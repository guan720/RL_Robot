"""F 的散文身份串对账牙：**F 自己的文书里，每一个 `sha256[:12]` 都必须对得上实物。**

为什么需要它（不是理论，是 F 自己刚犯的）：F 在 `daily_report.md` 的 §F1.9 里**手写**了
一个前像身份串，与机器取值不符。这违反裁定 **92.3（红线级）**「身份串必须由工具在落笔
时刻生成、人不碰」，也属缺陷类 **⑱** 的"错值"半边（本案**没有**为它编造依据，故不构成
完整的 ⑱）。修字只治一次；本件是那颗**牙**：每轮扫 F 的文书，把「行内同时出现
仓内路径 + 12 位十六进制串」的地方逐个与实物对账，不一致 ⇒ 非零退出。

判据的三值与边界（都照既有纪律，F 不新设）：
  · `match` / `mismatch` / **`not_measured`**（路径不存在、或该行有多个候选无法归一 ⇒
    不猜，记 `not_measured`，绝不写成 `match`）。
  · **`declared_historical`**：行内带 `as_of`/`before`/`前像`/`历史值` 等标记时，串可能
    指向**已被覆写的旧版**⇒ 不判 mismatch，只登记（否则牙会恒红 = 恒真的闸等于没有闸，
    裁定 `always_true_gate_downgrade_rule`）。
  · **对照探针（裁定 93.8 / 缺陷类 ⑲）**：注入一行"路径真实、串故意写错"的合成文书 ⇒
    必须被检出为 `mismatch`；注入一行"串正确"的 ⇒ 必须 `match`。抓不到 ⇒ 本牙按
    `not_measured` 登记、**不得报绿**。

扫描作用域（裁定 94.9-2 `no_root_filesystem_scans`）：只扫 `docs/f_*.md` 与
`daily_report.md` 的 `## §F` 段落，以及其中引用到的仓内路径。**禁止 `find /`**。
退出码：0 = 全部对账通过；3 = 对照探针失败；4 = 有 `not_measured`；6 = 存在 `mismatch`。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CITATION_ALGO = "sha256[:12]"
HEX12 = re.compile(r"\b[0-9a-f]{12}\b")
# 路径形态**必须覆盖前像件**（`.beforeF1` / `.before_rev19` / `.INVALIDATED.json` 这类
# 没有常规扩展名的件）—— 第一版的扩展名白名单漏掉了它们，而那正是覆写纪律里最需要
# 对账的一类（缺陷类 ⑲：审计器的模式比对象空间窄）。
PATH_RX = re.compile(r"(?:docs|scripts|harness|registry|work|runs|policies|envs|eval|configs)/[\w./-]+"
                     r"|(?:[\w.-]+/)*[\w.-]+\.(?:md|py|json|jsonl|txt|sh|sqlite|npz|log)")
HISTORICAL_RX = re.compile(r"as_of|before|前像|历史值|旧版|beforeF|superseded|INVALIDATED|修前|改前")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def _digests(path: Path) -> dict[str, str] | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    return {"sha256_12": hashlib.sha256(raw).hexdigest()[:12],
            "sha1_12": hashlib.sha1(raw).hexdigest()[:12],
            "n_lines": raw.count(b"\n"), "n_bytes": len(raw)}


def _resolve(token: str) -> Path | None:
    """把行内出现的相对路径解析成盘上的实物；解析不到 ⇒ None（不猜）。"""
    cand = ROOT / token
    if cand.exists():
        return cand
    name = Path(token).name
    for prefix in ("docs", "scripts", "harness", "registry", "work", "runs/vla", "runs/infra"):
        hit = ROOT / prefix / name
        if hit.exists():
            return hit
    return None


def scan_text(text: str, origin: str, only_f_sections: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    in_f = not only_f_sections
    for lineno, line in enumerate(text.splitlines(), 1):
        if only_f_sections:
            if line.startswith("## "):
                in_f = "§F" in line
            if not in_f:
                continue
        hexes = HEX12.findall(line)
        if not hexes:
            continue
        paths = [p for p in PATH_RX.findall(line)]
        resolved = [(tok, _resolve(tok)) for tok in paths]
        resolved = [(tok, p) for tok, p in resolved if p is not None]
        if not resolved:
            for hexstr in hexes:
                rows.append({"origin": origin, "line": lineno, "sha_token": hexstr,
                             "status": "not_measured",
                             "reason": "行内有 12 位串但无可解析的仓内路径 ⇒ 不猜它指哪一件",
                             "excerpt": line.strip()[:160]})
            continue
        for hexstr in hexes:
            matched_to = None
            candidates = []
            resolvable_but_missing = []
            for tok, path in resolved:
                dig = _digests(path)
                if dig is None:
                    resolvable_but_missing.append(tok)
                    continue
                candidates.append({"path": tok, **dig})
                if hexstr in (dig["sha256_12"], dig["sha1_12"]):
                    matched_to = tok
            historical = bool(HISTORICAL_RX.search(line))
            if matched_to:
                status = "match"
            elif candidates:
                # **在盘可对账却对不上 ⇒ 一律 mismatch**，行内有"前像/as_of"字样也不豁免。
                # 第一版在这里无条件走 `declared_historical`，于是 F 自己那处手写错串
                # （前像件在盘、串却对不上）被放过 ⇒ 豁免过宽，等于牙有洞。
                status = "mismatch"
            elif historical and resolvable_but_missing:
                status = "declared_historical"
            elif len(resolved) > 1:
                status = "not_measured"
            else:
                status = "mismatch"
            rows.append({"origin": origin, "line": lineno, "sha_token": hexstr,
                         "matched_to": matched_to, "status": status,
                         "historical_marker": historical,
                         "resolvable_but_missing": resolvable_but_missing,
                         "candidates": candidates[:4], "excerpt": line.strip()[:160]})
    return rows


def self_probe(tmp: Path) -> dict[str, Any]:
    """93.8 对照探针：一正一反，两个方向都必须对。"""
    tmp.mkdir(parents=True, exist_ok=True)
    real = ROOT / "docs" / "f_task_selfintake_20260930.md"
    dig = _digests(real)
    if dig is None:
        return {"both_directions": False, "reason": f"{real} 读不到 ⇒ 探针不可运行"}
    good = tmp / "probe_good.md"
    good.write_text(f"# 合成\n\n身份 = `docs/f_task_selfintake_20260930.md` **{dig['sha256_12']}**\n",
                    encoding="utf-8")
    wrong = "000000000000"
    bad = tmp / "probe_bad.md"
    bad.write_text(f"# 合成\n\n身份 = `docs/f_task_selfintake_20260930.md` **{wrong}**\n",
                   encoding="utf-8")
    good_rows = scan_text(good.read_text(encoding="utf-8"), "probe_good.md")
    bad_rows = scan_text(bad.read_text(encoding="utf-8"), "probe_bad.md")
    good_ok = any(r["status"] == "match" for r in good_rows)
    bad_ok = any(r["status"] == "mismatch" and r["sha_token"] == wrong for r in bad_rows)
    # 第三向（本轮新加）：**带"前像"字样 + 串错 + 文件在盘** ⇒ 仍必须 mismatch。
    # 这一向正是 F 自己犯的形态；没有它，牙对自己的缺陷是盲的。
    hist = tmp / "probe_historical.md"
    hist.write_text(f"# 合成\n\n前像 `docs/f_task_selfintake_20260930.md`（**{wrong}**）\n",
                    encoding="utf-8")
    hist_rows = scan_text(hist.read_text(encoding="utf-8"), "probe_historical.md")
    hist_ok = any(r["status"] == "mismatch" and r["historical_marker"] for r in hist_rows)
    return {"injected_bad_form": f"路径真实、串故意写错（{wrong}）；另加一向：带『前像』字样同样必须检出",
            "detected": bool(bad_ok and hist_ok), "positive_control_ok": good_ok,
            "historical_marker_not_an_escape_hatch": hist_ok,
            "both_directions": bool(good_ok and bad_ok and hist_ok),
            "good_rows": good_rows[:2], "bad_rows": bad_rows[:2], "hist_rows": hist_rows[:2]}


def main() -> int:
    ap = argparse.ArgumentParser(description="F 的散文身份串对账牙（三值 + 93.8 对照探针）")
    ap.add_argument("--out-dir", default="runs/vla/f_oversight_20260930")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    probe = self_probe(out_dir / "f_probe")

    if args.selftest:
        print(json.dumps(probe, ensure_ascii=False, indent=2))
        return 0 if probe["both_directions"] else 3

    rows: list[dict[str, Any]] = []
    scanned: list[str] = []
    for doc in sorted((ROOT / "docs").glob("f_*.md")):
        scanned.append(str(doc.relative_to(ROOT)))
        rows += scan_text(doc.read_text(encoding="utf-8", errors="ignore"),
                          str(doc.relative_to(ROOT)))
    report = ROOT / "daily_report.md"
    if report.exists():
        scanned.append("daily_report.md（仅 ## §F 段落）")
        rows += scan_text(report.read_text(encoding="utf-8", errors="ignore"),
                          "daily_report.md", only_f_sections=True)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    out = {"artifact": "f_prose_identity_audit", "generated_at": _now(),
           "generator": "scripts/f_verify_prose_identities.py", "line": "F",
           "read_only": True, "gpu_used": False, "policy_executed": False,
           "capability_claim": None, "citation_algo": CITATION_ALGO,
           "authority": "裁定 92.3（红线级）· 缺陷类 ⑱ · 裁定 93.8 / 缺陷类 ⑲",
           "scan_scope": scanned, "no_root_filesystem_scans": True,
           "n_rows": len(rows), "counts": counts, "rows": rows,
           "pattern_coverage_probe": probe,
           "verdict": ("probe_failed" if not probe["both_directions"]
                       else "mismatch_found" if counts.get("mismatch")
                       else "has_not_measured" if counts.get("not_measured")
                       else "all_match_or_declared_historical")}
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"prose_identity_audit_{stamp}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raw = path.read_bytes()
    print(json.dumps({"verdict": out["verdict"], "counts": counts, "n_rows": len(rows),
                      "path": str(path.relative_to(ROOT)),
                      "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
                      "n_lines": raw.count(b"\n"),
                      "probe_both_directions": probe["both_directions"]}, ensure_ascii=False, indent=2))
    for row in rows:
        if row["status"] == "mismatch":
            print(f"  [MISMATCH] {row['origin']}:{row['line']} 串={row['sha_token']} "
                  f"candidates={[(c['path'], c['sha256_12']) for c in row['candidates']]}")
            print(f"             {row['excerpt'][:150]}")
    if out["verdict"] == "probe_failed":
        return 3
    if out["verdict"] == "mismatch_found":
        return 6
    return 4 if counts.get("not_measured") else 0


if __name__ == "__main__":
    sys.exit(main())
