#!/usr/bin/env python3
"""Minimal state-based ACT imitation baseline for Lift."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import torch
from torch import nn
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env, reset_contact, contact_object_geom
from scripts.demo_scripted_lift_rs import LiftStateMachine

class ChunkPolicy(nn.Module):
    def __init__(self, obs_dim, chunk=4, *, goals=None):
        # T17（B→A 交接单 `docs/b_handoff_to_a_20260929.md` §8 第 2 项）：共享 πθ 要支持 A↔B 换向，
        # goal 必须进 policy 的**输入**。
        # **向后兼容是硬要求，不是风格偏好**：`ChunkPolicy(obs_dim, chunk)` 这两个位置参数被 7 个 B 线
        # 脚本（b_train_act_lift_fixed / b_eval_act_lift_v1 / b_probe_covariate_shift /
        # b_probe_eval_determinism …）与 A 自己的 eval_act_lift_truth / eval_act_replan_frequency /
        # audit_act_io_contract / run_act_lift_runtime_failure_audit 原样调用；既有 checkpoint 的
        # `net.0.weight` 形状是 (256, obs_dim)。所以 goal 相关参数一律**关键字、缺省关闭**：
        # `goals=None` 时 state_dict 的**键与形状与改动前逐字节相同**，旧 ckpt 仍能 strict=True 加载。
        # 开 goal 只改第一层 in_features，**不新增任何键**（键名不变 ⇒ 加载器不会静默漏掉一层）。
        super().__init__(); self.chunk=chunk; self.obs_dim=int(obs_dim)
        self.goals=_resolve_goal_vocab(goals); self.goal_dim=len(self.goals)
        self.net=nn.Sequential(nn.Linear(self.obs_dim+self.goal_dim,256),nn.ReLU(),nn.Linear(256,256),nn.ReLU(),nn.Linear(256,chunk*7),nn.Tanh())
    def goal_onehot(self, goal_id):
        """与 C 的 `harness/queue_td_learner.py::_goal_onehot` **同一套语义**：词表外拒绝、不静默映射。"""
        if goal_id is None:
            _refuse("goal 条件已开（词表 %d 项）但 forward 没给 goal_id；不给 goal 就等于把 goal 当常量偏置" % self.goal_dim)
        if goal_id not in self.goals:
            _refuse("goal_id=%r 不在词表 %r 里（不得静默当成某个已知 goal —— 对齐黄金值 E6 的拒绝语义）" % (goal_id, self.goals))
        vec=np.zeros(self.goal_dim,dtype=np.float32); vec[self.goals.index(goal_id)]=1.0
        return torch.from_numpy(vec)
    def forward(self,x,goal=None):
        if self.goal_dim:
            if isinstance(goal,(list,tuple)):
                # 逐样本 goal（BC 按 goal 分组训练时用）。长度必须与 batch 对齐：
                # 不齐还广播就等于把「按 goal 分组」静默退回单 goal，正是 B2–B6 那类
                # 「维度全对、只有 T17 能抓」的坏实现。
                if len(goal)!=x.shape[0]:
                    _refuse("逐样本 goal 给了 %d 个，batch 是 %d；长度不齐不得广播" % (len(goal),x.shape[0]))
                g=torch.stack([self.goal_onehot(one) for one in goal]).to(x.device)
            else:
                g=self.goal_onehot(goal).to(x.device).unsqueeze(0).expand(x.shape[0],-1)
            x=torch.cat([x,g],dim=-1)
        return self.net(x).view(-1,self.chunk,7)


# --- goal 词表：**读** learner 的缺省，不抄字面量（ADR-C-005 的同一条纪律）-----------------
# 抄一份字面量就会在缺省变更时对着一个**不存在的词表**绿着 —— 那是恒真断言的另一形态。
# 惰性 import：`goals=None`（缺省路径）时**完全不碰** harness.queue_td_learner，
# 免得把 learner 的依赖拖进 7 个只想要一个 MLP 的下游脚本。
def _resolve_goal_vocab(goals):
    if goals is None: return ()
    if isinstance(goals,str):
        if goals!="default": _refuse("goals=%r 不是合法写法；给 tuple/list，或给字符串 'default' 去读 learner 缺省" % goals)
        from harness.queue_td_learner import LearnerConfig
        return tuple(LearnerConfig.__dataclass_fields__["goals"].default)
    vocab=tuple(str(g) for g in goals)
    # 词表只有 1 项时 one-hot 恒为常量 [1.0]（= 给第一层加固定偏置），goal 对输出的影响恒为 0，
    # 而维度 / concat / forward 检查**全都会过** ⇒ 必须显式拒绝（同 C 的 `goal_dim < 2` 那一条）。
    if len(vocab)<2:
        _refuse("goals 词表只有 %d 项 %r ⇒ one-hot 退化成常量，goal 条件不可学；"
                "要么给完整双向词表，要么就别开 goal（goals=None）" % (len(vocab),vocab))
    if len(set(vocab))!=len(vocab): _refuse("goals 词表有重复项 %r" % (vocab,))
    return vocab


def _refuse(msg):
    """抛 C 已确立的 `LearnerRefused`，A 不另造第二种异常类型（跨线要能被同一个 except 抓住）。"""
    from harness.queue_td_learner import LearnerRefused
    raise LearnerRefused(msg)


def policy_from_checkpoint(ck, chunk=None):
    """按 checkpoint 里回显的词表重建 policy。

    为什么需要它：下游 8 个脚本都写 `ChunkPolicy(int(ck['obs_dim']), chunk)`。goal 条件的 ckpt
    被这样加载会在 `net.0.weight` 形状上**直接报错**（这是好事：不会静默丢掉 goal 条件），
    但报错信息看不出原因。A 自己的脚本一律走本函数；B 的脚本在真有 goal 条件 ckpt 之前不受影响。
    """
    vocab=tuple(ck.get("goal_vocab") or ())
    return ChunkPolicy(int(ck["obs_dim"]), int(chunk if chunk is not None else ck["chunk_length"]),
                       goals=(vocab if vocab else None))


# --- 真帧 teacher 的方向能力（环境事实，不是配置项）------------------------------------------
# `LiftStateMachine` 只会把 cube 从 A 抬向 B。词表的单一事实源仍是 `LearnerConfig.goals`
# （A 只读不抄，见 `_resolve_goal_vocab`）；这里只声明「teacher 覆盖词表里的哪一项」。
# 覆盖不到的方向**如实记 n_rows=0**，不伪造 0/0、也不拿 A→B 的帧冒充 B→A 的帧。
TEACHER_GOAL = "lift_A_to_B"


def parse_goals_arg(raw):
    """`--goals` 的三种写法：不给（关闭 goal 条件）/ `default`（读 learner 缺省）/ 逗号分隔词表。"""
    if raw is None: return None
    raw=str(raw).strip()
    if raw=="": return None
    if raw=="default": return "default"
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def collect_by_goal(env,vocab,seeds,horizon,chunk,history=1):
    """按 goal 分组采集真帧 BC 数据（B 交接单 §8 第 2 项：采集时就要分组，事后加 goal 输入没有可学差异）。

    返回 `{goal_id: {"rows": [(state, action_chunk), ...], "n_rows": int, "teacher_available": bool, ...}}`。
    只有 teacher 能做的方向真有 rows；其余方向 `n_rows=0` 且 `teacher_available=False`。
    """
    if TEACHER_GOAL not in vocab:
        _refuse("真帧 teacher 只做 %r，但它不在词表 %r 里 ⇒ 一帧真数据都采不到；"
                "词表的单一事实源是 LearnerConfig.goals，不要在这里另造一套" % (TEACHER_GOAL, tuple(vocab)))
    groups={}
    for goal_id in vocab:
        if goal_id==TEACHER_GOAL:
            rows=collect(env,seeds,horizon,chunk,history)
            groups[goal_id]={"rows":rows,"n_rows":len(rows),"teacher_available":True,"seeds":list(seeds),
                             "note":"真帧 teacher（LiftStateMachine）A→B 抬起"}
        else:
            groups[goal_id]={"rows":[],"n_rows":0,"teacher_available":False,"seeds":[],
                             "note":"teacher 无此方向的演示 ⇒ 0 行（如实记录，不以 A→B 的帧冒充）"}
    return groups

def collect(env,seeds,horizon,chunk,history=1):
    rows=[]
    for seed in seeds:
        obs=reset_contact(env,seed); raw=env._env._get_observations(); ctrl=LiftStateMachine(float(raw['cube_pos'][2])); states=[]; actions=[]
        hist=[]
        for _ in range(horizon):
            cur=np.asarray(obs,dtype=np.float32).copy(); hist.append(cur); hist=hist[-history:]
            while len(hist)<history: hist.insert(0,hist[0].copy())
            states.append(np.concatenate(hist)); actions.append(np.asarray(ctrl(raw),dtype=np.float32).copy()); obs,_,term,trunc,_=env.step(actions[-1]); raw=env._env._get_observations()
            if term or trunc: break
        states=np.asarray(states); actions=np.asarray(actions); n=len(actions)
        for t in range(0,n-chunk+1): rows.append((states[t],actions[t:t+chunk]))
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',default='runs/infra/act_lift_k4_state_seed0'); ap.add_argument('--chunk-length',type=int,default=4); ap.add_argument('--history',type=int,default=1); ap.add_argument('--train-episodes',type=int,default=24); ap.add_argument('--val-episodes',type=int,default=8); ap.add_argument('--epochs',type=int,default=40); ap.add_argument('--seed',type=int,default=0); ap.add_argument('--horizon',type=int,default=300)
    # 缺省**关闭** goal 条件：不加这个参数时，state_dict 的键/形状、ckpt 的键集、config.json 与
    # train_result.json 的内容都与改动前逐项相同 ⇒ 0924 的 48 臂基线产物仍可原样复算。
    ap.add_argument('--goals',default=None,help="不给=关闭 goal 条件（缺省）；'default'=读 LearnerConfig.goals；或逗号分隔词表")
    args=ap.parse_args(); np.random.seed(args.seed); torch.manual_seed(args.seed)
    vocab=_resolve_goal_vocab(parse_goals_arg(args.goals))
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True); env=make_contact_env('lift',horizon=args.horizon,reward_shaping=True,obs_mode='state')
    train_seeds=list(range(1000,1000+args.train_episodes)); val_seeds=list(range(2000,2000+args.val_episodes))
    if vocab:
        tr_groups=collect_by_goal(env,vocab,train_seeds,args.horizon,args.chunk_length,args.history)
        va_groups=collect_by_goal(env,vocab,val_seeds,args.horizon,args.chunk_length,args.history)
        tr=[row for g in vocab for row in tr_groups[g]['rows']]; tr_goals=[g for g in vocab for _ in tr_groups[g]['rows']]
        va=[row for g in vocab for row in va_groups[g]['rows']]; va_goals=[g for g in vocab for _ in va_groups[g]['rows']]
    else:
        tr_groups=va_groups=None; tr_goals=va_goals=None
        tr=collect(env,train_seeds,args.horizon,args.chunk_length,args.history); va=collect(env,val_seeds,args.horizon,args.chunk_length,args.history)
    geom=contact_object_geom(env,'lift',PINNED_OBJECT_SEED); env.close()
    x=np.stack([a for a,_ in tr]); y=np.stack([b for _,b in tr]); xv=np.stack([a for a,_ in va]); yv=np.stack([b for _,b in va]); mean=x.mean(0); std=x.std(0)+1e-6
    model=ChunkPolicy(x.shape[1],args.chunk_length,goals=(vocab or None)); opt=torch.optim.Adam(model.parameters(),lr=3e-4); tx=torch.tensor((x-mean)/std); ty=torch.tensor(y); vx=torch.tensor((xv-mean)/std); vy=torch.tensor(yv); best=1e9
    def ck_payload():
        d={'model':model.state_dict(),'obs_dim':x.shape[1],'history':args.history,'chunk_length':args.chunk_length,'obs_mean':mean.tolist(),'obs_std':std.tolist(),'action_dim':7,'object_geom':geom,'pinned_object_seed':PINNED_OBJECT_SEED}
        if vocab: d['goal_vocab']=list(vocab); d['goal_dim']=len(vocab)
        return d
    for epoch in range(args.epochs):
        model.train(); pred=model(tx,goal=tr_goals); loss=((pred-ty)**2).mean(); opt.zero_grad(); loss.backward(); opt.step(); model.eval();
        with torch.no_grad(): vl=((model(vx,goal=va_goals)-vy)**2).mean().item()
        if vl<best: best=vl; torch.save(ck_payload(),out/'model_best.pt')
    torch.save(ck_payload(),out/'model_final.pt')
    cfg={'task':'lift','obs':'state','history':args.history,'chunk_length':args.chunk_length,'action_dim':7,'train_seeds':train_seeds,'val_seeds':val_seeds,'horizon':args.horizon,'epochs':args.epochs,'seed':args.seed,'pinned_object_seed':PINNED_OBJECT_SEED,'object_geom':geom,'train_samples':len(tr),'val_samples':len(va),'best_val_mse':best}
    result={'best_val_mse':best,'train_samples':len(tr),'val_samples':len(va)}
    if vocab:
        n_dir=sum(1 for g in vocab if tr_groups[g]['n_rows']>0)
        cfg['goal_vocab']=list(vocab); cfg['goal_dim']=len(vocab); cfg['teacher_goal']=TEACHER_GOAL
        cfg['goal_coverage']={g:{'train_rows':tr_groups[g]['n_rows'],'val_rows':va_groups[g]['n_rows'],
                                 'teacher_available':tr_groups[g]['teacher_available'],'note':tr_groups[g]['note']} for g in vocab}
        # 「计算图已 goal 条件化」与「真帧能学出方向差异」是两件事，必须分开说：
        # 只覆盖 1 个方向时 one-hot 在**数据**上是常量，训练学不到任何方向差异（T17 只验计算图）。
        cfg['goal_conditioning_status']={'wired':True,'directions_total':len(vocab),'directions_with_real_frames':n_dir,
            'learnable_from_real_frames':bool(n_dir>=2),
            'note':("真帧覆盖全部 %d 个方向" % len(vocab)) if n_dir>=2 else
                    ("计算图已 goal 条件化，但真帧 teacher 只覆盖 %d/%d 个方向 ⇒ 单靠真帧 BC **学不出**方向差异；"
                     "要声称 goal-conditioned 已学成，必须先有 %s 的演示源"
                     % (n_dir,len(vocab),[g for g in vocab if tr_groups[g]['n_rows']==0]))}
        result['goal_coverage']={g:tr_groups[g]['n_rows'] for g in vocab}; result['goal_vocab']=list(vocab)
    (out/'config.json').write_text(json.dumps(cfg,indent=2)); (out/'train_result.json').write_text(json.dumps(result,indent=2)); print(json.dumps(cfg,indent=2));
    # 环境溯源**旁挂**（D 附记 §9.1 末：新训练产物必须回显新 lock 的 sha256）。
    # 只多写一个 env_provenance.json，**不给 config.json / ckpt 加任何键** ⇒ 缺省路径的产物 schema 与改动前逐项相同
    # （兼容性由 a_selfcheck_goal_conditioning_t17.py 的 G5/G6 对着 git HEAD 证）。非致命：写不出也不让训练失败。
    try:
        from scripts.a_env_provenance import write_sidecar
        write_sidecar(out,'train_act_lift',str(out/'model_final.pt'),
                      {'goal_vocab':list(vocab) if vocab else None,'argv':sys.argv[1:],
                       'train_samples':len(tr),'val_samples':len(va),'best_val_mse':best})
    except Exception as exc:
        print('[env_provenance][WARN] 旁挂件调用失败（不影响训练产物）：%r' % (exc,))
if __name__=='__main__': main()
