"""Small adapters shared by layered ACT/RL experiments and the harness.

The harness intentionally does not know whether a policy is a monolithic
actor, a phase-conditioned ACT policy, or a frozen controller with a residual
head.  These adapters keep that distinction in ``skills/`` and preserve the
single ``Skill`` contract.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import numpy as np

from skills.base import Skill, SkillMeta, compute_config_hash


class PhaseSkill(Skill):
    """Dispatch to a phase-specific skill while retaining one public skill."""

    def __init__(self, policies: Mapping[str, Skill], *, default: str = "approach",
                 name: str = "phase_skill", version: str = "v1") -> None:
        if not policies:
            raise ValueError("PhaseSkill 至少需要一个 phase policy")
        self.policies = dict(policies)
        self.default = default if default in self.policies else next(iter(self.policies))
        self.current_phase = self.default
        self.meta = SkillMeta(name=name, version=version, kind="layered_policy",
                              source="phase_dispatch",
                              config_hash=compute_config_hash({
                                  "phases": {k: v.meta.to_dict() for k, v in self.policies.items()}
                              }))

    def reset(self) -> None:
        self.current_phase = self.default
        for policy in self.policies.values():
            policy.reset()

    def act_with_context(self, obs: np.ndarray, context: dict[str, Any] | None = None) -> np.ndarray:
        context = context or {}
        phase = str(context.get("phase") or self.default)
        self.current_phase = phase if phase in self.policies else self.default
        return self.policies[self.current_phase].act_with_context(obs, context)

    def act(self, obs: np.ndarray) -> np.ndarray:
        return self.policies[self.current_phase].act(obs)


class ResidualSkill(Skill):
    """Compose a frozen base skill and a bounded residual policy."""

    def __init__(self, base: Skill, residual: Skill | Callable[..., np.ndarray],
                 *, scale: float = 0.25, name: str = "residual_skill", version: str = "v1") -> None:
        if scale <= 0:
            raise ValueError("residual scale 必须为正")
        self.base, self.residual, self.scale = base, residual, float(scale)
        self.meta = SkillMeta(name=name, version=version, kind="residual_policy",
                              source=f"{base.meta.short()}+residual",
                              config_hash=compute_config_hash({"scale": self.scale}))

    def reset(self) -> None:
        self.base.reset()
        if isinstance(self.residual, Skill):
            self.residual.reset()

    def act_with_context(self, obs: np.ndarray, context: dict[str, Any] | None = None) -> np.ndarray:
        context = context or {}
        base_action = np.asarray(self.base.act_with_context(obs, context), dtype=np.float32)
        if isinstance(self.residual, Skill):
            delta = self.residual.act_with_context(obs, context)
        else:
            try:
                delta = self.residual(obs, context)
            except TypeError:
                delta = self.residual(obs)
        delta = np.asarray(delta, dtype=np.float32).reshape(base_action.shape)
        return np.clip(base_action + self.scale * delta, -1.0, 1.0)

    def act(self, obs: np.ndarray) -> np.ndarray:
        return self.act_with_context(obs, {})
