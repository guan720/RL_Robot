#!/usr/bin/env python3
"""Export scripted Lift trajectories to a LeRobot-compatible interchange dataset."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from harness.env_factory import PINNED_OBJECT_SEED,make_contact_env,reset_contact,contact_object_geom
from scripts.demo_scripted_lift_rs import LiftStateMachine

def episode(env,seed,horizon,k):
 obs=reset_contact(env,seed); raw=env._env._get_observations(); ctrl=LiftStateMachine(float(raw['cube_pos'][2])); states=[]; acts=[]; phases=[]; t=[]
 for i in range(horizon):
  states.append(np.asarray(obs,np.float32)); phases.append(str(ctrl.phase)); a=np.asarray(ctrl(raw),np.float32); acts.append(a); t.append(i/20.0); obs,_,term,trunc,_=env.step(a); raw=env._env._get_observations()
  if term or trunc: break
 states=np.asarray(states); acts=np.asarray(acts); chunks=np.stack([acts[i:i+k] for i in range(0,len(acts)-k+1)],axis=0)
 return states,acts,chunks,phases,np.asarray(t,np.float32)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',default='runs/infra/lerobot_act_lift_state_overfit');ap.add_argument('--horizon',type=int,default=300);ap.add_argument('--chunk-length',type=int,default=4);ap.add_argument('--train-seeds',default='1000-1023');ap.add_argument('--val-seeds',default='2000-2007');ap.add_argument('--test-seeds',default='5000-5019');a=ap.parse_args();out=Path(a.out);(out/'data').mkdir(parents=True,exist_ok=True);env=make_contact_env('lift',horizon=a.horizon,reward_shaping=True,obs_mode='state'); geom=contact_object_geom(env,'lift',PINNED_OBJECT_SEED)
 def parse(s):
  x=s.split('-');return range(int(x[0]),int(x[-1])+1)
 episodes=[]; frame=0
 try:
  for split,spec in [('train',a.train_seeds),('validation',a.val_seeds),('test',a.test_seeds)]:
   for seed in parse(spec):
    st,ac,ch,ph,ts=episode(env,seed,a.horizon,a.chunk_length); eid=len(episodes); np.savez_compressed(out/'data'/f'episode_{eid:04d}.npz',observation_state=st,action=ac,action_chunk=ch,timestamp=ts,phase=np.asarray(ph,dtype='U16'),episode_index=eid,seed=seed,split=split); episodes.append({'episode_index':eid,'seed':seed,'split':split,'frames':len(ac),'frame_start':frame,'frame_end':frame+len(ac),'chunk_length':a.chunk_length});frame+=len(ac)
 finally: env.close()
 info={'codebase_version':'RL_Robot local export','robot_type':'robosuite_panda_lift','fps':20,'features':{'observation.state':{'dtype':'float32','shape':[int(np.load(out/'data/episode_0000.npz')['observation_state'].shape[1])]},'action':{'dtype':'float32','shape':[7]}},'action_semantics':'OSC_POSE: xyz/rpy delta + gripper; +1 close, -1 open','chunk_length':a.chunk_length,'receding_horizon_steps':a.chunk_length,'temporal_aggregation':None,'normalization':{'observation':'per-dimension train mean/std stored in normalization.npz','action':'teacher action already clipped to [-1,1]'},'pinned_object_seed':PINNED_OBJECT_SEED,'object_geometry':geom,'splits':{'train':a.train_seeds,'validation':a.val_seeds,'test':a.test_seeds}}
 arr=np.concatenate([np.load(out/'data'/f"episode_{i:04d}.npz")['observation_state'] for i in range(len(episodes)) if episodes[i]['split']=='train']);np.savez(out/'normalization.npz',observation_mean=arr.mean(0),observation_std=arr.std(0)+1e-6)
 (out/'meta').mkdir(exist_ok=True);(out/'meta/info.json').write_text(json.dumps(info,indent=2));(out/'meta/episodes.jsonl').write_text('\n'.join(json.dumps(e) for e in episodes)+'\n');print(json.dumps({'episodes':len(episodes),'frames':frame,'out':str(out),'object_geometry':geom},indent=2))
if __name__=='__main__':main()
