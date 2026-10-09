#!/usr/bin/env python3
"""B-5：历史裁定归档 —— 把旧构建产出的 gate_*.json 按可引用性三分类钉死。

为什么需要它：监管 改判 7 规定「唯一可采信的构建是当前门禁构建」，但仓里躺着几十份
旧构建裁定（实测跨 6 个构建）。它们不会被删除（AGENTS.md 禁 rm），也不会被改写
（A 的写入范围），所以**必须有一份索引说明每一份还能不能用**，否则下一个人翻到
旧文件就会照着引用。B 自己就报过「43 份历史裁定漂移」，这条把它变成可核查的归档。

三分类（按**臂**判，文件级取汇总）：
  A `superseded_no_drift`    同臂有当前构建裁定，且逐格数字一致 -> 旧件仅为历史留档
  B `superseded_with_drift`  同臂有当前构建裁定，但计数/裁定/有效性有差异 -> **必须**引新件
  B2 `superseded_name_variant`  当前权威里的同臂换了名字（实测只有 blindfix 的 `_gatefields`
                             后缀一种）-> 归 B2 而不是 C，否则会报「孤臂」让人去追不存在的漏判
  C `orphan_no_counterpart`  当前构建下找不到同臂裁定，且 B2/D 两条规则都不适用
                             -> 不得引用，且需要人工确认是否漏判
  D `probe_output_not_delivery_arm`  B 自己的探针产物（`--clip-norm-input` 变体，
                             路径含 `/clipprobe/` 或臂名以 `_clipC<值>` 结尾）-> 本来就不是
                             交付臂，权威集里没有 counterpart 属预期，**无需人工追**

B2/D 两条是 2026-09-28 深夜补的：首版把 8 条记录一律判 C，实测其中 4 条是
`train24_lr1e-4_actionminmax_s20k` / `train24_lr1e-5_actionminmax_s40k` 的 blindfix 前身
（当前权威里叫 `..._gatefields`），另 4 条是 `clipprobe/regate_current/` 下的 clip 探针。
「8 个孤臂」是**分类缺陷造成的假信号**，不是 8 个漏判。

所有三类一律 `citable = false`：旧构建的裁定不具备可引用性，分类只回答
「差异有多大、要不要去追」。

用法：python scripts/b_archive_historical_rulings.py [--json-out ...]
"""
from __future__ import annotations
import argparse, glob as globmod, json, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 分类规则常量（改动须在 docs/b_agent_review_20260928.md §9 登记理由）
NAME_VARIANT_SUFFIXES = ("_gatefields",)     # blindfix 补测后权威集里的改名后缀（实测唯一一种）
PROBE_PATH_MARKERS = ("/clipprobe/",)        # B 自己的 clip 探针产物目录
PROBE_ARM_RE = re.compile(r"_clipC[0-9p.]+$")   # 臂名带 clip 阈值，如 ..._seed0_clipC12p469445
OLD_GLOBS = [
    "runs/infra/lerobot_act_env_20260928/gate_*.json",
    "runs/infra/lerobot_act_env_20260928/superseded_gate_v1.0/*.json",
    "runs/infra/lerobot_act_env_20260928/*/regate_current/*.json",
    "runs/infra/lerobot_act_env_20260928/reblown/regate_current/*.json",
]
CURRENT = ROOT / "runs/infra/b_official_arms/reclassification.json"
COUNT_KEYS = ("controlled_success", "provisional_pass", "over_lift", "flick", "insufficient_lift")


def load_current():
    """当前构建的权威裁定：臂名 -> 记录（来自 B③ 重分类表）。"""
    if not CURRENT.exists():
        return None, None
    d = json.loads(CURRENT.read_text(encoding="utf-8"))
    idx = {}
    for a in d.get("arms", []):
        idx[a["arm"]] = a
    return d, idx


def arm_of_gate_entry(name: str) -> str:
    """gate_<arm>.json / gate_all.json 里的条目名 -> 臂名。"""
    stem = name[:-5] if name.endswith(".json") else name
    for pre in ("gate_", "official_act_truth20_"):
        if stem.startswith(pre):
            stem = stem[len(pre):]
            break
    for suf in ("_gatefields",):
        if stem.endswith(suf):
            stem = stem[:-len(suf)]
    return stem


def iter_rulings(files):
    """把每份裁定文件摊平成 (file, arm, record) —— 兼容三种历史布局：
    顶层 list、{"results": [...]}、{"arms": {...}}。"""
    for f in files:
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception as exc:                            # noqa: BLE001
            yield f, None, {"_unreadable": str(exc)}
            continue
        recs = []
        if isinstance(d, list):
            recs = d
        elif isinstance(d, dict):
            for k in ("results", "arms", "rulings", "per_arm"):
                if isinstance(d.get(k), list):
                    recs = d[k]
                    break
                if isinstance(d.get(k), dict):
                    recs = list(d[k].values())
                    break
            else:
                recs = [d]                                  # 单臂裁定文件
        build = None
        ver = None
        if isinstance(d, dict):
            build = d.get("gate_build")
            ver = d.get("gate_version")
        if not recs:
            continue
        for r in recs:
            if not isinstance(r, dict):
                continue
            r = dict(r)
            r.setdefault("gate_build", build or r.get("gate_build"))
            r.setdefault("gate_version", ver or r.get("gate_version"))
            arm = r.get("arm") or arm_of_gate_entry(Path(str(r.get("file") or f)).name)
            yield f, arm, r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_official_arms/historical_archive.json"))
    a = ap.parse_args()

    cur_meta, cur_idx = load_current()
    if cur_idx is None:
        print("[FATAL] 找不到当前权威裁定 %s —— 先跑 scripts/b_official_arms_reclassification.py"
              % CURRENT.relative_to(ROOT))
        return 2
    files = sorted({p for g in OLD_GLOBS for p in globmod.glob(str(ROOT / g))})
    print("=" * 112)
    print("B-5 历史裁定归档")
    print("当前权威构建：gate_version=%s gate_build=%s spec=%s git=%s"
          % (cur_meta.get("gate_version"), cur_meta.get("gate_build"),
             cur_meta.get("gate_spec_sha256"), str(cur_meta.get("git_commit"))[:12]))
    print("当前权威裁定覆盖 %d 个臂（%s）" % (len(cur_idx), CURRENT.relative_to(ROOT)))
    print("扫到历史裁定文件 %d 份" % len(files))
    print("=" * 112)

    per_file, per_arm_rows = [], []
    for f in files:
        rel = str(Path(f).relative_to(ROOT))
        entries = [(arm, r) for _, arm, r in iter_rulings([f])]
        builds = Counter(str(r.get("gate_build")) for _, r in entries)
        cls_counter = Counter()
        arms = []
        for arm, r in entries:
            if r.get("_unreadable"):
                cls = "unreadable"
                drift = {"reason": r["_unreadable"]}
            else:
                cur = cur_idx.get(arm)
                counterpart_arm = arm
                resolution = None
                same_build = (str(r.get("gate_build")) == str(cur_meta.get("gate_build")))
                if cur is None:                       # 规则 B2：blindfix 改名（`_gatefields` 后缀）
                    for suf in NAME_VARIANT_SUFFIXES:
                        if arm + suf in cur_idx:
                            cur, counterpart_arm = cur_idx[arm + suf], arm + suf
                            resolution = ("B2_superseded_name_variant",
                                          {"counterpart": arm + suf,
                                           "rule": "arm + %r 命中当前权威（blindfix 补测改名）" % suf})
                            break
                if cur is None and (any(m in rel for m in PROBE_PATH_MARKERS)
                                    or PROBE_ARM_RE.search(arm)):
                    cls = "D_probe_output_not_delivery_arm"      # 规则 D：B 自己的探针产物
                    drift = {"reason": "clip 探针产物（--clip-norm-input 变体），不是交付臂；"
                                       "权威集无 counterpart 属预期，无需人工追",
                             "rule": "path contains %r 或 arm 匹配 %r"
                                     % (PROBE_PATH_MARKERS, PROBE_ARM_RE.pattern)}
                elif cur is None:
                    cls = "C_orphan_no_counterpart"
                    drift = {"reason": "当前构建下无同臂裁定（产物改名/被取代/不再纳入官方集）"}
                else:
                    diffs = {}
                    for k in COUNT_KEYS:
                        old = (r.get("accounts") or {}).get("policy_independent", {}).get(k) \
                            if isinstance(r.get("accounts"), dict) else r.get(k)
                        new = cur.get(k)
                        if old is not None and new is not None and old != new:
                            diffs[k] = {"old": old, "new": new}
                    for k in ("measurement_valid", "gate_pass"):
                        if k in r and r[k] != cur.get(k):
                            diffs[k] = {"old": r[k], "new": cur.get(k)}
                    old_ic = (r.get("input_contract") or {}).get("status") if isinstance(r.get("input_contract"), dict) else r.get("ic_status")
                    if old_ic is not None and old_ic != cur.get("ic_status"):
                        diffs["ic_status"] = {"old": old_ic, "new": cur.get("ic_status")}
                    cls = ("A_superseded_no_drift" if not diffs else "B_superseded_with_drift")
                    if same_build:
                        cls = "current_build_not_historical"
                    if resolution is not None:        # B2 优先：改名事实比有无漂移更重要
                        cls = resolution[0]
                        diffs["resolution"] = resolution[1]
                    drift = diffs
            cls_counter[cls] += 1
            arms.append({"arm": arm, "class": cls, "citable": False,
                         "gate_build": r.get("gate_build"), "gate_version": r.get("gate_version"),
                         "drift": drift,
                         "superseded_by": (None if cls.startswith("C") or cls.startswith("D")
                                           or cls == "unreadable"
                                           else "%s#%s" % (CURRENT.relative_to(ROOT), counterpart_arm))})
            per_arm_rows.append({"file": rel, **arms[-1]})
        per_file.append({
            "file": rel, "n_entries": len(entries), "builds_in_file": dict(builds),
            "classes": dict(cls_counter),
            "citable": False,
            "citation_class": "NOT_CITABLE_superseded_build",
            "note": ("监管 改判 7：唯一可采信的是当前构建。本文件仅为历史留档，"
                     "任何数字都必须回到 %s 取。" % CURRENT.relative_to(ROOT)),
            "arms": arms,
        })

    allcls = Counter(r["class"] for r in per_arm_rows)
    print("\n%-72s %5s %s" % ("历史裁定文件", "条目", "分类分布"))
    for pf in per_file:
        print("%-72s %5d %s" % (pf["file"][:72], pf["n_entries"], pf["classes"]))
    print("\n--- 按臂汇总（%d 条臂级记录，来自 %d 份文件）---" % (len(per_arm_rows), len(per_file)))
    for k, v in allcls.most_common():
        print("  %-32s %4d 条   citable=False" % (k, v))
    drift_arms = sorted({r["arm"] for r in per_arm_rows if r["class"] == "B_superseded_with_drift"})
    orphan_arms = sorted({r["arm"] for r in per_arm_rows if r["class"] == "C_orphan_no_counterpart"})
    name_variant_arms = sorted({r["arm"] for r in per_arm_rows
                                if r["class"] == "B2_superseded_name_variant"})
    probe_arms = sorted({r["arm"] for r in per_arm_rows
                         if r["class"] == "D_probe_output_not_delivery_arm"})
    print("\n  有漂移的臂（%d 个，必须引新件）：%s" % (len(drift_arms), ", ".join(drift_arms[:12]) + ("..." if len(drift_arms) > 12 else "")))
    print("  改名臂（%d 个，B2：权威集里换了名字，非漏判）：%s"
          % (len(name_variant_arms), ", ".join(name_variant_arms[:12]) or "（无）"))
    print("  探针臂（%d 个，D：本来就不是交付臂，非漏判）：%s"
          % (len(probe_arms), ", ".join(probe_arms[:12]) or "（无）"))
    print("  真孤臂（%d 个，当前构建无对应裁定且 B2/D 均不适用，需人工确认是否漏判）：%s"
          % (len(orphan_arms), ", ".join(orphan_arms[:12]) + ("..." if len(orphan_arms) > 12 else "") or "（无）"))

    outp = Path(a.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({
        "purpose": "历史裁定归档（B-5）。三类一律 citable=false；分类只回答差异有多大、要不要追。",
        "current_authority": {"path": str(CURRENT.relative_to(ROOT)),
                              "gate_version": cur_meta.get("gate_version"),
                              "gate_build": cur_meta.get("gate_build"),
                              "gate_spec_sha256": cur_meta.get("gate_spec_sha256"),
                              "git_commit": cur_meta.get("git_commit"),
                              "n_arms": len(cur_idx)},
        "ruling_ref": "监管 改判 7（唯一可采信构建）+ 增补三 §4（留档裁定 gate_build 不同必须重判）",
        "n_files": len(per_file), "n_arm_records": len(per_arm_rows),
        "class_counts": dict(allcls),
        "drift_arms": drift_arms, "orphan_arms": orphan_arms,
        "name_variant_arms": name_variant_arms, "probe_arms": probe_arms,
        "classification_rules": {
            "B2_suffixes": list(NAME_VARIANT_SUFFIXES),
            "D_path_markers": list(PROBE_PATH_MARKERS),
            "D_arm_regex": PROBE_ARM_RE.pattern,
            "note": "首版把 B2/D 两类一律判 C_orphan，产生 8 条假孤臂信号；本版按规则分流",
        },
        "files": per_file,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("\n写出:", outp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
