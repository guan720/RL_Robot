"""robosuite Lift 的 gymnasium 包装：课程阶梯上比 PickPlaceCan 低一级的接触任务。

为什么要有这一级（2026-09-23 的实测教训）：
    PickPlaceCan 在 100k 步预算下，稀疏 / shaped / shaped+示范预填三臂的冻结评测成功率
    **全部 0%**（shaped 臂 mean_reward 能到 12，说明学会了 reach/grasp/lift/hover，
    但 place 那一段在预算内没学会）。任务难度超过了当前单卡预算的能力上界，
    「学习是否发生」反而看不出来了。

    Lift = 移动 → 抓 → 提起，**没有放置段**：接触与抓取都在，但 horizon 更短、
    目标更近。它用来回答一个更基本的问题：这套栈（OSC + SAC + 我们的包装层）
    在接触任务上到底能不能把成功率从 0 训上去。能，再回 PickPlaceCan 加拐杖；
    不能，问题在栈不在任务。

奖励结构（robosuite 源码 lift.py，与 PickPlaceCan 不同，别混读）：
    reward_shaping=False：纯稀疏，提起（cube 高于桌面 0.04m）给 2.25；
    reward_shaping=True ：稠密 reach = 1 - tanh(10*dist) 加 grasp +0.25，提起仍 2.25。
    所以 Lift 的「shaped」档有稠密接近信号，随机探索也能拿到梯度方向——
    这和 PickPlaceCan 稀疏档「完全无信号」不是一回事，两任务的成功率不可直接互比。

成功判定与任务计数纪律继承父类：只认 `env._check_success()`（cube 真实高度），
一局内提起记 1 个 task，掉下再提起再记。
"""

from __future__ import annotations

from envs.robosuite_pickplace import RobosuitePickPlaceCan


class RobosuiteLift(RobosuitePickPlaceCan):
    """Lift + gymnasium API + state/pixels 两种观测模式（逻辑全在父类）。"""

    def __init__(self, obs_mode: str = "state", cams: tuple[str, ...] = ("agentview",),
                 cam_size: int = 64, horizon: int = 300, control_freq: int = 20,
                 reward_shaping: bool = False, hist: int = 1):
        super().__init__(obs_mode=obs_mode, cams=cams, cam_size=cam_size, horizon=horizon,
                         control_freq=control_freq, reward_shaping=reward_shaping,
                         suite_task="Lift", hist=hist)
