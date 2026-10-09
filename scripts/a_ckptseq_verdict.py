#!/usr/bin/env python3
"""A-2：训练侧种子双峰「分岔何时可观测」的判定器（**只读**，不训练、不评测、不改任何留档）。

判据、臂清单、判定规则全部来自**跑之前**冻结的预登记
`docs/a_bimodal_divergence_preregistration_20260928.md`（2026-09-28 21:14:53）：
  - 判别量：`dz_pos_frac_tail >= 0.9` 且 `dz_mean_tail ∈ [0.024, 0.034]` → `HIGH`；
    只满足前者 → `POS_BIAS`；`dz_pos_frac_tail < 0.9` → `NONPOS`（§2，阈值来自 6+6 seed 的**样本内**分离）；
  - 判定规则 R1–R6（§5）；R5（020000 重跑必须与留档一致）先于 R1–R4；
  - 分辨率上限（§3）：`checkpoints/last -> 020000` 是符号链接、`save_freq=10000`，
    每臂只有 010000 / 020000 两个互异 ckpt ⇒ 允许的措辞只有
    「分岔**不晚于 10k**」/「分岔**发生在 10k–20k 之间**」/「本分辨率下**未能定位**」。

本脚本刻意**不**推断因果、**不**输出更细的时间定位、**不**调整阈值。
`010000` 是该阈值的首次**样本外**使用，结果无论是否符合都原样落盘（增补四 §11-A④）。

用法：
    python3 scripts/a_ckptseq_verdict.py [--dir runs/infra/lerobot_act_env_20260928] \
        [--json-out .../ckptseq/divergence_verdict.json]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

# ---- 预登记冻结常量（§2 / §4 / §5），改这里等于改预登记，禁止 --------------------
POS_FRAC_THR = 0.9
DZ_MEAN_BAND = (0.024, 0.034)
STEPS = ("010000", "020000")
FAMILIES = {
    "K1_replan1": {
        "high_arm": "trimdone0_minmax_k1_lr1e-5_s20k_seed0",
        "low_arm": "trimdone0_minmax_k1_lr1e-5_s20k_seed4",
        "archived_controlled": {"trimdone0_minmax_k1_lr1e-5_s20k_seed0": 20,
                                "trimdone0_minmax_k1_lr1e-5_s20k_seed4": 0},
    },
    "K2_replan2": {
        "high_arm": "trimdone0_minmax_k2_lr1e-5_s20k_seed4",
        "low_arm": "trimdone0_minmax_k2_lr1e-5_s20k_seed2",
        "archived_controlled": {"trimdone0_minmax_k2_lr1e-5_s20k_seed4": 19,
                                "trimdone0_minmax_k2_lr1e-5_s20k_seed2": 0},
    },
}
BLOWN_TOLERANCE = 0.05
# R7（增补五 §5 追加的**报告义务**，不是判据变更）：dz_pos_frac_tail 落在 [0.85,0.95] 的
# (臂, ckpt) 必须同时报三种切法下的级别归属，且该族结论降级为「级别归属对阈值敏感」。
R7_SENSITIVE_BAND = (0.85, 0.95)
R7_CUTS = (0.85, 0.90, 0.95)
ALLOWED_WORDING = ("分岔不晚于 10k", "分岔发生在 10k–20k 之间", "本分辨率下未能定位分岔")
FORBIDDEN_WORDING = ("分岔发生在第 X 步", "在第 N 步附近", "炸穿导致", "轨迹完全一致")


def classify(dz_pos_frac_tail, dz_mean_tail, pos_thr=POS_FRAC_THR) -> str:
    """§2 的三级序数归属。缺值按 UNKNOWN 处理并另行标注（不得当成高分簇）。"""
    if dz_pos_frac_tail is None or dz_mean_tail is None:
        return "UNKNOWN"
    if dz_pos_frac_tail < pos_thr:
        return "NONPOS"
    lo, hi = DZ_MEAN_BAND
    return "HIGH" if lo <= dz_mean_tail <= hi else "POS_BIAS"


def r7_sensitivity(dz_pos_frac_tail, dz_mean_tail) -> dict:
    """R7：三种切点下的级别归属 + 是否落在敏感带。"""
    if dz_pos_frac_tail is None:
        return {"in_sensitive_band": False, "levels_by_cut": {}, "level_spans_cuts": None}
    lo, hi = R7_SENSITIVE_BAND
    levels = {f"{c:.2f}": classify(dz_pos_frac_tail, dz_mean_tail, c) for c in R7_CUTS}
    return {"in_sensitive_band": bool(lo <= dz_pos_frac_tail <= hi),
            "levels_by_cut": levels,
            "level_spans_cuts": len(set(levels.values())) > 1}


def _load(path: Path):
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if isinstance(d, list):
        return d[0] if d else None
    return d


def collect(directory: Path, dz_name: str = "dz_diag_ckptseq.json") -> dict:
    """把 ckptseq/ 下的 (臂, step) 三元组（actlog + gate + dz）收齐。"""
    ck = directory / "ckptseq"
    dz_doc = _load(ck / dz_name) or {}
    dz_by_arm = {a["arm"]: a for a in dz_doc.get("arms", []) if isinstance(a, dict)}
    out = {}
    for path in sorted(ck.glob("actlog_*__step*.json")):
        stem = path.name[len("actlog_"):-len(".json")]
        arm, _, step = stem.rpartition("__step")
        doc = _load(path) or {}
        gate = _load(ck / f"gate_{stem}.json") or {}
        dz = (dz_by_arm.get(stem) or {}).get("all") or {}
        ic_gate = gate.get("input_contract") or {}
        ic_eval = doc.get("input_contract") or {}
        acct = ((gate.get("accounts") or {}).get("policy_independent") or {})
        out[stem] = {
            "arm": arm, "step": step, "tag": stem,
            "checkpoint_sha8": (dz_by_arm.get(stem) or {}).get("checkpoint_sha8"),
            "episodes": doc.get("episodes"),
            "controlled_success": acct.get("controlled_success", gate.get("controlled_success")),
            "denominator": acct.get("denominator", gate.get("episodes_total")),
            "success_raw": doc.get("success_raw"),
            "success_rise": doc.get("success_rise"),
            "mean_max_rise": doc.get("mean_max_rise"),
            "mean_final_rise": doc.get("mean_final_rise"),
            "dz_pos_frac_tail": dz.get("dz_pos_frac_tail"),
            "dz_mean_tail": dz.get("dz_mean_tail"),
            "burst_frames_mean": dz.get("burst_frames"),
            "level": classify(dz.get("dz_pos_frac_tail"), dz.get("dz_mean_tail")),
            "r7": r7_sensitivity(dz.get("dz_pos_frac_tail"), dz.get("dz_mean_tail")),
            "input_contract": {
                "gate_status": ic_gate.get("status"),
                "mean_blown_frames_frac": ic_gate.get("mean_blown_frames_frac",
                                                      ic_eval.get("mean_blown_frames_frac")),
                "tolerance": ic_gate.get("tolerance", ic_eval.get("gate_tolerance")),
                "blowup_threshold": ic_eval.get("blowup_threshold"),
                "threshold_semantics": ic_eval.get("threshold_semantics"),
                "stats_file": ic_eval.get("stats_file"),
                "blown_metric_impl": ic_eval.get("blown_metric_impl"),
                "closed_loop_norm_absmax": ic_gate.get("closed_loop_norm_absmax"),
                "measurement_valid": gate.get("measurement_valid"),
                "field_class": gate.get("field_class"),
                "gate_build": gate.get("gate_build"),
                "gate_version": gate.get("gate_version"),
                "gate_file": f"ckptseq/gate_{stem}.json",
                # R4：blown 超阈 ⇒ 该时间点测量无效，不得用于分岔主张
                "invalid_for_divergence": bool(ic_gate.get("mean_blown_frames_frac") is not None
                                               and (ic_gate.get("tolerance") or BLOWN_TOLERANCE)
                                               and ic_gate["mean_blown_frames_frac"]
                                               > (ic_gate.get("tolerance") or BLOWN_TOLERANCE))
                or gate.get("measurement_valid") is False,
            },
            "rows": {int(r["seed"]): {"max_rise": r.get("max_rise"),
                                      "final_rise": r.get("final_rise"),
                                      "norm_input_blown_frames_frac":
                                          r.get("norm_input_blown_frames_frac")}
                     for r in doc.get("rows", []) if isinstance(r, dict) and "seed" in r},
        }
    return out


def check_r5(directory: Path, batch: dict) -> dict:
    """R5（先行门槛）：020000 重跑必须与留档 actlog / 留档 dz 归因一致，否则整批作废。"""
    archived_dz = _load(directory / "closed_loop_dz_diag_A.json") or {}
    dz_by_arm = {a["arm"]: (a.get("all") or {}) for a in archived_dz.get("arms", [])
                 if isinstance(a, dict)}
    per_arm, ok_all = {}, True
    for stem, rec in batch.items():
        if rec["step"] != "020000":
            continue
        arm = rec["arm"]
        arch = _load(directory / "actlog" / f"actlog_{arm}.json")
        entry = {"arm": arm, "archived_actlog": f"actlog/actlog_{arm}.json" if arch else None,
                 "row_diffs": [], "dz_diffs": [], "aggregate_diffs": [], "identical": None}
        if arch is None:
            entry["verdict"] = "NO_ARCHIVED_PRODUCT"
            ok_all = False
            per_arm[arm] = entry
            continue
        arows = {int(r["seed"]): r for r in arch.get("rows", []) if "seed" in r}
        for seed, vals in sorted(rec["rows"].items()):
            a = arows.get(seed)
            if a is None:
                entry["row_diffs"].append({"seed": seed, "field": "<missing_in_archived>"})
                continue
            for f in ("max_rise", "final_rise"):
                if vals.get(f) != a.get(f):
                    entry["row_diffs"].append({"seed": seed, "field": f,
                                               "rerun": vals.get(f), "archived": a.get(f)})
        adz = dz_by_arm.get(arm) or {}
        for f in ("dz_pos_frac_tail", "dz_mean_tail"):
            if adz and rec.get(f) != adz.get(f):
                entry["dz_diffs"].append({"field": f, "rerun": rec.get(f),
                                          "archived": adz.get(f)})
        for f in ("success_raw", "success_rise", "mean_max_rise", "mean_final_rise"):
            if arch.get(f) is not None and rec.get(f) is not None and arch[f] != rec[f]:
                entry["aggregate_diffs"].append({"field": f, "rerun": rec[f], "archived": arch[f]})
        entry["identical"] = not (entry["row_diffs"] or entry["dz_diffs"]
                                  or entry["aggregate_diffs"])
        entry["verdict"] = "IDENTICAL" if entry["identical"] else "DRIFT"
        ok_all = ok_all and entry["identical"]
        per_arm[arm] = entry
    return {"rule": "R5", "passed": ok_all,
            "criterion": ("020000 重跑的逐局 max_rise / final_rise 与 dz_pos_frac_tail / "
                          "dz_mean_tail 必须与留档 actlog + closed_loop_dz_diag_A.json 一致"),
            "consequence_if_failed": "整批作废重查（评测器或环境漂移），不得先解释分岔",
            "n_arms_checked": len(per_arm), "arms": per_arm}


def family_verdict(fam: str, spec: dict, batch: dict) -> dict:
    """§5 的 R1/R2/R3/R4，逐族判定；措辞只允许 ALLOWED_WORDING 里的三种。"""
    out = {"family": fam, "high_arm": spec["high_arm"], "low_arm": spec["low_arm"],
           "time_points": {}, "rules_evaluated": [], "verdict_rule": None,
           "allowed_wording": None, "notes": []}
    usable = {}
    for step in STEPS:
        cells = {}
        for role in ("high_arm", "low_arm"):
            arm = spec[role]
            rec = batch.get(f"{arm}__step{step}")
            if rec is None:
                cells[role] = {"arm": arm, "present": False}
                continue
            ic = rec["input_contract"]
            cells[role] = {
                "arm": arm, "present": True, "level": rec["level"],
                "dz_pos_frac_tail": rec["dz_pos_frac_tail"], "dz_mean_tail": rec["dz_mean_tail"],
                "r7_levels_by_cut": rec["r7"]["levels_by_cut"],
                "r7_in_sensitive_band": rec["r7"]["in_sensitive_band"],
                "controlled_success": rec["controlled_success"],
                "mean_max_rise": rec["mean_max_rise"],
                "checkpoint_sha8": rec["checkpoint_sha8"],
                "input_contract_status": ic["gate_status"],
                "mean_blown_frames_frac": ic["mean_blown_frames_frac"],
                "blowup_threshold": ic["blowup_threshold"],
                "measurement_valid": ic["measurement_valid"],
                "usable_for_divergence": not ic["invalid_for_divergence"],
            }
            if ic["invalid_for_divergence"]:
                out["rules_evaluated"].append(
                    f"R4:{arm}@{step} 测量无效（blown {ic['mean_blown_frames_frac']} > "
                    f"{ic['tolerance']}），该时间点不得用于分岔主张")
        out["time_points"][step] = cells
        h, l = cells.get("high_arm", {}), cells.get("low_arm", {})
        usable[step] = bool(h.get("present") and l.get("present")
                            and h.get("usable_for_divergence") and l.get("usable_for_divergence")
                            and h.get("level") not in (None, "UNKNOWN")
                            and l.get("level") not in (None, "UNKNOWN"))
        if usable[step]:
            out["time_points"][step]["separated"] = (h["level"] != l["level"])
        else:
            out["time_points"][step]["separated"] = None

    if not usable["020000"]:
        out["verdict_rule"] = "R4"
        out["allowed_wording"] = None
        out["notes"].append("020000 一侧不可用 ⇒ 该族降级为 R3 并登记原因（§5 R4）")
        return out
    if usable["010000"] and out["time_points"]["010000"]["separated"]:
        out["verdict_rule"] = "R1"
        out["allowed_wording"] = "分岔不晚于 10k"
    elif usable["010000"] and not out["time_points"]["010000"]["separated"] \
            and out["time_points"]["020000"]["separated"]:
        out["verdict_rule"] = "R2"
        out["allowed_wording"] = "分岔发生在 10k–20k 之间"
    elif not out["time_points"]["020000"]["separated"]:
        out["verdict_rule"] = "R3"
        out["allowed_wording"] = "本分辨率下未能定位分岔"
    else:
        out["verdict_rule"] = "R3"
        out["allowed_wording"] = "本分辨率下未能定位分岔"
        out["notes"].append("010000 不可用但 020000 已分开 ⇒ 按 §5 只能降级为 R3（不能主张不晚于 10k）")
    # R7：族级敏感标注 + 三切点下判定是否稳定
    sens = []
    for step in STEPS:
        for role in ("high_arm", "low_arm"):
            c = out["time_points"][step].get(role, {})
            if c.get("r7_in_sensitive_band"):
                sens.append({"step": step, "role": role, "arm": c["arm"],
                             "dz_pos_frac_tail": c["dz_pos_frac_tail"],
                             "levels_by_cut": c["r7_levels_by_cut"]})
    out["r7_sensitive_cells"] = sens
    out["r7_threshold_sensitive"] = bool(sens)
    if sens:
        out["notes"].append("R7：本族有 (臂, ckpt) 的 dz_pos_frac_tail 落在 [0.85,0.95] ⇒ "
                            "结论措辞必须带「**级别归属对阈值敏感**」标注（增补五 §5）")
    # 判定在三种切点下是否稳定（重新跑一遍 R1/R2/R3 的分离判据）
    stable = {}
    for cut in R7_CUTS:
        sep = {}
        for step in STEPS:
            lv = {}
            for role in ("high_arm", "low_arm"):
                rec = batch.get(f"{spec[role]}__step{step}")
                lv[role] = (None if rec is None or rec["input_contract"]["invalid_for_divergence"]
                            else classify(rec["dz_pos_frac_tail"], rec["dz_mean_tail"], cut))
            sep[step] = (None if None in lv.values() else lv["high_arm"] != lv["low_arm"])
        if sep["010000"]:
            stable[f"{cut:.2f}"] = "R1"
        elif sep["010000"] is False and sep["020000"]:
            stable[f"{cut:.2f}"] = "R2"
        elif sep["020000"] is False:
            stable[f"{cut:.2f}"] = "R3"
        else:
            stable[f"{cut:.2f}"] = "R3"
    out["verdict_by_cut"] = stable
    out["verdict_stable_across_cuts"] = len(set(stable.values())) == 1

    # 方向注记：10k 的级别与 20k 的成败是否同向（这是本次最重要的观测量之一）
    h10 = out["time_points"]["010000"].get("high_arm", {})
    l10 = out["time_points"]["010000"].get("low_arm", {})
    if h10.get("level") and l10.get("level"):
        out["level_at_10k_predicts_20k_outcome"] = bool(
            (h10["level"] in ("HIGH", "POS_BIAS")) != (l10["level"] in ("HIGH", "POS_BIAS"))
            and h10["level"] in ("HIGH", "POS_BIAS"))
        out["notes"].append(
            f"10k 级别：高分臂(20k 受控 {spec['archived_controlled'][spec['high_arm']]})="
            f"{h10['level']}，低分臂(20k 受控 {spec['archived_controlled'][spec['low_arm']]})="
            f"{l10['level']}；level_at_10k_predicts_20k_outcome="
            f"{out['level_at_10k_predicts_20k_outcome']}")
    return out


def extension_q1_q2(directory: Path, batch: dict) -> dict:
    """预登记 §10.5 的 Q1 / Q2（扩围前追加，判据不变）：把 `010000` 快照与 **20k 留档**拼起来。

    20k 侧不重跑：留档 actlog（`actlog/actlog_<arm>.json`）+ 留档 dz 归因
    （`closed_loop_dz_diag_A.json`）就是 020000 的权威产物，R5 已证 4 臂重跑与它逐局一致。
    `k2 seed0` 是 `VALID_probe_exonerated` 臂，按 §4 不进判据样本；stdfloor 是**另一个数据配方**，
    单列不并入 K=2 族计数（跨族不混尺）。
    """
    arch_dz = _load(directory / "closed_loop_dz_diag_A.json") or {}
    dz20 = {a["arm"]: (a.get("all") or {}) for a in arch_dz.get("arms", []) if isinstance(a, dict)}
    joined, skipped = [], []
    for stem, rec in sorted(batch.items()):
        if rec["step"] != "010000":
            continue
        arm = rec["arm"]
        if arm.endswith("_seed0") and "minmax_k2_lr1e-5_s20k_seed0" == arm.replace("trimdone0_", ""):
            skipped.append({"arm": arm, "reason": "VALID_probe_exonerated（裁定 10）⇒ 按 §4 不进判据样本"})
            continue
        a20 = _load(directory / "actlog" / f"actlog_{arm}.json")
        if a20 is None:
            skipped.append({"arm": arm, "reason": "无 20k 留档 actlog"})
            continue
        d20 = dz20.get(arm) or {}
        if "stdfloor" in arm:
            fam = "stdfloor（另一数据配方，单列）"
        elif "_k1_" in arm:
            fam = "K1_replan1"
        elif "_k2_" in arm:
            fam = "K2_replan2"
        else:
            fam = "other"
        ic = rec["input_contract"]
        den = rec["denominator"] or 20
        ctrl10 = rec["controlled_success"]
        joined.append({
            "arm": arm, "family": fam,
            "step010000": {
                "level": rec["level"], "dz_pos_frac_tail": rec["dz_pos_frac_tail"],
                "dz_mean_tail": rec["dz_mean_tail"], "controlled_success": ctrl10,
                "denominator": den, "mean_max_rise": rec["mean_max_rise"],
                "at_least_half": (None if ic["invalid_for_divergence"] else bool(
                    isinstance(ctrl10, int) and ctrl10 * 2 >= den)),
                "measurement_valid": ic["measurement_valid"],
                "input_contract_status": ic["gate_status"],
                "mean_blown_frames_frac": ic["mean_blown_frames_frac"],
                "blowup_threshold": ic["blowup_threshold"],
                "r7_in_sensitive_band": rec["r7"]["in_sensitive_band"],
                "r7_levels_by_cut": rec["r7"]["levels_by_cut"],
            },
            "step020000_archived": {
                "level": classify(d20.get("dz_pos_frac_tail"), d20.get("dz_mean_tail")),
                "dz_pos_frac_tail": d20.get("dz_pos_frac_tail"),
                "dz_mean_tail": d20.get("dz_mean_tail"),
                "controlled_success": None,  # 由调用方从 arms_summary 填（本脚本不重复门禁）
                "mean_max_rise": a20.get("mean_max_rise"),
                "success_raw": a20.get("success_raw"),
                "source": f"actlog/actlog_{arm}.json + closed_loop_dz_diag_A.json",
            },
        })
    # 20k 受控成功从权威表取（arms_summary.json 是唯一生产者）；取不到就留 None
    summary = _load(directory / "arms_summary.json") or {}
    ctrl20 = {r["arm"]: r.get("controlled_success")
              for r in (summary.get("arms") or []) if isinstance(r, dict)}
    for j in joined:
        j["step020000_archived"]["controlled_success"] = ctrl20.get(j["arm"])
        d = j["step020000_archived"].get("denominator")
        c = j["step020000_archived"]["controlled_success"]
        j["step020000_archived"]["at_least_half"] = (None if c is None else bool(c * 2 >= 20))

    q1, q2 = {}, {}
    for fam in sorted({j["family"] for j in joined}):
        sub = [j for j in joined if j["family"] == fam]
        lvl10 = {}
        for j in sub:
            lvl10[j["step010000"]["level"]] = lvl10.get(j["step010000"]["level"], 0) + 1
        half10 = [j["arm"] for j in sub if j["step010000"]["at_least_half"] is True]
        invalid10 = [j["arm"] for j in sub if j["step010000"]["at_least_half"] is None]
        half20 = [j["arm"] for j in sub if j["step020000_archived"]["at_least_half"] is True]
        high10 = {j["arm"] for j in sub if j["step010000"]["level"] == "HIGH"}
        high20 = {j["arm"] for j in sub if j["step020000_archived"]["level"] == "HIGH"}
        q1[fam] = {
            "n_arms": len(sub), "levels_at_010000": lvl10,
            "at_least_half_at_010000": {"n": len(half10), "arms": half10},
            "at_least_half_at_020000": {"n": len(half20), "arms": half20},
            "invalid_time_points_at_010000": invalid10,
            "promotion_criterion_1_met_at_010000": len(half10) >= 3,
            "promotion_criterion_1_met_at_020000": len(half20) >= 3,
            "criterion_1_rule": "增补四 §8 条件①：同族 ≥3 个 seed 受控成功 ≥ 半数（10/20）",
        }
        q2[fam] = {
            "HIGH_at_010000": sorted(high10), "HIGH_at_020000": sorted(high20),
            "overlap": sorted(high10 & high20),
            "overlap_n": len(high10 & high20),
            "disjoint": not (high10 & high20) and bool(high10 or high20),
            "half_overlap": sorted(set(half10) & set(half20)),
            "half_overlap_n": len(set(half10) & set(half20)),
        }
    # 样本外分离度（**描述统计，不是新判据**；增补四 §11-A④ 要求报样本外表现）：
    # 只用第一判据 dz_pos_frac_tail >= 0.9 切两半，看两半的受控成功分布，10k / 20k 各算一次。
    def separation(key_lvl: str, key_ctrl: str, key_valid: str) -> dict:
        hi, lo = [], []
        for j in joined:
            side = j[key_lvl]
            if side.get(key_valid) is False or side.get(key_ctrl) is None:
                continue  # 测量无效的时间点不参与（裁定 12：能力未知，不当 0 分用）
            (hi if (side.get("dz_pos_frac_tail") or 0) >= POS_FRAC_THR else lo).append(
                {"arm": j["arm"], "dz_pos_frac_tail": side.get("dz_pos_frac_tail"),
                 "controlled_success": side[key_ctrl], "level": side.get("level")})
        def stat(g):
            c = [x["controlled_success"] for x in g]
            return {"n": len(g), "mean_controlled": round(sum(c) / len(c), 3) if c else None,
                    "min": min(c) if c else None, "max": max(c) if c else None,
                    "arms": g}
        return {"cut": f"dz_pos_frac_tail >= {POS_FRAC_THR}", "above": stat(hi), "below": stat(lo),
                "excluded_invalid_time_points": [
                    j["arm"] for j in joined if j[key_lvl].get(key_valid) is False]}

    oos = {"step010000": separation("step010000", "controlled_success", "measurement_valid"),
           "step020000_archived": separation("step020000_archived", "controlled_success",
                                             "_never_invalid_placeholder")}
    # 20k 留档侧的有效性以 arms_summary 的 validity_class 为准
    summary_valid = {r["arm"]: r.get("validity_class")
                     for r in ((_load(directory / "arms_summary.json") or {}).get("arms") or [])
                     if isinstance(r, dict)}
    keep = []
    for x in oos["step020000_archived"]["above"]["arms"] + oos["step020000_archived"]["below"]["arms"]:
        if summary_valid.get(x["arm"]) != "invalid":
            keep.append(x)
    hi20 = [x for x in keep if (x["dz_pos_frac_tail"] or 0) >= POS_FRAC_THR]
    lo20 = [x for x in keep if (x["dz_pos_frac_tail"] or 0) < POS_FRAC_THR]

    def stat20(g):
        c = [x["controlled_success"] for x in g]
        return {"n": len(g), "mean_controlled": round(sum(c) / len(c), 3) if c else None,
                "min": min(c) if c else None, "max": max(c) if c else None, "arms": g}

    oos["step020000_archived"] = {
        "cut": f"dz_pos_frac_tail >= {POS_FRAC_THR}", "above": stat20(hi20), "below": stat20(lo20),
        "excluded_invalid_time_points": sorted(
            a for a, v in summary_valid.items() if v == "invalid"
            and a in {j["arm"] for j in joined})}
    oos["note"] = ("样本外表现按原样报告：`HIGH` 的 `dz_mean_tail ∈ [0.024,0.034]` 上界在 10k 上"
                   "**排除了一个 18/20 的臂**（stdfloor seed0，dz_mean_tail 0.03787 → 判 POS_BIAS），"
                   "说明带内判据在样本外**低估**能力；只用第一判据 dz_pos_frac_tail ≥ 0.9 切分时"
                   "两半的受控成功均值差见上。**阈值不改**（已冻结），如需改必须新写一份预登记。")

    return {"joined": joined, "skipped": skipped, "q1_promotion_criterion_at_10k": q1,
            "q2_high_set_overlap_10k_vs_20k": q2, "out_of_sample_separation": oos}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="runs/infra/lerobot_act_env_20260928")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--dz", default="dz_diag_ckptseq.json",
                    help="ckptseq/ 下的 dz 归因文件名（首批=dz_diag_ckptseq.json，"
                         "扩围后=dz_diag_ckptseq_all.json；两批各自留档，不覆盖）")
    args = ap.parse_args()
    directory = Path(args.dir)
    batch = collect(directory, args.dz)

    r5 = check_r5(directory, batch)
    fams = {f: family_verdict(f, s, batch) for f, s in FAMILIES.items()}

    # R6：族间是否矛盾（§5 举的是 R1 vs R3；任何跨族不一致都不得合并成跨口径主张）
    rules = {f: v["verdict_rule"] for f, v in fams.items()}
    distinct = sorted(set(rules.values()))
    r6 = {"rules_per_family": rules, "consistent": len(distinct) <= 1,
          "note": ("§5 R6 字面覆盖「一族 R1、另一族 R3」；本批观测到的族间关系见 rules_per_family。"
                   "只要跨族不一致，就只报族内结论，不得合并成跨口径主张，并触发 §7 扩围。")}

    # §7 扩围触发条件
    triggers = []
    if all(v["verdict_rule"] == "R3" for v in fams.values()):
        triggers.append("§7 条件1：两族都判 R3")
    if not r6["consistent"]:
        triggers.append("§7 条件2：两族结论矛盾（R6）")
    for f, v in fams.items():
        if v["verdict_rule"] == "R4":
            triggers.append(f"§7 条件3：{f} 因 R4 只剩单侧")
    if not r5["passed"]:
        triggers.append("R5 未过：整批作废重查，扩围无意义（先查评测器/环境漂移）")

    # 010000 快照 = 阈值的首次样本外使用（增补四 §11-A④），原样报告、不得回调阈值
    snap = []
    for stem, rec in sorted(batch.items()):
        if rec["step"] != "010000":
            continue
        snap.append({"arm": rec["arm"], "level": rec["level"],
                     "dz_pos_frac_tail": rec["dz_pos_frac_tail"],
                     "dz_mean_tail": rec["dz_mean_tail"],
                     "controlled_success": rec["controlled_success"],
                     "denominator": rec["denominator"],
                     "mean_max_rise": rec["mean_max_rise"],
                     "input_contract_status": rec["input_contract"]["gate_status"],
                     "mean_blown_frames_frac": rec["input_contract"]["mean_blown_frames_frac"],
                     "in_preregistered_first_batch": any(
                         rec["arm"] in (s["high_arm"], s["low_arm"]) for s in FAMILIES.values())})

    doc = {
        "diagnostic": "training_seed_bimodality_divergence_localization",
        "preregistration": "docs/a_bimodal_divergence_preregistration_20260928.md",
        "preregistration_frozen_at": "2026-09-28T21:14:53+08:00",
        "dz_source": f"ckptseq/{args.dz}",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "script": "scripts/a_ckptseq_verdict.py",
        "read_only": True,
        "discriminator": {"dz_pos_frac_tail_threshold": POS_FRAC_THR,
                          "dz_mean_tail_band": list(DZ_MEAN_BAND),
                          "levels": ["HIGH", "POS_BIAS", "NONPOS"],
                          "threshold_provenance": ("样本内分离（6 个 K=1 seed + 6 个 K=2 seed 的 20k 产物）；"
                                                   "010000 时间点为首批**样本外**使用，结果原样报告，"
                                                   "不得事后调整（增补四 §11-A④）")},
        "resolution_cap": {"distinct_checkpoints_per_arm": 2, "steps": list(STEPS),
                           "note": ("checkpoints/last -> 020000 是符号链接、save_freq=10000；"
                                    "禁止写「分岔发生在第 X 步」这类更细定位（§3）")},
        "allowed_wording": list(ALLOWED_WORDING),
        "forbidden_wording": list(FORBIDDEN_WORDING),
        "r5_consistency": r5,
        "families": fams,
        "r6_cross_family": r6,
        "extension_triggers": triggers,
        "snapshot_step010000": snap,
        "extension_q1_q2": extension_q1_q2(directory, batch),
        "batch": {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in sorted(batch.items())},
        "claim": ("只回答「双峰分岔在训练过程里何时**可观测**」；不主张任何训练动力学**因果**，"
                  "不主张跨口径（K=1 vs K=2）合并结论，不把 blown 超阈写成失败原因（裁定 12）。"),
    }

    # ---- 摘要打印 -----------------------------------------------------------
    print(f"R5（先行门槛）: {'PASS' if r5['passed'] else 'FAIL'}  "
          f"（{r5['n_arms_checked']} 臂的 020000 重跑 vs 留档）")
    for arm, e in r5["arms"].items():
        print(f"  - {arm}: {e['verdict']}"
              f"{'' if e['identical'] else '  diffs=' + json.dumps(e['row_diffs'] + e['dz_diffs'] + e['aggregate_diffs'], ensure_ascii=False)[:200]}")
    print()
    for f, v in fams.items():
        print(f"{f}: 判定={v['verdict_rule']}  允许措辞={v['allowed_wording']}")
        for step in STEPS:
            tp = v["time_points"][step]
            hs, ls = tp.get("high_arm", {}), tp.get("low_arm", {})
            print(f"   {step}: 高分臂 {hs.get('level')}(ctrl {hs.get('controlled_success')},"
                  f" dzpos {hs.get('dz_pos_frac_tail')}, dzmean {hs.get('dz_mean_tail')},"
                  f" blown {hs.get('mean_blown_frames_frac')})"
                  f" | 低分臂 {ls.get('level')}(ctrl {ls.get('controlled_success')},"
                  f" dzpos {ls.get('dz_pos_frac_tail')}, dzmean {ls.get('dz_mean_tail')},"
                  f" blown {ls.get('mean_blown_frames_frac')})"
                  f" | separated={tp.get('separated')}")
        print(f"   R7 敏感格: {[(x['step'], x['arm'].split('_')[-1], x['dz_pos_frac_tail'], x['levels_by_cut']) for x in v['r7_sensitive_cells']] or '无'}")
        print(f"   三切点判定: {v['verdict_by_cut']}  稳定={v['verdict_stable_across_cuts']}")
        for n in v["notes"]:
            print(f"   note: {n}")
    print()
    print(f"R6 跨族一致性: {r6['consistent']}  rules={r6['rules_per_family']}")
    print(f"扩围触发: {triggers or '无'}")
    print()
    print("010000 快照（阈值的样本外使用）:")
    for s in snap:
        print(f"  - {s['arm'][:52]:54} {s['level']:9} ctrl={s['controlled_success']}/{s['denominator']}"
              f" dzpos={s['dz_pos_frac_tail']} dzmean={s['dz_mean_tail']}"
              f" blown={s['mean_blown_frames_frac']} ({s['input_contract_status']})"
              f"{'  [首批]' if s['in_preregistered_first_batch'] else '  [扩围]'}")

    ext = doc["extension_q1_q2"]
    print()
    print("Q1 晋级条件① 在 010000 上是否成立（≥3 seed 受控 ≥ 半数）:")
    for fam, v in ext["q1_promotion_criterion_at_10k"].items():
        short = lambda names: [a.rsplit("_", 1)[-1] for a in names]
        inv = v["invalid_time_points_at_010000"]
        inv_txt = f"  INVALID 时间点={short(inv)}" if inv else ""
        print(f"  - {fam}: n={v['n_arms']} 级别={v['levels_at_010000']} "
              f"10k ≥半数={v['at_least_half_at_010000']['n']}{short(v['at_least_half_at_010000']['arms'])} "
              f"20k ≥半数={v['at_least_half_at_020000']['n']}{short(v['at_least_half_at_020000']['arms'])} "
              f"⇒ 条件① 10k={v['promotion_criterion_1_met_at_010000']} / "
              f"20k={v['promotion_criterion_1_met_at_020000']}{inv_txt}")
    print("Q2 HIGH 集合重叠（10k vs 20k 留档）:")
    for fam, v in ext["q2_high_set_overlap_10k_vs_20k"].items():
        short = lambda names: [a.rsplit("_", 1)[-1] for a in names]
        print(f"  - {fam}: HIGH@10k={short(v['HIGH_at_010000'])} "
              f"HIGH@20k={short(v['HIGH_at_020000'])} 重叠={v['overlap_n']} "
              f"≥半数集合重叠={v['half_overlap_n']} disjoint={v['disjoint']}")
    for sk in ext["skipped"]:
        print(f"  - 跳过: {sk['arm']}（{sk['reason']}）")
    print("样本外分离度（描述统计，阈值未改）:")
    for tp, v in ext["out_of_sample_separation"].items():
        if not isinstance(v, dict):
            continue
        a, b = v["above"], v["below"]
        print(f"  - {tp}: ≥0.9 n={a['n']} 均值={a['mean_controlled']} 区间=[{a['min']},{a['max']}] "
              f"| <0.9 n={b['n']} 均值={b['mean_controlled']} 区间=[{b['min']},{b['max']}] "
              f"| 排除 INVALID={v['excluded_invalid_time_points']}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        print(f"\n写出: {out}")


if __name__ == "__main__":
    main()
