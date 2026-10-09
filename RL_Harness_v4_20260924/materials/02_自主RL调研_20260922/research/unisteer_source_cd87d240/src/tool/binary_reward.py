from __future__ import annotations

from typing import Any, Mapping

BINARY_REWARD_BACKEND = "binary_reward"


def build_binary_reward_sequence(*, num_chunks: int, success: bool) -> list[float]:
    num_chunks = int(num_chunks)
    if num_chunks <= 0:
        raise ValueError(f"num_chunks must be positive, got {num_chunks}")

    rewards = [0.0] * num_chunks
    if success:
        rewards[-1] = 1.0
    return rewards


def validate_binary_reward_sidecar(
    *,
    summary: Mapping[str, Any],
    decision_scores: Mapping[str, Any],
    success: bool,
    num_chunks: int,
    final_decision_index: int,
) -> None:
    backend = str(summary.get("backend", ""))
    if backend != BINARY_REWARD_BACKEND:
        raise ValueError(f"Expected reward backend {BINARY_REWARD_BACKEND!r}, got {backend!r}")

    required_summary_keys = ("success", "num_noise_chunks", "terminal", "done", "done_index")
    missing = [key for key in required_summary_keys if key not in summary]
    if missing:
        raise KeyError(f"Missing binary-reward summary fields: {missing}")
    if bool(summary["success"]) != bool(success):
        raise ValueError(
            "Binary-reward success mismatch: "
            f"sidecar={bool(summary['success'])}, trajectory={bool(success)}"
        )
    if not bool(summary["terminal"]) or not bool(summary["done"]):
        raise ValueError("Binary-reward sidecar must mark the final transition terminal and done")
    if int(summary["done_index"]) != int(final_decision_index):
        raise ValueError(
            "Binary-reward done-index mismatch: "
            f"sidecar={int(summary['done_index'])}, trajectory={int(final_decision_index)}"
        )
    if int(summary["num_noise_chunks"]) != int(num_chunks):
        raise ValueError(
            "Binary-reward chunk-count mismatch: "
            f"sidecar={int(summary['num_noise_chunks'])}, trajectory={int(num_chunks)}"
        )

    rewards = decision_scores.get("reward")
    if not isinstance(rewards, list) or len(rewards) != int(num_chunks):
        raise ValueError(
            f"Invalid binary-reward length: expected={num_chunks}, got="
            f"{len(rewards) if isinstance(rewards, list) else type(rewards).__name__}"
        )
    expected_rewards = build_binary_reward_sequence(num_chunks=num_chunks, success=success)
    if [float(value) for value in rewards] != expected_rewards:
        raise ValueError(f"Invalid binary rewards: actual={rewards}, expected={expected_rewards}")
