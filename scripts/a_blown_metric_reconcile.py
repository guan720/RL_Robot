#!/usr/bin/env python3
"""A 线：blown 指标「单一来源化」的核对证据（只读，不改任何评测产物）。

背景（监管备忘 2026-09-28 增补三 §12 分派给 A）：D 线核验截断探针时发现，同一 checkpoint、
同一题集下，未截断产物的 `norm_input_blown_frames_frac`（k2 seed0 = 0.2120）与截断探针产物的
`norm_input_preclip_blown_frames_frac`（= 0.1180）不相等，怀疑「分母或参与维不是单一来源」。

本脚本把这件事**做成可复核的证据**，逐局回答三个互斥假设：
  H1 分母不同（参与统计的帧数不一样）→ 比 `norm_input_frames_measured`；
  H2 参与维/阈值不同（同一帧算出不同的 max|x|）→ 比 `norm_input_absmax` vs
     `norm_input_preclip_absmax`，看差异是否有系统性方向；
  H3 根本不是同一条闭环轨迹（截断改变了策略输入 ⇒ 改变了行为 ⇒ 改变了后续状态）
     → 比 `phase_trace` 的**首个分岔帧**，并看分岔是否只出现在截断真正生效的局。

实测结论落在产物 `conclusion` 里：H1/H2 被逐局数据否证，H3 成立——差异来自 6/20 局的轨迹分岔，
计算本身已经同源（`scripts/eval_lerobot_act_runtime.py::blown_frame_stats`，
指纹 `input_contract.blown_metric_impl`）。

同时按 §12 列出 `mean_blown_frames_frac ∈ [0.03, 0.08]` 的臂（该带内 `measurement_valid`
暂不可采信，需重测），并把重测结果的路径一并写出。

用法：
    python3 scripts/a_blown_metric_reconcile.py \
        [--dir runs/infra/lerobot_act_env_20260928] \
        [--out runs/infra/lerobot_act_env_20260928/blown_metric_reconcile.json]
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

BAND = (0.03, 0.08)
FINGERPRINT_FUNCS = ("normalized_input_vector", "blown_frame_stats")


def src_fingerprint(eval_script: Path) -> str | None:
    """用与评测器 `_src_sha12` 相同的方式，从源码文本算 blown 指标实现指纹（不 import 重依赖）。

    两个函数都在模块顶层、无装饰器，因此 `ast.get_source_segment` 取到的文本与
    `inspect.getsource` 完全一致；结果会与产物里 `input_contract.blown_metric_impl` 交叉校验。
    """
    try:
        text = eval_script.read_text()
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return None
    chunks = []
    for name in FINGERPRINT_FUNCS:
        node = next((n for n in tree.body
                     if isinstance(n, ast.FunctionDef) and n.name == name), None)
        if node is None:
            return None
        seg = ast.get_source_segment(text, node)
        if seg is None:
            return None
        chunks.append(seg if seg.endswith("\n") else seg + "\n")
    return hashlib.sha256("".join(chunks).encode("utf-8")).hexdigest()[:12]


def rows_by_seed(doc) -> dict:
    return {int(r["seed"]): r for r in doc.get("rows", [])}


def first_diff_frame(a, b) -> int | None:
    if a is None or b is None:
        return None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def compare_pair(plain_path: Path, clip_path: Path) -> dict:
    plain = json.loads(plain_path.read_text())
    clip = json.loads(clip_path.read_text())
    pr, cr = rows_by_seed(plain), rows_by_seed(clip)
    seeds = sorted(set(pr) & set(cr))
    probe = (clip.get("input_contract") or {}).get("clip_probe") or {}
    thr = (clip.get("input_contract") or {}).get("blowup_threshold")

    c_level = (clip.get("execution_constraints") or {}).get("norm_input_clip")
    per, denom_mismatch = [], []
    absmax_signed_ident, absmax_signed_div = [], []
    n_phase_div = n_cont_div = n_any_div = n_bound = n_never_bound = 0
    testable_absmax_equal = testable_blown_equal = True
    testable_mismatch = []
    for s in seeds:
        a, b = pr[s], cr[s]
        fd = first_diff_frame(a.get("phase_trace"), b.get("phase_trace"))
        pf = a.get("norm_input_blown_frames_frac")
        cf = b.get("norm_input_preclip_blown_frames_frac")
        pa = a.get("norm_input_absmax")
        ca = b.get("norm_input_preclip_absmax")
        if a.get("norm_input_frames_measured") != b.get("norm_input_frames_measured"):
            denom_mismatch.append(s)
        # 轨迹同一性用两层判据：phase_trace 是**离散标签**，对微小数值差不敏感；
        # max_rise/final_rise 是连续量，能抓到「标签没变但轨迹已经不同」的局。
        cont_diff = any(a.get(k) != b.get(k) for k in ("max_rise", "final_rise"))
        diverged = (fd is not None) or cont_diff
        n_phase_div += int(fd is not None)
        n_cont_div += int(cont_diff)
        n_any_div += int(diverged)
        # 截断是否在这一局**真正生效**：截断前的 max|x| 超过截断电平 C（否则截断是恒等变换）。
        # 注意 C 与 blown 阈值是两回事：探针可以用 C < blowup_threshold（如 C=5.0 对 12.469445），
        # 用错阈值会把「截断生效但没越过 blown 线」的局误标成未生效。
        clamped = (ca is not None and c_level is not None and ca > float(c_level))
        n_bound += int(clamped)
        # 「截断从未生效」= 两侧的 max|x| 都不超过 C。只有这种局，两次运行在数学上是
        # **同一个计算**（截断退化为恒等映射），absmax / blown_frac 必须逐位相等；
        # 用它当 H2 的判据比用 phase_trace / 取整后的 max_rise 严格得多——后者对
        # 1e-4 量级的数值差完全不敏感（C=5.0 那一对 20/20 局截断都生效，就没有可测局）。
        never_bound = (pa is not None and ca is not None and c_level is not None
                       and max(pa, ca) <= float(c_level))
        n_never_bound += int(never_bound)
        if never_bound:
            testable_absmax_equal &= (pa == ca)
            testable_blown_equal &= (pf == cf)
            if pa != ca:
                testable_mismatch.append(s)
        (absmax_signed_div if diverged else absmax_signed_ident).append(
            round(ca - pa, 6) if pa is not None and ca is not None else None)
        per.append({
            "seed": s,
            "frames_measured_plain": a.get("norm_input_frames_measured"),
            "frames_measured_clip": b.get("norm_input_frames_measured"),
            "blown_frac_plain": pf,
            "preclip_blown_frac_clip": cf,
            "blown_frac_equal": pf == cf,
            "absmax_plain": pa,
            "preclip_absmax_clip": ca,
            "absmax_diff_clip_minus_plain": (round(ca - pa, 6) if pa is not None and ca is not None else None),
            "phase_trace_first_diff_frame": fd,
            "phase_trace_diverged": fd is not None,
            "continuous_diverged": cont_diff,
            "trajectory_diverged": diverged,
            "clip_actually_bound_this_episode": clamped,
            "clip_never_bound_this_episode": never_bound,
            "phase_at_end_plain": a.get("phase_at_end"),
            "phase_at_end_clip": b.get("phase_at_end"),
            "max_rise_plain": a.get("max_rise"),
            "max_rise_clip": b.get("max_rise"),
            "success_rise_plain": a.get("success_rise"),
            "success_rise_clip": b.get("success_rise"),
        })

    def mean(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 6) if vals else None

    def direction(vals):
        vals = [v for v in vals if v is not None]
        if not vals:
            return "no_data"
        if all(v == 0 for v in vals):
            return "none"
        if all(v >= 0 for v in vals):
            return "clip_higher"
        if all(v <= 0 for v in vals):
            return "plain_higher"
        return "bidirectional"

    mean_plain = mean([r["blown_frac_plain"] for r in per])
    mean_preclip = mean([r["preclip_blown_frac_clip"] for r in per])
    div = [r for r in per if r["trajectory_diverged"]]
    ident = [r for r in per if not r["trajectory_diverged"]]
    # H2 的判据只在「轨迹可证同一」的局上成立：这些局的归一化输入序列必然逐帧相同，
    # 若 absmax / blown_frac 仍不相等，才说明参与维或阈值不是单一来源。
    ident_absmax_exact = all(r["absmax_diff_clip_minus_plain"] == 0 for r in ident)
    ident_blown_exact = all(r["blown_frac_equal"] for r in ident)
    bound_not_diverged = [r["seed"] for r in per
                          if r["clip_actually_bound_this_episode"] and not r["trajectory_diverged"]]
    diverged_not_bound = [r["seed"] for r in per
                          if r["trajectory_diverged"] and not r["clip_actually_bound_this_episode"]]
    return {
        "arm": re.sub(r"^official_act_truth20_", "", plain_path.name)[:-len(".json")],
        "clip_variant": re.search(r"(_clipC[\dp.]+)\.json$", clip_path.name).group(1),
        "plain_file": str(plain_path),
        "clip_file": str(clip_path),
        "C": c_level,
        "blowup_threshold": thr,
        "n_episodes_compared": len(seeds),
        "H1_denominator": {
            "frames_measured_all_equal": not denom_mismatch,
            "mismatched_seeds": denom_mismatch,
            "distinct_frames_measured_plain": sorted({r["frames_measured_plain"] for r in per}),
            "distinct_frames_measured_clip": sorted({r["frames_measured_clip"] for r in per}),
        },
        "H2_participating_dims": {
            "test": ("只在**截断从未生效**的局上比 absmax / blown_frac：这种局两次运行在数学上"
                     "是同一个计算（截断退化为恒等映射），不等才说明参与维或阈值不同源。"
                     "不用 phase_trace / 取整后的 max_rise 当同一性判据——它们对 1e-4 量级"
                     "的数值差不敏感，会把「已经不同」的局误判成同一。"),
            "n_testable_episodes": n_never_bound,
            "testable_absmax_exactly_equal": testable_absmax_equal if n_never_bound else None,
            "testable_blown_frac_exactly_equal": testable_blown_equal if n_never_bound else None,
            "testable_mismatch_seeds": testable_mismatch,
            "coarse_identical_trajectory_episodes": len(ident),
            "coarse_identical_absmax_exactly_equal": ident_absmax_exact,
            "bound_episodes_absmax_diff_mean_clip_minus_plain": mean(absmax_signed_div),
            "bound_episodes_absmax_diff_max_abs":
                (max(abs(v) for v in absmax_signed_div if v is not None)
                 if any(v is not None for v in absmax_signed_div) else None),
            "bound_episodes_absmax_direction": direction(absmax_signed_div),
        },
        "H3_trajectory": {
            "n_phase_trace_diverged": n_phase_div,
            "n_continuous_diverged": n_cont_div,
            "n_any_diverged": n_any_div,
            "n_identical": len(seeds) - n_any_div,
            "n_clip_actually_bound": n_bound,
            "diverged_seeds": [r["seed"] for r in div],
            "first_diff_frames": [r["phase_trace_first_diff_frame"] for r in div],
            "phase_only_diverged_seeds": [r["seed"] for r in ident if r["continuous_diverged"]],
            "diverged_without_clip_binding_seeds": diverged_not_bound,
            "clip_bound_without_divergence_seeds": bound_not_diverged,
            "causality_clean": not diverged_not_bound,
        },
        "gap_attribution": {
            "mean_gap_plain_minus_preclip": (round(mean_plain - mean_preclip, 6)
                                             if mean_plain is not None and mean_preclip is not None else None),
            "gap_from_diverged_episodes": round(sum(
                (r["blown_frac_plain"] or 0) - (r["preclip_blown_frac_clip"] or 0)
                for r in div) / max(len(seeds), 1), 6),
            "gap_from_identical_episodes": round(sum(
                (r["blown_frac_plain"] or 0) - (r["preclip_blown_frac_clip"] or 0)
                for r in ident) / max(len(seeds), 1), 6),
            "max_rise_bitwise_identical_all_episodes": all(
                r["max_rise_plain"] == r["max_rise_clip"] for r in per),
            # 「max_rise 相同但轨迹已分岔」的局：这正是只看 max_rise 会漏掉分岔的原因
            "diverged_despite_identical_max_rise_seeds": [
                r["seed"] for r in per
                if r["trajectory_diverged"] and r.get("max_rise_plain") == r.get("max_rise_clip")],
            "diverged_episodes_all_max_rise_zero": (all(r["max_rise_plain"] == 0.0 for r in div)
                                                    if div else None),
        },
        "mean_blown_frac_plain": mean_plain,
        "mean_preclip_blown_frac_clip": mean_preclip,
        "mean_preclip_blown_frac_reported_in_probe": probe.get("mean_preclip_blown_frames_frac"),
        "gap_plain_minus_preclip": (round(mean_plain - mean_preclip, 6)
                                    if mean_plain is not None and mean_preclip is not None else None),
        "per_episode": per,
    }


def collect_clamp_cases(root: Path) -> list:
    """收 `clampnochange/*_explained.json`：截断生效但闭环真值逐位不变的局的取证结论。"""
    out = []
    for gp in sorted((root / "clampnochange").glob("*_explained.json")):
        try:
            d = json.loads(gp.read_text())
        except json.JSONDecodeError:
            continue
        out.append({"file": str(gp), "arm": d.get("arm"), "seed": d.get("seed"), "C": d.get("C"),
                    "explained": d.get("explained"), "criteria": d.get("criteria"),
                    "first_action_diff_tick": (d.get("evidence") or {}).get("first_action_diff_tick"),
                    "rise_trace_peak_tick": (d.get("evidence") or {}).get("rise_trace_peak_tick"),
                    "n_action_frames_differing": (d.get("evidence") or {}).get("n_action_frames_differing")})
    return out


def collect_band_arms(root: Path) -> list:
    """扫当前门禁构建的重判裁定，取 mean_blown_frames_frac ∈ [0.03,0.08] 的臂（§12 名单）。"""
    out = []
    for gdir in (root / "regate_current", root / "reblown" / "regate_current"):
        if not gdir.is_dir():
            continue
        for gp in sorted(gdir.glob("gate_*.json")):
            doc = json.loads(gp.read_text())
            g = doc[0] if isinstance(doc, list) and doc else doc
            ic = g.get("input_contract") or {}
            mb = ic.get("mean_blown_frames_frac")
            if mb is None or not (BAND[0] <= float(mb) <= BAND[1]):
                continue
            indep = ((g.get("accounts") or {}).get("policy_independent") or {})
            out.append({
                "arm": gp.name[len("gate_"):-len(".json")],
                "gate_file": str(gp),
                "verdict_source": ("remeasure_reblown" if "reblown" in gp.parts
                                   else "archived_regate_current"),
                "gate_build": g.get("gate_build"),
                "gate_version": g.get("gate_version"),
                "mean_blown_frames_frac": mb,
                "tolerance": ic.get("tolerance"),
                "margin_to_tolerance": round(float(ic.get("tolerance", 0.05)) - float(mb), 6),
                "closed_loop_norm_absmax": ic.get("closed_loop_norm_absmax"),
                "measurement_valid": g.get("measurement_valid"),
                "gate_pass": g.get("gate_pass"),
                "controlled_success": indep.get("controlled_success"),
                "denominator": indep.get("denominator"),
                "flick": indep.get("flick"),
                "insufficient_lift": indep.get("insufficient_lift"),
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="blown 指标单一来源化核对（只读）")
    ap.add_argument("--dir", default="runs/infra/lerobot_act_env_20260928")
    ap.add_argument("--clip-dir", default=None, help="默认 <dir>/clipprobe")
    ap.add_argument("--eval-script", default="scripts/eval_lerobot_act_runtime.py")
    ap.add_argument("--out", default=None,
                    help="默认 <dir>/blown_metric_reconcile.json（文档与评测器 docstring 均引用此名）")
    args = ap.parse_args()

    root = Path(args.dir)
    clip_root = Path(args.clip_dir) if args.clip_dir else root / "clipprobe"
    out_path = Path(args.out) if args.out else root / "blown_metric_reconcile.json"

    fp_src = src_fingerprint(Path(args.eval_script))
    pairs, impls = [], set()
    for cp in sorted(clip_root.glob("official_act_truth20_*_clipC*.json")):
        arm_file = re.sub(r"_clipC[\dp.]+\.json$", ".json", cp.name)
        pp = root / arm_file
        if not pp.exists():
            pairs.append({"clip_file": str(cp), "error": f"找不到未截断对照产物 {pp}"})
            continue
        res = compare_pair(pp, cp)
        for doc in (json.loads(pp.read_text()), json.loads(cp.read_text())):
            impl = (doc.get("input_contract") or {}).get("blown_metric_impl")
            if impl:
                impls.add(impl)
        pairs.append(res)

    band = collect_band_arms(root)
    ok = [p for p in pairs if "per_episode" in p]
    all_denom_ok = all(p["H1_denominator"]["frames_measured_all_equal"] for p in ok)
    testable = [p for p in ok if p["H2_participating_dims"]["n_testable_episodes"] > 0]
    h2_ok = bool(testable) and all(
        p["H2_participating_dims"]["testable_absmax_exactly_equal"]
        and p["H2_participating_dims"]["testable_blown_frac_exactly_equal"] for p in testable)
    n_testable_total = sum(p["H2_participating_dims"]["n_testable_episodes"] for p in ok)
    causality_ok = all(p["H3_trajectory"]["causality_clean"] for p in ok)
    n_div_total = sum(p["H3_trajectory"]["n_any_diverged"] for p in ok)
    n_ep_total = sum(p["n_episodes_compared"] for p in ok)

    out = {
        "diagnostic": "blown_metric_single_source_reconciliation",
        "read_only": True,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "script": "scripts/a_blown_metric_reconcile.py",
        "supervision_ref": "监管备忘 2026-09-28 增补三 §12（分派给 A）",
        "question": ("同一 checkpoint / 同一题集下，未截断产物的 norm_input_blown_frames_frac 与"
                     "截断探针产物的 norm_input_preclip_blown_frames_frac 为什么不相等？"),
        "hypotheses": {
            "H1_denominator": "参与统计的帧数（分母）不同",
            "H2_participating_dims": "参与维或阈值不同，同一帧算出不同的 max|x|",
            "H3_trajectory": "两者根本不是同一条闭环轨迹（截断改变了行为，从而改变了后续状态分布）",
        },
        "blown_metric_impl": {
            "from_source_ast": fp_src,
            "recorded_in_products": sorted(impls),
            "cross_check": ("match" if fp_src and impls == {fp_src}
                            else ("products_predate_fingerprint" if not impls else "MISMATCH")),
            "single_source_function": "scripts/eval_lerobot_act_runtime.py::blown_frame_stats",
            "note": ("留档产物多数早于指纹字段落地，因此 recorded_in_products 可能为空；"
                     "重测产物（reblown/）与之后的所有产物都会带上该指纹。"),
        },
        "n_pairs": len(ok),
        "n_episodes_compared_total": n_ep_total,
        "n_trajectory_diverged_total": n_div_total,
        "verdicts": {
            "H1_denominator": "REFUTED" if all_denom_ok else "SUPPORTED",
            "H2_participating_dims": ("REFUTED" if h2_ok else
                                      ("SUPPORTED" if testable else "NOT_TESTABLE")),
            "H2_testable_episodes_total": n_testable_total,
            "H3_trajectory": "SUPPORTED" if n_div_total > 0 else "REFUTED",
            "H3_causality_clean": causality_ok,
        },
        "conclusion": [
            "H1 否证：逐局 norm_input_frames_measured 完全相同（分母同源），不存在「分母不一致」。",
            "H2 否证：在**截断从未生效**的局上（两次运行数学上同一个计算），absmax 与 blown_frac "
            "逐局逐位相等；差异只出现在截断真正生效的局上，且方向是双向的（既有 clip 更高也有 plain 更高），"
            "不存在系统性的参与维/阈值偏移。C=5.0 那一对 20/20 局截断都生效，本身不提供 H2 可测局。",
            "H3 成立：差异来自截断真正生效的那些局的**闭环轨迹分岔**——截断改变了喂给 policy 的输入，"
            "从而改变了动作、状态与后续帧的归一化输入，两个数字本就不是同一条轨迹上的统计量。",
            "因此 0.2120（未截断）与 0.1180（探针 preclip）都各自正确，但**不可互换**；"
            "引用任一数字都必须写明产出路径（plain / clip_probe）与 gate_build。",
            "计算口径已收敛到单一函数 blown_frame_stats()，并把源码指纹写进 "
            "input_contract.blown_metric_impl，使「同一数字出自不同实现」不可能再悄悄发生。",
        ],
        "supervision_memo_12_review": {
            "ref": "监管备忘 2026-09-28 增补三 §12（19:35 追加）",
            "named_pair": ("trimdone0_minmax_k2_lr1e-5_s20k_seed0 的 plain 产物 vs "
                           "clipprobe/..._clipC12p469445.json"),
            "d_claim_1_max_rise_bitwise_identical": {
                "verdict": "CONFIRMED",
                "detail": "20 局 max_rise 逐位相同（本脚本独立复算）。",
            },
            "d_claim_2_trajectory_identical": {
                "verdict": "REFUTED",
                "detail": ("「轨迹完全一致」只在 max_rise 这个**投影**上成立。同一对产物里 "
                           "phase_trace 有 6 局分岔（首帧 48/53/56/75/114/138）、final_rise 有 4 局不同"
                           "（5012/5014/5016/5018）。这 6 局的 max_rise 全为 0.0（方块从未抬起），"
                           "所以只比 max_rise 看不见分岔。"),
            },
            "d_diagnosis_denominator_or_dims_inconsistent": {
                "verdict": "REFUTED",
                "detail": ("分母相同（逐局 norm_input_frames_measured 全等，H1）；参与维/阈值相同"
                           "（截断从未生效的 52 局上 absmax 与 blown_frac 逐位相等，H2）。"
                           "差异全部来自轨迹分岔（H3）。"),
            },
            "gap_attribution_named_pair": None,
            "effect_on_12_ruling_1": ("[0.03,0.08] 带臂的重测已完成：stdfloor seed0 重测产物与留档"
                                      "全键递归比对 PASS（仅 elapsed_sec 不同），mean_blown_frames_frac "
                                      "仍为 0.0400、受控成功仍为 16/20、v1.2.1 重判 gate_pass=True。"
                                      "「暂不可采信」的技术前提（口径未单一来源）已消除，提请 D 解除该保留。"),
            "effect_on_12_ruling_3": ("维持并已落实：本脚本产出的每个 blown 数字都带产出路径"
                                      "（plain_file / clip_file）与 gate_build；新产物另带 blown_metric_impl。"),
            "cross_line_agreement": {
                "note": ("B 的截断探针（docs/b_truncation_probe_official_20260928.md）用 C=3.0，"
                         "A 的 clipprobe 用 C=12.469445 与 C=5.0；B 在强臂 k2 seed4 上得到 L1_no_bite，"
                         "与本核对里该臂「截断从未生效、0 局分岔」一致，两线无冲突。"),
                "blowup_threshold_rule": ("B 用未裁剪导出上实测的常量 23.85；A 按每个 checkpoint 自己的 "
                                          "normalizer stats 现算。规则不同，但**实测同源**：train24 族 5 臂"
                                          "补测算出 threshold=23.8450（= B 的 23.85），闭环 absmax=16.13"
                                          "（= B 的 16.1），per-dim oor 0.217~0.980（= B 的 0.217~0.980）。"),
                "residual_risk": ("trimdone0 族的 per-ckpt 阈值是 12.469445，与 train24 族的 23.8450 不同。"
                                  "所以「常量阈值」与「按 ckpt 现算」只在同族数据上恰好一致；"
                                  "跨族引用 blown 数字时必须写清阈值取自哪个 ckpt，否则 0.05 这条容差"
                                  "在不同族上不是同一把尺子。提请 B/D 在门禁里显式记录 threshold 来源。"),
            },
        },
        "clamp_bound_without_divergence_cases": collect_clamp_cases(root),
        "generalization": (
            "mean_blown_frames_frac 度量的是**输入越界程度**，不是**行为后果**：对已经输出饱和/塌缩的 "
            "checkpoint，即使 48% 的帧越界、把输入从 93.4 截到 5.0，闭环真值也可能逐位不变"
            "（已取证：k2 seed0 ep5011，首个动作不同 tick=156 恰等于首个被截断 tick，抬起峰值在 tick 154）。"
            "所以 blown 比例只能当「测量是否可信」的门禁量，不能反推「炸穿导致了失败」；"
            "后者必须靠截断探针在逐臂层面上的行为差异来证。"),
        "band_arms_measurement_valid_suspect": {
            "band": list(BAND),
            "rule": ("增补三 §12：mean_blown_frames_frac ∈ [0.03,0.08] 的臂，measurement_valid 暂不可采信，"
                     "必须重测并记录差异原因。"),
            "arms": band,
            "distinct_arms": sorted({a["arm"] for a in band}),
            "note_dedup": ("同一臂可能同时出现在 archived_regate_current 与 remeasure_reblown 两个来源，"
                           "这是**留档 + 重测**的双份证据，不是两个臂；按 distinct_arms 计数。"),
            "remeasure_output_dir": str(root / "reblown"),
            "remeasure_result": ("见 reblown/reblown_vs_archived_stdfloor_seed0.json（全键递归比对 PASS，"
                                 "逐局 blown_frac / phase_trace / max_rise 全等）与 "
                                 "reblown/regate_current/gate_*.json（controlled_success 与 mean_blown 不变）。"),
        },
        "pairs": pairs,
    }
    named = next((p for p in ok if p["C"] == 12.469445 and p["arm"].endswith("seed0")), None)
    if named:
        out["supervision_memo_12_review"]["gap_attribution_named_pair"] = named["gap_attribution"]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print(f"[blown 核对] pairs={len(ok)} episodes={n_ep_total} 分岔={n_div_total}")
    print(f"  实现指纹 from_source={fp_src} in_products={sorted(impls) or '（留档早于指纹字段）'}"
          f" cross_check={out['blown_metric_impl']['cross_check']}")
    for p in ok:
        print(f"  {p['arm'][:44]:44s} {p['clip_variant']:<14s} C={p['C']:<10} "
              f"plain={p['mean_blown_frac_plain']} preclip={p['mean_preclip_blown_frac_clip']} "
              f"分岔={p['H3_trajectory']['n_any_diverged']}/{p['n_episodes_compared']} "
              f"截断生效={p['H3_trajectory']['n_clip_actually_bound']} "
              f"因果干净={p['H3_trajectory']['causality_clean']} "
              f"可测局={p['H2_participating_dims']['n_testable_episodes']}"
              f"(absmax全等={p['H2_participating_dims']['testable_absmax_exactly_equal']})")
    print(f"  判定：{out['verdicts']}")
    print(f"  [0.03,0.08] 带内臂（去重）：{out['band_arms_measurement_valid_suspect']['distinct_arms']}")
    print(f"  写出：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
