#!/usr/bin/env python
"""接触任务的**抓取几何可行性**探针：夹爪开口 vs 物体宽度，谁大谁小决定了「抓」是什么。

为什么需要这个探针（2026-09-24 实测触发）
------------------------------------------------------------------
`diag_lift_savebest_model_final32.json` 里出现了一个反直觉的组合：

    · 手写状态机 32/32 成功，但**每一局的 `min_width` 都等于开局张开值 0.0208**
      —— 也就是夹爪从头到尾没有闭合过；
    · SAC 26/32 成功，成功局 `min_width` 中位数同样是 0.0208；
      而 **17 个失败局的 `min_width` 是 0.001~0.0096**（几乎完全闭合）。

「闭合了 ⇒ 失败，没闭合 ⇒ 成功」不是学习噪声能解释的，它指向一个**几何常量**：
`harness/env_factory.py` 的 `object_geom` 审计显示本进程钉死的 cube 半尺寸是
[0.02198, 0.02104, 0.02170] ⇒ 边宽 **0.0421~0.0440 m**；而夹爪张开时两个
fingerpad 内侧面之间的距离只有 **~0.0406 m**（本探针实测）。物体比开口还宽
1.5~3.4 mm ⇒ **平行夹爪不可能包住它**，任何"闭合"动作要么把物体挤走、
要么在物体旁边空合。于是这个任务上唯一可行的技能不是"抓"，而是
**压配夹持（press-fit / wedge）**：张开的手指压进物体两侧，靠接触法向力 + 摩擦提起。

这直接解释了对方的两条负结果，而且给出的是相反的修法：
    · BC / DAgger 学的是示范里的**夹爪通道**（示范的 close_frac≈0.6，但因为手指已经
      压在物体上、根本动不了，所以"闭合指令"在示范里是无害的）。策略在没有接触的状态
      下模仿同一个指令 ⇒ 空合 ⇒ 物体丢在原地。这就是 `grasp_no_lift` 的真实机理。
    · `reward_shaping` 里的 grasp 项（+0.25）奖励的是 `_check_grasp`（两 pad 接触），
      不是闭合度，所以它并不要求闭合；但示范与 BC 都把"闭合"当成了相关特征。

还有一个**跨 run 可比性**的后果，必须一起量：cube 尺寸是 robosuite 构造期从
`size_min=[0.020]*3, size_max=[0.022]*3` 抽的（`pinned_object_rng` 的文档已记录它
未播种）。半宽 0.020 ⇒ 边宽 0.0400 < 开口 0.0406（**可以真夹住**）；
半宽 0.022 ⇒ 0.0440（**只能压配**）。也就是说 [0.020, 0.022] 这个默认区间
**横跨了几何可行性的分界线**：不同进程/不同臂抽到的 cube 落在分界线两侧，
任务性质都不一样。对方 ablation 表里 5%/5%/10%/15% 那些数字，
有一部分可能根本不是策略差异，而是**物体抽签**。

这个探针只做测量、不跑策略（秒级），输出三样东西：
    1. `pad_gap(qpos)`：夹爪开口随关节值的函数，以及全闭时的最小开口；
    2. 每个 `pin_seed` 抽到的 cube 边宽（沿闭合轴，含 yaw 的最坏/最好情况）；
    3. 可行性判定：`graspable`（边宽 < 张开开口）/ `press_fit`（边宽 ≥ 张开开口），
       以及干涉量 `interference_mm`。

用法：
    MUJOCO_GL=egl /root/venvs/rlrobot/bin/python scripts/probe_grasp_geometry.py \
        --pin-seeds 20260923,1,2,3,4,5,6,7 --out runs/infra/grasp_geometry.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.env_factory import (PINNED_OBJECT_SEED, contact_object, contact_object_geom,  # noqa: E402
                                 make_contact_env)


def _geom_ids_by_substr(sim, substr: str) -> dict[str, int]:
    out = {}
    for gid in range(sim.model.ngeom):
        name = sim.model.geom_id2name(gid) or ""
        if substr in name:
            out[name] = gid
    return out


def gripper_geometry(env, qpos_grid=(0.0208, 0.015, 0.010, 0.005, 0.0)) -> dict:
    """实测夹爪：闭合轴、开口随 qpos 的函数、全闭最小开口。

    不靠解析 XML：直接把两个 finger 关节设到给定 qpos，`mj_forward` 之后读
    pad / finger 两组 collision geom 的位置，用「张开 vs 全闭」的位移方向定闭合轴，
    再按 box geom 的半尺寸扣掉厚度得到**内侧面间距**（真正决定能不能塞进物体的量）。
    """
    inner = env._env
    sim = inner.sim
    jnames = [n for n in sim.model.joint_names if "finger" in n.lower()]
    if not jnames:
        raise RuntimeError("找不到 finger 关节，夹爪几何无法测量")
    pads = _geom_ids_by_substr(sim, "pad_collision")
    fingers = {k: v for k, v in _geom_ids_by_substr(sim, "finger") .items()
               if k.endswith("_collision") and "pad" not in k}
    if len(pads) != 2 or len(fingers) != 2:
        raise RuntimeError(f"pad/finger collision geom 数量异常: pads={list(pads)} fingers={list(fingers)}")

    def set_q(q: float):
        for i, jn in enumerate(jnames):
            sign = 1.0 if i % 2 == 0 else -1.0      # 左右指反向
            sim.data.set_joint_qpos(jn, sign * q)
        sim.forward()          # robosuite 包了一层 MjModel/MjData，不能直接喂 mujoco.mj_*

    def inner_gap(ids: dict[str, int]) -> tuple[float, np.ndarray]:
        (n1, g1), (n2, g2) = sorted(ids.items())
        p1 = np.asarray(sim.data.geom_xpos[g1], dtype=np.float64)
        p2 = np.asarray(sim.data.geom_xpos[g2], dtype=np.float64)
        s1 = np.asarray(sim.model.geom_size[g1], dtype=np.float64)
        s2 = np.asarray(sim.model.geom_size[g2], dtype=np.float64)
        return p1, p2, s1, s2, n1, n2

    rows = []
    axis = None
    for q in qpos_grid:
        set_q(float(q))
        p1, p2, s1, s2, n1, n2 = inner_gap(pads)
        d = p2 - p1
        if axis is None and q != qpos_grid[0]:
            pass
        rows.append({"qpos": float(q), "pad_center_dist": round(float(np.linalg.norm(d)), 5),
                     "pad_delta": [round(float(v), 5) for v in d],
                     "pad_halfsize": [round(float(v), 5) for v in s1],
                     "finger_center_dist": None})
        f1, f2, fs1, fs2, fn1, fn2 = inner_gap(fingers)
        rows[-1]["finger_center_dist"] = round(float(np.linalg.norm(f2 - f1)), 5)
        rows[-1]["finger_halfsize"] = [round(float(v), 5) for v in fs1]
        rows[-1]["pad_geoms"] = [n1, n2]
        rows[-1]["finger_geoms"] = [fn1, fn2]

    # 闭合轴：张开与全闭两次 pad 位移的主方向
    set_q(float(qpos_grid[0]))
    p_open = {n: np.asarray(sim.data.geom_xpos[g], dtype=np.float64).copy()
              for n, g in pads.items()}
    set_q(0.0)
    p_close = {n: np.asarray(sim.data.geom_xpos[g], dtype=np.float64).copy()
               for n, g in pads.items()}
    (n1, n2) = sorted(pads)
    disp = (p_close[n1] - p_open[n1]) - (p_close[n2] - p_open[n2])
    axis = disp / max(np.linalg.norm(disp), 1e-12)

    def gap_along_axis(q: float, ids: dict[str, int]) -> float:
        set_q(float(q))
        (a, ga), (b, gb) = sorted(ids.items())
        pa = np.asarray(sim.data.geom_xpos[ga], dtype=np.float64)
        pb = np.asarray(sim.data.geom_xpos[gb], dtype=np.float64)
        sa = float(np.dot(np.asarray(sim.model.geom_size[ga], dtype=np.float64), np.abs(axis)))
        sb = float(np.dot(np.asarray(sim.model.geom_size[gb], dtype=np.float64), np.abs(axis)))
        center = float(np.dot(pb - pa, axis))
        return abs(center) - sa - sb

    q_open = float(np.max(np.abs(np.asarray(
        inner._get_observations()["robot0_gripper_qpos"], dtype=np.float64))))
    out = {
        "finger_joints": jnames,
        "closing_axis": [round(float(v), 4) for v in axis],
        "qpos_at_reset_open": round(q_open, 5),
        "pad_gap_at_open": round(gap_along_axis(q_open, pads), 5),
        "finger_gap_at_open": round(gap_along_axis(q_open, fingers), 5),
        "pad_gap_at_full_close": round(gap_along_axis(0.0, pads), 5),
        "effective_gap_at_open": None,
        "qpos_grid": rows,
    }
    # 谁能先碰到物体，谁就是有效开口：pad 与 finger 两组 collision geom 取更小的那个
    out["effective_gap_at_open"] = round(min(out["pad_gap_at_open"], out["finger_gap_at_open"]), 5)
    set_q(q_open)
    return out


def object_widths(env, task: str, axis: np.ndarray) -> dict:
    """物体沿闭合轴的宽度：按当前 yaw 算一次，再给出 yaw 最坏/最好情况。

    box 的半宽沿轴 = Σ_i |axis·e_i| * halfsize_i（e_i 是物体自身坐标轴，由 quat 给出）。
    """
    import mujoco

    inner = env._env
    sim = inner.sim
    obj = contact_object(env, task)
    # `contact_object()` 给的是 robosuite 的物体**对象**（BoxObject / 罐子），不是 geom 名。
    # 取它自己的 collision geom 列表；拿不到就退回「名字含物体前缀且不是 *_vis」的扫描。
    names = list(getattr(obj, "contact_geoms", None) or [])
    if not names:
        prefix = getattr(getattr(obj, "root_body", None), "lower", lambda: "")() or ""
        names = [n for n in sim.model.geom_names
                 if (prefix and prefix in n) and not n.endswith("_vis")]
    gids = [sim.model.geom_name2id(n) for n in names if n in set(sim.model.geom_names)]
    if not gids:
        raise RuntimeError(f"找不到物体 collision geom（候选 {names}）")
    gid = gids[0]
    half = np.asarray(sim.model.geom_size[gid], dtype=np.float64)
    body = sim.model.geom_bodyid[gid]
    quat = np.asarray(sim.data.body_xquat[body], dtype=np.float64)   # (w,x,y,z)
    R9 = np.zeros(9, dtype=np.float64)          # mju_quat2Mat 要 (9,1) 扁平输出
    mujoco.mju_quat2Mat(R9, np.ascontiguousarray(quat, dtype=np.float64))
    R = R9.reshape(3, 3)
    w_along = 2.0 * float(np.dot(half, np.abs(R.T @ axis)))
    best = 2.0 * float(half.min())                     # yaw 最好：最短边正对夹爪
    worst = 2.0 * float(np.linalg.norm(half[:2]))       # yaw 最坏：水平面对角线正对夹爪
    return {"geom": sim.model.geom_id2name(gid),
            "half_size": [round(float(v), 5) for v in half],
            "width_along_axis_now": round(w_along, 5),
            "width_min_over_yaw": round(best, 5),
            "width_max_over_yaw_horizontal": round(worst, 5),
            "body_mass_kg": round(float(sim.model.body_mass[body]), 4)}


def feasibility(obj: dict, grip: dict) -> dict:
    gap = grip["effective_gap_at_open"]
    w_now = obj["width_along_axis_now"]
    interference = w_now - gap
    regime = "graspable" if interference < 0 else "press_fit"
    return {"effective_gap_at_open": gap,
            "object_width_along_axis": w_now,
            "interference_mm": round(interference * 1000.0, 3),
            "regime": regime,
            "worst_case_regime": ("press_fit" if obj["width_max_over_yaw_horizontal"] - gap >= 0
                                  else "graspable"),
            "note": ("物体比夹爪有效开口宽 ⇒ 平行夹爪无法包住它，只能压配夹持；"
                     "此时「闭合指令」在物体旁边空合，会把物体挤走或原地丢下"
                     if regime == "press_fit" else
                     "物体窄于有效开口 ⇒ 存在真正的包络抓取窗口")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", default="lift", choices=["lift", "pickplace"])
    ap.add_argument("--pin-seeds", default=str(PINNED_OBJECT_SEED),
                    help="逗号分隔的 pin_seed 列表；每个都会建一次环境量一遍几何")
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    seeds = [int(s) for s in str(args.pin_seeds).split(",") if s.strip() != ""]
    results = []
    for ps in seeds:
        env = make_contact_env(args.task, horizon=args.horizon, reward_shaping=False,
                               pin_seed=ps)
        env.reset(seed=1000)
        grip = gripper_geometry(env)
        axis = np.asarray(grip["closing_axis"], dtype=np.float64)
        env.reset(seed=1000)
        obj = object_widths(env, args.task, axis)
        feas = feasibility(obj, grip)
        audit = contact_object_geom(env, args.task, ps)
        row = {"pin_seed": ps, "gripper": {k: v for k, v in grip.items() if k != "qpos_grid"},
               "object": obj, "object_geom_audit": audit, **feas}
        results.append(row)
        print(f"pin_seed={ps:>10} 有效开口={feas['effective_gap_at_open']:.5f} m · "
              f"物宽(沿轴)={feas['object_width_along_axis']:.5f} m · "
              f"干涉={feas['interference_mm']:+.2f} mm · {feas['regime']} · "
              f"最坏 yaw={feas['worst_case_regime']} · 质量={obj['body_mass_kg']} kg",
              flush=True)
        env.close()

    n_pf = sum(1 for r in results if r["regime"] == "press_fit")
    summary = {
        "task": args.task, "n_pin_seeds": len(results),
        "n_press_fit": n_pf, "n_graspable": len(results) - n_pf,
        "pinned_seed_regime": next((r["regime"] for r in results
                                    if r["pin_seed"] == PINNED_OBJECT_SEED), None),
        "verdict": (
            f"{len(results)} 个 pin_seed 中 {n_pf} 个落在 press_fit（物体宽于夹爪有效开口）"
            f"⇒ 这些进程里的 Lift 根本不是「抓起来」的任务，而是「压配夹持」；"
            f"跨 run 比较成功率之前必须先比这一栏"
            if n_pf else
            f"{len(results)} 个 pin_seed 全部 graspable ⇒ 包络抓取窗口存在，"
            f"失败应归因于对准/时机而不是几何不可行"),
        "results": results,
    }
    print("-" * 78)
    print(summary["verdict"], flush=True)
    if args.out:
        out = Path(args.out)
        out = out if out.is_absolute() else REPO_ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"已写出: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
