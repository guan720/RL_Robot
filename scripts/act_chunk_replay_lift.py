#!/usr/bin/env python3
"""ACT-style fixed-length action-chunk replay baseline for scripted Lift."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.env_factory import (  # noqa: E402
    PINNED_OBJECT_SEED,
    contact_object_geom,
    make_contact_env,
    reset_contact,
)
from scripts.demo_scripted_lift_rs import LiftStateMachine, _cube_pos  # noqa: E402
from scripts.probe_contact_ceiling import grasp_truth_fn  # noqa: E402


def record_teacher(env, seed: int, horizon: int) -> dict:
    reset_contact(env, seed)
    raw = env._env._get_observations()
    initial_z = float(_cube_pos(raw)[2])
    teacher = LiftStateMachine(cube_z0=initial_z)
    frames = []
    for _ in range(horizon):
        phase = str(teacher.phase)
        action = np.asarray(teacher(raw), dtype=np.float32).copy()
        frames.append({"action": action.tolist(), "phase": phase})
        _, _, terminated, truncated, _ = env.step(action)
        raw = env._env._get_observations()
        if terminated or truncated:
            break
    return {"seed": seed, "frames": frames}


def replay_chunks(env, trajectory: dict, chunk_length: int) -> dict:
    started = time.perf_counter()
    seed = int(trajectory["seed"])
    reset_contact(env, seed)
    raw = env._env._get_observations()
    initial_z = float(_cube_pos(raw)[2])
    grasp_fn = grasp_truth_fn(env, "lift")
    frames = trajectory["frames"]
    rows, chunks, phases = [], [], []
    raw_success = False
    grasp_verified = False
    max_rise = 0.0
    step = 0
    request_id = 0
    terminated = truncated = False
    while step < len(frames):
        selected = frames[step:step + chunk_length]
        mask = []
        for chunk_index, frame in enumerate(selected):
            _, _, terminated, truncated, info = env.step(np.asarray(frame["action"], dtype=np.float32))
            raw = env._env._get_observations()
            max_rise = max(max_rise, float(_cube_pos(raw)[2]) - initial_z)
            raw_success = raw_success or bool(info.get("success", False))
            current_grasp = bool(grasp_fn()) if grasp_fn is not None else False
            grasp_verified = grasp_verified or current_grasp
            phase = str(frame["phase"])
            phases.append(phase)
            mask.append(True)
            rows.append({
                "step": step,
                "request_id": request_id,
                "chunk_index": chunk_index,
                "chunk_length": len(selected),
                "activated": True,
                "phase": phase,
                "grasp_verified": current_grasp,
                "raw_success": bool(raw_success),
            })
            step += 1
            if terminated or truncated:
                break
        chunks.append({
            "request_id": request_id,
            "start_step": step - len(mask),
            "chunk_length": len(selected),
            "actual_activation_mask": mask,
            "phase": selected[0]["phase"] if selected else "",
        })
        request_id += 1
        if terminated or truncated:
            break
    return {
        "seed": seed,
        "success_raw": bool(raw_success),
        "grasp_verified": bool(grasp_verified),
        "success_grasp_verified": bool(raw_success and grasp_verified),
        "max_rise": float(max_rise),
        "failure_phase": "" if raw_success else (phases[-1] if phases else "unknown"),
        "phase_trace": phases,
        "steps": len(rows),
        "elapsed_sec": time.perf_counter() - started,
        "chunks": chunks,
        "frame_records": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=5000)
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--chunk-length", type=int, default=4)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.chunk_length <= 0:
        raise SystemExit("--chunk-length must be positive")

    teacher_env = make_contact_env("lift", horizon=args.horizon, reward_shaping=True, obs_mode="state")
    replay_env = make_contact_env("lift", horizon=args.horizon, reward_shaping=True, obs_mode="state")
    rows = []
    try:
        for i in range(args.episodes):
            trajectory = record_teacher(teacher_env, args.seed0 + i, args.horizon)
            rows.append(replay_chunks(replay_env, trajectory, args.chunk_length))
        geometry = contact_object_geom(replay_env, "lift", PINNED_OBJECT_SEED)
    finally:
        teacher_env.close()
        replay_env.close()

    n = len(rows)
    out = {
        "controller": "scripted_teacher_act_chunk_replay",
        "task": "lift",
        "episodes": n,
        "seed0": args.seed0,
        "horizon": args.horizon,
        "chunk_length": args.chunk_length,
        "pinned_object_seed": PINNED_OBJECT_SEED,
        "object_geom": geometry,
        "success_raw": sum(int(r["success_raw"]) for r in rows),
        "success_raw_rate": sum(int(r["success_raw"]) for r in rows) / max(1, n),
        "grasp_verified_episodes": sum(int(r["grasp_verified"]) for r in rows),
        "success_grasp_verified": sum(int(r["success_grasp_verified"]) for r in rows),
        "success_grasp_verified_rate": sum(int(r["success_grasp_verified"]) for r in rows) / max(1, n),
        "mean_max_rise": sum(float(r["max_rise"]) for r in rows) / max(1, n),
        "failure_phase_counts": {
            phase: sum(1 for r in rows if r["failure_phase"] == phase)
            for phase in sorted({r["failure_phase"] for r in rows if r["failure_phase"]})
        },
        "harness_recovery_episodes": 0,
        "rows": rows,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
