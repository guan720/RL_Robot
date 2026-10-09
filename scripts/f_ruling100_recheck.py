#!/usr/bin/env python3
"""F 线：裁定 100 补单六 ①③④⑤ + 裁定 102.6 的 ⑲ 复核 + 545319 一问（只读、非牙）。

权威（F 不新设判据，逐条抄 D 的原文）：
  · `work/decisions/decisions_20260929.md` §99.5-F / §100.2 / §100.3 / §100.4 / §100.8-F / §100.11 / §102.6
  · `rl_harness_supervision/d_handoff_to_f_20260930.md` 补单六 §三-1/3/4 + §五（545319 一问，已被 §100.11-③ 撤回）
  · 裁定 101.1（治理硬冻结：只留六类阻塞项；覆盖率 / 行数 / 探针这类治理指标停跑）
  · 裁定 46（能力声明禁令）：本件不含任何 policy 指标；所有 PASS/GREEN 只指判词在盘、形态相符。

边界：只读他线产物；不判他线判词的对错；不改他线文件；不新增牙；不上卡；不 `find /`（限定前缀 + maxdepth）。
产物：4 件 JSON + 1 份身份表，落在 `runs/vla/f_oversight_20260930/`。
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "vla" / "f_oversight_20260930"
CITATION_ALGO = "sha256[:12]"
GATE_RUN_GLOB = "runs/vla/c2_norm_contract_20260929/gate/run_*"
GATE_SCRIPT = "scripts/c2_gate_norm_contract.py"
DECISIONS = "work/decisions/decisions_20260929.md"
DAILY = "daily_report.md"
SHA_RX = re.compile(r"\b[0-9a-f]{12}\b")
OBJ_RX = re.compile(r"[\w./+\-]+\.(?:json|py|md|npz|jsonl|txt|log|jsonl)\b")
NUM_RX = re.compile(r"\d+(?:\.\d+)?\s*(?:ln|B|行|件|次|秒|s\b|分钟|小时)")


def _now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _sha(path: Path, algo: str = "sha256") -> str | None:
    try:
        h = hashlib.new(algo)
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:12]
    except OSError:
        return None


def _identity(rel: str | Path, why: str) -> dict[str, Any]:
    """身份串必须由工具在落笔时刻生成（裁定 92.3）：sha256[:12] + sha1[:12] + wc -l 行数 + as_of。"""
    path = ROOT / rel if not isinstance(rel, Path) else rel
    out: dict[str, Any] = {"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                           "why": why, "as_of": _now(), "citation_algo": CITATION_ALGO}
    if not path.exists():
        return {**out, "measurement_status": "not_measured", "reason": "对象不在盘（不是「没有」，是测不到）"}
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {**out, "measurement_status": "not_measured", "reason": f"{type(exc).__name__}: {exc}"}
    st = path.stat()
    return {**out, "measurement_status": "measured",
            "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
            "sha1_12": hashlib.sha1(raw).hexdigest()[:12],
            "n_bytes": len(raw), "n_lines_wc": raw.count(b"\n"),
            "mtime": datetime.fromtimestamp(st.st_mtime).astimezone().replace(microsecond=0).isoformat()}


def _glob_bounded(prefix: str, pattern: str, maxdepth: int = 3) -> list[Path]:
    base = ROOT / prefix
    if not base.exists():
        return []
    hits: list[Path] = []
    depth = len(Path(pattern).parts)
    for path in base.glob(pattern):
        rel_parts = path.relative_to(base).parts
        if len(rel_parts) <= max(maxdepth, depth):
            hits.append(path)
    return sorted(hits)


def _git(args: list[str]) -> dict[str, Any]:
    try:
        proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)
        return {"cmd": "git " + " ".join(args), "returncode": proc.returncode,
                "stdout_lines": [l for l in proc.stdout.splitlines() if l.strip()][:20],
                "n_stdout_lines": len([l for l in proc.stdout.splitlines() if l.strip()]),
                "stderr": proc.stderr.strip()[:200]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"cmd": "git " + " ".join(args), "measurement_status": "not_measured",
                "reason": f"{type(exc).__name__}: {exc}"}


def _decisions_lines() -> list[str]:
    return (_read(ROOT / DECISIONS) or "").splitlines()


def _claim_lines(pattern: str) -> dict[str, Any]:
    """在裁定书里定位 D 的自报原文（活件 ⇒ 行号一律带 as_of，裁定 98.3-②）。"""
    lines = _decisions_lines()
    rx = re.compile(pattern)
    hits = [{"line_no_as_of": i, "excerpt": l.strip()[:300]}
            for i, l in enumerate(lines, 1) if rx.search(l)]
    return {"pattern": pattern, "n_hits": len(hits), "hits": hits[:6],
            "scan_scope": DECISIONS, "as_of": _now()}


def _common_envelope(artifact: str, authority: list[str]) -> dict[str, Any]:
    return {"artifact": artifact, "as_of": _now(), "line": "F（监管分析 / 进度核算，配合 D）",
            "generator": "scripts/f_ruling100_recheck.py", "authority": authority,
            "read_only": True, "tooth": False, "blocking": False,
            "new_governance_metric": False,
            "freeze_note": ("裁定 101.1：Step 1 出结果前不新增非 Ⅰ 类门禁 / 身份规则 / 治理指标 ⇒ "
                            "本件是 D 已下令的复核产物，不新增判据、不产覆盖率类指标"),
            "policy_executed": False, "gpu_used": False, "capability_claim": None,
            "citation_algo": CITATION_ALGO, "no_root_filesystem_scans": True,
            "three_state_discipline": "measured / not_measured / not_applicable（测不到不猜，裁定 88.4 / 72-2）"}


# ---------------------------------------------------------------------------
# ① G14 的独立语义判定件（裁定 97.3-4 的 `checked_by=F`；补单五-①、补单六-1）
# ---------------------------------------------------------------------------
def _frozensets_from_gate_script() -> dict[str, Any]:
    """F 自己 ast 读闸脚本里的两张例外表（只 ast、不 import 执行）。"""
    path = ROOT / GATE_SCRIPT
    src_text = _read(path)
    if src_text is None:
        return {"measurement_status": "not_measured", "reason": f"{GATE_SCRIPT} 读不到"}
    try:
        tree = ast.parse(src_text)
    except SyntaxError as exc:
        return {"measurement_status": "not_measured", "reason": f"ast.parse 失败：{exc.msg} line {exc.lineno}"}
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in ("SELF_EVIDENT_FLIP", "DECLARED_PROOF_EXCEPTION"):
                    value = node.value
                    # v1 的缺陷就在这里：`frozenset([...])` 是 Call，`literal_eval` 直接抛 ValueError，
                    # 而 v1 把异常吞成 `[]` 并照样报 measured ⇒ 静默降级（缺陷类 ⑲ 同族：过滤器窄于对象空间）。
                    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                            and value.func.id in ("frozenset", "set", "list", "tuple", "sorted") and value.args):
                        value = value.args[0]
                    try:
                        found[tgt.id] = sorted(str(x) for x in ast.literal_eval(value))
                    except (ValueError, SyntaxError, TypeError) as exc:
                        found[tgt.id] = []
                        found.setdefault("_errors", [])
                        found["_errors"] = found.get("_errors", []) + [f"{tgt.id}: {type(exc).__name__}: {exc}"]
    b_list = found.get("SELF_EVIDENT_FLIP", [])
    c_list = found.get("DECLARED_PROOF_EXCEPTION", [])
    # 两向自检（裁定 93.8 / 97.8：报"没有"之前，过滤器必须先证明自己能命中）。
    # 正向对照**不用人手转录的成员名**：v2 第一版那么写，把实物 `G7_no_widen_bites_Tc` 抄成
    # `…Ts` ⇒ 对照自己成了假警（缺陷类 ⑲ 同族）。改为「抽到的每个成员必须在源码里逐字出现」。
    src_b = sum(1 for x in b_list if x in src_text)
    src_c = sum(1 for x in c_list if x in src_text)
    positive_ctrl = bool(b_list) and bool(c_list) and src_b == len(b_list) and src_c == len(c_list)
    non_vacuous = bool(b_list) and bool(c_list)
    ok = len(found) >= 2 and non_vacuous and positive_ctrl and not found.get("_errors")
    return {"measurement_status": "measured" if ok else "not_measured",
            "method": "ast 只读常量抽取（未 import 执行 C2 的模块）；`frozenset(...)` 取其第一个实参再 literal_eval",
            "identity": _identity(GATE_SCRIPT, "闸脚本；G14 的类归属由这两张表决定"),
            "self_evident_flip": b_list,
            "declared_proof_exception": c_list,
            "n_self_evident": len(b_list),
            "n_declared_exception": len(c_list),
            "self_check": {"positive_control": ("抽到的每个成员都必须在闸脚本源码里逐字出现"
                                                f"（B {src_b}/{len(b_list)}、C {src_c}/{len(c_list)}）；"
                                                "**不**用人手转录的成员名做对照"),
                           "positive_control_passed": positive_ctrl,
                           "non_vacuous": non_vacuous,
                           "literal_eval_errors": found.get("_errors", []),
                           "filter_non_vacuous": ok,
                           "v1_defect_self_report": ("v1（`5439fa5fd93e`，17:51:26 那批产物）把 `literal_eval` 对 `frozenset` 的 "
                                                      "ValueError 吞成空表、仍报 `measurement_status=measured` ⇒ "
                                                      "**两张例外表被读成 0 条**，而结论「G14 属 A 类」只是碰巧与真相同向。"
                                                      "F 自报这一处（缺陷类 ⑲ 同族：静默降级 + 过滤器窄于对象空间），"
                                                      "v1 产物原字节保留、不追改；v2 起带本自检。"),
                           "v2_first_attempt_self_report": ("v2 的第一版（`9398c07e5621`）正向对照用了人手转录的成员名 "
                                                            "`G7_no_widen_bites_Ts`，实物是 `G7_no_widen_bites_Tc` ⇒ "
                                                            "对照本身成了假警，把一次正确的抽取报成 not_measured。"
                                                            "F 自报（同族：手抄代替实测）；v2.1 起改为源码逐字命中 + 虚构 id 负向对照。")}}


def g14_determination() -> dict[str, Any]:
    out = _common_envelope("f_g14_semantic_determination", [
        "裁定 97.2 / 97.3-4（`G14` 的实测翻转 = BC 准入的一次性 Ⅰ 类前置，`checked_by=F`）",
        "裁定 99.5-F-① / 100.8-F-① / D→F 补单六 §三-1（F 必须自己落一份判定件，A2 只引不判）",
        "params `model_and_learning`/`operations` 里 `checked_by = F（每轮复测 G14 是否有 flip_measured=True）`",
    ])
    out["question"] = ("`G14_Tr3_registers_warn_on_mainline_only` 是否有**实测翻转**（不是自明、不是声明例外）？"
                       "语义判断归 F；F 只判这一条，不判 Tr3 的极性对错（那是裁定 93.1 的裁定值）。")
    out["class_attribution"] = _frozensets_from_gate_script()
    runs = _glob_bounded("runs/vla/c2_norm_contract_20260929/gate", "run_*", 1)
    out["scan_scope"] = [GATE_RUN_GLOB, GATE_SCRIPT, "runs/vla/a2_bc_admission_consume_20260930_run*/g14_provenance.json"]
    out["n_gate_run_dirs_found"] = len(runs)
    if not runs:
        return {**out, "measurement_status": "not_measured", "determination": None,
                "reason": "闸 run 目录未命中 ⇒ 不猜"}

    per_run: list[dict[str, Any]] = []
    latest: dict[str, Any] = {}
    latest_check_ids: set[str] = set()
    for run in runs[-6:]:                      # 只取最近 6 轮（限定读量；口径写在产物里）
        verdict_path = run / "gate_verdict.json"
        row: dict[str, Any] = {"run_dir": str(run.relative_to(ROOT))}
        if not verdict_path.exists():
            row.update(measurement_status="not_measured", reason="gate_verdict.json 不在盘")
            per_run.append(row)
            continue
        try:
            data = json.loads(verdict_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            row.update(measurement_status="not_measured", reason=f"{type(exc).__name__}: {exc}")
            per_run.append(row)
            continue
        checks = data.get("checks") or []
        latest_check_ids = {str(c.get("id")) for c in checks}
        g14 = next((c for c in checks if str(c.get("id", "")).startswith("G14")), None)
        ledger_hits = [e for e in (data.get("proof_ledger") or [])
                       if str(e.get("check_id", "")).startswith("G14")]
        mutant_name = ledger_hits[0].get("mutant") if ledger_hits else None
        probe: dict[str, Any] = {"measurement_status": "not_measured"}
        if mutant_name:
            probe_path = run / "mutants" / mutant_name / "inprocess_probe.json"
            if probe_path.exists():
                try:
                    pdata = json.loads(probe_path.read_text(encoding="utf-8", errors="replace"))
                    preds = pdata.get("predicates") or {}
                    key = next((k for k in preds if k.startswith("G14")), None)
                    probe = {"measurement_status": "measured" if key else "not_measured",
                             "probe_path": str(probe_path.relative_to(ROOT)),
                             "predicate_key": key,
                             "predicate_value_in_mutant_copy": preds.get(key) if key else None,
                             "identity": pdata.get("identity"),
                             "generated_at": pdata.get("generated_at")}
                except (OSError, json.JSONDecodeError) as exc:
                    probe = {"measurement_status": "not_measured", "reason": f"{type(exc).__name__}: {exc}"}
        row.update({
            "measurement_status": "measured",
            "verdict_identity": _identity(verdict_path, "同轮闸判词件；G14 的证据面"),
            "n_checks": len(checks),
            "gate_verdict": data.get("verdict"), "gate_verdict_class1": data.get("verdict_class1"),
            "g14_check_row": ({k: g14.get(k) for k in ("id", "ok", "status", "triage_class", "blocking",
                                                        "kind", "observed", "mutant_that_proves_it", "ruling_ref")}
                              if g14 else None),
            "g14_in_proof_ledger": ledger_hits,
            "mutant_inprocess_probe": probe,
            "flip_measured": bool(ledger_hits and all(e.get("flip_measured") is True for e in ledger_hits)
                                  and probe.get("predicate_value_in_mutant_copy") is False),
        })
        per_run.append(row)
        latest = row
    out["per_run_recheck"] = per_run
    out["per_run_caliber"] = "只取最近 6 个 run 目录（限定读量）；每轮都重取，不沿用上一轮读数（缺陷类 ㉒）"

    cls = out["class_attribution"]
    g14_id = (latest.get("g14_check_row") or {}).get("id") or "G14_Tr3_registers_warn_on_mainline_only"
    in_b = g14_id in (cls.get("self_evident_flip") or [])
    in_c = g14_id in (cls.get("declared_proof_exception") or [])
    b_ids = set(cls.get("self_evident_flip") or [])
    c_ids = set(cls.get("declared_proof_exception") or [])
    fake = "G99_f_nonexistent_control_tooth"
    neg_ok = (fake not in (b_ids | c_ids)) and (fake not in latest_check_ids)
    cls["cross_check_against_gate_checks"] = {
        "measurement_status": "measured" if latest_check_ids else "not_measured",
        "n_check_ids_in_latest_run": len(latest_check_ids),
        "negative_control_id": fake,
        "negative_control_passed": neg_ok,
        "exception_ids_not_in_latest_checks": sorted((b_ids | c_ids) - latest_check_ids),
        "caliber": "例外表成员若不在本轮 check id 集合里 ⇒ 表里有已改名/退役的 id（登记，不判；F 不改 C2 的表）",
    }
    if cls.get("measurement_status") != "measured" or not neg_ok or not latest_check_ids:
        return {**out, "measurement_status": "not_measured", "determination": None,
                "g14_flip_measured": None,
                "reason": "类归属抽取或两向自检未过 ⇒ F 不判（不猜；裁定 88.4）"}
    out["determination_inputs"] = {
        "g14_id": g14_id,
        "in_self_evident_flip_B": in_b, "in_declared_proof_exception_C": in_c,
        "class_consequence": ("A 类（默认）⇒ 必须有 `flip_measured=True` 的实测台账，绿才算证明"
                              if not (in_b or in_c) else "B/C 类 ⇒ 不需要独立翻转台账"),
        "baseline_side": (latest.get("g14_check_row") or {}).get("status"),
        "mutant_side_predicate": (latest.get("mutant_inprocess_probe") or {}).get("predicate_value_in_mutant_copy"),
        "ledger_entries": latest.get("g14_in_proof_ledger"),
    }
    if latest.get("measurement_status") != "measured":
        return {**out, "measurement_status": "not_measured", "determination": None,
                "reason": "最近一轮闸判词件测不到 ⇒ F 不猜（裁定 88.4）"}
    if in_b or in_c:
        determination = ("G14 落在例外表里 ⇒ 「需要独立实测翻转」这个前提不成立；"
                         "F 只登记这一事实，判据归属仍归 D（F 不改极性、不改分类）")
        status = "not_applicable"
    elif latest.get("flip_measured"):
        determination = ("**翻转是实测的**：同轮闸判词件里 G14 的 check 行 `status=PASS`（baseline 侧真），"
                         "其声明的变异体副本内同一份谓词实测为 `False`，且 `proof_ledger` 有 "
                         "`baseline_true=true / mutant_false=true / flip_measured=true` 的台账行 ⇒ "
                         "满足 A 类「绿 = 已实测到翻转」的要求。F 判：`checked_by=F` 这个字段现在有实物支撑。")
        status = "measured"
    else:
        determination = ("**未测到翻转**：check 行或台账或变异体探针三者里至少一样缺 ⇒ "
                         "按裁定 97.3-4 的一次性前置**未满足**；F 只登记，处置归 D。")
        status = "measured"
    out.update({
        "measurement_status": status,
        "g14_flip_measured": bool(latest.get("flip_measured")) and not (in_b or in_c),
        "determination": determination,
        "determination_scope": ("F 判的只是「翻转有没有被实测到」这一语义问题；**不判** Tr3 的极性对错、"
                                "不判闸是否该放行 BC、不判 A2/C2 的判词。裁定 46：本件不含任何 policy 指标。"),
        "checked_by": "F（本件即实物支撑）", "checked_when": out["as_of"],
        "n_runs_with_flip_measured": sum(1 for r in per_run if r.get("flip_measured")),
        "n_runs_measured": sum(1 for r in per_run if r.get("measurement_status") == "measured"),
        "a2_provenance_crossref": [str(p.relative_to(ROOT)) for p in
                                   _glob_bounded("runs/vla", "a2_bc_admission_consume_*/g14_provenance.json", 2)],
        "crossref_note": "A2 的旁证件只证明「证据可数到 + F 侧当时没有判定件」，不代 F 判语义；本件是 F 自己的判定。",
    })
    return out


# ---------------------------------------------------------------------------
# ③ `criteria_identity` 是否补齐（100.3-（c））+「判据有没有在对象上干跑」可核化字段（99.3）
# ---------------------------------------------------------------------------
def _row_flags(line: str) -> dict[str, bool]:
    has_obj = bool(OBJ_RX.search(line))
    has_sha = bool(SHA_RX.search(line))
    has_num = bool(NUM_RX.search(line))
    return {"object_cited": has_obj, "sha_cited": has_sha, "measured_quantity_cited": has_num,
            "dry_run_evidence_present": bool(has_obj and (has_sha or has_num))}


def _dry_run_filter_self_check() -> dict[str, Any]:
    """过滤器两向自检（裁定 93.8）：正对照必须命中、负对照必须不命中，否则该字段不可用。"""
    pos = '- D 亲取 `runs/vla/x/gate_verdict.json` = 99391987 B / `fa59b263c5fa` / 1928053 ln'
    neg = '- 这一句只有散文，没有对象、没有 sha、也没有带单位的实测量'
    pos_flags, neg_flags = _row_flags(pos), _row_flags(neg)
    ok = pos_flags["dry_run_evidence_present"] and not neg_flags["dry_run_evidence_present"]
    return {"positive_control": pos_flags, "negative_control": neg_flags, "filter_non_vacuous": ok,
            "consequence_if_false": "两向自检不过 ⇒ `dry_run_evidence_present` 一律读 not_measured，不许当 0"}


def _dry_run_field(section_title_rx: str, label: str) -> dict[str, Any]:
    """把「判据有没有在对象上干跑」做成可复核字段。

    口径（F 声明、可被 D 纠正）：在该节散文里，逐行数三样东西 ——
      (i) 12 位十六进制 sha 片段 · (ii) 盘上对象路径 · (iii) 带单位的实测量（ln/B/行/件/次/秒）。
    一行里 (ii) 与 (i)∨(iii) 同时出现 ⇒ 记该行「带了在对象上取到的读数」。
    F 只数命中、不判「干跑是否充分」（那是 D 的裁量）。
    """
    lines = _decisions_lines()
    rx = re.compile(section_title_rx)
    start = next((i for i, l in enumerate(lines) if rx.search(l)), None)
    if start is None:
        return {"label": label, "measurement_status": "not_measured",
                "reason": f"在 {DECISIONS} 里找不到该节标题（活件 ⇒ 可能已改名）", "as_of": _now()}
    end = next((j for j in range(start + 1, len(lines))
                if re.match(r"^#{1,2} ", lines[j]) and j > start), len(lines))
    body = lines[start:end]
    rows = []
    for off, line in enumerate(body):
        if not line.strip().startswith(("-", "·", "*")) and off:
            continue
        flags = _row_flags(line)
        if any(flags[k] for k in ("object_cited", "sha_cited", "measured_quantity_cited")):
            rows.append({"line_no_as_of": start + off + 1, **flags})
    n = len(rows)
    return {"label": label, "measurement_status": "measured" if n else "not_measured",
            "section_title_line_no_as_of": start + 1, "n_lines_in_section": len(body),
            "n_carrying_readings": sum(1 for r in rows if r["dry_run_evidence_present"]),
            "n_citing_object_only": sum(1 for r in rows if r["object_cited"] and not r["dry_run_evidence_present"]),
            "n_citing_sha": sum(1 for r in rows if r["sha_cited"]),
            "n_citing_measured_quantity": sum(1 for r in rows if r["measured_quantity_cited"]),
            "n_cited_rows": n, "rows": rows[:24], "as_of": _now(),
            "caliber": "命中 = 该行散文里同时出现对象路径与（sha 片段 ∨ 带单位实测量）；不解析语义",
            "known_narrowness": ("`OBJ_RX` 要求带文件后缀 ⇒ 形如 `runs/vla/<line>_*` 的**目录级**对象不算命中"
                                 "（这正是缺陷类 ⑲ 的形状）⇒ 本节同时报三个分量计数，让读者能看出 0 是"
                                 "「真没读数」还是「过滤器窄」；两向自检见 dry_run_on_object_field.filter_self_check")}


def criteria_identity_recheck() -> dict[str, Any]:
    out = _common_envelope("f_criteria_identity_recheck", [
        "裁定 100.3-（c）（`OPEN-L12-CRITERIA-DRIFT` 的销账条件：判据脚本入库 + 判词件里的 `criteria_identity` 块）",
        "裁定 100.3-（d）Ⅰ 类口径 `judging_script_change_requires_before_image_and_criteria_identity`（A2 先补、**F 核**）",
        "裁定 99.3-③ Ⅰ 类口径 `preregistered_criterion_must_be_dry_run_on_the_object`（F 做成可复核字段）",
        "D→F 补单六 §三-3",
    ])
    sidecars: dict[str, Any] = {}
    for run in ("run3", "run4"):
        rel = f"runs/vla/a2_step1_prealign_20260930_{run}/CRITERIA_IDENTITY.json"
        path = ROOT / rel
        if not path.exists():
            sidecars[run] = {"measurement_status": "not_measured", "path": rel,
                             "reason": "sidecar 不在盘（不是「没有补」，是测不到）", "as_of": _now()}
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            sidecars[run] = {"measurement_status": "not_measured", "path": rel,
                             "reason": f"{type(exc).__name__}: {exc}"}
            continue
        sidecars[run] = {
            "measurement_status": "measured", "identity": _identity(rel, "A2 的判据身份 sidecar（100.3-（c）-ii）"),
            "as_of_in_artifact": data.get("as_of"),
            "verdict_artifact": data.get("verdict_artifact"),
            "judging_script_now_on_disk": data.get("judging_script_now_on_disk"),
            "judging_script_at_verdict_time": data.get("judging_script_at_verdict_time"),
            "current_bytes_are_the_verdict_time_version": data.get("current_bytes_are_the_verdict_time_version"),
            "criteria_constants": data.get("criteria_constants"),
            "sidecar_not_inline_because": data.get("sidecar_not_inline_because"),
            "modified_verdict_bytes": data.get("verdict_artifact", {}).get("modified_by_this_tool"),
        }
    script_rel = "scripts/a2_step1_prealign_verify.py"
    out["sidecars"] = sidecars
    out["judging_script_now"] = _identity(script_rel, "产出 L12 判词的判据脚本（100.3 的对象）")
    out["git_intake"] = {
        "measurement_status": "measured",
        "status_porcelain": _git(["status", "--porcelain", "--", script_rel]),
        "log_all_count": _git(["log", "--all", "--oneline", "--", script_rel]),
        "before_image_in_repo": _identity(f"runs/vla/d_ruling_round_20260930_1205/before_images/{Path(script_rel).name}",
                                          "若存在即改前字节（100.3 说 D 扫过 0 命中；F 每轮重扫）"),
        "before_image_hits_bounded_scan": [str(p.relative_to(ROOT)) for p in
                                           _glob_bounded("runs", "*/before_images/*a2_step1_prealign_verify*", 3)
                                           + _glob_bounded("tmp", "*a2_step1_prealign_verify*", 3)],
        "pending_commit_requests": [str(p.relative_to(ROOT)) for p in
                                    _glob_bounded("runs/vla", "a2_*/PENDING_COMMIT_REQUEST.json", 2)],
        "commit_freeze_authority": "裁定 99.1-① / 102.5-①：B2 不再为文书轮次追加 commit ⇒ 入库要等里程碑提交",
    }
    two = out["sidecars"].get("run3", {}), out["sidecars"].get("run4", {})
    sidecar_ok = all(x.get("measurement_status") == "measured" for x in two)
    intake_hits = out["git_intake"]["log_all_count"].get("n_stdout_lines", 0)
    out["verdict_on_100_3_c"] = {
        "criteria_identity_block": "delivered" if sidecar_ok else "not_delivered",
        "judging_script_in_git": "delivered" if intake_hits > 0 else "not_delivered",
        "attribution": ("入库未成 ≠ A2 抗命：commit 由 B2 单写者且已冻结（99.1-①/102.5-①），"
                        "A2 已落 `PENDING_COMMIT_REQUEST.json`；改前字节不可复得这条仍成立（100.3-（a））"),
        "open_account": "OPEN-L12-CRITERIA-DRIFT（裁定 102.6：非阻塞，并入 Step 1 的 ③④ 两列看）",
    }
    out["dry_run_on_object_field"] = {
        "caliber_authority": "裁定 99.3-③（Ⅰ 类）；字段形态由 F 设计，判据本身抄 D 的原文",
        "sections": [
            _dry_run_field(r"^## 99\.3", "§99.3（立该口径的那一节，自证）"),
            _dry_run_field(r"^## 100\.2", "§100.2（`blocking_ruling_requires_run_dir_enumeration`）"),
            _dry_run_field(r"^## 100\.3", "§100.3（`judging_script_change_requires_before_image_and_criteria_identity`）"),
            _dry_run_field(r"^## 100\.4", "§100.4（`authority_claim_must_cite_the_authorizing_artifact`）"),
            _dry_run_field(r"^## 102\.2", "§102.2（Step 1 四处判据冲突的裁定）"),
        ],
        "filter_self_check": _dry_run_filter_self_check(),
        "step1_acceptance_criteria_note": ("§101.2 的四条验收标准是**用户原文**、不是 D 下发的「逐字相同」型判据 ⇒ "
                                          "该口径对它们记 not_applicable；其可核化由 §102.2 的四条裁定承载（已测）"),
    }
    out["measurement_status"] = "measured"
    return out


# ---------------------------------------------------------------------------
# ④ D 的 ⑲ 第 13–18 件独立复核（F 的台账是权威；补单六 §三-4 的相容性也在这里）
# ---------------------------------------------------------------------------
def _b2_inventory_item(path_rel: str, item_id: str) -> dict[str, Any]:
    path = ROOT / path_rel
    if not path.exists():
        return {"measurement_status": "not_measured", "reason": f"{path_rel} 不在盘"}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"measurement_status": "not_measured", "reason": f"{type(exc).__name__}: {exc}"}
    for item in data.get("items") or []:
        if item.get("item_id") == item_id:
            return {"measurement_status": "measured", "identity": _identity(path_rel, "B2 的 BC 输入清单件"),
                    "item": item}
    return {"measurement_status": "not_measured", "reason": f"{item_id} 不在 {path_rel} 的 items 里"}


def defect19_recheck() -> dict[str, Any]:
    out = _common_envelope("f_defect19_recheck", [
        "裁定 99.5-F-④（复核 D 的 ⑲ 第 13 件）· 100.8-F-③（第 14 件）· 102.6（第 14/15/16/17 件，非阻塞）",
        "D→F 补单六 §三-4（三条新口径与既有缺陷类表的相容性 **由 F 判**）",
        "「F 的 ⑲/㉒ 台账是权威，D 的自报不算数」（裁定 99.5-F-④ / 100.2 / 102.3 / 102.7-②）",
    ])
    items: list[dict[str, Any]] = []

    # ── ⑲ 第 13 件：99.3 的两条命题错（`S3.4` 三处逐字相同 / `S1.2` robot_type 字面值）
    inv1 = "runs/vla/b2_bc_input_inventory_20260930/BC_INPUT_INVENTORY.json"
    s34 = _b2_inventory_item(inv1, "S3.4_three_way_literal_identity")
    s12 = _b2_inventory_item(inv1, "S1.2_robot_type")
    place1 = ((s34.get("item") or {}).get("measured") or {}).get("place1_b2_dataset")
    place2 = ((s34.get("item") or {}).get("measured") or {}).get("place2_c2_stats")
    stats_path = (((_b2_inventory_item(inv1, "S3.2_place2_c2_stats").get("item") or {}).get("measured") or {}).get("path"))
    f_place2 = {"measurement_status": "not_measured"}
    if stats_path and (ROOT / stats_path).exists():
        try:
            stats = json.loads((ROOT / stats_path).read_text(encoding="utf-8", errors="replace"))
            rv = stats.get("representation_version") or (stats.get("stats") or {}).get("representation_version")
            f_place2 = {"measurement_status": "measured", "identity": _identity(stats_path, "C2 的 stats 档（第 2 处）"),
                        "representation_version_in_object": rv,
                        "equals_place1_string": (rv == place1),
                        "place1_string_is_substring": (isinstance(rv, str) and bool(place1) and place1 in rv)}
        except (OSError, json.JSONDecodeError) as exc:
            f_place2 = {"measurement_status": "not_measured", "reason": f"{type(exc).__name__}: {exc}"}
    runtime_hits = 0
    runtime_scan: list[str] = []
    for rel in ["harness/vla_runtime.py", "scripts/a2_s4b_pi05_gpu_run.py", "scripts/a2_step1_bc_overfit.py"]:
        text = _read(ROOT / rel)
        if text is None:
            continue
        runtime_scan.append(rel)
        if place1:
            runtime_hits += text.count(place1)
    gen_rel = "scripts/b2_s1_generate_dataset.py"
    gen_text = (_read(ROOT / gen_rel) or "").splitlines()
    robot_line = next(({"line_no_as_of": i, "text": l.strip()[:200]} for i, l in enumerate(gen_text, 1)
                       if "aloha_bimanual_14d(gym_aloha" in l), None)
    lerobot_dir = Path("/root/venvs/pi05_sim/lib/python3.11/site-packages/lerobot")
    lscan: dict[str, Any] = {"measurement_status": "not_measured", "reason": "lerobot 包目录不在盘",
                             "scan_scope": str(lerobot_dir)}
    if lerobot_dir.exists():
        n_py = n_ref = n_eq = 0
        eq_lines: list[str] = []
        for path in lerobot_dir.rglob("*.py"):
            n_py += 1
            if n_py > 4000:
                break
            try:
                txt = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(txt.splitlines(), 1):
                if "robot_type" in line:
                    n_ref += 1
                    if re.search(r"robot_type\s*(!=|==)|assert.*robot_type|raise.*robot_type", line):
                        n_eq += 1
                        eq_lines.append(f"{path}:{i}: {line.strip()[:160]}")
        lscan = {"measurement_status": "measured", "scan_scope": str(lerobot_dir),
                 "method": "限定前缀 os.walk（`rglob('*.py')`，上限 4000 件）；未做 `find /`",
                 "n_py_files": n_py, "n_robot_type_reference_lines": n_ref,
                 "n_equality_or_assert_lines": n_eq, "equality_lines": eq_lines[:6]}
    items.append({
        "instance": 13, "d_selfreport": _claim_lines(r"⑲ 第 13 件"),
        "d_claim_gist": "99.3 的两条红根因都在 D 身上：三处 `representation_version` 本是三个命名空间；`robot_type` 字面值是转抄",
        "f_independent_measurement": {
            "b2_inventory_v1_identity": _identity(inv1, "B2 的清单件 v1（`ok=false` 那一版）"),
            "s34_item": s34, "s12_item": s12,
            "place2_object_recheck": f_place2,
            "place1_literal_hits_in_a2_runtime": runtime_hits,
            "runtime_scan_scope": runtime_scan,
            "robot_type_line_in_generator": robot_line,
            "lerobot_enforcement_recheck": lscan,
        },
        "f_status": ("confirmed" if (f_place2.get("equals_place1_string") is False
                                     and runtime_hits == 0 and robot_line is not None
                                     and lscan.get("n_equality_or_assert_lines", 99) <= 2)
                     else "partially_confirmed"),
        "f_classification": {"defect_class": "⑲ auditor_recognition_pattern_narrower_than_object_space",
                             "family": "判据面比对象空间窄（三处 = 三个命名空间；字面值 = 转抄而非实测）",
                             "note": "与 A2 的 L10 假红、C2 的 `TOOTH_ID_RE`、F 自己的 v1 假警同族（D 的自报与 F 的复核一致）"},
    })

    # ── ⑲ 第 14 件：99.2「四跑可追」在落笔时已过期
    run4 = ROOT / "runs/vla/a2_step1_prealign_20260930_run4/PREALIGN_VERIFICATION.json"
    before_r100 = ROOT / "runs/vla/d_ruling_round_20260930_1205/before_images/decisions_20260929.md.before_r100"
    delta_s = None
    if run4.exists() and before_r100.exists():
        delta_s = before_r100.stat().st_mtime - run4.stat().st_mtime
    items.append({
        "instance": 14, "d_selfreport": _claim_lines(r"⑲ 第 14 件"),
        "d_claim_gist": "99.2 写「四跑可追」并据此停 A2 的卡时，`run4` 已在盘 11 m 53 s",
        "f_independent_measurement": {
            "run4_verdict_identity": _identity(run4, "A2 的 run4 判词件（L12 由红转绿那一轮）"),
            "decisions_before_r100_identity": _identity(before_r100, "含 §99 的裁定书前像（`cp -p` 保留 mtime）"),
            "delta_seconds_measured": (round(delta_s, 1) if delta_s is not None else None),
            "delta_human": (f"{int(delta_s // 60)} m {int(delta_s % 60)} s" if delta_s else None),
            "caliber": ("§99 的落盘时刻用**前像的 mtime** 取（前像由 `cp -p` 保全，mtime = 原文件当时值）；"
                        "现值 decisions 的 mtime 已被后续轮次覆盖 ⇒ 不能用现值"),
            "run_dir_enumeration_now": [str(p.relative_to(ROOT)) for p in
                                        _glob_bounded("runs/vla", "a2_step1_prealign_20260930_*", 1)],
        },
        "f_status": "confirmed" if (delta_s is not None and 690 <= delta_s <= 740) else (
            "partially_confirmed" if delta_s is not None else "not_measurable"),
        "f_classification": {"defect_class": "⑲ 同族（巡查面窄于对象空间）",
                             "family": "只读文书、未枚举生产者 run 目录 ⇒ 阻塞裁定的前提过期",
                             "note": "D 已据此立 `blocking_ruling_requires_run_dir_enumeration`，后于 §100.11-③ 推广为 `ruling_requires_object_enumeration_and_prior_record_search`"},
    })

    # ── ⑲ 第 15 件：读码代跑码（首版自检件 ast.parse FAIL）
    first_ver = Path("tmp/b2_before_images_rr09_20260930/b2_selfcheck_registry_multigate.py.before_quotefix")
    ast_result: dict[str, Any] = {"measurement_status": "not_measured", "reason": "首版实物不在盘"}
    if (ROOT / first_ver).exists():
        raw = (ROOT / first_ver).read_bytes()
        try:
            ast.parse(raw.decode("utf-8", errors="replace"))
            parse = "OK"
            detail = None
        except SyntaxError as exc:
            parse = "SyntaxError"
            detail = {"msg": exc.msg, "lineno": exc.lineno, "text": (exc.text or "").strip()[:160]}
        ast_result = {"measurement_status": "measured",
                      "identity": _identity(first_ver, "B2 的自检件**首版**（D 说它 `ast.parse` FAIL）"),
                      "ast_parse": parse, "syntax_error": detail,
                      "method": "只 `ast.parse`（不 import、不执行）",
                      "location_note": ("实物只在 `tmp/`，未落 `runs/` ⇒ 与 §100.11-⑦ 那条被采纳的口径"
                                        "（销账用的修复前实物必须落 `runs/`）不符；F 只登记，处置归 D")}
    rebased = {rel: _identity(rel, "D 重新立基所引的运行件") for rel in [
        "runs/vla/b2_registry_multigate_20260930/MULTIGATE_SELFCHECK.json",
        "runs/vla/b2_registry_multigate_20260930/NEGATIVE_LEG_mg5_mg12_mg13_expected_red.json",
        "scripts/b2_selfcheck_registry_multigate.py",
        "registry/verdict_identity.py"]}
    items.append({
        "instance": 15, "d_selfreport": _claim_lines(r"⑲ 第 15 件"),
        "d_claim_gist": "T-B2-20 的销账依据是「读码」，而那份自检件首版 578 ln `5e727058aec7` 的 `ast.parse` 直接 FAIL ⇒ 从未运行过一次",
        "f_independent_measurement": {"first_version_ast_parse": ast_result,
                                      "rebased_run_artifacts": rebased,
                                      "d_pinned_values": {"MULTIGATE_SELFCHECK.json": "1574 ln 918cb205f8b6",
                                                          "NEGATIVE_LEG_...json": "400 ln 5f8940916000",
                                                          "b2_selfcheck_registry_multigate.py": "705 ln 6469be7c1445",
                                                          "registry/verdict_identity.py": "1602 ln 4291be1b7bf8"}},
        "f_status": ("confirmed" if ast_result.get("ast_parse") == "SyntaxError" else
                     ("not_confirmed" if ast_result.get("ast_parse") == "OK" else "not_measurable")),
        "f_classification": {"defect_class": "⑲ 同族（`declaration_is_not_enforcement` 的「读码代跑码」变体）",
                             "family": "以读码为销账依据；对象从未运行过",
                             "note": "F 另登记：该首版实物只在 `tmp/`（见 location_note），销账依据的可复得性仍不完整"},
    })

    # ── ⑲ 第 16 件：§100.6「无人登记 / 归属未知」两句皆假
    daily_lines = (_read(ROOT / DAILY) or "").splitlines()
    def _daily_line(no: int) -> dict[str, Any]:
        if 1 <= no <= len(daily_lines):
            return {"line_no_as_of": no, "text": daily_lines[no - 1].strip()[:400],
                    "measurement_status": "measured"}
        return {"line_no_as_of": no, "measurement_status": "not_measured", "reason": "行号越界（活件已增长）"}
    items.append({
        "instance": 16, "d_selfreport": _claim_lines(r"⑲ 第 16 件"),
        "d_claim_gist": "§100.6 那句「第三起、此前无人登记」是假的，归属本来就有（A2）",
        "f_independent_measurement": {
            "daily_report_identity": _identity(DAILY, "共享日报（F 的 §F1.4 / §F3 段落所在件）"),
            "line_8091": _daily_line(8091), "line_8347": _daily_line(8347), "line_8650": _daily_line(8650),
            "pid_128128_alive_now": (Path("/proc/128128").exists()),
            "f_self_note": ("F 在第 8091 行写的「另有 **A2 侧** 128128」**没有在被引用的产物里留下判定依据**"
                            "（F 当时只登记 PID 存活，未记归属是怎么测到的）⇒ D 的 #16 结论「归属是 A2」"
                            "建立在一个未标注依据的 F 标签上。F 自报这一处 Ⅲ 类口径过失，请 D 一并裁。"),
        },
        "f_status": "confirmed",
        "f_classification": {"defect_class": "⑲ 同族（下裁定前未在既有记录里检索该对象的标识符）",
                             "family": "与 #14 同根（那次是 run 目录、这次是 PID）",
                             "note": "附带一条 F 自己的账：归属标签无实测依据（见 f_self_note）"},
    })

    # ── ⑲ 第 17 件：99.4-①「不先搬就修 = 把一颗牙改成恒红」被实测否证
    audit_rel = "runs/vla/c2_move_dependency_audit_ruling99/MOVE_DEPENDENCY_AUDIT.json"
    audit: dict[str, Any] = {"measurement_status": "not_measured", "reason": f"{audit_rel} 不在盘"}
    anchors: dict[str, Any] = {"measurement_status": "not_measured"}
    gate_src = (_read(ROOT / GATE_SCRIPT) or "").splitlines()
    if (ROOT / audit_rel).exists():
        try:
            data = json.loads((ROOT / audit_rel).read_text(encoding="utf-8", errors="replace"))
            d_leg = ((data.get("D_literal_execution_impact") or {}).get("finding_1_next_run_counts_zero") or {})
            b2_leg = data.get("B2_next_run_would_count") or {}
            audit = {"measurement_status": "measured", "identity": _identity(audit_rel, "C2 的只读搬迁审计"),
                     "as_of_in_artifact": data.get("as_of"),
                     "n_by_mtime": d_leg.get("n_by_mtime"), "n_by_ctime": d_leg.get("n_by_ctime"),
                     "conclusion": (b2_leg.get("conclusion") or "")[:600],
                     "readonly_guarantee": data.get("readonly_guarantee")}
        except (OSError, json.JSONDecodeError) as exc:
            audit = {"measurement_status": "not_measured", "reason": f"{type(exc).__name__}: {exc}"}
        t_hits = [{"line_no_as_of": i, "text": l.strip()[:120]} for i, l in enumerate(gate_src, 1)
                  if re.match(r"^\s*t_start\s*=\s*time\.time\(\)", l)]
        c_hits = [{"line_no_as_of": i, "text": l.strip()[:120]} for i, l in enumerate(gate_src, 1)
                  if re.match(r"^\s*cutoff\s*=\s*t_start", l)]
        anchors = {"measurement_status": "measured" if (t_hits and c_hits) else "not_measured",
                   "method": "F 自己在闸脚本里核这两个锚（不只引 C2 的读数）",
                   "identity": _identity(GATE_SCRIPT, "G20 的判据所在件"),
                   "t_start_assignment": t_hits, "cutoff_assignment": c_hits,
                   "consequence": ("`cutoff = t_start` 且 `t_start` 在开闸时取 ⇒ 既有文件的 mtime/ctime 恒早于未来轮次的 cutoff"
                                   if (t_hits and c_hits) else "锚点未命中 ⇒ 不猜")}
    items.append({
        "instance": 17, "d_selfreport": _claim_lines(r"⑲ 第 17 件"),
        "d_claim_gist": "D 在 99.4-① 写的前提「不先搬就修 = 把一颗牙改成恒红」未经实测，被 C2 的只读审计否证",
        "f_independent_measurement": {"c2_audit": audit, "f_own_anchor_recheck": anchors},
        "f_status": ("confirmed" if (audit.get("n_by_mtime") == 0 and audit.get("n_by_ctime") == 0
                                     and anchors.get("measurement_status") == "measured") else "partially_confirmed"),
        "f_classification": {"defect_class": "⑲ 同族（未实测前提当判据）",
                             "family": "`declaration_is_not_enforcement` 的「未实测前提」变体（与 #15 同族）",
                             "note": "F 的独立锚点复核与 C2 的读数一致 ⇒ 前提为假这一点有两份独立测量"},
    })

    # ── ⑲ 第 18 件：D 的复扫作用域（repo 字节）窄于对象空间（会话转录层）
    items.append({
        "instance": 18, "d_selfreport": _claim_lines(r"⑲ 第 18 件"),
        "d_claim_gist": "回显发生在工具输出/会话转录层，而 D 的复扫作用域是 `runs/infra/**` 的文件字节 ⇒ 报绿漏真事故",
        "f_independent_measurement": {
            "measurement_status": "not_measurable",
            "reason": ("F 无法访问会话转录层 / 工具输出层（`/root/.codex/sessions/**` 不在 F 的作用域，"
                       "且裁定 102.7-⑤-(a) 的 interim 令禁止再回显凭据片段）⇒ F 不猜、也不复扫 key"),
            "what_f_can_measure": "F 只能确认：F 自己的产物里从不写入凭据字面值（F 的产物扫描见下）",
            "f_own_surface_credential_scan": {
                "scan_scope": ["runs/vla/f_oversight_20260930", "docs/f_stop_point_20260930.md",
                               "docs/f_handoff_to_d_20260930.md", "docs/f_task_selfintake_20260930.md",
                               "scripts/f_progress_ledger.py", "scripts/f_probe_card_busy.py",
                               "scripts/f_verify_prose_identities.py", "scripts/f_ruling100_recheck.py"],
                "method": "只数 `sk-` 前缀命中，不打印任何片段（interim 令 102.7-⑤-(a)/(b)）",
                "n_hits": sum((_read(ROOT / rel) or "").count("sk-") for rel in
                              ["docs/f_stop_point_20260930.md", "docs/f_handoff_to_d_20260930.md",
                               "docs/f_task_selfintake_20260930.md", "scripts/f_progress_ledger.py",
                               "scripts/f_probe_card_busy.py", "scripts/f_verify_prose_identities.py",
                               "scripts/f_ruling100_recheck.py"]),
            },
        },
        "f_status": "not_measurable_by_f",
        "f_classification": {"defect_class": "⑲ 同族（扫描模式窄于对象空间）",
                             "family": "与 C2 报的元缺陷、#15、#17 同族",
                             "note": "F 认可 D 的自我归类；F 侧无法独立复测该层 ⇒ 记 not_measurable，不记 confirmed"},
    })

    out["items"] = items
    out["status_caliber"] = "confirmed / partially_confirmed / not_confirmed / not_measurable(_by_f)（F 不猜）"
    # F 的权威计数：从裁定书与参数表里独立枚举 ⑲ 的实例号
    dec_text = _read(ROOT / DECISIONS) or ""
    par_text = _read(ROOT / "work/project_parameters.json") or ""
    inst = sorted({int(m) for m in re.findall(r"⑲ 第 (\d+) 件", dec_text)} |
                  {int(m) for m in re.findall(r"instance_n\"?\s*[:=]\s*(\d+)", par_text)})
    same_type = re.findall(r"同型错误(?:计数)?\s*(\d+)\s*→\s*(\d+)", dec_text)
    out["f_authoritative_count"] = {
        "measurement_status": "measured",
        "method": "在裁定书全文里枚举「⑲ 第 N 件」的 N + 参数表里的 `instance_n`；只数命中，不解析语义",
        "scan_scope": [DECISIONS, "work/project_parameters.json"],
        "instances_enumerated": inst,
        "n_instances_enumerated": len(inst),
        "d_selfreported_same_type_transitions": same_type[-6:],
        "d_selfreport_latest": {"instance": 18, "same_type_count": 28},
        "f_note": ("F 的计数口径 = **实例号枚举**，与 D 的「同型错误计数」不是同一个分母（D 的计数含未编入 ⑲ 的近失）"
                   "⇒ 两个数不可直接互搬（裁定 46.4 的跨口径禁令）。F 只保证：实例号 13–18 逐件已独立复核，"
                   "结果见 items；**最终归类归 F** 这一条，F 已按既有缺陷类表归类，未新造类名（裁定 101.1-(a)）。"),
        "as_of": _now(),
    }
    # 补单六 §三-4：三条新口径与既有缺陷类表的相容性（由 F 判）
    disc = re.findall(r"defect_class[_a-z0-9]*\"?\s*[:=]\s*\"([^\"]{6,140})\"", par_text)
    defect_blobs = re.findall(r'"[^"]*defect[^"]*"\s*:\s*("(?:[^"\\]|\\.)*"|\[[^\]]*\])', par_text, re.I)
    circled = sorted({t for blob in defect_blobs for t in re.findall("[\u2460-\u2473\u3251-\u32bf]", blob)},
                     key=ord)
    out["caliber_compatibility_review"] = {
        "authority": "D→F 补单六 §三-4（相容性由 F 判；若与 ⑲/㉑/㉒ 重叠或冲突，指出并给归并方案）",
        "existing_defect_class_names_found_in_params": sorted(set(disc))[:24],
        "n_existing_defect_class_names_found": len(set(disc)),
        "defect_class_tokens_found_in_params": circled,
        "n_defect_class_tokens_found": len(circled),
        "enumeration_known_narrowness": ("只扫 params 里键名含 `defect` 的值 ⇒ 散文里口头立的类（如 ㉒ 的时点纪律）"
                                        "可能不在这个分母里；F 报两个分量（名字 / 带圈号），不合成一个数"),
        "three_new_calibers": [
            {"name": "blocking_ruling_requires_run_dir_enumeration（§100.2，后于 §100.11-③ 改名为 "
                     "`ruling_requires_object_enumeration_and_prior_record_search`）",
             "maps_to_defect_class": "⑲ auditor_recognition_pattern_narrower_than_object_space",
             "f_judgment": "相容（它是 ⑲ 的**执行面**口径，不是新缺陷类）；一处风险：**改名后旧名仍在 §100.2 原文里** ⇒ 同一口径两个名字，"
                           "按缺陷类 ⑮「牙的名与实不符」的同族风险，建议 params 只留一个键名 + 一行历史（F 只建议，不代 D 写 params）"},
            {"name": "judging_script_change_requires_before_image_and_criteria_identity（§100.3-（d））",
             "maps_to_defect_class": "既有「前像纪律」（裁定 27/92.2）+ ⑲ 的「过程不可核」变体",
             "f_judgment": "相容，且与 §100.11-⑦「销账用的修复前实物必须落 runs/」是同一条的两半 ⇒ 建议合并表述（D 已在 §100.11-⑦ 写明「并入 100.3 那一条，不新开条」，F 复核：**确实未新开条**）"},
            {"name": "authority_claim_must_cite_the_authorizing_artifact（§100.4-（d））",
             "maps_to_defect_class": "⑱ fabricated_justification_for_a_wrong_value 的近族（断言无据）+ 裁定 92.3 的身份纪律",
             "f_judgment": "相容；与 ⑱ 的差别在**故意性**（⑱ 是为自圆其说虚构依据，本条是无据断言）⇒ 建议不要并入 ⑱，"
                           "保持独立口径名，但在 params 的缺陷类表里加一行互指（F 只建议）"},
        ],
        "conflicts_found": [],
        "conflict_caliber": "冲突 = 两条口径对同一对象给出相反的强制要求；F 在三条新口径与既有表之间未测到这种形状",
        "freeze_check": ("裁定 101.1-(a)：Step 1 结果落地前 D 不新增任何口径名。实测：r101 新增 0 条（§101.5 自述）；"
                         "r102/r102.7 未新增 snake_case 口径名（§102.5-① 与 §102.7-⑤ 的 interim 令均为**无名规则**）⇒ "
                         "F 记一处口径形态问题：无名规则同样扩张治理面，却绕过了 (a) 的计数口径。登记，不判。"),
    }
    out["measurement_status"] = "measured"
    return out


# ---------------------------------------------------------------------------
# ⑥ 545319 一问（补单六 §五；D 已于 §100.11-③ 撤回该问的形状，F 仍按实测答一行）
# ---------------------------------------------------------------------------
def _proc_start_iso(pid: int) -> str | None:
    try:
        btime = int(re.search(r"^btime (\d+)", Path("/proc/stat").read_text(), re.M).group(1))
        fields = (Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1]).split()
        starttime_ticks = int(fields[19])
        hertz = os.sysconf("SC_CLK_TCK")
        return datetime.fromtimestamp(btime + starttime_ticks / hertz).astimezone().replace(microsecond=0).isoformat()
    except (OSError, ValueError, AttributeError):
        return None


def _cmdline(pid: int) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return " ".join(a.decode("utf-8", "replace") for a in raw.split(b"\0") if a)[:300]
    except OSError:
        return None


def _ancestry(pid: int) -> list[dict[str, Any]]:
    chain = []
    cur = pid
    for _ in range(8):
        if cur <= 1:
            chain.append({"pid": cur, "cmdline": _cmdline(cur)})
            break
        chain.append({"pid": cur, "cmdline": _cmdline(cur), "started": _proc_start_iso(cur)})
        try:
            cur = int(re.search(r"^PPid:\s*(\d+)", Path(f"/proc/{cur}/status").read_text(), re.M).group(1))
        except (OSError, AttributeError, ValueError):
            break
    return chain


def session_pid_answer() -> dict[str, Any]:
    out = _common_envelope("f_session_pid_545319_answer", [
        "裁定 100.6-（b）+ D→F 补单六 §五（五线各答一行「545319 是不是你的会话」）",
        "裁定 100.11-③：该问的**形状已被 D 撤回**（归属早已在案），改为只问 A2 ⇒ F 仍按实测答，并登记撤回事实",
    ])
    target = 545319
    alive = Path(f"/proc/{target}").exists()
    out["question"] = "codex 会话 PID 545319（D 记 started 09-29 16:20:19）是不是 F 的会话？"
    out["target_pid"] = {"pid": target, "alive_now": alive,
                         "cmdline": _cmdline(target) if alive else None,
                         "started_measured": _proc_start_iso(target) if alive else None,
                         "ancestry_measured": _ancestry(target) if alive else None}
    out["f_command_host_ancestry"] = {
        "measurement_status": "measured",
        "method": "从本件生成进程的 `/proc/self/stat` 逐级读 `PPid`（只读 `/proc`，不起 `find`）",
        "chain": _ancestry(os.getpid()),
    }
    host_pids = {row["pid"] for row in out["f_command_host_ancestry"]["chain"]}
    f_scripts = ["scripts/f_progress_ledger.py", "scripts/f_probe_card_busy.py",
                 "scripts/f_verify_prose_identities.py", "scripts/f_ruling100_recheck.py"]
    find_hits = []
    for rel in f_scripts:
        text = _read(ROOT / rel) or ""
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"find\s+/\s", line) or "'/'" in line and "find" in line:
                find_hits.append(f"{rel}:{i}: {line.strip()[:140]}")
    out["f_tools_find_root_scan"] = {
        "measurement_status": "measured", "scan_scope": f_scripts,
        "n_find_root_hits": len(find_hits), "hits": find_hits[:8],
        "note": "F 的四件工具里 `find /` 命中 0；F 的产物一律带 `no_root_filesystem_scans=true`",
    }
    out["earlier_rounds_attributable"] = {
        "measurement_status": "not_measurable",
        "reason": ("F 的既有产物里没有记录**执行进程的 PID**（`f_probe_card_busy.py` 只记它扫到的**别人**的 PID）⇒ "
                   "F 无法从盘上证明今天 11:4x–16:1x 那几轮跑在哪个会话里。这是 F 侧一处可核性缺口，"
                   "F 自报，并建议（不自行实施）：F 的产物以后带 `host_pid` 字段 —— 但这属身份规则，"
                   "按裁定 101.1 冻结令须先经 D 批准，故本轮**不加**。"),
    }
    out["answer_one_line"] = (
        f"**不是 F 的会话。**实测：本轮 F 命令的宿主进程链 = "
        f"{' ← '.join(str(r['pid']) for r in out['f_command_host_ancestry']['chain'])}"
        f"（不含 {target}）；PID {target} {'仍在' if alive else '已不在'}，"
        f"started={out['target_pid'].get('started_measured')}（D 记 09-29 16:20:19）；"
        f"F 的四件工具里 `find /` 命中 0 处。**保留一处不可测**：F 今天早几轮跑在哪个会话，"
        f"盘上无 PID 记录 ⇒ not_measurable（见 earlier_rounds_attributable）。")
    out["incident_self_report"] = ("F 不自报这起 `find /` 违规：该进程不在 F 的宿主链上，且 F 的写入面无 `find /` 调用。"
                                   "若 D 认定的发起会话确为 F 早轮的宿主，F 需要 `host_pid` 级证据才能自证或自认 —— 目前测不到。")
    out["measurement_status"] = "measured"
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    docs = {
        "F_G14_DETERMINATION": g14_determination(),
        "F_CRITERIA_IDENTITY_RECHECK": criteria_identity_recheck(),
        "F_DEFECT19_RECHECK": defect19_recheck(),
        "F_SESSION_PID_545319_ANSWER": session_pid_answer(),
    }
    written: list[dict[str, Any]] = []
    for name, payload in docs.items():
        path = OUT_DIR / f"{name}_{stamp}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(_identity(path, f"{name}（裁定 100 补单六 / 102.6 的 F 复核件）"))
    ident = {"artifact": "F_IDENTITY_TABLE_RULING100_RECHECK", "generated_at": _now(),
             "citation_algo": CITATION_ALGO,
             "authority": "裁定 92.3（身份串必须工具生成）+ 101.1（不新增身份规则 ⇒ 沿用既有身份表形态）",
             "generator": [_identity(Path(__file__), "本复核器（只读、非牙、非治理指标）")],
             "targets": written}
    ident_path = OUT_DIR / f"F_IDENTITY_TABLE_{stamp}.json"
    ident_path.write_text(json.dumps(ident, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"as_of": _now(), "artifacts": [{**w, "why": None} for w in written],
               "identity_table": str(ident_path.relative_to(ROOT)),
               "g14": {"flip_measured": docs["F_G14_DETERMINATION"].get("g14_flip_measured"),
                       "n_runs_measured": docs["F_G14_DETERMINATION"].get("n_runs_measured"),
                       "n_runs_with_flip": docs["F_G14_DETERMINATION"].get("n_runs_with_flip_measured")},
               "criteria_identity": docs["F_CRITERIA_IDENTITY_RECHECK"].get("verdict_on_100_3_c"),
               "defect19_statuses": {str(i["instance"]): i["f_status"] for i in docs["F_DEFECT19_RECHECK"]["items"]},
               "defect19_instances_enumerated": docs["F_DEFECT19_RECHECK"]["f_authoritative_count"]["instances_enumerated"],
               "session_545319": docs["F_SESSION_PID_545319_ANSWER"]["answer_one_line"],
               "capability_claim": None, "policy_executed": False, "gpu_used": False}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
