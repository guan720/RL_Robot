#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · 引用身份三元组的**生成器**（把「落笔时刻重读 sha」从自觉变成函数）。

## 为什么存在
D 执行单 §13-3（裁定 82.6）的原话要求：*「请把『落笔时刻重读 sha』做成你文书生成脚本里的一个函数，
不要靠自觉。」* 本线已两起同型事故（裁定 78.11 第一起：审计引 `387f78e2c49f`，磁盘已是 `6c4d71eb732e`；
裁定 82.6 第二起：`matrix.json` 引 generator `99159100eb59`，脚本在 16 秒后变成 `faf7cfc6ccd4`）。
两起的共同形态都是**沿用早先 run 里的值**，而不是落笔时重读。

## 裁定 92.3 的全仓最低 schema（本轮升级；升级前 = 95 ln `9f02a03c9e98`，前像已留）
D 在裁定 92.3 把 `prose_identity_must_be_verifiable_against_a_saved_artifact` **升为红线级**，并采 E 的
`scripts/e_write_identity_table.py` 的 schema 为全仓最低标准；本脚本与它**并存**（D 允许任一），
但产物 schema 必须满足该最低标准（**D 会抽查**）。逐条对齐：
  · `sha256_12` = **唯一可引用口径**；`sha1_12` 一并给出，**只为让「算法错配」一眼可见，不得被引用**
    （E 在 §E12.6 正是把 sha1[:12] 当 sha256[:12] 写进散文；D 据此新立缺陷类 ⑱）；
  · `n_lines`（`wc -l` 口径 = **换行符个数**，与散文里的「N ln」一致）+ `n_lines_splitlines` +
    `ends_with_newline` **三者都给**（前两者不等 ⇔ 文件不以换行结尾，这本身是一个可核事实）；
  · 每条带 `why_it_matters` + `citable_as`；
  · 顶层显式写 `citation_algo: "sha256[:12]"` + 算法口径出处（**硬要求 (ii)**）。

## 输入格式
`path[:line][|why_it_matters[|citable_as]]`，可多个。例：
  `harness/norm_contract.py:1295|红信息的唯一拼接点|分隔符权威`
`|` 之后的两段在**产物模式**（`--json` / `--out`）下是**必填**的（缺 ⇒ exit 6）：
工具能算出 sha，但算不出「这一条为什么重要」——那必须来自引用者，不许由工具编。

## 退出码（全集；0 是唯一可读作「成功」的码）
  0 = 全部引用成功，且产物模式下每条都带 why/citable
  2 = 路径不存在（**默认拒绝**：不静默跳过、不沿用旧值）
  4 = 空清单（裁定 88.3-2：空集上不许给出「通过」形状的产物）
  5 = `--allow-missing` 下存在缺失文件（表照产，但退出码非 0，且逐条记 `missing: true`）
  6 = 产物模式下有记录缺 `why_it_matters` 或 `citable_as`
  7 = `--out` 目标已存在（本仓 `overwrite_own_artifact`：拒绝覆写；要覆盖先自己留前像）

## 纪律
不写任何文件（除非 `--out`，且只准写 C2 自己的写入面 `docs/c2_*` / `runs/**/c2_*`）；
不用 `rm`；每个数字带口径；外部事实标 `external_unverified`（本脚本只处理本仓文件，无外部事实）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_WRITE_PREFIXES = ("docs/c2_", "runs/")
CITATION_ALGO = "sha256[:12]"
CITATION_ALGO_WHY = (
    "本仓口径 = `hashlib.sha256(raw_bytes).hexdigest()[:12]`（与 `scripts/e_write_identity_table.py`、"
    "`scripts/b2_identity_table.py:385`、D 的 §D88 抬头同口径）。`sha1_12` 一并给出，"
    "**只为让「算法错配」一眼可见，不得被引用**（裁定 92.3；E §E12.6 的错配即此形态）。")
LINE_COUNT_CONVENTION = ("n_lines = 换行符个数（= `wc -l`），与散文里的「N ln」一致；"
                         "n_lines_splitlines = `len(raw.splitlines())`；两者不等 ⇔ 文件不以换行结尾")


def _now() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _self_rel() -> str:
    """本脚本自己的相对路径。**不写死**：写死 `scripts/c2_cite.py` 而在别处（例：`tmp/` 里的候选稿）
    跑，就会产出一个「路径说 A、sha 其实是 B」的记录 —— 正是本工具存在要消灭的形态。"""
    fp = Path(__file__).resolve()
    try:
        return str(fp.relative_to(ROOT))
    except ValueError:
        return str(fp)


def load_pair() -> dict:
    """每个数字带口径：负载与 cgroup 节流计数（本仓配额 12 核）。"""
    la = " ".join(Path("/proc/loadavg").read_text().split()[:3]) if Path("/proc/loadavg").exists() else "unavailable"
    nt = None
    for cand in ("/sys/fs/cgroup/cpu,cpuacct/cpu.stat", "/sys/fs/cgroup/cpu.stat"):
        cp = Path(cand)
        if cp.exists():
            for line in cp.read_text().splitlines():
                if line.startswith("nr_throttled"):
                    nt = int(line.split()[1])
            break
    return {"loadavg": la, "nr_throttled": nt, "cgroup_quota_cores": 12}


def parse_spec(spec: str) -> tuple[str, int | None, str | None, str | None]:
    """`path[:line][|why[|citable]]` ⇒ 四元组。`|` 之后两段可缺（产物模式下由 main 拒绝）。"""
    parts = spec.split("|")
    loc = parts[0].strip()
    why = (parts[1].strip() or None) if len(parts) > 1 else None
    citable = (parts[2].strip() or None) if len(parts) > 2 else None
    if ":" in loc and not loc.startswith(":"):
        rel, _, ln = loc.rpartition(":")
        line_no = int(ln)
    else:
        rel, line_no = loc, None
    return rel, line_no, why, citable


def cite_one(spec: str, *, root: Path = ROOT, allow_missing: bool = False) -> dict:
    """**此刻**重读身份，不接任何缓存值（本脚本存在的全部理由）。"""
    rel, line_no, why, citable = parse_spec(spec)
    p = Path(rel) if Path(rel).is_absolute() else (root / rel)
    out: dict = {"path": rel, "missing": False, "line_no": line_no, "line_text": None,
                 "why_it_matters": why, "citable_as": citable, "read_at": _now()}
    if not p.is_file():
        out.update({"missing": True, "why_missing": ("路径不存在" if not p.exists() else "存在但不是普通文件"),
                    "as_of_mtime": None, "bytes": None, "n_lines": None,
                    "n_lines_splitlines": None, "ends_with_newline": None,
                    "sha256_12": None, "sha1_12": None})
        if not allow_missing:
            print(f"拒绝引用：路径不是本仓的普通文件 {rel}（不得沿用旧值、不得静默跳过）", file=sys.stderr)
            raise SystemExit(2)
        return out
    raw = p.read_bytes()
    st = p.stat()
    lines = raw.decode("utf-8", errors="replace").splitlines()
    try:
        out["path"] = str(p.relative_to(root))
    except ValueError:
        out["path"] = str(p)
    out.update({
        "bytes": len(raw),
        "n_lines": raw.count(b"\n"),                     # wc -l 口径（裁定 92.3）
        "n_lines_splitlines": len(lines),
        "ends_with_newline": raw.endswith(b"\n"),
        "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
        "sha1_12": hashlib.sha1(raw).hexdigest()[:12],   # 只为让算法错配一眼可见；**不得被引用**
        "as_of_mtime": _dt.datetime.fromtimestamp(st.st_mtime).astimezone().replace(microsecond=0).isoformat(),
        "line_text": (lines[line_no - 1].strip()[:160] if line_no and 1 <= line_no <= len(lines) else None),
    })
    if line_no and out["line_text"] is None:
        out["line_out_of_range"] = f"行号 {line_no} 超出 1..{len(lines)}（⇒ 引用的行号已漂移，必须重取）"
    return out


def to_markdown(recs: list[dict], meta: dict) -> str:
    hdr = (f"<!-- citation_algo: {meta['citation_algo']}（唯一可引用口径；sha1_12 不得被引用） · "
           f"generated_at: {meta['generated_at']} · generator: {meta['generator']['path']} "
           f"{meta['generator']['sha256_12']} -->\n")
    hdr += ("| 路径 | sha256-12（引用这个） | sha1-12（不得引用） | n_lines(wc -l) | n_lines(splitlines) "
            "| 末尾换行 | 字节 | as_of mtime | 行号 | 该行原文（截断 160） | 为什么重要 | 可被引用成 |\n")
    hdr += "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    rows = []
    for r in recs:
        if r.get("missing"):
            rows.append(f"| `{r['path']}` | **MISSING** | — | — | — | — | — | — | "
                        f"{r['line_no'] or '—'} | {r.get('why_missing')} | "
                        f"{r.get('why_it_matters') or '—'} | {r.get('citable_as') or '—'} |")
            continue
        rows.append(
            f"| `{r['path']}` | `{r['sha256_12']}` | `{r['sha1_12']}` | {r['n_lines']} "
            f"| {r['n_lines_splitlines']} | {str(r['ends_with_newline']).lower()} | {r['bytes']} "
            f"| {r['as_of_mtime']} | {r['line_no'] or '—'} "
            f"| {('`' + r['line_text'] + '`') if r['line_text'] else (r.get('line_out_of_range') or '—')} "
            f"| {r.get('why_it_matters') or '—'} | {r.get('citable_as') or '—'} |")
    return hdr + "\n".join(rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("specs", nargs="*", help="`path[:line][|why_it_matters[|citable_as]]`，可多个")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而不是 markdown 表（= 产物模式）")
    ap.add_argument("--out", help="落盘路径（只准写 C2 自己的写入面；= 产物模式）")
    ap.add_argument("--allow-missing", action="store_true",
                    help="缺失文件不退出，改为逐条记 `missing: true`，但最终退出码 = 5（不静默）")
    args = ap.parse_args()

    if not args.specs:
        print("拒绝出件：清单为空（裁定 88.3-2：空集上不许给出「通过」形状的产物）", file=sys.stderr)
        return 4
    recs = [cite_one(s, allow_missing=args.allow_missing) for s in args.specs]
    n_missing = sum(1 for r in recs if r.get("missing"))
    artifact_mode = bool(args.json or args.out)
    meta = {"artifact": "c2_citation_identity", "citation_algo": CITATION_ALGO,
            "citation_algo_why": CITATION_ALGO_WHY, "line_count_convention": LINE_COUNT_CONVENTION,
            "generated_at": _now(), "n_records": len(recs), "n_missing": n_missing,
            "generator": {"path": _self_rel(),
                          "sha256_12": hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()[:12],
                          "self_sha_caveat": ("本行是**必然过期**的：`records` 在写盘前采集，而本脚本自己的 sha "
                                              "在采集之后才可能被改 ⇒ 引用本脚本时请重跑本工具")},
            "load_pair": load_pair()}
    if artifact_mode:
        lacking = [r["path"] for r in recs
                   if not (r.get("why_it_matters") or "").strip() or not (r.get("citable_as") or "").strip()]
        if lacking:
            print("拒绝出件：产物模式（--json / --out）下每条必须带 why_it_matters + citable_as"
                  f"（裁定 92.3 最低 schema）。缺={lacking}", file=sys.stderr)
            return 6
    body = (json.dumps({**meta, "records": recs}, ensure_ascii=False, indent=2)
            if args.json else to_markdown(recs, meta))
    if args.out:
        op = Path(args.out)
        rel = str(op.relative_to(ROOT)) if op.is_absolute() and op.is_relative_to(ROOT) else str(op)
        if not rel.startswith(ALLOWED_WRITE_PREFIXES) or "c2_" not in rel:
            print(f"拒绝写出：{rel} 不在 C2 写入面（{ALLOWED_WRITE_PREFIXES} 且含 c2_）", file=sys.stderr)
            return 2
        if op.exists():
            print(f"拒绝覆写：{rel} 已存在（本仓 overwrite_own_artifact 纪律：要覆盖先自己留前像 + 记 sha256-12）",
                  file=sys.stderr)
            return 7
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(body, encoding="utf-8")
        print(f"written: {rel}")
    else:
        print(body)
    if n_missing:
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
