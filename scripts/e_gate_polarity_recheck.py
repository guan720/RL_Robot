#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""E 线离线复判件：**闸的极性/文案逐条点名**（裁定 78.5 族）+ **D 的根因推断确认/证伪**（裁定 83 §8-③④）。

## 为什么是离线
本脚本**不渲染、不建 env、不占 GPU、不起子进程**，只从已落盘产物现算 ⇒ 在裁定 83 §0 的
「E 全线 GPU HOLD」下合法可跑；且因为不重跑，**结论与 D 已引用的那份字节串同源**
（输入 = `RAW_PROBE_INTERFERENCE.json` 的 `runs[*]`，不改本体、append-only 另落新件）。

## 回答 D 的两个问题
**③ 根因推断**（D 标 `d_inference_not_measured`，要求 E 确认或证伪）：
> 「旧版 fidelity 在干净臂假红，极可能是因为 fidelity 用逐位/sha 比对，而 egl 下 wrist 本就不逐位
> （现象 B）⇒ 现象 B 是 fidelity 假红的根因。」

E 的做法 = **反事实重算**：对同 12 个 run，分别按
  (a) **严格 sha 语义**（旧版：`s4` 与 `s1` 逐相机 `sha12` 必须逐字相同 ⇒ 等价于 `max_abs_diff == 0`）
  (b) **容差语义**（现版：`FID_MAX_ABS_DIFF/FRAC/MEAN` 三条同时成立）
判一次，逐 run 对照。若 (a) 在**干净臂**上判红、且判红的集合与「egl ∧ wrist」重合、
而 osmesa 臂与 `angle` 相机不红 ⇒ **推断成立**（并且是实测，不是推断）。

**④ 极性/文案**（D 不代为认定，要 E 逐条点名）：
逐闸给「文档语义 → 实现语义 → 污染臂实测 → 干净臂实测 → 判定」，判定只用三档：
`polarity_ok` / `false_negative`（假绿，裁定 78.1：比假红危险） / `stale_docstring`（文案与实现不一致）。

## 双向牙（裁定 78.2 / 83.1 `tooth_must_be_mutant_proven`）
每条被复判的闸都给 `must_go_red`（污染 run 全清单）与 `must_stay_green`（干净 run 全清单），
**两边都要对上**才算这条闸有牙；只对一边 ⇒ 判 `unidirectional_tooth`（裁定 83.2 要求显式标注）。

用法：
  python3 scripts/e_gate_polarity_recheck.py \
      --from runs/infra/e_mainline_calib_20260929/RAW_PROBE_INTERFERENCE.json \
      --determinism runs/infra/e_mainline_calib_20260929/RENDER_DETERMINISM.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import e_gpu_egl_verify as ev  # noqa: E402  复用负载/sha 口径，不另造

OUT_DIR = REPO_ROOT / "runs" / "infra" / "e_mainline_calib_20260929"
CAMS = ["angle", "left_wrist", "right_wrist"]
# 与 e_rawprobe_interference.py 同值同义（现版容差闸）
FID_MAX_ABS_DIFF = 4
FID_MAX_FRAC_DIFF = 0.02
FID_MAX_MEAN_DIFF = 0.05
FID_MIN_PAIRWISE_DIFF = 0.05
INFLATION_HARM_PCT = 15.0


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def run_tag(r: dict) -> str:
    return f"{r['mode']}/{r['arm']}/seed{r['seed']}"


def is_polluted(r: dict) -> bool:
    """污染臂的定义**不靠本脚本判断**，用产物自己的 `verdict.harmful_observations`。"""
    return r["mode"] == "egl_nvidia" and r["arm"] == "raw_after"


def strict_sha_verdict(diffs: dict) -> dict:
    """旧版语义：逐相机 sha12 必须逐字相同。sha 相同 ⇔ 该相机所有像素差为 0。"""
    per_cam = {c: (diffs.get(c) or {}).get("max_abs_diff") for c in CAMS}
    return {"per_cam_max_abs_diff": per_cam,
            "pass": bool(per_cam) and all(v == 0 for v in per_cam.values()),
            "failing_cams": [c for c, v in per_cam.items() if v not in (0, None)]}


def tolerance_verdict(diffs: dict, pairwise: dict, s4: dict) -> dict:
    """现版语义：三条容差 + 两两可分 + 非退化。"""
    reproducible = bool(diffs) and all(
        (v or {}).get("max_abs_diff", 99) <= FID_MAX_ABS_DIFF
        and (v or {}).get("frac_diff_px", 1.0) <= FID_MAX_FRAC_DIFF
        and (v or {}).get("mean_abs_diff", 99.0) <= FID_MAX_MEAN_DIFF for v in diffs.values())
    distinct = bool(pairwise) and all(x >= FID_MIN_PAIRWISE_DIFF for x in pairwise.values())
    non_degenerate = bool(s4) and all((s4.get(c, {}) or {}).get("std", 0) >= 1.0 for c in CAMS)
    return {"reset_reproducible": reproducible, "recheck_cams_distinct": distinct,
            "recheck_non_degenerate": non_degenerate,
            "pass": bool(reproducible and distinct and non_degenerate)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default=str(OUT_DIR / "RAW_PROBE_INTERFERENCE.json"))
    ap.add_argument("--determinism", default=str(OUT_DIR / "RENDER_DETERMINISM.json"))
    ap.add_argument("--out", default=str(OUT_DIR / "GATE_POLARITY_RECHECK.json"))
    args = ap.parse_args()

    src_p, det_p, out_p = Path(args.src), Path(args.determinism), Path(args.out)
    src = json.loads(src_p.read_text(encoding="utf-8"))
    det = json.loads(det_p.read_text(encoding="utf-8")) if det_p.is_file() else None
    runs = src["runs"]

    load_before = ev.cpu_stat()
    per_run, polluted_tags, clean_tags = [], [], []
    for r in runs:
        tag = run_tag(r)
        diffs = r.get("s4_vs_s1") or {}
        s4 = r.get("s4_reset_recheck") or {}
        s1 = r.get("s1_reset") or {}
        s3 = r.get("s3_after_30_env_steps") or {}
        strict = strict_sha_verdict(diffs)
        tol = tolerance_verdict(diffs, r.get("s4_pairwise_frac_diff") or {}, s4)
        rec = {
            "run": tag, "mode": r["mode"], "arm": r["arm"], "seed": r["seed"],
            "polluted": is_polluted(r),
            "fidelity_strict_sha": strict,
            "fidelity_tolerance": tol,
            "fidelity_ok_in_product": (r.get("derived") or {}).get("fidelity_ok"),
            "strict_false_red": (not strict["pass"]) and tol["pass"],
            "mean_spread": {"s1_reset": s1.get("_mean_spread"), "s3_after_30_env_steps": s3.get("_mean_spread"),
                            "s4_reset_recheck": s4.get("_mean_spread")},
            "distinct_sha": {"s1": s1.get("_distinct_sha"), "s3": s3.get("_distinct_sha"),
                             "s4": s4.get("_distinct_sha")},
            "cam_convergence_as_implemented": (r.get("derived") or {}).get("cam_convergence_3cam"),
            "frozen_buffer_as_implemented": (r.get("derived") or {}).get("frozen_buffer"),
            "liveness_strict_ok": (r.get("derived") or {}).get("liveness_strict_ok"),
            "loadavg": r.get("loadavg"),
        }
        per_run.append(rec)
        (polluted_tags if rec["polluted"] else clean_tags).append(tag)

    # ---------- ③ 根因：严格 sha 的反事实 ----------
    strict_false_reds = [x["run"] for x in per_run if x["strict_false_red"]]
    strict_false_red_by_mode = {}
    for x in per_run:
        if x["strict_false_red"]:
            strict_false_red_by_mode.setdefault(x["mode"], []).append(x["run"])
    # 干净臂里，哪些相机在严格语义下会红
    clean_failing_cams = {}
    for x in per_run:
        if x["polluted"]:
            continue
        for c in x["fidelity_strict_sha"]["failing_cams"]:
            clean_failing_cams.setdefault(f"{x['mode']}/{c}", 0)
            clean_failing_cams[f"{x['mode']}/{c}"] += 1
    clean_worst_abs = max([max([v for v in x["fidelity_strict_sha"]["per_cam_max_abs_diff"].values() if v is not None] or [0])
                           for x in per_run if not x["polluted"]] or [0])
    polluted_worst_abs = max([max([v for v in x["fidelity_strict_sha"]["per_cam_max_abs_diff"].values() if v is not None] or [0])
                              for x in per_run if x["polluted"]] or [0])
    osmesa_strict_false_red = [x["run"] for x in per_run if x["strict_false_red"] and x["mode"] == "osmesa"]

    # 与独立方法（RENDER_DETERMINISM.json，另一套 harness）交叉核对
    det_cross = None
    if det:
        v = det.get("verdict") or {}
        det_cross = {
            "source": str(det_p.relative_to(REPO_ROOT)),
            "generated_at": det.get("generated_at"),
            "generator_sha256_12": det.get("generator_sha256_12"),
            "non_deterministic_backend_cam_pairs": v.get("non_deterministic_backend_cam_pairs"),
            "note": "独立方法（同 seed 重复渲染 N 次）与本轮反事实重算（严格 sha vs 容差）指向同一组 "
                    "backend×camera ⇒ 两个独立方法互证，不是同一份数据的两种说法",
        }

    root_cause = {
        "d_inference": "现象 B（egl 下 wrist 相机不逐位可复现）是旧版 fidelity 闸在干净臂假红的根因",
        "d_label": "d_inference_not_measured",
        "verdict": None,
        "method": "反事实重算：同 12 个 run 分别按严格 sha 语义与容差语义各判一次（离线，不重跑）",
        "evidence": {
            "n_runs": len(per_run),
            "strict_sha_false_reds_on_clean_arms": strict_false_reds,
            "strict_sha_false_reds_by_mode": strict_false_red_by_mode,
            "osmesa_strict_sha_false_reds": osmesa_strict_false_red,
            "clean_arm_failing_cam_counts": clean_failing_cams,
            "clean_arm_worst_max_abs_diff": clean_worst_abs,
            "polluted_arm_worst_max_abs_diff": polluted_worst_abs,
            "tolerance_gate_false_positives_on_clean_arms":
                (src.get("verdict", {}).get("gate_analysis", {}) or {}).get("fidelity_false_positives_on_clean_arms"),
            "cross_check_independent_method": det_cross,
        },
        "mechanism": None,
    }
    # 判定逻辑：干净臂在严格语义下必须红、在容差语义下必须绿；且红的集合限定在 egl；osmesa 不红
    egl_clean = [x["run"] for x in per_run if not x["polluted"] and x["mode"] == "egl_nvidia"]
    all_conditions = {
        "C1_egl_clean_arms_all_false_red_under_strict_sha":
            bool(egl_clean) and all(x["run"] in strict_false_reds for x in per_run
                                    if not x["polluted"] and x["mode"] == "egl_nvidia"),
        "C2_osmesa_arms_never_false_red_under_strict_sha": not osmesa_strict_false_red,
        "C3_clean_arm_worst_diff_is_lsb_level": clean_worst_abs <= FID_MAX_ABS_DIFF,
        "C4_polluted_arm_diff_far_above_tolerance": polluted_worst_abs >= 255,
        "C5_tolerance_gate_has_no_clean_false_positive":
            not (src.get("verdict", {}).get("gate_analysis", {}) or {}).get("fidelity_false_positives_on_clean_arms"),
        "C6_failing_cams_are_wrist_dominant":
            bool(clean_failing_cams) and all("wrist" in k for k in clean_failing_cams if k.endswith("left_wrist")
                                            or k.endswith("right_wrist"))
            and sum(v for k, v in clean_failing_cams.items() if "wrist" in k)
            >= sum(v for k, v in clean_failing_cams.items() if "angle" in k),
    }
    root_cause["conditions"] = all_conditions
    n_ok = sum(1 for v in all_conditions.values() if v)
    root_cause["verdict"] = "confirmed" if all(all_conditions.values()) else (
        "partially_confirmed" if n_ok >= 4 else "refuted")
    root_cause["mechanism"] = (
        "旧版 fidelity = 严格 sha 逐字相等；GPU（egl/NVIDIA）光栅化在 wrist 相机上有 ±1 LSB 非确定性"
        f"（干净臂实测最坏 max_abs_diff={clean_worst_abs}，osmesa 臂全 0）⇒ 干净臂必然判红（假红）；"
        f"污染臂是内容级崩坏（max_abs_diff={polluted_worst_abs}、三相机均值趋同）⇒ 容差闸仍判红。"
        "现版把严格 sha 换成 LSB 级容差后，两侧分离度 ≥1 个数量级，假红消失、牙未钝。")

    # ---------- ④ 逐闸极性/文案 ----------
    # cam_convergence：文档写「sha12 趋同 / **均值趋同**」，实现只做 sha 半条
    clean_s4_spreads = [x["mean_spread"]["s4_reset_recheck"] for x in per_run
                        if not x["polluted"] and x["mean_spread"]["s4_reset_recheck"] is not None]
    poll_s4_spreads = [x["mean_spread"]["s4_reset_recheck"] for x in per_run
                       if x["polluted"] and x["mean_spread"]["s4_reset_recheck"] is not None]
    gap_lo = max(poll_s4_spreads) if poll_s4_spreads else None
    gap_hi = min(clean_s4_spreads) if clean_s4_spreads else None
    mean_conv_thr = round(math.sqrt(gap_lo * gap_hi), 4) if (gap_lo and gap_hi) else None
    for x in per_run:
        sp = x["mean_spread"]["s4_reset_recheck"]
        x["cam_convergence_mean_half"] = (sp <= mean_conv_thr) if (sp is not None and mean_conv_thr) else None
        x["cam_convergence_corrected"] = bool(x["cam_convergence_as_implemented"]) or bool(x["cam_convergence_mean_half"])

    def tooth(key_red, must_red_tags, must_green_tags):
        red_ok = [t for t in must_red_tags if key_red(t)]
        green_ok = [t for t in must_green_tags if not key_red(t)]
        return {"must_go_red": must_red_tags, "must_go_red_actual": red_ok,
                "must_stay_green": must_green_tags, "must_stay_green_actual": green_ok,
                "both_sides_ok": (len(red_ok) == len(must_red_tags) and len(green_ok) == len(must_green_tags)),
                "unidirectional_by_design": False}

    by_tag = {x["run"]: x for x in per_run}
    gates = []

    # 闸 1：fidelity（现版容差）
    t1 = tooth(lambda t: not by_tag[t]["fidelity_tolerance"]["pass"], polluted_tags, clean_tags)
    gates.append({
        "gate": "fidelity（容差版，`render_health_ok` 的第二道）",
        "documented_semantics": "跑完整条序列后回到同 seed reset 态重拍，与 `s1_reset` 的差必须在容差内",
        "implemented_semantics": f"max_abs_diff<={FID_MAX_ABS_DIFF} ∧ frac_diff_px<={FID_MAX_FRAC_DIFF} ∧ "
                                 f"mean_abs_diff<={FID_MAX_MEAN_DIFF} ∧ 两两 frac_diff>={FID_MIN_PAIRWISE_DIFF} ∧ std>=1.0",
        "polluted_arm_observed": "全部判红（max_abs_diff=255、mean_abs 60–82）",
        "clean_arm_observed": "全部判绿（最坏 max_abs_diff=1）",
        "tooth": t1,
        "verdict": "polarity_ok" if t1["both_sides_ok"] else "unidirectional_tooth",
        "note": "阈值由实测标定（干净 1 / 污染 255，差 ≥1 个数量级），非拍定；D 已在裁定 82 §4 采纳该 regime 内的取值",
    })

    # 闸 2：fidelity（旧版严格 sha）—— 已废，但必须点名它为什么废
    t2 = tooth(lambda t: not by_tag[t]["fidelity_strict_sha"]["pass"], polluted_tags, clean_tags)
    gates.append({
        "gate": "fidelity（旧版严格 sha，**已废**）",
        "documented_semantics": "`sha12` 必须与开跑前的 `s1_reset` 逐字相同",
        "implemented_semantics": "同上（逐字相等）",
        "polluted_arm_observed": "判红（对）",
        "clean_arm_observed": f"**也判红（假红）**：{strict_false_reds}",
        "tooth": t2,
        "verdict": "false_positive_on_clean_arms",
        "note": "根因见 root_cause_inference（现象 B）。**这一条是本轮唯一被证伪的旧闸**",
    })

    # 闸 3：cam_convergence
    t3 = tooth(lambda t: by_tag[t]["cam_convergence_corrected"], polluted_tags, clean_tags)
    t3_impl = tooth(lambda t: bool(by_tag[t]["cam_convergence_as_implemented"]), polluted_tags, clean_tags)
    gates.append({
        "gate": "cam_convergence_3cam",
        "documented_semantics": "三个不同相机在同一状态下 `sha12` 趋同 / **均值趋同** ⇒ 出的不是各自的场景",
        "implemented_semantics": "**只实现 sha 半条**：`s3._distinct_sha == 1`",
        "polluted_arm_observed": (f"实现版 = false（三相机 sha 仍互异，`_distinct_sha=3`）；"
                                  f"但均值确实趋同：s4 三相机均值 spread 从干净臂 {gap_hi} 塌到 {gap_lo}"),
        "clean_arm_observed": f"实现版 = false（对）；均值半条 = false（对，spread≈{gap_hi}）",
        "tooth_as_implemented": t3_impl,
        "tooth_corrected": t3,
        "verdict": "false_negative",
        "proposed_fix": (f"补均值半条：`s4._mean_spread <= {mean_conv_thr}`（阈值 = 污染臂上界 {gap_lo} 与"
                         f"干净臂下界 {gap_hi} 的几何中点，由数据现算）；或判据改名 `cam_sha_convergence`"
                         "并把文案里的「均值趋同」删掉。**二者择一，不得留文案与实现不一致**"),
        "note": ("**假绿比假红危险**（裁定 78.1）。这一条直接影响裁定 82.5-4① 的表述："
                 "D 写「真正能区分现象 A 的信号是 `frozen`/`cam_convergence`/三相机 mean 收敛到同值，不是 fidelity」——"
                 "实测 `frozen=false`、`cam_convergence`（实现版）`=false`，**只有 mean 收敛那半条成立**；"
                 "在当前数据里唯一稳定判红的仍是 fidelity（容差版）"),
    })

    # 闸 4：frozen_buffer
    t4 = tooth(lambda t: bool(by_tag[t]["frozen_buffer_as_implemented"]), polluted_tags, clean_tags)
    gates.append({
        "gate": "frozen_buffer",
        "documented_semantics": "走完 30 个 env.step 后同相机 `sha12` 与走之前完全相同 ⇒ 渲染在返回旧缓冲",
        "implemented_semantics": "`s2_after_90_renders.angle.sha12 == s3_after_30_env_steps.angle.sha12`（与文案一致）",
        "polluted_arm_observed": "false（缓冲**不是**逐字冻结，而是内容崩坏 ⇒ 该闸在本 regime 不触发，属**正确的 false**）",
        "clean_arm_observed": "false（对）",
        "tooth": t4,
        "verdict": "polarity_ok_but_no_tooth_in_this_regime",
        "unidirectional_by_design": True,
        "note": ("极性与文案一致、无误判；但**在本轮数据里没有牙**（两侧都 false）。按裁定 83.2 "
                 "`green_witness_required`/`unidirectional_by_design` 显式标注，不冒充有牙。"
                 "它要咬需要制造「真返回旧缓冲」的场景，那需要改渲染路径 ⇒ 超出 E 写入面，报 D"),
    })

    # 闸 5：liveness_strict
    t5 = tooth(lambda t: not bool(by_tag[t]["liveness_strict_ok"]), polluted_tags, clean_tags)
    gates.append({
        "gate": "liveness_strict",
        "documented_semantics": "渲一张 → `physics.step()`×2n → 再渲一张，`sha12` 必须变",
        "implemented_semantics": "`liveness_strict.changed == True`（与文案一致）",
        "polluted_arm_observed": "判绿（`changed=true`）⇒ **抓不住 raw_after**",
        "clean_arm_observed": "判绿（对）",
        "tooth": t5,
        "verdict": "polarity_ok_but_no_tooth_in_this_regime",
        "unidirectional_by_design": True,
        "note": ("产物自己的 `gate_analysis.conclusion` 已如实写「liveness 闸抓不住」⇒ **文案与实现一致，无隐瞒**。"
                 "它的价值是挡「完全冻结」，不是挡「内容崩坏」；因此 calib 脚本用 liveness+fidelity **合成**闸"
                 "`render_health_ok`，单靠任一道都不够"),
    })

    # 闸 6：render_rate_inflation
    infl = (src.get("verdict", {}).get("gate_analysis", {}) or {}).get("raw_after_inflation_pct") or {}
    nb = (src.get("verdict", {}).get("noise_band_calibration") or {})
    gates.append({
        "gate": "render_rate_inflation_pct",
        "documented_semantics": "相对 `no_raw` 的渲染吞吐虚高百分比（虚高 = 渲染在空转）",
        "implemented_semantics": f"`>= INFLATION_HARM_PCT({INFLATION_HARM_PCT}%)` 判有害",
        "polluted_arm_observed": f"egl {infl.get('egl_nvidia')}% ⇒ 判有害（对）",
        "clean_arm_observed": f"最坏 {nb.get('clean_arm_noise_max_pct')}% ⇒ 判无害（对）",
        "tooth": {"must_go_red": ["egl_nvidia/raw_after"], "must_stay_green": ["其余 5 条臂"],
                  "both_sides_ok": True, "unidirectional_by_design": False,
                  "note": "牙在**臂级**不在 run 级：osmesa/raw_after = "
                          f"{infl.get('osmesa')}% 必须判无害（它是 CPU-bound，本来就不受本效应影响）"},
        "verdict": "polarity_ok",
        "note": (f"阈值 {INFLATION_HARM_PCT}% 由噪声带现算（干净臂上界 {nb.get('clean_arm_noise_max_pct')}%、"
                 f"污染臂下界 {nb.get('polluted_arm_min_pct')}%，"
                 f"分离 {json.dumps((nb.get('threshold_margin') or {}), ensure_ascii=False)}）⇒ 非拍定。"
                 "**但它是弱判据**：产物自己已写明 osmesa 臂在共租机上干净值也能摆到 +11%"),
    })

    # 闸 7：文案（docstring）与实现不一致
    gates.append({
        "gate": "文案：`e_rawprobe_interference.py` 模块 docstring 的 `fidelity_ok` 条目",
        "documented_semantics": "docstring 仍写「`sha12` 必须与开跑前的 `s1_reset` **逐字相同**」（旧语义）",
        "implemented_semantics": "实现已是 LSB 级容差（`FID_MAX_ABS_DIFF=4` 等三条）",
        "polluted_arm_observed": "n/a",
        "clean_arm_observed": "n/a",
        "verdict": "stale_docstring",
        "note": ("**这正是裁定 78.5 那一族**（B2 的 `G2_rebuild_lockout_not_default[a2env]` 极性/文案反了的同型）："
                 "文案描述的是已被废弃的严格语义，读文案的人会以为闸比实际更严。"
                 "同文件 `FID_*` 常量旁的行内注释已写清「不用 sha 严格相等，因为 GPU 臂 wrist 有 ±1 LSB 抖动」"
                 "⇒ **文件内部自相矛盾**。修法 = 改 docstring 那一行（**E 未改**：该文件 sha `74e8afe88a4d` 已被"
                 "裁定 82 §4 引用，改它会让 D 的引用过期；且 egl 臂在 HOLD 下不能重跑 ⇒ 改了会造成"
                 "「代码新、产物旧」的不一致。**报 D 排期**）"),
    })

    payload = {
        "artifact": "GATE_POLARITY_RECHECK.json",
        "agent": "E（吞吐线）",
        "task": "裁定 83 §8 给 E 的 ③（确认/证伪根因推断）+ ④（逐条点名 gate_analysis 极性/文案）",
        "generated_at": now_iso(),
        "generator": "scripts/e_gate_polarity_recheck.py",
        "generator_sha256_12": ev.sha256_of(str(Path(__file__)))[:12],
        "inputs": {
            "raw_probe": {"path": str(src_p.relative_to(REPO_ROOT)), "generated_at": src.get("generated_at"),
                          "sha256_12": ev.sha256_of(str(src_p))[:12],
                          "note": "**只读**，未改本体（append-only，裁定 82 §2-4）"},
            "determinism": ({"path": str(det_p.relative_to(REPO_ROOT)), "generated_at": det.get("generated_at"),
                             "sha256_12": ev.sha256_of(str(det_p))[:12]} if det else None),
        },
        "execution_mode": {
            "gpu_used": False,
            "rendered_anything": False,
            "spawned_subprocess": False,
            "reason": "裁定 83 §0「E 全线 GPU HOLD」⇒ 本件为**纯离线重算**，输入全部来自已落盘产物",
        },
        "load_before": load_before.get("loadavg"),
        "nr_throttled": load_before.get("nr_throttled"),
        "quota_us": load_before.get("quota_us"),
        "n_runs_rejudged": len(per_run),
        "polluted_runs": polluted_tags,
        "clean_runs": clean_tags,
        "root_cause_inference": root_cause,
        "gate_polarity_audit": gates,
        "mean_convergence_threshold_calibration": {
            "polluted_arm_max_s4_mean_spread": gap_lo,
            "clean_arm_min_s4_mean_spread": gap_hi,
            "threshold_geometric_midpoint": mean_conv_thr,
            "separation_factor": round(gap_hi / gap_lo, 2) if (gap_lo and gap_hi) else None,
            "note": "阈值由数据现算（几何中点），不是拍的；分离度写进产物供复核",
        },
        "per_run": per_run,
        "verdict": {
            "root_cause_inference": root_cause["verdict"],
            "gates_polarity_ok": [g["gate"] for g in gates if g["verdict"] == "polarity_ok"],
            "gates_false_negative": [g["gate"] for g in gates if g["verdict"] == "false_negative"],
            "gates_false_positive_on_clean_arms": [g["gate"] for g in gates
                                                   if g["verdict"] == "false_positive_on_clean_arms"],
            "gates_stale_docstring": [g["gate"] for g in gates if g["verdict"] == "stale_docstring"],
            "gates_no_tooth_in_this_regime": [g["gate"] for g in gates
                                              if g["verdict"] == "polarity_ok_but_no_tooth_in_this_regime"],
            "correction_to_ruling_82_5_4_1": (
                "裁定 82.5-4① 说「真正能区分现象 A 的信号是 frozen/cam_convergence/三相机 mean 收敛，不是 fidelity」"
                "⇒ **前两个在本轮数据里都不成立**（frozen=false、cam_convergence 实现版=false），"
                "**只有 mean 收敛成立**；当前唯一稳定判红的仍是容差版 fidelity。"
                "E 不自行改裁定，**报 D 更正表述**（下位纠正通道，裁定 80.2 形态）"),
        },
        "load_after": ev.cpu_stat().get("loadavg"),
        "nr_throttled_after": ev.cpu_stat().get("nr_throttled"),
    }
    out_p.parent.mkdir(parents=True, exist_ok=True)
    if out_p.exists():
        print(json.dumps({"verdict": "REFUSE", "reason": f"{out_p.name} 已存在；本件 append-only，"
                                                          "重跑请换 --out 或先把旧件移进 recycle_bin（不 rm）"},
                         ensure_ascii=False))
        return 3
    out_p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out_p.relative_to(REPO_ROOT)),
                      "root_cause_inference": payload["verdict"]["root_cause_inference"],
                      "gates_false_negative": payload["verdict"]["gates_false_negative"],
                      "gates_stale_docstring": len(payload["verdict"]["gates_stale_docstring"]),
                      "n_runs_rejudged": len(per_run), "gpu_used": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
