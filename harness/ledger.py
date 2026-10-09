"""C 线：append-only 事实账本（只存物理事实，不含任何训练语义）。

对应 v4 附录 01 §5.1 的五类长期保存对象中的前四类：真实执行日志（`frame_fact`）、
真实调度事件（`schedule_event`）、纠正标签池（`proposal_label`）、标签账本
（`label_record`）；第五类训练视图 manifest 由 `harness/data_bridge.py` 写入本库。

三条硬约束（依据 `RL_Harness_v4_20260924/materials/06_.../appendices/01_接口契约与开发验收.md`）：

1. **迟到标签不改写物理事实**：奖励/评分/撤销一律 `append_label` 追加新行，
   账本层面用 SQLite BEFORE UPDATE/DELETE 触发器把改写变成硬错误。
2. **四种动作量分开存**：`proposed_action` / `a_rl` / `driver_command` / `measured_state`
   各占一列，实测位移不得倒填成动作标签（§2.1）。
3. **不用 executed_length**：逐帧保存 `chunk_id`（来源 request）+ `chunk_index`
   （原 chunk 内的绝对索引），块级只保留 `executed_indices` 区间（§2.2）。

本模块不做资格判定：TD/BC/候选/隔离四种视图在 `data_bridge.py` 里派生。
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

CONTRACT_VERSION = "v4-appendix01"

# 调度事件：request_admitted / result_committed / physical_activated 是三个独立事件，
# 不能事后按成功或失败补记（附录 01 §5.3）。
EVENT_KINDS = (
    "request_received", "request_admitted", "result_committed", "physical_activated",
    "partially_executed", "cancelled", "expired", "takeover", "hold_start", "hold_end",
    "goal_switch", "version_switch", "prime", "recovery", "episode_end",
    # P1-5（增补五 §9-C③ / 裁定 29.1）：裁定身份的准入结果也是**账本事件**，
    # 于是「拒收」本身可留档可查，而不是只留一个异常栈。
    "verdict_admitted", "verdict_refused", "verdict_identity_absent",
)
FRAME_SOURCES = ("policy", "harness", "teleop", "hold", "recovery", "script", "mock")
EXECUTION_STATUS = ("activated", "partially_executed", "not_activated", "unknown")
LABEL_KINDS = ("reward", "progress", "success", "quality", "unknown", "revoke")
REWARD_STATES = ("pending", "final", "unknown")
PROPOSAL_SOURCES = ("harness_shadow", "harness_committed", "policy_shadow", "teleop")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS frame_fact(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, inserted_ns INTEGER NOT NULL,
  episode_id TEXT NOT NULL, abs_frame INTEGER NOT NULL, abs_time_ns INTEGER,
  request_id TEXT, chunk_id TEXT, chunk_index INTEGER,
  goal_id TEXT NOT NULL, epoch INTEGER NOT NULL, lease_generation INTEGER NOT NULL,
  source TEXT NOT NULL, execution_status TEXT NOT NULL,
  proposed_action TEXT, a_rl TEXT, driver_command TEXT, measured_state TEXT,
  contract_version TEXT NOT NULL, policy_version TEXT, obs_ref TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS schedule_event(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, inserted_ns INTEGER NOT NULL,
  episode_id TEXT NOT NULL, request_id TEXT, kind TEXT NOT NULL,
  abs_frame INTEGER, epoch INTEGER, goal_id TEXT, deadline INTEGER,
  lease_generation INTEGER, contract_version TEXT NOT NULL, payload TEXT);
CREATE TABLE IF NOT EXISTS label_record(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, inserted_ns INTEGER NOT NULL,
  episode_id TEXT NOT NULL, target_kind TEXT NOT NULL, target_seq INTEGER,
  target_request_id TEXT, label_kind TEXT NOT NULL, value REAL, value_json TEXT,
  reward_state TEXT, rubric_version TEXT, source TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS proposal_label(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, inserted_ns INTEGER NOT NULL,
  episode_id TEXT NOT NULL, request_id TEXT, abs_frame INTEGER,
  goal_id TEXT NOT NULL, epoch INTEGER, source TEXT NOT NULL, admitted INTEGER NOT NULL,
  action TEXT, valid_indices TEXT, quality REAL, observation_ref TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS view_manifest(
  manifest_id TEXT PRIMARY KEY, created_ns INTEGER NOT NULL, view_name TEXT NOT NULL,
  contract_version TEXT NOT NULL, label_version TEXT, gamma REAL, n INTEGER,
  sample_count INTEGER, filter_rules TEXT, normalization_ref TEXT,
  source_seqs TEXT, affected_requests TEXT, notes TEXT);
CREATE INDEX IF NOT EXISTS ix_frame_episode ON frame_fact(episode_id, abs_frame);
CREATE INDEX IF NOT EXISTS ix_frame_chunk ON frame_fact(chunk_id, chunk_index);
CREATE INDEX IF NOT EXISTS ix_event_request ON schedule_event(request_id, kind);
CREATE INDEX IF NOT EXISTS ix_label_target ON label_record(target_kind, target_seq);
"""

# append-only：任何 UPDATE/DELETE 都直接失败，而不是静默改写历史。
for _tbl in ("frame_fact", "schedule_event", "label_record", "proposal_label"):
    for _op in ("UPDATE", "DELETE"):
        _SCHEMA += (f"CREATE TRIGGER IF NOT EXISTS no_{_op.lower()}_{_tbl} "
                    f"BEFORE {_op} ON {_tbl} BEGIN "
                    f"SELECT RAISE(FAIL, '{_tbl} is append-only'); END;\n")


def _dumps(obj: Any) -> str | None:
    """把 numpy 数组/嵌套结构统一成 JSON 文本；None 保持 None（未知不填 0）。"""
    if obj is None:
        return None
    if hasattr(obj, "tolist"):
        obj = obj.tolist()
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=_default)


def _default(obj: Any) -> Any:
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if hasattr(obj, "item"):
        return obj.item()
    raise TypeError(f"not serializable: {type(obj)}")


def _loads(text: str | None) -> Any:
    return None if text is None else json.loads(text)


@dataclass(frozen=True)
class Row:
    """只读行视图；`data` 里的 JSON 列已反序列化。"""
    table: str
    seq: str | int
    fields: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.fields[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.fields.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {"table": self.table, "seq": self.seq, **self.fields}


_JSON_COLUMNS = {
    "frame_fact": ("proposed_action", "a_rl", "driver_command", "measured_state", "payload"),
    "schedule_event": ("payload",),
    "label_record": ("value_json",),
    "proposal_label": ("action", "valid_indices", "payload"),
    "view_manifest": ("filter_rules", "source_seqs", "affected_requests"),
}


class FactLedger:
    """SQLite 事实账本。写入只追加；读取返回 `Row`。"""

    def __init__(self, path: str | Path, *, contract_version: str = CONTRACT_VERSION):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.contract_version = contract_version
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # ---------- writers ----------
    def _now_ns(self) -> int:
        return time.time_ns()

    def append_frame(self, *, episode_id: str, abs_frame: int, goal_id: str, epoch: int,
                     lease_generation: int, source: str, execution_status: str = "activated",
                     abs_time_ns: int | None = None, request_id: str | None = None,
                     chunk_id: str | None = None, chunk_index: int | None = None,
                     proposed_action: Any = None, a_rl: Any = None,
                     driver_command: Any = None, measured_state: Any = None,
                     policy_version: str | None = None, obs_ref: str | None = None,
                     payload: Any = None) -> int:
        if source not in FRAME_SOURCES:
            raise ValueError(f"unknown frame source: {source}")
        if execution_status not in EXECUTION_STATUS:
            raise ValueError(f"unknown execution status: {execution_status}")
        cur = self.conn.execute(
            "INSERT INTO frame_fact(inserted_ns,episode_id,abs_frame,abs_time_ns,request_id,"
            "chunk_id,chunk_index,goal_id,epoch,lease_generation,source,execution_status,"
            "proposed_action,a_rl,driver_command,measured_state,contract_version,policy_version,"
            "obs_ref,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self._now_ns(), episode_id, abs_frame, abs_time_ns, request_id, chunk_id, chunk_index,
             goal_id, epoch, lease_generation, source, execution_status, _dumps(proposed_action),
             _dumps(a_rl), _dumps(driver_command), _dumps(measured_state),
             self.contract_version, policy_version, obs_ref, _dumps(payload)))
        self.conn.commit()
        return int(cur.lastrowid)

    def append_event(self, *, episode_id: str, kind: str, request_id: str | None = None,
                     abs_frame: int | None = None, epoch: int | None = None,
                     goal_id: str | None = None, deadline: int | None = None,
                     lease_generation: int | None = None, payload: Any = None) -> int:
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind: {kind}")
        cur = self.conn.execute(
            "INSERT INTO schedule_event(inserted_ns,episode_id,request_id,kind,abs_frame,epoch,"
            "goal_id,deadline,lease_generation,contract_version,payload)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (self._now_ns(), episode_id, request_id, kind, abs_frame, epoch, goal_id, deadline,
             lease_generation, self.contract_version, _dumps(payload)))
        self.conn.commit()
        return int(cur.lastrowid)

    def append_label(self, *, episode_id: str, label_kind: str, target_kind: str = "frame",
                     target_seq: int | None = None, target_request_id: str | None = None,
                     value: float | None = None, value_json: Any = None,
                     reward_state: str | None = None, rubric_version: str | None = None,
                     source: str = "env", reason: str = "") -> int:
        if label_kind not in LABEL_KINDS:
            raise ValueError(f"unknown label kind: {label_kind}")
        if reward_state is not None and reward_state not in REWARD_STATES:
            raise ValueError(f"unknown reward state: {reward_state}")
        if target_seq is None and target_request_id is None:
            raise ValueError("label needs target_seq or target_request_id")
        cur = self.conn.execute(
            "INSERT INTO label_record(inserted_ns,episode_id,target_kind,target_seq,"
            "target_request_id,label_kind,value,value_json,reward_state,rubric_version,source,reason)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (self._now_ns(), episode_id, target_kind, target_seq, target_request_id, label_kind,
             None if value is None else float(value), _dumps(value_json), reward_state,
             rubric_version, source, reason))
        self.conn.commit()
        return int(cur.lastrowid)

    def revoke_label(self, target_seq: int, *, reason: str, rubric_version: str | None = None,
                     source: str = "auditor") -> int:
        """撤销一条既有标签：追加 `revoke` 行，绝不删原行。"""
        row = self.conn.execute("SELECT episode_id,label_kind FROM label_record WHERE seq=?",
                                (target_seq,)).fetchone()
        if row is None:
            raise KeyError(f"label seq not found: {target_seq}")
        return self.append_label(episode_id=row["episode_id"], label_kind="revoke",
                                 target_kind="label", target_seq=target_seq,
                                 rubric_version=rubric_version, source=source, reason=reason)

    def append_proposal(self, *, episode_id: str, goal_id: str, source: str, admitted: bool,
                        action: Any = None, abs_frame: int | None = None,
                        request_id: str | None = None, epoch: int | None = None,
                        valid_indices: Sequence[int] | None = None, quality: float | None = None,
                        observation_ref: str | None = None, payload: Any = None) -> int:
        """纠正标签池：影子查询（admitted=False）与真实接纳（True）分开放，不混。"""
        if source not in PROPOSAL_SOURCES:
            raise ValueError(f"unknown proposal source: {source}")
        cur = self.conn.execute(
            "INSERT INTO proposal_label(inserted_ns,episode_id,request_id,abs_frame,goal_id,epoch,"
            "source,admitted,action,valid_indices,quality,observation_ref,payload)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self._now_ns(), episode_id, request_id, abs_frame, goal_id, epoch, source,
             1 if admitted else 0, _dumps(action),
             None if valid_indices is None else json.dumps(list(valid_indices)),
             None if quality is None else float(quality), observation_ref, _dumps(payload)))
        self.conn.commit()
        return int(cur.lastrowid)

    def record_view_manifest(self, *, manifest_id: str, view_name: str, sample_count: int,
                             gamma: float | None = None, n: int | None = None,
                             label_version: str | None = None, filter_rules: Any = None,
                             normalization_ref: str | None = None,
                             source_seqs: Iterable[int] = (), affected_requests: Iterable[str] = (),
                             notes: str = "") -> str:
        self.conn.execute(
            "INSERT OR REPLACE INTO view_manifest(manifest_id,created_ns,view_name,contract_version,"
            "label_version,gamma,n,sample_count,filter_rules,normalization_ref,source_seqs,"
            "affected_requests,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (manifest_id, self._now_ns(), view_name, self.contract_version, label_version, gamma, n,
             int(sample_count), _dumps(filter_rules), normalization_ref,
             json.dumps(sorted({int(s) for s in source_seqs})),
             json.dumps(sorted({str(r) for r in affected_requests})), notes))
        self.conn.commit()
        return manifest_id

    # ---------- readers ----------
    def _rows(self, sql: str, args: Sequence[Any], table: str) -> list[Row]:
        out = []
        for raw in self.conn.execute(sql, tuple(args)).fetchall():
            fields = dict(raw)
            for col in _JSON_COLUMNS.get(table, ()):
                if col in fields:
                    fields[col] = _loads(fields[col])
            out.append(Row(table, fields.get("seq", fields.get("manifest_id")), fields))
        return out

    def frames(self, *, episode_id: str | None = None, request_id: str | None = None,
               chunk_id: str | None = None, lo: int | None = None,
               hi: int | None = None) -> list[Row]:
        sql, args = "SELECT * FROM frame_fact WHERE 1=1", []
        for col, val in (("episode_id", episode_id), ("request_id", request_id), ("chunk_id", chunk_id)):
            if val is not None:
                sql += f" AND {col}=?"; args.append(val)
        if lo is not None:
            sql += " AND abs_frame>=?"; args.append(lo)
        if hi is not None:
            sql += " AND abs_frame<?"; args.append(hi)
        return self._rows(sql + " ORDER BY abs_frame, seq", args, "frame_fact")

    def events(self, *, request_id: str | None = None, episode_id: str | None = None,
               kinds: Sequence[str] | None = None) -> list[Row]:
        sql, args = "SELECT * FROM schedule_event WHERE 1=1", []
        if request_id is not None:
            sql += " AND request_id=?"; args.append(request_id)
        if episode_id is not None:
            sql += " AND episode_id=?"; args.append(episode_id)
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"; args.extend(kinds)
        return self._rows(sql + " ORDER BY seq", args, "schedule_event")

    def labels(self, *, target_seq: int | None = None, target_request_id: str | None = None,
               label_kind: str | None = None, episode_id: str | None = None) -> list[Row]:
        sql, args = "SELECT * FROM label_record WHERE 1=1", []
        for col, val in (("target_seq", target_seq), ("target_request_id", target_request_id),
                         ("label_kind", label_kind), ("episode_id", episode_id)):
            if val is not None:
                sql += f" AND {col}=?"; args.append(val)
        return self._rows(sql + " ORDER BY seq", args, "label_record")

    def proposals(self, *, admitted: bool | None = None, episode_id: str | None = None,
                  goal_id: str | None = None) -> list[Row]:
        sql, args = "SELECT * FROM proposal_label WHERE 1=1", []
        if admitted is not None:
            sql += " AND admitted=?"; args.append(1 if admitted else 0)
        for col, val in (("episode_id", episode_id), ("goal_id", goal_id)):
            if val is not None:
                sql += f" AND {col}=?"; args.append(val)
        return self._rows(sql + " ORDER BY seq", args, "proposal_label")

    def manifests(self, *, view_name: str | None = None) -> list[Row]:
        sql, args = "SELECT * FROM view_manifest", []
        if view_name is not None:
            sql += " WHERE view_name=?"; args.append(view_name)
        return self._rows(sql + " ORDER BY created_ns", args, "view_manifest")

    def revoked_seqs(self) -> set[int]:
        return {int(r["target_seq"]) for r in self.labels(label_kind="revoke")
                if r["target_seq"] is not None}

    def revocation_impact(self, revoke_seq: int) -> dict[str, Any]:
        """沿 manifest 反查撤销影响：受影响样本 / 视图 / 需要冻结的发布。"""
        revoke_row = self.conn.execute(
            "SELECT * FROM label_record WHERE seq=?", (revoke_seq,)).fetchone()
        if revoke_row is None or revoke_row["label_kind"] != "revoke":
            raise KeyError(f"not a revoke label: {revoke_seq}")
        original = self.conn.execute("SELECT * FROM label_record WHERE seq=?",
                                     (revoke_row["target_seq"],)).fetchone()
        if original is None:
            raise KeyError(f"revoked label missing: {revoke_seq}")
        target_seq, target_request = original["target_seq"], original["target_request_id"]
        hit = []
        for man in self.manifests():
            seqs = set(man["source_seqs"] or [])
            reqs = set(man["affected_requests"] or [])
            if (target_seq is not None and target_seq in seqs) or \
               (target_request is not None and target_request in reqs):
                hit.append(man["manifest_id"])
        return {"revoke_seq": revoke_seq, "original_label_seq": target_seq,
                "original_request_id": target_request, "affected_manifests": hit}

    def stats(self) -> dict[str, Any]:
        out: dict[str, Any] = {"path": str(self.path)}
        for tbl in ("frame_fact", "schedule_event", "label_record", "proposal_label", "view_manifest"):
            out[tbl] = int(self.conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0])
        out["revoked_labels"] = len(self.revoked_seqs())
        out["admitted_proposals"] = int(self.conn.execute(
            "SELECT COUNT(*) FROM proposal_label WHERE admitted=1").fetchone()[0])
        return out

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "FactLedger":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


class VerdictAdmissionError(RuntimeError):
    """裁定不够格当物理事实入账 ⇒ **拒收**（回显理由，不是 warn、不是静默降级）。

    判据不在这里（裁定 21 判据单一来源）：准入规则由
    `registry/verdict_identity.py::admit_as_physical_fact` 拥有，账本只执行它的结论。
    """


def _admit_verdict(verdict: Any, *, current_gate: dict[str, Any] | None = None) -> dict[str, Any]:
    """跑裁定层的准入闸。延迟 import：`harness/` 不该在导入期就拉起裁定层与上游门禁模块。"""
    from registry.verdict_identity import admit_as_physical_fact
    return admit_as_physical_fact(verdict, current=current_gate)


def ingest_runtime_result(ledger: FactLedger, result: Any, *, episode_id: str,
                          goal_id: str = "lift", epoch: int = 1, lease_generation: int = 0,
                          source: str = "policy",
                          verdict: Any = None, admission: dict[str, Any] | None = None,
                          observation_only: bool = False, on_refusal: str = "raise",
                          current_gate: dict[str, Any] | None = None) -> dict[str, int]:
    """把 `harness/runtime_adapter.py` 的 `RuntimeResult` 事件落成账本行。

    只读消费既有契约对象，不修改 `harness/contracts.py` 或 `runtime_adapter.py`。
    事件映射：requested→request_received、accepted→request_admitted、
    committed→result_committed、activated→physical_activated。

    **准入闸（P1-5，fail-closed）**：调用方必须**显式声明本次入账的依据**，二选一——

    - `verdict=<裁定身份>`（`registry.verdict_identity.VerdictIdentity` 或等价 dict）：
      走 `admit_as_physical_fact()`，**只有 `usable_for == physical_fact` 且 `gate_build`
      等于门禁现值**才准入；其余各档一律**拒收并回显理由**（不是 warn），
      同时写一条 `verdict_refused` 事件留档（**不写任何帧/标签行**）。
      `on_refusal="event"` 时不抛错、只留档并返回 —— 用于「把不可用的裁定登记下来备查」。
    - `observation_only=True`：声明这批行是 **env 直接产出的原始观测/事件**，
      不是被门禁分级的裁定。它**没有** `gate_build`，因此写一条 `verdict_identity_absent`
      事件把这件事记在账上，且下游 `registry.release_bundle.build_bundle` 会拒绝
      把它翻成 `DirectionScore` 进发布包。

    两者都不给 ⇒ **抛错**。默认拒绝的理由：不声明就入账，等于把「没有身份」和「忘了闸」
    在账本里混成同一种行，而下游会把它当数字用（增补五 §9-C③ 点名的事故形状）。

    **预先写明的后果**（D 派工单「与 B §5 的交点」）：B 的 v1.6 落地会升 `GATE_BUILD`，
    届时现存 48 条 `physical_fact` 会整批变成「与门禁现值不符」⇒ 本闸全部拒收、
    `physical_fact` 由 48 → 0。**那是正确行为，不是回归红点**；要在 v1.6 上重新出裁定，
    不是把闸放宽。
    """
    if on_refusal not in ("raise", "event"):
        raise ValueError(f"on_refusal 只接 'raise' / 'event'，收到 {on_refusal!r}")
    counts = {"events": 0, "frames": 0, "labels": 0, "verdict_admitted": 0,
              "verdict_refused": 0, "verdict_identity_absent": 0}
    if verdict is None and admission is None:
        if not observation_only:
            raise VerdictAdmissionError(
                "必须显式声明本次入账的依据：给 verdict=<裁定身份> 走 physical_fact 准入闸，"
                "或给 observation_only=True 声明这是 env 直接产出的原始观测（不是被分级的门禁裁定）。"
                "两者都不给 ⇒ 拒收（fail-closed）。")
        ledger.append_event(episode_id=episode_id, kind="verdict_identity_absent",
                            goal_id=goal_id, epoch=epoch, lease_generation=lease_generation,
                            payload={"declared": "observation_only",
                                     "meaning": ("本批行是 env 直接产出的观测/事件，**不是**被门禁分级的"
                                                 "裁定 ⇒ 没有 gate_build，不得被翻成 DirectionScore "
                                                 "进发布包（build_bundle 会拒）。"),
                                     "source": source})
        counts["events"] += 1
        counts["verdict_identity_absent"] = 1
    else:
        adm = admission if admission is not None else _admit_verdict(verdict,
                                                                    current_gate=current_gate)
        admitted = bool(adm.get("admitted"))
        ledger.append_event(episode_id=episode_id,
                            kind="verdict_admitted" if admitted else "verdict_refused",
                            goal_id=goal_id, epoch=epoch, lease_generation=lease_generation,
                            payload={"identity": adm.get("identity"),
                                     "gate_current": adm.get("gate_current"),
                                     "refusal_reasons": adm.get("refusal_reasons"),
                                     "arm": adm.get("arm"),
                                     "source_path": adm.get("source_path"),
                                     "rule": adm.get("rule"),
                                     "frames_written": admitted})
        counts["events"] += 1
        counts["verdict_admitted" if admitted else "verdict_refused"] = 1
        if not admitted:
            reason = adm.get("refusal_reason") or "；".join(adm.get("refusal_reasons") or [])
            if on_refusal == "raise":
                raise VerdictAdmissionError(
                    f"拒收（不是 warn）：{reason}。已写一条 verdict_refused 事件留档，"
                    f"**没有**写任何帧/标签行。arm={adm.get('arm')} "
                    f"source={adm.get('source_path')}")
            return counts
    kind_map = {"requested": "request_received", "accepted": "request_admitted",
                "committed": "result_committed", "activated": "physical_activated",
                "partially_executed": "partially_executed", "cancelled": "cancelled",
                "expired": "expired"}
    for ev in result.events:
        kind = kind_map.get(getattr(ev, "kind", ""), None)
        if kind is not None:
            ledger.append_event(episode_id=episode_id, kind=kind, request_id=ev.request_id,
                                abs_frame=ev.frame, epoch=ev.epoch, goal_id=ev.goal_id,
                                lease_generation=lease_generation,
                                payload={"queue_c": list(ev.queue.c), "reason": ev.reason})
            counts["events"] += 1
            continue
        # OutcomeEvent：物理事实 + 奖励标签分开写，奖励默认 pending，不冒充 0。
        state = getattr(ev, "reward_state", "final")
        frame_seq = ledger.append_frame(
            episode_id=episode_id, abs_frame=ev.frame, goal_id=ev.goal_id, epoch=ev.epoch,
            lease_generation=lease_generation, source=source,
            execution_status="activated", request_id=ev.request_id,
            measured_state=ev.observation, policy_version=ev.version,
            payload={"terminal": ev.terminal, "terminal_kind": ev.terminal_kind,
                     "phase": ev.phase, "grasp_verified": ev.grasp_verified,
                     "max_rise": ev.max_rise, "failure_phase": ev.failure_phase})
        counts["frames"] += 1
        ledger.append_label(episode_id=episode_id, label_kind="reward", target_seq=frame_seq,
                            target_request_id=ev.request_id, value=float(ev.reward),
                            reward_state="final" if ev.terminal else state, source=ev.source or "env")
        counts["labels"] += 1
        if ev.terminal:
            ledger.append_event(episode_id=episode_id, kind="episode_end", request_id=ev.request_id,
                                abs_frame=ev.frame, epoch=ev.epoch, goal_id=ev.goal_id,
                                payload={"terminal_kind": ev.terminal_kind})
            counts["events"] += 1
    return counts
