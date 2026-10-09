from collections import OrderedDict
import json
import os
from pathlib import Path
import pickle
import random
import threading
from typing import Any, Iterator, List, Tuple

from einops import rearrange
from loguru import logger
import matplotlib.pyplot as plt
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import torch
from tqdm import tqdm

from src.utils.sft_image_aug import apply_sft_image_aug

EPS = 1e-6

NORMALIZATION_MODE_TO_METHOD = {
    "MEAN_STD": "meanstd",
    "MIN_MAX": "minmax",
    "QUANTILES": "q01q99",
    "QUANTILE10": "q10q90",
}

METHOD_TO_REQUIRED_STATS = {
    "meanstd": ("mean", "std"),
    "minmax": ("min", "max"),
    "q01q99": ("q01", "q99"),
    "q10q90": ("q10", "q90"),
}


def _optional_float_list(values: Any, *, name: str) -> list[float] | None:
    if values is None:
        return None
    if isinstance(values, str):
        if not values.strip():
            return None
        raise ValueError(f"{name} must be a list of numbers, got string: {values!r}")
    result = [float(v) for v in values]
    if not result:
        raise ValueError(f"{name} must be non-empty when provided")
    if not np.isfinite(np.asarray(result, dtype=np.float64)).all():
        raise ValueError(f"{name} contains non-finite values: {result}")
    if any(v < 0.0 for v in result):
        raise ValueError(f"{name} must be non-negative: {result}")
    if sum(result) <= 0.0:
        raise ValueError(f"{name} must have positive sum: {result}")
    return result


def resolve_normalization_mode(mode: str | None) -> str:
    normalized = str(mode or "QUANTILES").strip().upper()
    if normalized not in NORMALIZATION_MODE_TO_METHOD:
        supported = ", ".join(NORMALIZATION_MODE_TO_METHOD.keys())
        raise ValueError(f"Unsupported normalization mode: {mode}. Expected one of: {supported}")
    return normalized


def normalization_mode_to_method(mode: str | None) -> str:
    return NORMALIZATION_MODE_TO_METHOD[resolve_normalization_mode(mode)]


def _load_gripper_series(path: Path) -> np.ndarray:
    values = np.load(path)
    if values.ndim == 2 and values.shape[1] > 1:
        return values[:, -1].astype(np.float32)
    return values.reshape(-1).astype(np.float32)


def load_traj_proprio_action(
    traj_dir: Path | str, *, use_gripper_master: bool
) -> Tuple[np.ndarray, np.ndarray]:
    traj = Path(traj_dir)

    proprio_file = traj / "left_arm_poseuler_arm.npy"
    if not proprio_file.exists():
        proprio_file = traj / "proprio.npy"
    if not proprio_file.exists():
        raise FileNotFoundError(f"Missing proprio file under {traj}")
    proprio = np.load(proprio_file).astype(np.float32)
    if proprio.ndim != 2:
        raise ValueError(f"Unexpected proprio shape in {proprio_file}: {list(proprio.shape)}")

    action_file = traj / "action.npy"
    if not action_file.exists():
        raise FileNotFoundError(f"Missing action.npy under {traj}")
    action = np.load(action_file).astype(np.float32)
    if action.ndim != 2:
        raise ValueError(f"Unexpected action shape in {action_file}: {list(action.shape)}")

    joint_file = traj / "left_arm_joint_status.npy"
    action_gripper_file = traj / (
        "gripper_ctrl_smooth.npy" if use_gripper_master else "left_arm_joint_status.npy"
    )
    if use_gripper_master and (not action_gripper_file.exists()) and joint_file.exists():
        logger.warning(
            f"[use_gripper_master] missing {action_gripper_file.name} in {traj}, fallback to {joint_file.name}"
        )
        action_gripper_file = joint_file

    if action_gripper_file.exists():
        gr_abs = _load_gripper_series(action_gripper_file)
        if gr_abs.shape[0] != action.shape[0]:
            raise ValueError(
                f"Gripper / action length mismatch under {traj}: {gr_abs.shape[0]} vs {action.shape[0]}"
            )
        action = action.copy()
        action[:, -1] = gr_abs

    if proprio.shape[1] == 6:
        if joint_file.exists():
            gr_col = _load_gripper_series(joint_file).reshape(-1, 1)
            if gr_col.shape[0] != proprio.shape[0]:
                raise ValueError(
                    f"Gripper / proprio length mismatch under {traj}: {gr_col.shape[0]} vs {proprio.shape[0]}"
                )
            proprio = np.hstack([proprio, gr_col])
        else:
            if action.shape[0] != proprio.shape[0]:
                raise ValueError(
                    f"Action / proprio length mismatch under {traj}: {action.shape[0]} vs {proprio.shape[0]}"
                )
            proprio = np.hstack([proprio, action[:, [-1]]])
            proprio[1:, -1] = proprio[:-1, -1]

    if proprio.shape[0] != action.shape[0]:
        raise ValueError(
            f"Proprio / action length mismatch under {traj}: {proprio.shape[0]} vs {action.shape[0]}"
        )

    return (
        np.ascontiguousarray(proprio.astype(np.float32, copy=False)),
        np.ascontiguousarray(action.astype(np.float32, copy=False)),
    )


def resolve_traj_image_array_name(image_key: str | None) -> str:
    raw_key = str(image_key or "").strip().lower()
    if "primary" in raw_key:
        return "primary.npy"
    if "wrist" in raw_key:
        return "wrist.npy"
    raise ValueError(
        f"Could not map image_key={image_key!r} to a trajectory image array. "
        "Expected a key containing 'primary' or 'wrist'."
    )


def resolve_traj_image_array_path(traj_dir: Path | str, image_key: str | None) -> Path:
    return Path(traj_dir) / resolve_traj_image_array_name(image_key)


def validate_traj_image_array(array: np.ndarray, *, path: Path) -> None:
    if array.ndim != 4:
        raise ValueError(f"Expected image array rank 4 at {path}, got shape={list(array.shape)}")
    if int(array.shape[1]) != 3 and int(array.shape[-1]) != 3:
        raise ValueError(
            f"Expected TCHW or THWC image array with channel dim=3 at {path}, got shape={list(array.shape)}"
        )
    if array.dtype != np.uint8:
        raise ValueError(f"Expected uint8 image array at {path}, got dtype={array.dtype}")


def image_frame_to_chw_uint8(image: np.ndarray) -> np.ndarray:
    frame = np.asarray(image, dtype=np.uint8)
    if frame.ndim != 3:
        raise ValueError(f"Expected image rank 3, got shape={list(frame.shape)}")
    if int(frame.shape[0]) == 3:
        return np.ascontiguousarray(frame)
    if int(frame.shape[-1]) == 3:
        return np.ascontiguousarray(np.transpose(frame, (2, 0, 1)))
    raise ValueError(f"Expected CHW or HWC image with channel dim=3, got shape={list(frame.shape)}")


def load_traj_image_sequence(
    traj_dir: Path | str, image_key: str | None, *, mmap_mode: str = "r"
) -> np.ndarray:
    array_path = resolve_traj_image_array_path(traj_dir, image_key)
    if not array_path.is_file():
        raise FileNotFoundError(f"Missing image array for image_key={image_key!r}: {array_path}")
    array = np.load(array_path, mmap_mode=mmap_mode)
    validate_traj_image_array(array, path=array_path)
    return array


def get_traj_num_steps(traj_dir: Path | str, image_key: str | None) -> int:
    return int(load_traj_image_sequence(traj_dir, image_key).shape[0])


class TrajectoryImageArrayCache:
    def __init__(self, *, enabled: bool, max_trajs: int):
        self.enabled = bool(enabled)
        self.max_trajs = int(max_trajs)
        if self.max_trajs < 0:
            raise ValueError("image cache max_trajs must be >= 0")
        self._cache: OrderedDict[str, dict[str, np.ndarray]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _root_key(traj_dir: Path | str) -> str:
        return str(Path(traj_dir))

    def get_sequence(self, traj_dir: Path | str, image_key: str | None) -> np.ndarray:
        root_key = self._root_key(traj_dir)
        cache_key = str(image_key)
        if self.enabled:
            with self._lock:
                traj_cache = self._cache.get(root_key)
                if traj_cache is not None:
                    cached = traj_cache.get(cache_key)
                    if cached is not None:
                        self._cache.move_to_end(root_key)
                        return cached

        array = load_traj_image_sequence(root_key, image_key)
        if not self.enabled:
            return array

        with self._lock:
            traj_cache = self._cache.get(root_key)
            if traj_cache is None:
                traj_cache = {}
                self._cache[root_key] = traj_cache
            else:
                self._cache.move_to_end(root_key)

            cached = traj_cache.get(cache_key)
            if cached is not None:
                return cached

            traj_cache[cache_key] = array
            if self.max_trajs > 0 and len(self._cache) > self.max_trajs:
                self._cache.popitem(last=False)
        return array

    def get_frame(
        self, traj_dir: Path | str, image_key: str | None, step_index: int, *, copy: bool = True
    ) -> np.ndarray:
        array = self.get_sequence(traj_dir, image_key)
        idx = int(step_index)
        if idx < 0 or idx >= int(array.shape[0]):
            raise IndexError(
                f"step_index out of range for {traj_dir}: step_index={idx}, num_steps={int(array.shape[0])}"
            )
        frame = np.array(array[idx], dtype=np.uint8, copy=copy)
        return image_frame_to_chw_uint8(frame)


def load_traj_image_frame_chw_uint8(
    traj_dir: Path | str, image_key: str | None, step_index: int
) -> np.ndarray:
    array = load_traj_image_sequence(traj_dir, image_key)
    idx = int(step_index)
    if idx < 0 or idx >= int(array.shape[0]):
        raise IndexError(
            f"step_index out of range for {traj_dir}: step_index={idx}, num_steps={int(array.shape[0])}"
        )
    return image_frame_to_chw_uint8(np.array(array[idx], dtype=np.uint8, copy=True))


def chw_uint8_to_hwc_uint8(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image, dtype=np.uint8)
    if arr.ndim != 3 or int(arr.shape[0]) != 3:
        raise ValueError(f"Expected CHW uint8 image with shape [3,H,W], got {list(arr.shape)}")
    return np.ascontiguousarray(np.transpose(arr, (1, 2, 0)))


class FinetuneDataset(torch.utils.data.IterableDataset):
    """Index-based trajectory windows with masking support."""

    def __init__(self, config, train=True, num_workers=4):

        self.debug = getattr(config, "debug", False)
        self.proprio_type = config.proprio_type
        self.action_type = config.action_type

        assert self.proprio_type == "poseulerg"
        self.proprio_key = "proprio"

        self.wrist_key = config.wrist_key
        self.image_key = config.image_key
        self.force_regenerate = config.force_regenerate_meta
        self.plot_hist = config.plot_hist

        self.action_future_size = config.action_future_size
        self.state_hist_size = config.state_hist_size

        self.min_valid_action = max(1, getattr(config, "min_valid_action", 1))
        self.min_valid_state = max(1, getattr(config, "min_valid_state", 1))

        assert self.action_future_size >= 1
        assert self.state_hist_size >= 1

        self.extension = getattr(config, "extension", "jpg")
        self.overwrite_stats = getattr(config, "overwrite_stats", "piper_stack")
        self.state_normalization_mode = resolve_normalization_mode(
            getattr(config, "state_normalization_mode", "QUANTILES")
        )
        self.action_normalization_mode = resolve_normalization_mode(
            getattr(config, "action_normalization_mode", "QUANTILES")
        )
        # ---- RL meta loading (optional) ----
        self.load_rl_meta = bool(getattr(config, "load_rl_meta", False))
        self.require_rl_meta = bool(getattr(config, "require_rl_meta", False))

        self.rl_chains_file = str(getattr(config, "rl_chains_file", "rl_chains.npy"))
        self.rl_denoise_inds_file = str(
            getattr(config, "rl_denoise_inds_file", "rl_denoise_inds.npy")
        )
        self.rl_prev_logprobs_file = str(
            getattr(config, "rl_prev_logprobs_file", "rl_prev_logprobs.npy")
        )

        self._rl_meta_cache = {}  # traj_dir(str) -> mmap arrays

        # If True:
        # - action last dim uses gripper_ctrl.npy as the "master" source (overrides action last dim)
        # - proprio gripper dim (when appended) still uses left_arm_joint_status.npy
        self.use_gripper_master = bool(getattr(config, "use_gripper_master", False))

        self.use_img_aug = bool(getattr(config, "use_img_aug", True))
        self.enable_image_cache = bool(getattr(config, "enable_image_cache", False))
        self.image_cache_max_trajs = int(getattr(config, "image_cache_max_trajs", 0))
        if self.image_cache_max_trajs < 0:
            raise ValueError("image_cache_max_trajs must be >= 0")
        self._image_sequence_cache = TrajectoryImageArrayCache(
            enabled=self.enable_image_cache, max_trajs=self.image_cache_max_trajs
        )
        # data_path supports a single path or a list/tuple of paths
        data_path_cfg = config.data_path
        if isinstance(data_path_cfg, (str, Path)):
            self.data_paths = [Path(data_path_cfg)]
        else:
            self.data_paths = [Path(p) for p in data_path_cfg]
        if not self.data_paths:
            raise ValueError("data_path must contain at least one path")

        data_mix_weights = _optional_float_list(
            getattr(config, "data_mix_weights", None), name="data_mix_weights"
        )
        if data_mix_weights is not None and len(data_mix_weights) != len(self.data_paths):
            raise ValueError(
                "data_mix_weights length must match data_path length: "
                f"{len(data_mix_weights)} vs {len(self.data_paths)}"
            )
        if data_mix_weights is None:
            self.data_mix_weights = None
        else:
            total_mix_weight = sum(data_mix_weights)
            self.data_mix_weights = [w / total_mix_weight for w in data_mix_weights]

        # Keep data_path as a reference to the first directory (for caching statistics, etc.)
        self.data_path = self.data_paths[0]

        spec = (
            f"s{self.proprio_type}_{self.state_hist_size}"
            f"_a{self.action_type}_{self.action_future_size}"
        )

        # Load metadata from all data_paths
        self.metadata = []
        for root_idx, data_dir in enumerate(self.data_paths):
            if train:
                meta_path = data_dir / f"metadata_train_{spec}.pkl"
            else:
                meta_path = data_dir / f"metadata_val_{spec}.pkl"

            if meta_path.is_file() and (not self.force_regenerate):
                logger.info(f"Loading cached metadata from {data_dir}")
                with open(meta_path, "rb") as f:
                    dir_metadata = pickle.load(f)
            else:
                logger.info(f"Generating metadata for {data_dir}...")
                dir_metadata = self._generate_metadata(train, base_path=data_dir)
                with open(meta_path, "wb") as f:
                    pickle.dump(dir_metadata, f)

            data_root = self._normalize_traj_dir(data_dir)
            for meta in dir_metadata:
                meta["data_root_idx"] = root_idx
                meta["data_root"] = data_root
            self.metadata.extend(dir_metadata)

        # Load/generate statistics from the specified stats root (default: first data_path).
        stats_root_cfg = getattr(config, "stats_data_path", None)
        stats_root = Path(stats_root_cfg) if stats_root_cfg else self.data_path
        stat_path = stats_root / "dataset_statistics_train.json"
        self.stats_root = stats_root
        self.stat_path = stat_path
        self.stats_source = "generated_from_active_data_path"

        if stats_root_cfg:
            if not stat_path.is_file():
                raise FileNotFoundError(
                    f"stats_data_path set but dataset_statistics_train.json not found: {stat_path}"
                )
            with open(stat_path, "r", encoding="utf-8") as f:
                self.dataset_statistics = json.load(f)
            self.stats_source = "stats_data_path"
        elif stat_path.is_file() and ((not self.force_regenerate) or (not train)):
            with open(stat_path, "r", encoding="utf-8") as f:
                self.dataset_statistics = json.load(f)
            self.stats_source = "existing_data_path_stats"
        else:
            assert train
            assert self.metadata
            self.dataset_statistics = self._generate_statistics(self.metadata)
            with open(stat_path, "w", encoding="utf-8") as f:
                json.dump(self.dataset_statistics, f, indent=4)
            self.stats_source = "generated_from_active_data_path"

        self.dataset_statistics = self._overwrite_statistics(self.dataset_statistics)
        self._validate_normalization_stats()
        self._torch_stat_cache: dict[tuple[str, str, torch.dtype], dict[str, torch.Tensor]] = {}

        self.root_sample_counts = self._compute_root_sample_counts()
        self._validate_data_mix_sample_counts()
        self.weights = self._metadata_sampling_weights()
        total_samples = sum(item["num_samples"] for item in self.metadata)

        if self.plot_hist:
            self.plot_hist_prop_action()

        logger.info(
            f"FinetuneDataset: {len(self.data_paths)} dirs, "
            f"{len(self.metadata)} trajs, {total_samples} samples, "
            f"avg {total_samples / len(self.metadata):.1f} samples/traj"
        )
        if self.data_mix_weights is not None:
            logger.info("Data mix sampling enabled\n" + self.data_mix_summary_str())
        if self.enable_image_cache:
            max_trajs = (
                self.image_cache_max_trajs if self.image_cache_max_trajs > 0 else "unbounded"
            )
            logger.info(f"Image memmap cache enabled | max_trajs={max_trajs}")

        self._traj_meta_cache = {}
        self._active_traj_dirs = []
        self._rebuild_traj_meta_cache()

        logger.info("Normalization stats ready\n" + self.normalization_summary_str())

    @staticmethod
    def _is_traj_dir(path: Path) -> bool:
        return (path / "action.npy").is_file() and (path / "primary.npy").is_file()

    @staticmethod
    def _normalize_traj_dir(path: Path | str) -> str:
        return str(Path(path).expanduser().resolve())

    def _rebuild_traj_meta_cache(self) -> None:
        self._traj_meta_cache = {}
        self._active_traj_dirs = []
        normalized_data_paths = []

        for meta in self.metadata:
            traj_dir = self._normalize_traj_dir(meta["traj_dir"])
            meta["traj_dir"] = traj_dir
            self._traj_meta_cache[traj_dir] = meta
            self._active_traj_dirs.append(traj_dir)

        for path in self.data_paths:
            normalized_data_paths.append(Path(self._normalize_traj_dir(path)))
        self.data_paths = normalized_data_paths
        if self.data_paths:
            self.data_path = self.data_paths[0]

    def _set_active_traj_dirs(self, traj_dirs: List[str]) -> None:
        normalized = [self._normalize_traj_dir(path) for path in traj_dirs]
        self._active_traj_dirs = normalized
        self.metadata = [self._traj_meta_cache[path] for path in normalized]
        self.root_sample_counts = self._compute_root_sample_counts()
        self._validate_data_mix_sample_counts()
        self.weights = self._metadata_sampling_weights()
        self.data_paths = [Path(path) for path in normalized]
        if self.data_paths:
            self.data_path = self.data_paths[0]

    def _compute_root_sample_counts(self) -> list[int]:
        counts = [0 for _ in self.data_paths]
        for meta in self.metadata:
            root_idx = int(meta.get("data_root_idx", -1))
            if root_idx < 0 or root_idx >= len(counts):
                if self.data_mix_weights is None:
                    continue
                raise ValueError(
                    f"Invalid data_root_idx={root_idx} in metadata for {meta.get('traj_dir')}"
                )
            counts[root_idx] += int(meta["num_samples"])
        return counts

    def _validate_data_mix_sample_counts(self) -> None:
        if self.data_mix_weights is None:
            return
        for root_idx, (path, mix_weight, sample_count) in enumerate(
            zip(self.data_paths, self.data_mix_weights, self.root_sample_counts)
        ):
            if mix_weight > 0.0 and sample_count <= 0:
                raise ValueError(
                    f"data_mix_weights[{root_idx}]={mix_weight:.6g} but data_path has no samples: {path}"
                )

    def _metadata_sampling_weights(self) -> list[float]:
        if self.data_mix_weights is None:
            return [float(item["num_samples"]) for item in self.metadata]

        weights = []
        for meta in self.metadata:
            root_idx = int(meta["data_root_idx"])
            root_samples = self.root_sample_counts[root_idx]
            if root_samples <= 0:
                weights.append(0.0)
                continue
            weights.append(
                float(self.data_mix_weights[root_idx])
                * float(meta["num_samples"])
                / float(root_samples)
            )
        return weights

    def sample_window_weight(self, meta: dict) -> float:
        if self.data_mix_weights is None:
            return 1.0
        root_idx = int(meta["data_root_idx"])
        root_samples = self.root_sample_counts[root_idx]
        if root_samples <= 0:
            return 0.0
        return float(self.data_mix_weights[root_idx]) / float(root_samples)

    def data_mix_summary_str(self) -> str:
        if self.data_mix_weights is None:
            return "  data_mix_weights=disabled"
        lines = []
        for root_idx, (path, mix_weight, sample_count) in enumerate(
            zip(self.data_paths, self.data_mix_weights, self.root_sample_counts)
        ):
            lines.append(
                f"  root[{root_idx}] weight={mix_weight:.6f} samples={sample_count} path={path}"
            )
        return "\n".join(lines)

    def _normalization_method_for_key(self, norm_key: str) -> str:
        if norm_key == "proprio":
            return normalization_mode_to_method(self.state_normalization_mode)
        if norm_key == "action":
            return normalization_mode_to_method(self.action_normalization_mode)
        raise ValueError(f"Unsupported normalization key: {norm_key}")

    @staticmethod
    def _validate_stats_for_method(stats: dict, *, method: str, norm_key: str) -> None:
        required = METHOD_TO_REQUIRED_STATS[method]
        missing = [key for key in required if key not in stats]
        if missing:
            missing_text = ", ".join(missing)
            raise ValueError(
                f"{norm_key} normalization method '{method}' requires stats [{missing_text}], "
                "but they are missing from dataset_statistics."
            )

    def _validate_normalization_stats(self) -> None:
        self._validate_stats_for_method(
            self.dataset_statistics["proprio"],
            method=self._normalization_method_for_key("proprio"),
            norm_key="proprio",
        )
        self._validate_stats_for_method(
            self.dataset_statistics["action"],
            method=self._normalization_method_for_key("action"),
            norm_key="action",
        )

    def update_online_replay(self, traj_dirs: List[str]) -> int:
        if not traj_dirs:
            self._set_active_traj_dirs([])
            return 0

        num_new = 0
        normalized = []
        for traj_dir in traj_dirs:
            resolved = self._normalize_traj_dir(traj_dir)
            normalized.append(resolved)
            if resolved in self._traj_meta_cache:
                continue
            meta = self._build_traj_metadata(Path(resolved))
            self._traj_meta_cache[resolved] = meta
            num_new += 1

        self._set_active_traj_dirs(normalized)
        return num_new

    def plot_hist_prop_action(self):
        proprios = [item["proprio"] for item in self.metadata]
        actions = [item["action"] for item in self.metadata]

        proprios = np.concatenate(proprios)
        actions = np.concatenate(actions)
        # proprios and actions shape: [B, 7]
        self._plot_hist_single(proprios, actions, "original_hist.png")

        normed_proprios = self.normalize(proprios, norm_key="proprio")
        normed_actions = self.normalize(actions, norm_key="action")
        # normed_proprios and normed_proprios shape: [B, 7]
        self._plot_hist_single(normed_proprios, normed_actions, "normalized_hist.png")

    def _plot_hist_single(self, proprios, actions, filename):
        # create a fig with figsize=(15, 6)
        plt.figure(figsize=(15, 6))

        # Plot proprios dimensions (first row)
        for dim in range(7):
            plt.subplot(2, 7, dim + 1)
            plt.hist(proprios[:, dim], bins=50, color="skyblue", alpha=0.7)
            plt.title(f"Proprio Dim {dim}")
            plt.grid(True, linestyle="--", alpha=0.5)

        # Plot actions dimensions (second row)
        for dim in range(7):
            plt.subplot(2, 7, dim + 8)  # 8-14 for second row
            plt.hist(actions[:, dim], bins=50, color="salmon", alpha=0.7)
            plt.title(f"Action Dim {dim}")
            plt.grid(True, linestyle="--", alpha=0.5)

        # Adjust layout and save
        plt.tight_layout()
        output_path = os.path.join(self.data_path, filename)
        logger.info(f"Proprio and action histogram saved to {output_path}")
        plt.savefig(output_path)
        plt.close()

    def _overwrite_statistics(self, stats):
        """Overwrite action and proprio statistics when a robot preset is selected."""

        def _stat_array(block: dict, key: str, fallback: str) -> np.ndarray:
            source_key = key if key in block else fallback
            return np.asarray(block[source_key], dtype=np.float32).copy()

        if self.overwrite_stats == "piper_stack":
            # Temporary fix for current data (realman robot)
            # Single step move ~< 5cm; rotate ~< 5.8 deg = 0.1 rad
            # WARNING: These parameters only suited for v6 dataset
            action_q01 = _stat_array(stats["action"], "q01", "min")
            action_q99 = _stat_array(stats["action"], "q99", "max")
            action_q10 = _stat_array(stats["action"], "q10", "q01")
            action_q90 = _stat_array(stats["action"], "q90", "q99")

            bound_0199 = np.maximum(np.abs(action_q01[:6]), np.abs(action_q99[:6]))
            action_q01[:6] = -bound_0199
            action_q99[:6] = bound_0199
            bound_1090 = np.maximum(np.abs(action_q10[:6]), np.abs(action_q90[:6]))
            action_q10[:6] = -bound_1090
            action_q90[:6] = bound_1090

            action_q01[6] = 0.00
            action_q99[6] = 0.10
            action_q10[6] = 0.00
            action_q90[6] = 0.10

            stats["action"]["q01"] = action_q01.tolist()
            stats["action"]["q99"] = action_q99.tolist()
            stats["action"]["q10"] = action_q10.tolist()
            stats["action"]["q90"] = action_q90.tolist()

            proprio_q01 = _stat_array(stats["proprio"], "q01", "min")
            proprio_q99 = _stat_array(stats["proprio"], "q99", "max")
            proprio_q10 = _stat_array(stats["proprio"], "q10", "q01")
            proprio_q90 = _stat_array(stats["proprio"], "q90", "q99")
            # roll, pitch, yaw ranges from [-pi, +pi]
            # last dim = gripper absolute aperture in [0, 0.1]
            proprio_q99[3:] = [3.15, 3.15, 3.15, 0.10]
            proprio_q01[3:] = [-3.15, -3.15, -3.15, 0.00]
            proprio_q90[3:] = [3.15, 3.15, 3.15, 0.10]
            proprio_q10[3:] = [-3.15, -3.15, -3.15, 0.00]
            stats["proprio"]["q01"] = proprio_q01.tolist()
            stats["proprio"]["q99"] = proprio_q99.tolist()
            stats["proprio"]["q10"] = proprio_q10.tolist()
            stats["proprio"]["q90"] = proprio_q90.tolist()

            logger.warning("Overwriting action and proprio statistics with piper_stack")

        elif self.overwrite_stats == "piper_stack_old":
            # Temporary fix for current data (realman robot)
            # Single step move ~< 5cm; rotate ~< 5.8 deg = 0.1 rad
            # WARNING: These parameters only suited for v6 dataset
            fixed_action_q99 = [0.00993, 0.00765, 0.00763, 0.01989, 0.02801, 0.02468, 0.10]
            fixed_action_q01 = [-0.00993, -0.00765, -0.00763, -0.01989, -0.02801, -0.02468, 0.00]
            stats["action"]["q99"] = fixed_action_q99
            stats["action"]["q01"] = fixed_action_q01
            stats["action"]["q90"] = fixed_action_q99
            stats["action"]["q10"] = fixed_action_q01

            proprio_q01 = _stat_array(stats["proprio"], "q01", "min")
            proprio_q99 = _stat_array(stats["proprio"], "q99", "max")
            proprio_q10 = _stat_array(stats["proprio"], "q10", "q01")
            proprio_q90 = _stat_array(stats["proprio"], "q90", "q99")
            # roll, pitch, yaw ranges from [-pi, +pi]
            # last dim = gripper absolute aperture in [0, 0.1]
            proprio_q99[3:] = [3.15, 3.15, 3.15, 0.10]
            proprio_q01[3:] = [-3.15, -3.15, -3.15, 0.00]
            proprio_q90[3:] = [3.15, 3.15, 3.15, 0.10]
            proprio_q10[3:] = [-3.15, -3.15, -3.15, 0.00]
            stats["proprio"]["q01"] = proprio_q01.tolist()
            stats["proprio"]["q99"] = proprio_q99.tolist()
            stats["proprio"]["q10"] = proprio_q10.tolist()
            stats["proprio"]["q90"] = proprio_q90.tolist()

            logger.warning("Overwriting action and proprio statistics with piper_stack_old")

        for key in ["action", "proprio", "length"]:
            for stype in ["mean", "std", "max", "min", "q01", "q99", "q10", "q90"]:
                if stype in stats[key]:
                    stats[key][stype] = np.array(stats[key][stype])

        return stats

    @staticmethod
    def _format_stat_vector(values) -> str:
        arr = np.asarray(values, dtype=np.float32)
        return np.array2string(
            arr, precision=6, separator=", ", suppress_small=False, floatmode="maxprec_equal"
        )

    def normalization_summary_str(self) -> str:
        lines = [
            f"  stats_source={self.stats_source}",
            f"  stat_path={self.stat_path}",
            f"  overwrite_stats={self.overwrite_stats}",
            f"  state_normalization_mode={self.state_normalization_mode}",
            f"  action_normalization_mode={self.action_normalization_mode}",
            f"  action q01={self._format_stat_vector(self.dataset_statistics['action']['q01'])}",
            f"  action q99={self._format_stat_vector(self.dataset_statistics['action']['q99'])}",
            f"  proprio q01={self._format_stat_vector(self.dataset_statistics['proprio']['q01'])}",
            f"  proprio q99={self._format_stat_vector(self.dataset_statistics['proprio']['q99'])}",
        ]
        if (
            "q10" in self.dataset_statistics["action"]
            and "q90" in self.dataset_statistics["action"]
        ):
            lines.append(
                f"  action q10={self._format_stat_vector(self.dataset_statistics['action']['q10'])}"
            )
            lines.append(
                f"  action q90={self._format_stat_vector(self.dataset_statistics['action']['q90'])}"
            )
        if (
            "q10" in self.dataset_statistics["proprio"]
            and "q90" in self.dataset_statistics["proprio"]
        ):
            lines.append(
                f"  proprio q10={self._format_stat_vector(self.dataset_statistics['proprio']['q10'])}"
            )
            lines.append(
                f"  proprio q90={self._format_stat_vector(self.dataset_statistics['proprio']['q90'])}"
            )
        return "\n".join(lines)

    def _generate_statistics(self, metadata):

        proprios = [item["proprio"] for item in metadata]
        actions = [item["action"] for item in metadata]
        lengths = [item["num_steps"] for item in metadata]

        proprios = np.concatenate(proprios)
        actions = np.concatenate(actions)
        lengths = np.array(lengths)

        statistics = {
            "action": {
                "mean": actions.mean(0).tolist(),
                "std": actions.std(0).tolist(),
                "max": actions.max(0).tolist(),
                "min": actions.min(0).tolist(),
                "q01": np.quantile(actions, 0.01, axis=0).tolist(),
                "q10": np.quantile(actions, 0.10, axis=0).tolist(),
                "q90": np.quantile(actions, 0.90, axis=0).tolist(),
                "q99": np.quantile(actions, 0.99, axis=0).tolist(),
            },
            "proprio": {
                "mean": proprios.mean(0).tolist(),
                "std": proprios.std(0).tolist(),
                "max": proprios.max(0).tolist(),
                "min": proprios.min(0).tolist(),
                "q01": np.quantile(proprios, 0.01, axis=0).tolist(),
                "q10": np.quantile(proprios, 0.10, axis=0).tolist(),
                "q90": np.quantile(proprios, 0.90, axis=0).tolist(),
                "q99": np.quantile(proprios, 0.99, axis=0).tolist(),
            },
            "length": {
                "mean": lengths.mean()[None].tolist(),
                "std": lengths.std()[None].tolist(),
                "max": lengths.max()[None].tolist(),
                "min": lengths.min()[None].tolist(),
                "q01": np.quantile(lengths, 0.01)[None].tolist(),
                "q10": np.quantile(lengths, 0.10)[None].tolist(),
                "q90": np.quantile(lengths, 0.90)[None].tolist(),
                "q99": np.quantile(lengths, 0.99)[None].tolist(),
            },
            "num_transitions": len(metadata),
            "num_trajectories": int(lengths.sum()),
        }

        return statistics

    def _build_traj_metadata(self, traj: Path) -> dict:
        proprio, action = load_traj_proprio_action(traj, use_gripper_master=self.use_gripper_master)

        num_steps = self._get_num_steps(traj, self.image_key)
        if proprio.shape[0] != action.shape[0] or proprio.shape[0] != num_steps:
            raise ValueError(
                f"Trajectory length mismatch under {traj}: "
                f"proprio={proprio.shape[0]}, action={action.shape[0]}, images={num_steps}"
            )

        state_indices = np.arange(
            self.min_valid_state - self.state_hist_size, num_steps - self.min_valid_action + 1
        )
        state_indices = sliding_window_view(state_indices, self.state_hist_size, 0)
        state_mask = (state_indices < num_steps) & (state_indices >= 0)
        state_indices = np.clip(state_indices, 0, num_steps - 1)

        image_indices = state_indices.copy()
        proprio_chunk = proprio[state_indices]

        action_indices = np.arange(
            self.min_valid_state - 1, num_steps + self.action_future_size - self.min_valid_action
        )
        action_indices = sliding_window_view(action_indices, self.action_future_size, 0)
        action_mask = (action_indices < num_steps) & (action_indices >= 0)
        action_indices = np.clip(action_indices, 0, num_steps - 1)

        action_chunk = action[action_indices]

        instruction_file = traj / "task_instruction.txt"
        if os.path.isfile(instruction_file):
            with open(instruction_file, "r") as f:
                lang = f.read()
        else:
            lang = ""

        assert state_indices.shape[0] == action_indices.shape[0]
        num_samples = state_indices.shape[0]

        return {
            "proprio": proprio,
            "action": action,
            "num_steps": num_steps,
            "num_samples": num_samples,
            "lang_instr": lang,
            "image_path": self._normalize_traj_dir(traj),
            "state_indices": state_indices,
            "state_mask": state_mask,
            "action_indices": action_indices,
            "action_mask": action_mask,
            "image_indices": image_indices,
            "proprio_chunk": proprio_chunk,
            "action_chunk": action_chunk,
            "traj_dir": self._normalize_traj_dir(traj),
        }

    def _generate_metadata(self, train=True, train_ratio=1.0, base_path=None):
        """
        Generate metadata for a given base_path.
        """

        if base_path is None:
            base_path = self.data_path

        if self._is_traj_dir(base_path):
            traj_list = [base_path]
        else:
            traj_list = sorted(
                [
                    child
                    for child in base_path.iterdir()
                    if child.is_dir() and not child.is_symlink()
                ]
            )
        num_trajs = len(traj_list)

        train_ratio_x10 = int(train_ratio * 10)

        if train:
            traj_list = [val for ind, val in enumerate(traj_list) if ind % 10 < train_ratio_x10]
        else:
            traj_list = [val for ind, val in enumerate(traj_list) if ind % 10 >= train_ratio_x10]

        logger.info(f"process {len(traj_list)}/{num_trajs} trajectories")

        metadata = []
        for traj in tqdm(traj_list):
            metadata.append(self._build_traj_metadata(traj))
        return metadata

    @staticmethod
    def _copy_vector(input_vector):
        if isinstance(input_vector, (torch.Tensor, np.ndarray)):
            return input_vector
        return np.asarray(input_vector, dtype=np.float32)

    def _torch_stats_block(
        self, norm_key: str, *, device: torch.device, dtype: torch.dtype
    ) -> dict[str, torch.Tensor]:
        cache_key = (norm_key, str(device), dtype)
        cached = self._torch_stat_cache.get(cache_key)
        if cached is not None:
            return cached

        source = self.dataset_statistics[norm_key]
        cached = {
            stat_key: torch.as_tensor(
                np.asarray(stat_value, dtype=np.float32), device=device, dtype=dtype
            )
            for stat_key, stat_value in source.items()
            if isinstance(stat_value, np.ndarray)
        }
        self._torch_stat_cache[cache_key] = cached
        return cached

    def _stats_for_input(self, input_vector, *, norm_key: str):
        if isinstance(input_vector, torch.Tensor):
            dtype = input_vector.dtype if torch.is_floating_point(input_vector) else torch.float32
            return self._torch_stats_block(norm_key, device=input_vector.device, dtype=dtype)
        return self.dataset_statistics[norm_key]

    @classmethod
    def _normalize(cls, input_vector, stats, method="q01q99"):

        vector = cls._copy_vector(input_vector)

        if method == "minmax":
            vector = (vector - stats["min"]) / (stats["max"] - stats["min"])
            vector = (vector - 0.5) * 2
        elif method == "q01q99":
            vector = (vector - stats["q01"]) / (stats["q99"] - stats["q01"])
            vector = (vector - 0.5) * 2
        elif method == "q10q90":
            vector = (vector - stats["q10"]) / (stats["q90"] - stats["q10"])
            vector = (vector - 0.5) * 2
        elif method == "meanstd":
            vector = (vector - stats["mean"]) / (stats["std"] + EPS)
        else:
            raise ValueError(f"Unsupported normalization method: {method}")

        return vector

    def normalize(self, input_vector, norm_key="action", method=None):
        actual_method = method or self._normalization_method_for_key(norm_key)
        return self._normalize(
            input_vector, self._stats_for_input(input_vector, norm_key=norm_key), actual_method
        )

    @classmethod
    def _denormalize(cls, input_vector, stats, method="q01q99"):

        vector = cls._copy_vector(input_vector)

        if method == "minmax":
            vector = vector / 2 + 0.5
            vector = vector * (stats["max"] - stats["min"]) + stats["min"]
        elif method == "q01q99":
            vector = vector / 2 + 0.5
            vector = vector * (stats["q99"] - stats["q01"]) + stats["q01"]
        elif method == "q10q90":
            vector = vector / 2 + 0.5
            vector = vector * (stats["q90"] - stats["q10"]) + stats["q10"]
        elif method == "meanstd":
            vector = vector * (stats["std"] + EPS) + stats["mean"]
        else:
            raise ValueError(f"Unsupported denormalization method: {method}")

        return vector

    def denormalize(self, input_vector, norm_key="action", method=None):
        """Denormalize action or proprio values with the configured statistics."""
        actual_method = method or self._normalization_method_for_key(norm_key)
        return self._denormalize(
            input_vector, self._stats_for_input(input_vector, norm_key=norm_key), actual_method
        )

    @staticmethod
    def _image_root_key(traj_dir: Path | str) -> str:
        return str(Path(traj_dir))

    @staticmethod
    def _camera_array_name(image_key: str | None) -> str:
        return resolve_traj_image_array_name(image_key)

    def _image_array_path(self, traj_dir: Path | str, image_key: str | None) -> Path:
        return resolve_traj_image_array_path(traj_dir, image_key)

    @staticmethod
    def _validate_image_array(array: np.ndarray, *, path: Path) -> None:
        validate_traj_image_array(array, path=path)

    def _load_raw_image_sequence(self, traj_dir: Path | str, image_key: str) -> np.ndarray:
        return self._image_sequence_cache.get_sequence(traj_dir, image_key)

    def _get_num_steps(self, traj_dir: Path | str, image_key: str) -> int:
        return get_traj_num_steps(traj_dir, image_key)

    def _get_images(self, traj_dir, step_list, image_key):
        step_indices = np.asarray(step_list, dtype=np.int64)
        if self.debug:
            logger.info(
                f"Loading image array: {(self._image_root_key(traj_dir), image_key)} steps={step_list}"
            )
        raw_images = self._load_raw_image_sequence(traj_dir, image_key)
        selected_images = np.array(raw_images[step_indices], dtype=np.uint8, copy=True)
        if int(selected_images.shape[1]) != 3:
            selected_images = np.transpose(selected_images, (0, 3, 1, 2))
        images = torch.from_numpy(np.ascontiguousarray(selected_images))
        if self.use_img_aug:
            images = apply_sft_image_aug(images)
        images = rearrange(images, "chunk C H W -> chunk H W C")
        return images

    def _load_rl_meta_for_traj(self, traj_dir: Path) -> dict:
        key = str(traj_dir)
        if key in self._rl_meta_cache:
            return self._rl_meta_cache[key]

        chains_path = traj_dir / self.rl_chains_file
        denoise_path = traj_dir / self.rl_denoise_inds_file
        logp_path = traj_dir / self.rl_prev_logprobs_file

        if not (chains_path.is_file() and denoise_path.is_file() and logp_path.is_file()):
            if self.require_rl_meta:
                raise FileNotFoundError(f"Missing RL meta files in {traj_dir}")
            return {}

        meta = {
            "chains": np.load(chains_path, mmap_mode="r"),
            "denoise_inds": np.load(denoise_path, mmap_mode="r"),
            "prev_logprobs": np.load(logp_path, mmap_mode="r"),
        }

        if self.require_rl_meta:
            T = meta["prev_logprobs"].shape[0]
            if meta["chains"].shape[0] != T or meta["denoise_inds"].shape[0] != T:
                raise ValueError(
                    f"RL meta T mismatch in {traj_dir}: "
                    f"chains={meta['chains'].shape}, denoise={meta['denoise_inds'].shape}, logp={meta['prev_logprobs'].shape}"
                )

            prev_logprobs = meta["prev_logprobs"]
            if prev_logprobs.ndim == 3:
                chunk_dim = prev_logprobs.shape[1]
            elif prev_logprobs.ndim == 4:
                chunk_dim = prev_logprobs.shape[2]
            else:
                raise ValueError(
                    f"Unsupported prev_logprobs rank in {traj_dir}: shape={prev_logprobs.shape}"
                )
            if chunk_dim != self.action_future_size:
                raise ValueError(
                    f"prev_logprobs H mismatch in {traj_dir}: {prev_logprobs.shape} vs H={self.action_future_size}"
                )

        self._rl_meta_cache[key] = meta
        return meta

    def _get_data(self, sample, index):

        image_path = sample["image_path"]
        traj_dir = sample["traj_dir"]
        image_steps = sample["image_indices"][index].flatten().tolist()

        image_primary = self._get_images(image_path, image_steps, self.image_key)

        sample_dict = {
            "image_primary": image_primary,
            "proprio": self.normalize(sample["proprio_chunk"][index], norm_key="proprio"),
            "action": self.normalize(sample["action_chunk"][index], norm_key="action"),
            "state_mask": sample["state_mask"][index],
            "state_indices": sample["state_indices"][index],
            "action_mask": sample["action_mask"][index],
            "action_indices": sample["action_indices"][index],
            "instruction": sample["lang_instr"],
            "image_path": image_path,
            "traj_dir": traj_dir,
            "step_index": int(sample["action_indices"][index][0]),
        }
        if self.load_rl_meta:
            rl = self._load_rl_meta_for_traj(Path(traj_dir))

            if rl:
                t = sample_dict["step_index"]
                T = rl["prev_logprobs"].shape[0]
                if 0 <= t < T:
                    sample_dict["rl_chains"] = np.asarray(
                        rl["chains"][t], dtype=np.float32
                    )  # [K+1,H,7]
                    sample_dict["rl_denoise_inds"] = np.asarray(
                        rl["denoise_inds"][t], dtype=np.int32
                    )  # [K]
                    sample_dict["rl_prev_logprobs"] = np.asarray(
                        rl["prev_logprobs"][t], dtype=np.float32
                    )  # [H,7]
                elif self.require_rl_meta:
                    raise IndexError(f"step_index {t} out of range for {traj_dir} (T={T})")

        if self.wrist_key is not None:
            image_wrist = self._get_images(image_path, image_steps, self.wrist_key)
            sample_dict["image_wrist"] = image_wrist

        return sample_dict

    def __iter__(self):
        for _ in range(len(self.metadata)):
            sample = random.choices(self.metadata, weights=self.weights)[0]
            index = random.randint(0, sample["num_samples"] - 1)
            d = self._get_data(sample, index)
            yield d

    def __len__(self):
        return len(self.metadata)


class FinetuneSampleDataset(torch.utils.data.Dataset):
    """Map-style view over every sample window in a FinetuneDataset."""

    def __init__(self, base_ds: FinetuneDataset):
        super().__init__()
        self.base_ds = base_ds
        self.items: List[Tuple[int, int]] = []
        self.rebuild_items()

    def rebuild_items(self) -> None:
        self.items = []
        for traj_idx, meta in enumerate(self.base_ds.metadata):
            for sample_idx in range(int(meta["num_samples"])):
                self.items.append((traj_idx, sample_idx))

    def sample_weights(self) -> torch.Tensor | None:
        if self.base_ds.data_mix_weights is None:
            return None
        weights = [
            self.base_ds.sample_window_weight(self.base_ds.metadata[traj_idx])
            for traj_idx, _ in self.items
        ]
        return torch.as_tensor(weights, dtype=torch.double)

    def __getitem__(self, idx: int) -> dict:
        traj_idx, sample_idx = self.items[idx]
        meta = self.base_ds.metadata[traj_idx]
        sample = self.base_ds._get_data(meta, sample_idx)
        sample["traj_idx"] = traj_idx
        sample["sample_idx"] = sample_idx
        return sample

    def __len__(self) -> int:
        return len(self.items)


class DistributedWeightedSampler(torch.utils.data.Sampler):
    """DDP-safe weighted sampler over a map-style dataset.

    The sampler draws a full global epoch with replacement according to
    sample-level weights, then shards those indices by rank. This keeps the
    configured root mixture identical across single-GPU and multi-GPU SFT.
    """

    def __init__(
        self, weights: torch.Tensor, *, num_replicas: int, rank: int, seed: int = 0
    ) -> None:
        if weights.ndim != 1:
            raise ValueError(f"weights must be 1-D, got shape {tuple(weights.shape)}")
        if weights.numel() <= 0:
            raise ValueError("weights must be non-empty")
        if num_replicas <= 0:
            raise ValueError(f"num_replicas must be positive, got {num_replicas}")
        if rank < 0 or rank >= num_replicas:
            raise ValueError(f"rank must be in [0, {num_replicas}), got {rank}")

        weights = weights.to(dtype=torch.double, device="cpu")
        if not torch.isfinite(weights).all():
            raise ValueError("weights contain non-finite values")
        if torch.any(weights < 0):
            raise ValueError("weights must be non-negative")
        if float(weights.sum().item()) <= 0.0:
            raise ValueError("weights must have positive sum")

        self.weights = weights
        self.num_replicas = int(num_replicas)
        self.rank = int(rank)
        self.seed = int(seed)
        self.epoch = 0
        self.num_samples = int(np.ceil(len(self.weights) / self.num_replicas))
        self.total_size = self.num_samples * self.num_replicas

    def __iter__(self):
        generator = torch.Generator()
        generator.manual_seed(self.seed + self.epoch)
        indices = torch.multinomial(
            self.weights, self.total_size, replacement=True, generator=generator
        ).tolist()
        indices = indices[self.rank : self.total_size : self.num_replicas]
        if len(indices) != self.num_samples:
            raise RuntimeError(f"Sampler shard size mismatch: {len(indices)} vs {self.num_samples}")
        return iter(indices)

    def __len__(self) -> int:
        return self.num_samples

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)


class ValueDatasetRealRL(torch.utils.data.IterableDataset):
    """Dataset for value function training on base + round_x data.

    - Uses the same observation modalities (image / proprio / language) as SFT, reusing FinetuneDataset's metadata and preprocessing
    - Constructs returns based on is_human.npy:
        * No is_human or all 0: treated as base data, reward=1 at trajectory end
        * Human intervention exists: let t_h be the first non-zero position:
            - Failed trajectory: [0, t_h) all reward=0
            - Successful trajectory: [0, T) reward=1 at end
    - Computes discounted return G_t for each step using gamma to supervise value function
    - Does not modify original data, only builds indices and targets in memory
    """

    def __init__(self, config, train: bool = True):
        super().__init__()

        # Discount factor from config, default 0.99
        self.gamma: float = float(getattr(config, "gamma", 0.99))

        # Reuse FinetuneDataset to generate metadata / statistics etc.
        # FinetuneDataset now supports data_path=None for validation-only scenarios
        self.base_ds = FinetuneDataset(config, train=train)
        self.metadata = self.base_ds.metadata

        # value_samples: List[(traj_index, step_index, value_target)]
        # where traj_index indexes self.metadata
        self.value_samples: List[Tuple[int, int, float]] = []

        self._build_value_samples()
        logger.info(
            f"ValueDatasetRealRL built with {len(self.value_samples)} value samples "
            f"from {len(self.metadata)} trajectories (gamma={self.gamma})."
        )

    def _load_is_human(self, traj_dir: Path, num_steps: int) -> np.ndarray:
        """Load is_human.npy if present, otherwise return a boolean array.

        The canonical format is a 1D bool array of length ``num_steps``.
        Any loaded array is converted to bool and then truncated/padded with
        ``False`` to match ``num_steps``.
        """

        is_human_path = traj_dir / "is_human.npy"
        if is_human_path.is_file():
            is_human = np.load(is_human_path)
            if is_human.ndim > 1:
                is_human = is_human.reshape(-1)
            is_human = is_human.astype(bool)
            assert len(is_human) == num_steps, (
                f"is_human.npy length {len(is_human)} does not match num_steps {num_steps} "
                f"in trajectory {traj_dir}"
            )
        else:
            is_human = np.zeros(num_steps, dtype=bool)
        return is_human

    def _discount_returns(self, rewards: np.ndarray) -> np.ndarray:
        """Compute discounted returns G_t from rewards with gamma.

        G_t = r_t + gamma * G_{t+1}
        """
        T = len(rewards)
        returns = np.zeros(T, dtype=np.float32)
        running = 0.0
        for t in range(T - 1, -1, -1):
            running = float(rewards[t]) + self.gamma * running
            returns[t] = running
        return returns

    def _build_value_samples(self) -> None:
        """Construct (meta, sample_idx, value_target) tuples for all trajectories.

        The value target for each sample is based on the action_indices, specifically
        the first action index in the action_future window."""
        for traj_idx, meta in enumerate(self.metadata):
            traj_dir = Path(meta["traj_dir"])
            num_steps: int = int(meta["num_steps"])
            num_samples: int = int(meta["num_samples"])

            is_human = self._load_is_human(traj_dir, num_steps)

            # First compute step-level returns
            if np.any(is_human):
                # Human intervention exists: use first non-zero position as boundary
                first_human_idx = int(np.argmax(is_human))

                # We'll create two sets of returns: fail and success
                # For step t, we'll use fail if t < first_human_idx, else success

                # Failed trajectory: [0, first_human_idx), all reward=0
                fail_rewards = np.zeros(num_steps, dtype=np.float32)
                fail_returns = self._discount_returns(fail_rewards)

                # Successful trajectory: [0, num_steps), reward=1 at end
                succ_rewards = np.zeros(num_steps, dtype=np.float32)
                succ_rewards[-1] = 1.0
                succ_returns = self._discount_returns(succ_rewards)

                # Choose which return to use for each step
                step_returns = np.where(
                    np.arange(num_steps) < first_human_idx, fail_returns, succ_returns
                )
            else:
                # No human intervention: same as base data, reward=1 at end
                rewards = np.zeros(num_steps, dtype=np.float32)
                rewards[-1] = 1.0
                step_returns = self._discount_returns(rewards)

            # For each sample, use the return at the first action index
            action_indices = meta["action_indices"]  # shape: [num_samples, action_future_size]

            for sample_idx in range(num_samples):
                # Use the return value at the first action timestep
                first_action_idx = action_indices[sample_idx, 0]
                value_target = float(step_returns[first_action_idx])
                self.value_samples.append((traj_idx, sample_idx, value_target))

    def __iter__(self) -> Iterator[dict]:
        """Yield samples indexed by trajectory window."""
        # Shuffle sample order for each epoch
        indices = np.arange(len(self.value_samples))
        np.random.shuffle(indices)

        for idx in indices:
            traj_idx, sample_idx, value_target = self.value_samples[idx]

            meta = self.metadata[traj_idx]
            sample = self.base_ds._get_data(meta, sample_idx)
            sample["value_target"] = torch.tensor(value_target, dtype=torch.float32)
            yield sample

    def __len__(self) -> int:
        return len(self.value_samples)
