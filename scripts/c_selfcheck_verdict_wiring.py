#!/usr/bin/env python3
"""C 线自检：**P1-5 `physical_fact` 接线**（增补五 §9-C③ / 裁定 29.1 / D 派工单 P1-5）。

测的是三处接线本身，不测判据的分级逻辑（那是 `c_selfcheck_verdict_identity.py` 的活）：

1. `registry/verdict_identity.py::admit_as_physical_fact` —— 准入闸：
   **只吃 `physical_fact`**，且 `gate_build` 必须等于**调用时**的门禁现值；不符 ⇒ **拒收并回显理由**
   （不是 warn）。附带验「与 B §5 的交点」：门禁一升版（v1.6），先前准入的那条**必须**变成拒收。
2. `harness/ledger.py::ingest_runtime_result` —— **fail-closed**：不显式声明依据就不许入账；
   拒收时写 `verdict_refused` 事件留档但**不写任何帧/标签行**；重判是**追加**，不改写旧事件。
3. `registry/release_bundle.py` —— `DirectionScore` 自带身份**字段**（不是注释），
   缺身份 / 档位不对 / 构建不符 ⇒ `build_bundle` **拒收**（与「双向同 checkpoint」红线同级）。

判据单一来源（裁定 21）：本文件**不重述**任何阈值或分级规则，只断言「接线通了、且能红」。
门禁现值一律用**合成值**注入（`current_gate=` / `gate_current=`），保持 hermetic：
本自检不加载 B 的判据模块，因此 B 改判据不会让本自检的数字漂移。

合成数字与合成构建号**无物理意义**（ADR-C-007）。
产物只写 `runs/infra/c_verdict_wiring_selfcheck{,.json}`（C 自己的目录），不碰真账本、不碰 `registry/`。

用法：CUDA_VISIBLE_DEVICES="" /root/venvs/rlrobot/bin/python scripts/c_selfcheck_verdict_wiring.py
"""
from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.ledger import (  # noqa: E402
    EVENT_KINDS, FactLedger, VerdictAdmissionError, ingest_runtime_result)
from registry import release_bundle as rb  # noqa: E402
from registry import verdict_identity as vi  # noqa: E402

OUT_ROOT = ROOT / "runs" / "infra" / "c_verdict_wiring_selfcheck" / time.strftime("%Y%m%d_%H%M%S")
OUT_JSON = ROOT / "runs" / "infra" / "c_verdict_wiring_selfcheck.json"
SYNTHETIC_NOTE = {"physical_meaning": False,
                  "note": ("合成裁定身份 / 合成构建号 / 合成 success_rate，数字**无物理意义**"
                           "（ADR-C-007）。门禁现值由测试注入，不读上游真门禁。")}

# 合成的「门禁现值」与「升版后的门禁现值」（模拟 B 的 v1.6 落地会升 GATE_BUILD 那一刀）
GATE_NOW = {"gate_version": "vFIX.1", "gate_build": "fixfeed00001",
            "gate_spec_sha256": "fixspec00000001"}
GATE_NEXT = {"gate_version": "vFIX.2", "gate_build": "fixfeed00002",
             "gate_spec_sha256": "fixspec00000002"}

_VERDICT_DEFAULTS: dict[str, Any] = {
    "source_path": "runs/infra/synthetic/gate_synthetic_arm.json",
    "source_sha256": "syntheticverdictsha256",
    "arm": "synthetic_arm",
    "eval_file": "synthetic_eval.json",
    "eval_sha256": "syntheticevalsha256",
    "gate_version": GATE_NOW["gate_version"],
    "gate_build": GATE_NOW["gate_build"],
    "gate_spec_sha256": GATE_NOW["gate_spec_sha256"],
    "gate_spec_doc": "synthetic_spec.md",
    "measurement_valid": True,
    "measurement_validity_declared": True,
    "field_class": "complete",
    "missing_fields": (),
    "gate_pass": True,
    "gate_reason": "synthetic",
    "accounts": {name: 0.5 for name in vi.ACCOUNTS},
    "buckets": {name: 0.0 for name in vi.BUCKETS},
    "input_contract_status": "ok",
    "suspect_truncation_as_failure": False,
    "validity_class": "valid",
    "validity_reason": "synthetic",
    "arm_field_class": "complete",
    "validity_source": "synthetic",
    "blowup_threshold_source": "synthetic",
    "labels_reportable": True,
    "upstream_superseded_by": None,
    "arm_summary_sha256": "syntheticarmsummarysha",
    "arm_verdict": True,
    "is_current_build": True,
    "superseded": False,
    "superseded_by": None,
    "provenance": "synthetic",
    "usable_for": vi.USABLE_PHYSICAL_FACT,
    "reasons": ("synthetic_reason",),
}


def _verdict(**over: Any) -> vi.VerdictIdentity:
    """一条**合成**裁定身份（数字无物理意义）。默认是「最合格」的那一档，逐项劣化造反例。"""
    return vi.VerdictIdentity(**{**_VERDICT_DEFAULTS, **over})


def _ledger(name: str) -> FactLedger:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    return FactLedger(OUT_ROOT / f"{name}.db")


def _runtime_result(rid: str = "RW01", *, n: int = 2) -> Any:
    """用**真的** `RuntimeAdapter` 造一份运行时结果（不是桩对象）：接线自检要测真接口。"""
    from harness.contracts import DecisionRequest, QueueState
    from harness.runtime_adapter import RuntimeAdapter
    adapter = RuntimeAdapter(driver=lambda req, state, act: {
        "activated": True, "reward": 0.5, "phase": "approach", "grasp_verified": False})
    adapter.start(DecisionRequest(rid, 1, "lift", {"cube_pos": [0.0, 0.0, 0.0]},
                                  "mock", "v1", 0, 0, 10), QueueState())
    for _ in range(n):
        adapter.step([0.1, 0.2, 0.3])
    return adapter.finalize("success", reward=1.0)


def _components() -> list[rb.ComponentRef]:
    return [rb.inline_component(role, {"role": role, "synthetic": True}, version="vFIX")
            for role in rb.REQUIRED_ROLES]


def _directions(checkpoint_sha: str, protocol_sha: str,
                identity: dict[str, Any] | None = None) -> list[rb.DirectionScore]:
    ident = dict(FIXTURE_IDENTITY) if identity is None else dict(identity)
    return [rb.DirectionScore(goal_id=goal, passed=True, checkpoint_sha256=checkpoint_sha,
                              eval_protocol_sha256=protocol_sha, success_rate=0.5,
                              n_episodes=4, source="synthetic", **ident)
            for goal in rb.DEFAULT_DIRECTIONS]


FIXTURE_IDENTITY = {"gate_version": GATE_NOW["gate_version"], "gate_build": GATE_NOW["gate_build"],
                    "gate_spec_sha256": GATE_NOW["gate_spec_sha256"],
                    "verdict_sha256": "syntheticverdictsha256", "measurement_valid": True,
                    "usable_for": vi.USABLE_PHYSICAL_FACT, "provenance_kind": None,
                    "is_current_build": True, "superseded_by": None, "regraded_from": None}


def _bundle(**kwargs: Any) -> rb.ReleaseBundle:
    comps = _components()
    policy = next(c for c in comps if c.role == "policy")
    protocol = next(c for c in comps if c.role == "eval_protocol")
    return rb.build_bundle(comps, _directions(policy.sha256, protocol.sha256,
                                              kwargs.pop("identity", None)),
                           notes="c_verdict_wiring_selfcheck", created_ns=1_700_000_000, **kwargs)


def _kinds(led: FactLedger, episode_id: str) -> list[str]:
    return [row["kind"] for row in led.events(episode_id=episode_id)]


def _payload_of(led: FactLedger, episode_id: str, kind: str) -> dict[str, Any]:
    rows = [row for row in led.events(episode_id=episode_id) if row["kind"] == kind]
    return dict(rows[-1]["payload"]) if rows else {}


# ---------------- 1. 准入闸：只吃 physical_fact ----------------
def case_admission_only_physical_fact(checks: list) -> None:
    ok = vi.admit_as_physical_fact(_verdict(), current=GATE_NOW)
    checks.append(("physical_fact + 现构建 ⇒ 准入（判据非恒红）", ok["admitted"] is True
                   and ok["refusal_reasons"] == []))
    checks.append(("准入结论回显了完整身份与当时的门禁现值",
                   ok["identity"]["usable_for"] == vi.USABLE_PHYSICAL_FACT
                   and ok["gate_current"]["gate_build"] == GATE_NOW["gate_build"]))
    for grade in (vi.USABLE_STALE_BUILD, vi.USABLE_INVALID_MEASUREMENT, vi.USABLE_UNIDENTIFIED,
                  vi.USABLE_NOT_A_VERDICT):
        refused = vi.admit_as_physical_fact(_verdict(usable_for=grade), current=GATE_NOW)
        checks.append((f"{grade} ⇒ 拒收并回显理由（不是 warn）",
                       refused["admitted"] is False
                       and bool(refused["refusal_reasons"])
                       and grade in refused["refusal_reason"]))
    stale = vi.admit_as_physical_fact(
        _verdict(usable_for=vi.USABLE_STALE_BUILD, is_current_build=False,
                 gate_build="olderbuild0000", provenance_kind=vi.PROVENANCE_ORDINARY_STALE),
        current=GATE_NOW)
    checks.append(("拒收理由带上 provenance_kind 子标签（裁定 31.4）",
                   vi.PROVENANCE_ORDINARY_STALE in stale["refusal_reason"]))
    checks.append(("拒收时 verdict_reasons 原样带出（不吞掉裁定层给的理由）",
                   stale["verdict_reasons"] == ["synthetic_reason"]))


# ---------------- 2. build 轴：不符必须拒收，含 v1.6 那一刀 ----------------
def case_build_axis_rejects(checks: list) -> None:
    mismatch = vi.admit_as_physical_fact(_verdict(gate_build="olderbuild0000",
                                                 is_current_build=False), current=GATE_NOW)
    checks.append(("gate_build 与门禁现值不符 ⇒ 拒收（不是 warn）",
                   mismatch["admitted"] is False
                   and "≠ 门禁现值" in mismatch["refusal_reason"]))
    checks.append(("拒收结论里**没有** warn 这种软处置字段",
                   "warn" not in mismatch and "warning" not in mismatch))
    contradicted = vi.admit_as_physical_fact(_verdict(is_current_build=False), current=GATE_NOW)
    checks.append(("身份自相矛盾（build 等于现值却自称 is_current_build=False）⇒ 拒收",
                   contradicted["admitted"] is False
                   and "自相矛盾" in contradicted["refusal_reason"]))
    superseded = vi.admit_as_physical_fact(_verdict(superseded_by="synthetic_newer.json",
                                                   superseded=True), current=GATE_NOW)
    checks.append(("已被取代的裁定 ⇒ 拒收", superseded["admitted"] is False
                   and "superseded_by" in superseded["refusal_reason"]))
    missing = vi.admit_as_physical_fact(_verdict(gate_build=None, usable_for=vi.USABLE_UNIDENTIFIED,
                                                is_current_build=False), current=GATE_NOW)
    checks.append(("gate_build 缺失 ⇒ 拒收（连出自哪一版判据都说不清）",
                   missing["admitted"] is False and "gate_build 缺失" in missing["refusal_reason"]))

    # 「与 B §5 的交点」：门禁升版那一刀必须落得下来 —— 同一条裁定，现值一变就从准入变拒收。
    before = vi.admit_as_physical_fact(_verdict(), current=GATE_NOW)
    after = vi.admit_as_physical_fact(_verdict(), current=GATE_NEXT)
    checks.append(("门禁升版（模拟 v1.6）⇒ 先前准入的同一条裁定变成拒收（48→0 是正确行为）",
                   before["admitted"] is True and after["admitted"] is False
                   and GATE_NEXT["gate_build"] in after["refusal_reason"]))
    checks.append(("升版拒收的理由点名了两个构建号（可对表，不是含糊的『不符』）",
                   GATE_NOW["gate_build"] in after["refusal_reason"]
                   and GATE_NEXT["gate_build"] in after["refusal_reason"]))
    checks.append(("准入规则原文里预先写明了这个后果（不靠人记）",
                   "48 → 0" in vi.ADMISSION_RULE and "不是回归红点" in vi.ADMISSION_RULE))


# ---------------- 3. 身份同源同义（P1-6 的硬要求） ----------------
def case_same_source_identity(checks: list) -> None:
    record = _verdict(provenance_kind=vi.PROVENANCE_FROZEN_PREREG_ANCHOR)
    ident = vi.direction_identity(record)
    artifact = vi.artifact_identity(record)
    checks.append(("direction_identity 覆盖全部约定身份字段",
                   set(vi.DIRECTION_IDENTITY_FIELDS) <= set(ident)))
    shared = (("gate_build", "gate_build"), ("is_current_build", "is_current_build"),
              ("usable_for", "usable_for"), ("verdict_sha256", "source_sha256"),
              ("gate_version", "gate_version"), ("measurement_valid", "measurement_valid"))
    checks.append(("与 artifact_identity **同源同义**（三字段逐值相同，不各写一套）",
                   all(ident[a] == artifact[b] for a, b in shared)))
    moved = vi.direction_identity(_verdict(gate_build="anotherbuild000"))
    checks.append(("身份取自记录、不是常量：改记录的 gate_build ⇒ 身份跟着变",
                   moved["gate_build"] == "anotherbuild000"
                   and moved["gate_build"] != ident["gate_build"]))
    checks.append(("provenance_kind / regraded_from 也带进身份（子标签不丢）",
                   ident["provenance_kind"] == vi.PROVENANCE_FROZEN_PREREG_ANCHOR
                   and vi.direction_identity(_verdict(regraded_from=vi.USABLE_PENDING_IMPL)
                                             )["regraded_from"] == vi.USABLE_PENDING_IMPL))
    as_dict = vi.direction_identity({"gate_build": "dictbuild0000",
                                     "usable_for": vi.USABLE_PHYSICAL_FACT,
                                     "source_sha256": "dictsha", "is_current_build": True})
    checks.append(("等价 dict 也能读（账本侧不必 import 裁定层的类型）",
                   as_dict["gate_build"] == "dictbuild0000"
                   and as_dict["verdict_sha256"] == "dictsha"))


# ---------------- 4. 账本：fail-closed ----------------
def case_ledger_fail_closed(checks: list) -> None:
    result = _runtime_result("RW10")
    with _ledger("fail_closed") as led:
        try:
            ingest_runtime_result(led, result, episode_id="epFC", goal_id="lift", source="mock")
            refused = False
        except VerdictAdmissionError:
            refused = True
        stats = led.stats()
        checks.append(("不声明依据 ⇒ 拒收（fail-closed，抛 VerdictAdmissionError）", refused))
        checks.append(("拒收时**一行都没写**（不是先写再撤）",
                       stats["frame_fact"] == 0 and stats["schedule_event"] == 0
                       and stats["label_record"] == 0))
    with _ledger("observation_only") as led:
        counts = ingest_runtime_result(led, _runtime_result("RW11"), episode_id="epOO",
                                       goal_id="lift", source="mock", observation_only=True)
        checks.append(("显式声明 observation_only ⇒ 放行，并记一条 verdict_identity_absent",
                       counts["verdict_identity_absent"] == 1
                       and "verdict_identity_absent" in _kinds(led, "epOO")
                       and counts["frames"] > 0))
        checks.append(("那条事件写明「没有 gate_build ⇒ 不得翻成 DirectionScore」",
                       "gate_build" in json.dumps(_payload_of(led, "epOO",
                                                              "verdict_identity_absent"),
                                                  ensure_ascii=False)))
    checks.append(("三个新事件种类都在账本的封闭词表里（不是绕过校验塞进去的）",
                   {"verdict_admitted", "verdict_refused",
                    "verdict_identity_absent"} <= set(EVENT_KINDS)))


# ---------------- 5. 账本：拒收留档但不进事实表 ----------------
def case_ledger_refusal_archived(checks: list) -> None:
    stale = _verdict(usable_for=vi.USABLE_STALE_BUILD, is_current_build=False,
                     gate_build="olderbuild0000", provenance_kind=vi.PROVENANCE_ORDINARY_STALE)
    with _ledger("refusal_event") as led:
        counts = ingest_runtime_result(led, _runtime_result("RW20"), episode_id="epRE",
                                       goal_id="lift", source="mock", verdict=stale,
                                       current_gate=GATE_NOW, on_refusal="event")
        stats = led.stats()
        checks.append(("非 physical_fact + on_refusal=event ⇒ 留档一条 verdict_refused",
                       counts["verdict_refused"] == 1 and "verdict_refused" in _kinds(led, "epRE")))
        checks.append(("留档但**不进事实表**（帧 0 / 标签 0）",
                       stats["frame_fact"] == 0 and stats["label_record"] == 0
                       and counts["frames"] == 0 and counts["labels"] == 0))
        payload = _payload_of(led, "epRE", "verdict_refused")
        checks.append(("拒收事件自带身份 + 理由 + 当时的门禁现值（可查，不靠人记）",
                       payload["identity"]["usable_for"] == vi.USABLE_STALE_BUILD
                       and payload["identity"]["gate_build"] == "olderbuild0000"
                       and bool(payload["refusal_reasons"])
                       and payload["gate_current"]["gate_build"] == GATE_NOW["gate_build"]
                       and payload["frames_written"] is False))
    with _ledger("refusal_raise") as led:
        try:
            ingest_runtime_result(led, _runtime_result("RW21"), episode_id="epRR",
                                  goal_id="lift", source="mock", verdict=stale,
                                  current_gate=GATE_NOW, on_refusal="raise")
            raised = False
        except VerdictAdmissionError as exc:
            raised = "拒收" in str(exc) and "不是 warn" in str(exc)
        checks.append(("on_refusal=raise ⇒ 抛错，且错误文本明写「拒收（不是 warn）」", raised))
        checks.append(("抛错之前**已经**写下留档事件（拒收可追溯）",
                       "verdict_refused" in _kinds(led, "epRR")
                       and led.stats()["frame_fact"] == 0))
    with _ledger("admitted") as led:
        counts = ingest_runtime_result(led, _runtime_result("RW22"), episode_id="epAD",
                                       goal_id="lift", source="mock", verdict=_verdict(),
                                       current_gate=GATE_NOW)
        checks.append(("physical_fact + 现构建 ⇒ 准入，并真的写下帧与标签（判据非恒红）",
                       counts["verdict_admitted"] == 1 and counts["frames"] > 0
                       and counts["labels"] > 0 and "verdict_admitted" in _kinds(led, "epAD")))
        checks.append(("准入事件回显身份与门禁现值",
                       _payload_of(led, "epAD", "verdict_admitted")["identity"]["gate_build"]
                       == GATE_NOW["gate_build"]))


# ---------------- 6. 账本：重判是追加，不改写 ----------------
def case_rejudgment_append_only(checks: list) -> None:
    stale = _verdict(usable_for=vi.USABLE_STALE_BUILD, is_current_build=False,
                     gate_build="olderbuild0000")
    with _ledger("rejudgment") as led:
        ingest_runtime_result(led, _runtime_result("RW30"), episode_id="epRJ", goal_id="lift",
                              source="mock", verdict=stale, current_gate=GATE_NOW,
                              on_refusal="event")
        before_rows = [(row.seq, copy.deepcopy(dict(row["payload"])))
                       for row in led.events(episode_id="epRJ")]
        before_kinds = [row["kind"] for row in led.events(episode_id="epRJ")]
        ingest_runtime_result(led, _runtime_result("RW31"), episode_id="epRJ", goal_id="lift",
                              source="mock", verdict=_verdict(), current_gate=GATE_NOW)
        after_rows = led.events(episode_id="epRJ")
        after_kinds = [row["kind"] for row in after_rows]
        # append-only 的精确形状：**旧事件序列是新事件序列的前缀**（一条不少、一条不改、顺序不动）。
        # 只数「多了几条」不够 —— 那抓不到「改写中间一条」；前缀判定能抓到。
        checks.append(("重判 = **追加**：旧事件序列是新序列的前缀（没删、没改写、没重排）",
                       after_kinds[:len(before_kinds)] == before_kinds
                       and len(after_kinds) > len(before_kinds)))
        checks.append(("追加的部分里带着新的 verdict_admitted（重判结论入账）",
                       "verdict_refused" in before_kinds
                       and "verdict_admitted" in after_kinds[len(before_kinds):]))
        kept = {row.seq: dict(row["payload"]) for row in after_rows}
        checks.append(("旧事件的 payload **逐键不变**（append-only，不改写历史）",
                       all(kept[seq] == payload for seq, payload in before_rows)))
        checks.append(("旧 seq 一个都没消失，且 seq 单调递增 ⇒ 时序可读",
                       set(seq for seq, _ in before_rows) <= set(kept)
                       and [row.seq for row in after_rows]
                       == sorted(row.seq for row in after_rows)))
        first_kind = next(row["kind"] for row in after_rows if row["kind"].startswith("verdict_"))
        last_kind = [row["kind"] for row in after_rows if row["kind"].startswith("verdict_")][-1]
        checks.append(("同一局里先拒收后准入，两条都在账上（不覆盖、不移动、不删除）",
                       first_kind == "verdict_refused" and last_kind == "verdict_admitted"))


# ---------------- 7. 发布包：身份红线 ----------------
def case_bundle_identity_red_lines(checks: list) -> None:
    good = _bundle(gate_current=GATE_NOW)
    checks.append(("身份齐备且构建相符 ⇒ 正常出包（判据非恒红）",
                   isinstance(good, rb.ReleaseBundle)
                   and good.directions[0].usable_for == vi.USABLE_PHYSICAL_FACT))
    checks.append(("身份字段真的进了发布包 manifest（是字段，不是注释）",
                   all(k in rb.as_dict(good.directions[0])
                       for k in ("gate_build", "usable_for", "is_current_build",
                                 "verdict_sha256"))))
    for label, identity in (("缺身份", {}),
                             ("缺 verdict_sha256", {**FIXTURE_IDENTITY, "verdict_sha256": None}),
                             ("档位不对（stale_build_evidence）",
                              {**FIXTURE_IDENTITY, "usable_for": vi.USABLE_STALE_BUILD}),
                             ("自称非现构建", {**FIXTURE_IDENTITY, "is_current_build": False})):
        try:
            _bundle(identity=identity)
            refused = False
        except rb.VerdictIdentityViolation:
            refused = True
        checks.append((f"{label} ⇒ build_bundle 拒收（VerdictIdentityViolation）", refused))
    try:
        _bundle(gate_current=GATE_NEXT)
        mismatch_refused = False
    except rb.VerdictIdentityViolation as exc:
        mismatch_refused = "拒收，不是 warn" in str(exc) and GATE_NEXT["gate_build"] in str(exc)
    checks.append(("构建与门禁现值不符 ⇒ 拒收，且错误文本明写「不是 warn」+ 点名现值",
                   mismatch_refused))
    try:
        _bundle(gate_current=GATE_NEXT, require_verdict_identity=False)
        still_refused = False
    except rb.VerdictIdentityViolation:
        still_refused = True
    checks.append(("关掉 require_verdict_identity **也**拦得住构建不符（两条红线互相独立）",
                   still_refused))
    lax = _bundle(identity={}, require_verdict_identity=False)
    checks.append(("显式关掉身份要求且不给 gate_current ⇒ 放行（逃生口是显式的，不是默认）",
                   isinstance(lax, rb.ReleaseBundle)))
    checks.append(("身份红线与「双向同 checkpoint」同级：都是 BundleError 家族",
                   issubclass(rb.VerdictIdentityViolation, rb.BundleError)))


CASES = (case_admission_only_physical_fact, case_build_axis_rejects,
         case_same_source_identity, case_ledger_fail_closed,
         case_ledger_refusal_archived, case_rejudgment_append_only,
         case_bundle_identity_red_lines)


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, Any]] = []
    for case in CASES:
        print(f"--- {case.__name__} ---", flush=True)
        start = len(checks)
        case(checks)
        for name, ok in checks[start:]:
            tag = "PASS" if ok is True else "FAIL"
            print(f"[{tag}] {name}" + ("" if ok is True else f" -> {ok}"), flush=True)
    failed = [name for name, ok in checks if ok is not True]
    n_pass = len(checks) - len(failed)
    OUT_JSON.write_text(json.dumps({
        "cases": [c.__name__ for c in CASES],
        "checks": [{"name": name, "ok": bool(ok is True)} for name, ok in checks],
        "pass": not failed, "n_checks": len(checks), "n_pass": n_pass,
        "n_failed": len(failed), "failed": failed,
        "c_synthetic": SYNTHETIC_NOTE,
        "hermetic": ("门禁现值由测试注入（GATE_NOW / GATE_NEXT），不加载 B 的判据模块；"
                     "B 改判据不会让本自检漂移。"),
        "artifact_dir": str(OUT_ROOT.relative_to(ROOT)),
        "wiring_under_test": {
            "admission_gate": "registry/verdict_identity.py::admit_as_physical_fact",
            "ledger": "harness/ledger.py::ingest_runtime_result",
            "bundle": "registry/release_bundle.py::build_bundle/_require_verdict_identity",
            "identity_single_source": "registry/verdict_identity.py::artifact_identity",
        },
        "impl_sha256": {rel: vi.content_sha256(ROOT / rel) for rel in
                        ("registry/verdict_identity.py", "harness/ledger.py",
                         "registry/release_bundle.py", "scripts/c_selfcheck_verdict_wiring.py")},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("--- 全部通过 ---" if not failed else f"--- 失败 {len(failed)} 条 ---")
    for name in failed:
        print(f"  FAIL {name}")
    print(f"结果: {n_pass}/{len(checks)} PASS -> {OUT_JSON.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
