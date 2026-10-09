from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch

from src.model.openpi.openpi_common import (
    _cfg_get,
    has_explicit_openpi_policy_type,
    resolve_openpi_policy_type,
)


@dataclass(frozen=True)
class OpenPiNoiseLayout:
    horizon_steps: int
    predicted_noise_steps: int
    per_step_noise_dim: int
    expand_mode: str = "repeat_last"
    parameterization: str = "repeat"
    projection_steps: int = 1

    @property
    def actor_noise_dim(self) -> int:
        return int(self.predicted_noise_steps) * int(self.per_step_noise_dim)

    @property
    def full_noise_dim(self) -> int:
        return int(self.horizon_steps) * int(self.per_step_noise_dim)


def resolve_openpi_internal_noise_dim(cfg: Any) -> int:
    policy_type = resolve_openpi_policy_type(cfg)
    key = "pi05_max_action_dim" if policy_type == "pi05" else "pi0_max_action_dim"
    dim = int(_cfg_get(cfg, key, 32))
    if dim < 1:
        raise ValueError(f"{key} must be >= 1, got {dim}")
    return dim


def resolve_openpi_noise_layout(cfg: Any) -> OpenPiNoiseLayout:
    if not has_explicit_openpi_policy_type(cfg):
        raise ValueError(
            "OpenPI UniSteer noise layout requires explicit openpi_policy_type in config"
        )

    unisteer_cfg = _cfg_get(cfg, "unisteer", None)
    horizon_steps = int(_cfg_get(cfg, "horizon_steps", 0))
    predicted_noise_steps = int(_cfg_get(unisteer_cfg, "predicted_noise_steps", 1))
    per_step_noise_dim = resolve_openpi_internal_noise_dim(cfg)
    expand_mode = (
        str(_cfg_get(unisteer_cfg, "noise_expand_mode", "repeat_last") or "repeat_last")
        .strip()
        .lower()
    )
    parameterization = (
        str(_cfg_get(unisteer_cfg, "noise_parameterization", "repeat") or "repeat").strip().lower()
    )
    projection_steps = int(predicted_noise_steps)

    if horizon_steps < 1:
        raise ValueError(f"horizon_steps must be >= 1, got {horizon_steps}")
    if predicted_noise_steps < 1 or predicted_noise_steps > horizon_steps:
        raise ValueError(
            f"unisteer.predicted_noise_steps must be in [1, horizon_steps], got "
            f"{predicted_noise_steps} with horizon_steps={horizon_steps}"
        )
    if expand_mode != "repeat_last":
        raise ValueError(
            f"Unsupported unisteer.noise_expand_mode={expand_mode!r}; expected 'repeat_last'"
        )
    if parameterization not in {"repeat", "mean_time"}:
        raise ValueError(
            f"Unsupported unisteer.noise_parameterization={parameterization!r}; expected 'repeat' or 'mean_time'"
        )
    if parameterization == "mean_time" and predicted_noise_steps != 1:
        raise ValueError(
            "unisteer.noise_parameterization='mean_time' keeps the actor at one compact noise step, "
            f"so unisteer.predicted_noise_steps must be 1, got {predicted_noise_steps}"
        )
    if parameterization == "mean_time":
        raw_projection_steps = _cfg_get(cfg, "control_replan_interval", None)
        if raw_projection_steps in (None, "", "null"):
            raise ValueError(
                "unisteer.noise_parameterization='mean_time' requires top-level control_replan_interval"
            )
        projection_steps = int(raw_projection_steps)
        if projection_steps < 1 or projection_steps > horizon_steps:
            raise ValueError(
                f"control_replan_interval must be in [1, horizon_steps] for mean_time projection, "
                f"got {projection_steps} with horizon_steps={horizon_steps}"
            )

    layout = OpenPiNoiseLayout(
        horizon_steps=horizon_steps,
        predicted_noise_steps=predicted_noise_steps,
        per_step_noise_dim=per_step_noise_dim,
        expand_mode=expand_mode,
        parameterization=parameterization,
        projection_steps=projection_steps,
    )

    explicit_noise_action_dim = _cfg_get(unisteer_cfg, "noise_action_dim", None)
    if explicit_noise_action_dim not in (None, "", "null"):
        explicit_noise_action_dim = int(explicit_noise_action_dim)
        if explicit_noise_action_dim != layout.actor_noise_dim:
            raise ValueError(
                "OpenPI UniSteer uses predicted_noise_steps * internal_noise_dim as the single source of truth; "
                f"got unisteer.noise_action_dim={explicit_noise_action_dim} but expected {layout.actor_noise_dim} "
                f"for predicted_noise_steps={layout.predicted_noise_steps} and internal_noise_dim={layout.per_step_noise_dim}"
            )

    return layout


def _coerce_noise_tensor(
    noise_action: Any, *, device: torch.device | str | None, dtype: torch.dtype | None
) -> torch.Tensor:
    if isinstance(noise_action, torch.Tensor):
        tensor = noise_action
        if device is not None and tensor.device != torch.device(device):
            tensor = tensor.to(device=device)
        if dtype is not None and tensor.dtype != dtype:
            tensor = tensor.to(dtype=dtype)
        return tensor
    return torch.as_tensor(
        noise_action, device=device, dtype=dtype if dtype is not None else torch.float32
    )


def expand_actor_noise_to_full_torch(
    noise_action: Any,
    *,
    layout: OpenPiNoiseLayout,
    batch_size: int | None = None,
    target_steps: int | None = None,
    device: torch.device | str | None = None,
    dtype: torch.dtype | None = torch.float32,
) -> torch.Tensor:
    tensor = _coerce_noise_tensor(noise_action, device=device, dtype=dtype)

    actor_steps = int(layout.predicted_noise_steps)
    full_steps = int(layout.horizon_steps)
    output_steps = full_steps if target_steps is None else int(target_steps)
    step_dim = int(layout.per_step_noise_dim)
    actor_flat_dim = int(layout.actor_noise_dim)
    full_flat_dim = int(layout.full_noise_dim)

    if output_steps < actor_steps:
        raise ValueError(
            f"target_steps must be >= predicted_noise_steps={actor_steps}, got {output_steps}"
        )
    if output_steps > full_steps:
        raise ValueError(f"target_steps must be <= horizon_steps={full_steps}, got {output_steps}")

    if tensor.ndim == 1:
        if int(tensor.numel()) == actor_flat_dim:
            tensor = tensor.view(1, actor_steps, step_dim)
        elif int(tensor.numel()) == full_flat_dim:
            tensor = tensor.view(1, full_steps, step_dim)
        else:
            raise ValueError(
                f"Unsupported 1D noise_action size={tensor.numel()}; expected {actor_flat_dim} or {full_flat_dim}"
            )
    elif tensor.ndim == 2:
        shape = tuple(int(v) for v in tensor.shape)
        if shape == (actor_steps, step_dim):
            tensor = tensor.unsqueeze(0)
        elif shape == (output_steps, step_dim):
            tensor = tensor.unsqueeze(0)
        elif shape == (full_steps, step_dim):
            tensor = tensor.unsqueeze(0)
        elif shape[1] == actor_flat_dim:
            tensor = tensor.view(shape[0], actor_steps, step_dim)
        elif shape[1] == full_flat_dim:
            tensor = tensor.view(shape[0], full_steps, step_dim)
        else:
            raise ValueError(
                f"Unsupported 2D noise_action shape={shape}; expected (*,{actor_flat_dim}) or (*,{full_flat_dim}) or ({actor_steps},{step_dim}) or ({full_steps},{step_dim})"
            )
    elif tensor.ndim == 3:
        shape = tuple(int(v) for v in tensor.shape)
        if shape[1:] not in (
            (actor_steps, step_dim),
            (output_steps, step_dim),
            (full_steps, step_dim),
        ):
            raise ValueError(
                f"Unsupported 3D noise_action shape={shape}; expected [B,{actor_steps},{step_dim}], "
                f"[B,{output_steps},{step_dim}], or [B,{full_steps},{step_dim}]"
            )
    else:
        raise ValueError(f"Unsupported noise_action rank={tensor.ndim}; expected rank 1, 2, or 3")

    if batch_size is not None:
        batch_size = int(batch_size)
        if tensor.shape[0] == 1 and batch_size > 1:
            tensor = tensor.expand(batch_size, -1, -1)
        elif int(tensor.shape[0]) != batch_size:
            raise ValueError(
                f"noise_action batch mismatch: got batch={tensor.shape[0]} expected {batch_size}"
            )

    if int(tensor.shape[1]) == full_steps:
        return tensor[:, :output_steps, :]
    if int(tensor.shape[1]) == output_steps:
        return tensor
    if layout.expand_mode != "repeat_last":
        raise ValueError(f"Unsupported expand_mode={layout.expand_mode!r}")

    repeat_count = output_steps - int(tensor.shape[1])
    tail = tensor[:, -1:, :].expand(int(tensor.shape[0]), repeat_count, step_dim)
    return torch.cat([tensor, tail], dim=1)


def project_full_noise_to_actor_torch(
    full_noise: Any,
    *,
    layout: OpenPiNoiseLayout,
    device: torch.device | str | None = None,
    dtype: torch.dtype | None = torch.float32,
) -> torch.Tensor:
    """Project full OpenPI inverse noise [B,H,D] into the actor's compact noise space.

    The actor space is the single target space used by UniSteer actor SFT.
    For the 32-dim actor case, `repeat` preserves the first-step target while
    `mean_time` averages the first `control_replan_interval` full-noise steps.
    """

    tensor = _coerce_noise_tensor(full_noise, device=device, dtype=dtype)
    full_steps = int(layout.horizon_steps)
    actor_steps = int(layout.predicted_noise_steps)
    step_dim = int(layout.per_step_noise_dim)
    full_flat_dim = int(layout.full_noise_dim)

    if tensor.ndim == 1:
        if int(tensor.numel()) != full_flat_dim:
            raise ValueError(
                f"Expected full inverse noise size={full_flat_dim}, got {tensor.numel()}"
            )
        tensor = tensor.view(1, full_steps, step_dim)
    elif tensor.ndim == 2:
        shape = tuple(int(v) for v in tensor.shape)
        if shape[1] != full_flat_dim:
            raise ValueError(f"Expected full inverse noise shape [B,{full_flat_dim}], got {shape}")
        tensor = tensor.view(shape[0], full_steps, step_dim)
    elif tensor.ndim == 3:
        shape = tuple(int(v) for v in tensor.shape)
        if shape[1:] != (full_steps, step_dim):
            raise ValueError(
                f"Expected full inverse noise shape [B,{full_steps},{step_dim}], got {shape}"
            )
    else:
        raise ValueError(f"Unsupported full_noise rank={tensor.ndim}; expected rank 1, 2, or 3")

    if actor_steps == full_steps:
        if layout.parameterization != "repeat":
            raise ValueError(
                "Full-noise actor targets require unisteer.noise_parameterization='repeat', "
                f"got {layout.parameterization!r}"
            )
        return tensor.reshape(int(tensor.shape[0]), -1)

    if layout.parameterization == "repeat":
        if actor_steps != 1:
            raise ValueError(
                "Compact repeat actor targets currently require unisteer.predicted_noise_steps=1, "
                f"got {actor_steps}"
            )
        actor_noise = tensor[:, :1, :]
    elif layout.parameterization == "mean_time":
        if actor_steps != 1:
            raise ValueError(
                "mean_time actor targets require unisteer.predicted_noise_steps=1, "
                f"got {actor_steps}"
            )
        projection_steps = int(layout.projection_steps)
        if projection_steps < 1 or projection_steps > full_steps:
            raise ValueError(
                f"mean_time projection_steps must be in [1, {full_steps}], got {projection_steps}"
            )
        actor_noise = tensor[:, :projection_steps, :].mean(dim=1, keepdim=True)
    else:
        raise ValueError(f"Unsupported unisteer.noise_parameterization={layout.parameterization!r}")

    return actor_noise.reshape(int(tensor.shape[0]), int(layout.actor_noise_dim))
