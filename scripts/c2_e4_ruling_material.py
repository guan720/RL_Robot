#!/usr/bin/env python3
"""C2 · E4 两把牙的裁定材料 + ③ 号问题（准入闸 ∧ 质量闸）方案设计的**只读**取证器。

授权与边界（照抄监管件，不自扩）
------------------------------
* 任务来源：`rl_harness_supervision/d_handoff_to_c2_20260930.md` 的
  「待命令·二（裁定 103.6-④）」+「补单·四（裁定 104）」。范围 = ① E4 两把牙
  （`Tb_scale_floor_effective` / `Tr3_near_constant_floor_material`）的**裁定材料**、
  ② ③ 号问题的**方案设计**（只出方案、不落地新牙 —— 裁定 101.1 治理冻结在）。
* 本件是**只读探针**（`declared_readonly_probe_needs_no_ticket`）：
  - 只**读**他线的文件（`harness/`、`scripts/`、`runs/`、`docs/`、`tmp/`）；
  - 只**写**自己的目录 `runs/vla/c2_e4_ruling_material_20260930/`；
  - 不 import 任何会执行判定/训练的模块（一律 `ast` 静态解析 + 字节哈希），
    因此**不可能**改到冻结面（`harness/norm_contract.py` / `scripts/c2_build_norm_stats.py`
    / 判定层 `judge_from_facts` / stats 档 `b2150e0a3264`）。
* **不重跑全量闸、不上卡、不改任何牙的极性**（裁定 104-②）。重活只有
  `gate_verdict.json`（~95 MB）的**单遍流式**哈希 + 计数（1 pass，不整件载入）。
* 三值纪律：读不到 ⇒ `measurement_status="not_measured"` + `why`，**不写 false、不猜**。
* 行号纪律：所有行号都是 `line_no_as_of`（本件 `as_of` 那一刻的值），**不是**常驻身份；
  约束性对账只用 `sha256[:12]`（裁定 98.5）。
* 裁定 46/101.3 能力声明禁令：本件 `capability_claim=false`、`policy_executed=false`、
  `gpu_used=false`、`success_metrics_collected=false`；件内任何计数都**不是** policy 指标。
"""
from __future__ import annotations

import ast
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SELF_REL = "scripts/c2_e4_ruling_material.py"
OUT_DIR_REL = "runs/vla/c2_e4_ruling_material_20260930"

N_LINES_CALIBER = ("裁定 98.5：`n_lines_splitlines` = `len(read_text().splitlines())`；"
                   "`n_lines_wc` = 换行符个数（`wc -l`）。末行无换行符 ⇒ 两者差 1。"
                   "**裸 `n_lines` 不得再出现在任何广播或对账里**；"
                   "**对账的唯一约束性判据 = `sha256[:12]`**，行数只作辅证且必须点名口径。")

# 冻结面身份（裁定 101.2 / 104-②）：本件只**核**它们没被动过，不写它们。
FROZEN_EXPECTED = {
    "harness/norm_contract.py": "91795179de7e",
    "scripts/c2_build_norm_stats.py": "1bc468012cff",
    "scripts/c2_gate_norm_contract.py": "c9445a9a7f6a",
}

E4_TEETH = ("Tb_scale_floor_effective", "Tr3_near_constant_floor_material")
SUBSTITUTE_HARD_TEETH = ("Tz_denom_strictly_positive", "Tres_per_dim_resolution_floor")
THRESHOLD_FIELDS = ("min_bins_occupied", "floor_materiality_fraction",
                    "min_bins_occupied_non_near_constant", "min_bins_occupied_near_constant",
                    "warn_bins_occupied_near_constant", "clip_ratio_cap",
                    "start_pose_oob_dims_cap", "near_constant_rel_tol")


def sha12(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def identity(rel: str | pathlib.Path, *, expected_sha12: str | None = None) -> dict:
    """一件文件的身份块（measured / not_measured，不猜）。"""
    p = pathlib.Path(rel)
    if not p.is_absolute():
        p = REPO / rel
    out: dict = {"path": str(rel), "measurement_status": "not_measured"}
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
        out.update({
            "measurement_status": "measured",
            "n_bytes": p.stat().st_size,
            "n_lines_wc": txt.count("\n"),
            "n_lines_splitlines": len(txt.splitlines()),
            "ends_with_newline": txt.endswith("\n"),
            "sha256_12": sha12(p),
            "mtime_iso": datetime.datetime.fromtimestamp(
                p.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
            "n_lines_caliber": N_LINES_CALIBER,
        })
        if expected_sha12 is not None:
            out["expected_sha256_12"] = expected_sha12
            out["matches_expected"] = bool(out["sha256_12"] == expected_sha12)
    except Exception as exc:                                          # noqa: BLE001
        out["why"] = f"{type(exc).__name__}: {exc}"
        out["red_line"] = "absence_of_measurement_is_not_measurement_of_absence"
    return out


def read_json(rel: str | pathlib.Path) -> tuple[dict | None, dict]:
    p = pathlib.Path(rel)
    if not p.is_absolute():
        p = REPO / rel
    idn = identity(rel)
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace")), idn
    except Exception as exc:                                          # noqa: BLE001
        idn["json_parse"] = {"measurement_status": "not_measured",
                             "why": f"{type(exc).__name__}: {exc}"}
        return None, idn


def _src_seg(src: str, node: ast.AST) -> str | None:
    try:
        seg = ast.get_source_segment(src, node)
    except Exception:                                                 # noqa: BLE001
        seg = None
    return (seg if seg is None else " ".join(seg.split()))


# ══════════════════ Part A-1：牙的静态解析（AST，不 import）══════════════════
def parse_teeth(src_rel: str) -> dict:
    """从 `harness/norm_contract.py` 静态取出 E4 两把牙 + 两把替代硬红的**判据形状**。

    为什么用 AST 不用 grep：`blocking=` 的实参可能是表达式（`bool(mainline)`）也可能
    **缺席**（取 `tooth()` 的默认 `True`）⇒ 只有 AST 能区分「显式 False」与「没给」。
    裁定 93.1-1 的实质就是这一区分（D 亲核过 `A4_tb_has_no_blocking_kwarg`）。
    """
    p = REPO / src_rel
    out: dict = {"source": identity(src_rel), "teeth": {}, "tooth_helper": {},
                 "measurement_status": "not_measured"}
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except Exception as exc:                                          # noqa: BLE001
        out["why"] = f"{type(exc).__name__}: {exc}"
        return out

    # ---- `tooth()` 的定义：默认 `blocking` 与 status 机制行 ----
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "tooth":
            defaults = node.args.defaults
            kw_names = [a.arg for a in node.args.args][-len(defaults):] if defaults else []
            dflt = {}
            for name, dnode in zip(kw_names, defaults):
                dflt[name] = (_src_seg(src, dnode) if not isinstance(dnode, ast.Constant)
                              else dnode.value)
            status_line = None
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    seg = _src_seg(src, sub) or ""
                    if "RED" in seg and "WARN" in seg and "status" in seg:
                        status_line = {"line_no_as_of": sub.lineno, "source_segment": seg[:300]}
                        break
            out["tooth_helper"] = {
                "measurement_status": "measured",
                "def_line_no_as_of": node.lineno,
                "defaults": dflt,
                "blocking_default": dflt.get("blocking", "NOT_FOUND"),
                "status_mechanism": status_line,
                "semantics": ("`status = N_A if not applies_when else (PASS if ok else "
                              "(RED if blocking else WARN))` ⇒ **`blocking=False` 的牙在 "
                              "`ok=False` 时出 `WARN`，不可能出 `RED`**（这是下面四颗牙的"
                              "极性判据的唯一出处，不靠散文）。"),
            }
            break

    wanted = set(E4_TEETH) | set(SUBSTITUTE_HARD_TEETH) | {"Tp5_bc_admission_requires_formal40_bc_source",
                                                           "Tbcad_admission_requires_green_gate"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        fname = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
        if fname != "tooth" or not node.args:
            continue
        first = node.args[0]
        tid = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
        if tid is None or tid not in wanted:
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        rec = {
            "measurement_status": "measured",
            "tooth_id": tid,
            "call_line_no_as_of": node.lineno,
            "name_arg_source": _src_seg(src, node.args[1]) if len(node.args) > 1 else None,
            "blocking_kwarg_present": "blocking" in kw,
            "blocking_kwarg_source": (_src_seg(src, kw["blocking"]) if "blocking" in kw else None),
            "applies_when_kwarg_source": (_src_seg(src, kw["applies_when"]) if "applies_when" in kw else None),
            "blocking_reason_kwarg_source": (_src_seg(src, kw["blocking_reason"])
                                             if "blocking_reason" in kw else None),
        }
        # 有效 blocking = 显式实参 or `tooth()` 的默认
        dflt = (out["tooth_helper"].get("defaults") or {}).get("blocking", True)
        if "blocking" in kw:
            bnode = kw["blocking"]
            rec["blocking_effective"] = (bnode.value if isinstance(bnode, ast.Constant) else "EXPRESSION")
        else:
            rec["blocking_effective"] = dflt
            rec["blocking_effective_origin"] = "tooth() 的默认值（调用处没给实参）"
        rec["emits_red_when_not_ok"] = (rec["blocking_effective"] is True)
        rec["authority_arg_source"] = (_src_seg(src, node.args[5]) if len(node.args) > 5 else None)
        out["teeth"][tid] = rec

    out["measurement_status"] = "measured"
    out["n_teeth_found"] = len(out["teeth"])
    out["teeth_not_found"] = sorted(wanted - set(out["teeth"]))
    return out


# ══════════════════ Part A-2：阈值与溯源状态（AST）══════════════════
def parse_thresholds(src_rel: str) -> dict:
    p = REPO / src_rel
    out: dict = {"source": identity(src_rel), "fields": {}, "provenance": {},
                 "measurement_status": "not_measured"}
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except Exception as exc:                                          # noqa: BLE001
        out["why"] = f"{type(exc).__name__}: {exc}"
        return out
    cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ContractThresholds":
            cls = node
            break
    if cls is None:
        out["why"] = "ContractThresholds 类未找到"
        return out
    out["class_line_no_as_of"] = cls.lineno
    for st in cls.body:
        # 注意：这里**不许用 `continue`** —— `provenance` 本身不在 `THRESHOLD_FIELDS` 里，
        # 提前 continue 会把下面那段（阈值溯源状态的唯一约束性出处）整块跳掉。已踩过一次。
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) \
                and st.target.id in THRESHOLD_FIELDS:
            name = st.target.id
            out["fields"][name] = {
                "line_no_as_of": st.lineno,
                "default_source": _src_seg(src, st.value) if st.value is not None else None,
                "default_is_literal": isinstance(st.value, ast.Constant),
                "inline_comment_note": ("源码同行/上文的注释是**散文**，不作为判据；"
                                        "约束性判据 = `provenance` 字典里的状态串"),
            }
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) \
                and st.target.id == "provenance" and isinstance(st.value, ast.Call):
            for kwn in st.value.keywords:
                if kwn.arg == "lambda" or True:
                    seg = _src_seg(src, kwn.value)
                    if not seg:
                        continue
                    try:
                        lit = ast.literal_eval(kwn.value.body if isinstance(kwn.value, ast.Lambda)
                                               else kwn.value)
                    except Exception:                                 # noqa: BLE001
                        lit = None
                    if isinstance(lit, dict):
                        for kk, vv in lit.items():
                            out["provenance"][kk] = {"status_string": vv,
                                                     "line_no_as_of": kwn.value.lineno}
    # provenance 的 lambda 形式：`field(default_factory=lambda: {...})`
    if not out["provenance"]:
        m = re.search(r'"provenance"\s*:\s*\{', src)
        if m:
            out["provenance_note"] = "正则兜底未实现；provenance 取空 ⇒ not_measured"
    out["measurement_status"] = ("measured" if out["fields"] else "not_measured")
    if out["measurement_status"] == "not_measured":
        out["why"] = "没有取到任何阈值字段"
    # 红线判据（`redline_provenance_discipline`）：状态串是否属于「已定标」族
    CALIBRATED_TOKENS = ("d_calibrated", "ruling_51_1_c_hard")
    UNCALIBRATED_TOKENS = ("registered_measurement_not_a_judgment", "proposed_pending_s1",
                           "declared_only", "derived_from_min_F1_candidate")
    for name, blk in out["fields"].items():
        st = (out["provenance"].get(name) or {}).get("status_string")
        blk["provenance_status_string"] = st
        if st is None:
            blk["calibration_class"] = "not_measured"
        elif any(t in st for t in CALIBRATED_TOKENS):
            blk["calibration_class"] = "calibrated"
        elif any(t in st for t in UNCALIBRATED_TOKENS):
            blk["calibration_class"] = "uncalibrated_or_measurement_only"
        else:
            blk["calibration_class"] = "unclassified"
        blk["may_block_per_redline_provenance_discipline"] = (blk["calibration_class"] == "calibrated")
    return out


# ══════════════════ Part A-3：上一轮权威闸跑的实测判词 ══════════════════
def gate_run_facts(run_dir_rel: str) -> dict:
    out: dict = {"gate_run_dir": run_dir_rel, "measurement_status": "not_measured"}
    rd = REPO / run_dir_rel
    if not rd.is_dir():
        out["why"] = f"目录不在盘：{run_dir_rel}"
        return out
    out["arm_mainline_status"] = identity(f"{run_dir_rel}/arm_mainline/mainline_status.json")
    out["gate_verdict"] = identity(f"{run_dir_rel}/gate_verdict.json")
    out["matrix"] = identity(f"{run_dir_rel}/arm_mainline/matrix.json")

    # ---- 单遍流式：gate_verdict.json 的顶层判词 + 关键字计数（不整件载入）----
    gv = rd / "gate_verdict.json"
    if gv.is_file():
        keys = (b'"verdict_class1"', b'verdict_class1', b'"triage_class"', b'triage_class',
                b'Tbcad_admission_requires_green_gate', b'"blocking": true', b'"blocking": false',
                b'"id":')
        counts = {k.decode(): 0 for k in keys}
        h = hashlib.sha256()
        tail = b""
        first_verdict = None
        n_bytes = 0
        try:
            with gv.open("rb") as fh:
                while True:
                    chunk = fh.read(1 << 22)
                    if not chunk:
                        break
                    n_bytes += len(chunk)
                    h.update(chunk)
                    buf = tail + chunk
                    for k in keys:
                        counts[k.decode()] += buf.count(k)
                    if first_verdict is None:
                        m = re.search(rb'"verdict"\s*:\s*"([A-Z_]+)"', buf[:4096])
                        if m:
                            first_verdict = m.group(1).decode()
                    # 跨块边界的安全重叠（最长 key 远小于 64 B）
                    tail = chunk[-64:]
            # `tail` 里的 key 会被下一轮重复计一次 ⇒ 用重叠长度做上界披露，不静默
            out["gate_verdict_stream"] = {
                "measurement_status": "measured", "n_bytes": n_bytes,
                "sha256_12": h.hexdigest()[:12], "n_passes": 1,
                "top_level_verdict_first_occurrence": first_verdict,
                "substring_counts": counts,
                "count_caliber": ("子串出现次数（`bytes.count`），**不是** JSON 语义计数；"
                                  "64 B 跨块重叠会让边界上的命中最多重复计一次 ⇒ 计数是"
                                  "**上界**，只用于「存在性/量级」，不用于精确对账。"),
                "note": ("整件 ~95 MB，**不 json.load**（裁定 104-②：重 CPU 排队）。"
                         "精确判词以臂内件/matrix 为准。"),
            }
        except Exception as exc:                                      # noqa: BLE001
            out["gate_verdict_stream"] = {"measurement_status": "not_measured",
                                          "why": f"{type(exc).__name__}: {exc}"}

    # ---- 臂内件：WARN 计数、盲维登记、bc_admission 存量标签 ----
    ms, ms_id = read_json(f"{run_dir_rel}/arm_mainline/mainline_status.json")
    out["arm_mainline_status_identity_recheck"] = ms_id
    if ms is None:
        out["why"] = "臂内件解析失败"
        return out
    out["measurement_status"] = "measured"
    mf = ms.get("mainline_finding") or {}
    finding_txt = str(mf.get("finding") or "")
    m = re.search(r"本臂 WARN 计数 (\{[^}]*\})", finding_txt)
    warn_counts = None
    if m:
        try:
            warn_counts = ast.literal_eval(m.group(1))
        except Exception:                                             # noqa: BLE001
            warn_counts = None
    out["warn_counts_from_mainline_finding"] = {
        "measurement_status": ("measured" if warn_counts is not None else "not_measured"),
        "value": warn_counts,
        "source": "臂内件 `mainline_finding.finding` 散文里的字典字面值（AST 解析，不手抄）",
        "why": (None if warn_counts is not None else "散文里没有可解析的 WARN 计数字典"),
    }
    hb = ms.get("heldout_per_dim_blindness_ruling_94_3") or {}
    out["heldout_blindness_ruling_94_3"] = {
        "measurement_status": hb.get("measurement_status", "not_measured"),
        "n_rows": hb.get("n_rows"), "n_rows_measured": hb.get("n_rows_measured"),
        "n_dims": hb.get("n_dims"), "blind_dim_threshold": hb.get("blind_dim_threshold"),
        "blind_dim_threshold_status": hb.get("blind_dim_threshold_status"),
        "n_distinct_heldout_patterns": hb.get("n_distinct_heldout_patterns"),
        "heldout_bins_occupied_per_dim_distinct": hb.get("heldout_bins_occupied_per_dim_distinct"),
        "correctness_blind_dims_union": hb.get("correctness_blind_dims_union"),
        "source_field": "heldout_per_dim_blindness_ruling_94_3（裁定 94.3 的两字段登记，Ⅱ 类不阻塞）",
    }
    out["arm_bc_admission_stored_label"] = ms.get("bc_admission")
    out["arm_gate_verdict_reference"] = ms.get("gate_verdict_reference")
    out["arm_checked_path_sha256_12"] = ms.get("checked_path_sha256_12")
    out["arm_stats_provenance"] = ms.get("stats_provenance")
    out["arm_n_frames"] = ms.get("n_frames")
    out["arm_n_episodes"] = ms.get("n_episodes")
    out["arm_next_required_action_verbatim"] = ms.get("next_required_action")

    # ---- matrix：逐行取四颗牙的 status / blocking / 不足维（精确口径，替代散文）----
    mx, mx_id = read_json(f"{run_dir_rel}/arm_mainline/matrix.json")
    out["matrix_identity_recheck"] = mx_id
    if mx is not None:
        rows = None
        if isinstance(mx, dict):
            for cand in ("rows", "matrix", "main_rows", "results"):
                if isinstance(mx.get(cand), list):
                    rows = mx[cand]
                    out["matrix_rows_key"] = cand
                    break
            if rows is None:
                out["matrix_top_keys"] = list(mx.keys())[:40]
        elif isinstance(mx, list):
            rows = mx
            out["matrix_rows_key"] = "<top-level list>"
        per_tooth: dict = {}
        n_rows_scanned = 0
        prov_hist: dict = {}
        wanted_ids = set(E4_TEETH) | set(SUBSTITUTE_HARD_TEETH)
        if rows:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                n_rows_scanned += 1
                prov = str(row.get("stats_provenance"))
                prov_hist[prov] = prov_hist.get(prov, 0) + 1
                row_tag = "|".join(str(row.get(k)) for k in ("case", "family", "coef"))
                meta = {"row_tag": row_tag, "arm": row.get("arm"),
                        "mainline": row.get("mainline"), "consumer": row.get("consumer"),
                        "stats_provenance": prov,
                        "row_verdict": row.get("verdict"),
                        "eval_frames_are_held_out": row.get("eval_frames_are_held_out"),
                        "eval_scope": row.get("eval_scope")}
                teeth = row.get("teeth") or row.get("checks") or []
                if isinstance(teeth, dict):
                    teeth = list(teeth.values())
                for t in teeth:
                    if not isinstance(t, dict):
                        continue
                    tid = t.get("id")
                    if tid not in wanted_ids:
                        continue
                    blk = per_tooth.setdefault(tid, {
                        "n_rows": 0, "status_histogram": {}, "blocking_histogram": {},
                        "ok_histogram": {}, "observed_samples_non_pass": [],
                        "dims_below_union": [], "blocking_reason_sample": None,
                        "by_provenance": {}, "formal40_rows": []})
                    blk["n_rows"] += 1
                    st = str(t.get("status"))
                    blk["status_histogram"][st] = blk["status_histogram"].get(st, 0) + 1
                    bl = str(t.get("blocking"))
                    blk["blocking_histogram"][bl] = blk["blocking_histogram"].get(bl, 0) + 1
                    okk = str(t.get("ok"))
                    blk["ok_histogram"][okk] = blk["ok_histogram"].get(okk, 0) + 1
                    sub = blk["by_provenance"].setdefault(prov, {"n_rows": 0, "status_histogram": {},
                                                                 "blocking_histogram": {}})
                    sub["n_rows"] += 1
                    sub["status_histogram"][st] = sub["status_histogram"].get(st, 0) + 1
                    sub["blocking_histogram"][bl] = sub["blocking_histogram"].get(bl, 0) + 1
                    if prov == "formal40_bc_source":
                        dims_here: list = []
                        obs = str(t.get("observed") or "")
                        for mm in re.finditer(r"不足维[^\[]*(\[[0-9,\s]*\])", obs):
                            try:
                                dims_here = sorted(set(dims_here) | set(ast.literal_eval(mm.group(1))))
                            except Exception:                         # noqa: BLE001
                                pass
                        blk["formal40_rows"].append({**meta, "tooth_status": st,
                                                     "tooth_ok": t.get("ok"),
                                                     "tooth_blocking": t.get("blocking"),
                                                     "dims_below": dims_here,
                                                     "observed": obs[:300]})
                    obs = str(t.get("observed") or "")
                    if st not in ("PASS", "N_A") and len(blk["observed_samples_non_pass"]) < 6:
                        blk["observed_samples_non_pass"].append({**meta, "status": st,
                                                                 "observed": obs[:400]})
                    for mm in re.finditer(r"不足维[^\[]*(\[[0-9,\s]*\])", obs):
                        try:
                            for dd in ast.literal_eval(mm.group(1)):
                                if dd not in blk["dims_below_union"]:
                                    blk["dims_below_union"].append(dd)
                        except Exception:                             # noqa: BLE001
                            pass
                    if blk["blocking_reason_sample"] is None and t.get("blocking_reason"):
                        blk["blocking_reason_sample"] = str(t["blocking_reason"])[:600]
            for blk in per_tooth.values():
                blk["dims_below_union"] = sorted(blk["dims_below_union"])
                f40 = blk["formal40_rows"]
                blk["formal40_summary"] = {
                    "n_rows": len(f40),
                    "status_histogram": {s: sum(1 for r in f40 if r["tooth_status"] == s)
                                         for s in sorted({r["tooth_status"] for r in f40})},
                    "blocking_values": sorted({str(r["tooth_blocking"]) for r in f40}),
                    "dims_below_union": sorted({dd for r in f40 for dd in r["dims_below"]}),
                    "caliber": ("**权威档**：`stats_provenance == formal40_bc_source` 的行"
                                "（= BC 真正要吃的那一档）；其余行是诊断/stress/必红分支臂，"
                                "对它们判红属极性错（裁定 72-2）⇒ 分开报，不混算。"),
                }
        out["matrix_teeth_scan"] = {
            "measurement_status": ("measured" if per_tooth else "not_measured"),
            "n_rows_scanned": n_rows_scanned,
            "rows_by_stats_provenance": prov_hist,
            "why": (None if per_tooth else "matrix 里没有可识别的 teeth/checks 列表"),
            "per_tooth": per_tooth,
        }
    return out


# ══════════════════ Part B：③ 号问题（准入闸 ∧ 质量闸）的落地事实 ══════════════════
def parse_bc_coupling() -> dict:
    out: dict = {"measurement_status": "measured"}
    gate_rel = "harness/bc_admission_gate.py"
    entry_rel = "scripts/a2_step1_bc_overfit.py"
    watcher_rel = "tmp/a2_step1_watcher.sh"
    out["identities"] = {"bc_admission_gate": identity(gate_rel),
                         "a2_step1_entry": identity(entry_rel),
                         "a2_step1_watcher": identity(watcher_rel),
                         "norm_contract": identity("harness/norm_contract.py")}

    # ---- 静态：准入判据的三个关键点 ----
    try:
        gsrc = (REPO / gate_rel).read_text(encoding="utf-8", errors="replace")
        glines = gsrc.splitlines()
    except Exception as exc:                                          # noqa: BLE001
        out["bc_admission_gate_source"] = {"measurement_status": "not_measured", "why": str(exc)}
        glines, gsrc = [], ""

    def find_lines(pat: str, limit: int = 6) -> list[dict]:
        rx = re.compile(pat)
        hits = []
        for i, ln in enumerate(glines, start=1):
            if rx.search(ln):
                hits.append({"line_no_as_of": i, "text": ln.strip()[:240]})
                if len(hits) >= limit:
                    break
        return hits

    out["gate_call_site_of_c2_bc_admission"] = {
        "measurement_status": ("measured" if glines else "not_measured"),
        "hits": find_lines(r"=\s*bc_admission\("),
        "meaning": ("`harness/bc_admission_gate.py` **确实 import 并调用** C2 契约层的 "
                    "`bc_admission()`（不重造判据）⇒ ③ 号问题的「耦合」在码层已存在。"),
    }
    out["gate_r3_verdict_class1_read_from_artifact"] = {
        "hits": find_lines(r'verdict_class1_not_measured|verdict_class1_from_artifact'
                           r'|verdict_class1_not_substituted_by_top_level|verdict_class1_not_pass'),
        "meaning": ("R3：`verdict_class1` **只从实物读**，缺失 ⇒ `not_measured` ⇒ 拒；"
                    "且不许拿顶层 `verdict` 顶替。"),
    }
    out["gate_bc_blocking_caliber_literal"] = {
        "hits": find_lines(r'"bc_blocking_caliber"\s*:'),
    }
    out["gate_stats_recompute"] = {
        "hits": find_lines(r'stats_sha256_mismatch|stats_unreadable|stats_not_inside_declared_run_dir'
                           r'|stats_provenance_declaration_mismatch|stats_representation_version_mismatch'),
        "meaning": "stats 档的身份由消费方**自己复算**并对账（不是只读声明）。",
    }
    out["gate_npz_recompute"] = {
        "hits": find_lines(r'npz_sha256_mismatch|npz_unreadable|npz_identity_not_declared'
                           r'|npz_declaration_disagrees_with_arm'),
    }
    out["gate_crosscheck_leg"] = {
        "hits": find_lines(r'crosscheck_broadcast_sources|broadcast_sources_disagree'),
        "blocking_condition_verbatim": None,
    }
    for i, ln in enumerate(glines, start=1):
        if 'cross.get("measurement_status") == "measured"' in ln:
            out["gate_crosscheck_leg"]["blocking_condition_verbatim"] = {
                "line_no_as_of": i, "text": " ".join(glines[i - 1:i + 5])[:600].strip(),
                "reading": ("**只有 `measured ∧ not agree` 才阻塞**；`not_measured`（只给一件载体）"
                            "既不阻塞、也不进 `not_measured_items`、也不出 warning ⇒ 这条腿"
                            "在单载体稳态下**永不触发**，而判定件仍自称 `measured`。"),
            }
            break
    out["gate_broadcast_doc_default"] = {
        "hits": find_lines(r"BROADCAST_DOC_DEFAULT\s*="),
        "meaning": "广播件是**稳定名活件**（消费方读的是「当下这份」，不是「裁定那一刻那份」）。",
    }

    # ---- 静态：Step-1 入口的阶段门 ----
    try:
        esrc = (REPO / entry_rel).read_text(encoding="utf-8", errors="replace")
        elines = esrc.splitlines()
    except Exception as exc:                                          # noqa: BLE001
        out["entry_source"] = {"measurement_status": "not_measured", "why": str(exc)}
        elines = []
    out["entry_stage_gate"] = {
        "measurement_status": ("measured" if elines else "not_measured"),
        "hits": [{"line_no_as_of": i, "text": ln.strip()[:240]}
                 for i, ln in enumerate(elines, start=1)
                 if re.search(r'if "admission" in stages|EXIT_REFUSED_ADMISSION|ALL_STAGES\s*=', ln)][:8],
        "meaning": ("`main()` 里**唯一**的准入闸入口是 `if \"admission\" in stages:`；"
                    "`stage_train` / `stage_rollout` 内部**没有**任何 admission 复检"
                    "（下方 `entry_admission_references_by_region` 是穷举证据）。"),
    }
    refs = [{"line_no_as_of": i, "text": ln.strip()[:200]}
            for i, ln in enumerate(elines, start=1) if "admission" in ln.lower()]
    out["entry_admission_references_by_region"] = {
        "n_hits": len(refs), "hits": refs,
        "caliber": "对 `scripts/a2_step1_bc_overfit.py` 全文小写不敏感搜 `admission` 的**穷举**命中行",
    }
    out["entry_report_stage_binding"] = {
        "hits": [{"line_no_as_of": i, "text": ln.strip()[:240]}
                 for i, ln in enumerate(elines, start=1)
                 if re.search(r'glob\("BC_ADMISSION_STEP1_|adm_p\[-1\]|stable = out_dir', ln)][:8],
        "meaning": "`stage_report` 用 `sorted(glob(...))[-1]` 绑准入件 ⇒ **glob-latest**，不是同次调用产出。",
    }

    # ---- 守望器实际会起跑的命令 ----
    try:
        wsrc = (REPO / watcher_rel).read_text(encoding="utf-8", errors="replace")
        wlines = wsrc.splitlines()
    except Exception as exc:                                          # noqa: BLE001
        out["watcher_source"] = {"measurement_status": "not_measured", "why": str(exc)}
        wlines = []
    launch = []
    for i, ln in enumerate(wlines, start=1):
        if "--stages" in ln:
            launch.append({"line_no_as_of": i, "text": ln.strip()[:300]})
    stages_tokens = sorted(set(re.findall(r"--stages\s+([A-Za-z_,]+)", "\n".join(wlines))))
    out["watcher_launch_command"] = {
        "measurement_status": ("measured" if wlines else "not_measured"),
        "hits": launch,
        "stages_tokens_found": stages_tokens,
        "admission_in_stages": any("admission" in t.split(",") for t in stages_tokens),
        "caliber": ("对守望器脚本全文搜 `--stages`；`admission_in_stages` = 任一 token 的逗号分割里"
                    "含 `admission`。**这是「即将起跑的那次调用会不会复检准入」的直接判据**。"),
    }
    return out


def admission_artifact_facts(run_dir_rel: str) -> dict:
    out: dict = {"run_dir": run_dir_rel, "measurement_status": "not_measured"}
    rd = REPO / run_dir_rel
    if not rd.is_dir():
        out["why"] = f"目录不在盘：{run_dir_rel}"
        return out
    cands = sorted(rd.glob("BC_ADMISSION_STEP1_*.json"))
    out["n_timestamped_admission_artifacts"] = len(cands)
    out["artifacts"] = [identity(p.relative_to(REPO).as_posix()) for p in cands]
    out["stable_copy"] = identity(f"{run_dir_rel}/BC_ADMISSION_STEP1.json")
    if not cands:
        out["why"] = "没有带时间戳的准入件"
        return out
    latest = cands[-1]
    out["glob_latest_that_report_stage_would_bind"] = identity(latest.relative_to(REPO).as_posix())
    d, idn = read_json(latest.relative_to(REPO).as_posix())
    out["latest_identity_recheck"] = idn
    if d is None:
        out["why"] = "最新准入件解析失败"
        return out
    out["measurement_status"] = "measured"
    out["latest"] = {
        "as_of": d.get("as_of"),
        "admitted": d.get("admitted"),
        "admitted_and_rule": d.get("admitted_and_rule"),
        "blocking_refusals": d.get("blocking_refusals"),
        "not_measured_items": d.get("not_measured_items"),
        "warnings": d.get("warnings"),
        "producer": d.get("producer"),
        "gpu_used": d.get("gpu_used"), "policy_executed": d.get("policy_executed"),
        "capability_claim": d.get("capability_claim"),
        "blind_dims": d.get("blind_dims"), "observed_dims": d.get("observed_dims"),
    }
    c = d.get("c2_broadcast_consumption") or {}
    dec = c.get("decision") or {}
    out["consume_level"] = {
        "as_of": c.get("as_of"),
        "admitted": c.get("admitted"),
        "not_measured_items": c.get("not_measured_items"),
        "extra_blocking": c.get("extra_blocking"),
        "blocking_reason_codes": c.get("blocking_reason_codes"),
        "warnings_extra_reason_codes": [w.get("reason_code") for w in (c.get("warnings_extra") or [])],
        "broadcast_crosscheck": c.get("broadcast_crosscheck"),
        "parse_errors": c.get("parse_errors"),
        "declaration_source": c.get("declaration_source"),
        "npz_crosscheck": c.get("npz_crosscheck"),
        "bc_stats_input_recomputed_sha256_12": ((c.get("bc_stats_input") or {}).get("recomputed") or {}).get("sha256_12"),
        "bc_stats_input_declared_sha256_12": ((c.get("bc_stats_input") or {}).get("declared") or {}).get("sha256_12_declared"),
        "bc_stats_input_from_artifact": (c.get("bc_stats_input") or {}).get("from_artifact"),
        "authorization_to_start_bc": c.get("authorization_to_start_bc"),
        "authorization_note": c.get("authorization_note"),
        "broadcast_doc_identity_as_consumed": (c.get("parse") or {}).get("doc_identity"),
        "declaration_as_parsed": (c.get("parse") or {}).get("declaration"),
    }
    out["decision_level"] = {
        "admitted": dec.get("admitted"),
        "decision_measurement_status": dec.get("decision_measurement_status"),
        "not_measured_items": dec.get("not_measured_items"),
        "blocking_refusals": dec.get("blocking_refusals"),
        "warnings": dec.get("warnings"),
        "bc_blocking_caliber": dec.get("bc_blocking_caliber"),
        "checks_keys": sorted((dec.get("checks") or {}).keys()),
        "c2_bc_admission": (dec.get("checks") or {}).get("c2_bc_admission"),
        "verdict_class1_from_artifact": (dec.get("checks") or {}).get("verdict_class1_from_artifact"),
        "gate_verdict_identity_scanned": ((dec.get("checks") or {}).get("gate_verdict_identity") or {}).get("scanned"),
    }
    # ---- 广播件漂移：前缀 sha 复算（证明「纯追加」而不是「被改写」）----
    consumed = ((c.get("parse") or {}).get("doc_identity") or {})
    csha = consumed.get("sha256_12")
    cnb = consumed.get("n_bytes")
    doc_rel = (c.get("declaration_source") or {}).get("doc_path")
    drift: dict = {"measurement_status": "not_measured", "consumed_sha256_12": csha,
                   "consumed_n_bytes": cnb, "broadcast_doc_path": doc_rel}
    if doc_rel and csha and isinstance(cnb, int):
        dp = REPO / doc_rel
        cur = identity(doc_rel)
        drift["current_identity"] = cur
        if cur.get("measurement_status") == "measured":
            try:
                raw = dp.read_bytes()
                prefix_sha = hashlib.sha256(raw[:cnb]).hexdigest()[:12]
                drift.update({
                    "measurement_status": "measured",
                    "prefix_n_bytes_used": cnb,
                    "prefix_sha256_12": prefix_sha,
                    "prefix_sha_equals_consumed_sha": bool(prefix_sha == csha),
                    "current_n_bytes": len(raw),
                    "n_bytes_appended": len(raw) - cnb,
                    "conclusion": ("**纯追加**：当前件的前 %d 字节 sha256[:12] = %s = A2 消费那一刻的整件 sha "
                                   "⇒ A2 那次准入读的字节**一个都没被改**，追加发生在消费之后。"
                                   % (cnb, prefix_sha)) if prefix_sha == csha else
                                  ("**不是纯追加**：前缀 sha 与消费时不符 ⇒ A2 读过的字节已被改动，"
                                   "那次准入的证据基础失效，必须重跑准入。"),
                })
            except Exception as exc:                                  # noqa: BLE001
                drift["why"] = f"{type(exc).__name__}: {exc}"
    out["broadcast_doc_drift"] = drift

    # ---- 生产者版本漂移 ----
    prod = d.get("producer") or {}
    cur_entry = identity("scripts/a2_step1_bc_overfit.py")
    out["producer_version_drift"] = {
        "measurement_status": ("measured" if prod.get("sha256_12") else "not_measured"),
        "producer_script": prod.get("script"),
        "producer_sha256_12": prod.get("sha256_12"),
        "producer_bytes": prod.get("bytes"),
        "producer_n_lines_wc": prod.get("n_lines_wc"),
        "current_entry_sha256_12": cur_entry.get("sha256_12"),
        "current_entry_bytes": cur_entry.get("n_bytes"),
        "current_entry_n_lines_wc": cur_entry.get("n_lines_wc"),
        "current_entry_mtime": cur_entry.get("mtime_iso"),
        "same_version": bool(prod.get("sha256_12") and prod.get("sha256_12") == cur_entry.get("sha256_12")),
        "before_image_present": identity(
            "runs/vla/a2_s3_bc_overfit_20260930/before_images/"
            f"a2_step1_bc_overfit.py.before_{prod.get('sha256_12')}").get("measurement_status") == "measured",
        "before_image_identity": identity(
            "runs/vla/a2_s3_bc_overfit_20260930/before_images/"
            f"a2_step1_bc_overfit.py.before_{prod.get('sha256_12')}"),
    }
    return out


def negative_legs(patterns: list[str]) -> dict:
    out = {"measurement_status": "measured", "legs": []}
    import glob as _glob
    for pat in patterns:
        for d in sorted(_glob.glob(str(REPO / pat))):
            dp = pathlib.Path(d)
            for f in sorted(dp.glob("BC_ADMISSION_DECISION_*.json")) + sorted(dp.glob("BC_ADMISSION_STEP1_*.json")):
                rec = {"dir": dp.relative_to(REPO).as_posix(),
                       "artifact": f.relative_to(REPO).as_posix(),
                       "sha256_12": sha12(f), "n_bytes": f.stat().st_size}
                try:
                    j = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                    rec["admitted"] = j.get("admitted")
                    rec["consume_admitted"] = (j.get("c2_broadcast_consumption") or {}).get("admitted")
                    rec["blocking_reason_codes"] = (j.get("c2_broadcast_consumption") or {}).get("blocking_reason_codes")
                    rec["not_measured_items"] = (j.get("c2_broadcast_consumption") or {}).get("not_measured_items")
                    rec["measurement_status"] = "measured"
                except Exception as exc:                              # noqa: BLE01
                    rec["measurement_status"] = "not_measured"
                    rec["why"] = f"{type(exc).__name__}: {exc}"
                out["legs"].append(rec)
    out["n_legs"] = len(out["legs"])
    out["n_admitted_true"] = sum(1 for r in out["legs"] if r.get("admitted") is True)
    out["n_admitted_false"] = sum(1 for r in out["legs"] if r.get("admitted") is False)
    return out


# ══════════════════ Part C：搬迁的盘上事实 vs 待命令·二 的措辞 ══════════════════
def move_facts() -> dict:
    out: dict = {"measurement_status": "not_measured"}
    mr_rel = "runs/vla/c2_docs_ruling99/MOVE_RECORD.json"
    rp_rel = "runs/vla/c2_docs_ruling99/REPOINT_RECORD.json"
    out["move_record_identity"] = identity(mr_rel)
    out["repoint_record_identity"] = identity(rp_rel)
    out["before_images_dir"] = {
        "measurement_status": "measured" if (REPO / "runs/vla/c2_docs_ruling99/before_images").is_dir()
        else "not_measured",
        "n_entries": (len(list((REPO / "runs/vla/c2_docs_ruling99/before_images").iterdir()))
                      if (REPO / "runs/vla/c2_docs_ruling99/before_images").is_dir() else None),
    }
    mr, _ = read_json(mr_rel)
    if mr is None:
        out["why"] = "MOVE_RECORD.json 读不到/解析失败"
        return out
    out["measurement_status"] = "measured"
    summ = mr.get("summary") or {}
    items = mr.get("items") or []
    out["move_record_summary"] = summ
    out["move_record_n_items"] = len(items)
    out["move_record_item_status_histogram"] = {}
    for it in items:
        st = str(it.get("status") or it.get("result") or "?")
        out["move_record_item_status_histogram"][st] = \
            out["move_record_item_status_histogram"].get(st, 0) + 1
    out["moved_target_dir_exists"] = bool((REPO / "runs/vla/c2_docs_ruling99").is_dir())
    out["n_files_in_target_dir"] = (len(list((REPO / "runs/vla/c2_docs_ruling99").rglob("*")))
                                    if out["moved_target_dir_exists"] else None)
    out["caliber"] = ("盘上事实 = 搬迁**已执行完**（`MOVE_RECORD.json` 在盘、目标目录有件）；"
                      "而 `d_handoff_to_c2_20260930.md` 的「待命令·二」仍写「搬迁仍是纯整理、"
                      "仍延期」⇒ **措辞与盘上事实不符**，需要 D 追平（甲=追认 / 乙=回滚，C2 不自选）。")
    return out


def main() -> int:
    as_of = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    out_dir = REPO / OUT_DIR_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    doc: dict = {
        "artifact": "c2_e4_ruling_material_evidence",
        "as_of": as_of,
        "producer": {"script": SELF_REL, "sha256_12": sha12(REPO / SELF_REL),
                     "n_bytes": (REPO / SELF_REL).stat().st_size,
                     "python": sys.version.split()[0]},
        "task_authority": {
            "source": "rl_harness_supervision/d_handoff_to_c2_20260930.md",
            "sections": ["待命令·二（裁定 103.6-④）", "补单·四（裁定 104）"],
            "scope_verbatim": ("① E4 两把牙（Tb_scale_floor_effective / "
                               "Tr3_near_constant_floor_material）的**裁定材料**（Step-1 期间不改极性）；"
                               "② ③ 号问题（准入闸 ∧ 质量闸）的**方案设计**（只出方案、不落地新牙）"),
            "handoff_identity_at_read_time": identity(
                "rl_harness_supervision/d_handoff_to_c2_20260930.md"),
        },
        "read_only": True,
        "write_scope": [OUT_DIR_REL],
        "policy_executed": False, "gpu_used": False, "capability_claim": False,
        "success_metrics_collected": False,
        "gate_rerun": False,
        "gate_rerun_note": ("裁定 104-②：Step-1 出结果前**不重跑全量闸**、不上卡。本件只对既有产物做"
                            "只读取证；唯一的重活是 `gate_verdict.json` 的**单遍流式**哈希+计数。"),
        "ruling_46": ("裁定 46/101.3 能力声明禁令：本件内任何计数都**不是** policy 能力指标；"
                      "`success_rate_column = not_an_exit_criterion`。"),
        "success_rate_column": "not_an_exit_criterion",
        "n_lines_caliber": N_LINES_CALIBER,
        "line_no_discipline": ("件内所有 `line_no_as_of` 都是 **as_of 这一刻**的行号，不是常驻身份；"
                               "约束性对账只用 `sha256[:12]`（裁定 98.5）。"),
        "resource_readings": {
            "measurement_status": "measured",
            "loadavg": open("/proc/loadavg").read().strip(),
            "cgroup_quota_cores_note": "见守望器 poll 件的 `readings.cgroup_quota_cores`（A2 侧读数，本件只引不判）",
        },
    }

    # ---- 冻结面完整性（先核，任何一项不符都要在件里显式红）----
    frozen = {}
    for rel, exp in FROZEN_EXPECTED.items():
        idn = identity(rel, expected_sha12=exp)
        frozen[rel] = idn
    doc["frozen_surface_integrity"] = {
        "measurement_status": "measured",
        "expected_source": "裁定 101.2 / 104-② 点名的冻结面身份",
        "per_file": frozen,
        "all_match": all(v.get("matches_expected") is True for v in frozen.values()),
        "note": ("本件**不写**这些文件（AST 静态解析，不 import）⇒ 冻结面一个字节不动是"
                 "结构性的，不只是声明。"),
    }

    # ---- Part A ----
    doc["part_A_e4_teeth"] = {
        "static_parse": parse_teeth("harness/norm_contract.py"),
        "thresholds": parse_thresholds("harness/norm_contract.py"),
        "calibration_source": None,
        "authoritative_gate_run": None,
    }
    cal_rel = "runs/vla/d_ruling_round_20260930_1010/probe_resolution_calibration_inputs.json"
    cal, cal_id = read_json(cal_rel)
    cal_blk = {"identity": cal_id, "measurement_status": "not_measured"}
    if cal is not None:
        cal_blk.update({
            "measurement_status": "measured",
            "artifact": cal.get("artifact"), "ruling": cal.get("ruling"),
            "generated_at": cal.get("generated_at"),
            "generator": cal.get("generator"), "generator_sha256_12": cal.get("generator_sha256_12"),
            "read_only": cal.get("read_only"),
            "sources": cal.get("sources"),
            "gate_verdict_top_level": cal.get("gate_verdict_top_level"),
            "arm_mainline_matrix_verdict": cal.get("arm_mainline_matrix_verdict"),
            "n_formal40_bc_source_rows": cal.get("n_formal40_bc_source_rows"),
            "near_constant_rel_tol": cal.get("near_constant_rel_tol"),
            "near_constant_dims": cal.get("near_constant_dims"),
            "calibers": cal.get("calibers"),
            "calibration_decided_by_d": cal.get("calibration_decided_by_d"),
            "falsifiable_checkpoints_preregistered": cal.get("falsifiable_checkpoints_preregistered"),
        })
    else:
        cal_blk["why"] = "定标件读不到/解析失败"
    doc["part_A_e4_teeth"]["calibration_source"] = cal_blk
    doc["part_A_e4_teeth"]["authoritative_gate_run"] = gate_run_facts(
        "runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156")

    # ---- Part B ----
    doc["part_B_bc_coupling"] = {
        "code_facts": parse_bc_coupling(),
        "admission_artifact": admission_artifact_facts("runs/vla/a2_s3_bc_overfit_20260930"),
        "negative_legs": negative_legs(["runs/vla/a2_bc_admission_consume_20260930_run*"]),
        "contract_layer_bc_admission": None,
    }
    # 契约层 `bc_admission()` 的三值纪律（静态取证）
    try:
        nsrc = (REPO / "harness/norm_contract.py").read_text(encoding="utf-8", errors="replace")
        nlines = nsrc.splitlines()
        hits = [{"line_no_as_of": i, "text": ln.strip()[:240]}
                for i, ln in enumerate(nlines, start=1)
                if re.search(r"def bc_admission\(|\"admissible_for_bc\":|"
                             r"gate_verdict_class1_green\"|gate_verdict_class1_measurement_status\"", ln)][:10]
        doc["part_B_bc_coupling"]["contract_layer_bc_admission"] = {
            "measurement_status": "measured", "hits": hits,
            "reading": ("`admissible_for_bc` **仍是纯标签派生**（`prov in BC_ADMISSIBLE_PROVENANCES`），"
                        "这是**刻意设计**（不合并「标签错」与「闸红」两种失效）；闸证据走独立字段 + "
                        "独立牙 `Tbcad_admission_requires_green_gate`（`blocking=True`, "
                        "`applies_when=consumer=='bc'`），缺 class-1 证据 ⇒ `None` ⇒ 牙红。"),
        }
    except Exception as exc:                                          # noqa: BLE001
        doc["part_B_bc_coupling"]["contract_layer_bc_admission"] = {
            "measurement_status": "not_measured", "why": f"{type(exc).__name__}: {exc}"}

    # ---- Part C ----
    doc["part_C_move_reconciliation"] = move_facts()

    # ---- 自证：本件不写冻结面（写完后复核一次 sha）----
    post = {rel: sha12(REPO / rel) for rel in FROZEN_EXPECTED}
    doc["frozen_surface_integrity"]["post_run_sha256_12"] = post
    doc["frozen_surface_integrity"]["unchanged_by_this_probe"] = all(
        post[rel] == exp for rel, exp in FROZEN_EXPECTED.items())

    dst = out_dir / "E4_EVIDENCE.json"
    txt = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False)
    dst.write_text(txt + "\n", encoding="utf-8")
    ident = {"path": dst.relative_to(REPO).as_posix(), "sha256_12": sha12(dst),
             "n_bytes": dst.stat().st_size, "n_lines_wc": txt.count("\n") + 1,
             "n_lines_splitlines": len((txt + "\n").splitlines()),
             "n_lines_caliber": N_LINES_CALIBER}
    print(json.dumps({"artifact": "c2_e4_ruling_material_evidence", "as_of": as_of,
                      "identity": ident,
                      "frozen_surface_all_match": doc["frozen_surface_integrity"]["all_match"],
                      "frozen_surface_unchanged_by_this_probe":
                          doc["frozen_surface_integrity"]["unchanged_by_this_probe"],
                      "gate_rerun": False, "gpu_used": False},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
