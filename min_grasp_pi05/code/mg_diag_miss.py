#!/usr/bin/env python
"""最小抓取链路 · 抓空几何定位（eef 轨迹 vs can 初始位置，逐局给出「差多少、差在哪个轴」）。

为什么能只靠已落盘的 rollout 就算出来：
  mg_diag_trace.py 发现 K=50 的 10/10 局都是「夹爪完全空合（width→0.001）+ can 从未离地
  （max_lift≈0.03 cm）」。can 没动 => 它整局都停在**初始位置**；而初始位置由 seed 完全决定
  （mg_env.reset(seed) 钉住所有随机源，已用 --determinism 探针自证）。
  所以只要用同样的 seed 把 env reset 一次、读出 object_pos，就能把 rollout 里的 eef 轨迹
  和 can 的真实位置放在同一个坐标系里比 —— 不需要改 mg_eval.py（档 1 的评测进程正在用它）。

回答的问题（三个互斥假设，处方完全不同）：
  H1 横向偏：min‖eef_xy - can_xy‖ 明显 > 夹爪半开口（0.025+指厚）=> 视觉/动作尺度/状态对齐问题；
  H2 深度偏：横向对得上，但**空合那一刻** eef_z 比示范抓取高度 0.875 高太多 => 下探不够；
  H3 时机偏：横向、深度都对，但夹爪在 can 还没到指间时就合了 => 相位/时序（K 太大开环最常见）。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_diag_miss.py runs/pi05_rand60_s1/sweep/step_3000 \
        runs/s1_diag_step3000_k10'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

STATE_NAMES = ["eef_x", "eef_y", "eef_z", "eef_qw", "eef_qx", "eef_qy", "eef_qz", "gripper_width"]
IX, IY, IZ, IW = 0, 1, 2, 7

# 示范参照（60 局 rand60 实测，用 --demo-npz 可复算）：t_open=6、合爪时刻 t_close=38
# （min 25 / med 39 / max 50）、合爪时 eef_z=0.880（0.876~0.884）、夹住后 width=0.042~0.050、
# 全程 eef_z 最低点 0.878 出现在 t≈49、总步数 240（193~283）。
GRASP_Z_DEMO = 0.880      # **正向**示范合爪时夹爪中心高度（不是 0.875：那是 mg_env_reverse 的粗略注释值）
                          # ⚠️ 这只是 forward 的兜底值。反向要在**有墙的 bin2 象限**里抓，
                          # 合爪高度本来就可能不同；拿 0.880 去判反向的 H2（下探不够）会**安静地**给出
                          # 错结论。所以给了 --demo-npz 时，一律用**该 task_mode 的示范实测中位数**覆盖，
                          # 并把「用的是哪个值、从哪来的」打印出来（坑 30 的房规：参照值必须自报出处）。
W_OPEN_TH = 0.070         # 张开判据（reset 时 width=0.0417 是**半合**，不能拿它当「张开」）
W_CLOSE_TH = 0.055        # 合爪跃变判据：先 > W_OPEN_TH 再 < W_CLOSE_TH
CAN_RADIUS = 0.025        # can 半径；夹爪两指内侧面间距 = 2*0.025 时刚好贴住
CAN_TOP_Z = 0.9206        # can 立置顶面 = 中心 0.8603 + 半高 0.0603
CLOSE_EARLY_Z_TOL = 0.02  # 合爪时高出示范 0.880 这么多 = 「没到位就合爪」
W_EMPTY = 0.020           # width < 0.020 视为「两指合上了、中间什么都没有」


def close_transition(widths: np.ndarray) -> int:
    """示范/策略的「真正合爪时刻」：必须先张开（>0.070）再合上（<0.055）。

    为什么不能直接用 width<0.055：robosuite reset 后 width=0.0417（半合），
    第一帧就会被误判成「已合爪」（踩过：算出来 t_close 恒为 0）。
    """
    opened = np.nonzero(widths > W_OPEN_TH)[0]
    if len(opened) == 0:
        return -1
    t0 = int(opened[0])
    after = np.nonzero(widths[t0:] < W_CLOSE_TH)[0]
    return t0 + int(after[0]) if len(after) else -1


def demo_reference(npz_path: Path, task_mode: str, img_size: int) -> list[dict]:
    """把示范 npz 按同样的口径算一遍 —— 这就是「专家有多准」的参照，也是策略要达到的精度门。"""
    d = np.load(npz_path)
    st_all, L = d["state"], np.asarray(d["episode_lengths"], dtype=int)
    seeds = [int(x) for x in np.asarray(d["seeds"]).reshape(-1)] if "seeds" in d else [-1] * len(L)
    can0 = can_init_positions(seeds, task_mode, img_size)
    out, off = [], 0
    for i, n in enumerate(L):
        st = st_all[off:off + n]
        off += n
        c = can0.get(seeds[i])
        tc = close_transition(st[:, IW])
        dxy = np.linalg.norm(st[:, IX:IY + 1] - c[None, :2], axis=1) if c is not None else None
        rec = {"ep": i, "seed": seeds[i], "steps": int(n), "t_close": tc,
               "z_at_close": round(float(st[tc, IZ]), 4) if tc >= 0 else None,
               "w_min": round(float(st[:, IW].min()), 4),
               "z_min": round(float(st[:, IZ].min()), 4),
               "t_z_min": int(np.argmin(st[:, IZ]))}
        if dxy is not None:
            rec["min_dxy_cm"] = round(float(dxy.min()) * 100, 2)
            rec["dxy_at_close_cm"] = round(float(dxy[tc]) * 100, 2) if tc >= 0 else None
        out.append(rec)
    return out


def _mean_or_nan(vals) -> float:
    xs = [float(v) for v in vals if v is not None]
    return float(np.mean(xs)) if xs else float("nan")


def can_init_positions(seeds: list[int], task_mode: str, img_size: int = 64) -> dict[int, np.ndarray]:
    """按 seed 重建 can 的初始位置（reset 是确定的，所以这就是评测那局的真值）。"""
    if task_mode == "reverse":
        from mg_env_reverse import ReverseGraspEnv as EnvCls
    else:
        from mg_env import SingleArmGraspEnv as EnvCls
    env = EnvCls(img_size=img_size)
    out: dict[int, np.ndarray] = {}
    try:
        for s in sorted(set(seeds)):
            env.reset(seed=s)
            out[s] = np.asarray(env.object_pos, dtype=np.float64).copy()
    finally:
        env.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--img-size", type=int, default=64, help="只为重建初态，用小图省显存/时间")
    ap.add_argument("--demo-npz", default="", help="给一份示范 npz：按同口径算出「专家精度参照」并并排打印")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    payload: dict[str, object] = {}
    grasp_z_by_mode: dict[str, tuple[float, str]] = {}   # task_mode -> (合爪高度参照, 出处)
    if args.demo_npz:
        dp = Path(args.demo_npz)
        dm = json.loads((dp.parent / "MG_DATASET_CARD.json").read_text())["mode"] if (dp.parent / "MG_DATASET_CARD.json").exists() else "forward"
        mode = "reverse" if dp.name.endswith("_rev_raw.npz") else "forward"
        recs = demo_reference(dp, mode, args.img_size)
        print(f"\n=== 示范参照 {dp.name} (task_mode={mode}, n={len(recs)}) ===")
        for key in ("t_close", "z_at_close", "min_dxy_cm", "dxy_at_close_cm", "z_min", "w_min", "steps"):
            vals = [r[key] for r in recs if r.get(key) is not None]
            if vals:
                print(f"  {key:>15}: mean={np.mean(vals):8.4f} min={np.min(vals):8.4f} "
                      f"med={np.median(vals):8.4f} max={np.max(vals):8.4f}")
        print("  => 专家合爪时横向精度就是策略要达到的量级；差一个数量级 = 抓空。")
        zc = [r["z_at_close"] for r in recs if r.get("z_at_close") is not None]
        if zc:
            grasp_z_by_mode[mode] = (
                float(np.median(zc)),
                f"--demo-npz {dp.name} 实测 z_at_close 中位数（n={len(zc)}，"
                f"范围 {min(zc):.4f}~{max(zc):.4f}）")
            print(f"  => 合爪高度参照（task_mode={mode}）改用 **{np.median(zc):.4f}**，"
                  f"不再用硬编码的 {GRASP_Z_DEMO}")
        payload["demo_reference"] = {"npz": str(dp), "task_mode": mode, "episodes": recs,
                                    "grasp_z_used": grasp_z_by_mode.get(mode, (None, None))[0]}

    for r in args.runs:
        run = Path(r)
        summary = json.loads((run / "eval_summary.json").read_text())
        npz = np.load(run / "rollout_actions.npz")
        lengths = np.asarray(npz["episode_lengths"], dtype=int)
        states = npz["state"]
        per = summary.get("per_episode", [])
        task_mode = summary.get("task_mode", "forward")
        seeds = [int(p.get("seed", -1)) for p in per]
        print(f"\n=== {run.name}  task_mode={task_mode} K={summary.get('n_action_steps')} "
              f"成功率={summary.get('pc_success', float('nan')) * 100:.0f}% ===", flush=True)
        gz, gz_src = grasp_z_by_mode.get(
            task_mode,
            (GRASP_Z_DEMO, f"硬编码 GRASP_Z_DEMO（没给 task_mode={task_mode} 的 --demo-npz）"))
        print(f"  [参照] 合爪高度 gz={gz:.4f}，来源：{gz_src}"
              + ("" if task_mode in grasp_z_by_mode else
                 "  ⚠️ 这是**正向**的值，若本 run 是反向，H2（下探不够）的判定不可信，"
                 "请补 --demo-npz data/mix60f60r_rev_raw.npz 重跑"), flush=True)
        can0 = can_init_positions(seeds, task_mode, args.img_size)
        recs = []
        off = 0
        for i, L in enumerate(lengths):
            st = states[off:off + L]
            off += L
            pe = per[i] if i < len(per) else {}
            c = can0.get(seeds[i])
            if c is None:
                continue
            dxy = np.linalg.norm(st[:, IX:IY + 1] - c[None, :2], axis=1)
            dz = st[:, IZ] - c[2]
            t_near = int(np.argmin(dxy))
            closed = np.nonzero(st[:, IW] < W_EMPTY)[0]
            t_close = int(closed[0]) if len(closed) else -1
            rec = {
                "ep": i, "seed": seeds[i], "success": bool(pe.get("success")),
                "max_lift_cm": pe.get("max_lift_cm"),
                "can_init": np.round(c, 4).tolist(),
                # 最近横向接近：这一局 eef 到底有没有到过 can 正上方/正侧
                "min_dxy_cm": round(float(dxy.min()) * 100, 2), "t_min_dxy": t_near,
                "eef_z_at_min_dxy": round(float(st[t_near, IZ]), 4),
                "dz_at_min_dxy_cm": round(float(dz[t_near]) * 100, 2),
                "grip_width_at_min_dxy": round(float(st[t_near, IW]), 4),
                # 空合那一刻：横向差多少、高度差多少（H1/H2/H3 的直接读数）
                "first_empty_close_t": t_close,
                "dxy_at_close_cm": round(float(dxy[t_close]) * 100, 2) if t_close >= 0 else None,
                "eef_z_at_close": round(float(st[t_close, IZ]), 4) if t_close >= 0 else None,
                "dz_vs_grasp_at_close_cm": (round(float(st[t_close, IZ] - gz) * 100, 2)
                                            if t_close >= 0 else None),
                # 到达 can 顶面高度以下时，横向是否已经对上（判断「有没有真的伸进 can 两侧」）
                "min_dxy_below_can_top_cm": round(float(dxy[st[:, IZ] < CAN_TOP_Z].min()) * 100, 2)
                if bool((st[:, IZ] < CAN_TOP_Z).any()) else None,
            }
            recs.append(rec)
            tag = "*" if rec["success"] else " "
            print(f"  {tag} ep{i} seed={rec['seed']} lift={rec['max_lift_cm']}cm | "
                  f"min_dxy={rec['min_dxy_cm']}cm@t{rec['t_min_dxy']}(z={rec['eef_z_at_min_dxy']:.3f}, "
                  f"w={rec['grip_width_at_min_dxy']:.3f}) | "
                  + (f"空合@t{rec['first_empty_close_t']}: dxy={rec['dxy_at_close_cm']}cm "
                     f"z={rec['eef_z_at_close']} (比示范合爪高度 {gz:.4f} "
                     f"{rec['dz_vs_grasp_at_close_cm']:+}cm)"
                     if rec['first_empty_close_t'] >= 0 else "全程未空合") + " | "
                  f"低于 can 顶时的 min_dxy={rec['min_dxy_below_can_top_cm']}cm", flush=True)
        if recs:
            fails = [x for x in recs if not x["success"]]
            pool = fails or recs
            print(f"  -- 汇总（{'失败局' if fails else '全部'} n={len(pool)}）："
                  f"min_dxy mean={np.mean([x['min_dxy_cm'] for x in pool]):.2f}cm "
                  f"max={max(x['min_dxy_cm'] for x in pool):.2f}cm | "
                  f"空合局数={sum(1 for x in pool if x['first_empty_close_t'] >= 0)}/{len(pool)} "
                  f"空合时 dxy mean={_mean_or_nan([x['dxy_at_close_cm'] for x in pool]):.2f}cm "
                  f"空合时刻 mean={_mean_or_nan([x['first_empty_close_t'] if x['first_empty_close_t'] >= 0 else None for x in pool]):.0f} | "
                  f"空合时 z-参照({gz:.3f}) mean="
                  f"{_mean_or_nan([x['dz_vs_grasp_at_close_cm'] for x in pool]):+.2f}cm")
        payload[str(run)] = {"task_mode": task_mode, "K": summary.get("n_action_steps"),
                             "pc_success": summary.get("pc_success"), "episodes": recs,
                             "grasp_z_used": gz, "grasp_z_source": gz_src,
                             "grasp_z_demo_hardcoded": GRASP_Z_DEMO, "can_radius": CAN_RADIUS}

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"\n[saved] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
