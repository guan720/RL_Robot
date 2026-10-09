#!/usr/bin/env python3
"""只读审计 from-scratch SAC Lift checkpoint 的物理真值。"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stable_baselines3 import SAC  # noqa: E402
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env, reset_contact  # noqa: E402
from scripts.probe_contact_ceiling import grasp_truth_fn  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ckpt', required=True)
    ap.add_argument('--episodes', type=int, default=20)
    ap.add_argument('--seed0', type=int, default=5000)
    ap.add_argument('--horizon', type=int, default=300)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    with __import__('harness.env_factory', fromlist=['pinned_object_rng']).pinned_object_rng(PINNED_OBJECT_SEED):
        env = make_contact_env('lift', horizon=args.horizon, reward_shaping=True, obs_mode='state')
    model = SAC.load(args.ckpt, device='cpu')
    rows = []
    try:
        for i in range(args.episodes):
            seed = args.seed0 + i
            obs = reset_contact(env, seed)
            truth = grasp_truth_fn(env, 'lift')
            raw0 = env._env._get_observations()
            z0 = float(np.asarray(raw0['cube_pos'])[2])
            raw_success = False; held = False; max_rise = 0.0; phases = []
            for step in range(args.horizon):
                action, _ = model.predict(obs, deterministic=True)
                obs, _, term, trunc, info = env.step(action)
                raw = env._env._get_observations()
                max_rise = max(max_rise, float(np.asarray(raw['cube_pos'])[2]) - z0)
                raw_success = raw_success or bool(info.get('success', False))
                if truth is not None:
                    held = held or bool(truth())
                phase = str(info.get('phase', ''))
                if phase and (not phases or phases[-1] != phase): phases.append(phase)
                if term or trunc: break
            success_grasp = bool(raw_success and held)
            success_rise = bool(max_rise >= 0.04)
            failure = '' if success_grasp else (phases[-1] if phases else 'unknown')
            rows.append({'seed': seed, 'raw_success': raw_success,
                         'grasp_verified': held, 'success_grasp_verified': success_grasp,
                         'success_rise': success_rise, 'max_rise': round(max_rise, 6),
                         'phase_trace': phases, 'failure_phase': failure, 'steps': step + 1})
    finally:
        env.close()
    n = len(rows)
    out = {'ckpt': str(Path(args.ckpt).resolve()), 'controller': 'from-scratch SAC',
           'task': 'lift', 'episodes': n, 'seed0': args.seed0, 'horizon': args.horizon,
           'pinned_object_seed': PINNED_OBJECT_SEED,
           'success_raw': sum(r['raw_success'] for r in rows),
           'success_raw_rate': sum(r['raw_success'] for r in rows) / max(1, n),
           'grasp_verified_episodes': sum(r['grasp_verified'] for r in rows),
           'success_grasp_verified': sum(r['success_grasp_verified'] for r in rows),
           'success_grasp_verified_rate': sum(r['success_grasp_verified'] for r in rows) / max(1, n),
           'success_rise': sum(r['success_rise'] for r in rows),
           'success_rise_rate': sum(r['success_rise'] for r in rows) / max(1, n),
           'mean_max_rise': float(np.mean([r['max_rise'] for r in rows])),
           'failure_phase_counts': {p: sum(r['failure_phase'] == p for r in rows)
                                    for p in sorted({r['failure_phase'] for r in rows if r['failure_phase']})},
           'rows': rows}
    path = Path(args.out); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in out.items() if k != 'rows'}, indent=2, ensure_ascii=False))


if __name__ == '__main__': main()
