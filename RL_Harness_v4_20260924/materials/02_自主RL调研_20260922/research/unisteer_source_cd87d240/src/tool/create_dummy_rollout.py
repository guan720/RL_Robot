from __future__ import annotations

import argparse
import json
from pathlib import Path

import msgpack
import numpy as np


def create_dummy_rollout(
    output_dir: str | Path,
    *,
    success: bool,
    num_steps: int = 3,
    state_dim: int = 2055,
    noise_action_dim: int = 32,
) -> Path:
    if num_steps <= 0:
        raise ValueError(f"num_steps must be positive, got {num_steps}")

    trajectory_dir = Path(output_dir).expanduser().resolve()
    trajectory_dir.mkdir(parents=True, exist_ok=True)

    images = np.zeros((num_steps, 3, 224, 224), dtype=np.uint8)
    proprio = np.zeros((num_steps, 7), dtype=np.float32)
    action = np.zeros((num_steps, 7), dtype=np.float32)
    np.save(trajectory_dir / "primary.npy", images)
    np.save(trajectory_dir / "wrist.npy", images)
    np.save(trajectory_dir / "proprio.npy", proprio)
    np.save(trajectory_dir / "action.npy", action)
    np.save(trajectory_dir / "is_human.npy", np.zeros(num_steps, dtype=bool))

    task_description = "pick up the spoon"
    (trajectory_dir / "task_instruction.txt").write_text(task_description, encoding="utf-8")
    (trajectory_dir / "meta.json").write_text(
        json.dumps(
            {
                "task": task_description,
                "success": bool(success),
                "is_reset": False,
                "human_collect": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    decision_indices = list(range(num_steps))
    steps = [
        {
            "step_index": step_index,
            "state": np.zeros(state_dim, dtype=np.float32).tolist(),
            "noise_action": np.zeros(noise_action_dim, dtype=np.float32).tolist(),
        }
        for step_index in decision_indices
    ]
    episode = {
        "request_id": trajectory_dir.name,
        "task_description": task_description,
        "decision_indices": decision_indices,
        "steps": steps,
    }
    (trajectory_dir / "unisteer_episode.msgpack").write_bytes(
        msgpack.packb(episode, use_bin_type=True)
    )
    return trajectory_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a synthetic local UniSteer rollout")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--success", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--num-steps", type=int, default=3)
    parser.add_argument("--state-dim", type=int, default=2055)
    parser.add_argument("--noise-action-dim", type=int, default=32)
    args = parser.parse_args()

    output = create_dummy_rollout(
        args.output_dir,
        success=bool(args.success),
        num_steps=int(args.num_steps),
        state_dim=int(args.state_dim),
        noise_action_dim=int(args.noise_action_dim),
    )
    print(output)


if __name__ == "__main__":
    main()
