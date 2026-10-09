"""robosuite PickPlaceCan 的 gymnasium 包装：把视觉/状态观测与成功判定统一到阶段 2 的口径。

为什么需要包装层（三个实际的坑，探针脚本里踩过）：
    1. robosuite 1.5 仍是**旧 API**：`reset() -> obs`、`step() -> (obs, r, done, info)`；
       SB3 2.x 要 gymnasium 的五元组，不包装接不上。
    2. 观测是 OrderedDict，图像键叫 `<cam>_image`，状态键叫 `*-state`；相机名只有
       `frontview / birdview / agentview / robot0_robotview / robot0_eye_in_hand` 五个
       （写 `robotview` 会直接报 observable invalid）。
    3. 相机参数叫 `camera_heights / camera_widths`（没有 `camera_obs_size`）。

成功判定纪律（和阶段 1/2 一致）：
    **只用环境真值判定**——robosuite 1.5 里是 `env._check_success()`（can 真实位姿 vs 目标象限）。
    注意 1.5 的 `info` 是空 dict，`info["success"]` 不存在；早期代码读它恒为 False（已修）。
    奖励用环境自带的（reach/lift/place 分段稠密奖励），但报告里永远同时给 success 率，
    不让奖励或模型自己定义「成功」。

任务计数口径（向阶段 2 看齐）：
    一局 `horizon` 步内，can 进入目标区域记 1 个 task；掉出来再放进去再记 1 个
    （`tasks_done`），这样和搬运环境的「一局多个 task」口径一致，将来两张表能对齐。
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

os.environ.setdefault("OMP_NUM_THREADS", "1")

import gymnasium as gym  # noqa: E402
import robosuite  # noqa: E402

STATE_KEYS = ("robot0_proprio-state", "object-state")
VALID_CAMS = ("frontview", "birdview", "agentview", "robot0_robotview", "robot0_eye_in_hand")


class RobosuitePickPlaceCan(gym.Env):
    """PickPlaceCan + gymnasium API + state/pixels 两种观测模式。"""

    metadata = {"render_modes": []}

    def __init__(self, obs_mode: str = "state", cams: tuple[str, ...] = ("agentview",),
                 cam_size: int = 64, horizon: int = 400, control_freq: int = 20,
                 reward_shaping: bool = False, suite_task: str = "PickPlaceCan",
                 hist: int = 1):
        # hist = 状态观测堆叠帧数：相位（接近/降/闭/升）在单帧 obs 里歧义（同一 obs 区域对应
        # 不同动作 -> MSE-BC 学条件均值 -> 5%/0%/0% 否证链）；把时间窗放进观测后 obs->action
        # 才良定。=1 时与旧行为完全一致。
        super().__init__()
        if obs_mode not in ("state", "pixels"):
            raise ValueError(f"obs_mode 只能是 state/pixels，收到 {obs_mode}")
        for c in cams:
            if c not in VALID_CAMS:
                raise ValueError(f"相机 {c} 不存在，可选 {VALID_CAMS}")
        self.obs_mode = obs_mode
        self.cams = tuple(cams)
        self.cam_size = int(cam_size)
        self.hist = int(hist)
        self._hist_buf: list[np.ndarray] = []
        if self.hist > 1 and obs_mode == "pixels":
            raise ValueError("hist>1 暂只支持 state 观测（像素叠帧的代价另算）")
        use_cam = obs_mode == "pixels"
        self._env = robosuite.make(
            suite_task,
            robots="Panda",
            has_renderer=False,
            has_offscreen_renderer=use_cam,
            use_camera_obs=use_cam,
            camera_heights=self.cam_size,
            camera_widths=self.cam_size,
            camera_names=list(self.cams),
            use_object_obs=True,
            control_freq=control_freq,
            horizon=horizon,
            hard_reset=False,
            reward_shaping=reward_shaping,
        )
        # 纪律：shaping 只影响「学得多快」，不影响「算不算成功」。
        # robosuite 默认 reward_shaping=False -> 纯稀疏（成功 +1），随机探索永远拿不到信号；
        # 打开后是 reach[0,0.1]/grasp{0,0.35}/lift[0.35,0.5]/hover[0.5,0.7] 的分段稠密奖励。
        # 报告里永远同时给 info["success"] 口径的成功率，不用奖励代替成功。
        self.reward_shaping = bool(reward_shaping)
        lo, hi = self._env.action_spec
        self._act_lo = np.asarray(lo, dtype=np.float32)
        self._act_hi = np.asarray(hi, dtype=np.float32)
        self.action_space = gym.spaces.Box(self._act_lo, self._act_hi)
        if use_cam:
            self.observation_space = gym.spaces.Box(
                0, 255, (self.cam_size, self.cam_size, 3 * len(self.cams)), np.uint8)
        else:
            probe = self._env.reset()
            d = int(sum(np.asarray(probe[k], dtype=np.float32).size for k in STATE_KEYS))
            self.observation_space = gym.spaces.Box(-np.inf, np.inf, (d * self.hist,), np.float32)
        self._succ_held = False
        self.tasks_done = 0
        self.suite_task = suite_task

    # ------------------------------------------------------------------ obs
    def _obs(self, obs: dict) -> np.ndarray:
        if self.obs_mode == "pixels":
            imgs = [np.asarray(obs[f"{c}_image"], dtype=np.uint8) for c in self.cams]
            return np.concatenate(imgs, axis=-1)
        vec = np.concatenate([np.asarray(obs[k], dtype=np.float32).ravel() for k in STATE_KEYS])
        if self.hist == 1:
            return vec
        self._hist_buf.append(vec)
        self._hist_buf = self._hist_buf[-self.hist:]
        while len(self._hist_buf) < self.hist:
            self._hist_buf.insert(0, vec)
        return np.concatenate(self._hist_buf)

    # ------------------------------------------------------------------ gymnasium API
    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        if seed is not None:
            # robosuite 1.5 没有 env.seed()：随机性来自构造期的 self.rng（np.random.default_rng），
            # 物体初始摆放等都在 reset 里从 self.rng 取数，所以换 seed = 换一个新的 rng。
            self._env.rng = np.random.default_rng(seed)
        obs = self._env.reset()
        self._succ_held = False
        self.tasks_done = 0
        self._hist_buf = []
        return self._obs(obs), {"tasks_done": 0}

    def step(self, action: np.ndarray):
        action = np.clip(np.asarray(action, dtype=np.float64), self._act_lo, self._act_hi)
        obs, reward, done, info = self._env.step(action)
        # robosuite 1.5 的 info 是**空 dict**（没有 info["success"]，探针实测）；
        # 成功真值只能问环境自己：_check_success() 会刷新 objects_in_bins 并返回判定。
        succ = bool(self._env._check_success())
        if succ and not self._succ_held:
            self.tasks_done += 1
        self._succ_held = succ
        out_info = {"success": succ, "tasks_done": self.tasks_done}
        return self._obs(obs), float(reward), False, bool(done), out_info

    def close(self):
        self._env.close()
