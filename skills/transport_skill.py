"""把另一条并行工作线的正反向搬运环境，包进阶段 3 的技能接口（**只新增，不修改**）。

为什么现在包、不等那边跑完
--------------------------
包装的是**接口**，不是他们的代码：本文件只 `import` 环境类（只读），不碰
`envs/bidirectional_pickplace.py`、`envs/transport_perturbed.py`、
`scripts/train_transport.py`、`eval/transport_eval.py` 里任何一个字。
并发安全靠 `env_hash`：它覆盖「环境参数 + 扰动档位 + ckpt 文件内容 sha256」，
那边改环境或换 ckpt 之后，旧分数会在 `registry.publish.decide()` 的第 0 条
（环境一致性检查）被直接拒绝 —— 并发不会污染版本线，只会让旧版本显得「环境不一致」。

两个技能，和 reach 线保持同构
------------------------------
    TransportPolicySkill        冻结的 SB3 权重（能力来自数据，参数被训练改写过）
    ProportionalTransportSkill  二十行比例控制（能力来自公式；也是恢复动作的候选）

动作语义（从 `envs/bidirectional_pickplace.py` 读出来的，不是猜的）
    · 观测 7 维 = [ee/half, obj/half, target/half, +1 抓着 / -1 空手]
    · 动作 2 维 ∈ [-1, 1]，`action_scale` 米/单位动作（configs/transport_sac.yaml 里是 0.04）
    · 空手时子目标是物体、抓着时子目标是目标点（基类 `_subgoal()`）
    · 一局 `max_steps` 步里会连续做很多 task；成败看 `coverage_report()` 的
      `tasks_done / tasks_attempted` 与 `success_forward / success_backward`

「严酷探针」在 transport 上的对应物
----------------------------------
reach 线用「步数砍半 + 成功圈收紧」做探针；transport 上更自然的做法是
**同一套环境参数、换更重的扰动档位**（`envs/transport_perturbed.LEVELS`），
因为真机上「更难」就是延迟更大、增益更不准、更容易掉物，而不是步数更少。
档位名会进 `env_hash` 的 extra，所以标准分和探针分永远不会被混进同一条版本线。

用法见 `scripts/smoke_transport_skill.py`（--list / --smoke / --publish）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from skills.base import Skill, SkillMeta, compute_config_hash

REPO_ROOT = Path(__file__).resolve().parents[1]

# 另一条线已经训出来的冻结权重。只读引用，不复制、不重训。
FROZEN_CKPT = REPO_ROOT / "runs" / "20260922_205625_sac_transport_alternate" / "model_final.zip"
DEFAULT_CONFIG = REPO_ROOT / "configs" / "transport_sac.yaml"

# 与 configs/transport_sac.yaml 的 env 块一致的兜底默认值：yaml 读不到时不至于猜错量纲。
DEFAULT_ENV_KWARGS: dict[str, Any] = {
    "half": 0.15,
    "gap": 0.02,
    "action_scale": 0.04,
    "pick_radius": 0.02,
    "place_radius": 0.02,
    "max_steps": 400,
    "stall_limit": 120,
    "grid_n": 6,
    "reset_mode": "alternate",
    "recovery_mode": "resample",
    "pick_bonus": 2.0,
    "place_bonus": 8.0,
}


def sha256_of_file(path: str | Path) -> str:
    """文件内容指纹。用内容而不是 mtime：NFS 上的 mtime 不可信，内容才可信。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_transport_env_kwargs(config_path: str | Path = DEFAULT_CONFIG) -> dict:
    """读 `configs/transport_sac.yaml` 的 env 块（只读）。

    只认 `DEFAULT_ENV_KWARGS` 里已知的键：yaml 里将来新增的键如果环境类不认识，
    传进去会直接 TypeError；宁可忽略并让调用方显式传，也不要静默猜。
    """
    kwargs = dict(DEFAULT_ENV_KWARGS)
    try:
        import yaml

        data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
        env_block = data.get("env") or {}
        for key, value in env_block.items():
            if key in kwargs:
                kwargs[key] = value
    except Exception:
        pass                      # 读不到就用默认值；smoke 会把实际用的参数打印出来
    return kwargs


def available_levels() -> list[str]:
    """扰动档位清单（nominal + `envs/transport_perturbed.LEVELS` 的键）。"""
    levels = ["nominal"]
    try:
        from envs.transport_perturbed import LEVELS

        levels += [name for name in LEVELS if name not in levels]
    except Exception:
        pass
    return levels


def make_transport_env(env_kwargs: dict, level: str = "nominal"):
    """按扰动档位造环境。nominal 走基类，其余走 `PerturbedTransport2D` 的预设。

    预设**叠加**在 env_kwargs 之上（预设里的键覆盖 yaml 的同名键），
    所以「同一套几何参数、不同扰动强度」的对照是干净的。
    """
    level = (level or "nominal").lower()
    if level == "nominal":
        from envs.bidirectional_pickplace import make_transport_env as make_base

        return make_base(**env_kwargs)
    from envs.transport_perturbed import LEVELS, PerturbedTransport2D

    preset = dict(LEVELS.get(level, {}))
    if level not in LEVELS:
        raise ValueError(f"未知扰动档位 {level!r}，可选 {available_levels()}")
    return PerturbedTransport2D(**{**env_kwargs, **preset})


def decode_transport_obs(obs: np.ndarray, half: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
    """把 7 维观测拆回物理量：末端、物体、目标（米制）+ 是否抓着。"""
    flat = np.asarray(obs, dtype=np.float64).reshape(-1)
    if flat.size < 7:
        raise ValueError(f"transport 观测应为 7 维，实际 {flat.size} 维")
    ee = flat[0:2] * half
    obj = flat[2:4] * half
    target = flat[4:6] * half
    held = bool(flat[6] > 0.0)
    return ee, obj, target, held


def transport_env_hash(env_kwargs: dict, *, ckpt: str | Path | None = None,
                       level: str = "nominal", harsh_level: str = "",
                       extra: dict | None = None) -> str:
    """环境指纹：环境参数 + 扰动档位 + ckpt 内容。

    为什么 ckpt 也要进 env_hash？因为这里发布的是「冻结权重 + 环境」这个**组合**：
    换了权重，同一个版本号下的分数就不再代表同一个能力，门禁的「不掉点」会失去意义。
    """
    payload: dict[str, Any] = {
        "env_kwargs": env_kwargs,
        "level": level,
        "harsh_level": harsh_level,
        "ckpt": str(ckpt) if ckpt else "",
        "ckpt_sha256": sha256_of_file(ckpt) if ckpt else "",
    }
    if extra:
        payload["extra"] = extra
    return compute_config_hash(payload)


class ProportionalTransportSkill(Skill):
    """规划/控制式技能：动作 = (子目标 - 末端) * gain / action_scale，再裁剪。

    与 `skills/reach_skills.ProportionalReachSkill` 同构，只是子目标会随
    「空手/抓着」切换。在 harness 里它的角色是**恢复动作 / 基线**：
    真机上「退回、重新对准」这类动作交给写死的控制比交给还在学的策略可靠。
    """

    def __init__(self, half: float = 0.15, action_scale: float = 0.04, gain: float = 1.0,
                 deadband: float = 0.0, version: str = "v1", env_hash: str = "") -> None:
        self.half = float(half)
        self.action_scale = float(action_scale)
        self.gain = float(gain)
        self.deadband = float(deadband)
        config = {
            "half": self.half,
            "action_scale": self.action_scale,
            "gain": self.gain,
            "deadband": self.deadband,
        }
        self.meta = SkillMeta(
            name="transport_proportional",
            version=version,
            kind="planner",
            source="skills/transport_skill.py::ProportionalTransportSkill",
            trained_on="无需训练（人写公式）",
            config_hash=compute_config_hash(config),
            env_hash=env_hash,
            notes="正反向搬运的比例控制基线 / 恢复动作；deadband>0 时是故障注入夹具",
        )

    def act(self, obs: np.ndarray) -> np.ndarray:
        ee, obj, target, held = decode_transport_obs(obs, self.half)
        subgoal = target if held else obj
        delta = subgoal - ee
        if self.deadband > 0.0 and float(np.linalg.norm(delta)) <= self.deadband:
            return np.zeros(2, dtype=np.float32)
        action = self.gain * delta / self.action_scale
        return np.clip(action, -1.0, 1.0).astype(np.float32)


class TransportPolicySkill(Skill):
    """RL 策略技能：加载 SB3 的 .zip，用 `predict()` 出 2 维动作。

    算法类型从 ckpt 自动识别（复用 `scripts/eval_policy.load_any_policy`），
    所以 SAC / PPO 存的权重都能直接当技能用。
    """

    def __init__(self, ckpt: str | Path, *, deterministic: bool = True, version: str = "",
                 name: str = "transport_policy", trained_on: str = "", env_hash: str = "",
                 eval_score: dict | None = None, notes: str = "") -> None:
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
            notes=notes or f"由 {self.algo} 训练得到（冻结，不在本文件里重训）",
        )

    def act(self, obs: np.ndarray) -> np.ndarray:
        action, _ = self.model.predict(obs, deterministic=self.deterministic)
        return np.asarray(action, dtype=np.float32).reshape(-1)


# --------------------------------------------------------------------------- 评测
def run_transport_episodes(skill: Skill, env_kwargs: dict, *, level: str = "nominal",
                           n_episodes: int = 3, seed: int = 999,
                           max_steps_per_episode: int | None = None) -> dict:
    """transport 版的独立评测：成败只认环境记账，不听技能自己解释。

    与 reach 线的差别：transport 一局里包含很多 task，所以主指标是
    **任务完成率**（tasks_done / tasks_attempted），而不是「这一局成没成」。
    正反向分开记，是因为「只会正向」和「两个方向都会」是完全不同的能力。
    """
    env = make_transport_env(env_kwargs, level=level)
    limit = int(max_steps_per_episode or env_kwargs.get("max_steps", 400))
    steps_used = 0
    for episode in range(int(n_episodes)):
        obs, _info = env.reset(seed=int(seed) + episode)
        skill.reset()
        for _ in range(limit):
            obs, _reward, terminated, truncated, _info = env.step(skill(obs))
            steps_used += 1
            if terminated or truncated:
                break
    report = env.coverage_report()
    attempted = max(1, int(report["tasks_attempted"]))
    metrics = {
        "success_rate": round(report["tasks_done"] / attempted, 4),
        "success_forward_rate": round(report["success_forward"] / attempted, 4),
        "success_backward_rate": round(report["success_backward"] / attempted, 4),
        "coverage": report["coverage_union"],
        "coverage_pick": report["coverage_pick"],
        "coverage_place": report["coverage_place"],
        "tasks_done": report["tasks_done"],
        "tasks_attempted": report["tasks_attempted"],
        "manual_resets": report["manual_resets"],
        "slip_events": report["slip_events"],
        "push_events": report["push_events"],
        "env_steps": steps_used,
        "start_sources": report["start_sources"],
    }
    return {"n_episodes": int(n_episodes), "seed": int(seed), "level": level,
            "metrics": metrics, "report": report}


def score_transport_skill(skill: Skill, env_kwargs: dict, *, n_episodes: int = 3,
                          seed: int = 999, level: str = "nominal",
                          harsh_level: str = "medium") -> dict:
    """标准条件 + 扰动探针，两档都评。形状对齐 `registry.publish.summarize_scores`。"""
    standard = run_transport_episodes(skill, env_kwargs, level=level,
                                      n_episodes=n_episodes, seed=seed)
    harsh = run_transport_episodes(skill, env_kwargs, level=harsh_level,
                                   n_episodes=n_episodes, seed=seed)
    return {
        "n_episodes": int(n_episodes),
        "seed": int(seed),
        "standard": standard["metrics"],
        "harsh": {**harsh["metrics"], "probe": {"level": harsh_level}},
        "reports": {"standard": standard["report"], "harsh": harsh["report"]},
    }


def summarize_transport_scores(scores: dict) -> dict:
    """挑出门禁要看的那几个数。键名与 reach 线一致，`decide()` 才能直接复用。"""
    std = scores.get("standard") or {}
    harsh = scores.get("harsh") or {}
    return {
        "success_rate": std.get("success_rate"),
        "success_forward_rate": std.get("success_forward_rate"),
        "success_backward_rate": std.get("success_backward_rate"),
        "coverage": std.get("coverage"),
        "harsh_success_rate": harsh.get("success_rate"),
        "harsh_coverage": harsh.get("coverage"),
    }
