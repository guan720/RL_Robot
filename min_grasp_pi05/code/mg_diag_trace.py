#!/usr/bin/env python
"""最小抓取链路 · 失败模式定位（从已落盘的 rollout 反推，不用重跑仿真）。

为什么需要它：mg_eval.py 只给「成功/失败 + max_lift + min_dist」，
但失败的**机理**有好几种，处方完全不同：
  A. 没下探到位（min eef_z 太高）          -> 视觉/状态对齐、位置增量尺度、或 K 太大开环；
  B. 下探到位但抓空（width < 0.020 = 两指合上了中间没东西）-> **横向**精度不够（不是 gripper 语义错，
                                             语义错的话 width 根本不会到 0.001）；
  C. 物体真的被抬起来了（max_lift > 2 cm）但没落进目标框 -> 搬运/释放/落点或终止判定；
  D. 成功。
本工具用「夹爪开口三态 + 下探深度 + 物体是否离地」把 A/B/C 分开，并支持多个 run 并排
（例如同检查点的 K=50 vs K=10），这样「K 改变了什么」是**机理级**结论，而不是只看成功率。

判据（实测真值：can 直径 0.050；示范里夹住 can 时 width=0.0417~0.050、空夹张开 0.0795、
抓空时 width→0.001；机器人基座 [-0.5,-0.1,0.912]，故 eef_z 物理上限 ≈1.77）：
  下探到位  min(eef_z) <= 0.90
  抓空      min(width) <  0.020
  夹住 can  width ∈ [0.030, 0.065] 的步数占比 > 2%
  物体离地  eval_summary 的 max_lift_cm > 2
  竖直甩臂  max(eef_z) > 1.30（示范上限 1.0457）= 抓空后把「抬臂」一路积分到关节极限

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_diag_trace.py \
        runs/pi05_rand60_s1/sweep/step_3000 runs/s1_diag_step3000_k10'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

STATE_NAMES = ["eef_x", "eef_y", "eef_z", "eef_qw", "eef_qx", "eef_qy", "eef_qz", "gripper_width"]
ACTION_NAMES = ["dx", "dy", "dz", "droll", "dpitch", "dyaw", "gripper"]
IZ = STATE_NAMES.index("eef_z")
IW = STATE_NAMES.index("gripper_width")
IG = ACTION_NAMES.index("gripper")

# 几何真值（mg_env / mg_env_reverse 实测）：bin 底 0.82，can 立置中心 0.8603，
# 抓取时 eef_z ≈ 0.875；**机器人基座在 [-0.5,-0.1,0.912]**（探针实测），
# 所以 eef_z 的物理上限 ≈ 0.912 + 0.855 ≈ 1.77 —— 见到 1.6~1.75 不是仿真炸了，是臂竖直伸到底。
GRASP_Z = 0.875
REACHED_Z_TOL = 0.025   # z_min <= 0.90 记为「下探到位」
CAN_DIAM = 0.050
# 夹爪开口三态（示范实测：空夹张开 0.0795，夹住 can 0.0417~0.050，空合 0.001）
W_EMPTY = 0.020         # < 0.020 = 两指合上了但中间什么都没有（抓空）
W_HOLD_LO = 0.030       # [0.030, 0.065] = 夹着 can
W_HOLD_HI = 0.065
W_OPEN = 0.070          # > 0.070 = 张开
RUNAWAY_Z = 1.30        # 示范 eef_z 上限 1.0457；超过就是「抓空后一路往上甩」


def classify(states: np.ndarray, actions: np.ndarray, extra: dict | None = None) -> dict:
    """三态夹爪 + 下探深度 + 物体是否真的离开初始高度 -> 定位失败机理。

    extra 里放 eval_summary 的 per-episode 字段（max_lift_cm / min_dist），
    因为 rollout npz 只存了 eef 侧的量，物体侧只能从 summary 拿。
    """
    extra = extra or {}
    z = states[:, IZ]
    w = states[:, IW]
    g = actions[:, IG]
    z_min = float(z.min())
    z_min_i = int(np.argmin(z))
    w_min = float(w.min())
    w_min_i = int(np.argmin(w))
    lift_cm = extra.get("max_lift_cm")
    lifted = bool(lift_cm is not None and float(lift_cm) > 2.0)

    f_empty = float((w < W_EMPTY).mean())
    f_hold = float(((w >= W_HOLD_LO) & (w <= W_HOLD_HI)).mean())
    f_open = float((w > W_OPEN).mean())
    reached = bool(z_min <= GRASP_Z + REACHED_Z_TOL)
    closed_empty = bool(w_min < W_EMPTY)
    held_can = bool(f_hold > 0.02)
    runaway = bool(float(z.max()) > RUNAWAY_Z)

    if not reached:
        mode = "A_没下探到位"
    elif closed_empty and not lifted:
        mode = "B_到位但抓空"
    elif lifted and not bool(extra.get("success", False)):
        mode = "C_抓起但没放对" if held_can else "C?_物体动了但没夹住"
    elif bool(extra.get("success", False)):
        mode = "D_成功"
    else:
        mode = "E_其它"
    return {"mode": mode, "z_min": round(z_min, 4), "z_min_at": z_min_i,
            "z_max": round(float(z.max()), 4), "z_end": round(float(z[-1]), 4),
            "w_min": round(w_min, 4), "w_min_at": w_min_i, "w_end": round(float(w[-1]), 4),
            "f_empty": round(f_empty, 3), "f_hold": round(f_hold, 3), "f_open": round(f_open, 3),
            "runaway_up": runaway, "lifted": lifted,
            "grip_open": round(float((g > 0.2).mean()), 3),
            "grip_close": round(float((g < -0.2).mean()), 3),
            "grip_mush": round(float((np.abs(g) <= 0.2).mean()), 3),
            "steps": int(len(states))}


def load(run: Path):
    npz = np.load(run / "rollout_actions.npz")
    lengths = np.asarray(npz["episode_lengths"], dtype=int)
    success = np.asarray(npz["success"], dtype=bool)
    acts, states = npz["action"], npz["state"]
    summary = json.loads((run / "eval_summary.json").read_text()) if (run / "eval_summary.json").exists() else {}
    per = summary.get("per_episode", [])
    out, o, so = [], 0, 0
    for i, L in enumerate(lengths):
        pe = per[i] if i < len(per) else {}
        rec = {"i": i, "seed": pe.get("seed", -1), "success": bool(success[i]),
               "max_lift_cm": pe.get("max_lift_cm"), "min_dist_cm": pe.get("min_dist_to_target_xy")}
        rec.update(classify(states[so:so + L], acts[o:o + L],
                            extra={"max_lift_cm": pe.get("max_lift_cm"), "success": bool(success[i])}))
        out.append(rec)
        o += L
        so += L
    return out, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", help="含 rollout_actions.npz 的评测输出目录")
    ap.add_argument("--per-episode", action="store_true", help="打印逐局明细（默认只打汇总 + 失败局）")
    ap.add_argument("--out", default="", help="把结构化结果写成 JSON")
    args = ap.parse_args()

    all_res = {}
    for r in args.runs:
        run = Path(r)
        if not (run / "rollout_actions.npz").exists():
            print(f"[skip] {run} 没有 rollout_actions.npz", file=sys.stderr)
            continue
        eps, summary = load(run)
        all_res[str(run)] = {"episodes": eps, "summary_keys": {
            k: summary.get(k) for k in ("pc_success", "n_success", "n_action_steps", "chunk_size",
                                        "seed", "seed_mode", "task_mode", "policy_ckpt")}}
        K = summary.get("n_action_steps", "?")
        print(f"\n=== {run.name}  K={K}  seeds={summary.get('seed')}+  "
              f"成功率={summary.get('pc_success', float('nan')) * 100:.0f}% "
              f"({summary.get('n_success')}/{summary.get('episodes')}) ===")
        modes: dict[str, int] = {}
        for e in eps:
            modes[e["mode"]] = modes.get(e["mode"], 0) + 1
        print("  失败/成功机理分布：" + "  ".join(f"{k}={v}" for k, v in sorted(modes.items())))
        n_run = sum(e["runaway_up"] for e in eps)
        print(f"  抓空(w<{W_EMPTY}) 局数={sum(1 for e in eps if e['w_min'] < W_EMPTY)}/{len(eps)}  "
              f"夹住 can 局数={sum(1 for e in eps if e['f_hold'] > 0.02)}/{len(eps)}  "
              f"竖直甩臂(z>{RUNAWAY_Z}) 局数={n_run}/{len(eps)}")
        for key in ("z_min", "z_max", "w_min", "f_empty", "f_hold", "f_open",
                    "grip_open", "grip_close", "grip_mush", "max_lift_cm"):
            vals = [e[key] for e in eps if isinstance(e.get(key), (int, float))]
            if vals:
                print(f"  {key:>11}: mean={np.mean(vals):+.3f}  min={np.min(vals):+.3f}  max={np.max(vals):+.3f}")
        print("  逐局（* = 成功）：")
        for e in eps:
            if not args.per_episode and e["success"]:
                continue
            print(f"   {'*' if e['success'] else ' '} ep{e['i']} seed={e['seed']} {e['mode']:<14} "
                  f"steps={e['steps']:>3} z_min={e['z_min']:.3f}@{e['z_min_at']:>3} z_max={e['z_max']:.3f} "
                  f"w_min={e['w_min']:.4f}@{e['w_min_at']:>3} lift={e['max_lift_cm']} "
                  f"w(empty/hold/open)={e['f_empty']:.2f}/{e['f_hold']:.2f}/{e['f_open']:.2f} "
                  f"grip(+/-/~0)={e['grip_open']:.2f}/{e['grip_close']:.2f}/{e['grip_mush']:.2f}"
                  + (" RUNAWAY" if e["runaway_up"] else ""))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(all_res, indent=2, ensure_ascii=False))
        print(f"\n[saved] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
