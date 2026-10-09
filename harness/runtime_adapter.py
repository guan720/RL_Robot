"""阶段 3 P1：固定 slot 的增量 Runtime adapter。

这是 legacy ``run_episode`` 之外的独立路径。它只负责契约事件和 mock/Lift
式逐 slot 推进，不改变现有 Harness 默认行为，也不连接真机。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .contracts import (ActionEvent, DecisionRequest, OutcomeEvent, QueueState,
                        TrainingView)

@dataclass
class RuntimeResult:
    request_id: str
    training_view: TrainingView
    events: list[Any]

class RuntimeAdapter:
    """单 request、单 slot 增量执行器；driver 通过 ``execute`` 提供 mock 回执。"""
    def __init__(self, driver=None, *, policy="mock", version="v1"):
        self.driver = driver or (lambda request, slot: {"activated": True, "reward": 0.0})
        self.policy, self.version = policy, version
        self.request: DecisionRequest | None = None
        self.queue = QueueState()
        self.events: list[Any] = []
        self.frame = 0
        self.done = False
        self.result: RuntimeResult | None = None

    def start(self, request: DecisionRequest, queue: QueueState | None = None) -> DecisionRequest:
        if self.request is not None and not self.done:
            raise RuntimeError("runtime already active")
        self.request, self.queue, self.events, self.frame, self.done = request, queue or QueueState(), [], request.frame, False
        self.events.append(ActionEvent(request.request_id, "requested", request.epoch, request.goal_id,
                                       request.frame, self.queue, requested=True))
        self.events.append(ActionEvent(request.request_id, "accepted", request.epoch, request.goal_id,
                                       request.frame, self.queue, accepted=True))
        return request

    def step(self, action: Any = None) -> dict[str, Any]:
        if self.request is None or self.done: raise RuntimeError("runtime is not active")
        r = self.request
        slot = self.frame
        if not self.queue.c:
            self.queue = QueueState(c=(str(action),) if action is not None else ("noop",), c_frame=slot)
            self.events.append(ActionEvent(r.request_id, "committed", r.epoch, r.goal_id, slot, self.queue, committed=action))
        try:
            ack = dict(self.driver(r, slot, action) or {})
        except TypeError:
            ack = dict(self.driver(r, slot) or {})
        activated = bool(ack.get("activated", False)); partial = bool(ack.get("partially_executed", False))
        kind = "partially_executed" if partial else "activated"
        self.events.append(ActionEvent(r.request_id, kind, r.epoch, r.goal_id, slot, self.queue,
                                       activated=action if activated else None, partially_executed=partial,
                                       reason=str(ack.get("reason", ""))))
        out = OutcomeEvent(r.request_id, r.epoch, r.goal_id, slot,
                           dict(ack.get("observation", r.observation)), float(ack.get("reward", 0.0)),
                           False, "none", str(ack.get("source", "mock")), r.policy, r.version,
                           str(ack.get("phase", "")), ack.get("grasp_verified"), ack.get("max_rise"),
                           str(ack.get("failure_phase", "")))
        self.events.append(out); self.frame += 1
        return {"activated": activated, "partially_executed": partial, "frame": slot, "outcome": out}

    def finalize(self, terminal_kind="success", *, reason="", observation=None, reward=0.0) -> RuntimeResult:
        if self.request is None or self.done: raise RuntimeError("runtime is not active")
        r=self.request; isolated = terminal_kind in ("cancel", "takeover", "deadline_miss", "early_termination", "policy_failure")
        kind = "expired" if terminal_kind == "deadline_miss" else "cancelled" if isolated else "activated"
        self.events.append(ActionEvent(r.request_id, kind, r.epoch, r.goal_id, self.frame, self.queue,
                                       cancelled=kind == "cancelled", expired=kind == "expired", reason=reason))
        self.events.append(OutcomeEvent(r.request_id, r.epoch, r.goal_id, self.frame,
                                        dict(observation or r.observation), float(reward), True, terminal_kind,
                                        "mock", r.policy, r.version))
        reasons=(terminal_kind,) if isolated else ()
        view=TrainingView(r.request_id, r.epoch, r.goal_id, not isolated, not isolated,
                          (1,) if not isolated else (), (1,) if not isolated else (), terminal_kind,
                          reasons, 0.99)
        self.done=True; self.result=RuntimeResult(r.request_id, view, list(self.events)); return self.result
