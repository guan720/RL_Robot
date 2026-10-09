#!/usr/bin/env python3
"""只读审计 LeRobot-style ACT Lift 导出数据集。"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--dataset',required=True); ap.add_argument('--out',default='runs/infra/lerobot_act_dataset_audit.json'); a=ap.parse_args(); root=Path(a.dataset); info=json.loads((root/'meta/info.json').read_text()); eps=[json.loads(x) for x in (root/'meta/episodes.jsonl').read_text().splitlines() if x.strip()]; files=sorted((root/'data').glob('episode_*.npz')); rows=[]; errors=[]
 seeds={}; train_seeds=set(); val_seeds=set(); test_seeds=set()
 for e in eps:
  seeds.setdefault(e['split'],set()).add(e['seed'])
  {'train':train_seeds,'validation':val_seeds,'test':test_seeds}.get(e['split'],set()).add(e['seed'])
 for p in files:
  z=np.load(p,allow_pickle=False); idx=int(z['episode_index']); split=str(z['split']); seed=int(z['seed']); obs=z['observation_state']; act=z['action']; chunks=z['action_chunk']; ts=z['timestamp']; n=len(obs); local=[]
  if obs.dtype!=np.float32 or obs.ndim!=2 or obs.shape[1]!=60: local.append('observation shape/dtype')
  if act.dtype!=np.float32 or act.shape!=(n,7): local.append('action shape/dtype')
  if chunks.shape!=(max(0,n-3),4,7): local.append('chunk shape')
  if len(ts)!=n or n>1 and not np.allclose(np.diff(ts),.05,atol=2e-5): local.append('timestamp dt')
  if len(chunks) and not np.array_equal(chunks[:,0,:],act[:len(chunks)]): local.append('action_chunk first mismatch')
  if len(chunks) and not np.array_equal(chunks[-1],act[-4:]): local.append('chunk tail alignment')
  if np.any(act[:,-1] < -1-1e-6) or np.any(act[:,-1] > 1+1e-6): local.append('gripper range')
  rows.append({'episode_index':idx,'seed':seed,'split':split,'frames':n,'obs_dim':int(obs.shape[1]),'action_dim':int(act.shape[1]),'chunk_count':len(chunks),'timestamp_dt_mean':float(np.mean(np.diff(ts))) if n>1 else None,'timestamp_dt_max_error':float(np.max(np.abs(np.diff(ts)-.05))) if n>1 else 0.,'action_chunk_first_exact':not any(x=='action_chunk first mismatch' for x in local),'chunk_tail_within_episode':not any(x=='chunk tail alignment' for x in local),'gripper_min':float(act[:,-1].min()),'gripper_max':float(act[:,-1].max()),'errors':local})
  if local: errors.append({'episode':idx,'errors':local})
 norm=np.load(root/'normalization.npz'); mean=norm['observation_mean']; std=norm['observation_std']; overlaps={'train_validation':sorted(train_seeds&val_seeds),'train_test':sorted(train_seeds&test_seeds),'validation_test':sorted(val_seeds&test_seeds)}
 checks={'episode_split_disjoint':not any(overlaps.values()),'test_seeds_exact_5000_5019':test_seeds==set(range(5000,5020)),'obs_60_float32':all(r['obs_dim']==60 for r in rows),'action_7_float32':all(r['action_dim']==7 for r in rows),'timestamp_20hz':not any('timestamp dt' in e for e in errors),'action_chunk_first_exact':not any('action_chunk first mismatch' in x for e in errors for x in e['errors']),'chunk_tails_in_episode':not any('chunk tail alignment' in x for e in errors for x in e['errors']),'normalization_shape':mean.shape==(60,) and std.shape==(60,),'metadata_temporal_config':info.get('chunk_length')==4 and info.get('receding_horizon_steps')==4 and 'temporal_aggregation' in info,'action_semantics_recorded':'+1 close' in info.get('action_semantics','') and '-1 open' in info.get('action_semantics','')}
 out={'dataset':str(root.resolve()),'read_only':True,'metadata':info,'episode_count':len(rows),'split_seed_counts':{k:len(v) for k,v in [('train',train_seeds),('validation',val_seeds),('test',test_seeds)]},'split_overlaps':overlaps,'normalization':{'mean_shape':list(mean.shape),'std_shape':list(std.shape),'std_min':float(std.min()),'source_declared':'train split'},'checks':checks,'errors':errors,'episodes':rows}
 p=Path(a.out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n'); print(json.dumps({'checks':checks,'errors':len(errors)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
