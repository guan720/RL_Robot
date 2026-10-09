#!/usr/bin/env python3
"""A2 / G3 附：**「起手位姿保持」零假设对照**（no-op null）+ 可达包络算术。

为什么要有这个探针
------------------
G3 实测 20/20 局 `max_stage=0(no_contact)`、`min_dist_box_to_finger` 中位数 0.30 m。
**光看这个数字不能下任何结论**：0.30 m 可能是「模型完全没动臂」（= 接口坏了），
也可能是「模型动了臂但根本没朝方块去」（= zero-shot 能力/定标问题）。
两者的下一步动作完全不同（前者要修接线，后者要 SFT/统计量）。

本探针给出**同一批 seed 的零假设**：把 `physics.data.ctrl` 钉在 `START_ARM_POSE`
（就是 `sim.py:113-114` reset 时写入的那一份）**保持 300 个控制步**，
量同一套距离判据。于是每个 seed 上有三个可比的数：
    d_at_reset   起手时 手指↔方块 距离
    d_min_hold   「什么都不做」整局能达到的最小距离（= 零假设，含物理沉降）
    d_min_policy G3 实跑里 π₀.₅ 的最小距离（从 summary_pi05.json 读，不重跑）
⇒ `d_min_policy - d_min_hold` **才是**「策略带来的净接近量」。

纪律
----
- 距离判据**复用** G3 评测脚本里的同一个 `SceneProbe`（`import`，不另写一套），
  避免"两个探针两种口径"（D 反复点名的跨口径并列问题）。
- 快路径（直接 `physics.step()`，跳过 gym 的 3 路渲染）**必须**先与慢路径
  （`env.step()`）在 `--validate-n` 个 seed 上对齐，超差 ⇒ **响亮失败、不产出报告**
  （同 G0.5 的 liveness 教训）。
- 全程 **CPU-only**（`CUDA_VISIBLE_DEVICES=""`），不占卡、不需要申报。
- 可达包络是**算术**：用 G3 实测的 π₀.₅ 原始输出幅值 `raw_absmax` 与各关节
  `ctrlrange` 求交集占比。**它不是"任务可解性"的结论**，只说明在这种输出尺度下
  绝对关节目标能覆盖各关节行程的多少。

用法：
  CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl python scripts/a2_g3_approach_baseline.py \
      --n 20 --seed0 1000 --summary runs/vla/a2_pi05_zeroshot_20260929/summary_pi05.json \
      --out runs/vla/a2_pi05_zeroshot_20260929/approach_baseline.json
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import sys
import time
from datetime import datetime

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from a2_pi05_zeroshot_eval import (  # noqa: E402
    LEFT_FINGERS, RIGHT_FINGERS, SceneProbe, dist,
)


def load_snapshot() -> dict:
    out = {"ts": datetime.now().astimezone().isoformat(timespec="seconds")}
    try:
        out["loadavg"] = [float(x) for x in pathlib.Path("/proc/loadavg").read_text().split()[:3]]
    except Exception as exc:  # noqa: BLE001
        out["loadavg_error"] = str(exc)
    # cgroup v2 是 /sys/fs/cgroup/cpu.stat，v1 是 /sys/fs/cgroup/cpu/cpu.stat（本机是 v1）
    # —— 与 `scripts/a2_pi05_zeroshot_eval.py:67` 同一口径，不另造读法
    txt = ""
    for cand in ("/sys/fs/cgroup/cpu.stat", "/sys/fs/cgroup/cpu/cpu.stat"):
        try:
            txt = pathlib.Path(cand).read_text()
            out["cpu_stat_path"] = cand
            break
        except Exception:  # noqa: BLE001
            continue
    if not txt:
        out["cpu_stat_error"] = "neither /sys/fs/cgroup/cpu.stat nor /sys/fs/cgroup/cpu/cpu.stat readable"
    else:
        stat = {}
        for line in txt.splitlines():
            k, _, v = line.partition(" ")
            try:
                stat[k] = int(v)
            except ValueError:
                continue
        out["cpu_stat"] = {k: stat[k] for k in ("nr_periods", "nr_throttled") if k in stat}
    return out


def hold_action_14d(constants) -> list[float]:
    """把 `START_ARM_POSE` 反解成 gym-aloha 的 14 维动作（慢路径校验用）。

    `sim.py:38-55`：arm 维原样透传，夹爪维是**归一化**值，
    经 `unnormalize_puppet_gripper_position(x) = x*(OPEN-CLOSE)+CLOSE` 还原成 ctrl。
    """
    start = list(constants.START_ARM_POSE)
    close = constants.PUPPET_GRIPPER_POSITION_CLOSE
    open_ = constants.PUPPET_GRIPPER_POSITION_OPEN
    finger_ctrl = start[6]                      # 左夹爪第一根手指的 ctrl 值
    if not (open_ - close):
        raise RuntimeError("PUPPET_GRIPPER_POSITION_OPEN == CLOSE ⇒ 无法反解夹爪归一化值")
    norm = (finger_ctrl - close) / (open_ - close)
    act = start[0:6] + [norm] + start[8:14] + [norm]
    if len(act) != 14:
        raise RuntimeError(f"hold action 维度 {len(act)} != 14")
    return [float(x) for x in act]


def run_hold(probe, physics, ctrl_hold, n_control_steps, n_sub):
    """快路径：钉住 ctrl，推进 n_control_steps × n_sub 个物理步，逐步量距离。"""
    import numpy as np

    q0 = np.asarray(physics.data.qpos[:16], dtype="float64").copy()
    box_z0 = float(physics.data.qpos[-7:-4][2])
    d_left_min = d_right_min = 1e9
    box_z_max = -1e9
    touched = False
    for _ in range(n_control_steps):
        physics.data.ctrl[:] = ctrl_hold
        for _ in range(n_sub):
            physics.step()
        s = probe.sample()
        d_left_min = min(d_left_min, dist(s["box_xyz"], probe.gripper_xpos(LEFT_FINGERS[0])))
        d_right_min = min(d_right_min, dist(s["box_xyz"], probe.gripper_xpos(RIGHT_FINGERS[0])))
        box_z_max = max(box_z_max, s["box_xyz"][2])
        touched = touched or s["touch_left"] or s["touch_right"]
    q1 = np.asarray(physics.data.qpos[:16], dtype="float64")
    box_z1 = float(physics.data.qpos[-7:-4][2])
    liveness = {
        "qpos_max_abs_delta": float(abs(q1 - q0).max()),
        "box_z_start": round(box_z0, 6), "box_z_end": round(box_z1, 6),
        "box_z_delta": round(box_z1 - box_z0, 6),
        "advanced": bool(abs(q1 - q0).max() > 1e-9 or abs(box_z1 - box_z0) > 1e-9),
    }
    return {"min_dist_left": d_left_min, "min_dist_right": d_right_min,
            "box_z_max": box_z_max, "any_contact": touched, "liveness": liveness}


def run_hold_slow(env, probe, action14, n_control_steps):
    """慢路径：走 gym 的 `env.step()`（含渲染 + `before_step` 动作映射）。"""
    import numpy as np

    d_left_min = d_right_min = 1e9
    box_z_max = -1e9
    touched = False
    max_reward = 0.0
    for _ in range(n_control_steps):
        _obs, reward, term, trunc, _info = env.step(np.asarray(action14, dtype="float32"))
        max_reward = max(max_reward, float(reward))
        s = probe.sample()
        d_left_min = min(d_left_min, dist(s["box_xyz"], probe.gripper_xpos(LEFT_FINGERS[0])))
        d_right_min = min(d_right_min, dist(s["box_xyz"], probe.gripper_xpos(RIGHT_FINGERS[0])))
        box_z_max = max(box_z_max, s["box_xyz"][2])
        touched = touched or s["touch_left"] or s["touch_right"]
        if term or trunc:
            break
    return {"min_dist_left": d_left_min, "min_dist_right": d_right_min,
            "box_z_max": box_z_max, "any_contact": touched, "max_reward": max_reward}


def reachable_envelope(ctrlrange, raw_absmax, arm_idx):
    """算术：|a| ≤ raw_absmax 的绝对关节目标能覆盖各关节行程的比例。"""
    rows = []
    for i in arm_idx:
        lo, hi = float(ctrlrange[i][0]), float(ctrlrange[i][1])
        span = hi - lo
        c_lo, c_hi = max(lo, -raw_absmax), min(hi, raw_absmax)
        covered = max(0.0, c_hi - c_lo)
        rows.append({"actuator": i, "ctrlrange": [lo, hi], "span_rad": round(span, 4),
                     "covered_rad": round(covered, 4),
                     "covered_fraction": round(covered / span, 4) if span > 0 else None})
    fr = [r["covered_fraction"] for r in rows if r["covered_fraction"] is not None]
    return rows, (round(sum(fr) / len(fr), 4) if fr else None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--max-steps", type=int, default=300)
    ap.add_argument("--validate-n", type=int, default=2, help="前 N 个 seed 走慢路径交叉校验快路径")
    ap.add_argument("--tol-m", type=float, default=0.005, help="快/慢路径距离差容忍（m），超差即失败")
    ap.add_argument("--env-id", default="gym_aloha/AlohaTransferCube-v0")
    ap.add_argument("--summary", action="append", default=[],
                    help="G3 的 summary_*.json（可多次），用于逐 seed 比对；box_start 不一致即失败")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import numpy as np
    import gymnasium as gym
    import gym_aloha  # noqa: F401
    from gym_aloha import constants as C

    rep = {"probe": "a2_g3_approach_baseline", "purpose": "no-op hold null for G3 min-distance",
           "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "generator": "scripts/a2_g3_approach_baseline.py", "args": vars(args),
           "morphology": "aloha_bimanual_14d", "env_id": args.env_id,
           "python": sys.version.split()[0], "platform": platform.platform(),
           "mujoco_gl": os.environ.get("MUJOCO_GL"),
           "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
           "control_dt": C.DT, "load_before": load_snapshot()}

    env = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    inner = env.unwrapped._env
    n_sub = int(round(inner.control_timestep() / inner.physics.timestep()))
    rep["n_substeps_per_control_step"] = n_sub
    rep["control_timestep_s"] = float(inner.control_timestep())
    rep["physics_timestep_s"] = float(inner.physics.timestep())
    ctrl_hold = np.asarray(C.START_ARM_POSE, dtype="float64")
    act_hold = hold_action_14d(C)
    rep["hold_ctrl_16d"] = [float(x) for x in ctrl_hold]
    rep["hold_action_14d"] = [round(x, 6) for x in act_hold]
    lo = np.asarray(inner.physics.model.actuator_ctrlrange[:, 0], dtype="float64")
    hi = np.asarray(inner.physics.model.actuator_ctrlrange[:, 1], dtype="float64")

    summaries = {}
    for path in args.summary:
        p = pathlib.Path(path)
        if not p.exists():
            print(f"[warn] summary 不存在，跳过：{p}", flush=True)
            continue
        d = json.loads(p.read_text())
        summaries[p.stem] = {"path": str(p), "episodes": {e["seed"]: e for e in d["summary"]["episodes"]},
                             "action_adapter": d["summary"].get("action_adapter")}
    rep["summaries_used"] = [v["path"] for v in summaries.values()]

    per_seed, validations, t_all0 = [], [], time.perf_counter()
    for k in range(args.n):
        seed = args.seed0 + k
        t0 = time.perf_counter()
        obs, _info = env.reset(seed=seed)
        physics = env.unwrapped._env.physics
        probe = SceneProbe(physics)
        s0 = probe.sample()
        d_left0 = dist(s0["box_xyz"], probe.gripper_xpos(LEFT_FINGERS[0]))
        d_right0 = dist(s0["box_xyz"], probe.gripper_xpos(RIGHT_FINGERS[0]))
        box_start = [round(x, 4) for x in s0["box_xyz"]]

        fast = run_hold(probe, physics, ctrl_hold, args.max_steps, n_sub)

        rec = {"seed": seed, "box_start_xyz": box_start,
               "d_left_at_reset_m": round(d_left0, 4), "d_right_at_reset_m": round(d_right0, 4),
               "hold_fast": {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                             for kk, vv in fast.items() if kk != "liveness"},
               "hold_liveness": fast["liveness"],
               "wall_s": round(time.perf_counter() - t0, 2)}

        if not fast["liveness"]["advanced"]:
            raise RuntimeError(f"seed={seed} 快路径物理**没有推进**（qpos 与 box_z 都没变）"
                               " ⇒ 零假设无效，停下不产出报告（G0.5 liveness 教训）")

        if k < args.validate_n:
            env.reset(seed=seed)
            probe2 = SceneProbe(env.unwrapped._env.physics)
            t1 = time.perf_counter()
            slow = run_hold_slow(env, probe2, act_hold, args.max_steps)
            slow_wall = time.perf_counter() - t1
            dl = abs(slow["min_dist_left"] - fast["min_dist_left"])
            dr = abs(slow["min_dist_right"] - fast["min_dist_right"])
            ok = dl <= args.tol_m and dr <= args.tol_m
            validations.append({"seed": seed, "fast_min_dist_left": round(fast["min_dist_left"], 4),
                                "slow_min_dist_left": round(slow["min_dist_left"], 4),
                                "fast_min_dist_right": round(fast["min_dist_right"], 4),
                                "slow_min_dist_right": round(slow["min_dist_right"], 4),
                                "abs_diff_left_m": round(dl, 6), "abs_diff_right_m": round(dr, 6),
                                "tol_m": args.tol_m, "agree": bool(ok),
                                "slow_wall_s": round(slow_wall, 2), "fast_wall_s": rec["wall_s"],
                                "slow_max_reward": slow["max_reward"]})
            if not ok:
                raise RuntimeError(f"seed={seed} 快/慢路径不一致（Δleft={dl:.4f} m, Δright={dr:.4f} m > "
                                   f"{args.tol_m} m）⇒ 快路径零假设不可信，停下不产出报告")

        # 逐 seed 与 G3 实跑比对；box_start 必须一致（否则 seed 没对齐，比对无效）
        rec["policy_compare"] = {}
        for name, sm in summaries.items():
            e = sm["episodes"].get(seed)
            if e is None:
                continue
            same_box = max(abs(a - b) for a, b in zip(e["box_start_xyz"], box_start)) <= 1e-3
            if not same_box:
                raise RuntimeError(f"seed={seed} box_start 与 {name} 不一致："
                                   f"{e['box_start_xyz']} vs {box_start} ⇒ seed 未对齐，比对无效")
            rec["policy_compare"][name] = {
                "box_start_matches": True,
                "d_min_policy_left_m": e["min_dist_box_to_left_finger_m"],
                "d_min_policy_right_m": e["min_dist_box_to_right_finger_m"],
                "d_min_hold_left_m": round(fast["min_dist_left"], 4),
                "d_min_hold_right_m": round(fast["min_dist_right"], 4),
                "net_approach_left_m": round(fast["min_dist_left"] - e["min_dist_box_to_left_finger_m"], 4),
                "net_approach_right_m": round(fast["min_dist_right"] - e["min_dist_box_to_right_finger_m"], 4),
                "policy_max_stage": e["max_stage"], "policy_env_success": e["env_success"],
                "hold_any_contact": fast["any_contact"],
            }
        per_seed.append(rec)
        print(f"[seed {seed}] d_reset L/R={d_left0:.3f}/{d_right0:.3f} "
              f"d_min_hold L/R={fast['min_dist_left']:.3f}/{fast['min_dist_right']:.3f} "
              f"contact={fast['any_contact']} box_z {fast['liveness']['box_z_start']:.4f}->"
              f"{fast['liveness']['box_z_end']:.4f} wall={rec['wall_s']}s", flush=True)

    total_wall = time.perf_counter() - t_all0

    def stats(vals):
        if not vals:
            return None
        v = sorted(vals)
        return {"min": round(v[0], 4), "median": round(v[len(v) // 2], 4), "max": round(v[-1], 4),
                "mean": round(sum(v) / len(v), 4), "n": len(v)}

    agg = {
        "n_seeds": len(per_seed),
        "d_left_at_reset": stats([r["d_left_at_reset_m"] for r in per_seed]),
        "d_right_at_reset": stats([r["d_right_at_reset_m"] for r in per_seed]),
        "d_min_hold_left": stats([r["hold_fast"]["min_dist_left"] for r in per_seed]),
        "d_min_hold_right": stats([r["hold_fast"]["min_dist_right"] for r in per_seed]),
        "hold_any_contact_count": sum(1 for r in per_seed if r["hold_fast"]["any_contact"]),
        "hold_box_z_max": stats([r["hold_fast"]["box_z_max"] for r in per_seed]),
        "total_wall_s": round(total_wall, 2),
    }
    for name in summaries:
        nl = [r["policy_compare"][name]["net_approach_left_m"] for r in per_seed if name in r["policy_compare"]]
        nr = [r["policy_compare"][name]["net_approach_right_m"] for r in per_seed if name in r["policy_compare"]]
        agg[f"net_approach_vs_hold[{name}]"] = {
            "left": stats(nl), "right": stats(nr),
            "seeds_where_policy_closer_than_hold_left": sum(1 for x in nl if x > 0),
            "seeds_where_policy_closer_than_hold_right": sum(1 for x in nr if x > 0),
            "n_compared": len(nl),
            "reading": ("net_approach = d_min_hold - d_min_policy > 0 ⇒ 策略比『什么都不做』更接近方块；"
                        "<= 0 ⇒ 策略没有带来净接近（臂在动，但不是朝方块去）。"),
        }
    rep["aggregate"] = agg
    rep["validations_fast_vs_slow"] = validations

    # 可达包络算术：需要 summary 里的 raw_absmax（π₀.₅ 原始输出幅值，实测）
    for name, sm in summaries.items():
        aa = sm.get("action_adapter") or {}
        raw_absmax = (aa.get("clip") or {}).get("raw_absmax")
        if not raw_absmax:
            continue
        arm_idx = list(range(0, 6)) + list(range(8, 14))
        rows, mean_cov = reachable_envelope([[float(a), float(b)] for a, b in zip(lo, hi)],
                                            float(raw_absmax), arm_idx)
        rep[f"reachable_envelope[{name}]"] = {
            "raw_absmax_from_g3": float(raw_absmax),
            "assumption": ("把 |action| ≤ raw_absmax 直接当作**绝对关节角(rad)**目标 ⇒ 与各关节 ctrlrange 求交。"
                           "这是**算术**，不是任务可解性结论；且 π₀.₅ 输出单位本身是 unknown（contract q3）。"),
            "per_joint": rows, "mean_covered_fraction": mean_cov,
        }

    rep["load_after"] = load_snapshot()
    ns = rep["load_before"].get("cpu_stat", {}).get("nr_throttled")
    ne = rep["load_after"].get("cpu_stat", {}).get("nr_throttled")
    rep["nr_throttled_delta_total"] = (ne - ns) if (ns is not None and ne is not None) else None
    rep["per_seed"] = per_seed
    rep["conclusion_guard"] = ("本产物只回答『策略相对零假设有没有净接近』与『输出尺度覆盖了多少关节行程』。"
                               "**不得**据此声称 π₀.₅ 的能力上下界，也**不得**把结论外推到 Piper/Cobot Magic。")

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"[written] {out}", flush=True)
    print(f"[done] seeds={agg['n_seeds']} hold_contact={agg['hold_any_contact_count']} "
          f"d_min_hold_left={agg['d_min_hold_left']} wall={agg['total_wall_s']}s", flush=True)
    env.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
