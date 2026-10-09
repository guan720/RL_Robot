#!/usr/bin/env python
"""Truth-based audit for a bounded-residual Lift checkpoint.

门禁字段（2026-09-28 追加，交付 B 的 `docs/b_handoff_to_a_20260928.md` 交接单 2）：
每局额外输出 `final_rise / held_at_end / phase_at_end / rise_at_success / terminal_kind`，
使 `scripts/b_gate_controlled_success.py`（v1.2.1）能判 C4「局末仍夹持」与 C5「抬起高度」，
不再退化成 `provisional_pass`。字段语义与 `scripts/eval_lerobot_act_runtime.py:330-380`
（B 认可的参考实现）逐条对齐：
  - `grasp_verified` 保持 **held_ever**（任一帧夹住过）语义不变，`held_at_end` 是独立字段；
  - `terminal_kind` 不把跑满 horizon 标成 failure（`horizon_exhausted`），避免门禁的
    `suspect_truncation_labeled_as_failure` 自检报警；
  - 只**追加**字段，原有键与算法一字节未改，因此与 09-24 留档产物可直接对比。
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stable_baselines3 import SAC
from envs.residual_lift import ResidualLiftEnv
from harness.env_factory import PINNED_OBJECT_SEED, pinned_object_rng, reset_contact
from scripts.probe_contact_ceiling import grasp_truth_fn

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ckpt', required=True); ap.add_argument('--episodes', type=int, default=20)
    ap.add_argument('--seed0', type=int, default=5000); ap.add_argument('--horizon', type=int, default=300)
    ap.add_argument('--residual-scale', type=float, default=0.25); ap.add_argument('--residual-phases', default='grasp,lift')
    ap.add_argument('--out', default=''); args = ap.parse_args()
    phases = tuple(x.strip() for x in args.residual_phases.split(',') if x.strip())
    with pinned_object_rng(PINNED_OBJECT_SEED):
        env = ResidualLiftEnv(obs_mode='state', horizon=args.horizon, reward_shaping=True,
                              residual_scale=args.residual_scale, residual_phases=phases)
    model = SAC.load(args.ckpt, device='cpu'); rows = []
    for i in range(args.episodes):
        seed = args.seed0 + i; obs = reset_contact(env, seed); truth = grasp_truth_fn(env, 'lift')
        held = success = False; max_rise = 0.0; phases_seen = []; residual_norm = 0.0; active = 0
        final_rise = 0.0; held_at_end = False; rise_at_success = None; last_phase = ''
        terminal_kind = 'horizon_exhausted'
        raw0 = env._env._get_observations(); z0 = float(np.asarray(raw0['cube_pos'])[2])
        for step in range(args.horizon):
            action, _ = model.predict(obs, deterministic=True); obs, _, term, trunc, info = env.step(action)
            raw = env._env._get_observations()
            rise = float(np.asarray(raw['cube_pos'])[2]) - z0
            max_rise = max(max_rise, rise); final_rise = rise
            succ_now = bool(info.get('success', False))
            if succ_now and rise_at_success is None: rise_at_success = rise
            held_now = bool(truth()); held_at_end = held_now
            success = success or succ_now; held = held or held_now
            phase = str(info.get('phase', ''))
            if phase: last_phase = phase
            if phase and (not phases_seen or phases_seen[-1] != phase): phases_seen.append(phase)
            residual_norm += float(np.linalg.norm(np.asarray(info.get('residual_action', 0.0))))
            active += int(np.any(np.asarray(info.get('residual_gate', 0.0))))
            if term or trunc:
                terminal_kind = 'environment_done' if term else 'horizon_exhausted'
                break
        rows.append({'seed': seed, 'success_raw': success, 'grasp_verified': held,
                     'success_grasp_verified': bool(success and held), 'max_rise': round(max_rise, 6),
                     'final_rise': round(final_rise, 6), 'held_at_end': held_at_end,
                     'phase_at_end': (last_phase or (phases_seen[-1] if phases_seen else '')),
                     'rise_at_success': (round(rise_at_success, 6) if rise_at_success is not None else None),
                     'terminal_kind': terminal_kind,
                     'steps': step + 1, 'phases': phases_seen,
                     # 与参考实现 scripts/audit_lift_base_truth.py:66 同名同义：门禁靠
                     # `phase_trace` 分辨「6 元素状态机日志」与「逐帧 phase_of 分类」两套词表
                     # （b_gate_controlled_success.py:96 classify_phase_field）。只写 `phases`
                     # 会让状态机的 'done' 被 per-frame 规则判成非夹持 -> 20/20 真夹持被误判 flick。
                     'phase_trace': list(phases_seen),
                     'residual_norm_sum': round(residual_norm, 6),
                     'residual_active_steps': active,
                     'guard_interventions': 0, 'recovery_events': 0})
    env.close(); n = len(rows)
    result = {'ckpt': str(Path(args.ckpt).resolve()), 'task': 'lift',
              'controller': 'SAC bounded residual on scripted LiftStateMachine base',
              # 这条臂的能力来自「scripted base + 有界 residual + 动作 clip」的复合体，
              # 不是从零学出的策略。按门禁 v1.2.1 §2.8 必须显式声明，让裁定自动标
              # composite_policy=true，避免 20/20 被当成 learned-from-scratch 的能力引用。
              'execution_constraints': {
                  'scripted_base_controller': 'envs/residual_lift.py:49 a = clip(a_base + scale*a_residual, -1, 1)',
                  'residual_scale': args.residual_scale,
                  'residual_phases': ','.join(phases),
                  'action_clip': '[-1,1]',
              },
              # SAC 直接吃 raw 60 维 state obs（train_residual_lift.py 未用 VecNormalize/normalize_obs），
              # 因此不存在「归一化输入」，增补二 §3 的 norm_input_blown_frames_frac 没有对应量；
              # 训练期的 obs 范围也没有落盘，无法事后重建参考上界。门禁 v1.2.1 会因缺该字段判
              # measurement_invalid —— 这是**口径缺口**（无归一化策略如何履行输入契约），已上报 B/D 裁定，
              # A 线不自行绕过（不删 ckpt 字段、不伪造 0.0）。
              'input_constraints': {
                  'normalization': 'none (raw 60-dim state obs; no VecNormalize at train time)',
                  'train_time_norm_absmax': None,
                  'note': ('unnormalized policy: 无「归一化输入越界」可测；训练期 obs 范围未落盘，'
                           '无法计算等效 |x| 上界。缺字段按 v1.2.1 判 INVALID，等待 B/D 裁定口径。'),
              },
              'episodes': n, 'seed0': args.seed0,
              'horizon': args.horizon, 'pinned_object_seed': PINNED_OBJECT_SEED,
              'residual_scale': args.residual_scale, 'residual_phases': phases,
              'success_raw': sum(r['success_raw'] for r in rows),
              'success_raw_rate': sum(r['success_raw'] for r in rows) / max(1, n),
              'grasp_verified_episodes': sum(r['grasp_verified'] for r in rows),
              'success_grasp_verified': sum(r['success_grasp_verified'] for r in rows),
              'success_grasp_verified_rate': sum(r['success_grasp_verified'] for r in rows) / max(1, n),
              'mean_max_rise': float(np.mean([r['max_rise'] for r in rows])),
              'mean_final_rise': float(np.mean([r['final_rise'] for r in rows])),
              'held_at_end_count': sum(r['held_at_end'] for r in rows),
              'success_rise': sum(r['max_rise'] >= 0.04 for r in rows),
              'terminal_kind_counts': {t: sum(1 for r in rows if r['terminal_kind'] == t)
                                       for t in sorted({r['terminal_kind'] for r in rows})},
              'gate_field_contract': 'final_rise/held_at_end/phase_at_end/rise_at_success/terminal_kind (v1.2.1)',
              'mean_residual_active_steps': float(np.mean([r['residual_active_steps'] for r in rows])), 'rows': rows}
    out = Path(args.out) if args.out else Path(args.ckpt).resolve().parent / 'audit_truth20.json'
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'rows'}, indent=2, ensure_ascii=False))
if __name__ == '__main__': main()
