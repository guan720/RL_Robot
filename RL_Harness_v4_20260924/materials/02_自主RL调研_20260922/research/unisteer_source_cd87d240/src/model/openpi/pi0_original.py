from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from lerobot.configs import FeatureType, NormalizationMode, PolicyFeature, PreTrainedConfig
from lerobot.policies.pi0.configuration_pi0 import PI0Config
from lerobot.policies.pi0.modeling_pi0 import PI0Policy, make_att_2d_masks
from lerobot.policies.pi0.processor_pi0 import Pi0NewLineProcessor
from lerobot.processor import (
    AbsoluteActionsProcessorStep,
    AddBatchDimensionProcessorStep,
    DeviceProcessorStep,
    NormalizerProcessorStep,
    PolicyProcessorPipeline,
    RelativeActionsProcessorStep,
    TokenizerProcessorStep,
    UnnormalizerProcessorStep,
    policy_action_to_transition,
    transition_to_policy_action,
)
from lerobot.utils.constants import (
    ACTION,
    OBS_STATE,
    POLICY_POSTPROCESSOR_DEFAULT_NAME,
    POLICY_PREPROCESSOR_DEFAULT_NAME,
)
from safetensors.torch import load_file as load_safetensors_file
import torch

from src.model.openpi.openpi_common import (
    LANGUAGE_ATTENTION_MASK_KEY,
    LANGUAGE_TOKENS_KEY,
    PRIMARY_IMAGE_KEY,
    TASK_KEY,
    WRIST_IMAGE_KEY,
    _cfg_get,
    _feature_stats_from_dataset,
    _flatten_state,
    _image_to_float01,
    _load_training_checkpoint,
    _pad_or_trim_last_dim,
    _resolve_checkpoint_path,
    _resolve_policy_normalization_mode,
    _to_lerobot_normalization_mode,
    apply_runtime_openpi_surface_config,
    openpi_config_device,
    resolve_openpi_tokenizer_source,
    resolve_openpi_train_hparam_source,
    sync_normal_policy_horizon,
)


def make_local_pi0_pre_post_processors(
    config: PI0Config,
    *,
    dataset_stats: dict[str, dict[str, torch.Tensor]] | None,
    tokenizer_source: str,
) -> tuple[
    PolicyProcessorPipeline[dict[str, Any], dict[str, Any]],
    PolicyProcessorPipeline[torch.Tensor, torch.Tensor],
]:
    relative_step = RelativeActionsProcessorStep(
        enabled=config.use_relative_actions,
        exclude_joints=getattr(config, "relative_exclude_joints", []),
        action_names=getattr(config, "action_feature_names", None),
    )
    input_steps = [
        AddBatchDimensionProcessorStep(),
        Pi0NewLineProcessor(),
        TokenizerProcessorStep(
            tokenizer_name=tokenizer_source,
            max_length=config.tokenizer_max_length,
            padding_side="right",
            padding="max_length",
        ),
        DeviceProcessorStep(device=config.device),
        relative_step,
        NormalizerProcessorStep(
            features={**config.input_features, **config.output_features},
            norm_map=config.normalization_mapping,
            stats=dataset_stats,
        ),
    ]
    output_steps = [
        UnnormalizerProcessorStep(
            features=config.output_features,
            norm_map=config.normalization_mapping,
            stats=dataset_stats,
        ),
        AbsoluteActionsProcessorStep(
            enabled=config.use_relative_actions, relative_step=relative_step
        ),
        DeviceProcessorStep(device="cpu"),
    ]
    return (
        PolicyProcessorPipeline[dict[str, Any], dict[str, Any]](
            steps=input_steps, name=POLICY_PREPROCESSOR_DEFAULT_NAME
        ),
        PolicyProcessorPipeline[torch.Tensor, torch.Tensor](
            steps=output_steps,
            name=POLICY_POSTPROCESSOR_DEFAULT_NAME,
            to_transition=policy_action_to_transition,
            to_output=transition_to_policy_action,
        ),
    )


def build_pi0_config(cfg: Any, *, device: str) -> PI0Config:
    config_device = openpi_config_device(device)
    action_dim = int(_cfg_get(cfg, "action_dim", 7))
    proprio_dim = int(_cfg_get(cfg, "proprio_dim", 7))
    internal_state_dim = int(_cfg_get(cfg, "pi0_max_state_dim", 32))
    internal_action_dim = int(_cfg_get(cfg, "pi0_max_action_dim", 32))
    if internal_state_dim < proprio_dim:
        raise ValueError(
            f"pi0_max_state_dim ({internal_state_dim}) must be >= proprio_dim ({proprio_dim})"
        )
    if internal_action_dim < action_dim:
        raise ValueError(
            f"pi0_max_action_dim ({internal_action_dim}) must be >= action_dim ({action_dim})"
        )
    chunk_size = sync_normal_policy_horizon(cfg)
    image_resolution = (
        int(_cfg_get(cfg, "image_resolution", (224, 224))[0]),
        int(_cfg_get(cfg, "image_resolution", (224, 224))[1]),
    )
    train_vlm = bool(_cfg_get(cfg, "train_vlm", False))
    action_lr = float(_cfg_get(cfg, "action_lr", 5e-5))
    action_wd = float(_cfg_get(cfg, "action_weight_decay", 0.0))
    vlm_lr = float(_cfg_get(cfg, "vlm_lr", action_lr))
    vlm_wd = float(_cfg_get(cfg, "vlm_weight_decay", action_wd))
    if train_vlm and (abs(vlm_lr - action_lr) > 1e-12 or abs(vlm_wd - action_wd) > 1e-12):
        raise ValueError(
            "original pi0 path uses a single optimizer; "
            "set vlm_lr/action_lr and vlm_weight_decay/action_weight_decay to the same values"
        )

    lr_sched_cfg = _cfg_get(cfg, "action_lr_scheduler", {}) or {}
    input_features = {
        PRIMARY_IMAGE_KEY: PolicyFeature(type=FeatureType.VISUAL, shape=(3, *image_resolution)),
        OBS_STATE: PolicyFeature(type=FeatureType.STATE, shape=(proprio_dim,)),
    }
    if bool(_cfg_get(cfg, "use_wrist", False)):
        input_features[WRIST_IMAGE_KEY] = PolicyFeature(
            type=FeatureType.VISUAL, shape=(3, *image_resolution)
        )

    output_features = {ACTION: PolicyFeature(type=FeatureType.ACTION, shape=(action_dim,))}

    model_dtype = (
        "bfloat16"
        if (bool(_cfg_get(cfg, "use_bf16", True)) and not config_device.startswith("cpu"))
        else "float32"
    )
    state_norm_mode = _to_lerobot_normalization_mode(
        _resolve_policy_normalization_mode(cfg, "state_normalization_mode", "QUANTILES")
    )
    action_norm_mode = _to_lerobot_normalization_mode(
        _resolve_policy_normalization_mode(cfg, "action_normalization_mode", "QUANTILES")
    )

    return PI0Config(
        n_obs_steps=1,
        input_features=input_features,
        output_features=output_features,
        device=config_device,
        use_amp=bool(_cfg_get(cfg, "use_amp", False)),
        paligemma_variant=str(_cfg_get(cfg, "pi0_paligemma_variant", "gemma_2b")),
        action_expert_variant=str(_cfg_get(cfg, "pi0_action_expert_variant", "gemma_300m")),
        dtype=model_dtype,
        chunk_size=chunk_size,
        # Active normal-policy infer always returns the full chunk; control-side
        # replan cadence is external to this repo, so we do not expose a second
        # infer-time horizon knob here.
        n_action_steps=chunk_size,
        max_state_dim=internal_state_dim,
        max_action_dim=internal_action_dim,
        num_inference_steps=int(_cfg_get(cfg, "num_inference_steps", 10)),
        image_resolution=image_resolution,
        normalization_mapping={
            "VISUAL": NormalizationMode.IDENTITY,
            "STATE": state_norm_mode,
            "ACTION": action_norm_mode,
        },
        gradient_checkpointing=bool(_cfg_get(cfg, "gradient_checkpointing", False)),
        compile_model=bool(_cfg_get(cfg, "use_torch_compile", False)),
        compile_mode=str(_cfg_get(cfg, "torch_compile_mode", "max-autotune")),
        freeze_vision_encoder=bool(_cfg_get(cfg, "freeze_vision_encoder", False)),
        train_expert_only=not train_vlm,
        optimizer_lr=action_lr,
        optimizer_weight_decay=action_wd,
        optimizer_grad_clip_norm=float(_cfg_get(cfg, "max_grad_norm", 1.0)),
        scheduler_warmup_steps=int(_cfg_get(lr_sched_cfg, "warmup_steps", 200)),
        scheduler_decay_steps=int(
            _cfg_get(lr_sched_cfg, "first_cycle_steps", _cfg_get(cfg, "max_updates_total", 30000))
        ),
        scheduler_decay_lr=float(_cfg_get(lr_sched_cfg, "min_lr", 1e-8)),
        tokenizer_max_length=int(_cfg_get(cfg, "pi0_tokenizer_max_length", 48)),
    )


def _load_pretrained_directory_checkpoint(
    resolved_path: str, *, device: str
) -> tuple[PI0Policy, PI0Config]:
    config = PreTrainedConfig.from_pretrained(
        pretrained_name_or_path=resolved_path, local_files_only=True
    )
    if not isinstance(config, PI0Config):
        raise TypeError(f"Expected PI0Config from {resolved_path}, got {type(config)}")

    config.device = openpi_config_device(device)
    policy = PI0Policy(config)

    model_file = Path(resolved_path) / "model.safetensors"
    if not model_file.is_file():
        raise FileNotFoundError(f"model.safetensors not found under {resolved_path}")

    original_state_dict = load_safetensors_file(str(model_file), device=device)
    fixed_state_dict = policy._fix_pytorch_state_dict_keys(original_state_dict, policy.config)
    remapped_state_dict = {
        (key if key.startswith("model.") else f"model.{key}"): value
        for key, value in fixed_state_dict.items()
    }
    policy.load_state_dict(remapped_state_dict, strict=False)
    policy.eval()
    return policy, config


def load_pi0_policy(
    cfg: Any, *, device: str, checkpoint_path: str | None = None
) -> tuple[PI0Policy, PI0Config, dict[str, Any] | None]:
    config = build_pi0_config(cfg, device=device)
    resolved_path = _resolve_checkpoint_path(cfg, checkpoint_path)
    if not resolved_path:
        raise ValueError(
            "No original pi0 model source configured. Set inference_checkpoint_path, "
            "resume_checkpoint_path, init_ckpt, or pretrained_model_path."
        )

    path_obj = Path(resolved_path)
    if path_obj.is_dir():
        policy, loaded_config = _load_pretrained_directory_checkpoint(resolved_path, device=device)
        return policy, loaded_config, None

    if path_obj.is_file() and path_obj.suffix == ".pt":
        policy = PI0Policy(config)
        checkpoint = _load_training_checkpoint(
            policy, resolved_path, device=device, family_name="pi0"
        )
        policy.to(config.device)
        policy.eval()
        return policy, config, checkpoint

    raise ValueError(
        f"Unsupported original pi0 model source: {resolved_path}. "
        "Expected a pretrained directory with model.safetensors or a trainer-produced .pt checkpoint."
    )


@dataclass
class Pi0OriginalAdapter:
    cfg: Any
    dataset_statistics: dict[str, Any]
    device: str

    def __post_init__(self) -> None:
        self.policy_config = build_pi0_config(self.cfg, device=self.device)
        self.tokenizer_source = resolve_openpi_tokenizer_source(self.cfg, family="pi0")
        self._refresh_processors(self.policy_config)

    @staticmethod
    def _state_key_from_config(policy_config: PI0Config) -> str:
        for key, feature in policy_config.input_features.items():
            if feature.type == FeatureType.STATE:
                return key
        return OBS_STATE

    @staticmethod
    def _visual_keys_from_config(policy_config: PI0Config) -> list[str]:
        return [
            key
            for key, feature in policy_config.input_features.items()
            if feature.type == FeatureType.VISUAL
        ]

    @staticmethod
    def _action_key_from_config(policy_config: PI0Config) -> str:
        for key, feature in policy_config.output_features.items():
            if feature.type == FeatureType.ACTION:
                return key
        return ACTION

    def _refresh_processors(self, policy_config: PI0Config) -> None:
        state_key = self._state_key_from_config(policy_config)
        action_key = self._action_key_from_config(policy_config)
        state_dim = int(policy_config.input_features[state_key].shape[0])
        action_dim = int(policy_config.output_features[action_key].shape[0])
        self.policy_config = policy_config
        self.feature_stats = _feature_stats_from_dataset(
            self.dataset_statistics,
            state_key=state_key,
            state_dim=state_dim,
            action_key=action_key,
            action_dim=action_dim,
        )
        self.preprocessor, self.postprocessor = make_local_pi0_pre_post_processors(
            self.policy_config,
            dataset_stats=self.feature_stats,
            tokenizer_source=self.tokenizer_source,
        )

    def load_policy(
        self, checkpoint_path: str | None = None
    ) -> tuple[PI0Policy, dict[str, Any] | None]:
        policy, loaded_config, checkpoint = load_pi0_policy(
            self.cfg, device=self.device, checkpoint_path=checkpoint_path
        )
        loaded_config = apply_runtime_openpi_surface_config(
            loaded_config,
            self.policy_config,
            train_hparam_source=resolve_openpi_train_hparam_source(self.cfg),
        )
        self._refresh_processors(loaded_config)
        return policy, checkpoint

    def finetune_batch_to_model_batch(
        self, batch: dict[str, Any], *, dataset: Any, include_action: bool
    ) -> dict[str, Any]:
        visual_keys = self._visual_keys_from_config(self.policy_config)
        state_key = self._state_key_from_config(self.policy_config)
        model_batch: dict[str, Any] = {
            # FinetuneDataset yields image chunks as [B, 1, H, W, C]; original pi0 expects [B, C, H, W].
            visual_keys[0]: _image_to_float01(
                batch["image_primary"][:, 0].permute(0, 3, 1, 2).contiguous()
            ),
            state_key: dataset.denormalize(_flatten_state(batch["proprio"]), norm_key="proprio").to(
                torch.float32
            ),
            TASK_KEY: list(batch["instruction"]),
        }
        model_batch[state_key] = _pad_or_trim_last_dim(
            model_batch[state_key], int(self.policy_config.input_features[state_key].shape[0])
        )
        if len(visual_keys) > 1 and "image_wrist" in batch and batch["image_wrist"] is not None:
            model_batch[visual_keys[1]] = _image_to_float01(
                batch["image_wrist"][:, 0].permute(0, 3, 1, 2).contiguous()
            )
        if include_action:
            action_key = self._action_key_from_config(self.policy_config)
            model_batch[action_key] = dataset.denormalize(batch["action"], norm_key="action").to(
                torch.float32
            )
        return self.preprocessor(model_batch)

    def observation_to_model_batch(
        self,
        *,
        image: torch.Tensor,
        image_wrist: torch.Tensor | None,
        proprio: torch.Tensor,
        task_description: list[str],
    ) -> dict[str, Any]:
        visual_keys = self._visual_keys_from_config(self.policy_config)
        state_key = self._state_key_from_config(self.policy_config)
        model_batch: dict[str, Any] = {
            visual_keys[0]: _image_to_float01(image),
            state_key: _pad_or_trim_last_dim(
                _flatten_state(proprio).to(torch.float32),
                int(self.policy_config.input_features[state_key].shape[0]),
            ),
            TASK_KEY: list(task_description),
        }
        if len(visual_keys) > 1 and image_wrist is not None:
            model_batch[visual_keys[1]] = _image_to_float01(image_wrist)
        return self.preprocessor(model_batch)

    def postprocess_action(self, action: torch.Tensor) -> torch.Tensor:
        processed = self.postprocessor(action)
        if not isinstance(processed, torch.Tensor):
            raise TypeError(f"Expected tensor action after postprocess, got {type(processed)}")
        return processed

    def unisteer_internal_noise_dim(self) -> int:
        return int(self.policy_config.max_action_dim)

    def pad_action_to_internal_noise_dim(self, action: torch.Tensor) -> torch.Tensor:
        if action.ndim != 3:
            raise ValueError(f"Expected action chunk [B,H,D], got {list(action.shape)}")
        return _pad_or_trim_last_dim(
            action.to(torch.float32), int(self.policy_config.max_action_dim)
        )

    def build_denoise_context(
        self, policy: PI0Policy, *, model_batch: dict[str, Any]
    ) -> dict[str, Any]:
        images, img_masks = policy._preprocess_images(model_batch)
        lang_tokens = model_batch[LANGUAGE_TOKENS_KEY]
        lang_masks = model_batch[LANGUAGE_ATTENTION_MASK_KEY]
        state = policy.prepare_state(model_batch)

        prefix_embs, prefix_pad_masks, prefix_att_masks = policy.model.embed_prefix(
            images, img_masks, lang_tokens, lang_masks
        )
        prefix_att_2d_masks = make_att_2d_masks(prefix_pad_masks, prefix_att_masks)
        prefix_position_ids = torch.cumsum(prefix_pad_masks, dim=1) - 1
        prefix_att_2d_masks_4d = policy.model._prepare_attention_masks_4d(prefix_att_2d_masks)
        policy.model.paligemma_with_expert.paligemma.model.language_model.config._attn_implementation = "eager"  # noqa: SLF001

        _, past_key_values = policy.model.paligemma_with_expert.forward(
            attention_mask=prefix_att_2d_masks_4d,
            position_ids=prefix_position_ids,
            past_key_values=None,
            inputs_embeds=[prefix_embs, None],
            use_cache=True,
        )
        return {
            "prefix_pad_masks": prefix_pad_masks,
            "past_key_values": past_key_values,
            "state": state,
        }

    def denoise_step(
        self,
        policy: PI0Policy,
        *,
        context: Mapping[str, Any],
        action: torch.Tensor,
        timestep: torch.Tensor,
    ) -> torch.Tensor:
        return policy.model.denoise_step(
            state=context["state"],
            prefix_pad_masks=context["prefix_pad_masks"],
            past_key_values=context["past_key_values"],
            x_t=action,
            timestep=timestep,
        )

    def extract_unisteer_state(
        self, policy: PI0Policy, *, model_batch: dict[str, Any], raw_proprio: torch.Tensor
    ) -> torch.Tensor:
        images, img_masks = policy._preprocess_images(model_batch)
        lang_tokens = model_batch[LANGUAGE_TOKENS_KEY]
        lang_masks = model_batch[LANGUAGE_ATTENTION_MASK_KEY]

        prefix_embs, prefix_pad_masks, prefix_att_masks = policy.model.embed_prefix(
            images, img_masks, lang_tokens, lang_masks
        )
        prefix_att_2d_masks = make_att_2d_masks(prefix_pad_masks, prefix_att_masks)
        prefix_position_ids = torch.cumsum(prefix_pad_masks, dim=1) - 1
        prefix_att_2d_masks_4d = policy.model._prepare_attention_masks_4d(prefix_att_2d_masks)
        policy.model.paligemma_with_expert.paligemma.model.language_model.config._attn_implementation = "eager"  # noqa: SLF001

        outputs_embeds, _ = policy.model.paligemma_with_expert.forward(
            attention_mask=prefix_att_2d_masks_4d,
            position_ids=prefix_position_ids,
            past_key_values=None,
            inputs_embeds=[prefix_embs, None],
            use_cache=False,
        )

        prefix_output = outputs_embeds[0]
        valid_lengths = prefix_pad_masks.to(dtype=torch.long).sum(dim=1).clamp_min(1)
        last_valid_idx = valid_lengths - 1
        batch_indices = torch.arange(prefix_output.shape[0], device=prefix_output.device)
        prefix_rep = prefix_output[batch_indices, last_valid_idx, :].to(dtype=torch.float32)

        raw_state = _flatten_state(raw_proprio).to(device=prefix_rep.device, dtype=torch.float32)
        return torch.cat([raw_state, prefix_rep], dim=-1)
