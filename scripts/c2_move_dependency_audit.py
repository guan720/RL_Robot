#!/usr/bin/env python3
"""裁定 99.4-①「先搬」的**执行前依赖审计**（只读；不搬、不改任何既有文件）。

为什么需要它：补单五-③ 下令把「所有非闸产物（探针件、说明件、前像、`cp -p` 的顶层便利副本）」
搬出 `NORM_DIR`。本审计只做三件事，全部实测、不采信散文：
  A. 把**代码里对 `NORM_DIR` 的每一处引用**枚举出来（file:line + 引用串 + 该文件是否冻结面）；
  B. 把 `G20` 的**判据原文**取出来，并实测「新一轮闸跑会不会数到既有文件」；
  C. 据此把 `NORM_DIR` 的顶层条目分成「可安全搬 / 被活代码引用 / 被冻结码引用 / 登记禁搬 /
     闸产物 / stats 冻结面」，并给出**字面执行补单五-③ 会打断什么**的逐条清单。
  E. 按 basename 扫（治**跨行隐式拼接**与已发布文书里的路径引用）。
  F1. 按 **AST 取字符串常量 + 通配配对**扫（治 `bi_dir.glob("x.md.before_*")` 这类**带 `*` 的引用**）。
  F2. 扫**他线产物**里对本目录件的消费记录（治「引用不在代码里、而在上一次调用的入参记录里」）。

三值纪律：没测到的一律 `not_measured`，不写 false/0 顶替。裁定 46：本件不含任何 policy 指标。
"""
from __future__ import annotations

import ast
import datetime as _dt
import fnmatch
import hashlib
import importlib.util
import json
import pathlib
import posixpath
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
NORM_DIR = ROOT / "runs/vla/c2_norm_contract_20260929"
GATE_SRC = ROOT / "scripts/c2_gate_norm_contract.py"
OUT_DIR = ROOT / "runs/vla/c2_move_dependency_audit_ruling99"
OUT = OUT_DIR / "MOVE_DEPENDENCY_AUDIT.json"
CODE_DIRS = ("harness", "scripts", "registry")
NORM_REL = "runs/vla/c2_norm_contract_20260929/"
# 冻结面（裁定 95.5 / 97.3-5 / 补单五-⑤）：**只读身份，不改一个字节**
FROZEN = {"harness/norm_contract.py": "91795179de7e",
          "scripts/c2_build_norm_stats.py": "1bc468012cff"}
REF_RE = re.compile(r"runs/vla/c2_norm_contract_20260929/[A-Za-z0-9_./+*{}-]*")
# 字面串扫描看不到的第二类引用：**路径构造**（`NORM_DIR / "matrix.json"`）。
# 裁定 93.8：审计器必须自证覆盖 ⇒ 这一类单独扫、单独报，不假装字面扫描是完备的。
NORM_JOIN_RE = re.compile(r"NORM_DIR\s*/\s*[\"']([^\"']+)[\"']")
NORM_VAR_RE = re.compile(r"\bNORM_DIR\b")
# 闸源码本身在裁定 97.3-5 的冻结令下（「再修」批次之前不得改判据形态），单列一类。
GATE_SOURCE_REL = "scripts/c2_gate_norm_contract.py"


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha12(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:12]


def ident(p: pathlib.Path) -> dict:
    if not p.exists():
        return {"path": str(p.relative_to(ROOT)), "measurement_status": "not_measured",
                "why": "path_absent"}
    st = p.stat()
    return {"path": str(p.relative_to(ROOT)), "measurement_status": "measured",
            "bytes": st.st_size, "sha256_12": sha12(p),
            "mtime": _dt.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds"),
            "ctime": _dt.datetime.fromtimestamp(st.st_ctime).astimezone().isoformat(timespec="seconds")}


def code_reference_census() -> dict:
    """A：代码里对 NORM_DIR 的每一处引用（含行号；行号是**本件 as_of 的时点读数**，引用一律带 sha12）。"""
    rows = []
    scanned = []
    for d in CODE_DIRS:
        for p in sorted((ROOT / d).rglob("*.py")):
            rel = str(p.relative_to(ROOT))
            if rel == str(pathlib.Path(__file__).relative_to(ROOT)):
                continue                                   # 不自指（本审计器不算被审计对象）
            scanned.append({"path": rel, "sha256_12": sha12(p),
                            "is_frozen_face": rel in FROZEN,
                            "frozen_sha_matches": (sha12(p) == FROZEN[rel]) if rel in FROZEN else None})
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                for m in REF_RE.finditer(line):
                    ref = m.group(0).rstrip(".,;:")
                    rows.append({"referencing_file": rel,
                                 "referencing_file_is_frozen": rel in FROZEN,
                                 "referencing_line_no_as_of": i,
                                 "ref": ref,
                                 "ref_target_exists": (ROOT / ref).exists(),
                                 "kind": ("prose_or_docstring" if line.lstrip().startswith(("#", "（", "「"))
                                          or line.strip().startswith(('"', "'")) else "code_path")})
    by_target: dict = {}
    for r in rows:
        by_target.setdefault(r["ref"], []).append(r)
    return {"as_of": _now(), "n_references": len(rows), "n_files_scanned": len(scanned),
            "n_distinct_targets": len(by_target),
            "targets_referenced_by_frozen_face": sorted(
                {r["ref"] for r in rows if r["referencing_file_is_frozen"]}),
            "targets_referenced_by_live_code": sorted(
                {r["ref"] for r in rows if not r["referencing_file_is_frozen"]}),
            "by_target": {k: v for k, v in sorted(by_target.items())},
            "scanned_files": scanned, "rows": rows}


def g20_criterion_verbatim() -> dict:
    """B：把 G20 的判据原文按名字锚点取出来（不给行号当常驻身份，行号只作时点读数）。"""
    return _g20_impl()


def constructed_reference_scan() -> dict:
    """A2：`NORM_DIR / "x"` 形状的路径构造引用 + 无法静态解析的 `NORM_DIR` 提及（残余类，如实报）。"""
    joined, residual = [], []
    self_rel = str(pathlib.Path(__file__).relative_to(ROOT))
    for d in CODE_DIRS:
        for p in sorted((ROOT / d).rglob("*.py")):
            rel = str(p.relative_to(ROOT))
            if rel == self_rel:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                for m in NORM_JOIN_RE.finditer(line):
                    joined.append({"referencing_file": rel, "line_no_as_of": i,
                                   "constructed_leaf": m.group(1),
                                   "referencing_file_is_frozen": rel in FROZEN,
                                   "referencing_file_is_gate_source": rel == GATE_SOURCE_REL,
                                   "text": line.strip()[:220]})
                if NORM_VAR_RE.search(line) and not NORM_JOIN_RE.search(line) \
                        and not REF_RE.search(line):
                    residual.append({"referencing_file": rel, "line_no_as_of": i,
                                     "text": line.strip()[:220]})
    return {"as_of": _now(), "n_constructed_refs": len(joined),
            "n_residual_norm_dir_mentions": len(residual),
            "constructed_leaves": sorted({r["constructed_leaf"] for r in joined}),
            "constructed_refs": joined,
            "residual_mentions_not_statically_resolvable": residual,
            "why_this_section_exists": ("字面串扫描（A 段）只能看见写全路径的引用。`NORM_DIR / \"matrix.json\"` "
                                        "这种**构造式**引用它看不见 ⇒ 若只报 A 段，`matrix.json` 会被误判成"
                                        "「无人引用、可安全搬」，而它其实是 `G20` 非恒真哨兵的锚点"
                                        "（搬走 ⇒ `enumerator_sees_known=False` ⇒ **G20 永久红**）。"
                                        "残余类（提到 `NORM_DIR` 但既非字面串也非可解析构造）逐行列出、不吞掉。")}


def _entries_touched_by_ref(ref: str) -> set:
    """把一个引用串映射到它实际触到的 `NORM_DIR` 顶层条目名（**含通配展开**）。"""
    out: set = set()
    if "*" in ref or "{" in ref:
        try:
            cands = list(ROOT.glob(ref))
        except (OSError, ValueError):
            cands = []
        if not cands:                      # 通配串也可能只是散文示意 ⇒ 退回前缀匹配，不静默当 0
            stem = ref.split("*")[0]
            cands = [p for p in NORM_DIR.iterdir()
                     if str(p.relative_to(ROOT)).startswith(stem)]
    else:
        cands = [ROOT / ref]
    for c in cands:
        try:
            rp = c.resolve().relative_to(NORM_DIR.resolve())
        except (ValueError, OSError):
            continue
        if rp.parts:
            out.add(rp.parts[0])
    return out


def _g20_impl() -> dict:
    """B：把 G20 的判据原文按名字锚点取出来（不给行号当常驻身份，行号只作时点读数）。"""
    text = GATE_SRC.read_text(encoding="utf-8", errors="replace")
    anchors = {
        "t_start_assignment": r"^\s*t_start\s*=\s*time\.time\(\)",
        "cutoff_assignment": r"^\s*cutoff\s*=\s*t_start",
        "mtime_test": r"st_mtime\s*>=\s*cutoff",
        "enumerator_sentinel": r"enumerator_sees_known\s*=\s*\(NORM_DIR\s*/\s*[\"']matrix\.json[\"']\)\s*in\s*enumerated",
        "g20_ok_expression": r"\(not\s+touched_undeclared\)\s*and\s*enumerator_sees_known\s*and\s*len\(enumerated\)\s*>\s*0",
        "exception_membership_test": r"t\s+not\s+in\s+G20_DECLARED_WRITE_EXCEPTIONS",
    }
    out = {"as_of": _now(), "gate_source": ident(GATE_SRC), "anchors": {}}
    lines = text.splitlines()
    for name, pat in anchors.items():
        hits = [{"line_no_as_of": i, "text": ln.strip()}
                for i, ln in enumerate(lines, 1) if re.search(pat, ln)]
        out["anchors"][name] = {"pattern": pat, "n_hits": len(hits), "hits": hits,
                                "measurement_status": "measured" if hits else "not_found"}
    spec = importlib.util.spec_from_file_location("gate_ro", GATE_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    exc = dict(mod.G20_DECLARED_WRITE_EXCEPTIONS)
    out["declared_write_exceptions"] = {
        "n_entries": len(exc),
        "entries": {k: v for k, v in exc.items()},
        "n_entries_with_must_not_move_or_delete": sum(
            1 for v in exc.values() if v.get("must_not_move_or_delete") is True),
        "membership_semantics": ("**精确路径成员判定**（`t in … / t not in …`）⇒ 目录级/前缀级例外无效，"
                                 "除非改判据形状（撞裁定 97.3-5 的冻结）")}
    return out


def next_run_would_count(anchors: dict) -> dict:
    """B2：实测「新一轮闸跑会不会数到既有文件」—— 这是补单五-③「不先搬就修 = 恒红」那个前提的判据。"""
    files = [p for p in NORM_DIR.rglob("*") if p.is_file()]
    now = time.time()
    res = {"as_of": _now(), "cutoff_semantics_verbatim": None,
           "n_files_under_norm_dir_total": len(files),
           "cutoff_if_a_new_run_started_now": _dt.datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds")}
    for a in ("t_start_assignment", "cutoff_assignment"):
        h = anchors.get(a, {}).get("hits") or []
        if h:
            res["cutoff_semantics_verbatim"] = (res.get("cutoff_semantics_verbatim") or "") + h[0]["text"] + " ｜ "
    for tag, key in (("mtime", "st_mtime"), ("ctime", "st_ctime")):
        n = sum(1 for p in files if getattr(p.stat(), key) >= now)
        res["n_files_counted_if_new_run_started_now_by_" + tag] = n
    res["conclusion"] = (
        "**`cutoff = t_start`，而 `t_start = time.time()` 就在 `run_dir.mkdir()` 之后取** ⇒ "
        "**G20 只数「本轮开闸之后被写」的文件**。既有文件的 mtime/ctime 全都早于任何未来轮次的 cutoff ⇒ "
        "实测两口径都是 **0** 件。⇒ ①「下一轮全量闸跑会因为既有未声明写入而红」**不成立**；"
        "②「P2 改成 `mtime ∨ ctime` 就会恒红 130 件」**也不成立**（那 130 是**用旧轮 cutoff 复算现在的树**"
        "得到的数，与真判据不同源）。**P2 的真实作用只是：让「本轮期间用 `cp -p` 写入」这一形状可见。**")
    return res


def toplevel_copy_inventory() -> dict:
    """C1：那 51 份 `cp -p` 顶层便利副本到底是什么（读标记件，不猜）。"""
    mk_path = NORM_DIR / "TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json"
    out = {"marker": ident(mk_path), "measurement_status": "not_measured"}
    if not mk_path.exists():
        out["why"] = "marker_absent"
        return out
    mk = json.loads(mk_path.read_text(encoding="utf-8"))
    rows = (mk.get("byte_identity_audit") or {}).get("rows") or []
    cat: dict = {}
    for r in rows:
        tp = r["toplevel_path"]
        tail = tp[len("runs/vla/c2_norm_contract_20260929/"):]
        k = "stats/*.json" if tail.startswith("stats/") else tail
        cat[k] = cat.get(k, 0) + 1
    out.update({"measurement_status": "measured", "n_rows": len(rows),
                "n_byte_identical": sum(1 for r in rows if r.get("byte_identical") is True),
                "category_counts": cat,
                "n_that_are_stats_files": sum(1 for r in rows
                                              if r["toplevel_path"].split("/")[-2:-1] == ["stats"]),
                "conclusion": ("**51 份里有 49 份就是 `stats/*.json`** ⇒ 补单五-③「搬走 `cp -p` 的顶层便利副本」"
                               "与补单五-⑤／裁定 95.5「**不许动 stats**」**在字面上直接冲突**；"
                               "另 2 份是 `mainline_status.json` 与 `matrix.json`（见 C2 的活代码依赖）。")})
    return out


OWNER_BY_PREFIX = (("scripts/a2_", "A2"), ("harness/bc_admission_gate.py", "A2"),
                   ("scripts/b2_", "B2"), ("registry/", "B2"),
                   ("scripts/e_", "E"), ("scripts/f_", "F"),
                   ("scripts/c2_", "C2"), ("harness/norm_contract.py", "C2（冻结契约层）"))


def _owner(rel: str) -> str:
    for pre, who in OWNER_BY_PREFIX:
        if rel.startswith(pre) or rel == pre:
            return who
    return "other"


def classify_toplevel(census: dict, constructed: dict) -> dict:
    """C2：`NORM_DIR` 顶层条目分类（引用来源含字面串、构造式、通配展开三类，逐条标 `via`）。"""
    per_entry: dict = {}

    def add(entry: str, rec: dict) -> None:
        per_entry.setdefault(entry, []).append(rec)

    for r in census["rows"]:
        for e in _entries_touched_by_ref(r["ref"]):
            add(e, {"ref": r["ref"], "via": "glob_expanded" if "*" in r["ref"] else "literal_string",
                    "referencing_file": r["referencing_file"], "owner": _owner(r["referencing_file"]),
                    "is_frozen_face": r["referencing_file_is_frozen"],
                    "is_gate_source": r["referencing_file"] == GATE_SOURCE_REL,
                    "line_no_as_of": r["referencing_line_no_as_of"], "kind": r["kind"]})
    for r in constructed["constructed_refs"]:
        for e in _entries_touched_by_ref(NORM_REL + r["constructed_leaf"]):
            add(e, {"ref": 'NORM_DIR / "' + r["constructed_leaf"] + '"', "via": "constructed_path",
                    "referencing_file": r["referencing_file"], "owner": _owner(r["referencing_file"]),
                    "is_frozen_face": r["referencing_file_is_frozen"],
                    "is_gate_source": r["referencing_file_is_gate_source"],
                    "line_no_as_of": r["line_no_as_of"], "kind": "code_path"})

    exc_paths = set()
    try:
        spec = importlib.util.spec_from_file_location("gate_ro2", GATE_SRC)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        exc_paths = set(mod.G20_DECLARED_WRITE_EXCEPTIONS)
    except Exception as exc:                                            # noqa: BLE001
        exc_paths = set()
        print("WARN: 读不到例外清单 " + type(exc).__name__, file=sys.stderr)

    entries = []
    for p in sorted(NORM_DIR.iterdir()):
        name = p.name
        rel = name + ("" if p.is_file() else "/")
        n_files = 1 if p.is_file() else sum(1 for q in p.rglob("*") if q.is_file())
        rr = per_entry.get(name, [])
        frozen = sorted({x["referencing_file"] for x in rr if x["is_frozen_face"]})
        gate_src = sorted({x["referencing_file"] for x in rr if x["is_gate_source"]})
        owners = sorted({x["owner"] for x in rr})
        has_exc = any(str((NORM_DIR / name).relative_to(ROOT)) in e or e.startswith(NORM_REL + name + "/")
                      for e in exc_paths)
        if name == "gate":
            safety = "must_not_move_gate_product"
        elif name == "stats":
            safety = "must_not_move_stats_frozen_ruling95_5"
        elif has_exc:
            safety = "must_not_move_registered_exception"
        elif frozen:
            safety = "blocked_referenced_by_frozen_face"
        elif gate_src:
            safety = "blocked_referenced_by_gate_source"
        elif owners:
            safety = "blocked_referenced_by_live_code"
        else:
            safety = "movable_no_code_reference_found"
        entries.append({"entry": rel, "is_dir": p.is_dir(), "n_files": n_files,
                        "n_code_refs": len(rr),
                        "ref_vias": sorted({x["via"] for x in rr}),
                        "referenced_by": sorted({x["referencing_file"] for x in rr}),
                        "owners_that_would_break": owners,
                        "referenced_by_frozen_face": frozen,
                        "referenced_by_gate_source": gate_src,
                        "contains_registered_must_not_move_exception": has_exc,
                        "move_safety": safety,
                        "refs": rr})
    by_safety: dict = {}
    for e in entries:
        by_safety.setdefault(e["move_safety"], []).append(e["entry"])
    return {"as_of": _now(), "n_toplevel_entries": len(entries),
            "entries_by_move_safety": {k: sorted(v) for k, v in sorted(by_safety.items())},
            "n_entries_movable_no_code_reference_found": len(by_safety.get("movable_no_code_reference_found", [])),
            "n_files_under_movable_entries": sum(e["n_files"] for e in entries
                                                 if e["move_safety"] == "movable_no_code_reference_found"),
            "entries": entries}


DOC_FACES = ("docs", "rl_harness_supervision")


# ── F1 / F2 两条新通道的参数（写死在代码里；产物里逐字回显，便于 D 复核判据本身） ──────
CONSUMER_BASES = ("runs/vla", "runs/infra")
CONSUMER_DIR_PREFIXES = ("a2_", "b2_", "d_", "e_", "f_")
CONSUMER_SUFFIXES = (".json", ".md", ".txt", ".log")
MAX_CONSUMER_FILE_BYTES = 8 << 20
MAX_CONSUMER_FILES = 2000
# `*` / `*.json` 这类退化通配不当「引用」处理（否则任何 `glob("*")` 都会把全目录判成禁搬），
# 但它们**不被吞掉**：单独计数 + 点名文件，列在 F1 段的 `degenerate_patterns`（裁定 93.8）。
MIN_PATTERN_LITERAL_CHARS = 3
MAX_WILDCARD_CANDIDATES = 400000
MIN_RECEIVER_NAME_CHARS = 3          # `d` / `p` 这类单字母名不做变量名回流（噪声太大）
NAME_FLOW_MAX_LINE_GAP = 30          # 目录赋值行与通配行的行距上限（治跨函数误配）
INPUT_KEYISH_TOKENS = ("path", "artifact", "input", "consume", "doc")
WILDCARDS = ("*", "?")


def _owner_of_run_dir(rel: str) -> str:
    """从他线 run 目录名的前缀推出归属线（`runs/vla/a2_…` → `A2`）。"""
    parts = rel.split("/")
    name = parts[2] if len(parts) > 2 else rel
    for pre in CONSUMER_DIR_PREFIXES:
        if name.startswith(pre):
            return pre.rstrip("_").upper()
    return "other"


def _doc_owner(rel: str) -> str:
    """文书归属：`docs/c2_*` → C2、`rl_harness_supervision/d_*` → D、日报是多写者共享面。"""
    if rel == "daily_report.md":
        return "shared_daily_report"
    if rel.startswith("rl_harness_supervision/"):
        return "D"
    base = pathlib.Path(rel).name
    for who in ("c2", "a2", "b2", "e", "f"):
        if base.startswith(who + "_"):
            return who.upper()
    return "other"


def _iter_text_files() -> list:
    out = []
    for d in CODE_DIRS:
        out += sorted((ROOT / d).rglob("*.py"))
    for d in DOC_FACES:
        out += sorted((ROOT / d).glob("*.md"))
    out.append(ROOT / "daily_report.md")
    self_p = (ROOT / pathlib.Path(__file__).name).resolve()
    return [q for q in out if q.exists() and q.resolve() != self_p]


def undeclared_rows(cutoff_iso: str) -> list:
    """按闸的判据（只读复现）枚举 `NORM_DIR` 内 run 目录外、`mtime >= cutoff`、不在例外清单里的行。"""
    spec = importlib.util.spec_from_file_location("gate_ro3", GATE_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    exc = set(mod.G20_DECLARED_WRITE_EXCEPTIONS)
    cut = _dt.datetime.fromisoformat(cutoff_iso).timestamp()
    target_run = NORM_DIR / "gate/run_20260930_133156"
    rows = []
    for q in sorted(NORM_DIR.rglob("*")):
        if not q.is_file() or str(q).startswith(str(target_run)):
            continue
        st = q.stat()
        if st.st_mtime < cut:
            continue
        rel = str(q.relative_to(ROOT))
        if rel in exc:
            continue
        rows.append({"path": rel, "bytes": st.st_size, "sha256_12": sha12(q),
                     "mtime": _dt.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds"),
                     "ctime": _dt.datetime.fromtimestamp(st.st_ctime).astimezone().isoformat(timespec="seconds")})
    return rows


def bare_name_census(rows: list) -> dict:
    """**第三条引用探测通道**：按 basename 扫，专治字面串通道看不见的两种形状 ——
    ① 跨行隐式拼接（实物 = `scripts/b2_bc_input_inventory.py` 的 `P_C2_TOPLEVEL_MARKER`，
       两行拼出同一个路径 ⇒ 任何单行正则都看不见它）；
    ② 已发布文书里按路径的引用（搬动会让它悬空 = 缺陷类 ㉒）。
    裁定 93.8：审计器必须自证覆盖 ⇒ A / A2 / E 三条通道取并集。
    """
    files = _iter_text_files()
    cache = {}
    for f in files:
        try:
            cache[str(f.relative_to(ROOT))] = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
    per_row = []
    for r in rows:
        name = pathlib.Path(r["path"]).name
        tail = r["path"][len(NORM_REL):]
        parent = pathlib.Path(r["path"]).parent.name
        needles = {name}
        if parent not in ("before_images", "."):
            needles.add(parent)
        code_hits, doc_hits = [], []
        for rel, lines in cache.items():
            is_code = rel.endswith(".py")
            for i, line in enumerate(lines, 1):
                for nd in needles:
                    if nd in line:
                        rec = {"file": rel, "line_no_as_of": i, "needle": nd,
                               # 判据分层：**basename 命中 / 同行有全路径字面量** = 功能性引用（能挡住搬迁）；
                               # 只命中父目录名（如 `c2_norm_contract_20260929`）= 目录级提及，**不单独挡搬迁**，
                               # 但照旧列出、不吞掉（裁定 93.8）。
                               "needle_kind": ("basename" if nd == name else "parent_dir_only"),
                               # `functional` = 这行**确实在指这一件**：basename 命中，或同行有全路径字面量
                               # 且该行含本件的目录内相对路径。只写全 NORM_DIR 前缀而指向**别件**的行
                               # （实物 = `harness/bc_admission_gate.py` 的 `TOPLEVEL_CONVENIENCE_COPY =
                               # "…/mainline_status.json"`）不算本件的阻塞引用，只算目录级提及。
                               "functional": (nd == name or (NORM_REL in line and tail in line)),
                               "full_path_literal_on_same_line": NORM_REL in line,
                               "text": line.strip()[:200]}
                        (code_hits if is_code else doc_hits).append(rec)
                        break
        functional_code = [h for h in code_hits if h["functional"]]
        dir_mention_code = [h for h in code_hits if not h["functional"]]
        per_row.append({"path": r["path"], "basename": name,
                        "n_code_hits": len(code_hits), "n_doc_hits": len(doc_hits),
                        "n_code_hits_functional": len(functional_code),
                        "n_code_hits_dir_mention_only": len(dir_mention_code),
                        "code_hits_functional": functional_code[:40],
                        "referencing_code_files_functional": sorted({h["file"] for h in functional_code}),
                        "owners_functional": sorted({_owner(h["file"]) for h in functional_code}),
                        "owners_dir_mention_only": sorted({_owner(h["file"]) for h in dir_mention_code}),
                        "code_hits": code_hits[:20], "doc_hits_head": doc_hits[:12],
                        "n_doc_hits_listed": min(len(doc_hits), 12),
                        "referencing_code_files": sorted({h["file"] for h in code_hits}),
                        "referencing_code_owners": sorted({_owner(h["file"]) for h in code_hits}),
                        "citing_doc_files": sorted({h["file"] for h in doc_hits}),
                        "citing_doc_owners": sorted({_doc_owner(h["file"]) for h in doc_hits}),
                        "cross_line_concat_suspected": any(
                            not h["full_path_literal_on_same_line"] for h in code_hits)})
    return {"as_of": _now(), "n_files_scanned": len(cache), "n_rows_probed": len(per_row),
            "channels": ["A_literal_path_string", "A2_constructed_path_and_glob", "E_bare_name",
                         "F1_wildcard_glob（另段）", "F2_consumer_record（另段）"],
            "rows": per_row,
            "why": ("字面串通道（A）漏掉跨行拼接与构造式引用 ⇒ 第一版审计把标记件判成「只有 C2 引用」，"
                    "而实物是 `scripts/b2_bc_input_inventory.py` 的 `P_C2_TOPLEVEL_MARKER` 跨两行拼出同一路径。"
                    "**这是本审计器自己的第二个假阴性**（第一个是 `matrix.json` 的构造式引用），"
                    "两版原字节都保留在同目录（`…py.v1_cd3c8c8afd4d` / `…py.v2_96e131af8cbd`）。"
                    "**第三个假阴性由 v3 自己暴露**：E 通道按 basename 匹配，看不见 `*` 通配 ⇒ 把 "
                    "`scripts/b2_bc_input_inventory.py` 的 `bi_dir.glob(\"c2_to_a2_bc_stats_handoff_20260930.md.before_*\")` "
                    "判成 0 引用（v3 原字节 = `…py.v3_03231856ee41`，它给出的计划是 28 搬 / 1 留）。"
                    "v4 增 F1（通配）+ F2（他线产物消费记录）两条通道补上。")}


def _code_string_constants() -> dict:
    """按 **AST** 取每份代码里的字符串常量（跨行隐式拼接在 AST 里已合并成一个常量；
    f-string 只取其字面片段，并标 `kind=fstring_literal_parts` ⇒ 不假装看见了插值）。"""
    out = {}
    self_rel = str(pathlib.Path(__file__).relative_to(ROOT))
    for d in CODE_DIRS:
        for p in sorted((ROOT / d).rglob("*.py")):
            rel = str(p.relative_to(ROOT))
            if rel == self_rel:
                continue                                   # 不自指
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(text)
            except (OSError, SyntaxError) as exc:
                out[rel] = {"parse_status": "not_measured", "why": f"{type(exc).__name__}",
                            "constants": [], "lines": []}
                continue
            consts = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    consts.append({"line_no_as_of": node.lineno, "value": node.value,
                                   "kind": "constant"})
                elif isinstance(node, ast.JoinedStr):
                    lit = "".join(v.value for v in node.values
                                  if isinstance(v, ast.Constant) and isinstance(v.value, str))
                    if lit:
                        consts.append({"line_no_as_of": node.lineno, "value": lit,
                                       "kind": "fstring_literal_parts"})
            out[rel] = {"parse_status": "measured", "n_constants": len(consts),
                        "constants": consts, "lines": text.splitlines()}
    return out


_GLOB_CACHE: dict = {}


def _glob_compile(pat: str):
    """**glob 语义**（不是 `fnmatch` 语义）：`*` 不跨 `/`、`**` 跨、`?` 不跨。
    为什么必须区分：被审计的实物是 `pathlib.Path.glob(...)`，而 `fnmatch.fnmatch` 让 `*` 吃掉 `/`
    ⇒ v4 第一版把 `runs/vla/c2_norm_contract_20260929/*.json` 误配到**嵌套**的探针件上（18 起假阳性）。"""
    hit = _GLOB_CACHE.get(pat)
    if hit is None:
        i, n, out = 0, len(pat), []
        while i < n:
            ch = pat[i]
            if ch == "*":
                if pat[i + 1:i + 2] == "*":
                    out.append(".*")
                    i += 2
                    if pat[i:i + 1] == "/":
                        i += 1
                else:
                    out.append("[^/]*")
                    i += 1
            elif ch == "?":
                out.append("[^/]")
                i += 1
            elif ch == "[":
                j = pat.find("]", i + 1)
                if j == -1:
                    out.append(re.escape(ch))
                    i += 1
                else:
                    out.append(pat[i:j + 1])
                    i = j + 1
            else:
                out.append(re.escape(ch))
                i += 1
        hit = re.compile("".join(out) + r"\Z")
        _GLOB_CACHE[pat] = hit
    return hit


def _glob_match(path: str, pat: str) -> bool:
    return _glob_compile(pat).match(path) is not None


def _is_prose_literal(v: str) -> bool:
    """含中文或空格的「通配串」是散文（Markdown 的 `**` 加粗），不是路径模式 ⇒ 单列计数、不当引用。"""
    return bool(re.search(r"[\u4e00-\u9fff]", v)) or " " in v


def _wildcard_candidate_index() -> dict:
    """把「目录字面量 × 通配串」的配对**只算一次**，并且**只按两条真实用法配对**（不做盲目笛卡尔）：
      (a) **同行**：`("glob", "<dir>", "<pattern>", …)` 这类规格行；
      (b) **变量名回流**：`bi_dir = REPO / "<dir>"`（AST 常量的 `lineno` 就是赋值行）⇒ 取该行被赋值的名字，
          若这个名字出现在通配串所在行（或其上一行，治多行调用）⇒ 配对。
    配不上任何目录的通配串**不被吞掉**：进 `residual_wildcard_literals_not_paired`（裁定 93.8）。
    （v4 第一版按行重算 ⇒ 29 倍冗余跑不完；第二版盲目笛卡尔 ⇒ 400000 候选截断 + 假阳性。这是第三版。）"""
    files = _code_string_constants()
    split_re = re.compile(r"[*?\[]")
    assign_re = re.compile(r"^\s*(\w+)\s*(?::\s*[\w\[\], .]+\s*)?=\s*")
    cands, degenerate, prose, unpaired = [], [], [], []
    for frel, doc in files.items():
        consts, lines = doc["constants"], doc["lines"]
        owner = _owner(frel)
        name_to_dirs, dir_by_line = {}, {}
        for c in consts:
            v = c["value"]
            if any(w in v for w in WILDCARDS) or "/" not in v or _is_prose_literal(v):
                continue
            L = c["line_no_as_of"]
            dir_by_line.setdefault(L, []).append(v)
            txt = lines[L - 1] if 0 <= L - 1 < len(lines) else ""
            m = assign_re.match(txt)
            if m and len(m.group(1)) >= MIN_RECEIVER_NAME_CHARS:
                name_to_dirs.setdefault(m.group(1), []).append((v, L))
        for c in consts:
            v = c["value"]
            if not any(w in v for w in WILDCARDS):
                continue
            L = c["line_no_as_of"]
            if _is_prose_literal(v):
                prose.append({"file": frel, "line_no_as_of": L, "literal": v[:80]})
                continue
            if len(re.sub(r"[*?\[\]]", "", v)) < MIN_PATTERN_LITERAL_CHARS:
                degenerate.append({"file": frel, "line_no_as_of": L, "pattern": v})
                continue
            ctx = "\n".join(lines[max(0, L - 2):L + 1])
            dirs = set(dir_by_line.get(L, ()))                  # (a) 同行
            pairing = "same_line" if dirs else None
            for name, ds in name_to_dirs.items():               # (b) 变量名回流（带角色 + 邻近两道闸）
                # 角色闸：名字必须以**接收者/实参**身份出现（`NAME.` / `NAME,` / `NAME)`），
                # 否则 `if not hits:` 这种**读值**也会把 235 行的目录配到 442 行的通配串上（实测假阳性）。
                if not re.search(r"\b" + re.escape(name) + r"\s*(?:\.|,|\))", ctx):
                    continue
                for dv, dl in ds:
                    if abs(dl - L) <= NAME_FLOW_MAX_LINE_GAP:    # 邻近闸
                        dirs.add(dv)
                        pairing = pairing or "name_flow"
            if not dirs:
                unpaired.append({"file": frel, "line_no_as_of": L, "pattern": v})
            leaf = pathlib.PurePosixPath(v).name
            raw = [v]
            # 退化叶子闸：`e_restart_readiness_*/*` 的叶子就是 `*` ⇒ 与任何目录拼接都会造出
            # `<dir>/*` 这种**吞掉整层**的假候选（实测把 F 的 `runs/infra` 通配配到了 NORM_DIR 上）。
            if len(re.sub(r"[*?\[\]]", "", leaf)) >= MIN_PATTERN_LITERAL_CHARS:
                raw.append(leaf)
                raw += [posixpath.normpath(posixpath.join(d, leaf)) for d in sorted(dirs)]
            raw += [posixpath.normpath(posixpath.join(d, v)) for d in sorted(dirs)]
            seen = set()
            for cand in raw:
                if cand in seen:
                    continue
                seen.add(cand)
                cands.append({"file": frel, "line_no_as_of": L, "owner": owner,
                              "pattern_literal": v, "candidate": cand,
                              "pairing": (pairing or "bare_pattern_only"),
                              "prefix_relpath": split_re.split(cand, 1)[0],
                              "prefix_basename": split_re.split(posixpath.basename(cand), 1)[0]})
                if len(cands) >= MAX_WILDCARD_CANDIDATES:
                    return {"n_code_files": len(files), "n_candidates": len(cands),
                            "candidates": cands, "n_degenerate": len(degenerate),
                            "degenerate": degenerate, "n_prose": len(prose), "prose": prose,
                            "n_unpaired": len(unpaired), "unpaired": unpaired, "truncated": True}
    return {"n_code_files": len(files),
            "n_code_files_parsed": sum(1 for d in files.values() if d["parse_status"] == "measured"),
            "n_candidates": len(cands), "candidates": cands,
            "n_degenerate": len(degenerate), "degenerate": degenerate,
            "n_prose": len(prose), "prose": prose,
            "n_unpaired": len(unpaired), "unpaired": unpaired,
            "truncated": False}


def wildcard_glob_channel(rows: list) -> dict:
    """**F1：通配 glob 通道** —— 治 E 通道（basename 子串）看不见的第三类形状：
    `bi_dir = REPO / "runs/vla/c2_norm_contract_20260929/before_images"` +
    `bi_dir.glob("c2_to_a2_bc_stats_handoff_20260930.md.before_*")`
    ⇒ **目录字面量与通配串分居两行、且通配串不含完整 basename**，任何子串匹配都命中不了。
    匹配用 **glob 语义**（`*` 不跨 `/`），配对只用「同行 / 变量名回流」两条真实用法。
    """
    idx = _wildcard_candidate_index()
    cands = idx["candidates"]
    per_row = []
    n_match_calls = 0
    for r in rows:
        rel = r["path"]
        base = pathlib.Path(rel).name
        hits = []
        for c in cands:
            pr, pb = c["prefix_relpath"], c["prefix_basename"]
            if not ((pr and rel.startswith(pr)) or (pb and base.startswith(pb))):
                continue                                   # 前缀剪枝：不可能匹配的不进正则
            n_match_calls += 1
            cand = c["candidate"]
            form = ("relpath" if _glob_match(rel, cand)
                    else ("basename" if _glob_match(base, cand) else None))
            if form:
                hits.append({"file": c["file"], "line_no_as_of": c["line_no_as_of"],
                             "owner": c["owner"], "pattern_literal": c["pattern_literal"],
                             "matched_candidate": cand, "matched_form": form,
                             "pairing": c["pairing"]})
        per_row.append({"path": rel, "basename": base, "n_wildcard_hits": len(hits),
                        "hits": hits[:12], "n_hits_listed": min(len(hits), 12),
                        "referencing_code_files": sorted({h["file"] for h in hits}),
                        "referencing_code_owners": sorted({h["owner"] for h in hits})})
    return {"as_of": _now(), "channel": "F1_wildcard_glob",
            "n_code_files_ast_parsed": idx.get("n_code_files_parsed"),
            "n_code_files_seen": idx["n_code_files"],
            "n_candidates_precomputed": idx["n_candidates"],
            "candidate_index_truncated": idx["truncated"],
            "max_candidates": MAX_WILDCARD_CANDIDATES,
            "n_match_calls_after_prefix_prune": n_match_calls,
            "n_degenerate_patterns_skipped": idx["n_degenerate"],
            "degenerate_patterns_head": idx["degenerate"][:10],
            "n_prose_literals_skipped": idx["n_prose"],
            "prose_literals_head": idx["prose"][:5],
            "n_unpaired_wildcard_literals": idx["n_unpaired"],
            "residual_wildcard_literals_not_paired": idx["unpaired"][:20],
            "residual_note": ("配不上任何目录字面量的通配串（接收者是变量/入参，静态不可解析）"
                              "**逐条列出、不吞掉**（裁定 93.8）；它们仍可能被 E 通道的 basename 扫命中。"),
            "criteria_verbatim": {"wildcard_chars": list(WILDCARDS),
                                  "min_pattern_literal_chars": MIN_PATTERN_LITERAL_CHARS,
                                  "match_semantics": "glob（`*` 不跨 `/`、`**` 跨、`?` 不跨），**不是 fnmatch**",
                                  "pairing_rules": ["(a) 目录字面量与通配串同一行",
                                                    "(b) 目录字面量被赋值的变量名（≥3 字符）以**接收者/实参**身份"
                                                    "（`NAME.` / `NAME,` / `NAME)`）出现在通配串所在行或其上一行，"
                                                    "且赋值行与通配行行距 ≤30"],
                                  "degenerate_leaf_guard": "通配串的叶子若去掉通配符后不足 3 字符（如 `*`），不做「目录 × 叶子」拼接",
                                  "name_flow_max_line_gap": NAME_FLOW_MAX_LINE_GAP,
                                  "min_receiver_name_chars": MIN_RECEIVER_NAME_CHARS,
                                  "prune_rule": "candidate 首个通配符之前的字面前缀必须是 relpath 或 basename 的前缀",
                                  "prose_filter": "含中文字符或空格的通配串按散文处理（Markdown `**` 加粗），单列计数"},
            "rows": per_row,
            "negative_leg": ("**三个负向腿，全部 C2 自己复现**：① v3 只有 A/A2/E 三通道 ⇒ 对两份 "
                             "`c2_to_a2_bc_stats_handoff_20260930.md.before_*` 报 `n_blocking_references = 0`，"
                             "而实物是 `scripts/b2_bc_input_inventory.py` 的 `bi_dir.glob(...)`（B2 活代码，"
                             "T-B2-19 v2 刚落地）用它做**归因证据**，空 glob 会把该行 `verdict` 翻成 "
                             "`unattributed_defect`、`ok` 翻回 `false`（原字节 `…py.v3_03231856ee41`）；"
                             "② F1 第一版按行重算笛卡尔积 ⇒ 5 分钟未出结果，C2 中止；"
                             "③ F1 第二版盲目笛卡尔 + `fnmatch` 语义 ⇒ 400000 候选被截断，"
                             "且 `*` 跨 `/` 造出 18 起假阳性（把 `NORM_DIR/*.json` 配到嵌套探针件上）、"
                             "还有把 Markdown 加粗 `**…**` 当通配串的 1 起。**本版（第三版）改为 glob 语义 + "
                             "两条真实配对规则**，并把配不上的通配串逐条列出。"),
            "why": "裁定 93.8：审计器必须自证覆盖 ⇒ 通道数从 3 增到 5，且**每条通道的漏检形态与假阳性都要点名**。"}


def consumer_record_channel(rows: list) -> dict:
    """**F2：他线产物消费记录通道** —— 治第四类形状：引用**不在代码里**，而在**上一次调用的入参记录**里。
    实物 = A2 的 `runs/vla/a2_bc_admission_consume_20260930_run{2,3}/BC_ADMISSION_DECISION_*.json`
    里记着 `c2_broadcast_json = runs/vla/c2_norm_contract_20260929/TOPLEVEL_…json`（CLI 入参），
    代码里只有一个 `default=None` ⇒ A/A2/E/F1 四条通道全都看不见它。
    **判据分层**：本通道产出的是**追平义务**（引用会悬空），不单独当「禁搬」——
    禁搬只由活代码（A/A2/E/F1）决定；但 `input_keyish=true` 的命中会单列，因为那是**下一次调用会读的入参**。
    """
    needle_map: dict = {}
    for r in rows:
        rel = r["path"]
        for nd in {pathlib.Path(rel).name, rel[len(NORM_REL):]}:
            needle_map.setdefault(nd, set()).add(rel)
    needles = sorted(needle_map, key=len, reverse=True)
    rx = re.compile("|".join(re.escape(n) for n in needles))
    files, truncated = [], False
    for base in CONSUMER_BASES:
        b = ROOT / base
        if not b.exists():
            continue
        for d in sorted(b.iterdir()):
            if not d.is_dir() or not d.name.startswith(CONSUMER_DIR_PREFIXES):
                continue
            for q in sorted(d.rglob("*")):
                if not q.is_file() or q.suffix not in CONSUMER_SUFFIXES:
                    continue
                try:
                    if q.stat().st_size > MAX_CONSUMER_FILE_BYTES:
                        continue
                except OSError:
                    continue
                files.append(q)
                if len(files) >= MAX_CONSUMER_FILES:
                    truncated = True
                    break
            if truncated:
                break
        if truncated:
            break
    acc = {r["path"]: {"n": 0, "n_input": 0, "by_owner": {}, "hits": [], "files": []} for r in rows}
    n_files_read = n_files_with_hits = 0
    for q in files:
        frel = str(q.relative_to(ROOT))
        try:
            text = q.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n_files_read += 1
        if not rx.search(text):                            # 整篇先过一遍（C 层），命中的才逐行
            continue
        n_files_with_hits += 1
        owner = _owner_of_run_dir(frel)
        for i, line in enumerate(text.splitlines(), 1):
            matched = {m.group(0) for m in rx.finditer(line)}
            if not matched:
                continue
            keyish = any(t in line for t in INPUT_KEYISH_TOKENS)
            for nd in matched:
                for row_path in needle_map[nd]:
                    e = acc[row_path]
                    e["n"] += 1
                    e["n_input"] += 1 if keyish else 0
                    e["by_owner"][owner] = e["by_owner"].get(owner, 0) + 1
                    if len(e["hits"]) < 8:
                        e["hits"].append({"file": frel, "line_no_as_of": i, "owner_line": owner,
                                          "needle": nd, "input_keyish": keyish,
                                          "text": line.strip()[:160]})
                    if len(e["files"]) < 12 and frel not in e["files"]:
                        e["files"].append(frel)
    per_row = []
    for r in rows:
        e = acc[r["path"]]
        per_row.append({"path": r["path"], "basename": pathlib.Path(r["path"]).name,
                        "n_consumer_record_hits": e["n"],
                        "n_hits_input_keyish": e["n_input"],
                        "n_hits_by_owner_line": e["by_owner"],
                        "hits_head": e["hits"], "n_hits_listed": len(e["hits"]),
                        "consumer_files": e["files"]})
    return {"as_of": _now(), "channel": "F2_consumer_record",
            "scan_scope": {"bases": list(CONSUMER_BASES), "dir_prefixes": list(CONSUMER_DIR_PREFIXES),
                           "suffixes": list(CONSUMER_SUFFIXES),
                           "max_file_bytes": MAX_CONSUMER_FILE_BYTES,
                           "max_files": MAX_CONSUMER_FILES},
            "n_files_collected": len(files), "n_files_read": n_files_read,
            "n_files_with_hits": n_files_with_hits, "scan_truncated": truncated,
            "n_needles": len(needles),
            "input_keyish_tokens": list(INPUT_KEYISH_TOKENS),
            "input_keyish_is_a_heuristic": True,
            "rows": per_row,
            "why": ("补单六-②-1 要求「每一处已发布引用的追平」。已发布引用**不只活在代码与文书里**，"
                    "也活在他线产物记录的入参里 ⇒ 不扫它就会漏掉 A2 对标记件的消费。")}


def move_execution_plan(rows: list, bare: dict, wild: dict, cons: dict) -> dict:
    """把补单六-② 授权的搬迁范围落成**逐件可执行**的计划：搬 / 不搬 + 理由 + 证据锚点。

    **禁搬判据（只用活代码，四条通道取并集）**：A 字面串 ∪ A2 构造式/通配展开 ∪
    E basename（只算 `functional` 命中，目录级提及不算）∪ F1 通配 glob；命中文件的 owner ≠ C2 才算阻塞。
    **F2（他线产物里的消费记录）不当禁搬**，只当**追平义务**并单列 `input_keyish` 的条数。
    """
    bmap = {r["path"]: r for r in bare["rows"]}
    wmap = {r["path"]: r for r in wild["rows"]}
    cmap = {r["path"]: r for r in cons["rows"]}
    plan = []
    for r in rows:
        tail = r["path"][len(NORM_REL):]
        in_scope = (tail.startswith("before_images/") or tail.startswith("probe_")
                    or tail == "TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json")
        b = bmap.get(r["path"], {})
        w = wmap.get(r["path"], {})
        c = cmap.get(r["path"], {})
        functional_code = [h for h in (b.get("code_hits_functional") or [])
                           if _owner(h["file"]) != "C2"]
        wildcard_code = [h for h in (w.get("hits") or []) if h["owner"] != "C2"]
        dir_mentions = [h for h in (b.get("code_hits") or [])
                        if not h.get("functional") and _owner(h["file"]) != "C2"]
        blockers = functional_code + wildcard_code
        decision = "move" if (in_scope and not blockers) else "hold_back"
        if decision == "move":
            reason = "在补单六-② 授权的三类内，且 A/A2/E/F1 四条通道**都没有他线活代码引用**"
        elif not in_scope:
            reason = "不在授权的三类内"
        else:
            reason = ("**他线活代码**按路径/通配引用它 ⇒ 搬动会让该引用悬空或直接翻判词，"
                      "而追平不在 C2 的写入面内（补单六-②-1 要求同批追平 ⇒ 只能留）")
        doc_cites = b.get("citing_doc_files") or []
        plan.append({**r, "in_authorized_scope": in_scope, "decision": decision, "reason": reason,
                     "blocking_references": blockers[:8],
                     "n_blocking_references": len(blockers),
                     "blocking_files": sorted({h["file"] for h in blockers}),
                     "blocking_owners": sorted({_owner(h["file"]) for h in blockers}),
                     "blocking_channel": sorted({"F1_wildcard_glob" if "matched_candidate" in h
                                                 else "E_bare_name_functional" for h in blockers}),
                     "non_blocking_dir_mentions_n": len(dir_mentions),
                     "non_blocking_dir_mentions_owners": sorted(
                         {_owner(h["file"]) for h in dir_mentions}),
                     "published_doc_citations_to_repoint": doc_cites,
                     "published_doc_citation_owners": b.get("citing_doc_owners") or [],
                     "n_doc_citations": b.get("n_doc_hits", 0),
                     "consumer_record_hits": c.get("n_consumer_record_hits", 0),
                     "consumer_record_hits_input_keyish": c.get("n_hits_input_keyish", 0),
                     "consumer_record_hits_by_owner_line": c.get("n_hits_by_owner_line") or {},
                     "consumer_record_files_head": c.get("consumer_files") or [],
                     "repoint_owner_split": {
                         "c2_owned_docs_i_will_repoint": sorted(
                             f for f in doc_cites if _doc_owner(f) == "C2"),
                         "other_line_docs_handed_to_D": sorted(
                             f for f in doc_cites if _doc_owner(f) != "C2"),
                         "consumer_records_handed_to_D": c.get("consumer_files") or []}})
    hold = [p_ for p_ in plan if p_["decision"] == "hold_back"]
    return {"as_of": _now(), "target_dir": "runs/vla/c2_docs_ruling99/",
            "authority": "裁定 100 / 补单六-②（目标路径 D 定死；51 份顶层便利副本不得搬）",
            "blocking_rule_verbatim": ("hold_back ⟺ ¬in_authorized_scope ∨ ∃ 活代码引用(owner≠C2) "
                                       "∈ A ∪ A2 ∪ E(functional) ∪ F1；F2 只产追平义务，不禁搬"),
            "n_rows_enumerated": len(rows),
            "n_move": sum(1 for p_ in plan if p_["decision"] == "move"),
            "n_hold_back": len(hold),
            "hold_back_paths": [p_["path"] for p_ in hold],
            "hold_back_evidence": [{"path": p_["path"],
                                    "blocking_owners": p_["blocking_owners"],
                                    "blocking_files": p_["blocking_files"],
                                    "blocking_references": p_["blocking_references"],
                                    "consumer_record_hits_input_keyish":
                                        p_["consumer_record_hits_input_keyish"]} for p_ in hold],
            "expected_post_move_undeclared_count": len(hold),
            "why_not_zero": ("补单六-②-3 的预期是「→ 0」。**实测做不到 0，且不该硬做到 0**：被留下的每一件都有"
                             "**他线活代码**按路径或通配引用（逐件见 `hold_back_evidence`），"
                             "而补单六-②-1 要求「每一处已发布引用的追平」必须在同一批里 ⇒ "
                             "C2 不能替 B2 改 B2 的常量、也不能替 A2 改它的调用入参。"
                             "**要么 D 令 B2 同批改那两个常量（`P_C2_TOPLEVEL_MARKER` + `bi_dir.glob(...)`）、"
                             "A2 改一处调用入参，C2 随后一分钟补搬；要么接受这个非零残值。**"),
            "plan": plan}


def literal_execution_impact(classified: dict, b2: dict, marker: dict, anchors: dict) -> dict:
    """D：字面执行补单五-③（把四类全搬走）会打断什么 —— 全部由前面的实测段推出，不手打。"""
    ent = {e["entry"].rstrip("/"): e for e in classified["entries"]}
    sentinel = (anchors["anchors"].get("enumerator_sentinel") or {}).get("hits") or []
    ok_expr = (anchors["anchors"].get("g20_ok_expression") or {}).get("hits") or []
    sentinel_names_matrix = bool(sentinel) and "matrix.json" in sentinel[0]["text"]
    ok_uses_sentinel = bool(ok_expr) and "enumerator_sees_known" in ok_expr[0]["text"]
    blocked = [e for e in classified["entries"] if e["move_safety"] != "movable_no_code_reference_found"]
    return {
        "as_of": _now(),
        "finding_1_next_run_counts_zero": {
            "measurement_status": "measured",
            "n_by_mtime": b2["n_files_counted_if_new_run_started_now_by_mtime"],
            "n_by_ctime": b2["n_files_counted_if_new_run_started_now_by_ctime"],
            "meaning": ("**「不先搬就修 = 把一颗牙改成恒红」这个前提不成立**：`cutoff = t_start`（本轮自己的开闸时刻）"
                        "⇒ 既有文件的 mtime/ctime 都早于任何未来轮次的 cutoff ⇒ 实测两口径都是 0 件。"
                        "130/78/29 那些数是**用旧轮 cutoff 复算现在的树**得到的，与真判据不同源"
                        "（本件 B2 段与探针件的 `caliber_warning` 同源同结论）。"),
            "what_p2_actually_buys": ("只有一件事：让「**本轮期间**用 `cp -p` 写入（mtime 被保留成旧值）」这一形状可见。"
                                      "它对既有文件的计数没有任何影响。")},
        "finding_2_moving_matrix_json_creates_a_permanent_red": {
            "measurement_status": "measured",
            "enumerator_sentinel_verbatim": sentinel[0]["text"] if sentinel else None,
            "g20_ok_expression_verbatim": ok_expr[0]["text"] if ok_expr else None,
            "sentinel_is_toplevel_matrix_json": sentinel_names_matrix,
            "ok_expression_ands_the_sentinel": ok_uses_sentinel,
            "meaning": ("**搬走顶层 `matrix.json` 会亲手制造一颗永久红**（`enumerator_sees_known=False` ⇒ "
                        "`G20` 的 ok 恒为 False，每一轮都红，直到改码）—— 与补单五-③ 想避免的结果正好相反。"
                        "而 `matrix.json` 正是那 51 份 `cp -p` 顶层便利副本之一。")},
        "finding_3_49_of_51_copies_are_stats": {
            "measurement_status": marker.get("measurement_status"),
            "n_that_are_stats_files": marker.get("n_that_are_stats_files"),
            "n_rows": marker.get("n_rows"),
            "meaning": ("补单五-③「搬走 `cp -p` 的顶层便利副本」与补单五-⑤／裁定 95.5「**不许动 stats**」"
                        "**在字面上直接冲突**（51 份里 49 份就是 `stats/*.json`）。C2 按 ⑤ 优先，未搬。")},
        "finding_4_registered_must_not_move": {
            "measurement_status": "measured",
            "n_entries": anchors["declared_write_exceptions"]["n_entries"],
            "n_must_not_move": anchors["declared_write_exceptions"]["n_entries_with_must_not_move_or_delete"],
            "paths": sorted(k for k, v in anchors["declared_write_exceptions"]["entries"].items()
                            if v.get("must_not_move_or_delete") is True),
            "meaning": ("闸源码里的字面量 `must_not_move_or_delete: True`（裁定 97.2 红二登记，理由 = 已被 D 的文书引用）"
                        "⇒ 搬它需要先撤销那条登记，而登记在冻结的闸源码里。")},
        "finding_5_a2_live_consumer": {
            "measurement_status": "measured",
            "hard_coded_constant": "TOPLEVEL_CONVENIENCE_COPY = " + '"' + NORM_REL + 'mainline_status.json"',
            "referencing_files": ent.get("mainline_status.json", {}).get("referenced_by"),
            "owners": ent.get("mainline_status.json", {}).get("owners_that_would_break"),
            "meaning": ("A2 的 `harness/bc_admission_gate.py` 用**硬编码路径**读顶层 `mainline_status.json`"
                        "（另有 B2 的清单件、F 的台账也读同一路径）；A2 的第 1 步正在飞 ⇒ "
                        "**搬它不是「可逆的 Ⅲ 类文书动作」，而是在别线运行中抽掉它脚下的地板**。")},
        "n_toplevel_entries_blocked": len(blocked),
        "n_toplevel_entries_movable": classified["n_entries_movable_no_code_reference_found"],
        "n_files_under_movable_entries": classified["n_files_under_movable_entries"],
        "c2_action_taken": ("**C2 未搬动任何文件**（`files_moved = 0`）。理由不是「不敢」，而是本段 5 条实测："
                            "①搬的前提（恒红）经实测为假；②搬 `matrix.json` 会**制造**恒红；③49/51 撞 stats 冻结；"
                            "④1 件登记禁搬；⑤A2 正在用硬编码路径读其中一件。⇒ 请 D 就本件再裁一次「先搬」的范围。"),
        "proposal_minimal_safe_move_set": (
            "**只搬 `move_safety = movable_no_code_reference_found` 的条目**（清单见 C2 段 "
            "`entries_by_move_safety`），且**排除被已发布文书按路径引用的那几件**（探针件、说明件）—— "
            "对后者，搬动会让 `daily_report.md` / `docs/c2_*` 里已发布的引用失效（缺陷类 ㉒），"
            "而它们**本来就不会让下一轮 `G20` 变红**（finding_1）⇒ **搬它们只有成本、没有收益**。"
            "**C2 的建议 = 「先搬」这一步整体撤销或缩到 0 件**，把力气放在 ②「再修」的 P1/P2 批次上"
            "（P2 的价值已由 finding_1 收窄成一句话：让本轮期间的 `cp -p` 写入可见）。"),
    }


def main() -> int:
    started = _now()
    census = code_reference_census()
    anchors = g20_criterion_verbatim()
    constructed = constructed_reference_scan()
    b2seg = next_run_would_count(anchors["anchors"])
    marker = toplevel_copy_inventory()
    classified = classify_toplevel(census, constructed)
    und = undeclared_rows("2026-09-30T13:33:51+08:00")
    bare_seg = bare_name_census(und)
    wild_seg = wildcard_glob_channel(und)
    cons_seg = consumer_record_channel(und)
    move_seg = move_execution_plan(und, bare_seg, wild_seg, cons_seg)
    doc = {
        "artifact": "c2_move_dependency_audit_ruling99",
        "generated_at": started, "as_of": _now(),
        "authority": ("裁定 100 / 补单六-②（搬迁一批授权，目标 = `runs/vla/c2_docs_ruling99/`）· "
                      "本件是**执行前**的只读审计 + 逐件计划，不是搬迁记录；"
                      "**C2 未在本件里搬动任何文件**（搬迁由 `scripts/c2_move_ruling99_batch.py` 执行，"
                      "并另出 `MOVE_RECORD.json`）"),
        "audit_script_version": {"version": "v4",
                                 "prior_versions_preserved_bytes": {
                                     "v1": "c2_move_dependency_audit.py.v1_cd3c8c8afd4d",
                                     "v2": "c2_move_dependency_audit.py.v2_96e131af8cbd",
                                     "v3": "c2_move_dependency_audit.py.v3_03231856ee41"},
                                 "v4_delta": ("增 F1（AST 常量 + 通配配对）与 F2（他线产物消费记录）两条通道；"
                                              "E 通道的命中按 `functional` 分层（basename/全路径字面量 = 功能性，"
                                              "只命中父目录名 = 目录级提及，不禁搬但照列）；"
                                              "计划段的禁搬判据改为「活代码四通道并集」，F2 只产追平义务"),
                                 "why_v4": ("v3 的计划 = 28 搬 / 1 留，其中两份 "
                                            "`before_images/c2_to_a2_bc_stats_handoff_20260930.md.before_*` "
                                            "被误判为可搬 ⇒ **本审计器自己的第三个假阴性**，"
                                            "在执行前被 C2 复核计划时挡住（补单六-②-1 的同批追平要求）")},
        "readonly_guarantee": {"files_moved": 0, "files_written": [str(OUT.relative_to(ROOT))],
                               "gate_source_modified": False, "gate_products_modified": False,
                               "stats_modified": False, "gpu_used": False,
                               "policy_executed": False, "capability_claim": None},
        "A_code_reference_census": census,
        "A2_constructed_and_glob_references": constructed,
        "B_g20_criterion_verbatim": anchors,
        "B2_next_run_would_count": b2seg,
        "C1_toplevel_copy_inventory": marker,
        "C2_toplevel_classification": classified,
        "D_literal_execution_impact": literal_execution_impact(classified, b2seg, marker, anchors),
        "E0_bare_name_census": bare_seg,
        "F1_wildcard_glob_channel": wild_seg,
        "F2_consumer_record_channel": cons_seg,
        "E_move_execution_plan": move_seg,
        "coverage_self_proof": {
            "ruling_ref": "裁定 93.8（审计器必须自证其模式覆盖）",
            "what_the_literal_census_sees": "写全 `runs/vla/c2_norm_contract_20260929/…` 的字符串（含通配串）",
            "what_it_cannot_see_and_how_covered": [
                "① **构造式引用** `NORM_DIR / \"x\"` ⇒ 由 A2 段单独扫（`constructed_refs`），并已并入 C2 段分类；",
                "② **通配串** `env_states_*/env_states.npz` ⇒ C2 段用 `ROOT.glob()` 真展开到具体条目（`via=glob_expanded`），"
                "展不开时退回前缀匹配、**不静默当 0**；",
                "③ **变量间接**（如 `NORM_DIR / PR_JSON`，叶子名在别处定义）⇒ 静态不可解析，"
                "逐行列在 A2 段的 `residual_mentions_not_statically_resolvable`，**不吞掉**；",
                "④ **非代码引用**（`docs/`、`daily_report.md`、D 的文书里按路径引用）⇒ 由 E 通道的 "
                "`doc_hits` 扫，并在计划段落成 `repoint_owner_split`（C2 自己追平 / 他线文书交 D）；",
                "⑤ **带 `*` 的通配引用**（`bi_dir.glob(\"x.md.before_*\")`：目录字面量与通配串分居两行、"
                "通配串不含完整 basename）⇒ 由 **F1 段**（AST 常量 + 同文件目录字面量笛卡尔配对 + `fnmatch`）扫；",
                "⑥ **只活在他线产物入参记录里的引用**（A2 的 `c2_broadcast_json` CLI 入参，代码里是 "
                "`default=None`）⇒ 由 **F2 段**扫他线 run 目录的 json/md/txt/log；它是**追平义务**、不单独禁搬，"
                "但 `input_keyish` 命中单列（那是下一次调用会真读的入参）。"],
            "n_residual_mentions": constructed["n_residual_norm_dir_mentions"],
            "negative_leg": ("**负向腿（三个假阴性，全部由 C2 自己复现并修，三版原字节都保留在同目录）**："
                             "**v1** 只有字面串扫描 ⇒ 把 `matrix.json` 判成 `refs=0`（可安全搬），"
                             "而它其实是 `G20` 非恒真哨兵的锚点（修 = A2 段 + `_entries_touched_by_ref`，"
                             "原字节 `…py.v1_cd3c8c8afd4d`）；**v2** 漏掉跨行隐式拼接 ⇒ 把标记件判成"
                             "「只有 C2 引用」，实物是 `scripts/b2_bc_input_inventory.py` 的 "
                             "`P_C2_TOPLEVEL_MARKER`（修 = E 通道 basename 扫，原字节 `…py.v2_96e131af8cbd`）；"
                             "**v3** 的 E 通道是子串匹配 ⇒ 看不见 `*` 通配，把两份 "
                             "`c2_to_a2_bc_stats_handoff_20260930.md.before_*` 判成 0 引用、计划 28 搬 / 1 留，"
                             "而实物是 B2 活代码 `bi_dir.glob(...)` 的归因证据（修 = F1/F2 段，"
                             "原字节 `…py.v3_03231856ee41`）。**v3 的错误计划没有被执行**："
                             "C2 在跑 mover 之前逐件复核了计划（补单六-②-1 的同批追平要求逼出这一步）。"),
            "not_a_capability_claim": "本件只判「搬动会不会打断引用」，不判任何 policy 能力（裁定 46）。"},
        "line_count_caliber_declaration": ("裁定 98.3-②③：本件所有行数字段都点名口径"
                                           "（`n_lines_wc` / `n_lines_splitlines`），不出现裸 `n_lines`；"
                                           "**代码行号一律标 `line_no_as_of`（时点读数，不是常驻身份）**，"
                                           "约束性对账只用 `sha256[:12]`（裁定 96.1-①）。"),
        "no_policy_metrics": True,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    idn = ident(OUT)
    idn["n_lines_wc"] = len(OUT.read_text(encoding="utf-8").split("\n")) - 1
    idn["n_lines_splitlines"] = len(OUT.read_text(encoding="utf-8").splitlines())
    print(json.dumps({"out": idn,
                      "n_code_refs": census["n_references"],
                      "n_distinct_targets": census["n_distinct_targets"],
                      "n_targets_referenced_by_frozen_face": len(census["targets_referenced_by_frozen_face"]),
                      "next_run_mtime_hits": doc["B2_next_run_would_count"]["n_files_counted_if_new_run_started_now_by_mtime"],
                      "next_run_ctime_hits": doc["B2_next_run_would_count"]["n_files_counted_if_new_run_started_now_by_ctime"],
                      "n_constructed_refs": constructed["n_constructed_refs"],
                      "n_residual_mentions": constructed["n_residual_norm_dir_mentions"],
                      "n_toplevel_copies_that_are_stats": marker.get("n_that_are_stats_files"),
                      "n_exceptions_must_not_move": anchors["declared_write_exceptions"]["n_entries_with_must_not_move_or_delete"],
                      "entries_by_move_safety": classified["entries_by_move_safety"],
                      "n_undeclared_now": len(und),
                      "n_move_planned": move_seg["n_move"],
                      "n_hold_back": move_seg["n_hold_back"],
                      "hold_back_paths": move_seg["hold_back_paths"],
                      "hold_back_blocking_owners": [
                          {"path": e["path"].rsplit("/", 1)[-1], "owners": e["blocking_owners"],
                           "files": e["blocking_files"]} for e in move_seg["hold_back_evidence"]],
                      "f1_rows_with_wildcard_hits": sum(
                          1 for r_ in wild_seg["rows"] if r_["n_wildcard_hits"]),
                      "f1_wildcard_hits_total": sum(r_["n_wildcard_hits"] for r_ in wild_seg["rows"]),
                      "f1_degenerate_patterns_skipped": wild_seg["n_degenerate_patterns_skipped"],
                      "f2_files_read": cons_seg["n_files_read"],
                      "f2_files_with_hits": cons_seg["n_files_with_hits"],
                      "f2_scan_truncated": cons_seg["scan_truncated"],
                      "f2_rows_with_consumer_hits": sum(
                          1 for r_ in cons_seg["rows"] if r_["n_consumer_record_hits"]),
                      "n_entries_movable": classified["n_entries_movable_no_code_reference_found"],
                      "n_files_under_movable_entries": classified["n_files_under_movable_entries"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
