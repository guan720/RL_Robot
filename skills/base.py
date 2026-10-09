"""技能层的地基：Skill 接口 + SkillMeta 版本记账 + EpisodeRecord 轨迹记账。

为什么要有这一层？因为上层 harness 只应该关心「现在跑哪个能力、失败了走哪条路」，
而不应该关心这个能力内部是**神经网络**、**比例控制规则**还是**大模型调用**。
把三者压成同一个接口，harness 的代码在阶段 4 换成真机时一行都不用改：

    skill(obs) -> action                    # 单步：给观测，还动作
    skill.meta -> SkillMeta                 # 这个能力是哪个版本、怎么来的、考了多少分
    run_episode(env, skill, ...) -> Record  # 整局：跑完返回客观成败与距离轨迹

`SkillMeta` 里的 `config_hash` 是刻意加的：技能**代码/规则**变更和**策略参数**变更
必须分开记账（见 `skills/README.md`）。有了 hash，事后才能回答
「这次成功率提升到底来自改了网络权重，还是来自改了环境参数/评测口径」。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np


def compute_config_hash(obj: Any) -> str:
    """把任意可 JSON 化的配置压成 16 位短 hash，用于「条件是否变了」的判定。"""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclasses.dataclass
class SkillMeta:
    """一个技能版本的身份证。发布进 `registry/` 时会原样写成 meta.json。"""

    name: str
    version: str
    kind: str = "rl_policy"          # rl_policy | planner | llm | random
    source: str = ""                 # ckpt 路径，或规则/提示词的描述
    trained_on: str = ""             # 训练用的 run 目录 / 数据集 / 交互预算
    eval_score: dict = dataclasses.field(default_factory=dict)
    config_hash: str = ""            # 训练/规则配置的 hash
    env_hash: str = ""               # 环境参数的 hash（与 config_hash 分开！）
    created_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SkillMeta":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def short(self) -> str:
        return f"{self.name}@{self.version}({self.kind})"


class Skill:
    """技能基类。子类只需要实现 `act(obs)`；`__call__` 已经接好。

    `reset()` 在每一局开始时调用，用来清掉技能自己的内部状态
    （积分项、历史观测、上一帧动作）。无状态技能可以不实现。
    """

    meta: SkillMeta

    def reset(self) -> None:
        return None

    def act(self, obs: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def act_with_context(self, obs: np.ndarray, context: dict[str, Any] | None = None) -> np.ndarray:
        """Optional hook for layered ACT/RL policies; legacy skills use ``act``."""
        return self.act(obs)

    def __call__(self, obs: np.ndarray) -> np.ndarray:
        return self.act(obs)

    def close(self) -> None:
        return None

    def __repr__(self) -> str:
        meta = getattr(self, "meta", None)
        return f"<Skill {meta.short() if meta else 'unnamed'}>"


@dataclasses.dataclass
class EpisodeRecord:
    """一局交互的客观记录。成败只认环境给的 `info['success']`，不听技能自己解释。

    `dist_trace` 保留每步到目标的距离，是诊断层唯一需要的原始信号：
    光看 final_dist 分不清「一直没接近」和「接近了又抖出去」，
    而这两种失败对应的补救措施完全不同（前者要采更近的目标，后者要采边界目标）。
    """

    direction: str
    role: str                        # primary | recovery
    skill: str
    seed: int
    steps: int
    success: bool
    terminated: bool
    truncated: bool
    init_dist: float
    final_dist: float
    min_dist: float
    goal: list
    label: str = ""
    dist_trace: list = dataclasses.field(default_factory=list)
    env_steps: int = 0               # 消耗的环境交互步数（预算记账用）
    phase_trace: list = dataclasses.field(default_factory=list)
    success_raw: bool | None = None
    success_grasp_verified: bool | None = None
    failure_phase: str = ""
    max_rise: float | None = None
    held_steps: int = 0
    regrasp_count: int = 0

    def to_dict(self) -> dict:
        data = dataclasses.asdict(self)
        data["dist_trace"] = [round(float(x), 5) for x in self.dist_trace]
        data["goal"] = [round(float(x), 5) for x in self.goal]
        data["phase_trace"] = [str(x) for x in self.phase_trace]
        for key in ("init_dist", "final_dist", "min_dist"):
            data[key] = round(float(data[key]), 5)
        return data


def run_episode(
    env: Any,
    skill: Skill | None,
    *,
    seed: int = 0,
    direction: str = "forward",
    role: str = "primary",
    goal: np.ndarray | None = None,
    max_steps: int | None = None,
) -> EpisodeRecord:
    """在 env 上跑完整一局，返回客观记录。

    `skill=None` 表示随机策略基线（回答「不学习能得多少分」）。
    `goal` 不为空时通过 `env.reset(options={'goal': ...})` 指定初始目标，
    这是「针对性采样」进入训练的通道：采样只影响训练时看到的题，
    **绝不影响评测**，否则两组的分数没有可比性。
    """
    options = {"goal": np.asarray(goal, dtype=np.float64).reshape(3)} if goal is not None else None
    obs, info = env.reset(seed=seed, options=options)

    skill_name = "random"
    if skill is not None:
        skill.reset()
        skill_name = skill.meta.name + "@" + skill.meta.version

    trace = [float(info.get("dist", float("nan")))]
    phase_trace = [str(info["phase"])] if "phase" in info else []
    held_steps = 0
    regrasp_count = 0
    max_rise = None
    last_info = dict(info or {})
    steps = 0
    terminated = truncated = False
    while True:
        if skill is None:
            action = env.action_space.sample()
        else:
            action = skill.act_with_context(
                obs, {"step": steps, "info": dict(last_info),
                      "phase": last_info.get("phase"), "direction": direction,
                      "goal": goal})
        obs, _reward, terminated, truncated, info = env.step(action)
        info = dict(info or {})
        last_info = info
        steps += 1
        trace.append(float(info.get("dist", float("nan"))))
        if "phase" in info:
            phase_trace.append(str(info["phase"]))
        held_steps += int(bool(info.get("held", info.get("grasp_verified", False))))
        regrasp_count = max(regrasp_count, int(info.get("regrasp_count", 0) or 0))
        if info.get("rise") is not None:
            try:
                max_rise = max(float(max_rise or 0.0), float(info["rise"]))
            except (TypeError, ValueError):
                pass
        if terminated or truncated:
            break
        if max_steps is not None and steps >= max_steps:
            truncated = True
            break

    finite = [d for d in trace if np.isfinite(d)]
    return EpisodeRecord(
        direction=direction,
        role=role,
        skill=skill_name,
        seed=int(seed),
        steps=int(steps),
        success=bool(info.get("success", False)),
        terminated=bool(terminated),
        truncated=bool(truncated),
        init_dist=float(trace[0]) if finite else float("nan"),
        final_dist=float(info.get("dist", trace[-1] if finite else float("nan"))),
        min_dist=float(min(finite)) if finite else float("nan"),
        goal=[float(x) for x in np.asarray(getattr(env, "goal", [0.0, 0.0, 0.0])).reshape(-1)],
        dist_trace=trace,
        env_steps=int(steps),
        phase_trace=phase_trace,
        success_raw=bool(info.get("success", False)),
        success_grasp_verified=(bool(info["success_grasp_verified"])
                                if "success_grasp_verified" in info else None),
        failure_phase=(str(info.get("failure_phase", "")) if not info.get("success") else ""),
        max_rise=max_rise,
        held_steps=int(held_steps),
        regrasp_count=int(regrasp_count),
    )


def timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_tag() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: str | Path, obj: Any) -> Path:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return p
