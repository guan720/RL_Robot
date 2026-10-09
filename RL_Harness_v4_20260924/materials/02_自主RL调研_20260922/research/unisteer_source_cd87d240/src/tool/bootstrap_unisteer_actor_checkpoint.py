from __future__ import annotations

import argparse
from pathlib import Path

try:
    from omegaconf import OmegaConf, open_dict
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "omegaconf is required to run bootstrap_unisteer_actor_checkpoint.py"
    ) from exc

from src.model.openpi.openpi_common import has_explicit_openpi_policy_type
from src.model.openpi.openpi_noise import resolve_openpi_noise_layout
from src.trainer import RLTrainer


def _register_omegaconf_resolvers() -> None:
    from datetime import datetime
    import math

    OmegaConf.register_new_resolver("eval", eval, replace=True)
    OmegaConf.register_new_resolver("round_up", math.ceil, replace=True)
    OmegaConf.register_new_resolver("round_down", math.floor, replace=True)
    OmegaConf.register_new_resolver("now", lambda fmt: datetime.now().strftime(fmt), replace=True)


def _maybe_get(cfg, key: str, default=None):
    if cfg is None:
        return default
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return getattr(cfg, key, default)


def main() -> None:
    _register_omegaconf_resolvers()

    parser = argparse.ArgumentParser(description="Bootstrap an initial UniSteer actor checkpoint")
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--state_dim", type=int, default=None)
    parser.add_argument("--noise_action_dim", type=int, default=None)
    parser.add_argument("--pixel_height", type=int, default=None)
    parser.add_argument("--pixel_width", type=int, default=None)
    parser.add_argument("--pixel_channels", type=int, default=None)
    args = parser.parse_args()

    cfg = OmegaConf.load(str(Path(args.config).expanduser().resolve()))
    unisteer_cfg = _maybe_get(cfg, "unisteer", None)

    state_dim = args.state_dim
    if state_dim is None:
        state_dim = _maybe_get(unisteer_cfg, "state_dim", None)
    if state_dim is None:
        state_dim = int(_maybe_get(cfg, "proprio_dim", 7)) + int(
            _maybe_get(
                _maybe_get(_maybe_get(cfg, "mixture", None), "vlm", None), "hidden_size", 2048
            )
        )

    noise_action_dim = args.noise_action_dim
    if noise_action_dim is None and has_explicit_openpi_policy_type(cfg):
        noise_action_dim = resolve_openpi_noise_layout(cfg).actor_noise_dim
    if noise_action_dim is None:
        noise_action_dim = _maybe_get(unisteer_cfg, "noise_action_dim", None)
    if noise_action_dim is None:
        noise_action_dim = int(_maybe_get(cfg, "horizon_steps", 16)) * int(
            _maybe_get(cfg, "action_dim", 7)
        )

    pixel_height = args.pixel_height
    if pixel_height is None:
        pixel_height = _maybe_get(unisteer_cfg, "pixel_height", None)
    if pixel_height is None:
        pixel_height = int(
            _maybe_get(
                _maybe_get(_maybe_get(cfg, "vision", None), "config", None), "image_size", 224
            )
        )

    pixel_width = args.pixel_width
    if pixel_width is None:
        pixel_width = _maybe_get(unisteer_cfg, "pixel_width", None)
    if pixel_width is None:
        pixel_width = int(pixel_height)

    pixel_channels = args.pixel_channels
    if pixel_channels is None:
        pixel_channels = _maybe_get(unisteer_cfg, "pixel_channels", None)
    if pixel_channels is None:
        pixel_channels = 6 if bool(_maybe_get(cfg, "use_wrist", False)) else 3

    with open_dict(cfg):
        if _maybe_get(cfg, "unisteer", None) is None:
            cfg.unisteer = {}
        cfg.unisteer.device = str(args.device)
        cfg.unisteer.state_dim = int(state_dim)
        cfg.unisteer.noise_action_dim = int(noise_action_dim)
        cfg.unisteer.pixel_height = int(pixel_height)
        cfg.unisteer.pixel_width = int(pixel_width)
        cfg.unisteer.pixel_channels = int(pixel_channels)

    trainer = RLTrainer(cfg)
    output = str(Path(args.output).expanduser().resolve())
    trainer.save_checkpoint(output)
    print(output)


if __name__ == "__main__":
    main()
