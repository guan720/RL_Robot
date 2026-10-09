#!/usr/bin/env python3
"""真实 Lift 环境接入 P1 RuntimeAdapter（scripted teacher，非 ACT 学习）。"""
from __future__ import annotations
import argparse, json, sys
from dataclasses import asdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from harness.contracts import DecisionRequest, QueueState  # noqa: E402
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env, reset_contact, contact_object_geom  # noqa: E402
from harness.runtime_adapter import RuntimeAdapter  # noqa: E402
from scripts.demo_scripted_lift_rs import LiftStateMachine, _cube_pos  # noqa: E402
from scripts.probe_contact_ceiling import grasp_truth_fn  # noqa: E402

def snapshot(raw):
    return {k: np.asarray(raw[k], dtype=float).reshape(-1).round(8).tolist()
            for k in ('cube_pos','robot0_eef_pos') if k in raw}

def episode(env, seed, horizon, chunk_length):
    reset_contact(env, seed); raw=env._env._get_observations(); z0=float(_cube_pos(raw)[2])
    teacher=LiftStateMachine(cube_z0=z0); truth=grasp_truth_fn(env,'lift')
    rows=[]; chunks=[]; events=[]; max_rise=0.; held=False; raw_success=False; frame=0; terminal=False
    while frame < horizon and not terminal:
        selected=[]; request_id=f'{seed}:{len(chunks)}'; req=DecisionRequest(request_id,1,'lift',snapshot(raw),'scripted_teacher','v1',frame,frame,frame+chunk_length)
        def driver(request, slot, action):
            nonlocal raw, max_rise, held, raw_success, terminal
            raw2,reward,term,trunc,info=env.step(np.asarray(action,dtype=np.float32)); raw=env._env._get_observations()
            rise=float(_cube_pos(raw)[2])-z0; max_rise=max(max_rise,rise)
            raw_success=raw_success or bool(info.get('success',False)); held=held or bool(truth())
            terminal=bool(term or trunc)
            return {'activated':True,'partially_executed':False,'observation':snapshot(raw),'reward':float(reward),'source':'robosuite','phase':str(teacher.phase),'grasp_verified':bool(held),'max_rise':max_rise,'failure_phase':'' if raw_success else str(teacher.phase)}
        rt=RuntimeAdapter(driver=driver,policy='scripted_teacher',version='v1'); rt.start(req,QueueState())
        for _ in range(min(chunk_length,horizon-frame)):
            phase=str(teacher.phase); action=np.asarray(teacher(raw),dtype=np.float32).copy(); selected.append(action.tolist())
            result=rt.step(action); out=result['outcome']; rows.append({'frame':frame,'request_id':request_id,'epoch':1,'goal_id':'lift','action':action.tolist(),'execution_mask':[1],'accepted':True,'committed':True,'activated':result['activated'],'partially_executed':result['partially_executed'],'terminal':False,'phase':phase,'grasp_verified':out.grasp_verified,'max_rise':out.max_rise,'failure_phase':out.failure_phase,'td_eligible':True,'bc_eligible':True,'isolation_reasons':[]})
            frame += 1
            if terminal: break
        final_kind='success' if raw_success and terminal else ('environment_done' if terminal else 'slot_complete')
        rr=rt.finalize(final_kind,observation=snapshot(raw),reward=0.0)
        events.extend(rr.events); chunks.append({'request_id':request_id,'epoch':1,'goal_id':'lift','start_frame':frame-len(selected),'deadline':req.deadline,'accepted':True,'committed':True,'activated':True,'partially_executed':False,'terminal':final_kind!='slot_complete','actual_action_count':len(selected),'execution_mask':[1]*len(selected),'td_eligible':rr.training_view.td_eligible,'bc_eligible':rr.training_view.bc_eligible,'isolation_reasons':list(rr.training_view.isolation_reasons),'terminal_kind':final_kind})
    phases=[]
    for r in rows:
        if not phases or phases[-1]!=r['phase']: phases.append(r['phase'])
    return {'seed':seed,'raw_success':raw_success,'grasp_verified':held,'success_grasp_verified':bool(raw_success and held),'success_rise':bool(max_rise>=0.04),'max_rise':max_rise,'phase_trace':phases,'failure_phase':'' if raw_success else (phases[-1] if phases else 'unknown'),'steps':frame,'chunks':chunks,'frame_records':rows,'events':[asdict(e) for e in events]}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--episodes',type=int,default=20); ap.add_argument('--seed0',type=int,default=5000); ap.add_argument('--horizon',type=int,default=300); ap.add_argument('--chunk-length',type=int,default=4); ap.add_argument('--out',required=True); a=ap.parse_args()
    env=make_contact_env('lift',horizon=a.horizon,reward_shaping=True,obs_mode='state'); rows=[]
    try:
        for i in range(a.episodes): rows.append(episode(env,a.seed0+i,a.horizon,a.chunk_length))
        geom=contact_object_geom(env,'lift',PINNED_OBJECT_SEED)
    finally: env.close()
    out={'controller':'scripted_teacher_runtime_adapter','description':'真实 Lift tick；不是 ACT 学习结果','task':'lift','episodes':len(rows),'seed0':a.seed0,'horizon':a.horizon,'chunk_length':a.chunk_length,'pinned_object_seed':PINNED_OBJECT_SEED,'object_geom':geom,'success_raw':sum(r['raw_success'] for r in rows),'grasp_verified_episodes':sum(r['grasp_verified'] for r in rows),'success_grasp_verified':sum(r['success_grasp_verified'] for r in rows),'success_rise':sum(r['success_rise'] for r in rows),'mean_max_rise':float(np.mean([r['max_rise'] for r in rows])),'rows':rows}
    def _json_default(x):
        return x.tolist() if hasattr(x, 'tolist') else str(x)
    p=Path(a.out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=_json_default)+'\n'); print(json.dumps({k:v for k,v in out.items() if k not in ('rows','object_geom')},ensure_ascii=False,indent=2,default=_json_default))
if __name__=='__main__': main()
