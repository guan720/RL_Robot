"""F 的只读探针：E/A2/B2 共用的占卡判定 `card_busy()` 会不会被**文本**误触发。

为什么需要它（实测动机）：`card_busy()` 的窄档 `gpu_intent` 判据是「cmdline 里出现
GPU 入口关键字」。而关键字是**字面量匹配**，于是任何"正在 grep/cat/heredoc 里提到
这些字面量"的纯 CPU 进程都会被判成「有人正要上卡」。后果是具体的：裁定 94.9-1② 要求
A2 在 S4b **起跑那一刻**实测三网，若此刻别线正在读这些脚本，A2 的窗口会被判
`contaminated`（数字不被 D 认），或被起跑前拒绝逻辑挡下（`exit 3`）⇒ 白跑一轮。

这与 B2 自报的 **RR-B2-18**（`contaminated_by_cotenant` 因 `"RL_Robot" in args` 永久为真）
和 E 的 cmdline 网是**同一族**：网在匹配「关于 GPU 的文本」，不是「GPU 占用」。

本探针**不修改任何线的代码**，只做三件事：
  ① 用 `ast` 从 `scripts/e_mainline_render_calib.py` **运行时**取出 `GPU_INTENT_PATTERNS`
     与 `OTHER_LINE_SCRIPT_RE`（不把它们写进本件源码 —— 第一版写死过，结果被自己命中，
     那是缺陷类 ⑲ 的自实例；本件按 93.8 带对照探针，见 ③）；
  ② 扫 `/proc`（**只读，不起 `find`，不扫根文件系统**，裁定 94.9-2），按窄档/宽档分类，
     并把每个命中进一步分成 `real_gpu_work`（cmdline 里真的有 `python …/scripts/<line>_*.py`
     这种执行形态）与 `text_mention_only`（只是提到了关键字）；
  ③ 落 93.8 要求的 `pattern_coverage_probe`：注入一个**只在文本里提到关键字**的合成
     cmdline ⇒ 必须被本探针归类为 `text_mention_only`（即"能被识别出来"），
     抓不到 ⇒ 本探针按 `not_measured` 登记、不得报绿。

退出码：0 = 测到且无假阳性风险；5 = 存在 `text_mention_only` 命中（= 假阳性风险成立，
需要 E 侧修判据）；4 = 探测作用域为空（`/proc` 读不到）；3 = 对照探针失败。
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CALIBER_SRC = "scripts/e_mainline_render_calib.py"
OUT_DIR = ROOT / "runs" / "vla" / "f_oversight_20260930"
CITATION_ALGO = "sha256[:12]"
EXEC_FORM_RE = re.compile(r"(?:^|\s)(?:\S*python\S*|\S*/bin/\S+)\s+\S*scripts/(?:a2?|b2?|c2?|d|e|f)_\S+")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def load_patterns() -> tuple[tuple[str, ...], re.Pattern[str], dict[str, Any]]:
    """用 ast 从 E 的源码里取判据；**不 import**（避免任何副作用），也不把字面量抄进本件。"""
    src = (ROOT / CALIBER_SRC).read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(src)
    intent: tuple[str, ...] = ()
    broad_src = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = getattr(target, "id", "")
                if name == "GPU_INTENT_PATTERNS" and isinstance(node.value, ast.Tuple):
                    intent = tuple(ast.literal_eval(node.value))
                elif name == "OTHER_LINE_SCRIPT_RE" and isinstance(node.value, ast.Call):
                    args = [a for a in node.value.args if isinstance(a, ast.Constant)]
                    broad_src = str(args[0].value) if args else ""
    meta = {"source": CALIBER_SRC,
            "source_sha256_12": hashlib.sha256((ROOT / CALIBER_SRC).read_bytes()).hexdigest()[:12],
            "source_n_lines": (ROOT / CALIBER_SRC).read_bytes().count(b"\n"),
            "extraction_method": "ast.literal_eval（运行时取值，本件源码不含这些字面量）",
            "n_intent_patterns": len(intent),
            "broad_regex": broad_src,
            "as_of": _now()}
    if not intent or not broad_src:
        raise RuntimeError(f"判据取值失败（intent={len(intent)}, broad={broad_src!r}）")
    return intent, re.compile(broad_src), meta


def own_tree() -> set[int]:
    pids = {os.getpid()}
    try:
        cur = os.getpid()
        for _ in range(8):
            stat = Path(f"/proc/{cur}/stat").read_text(errors="ignore")
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
            if ppid <= 1 or ppid in pids:
                break
            pids.add(ppid)
            cur = ppid
    except (OSError, ValueError, IndexError):
        pass
    return pids


def scan(intent: tuple[str, ...], broad: re.Pattern[str]) -> dict[str, Any]:
    excl = own_tree()
    try:
        entries = os.listdir("/proc")
    except OSError as exc:
        return {"measurement_status": "not_measured", "error": f"{type(exc).__name__}: {exc}"}
    narrow_hits: list[dict[str, Any]] = []
    broad_hits: list[dict[str, Any]] = []
    n_proc = 0
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in excl:
            continue
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            continue
        cl = " ".join(raw.replace(b"\0", b" ").decode(errors="ignore").split())[:400]
        if not cl:
            continue
        n_proc += 1
        matched = [p for p in intent if p in cl]
        is_exec = bool(EXEC_FORM_RE.search(cl))
        if matched:
            narrow_hits.append({"pid": pid, "matched_patterns": matched[:4],
                                "classification": "real_gpu_work" if is_exec else "text_mention_only",
                                "exec_form_detected": is_exec, "cmdline": cl[:200]})
        if broad.search(cl):
            broad_hits.append({"pid": pid, "classification": "real_gpu_work" if is_exec else "text_mention_only",
                               "cmdline": cl[:200]})
    return {"measurement_status": "measured" if n_proc else "not_measured",
            "n_proc_scanned": n_proc, "excluded_own_pids": sorted(excl),
            "narrow_band_hits": narrow_hits, "broad_band_hits": broad_hits,
            "n_narrow": len(narrow_hits), "n_broad": len(broad_hits),
            "n_narrow_text_mention_only": sum(1 for h in narrow_hits if h["classification"] == "text_mention_only"),
            "scan_scope": "/proc（只读）", "no_root_filesystem_scans": True}


def self_probe(intent: tuple[str, ...]) -> dict[str, Any]:
    """93.8 对照探针：注入一条"只提到关键字、并非执行形态"的合成 cmdline。"""
    if not intent:
        return {"detected": False, "reason": "判据为空 ⇒ 探针不可运行"}
    synthetic = f"/bin/bash -c cd /repo && grep -n {intent[0]} harness/some_module.py"
    matched = [p for p in intent if p in synthetic]
    is_exec = bool(EXEC_FORM_RE.search(synthetic))
    classified = "real_gpu_work" if is_exec else "text_mention_only"
    # 反向：一条真实执行形态必须被判成 real_gpu_work
    positive = f"/root/venvs/pi05_sim/bin/python scripts/a2_egl_latency_remeasure.py --mode closed_loop"
    pos_is_exec = bool(EXEC_FORM_RE.search(positive))
    return {"injected_bad_form": synthetic,
            "detected": bool(matched) and classified == "text_mention_only",
            "matched_patterns": matched, "classification": classified,
            "positive_control": {"cmdline": positive, "exec_form_detected": pos_is_exec,
                                 "ok": pos_is_exec},
            "both_directions": (bool(matched) and classified == "text_mention_only" and pos_is_exec)}


def main() -> int:
    try:
        intent, broad, meta = load_patterns()
    except (OSError, RuntimeError, SyntaxError) as exc:
        print(json.dumps({"measurement_status": "not_measured", "error": f"{type(exc).__name__}: {exc}"},
                         ensure_ascii=False))
        return 4
    result = scan(intent, broad)
    probe = self_probe(intent)
    out = {"artifact": "f_probe_card_busy", "generated_at": _now(), "generator": "scripts/f_probe_card_busy.py",
           "line": "F", "read_only": True, "gpu_used": False, "policy_executed": False,
           "capability_claim": None, "citation_algo": CITATION_ALGO,
           "caliber_source": meta, "result": result, "pattern_coverage_probe": probe,
           "question": "窄档 gpu_intent 是否会把『只在文本里提到 GPU 关键字的纯 CPU 进程』判成占卡",
           "authority": "裁定 94.9-1② 的三网实测要求；缺陷族参照 B2 的 RR-B2-18",
           # 判词必须**同时**看两档：第一版只看窄档，于是宽档那一个 `text_mention_only`
           # 命中（实测 PID 214244，某线 heredoc 的文本里提到脚本路径）被漏掉 ⇒ 报了一个
           # 过绿的 verdict。F 自报并根因修（缺陷类 ⑲ 同族：判词的作用域比对象空间窄）。
           "verdict_caliber": "两档并判（窄档 gpu_intent + 宽档 other_line_script）；任一档出现 text_mention_only ⇒ 假阳性风险成立",
           "verdict": ("not_measured" if result.get("measurement_status") != "measured"
                       else ("false_positive_risk_confirmed"
                             if (result["n_narrow_text_mention_only"]
                                 or any(h["classification"] == "text_mention_only"
                                        for h in result["broad_band_hits"]))
                             else ("no_false_positive_this_moment"
                                   if (result["n_narrow"] + result["n_broad"]) == 0
                                   else "all_hits_are_real_gpu_work")))}
    if not probe["both_directions"]:
        out["verdict"] = "probe_failed"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"probe_card_busy_{stamp}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raw = path.read_bytes()
    print(json.dumps({"verdict": out["verdict"], "path": str(path.relative_to(ROOT)),
                      "sha256_12": hashlib.sha256(raw).hexdigest()[:12], "n_lines": raw.count(b"\n"),
                      "n_proc_scanned": result.get("n_proc_scanned"),
                      "n_narrow": result.get("n_narrow"), "n_broad": result.get("n_broad"),
                      "n_narrow_text_mention_only": result.get("n_narrow_text_mention_only"),
                      "n_broad_text_mention_only": sum(1 for h in (result.get("broad_band_hits") or [])
                                                       if h["classification"] == "text_mention_only"),
                      "broad_hits": [{k: h[k] for k in ("pid", "classification", "cmdline")}
                                     for h in (result.get("broad_band_hits") or [])][:6],
                      "verdict_caliber": out.get("verdict_caliber"),
                      "narrow_hits": [{k: h[k] for k in ("pid", "classification", "matched_patterns", "cmdline")}
                                      for h in (result.get("narrow_band_hits") or [])][:6],
                      "probe_both_directions": probe["both_directions"]}, ensure_ascii=False, indent=2))
    if out["verdict"] == "probe_failed":
        return 3
    if out["verdict"] == "not_measured":
        return 4
    return 5 if out["verdict"] == "false_positive_risk_confirmed" else 0


if __name__ == "__main__":
    sys.exit(main())
