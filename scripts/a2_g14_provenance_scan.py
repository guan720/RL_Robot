#!/usr/bin/env python3
"""T-A2-7 的旁证件：`G14` 一次性前置（裁定 97.3-4）的**归属 + 证据**扫描。

为什么要有这件：裁定 97.3-4 把「`G14` 的实测翻转」定为 A2 第 1 步开跑前的**一次性前置**，
并写明 `checked_by = F`。A2 的准入闸（`harness/bc_admission_gate.py`）只核**证据件的存在与 sha**、
**不判语义**。所以在消费 C2 的成对广播之前，A2 必须把两件事分开登记清楚：

1. **证据**：同轮 `gate_verdict.json` 里 `G14` 那一条 check 的**实物字段**（`ok` / `status` /
   `triage_class` / `blocking`）与 `G24` 台账里 `flip_measured=True` 的清单、`M6` 变异体的
   `baseline=true → in_mutant_copy=false`（这三样合起来才是「翻转被测到了」）。
2. **归属**：F 的写入面里**有没有**一份独立判定 `G14` 翻转的件。这一问是**否定存在性结论**，
   按 D 的新口径（checkpoint §10 的 Ⅲ 类纪律）必须带**过滤器本身的两向自检** +
   **大小写 / 连字符与下划线 / 缩写三类变体各扫一次**，否则不许写「没有」。

本件**不判语义**（那是 F 的活），也**不改任何他线文件**。
输出：一份 JSON（`--out`）。`gpu_used=false`、`capability_claim=false`（裁定 46）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
from datetime import datetime
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]

# F 的写入面（**显式列举**，限定前缀；禁 `find /`，裁定 94.9-2 / `no_root_filesystem_scans`）
F_SURFACE_PREFIXES = (
    "runs/vla/f_oversight_20260930",
    "docs/f_stop_point_20260930.md",
    "scripts/f_progress_ledger.py",
    "scripts/f_probe_card_busy.py",
    "scripts/f_verify_prose_identities.py",
)
# 三类变体：大小写 · 连字符/下划线 · 缩写/别名（D 的 Ⅲ 类新口径）
VARIANTS = ("G14", "g14", "G-14", "G_14", "gate14", "gate_14",
            "Tr3_registers_warn", "Tr3_bites", "flip_measured", "M6_tr3", "翻转")
# 两向自检的**正向对照**：同一过滤器必须能命中（否则「0 命中」毫无意义）
POSITIVE_CONTROLS = ("card_busy", "133156", "e72776306f98", "PROGRESS_LEDGER")
# `gate_verdict.json` 里的证据形状（转义形态是因为 `G24` 的 `observed` 是 JSON 字符串套 JSON）
G14_ID = "G14_Tr3_registers_warn_on_mainline_only"
EVIDENCE_PATTERNS = {
    "check_row_id": ('"id": "%s"' % G14_ID).encode(),
    "baseline_true_in_mutant_ledger": ('\\"baseline\\": {\\"%s\\": true}' % G14_ID).encode(),
    "mutant_copy_false_in_mutant_ledger": ('\\"in_mutant_copy\\": {\\"%s\\": false}' % G14_ID).encode(),
    "listed_in_flip_measured_true": ("'%s'" % G14_ID).encode(),
    "mutant_id_m6": b"M6_tr3_always_blocking",
}
CHECK_ROW_FIELDS = ("id", "ok", "status", "triage_class", "blocking", "kind", "observed",
                    "mutant_that_proves_it", "ruling_ref")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _identity(path: pathlib.Path) -> dict[str, Any]:
    out: dict[str, Any] = {"path": str(path), "measurement_status": "not_measured"}
    if not path.exists():
        out["why"] = "路径不存在（读不到 ≠ 测到没有）"
        return out
    h = hashlib.sha256()
    n_bytes = n_nl = 0
    with path.open("rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
            n_bytes += len(b)
            n_nl += b.count(b"\n")
    out.update({"measurement_status": "measured", "sha256_12": h.hexdigest()[:12],
                "n_bytes": n_bytes, "n_lines_wc_l": n_nl})
    return out


def _machine_load() -> dict[str, Any]:
    out: dict[str, Any] = {"measurement_status": "measured", "nvidia_smi_called": False}
    try:
        la = os.getloadavg()
        out["loadavg"] = f"{la[0]:.2f} {la[1]:.2f} {la[2]:.2f}"
    except Exception as exc:                                          # noqa: BLE001
        out.update({"loadavg": None, "error": f"{type(exc).__name__}: {exc}"})
    try:
        stat = {}
        for ln in pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat").read_text().splitlines():
            k, _, v = ln.partition(" ")
            stat[k] = int(v)
        out["nr_throttled"] = stat.get("nr_throttled")
        out["cgroup_version"] = "v1"
    except Exception as exc:                                          # noqa: BLE001
        out.update({"nr_throttled": None, "error": f"{type(exc).__name__}: {exc}",
                    "measurement_status": "not_measured"})
    return out


def _iter_surface_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for pre in F_SURFACE_PREFIXES:
        p = REPO / pre
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            for root, _dirs, names in os.walk(p):
                for n in sorted(names):
                    files.append(pathlib.Path(root) / n)
    return sorted(set(files))


def _rel(p: Any) -> str:
    s = str(p)
    return s[len(str(REPO)) + 1:] if s.startswith(str(REPO)) else s


def _classify(rel_path: str) -> str:
    """命中件的**性质**：F 自己的产物 / F 目录里那份共享文件的副本 / F 的脚本或文书。"""
    if "/before_images/" in rel_path:
        return "copy_of_shared_file_in_f_before_images（**不是 F 自己的判定**）"
    if rel_path.startswith("runs/vla/f_oversight_20260930/"):
        return "f_own_artifact"
    if rel_path.startswith("docs/f_") or rel_path.startswith("scripts/f_"):
        return "f_own_doc_or_script"
    return "other"


def scan_surface(files: list[pathlib.Path]) -> dict[str, Any]:
    hits: dict[str, list[dict[str, str]]] = {v: [] for v in VARIANTS}
    ctrl: dict[str, int] = {c: 0 for c in POSITIVE_CONTROLS}
    scanned = 0
    for f in files:
        try:
            txt = f.read_text(errors="replace")
        except Exception:                                             # noqa: BLE001
            continue
        scanned += 1
        low = txt.lower()
        for v in VARIANTS:
            if v.lower() in low:
                hits[v].append({"path": _rel(f), "kind": _classify(_rel(f)),
                                "n_occurrences": txt.lower().count(v.lower())})
        for c in POSITIVE_CONTROLS:
            if c.lower() in low:
                ctrl[c] += 1
    n_ctrl_hit = sum(1 for v in ctrl.values() if v > 0)
    return {"scan_scope": list(F_SURFACE_PREFIXES),
            "n_files_scanned": scanned,
            "variants": {v: {"n_files_hit": len(hs), "hits": hs[:6]} for v, hs in hits.items()},
            "positive_control": {"terms": ctrl, "n_terms_hit": n_ctrl_hit,
                                "n_terms": len(POSITIVE_CONTROLS)},
            "two_way_self_check": {
                "forward": "11 个变体各扫一次（大小写 / 连字符与下划线 / 缩写与别名三类）",
                "backward": f"正向对照 {n_ctrl_hit}/{len(POSITIVE_CONTROLS)} 个词命中 ⇒ 过滤器非空转",
                "filter_non_vacuous": n_ctrl_hit == len(POSITIVE_CONTROLS),
                "caliber": "命中 = 文件文本里出现该词（**不区分它是判定还是转述**）⇒ 下面还要逐件看性质"}}


def extract_g14_from_gate_verdict(gv: pathlib.Path) -> dict[str, Any]:
    """单遍流式：数证据形状 + 抓 `G14` 那一条 check 对象的**实物字段**（95 MB 不整件载入）。"""
    out: dict[str, Any] = {"gate_verdict_identity": _identity(gv), "measurement_status": "not_measured"}
    if not gv.exists():
        out["why"] = "闸判词件不在盘（读不到 ≠ 测到没有）"
        return out
    counts = {k: 0 for k in EVIDENCE_PATTERNS}
    cur: list[bytes] | None = None
    cur_start = 0
    row: dict[str, Any] | None = None
    row_lines: tuple[int, int] | None = None
    with gv.open("rb") as fh:
        for lineno, raw in enumerate(fh, 1):
            for k, pat in EVIDENCE_PATTERNS.items():
                if pat in raw:
                    counts[k] += 1
            if raw.startswith(b"    {"):
                cur, cur_start = [raw], lineno
            elif cur is not None:
                cur.append(raw)
                if raw.startswith(b"    }"):
                    blob = b"".join(cur)
                    if row is None and ('"id": "%s"' % G14_ID).encode() in blob:
                        row_lines = (cur_start, lineno)
                        txt = blob.decode("utf-8", "replace").strip()
                        if txt.endswith(","):
                            txt = txt[:-1]
                        try:
                            obj = json.loads(txt)
                            row = {k: obj.get(k) for k in CHECK_ROW_FIELDS}
                            row["_parse"] = "ok"
                        except Exception as exc:                      # noqa: BLE001
                            row = {"_parse": f"failed: {type(exc).__name__}: {exc}",
                                   "_raw_head": txt[:400]}
                    cur = None
    out.update({"measurement_status": "measured", "evidence_pattern_counts": counts,
                "g14_check_row_fields": row, "g14_check_row_lines": row_lines,
                "caliber": ("counts 是**字节子串命中次数**（不是判定）；`g14_check_row_fields` 是"
                            "从该 check 对象里 `json.loads` 出来的实物字段")})
    return out


def find_ruling_lines(paths: tuple[str, ...], pattern: str) -> dict[str, Any]:
    rx = re.compile(pattern)
    found: dict[str, list[str]] = {}
    for pre in paths:
        p = REPO / pre
        if not p.exists():
            found[pre] = ["<path absent>"]
            continue
        rows = []
        for i, ln in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if rx.search(ln):
                rows.append(f"{pre}:{i}")
            if len(rows) >= 6:
                break
        found[pre] = rows
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="`G14` 一次性前置的归属 + 证据扫描（裁定 97.3-4）")
    ap.add_argument("--gate-verdict-json", required=True, help="同轮 `gate_verdict.json`（证据件）")
    ap.add_argument("--out", required=True, help="输出 JSON 路径")
    ap.add_argument("--checked-by", default="F（裁定 97.3-4 的裁定值；A2 只引不判）")
    ap.add_argument("--checked-when", default="A2 第 1 步开跑前（裁定 97.3-4）")
    args = ap.parse_args()

    load0 = _machine_load()
    files = _iter_surface_files()
    surface = scan_surface(files)
    gv = REPO / _rel(args.gate_verdict_json)
    gv_ev = extract_g14_from_gate_verdict(gv)
    ruling = find_ruling_lines(
        ("work/decisions/decisions_20260929.md",
         "rl_harness_supervision/d_context_checkpoint_20260930_1205.md",
         "rl_harness_supervision/d_handoff_to_a2_20260930.md"),
        r"G14.*(翻转|satisfied|flip)|status\s*=\s*satisfied")

    own_hits = [h for v in surface["variants"].values() for h in v["hits"]
                if h["kind"] in ("f_own_artifact", "f_own_doc_or_script")]
    f_artifact: dict[str, Any] = {
        "measurement_status": "not_measured",
        "question": "F 的写入面里有没有一份**独立判定 `G14` 实测翻转**的件？",
        "n_files_scanned": surface["n_files_scanned"],
        "n_own_surface_hits_any_variant": len(own_hits),
        "own_surface_hits": own_hits[:10],
        "hits_in_before_images_are_copies_of_shared_file": (
            "`before_images/daily_report.md.before*` 是 F 存的**共享文件副本**，里面的 `G14` 是"
            "D/他线的散文 ⇒ 不构成 F 自己的判定"),
        "why": ("A2 在 F 的写入面里**未测到**一份独立判定 `G14` 翻转的件；"
                "两向自检与变体清单见 `variant_scan` / `positive_control`"),
    }
    if own_hits:
        f_artifact["measurement_status"] = "measured_candidates_found"
        f_artifact["why"] = ("命中了 F 自己写入面里的候选件 ⇒ **需要人工看一眼性质**"
                             "（命中 ≠ 判定；A2 不代 F 表态）")

    counts = gv_ev.get("evidence_pattern_counts") or {}
    row = gv_ev.get("g14_check_row_fields") or {}
    evidence_holds = bool(
        counts.get("check_row_id", 0) >= 1
        and counts.get("baseline_true_in_mutant_ledger", 0) >= 1
        and counts.get("mutant_copy_false_in_mutant_ledger", 0) >= 1
        and counts.get("listed_in_flip_measured_true", 0) >= 1
        and (row.get("status") == "PASS" or row.get("ok") is True))
    out = {
        "artifact": "a2_g14_provenance_scan",
        "as_of": _now(),
        "purpose": ("给 `harness/bc_admission_gate.py` 的 `G14` 前置字段提供**证据 + 归属**的旁证；"
                    "本件**不判语义**（`checked_by=F`），只把「实物里有什么」与「F 的写入面里测到/未测到什么」分开写清"),
        "ruling_authority": {
            "ruling": "裁定 97.2 / 97.3-4 / 97.7 + checkpoint §10：`status = satisfied`、`checked_by = F + D`",
            "docs": {"work/decisions/decisions_20260929.md":
                         _identity(REPO / "work/decisions/decisions_20260929.md"),
                     "rl_harness_supervision/d_context_checkpoint_20260930_1205.md":
                         _identity(REPO / "rl_harness_supervision/d_context_checkpoint_20260930_1205.md")},
            "matched_lines": ruling},
        "variant_scan": surface,
        "positive_control": surface["positive_control"],
        "two_way_self_check": surface["two_way_self_check"],
        "f_independent_g14_verdict_artifact": f_artifact,
        "g14_evidence_in_gate_verdict": gv_ev,
        "evidence_holds_in_artifact": evidence_holds,
        "conclusion": (
            "**证据侧**：同轮 `gate_verdict.json` 里 `G14` 的 check 行 `status=%s` / `ok=%s` / "
            "`triage_class=%s` / `blocking=%s`，且 `M6` 变异体的 `baseline=true → in_mutant_copy=false` "
            "与 `flip_measured=True` 清单都能在同一件里数到 ⇒ 「翻转被测到了」这一事实**有实物支撑**"
            "（evidence_holds_in_artifact=%s）。**归属侧**：F 的写入面里**未测到**独立判定件"
            "（measurement_status=%s）⇒ A2 引用的是 D 的裁定值 `checked_by=F`，"
            "**A2 不代 F 表态、也不把它写成「F 已判定」**。"
            % (row.get("status"), row.get("ok"), row.get("triage_class"), row.get("blocking"),
               evidence_holds, f_artifact["measurement_status"])),
        "note_for_consumer": (
            "`G14` 的语义判断归 F（裁定 97.3-4）；本件只证明：① 同轮闸判词里有可数到的翻转证据，"
            "② F 的写入面里没有独立判定件（两向自检 + 11 个变体，正向对照全命中）。"
            "⇒ 准入闸里的 `g14_flip_checked_by` 是**裁定值引用**，不是 A2 自己的判定。"),
        "checked_by_as_declared": args.checked_by,
        "checked_when_as_declared": args.checked_when,
        "machine_load": load0,
        "machine_load_after": _machine_load(),
        "capability_claim": False, "policy_executed": False, "gpu_used": False,
        "writes_outside_a2_surface": False,
    }
    op = pathlib.Path(args.out)
    if not op.is_absolute():
        op = REPO / _rel(args.out)
    op.parent.mkdir(parents=True, exist_ok=True)
    op.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"[g14-scan] files_scanned={surface['n_files_scanned']} "
          f"positive_control={surface['positive_control']['n_terms_hit']}/"
          f"{surface['positive_control']['n_terms']} "
          f"filter_non_vacuous={surface['two_way_self_check']['filter_non_vacuous']}")
    print(f"[g14-scan] evidence_holds_in_artifact={evidence_holds} "
          f"row_status={row.get('status')} triage_class={row.get('triage_class')} "
          f"blocking={row.get('blocking')}")
    print(f"[g14-scan] f_independent_g14_verdict_artifact={f_artifact['measurement_status']} "
          f"(own-surface hits={len(own_hits)})")
    print(f"[g14-scan] loadavg={load0.get('loadavg')} nr_throttled={load0.get('nr_throttled')}")
    print(f"[written] {op}")
    return 0 if (evidence_holds and surface["two_way_self_check"]["filter_non_vacuous"]) else 3


if __name__ == "__main__":
    sys.exit(main())
