#!/usr/bin/env python3
"""Truth audit for a trained ACT imitation chunk policy.

门禁字段（2026-09-28 追加，交付 B 的 `docs/b_handoff_to_a_20260928.md` 交接单 2）：每局额外输出
`final_rise / held_at_end / phase_at_end / rise_at_success / terminal_kind`，语义与
`scripts/eval_lerobot_act_runtime.py:330-380`（B 认可的参考实现）一致；`grasp_verified` 仍是
held_ever，两者不得互相覆盖。只追加、不改任何既有键与算法，因此与 09-24 留档产物可直接对比。
注意：本评测器**尚未**记录 `norm_input_blown_frames_frac`，按门禁 v1.2.1 §2.6 其产物会被判
`measurement_invalid`（输入契约未验证）——要出可引用的率数字，需按 B 的
`scripts/b_eval_act_lift_v1.py:203-206` 同口径补记录后重跑。
"""
from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path
import numpy as np, torch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env, reset_contact, contact_object_geom
from scripts.probe_contact_ceiling import grasp_truth_fn
from scripts.train_act_lift import ChunkPolicy

def phase(raw,z0,step):
    z=float(raw['cube_pos'][2]); e=np.asarray(raw['robot0_eef_pos']); c=np.asarray(raw['cube_pos']); w=float(np.max(np.abs(raw['robot0_gripper_qpos'])))
    if z>z0+0.04: return 'hold'
    if w>0.012: return 'grasp'
    if abs(e[2]-c[2])<0.035: return 'descend'
    return 'approach'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--ckpt',required=True); ap.add_argument('--episodes',type=int,default=20); ap.add_argument('--seed0',type=int,default=5000); ap.add_argument('--horizon',type=int,default=300); ap.add_argument('--chunk-length',type=int,default=4); ap.add_argument('--history',type=int,default=None); ap.add_argument('--out',required=True); args=ap.parse_args(); ck=torch.load(args.ckpt,map_location='cpu'); assert int(ck['chunk_length'])==args.chunk_length
    history=int(args.history or ck.get('history',1))
    model=ChunkPolicy(int(ck['obs_dim']),args.chunk_length); model.load_state_dict(ck['model']); model.eval(); mean=np.asarray(ck['obs_mean'],np.float32); std=np.asarray(ck['obs_std'],np.float32); env=make_contact_env('lift',horizon=args.horizon,reward_shaping=True,obs_mode='state'); rows=[]
    try:
      for i in range(args.episodes):
        seed=args.seed0+i; obs=reset_contact(env,seed); raw=env._env._get_observations(); z0=float(raw['cube_pos'][2]); truth=grasp_truth_fn(env,'lift'); raw_s=held=False; max_rise=0.; frames=0; requests=0; chunks=[]; phases=[]; started=time.perf_counter(); events={'partial':0,'cancel':0,'deadline':0}; hist=[]
        final_rise=0.; held_at_end=False; rise_at_success=None; terminal_kind='horizon_exhausted'; env_done=False
        while frames<args.horizon:
          cur=np.asarray(obs,dtype=np.float32); hist.append(cur); hist=hist[-history:]
          while len(hist)<history: hist.insert(0,hist[0].copy())
          model_obs=np.concatenate(hist)
          with torch.no_grad(): chunk=model(torch.tensor(((model_obs-mean)/std)[None]))[0].numpy()
          n=min(args.chunk_length,args.horizon-frames); mask=[]; rid=requests
          for j in range(n):
            obs,_,term,trunc,info=env.step(chunk[j]); raw=env._env._get_observations(); frames+=1; mask.append(True)
            rise=float(raw['cube_pos'][2])-z0; max_rise=max(max_rise,rise); final_rise=rise
            succ_now=bool(info.get('success',False))
            if succ_now and rise_at_success is None: rise_at_success=rise
            held_now=bool(truth()); held_at_end=held_now
            raw_s=raw_s or succ_now; held=held or held_now; phases.append(phase(raw,z0,frames))
            if term or trunc: events['cancel']+=1; env_done=bool(term); break
          if n<args.chunk_length: events['partial']+=1
          chunks.append({'request_id':rid,'chunk_length':n,'actual_activation_mask':mask,'start_step':frames-len(mask),'phase':phases[-len(mask)] if mask else ''}); requests+=1
          if term or trunc:
            terminal_kind='environment_done' if env_done else 'horizon_exhausted'; break
        rows.append({'seed':seed,'success_raw':raw_s,'grasp_verified':held,'success_grasp_verified':bool(raw_s and held),'success_rise':bool(max_rise>=0.04),'max_rise':round(max_rise,6),'final_rise':round(final_rise,6),'held_at_end':held_at_end,'phase_at_end':(phases[-1] if phases else ''),'rise_at_success':(round(rise_at_success,6) if rise_at_success is not None else None),'terminal_kind':terminal_kind,'guard_interventions':0,'recovery_events':0,'failure_phase':'' if raw_s else (phases[-1] if phases else 'unknown'),'steps':frames,'chunk_count':requests,'actual_activation_frames':sum(len(c['actual_activation_mask']) for c in chunks),'partial_events':events['partial'],'cancel_events':events['cancel'],'deadline_events':events['deadline'],'elapsed_sec':time.perf_counter()-started,'phase_trace':phases,'chunks':chunks})
      geom=contact_object_geom(env,'lift',PINNED_OBJECT_SEED)
    finally: env.close()
    n=len(rows); result={'controller':'ACT imitation','task':'lift','history':history,'ckpt':str(Path(args.ckpt).resolve()),'episodes':n,'seed0':args.seed0,'horizon':args.horizon,'chunk_length':args.chunk_length,'pinned_object_seed':PINNED_OBJECT_SEED,'object_geom':geom,'success_raw':sum(r['success_raw'] for r in rows),'grasp_verified':sum(r['grasp_verified'] for r in rows),'success_grasp_verified':sum(r['success_grasp_verified'] for r in rows),'success_rise':sum(r['success_rise'] for r in rows),'mean_max_rise':float(np.mean([r['max_rise'] for r in rows])),'mean_final_rise':float(np.mean([r['final_rise'] for r in rows])),'held_at_end_count':sum(r['held_at_end'] for r in rows),'terminal_kind_counts':{t:sum(1 for r in rows if r['terminal_kind']==t) for t in sorted({r['terminal_kind'] for r in rows})},'gate_field_contract':'final_rise/held_at_end/phase_at_end/rise_at_success/terminal_kind (v1.2.1)','failure_phase_counts':{p:sum(r['failure_phase']==p for r in rows) for p in sorted({r['failure_phase'] for r in rows if r['failure_phase']})},'rows':rows}; p=Path(args.out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(result,indent=2)); print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
if __name__=='__main__': main()
