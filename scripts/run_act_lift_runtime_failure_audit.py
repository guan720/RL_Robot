#!/usr/bin/env python3
"""learned ACT checkpoint 的真实 Lift runtime 事件级失败审计。

T17（B 交接单 §8 第 1 项）：`goal_id` / `epoch` 由 `make_goal_resolver` 统一给出并随 A↔B 换向一起进账本；
ckpt 无 `goal_vocab` 时退回任务名占位，`goal_source` 会明说这不是 goal 条件化（不伪造贯通证据）。
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np, torch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from harness.contracts import DecisionRequest, QueueState
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env, reset_contact, contact_object_geom
from harness.runtime_adapter import RuntimeAdapter
from scripts.probe_contact_ceiling import grasp_truth_fn
from scripts.train_act_lift import policy_from_checkpoint


def make_goal_resolver(vocab, plan, switch_every, task):
    """把「第 ci 个 chunk 用哪个 goal_id / 哪个 epoch」收敛成**一处**（B 交接单 §8 第 1 项）。

    改之前 `goal_id` 在 records / chunks 各写死一份 `'lift'`，`epoch` 在 DecisionRequest / records /
    chunks 各写死一份 `1`：三处字面量各改各的，就会让「换向」与「epoch」在账本里对不上，
    而黄金值 E6 要的正是这两条**独立**的拒绝理由（`harness/data_bridge.py:379` `deadline_miss`、
    `:388` `goal_epoch_incompatible`，另加 `:377` `goal_epoch_mismatch`）。

    返回 `(resolver, plan, goal_source)`；`resolver(ci) -> (goal_id, epoch)`。
    """
    from harness.queue_td_learner import LearnerRefused
    goal_conditioned = bool(vocab)
    if plan == "auto":
        plan = "alternate" if goal_conditioned else "fixed"
    if not goal_conditioned:
        if plan != "fixed":
            raise LearnerRefused(
                "ckpt 没有 goal_vocab（goal_dim=0，policy 是 goal-blind 的），却要求 --goal-plan=%s；"
                "那样账本会记方向性 goal_id 而 policy 根本不看 goal ⇒ 等于伪造 goal 贯通证据。"
                "要测换向，先用 `train_act_lift.py --goals default` 训一个带词表的 ckpt" % plan)
        # 任务名占位：**不是**方向标签。显式标注来源，免得 'lift' 被下游读成「已 goal 条件化」。
        return (lambda ci: (task, 1)), plan, "task_name_fallback(ckpt 无 goal_vocab ⇒ 非 goal 条件)"
    if plan == "fixed":
        return (lambda ci: (vocab[0], 1)), plan, "vocab[0] 固定（不换向）"
    if switch_every < 1:
        raise LearnerRefused("--switch-every 必须 >= 1；周期 0 会让每个 chunk 都换向，epoch 失去意义")
    def resolver(ci):
        switch = ci // switch_every
        return vocab[switch % len(vocab)], 1 + switch
    return resolver, plan, "每 %d 个 chunk 在词表内轮换，epoch 随换向 +1" % switch_every

def phase(raw,z0):
    z=float(raw['cube_pos'][2]); e=np.asarray(raw['robot0_eef_pos']); c=np.asarray(raw['cube_pos']); w=float(np.max(np.abs(raw['robot0_gripper_qpos'])))
    if z>z0+0.04: return 'hold'
    if w>0.012: return 'grasp'
    if abs(e[2]-c[2])<0.035: return 'descend'
    return 'approach'

def snap(obs): return np.asarray(obs,dtype=np.float32).reshape(-1).round(8).tolist()

def run_episode(env, model, mean, std, seed, horizon, K, goal_of, task='lift'):
    obs=reset_contact(env,seed); raw=env._env._get_observations(); z0=float(raw['cube_pos'][2]); truth=grasp_truth_fn(env,task)
    frame=0; raw_success=False; held=False; max_rise=0.; chunks=[]; records=[]; events=[]; actions=[]; norm_stats=[]; terminal=False
    while frame<horizon and not terminal:
        goal_id,epoch=goal_of(len(chunks))
        with torch.no_grad(): chunk=model(torch.tensor(((np.asarray(obs,dtype=np.float32)-mean)/std)[None]),goal=goal_id)[0].numpy()
        norm=(np.asarray(obs,dtype=np.float32)-mean)/std; norm_stats.append({'mean':float(norm.mean()),'max_abs':float(np.max(np.abs(norm))),'finite':bool(np.isfinite(norm).all())})
        n=min(K,horizon-frame); rid=f'{seed}:{len(chunks)}'; req=DecisionRequest(rid,epoch,goal_id,{'obs':snap(obs)},'learned_act','model_final.pt',frame,frame,frame+K); local=[]
        def driver(request,slot,action):
            nonlocal obs,raw,raw_success,held,max_rise,terminal
            obs,reward,term,trunc,info=env.step(np.asarray(action,dtype=np.float32)); raw=env._env._get_observations(); max_rise=max(max_rise,float(raw['cube_pos'][2])-z0); raw_success=raw_success or bool(info.get('success',False)); held=held or bool(truth()); terminal=bool(term or trunc)
            return {'activated':True,'observation':{'obs':snap(obs)},'reward':float(reward),'source':'robosuite','phase':phase(raw,z0),'grasp_verified':bool(held),'max_rise':max_rise,'failure_phase':'' if raw_success else phase(raw,z0)}
        rt=RuntimeAdapter(driver=driver,policy='learned_act',version='model_final.pt'); rt.start(req,QueueState())
        for j in range(n):
            action=np.asarray(chunk[j],dtype=np.float32); before=phase(raw,z0); result=rt.step(action); out=result['outcome']; local.append(action.copy()); actions.append(action.copy()); records.append({'frame':frame,'request_id':rid,'epoch':epoch,'goal_id':goal_id,'accepted':True,'committed':True,'activated':result['activated'],'partially_executed':result['partially_executed'],'terminal':False,'action':action.tolist(),'execution_mask':[1],'phase':before,'grasp_verified':out.grasp_verified,'max_rise':out.max_rise,'failure_phase':out.failure_phase,'td_eligible':True,'bc_eligible':True,'isolation_reasons':[]}); frame+=1
            if terminal: break
        rr=rt.finalize('environment_done' if terminal else 'slot_complete',observation={'obs':snap(obs)}); events.extend(rr.events)
        chunks.append({'request_id':rid,'epoch':epoch,'goal_id':goal_id,'start_frame':frame-len(local),'deadline':req.deadline,'accepted':True,'committed':True,'activated':True,'partially_executed':len(local)<K,'terminal':terminal,'execution_mask':[1]*len(local),'action_count':len(local),'td_eligible':rr.training_view.td_eligible,'bc_eligible':rr.training_view.bc_eligible,'isolation_reasons':list(rr.training_view.isolation_reasons),'terminal_kind':'environment_done' if terminal else 'slot_complete','actions':[a.tolist() for a in local]})
    failure='' if raw_success else (records[-1]['phase'] if records else 'unknown')
    if not raw_success:
        for r in records: r.update(td_eligible=False,bc_eligible=False,isolation_reasons=['policy_failure'])
        for c in chunks: c.update(td_eligible=False,bc_eligible=False,isolation_reasons=['policy_failure'])
    jumps=[float(np.linalg.norm(actions[i]-actions[i-1])) for i in range(1,len(actions)) if i%K==0]
    anomaly={'nonfinite_norm':sum(not n['finite'] for n in norm_stats),'max_abs_norm':max((n['max_abs'] for n in norm_stats),default=0.),'boundary_action_jump':{'count':len(jumps),'max_l2_jump':max(jumps) if jumps else 0.,'mean_l2_jump':float(np.mean(jumps)) if jumps else 0.},'action_out_of_bounds':sum(int(np.any(np.abs(a)>1.0001)) for a in actions)}
    return {'seed':seed,'raw_success':raw_success,'grasp_verified':held,'success_grasp_verified':bool(raw_success and held),'success_rise':bool(max_rise>=0.04),'max_rise':max_rise,'phase_trace':list(dict.fromkeys(r['phase'] for r in records)),'failure_phase':failure,'steps':frame,'chunks':chunks,'frame_records':records,'events':events,'normalization_audit':anomaly}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--ckpt',default='runs/infra/act_lift_k4_state_seed0/model_final.pt'); ap.add_argument('--episodes',type=int,default=20); ap.add_argument('--seed0',type=int,default=5000); ap.add_argument('--horizon',type=int,default=300); ap.add_argument('--chunk-length',type=int,default=4); ap.add_argument('--out',default='runs/infra/act_lift_runtime_failure_audit.json')
    # T17（B 交接单 §8 第 1 项）：goal_id 不再写死 'lift'。auto = ckpt 带 goal_vocab 就在词表内
    # 随 epoch 轮换 A↔B；ckpt 是 goal-blind 的就退回任务名占位，并在 goal_source 里明说「非 goal 条件」。
    ap.add_argument('--goal-plan',default='auto',choices=('auto','fixed','alternate')); ap.add_argument('--switch-every',type=int,default=8,help='alternate 下每多少个 chunk 换一次向（epoch 同步 +1）'); ap.add_argument('--task',default='lift'); a=ap.parse_args()
    ck=torch.load(a.ckpt,map_location='cpu'); assert int(ck['chunk_length'])==a.chunk_length; model=policy_from_checkpoint(ck,a.chunk_length); model.load_state_dict(ck['model']); model.eval(); mean=np.asarray(ck['obs_mean'],np.float32); std=np.asarray(ck['obs_std'],np.float32); env=make_contact_env(a.task,horizon=a.horizon,reward_shaping=True,obs_mode='state'); rows=[]
    vocab=tuple(ck.get('goal_vocab') or ()); goal_of,goal_plan,goal_source=make_goal_resolver(vocab,a.goal_plan,a.switch_every,a.task)
    try:
        for i in range(a.episodes): rows.append(run_episode(env,model,mean,std,a.seed0+i,a.horizon,a.chunk_length,goal_of,a.task))
        geom=contact_object_geom(env,a.task,PINNED_OBJECT_SEED)
    finally: env.close()
    out={'controller':'learned ACT runtime failure audit','ckpt':str(Path(a.ckpt).resolve()),'description':'真实 env.step 接入；不是 ACT-RL 训练结果','episodes':len(rows),'seed0':a.seed0,'horizon':a.horizon,'chunk_length':a.chunk_length,'pinned_object_seed':PINNED_OBJECT_SEED,'object_geom':geom,'success_raw':sum(r['raw_success'] for r in rows),'grasp_verified':sum(r['grasp_verified'] for r in rows),'success_grasp_verified':sum(r['success_grasp_verified'] for r in rows),'success_rise':sum(r['success_rise'] for r in rows),'mean_max_rise':float(np.mean([r['max_rise'] for r in rows])),'rows':rows}
    ledger={}
    for r in rows:
        for c in r['chunks']:
            e=ledger.setdefault((c['epoch'],c['goal_id']),{'chunks':0,'frames':0,'isolation_reasons':set()})
            e['chunks']+=1; e['frames']+=int(c['action_count']); e['isolation_reasons'].update(c['isolation_reasons'])
    out.update({'task':a.task,'goal_plan':goal_plan,'goal_source':goal_source,'goal_vocab':list(vocab),
                'switch_every':a.switch_every,'policy_goal_conditioned':bool(vocab),
                'goal_ledger':[{'epoch':k[0],'goal_id':k[1],'chunks':v['chunks'],'frames':v['frames'],
                                'isolation_reasons':sorted(v['isolation_reasons'])} for k,v in sorted(ledger.items())]})
    p=Path(a.out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x))+'\n'); print(json.dumps({k:v for k,v in out.items() if k not in ('rows','object_geom')},ensure_ascii=False,indent=2))
    # 环境溯源**旁挂**（D 附记 §9.1 末）。只在输出目录多写一个文件，**不动**上面那份 JSON 的 schema
    # ⇒ 0924 的 runs/infra/act_lift_runtime_failure_audit.json 若被重跑，逐字段仍可比。非致命。
    try:
        from scripts.a_env_provenance import write_sidecar
        write_sidecar(p.parent,'act_lift_runtime_failure_audit',str(p),
                      {'ckpt':str(Path(a.ckpt).resolve()),'goal_plan':goal_plan,'goal_source':goal_source,
                       'goal_vocab':list(vocab),'argv':sys.argv[1:]})
    except Exception as exc:
        print('[env_provenance][WARN] 旁挂件调用失败（不影响审计产物）：%r' % (exc,))
if __name__=='__main__': main()
