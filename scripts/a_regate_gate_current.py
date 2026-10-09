#!/usr/bin/env python3
"""A 线：把本线全部官方臂的留档门禁裁定重判到**当前**门禁构建（只读后处理）。

为什么需要它：B 的门禁在 2026-09-28 一天内从 v1.1 升到 v1.2.1（`insufficient_lift` 从
`flick` 里分出、缺输入契约字段判 INVALID、输入侧约束计入 `composite_policy`），而 A 目录里的
41 份留档裁定停在 **4 个不同的 `gate_build`** 上（实测 v1.1×37 + v1.2×4）。这正是
`docs/b_handoff_to_a_20260928.md` §4 与 `scripts/b_regate_all.py` docstring 点名的产物漂移：
同一张表里的数字出自不同判据构建，跨臂比较与失效模式归因都不成立。

本脚本做三件事，全部只读评测产物、不改任何评测器、不改 B/C 的文件：
  1. 重判：对 `official_act_truth20_*.json` 逐臂调用 B 的 `judge_file`（**import，不复制判据**），
     用当前构建生成裁定，写到 `--out-dir`（默认 `regate_current/` 子目录）；
  2. 留档比对：读同名的旧 `gate_strict_<arm>.json`，逐臂 diff
     `gate_version / gate_build / controlled_success / flick / over_lift / insufficient_lift /
      measurement_valid / gate_pass`；
  3. 汇总：写 `regate_diff_current.json`，并打印「判据升级改了哪些数字」的表。

纪律：**不覆盖、不移动、不删除**旧裁定（旧产物是 v1.1 口径的证据，改判前后必须都能核）。
产物目录名不写死版本号 —— 门禁每升一次，写死在路径/文档里的版本就过期一次。

用法：
    python3 scripts/a_regate_gate_current.py \
        [--dir runs/infra/lerobot_act_env_20260928] \
        [--out-dir runs/infra/lerobot_act_env_20260928/regate_current]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

COUNT_KEYS = ("controlled_success", "provisional_pass", "over_lift", "flick", "insufficient_lift")


def load_gate_module():
    path = Path(__file__).resolve().parent / "b_gate_controlled_success.py"
    spec = importlib.util.spec_from_file_location("b_gate_controlled_success", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _unwrap(obj):
    """旧裁定有两种落盘形态：单臂 list（长度 1）或裸 dict。"""
    if isinstance(obj, list):
        return obj[0] if obj else {}
    return obj if isinstance(obj, dict) else {}


def summarize(g: dict) -> dict:
    indep = (g.get("accounts") or {}).get("policy_independent") or {}
    return {
        "gate_version": g.get("gate_version"),
        "gate_build": g.get("gate_build"),
        "field_class": g.get("field_class"),
        "denominator": indep.get("denominator"),
        **{k: indep.get(k) for k in COUNT_KEYS},
        "measurement_valid": g.get("measurement_valid"),
        "gate_pass": g.get("gate_pass"),
        "gate_reason": g.get("gate_reason"),
        "composite_policy": g.get("composite_policy"),
        "active_constraints": g.get("active_constraints"),
        "ic_status": (g.get("input_contract") or {}).get("status"),
        "ic_blown": (g.get("input_contract") or {}).get("mean_blown_frames_frac"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="把 A 线官方臂的留档裁定重判到当前门禁构建（只读）")
    ap.add_argument("--dir", default="runs/infra/lerobot_act_env_20260928")
    ap.add_argument("--out-dir", default=None,
                    help="默认 <dir>/regate_current；重判产物写这里，旧裁定一字节不动")
    ap.add_argument("--pattern", default="official_act_truth20_*.json")
    ap.add_argument("--rise-cap", type=float, default=0.15)
    ap.add_argument("--final-rise", type=float, default=0.04)
    args = ap.parse_args()

    root = Path(args.dir)
    out_dir = Path(args.out_dir) if args.out_dir else root / "regate_current"
    out_dir.mkdir(parents=True, exist_ok=True)

    gate = load_gate_module()
    gargs = SimpleNamespace(rise_cap=args.rise_cap, final_rise=args.final_rise, assist_off=False)
    print("当前门禁构建：gate_version=%s gate_build=%s spec_sha256=%s"
          % (gate.GATE_VERSION, gate.GATE_BUILD, gate.GATE_SPEC_SHA))

    evals = sorted(p for p in root.glob(args.pattern) if p.is_file())
    rows, n_changed_counts, n_changed_verdict = [], 0, 0
    for ev in evals:
        arm = ev.name[len("official_act_truth20_"):-len(".json")]
        new = _unwrap(gate.judge_file(str(ev), gargs))
        if "error" in new:
            print("SKIP %s: %s" % (arm, new["error"]))
            continue
        (out_dir / ("gate_%s.json" % arm)).write_text(
            json.dumps([new], ensure_ascii=False, indent=1))
        new_s = summarize(new)

        old_path = root / ("gate_strict_%s.json" % arm)
        old_s = None
        if old_path.exists():
            try:
                old_s = summarize(_unwrap(json.loads(old_path.read_text())))
            except json.JSONDecodeError:
                old_s = None

        changed_counts = bool(old_s) and any(old_s.get(k) != new_s.get(k) for k in COUNT_KEYS)
        changed_verdict = bool(old_s) and (old_s.get("gate_pass") != new_s.get("gate_pass")
                                           or old_s.get("measurement_valid") != new_s.get("measurement_valid"))
        n_changed_counts += int(changed_counts)
        n_changed_verdict += int(changed_verdict)
        rows.append({"arm": arm, "eval_file": ev.name,
                     "old": old_s, "new": new_s,
                     "counts_changed": changed_counts, "verdict_changed": changed_verdict})

    hdr = "%-52s %-9s %-9s %5s %5s %5s %5s %5s %5s %5s %5s %5s %8s %8s"
    print(hdr % ("arm", "old_ver", "new_ver", "o_cs", "n_cs", "o_fl", "n_fl", "o_ol", "n_ol",
                 "o_il", "n_il", "denom", "o_gate", "n_gate"))
    for r in rows:
        o, n = r["old"] or {}, r["new"]
        print(hdr % (r["arm"][:52], str(o.get("gate_version"))[:9], str(n.get("gate_version"))[:9],
                     o.get("controlled_success", "-"), n.get("controlled_success"),
                     o.get("flick", "-"), n.get("flick"),
                     o.get("over_lift", "-"), n.get("over_lift"),
                     o.get("insufficient_lift", "-"), n.get("insufficient_lift"),
                     n.get("denominator"),
                     ("INVALID" if o.get("measurement_valid") is False else
                      ("PASS" if o.get("gate_pass") else "FAIL")) if o else "-",
                     ("INVALID" if n.get("measurement_valid") is False else
                      ("PASS" if n.get("gate_pass") else "FAIL"))))

    diff = {
        "diagnostic": "regate_to_current_gate_build",
        "read_only": True,
        "gate_version": gate.GATE_VERSION, "gate_build": gate.GATE_BUILD,
        "gate_spec_sha256": gate.GATE_SPEC_SHA,
        "rise_cap": args.rise_cap, "final_rise_min": args.final_rise,
        "n_arms": len(rows),
        "n_old_builds": sorted({str((r["old"] or {}).get("gate_build")) for r in rows}),
        "n_counts_changed": n_changed_counts,
        "n_verdict_changed": n_changed_verdict,
        "claim": "只说明「同一份评测产物在新旧门禁构建下裁定是否一致」，不是能力结论",
        "arms": rows,
    }
    out = root / "regate_diff_current.json"
    out.write_text(json.dumps(diff, ensure_ascii=False, indent=1))
    print("\n臂数 %d；四类失效计数有变 %d 臂；gate_pass/measurement_valid 有变 %d 臂"
          % (len(rows), n_changed_counts, n_changed_verdict))
    print("旧裁定构建指纹集合：%s" % diff["n_old_builds"])
    print("写出：%s 与 %s/gate_*.json（旧 gate_strict_*.json 未改动）" % (out, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
