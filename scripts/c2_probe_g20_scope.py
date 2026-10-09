#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`G20_write_scope` 的**枚举作用域 + 时间窗**自证探针（回答 E §E13.2 末那条给 C2/F 的疑问）。

纪律：
* **只读**闸与闸产物；**只写**自己的探针目录（`runs/vla/c2_docs_ruling99/probe_g20_scope_ruling98/`）。
  **路径已按 裁定 100 / 补单六-② 搬迁**（原在 `runs/vla/c2_norm_contract_20260929/` 下 ⇒ 落在 `G20`
  的枚举根里、会被下一轮全量闸数成未申报写入）。搬迁逐件对账见
  `runs/vla/c2_docs_ruling99/MOVE_RECORD.json`（`mv` 不改字节 ⇒ 搬前/搬后 `sha256[:12]` 相同）。
  **⇒ 本探针从此不再往 `NORM_DIR` 里写任何东西**（`NORM_DIR` 仍只读地枚举）。
* **不改闸、不新增 check、不改判据形态**（裁定 97.3-5 的冻结令 + 裁定 98.6 的 C2 停点）。
  本探针发现的两条待改项一律登记为 `proposed_for_D`（待裁），**不当场落码**。
* 每个数字都由本进程工具取值（裁定 92.3(i)）；行数一律**点名口径**（裁定 98.3-②③）。
* 三值纪律：没测到写 `not_measured`，不写 0 / false 冒充「测过没有」。
* 不含任何 policy 指标（裁定 46）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
NORM_DIR = ROOT / "runs/vla/c2_norm_contract_20260929"
GATE_SRC = ROOT / "scripts/c2_gate_norm_contract.py"
TARGET_RUN = NORM_DIR / "gate/run_20260930_133156"
# 裁定 100 / 补单六-②：探针目录搬出 `NORM_DIR`（目标路径 D 定死 = `runs/vla/c2_docs_ruling99/`）。
# 追平这一处常量就是补单六-②-1 要求的「已发布引用的追平」之一；改前身份 = `e9abbacb9f68`（前像
# `runs/vla/c2_docs_ruling99/before_images/c2_probe_g20_scope.py.before_e9abbacb9f68`）。
PROBE_DIR = ROOT / "runs/vla/c2_docs_ruling99/probe_g20_scope_ruling98"

# E §E13.2 点名的三件（作为「作用域外」的实物阴性对照）
E_FILES = [
    ROOT / "runs/infra/e_gpu_render_reverify_20260930/CARD_BUSY_ARTIFACT_PRESENCE_PROOF_97_7_2.json",
    ROOT / "runs/infra/e_gpu_render_reverify_20260930/GPU_RENDER_REVERIFY_AND_INCIDENT.json",
    ROOT / "runs/infra/e_gpu_render_reverify_20260930/make_reverify_artifacts.py",
]
C2_TMP_LOG = ROOT / "tmp/c2_gate_full_ruling97.log"

# 窗口扫描的作用域**必须显式声明**（裁定 93.8：审计器必须自证其模式覆盖）
WINDOW_SCAN_ROOTS = ["runs", "docs", "work", "harness", "scripts", "tmp", "registry",
                     "rl_harness_supervision", "daily_report.md"]
WINDOW_SCAN_EXCLUDED = [".git（版本库内部件，不属任何线的写入面）",
                        "runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/（本闸自己的 run 目录，G20 本来就排除）"]


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _localize(stamp: str) -> _dt.datetime:
    """`YYYY-mm-dd HH:MM:SS` → 带本地时区的 aware datetime（本机时区实测取，不手写 +08:00）。"""
    return _dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=_dt.datetime.now().astimezone().tzinfo)


def _ident(path: pathlib.Path) -> dict:
    """单遍取身份；行数**两个口径都给**并点名（裁定 98.3）。"""
    out: dict = {"path": str(path.relative_to(ROOT)) if path.is_absolute() else str(path),
                 "measurement_status": "not_measured"}
    if not path.exists():
        out["why"] = "路径不存在（读不到 ≠ 测到没有）"
        return out
    st = path.stat()
    h = hashlib.sha256()
    n_bytes = n_nl = 0
    tail = b""
    with path.open("rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
            n_bytes += len(b)
            n_nl += b.count(b"\n")
            tail = b[-1:]
    out.update({
        "measurement_status": "measured", "bytes": n_bytes, "sha256_12": h.hexdigest()[:12],
        "n_lines_wc": n_nl, "n_lines_splitlines": n_nl + (0 if tail.endswith(b"\n") or n_bytes == 0 else 1),
        "ends_with_newline": bool(tail.endswith(b"\n")),
        "n_lines_caliber": "n_lines_wc = 换行符个数（`wc -l`）；n_lines_splitlines = len(read_text().splitlines())",
        "mtime": _dt.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds"),
        "ctime": _dt.datetime.fromtimestamp(st.st_ctime).astimezone().isoformat(timespec="seconds"),
    })
    return out


def source_anchors() -> dict:
    """把判据原文的**行号 + 逐字行**由工具取出来（不手打引用）。"""
    lines = GATE_SRC.read_text(encoding="utf-8").splitlines()
    pats = {
        "norm_dir_definition": r"^NORM_DIR\s*=",
        "gate_root_definition": r"^GATE_ROOT\s*=",
        "t_start_assignment": r"^\s*t_start\s*=\s*time\.time\(\)",
        "run_dir_mkdir": r"^\s*run_dir\.mkdir\(",
        "cutoff_assignment": r"^\s*cutoff\s*=\s*t_start",
        "touched_loop": r"for p in NORM_DIR\.rglob",
        "mtime_test": r"st_mtime\s*>=\s*cutoff",
        "enumerated_comprehension": r"enumerated = \[p for p in NORM_DIR\.rglob",
        "enumerator_self_check": r"enumerator_sees_known\s*=",
        "g20_add": r'gate\.add\("G20_write_scope"',
    }
    out: dict = {"source_file": str(GATE_SRC.relative_to(ROOT)),
                 "source_identity": _ident(GATE_SRC)}
    for name, pat in pats.items():
        hits = [{"line_no": i + 1, "verbatim": lines[i].strip()}
                for i in range(len(lines)) if re.search(pat, lines[i])]
        out[name] = {"n_hits": len(hits), "hits": hits,
                     "measurement_status": "measured" if hits else "not_found"}
    return out


def extract_g20(product: pathlib.Path) -> dict:
    """从 ~99 MB 的 `gate_verdict.json` 里**流式**取出 G20 那一条记录（裁定 97.4 体积纪律）。"""
    pat = re.compile(rb'"id"\s*:\s*"G20_write_scope"')
    tail = b""
    with product.open("rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            w = tail + b
            m = pat.search(w)
            if m:
                frag = w[w[:m.start()].rfind(b"{"):]
                depth = 0
                instr = esc = False
                endp = None
                for i, ch in enumerate(frag):
                    c = chr(ch)
                    if instr:
                        if esc:
                            esc = False
                        elif c == "\\":
                            esc = True
                        elif c == '"':
                            instr = False
                        continue
                    if c == '"':
                        instr = True
                    elif c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            endp = i + 1
                            break
                if endp:
                    return {"measurement_status": "measured",
                            "record": json.loads(frag[:endp].decode("utf-8", "replace"))}
            tail = w[-8192:]
    return {"measurement_status": "not_found", "record": None}


def parse_observed(obs: str) -> dict:
    """把 observed 原文里的两个数字解析出来（不重算、只读判词）。"""
    m_written = re.search(r"run 目录外被写文件数=(\d+)", obs or "")
    m_enum = re.search(r"枚举到 (\d+) 个文件", obs or "")
    m_undecl = re.search(r"未声明=(\d+)", obs or "")
    return {"n_written_from_verbatim": int(m_written.group(1)) if m_written else None,
            "n_undeclared_from_verbatim": int(m_undecl.group(1)) if m_undecl else None,
            "n_enumerated_from_verbatim": int(m_enum.group(1)) if m_enum else None,
            "caliber": "以上三数**逐字取自判词原文**，不是本探针重算"}


def g20_history() -> dict:
    rows = []
    for run in sorted((NORM_DIR / "gate").glob("run_*")):
        product = run / "gate_verdict.json"
        if not product.exists():
            rows.append({"run": run.name, "measurement_status": "not_measured",
                         "why": "无 gate_verdict.json（早期中断轮）"})
            continue
        got = extract_g20(product)
        rec = got.get("record") or {}
        obs = rec.get("observed")
        row = {"run": run.name, "measurement_status": got["measurement_status"],
               "ok": rec.get("ok"), "status": rec.get("status"),
               "triage_class": rec.get("triage_class")}
        row.update(parse_observed(obs))
        row["observed_verbatim"] = obs
        rows.append(row)
    tp = [r["run"] for r in rows
          if (r.get("n_written_from_verbatim") or 0) > 0 or r.get("status") == "RED"]
    return {"n_runs_scanned": len(rows),
            "rows": rows,
            "true_positive_runs": tp,
            "n_true_positive_runs": len(tp),
            "conclusion": ("**非恒真已由实物真检出证明**（不只是枚举器自检）："
                           + ("、".join(tp) if tp else "无") if tp else
                           "全部轮次判词都是 0 ⇒ 非恒真只由枚举器自检支撑")}


def window_scan(win_start: str, win_end: str, reuse: str | None) -> dict:
    argv = ["find", ".", "-path", "./.git", "-prune", "-o", "-type", "f",
            "-newermt", win_start, "!", "-newermt", win_end, "-print"]
    out: dict = {"argv_verbatim": " ".join(argv),
                 "window_start": win_start, "window_end": win_end,
                 "declared_scan_coverage": {"roots_scanned": "整个 `.`（除 .git）",
                                            "excluded": WINDOW_SCAN_EXCLUDED,
                                            "note": ("`find` 从 `.` 起 ⇒ 覆盖比 `WINDOW_SCAN_ROOTS` 更宽；"
                                                     "常量 `WINDOW_SCAN_ROOTS` 只用于归属分类，不用于限制扫描")}}
    t0 = time.time()
    if reuse:
        raw = pathlib.Path(reuse).read_text().splitlines()
        out["mode"] = "reused_list"
        out["reused_from"] = reuse
    else:
        proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        raw = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        out["mode"] = "fresh_find"
        out["find_returncode"] = proc.returncode
        if proc.stderr.strip():
            out["find_stderr_head"] = proc.stderr.strip()[:400]
    out["elapsed_s"] = round(time.time() - t0, 2)
    run_prefix = "./" + str(TARGET_RUN.relative_to(ROOT)) + "/"
    hits = [ln for ln in raw if not ln.startswith(run_prefix)]
    out["n_hits_outside_run_dir_by_mtime"] = len(hits)
    rows = []
    for ln in hits:
        p = ROOT / ln[2:] if ln.startswith("./") else ROOT / ln
        try:
            st = p.stat()
        except OSError as exc:
            rows.append({"path": ln, "measurement_status": "not_measured", "why": type(exc).__name__})
            continue
        mt = _dt.datetime.fromtimestamp(st.st_mtime).astimezone()
        ct = _dt.datetime.fromtimestamp(st.st_ctime).astimezone()
        rel = ln[2:] if ln.startswith("./") else ln
        parts = [x for x in rel.split("/") if x]
        if parts and parts[0] == "tmp":
            owner = "C2（本闸 stdout 重定向）"
        elif len(parts) >= 3 and parts[0] == "runs":
            d = parts[2]                      # `runs/<vla|infra>/<线号_目录>/…`
            key = next((L for L in ("a2_", "b2_", "c2_", "e_", "f_", "d_") if d.startswith(L)), None)
            owner = {"a2_": "A2", "b2_": "B2", "c2_": "C2", "e_": "E",
                     "f_": "F", "d_": "D"}.get(key, "other:" + "/".join(parts[:3]))
        else:
            owner = "other:" + "/".join(parts[:2])
        rows.append({"path": ln, "owner_by_dir_prefix": owner,
                     "mtime": mt.isoformat(timespec="seconds"),
                     "ctime": ct.isoformat(timespec="seconds"),
                     "mtime_in_window": True,
                     "ctime_in_window": bool(_localize(win_start) <= ct <= _localize(win_end)),
                     "classification": None})
    for r in rows:
        if r.get("measurement_status") == "not_measured":
            continue
        r["classification"] = ("真窗口内写入" if r["ctime_in_window"]
                               else "**mtime 被保留的复制件（`cp -p` 形状）⇒ mtime 窗口误报**")
    out["rows"] = rows
    out["n_real_in_window_by_ctime"] = sum(1 for r in rows if r.get("ctime_in_window") is True)
    out["n_mtime_preserved_false_hits"] = sum(1 for r in rows if r.get("ctime_in_window") is False)
    by_owner: dict = {}
    for r in rows:
        if r.get("ctime_in_window") is True:
            by_owner[r["owner_by_dir_prefix"]] = by_owner.get(r["owner_by_dir_prefix"], 0) + 1
    out["real_in_window_by_owner"] = by_owner
    return out


# D 在 daily_report.md §D98.7-④ 报的未声明写入数 = **转录值**，不是本件实测：D 的枚举脚本不在盘上，
# C2 无法复现它 ⇒ 它只能作为对账的一侧；凡差值一律逐件归因，归不了的如实标 unexplained（三值纪律）。
D_98_7_4_REPORTED_N = 12
D_98_7_4_AS_OF_LO = "2026-09-30T14:31:00+08:00"
D_98_7_4_AS_OF_HI = "2026-09-30T14:36:59+08:00"


def _reconcile_with_d_98_7_4(rows_same_cutoff: list) -> dict:
    """把 D 报的 12 与本件在**同一 cutoff**下枚举到的行逐件对账。

    D 自己在 §D98.7-④ 声明「这个 12 是下界」，给的理由是 cutoff 选择（产物 mtime 13:33:51 而非
    `t_start` 13:31:56）。本件要回答更细的一问：**就在 D 用的那个 cutoff 上**，差值里有多少能用
    「时点不同」解释、有多少不能。不能解释的部分必须留数字、不许抹平（裁定 93.8 同族）。
    """
    lo = _dt.datetime.fromisoformat(D_98_7_4_AS_OF_LO)
    hi = _dt.datetime.fromisoformat(D_98_7_4_AS_OF_HI)
    stamped = [(r, _dt.datetime.fromisoformat(r["mtime"])) for r in rows_same_cutoff]
    pre = [r for r, mt in stamped if mt < lo]
    inwin = [r for r, mt in stamped if lo <= mt <= hi]
    post = [r for r, mt in stamped if mt > hi]
    n_c2 = len(rows_same_cutoff)
    missed = max(0, len(pre) - D_98_7_4_REPORTED_N)
    return {
        "measurement_status": "measured",
        "status": "fully_reconciled" if missed == 0 else "residual_not_explainable_by_timing",
        "cutoff_used_by_both": "产物 mtime 13:33:51（= `per_cutoff.cutoff_product_mtime_D_lower_bound`）",
        "d_reported_n_undeclared_transcript": D_98_7_4_REPORTED_N,
        "d_reported_as_of_window": "14:31–14:36（`daily_report.md` §D98.7 身份行原文）",
        "d_self_declared_reason_for_lower_bound": "D 原文：cutoff 用产物 mtime 而非 `t_start` ⇒ 真跑只会数到更多",
        "c2_n_undeclared_same_cutoff": n_c2,
        "n_rows_mtime_before_d_window": len(pre),
        "n_rows_mtime_inside_d_window": len(inwin),
        "n_rows_mtime_after_d_window": len(post),
        "rows_after_d_window_paths": sorted(r["path"] for r in post),
        "residual_total": n_c2 - D_98_7_4_REPORTED_N,
        "residual_explainable_by_timing_upper_bound": len(inwin) + len(post),
        "n_pre_window_rows_d_must_have_missed": missed,
        "which_rows_d_missed": ("not_derivable —— D 的广播以「等」字收尾、D 的枚举脚本不在盘上 ⇒ "
                                "C2 不指认是哪几件，改为把 D 窗口之前就已存在的全部行逐件列出"),
        "pre_window_rows_all_listed": sorted(r["path"] for r in pre),
        "conclusion": (f"**D 的 12 与本件读数之间的差，不能全部由「cutoff 选择」解释**：就在 D 自己用的那个 "
                       f"cutoff 上，D 的 as_of 窗口（14:31–14:36）**之前就已存在**的行有 {len(pre)} 件，"
                       f"而 D 只报了 {D_98_7_4_REPORTED_N} ⇒ **至少 {missed} 件是 D 的枚举没数到的**。"
                       f"⇒ 给 裁定 99 的权威规模 = 本件的 `c2_n_undeclared_same_cutoff` = {n_c2}"
                       f"（逐件可核、`undeclared_rows_truncated=false`），**不是 12，也不是「12 是下界所以真值未知」**。"
                       f"C2 不据此判 D 错（D 的 12 自称下界、方向一致），只把可核的那一侧交出去。"),
    }


def recount_against_current_tree(t_start_ts: float, product_mtime_ts: float,
                                 marker_path: pathlib.Path) -> dict:
    """用 **133156 那一轮的 cutoff** 对 **现在盘上的树** 复算 `G20` 的未声明写入数。

    ⚠ **口径（必须点名，否则就是把假设写成事实）**：这**不是**「下一轮重跑会数出多少」——
    下一轮的 cutoff 是它**自己的**开闸时刻，本件无法预测。本件回答的是 D 在 §D98.7-④ 问的那件事：
    **「按现行判据复算，`G20` 潜在红的确切规模有多大」**。
    判据逐字复现（枚举根 `NORM_DIR`、**排除该轮自己的 run 目录**、`mtime >= cutoff`、不在
    `G20_DECLARED_WRITE_EXCEPTIONS` 里）—— **只读、不改判据**。两个 cutoff 都给：
    真判据用 `t_start`（开闸时刻 13:31:56），D 在 §D98.7-④ 用的是产物 `mtime`（13:33:51，下界口径）。
    """
    out: dict = {"purpose": "裁定 99 的输入（D 在 §D98.7-④ / §D98.8-④ 点名要处置这件事）",
                 "caliber_warning": ("**不是对下一轮重跑的预测**。下一轮的 cutoff = 它自己的开闸时刻 ⇒ "
                                     "现在盘上这些文件的 mtime 全都早于它 ⇒ 真重跑时 `G20` 只会数到"
                                     "**那一轮期间**新写的文件。本件是「用 133156 的 cutoff 复算现在的树」。"),
                 "measurement_status": "not_measured"}
    try:
        spec = importlib.util.spec_from_file_location("c2_gate_readonly_for_exceptions", GATE_SRC)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        exceptions = dict(mod.G20_DECLARED_WRITE_EXCEPTIONS)
    except Exception as exc:                                            # noqa: BLE001
        out["why"] = ("读不到闸的 `G20_DECLARED_WRITE_EXCEPTIONS`："
                      + type(exc).__name__ + ": " + str(exc))
        return out
    refresh: set = set()
    if marker_path.exists():
        try:
            for row in (json.loads(marker_path.read_text(encoding="utf-8"))
                        .get("byte_identity_audit", {}).get("rows") or []):
                if row.get("toplevel_path"):
                    refresh.add(row["toplevel_path"])
        except Exception:                                               # noqa: BLE001
            pass
    files = [p for p in NORM_DIR.rglob("*")
             if p.is_file() and not str(p).startswith(str(TARGET_RUN))]
    per_cutoff = {}
    all_rows: dict = {}
    for tag, cutoff in (("cutoff_t_start_true_criterion", t_start_ts),
                        ("cutoff_product_mtime_D_lower_bound", product_mtime_ts)):
        hit = []
        for p in files:
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff:
                continue
            rel = str(p.relative_to(ROOT))
            hit.append({"path": rel,
                        "declared_exception": rel in exceptions,
                        "is_toplevel_convenience_copy_ruling96_1_4": rel in refresh,
                        "mtime": _dt.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds")})
        undecl = [h for h in hit if not h["declared_exception"]]
        per_cutoff[tag] = {
            "cutoff": _dt.datetime.fromtimestamp(cutoff).astimezone().isoformat(timespec="seconds"),
            "n_files_mtime_at_or_after_cutoff": len(hit),
            "n_declared_exception_hits": len(hit) - len(undecl),
            "n_undeclared": len(undecl),
            "n_undeclared_that_are_toplevel_convenience_copies": sum(
                1 for h in undecl if h["is_toplevel_convenience_copy_ruling96_1_4"]),
            "n_undeclared_that_are_c2_ruling98_docs_or_probes": sum(
                1 for h in undecl if not h["is_toplevel_convenience_copy_ruling96_1_4"]),
            "undeclared_rows_head": sorted(undecl, key=lambda h: h["path"])[:80],
            "n_undeclared_rows_listed": min(len(undecl), 80),
            "undeclared_rows_truncated": len(undecl) > 80,
        }
        all_rows[tag] = undecl
    d_cut = all_rows["cutoff_product_mtime_D_lower_bound"]
    t_cut = all_rows["cutoff_t_start_true_criterion"]
    n_toplevel = sum(1 for h in t_cut if h["is_toplevel_convenience_copy_ruling96_1_4"])
    out.update({"measurement_status": "measured",
                "g20_declared_exceptions_registry": exceptions,
                "caliber": ("**这是「按 mtime 的现行判据」的预测**：裁定 98.10-③（§D98.8-③）已把「只读 "
                            "mtime」定性为真缺陷（P2）⇒ 若同时把判据改成 `mtime ∨ ctime`，计数还会更大"
                            "（本件 `window_scan` 已实测到 51 件 `cp -p` 形状的文件）。"),
                "conclusion": ("⇒ **只要这些非闸产物还留在 `NORM_DIR` 里，任何一轮新的全量闸跑都会把它们中间"
                               "「在该轮期间被写/被复制」的那些数成未声明写入**；但它的 "
                               "`triage_class = 3`（裁定 97.3-4）⇒ 按裁定 97.5 **不单独禁 BC**。"
                               "处置归 裁定 99（D 的倾向 = 把非闸产物移出 `NORM_DIR`）；**C2 不自行搬动**，"
                               "因为搬动会让已发布的引用路径全部失效（那正是缺陷类 ㉒ 的镜像）。"
                               "**规模读数一律以 `per_cutoff` 的实测值为准，下面四个数只是转录轨迹**："
                               "D 报 **12**（as_of 14:31–14:36）→ C2 报 **18**（as_of 15:06）→ C2 报 **19**"
                               "（as_of 15:08:26，已含本件自身）→ **本次重生成实测 "
                               + str(len(d_cut)) + " 件**（同一 cutoff）。每一跳的差 = 该跳新增的前像/保留件"
                               "路径数，逐件可归因，见 `reconciliation_with_D_98_7_4` 与 `self_reference_caveat`。"
                               "**本串写的是运行时计算值 ⇒ 它与 `per_cutoff` 不可能不一致**"
                               "（这正是缺陷类 ㉒「把时点读数当常驻身份」的反面做法）。"),
                "self_reference_caveat": (
                    "**【历史档，as_of 裁定 98/99 那两轮；裁定 100 之后已不成立，见本段末的 `superseded_by_move`】**"
                    "**本件自己就在计数里**：`probe_g20_scope_ruling98/g20_enumeration_scope_probe.json` 是 "
                    "`undeclared_rows_head` 的一行。它在测量完成**之后**才被覆写落盘，而**路径不变** ⇒ "
                    "重跑不会让计数无穷增长（同一路径只算一件）；但**每新增一份前像就 +1**"
                    "（本次重生成新增 `before_images/c2_probe_g20_scope.py.before_2f849d63a7db` 一件，"
                    "`cp -p` 保留源 mtime 15:05:55 ⇒ 晚于两个 cutoff ⇒ 两档都数得到）。"
                    "⇒ 处置 = 在散文里点名这一点，**不去追自己的尾巴**（追的话每次重生成都要再造一份前像 "
                    "= 无穷回归）。**但本轮 C2 追了一次、且只追一次（近失自纠）**：上一版把「本次重生成预测 "
                    "= 20」写死进散文，而实测是 **21** —— 因为除了脚本前像，还多留了上一版产物的保留件 "
                    "`g20_enumeration_scope_probe.v2_1dabd5465c3b.json` ⇒ 已把该串改成**运行时计算值**，"
                    "使它不可能再与 `per_cutoff` 打架。这也是 §D98.8-⑤「活件按 `as_of` 有效、"
                    "不得当现值引用」的一个实例。"
                    "**`superseded_by_move`（裁定 100 / 补单六-②，2026-09-30 17:3x）**：`PROBE_DIR` 已搬到 "
                    "`runs/vla/c2_docs_ruling99/probe_g20_scope_ruling98/`（**在 `NORM_DIR` 之外**）⇒ "
                    "本件与它的前像**都不再进 `G20` 的计数**，上面那段自指告诫对**新的重跑**已不适用；"
                    "它对已落盘的三份产物（`g20_enumeration_scope_probe.json` = `6a1e599b60da` 定稿件 + "
                    "`.v1_0f732c9fd674` / `.v2_1dabd5465c3b` 两份保留件）**仍是当时的真话**，"
                    "按 `as_of` 引用即可。**本轮不重跑本探针**（补单六 §七：不重跑全量闸、不新增 check）⇒ "
                    "定稿件的身份保持 D 在 §100.5 写死的那一组值，只是**路径前缀换了**"
                    "（逐件 sha 相等，见 `MOVE_RECORD.json`）。"),
                "reconciliation_with_D_98_7_4": _reconcile_with_d_98_7_4(d_cut),
                "the_51_copies_are_a_recount_artifact": (
                    f"**{n_toplevel} 件顶层便利副本不是新增污染，是「用旧 cutoff 复算现在的树」这个动作本身的产物**："
                    "裁定 96.1-④ 采甲案时，C2 用 `cp -p` 把 51 份闸产物复制到 `NORM_DIR` 顶层，`cp -p` 保留了"
                    "**源件**的 mtime（13:32:0x）；13:32:0x 晚于真判据的 cutoff `t_start`=13:31:56、"
                    "却早于 D 用的下界 cutoff 13:33:51 ⇒ 它们**只在 `cutoff_t_start_true_criterion` 那一档出现**"
                    f"（该档 {len(t_cut)} = {len(d_cut)} + {n_toplevel}），在 D 的那一档一件都不出现。"
                    "**⇒ 裁定 99 的处置面必须把这两类分开**：这 51 件**必须留在 `NORM_DIR`**"
                    "（它们本身就是被 D 的文书引用的顶层便利副本，搬走 = 让已发布引用失效）；"
                    "**能移出的只有 C2 自己的文书件、探针件与前像**（即 D 那一档数到的那些）。"),
                "per_cutoff": per_cutoff})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PROBE_DIR / "g20_enumeration_scope_probe.json"))
    ap.add_argument("--reuse-window-list", default=None,
                    help="复用已有的 find 输出清单（只为快速迭代；产物会记 mode=reused_list）")
    args = ap.parse_args()

    started = _now()
    product = TARGET_RUN / "gate_verdict.json"
    prod_ident = _ident(product)
    anchors = source_anchors()

    # 窗口 = run 目录名给的开闸时刻 → 产物 generated_at / mtime
    m_run = re.search(r"run_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", TARGET_RUN.name)
    if not m_run:
        raise SystemExit("run 目录名不含时间戳 ⇒ 开闸时刻无从取值（不猜、不手打）")
    win_start = "%s-%s-%s %s:%s:%s" % m_run.groups()
    head = product.open("rb").read(4096).decode("utf-8", "replace")
    m_gen = re.search(r'"generated_at"\s*:\s*"([^"]+)"', head)
    generated_at = m_gen.group(1) if m_gen else None
    if not prod_ident.get("mtime"):
        raise SystemExit("产物 mtime 取不到 ⇒ 窗口右端无从取值（不猜）")
    win_end_arg = (_dt.datetime.fromisoformat(prod_ident["mtime"])
                   + _dt.timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")

    # 枚举器复现（as_of 现在）
    t0 = time.time()
    enum = [p for p in NORM_DIR.rglob("*") if p.is_file() and not str(p).startswith(str(TARGET_RUN))]
    enum_set = set(enum)
    repl = {"as_of": _now(), "elapsed_s": round(time.time() - t0, 2),
            "enumerator_root": str(NORM_DIR.relative_to(ROOT)),
            "n_enumerated_now": len(enum),
            "all_under_norm_dir": all(str(p).startswith(str(NORM_DIR)) for p in enum),
            "enumerator_sees_matrix_json": (NORM_DIR / "matrix.json") in enum_set,
            "n_enumerated_from_verbatim_at_gate_time": None,
            "delta_vs_gate_time": None}

    g20 = extract_g20(product)
    rec = g20.get("record") or {}
    obs_parsed = parse_observed(rec.get("observed"))
    repl["n_enumerated_from_verbatim_at_gate_time"] = obs_parsed["n_enumerated_from_verbatim"]
    if obs_parsed["n_enumerated_from_verbatim"] is not None:
        repl["delta_vs_gate_time"] = len(enum) - obs_parsed["n_enumerated_from_verbatim"]
        # 差额必须**逐件归因**，不然就是一个说不清的数（裁定 93.8 同族）
        prod_ct = _dt.datetime.fromisoformat(prod_ident["ctime"])
        post = [p for p in enum if _dt.datetime.fromtimestamp(p.stat().st_ctime).astimezone() >= prod_ct]
        # 就地覆盖的那一批（裁定 96.1-④ 甲案 = 顶层 51 件刷新）必须单列，否则差额对不平
        marker_path = NORM_DIR / "TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json"
        marker_ident = _ident(marker_path)
        marker_rows: list = []
        if marker_path.exists():
            try:
                marker_rows = (json.loads(marker_path.read_text(encoding="utf-8"))
                               .get("byte_identity_audit", {}).get("rows") or [])
            except Exception as exc:                                   # noqa: BLE001
                marker_ident["marker_parse_error"] = type(exc).__name__ + ": " + str(exc)
        refresh_set = {(ROOT / r["toplevel_path"]).resolve()
                       for r in marker_rows if r.get("toplevel_path")}
        post_resolved = {p.resolve(): p for p in post}
        overwritten = [str(post_resolved[k].relative_to(ROOT)) for k in refresh_set if k in post_resolved]
        by_sub: dict = {}
        for p in post:
            relp = p.relative_to(NORM_DIR)
            key = relp.parts[0] if len(relp.parts) > 1 else "(NORM_DIR 根)"
            by_sub[key] = by_sub.get(key, 0) + 1
        repl["delta_accounting"] = {
            "n_delta": repl["delta_vs_gate_time"],
            "n_enumerated_files_with_ctime_at_or_after_product_ctime": len(post),
            "n_of_those_that_are_in_place_overwrites": len(overwritten),
            "n_of_those_that_are_newly_created": len(post) - len(overwritten),
            "fully_accounted": repl["delta_vs_gate_time"] == len(post) - len(overwritten),
            "residual_unexplained": repl["delta_vs_gate_time"] - (len(post) - len(overwritten)),
            "why_a_naive_count_does_not_close": ("「ctime 变新的文件数」≠「枚举数的增量」：裁定 96.1-④ 采甲案时，"
                                                 "顶层 51 件是**就地覆盖**已存在的旧件（旧件本来就在闸时的枚举里）⇒ "
                                                 "它们 ctime 变新但**不增加**枚举数。必须把这 51 件单列出来，差额才对得平。"),
            "in_place_overwrite_evidence": {
                "source": "标记件 `byte_identity_audit.rows[].toplevel_path`（51 条，机器核过 51/51 逐字节相同）",
                "marker_identity": marker_ident,
                "n_rows": len(marker_rows),
                "n_rows_with_ctime_at_or_after_product_ctime": len(overwritten),
                "sample_paths": [str(x) for x in overwritten[:3]],
                "caliber": "同一批路径既在 `post` 里、又在标记件的 51 行里 ⇒ 判为就地覆盖而不是新建。",
            },
            "by_first_level_subdir": dict(sorted(by_sub.items(), key=lambda kv: -kv[1])),
            "caliber": ("`ctime`（inode 变更时刻，**不被 `cp -p` 保留**）≥ 产物 ctime ⇒ 判为「闸退出后才落盘」。"
                        "差额 = 现在的枚举数 − 判词里的枚举数。"),
        }

    # 两向哨兵（全部用**盘上已有的实物**，不在作用域外造任何文件）
    sentinel = {
        "design": ("阳性对照必须被枚举到、阴性对照必须不被枚举到；**阴性对照用的是 E 的实物**，"
                   "不往 `runs/infra/` 或任何别人的目录写一个字节（裁定 97.2 红二的同族纪律）"),
        "positive_control": {
            "path": str((NORM_DIR / "matrix.json").relative_to(ROOT)),
            "expected_in_enumerated": True,
            "measured_in_enumerated": (NORM_DIR / "matrix.json") in enum_set,
        },
        "negative_controls": [],
    }
    for p in E_FILES + [ROOT / "daily_report.md", C2_TMP_LOG]:
        sentinel["negative_controls"].append({
            "path": str(p.relative_to(ROOT)),
            "expected_in_enumerated": False,
            "measured_in_enumerated": p in enum_set,
            "exists_on_disk": p.exists(),
            "identity": _ident(p),
        })
    sentinel["positive_control_pass"] = (sentinel["positive_control"]["measured_in_enumerated"]
                                        is sentinel["positive_control"]["expected_in_enumerated"])
    sentinel["negative_controls_pass"] = all(n["measured_in_enumerated"] is n["expected_in_enumerated"]
                                            for n in sentinel["negative_controls"])
    sentinel["all_pass"] = bool(sentinel["positive_control_pass"] and sentinel["negative_controls_pass"])

    # 时序反事实：E 的三件是否**可能**被那一轮 G20 看到
    e_ts = []
    for p in E_FILES:
        idn = _ident(p)
        e_ts.append({"path": idn["path"], "mtime": idn.get("mtime"), "ctime": idn.get("ctime")})
    prod_mtime_dt = _dt.datetime.fromisoformat(prod_ident["mtime"])
    timing = {
        "gate_window": {"start_from_run_dir_name": win_start,
                        "product_generated_at": generated_at,
                        "product_mtime": prod_ident["mtime"],
                        "caliber": "开闸时刻取自 run 目录名（`t_start = time.time()` 紧随 `run_dir.mkdir()`，见 source_anchors）"},
        "e_files": e_ts,
        "e_writes_after_product_s": [
            {"path": r["path"],
             "seconds_after_product_mtime": (round((_dt.datetime.fromisoformat(r["mtime"]) - prod_mtime_dt).total_seconds(), 1)
                                             if r.get("mtime") else None)} for r in e_ts],
        "conclusion": None,
    }
    all_after = all((r["seconds_after_product_mtime"] or 0) > 0 for r in timing["e_writes_after_product_s"])
    timing["all_e_writes_after_gate_exit"] = all_after
    timing["conclusion"] = ("**E 的三件写在闸进程已退出之后**（产物 mtime 之后 "
                            + str(min(r["seconds_after_product_mtime"] for r in timing["e_writes_after_product_s"]))
                            + " s 起）⇒ 即使把枚举作用域扩到全仓，那一轮 G20 也**不可能**看到它们。"
                            if all_after else "存在窗口内的 E 写入，需逐件定性")

    # `cp -p` 盲点：mtime 窗口 vs ctime
    tl = NORM_DIR / "mainline_status.json"
    arm = TARGET_RUN / "arm_mainline/mainline_status.json"
    cpp = {"claim": ("G20 的时间测试是 `st_mtime >= cutoff`（见 source_anchors.mtime_test，**只读 mtime**）⇒ "
                     "一次**保留 mtime 的复制**（`cp -p`）落进 `NORM_DIR` 时，即便发生在闸跑期间也不会被计数。"),
           "epistemic_status": ("**源码判据直读 + 实物 mtime/ctime 实测**；C2 **没有**构造行为型变异体去实跑"
                                "（往 run 目录外写文件会污染共享 `runs/`，与 G20 要守的纪律自相矛盾 —— 闸的 note "
                                "已把这条取舍显式登记）。⇒ 这一条记 `derived_from_source`，不记 `measured_by_experiment`。"),
           "demonstration_on_real_files": {
               "toplevel_convenience_copy": _ident(tl),
               "arm_source_it_was_copied_from": _ident(arm),
               "reading": ("两件 mtime 完全相同（复制时 `cp -p` 保留了源 mtime），而顶层件 ctime 晚 ~7 min "
                           "= 真实落盘时刻 ⇒ 用 mtime 判「是否在窗口内写入」会把这次 13:39:46 的刷新误判成 13:32:02 的写入。"),
               "n_files_affected_in_this_refresh": 51},
           "counterfactual": ("若这次 51 件刷新发生在某一轮闸跑**期间**，按现行判据（mtime-only）G20 会数出 "
                              "**0**；把测试改成 `mtime >= cutoff or ctime >= cutoff` 才会数出 51。"),
           "fix_status": "**未落码**（属判据形态改动 ⇒ 裁定 97.3-5 冻结 + 需 D 授权重跑），登记为 proposed_for_D。"}

    ws = window_scan(win_start, win_end_arg, args.reuse_window_list)
    forecast = recount_against_current_tree(_localize(win_start).timestamp(),
                              _dt.datetime.fromisoformat(prod_ident["mtime"]).timestamp(),
                              NORM_DIR / "TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json")

    ans = {
        "question_verbatim_from_E": ("「E 那三个文件确实在 C2 的 run 目录之外、mtime 也 ≥ 开闸时刻，而 `G20` 自报"
                                     "『run 目录外枚举到 23401 个文件』却数出 **0** ⇒ `G20` 的枚举作用域是否覆盖 "
                                     "`runs/infra/`，值得核一次」（daily_report.md §E13.2 末条）"),
        "answer_scope": {
            "status": "measured",
            "value": "**不覆盖**。枚举根 = `NORM_DIR` = `runs/vla/c2_norm_contract_20260929`（源码常量 + 复现枚举器 "
                     "`all_under_norm_dir=true` + 阴性对照三件全部 `in_enumerated=false`）。`runs/infra/` 结构性地在作用域外。"},
        "answer_why_zero": {
            "status": "measured",
            "reasons": ["① **作用域**：三件在 `NORM_DIR` 之外，枚举器从未看到它们；",
                        "② **时序**：三件的写入时刻在闸产物落盘之后 "
                        + str(min(r["seconds_after_product_mtime"] for r in timing["e_writes_after_product_s"]))
                        + " s 起，闸进程已退出 ⇒ 与作用域无关也不可能被计数。"],
            "g20_false_green": "**否**。G20 在这一轮没有假绿：它的判词与它声明的作用域一致（claim 原文写的就是 "
                              "「`c2_norm_contract_20260929/` 下其它文件零改动」，note 原文写的就是 "
                              "「枚举方式：`NORM_DIR.rglob('*')` 全枚举」）。"},
        "non_vacuity_evidence": {
            "status": "measured",
            "value": ("**比闸自己登记的更强**：`run_20260930_125352` 的判词实测 "
                      "「run 目录外被写文件数=1 例=[`…/probe_monotonicity_20260930/ADDENDUM_ruling_94_6_1_wording_correction.json`]」"
                      "且 `status=RED` ⇒ 这是**实物真检出**，不只是 `enumerator_self_check`。")},
        "defects_found": [
            {"id": "P1", "class": "Ⅱ（文书可发现性）", "what": ("`observed` 判词的前半句「run 目录外被写文件数=N」**没有带作用域限定词**，"
                                                          "容易被读成全仓（E 就是这么读的）。claim 与 note 里都写了作用域，"
                                                          "但判词里没写 ⇒ 读判词的人要翻 note 才不被误导。"),
             "fix": "**未落码**。改判词文案属产物字节变化 ⇒ 需重跑，而重跑需 D 授权（裁定 97.4）⇒ 登记待裁。"},
            {"id": "P2", "class": "Ⅰ→待裁（判据灵敏度，非极性）", "what": ("时间测试只读 `st_mtime` ⇒ `cp -p` 形状的写入在闸跑期间**不可见**"
                                                                  "（本轮实物证据：51 件顶层刷新 mtime=13:32:0x / ctime=13:39:46）。"),
             "fix": "**未落码**。加 `or ctime >= cutoff` 会让判据变严（可能让将来的轮次变红）⇒ 属判据形态改动，冻结中 ⇒ 登记待裁。"},
            {"id": "P3", "class": "Ⅲ（作用域外的自写件，自报）", "what": ("C2 自己的闸 stdout 日志 `tmp/c2_gate_full_ruling97.log`"
                                                                 "（649 B、mtime 13:33:51）在 `NORM_DIR` 外 ⇒ G20 结构上看不到 C2 自己的这一件写入。"),
             "fix": "**未落码**。要么把日志收进 run 目录（改启动形态，不改判据），要么在 note 里点名这条已知例外 ⇒ 待裁。"}],
        "proposed_for_D": [
            "① 若 D 授权下一次重跑：**仅**在 G20 的 `observed` 前缀加作用域限定（「`NORM_DIR` 内、run 目录外」），极性零变化（P1）。",
            "② 是否把时间测试改成 `mtime >= cutoff or ctime >= cutoff`（P2）。C2 建议**改**（它只会变严、不会变松），但它可能让未来的轮次因别线的 `cp -p` 而变红 ⇒ 必须 D 定，且要配套一条「别线的 `cp -p` 不算 C2 的写入」的归属规则，否则就是把别线的行为记到 C2 的牙上。",
            "③ 闸的 stdout 日志改落 run 目录内（P3，零判据改动，只改启动形态）。",
            "④ 若 D 认为「C2 未被发单就不该做这次核查」：本探针**只读 + 只写自己的探针目录**，未动闸、未动判据、未上卡，产物可整目录作废（`recycle_bin` 形状），C2 照办不辩解。"],
    }

    doc = {
        "artifact": "c2_g20_enumeration_scope_probe",
        "generated_at": started,
        "as_of": _now(),
        "authority": ("回答 daily_report.md §E13.2 末条给 C2/F 的疑问；纪律依据 = 裁定 93.8"
                      "（审计器必须自证其模式覆盖）+ 裁定 97.3-5（闸侧冻结）+ 裁定 98.6（C2 停点）"),
        "freeze_compliance": {
            "gate_source_modified": False,
            "gate_products_modified": False,
            "new_checks_added": 0,
            "criterion_shape_changed": False,
            "writes_outside_probe_dir": [],
            "gpu_used": False,
            "policy_executed": False,
            "capability_claim": None,
            "note": "本探针只读闸与闸产物，只写 `probe_g20_scope_ruling98/`。判据待改项一律登记为 proposed_for_D。"},
        "target_run": {"path": str(TARGET_RUN.relative_to(ROOT)), "gate_verdict_identity": prod_ident},
        "source_anchors": anchors,
        "enumerator_replication": repl,
        "g20_record_verbatim": {"measurement_status": g20["measurement_status"],
                                "ok": rec.get("ok"), "status": rec.get("status"),
                                "triage_class": rec.get("triage_class"),
                                "observed": rec.get("observed"),
                                "claim_text": rec.get("claim") or rec.get("name"),
                                "note": rec.get("note"),
                                "mutant_that_proves_it": rec.get("mutant_that_proves_it"),
                                "parsed_numbers": obs_parsed},
        "g20_history": g20_history(),
        "two_way_sentinel": sentinel,
        "timing_counterfactual": timing,
        "mtime_only_blindspot": cpp,
        "window_scan": ws,
        "g20_recount_against_current_tree_ruling99_input": forecast,
        "d_rulings_on_this_probes_findings": {
            "as_of": _now(),
            "source": ("daily_report.md §D98.7 / §D98.8（裁定 98.10）+ "
                       "rl_harness_supervision/d_handoff_to_c2_20260930.md 补单四"),
            "P1_observed_prefix_lacks_scope_qualifier": "**未裁**（排在下次经 D 授权的闸侧改动那一批）",
            "P2_mtime_only_blindspot": (
                "**D 裁 = 真缺陷、Ⅱ 类**（§D98.8-③）；修法 `mtime ∨ ctime` 只会变严，**本轮不改字节**"
                "（裁定 97.3-5 冻结）。**过渡口径（对全线生效）**：任何线不得把「`G20` 绿」读成"
                "「作用域内零未声明写入」，只能读成「零未声明写入 ∧ 写入未保留旧 mtime」"),
            "P3_self_writes_outside_scope": (
                "**D 裁 = 不是缺陷**（枚举根就是 `NORM_DIR`），但追加一条 Ⅲ 类口径："
                "**任何线在自己作用域外的自写件必须在文书里点名**（C2 已自发做到 ⇒ 追认为对全线生效）"),
            "probe_itself": "**D 追认 C2 的越界自报 + 记第五功**（§D98.8-①：C2 的双因版本取代 D 的单因版本）",
            "note": ("本件的 `answer_to_E.proposed_for_D` 段是 **14:25 提交时的原文，不追改**；"
                     "D 的处置以本段为准（本件重生成于 D 裁定之后 ⇒ 两段并存，读者按 `as_of` 分辨）。"),
        },
        "answer_to_E": ans,
        "line_count_caliber_declaration": ("裁定 98.3-②③：本件所有行数字段都点名口径（`n_lines_wc` / `n_lines_splitlines`），"
                                          "**不出现裸 `n_lines`**。"),
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    idn = _ident(out)
    print(json.dumps({"probe_out": idn, "sentinel_all_pass": sentinel["all_pass"],
                      "n_enumerated_now": repl["n_enumerated_now"],
                      "n_enumerated_at_gate_time": repl["n_enumerated_from_verbatim_at_gate_time"],
                      "true_positive_runs": doc["g20_history"]["true_positive_runs"],
                      "real_in_window_by_ctime": ws["n_real_in_window_by_ctime"],
                      "mtime_preserved_false_hits": ws["n_mtime_preserved_false_hits"],
                      "real_in_window_by_owner": ws["real_in_window_by_owner"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
