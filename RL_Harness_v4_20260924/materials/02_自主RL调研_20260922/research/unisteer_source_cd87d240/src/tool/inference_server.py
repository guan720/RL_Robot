"""
Inference Server for original LeRobot PI0 normal-policy rollout.

The /act endpoint always returns the full action chunk as
float32[horizon_steps, action_dim]. The server does not maintain an
infer-side action queue and does not apply select_action() semantics.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
import io
import json
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import uuid

from flask import Flask, Response, request
from loguru import logger
import msgpack
import numpy as np
from PIL import Image
import torch

from src.dataset.dataset import get_traj_num_steps
from src.tool.binary_reward import BINARY_REWARD_BACKEND, build_binary_reward_sequence

try:
    from omegaconf import OmegaConf, open_dict
except Exception:  # pragma: no cover
    OmegaConf = None

    @contextmanager
    def open_dict(cfg):
        yield cfg


UNISTEER_SEGMENT_ROOT_NAME = ".unisteer_segments"
UNISTEER_ACTOR_CHECKPOINT_ENV = "UNISTEER_ACTOR_CHECKPOINT"


class InferenceServer:
    def __init__(self, cfg):
        with open_dict(cfg):
            cfg.gpu_id = 0
            cfg.multi_gpu = False

        self.cfg = cfg
        self._maybe_redirect_checkpoint()

        logger.info("Loading InferenceAgent...")
        from src.agent.inference_agent import InferenceAgent
        from src.agent.unisteer_actor_agent import UniSteerActorAgent

        self.agent = InferenceAgent(cfg)
        self.unisteer_actor = UniSteerActorAgent(
            cfg,
            device=self.agent.device,
            deterministic_by_default=bool(getattr(cfg, "unisteer_actor_deterministic", False)),
        )
        self.unisteer_actor_rollout_temperature = float(
            getattr(cfg, "unisteer_actor_rollout_temperature", 0.0)
        )
        if self.unisteer_actor_rollout_temperature < 0.0:
            raise ValueError(
                f"unisteer_actor_rollout_temperature must be non-negative, got {self.unisteer_actor_rollout_temperature}"
            )
        unisteer_server_cfg = getattr(self.cfg, "unisteer_server", None)
        self.unisteer_initial_rollout_bypass_actor = bool(
            getattr(unisteer_server_cfg, "initial_rollout_bypass_actor", False)
        )
        self.unisteer_num_initial_traj_collect = int(
            getattr(unisteer_server_cfg, "num_initial_traj_collect", 0)
        )
        if self.unisteer_num_initial_traj_collect < 0:
            raise ValueError(
                f"unisteer_server.num_initial_traj_collect must be non-negative, got "
                f"{self.unisteer_num_initial_traj_collect}"
            )
        unisteer_url = os.environ.get("UNISTEER_TRAIN_SERVER_URL") or getattr(
            self.cfg, "unisteer_train_server_url", None
        )
        self.unisteer_train_server_url = (
            self._validate_unisteer_url(unisteer_url) if unisteer_url else None
        )
        unisteer_actor_ckpt = os.environ.get(UNISTEER_ACTOR_CHECKPOINT_ENV) or getattr(
            self.cfg, "unisteer_actor_checkpoint_path", None
        )
        if unisteer_actor_ckpt:
            local_unisteer_ckpt = self._resolve_local_checkpoint_path(str(unisteer_actor_ckpt))
            self.unisteer_actor.load_checkpoint(
                local_unisteer_ckpt, expected_distribution="tanh_gaussian"
            )

        finetune_cfg = getattr(getattr(self.cfg, "data", None), "finetune", None)
        reward_backend = (
            str(getattr(unisteer_server_cfg, "reward_backend", BINARY_REWARD_BACKEND))
            .strip()
            .lower()
        )
        if reward_backend != BINARY_REWARD_BACKEND:
            raise ValueError(
                f"Unsupported UniSteer reward backend: {reward_backend}. "
                f"Expected: {BINARY_REWARD_BACKEND}."
            )
        self.unisteer_image_key = str(
            getattr(
                unisteer_server_cfg,
                "image_key",
                getattr(finetune_cfg, "image_key", "primary_image_crop"),
            )
        )
        self.unisteer_image_extension = str(
            getattr(
                unisteer_server_cfg, "image_extension", getattr(finetune_cfg, "extension", "jpg")
            )
        )
        self.inference_count = 0
        self.last_inference_time = None
        self._rollout_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None

        logger.info("InferenceServer initialized successfully")

    @staticmethod
    def _validate_unisteer_url(url: str) -> str:
        normalized = str(url).strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError(
                "unisteer_train_server_url must use http or https with a loopback host "
                "(localhost, 127.0.0.1, or ::1)"
            )
        return normalized

    def _should_initial_rollout_bypass_actor(self) -> bool:
        return (
            bool(self.unisteer_initial_rollout_bypass_actor)
            and int(self.unisteer_num_initial_traj_collect) > 0
            and self.unisteer_actor.ready
            and int(self.unisteer_actor.update_step) == 0
        )

    def _maybe_redirect_checkpoint(self) -> None:
        ckpt_path = os.environ.get("INFERENCE_CHECKPOINT") or getattr(
            self.cfg, "inference_checkpoint_path", None
        )
        if not ckpt_path:
            return
        local_ckpt = self._resolve_local_checkpoint_path(str(ckpt_path))
        with open_dict(self.cfg):
            self.cfg.inference_checkpoint_path = local_ckpt
        os.environ["INFERENCE_CHECKPOINT"] = local_ckpt

    @staticmethod
    def _resolve_local_checkpoint_path(ckpt_path: str) -> str:
        if not ckpt_path:
            raise ValueError("Empty ckpt_path")
        if urlparse(ckpt_path).scheme in {"http", "https"}:
            raise ValueError("Checkpoint must be an existing local filesystem path")
        try:
            return str(Path(ckpt_path).expanduser().resolve(strict=True))
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Checkpoint path does not exist: {ckpt_path}") from exc

    @staticmethod
    def decompress_image(compressed_bytes: bytes) -> np.ndarray:
        buffer = io.BytesIO(compressed_bytes)
        pil_img = Image.open(buffer).convert("RGB")
        img_array = np.array(pil_img)
        return np.transpose(img_array, (2, 0, 1))

    def _decode_standard_observation(self, decoded: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "image": self.decompress_image(decoded["o"]).reshape(1, 3, 224, 224),
            "image_wrist": self.decompress_image(decoded["w"]).reshape(1, 3, 224, 224)
            if "w" in decoded
            else None,
            "proprio": np.frombuffer(decoded["s"], dtype=np.float32).reshape(1, 1, 7),
            "task_description": decoded["t"],
        }

    @staticmethod
    def _parse_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        images = torch.tensor(payload["image"], dtype=torch.uint8)
        texts = [payload["task_description"]]
        proprio = torch.tensor(payload["proprio"], dtype=torch.float32)
        result = {
            "image": images,
            "proprio": proprio,
            "task_description": texts,
            "image_wrist": None,
        }
        if payload.get("image_wrist") is not None:
            result["image_wrist"] = torch.tensor(payload["image_wrist"], dtype=torch.uint8)
        return result

    def _reload_actor_checkpoint(self, checkpoint: str) -> str:
        local_ckpt = self._resolve_local_checkpoint_path(str(checkpoint))
        logger.info(f"Reloading UniSteer actor checkpoint: {local_ckpt}")
        self.unisteer_actor.load_checkpoint(local_ckpt, expected_distribution="tanh_gaussian")
        return local_ckpt

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

    @staticmethod
    def _load_traj_meta(traj_dir: Path) -> Dict[str, Any]:
        meta_json = traj_dir / "meta.json"
        if not meta_json.exists():
            return {}
        payload = json.loads(meta_json.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"Invalid meta.json payload under {traj_dir}")
        return payload

    def _build_binary_reward_result(
        self,
        *,
        request_id: str,
        trajectory_dir: Path,
        instruction: str,
        decision_indices: List[int],
    ) -> Dict[str, Any]:
        if not decision_indices:
            raise ValueError(
                f"Cannot build binary reward without decision indices under {trajectory_dir}"
            )

        meta_payload = self._load_traj_meta(trajectory_dir)
        reset_failure = bool(meta_payload.get("is_reset", False))
        trajectory_success = bool(meta_payload.get("success", False)) and not reset_failure
        rewards = build_binary_reward_sequence(
            num_chunks=len(decision_indices), success=trajectory_success
        )
        done_index = int(decision_indices[-1])
        failure_reason = None
        if not trajectory_success:
            failure_reason = str(meta_payload.get("failure_reason", "")).strip().lower() or None
            if reset_failure and failure_reason is None:
                failure_reason = "reset"
        success_scores = [
            bool(trajectory_success and idx == len(decision_indices) - 1)
            for idx in range(len(decision_indices))
        ]
        reward_sum = float(sum(rewards))
        return {
            "request_id": request_id,
            "instruction": instruction,
            "trajectory_dir": str(trajectory_dir),
            "frame_paths": [],
            "frame_timestamps": None,
            "metadata": dict(meta_payload),
            "decision_scores": {
                "decision_indices": [int(i) for i in decision_indices],
                "success": success_scores,
                "reward": rewards,
            },
            "summary": {
                "backend": BINARY_REWARD_BACKEND,
                "num_input_frames": int(
                    get_traj_num_steps(trajectory_dir, self.unisteer_image_key)
                ),
                "num_scored_frames": int(len(decision_indices)),
                "num_noise_chunks": int(len(decision_indices)),
                "reward_mode": BINARY_REWARD_BACKEND,
                "success_max": float(max(success_scores)),
                "reward_sum": reward_sum,
                "done": True,
                "done_index": done_index,
                "success": bool(trajectory_success),
                "failure_reason": failure_reason,
                "reset_failure": bool(reset_failure),
                "terminal": True,
            },
            "backend_result": {
                "backend": BINARY_REWARD_BACKEND,
                "success": bool(trajectory_success),
                "failure_reason": failure_reason,
                "reset_failure": bool(reset_failure),
                "decision_indices": [int(i) for i in decision_indices],
            },
        }

    @staticmethod
    def _reward_summary_success(summary: Dict[str, Any]) -> bool:
        if "success" in summary:
            return bool(summary["success"])
        return bool(summary.get("done")) and not bool(summary.get("reset_failure", False))

    @staticmethod
    def _discover_rollout_trajectory_dirs(root_dir: Path) -> List[Path]:
        if (root_dir / "meta.json").exists() or (root_dir / "unisteer_episode.msgpack").exists():
            return [root_dir.resolve()]
        discovered = {
            path.parent.resolve()
            for path in root_dir.rglob("meta.json")
            if UNISTEER_SEGMENT_ROOT_NAME not in path.parts
        }
        discovered.update(
            {
                path.parent.resolve()
                for path in root_dir.rglob("unisteer_episode.msgpack")
                if UNISTEER_SEGMENT_ROOT_NAME not in path.parts
            }
        )
        return sorted(discovered, key=lambda p: str(p))

    @staticmethod
    def _load_is_human_flags(traj_dir: Path) -> np.ndarray:
        is_human_path = traj_dir / "is_human.npy"
        if not is_human_path.exists():
            raise FileNotFoundError(f"Missing is_human.npy under {traj_dir}")
        flags = np.asarray(np.load(is_human_path)).reshape(-1)
        if int(flags.size) <= 0:
            raise ValueError(f"Empty is_human.npy under {traj_dir}")
        if not bool(np.all(np.isin(flags, [0, 1]))):
            raise ValueError(
                f"is_human.npy must contain only boolean or 0/1 values under {traj_dir}"
            )

        action_path = traj_dir / "action.npy"
        if not action_path.exists():
            raise FileNotFoundError(f"Missing action.npy under {traj_dir}")
        action = np.load(action_path, mmap_mode="r")
        if action.ndim < 1:
            raise ValueError(f"action.npy must have a time dimension under {traj_dir}")
        if int(flags.size) != int(action.shape[0]):
            raise ValueError(
                f"is_human.npy length {int(flags.size)} does not match "
                f"action.npy length {int(action.shape[0])} under {traj_dir}"
            )
        return flags.astype(bool, copy=False)

    @staticmethod
    def _find_contiguous_segments(flags: np.ndarray) -> List[Tuple[bool, int, int]]:
        segments: List[Tuple[bool, int, int]] = []
        start = 0
        current = bool(flags[0])
        for idx in range(1, int(flags.shape[0])):
            value = bool(flags[idx])
            if value == current:
                continue
            segments.append((current, start, idx))
            start = idx
            current = value
        segments.append((current, start, int(flags.shape[0])))
        return segments

    @staticmethod
    def _segment_output_dir(
        segment_root: Path, root_dir: Path, traj_dir: Path, segment_idx: int, is_human: bool
    ) -> Path:
        role = "human" if is_human else "model"
        relative_traj = traj_dir.resolve().relative_to(root_dir.resolve())
        if relative_traj == Path("."):
            relative_traj = Path(traj_dir.name)
        return (
            segment_root
            / relative_traj.parent
            / f"{relative_traj.name}__seg_{segment_idx:03d}_{role}"
        )

    @staticmethod
    def _frame_file_map(image_dir: Path) -> Dict[int, Path]:
        mapped: Dict[int, Path] = {}
        for path in sorted(image_dir.iterdir(), key=lambda p: p.name):
            if not path.is_file():
                continue
            try:
                frame_idx = int(path.stem)
            except ValueError:
                continue
            mapped[frame_idx] = path
        return mapped

    @staticmethod
    def _slice_images_for_segment(
        src_traj_dir: Path, dst_traj_dir: Path, *, start: int, end: int
    ) -> None:
        src_images_root = src_traj_dir / "images"
        if not src_images_root.exists():
            return

        dst_images_root = dst_traj_dir / "images"
        for image_dir in sorted(path for path in src_images_root.iterdir() if path.is_dir()):
            frame_map = InferenceServer._frame_file_map(image_dir)
            if not frame_map:
                continue
            dst_image_dir = dst_images_root / image_dir.name
            dst_image_dir.mkdir(parents=True, exist_ok=True)
            for local_idx, global_idx in enumerate(range(int(start), int(end))):
                src_frame = frame_map.get(int(global_idx))
                if src_frame is None:
                    raise FileNotFoundError(
                        f"Missing frame {global_idx} in {image_dir} while slicing {src_traj_dir}"
                    )
                shutil.copy2(src_frame, dst_image_dir / f"{local_idx}{src_frame.suffix}")

    @staticmethod
    def _slice_npy_files_for_segment(
        src_traj_dir: Path, dst_traj_dir: Path, *, start: int, end: int, num_frames: int
    ) -> None:
        for npy_path in sorted(src_traj_dir.glob("*.npy")):
            array = np.load(npy_path, mmap_mode="r")
            if array.ndim < 1 or int(array.shape[0]) != int(num_frames):
                continue
            np.save(dst_traj_dir / npy_path.name, np.asarray(array[int(start) : int(end)]))

    @staticmethod
    def _rewrite_meta_for_segment(
        meta_payload: Dict[str, Any],
        *,
        src_traj_dir: Path,
        start: int,
        end: int,
        is_human: bool,
        is_last_segment: bool,
    ) -> Dict[str, Any]:
        segment_success = bool(meta_payload.get("success", False)) and bool(is_last_segment)
        segment_is_reset = bool(meta_payload.get("is_reset", False)) and bool(is_last_segment)
        rewritten = dict(meta_payload)
        rewritten["human_collect"] = bool(is_human)
        rewritten["success"] = bool(segment_success)
        rewritten["is_reset"] = bool(segment_is_reset)
        rewritten["source_traj_dir"] = str(src_traj_dir)
        rewritten["source_frame_start"] = int(start)
        rewritten["source_frame_end"] = int(end)
        rewritten["split_from_is_human"] = True
        segment_length = int(end) - int(start)
        for key in list(rewritten.keys()):
            if key.startswith("num_") and key.endswith("_saved"):
                rewritten[key] = int(segment_length)
        return rewritten

    @staticmethod
    def _write_segment_unisteer_episode(
        src_traj_dir: Path,
        dst_traj_dir: Path,
        *,
        start: int,
        end: int,
        segment_idx: int,
        is_human: bool,
    ) -> bool:
        if is_human:
            return False

        episode_path = src_traj_dir / "unisteer_episode.msgpack"
        if not episode_path.exists():
            raise FileNotFoundError(
                f"Missing unisteer_episode.msgpack under model trajectory {src_traj_dir}"
            )

        episode_payload = msgpack.unpackb(episode_path.read_bytes(), raw=False)
        if not isinstance(episode_payload, dict):
            raise TypeError(f"Invalid UniSteer episode payload in {episode_path}")
        steps = episode_payload.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"Invalid UniSteer episode steps in {episode_path}")

        filtered_steps: List[Dict[str, Any]] = []
        for step in steps:
            step_index = int(step["step_index"])
            if int(start) <= step_index < int(end):
                local_step = copy.deepcopy(step)
                local_step["step_index"] = int(step_index - int(start))
                filtered_steps.append(local_step)

        if not filtered_steps:
            return False

        request_id = str(episode_payload.get("request_id") or src_traj_dir.name)
        remapped_payload = dict(episode_payload)
        remapped_payload["request_id"] = f"{request_id}:seg{segment_idx:03d}"
        remapped_payload["steps"] = filtered_steps
        remapped_payload["decision_indices"] = [int(step["step_index"]) for step in filtered_steps]
        (dst_traj_dir / "unisteer_episode.msgpack").write_bytes(
            msgpack.packb(remapped_payload, use_bin_type=True)
        )
        return True

    def _materialize_segmented_traj(
        self,
        *,
        src_traj_dir: Path,
        dst_traj_dir: Path,
        start: int,
        end: int,
        segment_idx: int,
        is_human: bool,
        is_last_segment: bool,
        num_frames: int,
        meta_payload: Dict[str, Any],
    ) -> bool:
        if int(end) <= int(start):
            return False

        if dst_traj_dir.exists():
            shutil.rmtree(dst_traj_dir)
        dst_traj_dir.mkdir(parents=True, exist_ok=True)

        self._slice_npy_files_for_segment(
            src_traj_dir, dst_traj_dir, start=int(start), end=int(end), num_frames=int(num_frames)
        )
        self._slice_images_for_segment(src_traj_dir, dst_traj_dir, start=int(start), end=int(end))
        task_path = src_traj_dir / "task_instruction.txt"
        if task_path.exists():
            shutil.copy2(task_path, dst_traj_dir / "task_instruction.txt")
        (dst_traj_dir / "meta.json").write_text(
            json.dumps(
                self._rewrite_meta_for_segment(
                    meta_payload,
                    src_traj_dir=src_traj_dir,
                    start=int(start),
                    end=int(end),
                    is_human=bool(is_human),
                    is_last_segment=bool(is_last_segment),
                ),
                indent=2,
            ),
            encoding="utf-8",
        )
        if is_human:
            return True
        return self._write_segment_unisteer_episode(
            src_traj_dir,
            dst_traj_dir,
            start=int(start),
            end=int(end),
            segment_idx=int(segment_idx),
            is_human=bool(is_human),
        )

    def _partition_unisteer_training_trajs(
        self, root_dir: Path, traj_dirs: List[Path]
    ) -> Dict[str, List[Path]]:
        model_trajs: List[Path] = []
        human_trajs: List[Path] = []
        segment_root = root_dir / UNISTEER_SEGMENT_ROOT_NAME / uuid.uuid4().hex

        for traj_dir in traj_dirs:
            meta_payload = self._load_traj_meta(traj_dir)
            has_unisteer_sidecar = (traj_dir / "unisteer_episode.msgpack").exists()
            is_human_flags = self._load_is_human_flags(traj_dir)
            num_frames = int(is_human_flags.shape[0])

            if bool(np.all(is_human_flags)):
                human_trajs.append(traj_dir)
                continue
            if bool(np.all(~is_human_flags)):
                if not has_unisteer_sidecar:
                    raise FileNotFoundError(
                        f"All-model trajectory requires unisteer_episode.msgpack under {traj_dir}"
                    )
                model_trajs.append(traj_dir)
                continue

            segments = self._find_contiguous_segments(is_human_flags)
            for segment_idx, (is_human, start, end) in enumerate(segments):
                dst_traj_dir = self._segment_output_dir(
                    segment_root, root_dir, traj_dir, segment_idx, is_human
                )
                created = self._materialize_segmented_traj(
                    src_traj_dir=traj_dir,
                    dst_traj_dir=dst_traj_dir,
                    start=int(start),
                    end=int(end),
                    segment_idx=int(segment_idx),
                    is_human=bool(is_human),
                    is_last_segment=segment_idx == len(segments) - 1,
                    num_frames=num_frames,
                    meta_payload=meta_payload,
                )
                if not created:
                    continue
                if is_human:
                    human_trajs.append(dst_traj_dir)
                else:
                    model_trajs.append(dst_traj_dir)

        return {
            "model_trajs": sorted(model_trajs, key=lambda p: str(p)),
            "human_trajs": sorted(human_trajs, key=lambda p: str(p)),
        }

    def _load_unisteer_episode_sidecar(self, trajectory_dir: Path) -> Dict[str, Any]:
        episode_path = trajectory_dir / "unisteer_episode.msgpack"
        if not episode_path.exists():
            raise FileNotFoundError(f"Missing UniSteer episode sidecar: {episode_path}")

        episode_payload = msgpack.unpackb(episode_path.read_bytes(), raw=False)
        if not isinstance(episode_payload, dict):
            raise TypeError(f"Invalid UniSteer episode payload in {episode_path}")
        steps = episode_payload.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"Invalid UniSteer episode steps in {episode_path}")

        task_description = str(
            episode_payload.get("task_description")
            or self._load_traj_task_instruction(trajectory_dir)
        ).strip()
        if not task_description:
            raise ValueError(f"Missing task_description in {episode_path}")

        decision_indices = episode_payload.get("decision_indices")
        if decision_indices is None:
            decision_indices = [int(step["step_index"]) for step in steps]
        else:
            decision_indices = [int(idx) for idx in decision_indices]

        return {
            "episode_path": str(episode_path),
            "request_id": str(episode_payload.get("request_id") or trajectory_dir.name),
            "task_description": task_description,
            "decision_indices": decision_indices,
            "num_steps": len(steps),
        }

    def _count_human_decision_frames(
        self, trajectory_dir: Path, *, image_key: str, extension: str
    ) -> int:
        try:
            return int(get_traj_num_steps(trajectory_dir, image_key))
        except FileNotFoundError:
            image_dir = trajectory_dir / "images" / image_key
            if not image_dir.exists():
                raise FileNotFoundError(
                    f"Missing image data for UniSteer human reward: {trajectory_dir} image_key={image_key}"
                )
            count = sum(1 for _ in image_dir.glob(f"*.{extension}"))
            if count <= 0:
                raise ValueError(f"No *.{extension} images found under {image_dir}")
            return int(count)

    def _human_unisteer_decision_indices(self, trajectory_dir: Path) -> List[int]:
        finetune_cfg = getattr(getattr(self.cfg, "data", None), "finetune", None)
        image_key = str(getattr(finetune_cfg, "image_key", self.unisteer_image_key))
        extension = str(getattr(finetune_cfg, "extension", self.unisteer_image_extension))
        action_future_size = int(
            getattr(finetune_cfg, "action_future_size", getattr(self.cfg, "horizon_steps", 16))
        )
        min_valid_action = int(getattr(finetune_cfg, "min_valid_action", 1))
        min_valid_state = int(getattr(finetune_cfg, "min_valid_state", 1))

        num_steps = self._count_human_decision_frames(
            trajectory_dir, image_key=image_key, extension=extension
        )
        action_indices = np.arange(
            int(min_valid_state) - 1, num_steps + int(action_future_size) - int(min_valid_action)
        )
        action_indices = np.lib.stride_tricks.sliding_window_view(
            action_indices, int(action_future_size), 0
        )
        action_indices = np.clip(action_indices, 0, num_steps - 1)
        if int(action_indices.shape[0]) <= 0:
            raise ValueError(
                f"No human UniSteer decision indices generated for {trajectory_dir} "
                f"(num_steps={num_steps}, action_future_size={action_future_size})"
            )
        return [int(row[0]) for row in action_indices]

    def _write_unisteer_reward_sidecar(self, *, trajectory_dir: Path) -> Dict[str, Any]:
        episode_info = self._load_unisteer_episode_sidecar(trajectory_dir)
        reward_result = self._build_binary_reward_result(
            request_id=episode_info["request_id"],
            trajectory_dir=trajectory_dir,
            instruction=episode_info["task_description"],
            decision_indices=episode_info["decision_indices"],
        )

        reward_path = trajectory_dir / "unisteer_reward_result.json"
        reward_path.write_text(json.dumps(reward_result, indent=2), encoding="utf-8")

        summary = reward_result.get("summary") or {}
        return {
            "trajectory_dir": str(trajectory_dir),
            "episode_path": episode_info["episode_path"],
            "reward_path": str(reward_path),
            "num_decisions": int(episode_info["num_steps"]),
            "decision_indices": episode_info["decision_indices"],
            "reward_sum": summary.get("reward_sum"),
            "done_index": summary.get("done_index"),
            "success": self._reward_summary_success(summary),
            "reset_failure": bool(summary.get("reset_failure", False)),
        }

    def _write_unisteer_human_reward_sidecar(self, *, trajectory_dir: Path) -> Dict[str, Any]:
        task_description = self._load_traj_task_instruction(trajectory_dir)
        decision_indices = self._human_unisteer_decision_indices(trajectory_dir)
        reward_result = self._build_binary_reward_result(
            request_id=trajectory_dir.name,
            trajectory_dir=trajectory_dir,
            instruction=task_description,
            decision_indices=decision_indices,
        )
        reward_path = trajectory_dir / "unisteer_reward_result.json"
        reward_path.write_text(json.dumps(reward_result, indent=2), encoding="utf-8")

        summary = reward_result.get("summary") or {}
        return {
            "trajectory_dir": str(trajectory_dir),
            "episode_path": None,
            "reward_path": str(reward_path),
            "num_decisions": int(len(decision_indices)),
            "decision_indices": decision_indices,
            "reward_sum": summary.get("reward_sum"),
            "done_index": summary.get("done_index"),
            "success": self._reward_summary_success(summary),
            "reset_failure": bool(summary.get("reset_failure", False)),
        }

    def predict_action(self) -> Response:
        t0 = time.time()
        try:
            decoded = msgpack.unpackb(request.get_data(cache=False))
            payload = self._decode_standard_observation(decoded)
            inputs = self._parse_payload(payload)
            action, _ = self.agent.inference(**inputs)
            # /act returns a pure runtime-sized action chunk: float32[inference_chunk_size, action_dim].
            response = msgpack.packb(action.astype(np.float32).tobytes())
            self.inference_count += 1
            self.last_inference_time = time.time()
            logger.debug(f"Inference {self.inference_count}: {time.time() - t0:.3f}s")
            return Response(response=response, status=200)
        except Exception as exc:
            logger.error(f"Prediction error: {exc}")
            import traceback

            traceback.print_exc()
            return Response(response="error", status=500)

    def predict_action_unisteer(self) -> Response:
        """Act with the UniSteer noise actor and frozen VLA decoder."""
        t0 = time.time()
        try:
            if not self.unisteer_actor.ready:
                raise RuntimeError("Noise actor is not loaded; call /reload_actor first")

            decoded = msgpack.unpackb(request.get_data(cache=False))
            payload = self._decode_standard_observation(decoded)
            deterministic_override = decoded.get("deterministic", None)
            if deterministic_override is None:
                rollout_temp = float(self.unisteer_actor_rollout_temperature)
                deterministic = bool(
                    self.unisteer_actor.deterministic_by_default and rollout_temp <= 0.0
                )
                sampling_temperature = None if deterministic else rollout_temp
            else:
                deterministic = bool(deterministic_override)
                sampling_temperature = None

            inputs = self._parse_payload(payload)
            unisteer_observation = self.agent.build_unisteer_observation(**inputs)
            state = np.asarray(unisteer_observation["state"], dtype=np.float32).reshape(-1)
            if self._should_initial_rollout_bypass_actor():
                noise_action, actor_info = (
                    self.unisteer_actor.sample_standard_gaussian_noise_action()
                )
            else:
                noise_action, actor_info = self.unisteer_actor.act(
                    unisteer_observation,
                    deterministic=deterministic,
                    temperature=sampling_temperature,
                )
            action, info = self.agent.inference_from_noise(**inputs, noise_action=noise_action)

            resp = {
                "action": np.asarray(action, dtype=np.float32).tobytes(),
                "meta": {
                    "state": state.tolist(),
                    "noise_action": np.asarray(noise_action, dtype=np.float32).reshape(-1).tolist(),
                    "action_pred_norm": np.asarray(
                        info["action_pred_norm"], dtype=np.float32
                    ).tolist(),
                    "inference_chunk_size": int(self.agent.inference_chunk_size),
                    "actor_update_step": int(actor_info["update_step"]),
                    "actor_checkpoint_path": actor_info["checkpoint_path"],
                    "deterministic": bool(actor_info["deterministic"]),
                    "sampling_mode": str(actor_info["sampling_mode"]),
                    "sampling_temperature": float(actor_info["sampling_temperature"]),
                    "initial_rollout_bypass_actor": bool(
                        actor_info.get("initial_rollout_bypass_actor", False)
                    ),
                },
            }
            response = msgpack.packb(resp, use_bin_type=True)

            self.inference_count += 1
            self.last_inference_time = time.time()
            logger.debug(f"UniSteer Full Inference {self.inference_count}: {time.time() - t0:.3f}s")
            return Response(response=response, status=200)
        except Exception as exc:
            logger.error(f"UniSteer Full Prediction error: {exc}")
            import traceback

            traceback.print_exc()
            return Response(response="error", status=500)

    def set_rollout_callback(self, callback):
        self._rollout_callback = callback

    def handle_submit_rollout(self) -> Response:
        try:
            data = request.get_json() or {}
            request_id = data.get("request_id") or f"rollout_{uuid.uuid4().hex[:12]}"
            trajectory_dir = data.get("trajectory_dir")
            num_trajectories = int(data.get("num_trajectories", 0))
            meta = data.get("meta", {}) or {}
            logger.info(
                f"Submitting rollout: request_id={request_id}, "
                f"dir={trajectory_dir}, n_traj={num_trajectories}"
            )

            if not trajectory_dir:
                return Response(
                    response=json.dumps({"status": "error", "message": "missing trajectory_dir"}),
                    status=400,
                    mimetype="application/json",
                )

            local_dir = Path(str(trajectory_dir)).expanduser().resolve()
            if not local_dir.exists() or not local_dir.is_dir():
                return Response(
                    response=json.dumps(
                        {
                            "status": "error",
                            "message": f"trajectory_dir not found: {trajectory_dir}",
                        }
                    ),
                    status=400,
                    mimetype="application/json",
                )

            model_traj_dirs: List[Path] = []
            human_traj_dirs: List[Path] = []
            has_unisteer_training = False
            unisteer_rollout_results: List[Dict[str, Any]] = []
            unisteer_human_reward_results: List[Dict[str, Any]] = []

            if self.unisteer_train_server_url:
                discovered_traj_dirs = self._discover_rollout_trajectory_dirs(local_dir)
                unisteer_groups = self._partition_unisteer_training_trajs(
                    local_dir, discovered_traj_dirs
                )
                model_traj_dirs = unisteer_groups["model_trajs"]
                human_traj_dirs = unisteer_groups["human_trajs"]
                has_unisteer_training = bool(model_traj_dirs or human_traj_dirs)
                unisteer_rollout_results = [
                    self._write_unisteer_reward_sidecar(trajectory_dir=traj_dir)
                    for traj_dir in model_traj_dirs
                ]
                unisteer_human_reward_results = [
                    self._write_unisteer_human_reward_sidecar(trajectory_dir=traj_dir)
                    for traj_dir in human_traj_dirs
                ]

            meta_for_train = {
                **meta,
                "unisteer_training": bool(has_unisteer_training),
                "unisteer_rollout": bool(model_traj_dirs),
                "unisteer_model_trajectory_dirs": [str(path) for path in model_traj_dirs],
                "unisteer_human_trajectory_dirs": [str(path) for path in human_traj_dirs],
                "unisteer_result": {
                    "mode": "scan",
                    "num_rollouts": len(unisteer_rollout_results),
                    "rollouts": unisteer_rollout_results,
                    "num_human_rollouts": len(unisteer_human_reward_results),
                    "human_rollouts": unisteer_human_reward_results,
                },
            }

            payload = {
                "status": "completed",
                "trajectory_dir": str(local_dir),
                "num_trajectories": num_trajectories,
                "end_time": time.time(),
                "meta": meta_for_train,
            }
            if self._rollout_callback is not None:
                self._rollout_callback(
                    request_id=request_id, trajectory_dir=str(local_dir), meta=payload
                )
            return Response(
                response=json.dumps({"status": "ok", "request_id": request_id}),
                status=200,
                mimetype="application/json",
            )

        except Exception as exc:
            logger.error(f"Submit rollout handler error: {exc}")
            import traceback

            traceback.print_exc()
            return Response(
                response=json.dumps({"status": "error", "message": str(exc)}),
                status=500,
                mimetype="application/json",
            )

    def handle_reload_actor(self) -> Response:
        try:
            data = request.get_json() or {}
            ckpt = data.get("checkpoint", None)
            if not ckpt:
                return Response(
                    response=json.dumps({"status": "error", "message": "missing checkpoint"}),
                    status=400,
                    mimetype="application/json",
                )

            local_ckpt = self._reload_actor_checkpoint(str(ckpt))
            return Response(
                response=json.dumps(
                    {
                        "status": "ok",
                        "checkpoint": local_ckpt,
                        "actor": self.unisteer_actor.status(),
                    }
                ),
                status=200,
                mimetype="application/json",
            )
        except Exception as exc:
            logger.error(f"handle_reload_actor error: {exc}")
            import traceback

            traceback.print_exc()
            return Response(
                response=json.dumps({"status": "error", "message": str(exc)}),
                status=500,
                mimetype="application/json",
            )

    def handle_actor_status(self) -> Response:
        return Response(
            response=json.dumps({"status": "ok", "actor": self.unisteer_actor.status()}),
            status=200,
            mimetype="application/json",
        )

    def create_app(self) -> Flask:
        app = Flask(__name__)
        app.route("/act", methods=["POST"])(self.predict_action)
        app.route("/act_unisteer", methods=["POST"])(self.predict_action_unisteer)
        app.route("/submit_rollout", methods=["POST"])(self.handle_submit_rollout)
        app.route("/reload_actor", methods=["POST"])(self.handle_reload_actor)
        app.route("/actor_status", methods=["GET"])(self.handle_actor_status)
        return app

    def run(self, host: str = "127.0.0.1", port: int = 8000):
        app = self.create_app()
        logger.info(f"Starting inference server on {host}:{port}")
        app.run(host=host, port=port, threaded=False)


def main():
    import argparse

    import requests

    if OmegaConf is None:
        raise ImportError("omegaconf is required to run inference_server.py via CLI")

    OmegaConf.register_new_resolver("eval", eval, replace=True)
    OmegaConf.register_new_resolver("round_up", math.ceil, replace=True)
    OmegaConf.register_new_resolver("round_down", math.floor, replace=True)

    parser = argparse.ArgumentParser(description="Original PI0 Inference Server")
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--checkpoint", type=str, default=None)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--unisteer_train_server_url", type=str, default=None)
    parser.add_argument("--inference_chunk_size", type=int, default=None)
    parser.add_argument("--unisteer_actor_checkpoint", type=str, default=None)
    args = parser.parse_args()

    cfg = OmegaConf.load(args.config)
    if args.checkpoint:
        os.environ["INFERENCE_CHECKPOINT"] = args.checkpoint
    if args.unisteer_actor_checkpoint:
        os.environ[UNISTEER_ACTOR_CHECKPOINT_ENV] = args.unisteer_actor_checkpoint
    with open_dict(cfg):
        if args.unisteer_train_server_url:
            cfg.unisteer_train_server_url = args.unisteer_train_server_url.rstrip("/")
        if args.inference_chunk_size is not None:
            cfg.inference_chunk_size = int(args.inference_chunk_size)

    server = InferenceServer(cfg)

    unisteer_train_url = (server.unisteer_train_server_url or "").rstrip("/") or None
    if unisteer_train_url:

        def _notify_train(request_id: str, trajectory_dir: str, meta: dict):
            meta_payload = meta.get("meta", {}) if isinstance(meta.get("meta"), dict) else {}
            is_unisteer_training = bool(
                meta_payload.get("unisteer_training", meta_payload.get("unisteer_rollout", False))
            )
            if not is_unisteer_training:
                logger.warning(
                    f"Skipping rollout callback for request_id={request_id}: "
                    "rollout does not contain UniSteer training data"
                )
                return

            payload = {
                "request_id": request_id,
                "model_trajectory_dirs": meta_payload.get("unisteer_model_trajectory_dirs", []),
                "human_trajectory_dirs": meta_payload.get("unisteer_human_trajectory_dirs", []),
            }

            def _post():
                try:
                    if meta.get("status") != "completed":
                        logger.warning(
                            f"Skipping rollout callback for request_id={request_id} because status={meta.get('status')}"
                        )
                        return
                    response = requests.post(
                        f"{unisteer_train_url}/train_rollout", json=payload, timeout=10
                    )
                    if response.status_code not in (200, 202):
                        logger.error(f"notify train failed: {response.status_code} {response.text}")
                except Exception as exc:
                    logger.error(f"notify train failed: {exc}")

            threading.Thread(target=_post, daemon=True).start()

        server.set_rollout_callback(_notify_train)
        logger.info(f"UniSteer rollout callback enabled: {unisteer_train_url}")

    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    import math

    main()
