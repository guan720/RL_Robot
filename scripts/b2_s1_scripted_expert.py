#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 / S1：**主线仿真双向示范的脚本专家**（关节空间 Jacobian IK，在**部署 env 内**直接生成）。

为什么不是 D §4 S1 设想的「EE + mocap + weld」通道（B2 只读复核后的三处硬伤，均有实测）
------------------------------------------------------------------------------------
| # | D 的口径 | B2 只读实读/实测 | 证据 |
|---|---|---|---|
| 1 | 「`env.py:120`–`:124` 支持 `task="end_effector_transfer_cube"`，可直接构造 `AlohaEnv`」 | **不成立**：`:121` 第一行就是 `raise NotImplementedError()`，在 xml/physics/task 三行之前 | `probe/probe.json → files.env_py_ee_branch` |
| 2 | 「EE XML 含 2 处 `<equality>`」 | 精确说是 **1 个 `<equality>` 容器 + 2 个 `<weld>`**；关节空间版 0/0（结论方向成立，计数口径已更正） | `probe/probe.json → files.equality_weld_counts` |
| 3 | 「weld 负责解算」 | weld **确能**解算，但 `eq_data[3:6]` 里带一个编译期（qpos0）捕获的 **anchor2 = ±0.134706 m**（左右镜像），而上游 `initialize_robots` 把 mocap 设成**等于**复位后的 `gripper_link` 位姿 ⇒ **约束在复位瞬间就违反 0.1347 m** ⇒ 第一步起臂被猛拉 13.5 cm（≈4 m/s）。B2 按 `eq_data` 反解出"一致 mocap"后：**左臂零瞬变成立（30 步残差 ≤1.3 mm）**，**右臂不成立（残差 0.247 m、姿态偏 2.376 rad）**，根因是 `assets/vx300s_right.xml:3` 的 `euler="0 0 3.1416"`（右臂基座绕 z 装反 180°），使 `eq_data[6:10]` 的相对四元数左右不同、约定不统一 | `probe/probe4.json → E2_zero_transient_init`、`calibration_analytic`、`weld_rows` |

⇒ **改走等价但可控的路**：在**部署 env**（`bimanual_viperx_transfer_cube.xml`，即
`gym_aloha/AlohaTransferCube-v0` 的模型）内用 **Jacobian 阻尼最小二乘 IK** 直接生成 14 维
关节目标。好处（都是 S1 判据关心的）：
  * **无跨环境回放失配**：示范的 state/action/图像全部产自策略将要运行的同一个 env；
  * **无 weld 软约束下垂**：关节 env 是 position actuator（probe2 实测跟踪误差 max 0.028 rad）；
  * **反向任务只是把 x 镜像**，同一套代码同一套 θ 无关参数 ⇒ 与任务 3（T17 π₀.₅ 版）同构。

实测标定常数（**全部有出处，不猜**）
----------------------------------
* 指尖中点相对 `gripper_link` 的偏移（夹爪坐标系）= `(0.0935, 0.0, 0.0021)` m
  —— `probe/probe4.json → E1_reset_geometry_no_step.left.tip_minus_grip_gripframe`
  （右臂同值，因两臂夹爪 XML 相同、只是基座朝向不同）。
* 夹爪开度 vs normalized 值：0.0→1.83 cm、0.5→4.65 cm、1.0→**8.41 cm**（方块 4 cm）
  —— `probe/probe4.json → E4_gripper_spread`。⇒ 张开用 1.0、合爪用 0.0，余量 4.4 cm。
* 方块生成 z=0.05，落定后 z=**0.02**（桌面 z=0，方块半高 0.02）
  —— `probe/probe4.json → E3_box_after_settle`、`E2.box_z_final`。
* 14 维装配序（state 与 action **同序**）：`[左臂6, 左夹爪1, 右臂6, 右夹爪1]`
  —— `constants.JOINTS`/`ACTIONS` + `tasks/sim.py:38-53,61-69`；probe1 用错序（`qpos[:14]`）
  导致"跟踪误差 2.418 rad"，probe2 用对序后 = **0.028 rad**（RR-B2-09 的实测代价）。
* 频率：`DT=0.034` ⇒ **29.411765 Hz**、17 substeps、QC 区间 [29,31] 内
  —— `probe/probe.json → ee_env.live_timing`（活对象读数，不是常量）。

三值纪律：任何"成功/失败"判定都由 `SuccessJudge` 给 `success|failure|unknown` 三值 + 显式规则；
证据不足 ⇒ `unknown`，不填 0、不当通过。
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if "MUJOCO_GL" not in os.environ:
    os.environ["MUJOCO_GL"] = "disable"

import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CST = timezone(timedelta(hours=8))

# ---------------------------- 标定常数（出处见模块 docstring） ----------------------------
TIP_REL_GRIPFRAME = np.array([0.0935, 0.0, 0.0021])   # probe4 E1（左右同值）
GRIP_OPEN_NORM = 1.0        # 开度 8.41 cm（probe4 E4）
GRIP_CLOSE_NORM = 0.0       # 开度 1.83 cm
BOX_HALF = 0.02             # assets/bimanual_viperx_transfer_cube.xml: geom size="0.02 0.02 0.02"
TABLE_Z = 0.0               # scene.xml: table body pos="0 .6 0"，方块落定 z=0.02 = 半高
BOX_REST_Z = TABLE_Z + BOX_HALF
# **实测**：夹爪朝下张开、一路下降到手指 geom 刚碰桌面时，"指尖中点"的高度 = 左 0.060 / 右 0.059 m
# （`probe/pad_extent_calibration.json`，`calibrate_pad_extent()` 产出）⇒ 指尖中点**不是**最低接触点，
# 最低接触点在其下方 ~0.0595 m。B2 第一版按"指尖中点=方块中心"写死 `grasp_dz=0.02`，
# 等价于把手指插进桌面 2 cm ⇒ 实测方块被弹飞（`max_box_speed=1.7565 m/s`，相位 `place_lower`）。
PAD_EXTENT_M = 0.0595
FINGER_BOTTOM_CLEARANCE_M = 0.005
GRIP_START_NORM = 0.099848  # START_ARM_POSE 的夹爪指位 0.02239 归一化后（probe2 A_mapping 复算相符）
# 让夹爪"指尖朝下"的姿态：夹爪坐标系 +x 是指向（probe4 E1），要映到世界 -z ⇒ Ry(+90°)
Q_DOWN_WXYZ = np.array([np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0])
R_DOWN = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])  # Ry(90°)：x→-z, z→+x

ARM_DOF = {"left": list(range(0, 6)), "right": list(range(8, 14))}
GRIP_QPOS_IDX = {"left": 6, "right": 14}
GRIP_ACT_IDX = {"left": 6, "right": 13}
ARM_ACT_SLICE = {"left": slice(0, 6), "right": slice(7, 13)}
GRIP_LINK_BODY = {"left": "vx300s_left/gripper_link", "right": "vx300s_right/gripper_link"}
FINGER_GEOMS = {"left": ("vx300s_left/10_left_gripper_finger", "vx300s_left/10_right_gripper_finger"),
                "right": ("vx300s_right/10_left_gripper_finger", "vx300s_right/10_right_gripper_finger")}
# 上游 reward 只查这两个 geom（不对称，B2 照实记录）：sim.py:129-155 / sim_end_effector.py:171-172
REWARD_CHECKED_FINGER = {"left": "vx300s_left/10_left_gripper_finger",
                         "right": "vx300s_right/10_right_gripper_finger"}

SPAWN_RANGE = {"forward": ((0.0, 0.2), (0.4, 0.6)),    # 上游 utils.py:5-7（x 恒正 = 右侧）
               "reverse": ((-0.2, 0.0), (0.4, 0.6))}   # B2 镜像（反向任务，上游没有）
DIRECTION = {"forward": {"pick": "right", "receive": "left", "goal_x_sign": -1},
             "reverse": {"pick": "left", "receive": "right", "goal_x_sign": +1}}


class BudgetExceeded(RuntimeError):
    """硬步数预算用尽（`ExpertConfig.max_steps`）。**不静默截断**：抛出后由 run_episode 记录。"""

    def __init__(self, step_idx: int, phase: str):
        super().__init__(f"step budget exceeded at step {step_idx} in phase {phase}")
        self.step_idx = step_idx
        self.phase = phase


def now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sample_box_pose_seeded(seed: int, direction: str) -> np.ndarray:
    """与上游 `gym_aloha/utils.py:4-15` **同分布**（同 rng 类型、同 y/z 区间），只把 x 区间镜像。"""
    (xr, yr) = SPAWN_RANGE[direction]
    rng = np.random.RandomState(seed)
    # 上游布局是 **3×2**（每行 = (low, high)）：`ranges = np.vstack([x_range, y_range, z_range])`
    # （`gym_aloha/utils.py:11`）。B2 第一版写成 2×3（转置）⇒ 采样出 6 维、且 x=0.2614 越出
    # [0,0.2] 区间。已按上游布局修正，并在下面 assert 维数与区间。
    ranges = np.vstack([[xr[0], xr[1]], [yr[0], yr[1]], [0.05, 0.05]])
    pos = rng.uniform(ranges[:, 0], ranges[:, 1])
    assert pos.shape == (3,), pos.shape
    assert xr[0] <= pos[0] <= xr[1] and yr[0] <= pos[1] <= yr[1], (pos, xr, yr)
    return np.concatenate([pos, [1.0, 0.0, 0.0, 0.0]])


# ---------------------------- 旋转工具 ----------------------------
def quat_to_mat(q_wxyz: Sequence[float]) -> np.ndarray:
    w, x, y, z = q_wxyz
    n = np.sqrt(w * w + x * x + y * y + z * z)
    if n < 1e-12:
        return np.eye(3)
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def mat_to_axisangle(R: np.ndarray) -> np.ndarray:
    tr = float(np.clip((R[0, 0] + R[1, 1] + R[2, 2] - 1.0) / 2.0, -1.0, 1.0))
    ang = np.arccos(tr)
    if ang < 1e-9:
        return np.zeros(3)
    s = 2.0 * np.sin(ang)
    if abs(s) < 1e-12:
        return np.array([ang, 0.0, 0.0])
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / s
    n = np.linalg.norm(v)
    if n < 1e-12:
        return np.array([ang, 0.0, 0.0])
    return v / n * ang


def slerp_rot(R0: np.ndarray, R1: np.ndarray, t: float) -> np.ndarray:
    """旋转矩阵球面插值：`t=0→R0`、`t=1→R1`，角度**线性**、走短弧。

    只用 mujoco 自己的四元数原语（`mju_mat2Quat`/`mju_negQuat`/`mju_mulQuat`/`mju_quat2Vel`/
    `mju_axisAngle2Quat`/`mju_quat2Mat`），不自手写三角函数。B2 2026-09-30 实测：
    R0=I → R1=Rz(180°)，t=0/0.25/0.5/1.0 给出 0/45/90/180°，`det=1.000000000`、
    `max|RᵀR−I|=0`（mujoco 3.8.1 **没有** `mju_slerpQuat`，只有上面这几个）。
    """
    import mujoco
    R0 = np.asarray(R0, dtype=float).reshape(3, 3)
    R1 = np.asarray(R1, dtype=float).reshape(3, 3)
    t = float(min(1.0, max(0.0, t)))
    q0 = np.zeros(4); mujoco.mju_mat2Quat(q0, R0.reshape(9))
    if t <= 0.0:
        return R0.copy()
    q1 = np.zeros(4); mujoco.mju_mat2Quat(q1, R1.reshape(9))
    q0inv = np.zeros(4); mujoco.mju_negQuat(q0inv, q0)     # 单位四元数的共轭 == 逆
    dq = np.zeros(4); mujoco.mju_mulQuat(dq, q1, q0inv)    # dq = q1 · q0⁻¹（相对转动）
    if dq[0] < 0.0:                                        # 翻到 w>=0 半球 ⇒ 短弧（q 与 −q 同转动）
        mujoco.mju_negQuat(dq, dq)
    vel = np.zeros(3); mujoco.mju_quat2Vel(vel, dq, 1.0)   # = axis·angle
    nrm = float(np.linalg.norm(vel))
    if nrm < 1e-12:
        return R0.copy()
    axis = vel / nrm
    dqt = np.zeros(4); mujoco.mju_axisAngle2Quat(dqt, axis, nrm * t)
    qt = np.zeros(4); mujoco.mju_mulQuat(qt, dqt, q0)
    out = np.zeros(9); mujoco.mju_quat2Mat(out, qt)
    return out.reshape(3, 3)


# ---------------------------- 环境封装（旁路 AlohaEnv） ----------------------------
class JointEnv:
    """部署 env 的最小封装：`bimanual_viperx_transfer_cube.xml` + `TransferCubeTask`，
    但 **① 方块位姿可注入（含左侧）**、**② `get_observation` 默认不渲染**（渲染按需单独调）。

    ①的必要性：`AlohaEnv.reset()`（`env.py:159`–`:160`）会用 `sample_box_pose(seed)` **覆盖**
      外部写入的 `BOX_POSE[0]`，而上游 x 区间恒为 [0.0,0.2] ⇒ **反向任务（左侧）无法生成**
      （probe1 实测 `box_spawn_matches_injection=false`）。旁路后 probe2 实测 `bitwise_equal=true`。
    ②的必要性：上游 `get_observation` 每 step 渲 3 张 480×640（probe1 实测 93.5 ms/step），
      专家搜索阶段不需要图像；录制阶段按帧显式渲染，成本可控。
    """

    def __init__(self, dt: float, box_pose7: np.ndarray, render_cams: Sequence[str] = (),
                 img_h: int = 480, img_w: int = 640,
                 render_spec: Optional[Sequence[Tuple[str, str, int, int]]] = None):
        import mujoco
        from dm_control import mujoco as dm_mujoco
        from dm_control.rl import control
        import gym_aloha
        from gym_aloha.tasks.sim import TransferCubeTask, BOX_POSE
        self.mujoco = mujoco
        pkg = Path(gym_aloha.__file__).resolve().parent / "assets"
        self.xml_path = str(pkg / "bimanual_viperx_transfer_cube.xml")
        self.render_cams = tuple(render_cams)
        self.img_h, self.img_w = img_h, img_w
        # **逐槽分辨率**（S1 数据集生成器用）：`render_spec = [(slot_id, camera_name, h, w), …]`。
        # 为什么必须按 slot 而不是按相机名做键：**同一个相机要出两档分辨率** —— 团队三槽
        # （`top`/`left_wrist`/`right_wrist` @480×640，对齐 ABC-130k 的 640×480 子集）与 π₀.₅ 三键
        # （`angle`/`left_wrist`/`right_wrist` @224²，对齐 A2 契约 `scripts/a2_pi05_contract_probe.py:97`
        # 的原生渲法）共用两个腕相机。**两档不是缩放关系**：MuJoCo 的 `fovy` 固定、`fx=fy`，
        # 所以 4:3 与 1:1 的视锥不同 ⇒ 224² 必须由渲染器直接出，不能从 480×640 缩。
        self.render_spec = tuple(render_spec) if render_spec else ()
        outer = self

        class _Task(TransferCubeTask):
            def get_observation(self, physics):
                obs = collections.OrderedDict()
                obs["qpos"] = self.get_qpos(physics)
                obs["qvel"] = self.get_qvel(physics)
                obs["env_state"] = self.get_env_state(physics)
                obs["images"] = {}
                return obs

        self._BOX_POSE = BOX_POSE
        BOX_POSE[0] = np.asarray(box_pose7, dtype=float).copy()
        self.box_pose_cmd = np.asarray(box_pose7, dtype=float).copy()
        physics = dm_mujoco.Physics.from_xml_path(self.xml_path)
        self.task = _Task()
        self.env = control.Environment(physics, self.task, float("inf"), control_timestep=dt,
                                       n_sub_steps=None, flat_observation=False)
        self.physics = physics
        self.m = physics.model.ptr
        self.d = physics.data.ptr
        self.dt = dt
        self._body_id = {s: physics.model.name2id(GRIP_LINK_BODY[s], "body") for s in ("left", "right")}
        self._geom_id = {}
        for s in ("left", "right"):
            for g in FINGER_GEOMS[s]:
                self._geom_id[g] = physics.model.name2id(g, "geom")
        self._box_body = physics.model.name2id("box", "body")
        self._jnt_range = np.asarray(physics.model.jnt_range, dtype=float)
        self._dof_lo = {}
        self._dof_hi = {}
        for s, dofs in ARM_DOF.items():
            lo, hi = [], []
            for dof in dofs:
                jid = int(self.m.dof_jntid[dof])   # mujoco 3.8.1 无 mj_dof2joint（B2 实测 AttributeError）
                r = self._jnt_range[jid]
                lo.append(r[0]); hi.append(r[1])
            self._dof_lo[s] = np.array(lo); self._dof_hi[s] = np.array(hi)

    # ---- 基本读数 ----
    def reset(self):
        ts = self.env.reset()
        self.physics.forward()
        return ts

    def qpos16(self) -> np.ndarray:
        return np.asarray(self.physics.data.qpos[:16], dtype=float).copy()

    def state14(self) -> np.ndarray:
        return np.asarray(self.env.task.get_qpos(self.physics), dtype=float).copy()

    def qvel14(self) -> np.ndarray:
        return np.asarray(self.env.task.get_qvel(self.physics), dtype=float).copy()

    def box_pos(self) -> np.ndarray:
        return np.asarray(self.physics.named.data.xpos["box"], dtype=float).copy()

    def box_qvel(self) -> np.ndarray:
        return np.asarray(self.physics.data.qvel[16:22], dtype=float).copy()

    def grip_pose(self, side: str) -> Tuple[np.ndarray, np.ndarray]:
        bid = self._body_id[side]
        p = np.asarray(self.physics.data.xpos[bid], dtype=float).copy()
        q = np.asarray(self.physics.data.xquat[bid], dtype=float).copy()
        return p, q

    def tip_pos(self, side: str) -> np.ndarray:
        p, q = self.grip_pose(side)
        return p + quat_to_mat(q) @ TIP_REL_GRIPFRAME

    def finger_geom_pos(self, name: str) -> np.ndarray:
        return np.asarray(self.physics.data.geom_xpos[self._geom_id[name]], dtype=float).copy()

    def contacts_with_box(self) -> List[Tuple[str, str]]:
        out = []
        pd = self.physics.data
        for i in range(pd.ncon):
            c = pd.contact[i]
            n1 = self.physics.model.id2name(int(c.geom1), "geom")
            n2 = self.physics.model.id2name(int(c.geom2), "geom")
            if n1 and n2 and ("red_box" in (n1, n2)):
                out.append((n1, n2))
        return sorted(set(out))

    def env_reward(self) -> int:
        """上游 `TransferCubeTask.get_reward`（`tasks/sim.py:125`–`:155`）：只覆盖右→左。"""
        return int(self.env.task.get_reward(self.physics))

    # ---- IK ----
    def jac(self, side: str) -> Tuple[np.ndarray, np.ndarray]:
        import mujoco
        jp = np.zeros((3, self.m.nv)); jr = np.zeros((3, self.m.nv))
        mujoco.mj_jacBody(self.m, self.d, jp, jr, self._body_id[side])
        dofs = ARM_DOF[side]
        return jp[:, dofs], jr[:, dofs]

    def ik_step(self, side: str, p_des: np.ndarray, R_des: np.ndarray, max_dq: float,
                lam: float = 0.05) -> Tuple[np.ndarray, float, float]:
        """一步阻尼最小二乘（闭环：从**当前实测** q 出发，不积分自己的目标，避免漂移）。"""
        p_cur, q_cur = self.grip_pose(side)
        R_cur = quat_to_mat(q_cur)
        e_pos = np.asarray(p_des, dtype=float) - p_cur
        e_ori = mat_to_axisangle(R_des @ R_cur.T)
        e = np.concatenate([e_pos, e_ori])
        Jp, Jr = self.jac(side)
        J = np.vstack([Jp, Jr])
        JJt = J @ J.T + (lam ** 2) * np.eye(6)
        dq = J.T @ np.linalg.solve(JJt, e)
        dq = np.clip(dq, -max_dq, max_dq)
        qpos = self.qpos16()
        q_now = qpos[ARM_DOF[side]]
        margin = 0.02
        lo = self._dof_lo[side] + margin
        hi = self._dof_hi[side] - margin
        q_tgt = np.clip(q_now + dq, lo, hi)
        return q_tgt, float(np.linalg.norm(e_pos)), float(np.linalg.norm(e_ori))

    # ---- 动作下发 ----
    def make_action(self, arm_targets: Dict[str, np.ndarray], grip_norm: Dict[str, float]) -> np.ndarray:
        a = np.zeros(14, dtype=np.float32)
        for s in ("left", "right"):
            if s in arm_targets:
                a[ARM_ACT_SLICE[s]] = np.asarray(arm_targets[s], dtype=float)
            else:  # 保持当前实测角（不加能量）
                a[ARM_ACT_SLICE[s]] = self.qpos16()[ARM_DOF[s]]
            a[GRIP_ACT_IDX[s]] = float(grip_norm.get(s, GRIP_START_NORM))
        return a

    def step(self, action14: np.ndarray):
        return self.env.step(np.asarray(action14, dtype=np.float32))

    def render(self, cams: Optional[Sequence[str]] = None) -> Dict[str, np.ndarray]:
        if self.render_spec:
            out = {}
            for slot, cam, h, w in self.render_spec:
                out[slot] = self.physics.render(height=int(h), width=int(w), camera_id=cam)
            return out
        cams = tuple(cams if cams is not None else self.render_cams)
        out = {}
        for c in cams:
            out[c] = self.physics.render(height=self.img_h, width=self.img_w, camera_id=c)
        return out

    def close(self):
        try:
            self.env.close()
        except Exception:
            pass


# ---------------------------- 成功/失败/未知 判据 ----------------------------
@dataclass
class JudgeConfig:
    """几何真值判据（**独立于** env 的 `reward==4`），方向由 `receive_side` 决定。"""
    hold_steps_required: int = 10          # 必须连续握住 ≥10 步（0.34 s）才算，防"一瞬间弹过"
    min_box_z_above_table: float = 0.03    # 离桌面 ≥3 cm（方块半高 2 cm ⇒ 真的被提起来）
    tip_to_box_max_m: float = 0.045        # 指尖中点到方块中心 ≤4.5 cm（几何真值，不靠接触）
    flick_speed_mps: float = 1.5           # 方块线速度峰值 >1.5 m/s ⇒ 弹射/flick
    off_table_bounds: float = 0.45         # |x| 或 |y-0.6| 超过 ⇒ 掉出桌面工作区
    min_displacement_m: float = 0.05       # 方块水平位移下限：证明"真的搬动了"，防接收臂就地捡起的假成功
    goal_x_sign_margin: float = 0.0        # 诊断用（不作红判据）：方块终态 x 的符号是否与目标侧一致


class SuccessJudge:
    """逐步累积证据，回合结束给 `success|failure|unknown` + 失败原因分类 + 弹射检出。

    **极性牙**：判据里 `receive_side` 与 `goal_x_sign` 都来自 `DIRECTION[direction]`；
    把方向写反（`--mutation reverse-direction-flipped`）会让"方块在目标侧"这一条恒假 ⇒ 必须判红。
    """

    def __init__(self, direction: str, cfg: JudgeConfig = JudgeConfig(),
                 box_spawn: Optional[np.ndarray] = None):
        self.direction = direction
        self.cfg = cfg
        self.receive = DIRECTION[direction]["receive"]
        self.pick = DIRECTION[direction]["pick"]
        self.goal_sign = DIRECTION[direction]["goal_x_sign"]
        self.box_spawn = (np.asarray(box_spawn, dtype=float)[:3].copy()
                          if box_spawn is not None else None)
        self.reset()

    def reset(self):
        self.steps: List[dict] = []
        self.held_run = 0
        self.max_held_run = 0
        self.max_box_speed = 0.0
        self.max_box_speed_phase = None
        self.max_box_speed_step = None
        self.box_off_table = False
        self.ever_touched_by_receiver = False
        self.ever_touched_by_picker = False
        self.picker_held_run = 0
        self.max_picker_held_run = 0
        self.first_contact_step = None
        self.env_reward4_step = None
        self.env_reward4 = False

    def observe(self, env: JointEnv, step_idx: int, phase: str) -> dict:
        cfg = self.cfg
        box = env.box_pos()
        bv = env.box_qvel()[:3]
        speed = float(np.linalg.norm(bv))
        if speed > self.max_box_speed:
            self.max_box_speed = speed
            self.max_box_speed_phase = phase
            self.max_box_speed_step = step_idx
        cons = env.contacts_with_box()
        names = set()
        for a, b in cons:
            names.add(a); names.add(b)
        touch_table = "table" in names
        touch_recv = any(g in names for g in FINGER_GEOMS[self.receive])
        touch_pick = any(g in names for g in FINGER_GEOMS[self.pick])
        if touch_recv:
            self.ever_touched_by_receiver = True
            if self.first_contact_step is None:
                self.first_contact_step = step_idx
        if touch_pick:
            self.ever_touched_by_picker = True
        tip = env.tip_pos(self.receive)
        tip_dist = float(np.linalg.norm(tip - box))
        off_table_high = bool((not touch_table) and (box[2] - TABLE_Z) > cfg.min_box_z_above_table)
        held = bool(touch_recv and off_table_high)
        picker_held = bool(touch_pick and off_table_high)
        if held:
            self.held_run += 1
        else:
            self.held_run = 0
        self.max_held_run = max(self.max_held_run, self.held_run)
        if picker_held:
            self.picker_held_run += 1
        else:
            self.picker_held_run = 0
        self.max_picker_held_run = max(self.max_picker_held_run, self.picker_held_run)
        if abs(box[0]) > cfg.off_table_bounds or abs(box[1] - 0.6) > cfg.off_table_bounds or box[2] < TABLE_Z - 0.02:
            self.box_off_table = True
        r = env.env_reward()
        if r == 4 and self.env_reward4_step is None:
            self.env_reward4_step = step_idx
            self.env_reward4 = True
        rec = {"step": step_idx, "phase": phase, "box": [round(float(x), 5) for x in box],
               "box_speed": round(speed, 4), "held": held, "held_run": self.held_run,
               "touch_table": touch_table, "touch_receive": touch_recv, "touch_pick": touch_pick,
               "picker_held": picker_held,
               "recv_tip_to_box_m": round(tip_dist, 5), "env_reward": r}
        self.steps.append(rec)
        return rec

    def verdict(self) -> dict:
        cfg = self.cfg
        last = self.steps[-1] if self.steps else None
        box = np.array(last["box"]) if last else np.zeros(3)
        on_goal_side = bool(self.goal_sign * box[0] > cfg.goal_x_sign_margin)
        final_held = bool(last and last["held"])
        long_hold = self.max_held_run >= cfg.hold_steps_required
        picker_held_long = self.max_picker_held_run >= cfg.hold_steps_required
        flick = self.max_box_speed > cfg.flick_speed_mps
        disp = (float(np.linalg.norm(box[:2] - self.box_spawn[:2]))
                if (self.box_spawn is not None and last) else None)
        displaced = bool(disp is not None and disp >= cfg.min_displacement_m)
        # ---- 三值判定 ----
        if not self.steps:
            ok, why = None, "无任何逐步证据 ⇒ UNJUDGED（三值纪律：不用 0 填充）"
        elif self.box_spawn is None:
            ok, why = None, "缺 spawn 位置 ⇒ 无法判「真的搬动了」⇒ UNJUDGED（不用 0 填充）"
        elif final_held and long_hold and picker_held_long and displaced and not self.box_off_table:
            ok, why = True, (f"终态被 {self.receive} 夹爪握住、离桌面 {box[2]-TABLE_Z:.3f} m、"
                             f"连续握住 {self.max_held_run} 步；抓取臂曾连续握住 {self.max_picker_held_run} 步；"
                             f"水平位移 {disp:.3f} m ≥ {cfg.min_displacement_m}（真的搬动了）")
        elif flick and not (final_held and long_hold):
            ok, why = False, f"弹射/flick 检出：方块线速度峰值 {self.max_box_speed:.2f} m/s > {cfg.flick_speed_mps}"
        elif self.box_off_table:
            ok, why = False, f"方块掉出桌面工作区（终态 {[round(float(x),3) for x in box]}）"
        elif not self.ever_touched_by_picker:
            ok, why = False, "抓取臂从未与方块接触（no_contact_at_grasp）"
        elif not self.ever_touched_by_receiver:
            ok, why = False, "接收臂从未与方块接触（receiver_missed）"
        elif not picker_held_long:
            ok, why = False, (f"抓取臂最长连续握持 {self.max_picker_held_run} 步 < {cfg.hold_steps_required}"
                              "（picker_never_held：没真正提起来过）")
        elif not displaced:
            ok, why = False, (f"方块水平位移 {disp:.3f} m < {cfg.min_displacement_m}"
                              "（not_displaced：接收臂就地捡起 ≠ 交接，判失败）")
        elif not long_hold:
            ok, why = False, (f"握持时长不足：最长连续 {self.max_held_run} 步 < {cfg.hold_steps_required}"
                              "（receiver_grasp_slipped）")
        elif last and last["touch_table"]:
            ok, why = False, "终态方块仍接触桌面（未真正提起）"
        else:
            ok, why = None, (f"证据不足以判定：final_held={final_held} long_hold={long_hold} "
                             f"on_goal_side={on_goal_side} ⇒ UNJUDGED")
        failure_class = None
        if ok is False:
            for tag, cond in (("flick_ejected", flick),
                              ("box_off_table", self.box_off_table),
                              ("no_contact_at_grasp", not self.ever_touched_by_picker),
                              ("receiver_missed", not self.ever_touched_by_receiver),
                              ("picker_never_held", not picker_held_long),
                              ("not_displaced", not displaced),
                              ("receiver_grasp_slipped", not long_hold),
                              ("not_lifted", bool(last and last["touch_table"]))):
                if cond:
                    failure_class = tag
                    break
        return {
            "direction": self.direction, "pick_side": self.pick, "receive_side": self.receive,
            "goal_x_sign": self.goal_sign, "ok": ok, "why": why, "failure_class": failure_class,
            "verdict": ("success" if ok is True else ("failure" if ok is False else "unknown")),
            "evidence": {
                "n_steps": len(self.steps),
                "max_held_run_steps": self.max_held_run,
                "hold_steps_required": cfg.hold_steps_required,
                "max_box_speed_mps": round(self.max_box_speed, 4),
                "max_box_speed_phase": self.max_box_speed_phase,
                "max_box_speed_step": self.max_box_speed_step,
                "flick_detected": flick,
                "box_off_table": self.box_off_table,
                "ever_touched_by_picker": self.ever_touched_by_picker,
                "ever_touched_by_receiver": self.ever_touched_by_receiver,
                "max_picker_held_run_steps": self.max_picker_held_run,
                "box_horizontal_displacement_m": (round(disp, 5) if disp is not None else None),
                "min_displacement_m": cfg.min_displacement_m,
                "box_spawn_xyz": ([round(float(x), 5) for x in self.box_spawn]
                                  if self.box_spawn is not None else None),
                "on_goal_side_x_sign_diagnostic_only": on_goal_side,
                "first_receiver_contact_step": self.first_contact_step,
                "final_box_xyz": [round(float(x), 5) for x in box],
                "final_box_z_above_table_m": round(float(box[2] - TABLE_Z), 5) if last else None,
                "on_goal_side": on_goal_side,
                "env_reward4_seen": self.env_reward4,
                "env_reward4_first_step": self.env_reward4_step,
                "judge_rules": [
                    f"held := 方块与 {self.receive} 侧任一指 geom 接触 AND 不接触 table AND box_z-TABLE_Z > {cfg.min_box_z_above_table}",
                    f"success := 终态 held AND 接收臂最长连续 held ≥ {cfg.hold_steps_required} 步 "
                    f"AND 抓取臂最长连续 held ≥ {cfg.hold_steps_required} 步 "
                    f"AND 水平位移 ≥ {cfg.min_displacement_m} m AND 未掉出桌面",
                    "「方块在目标侧（x 符号）」只作**诊断**不作红判据：D §4 S1 判据 3 要的是"
                    "「方块在目标侧夹爪内 + 离桌面高度阈值」，指的是**哪只夹爪**，不是 x 符号；"
                    "实测两臂可达带重叠区只有 x∈[-0.125,+0.125]（probe/reach_sweep.json），"
                    "交接点必然靠近中线，用 x 符号当红判据会把合法交接判红（极性错，同裁定 51.1 的教训）",
                    f"flick := max|box 线速度| > {cfg.flick_speed_mps} m/s",
                    "证据不足 ⇒ unknown（不填 False、不填 0）",
                ],
            },
        }


# ---------------------------- 运动学规划器（plan-then-replay） ----------------------------
class KinPlanner:
    """**纯运动学** IK 规划器：在独立的 `MjData` 上把指尖路径迭代到收敛，产出关节目标序列。

    为什么不用"每控制步一次闭环 IK"（B2 第一版就是这么写的，实测失败）
    ------------------------------------------------------------------
    第一版 `ik_step` 每步从**实测** q 出发加 `dq`，而关节 env 是 position actuator（kp 800/1600），
    实测存在稳态滞后 ⇒ 目标永远只比实测领先一个 `dq`，实际推进速度掉到命令值的 ~1/8：
    `carry` 相位 90 步只走完 0.24/0.28 m（`probe` 前的 selftest 实测 `phase_diag`）。
    改成"离线把整条路径的 IK 解到收敛 → 逐步下发"后，滞后只影响跟踪误差不影响路径长度。

    **不碰物理**：`mj_forward` 只算运动学与接触，不积分；因此规划与执行解耦，
    规划失败（不可达/撞限位）能在**执行前**就报出来，而不是变成一条烂示范。
    """

    def __init__(self, xml_path: str):
        import mujoco
        self.mujoco = mujoco
        self.m = mujoco.MjModel.from_xml_path(xml_path)
        self.d = mujoco.MjData(self.m)
        self._bid = {s: mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, GRIP_LINK_BODY[s])
                     for s in ("left", "right")}
        self._lo = {}
        self._hi = {}
        for s, dofs in ARM_DOF.items():
            lo, hi = [], []
            for dof in dofs:
                jid = int(self.m.dof_jntid[dof])
                lo.append(float(self.m.jnt_range[jid][0]))
                hi.append(float(self.m.jnt_range[jid][1]))
            self._lo[s] = np.array(lo)
            self._hi[s] = np.array(hi)

    def sync(self, qpos23: np.ndarray):
        np.copyto(self.d.qpos, np.asarray(qpos23, dtype=float))
        self.mujoco.mj_forward(self.m, self.d)

    def grip_pose(self, side: str):
        bid = self._bid[side]
        return (np.asarray(self.d.xpos[bid], dtype=float).copy(),
                np.asarray(self.d.xmat[bid], dtype=float).reshape(3, 3).copy())

    def tip(self, side: str) -> np.ndarray:
        p, R = self.grip_pose(side)
        return p + R @ TIP_REL_GRIPFRAME

    def q_arm(self, side: str) -> np.ndarray:
        return np.asarray(self.d.qpos[ARM_DOF[side]], dtype=float).copy()

    def jac(self, side: str):
        jp = np.zeros((3, self.m.nv)); jr = np.zeros((3, self.m.nv))
        self.mujoco.mj_jacBody(self.m, self.d, jp, jr, self._bid[side])
        dofs = ARM_DOF[side]
        return jp[:, dofs], jr[:, dofs]

    def contact_names(self):
        out = set()
        for i in range(self.d.ncon):
            c = self.d.contact[i]
            n1 = self.mujoco.mj_id2name(self.m, self.mujoco.mjtObj.mjOBJ_GEOM, int(c.geom1))
            n2 = self.mujoco.mj_id2name(self.m, self.mujoco.mjtObj.mjOBJ_GEOM, int(c.geom2))
            if n1 and n2:
                out.add((n1, n2))
        return out

    def ik_solve(self, side: str, p_des: np.ndarray, R_des: np.ndarray, iters: int = 60,
                 lam: float = 0.03, max_dq: float = 0.12, tol_pos: float = 2e-3,
                 tol_ori: float = 0.03, margin: float = 0.02,
                 other_q: Optional[Dict[str, np.ndarray]] = None) -> dict:
        """把 `side` 臂的 gripper_link 迭代到 (p_des + R_des@tip_rel, R_des)。就地改 self.d.qpos。"""
        p_grip_des = np.asarray(p_des, dtype=float) - R_des @ TIP_REL_GRIPFRAME
        lo = self._lo[side] + margin
        hi = self._hi[side] - margin
        if other_q:
            for s2, q2 in other_q.items():
                if s2 != side:
                    self.d.qpos[ARM_DOF[s2]] = np.clip(np.asarray(q2, dtype=float), lo if s2 == side else None,
                                                       hi if s2 == side else None) if False else np.asarray(q2, dtype=float)
        e_pos = e_ori = float("nan")
        n_at_limit = 0
        for _ in range(iters):
            self.mujoco.mj_forward(self.m, self.d)
            p_cur, R_cur = self.grip_pose(side)
            e_pos = float(np.linalg.norm(p_grip_des - p_cur))
            e_ori = float(np.linalg.norm(mat_to_axisangle(R_des @ R_cur.T)))
            if e_pos < tol_pos and e_ori < tol_ori:
                break
            e = np.concatenate([p_grip_des - p_cur, mat_to_axisangle(R_des @ R_cur.T)])
            Jp, Jr = self.jac(side)
            J = np.vstack([Jp, Jr])
            dq = J.T @ np.linalg.solve(J @ J.T + (lam ** 2) * np.eye(6), e)
            dq = np.clip(dq, -max_dq, max_dq)
            q = np.clip(self.q_arm(side) + dq, lo, hi)
            n_at_limit = int(np.sum(np.abs(q - lo) < 1e-6) + np.sum(np.abs(q - hi) < 1e-6))
            self.d.qpos[ARM_DOF[side]] = q
        self.mujoco.mj_forward(self.m, self.d)
        p_fin, R_fin = self.grip_pose(side)
        return {"converged": bool(e_pos < tol_pos and e_ori < tol_ori),
                "e_pos_m": round(float(np.linalg.norm(p_grip_des - p_fin)), 6),
                "e_ori_rad": round(float(np.linalg.norm(mat_to_axisangle(R_des @ R_fin.T))), 6),
                "n_joints_at_limit": n_at_limit,
                "tip_final": [round(float(x), 5) for x in self.tip(side)],
                "q_final": [round(float(x), 5) for x in self.q_arm(side)]}

    def plan_align(self, side: str, R_des: np.ndarray, n_steps: int,
                   other_q: Optional[Dict[str, np.ndarray]] = None
                   ) -> Tuple[List[np.ndarray], dict]:
        """**原地转腕**：gripper_link 位置钉住不动，姿态从当前实测球面插值到 `R_des`。

        用途：把 175° 量级的腕姿态对齐放进**沉降的那 12 步**里做 —— 那 12 步不进数据集
        （裁定 66 §13.7-1），所以大转角一帧都不落在数据里。留在数据集内做的话，位置伺服是
        **欠阻尼**的：B2 2026-09-30 实测命令侧已压到 11.7°/步，实测侧仍在相位第一个点
        冲出 23.3°、第二个点 42.0°（团队 C03 阈值 30°/帧，`clean` 段会删帧），
        命令→实测的跟踪误差一度涨到 46.5° 才回落。

        `ik_solve` 的 `p_des` 是**指尖**目标（内部会减掉 `R_des @ TIP_REL_GRIPFRAME`），
        所以要把 grip 钉在 p0，每步就得喂 `tip_k = p0 + R_k @ TIP_REL_GRIPFRAME`。
        """
        p0, R0 = self.grip_pose(side)
        p0 = np.asarray(p0, dtype=float).copy()
        R_des = np.asarray(R_des, dtype=float).reshape(3, 3)
        total_deg = float(np.degrees(np.linalg.norm(mat_to_axisangle(R_des @ R0.T))))
        n_steps = max(1, int(n_steps))
        qs: List[np.ndarray] = []
        nonconv = 0
        max_e_ori = 0.0
        for k in range(1, n_steps + 1):
            Rk = slerp_rot(R0, R_des, min(1.0, k / float(n_steps)))
            info = self.ik_solve(side, p0 + Rk @ TIP_REL_GRIPFRAME, Rk, other_q=other_q)
            if not info["converged"]:
                nonconv += 1
            max_e_ori = max(max_e_ori, info["e_ori_rad"])
            qs.append(self.q_arm(side).copy())
        return qs, {"kind": "wrist_align_in_place", "side": side, "n_points": len(qs),
                    "total_angle_deg": round(total_deg, 4),
                    "per_step_deg": round(total_deg / n_steps, 4),
                    "n_nonconverged_points": nonconv, "max_e_ori_rad": round(max_e_ori, 6),
                    "grip_position_held_at": [round(float(x), 5) for x in p0]}

    def plan_line(self, side: str, tip_from: np.ndarray, tip_to: np.ndarray, R_des: np.ndarray,
                  step_m: float, other_q: Optional[Dict[str, np.ndarray]] = None,
                  stop_on_contact_with: Optional[str] = None,
                  R_from: Optional[np.ndarray] = None,
                  n_align: int = 0) -> Tuple[List[np.ndarray], dict]:
        """从 `tip_from` 到 `tip_to` 直线插值（每 `step_m` 一个控制步），逐点解 IK。

        返回 `(关节目标序列, 诊断)`。若 `stop_on_contact_with="red_box"` 且规划中检测到该 geom
        与手指接触，则**在接触点截断**（下降相位需要这个语义：碰到方块就该合爪，不该硬顶）。
        """
        tip_from = np.asarray(tip_from, dtype=float)
        tip_to = np.asarray(tip_to, dtype=float)
        dist = float(np.linalg.norm(tip_to - tip_from))
        n = max(1, int(np.ceil(dist / step_m)))
        qs: List[np.ndarray] = []
        last = None
        truncated_at = None
        max_e_pos = 0.0
        nonconv = 0
        # 腕姿态对齐：前 `n_align` 个点从 `R_from`（= 规划开始时的**实测**姿态）球面插值到 `R_des`。
        # 不整段强制：若相位点数 < n_align，本相位只插值一部分，剩余误差留给下一相位继续摊
        # （这样每步转角恒 ≤ 总转角/n_align，不会因为相位短反而变得更快）。
        n_align = int(n_align or 0)
        align_on = (R_from is not None and n_align > 0)
        R_from = np.asarray(R_from, dtype=float).reshape(3, 3) if align_on else None
        align_total_deg = (float(np.degrees(np.linalg.norm(
            mat_to_axisangle(np.asarray(R_des, dtype=float) @ R_from.T)))) if align_on else 0.0)
        for k in range(1, n + 1):
            tgt = tip_from + (tip_to - tip_from) * (k / n)
            R_k = R_des
            if align_on:
                t = min(1.0, k / float(n_align))
                if t < 1.0:
                    R_k = slerp_rot(R_from, R_des, t)
            info = self.ik_solve(side, tgt, R_k, other_q=other_q)
            last = info
            max_e_pos = max(max_e_pos, info["e_pos_m"])
            if not info["converged"]:
                nonconv += 1
            qs.append(self.q_arm(side).copy())
            if stop_on_contact_with:
                hit = any(stop_on_contact_with in pair and
                          any(g in pair for g in FINGER_GEOMS[side])
                          for pair in self.contact_names())
                if hit:
                    truncated_at = k
                    break
        return qs, {"n_points": len(qs), "path_len_m": round(dist, 5), "step_m": step_m,
                    "max_e_pos_m": round(max_e_pos, 6), "n_nonconverged_points": nonconv,
                    "last_point": last, "truncated_at_point": truncated_at,
                    "wrist_align": {"enabled": bool(align_on), "n_align": n_align,
                                    "total_angle_deg": round(align_total_deg, 4),
                                    "per_step_deg": (round(align_total_deg / n_align, 4)
                                                     if align_on and n_align else None),
                                    "note": ("前 n_align 个点把腕从实测姿态球面插值到 R_DOWN，"
                                             "避免相位第一个点猛拉腕（C03 0.1 m/30° 阈值）")}}


def calibrate_pad_extent(xml_path: str) -> dict:
    """**实测**：夹爪朝下、张开，一路下降到手指碰桌面，量"指尖中点"离桌面的高度。

    这个数决定 `grasp_dz`（抓取时指尖中点该对准方块中心还是更高）。B2 第一版按
    "指尖中点 = 方块中心"（`grasp_dz=0`）写死，实测下降相位顶不进去（`phase_diag`
    `pick_descend` 90 步 cap_exhausted、tip 停在 z=0.060）⇒ 说明"指尖中点"不是最低接触点。
    """
    kp = KinPlanner(xml_path)
    q = np.zeros(23)
    q[:16] = np.array([0, -0.96, 1.16, 0, -0.3, 0, 0.02239, -0.02239,
                       0, -0.96, 1.16, 0, -0.3, 0, 0.02239, -0.02239])
    q[16:23] = np.array([0.15, 0.5, 0.05, 1, 0, 0, 0])
    out = {}
    for side, x in (("right", 0.15), ("left", -0.15)):
        kp.sync(q)
        tip0 = kp.tip(side).copy()
        # 先解到"指尖中点在 z=0.20、xy 与 home 同"的朝下姿态，再逐 1 mm 下降直到接触桌面
        info = kp.ik_solve(side, np.array([tip0[0], tip0[1], 0.20]), R_DOWN, iters=200)
        z_at_contact = None
        tip_z = 0.20
        for _ in range(260):
            tip_z -= 0.001
            kp.ik_solve(side, np.array([tip0[0], tip0[1], tip_z]), R_DOWN, iters=40)
            hit = any("table" in pair and any(g in pair for g in FINGER_GEOMS[side])
                      for pair in kp.contact_names())
            if hit:
                z_at_contact = tip_z
                break
        out[side] = {"home_tip": [round(float(v), 5) for v in tip0],
                     "approach_converged": info["converged"],
                     "tip_z_at_table_contact": z_at_contact,
                     "pad_extent_below_tip_midpoint_m": (round(float(z_at_contact - TABLE_Z), 5)
                                                         if z_at_contact is not None else None),
                     "note": ("tip_z_at_table_contact = 指尖中点在**手指刚碰桌面**时的高度；"
                              "pad_extent = 0 - 该值 = 指尖中点到最低接触点的距离")}
    return out


# ---------------------------- 脚本专家（相位机 · plan-then-replay） ----------------------------
@dataclass
class ExpertConfig:
    path_step_m: float = 0.006        # 每个控制步指尖推进 6 mm ⇒ 0.176 m/s @29.4118 Hz
    lam: float = 0.03                 # DLS 阻尼（规划用，与执行无关）
    ik_iters: int = 60
    settle_steps: int = 12            # 开局让方块从 z=0.05 落到 0.02
    pre_grasp_dz: float = 0.12        # 方块上方 12 cm
    # 抓取/放下高度**由实测常数导出**，不是手调魔数：
    #   指尖中点高度 = 方块底面(TABLE_Z) + FINGER_BOTTOM_CLEARANCE_M + PAD_EXTENT_M
    #   ⇒ 相对方块中心(z=0.02) 的 dz = -BOX_HALF + 0.005 + 0.0595 = 0.0445
    grasp_dz: float = -BOX_HALF + FINGER_BOTTOM_CLEARANCE_M + PAD_EXTENT_M
    lift_dz: float = 0.16
    release_dz: float = FINGER_BOTTOM_CLEARANCE_M + PAD_EXTENT_M   # 相对桌面
    grip_ramp_steps: int = 8
    hold_steps: int = 15
    # **腕姿态对齐步数**（每相位前 `align_steps` 个规划点里把腕从实测姿态球面插值到 R_DOWN）。
    # 为什么必须有它：相位开始时臂停在 `START_ARM_POSE`（腕 ≈ Rz(180°)），而每个规划点都强制
    # `R_des=R_DOWN`，且 `ik_solve` 是**迭代到收敛**的（60 次 × max_dq 0.12 ⇒ 单点可走 7.2 rad）
    # ⇒ 第一个规划点就把腕猛拉 175.75°、gripper_link 位置跳 0.127 m（B2 2026-09-30 selftest 实测，
    # 团队 C03 阈值是 0.1 m / 30°，`clean` 段会删帧）。分摊到 15 步 ⇒ 11.7°/步、
    # 位置变化 ≤ |tip_rel|·Δθ = 0.0935×0.204 rad = 0.019 m，两项都在 C03 阈值内一个量级。
    # **不额外增加步数**（复用既有规划点），所以 300 步/10.2 s 的口径不变（裁定 65-2）。
    align_steps: int = 15
    # 交接点必须在**两臂可达带重叠区**内：实测 z=0.04 时重叠 x∈[-0.125,+0.125]、
    # z=0.10 时 x∈[-0.10,+0.125]（probe/reach_sweep.json）⇒ 取 |x|=0.06（留 4 cm 余量）。
    # B2 第一版写 0.15 ⇒ 越界，carry/place_lower 相位 IK 不收敛、正向 0/2 失败。
    place_x_abs: float = 0.06
    place_y: float = 0.5
    max_steps: int = 400
    phase_step_cap: int = 200         # 单相位数上限（规划出来的点数超过它 ⇒ 记 timeout，防死循环）


class ScriptedExpert:
    """相位机：**接近→下降→合爪→抬→搬→放→松开→撤→(对侧)接近→下降→合爪→抬→保持**。

    正/反向共用同一套代码，只有 `pick`/`receive`/`place_x` 符号不同（镜像）⇒ 与任务 3
    （同状态同 θ 换 goal）同构。每个相位都是"规划整段 → 逐步下发"，相位之间用**实测**状态重规划
    （闭环在相位级），所以方块被碰歪也能续上。
    """

    def __init__(self, direction: str, cfg: ExpertConfig = ExpertConfig(),
                 pad_extent: Optional[float] = None):
        self.direction = direction
        self.cfg = cfg
        self.pick = DIRECTION[direction]["pick"]
        self.receive = DIRECTION[direction]["receive"]
        self.goal_sign = DIRECTION[direction]["goal_x_sign"]
        self.pad_extent = pad_extent

    def place_target(self, box_spawn: np.ndarray) -> np.ndarray:
        return np.array([self.goal_sign * self.cfg.place_x_abs, self.cfg.place_y])

    # ---- 执行一段规划好的关节序列 ----
    def _exec(self, env, ctx, qs: Sequence[np.ndarray], side: str, label: str,
              grip: Dict[str, float], grip_ramp_to: Optional[float] = None) -> None:
        cfg = self.cfg
        n = len(qs)
        for i, q in enumerate(n and qs or []):
            if ctx["step_idx"] >= cfg.max_steps:
                raise BudgetExceeded(ctx["step_idx"], label)
            if grip_ramp_to is not None:
                grip[side] = grip[side] + (grip_ramp_to - grip[side]) * (1.0 / max(1, cfg.grip_ramp_steps))
            ctx["arm_tgt"][side] = np.asarray(q, dtype=float)
            ctx["emit"](label, {"plan_point": i + 1, "plan_n": n})
        ctx["phase_diag"].append({"label": label, "side": side, "n_steps": n,
                                  "grip_ramp_to": grip_ramp_to})

    def run(self, env: JointEnv, judge: SuccessJudge, record_images: bool = False,
            trace_every: int = 1) -> dict:
        cfg = self.cfg
        frames: List[dict] = []
        images: Dict[str, List[np.ndarray]] = {c: [] for c in env.render_cams}
        # **全精度**动作/状态序列（float64 容器装 float32 值 ⇒ 无精度损失）。
        # 为什么必须有它：`frames[*]["action14"]` 是 round(·,6) 的**报告用**副本，
        # 用它重放会在 300 步里累积差异 ⇒ 无法主张"逐位复现"。S1 出口判据 4
        # （`d_handoff_to_b2_20260929.md` §13.8-4：重放该 14 维动作序列在关节模型里能复现同一结果）
        # 要的是**下发过的那一串 float32**，所以这里另存一份不 round 的。
        actions_f64: List[np.ndarray] = []
        states_f64: List[np.ndarray] = []
        timeouts: List[str] = []
        phase_diag: List[dict] = []
        plan_diag: List[dict] = []
        box_spawn = env.box_pos()
        place_xy = self.place_target(box_spawn)
        grip = {"left": GRIP_OPEN_NORM, "right": GRIP_OPEN_NORM}
        ctx = {"step_idx": 0, "arm_tgt": {}, "emit": None, "phase_diag": phase_diag}

        def emit(phase: str, extra: Optional[dict] = None):
            if ctx["step_idx"] >= cfg.max_steps:
                raise BudgetExceeded(ctx["step_idx"], phase)
            a = env.make_action(ctx["arm_tgt"], grip)
            actions_f64.append(np.asarray(a, dtype=np.float64).copy())
            env.step(a)
            ctx["step_idx"] += 1
            states_f64.append(np.asarray(env.state14(), dtype=np.float64).copy())
            j = judge.observe(env, ctx["step_idx"], phase)
            rec = {"step": ctx["step_idx"], "phase": phase,
                   "action14": [round(float(x), 6) for x in a],
                   "state14": [round(float(x), 6) for x in env.state14()],
                   "qvel14": [round(float(x), 6) for x in env.qvel14()],
                   "box": j["box"], "env_reward": j["env_reward"],
                   "grip_norm": {"left": round(float(grip["left"]), 5),
                                 "right": round(float(grip["right"]), 5)},
                   "tip": {"left": [round(float(x), 5) for x in env.tip_pos("left")],
                           "right": [round(float(x), 5) for x in env.tip_pos("right")]}}
            if extra:
                rec.update(extra)
            if ctx["step_idx"] % trace_every == 0:
                frames.append(rec)
            if record_images:
                for c, im in env.render().items():
                    images[c].append(np.asarray(im))
            return j

        ctx["emit"] = emit
        planner = KinPlanner(env.xml_path)

        def sync_planner():
            q23 = np.asarray(env.physics.data.qpos, dtype=float).copy()
            planner.sync(q23)
            return {s: planner.q_arm(s) for s in ("left", "right")}

        def plan(side, tip_from, tip_to, label, stop_on_contact_with=None, other_q=None):
            # `R_from` 必须在 `plan_line` 动 qpos **之前**取：调用点都已先 `sync_planner()`，
            # 所以此刻 planner 的位姿 == env 的**实测**位姿（不是上一相位的规划目标）。
            R_from = planner.grip_pose(side)[1].copy()
            qs, info = planner.plan_line(side, tip_from, tip_to, R_DOWN, cfg.path_step_m,
                                         other_q=other_q, stop_on_contact_with=stop_on_contact_with,
                                         R_from=R_from, n_align=cfg.align_steps)
            info["label"] = label
            info["side"] = side
            info["tip_from"] = [round(float(x), 5) for x in np.asarray(tip_from)]
            info["tip_to"] = [round(float(x), 5) for x in np.asarray(tip_to)]
            plan_diag.append(info)
            if len(qs) > cfg.phase_step_cap:
                timeouts.append(label + ":plan_too_long")
                qs = qs[:cfg.phase_step_cap]
            if info["n_nonconverged_points"] > max(2, int(0.2 * max(1, info["n_points"]))):
                timeouts.append(label + ":ik_nonconverged")
            return qs

        try:
          # ---- 0 settle：方块从 z=0.05 落到桌面；**同时**两臂原地把腕转到 R_DOWN ----
          # 这 12 步不进数据集 ⇒ 175° 的腕对齐不落在任何一帧里（理由见 `plan_align`）。
          # 两臂各自原地转（grip 位置钉住），互不干扰；方块在 x∈[0,0.2]、z≈0.02，
          # 而腕扫过的球面半径只有 |tip_rel|=0.0935 m、grip 在 |x|≈0.317/z≈0.295 ⇒ 碰不到。
          sync_planner()
          align_q: Dict[str, List[np.ndarray]] = {}
          for s in ("left", "right"):
              qs_a, info_a = planner.plan_align(s, R_DOWN, cfg.settle_steps)
              plan_diag.append(info_a)
              align_q[s] = qs_a
          for k in range(cfg.settle_steps):
              ctx["arm_tgt"] = {s: align_q[s][k] for s in ("left", "right")}
              grip = {"left": GRIP_OPEN_NORM, "right": GRIP_OPEN_NORM}
              emit("settle")
          box_rest = env.box_pos()
          other = sync_planner()

          # ---- 1-4 抓取臂：接近 → 下降 → 合爪 → 抬 ----
          tip0 = planner.tip(self.pick)
          above = np.array([box_rest[0], box_rest[1], box_rest[2] + cfg.pre_grasp_dz])
          self._exec(env, ctx, plan(self.pick, tip0, above, "pick_approach", other_q=other),
                     self.pick, "pick_approach", grip)
          grasp = np.array([box_rest[0], box_rest[1], box_rest[2] + cfg.grasp_dz])
          other = sync_planner()
          tip1 = planner.tip(self.pick)
          self._exec(env, ctx, plan(self.pick, tip1, grasp, "pick_descend",
                                    stop_on_contact_with="red_box", other_q=other),
                     self.pick, "pick_descend", grip)
          # 合爪（位置保持：用实测角当目标）
          for k in range(cfg.grip_ramp_steps):
            if ctx["step_idx"] >= cfg.max_steps:
                raise BudgetExceeded(ctx["step_idx"], "pick_close")
            grip[self.pick] = GRIP_OPEN_NORM + (GRIP_CLOSE_NORM - GRIP_OPEN_NORM) * ((k + 1) / cfg.grip_ramp_steps)
            ctx["arm_tgt"] = {s: env.qpos16()[ARM_DOF[s]] for s in ("left", "right")}
            emit("pick_close", {"grip_ramp": round(float(grip[self.pick]), 5)})
          phase_diag.append({"label": "pick_close", "side": self.pick, "n_steps": cfg.grip_ramp_steps})
          other = sync_planner()
          tip2 = planner.tip(self.pick)
          lift = np.array([box_rest[0], box_rest[1], box_rest[2] + cfg.lift_dz])
          self._exec(env, ctx, plan(self.pick, tip2, lift, "pick_lift", other_q=other),
                     self.pick, "pick_lift", grip)

          # ---- 5-7 搬运 → 放下 → 松开 ----
          other = sync_planner()
          tip3 = planner.tip(self.pick)
          carry = np.array([place_xy[0], place_xy[1], box_rest[2] + cfg.lift_dz])
          self._exec(env, ctx, plan(self.pick, tip3, carry, "carry", other_q=other),
                     self.pick, "carry", grip)
          other = sync_planner()
          tip4 = planner.tip(self.pick)
          lower = np.array([place_xy[0], place_xy[1], TABLE_Z + cfg.release_dz])
          self._exec(env, ctx, plan(self.pick, tip4, lower, "place_lower", other_q=other),
                     self.pick, "place_lower", grip)
          for k in range(cfg.grip_ramp_steps):
            if ctx["step_idx"] >= cfg.max_steps:
                raise BudgetExceeded(ctx["step_idx"], "place_release")
            grip[self.pick] = GRIP_CLOSE_NORM + (GRIP_OPEN_NORM - GRIP_CLOSE_NORM) * ((k + 1) / cfg.grip_ramp_steps)
            ctx["arm_tgt"] = {s: env.qpos16()[ARM_DOF[s]] for s in ("left", "right")}
            emit("place_release", {"grip_ramp": round(float(grip[self.pick]), 5)})
          phase_diag.append({"label": "place_release", "side": self.pick, "n_steps": cfg.grip_ramp_steps})
          # ---- 8 撤（抬开，避免挡接收臂） ----
          other = sync_planner()
          tip5 = planner.tip(self.pick)
          # 撤退方向 = 朝抓取臂自己的基座（-goal_sign 方向），别悬在交接点正上方挡接收臂
          retract = np.array([place_xy[0] - self.goal_sign * 0.14, place_xy[1],
                              TABLE_Z + cfg.lift_dz + 0.08])
          self._exec(env, ctx, plan(self.pick, tip5, retract, "pick_retract", other_q=other),
                     self.pick, "pick_retract", grip)

          # ---- 9-13 接收臂（用**实测**方块位置重规划） ----
          box_now = env.box_pos()
          other = sync_planner()
          tip6 = planner.tip(self.receive)
          above2 = np.array([box_now[0], box_now[1], box_now[2] + cfg.pre_grasp_dz])
          self._exec(env, ctx, plan(self.receive, tip6, above2, "recv_approach", other_q=other),
                     self.receive, "recv_approach", grip)
          other = sync_planner()
          tip7 = planner.tip(self.receive)
          grasp2 = np.array([box_now[0], box_now[1], box_now[2] + cfg.grasp_dz])
          self._exec(env, ctx, plan(self.receive, tip7, grasp2, "recv_descend",
                                    stop_on_contact_with="red_box", other_q=other),
                     self.receive, "recv_descend", grip)
          for k in range(cfg.grip_ramp_steps):
            if ctx["step_idx"] >= cfg.max_steps:
                raise BudgetExceeded(ctx["step_idx"], "recv_close")
            grip[self.receive] = GRIP_OPEN_NORM + (GRIP_CLOSE_NORM - GRIP_OPEN_NORM) * ((k + 1) / cfg.grip_ramp_steps)
            ctx["arm_tgt"] = {s: env.qpos16()[ARM_DOF[s]] for s in ("left", "right")}
            emit("recv_close", {"grip_ramp": round(float(grip[self.receive]), 5)})
          phase_diag.append({"label": "recv_close", "side": self.receive, "n_steps": cfg.grip_ramp_steps})
          other = sync_planner()
          tip8 = planner.tip(self.receive)
          box_now2 = env.box_pos()
          lift2 = np.array([box_now2[0], box_now2[1], box_now2[2] + cfg.lift_dz])
          self._exec(env, ctx, plan(self.receive, tip8, lift2, "recv_lift", other_q=other),
                     self.receive, "recv_lift", grip)
          for _ in range(cfg.hold_steps):
            if ctx["step_idx"] >= cfg.max_steps:
                raise BudgetExceeded(ctx["step_idx"], "recv_hold")
            ctx["arm_tgt"] = {s: env.qpos16()[ARM_DOF[s]] for s in ("left", "right")}
            emit("recv_hold")
          phase_diag.append({"label": "recv_hold", "side": self.receive, "n_steps": cfg.hold_steps})
          budget_exceeded = None
        except BudgetExceeded as be:
          timeouts.append("BUDGET_EXCEEDED:" + be.phase)
          budget_exceeded = {"at_step": be.step_idx, "phase": be.phase}

        return {
            "direction": self.direction, "pick_side": self.pick, "receive_side": self.receive,
            "n_steps": ctx["step_idx"], "phases_timeouts": timeouts, "phase_diag": phase_diag,
            "plan_diag": plan_diag, "budget_exceeded": budget_exceeded,
            "box_spawn_xyz": [round(float(x), 5) for x in box_spawn],
            "box_rest_after_settle_xyz": [round(float(x), 5) for x in box_rest],
            "place_target_xy": [round(float(x), 5) for x in place_xy],
            "frames": frames,
            "images": (images if any(len(v) for v in images.values()) else None),
            "actions_f64": (np.asarray(actions_f64, dtype=np.float64).reshape(-1, 14)
                            if actions_f64 else np.zeros((0, 14))),
            "states_f64": (np.asarray(states_f64, dtype=np.float64).reshape(-1, 14)
                           if states_f64 else np.zeros((0, 14))),
            "config": {k: (v if not isinstance(v, np.ndarray) else v.tolist())
                       for k, v in cfg.__dict__.items()},
            "pad_extent_m": self.pad_extent,
        }


def run_episode(direction: str, seed: int, dt: float = 0.034, cfg: ExpertConfig = ExpertConfig(),
                jcfg: JudgeConfig = JudgeConfig(), record_images: bool = False,
                render_cams: Sequence[str] = (), img_h: int = 480, img_w: int = 640,
                box_pose_override: Optional[np.ndarray] = None,
                action_noise: float = 0.0) -> dict:
    box = (np.asarray(box_pose_override, dtype=float) if box_pose_override is not None
           else sample_box_pose_seeded(seed, direction))
    env = JointEnv(dt, box, render_cams=render_cams, img_h=img_h, img_w=img_w)
    judge = SuccessJudge(direction, jcfg, box_spawn=box)
    t0 = time.time()
    try:
        env.reset()
        exp = ScriptedExpert(direction, cfg)
        if action_noise > 0.0:
            # 变异体：把随机动作当"示范"（S1 判据 5-③）⇒ 专家自证闸必须红
            rng = np.random.RandomState(seed)
            frames = []
            rand_actions: List[np.ndarray] = []
            rand_states: List[np.ndarray] = []
            for i in range(cfg.max_steps):
                a = rng.uniform(-1, 1, size=14).astype(np.float32)
                a[6] = rng.uniform(0, 1); a[13] = rng.uniform(0, 1)
                env.step(a)
                j = judge.observe(env, i + 1, "random_mutation")
                frames.append({"step": i + 1, "phase": "random_mutation",
                               "action14": [round(float(x), 6) for x in a],
                               "state14": [round(float(x), 6) for x in env.state14()],
                               "qvel14": [round(float(x), 6) for x in env.qvel14()],
                               "box": j["box"], "env_reward": j["env_reward"],
                               "grip_norm": {"left": float(a[6]), "right": float(a[13])},
                               "tip": {"left": [round(float(x), 5) for x in env.tip_pos("left")],
                                       "right": [round(float(x), 5) for x in env.tip_pos("right")]}})
                rand_actions.append(np.asarray(a, dtype=np.float64).copy())
                rand_states.append(np.asarray(env.state14(), dtype=np.float64).copy())
            res = {"direction": direction, "pick_side": DIRECTION[direction]["pick"],
                   "receive_side": DIRECTION[direction]["receive"], "n_steps": len(frames),
                   "phases_timeouts": [], "box_spawn_xyz": [float(x) for x in box],
                   "box_rest_after_settle_xyz": [float(x) for x in env.box_pos()],
                   "place_target_xy": None, "frames": frames,
                   "images": None,
                   "actions_f64": (np.asarray(rand_actions, dtype=np.float64).reshape(-1, 14)
                                   if rand_actions else np.zeros((0, 14))),
                   "states_f64": (np.asarray(rand_states, dtype=np.float64).reshape(-1, 14)
                                  if rand_states else np.zeros((0, 14))),
                   "config": {"mutation": "random_actions", "action_noise": action_noise}}
        else:
            res = exp.run(env, judge, record_images=record_images)
        res["wall_s"] = round(time.time() - t0, 3)
        res["seed"] = seed
        res["dt"] = dt
        res["box_pose_cmd"] = [float(x) for x in box]
        res["judge"] = judge.verdict()
        res["live_timing"] = {"control_timestep_s": float(env.env.control_timestep()
                                                          if callable(env.env.control_timestep)
                                                          else env.env.control_timestep),
                              "n_sub_steps": int(getattr(env.env, "_n_sub_steps", -1)),
                              "measured_hz": None}
        ct = res["live_timing"]["control_timestep_s"]
        res["live_timing"]["measured_hz"] = round(1.0 / ct, 6) if ct else None
        return res
    finally:
        env.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="双向各跑 --n-seeds 个 seed，不渲染，打印成功率")
    ap.add_argument("--direction", default="forward", choices=["forward", "reverse", "both"])
    ap.add_argument("--n-seeds", type=int, default=3)
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--dt", type=float, default=0.034)
    ap.add_argument("--max-dq", type=float, default=None)
    ap.add_argument("--grasp-dz", type=float, default=None)
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--mutation", default=None,
                    choices=["random-actions", "reverse-direction-flipped", "dt-back-to-50hz"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cfg = ExpertConfig()
    if a.max_dq is not None:
        cfg.max_dq = a.max_dq
    if a.grasp_dz is not None:
        cfg.grasp_dz = a.grasp_dz
    if a.max_steps is not None:
        cfg.max_steps = a.max_steps
    if a.mutation == "dt-back-to-50hz":
        a.dt = 0.02
    dirs = ["forward", "reverse"] if a.direction == "both" else [a.direction]
    rows = []
    for d in dirs:
        for i in range(a.n_seeds):
            seed = a.seed0 + i
            kw = {}
            if a.mutation == "random-actions":
                kw["action_noise"] = 1.0
            jcfg = JudgeConfig()
            if a.mutation == "reverse-direction-flipped":
                # 把判据的方向写反（S1 判据 5-②）：接收侧与目标符号互换
                DIRECTION[d]["receive"], DIRECTION[d]["pick"] = DIRECTION[d]["pick"], DIRECTION[d]["receive"]
                DIRECTION[d]["goal_x_sign"] = -DIRECTION[d]["goal_x_sign"]
            try:
                r = run_episode(d, seed, dt=a.dt, cfg=cfg, jcfg=jcfg, **kw)
            except Exception:
                rows.append({"direction": d, "seed": seed, "error": traceback.format_exc(limit=6)})
                continue
            j = r["judge"]
            rows.append({"direction": d, "seed": seed, "verdict": j["verdict"], "ok": j["ok"],
                         "failure_class": j["failure_class"], "n_steps": r["n_steps"],
                         "wall_s": r["wall_s"], "hz": r["live_timing"]["measured_hz"],
                         "max_held": j["evidence"]["max_held_run_steps"],
                         "box_final": j["evidence"]["final_box_xyz"],
                         "env_reward4": j["evidence"]["env_reward4_seen"],
                         "max_box_speed": j["evidence"]["max_box_speed_mps"],
                         "max_box_speed_phase": j["evidence"]["max_box_speed_phase"],
                         "picker_held": j["evidence"]["max_picker_held_run_steps"],
                         "displacement_m": j["evidence"]["box_horizontal_displacement_m"],
                         "on_goal_side_diag": j["evidence"]["on_goal_side_x_sign_diagnostic_only"],
                         "box_spawn": j["evidence"]["box_spawn_xyz"],
                         "budget_exceeded": r.get("budget_exceeded"),
                         "n_plan_nonconverged": sum(d.get("n_nonconverged_points", 0)
                                                    for d in r.get("plan_diag", [])),
                         "timeouts": r["phases_timeouts"],
                         "why": j["why"][:150]})
            print(f"[{d} seed={seed}] {j['verdict']:8s} steps={r['n_steps']:4d} "
                  f"wall={r['wall_s']:6.2f}s held={j['evidence']['max_held_run_steps']:3d} "
                  f"box={j['evidence']['final_box_xyz']} rew4={j['evidence']['env_reward4_seen']} "
                  f"cls={j['failure_class']} to={r['phases_timeouts']}")
    n_ok = sum(1 for r in rows if r.get("ok") is True)
    n_bad = sum(1 for r in rows if r.get("ok") is False)
    n_unk = sum(1 for r in rows if r.get("ok") is None)
    print(f"== summary: success={n_ok} failure={n_bad} unknown={n_unk} total={len(rows)} "
          f"success_rate={n_ok/len(rows) if rows else None}")
    steps = [r["n_steps"] for r in rows if isinstance(r.get("n_steps"), int)]
    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        mod = Path(__file__).resolve()
        mst = mod.stat()
        p.write_text(json.dumps({
            "generated_at": now(), "args": sys.argv[1:],
            # **模块身份**：自证产物必须能对上"当时那一份模块"。生成器
            # （scripts/b2_s1_generate_dataset.py 的 self_verify_evidence）会把这个 sha 与它
            # 自己 import 的那份 b2_s1_scripted_expert.py 比对，不一致 ⇒ 判红，不许拿陈旧证据充数
            # （裁定 50.2 计数类主张同批落 (mtime,计数,命令原文) / 裁定 72 取证纪律）。
            "module_identity": {
                "path": "scripts/b2_s1_scripted_expert.py",
                "sha256_12": hashlib.sha256(mod.read_bytes()).hexdigest()[:12],
                "sha256_full": hashlib.sha256(mod.read_bytes()).hexdigest(),
                "bytes": mst.st_size,
                "mtime": datetime.fromtimestamp(mst.st_mtime, CST).isoformat(timespec="seconds"),
                "python": sys.executable,
                "versions_note": "同批落 (mtime, 计数, 命令原文)"},
            "rows": rows,
            "summary": {
                "success": n_ok, "failure": n_bad, "unknown": n_unk, "total": len(rows),
                "success_rate": (n_ok / len(rows)) if rows else None,
                "n_steps_min": min(steps) if steps else None,
                "n_steps_max": max(steps) if steps else None,
                "n_steps_mean": round(sum(steps) / len(steps), 2) if steps else None,
                "settle_steps_dropped": cfg.settle_steps,
                "n_frames_recorded_max": (max(steps) - cfg.settle_steps) if steps else None,
                "registered_max_episode_steps": 300,
                "n_over_registered_horizon": sum(1 for x in steps if x > 300),
                "horizon_ruling": "裁定 65-2（max_episode_steps 维持 300 = 10.2 s @29.4118 Hz）",
                "n_plan_nonconverged_total": sum(r.get("n_plan_nonconverged", 0) for r in rows),
                "n_with_timeouts": sum(1 for r in rows if r.get("timeouts"))}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def reach_sweep(dt: float = 0.034, xs=None, zs=(0.04, 0.10, 0.16, 0.22), y: float = 0.5) -> dict:
    """**实测两臂在"指尖朝下"姿态下的可达带**（决定交接点 place_x 的唯一依据，不猜）。

    为什么要测：B2 第一版把 `place_x_abs` 写成 0.15（与生成范围同量级），实测
    `carry`/`place_lower` 相位 IK **不收敛**（`plan_diag.n_nonconverged_points`），
    正向 0/2 失败；反向 2/2 成功 ⇒ 是**左右不对称的可达域**问题，不是判据问题。
    两臂基座在 x=∓0.469（`assets/vx300s_{left,right}.xml:3`），故 x=±0.15 对**对侧**臂
    意味着 0.62 m 的伸展，远超 ViperX300 的臂展。
    """
    import gym_aloha
    pkg = Path(gym_aloha.__file__).resolve().parent / "assets"
    xml = str(pkg / "bimanual_viperx_transfer_cube.xml")
    kp = KinPlanner(xml)
    q = np.zeros(23)
    q[:16] = np.array([0, -0.96, 1.16, 0, -0.3, 0, 0.02239, -0.02239,
                       0, -0.96, 1.16, 0, -0.3, 0, 0.02239, -0.02239])
    q[16:23] = np.array([0.15, 0.5, 0.05, 1, 0, 0, 0])
    xs = xs if xs is not None else [round(v, 3) for v in np.arange(-0.30, 0.301, 0.025)]
    out = {"xml": xml, "y": y, "zs": list(zs), "xs": xs, "grid": {}, "summary": {}}
    for side in ("left", "right"):
        out["grid"][side] = {}
        base_x = -0.469 if side == "left" else 0.469
        for z in zs:
            row = {}
            for x in xs:
                kp.sync(q)
                info = kp.ik_solve(side, np.array([x, y, z]), R_DOWN, iters=250, tol_pos=3e-3,
                                   tol_ori=0.05)
                row[f"x={x:+.3f}"] = {"converged": info["converged"],
                                      "e_pos_m": info["e_pos_m"], "e_ori_rad": info["e_ori_rad"],
                                      "n_joints_at_limit": info["n_joints_at_limit"],
                                      "reach_m": round(abs(x - base_x), 4)}
            out["grid"][side][f"z={z:.2f}"] = row
        # 可达带 = 该高度上连续收敛的 x 区间
        bands = {}
        for z in zs:
            row = out["grid"][side][f"z={z:.2f}"]
            ok = [x for x in xs if row[f"x={x:+.3f}"]["converged"]]
            bands[f"z={z:.2f}"] = {"n_converged": len(ok),
                                   "x_min": (min(ok) if ok else None),
                                   "x_max": (max(ok) if ok else None),
                                   "base_x": base_x}
        out["summary"][side] = bands
    ov = {}
    for z in zs:
        l = out["summary"]["left"][f"z={z:.2f}"]
        r = out["summary"]["right"][f"z={z:.2f}"]
        if l["x_min"] is not None and r["x_min"] is not None:
            lo = max(l["x_min"], r["x_min"]); hi = min(l["x_max"], r["x_max"])
            ov[f"z={z:.2f}"] = {"overlap_x": [lo, hi] if lo <= hi else None,
                                "left_band": [l["x_min"], l["x_max"]],
                                "right_band": [r["x_min"], r["x_max"]]}
        else:
            ov[f"z={z:.2f}"] = {"overlap_x": None, "left_band": None, "right_band": None}
    out["both_arms_overlap"] = ov
    return out
