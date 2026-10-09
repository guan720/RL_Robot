"""真行为树：`scripts/demo_harness_tree.py` 的可执行升级版。

那个 demo 用「假机械臂 + 剧本化失败」讲清楚控制流；本模块把同一棵树接到
**真环境和真技能**上，让每个 tick 都跑一局真实交互，产出可诊断的轨迹记录。

结构（与 demo 一致，便于对照阅读）：

    harness 主循环 (Sequence)
    ├── 记录本轮
    └── 任务调度 (Selector，谁的条件满足就跑谁)
        ├── 正向 +x (Sequence)
        │   ├── 该跑正向?
        │   └── 正向 带恢复 (Selector)
        │       ├── 主策略直接做:  采题 -> 跑技能 -> 记成功并切方向
        │       ├── 降级恢复后重试: 诊断失败 -> 跑恢复技能 -> 记恢复
        │       └── 请求接管（返回 FAILURE，绝不吞成 SUCCESS）
        ├── 反向 -x (Sequence) 同构
        └── 连续接管过多 -> 复位

三条刻意保留的纪律：

  1. **成功判定只来自环境**。`RunSkill` 看的是 `info['success']`，不看技能自己怎么说。
  2. **接管必须让本轮 FAILURE**。兜底分支把失败吞成 SUCCESS，失败就会从统计里消失
     （demo 结尾那段话说的就是这个）。
  3. **节点之间不互相调用**，状态全走 Blackboard（见 `harness/README.md`）。

关于「恢复」在 Reach 上的诚实说明：`envs/reach_env.py` 的 `reset()` 会把末端归零，
所以 Reach 里**不存在需要物理恢复的状态**。这里的恢复分支实现的是「主策略失败 →
降级到一个不依赖训练的规划式技能」，这在真机上是标准做法（安全兜底控制器），
但在 Reach 上它演练的是**流程**而不是物理恢复。等阶段 2 的 `BidirectionalPickPlace`
落地（物体有真实位姿、失败后物体可能掉落/卡住），把 `recovery_skill` 换成
「张开夹爪 + 退回 home + 重新定位」的技能即可，树本身不用改。
"""

from __future__ import annotations

import dataclasses
import itertools
from collections import Counter
from typing import Any

import numpy as np
import py_trees
from py_trees import common

from harness.diagnose import label_episode
from harness.sampling import RegionGoalSampler
from skills.base import EpisodeRecord, Skill, run_episode

FORWARD = "forward"
BACKWARD = "backward"
STALLED = "stalled"
DIRECTIONS = (FORWARD, BACKWARD)


@dataclasses.dataclass
class HarnessContext:
    """行为树需要的一切。树只认这个上下文，所以换环境/换技能不用改树。"""

    env: Any
    primary_skill: Skill | None
    recovery_skill: Skill | None = None
    goal_radius: float = 0.03
    half_space: float = 0.15
    min_goal_dist: float = 0.08
    seed: int = 0
    max_takeover_in_a_row: int = 2
    verbose: bool = True
    namespace: str = "harness"

    records: list[EpisodeRecord] = dataclasses.field(default_factory=list)
    label_counts: Counter = dataclasses.field(default_factory=Counter)
    outcomes: Counter = dataclasses.field(default_factory=Counter)
    env_steps: int = 0
    _seed_iter: Any = None

    def __post_init__(self) -> None:
        self.regions: dict[str, RegionGoalSampler] = {
            FORWARD: RegionGoalSampler(sign=+1, half_space=self.half_space,
                                       min_goal_dist=self.min_goal_dist, seed=self.seed + 1),
            BACKWARD: RegionGoalSampler(sign=-1, half_space=self.half_space,
                                        min_goal_dist=self.min_goal_dist, seed=self.seed + 2),
        }
        self._seed_iter = itertools.count(self.seed * 1000 + 1)

    def next_seed(self) -> int:
        return next(self._seed_iter)

    def reset_counters(self) -> None:
        """开始新一轮采集前清空（闭环里每个 round 都要一份干净的诊断输入）。"""
        self.records.clear()
        self.label_counts.clear()
        self.outcomes.clear()
        self.env_steps = 0
        for sampler in self.regions.values():
            sampler.history.clear()


class _BB(py_trees.behaviour.Behaviour):
    """所有节点的基类：统一注册 Blackboard key，避免每个节点重复写。"""

    KEYS_WRITE = ("direction", "goal", "last_record", "last_label", "round_outcome",
                  "n_round", "n_forward", "n_backward", "n_recover", "n_takeover", "n_stall")

    def __init__(self, name: str, ctx: HarnessContext) -> None:
        super().__init__(name=name)
        self.ctx = ctx
        self.bb = py_trees.blackboard.Client(name=name, namespace=ctx.namespace)
        for key in self.KEYS_WRITE:
            self.bb.register_key(key=key, access=common.Access.WRITE)


def init_blackboard(ctx: HarnessContext) -> py_trees.blackboard.Client:
    """初始化共享状态。对应 RoboRSI 里 Manager 的角色：状态放一个地方，节点按 key 取。"""
    client = py_trees.blackboard.Client(name="harness-init", namespace=ctx.namespace)
    for key in _BB.KEYS_WRITE:
        client.register_key(key=key, access=common.Access.WRITE)
    client.direction = FORWARD
    client.goal = np.zeros(3)
    client.last_record = None
    client.last_label = ""
    client.round_outcome = ""
    client.n_round = 0
    client.n_forward = 0
    client.n_backward = 0
    client.n_recover = 0
    client.n_takeover = 0
    client.n_stall = 0
    return client


class CountRound(_BB):
    def update(self) -> common.Status:
        self.bb.n_round += 1
        return common.Status.SUCCESS


class DirectionIsDue(_BB):
    """条件节点：现在轮到这个方向吗？SUCCESS/FAILURE，永不 RUNNING。"""

    def __init__(self, name: str, ctx: HarnessContext, direction: str) -> None:
        super().__init__(name, ctx)
        self.direction = direction

    def update(self) -> common.Status:
        due = self.bb.direction == self.direction
        return common.Status.SUCCESS if due else common.Status.FAILURE


class SampleGoal(_BB):
    """采题：从该方向的区域里取一个目标点，写到 Blackboard。"""

    def __init__(self, name: str, ctx: HarnessContext, direction: str) -> None:
        super().__init__(name, ctx)
        self.direction = direction

    def update(self) -> common.Status:
        goal = self.ctx.regions[self.direction].draw()
        self.bb.goal = goal
        return common.Status.SUCCESS


class RunSkill(_BB):
    """跑一整局并记账。这是「技能」与「流程」的唯一接触面。

    真机上这个节点应该是跨多个 tick 返回 RUNNING 的（一次搬运要几十秒），
    这里为了先把闭环跑通，一个 tick 内同步跑完整局 —— 接口语义完全一样，
    只是把「等它跑完」压缩到了一个 tick 里。
    """

    def __init__(self, name: str, ctx: HarnessContext, use_recovery: bool = False) -> None:
        super().__init__(name, ctx)
        self.use_recovery = use_recovery

    def update(self) -> common.Status:
        skill = self.ctx.recovery_skill if self.use_recovery else self.ctx.primary_skill
        role = "recovery" if self.use_recovery else "primary"
        record = run_episode(
            self.ctx.env, skill,
            seed=self.ctx.next_seed(),
            direction=str(self.bb.direction),
            role=role,
            goal=np.asarray(self.bb.goal, dtype=np.float64),
        )
        record.label = label_episode(record, self.ctx.goal_radius)
        self.ctx.records.append(record)
        self.ctx.env_steps += record.env_steps
        self.bb.last_record = record
        self.bb.last_label = record.label
        if self.ctx.verbose:
            who = "恢复技能" if self.use_recovery else "主策略"
            print(f"        -> {who} [{record.direction}] steps={record.steps:>3} "
                  f"末距={record.final_dist:.4f} -> {'成功' if record.success else record.label}")
        return common.Status.SUCCESS if record.success else common.Status.FAILURE


class DiagnoseFailure(_BB):
    """把失败标签记进账。永远 SUCCESS：诊断不该阻断流程，它只负责让失败可见。"""

    def update(self) -> common.Status:
        label = str(self.bb.last_label or "unknown")
        self.ctx.label_counts[label] += 1
        if self.ctx.verbose:
            record = self.bb.last_record
            extra = ""
            if record is not None:
                extra = f"（初始 {record.init_dist:.3f} / 最近 {record.min_dist:.3f} / 最终 {record.final_dist:.3f} m）"
            print(f"        -> 诊断: {label} {extra}")
        return common.Status.SUCCESS


class CountSuccess(_BB):
    """成功了：记账 + **切换方向**。这就是正反向交替的开关。"""

    def __init__(self, name: str, ctx: HarnessContext, direction: str) -> None:
        super().__init__(name, ctx)
        self.direction = direction

    def update(self) -> common.Status:
        if self.direction == FORWARD:
            self.bb.n_forward += 1
        else:
            self.bb.n_backward += 1
        self.bb.direction = BACKWARD if self.direction == FORWARD else FORWARD
        self.bb.round_outcome = f"{self.direction}_success"
        self.ctx.outcomes[self.bb.round_outcome] += 1
        if self.ctx.verbose:
            print(f"        -> 本轮成功，下一轮切到 {self.bb.direction}")
        return common.Status.SUCCESS


class CountRecovered(_BB):
    """靠降级技能救回来了：记一笔恢复，方向**不切**（原任务还没真正完成）。"""

    def update(self) -> common.Status:
        self.bb.n_recover += 1
        self.bb.round_outcome = "recovered"
        self.ctx.outcomes["recovered"] += 1
        return common.Status.SUCCESS


class RequestTakeover(_BB):
    """最后一级：请求人类 / 大模型接管。

    返回 FAILURE —— 接管意味着这一轮自主执行没成功，必须被记账。
    连续接管超过 `max_takeover_in_a_row` 就把方向置为 stalled，
    交给「复位」分支处理：这正是「两个方向都失败时会进入无人能救的状态」。
    """

    def __init__(self, name: str, ctx: HarnessContext) -> None:
        super().__init__(name, ctx)
        self._streak = 0

    def update(self) -> common.Status:
        self.bb.n_takeover += 1
        self.ctx.outcomes["takeover"] += 1
        self._streak += 1
        self.bb.round_outcome = "takeover"
        if self.ctx.verbose:
            print(f"        -> 请求接管（连续第 {self._streak} 次）")
        if self._streak >= self.ctx.max_takeover_in_a_row:
            self.bb.direction = STALLED
            if self.ctx.verbose:
                print(f"        -> 连续 {self._streak} 次接管，标记为 stalled，等待复位")
        return common.Status.FAILURE


class IsStalled(_BB):
    def update(self) -> common.Status:
        return common.Status.SUCCESS if self.bb.direction == STALLED else common.Status.FAILURE


class DoReset(_BB):
    """复位：把方向状态拉回可用的起点。

    Reach 里这一步是纯状态复位；阶段 2 的 PickPlace 里，这一步要换成
    「调用 reset 技能把物体搬回 A 区」——那时它本身也可能失败，需要再接一层。
    """

    def update(self) -> common.Status:
        self.bb.n_stall += 1
        self.bb.direction = FORWARD
        self.bb.round_outcome = "reset"
        self.ctx.outcomes["reset"] += 1
        if self.ctx.verbose:
            print("        -> 已复位，方向回到 forward")
        return common.Status.SUCCESS


def build_transport_branch(ctx: HarnessContext, direction: str, label: str) -> Any:
    """一个方向 = 条件 + 三级降级（直接做 / 降级救场 / 请求接管）。"""
    return py_trees.composites.Sequence(
        name=f"{label}",
        memory=True,
        children=[
            DirectionIsDue(f"该跑{direction}?", ctx, direction),
            py_trees.composites.Selector(
                name=f"{direction} 带恢复",
                memory=True,
                children=[
                    py_trees.composites.Sequence(
                        name="主策略直接做",
                        memory=True,
                        children=[
                            SampleGoal(f"采题({direction})", ctx, direction),
                            RunSkill("跑主策略", ctx),
                            CountSuccess(f"记成功并切方向", ctx, direction),
                        ],
                    ),
                    py_trees.composites.Sequence(
                        name="降级救场",
                        memory=True,
                        children=[
                            DiagnoseFailure("诊断失败", ctx),
                            RunSkill("跑恢复技能", ctx, use_recovery=True),
                            CountRecovered("记恢复", ctx),
                        ],
                    ),
                    RequestTakeover("请求接管", ctx),
                ],
            ),
        ],
    )


def build_tree(ctx: HarnessContext) -> Any:
    init_blackboard(ctx)
    return py_trees.composites.Sequence(
        name="harness 主循环",
        memory=True,
        children=[
            CountRound("记录本轮", ctx),
            py_trees.composites.Selector(
                name="任务调度（谁的条件满足就跑谁）",
                memory=False,
                children=[
                    build_transport_branch(ctx, FORWARD, "正向 +x"),
                    build_transport_branch(ctx, BACKWARD, "反向 -x"),
                    py_trees.composites.Sequence(
                        name="无人能救 -> 复位",
                        memory=True,
                        children=[IsStalled("已 stalled?", ctx), DoReset("执行复位", ctx)],
                    ),
                ],
            ),
        ],
    )


def read_stats(namespace: str = "harness") -> dict:
    """把 Blackboard 上的计数器读出来（跑完之后打印/落盘用）。"""
    board = py_trees.blackboard.Blackboard()
    keys = ("direction", "n_round", "n_forward", "n_backward", "n_recover", "n_takeover", "n_stall")
    return {key: board.get(f"{namespace}/{key}") for key in keys}


def run_rounds(ctx: HarnessContext, n_rounds: int, tree: Any = None) -> tuple[Any, list[str]]:
    """tick n_rounds 次，返回 (树, 每轮的结果标签)。一次 tick = 一轮任务尝试。"""
    tree = tree if tree is not None else build_tree(ctx)
    outcomes: list[str] = []
    board = py_trees.blackboard.Blackboard()
    for _ in range(int(n_rounds)):
        tree.tick_once()
        outcome = board.get(f"{ctx.namespace}/round_outcome") or "none"
        outcomes.append(str(outcome))
    return tree, outcomes
