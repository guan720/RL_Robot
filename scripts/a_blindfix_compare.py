#!/usr/bin/env python3
"""A 线：盲臂补测产物 vs 留档产物的**交集字段**比对（只读）。

背景（监管备忘 2026-09-28 增补三 §3 修正 + §9.A②）：44 份留档里有 5 份出自**旧评测器**，
不只缺 `input_contract`，还缺 10 个逐局门禁字段（`final_rise / held_at_end / phase_at_end /
terminal_kind / norm_input_*`），门禁只能判 `field_class=partial` + `measurement_invalid`。
处置选了「补测」而不是「作废」（checkpoint 都还在、协议一致），于是必须回答一个问题：
**补测有没有改变已有结论？**

比不了全键（旧产物键少），所以比**交集**：把补测产物按留档产物的键集裁剪，再做全键递归比对。
允许差异只有 `rows[].elapsed_sec`。交集上全等 ⇒ 补测只是**多写了字段**，
留档的 `success_raw / success_rise / max_rise` 等结论继续成立，可以安全地被 superseded；
交集上有差 ⇒ 旧评测器与当前评测器在核心口径上不一致，必须逐臂说明，不能笼统替换。

用法：
    python3 scripts/a_blindfix_compare.py \
        [--dir runs/infra/lerobot_act_env_20260928] [--sub blindfix] \
        [--out runs/infra/lerobot_act_env_20260928/blindfix/blindfix_vs_archived.json]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.a_eval_idempotence_check import norm_path, walk  # noqa: E402

ALLOWED_VALUE = ("$.rows[].elapsed_sec",)
CORE_KEYS = ("success_raw", "success_rise", "mean_max_rise", "grasp_verified",
             "episodes", "seed0", "horizon", "chunk_size", "n_action_steps")


def prune(new, old):
    """把 new 裁剪到 old 的键集（列表逐元素同构裁剪），得到可比对的交集视图。"""
    if isinstance(old, dict) and isinstance(new, dict):
        return {k: prune(new[k], old[k]) for k in old if k in new}
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return new
        return [prune(x, y) for x, y in zip(new, old)]
    return new


def added_keys(new, old, path="$", acc=None):
    acc = [] if acc is None else acc
    if isinstance(old, dict) and isinstance(new, dict):
        for k in new:
            if k not in old:
                acc.append(f"{path}.{k}")
            else:
                added_keys(new[k], old[k], f"{path}.{k}", acc)
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for i, (x, y) in enumerate(zip(new, old)):
            added_keys(x, y, f"{path}[]", acc)
    return acc


def main() -> int:
    ap = argparse.ArgumentParser(description="盲臂补测 vs 留档的交集字段比对（只读）")
    ap.add_argument("--dir", default="runs/infra/lerobot_act_env_20260928")
    ap.add_argument("--sub", default="blindfix")
    ap.add_argument("--pattern", default="official_act_truth20_*.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = Path(args.dir)
    sub = root / args.sub
    out_path = Path(args.out) if args.out else sub / "blindfix_vs_archived.json"

    arms = []
    for np_ in sorted(sub.glob(args.pattern)):
        old_p = root / np_.name
        rec = {"arm": np_.name[len("official_act_truth20_"):-len(".json")],
               "archived_file": str(old_p), "remeasured_file": str(np_)}
        if not old_p.exists():
            rec["verdict"] = "NO_ARCHIVED_COUNTERPART"
            arms.append(rec)
            continue
        old = json.loads(old_p.read_text())
        new = json.loads(np_.read_text())
        diffs, nk, mk = [], [], []
        walk(old, prune(new, old), "$", diffs, nk, mk)
        viol = [d for d in diffs if norm_path(d["path"]) not in ALLOWED_VALUE]
        rec.update({
            "verdict": "IDENTICAL_ON_COMMON_FIELDS" if not viol else "DIFFERS_ON_COMMON_FIELDS",
            "n_common_value_diffs": len(diffs),
            "n_common_value_diffs_violating": len(viol),
            "violating_fields": dict(collections.Counter(norm_path(d["path"]) for d in viol)),
            "violations": viol[:30],
            "newly_available_fields": sorted(set(added_keys(new, old))),
            "core_comparison": {k: {"archived": old.get(k), "remeasured": new.get(k),
                                    "same": old.get(k) == new.get(k)} for k in CORE_KEYS},
            "archived_blown_metric_impl": (old.get("input_contract") or {}).get("blown_metric_impl"),
            "remeasured_blown_metric_impl": (new.get("input_contract") or {}).get("blown_metric_impl"),
        })
        arms.append(rec)

    n_ident = sum(1 for a in arms if a.get("verdict") == "IDENTICAL_ON_COMMON_FIELDS")
    out = {
        "diagnostic": "blind_arm_remeasure_vs_archived",
        "read_only": True,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "script": "scripts/a_blindfix_compare.py",
        "supervision_ref": "监管备忘 2026-09-28 增补三 §3 修正 / §9.A②",
        "rule": ("按留档产物的键集裁剪补测产物后做全键递归比对；允许差异只有 rows[].elapsed_sec。"
                 "交集全等 ⇒ 补测只是多写门禁字段，留档结论可安全 superseded。"),
        "n_arms": len(arms),
        "n_identical_on_common_fields": n_ident,
        "n_differing": len(arms) - n_ident,
        "conclusion": (
            f"{n_ident}/{len(arms)} 臂在共有字段上逐位相同：补测只是把缺失的门禁字段补齐，"
            "没有改变任何留档结论；这 5 份旧产物可登记为 superseded（保留原件，不覆盖、不删除）。"
            if n_ident == len(arms) else
            f"只有 {n_ident}/{len(arms)} 臂在共有字段上相同，其余逐臂见 violating_fields，"
            "不得笼统替换留档结论。"),
        "arms": arms,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print(f"[盲臂补测比对] {n_ident}/{len(arms)} 臂共有字段逐位相同")
    for a in arms:
        cc = a.get("core_comparison") or {}
        bad = [k for k, v in cc.items() if not v["same"]]
        print(f"  {a['arm'][:46]:46s} {a['verdict']:30s} 新增字段 {len(a.get('newly_available_fields', []))} "
              f"核心键不一致 {bad or '无'}")
    print(f"  写出：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
