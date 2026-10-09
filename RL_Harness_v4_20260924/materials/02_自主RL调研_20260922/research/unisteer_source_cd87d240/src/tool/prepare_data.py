from __future__ import annotations

import argparse
import os
from pathlib import Path

from loguru import logger
import numpy as np
from PIL import Image

CAMERAS = {"primary_image_crop": "primary.npy", "wrist_image_crop": "wrist.npy"}


def _frame_paths(frame_dir: Path) -> list[Path]:
    paths = list(frame_dir.glob("*.jpg"))
    if not paths:
        raise FileNotFoundError(f"No JPEG frames found under {frame_dir}")
    try:
        return sorted(paths, key=lambda path: int(path.stem))
    except ValueError as exc:
        raise ValueError(f"Frame filenames must use integer indices under {frame_dir}") from exc


def _read_rgb_chw(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    return np.ascontiguousarray(np.transpose(rgb, (2, 0, 1)))


def _convert_camera(traj_dir: Path, camera_dir_name: str, output_name: str, num_steps: int) -> bool:
    output_path = traj_dir / output_name
    if output_path.is_file():
        return False

    frame_paths = _frame_paths(traj_dir / "images" / camera_dir_name)
    if len(frame_paths) != num_steps:
        raise ValueError(
            f"Image / action length mismatch under {traj_dir}: {len(frame_paths)} vs {num_steps}"
        )

    first_frame = _read_rgb_chw(frame_paths[0])
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    try:
        output = np.lib.format.open_memmap(
            temp_path, mode="w+", dtype=np.uint8, shape=(num_steps, *first_frame.shape)
        )
        output[0] = first_frame
        for index, frame_path in enumerate(frame_paths[1:], start=1):
            frame = _read_rgb_chw(frame_path)
            if frame.shape != first_frame.shape:
                raise ValueError(
                    f"Inconsistent image shape under {frame_path.parent}: {frame.shape} vs {first_frame.shape}"
                )
            output[index] = frame
        output.flush()
        del output
        os.replace(temp_path, output_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return True


def _trajectory_dirs(data_root: Path) -> list[Path]:
    if (data_root / "action.npy").is_file():
        return [data_root]
    trajectories = sorted(
        path
        for path in data_root.iterdir()
        if path.is_dir() and not path.is_symlink() and (path / "action.npy").is_file()
    )
    if not trajectories:
        raise FileNotFoundError(f"No trajectory directories found under {data_root}")
    return trajectories


def prepare_data(data_root: Path) -> dict[str, int]:
    root = data_root.expanduser().resolve()
    converted = 0
    reused = 0
    trajectories = _trajectory_dirs(root)
    for traj_dir in trajectories:
        if all((traj_dir / output_name).is_file() for output_name in CAMERAS.values()):
            reused += len(CAMERAS)
            continue
        action = np.load(traj_dir / "action.npy", mmap_mode="r")
        if action.ndim != 2:
            raise ValueError(
                f"Expected action.npy rank 2 under {traj_dir}, got shape={list(action.shape)}"
            )
        num_steps = int(action.shape[0])
        for camera_dir_name, output_name in CAMERAS.items():
            if _convert_camera(traj_dir, camera_dir_name, output_name, num_steps):
                converted += 1
            else:
                reused += 1
    result = {
        "trajectories": len(trajectories),
        "converted_arrays": converted,
        "reused_arrays": reused,
    }
    logger.info(
        "Trajectory image arrays ready | "
        f"trajectories={result['trajectories']} converted={converted} reused={reused}"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare trajectory image arrays")
    parser.add_argument("--data-root", required=True)
    args = parser.parse_args()
    prepare_data(Path(args.data_root))


if __name__ == "__main__":
    main()
