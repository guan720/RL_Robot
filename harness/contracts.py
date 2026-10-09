"""阶段 3 Harness P0：可回放的异步决策与训练视图契约。

本模块只描述事件和确定性回放，不改变旧 Harness 的同步执行路径。
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any
import json

EVENT_KINDS = ("requested", "accepted", "committed", "activated",
               "partially_executed", "cancelled", "expired")

@dataclass(frozen=True)
class DecisionRequest:
    request_id: str; epoch: int; goal_id: str; observation: dict[str, Any]
    policy: str; version: str; slot: int; frame: int; deadline: int

@dataclass(frozen=True)
class QueueState:
    c: tuple[str, ...] = (); e: tuple[str, ...] = (); d: tuple[str, ...] = ()
    c_frame: int | None = None; e_frame: int | None = None; d_frame: int | None = None

@dataclass(frozen=True)
class ActionEvent:
    request_id: str; kind: str; epoch: int; goal_id: str; frame: int
    queue: QueueState; requested: Any = None; accepted: Any = None
    committed: Any = None; activated: Any = None; partially_executed: Any = None
    cancelled: bool = False; expired: bool = False; reason: str = ""
    def __post_init__(self):
        if self.kind not in EVENT_KINDS: raise ValueError(f"unknown event kind: {self.kind}")

@dataclass(frozen=True)
class OutcomeEvent:
    request_id: str; epoch: int; goal_id: str; frame: int; observation: dict[str, Any]
    reward: float; terminal: bool; terminal_kind: str = "none"; source: str = "env"
    policy: str = ""; version: str = ""; phase: str = ""; grasp_verified: bool | None = None
    max_rise: float | None = None; failure_phase: str = ""

@dataclass(frozen=True)
class TrainingView:
    request_id: str; epoch: int; goal_id: str; td_eligible: bool; bc_eligible: bool
    execution_mask: tuple[int, ...] = (); bc_mask: tuple[int, ...] = ()
    terminal_kind: str = "none"; isolation_reasons: tuple[str, ...] = ()
    gamma_slot: float = 1.0

def to_dict(obj: Any) -> dict[str, Any]:
    d = asdict(obj)
    return d

def dumps(obj: Any) -> str:
    return json.dumps(to_dict(obj), ensure_ascii=False, sort_keys=True)

class ReplayDriver:
    """确定性事件驱动器：只允许 committed 队列进入 activated/TD。"""
    def __init__(self):
        self.events: list[ActionEvent | OutcomeEvent] = []
        self.committed: dict[int, tuple[str, ...]] = {}
        self.requests: dict[str, DecisionRequest] = {}
        self.terminal: set[str] = set()

    def request(self, r: DecisionRequest) -> None:
        self.requests[r.request_id] = r
        self.events.append(ActionEvent(r.request_id, "requested", r.epoch, r.goal_id, r.frame, QueueState(), requested=True))

    def commit(self, request_id: str, actions: tuple[str, ...], frame: int) -> None:
        r = self.requests[request_id]
        # New proposals never mutate an already committed epoch/frame.
        key = r.epoch
        if key in self.committed: raise ValueError("committed queue is immutable")
        self.committed[key] = tuple(actions)
        q = QueueState(c=tuple(actions), c_frame=frame)
        self.events.append(ActionEvent(request_id, "committed", r.epoch, r.goal_id, frame, q, committed=actions))

    def activate(self, request_id: str, frame: int, partial: bool = False) -> None:
        r = self.requests[request_id]
        q = QueueState(c=self.committed.get(r.epoch, ()), c_frame=frame)
        if not q.c: raise ValueError("uncommitted action cannot activate")
        kind = "partially_executed" if partial else "activated"
        self.events.append(ActionEvent(request_id, kind, r.epoch, r.goal_id, frame, q, activated=True, partially_executed=partial))

    def finish(self, request_id: str, frame: int, terminal_kind: str, reason: str = "") -> TrainingView:
        r = self.requests[request_id]; self.terminal.add(request_id)
        q = QueueState(c=self.committed.get(r.epoch, ()), c_frame=frame)
        kind = "expired" if terminal_kind == "deadline_miss" else "cancelled" if terminal_kind in ("cancel", "takeover") else "activated"
        self.events.append(ActionEvent(request_id, kind, r.epoch, r.goal_id, frame, q, cancelled=kind == "cancelled", expired=kind == "expired", reason=reason))
        self.events.append(OutcomeEvent(request_id, r.epoch, r.goal_id, frame, r.observation,
                                        0.0, True, terminal_kind, "mock", r.policy, r.version))
        isolated = [] if kind == "activated" else [terminal_kind]
        return TrainingView(request_id, r.epoch, r.goal_id, kind == "activated", kind == "activated", (1,), (1,), terminal_kind, tuple(isolated), 0.99)

    def replay(self) -> list[TrainingView]:
        return [self.finish(rid, self.requests[rid].frame, "success") for rid in self.requests if rid not in self.terminal]
