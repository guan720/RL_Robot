#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2 / `criteria_identity` **sidecar** 生成器（补单六 §四-② · `decisions` §100.3-（c）（d））。

## 为什么是 sidecar 而不是直接改判词件
`run3`/`run4` 的 `PREALIGN_VERIFICATION.json` 已经被 D 逐条引过 sha（`run4` = `2b396ea01978`、
151407 B）。**改它一个字节就会让 D 的引用失效**（身份漂移），所以本件把 `criteria_identity`
**追加**成同目录的 `CRITERIA_IDENTITY.json`：判词件本体不动，判据身份与它同目录、同批可核。
（新跑的判词件把 `criteria_identity` 直接写在件内，见 `scripts/a2_r1_r2_alignment_residual.py`。）

## 它写什么（§100.3-（c） 点名的三件）
1. **判据脚本 `sha256[:12]` + `n_lines_wc`**（外加 `n_lines_splitlines`/`bytes`，口径点名，
   裁定 98.3-②/98.5-②：**裸 `n_lines` 禁用**）；
2. **判据常量的 sha**：从判据脚本源码里**当场抽出** `moving_thresh` / `margin_required` 的默认值
   与 discrimination / 行内 verdict 的**原文行**，规范化后取 sha ⇒ 常量或规则一改，sha 就变；
3. **改前字节的前像状态**：三值 —— `measured`（当前在盘字节就是出判词那一版）/
   `not_measured`（改前字节不可复得，如 `run3`：`OPEN-L12-CRITERIA-DRIFT` 的事实本体）。

## 三值纪律
`--script-bytes-status not_recoverable` 时，**不拿当前在盘字节冒充出判词那一版**：
`judging_script_at_verdict_time` 里 sha/行数写 `null` + `measurement_status="not_measured"`，
第三方读数（F 的实测）**另立字段并注明来源**，不当成 A2 自己的复算。退出码 `3`。

## 用法
    /root/venvs/pi05_sim/bin/python scripts/a2_criteria_identity_sidecar.py \
        --run-dir runs/vla/a2_step1_prealign_20260930_run4 \
        --verdict-artifact PREALIGN_VERIFICATION.json \
        --verdict-time-sha ad77b2611475 --verdict-time-n-lines-wc 1720

    # run3 那一版字节不可复得（缺陷本体）：
    /root/venvs/pi05_sim/bin/python scripts/a2_criteria_identity_sidecar.py \
        --run-dir runs/vla/a2_step1_prealign_20260930_run3 \
        --verdict-artifact PREALIGN_VERIFICATION.json \
        --script-bytes-status not_recoverable \
        --third-party-reading 'F 的 §F4.2 实测：1617 ln(wc) / e7dd74482748'

退出码：`0` = measured 且与判词时刻同版 · `3` = 有 not_measured（含改前字节不可复得）·
`1` = 当前在盘字节与声明的判词时刻版本**不符**（响亮报，不静默）· `2` = 用法错。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CST = timezone(timedelta(hours=8))
N_LINES_CALIBER = ("n_lines_wc = 换行符个数（`wc -l`）；n_lines_splitlines = "
                   "len(read_text().splitlines())。末行无换行符 ⇒ 两口径差 1。"
                   "对账的唯一约束性判据 = sha256[:12]（裁定 98.3-①④ / 98.5-②）。")
EXIT_OK, EXIT_MISMATCH, EXIT_USAGE, EXIT_NOT_MEASURED = 0, 1, 2, 3
DEFAULT_JUDGING_SCRIPT = "scripts/a2_step1_prealign_verify.py"
# 判据常量与规则行：从源码里**抽**，不手写转录（手写转录就是不可核的来源）
RE_SIG = re.compile(r"def l12_action_time_alignment\((?P<sig>.*?)\)\s*->\s*dict:", re.S)
RE_DEFAULT = re.compile(r"(?P<name>moving_thresh|margin_required)\s*:\s*float\s*=\s*(?P<val>[-0-9.eE+]+)")
RULE_ANCHORS = (
    "step_mag = float(np.linalg.norm(target - ep_state[j]))",
    "high = bool(step_mag >= moving_thresh)",
    'wins = bool(ordered[0][0] == "aligned_action_j")',
    "beats_shifted = bool(shifted_best >= margin_required * a) if a > 0 else False",
    '"verdict": (("pass" if (wins and beats_shifted) else "fail") if high',
    'else "n_a_low_discrimination"),',
)


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sha12(path: pathlib.Path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except Exception:                                                # noqa: BLE001
        return None


def file_identity(rel: str) -> dict:
    p = REPO / rel
    out = {"path": rel, "exists": p.exists(), "as_of": now_iso(), "n_lines_caliber": N_LINES_CALIBER}
    if not p.exists():
        out.update({"measurement_status": "not_measured", "sha256_12": None, "bytes": None,
                    "n_lines_wc": None, "n_lines_splitlines": None,
                    "why": "路径不存在 ⇒ not_measured（不是「文件为空」）"})
        return out
    raw = p.read_bytes()
    txt = raw.decode("utf-8", errors="replace")
    out.update({"measurement_status": "measured",
                "sha256_12": hashlib.sha256(raw).hexdigest()[:12], "bytes": len(raw),
                "n_lines_wc": txt.count("\n"), "n_lines_splitlines": len(txt.splitlines()),
                "mtime": datetime.fromtimestamp(p.stat().st_mtime, CST).isoformat(timespec="seconds")})
    return out


def extract_criteria(rel: str) -> dict:
    """从判据脚本源码里**当场抽**常量与规则行，规范化后取 sha。抽不到 ⇒ `not_measured`。"""
    p = REPO / rel
    if not p.exists():
        return {"measurement_status": "not_measured", "why": f"{rel} 不存在", "constants": None,
                "sha256_12": None}
    src = p.read_text(encoding="utf-8")
    m = RE_SIG.search(src)
    consts, missing = {}, []
    if m:
        for dm in RE_DEFAULT.finditer(m.group("sig")):
            consts[dm.group("name")] = float(dm.group("val"))
    for k in ("moving_thresh", "margin_required"):
        if k not in consts:
            missing.append(k)
    lines = [ln.strip() for ln in src.splitlines()]
    rules, rules_missing = {}, []
    for a in RULE_ANCHORS:
        hit = [ln for ln in lines if ln == a.strip()]
        if hit:
            rules[a.strip()[:48]] = hit[0]
        else:
            rules_missing.append(a.strip()[:80])
    canon = json.dumps({"constants": consts, "discrimination_and_verdict_rule_lines": rules},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    ok = not missing and not rules_missing
    return {"measurement_status": "measured" if ok else "not_measured",
            "constants": consts, "constants_missing": missing,
            "discrimination_and_verdict_rule_lines": rules,
            "rule_lines_missing": rules_missing,
            "canonical_form_sha256_12": hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12],
            "extraction_caliber": ("常量取自 `def l12_action_time_alignment(...)` 的**形参默认值**；"
                                   "规则取自 discrimination / 行内 verdict 的**原文行**（逐字比对，"
                                   "不转录）⇒ 常量或规则一改，`canonical_form_sha256_12` 就变"),
            "why": (None if ok else f"抽取不完整：constants_missing={missing} "
                                    f"rule_lines_missing={rules_missing}")}


def main() -> int:
    ap = argparse.ArgumentParser(description="`criteria_identity` sidecar 生成器（不改判词件本体）")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--judging-script", default=DEFAULT_JUDGING_SCRIPT)
    ap.add_argument("--verdict-artifact", default="PREALIGN_VERIFICATION.json")
    ap.add_argument("--verdict-time-sha", default=None,
                    help="出判词那一刻的判据脚本 sha256[:12]（不给 ⇒ 只报当前在盘版本）")
    ap.add_argument("--verdict-time-n-lines-wc", type=int, default=None)
    ap.add_argument("--script-bytes-status", choices=["measured", "not_recoverable"],
                    default="measured",
                    help="`not_recoverable` = 改前字节不可复得（`OPEN-L12-CRITERIA-DRIFT` 的事实本体）")
    ap.add_argument("--third-party-reading", default=None,
                    help="别人对那一版的实测读数（**注明出处**，不当成 A2 自己的复算）")
    ap.add_argument("--tag", default="")
    ap.add_argument("--out-name", default="CRITERIA_IDENTITY.json")
    a = ap.parse_args()

    run_dir = pathlib.Path(a.run_dir)
    if not run_dir.is_absolute():
        run_dir = REPO / run_dir
    if not run_dir.is_dir():
        print(json.dumps({"ok": False, "exit_code": EXIT_USAGE, "error": f"run-dir 不存在：{run_dir}"},
                         ensure_ascii=False))
        return EXIT_USAGE
    verdict_path = run_dir / a.verdict_artifact
    cur = file_identity(a.judging_script)
    consts = extract_criteria(a.judging_script)
    unrecoverable = (a.script_bytes_status == "not_recoverable")

    at_verdict_time = {
        "measurement_status": "not_measured" if unrecoverable else
                              ("measured" if a.verdict_time_sha else "not_measured"),
        "sha256_12": (None if unrecoverable else a.verdict_time_sha),
        "n_lines_wc": (None if unrecoverable else a.verdict_time_n_lines_wc),
        "n_lines_caliber": N_LINES_CALIBER,
        "bytes": None,
        "third_party_reading": a.third_party_reading,
        "third_party_reading_note": ("**这是别人的读数，不是 A2 的复算**；A2 无法复算，"
                                     "因为改前字节不可复得（本件登记的就是这个缺口）")
                                    if a.third_party_reading else None,
        "why": ("改前字节不可复得 ⇒ `not_measured`（不用当前在盘字节顶替：那会把 "
                "`OPEN-L12-CRITERIA-DRIFT` 说成已解决）" if unrecoverable else
                (None if a.verdict_time_sha else "未提供 --verdict-time-sha")),
    }
    matches = (None if (unrecoverable or not a.verdict_time_sha)
               else bool(cur.get("sha256_12") == a.verdict_time_sha))
    doc = {
        "artifact": "a2_criteria_identity_sidecar", "as_of": now_iso(),
        "producer": {"script": "scripts/a2_criteria_identity_sidecar.py",
                     **{k: v for k, v in file_identity("scripts/a2_criteria_identity_sidecar.py").items()
                        if k in ("sha256_12", "bytes", "n_lines_wc", "n_lines_splitlines")},
                     "python": sys.version.split()[0], "venv": sys.executable},
        "required_by": ["rl_harness_supervision/d_handoff_to_a2_20260930.md 补单六 §四-②",
                        "work/decisions/decisions_20260929.md §100.3-（c）（d）",
                        "Ⅰ 类口径 judging_script_change_requires_before_image_and_criteria_identity"],
        "sidecar_not_inline_because": (
            f"`{a.verdict_artifact}` 的字节已被 D 逐条引用（改一个字节即身份漂移）⇒ "
            "`criteria_identity` 以**同目录 sidecar** 追加，判词件本体不动"),
        "run_dir": str(run_dir.relative_to(REPO)) if run_dir.is_relative_to(REPO) else str(run_dir),
        "verdict_artifact": {"path": a.verdict_artifact, "exists": verdict_path.exists(),
                             "sha256_12": sha12(verdict_path),
                             "bytes": (verdict_path.stat().st_size if verdict_path.exists() else None),
                             "n_lines_wc": (verdict_path.read_text(encoding='utf-8').count("\n")
                                            if verdict_path.exists() else None),
                             "n_lines_caliber": N_LINES_CALIBER,
                             "modified_by_this_tool": False},
        "judging_script_now_on_disk": cur,
        "judging_script_at_verdict_time": at_verdict_time,
        "current_bytes_are_the_verdict_time_version": matches,
        "criteria_constants": consts,
        "criteria_constants_extracted_from": {
            "path": a.judging_script, "sha256_12": cur.get("sha256_12"),
            "n_lines_wc": cur.get("n_lines_wc"),
            "is_the_verdict_time_version": matches,
            "caveat": (None if not unrecoverable else
                       "**这些常量是从「当前在盘字节」抽的，不是从出判词那一版抽的**（那一版不可复得）"
                       "⇒ 对本 run 只能作旁证，不能当判据同一性的证明；`criteria_identity."
                       "measurement_status` 因此是 `not_measured`"),
        },
        "criteria_identity": {
            "judging_script_sha256_12": cur.get("sha256_12"),
            "judging_script_n_lines_wc": cur.get("n_lines_wc"),
            "criteria_constants_sha256_12": consts.get("canonical_form_sha256_12"),
            "constants": consts.get("constants"),
            "discrimination_and_verdict_rule_lines": consts.get("discrimination_and_verdict_rule_lines"),
            "measurement_status": ("measured" if (cur.get("measurement_status") == "measured"
                                                 and consts.get("measurement_status") == "measured"
                                                 and not unrecoverable) else "not_measured"),
        },
        "open_defect": {
            "id": "OPEN-L12-CRITERIA-DRIFT",
            "applies_to_this_run": bool(unrecoverable),
            "status_for_this_run": ("**未销**：改前字节不可复得 ⇒ `criteria_drift` 无法逐字段比对"
                                    if unrecoverable else
                                    ("**本件已具备销账要件**：判据脚本身份 + 判据常量 sha + 规则原文行都在盘"
                                     if (matches or matches is None) else
                                     "**当前在盘字节与判词时刻那一版不符** ⇒ 见 mismatch")),
            "remaining_actions": [
                "① 判据脚本入库（下次经授权的提交带走；A2 不 `git commit`，B2 是 git 单写者）",
                "② 判词件带 `criteria_identity`（新件写在件内，旧件用本 sidecar）",
            ],
            "ruling": "decisions §100.3：`run4` 的 GREEN 仍被采信，但根据是 §100.1-① 的独立复算，"
                      "**不是**「漂移已排除」；过程不可核这件事不被结论可用掩盖",
        },
        "capability_claim": False, "policy_executed": False, "gpu_used": False,
        "success_rate_column": "not_an_exit_criterion",
        "note": "本件只登记判据身份，**不产任何判词**、不改任何既有产物字节、不用 `rm`",
    }
    if a.tag:
        doc["tag"] = a.tag
    txt = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    out_path = run_dir / a.out_name
    if out_path.exists():
        bi = run_dir / "before_images"
        bi.mkdir(parents=True, exist_ok=True)
        prior = bi / f"{a.out_name}.before_{sha12(out_path)}"
        if not prior.exists():
            prior.write_bytes(out_path.read_bytes())
        doc["before_image"] = {"path": str(prior.relative_to(REPO)), "sha256_12": sha12(prior),
                               "why": "覆盖已存在的 sidecar 前必须先留前像（Ⅰ 类口径，§100.3-（d））"}
        txt = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    out_path.write_text(txt, encoding="utf-8")
    ident = {"path": str(out_path.relative_to(REPO)), "sha256_12": sha12(out_path),
             "bytes": len(txt.encode("utf-8")), "n_lines_wc": txt.count("\n"),
             "n_lines_splitlines": len(txt.splitlines()), "n_lines_caliber": N_LINES_CALIBER}
    doc["self_identity"] = ident
    if matches is False:
        code = EXIT_MISMATCH
    elif unrecoverable or doc["criteria_identity"]["measurement_status"] != "measured":
        code = EXIT_NOT_MEASURED
    else:
        code = EXIT_OK
    print(json.dumps({"ok": code == EXIT_OK, "exit_code": code, "sidecar": ident,
                      "judging_script_now": {"sha256_12": cur.get("sha256_12"),
                                             "n_lines_wc": cur.get("n_lines_wc"),
                                             "n_lines_splitlines": cur.get("n_lines_splitlines")},
                      "current_bytes_are_the_verdict_time_version": matches,
                      "criteria_constants_sha256_12": consts.get("canonical_form_sha256_12"),
                      "constants": consts.get("constants"),
                      "constants_measurement_status": consts.get("measurement_status"),
                      "script_bytes_status": a.script_bytes_status,
                      "verdict_artifact_sha256_12": doc["verdict_artifact"]["sha256_12"],
                      "verdict_artifact_modified": False},
                     ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
