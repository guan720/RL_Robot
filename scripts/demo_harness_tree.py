#!/usr/bin/env python
"""阶段 3 预览：用 py_trees 搭一个最小 harness，看懂「上层框架」到底在管什么。

为什么值得先看这个？
    RoboRSI / LeRobot / SERL 这些框架，上层做的事本质上都是同一件：
        决定现在跑哪个任务 → 出错了走哪条恢复路径 → 什么时候停 → 状态存哪里
    这套逻辑用**行为树（Behavior Tree）**表达最直观，而且几十行就能跑，
    不需要 ROS、不需要仿真器、不需要大模型。

本脚本用一个「假机械臂」演示你真正的研究场景：
    A、B 两个区域，一个物体。
        正向搬运 A→B 成功后，A 空了、B 有物体；
        下一轮自动变成反向搬运 B→A；
        反向成功后又给正向创造了初始条件。
    这就是 reset-free 的核心思想：**让两个方向的策略互相替对方复位**，
    省掉人工把物体摆回去的成本。

失败路径也演示了三级降级：
        直接执行 → 失败 → 恢复动作 + 重试 → 还失败 → 请求人类/大模型接管

用法：
    python scripts/demo_harness_tree.py                 # 跑 12 个 tick
    python scripts/demo_harness_tree.py --ticks 20
    python scripts/demo_harness_tree.py --tree          # 只看树结构，不执行

预期输出：每个 tick 打印一次行为树，SUCCESS/RUNNING/FAILURE 用颜色或文字标出，
最后打印统计（搬运成功几次、恢复几次、接管几次）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

# 忘了 activate venv 时给出人话提示，而不是甩一堆 traceback
ensure_venv("py_trees")

import py_trees  # noqa: E402
from py_trees import behaviours, common  # noqa: E402


# --------------------------------------------------------------------------
# 1. 假机械臂：把「真机接口」抽象成四个方法
# --------------------------------------------------------------------------
class FakeArm:
    """玩具机械臂。真机上这四个方法就是 move_to / close_gripper / lift / release。

    关键设计：失败是**按剧本发生**的（self.scripted_failures），不是随机数。
    这样每次运行输出都一样，方便你逐行对照代码理解控制流。
    真机 harness 里对应的是「环境给的客观成功判定」，而不是模型自己的解释。
    """

    def __init__(self, scripted_failures: dict[str, list[int]] | None = None) -> None:
        self.regions = {"A": ["cube_01"], "B": []}   # 每个区域里有哪些物体
        self.home = "home"
        self.grasped: str | None = None
        self.scripted_failures = scripted_failures or {
            "grasp": [1],        # 第 1 次抓取尝试失败
            "place": [3],        # 第 3 次放置尝试失败
            "recover": [1],      # 第 1 次恢复动作也失败 -> 触发接管
        }
        self.calls = {"grasp": 0, "place": 0, "recover": 0}
        self.events: list[str] = []

    def _should_fail(self, kind: str) -> bool:
        self.calls[kind] += 1
        return self.calls[kind] in self.scripted_failures.get(kind, [])

    def log(self, text: str) -> None:
        self.events.append(text)
        print(f"          · {text}")

    def pick(self, region: str) -> bool:
        """从 region 抓一个物体。返回 True/False —— 这就是最底层的能力。"""
        if not self.regions[region]:
            self.log(f"[{region}] 没有物体，无法抓取")
            return False
        if self._should_fail("grasp"):
            obj = self.regions[region][0]
            self.log(f"抓取 {obj} 失败（抓空 / 滑落），物体仍在 [{region}]")
            return False
        obj = self.regions[region].pop(0)
        self.grasped = obj
        self.log(f"抓取成功：{obj} 已在夹爪上")
        return True

    def place(self, region: str) -> bool:
        if self.grasped is None:
            self.log("夹爪是空的，无法放置")
            return False
        if self._should_fail("place"):
            self.log(f"放置 {self.grasped} 到 [{region}] 失败（掉落）")
            self.regions.setdefault(region, [])
            return False
        self.regions.setdefault(region, []).append(self.grasped)
        self.log(f"放置成功：{self.grasped} -> [{region}]")
        self.grasped = None
        return True

    def recover(self) -> bool:
        """恢复动作：真机上是「张开夹爪 / 退回 home / 重新视觉定位」。"""
        if self._should_fail("recover"):
            self.log("恢复失败：物体位置不明，需要人或大模型接管")
            return False
        if self.grasped is not None:
            self.regions["A"].append(self.grasped)
            self.log(f"恢复成功：把 {self.grasped} 放回 [A]，回到 home")
            self.grasped = None
        else:
            self.log("恢复成功：退回 home，重新定位物体")
        return True

    def snapshot(self) -> dict:
        return {"A": list(self.regions.get("A", [])), "B": list(self.regions.get("B", [])),
                "grasped": self.grasped, "home": self.home}


# --------------------------------------------------------------------------
# 2. 共享状态：py_trees 的 Blackboard（真 harness 里的「全局上下文」）
# --------------------------------------------------------------------------
def make_shared_state(arm: FakeArm) -> None:
    """把 arm 和统计计数挂到 Blackboard 上，所有行为节点通过 key 读写。

    这一步对应 RoboRSI 里 Manager 的角色：任务状态、技能版本、统计都放在
    一个共享位置，各个 agent / 节点只按 key 取用，不互相直接调用。
    """
    client = py_trees.blackboard.Client(name="shared")
    client.register_key(key="arm", access=common.Access.WRITE)
    for key in ("n_forward", "n_backward", "n_recover", "n_takeover", "n_round"):
        client.register_key(key=key, access=common.Access.WRITE)
    client.arm = arm
    client.n_forward = 0
    client.n_backward = 0
    client.n_recover = 0
    client.n_takeover = 0
    client.n_round = 0


class SharedBehaviour(py_trees.behaviour.Behaviour):
    """所有节点的基类：统一从 Blackboard 取 arm 和计数器。"""

    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        self.bb = py_trees.blackboard.Client(name=name)
        self.bb.register_key(key="arm", access=common.Access.READ)
        for key in ("n_forward", "n_backward", "n_recover", "n_takeover", "n_round"):
            self.bb.register_key(key=key, access=common.Access.WRITE)


# --------------------------------------------------------------------------
# 3. 叶子节点：条件与动作
# --------------------------------------------------------------------------
class HasObject(SharedBehaviour):
    """条件节点：某个区域里是否还有物体。SUCCESS / FAILURE，永不 RUNNING。"""

    def __init__(self, name: str, region: str) -> None:
        super().__init__(name)
        self.region = region

    def update(self) -> common.Status:
        has = bool(self.bb.arm.regions.get(self.region))
        return common.Status.SUCCESS if has else common.Status.FAILURE


class Transport(SharedBehaviour):
    """复合技能：从 src 搬到 dst。这是「一个可复用技能」的最小形态。

    真机上这里面是：视觉定位 -> 生成抓取位姿 -> IK -> 接近 -> 闭合 -> 抬升 -> 移动 -> 释放。
    harness 只关心它返回 SUCCESS 还是 FAILURE，不关心内部怎么做。
    这正是分层的意义：技能内部可以换成规划、换成 RL 策略、换成大模型调用，树不用改。
    """

    def __init__(self, name: str, src: str, dst: str, direction: str) -> None:
        super().__init__(name)
        self.src, self.dst, self.direction = src, dst, direction

    def update(self) -> common.Status:
        arm = self.bb.arm
        print(f"        -> 执行技能 {self.name}")
        ok = arm.pick(self.src) and arm.place(self.dst)
        if ok:
            if self.direction == "forward":
                self.bb.n_forward += 1
            else:
                self.bb.n_backward += 1
            return common.Status.SUCCESS
        return common.Status.FAILURE


class Recover(SharedBehaviour):
    """恢复节点：失败后先尝试自己救回来，救不回来才升级。"""

    def update(self) -> common.Status:
        print(f"        -> 尝试恢复 {self.name}")
        self.bb.n_recover += 1
        return common.Status.SUCCESS if self.bb.arm.recover() else common.Status.FAILURE


class RequestTakeover(SharedBehaviour):
    """最后一级：请求人类（或大模型）接管。

    在你的研究里，这个节点就是「LLM 接管」的插槽：
    现在只是打印一行，将来换成调用大模型生成恢复方案 + 受约束的机器人 API 执行。
    注意它返回 FAILURE —— 接管意味着这一轮自主执行没有成功，必须被记账。
    """

    def update(self) -> common.Status:
        print("        -> 请求接管（人类 / LLM）")
        self.bb.n_takeover += 1
        return common.Status.FAILURE


class NothingTodo(SharedBehaviour):
    """兜底条件：A、B 两个区域都空了才 SUCCESS。

    正常的来回搬运永远走不到这条分支（物体总在 A 或 B）。
    一旦走到，说明物体丢了或还卡在夹爪上 —— 这正是需要「复位」的信号，
    也是 reset-free 方案必须处理的边界情况：两个方向都失败时会进入无人能救的状态。
    """

    def update(self) -> common.Status:
        arm = self.bb.arm
        if arm.regions.get("A") or arm.regions.get("B"):
            return common.Status.FAILURE
        print(f"        -> 两个区域都空了（物体状态={arm.grasped}），需要复位")
        return common.Status.SUCCESS


class CountRound(SharedBehaviour):
    """什么都不做，只负责给每个 tick 编号，方便对照日志。"""

    def update(self) -> common.Status:
        self.bb.n_round += 1
        arm = self.bb.arm
        print(f"    [tick {self.bb.n_round}] 状态 A={arm.regions.get('A')} "
              f"B={arm.regions.get('B')} 夹爪={arm.grasped}")
        return common.Status.SUCCESS


# --------------------------------------------------------------------------
# 4. 组装树
# --------------------------------------------------------------------------
def build_transport_branch(direction: str, src: str, dst: str) -> py_trees.behaviour.Behaviour:
    """一个方向 = 条件 + 三级降级（直接做 / 恢复后重试 / 请求接管）。"""
    return py_trees.composites.Sequence(
        name=f"{direction} {src}->{dst}",
        memory=True,
        children=[
            HasObject(name=f"[{src}] 有物体?", region=src),
            py_trees.composites.Selector(
                name=f"{direction} 带恢复",
                memory=True,
                children=[
                    Transport(name=f"搬运({src}->{dst})", src=src, dst=dst,
                              direction="forward" if src == "A" else "backward"),
                    py_trees.composites.Sequence(
                        name="恢复后重试",
                        memory=True,
                        children=[
                            Recover(name="恢复动作"),
                            Transport(name=f"重试搬运({src}->{dst})", src=src, dst=dst,
                                      direction="forward" if src == "A" else "backward"),
                        ],
                    ),
                    RequestTakeover(name="请求接管"),
                ],
            ),
        ],
    )


def build_tree() -> py_trees.behaviour.Behaviour:
    root = py_trees.composites.Sequence(name="harness 主循环", memory=True, children=[
        CountRound(name="记录本轮"),
        py_trees.composites.Selector(
            name="任务调度（谁的条件满足就跑谁）",
            memory=False,     # 每个 tick 重新判断，正向失败/完成后能立刻切到反向
            children=[
                build_transport_branch("正向", "A", "B"),
                build_transport_branch("反向", "B", "A"),
                NothingTodo(name="两区皆空(需复位)"),
            ],
        ),
    ])
    return root


def status_of(behaviour) -> str:
    """把状态枚举变成短字符串，方便打印。"""
    return str(behaviour.status).split(".")[-1] if behaviour.status else "INVALID"


def branch_summary(root) -> str:
    """一句话说明这个 tick 里哪条分支跑了、结果如何。

    真 harness 里这一步就是可观测性：出问题时你要能立刻看出
    「是条件不满足所以没跑」还是「跑了但失败了」还是「跑了并进了恢复」。
    """
    watched = ("正向 A->B", "反向 B->A", "恢复动作", "请求接管", "两区皆空(需复位)")
    interesting = []
    for node in root.iterate():
        if node.name not in watched:
            continue
        status = status_of(node)
        if status == "INVALID":      # 这个 tick 根本没轮到它，不打印，避免噪音
            continue
        interesting.append(f"{node.name}={status}")
    return " ".join(interesting) if interesting else "无分支被执行"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticks", type=int, default=12, help="跑多少个 tick（默认 12）")
    parser.add_argument("--tree", action="store_true", help="只打印树结构，不执行")
    parser.add_argument("--verbose", action="store_true",
                        help="每个 tick 打印完整的带状态行为树（默认只打一行摘要，看着更清楚）")
    args = parser.parse_args()

    arm = FakeArm()
    make_shared_state(arm)
    root = build_tree()

    print("=" * 76)
    print("py_trees 行为树 harness 演示")
    print("=" * 76)
    print("树结构（Selector=择一执行 / Sequence=依次执行 / 叶子=具体动作或条件）：")
    print(py_trees.display.ascii_tree(root, indent=0))
    if args.tree:
        return 0

    print()
    print("初始状态：物体在 A 区。剧本设定的失败：第1次抓取失败、第3次放置失败、第1次恢复失败")
    print("-" * 76)

    for _ in range(args.ticks):
        root.tick_once()
        if args.verbose:
            print(py_trees.display.unicode_tree(root, indent=8, show_status=True))
        else:
            root_status = status_of(root)
            tag = {"SUCCESS": "本轮完成", "FAILURE": "本轮失败(需记账)",
                   "RUNNING": "本轮未完成"}.get(root_status, root_status)
            print(f"      本轮结果: {tag:<16} | {branch_summary(root)}")
        print("-" * 76)

    client = py_trees.blackboard.Client(name="report")
    for key in ("n_forward", "n_backward", "n_recover", "n_takeover"):
        client.register_key(key=key, access=common.Access.READ)

    print("=" * 76)
    print("统计")
    print("=" * 76)
    print(f"  正向搬运成功 {client.n_forward} 次 · 反向搬运成功 {client.n_backward} 次")
    print(f"  触发恢复 {client.n_recover} 次 · 请求接管 {client.n_takeover} 次")
    print(f"  最终状态 A={arm.regions['A']} B={arm.regions['B']} 夹爪={arm.grasped}")
    print()
    print("注意 tick 1：抓取失败 -> 恢复也失败 -> 请求接管，这一轮的根节点状态是 FAILURE。")
    print("这个 FAILURE 就是上层框架要记账的信号：它决定了要不要把这段轨迹送去训练、")
    print("要不要升级给人。别让兜底分支把它吞成 SUCCESS —— 那会让失败在统计里消失。")
    print()
    print("这棵树现在管的只是「流程」。它还不知道：")
    print("  · 搬运技能内部怎么做（规划？RL 策略？大模型调用？）")
    print("  · 失败原因是什么（感知错 / 抓取位姿错 / 控制抖）")
    print("  · 要不要根据这批轨迹去训练一个新版本，训练完能不能发布")
    print("后面三件事分别对应：技能层、诊断层（RoboRSI 的 Reviewer）、版本发布（registry/）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
