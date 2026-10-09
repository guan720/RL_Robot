"""
Inference agent for original LeRobot OpenPI family policies.

The active normal-policy path returns float32[inference_chunk_size, action_dim]
via predict_action_chunk().
Infer-side queueing/select_action semantics are intentionally unused.

For OpenPI UniSteer, the actor predicts compressed internal noise with shape
[predicted_noise_steps, internal_noise_dim] and this wrapper expands it to the
runtime inference chunk before decoding to real actions.
"""

from __future__ import annotations

from types import MethodType
from typing import Any, Mapping

from loguru import logger
import numpy as np
import torch
import torch.nn.functional as F

from src.dataset.dataset import FinetuneDataset
from src.model.openpi.openpi_adapter import build_openpi_adapter
from src.model.openpi.openpi_common import (
    _cfg_get,
    resolve_openpi_policy_type,
    sync_normal_policy_horizon,
)
from src.model.openpi.openpi_noise import (
    expand_actor_noise_to_full_torch,
    resolve_openpi_noise_layout,
)


class InferenceAgent:
    """Thin inference wrapper for runtime-sized OpenPI action chunks."""

    def __init__(self, cfg: Any, dataset: FinetuneDataset | None = None, use_cpu: bool = False):
        self.cfg = cfg
        self.use_cpu = use_cpu
        self.gpu_id = int(getattr(cfg, "gpu_id", 0))
        configured_device = str(getattr(cfg, "device", ""))
        if self.use_cpu or not torch.cuda.is_available():
            self.device = torch.device("cpu")
        elif configured_device:
            self.device = torch.device(configured_device)
        else:
            self.device = torch.device(f"cuda:{self.gpu_id}")

        logger.info(f"Using device: {self.device}")
        self.horizon_steps = int(sync_normal_policy_horizon(cfg))
        self.inference_chunk_size = int(_cfg_get(cfg, "inference_chunk_size", self.horizon_steps))
        if self.inference_chunk_size < 1 or self.inference_chunk_size > self.horizon_steps:
            raise ValueError(
                f"inference_chunk_size must be in [1, horizon_steps={self.horizon_steps}], "
                f"got {self.inference_chunk_size}"
            )
        self.ds_train = (
            dataset if dataset is not None else FinetuneDataset(cfg.data.finetune, train=True)
        )
        logger.info("Inference normalization ranges\n" + self.ds_train.normalization_summary_str())

        self.policy_type = resolve_openpi_policy_type(cfg)
        self.adapter = build_openpi_adapter(
            cfg, dataset_statistics=self.ds_train.dataset_statistics, device=str(self.device)
        )
        self.unisteer_noise_layout = resolve_openpi_noise_layout(cfg)
        self.unisteer_prefix_rep_dim = int(
            _cfg_get(_cfg_get(_cfg_get(cfg, "mixture", None), "vlm", None), "hidden_size", 2048)
        )
        self.policy, _ = self.adapter.load_policy(getattr(cfg, "inference_checkpoint_path", None))
        self.policy.eval()
        self._patch_policy_runtime_action_length()
        logger.info(
            f"Original {self.policy_type} inference agent is ready "
            f"(horizon_steps={self.horizon_steps}, inference_chunk_size={self.inference_chunk_size})"
        )

    def _patch_policy_runtime_action_length(self) -> None:
        if self.policy_type != "pi05":
            if self.inference_chunk_size != self.horizon_steps:
                raise ValueError(
                    f"inference_chunk_size={self.inference_chunk_size} is currently supported only for pi05; "
                    f"{self.policy_type} must keep inference_chunk_size == horizon_steps"
                )
            return

        model = getattr(self.policy, "model", None)
        if model is None or not hasattr(model, "embed_suffix"):
            raise TypeError(
                "Expected a pi05 policy with model.embed_suffix for runtime chunk inference"
            )
        if bool(getattr(model, "_unisteer_dynamic_suffix_length", False)):
            return

        from lerobot.policies.pi05.modeling_pi05 import create_sinusoidal_pos_embedding

        def embed_suffix_dynamic(
            model_self: Any, noisy_actions: torch.Tensor, timestep: torch.Tensor
        ):
            embs = []
            pad_masks = []
            att_masks = []

            time_emb = create_sinusoidal_pos_embedding(
                timestep,
                model_self.action_in_proj.out_features,
                min_period=model_self.config.min_period,
                max_period=model_self.config.max_period,
                device=timestep.device,
            )
            time_emb = time_emb.type(dtype=timestep.dtype)

            def action_proj_func(actions: torch.Tensor) -> torch.Tensor:
                return model_self.action_in_proj(actions)

            action_emb = model_self._apply_checkpoint(action_proj_func, noisy_actions)

            def time_mlp_func(time_value: torch.Tensor) -> torch.Tensor:
                hidden = model_self.time_mlp_in(time_value)
                hidden = F.silu(hidden)
                hidden = model_self.time_mlp_out(hidden)
                return F.silu(hidden)

            time_emb = model_self._apply_checkpoint(time_mlp_func, time_emb)
            action_time_emb = action_emb
            adarms_cond = time_emb

            embs.append(action_time_emb)
            batch_size, action_time_dim = action_time_emb.shape[:2]
            action_time_mask = torch.ones(
                batch_size, action_time_dim, dtype=torch.bool, device=action_time_emb.device
            )
            pad_masks.append(action_time_mask)

            # PI05 can denoise any runtime action length; the attention mask must
            # follow the actual noisy_actions length rather than config.chunk_size.
            att_masks += [1] + ([0] * (int(action_time_dim) - 1))

            embs = torch.cat(embs, dim=1)
            pad_masks = torch.cat(pad_masks, dim=1)
            att_masks_tensor = torch.tensor(att_masks, dtype=embs.dtype, device=embs.device)
            att_masks_tensor = att_masks_tensor[None, :].expand(batch_size, len(att_masks))

            return embs, pad_masks, att_masks_tensor, adarms_cond

        model.embed_suffix = MethodType(embed_suffix_dynamic, model)
        model._unisteer_dynamic_suffix_length = True
        logger.info("Patched pi05 suffix attention masks to follow runtime action length")

    def _expand_actor_noise(self, noise_action: Any, *, batch_size: int) -> torch.Tensor:
        return expand_actor_noise_to_full_torch(
            noise_action,
            layout=self.unisteer_noise_layout,
            batch_size=batch_size,
            target_steps=self.inference_chunk_size,
            device=self.device,
            dtype=torch.float32,
        )

    def _build_base_inference_noise(self, *, batch_size: int) -> torch.Tensor | None:
        if self.inference_chunk_size == self.horizon_steps:
            return None
        return self.policy.model.sample_noise(
            (
                int(batch_size),
                int(self.inference_chunk_size),
                int(self.adapter.unisteer_internal_noise_dim()),
            ),
            self.device,
        )

    def build_decode_inputs(
        self,
        *,
        image: torch.Tensor,
        image_wrist: torch.Tensor | None,
        proprio: torch.Tensor,
        task_description: list[str],
    ) -> dict[str, Any]:
        return self.adapter.observation_to_model_batch(
            image=image, image_wrist=image_wrist, proprio=proprio, task_description=task_description
        )

    def build_decode_context_from_prebuilt_inputs(
        self, *, inputs: Mapping[str, Any], is_pretrain: bool = False
    ) -> dict[str, Any]:
        if is_pretrain:
            raise ValueError(
                "OpenPI UniSteer wrapper only supports finetune/runtime mode, not pretrain mode"
            )
        model_batch = dict(inputs)
        denoise_context = self.adapter.build_denoise_context(self.policy, model_batch=model_batch)
        return {
            "model_batch": model_batch,
            "batch_size": int(
                next(value.shape[0] for value in inputs.values() if isinstance(value, torch.Tensor))
            ),
            "denoise_context": denoise_context,
        }

    def build_decode_context(
        self,
        *,
        image: torch.Tensor,
        image_wrist: torch.Tensor | None,
        proprio: torch.Tensor,
        task_description: list[str],
        is_pretrain: bool = False,
    ) -> dict[str, Any]:
        inputs = self.build_decode_inputs(
            image=image, image_wrist=image_wrist, proprio=proprio, task_description=task_description
        )
        return self.build_decode_context_from_prebuilt_inputs(
            inputs=inputs, is_pretrain=is_pretrain
        )

    def decode_action_norm_from_prebuilt_inputs(
        self, *, inputs: Mapping[str, Any], noise_action: Any, is_pretrain: bool = False
    ) -> torch.Tensor:
        if is_pretrain:
            raise ValueError(
                "OpenPI UniSteer wrapper only supports finetune/runtime mode, not pretrain mode"
            )
        batch_size = int(
            next(value.shape[0] for value in inputs.values() if isinstance(value, torch.Tensor))
        )
        full_noise = self._expand_actor_noise(noise_action, batch_size=batch_size)
        return self.policy.predict_action_chunk(dict(inputs), noise=full_noise)

    def decode_action_norm_from_prebuilt_context(
        self, *, context: Mapping[str, Any], noise_action: Any, is_pretrain: bool = False
    ) -> torch.Tensor:
        if is_pretrain:
            raise ValueError(
                "OpenPI UniSteer wrapper only supports finetune/runtime mode, not pretrain mode"
            )
        model_batch = context["model_batch"]
        batch_size = int(context["batch_size"])
        full_noise = self._expand_actor_noise(noise_action, batch_size=batch_size)
        return self.policy.predict_action_chunk(model_batch, noise=full_noise)

    def _build_unisteer_pixels(
        self, image: torch.Tensor, image_wrist: torch.Tensor | None
    ) -> np.ndarray:
        image_np = (
            image.detach().cpu().numpy() if isinstance(image, torch.Tensor) else np.asarray(image)
        )
        if image_np.ndim != 4:
            raise ValueError(
                f"UniSteer primary image must be [B, C, H, W], got {list(image_np.shape)}"
            )

        if image_wrist is not None:
            wrist_np = (
                image_wrist.detach().cpu().numpy()
                if isinstance(image_wrist, torch.Tensor)
                else np.asarray(image_wrist)
            )
            if wrist_np.ndim != 4:
                raise ValueError(
                    f"UniSteer wrist image must be [B, C, H, W], got {list(wrist_np.shape)}"
                )
        else:
            wrist_np = None

        include_wrist = bool(getattr(self.cfg, "use_wrist", False))
        pixels = []
        for batch_idx in range(image_np.shape[0]):
            primary = np.transpose(image_np[batch_idx], (1, 2, 0)).astype(np.uint8, copy=False)
            if include_wrist:
                if wrist_np is None:
                    wrist = np.zeros_like(primary, dtype=np.uint8)
                else:
                    wrist = np.transpose(wrist_np[batch_idx], (1, 2, 0)).astype(
                        np.uint8, copy=False
                    )
                pixel = np.concatenate([primary, wrist], axis=-1)
            else:
                pixel = primary
            pixels.append(pixel[..., None])
        return np.stack(pixels, axis=0).astype(np.uint8, copy=False)

    def build_unisteer_pixels(
        self, *, image: torch.Tensor, image_wrist: torch.Tensor | None
    ) -> np.ndarray:
        pixels_np = self._build_unisteer_pixels(image, image_wrist)
        if pixels_np.shape[0] == 1:
            return pixels_np[0]
        return pixels_np

    def pad_action_chunk_to_internal_noise_dim(self, action_chunk: torch.Tensor) -> torch.Tensor:
        return self.adapter.pad_action_to_internal_noise_dim(action_chunk)

    def denoise_step_from_prebuilt_context(
        self, *, context: Mapping[str, Any], action: torch.Tensor, timestep: torch.Tensor
    ) -> torch.Tensor:
        return self.adapter.denoise_step(
            self.policy, context=context["denoise_context"], action=action, timestep=timestep
        )

    def get_model_dtype(self) -> torch.dtype:
        action_proj = getattr(self.policy.model, "action_in_proj", None)
        if action_proj is not None and hasattr(action_proj, "weight"):
            return action_proj.weight.dtype
        return next(self.policy.parameters()).dtype

    def get_num_inference_steps(self) -> int:
        return int(self.policy.config.num_inference_steps)

    def build_unisteer_observation(
        self,
        *,
        image: torch.Tensor,
        image_wrist: torch.Tensor | None,
        proprio: torch.Tensor,
        task_description: list[str],
    ) -> dict[str, np.ndarray]:
        model_batch = self.build_decode_inputs(
            image=image, image_wrist=image_wrist, proprio=proprio, task_description=task_description
        )
        with torch.inference_mode():
            state = self.adapter.extract_unisteer_state(
                self.policy, model_batch=model_batch, raw_proprio=proprio
            )

        state_np = state.detach().cpu().numpy().astype(np.float32, copy=False)
        if state_np.ndim == 2:
            state_np = state_np[:, :, None]
        elif state_np.ndim != 3:
            raise ValueError(f"Unexpected UniSteer state shape from OpenPI: {list(state_np.shape)}")

        pixels_np = self._build_unisteer_pixels(image, image_wrist)
        if pixels_np.shape[0] != state_np.shape[0]:
            raise ValueError(
                f"UniSteer observation batch mismatch: pixels={pixels_np.shape[0]} state={state_np.shape[0]}"
            )

        if pixels_np.shape[0] == 1:
            return {"pixels": pixels_np[0], "state": state_np[0]}
        return {"pixels": pixels_np, "state": state_np}

    def get_unisteer_state_dim(self) -> int:
        return int(_cfg_get(self.cfg, "proprio_dim", 7)) + int(self.unisteer_prefix_rep_dim)

    def get_unisteer_pixel_shape(self) -> tuple[int, int, int, int]:
        image_resolution = _cfg_get(self.cfg, "image_resolution", (224, 224))
        image_height = int(image_resolution[0])
        image_width = int(image_resolution[1])
        pixel_channels = 6 if bool(getattr(self.cfg, "use_wrist", False)) else 3
        return (image_height, image_width, pixel_channels, 1)

    def inference(
        self,
        *,
        image: torch.Tensor,
        image_wrist: torch.Tensor | None,
        proprio: torch.Tensor,
        task_description: list[str],
    ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        model_batch = self.build_decode_inputs(
            image=image, image_wrist=image_wrist, proprio=proprio, task_description=task_description
        )
        with torch.inference_mode():
            batch_size = int(
                next(
                    value.shape[0]
                    for value in model_batch.values()
                    if isinstance(value, torch.Tensor)
                )
            )
            noise = self._build_base_inference_noise(batch_size=batch_size)
            if noise is None:
                action_pred_norm = self.policy.predict_action_chunk(model_batch)
            else:
                action_pred_norm = self.policy.predict_action_chunk(model_batch, noise=noise)
            action_pred = self.adapter.postprocess_action(action_pred_norm)

        return (
            np.asarray(action_pred[0].detach().cpu(), dtype=np.float32),
            {
                "action_pred_norm": np.asarray(
                    action_pred_norm[0].detach().cpu(), dtype=np.float32
                ),
                "inference_chunk_size": np.asarray(self.inference_chunk_size, dtype=np.int32),
            },
        )

    def inference_from_noise(
        self,
        *,
        image: torch.Tensor,
        image_wrist: torch.Tensor | None,
        proprio: torch.Tensor,
        task_description: list[str],
        noise_action: Any,
        is_pretrain: bool = False,
    ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        action_pred_norm = self.decode_action_norm_from_prebuilt_inputs(
            inputs=self.build_decode_inputs(
                image=image,
                image_wrist=image_wrist,
                proprio=proprio,
                task_description=task_description,
            ),
            noise_action=noise_action,
            is_pretrain=is_pretrain,
        )
        action_pred = self.adapter.postprocess_action(action_pred_norm)
        return (
            np.asarray(action_pred[0].detach().cpu(), dtype=np.float32),
            {
                "action_pred_norm": np.asarray(
                    action_pred_norm[0].detach().cpu(), dtype=np.float32
                ),
                "inference_chunk_size": np.asarray(self.inference_chunk_size, dtype=np.int32),
            },
        )

    def load_checkpoint(self, path: str, finetuning: bool = True) -> None:
        del finetuning
        self.policy, _ = self.adapter.load_policy(path)
        self.policy.eval()
        self._patch_policy_runtime_action_length()
        logger.info(f"Reloaded original {self.policy_type} checkpoint: {path}")
