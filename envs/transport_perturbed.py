"""带扰动的正反向搬运：让「手写控制器不再免费满分」，RL 才有可学的东西。

为什么需要它（实测驱动，不是想当然）
------------------------------------
阶段 2 的抽象环境 `envs/bidirectional_pickplace.py` 是一个**理想单积分器**：
action 直接等于位移增量，没有延迟、没有噪声、抓取一定成功。结果实测
SAC 训 60000 步 = 3637 个任务 / 98.6%，而 20 行手写比例控制器 = 3627 / 98.6%
（`runs/20260922_205020_stage2_compare`）。**RL 只是打平了脚本上界**，
说明环境已经到天花板，再训也只是在天花板上磨。

更要紧的是：因为策略处处可靠，阶段 2 那个核心风险（reset-free 交替导致
起始状态分布塌缩）在这个环境里**根本没机会出现**——训练后起始覆盖是满格
36/36、熵 0.994。要研究「策略不可靠时交替会怎样」，就必须先把策略变得不可靠。

加了什么（每一项都对应真机上一定存在的东西）
--------------------------------------------
    action_delay          执行延迟：指令发出后 k 步才生效（通信 + 控制器周期）
    gain_noise            增益不确定：每步每轴实际增益在 [1-g, 1+g] 之间随机（电机标定、负载变化）
    drift                 常值漂移：每局随机一个方向，每步固定偏移（标定偏置 / 侧向力）
    obs_noise             观测噪声：只加在**观测**上（相机 / 状态估计误差）
    payload_gain          负载降速：抓着物体时位移比例乘以该系数（有负载时更慢更钝）
    approach_speed_limit  接近限速：进入抓取圈那一刻速度超过它就**把物体撞开**，抓取失败
    slip_prob             搬运滑落：每步有一定概率掉物，物体弹开 slip_dist

关于「谁能被脚本解决、谁不能」，有一个必须先说清的机理：
    比例控制是**状态反馈**，所以 gain_noise / drift / 负载降速这类「稳态误差」
    都能被反馈吸收——把增益调小一点（阻尼）就照样能到。
    唯独 `action_delay` 会引入相位滞后：增益 1 的纯比例控制在 1 步延迟下
    满足 x_{t+1} = x_t - x_{t-1}，特征根模长恰为 1 → **等幅振荡，永远停不进 2cm 圈**。
    所以延迟是打破脚本上界的主力，而 `approach_speed_limit` 和 `slip_prob`
    负责制造「必须学会小心接近、掉了要重抓」这类脚本没有的行为。

与基类的关系：**继承，不修改**
    只覆写 `envs/bidirectional_pickplace.py` 里预留的五个钩子
    （`_transform_action` / `_effective_scale` / `_grasp_ok` / `_carry_slips` / `_obs`），
    覆盖率统计、任务推进、正反向切换、规则式救场、成功判定**一行都没复制**。
    所以加难度前后的指标口径完全一致，两张表可以直接对比。

一条纪律（和 `envs/reach_perturbed.py` 一致）：
    **扰动只影响策略能看到什么、能做到什么，绝不影响环境怎么判成败。**
    `obs_noise` 只加在 `_obs()` 的返回值上；抓取/放置判定和覆盖率格子
    全部用真实状态 `self.ee` / `self.obj` / `self.target` 计算。
"""

from __future__ import annotations

from collections import deque

import numpy as np
from gymnasium import spaces

from envs.bidirectional_pickplace import BidirectionalTransport2D

# 几档预设，供 scripts/calibrate_transport.py 扫描用。
# 真正的实验配置写在 configs/transport_perturbed.yaml 里（显式数字，便于复现）。
LEVELS: dict[str, dict] = {
    "nominal": {},                                     # = 阶段 2 原环境
    "mild": {"action_delay": 1, "gain_noise": 0.20, "payload_gain": 0.85,
             "approach_speed_limit": 0.040, "slip_prob": 0.01},
    "medium": {"action_delay": 1, "gain_noise": 0.35, "drift": 0.004, "payload_gain": 0.75,
               "approach_speed_limit": 0.030, "push_dist": 0.035, "slip_prob": 0.03},
    "hard": {"action_delay": 2, "gain_noise": 0.50, "drift": 0.008, "payload_gain": 0.65,
             "approach_speed_limit": 0.022, "push_dist": 0.045, "slip_prob": 0.06},
}


class PerturbedTransport2D(BidirectionalTransport2D):
    def __init__(
        self,
        *args,
        action_delay: int = 0,
        gain_noise: float = 0.0,
        drift: float = 0.0,
        obs_noise: float = 0.0,
        payload_gain: float = 1.0,
        approach_speed_limit: float | None = None,
        push_dist: float = 0.035,
        slip_prob: float = 0.0,
        slip_dist: float = 0.045,
        randomize_per_episode: bool = True,
        include_velocity: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.action_delay = max(0, int(action_delay))
        self.gain_noise = float(gain_noise)
        self.drift = float(drift)
        self.obs_noise = float(obs_noise)
        self.payload_gain = float(payload_gain)
        self.approach_speed_limit = None if approach_speed_limit is None else float(approach_speed_limit)
        self.push_dist = float(push_dist)
        self.slip_prob = float(slip_prob)
        self.slip_dist = float(slip_dist)
        self.randomize_per_episode = bool(randomize_per_episode)
        # 观测里要不要带「上一步真实位移」（= 速度，用 action_scale 归一化）。
        # 为什么这是个真问题而不是锦上添花：
        #   一旦有执行延迟，最优控制律需要**微分项**（刹车），而微分项需要速度；
        #   速度又只能由相邻两帧观测差分得到。观测只有 [ee, obj, target, held] 时，
        #   无记忆的 MLP 策略原则上拿不到速度 -> 环境对它是**部分可观测**的。
        #   更妙的是：位移 = action_scale x 本局增益 x 上一步指令 + 漂移，
        #   所以把它放进观测，等于同时把「这一局的增益偏置」和「这一局的漂移方向」
        #   都变成可观测的 —— 策略才有可能做增益调度，而不是学一个折中的平均值。
        #   真机上这一项对应「关节速度 / 末端速度反馈」，本来就是标准观测量。
        # 默认 False：不改变任何已有实验的观测维度与结果（阶段 2 的数字必须可复现）。
        self.include_velocity = bool(include_velocity)
        if self.include_velocity:
            self.observation_space = spaces.Box(low=-1.5, high=1.5, shape=(9,), dtype=np.float32)

        self._pending: deque = deque()
        self._drift_vec = np.zeros(2)
        self._episode_gain = 1.0
        self._last_disp = np.zeros(2)
        self._reset_dynamics()

    # ------------------------------------------------------------------ 每局的动力学抽签
    def _reset_dynamics(self) -> None:
        """每局重新抽一次延迟队列、漂移方向、增益偏置。

        randomize_per_episode=True 就是最朴素的 domain randomization：
        策略不能记住「这一局的漂移往哪边」，只能学一个对各种动力学都成立的闭环。
        """
        # 队列长度必须是 action_delay + 1，不是 action_delay。
        # 每步「进一条、读最老的一条」，要让第 t 步发的指令在第 t+k 步生效，
        # 队列里就必须同时容下 k 条在途指令 + 当前这条 = k+1 条。
        # 写成 maxlen=k 时（deque 满了会自动挤掉最老的）实际延迟只有 k-1，
        # 而 k=1 会退化成**完全没有延迟**——标定时就是这么发现的：
        # 「只加延迟1」和「无扰动」跑出的数字一模一样。
        depth = self.action_delay + 1
        self._pending = deque(
            (np.zeros(2, dtype=np.float64) for _ in range(depth)), maxlen=depth,
        )
        self._last_disp = np.zeros(2)      # 速度观测跨局必须清零，否则第一帧带着上一局的速度
        if self.drift > 0:
            angle = self.np_random.uniform(0.0, 2.0 * np.pi)
            self._drift_vec = np.array([np.cos(angle), np.sin(angle)]) * self.drift
        else:
            self._drift_vec = np.zeros(2)
        self._episode_gain = (float(self.np_random.uniform(1.0 - self.gain_noise, 1.0 + self.gain_noise))
                              if (self.randomize_per_episode and self.gain_noise > 0) else 1.0)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        obs, info = super().reset(seed=seed, options=options)
        # 先 super().reset() 才有正确的 np_random 流，再抽本局的动力学
        self._reset_dynamics()
        return self._obs(), info

    # ------------------------------------------------------------------ 钩子覆写
    def _transform_action(self, act: np.ndarray) -> np.ndarray:
        """延迟 + 每步增益抖动。延迟用队列实现：进一条、出一条。"""
        out = act
        if self.action_delay > 0:
            self._pending.append(act.copy())
            out = self._pending[0]
        if self.gain_noise > 0 and not self.randomize_per_episode:
            out = out * self.np_random.uniform(1.0 - self.gain_noise, 1.0 + self.gain_noise, size=2)
        return np.clip(out * self._episode_gain, -1.5, 1.5)

    def _effective_scale(self) -> float:
        """抓着物体时更慢（负载）。"""
        return self.action_scale * (self.payload_gain if self.held else 1.0)

    def _apply_motion(self, act: np.ndarray) -> None:
        before = self.ee.copy()
        super()._apply_motion(act)
        if self._drift_vec.any():
            self.ee = np.clip(self.ee + self._drift_vec, -self.half, self.half)
            if self.held:
                self.obj = self.ee.copy()
        # 记录「这一步末端真实移动了多少」（含延迟、增益、负载、漂移的全部效果），
        # 归一化后就是观测里的速度分量。放在 super() 和漂移之后，才是真实发生的位移。
        self._last_disp = self.ee - before

    def _grasp_ok(self, dist: float) -> bool:
        """冲得太快 -> 把物体撞开，这一抓落空（真实的「接近过快打飞小物体」）。"""
        if self.approach_speed_limit is None:
            return True
        if self._last_speed <= self.approach_speed_limit:
            return True
        away = self.obj - self.ee
        norm = float(np.linalg.norm(away))
        direction = away / norm if norm > 1e-9 else np.array([1.0, 0.0])
        self.obj = np.clip(self.obj + direction * self.push_dist, -self.half, self.half)
        self.push_events += 1
        return False

    def _carry_slips(self, dist: float) -> bool:
        """搬运途中掉物：物体弹开一段，必须重新去抓（考验的是恢复能力）。"""
        if self.slip_prob <= 0 or self.np_random.random() >= self.slip_prob:
            return False
        angle = self.np_random.uniform(0.0, 2.0 * np.pi)
        offset = np.array([np.cos(angle), np.sin(angle)]) * self.slip_dist
        self.obj = np.clip(self.ee + offset, -self.half, self.half)
        return True

    def _obs(self) -> np.ndarray:
        """观测加噪；**判定和记账仍然用真实状态**（见模块 docstring 的纪律）。"""
        obs = super()._obs()
        if self.obs_noise > 0:
            noise = self.np_random.normal(0.0, self.obs_noise / self.half, size=6)
            obs = np.concatenate([obs[:6] + noise, obs[6:]]).astype(np.float32)
        if self.include_velocity:
            obs = np.concatenate([obs, self._last_disp / self.action_scale]).astype(np.float32)
        return np.clip(obs, -1.5, 1.5).astype(np.float32)


def make_perturbed_transport(level: str = "", **kwargs) -> PerturbedTransport2D:
    """按预设档位 + 覆盖参数构造环境。level 留空则只用 kwargs。"""
    params = dict(LEVELS.get(level, {}))
    params.update(kwargs)
    return PerturbedTransport2D(**params)
