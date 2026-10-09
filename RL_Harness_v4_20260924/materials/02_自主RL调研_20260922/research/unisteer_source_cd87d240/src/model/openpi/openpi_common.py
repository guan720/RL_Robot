from __future__ import annotations

from pathlib import Path
from typing import Any

from lerobot.configs import NormalizationMode
import numpy as np
import torch

from src.dataset.dataset import resolve_normalization_mode

try:
    from omegaconf import open_dict
except Exception:  # pragma: no cover
    from contextlib import contextmanager

    @contextmanager
    def open_dict(cfg):
        yield cfg


PRIMARY_IMAGE_KEY = "observation.images.image"
WRIST_IMAGE_KEY = "observation.images.image2"
LANGUAGE_TOKENS_KEY = "observation.language.tokens"
LANGUAGE_ATTENTION_MASK_KEY = "observation.language.attention_mask"
TASK_KEY = "task"
DEFAULT_OPENPI_TOKENIZER = "google/paligemma-3b-pt-224"


def _cfg_get(cfg: Any, key: str, default: Any = None) -> Any:
    if cfg is None:
        return default
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return getattr(cfg, key, default)


def openpi_config_device(device: str | torch.device) -> str:
    """LeRobot policy configs expect a device type, while trainers own rank placement."""
    return torch.device(device).type


def resolve_openpi_policy_type(cfg: Any) -> str:
    raw_value = str(_cfg_get(cfg, "openpi_policy_type", "pi0") or "pi0").strip().lower()
    aliases = {"pi0": "pi0", "pi05": "pi05", "pi0.5": "pi05", "pi0_5": "pi05"}
    try:
        return aliases[raw_value]
    except KeyError as exc:  # pragma: no cover - config validation
        raise ValueError(
            f"Unsupported openpi_policy_type={raw_value!r}. Expected one of {sorted(aliases)}"
        ) from exc


def has_explicit_openpi_policy_type(cfg: Any) -> bool:
    raw_value = _cfg_get(cfg, "openpi_policy_type", None)
    if raw_value is None:
        return False
    return str(raw_value).strip() != ""


def _to_stat_tensor(value: Any) -> torch.Tensor:
    return torch.as_tensor(np.asarray(value, dtype=np.float32))


def _image_to_float01(image: torch.Tensor) -> torch.Tensor:
    if image.dtype == torch.uint8:
        return image.to(torch.float32) / 255.0
    image = image.to(torch.float32)
    if torch.max(image).item() > 1.0:
        image = image / 255.0
    return image.clamp(0.0, 1.0)


def _flatten_state(proprio: torch.Tensor) -> torch.Tensor:
    if proprio.ndim == 3:
        return proprio[:, 0]
    if proprio.ndim == 2:
        return proprio
    raise ValueError(f"Unsupported proprio shape: {tuple(proprio.shape)}")


def _pad_or_trim_last_dim(tensor: torch.Tensor, target_dim: int) -> torch.Tensor:
    current_dim = int(tensor.shape[-1])
    if current_dim == target_dim:
        return tensor
    if current_dim > target_dim:
        return tensor[..., :target_dim]
    pad_shape = list(tensor.shape)
    pad_shape[-1] = target_dim - current_dim
    padding = torch.zeros(*pad_shape, dtype=tensor.dtype, device=tensor.device)
    return torch.cat([tensor, padding], dim=-1)


def _feature_stats_from_dataset(
    dataset_statistics: dict[str, Any],
    *,
    state_key: str,
    state_dim: int,
    action_key: str,
    action_dim: int,
) -> dict[str, dict[str, torch.Tensor]]:
    def _feature_block(source: dict[str, Any], target_dim: int) -> dict[str, torch.Tensor]:
        block: dict[str, torch.Tensor] = {}
        for stat_key in ("mean", "std", "min", "max", "q01", "q10", "q90", "q99"):
            if stat_key in source:
                block[stat_key] = _pad_or_trim_last_dim(
                    _to_stat_tensor(source[stat_key]), target_dim
                )
        return block

    return {
        state_key: _feature_block(dataset_statistics["proprio"], state_dim),
        action_key: _feature_block(dataset_statistics["action"], action_dim),
    }


def resolve_openpi_tokenizer_source(cfg: Any, *, family: str) -> str:
    candidate_keys = (f"{family}_tokenizer_path", "openpi_tokenizer_path", "pretrained_model_path")
    configured = ""
    for key in candidate_keys:
        value = str(_cfg_get(cfg, key, "") or "").strip()
        if value:
            configured = value
            break
    if configured and Path(configured).exists():
        return configured
    return DEFAULT_OPENPI_TOKENIZER


def sync_normal_policy_horizon(cfg: Any) -> int:
    """Use top-level horizon_steps as the only chunk-size source of truth."""
    horizon_steps = int(_cfg_get(cfg, "horizon_steps", 0))
    if horizon_steps < 1:
        raise ValueError(f"horizon_steps must be >= 1, got {horizon_steps}")

    data_cfg = _cfg_get(cfg, "data", None)
    for split_name in ("finetune", "finetune_val"):
        split_cfg = _cfg_get(data_cfg, split_name, None)
        if split_cfg is None:
            continue
        existing = _cfg_get(split_cfg, "action_future_size", None)
        if existing not in (None, "") and int(existing) != horizon_steps:
            raise ValueError(
                f"normal openpi path uses top-level horizon_steps as the only chunk-size source of truth; "
                f"found {split_name}.action_future_size={existing} but horizon_steps={horizon_steps}"
            )
        with open_dict(split_cfg):
            split_cfg.action_future_size = horizon_steps
    return horizon_steps


def _resolve_policy_normalization_mode(cfg: Any, field_name: str, default: str) -> str:
    data_cfg = _cfg_get(cfg, "data", None)
    finetune_cfg = _cfg_get(data_cfg, "finetune", None)
    return resolve_normalization_mode(_cfg_get(finetune_cfg, field_name, default))


def _to_lerobot_normalization_mode(mode_name: str) -> NormalizationMode:
    mapping = {
        "MEAN_STD": NormalizationMode.MEAN_STD,
        "MIN_MAX": NormalizationMode.MIN_MAX,
        "QUANTILES": NormalizationMode.QUANTILES,
        "QUANTILE10": NormalizationMode.QUANTILE10,
    }
    return mapping[resolve_normalization_mode(mode_name)]


def _resolve_checkpoint_path(cfg: Any, explicit_path: str | None) -> str | None:
    if explicit_path:
        return str(explicit_path)
    for key in ("inference_checkpoint_path", "resume_checkpoint_path", "init_ckpt"):
        value = _cfg_get(cfg, key, "")
        if value:
            return str(value)
    if bool(_cfg_get(cfg, "load_pretrained_weights", False)):
        pretrained_path = _cfg_get(cfg, "pretrained_model_path", "")
        if pretrained_path:
            return str(pretrained_path)
    return None


def resolve_openpi_train_hparam_source(cfg: Any) -> str:
    raw_value = str(_cfg_get(cfg, "openpi_train_hparam_source", "ckpt") or "ckpt").strip().lower()
    if raw_value not in {"ckpt", "config"}:
        raise ValueError(
            f"Unsupported openpi_train_hparam_source={raw_value!r}. Expected one of ['ckpt', 'config']."
        )
    return raw_value


def _load_training_checkpoint(
    policy: torch.nn.Module, checkpoint_path: str, *, device: str, family_name: str
) -> dict[str, Any]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    state_dict = checkpoint.get("model", checkpoint)
    if not isinstance(state_dict, dict):
        raise TypeError(f"Invalid checkpoint payload at {checkpoint_path}")
    cleaned_state_dict = {
        str(key).replace("_orig_mod.", ""): value for key, value in state_dict.items()
    }
    missing_keys, unexpected_keys = policy.load_state_dict(cleaned_state_dict, strict=False)
    if missing_keys:
        preview = ", ".join(missing_keys[:5])
        raise RuntimeError(
            f"Failed to load original {family_name} checkpoint from {checkpoint_path}. "
            f"Missing keys after load: {preview}"
        )
    if unexpected_keys:
        preview = ", ".join(unexpected_keys[:5])
        raise RuntimeError(
            f"Failed to load original {family_name} checkpoint from {checkpoint_path}. "
            f"Unexpected keys after load: {preview}"
        )
    return checkpoint


def apply_runtime_openpi_surface_config(
    loaded_config: Any, runtime_config: Any, *, train_hparam_source: str = "ckpt"
) -> Any:
    """Keep the model's internal padded width, but restore the task-facing runtime interface."""
    loaded_chunk = int(getattr(loaded_config, "chunk_size"))
    runtime_chunk = int(getattr(runtime_config, "chunk_size"))
    if loaded_chunk != runtime_chunk:
        raise ValueError(
            f"Loaded OpenPI checkpoint chunk_size={loaded_chunk} but runtime horizon_steps={runtime_chunk}. "
            "This path requires matching chunk sizes."
        )

    loaded_config.normalization_mapping = runtime_config.normalization_mapping
    loaded_config.input_features = runtime_config.input_features
    loaded_config.output_features = runtime_config.output_features
    loaded_config.n_action_steps = runtime_config.n_action_steps
    loaded_config.num_inference_steps = runtime_config.num_inference_steps

    if train_hparam_source == "config":
        for attr_name in (
            "optimizer_lr",
            "optimizer_weight_decay",
            "optimizer_grad_clip_norm",
            "optimizer_betas",
            "optimizer_eps",
            "scheduler_warmup_steps",
            "scheduler_decay_steps",
            "scheduler_decay_lr",
        ):
            if hasattr(runtime_config, attr_name):
                setattr(loaded_config, attr_name, getattr(runtime_config, attr_name))
    elif train_hparam_source != "ckpt":
        raise ValueError(
            f"Unsupported train_hparam_source={train_hparam_source!r}. Expected one of ['ckpt', 'config']."
        )
    return loaded_config
