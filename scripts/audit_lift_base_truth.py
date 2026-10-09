#!/usr/bin/env python3
"""只读审计 scripted/base-only Lift 的逐局物理真值。

评测与 residual 审计使用同一 pinned object、reset seed、horizon 和 grasp
真值判据。结果保留逐局记录，供配对审计使用；本脚本不训练、不写模型。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env  # noqa: E402
from scripts.probe_contact_ceiling import (  # noqa: E402
    make_scripted_factory,
    run_one,
)


def failure_phase(row: dict) -> str:
    """将结构化失败标签映射到监管报告需要的阶段名。"""
    if row.get("success_grasp"):
        return ""
    return {
        "no_reach": "approach",
        "reach_no_close": "grasp",
        "reach_no_hold": "grasp",
        "grasp_no_lift": "lift",
        "lifted_below": "lift",
        "dropped": "hold",
        "success_flick": "grasp/lift (flick)",
    }.get(str(row.get("label", "")), str(row.get("phase_at_end", "")))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=5000)
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    env = make_contact_env("lift", horizon=args.horizon, reward_shaping=True, obs_mode="state")
    factory = make_scripted_factory("lift", env)
    rows = []
    try:
        for i in range(args.episodes):
            started = time.perf_counter()
            row = run_one(
                env, "lift", None, args.seed0 + i, args.horizon,
                stop_on_success=False, controller_factory=factory,
                # All scripted successful rows are above any failure threshold;
                # this value is only used when a run genuinely fails.
                cal={"lift_ok": 0.04, "near": 0.02},
            )
            row["raw_success"] = bool(row.get("success"))
            row["grasp_verified"] = bool(row.get("held"))
            row["success_grasp_verified"] = bool(row.get("success_grasp"))
            # Lift 的物理成功线是 cube 相对出生高度至少上升 4 cm。
            row["success_rise"] = bool(float(row.get("max_rise", 0.0)) >= 0.04)
            row["phase_trace"] = list(row.get("phases") or [])
            row["failure_phase"] = failure_phase(row)
            row["elapsed_sec"] = time.perf_counter() - started
            rows.append(row)
    finally:
        env.close()

    n = len(rows)
    out = {
        "controller": "scripted/base-only",
        "task": "lift",
        "episodes": n,
        "seed0": args.seed0,
        "horizon": args.horizon,
        "pinned_object_seed": PINNED_OBJECT_SEED,
        "success_raw": sum(r["raw_success"] for r in rows),
        "success_raw_rate": sum(r["raw_success"] for r in rows) / max(1, n),
        "grasp_verified_episodes": sum(r["grasp_verified"] for r in rows),
        "success_grasp_verified": sum(r["success_grasp_verified"] for r in rows),
        "success_grasp_verified_rate": sum(r["success_grasp_verified"] for r in rows) / max(1, n),
        "mean_max_rise": sum(float(r["max_rise"]) for r in rows) / max(1, n),
        "failure_phase_counts": {
            p: sum(1 for r in rows if r["failure_phase"] == p)
            for p in sorted({r["failure_phase"] for r in rows if r["failure_phase"]})
        },
        "rows": rows,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
