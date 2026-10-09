"""Reach 任务上的两个具体技能：一个学出来的，一个手写的。

为什么要同时有这两个？因为 `skills/README.md` 的约定是「技能内部可以是规划、
RL 策略或大模型调用，对上层都一样」。只有把两种**来源完全不同的能力**塞进同一个
接口跑通，才能证明这个接口是真的抽象，而不是只为 SAC 量身定做的壳：

    ReachPolicySkill        读 SB3 的 .zip 权重。能力来自数据（参数被训练改写过）。
    ProportionalReachSkill  几十行比例控制。能力来自人写的公式，一次都不用训练。

第二个技能在 harness 里还有一个实际用途：**恢复动作**。真机上「退回安全位姿、
重新对准」这类动作通常用规划/控制写死最可靠，不该交给还在学的策略去试。

关于 `deadband`（故障注入开关）
    训练好的 SAC 在默认 Reach 上是 100% 成功率 —— 这意味着 harness 的
    「失败诊断 → 针对性采样」分支永远不会被触发，等于没测。
    `deadband` 让技能在离目标还剩 `deadband` 米时就停止输出动作，从而稳定地
    停在成功圈外面一点，制造可复现的「差一点」失败。
    **它只是测试夹具，不代表任何真实能力**，做正式对照实验时必须保持 0。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from skills.base import Skill, SkillMeta, compute_config_hash


def decode_reach_obs(obs: np.ndarray, half_space: float) -> tuple[np.ndarray, np.ndarray]:
    """把 Reach 的 6 维观测拆回物理量。

    `envs/reach_env.py::_obs()` 存的是 `[ee/half_space, goal/half_space]`，
    所以乘回去就是米制坐标。技能不该假设观测是归一化过的 —— 这一步显式写出来，
    换成 robosuite 时对应的就是「从 obs dict 里取 robot0_eef_pos 和 object pos」。
    """
    flat = np.asarray(obs, dtype=np.float64).reshape(-1)
    ee = flat[:3] * half_space
    goal = flat[3:6] * half_space
    return ee, goal


class ProportionalReachSkill(Skill):
    """规划/控制式技能：动作 = 剩余位移 × 增益，再裁剪到 [-1, 1]。

    一步走多少米由环境的 `action_scale` 决定（默认 0.05 m/单位动作），
    所以要先把「想要的位移」除以 `action_scale` 换算成动作量纲。
    这一步换算就是「动作接口语义」的核心：接的是增量还是绝对位姿、单位是什么。
    """

    def __init__(
        self,
        half_space: float = 0.15,
        action_scale: float = 0.05,
        gain: float = 1.0,
        deadband: float = 0.0,
        version: str = "v1",
    ) -> None:
        self.half_space = float(half_space)
        self.action_scale = float(action_scale)
        self.gain = float(gain)
        self.deadband = float(deadband)
        cfg = {
            "half_space": self.half_space,
            "action_scale": self.action_scale,
            "gain": self.gain,
            "deadband": self.deadband,
        }
        self.meta = SkillMeta(
            name="reach_proportional",
            version=version,
            kind="planner",
            source="skills/reach_skills.py::ProportionalReachSkill",
            trained_on="无需训练（人写公式）",
            config_hash=compute_config_hash(cfg),
            notes="比例控制基线 / 恢复动作；deadband>0 时是故障注入夹具",
        )

    def act(self, obs: np.ndarray) -> np.ndarray:
        ee, goal = decode_reach_obs(obs, self.half_space)
        delta = goal - ee
        dist = float(np.linalg.norm(delta))
        if self.deadband > 0.0 and dist <= self.deadband:
            return np.zeros(3, dtype=np.float32)
        action = self.gain * delta / self.action_scale
        return np.clip(action, -1.0, 1.0).astype(np.float32)


class ReachPolicySkill(Skill):
    """RL 策略技能：加载 stable-baselines3 存的 .zip，用 `predict()` 出动作。

    算法类型是从 ckpt 里自动识别的（复用 `scripts/eval_policy.load_any_policy`），
    所以 SAC / PPO 存的模型都能直接当技能用，不用改这里的代码。
    """

    def __init__(
        self,
        ckpt: str | Path,
        *,
        deterministic: bool = True,
        version: str = "",
        name: str = "reach_policy",
        trained_on: str = "",
        env_hash: str = "",
        eval_score: dict | None = None,
        notes: str = "",
    ) -> None:
        from scripts.eval_policy import load_any_policy

        self.ckpt = str(ckpt)
        if not Path(self.ckpt).exists():
            raise FileNotFoundError(f"找不到策略权重: {self.ckpt}")
        self.model, self.algo = load_any_policy(self.ckpt)
        self.deterministic = bool(deterministic)

        resolved_version = version or f"ckpt-{compute_config_hash(self.ckpt)}"
        self.meta = SkillMeta(
            name=name,
            version=resolved_version,
            kind="rl_policy",
            source=self.ckpt,
            trained_on=trained_on or str(Path(self.ckpt).parent),
            eval_score=eval_score or {},
            config_hash=compute_config_hash({"algo": self.algo, "deterministic": self.deterministic}),
            env_hash=env_hash,
            notes=notes or f"由 {self.algo} 训练得到",
        )

    def act(self, obs: np.ndarray) -> np.ndarray:
        action, _ = self.model.predict(obs, deterministic=self.deterministic)
        return np.asarray(action, dtype=np.float32).reshape(-1)


class RandomSkill(Skill):
    """随机策略。它也是一种「技能」，因为 harness 需要一个从零开始的起点，
    好让「学习带来的提升」有对照。`skill=None` 也能表达随机，但那样在日志里
    就没有版本可记，事后无法复现是哪一个基线。"""

    def __init__(self, seed: int = 0, version: str = "v1") -> None:
        self.rng = np.random.default_rng(seed)
        self.meta = SkillMeta(
            name="reach_random",
            version=version,
            kind="random",
            source="env.action_space.sample()",
            trained_on="无",
            config_hash=compute_config_hash({"seed": seed}),
            notes="不学习基线",
        )

    def reset(self) -> None:
        return None

    def act(self, obs: np.ndarray) -> np.ndarray:
        return self.rng.uniform(-1.0, 1.0, size=3).astype(np.float32)
