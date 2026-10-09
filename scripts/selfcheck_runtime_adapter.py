#!/usr/bin/env python3
"""P1 Runtime adapter 自检：固定 slot、事件隔离和终局路径。"""
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.contracts import DecisionRequest, QueueState
from harness.runtime_adapter import RuntimeAdapter

def req(i, deadline=10):
    return DecisionRequest(i, 1, 'lift', {'cube_pos':[0,0,0]}, 'mock', 'v1', 0, 0, deadline)

def run(name, terminal='success', ack=None, n=1):
    rt=RuntimeAdapter(driver=(lambda r,s: ack or {'activated':True,'reward':1.0}))
    rt.start(req(name), QueueState())
    for _ in range(n): rt.step('a')
    return rt.finalize(terminal, reason=terminal)

def main():
    checks=[]
    normal=run('normal', n=2); checks.append(('正常激活', normal.training_view.td_eligible and normal.training_view.bc_eligible))
    partial=run('partial', ack={'activated':True,'partially_executed':True}, n=1); checks.append(('部分执行有事件', any(getattr(e,'kind','')=='partially_executed' for e in partial.events)))
    for kind in ('cancel','deadline_miss','takeover'):
        x=run(kind, terminal=kind); checks.append((f'{kind} 隔离 TD/BC', not x.training_view.td_eligible and not x.training_view.bc_eligible and kind in x.training_view.isolation_reasons))
    early=run('early', terminal='early_termination', n=1); checks.append(('early termination 保留 request', early.request_id=='early' and not early.training_view.td_eligible))
    bad=[name for name,ok in checks if not ok]
    for name,ok in checks: print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    out=Path('runs/infra/runtime_adapter_selfcheck.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({'checks':[{'name':n,'ok':o} for n,o in checks],'pass':not bad},ensure_ascii=False,indent=2)+'\n')
    print(f'结果: {len(checks)-len(bad)}/{len(checks)} PASS -> {out}')
    raise SystemExit(1 if bad else 0)
if __name__=='__main__': main()
