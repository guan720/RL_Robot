#!/usr/bin/env python
"""最小抓取链路 · 单臂仿真环境包装（robosuite PickPlaceCan / Panda / OSC_POSE）。

隔离纪律：本目录只 import 第三方库（robosuite / numpy），不 import 仓内其它线的任何模块。

──────────────────────── 契约 CONTRACT（唯一真源，改动必须同步 mg_probe.py） ────────────────────────
动作 action (7,) float32，语义 = robosuite 默认控制器 OSC_POSE + 夹爪：
    [0:3] 末端位置增量 dx, dy, dz      ∈ [-1, 1]；控制器 output_max=0.05 m 但 ramp_ratio=0.2 +
                                     kp=150 阻抗控制，**实测有效增益 ≈ 11 mm/控制步**（mg_probe --axes）
    [3:6] 末端姿态增量（轴角）          ∈ [-1, 1]，本链路恒为 0（不做姿态控制）
    [6]   夹爪                          -1 = 闭合，+1 = 张开（robosuite 约定）
状态 observation.state (8,) float32：
    [0:3] robot0_eef_pos     末端位置（世界系，米）
    [3:7] robot0_eef_quat    末端姿态四元数（wxyz，robosuite 约定）
    [7]   gripper_width      开口宽度 = sum(|robot0_gripper_qpos|)；空手张开 ≈ 0.08，夹住 can ≈ 0.05
图像（uint8, HWC, RGB, 已上下翻转——robosuite 原始渲染是倒的）：
    agentview           -> observation.images.base_0_rgb        （第三人称）
    robot0_eye_in_hand  -> observation.images.left_wrist_0_rgb  （腕部）
图像键名沿用 π₀.₅ 基座的相机命名，将来换基座不用改数据集。
成功判定：**只用 robosuite 真值** env._check_success()
    = can 落入 bin2 的右上象限（object_to_id["can"]=3）且 z ∈ (bin2_z, bin2_z+0.1) 且末端已离开 can。
    奖励/模型输出/自写几何判据一律不参与「成功」定义。
固定初态：每次 reset 前把 env.rng 设为同一个 seed（物体、篮子、机械臂关节的随机性都出自这个 rng）
    → 每局完全相同的初态；由 mg_probe.py --determinism 逐位自证（图像哈希也要一致）。
    要随机位姿时传 seed=<不同值>（第 2 阶段才打开）。
──────────────────────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import hashlib
import os

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402

# ── 固定常数（第 1 阶段：固定物体 + 固定初姿）──
FIXED_SEED = 0
HORIZON = 400          # 控制步上限（control_freq=20 -> 20 s 仿真）
CONTROL_FREQ = 20      # Hz；数据集 fps 必须与它一致
IMG_SIZE = 224         # π₀.₅ 原生分辨率
ROBOT = "Panda"        # 单臂
SUITE_TASK = "PickPlaceCan"   # = single_object_mode 2 + object_type "can"，物体固定为 can

CAM_BASE = "agentview"
CAM_WRIST = "robot0_eye_in_hand"

STATE_KEY = "observation.state"
ACTION_KEY = "action"
IMG_KEY_BASE = "observation.images.base_0_rgb"
IMG_KEY_WRIST = "observation.images.left_wrist_0_rgb"
CAM_TO_KEY = {CAM_BASE: IMG_KEY_BASE, CAM_WRIST: IMG_KEY_WRIST}

STATE_NAMES = ["eef_x", "eef_y", "eef_z", "eef_qw", "eef_qx", "eef_qy", "eef_qz", "gripper_width"]
ACTION_NAMES = ["dx", "dy", "dz", "droll", "dpitch", "dyaw", "gripper"]
STATE_DIM = len(STATE_NAMES)     # 8
ACTION_DIM = len(ACTION_NAMES)   # 7

TASK = "Pick up the can and place it into the bin."

OBJ_POS_KEY = "Can_pos"
# 夹爪宽度实测值（sum(|gripper_qpos|)，mg_probe --gripper）：
GRIP_OPEN_WIDTH = 0.0788    # action=-1 张开到底
GRIP_AT_RESET = 0.0417      # reset 后的初始开口
GRIP_EMPTY_CLOSE = 0.0010   # action=+1 空合到底（没夹到东西）
GRIP_HOLD_WIDTH = 0.012     # 「夹到东西」阈值：夹住 can（半径 2.5cm）时约 0.05，远大于空合的 0.001

# ── 严格成功判定所需的物体几何与阈值 ──
CAN_HALF_HEIGHT = 0.0603    # can 半高（实测：静置桌面 can 中心 z=0.8603，桌面 z=0.8）
BIN_FLOOR_OFFSET = 0.0      # 实测：can 落在篮里静止时中心 z=0.8603 = bin_z(0.8) + can 半高，篮底与桌面齐平
SETTLE_Z_TOL = 0.025        # can 中心与「篮底静止高度」的容差
SETTLE_SPEED = 0.05         # m/s，低于它算静止
RELEASE_DIST = 0.05         # m，末端离 can 超过它才算真的松手了
SUCCESS_HOLD_STEPS = 10     # 严格成功要连续保持 10 个控制步（0.5 s），杜绝「掉进去弹一下」的假阳性


class SingleArmGraspEnv:
    """robosuite PickPlaceCan 的最小包装：固定初态 + 统一 obs/action + 只用环境真值判成功。"""

    def __init__(
        self,
        img_size: int = IMG_SIZE,
        horizon: int = HORIZON,
        control_freq: int = CONTROL_FREQ,
        cameras: tuple[str, ...] = (CAM_BASE, CAM_WRIST),
        seed: int = FIXED_SEED,
        robot: str = ROBOT,
    ) -> None:
        import robosuite  # 延迟 import：让 --help 之类的调用不必付渲染库加载代价

        for cam in cameras:
            if cam not in CAM_TO_KEY:
                raise ValueError(f"未知相机 {cam}，可选 {tuple(CAM_TO_KEY)}")
        self.cameras = tuple(cameras)
        self.img_size = int(img_size)
        self.horizon = int(horizon)
        self.control_freq = int(control_freq)
        self.seed = int(seed)
        self.fps = self.control_freq

        self.env = robosuite.make(
            SUITE_TASK,
            robots=robot,
            has_renderer=False,
            has_offscreen_renderer=True,
            use_camera_obs=True,
            camera_names=list(self.cameras),
            camera_heights=self.img_size,
            camera_widths=self.img_size,
            use_object_obs=True,
            control_freq=self.control_freq,
            horizon=self.horizon,
            hard_reset=False,        # 复用 sim，reset 快；确定性由下面的 rng 固定保证
            reward_shaping=False,    # 纪律：成功只用真值判，奖励不参与判定
        )
        # robosuite 1.5.2 没有 robot_init_qpos_noise 这个 kwarg；物体与机械臂初态的随机性
        # 全部来自 self.rng，所以「固定初态」= 每次 reset 前把 rng 设成同一个 seed（探针自证）。
        self.env.deterministic_reset = False
        self._steps = 0
        self._last_obs: dict | None = None
        self._raw: dict | None = None
        self._prev_obj_pos: np.ndarray | None = None
        self._hold = 0
        self._ever_success = False      # 最近一次 robosuite 原始 obs（真值属性从这里读）

    # ── 生命周期 ────────────────────────────────────────────────────────────
    def _seed_randomness(self, seed: int) -> None:
        """把**所有**随机源钉到同一个 seed —— 「固定初始位姿」的真正实现处。

        robosuite 1.5.2 的坑（探针实测）：物体摆放**不走** env.rng，而是每个 placement sampler
        在构造时自己 `np.random.default_rng()`（无 seed -> 取 OS 熵）。只设 env.rng 的结果是
        机械臂初姿可复现、物体位置每次都变（同 seed 两次 reset，can 差 4 cm）。
        所以三个随机源都要设：env.rng（机械臂初姿）、sampler.rng（物体摆放）、np.random（兜底）。
        """
        self.env.rng = np.random.default_rng(seed)
        initializer = getattr(self.env, "placement_initializer", None)
        samplers: list = []
        if initializer is not None:
            if hasattr(initializer, "rng"):
                samplers.append(initializer)
            samplers.extend(list(getattr(initializer, "samplers", {}).values()))
        for i, sampler in enumerate(samplers):
            if hasattr(sampler, "rng"):
                sampler.rng = np.random.default_rng([seed, 1000 + i])
        np.random.seed(int(seed) % (2 ** 32))

    def reset(self, seed: int | None = None) -> dict:
        """固定 seed -> 固定初态（物体、篮子、机械臂关节、图像逐位一致；由探针自证）。"""
        use_seed = self.seed if seed is None else int(seed)
        self._seed_randomness(use_seed)
        obs = self.env.reset()
        self._steps = 0
        self._hold = 0
        self._ever_success = False
        self._last_obs = self._pack(obs)
        self._prev_obj_pos = self.object_pos.copy()
        return self._last_obs

    def step(self, action) -> tuple[dict, float, bool, bool, dict]:
        """gymnasium 风格五元组：(obs, reward, terminated, truncated, info)。"""
        act = np.asarray(action, dtype=np.float64).reshape(-1)
        if act.shape[0] != ACTION_DIM:
            raise ValueError(f"动作必须是 {ACTION_DIM} 维，收到 {act.shape}")
        if not np.all(np.isfinite(act)):
            act = np.nan_to_num(act, nan=0.0, posinf=1.0, neginf=-1.0)
        act = np.clip(act, -1.0, 1.0)   # OSC_POSE 输入域就是 [-1,1]，越界会被控制器截断，这里显式截

        obs, reward, _done, _info = self.env.step(act)
        self._steps += 1
        packed = self._pack(obs)
        self._last_obs = packed

        raw_success = bool(self.env._check_success())      # robosuite 环境真值（必要条件）
        # 但 robosuite 的判定窗口很宽：can 只要在象限 xy 内且 z ∈ (bin_z, bin_z+0.1) 就算数，
        # 于是「搬运途中滑脱、can 自由落体穿过该窗口」也会被判成功（2026-09-30 实测踩到）。
        # 所以严格成功 = 环境真值 AND 物理落定 AND 连续保持，两个数都记进 info，谁也不隐藏。
        obj_speed = (float(np.linalg.norm(self.object_pos - self._prev_obj_pos)) * self.control_freq
                     if self._prev_obj_pos is not None else float("inf"))
        resting_z = float(self.bin_pos[2]) + CAN_HALF_HEIGHT + BIN_FLOOR_OFFSET
        settled = (abs(float(self.object_pos[2]) - resting_z) < SETTLE_Z_TOL
                   and obj_speed < SETTLE_SPEED
                   and self.gripper_width > 0.05
                   and float(np.linalg.norm(self.eef_pos - self.object_pos)) > RELEASE_DIST)
        self._hold = self._hold + 1 if (raw_success and settled) else 0
        success = self._ever_success or self._hold >= SUCCESS_HOLD_STEPS
        self._ever_success = success
        self._prev_obj_pos = self.object_pos.copy()
        truncated = self._steps >= self.horizon
        info = {
            "success": success,
            "success_raw": raw_success,
            "settled": settled,
            "hold": int(self._hold),
            "object_speed": obj_speed,
            "resting_z": resting_z,
            "reward": float(reward),
            "steps": self._steps,
            "object_pos": self.object_pos.tolist(),
            "eef_pos": self.eef_pos.tolist(),
            "gripper_width": float(self.gripper_width),
            "target_xy": self.target_xy.tolist(),
            "dist_to_target_xy": float(np.linalg.norm(self.object_pos[:2] - self.target_xy)),
        }
        return packed, float(reward), success, truncated, info

    def close(self) -> None:
        try:
            self.env.close()
        except Exception:
            pass

    # ── 观测打包 ────────────────────────────────────────────────────────────
    def _pack(self, obs: dict) -> dict:
        self._raw = obs
        eef_pos = np.asarray(obs["robot0_eef_pos"], dtype=np.float32)
        eef_quat = np.asarray(obs["robot0_eef_quat"], dtype=np.float32)   # wxyz
        grip_qpos = np.asarray(obs["robot0_gripper_qpos"], dtype=np.float32)
        # 两指 qpos 反号（开 = ±0.04），求和恒为 0，必须取绝对值求和才是开口宽度
        width = float(np.abs(grip_qpos).sum())
        state = np.concatenate([eef_pos, eef_quat, np.array([width], dtype=np.float32)]).astype(np.float32)
        if state.shape[0] != STATE_DIM:
            raise ValueError(f"状态维度不是 {STATE_DIM}：{state.shape}")

        out: dict = {STATE_KEY: state}
        for cam in self.cameras:
            img = np.asarray(obs[f"{cam}_image"], dtype=np.uint8)
            out[CAM_TO_KEY[cam]] = np.ascontiguousarray(img[::-1])   # robosuite 渲染上下颠倒
        return out

    # ── 只读真值（给脚本专家 / 评测 / 探针用；策略观测里不含这些）──────────────
    @property
    def object_pos(self) -> np.ndarray:
        return np.asarray(self._last_obs_raw[OBJ_POS_KEY], dtype=np.float64)

    @property
    def eef_pos(self) -> np.ndarray:
        return np.asarray(self._last_obs_raw["robot0_eef_pos"], dtype=np.float64)

    @property
    def gripper_width(self) -> float:
        return float(np.abs(np.asarray(self._last_obs_raw["robot0_gripper_qpos"], dtype=np.float64)).sum())

    def init_state_snapshot(self) -> dict:
        """当前（reset 之后的）初态真值快照：固定初姿的**声明式证据**。"""
        sim = self.env.sim
        can_quat = np.asarray(self._last_obs_raw.get("Can_quat", [np.nan] * 4), dtype=np.float64)
        return {
            "seed": self.seed,
            "object_pos": np.round(self.object_pos, 6).tolist(),
            "object_quat_wxyz": np.round(can_quat, 6).tolist(),
            "eef_pos": np.round(self.eef_pos, 6).tolist(),
            "bin_pos": np.round(self.bin_pos, 6).tolist(),
            "target_xy": np.round(self.target_xy, 6).tolist(),
            "gripper_width": round(self.gripper_width, 6),
            "robot_qpos_hash": hashlib.sha256(np.ascontiguousarray(sim.data.qpos).tobytes()).hexdigest()[:16],
        }

    @property
    def bin_pos(self) -> np.ndarray:
        """目标篮（2x2 篮格）的原点坐标。"""
        return np.asarray(self.env.bin2_pos, dtype=np.float64)

    @property
    def target_xy(self) -> np.ndarray:
        """can 的目标象限中心（右上象限，object_to_id['can']=3），用 robosuite 自己的真值表。"""
        idx = self.env.object_to_id["can"]
        return np.asarray(self.env.target_bin_placements[idx], dtype=np.float64)[:2]

    @property
    def success_raw(self) -> bool:
        """robosuite 环境真值（宽口径）。"""
        return bool(self.env._check_success())

    @property
    def success(self) -> bool:
        """严格成功：环境真值 + 物理落定 + 连续保持（本链路所有指标只用这个）。"""
        return self._ever_success

    # 内部：保留最近一次原始 obs（真值属性从这里读，避免重复解析）
    @property
    def _last_obs_raw(self) -> dict:
        if self._raw is None:
            raise RuntimeError("还没有 reset()")
        return self._raw

    # ── 渲染（评测录视频用）──────────────────────────────────────────────────
    def render(self, cam: str = CAM_BASE) -> np.ndarray:
        return np.ascontiguousarray(np.asarray(self._last_obs_raw[f"{cam}_image"], dtype=np.uint8)[::-1])

    # 元信息
    def contract(self) -> dict:
        return {
            "suite_task": SUITE_TASK,
            "robot": ROBOT,
            "controller": "OSC_POSE (robosuite default) + gripper",
            "action_dim": ACTION_DIM,
            "action_names": ACTION_NAMES,
            "action_range": [-1.0, 1.0],
            "controller_output_max_m": 0.05,
            "controller_ramp_ratio": 0.2,
            "measured_step_gain_m_at_saturation": 0.0111,   # mg_probe --axes 实测，勿凭 output_max 推断
            "gripper_semantics": "-1 = close, +1 = open",
            "state_dim": STATE_DIM,
            "state_names": STATE_NAMES,
            "state_units": "meter / wxyz quaternion / meter(opening width)",
            "cameras": list(self.cameras),
            "camera_keys": [CAM_TO_KEY[c] for c in self.cameras],
            "img_size": self.img_size,
            "img_flip_vertical": True,
            "fps": self.fps,
            "horizon": self.horizon,
            "fixed_seed": self.seed,
            "success_criterion": ("robosuite env._check_success() AND 物理落定"
                                  "(|can_z - 篮底静止高度| < 25 mm, 速度 < 0.05 m/s, 夹爪张开, 末端离 can > 5 cm)"
                                  f" AND 连续保持 {SUCCESS_HOLD_STEPS} 个控制步"),
            "success_criterion_raw": "robosuite env._check_success()（宽口径，会把搬运滑脱的假阳性算成功）",
            "can_half_height_m": CAN_HALF_HEIGHT,
            "task": TASK,
        }
