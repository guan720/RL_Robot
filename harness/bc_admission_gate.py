#!/usr/bin/env python3
"""**T-A2-7 · BC 入口准入闸**（裁定 93.4 / 96.1-④ / 97.3-3 / 97.5 / 85.4-3）。

## 这个模块守什么（派工原文，不重新解释）
`rl_harness_supervision/d_handoff_to_a2_20260930.md` §二：
「1. **不得只读** `admissible_for_bc` / `not_for_bc`。这两个字段是**纯标签派生、对数据质量盲**……
  2. **必须 AND** C2 新增的 `gate_verdict_green`，并**自己复算一次**闸产物（`gate_verdict.json`）的
  `sha256[:12]` 与 C2 声明值对账。 3. **不一致 ⇒ `LearnerRefused`**（不是继续、不是只告警）。
  变异体两向：喂一个 `verdict=RED` 的 run 目录 ⇒ 必须拒；喂 C2 本轮权威跑 ⇒ 必须放行。」
补单二 §六 又收紧了对账口径；裁定 97.3-3 把 AND 的对象从顶层 `verdict` **收窄到 `verdict_class1`**。

## 判据（BC 被禁的三个条件，裁定 97.5 · **只有这三个**）
`verdict_class1 = RED` **或** `admissible_for_bc = false` **或** `Tp5` 同源不成立。
**顶层 `verdict = RED` 本身不再等于「BC 被禁」**（`G20` 是 Ⅲ 类记账、`G24`/`G25` 是 Ⅱ 类台账，
都是 run 级元牙、一个字节都不碰训练数据）—— 但它们**照样登记、照样在 S5 前清零**。

## 三值纪律（红线 `absence_of_measurement_is_not_measurement_of_absence`）
* 声明缺失 / 路径读不到 / 产物里没有 `verdict_class1` 字面值 ⇒ **`not_measured` ⇒ 拒绝**。
  **不写 `false`**（那等于宣称"测过了、闸是红的"），也**不静默当绿**，
  **更不许拿顶层 `verdict` 顶替 `verdict_class1`**（C2 在 `bc_admission()` 的 docstring 里明写：
  顶替 = 把"没测这一项"谎报成"测了、且与顶层同值"）。
* `sha256[:12]` 是**身份**（裁定 98.5-①：对账的**唯一约束性判据**）；行数只是人可读的旁证，
  且**必须点名口径**（`n_lines_wc` / `n_lines_splitlines`，裁定 98.5-②）⇒ 只在 sha 相符时降级为
  `warn`，sha 不符一律拒）。

## 不许自己挑份（补单二 §六）
**只对 C2 声明的那一条完整路径复算对账**，**不许 `glob` 后挑一份**。实测已存在**同名双件**
（顶层 `mainline_status.json` vs 臂内 `arm_mainline/mainline_status.json`，行数与字节数全同、
sha 不同）⇒ 本模块**没有任何 glob 逻辑**：声明里没有的路径一律不读（`no_globbing_by_construction`）。
**BC 消费口径 = 最新一次 class-1 绿的闸跑的臂内件。**

## 判定层与准入函数都不归 A2
`admissible_for_bc` / `gate_verdict_class1_green` / `bc_blocking_caliber` 全部由 **C2 的
`harness/norm_contract.py::bc_admission()`** 产出，本模块只 import 调用 + 自己复算 sha 对账。
**两个位置各写一份口径 = 本仓已发生四次的事故形状**（裁定 83§7 / 缺陷类 ⑲）。

## 用法
    python -c "from harness.bc_admission_gate import bc_admission_check; …"   # BC 入口调用
    /root/venvs/pi05_sim/bin/python harness/bc_admission_gate.py --selftest   # 两向变异体（裁定 93.8）
    … --probe-real            # 拿**当前** C2 实物跑一遍（结论如实报，今天预期是 refused）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# ── C2 的准入函数（**只 import，不改、不重造**）──
from harness.norm_contract import (BC_ADMISSIBLE_PROVENANCES, GATE_VERDICT_PASS,  # noqa: E402
                                   STATS_PROVENANCE_FORMAL40_BC, bc_admission)

MODULE_REPRESENTATION_VERSION = "a2-bc-admission-gate-v1"
MAINLINE_CONTROL_HZ = 29.411764705882355      # `params:119` 同频纪律（DT=0.034 = 17 × 0.002）
N_LINES_CALIBER = ("裁定 98.5：`n_lines_splitlines` = `len(read_text().splitlines())`；"
                   "`n_lines_wc` = 换行符个数（`wc -l`）。末行无换行符 ⇒ 两者差 1。"
                   "**裸 `n_lines` 不得再出现在任何广播或对账里**；"
                   "**对账的唯一约束性判据 = `sha256[:12]`**，行数只作辅证且必须点名口径。")
N_LINES_CALIBERS = ("n_lines_wc", "n_lines_splitlines")

# C2 按裁定 96.1-④ 广播时必须给全的字段（**成对**：臂内件 + 同轮 gate_verdict.json）
DECLARATION_REQUIRED_FIELDS = (
    "declared_by", "as_of", "gate_run_dir",
    "arm_mainline_status_path", "arm_mainline_status_sha256_12",
    "gate_verdict_path", "gate_verdict_sha256_12",
    "verdict_class1",
)
# 裁定 98.5-①/④：行数是**辅证**、且必须点名口径 ⇒ 不进必给清单（进了就等于让一次文书改名
# 有能力把 BC 假红掉，那正是 §98.5 点名的「第 1 步白跑一轮」的形状）。
DECLARATION_LINE_FIELDS = ("arm_mainline_status_n_lines_wc", "arm_mainline_status_n_lines_splitlines",
                           "gate_verdict_n_lines_wc", "gate_verdict_n_lines_splitlines")
FORBIDDEN_BARE_LINE_KEYS = ("arm_mainline_status_n_lines", "gate_verdict_n_lines", "n_lines")
# 裁定 97.3-4 的一次性前置（`checked_by = F`、`checked_when = A2 第 1 步开跑前`）。
# 本模块是它的**消费方** —— 预登记条件没有消费方 = 缺陷类 ⑳。
# **职责边界（重要）**：`G14` 是否**真的有实测翻转**这个**语义判断归 F**（裁定 97.3-4 明写
# `checked_by = F`），本闸**不重判语义**，只核「被引为证据的那一件**存在**、且 sha 与声明相等」。
# ⇒ 声明里给的 `g14_flip_evidence_path` 可以是 F 的每轮台账产物，**也可以就是同轮的
# `gate_verdict.json` 本身**（裁定 97 之后它自带 `triage_class` / `verdict_class1` / `G24` 的
# `flip_measured` 台账）。这样既让预登记条件有了消费方，又不把 F 的判据搬进 A2 的写入面。
G14_PRECONDITION_FIELDS = ("g14_flip_evidence_path", "g14_flip_evidence_sha256_12",
                           "g14_flip_checked_by", "g14_flip_checked_when")


class LearnerRefused(RuntimeError):
    """BC 准入不成立 ⇒ **拒绝**（不是继续、不是只告警）。携带完整判定块。"""

    def __init__(self, reason_code: str, decision: dict[str, Any]):
        self.reason_code = reason_code
        self.decision = decision
        super().__init__(
            f"LearnerRefused: {reason_code} —— {decision.get('reason_verbatim') or ''}"
            f"（判据见 decision.blocking_refusals；裁定 93.4 / 97.5）")


def _stream_identity(path: pathlib.Path, *, scan_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    """**单遍流式**取身份 + 顺手扫顶层判词（`gate_verdict.json` 实测 ~95 MB ⇒ 不整件载入，
    裁定 97.4 的体积纪律）。sha256 与行数在同一次读里算完 ⇒ 不存在"读了两次、两次不是同一份"。
    """
    out: dict[str, Any] = {"path": str(path), "measurement_status": "not_measured"}
    if not path.exists():
        out["why"] = "路径不存在（读不到 ≠ 测到没有）"
        return out
    h = hashlib.sha256()
    n_bytes = n_newlines = 0
    tail = b""
    found: dict[str, str | None] = {k: None for k in scan_keys}
    pat = {k: re.compile(rb'"' + k.encode() + rb'"\s*:\s*"([^"]*)"') for k in scan_keys}
    try:
        with path.open("rb") as fh:
            while True:
                b = fh.read(1 << 20)
                if not b:
                    break
                h.update(b)
                n_bytes += len(b)
                n_newlines += b.count(b"\n")
                buf = tail + b                      # 跨块边界的键也能命中
                for k, p in pat.items():
                    if found[k] is None:
                        m = p.search(buf)
                        if m:
                            found[k] = m.group(1).decode("utf-8", "replace")
                tail = buf[-4096:]
    except Exception as exc:                                          # noqa: BLE001
        out["why"] = f"{type(exc).__name__}: {exc}"
        return out
    txt_lines = n_newlines + (0 if tail.endswith(b"\n") or n_bytes == 0 else 1)
    # 裁定 98.5-②：**裸 `n_lines` 不得再出现在任何广播或对账里** ⇒ 两个口径各自点名。
    out.update({"measurement_status": "measured", "n_bytes": n_bytes,
                "n_lines_splitlines": txt_lines, "n_lines_wc": n_newlines,
                "ends_with_newline": bool(n_bytes) and tail.endswith(b"\n"),
                "sha256_12": h.hexdigest()[:12], "scanned": found,
                "n_lines_caliber": N_LINES_CALIBER})
    return out


def _rel(p: Any) -> str:
    s = str(p)
    return s[len(str(REPO)) + 1:] if s.startswith(str(REPO)) else s


def _inside(run_dir: pathlib.Path, target: pathlib.Path) -> bool:
    try:
        target.resolve().relative_to(run_dir.resolve())
        return True
    except Exception:                                                 # noqa: BLE001
        return False


# ══════════ 机器负载读数（**成对纪律**：吞吐/延迟数字必须带 loadavg 三点 + nr_throttled）══════════
def _machine_load() -> dict[str, Any]:
    """CPU 侧读数。cgroup **v1** 路径 `/sys/fs/cgroup/cpu/cpu.stat`（v2 路径本机不存在）；
    配额 12 核，`nproc=112` 是假象 ⇒ 分母一律用配额。**本函数不叫 `nvidia-smi`**：准入对账是
    CPU 作业（`gpu_used=false`）；真上卡窗口的三网读数归 `harness/prompt_bin_guard.py::
    gpu_window_readings()`（那里才是权威，不在此重造）。
    """
    out: dict[str, Any] = {"measurement_status": "measured", "nvidia_smi_called": False,
                           "cpu_quota_cores": 12, "nproc_is_misleading": True}
    try:
        la = os.getloadavg()
        out["loadavg"] = f"{la[0]:.2f} {la[1]:.2f} {la[2]:.2f}"
        out["loadavg_points"] = [round(x, 2) for x in la]
    except Exception as exc:                                          # noqa: BLE001
        out.update({"loadavg": None, "loadavg_error": f"{type(exc).__name__}: {exc}"})
    try:
        stat: dict[str, int] = {}
        for ln in pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat").read_text().splitlines():
            k, _, v = ln.partition(" ")
            stat[k] = int(v)
        out["nr_throttled"] = stat.get("nr_throttled")
        out["nr_periods"] = stat.get("nr_periods")
        out["cgroup_version"] = "v1"
    except Exception as exc:                                          # noqa: BLE001
        out.update({"nr_throttled": None, "cpu_stat_error": f"{type(exc).__name__}: {exc}",
                    "measurement_status": "not_measured"})
    return out


# ══════════ C2 的成对广播 = 声明的**正主**（裁定 96.1-④ / 97.5）══════════════════════
# 纪律：声明只能来自 C2 **自己点名**的路径 ⇒ 本节没有任何 `glob` / latest-run 推断 / 手抄。
# 解析不出来 = **拒绝**（不猜一份、不退回 `--trial-from-latest-run` 那种 A2 自拼试算件）。
BROADCAST_DOC_DEFAULT = "docs/c2_to_a2_bc_stats_handoff_20260930.md"
BROADCAST_SECTION_RE = re.compile(r"^##\s+(\d+)\.\s*(.*)$")
BROADCAST_PAIR_MARK_RE = re.compile(r"^\*\*\s*([①②])")
SHA12_RE = re.compile(r"(?<![0-9a-f])([0-9a-f]{12})(?![0-9a-f])")
PATH_IN_BACKTICK_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./\-]*\.(?:json|npz))`")
NPZ_WITH_SHA_RE = re.compile(r"`([A-Za-z0-9_./\-]+\.npz)`\s*=\s*`([0-9a-f]{12})`")
INT_RE = re.compile(r"(\d+)")
ARM_DIR_TOKEN = "/arm_mainline/"
# 两件广播载体合并时，只有**点名口径的行数**从 json 那份补进来（裁定 98.5-②/③）；
# 身份串（路径/sha/verdict_class1）一律以 markdown 那份为底，再由 crosscheck 要求两件相等。
N_LINES_MERGE_KEYS = ("arm_mainline_status_n_lines_wc", "arm_mainline_status_n_lines_splitlines",
                      "gate_verdict_n_lines_wc", "gate_verdict_n_lines_splitlines")
TOPLEVEL_CONVENIENCE_COPY = "runs/vla/c2_norm_contract_20260929/mainline_status.json"


class BroadcastParseError(RuntimeError):
    """C2 的广播件解析不出**唯一**声明 ⇒ 拒绝（`reason_code` 进判定块，不猜、不顶替）。"""

    def __init__(self, reason_code: str, detail: str):
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"BroadcastParseError: {reason_code} —— {detail}")


def _clean_cell(txt: str) -> str:
    return txt.replace("`", "").replace("**", "").strip()


def _cut_paren(txt: str) -> str:
    """取值时切掉中文/英文括注（`PASS（裁定 97.3-2 新增…）` → `PASS`）。"""
    for ch in ("（", "("):
        if ch in txt:
            txt = txt.split(ch, 1)[0]
    return txt.strip()


def _kv_rows(block: list[str]) -> list[tuple[str, str, str]]:
    """把 markdown 表格行读成 (键, 原值, 原行)；跳过表头与分隔行。"""
    rows: list[tuple[str, str, str]] = []
    for ln in block:
        if not ln.lstrip().startswith("|"):
            continue
        cells = [c for c in ln.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        key, val = _clean_cell(cells[0]), cells[1].strip()
        if not key or set(key) <= {"-", " ", ":"}:
            continue
        if key in ("项", "字段"):
            continue
        rows.append((key, val, ln.rstrip()))
    return rows


def _pick(rows: list[tuple[str, str, str]], *, prefix: str | None = None, exact: str | None = None,
          where: str) -> tuple[str, str]:
    """**唯一命中**才取值：0 命中 ⇒ `not_found`，≥2 命中 ⇒ `ambiguous`，两种都抛（不挑一份）。"""
    hit = [(v, raw) for k, v, raw in rows
           if (k == exact if exact is not None else k.startswith(prefix))]
    if not hit:
        raise BroadcastParseError(
            "broadcast_row_not_found",
            f"{where} 里没有键 {'= ' + exact if exact else '前缀 ' + str(prefix)} 的行")
    if len(hit) > 1:
        raise BroadcastParseError(
            "broadcast_row_ambiguous",
            f"{where} 里键 {'= ' + exact if exact else '前缀 ' + str(prefix)} 命中 {len(hit)} 行 "
            f"⇒ 不可判、不挑一份（{[h[1][:60] for h in hit]}）")
    return hit[0]


def _pick3(rows: list[tuple[str, str, str]], *, prefix: str, where: str) -> tuple[str, str, str]:
    """同 `_pick`，但把**键原文**也带出来（行数行需要靠键名判口径，裁定 98.5-②）。"""
    hit = [(k, v, raw) for k, v, raw in rows if k.startswith(prefix)]
    if not hit:
        raise BroadcastParseError("broadcast_row_not_found", f"{where} 里没有键前缀 {prefix} 的行")
    if len(hit) > 1:
        raise BroadcastParseError("broadcast_row_ambiguous",
                                  f"{where} 里键前缀 {prefix} 命中 {len(hit)} 行 ⇒ 不挑一份")
    return hit[0]


def _caliber_of_line_key(key: str, raw: str) -> str | None:
    """从**键名或行内注记**推出行数口径；推不出 ⇒ `None`（= 口径不明，只登记不比对）。"""
    k, t = key.lower(), raw.lower()
    if "splitlines" in k:
        return "n_lines_splitlines"
    if k.endswith("_wc") or "wc_l" in k or "wc -l" in k:
        return "n_lines_wc"
    if "splitlines" in t:
        return "n_lines_splitlines"
    if "wc -l" in t or "wc_l" in t:
        return "n_lines_wc"
    return None


def _unique(pattern: re.Pattern[str], txt: str, *, where: str, group: int = 1) -> str:
    ms = pattern.findall(txt)
    if len(ms) != 1:
        raise BroadcastParseError(
            "broadcast_value_ambiguous" if len(ms) > 1 else "broadcast_value_not_found",
            f"{where} 里 {pattern.pattern} 命中 {len(ms)} 次（{ms[:4]}）⇒ 不猜")
    return ms[0] if isinstance(ms[0], str) else ms[0][group - 1]


def parse_c2_broadcast(doc_path: Any) -> dict[str, Any]:
    """把 C2 的成对广播件解析成 `bc_admission_check` 要的**声明**。

    只认两件：① 臂内件（BC 消费口径）· ② 同轮 `gate_verdict.json`（「闸绿」这个事实的唯一出处）。
    **sha 一律由消费方复算**（本函数只取 C2 的声明值，不信任它）。
    """
    dp = (REPO / _rel(doc_path)) if not pathlib.Path(str(doc_path)).is_absolute() \
        else pathlib.Path(str(doc_path))
    doc_id = _stream_identity(dp)
    if doc_id.get("measurement_status") != "measured":
        raise BroadcastParseError("broadcast_doc_unreadable",
                                  f"广播件读不到（{doc_id.get('why')}）⇒ not_measured，不猜")
    text = dp.read_text(errors="replace")
    lines = text.splitlines()

    # 分段：`## N. 标题`
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    cur: str | None = None
    for ln in lines:
        m = BROADCAST_SECTION_RE.match(ln)
        if m:
            cur = m.group(1)
            sections[cur] = []
            order.append(cur)
            continue
        if cur is not None:
            sections[cur].append(ln)
    as_of_m = re.search(r"as_of\s*=\s*([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{5,8}"
                        r"(?:\+[0-9]{2}:[0-9]{2})?)", text)
    if not as_of_m:
        raise BroadcastParseError("broadcast_as_of_not_found",
                                  "广播件里没有 `as_of = <ISO8601>` ⇒ 声明缺 `as_of`（必给字段）")

    # §1 的两块（①/②）
    if "1" not in sections:
        raise BroadcastParseError("broadcast_section1_absent", "广播件没有 `## 1.` 段（成对身份段）")
    sec1 = sections["1"]
    marks = [i for i, ln in enumerate(sec1) if BROADCAST_PAIR_MARK_RE.match(ln)]
    if len(marks) != 2:
        raise BroadcastParseError(
            "broadcast_pair_marks_not_two",
            f"§1 里 ①/② 标记命中 {len(marks)} 处（应为 2）⇒ 成对身份不可判")
    blocks = {"①": sec1[marks[0]:marks[1]], "②": sec1[marks[1]:]}
    parsed_blocks: dict[str, dict[str, Any]] = {}
    verbatim_rows: list[str] = []
    for tag in ("①", "②"):
        rows = _kv_rows(blocks[tag])
        where = f"§1-{tag}"
        pval, praw = _pick(rows, prefix="完整路径", where=where)
        path = _unique(PATH_IN_BACKTICK_RE, pval, where=f"{where} 的完整路径行")
        sval, sraw = _pick(rows, prefix="sha256", where=where)
        sha = _unique(SHA12_RE, sval, where=f"{where} 的 sha256 行")
        # 行数行：**同一张表里可以并存多个口径**（C2 按裁定 98.5-③ 改名后就是两个都给）⇒
        # 逐行推口径、按口径归并；**只有「同一口径出现两个不同值」才算不可判**。
        lrows = [(k, v, raw) for k, v, raw in rows if k.startswith("n_lines")]
        if not lrows:
            raise BroadcastParseError("broadcast_row_not_found",
                                      f"{where} 里没有键前缀 `n_lines` 的行")
        per_caliber: dict[str, int] = {}
        unnamed_lines: list[dict[str, Any]] = []
        for lkey, lval, _lraw in lrows:
            lcal = _caliber_of_line_key(lkey, lval)
            lclean = _cut_paren(_clean_cell(lval))
            lints = INT_RE.findall(lclean)
            if lcal is None or len(lints) != 1:
                unnamed_lines.append({"row_key_verbatim": lkey, "value_raw": lval,
                                      "caliber": lcal, "n_int_candidates": len(lints)})
                continue
            val = int(lints[0])
            if per_caliber.get(lcal, val) != val:
                raise BroadcastParseError(
                    "broadcast_row_ambiguous",
                    f"{where} 里同一口径 `{lcal}` 出现两个不同值（{per_caliber[lcal]} 与 {val}）⇒ 不挑一份")
            per_caliber[lcal] = val
        verbatim_rows += [f"[{where}] {raw}" for _k, _v, raw in lrows]
        bval, braw = _pick(rows, prefix="bytes", where=where)
        nby = int(_unique(INT_RE, _cut_paren(_clean_cell(bval)), where=f"{where} 的 bytes 行"))
        blk: dict[str, Any] = {"path": path, "sha256_12_declared": sha,
                               "n_lines_by_caliber": per_caliber,
                               "n_lines_caliber_unnamed_rows": unnamed_lines,
                               "bytes_declared": nby,
                               "n_lines_caliber_note": (
                                   "口径由**键名/行内注记**推出（裁定 98.5-②）；推不出的行只登记不比对，"
                                   "⇒ 不会出现 §98.5 点名的「假 LearnerRefused、第 1 步白跑一轮」")}
        verbatim_rows += [f"[{where}] {x}" for x in (praw, sraw, braw)]
        if tag == "②":
            vtop, vraw = _pick(rows, exact="verdict", where=where)
            vc1, craw = _pick(rows, prefix="verdict_class1", where=where)
            blk["verdict_declared"] = _cut_paren(_clean_cell(vtop))
            blk["verdict_class1_declared"] = _cut_paren(_clean_cell(vc1))
            verbatim_rows += [f"[{where}] {vraw}", f"[{where}] {craw}"]
        parsed_blocks[tag] = blk

    arm, gv = parsed_blocks["①"], parsed_blocks["②"]
    if ARM_DIR_TOKEN not in arm["path"]:
        raise BroadcastParseError(
            "declared_arm_is_toplevel_convenience_copy",
            f"①的路径 {arm['path']} 不含 `{ARM_DIR_TOKEN}` ⇒ 是顶层便捷副本，"
            "各线一律不消费（裁定 96.1-④ / §D96.9）")
    run_dir = str(pathlib.PurePosixPath(gv["path"]).parent)
    if not arm["path"].startswith(run_dir + "/"):
        raise BroadcastParseError(
            "broadcast_pair_not_same_round",
            f"①({arm['path']}) 不在②的 run 目录 ({run_dir}) 内 ⇒ 两条身份不是一轮，成对广播不成立")

    declaration: dict[str, Any] = {
        "declared_by": (f"C2（广播件 `{_rel(dp)}`，sha256[:12]={doc_id['sha256_12']}）"),
        "as_of": as_of_m.group(1),
        "gate_run_dir": run_dir,
        "gate_run_dir_derivation": "取②的 `gate_verdict.json` 路径的 parent（**不是 glob、不是挑最新一轮**）",
        "arm_mainline_status_path": arm["path"],
        "arm_mainline_status_sha256_12": arm["sha256_12_declared"],
        "arm_mainline_status_bytes": arm["bytes_declared"],
        "gate_verdict_path": gv["path"],
        "gate_verdict_sha256_12": gv["sha256_12_declared"],
        "gate_verdict_bytes": gv["bytes_declared"],
        "verdict_class1": gv["verdict_class1_declared"],
        "verdict_top_level_declared": gv["verdict_declared"],
        "broadcast_doc_path": _rel(dp),
        "broadcast_doc_sha256_12": doc_id["sha256_12"],
    }
    for tag, blk in (("arm_mainline_status", arm), ("gate_verdict", gv)):
        for cal, val in (blk.get("n_lines_by_caliber") or {}).items():
            declaration[f"{tag}_{cal}"] = val
        if blk.get("n_lines_caliber_unnamed_rows"):
            declaration[f"{tag}_n_lines_caliber_unnamed"] = {
                "rows": blk["n_lines_caliber_unnamed_rows"],
                "why": "键名与行内注记都没点名口径 ⇒ 不比对（裁定 98.5-②）"}

    # §3 的 stats 唯一一档 + 源数据 npz（BC 真正要吃的两样东西）
    stats_dec: dict[str, Any] = {"measurement_status": "not_measured"}
    npz_dec: dict[str, Any] = {"measurement_status": "not_measured"}
    if "3" in sections:
        rows3 = _kv_rows(sections["3"])
        try:
            pval, praw = _pick(rows3, prefix="完整路径", where="§3")
            spath = _unique(PATH_IN_BACKTICK_RE, pval, where="§3 的完整路径行")
            sval, sraw = _pick(rows3, prefix="sha256", where="§3")
            ssha = _unique(SHA12_RE, sval, where="§3 的 sha256 行")
            sclean = _clean_cell(sval)
            sbytes = int(_unique(re.compile(r"bytes`?\s*(\d+)"), sclean, where="§3 的 bytes"))
            s_lines = {}
            for cal in N_LINES_CALIBERS:
                m = re.search(re.escape(cal) + r"[^0-9]{0,12}(\d+)", sclean)
                if m:
                    s_lines[cal] = int(m.group(1))
            rval, rraw = _pick(rows3, prefix="representation_version", where="§3")
            pval2, _ = _pick(rows3, prefix="stats_provenance", where="§3")
            ndims, ndraw = _pick(rows3, exact="n_dims", where="§3")
            dval, draw = _pick(rows3, prefix="源数据", where="§3")
            npz_m = NPZ_WITH_SHA_RE.search(dval)
            if npz_m is None:
                raise BroadcastParseError("broadcast_npz_identity_not_found",
                                          f"§3 的源数据行里没有 `<npz>` = `<sha12>` 形状：{draw[:120]}")
            man_m = re.search(r"npz_manifest_sha256_12\s*=\s*([0-9a-f]{12})", dval)
            stats_dec = {"measurement_status": "measured", "path": spath,
                         "sha256_12_declared": ssha, "bytes_declared": sbytes,
                         "n_lines_by_caliber": s_lines,
                         "representation_version_declared": _cut_paren(_clean_cell(rval)),
                         "stats_provenance_declared": _cut_paren(_clean_cell(pval2)),
                         "n_dims_declared": int(_unique(INT_RE, ndims, where="§3 的 n_dims 行")),
                         "inside_declared_run_dir": spath.startswith(run_dir + "/")}
            npz_dec = {"measurement_status": "measured", "path": npz_m.group(1),
                       "sha256_12_declared": npz_m.group(2),
                       "npz_manifest_sha256_12_declared": (man_m.group(1) if man_m else None)}
            verbatim_rows += [f"[§3] {x}" for x in (praw, sraw, rraw, ndraw, draw)]
        except BroadcastParseError as exc:
            stats_dec = {"measurement_status": "not_measured", "why": f"{exc.reason_code}: {exc.detail}"}
            npz_dec = {"measurement_status": "not_measured", "why": f"{exc.reason_code}: {exc.detail}"}
    else:
        why = "广播件没有 `## 3.` 段（stats 唯一一档 + 源数据 npz）"
        stats_dec = {"measurement_status": "not_measured", "why": why}
        npz_dec = {"measurement_status": "not_measured", "why": why}

    return {"artifact": "c2_broadcast_parse", "measurement_status": "measured",
            "as_of_parsed": datetime.now().astimezone().isoformat(timespec="seconds"),
            "doc_identity": doc_id, "as_of_declared": as_of_m.group(1),
            "declaration": declaration, "stats_declaration": stats_dec,
            "npz_declaration": npz_dec,
            "parse_report": {"sections_seen": order,
                             "pair_blocks": {k: {kk: vv for kk, vv in v.items()}
                                             for k, v in parsed_blocks.items()},
                             "verbatim_rows_used": verbatim_rows,
                             "discovery_method": ("逐行解析 C2 **点名**的路径与身份串；"
                                                  "无 glob、无 latest-run 推断、无手抄"),
                             "no_globbing_by_construction": True,
                             "sha_not_trusted_here": "声明值只用于对账，实物 sha 一律由消费方复算"}}


def bc_admission_check(*, declaration: Any = None, raise_on_refusal: bool = True,
                       npz_path: Any = None, npz_sha256_12_declared: str | None = None,
                       control_hz: float | None = None,
                       consumer: str = "bc") -> dict[str, Any]:
    """BC 起跑前的**唯一**准入判定。返回一个可落盘的判定块；`raise_on_refusal=True`（默认）时
    不成立就抛 `LearnerRefused`。

    `declaration` = C2 按裁定 96.1-④ 广播的那一条**完整路径 + 身份串 + `as_of`**（成对给出
    臂内件与同轮 `gate_verdict.json`）。**没有声明就没有准入**：本函数不会去 `glob` 找一份。
    """
    as_of = datetime.now().astimezone().isoformat(timespec="seconds")
    dec = dict(declaration or {})
    checks: dict[str, Any] = {}
    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    not_measured: list[str] = []

    def refuse(code: str, verbatim: str, ruling: str) -> None:
        blocking.append({"reason_code": code, "reason_verbatim": verbatim, "ruling": ruling})

    # ── R0：声明本身（缺 ⇒ not_measured ⇒ 拒；**不许 glob 补**）────────────────────────
    missing = [k for k in DECLARATION_REQUIRED_FIELDS if dec.get(k) in (None, "")]
    checks["declaration_present"] = not missing
    checks["declaration_fields_missing"] = missing
    checks["no_globbing_by_construction"] = True
    if missing:
        refuse("declaration_absent_or_incomplete",
               f"C2 的成对广播缺失/不全（缺 {missing}）⇒ `not_measured`，**不许拿别的产物顶替、"
               "也不许自己 glob 挑一份**",
               "裁定 96.1-④ + 补单二 §六 + 97.5")
        not_measured.append("declaration")

    arm_id: dict[str, Any] = {"measurement_status": "not_measured"}
    gv_id: dict[str, Any] = {"measurement_status": "not_measured"}
    arm_json: dict[str, Any] = {}
    c2_admission: dict[str, Any] = {}

    if not missing:
        run_dir = REPO / _rel(dec["gate_run_dir"])
        arm_p = REPO / _rel(dec["arm_mainline_status_path"])
        gv_p = REPO / _rel(dec["gate_verdict_path"])
        checks["gate_run_dir_exists"] = run_dir.is_dir()
        checks["arm_path_inside_declared_run_dir"] = _inside(run_dir, arm_p)
        checks["gate_verdict_path_inside_declared_run_dir"] = _inside(run_dir, gv_p)
        if not (run_dir.is_dir() and checks["arm_path_inside_declared_run_dir"]
                and checks["gate_verdict_path_inside_declared_run_dir"]):
            refuse("declared_paths_not_inside_declared_run_dir",
                   "声明的路径不在声明的 run 目录内 ⇒ 声明与实物不是一轮（对账无意义）",
                   "裁定 96.1-④（成对广播）")
        # 顶层便捷副本即使被声明成「run 目录 = 上层目录」而通过包含性检查，也**一律不消费**
        # （Ⅰ 类：认错消费件会让 06:04 的旧 stats 被合法吃进 BC）。
        checks["arm_path_is_toplevel_convenience_copy"] = (
            _rel(arm_p) == TOPLEVEL_CONVENIENCE_COPY or ARM_DIR_TOKEN not in _rel(arm_p))
        if checks["arm_path_is_toplevel_convenience_copy"]:
            refuse("arm_path_is_toplevel_convenience_copy",
                   f"声明的 BC 消费件 `{_rel(arm_p)}` 是**顶层便捷副本**（不含 `{ARM_DIR_TOKEN}`）"
                   " ⇒ 各线一律不消费顶层件；BC 消费口径只能是最新一次 class-1 绿的闸跑的**臂内件**",
                   "裁定 96.1-④ / §D96.9（顶层件与臂内件曾分叉）")

        # ── R1/R2：**自己复算** sha 对账（裁定 93.4 第 2 条）──────────────────────────
        arm_id = _stream_identity(arm_p)
        gv_id = _stream_identity(gv_p, scan_keys=("verdict", "verdict_class1"))
        checks["arm_identity"] = arm_id
        checks["gate_verdict_identity"] = gv_id
        for tag, ident_, dec_sha in (
                ("arm_mainline_status", arm_id, dec.get("arm_mainline_status_sha256_12")),
                ("gate_verdict", gv_id, dec.get("gate_verdict_sha256_12"))):
            if ident_.get("measurement_status") != "measured":
                refuse(f"{tag}_unreadable", f"`{tag}` 读不到 ⇒ not_measured（{ident_.get('why')}）",
                       "红线 absence_of_measurement_is_not_measurement_of_absence")
                not_measured.append(tag)
                continue
            sha_ok = str(dec_sha).lower() == ident_["sha256_12"]
            if not sha_ok:
                refuse(f"{tag}_sha256_mismatch",
                       f"`{tag}` 复算 sha256[:12]={ident_['sha256_12']} ≠ C2 声明 {dec_sha} ⇒ 拒绝",
                       "裁定 93.4 第 3 条：不一致 ⇒ LearnerRefused（sha 是唯一约束性判据，裁定 98.5-①）")
            # 行数：**只在口径名对得上时才比**（裁定 98.5-②/④）
            for cal in N_LINES_CALIBERS:
                dec_ln = dec.get(f"{tag}_{cal}")
                if dec_ln is None:
                    continue
                if int(dec_ln) != int(ident_[cal]):
                    item = {"reason_code": f"{tag}_{cal}_mismatch",
                            "reason_verbatim": (f"`{tag}` 的 `{cal}` 复算={ident_[cal]} ≠ 声明 {dec_ln}"
                                                f"（sha256[:12] {'相符' if sha_ok else '不符'}）"),
                            "ruling": ("裁定 98.5-①/④：行数只作辅证且必须点名口径；"
                                       "身份以 sha256[:12] 为准 ⇒ sha 相符时**不阻塞**（否则就是"
                                       "§98.5 点名的「假 LearnerRefused、第 1 步白跑一轮」）"),
                            "triage_class": ("class1_control_and_data_correctness" if not sha_ok
                                             else "class3_documentation_integrity")}
                    (blocking if not sha_ok else warnings).append(item)
            declared_cals = [c for c in N_LINES_CALIBERS if dec.get(f"{tag}_{c}") is not None]
            if not declared_cals:
                warnings.append({
                    "reason_code": f"{tag}_n_lines_not_declared_with_caliber",
                    "reason_verbatim": (f"`{tag}` 的声明里没有点名口径的行数 ⇒ 辅证缺席"
                                        f"（约束性判据 sha256[:12] 已{'相符' if sha_ok else '不符'}）"),
                    "ruling": "裁定 98.5-②（裸 `n_lines` 不得再出现；行数只作辅证）",
                    "triage_class": "class3_documentation_integrity"})

        bare = [k for k in FORBIDDEN_BARE_LINE_KEYS if k in dec]
        checks["forbidden_bare_n_lines_keys_present"] = bare
        if bare:
            warnings.append({
                "reason_code": "bare_n_lines_key_in_declaration",
                "reason_verbatim": (f"声明里出现了裸行数键 {bare} ⇒ 口径不明。本闸**不拿它比对**"
                                    "（避免跨口径假红），只登记；请广播方改名为 `n_lines_wc` / "
                                    "`n_lines_splitlines`（裁定 98.5-②/③）"),
                "ruling": "裁定 98.5-②：裸 `n_lines` 不得再出现在任何广播或对账里",
                "triage_class": "class3_documentation_integrity"})

        # ── R3：`verdict_class1` **只从实物读**，缺失 ⇒ not_measured ⇒ 拒 ─────────────
        scanned = (gv_id.get("scanned") or {})
        vc1_file = scanned.get("verdict_class1")
        v_top = scanned.get("verdict")
        checks["verdict_class1_from_artifact"] = vc1_file
        checks["top_level_verdict_from_artifact"] = v_top
        checks["verdict_class1_not_substituted_by_top_level"] = True
        if vc1_file is None:
            refuse("verdict_class1_not_measured",
                   f"闸产物里没有 `verdict_class1` 字面值（顶层 `verdict`={v_top!r}）⇒ "
                   "**not_measured**；这是早于裁定 97.3 的产物形态，**不许拿顶层 verdict 顶替**",
                   "裁定 97.3-3 + C2 `bc_admission()` docstring 的三值纪律")
            not_measured.append("verdict_class1")
        else:
            if str(dec["verdict_class1"]) != vc1_file:
                refuse("verdict_class1_declaration_mismatch",
                       f"声明 `verdict_class1`={dec['verdict_class1']!r} ≠ 实物 {vc1_file!r}",
                       "裁定 96.1-④（广播必须与实物相等）")
            if vc1_file != GATE_VERDICT_PASS:
                refuse("verdict_class1_not_pass",
                       f"`verdict_class1={vc1_file}` ⇒ **BC 被禁**（这是三个禁训判据之一）",
                       "裁定 97.5")

        # ── R4：臂内件的 `bc_admission` + **C2 的函数**（不重造）────────────────────
        try:
            arm_json = json.loads(arm_p.read_text(errors="replace"))
            checks["arm_mainline_status_readable"] = True
        except Exception as exc:                                      # noqa: BLE001
            checks["arm_mainline_status_readable"] = False
            refuse("arm_mainline_status_unparseable", f"臂内件解析失败：{type(exc).__name__}: {exc}",
                   "裁定 93.4")
        arm_bc = dict((arm_json or {}).get("bc_admission") or {})
        prov = (arm_json or {}).get("stats_provenance") or arm_bc.get("stats_provenance")
        checks["stats_provenance_from_arm"] = prov
        c2_admission = bc_admission(prov, gate_verdict=v_top, gate_verdict_class1=vc1_file,
                                    gate_run_dir=_rel(run_dir),
                                    gate_verdict_sha256_12=gv_id.get("sha256_12"))
        checks["c2_bc_admission"] = c2_admission
        checks["c2_bc_admission_is_the_authority"] = (
            "harness/norm_contract.py::bc_admission（A2 只 import 调用，不重算）")
        # ── **存量标签 vs 重算值必须一致**（派工 §二 第 1 条点名的失效形态）──────────────
        # 原文：「本轮**实测存在过**『`admissible_for_bc=true` 而同一批数据 matrix=RED』的状态」。
        # 只**重算**会漏掉"臂内件自己写的标签是错的"；只**读标签**会漏掉"标签对数据质量盲"。
        # ⇒ 两边都取，**不一致就是实物内部自相矛盾** ⇒ 拒（不是挑一个信）。
        stored_admissible = arm_bc.get("admissible_for_bc")
        recomputed_admissible = c2_admission.get("admissible_for_bc")
        stored_prov = arm_bc.get("stats_provenance")
        checks["arm_stored_admissible_for_bc"] = stored_admissible
        checks["recomputed_admissible_for_bc"] = recomputed_admissible
        checks["arm_stored_stats_provenance"] = stored_prov
        if stored_admissible is not None and stored_admissible != recomputed_admissible:
            refuse("arm_admission_label_disagrees_with_recomputation",
                   f"臂内件存量 `admissible_for_bc={stored_admissible}` 与按 provenance={prov!r} "
                   f"重算的 {recomputed_admissible} **不一致** ⇒ 实物内部自相矛盾，两个都不采信",
                   "裁定 93.4 第 1 条（标签派生对数据质量盲）+ 缺陷类 ⑲")
        if stored_prov is not None and stored_prov != c2_admission.get("stats_provenance"):
            refuse("arm_provenance_label_disagrees_with_recomputation",
                   f"臂内件存量 `stats_provenance={stored_prov!r}` 与归一化后的 "
                   f"{c2_admission.get('stats_provenance')!r} 不一致",
                   "裁定 87.4（别名 → 正典；BC 硬闸只认 `== formal40_bc_source`）")
        if c2_admission.get("admissible_for_bc") is not True:
            refuse("admissible_for_bc_not_true",
                   f"`admissible_for_bc={c2_admission.get('admissible_for_bc')}`（provenance={prov!r}，"
                   f"可进 BC 的只有 {list(BC_ADMISSIBLE_PROVENANCES)}）⇒ **BC 被禁**",
                   "裁定 97.5 + 85.4-3（同源硬闸）")
        if prov != STATS_PROVENANCE_FORMAL40_BC:
            refuse("tp5_same_source_not_satisfied",
                   f"`stats_provenance={prov!r}` ≠ `{STATS_PROVENANCE_FORMAL40_BC}` ⇒ `Tp5` 同源不成立"
                   " ⇒ **BC 被禁**（pilot 10 集与 formal 40 集不是同一批数据，stats 不得互替）",
                   "裁定 85.4-3 / C2 的牙 Tp5_bc_admission_requires_formal40_bc_source")

        # ── R5：裁定 97.3-4 的一次性前置（`G14` 实测翻转；`checked_by=F`）─────────────
        g14_missing = [k for k in G14_PRECONDITION_FIELDS if dec.get(k) in (None, "")]
        checks["g14_precondition_fields_missing"] = g14_missing
        if g14_missing:
            refuse("g14_flip_precondition_not_measured",
                   f"`G14` 的实测翻转证据未在声明里给出（缺 {g14_missing}）⇒ not_measured。"
                   "它是**一次性前置**（不是把 G24/G25 升回 class 1）：`G14` 若恒真，"
                   "「主线臂全绿」就不可信，而第 1 步就要吃这个绿。**语义判断归 F**"
                   "（`checked_by=F`）；本闸只核证据件的**存在与 sha**。可接受的证据件 = F 的每轮"
                   "台账产物，或同轮 `gate_verdict.json` 本身",
                   "裁定 97.2 + 97.3-4（`checked_by=F`、`checked_when=A2 第 1 步开跑前`）")
            not_measured.append("g14_flip")
        else:
            g14_id = _stream_identity(REPO / _rel(dec["g14_flip_evidence_path"]))
            checks["g14_flip_evidence_identity"] = g14_id
            if g14_id.get("measurement_status") != "measured":
                refuse("g14_flip_evidence_unreadable",
                       f"`G14` 证据件读不到（{g14_id.get('why')}）⇒ not_measured",
                       "裁定 97.3-4")
            elif str(dec["g14_flip_evidence_sha256_12"]).lower() != g14_id["sha256_12"]:
                refuse("g14_flip_evidence_sha_mismatch",
                       f"`G14` 证据件复算 sha={g14_id['sha256_12']} ≠ 声明 "
                       f"{dec['g14_flip_evidence_sha256_12']}", "裁定 93.4 第 3 条")

    # ── R6：同源硬闸的数据侧（npz 身份）+ 同频纪律 ──────────────────────────────────
    if npz_path is not None:
        npz_id = _stream_identity(REPO / _rel(npz_path))
        checks["npz_identity"] = npz_id
        if npz_id.get("measurement_status") != "measured":
            refuse("npz_unreadable", f"npz 读不到（{npz_id.get('why')}）⇒ not_measured",
                   "裁定 86.0/86.1/90.4-4（权威读路径 = npz + --s1-frames）")
            not_measured.append("npz")
        elif npz_sha256_12_declared and str(npz_sha256_12_declared).lower() != npz_id["sha256_12"]:
            refuse("npz_sha256_mismatch",
                   f"npz 复算 sha={npz_id['sha256_12']} ≠ 声明 {npz_sha256_12_declared} ⇒ 数据不是同一批",
                   "裁定 85.4-3（同源硬闸）")
    else:
        checks["npz_identity"] = {"measurement_status": "not_measured",
                                  "why": "调用方未声明 npz 路径（BC 装载时必须给）"}
        not_measured.append("npz")
        refuse("npz_identity_not_declared",
               "调用方未声明 npz 路径 ⇒ 数据身份 `not_measured`。**权威读路径 = npz + "
               "`--s1-frames`**（裁定 86.0/86.1/90.4-4），没有 npz 身份就没有同源可判 ⇒ 拒绝",
               "裁定 85.4-3（同源硬闸）+ 86.0/86.1")
    if control_hz is None:
        checks["control_hz"] = {"measurement_status": "not_measured",
                                "required": MAINLINE_CONTROL_HZ,
                                "why": "调用方未声明；由数据装载侧的 `params:119` 同频纪律强制"}
        not_measured.append("control_hz")
        refuse("control_hz_not_declared",
               "调用方未声明 control_hz ⇒ 同频纪律无法核（`params:119`：S1 示范 / S3 BC / S5 评测 / "
               "S6 RL 采样**必须同值 29.4118 Hz**，跨值不得并列）⇒ 拒绝",
               "`params:119` 同频纪律")
    else:
        ok_hz = abs(float(control_hz) - MAINLINE_CONTROL_HZ) < 1e-9
        checks["control_hz"] = {"measurement_status": "measured", "value": float(control_hz),
                                "required": MAINLINE_CONTROL_HZ, "matches": ok_hz}
        if not ok_hz:
            refuse("control_hz_off_caliber",
                   f"control_hz={control_hz} ≠ {MAINLINE_CONTROL_HZ}（S1/S3/S5/S6 必须同值，跨值不得并列）",
                   "`params:119` 同频纪律")

    admitted = not blocking
    decision = {
        "artifact": "bc_admission_decision",
        "module": "harness/bc_admission_gate.py",
        "module_representation_version": MODULE_REPRESENTATION_VERSION,
        "as_of": as_of, "consumer": consumer,
        "admitted": admitted,
        "decision_measurement_status": ("measured" if not not_measured else "not_measured"),
        "not_measured_items": not_measured,
        "blocking_refusals": blocking,
        "warnings": warnings,
        "bc_blocking_caliber": ("**只有三个**：`verdict_class1 = RED` 或 `admissible_for_bc = false` "
                                "或 `Tp5` 同源不成立（裁定 97.5）。**顶层 `verdict=RED` 本身不再等于"
                                "「BC 被禁」**；但 class-2/3 的红照样登记、照样在 S5 前清零"),
        "top_level_verdict_is_not_a_stop_reason": (
            "裁定 97.5：任何线（含 D 自己）不得再拿顶层 RED 当停训理由"),
        "declaration_as_given": dec,
        "checks": checks,
        "authority": ("裁定 93.4（AND 闸 + 自己复算 sha，不一致 ⇒ LearnerRefused）· 96.1-④（成对广播、"
                      "不许 glob 挑份）· 97.3-3（AND 收窄到 `verdict_class1`）· 97.5（三个禁训判据）· "
                      "85.4-3（同源硬闸）· 97.2/97.3-4（`G14` 实测翻转的一次性前置）"),
        "capability_claim": False,
        "success_rate_column": "not_an_exit_criterion",
        "gpu_used": False,
    }
    decision["reason_verbatim"] = (blocking[0]["reason_verbatim"] if blocking else
                                   "三个禁训判据都不成立 ⇒ 准入")
    if not admitted and raise_on_refusal:
        raise LearnerRefused(blocking[0]["reason_code"], decision)
    return decision


# ══════════════════ 两向变异体自检（裁定 93.8：Ⅰ 类闸必须两向）══════════════════
FIXTURE_STATS_NAME = ("s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.05"
                      "__mainline_path_check.json")
FIXTURE_REPRESENTATION_VERSION = "fixture-s1-sim-demo-bidir-quantiles-with-scale-floor-coef0.05-v1"
FIXTURE_BLIND_DIMS = [0, 3, 5, 7, 10, 12]


def _strip_priv(dec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """把夹具里的 `_` 私键拆出来（它们不是声明字段，不该进 `declaration_as_given`）。"""
    pub = {k: v for k, v in dec.items() if not k.startswith("_")}
    priv = {k: v for k, v in dec.items() if k.startswith("_")}
    return pub, priv


def _write_fixture(root: pathlib.Path, *, verdict: str = "RED", verdict_class1: str | None = "PASS",
                   declared_class1: str | None = None,
                   provenance: str = STATS_PROVENANCE_FORMAL40_BC,
                   admissible: bool | None = None, arm_n_lines_note: str = "fixture",
                   with_bc_inputs: bool = False) -> dict:
    """造一个**合成**闸跑目录（明确标注 `is_c2_authoritative_product=False`）。

    为什么需要合成件：截至本件落盘，C2 的**任何**一轮实物闸跑都还没有 `verdict_class1` 字面值
    （裁定 97.3-1/2 刚进码、下一轮才会产出）⇒ 「必须放行」这一向在实物上**无法**验证。
    合成件只用于验**本模块的判据形状**，**不得**被引用成"C2 的闸绿了"。
    """
    run = root / "fixture_gate_run"
    (run / "arm_mainline").mkdir(parents=True, exist_ok=True)
    gv: dict[str, Any] = {"artifact": "c2_norm_contract_gate_FIXTURE", "verdict": verdict,
                          "ok": verdict == "PASS", "n_checks": 54,
                          "is_c2_authoritative_product": False,
                          "fixture_note": ("**合成件**：只为验 A2 准入闸的判据形状。"
                                           "顶层 `verdict` 故意与 `verdict_class1` **不同向**，"
                                           "用来证明「顶层 RED 不是停训理由」（裁定 97.5）")}
    if verdict_class1 is not None:
        gv["verdict_class1"] = verdict_class1
    gvp = run / "gate_verdict.json"
    gvp.write_text(json.dumps(gv, ensure_ascii=False, indent=1))
    npz = root / "fixture_states_14d.npz"
    npz.write_bytes(b"FIXTURE-NPZ-BYTES")
    npz_id = _stream_identity(npz)
    stats_dir = run / "arm_mainline" / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)
    statsp = stats_dir / FIXTURE_STATS_NAME
    statsp.write_text(json.dumps(
        {"artifact": "FIXTURE_stats", "is_c2_authoritative_product": False,
         "stats_provenance": provenance, "case": "quantiles_with_scale_floor",
         "family": "F1_physical_range_fraction", "coef": 0.05, "n_dims": 14,
         "representation_version": FIXTURE_REPRESENTATION_VERSION}, ensure_ascii=False, indent=1))
    stats_id = _stream_identity(statsp)
    arm: dict[str, Any] = {
        "status": "FIXTURE", "stats_provenance": provenance, "arm_n_lines_note": arm_n_lines_note,
        "bc_admission": bc_admission(provenance, gate_verdict=verdict,
                                     gate_verdict_class1=verdict_class1,
                                     gate_run_dir=_rel(run),
                                     gate_verdict_sha256_12=None)}
    if with_bc_inputs:
        # 实物臂内件里 BC 输入面长这样（`checked_path` / `checked_path_sha256_12` /
        # `heldout_per_dim_blindness_ruling_94_3`）⇒ 夹具照抄形状，好让解析腿与同源交叉核能被验。
        arm["checked_path"] = _rel(npz)
        arm["checked_path_sha256_12"] = npz_id["sha256_12"]
        arm["npz_manifest_sha256_12"] = "000000000000"
        arm["heldout_per_dim_blindness_ruling_94_3"] = {
            "measurement_status": "measured", "n_dims": 14, "blind_dim_threshold": 8,
            "correctness_blind_dims_union": FIXTURE_BLIND_DIMS,
            "note": "FIXTURE：正确性族在这些维上无从触发 ⇒ 它们的 PASS 不是「已验证」"}
        arm["next_required_action"] = "FIXTURE 的过期散文（用来验「登记为 warning、不阻塞」这条路）"
    if admissible is not None:                       # 变异体：强行改写标签（模拟"标签错"）
        arm["bc_admission"]["admissible_for_bc"] = admissible
    armp = run / "arm_mainline" / "mainline_status.json"
    armp.write_text(json.dumps(arm, ensure_ascii=False, indent=1))
    g14 = root / "fixture_g14_flip_evidence.json"
    g14.write_text(json.dumps({"artifact": "FIXTURE_g14_flip_evidence", "flip_measured": True,
                               "is_c2_authoritative_product": False}, ensure_ascii=False, indent=1))
    arm_id = _stream_identity(armp)
    gv_id = _stream_identity(gvp, scan_keys=("verdict", "verdict_class1"))
    # `declared_class1` 与产物里的 `verdict_class1` **可以故意不同**：用来造「C2 声明了 PASS、
    # 但产物是早于裁定 97.3 的形态（没有这个字面值）」这一案 ⇒ 必须落 `not_measured` 并拒绝，
    # **不许拿顶层 `verdict` 顶替**（顶替 = 把"没测这一项"谎报成"测了、且与顶层同值"）。
    dec_class1 = verdict_class1 if declared_class1 is None else declared_class1
    return {"declared_by": "FIXTURE(not C2)", "as_of": datetime.now().astimezone().isoformat(),
            "gate_run_dir": _rel(run),
            "arm_mainline_status_path": _rel(armp),
            "arm_mainline_status_sha256_12": arm_id["sha256_12"],
            "arm_mainline_status_n_lines_wc": arm_id["n_lines_wc"],
            "arm_mainline_status_n_lines_splitlines": arm_id["n_lines_splitlines"],
            "gate_verdict_path": _rel(gvp),
            "gate_verdict_sha256_12": gv_id["sha256_12"],
            "gate_verdict_n_lines_wc": gv_id["n_lines_wc"],
            "gate_verdict_n_lines_splitlines": gv_id["n_lines_splitlines"],
            "verdict_class1": dec_class1,
            "g14_flip_evidence_path": _rel(g14),
            "g14_flip_evidence_sha256_12": _stream_identity(g14)["sha256_12"],
            "g14_flip_checked_by": "FIXTURE", "g14_flip_checked_when": "FIXTURE",
            "_verdict_top_level": verdict,
            "_arm_bytes": arm_id["n_bytes"], "_gv_bytes": gv_id["n_bytes"],
            "_npz_path": _rel(npz), "_npz_sha256_12": npz_id["sha256_12"],
            "_stats_path": _rel(statsp), "_stats_sha256_12": stats_id["sha256_12"],
            "_stats_bytes": stats_id["n_bytes"],
            "_stats_representation_version": FIXTURE_REPRESENTATION_VERSION,
            "_stats_provenance": provenance,
            "_checked_path": (_rel(npz) if with_bc_inputs else None),
            "_checked_path_sha256_12": (npz_id["sha256_12"] if with_bc_inputs else None),
            "_with_bc_inputs": with_bc_inputs,
            "_is_c2_authoritative_product": False}


BROADCAST_TAMPERS = ("arm_sha", "gv_sha", "drop_gv_table", "duplicate_arm_path_row",
                     "npz_sha", "stats_sha", "toplevel_arm", "class1_row", "drop_as_of",
                     "bare_n_lines_row", "wrong_caliber_n_lines")


def _write_broadcast_fixture(root: pathlib.Path, fx: dict[str, Any], *,
                             tamper: str | None = None) -> pathlib.Path:
    """造一份与 C2 的实物广播件**同构**的合成 markdown（明确标注是合成件）。

    存在的理由：解析腿（`parse_c2_broadcast`）是 Ⅰ 类通路 —— 它一旦把「挑一份」或「猜一个值」
    当成正常路径，BC 就会合法吃进错的 stats。所以它的两向必须在**与实物同构的形状**上验，
    不能只在 dict 上验（dict 喂进去等于跳过了解析）。
    """
    root.mkdir(parents=True, exist_ok=True)
    _, priv = _strip_priv(dict(fx))
    arm_sha = fx["arm_mainline_status_sha256_12"]
    gv_sha = fx["gate_verdict_sha256_12"]
    arm_path = fx["arm_mainline_status_path"]
    npz_sha = priv["_checked_path_sha256_12"] or priv["_npz_sha256_12"]
    stats_sha = priv["_stats_sha256_12"]
    vc1 = fx["verdict_class1"]
    if tamper == "arm_sha":
        arm_sha = "0" * 12
    if tamper == "gv_sha":
        gv_sha = "0" * 12
    if tamper == "npz_sha":
        npz_sha = "0" * 12
    if tamper == "stats_sha":
        stats_sha = "0" * 12
    if tamper == "toplevel_arm":
        arm_path = TOPLEVEL_CONVENIENCE_COPY
    if tamper == "class1_row":
        vc1 = "RED"
    # 裁定 98.5-②：夹具默认**点名口径**；两条变异专门验「裸键」与「口径写反」都不会造成假红/假绿
    line_key = "n_lines_splitlines"
    arm_lines = fx["arm_mainline_status_n_lines_splitlines"]
    gv_lines = fx["gate_verdict_n_lines_splitlines"]
    if tamper == "bare_n_lines_row":
        line_key = "n_lines"                       # 裸键（裁定 98.5-② 禁止的形状）
    if tamper == "wrong_caliber_n_lines":
        arm_lines = fx["arm_mainline_status_n_lines_wc"]   # 名字写 splitlines、值取 wc ⇒ 名字与值不符
    as_of_line = "" if tamper == "drop_as_of" else \
        "> `as_of = 2026-09-30T13:45:57+08:00`（**FIXTURE 的 as_of**，不是 C2 的读数）\n"
    dup_row = ("| 完整路径 | `%s` |\n" % priv["_stats_path"]) if tamper == "duplicate_arm_path_row" else ""
    gv_block = "" if tamper == "drop_gv_table" else (
        "**② 同轮闸判词（合成件）**\n\n"
        "| 项 | 值 |\n|---|---|\n"
        "| 完整路径 | `%s` |\n"
        "| `sha256[:12]` | `%s` |\n"
        "| `%s` | %d |\n"
        "| `bytes` | %d |\n"
        "| `verdict` | **%s** |\n"
        "| `verdict_class1` | **%s**（裁定 97.3-2 新增；**这才是 BC 准入 AND 的那一个**） |\n"
        % (fx["gate_verdict_path"], gv_sha, line_key, gv_lines,
           priv.get("_gv_bytes", 0), fx.get("_verdict_top_level", "RED"), vc1))
    doc = (
        "# FIXTURE 广播件（**合成件，不是 C2 的产物**）· `_write_broadcast_fixture`\n\n"
        + as_of_line + "\n"
        "## 1. 成对身份（**两条必须一起用，缺一 ⇒ `LearnerRefused`**）\n\n"
        "**① BC 消费口径（合成件）**\n\n"
        "| 项 | 值 |\n|---|---|\n"
        "| 完整路径 | `%s` |\n" % arm_path
        + dup_row +
        "| `sha256[:12]` | `%s` |\n"
        "| `%s` | %d |\n"
        "| `bytes` | %d |\n\n" % (arm_sha, line_key, arm_lines,
                                    priv.get("_arm_bytes", 0))
        + gv_block + "\n"
        "## 3. 归一化 stats：**唯一一档**（合成件）\n\n"
        "| 项 | 值 |\n|---|---|\n"
        "| 完整路径 | `%s` |\n"
        "| `sha256[:12]` | `%s` · `bytes` %d · `n_lines_splitlines` 1 |\n"
        "| `representation_version` | `%s` |\n"
        "| `stats_provenance` | `%s`（裁定 85.4-3 同源硬闸：**BC 只认这一档标签**） |\n"
        "| `n_dims` | 14 |\n"
        "| 源数据 | `%s` = `%s`（40 集 / 11035 帧）· `npz_manifest_sha256_12 = 000000000000` |\n\n"
        % (priv["_stats_path"], stats_sha, priv["_stats_bytes"],
           priv["_stats_representation_version"], priv["_stats_provenance"],
           priv["_checked_path"] or priv["_npz_path"], npz_sha)
        + "## 6. 冻结与停点\n\n- **合成件**：不得被引用成「C2 已广播」或「BC 可开跑」。\n")
    out = root / "FIXTURE_c2_broadcast.md"
    out.write_text(doc)
    return out


def _write_broadcast_json_fixture(root: pathlib.Path, fx: dict[str, Any], *,
                                  tamper: str | None = None) -> pathlib.Path:
    """造一份与 C2 的**机器可读**广播件（`bc_consumption_caliber`）同构的合成 JSON。"""
    root.mkdir(parents=True, exist_ok=True)
    _, priv = _strip_priv(dict(fx))
    arm_sha = ("0" * 12) if tamper == "json_arm_sha" else fx["arm_mainline_status_sha256_12"]
    doc = {"artifact": "FIXTURE_toplevel_convenience_copy_identity",
           "is_c2_authoritative_product": False,
           "as_of": "2026-09-30T14:10:26+08:00",
           "bc_consumption_caliber": {
               "declaration": "FIXTURE：BC 消费口径 = 臂内件",
               "path": fx["arm_mainline_status_path"], "sha256_12": arm_sha,
               "n_lines_splitlines": fx["arm_mainline_status_n_lines_splitlines"],
               "n_lines_wc": fx["arm_mainline_status_n_lines_wc"],
               "ends_with_newline": False, "bytes": priv["_arm_bytes"],
               "paired_gate_verdict": {
                   "path": fx["gate_verdict_path"],
                   "sha256_12": fx["gate_verdict_sha256_12"],
                   "n_lines_splitlines": fx["gate_verdict_n_lines_splitlines"],
                   "n_lines_wc": fx["gate_verdict_n_lines_wc"],
                   "bytes": priv["_gv_bytes"], "verdict": fx["_verdict_top_level"],
                   "verdict_class1": fx["verdict_class1"], "n_checks": 54, "n_red": 0,
                   "n_red_class1": 0},
               "source_data_identity": {
                   "checked_path": priv["_checked_path"],
                   "checked_path_sha256_12": priv["_checked_path_sha256_12"],
                   "stats_provenance": priv["_stats_provenance"],
                   "n_frames": 11035, "n_episodes": 40},
               "consumer_obligation_A2_T_A2_7": "FIXTURE（五条义务的形状见 C2 的实物件）"}}
    out = root / "FIXTURE_c2_broadcast.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    return out


def selftest(*, workdir: pathlib.Path | None = None) -> dict[str, Any]:
    """**两向**：正向（该放行必须放行）+ 反向（每个禁训判据都必须真的咬）。"""
    root = workdir or (REPO / "runs/vla/a2_bc_admission_gate_selftest")
    root.mkdir(parents=True, exist_ok=True)
    rows: dict[str, Any] = {}

    def call(dec: Any, **kw) -> dict:
        try:
            d = bc_admission_check(declaration=dec, raise_on_refusal=False, **kw)
            return {"raised": False, "admitted": d["admitted"],
                    "reason_codes": [b["reason_code"] for b in d["blocking_refusals"]],
                    "not_measured": d["not_measured_items"], "decision": d}
        except Exception as exc:                                      # noqa: BLE001
            return {"raised": True, "admitted": False, "exc": f"{type(exc).__name__}: {exc}",
                    "reason_codes": [], "not_measured": [], "decision": None}

    def rec(name: str, *, expect_admitted: bool, expect_code: str | None, res: dict, tamper: str):
        codes = res["reason_codes"]
        ok = (res["admitted"] is expect_admitted
              and (expect_code is None or expect_code in codes))
        rows[name] = {"ok": ok, "expect_admitted": expect_admitted, "got_admitted": res["admitted"],
                      "expect_reason_code": expect_code, "got_reason_codes": codes,
                      "tamper": tamper,
                      "not_measured": res["not_measured"]}

    # ── 正向 ①：完整声明 + class1=PASS（顶层 verdict 故意 = RED）⇒ 必须放行 ──
    dec, _priv1 = _strip_priv(_write_fixture(root / "pos1", verdict="RED", verdict_class1="PASS"))
    npz, npzsha = _priv1["_npz_path"], _priv1["_npz_sha256_12"]
    r_pos1 = call(dec, npz_path=npz, npz_sha256_12_declared=npzsha,
                  control_hz=MAINLINE_CONTROL_HZ)
    rec("POS1_class1_pass_top_level_red_is_admitted", expect_admitted=True, expect_code=None,
        res=r_pos1, tamper="无（正向）：顶层 verdict=RED 而 verdict_class1=PASS ⇒ 裁定 97.5 要求放行")
    rows["POS1_class1_pass_top_level_red_is_admitted"]["proof_top_level_red_did_not_block"] = (
        r_pos1["decision"]["checks"]["top_level_verdict_from_artifact"] == "RED"
        and r_pos1["decision"]["checks"]["verdict_class1_from_artifact"] == "PASS")

    # ── 正向 ②：顶层 PASS + class1 PASS ⇒ 也放行（两向同框，证明判据不是"恒放行"）──
    dec2, _priv2 = _strip_priv(_write_fixture(root / "pos2", verdict="PASS", verdict_class1="PASS"))
    npz2, npzsha2 = _priv2["_npz_path"], _priv2["_npz_sha256_12"]
    rec("POS2_both_pass_is_admitted", expect_admitted=True, expect_code=None,
        res=call(dec2, npz_path=npz2, npz_sha256_12_declared=npzsha2,
                 control_hz=MAINLINE_CONTROL_HZ),
        tamper="无（正向）：顶层与 class1 同向 PASS")

    # ── 反向：逐条禁训判据 ──
    def fresh(**kw):
        d, priv = _strip_priv(_write_fixture(root / kw.pop("sub"), **kw))
        return d, priv["_npz_path"], priv["_npz_sha256_12"]

    d, n, ns = fresh(sub="m1", verdict="RED", verdict_class1="RED")
    rec("NEG1_verdict_class1_red", expect_admitted=False, expect_code="verdict_class1_not_pass",
        res=call(d, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ),
        tamper="闸产物 `verdict_class1` PASS→RED")

    # NEG2 = **不许拿顶层 verdict 顶替**：产物里没有 class1、但顶层是 PASS ⇒ 必须拒（不是放行）
    d, n, ns = fresh(sub="m2", verdict="PASS", verdict_class1=None, declared_class1="PASS")
    r = call(d, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ)
    rec("NEG2_no_class1_literal_is_not_measured_not_top_level_substitution",
        expect_admitted=False, expect_code="verdict_class1_not_measured", res=r,
        tamper="产物里删掉 `verdict_class1` 键、顶层留 PASS，而声明仍写 PASS（早于裁定 97.3 的产物形态）")
    rows["NEG2_no_class1_literal_is_not_measured_not_top_level_substitution"][
        "proof_no_substitution"] = ("verdict_class1" in (r["not_measured"] or []))

    d, n, ns = fresh(sub="m3", verdict="RED", verdict_class1="PASS",
                     provenance="formal40_lerobot_crosscheck")
    rec("NEG3_crosscheck_provenance_tp5", expect_admitted=False,
        expect_code="tp5_same_source_not_satisfied",
        res=call(d, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ),
        tamper="provenance → `formal40_lerobot_crosscheck`（只作交叉核对、`Tp5` 必红）")

    d, n, ns = fresh(sub="m4", verdict="RED", verdict_class1="PASS", admissible=False)
    rec("NEG4_admissible_for_bc_false", expect_admitted=False,
        expect_code="arm_admission_label_disagrees_with_recomputation",
        res=call(d, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ),
        tamper="臂内件 `admissible_for_bc` true→false（模拟「标签错」这一侧的失效）")

    d, n, ns = fresh(sub="m5", verdict="RED", verdict_class1="PASS")
    bad = dict(d); bad["gate_verdict_sha256_12"] = "0" * 12
    rec("NEG5_gate_verdict_sha_mismatch", expect_admitted=False,
        expect_code="gate_verdict_sha256_mismatch",
        res=call(bad, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ),
        tamper="声明的 `gate_verdict_sha256_12` 改成 12 个 0（复算对不上）")

    d, n, ns = fresh(sub="m6", verdict="RED", verdict_class1="PASS")
    bad = dict(d); bad["arm_mainline_status_sha256_12"] = "0" * 12
    rec("NEG6_arm_sha_mismatch", expect_admitted=False,
        expect_code="arm_mainline_status_sha256_mismatch",
        res=call(bad, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ),
        tamper="声明的臂内件 sha 改成 12 个 0")

    d, n, ns = fresh(sub="m7", verdict="RED", verdict_class1="PASS")
    bad = dict(d); bad["verdict_class1"] = "RED"
    rec("NEG7_class1_declaration_mismatch", expect_admitted=False,
        expect_code="verdict_class1_declaration_mismatch",
        res=call(bad, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ),
        tamper="声明 `verdict_class1=RED` 而实物是 PASS（广播与实物不相等）")

    rec("NEG8_declaration_absent", expect_admitted=False,
        expect_code="declaration_absent_or_incomplete",
        res=call(None, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ),
        tamper="声明整体缺失（= 今天 C2 尚未广播的实况）⇒ 必须拒，**不许 glob 补**")

    d, n, ns = fresh(sub="m9", verdict="RED", verdict_class1="PASS")
    bad = dict(d); bad.pop("g14_flip_evidence_path")
    rec("NEG9_g14_precondition_missing", expect_admitted=False,
        expect_code="g14_flip_precondition_not_measured",
        res=call(bad, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ),
        tamper="删掉 `G14` 实测翻转的证据路径（裁定 97.3-4 的一次性前置）")

    d, n, ns = fresh(sub="m10", verdict="RED", verdict_class1="PASS")
    rec("NEG10_npz_sha_mismatch", expect_admitted=False, expect_code="npz_sha256_mismatch",
        res=call(d, npz_path=n, npz_sha256_12_declared="0" * 12,
                 control_hz=MAINLINE_CONTROL_HZ),
        tamper="npz 声明 sha 改成 12 个 0（同源硬闸，裁定 85.4-3）")

    d, n, ns = fresh(sub="m11", verdict="RED", verdict_class1="PASS")
    rec("NEG11_control_hz_off_caliber", expect_admitted=False, expect_code="control_hz_off_caliber",
        res=call(d, npz_path=n, npz_sha256_12_declared=ns, control_hz=50.0),
        tamper="control_hz 29.4118→50.0（跨频不得并列，`params:119`）")

    d, n, ns = fresh(sub="m12", verdict="RED", verdict_class1="PASS")
    bad = dict(d); bad["arm_mainline_status_path"] = "runs/vla/c2_norm_contract_20260929/mainline_status.json"
    rec("NEG12_arm_path_outside_declared_run_dir", expect_admitted=False,
        expect_code="declared_paths_not_inside_declared_run_dir",
        res=call(bad, npz_path=n, npz_sha256_12_declared=ns, control_hz=MAINLINE_CONTROL_HZ),
        tamper="臂内件路径换成**顶层同名件**（= 补单二 §六 点名的「挑份」形状）")

    d, n, ns = fresh(sub="m13", verdict="RED", verdict_class1="PASS")
    rec("NEG14_npz_not_declared", expect_admitted=False, expect_code="npz_identity_not_declared",
        res=call(d, npz_path=None, control_hz=MAINLINE_CONTROL_HZ),
        tamper="不声明 npz 路径（数据身份 not_measured）⇒ 必须拒，不许「其它都对就放行」")

    d, n, ns = fresh(sub="m14", verdict="RED", verdict_class1="PASS")
    rec("NEG15_control_hz_not_declared", expect_admitted=False,
        expect_code="control_hz_not_declared",
        res=call(d, npz_path=n, npz_sha256_12_declared=ns, control_hz=None),
        tamper="不声明 control_hz（同频纪律无法核）⇒ 必须拒")

    # ── raise 语义：默认必须**抛**，不是返回 False ──
    raised = None
    try:
        bc_admission_check(declaration=None, raise_on_refusal=True)
        raised = False
    except LearnerRefused as exc:
        raised = True
        raised_code = exc.reason_code
    rows["NEG13_refusal_raises_learner_refused"] = {
        "ok": raised is True, "expect": "LearnerRefused", "got_raised": raised,
        "got_reason_code": (raised_code if raised else None),
        "tamper": "无（正向验异常语义）：派工第 3 条要求「不一致 ⇒ `LearnerRefused`，不是继续、不是只告警」"}

    # ── 广播件腿（Ⅰ 类通路）：正向 1 条 + 反向 9 条，全部走**真解析**（不喂 dict）──
    def res_of_artifact(a: dict) -> dict:
        d = a.get("decision")
        codes = ([b["reason_code"] for b in d["blocking_refusals"]] if isinstance(d, dict) else [])
        codes += [b["reason_code"] for b in (a.get("extra_blocking") or [])]
        return {"raised": False, "admitted": a.get("admitted"),
                "reason_codes": [c for c in codes if c],
                "not_measured": a.get("not_measured_items") or [], "decision": a}

    def g14_of(fx: dict) -> dict:
        return {"g14_flip_evidence_path": fx["g14_flip_evidence_path"],
                "g14_flip_evidence_sha256_12": fx["g14_flip_evidence_sha256_12"],
                "g14_flip_checked_by": "FIXTURE（语义判断在实物上归 F）",
                "g14_flip_checked_when": "FIXTURE"}

    fx3 = _write_fixture(root / "pos3", verdict="RED", verdict_class1="PASS", with_bc_inputs=True)
    doc3 = _write_broadcast_fixture(root / "pos3", fx3)
    a3 = consume_c2_broadcast(doc_path=doc3, g14=g14_of(fx3))
    rec("POS3_broadcast_doc_parsed_and_admitted", expect_admitted=True, expect_code=None,
        res=res_of_artifact(a3),
        tamper="无（正向）：与 C2 实物**同构**的广播件 ⇒ 解析腿必须给出唯一声明并放行")
    rows["POS3_broadcast_doc_parsed_and_admitted"]["proof_no_globbing"] = bool(
        a3["parse"]["parse_report"]["no_globbing_by_construction"]
        and a3["parse"]["declaration"]["gate_run_dir"].endswith("fixture_gate_run"))
    rows["POS3_broadcast_doc_parsed_and_admitted"]["proof_admission_is_not_start_authorization"] = (
        a3["authorization_to_start_bc"] is False)
    rows["POS3_broadcast_doc_parsed_and_admitted"]["proof_bc_inputs_crosschecked"] = (
        a3["npz_crosscheck"].get("same_source_holds") is True
        and a3["bc_stats_input"]["recomputed"]["sha256_12"]
        == a3["bc_stats_input"]["declared"]["sha256_12_declared"])

    doc_neg_cases = [
        ("NEG16_broadcast_arm_sha_tampered", "arm_sha", "arm_mainline_status_sha256_mismatch",
         "广播件①的 sha 改成 12 个 0（复算对不上 ⇒ 拒）"),
        ("NEG17_broadcast_gv_sha_tampered", "gv_sha", "gate_verdict_sha256_mismatch",
         "广播件②的 sha 改成 12 个 0（「闸绿」这个事实的唯一出处对不上 ⇒ 拒）"),
        ("NEG18_broadcast_gate_verdict_block_dropped", "drop_gv_table", "broadcast_pair_marks_not_two",
         "删掉②那一块 ⇒ 成对身份只剩一条 ⇒ 解析不出唯一声明（**不许拿①自己当准入**）"),
        ("NEG19_broadcast_ambiguous_path_row", "duplicate_arm_path_row", "broadcast_row_ambiguous",
         "①里多塞一行「完整路径」⇒ 命中 2 行 ⇒ 不可判、**不挑一份**"),
        ("NEG20_broadcast_npz_disagrees_with_arm", "npz_sha", "npz_declaration_disagrees_with_arm",
         "§3 的 npz sha 与臂内件自述的 `checked_path_sha256_12` 不同 ⇒ 同源不成立（裁定 85.4-3）"),
        ("NEG21_broadcast_arm_is_toplevel_copy", "toplevel_arm",
         "declared_arm_is_toplevel_convenience_copy",
         "①指向**顶层便捷副本** ⇒ 各线一律不消费顶层件（裁定 96.1-④ / §D96.9）"),
        ("NEG22_broadcast_stats_sha_tampered", "stats_sha", "stats_sha256_mismatch",
         "§3 的 stats sha 改成 12 个 0 ⇒ BC 真正要吃的那一档身份对不上"),
        ("NEG23_broadcast_class1_declaration_mismatch", "class1_row",
         "verdict_class1_declaration_mismatch",
         "广播件写 `verdict_class1=RED` 而实物是 PASS ⇒ 广播与实物不相等"),
        ("NEG24_broadcast_as_of_missing", "drop_as_of", "broadcast_as_of_not_found",
         "广播件没有 `as_of` ⇒ 声明缺必给字段（不许用「现在」顶替）"),
    ]
    for name, tamper, expect_code, why in doc_neg_cases:
        fxn = _write_fixture(root / name, verdict="RED", verdict_class1="PASS", with_bc_inputs=True)
        docn = _write_broadcast_fixture(root / name, fxn, tamper=tamper)
        an = consume_c2_broadcast(doc_path=docn, g14=g14_of(fxn))
        rec(name, expect_admitted=False, expect_code=expect_code, res=res_of_artifact(an), tamper=why)

    # ── 裁定 98.5 的三案：裸键 / 名字与值不符 / 机器可读载体（都不得造成**假红**）──
    fx5 = _write_fixture(root / "pos4", verdict="RED", verdict_class1="PASS", with_bc_inputs=True)
    doc5 = _write_broadcast_fixture(root / "pos4", fx5, tamper="bare_n_lines_row")
    a5 = consume_c2_broadcast(doc_path=doc5, g14=g14_of(fx5))
    r5 = res_of_artifact(a5)
    rec("POS4_bare_n_lines_row_is_registered_not_refused", expect_admitted=True, expect_code=None,
        res=r5, tamper="广播件用**裸 `n_lines`** 行（裁定 98.5-② 禁止的形状）⇒ 只登记、不拿它比对")
    rows["POS4_bare_n_lines_row_is_registered_not_refused"]["proof_registered"] = any(
        w["reason_code"].endswith("n_lines_not_declared_with_caliber")
        for w in a5["decision"]["warnings"])

    fx6 = _write_fixture(root / "pos5", verdict="RED", verdict_class1="PASS", with_bc_inputs=True)
    doc6 = _write_broadcast_fixture(root / "pos5", fx6, tamper="wrong_caliber_n_lines")
    a6 = consume_c2_broadcast(doc_path=doc6, g14=g14_of(fx6))
    rec("POS5_wrong_caliber_n_lines_is_warning_not_false_refusal", expect_admitted=True,
        expect_code=None, res=res_of_artifact(a6),
        tamper="行数**名字与值不符**（名 `splitlines`、值取 `wc`）⇒ 降级为 warning，**不得**假红 "
               "（这正是 §98.5 点名的「第 1 步白跑一轮」）")
    rows["POS5_wrong_caliber_n_lines_is_warning_not_false_refusal"]["proof_warning_not_blocking"] = (
        any(w["reason_code"] == "arm_mainline_status_n_lines_splitlines_mismatch"
            for w in a6["decision"]["warnings"])
        and "arm_mainline_status_n_lines_splitlines_mismatch" not in r5["reason_codes"]
        and a6["decision"]["admitted"] is True)

    fx7 = _write_fixture(root / "pos6", verdict="RED", verdict_class1="PASS", with_bc_inputs=True)
    doc7 = _write_broadcast_fixture(root / "pos6", fx7)
    js7 = _write_broadcast_json_fixture(root / "pos6", fx7)
    a7 = consume_c2_broadcast(doc_path=doc7, json_path=js7, g14=g14_of(fx7))
    rec("POS6_both_broadcast_carriers_agree_and_admitted", expect_admitted=True, expect_code=None,
        res=res_of_artifact(a7), tamper="无（正向）：markdown + 机器可读两件**互相相等** ⇒ 放行")
    rows["POS6_both_broadcast_carriers_agree_and_admitted"]["proof_crosscheck_measured"] = (
        a7["broadcast_crosscheck"].get("measurement_status") == "measured"
        and a7["broadcast_crosscheck"].get("agree") is True)

    fx8 = _write_fixture(root / "neg25", verdict="RED", verdict_class1="PASS", with_bc_inputs=True)
    doc8 = _write_broadcast_fixture(root / "neg25", fx8)
    js8 = _write_broadcast_json_fixture(root / "neg25", fx8, tamper="json_arm_sha")
    a8 = consume_c2_broadcast(doc_path=doc8, json_path=js8, g14=g14_of(fx8))
    rec("NEG25_broadcast_carriers_disagree", expect_admitted=False,
        expect_code="broadcast_sources_disagree", res=res_of_artifact(a8),
        tamper="两件载体的臂内件 sha 不一致 ⇒ **不挑一份**，两个都不采信")

    n_ok = sum(1 for v in rows.values() if v["ok"])
    pos = [k for k in rows if k.startswith("POS")]
    neg = [k for k in rows if k.startswith("NEG")]
    return {"artifact": "bc_admission_gate_selftest", "as_of": datetime.now().astimezone().isoformat(),
            "module_representation_version": MODULE_REPRESENTATION_VERSION,
            "module_identity": _stream_identity(pathlib.Path(__file__).resolve()),
            "fixture_root": _rel(root),
            "fixtures_are_synthetic": True,
            "fixtures_are_not_c2_products": ("**合成件不得被引用成「C2 的闸绿了」或「C2 已广播」**；"
                                             "自检里的广播件由 `_write_broadcast_fixture` 生成，"
                                             "只验**解析腿的判据形状**"),
            "rows": rows, "n_rows": len(rows), "n_ok": n_ok, "all_ok": n_ok == len(rows),
            "two_way": {"n_positive": len(pos), "n_negative": len(neg),
                        "positive_names": pos, "negative_names": neg,
                        "both_directions_covered": bool(pos) and bool(neg)},
            "c2_authority_reused_not_reimplemented": (
                "harness/norm_contract.py::bc_admission（本模块只 import 调用）"),
            "norm_contract_identity": _stream_identity(REPO / "harness/norm_contract.py"),
            "capability_claim": False, "gpu_used": False}


def probe_real(*, gate_run_dir: str | None = None, trial_from_latest_run: bool = False) -> dict[str, Any]:
    """**诊断**（不是消费决定）：拿当前 C2 的实物跑一遍准入，如实报结论。

    它**不会**替 C2 编一份声明：没有广播 ⇒ `declaration=None` ⇒ 结论就是 `refused`
    （`declaration_absent_or_incomplete`）。附带的扫描只用于说明"为什么还没到"，
    并明确标注 `probe_only_not_a_consumption_decision=True`。
    """
    gate = REPO / "runs/vla/c2_norm_contract_20260929/gate"
    scan_scope = "runs/vla/c2_norm_contract_20260929/gate/run_*（限定前缀 + maxdepth，裁定 94.9-2）"
    runs = sorted([d for d in gate.glob("run_*") if d.is_dir()], reverse=True)[:3] if gate.is_dir() else []
    observed = []
    for d in runs:
        gv = d / "gate_verdict.json"
        row = {"run_dir": _rel(d), "gate_verdict_json": _stream_identity(
            gv, scan_keys=("verdict", "verdict_class1")) if gv.exists() else
            {"measurement_status": "not_measured", "why": "gate_verdict.json 尚未落盘（该轮在制）"}}
        arm = d / "arm_mainline" / "mainline_status.json"
        row["arm_mainline_status"] = _stream_identity(arm) if arm.exists() else {
            "measurement_status": "not_measured", "why": "臂内件不在盘"}
        observed.append(row)
    dec = None
    trial_label = None
    trial_npz = trial_npz_sha = None
    trial_npz_info: dict[str, Any] = {"measurement_status": "not_measured",
                                      "why": "本轮未使用试算声明"}
    if gate_run_dir or (trial_from_latest_run and runs):
        rd = (REPO / _rel(gate_run_dir)) if gate_run_dir else runs[0]
        arm = rd / "arm_mainline" / "mainline_status.json"
        gv = rd / "gate_verdict.json"
        if arm.exists() and gv.exists():
            arm_id = _stream_identity(arm)
            gv_id = _stream_identity(gv, scan_keys=("verdict", "verdict_class1"))
            dec = {"declared_by": "A2-probe **试算件（不是 C2 的广播）**",
                   "as_of": datetime.now().astimezone().isoformat(timespec="seconds"),
                   "gate_run_dir": _rel(rd),
                   "arm_mainline_status_path": _rel(arm),
                   "arm_mainline_status_sha256_12": arm_id["sha256_12"],
                   "arm_mainline_status_n_lines_wc": arm_id["n_lines_wc"],
            "arm_mainline_status_n_lines_splitlines": arm_id["n_lines_splitlines"],
                   "gate_verdict_path": _rel(gv),
                   "gate_verdict_sha256_12": gv_id["sha256_12"],
                   "gate_verdict_n_lines_wc": gv_id["n_lines_wc"],
            "gate_verdict_n_lines_splitlines": gv_id["n_lines_splitlines"],
                   "verdict_class1": (gv_id.get("scanned") or {}).get("verdict_class1"),
                   "g14_flip_evidence_path": _rel(gv),
                   "g14_flip_evidence_sha256_12": gv_id["sha256_12"],
                   "g14_flip_checked_by": "**未由 F 判定**（试算件自带，语义判断仍归 F）",
                   "g14_flip_checked_when": datetime.now().astimezone().isoformat(timespec="seconds")}
            trial_label = ("**试算件**：由 A2 从最新一轮闸跑**自己拼**的声明，用来预验管路。"
                           "**它不是 C2 按裁定 96.1-④ 的广播** ⇒ 其 `admitted` 结果**不得**被"
                           "引用成「BC 可以开跑」；`g14_flip_checked_by` 也不是 F 的判定")
            # 试算件里连 npz 身份也一起拼：取**臂内件自己声明的** `checked_path` /
            # `checked_path_sha256_12`（= C2 说它这批 stats 是吃哪个 npz 生成的）⇒ 顺带验
            # 「A2 要装载的 npz」与「C2 生成 stats 时吃的 npz」是不是同一份（裁定 85.4-3 同源）。
            try:
                armj = json.loads(arm.read_text(errors="replace"))
                trial_npz = armj.get("checked_path")
                trial_npz_sha = armj.get("checked_path_sha256_12")
            except Exception:                                          # noqa: BLE001
                trial_npz = trial_npz_sha = None
            trial_npz_info = {"npz_path_from_arm": trial_npz, "npz_sha_from_arm": trial_npz_sha}
        else:
            trial_npz = trial_npz_sha = None
            trial_npz_info = {"measurement_status": "not_measured", "why": "臂内件或闸产物不在盘"}
    try:
        d = bc_admission_check(declaration=dec, raise_on_refusal=False,
                               npz_path=trial_npz, npz_sha256_12_declared=trial_npz_sha,
                               control_hz=(MAINLINE_CONTROL_HZ if dec else None))
        admitted, codes, nm = d["admitted"], [b["reason_code"] for b in d["blocking_refusals"]], \
            d["not_measured_items"]
        decision = d
    except Exception as exc:                                          # noqa: BLE001
        admitted, codes, nm, decision = False, [], [], f"{type(exc).__name__}: {exc}"
    return {"artifact": "bc_admission_probe_real",
            "as_of": datetime.now().astimezone().isoformat(timespec="seconds"),
            "probe_only_not_a_consumption_decision": True,
            "trial_declaration_used": bool(trial_label),
            "trial_declaration_warning": trial_label,
            "trial_npz_identity_source": trial_npz_info if (gate_run_dir or trial_from_latest_run)
            else {"measurement_status": "not_measured", "why": "本轮未使用试算声明"},
            "scan_scope": scan_scope, "n_runs_observed": len(observed), "runs": observed,
            "admitted": admitted, "blocking_reason_codes": codes, "not_measured_items": nm,
            "decision": decision,
            "interpretation_rule": INTERPRETATION_RULE,
            "capability_claim": False, "gpu_used": False}


INTERPRETATION_RULE = (
    "**`probe_real` 的结论不得被引用成「BC 被禁」或「BC 可跑」**（它是诊断件）；消费决定只能由 "
    "C2 的成对广播 + `bc_admission_check` 在 BC 入口处产出（裁定 96.1-④ / 97.5）。"
    "**`consume_c2_broadcast` 的 `admitted=true` 也只回答「准入判据成立」**，"
    "不等于「BC 可以开跑」：停点、预算与 GPU 窗口申报是另外的门（裁定 46 能力声明禁令不变）。")

START_AUTHORITY_DEFAULT = (
    "**准入成立 ≠ 本件就是开跑授权**。停点已由**裁定 98.6 解除**（用户三项批复落地 ⇒ "
    "「[A2] 第 1 步即刻可起跑」，`decisions_20260929.md` §98.6 / 日报 §D98.4）。"
    "但上卡仍须逐条走完 94.9-1② 的过渡协议：**申报（写入口脚本名，RR1(a)）→ 起跑那一刻实测三网 → "
    "落 `GPU_WINDOW.json` → 起跑前拒绝逻辑读 E 的参考实现 `card_busy()`（RR4：不读 B2 的副本）**。"
    "本件只回答「BC 入口的准入判据成不成立」，不代替那次申报。")
REMAINING_PRECONDITIONS_DEFAULT = (
    "① `daily_report.md` 里的事前申报（裁定 73 模板 + 入口脚本名，RR1(a)：E 收到后一行补词表）· "
    "② 起跑那一刻的三网实测 + `GPU_WINDOW.json`（`loadavg` 三点 + `nr_throttled`，cgroup v1）· "
    "③ 起跑前拒绝逻辑（外来 GPU 占用命中且未给 `--allow-cotenant` ⇒ `exit 3` + "
    "`refused_gpu_busy_<ts>.json`；读 E 的 `card_busy()`）· "
    "④ 预算：第 1 步的过拟合探针**不计入** 24 h；若单种子显示 >8 h ⇒ 必须报 D，不得静默超（裁定 98.1-②）· "
    "⑤ `CRITERIA_PREREGISTERED.json` 在盘（T-A2-8）且 checkpoint 选择规则已预登记（裁定 95.5-③）")


def parse_c2_broadcast_json(doc_path: Any) -> dict[str, Any]:
    """吃 C2 的**机器可读**成对广播件：`TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json`
    的 `bc_consumption_caliber`（D 在裁定 98.2-A 逐条亲核的就是这一份）。

    它与 markdown 广播件是**同一件事的两种载体** ⇒ 两件都给时必须**互相相等**（见
    `crosscheck_broadcast_sources`）；只给一件时以那一件为准，缺的那一面写 `not_measured`。
    """
    dp = (REPO / _rel(doc_path)) if not pathlib.Path(str(doc_path)).is_absolute() \
        else pathlib.Path(str(doc_path))
    doc_id = _stream_identity(dp)
    if doc_id.get("measurement_status") != "measured":
        raise BroadcastParseError("broadcast_doc_unreadable",
                                  f"JSON 广播件读不到（{doc_id.get('why')}）⇒ not_measured，不猜")
    try:
        dj = json.loads(dp.read_text(errors="replace"))
    except Exception as exc:                                          # noqa: BLE001
        raise BroadcastParseError("broadcast_json_unparseable",
                                  f"JSON 广播件解析失败：{type(exc).__name__}: {exc}") from exc
    cal = dj.get("bc_consumption_caliber")
    if not isinstance(cal, dict):
        raise BroadcastParseError("broadcast_json_missing_caliber",
                                  "JSON 广播件里没有 `bc_consumption_caliber` 对象 ⇒ 成对身份不可判")
    gv = cal.get("paired_gate_verdict")
    if not isinstance(gv, dict):
        raise BroadcastParseError("broadcast_json_missing_pair",
                                  "`bc_consumption_caliber` 里没有 `paired_gate_verdict` ⇒ 只有单条身份，"
                                  "成对广播不成立（裁定 96.1-④）")
    arm_path, gv_path = cal.get("path"), gv.get("path")
    arm_sha, gv_sha = cal.get("sha256_12"), gv.get("sha256_12")
    for name, val in (("arm.path", arm_path), ("arm.sha256_12", arm_sha),
                      ("paired_gate_verdict.path", gv_path), ("paired_gate_verdict.sha256_12", gv_sha),
                      ("paired_gate_verdict.verdict_class1", gv.get("verdict_class1"))):
        if val in (None, ""):
            raise BroadcastParseError("broadcast_json_field_missing",
                                      f"`bc_consumption_caliber` 缺 `{name}` ⇒ 声明不全，不猜")
    if ARM_DIR_TOKEN not in str(arm_path):
        raise BroadcastParseError(
            "declared_arm_is_toplevel_convenience_copy",
            f"声明的 BC 消费件 `{arm_path}` 不含 `{ARM_DIR_TOKEN}` ⇒ 是顶层便捷副本，各线一律不消费")
    run_dir = str(pathlib.PurePosixPath(str(gv_path)).parent)
    if not str(arm_path).startswith(run_dir + "/"):
        raise BroadcastParseError("broadcast_pair_not_same_round",
                                  f"臂内件（{arm_path}）不在②的 run 目录（{run_dir}）内 ⇒ 不是一轮")
    declaration: dict[str, Any] = {
        "declared_by": f"C2（机器可读广播件 `{_rel(dp)}`，sha256[:12]={doc_id['sha256_12']}）",
        "as_of": dj.get("as_of") or dj.get("generated_at"),
        "gate_run_dir": run_dir,
        "gate_run_dir_derivation": "取 `paired_gate_verdict.path` 的 parent（**不是 glob**）",
        "arm_mainline_status_path": str(arm_path),
        "arm_mainline_status_sha256_12": str(arm_sha),
        "arm_mainline_status_bytes": cal.get("bytes"),
        "gate_verdict_path": str(gv_path),
        "gate_verdict_sha256_12": str(gv_sha),
        "gate_verdict_bytes": gv.get("bytes"),
        "verdict_class1": gv.get("verdict_class1"),
        "verdict_top_level_declared": gv.get("verdict"),
        "broadcast_doc_path": _rel(dp),
        "broadcast_doc_sha256_12": doc_id["sha256_12"],
    }
    if not declaration["as_of"]:
        raise BroadcastParseError("broadcast_as_of_not_found",
                                  "JSON 广播件里既没有 `as_of` 也没有 `generated_at` ⇒ 声明缺 `as_of`")
    line_calibers: dict[str, Any] = {}
    for tag, src in (("arm_mainline_status", cal), ("gate_verdict", gv)):
        for c in N_LINES_CALIBERS:
            if src.get(c) is not None:
                declaration[f"{tag}_{c}"] = src[c]
                line_calibers[f"{tag}_{c}"] = src[c]
        if src.get("n_lines_caliber"):
            line_calibers[f"{tag}_n_lines_caliber_verbatim"] = src["n_lines_caliber"]
        if not any(declaration.get(f"{tag}_{c}") is not None for c in N_LINES_CALIBERS):
            declaration[f"{tag}_n_lines_caliber_unnamed"] = {
                "value": src.get("n_lines"), "why": "件里没有点名口径的行数 ⇒ 不比对（裁定 98.5-②）"}
    sdi = cal.get("source_data_identity") or {}
    npz_dec: dict[str, Any] = {"measurement_status": "not_measured",
                               "why": "件里没有 `source_data_identity`"}
    if sdi.get("checked_path") and sdi.get("checked_path_sha256_12"):
        npz_dec = {"measurement_status": "measured", "path": sdi["checked_path"],
                   "sha256_12_declared": sdi["checked_path_sha256_12"],
                   "stats_provenance_declared": sdi.get("stats_provenance"),
                   "n_frames_declared": sdi.get("n_frames"),
                   "n_episodes_declared": sdi.get("n_episodes")}
    return {"artifact": "c2_broadcast_parse", "source_kind": "json",
            "measurement_status": "measured",
            "as_of_parsed": datetime.now().astimezone().isoformat(timespec="seconds"),
            "doc_identity": doc_id, "as_of_declared": declaration["as_of"],
            "declaration": declaration,
            "line_calibers_declared": line_calibers,
            "stats_declaration": {"measurement_status": "not_measured",
                                  "why": ("JSON 广播件不声明 stats 档路径 ⇒ stats 身份只能来自 "
                                          "markdown 广播件的 §3（两件都给时由 crosscheck 合并）")},
            "npz_declaration": npz_dec,
            "consumer_obligation_verbatim": cal.get("consumer_obligation_A2_T_A2_7"),
            "parse_report": {"sections_seen": sorted(dj.keys()),
                             "discovery_method": "读 `bc_consumption_caliber` 的具名字段（无 glob、无推断）",
                             "no_globbing_by_construction": True,
                             "sha_not_trusted_here": "声明值只用于对账，实物 sha 一律由消费方复算"}}


def crosscheck_broadcast_sources(md: dict[str, Any] | None, js: dict[str, Any] | None) -> dict[str, Any]:
    """两件广播载体必须**互相相等**（不等 ⇒ 拒，不挑一份）。只给一件时如实写 `not_measured`。"""
    out: dict[str, Any] = {"sources_given": {"markdown": bool(md), "json": bool(js)}}
    if not (md and js):
        out.update({"measurement_status": "not_measured",
                    "why": "只给了一件载体 ⇒ 无从交叉核（读不到 ≠ 测到没有）"})
        return out
    a, b = md["declaration"], js["declaration"]
    fields = ("arm_mainline_status_path", "arm_mainline_status_sha256_12", "gate_verdict_path",
              "gate_verdict_sha256_12", "verdict_class1", "gate_run_dir")
    diffs = {f: {"markdown": a.get(f), "json": b.get(f)} for f in fields if a.get(f) != b.get(f)}
    npz_a, npz_b = md.get("npz_declaration") or {}, js.get("npz_declaration") or {}
    npz_diffs = {}
    if npz_a.get("measurement_status") == "measured" and npz_b.get("measurement_status") == "measured":
        for f in ("path", "sha256_12_declared"):
            if npz_a.get(f) != npz_b.get(f):
                npz_diffs[f] = {"markdown": npz_a.get(f), "json": npz_b.get(f)}
    out.update({"measurement_status": "measured", "fields_compared": list(fields),
                "declaration_diffs": diffs, "npz_diffs": npz_diffs,
                "agree": not diffs and not npz_diffs})
    return out


def consume_c2_broadcast(*, doc_path: Any = BROADCAST_DOC_DEFAULT,
                         json_path: Any = None,
                         g14: dict[str, Any] | None = None,
                         control_hz: float | None = MAINLINE_CONTROL_HZ,
                         consumer: str = "bc_step1",
                         start_authority: str = START_AUTHORITY_DEFAULT,
                         remaining_preconditions_before_card: str =
                         REMAINING_PRECONDITIONS_DEFAULT,
                         extra_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """**消费**（不是诊断）：吃 C2 的成对广播，产出 BC 入口的准入判定件。

    与 `probe_real` 的区别只有一处但很关键：这里的声明**来自 C2 点名的路径**（解析而来），
    不是 A2 自拼的试算件 ⇒ 其 `admitted` 可以作为 BC 入口的准入结论被引用。
    **但「准入」仍不等于「可以开跑」**：停点/预算/窗口申报是另外的门（见 `authorization_to_start_bc`）。
    """
    t0 = time.monotonic()
    load_before = _machine_load()
    dp = pathlib.Path(_rel(doc_path))
    out: dict[str, Any] = {
        "artifact": "bc_admission_consumption_decision",
        "module": "harness/bc_admission_gate.py",
        "module_representation_version": MODULE_REPRESENTATION_VERSION,
        "as_of": datetime.now().astimezone().isoformat(timespec="seconds"),
        "consumer": consumer,
        "declaration_source": {"kind": "c2_paired_broadcast", "doc_path": str(dp),
                               "discovery_method": "解析 C2 广播件里**点名**的路径（无 glob、无 latest-run 推断）"},
        "capability_claim": False, "policy_executed": False, "gpu_used": False,
        "success_rate_column": "not_an_exit_criterion",
    }
    extra_blocking: list[dict[str, str]] = []
    warnings_extra: list[dict[str, Any]] = []
    not_measured: list[str] = []

    jp = pathlib.Path(_rel(json_path)) if json_path else None
    out["declaration_source"]["json_path"] = str(jp) if jp else None
    parsed_md: dict[str, Any] | None = None
    parsed_js: dict[str, Any] | None = None
    parse_errors: list[dict[str, str]] = []
    for label, path_, fn in (("markdown", dp, parse_c2_broadcast), ("json", jp, parse_c2_broadcast_json)):
        if path_ is None:
            continue
        try:
            res = fn(path_)
            if label == "markdown":
                parsed_md = res
            else:
                parsed_js = res
        except BroadcastParseError as exc:
            parse_errors.append({"source": label, "reason_code": exc.reason_code,
                                 "detail": exc.detail, "path": str(path_)})
    # 两件都在 ⇒ 以 markdown 为底（它有 §3 的 stats 档），把 JSON 的口径名行数并进来，并交叉核
    parsed = parsed_md or parsed_js
    if parsed is None:
        parsed = {"artifact": "c2_broadcast_parse", "measurement_status": "not_measured",
                  "error": (parse_errors[0] if parse_errors else
                            {"reason_code": "broadcast_source_absent", "detail": "两件载体都没给"})}
        parse_errors = parse_errors or [{"source": "none", "reason_code": "broadcast_source_absent",
                                         "detail": "两件载体都没给"}]
    elif parsed_md and parsed_js:
        merged = dict(parsed_md["declaration"])
        for k, v in parsed_js["declaration"].items():
            if k in N_LINES_MERGE_KEYS or k.endswith(("_n_lines_wc", "_n_lines_splitlines")):
                merged.setdefault(k, v)
        if parsed_md.get("npz_declaration", {}).get("measurement_status") != "measured":
            parsed_md = dict(parsed_md)
            parsed_md["npz_declaration"] = parsed_js.get("npz_declaration")
        parsed = dict(parsed_md)
        parsed["declaration"] = merged
        parsed["merged_from"] = "markdown（含 §3 的 stats 档）+ json（D 在 §98.2-A 亲核的那份）"
    out["parse_errors"] = parse_errors
    for pe in parse_errors:
        extra_blocking.append({
            "reason_code": pe["reason_code"], "reason_verbatim": f"{pe['source']}：{pe['detail']}",
            "ruling": "裁定 96.1-④（成对广播）：解析不出唯一声明 ⇒ 拒，**不猜、不 glob**",
            "triage_class": "class1_control_and_data_correctness"})
    cross = crosscheck_broadcast_sources(parsed_md, parsed_js)
    out["broadcast_crosscheck"] = cross
    if cross.get("measurement_status") == "measured" and not cross.get("agree"):
        extra_blocking.append({
            "reason_code": "broadcast_sources_disagree",
            "reason_verbatim": (f"两件广播载体互不相等：{json.dumps(cross.get('declaration_diffs'), ensure_ascii=False)}"
                                f" / npz：{json.dumps(cross.get('npz_diffs'), ensure_ascii=False)}"
                                " ⇒ 不挑一份，两个都不采信"),
            "ruling": "裁定 96.1-④（成对广播必须唯一）+ 缺陷类 ⑲（挑一份 = 把分叉读成一致）",
            "triage_class": "class1_control_and_data_correctness"})
    out["parse"] = parsed
    if parsed.get("measurement_status") != "measured":
        out.update({"admitted": False, "decision": None, "extra_blocking": extra_blocking,
                    "warnings_extra": warnings_extra, "not_measured_items": ["broadcast"],
                    "authorization_to_start_bc": False,
                    "stop_order_in_force": False,
                    "stop_order_lifted_by": "裁定 98.6（`decisions_20260929.md` §98.6 / 日报 §D98.4）",
                    "start_authority": start_authority,
                    "remaining_preconditions_before_card": remaining_preconditions_before_card,
                    "interpretation_rule": INTERPRETATION_RULE,
                    "machine_load": load_before, "elapsed_s": round(time.monotonic() - t0, 3)})
        return out

    dec = dict(parsed["declaration"])
    g14 = dict(g14 or {})
    for k in G14_PRECONDITION_FIELDS:
        if g14.get(k) not in (None, ""):
            dec[k] = g14[k]
    out["g14_precondition"] = {
        "fields_supplied": {k: dec.get(k) for k in G14_PRECONDITION_FIELDS},
        "missing": [k for k in G14_PRECONDITION_FIELDS if dec.get(k) in (None, "")],
        "semantics_owner": "F（裁定 97.3-4 的 `checked_by=F`）；本闸只核证据件的**存在与 sha**，不判语义",
        "status_authority": "D（`decisions_20260929.md` §97.2 / §97.7 + checkpoint §10：`status=satisfied`）",
        "provenance_note": (g14.get("provenance_note")
                            or "调用方未附 provenance 说明 ⇒ G14 归属只按裁定值引用，A2 不代 F 表态"),
        "provenance_evidence": g14.get("provenance_evidence"),
    }

    stats_dec = parsed.get("stats_declaration") or {}
    npz_dec = parsed.get("npz_declaration") or {}
    run_dir = dec["gate_run_dir"]
    arm_p = REPO / _rel(dec["arm_mainline_status_path"])

    # ── 臂内件的 BC 输入面（同源 + 94.3 盲维）：只从实物读 ──
    arm_json: dict[str, Any] = {}
    arm_read: dict[str, Any] = {"measurement_status": "not_measured"}
    try:
        arm_json = json.loads(arm_p.read_text(errors="replace"))
        arm_read = {"measurement_status": "measured",
                    "checked_path": arm_json.get("checked_path"),
                    "checked_path_sha256_12": arm_json.get("checked_path_sha256_12"),
                    "stats_provenance": arm_json.get("stats_provenance"),
                    "n_episodes": arm_json.get("n_episodes"), "n_frames": arm_json.get("n_frames"),
                    "npz_manifest_sha256_12": arm_json.get("npz_manifest_sha256_12"),
                    "next_required_action_verbatim": arm_json.get("next_required_action")}
    except Exception as exc:                                          # noqa: BLE001
        arm_read = {"measurement_status": "not_measured", "why": f"{type(exc).__name__}: {exc}"}
        not_measured.append("arm_bc_inputs")
    out["arm_bc_inputs_from_artifact"] = arm_read

    # ── npz：广播件声明 vs 臂内件自述，必须**同一份**（裁定 85.4-3 同源硬闸）──
    npz_cross: dict[str, Any] = {"measurement_status": "not_measured"}
    npz_path = npz_dec.get("path")
    npz_sha = npz_dec.get("sha256_12_declared")
    if npz_dec.get("measurement_status") == "measured":
        if arm_read.get("measurement_status") == "measured":
            same_path = (arm_read.get("checked_path") == npz_path)
            same_sha = (str(arm_read.get("checked_path_sha256_12") or "").lower()
                        == str(npz_sha or "").lower())
            npz_cross = {"measurement_status": "measured", "broadcast_path": npz_path,
                         "arm_checked_path": arm_read.get("checked_path"), "path_matches": same_path,
                         "broadcast_sha256_12": npz_sha,
                         "arm_checked_path_sha256_12": arm_read.get("checked_path_sha256_12"),
                         "sha_matches": same_sha, "same_source_holds": bool(same_path and same_sha)}
            if not (same_path and same_sha):
                extra_blocking.append({
                    "reason_code": "npz_declaration_disagrees_with_arm",
                    "reason_verbatim": (f"广播件声明的 npz（{npz_path} / {npz_sha}）与臂内件自述的 "
                                        f"`checked_path`（{arm_read.get('checked_path')} / "
                                        f"{arm_read.get('checked_path_sha256_12')}）不是同一份 ⇒ "
                                        "同源无法判定，**两个都不采信**"),
                    "ruling": "裁定 85.4-3（同源硬闸：pilot 与 formal 的 stats 不得互替）",
                    "triage_class": "class1_control_and_data_correctness"})
        else:
            npz_cross = {"measurement_status": "not_measured",
                         "why": "臂内件读不到 ⇒ 无法交叉核（读不到 ≠ 测到没有）"}
            not_measured.append("npz_crosscheck")
    else:
        npz_cross = {"measurement_status": "not_measured",
                     "why": npz_dec.get("why") or "广播件里没有 §3 的源数据行"}
        not_measured.append("npz_declaration")
        extra_blocking.append({
            "reason_code": "npz_identity_not_in_broadcast",
            "reason_verbatim": f"广播件没有给出 npz 身份（{npz_cross['why']}）⇒ 数据身份 not_measured",
            "ruling": "裁定 86.0/86.1/90.4-4（权威读路径 = npz + `--s1-frames`）",
            "triage_class": "class1_control_and_data_correctness"})
    out["npz_crosscheck"] = npz_cross

    # ── stats：BC 真正要吃的那一档，身份必须**自己复算**对账 ──
    stats_out: dict[str, Any] = {"measurement_status": "not_measured"}
    if stats_dec.get("measurement_status") == "measured":
        sp = REPO / _rel(stats_dec["path"])
        sid = _stream_identity(sp)
        stats_out = {"declared": stats_dec, "recomputed": sid,
                     "inside_declared_run_dir": bool(stats_dec.get("inside_declared_run_dir"))}
        if sid.get("measurement_status") != "measured":
            extra_blocking.append({
                "reason_code": "stats_unreadable",
                "reason_verbatim": f"stats 档读不到（{sid.get('why')}）⇒ not_measured",
                "ruling": "红线 absence_of_measurement_is_not_measurement_of_absence",
                "triage_class": "class1_control_and_data_correctness"})
            not_measured.append("stats")
        else:
            if str(stats_dec["sha256_12_declared"]).lower() != sid["sha256_12"]:
                extra_blocking.append({
                    "reason_code": "stats_sha256_mismatch",
                    "reason_verbatim": (f"stats 档复算 sha256[:12]={sid['sha256_12']} ≠ 广播声明 "
                                        f"{stats_dec['sha256_12_declared']} ⇒ 拒绝"),
                    "ruling": "裁定 93.4 第 3 条（不一致 ⇒ LearnerRefused）+ 95.5（stats 一经开跑即冻结）",
                    "triage_class": "class1_control_and_data_correctness"})
            if not stats_dec.get("inside_declared_run_dir"):
                extra_blocking.append({
                    "reason_code": "stats_not_inside_declared_run_dir",
                    "reason_verbatim": (f"stats 档 `{stats_dec['path']}` 不在声明的 run 目录 "
                                        f"`{run_dir}` 内 ⇒ 与臂内件不是一轮"),
                    "ruling": "裁定 96.1-④（成对/同轮）",
                    "triage_class": "class1_control_and_data_correctness"})
            try:
                sj = json.loads(sp.read_text(errors="replace"))
                stats_out["from_artifact"] = {
                    "stats_provenance": sj.get("stats_provenance"),
                    "representation_version": sj.get("representation_version"),
                    "n_dims": sj.get("n_dims"),
                    "case": sj.get("case"), "family": sj.get("family"), "coef": sj.get("coef")}
                if sj.get("stats_provenance") != stats_dec.get("stats_provenance_declared"):
                    extra_blocking.append({
                        "reason_code": "stats_provenance_declaration_mismatch",
                        "reason_verbatim": (f"stats 档实物 `stats_provenance="
                                            f"{sj.get('stats_provenance')!r}` ≠ 广播声明 "
                                            f"{stats_dec.get('stats_provenance_declared')!r}"),
                        "ruling": "裁定 85.4-3 / 87.4（BC 只认 `formal40_bc_source`）",
                        "triage_class": "class1_control_and_data_correctness"})
                if sj.get("representation_version") != stats_dec.get("representation_version_declared"):
                    extra_blocking.append({
                        "reason_code": "stats_representation_version_mismatch",
                        "reason_verbatim": ("stats 档实物 `representation_version` 与广播声明不相等 ⇒ "
                                            "换 stats 等于换归一化口径（裁定 95.5 冻结面）"),
                        "ruling": "裁定 95.5（stats 与阈值一经第 1 步开跑即冻结）",
                        "triage_class": "class1_control_and_data_correctness"})
            except Exception as exc:                                  # noqa: BLE001
                stats_out["from_artifact"] = {"measurement_status": "not_measured",
                                             "why": f"{type(exc).__name__}: {exc}"}
                not_measured.append("stats_json")
    else:
        stats_out = {"measurement_status": "not_measured",
                     "why": stats_dec.get("why") or "广播件没有 §3"}
        not_measured.append("stats_declaration")
        extra_blocking.append({
            "reason_code": "stats_identity_not_in_broadcast",
            "reason_verbatim": f"广播件没有给出 stats 档身份（{stats_out['why']}）⇒ BC 输入身份未知",
            "ruling": "裁定 95.5 + 96.1-④",
            "triage_class": "class1_control_and_data_correctness"})
    out["bc_stats_input"] = stats_out

    decision = bc_admission_check(declaration=dec, raise_on_refusal=False,
                                  npz_path=npz_path, npz_sha256_12_declared=npz_sha,
                                  control_hz=control_hz, consumer=consumer)

    # ── Ⅱ/Ⅲ 类：只登记、不阻塞（裁定 95.2 三分类）──
    blind = ((arm_json or {}).get("heldout_per_dim_blindness_ruling_94_3") or {})
    blind_dims = blind.get("correctness_blind_dims_union")
    if blind.get("measurement_status") == "measured" and blind_dims is not None:
        caveat = {"measurement_status": "measured", "correctness_blind_dims_union": blind_dims,
                  "blind_dim_threshold": blind.get("blind_dim_threshold"),
                  "n_distinct_heldout_patterns": blind.get("n_distinct_heldout_patterns"),
                  "source": "臂内件 `heldout_per_dim_blindness_ruling_94_3`（实物读出，不是转抄散文）"}
    else:
        caveat = {"measurement_status": "not_measured",
                  "why": "臂内件里没有 94.3 的两个字段 ⇒ 盲维未知（不许写成「无盲维」）"}
        not_measured.append("correctness_blind_dims")
    out["caveats_must_be_reported_with_any_bc_result"] = caveat
    warnings_extra.append({
        "reason_code": "correctness_family_blind_on_some_dims",
        "reason_verbatim": (f"正确性族（held-out 口径）在 {blind_dims} 上 `not_measured` ⇒ "
                            "报 BC 结果时**不得**写成「归一化器已通过正确性验证」的全 14 维结论"),
        "ruling": "裁定 94.3 / 94.5 + 红线 absence_of_measurement_is_not_measurement_of_absence",
        "triage_class": "class2_experiment_interpretation_risk"})
    if arm_read.get("next_required_action_verbatim"):
        warnings_extra.append({
            "reason_code": "arm_next_required_action_prose_is_stale",
            "reason_verbatim": ("臂内件的 `next_required_action` 仍写着「闸侧重跑 ⇒ 0 红后本档 stats 才是 "
                                "S3 BC 的输入」，而该前置已由②满足 ⇒ 该字段散文**不是当前口径**"
                                "（C2 在自己的广播件 §5-2 里已声明不改生成物字段）"),
            "ruling": "裁定 97.3-5（闸侧冻结：不得再改判据形态）⇒ 只登记",
            "triage_class": "class3_documentation_integrity",
            "verbatim": arm_read["next_required_action_verbatim"]})
    if control_hz is not None:
        warnings_extra.append({
            "reason_code": "control_hz_is_caller_declaration",
            "reason_verbatim": (f"臂内件里没有 `control_hz` 字段 ⇒ 同频（{MAINLINE_CONTROL_HZ} Hz）"
                                "这一项是**调用方声明**、不是从实物读出；BC 运行时必须把实际用的 "
                                "`control_hz` 落进 run 产物，否则同频纪律只有声明没有证据"),
            "ruling": "`params:119` 同频纪律（S1/S3/S5/S6 必须同值 29.4118 Hz）",
            "triage_class": "class2_experiment_interpretation_risk"})

    admitted = bool(decision["admitted"]) and not extra_blocking
    out.update({
        "admitted": admitted,
        "decision": decision,
        "extra_blocking": extra_blocking,
        "warnings_extra": warnings_extra,
        "not_measured_items": sorted(set((decision.get("not_measured_items") or []) + not_measured)),
        "blocking_reason_codes": ([b["reason_code"] for b in decision["blocking_refusals"]]
                                  + [b["reason_code"] for b in extra_blocking]),
        "authorization_to_start_bc": False,
        "authorization_note": ("本件是**准入判定**，不是开跑授权；`False` 的含义是「这份 JSON 本身"
                               "不构成授权」，**不是**「停点仍有效」"),
        "stop_order_in_force": False,
        "stop_order_lifted_by": "裁定 98.6（`decisions_20260929.md` §98.6 / 日报 §D98.4：停点解除、第 1 步即刻可起跑）",
        "start_authority": start_authority,
        "remaining_preconditions_before_card": remaining_preconditions_before_card,
        "what_would_change_authorization": (
            "① 用户答三项（六步/双轨 · 预算上限 · git remote）· ② 按 94.9-1 的过渡协议申报 GPU 窗口"
            "（申报 + `GPU_WINDOW.json` + 起跑前拒绝逻辑，入口脚本名按 RR1(a) 写给 E）· "
            "③ 拒绝逻辑读 E 的参考实现 `card_busy()`（RR4：不读 B2 的副本）"),
        "interpretation_rule": INTERPRETATION_RULE,
        "extra_context": extra_context or {},
        "machine_load": load_before,
        "machine_load_after": _machine_load(),
        "elapsed_s": round(time.monotonic() - t0, 3),
    })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="T-A2-7 · BC 入口准入闸（裁定 93.4 / 96.1-④ / 97.3-3）")
    ap.add_argument("--selftest", action="store_true", help="两向变异体自检（裁定 93.8）")
    ap.add_argument("--probe-real", action="store_true", help="拿当前 C2 实物做**诊断**（不是消费决定）")
    ap.add_argument("--gate-run-dir", default=None, help="仅配合 --probe-real；不给 = 无声明 ⇒ 预期 refused")
    ap.add_argument("--trial-from-latest-run", action="store_true",
                    help="仅配合 --probe-real：用最新一轮闸跑**自拼**一份试算声明预验管路"
                         "（产物里带大字警示，**不是** C2 的广播、不得当准入结论）")
    ap.add_argument("--consume-c2-broadcast", nargs="?", const=BROADCAST_DOC_DEFAULT, default=None,
                    metavar="DOC",
                    help=f"**消费**（不是诊断）：吃 C2 的成对广播件（默认 `{BROADCAST_DOC_DEFAULT}`），"
                         "产出 BC 入口的准入判定件")
    ap.add_argument("--c2-broadcast-json", default=None, metavar="JSON",
                    help="C2 的**机器可读**成对广播件（`bc_consumption_caliber`）；与 markdown 件同时给 ⇒ 两件必须互相相等")
    ap.add_argument("--g14-evidence-path", default=None,
                    help="裁定 97.3-4 的一次性前置：`G14` 实测翻转的证据件（可是同轮 `gate_verdict.json`）")
    ap.add_argument("--g14-evidence-sha256-12", default=None, help="上面那件的 sha256[:12]（本闸会自己复算对账）")
    ap.add_argument("--g14-checked-by", default=None, help="谁判的语义（裁定值 = F）；本闸只引不判")
    ap.add_argument("--g14-checked-when", default=None, help="何时判的（裁定值 = A2 第 1 步开跑前）")
    ap.add_argument("--g14-provenance-json", default=None,
                    help="`G14` 归属的扫描证据件（变体扫描 + 两向自检）；只登记，不判语义")
    ap.add_argument("--control-hz", type=float, default=None,
                    help=f"调用方声明的控制频率（默认 {MAINLINE_CONTROL_HZ}，`params:119` 同频纪律）")
    ap.add_argument("--out-dir", default="runs/vla/a2_bc_admission_gate_20260930")
    args = ap.parse_args()
    if not (args.selftest or args.probe_real or args.consume_c2_broadcast):
        ap.print_help()
        print("\n[info] 本模块的**主要用法是被 BC 入口 import**：`from harness.bc_admission_gate "
              "import bc_admission_check, LearnerRefused`", file=sys.stderr)
        return 2
    out = REPO / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    rc = 0
    if args.selftest:
        st = selftest()
        p = out / f"selftest_{datetime.now():%Y%m%d_%H%M%S}.json"
        p.write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str))
        for k, v in st["rows"].items():
            print(f"  [{'PASS' if v['ok'] else 'FAIL'}] {k}  admitted={v.get('got_admitted')} "
                  f"codes={v.get('got_reason_codes')}")
        print(f"[selftest] {st['n_ok']}/{st['n_rows']} 条通过（两向：{st['two_way']['n_positive']} 正 / "
              f"{st['two_way']['n_negative']} 反）⇒ all_ok={st['all_ok']}")
        print(f"[written] {p}")
        rc = rc or (0 if st["all_ok"] else 3)
    if args.probe_real:
        pr = probe_real(gate_run_dir=args.gate_run_dir,
                        trial_from_latest_run=args.trial_from_latest_run)
        p = out / f"probe_real_{datetime.now():%Y%m%d_%H%M%S}.json"
        p.write_text(json.dumps(pr, ensure_ascii=False, indent=1, default=str))
        print(f"[probe-real] admitted={pr['admitted']} codes={pr['blocking_reason_codes']} "
              f"not_measured={pr['not_measured_items']}")
        for r in pr["runs"]:
            gv = r["gate_verdict_json"]
            print(f"           {r['run_dir']}: verdict={ (gv.get('scanned') or {}).get('verdict') } "
                  f"verdict_class1={ (gv.get('scanned') or {}).get('verdict_class1') } "
                  f"sha={gv.get('sha256_12')}")
        print(f"[written] {p}")
        print("[probe-real] **诊断件**：它的结论不得被引用成「BC 被禁 / 可跑」（见 interpretation_rule）")
        if pr.get("trial_declaration_used"):
            print("[probe-real] ⚠ 本轮用了**试算声明**（A2 自拼）⇒ 结论只证明管路通，"
                  "**不证明 BC 可开跑**（缺 C2 的成对广播 + F 的 G14 判定）")
    if args.consume_c2_broadcast:
        g14: dict[str, Any] = {}
        for k, v in (("g14_flip_evidence_path", args.g14_evidence_path),
                     ("g14_flip_evidence_sha256_12", args.g14_evidence_sha256_12),
                     ("g14_flip_checked_by", args.g14_checked_by),
                     ("g14_flip_checked_when", args.g14_checked_when)):
            if v:
                g14[k] = v
        if args.g14_provenance_json:
            gp = REPO / _rel(args.g14_provenance_json)
            try:
                gj = json.loads(gp.read_text(errors="replace"))
                g14["provenance_evidence"] = {"path": _rel(gp), "identity": _stream_identity(gp),
                                             "conclusion": gj.get("conclusion"),
                                             "f_independent_g14_verdict_artifact":
                                                 gj.get("f_independent_g14_verdict_artifact"),
                                             "variant_scan": gj.get("variant_scan"),
                                             "positive_control": gj.get("positive_control")}
                g14["provenance_note"] = gj.get("note_for_consumer")
            except Exception as exc:                                  # noqa: BLE001
                g14["provenance_evidence"] = {"path": _rel(gp), "measurement_status": "not_measured",
                                              "why": f"{type(exc).__name__}: {exc}"}
        art = consume_c2_broadcast(
            doc_path=args.consume_c2_broadcast, json_path=args.c2_broadcast_json,
            g14=(g14 or None),
            control_hz=(args.control_hz if args.control_hz is not None else MAINLINE_CONTROL_HZ),
            extra_context={"cli": {k: v for k, v in vars(args).items()
                                   if k in ("consume_c2_broadcast", "g14_evidence_path",
                                            "g14_evidence_sha256_12", "g14_checked_by",
                                            "g14_checked_when", "g14_provenance_json",
                                            "c2_broadcast_json",
                                            "control_hz", "out_dir")}})
        ts = f"{datetime.now():%Y%m%d_%H%M%S}"
        p2 = out / f"BC_ADMISSION_DECISION_{ts}.json"
        p2.write_text(json.dumps(art, ensure_ascii=False, indent=1, default=str))
        print(f"[consume] admitted={art['admitted']} "
              f"codes={art.get('blocking_reason_codes')} not_measured={art.get('not_measured_items')}")
        print(f"[consume] authorization_to_start_bc={art['authorization_to_start_bc']}"
              f"（本件不是开跑授权）· stop_order_in_force={art.get('stop_order_in_force')}"
              f"（裁定 98.6 已解除）")
        print(f"[consume] crosscheck={art.get('broadcast_crosscheck', {}).get('measurement_status')}"
              f" agree={art.get('broadcast_crosscheck', {}).get('agree')}")
        prs = (art.get("parse") or {})
        if prs.get("measurement_status") == "measured":
            d0 = prs["declaration"]
            print(f"[consume] 广播件={d0['broadcast_doc_path']} sha={d0['broadcast_doc_sha256_12']} "
                  f"as_of={d0['as_of']}")
            print(f"[consume] ①={d0['arm_mainline_status_path']} 声明 sha={d0['arm_mainline_status_sha256_12']}"
                  f" 复算={((art['decision'] or {}).get('checks', {}).get('arm_identity') or {}).get('sha256_12')}")
            print(f"[consume] ②={d0['gate_verdict_path']} 声明 sha={d0['gate_verdict_sha256_12']}"
                  f" 复算={((art['decision'] or {}).get('checks', {}).get('gate_verdict_identity') or {}).get('sha256_12')}"
                  f" verdict_class1(实物)={(art['decision'] or {}).get('checks', {}).get('verdict_class1_from_artifact')}")
            print(f"[consume] npz 同源={art['npz_crosscheck'].get('same_source_holds')} "
                  f"stats 复算={((art.get('bc_stats_input') or {}).get('recomputed') or {}).get('sha256_12')}")
            print(f"[consume] 盲维={art['caveats_must_be_reported_with_any_bc_result']}")
        print(f"[consume] loadavg={art['machine_load'].get('loadavg')} "
              f"nr_throttled={art['machine_load'].get('nr_throttled')} elapsed_s={art['elapsed_s']}")
        print(f"[written] {p2}")
        rc = rc or (0 if art["admitted"] else 3)
    return rc


if __name__ == "__main__":
    sys.exit(main())
