#!/usr/bin/env python3
"""只读 ACT chunk 重规划频率诊断；不训练、不修改 checkpoint。"""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import numpy as np, torch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env, reset_contact
from scripts.probe_contact_ceiling import grasp_truth_fn
from scripts.train_act_lift import ChunkPolicy

def phase(raw,z0):
 z=float(raw['cube_pos'][2]); e=np.asarray(raw['robot0_eef_pos']); c=np.asarray(raw['cube_pos']); w=float(np.max(np.abs(raw['robot0_gripper_qpos'])))
 if z>z0+.04:return 'hold'
 if w>.012:return 'grasp'
 if abs(e[2]-c[2])<.035:return 'descend'
 return 'approach'

def run(env,model,mean,std,seed,horizon,K,replan):
 obs=reset_contact(env,seed); raw=env._env._get_observations(); z0=float(raw['cube_pos'][2]); truth=grasp_truth_fn(env,'lift'); frame=0; raw_s=held=False; rise=0.; phases=[]; chunks=[]; actions=[]; terminal=False
 while frame<horizon and not terminal:
  with torch.no_grad(): chunk=model(torch.tensor(((np.asarray(obs,dtype=np.float32)-mean)/std)[None]))[0].numpy()
  n=min(replan,horizon-frame); rid=f'{seed}:{len(chunks)}'; mask=[]; local=[]
  for j in range(n):
   action=np.asarray(chunk[j],dtype=np.float32); obs,_,term,trunc,info=env.step(action); raw=env._env._get_observations(); frame+=1; mask.append(True); local.append(action.tolist()); actions.append(action); rise=max(rise,float(raw['cube_pos'][2])-z0); raw_s=raw_s or bool(info.get('success',False)); held=held or bool(truth()); phases.append(phase(raw,z0)); terminal=bool(term or trunc)
   if terminal: break
  chunks.append({'request_id':rid,'start_frame':frame-len(mask),'chunk_length':K,'actual_activation_mask':mask,'executed_frames':len(mask),'replan_every':replan,'terminal':terminal})
 jumps=[float(np.linalg.norm(actions[i]-actions[i-1])) for i in range(1,len(actions)) if i%replan==0]
 return {'seed':seed,'raw_success':raw_s,'grasp_verified':held,'success_grasp_verified':bool(raw_s and held),'success_rise':rise>=.04,'max_rise':rise,'failure_phase':'' if raw_s else (phases[-1] if phases else 'unknown'),'phase_trace':list(dict.fromkeys(phases)),'steps':frame,'chunks':chunks,'event_count':frame+len(chunks)*4,'activation_frames':sum(len(c['actual_activation_mask']) for c in chunks),'boundary_action_jump_max':max(jumps) if jumps else 0.,'boundary_action_jump_mean':float(np.mean(jumps)) if jumps else 0.}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--ckpt',required=True); ap.add_argument('--episodes',type=int,default=20); ap.add_argument('--seed0',type=int,default=5000); ap.add_argument('--horizon',type=int,default=300); ap.add_argument('--chunk-length',type=int,default=4); ap.add_argument('--replan-every',default='1,2,4'); ap.add_argument('--out',required=True); a=ap.parse_args()
 ck=torch.load(a.ckpt,map_location='cpu'); assert int(ck['chunk_length'])==a.chunk_length; model=ChunkPolicy(int(ck['obs_dim']),a.chunk_length); model.load_state_dict(ck['model']); model.eval(); mean=np.asarray(ck['obs_mean'],np.float32); std=np.asarray(ck['obs_std'],np.float32); env=make_contact_env('lift',horizon=a.horizon,reward_shaping=True,obs_mode='state'); conditions={}
 try:
  for every in [int(x) for x in a.replan_every.split(',')]:
   rows=[run(env,model,mean,std,a.seed0+i,a.horizon,a.chunk_length,every) for i in range(a.episodes)]
   conditions[str(every)]={'rows':rows,'raw_success':sum(r['raw_success'] for r in rows),'grasp_verified':sum(r['grasp_verified'] for r in rows),'success_grasp_verified':sum(r['success_grasp_verified'] for r in rows),'success_rise':sum(r['success_rise'] for r in rows),'mean_max_rise':float(np.mean([r['max_rise'] for r in rows])),'mean_boundary_jump':float(np.mean([r['boundary_action_jump_mean'] for r in rows])),'event_counts':sorted({r['event_count'] for r in rows}),'activation_frames':sorted({r['activation_frames'] for r in rows}),'failure_phases':{p:sum(r['failure_phase']==p for r in rows) for p in sorted({r['failure_phase'] for r in rows})}}
 finally: env.close()
 out={'checkpoint':str(Path(a.ckpt).resolve()),'controller':'learned ACT replan frequency diagnostic','read_only':True,'pinned_object_seed':PINNED_OBJECT_SEED,'episodes':a.episodes,'seed0':a.seed0,'horizon':a.horizon,'chunk_length':a.chunk_length,'conditions':conditions}; p=Path(a.out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n'); print(json.dumps({k:{x:y for x,y in v.items() if x!='rows'} for k,v in conditions.items()},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
