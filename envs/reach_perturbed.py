"""带扰动的 Reach：让「手写控制器不再免费满分」，RL 才有可学的东西。

为什么需要这个环境（实测驱动的结论，不是想当然）
    默认的 `envs/reach_env.py` 是一个**单积分器**：action 直接等于位移增量，
    没有延迟、没有噪声、没有动力学。这种任务上比例控制就是最优解——
    实测 `ProportionalReachSkill(gain=1)` 在默认配置和「严酷探针」配置下
    **都是 100% 成功率、2.6 步**，和训了 50000 步的 SAC 打平。

    这带来一个致命后果：`harness/loop.py` 想回答的那个问题
    （诊断+针对性采样 vs 固定均匀采样，谁学得更快）
    在这个环境里**不可判定**——两臂都会在 2 万步内撞到 100% 的天花板。
    实测 SAC 的起飞点在 10000~15000 步之间（见 `configs/reach_hard.yaml` 注释）。

    收紧成功圈也没用：只要动力学还是平凡的单积分器，比例控制照样满分
    （`configs/reach_hard.yaml` 下实测 100%）。**必须改动力学**。

这里加了三个真实机器人上一定存在、但默认 Reach 完全没有的东西：

    action_delay   执行延迟。发出去的指令要过 k 步才生效（真机上是通信 + 控制器周期）
    gain_noise     每个轴的增益不确定 ±g（电机标定误差、负载变化）
    drift          与位置相关的横向漂移场（末端受到侧向力 / 标定偏置）

加了这三样之后，「直接把剩余位移全给出去」会**过冲并振荡**：
指令延迟让修正总是慢半拍，增益误差让每次修正的量不准，漂移让目标方向一直在偏。
这时比例控制不再满分，而策略需要学会「提前减速、留余量、补偿漂移」——
这才是 RL 真正有活可干的地方，也才谈得上比较谁学得快。

与 `Reach3DEnv` 的关系：**继承，不修改**。观测布局、奖励形状、成功判定、
`reset(options={'goal': ...})` 这个采样钩子全部沿用父类，所以
`harness/` 和 `registry/` 的代码一行都不用改就能换到这个环境上。
唯一的差别是父类的 `_obs()` 会被加上观测噪声（如果开了 `obs_noise`），
而**奖励和成功判定仍然基于真实状态** `self.ee`/`self.goal` —— 这是刻意的：
扰动只应该影响策略能看到什么，绝不能影响环境怎么判成败。
"""

from __future__ import annotations

from collections import deque

import numpy as np
from gymnasium import spaces

from envs.reach_env import Reach3DEnv


class PerturbedReachEnv(Reach3DEnv):
    def __init__(
        self,
        *args,
        action_delay: int = 2,
        gain_noise: float = 0.5,
        drift: float = 0.004,
        obs_noise: float = 0.0,
        expose_queue: bool = False,
        obs_stack: int = 1,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.action_delay = max(0, int(action_delay))
        self.gain_noise = float(gain_noise)
        self.drift = float(drift)
        self.obs_noise = float(obs_noise)
        # 两个「补可观测性」的开关（run7 机理对照用，默认关、历史数字可比）：
        #   expose_queue  把**在途指令队列**放进观测 -> 恢复真 Markov 状态。
        #                 delay=2 时队列里恰好是「上一步发出、还没生效」的那条指令，
        #                 也就是记忆less MLP 唯一拿不到的信息。
        #   obs_stack     朴素观测堆叠（最近 k 帧拼接）。它**恢复不了**队列：
        #                 在途指令是策略自己的历史输出，且被执行时乘了每步随机增益，
        #                 从观测差分里反解不出来。它的作用是当「朴素记忆不够」的对照。
        self.expose_queue = bool(expose_queue)
        self.obs_stack = max(1, int(obs_stack))
        self._pending: deque = deque(maxlen=max(1, self.action_delay))
        self._reset_queue()
        self._obs_hist: deque = deque(maxlen=self.obs_stack)
        dim = 6 * self.obs_stack + (3 * self._pending.maxlen if self.expose_queue else 0)
        if dim != 6:
            self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(dim,),
                                                dtype=np.float32)

    def _reset_queue(self) -> None:
        self._pending = deque(
            (np.zeros(3, dtype=np.float64) for _ in range(max(1, self.action_delay))),
            maxlen=max(1, self.action_delay),
        )

    def reset(self, *, seed=None, options=None):
        self._reset_queue()
        self._obs_hist = deque(maxlen=self.obs_stack)
        obs, info = super().reset(seed=seed, options=options)
        return obs, info

    def _obs(self) -> np.ndarray:
        obs = Reach3DEnv._obs(self)
        if self.obs_noise > 0.0:
            obs = obs + self.np_random.normal(0.0, self.obs_noise, size=obs.shape).astype(np.float32)
        base = np.clip(obs, -1.0, 1.0).astype(np.float32)
        if self.obs_stack == 1 and not self.expose_queue:
            return base
        self._obs_hist.append(base)
        parts = list(self._obs_hist)
        while len(parts) < self.obs_stack:
            parts.insert(0, parts[0])
        stacked = np.concatenate(parts)
        if self.expose_queue:
            # 队列长度在 reset(=maxlen) 与 step 之后(=maxlen-1) 之间会跳，
            # 前面补零垫到定长，否则观测维度不稳、SB3 直接报错。
            queue = list(self._pending)
            while len(queue) < self._pending.maxlen:
                queue.insert(0, np.zeros(3, dtype=np.float32))
            queue_arr = np.clip(np.asarray(queue, dtype=np.float32).reshape(-1), -1.0, 1.0)
            stacked = np.concatenate([stacked, queue_arr])
        return stacked.astype(np.float32)

    def step(self, action):
        cmd = np.clip(np.asarray(action, dtype=np.float64).reshape(3), -1.0, 1.0)

        # 延迟：先把指令压进队列，取出的是 action_delay 步之前发的那条。
        # delay=0 时队列长度 1，压进去立刻取出来，等价于无延迟。
        self._pending.append(cmd)
        applied = np.asarray(self._pending.popleft(), dtype=np.float64)

        # 增益不确定：每个轴独立，模拟电机标定误差 / 负载差异。
        if self.gain_noise > 0.0:
            gain = self.np_random.uniform(1.0 - self.gain_noise, 1.0 + self.gain_noise, size=3)
        else:
            gain = np.ones(3)

        # 漂移场：绕 z 轴旋转的横向场，大小与到轴的距离成正比。
        # 折算成「等效动作量纲」再和指令相加，这样父类 step 里的
        # 位移积分、奖励、成功判定全部保持一致，不需要重写。
        drift_action = np.zeros(3)
        if self.drift != 0.0 and self.action_scale > 0:
            field = np.array([-self.ee[1], self.ee[0], 0.0], dtype=np.float64)
            drift_action = self.drift * field / self.action_scale

        effective = np.clip(applied * gain + drift_action, -1.0, 1.0)
        return super().step(effective)


def make_perturbed_reach_env(**kwargs) -> PerturbedReachEnv:
    return PerturbedReachEnv(**kwargs)
