"""
Local inference-only runtime for the UniSteer noise actor.

The actor now consumes observation dictionaries:

    {
      "pixels": [H, W, 3 * num_cameras, 1],
      "state": [state_dim, 1],
    }

and outputs latent/noise actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
import torch

from src.trainer.RLTrainer import (
    RLConfig,
    TanhGaussianActor,
    batch_unisteer_observations_to_torch,
    normalize_unisteer_observation,
)

TANH_GAUSSIAN_DISTRIBUTION = "tanh_gaussian"


@dataclass
class UniSteerActorRuntime:
    state_dim: int
    noise_action_dim: int
    pixel_shape: tuple[int, int, int, int]
    actor_distribution: str
    update_step: int = 0
    checkpoint_path: Optional[str] = None


class UniSteerActorAgent:
    def __init__(
        self,
        cfg: Optional[Any] = None,
        *,
        checkpoint_path: Optional[str] = None,
        device: Optional[str | torch.device] = None,
        deterministic_by_default: bool = False,
    ):
        self.cfg = RLConfig.from_cfg(cfg or {})
        if device is None:
            device = (
                self.cfg.device
                if self.cfg.device
                else ("cuda" if torch.cuda.is_available() else "cpu")
            )
        self.device = torch.device(device)
        self.deterministic_by_default = bool(deterministic_by_default)

        self.actor: Optional[TanhGaussianActor] = None
        self.runtime: Optional[UniSteerActorRuntime] = None

        if checkpoint_path is not None:
            self.load_checkpoint(checkpoint_path)

    @property
    def ready(self) -> bool:
        return self.actor is not None and self.runtime is not None

    @property
    def state_dim(self) -> int:
        if self.runtime is None:
            raise RuntimeError("UniSteerActorAgent is not initialized yet")
        return self.runtime.state_dim

    @property
    def noise_action_dim(self) -> int:
        if self.runtime is None:
            raise RuntimeError("UniSteerActorAgent is not initialized yet")
        return self.runtime.noise_action_dim

    @property
    def update_step(self) -> int:
        if self.runtime is None:
            raise RuntimeError("UniSteerActorAgent is not initialized yet")
        return int(self.runtime.update_step)

    @property
    def checkpoint_path(self) -> Optional[str]:
        if self.runtime is None:
            raise RuntimeError("UniSteerActorAgent is not initialized yet")
        return self.runtime.checkpoint_path

    def _build_actor(
        self,
        *,
        state_dim: int,
        noise_action_dim: int,
        pixel_shape: tuple[int, int, int, int],
        actor_distribution: str,
    ) -> None:
        pixel_height = int(pixel_shape[0])
        pixel_width = int(pixel_shape[1])
        pixel_channels = int(pixel_shape[2])
        actor_kwargs = dict(
            pixel_height=pixel_height,
            pixel_width=pixel_width,
            pixel_channels=pixel_channels,
            state_dim=int(state_dim),
            action_dim=int(noise_action_dim),
            hidden_dims=self.cfg.actor_hidden_dims,
            log_std_min=self.cfg.log_std_min,
            log_std_max=self.cfg.log_std_max,
            cnn_features=self.cfg.cnn_features,
            cnn_strides=self.cfg.cnn_strides,
            cnn_padding=self.cfg.cnn_padding,
            latent_dim=self.cfg.latent_dim,
            dropout_rate=self.cfg.dropout_rate,
            use_bottleneck=self.cfg.use_bottleneck,
            encoder_type=self.cfg.encoder_type,
        )
        if actor_distribution != TANH_GAUSSIAN_DISTRIBUTION:
            raise ValueError(f"Unsupported actor_distribution: {actor_distribution!r}")
        self.actor = TanhGaussianActor(**actor_kwargs, action_limit=self.cfg.noise_action_limit).to(
            self.device
        )
        self.actor.eval()

    def load_checkpoint(
        self, path: str | Path, *, expected_distribution: Optional[str] = None
    ) -> None:
        ckpt_path = str(Path(path).expanduser().resolve())
        payload = torch.load(ckpt_path, map_location="cpu")

        cfg_payload = payload.get("cfg")
        if cfg_payload is not None:
            self.cfg = RLConfig.from_cfg(cfg_payload)

        state_dim = int(payload["state_dim"])
        noise_action_dim = int(payload["noise_action_dim"])
        pixel_shape = tuple(int(v) for v in payload["pixel_shape"])
        actor_distribution = str(payload.get("actor_distribution", TANH_GAUSSIAN_DISTRIBUTION))
        if actor_distribution != TANH_GAUSSIAN_DISTRIBUTION:
            raise ValueError(
                f"Unsupported actor checkpoint distribution: {actor_distribution!r}; "
                f"expected {TANH_GAUSSIAN_DISTRIBUTION!r}"
            )
        if expected_distribution is not None and actor_distribution != expected_distribution:
            raise ValueError(
                "Actor checkpoint distribution mismatch: "
                f"checkpoint={actor_distribution!r} expected={expected_distribution!r} "
                f"path={ckpt_path}"
            )

        if self.actor is None or self.runtime is None:
            self._build_actor(
                state_dim=state_dim,
                noise_action_dim=noise_action_dim,
                pixel_shape=pixel_shape,
                actor_distribution=actor_distribution,
            )
        else:
            same_shape = (
                self.runtime.state_dim == state_dim
                and self.runtime.noise_action_dim == noise_action_dim
                and tuple(self.runtime.pixel_shape) == tuple(pixel_shape)
                and self.runtime.actor_distribution == actor_distribution
            )
            if not same_shape:
                self._build_actor(
                    state_dim=state_dim,
                    noise_action_dim=noise_action_dim,
                    pixel_shape=pixel_shape,
                    actor_distribution=actor_distribution,
                )

        assert self.actor is not None
        self.actor.load_state_dict(payload["actor"])
        self.actor.action_limit = float(self.cfg.noise_action_limit)
        self.actor.policy.action_limit = float(self.cfg.noise_action_limit)
        self.actor.to(self.device)
        self.actor.eval()

        self.runtime = UniSteerActorRuntime(
            state_dim=state_dim,
            noise_action_dim=noise_action_dim,
            pixel_shape=tuple(pixel_shape),
            actor_distribution=actor_distribution,
            update_step=int(payload.get("update_step", 0)),
            checkpoint_path=ckpt_path,
        )
        logger.info(
            f"Loaded UniSteer actor checkpoint from {ckpt_path} "
            f"(state_dim={state_dim}, noise_action_dim={noise_action_dim}, pixel_shape={pixel_shape}, "
            f"actor_distribution={actor_distribution}, step={self.runtime.update_step}"
            f" noise_action_limit={self.cfg.noise_action_limit})"
        )

    def sample_noise_action(
        self,
        observation: Any,
        *,
        deterministic: Optional[bool] = None,
        temperature: Optional[float] = None,
        return_numpy: bool = True,
    ):
        if not self.ready:
            raise RuntimeError("UniSteerActorAgent is not ready; load a checkpoint first")

        obs = normalize_unisteer_observation(observation)
        batched_obs = {"pixels": obs["pixels"][None, ...], "state": obs["state"][None, ...]}
        obs_t = batch_unisteer_observations_to_torch(batched_obs, self.device)

        assert self.runtime is not None
        if int(obs["state"].shape[0]) != int(self.runtime.state_dim):
            raise ValueError(
                f"UniSteer state dimension mismatch: got={obs['state'].shape[0]} expected={self.runtime.state_dim}"
            )
        if tuple(obs["pixels"].shape) != tuple(self.runtime.pixel_shape):
            raise ValueError(
                f"UniSteer pixel shape mismatch: got={tuple(obs['pixels'].shape)} expected={self.runtime.pixel_shape}"
            )

        det = self.deterministic_by_default if deterministic is None else bool(deterministic)
        temp = 1.0 if temperature is None else float(temperature)
        if temp < 0.0:
            raise ValueError(f"temperature must be non-negative, got {temp}")

        assert self.actor is not None
        with torch.inference_mode():
            if det or temp == 0.0:
                _, _, mean_action = self.actor.sample(obs_t, deterministic=True)
                noise_action = mean_action
                log_prob = torch.zeros(
                    (mean_action.shape[0], 1), device=mean_action.device, dtype=mean_action.dtype
                )
                sampling_mode = "deterministic"
            elif temp == 1.0:
                noise_action, log_prob, mean_action = self.actor.sample(obs_t, deterministic=False)
                sampling_mode = "stochastic"
            else:
                mean, log_std = self.actor.forward(obs_t)
                std = log_std.exp() * temp
                normal = torch.distributions.Normal(mean, std)
                pre_tanh = normal.rsample()
                tanh_pre = torch.tanh(pre_tanh)
                noise_action = tanh_pre * self.actor.action_limit
                raw_log_prob = normal.log_prob(pre_tanh).sum(dim=-1, keepdim=True)
                correction = torch.log(1 - tanh_pre.pow(2) + 1e-6).sum(dim=-1, keepdim=True)
                log_prob = raw_log_prob - correction
                mean_action = torch.tanh(mean) * self.actor.action_limit
                sampling_mode = "tempered_stochastic"

        if return_numpy:
            noise_np = noise_action.detach().cpu().numpy()[0]
            logp_np = log_prob.detach().cpu().numpy()[0]
            mean_np = mean_action.detach().cpu().numpy()[0]
            return noise_np, {
                "deterministic": det,
                "sampling_mode": sampling_mode,
                "sampling_temperature": float(0.0 if det else temp),
                "log_prob": logp_np,
                "mean_action": mean_np,
                "update_step": self.runtime.update_step,
                "checkpoint_path": self.runtime.checkpoint_path,
                "actor_distribution": self.runtime.actor_distribution,
            }

        return noise_action[0], {
            "deterministic": det,
            "sampling_mode": sampling_mode,
            "sampling_temperature": float(0.0 if det else temp),
            "log_prob": log_prob[0],
            "mean_action": mean_action[0],
            "update_step": self.runtime.update_step,
            "checkpoint_path": self.runtime.checkpoint_path,
            "actor_distribution": self.runtime.actor_distribution,
        }

    def act(
        self,
        observation: Any,
        *,
        deterministic: Optional[bool] = None,
        temperature: Optional[float] = None,
    ):
        return self.sample_noise_action(
            observation, deterministic=deterministic, temperature=temperature, return_numpy=True
        )

    def sample_standard_gaussian_noise_action(self, *, return_numpy: bool = True):
        if self.runtime is None:
            raise RuntimeError("UniSteerActorAgent is not initialized yet")

        noise_action = torch.randn(
            int(self.runtime.noise_action_dim), device=self.device, dtype=torch.float32
        )
        mean_action = torch.zeros_like(noise_action)
        normal = torch.distributions.Normal(mean_action, torch.ones_like(noise_action))
        log_prob = normal.log_prob(noise_action).sum().reshape(1)

        info = {
            "deterministic": False,
            "sampling_mode": "initial_random_bypass",
            "sampling_temperature": 1.0,
            "log_prob": log_prob,
            "mean_action": mean_action,
            "update_step": int(self.runtime.update_step),
            "checkpoint_path": self.runtime.checkpoint_path,
            "initial_rollout_bypass_actor": True,
        }
        if return_numpy:
            return noise_action.detach().cpu().numpy(), {
                **info,
                "log_prob": log_prob.detach().cpu().numpy(),
                "mean_action": mean_action.detach().cpu().numpy(),
            }
        return noise_action, info

    def status(self) -> Dict[str, Any]:
        if not self.ready:
            return {"ready": False, "device": str(self.device)}
        assert self.runtime is not None
        return {
            "ready": True,
            "device": str(self.device),
            "state_dim": int(self.runtime.state_dim),
            "noise_action_dim": int(self.runtime.noise_action_dim),
            "pixel_shape": list(self.runtime.pixel_shape),
            "actor_distribution": self.runtime.actor_distribution,
            "update_step": int(self.runtime.update_step),
            "checkpoint_path": self.runtime.checkpoint_path,
        }
