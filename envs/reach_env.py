"""最小 Reach 环境：不依赖任何机器人仿真器，只用 numpy。

为什么先写这个？因为强化学习的接口只有两个函数：

    obs, info = env.reset(seed=...)          # 开一局，返回初始观测
    obs, reward, terminated, truncated, info = env.step(action)   # 走一步

后面换成 robosuite、ManiSkill、Genie Sim，接口完全一样，只是 obs/action 变复杂。
在这个几十行的环境里把五个要素看清楚，之后就不会被大框架绕晕：

    observation  末端位置 + 目标位置（6 维，已归一化到 [-1, 1]）
    action       末端位移增量（3 维，[-1, 1]，实际位移 = action * action_scale）
    reward       -距离；进入 goal_radius 额外 +10 并结束
    terminated   到达目标（任务成功）
    truncated    超过 max_steps 还没到（超时）
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces


class Reach3DEnv(gym.Env):
    """三维空间里让一个点（代表机械臂末端）移动到目标点。"""

    metadata = {"render_modes": []}

    def __init__(
        self,
        max_steps: int = 100,
        action_scale: float = 0.05,
        goal_radius: float = 0.03,
        min_goal_dist: float = 0.08,
        half_space: float = 0.15,
        success_bonus: float = 10.0,
    ) -> None:
        super().__init__()
        self.max_steps = int(max_steps)
        self.action_scale = float(action_scale)
        self.goal_radius = float(goal_radius)
        self.min_goal_dist = float(min_goal_dist)
        self.success_bonus = float(success_bonus)
        self.half_space = np.full(3, float(half_space), dtype=np.float64)

        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(6,), dtype=np.float32)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(3,), dtype=np.float32)

        self.ee = np.zeros(3, dtype=np.float64)
        self.goal = np.zeros(3, dtype=np.float64)
        self.step_idx = 0
        self.last_success = False
        self.total_episodes = 0
        self.success_episodes = 0

    def _obs(self) -> np.ndarray:
        return np.concatenate([self.ee / self.half_space, self.goal / self.half_space]).astype(np.float32)

    def _dist(self) -> float:
        return float(np.linalg.norm(self.goal - self.ee))

    def _sample_goal(self) -> np.ndarray:
        goal = self.np_random.uniform(-self.half_space, self.half_space)
        for _ in range(64):
            if np.linalg.norm(goal - self.ee) >= self.min_goal_dist:
                break
            goal = self.np_random.uniform(-self.half_space, self.half_space)
        return goal.astype(np.float64)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self.ee = np.zeros(3, dtype=np.float64)
        self.goal = self._sample_goal()
        if options and "goal" in options:
            self.goal = np.asarray(options["goal"], dtype=np.float64).reshape(3)
        self.step_idx = 0
        self.last_success = False
        return self._obs(), {"dist": self._dist(), "success": False, "steps": 0}

    def step(self, action):
        act = np.clip(np.asarray(action, dtype=np.float64).reshape(3), -1.0, 1.0)
        self.ee = np.clip(self.ee + act * self.action_scale, -self.half_space, self.half_space)

        dist = self._dist()
        success = dist <= self.goal_radius
        self.step_idx += 1

        reward = -dist
        terminated = False
        if success:
            reward += self.success_bonus
            terminated = True
        truncated = self.step_idx >= self.max_steps

        if terminated or truncated:
            self.total_episodes += 1
            self.last_success = success
            self.success_episodes += int(success)

        info = {"dist": dist, "success": bool(success), "steps": self.step_idx}
        return self._obs(), float(reward), bool(terminated), bool(truncated), info

    def render(self):
        return None


def make_reach_env(**kwargs) -> Reach3DEnv:
    return Reach3DEnv(**kwargs)
