"""
PyTorch latent-noise RL core for UniSteer.

Core choices:

- RL acts in the latent/noise action space only.
- Observations are dicts with `pixels` and `state`.
- `state` is expected to be `robot_state + pi0_prefix_rep_last_token`.
- The replay buffer stores online transitions as
  `(observations, actions=noise_actions, rewards, masks, discount, next_observations)`.

This file intentionally does not keep the older custom `Q^A / Q^W + decoder_obs`
path. The goal here is a single UniSteer observation/action pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import threading
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from loguru import logger
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from src.model.openpi.openpi_common import has_explicit_openpi_policy_type
from src.model.openpi.openpi_noise import resolve_openpi_noise_layout


def _cfg_get(cfg: Any, key: str, default: Any = None) -> Any:
    if cfg is None:
        return default
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return getattr(cfg, key, default)


def _to_numpy(value: Any, *, dtype: Optional[np.dtype] = None) -> np.ndarray:
    if isinstance(value, np.ndarray):
        arr = value
    elif isinstance(value, torch.Tensor):
        tensor = value.detach().cpu()
        if tensor.is_floating_point():
            tensor = tensor.to(dtype=torch.float32)
        arr = tensor.numpy()
    else:
        arr = np.asarray(value)
    if dtype is not None:
        arr = arr.astype(dtype, copy=False)
    return arr


def _normalize_state_array(state: Any) -> np.ndarray:
    arr = _to_numpy(state, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr[:, None]
    elif arr.ndim == 2 and arr.shape[-1] == 1:
        pass
    else:
        raise ValueError(f"UniSteer state must have shape [D] or [D, 1], got {list(arr.shape)}")
    return np.ascontiguousarray(arr, dtype=np.float32)


def _normalize_pixels_array(pixels: Any) -> np.ndarray:
    arr = _to_numpy(pixels)
    if arr.ndim == 3:
        arr = arr[..., None]
    elif arr.ndim == 4 and arr.shape[-1] == 1:
        pass
    else:
        raise ValueError(
            f"UniSteer pixels must have shape [H, W, C] or [H, W, C, 1], got {list(arr.shape)}"
        )
    return np.ascontiguousarray(arr.astype(np.uint8, copy=False))


def normalize_unisteer_observation(observation: Mapping[str, Any]) -> Dict[str, np.ndarray]:
    if not isinstance(observation, Mapping):
        raise TypeError(f"UniSteer observation must be a mapping, got {type(observation).__name__}")
    if "pixels" not in observation or "state" not in observation:
        raise KeyError("UniSteer observation must contain 'pixels' and 'state'")
    return {
        "pixels": _normalize_pixels_array(observation["pixels"]),
        "state": _normalize_state_array(observation["state"]),
    }


def batch_unisteer_observations_to_torch(
    observation: Mapping[str, Any], device: torch.device
) -> Dict[str, torch.Tensor]:
    pixels_value = observation["pixels"]
    if isinstance(pixels_value, torch.Tensor):
        pixels_t = pixels_value
        if pixels_t.ndim == 3:
            if (
                int(pixels_t.shape[0]) <= 16
                and int(pixels_t.shape[1]) > 16
                and int(pixels_t.shape[2]) > 16
            ):
                pixels_t = pixels_t.unsqueeze(0)
            elif (
                int(pixels_t.shape[-1]) <= 16
                and int(pixels_t.shape[0]) > 16
                and int(pixels_t.shape[1]) > 16
            ):
                pixels_t = pixels_t.permute(2, 0, 1).unsqueeze(0)
            else:
                raise ValueError(
                    f"Batched UniSteer pixels must be CHW or HWC, got {list(pixels_t.shape)}"
                )
        elif pixels_t.ndim == 4:
            if (
                int(pixels_t.shape[1]) <= 16
                and int(pixels_t.shape[2]) > 16
                and int(pixels_t.shape[3]) > 16
            ):
                pass
            elif (
                int(pixels_t.shape[-1]) <= 16
                and int(pixels_t.shape[1]) > 16
                and int(pixels_t.shape[2]) > 16
            ):
                pixels_t = pixels_t.permute(0, 3, 1, 2)
            else:
                raise ValueError(
                    f"Batched UniSteer pixels must be NCHW or NHWC, got {list(pixels_t.shape)}"
                )
        elif pixels_t.ndim == 5 and int(pixels_t.shape[-1]) == 1:
            pixels_t = pixels_t.squeeze(-1)
            if (
                int(pixels_t.shape[1]) <= 16
                and int(pixels_t.shape[2]) > 16
                and int(pixels_t.shape[3]) > 16
            ):
                pass
            elif (
                int(pixels_t.shape[-1]) <= 16
                and int(pixels_t.shape[1]) > 16
                and int(pixels_t.shape[2]) > 16
            ):
                pixels_t = pixels_t.permute(0, 3, 1, 2)
            else:
                raise ValueError(
                    f"Batched UniSteer pixels must be NCHW or NHWC after squeeze, got {list(pixels_t.shape)}"
                )
        else:
            raise ValueError(
                f"Batched UniSteer pixels must have rank 4 or 5, got {list(pixels_t.shape)}"
            )
        pixels_t = pixels_t.to(device=device, dtype=torch.uint8).contiguous()
    else:
        pixels = _to_numpy(pixels_value, dtype=np.uint8)
        if pixels.ndim == 4:
            pixels = pixels[None, ...]
        elif pixels.ndim != 5:
            raise ValueError(
                f"Batched UniSteer pixels must have rank 4 or 5, got {list(pixels.shape)}"
            )
        pixels = np.ascontiguousarray(pixels.squeeze(-1))
        pixels_t = torch.from_numpy(np.transpose(pixels, (0, 3, 1, 2))).to(device=device)

    state_value = observation["state"]
    if isinstance(state_value, torch.Tensor):
        state_t = state_value
        if state_t.ndim == 1:
            state_t = state_t.unsqueeze(0)
        elif state_t.ndim == 2:
            pass
        elif state_t.ndim == 3 and int(state_t.shape[-1]) == 1:
            state_t = state_t.squeeze(-1)
        else:
            raise ValueError(
                f"Batched UniSteer state must have rank 2 or 3, got {list(state_t.shape)}"
            )
        state_t = state_t.to(device=device, dtype=torch.float32).contiguous()
    else:
        state = _to_numpy(state_value, dtype=np.float32)
        if state.ndim == 2:
            state = state[None, ...]
        elif state.ndim != 3:
            raise ValueError(
                f"Batched UniSteer state must have rank 2 or 3, got {list(state.shape)}"
            )
        state_t = torch.from_numpy(np.ascontiguousarray(state.squeeze(-1))).to(
            device=device, dtype=torch.float32
        )

    return {"pixels": pixels_t, "state": state_t}


def _batched_random_crop(pixels: torch.Tensor, padding: int) -> torch.Tensor:
    if padding <= 0:
        return pixels
    if pixels.ndim != 4:
        raise ValueError(f"Expected NCHW pixels for random crop, got shape {list(pixels.shape)}")

    batch, _, height, width = pixels.shape
    padded = F.pad(pixels, (padding, padding, padding, padding), mode="replicate")
    y0 = torch.randint(0, 2 * padding + 1, (batch,), device=pixels.device)
    x0 = torch.randint(0, 2 * padding + 1, (batch,), device=pixels.device)
    y_idx = y0[:, None] + torch.arange(height, device=pixels.device)[None, :]
    x_idx = x0[:, None] + torch.arange(width, device=pixels.device)[None, :]
    batch_idx = torch.arange(batch, device=pixels.device)[:, None, None]
    padded_nhwc = padded.permute(0, 2, 3, 1)
    cropped = padded_nhwc[batch_idx, y_idx[:, :, None], x_idx[:, None, :], :]
    return cropped.permute(0, 3, 1, 2).contiguous()


def _sample_batched_color_transform_params(
    batch_size: int,
    device: torch.device,
    *,
    brightness: float = 0.2,
    contrast: float = 0.1,
    saturation: float = 0.1,
    hue: float = 0.03,
    color_jitter_prob: float = 0.8,
    to_grayscale_prob: float = 0.0,
    apply_prob: float = 1.0,
) -> Dict[str, torch.Tensor]:
    return {
        "should_apply": torch.rand(batch_size, device=device) <= apply_prob,
        "should_apply_color": torch.rand(batch_size, device=device) <= color_jitter_prob,
        "should_apply_grayscale": torch.rand(batch_size, device=device) <= to_grayscale_prob,
        "order": torch.argsort(torch.rand(batch_size, 4, device=device), dim=-1),
        "brightness_delta": torch.empty(batch_size, device=device).uniform_(
            -brightness, brightness
        ),
        "contrast_factor": torch.empty(batch_size, device=device).uniform_(
            1.0 - contrast, 1.0 + contrast
        ),
        "saturation_factor": torch.empty(batch_size, device=device).uniform_(
            1.0 - saturation, 1.0 + saturation
        ),
        "hue_delta": torch.empty(batch_size, device=device).uniform_(-hue, hue),
    }


def _rgb_to_hsv_image(image: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    r = image.select(dim=-3, index=0)
    g = image.select(dim=-3, index=1)
    b = image.select(dim=-3, index=2)
    vv = torch.maximum(torch.maximum(r, g), b)
    min_rgb = torch.minimum(torch.minimum(r, g), b)
    range_ = vv - min_rgb
    sat = torch.where(vv > 0, range_ / vv, torch.zeros_like(vv))
    norm = torch.where(range_ != 0, 1.0 / (6.0 * range_), torch.full_like(range_, 1e9))

    hr = norm * (g - b)
    hg = norm * (b - r) + (2.0 / 6.0)
    hb = norm * (r - g) + (4.0 / 6.0)

    hue = torch.where(r == vv, hr, torch.where(g == vv, hg, hb))
    hue = hue * (range_ > 0).to(dtype=image.dtype)
    hue = hue + (hue < 0).to(dtype=image.dtype)
    return hue, sat, vv


def _hsv_to_rgb_image(h: torch.Tensor, s: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    c = s * v
    m = v - c
    dh = torch.remainder(h, 1.0) * 6.0
    fmodu = torch.remainder(dh, 2.0)
    x = c * (1.0 - torch.abs(fmodu - 1.0))
    hcat = torch.floor(dh).to(dtype=torch.int64)

    rr = (
        torch.where(
            (hcat == 0) | (hcat == 5),
            c,
            torch.where((hcat == 1) | (hcat == 4), x, torch.zeros_like(c)),
        )
        + m
    )
    gg = (
        torch.where(
            (hcat == 1) | (hcat == 2),
            c,
            torch.where((hcat == 0) | (hcat == 3), x, torch.zeros_like(c)),
        )
        + m
    )
    bb = (
        torch.where(
            (hcat == 3) | (hcat == 4),
            c,
            torch.where((hcat == 2) | (hcat == 5), x, torch.zeros_like(c)),
        )
        + m
    )
    return torch.stack([rr, gg, bb], dim=-3)


def _adjust_saturation_image(image: torch.Tensor, factor: torch.Tensor | float) -> torch.Tensor:
    h, s, v = _rgb_to_hsv_image(image)
    s = torch.clamp(s * factor, 0.0, 1.0)
    return _hsv_to_rgb_image(h, s, v)


def _adjust_hue_image(image: torch.Tensor, delta: torch.Tensor | float) -> torch.Tensor:
    h, s, v = _rgb_to_hsv_image(image)
    h = torch.remainder(h + delta, 1.0)
    return _hsv_to_rgb_image(h, s, v)


def _to_grayscale_image(image: torch.Tensor) -> torch.Tensor:
    weights = torch.tensor([0.2989, 0.5870, 0.1140], device=image.device, dtype=image.dtype)
    view_shape = [1] * image.ndim
    view_shape[-3] = 3
    weights = weights.view(*view_shape)
    grayscale = (image * weights).sum(dim=-3, keepdim=True)
    repeat_shape = [1] * image.ndim
    repeat_shape[-3] = 3
    return grayscale.repeat(*repeat_shape)


def _apply_grouped_color_ops(
    images: torch.Tensor,
    batch_indices: torch.Tensor,
    params: Mapping[str, torch.Tensor],
    order: torch.Tensor,
) -> torch.Tensor:
    transformed = images
    for op in order.tolist():
        if op == 0:
            delta = params["brightness_delta"][batch_indices].view(-1, 1, 1, 1, 1)
            transformed = torch.clamp(transformed + delta, 0.0, 1.0)
        elif op == 1:
            mean = transformed.mean(dim=(-2, -1), keepdim=True)
            factor = params["contrast_factor"][batch_indices].view(-1, 1, 1, 1, 1)
            transformed = torch.clamp(factor * (transformed - mean) + mean, 0.0, 1.0)
        elif op == 2:
            factor = params["saturation_factor"][batch_indices].view(-1, 1, 1, 1)
            transformed = torch.clamp(_adjust_saturation_image(transformed, factor), 0.0, 1.0)
        elif op == 3:
            delta = params["hue_delta"][batch_indices].view(-1, 1, 1, 1)
            transformed = torch.clamp(_adjust_hue_image(transformed, delta), 0.0, 1.0)
        else:
            raise ValueError(f"Unsupported color transform op={op}")
    return transformed


def _batched_color_transform(
    pixels: torch.Tensor, *, num_cameras: int, enabled: bool
) -> torch.Tensor:
    if not enabled:
        return pixels
    if pixels.ndim != 4:
        raise ValueError(
            f"Expected NCHW pixels for color transform, got shape {list(pixels.shape)}"
        )

    batch, channels, height, width = pixels.shape
    if channels != 3 * num_cameras:
        raise ValueError(
            f"Expected channels == 3 * num_cameras, got channels={channels} num_cameras={num_cameras}"
        )

    out = pixels.clone()
    if out.dtype == torch.uint8:
        work = out.to(dtype=torch.float32) / 255.0
    else:
        work = out.to(dtype=torch.float32)
        if work.max().item() > 1.0:
            work = work / 255.0

    work = work.view(batch, num_cameras, 3, height, width)
    params = _sample_batched_color_transform_params(batch, out.device)

    should_apply = params["should_apply"]
    should_apply_color = should_apply & params["should_apply_color"]
    if bool(should_apply_color.any().item()):
        batch_indices = torch.nonzero(should_apply_color, as_tuple=False).flatten()
        orders = params["order"][batch_indices]
        unique_orders, inverse = torch.unique(orders, dim=0, return_inverse=True)
        for group_idx in range(unique_orders.shape[0]):
            group_batch_indices = batch_indices[inverse == group_idx]
            work[group_batch_indices] = _apply_grouped_color_ops(
                work[group_batch_indices], group_batch_indices, params, unique_orders[group_idx]
            )

    should_apply_grayscale = should_apply & params["should_apply_grayscale"]
    if bool(should_apply_grayscale.any().item()):
        batch_indices = torch.nonzero(should_apply_grayscale, as_tuple=False).flatten()
        work[batch_indices] = _to_grayscale_image(work[batch_indices])

    quantized = torch.clamp(torch.round(work * 255.0), 0.0, 255.0)
    return quantized.view(batch, channels, height, width).to(dtype=out.dtype)


@dataclass
class RLConfig:
    device: str = "cuda"
    state_dim: Optional[int] = None
    noise_action_dim: Optional[int] = None
    pixel_height: Optional[int] = None
    pixel_width: Optional[int] = None
    pixel_channels: Optional[int] = None

    actor_hidden_dims: Tuple[int, ...] = (1024, 1024, 1024)
    critic_hidden_dims: Tuple[int, ...] = (1024, 1024, 1024)
    cnn_features: Tuple[int, ...] = (32, 32, 32, 32)
    cnn_strides: Tuple[int, ...] = (3, 2, 2, 2)
    cnn_padding: str = "VALID"
    latent_dim: int = 50
    critic_reduction: str = "min"
    dropout_rate: float = 0.0
    use_bottleneck: bool = True
    encoder_type: str = "small"
    color_jitter: bool = True
    aug_next: bool = True
    augmentation_padding: int = 4

    actor_lr: float = 1e-4
    actor_sft_lr: float = 5e-5
    critic_lr: float = 3e-4
    alpha_lr: float = 3e-4

    discount: float = 0.99
    tau: float = 0.005
    batch_size: int = 256
    replay_capacity: int = 50_000
    updates_per_step: int = 1

    target_entropy: Optional[float] = None
    learnable_temperature: bool = True
    init_temperature: float = 1.0

    noise_action_limit: float = 2.5
    log_std_min: float = -20.0
    log_std_max: float = 2.0
    actor_grad_clip_norm: Optional[float] = None
    critic_grad_clip_norm: Optional[float] = None

    save_buffer_in_checkpoint: bool = False

    @classmethod
    def from_cfg(cls, cfg: Any) -> "RLConfig":
        unisteer = _cfg_get(cfg, "unisteer", cfg)
        vision_cfg = _cfg_get(_cfg_get(cfg, "vision", None), "config", None)
        mixture_cfg = _cfg_get(cfg, "mixture", None)
        vlm_cfg = _cfg_get(mixture_cfg, "vlm", None)

        image_size = _cfg_get(unisteer, "pixel_height", None)
        if image_size is None:
            image_size = _cfg_get(vision_cfg, "image_size", None)

        state_dim = _cfg_get(unisteer, "state_dim", None)
        if state_dim is None:
            proprio_dim = int(_cfg_get(cfg, "proprio_dim", 7))
            prefix_dim = int(_cfg_get(vlm_cfg, "hidden_size", 2048))
            state_dim = proprio_dim + prefix_dim

        noise_action_dim = _cfg_get(unisteer, "noise_action_dim", None)
        if has_explicit_openpi_policy_type(cfg):
            noise_action_dim = resolve_openpi_noise_layout(cfg).actor_noise_dim
        elif noise_action_dim is None:
            noise_action_dim = int(_cfg_get(cfg, "horizon_steps", 16)) * int(
                _cfg_get(cfg, "action_dim", 7)
            )

        pixel_channels = _cfg_get(unisteer, "pixel_channels", None)
        if pixel_channels is None:
            num_cameras = 2 if bool(_cfg_get(cfg, "use_wrist", False)) else 1
            pixel_channels = 3 * num_cameras

        actor_hidden = tuple(
            int(v) for v in _cfg_get(unisteer, "actor_hidden_dims", (1024, 1024, 1024))
        )
        critic_hidden = tuple(
            int(v) for v in _cfg_get(unisteer, "critic_hidden_dims", (1024, 1024, 1024))
        )
        cnn_features = tuple(int(v) for v in _cfg_get(unisteer, "cnn_features", (32, 32, 32, 32)))
        cnn_strides = tuple(int(v) for v in _cfg_get(unisteer, "cnn_strides", (3, 2, 2, 2)))

        target_entropy = _cfg_get(unisteer, "target_entropy", None)
        if target_entropy is not None:
            target_entropy = float(target_entropy)

        return cls(
            device=str(_cfg_get(unisteer, "device", _cfg_get(cfg, "device", "cuda"))),
            state_dim=int(state_dim) if state_dim is not None else None,
            noise_action_dim=int(noise_action_dim) if noise_action_dim is not None else None,
            pixel_height=int(image_size) if image_size is not None else None,
            pixel_width=int(_cfg_get(unisteer, "pixel_width", image_size))
            if image_size is not None
            else None,
            pixel_channels=int(pixel_channels) if pixel_channels is not None else None,
            actor_hidden_dims=actor_hidden,
            critic_hidden_dims=critic_hidden,
            cnn_features=cnn_features,
            cnn_strides=cnn_strides,
            cnn_padding=str(_cfg_get(unisteer, "cnn_padding", "VALID")),
            latent_dim=int(_cfg_get(unisteer, "latent_dim", 50)),
            critic_reduction=str(_cfg_get(unisteer, "critic_reduction", "min")),
            dropout_rate=float(_cfg_get(unisteer, "dropout_rate", 0.0)),
            use_bottleneck=bool(_cfg_get(unisteer, "use_bottleneck", True)),
            encoder_type=str(_cfg_get(unisteer, "encoder_type", "small")),
            color_jitter=bool(_cfg_get(unisteer, "color_jitter", True)),
            aug_next=bool(_cfg_get(unisteer, "aug_next", True)),
            augmentation_padding=int(_cfg_get(unisteer, "augmentation_padding", 4)),
            actor_lr=float(_cfg_get(unisteer, "actor_lr", 1e-4)),
            actor_sft_lr=float(
                _cfg_get(unisteer, "actor_sft_lr", _cfg_get(unisteer, "actor_lr", 1e-4))
            ),
            critic_lr=float(_cfg_get(unisteer, "critic_lr", 3e-4)),
            alpha_lr=float(_cfg_get(unisteer, "alpha_lr", 3e-4)),
            discount=float(_cfg_get(unisteer, "discount", 0.99)),
            tau=float(_cfg_get(unisteer, "tau", 0.005)),
            batch_size=int(_cfg_get(unisteer, "batch_size", 256)),
            replay_capacity=int(_cfg_get(unisteer, "replay_capacity", 50_000)),
            updates_per_step=int(_cfg_get(unisteer, "updates_per_step", 1)),
            target_entropy=target_entropy,
            learnable_temperature=bool(_cfg_get(unisteer, "learnable_temperature", True)),
            init_temperature=float(_cfg_get(unisteer, "init_temperature", 1.0)),
            noise_action_limit=float(_cfg_get(unisteer, "noise_action_limit", 2.5)),
            log_std_min=float(_cfg_get(unisteer, "log_std_min", -20.0)),
            log_std_max=float(_cfg_get(unisteer, "log_std_max", 2.0)),
            actor_grad_clip_norm=_cfg_get(unisteer, "actor_grad_clip_norm", None),
            critic_grad_clip_norm=_cfg_get(unisteer, "critic_grad_clip_norm", None),
            save_buffer_in_checkpoint=bool(_cfg_get(unisteer, "save_buffer_in_checkpoint", False)),
        )


class ReplayBuffer:
    """Thread-safe replay buffer for `obs_dict={"pixels","state"}` observations."""

    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        if self.capacity <= 0:
            raise ValueError(f"ReplayBuffer capacity must be positive, got {self.capacity}")
        self.size = 0
        self.ptr = 0
        self.lock = threading.Lock()

        self.obs_pixels: Optional[np.ndarray] = None
        self.obs_state: Optional[np.ndarray] = None
        self.next_obs_pixels: Optional[np.ndarray] = None
        self.next_obs_state: Optional[np.ndarray] = None
        self.actions: Optional[np.ndarray] = None
        self.rewards: Optional[np.ndarray] = None
        self.masks: Optional[np.ndarray] = None
        self.discounts: Optional[np.ndarray] = None

    def _maybe_init(
        self,
        observation: Mapping[str, Any],
        next_observation: Mapping[str, Any],
        action: np.ndarray,
    ) -> None:
        if self.obs_pixels is not None:
            return

        obs = normalize_unisteer_observation(observation)
        next_obs = normalize_unisteer_observation(next_observation)
        if obs["pixels"].shape != next_obs["pixels"].shape:
            raise ValueError(
                f"Observation pixel shape mismatch: {obs['pixels'].shape} vs {next_obs['pixels'].shape}"
            )
        if obs["state"].shape != next_obs["state"].shape:
            raise ValueError(
                f"Observation state shape mismatch: {obs['state'].shape} vs {next_obs['state'].shape}"
            )

        self.obs_pixels = np.empty((self.capacity, *obs["pixels"].shape), dtype=np.uint8)
        self.obs_state = np.empty((self.capacity, *obs["state"].shape), dtype=np.float32)
        self.next_obs_pixels = np.empty((self.capacity, *next_obs["pixels"].shape), dtype=np.uint8)
        self.next_obs_state = np.empty((self.capacity, *next_obs["state"].shape), dtype=np.float32)
        self.actions = np.empty((self.capacity, action.size), dtype=np.float32)
        self.rewards = np.empty((self.capacity, 1), dtype=np.float32)
        self.masks = np.empty((self.capacity, 1), dtype=np.float32)
        self.discounts = np.empty((self.capacity, 1), dtype=np.float32)

    def add(
        self,
        *,
        observation: Mapping[str, Any],
        next_observation: Mapping[str, Any],
        action: Any,
        reward: float,
        mask: float,
        discount: float,
    ) -> None:
        obs = normalize_unisteer_observation(observation)
        next_obs = normalize_unisteer_observation(next_observation)
        action_np = _to_numpy(action, dtype=np.float32).reshape(-1)
        if action_np.size == 0:
            raise ValueError("noise action must not be empty")

        with self.lock:
            self._maybe_init(obs, next_obs, action_np)
            assert self.obs_pixels is not None
            assert self.obs_state is not None
            assert self.next_obs_pixels is not None
            assert self.next_obs_state is not None
            assert self.actions is not None
            assert self.rewards is not None
            assert self.masks is not None
            assert self.discounts is not None

            idx = self.ptr
            self.obs_pixels[idx] = obs["pixels"]
            self.obs_state[idx] = obs["state"]
            self.next_obs_pixels[idx] = next_obs["pixels"]
            self.next_obs_state[idx] = next_obs["state"]
            self.actions[idx] = action_np
            self.rewards[idx, 0] = float(reward)
            self.masks[idx, 0] = float(mask)
            self.discounts[idx, 0] = float(discount)

            self.ptr = (self.ptr + 1) % self.capacity
            self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int) -> Dict[str, Any]:
        with self.lock:
            if self.size == 0:
                raise RuntimeError("ReplayBuffer is empty")
            assert self.obs_pixels is not None
            assert self.obs_state is not None
            assert self.next_obs_pixels is not None
            assert self.next_obs_state is not None
            assert self.actions is not None
            assert self.rewards is not None
            assert self.masks is not None
            assert self.discounts is not None

            batch_size = int(batch_size)
            if batch_size <= 0:
                raise ValueError(f"batch_size must be positive, got {batch_size}")
            # Always sample `batch_size`, using replacement while the buffer is small.
            # transitions with replacement, even when the online buffer is still small.
            indices = np.random.randint(0, self.size, size=batch_size)
            return {
                "observations": {
                    "pixels": self.obs_pixels[indices],
                    "state": self.obs_state[indices],
                },
                "next_observations": {
                    "pixels": self.next_obs_pixels[indices],
                    "state": self.next_obs_state[indices],
                },
                "actions": self.actions[indices],
                "rewards": self.rewards[indices],
                "masks": self.masks[indices],
                "discounts": self.discounts[indices],
            }

    def state_dict(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "capacity": self.capacity,
                "size": self.size,
                "ptr": self.ptr,
                "obs_pixels": self.obs_pixels,
                "obs_state": self.obs_state,
                "next_obs_pixels": self.next_obs_pixels,
                "next_obs_state": self.next_obs_state,
                "actions": self.actions,
                "rewards": self.rewards,
                "masks": self.masks,
                "discounts": self.discounts,
            }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        with self.lock:
            source_capacity = int(state["capacity"])
            source_size = min(int(state["size"]), source_capacity)
            source_ptr = int(state["ptr"]) % source_capacity
            source_arrays = {
                "obs_pixels": state.get("obs_pixels"),
                "obs_state": state.get("obs_state"),
                "next_obs_pixels": state.get("next_obs_pixels"),
                "next_obs_state": state.get("next_obs_state"),
                "actions": state.get("actions"),
                "rewards": state.get("rewards"),
                "masks": state.get("masks"),
                "discounts": state.get("discounts"),
            }
            if source_size == 0:
                self.size = 0
                self.ptr = 0
                for name in source_arrays:
                    setattr(self, name, None)
                return

            if any(array is None for array in source_arrays.values()):
                raise ValueError("Replay checkpoint with non-zero size is missing array data")
            if source_size < source_capacity:
                chronological = np.arange(source_size, dtype=np.int64)
            else:
                chronological = np.concatenate(
                    [
                        np.arange(source_ptr, source_capacity, dtype=np.int64),
                        np.arange(0, source_ptr, dtype=np.int64),
                    ]
                )
            retained = chronological[-self.capacity :]
            retained_size = int(retained.size)
            for name, source in source_arrays.items():
                assert source is not None
                target = np.empty((self.capacity, *source.shape[1:]), dtype=source.dtype)
                target[:retained_size] = source[retained]
                setattr(self, name, target)
            self.size = retained_size
            self.ptr = retained_size % self.capacity


def _init_linear(linear: nn.Linear, gain: float = np.sqrt(2.0)) -> None:
    nn.init.orthogonal_(linear.weight, gain=gain)
    if linear.bias is not None:
        nn.init.zeros_(linear.bias)


def _init_xavier_linear(linear: nn.Linear) -> None:
    nn.init.xavier_normal_(linear.weight)
    if linear.bias is not None:
        nn.init.zeros_(linear.bias)


def _init_conv(conv: nn.Conv2d, gain: float = np.sqrt(2.0)) -> None:
    nn.init.orthogonal_(conv.weight, gain=gain)
    if conv.bias is not None:
        nn.init.zeros_(conv.bias)


class FeedForwardMLP(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_dims: Sequence[int],
        *,
        activate_final: bool = False,
        dropout_rate: Optional[float] = None,
        use_layer_norm: bool = False,
    ):
        super().__init__()
        dims = [int(input_dim), *[int(v) for v in hidden_dims]]
        self.layers = nn.ModuleList()
        self.norms = nn.ModuleList()
        self.dropout_rate = None if not dropout_rate or dropout_rate <= 0 else float(dropout_rate)
        self.use_layer_norm = bool(use_layer_norm)
        self.activate_final = bool(activate_final)

        for idx, (in_dim, out_dim) in enumerate(zip(dims[:-1], dims[1:])):
            linear = nn.Linear(in_dim, out_dim)
            _init_linear(linear)
            self.layers.append(linear)
            if idx + 1 < len(dims) - 1 or self.activate_final:
                self.norms.append(nn.LayerNorm(out_dim) if self.use_layer_norm else nn.Identity())

    def forward(self, x: torch.Tensor, *, training: bool = False) -> torch.Tensor:
        norm_idx = 0
        for idx, linear in enumerate(self.layers):
            x = linear(x)
            if idx + 1 < len(self.layers) or self.activate_final:
                if self.dropout_rate is not None:
                    x = F.dropout(x, p=self.dropout_rate, training=training)
                x = self.norms[norm_idx](x)
                norm_idx += 1
                x = F.relu(x, inplace=False)
        return x


class SmallEncoder(nn.Module):
    def __init__(
        self,
        *,
        pixel_height: int,
        pixel_width: int,
        pixel_channels: int,
        cnn_features: Sequence[int],
        cnn_strides: Sequence[int],
        cnn_padding: str,
    ):
        super().__init__()
        if str(cnn_padding).upper() != "VALID":
            raise ValueError(
                f"Only official small encoder padding='VALID' is supported, got {cnn_padding}"
            )

        in_channels = int(pixel_channels)
        convs = []
        for out_channels, stride in zip(cnn_features, cnn_strides):
            conv = nn.Conv2d(
                in_channels, int(out_channels), kernel_size=3, stride=int(stride), padding=0
            )
            _init_conv(conv)
            convs.extend([conv, nn.ReLU(inplace=True)])
            in_channels = int(out_channels)
        self.conv = nn.Sequential(*convs)

        with torch.no_grad():
            dummy = torch.zeros(
                1, int(pixel_channels), int(pixel_height), int(pixel_width), dtype=torch.float32
            )
            self.output_dim = int(self.conv(dummy).flatten(start_dim=1).shape[1])

    def forward(self, pixels: torch.Tensor) -> torch.Tensor:
        x = pixels.to(dtype=torch.float32)
        if x.max().item() > 1.0:
            x = x / 255.0
        x = self.conv(x)
        return x.flatten(start_dim=1)


class PixelMultiplexer(nn.Module):
    def __init__(
        self, *, encoder: SmallEncoder, state_dim: int, latent_dim: int, use_bottleneck: bool
    ):
        super().__init__()
        self.encoder = encoder
        self.state_dim = int(state_dim)
        self.use_bottleneck = bool(use_bottleneck)
        if self.use_bottleneck:
            self.bottleneck = nn.Linear(self.encoder.output_dim, int(latent_dim))
            _init_xavier_linear(self.bottleneck)
            self.bottleneck_norm = nn.LayerNorm(int(latent_dim))
            self.pixel_latent_dim = int(latent_dim)
        else:
            self.bottleneck = None
            self.bottleneck_norm = None
            self.pixel_latent_dim = int(self.encoder.output_dim)

    @property
    def observation_dim(self) -> int:
        return int(self.pixel_latent_dim + self.state_dim)

    def encode_observation(
        self, observation: Mapping[str, torch.Tensor]
    ) -> Dict[str, torch.Tensor]:
        pixel_latent = self.encoder(observation["pixels"])
        if self.use_bottleneck:
            assert self.bottleneck is not None and self.bottleneck_norm is not None
            pixel_latent = torch.tanh(self.bottleneck_norm(self.bottleneck(pixel_latent)))
        state = observation["state"].reshape(observation["state"].shape[0], -1)
        return {"pixels": pixel_latent, "state": state}

    def flatten_observation(self, observation: Mapping[str, torch.Tensor]) -> torch.Tensor:
        encoded = self.encode_observation(observation)
        return torch.cat([encoded["pixels"], encoded["state"]], dim=-1)


class LearnedStdNormalPolicy(nn.Module):
    def __init__(
        self,
        *,
        input_dim: int,
        hidden_dims: Sequence[int],
        action_dim: int,
        dropout_rate: Optional[float],
        log_std_min: float,
        log_std_max: float,
        action_limit: float,
    ):
        super().__init__()
        self.backbone = FeedForwardMLP(
            int(input_dim),
            tuple(int(v) for v in hidden_dims),
            activate_final=True,
            dropout_rate=dropout_rate,
            use_layer_norm=False,
        )
        last_dim = int(hidden_dims[-1])
        self.mean_head = nn.Linear(last_dim, int(action_dim))
        self.log_std_head = nn.Linear(last_dim, int(action_dim))
        _init_linear(self.mean_head, gain=1e-2)
        _init_linear(self.log_std_head, gain=1e-2)
        self.log_std_min = float(log_std_min)
        self.log_std_max = float(log_std_max)
        self.action_limit = float(action_limit)

    def forward(self, flat_observation: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        features = self.backbone(flat_observation, training=self.training)
        mean = self.mean_head(features)
        log_std = torch.clamp(self.log_std_head(features), self.log_std_min, self.log_std_max)
        return mean, log_std


class TanhGaussianActor(nn.Module):
    def __init__(
        self,
        *,
        pixel_height: int,
        pixel_width: int,
        pixel_channels: int,
        state_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int],
        action_limit: float,
        log_std_min: float,
        log_std_max: float,
        cnn_features: Sequence[int],
        cnn_strides: Sequence[int],
        cnn_padding: str,
        latent_dim: int,
        dropout_rate: Optional[float],
        use_bottleneck: bool,
        encoder_type: str,
    ):
        super().__init__()
        if str(encoder_type) != "small":
            raise ValueError(
                f"Only official real-world encoder_type='small' is supported, got {encoder_type}"
            )
        encoder = SmallEncoder(
            pixel_height=int(pixel_height),
            pixel_width=int(pixel_width),
            pixel_channels=int(pixel_channels),
            cnn_features=cnn_features,
            cnn_strides=cnn_strides,
            cnn_padding=cnn_padding,
        )
        self.multiplexer = PixelMultiplexer(
            encoder=encoder,
            state_dim=int(state_dim),
            latent_dim=int(latent_dim),
            use_bottleneck=bool(use_bottleneck),
        )
        self.policy = LearnedStdNormalPolicy(
            input_dim=self.multiplexer.observation_dim,
            hidden_dims=hidden_dims,
            action_dim=int(action_dim),
            dropout_rate=dropout_rate,
            log_std_min=log_std_min,
            log_std_max=log_std_max,
            action_limit=action_limit,
        )
        self.action_limit = float(action_limit)

    def forward(self, observation: Mapping[str, torch.Tensor]) -> Tuple[torch.Tensor, torch.Tensor]:
        flat_observation = self.multiplexer.flatten_observation(observation)
        return self.policy(flat_observation)

    def sample(
        self, observation: Mapping[str, torch.Tensor], deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mean, log_std = self.forward(observation)
        std = log_std.exp()
        normal = torch.distributions.Normal(mean, std)
        pre_tanh = mean if deterministic else normal.rsample()
        action = torch.tanh(pre_tanh) * self.action_limit

        if deterministic:
            log_prob = torch.zeros((mean.shape[0], 1), device=mean.device, dtype=mean.dtype)
        else:
            raw_log_prob = normal.log_prob(pre_tanh).sum(dim=-1, keepdim=True)
            correction = torch.log(1 - torch.tanh(pre_tanh).pow(2) + 1e-6).sum(dim=-1, keepdim=True)
            log_prob = raw_log_prob - correction

        mean_action = torch.tanh(mean) * self.action_limit
        return action, log_prob, mean_action

    def evaluate_actions(
        self,
        observation: Mapping[str, torch.Tensor],
        actions: torch.Tensor,
        *,
        average_entropy: bool = False,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        if actions.ndim != 2:
            raise ValueError(f"actions must have shape [B, A], got {list(actions.shape)}")

        mean, log_std = self.forward(observation)
        if actions.shape != mean.shape:
            raise ValueError(
                f"action shape mismatch: actions={list(actions.shape)} policy={list(mean.shape)}"
            )

        scaled_actions = torch.clamp(
            actions / float(self.action_limit), min=-1.0 + 1e-6, max=1.0 - 1e-6
        )
        pre_tanh = torch.atanh(scaled_actions)
        normal = torch.distributions.Normal(mean, log_std.exp())
        log_prob = normal.log_prob(pre_tanh) - torch.log(1.0 - scaled_actions.pow(2) + 1e-6)
        log_prob = log_prob.sum(dim=-1) / float(actions.shape[-1])

        entropy = normal.entropy().sum(dim=-1)
        if average_entropy:
            entropy = entropy / float(actions.shape[-1])
        return log_prob.float(), entropy.float()


class StateActionValue(nn.Module):
    def __init__(self, *, observation_dim: int, action_dim: int, hidden_dims: Sequence[int]):
        super().__init__()
        self.net = FeedForwardMLP(
            int(observation_dim + action_dim),
            tuple(int(v) for v in (*hidden_dims, 1)),
            activate_final=False,
            dropout_rate=None,
            use_layer_norm=True,
        )

    def forward(self, flat_observation: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        x = torch.cat([action, flat_observation], dim=-1)
        return self.net(x, training=self.training).squeeze(-1)


class TwinCritic(nn.Module):
    def __init__(
        self,
        *,
        pixel_height: int,
        pixel_width: int,
        pixel_channels: int,
        state_dim: int,
        action_dim: int,
        hidden_dims: Sequence[int],
        cnn_features: Sequence[int],
        cnn_strides: Sequence[int],
        cnn_padding: str,
        latent_dim: int,
        use_bottleneck: bool,
        encoder_type: str,
    ):
        super().__init__()
        if str(encoder_type) != "small":
            raise ValueError(
                f"Only official real-world encoder_type='small' is supported, got {encoder_type}"
            )
        encoder = SmallEncoder(
            pixel_height=int(pixel_height),
            pixel_width=int(pixel_width),
            pixel_channels=int(pixel_channels),
            cnn_features=cnn_features,
            cnn_strides=cnn_strides,
            cnn_padding=cnn_padding,
        )
        self.multiplexer = PixelMultiplexer(
            encoder=encoder,
            state_dim=int(state_dim),
            latent_dim=int(latent_dim),
            use_bottleneck=bool(use_bottleneck),
        )
        obs_dim = self.multiplexer.observation_dim
        self.q1 = StateActionValue(
            observation_dim=obs_dim, action_dim=int(action_dim), hidden_dims=hidden_dims
        )
        self.q2 = StateActionValue(
            observation_dim=obs_dim, action_dim=int(action_dim), hidden_dims=hidden_dims
        )

    def forward(
        self, observation: Mapping[str, torch.Tensor], action: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        flat_observation = self.multiplexer.flatten_observation(observation)
        return self.q1(flat_observation, action).unsqueeze(-1), self.q2(
            flat_observation, action
        ).unsqueeze(-1)


class RLTrainer:
    """Observation-dict Pixel-SAC trainer for UniSteer latent-noise RL."""

    def __init__(self, cfg: Any):
        self.cfg = RLConfig.from_cfg(cfg)
        self.device = torch.device(self.cfg.device)
        self.replay_buffer = ReplayBuffer(self.cfg.replay_capacity)

        self.state_dim = self.cfg.state_dim
        self.noise_action_dim = self.cfg.noise_action_dim
        self.pixel_shape = None

        self.actor: Optional[TanhGaussianActor] = None
        self.critic: Optional[TwinCritic] = None
        self.target_critic: Optional[TwinCritic] = None

        self.actor_opt: Optional[torch.optim.Optimizer] = None
        self.actor_sft_opt: Optional[torch.optim.Optimizer] = None
        self.critic_opt: Optional[torch.optim.Optimizer] = None
        init_log_alpha = np.log(max(self.cfg.init_temperature, 1e-6))
        self.log_alpha = torch.tensor(
            init_log_alpha, device=self.device, dtype=torch.float32, requires_grad=True
        )
        self.alpha_opt: Optional[torch.optim.Optimizer] = None

        self.update_step = 0
        self.actor_sft_step = 0

        if None not in (
            self.cfg.state_dim,
            self.cfg.noise_action_dim,
            self.cfg.pixel_height,
            self.cfg.pixel_width,
            self.cfg.pixel_channels,
        ):
            self._build_networks(
                state_dim=int(self.cfg.state_dim),
                noise_action_dim=int(self.cfg.noise_action_dim),
                pixel_shape=(
                    int(self.cfg.pixel_height),
                    int(self.cfg.pixel_width),
                    int(self.cfg.pixel_channels),
                    1,
                ),
            )

    @property
    def alpha(self) -> torch.Tensor:
        return self.log_alpha.exp()

    @property
    def actor_update_step(self) -> int:
        return int(self.update_step + self.actor_sft_step)

    def _build_networks(
        self, *, state_dim: int, noise_action_dim: int, pixel_shape: Tuple[int, int, int, int]
    ) -> None:
        if self.actor is not None:
            return

        self.state_dim = int(state_dim)
        self.noise_action_dim = int(noise_action_dim)
        self.pixel_shape = tuple(int(v) for v in pixel_shape)
        pixel_height = int(self.pixel_shape[0])
        pixel_width = int(self.pixel_shape[1])
        pixel_channels = int(self.pixel_shape[2])

        self.actor = TanhGaussianActor(
            pixel_height=pixel_height,
            pixel_width=pixel_width,
            pixel_channels=pixel_channels,
            state_dim=self.state_dim,
            action_dim=self.noise_action_dim,
            hidden_dims=self.cfg.actor_hidden_dims,
            action_limit=self.cfg.noise_action_limit,
            log_std_min=self.cfg.log_std_min,
            log_std_max=self.cfg.log_std_max,
            cnn_features=self.cfg.cnn_features,
            cnn_strides=self.cfg.cnn_strides,
            cnn_padding=self.cfg.cnn_padding,
            latent_dim=self.cfg.latent_dim,
            dropout_rate=self.cfg.dropout_rate,
            use_bottleneck=self.cfg.use_bottleneck,
            encoder_type=self.cfg.encoder_type,
        ).to(self.device)

        self.critic = TwinCritic(
            pixel_height=pixel_height,
            pixel_width=pixel_width,
            pixel_channels=pixel_channels,
            state_dim=self.state_dim,
            action_dim=self.noise_action_dim,
            hidden_dims=self.cfg.critic_hidden_dims,
            cnn_features=self.cfg.cnn_features,
            cnn_strides=self.cfg.cnn_strides,
            cnn_padding=self.cfg.cnn_padding,
            latent_dim=self.cfg.latent_dim,
            use_bottleneck=self.cfg.use_bottleneck,
            encoder_type=self.cfg.encoder_type,
        ).to(self.device)
        self.target_critic = TwinCritic(
            pixel_height=pixel_height,
            pixel_width=pixel_width,
            pixel_channels=pixel_channels,
            state_dim=self.state_dim,
            action_dim=self.noise_action_dim,
            hidden_dims=self.cfg.critic_hidden_dims,
            cnn_features=self.cfg.cnn_features,
            cnn_strides=self.cfg.cnn_strides,
            cnn_padding=self.cfg.cnn_padding,
            latent_dim=self.cfg.latent_dim,
            use_bottleneck=self.cfg.use_bottleneck,
            encoder_type=self.cfg.encoder_type,
        ).to(self.device)
        self.target_critic.load_state_dict(self.critic.state_dict())

        self.actor_opt = torch.optim.Adam(self.actor.parameters(), lr=self.cfg.actor_lr)
        self.critic_opt = torch.optim.Adam(self.critic.parameters(), lr=self.cfg.critic_lr)
        self.alpha_opt = torch.optim.Adam([self.log_alpha], lr=self.cfg.alpha_lr)

        logger.info(
            "Initialized UniSteer RL trainer: "
            f"state_dim={self.state_dim}, noise_action_dim={self.noise_action_dim}, pixel_shape={self.pixel_shape}"
        )

    def _maybe_build_from_transition(
        self,
        observation: Mapping[str, Any],
        next_observation: Mapping[str, Any],
        action: np.ndarray,
    ) -> None:
        if self.actor is not None:
            return
        obs = normalize_unisteer_observation(observation)
        next_obs = normalize_unisteer_observation(next_observation)
        if obs["pixels"].shape != next_obs["pixels"].shape:
            raise ValueError(
                f"Observation pixel shape mismatch: {obs['pixels'].shape} vs {next_obs['pixels'].shape}"
            )
        if obs["state"].shape != next_obs["state"].shape:
            raise ValueError(
                f"Observation state shape mismatch: {obs['state'].shape} vs {next_obs['state'].shape}"
            )
        self._build_networks(
            state_dim=int(obs["state"].shape[0]),
            noise_action_dim=int(action.size),
            pixel_shape=tuple(int(v) for v in obs["pixels"].shape),
        )

    def add_transition(
        self,
        *,
        observation: Mapping[str, Any],
        next_observation: Mapping[str, Any],
        noise_action: Any,
        reward: float,
        mask: float,
        discount: float,
    ) -> None:
        action_np = _to_numpy(noise_action, dtype=np.float32).reshape(-1)
        self._maybe_build_from_transition(observation, next_observation, action_np)
        self.replay_buffer.add(
            observation=observation,
            next_observation=next_observation,
            action=action_np,
            reward=reward,
            mask=mask,
            discount=discount,
        )

    def ready(self) -> bool:
        return self.actor is not None and self.replay_buffer.size > 0

    def _sample_batch_tensors(self, batch_size: int) -> Dict[str, Any]:
        batch_np = self.replay_buffer.sample(batch_size)
        return {
            "observations": batch_unisteer_observations_to_torch(
                batch_np["observations"], self.device
            ),
            "next_observations": batch_unisteer_observations_to_torch(
                batch_np["next_observations"], self.device
            ),
            "actions": torch.from_numpy(batch_np["actions"]).to(self.device, dtype=torch.float32),
            "rewards": torch.from_numpy(batch_np["rewards"]).to(self.device, dtype=torch.float32),
            "masks": torch.from_numpy(batch_np["masks"]).to(self.device, dtype=torch.float32),
            "discounts": torch.from_numpy(batch_np["discounts"]).to(
                self.device, dtype=torch.float32
            ),
        }

    def _grad_norm(self, module: nn.Module) -> float:
        total_sq_norm = 0.0
        has_grad = False
        for param in module.parameters():
            if param.grad is None:
                continue
            has_grad = True
            grad_norm = param.grad.detach().norm(2)
            total_sq_norm += float(grad_norm.item() ** 2)
        if not has_grad:
            return 0.0
        return float(total_sq_norm**0.5)

    def _clip_or_measure_grad_norm(
        self, module: nn.Module, clip_norm: Optional[float]
    ) -> Tuple[float, float]:
        pre_clip_norm = self._grad_norm(module)
        if clip_norm is None or float(clip_norm) <= 0.0:
            return pre_clip_norm, pre_clip_norm
        torch.nn.utils.clip_grad_norm_(module.parameters(), max_norm=float(clip_norm))
        return pre_clip_norm, self._grad_norm(module)

    def _soft_update(self, source: nn.Module, target: nn.Module, tau: float) -> None:
        with torch.no_grad():
            for target_param, param in zip(target.parameters(), source.parameters()):
                target_param.data.mul_(1.0 - tau).add_(param.data, alpha=tau)

    def _reduce_q(self, q1: torch.Tensor, q2: torch.Tensor) -> torch.Tensor:
        if self.cfg.critic_reduction == "min":
            return torch.min(q1, q2)
        if self.cfg.critic_reduction == "mean":
            return 0.5 * (q1 + q2)
        raise ValueError(f"Unsupported critic_reduction={self.cfg.critic_reduction}")

    def _augment_pixels(self, pixels: torch.Tensor) -> torch.Tensor:
        aug_pixels = _batched_random_crop(pixels, self.cfg.augmentation_padding)
        num_cameras = max(1, int(aug_pixels.shape[1] // 3))
        aug_pixels = _batched_color_transform(
            aug_pixels, num_cameras=num_cameras, enabled=self.cfg.color_jitter
        )
        return aug_pixels

    def _augment_observations(
        self, observations: Mapping[str, torch.Tensor], *, augment: bool
    ) -> Dict[str, torch.Tensor]:
        if not augment:
            return {"pixels": observations["pixels"], "state": observations["state"]}
        return {
            "pixels": self._augment_pixels(observations["pixels"]),
            "state": observations["state"],
        }

    def update(self, num_updates: Optional[int] = None) -> Dict[str, float]:
        if num_updates is None:
            num_updates = self.cfg.updates_per_step
        if not self.ready():
            raise RuntimeError(f"Replay buffer not ready: size={self.replay_buffer.size}")
        metrics: Dict[str, float] = {}
        for _ in range(int(num_updates)):
            metrics = self._update_once()
        return metrics

    def _update_once(self) -> Dict[str, float]:
        assert self.actor is not None
        assert self.critic is not None
        assert self.target_critic is not None
        assert self.actor_opt is not None
        assert self.critic_opt is not None
        assert self.alpha_opt is not None

        batch = self._sample_batch_tensors(self.cfg.batch_size)
        observations = batch["observations"]
        next_observations = batch["next_observations"]
        actions = batch["actions"]
        rewards = batch["rewards"]
        masks = batch["masks"]
        discounts = batch["discounts"]

        observations = self._augment_observations(observations, augment=True)
        next_observations = self._augment_observations(next_observations, augment=self.cfg.aug_next)

        with torch.no_grad():
            next_actions, next_logp, _ = self.actor.sample(next_observations, deterministic=False)
            target_q1, target_q2 = self.target_critic(next_observations, next_actions)
            # Use the real-world critic target without an entropy backup.
            target_v = self._reduce_q(target_q1, target_q2)
            bellman_target = rewards + masks * discounts * target_v

        current_q1, current_q2 = self.critic(observations, actions)
        # Official JAX implementation averages the squared TD error across the Q ensemble.
        current_qs = torch.stack([current_q1, current_q2], dim=0)
        critic_loss = (current_qs - bellman_target.unsqueeze(0)).pow(2).mean()

        self.critic_opt.zero_grad(set_to_none=True)
        critic_loss.backward()
        critic_grad_norm_pre_clip, critic_grad_norm = self._clip_or_measure_grad_norm(
            self.critic, self.cfg.critic_grad_clip_norm
        )
        self.critic_opt.step()

        sampled_actions, logp, mean_actions = self.actor.sample(observations, deterministic=False)
        q1_pi, q2_pi = self.critic(observations, sampled_actions)
        q_pi = self._reduce_q(q1_pi, q2_pi)
        actor_loss = (self.alpha.detach() * logp - q_pi).mean()

        self.actor_opt.zero_grad(set_to_none=True)
        actor_loss.backward()
        actor_grad_norm_pre_clip, actor_grad_norm = self._clip_or_measure_grad_norm(
            self.actor, self.cfg.actor_grad_clip_norm
        )
        self.actor_opt.step()

        alpha_loss = torch.tensor(0.0, device=self.device)
        if self.cfg.learnable_temperature:
            target_entropy = self.cfg.target_entropy
            if target_entropy is None:
                target_entropy = -float(self.noise_action_dim)
            entropy = -logp.detach()
            # Temperature update: alpha * (entropy - target_entropy).
            alpha_loss = (self.alpha * (entropy - target_entropy)).mean()
            self.alpha_opt.zero_grad(set_to_none=True)
            alpha_loss.backward()
            self.alpha_opt.step()

        self._soft_update(self.critic, self.target_critic, self.cfg.tau)
        self.update_step += 1

        metrics = {
            "step": float(self.update_step),
            "critic_loss": float(critic_loss.item()),
            "actor_loss": float(actor_loss.item()),
            "alpha_loss": float(alpha_loss.item()),
            "alpha": float(self.alpha.detach().item()),
            "q_mean": float(current_qs.mean().item()),
            "q_min": float(current_qs.min().item()),
            "q_max": float(current_qs.max().item()),
            "q_pi_mean": float(q_pi.mean().item()),
            "target_v_mean": float(target_v.mean().item()),
            "bellman_target_mean": float(bellman_target.mean().item()),
            "bellman_target_min": float(bellman_target.min().item()),
            "bellman_target_max": float(bellman_target.max().item()),
            "reward_mean": float(rewards.mean().item()),
            "reward_min": float(rewards.min().item()),
            "reward_max": float(rewards.max().item()),
            "reward_std": float(rewards.std(unbiased=False).item()),
            "mask_mean": float(masks.mean().item()),
            "terminal_fraction": float((1.0 - masks).mean().item()),
            "discount_mean": float(discounts.mean().item()),
            "logp_mean": float(logp.mean().item()),
            "entropy_mean": float((-logp).mean().item()),
            "replay_action_abs_max": float(actions.abs().max().item()),
            "sampled_action_abs_max": float(sampled_actions.abs().max().item()),
            "mean_action_abs_max": float(mean_actions.abs().max().item()),
            "mean_action_abs_mean": float(mean_actions.abs().mean().item()),
            "actor_grad_clip_norm": 0.0
            if self.cfg.actor_grad_clip_norm is None
            else float(self.cfg.actor_grad_clip_norm),
            "critic_grad_clip_norm": 0.0
            if self.cfg.critic_grad_clip_norm is None
            else float(self.cfg.critic_grad_clip_norm),
            "actor_grad_norm_pre_clip": float(actor_grad_norm_pre_clip),
            "actor_grad_norm": float(actor_grad_norm),
            "critic_grad_norm_pre_clip": float(critic_grad_norm_pre_clip),
            "critic_grad_norm": float(critic_grad_norm),
            "replay_size": float(self.replay_buffer.size),
        }
        return metrics

    def _ensure_actor_sft_optimizer(self) -> torch.optim.Optimizer:
        if self.actor is None:
            raise RuntimeError("Actor SFT requires initialized UniSteer actor")
        if self.actor_sft_opt is None:
            self.actor_sft_opt = torch.optim.Adam(self.actor.parameters(), lr=self.cfg.actor_sft_lr)
        else:
            for group in self.actor_sft_opt.param_groups:
                group["lr"] = float(self.cfg.actor_sft_lr)
        return self.actor_sft_opt

    def supervised_actor_step(
        self, observations: Mapping[str, Any], target_noise_actions: Any
    ) -> Dict[str, float]:
        if self.actor is None:
            raise RuntimeError("Actor SFT requires initialized UniSteer actor")
        optimizer = self._ensure_actor_sft_optimizer()

        obs_t = batch_unisteer_observations_to_torch(observations, self.device)
        if isinstance(target_noise_actions, torch.Tensor):
            target_t = target_noise_actions.to(self.device, dtype=torch.float32)
            if target_t.ndim == 1:
                target_t = target_t.unsqueeze(0)
            elif target_t.ndim != 2:
                raise ValueError(
                    f"target_noise_actions must have shape [A] or [B, A], got {list(target_t.shape)}"
                )
        else:
            target_np = np.asarray(target_noise_actions, dtype=np.float32)
            if target_np.ndim == 1:
                target_np = target_np[None, ...]
            elif target_np.ndim != 2:
                raise ValueError(
                    f"target_noise_actions must have shape [A] or [B, A], got {list(target_np.shape)}"
                )
            target_t = torch.from_numpy(np.ascontiguousarray(target_np)).to(
                self.device, dtype=torch.float32
            )
        if target_t.shape[1] != int(self.noise_action_dim):
            raise ValueError(
                f"target_noise_actions dim mismatch: got {target_t.shape[1]} expected {self.noise_action_dim}"
            )
        mean, _ = self.actor(obs_t)
        mean_action = torch.tanh(mean) * float(self.cfg.noise_action_limit)
        actor_supervised_loss = F.mse_loss(mean_action, target_t)

        optimizer.zero_grad(set_to_none=True)
        actor_supervised_loss.backward()
        actor_grad_norm = self._grad_norm(self.actor)
        optimizer.step()

        self.actor_sft_step += 1
        return {
            "step": float(self.actor_sft_step),
            "actor_supervised_loss": float(actor_supervised_loss.item()),
            "actor_grad_norm": float(actor_grad_norm),
        }

    def state_dict(self) -> Dict[str, Any]:
        if self.actor is None or self.critic is None or self.target_critic is None:
            raise RuntimeError("RLTrainer is not initialized yet")
        payload = {
            "cfg": asdict(self.cfg),
            "state_dim": int(self.state_dim),
            "noise_action_dim": int(self.noise_action_dim),
            "pixel_shape": list(self.pixel_shape),
            "actor": self.actor.state_dict(),
            "critic": self.critic.state_dict(),
            "target_critic": self.target_critic.state_dict(),
            "actor_opt": self.actor_opt.state_dict() if self.actor_opt is not None else None,
            "critic_opt": self.critic_opt.state_dict() if self.critic_opt is not None else None,
            "log_alpha": self.log_alpha.detach().cpu(),
            "alpha_opt": self.alpha_opt.state_dict() if self.alpha_opt is not None else None,
            "update_step": int(self.update_step),
            "actor_sft_step": int(self.actor_sft_step),
        }
        if self.cfg.save_buffer_in_checkpoint:
            payload["replay_buffer"] = self.replay_buffer.state_dict()
        return payload

    def actor_state_dict(self) -> Dict[str, Any]:
        if self.actor is None or self.pixel_shape is None:
            raise RuntimeError("RLTrainer actor is not initialized yet")
        return {
            "cfg": asdict(self.cfg),
            "state_dim": int(self.state_dim),
            "noise_action_dim": int(self.noise_action_dim),
            "pixel_shape": list(self.pixel_shape),
            "actor_distribution": "tanh_gaussian",
            "actor": self.actor.state_dict(),
            "update_step": int(self.actor_update_step),
            "rl_update_step": int(self.update_step),
            "actor_sft_step": int(self.actor_sft_step),
        }

    def _sync_train_config_to_runtime(self) -> None:
        """Training config is authoritative after loading checkpoint weights."""
        if self.actor is not None:
            self.actor.action_limit = float(self.cfg.noise_action_limit)
            self.actor.policy.action_limit = float(self.cfg.noise_action_limit)
        if self.actor_opt is not None:
            for group in self.actor_opt.param_groups:
                group["lr"] = float(self.cfg.actor_lr)
        if self.critic_opt is not None:
            for group in self.critic_opt.param_groups:
                group["lr"] = float(self.cfg.critic_lr)
        if self.alpha_opt is not None:
            for group in self.alpha_opt.param_groups:
                group["lr"] = float(self.cfg.alpha_lr)

    @staticmethod
    def _optimizer_lr(optimizer: Optional[torch.optim.Optimizer]) -> Optional[float]:
        if optimizer is None or not optimizer.param_groups:
            return None
        return float(optimizer.param_groups[0].get("lr", 0.0))

    def load_state_dict(self, state: Mapping[str, Any], *, strict: bool = True) -> None:
        cfg_payload = state.get("cfg")

        state_dim = int(state["state_dim"])
        noise_action_dim = int(state["noise_action_dim"])
        pixel_shape = tuple(int(v) for v in state["pixel_shape"])

        if self.actor is None or self.critic is None or self.target_critic is None:
            self._build_networks(
                state_dim=state_dim, noise_action_dim=noise_action_dim, pixel_shape=pixel_shape
            )

        assert self.actor is not None
        assert self.critic is not None
        assert self.target_critic is not None
        self.actor.load_state_dict(state["actor"], strict=strict)
        self.critic.load_state_dict(state["critic"], strict=strict)
        self.target_critic.load_state_dict(state["target_critic"], strict=strict)

        if self.actor_opt is not None and state.get("actor_opt") is not None:
            self.actor_opt.load_state_dict(state["actor_opt"])
        if self.critic_opt is not None and state.get("critic_opt") is not None:
            self.critic_opt.load_state_dict(state["critic_opt"])

        log_alpha = state.get("log_alpha")
        if log_alpha is not None:
            self.log_alpha = torch.as_tensor(
                log_alpha, device=self.device, dtype=torch.float32
            ).requires_grad_(True)
        if self.alpha_opt is not None and state.get("alpha_opt") is not None:
            self.alpha_opt = torch.optim.Adam([self.log_alpha], lr=self.cfg.alpha_lr)
            self.alpha_opt.load_state_dict(state["alpha_opt"])

        self.update_step = int(state.get("update_step", 0))
        self.actor_sft_step = int(state.get("actor_sft_step", 0))
        if self.cfg.save_buffer_in_checkpoint and state.get("replay_buffer") is not None:
            self.replay_buffer.load_state_dict(state["replay_buffer"])

        self._sync_train_config_to_runtime()
        checkpoint_noise_limit = None
        if cfg_payload is not None:
            checkpoint_noise_limit = cfg_payload.get("noise_action_limit")
        logger.info(
            "Loaded UniSteer trainer state with current training config: "
            f"checkpoint_noise_action_limit={checkpoint_noise_limit}, "
            f"train_noise_action_limit={self.cfg.noise_action_limit}, "
            f"actor_action_limit={self.actor.action_limit if self.actor is not None else None}, "
            f"actor_lr={self.cfg.actor_lr}, critic_lr={self.cfg.critic_lr}, alpha_lr={self.cfg.alpha_lr}, "
            f"actor_opt_lr={self._optimizer_lr(self.actor_opt)}, "
            f"critic_opt_lr={self._optimizer_lr(self.critic_opt)}, "
            f"alpha_opt_lr={self._optimizer_lr(self.alpha_opt)}, "
            f"state_dim={state_dim}, noise_action_dim={noise_action_dim}, pixel_shape={pixel_shape}, "
            f"step={self.update_step}"
        )

    def save_checkpoint(self, path: str | Path) -> str:
        ckpt_path = str(Path(path).expanduser().resolve())
        Path(ckpt_path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.state_dict(), ckpt_path)
        logger.info(f"Saved UniSteer checkpoint to {ckpt_path}")
        return ckpt_path

    def save_actor_checkpoint(self, path: str | Path) -> str:
        ckpt_path = str(Path(path).expanduser().resolve())
        Path(ckpt_path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.actor_state_dict(), ckpt_path)
        logger.info(f"Saved UniSteer actor checkpoint to {ckpt_path}")
        return ckpt_path

    def load_checkpoint(self, path: str | Path, *, strict: bool = True) -> None:
        ckpt_path = str(Path(path).expanduser().resolve())
        payload = torch.load(ckpt_path, map_location="cpu")
        self.load_state_dict(payload, strict=strict)
        logger.info(f"Loaded UniSteer checkpoint from {ckpt_path}")
