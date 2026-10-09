#!/usr/bin/env python3
"""A 线：闭环抬起的**来源归因**诊断（只读，吃 `eval_lerobot_act_runtime.py --log-actions` 产物）。

为什么需要它：开环审计（`scripts/audit_lerobot_act_lift_frames.py`）只能说明 policy 在
**teacher 状态**上会不会发抬起命令；闭环成功到底靠什么抬起来的，必须看真正送进
`env.step` 的逐帧动作与逐帧方块高度。本脚本把每 0.001 m 的抬升归因到三类帧：

  burst  dz >= 0.5                    —— teacher 的抬法是 lift 相位 7 帧 dz=+1.0（base-only
                                          实测每帧约 0.011 m，7 帧 ≈ 0.0764 m = 参考上界）
  bias   0.005 <= dz < 0.5            —— 持续小正命令，20 Hz 下靠积分慢慢抬
  other  dz < 0.005（含负）            —— 不贡献抬升

回答的问题（K=2 臂 seed0 受控 9/20、seed1 只有 2/20，而两者**开环** lift 帧 dz 均值
0.815 / 0.812、首个 dz>=0.5 都在第 2 帧，几乎相同）：差异到底在哪一段？

口径说明：
  - 不使用 `phase_trace` 的 'grasp' 当锚点：该标签判据是 max|gripper_qpos| > 0.012
    （两指张开超 1.2cm），episode 第 0 帧爪是张开的就成立，因此 t=0 就是 'grasp'，
    拿它当"抓起时刻"会把整局都算进窗口（已踩过这个坑）。夹持证据一律取
    `grasp_verified` / `held_at_end`（robosuite `_check_grasp`）。
  - 归因用逐帧 rise 增量 dr[t] = rise[t] - rise[t-1]，按该帧的 dz 分类求和；
    三类之和 = final_rise - rise[0]，脚本内做闭合校验（残差 > 1e-6 就报警）。
  - tail 窗口默认取第 100 帧之后（approach/descend 在此之前基本结束），用于量
    "抓起之后的持续 dz 偏置"。

用法：
    python3 scripts/a_closed_loop_dz_diag.py \
        [--dir runs/infra/lerobot_act_env_20260928/actlog] [--tail 100] [--json-out ...]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

DZ = 2
GRIP = 6
BURST = 0.5
BIAS_LO = 0.005
RISE_OK = 0.04


def episode_stats(row: dict, tail0: int) -> dict:
    acts = np.asarray(row["actions"], dtype=np.float64)
    rise = np.asarray(row["rise_trace"], dtype=np.float64)
    dz = acts[:, DZ]
    n = len(dz)
    # rise_trace[t] 是执行完第 t 帧动作后的相对位移；第 t 帧的增量 = rise[t] - rise[t-1]，
    # 第 0 帧的增量 = rise[0]（相对 z0）。
    dr = np.empty(n)
    dr[0] = rise[0]
    dr[1:] = np.diff(rise)

    m_burst = dz >= BURST
    m_bias = (dz >= BIAS_LO) & ~m_burst
    m_other = ~m_burst & ~m_bias
    attribution = {
        "burst": round(float(dr[m_burst].sum()), 5),
        "bias": round(float(dr[m_bias].sum()), 5),
        "other": round(float(dr[m_other].sum()), 5),
    }
    # 三类之和必须等于 final rise（逐项求和是精确望远镜求和）。容差取 1e-4：
    # rise_trace 记到 1e-6、归因分量记到 1e-5，舍入本身就在这个量级，不能用 1e-6 判违规。
    closure = abs(float(dr[m_burst].sum() + dr[m_bias].sum() + dr[m_other].sum()) - float(rise[-1]))
    # 最长连续 burst 段
    run = best = 0
    for v in m_burst:
        run = run + 1 if v else 0
        best = max(best, run)
    lo = min(tail0, max(0, n - 1))
    dzt = dz[lo:]
    return {
        "seed": row["seed"],
        "max_rise": round(float(row["max_rise"]), 4),
        "final_rise": round(float(row["final_rise"]), 4),
        "grasp_verified": bool(row["grasp_verified"]),
        "held_at_end": bool(row["held_at_end"]),
        "phase_at_end": row["phase_at_end"],
        "rise_attribution_m": attribution,
        "attribution_closure_residual": round(closure, 9),
        "attribution_total": round(float(dr.sum()), 5),
        "burst_frames": int(m_burst.sum()),
        "burst_max_run": int(best),
        "first_burst_frame": (int(np.argmax(m_burst)) if m_burst.any() else None),
        "dz_mean_all": round(float(dz.mean()), 4),
        "dz_mean_tail": round(float(dzt.mean()), 4),
        "dz_pos_frac_tail": round(float((dzt >= BIAS_LO).mean()), 4),
        "grip_mean_tail": round(float(acts[lo:, GRIP].mean()), 4),
        "rise_tail_gain": round(float(rise[-1] - rise[lo]), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="闭环抬起来源归因（只读）")
    ap.add_argument("--dir", default="runs/infra/lerobot_act_env_20260928/actlog")
    ap.add_argument("--pattern", default="actlog_*.json")
    ap.add_argument("--tail", type=int, default=100, help="tail 窗口起始帧（默认 100）")
    ap.add_argument("--per-episode", action="store_true", help="打印逐局明细")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()

    root = Path(a.dir)
    files = sorted(root.glob(a.pattern))
    if not files:
        raise SystemExit(f"[错误] {root} 下没有 {a.pattern}；先用 --log-actions 生成")

    out = []
    for path in files:
        d = json.loads(path.read_text())
        if not d.get("log_actions"):
            print(f"[跳过] {path.name}: log_actions != true（需要重跑 --log-actions）")
            continue
        arm = path.name[len("actlog_"):-len(".json")]
        eps = [episode_stats(r, a.tail) for r in d["rows"]]
        bad = [e for e in eps if e["attribution_closure_residual"] > 1e-4]
        hi = [e for e in eps if e["max_rise"] >= RISE_OK]
        lo = [e for e in eps if e["max_rise"] < RISE_OK]

        def agg(seq, path_):
            if not seq:
                return None
            v = seq[0]
            for k in path_:
                v = v[k]
            vals = []
            for e in seq:
                x = e
                for k in path_:
                    x = x[k]
                vals.append(x)
            return round(float(np.mean([x for x in vals if x is not None])), 5) if vals else None

        grp = lambda seq: {
            "n": len(seq),
            "max_rise": agg(seq, ["max_rise"]),
            "burst_frames": agg(seq, ["burst_frames"]),
            "burst_max_run": agg(seq, ["burst_max_run"]),
            "dz_mean_tail": agg(seq, ["dz_mean_tail"]),
            "dz_pos_frac_tail": agg(seq, ["dz_pos_frac_tail"]),
            "rise_from_burst": agg(seq, ["rise_attribution_m", "burst"]),
            "rise_from_bias": agg(seq, ["rise_attribution_m", "bias"]),
            "rise_from_other": agg(seq, ["rise_attribution_m", "other"]),
            "rise_tail_gain": agg(seq, ["rise_tail_gain"]),
        }
        out.append({
            "arm": arm, "file": path.name,
            "chunk_size": d.get("chunk_size"), "replan_every": d.get("replan_every"),
            "checkpoint_sha8": (d.get("checkpoint", {}).get("model_safetensors_sha256") or "")[:8],
            "episodes": len(eps), "n_high_rise": len(hi), "n_low_rise": len(lo),
            "grasp_verified": sum(e["grasp_verified"] for e in eps),
            "held_at_end": sum(e["held_at_end"] for e in eps),
            "attribution_closure_violations": len(bad),
            "all": grp(eps), "high": grp(hi), "low": grp(lo),
            "per_episode": eps,
        })
        if a.per_episode:
            print(f"\n--- {arm} 逐局 ---")
            for e in eps:
                at = e["rise_attribution_m"]
                print(f"  seed={e['seed']} max={e['max_rise']:+.4f} fin={e['final_rise']:+.4f} "
                      f"gv={int(e['grasp_verified'])} hold_end={int(e['held_at_end'])} "
                      f"burst={e['burst_frames']:2d}(run{e['burst_max_run']},first={e['first_burst_frame']}) "
                      f"dz_tail={e['dz_mean_tail']:+.4f} posfrac={e['dz_pos_frac_tail']:.2f} "
                      f"归因 burst={at['burst']:+.4f} bias={at['bias']:+.4f} other={at['other']:+.4f}")

    hdr = (f"{'arm':42s} {'K':>2s} {'R':>2s} {'hi/lo':>6s} {'gv':>3s} "
           f"{'burst帧':>7s} {'dz_tail':>8s} {'rise←burst':>10s} {'rise←bias':>10s} {'闭合残差':>8s}")
    print()
    print(hdr)
    print("-" * len(hdr))
    for e in out:
        g = e["all"]
        print(f"{e['arm'][:42]:42s} {e['chunk_size']:>2d} {e['replan_every']:>2d} "
              f"{str(e['n_high_rise'])+'/'+str(e['n_low_rise']):>6s} {e['grasp_verified']:>3d} "
              f"{g['burst_frames']:>7.2f} {g['dz_mean_tail']:>+8.4f} "
              f"{g['rise_from_burst']:>+10.4f} {g['rise_from_bias']:>+10.4f} "
              f"{e['attribution_closure_violations']:>8d}")

    print("\nhigh(max_rise>=0.04) vs low 分组对比：")
    for e in out:
        h, l = e["high"], e["low"]
        line = f"  {e['arm']}"
        for name, g in (("high", h), ("low", l)):
            if not g["n"]:
                line += f" | {name}: n=0"
                continue
            line += (f" | {name}: n={g['n']} burst帧={g['burst_frames']:.1f} "
                     f"dz_tail={g['dz_mean_tail']:+.4f} rise←burst={g['rise_from_burst']:+.4f} "
                     f"rise←bias={g['rise_from_bias']:+.4f}")
        print(line)

    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(
            {"diagnostic": "closed_loop_rise_attribution", "read_only": True,
             "claim": "closed_loop_sim_truth 的抬升来源分解，不是能力结论",
             "bins": {"burst": f"dz>={BURST}", "bias": f"{BIAS_LO}<=dz<{BURST}", "other": f"dz<{BIAS_LO}"},
             "tail_window_start": a.tail, "rise_ok": RISE_OK,
             "note": "teacher 的抬法 = lift 相位 7 帧 dz=+1.0；base-only 参考上界 mean_max_rise 0.0764 m",
             "arms": out}, indent=2, ensure_ascii=False) + "\n")
        print("\n写出:", a.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
