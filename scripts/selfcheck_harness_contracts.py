#!/usr/bin/env python3
"""阶段 3 Harness P0 契约回放自检：六个确定性异步例子。"""
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.contracts import DecisionRequest, QueueState, ReplayDriver, TrainingView

def req(i="r1", epoch=1, goal="g1", deadline=10):
    return DecisionRequest(i, epoch, goal, {"x": [1, 2, 3]}, "mock", "v1", 0, 0, deadline)

def case_queue_immutable():
    d=ReplayDriver(); d.request(req()); d.commit("r1", ("a", "b"), 2)
    try: d.commit("r1", ("new",), 3); return False, "proposal overwrote committed queue"
    except ValueError: return d.committed[1] == ("a", "b"), ""

def case_uncommitted_no_td():
    d=ReplayDriver(); d.request(req()); v=d.finish("r1", 10, "deadline_miss", "never committed")
    return (not v.td_eligible and not v.bc_eligible and "deadline_miss" in v.isolation_reasons), ""

def case_early_termination():
    d=ReplayDriver(); d.request(req()); d.commit("r1", ("a",), 1); v=d.finish("r1", 2, "cancel", "early termination")
    return ("r1" in d.requests and v.terminal_kind == "cancel" and not v.td_eligible), ""

def case_takeover_cancel_deadline():
    good=True
    for kind in ("takeover", "cancel", "deadline_miss"):
        d=ReplayDriver(); d.request(req("r1")); d.commit("r1", ("a",), 1); v=d.finish("r1", 3, kind)
        good &= (not v.td_eligible and kind in v.isolation_reasons)
    return good, ""

def case_gamma_once():
    d=ReplayDriver(); d.request(req()); d.commit("r1", ("a",), 1); v=d.finish("r1", 2, "success")
    # A slot transition carries one discount; replay must not compound it.
    return v.gamma_slot == 0.99, f"gamma={v.gamma_slot}"

def case_lifecycle_by_id():
    d=ReplayDriver(); d.request(req()); d.commit("r1", ("a",), 1); d.activate("r1", 1); d.finish("r1", 2, "success")
    kinds=[e.kind for e in d.events if getattr(e, "request_id", None)=="r1" and hasattr(e, "kind")]
    return kinds == ["requested", "committed", "activated", "activated"], str(kinds)

def main():
    cases=[("旧 committed queue 不被新 proposal 覆盖",case_queue_immutable),
           ("未提交建议不能生成 TD",case_uncommitted_no_td),
           ("early termination 保留原 request",case_early_termination),
           ("takeover/cancel/deadline miss 隔离普通 TD",case_takeover_cancel_deadline),
           ("gamma_slot 只折扣一次",case_gamma_once),
           ("按 request_id 重建完整生命周期",case_lifecycle_by_id)]
    rows=[]; bad=[]
    for name,fn in cases:
        ok,detail=fn(); rows.append({"case":name,"ok":ok,"detail":detail}); print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok: bad.append(name)
    out=Path("runs/infra/harness_contract_replay.json"); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({"cases":rows,"pass":not bad},ensure_ascii=False,indent=2)+"\n")
    print(f"结果: {len(cases)-len(bad)}/{len(cases)} PASS -> {out}")
    raise SystemExit(1 if bad else 0)
if __name__ == "__main__": main()
