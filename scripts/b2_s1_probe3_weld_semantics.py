#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 / S1 前置探针 3：**weld 语义**查清（S1 通道的命门）。

probe2 的实测：把 `mocap_right` 阶跃 [0,-0.05,+0.05] 后，`vx300s_right/gripper_link` 的残差
**不收敛反而变大**（step1 0.0872 m → step50 0.1359 m）。这与 D §4 S1 设想的
「weld 负责解算」直接冲突 ⇒ 在写专家之前必须判明是下面哪一种：

  H1 `eq_ref` 是在 **qpos0（XML 位姿）** 上编译期捕获的，而 `initialize_robots` 把 mocap 设成了
     START_ARM_POSE 对应的位姿 ⇒ 复位后约束本身就带着一个**非零参考偏置**，一 step 就被拉走。
  H2 EE 模型 `nu=4`（只有 4 个夹爪 actuator，**臂关节无 actuator**）⇒ 整条臂只靠 weld 吊着，
     重力下产生**稳态下垂**（soft weld：solref="0.01 1"、solimp=".25 .25 0.001"）。
  H3 目标位姿超出可达域/撞关节限位或奇异 ⇒ 解算不到。

本探针**只做测量与判据**，不改 site-packages，不写专家。产物 `probe3.json`。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

_GL = "disable"
for i, a in enumerate(sys.argv):
    if a == "--gl" and i + 1 < len(sys.argv):
        _GL = sys.argv[i + 1]
if _GL != "disable":
    os.environ["MUJOCO_GL"] = _GL
else:
    os.environ.pop("MUJOCO_GL", None)

import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
CST = timezone(timedelta(hours=8))
GRIP = "vx300s_right/gripper_link"
BOX = np.array([0.15, 0.5, 0.05, 1.0, 0.0, 0.0, 0.0])


def now():
    return datetime.now(CST).isoformat(timespec="seconds")


def build(dt):
    from dm_control import mujoco as dm_mujoco
    from dm_control.rl import control
    import gym_aloha
    from gym_aloha.tasks.sim_end_effector import TransferCubeEndEffectorTask
    pkg = Path(gym_aloha.__file__).resolve().parent / "assets"

    class SeededEE(TransferCubeEndEffectorTask):
        def initialize_episode(self, physics):
            self.initialize_robots(physics)
            i = physics.model.name2id("red_box_joint", "joint")
            np.copyto(physics.data.qpos[i:i + 7], BOX)
            physics.forward()
            super(TransferCubeEndEffectorTask, self).initialize_episode(physics)

    ph = dm_mujoco.Physics.from_xml_path(str(pkg / "bimanual_viperx_end_effector_transfer_cube.xml"))
    env = control.Environment(ph, SeededEE(), float("inf"), control_timestep=dt,
                              n_sub_steps=None, flat_observation=False)
    return env


def act_from(ph, mpos_l=None, mquat_l=None, mpos_r=None, mquat_r=None, grip=0.099848):
    a = np.zeros(16)
    a[0:3] = ph.data.mocap_pos[0] if mpos_l is None else mpos_l
    a[3:7] = ph.data.mocap_quat[0] if mquat_l is None else mquat_l
    a[7] = grip
    a[8:11] = ph.data.mocap_pos[1] if mpos_r is None else mpos_r
    a[11:15] = ph.data.mocap_quat[1] if mquat_r is None else mquat_r
    a[15] = grip
    return a


def snap(ph):
    return {
        "mocap_pos": [[float(x) for x in ph.data.mocap_pos[i]] for i in range(2)],
        "mocap_quat": [[float(x) for x in ph.data.mocap_quat[i]] for i in range(2)],
        "grip_left": [float(x) for x in ph.named.data.xpos["vx300s_left/gripper_link"]],
        "grip_right": [float(x) for x in ph.named.data.xpos[GRIP]],
        "qpos_arm_left": [float(x) for x in ph.data.qpos[0:6]],
        "qpos_arm_right": [float(x) for x in ph.data.qpos[8:14]],
        "box": [float(x) for x in ph.named.data.xpos["box"]],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gl", default="disable")
    ap.add_argument("--dt", type=float, default=0.034)
    ap.add_argument("--out-dir", default="runs/vla/b2_sim_demo_bidir_20260930/probe")
    a = ap.parse_args()
    out = {"probe": "b2_s1_probe3_weld_semantics", "generated_at": now(), "argv": sys.argv[1:],
           "dt": a.dt, "hypotheses": ["H1 eq_ref 编译期偏置", "H2 无臂 actuator ⇒ 重力稳态下垂", "H3 不可达/限位"]}
    try:
        env = build(a.dt)
        ph = env.physics
        m = ph.model
        # ---- 约束静态事实 ----
        out["constraints"] = {
            "neq": int(m.neq),
            "eq_type": [int(x) for x in m.eq_type],
            "eq_obj1_names": [m.id2name(int(m.eq_obj1id[i]), "body") for i in range(m.neq)],
            "eq_obj2_names": [m.id2name(int(m.eq_obj2id[i]), "body") for i in range(m.neq)],
            "eq_data_row0": [float(x) for x in m.eq_data[0]],
            "eq_data_row1": [float(x) for x in m.eq_data[1]],
            "eq_ref_row0": [float(x) for x in getattr(m, "eq_ref", np.zeros((m.neq, 7)))[0]] if hasattr(m, "eq_ref") else "no_attr",
            "eq_ref_row1": [float(x) for x in getattr(m, "eq_ref", np.zeros((m.neq, 7)))[1]] if hasattr(m, "eq_ref") else "no_attr",
            "eq_solref": [[float(x) for x in m.eq_solref[i]] for i in range(m.neq)],
            "eq_solimp": [[float(x) for x in m.eq_solimp[i]] for i in range(m.neq)],
            "nu": int(m.nu),
            "actuator_names": [m.id2name(i, "actuator") for i in range(m.nu)],
            "data_eq_active_after_reset": None,
            "interpretation": ("eq_data[0] 的前 7 位若 = [-1,0,0,0,0,0,0] 则表示 relpose 未指定；"
                               "MuJoCo 在 **data.eq_ref** 里放运行时/编译期捕获的参考相对位姿。"),
        }
        ts = env.reset()
        out["constraints"]["data_eq_ref_row0"] = [float(x) for x in ph.data.eq_ref[0]] if hasattr(ph.data, "eq_ref") else "no_attr"
        out["constraints"]["data_eq_ref_row1"] = [float(x) for x in ph.data.eq_ref[1]] if hasattr(ph.data, "eq_ref") else "no_attr"
        out["constraints"]["data_eq_active"] = [int(x) for x in ph.data.eq_active] if hasattr(ph.data, "eq_active") else "no_attr"
        s0 = snap(ph)
        out["after_reset"] = s0
        out["after_reset"]["grip_right_minus_mocap_right"] = [
            float(x - y) for x, y in zip(s0["grip_right"], s0["mocap_pos"][1])]
        out["after_reset"]["qpos0_arm_left"] = [float(x) for x in ph.model.qpos0[0:6]]
        out["after_reset"]["qpos0_arm_right"] = [float(x) for x in ph.model.qpos0[8:14]]
        # 编译期 qpos0 下 gripper_link 相对 mocap 的位姿（H1 的关键数字）
        import mujoco
        d0 = mujoco.MjData(ph.model.ptr)
        mujoco.mj_kinematics(ph.model.ptr, d0)
        gid = ph.model.name2id("vx300s_right/gripper_link", "body")
        mid = ph.model.name2id("mocap_right", "body")
        out["qpos0_kinematics"] = {
            "cmd": "mujoco.mj_kinematics(model, MjData()) 在 **qpos0**（未 reset、未 initialize_robots）下前向",
            "grip_right_xpos_at_qpos0": [float(x) for x in d0.xpos[gid]],
            "mocap_right_xpos_at_qpos0": [float(x) for x in d0.xpos[mid]],
            "grip_minus_mocap_at_qpos0": [float(x - y) for x, y in zip(d0.xpos[gid], d0.xpos[mid])],
            "arm_qpos0_left": [float(x) for x in ph.model.qpos0[0:6]],
        }

        # ---- 实验 1：HOLD（不动 mocap），看纯重力/参考偏置导致的漂移 ----
        hold = []
        for i in range(60):
            env.step(act_from(ph))
            cur = np.asarray(ph.named.data.xpos[GRIP], dtype=float).copy()
            tgt = np.asarray(ph.data.mocap_pos[1], dtype=float).copy()
            hold.append({"step": i + 1, "residual_to_mocap_m": round(float(np.linalg.norm(cur - tgt)), 6),
                         "grip_right": [round(float(x), 5) for x in cur],
                         "drift_from_reset_m": round(float(np.linalg.norm(cur - np.asarray(s0["grip_right"]))), 6),
                         "arm_right_qpos": [round(float(x), 4) for x in ph.data.qpos[8:14]]})
        out["exp1_hold_mocap"] = {"n_steps": 60, "curve": hold[::6] + [hold[-1]],
                                  "final_residual_to_mocap_m": hold[-1]["residual_to_mocap_m"],
                                  "final_drift_from_reset_m": hold[-1]["drift_from_reset_m"]}

        # ---- 实验 2：小增量（每步 2 mm）连续移动，看是否跟得上 ----
        env.reset()
        s0b = snap(ph)
        base = np.asarray(ph.data.mocap_pos[1], dtype=float).copy()
        inc = []
        for i in range(50):
            tgt = base + np.array([0.0, -0.002 * i, 0.002 * i])
            env.step(act_from(ph, mpos_r=tgt))
            cur = np.asarray(ph.named.data.xpos[GRIP], dtype=float).copy()
            if (i + 1) % 10 == 0 or i == 0:
                inc.append({"step": i + 1, "target": [round(float(x), 5) for x in tgt],
                            "actual": [round(float(x), 5) for x in cur],
                            "residual_m": round(float(np.linalg.norm(cur - tgt)), 6)})
        out["exp2_incremental_2mm_per_step"] = {"total_commanded_m": 0.1, "curve": inc}

        # ---- 实验 3：把 arm qpos 也一起"喂"进去（EE 通道不行时的退路：直接设 qpos + mocap 一致） ----
        env.reset()
        env.step(act_from(ph))
        out["exp3_qpos_write_then_step"] = {
            "note": "若 weld 参考偏置是根因，则「reset 后把 mocap 设成 grip_link 当前位姿 + 期望增量」应与 H1 的偏置无关；"
                    "exp1/exp2 的数字用来判 H1/H2/H3，本条只是留退路证据。",
            "grip_right_after_reset": s0b["grip_right"],
            "mocap_right_after_reset": s0b["mocap_pos"][1],
        }
        # ---- 实验 4：关节限位是否被撞到（H3） ----
        jl = ph.model.jnt_range[0:14]
        out["exp4_joint_limits"] = {
            "jnt_range_arm_left": [[float(x) for x in jl[i]] for i in range(6)],
            "jnt_range_arm_right": [[float(x) for x in jl[8 + i]] for i in range(6)],
            "arm_right_qpos_after_hold": [round(float(x), 4) for x in ph.data.qpos[8:14]],
            "at_limit_count": int(sum(1 for i in range(8, 14)
                                      if jl[i][1] > jl[i][0] and (ph.data.qpos[i] <= jl[i][0] + 1e-4 or ph.data.qpos[i] >= jl[i][1] - 1e-4))),
        }
    except Exception:
        out["error"] = traceback.format_exc(limit=10)

    od = REPO / a.out_dir
    od.mkdir(parents=True, exist_ok=True)
    p = od / "probe3.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[b2-s1-probe3] wrote {p} ({p.stat().st_size} bytes) at {now()}")
    c = out.get("constraints", {})
    print("  neq=", c.get("neq"), "eq_type=", c.get("eq_type"), "nu=", c.get("nu"), "actuators=", c.get("actuator_names"))
    print("  eq_data_row1=", c.get("eq_data_row1"))
    print("  data_eq_ref_row1=", c.get("data_eq_ref_row1"))
    print("  qpos0_kin=", json.dumps(out.get("qpos0_kinematics", {}), ensure_ascii=False)[:400])
    print("  exp1 final:", json.dumps(out.get("exp1_hold_mocap", {}).get("curve", [])[-3:], ensure_ascii=False))
    print("  exp2 curve:", json.dumps(out.get("exp2_incremental_2mm_per_step", {}).get("curve", []), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
