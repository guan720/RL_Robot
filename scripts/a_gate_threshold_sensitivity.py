#!/usr/bin/env python3
"""A 线：受控成功门禁的 `final_rise` 阈值敏感性扫描（只读）。

监管备忘 2026-09-28 §二.A.3 要求：本线受控成功局的 `final_rise` 落在 0.0415–0.0466 m，
紧贴判据 v1.1 的 C5 门槛 `FINAL_RISE_MIN = 0.04`，因此必须给出阈值 ±0.005 的敏感性，
说明「2/20」这类数字是不是门槛的产物。

口径纪律：本脚本**不重新实现判据**，而是 import `scripts/b_gate_controlled_success.py`
的 `judge_file`，只改 `final_rise` 一个入参，其余（RISE_CAP、HOLD_PHASES_*、
unjudged 移出分母、三套账）全部沿用 B 的实现。因此本表的每一格都与 B 的门禁同源。

用法：
    python3 scripts/a_gate_threshold_sensitivity.py \
        [--dir runs/infra/lerobot_act_env_20260928] \
        [--thresholds 0.030,0.035,0.040,0.045,0.050] \
        [--json-out runs/infra/lerobot_act_env_20260928/gate_threshold_sensitivity_A.json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

DEFAULT_THRESHOLDS = (0.030, 0.035, 0.040, 0.045, 0.050)


def load_gate_module():
    path = Path(__file__).resolve().parent / "b_gate_controlled_success.py"
    spec = importlib.util.spec_from_file_location("b_gate_controlled_success", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def judge_at(gate, eval_path: Path, rise_cap: float, final_rise: float) -> dict:
    args = SimpleNamespace(rise_cap=rise_cap, final_rise=final_rise, assist_off=False)
    return gate.judge_file(str(eval_path), args)


def main() -> int:
    ap = argparse.ArgumentParser(description="受控成功门禁 final_rise 阈值敏感性（只读）")
    ap.add_argument("--dir", default="runs/infra/lerobot_act_env_20260928")
    ap.add_argument("--pattern", default="official_act_truth20_*.json")
    ap.add_argument("--thresholds", default=",".join(f"{t:.3f}" for t in DEFAULT_THRESHOLDS))
    ap.add_argument("--rise-cap", type=float, default=None, help="默认沿用门禁的 RISE_CAP")
    ap.add_argument("--baseline", type=float, default=0.040, help="判据 v1.1 的现行门槛，用于标 flip")
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()

    gate = load_gate_module()
    rise_cap = gate.RISE_CAP if a.rise_cap is None else float(a.rise_cap)
    thresholds = [float(x) for x in a.thresholds.split(",") if x.strip()]
    root = Path(a.dir)
    files = sorted(root.glob(a.pattern))
    if not files:
        raise SystemExit(f"[错误] {root} 下没有匹配 {a.pattern} 的评测产物")

    arms = []
    for path in files:
        entry: dict = {"arm": path.name[len("official_act_truth20_"):-len(".json")],
                       "file": path.name, "thresholds": {}}
        seedsets: dict[float, set] = {}
        blind = None
        for thr in thresholds:
            res = judge_at(gate, path, rise_cap, thr)
            if "error" in res:
                entry["error"] = res["error"]
                break
            blind = res.get("field_class") != "strict"
            acct = (res.get("accounts") or {}).get("policy_independent") or {}
            seeds = sorted(str(e["seed"]) for e in res.get("per_episode", [])
                           if e["verdict"] == "controlled_success")
            seedsets[thr] = set(seeds)
            entry["thresholds"][f"{thr:.3f}"] = {
                "controlled_success": acct.get("controlled_success"),
                "denominator": acct.get("denominator"),
                "provisional_pass": res.get("n_provisional_pass"),
                "flick": ((res.get("accounts") or {}).get("system_assisted") or {}).get("flick"),
                "insufficient_lift": acct.get("insufficient_lift"),
                "over_lift": acct.get("over_lift"),
                "gate_pass": res.get("gate_pass"),
                "seeds": seeds,
            }
            # 与阈值无关的裁定元数据，取任一轮即可（v1.2 起缺输入契约字段 = INVALID，
            # 这类臂的「受控成功 N/20」不是能力数字，必须在表里与 FAIL 分开显示）。
            if thr == thresholds[0]:
                entry["measurement_valid"] = res.get("measurement_valid")
                entry["gate_reason"] = res.get("gate_reason")
                entry["ic_status"] = (res.get("input_contract") or {}).get("status")
                entry["ic_blown_frames_frac"] = (res.get("input_contract") or {}).get("mean_blown_frames_frac")
                entry["composite_policy"] = res.get("composite_policy")
                entry["active_constraints"] = res.get("active_constraints")
        if "error" in entry:
            arms.append(entry)
            continue
        base = seedsets.get(a.baseline, set())
        entry["field_blind"] = bool(blind)
        # ±0.005 敏感带（与 B 的 docs/b_gate_threshold_sensitivity_20260928.md §2 同口径）：
        # 带内三格全等 = threshold_robust，否则 threshold_sensitive；全 0 单独归类，
        # 因为「0→0→0」既不是稳也不是敏感，是这条臂在该带内没有可判定的受控成功。
        band = [t for t in thresholds if abs(t - a.baseline) <= 0.005 + 1e-9]
        band_vals = [(entry["thresholds"][f"{t:.3f}"]["controlled_success"] or 0) for t in band]
        entry["band_thresholds"] = [f"{t:.3f}" for t in band]
        entry["band_values"] = band_vals
        entry["band_spread"] = (max(band_vals) - min(band_vals)) if band_vals else None
        entry["band_class"] = ("always_zero" if band_vals and max(band_vals) == 0
                               else ("threshold_robust" if band_vals and min(band_vals) == max(band_vals)
                                     else "threshold_sensitive"))
        entry["monotone"] = all(len(seedsets[t]) >= len(seedsets[t2])
                               for t, t2 in zip(thresholds, thresholds[1:]))
        entry["flip_vs_baseline"] = {
            f"{t:.3f}": {
                "gained": sorted(seedsets[t] - base),
                "lost": sorted(base - seedsets[t]),
                "delta": len(seedsets[t]) - len(base),
            } for t in thresholds if t != a.baseline
        }
        arms.append(entry)

    print("门禁构建：gate_version=%s gate_build=%s spec_sha256=%s"
          % (gate.GATE_VERSION, gate.GATE_BUILD, gate.GATE_SPEC_SHA))
    hdr = (f"{'arm':56s} " + " ".join(f"{t:>6.3f}" for t in thresholds)
           + "   blind  mono   verdict     band")
    print(hdr)
    print("-" * len(hdr))
    for e in arms:
        if "error" in e:
            print(f"{e['arm'][:56]:56s} ERROR {e['error']}")
            continue
        cells = " ".join(f"{(e['thresholds'][f'{t:.3f}']['controlled_success'] or 0):>6d}"
                         for t in thresholds)
        verdict = ("INVALID" if e.get("measurement_valid") is False
                   else ("BLIND" if e["field_blind"] else "ok"))
        print(f"{e['arm'][:56]:56s} {cells}   "
              f"{'YES' if e['field_blind'] else 'no':5s}  {'ok' if e['monotone'] else 'NON-MONOTONE'}"
              f"   {verdict:9s} {e.get('band_class', '-')}")

    judged = [e for e in arms if "error" not in e and not e["field_blind"]]
    valid = [e for e in judged if e.get("measurement_valid") is not False]
    n_by = lambda cls: sum(1 for e in valid if e.get("band_class") == cls)
    print(f"\n可判臂（字段等级 strict）：{len(judged)} / {len(arms)}；"
          f"其中测量有效 {len(valid)}、INVALID {len(judged) - len(valid)}；"
          f"rise_cap={rise_cap}，现行门槛 baseline={a.baseline:.3f}")
    band_txt = ", ".join(f"{t:.3f}" for t in thresholds if abs(t - a.baseline) <= 0.005 + 1e-9)
    print(f"±0.005 敏感带（{band_txt}，仅测量有效臂）：threshold_robust {n_by('threshold_robust')}、"
          f"threshold_sensitive {n_by('threshold_sensitive')}、always_zero {n_by('always_zero')}")
    for e in valid:
        if e.get("band_class") == "threshold_robust":
            print(f"  robust: {e['arm']} = {e['band_values']}")
    for t in thresholds:
        tot = sum((e["thresholds"][f"{t:.3f}"]["controlled_success"] or 0) for e in judged)
        den = sum((e["thresholds"][f"{t:.3f}"]["denominator"] or 0) for e in judged)
        narms = sum(1 for e in judged if (e["thresholds"][f"{t:.3f}"]["controlled_success"] or 0) > 0)
        print(f"  final_rise>={t:.3f}: 受控成功合计 {tot}/{den}，非零臂 {narms}/{len(judged)}")

    if a.json_out:
        out = {"rise_cap": rise_cap, "baseline": a.baseline, "thresholds": thresholds,
               "gate_impl": "scripts/b_gate_controlled_success.py::judge_file (imported, 未改写)",
               # 构建指纹必须随产物落盘：留档裁定若 build 不同就得重判（B 的教训，
               # 见 docs/b_handoff_to_a_20260928.md §4）。
               "gate_version": gate.GATE_VERSION, "gate_build": gate.GATE_BUILD,
               "gate_spec_sha256": gate.GATE_SPEC_SHA,
               "arms": arms}
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        print("写出:", a.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
