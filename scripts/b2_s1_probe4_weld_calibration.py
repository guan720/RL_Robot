#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 / S1 前置探针 4：**weld 标定 + 零瞬变初始化 + 真抓取**（S1 通道成立与否的决定性一测）。

probe2/probe3 已确立的事实
------------------------
1. `grip_xpos ≈ mocap_pos + R_grip · eq_data[i][3:6]`（`eq_data[3:6]` = 编译期在 **qpos0** 上
   捕获的 anchor2；左 = `-0.134706`、右 = `+0.134706`，镜像）。
   解析预测 vs probe2 实测：左 (-0.4517,0.500,0.2973) vs (-0.45142,0.49990,0.29592) ⇒ 相符。
2. `initialize_robots`（上游 `sim_end_effector.py:56`–`:81`）把 mocap 设成**等于**复位后的
   `gripper_link` 位姿 ⇒ **与 weld 参考不一致，差 0.1347 m** ⇒ 第一次 step 起臂被猛拉 13.5 cm。
   ⇒ 直接照上游写法驱动 = 开局一个 4 m/s 级的暴力瞬变（会撞方块、会甩出奇怪构型）。
3. `vx300s_right` 基座 `euler="0 0 3.1416"`（`assets/vx300s_right.xml:3`），左臂无 ⇒ 右臂坐标系
   绕 z 转了 180°，`eq_data[6:10]` 的相对四元数左右不同，**必须按臂分别标定**。
4. EE 模型 `nu=4`（只有 4 个夹爪 actuator，臂关节无 actuator）⇒ 整条臂只由 weld 吊着。
5. 方块 `sample_box_pose` 生成在 z=0.05，落地后稳定在 **z≈0.02**（桌面 z=0，方块半高 0.02）。

本探针要判的四件事（每件都带数字，不给"看起来对"）
--------------------------------------------------
E1 复位姿态几何（**未 step**）：两臂 gripper_link / 双指 geom / 指尖中点 / 桌面 / 方块。
E2 **零瞬变初始化**：按 E1+eq_data 反解出"与 weld 一致"的 mocap 写进去，再 step 30 次，
   残差必须 < 3 mm（否则 E3 的航点全部无意义）。
E3 **真抓取**：右臂 home → 方块上方 → 下降到指尖对准方块中心 → 合爪 → 抬升 12 cm，
   判据 = 接触对含 (red_box, 右指 geom) **且** 方块 z 抬升 > 6 cm **且** 方块水平位移 < 5 cm。
E4 夹爪开度 vs normalized 值（4 cm 方块能不能张开到够）。

只读 site-packages；不写专家、不产数据集。产物 `probe4.json`。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "disable")
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
CST = timezone(timedelta(hours=8))


def now():
    return datetime.now(CST).isoformat(timespec="seconds")


def qmul(a, b):
    """(w,x,y,z) 四元数乘法。"""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ])


def qconj(a):
    return np.array([a[0], -a[1], -a[2], -a[3]])


def qrot(a, v):
    """用 (w,x,y,z) 四元数旋转向量。"""
    qv = np.array([0.0, v[0], v[1], v[2]])
    r = qmul(qmul(a, qv), qconj(a))
    return r[1:]


def build_env(dt: float, box_pose):
    from dm_control import mujoco as dm_mujoco
    from dm_control.rl import control
    import gym_aloha
    from gym_aloha.tasks.sim_end_effector import TransferCubeEndEffectorTask
    from dm_control.suite import base
    pkg = Path(gym_aloha.__file__).resolve().parent / "assets"
    bp = np.asarray(box_pose, dtype=float)

    class NoRenderSeededEE(TransferCubeEndEffectorTask):
        """① 方块位姿可注入（上游用无种子 `sample_box_pose()`）；② `get_observation` **不渲染**
        （上游每 step 渲 3 张 480×640 ⇒ probe1 实测 93.5 ms/step；专家只需要关节量）。"""

        def initialize_episode(self, physics):
            self.initialize_robots(physics)
            i = physics.model.name2id("red_box_joint", "joint")
            np.copyto(physics.data.qpos[i:i + 7], bp)
            physics.forward()
            base.Task.initialize_episode(self, physics)

        def get_observation(self, physics):
            obs = collections.OrderedDict()
            obs["qpos"] = self.get_qpos(physics)
            obs["qvel"] = self.get_qvel(physics)
            obs["env_state"] = physics.data.qpos.copy()[16:]
            obs["images"] = {}
            obs["mocap_pose_left"] = np.concatenate(
                [physics.data.mocap_pos[0], physics.data.mocap_quat[0]]).copy()
            obs["mocap_pose_right"] = np.concatenate(
                [physics.data.mocap_pos[1], physics.data.mocap_quat[1]]).copy()
            obs["gripper_ctrl"] = physics.data.ctrl.copy()
            return obs

    ph = dm_mujoco.Physics.from_xml_path(str(pkg / "bimanual_viperx_end_effector_transfer_cube.xml"))
    env = control.Environment(ph, NoRenderSeededEE(), float("inf"), control_timestep=dt,
                              n_sub_steps=None, flat_observation=False)
    return env


def weld_rows(ph):
    """从 model.eq_data 里把两条 weld 的 anchor2 / relpose 取出来，并**按 body 名认亲**（不按下标猜）。"""
    m = ph.model
    rows = {}
    for i in range(m.neq):
        b1 = m.id2name(int(m.eq_obj1id[i]), "body")
        b2 = m.id2name(int(m.eq_obj2id[i]), "body")
        d = np.asarray(m.eq_data[i], dtype=float)
        rows[b2] = {
            "eq_index": i, "body1_mocap": b1, "body2_gripper": b2,
            "anchor1_body1_frame": [float(x) for x in d[0:3]],
            "anchor2_body2_frame": [float(x) for x in d[3:6]],
            "relpose_quat_wxyz_raw": [float(x) for x in d[6:10]],
            "torquescale": float(d[10]),
            "solref": [float(x) for x in m.eq_solref[i]],
            "solimp": [float(x) for x in m.eq_solimp[i]],
        }
    return rows


def geom_snapshot(ph, side):
    d = {}
    grip = np.asarray(ph.named.data.xpos[f"vx300s_{side}/gripper_link"], dtype=float).copy()
    bid = ph.model.name2id(f"vx300s_{side}/gripper_link", "body")
    xq = np.asarray(ph.data.xquat[bid], dtype=float).copy()
    d["gripper_link_xpos"] = [float(x) for x in grip]
    d["gripper_link_xquat_wxyz"] = [float(x) for x in xq]
    tips = []
    for nm in (f"vx300s_{side}/10_left_gripper_finger", f"vx300s_{side}/10_right_gripper_finger"):
        gid = ph.model.name2id(nm, "geom")
        xp = np.asarray(ph.data.geom_xpos[gid], dtype=float).copy()
        d[nm] = [float(x) for x in xp]
        tips.append(xp)
    mid = (tips[0] + tips[1]) / 2.0
    d["fingertip_midpoint"] = [float(x) for x in mid]
    d["finger_spread_m"] = float(np.linalg.norm(tips[0] - tips[1]))
    d["tip_minus_grip_world"] = [float(x) for x in (mid - grip)]
    d["tip_minus_grip_gripframe"] = [float(x) for x in qrot(qconj(xq), mid - grip)]
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dt", type=float, default=0.034)
    ap.add_argument("--box-x", type=float, default=0.15)
    ap.add_argument("--box-y", type=float, default=0.5)
    ap.add_argument("--settle-steps", type=int, default=12)
    ap.add_argument("--out-dir", default="runs/vla/b2_sim_demo_bidir_20260930/probe")
    a = ap.parse_args()
    out = {"probe": "b2_s1_probe4_weld_calibration", "generated_at": now(), "argv": sys.argv[1:],
           "dt": a.dt, "box_pose_cmd": [a.box_x, a.box_y, 0.05, 1, 0, 0, 0]}
    try:
        box0 = np.array([a.box_x, a.box_y, 0.05, 1.0, 0.0, 0.0, 0.0])
        env = build_env(a.dt, box0)
        ph = env.physics
        env.reset()
        out["weld_rows"] = weld_rows(ph)

        # ---------------- E1 复位姿态几何（未 step） ----------------
        e1 = {"box_qpos7": [float(x) for x in ph.data.qpos[-7:]],
              "box_xpos": [float(x) for x in ph.named.data.xpos["box"]],
              "mocap_pos": [[float(x) for x in ph.data.mocap_pos[i]] for i in range(2)],
              "mocap_quat": [[float(x) for x in ph.data.mocap_quat[i]] for i in range(2)],
              "qpos16": [float(x) for x in ph.data.qpos[:16]]}
        for s in ("left", "right"):
            e1[s] = geom_snapshot(ph, s)
        out["E1_reset_geometry_no_step"] = e1

        # ---------------- 标定：解出 (mocap → grip) 的位姿映射 ----------------
        calib = {}
        for s, other in (("left", "right"), ("right", "left")):
            row = out["weld_rows"][f"vx300s_{s}/gripper_link"]
            anchor2 = np.array(row["anchor2_body2_frame"])
            qrel = np.array(row["relpose_quat_wxyz_raw"])
            grip_x = np.asarray(e1[s]["gripper_link_xpos"])
            grip_q = np.asarray(e1[s]["gripper_link_xquat_wxyz"])
            # 假设 A：grip = mocap + R_grip·anchor2，R_grip = R_mocap·R(qrel)
            pred_grip_A = np.asarray(e1[s]["mocap_pos"] if False else
                                     out["E1_reset_geometry_no_step"]["mocap_pos"][0 if s == "left" else 1]) + qrot(grip_q, anchor2)
            calib[s] = {
                "anchor2": [float(x) for x in anchor2],
                "qrel_raw_wxyz": [float(x) for x in qrel],
                "grip_pos_at_reset": [float(x) for x in grip_x],
                "grip_quat_at_reset": [float(x) for x in grip_q],
                "pred_grip_if_mocap_as_initialized": [float(x) for x in pred_grip_A],
                "pred_offset_norm_m": float(np.linalg.norm(pred_grip_A - grip_x)),
                "mocap_needed_for_reset_grip_pos": [float(x) for x in (grip_x - qrot(grip_q, anchor2))],
                "mocap_needed_for_reset_grip_quat": [float(x) for x in qmul(grip_q, qconj(qrel))],
            }
        out["calibration_analytic"] = calib

        # ---------------- E2 零瞬变初始化 ----------------
        # 用 E1 的复位姿态反解 mocap，直接写进 data（mocap 体的位姿就是 qpos 的一部分），
        # 然后 step 30 次**保持同一目标**，看两臂是否原地不动。
        for s, i in (("left", 0), ("right", 1)):
            np.copyto(ph.data.mocap_pos[i], np.array(calib[s]["mocap_needed_for_reset_grip_pos"]))
            np.copyto(ph.data.mocap_quat[i], np.array(calib[s]["mocap_needed_for_reset_grip_quat"]))
        ph.forward()
        home = {s: np.asarray(ph.named.data.xpos[f"vx300s_{s}/gripper_link"], dtype=float).copy()
                for s in ("left", "right")}
        home_q = {s: np.asarray(ph.data.xquat[ph.model.name2id(f"vx300s_{s}/gripper_link", "body")],
                                dtype=float).copy() for s in ("left", "right")}
        hold = []
        for k in range(30):
            act = np.zeros(16)
            act[0:3] = ph.data.mocap_pos[0]; act[3:7] = ph.data.mocap_quat[0]; act[7] = 0.099848
            act[8:11] = ph.data.mocap_pos[1]; act[11:15] = ph.data.mocap_quat[1]; act[15] = 0.099848
            env.step(act)
            if k in (0, 1, 4, 9, 19, 29):
                rec = {"step": k + 1}
                for s in ("left", "right"):
                    cur = np.asarray(ph.named.data.xpos[f"vx300s_{s}/gripper_link"], dtype=float)
                    cq = np.asarray(ph.data.xquat[ph.model.name2id(f"vx300s_{s}/gripper_link", "body")], dtype=float)
                    rec[f"{s}_pos_residual_m"] = round(float(np.linalg.norm(cur - home[s])), 6)
                    rec[f"{s}_quat_angle_residual_rad"] = round(float(2 * np.arccos(min(1.0, abs(float(np.dot(cq, home_q[s])))))), 6)
                rec["box_z"] = round(float(ph.named.data.xpos["box"][2]), 6)
                hold.append(rec)
        out["E2_zero_transient_init"] = {
            "method": "按 calibration_analytic 反解 mocap，reset 后**直接写 data.mocap_pos/quat** 再 forward()",
            "curve": hold,
            "max_pos_residual_m": max(max(r[f"{s}_pos_residual_m"] for s in ("left", "right")) for r in hold),
            "criterion_lt_3mm": bool(max(max(r[f"{s}_pos_residual_m"] for s in ("left", "right")) for r in hold) < 3e-3),
            "box_z_final": hold[-1]["box_z"],
        }

        # ---------------- E4 夹爪开度 ----------------
        spread = {}
        for gv in (0.0, 0.25, 0.5, 0.75, 1.0):
            for _ in range(8):
                act = np.zeros(16)
                act[0:3] = ph.data.mocap_pos[0]; act[3:7] = ph.data.mocap_quat[0]; act[7] = gv
                act[8:11] = ph.data.mocap_pos[1]; act[11:15] = ph.data.mocap_quat[1]; act[15] = gv
                env.step(act)
            g = geom_snapshot(ph, "right")
            spread[str(gv)] = {"finger_spread_m": round(g["finger_spread_m"], 5),
                               "qpos6_left": round(float(ph.data.qpos[6]), 5),
                               "qpos14_right": round(float(ph.data.qpos[14]), 5),
                               "box_width_m": 0.04,
                               "spread_gt_box_width": bool(g["finger_spread_m"] > 0.04)}
        out["E4_gripper_spread"] = spread

        # ---------------- E3 真抓取（右臂，方块在右侧） ----------------
        # 目标：指尖中点落到方块中心 → 合爪 → 抬 12 cm
        s = "right"
        row = out["weld_rows"][f"vx300s_{s}/gripper_link"]
        anchor2 = np.array(row["anchor2_body2_frame"])
        qrel = np.array(row["relpose_quat_wxyz_raw"])
        # 让 box 落定
        for _ in range(a.settle_steps):
            act = np.zeros(16)
            act[0:3] = ph.data.mocap_pos[0]; act[3:7] = ph.data.mocap_quat[0]; act[7] = 1.0
            act[8:11] = ph.data.mocap_pos[1]; act[11:15] = ph.data.mocap_quat[1]; act[15] = 1.0
            env.step(act)
        box_c = np.asarray(ph.named.data.xpos["box"], dtype=float).copy()
        out["E3_box_after_settle"] = {"box_center": [float(x) for x in box_c], "settle_steps": a.settle_steps}
        g0 = geom_snapshot(ph, s)
        tip_rel_gripframe = np.array(g0["tip_minus_grip_gripframe"])
        q_des = np.array(g0["gripper_link_xquat_wxyz"])   # 保持复位朝向（下游一致）
        out["E3_tip_offset"] = {"tip_rel_gripframe": [float(x) for x in tip_rel_gripframe],
                                "tip_rel_world_at_home": [float(x) for x in g0["tip_minus_grip_world"]],
                                "q_desired": [float(x) for x in q_des]}

        def mocap_for_tip(tip_target):
            grip_pos = tip_target - qrot(q_des, tip_rel_gripframe)
            mpos = grip_pos - qrot(q_des, anchor2)
            mquat = qmul(q_des, qconj(qrel))
            return mpos, mquat

        tip_home = np.asarray(g0["fingertip_midpoint"], dtype=float)
        waypoints = []
        above = box_c.copy(); above[2] = tip_home[2]          # 保持当前高度，先平移到方块正上方
        grasp = box_c.copy()                                   # 指尖到方块中心
        lift = box_c.copy(); lift[2] = box_c[2] + 0.12
        for tgt in (above, grasp, grasp, lift, lift):
            waypoints.append(tgt)
        trace = []
        # 逐段以每步 ≤4 mm 的速度插值（weld 是软约束，太快会掉队）
        cur_tip = tip_home.copy()
        for wi, tgt in enumerate(waypoints):
            grip_open = 1.0 if wi < 2 else (0.0 if wi == 2 else 0.0)
            n = max(1, int(np.ceil(np.linalg.norm(tgt - cur_tip) / 0.004)))
            n = min(n, 120)
            for j in range(1, n + 1):
                tip_cmd = cur_tip + (tgt - cur_tip) * (j / n)
                mpos, mquat = mocap_for_tip(tip_cmd)
                act = np.zeros(16)
                act[0:3] = ph.data.mocap_pos[0]; act[3:7] = ph.data.mocap_quat[0]; act[7] = 1.0
                act[8:11] = mpos; act[11:15] = mquat; act[15] = grip_open
                env.step(act)
                gt = geom_snapshot(ph, s)
                tip_now = np.asarray(gt["fingertip_midpoint"])
                trace.append({"wp": wi, "step_in_wp": j,
                              "tip_cmd": [round(float(x), 5) for x in tip_cmd],
                              "tip_now": [round(float(x), 5) for x in tip_now],
                              "residual_m": round(float(np.linalg.norm(tip_now - tip_cmd)), 5),
                              "box": [round(float(x), 5) for x in ph.named.data.xpos["box"]],
                              "spread": round(gt["finger_spread_m"], 5)})
            cur_tip = tgt.copy()
        # 合爪 + 抬升已在 waypoints 内；这里再补 10 步保持
        for _ in range(10):
            mpos, mquat = mocap_for_tip(lift)
            act = np.zeros(16)
            act[0:3] = ph.data.mocap_pos[0]; act[3:7] = ph.data.mocap_quat[0]; act[7] = 1.0
            act[8:11] = mpos; act[11:15] = mquat; act[15] = 0.0
            env.step(act)
        contacts = []
        for ci in range(ph.data.ncon):
            c = ph.data.contact[ci]
            n1 = ph.model.id2name(int(c.geom1), "geom")
            n2 = ph.model.id2name(int(c.geom2), "geom")
            if n1 and n2 and ("red_box" in (n1, n2)):
                contacts.append((n1, n2))
        box_end = np.asarray(ph.named.data.xpos["box"], dtype=float)
        gt = geom_snapshot(ph, s)
        tip_end = np.asarray(gt["fingertip_midpoint"])
        out["E3_grasp_attempt"] = {
            "trace_head": trace[:3] + trace[len(trace) // 2:len(trace) // 2 + 2] + trace[-4:],
            "n_trace": len(trace),
            "max_tip_residual_m": round(max(t["residual_m"] for t in trace), 5),
            "mean_tip_residual_m": round(float(np.mean([t["residual_m"] for t in trace])), 5),
            "box_center_after_settle": [float(x) for x in box_c],
            "box_center_final": [float(x) for x in box_end],
            "box_lift_dz_m": round(float(box_end[2] - box_c[2]), 5),
            "box_horizontal_drift_m": round(float(np.linalg.norm(box_end[:2] - box_c[:2])), 5),
            "contacts_with_box": [list(c) for c in sorted(set(contacts))],
            "tip_to_box_center_m": round(float(np.linalg.norm(tip_end - box_end)), 5),
            "verdict_grasped_and_lifted": bool(
                any("red_box" in c and "gripper_finger" in (c[0] + c[1]) for c in contacts)
                and (box_end[2] - box_c[2]) > 0.06
                and np.linalg.norm(box_end[:2] - box_c[:2]) < 0.05),
        }
    except Exception:
        out["error"] = traceback.format_exc(limit=12)

    od = REPO / a.out_dir
    od.mkdir(parents=True, exist_ok=True)
    p = od / "probe4.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[b2-s1-probe4] wrote {p} ({p.stat().st_size} bytes) at {now()}")
    for k in ("E2_zero_transient_init", "E3_grasp_attempt", "E4_gripper_spread"):
        v = out.get(k)
        if isinstance(v, dict):
            print(f"  {k}:", json.dumps({kk: vv for kk, vv in v.items()
                                          if kk in ("max_pos_residual_m", "criterion_lt_3mm", "box_z_final",
                                                    "max_tip_residual_m", "mean_tip_residual_m", "box_lift_dz_m",
                                                    "box_horizontal_drift_m", "tip_to_box_center_m",
                                                    "verdict_grasped_and_lifted", "contacts_with_box")},
                                         ensure_ascii=False))
    if "error" in out:
        print("  ERROR:", out["error"][-800:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
