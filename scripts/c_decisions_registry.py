#!/usr/bin/env python3
"""C 线：`work/decisions/` 的**正式登记处**（待办 2 / 执行单 P0-4，裁定 29.5 第 1 条改判 P0）。

为什么要有它：本轮 D 自己撞上「同一条裁定在三个地方有三种措辞、没人能说出哪份是权威」的事。
过渡期的做法是每天一个 markdown（`decisions_2026092{8,9}*.md`），它的问题是：
① 一条决定可以被就地改写而看不出来；② 撤销靠人在原文上划一句话，划没划要读全文才知道；
③ ack 散在各线自己的文档里，「谁还没 ack」不可查；④ 判据被抄进登记文本，于是有了第二份口径。

**原子单位 = 一条决定一文件、内容寻址、只追加、撤销靠新条目指向旧条目**（与 `supersedes` 同型）。

目录（全部在 `work/decisions/registry/`，C 的写入边界内）：
    entries/<decision_id>__<sha256_12>.json   一条决定一个文件；文件名带内容哈希
    events/<seq>-<kind>-<sha256_12>.json      append-only 事件流（ack / revoke / supersede / annotate）
    index.json                                **派生**索引（可由 entries+events 重建，不是权威）
    README.md                                 口径与编号规则

四条验收（执行单 P0-4，D 会逐条核）与本脚本的对应：
1. **内容哈希可取回**：`show --hash <sha256 或前缀>`；改一个字节 ⇒ 文件名里的 sha256_12 与
   重算值不符 ⇒ `verify` 报红（`tampered`）。哈希真的在寻址，不是装饰。
2. **撤销可执行且有牙**：`revoke` 写一条**新**事件，被撤条目的 `status` 由事件流派生为
   `retired`，**原条目文件一个字节都不改**（selfcheck 用 before/after 的 sha256 逐字节证明）。
   「牙」= `verify` 会把「已被撤销却仍被某条 active 决定当权威引用」判红（`dangling_authority`）——
   撤销若不会让任何东西变红，它就不是机制。
3. **ack 可核**：`acks` / `list --missing-acks` 给出每条决定「哪几线已 ack、哪几线还没」；
   未 ack 的**可见**，不靠人记。
4. **不重造口径**：登记处只存「决定 + 证据指针 + ack」。摄取历史条目时 `statement_kind =
   "pointer_only"`（只给标题 + 源文件锚点 + sha256_12，**不抄正文**）；判据的唯一来源仍是
   门禁脚本本身（裁定 21）。`verify` 会红任何 `statement_kind="full_text"` 且带 `criteria` 字段的条目。

编号规则（执行单重申，登记处**只接续、不重编**）：
    DR-D<n>      D 线裁定序号
    DR-0<n>      B 线门禁 / 流程决定
    ADR-A-<n>    A 线架构决定
    ADR-C-<n>    C 线架构决定
登记处自己的事件不占上述号段（事件 id = `EV-<seq>`）。

用法：
    python3 scripts/c_decisions_registry.py ingest            # 摄取历史 markdown（pointer_only）
    python3 scripts/c_decisions_registry.py add --line C --title ... --statement ... [--affects A,B]
    python3 scripts/c_decisions_registry.py ack --id ADR-C-009 --line B [--evidence path]
    python3 scripts/c_decisions_registry.py revoke --id DR-Dxx --by D --reason ... [--authority ptr]
    python3 scripts/c_decisions_registry.py show --id ADR-C-009 | --hash 3f2a...
    python3 scripts/c_decisions_registry.py list [--missing-acks] [--status retired]
    python3 scripts/c_decisions_registry.py verify            # 判据自检（能红）；exit 1 = 有红点
    python3 scripts/c_decisions_registry.py selfcheck         # 合成注册表上的双向变异自检
    python3 scripts/c_decisions_registry.py rebuild-index
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "work" / "decisions" / "registry"
DECISIONS_DIR = ROOT / "work" / "decisions"
SCHEMA = "c_decision_entry/v1"
EVENT_SCHEMA = "c_decision_event/v1"

# 摄取源：过渡期的每日 markdown（迁移后它们保留为**只读历史**，DR-001 的口径）。
INGEST_SOURCES = (
    "work/decisions/decisions_20260928.md",
    "work/decisions/decisions_20260928_A.md",
    "work/decisions/decisions_20260928_B.md",
    "work/decisions/decisions_20260928_C.md",
    "work/decisions/decisions_20260929.md",
    "work/decisions/decisions_20260929_A.md",
    "work/decisions/decisions_20260929_C.md",
)
# `## DR-003 标题` / `## ADR-A-008 标题` / `- **DR-D14 标题**（增补六 §1）`
HEADING_RE = re.compile(r"^##\s+(?P<id>DR-D\d+|DR-\d+|ADR-[ABC]-\d+)\s+(?P<title>.+?)\s*$")
BULLET_RE = re.compile(r"^-\s+\*\*(?P<id>DR-D\d+|DR-\d+|ADR-[ABC]-\d+)[\s:：]*(?P<title>.*?)\*\*(?P<rest>.*)$")
ID_RE = re.compile(r"^(DR-D(\d+)|DR-0*(\d+)|ADR-([ABC])-(\d+))$")
LINES = ("A", "B", "C", "D")
EVENT_KINDS = ("ack", "revoke", "supersede", "annotate")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def canonical(obj: Any) -> str:
    """规范化 JSON：键排序、无多余空白、UTF-8 原样。内容寻址的分母就是它。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


# 登记**簿记**字段：谁在什么时候把它记进来、第几版。它们每次登记都会变，
# 但**不属于「决定了什么」**⇒ 判重与 `payload_sha256` 都要把它们剔掉。
BOOKKEEPING_FIELDS = ("version_seq", "registered_at", "registered_by", "payload_sha256")


def payload_of(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k not in BOOKKEEPING_FIELDS}


def payload_sha256(entry: dict[str, Any]) -> str:
    """「决定了什么」的哈希。缺 `payload_sha256` 字段的历史条目也能重算（此时等于全量哈希）。"""
    return content_sha256(payload_of(entry))


def _sha12_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _sha12_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def _version_sort_key(record: dict[str, Any]) -> tuple[int, str, str]:
    """同一 `decision_id` 的多版本按**写入时序**排序。

    不能按文件名排：文件名尾是内容哈希（`<id>__<sha256_12>.json`），字典序与写入时间**无关**，
    于是「最新版」会随机落在 v1 或 v2 上 ⇒ `current_sha256()` 会指错版本 ⇒
    旧 ack 永远显示 `matches_current_content=true`（判据失去牙）。
    权威键是条目自带的 `version_seq`（写入时定，属内容 ⇒ 可被哈希保护）；
    没有该字段的历史条目退化为 `registered_at` → 文件名。
    """
    entry = record.get("entry") or {}
    seq = entry.get("version_seq")
    return (seq if isinstance(seq, int) else 0,
            str(entry.get("registered_at") or ""),
            str(record.get("path").name if record.get("path") else ""))


def id_kind(decision_id: str) -> str | None:
    """号段判定（登记处只接续、不重编）。"""
    if decision_id.startswith("DR-D"):
        return "DR-D"
    if decision_id.startswith("ADR-A-"):
        return "ADR-A"
    if decision_id.startswith("ADR-C-"):
        return "ADR-C"
    if decision_id.startswith("ADR-B-"):
        return "ADR-B"
    if decision_id.startswith("DR-"):
        return "DR-00"
    return None


def _resolve_ref(ref: Any, statuses: dict[str, str]) -> str | None:
    """把引用（可能是裸 id，也可能是带 id 的文件路径/锚点）解析成登记处里的 id。

    精确命中优先；否则取**最长**的 id 子串命中（`next(...)` 那种「随便命中一个」的写法
    依赖 set 迭代序，而 Python 的字符串哈希每次进程都随机 ⇒ 报红顺序不可复现）。
    """
    text = str(ref)
    if text in statuses:
        return text
    hits = [known for known in statuses if known and known in text]
    return max(hits, key=lambda known: (len(known), known)) if hits else None


def owner_line(decision_id: str) -> str | None:
    kind = id_kind(decision_id)
    return {"DR-D": "D", "DR-00": "B", "ADR-A": "A", "ADR-C": "C", "ADR-B": "B"}.get(kind)


def ordinal(decision_id: str) -> int | None:
    match = ID_RE.match(decision_id)
    if not match:
        return None
    digits = next((g for g in match.groups()[1:] if g and g.isdigit()), None)
    return int(digits) if digits else None


class DecisionRegistry:
    """内容寻址、append-only 的决定登记处。

    写入只有两种：① `entries/` 里**新增**一个文件（一条决定，写定后不改）；
    ② `events/` 里**追加**一个事件文件（ack / revoke / supersede / annotate）。
    任何「改状态」都不是改条目，而是加事件 —— 于是「原来写的是什么」永远可查。
    """

    def __init__(self, root: Path = DEFAULT_REGISTRY):
        self.root = Path(root)
        self.entries_dir = self.root / "entries"
        self.events_dir = self.root / "events"
        self.index_path = self.root / "index.json"

    # --- 基础设施 ---
    def ensure_dirs(self) -> None:
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load_entries(self) -> dict[str, dict[str, Any]]:
        """decision_id → {entry, path, sha256, sha256_12_in_name, tampered}。同 id 多版本全部保留。"""
        out: dict[str, dict[str, Any]] = {}
        if not self.entries_dir.is_dir():
            return out
        for path in sorted(self.entries_dir.glob("*.json")):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:                                   # noqa: BLE001
                out.setdefault("_unreadable", {})[path.name] = f"{type(exc).__name__}: {exc}"
                continue
            digest = content_sha256(entry)
            name_sha = path.stem.split("__")[-1]
            recomputed_payload = payload_sha256(entry)
            stated_payload = entry.get("payload_sha256")
            record = {"entry": entry, "path": path, "sha256": digest, "sha256_12": digest[:12],
                      "sha256_12_in_name": name_sha, "tampered": name_sha != digest[:12],
                      "decision_id": entry.get("decision_id"),
                      "registered_at": entry.get("registered_at"),
                      "version_seq": entry.get("version_seq"),
                      "payload_sha256": recomputed_payload,
                      "payload_sha256_in_entry": stated_payload,
                      "payload_mismatch": bool(stated_payload) and stated_payload != recomputed_payload}
            key = record["decision_id"] or path.stem
            out.setdefault(key, {})
            if isinstance(out[key], dict) and "entry" in out[key]:
                # 同一个 id 有第二份内容不同的条目 ⇒ 版本链（后者必须是 supersede 事件带来的）
                out[key] = {"versions": [out[key], record]}
            elif isinstance(out[key], dict) and "versions" in out[key]:
                out[key]["versions"].append(record)
            else:
                out[key] = record
        for record in out.values():
            if isinstance(record, dict) and "versions" in record:
                record["versions"].sort(key=_version_sort_key)
        return out

    def _iter_versions(self, record: Any) -> Iterable[dict[str, Any]]:
        """把 `load_entries()` 的一条记录展平成版本列表（时序）。

        空记录 / 非条目记录（例如 `_unreadable` 那个桶）展平成**空列表**，不是 `[{}]`。
        这条不是洁癖：`add()` 要靠它数「已有几版」来定 `version_seq`，
        多产出一个空 dict 就会把第一版编成 `version_seq=2`（今天真踩到，
        于是两版同 seq、排序退化成按文件名 ⇒ 旧 ack 仍显示 `matches_current_content=true`）。
        """
        if not isinstance(record, dict) or not record:
            return
        if "versions" in record:
            yield from record["versions"]
        elif "entry" in record:
            yield record

    def load_events(self) -> list[dict[str, Any]]:
        events = []
        if not self.events_dir.is_dir():
            return events
        for path in sorted(self.events_dir.glob("*.json"),
                           key=lambda p: (int(p.name.split("-")[0]) if p.name.split("-")[0].isdigit()
                                          else 0, p.name)):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:                                   # noqa: BLE001
                events.append({"path": path, "unreadable": f"{type(exc).__name__}: {exc}"})
                continue
            digest = content_sha256({k: v for k, v in payload.items() if k != "event_sha256_12"})
            name_sha = path.stem.split("-")[-1]
            events.append({**payload, "path": path, "event_sha256": digest,
                           "tampered": name_sha != digest[:12]})
        return events

    def next_event_seq(self) -> int:
        self.ensure_dirs()
        seqs = [int(p.name.split("-")[0]) for p in self.events_dir.glob("*.json")
                if p.name.split("-")[0].isdigit()]
        return (max(seqs) + 1) if seqs else 1

    # --- 写：新增一条决定 ---
    def add(self, *, decision_id: str | None, line: str, title: str, statement: str | None,
            affects: Sequence[str] = (), requires_ack_from: Sequence[str] | None = None,
            evidence: Sequence[dict[str, Any]] = (), source: dict[str, Any] | None = None,
            supersedes: Sequence[str] = (), authority_pointers: Sequence[str] = (),
            statement_kind: str = "self_authored", decided_at: str | None = None,
            registered_by: str = "C（登记处）", extra: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_dirs()
        if decision_id is None:
            decision_id = self.next_id(line)
        if id_kind(decision_id) is None:
            raise ValueError(f"号段不合法：{decision_id}（只接 DR-D<n> / DR-0<n> / ADR-[ABC]-<n>）")
        if owner_line(decision_id) and owner_line(decision_id) != line:
            raise ValueError(f"号段与线不符：{decision_id} 属 {owner_line(decision_id)} 线，"
                             f"却以 line={line} 登记（登记处不代发别人的号）")
        existing = self.load_entries().get(decision_id)
        prior = list(self._iter_versions(existing))
        version_seq = len(prior) + 1
        # ① 决定**内容**（payload）：「决定了什么」。重复登记按它判重。
        payload: dict[str, Any] = {
            "schema": SCHEMA,
            "decision_id": decision_id,
            "id_kind": id_kind(decision_id),
            "line": line,
            "title": title,
            "statement": statement,
            "statement_kind": statement_kind,
            "decided_at": decided_at,
            "affects": sorted(set(affects)),
            # None = 未指定 ⇒ 由 affects 推；() = **显式**声明「本条不设 ack 义务」
            # （摄取历史条目用它：ack 纪律从登记处生效那天起算，不追溯给 72 条老裁定补 ack）。
            "requires_ack_from": (sorted(set(affects)) if requires_ack_from is None
                                  else sorted(set(requires_ack_from))),
            "evidence_pointers": list(evidence),
            "source": source,
            "supersedes": list(supersedes),
            "authority_pointers": list(authority_pointers),
            "criteria_single_source": ("判据不在本条里（裁定 21：判据单一来源）。本条只存"
                                       "「决定 + 证据指针 + ack」；要判据请读 authority_pointers "
                                       "指的那个文件本身。"),
        }
        if extra:
            payload["extra"] = extra
        payload_sha = content_sha256(payload)
        for version in prior:
            if payload_sha256(version["entry"]) == payload_sha:
                raise FileExistsError(
                    "同一份决定内容已登记过（append-only：不重写既有文件，也不为它新开一版）："
                    f"{Path(version['path']).name}，payload_sha256={payload_sha[:12]}")
        # ② 登记**簿记**：谁、什么时候、第几版。
        #    `version_seq` 是版本顺序的**权威键**（见 `_version_sort_key`）：不靠文件名
        #    （尾部是内容哈希，字典序与写入时间无关）、也不靠 mtime（文件系统状态，可被碰）。
        entry: dict[str, Any] = {**payload, "version_seq": version_seq,
                                 "registered_at": _now_iso(),
                                 "registered_by": registered_by,
                                 "payload_sha256": payload_sha}
        digest = content_sha256(entry)
        path = self.entries_dir / f"{decision_id}__{digest[:12]}.json"
        if path.exists():
            raise FileExistsError(f"同内容条目已在（append-only，不重写）：{path.name}")
        self._write_json(path, entry)
        return {"decision_id": decision_id, "path": str(path), "sha256": digest,
                "sha256_12": digest[:12], "payload_sha256": payload_sha, "entry": entry}

    def source_docs(self, sources: Sequence[str] | None = None) -> list[Path]:
        """并号扫描面。`sources=None` ⇒ `work/decisions/` 下**全部** markdown（登记处自己除外）。

        不能写死成 `INGEST_SOURCES` 那几份：别的线随时会新开当日文档、或在旧文档里补发新号
        （今天就实测到 `decisions_20260928_B.md:822` 补发 `DR-014`）⇒ 写死就扫不到 ⇒ 撞号。
        「摄取范围」与「并号扫描面」是两件事：前者要稳定可复现，后者要**尽量宽**（宁可多认一个号）。
        """
        if sources is not None:
            return [ROOT / rel for rel in sources]
        return sorted(p for p in DECISIONS_DIR.rglob("*.md")
                      if p.is_file() and DEFAULT_REGISTRY not in p.parents)

    def ids_in_sources(self, sources: Sequence[str] | None = None) -> set[str]:
        """源 markdown 里出现过的号（防撞号：登记处只接续、不重编）。"""
        found: set[str] = set()
        for path in self.source_docs(sources):
            if not path.exists():
                continue
            for raw in path.read_text(encoding="utf-8").splitlines():
                match = HEADING_RE.match(raw) or BULLET_RE.match(raw)
                if match:
                    found.add(match.group("id"))
        return found

    def next_id(self, line: str, sources: Sequence[str] | None = None) -> str:
        """按号段接续下一个空号（B=`DR-0<n>`、D=`DR-D<n>`、A/C=`ADR-[AC]-<n>`）。

        `sources=None` ⇒ 扫 `work/decisions/` 全量（见 `source_docs`，宁宽勿漏）；
        传 `[]` ⇒ **只看登记处自己**。后者是给合成注册表自检用的：不隔离的话，
        合成注册表也会被真文档的号带着走，于是「901→902」这条判据只能写成
        `in ("ADR-C-902", "ADR-C-009")` —— 两个都算过 = 没有牙。
        """
        prefixes = {"A": "ADR-A-", "B": "DR-", "C": "ADR-C-", "D": "DR-D"}
        if line not in prefixes:
            raise ValueError(f"未知线：{line}")
        prefix = prefixes[line]
        taken = {ordinal(did) for did in (self.known_ids() | self.ids_in_sources(sources))
                 if did.startswith(prefix) and not (prefix == "DR-" and did.startswith("DR-D"))}
        taken = {n for n in taken if n is not None}
        n = (max(taken) + 1) if taken else 1
        return f"{prefix}{n:03d}" if prefix in ("ADR-A-", "ADR-C-", "DR-") else f"{prefix}{n}"

    # --- 写：追加事件 ---
    def append_event(self, kind: str, *, target_id: str, by: str, reason: str | None = None,
                     line: str | None = None, evidence: Sequence[dict[str, Any]] = (),
                     target_sha256: str | None = None,
                     new_decision_id: str | None = None) -> dict[str, Any]:
        if kind not in EVENT_KINDS:
            raise ValueError(f"未知事件类型：{kind}（只接 {EVENT_KINDS}）")
        self.ensure_dirs()
        known = self.known_ids()
        if target_id not in known:
            raise KeyError(f"撤销/ack 的目标不存在：{target_id}（登记处不给不存在的东西改状态；"
                           f"现有 {len(known)} 条）")
        seq = self.next_event_seq()
        event: dict[str, Any] = {
            "schema": EVENT_SCHEMA, "seq": seq, "kind": kind, "target_id": target_id,
            "target_sha256": target_sha256 or self.current_sha256(target_id),
            "by": by, "line": line or by, "reason": reason, "at": _now_iso(),
            "evidence_pointers": list(evidence),
            "new_decision_id": new_decision_id,
            "append_only": ("本事件是**新增文件**，被指向的条目文件一个字节都不改；"
                            "条目的 status 由事件流**派生**，不是被改写出来的。"),
        }
        digest = content_sha256(event)
        path = self.events_dir / f"{seq:04d}-{kind}-{digest[:12]}.json"
        self._write_json(path, event)
        return {"seq": seq, "kind": kind, "path": str(path), "sha256": digest, "event": event}

    def known_ids(self) -> set[str]:
        ids = set()
        for record in self.load_entries().values():
            for version in self._iter_versions(record):
                did = version.get("decision_id")
                if did:
                    ids.add(did)
        return ids

    def current_sha256(self, decision_id: str) -> str | None:
        record = self.load_entries().get(decision_id)
        if not record:
            return None
        versions = list(self._iter_versions(record))
        return versions[-1]["sha256"] if versions else None

    # --- 读：派生状态 ---
    def status(self, decision_id: str, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        events = events if events is not None else self.load_events()
        mine = [e for e in events if e.get("target_id") == decision_id
                and e.get("kind") in ("revoke", "supersede")]
        mine.sort(key=lambda e: (e.get("seq") or 0, e.get("at") or ""))
        if not mine:
            return {"decision_id": decision_id, "status": "active", "events": []}
        last = mine[-1]
        return {"decision_id": decision_id,
                "status": "superseded" if last["kind"] == "supersede" else "retired",
                "by_event": {"seq": last.get("seq"), "kind": last.get("kind"),
                             "by": last.get("by"), "at": last.get("at"),
                             "reason": last.get("reason"),
                             "path": str(last.get("path")) if last.get("path") else None,
                             "new_decision_id": last.get("new_decision_id")},
                "events": [{"seq": e.get("seq"), "kind": e.get("kind"), "at": e.get("at")}
                           for e in mine]}

    def acks(self, decision_id: str, entry: dict[str, Any],
             events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        events = events if events is not None else self.load_events()
        mine = [e for e in events if e.get("target_id") == decision_id and e.get("kind") == "ack"]
        acked = {}
        for event in mine:
            line = (event.get("line") or event.get("by") or "?").upper()[:1]
            acked[line] = {"at": event.get("at"), "by": event.get("by"),
                           "seq": event.get("seq"),
                           "target_sha256": event.get("target_sha256"),
                           "matches_current_content": (event.get("target_sha256")
                                                       == self.current_sha256(decision_id)),
                           "evidence_pointers": event.get("evidence_pointers") or []}
        required = list(entry.get("requires_ack_from") or [])
        own = owner_line(decision_id)
        missing = [line for line in required if line not in acked and line != own]
        return {"decision_id": decision_id, "acked_by": sorted(acked), "acks": acked,
                "requires_ack_from": required, "missing_acks": missing,
                "self_line": own,
                "note": ("作者线自己不给自己 ack（`missing_acks` 里排除它）；"
                         "未 ack 的**可见**，不靠人记（验收 3）。")}

    def index(self) -> dict[str, Any]:
        entries = self.load_entries()
        events = self.load_events()
        rows = []
        for key, record in sorted(entries.items()):
            if key == "_unreadable":
                continue
            for version in self._iter_versions(record):
                entry = version["entry"]
                did = entry.get("decision_id") or key
                state = self.status(did, events)
                rows.append({
                    "decision_id": did, "line": entry.get("line"),
                    "id_kind": entry.get("id_kind"), "title": entry.get("title"),
                    "statement_kind": entry.get("statement_kind"),
                    "sha256": version["sha256"], "sha256_12": version["sha256_12"],
                    "path": str(version["path"].relative_to(self.root))
                    if version["path"].is_relative_to(self.root) else str(version["path"]),
                    "tampered": version["tampered"],
                    "registered_at": entry.get("registered_at"),
                    "decided_at": entry.get("decided_at"),
                    "affects": entry.get("affects"),
                    "status": state["status"], "status_detail": state.get("by_event"),
                    "acks": self.acks(did, entry, events),
                })
        return {"schema": "c_decision_index/v1", "generated_at": _now_iso(),
                "registry_root": str(self.root),
                "derived": ("本索引是**派生**的：由 entries/ + events/ 重算得出"
                            "（`rebuild-index`）。权威是那两堆文件，不是本索引。"),
                "n_decisions": len({r['decision_id'] for r in rows}),
                "n_versions": len(rows), "n_events": len(events),
                "counts_by_line": {line: sum(1 for r in rows if r["line"] == line)
                                   for line in LINES},
                "counts_by_status": {st: sum(1 for r in rows if r["status"] == st)
                                     for st in ("active", "retired", "superseded")},
                "n_missing_acks": sum(1 for r in rows if r["acks"]["missing_acks"]),
                "decisions": rows}

    def rebuild_index(self) -> dict[str, Any]:
        payload = self.index()
        self._write_json(self.index_path, payload)
        return payload

    # --- 判据：verify（能红） ---
    def verify(self) -> dict[str, Any]:
        entries = self.load_entries()
        events = self.load_events()
        red: list[dict[str, Any]] = []
        warn: list[dict[str, Any]] = []

        for key, record in entries.items():
            if key == "_unreadable":
                for name, err in record.items():
                    red.append({"check": "entry_unreadable", "file": name, "detail": err})
                continue
            for version in self._iter_versions(record):
                if version["tampered"]:
                    red.append({"check": "tampered", "decision_id": version["decision_id"],
                                "file": version["path"].name,
                                "detail": (f"文件名里的 sha256_12={version['sha256_12_in_name']}，"
                                           f"重算={version['sha256_12']} ⇒ 内容被改过"
                                           "（append-only 被破坏；验收 1 的牙）")})
                if version.get("payload_mismatch"):
                    red.append({"check": "payload_sha256_mismatch",
                                "decision_id": version["decision_id"],
                                "file": version["path"].name,
                                "detail": (f"条目自称 payload_sha256="
                                           f"{str(version['payload_sha256_in_entry'])[:12]}，"
                                           f"重算={version['payload_sha256'][:12]} ⇒ "
                                           "「决定了什么」被改过而文件名哈希被同步重算"
                                           "（tampered 的同型，只是改的是 payload 那一层）")})
                elif not version.get("payload_sha256_in_entry"):
                    warn.append({"check": "version_bookkeeping_missing",
                                 "decision_id": version["decision_id"],
                                 "file": version["path"].name,
                                 "detail": ("条目没有 version_seq/payload_sha256（早期格式）⇒ "
                                            "版本顺序退化为按 registered_at/文件名；"
                                            "重新摄取即可补齐")})
                entry = version["entry"]
                if entry.get("statement_kind") == "full_text" and entry.get("criteria"):
                    red.append({"check": "criteria_duplicated", "decision_id": entry.get("decision_id"),
                                "detail": ("登记处不得复制判定逻辑（裁定 21 判据单一来源；验收 4）。"
                                           "把 criteria 换成 authority_pointers 指针。")})
                if entry.get("statement_kind") == "pointer_only" and not entry.get("source"):
                    red.append({"check": "pointer_without_source",
                                "decision_id": entry.get("decision_id"),
                                "detail": "pointer_only 却没有 source 锚点 ⇒ 取不回原文"})

        for event in events:
            if event.get("unreadable"):
                red.append({"check": "event_unreadable", "file": str(event.get("path")),
                            "detail": event["unreadable"]})
                continue
            if event.get("tampered"):
                red.append({"check": "event_tampered", "file": event["path"].name,
                            "detail": f"seq={event.get('seq')} kind={event.get('kind')} 哈希不符"})
            target = event.get("target_id")
            if target not in entries:
                red.append({"check": "event_target_missing", "file": event["path"].name,
                            "detail": f"事件指向不存在的决定 {target}"})
                continue
            current = self.current_sha256(target)
            if (event.get("kind") in ("revoke", "supersede")
                    and event.get("target_sha256") and current
                    and event["target_sha256"] != current):
                warn.append({"check": "revoked_version_not_current", "target_id": target,
                             "detail": (f"撤销时指向 {event['target_sha256'][:12]}，"
                                        f"当前最新是 {current[:12]} ⇒ 撤的是旧版本，"
                                        "新版本仍 active（需要重新裁）")})

        # 撤销的**牙**：被撤条目仍被某条 active 决定当权威引用 ⇒ 红（验收 2）
        statuses: dict[str, str] = {}
        for key, record in entries.items():
            if key == "_unreadable":
                continue
            for version in self._iter_versions(record):
                did = version["entry"].get("decision_id")
                if did:
                    statuses[did] = self.status(did, events)["status"]
        for key, record in entries.items():
            if key == "_unreadable":
                continue
            for version in self._iter_versions(record):
                entry = version["entry"]
                did = entry.get("decision_id")
                if statuses.get(did) != "active":
                    continue
                # 两类引用的语义**相反**，必须分开判（合并判会让「传导成功」也报红 ⇒ 判据恒红）：
                #   authority_pointers = 「我拿它当权威」⇒ 权威死了而我还 active = 真红（撤销的牙）
                #   supersedes         = 「我取代它」    ⇒ 它非 active 才是传导**成功**；
                #                                        它仍 active = 取代只写了一半（漏了事件）= 另一种红
                for ref in sorted(str(x) for x in (entry.get("authority_pointers") or [])):
                    ref_id = _resolve_ref(ref, statuses)
                    if ref_id and ref_id != did and statuses.get(ref_id) in ("retired", "superseded"):
                        red.append({"check": "dangling_authority", "decision_id": did,
                                    "referenced": ref_id, "referenced_via": "authority_pointers",
                                    "referenced_status": statuses.get(ref_id),
                                    "detail": (f"{did} 仍 active，却把已 "
                                               f"{statuses.get(ref_id)} 的 {ref_id} 当权威引用 ⇒ "
                                               "撤销没有传导下去（这就是撤销的牙）")})
                for ref in sorted(str(x) for x in (entry.get("supersedes") or [])):
                    ref_id = _resolve_ref(ref, statuses)
                    if ref_id and ref_id != did and statuses.get(ref_id) == "active":
                        red.append({"check": "supersede_not_propagated", "decision_id": did,
                                    "referenced": ref_id, "referenced_via": "supersedes",
                                    "referenced_status": "active",
                                    "detail": (f"{did} 声明取代 {ref_id}，但 {ref_id} 仍 active ⇒ "
                                               "取代只写了一半：还缺一条指向它的 `supersede` 事件"
                                               "（状态由事件流派生，不由条目字段改写）")})
        return {"registry_root": str(self.root), "verified_at": _now_iso(),
                "n_entries": sum(len(list(self._iter_versions(r)))
                                 for k, r in entries.items() if k != "_unreadable"),
                "n_events": len(events), "red": red, "warn": warn,
                "pass": not red,
                "checks": ["tampered", "entry_unreadable", "event_unreadable", "event_tampered",
                           "event_target_missing", "criteria_duplicated", "pointer_without_source",
                           "dangling_authority", "supersede_not_propagated",
                           "payload_sha256_mismatch",
                           "revoked_version_not_current(warn)",
                           "version_bookkeeping_missing(warn)"]}

    # --- 摄取：历史 markdown → pointer_only 条目 ---
    def ingest(self, sources: Sequence[str] = INGEST_SOURCES, *, dry_run: bool = False,
               only: Sequence[str] = ()) -> dict[str, Any]:
        existing = self.known_ids()
        rows, skipped = [], []
        for rel in sources:
            path = ROOT / rel if not Path(rel).is_absolute() else Path(rel)
            if not path.exists():
                skipped.append({"source": rel, "reason": "文件不存在"})
                continue
            text = path.read_text(encoding="utf-8")
            file_sha = _sha12_file(path)
            lines = text.splitlines()
            hits: list[dict[str, Any]] = []
            for idx, raw in enumerate(lines, start=1):
                match = HEADING_RE.match(raw) or BULLET_RE.match(raw)
                if not match:
                    continue
                hits.append({"id": match.group("id"), "title": match.group("title").strip(),
                             "line": idx, "kind": "heading" if raw.startswith("##") else "bullet"})
            for pos, hit in enumerate(hits):
                end = hits[pos + 1]["line"] - 1 if pos + 1 < len(hits) else len(lines)
                did = hit["id"]
                if only and did not in only:
                    continue
                if did in existing:
                    skipped.append({"source": rel, "decision_id": did,
                                    "reason": "已在登记处（append-only：不重写、不重复摄取）"})
                    continue
                anchor = {"file": rel, "sha256_12": file_sha, "lines": f"{hit['line']}-{end}",
                          "heading_line": hit["line"], "element": hit["kind"],
                          "title_as_written": hit["title"]}
                if dry_run:
                    rows.append({"decision_id": did, "source": anchor})
                    existing.add(did)
                    continue
                line = owner_line(did) or "D"
                result = self.add(decision_id=did, line=line, title=hit["title"],
                                  statement=None, statement_kind="pointer_only",
                                  affects=tuple(x for x in LINES if x != line),
                                  requires_ack_from=(),
                                  source=anchor,
                                  authority_pointers=[rel],
                                  registered_by="C（登记处摄取；原文在 source 锚点里，未抄正文）",
                                  extra={"ingest_scope": "执行单 P0-4：DR-001/002 + 增补裁定 8–31"
                                                         "（实际摄取到源文档现有最后一条，超出部分一并登记）",
                                         "ack_policy": ("历史条目：ack 纪律自登记处生效起算，"
                                                        "不追溯补 ack ⇒ requires_ack_from 为空。"
                                                        "新登记的决定才带 ack 义务（验收 3）。")})
                rows.append({"decision_id": did, "sha256_12": result["sha256_12"],
                             "path": Path(result["path"]).name, "source": anchor})
                existing.add(did)
        return {"ingested": rows, "n_ingested": len(rows), "skipped": skipped,
                "dry_run": dry_run, "at": _now_iso()}


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY), help="登记处根目录")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="摄取历史 markdown（pointer_only，不抄正文）")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--only", default="", help="逗号分隔的 decision_id 白名单")

    p = sub.add_parser("add", help="新增一条决定")
    p.add_argument("--id", dest="decision_id", default=None)
    p.add_argument("--line", required=True, choices=list(LINES))
    p.add_argument("--title", required=True)
    p.add_argument("--statement", default=None)
    p.add_argument("--affects", default="")
    p.add_argument("--requires-ack-from", default=None,
                   help="逗号分隔；给 `none` 表示显式不设 ack 义务")
    p.add_argument("--evidence", default="", help="逗号分隔 path[:why]")
    p.add_argument("--authority", default="", help="逗号分隔的判据单一来源指针")
    p.add_argument("--supersedes", default="")

    p = sub.add_parser("ack", help="追加一条 ack 事件")
    p.add_argument("--id", dest="target_id", required=True)
    p.add_argument("--line", required=True, choices=list(LINES))
    p.add_argument("--by", default=None)
    p.add_argument("--reason", default=None)
    p.add_argument("--evidence", default="")

    p = sub.add_parser("revoke", help="追加一条撤销事件（原条目文件不改）")
    p.add_argument("--id", dest="target_id", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--authority", default="")
    p.add_argument("--new-id", dest="new_id", default=None)
    p.add_argument("--kind", default="revoke", choices=("revoke", "supersede"))

    p = sub.add_parser("annotate", help="追加一条批注事件（不改状态）")
    p.add_argument("--id", dest="target_id", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--reason", required=True)

    p = sub.add_parser("show", help="按 id 或内容哈希取回一条决定")
    p.add_argument("--id", dest="decision_id", default=None)
    p.add_argument("--hash", dest="digest", default=None)

    p = sub.add_parser("list", help="列出台账")
    p.add_argument("--missing-acks", action="store_true")
    p.add_argument("--status", default=None, choices=("active", "retired", "superseded"))
    p.add_argument("--line", default=None, choices=list(LINES))

    sub.add_parser("verify", help="判据自检（能红）；exit 1 = 有红点")
    sub.add_parser("selfcheck", help="合成注册表上的双向变异自检")
    sub.add_parser("rebuild-index", help="重建派生索引")

    args = ap.parse_args(argv)
    reg = DecisionRegistry(Path(args.registry))

    def _evidence_list(spec: str) -> list[dict[str, Any]]:
        out = []
        for item in filter(None, (x.strip() for x in spec.split(","))):
            path, _, why = item.partition(":")
            full = Path(path) if Path(path).is_absolute() else ROOT / path
            out.append({"path": path, "sha256_12": _sha12_file(full),
                        "exists": full.exists(), "why": why or None})
        return out

    if args.cmd == "ingest":
        result = reg.ingest(dry_run=args.dry_run,
                            only=tuple(x for x in args.only.split(",") if x))
        _print_json({"n_ingested": result["n_ingested"], "dry_run": result["dry_run"],
                     "ingested": [r["decision_id"] for r in result["ingested"]],
                     "skipped": result["skipped"][:20], "n_skipped": len(result["skipped"])})
        if not args.dry_run:
            reg.rebuild_index()
        return 0

    if args.cmd == "add":
        result = reg.add(decision_id=args.decision_id, line=args.line, title=args.title,
                         statement=args.statement,
                         affects=tuple(x for x in args.affects.split(",") if x),
                         requires_ack_from=(() if (args.requires_ack_from or "").strip() == "none"
                                              else (tuple(x for x in args.requires_ack_from.split(",")
                                                          if x)
                                                    if args.requires_ack_from is not None else None)),
                         evidence=_evidence_list(args.evidence),
                         authority_pointers=tuple(x for x in args.authority.split(",") if x),
                         supersedes=tuple(x for x in args.supersedes.split(",") if x))
        _print_json({k: v for k, v in result.items() if k != "entry"})
        reg.rebuild_index()
        return 0

    if args.cmd in ("ack", "revoke", "annotate"):
        # `--kind` 只挂在 revoke 子命令上。字典字面量的**三个值会先全部求值**再取键，
        # 于是 ack / annotate 也会去读 args.kind ⇒ AttributeError（CLI 崩，而 API 路径不崩，
        # 所以只跑 API 的自检查不出来）。惰性取：没有 --kind 就用子命令名本身。
        kind = getattr(args, "kind", None) or args.cmd
        event = reg.append_event(
            kind, target_id=args.target_id,
            by=getattr(args, "by", None) or getattr(args, "line", None),
            line=getattr(args, "line", None), reason=getattr(args, "reason", None),
            evidence=_evidence_list(getattr(args, "evidence", "") or ""),
            new_decision_id=getattr(args, "new_id", None))
        _print_json({k: v for k, v in event.items() if k != "event"})
        reg.rebuild_index()
        return 0

    if args.cmd == "show":
        entries = reg.load_entries()
        events = reg.load_events()
        if args.digest:
            for key, record in entries.items():
                if key == "_unreadable":
                    continue
                for version in reg._iter_versions(record):
                    if version["sha256"].startswith(args.digest) or \
                            version["sha256_12"].startswith(args.digest):
                        _print_json({"found_by": "content_sha256", **version["entry"],
                                     "content_sha256": version["sha256"],
                                     "path": str(version["path"]),
                                     "tampered": version["tampered"],
                                     "status": reg.status(version["decision_id"], events),
                                     "acks": reg.acks(version["decision_id"], version["entry"],
                                                      events)})
                        return 0
            print(f"!! 没有条目的内容哈希以 {args.digest} 开头（改一个字节就取不回，这正是验收 1）")
            return 1
        record = entries.get(args.decision_id)
        if not record:
            print(f"!! 没有这条决定：{args.decision_id}（现有 {len(reg.known_ids())} 条）")
            return 1
        versions = list(reg._iter_versions(record))
        _print_json({"decision_id": args.decision_id, "n_versions": len(versions),
                     "versions": [{**v["entry"], "content_sha256": v["sha256"],
                                   "path": str(v["path"]), "tampered": v["tampered"]}
                                  for v in versions],
                     "status": reg.status(args.decision_id, events),
                     "acks": reg.acks(args.decision_id, versions[-1]["entry"], events),
                     "events": [e for e in events if e.get("target_id") == args.decision_id]})
        return 0

    if args.cmd == "list":
        index = reg.index()
        rows = index["decisions"]
        if args.status:
            rows = [r for r in rows if r["status"] == args.status]
        if args.line:
            rows = [r for r in rows if r["line"] == args.line]
        if args.missing_acks:
            rows = [r for r in rows if r["acks"]["missing_acks"]]
        for row in rows:
            miss = ",".join(row["acks"]["missing_acks"]) or "-"
            print(f"{row['decision_id']:<12} {row['status']:<11} line={row['line']} "
                  f"sha12={row['sha256_12']} ack={','.join(row['acks']['acked_by']) or '-'}"
                  f" missing={miss}  {str(row['title'])[:60]}")
        print(f"-- {len(rows)} 条（共 {index['n_decisions']} 条决定 / {index['n_versions']} 个版本 / "
              f"{index['n_events']} 个事件；按状态 {index['counts_by_status']}）")
        return 0

    if args.cmd == "verify":
        result = reg.verify()
        _print_json({k: v for k, v in result.items()})
        print(f"-- verify: {'PASS' if result['pass'] else 'RED'} "
              f"(red={len(result['red'])} warn={len(result['warn'])})")
        return 0 if result["pass"] else 1

    if args.cmd == "rebuild-index":
        index = reg.rebuild_index()
        _print_json({k: v for k, v in index.items() if k != "decisions"})
        return 0

    if args.cmd == "selfcheck":
        from scripts.c_selfcheck_decisions_registry import main as sc_main  # noqa: PLC0415
        return sc_main()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
