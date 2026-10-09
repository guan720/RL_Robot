#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · 裁定 68 补救登记：`overwritten_c_artifacts`（新纪律 `regression_driver_output_enumeration`）。

## 为什么有这个脚本
D 实测（裁定 68 / `d_handoff_to_c2_20260929.md:286`–`:306`）：C2 的 C 线回归驱动
`scripts/c2_run_c_regression_postpatch.sh` 在 21:42:43–21:44:16 **覆写了 `runs/infra/` 顶层 16 个
C 线产物**，未申报、无 before 影像；根因是驱动只把 `c_env_manifest.py --check` 一处改指到 C2 目录，
其余自检脚本把结果写在**源码里的固定路径**（例 `scripts/c_learner_shard_smoke.py:85`）。
`runs/` 被 `.gitignore:12` 排除 ⇒ 无 git 恢复路径。
D 的处置：**结果采纳，程序违规记一次**；补救 = **只做登记，不重跑**，且这份登记
「就是这 16 个文件从此以后的新溯源起点」（`:306`）。

## 本脚本产出什么（逐条对齐 D 要求的六列）
文件名 / 覆写时刻 / 新 `sha256-12` / 新字节数 / 是否被其它线文书引用（引到哪一行）/ D 的复核结论。
另外按新纪律补两件 D 没点名但纪律要求的事：
1. **枚举**（不是"挑一个最显眼的"）：从 17 个被调脚本的**源码**里 grep 全部固定路径输出，
   逐个登记 `script → fixed_outputs → 驱动是否改指`；
2. **双向核对**：本脚本**独立**按 mtime 窗口重新推导覆写集合，再与 D 在 `:291`–`:296` 代码块里
   枚举的 16 个文件名**逐条比对**；不一致 ⇒ `verdict=RED`（防止"两边各说一半"）。

## 纪律
* **只读**：不改任何 `runs/infra/c_*`、不改 `harness/`、不 `rm`；产物只落 C2 自己的目录。
* 计数/存在性主张带 (mtime, 计数, 命令原文)；否定型主张先枚举完整清单（裁定 50.2）。
* 状态词只用 v4 五档；不用「跑通 / 学会 / 达标」。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "c2_run_c_regression_postpatch.sh"
DRIVER_OUT_DEFAULT = ROOT / "runs/vla/c2_obs_key_whitelist_20260929/c_regression_postpatch"
C_RUN_ALL = ROOT / "scripts/c_run_all_selfchecks.sh"
D_DOC = ROOT / "rl_harness_supervision/d_handoff_to_c2_20260929.md"
OUT_DIR = ROOT / "runs/infra/c2_overwritten_c_artifacts_20260929"
# 引用面：只读 grep 的文书范围（不含 recycle_bin / runs）
DOC_ROOTS = ["docs", "rl_harness_supervision", "RL_Harness_v4_20260924", "work/decisions", "appendices"]
DOC_FILES = ["daily_report.md", "README.md"]
FIXED_PATH_RE = re.compile(r"runs/infra/[A-Za-z0-9_./{}\-]+\.json(?:l)?")


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def sha12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def mtime_iso(path: Path) -> str:
    return _dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone().replace(microsecond=0).isoformat()


def loadavg() -> str:
    try:
        return " ".join(Path("/proc/loadavg").read_text().split()[:3])
    except OSError:
        return "unavailable"


def nr_throttled() -> int | None:
    p = Path("/sys/fs/cgroup/cpu,cpuacct/cpu.stat")
    if not p.exists():
        p = Path("/sys/fs/cgroup/cpu.stat")
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        if line.startswith("nr_throttled"):
            return int(line.split()[1])
    return None


def parse_script_list() -> list[str]:
    """不手抄清单：从 C 的驱动里解析 `SCRIPTS=(...)`（与回归驱动同一套解析，避免两份清单分叉）。"""
    text = C_RUN_ALL.read_text(encoding="utf-8")
    block = re.search(r"^SCRIPTS=\((.*?)^\)", text, re.S | re.M)
    if not block:
        raise SystemExit(f"无法从 {C_RUN_ALL} 解析 SCRIPTS=(...)")
    return [tok for tok in re.split(r"\s+", block.group(1)) if re.fullmatch(r"[A-Za-z0-9_]+", tok)]


def driver_window(driver_out: Path) -> tuple[float, float, dict]:
    """覆写时间窗从驱动自己的日志 mtime 推导（不写死 D 报的钟点）。"""
    logs = sorted(driver_out.glob("*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        raise SystemExit(f"驱动日志不存在：{driver_out}/*.log")
    lo = logs[0].stat().st_mtime
    hi = max(p.stat().st_mtime for p in driver_out.rglob("*") if p.is_file())
    summary = {}
    sp = driver_out / "summary.txt"
    if sp.exists():
        for line in sp.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                summary[k.strip()] = v.strip()
    return lo, hi, summary


def d_enumerated_names() -> tuple[list[str], dict]:
    """解析 D 在 §10.2 代码块里枚举的文件名（用于双向核对），带 (mtime, sha256-12, 行号)。"""
    text = D_DOC.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if "覆写了 16 个 C 线产物" in line:
            start = i
            break
    if start is None:
        return [], {"error": "定位不到 §10.2 标题行"}
    fence = [i for i in range(start, min(start + 40, len(lines))) if lines[i].strip() == "```"]
    if len(fence) < 2:
        return [], {"error": "定位不到 §10.2 代码块围栏"}
    body = "\n".join(lines[fence[0] + 1:fence[1]])
    # 长后缀优先：否则 `x.jsonl` 会被截成 `x.json` ⇒ 假 RED（C2 首跑实测踩过，见产物 selfcheck）
    names = sorted(set(re.findall(r"[A-Za-z0-9_\-]+\.(?:jsonl|json)(?![A-Za-z0-9])", body)))
    ident = {"path": str(D_DOC.relative_to(ROOT)), "sha256_12": sha12(D_DOC),
             "block_first_line": fence[0] + 1, "block_last_line": fence[1] + 1,
             "doc_lines": len(lines), "doc_mtime": mtime_iso(D_DOC)}
    return names, ident


def fixed_outputs_of(script_name: str) -> dict:
    """从被调脚本源码里枚举固定路径输出（新纪律要求：枚举，不挑）。"""
    p = ROOT / "scripts" / f"{script_name}.py"
    rec: dict = {"script": f"scripts/{script_name}.py", "exists": p.exists()}
    if not p.exists():
        return rec
    text = p.read_text(encoding="utf-8")
    hits: list[dict] = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in FIXED_PATH_RE.finditer(line):
            hits.append({"line": i, "path": m.group(0), "text": line.strip()[:160]})
    # 也认 ROOT/"runs"/"infra"/"x.json" 这种拼接式写法
    joined = re.findall(r'"runs"\s*/\s*"infra"\s*/\s*"([A-Za-z0-9_.\-]+\.jsonl?)"', text)
    joined_lines = []
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r'"runs"\s*/\s*"infra"', line):
            joined_lines.append({"line": i, "text": line.strip()[:160]})
    rec.update({"literal_fixed_paths": hits, "joined_runs_infra_lines": joined_lines,
                "joined_output_names": sorted(set(joined)),
                "sha256_12": sha12(p), "lines": len(text.splitlines())})
    return rec


def references_to(filename: str) -> dict:
    """grep 引用面：命令原文 + 命中 (path:line) + 计数。"""
    paths = [str(ROOT / d) for d in DOC_ROOTS if (ROOT / d).exists()] + \
            [str(ROOT / f) for f in DOC_FILES if (ROOT / f).exists()]
    cmd = ["grep", "-rn", "--include=*.md", "--include=*.json", "--include=*.txt", filename] + paths
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"command": " ".join(cmd), "error": "timeout"}
    hits = []
    for line in proc.stdout.splitlines():
        m = re.match(r"^(.*?):(\d+):", line)
        if m:
            hits.append({"path": os.path.relpath(m.group(1), ROOT), "line": int(m.group(2))})
    return {"command": " ".join(cmd), "n_hits": len(hits), "hits": hits[:12],
            "truncated": len(hits) > 12, "grep_exit": proc.returncode}


def git_ignore_status(relpath: str) -> dict:
    cmd = ["git", "-C", str(ROOT), "check-ignore", "-v", relpath]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {"command": " ".join(cmd), "exit": proc.returncode,
            "ignored": proc.returncode == 0, "rule": proc.stdout.strip() or None}


def json_fingerprint(path: Path) -> dict:
    """新字节的可核验指纹：顶层键 + 少量关键字段（供后续文书引用比对）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - 登记事实，不掩盖
        return {"parse_ok": False, "error": f"{type(exc).__name__}: {exc}"}
    out: dict = {"parse_ok": True}
    if isinstance(data, dict):
        out["top_level_keys"] = sorted(data.keys())[:40]
        out["n_top_level_keys"] = len(data)
        for k in ("n_checks", "pass", "ok", "verdict", "generated_at", "representation_version"):
            if k in data:
                out[f"field_{k}"] = data[k] if not isinstance(data[k], (dict, list)) else type(data[k]).__name__
    elif isinstance(data, list):
        out["list_len"] = len(data)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--driver-out", default=None, help="驱动的输出目录（默认 = 未接守卫那次的目录）")
    ap.add_argument("--event-label", default=None,
                    help="事件标签（默认由窗口时刻推导：event_<YYYYmmdd>_<HHMM>）；产物落 <out-dir>/events/<label>/")
    ap.add_argument("--prior-registry", default=None,
                    help="上一事件的 registry.json；给了就逐条比对 sha256-12（本事件的 before 指纹）")
    ap.add_argument("--root-cause", default=None, help="本次覆写的根因（自由文本，写进产物）")
    ap.add_argument("--trigger", default=None, help="触发者（脚本路径 + sha256-12）")
    ap.add_argument("--seed-event1", action="store_true",
                    help="把顶层 event1 权威记录推导成 index 的一条（不手抄数字）")
    ap.add_argument("--guard-active", action="store_true",
                    help="本次运行是否在 c2_driver_output_guard 三段式守卫下（默认 false）")
    ap.add_argument("--pad-s", type=float, default=2.0,
                    help="时间窗左右各放宽的秒数（默认 2 s，覆盖脚本启动与落盘抖动）")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    driver_out = Path(args.driver_out).resolve() if args.driver_out else DRIVER_OUT_DEFAULT
    lo, hi, summary = driver_window(driver_out)
    d_names, d_ident = d_enumerated_names()
    scripts = parse_script_list()

    infra = ROOT / "runs/infra"
    window_files = []
    for p in sorted(infra.iterdir()):
        if not p.is_file():
            continue
        mt = p.stat().st_mtime
        if lo - args.pad_s <= mt <= hi + args.pad_s:
            window_files.append(p)
    derived_names = sorted(p.name for p in window_files)

    enumerated = []
    for s in scripts + ["c_env_manifest", "verify_package"]:
        enumerated.append(fixed_outputs_of(s if s != "verify_package" else "verify_package"))

    entries = []
    for p in window_files:
        rel = str(p.relative_to(ROOT))
        refs = references_to(p.name)
        entries.append({
            "filename": p.name,
            "relpath": rel,
            "overwritten_at": mtime_iso(p),
            "sha256_12": sha12(p),
            "bytes": p.stat().st_size,
            "line_owner_prefix": p.name.split("_")[0],
            "before_image_present": False,
            "git_recovery_possible": False,
            "git_ignore": git_ignore_status(rel),
            "referenced_by_other_docs": refs["n_hits"] > 0,
            "n_references": refs["n_hits"],
            "references": refs["hits"],
            "references_truncated": refs.get("truncated", False),
            "grep_command": refs["command"],
            "new_bytes_fingerprint": json_fingerprint(p),
            "d_review_conclusion": (
                "D 逐条复核通过（裁定 68 §10.2 正文点名本文件：n_checks=46 / pass=true / "
                "bc_anchor_xi0_gap.verdict=substantive_gap / channels_with_gap=[takeover] / "
                "takeover 28/28 / clean=terminal=0 且 ratio=None / representation_version="
                "lift-state-proprio50+obj10-v1 / n=4 γ=0.99 H=8 ⇒ 与四处文书引用逐条一致）"
                if p.name == "c_learner_shard_smoke.json"
                else "D 未逐条复核本文件（§10.2 只点名 c_learner_shard_smoke.json）；"
                     "损害评估结论「可恢复 / 原始 C 运行字节的 mtime 溯源已断、永久登记」按裁定 68 适用于全部 16 个文件"
            ),
        })

    both = sorted(set(derived_names) | set(d_names))
    crosscheck = {
        "derived_by_c2_from_mtime_window": derived_names,
        "enumerated_by_d_in_ruling_68": d_names,
        "window": {"lo_iso": _dt.datetime.fromtimestamp(lo).astimezone().replace(microsecond=0).isoformat(),
                   "hi_iso": _dt.datetime.fromtimestamp(hi).astimezone().replace(microsecond=0).isoformat(),
                   "pad_s": args.pad_s,
                   "derived_from": f"{driver_out.relative_to(ROOT)} 下全部文件的 mtime（不写死 D 报的钟点）"},
        "only_in_c2": sorted(set(derived_names) - set(d_names)),
        "only_in_d": sorted(set(d_names) - set(derived_names)),
        "identical": derived_names == d_names,
        "n_derived": len(derived_names), "n_d": len(d_names),
        "d_doc_identity": d_ident,
    }
    # 潜在地雷：被调脚本源码里声明的固定路径，本轮**没有**落在窗口内 ⇒ 换个 flag 再跑就可能覆写。
    # 纪律 regression_driver_output_enumeration 要求"枚举全部"，不只是"枚举被写的那批"。
    latent = []
    seen = set()
    for rec in enumerated:
        cand = [h["path"] for h in rec.get("literal_fixed_paths", [])] + \
               [f"runs/infra/{n}" for n in rec.get("joined_output_names", [])]
        for c in cand:
            if "{" in c or "..." in c or c in seen:
                continue
            seen.add(c)
            ap_ = ROOT / c
            in_window = ap_.exists() and (lo - args.pad_s <= ap_.stat().st_mtime <= hi + args.pad_s)
            latent.append({"path": c, "declared_by": rec["script"], "exists": ap_.exists(),
                           "written_in_window": in_window,
                           "mtime": mtime_iso(ap_) if ap_.exists() else None,
                           "sha256_12": sha12(ap_) if ap_.exists() else None,
                           "bytes": ap_.stat().st_size if ap_.exists() else None,
                           "line": next((h["line"] for h in rec.get("literal_fixed_paths", [])
                                         if h["path"] == c), None)})
    latent_summary = {"n_declared_fixed_paths": len(latent),
                      "n_written_in_window": sum(1 for x in latent if x["written_in_window"]),
                      "n_declared_but_not_written": sum(1 for x in latent if not x["written_in_window"]),
                      "declared_but_not_written": [x["path"] for x in latent if not x["written_in_window"]]}

    prior = None
    if args.prior_registry:
        prior_path = Path(args.prior_registry)
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        try:
            prior_rel = str(prior_path.resolve().relative_to(ROOT))
        except ValueError:
            prior_rel = str(prior_path)
        pmap = {e["filename"]: e for e in prior.get("entries", [])}
        for e in entries:
            pe = pmap.get(e["filename"])
            if pe is None:
                e.update({"sha_before_event": None, "bytes_before_event": None,
                          "changed_by_this_event": None,
                          "in_prior_event": False})
                continue
            e.update({"sha_before_event": pe["sha256_12"], "bytes_before_event": pe["bytes"],
                      "changed_by_this_event": pe["sha256_12"] != e["sha256_12"],
                      "in_prior_event": True})
        prior_names = sorted(pmap)
        crosscheck_prior = {"prior_registry": prior_rel,
                            "prior_registry_sha256_12": sha12(prior_path),
                            "prior_event_label": prior.get("event_label"),
                            "n_prior": len(prior_names),
                            "identical_file_set": prior_names == derived_names,
                            "only_in_this": sorted(set(derived_names) - set(prior_names)),
                            "only_in_prior": sorted(set(prior_names) - set(derived_names)),
                            "n_changed_bytes": sum(1 for e in entries if e.get("changed_by_this_event")),
                            "n_unchanged_bytes": sum(1 for e in entries if e.get("changed_by_this_event") is False),
                            "changed": [e["filename"] for e in entries if e.get("changed_by_this_event")],
                            "unchanged": [e["filename"] for e in entries
                                          if e.get("changed_by_this_event") is False]}
    else:
        crosscheck_prior = None

    label = args.event_label or ("event_" + _dt.datetime.fromtimestamp(lo).astimezone().strftime("%Y%m%d_%H%M"))
    classification = ("guarded_regression_no_net_change" if args.guard_active
                      else "violation_unguarded_overwrite")

    a_line_in_set = [n for n in derived_names if n.startswith("a_")]
    payload = {
        "event_label": label,
        "classification": classification,
        "guard_active": bool(args.guard_active),
        "root_cause": args.root_cause,
        "trigger": args.trigger or f"{DRIVER.relative_to(ROOT)} sha256-12={sha12(DRIVER)}",
        "crosscheck_with_prior_event": crosscheck_prior,
        "artifact": "overwritten_c_artifacts",
        "generated_at": now_iso(),
        "generated_by": {"script": "scripts/c2_register_overwritten_c_artifacts.py",
                         "sha256_12": sha12(Path(__file__).resolve())},
        "authority": ["裁定 68（d_handoff_to_c2_20260929.md:269-312）",
                      "裁定 69（supervisor_memo_20260929.md:2364-2372）",
                      "新纪律 regression_driver_output_enumeration（d_handoff_to_c2_20260929.md:307-312）"],
        "driver": {"path": str(DRIVER.relative_to(ROOT)), "sha256_12": sha12(DRIVER),
                   "summary_txt": summary},
        "crosscheck_with_d": crosscheck,
        "fixed_output_enumeration": enumerated,
        "latent_fixed_outputs": latent,
        "latent_summary": latent_summary,
        "entries": entries,
        "n_entries": len(entries),
        "a_line_products_in_set": a_line_in_set,
        "load_pair": {"loadavg": loadavg(), "nr_throttled": nr_throttled(),
                      "cgroup_quota_cores": 12, "note": "并行度分母用 cgroup 配额 12 核，不用 nproc(=112)"},
        "verdict": "PASS" if crosscheck["identical"] else "RED",
        "verdict_reason": ("C2 独立按 mtime 窗口推导的覆写集合与 D 在裁定 68 §10.2 枚举的集合逐条相同"
                           if crosscheck["identical"] else
                           f"集合不一致：only_in_c2={crosscheck['only_in_c2']} only_in_d={crosscheck['only_in_d']}"),
        "provenance_note": ("本登记是这 16 个文件从此以后的**新溯源起点**（D 原文，:306）。"
                            "原始 C 运行字节的 mtime 溯源已断、不可修复；本文件不声称恢复它。"),
    }
    ev_dir = out_dir / "events" / label
    ev_dir.mkdir(parents=True, exist_ok=True)
    outp = ev_dir / "registry.json"
    before_images = []
    if outp.exists():
        prev_sha = sha12(outp)
        prev = outp.with_name(f"overwritten_c_artifacts_registry.before_{prev_sha}.json")
        prev.write_bytes(outp.read_bytes())
        before_images.append({"path": str(prev.relative_to(ROOT)), "sha256_12": prev_sha,
                              "bytes": prev.stat().st_size, "mtime": mtime_iso(prev)})
        payload["previous_run_before_image"] = before_images[-1]
    payload["before_images_written_this_run"] = before_images
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown 表（供回流单直接引用，避免两份内容分叉：回流单只引本文件路径 + verdict）
    md = ["| 文件名 | 覆写时刻 | 新 sha256-12 | 新字节数 | 被其它线文书引用 | D 的复核结论 |",
          "|---|---|---|---|---|---|"]
    for e in entries:
        d_short = "D 逐条复核通过（§10.2 点名）" if e["filename"] == "c_learner_shard_smoke.json" \
            else "未逐条复核；按裁定 68 整体损害评估"
        ref = f"是（{e['n_references']} 处" + (f"，示例 {e['references'][0]['path']}:{e['references'][0]['line']}"
                                              if e["references"] else "") + "）" if e["referenced_by_other_docs"] else "否（0 处）"
        md.append(f"| `{e['filename']}` | {e['overwritten_at']} | `{e['sha256_12']}` | {e['bytes']} | {ref} | {d_short} |")
    md += ["", f"- 双向核对：C2 独立推导 {crosscheck['n_derived']} 个 vs D 枚举 {crosscheck['n_d']} 个 ⇒ "
               f"`identical={str(crosscheck['identical']).lower()}`；verdict=**{payload['verdict']}**",
           f"- A 线产物是否在其中：`{a_line_in_set or '[]（0 个，均为 c_/harness_/runtime_ 前缀）'}`",
           f"- git 恢复路径：无（`runs/` 被 `.gitignore:12` 排除；逐条 check-ignore 见 JSON）",
           f"- before 影像：无（`before_image_present=false`，16/16）"]
    (ev_dir / "table.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # 顶层索引（不覆写 event1 的权威记录 `overwritten_c_artifacts_registry.json`）
    idx_path = out_dir / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {"events": []}
    # event1 的种子：从顶层权威记录里**推导**（不手抄），保证 index 与 event1 记录一致
    top = out_dir / "overwritten_c_artifacts_registry.json"
    if args.seed_event1 and top.exists() and "event_label" not in json.loads(top.read_text(encoding="utf-8")):
        e1 = json.loads(top.read_text(encoding="utf-8"))
        w1 = e1["crosscheck_with_d"]["window"]
        idx["events"] = [e for e in idx["events"] if e.get("event_label") != "event1_20260929_2142"]
        idx["events"].append({
            "event_label": "event1_20260929_2142",
            "classification": "violation_unguarded_overwrite",
            "guard_active": False,
            "window": w1, "n_files": e1["n_entries"],
            "verdict_set_crosscheck": e1["verdict"],
            "registry": str((out_dir / "events/event1_20260929_2142/registry.json").relative_to(ROOT)),
            "registry_sha256_12": sha12(out_dir / "events/event1_20260929_2142/registry.json"),
            "root_cause": ("驱动只改指 c_env_manifest 一处，其余自检脚本写死 runs/infra 固定路径"
                           "（裁定 68 §10.2 的根因）"),
            "trigger": "scripts/c2_run_c_regression_postpatch.sh sha256-12=60aff102c836（未接守卫版本）",
            "registered_at": e1["generated_at"], "seeded_from_top_level": str(top.relative_to(ROOT)),
            "top_level_sha256_12": sha12(top)})
    idx["events"] = [e for e in idx["events"] if e.get("event_label") != label]
    idx["events"].append({"event_label": label, "classification": classification,
                          "guard_active": bool(args.guard_active),
                          "window": crosscheck["window"], "n_files": len(entries),
                          "verdict_set_crosscheck": payload["verdict"],
                          "registry": str(outp.relative_to(ROOT)), "registry_sha256_12": sha12(outp),
                          "root_cause": args.root_cause, "trigger": payload["trigger"],
                          "registered_at": now_iso()})
    idx["events"].sort(key=lambda e: e["window"]["lo_iso"])
    idx["updated_at"] = now_iso()
    idx["n_events"] = len(idx["events"])
    idx["top_level_event1_record"] = {"path": "overwritten_c_artifacts_registry.json",
                                      "sha256_12": "17054fa4c2b3",
                                      "note": "event1 的权威记录，原样保留（另见 events/event1_20260929_2142/）"}
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"verdict": payload["verdict"], "reason": payload["verdict_reason"],
                      "n_entries": payload["n_entries"], "n_fixed_output_scripts": len(enumerated),
                      "out": str(outp.relative_to(ROOT)),
                      "event_label": label, "classification": classification,
                      "table": str((ev_dir / "table.md").relative_to(ROOT)),
                      "index": str(idx_path.relative_to(ROOT))},
                     ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
