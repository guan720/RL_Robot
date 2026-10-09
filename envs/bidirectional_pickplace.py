"""阶段 2 环境：正反向交替搬运（reset-free）+ 覆盖率统计 + 规则式救场复位。

研究问题（ROADMAP 阶段 2 的验收标准）：
    1. 交替是否更快？      -> 比「每次任务都人工复位」省了多少次复位
    2. 代价是什么？        -> 覆盖率会不会塌缩（交替 ≠ 遍历）
    3. 两者都失败时谁复位？ -> 规则式救场（stall_limit 触发），并把它记账

设计要点
--------
* 抽象平面环境（和阶段 1 的 Reach 同一哲学）：一个点代表末端，在桌面上搬一个物体。
  先在这里把 reset-free 的**机制和度量**搞清楚，再搬去 robosuite / 真机。
* 两个区域：A = 左半 (x < -gap)，B = 右半 (x > +gap)。
  正向 = 把物体从 A 搬到 B；反向 = 从 B 搬回 A。
* 一局（episode）里会连续做很多个任务（task），直到 max_steps 超时。
  每个 task 分两相：seek（空手去抓）→ carry（抓着去放）。
* reset_mode:
    "alternate"  reset-free：task 成功后物体就留在放置点，**下一个任务的抓取点就是它**，
                 不需要任何复位。只有卡死时才规则复位。
    "fixed"      每个 task 边界都把物体重新采样到源区域 = 「每次都人工复位」。
                 复位次数 = 任务数，作为成本对照。
* 覆盖率：把工作空间离散成 grid_n × grid_n 个格子，记录
    pick_cells  每次成功抓取时物体所在格子（= 策略**实际经历**的起始状态）
    place_cells 每次成功放置的格子（= 策略**实际做到**的目标）
  这是回答「交替 ≠ 遍历」的唯一硬证据：请求的目标可以很均匀，
  但策略若只在部分区域可靠，交替模式下下一轮的起始点就会被带偏，覆盖率塌缩。
* 规则式救场：连续 stall_limit 步没有任何 task 完成 -> 把物体按当前方向重新采样回源区域，
  manual_resets += 1。这就是「两者都失败时谁负责复位」的答案：先由规则兜底，
  将来可以换成大模型接管，接口不变。

obs = [ee(2), object(2), target(2), held(1)] / half  归一化到 [-1, 1]，共 7 维
action = [dx, dy] ∈ [-1, 1]²，实际位移 = action * action_scale
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces


class BidirectionalTransport2D(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        half: float = 0.15,
        gap: float = 0.02,
        action_scale: float = 0.04,
        pick_radius: float = 0.02,
        place_radius: float = 0.02,
        max_steps: int = 400,
        stall_limit: int = 120,
        grid_n: int = 6,
        reset_mode: str = "alternate",
        recovery_mode: str = "resample",
        pick_bonus: float = 2.0,
        place_bonus: float = 8.0,
    ) -> None:
        super().__init__()
        assert reset_mode in ("alternate", "fixed")
        assert recovery_mode in ("resample", "home")
        self.half = float(half)
        self.gap = float(gap)
        self.action_scale = float(action_scale)
        self.pick_radius = float(pick_radius)
        self.place_radius = float(place_radius)
        self.max_steps = int(max_steps)
        self.stall_limit = int(stall_limit)
        self.grid_n = int(grid_n)
        self.reset_mode = reset_mode
        # 规则式救场把物体放到哪，直接决定 reset-free 的覆盖会不会塌缩：
        #   resample 在源区域里均匀重采样 -> 救场顺便补了起始状态多样性
        #   home     放回该区域的固定 home 点（区域中心）-> 起始状态只剩「舒适区 + home」
        # 真机上「恢复动作把物体摆回一个固定位」更接近 home，所以这个开关必须能对照。
        self.recovery_mode = recovery_mode
        self.pick_bonus = float(pick_bonus)
        self.place_bonus = float(place_bonus)

        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(7,), dtype=np.float32)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(2,), dtype=np.float32)

        self.ee = np.zeros(2)
        self.obj = np.zeros(2)
        self.target = np.zeros(2)
        self.held = False
        self.direction = "forward"          # forward = A->B, backward = B->A
        self.step_idx = 0
        self.steps_since_task = 0

        self.tasks_done = 0
        self.tasks_attempted = 0
        self.success = {"forward": 0, "backward": 0}
        self.manual_resets = 0
        self.fixed_resets = 0
        self.slip_events = 0       # 搬运途中掉了几次（扰动环境才会 > 0）
        self.push_events = 0       # 冲太快把物体撞开几次（扰动环境才会 > 0）
        self._last_speed = 0.0
        self.pick_cells: set[tuple[int, int]] = set()
        self.place_cells: set[tuple[int, int]] = set()
        # 计数版（set 只够算覆盖率，画热力图需要访问次数）
        self.pick_cell_counts: dict[tuple[int, int], int] = {}
        self.place_cell_counts: dict[tuple[int, int], int] = {}
        # 「请求」与「经历」要分开记：这是回答「交替 != 遍历」的关键证据。
        #   start_cell_counts 每个 task 开始时物体所在格子 = 策略**实际经历**的起始状态分布
        #   goal_cell_counts  每个 task 请求的目标格子     = 环境**要求**它做到的分布
        # fixed 模式下 start 由环境均匀重采样（外生），alternate 模式下 start = 上一轮的放置点（内生）。
        self.start_cell_counts: dict[tuple[int, int], int] = {}
        self.goal_cell_counts: dict[tuple[int, int], int] = {}
        # 起始状态**从哪来**：这是把「交替 != 遍历」讲清楚的最直接证据。
        #   prev_place   上一轮成功放置点（alternate 模式的主要来源，内生于策略）
        #   fixed_reset  固定复位时的人工重采样（外生、均匀）
        #   recovery     规则式救场复位（外生，resample 时均匀 / home 时固定点）
        #   episode_init 每局开头的第一个任务
        self.start_sources: dict[str, int] = {}

    # ------------------------------------------------------------------ 区域与采样
    def _region_bounds(self, region: str) -> tuple[np.ndarray, np.ndarray]:
        if region == "A":
            lo = np.array([-self.half, -self.half])
            hi = np.array([-self.gap, self.half])
        else:
            lo = np.array([self.gap, -self.half])
            hi = np.array([self.half, self.half])
        return lo, hi

    def _region_of(self, pos: np.ndarray) -> str:
        return "A" if pos[0] < 0 else "B"

    def _sample_in(self, region: str) -> np.ndarray:
        lo, hi = self._region_bounds(region)
        return self.np_random.uniform(lo, hi)

    def _cell(self, pos: np.ndarray) -> tuple[int, int]:
        u = np.clip((pos + self.half) / (2 * self.half), 0.0, 1.0 - 1e-9)
        idx = (u * self.grid_n).astype(int)
        return int(idx[0]), int(idx[1])

    # ------------------------------------------------------------------ 观测
    def _obs(self) -> np.ndarray:
        return np.concatenate([
            self.ee / self.half,
            self.obj / self.half,
            self.target / self.half,
            [1.0 if self.held else -1.0],
        ]).astype(np.float32)

    def _subgoal(self) -> np.ndarray:
        return self.obj if not self.held else self.target

    # ------------------------------------------------------------------ 可覆写钩子
    # 下面五个钩子在基类里都是「什么都不做」的默认实现，行为与未拆分之前**完全等价**。
    # 存在的意义是：`envs/transport_perturbed.py` 可以只覆写钩子来加扰动，
    # 而覆盖率统计、任务推进、成功判定、救场规则一行都不用复制。
    # 这样两套环境的**指标口径天然一致**，加难度前后的数字才有可比性。
    def _transform_action(self, act: np.ndarray) -> np.ndarray:
        """指令 -> 实际下发的指令（延迟 / 增益 / 漂移的插入点）。"""
        return act

    def _effective_scale(self) -> float:
        """本步的位移比例（负载影响速度的插入点）。"""
        return self.action_scale

    def _apply_motion(self, act: np.ndarray) -> None:
        """执行位移。`_last_speed` 记录真实位移大小，供「冲太快把物体撞开」判定用。"""
        previous = self.ee.copy()
        self.ee = np.clip(self.ee + act * self._effective_scale(), -self.half, self.half)
        self._last_speed = float(np.linalg.norm(self.ee - previous))
        if self.held:
            self.obj = self.ee.copy()

    def _grasp_ok(self, dist: float) -> bool:
        """已经进入抓取圈了，这一抓到底抓不抓得住（抓取可靠性的插入点）。"""
        return True

    def _carry_slips(self, dist: float) -> bool:
        """搬运途中物体是否滑落（返回 True 则本步变成空手，物体留在原处附近）。"""
        return False

    # ------------------------------------------------------------------ gym API
    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self.ee = np.zeros(2)
        self.direction = "forward"
        self.held = False
        self.obj = self._sample_in("A")
        self.target = self._sample_in("B")
        self.step_idx = 0
        self.steps_since_task = 0
        self.tasks_done = 0
        self.tasks_attempted = 0
        self.success = {"forward": 0, "backward": 0}
        self.manual_resets = 0
        self.fixed_resets = 0
        self.slip_events = 0
        self.push_events = 0
        self._last_speed = 0.0
        self.pick_cells = set()
        self.place_cells = set()
        self.pick_cell_counts = {}
        self.place_cell_counts = {}
        self.start_cell_counts = {}
        self.goal_cell_counts = {}
        self.start_sources = {}
        self._record_task_start("episode_init")
        return self._obs(), self._info()

    def step(self, action):
        act = np.clip(np.asarray(action, dtype=np.float64).reshape(2), -1.0, 1.0)
        act = self._transform_action(act)
        self._apply_motion(act)
        self.step_idx += 1
        self.steps_since_task += 1

        dist = float(np.linalg.norm(self._subgoal() - self.ee))
        reward = -dist
        terminated = False

        if not self.held:
            if dist <= self.pick_radius and self._grasp_ok(dist):
                self.held = True
                cell = self._cell(self.obj)
                self.pick_cells.add(cell)
                self.pick_cell_counts[cell] = self.pick_cell_counts.get(cell, 0) + 1
                reward += self.pick_bonus
        else:
            if self._carry_slips(dist):
                self.held = False
                self.slip_events += 1
            elif dist <= self.place_radius:
                reward += self.place_bonus
                cell = self._cell(self.obj)
                self.place_cells.add(cell)
                self.place_cell_counts[cell] = self.place_cell_counts.get(cell, 0) + 1
                self.success[self.direction] += 1
                self.tasks_done += 1
                self.steps_since_task = 0
                self._advance_task()

        # 规则式救场：长时间没有任何 task 完成 -> 兜底复位并记账
        truncated = False
        if self.steps_since_task >= self.stall_limit:
            self.manual_resets += 1
            self._rule_reset()
        if self.step_idx >= self.max_steps:
            truncated = True

        return self._obs(), float(reward), terminated, truncated, self._info()

    # ------------------------------------------------------------------ 任务推进
    def _record_task_start(self, source: str) -> None:
        """每个 task 开始时记账：请求了什么目标、策略将从什么起始状态开始、这个起始状态谁给的。"""
        self.tasks_attempted += 1
        self.start_sources[source] = self.start_sources.get(source, 0) + 1
        sc = self._cell(self.obj)
        gc = self._cell(self.target)
        self.start_cell_counts[sc] = self.start_cell_counts.get(sc, 0) + 1
        self.goal_cell_counts[gc] = self.goal_cell_counts.get(gc, 0) + 1

    def _advance_task(self) -> None:
        """一个 task 完成后切方向、采样新目标。

        alternate: 物体留在放置点（= 下一任务的抓取点），零复位成本。
        fixed:     物体重新采样到源区域 = 每个任务一次人工复位。
        """
        self.direction = "backward" if self.direction == "forward" else "forward"
        self.held = False
        src = "A" if self.direction == "forward" else "B"
        dst = "B" if self.direction == "forward" else "A"
        if self.reset_mode == "fixed":
            self.obj = self._sample_in(src)
            self.fixed_resets += 1
        # alternate 模式下 self.obj 已经是上一轮的放置点，天然落在 src 区域
        self.target = self._sample_in(dst)
        self._record_task_start("fixed_reset" if self.reset_mode == "fixed" else "prev_place")

    def _home_of(self, region: str) -> np.ndarray:
        sign = -1.0 if region == "A" else 1.0
        return np.array([sign * (self.gap + self.half) / 2.0, 0.0])

    def _rule_reset(self) -> None:
        """规则式救场复位：把物体放回当前方向应有的源区域，目标重新采样。

        recovery_mode="home" 时放回固定的 home 点，而不是重新随机采样。
        """
        src = "A" if self.direction == "forward" else "B"
        dst = "B" if self.direction == "forward" else "A"
        self.held = False
        self.obj = self._home_of(src) if self.recovery_mode == "home" else self._sample_in(src)
        self.target = self._sample_in(dst)
        self.steps_since_task = 0
        self._record_task_start("recovery")

    # ------------------------------------------------------------------ 报告
    def _info(self) -> dict:
        return {
            "phase": "carry" if self.held else "seek",
            "direction": self.direction,
            "held": bool(self.held),
            "dist": float(np.linalg.norm(self._subgoal() - self.ee)),
            "tasks_done": self.tasks_done,
            "tasks_attempted": self.tasks_attempted,
            "success_forward": self.success["forward"],
            "success_backward": self.success["backward"],
            "manual_resets": self.manual_resets,
            "fixed_resets": self.fixed_resets,
            "slip_events": self.slip_events,
            "push_events": self.push_events,
            "coverage": self.coverage_fraction(),
        }

    def coverage_fraction(self) -> float:
        total = self.grid_n * self.grid_n
        return round(len(self.pick_cells | self.place_cells) / total, 4)

    def coverage_report(self) -> dict:
        total = self.grid_n * self.grid_n
        return {
            "grid_n": self.grid_n,
            "reset_mode": self.reset_mode,
            "recovery_mode": self.recovery_mode,
            "tasks_done": self.tasks_done,
            "tasks_attempted": self.tasks_attempted,
            "success_forward": self.success["forward"],
            "success_backward": self.success["backward"],
            "manual_resets": self.manual_resets,
            "fixed_resets": self.fixed_resets,
            "slip_events": self.slip_events,
            "push_events": self.push_events,
            "total_resets": self.manual_resets + self.fixed_resets,
            "pick_cells": sorted(self.pick_cells),
            "place_cells": sorted(self.place_cells),
            "pick_cell_counts": {f"{k[0]},{k[1]}": v for k, v in sorted(self.pick_cell_counts.items())},
            "place_cell_counts": {f"{k[0]},{k[1]}": v for k, v in sorted(self.place_cell_counts.items())},
            "start_cell_counts": {f"{k[0]},{k[1]}": v for k, v in sorted(self.start_cell_counts.items())},
            "goal_cell_counts": {f"{k[0]},{k[1]}": v for k, v in sorted(self.goal_cell_counts.items())},
            "start_sources": dict(sorted(self.start_sources.items())),
            "coverage_pick": round(len(self.pick_cells) / total, 4),
            "coverage_place": round(len(self.place_cells) / total, 4),
            "coverage_union": self.coverage_fraction(),
        }


def make_transport_env(**kwargs) -> BidirectionalTransport2D:
    return BidirectionalTransport2D(**kwargs)
