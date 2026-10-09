#!/usr/bin/env python3
"""A 线：评测器改动后的**恒等回归**（只读比对，不改任何既有产物）。

为什么需要它（A 线纪律「改评测器必须回归」，`docs/lerobot_act_env_setup_20260928.md` §21）：
`scripts/eval_lerobot_act_runtime.py` 每改一次，都必须在**同一 checkpoint / 同一题集
（seeds 5000-5019、horizon 300、无 guard）**上重跑一遍，并与留档产物做**全键递归比对**。
只允许两类差异，其余一律视为改动污染了既有口径：
  1. `rows[].elapsed_sec` —— 墙钟耗时，天然不可复现；
  2. 本次改动**新增**的键 —— 语义追加（如 `input_contract.blown_metric_impl`），
     不得改任何既有键的数值或类型。

比的是「产物树」而不是几个汇总数字：汇总数字相同但逐局字段变了的情况在本项目已经出现过
（`phase_trace` 分岔、`norm_input_blown_frames_frac` 口径疑云，见
`scripts/a_blown_metric_reconcile.py`），所以这里默认全键递归、不允许抽样。

用法：
    python3 scripts/a_eval_idempotence_check.py \
        --old runs/infra/lerobot_act_env_20260928/official_act_truth20_<arm>.json \
        --new /tmp/id_check.json \
        --out runs/infra/lerobot_act_env_20260928/evaluator_patch_regression_<arm>.json
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
from pathlib import Path

DEFAULT_ALLOW_VALUE = ("rows[].elapsed_sec",)

SUMMARY_KEYS = (
    "controller", "claim", "task", "episodes", "seed0", "horizon",
    "chunk_size", "n_action_steps", "replan_every", "log_actions",
    "temporal_ensemble_coeff", "pinned_object_seed", "versions", "checkpoint",
    "policy_config", "success_raw", "grasp_verified", "success_grasp_verified",
    "success_rise", "mean_max_rise", "mean_final_rise", "held_at_end_count",
    "terminal_kind_counts", "total_clip_events", "failure_phase_counts",
    "total_partial_events", "total_cancel_events",
)

ROW_EXACT_KEYS = ("seed", "max_rise", "final_rise", "phase_trace", "phase_at_end",
                  "held_at_end", "terminal_kind", "success_raw", "success_rise",
                  "grasp_verified", "steps", "chunk_count", "clip_events",
                  "max_preclip_abs_action", "norm_input_frames_measured",
                  "norm_input_blown_frames_frac", "norm_input_out_of_range_frames_frac",
                  "norm_input_absmax", "norm_input_top_dim")


def norm_path(path: str) -> str:
    """把 `$.rows[3].x` 归一成 `$.rows[].x`，便于按「字段种类」汇总差异。"""
    return re.sub(r"\[\d+\]", "[]", path)


def walk(old, new, path, diffs, new_keys, missing_keys):
    if isinstance(old, dict) and isinstance(new, dict):
        for k in old:
            if k not in new:
                missing_keys.append(f"{path}.{k}")
        for k in new:
            if k not in old:
                new_keys.append(f"{path}.{k}")
                continue
            walk(old[k], new[k], f"{path}.{k}", diffs, new_keys, missing_keys)
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            diffs.append({"path": path, "kind": "list_length", "old": len(old), "new": len(new)})
            return
        for i, (x, y) in enumerate(zip(old, new)):
            walk(x, y, f"{path}[{i}]", diffs, new_keys, missing_keys)
    else:
        if type(old) is not type(new) or old != new:
            diffs.append({"path": path, "kind": "value", "old": old, "new": new})


def main() -> int:
    ap = argparse.ArgumentParser(description="评测器恒等回归：两份产物全键递归比对（只读）")
    ap.add_argument("--old", required=True, help="留档产物（改动前）")
    ap.add_argument("--new", required=True, help="重跑产物（改动后）")
    ap.add_argument("--out", required=True, help="回归证据 JSON 落盘路径")
    ap.add_argument("--allow-value", action="append", default=None,
                    help=f"允许不同的字段（归一路径），可重复；默认 {list(DEFAULT_ALLOW_VALUE)}")
    args = ap.parse_args()

    raw_allowed = tuple(args.allow_value) if args.allow_value else DEFAULT_ALLOW_VALUE
    # 允许清单按归一路径比对，写 `rows[].elapsed_sec` 或 `$.rows[].elapsed_sec` 都认。
    allowed = tuple(a if a.startswith("$") else "$." + a.lstrip(".") for a in raw_allowed)
    old = json.loads(Path(args.old).read_text())
    new = json.loads(Path(args.new).read_text())

    diffs, new_keys, missing_keys = [], [], []
    walk(old, new, "$", diffs, new_keys, missing_keys)

    by_field = collections.Counter(norm_path(d["path"]) for d in diffs)
    nk = collections.Counter(new_keys)
    violations = [d for d in diffs if norm_path(d["path"]) not in allowed]

    summary_cmp = {k: {"old": old.get(k), "new": new.get(k),
                       "same": old.get(k) == new.get(k)} for k in SUMMARY_KEYS if k in old or k in new}
    rows_same = {}
    if isinstance(old.get("rows"), list) and isinstance(new.get("rows"), list) \
            and len(old["rows"]) == len(new["rows"]):
        for k in ROW_EXACT_KEYS:
            if all(k in a and k in b for a, b in zip(old["rows"], new["rows"])):
                rows_same[k] = all(a[k] == b[k] for a, b in zip(old["rows"], new["rows"]))

    verdict = "PASS" if not violations and not missing_keys else "FAIL"
    out = {
        "diagnostic": "evaluator_patch_idempotence_regression",
        "read_only": True,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "script": "scripts/a_eval_idempotence_check.py",
        "old_file": str(args.old),
        "new_file": str(args.new),
        "old_blown_metric_impl": (old.get("input_contract") or {}).get("blown_metric_impl"),
        "new_blown_metric_impl": (new.get("input_contract") or {}).get("blown_metric_impl"),
        "allowed_value_fields": list(allowed),
        "allowed_value_fields_as_given": list(raw_allowed),
        "verdict": verdict,
        "n_value_diffs_total": len(diffs),
        "n_value_diffs_violating": len(violations),
        "value_diff_fields": {k: v for k, v in sorted(by_field.items())},
        "new_keys_added": {k: v for k, v in sorted(nk.items())},
        "keys_missing_in_new": missing_keys,
        "violations": violations[:50],
        "summary_key_comparison": summary_cmp,
        "per_episode_exact_match": rows_same,
        "rule": ("全键递归比对；允许差异 = rows[].elapsed_sec + 本次改动新增的键。"
                 "任何既有键的数值/类型变化或键丢失都判 FAIL。"),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print(f"[恒等回归] verdict={verdict}")
    print(f"  值差异 {len(diffs)} 处，按字段：{dict(by_field)}")
    print(f"  违规（不在允许清单内）{len(violations)} 处")
    print(f"  新增键：{dict(nk)}")
    print(f"  丢失键：{len(missing_keys)} 处")
    bad_summary = [k for k, v in summary_cmp.items() if not v["same"]]
    print(f"  汇总键不一致：{bad_summary or '无'}")
    print(f"  逐局字段全等：{ {k: v for k, v in rows_same.items() if not v} or '全部全等' }")
    print(f"  证据写出: {args.out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
