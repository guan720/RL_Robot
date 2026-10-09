#!/usr/bin/env python3
"""只读审计 ACT 训练、评测和 runtime 的 I/O contract。"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np, torch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env, reset_contact
from scripts.demo_scripted_lift_rs import LiftStateMachine
from scripts.probe_contact_ceiling import grasp_truth_fn
from scripts.train_act_lift import ChunkPolicy

def phase(raw,z0):
    z=float(raw['cube_pos'][2]); e=np.asarray(raw['robot0_eef_pos']); c=np.asarray(raw['cube_pos']); w=float(np.max(np.abs(raw['robot0_gripper_qpos'])))
    if z>z0+.04:return 'hold'
    if w>.012:return 'grasp'
    if abs(e[2]-c[2])<.035:return 'descend'
    return 'approach'

def infer(env,model,mean,std,mode,seed,horizon,K,first=False):
    obs=reset_contact(env,seed); raw=env._env._get_observations(); z0=float(raw['cube_pos'][2]); truth=grasp_truth_fn(env,'lift'); frames=0; raw_s=held=False; rise=0.; phases=[]; actions=[]; chunks=[]; norm_max=0.; first_sample=None
    while frames<horizon:
        flat=np.asarray(obs,dtype=np.float32); inp=(flat-mean)/std if mode=='current' else (flat-mean)/std if mode=='floor' else flat; norm_max=max(norm_max,float(np.max(np.abs(inp))))
        with torch.no_grad(): pred=model(torch.tensor(inp[None],dtype=torch.float32))[0].numpy()
        if first and first_sample is None:
            teacher=LiftStateMachine(cube_z0=z0); first_sample={'raw_obs':flat.tolist(),'raw_obs_dtype':str(flat.dtype),'normalized_obs':inp.tolist(),'predicted_action':pred[0].tolist(),'teacher_action':np.asarray(teacher(raw),dtype=np.float32).tolist()}
        n=min(K,horizon-frames); mask=[]
        for j in range(n):
            obs,_,term,trunc,info=env.step(pred[j]); raw=env._env._get_observations(); frames+=1; mask.append(True); actions.append(np.asarray(pred[j],dtype=np.float32)); raw_s=raw_s or bool(info.get('success',False)); held=held or bool(truth()); rise=max(rise,float(raw['cube_pos'][2])-z0); phases.append(phase(raw,z0))
            if term or trunc: break
        chunks.append({'request_id':f'{seed}:{len(chunks)}','execution_mask':mask,'action_count':len(mask),'start_frame':frames-len(mask)}); 
        if term or trunc: break
    jumps=[float(np.linalg.norm(actions[i]-actions[i-1])) for i in range(1,len(actions)) if i%K==0]
    return {'seed':seed,'raw_success':raw_s,'grasp_verified':held,'success_grasp_verified':bool(raw_s and held),'success_rise':rise>=.04,'max_rise':rise,'failure_phase':'' if raw_s else (phases[-1] if phases else 'unknown'),'phase_trace':list(dict.fromkeys(phases)),'steps':frames,'chunk_count':len(chunks),'event_count':frames+len(chunks)*4,'activation_frames':sum(len(c['execution_mask']) for c in chunks),'max_abs_norm':norm_max,'boundary_action_jump_max':max(jumps) if jumps else 0.,'boundary_action_jump_mean':float(np.mean(jumps)) if jumps else 0.,'chunks':chunks,'first_sample':first_sample}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--ckpt',default='runs/infra/act_lift_k4_state_seed0/model_final.pt'); ap.add_argument('--episodes',type=int,default=20); ap.add_argument('--seed0',type=int,default=5000); ap.add_argument('--horizon',type=int,default=300); ap.add_argument('--chunk-length',type=int,default=4); ap.add_argument('--out',default='runs/infra/act_io_contract_audit.json'); a=ap.parse_args()
    ck=torch.load(a.ckpt,map_location='cpu'); model=ChunkPolicy(int(ck['obs_dim']),a.chunk_length); model.load_state_dict(ck['model']); model.eval(); mean=np.asarray(ck['obs_mean'],np.float32); std=np.asarray(ck['obs_std'],np.float32); floor=np.maximum(std,1e-3); env=make_contact_env('lift',horizon=a.horizon,reward_shaping=True,obs_mode='state'); modes={}
    try:
        for mode,s in [('current',std),('floor',floor),('raw',std)]:
            rows=[infer(env,model,mean,s,mode,a.seed0+i,a.horizon,a.chunk_length,first=i==0) for i in range(a.episodes)]; modes[mode]={'rows':rows,'success_grasp_verified':sum(r['success_grasp_verified'] for r in rows),'max_abs_norm':max(r['max_abs_norm'] for r in rows),'mean_boundary_jump':float(np.mean([r['boundary_action_jump_mean'] for r in rows])),'failure_phases':{p:sum(r['failure_phase']==p for r in rows) for p in sorted({r['failure_phase'] for r in rows})},'event_counts':sorted({r['event_count'] for r in rows}),'activation_frames':sorted({r['activation_frames'] for r in rows})}
    finally: env.close()
    out={'checkpoint':str(Path(a.ckpt).resolve()),'read_only':True,'pinned_object_seed':PINNED_OBJECT_SEED,'seed_range':[a.seed0,a.seed0+a.episodes-1],'obs_dim':int(ck['obs_dim']),'action_dim':int(ck['action_dim']),'chunk_length':a.chunk_length,'dtype_contract':{'train_obs':'float32','eval_obs':'float32','runtime_obs':'float32'},'field_order':'robosuite state vector passed unchanged; no field reorder','train_stats_source':'train_act_lift.py collect train seeds 1000..1023: x.mean/x.std + 1e-6','validation_stats_source':'training mean/std reused; validation does not recompute statistics','test_stats_source':'checkpoint obs_mean/obs_std reused by eval/runtime','std_min':float(std.min()),'near_zero_std_indices':np.where(std<1e-4)[0].tolist(),'safe_std_floor':1e-3,'action_contract':'ChunkPolicy tanh output, 7 dims, direct [-1,1], no inverse scaling','teacher_alignment':'state t predicts chunk t:t+K; one env step per chunk frame','modes':modes}
    p=Path(a.out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n'); print(json.dumps({k:out[k] for k in ('obs_dim','action_dim','std_min','near_zero_std_indices','modes')},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
