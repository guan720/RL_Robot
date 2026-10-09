from __future__ import annotations

import math
from typing import Optional

import torch
from torchvision.transforms import InterpolationMode
from torchvision.transforms import functional as VF

SFT_AUG_OUTPUT_SIZE = (224, 224)
SFT_AUG_SCALE = (0.8, 1.0)
SFT_AUG_RATIO = (0.9, 1.1)
SFT_AUG_BRIGHTNESS = (0.9, 1.1)
SFT_AUG_CONTRAST = (0.9, 1.1)
SFT_AUG_SATURATION = (0.9, 1.1)
SFT_AUG_HUE = (-0.05, 0.05)


def _resolve_generator(
    *, seed: Optional[int], generator: Optional[torch.Generator]
) -> Optional[torch.Generator]:
    if seed is not None and generator is not None:
        raise ValueError("Pass either seed or generator, not both")
    if generator is not None:
        return generator
    if seed is None:
        return None
    resolved = torch.Generator()
    resolved.manual_seed(int(seed))
    return resolved


def _rand_uniform(low: float, high: float, *, generator: Optional[torch.Generator]) -> float:
    return float(
        torch.empty((), dtype=torch.float32).uniform_(low, high, generator=generator).item()
    )


def _randint_inclusive(low: int, high: int, *, generator: Optional[torch.Generator]) -> int:
    if low > high:
        raise ValueError(f"Expected low <= high, got low={low}, high={high}")
    if low == high:
        return int(low)
    return int(torch.randint(low, high + 1, (), generator=generator).item())


def _as_batched_nchw(images: torch.Tensor) -> tuple[torch.Tensor, bool]:
    if images.ndim == 3:
        return images.unsqueeze(0), True
    if images.ndim == 4:
        return images, False
    raise ValueError(f"Expected image tensor rank 3 or 4, got shape={list(images.shape)}")


def _sample_random_resized_crop_params(
    *, height: int, width: int, generator: Optional[torch.Generator]
) -> tuple[int, int, int, int]:
    area = float(height * width)
    log_ratio = (math.log(float(SFT_AUG_RATIO[0])), math.log(float(SFT_AUG_RATIO[1])))
    for _ in range(10):
        target_area = area * _rand_uniform(
            float(SFT_AUG_SCALE[0]), float(SFT_AUG_SCALE[1]), generator=generator
        )
        aspect_ratio = math.exp(_rand_uniform(log_ratio[0], log_ratio[1], generator=generator))
        crop_w = int(round(math.sqrt(target_area * aspect_ratio)))
        crop_h = int(round(math.sqrt(target_area / aspect_ratio)))
        if 0 < crop_w <= width and 0 < crop_h <= height:
            top = _randint_inclusive(0, height - crop_h, generator=generator)
            left = _randint_inclusive(0, width - crop_w, generator=generator)
            return top, left, crop_h, crop_w

    in_ratio = float(width) / float(height)
    if in_ratio < min(SFT_AUG_RATIO):
        crop_w = width
        crop_h = int(round(crop_w / min(SFT_AUG_RATIO)))
    elif in_ratio > max(SFT_AUG_RATIO):
        crop_h = height
        crop_w = int(round(crop_h * max(SFT_AUG_RATIO)))
    else:
        crop_w = width
        crop_h = height
    top = (height - crop_h) // 2
    left = (width - crop_w) // 2
    return top, left, crop_h, crop_w


def _sample_color_jitter_ops(*, generator: Optional[torch.Generator]) -> list[tuple[str, float]]:
    ops = [
        (
            "brightness",
            _rand_uniform(
                float(SFT_AUG_BRIGHTNESS[0]), float(SFT_AUG_BRIGHTNESS[1]), generator=generator
            ),
        ),
        (
            "contrast",
            _rand_uniform(
                float(SFT_AUG_CONTRAST[0]), float(SFT_AUG_CONTRAST[1]), generator=generator
            ),
        ),
        (
            "saturation",
            _rand_uniform(
                float(SFT_AUG_SATURATION[0]), float(SFT_AUG_SATURATION[1]), generator=generator
            ),
        ),
        ("hue", _rand_uniform(float(SFT_AUG_HUE[0]), float(SFT_AUG_HUE[1]), generator=generator)),
    ]
    order = torch.randperm(len(ops), generator=generator).tolist()
    return [ops[idx] for idx in order]


def apply_sft_image_aug(
    images: torch.Tensor, *, seed: Optional[int] = None, generator: Optional[torch.Generator] = None
) -> torch.Tensor:
    resolved_generator = _resolve_generator(seed=seed, generator=generator)
    batch, squeeze_output = _as_batched_nchw(images)
    if batch.ndim != 4 or int(batch.shape[1]) != 3:
        raise ValueError(f"Expected NCHW images with channel dim=3, got shape={list(batch.shape)}")

    top, left, crop_h, crop_w = _sample_random_resized_crop_params(
        height=int(batch.shape[-2]), width=int(batch.shape[-1]), generator=resolved_generator
    )
    out = VF.resized_crop(
        batch,
        top=top,
        left=left,
        height=crop_h,
        width=crop_w,
        size=list(SFT_AUG_OUTPUT_SIZE),
        interpolation=InterpolationMode.BILINEAR,
        antialias=True,
    )
    for op_name, factor in _sample_color_jitter_ops(generator=resolved_generator):
        if op_name == "brightness":
            out = VF.adjust_brightness(out, factor)
        elif op_name == "contrast":
            out = VF.adjust_contrast(out, factor)
        elif op_name == "saturation":
            out = VF.adjust_saturation(out, factor)
        elif op_name == "hue":
            out = VF.adjust_hue(out, factor)
        else:
            raise ValueError(f"Unsupported augmentation op: {op_name}")
    return out[0] if squeeze_output else out
