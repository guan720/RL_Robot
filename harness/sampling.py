"""采样层：把诊断结论真正变成「训练时看到哪些题」。

这一层是对照实验的**唯一变量**。两个对照组跑的是同一份固定训练程序、同样的交互
预算、同样的评测口径，只有这里不同：

    UniformGoalSampler   环境默认的均匀采样（对照组，等价于不用 harness 直接训）
    BandedGoalSampler    按 `harness/diagnose.py` 给的失败分布加权采样（实验组）

红线：采样只作用于**训练环境**。评测永远用环境自己的均匀采样（`eval/reach_eval.py`
里 `env.reset(seed=...)` 不带 options），否则「实验组分高」可能只是因为它在评测
分布上练过 —— 那就是数据泄漏，不是学得更快。

为什么用「拒绝采样」而不是「先采距离再采方向」？
    先采方向再乘半径很容易生成**工作空间外**的目标点（立方体的角落距离可达
    half×√3，但大部分方向在这个距离上已经出界）。目标出界后末端永远够不到，
    这一局就成了不可能完成的任务，会往训练数据里灌噪声。
    在立方体内均匀采、再按距离带筛选，天然保证目标合法。
"""

from __future__ import annotations

import math
from typing import Any

import gymnasium as gym
import numpy as np

from harness.diagnose import SamplingPlan


class GoalSampler:
    """初始目标采样器接口：`sample()` 返回一个合法的目标坐标（米）。"""

    kind = "base"

    def __init__(self, half_space: float = 0.15, min_goal_dist: float = 0.08, seed: int = 0) -> None:
        self.half_space = float(half_space)
        self.min_goal_dist = float(min_goal_dist)
        self.rng = np.random.default_rng(seed)
        self._draws = 0
        self.history: list[np.ndarray] = []   # 采过的目标点，事后核对两组题目是否真不同

    def seed(self, seed: int) -> None:
        self.rng = np.random.default_rng(seed)

    def _uniform_in_box(self, max_tries: int = 64) -> np.ndarray:
        """环境自带的分布：立方体内均匀，且离起点至少 min_goal_dist。"""
        half = np.full(3, self.half_space)
        goal = self.rng.uniform(-half, half)
        for _ in range(max_tries):
            if np.linalg.norm(goal - np.zeros(3)) >= self.min_goal_dist:
                break
            goal = self.rng.uniform(-half, half)
        return goal.astype(np.float64)

    def draw(self) -> np.ndarray:
        """对外统一入口：采样 + 记账。所有调用方（wrapper / 行为树）都用 draw，
        这样 `history` 只在一个地方追加，不会出现重复计数。"""
        goal = self.sample()
        self.history.append(np.asarray(goal, dtype=np.float64).reshape(-1).copy())
        return goal

    def sample(self) -> np.ndarray:
        self._draws += 1
        return self._uniform_in_box()

    def describe(self) -> dict:
        return {"kind": self.kind, "half_space": self.half_space,
                "min_goal_dist": self.min_goal_dist, "draws": self._draws}


class UniformGoalSampler(GoalSampler):
    kind = "uniform"


class BandedGoalSampler(GoalSampler):
    """按距离带加权的采样器（实验组）。

    `mix_uniform` 是保底比例：有这么多概率完全按环境默认分布采，剩下的才按诊断
    权重采。设为 0 会退化成「只在失败带训练」，旧能力会掉；默认 0.25。
    """

    kind = "banded"

    def __init__(
        self,
        plan: SamplingPlan,
        half_space: float = 0.15,
        min_goal_dist: float = 0.08,
        seed: int = 0,
        mix_uniform: float = 0.25,
        max_tries: int = 256,
    ) -> None:
        super().__init__(half_space=half_space, min_goal_dist=min_goal_dist, seed=seed)
        self.plan = plan.normalized()
        self.mix_uniform = float(mix_uniform)
        self.max_tries = int(max_tries)
        self.weights = np.asarray(self.plan.weights, dtype=np.float64)
        self.weights = self.weights / self.weights.sum()
        self.band_hits = [0] * len(self.plan.bands)
        self.fallbacks = 0

    def _in_band(self, band: tuple[float, float]) -> np.ndarray | None:
        lo, hi = float(band[0]), float(band[1])
        half = np.full(3, self.half_space)
        for _ in range(self.max_tries):
            goal = self.rng.uniform(-half, half)
            dist = float(np.linalg.norm(goal))
            if dist < self.min_goal_dist:
                continue
            if lo <= dist < hi:
                return goal.astype(np.float64)
        return None

    def sample(self) -> np.ndarray:
        self._draws += 1
        if self.rng.random() < self.mix_uniform:
            return self._uniform_in_box()
        idx = int(self.rng.choice(len(self.plan.bands), p=self.weights))
        goal = self._in_band(self.plan.bands[idx])
        if goal is None:
            # 这个距离带在当前工作空间里几乎没有合法点（例如贴近角落的极远带），
            # 退回均匀采样，绝不能返回一个够不到的目标。
            self.fallbacks += 1
            return self._uniform_in_box()
        self.band_hits[idx] += 1
        return goal

    def describe(self) -> dict:
        base = super().describe()
        base.update({
            "mix_uniform": self.mix_uniform,
            "bands": [[round(a, 4), round(b, 4)] for a, b in self.plan.bands],
            "weights": [round(float(w), 4) for w in self.weights],
            "band_hits": self.band_hits,
            "fallbacks": self.fallbacks,
        })
        return base


class RegionGoalSampler(GoalSampler):
    """只在半个空间里采目标 —— 用来给 Reach 造出「正向 / 反向」两个方向。

    `sign=+1` 表示目标 x>0（相当于把物体搬到 B 区），`sign=-1` 表示 x<0（搬回 A 区）。
    这是行为树里「成功后切换方向」需要的两个题目来源。

    必须说清楚的局限：Reach 里**没有物体**，`env.reset()` 每次都把末端归零，
    所以这里的正反向只是在演练 harness 的方向切换与记账逻辑，
    **不是**真正的 reset-free —— 真正的 reset-free 要靠「上一局的末态恰好是下一局
    的初态」，那需要阶段 2 的 `BidirectionalPickPlace`（物体在 A/B 之间来回搬，
    正向的终点就是反向的起点）。等那个环境落地，把这里换成它的 goal provider 即可，
    行为树和闭环代码不用动。
    """

    kind = "region"

    def __init__(self, sign: int = 1, half_space: float = 0.15,
                 min_goal_dist: float = 0.08, seed: int = 0, margin: float = 0.02) -> None:
        super().__init__(half_space=half_space, min_goal_dist=min_goal_dist, seed=seed)
        self.sign = 1 if sign >= 0 else -1
        self.margin = float(margin)

    def sample(self) -> np.ndarray:
        self._draws += 1
        goal = self._uniform_in_box()
        for _ in range(256):
            if self.sign * goal[0] >= self.margin:
                break
            goal = self._uniform_in_box()
        goal[0] = self.sign * max(abs(float(goal[0])), self.margin)
        return goal

    def describe(self) -> dict:
        base = super().describe()
        base.update({"sign": self.sign, "margin": self.margin})
        return base


def sampler_from_plan(plan_dict: dict | None, env_kwargs: dict, seed: int = 0,
                      mix_uniform: float = 0.25) -> GoalSampler:
    """诊断结果（dict）-> 采样器。`plan_dict=None` 就是对照组。"""
    half_space = float(env_kwargs.get("half_space", 0.15))
    min_goal_dist = float(env_kwargs.get("min_goal_dist", 0.08))
    if not plan_dict:
        return UniformGoalSampler(half_space, min_goal_dist, seed)
    plan = SamplingPlan(
        bands=[(float(a), float(b)) for a, b in plan_dict["bands"]],
        weights=[float(w) for w in plan_dict["weights"]],
        reason=dict(plan_dict.get("reason", {})),
    )
    return BandedGoalSampler(plan, half_space, min_goal_dist, seed, mix_uniform)


class GoalSamplingWrapper(gym.Wrapper):
    """把采样器接到环境的 `reset()` 上。

    为什么需要 wrapper 而不是改 `envs/reach_env.py`？两个理由：
      1. 训练环境的采样策略属于 harness 的实验变量，不属于环境定义；
      2. SB3 的 `learn()` 内部自己调 `env.reset()`，我们没有别的地方插手。
    wrapper 只重写 reset 注入 `options={'goal': ...}`，step/reward/成功判定
    一律不动 —— 环境真值判定必须保持中立。
    """

    def __init__(self, env: Any, sampler: GoalSampler) -> None:
        super().__init__(env)
        self.sampler = sampler

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        opts = dict(options or {})
        if "goal" not in opts:
            opts["goal"] = self.sampler.draw()
        return self.env.reset(seed=seed, options=opts)


def init_dist_histogram(goals: list[np.ndarray], bins: int = 8,
                        hi: float | None = None) -> dict:
    """统计采样出来的初始距离分布，用来事后核对「两组看到的题是否真的不同」。"""
    if not goals:
        return {"n": 0}
    dists = np.asarray([float(np.linalg.norm(g)) for g in goals])
    top = float(hi if hi is not None else dists.max())
    hist, edges = np.histogram(dists, bins=bins, range=(0.0, max(top, 1e-6)))
    return {
        "n": int(dists.size),
        "mean": round(float(dists.mean()), 4),
        "std": round(float(dists.std()), 4),
        "min": round(float(dists.min()), 4),
        "max": round(float(dists.max()), 4),
        "hist": [int(x) for x in hist],
        "edges": [round(float(x), 4) for x in edges],
    }


def max_reach_distance(half_space: float) -> float:
    """立方体工作空间里离原点的最大可能距离（角落），用于设定距离带上界。"""
    return float(half_space) * math.sqrt(3.0)
