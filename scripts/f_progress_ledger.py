"""F 线的只读进度核算器：把「任务书说要做的」与「盘上实际有的」对成一张三值台账。

F 的定位（用户 2026-09-30 11:3x 指派）= 监管文件分析 + 执行进度核算，配合 D。
本件存在的理由是一个已被实证的缺陷类：**⑳ `preregistered_condition_without_a_consumer`**
（裁定 94.9-5）—— T-C2-7 的「再发生一次抢卡事故 ⇒ 立即升 P0」在 00:2x 触发后
**11 小时无人执行**，而且是外部分析而不是 D 自己发现的。预登记条件如果没有一个
**常设消费方**，它等于没写。本件就是那个消费方：每轮把所有 T-* 任务与所有预登记
触发条件重新对一遍盘，落机器可读台账，报 D 核。

三条自我约束（都是仓里已有纪律，不是 F 自创）：
  · **只读**：除自己的 run 目录外不写任何文件；不改他线代码；不 `git commit`（单写者 B2）；
    不写 `work/project_parameters.json`（D 单写者）；不用 `rm`。
  · **三值**（裁定 88.5-4 / `absence_of_measurement_three_state_rev15`）：
    `delivered` / `not_delivered` / **`not_measured`**（探测本身失败或作用域为空 ⇒ `null` + exit 4），
    **不许把「没测」写成「没有」**。
  · **限定前缀扫描**（裁定 94.9-2 `no_root_filesystem_scans`）：只扫本仓与 `/proc`，
    **禁止 `find /`**；所有扫描都带 `maxdepth` 与显式前缀。

判据来源纪律：每条 check 必须带 `authority`（裁定号或 `file:line`），且**判据是 D/任务书
已经写下的**，F 不新设判据、不定标、不改极性。发现判据本身有问题 ⇒ 只报 D，不自决
（C2 的 E4 处置就是这个形状，裁定 90.2 记功）。

退出码：0 = 台账已建成且自检两向通过；3 = 对照探针（93.8）任一方向失败；
4 = 存在 `not_measured`（探测作用域为空或异常）。`not_delivered` **不**影响退出码
（在制品是正常的，台账的作用是让"还欠什么"可见，不是拦人）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CITATION_ALGO = "sha256[:12]"

DELIVERED = "delivered"
NOT_DELIVERED = "not_delivered"
NOT_MEASURED = "not_measured"
# 裁定 72-2：**不适用的臂必须出 `N_A` + 理由，不许出红**。F 的判据里有条件式的
# （到期条件未触发），这类必须走 n_a，不能塞进 not_delivered（狼来了）也不能塞进
# not_measured（那是"探测失败"，语义不同）。
NOT_APPLICABLE = "not_applicable"

# 限定前缀（裁定 94.9-2）：只在这些前缀下扫，且一律带 maxdepth。
SCAN_PREFIXES = ("runs/vla", "runs/infra", "scripts", "harness", "docs", "registry", "work")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
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


def _identity(path: Path, why: str) -> dict[str, Any]:
    """裁定 92.3 的全仓最低 schema：两算法都给、三种行数口径都给、每条带 why/citable。"""
    # 相对路径一律按 ROOT 解析：第一版直接 `path.relative_to(ROOT)`，传相对路径就抛
    # ValueError（F 自己复用本函数生成文书身份表时撞到）。
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    text = _read(path)
    if text is None:
        return {"path": str(path.relative_to(ROOT)), "measurement_status": NOT_MEASURED,
                "why_it_matters": why,
                "citable": False, "as_of": _now()}
    raw = path.read_bytes()
    n_wc = raw.count(b"\n")                      # wc -l 口径（= 换行符个数）
    n_split = len(text.splitlines())
    return {
        "path": str(path.relative_to(ROOT)),
        "n_bytes": len(raw),
        "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
        "sha1_12": hashlib.sha1(raw).hexdigest()[:12],   # 只为让算法错配一眼可见
        "n_lines": n_wc,
        "n_lines_splitlines": n_split,
        "ends_with_newline": raw.endswith(b"\n"),
        "mtime": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(path.stat().st_mtime)),
        "citation_algo": CITATION_ALGO,
        "measurement_status": "measured",
        "why_it_matters": why,
        "citable": True,
        "as_of": _now(),
    }


def _grep_lines(rel: str, pattern: str) -> list[str]:
    """在单个文件里 grep -n，返回 `file:line` 命中（不扫根、不起子进程）。"""
    path = ROOT / rel
    text = _read(path)
    if text is None:
        return []
    rx = re.compile(pattern)
    return [f"{rel}:{i}" for i, line in enumerate(text.splitlines(), 1) if rx.search(line)]


def _glob_bounded(prefix: str, pattern: str, maxdepth: int = 3) -> list[Path]:
    base = ROOT / prefix
    if not base.is_dir():
        return []
    depth = pattern.count("/") + 1
    if depth > maxdepth:
        return []
    try:
        return sorted(base.glob(pattern))
    except OSError:
        return []


def _ps_pids() -> dict[int, str]:
    """只读 /proc，不起 `find`；返回 {pid: cmdline}。"""
    out: dict[int, str] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return out
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            raw = Path(f"/proc/{entry}/cmdline").read_bytes()
        except OSError:
            continue
        out[int(entry)] = " ".join(raw.replace(b"\0", b" ").decode(errors="ignore").split())[:300]
    return out


def _git_log(n: int = 12) -> str:
    try:
        proc = subprocess.run(["git", "log", f"--format=%h %ad %s", f"--date=format:%m-%d %H:%M",
                               f"-{n}"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        return proc.stdout if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ---------------------------------------------------------------------------
# 判据（每条都带 authority；F 不新设判据）
# ---------------------------------------------------------------------------
Check = Callable[[], dict[str, Any]]
CHECKS: list[tuple[str, str, str, Check]] = []


def check(task: str, question: str, authority: str):
    def deco(fn: Check) -> Check:
        CHECKS.append((task, question, authority, fn))
        return fn
    return deco


def _src_status(hits: list[str], rel: str) -> tuple[str, str]:
    if not (ROOT / rel).exists():
        return NOT_MEASURED, f"{rel} 不存在 ⇒ 无法判定（不是「没有」）"
    if hits:
        return DELIVERED, "命中 " + ", ".join(hits[:4]) + (f"（共 {len(hits)} 处）" if len(hits) > 4 else "")
    return NOT_DELIVERED, f"在 {rel} 扫过该模式未命中（as_of {_now()}）"


NC = "harness/norm_contract.py"
DEC_PATH = "work/decisions/decisions_20260929.md"
DAILY_PATH = "daily_report.md"


@check("T-C2-8-1", "`Tb_scale_floor_effective` 的 tooth 调用带 `blocking=False`（裁定 94.6-2：是**新增**实参，不是改）",
       "裁定 93.1 / 94.6-2；`decisions_20260929.md:3306` 附近")
def _c01() -> dict[str, Any]:
    text = _read(ROOT / NC) or ""
    lines = text.splitlines()
    anchor = [i for i, l in enumerate(lines, 1) if 'tooth("Tb_scale_floor_effective"' in l]
    if not anchor:
        return {"status": NOT_MEASURED, "evidence": f"{NC} 里找不到 Tb 的 tooth 调用"}
    start = anchor[0]
    window = lines[start - 1:start + 22]
    has_false = any(re.search(r"blocking\s*=\s*False", w) for w in window)
    return {"status": DELIVERED if has_false else NOT_DELIVERED,
            "evidence": f"Tb 的 tooth 调用当前在 {NC}:{start}；调用体内 `blocking=False` "
                        f"{'已存在' if has_false else '不存在'}",
            "anchor_now": f"{NC}:{start}",
            "anchor_in_ruling_94_6_2": f"{NC}:977",
            "anchor_drift": start != 977}


@check("T-C2-8-1", "`Tr3_near_constant_floor_material` 的 `blocking` 已改为 `False`", "裁定 93.1")
def _c02() -> dict[str, Any]:
    hits = _grep_lines(NC, r'tooth\("Tr3_near_constant_floor_material"')
    st, ev = _src_status(hits, NC)
    if st != DELIVERED:
        return {"status": st, "evidence": ev}
    text = (ROOT / NC).read_text(encoding="utf-8", errors="ignore").splitlines()
    start = int(hits[0].split(":")[1])
    window = text[start - 1:start + 22]
    ok = any(re.search(r"blocking\s*=\s*False", w) for w in window)
    return {"status": DELIVERED if ok else NOT_DELIVERED,
            "evidence": f"Tr3 在 {NC}:{start}；`blocking=False` {'已存在' if ok else '不存在'}"}


@check("T-C2-8-2", "新牙 `Tz_denom_strictly_positive` 已落码（绝对硬红）", "裁定 93.2 补丁①")
def _c03() -> dict[str, Any]:
    hits = _grep_lines(NC, r'tooth\("Tz_denom_strictly_positive"')
    st, ev = _src_status(hits, NC)
    return {"status": st, "evidence": ev}


@check("T-C2-8-2", "新牙 `Tres_per_dim_resolution_floor` 已落码（逐维、全量口径）", "裁定 93.2 补丁②")
def _c04() -> dict[str, Any]:
    hits = _grep_lines(NC, r'tooth\("Tres_per_dim_resolution_floor"')
    st, ev = _src_status(hits, NC)
    return {"status": st, "evidence": ev}


@check("T-C2-8-3", "四点单调性实测件在盘，且其 `overall.verdict` 的**实际取值**",
       "裁定 93.2 预登记检查点；94.0 触发一")
def _c05() -> dict[str, Any]:
    hits = _glob_bounded("runs/vla/c2_norm_contract_20260929", "probe_monotonicity_*/verdict.json", 3)
    if not hits:
        return {"status": NOT_MEASURED, "evidence": "作用域内未找到 probe_monotonicity_*/verdict.json（不判「没做」）"}
    path = hits[-1]
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": NOT_MEASURED, "evidence": f"{path.name} 解析失败：{type(exc).__name__}"}
    verdict = (data.get("overall") or {}).get("verdict")
    return {"status": DELIVERED if verdict is not None else NOT_MEASURED,
            "evidence": f"{path.relative_to(ROOT)} → overall.verdict = {verdict!r}",
            "identity": _identity(path, "93.2 口径的命门件；D 已据它裁 94.1")}


@check("T-C2-8-4", "`bc_admission()` 签名已带 gate_verdict / gate_run_dir / gate_verdict_sha256_12", "裁定 93.4 C2 侧")
def _c06() -> dict[str, Any]:
    hits = _grep_lines(NC, r"def bc_admission\(")
    if not (ROOT / NC).exists():
        return {"status": NOT_MEASURED, "evidence": f"{NC} 不存在"}
    text = (ROOT / NC).read_text(encoding="utf-8", errors="ignore").splitlines()
    if not hits:
        return {"status": NOT_MEASURED, "evidence": f"{NC} 里找不到 bc_admission 定义"}
    start = int(hits[0].split(":")[1])
    sig = " ".join(text[start - 1:start + 3])
    need = ["gate_verdict", "gate_run_dir", "gate_verdict_sha256_12"]
    missing = [n for n in need if n not in sig]
    return {"status": DELIVERED if not missing else NOT_DELIVERED,
            "evidence": f"bc_admission 在 {NC}:{start}；缺字段={missing or '无'}"}


@check("T-C2-8-4", "新牙 `Tbcad_admission_requires_green_gate` 已落码", "裁定 93.4")
def _c07() -> dict[str, Any]:
    st, ev = _src_status(_grep_lines(NC, r'tooth\("Tbcad_admission_requires_green_gate"'), NC)
    return {"status": st, "evidence": ev}


@check("T-C2-8-8", "裁定 94.3 的新牙 `Theldout_per_dim_blindness_is_registered` 已落码（P0，与 T-C2-8 同批）",
       "裁定 94.3")
def _c08() -> dict[str, Any]:
    st, ev = _src_status(_grep_lines(NC, r'Theldout_per_dim_blindness_is_registered'), NC)
    return {"status": st, "evidence": ev}


@check("T-C2-8-6", "裁定 93 落盘（10:36）之后有没有**新的全量闸跑**，其 verdict 为何", "裁定 93.1/93.2 要求重跑全量闸")
def _c09() -> dict[str, Any]:
    runs = _glob_bounded("runs/vla/c2_norm_contract_20260929/gate", "run_*/gate_verdict.json", 3)
    cutoff = 1751250960  # 2026-09-30 10:36 附近（裁定 93 落 params rev18 的时刻）
    fresh = [p for p in runs if p.stat().st_mtime >= cutoff]
    if not runs:
        return {"status": NOT_MEASURED, "evidence": "作用域内没有任何 gate run（不判「没跑」）"}
    if not fresh:
        newest = max(runs, key=lambda p: p.stat().st_mtime)
        return {"status": NOT_DELIVERED,
                "evidence": f"最新一跑是 {newest.parent.name}（mtime "
                            f"{time.strftime('%H:%M:%S', time.localtime(newest.stat().st_mtime))}），"
                            f"早于裁定 93 落盘 ⇒ 93 之后尚未重跑"}
    newest = max(fresh, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(newest.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": NOT_MEASURED, "evidence": f"{newest} 解析失败：{type(exc).__name__}"}
    return {"status": DELIVERED,
            "evidence": f"93 之后已有 {len(fresh)} 跑；最新 = {newest.parent.name} → verdict="
                        f"{data.get('verdict')!r} n_checks={data.get('n_checks')} "
                        f"n_red={data.get('n_red')} n_warn={data.get('n_warn')}",
            "identity": _identity(newest, "93.1/93.2 落地后的权威闸跑")}


@check("T-A2-6-①", "`harness/prompt_bin_guard.py` 在盘且自带 93.8 的 `pattern_coverage_probe`",
       "裁定 93.8；D §94.10 对 A2 写入面的认可")
def _c10() -> dict[str, Any]:
    rel = "harness/prompt_bin_guard.py"
    if not (ROOT / rel).exists():
        return {"status": NOT_DELIVERED, "evidence": f"在 {rel} 扫过未命中（as_of {_now()}）"}
    hits = _grep_lines(rel, r"pattern_coverage_probe")
    return {"status": DELIVERED if hits else NOT_DELIVERED,
            "evidence": f"{rel} 在盘；`pattern_coverage_probe` 命中 {len(hits)} 处"
                        + ("" if hits else " ⇒ 93.8 要求缺，按 `not_measured` 登记、不得报绿"),
            "identity": _identity(ROOT / rel, "S4b 的运行时 -1 prompt 牙（与 C2 的离线牙互补）")}


@check("T-A2-6 / 94.9-1③", "**若 S4b 已上卡**，是否留下过渡协议要求的 `GPU_WINDOW.json`（起跑那一刻的三网原文）",
       "裁定 94.9-1 过渡协议 ③（缺 ③ 或 ④ ⇒ D 不认该窗口的延迟/吞吐数字）")
def _c11() -> dict[str, Any]:
    # 判据必须是**条件式**的：协议件只在"真的上了卡"时才到期。第一版无条件判
    # `not_delivered`，而 A2 当时的 5 轮 dbg 全是 osmesa/CPU 臂（`renderer_class=None`、
    # `measurement_kind=not_measured_no_gl_context`）⇒ 那会是一次"狼来了"
    # （B2 的 RR-B2-18 同族）。F 自报并根因修：先取上卡证据，证据不足 ⇒ `not_measured`。
    hits: list[Path] = []
    for prefix in ("runs/vla", "runs/infra"):
        hits += _glob_bounded(prefix, "*/*/GPU_WINDOW.json", 3)
        hits += _glob_bounded(prefix, "*/GPU_WINDOW.json", 3)
    if hits:
        return {"status": DELIVERED,
                "evidence": "命中 " + ", ".join(str(p.relative_to(ROOT)) for p in hits[:3])}
    s4b = _glob_bounded("runs/vla", "a2_s4b*", 1)
    if not s4b:
        return {"status": NOT_MEASURED, "evidence": "作用域内无 a2_s4b* run 目录 ⇒ 到期条件未触发"}
    verifs = sorted((d / "s4b_verification.json" for d in s4b if (d / "s4b_verification.json").exists()),
                    key=lambda p: p.stat().st_mtime)
    if not verifs:
        return {"status": NOT_MEASURED,
                "evidence": f"S4b run 目录 {len(s4b)} 个，但无 s4b_verification.json ⇒ 上卡与否不可测"}
    newest = verifs[-1]
    try:
        data = json.loads(newest.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": NOT_MEASURED, "evidence": f"{newest.name} 解析失败：{type(exc).__name__}"}
    # **`gpu_used` 是权威字段，存在即决定性**。第二版曾用全 JSON 文本匹配
    # `nvidia_gpu`/`egl`，结果命中的是 A2 闸里的 **check 名**（`classify_nvidia_gpu`），
    # 不是实测值 ⇒ 假阳性（与 B2 的 RR-B2-18、E 的 cmdline 网同族：匹配"关于它的文本"）。
    gpu_flag = data.get("gpu_used")
    measured_classes: list[Any] = []

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            # 只认**同时带 renderer_class 与 measurement_kind 的实测记录**，不认 check 名
            if "renderer_class" in node and "measurement_kind" in node:
                measured_classes.append(node.get("renderer_class"))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(data)
    on_card: bool | None
    if gpu_flag is not None:
        on_card = bool(gpu_flag)
        basis = f"`gpu_used={gpu_flag}`（权威字段，决定性）"
    elif measured_classes:
        on_card = any(c == "nvidia_gpu" for c in measured_classes)
        basis = f"实测 renderer_class 记录 {len(measured_classes)} 条 = {measured_classes[:4]}"
    else:
        on_card = None
        basis = "`gpu_used` 缺且无 renderer_class 实测记录 ⇒ 上卡与否不可测"
    stamp_new = time.strftime("%H:%M:%S", time.localtime(newest.stat().st_mtime))
    if on_card is None:
        return {"status": NOT_MEASURED, "evidence": f"{newest.parent.name}（mtime {stamp_new}）：{basis}",
                "run_dirs": [p.name for p in s4b]}
    if not on_card:
        return {"status": NOT_APPLICABLE,
                "evidence": f"最新 S4b 产物 {newest.parent.name}（mtime {stamp_new}）{basis} "
                            f"⇒ 本轮未上卡，`GPU_WINDOW.json` 的到期条件未触发（裁定 72-2：不适用不出红）",
                "run_dirs": [p.name for p in s4b],
                "note": "到期条件 = 出现一次真上卡的 S4b 跑；届时本条自动转 not_delivered/delivered。"
                        "顺带登记：osmesa 臂不会产生 `renderer_class=nvidia_gpu` ⇒ **E 的 T-E-10"
                        "（C4 复验搭 A2 便车）在这些跑里拿不到第三方证据**，需等 A2 的 EGL 臂。"}
    return {"status": NOT_DELIVERED,
            "evidence": f"已上卡（{basis}）但限定前缀内未见 GPU_WINDOW.json ⇒ 裁定 94.9-1③ 缺件，"
                        f"D 明示「缺 ③ 或 ④ ⇒ 不认该窗口的延迟/吞吐数字」"}


@check("T-B2-17", "两次代提交（commit-1 = C2 四件 / commit-2 = 裁定 93 全套）已入库",
       "裁定 94.9-1 的 B2 顺序；`daily_report.md` §B2-17")
def _c13() -> dict[str, Any]:
    log = _git_log(20)
    if not log:
        return {"status": NOT_MEASURED, "evidence": "git log 取不到（不判「没提交」）"}
    want = {"97c8e63": "commit-1（C2 四件）", "d194269": "commit-2（裁定 93 全套）"}
    found = {k: v for k, v in want.items() if k in log}
    return {"status": DELIVERED if len(found) == len(want) else NOT_DELIVERED,
            "evidence": f"命中 {len(found)}/{len(want)}：" + (", ".join(f"{k}={v}" for k, v in found.items()) or "无")}


@check("T-B2-20", "`registry/verdict_identity.py` 的 `GATE_MODULE_PATH` 已由单值改为按 `gate_id` 索引的映射",
       "裁定 94.9-1（B2 顺序第 2）；D：这是 A2 做 sha 对账的地基")
def _c14() -> dict[str, Any]:
    rel = "registry/verdict_identity.py"
    hits = _grep_lines(rel, r"^GATE_MODULE_PATH\s*=")
    multi = _grep_lines(rel, r"GATE_MODULES|GATE_MODULE_PATHS|gate_id")
    if not (ROOT / rel).exists():
        return {"status": NOT_MEASURED, "evidence": f"{rel} 不存在"}
    if hits and not multi:
        return {"status": NOT_DELIVERED,
                "evidence": f"{hits[0]} 仍是单值路径，且全文件未见 gate_id 索引 ⇒ A2 的 T-A2-7 无处对账"}
    return {"status": DELIVERED if multi else NOT_MEASURED,
            "evidence": f"gate_id 索引命中 {len(multi)} 处：" + ", ".join(multi[:3])}


@check("T-B2-21", "GPU 窗口登记处（`scripts/gpu_window_ledger.py` + `runs/infra/gpu_window_ledger.jsonl`）",
       "裁定 94.9-1（T-C2-7 升 P0.5、归属改判 B2）")
def _c15() -> dict[str, Any]:
    script = ROOT / "scripts" / "gpu_window_ledger.py"
    ledger = ROOT / "runs" / "infra" / "gpu_window_ledger.jsonl"
    return {"status": DELIVERED if script.exists() else NOT_DELIVERED,
            "evidence": f"scripts/gpu_window_ledger.py {'在盘' if script.exists() else '不在盘'}；"
                        f"runs/infra/gpu_window_ledger.jsonl {'在盘' if ledger.exists() else '不在盘'}"
                        f"（过渡协议已即刻生效，本项是其机器化根治）"}


@check("T-B2-18 / 94.9-2", "遗留 `find /` PID 39153/39199 是否已终止并登记", "裁定 94.9-2 处置条")
def _c16() -> dict[str, Any]:
    pids = _ps_pids()
    alive = [p for p in (39153, 39199) if p in pids]
    roots = [p for p, cl in pids.items() if cl.startswith("find /")]
    if not pids:
        return {"status": NOT_MEASURED, "evidence": "/proc 读不到 ⇒ 无法判定"}
    return {"status": NOT_DELIVERED if alive else DELIVERED,
            "evidence": f"PID 39153/39199 存活={alive or '无'}；当前全机 `find /` 进程={sorted(roots)}",
            "note": "裁定 94.9-2 明令禁止 `find /`（吃 12 核配额 + 让 `contaminated_by_cotenant` 永久为真）"}


@check("T-E-11", "`RESTART_READINESS.json` 是否已产出（重启续跑就绪清单）", "裁定 94.10 第 4 项 / T-E-11")
def _c17() -> dict[str, Any]:
    hits = _glob_bounded("runs/infra", "e_restart_readiness_*/RESTART_READINESS.json", 3)
    if not hits:
        partial = _glob_bounded("runs/infra", "e_restart_readiness_*/*", 2)
        return {"status": NOT_DELIVERED if partial else NOT_MEASURED,
                "evidence": (f"RESTART_READINESS.json 未见，但该 run 目录已有 {len(partial)} 件在制品"
                             if partial else "作用域内无 e_restart_readiness_* 目录")}
    return {"status": DELIVERED, "evidence": str(hits[-1].relative_to(ROOT)),
            "identity": _identity(hits[-1], "服务器可能关闭 ⇒ 这是重启后唯一的续跑依据")}


@check("T-E-12", "`EVIDENCE_SNAPSHOT.json` 是否已产出（最小证据快照，≤200 MiB/件、≤4 GiB 总读）",
       "裁定 94.9-6")
def _c18() -> dict[str, Any]:
    hits = _glob_bounded("runs/infra", "e_evidence_snapshot_*/EVIDENCE_SNAPSHOT.json", 3)
    return {"status": DELIVERED if hits else NOT_DELIVERED,
            "evidence": (str(hits[-1].relative_to(ROOT)) if hits
                         else "在 runs/infra/e_evidence_snapshot_*/ 扫过未命中（as_of " + _now() + "）")}


@check("T-A2-8", "BC 结果口径的**预登记件** `CRITERIA_PREREGISTERED.json` 是否在 BC 开跑前落盘",
       "裁定 94.10 第 2 项：跑完再定判据 = 无效判据")
def _c19() -> dict[str, Any]:
    hits = _glob_bounded("runs/vla", "a2_s3_bc*/CRITERIA_PREREGISTERED.json", 3)
    bc_runs = _glob_bounded("runs/vla", "a2_s3_bc*", 1)
    if hits:
        return {"status": DELIVERED, "evidence": str(hits[-1].relative_to(ROOT))}
    if bc_runs:
        return {"status": NOT_DELIVERED,
                "evidence": f"BC run 目录已存在（{[p.name for p in bc_runs]}）但预登记件未见 ⇒ **顺序违规风险**"}
    return {"status": NOT_DELIVERED, "evidence": "BC 尚未开跑（无 a2_s3_bc* 目录）⇒ 预登记件仍未落盘，尚不构成顺序违规"}


@check("裁定 94.6-2 的行号锚", "裁定文本引用的 `harness/norm_contract.py:977`（Tb）是否仍指向 Tb",
       "DR-014 决定 13/14（跨线行号锚耦合）；C2 既有修法 = 绝对行号 → 名字锚点")
def _c22() -> dict[str, Any]:
    text = _read(ROOT / NC)
    if text is None:
        return {"status": NOT_MEASURED, "evidence": f"{NC} 读不到"}
    lines = text.splitlines()
    if len(lines) < 977:
        return {"status": NOT_MEASURED, "evidence": f"{NC} 只有 {len(lines)} 行，:977 越界"}
    at_977 = lines[976]
    now = [i for i, l in enumerate(lines, 1) if 'tooth("Tb_scale_floor_effective"' in l]
    drifted = bool(now) and now[0] != 977
    return {"status": NOT_DELIVERED if drifted else DELIVERED,
            "evidence": f":977 现在的内容 = {at_977.strip()[:70]!r}；Tb 的实际锚点 = "
                        f"{(NC + ':' + str(now[0])) if now else '未找到'} ⇒ 漂移={drifted}",
            "note": "判据是「裁定文本里的行号锚是否仍可核」，不是「谁错了」。修法建议见 F 的交接件。"}


@check("裁定 94.9-5 全线自查", "预登记条件是否都补了 `checked_by` / `checked_when`（缺陷类 ⑳ 的消费方）",
       "裁定 94.9-5")
def _c20() -> dict[str, Any]:
    path = ROOT / "work" / "project_parameters.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": NOT_MEASURED, "evidence": f"参数表解析失败：{type(exc).__name__}"}
    trig = json.dumps(data, ensure_ascii=False)
    n_trig = len(re.findall(r"可推翻条件|trigger_to_promote|falsifiable", trig))
    n_consumer = len(re.findall(r"checked_by", trig))
    n_when = len(re.findall(r"checked_when", trig))
    return {"status": DELIVERED if n_consumer > 0 else NOT_DELIVERED,
            "evidence": f"参数表里触发/可推翻条件相关键 {n_trig} 处；`checked_by` {n_consumer} 处、"
                        f"`checked_when` {n_when} 处 ⇒ 覆盖率 = "
                        + (f"{n_consumer}/{n_trig}" if n_trig else "null（空集，按三值记 not_measured）"),
            "note": "F 只数覆盖率、不判 D 侧是否该更多；逐条清单在 TRIGGER_REGISTRY.json"}


@check("环境上下文", "GPU 三网 + `loadavg` 三点 + `nr_throttled`（cgroup v1）—— 台账的口径伴随值",
       "裁定 46.4（数字必须成对给口径）；裁定 94.9-1②")
def _c21() -> dict[str, Any]:
    def q(args: list[str]) -> str:
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=20)
            return proc.stdout.strip() if proc.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    util = q(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader"])
    apps = q(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader"])
    try:
        loadavg = open("/proc/loadavg").read().split()[:3]
    except OSError:
        loadavg = []
    throttled = None
    for p in ("/sys/fs/cgroup/cpu/cpu.stat", "/sys/fs/cgroup/cpu.stat"):
        text = _read(Path(p))
        if text and "nr_throttled" in text:
            throttled = dict(re.findall(r"(nr_throttled|nr_periods)\s+(\d+)", text))
            throttled["path"] = p
            break
    if not util:
        return {"status": NOT_MEASURED, "evidence": "nvidia-smi 取不到 ⇒ 三网不可测（不判「卡空」）"}
    return {"status": DELIVERED,
            "evidence": f"GPU={util}；compute-apps={len([a for a in apps.splitlines() if a.strip()])} 行；"
                        f"loadavg={loadavg}；nr_throttled={throttled}",
            "note": "本条不判任何线的功过，只为台账里其它读数提供口径伴随值"}


# ---------------------------------------------------------------------------
# 预登记条件台账（缺陷类 ⑳ 的常设消费方）
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 裁定 95.3 的六步序列（**权威、不许重排**）+ D 补的第 0 步（第 1–3 步的共同前置）
# 依据：D→F 交接件 `rl_harness_supervision/d_handoff_to_f_20260930.md` §五-1
#   「进度台账重跑：判据换成六步序列，不再按旧关键路径（S4b → S3 BC）；
#     旧判据不作废、标 `superseded_by_ruling_95`」
# F 的边界（裁定 96）：只核算、不定标、不改极性。下列 `due_when` 全部抄 D 的原文，F 不新设。
# ---------------------------------------------------------------------------
SIX_STEPS: list[dict[str, str]] = [
    {"step": "S0", "owner": "A2", "due_when": "第 1 步开跑前",
     "name": "标准同步执行通路能在仿真里跑起来（第 1–3 步的共同前置；本轮唯一必须新增的运行时能力）",
     "authority": "裁定 95.3 的 D 补（Ⅰ 类）"},
    {"step": "S1", "owner": "A2", "due_when": "S0 通 ∧ C2 的成对广播 ∧ E 的 96.1-③ 修完（都不需要用户裁定）",
     "name": "小量示范过拟合 + 动作/夹爪/时间对齐检查 + 从示范初态闭环执行",
     "authority": "裁定 95.3 第 1 步（回答「数据能否被当前模型学到」）"},
    {"step": "S2", "owner": "A2", "due_when": "S1 出结果后",
     "name": "标准同步执行下的正式 BC/SFT；≥3 种子；正反向分别评估",
     "authority": "裁定 95.3 第 2 步（≥3 种子是开发阶段最低要求、不是统计充分性声明；每种子单独报数）"},
    {"step": "S3", "owner": "A2", "due_when": "S2 有 ≥3 种子结果后",
     "name": "同 ckpt、同初态配对比较：标准执行 vs 现有 Harness 调度",
     "authority": "裁定 95.3 第 3 步（回答「Harness 是否损害基础策略」）"},
    {"step": "S4", "owner": "A2 + C2", "due_when": "S3 出结论后",
     "name": "加入受限脚本恢复，分开统计自主成功与救场成功",
     "authority": "裁定 95.3 第 4 步"},
    {"step": "S5", "owner": "A2 + C2", "due_when": "S4 出结论后",
     "name": "用纠正数据更新策略，关闭恢复重测",
     "authority": "裁定 95.3 第 5 步"},
    {"step": "S6", "owner": "A2", "due_when": "S5 出结论后",
     "name": "同预算动态 BC vs BC + RL",
     "authority": "裁定 95.3 第 6 步"},
]

# 旧判据 → 六步的归属（**F 草案，待 D 里程碑审查**；映射错由 D 纠正，F 不定标）
SIX_STEP_MAP: dict[str, str] = {
    "T-C2-8-1": "S1 前置（stats/闸的判据极性）",
    "T-C2-8-2": "S1 前置（新硬红 Tz / Tres）",
    "T-C2-8-3": "S1 前置（单调性实测件）",
    "T-C2-8-4": "S1 前置（bc_admission 的 AND 闸）",
    "T-C2-8-6": "S1 前置（全量闸跑）",
    "T-C2-8-8": "S1 前置（94.3 的牙；已按 95.2 推迟到 S5 前）",
    "T-A2-6-①": "S1（运行时 -1 的 prompt 牙）",
    "T-A2-6 / 94.9-1③": "S1–S6 的上卡窗口纪律（任何一次真上卡都适用）",
    "T-A2-8": "S2（BC 结果口径的预登记件）",
    "T-B2-20": "S1 前置（A2 的对账入口 gate_id 映射）",
    "T-E-11": "S1–S6 的保险（重启续跑就绪）",
}

# 按裁定 95.2 被拿出关键路径 / 冻结的旧判据：**不作废，只打标 + 写理由**
SUPERSEDED_BY_RULING_95: dict[str, str] = {
    "T-B2-21": "裁定 95.2：T-B2-21 脚本冻结（过渡协议保留，它是 Ⅰ 类且成本比脚本低）",
    "T-C2-8-8": "裁定 95.2：94.3 的 Theldout_per_dim_blindness 从 T-C2-8 的 P0 批次拿出，牙与双向变异体推迟到 S5 前，BC 不等它",
}

GATE_ROOT = "runs/vla/c2_norm_contract_20260929/gate"
C2_TOPLEVEL_STATUS = "runs/vla/c2_norm_contract_20260929/mainline_status.json"
E_FIX_VERDICT = "runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json"
F_DIFF_RECHECK = "runs/vla/f_oversight_20260930/f_differential_recheck_card_busy_20260930.json"


def _fast_verdict(path: Path) -> dict[str, Any]:
    """只读前 8 KiB 取 `verdict` / `generated_at`。

    为什么不全量 load：闸判词件已达 **94,852,438 B / 1,896,737 ln**（as_of 13:04:45 的那一次），
    逐个 run 全量 json.load 会把只读台账变成分钟级作业。取不到 ⇒ `not_measured`，不猜。
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(8192).decode("utf-8", "ignore")
    except OSError as exc:
        return {"measurement_status": NOT_MEASURED, "reason": f"{type(exc).__name__}: {exc}",
                "method": "只读前 8 KiB 正则取键（不全量 load）"}
    mv = re.search(r'"verdict"\s*:\s*"([A-Za-z_]+)"', head)
    mg = re.search(r'"generated_at"\s*:\s*"([^"]+)"', head)
    return {"measurement_status": "measured" if mv else NOT_MEASURED,
            "verdict": mv.group(1) if mv else None,
            "generated_at": mg.group(1) if mg else None,
            "method": "只读前 8 KiB 正则取键（不全量 load）"}


def _latest_gate_runs(n: int = 8) -> list[Path]:
    root = ROOT / GATE_ROOT
    if not root.is_dir():
        return []
    runs = [p for p in root.glob("run_*") if p.is_dir()]
    return sorted(runs, key=lambda p: p.name, reverse=True)[:n]


@check("六步-S0", "标准同步执行通路（第 1–3 步的共同前置）是否已能跑起来并留下产物",
       "裁定 95.3 的 D 补（Ⅰ 类）；D→F 交接件 §五-1")
def _s0() -> dict[str, Any]:
    script = ROOT / "scripts" / "a2_standard_sync_exec_verify.py"
    out: dict[str, Any] = {"six_step": "S0"}
    if not script.exists():
        return {**out, "status": NOT_MEASURED,
                "evidence": "scripts/a2_standard_sync_exec_verify.py 不在盘 ⇒ 通路无从判定（不是「没跑通」）"}
    dirs = sorted((ROOT / "runs" / "vla").glob("a2_standard_sync_exec_*"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    products: list[Path] = []
    for d in dirs[:8]:
        products += list(d.glob("*.json"))
    products.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out["identity"] = _identity(script, "S0 的核验脚本（A2 的写入面，F 只读）")
    out["n_run_dirs"] = len(dirs)
    out["run_dirs_newest_first"] = [d.name for d in dirs[:5]]
    if not products:
        return {**out, "status": NOT_DELIVERED,
                "evidence": f"核验脚本在盘、run 目录 {len(dirs)} 个，但无 json 产物 ⇒ 通路尚未跑出可读结果"
                            f"（as_of {_now()}）"}
    newest = products[0]
    txt = _read(newest) or ""
    verdict_seen = re.findall(r'"(?:verdict|ok|status)"\s*:\s*("?[\w.]+"?)', txt)[:4]
    return {**out, "status": DELIVERED,
            "evidence": f"最新产物 {newest.relative_to(ROOT)}（mtime "
                        f"{time.strftime('%H:%M:%S', time.localtime(newest.stat().st_mtime))}）在盘；"
                        f"其中出现的判词字段（F 只抄不判）= {verdict_seen}",
            "product_identity": _identity(newest, "S0 的最新产物；F 只登记在盘与身份，不判其对错")}


@check("六步-S1", "第 1 步的开工前置是否齐备（F④ 的 BC 消费口径可对账 ∧ C2 的成对广播 ∧ 顶层件不分叉）",
       "裁定 95.3 第 1 步；裁定 96.1-④（BC 消费口径 = 最新一次 PASS 闸跑的臂内件）；§D96.9")
def _s1() -> dict[str, Any]:
    out: dict[str, Any] = {"six_step": "S1"}
    runs = _latest_gate_runs(8)
    if not runs:
        return {**out, "status": NOT_MEASURED,
                "evidence": f"{GATE_ROOT} 下没有 run_* ⇒ 无从判定（扫描作用域 = 该前缀，未做 find /）"}
    scanned, latest_pass = [], None
    for r in runs:
        gv = r / "gate_verdict.json"
        if not gv.exists():
            scanned.append({"run": r.name, "gate_verdict": NOT_MEASURED})
            continue
        fast = _fast_verdict(gv)
        scanned.append({"run": r.name, **fast})
        if latest_pass is None and fast.get("verdict") == "PASS":
            latest_pass = (r, gv, fast)
    out["scanned_runs_newest_first"] = scanned
    if latest_pass is None:
        return {**out, "status": NOT_MEASURED,
                "evidence": f"最近 {len(scanned)} 次闸跑里没有 PASS ⇒ 最新 PASS 不在扫描窗口内（不猜更早的）"}
    r, gv, fast = latest_pass
    arm = r / "arm_mainline" / "mainline_status.json"
    top = ROOT / C2_TOPLEVEL_STATUS
    if not arm.exists():
        return {**out, "status": NOT_MEASURED,
                "evidence": f"最新 PASS = {r.name}（generated_at {fast.get('generated_at')}），"
                            f"但其 arm_mainline/mainline_status.json 不在盘 ⇒ F④ 的消费件无从定位"}
    arm_id = _identity(arm, "F④ 口径下当前的 BC 消费件（最新一次 PASS 闸跑的臂内件）")
    out["bc_consumption_target"] = arm_id
    out["latest_pass_gate_verdict"] = {"run": r.name, "n_bytes": gv.stat().st_size, **fast}
    # ① 顶层件是否与臂内件一致，或显式标 superseded_by（裁定 96.1-④ 的 Ⅰ 类判据，D 定的，F 只测）
    if top.exists():
        top_id = _identity(top, "顶层便利副本；按 96.1-④ 必须与臂内件字节一致或显式 superseded_by")
        top_txt = _read(top) or ""
        marked = "superseded_by" in top_txt
        same = top_id.get("sha256_12") == arm_id.get("sha256_12")
        out["toplevel_copy"] = {"identity": top_id, "byte_identical_to_arm": same,
                                "has_superseded_by": marked,
                                "class1_red_candidate": (not same and not marked)}
    else:
        out["toplevel_copy"] = {"measurement_status": NOT_MEASURED, "reason": f"{C2_TOPLEVEL_STATUS} 不在盘"}
    # ② C2 的成对广播：臂内件与同轮 gate_verdict 两条身份是否**成对**出现在 C2 的写入面
    arm_sha = str(arm_id.get("sha256_12") or "")
    pair_hits: list[str] = []
    dr = _read(ROOT / "daily_report.md") or ""
    cur, in_c2 = "(preamble)", False
    for line in dr.splitlines():
        if line.startswith("## "):
            cur, in_c2 = line[3:60], line.startswith("## §C2")
        if in_c2 and arm_sha and arm_sha in line:
            pair_hits.append(f"daily_report.md §{cur[:24]}")
    for doc in sorted((ROOT / "docs").glob("c2_*.md")):
        if arm_sha and arm_sha in (_read(doc) or ""):
            pair_hits.append(str(doc.relative_to(ROOT)))
    out["c2_paired_broadcast"] = {
        "found": bool(pair_hits), "where": pair_hits[:6],
        "scan_scope": ["daily_report.md 的 ## §C2 段", "docs/c2_*.md"],
        "required_form": "臂内件与同轮 gate_verdict.json 两条身份成对给出（§D96.9：否则 AND 在实物里是空的）",
        "note": "只认 C2 自己的写入面；D 的文书里出现不算 C2 已广播（F 不代 C2 表态）"}
    ready = bool(pair_hits) and not out.get("toplevel_copy", {}).get("class1_red_candidate", False)
    missing = []
    if not pair_hits:
        missing.append("C2 的成对广播（臂内件 + 同轮 gate_verdict 身份）")
    if out.get("toplevel_copy", {}).get("class1_red_candidate"):
        missing.append("顶层件与臂内件分叉且无 superseded_by（96.1-④ 的 Ⅰ 类红候选）")
    return {**out, "status": DELIVERED if ready else NOT_DELIVERED,
            "evidence": ("第 1 步的对账前置齐备" if ready else "第 1 步尚欠：" + "；".join(missing))
                        + f"（最新 PASS = {r.name}，臂内件 {arm_id.get('n_lines')} ln "
                          f"`{arm_id.get('sha256_12')}`，as_of {_now()}）"}


@check("六步-S2", "正式 BC/SFT 的结果口径预登记件是否在开跑前落盘（≥3 种子、正反向分别评估的口径）",
       "裁定 95.3 第 2 步；T-A2-8")
def _s2() -> dict[str, Any]:
    hits = sorted((ROOT / "runs" / "vla").glob("*/CRITERIA_PREREGISTERED.json"))
    bc_dirs = sorted((ROOT / "runs" / "vla").glob("a2_s3_bc*"))
    out: dict[str, Any] = {"six_step": "S2", "n_preregistered": len(hits),
                           "n_bc_run_dirs": len(bc_dirs),
                           "scan_scope": ["runs/vla/*/CRITERIA_PREREGISTERED.json", "runs/vla/a2_s3_bc*"]}
    if hits:
        txt = _read(hits[0]) or ""
        seed_hits = re.findall(r'"[^"]*seed[^"]*"\s*:\s*[^,}\n]{0,40}', txt, re.IGNORECASE)[:4]
        return {**out, "status": DELIVERED,
                "evidence": f"预登记件在盘：{hits[0].relative_to(ROOT)}；其中与种子/口径相关的字段（F 只抄不判够不够）= {seed_hits}",
                "identity": _identity(hits[0], "S2 的结果口径预登记件")}
    if bc_dirs:
        return {**out, "status": NOT_DELIVERED,
                "evidence": f"BC 目录已有 {len(bc_dirs)} 个（{bc_dirs[0].name} 等）但预登记件不在盘 ⇒ 顺序违规（到期条件已触发）"}
    return {**out, "status": NOT_DELIVERED,
            "evidence": f"BC 尚未开跑（无 a2_s3_bc* 目录），预登记件也不在盘 ⇒ 尚不构成顺序违规；到期 = 第 2 步开跑前（as_of {_now()}）"}


@check("六步-S3", "同 ckpt、同初态的配对比较（标准执行 vs 现有 Harness 调度）是否已有可执行判据",
       "裁定 95.3 第 3 步")
def _s3() -> dict[str, Any]:
    return {"six_step": "S3", "status": NOT_APPLICABLE,
            "evidence": "到期条件未触发：S2 尚无 ≥3 种子结果 ⇒ 本条不适用（裁定 72-2：不适用不出红）",
            "due_when": "S2 有 ≥3 种子结果后"}


@check("六步-S4/S5/S6", "恢复是否有效 / 是否真从纠正中学到 / RL 是否带来额外收益",
       "裁定 95.3 第 4–6 步")
def _s456() -> dict[str, Any]:
    return {"six_step": "S4", "status": NOT_APPLICABLE,
            "evidence": "到期条件未触发：S3 尚无结论 ⇒ 第 4–6 步不适用（裁定 72-2）；"
                        "另记：裁定 95.3 明示 P2（大模型监督）排在第 4 步之后",
            "due_when": "S3 出结论后（S5 依 S4、S6 依 S5）"}


@check("裁定 96.1-③（Ⅰ 类 · **阻塞上卡、不阻塞训练**）",
       "E 的 `card_busy()` 修法是否两向都装了探针、验证产物是否在盘（D→F 交接件 §五-3：`checked_by` = F）",
       "裁定 96.1-③；D→F 交接件 §五-3；E 的 residual_risk_register RR2（checked_by = F，每轮）")
def _due_e_card_busy_fix() -> dict[str, Any]:
    out: dict[str, Any] = {"six_step": "S1 前置（上卡纪律）", "triage_class": "Ⅰ",
                           "blocking_scope": "阻塞「上卡」（A2 第一次真上卡前必须修完）；**不阻塞训练/仿真准备**",
                           "checked_by": "F", "checked_when": "A2 第一次申报窗口时；F 每轮先自查（E 的 RR2）",
                           "scan_scope": [E_FIX_VERDICT, F_DIFF_RECHECK, "scripts/f_probe_card_busy.py 的每轮读数"]}
    vp, dp = ROOT / E_FIX_VERDICT, ROOT / F_DIFF_RECHECK
    if not vp.exists():
        return {**out, "status": NOT_MEASURED,
                "evidence": f"{E_FIX_VERDICT} 不在盘 ⇒ 修法验证不可判（不是「没修」）。"
                            f"扫描作用域见 scan_scope；D §D96.9 曾判 not_measured，其名字过滤用小写 `*card_busy*`，"
                            f"而实物名为 `CARD_BUSY_FIX_VERDICT.json`（大小写不匹配 ⇒ 假阴性）"}
    v = json.loads(_read(vp) or "{}")
    verdict, code, n_nm = v.get("verdict"), v.get("exit_code"), v.get("n_not_measured_legs")
    legs = v.get("legs") or {}
    probe = v.get("pattern_coverage_probe")
    out["e_verdict_artifact"] = {"identity": _identity(vp, "E 的修法验证判词；A2 上卡前置之一"),
                                 "verdict": verdict, "exit_code": code, "n_not_measured_legs": n_nm,
                                 "n_legs": len(legs), "pattern_coverage_probe_entries": (len(probe) if hasattr(probe, "__len__") else probe)}
    f_side: dict[str, Any] = {"measurement_status": NOT_MEASURED}
    if dp.exists():
        d = json.loads(_read(dp) or "{}")
        f_side = {"measurement_status": "measured", "verdict": d.get("verdict"),
                  "two_way_probe": (d.get("two_way_probe") or {}),
                  "as_of": d.get("as_of"), "identity": _identity(dp, "F 的独立差分复测（把 F 自己抓到的活体 cmdline 喂进 E 的纯函数）"),
                  "caliber_note": "F 的差分是**时点读数**（活体 PID 会退出）⇒ 每轮须重取；不得当常驻事实（缺陷类 ㉒）"}
    out["f_independent_recheck"] = f_side
    ok_e = verdict == "PASS" and code == 0 and n_nm == 0
    ok_f = f_side.get("verdict") == "fix_confirmed_two_way"
    out["f_probe_caliber_note"] = ("`scripts/f_probe_card_busy.py` 只 ast 取**词表与正则**，测的是词法口径；"
                                   "E 的新判据是「真实执行形态 ∧ 关键字 ∧ 非闲置」的合取 ⇒ 该探针 exit 5 "
                                   "**不能**读成「修法失败」，只能读成「词法口径下仍有文本命中」。"
                                   "决定性证据 = E 的判词件 + F 调 E 的纯函数 `classify_cmdline` 做的差分。")
    if ok_e and ok_f:
        return {**out, "status": DELIVERED,
                "evidence": f"E 的判词件 verdict={verdict} / exit={code} / n_not_measured_legs={n_nm}，"
                            f"且 F 的独立差分两向都过（文本样本 counted=False、真跑样本 counted=True）"
                            f" ⇒ 96.1-③ 的到期条件已满足（as_of {_now()}）"}
    if ok_e:
        return {**out, "status": NOT_DELIVERED,
                "evidence": f"E 侧齐备（{verdict}/exit {code}），但 F 的独立差分缺或未两向过 ⇒ 到期条件未销账（不猜）"}
    return {**out, "status": NOT_DELIVERED,
            "evidence": f"E 的判词件在盘但 verdict={verdict} / exit={code} / n_not_measured_legs={n_nm} ⇒ 未达 96.1-③ 的要求"}


def measure_doc_limit_compliance(limit: int = 120) -> dict[str, Any]:
    """裁定 94.9-3（§D95.7 升为硬口径）：各线日报增量 ≤120 行/轮。

    口径（F 明示、保守）：以 `## ` 顶级段为单位数行（含其 `###` 子节）⇒ 这是**段大小**，
    同一段跨轮追加时会偏大，**不等于**「单轮增量」；F 不猜轮次边界，故宁大勿小。
    """
    text = _read(ROOT / "daily_report.md")
    if text is None:
        return {"measurement_status": NOT_MEASURED, "reason": "daily_report.md 读不到",
                "limit_per_round": limit}
    lines = text.splitlines()
    heads = [i for i, l in enumerate(lines) if l.startswith("## ")]
    heads.append(len(lines))
    secs = [{"section": lines[a][3:70], "start_line": a + 1, "n_lines": b - a,
             "over_limit": (b - a) > limit,
             "is_today": "2026-09-30" in lines[a]} for a, b in zip(heads, heads[1:])]
    over_today = [s for s in secs if s["over_limit"] and s["is_today"]]
    over_hist = [s for s in secs if s["over_limit"] and not s["is_today"]]
    today = [s for s in secs if s["is_today"]]
    return {"measurement_status": "measured", "limit_per_round": limit,
            "authority": "裁定 94.9-3（§D95.7 升为硬口径）；D→F 交接件 §五-2",
            "caliber": "以 `## ` 顶级段为单位数行（含 `###` 子节）= 段大小；同一段跨轮追加会偏大 ⇒ 保守口径，F 不猜轮次边界",
            "compliance_caliber": ("**合规只看今日段**（段头含 2026-09-30）；历史段超限只登记、不判本轮不合规"
                                   "（它们是多轮累积的，段大小 ≠ 单轮增量）"),
            "n_sections": len(secs), "n_sections_today": len(today),
            "n_over_limit_today": len(over_today),
            "over_limit_today": [{"section": s["section"], "start_line": s["start_line"],
                                  "n_lines": s["n_lines"]} for s in over_today[:12]],
            "n_over_limit_historical": len(over_hist),
            "over_limit_historical_head": [{"section": s["section"], "n_lines": s["n_lines"]}
                                           for s in over_hist[:8]],
            "caliber_crosscheck_vs_d": [{"section": s["section"], "n_lines": s["n_lines"],
                                         "over_limit": s["over_limit"]} for s in secs
                                        if any(k in s["section"] for k in
                                               ("§E13", "§D94", "§D95", "§D96", "§B2-17",
                                                "§B2-18", "§F1", "§F2"))],
            "last_8_sections": secs[-8:], "scan_scope": ["daily_report.md"]}



def _latest_f_artifact(prefix: str) -> Path | None:
    hits = sorted((OUT_DIR_ARTIFACTS).glob(f"{prefix}_*.json")) if OUT_DIR_ARTIFACTS.exists() else []
    return hits[-1] if hits else None


OUT_DIR_ARTIFACTS = ROOT / "runs/vla/f_oversight_20260930"


@check("裁定 101.1 六类阻塞项登记", "六类（时间对齐 / 单位与维度 / 夹爪语义 / 可读取与重放 / 泄漏 / 标准同步）是否都已登记且带实测锚与消费方",
       "裁定 101.1 + 101.2 的对应表；D→F 待命令（17:2x）：F 只保这一件")
def _r101_six_classes() -> dict[str, Any]:
    reg = build_trigger_registry()
    block = reg.get("blocking_classes_ruling101") or {}
    classes = block.get("classes") or []
    measured = [c for c in classes if c.get("measurement_status") in ("measured", "partially_measured")]
    return {"status": DELIVERED if len(classes) == 6 and len(measured) == 6 else NOT_DELIVERED,
            "evidence": f"六类登记 {len(classes)} 条、带实测锚的 {len(measured)} 条；"
                        f"非阻塞登记 {len(block.get('non_blocking_registered') or [])} 条（as_of {_now()}）",
            "n_classes": len(classes), "n_with_measured_anchor": len(measured),
            "coverage_metric_suspended": reg.get("coverage_metric_status", {}).get("status")}


@check("补单六 §三-2（L12 链）", "L12 的红→绿链是否**不删**地登进台账，并标 `explained_by = run4 / T8`",
       "裁定 100.1-① / 100.8-F-②；D→F 补单六 §三-2")
def _r100_l12_chain() -> dict[str, Any]:
    block = build_trigger_registry().get("blocking_classes_ruling101", {}).get("l12_chain") or {}
    ok = bool(block.get("chain_not_deleted")) and bool(block.get("explained_by")) \
        and (block.get("run3_reading") or {}).get("measurement_status") == "measured" \
        and (block.get("run4_reading") or {}).get("measurement_status") == "measured"
    return {"status": DELIVERED if ok else NOT_DELIVERED,
            "evidence": f"chain_not_deleted={block.get('chain_not_deleted')}；explained_by={str(block.get('explained_by'))[:60]}…"
                        f"；run3/run4 两半读数 {(block.get('run3_reading') or {}).get('measurement_status')}/"
                        f"{(block.get('run4_reading') or {}).get('measurement_status')}",
            "open_account": block.get("open_account"),
            "sidecars": block.get("criteria_identity_sidecar")}


@check("补单六 §三-2（R1/R2）", "R1/R2 是否已登进台账，并按裁定 101.2 记为「并入 Step 1 产出列、不再是上卡前探针」",
       "裁定 100.8-F-②（登进台账）→ 101.2（撤销 100.1-(b) 的前置）")
def _r100_r1r2() -> dict[str, Any]:
    block = build_trigger_registry().get("blocking_classes_ruling101", {}).get("r1_r2") or {}
    return {"status": DELIVERED if block.get("measurement_status") == "measured" else NOT_DELIVERED,
            "evidence": f"A2 的 R1/R2 run 目录 {block.get('n_run_dirs')} 个；blocking_now={block.get('blocking_now')}"
                        f"（裁定 101.2 撤销了「R1+R2 先做完才可申报窗口」）",
            "run_dirs": block.get("run_dirs_found")}


@check("裁定 100.9 / 101.1 自缚（**超限即由 F 出红**）", "D 的自我限产是否守住：decisions 每轮 ≤60 行 · §D 段 ≤20 行 · params 每轮 ≤1 rev · 新口径每轮 ≤2 条 · 交接件每线每轮 ≤1 份 · 身份自检降为每里程碑一次",
       "裁定 100.9（F 可核、超限出红）+ 101.1 自缚四条 + D→F 补单六 §三-5")
def _r100_d_self_limit() -> dict[str, Any]:
    res = measure_d_self_limit()
    over = res.get("overall") == "exceeded"
    return {"status": NOT_DELIVERED if over else DELIVERED,
            "evidence": ("**超限（F 出红）**：" + json.dumps(res.get("exceeded"), ensure_ascii=False)[:300]
                         if over else
                         "自裁定 101 起三轮（r101 / r102 / r102.7）实测：decisions 增量 "
                         + str([r.get("decisions_line_delta") for r in res.get("rounds", [])])
                         + " ≤60；§D 段行数 " + str([s["n_lines"] for s in res.get("daily_d_sections", [])])
                         + " ≤20；新口径名 " + str([r.get("n_new_caliber_names") for r in res.get("rounds", [])]) + " ≤2"),
            "overall": res.get("overall"), "exceeded": res.get("exceeded"),
            "handoff_ambiguity": res["limits"]["handoff_per_line_per_round"]["ambiguity_registered"],
            "unnamed_rules_note": res["limits"]["new_calibers_per_round_le_2_and_class1"]["unnamed_rules_note"]}


def _recheck_artifact(prefix: str, what: str, authority: str) -> dict[str, Any]:
    path = _latest_f_artifact(prefix)
    if path is None:
        return {"status": NOT_DELIVERED,
                "evidence": f"在 runs/vla/f_oversight_20260930/ 扫过 `{prefix}_*.json` 未命中（as_of {_now()}）⇒ {what} 未落盘"}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": NOT_MEASURED, "evidence": f"{path.name} 读不到（{type(exc).__name__}）⇒ 不猜"}
    return {"status": DELIVERED, "evidence": f"{what} = {path.name}",
            "identity": _identity(path, what), "authority": authority,
            "artifact_measurement_status": data.get("measurement_status"), "payload": data}


@check("补单五-① / 补单六-1（G14）", "F 的 `G14` 独立语义判定件是否已落盘（`checked_by=F` 从裁定值引用变成有实物支撑）",
       "裁定 97.3-4 / 99.5-F-① / 100.8-F-①；params `checked_by = F（每轮复测 flip_measured）`")
def _r100_g14() -> dict[str, Any]:
    res = _recheck_artifact("F_G14_DETERMINATION", "G14 的独立语义判定件", "裁定 97.3-4 / 100.8-F-①")
    payload = res.pop("payload", None) or {}
    res["g14_flip_measured"] = payload.get("g14_flip_measured")
    res["determination_status"] = payload.get("measurement_status")
    res["class_attribution_status"] = (payload.get("class_attribution") or {}).get("measurement_status")
    res["n_runs_rechecked"] = payload.get("n_runs_measured")
    res["n_runs_with_flip"] = payload.get("n_runs_with_flip_measured")
    res["tool_self_report"] = ((payload.get("class_attribution") or {}).get("self_check") or {}).get("v2_first_attempt_self_report")
    if res["status"] == DELIVERED and payload.get("measurement_status") != "measured":
        res["status"] = NOT_MEASURED
        res["evidence"] += "；但判定件自身 `measurement_status != measured` ⇒ 不猜"
    return res


@check("补单六-3（criteria_identity）", "裁定 100.3-（c）的两件是否补齐：判据脚本入库 + 判词件里的 `criteria_identity` 块；「判据有没有在对象上干跑」是否已做成可复核字段",
       "裁定 100.3-（c）（d）/ 99.3-③；D→F 补单六 §三-3")
def _r100_criteria_identity() -> dict[str, Any]:
    res = _recheck_artifact("F_CRITERIA_IDENTITY_RECHECK", "criteria_identity 的复核件", "裁定 100.3-（c）")
    payload = res.pop("payload", None) or {}
    verdict = payload.get("verdict_on_100_3_c") or {}
    res["criteria_identity_block"] = verdict.get("criteria_identity_block")
    res["judging_script_in_git"] = verdict.get("judging_script_in_git")
    res["attribution"] = verdict.get("attribution")
    res["dry_run_field_sections"] = [(s.get("label"), s.get("n_carrying_readings"), s.get("n_cited_rows"))
                                     for s in (payload.get("dry_run_on_object_field") or {}).get("sections", [])]
    res["dry_run_filter_self_check"] = ((payload.get("dry_run_on_object_field") or {}).get("filter_self_check") or {}).get("filter_non_vacuous")
    if verdict.get("criteria_identity_block") != "delivered":
        res["status"] = NOT_DELIVERED
    return res


@check("补单六-4 + 102.6（⑲ 复核）", "D 的 ⑲ 第 13–18 件是否已逐件独立复核（F 的台账是权威），三条新口径与既有缺陷类表的相容性是否已判",
       "裁定 99.5-F-④ / 100.8-F-③ / 102.6；D→F 补单六 §三-4（相容性由 F 判）")
def _r100_defect19() -> dict[str, Any]:
    res = _recheck_artifact("F_DEFECT19_RECHECK", "⑲ 第 13–18 件的独立复核件", "裁定 102.6")
    payload = res.pop("payload", None) or {}
    res["statuses"] = {str(i.get("instance")): i.get("f_status") for i in payload.get("items", [])}
    res["f_instances_enumerated"] = (payload.get("f_authoritative_count") or {}).get("instances_enumerated")
    res["caliber_conflicts_found"] = (payload.get("caliber_compatibility_review") or {}).get("conflicts_found")
    res["f_self_note_16"] = next((i.get("f_independent_measurement", {}).get("f_self_note")
                                  for i in payload.get("items", []) if i.get("instance") == 16), None)
    return res


@check("补单六-⑥（545319 一问）", "「PID 545319 是不是 F 的会话」是否已按实测答出（含 F 侧不可测的那一部分）",
       "裁定 100.6-（b）；D→F 补单六 §五（该问的形状已被 §100.11-③ 撤回，F 仍按实测答）")
def _r100_session_pid() -> dict[str, Any]:
    res = _recheck_artifact("F_SESSION_PID_545319_ANSWER", "545319 一问的实测答复件", "裁定 100.6-（b）")
    payload = res.pop("payload", None) or {}
    res["answer_one_line"] = payload.get("answer_one_line")
    res["earlier_rounds_attributable"] = (payload.get("earlier_rounds_attributable") or {}).get("measurement_status")
    res["question_withdrawn_by_d"] = "裁定 100.11-③（问的形状撤回，改为只问 A2）"
    return res


@check("裁定 102.6（Step 1 里程碑审查）", "Step 1 的四条验收标准是否已有实测读数支撑（F 核读数在不在，不判通过）",
       "裁定 101.2 的四条验收标准（逐字采纳用户原文）+ 102.2 的四处冲突裁定 + D→F 待命令（17:2x）",
       )
def _r102_step1_review() -> dict[str, Any]:
    tr = step1_acceptance_tracker()
    rows = tr.get("criteria") or []
    have = [r for r in rows if r.get("measurement_status") != NOT_MEASURED]
    if not have:
        return {"status": NOT_APPLICABLE, "six_step": "S1",
                "evidence": f"Step 1 的 train/rollout 读数尚未落盘（盘上 {tr.get('n_step1_artifacts')} 件、四条验收标准 0 条有读数）"
                            f"⇒ 到期条件未触发，不判红（裁定 72-2）",
                "due_when": "A2 按固定六问报完 Step 1 的结果（裁定 102.6：F 在里程碑审查在场）",
                "criteria": rows}
    return {"status": DELIVERED, "six_step": "S1",
            "evidence": f"四条验收标准里 {len(have)}/4 已有读数（{[r['criterion_id'] for r in have]}）；"
                        f"能力声明禁令照裁定 46 / 101.3：读数只指判词",
            "criteria": rows}


def build_trigger_registry() -> dict[str, Any]:
    """扫参数表与裁定件里的预登记条件，逐条报「有没有消费方」。

    三值：`has_consumer` / `no_consumer` / `not_measured`。判据 = 该条件所在对象里
    是否同时出现 `checked_by`（谁核）与 `checked_when`（何时核）—— 这是裁定 94.9-5
    自己定的形状，F 不另立。
    """
    out: dict[str, Any] = {"artifact": "f_trigger_registry", "as_of": _now(),
                           "authority": ["裁定 101.1（治理硬冻结：只保留六类阻塞项，其余登记不阻塞）",
                                         "D→F 待命令（17:2x）：F 只维持六类阻塞项的登记，**停覆盖率指标**",
                                         "裁定 94.9-5 / 缺陷类 ⑳（历史口径：预登记条件的消费方台账）"],
                           "scan_scope": ["work/project_parameters.json", "work/decisions/decisions_20260929.md",
                                          "runs/vla/a2_step1_prealign_20260930_run3|run4/PREALIGN_VERIFICATION.json",
                                          "runs/vla/a2_s3_bc_overfit_20260930/*", "runs/vla/a2_r1_r2_alignment_20260930_*"],
                           "scan_method": "限定前缀读取 + 键名/关键词匹配；**未扫根文件系统**（裁定 94.9-2）",
                           "entries": [], "summary": {}}
    # ── 裁定 101.1：覆盖率类指标停跑（原字节由 before_images 保全；上一轮读数如实保留） ──
    out["coverage_metric_status"] = {
        "status": "suspended_by_ruling_101",
        "authority": "裁定 101.1 + D→F 待命令（17:2x）：`6/53 = 11.32%` 那种统计不再要求增长、Step 1 出结果前不再更新",
        "not_updated_this_round": True,
        "last_reading": {"as_of": "2026-09-30T16:09:49+0800", "identity": "TRIGGER_REGISTRY.json@d0661270d337",
                         "n_entries": 53, "n_has_consumer": 6, "coverage_all": 0.1132,
                         "n_in_scope_steps_1_to_3": 4, "coverage_in_scope": 0.5},
        "before_image_of_last_reading": "runs/vla/f_oversight_20260930/before_images/TRIGGER_REGISTRY.json.before_20260930_160949",
        "still_owed_to_d": ("范围内两条无消费方的预登记条件（`operations.gpu_window_mechanism_rev19_trigger_fired.finding` "
                            "与 `measurements_and_decisions[120].value`）仍需 D 在 params 补 `checked_by=F`；F 不写 params"),
    }
    out["blocking_classes_ruling101"] = build_blocking_class_registry()
    out["classification_ruling104"] = build_classification_ruling104()
    out["ruling104_scope_note"] = ("补单·四-①：三项治理指标（`coverage` / `doc_limit_compliance` / "
                                   "`pattern_coverage_probe`）**仍停跑**，本轮为裁定 104 **未新增任何指标或登记处** —— "
                                   "上面两块都写在既有的 `TRIGGER_REGISTRY.json` 里。")
    out["entries_note"] = ("`entries`（53 条预登记条件的逐条清单）本轮**不再重扫**：它就是被停跑的覆盖率指标的分母。"
                           "上一轮的逐条清单在 before_images 里原字节保全。六类阻塞项的登记见 "
                           "`blocking_classes_ruling101`；裁定 104 的两块登记见 "
                           "`blocking_classes_ruling101.class_i_open_items_ruling104` 与 `classification_ruling104`。")
    out["measurement_status"] = "measured"
    return out
    # ── 以下是**被裁定 101.1 停跑**的原覆盖率实现：原字节保留、不可达；冻结解除后由 D 下令再启用 ──
    path = ROOT / "work" / "project_parameters.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError) as exc:
        out["measurement_status"] = NOT_MEASURED
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    key_rx = re.compile(r"可推翻条件|trigger_to_promote|falsifiable|rebuttal|overturn", re.IGNORECASE)
    # 裁定 96.1-②：只有第 1–3 步那一批（T-C2-8 最小集 / T-A2-6 / T-A2-7 / T-B2-20 / T-E-11 /
    # T-E-12 名下）才补消费方，其余一律不补 ⇒ 归属在**遍历当时**用整个兄弟对象的文本判。
    # 不能只看 220 字摘录：第一版就是这么窄的，n_in_scope=0、覆盖率恒 null（缺陷类 ⑲）。
    scope_rx = re.compile(r"T-C2-8|T-A2-6|T-A2-7|T-B2-20|T-E-11|T-E-12"
                          r"|ruling95_critical_path_six_steps|ruling95_technical_corrections"
                          r"|bc_consumption_caliber")

    def walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{trail}.{key}" if trail else key
                if key_rx.search(str(key)) or (isinstance(value, str) and key_rx.search(value)):
                    blob = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
                    sibling = json.dumps(node, ensure_ascii=False)
                    has_by = "checked_by" in sibling or "checked_by" in blob
                    has_when = "checked_when" in sibling or "checked_when" in blob
                    out["entries"].append({
                        "where": here,
                        "status": "has_consumer" if (has_by and has_when) else "no_consumer",
                        "checked_by_present": has_by, "checked_when_present": has_when,
                        "excerpt": (value if isinstance(value, str) else blob)[:220],
                        "scope_steps_1_to_3": bool(scope_rx.search(here) or scope_rx.search(sibling)),
                    })
                walk(value, here)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{trail}[{i}]")

    walk(data, "")
    n = len(out["entries"])
    n_has = sum(1 for e in out["entries"] if e["status"] == "has_consumer")
    out["summary"] = {
        "n_entries": n, "n_has_consumer": n_has, "n_no_consumer": n - n_has,
        "coverage": (round(n_has / n, 4) if n else None),
        "coverage_caliber": "参数表内键名/文本命中 `可推翻条件|trigger_to_promote|falsifiable|rebuttal|overturn` 的对象",
        "empty_set_rule": "n=0 ⇒ coverage=null（`aggregate_over_empty_set_must_be_null`，裁定 88.4）",
    }
    out["measurement_status"] = "measured" if n else NOT_MEASURED

    # 裁定件侧：只数「有多少个 §小节提到可推翻条件、其中多少提到 checked_by」，不解析散文语义
    dec = ROOT / "work" / "decisions" / "decisions_20260929.md"
    text = _read(dec)
    if text is None:
        out["decisions_side"] = {"measurement_status": NOT_MEASURED, "reason": f"{dec} 读不到"}
    else:
        sections: list[str] = []
        cur = "(preamble)"
        cur_has_cond = cur_has_consumer = False
        for line in text.splitlines():
            if line.startswith("## "):
                if cur_has_cond:
                    sections.append({"section": cur, "checked_by_mentioned": cur_has_consumer})
                cur, cur_has_cond, cur_has_consumer = line[3:60], False, False
            if key_rx.search(line):
                cur_has_cond = True
            if "checked_by" in line:
                cur_has_consumer = True
        if cur_has_cond:
            sections.append({"section": cur, "checked_by_mentioned": cur_has_consumer})
        out["decisions_side"] = {
            "measurement_status": "measured",
            "n_sections_with_preregistered_condition": len(sections),
            "n_sections_mentioning_checked_by": sum(1 for s in sections if s["checked_by_mentioned"]),
            "sections_without_consumer": [s["section"] for s in sections if not s["checked_by_mentioned"]][:20],
            "note": "散文侧只数命中、不解析语义（F 不代 D 判断某条条件是否真的需要消费方）",
        }

    # 裁定 96.1-②：覆盖率**只统计与六步第 1–3 步直接相关的那一批**（T-C2-8 最小集 / T-A2-6 /
    # T-A2-7 / T-B2-20 / T-E-11 / T-E-12 名下），其余一律不补 ⇒ 两个分母分开报，不混算。
    in_scope = [e for e in out["entries"] if e.get("scope_steps_1_to_3")]
    n_in = len(in_scope)
    n_in_has = sum(1 for e in in_scope if e["status"] == "has_consumer")
    out["scope_steps_1_to_3"] = {
        "measurement_status": "measured" if n_in else NOT_MEASURED,
        "authority": "裁定 96.1-②（D→F 交接件 §二）+ §五-2（覆盖率是 F 的常设登记指标）",
        "scope_rule": ("参数表内该条件的 `where` 路径或**整个兄弟对象文本**里提到 T-C2-8 / T-A2-6 / T-A2-7 / "
                       "T-B2-20 / T-E-11 / T-E-12，或 rev20/rev21/rev22 的六步与 BC 消费口径键"),
        "mapping_status": "f_draft_pending_d_milestone_review（F 出草案、不定标；映射错由 D 纠正）",
        "n_in_scope": n_in, "n_has_consumer_in_scope": n_in_has,
        "coverage_in_scope": (round(n_in_has / n_in, 4) if n_in else None),
        "n_out_of_scope_never_backfill": len(out["entries"]) - n_in,
        "out_of_scope_rule": "裁定 96.1-②：其余一律不补（全补正是 95.1 要止住的 Ⅲ 类扩张）",
        "in_scope_entries": [{"where": e["where"], "status": e["status"]} for e in in_scope][:24],
        "empty_set_rule": "n_in_scope=0 ⇒ coverage_in_scope=null（裁定 88.4）",
    }
    return out


# ---------------------------------------------------------------------------
# 93.8 对照探针：审计器必须先证明自己的模式覆盖
# ---------------------------------------------------------------------------
def pattern_coverage_probe(tmpdir: Path) -> dict[str, Any]:
    """两向：① 注入一条**裸形态**的任务号 ⇒ 抽取器必须命中；
    ② 注入一条判据为假的 check ⇒ 必须报 `not_delivered`，**不得**报 `delivered`。

    缺这颗探针 ⇒ 本台账按 `not_measured` 登记、不得报绿（裁定 93.8 / 缺陷类 ⑲）。
    """
    probe_dir = tmpdir / "f_probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    injected_bad_form = "裸形态任务号（无「任务」二字、无表格、混在散文里）：T-Z9-99"
    doc = probe_dir / "injected_task_book.md"
    doc.write_text(f"# 合成任务书\n\n{injected_bad_form}\n\n另有带前缀的 T-Z9-98 一条。\n",
                   encoding="utf-8")
    text = doc.read_text(encoding="utf-8")
    found = sorted(set(re.findall(r"\bT-[A-Z0-9]+-\d+\b", text)))
    probe_a = {"name": "task_id_extraction_covers_bare_form",
               "injected_bad_form": injected_bad_form,
               "detected": ("T-Z9-99" in found), "found": found}

    # ② 三值映射的**两向**验证（不 grep 本件自己 —— 第一版就是这么犯的：注入的
    #    "必然零命中"模式串写在本件源码里，于是被自己命中，`detected=false`。
    #    那是缺陷类 ⑲ 的自实例，已根因修：改为直接验映射 + 哨兵**运行时拼接**）。
    zero_hit, _ = _src_status([], NC)
    one_hit, _ = _src_status([f"{NC}:1"], NC)
    sentinel = "F_SENTINEL_" + "MUST_HAVE_ZERO_HIT"      # 运行时拼接 ⇒ 不会自匹配
    sentinel_hits = _grep_lines(NC, sentinel)
    probe_b = {"name": "three_state_mapping_is_two_directional",
               "injected_bad_form": "零命中判据必须报 not_delivered、非零必须报 delivered、且哨兵必须真的零命中",
               "detected": (zero_hit == NOT_DELIVERED and one_hit == DELIVERED and sentinel_hits == []),
               "zero_hit_status": zero_hit, "one_hit_status": one_hit,
               "sentinel_hits_in_target": len(sentinel_hits),
               "self_caught_defect": ("第一版把哨兵模式串写死在本件里 ⇒ 被自己命中 ⇒ detected=false；"
                                      "本机自检 exit=3 拦下，未落进任何台账（F 自报，缺陷类 ⑲ 自实例）")}

    # ③ 目标不存在 ⇒ 必须 `not_measured`，**不得** `not_delivered`（不许把"没测"写成"没有"）
    missing_status, missing_ev = _src_status([], "scripts/f_this_target_does_not_exist.py")
    probe_c = {"name": "missing_target_must_be_not_measured_never_not_delivered",
               "injected_bad_form": "指向不存在文件的判据",
               "detected": (missing_status == NOT_MEASURED),
               "status": missing_status, "evidence": missing_ev}

    probes = [probe_a, probe_b, probe_c]
    return {"citation_algo": CITATION_ALGO, "authority": "裁定 93.8 / 缺陷类 ⑲",
            "probes": probes, "all_detected": all(p["detected"] for p in probes),
            "injected_bad_form": probe_a["injected_bad_form"], "detected": probe_a["detected"]}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 裁定 101.1：治理硬冻结后，F 只保一件 = **六类阻塞项的登记**（其余登记不阻塞）
# 六类的名字与 Step 1 的对应关系逐字抄 D 的 §101.2；F 不新设、不改名、不合并。
# ---------------------------------------------------------------------------
STEP1_RUN_GLOB = "a2_s3_bc_overfit_20260930/*"
R1R2_GLOB = "a2_r1_r2_alignment_20260930_*"
PREALIGN_RUN3 = "runs/vla/a2_step1_prealign_20260930_run3/PREALIGN_VERIFICATION.json"
PREALIGN_RUN4 = "runs/vla/a2_step1_prealign_20260930_run4/PREALIGN_VERIFICATION.json"

SIX_BLOCKING_CLASSES: list[dict[str, Any]] = [
    {"class_id": 1, "name_verbatim": "动作和状态时间对齐",
     "step1_column": "验收标准 ③「动作和夹爪时间对齐没有未解释的系统性偏移」+ 产出④",
     "anchors": [("run4 的 L12（现值）", PREALIGN_RUN4, "L12_action_time_alignment"),
                 ("run3 的 L12（红→绿链的前一半，**不删**）", PREALIGN_RUN3, "L12_action_time_alignment")],
     "consumer": {"checked_by": "A2（Step 1 的 ③④ 两列）+ F（登记）", "checked_when": "Step 1 报告落盘时（里程碑审查）"}},
    {"class_id": 2, "name_verbatim": "动作单位与维度",
     "step1_column": "验收标准 ①「训练集动作误差明显下降」+ 产出①",
     "anchors": [("run4 的 L2（归一化后范围）", PREALIGN_RUN4, "L2_normalized_range"),
                 ("run4 的 L6（维序一致）", PREALIGN_RUN4, "L6_dim_order_same")],
     "consumer": {"checked_by": "A2（Step 1 的 ① 列）+ F（登记）", "checked_when": "Step 1 报告落盘时"}},
    {"class_id": 3, "name_verbatim": "夹爪语义",
     "step1_column": "产出④「夹爪转变帧误差」（= R2）",
     "anchors": [("run4 的 L5（极性 1.0=张开 / 0.0=合爪、9 个离散值）", PREALIGN_RUN4, "L5_gripper_semantics")],
     "consumer": {"checked_by": "A2（R2 / Step 1 的 ④ 列）+ F（登记）", "checked_when": "Step 1 报告落盘时"}},
    {"class_id": 4, "name_verbatim": "数据是否能被读取和重放",
     "step1_column": "验收标准 ②「至少一条正向和一条反向轨迹能从示范初态闭环复现」",
     "anchors": [("run4 的 L9（示范初态复现）", PREALIGN_RUN4, "L9_env_initial_state_reproduce"),
                 ("run4 的 L11（post-init 瞬态）", PREALIGN_RUN4, "L11_post_init_transient"),
                 ("run4 的 L8（示范初态抽取）", PREALIGN_RUN4, "L8_demo_initial_states_extract"),
                 ("run4 的 L3（roundtrip）", PREALIGN_RUN4, "L3_roundtrip")],
     "consumer": {"checked_by": "A2（Step 1 的 rollout 腿）+ F（登记）", "checked_when": "Step 1 报告落盘时"}},
    {"class_id": 5, "name_verbatim": "训练/测试是否泄漏",
     "step1_column": "§101.2 的用户口径：按整条 episode 划分；过拟合阶段允许用示范集本身，但闭环复现必须从示范初态起、不得用评测集调参",
     "anchors": [("A2 的 Step 1 预登记件", "runs/vla/a2_s3_bc_overfit_20260930/PRE_REGISTRATION.json", None),
                 ("A2 的 Step 1 缓存清单（train/val 两份 npz）", "runs/vla/a2_s3_bc_overfit_20260930/CACHE_MANIFEST.json", None)],
     "consumer": {"checked_by": "A2（划分口径落盘）+ F（登记）", "checked_when": "Step 1 报告落盘时"}},
    {"class_id": 6, "name_verbatim": "标准同步控制是否正确执行",
     "step1_column": "§101.2「不使用 Harness 后半段调度」+ 产出⑤「每步动作间隔」",
     "anchors": [("A2 的 Step 1 阶段汇总", "runs/vla/a2_s3_bc_overfit_20260930/STEP1_RUN_SUMMARY.json", None),
                 ("`wall_ms_per_ctrl_step` 的实现锚（§102.2-④ 点名）", "harness/vla_runtime.py",
                  "wall_ms_per_ctrl_step")],
     "consumer": {"checked_by": "A2（standard_sync 下的逐集间隔）+ F（登记）", "checked_when": "Step 1 报告落盘时"}},
]

NON_BLOCKING_REGISTERED = [
    "`G20` 的计数与搬迁批次（裁定 101.1：`OPEN-C2-MOVE-DEFERRED`，登记不阻塞）",
    "身份核对 / 身份表（裁定 101.1-(c)：从每轮降为每里程碑一次）",
    "F 的覆盖率类指标（`coverage` / `doc_limit_compliance` / `pattern_coverage_probe`：Step 1 出结果前停跑）",
    "`git bundle` 记录形态（裁定 99.1-① / 102.5-①）",
    "文书行数与节数记账（裁定 94.9-3 的 ≤120 行仍适用，但不再作为治理指标扩张）",
]


# ---------------------------------------------------------------------------
# 裁定 104（D→F 补单·四）：登记一条 Ⅰ 类缺陷 + 四笔记功/缺陷的归类。
# 约束（补单·四-①）：三项治理指标仍停跑、**不为裁定 104 新增任何指标或登记处**
# ⇒ 下面两块都写进既有的 `TRIGGER_REGISTRY.json`，不新建文件、不新建门禁。
# ---------------------------------------------------------------------------
A2_PREALIGN = "scripts/a2_step1_prealign_verify.py"
A2_BCOVERFIT = "scripts/a2_step1_bc_overfit.py"
GPU_LEDGER = "runs/infra/gpu_window_ledger.jsonl"
WATCHER_SH = "tmp/a2_step1_watcher.sh"
WATCHER_POLLS = "runs/vla/a2_s3_bc_overfit_20260930/watcher_w2/watcher_polls.jsonl"
F_DEFECT19_ARTIFACT = "runs/vla/f_oversight_20260930/F_DEFECT19_RECHECK_20260930_175736.json"

# 判「`q[19:23]` 这一句是写还是读」：只有切片在**等号左边**才算写。
SLICE_WRITE_RX = re.compile(r"[A-Za-z_][A-Za-z0-9_.\[\]]*\[19:23\]\s*=(?!=)")


def _slice_1923_scan(rel: str) -> dict[str, Any]:
    """在单个文件里扫 `[19:23]` 的命中，并逐条判「写 / 读」。带两向自检（裁定 93.8）。"""
    hits = _grep_lines(rel, r"\[19:23\]")
    lines = (_read(ROOT / rel) or "").splitlines()
    rows: list[dict[str, Any]] = []
    for hit in hits:
        line_no = int(hit.rsplit(":", 1)[1])
        text = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else ""
        rows.append({"hit": hit, "line_no": line_no, "is_write": bool(SLICE_WRITE_RX.search(text)),
                     "line_text": text.strip()[:170]})
    pos_ctrl = "q[19:23] = np.asarray(box_quat, dtype=np.float64)"
    neg_ctrl = "quat_at_reset = np.asarray(ph.data.qpos[19:23], dtype=np.float64).copy()"
    self_check = {"positive_control": pos_ctrl,
                  "positive_control_is_write": bool(SLICE_WRITE_RX.search(pos_ctrl)),
                  "negative_control": neg_ctrl,
                  "negative_control_is_write": bool(SLICE_WRITE_RX.search(neg_ctrl)),
                  "filter_non_vacuous": bool(SLICE_WRITE_RX.search(pos_ctrl)) and not SLICE_WRITE_RX.search(neg_ctrl),
                  "consequence_if_false": ("两向自检不过 ⇒ 本条一律读 not_measured，"
                                           "**不许**据此下「没写四元数」的结论（裁定 93.8：只装一向不许报绿）")}
    return {"file": rel,
            "identity": _identity(rel, "裁定 104.2 的 Ⅰ 类缺陷 `demo_init_box_quat_not_written` 的对象侧锚"),
            "n_hits_slice_1923": len(rows), "hits": rows,
            "n_writes_slice_1923": sum(1 for r in rows if r["is_write"]),
            "write_hits": [r["hit"] for r in rows if r["is_write"]],
            "read_hits": [r["hit"] for r in rows if not r["is_write"]],
            "detector_self_check": self_check,
            "detector_usable": self_check["filter_non_vacuous"],
            "measurement_status": "measured" if self_check["filter_non_vacuous"] else NOT_MEASURED,
            "caliber": ("命中 = 字节子串；写/读 = 切片是否在等号左边（正则）。F 只核「有没有写这一句」，"
                        "**不判物理后果大小**（那要 A2 的 CPU-only 测量，裁定 104.3）")}


def build_class_i_open_items_ruling104() -> dict[str, Any]:
    """裁定 104.2–104.3 + D→F 补单·四-②：登记 Ⅰ 类缺陷，锚由 F 自己取（不转抄 D 的行号）。"""
    scans = {rel: _slice_1923_scan(rel) for rel in (A2_PREALIGN, A2_BCOVERFIT)}
    usable = all(s["detector_usable"] for s in scans.values())
    n_writes_total = sum(s["n_writes_slice_1923"] for s in scans.values())
    init_def = _grep_lines(A2_PREALIGN, r"^def _init_env_to_state\(")
    box_xyz_writes = _grep_lines(A2_PREALIGN, r"q\[16:19\]\s*=")
    step1_call_site = _grep_lines(A2_BCOVERFIT, r"PRE\._init_env_to_state\(")
    state_dim = _grep_lines(A2_BCOVERFIT, r"^STATE_DIM\s*=")
    readback_14 = _grep_lines(A2_BCOVERFIT, r"st\[:14\]|\[:STATE_DIM\]")
    a2_not_affected_key = _grep_lines(A2_BCOVERFIT, r"step1_rollout_not_affected")
    a2_d4_key = _grep_lines(A2_BCOVERFIT, r"self_defect_registered")
    existence_measured = bool(init_def and box_xyz_writes and step1_call_site and usable)
    item = {
        "item_id": "demo_init_box_quat_not_written",
        "class_ids": [1, 6],
        "class_names_verbatim": ["动作和状态时间对齐（+ 初态正确性）", "标准同步控制是否正确执行"],
        "classified_by": "D（裁定 104.2-(a)：定性 Ⅰ 类，落在用户 Step-1 出场判据的字面「从示范初态」上）",
        "blocking": True,
        "blocking_scope": "六类之内 = 阻塞（裁定 101.1）；本条归第 ①/⑥ 两类 ⇒ 在阻塞范围内，但处置按裁定 104.3",
        "status": "OPEN",
        "measurement_status": NOT_MEASURED,
        "measurement_status_reason": ("**事实链的存在性**由 F 独立测到（见 `f_independent_anchors`）；"
                                      "**后果大小（沉降前后姿态差）未测** —— 那是 A2 的 CPU-only 测量，"
                                      "本条落盘时还没有读数 ⇒ 记 not_measured，不猜（裁定 88.3-1）"),
        "authority": ["裁定 104.2（定性 Ⅰ 类 / OPEN / not_measured）",
                      "裁定 104.3（处置：不新增门禁、不改判据常量、不停守望器；甲/乙两分支都预登记）",
                      "D→F 补单·四-②（F 本轮登记这一条，归第 ①+⑥ 类）"],
        "disposition_pointer": {
            "who_measures": "A2（CPU-only：不上卡、不执行 policy、不动冻结面；断言与阈值由 A2 自己预登记）",
            "branch_甲": "差 ≤ 阈值 ⇒ 该键升为 `measured_and_immaterial`，Step-1 按现码起跑、一个字节不改",
            "branch_乙": "差 > 阈值 ⇒ 只允许一处窄修（`_init_env_to_state` 补写四元数）",
            "race_fallback": ("守望器若在测量落盘前起跑 ⇒ 那一跑仍有效、不作废，但本条必须作为"
                              "**已登记混淆项**随报告一起出（裁定 104.3）"),
            "adjudicator": "D（里程碑审查）；F 不判甲/乙，只登记读数在不在"},
        "f_independent_anchors": {
            "init_fn_def": init_def,
            "box_xyz_write_sites": box_xyz_writes,
            "box_quat_write_sites_total": n_writes_total,
            "scan_per_file": scans,
            "step1_closed_loop_uses_same_path": step1_call_site,
            "readback_scope_state_dim": state_dim,
            "readback_slice_hits": readback_14,
            "a2_key_not_accepted_by_d": a2_not_affected_key,
            "a2_d4_self_registration_scope": a2_d4_key,
            "existence_measurement_status": "measured" if existence_measured else NOT_MEASURED,
            "f_finding": ("F 独立核到：`_init_env_to_state` 写方块 xyz 的句子在盘（命中见上），"
                          "而两个脚本里对 `[19:23]` 的**写**命中 = "
                          f"{n_writes_total} 条；Step-1 的闭环初态经由 `PRE._init_env_to_state(...)` "
                          "走同一路径；回读作用域 = `STATE_DIM`（14 维）⇒ D 的「证据作用域 ⊊ 结论作用域」"
                          "在字面上可核。**F 不判该缺陷对 Step-1 结果的实质影响**（未测）。")},
        "capability_claim": None, "policy_executed": False, "gpu_used": False,
        "as_of": _now()}
    return {"registry_block": "class_i_open_items_ruling104",
            "as_of": _now(),
            "lives_inside": "TRIGGER_REGISTRY.json（既有登记处；补单·四-①：不新增登记处/指标）",
            "authority": ["裁定 104.2 / 104.3", "D→F 补单·四-②"],
            "n_items": 1, "items": [item],
            "no_new_metric_created": True,
            "governance_metrics_still_suspended": ["coverage", "doc_limit_compliance", "pattern_coverage_probe"]}


def _window_ledger_rows() -> list[dict[str, Any]]:
    """`runs/infra/gpu_window_ledger.jsonl` 的逐行读数（只取时刻/事件字段，用于 ⑲ 第 19 件的锚）。"""
    path = ROOT / GPU_LEDGER
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for i, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            rows.append({"row_no": i, "measurement_status": NOT_MEASURED, "reason": "该行不是合法 JSON"})
            continue
        rows.append({"row_no": i, "event": d.get("event"), "line": d.get("line"),
                     "task_id": d.get("task_id"), "recorded_at": d.get("recorded_at"),
                     "declared_start": d.get("declared_start"), "declared_end": d.get("declared_end"),
                     "not_an_incident": d.get("not_an_incident"), "cotenant_used": d.get("cotenant_used")})
    return rows


def _watcher_anchors() -> dict[str, Any]:
    """守望器的活体锚（⑲ 第 20 件用）：只读 /proc 与既有 poll 账，不起 `find`、不动守望器。"""
    ps = _ps_pids()
    hits = {pid: cmd for pid, cmd in ps.items() if "a2_step1_watcher" in cmd}
    proc_start: dict[str, str] = {}
    for pid in hits:
        try:
            proc_start[str(pid)] = datetime.fromtimestamp(os.stat(f"/proc/{pid}").st_ctime).astimezone().isoformat()
        except OSError:
            proc_start[str(pid)] = NOT_MEASURED
    first_ts = last_ts = None
    n_polls = 0
    polls = ROOT / WATCHER_POLLS
    if polls.exists():
        rows = []
        for raw in polls.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        n_polls = len(rows)
        if rows:
            first_ts, last_ts = rows[0].get("ts"), rows[-1].get("ts")
    return {"watcher_script": _identity(WATCHER_SH, "守望器脚本（裁定 104.1 点名）"),
            "watcher_pids_alive": sorted(hits), "watcher_cmdlines": hits,
            "proc_ctime_as_start_caliber": proc_start,
            "proc_ctime_caliber_note": ("`/proc/<pid>` 的 ctime ≈ 进程起跑时刻（F 自标口径，非裁定口径），"
                                        "与首次 poll 的 `ts` 互证；两者不符 ⇒ 本条读 not_measured"),
            "polls_file": _identity(WATCHER_POLLS, "守望器轮询账（append-only）"),
            "n_polls": n_polls, "first_poll_ts": first_ts, "last_poll_ts": last_ts,
            "measurement_status": "measured" if (hits or n_polls) else NOT_MEASURED,
            "as_of": _now()}


DEFECT19_F_STATUS: list[dict[str, str]] = [
    {"item": "⑲ 第 14 件", "f_status": "confirmed_by_f",
     "f_anchor": "F 用 `cp -p` 前像的 mtime 独立复算出 11m53s 那个差（`F_DEFECT19_RECHECK_…175736.json`）"},
    {"item": "⑲ 第 15 件", "f_status": "confirmed_by_f",
     "f_anchor": "F 自己对找到的第一版跑 `ast.parse` = SyntaxError，且 4 件重定基产物的读数与 D 钉的值相符"},
    {"item": "⑲ 第 16 件", "f_status": "confirmed_with_f_self_report",
     "f_anchor": "「此前有登记」这一层成立；但 F 自报：那句「A2 侧 128128」的标签**没有实测依据**（日报第 8091 行）⇒ 记 F 一处 Ⅲ 类口径过失"},
    {"item": "⑲ 第 17 件", "f_status": "confirmed_by_f",
     "f_anchor": "F 自己重取了 `t_start` / `cutoff` 两个锚"},
    {"item": "⑲ 第 18 件", "f_status": "not_measurable_by_f",
     "f_anchor": "会话记录层不在 F 的作用域；且 interim 令禁止再次回显凭据 ⇒ F 不测（不猜）"},
    {"item": "⑲ 第 19 件", "f_status": "confirmed_by_f_this_round",
     "f_anchor": ("窗口登记处实测：第 2 行 `declare`（w1 18:25:05–21:23:05，18:23:05）· 第 3 行 `yield`（18:37:56）· "
                  "第 4 行 `declare`（w2 18:38:56–23:37:56，18:37:56）⇒ §103 广播落笔时 w1 已 yield，"
                  "D 引的是过期窗口读数（D 自报成立）")},
    {"item": "⑲ 第 20 件", "f_status": "confirmed_by_f_this_round",
     "f_anchor": ("守望器首次 poll 的 `ts` = 18:53:40（PID 起跑时刻同值）> D 那次负读数的 as_of 18:50:03 "
                  "⇒ 负读数本身准确，但不足以支撑「掉棒」定性（D 自报成立）")},
]

FOUR_LINE_CLASSIFICATION: list[dict[str, Any]] = [
    {"line": "A2",
     "defects": [
         {"id": "D1", "class_per_d": "Ⅱ/Ⅲ（D 采纳 A2 的自报定性）",
          "what": "凭「看起来合理」的 `.config` 写回读、没核对已被验证的同源实现",
          "f_status": "registered（F 不重新定性）"},
         {"id": "D2", "class_per_d": "Ⅱ/Ⅲ（同上）", "what": "同族码错（见 decisions §103.2）",
          "f_status": "registered"},
         {"id": "D3", "class_per_d": "Ⅱ/Ⅲ（同上）", "what": "同族码错（见 decisions §103.2）",
          "f_status": "registered"},
         {"id": "D4-对象侧", "class_per_d": "**Ⅰ 类（D 另立）**",
          "what": ("A2 的 D4 只把它登记成「探针层的未受控初值」，但同一函数 `_init_env_to_state` "
                   "**也是 Step-1 的闭环初态写入路径** ⇒ 作用域窄了；D 把对象侧那一半另立为 Ⅰ 类"),
          "f_status": "confirmed_by_f_this_round",
          "f_anchor": ("F 实测：调用点 `PRE._init_env_to_state(...)` 在 Step-1 的 `reset()` 里；"
                       "A2 自己的 D4 文本写的是「探针层」；`step1_rollout_not_affected` 引的是 14 维口径的 "
                       "`maxdiff=0.0` ⇒ 证据作用域 ⊊ 结论作用域（字面可核）"),
          "cross_ref": "class_i_open_items_ruling104.items[0]"}],
     "merits": [
         {"what": "排队记账合规（`queued_waiting_for_idle`，且调 B2 工具自己的 `append_row()`、工具一个字节未改）",
          "f_status": "confirmed_by_f_this_round",
          "f_anchor": "窗口登记处逐行实测（第 5 行）+ `scripts/gpu_window_ledger.py` 身份未变"},
         {"what": "R2 的 RED 未事后改判（`does_not_change_r2_verdict=true`）",
          "f_status": "confirmed_by_f_this_round",
          "f_anchor": "A2 脚本里该键实测在盘；F 的六类登记里 R2 仍按 RED 保留、`blocking_for_step2=true`"}]},
    {"line": "C2",
     "defects": [{"id": "抗命类自报（§C2-4-①）", "class_per_d": "抗命类（C2 自报，D 采纳）",
                  "what": "D 的停令落盘（17:26:24）之后仍把搬迁批次执行完（26 搬 / 3 留 / 0 失败）",
                  "f_status": "registered（C2 自报；处置权在 D：追认甲 / 回滚乙，C2 未自选）"}],
     "merits": [{"what": "元缺陷「审计器识别模式比对象空间窄」被 D 在 A2 侧独立印证（同族跨线成立）",
                 "f_status": "registered",
                 "f_anchor": "F 的 ⑲ 复核件里 #13–#17 同族读数；本轮 A2 的 D4 作用域窄 = 同一型"}]},
    {"line": "E",
     "defects": [{"id": "Ⅰ 类凭据回显自报", "class_per_d": "Ⅰ 类（E 自报，D 采纳）",
                  "what": "api_key 回显进持久会话记录（裁定 102.7-⑤；待用户第 ① 项 = 轮换）",
                  "f_status": "not_measurable_by_f",
                  "f_anchor": "会话记录层不在 F 作用域 + interim 令禁止再次回显凭据 ⇒ F 不测（⑲ 第 18 件同因）"}],
     "merits": [{"what": "裁定 96.1-③ 的假阳性修法在真实排队场景验过（`card_busy()` 被守望器与登记处复用）",
                 "f_status": "confirmed_by_f_this_round",
                 "f_anchor": ("守望器的互斥判据只转发 E 的 `card_busy()`（不重造）；"
                              "18:28:08 那次拒起跑与 18:58:19 那条排队记账都出自同一把尺 ⇒ 真实场景已验")}]},
    {"line": "D",
     "defects": [{"id": "⑲ 第 14–20 件", "class_per_d": "D 自报（第 19 = 引过期窗口读数；第 20 = 一次负读数差点被定性成「掉棒」）",
                  "what": "见 `defect19_items_f_status` 的逐件锚",
                  "f_status": "per_item（#14–#17 confirmed · #18 not_measurable_by_f · #19/#20 confirmed_by_f_this_round）"}],
     "merits": [{"what": "⑳ 族自报机制本身在跑（D 连续自报且逐件给锚）",
                 "f_status": "registered（F 不记功、只登记 D 的自报与 F 的复核状态）"}]},
]


def build_classification_ruling104() -> dict[str, Any]:
    """D→F 补单·四-③：四笔记功/缺陷的**归类**登记（记功与缺陷并存、不互相抵消）。
    F 只做两件事：抄 D 的归类 + 附 F 自己的复核状态与实测锚。**F 不定性、不改极性、不记功。**"""
    ledger_rows = _window_ledger_rows()
    watcher = _watcher_anchors()
    d19 = []
    for row in DEFECT19_F_STATUS:
        anchor: Any = row["f_anchor"]
        if row["item"].endswith("第 19 件"):
            anchor = {"f_anchor_text": row["f_anchor"], "window_ledger_rows": ledger_rows,
                      "window_ledger_identity": _identity(GPU_LEDGER, "⑲ 第 19 件的实测锚（窗口账）")}
        if row["item"].endswith("第 20 件"):
            anchor = {"f_anchor_text": row["f_anchor"], "watcher": watcher}
        d19.append({**row, "f_anchor": anchor})
    return {"registry_block": "classification_ruling104",
            "as_of": _now(),
            "lives_inside": "TRIGGER_REGISTRY.json（既有登记处；补单·四-①：不新增登记处/指标）",
            "authority": ["裁定 104.1（追认与记功，不新增裁定）", "裁定 104.8（D 自报 ⑲ 第 19、20 件）",
                          "D→F 补单·四-③（归类四笔；记功与缺陷并存、不互相抵消）"],
            "non_cancellation_note": ("记功与缺陷**不互相抵消**（补单·四-③ 逐字）：F 不把任何一件记功"
                                      "用来降低同线缺陷的类别，也不把缺陷用来抹掉记功。"),
            "f_role_boundary": "F 只登记 D 的归类 + 附 F 的复核状态；**不定性、不改极性、不代 D 记功或销账**",
            "four_line_classification": FOUR_LINE_CLASSIFICATION,
            "defect19_items_f_status": d19,
            "f_prior_recheck_artifact": _identity(F_DEFECT19_ARTIFACT, "F 上一轮对 ⑲ #13–#18 的独立复核件（原字节保留、不追改）"),
            "d_self_limit_note": ("D 的自我限产（100.9 / 101.1 自缚四条）本轮由 `measure_d_self_limit()` 实测，"
                                  "轮次窗已扩到 r103 / r103.6 / r104；超限即由 F 出红。"),
            "no_new_metric_created": True,
            "capability_claim": None, "policy_executed": False, "gpu_used": False}


def _leg_reading(rel: str, leg: str | None) -> dict[str, Any]:
    """从 A2 的判词件里取一条腿的实物读数（只读、只取判词字段，不判对错）。"""
    path = ROOT / rel
    if not path.exists():
        return {"anchor": rel, "measurement_status": NOT_MEASURED, "reason": "锚对象不在盘（不是「没有」）"}
    if path.suffix != ".json":
        text = _read(path) or ""
        return {"anchor": rel, "measurement_status": "measured", "anchor_kind": "code_anchor",
                "identity": _identity(path, "六类阻塞项的代码锚（只核存在性与词法命中，不 import 执行）"),
                "token": leg, "token_hits": (text.count(leg) if leg else None),
                "caliber": "命中 = 字节子串；**不是**语义判定（F 不判他线代码对错）"}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"anchor": rel, "measurement_status": NOT_MEASURED, "reason": f"{type(exc).__name__}: {exc}"}
    out: dict[str, Any] = {"anchor": rel, "identity": _identity(path, "六类阻塞项的实测锚（裁定 101.2 的对应表）"),
                           "as_of_in_artifact": data.get("as_of"),
                           "gpu_used": data.get("gpu_used"), "policy_executed": data.get("policy_executed"),
                           "capability_claim": data.get("capability_claim")}
    if leg is None:
        keys = [k for k in ("stages_requested", "overall_verdict", "heldout", "split", "episode")
                if k in json.dumps(data, ensure_ascii=False)]
        out.update(measurement_status="measured", object_level_fields_present=keys)
        return out
    legs = data.get("legs") or {}
    row = legs.get(leg) if isinstance(legs, dict) else None
    if not isinstance(row, dict):
        return {**out, "measurement_status": NOT_MEASURED, "leg": leg, "reason": f"{leg} 不在判词件的 legs 里"}
    return {**out, "measurement_status": "measured", "leg": leg,
            "verdict": row.get("verdict"), "blocking": row.get("blocking"),
            "red_codes": row.get("red_codes"),
            "key_measured_fields": {k: row.get(k) for k in list(row.keys())
                                    if k in ("worst_state_maxdiff", "neq", "frac_aligned_is_winner",
                                             "frac_high_pass", "min_margin_ratio_vs_best_shifted",
                                             "n_low_discrimination", "gripper_polarity", "n_discrete_values",
                                             "frac_below_minus1", "frac_above_plus1")}}


def build_blocking_class_registry() -> dict[str, Any]:
    """裁定 101.1 的落地：只登记六类阻塞项（含实测锚 + 消费方），其余登记不阻塞。"""
    classes = []
    for spec in SIX_BLOCKING_CLASSES:
        readings = [_leg_reading(rel, leg) for (_label, rel, leg) in spec["anchors"]]
        measured = [r for r in readings if r.get("measurement_status") == "measured"]
        classes.append({
            "class_id": spec["class_id"], "name_verbatim": spec["name_verbatim"],
            "blocking": True, "blocking_scope": "六类之内 = 阻塞（裁定 101.1）；六类之外 = 登记不阻塞",
            "step1_column": spec["step1_column"], "consumer": spec["consumer"],
            "anchor_readings": [{"label": lab, **rd} for (lab, _rel, _leg), rd
                                in zip(spec["anchors"], readings)],
            "measurement_status": ("measured" if len(measured) == len(readings)
                                   else ("partially_measured" if measured else NOT_MEASURED)),
            "n_anchors": len(readings), "n_anchors_measured": len(measured),
            "step1_reading_status": NOT_MEASURED,
            "step1_reading_reason": "Step 1 的 train/rollout 结果尚未落盘 ⇒ 该类的**闭环侧**读数测不到（不猜）",
        })
    # 裁定 104.2：新登记的 Ⅰ 类缺陷归第 ①/⑥ 两类 ⇒ 在那两类下面挂交叉引用（不新建登记处）
    r104_items = build_class_i_open_items_ruling104()
    for cls in classes:
        cls["open_items_ruling104"] = [it["item_id"] for it in r104_items["items"]
                                       if cls["class_id"] in it["class_ids"]]
    # L12 的红→绿链：D 明令「不要删，标 explained_by = run4 / T8」（补单六 §三-2）
    l12 = {"item": "L12_action_time_alignment", "chain_not_deleted": True,
           "explained_by": "run4 / T8（裁定 100.1-①：D 用 run3 的严判据独立复算 run4 的 22 个 high-discrimination 行，例外 0）",
           "authority": "裁定 99.2（红 + 停卡）→ 100.1（撤销停卡、采信 GREEN，但根据不是「漂移已排除」）→ 102.6（非阻塞，并入 Step 1 的 ③④ 两列）",
           "run3_reading": _leg_reading(PREALIGN_RUN3, "L12_action_time_alignment"),
           "run4_reading": _leg_reading(PREALIGN_RUN4, "L12_action_time_alignment"),
           "criteria_identity_sidecar": [str(p.relative_to(ROOT)) for p in
                                         _glob_bounded("runs/vla", "a2_step1_prealign_20260930_run*/CRITERIA_IDENTITY.json", 2)],
           "open_account": "OPEN-L12-CRITERIA-DRIFT（改前字节不可复得；裁定 100.3-（a）记 A2 一处缺陷，102.6 定为非阻塞）"}
    # R1/R2：裁定 101.2 撤销了「R1+R2 先做完才可申报窗口」⇒ 不再是上卡前探针，改为 Step 1 的产出列
    r1r2_runs = _glob_bounded("runs/vla", R1R2_GLOB, 1)
    r1r2 = {"item": "R1（高运动量帧 off-by-one）/ R2（夹爪维转变点时序）",
            "status_change": ("裁定 100.1-（b）曾把它们定为第 2 步的阻塞前置 ⇒ **裁定 101.2 撤销**："
                              "R2 = Step 1 产出④（夹爪转变帧误差）、R1 = 验收标准 ③ 的取证；不再是上卡前独立探针"),
            "blocking_now": False, "blocking_note": "按 101.2 并入 Step 1 的产出列；仍属六类里的 ①③ 两类 ⇒ 阻塞性由那两类的验收标准承载",
            "run_dirs_found": [str(p.relative_to(ROOT)) for p in r1r2_runs],
            "n_run_dirs": len(r1r2_runs),
            "measurement_status": "measured" if r1r2_runs else NOT_MEASURED,
            "as_of": _now()}
    return {"registry_block": "blocking_classes_ruling101", "as_of": _now(),
            "authority": ["裁定 101.1（只保留六类为阻塞项，其它一律先登记、不阻塞训练）",
                          "裁定 101.2（六类与 Step 1 的对应表，逐字采纳用户原文）",
                          "D→F 待命令（17:2x）：F 只维持六类阻塞项登记，停覆盖率指标",
                          "补单六 §三-2（L12 不删、标 explained_by；R1/R2 登进台账）",
                          "裁定 104.2–104.3 + D→F 补单·四-②（本轮新增一条 Ⅰ 类缺陷的登记）"],
            "n_classes": len(classes), "classes": classes,
            "l12_chain": l12, "r1_r2": r1r2,
            "class_i_open_items_ruling104": r104_items,
            "non_blocking_registered": NON_BLOCKING_REGISTERED,
            "capability_claim": None, "policy_executed": False, "gpu_used": False,
            "caliber_note": "本块只登记「哪六类阻塞、锚在哪、谁消费」；F 不判 Step 1 通过与否（那归 D 的里程碑审查）"}


def step1_acceptance_tracker() -> dict[str, Any]:
    """裁定 102.6：Step 1 里程碑审查时 F 核的是「四条验收标准逐条有没有实测读数支撑」。
    本节只做**读数在不在**的登记，不判通过（F 不定标、不判他线判词）。"""
    criteria = [
        ("①", "训练集动作误差明显下降", ["train_det_loss_final_over_step0", "plateau_reached"]),
        ("②", "至少一条正向和一条反向轨迹能从示范初态闭环复现", ["geometric_success", "max_stage", "success_rate"]),
        ("③", "动作和夹爪时间对齐没有未解释的系统性偏移", ["R1", "systematic_offset", "frac_aligned_is_winner"]),
        ("④", "失败时能定位到具体阶段", ["failed_stage", "stage"]),
    ]
    step1_files = _glob_bounded("runs/vla", STEP1_RUN_GLOB, 2)
    # 口径（F 声明、可被 D 纠正）：**预登记件里的词法命中不算读数**。只有结果/判词件
    # （`*SUMMARY*` / `*VERDICT*` / `*REPORT*` / `*RESULT*`）里的命中才记 partially_measured。
    result_files = [f for f in step1_files if f.suffix == ".json"
                    and any(k in f.name.upper() for k in ("SUMMARY", "VERDICT", "REPORT", "RESULT"))]
    stages_seen: list[Any] = []
    for f in result_files[-4:]:
        try:
            stages_seen.append(json.loads(f.read_text(encoding="utf-8", errors="ignore")).get("stages_requested"))
        except (OSError, json.JSONDecodeError):
            stages_seen.append(None)
    flat_stages = {str(x) for row in stages_seen if isinstance(row, list) for x in row}
    train_or_rollout_done = bool(flat_stages & {"train", "rollout", "report"})
    prereg_files = [f for f in step1_files if f.suffix == ".json" and f not in result_files]
    blob = "".join((_read(f) or "") for f in result_files[-8:])
    prereg_blob = "".join((_read(f) or "") for f in prereg_files[-8:])
    rows = []
    for cid, text, tokens in criteria:
        hits = sorted({t for t in tokens if t in blob})
        pre_hits = sorted({t for t in tokens if t in prereg_blob})
        rows.append({"criterion_id": cid, "criterion_verbatim": text,
                     "reading_tokens_in_result_artifacts": hits,
                     "lexical_hits_in_preregistration_only": pre_hits,
                     "measurement_status": ("partially_measured" if (hits and train_or_rollout_done) else NOT_MEASURED),
                     "reason": (None if (hits and train_or_rollout_done) else
                                "结果件只到 %s 阶段（`stages_requested`），train/rollout 的读数尚未产生 ⇒ 不猜；"
                                "**词法命中不算读数**（预登记件里出现同名词同样不算）" % (sorted(flat_stages) or ["无"])),
                     "capability_claim_forbidden": "裁定 46 + 101.3：本条即便有读数，也只指判词，不指能力"})
    return {"artifact_block": "step1_acceptance_tracker", "as_of": _now(),
            "authority": ["裁定 101.2（四条验收标准，逐字采纳用户原文）",
                          "裁定 102.2（四处判据冲突的裁定：②是出场判据、③的取证=R1、④=R2）",
                          "D→F 待命令（17:2x）：F 核「四条验收标准逐条有没有实测读数支撑」+ 有没有把 GREEN/admitted 写成能力声明"],
            "step1_artifacts_found": [str(p.relative_to(ROOT)) for p in step1_files][-12:],
            "result_artifacts_counted": [str(p.relative_to(ROOT)) for p in result_files],
            "preregistration_artifacts_excluded_from_readings": [str(p.relative_to(ROOT)) for p in prereg_files],
            "n_step1_artifacts": len(step1_files),
            "stages_requested_seen_in_result_artifacts": sorted(flat_stages),
            "train_or_rollout_done": train_or_rollout_done,
            "stage_gate_caliber": ("裁定 102.1：A2 已交的三阶段 = admission / prereg / cache，全在 CPU、零上卡、"
                                   "零 policy 执行 ⇒ 四条验收标准的读数**按构造还没产生**；F 不因词法命中而记 measured。"
                                   "**裁定 103.2 追平**：`probe` 阶段已 GREEN（模型建得起来、stats 注入逐位相同、"
                                   "batch 选定），但 D 明示它**不是任何能力表述** ⇒ 四条验收标准的读数仍按构造未产生；"
                                   "`train,rollout` 在窗口 w2 内排队等卡（登记处第 5 行 `queued_waiting_for_idle`）"),
            "criteria": rows,
            "authoritative_stage_wording": ("裁定 101.3：对外阶段表述只用那一句（params `stage_judgment_authoritative_wording_rev27`）；"
                                           "F 的文书同样只用它"),
            "measurement_status": "measured"}


def rev_declared_rounds(summary: str, head_chars: int = 160) -> list[str]:
    """从 rev 条目**自己写的** summary 头部解析它声明的裁定号 ⇒ 轮次标签。

    这是归属的**主口径**：`before_rev31` 与 `decisions…before_r105` 在同一秒（19:31:05）落盘，
    用 mtime 窗归属会把 rev31 算进 r104 ⇒ 对 D 出假红。rev 自己写着「裁定 105 落地」，
    那才是权威归属。解不出裁定号 ⇒ 返回 []（该条走 not_measured，不猜、也不出红）。
    """
    runs = re.findall(r"裁定\s*(\d{2,3}(?:\.\d+)?(?:\s*[\/、,，]\s*\d{2,3}(?:\.\d+)?)*)",
                      (summary or "")[:head_chars])
    out: list[str] = []
    for run in runs:
        for num in re.split(r"[\/、,，]", run):
            num = num.strip()
            if re.fullmatch(r"\d{2,3}(?:\.\d+)?", num) and f"r{num}" not in out:
                out.append(f"r{num}")
    return out


def rev_write_events(img_mtimes: list[tuple[str, float]], now_name: str, now_mtime: float,
                     tolerance_s: float = 120.0) -> list[dict[str, Any]]:
    """把 params 的写入事件数出来：**一份前像 = 一次写入**（D 的纪律是写前 `cp -p`）。

    `params` 现值不额外计数 —— 它就是最后一份前像那一次写入的结果；**只有**当现值比最后一份
    前像晚出 `tolerance_s` 以上（⇒ 那次写入没留前像）才算另一次事件。这样既不会把
    「前像 + 现值」数成两次（对 D 的假红），也不会漏掉「没留前像的写入」。
    """
    events = [{"source": name, "mtime_epoch": mt,
               "mtime": datetime.fromtimestamp(mt).astimezone().isoformat(),
               "rev_parsed": (re.search(r"before_rev(\d+)", name).group(1)
                              if re.search(r"before_rev(\d+)", name) else None)}
              for name, mt in img_mtimes]
    if events:
        latest = max(mt for _n, mt in img_mtimes)
        unpaired = (now_mtime - latest) > tolerance_s
    else:
        unpaired = True
    if unpaired:
        events.append({"source": f"{now_name}（未配对 ⇒ 记为一次没留前像的写入）", "mtime_epoch": now_mtime,
                       "mtime": datetime.fromtimestamp(now_mtime).astimezone().isoformat(), "rev_parsed": None})
    return sorted(events, key=lambda e: e["mtime_epoch"])


def measure_d_self_limit() -> dict[str, Any]:
    """裁定 100.9 / 101.1 自缚四条：F 可核、**超限即由 F 出红**。全部用前像与现值实测，不手打。"""
    bi = ROOT / "runs/vla/d_ruling_round_20260930_1205/before_images"
    dec = ROOT / DEC_PATH
    rounds_spec = [("r101", "decisions_20260929.md.before_r101", "decisions_20260929.md.before_r102"),
                   ("r102", "decisions_20260929.md.before_r102", "decisions_20260929.md.before_r102_7"),
                   ("r102.7", "decisions_20260929.md.before_r102_7", "decisions_20260929.md.before_r103"),
                   ("r103", "decisions_20260929.md.before_r103", "decisions_20260929.md.before_r103_6"),
                   ("r103.6", "decisions_20260929.md.before_r103_6", "decisions_20260929.md.before_r104"),
                   ("r104", "decisions_20260929.md.before_r104", "decisions_20260929.md.before_r104_9"),
                   ("r104.9", "decisions_20260929.md.before_r104_9", "decisions_20260929.md.before_r105"),
                   ("r105", "decisions_20260929.md.before_r105", None)]
    # 口径名探测器：**必须**在「口径 / caliber」的语境里才算（否则会把它实测到的字段名
    # `wall_ms_per_ctrl_step`、params 键名 `stage_judgment_authoritative_wording_rev27` 之类
    # 当成"新口径" ⇒ 对 D 出假红，那正是缺陷类 ⑲/⑧ 的形状）。带两向自检。
    cal_rx = re.compile(r"(?:口径|caliber)[^。\n]{0,60}?`([a-z][a-z0-9]*(?:_[a-z0-9]+){2,})`")

    def _caliber_names(text: str) -> set[str]:
        return set(cal_rx.findall(text))

    pos_ctrl = "- **新的 Ⅰ 类口径 `positive_control_caliber_name`**：这是自检用的合成行（与真口径同形）"
    neg_ctrl = "- 实测 `wall_ms_per_ctrl_step` 与 `stage_judgment_authoritative_wording_rev27` 两个字段名"
    cal_self_check = {"positive_control_detected": sorted(_caliber_names(pos_ctrl)),
                      "negative_control_detected": sorted(_caliber_names(neg_ctrl)),
                      "filter_non_vacuous": bool(_caliber_names(pos_ctrl)) and not _caliber_names(neg_ctrl),
                      "consequence_if_false": "两向自检不过 ⇒ 本条一律读 not_measured，**不许**据此对 D 出红"}
    rounds = []
    for name, before_name, after_name in rounds_spec:
        before = bi / before_name
        after = (bi / after_name) if after_name else dec
        if not before.exists() or not after.exists():
            rounds.append({"round": name, "measurement_status": NOT_MEASURED,
                           "reason": "前像或现值不在盘 ⇒ 不猜"})
            continue
        b_txt, a_txt = _read(before) or "", _read(after) or ""
        b_lines, a_lines = b_txt.count("\n"), a_txt.count("\n")
        added = a_txt[len(b_txt):] if a_txt.startswith(b_txt[:2000]) else a_txt
        new_cal = sorted(_caliber_names(added) - _caliber_names(b_txt))
        cal_ctx = []
        for m in cal_rx.finditer(added):
            if m.group(1) in new_cal:
                ctx = added[max(0, m.start() - 80):m.end() + 50].replace("\n", " ")
                cal_ctx.append({"name": m.group(1), "context": ctx[:230],
                                "d_says_not_a_new_caliber": bool(re.search(r"不新开条|沿用|不是新口径|不新增口径", ctx)),
                                "f_note": ("D 在这句里明写「不新开条 / 沿用」⇒ F 记为**命名形态命中**（尺子把字段名当口径名），"
                                           "**计数照报不改**（F 不代 D 判某条是不是口径），请 D 在里程碑审查时自己核")
                                          if re.search(r"不新开条|沿用|不是新口径|不新增口径", ctx) else None})
        rounds.append({
            "round": name, "measurement_status": "measured",
            "before_image": _identity(before, f"{name} 轮的裁定书前像（`cp -p` 保留 mtime）"),
            "after_object": _identity(after, f"{name} 轮的裁定书现值/下一轮前像"),
            "decisions_line_delta": a_lines - b_lines,
            "decisions_limit": 60, "decisions_within_limit": (a_lines - b_lines) <= 60,
            "new_caliber_names": new_cal, "n_new_caliber_names": len(new_cal),
            "new_caliber_contexts": cal_ctx,
            "caliber_limit": 2, "caliber_within_limit": len(new_cal) <= 2,
            "caliber_class_check": ("not_measured（F 只数名字；某条是不是 Ⅰ 类由 D 定，F 不代判）"
                                    if new_cal else "not_applicable（本轮 0 条新口径名）"),
            "caliber_detector_self_check": cal_self_check,
            "caliber_detector_usable": cal_self_check["filter_non_vacuous"],
            "round_window": {"start": datetime.fromtimestamp(before.stat().st_mtime).astimezone().isoformat(),
                             "end": datetime.fromtimestamp(after.stat().st_mtime).astimezone().isoformat()},
        })
    # 日报 §D 段 ≤20 行（记法采 §100.11-①：标题行号 → 末行行号）
    daily = (_read(ROOT / DAILY_PATH) or "").splitlines()
    heads = [i for i, l in enumerate(daily) if l.startswith("## §D")]
    segs = []
    for idx, start in enumerate(heads):
        end = next((j for j in range(start + 1, len(daily)) if daily[j].startswith("## ")), len(daily))
        segs.append({"section": daily[start][3:40], "title_line_no": start + 1, "last_line_no": end,
                     "n_lines": end - start, "limit": 20, "within_limit": (end - start) <= 20})
    d_segs_since_r100 = [s for s in segs if s["title_line_no"] >= 8890]
    # 参数表：每轮最多 +1 个 rev（用 revision_history 的 as_of 与前像 mtime 对时）
    params_now = ROOT / "work/project_parameters.json"
    rev_rows: list[dict[str, Any]] = []
    rev_rows_full: list[dict[str, Any]] = []
    try:
        pdata = json.loads(params_now.read_text(encoding="utf-8", errors="ignore"))
        for entry in pdata.get("revision_history") or []:
            if isinstance(entry, dict):
                rev_rows.append({"rev": entry.get("rev"),
                                 "as_of": str(entry.get("as_of") or entry.get("date") or entry.get("when") or "")[:32]})
                rev_rows_full.append(entry)
    except (OSError, json.JSONDecodeError):
        pass
    # 每轮 rev 数用**前像 mtime 的时间窗**实测（`revision_history` 的 as_of 有两条是空的 ⇒ 不能只靠它）
    param_images = sorted((bi).glob("project_parameters.json.before_rev*"), key=lambda q: q.stat().st_mtime)
    windows: list[tuple[str, float, float]] = []
    for r in rounds:
        w = r.get("round_window") or {}
        if w.get("start") and w.get("end"):
            windows.append((r["round"],
                            datetime.fromisoformat(w["start"]).timestamp(),
                            datetime.fromisoformat(w["end"]).timestamp()))
    # 一个 rev 的写入会同时留下两个物件：前像 `before_revN`（写之前 `cp -p` 的那一份）
    # 与写后的 params 现值。按**文件**数就会把每一轮的最后一次写入数成两次 ⇒ 那是 F 自己的
    # 假红（缺陷类 ⑲ 同族：尺子比对象空间窄/宽）。⇒ 按 **rev 号**去重，一个 rev = 一次写入。
    current_rev_label = f"rev{rev_rows[-1]['rev']}" if rev_rows else "rev_unknown"
    img_mtimes = [(q.name, q.stat().st_mtime) for q in param_images]
    rev_events = rev_write_events(img_mtimes, params_now.name, params_now.stat().st_mtime)
    rev_events_raw = rev_events
    # 两向自检（裁定 93.8）：两份前像同窗必须数成 2（能出红）；一份前像 + 37 s 后的现值必须数成 1（不放假红）。
    _pos = rev_write_events([("project_parameters.json.before_rev98", 1000.0),
                             ("project_parameters.json.before_rev99", 1010.0)], "project_parameters.json", 1010.5)
    _neg = rev_write_events([("project_parameters.json.before_rev99", 1000.0)], "project_parameters.json", 1037.0)
    _neg_far = rev_write_events([("project_parameters.json.before_rev99", 1000.0)], "project_parameters.json", 1400.0)
    rev_dedup_self_check = {"two_before_images_same_window_count_as": len(_pos),
                            "one_before_image_plus_now_37s_count_as": len(_neg),
                            "one_before_image_plus_now_400s_count_as": len(_neg_far),
                            "filter_non_vacuous": (len(_pos) == 2 and len(_neg) == 1 and len(_neg_far) == 2),
                            "consequence_if_false": ("两向自检不过 ⇒ `params_rev_per_round_le_1` 一律读 not_measured，"
                                                     "**不许**据此对 D 出红"),
                            "self_caught_defect": ("第一版按「前像 + 现值」两个物件计数 ⇒ r104 被数成 2 次写入、"
                                                   "对 D 出了一次假红（F-31 not_delivered）；第二版按 rev 号去重，"
                                                   "但 `before_rev23_fix1` 这种带后缀的名字解不出 rev 号、"
                                                   "回退成 `current_rev_label` ⇒ 把 13:31 的旧前像当成 rev30、"
                                                   "反而把 r104 数成 0。现版改为「一份前像 = 一次写入」，"
                                                   "不再依赖名字里的 rev 号（F 自报，缺陷类 ⑲ 同族：尺子比对象空间窄）")}
    revs_per_round: dict[str, list[str]] = {name: [] for name, _s, _e in windows}
    for ev in rev_events:
        for name, w_start, w_end in windows:
            if w_start <= ev["mtime_epoch"] <= w_end + 1:
                revs_per_round[name].append(ev["source"].replace("project_parameters.json.", ""))
                break
    # ── 主口径：rev 自己声明的裁定号 → 轮次 ──
    rev_declared: list[dict[str, Any]] = []
    for entry in rev_rows_full:
        declared = rev_declared_rounds(str(entry.get("summary") or ""))
        rev_declared.append({"rev": entry.get("rev"), "declared_rounds": declared,
                             "in_scope_rounds": [r for r in declared if r in revs_per_round],
                             "identities_as_of": entry.get("identities_as_of"),
                             "before_image": entry.get("before_image"),
                             "measurement_status": "measured" if declared else NOT_MEASURED})
    declared_per_round: dict[str, list[str]] = {name: [] for name, _s, _e in windows}
    for row in rev_declared:
        for r in row["in_scope_rounds"]:
            declared_per_round[r].append(f"rev{row['rev']}")
    _pos_ctrl = rev_declared_rounds("**裁定 104 落地（指针式，正文 = decisions §104）**：① 追认…")
    _two_ctrl = rev_declared_rounds("**裁定 103 / 103.6 落地（指针式）**：① 主线不变…")
    _neg_ctrl = rev_declared_rounds("本机实测若干数字与前像身份，正文不含任何裁定编号。")
    rev_attribution_self_check = {
        "positive_control_single": _pos_ctrl, "positive_control_two_rounds": _two_ctrl,
        "negative_control": _neg_ctrl,
        "filter_non_vacuous": (_pos_ctrl == ["r104"] and _two_ctrl == ["r103", "r103.6"] and _neg_ctrl == []),
        "consequence_if_false": ("两向自检不过 ⇒ `params_rev_per_round_le_1` 一律读 not_measured，**不许**据此对 D 出红"),
        "self_caught_defect": ("mtime 窗口口径在 r104/r105 的边界上把 rev31（`before_rev31` 与 `before_r105` 同为 "
                               "19:31:05）算进 r104 ⇒ F 第二次对 D 出假红。改以 rev 自己声明的裁定号为主口径，"
                               "mtime 窗只作旁证并原样报出（F 自报，缺陷类 ⑲ 同族：尺子的分辨率低于对象）")}
    handoffs = []
    for line in ("a2", "b2", "c2", "e", "f"):
        cur = ROOT / f"rl_harness_supervision/d_handoff_to_{line}_20260930.md"
        imgs = sorted(bi.glob(f"d_handoff_to_{line}_20260930.md.before_*"), key=lambda q: q.stat().st_mtime)
        if not cur.exists():
            continue
        cur_ln = (_read(cur) or "").count("\n")
        latest = imgs[-1] if imgs else None
        latest_ln = (_read(latest) or "").count("\n") if latest else None
        r102 = bi / f"d_handoff_to_{line}_20260930.md.before_r102"
        r102_ln = (_read(r102) or "").count("\n") if r102.exists() else None
        handoffs.append({"line": line, "n_lines_now": cur_ln,
                         "this_round_before_image": (latest.name if latest else None),
                         "this_round_before_image_mtime": (datetime.fromtimestamp(latest.stat().st_mtime)
                                                           .astimezone().isoformat() if latest else None),
                         "n_lines_this_round_before": latest_ln,
                         "delta_this_round": (cur_ln - latest_ln) if latest_ln is not None else None,
                         "n_lines_before_r102": r102_ln,
                         "delta_since_r102_cumulative": (cur_ln - r102_ln) if r102_ln is not None else None,
                         "delta_caliber": ("本轮增量 = 现值 − **最近一份前像**（按 mtime 取，工具实测）；"
                                           "旧版拿 `before_r102` 当基准 ⇒ 跨了 r102.7/r103/r103.6/r104 四轮，"
                                           "那个数不是「本轮」，现另列 `delta_since_r102_cumulative` 保留"),
                         "limit_reading_A_increment": 40, "limit_reading_B_total": 40,
                         "within_limit_reading_A": (None if latest_ln is None else (cur_ln - latest_ln) <= 40),
                         "within_limit_reading_B": cur_ln <= 40})
    ident_tables = [p for p in (ROOT / "runs/vla/d_ruling_round_20260930_1205").glob("D_IDENTITY_TABLE_*.json")]
    r101_start = (bi / "decisions_20260929.md.before_r101").stat().st_mtime if (bi / "decisions_20260929.md.before_r101").exists() else None
    ident_after = [str(p.name) for p in ident_tables if r101_start and p.stat().st_mtime >= r101_start]
    limits = {
        "decisions_per_round_le_60": {"measured": [(r["round"], r.get("decisions_line_delta")) for r in rounds],
                                      "exceeded": [r["round"] for r in rounds if r.get("decisions_within_limit") is False]},
        "daily_d_section_le_20": {"measured": [(s["section"], s["n_lines"]) for s in d_segs_since_r100],
                                  "exceeded": [s["section"] for s in d_segs_since_r100 if not s["within_limit"]]},
        "params_rev_per_round_le_1": {"n_rev_entries_total": len(rev_rows), "last_revs": rev_rows[-4:],
                                      "rev_writes_per_round_by_before_image_mtime": revs_per_round,
                                      "counting_unit": ("params 前像的份数（一份前像 = 一次写入）；"
                                                          "现值只在「比最后一份前像晚 >120 s ⇒ 那次写入没留前像」时才另计一次"),
                                      "rev_events_raw": rev_events_raw,
                                      "rev_events_counted": rev_events,
                                      "current_rev_label": current_rev_label,
                                      "dedup_detector_self_check": rev_dedup_self_check,
                                      "boundary_caveat": ("轮次边界用**裁定书前像的 mtime**；D 通常在同一轮的 decisions 之后才写 params，"
                                                          "⇒ 某一轮的 params 写入可能落进下一轮的窗口（例如 rev28 的落盘时刻在 "
                                                          "r103 窗口内，而它语义上属 r102.7）。F 只报窗口内的计数与逐件原始时刻，"
                                                          "**不代 D 重新归属**；若因此出现 exceeded，F 会把这条 caveat 一起报给 D。"),
                                      "n_rev_writes_per_round_by_mtime_window_secondary": {
                                          k: len(v) for k, v in revs_per_round.items()},
                                      "revs_per_round_by_mtime_window_secondary": revs_per_round,
                                      "attribution_primary_caliber": ("rev 条目自己声明的裁定号（`revision_history[].summary` 头部）；"
                                                                      "mtime 窗只作旁证 —— 它在轮次边界那一秒会把下一轮的 rev 算进上一轮"),
                                      "rev_declared_attribution": rev_declared,
                                      "attribution_detector_self_check": rev_attribution_self_check,
                                      "n_revs_per_round": {k: len(v) for k, v in declared_per_round.items()},
                                      "revs_per_round": declared_per_round,
                                      "exceeded_rounds": ([k for k, v in declared_per_round.items() if len(v) > 1]
                                                          if rev_attribution_self_check["filter_non_vacuous"] else []),
                                      "caliber": ("每轮 ≤1 个 rev；轮次边界用**裁定书前像的 mtime** 取（工具实测，不手打）；"
                                                  "rev 的落盘时刻用 params 前像的 mtime 取"),
                                      "measurement_status": (("measured" if rev_rows else NOT_MEASURED)
                                                               if (rev_dedup_self_check["filter_non_vacuous"]
                                                                   and rev_attribution_self_check["filter_non_vacuous"])
                                                               else NOT_MEASURED),
                                      "measurement_status_reason": ("两个探测器（写入事件去重 / 轮次归属）的两向自检都过才读 measured；"
                                                                   "任一不过 ⇒ not_measured 且**不许**对 D 出红（裁定 93.8）")},
        "new_calibers_per_round_le_2_and_class1": {"measured": [(r["round"], r.get("new_caliber_names")) for r in rounds],
                                                   "exceeded": [r["round"] for r in rounds if r.get("caliber_within_limit") is False],
                                                   "unnamed_rules_note": ("§102.5-① / §102.7-⑤ 的 interim 令是**无名规则**，"
                                                                          "不进 snake_case 计数 ⇒ F 记一处口径形态问题：无名规则同样扩张治理面，"
                                                                          "却绕过了本条的计数口径（登记，不判）")},
        "handoff_per_line_per_round": {"measured": handoffs,
                                       "ambiguity_registered": ("「每份 ≤40 行」有两种读法：A = 本轮增量 ≤40、B = 全文 ≤40。"
                                                                "F 两种都报，不代 D 选（现状：按 A 全过、按 B 五份都超）"),
                                       "exceeded_reading_A": [h["line"] for h in handoffs if h["within_limit_reading_A"] is False],
                                       "exceeded_reading_B": [h["line"] for h in handoffs if not h["within_limit_reading_B"]]},
        "identity_selfcheck_per_milestone": {"n_identity_tables_after_r101": len(ident_after), "files": ident_after,
                                             "authority": "裁定 101.1-(c)：本轮 v7 收尾一次，下一次在 Step 1 的里程碑审查",
                                             "within_limit": len(ident_after) <= 1},
    }
    # 探测器不可用 ⇒ 该维度记 not_measured，**不**参与出红（不猜，也不放假红）
    if not cal_self_check["filter_non_vacuous"]:
        limits["new_calibers_per_round_le_2_and_class1"]["exceeded"] = []
        limits["new_calibers_per_round_le_2_and_class1"]["measurement_status"] = NOT_MEASURED
    rev_over = limits["params_rev_per_round_le_1"].get("exceeded_rounds") or []
    if rev_over:
        limits["params_rev_per_round_le_1"]["exceeded"] = rev_over
    # 去重探测器自检不过 ⇒ 本维度 not_measured，**不参与出红**（同 `cal_self_check` 的处理）
    if (limits["params_rev_per_round_le_1"].get("measurement_status") != "measured"
            or not rev_attribution_self_check["filter_non_vacuous"]):
        limits["params_rev_per_round_le_1"]["exceeded"] = []
        limits["params_rev_per_round_le_1"]["exceeded_rounds"] = []
    exceeded = {k: v.get("exceeded") for k, v in limits.items() if v.get("exceeded")}
    over = bool(exceeded) or (limits["identity_selfcheck_per_milestone"]["within_limit"] is False)
    return {"artifact_block": "d_self_limit_compliance", "as_of": _now(),
            "authority": ["裁定 100.9（自我限产硬口径，**超限即由 F 出红**）",
                          "裁定 101.1 自缚四条（(a) 不新增口径名 · (b) params 只写指针+实测值 · (c) 身份自检降为每里程碑一次 · (d) 交接件/日报/decisions 行数上限）",
                          "D→F 补单六 §三-5"],
            "rounds": rounds, "daily_d_sections": d_segs_since_r100, "limits": limits,
            "exceeded": exceeded, "overall": ("exceeded" if over else "within_limits"),
            "f_action_if_exceeded": "按裁定 100.9 出红（F 的台账里记 not_delivered，并在日报点名超限的那一条）",
            "measurement_status": "measured",
            "params_prose_check_note": ("101.1-(b)「params 只写指针 + 实测值、不复制散文」需要逐键判散文，"
                                        "F 本轮只报行数增量与 rev 数，**不**代 D 判某段是不是散文（登记为待 D 明确判据）")}


def build_ledger(probe: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for task, question, authority, fn in CHECKS:
        try:
            res = fn()
        except Exception as exc:                                   # noqa: BLE001
            res = {"status": NOT_MEASURED, "evidence": f"探测异常：{type(exc).__name__}: {exc}"}
        res.setdefault("status", NOT_MEASURED)
        step = res.pop("six_step", None) or SIX_STEP_MAP.get(task)
        entries.append({"check_id": f"F-{len(entries) + 1:02d}", "task": task,
                        "question": question, "authority": authority,
                        "status": res.pop("status"), "as_of": _now(),
                        "six_step": step,
                        "critical_path_generation": ("ruling_95_six_steps" if step
                                                     else "ruling_94_or_earlier"),
                        "superseded_by_ruling_95": task in SUPERSEDED_BY_RULING_95,
                        "superseded_reason": SUPERSEDED_BY_RULING_95.get(task),
                        **res})
    counts = {s: sum(1 for e in entries if e["status"] == s)
              for s in (DELIVERED, NOT_DELIVERED, NOT_MEASURED, NOT_APPLICABLE)}

    # 六步视图（裁定 95.3 权威序列）。**描述性汇总，不是判据**：F 不设阻塞（裁定 96）。
    six_step_view = []
    for spec in SIX_STEPS:
        sid = spec["step"]
        mine = [e for e in entries if str(e.get("six_step") or "").startswith(sid)]
        st: dict[str, int] = {}
        for e in mine:
            st[e["status"]] = st.get(e["status"], 0) + 1
        if not mine:
            rollup, why = NOT_APPLICABLE, "本轮未对本步单设检查；到期条件未触发（裁定 72-2：不适用不出红）"
        elif st.get(NOT_MEASURED):
            rollup, why = NOT_MEASURED, "至少一条检查探测失败或对象不在盘 ⇒ 不猜"
        elif st.get(NOT_DELIVERED):
            rollup, why = NOT_DELIVERED, "至少一条检查实测未交付"
        elif len(st) == 1 and st.get(DELIVERED):
            rollup, why = DELIVERED, "本步名下的检查全部实测交付"
        elif len(st) == 1 and st.get(NOT_APPLICABLE):
            rollup, why = NOT_APPLICABLE, "本步的到期条件未触发"
        else:
            rollup, why = "mixed", "本步名下检查状态不一致（逐条看 checks）"
        six_step_view.append({**spec, "n_checks": len(mine), "statuses": st, "rollup": rollup,
                              "rollup_reason": why, "check_ids": [e["check_id"] for e in mine]})
    return {
        "artifact": "f_progress_ledger",
        "generated_at": _now(),
        "generator": "scripts/f_progress_ledger.py",
        "line": "F（监管分析 / 进度核算，配合 D）",
        "read_only": True,
        "policy_executed": False,
        "gpu_used": False,
        "capability_claim": None,          # 裁定 46：BC 出结果前不得有任何能力表述
        "success_metrics_collected": False,
        "citation_algo": CITATION_ALGO,
        "three_state_discipline": ("delivered / not_delivered / not_measured（空集或探测失败 ⇒ not_measured，"
                                   "不许写 false/0）+ not_applicable（到期条件未触发，裁定 72-2：不适用不出红）"),
        "scan_scope": list(SCAN_PREFIXES) + ["/proc（只读，不起 find）"],
        "no_root_filesystem_scans": True,
        "counts": counts,
        "n_checks": len(entries),
        "checks": entries,
        "critical_path_authority": ("裁定 95.3 的六步序列（**权威、不许重排**）；旧关键路径 S4b → S3 BC "
                                    "已由 D→F 交接件 §五-1 换判据，旧判据**不作废**、逐条标 "
                                    "`superseded_by_ruling_95` + `critical_path_generation`"),
        "six_step_view": six_step_view,
        "six_step_rollup_caliber": ("描述性汇总，不是判据：有 not_measured ⇒ not_measured；有 not_delivered ⇒ "
                                    "not_delivered；全 delivered ⇒ delivered；全 not_applicable ⇒ not_applicable；"
                                    "其余 ⇒ mixed。F 不设阻塞、不定标、不改极性（裁定 96）"),
        "superseded_by_ruling_95": SUPERSEDED_BY_RULING_95,
        "governance_metrics_status": {
            "suspended_by": "裁定 101.1 + D→F 待命令（17:2x）：`coverage` / `doc_limit_compliance` / "
                            "`pattern_coverage_probe` 这类治理指标在 Step 1 出结果前**不再更新**（登记不阻塞）",
            "doc_limit_compliance": {"status": "suspended_by_ruling_101", "not_updated_this_round": True,
                                     "last_reading": {"as_of": "2026-09-30T16:09:49+0800",
                                                      "artifact": "PROGRESS_LEDGER.json@a2b5b0eef54d"}},
            "pattern_coverage_probe": probe,
            "coverage_metric": {"status": "suspended_by_ruling_101", "not_updated_this_round": True,
                                "last_reading": {"as_of": "2026-09-30T16:09:49+0800", "coverage_all": 0.1132,
                                                 "coverage_steps_1_to_3": 0.5,
                                                 "artifact": "TRIGGER_REGISTRY.json@d0661270d337"}},
        },
        "ruling_101_freeze": {
            "six_blocking_classes_only": True,
            "other_items": "登记，不阻塞训练（裁定 101.1）",
            "step1_is_the_only_in_flight_order": True,
            "authority": "裁定 101.1 / 101.2 / 102.6",
        },
        "blocking_class_registry": build_blocking_class_registry(),
        "step1_acceptance_tracker": step1_acceptance_tracker(),
        "d_self_limit_compliance": measure_d_self_limit(),
        "verdict": ("ok" if counts[NOT_MEASURED] == 0 else "has_not_measured"),
        "verdict_caliber_note": ("裁定 101.1 起探针停跑 ⇒ verdict 只看三值计数，不再看 `all_detected`；"
                                 "探针状态在 governance_metrics_status 里如实登记为 suspended"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="F 线只读进度核算器（三值 + 对照探针）")
    ap.add_argument("--out-dir", default="runs/vla/f_oversight_20260930")
    ap.add_argument("--selftest", action="store_true", help="只跑 93.8 的对照探针，不写台账")
    args = ap.parse_args()

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.selftest:
        probe = pattern_coverage_probe(out_dir)
        print(json.dumps(probe, ensure_ascii=False, indent=2))
        return 0 if probe["all_detected"] else 3

    # 裁定 101.1：探针（93.8 的模式覆盖自检）属治理指标 ⇒ Step 1 出结果前停跑，只留上一轮读数。
    probe = {"status": "suspended_by_ruling_101", "all_detected": None, "not_a_measurement": True,
             "authority": "裁定 101.1 + D→F 待命令（17:2x）",
             "last_reading": {"as_of": "2026-09-30T16:09:49+0800", "all_detected": True,
                              "artifact": "PROGRESS_LEDGER.json@a2b5b0eef54d"}}
    ledger = build_ledger(probe)
    registry = build_trigger_registry()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    ledger_path = out_dir / "PROGRESS_LEDGER.json"
    registry_path = out_dir / "TRIGGER_REGISTRY.json"
    # 覆写自己的产物 ⇒ 先留前像（裁定 27/92.2）
    for path in (ledger_path, registry_path):
        if path.exists():
            before = out_dir / "before_images" / f"{path.name}.before_{stamp}"
            before.parent.mkdir(parents=True, exist_ok=True)
            before.write_bytes(path.read_bytes())

    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ident = {"artifact": "F_IDENTITY_TABLE", "generated_at": _now(), "citation_algo": CITATION_ALGO,
             "authority": "裁定 92.3（红线级）：身份串必须由工具在落笔时刻生成、人不碰",
             "generator_sha256_12": _sha(Path(__file__)),
             "targets": [_identity(ledger_path, "F 每轮的进度台账；D 核各线交付的第一入口"),
                         _identity(registry_path, "预登记条件的消费方台账（缺陷类 ⑳）"),
                         _identity(Path(__file__), "本核算器；判据与扫描作用域都在里面，可复核")]}
    ident_path = out_dir / f"F_IDENTITY_TABLE_{stamp}.json"
    ident_path.write_text(json.dumps(ident, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"verdict": ledger["verdict"], "counts": ledger["counts"],
                      "n_checks": ledger["n_checks"],
                      "probe_all_detected": probe["all_detected"],
                      "six_step_rollup": {s["step"]: s["rollup"] for s in ledger["six_step_view"]},
                      "governance_metrics": (ledger.get("governance_metrics_status") or {})
                      .get("pattern_coverage_probe", {}).get("status"),
                      "d_self_limit_overall": (ledger.get("d_self_limit_compliance") or {}).get("overall"),
                      "six_blocking_classes": [(c["class_id"], c["measurement_status"]) for c in
                                               ((ledger.get("blocking_class_registry") or {}).get("classes") or [])],
                      "step1_criteria_with_readings": sum(1 for c in ((ledger.get("step1_acceptance_tracker") or {})
                                                                     .get("criteria") or [])
                                                          if c.get("measurement_status") != NOT_MEASURED),
                      "coverage_metric_status": (registry.get("coverage_metric_status") or {}).get("status"),
                      "l12_chain_not_deleted": ((registry.get("blocking_classes_ruling101") or {})
                                                 .get("l12_chain") or {}).get("chain_not_deleted"),
                      "ledger": str(ledger_path.relative_to(ROOT)),
                      "ledger_sha256_12": _sha(ledger_path),
                      "registry": str(registry_path.relative_to(ROOT)),
                      "registry_sha256_12": _sha(registry_path),
                      "identity_table": str(ident_path.relative_to(ROOT))}, ensure_ascii=False, indent=2))
    for entry in ledger["checks"]:
        if entry["status"] != DELIVERED:
            print(f"  [{entry['status']:>13}] {entry['check_id']} {entry['task']}: {entry['evidence'][:150]}")
    if not probe["all_detected"]:
        return 3
    return 4 if ledger["counts"][NOT_MEASURED] else 0


if __name__ == "__main__":
    sys.exit(main())
