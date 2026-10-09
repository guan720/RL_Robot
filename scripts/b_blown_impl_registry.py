#!/usr/bin/env python3
"""B 线：blown_metric_impl 存量豁免册的登记与校验（监管 §12 分派 / DR-002 护栏 1）。

门禁 v1.3 的规则是「**新产物**缺 blown_metric_impl 指纹则拒判」。要让它可执行，就必须
有一个**能区分新旧**的机制。按 mtime 判新旧不可靠（mtime 会被 cp/rsync/NAS 改写），
所以这里用 DR-002 护栏 1 指定的登记模型：受版控的文本文件 + 逐产物 sha256 + 一个
**写死在册子里的 cutoff**。

带牙之处：
  1. cutoff 在册子首次创建时固化，之后的 --scan **拒绝**登记任何 mtime 晚于 cutoff 的产物
     —— 也就是说这个册子在时间上只能往回长，不能用来给新产物开脱；
  2. --verify 会重算每个条目的 sha256，产物被改写即报 drift（豁免不再成立）；
  3. --revoke 不删除条目，而是搬进 revoked 段（append-only，保留作废痕迹）；
  4. 册子本身受版控（git），改动会进提交历史，谁放行了什么可追溯。

用法：
  python scripts/b_blown_impl_registry.py --scan            # 扫默认 glob，登记存量产物
  python scripts/b_blown_impl_registry.py --scan --glob 'runs/infra/**/*.json' --dry-run
  python scripts/b_blown_impl_registry.py --verify          # 校验册子与产物是否仍然对得上
  python scripts/b_blown_impl_registry.py --revoke <sha256-prefix> --why "..."
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "configs" / "b_blown_impl_grandfathered.json"
DEFAULT_GLOBS = [
    "runs/infra/lerobot_act_env_20260928/official_act_truth20_*.json",
    "runs/infra/lerobot_act_env_20260928/*/*.json",
    "runs/infra/b_normclip*/*.json",
    "runs/infra/b_env_rebuild/*.json",
    "runs/infra/b_flick_sweep/*.json",
    "runs/infra/b_act_lift_*/*.json",
    "runs/infra/b_dzdeadband/*.json",
    "runs/infra/b_bc_retrain/**/*.json",
    "runs/20260924_*/*.json",
]
# 只登记「确实记录了 blown 字段却缺指纹」的产物：没记录 blown 字段的产物由 ic_status 的
# unverified / not_applicable 分支处理，不属于本册子的管辖范围（混进来会让册子变成万能豁免）。
BLOWN_ROW_FIELD = "norm_input_blown_frames_frac"
IMPL_KEY_PATH = ("input_contract", "blown_metric_impl")


def _now() -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def sha256_file(p: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
        return h.hexdigest()
    except Exception:                                   # noqa: BLE001
        return None


def load_doc() -> dict:
    if not DOC.exists():
        return {"_doc": ("blown_metric_impl 存量豁免册（监管 §12 分派 / DR-002 护栏 1）。"
                        "cutoff 之后产出的产物**不得**登记；门禁对册外且缺指纹的产物直接拒判。"),
                "cutoff": None, "created": None, "entries": {}, "revoked": {}}
    return json.loads(DOC.read_text(encoding="utf-8"))


def save_doc(doc: dict) -> None:
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def needs_grandfather(p: Path) -> tuple[bool, str]:
    """产物是否属于「有 blown 字段但缺 impl 指纹」的存量件。"""
    try:
        d = json.loads(p.read_text())
    except Exception as exc:                            # noqa: BLE001
        return False, "unreadable(%s)" % exc.__class__.__name__
    if not isinstance(d, dict):
        return False, "not_a_dict"
    rows = d.get("rows") or d.get("per_episode") or []
    if not isinstance(rows, list) or not rows:
        return False, "no_rows"
    n_with = sum(1 for r in rows if isinstance(r, dict) and r.get(BLOWN_ROW_FIELD) is not None)
    if n_with == 0:
        return False, "no_blown_field(%d rows)" % len(rows)
    blk = d.get(IMPL_KEY_PATH[0])
    impl = blk.get(IMPL_KEY_PATH[1]) if isinstance(blk, dict) else None
    if impl:
        return False, "has_impl(%s)" % impl
    return True, "blown_field=%d/%d, impl missing" % (n_with, len(rows))


def collect(globs: list[str]) -> list[Path]:
    out: dict[str, Path] = {}
    for g in globs:
        for p in ROOT.glob(g):
            if p.is_file():
                out[str(p.resolve())] = p
    return sorted(out.values(), key=lambda x: str(x))


def do_scan(globs, dry_run, reason) -> int:
    doc = load_doc()
    if not doc.get("cutoff"):
        doc["cutoff"] = _now()
        doc["created"] = doc["cutoff"]
        print("首次创建豁免册：cutoff 固化为 %s（此后产出的产物一律不得登记）" % doc["cutoff"])
    cutoff = dt.datetime.fromisoformat(doc["cutoff"])
    files = collect(globs)
    print("扫描 %d 个候选产物（%d 条 glob）" % (len(files), len(globs)))
    added = skipped = refused = dup = 0
    for p in files:
        need, why = needs_grandfather(p)
        if not need:
            skipped += 1
            continue
        sha = sha256_file(p)
        if not sha:
            continue
        if sha in doc["entries"]:
            dup += 1
            continue
        mt = dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone()
        rel = str(p.relative_to(ROOT))
        if mt > cutoff:
            refused += 1
            print("  ✗ 拒绝登记（mtime %s 晚于 cutoff %s）：%s" % (mt.isoformat(), doc["cutoff"], rel))
            print("      -> 这是**新产物**，必须用带 ADR-A-001 补丁的评测器重跑，不能靠豁免册放行")
            continue
        doc["entries"][sha] = {
            "path": rel, "recorded": _now(), "artifact_mtime": mt.replace(microsecond=0).isoformat(),
            "bytes": p.stat().st_size, "sha256": sha, "reason": reason, "scan_detail": why,
        }
        added += 1
        if added <= 8 or added % 25 == 0:
            print("  + %s  (%s)" % (rel, why))
    print("登记 %d，已存在 %d，不属于本册 %d，**拒绝** %d（cutoff 之后）"
          % (added, dup, skipped, refused))
    if dry_run:
        print("[dry-run] 未写盘")
        return 0
    save_doc(doc)
    print("写出 %s（entries=%d，revoked=%d）" % (DOC.relative_to(ROOT), len(doc["entries"]), len(doc.get("revoked", {}))))
    return 0


def do_verify() -> int:
    doc = load_doc()
    ents = doc.get("entries") or {}
    if not ents:
        print("豁免册为空 —— 门禁会对所有缺指纹产物拒判")
        return 0
    drift = gone = ok = 0
    for sha, e in sorted(ents.items(), key=lambda kv: kv[1].get("path", "")):
        p = ROOT / e["path"]
        if not p.exists():
            gone += 1
            print("  ✗ 产物已不存在：%s" % e["path"])
            continue
        got = sha256_file(p)
        if got != sha:
            drift += 1
            print("  ✗ sha256 漂移：%s\n      登记 %s\n      实测 %s\n      -> 豁免不再成立，须重新登记或重测"
                  % (e["path"], sha[:16], (got or "")[:16]))
        else:
            ok += 1
    print("豁免册校验：%d 条一致，%d 条漂移，%d 条产物缺失（共 %d 条，cutoff=%s）"
          % (ok, drift, gone, len(ents), doc.get("cutoff")))
    return 1 if (drift or gone) else 0


def do_revoke(prefix: str, why: str) -> int:
    doc = load_doc()
    ents = doc.get("entries") or {}
    hits = [s for s in ents if s.startswith(prefix)]
    if not hits:
        print("没有匹配 %r 的条目" % prefix)
        return 1
    doc.setdefault("revoked", {})
    for s in hits:
        doc["revoked"][s] = {**ents.pop(s), "revoked_at": _now(), "revoke_reason": why}
        print("  已作废 %s（%s）" % (s[:16], doc["revoked"][s]["path"]))
    save_doc(doc)
    print("剩余 entries=%d，revoked=%d" % (len(ents), len(doc["revoked"])))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="blown_metric_impl 存量豁免册")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--revoke", default=None, help="按 sha256 前缀作废条目（不删除，搬进 revoked）")
    ap.add_argument("--why", default="", help="--revoke 的理由（必填）")
    ap.add_argument("--glob", action="append", default=None, help="可重复；默认用内置 glob 列表")
    ap.add_argument("--reason", default=("存量产物：产出于 A 线 blown 口径单一来源化（ADR-A-001，"
                                        "impl=52eae25ee2d7）之前，按 DR-002 护栏 1 登记豁免"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.revoke:
        if not a.why.strip():
            print("✗ --revoke 必须给 --why（作废要留理由）")
            return 2
        return do_revoke(a.revoke, a.why.strip())
    if a.verify:
        return do_verify()
    if a.scan:
        return do_scan(a.glob or DEFAULT_GLOBS, a.dry_run, a.reason)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
