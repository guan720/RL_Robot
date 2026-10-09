from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import random
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from loguru import logger
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from omegaconf import OmegaConf, open_dict
import torch
import torch.distributed as dist
from torch.nn import functional as F

from src.agent.inference_agent import InferenceAgent
from src.dataset.dataset import (
    FinetuneDataset,
    TrajectoryImageArrayCache,
    get_traj_num_steps,
    load_traj_image_frame_chw_uint8,
    load_traj_proprio_action,
    resolve_traj_image_array_path,
)
from src.model.openpi.openpi_common import has_explicit_openpi_policy_type
from src.model.openpi.openpi_noise import (
    expand_actor_noise_to_full_torch,
    project_full_noise_to_actor_torch,
    resolve_openpi_noise_layout,
)
from src.trainer.RLTrainer import (
    RLTrainer,
    batch_unisteer_observations_to_torch,
    normalize_unisteer_observation,
)
from src.utils.sft_image_aug import apply_sft_image_aug


def _pack_ndarray(array: Any) -> Dict[str, Any]:
    arr = np.ascontiguousarray(np.asarray(array))
    return {"dtype": str(arr.dtype), "shape": list(arr.shape), "data": arr.tobytes()}


def _cfg_get(cfg: Any, key: str, default: Any = None) -> Any:
    if cfg is None:
        return default
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return getattr(cfg, key, default)


def _resolve_torchrun_env() -> Dict[str, int]:
    return {
        "world_size": int(os.environ.get("WORLD_SIZE", "1")),
        "rank": int(os.environ.get("RANK", "0")),
        "local_rank": int(os.environ.get("LOCAL_RANK", "0")),
    }


def _resolve_local_device(device: str, *, local_rank: int) -> str:
    if not str(device).startswith("cuda"):
        return str(device)
    return f"cuda:{int(local_rank)}"


def _maybe_init_distributed_for_actor_sft(device: str) -> Dict[str, Any]:
    env = _resolve_torchrun_env()
    distributed = int(env["world_size"]) > 1
    resolved_device = _resolve_local_device(device, local_rank=int(env["local_rank"]))
    if distributed and not dist.is_initialized():
        torch.cuda.set_device(int(env["local_rank"]))
        dist.init_process_group(backend="nccl", init_method="env://", timeout=timedelta(hours=6))
    return {
        "distributed": bool(distributed),
        "world_size": int(env["world_size"]),
        "rank": int(env["rank"]),
        "local_rank": int(env["local_rank"]),
        "device": str(resolved_device),
        "main_rank": (not distributed) or int(env["rank"]) == 0,
    }


def _maybe_destroy_distributed() -> None:
    if dist.is_available() and dist.is_initialized():
        dist.barrier()
        dist.destroy_process_group()


def _load_meta(traj_dir: Path) -> Dict[str, Any]:
    meta_path = traj_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing meta.json under {traj_dir}")
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Invalid meta.json payload in {meta_path}")
    return payload


def _load_task_description(traj_dir: Path) -> str:
    txt = traj_dir / "task_instruction.txt"
    if txt.exists():
        task = txt.read_text(encoding="utf-8").strip()
        if task:
            return task
    payload = _load_meta(traj_dir)
    task = str(payload.get("task", "")).strip()
    if task:
        return task
    raise FileNotFoundError(f"Could not find task instruction under {traj_dir}")


def _load_raw_observation(
    *,
    traj_dir: Path,
    step_index: int,
    proprio_series: np.ndarray,
    image_key: str,
    wrist_key: Optional[str],
    extension: str,
    task_description: str,
    image_cache: Optional[TrajectoryImageArrayCache] = None,
) -> Dict[str, Any]:
    del extension
    if step_index < 0 or step_index >= proprio_series.shape[0]:
        raise IndexError(
            f"step_index out of range for {traj_dir}: step_index={step_index}, num_steps={proprio_series.shape[0]}"
        )

    if image_cache is None:
        image = load_traj_image_frame_chw_uint8(traj_dir, image_key, step_index)
    else:
        image = image_cache.get_frame(traj_dir, image_key, step_index, copy=True)

    wrist_image = None
    if wrist_key and resolve_traj_image_array_path(traj_dir, wrist_key).is_file():
        if image_cache is None:
            wrist_image = load_traj_image_frame_chw_uint8(traj_dir, wrist_key, step_index)
        else:
            wrist_image = image_cache.get_frame(traj_dir, wrist_key, step_index, copy=True)

    return {
        "image": image,
        "image_wrist": wrist_image,
        "proprio": proprio_series[step_index].astype(np.float32).copy(),
        "task_description": task_description,
    }


def _raw_observation_to_tensors(
    raw_observation: Mapping[str, Any],
) -> Tuple[torch.Tensor, Optional[torch.Tensor], torch.Tensor, List[str]]:
    image = np.array(raw_observation["image"], dtype=np.uint8, copy=True)
    image_t = torch.from_numpy(image[None, ...])

    wrist_t = None
    wrist_value = raw_observation.get("image_wrist")
    if wrist_value is not None:
        wrist = np.array(wrist_value, dtype=np.uint8, copy=True)
        wrist_t = torch.from_numpy(wrist[None, ...])

    proprio = np.asarray(raw_observation["proprio"], dtype=np.float32).reshape(1, 1, -1)
    proprio_t = torch.from_numpy(proprio)
    task = [str(raw_observation["task_description"])]
    return image_t, wrist_t, proprio_t, task


def _nchw_uint8_tensor(image_array: np.ndarray) -> torch.Tensor:
    arr = np.asarray(image_array, dtype=np.uint8)
    if arr.ndim != 3 or int(arr.shape[0]) != 3:
        raise ValueError(f"Expected CHW uint8 image with shape [3,H,W], got {list(arr.shape)}")
    return torch.from_numpy(arr[None, ...].copy())


def _build_tensor_observation_view(
    *,
    raw_observation: Mapping[str, Any],
    augment_index: int,
    is_augmented: bool,
    image_aug_seed: Optional[int],
) -> Dict[str, Any]:
    image_t = _nchw_uint8_tensor(raw_observation["image"])
    wrist_t = None
    wrist_value = raw_observation.get("image_wrist")
    if wrist_value is not None:
        wrist_t = _nchw_uint8_tensor(wrist_value)

    if is_augmented:
        if image_aug_seed is None:
            raise ValueError("Augmented view requires a deterministic image_aug_seed")
        aug_generator = torch.Generator()
        aug_generator.manual_seed(int(image_aug_seed))
        image_t = apply_sft_image_aug(image_t, generator=aug_generator)
        if wrist_t is not None:
            wrist_t = apply_sft_image_aug(wrist_t, generator=aug_generator)

    proprio = np.asarray(raw_observation["proprio"], dtype=np.float32).reshape(1, 1, -1)
    proprio_t = torch.from_numpy(proprio)
    return {
        "image_t": image_t,
        "wrist_t": wrist_t,
        "proprio_t": proprio_t,
        "task": [str(raw_observation["task_description"])],
        "augment_index": int(augment_index),
        "is_augmented": bool(is_augmented),
        "image_aug_seed": image_aug_seed,
    }


def _build_live_tensor_view_for_sample(
    *,
    sample: Mapping[str, Any],
    local_idx: int,
    update_idx: int,
    rank: int,
    settings: Mapping[str, Any],
    proprio_series: np.ndarray,
    image_cache: Optional[TrajectoryImageArrayCache],
) -> Dict[str, Any]:
    traj_dir = Path(str(sample["traj_dir"]))
    raw_observation = _load_raw_observation(
        traj_dir=traj_dir,
        step_index=int(sample["step_index"]),
        proprio_series=proprio_series,
        image_key=str(settings["image_key"]),
        wrist_key=settings["wrist_key"],
        extension=str(settings["extension"]),
        task_description=str(sample["task_description"]),
        image_cache=image_cache,
    )
    is_augmented = bool(settings["image_aug_enabled"])
    image_aug_seed = None
    if is_augmented:
        image_aug_seed = (
            int(settings["image_aug_seed"])
            + int(rank) * 1_000_003
            + int(update_idx) * 10_000_019
            + int(sample["global_sample_id"]) * 97
            + int(local_idx)
        )
    return {
        **_build_tensor_observation_view(
            raw_observation=raw_observation,
            augment_index=0,
            is_augmented=is_augmented,
            image_aug_seed=image_aug_seed,
        ),
        "sample": sample,
    }


def _make_tensor_observation_view_specs(
    *,
    include_original: bool,
    num_aug_views: int,
    image_aug_enabled: bool,
    image_aug_seed: int,
    sample_seed_offset: int,
) -> List[Dict[str, Any]]:
    if num_aug_views < 0:
        raise ValueError(f"num_aug_views must be >= 0, got {num_aug_views}")
    if not image_aug_enabled:
        num_aug_views = 0
    if (not include_original) and num_aug_views <= 0:
        raise ValueError("At least one original or augmented view is required")

    specs: List[Dict[str, Any]] = []
    if include_original:
        specs.append({"augment_index": 0, "is_augmented": False, "image_aug_seed": None})

    for aug_idx in range(num_aug_views):
        seed = int(image_aug_seed) + int(sample_seed_offset) * 1_000_003 + int(aug_idx)
        specs.append({"augment_index": len(specs), "is_augmented": True, "image_aug_seed": seed})
    return specs


def _split_decode_inputs(inputs: Mapping[str, Any]) -> List[Dict[str, Any]]:
    tensor_value = next(
        (value for value in inputs.values() if isinstance(value, torch.Tensor)), None
    )
    if tensor_value is None:
        raise ValueError("decode inputs do not contain any batched tensor")
    batch_size = int(tensor_value.shape[0])
    split: List[Dict[str, Any]] = []
    for batch_idx in range(batch_size):
        item: Dict[str, Any] = {}
        for key, value in inputs.items():
            if isinstance(value, torch.Tensor):
                item[key] = value[batch_idx : batch_idx + 1]
            elif isinstance(value, list):
                item[key] = [value[batch_idx]]
            else:
                item[key] = value
        split.append(item)
    return split


def _build_unisteer_batch_tensors_and_inputs(
    agent: InferenceAgent, tensor_views: Sequence[Mapping[str, Any]], *, device: torch.device | str
) -> Tuple[Dict[str, torch.Tensor], List[Dict[str, Any]]]:
    if not tensor_views:
        raise ValueError("tensor_views must not be empty")

    image_t = torch.cat([view["image_t"] for view in tensor_views], dim=0)
    proprio_t = torch.cat([view["proprio_t"] for view in tensor_views], dim=0)
    task = sum((list(view["task"]) for view in tensor_views), [])

    wrist_values = [view.get("wrist_t") for view in tensor_views]
    has_wrist = [value is not None for value in wrist_values]
    if any(has_wrist) and not all(has_wrist):
        raise ValueError("Mixed wrist/no-wrist tensor views in one target batch are not supported")
    wrist_t = (
        torch.cat([value for value in wrist_values if value is not None], dim=0)
        if all(has_wrist)
        else None
    )

    with torch.no_grad():
        observation = agent.build_unisteer_observation(
            image=image_t, image_wrist=wrist_t, proprio=proprio_t, task_description=task
        )
        decode_inputs = agent.build_decode_inputs(
            image=image_t, image_wrist=wrist_t, proprio=proprio_t, task_description=task
        )

    observation_t = batch_unisteer_observations_to_torch(
        {"pixels": observation["pixels"], "state": observation["state"]}, torch.device(device)
    )
    if observation_t["pixels"].shape[0] != len(tensor_views) or observation_t["state"].shape[
        0
    ] != len(tensor_views):
        raise ValueError(
            f"Batched UniSteer observation size mismatch: pixels={list(observation_t['pixels'].shape)}, "
            f"state={list(observation_t['state'].shape)}, views={len(tensor_views)}"
        )
    return observation_t, _split_decode_inputs(decode_inputs)


def _build_unisteer_observations_and_inputs_batch(
    agent: InferenceAgent, tensor_views: Sequence[Mapping[str, Any]]
) -> Tuple[List[Dict[str, np.ndarray]], List[Dict[str, Any]]]:
    observation_t, decode_inputs_list = _build_unisteer_batch_tensors_and_inputs(
        agent, tensor_views, device=agent.device
    )
    pixels = observation_t["pixels"].detach().cpu().permute(0, 2, 3, 1).unsqueeze(-1).numpy()
    state = observation_t["state"].detach().cpu().unsqueeze(-1).numpy()
    observations = [
        {
            "pixels": np.ascontiguousarray(pixels[idx].astype(np.uint8, copy=False)),
            "state": np.ascontiguousarray(state[idx].astype(np.float32, copy=False)),
        }
        for idx in range(len(tensor_views))
    ]
    return observations, decode_inputs_list


def _build_unisteer_observation_and_inputs(
    agent: InferenceAgent, raw_observation: Mapping[str, Any]
) -> Tuple[Dict[str, np.ndarray], Dict[str, Any]]:
    image_t, wrist_t, proprio_t, task = _raw_observation_to_tensors(raw_observation)
    with torch.no_grad():
        observation = agent.build_unisteer_observation(
            image=image_t, image_wrist=wrist_t, proprio=proprio_t, task_description=task
        )
        decode_inputs = agent.build_decode_inputs(
            image=image_t, image_wrist=wrist_t, proprio=proprio_t, task_description=task
        )
    obs = normalize_unisteer_observation(
        {"pixels": observation["pixels"], "state": observation["state"]}
    )
    return obs, decode_inputs


def _repeat_decode_inputs(inputs: Mapping[str, Any], repeat_count: int) -> Dict[str, Any]:
    if repeat_count <= 0:
        raise ValueError(f"repeat_count must be positive, got {repeat_count}")

    repeated: Dict[str, Any] = {}
    for key, value in inputs.items():
        if isinstance(value, torch.Tensor):
            repeat_shape = [repeat_count] + [1] * (value.ndim - 1)
            repeated[key] = value.repeat(*repeat_shape)
        elif isinstance(value, list):
            repeated[key] = value * repeat_count
        else:
            repeated[key] = value
    return repeated


def _concat_decode_inputs(input_list: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not input_list:
        raise ValueError("input_list must not be empty")

    merged: Dict[str, Any] = {}
    keys = list(input_list[0].keys())
    for key in keys:
        values = [item[key] for item in input_list]
        first = values[0]
        if isinstance(first, torch.Tensor):
            merged[key] = torch.cat(values, dim=0)
        elif isinstance(first, list):
            merged[key] = sum((list(v) for v in values), [])
        else:
            merged[key] = first
    return merged


def _make_human_finetune_cfg(cfg: Any, data_roots: Sequence[str]) -> Any:
    finetune_cfg = OmegaConf.create(OmegaConf.to_container(cfg.data.finetune, resolve=False))
    with open_dict(finetune_cfg):
        finetune_cfg.data_path = [str(Path(p).expanduser().resolve()) for p in data_roots]
        finetune_cfg.force_regenerate_meta = True
    return finetune_cfg


def _discover_traj_dirs(paths: Sequence[str]) -> List[Path]:
    discovered: set[Path] = set()
    for root_str in paths:
        root = Path(root_str).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Trajectory root does not exist: {root}")
        if (root / "meta.json").exists():
            discovered.add(root)
            continue
        discovered.update(path.parent.resolve() for path in root.rglob("meta.json"))
    return sorted(discovered, key=lambda p: str(p))


def _count_num_steps(traj_dir: Path, *, image_key: str, extension: str) -> int:
    del extension
    return get_traj_num_steps(traj_dir, image_key)


def _iter_human_samples_from_traj_dirs(
    *,
    traj_dirs: Sequence[Path],
    action_normalizer: FinetuneDataset,
    use_gripper_master: bool,
    image_key: str,
    extension: str,
    action_future_size: int,
    min_valid_action: int,
    min_valid_state: int,
) -> Iterable[Dict[str, Any]]:
    for traj_dir in traj_dirs:
        meta_payload = _load_meta(traj_dir)
        if "human_collect" not in meta_payload:
            raise KeyError(f"Missing 'human_collect' in {traj_dir / 'meta.json'}")
        if not bool(meta_payload["human_collect"]):
            continue

        _, action = load_traj_proprio_action(traj_dir, use_gripper_master=use_gripper_master)
        num_steps = _count_num_steps(traj_dir, image_key=image_key, extension=extension)
        if action.shape[0] != num_steps:
            raise ValueError(
                f"Action / image length mismatch under {traj_dir}: "
                f"action={action.shape[0]} num_steps={num_steps}"
            )

        action_indices = np.arange(
            int(min_valid_state) - 1, num_steps + int(action_future_size) - int(min_valid_action)
        )
        action_indices = sliding_window_view(action_indices, int(action_future_size), 0)
        action_indices = np.clip(action_indices, 0, num_steps - 1)

        task_description = _load_task_description(traj_dir)
        for sample_idx in range(int(action_indices.shape[0])):
            step_index = int(action_indices[sample_idx][0])
            action_norm = action_normalizer.normalize(
                action[action_indices[sample_idx]], norm_key="action", method="q01q99"
            ).astype(np.float32)
            yield {
                "traj_dir": traj_dir,
                "step_index": step_index,
                "task_description": task_description,
                "action_norm": np.asarray(action_norm, dtype=np.float32),
            }


def _prepare_runtime_cfg(cfg: Any, device: str, *, base_checkpoint: Optional[str] = None) -> Any:
    cfg_local = copy.deepcopy(cfg)
    with open_dict(cfg_local):
        cfg_local.device = device
        if device.startswith("cuda:"):
            cfg_local.gpu_id = int(device.split(":")[1])
        if hasattr(cfg_local, "unisteer"):
            cfg_local.unisteer.device = device
        resolved_base_checkpoint = base_checkpoint
        if resolved_base_checkpoint is None:
            resolved_base_checkpoint = getattr(
                cfg_local, "inference_checkpoint_path", None
            ) or getattr(cfg_local, "init_ckpt", None)
        if not resolved_base_checkpoint:
            raise ValueError(
                "Could not resolve Pi0/base checkpoint for actor supervision. "
                "Provide --base_checkpoint explicitly or set inference_checkpoint_path/init_ckpt in config."
            )
        cfg_local.inference_checkpoint_path = str(
            Path(resolved_base_checkpoint).expanduser().resolve()
        )
    return cfg_local


def _move_optimizer_to_device(
    optimizer: Optional[torch.optim.Optimizer], device: torch.device
) -> None:
    if optimizer is None:
        return
    for state in optimizer.state.values():
        for key, value in list(state.items()):
            if isinstance(value, torch.Tensor):
                state[key] = value.to(device)


def _move_actor_runtime_to_device(trainer: RLTrainer, device: str) -> None:
    target_device = torch.device(device)
    trainer.device = target_device
    trainer.cfg.device = device
    if trainer.actor is not None:
        trainer.actor.to(target_device)
    _move_optimizer_to_device(trainer.actor_opt, target_device)


def _infer_noise_target_batch_fixed_point_core(
    *,
    agent: InferenceAgent,
    decode_inputs_list: Sequence[Mapping[str, Any]],
    demo_action_t: torch.Tensor,
    fixed_point_iters: int,
    lambda_actor_prior: float,
    lambda_norm: float,
    emit_logs: bool = True,
) -> Tuple[torch.Tensor, List[Dict[str, float]]]:
    if demo_action_t.ndim != 3:
        raise ValueError(
            f"demo_action_t must have shape [B, H, A], got {list(demo_action_t.shape)}"
        )
    num_samples = int(demo_action_t.shape[0])
    if num_samples <= 0:
        raise ValueError("demo_action_t must not be empty")
    if len(decode_inputs_list) != num_samples:
        raise ValueError("decode_inputs_list and demo_action_t must have the same batch size")

    batched_decode_inputs = _concat_decode_inputs(list(decode_inputs_list))
    decode_context = agent.build_decode_context_from_prebuilt_inputs(
        inputs=batched_decode_inputs, is_pretrain=False
    )

    demo_action_t = demo_action_t.to(device=agent.device, dtype=torch.float32)
    model_dtype = agent.get_model_dtype()
    demo_action_full = agent.pad_action_chunk_to_internal_noise_dim(demo_action_t)
    x_next = demo_action_full.to(device=agent.device, dtype=model_dtype)
    reverse_steps = max(1, int(agent.get_num_inference_steps()))
    delta_t = 1.0 / float(reverse_steps)
    fixed_point_iters = max(1, int(fixed_point_iters))
    residuals: List[torch.Tensor] = []

    with torch.no_grad():
        for step_idx in range(reverse_steps - 1, -1, -1):
            t = torch.full(
                (num_samples,),
                float(step_idx) / float(reverse_steps),
                device=agent.device,
                dtype=model_dtype,
            )
            x = x_next.clone()
            for _ in range(fixed_point_iters):
                v_t = agent.denoise_step_from_prebuilt_context(
                    context=decode_context, action=x, timestep=t
                )
                x = x_next - delta_t * v_t

            v_final = agent.denoise_step_from_prebuilt_context(
                context=decode_context, action=x, timestep=t
            )
            step_residual = x + delta_t * v_final - x_next
            residuals.append(
                step_residual.reshape(num_samples, -1).float().pow(2).mean(dim=1).sqrt()
            )
            x_next = x

        pred_final = agent.decode_action_norm_from_prebuilt_context(
            context=decode_context, noise_action=x_next, is_pretrain=False
        ).float()
        compact_noise = project_full_noise_to_actor_torch(
            x_next, layout=agent.unisteer_noise_layout, device=agent.device, dtype=torch.float32
        )
        reexpanded_compact_noise = expand_actor_noise_to_full_torch(
            compact_noise,
            layout=agent.unisteer_noise_layout,
            batch_size=num_samples,
            device=agent.device,
            dtype=torch.float32,
        )
        pred_projected = agent.decode_action_norm_from_prebuilt_context(
            context=decode_context, noise_action=reexpanded_compact_noise, is_pretrain=False
        ).float()

    z_final = x_next.detach().to(device=agent.device, dtype=torch.float32)
    z_final_flat = z_final.reshape(num_samples, -1)
    residual_stack = (
        torch.stack(residuals, dim=1)
        if residuals
        else torch.zeros(num_samples, 1, device=agent.device)
    )

    final_action_loss_vec = (
        F.mse_loss(pred_final, demo_action_t, reduction="none").reshape(num_samples, -1).mean(dim=1)
    )
    post_projection_action_loss_vec = (
        F.mse_loss(pred_projected, demo_action_t, reduction="none")
        .reshape(num_samples, -1)
        .mean(dim=1)
    )
    final_prior_loss_vec = torch.zeros_like(final_action_loss_vec)
    final_norm_loss_vec = F.mse_loss(
        z_final_flat, torch.zeros_like(z_final_flat), reduction="none"
    ).mean(dim=1)
    final_loss_vec = (
        final_action_loss_vec
        + float(lambda_actor_prior) * final_prior_loss_vec
        + float(lambda_norm) * final_norm_loss_vec
    )

    if emit_logs:
        logger.info(
            "[invert_fixed_point] exact forward-Euler inverse approximation uses "
            f"model.num_inference_steps={reverse_steps}, fixed_point_iters={fixed_point_iters}"
        )

    stats_list: List[Dict[str, float]] = []
    for sample_idx in range(num_samples):
        if emit_logs:
            logger.info(
                f"[invert_fixed_point] sample {sample_idx + 1}/{num_samples} "
                f"action_loss={float(final_action_loss_vec[sample_idx].item()):.6f} "
                f"post_projection_action_loss={float(post_projection_action_loss_vec[sample_idx].item()):.6f} "
                f"prior_loss={float(final_prior_loss_vec[sample_idx].item()):.6f} "
                f"norm_loss={float(final_norm_loss_vec[sample_idx].item()):.6f} "
                f"step_residual_mean={float(residual_stack[sample_idx].mean().item()):.6f} "
                f"step_residual_max={float(residual_stack[sample_idx].max().item()):.6f}"
            )
        stats_list.append(
            {
                "loss": float(final_loss_vec[sample_idx].item()),
                "action_loss": float(final_action_loss_vec[sample_idx].item()),
                "post_projection_action_loss": float(
                    post_projection_action_loss_vec[sample_idx].item()
                ),
                "actor_prior_loss": float(final_prior_loss_vec[sample_idx].item()),
                "latent_norm_loss": float(final_norm_loss_vec[sample_idx].item()),
                "restart_index": 0.0,
                "inverse_step_residual_rmse_mean": float(residual_stack[sample_idx].mean().item()),
                "inverse_step_residual_rmse_max": float(residual_stack[sample_idx].max().item()),
            }
        )
    return z_final_flat, stats_list


def _infer_noise_target_batch_fixed_point(
    *,
    agent: InferenceAgent,
    decode_inputs_list: Sequence[Mapping[str, Any]],
    trainer: RLTrainer,
    observations: Sequence[Mapping[str, np.ndarray]],
    demo_action_norms: Sequence[np.ndarray],
    fixed_point_iters: int,
    lambda_actor_prior: float,
    lambda_norm: float,
) -> List[Tuple[np.ndarray, Dict[str, float]]]:
    num_samples = len(observations)
    if num_samples <= 0:
        raise ValueError("observations must not be empty")
    if len(demo_action_norms) != num_samples or len(decode_inputs_list) != num_samples:
        raise ValueError(
            "decode_inputs_list, observations, and demo_action_norms must have the same length"
        )
    demo_action_t = torch.stack(
        [
            torch.as_tensor(demo_action_norm, device=agent.device, dtype=torch.float32)
            for demo_action_norm in demo_action_norms
        ],
        dim=0,
    )
    z_final_flat, stats_list = _infer_noise_target_batch_fixed_point_core(
        agent=agent,
        decode_inputs_list=decode_inputs_list,
        demo_action_t=demo_action_t,
        fixed_point_iters=fixed_point_iters,
        lambda_actor_prior=lambda_actor_prior,
        lambda_norm=lambda_norm,
    )
    z_final_np = z_final_flat.detach().cpu().numpy()
    return [
        (np.asarray(z_final_np[idx], dtype=np.float32), dict(stats_list[idx]))
        for idx in range(num_samples)
    ]


def _load_finetune_statistics(finetune_cfg: Any) -> Dict[str, Any]:
    data_path_cfg = getattr(finetune_cfg, "data_path")
    if isinstance(data_path_cfg, (str, Path)):
        first_data_path = Path(data_path_cfg)
    else:
        first_data_path = Path(list(data_path_cfg)[0])
    stats_root_cfg = getattr(finetune_cfg, "stats_data_path", None)
    stats_root = Path(stats_root_cfg) if stats_root_cfg else first_data_path
    stat_path = stats_root / "dataset_statistics_train.json"
    if not stat_path.exists():
        raise FileNotFoundError(f"dataset_statistics_train.json not found: {stat_path}")
    stats = json.loads(stat_path.read_text(encoding="utf-8"))
    dummy = object.__new__(FinetuneDataset)
    dummy.overwrite_stats = getattr(finetune_cfg, "overwrite_stats", "piper_stack")
    return FinetuneDataset._overwrite_statistics(dummy, stats)


def _normalize_action_chunk(action_chunk: np.ndarray, stats: Mapping[str, Any]) -> np.ndarray:
    return np.asarray(
        FinetuneDataset._normalize(
            np.asarray(action_chunk, dtype=np.float32).copy(), stats["action"], method="q01q99"
        ),
        dtype=np.float32,
    )


def _resolve_target_build_settings(
    cfg: Any,
    *,
    data_roots: Sequence[str],
    inversion_sample_batch_size: Optional[int] = None,
    lambda_actor_prior: float = 1e-2,
    lambda_norm: float = 1e-4,
    force_original_only: bool = False,
    image_aug_seed_offset: int = 0,
) -> Dict[str, Any]:
    finetune_cfg = _make_human_finetune_cfg(cfg, data_roots)

    use_gripper_master = bool(getattr(finetune_cfg, "use_gripper_master", False))
    image_key = str(getattr(finetune_cfg, "image_key"))
    wrist_key = getattr(finetune_cfg, "wrist_key", None)
    extension = str(
        getattr(
            finetune_cfg,
            "extension",
            _cfg_get(_cfg_get(cfg, "unisteer_server", None), "image_extension", "jpg"),
        )
    )
    action_future_size = int(getattr(finetune_cfg, "action_future_size"))
    min_valid_action = int(getattr(finetune_cfg, "min_valid_action", 1))
    min_valid_state = int(getattr(finetune_cfg, "min_valid_state", 1))

    inverse_cfg = _cfg_get(cfg, "unisteer_inverse_sft", None)
    image_aug_cfg = _cfg_get(inverse_cfg, "image_aug", None)
    inversion_method = str(_cfg_get(inverse_cfg, "inversion_method", "fixed_point")).strip().lower()
    if inversion_method not in {"fixed_point", "fixed-point", "fp"}:
        raise ValueError(
            f"Unsupported unisteer_inverse_sft.inversion_method={inversion_method!r}; expected 'fixed_point'"
        )
    noise_parameterization = "repeat"
    noise_projection_steps = 1
    if has_explicit_openpi_policy_type(cfg):
        noise_layout = resolve_openpi_noise_layout(cfg)
        noise_parameterization = str(noise_layout.parameterization)
        noise_projection_steps = int(noise_layout.projection_steps)

    fixed_point_iters = int(_cfg_get(inverse_cfg, "fixed_point_iters", 16))
    if inversion_sample_batch_size is None:
        inversion_sample_batch_size = int(_cfg_get(inverse_cfg, "sample_batch_size", 128))
    sample_batch_size = max(1, int(inversion_sample_batch_size))

    enable_image_cache = bool(getattr(finetune_cfg, "enable_image_cache", True))
    image_cache_max_trajs = int(getattr(finetune_cfg, "image_cache_max_trajs", 64))
    if image_cache_max_trajs < 0:
        raise ValueError(f"image_cache_max_trajs must be >= 0, got {image_cache_max_trajs}")

    image_aug_enabled = bool(_cfg_get(image_aug_cfg, "enabled", False))
    image_aug_mode = str(_cfg_get(image_aug_cfg, "mode", "sft")).strip().lower()
    num_aug_views = int(
        _cfg_get(image_aug_cfg, "num_aug_views", _cfg_get(image_aug_cfg, "num_views", 0))
    )
    include_original_view = bool(_cfg_get(image_aug_cfg, "include_original", True))
    if force_original_only:
        image_aug_enabled = False
        include_original_view = True
    if not image_aug_enabled:
        num_aug_views = 0
    image_aug_seed = int(_cfg_get(image_aug_cfg, "seed", int(getattr(cfg, "seed", 0)))) + int(
        image_aug_seed_offset
    )
    image_aug_num_workers = max(0, int(_cfg_get(image_aug_cfg, "num_workers", 0)))
    if force_original_only or (not image_aug_enabled):
        image_aug_num_workers = 0
    max_pending_aug_views = max(
        sample_batch_size,
        int(
            _cfg_get(
                image_aug_cfg,
                "max_pending_views",
                max(sample_batch_size * 2, image_aug_num_workers * 2),
            )
        ),
    )
    if image_aug_enabled and image_aug_mode != "sft":
        raise ValueError(
            f"Unsupported unisteer_inverse_sft.image_aug.mode={image_aug_mode!r}; expected 'sft'"
        )
    if (not include_original_view) and num_aug_views <= 0:
        raise ValueError(
            "At least one view is required: enable include_original or set num_aug_views > 0"
        )

    return {
        "finetune_cfg": finetune_cfg,
        "use_gripper_master": use_gripper_master,
        "image_key": image_key,
        "wrist_key": wrist_key,
        "extension": extension,
        "action_future_size": action_future_size,
        "min_valid_action": min_valid_action,
        "min_valid_state": min_valid_state,
        "sample_batch_size": sample_batch_size,
        "noise_parameterization": noise_parameterization,
        "noise_projection_steps": noise_projection_steps,
        "fixed_point_iters": fixed_point_iters,
        "lambda_actor_prior": float(lambda_actor_prior),
        "lambda_norm": float(lambda_norm),
        "image_aug_enabled": image_aug_enabled,
        "enable_image_cache": enable_image_cache,
        "image_cache_max_trajs": image_cache_max_trajs,
        "num_aug_views": num_aug_views,
        "include_original_view": include_original_view,
        "image_aug_seed": image_aug_seed,
        "image_aug_num_workers": image_aug_num_workers,
        "max_pending_aug_views": max_pending_aug_views,
        "force_original_only": bool(force_original_only),
    }


def _collect_human_target_manifest(
    *,
    data_roots: Sequence[str],
    settings: Mapping[str, Any],
    sample_limit: Optional[int],
    sample_seed: Optional[int],
) -> Dict[str, Any]:
    base_sample_info = _collect_human_base_sample_manifest(
        data_roots=data_roots, settings=settings, sample_limit=sample_limit, sample_seed=sample_seed
    )
    base_samples = base_sample_info["base_samples"]

    manifest: List[Dict[str, Any]] = []
    num_target_views = 0
    for sample in base_samples:
        view_specs = _make_tensor_observation_view_specs(
            include_original=bool(settings["include_original_view"]),
            num_aug_views=int(settings["num_aug_views"]),
            image_aug_enabled=bool(settings["image_aug_enabled"]),
            image_aug_seed=int(settings["image_aug_seed"]),
            sample_seed_offset=int(sample["global_sample_id"]) - 1,
        )
        num_target_views += len(view_specs)
        manifest.append(
            {
                "global_sample_id": int(sample["global_sample_id"]),
                "traj_dir": str(sample["traj_dir"]),
                "step_index": int(sample["step_index"]),
                "task_description": str(sample["task_description"]),
                "action_norm": np.asarray(sample["action_norm"], dtype=np.float32),
                "view_specs": list(view_specs),
            }
        )

    return {
        "manifest": manifest,
        "num_human_samples": int(base_sample_info["num_human_samples"]),
        "num_available_human_samples": int(base_sample_info["num_available_human_samples"]),
        "num_target_views": int(num_target_views),
    }


def _collect_human_base_sample_manifest(
    *,
    data_roots: Sequence[str],
    settings: Mapping[str, Any],
    sample_limit: Optional[int],
    sample_seed: Optional[int],
) -> Dict[str, Any]:
    finetune_cfg = settings["finetune_cfg"]
    action_stats = _load_finetune_statistics(finetune_cfg)
    traj_dirs = _discover_traj_dirs(data_roots)

    base_samples: List[Dict[str, Any]] = []
    for traj_dir in traj_dirs:
        meta_payload = _load_meta(traj_dir)
        if "human_collect" not in meta_payload:
            raise KeyError(f"Missing 'human_collect' in {traj_dir / 'meta.json'}")
        if not bool(meta_payload["human_collect"]):
            continue

        _, action = load_traj_proprio_action(
            traj_dir, use_gripper_master=bool(settings["use_gripper_master"])
        )
        num_steps = _count_num_steps(
            traj_dir, image_key=str(settings["image_key"]), extension=str(settings["extension"])
        )
        if action.shape[0] != num_steps:
            raise ValueError(
                f"Action / image length mismatch under {traj_dir}: action={action.shape[0]} num_steps={num_steps}"
            )

        action_indices = np.arange(
            int(settings["min_valid_state"]) - 1,
            num_steps + int(settings["action_future_size"]) - int(settings["min_valid_action"]),
        )
        action_indices = sliding_window_view(action_indices, int(settings["action_future_size"]), 0)
        action_indices = np.clip(action_indices, 0, num_steps - 1)

        task_description = _load_task_description(traj_dir)
        for sample_idx in range(int(action_indices.shape[0])):
            indices = action_indices[sample_idx]
            step_index = int(indices[0])
            action_norm = _normalize_action_chunk(action[indices], action_stats)
            base_samples.append(
                {
                    "traj_dir": str(traj_dir),
                    "step_index": step_index,
                    "task_description": task_description,
                    "action_norm": np.asarray(action_norm, dtype=np.float32),
                }
            )

    num_available_human_samples = len(base_samples)
    if not base_samples:
        raise RuntimeError("No human decision-chunk samples found under the provided data roots")
    if sample_limit is not None:
        sample_limit = int(sample_limit)
        if sample_limit < 0:
            raise ValueError(f"sample_limit must be >= 0, got {sample_limit}")
        if sample_limit > 0 and len(base_samples) > sample_limit:
            rng = random.Random(
                int(sample_seed if sample_seed is not None else settings["image_aug_seed"])
            )
            base_samples = rng.sample(base_samples, sample_limit)

    selected_samples: List[Dict[str, Any]] = []
    for global_sample_id, sample in enumerate(base_samples, start=1):
        selected_samples.append(
            {
                "global_sample_id": int(global_sample_id),
                "traj_dir": str(sample["traj_dir"]),
                "step_index": int(sample["step_index"]),
                "task_description": str(sample["task_description"]),
                "action_norm": np.asarray(sample["action_norm"], dtype=np.float32),
            }
        )

    return {
        "base_samples": selected_samples,
        "num_human_samples": int(len(selected_samples)),
        "num_available_human_samples": int(num_available_human_samples),
    }


def _freeze_agent_for_inversion(agent: InferenceAgent) -> None:
    agent.policy.eval()
    for param in agent.policy.parameters():
        param.requires_grad_(False)


def _infer_actor_target_batch_from_tensor_views(
    *,
    agent: InferenceAgent,
    trainer: RLTrainer,
    tensor_views: Sequence[Mapping[str, Any]],
    settings: Mapping[str, Any],
) -> Dict[str, Any]:
    if not tensor_views:
        raise ValueError("tensor_views must not be empty")

    observations_t, decode_inputs_list = _build_unisteer_batch_tensors_and_inputs(
        agent, tensor_views, device=trainer.device
    )
    demo_action_t = torch.stack(
        [
            torch.as_tensor(item["sample"]["action_norm"], device=agent.device, dtype=torch.float32)
            for item in tensor_views
        ],
        dim=0,
    )

    target_noise_full_t, stats_list = _infer_noise_target_batch_fixed_point_core(
        agent=agent,
        decode_inputs_list=decode_inputs_list,
        demo_action_t=demo_action_t,
        fixed_point_iters=int(settings["fixed_point_iters"]),
        lambda_actor_prior=float(settings["lambda_actor_prior"]),
        lambda_norm=float(settings["lambda_norm"]),
    )
    target_noise_t = project_full_noise_to_actor_torch(
        target_noise_full_t,
        layout=agent.unisteer_noise_layout,
        device=agent.device,
        dtype=torch.float32,
    )
    if int(target_noise_t.shape[1]) != int(trainer.noise_action_dim):
        raise ValueError(
            f"Projected noise target dim mismatch: got {int(target_noise_t.shape[1])}, "
            f"expected trainer.noise_action_dim={int(trainer.noise_action_dim)}"
        )

    return {
        "observations": observations_t,
        "target_noise_actions": target_noise_t,
        "stats": stats_list,
    }


def _infer_actor_target_entries_from_tensor_views(
    *,
    agent: InferenceAgent,
    trainer: RLTrainer,
    tensor_views: Sequence[Mapping[str, Any]],
    settings: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    batch_payload = _infer_actor_target_batch_from_tensor_views(
        agent=agent, trainer=trainer, tensor_views=tensor_views, settings=settings
    )
    observations_t = batch_payload["observations"]
    target_noise_t = batch_payload["target_noise_actions"]
    stats_list = batch_payload["stats"]

    pixels = observations_t["pixels"].detach().cpu().permute(0, 2, 3, 1).unsqueeze(-1).numpy()
    state = observations_t["state"].detach().cpu().unsqueeze(-1).numpy()
    noise_target = target_noise_t.detach().cpu().numpy()

    target_entries: List[Dict[str, Any]] = []
    for idx, (item, stats) in enumerate(zip(tensor_views, stats_list)):
        sample = item["sample"]
        entry: Dict[str, Any] = {
            "global_sample_id": int(sample["global_sample_id"]),
            "traj_dir": str(sample["traj_dir"]),
            "step_index": int(sample["step_index"]),
            "augment_index": int(item["augment_index"]),
            "is_augmented": bool(item["is_augmented"]),
            "image_aug_seed": item["image_aug_seed"],
            "pixels": np.ascontiguousarray(pixels[idx].astype(np.uint8, copy=False)),
            "state": np.ascontiguousarray(state[idx].astype(np.float32, copy=False)),
            "noise_target": np.ascontiguousarray(
                noise_target[idx].astype(np.float32, copy=False)
            ).reshape(-1),
            "action_loss": float(stats["action_loss"]),
        }
        for key in (
            "loss",
            "post_projection_action_loss",
            "actor_prior_loss",
            "latent_norm_loss",
            "inverse_step_residual_rmse_mean",
            "inverse_step_residual_rmse_max",
        ):
            if key in stats:
                entry[key] = float(stats[key])
        target_entries.append(entry)
    return target_entries


def build_actor_targets_in_memory(
    cfg: Any,
    *,
    data_roots: Sequence[str],
    trainer: RLTrainer,
    agent: InferenceAgent,
    inversion_sample_batch_size: Optional[int] = None,
    lambda_actor_prior: float = 1e-2,
    lambda_norm: float = 1e-4,
    force_original_only: bool = False,
    sample_limit: Optional[int] = None,
    sample_seed: Optional[int] = None,
    image_aug_seed_offset: int = 0,
) -> Dict[str, Any]:
    settings = _resolve_target_build_settings(
        cfg,
        data_roots=data_roots,
        inversion_sample_batch_size=inversion_sample_batch_size,
        lambda_actor_prior=lambda_actor_prior,
        lambda_norm=lambda_norm,
        force_original_only=force_original_only,
        image_aug_seed_offset=image_aug_seed_offset,
    )
    manifest_info = _collect_human_target_manifest(
        data_roots=data_roots, settings=settings, sample_limit=sample_limit, sample_seed=sample_seed
    )
    manifest = manifest_info["manifest"]
    if not manifest:
        raise RuntimeError("No target samples found for in-memory inverse build")

    _freeze_agent_for_inversion(agent)

    logger.info(
        f"[invert_memory] starting inverse build | num_base_samples={manifest_info['num_human_samples']} "
        f"| num_target_views={manifest_info['num_target_views']} | target_batch_size={int(settings['sample_batch_size'])} "
        f"| noise_parameterization={settings['noise_parameterization']} "
        f"| noise_projection_steps={int(settings['noise_projection_steps'])} "
        f"| image_aug_enabled={bool(settings['image_aug_enabled'])}"
    )

    proprio_cache: Dict[str, np.ndarray] = {}
    pending_views: List[Dict[str, Any]] = []
    pending_futures: Dict[Future, Dict[str, Any]] = {}
    target_entries: List[Dict[str, Any]] = []
    num_target_views = 0
    image_cache = TrajectoryImageArrayCache(
        enabled=bool(settings["enable_image_cache"]),
        max_trajs=int(settings["image_cache_max_trajs"]),
    )

    def flush_pending(*, final: bool = False) -> None:
        nonlocal num_target_views
        batch_size = int(settings["sample_batch_size"])
        while pending_views and (final or len(pending_views) >= batch_size):
            current_batch = pending_views[:batch_size]
            del pending_views[:batch_size]
            current_entries = _infer_actor_target_entries_from_tensor_views(
                agent=agent, trainer=trainer, tensor_views=current_batch, settings=settings
            )
            target_entries.extend(current_entries)
            num_target_views += len(current_entries)

    def collect_augmented_views(*, executor_final: bool = False) -> None:
        if not pending_futures:
            return
        if executor_final:
            done_futures = list(pending_futures.keys())
        else:
            done_futures, _ = wait(list(pending_futures.keys()), return_when=FIRST_COMPLETED)
        for future in done_futures:
            metadata = pending_futures.pop(future)
            pending_views.append({**future.result(), **metadata})
        flush_pending(final=False)

    image_aug_num_workers = int(settings["image_aug_num_workers"])
    image_aug_executor = (
        ThreadPoolExecutor(max_workers=image_aug_num_workers) if image_aug_num_workers > 1 else None
    )

    for sample in manifest:
        traj_key = str(sample["traj_dir"])
        traj_dir = Path(traj_key)
        if traj_key not in proprio_cache:
            proprio_cache[traj_key], _ = load_traj_proprio_action(
                traj_dir, use_gripper_master=bool(settings["use_gripper_master"])
            )
        raw_observation = _load_raw_observation(
            traj_dir=traj_dir,
            step_index=int(sample["step_index"]),
            proprio_series=proprio_cache[traj_key],
            image_key=str(settings["image_key"]),
            wrist_key=settings["wrist_key"],
            extension=str(settings["extension"]),
            task_description=str(sample["task_description"]),
            image_cache=image_cache,
        )
        for view_spec in sample["view_specs"]:
            metadata = {"sample": sample}
            if image_aug_executor is None:
                pending_views.append(
                    {
                        **_build_tensor_observation_view(
                            raw_observation=raw_observation,
                            augment_index=int(view_spec["augment_index"]),
                            is_augmented=bool(view_spec["is_augmented"]),
                            image_aug_seed=view_spec["image_aug_seed"],
                        ),
                        **metadata,
                    }
                )
            else:
                future = image_aug_executor.submit(
                    _build_tensor_observation_view,
                    raw_observation=raw_observation,
                    augment_index=int(view_spec["augment_index"]),
                    is_augmented=bool(view_spec["is_augmented"]),
                    image_aug_seed=view_spec["image_aug_seed"],
                )
                pending_futures[future] = metadata
                while len(pending_futures) >= int(settings["max_pending_aug_views"]):
                    collect_augmented_views(executor_final=False)
        flush_pending(final=False)

    collect_augmented_views(executor_final=True)
    if image_aug_executor is not None:
        image_aug_executor.shutdown(wait=True)
    flush_pending(final=True)

    logger.info(
        f"[invert_memory] complete | num_target_views={int(num_target_views)} "
        f"| num_base_samples={int(manifest_info['num_human_samples'])}"
    )
    return {
        "num_human_samples": int(manifest_info["num_human_samples"]),
        "num_available_human_samples": int(manifest_info["num_available_human_samples"]),
        "num_target_views": int(num_target_views),
        "force_original_only": bool(force_original_only),
        "sample_limit": None if sample_limit is None else int(sample_limit),
        "sample_seed": None if sample_seed is None else int(sample_seed),
        "image_aug_seed_offset": int(image_aug_seed_offset),
        "target_entries": target_entries,
    }
