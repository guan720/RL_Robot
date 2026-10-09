from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Optional, Sequence

from loguru import logger
import numpy as np
from PIL import Image
import torch
from torch.nn import functional as F

from src.dataset.dataset import (
    load_traj_image_frame_chw_uint8,
    load_traj_proprio_action,
    resolve_traj_image_array_path,
)
from src.tool.binary_reward import BINARY_REWARD_BACKEND, validate_binary_reward_sidecar
from src.tool.unisteer_actor_supervision import build_actor_targets_in_memory
from src.trainer.RLTrainer import (
    RLTrainer,
    batch_unisteer_observations_to_torch,
    normalize_unisteer_observation,
)

if TYPE_CHECKING:
    from src.agent.inference_agent import InferenceAgent


class _TerminalProgressBar:
    def __init__(self, *, label: str, total: int):
        self.label = str(label)
        self.total = max(1, int(total))
        self.width = 30
        self.started_at = time.time()
        self._last_render_len = 0
        self._last_render_time = 0.0
        self._last_completed = 0
        self._min_refresh_sec = 0.2
        self._min_refresh_steps = 10

    def update(self, completed: int, *, force: bool = False) -> None:
        completed = max(0, min(int(completed), self.total))
        now = time.time()
        if not force and completed < self.total:
            if completed != 1:
                enough_time = (now - self._last_render_time) >= self._min_refresh_sec
                enough_steps = (completed - self._last_completed) >= self._min_refresh_steps
                if not (enough_time or enough_steps):
                    return
        frac = completed / float(self.total)
        filled = int(self.width * frac)
        bar = "#" * filled + "-" * (self.width - filled)
        elapsed = now - self.started_at
        line = (
            f"[{self.label}] train [{bar}] "
            f"{completed}/{self.total} ({frac * 100.0:5.1f}%) "
            f"elapsed {elapsed:6.1f}s"
        )
        pad = max(0, self._last_render_len - len(line))
        sys.stderr.write(line + (" " * pad))
        sys.stderr.flush()
        self._last_render_len = len(line)
        self._last_render_time = now
        self._last_completed = completed

    def close(self) -> None:
        self.update(self.total, force=True)
        sys.stderr.write("\n")
        sys.stderr.flush()


class SFTReplayBuffer:
    """Replay buffer for actor SFT samples: observation -> target noise."""

    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        if self.capacity <= 0:
            raise ValueError(f"SFTReplayBuffer capacity must be positive, got {self.capacity}")
        self.size = 0
        self.ptr = 0
        self.lock = threading.Lock()

        self.obs_pixels: Optional[np.ndarray] = None
        self.obs_state: Optional[np.ndarray] = None
        self.target_noise_actions: Optional[np.ndarray] = None

    def _maybe_init(self, observation: Mapping[str, Any], target_noise_action: np.ndarray) -> None:
        if self.obs_pixels is not None:
            return
        obs = normalize_unisteer_observation(observation)
        self.obs_pixels = np.empty((self.capacity, *obs["pixels"].shape), dtype=np.uint8)
        self.obs_state = np.empty((self.capacity, *obs["state"].shape), dtype=np.float32)
        self.target_noise_actions = np.empty(
            (self.capacity, target_noise_action.size), dtype=np.float32
        )

    def add(self, *, observation: Mapping[str, Any], target_noise_action: Any) -> None:
        obs = normalize_unisteer_observation(observation)
        target_np = _flatten_float32(target_noise_action, "target_noise_action")
        with self.lock:
            self._maybe_init(obs, target_np)
            assert self.obs_pixels is not None
            assert self.obs_state is not None
            assert self.target_noise_actions is not None
            idx = self.ptr
            self.obs_pixels[idx] = obs["pixels"]
            self.obs_state[idx] = obs["state"]
            self.target_noise_actions[idx] = target_np
            self.ptr = (self.ptr + 1) % self.capacity
            self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int) -> Dict[str, Any]:
        with self.lock:
            if self.size == 0:
                raise RuntimeError("SFTReplayBuffer is empty")
            assert self.obs_pixels is not None
            assert self.obs_state is not None
            assert self.target_noise_actions is not None

            batch_size = int(batch_size)
            if batch_size <= 0:
                raise ValueError(f"batch_size must be positive, got {batch_size}")

            indices = np.random.randint(0, self.size, size=batch_size)
            return {
                "observations": {
                    "pixels": self.obs_pixels[indices],
                    "state": self.obs_state[indices],
                },
                "target_noise_actions": self.target_noise_actions[indices],
            }


class HumanSFTSourceBuffer:
    """Long-lived source set for dynamic actor-SFT augmentation."""

    def __init__(self):
        self.lock = threading.Lock()
        self.traj_dirs: List[str] = []
        self._traj_dir_set: set[str] = set()

    def _trim_to_capacity_locked(self, max_trajectories: int) -> int:
        if int(max_trajectories) <= 0:
            return 0
        overflow = len(self.traj_dirs) - int(max_trajectories)
        if overflow <= 0:
            return 0
        removed = self.traj_dirs[:overflow]
        del self.traj_dirs[:overflow]
        for traj_dir in removed:
            self._traj_dir_set.discard(traj_dir)
        return len(removed)

    def add_traj_dirs(
        self, traj_dirs: Sequence[Path], *, max_trajectories: int = 0
    ) -> tuple[int, int]:
        added = 0
        evicted = 0
        with self.lock:
            for traj_dir in traj_dirs:
                resolved = str(Path(traj_dir).expanduser().resolve())
                if resolved in self._traj_dir_set:
                    continue
                self._traj_dir_set.add(resolved)
                self.traj_dirs.append(resolved)
                added += 1
            evicted = self._trim_to_capacity_locked(int(max_trajectories))
        return added, evicted

    def snapshot(self) -> List[str]:
        with self.lock:
            return list(self.traj_dirs)

    @property
    def size(self) -> int:
        with self.lock:
            return len(self.traj_dirs)


def _decode_image_bytes(data: bytes) -> np.ndarray:
    pil_img = Image.open(io.BytesIO(data)).convert("RGB")
    img_array = np.array(pil_img, dtype=np.uint8)
    return np.transpose(img_array, (2, 0, 1))


def _image_to_chw_uint8(value: Any, *, field_name: str) -> np.ndarray:
    if value is None:
        raise ValueError(f"{field_name} is required")

    if isinstance(value, (bytes, bytearray)):
        arr = _decode_image_bytes(bytes(value))
    elif isinstance(value, str):
        path = Path(value).expanduser()
        arr = np.transpose(np.array(Image.open(path).convert("RGB"), dtype=np.uint8), (2, 0, 1))
    else:
        arr = np.asarray(value)
        if arr.ndim == 4 and arr.shape[0] == 1:
            arr = arr[0]
        if arr.ndim != 3:
            raise ValueError(f"{field_name} must be rank-3 image data, got shape={list(arr.shape)}")
        if arr.shape[0] in (1, 3):
            pass
        elif arr.shape[-1] in (1, 3):
            arr = np.transpose(arr, (2, 0, 1))
        else:
            raise ValueError(
                f"{field_name} must be CHW or HWC image data, got shape={list(arr.shape)}"
            )

    arr = np.asarray(arr, dtype=np.uint8)
    if arr.shape[0] == 1:
        arr = np.repeat(arr, 3, axis=0)
    if arr.shape[0] != 3:
        raise ValueError(
            f"{field_name} must have 3 channels after conversion, got shape={list(arr.shape)}"
        )
    return arr


def _normalize_state(state: Any) -> np.ndarray:
    arr = np.asarray(state, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr[:, None]
    elif arr.ndim == 2 and arr.shape[-1] == 1:
        pass
    else:
        raise ValueError(f"UniSteer state must have shape [D] or [D, 1], got {list(arr.shape)}")
    return np.ascontiguousarray(arr.astype(np.float32, copy=False))


def _flatten_float32(value: Any, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        raise ValueError(f"{name} must not be empty")
    return arr


def _cfg_get(cfg: Any, key: str, default: Any = None) -> Any:
    if cfg is None:
        return default
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return getattr(cfg, key, default)


class UniSteerTrainer:
    def __init__(
        self,
        cfg: Any,
        *,
        server_cfg: Any,
        trainer: RLTrainer,
        agent: "InferenceAgent",
        checkpoint_path_getter: Optional[Callable[[], Optional[str]]] = None,
    ):
        self.cfg = cfg
        self.server_cfg = server_cfg
        self.trainer = trainer
        self.agent = agent
        self._checkpoint_path_getter = checkpoint_path_getter or (lambda: None)

        finetune_cfg = getattr(getattr(self.cfg, "data", None), "finetune", None)
        self.unisteer_use_gripper_master = bool(getattr(finetune_cfg, "use_gripper_master", False))
        self.unisteer_discount_horizon = self.server_cfg.resolved_discount_horizon(self.cfg)

        unisteer_cfg = _cfg_get(self.cfg, "unisteer", {})
        self.actor_sft_lr = float(_cfg_get(unisteer_cfg, "actor_sft_lr", 5e-5))
        self.actor_sft_opt: Optional[torch.optim.Optimizer] = None
        self.sft_buffer = SFTReplayBuffer(self.server_cfg.sft_buffer_capacity)
        self.human_sft_source_buffer = HumanSFTSourceBuffer()
        self.dynamic_sft_aug_round = 0

    def _current_unisteer_checkpoint_label(self) -> str:
        return str(self._checkpoint_path_getter() or "in_memory")

    def sft_image_cfg(self) -> Dict[str, Any]:
        finetune_cfg = getattr(getattr(self.cfg, "data", None), "finetune", None)
        return {
            "image_key": str(getattr(finetune_cfg, "image_key", self.server_cfg.image_key)),
            "wrist_key": getattr(finetune_cfg, "wrist_key", self.server_cfg.wrist_key),
            "extension": str(getattr(finetune_cfg, "extension", self.server_cfg.image_extension)),
            "use_wrist": bool(getattr(self.cfg, "use_wrist", False)),
        }

    def image_aug_cfg(self) -> Any:
        inverse_cfg = getattr(self.cfg, "unisteer_inverse_sft", None)
        return getattr(inverse_cfg, "image_aug", None)

    def dynamic_sft_aug_enabled(self) -> bool:
        image_aug_cfg = self.image_aug_cfg()
        if not bool(getattr(image_aug_cfg, "enabled", False)):
            return False
        return bool(getattr(image_aug_cfg, "dynamic_aug", False))

    def dynamic_sft_aug_num_samples(self) -> int:
        value = int(getattr(self.image_aug_cfg(), "dynamic_aug_num_samples", 0))
        if value < 0:
            raise ValueError(
                f"unisteer_inverse_sft.image_aug.dynamic_aug_num_samples must be >= 0, got {value}"
            )
        return value

    def dynamic_sft_aug_buffer_size(self) -> int:
        value = int(getattr(self.image_aug_cfg(), "dynamic_aug_buffer_size", 0))
        if value < 0:
            raise ValueError(
                f"unisteer_inverse_sft.image_aug.dynamic_aug_buffer_size must be >= 0, got {value}"
            )
        return value

    def build_human_rl_actor_targets(self, human_dirs: Sequence[Path]) -> Dict[str, Any]:
        return build_actor_targets_in_memory(
            self.cfg,
            data_roots=[str(path) for path in human_dirs],
            trainer=self.trainer,
            agent=self.agent,
            lambda_actor_prior=self.server_cfg.actor_lambda_actor_prior,
            lambda_norm=self.server_cfg.actor_lambda_norm,
            force_original_only=True,
        )

    def build_human_sft_original_actor_targets(self, human_dirs: Sequence[Path]) -> Dict[str, Any]:
        return build_actor_targets_in_memory(
            self.cfg,
            data_roots=[str(path) for path in human_dirs],
            trainer=self.trainer,
            agent=self.agent,
            lambda_actor_prior=self.server_cfg.actor_lambda_actor_prior,
            lambda_norm=self.server_cfg.actor_lambda_norm,
            force_original_only=True,
        )

    def build_human_sft_actor_targets(self, human_dirs: Sequence[Path]) -> Dict[str, Any]:
        return build_actor_targets_in_memory(
            self.cfg,
            data_roots=[str(path) for path in human_dirs],
            trainer=self.trainer,
            agent=self.agent,
            lambda_actor_prior=self.server_cfg.actor_lambda_actor_prior,
            lambda_norm=self.server_cfg.actor_lambda_norm,
        )

    def build_dynamic_sft_actor_targets(self) -> Dict[str, Any]:
        source_dirs = self.human_sft_source_buffer.snapshot()
        if not source_dirs:
            raise RuntimeError("dynamic_aug is enabled but human SFT source buffer is empty")
        self.dynamic_sft_aug_round += 1
        round_id = int(self.dynamic_sft_aug_round)
        sample_limit = self.dynamic_sft_aug_num_samples()
        sample_seed = int(getattr(self.cfg, "seed", 0)) + round_id * 1_000_003
        return build_actor_targets_in_memory(
            self.cfg,
            data_roots=source_dirs,
            trainer=self.trainer,
            agent=self.agent,
            lambda_actor_prior=self.server_cfg.actor_lambda_actor_prior,
            lambda_norm=self.server_cfg.actor_lambda_norm,
            sample_limit=(sample_limit if sample_limit > 0 else None),
            sample_seed=sample_seed,
            image_aug_seed_offset=round_id * 1_000_003,
        )

    def ingest_sft_entries(
        self,
        entries: Sequence[Mapping[str, Any]],
        *,
        target_buffer: Optional[SFTReplayBuffer] = None,
    ) -> int:
        if not entries:
            return 0
        buffer = target_buffer or self.sft_buffer
        num_entries = 0
        for entry in entries:
            if "pixels" not in entry:
                raise KeyError("In-memory SFT target entry must contain pixels")
            buffer.add(
                observation={
                    "pixels": np.asarray(entry["pixels"], dtype=np.uint8),
                    "state": _normalize_state(entry["state"]),
                },
                target_noise_action=np.asarray(entry["noise_target"], dtype=np.float32).reshape(-1),
            )
            num_entries += 1
        return num_entries

    def _observation_from_actor_target_entry(
        self, *, entry: Mapping[str, Any]
    ) -> Dict[str, np.ndarray]:
        if "pixels" not in entry:
            raise KeyError("In-memory actor target entry must contain pixels")
        return {
            "pixels": np.asarray(entry["pixels"], dtype=np.uint8),
            "state": _normalize_state(entry["state"]),
        }

    def _load_traj_proprio_series(self, traj_dir: Path) -> np.ndarray:
        proprio, _ = load_traj_proprio_action(
            traj_dir, use_gripper_master=self.unisteer_use_gripper_master
        )
        return proprio.astype(np.float32)

    def _load_traj_task_instruction(self, traj_dir: Path) -> str:
        txt = traj_dir / "task_instruction.txt"
        if txt.exists():
            return txt.read_text(encoding="utf-8").strip()
        meta_json = traj_dir / "meta.json"
        if meta_json.exists():
            payload = json.loads(meta_json.read_text(encoding="utf-8"))
            task = str(payload.get("task", "")).strip()
            if task:
                return task
        raise FileNotFoundError(f"Could not find task instruction under {traj_dir}")

    def _load_traj_meta(self, traj_dir: Path) -> Dict[str, Any]:
        meta_path = traj_dir / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Missing trajectory meta.json under {traj_dir}")
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"Invalid trajectory meta payload in {meta_path}")
        return payload

    def _load_traj_raw_observation(
        self, traj_dir: Path, *, step_index: int, proprio_series: np.ndarray, task_description: str
    ) -> Dict[str, Any]:
        if step_index < 0 or step_index >= proprio_series.shape[0]:
            raise IndexError(
                f"step_index out of range for {traj_dir}: step_index={step_index}, num_steps={proprio_series.shape[0]}"
            )

        image_path = resolve_traj_image_array_path(traj_dir, self.server_cfg.image_key)
        if not image_path.is_file():
            raise FileNotFoundError(
                f"Missing primary trajectory image array for step_index={step_index}: {image_path}"
            )
        image = load_traj_image_frame_chw_uint8(traj_dir, self.server_cfg.image_key, step_index)

        wrist_image = None
        if self.server_cfg.wrist_key:
            wrist_path = resolve_traj_image_array_path(traj_dir, self.server_cfg.wrist_key)
            if wrist_path.is_file():
                wrist_image = load_traj_image_frame_chw_uint8(
                    traj_dir, self.server_cfg.wrist_key, step_index
                )

        return {
            "image": image,
            "image_wrist": wrist_image,
            "proprio": proprio_series[step_index].astype(np.float32).copy(),
            "task_description": task_description,
        }

    def _build_pixels_from_raw_observation(self, observation: Mapping[str, Any]) -> np.ndarray:
        image = _image_to_chw_uint8(observation["image"], field_name="image")
        image_t = torch.from_numpy(image[None, ...])

        wrist_t = None
        wrist_value = observation.get("image_wrist")
        if wrist_value is not None:
            wrist = _image_to_chw_uint8(wrist_value, field_name="image_wrist")
            wrist_t = torch.from_numpy(wrist[None, ...])

        pixels = self.agent.build_unisteer_pixels(image=image_t, image_wrist=wrist_t)
        return np.asarray(pixels, dtype=np.uint8)

    def _build_observation_from_explicit_state(
        self, *, state: Any, raw_observation: Mapping[str, Any]
    ) -> Dict[str, np.ndarray]:
        return {
            "pixels": self._build_pixels_from_raw_observation(raw_observation),
            "state": _normalize_state(state),
        }

    def _build_observation_from_raw(
        self, raw_observation: Mapping[str, Any]
    ) -> Dict[str, np.ndarray]:
        image = _image_to_chw_uint8(raw_observation["image"], field_name="image")
        image_t = torch.from_numpy(image[None, ...])

        wrist_t = None
        wrist_value = raw_observation.get("image_wrist")
        if wrist_value is not None:
            wrist = _image_to_chw_uint8(wrist_value, field_name="image_wrist")
            wrist_t = torch.from_numpy(wrist[None, ...])

        proprio = np.asarray(raw_observation["proprio"], dtype=np.float32).reshape(1, 1, -1)
        proprio_t = torch.from_numpy(proprio)
        task = [str(raw_observation["task_description"])]

        obs = self.agent.build_unisteer_observation(
            image=image_t, image_wrist=wrist_t, proprio=proprio_t, task_description=task
        )
        return {
            "pixels": np.asarray(obs["pixels"], dtype=np.uint8),
            "state": _normalize_state(obs["state"]),
        }

    def build_human_episode_payloads_from_target_entries(
        self, target_entries: Sequence[Mapping[str, Any]], *, request_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not target_entries:
            return []

        grouped_entries: Dict[str, List[Mapping[str, Any]]] = {}
        for entry in target_entries:
            traj_dir = str(entry.get("traj_dir", "")).strip()
            if not traj_dir:
                raise KeyError("In-memory actor target entry must contain traj_dir")
            grouped_entries.setdefault(traj_dir, []).append(entry)

        episode_payloads: List[Dict[str, Any]] = []
        fixed_discount = float(self.trainer.cfg.discount**self.unisteer_discount_horizon)
        for traj_dir_str, grouped in grouped_entries.items():
            traj_dir = Path(traj_dir_str).expanduser().resolve()
            original_entries = [
                entry for entry in grouped if not bool(entry.get("is_augmented", False))
            ]
            original_entries = sorted(
                original_entries,
                key=lambda item: (int(item["step_index"]), int(item.get("augment_index", 0))),
            )
            if not original_entries:
                raise RuntimeError(
                    f"No original-view actor targets found for {traj_dir}; "
                    "human RL replay requires unisteer_inverse_sft.image_aug.include_original=true"
                )

            reward_path = traj_dir / "unisteer_reward_result.json"
            if not reward_path.exists():
                raise FileNotFoundError(f"Missing UniSteer human reward sidecar: {reward_path}")
            reward_result = json.loads(reward_path.read_text(encoding="utf-8"))
            if not isinstance(reward_result, dict):
                raise TypeError(f"Invalid reward payload in {reward_path}")

            meta_payload = self._load_traj_meta(traj_dir)
            if "success" not in meta_payload:
                raise KeyError(f"Missing 'success' in trajectory meta.json under {traj_dir}")
            trajectory_success = bool(meta_payload["success"])

            decision_scores = reward_result.get("decision_scores") or {}
            summary = reward_result.get("summary") or {}
            reward_backend = str(summary.get("backend", ""))
            if reward_backend != BINARY_REWARD_BACKEND:
                raise ValueError(f"Unsupported reward backend {reward_backend!r} in {reward_path}")
            if bool(meta_payload.get("is_reset", False)):
                trajectory_success = False
            rewards = decision_scores.get("reward")
            decision_indices = decision_scores.get("decision_indices")
            if rewards is None or not isinstance(rewards, list):
                raise ValueError(f"Missing decision_scores.reward in {reward_path}")
            if len(rewards) != len(original_entries):
                raise ValueError(
                    f"Human reward length mismatch in {reward_path}: "
                    f"rewards={len(rewards)} original_targets={len(original_entries)}"
                )

            transition_discount = fixed_discount
            step_indices = [int(entry["step_index"]) for entry in original_entries]
            if decision_indices is not None:
                parsed_decision_indices = [int(v) for v in decision_indices]
                if parsed_decision_indices != step_indices:
                    raise ValueError(
                        f"Decision index mismatch between in-memory targets and {reward_path}: "
                        f"targets={step_indices} rewards={parsed_decision_indices}"
                    )
            validate_binary_reward_sidecar(
                summary=summary,
                decision_scores=decision_scores,
                success=trajectory_success,
                num_chunks=len(original_entries),
                final_decision_index=step_indices[-1],
            )

            proprio_series = self._load_traj_proprio_series(traj_dir)
            task_description = self._load_traj_task_instruction(traj_dir)
            final_frame_index = int(proprio_series.shape[0] - 1)
            final_raw_observation = self._load_traj_raw_observation(
                traj_dir,
                step_index=final_frame_index,
                proprio_series=proprio_series,
                task_description=task_description,
            )

            terminal_transition_idx = len(original_entries) - 1
            if trajectory_success and self.server_cfg.truncate_success_on_done_index:
                frame_done_index = summary.get("done_index")
                if frame_done_index is not None:
                    frame_done_index = int(frame_done_index)
                    mapped_idx = None
                    for idx, step_index in enumerate(step_indices):
                        if step_index <= frame_done_index:
                            mapped_idx = idx
                        else:
                            break
                    if mapped_idx is None:
                        raise ValueError(
                            f"Success done_index={frame_done_index} occurs before the first human decision "
                            f"step in {reward_path}"
                        )
                    terminal_transition_idx = int(mapped_idx)

            transitions: List[Dict[str, Any]] = []
            for idx, entry in enumerate(original_entries[: terminal_transition_idx + 1]):
                observation = self._observation_from_actor_target_entry(entry=entry)

                is_last_transition = idx == terminal_transition_idx
                is_terminal = bool(is_last_transition)
                if not is_terminal:
                    if is_last_transition:
                        next_observation = self._build_observation_from_raw(final_raw_observation)
                    else:
                        next_observation = self._observation_from_actor_target_entry(
                            entry=original_entries[idx + 1]
                        )
                    mask = 1.0
                else:
                    next_observation = self._build_observation_from_raw(final_raw_observation)
                    mask = 0.0

                transitions.append(
                    {
                        "observation": observation,
                        "next_observation": next_observation,
                        "noise_action": _flatten_float32(
                            entry["noise_target"], "noise_target"
                        ).tolist(),
                        "reward": float(rewards[idx]),
                        "mask": float(mask),
                        "discount": float(transition_discount),
                    }
                )

            episode_id = str(request_id or traj_dir.name)
            episode_payloads.append(
                {
                    "episode_id": f"{episode_id}:human:{traj_dir.name}",
                    "checkpoint_tag": f"{episode_id}_human_{traj_dir.name}_{int(time.time())}",
                    "trajectory_success": trajectory_success,
                    "transitions": transitions,
                }
            )

        return episode_payloads

    def _ensure_actor_sft_optimizer(self) -> torch.optim.Optimizer:
        if self.trainer.actor is None:
            raise RuntimeError("UniSteer actor SFT requires initialized UniSteer actor")
        if self.actor_sft_opt is None:
            self.actor_sft_opt = torch.optim.Adam(
                self.trainer.actor.parameters(), lr=self.actor_sft_lr
            )
        else:
            for group in self.actor_sft_opt.param_groups:
                group["lr"] = float(self.actor_sft_lr)
        return self.actor_sft_opt

    @staticmethod
    def _grad_norm(module: torch.nn.Module) -> float:
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

    def supervised_actor_step(
        self, observations: Mapping[str, Any], target_noise_actions: Any
    ) -> Dict[str, float]:
        if self.trainer.actor is None:
            raise RuntimeError("UniSteer actor SFT requires initialized UniSteer actor")
        optimizer = self._ensure_actor_sft_optimizer()

        obs_t = batch_unisteer_observations_to_torch(observations, self.trainer.device)
        target_np = np.asarray(target_noise_actions, dtype=np.float32)
        if target_np.ndim == 1:
            target_np = target_np[None, ...]
        elif target_np.ndim != 2:
            raise ValueError(
                f"target_noise_actions must have shape [A] or [B, A], got {list(target_np.shape)}"
            )

        if target_np.shape[1] != int(self.trainer.noise_action_dim):
            raise ValueError(
                f"target_noise_actions dim mismatch: got {target_np.shape[1]} "
                f"expected {self.trainer.noise_action_dim}"
            )

        target_t = torch.from_numpy(np.ascontiguousarray(target_np)).to(
            self.trainer.device, dtype=torch.float32
        )
        mean, _ = self.trainer.actor(obs_t)
        mean_action = torch.tanh(mean) * float(self.trainer.cfg.noise_action_limit)
        actor_supervised_loss = F.mse_loss(mean_action, target_t)

        optimizer.zero_grad(set_to_none=True)
        actor_supervised_loss.backward()
        actor_grad_norm = self._grad_norm(self.trainer.actor)
        optimizer.step()

        self.trainer.actor_sft_step += 1
        return {
            "step": float(self.trainer.actor_sft_step),
            "actor_supervised_loss": float(actor_supervised_loss.item()),
            "actor_grad_norm": float(actor_grad_norm),
        }

    def run_sft_updates(
        self, num_updates: int, *, source_buffer: Optional[SFTReplayBuffer] = None
    ) -> Dict[str, Any]:
        buffer = source_buffer or self.sft_buffer
        if int(num_updates) <= 0:
            return {"num_updates": 0, "num_target_entries": int(buffer.size), "train_metrics": {}}
        if buffer.size <= 0:
            raise RuntimeError("SFT buffer is empty")
        total_updates = int(num_updates)
        progress = _TerminalProgressBar(label="actor_sft", total=total_updates)
        metrics: Dict[str, Any] = {}
        for update_idx in range(total_updates):
            batch = buffer.sample(self.server_cfg.actor_sft_batch_size)
            metrics = self.supervised_actor_step(
                batch["observations"], batch["target_noise_actions"]
            )
            progress.update(update_idx + 1)
            if (
                update_idx == 0
                or (update_idx + 1) % max(1, int(self.server_cfg.actor_sft_log_every)) == 0
                or (update_idx + 1) == total_updates
            ):
                logger.info(
                    f"[actor_sft] step {update_idx + 1}/{total_updates} "
                    f"loss={metrics['actor_supervised_loss']:.6f} "
                    f"grad={metrics['actor_grad_norm']:.6f}"
                )
        progress.close()
        return {
            "num_updates": total_updates,
            "num_target_entries": int(buffer.size),
            "train_metrics": metrics,
        }
