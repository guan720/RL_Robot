#!/usr/bin/env python3
"""真实 Lift tick + RuntimeAdapter 字段传递自检。"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.contracts import DecisionRequest, QueueState
from harness.env_factory import make_contact_env, reset_contact
from harness.runtime_adapter import RuntimeAdapter
from scripts.probe_contact_ceiling import grasp_truth_fn

def request(i): return DecisionRequest(i,1,'lift',{'cube_pos':[0,0,0]},'teacher','v1',0,0,4)

def main():
    checks=[]
    # Real environment callback: reward/observation/verifier fields originate at env.step.
    env=make_contact_env('lift',horizon=4,reward_shaping=True,obs_mode='state'); reset_contact(env,5000); truth=grasp_truth_fn(env,'lift')
    def real_driver(req,slot,action):
        obs,reward,term,trunc,info=env.step(np.asarray(action,dtype=np.float32))
        raw=env._env._get_observations()
        return {'activated':True,'observation':{'cube_pos':np.asarray(raw['cube_pos']).tolist()},'reward':float(reward),'source':'robosuite','phase':'approach','grasp_verified':bool(truth()),'max_rise':0.0,'failure_phase':''}
    rt=RuntimeAdapter(driver=real_driver); rt.start(request('real')); got=rt.step(np.zeros(7,dtype=np.float32)); rr=rt.finalize('success'); env.close()
    checks.append(('真实 env.step 回执',got['outcome'].source=='robosuite' and got['outcome'].grasp_verified is not None and got['outcome'].observation.get('cube_pos') is not None))
    # Terminal/isolation matrix uses deterministic adapter callbacks.
    for kind in ('early_termination','cancel','deadline_miss'):
        x=RuntimeAdapter(driver=lambda r,s,a:{'activated':True}); x.start(request(kind)); x.step('a'); z=x.finalize(kind)
        checks.append((f'{kind} 隔离',not z.training_view.td_eligible and not z.training_view.bc_eligible and kind in z.training_view.isolation_reasons))
    x=RuntimeAdapter(driver=lambda r,s,a:{'activated':True,'partially_executed':True,'reason':'device_ack'}); x.start(request('partial')); z=x.step('a'); checks.append(('partial execution 传递',z['partially_executed'] and any(getattr(e,'kind','')=='partially_executed' for e in x.events)))
    bad=[n for n,o in checks if not o]
    for n,o in checks: print(f"[{'PASS' if o else 'FAIL'}] {n}")
    print(f'结果: {len(checks)-len(bad)}/{len(checks)} PASS')
    raise SystemExit(1 if bad else 0)
if __name__=='__main__': main()
