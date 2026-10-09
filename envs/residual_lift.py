"""Lift 环境的有界 residual 控制包装。

base controller 负责完整动作序列，SAC 只输出小幅修正。包装器保留原始
robosuite 观测给 base，给 learner 的 observation 仍是正常的 Gym observation。
"""

from __future__ import annotations

import numpy as np

from envs.robosuite_lift import RobosuiteLift
from scripts.demo_scripted_lift_rs import LiftStateMachine, _cube_pos


class ResidualLiftEnv(RobosuiteLift):
    """a = clip(a_base(raw_obs) + scale * a_residual, -1, 1)。"""

    def __init__(self, *args, residual_scale: float = 0.25,
                 residual_phases=("grasp", "lift"), **kwargs):
        super().__init__(*args, **kwargs)
        if residual_scale <= 0 or residual_scale > 1:
            raise ValueError("residual_scale 必须在 (0, 1] 内")
        self.residual_scale = float(residual_scale)
        self.residual_phases = frozenset(residual_phases)
        self._base = None

    def _raw(self):
        return self._env._get_observations()

    def _new_base(self):
        return LiftStateMachine(cube_z0=float(_cube_pos(self._raw())[2]))

    def reset(self, *, seed=None, options=None):
        obs, info = super().reset(seed=seed, options=options)
        self._base = self._new_base()
        return obs, info

    def step(self, residual):
        if self._base is None:
            self._base = self._new_base()
        base_action = np.asarray(self._base(self._raw()), dtype=np.float32)
        residual = np.asarray(residual, dtype=np.float32).reshape(base_action.shape)
        # 接近和下降由可靠 base 完成；RL 只修正真正接触相关的阶段。
        gate = np.zeros_like(base_action)
        if self._base.phase in self.residual_phases:
            gate[:3] = 1.0
            gate[6] = 1.0
        applied = gate * residual
        action = np.clip(base_action + self.residual_scale * applied, -1.0, 1.0)
        obs, reward, terminated, truncated, info = super().step(action)
        info = dict(info)
        info["base_action"] = base_action.copy()
        info["residual_action"] = applied.copy()
        info["residual_gate"] = gate.copy()
        info["executed_action"] = action.copy()
        info["phase"] = self._base.phase
        return obs, reward, terminated, truncated, info
