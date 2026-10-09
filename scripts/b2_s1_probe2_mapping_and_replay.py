#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 / S1 前置探针 2：把 probe1 打出来的两个坑钉死（**14 维装配序** + **BOX_POSE 注入**）。

probe1 的两个实测结论（`runs/vla/b2_sim_demo_bidir_20260930/probe/probe.json`）
----------------------------------------------------------------------------
1. `joint_replay_box_left.box_spawn_matches_injection = false`：B2 先把 `BOX_POSE[0]` 写成
   左侧位姿，`AlohaEnv.reset()` 里 `env.py:159`–`:160` 又用 `sample_box_pose(seed)` 把它**覆盖回右侧**
   （`utils.py:5` 的 `x_range=[0.0, 0.2]` 恒为正）⇒ **反向任务不能靠"先写 BOX_POSE 再 reset"**。
2. `replay_tracking.max_abs_err_rad = 2.418`：不是跟踪误差，是 **B2 自己的索引映射写错了** ——
   `qpos[:14]` 的语义是 `[左臂6, 左夹爪指×2, 右臂前6]`，而动作/state 的 14 维是
   `[左臂6, 左夹爪 normalized×1, 右臂6, 右夹爪 normalized×1]`（`constants.JOINTS` /
   `sim.py:get_qpos`）⇒ 右臂整体错位一格。**这正是 RR-B2-09（装配顺序）预言的静默错位**，
   现在它有了一个实测数字：错位会让"跟踪误差"从 mm 级变成 **2.4 rad**（≈138°）。

本探针要产出的四个可核数字
------------------------
A. `mapping`：qpos16 ↔ state14 ↔ action14 的**逐索引**映射表（含夹爪归一化公式的实测复算）。
B. `replay_correct_mapping`：用**正确映射**回放 40 步的最大/均值跟踪误差（rad）。
C. `box_left_injection_bypass`：旁路 `AlohaEnv`、直接构造 `control.Environment(TransferCubeTask)`
   后，左侧方块注入是否逐位相符（反向任务的入口条件）。
D. `weld_convergence`：mocap 阶跃后 1/5/20/50 步的残差（决定专家航点的每步步长上限）。

只读 site-packages；频率口径用 `envs/gym_aloha_shim.py`（裁定 53）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

_GL = "osmesa"
for i, a in enumerate(sys.argv):
    if a == "--gl" and i + 1 < len(sys.argv):
        _GL = sys.argv[i + 1]
    elif a.startswith("--gl="):
        _GL = a.split("=", 1)[1]
if _GL != "disable":
    os.environ["MUJOCO_GL"] = _GL

import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
CST = timezone(timedelta(hours=8))


def now():
    return datetime.now(CST).isoformat(timespec="seconds")


def mapping_section() -> dict:
    """A：把 14 维装配序写成**可执行**的映射，并用上游函数复算（不是抄文档）。"""
    from gym_aloha.constants import (JOINTS, ACTIONS, PUPPET_GRIPPER_POSITION_CLOSE,
                                     PUPPET_GRIPPER_POSITION_OPEN, normalize_puppet_gripper_position)
    idx = {
        "state14_from_qpos": {
            "left_arm_joints": "qpos[0:6]",
            "left_gripper_normalized": "normalize_puppet_gripper_position(qpos[6])",
            "right_arm_joints": "qpos[8:14]",
            "right_gripper_normalized": "normalize_puppet_gripper_position(qpos[14])",
            "source": "gym_aloha/tasks/sim.py:61-69 get_qpos（B2 只读实读）",
        },
        "action14_consumed_by": {
            "left_arm_joints": "action[0:6]  -> position actuators（sim.py:39）",
            "left_gripper_normalized": "action[6]   -> unnormalize 后写 ctrl[0:2]=[g,-g]（sim.py:41,44,47）",
            "right_arm_joints": "action[7:13] -> position actuators（sim.py:40）",
            "right_gripper_normalized": "action[13]  -> unnormalize 后写 ctrl[2:4]=[g,-g]（sim.py:42,45,48）",
            "source": "gym_aloha/tasks/sim.py:38-53 before_step（B2 只读实读）",
        },
        "wrong_layout_used_in_probe1": "qpos[:14] = [左臂6, 左指 qpos[6], 左指 qpos[7]=-qpos[6], 右臂 qpos[8:13]] ⇒ 右臂错位一格",
        "JOINTS": JOINTS, "ACTIONS": ACTIONS,
        "JOINTS_equals_ACTIONS": JOINTS == ACTIONS,
        "gripper_norm_constants": {"PUPPET_CLOSE": PUPPET_GRIPPER_POSITION_CLOSE,
                                   "PUPPET_OPEN": PUPPET_GRIPPER_POSITION_OPEN},
    }
    # 复算：START_ARM_POSE 的夹爪指位 0.02239 归一化后应 == A2 契约里的 0.099848
    from gym_aloha.constants import START_ARM_POSE
    val = float(normalize_puppet_gripper_position(START_ARM_POSE[6]))
    idx["gripper_norm_recompute"] = {
        "input_qpos6": float(START_ARM_POSE[6]), "normalized": round(val, 6),
        "a2_contract_state_raw_14d_idx6": 0.099848,
        "matches_a2_contract_within_1e-6": bool(abs(val - 0.099848) < 1e-6),
        "cross_ref": "runs/vla/a2_pi05_contract_20260929/contract.json → observation.state_raw_14d[6]",
    }
    return idx


def _qpos16_to_state14(qpos16) -> np.ndarray:
    from gym_aloha.constants import normalize_puppet_gripper_position as nz
    q = np.asarray(qpos16, dtype=float)
    return np.concatenate([q[0:6], [nz(q[6])], q[8:14], [nz(q[14])]])


def _make_joint_env(dt: float):
    """旁路 AlohaEnv（理由见模块 docstring 的 C 条）：直接构造 dm_control Environment。"""
    from dm_control import mujoco as dm_mujoco
    from dm_control.rl import control
    import gym_aloha
    from gym_aloha.tasks.sim import TransferCubeTask
    pkg = Path(gym_aloha.__file__).resolve().parent / "assets"
    physics = dm_mujoco.Physics.from_xml_path(str(pkg / "bimanual_viperx_transfer_cube.xml"))
    task = TransferCubeTask()
    env = control.Environment(physics, task, float("inf"), control_timestep=dt,
                              n_sub_steps=None, flat_observation=False)
    return env


def replay_section(dt: float, seed: int) -> dict:
    """B + C：正确映射下的跟踪误差；左侧方块注入是否成立。"""
    from gym_aloha.tasks.sim import BOX_POSE
    from gym_aloha.utils import sample_box_pose
    out = {"dt": dt, "seed": seed}

    base = sample_box_pose(seed)
    left = base.copy()
    left[0] = -float(abs(base[0])) if abs(base[0]) > 1e-9 else -0.15
    out["sample_box_pose_ranges_readonly"] = {
        "x_range": [0.0, 0.2], "y_range": [0.4, 0.6], "z_range": [0.05, 0.05],
        "source": "gym_aloha/utils.py:5-7（恒为右侧 ⇒ 反向必须自采样）",
        "sampled_right": [float(x) for x in base], "mirrored_left": [float(x) for x in left],
    }

    for tag, pose in (("box_right", base), ("box_left", left)):
        BOX_POSE[0] = np.asarray(pose, dtype=float)
        env = _make_joint_env(dt)
        ts = env.reset()
        ph = env.physics
        got = np.asarray(ph.data.qpos[-7:], dtype=float).copy()
        rec = {
            "injected": [float(x) for x in pose],
            "after_reset_qpos_last7": [float(x) for x in got],
            "bitwise_equal": bool(np.array_equal(got, np.asarray(pose, dtype=float))),
            "allclose_atol1e-12": bool(np.allclose(got, pose, atol=1e-12)),
            "agent_pos_dim_from_obs": int(np.asarray(ts.observation["qpos"]).shape[0]),
        }
        # 正确映射下的回放：目标 = 当前 state14 的臂角做正弦摆动
        s0 = _qpos16_to_state14(ph.data.qpos[:16])
        errs, errs_grip = [], []
        for i in range(40):
            a = s0.copy()
            a[1] = s0[1] + 0.3 * np.sin(i / 8.0)
            a[8] = s0[8] + 0.3 * np.sin(i / 8.0)   # 右臂 shoulder（正确索引 = 7+1）
            a[6] = 0.5 + 0.5 * np.sin(i / 8.0) * 0.5 + 0.25
            ts = env.step(a.astype(np.float32))
            cur = _qpos16_to_state14(ph.data.qpos[:16])
            arm_idx = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12]
            errs.append(float(np.max(np.abs(cur[arm_idx] - a[arm_idx]))))
            errs_grip.append(float(abs(cur[6] - a[6])))
        rec["replay_correct_mapping"] = {
            "cmd": "40 步：action=state14 布局（左右 shoulder 正弦 ±0.3 rad），逐步用 get_qpos 口径读回比误差",
            "max_abs_err_arm_rad": round(float(np.max(errs)), 6),
            "mean_abs_err_arm_rad": round(float(np.mean(errs)), 6),
            "p95_abs_err_arm_rad": round(float(np.percentile(errs, 95)), 6),
            "last_err_arm_rad": round(float(errs[-1]), 6),
            "max_abs_err_left_gripper_normalized": round(float(np.max(errs_grip)), 6),
            "verdict_trackable_below_0p05rad": bool(float(np.max(errs)) < 0.05),
        }
        out[tag] = rec
    return out


def weld_convergence_section(dt: float, box_pose) -> dict:
    """D：mocap 阶跃后的残差曲线 ⇒ 决定专家航点的每步位移上限。"""
    from dm_control import mujoco as dm_mujoco
    from dm_control.rl import control
    import gym_aloha
    from gym_aloha.tasks.sim_end_effector import TransferCubeEndEffectorTask
    pkg = Path(gym_aloha.__file__).resolve().parent / "assets"
    bp = np.asarray(box_pose, dtype=float)

    class _SeededEE(TransferCubeEndEffectorTask):
        def initialize_episode(self, physics):
            self.initialize_robots(physics)
            i = physics.model.name2id("red_box_joint", "joint")
            np.copyto(physics.data.qpos[i:i + 7], bp)
            physics.forward()
            super(TransferCubeEndEffectorTask, self).initialize_episode(physics)

    physics = dm_mujoco.Physics.from_xml_path(str(pkg / "bimanual_viperx_end_effector_transfer_cube.xml"))
    env = control.Environment(physics, _SeededEE(), float("inf"), control_timestep=dt,
                              n_sub_steps=None, flat_observation=False)
    env.reset()
    ph = env.physics
    start = np.asarray(ph.data.mocap_pos[1], dtype=float).copy()
    delta = np.array([0.0, -0.05, 0.05])
    curve = []
    for step in range(1, 51):
        act = np.zeros(16)
        act[0:3] = ph.data.mocap_pos[0]
        act[3:7] = ph.data.mocap_quat[0]
        act[7] = 0.099848
        act[8:11] = start + delta
        act[11:15] = ph.data.mocap_quat[1]
        act[15] = 0.099848
        env.step(act)
        cur = np.asarray(ph.named.data.xpos["vx300s_right/gripper_link"], dtype=float).copy()
        err = float(np.linalg.norm(cur - (start + delta)))
        if step in (1, 2, 5, 10, 20, 30, 50):
            curve.append({"step": step, "t_s": round(step * dt, 4), "residual_norm_m": round(err, 6)})
    # 手指几何（抓取点标定）：用 geom 名（reward 函数用的就是 geom 名）
    geoms = {}
    # 实测 geom 名（`ph.model.id2name(i,'geom')` 枚举）：每侧有 **两个** 指 geom
    # `10_left_gripper_finger` / `10_right_gripper_finger`；上游 reward 只查
    # 左夹爪的 `10_left_gripper_finger` 与右夹爪的 `10_right_gripper_finger`（不对称，B2 照实记录）。
    for side in ("left", "right"):
        finger_names = [f"vx300s_{side}/10_left_gripper_finger",
                        f"vx300s_{side}/10_right_gripper_finger"]
        tips = []
        for nm in finger_names + [f"vx300s_{side}/9_gripper_bar", f"vx300s_{side}/7_gripper"]:
            try:
                gid = ph.model.name2id(nm, "geom")
            except Exception as e:  # noqa: BLE001
                geoms[nm] = f"name2id_error: {type(e).__name__}: {e}"
                continue
            xp = np.asarray(ph.data.geom_xpos[gid], dtype=float).copy()
            geoms[nm] = {"xpos": [float(x) for x in xp],
                         "z_axis": [float(x) for x in np.asarray(ph.data.geom_xmat[gid]).reshape(3, 3)[2]]}
            if nm in finger_names:
                tips.append(xp)
        gl = np.asarray(ph.named.data.xpos[f"vx300s_{side}/gripper_link"], dtype=float)
        geoms[f"vx300s_{side}/gripper_link(body)"] = {"xpos": [float(x) for x in gl]}
        if len(tips) == 2:
            mid = (tips[0] + tips[1]) / 2.0
            geoms[f"vx300s_{side}/fingertip_midpoint"] = {
                "xpos": [float(x) for x in mid],
                "minus_gripper_link": [float(a - b) for a, b in zip(mid, gl)],
                "finger_spread_m": float(np.linalg.norm(tips[0] - tips[1])),
                "note": "抓取点标定用：航点必须让 **fingertip_midpoint** 落到方块中心，不是让 gripper_link 落到方块中心",
            }
    # 夹爪开合的物理量：ctrl vs qpos[6] vs qpos[7]
    grip = {}
    for gv in (0.0, 0.5, 1.0):
        from gym_aloha.constants import unnormalize_puppet_gripper_position as unz
        act = np.zeros(16)
        act[0:3] = ph.data.mocap_pos[0]; act[3:7] = ph.data.mocap_quat[0]; act[7] = gv
        act[8:11] = ph.data.mocap_pos[1]; act[11:15] = ph.data.mocap_quat[1]; act[15] = gv
        for _ in range(10):
            env.step(act)
        grip[str(gv)] = {"ctrl4": [float(x) for x in ph.data.ctrl[:4]],
                         "qpos_left_finger": float(ph.data.qpos[6]),
                         "qpos_right_finger": float(ph.data.qpos[14]),
                         "state_left_gripper_normalized": float(
                             (ph.data.qpos[6] - 0.01844) / (0.058 - 0.01844)),
                         "unnormalized_target": float(unz(gv))}
    return {"dt": dt, "mocap_step_delta": [float(x) for x in delta],
            "residual_curve": curve,
            "residual_at_50_steps_m": curve[-1]["residual_norm_m"] if curve else None,
            "converged_within_2mm_by_step": (next((c["step"] for c in curve if c["residual_norm_m"] < 2e-3), None)),
            "finger_geom_positions": geoms,
            "gripper_open_close_physics": grip,
            "box_pose_used": [float(x) for x in bp],
            "box_xpos_after": [float(x) for x in ph.named.data.xpos["box"]]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gl", default="egl")
    ap.add_argument("--dt", type=float, default=0.034)
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--out-dir", default="runs/vla/b2_sim_demo_bidir_20260930/probe")
    a = ap.parse_args()
    out = {"probe": "b2_s1_probe2_mapping_and_replay", "generated_at": now(), "argv": sys.argv[1:],
           "supersedes": "probe.json 的 replay_tracking（映射错误）与 joint_replay_box_left（注入被覆盖）"}
    out["A_mapping"] = mapping_section()
    try:
        out["BC_replay_and_box_injection"] = replay_section(a.dt, a.seed)
    except Exception:
        out["BC_replay_and_box_injection"] = {"error": traceback.format_exc(limit=8)}
    try:
        out["D_weld_convergence"] = weld_convergence_section(a.dt, [0.15, 0.5, 0.05, 1, 0, 0, 0])
    except Exception:
        out["D_weld_convergence"] = {"error": traceback.format_exc(limit=8)}
    od = REPO / a.out_dir
    od.mkdir(parents=True, exist_ok=True)
    p = od / "probe2.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[b2-s1-probe2] wrote {p} ({p.stat().st_size} bytes) at {now()}")
    bc = out.get("BC_replay_and_box_injection", {})
    for k in ("box_right", "box_left"):
        if k in bc:
            print(f"  {k}: bitwise_equal={bc[k]['bitwise_equal']} replay={json.dumps(bc[k]['replay_correct_mapping'],ensure_ascii=False)[:220]}")
    dw = out.get("D_weld_convergence", {})
    print("  weld curve:", json.dumps(dw.get("residual_curve"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
