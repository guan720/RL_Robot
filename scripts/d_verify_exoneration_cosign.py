#!/usr/bin/env python3
"""D 线：裁定 16.4「免罪册 `k2 seed0` 条目」的会签前独立核验（**只读**上游）。

为什么需要这个脚本（而不是照抄 A/B 的结论会签）
--------------------------------------------------
A 在 `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md` §4 把最小修复面写成
「改豁免册 `_doc` 的『带外不受理』+ 新增一个 `probe_kind`」，并在 §7 承诺 B 补完后
A「重跑一条命令即可迁表」。D 会签前必须自己核这件事**在代码里到底能不能成立** ——
裁定 10 的事实基础 D 已在增补四 §3 核可过（当时锚在 v1.2.1），但**登记册能否承载它**
是另一件事，取决于 `scripts/b_gate_controlled_success.py::probe_exoneration_check()`
与 `:807` 的晋级分支，而这两处 A 没有读。

本脚本做四件事，全部只读 A/B/C 的文件：
  1. 用**当前门禁构建**现场重判 4 份产物（plain / clipC12.469445 / clipC5.0 / stdfloor reblown），
     不复用任何留档裁定 —— 留档裁定可能出自旧 build（增补三 §10 禁跨 build 混引）；
  2. 独立复算 裁定 10 的五条准入（cond1..cond5），逐局 verdict / accounts 五项 / 残余差异枚举；
  3. **通道实证**：把豁免册路径在内存里换成 D 自己的候选册（不动 `configs/`），
     调**真实**的 `probe_exoneration_check()`，看 `scope=arm` 与 `scope=artifact`
     两种写法对 blown=0.212 的目标臂分别返回什么；
  4. 晋级闸实证：按 `:807` 的分支谓词，用目标臂真实 `ic_status` 判定「即使豁免受理，
     ic_status 能不能从 violated 升为 probe_exonerated」。

产物：`tmp/agentD_review_20260929/D_cosign_k2seed0.json`（+ stdout 摘要）。
退出码：0 = 五条准入全过且两处代码级阻塞都被实证命中；非 0 = 有核验项不成立（须先看 JSON）。

用法：
    python3 scripts/d_verify_exoneration_cosign.py
    python3 scripts/d_verify_exoneration_cosign.py --out tmp/agentD_review_20260929/D_cosign_k2seed0.json
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys, types
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE_PY = ROOT / "scripts" / "b_gate_controlled_success.py"
TZ = timezone(timedelta(hours=8))

ARM = "trimdone0_minmax_k2_lr1e-5_s20k_seed0"
STDFLOOR_ARM = "trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0"
PLAIN = "runs/infra/lerobot_act_env_20260928/official_act_truth20_%s.json" % ARM
CLIP12 = ("runs/infra/lerobot_act_env_20260928/clipprobe/"
          "official_act_truth20_%s_clipC12p469445.json" % ARM)
CLIP5 = ("runs/infra/lerobot_act_env_20260928/clipprobe/"
         "official_act_truth20_%s_clipC5p0.json" % ARM)
STDFLOOR_REBLOWN = ("runs/infra/lerobot_act_env_20260928/reblown/"
                    "official_act_truth20_%s.json" % STDFLOOR_ARM)
STDFLOOR_MAIN = "runs/infra/lerobot_act_env_20260928/official_act_truth20_%s.json" % STDFLOOR_ARM

COUNT_KEYS = ("controlled_success", "provisional_pass", "over_lift", "flick", "insufficient_lift")


def _now():
    return datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_file(rel):
    p = ROOT / rel
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def load_gate_module():
    """按 import 读门禁（DR-D03 起 C 线同款做法：读构建指纹，不硬编码版本号）。"""
    spec = importlib.util.spec_from_file_location("d_gate_impl", str(GATE_PY))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def judge(mod, rel):
    """用**当前**门禁构建现场重判一份产物（不复用留档裁定）。"""
    args = types.SimpleNamespace(rise_cap=mod.RISE_CAP, final_rise=mod.FINAL_RISE_MIN,
                                 assist_off=False, no_strict_final_rise=False,
                                 hold_phases=None, json_out=None, quiet=True)
    r = mod.judge_file(str(ROOT / rel), args)
    if "error" in r:
        raise SystemExit("门禁重判失败 %s: %s" % (rel, r["error"]))
    return r


def accounts_flat(r):
    pi = r["accounts"]["policy_independent"]
    sa = r["accounts"]["system_assisted"]
    out = {}
    for k in COUNT_KEYS:
        out[k] = pi.get(k, sa.get(k))
    out["raw_success"] = r.get("raw_success")
    out["denominator"] = pi.get("denominator")
    return out


def per_episode_map(r):
    m = {}
    for e in r.get("per_episode") or []:
        m[e.get("seed")] = {k: e.get(k) for k in
                            ("verdict", "final_rise", "max_rise", "held_at_end",
                             "terminal_kind", "grasp_verified", "phase_at_end")}
    return m


def diff_verdicts(base, other):
    """裁定 10 条件 ②③ 的机器判据：逐局 verdict 差集 + 残余字段差枚举。"""
    verdict_diff, field_diff = [], []
    for s in sorted(set(base) | set(other), key=lambda x: (x is None, x)):
        b, o = base.get(s, {}), other.get(s, {})
        if b.get("verdict") != o.get("verdict"):
            verdict_diff.append({"seed": s, "plain": b.get("verdict"), "probe": o.get("verdict"),
                                 "verdict_same": False})
        for k in sorted(set(b) | set(o)):
            if k == "verdict":
                continue
            if b.get(k) != o.get(k):
                field_diff.append({"seed": s, "field": k, "plain": b.get(k), "probe": o.get(k),
                                   "verdict_same": b.get("verdict") == o.get("verdict")})
    return verdict_diff, field_diff


def ruling10_conditions(mod, plain, c12, c5):
    """裁定 10 五条准入（增补四 §3）逐条机器核对。D 自己算，不引用 A 的 arms_summary。"""
    ap, ac = accounts_flat(plain), accounts_flat(c12)
    v12, f12 = diff_verdicts(per_episode_map(plain), per_episode_map(c12))
    v5, f5 = diff_verdicts(per_episode_map(plain), per_episode_map(c5))

    thr_plain = (plain.get("input_contract") or {}).get("train_time_norm_absmax")
    clip12 = (c12.get("execution_constraints") or {}).get("norm_input_clip")
    clip5 = (c5.get("execution_constraints") or {}).get("norm_input_clip")
    count_diff = {k: {"plain": ap[k], "probe_C12": ac[k]} for k in ac if ap[k] != ac[k]}

    cond1 = (thr_plain is not None and clip12 is not None
             and abs(float(clip12) - float(thr_plain)) < 1e-9)
    cond2 = (not v12) and (not count_diff)
    cond3 = all(d["verdict_same"] for d in f12)          # 残余差异必须都不改 verdict
    cond4 = bool(sha256_file(CLIP12))                     # 探针产物存在且可指纹
    cond5 = (plain.get("composite_policy") is False
             and c12.get("composite_policy") is True
             and "norm_input_clip" in (c12.get("active_constraints") or []))

    return {
        "cond1_C_equals_train_absmax": {
            "pass": bool(cond1), "train_time_norm_absmax": thr_plain,
            "probe_clip_C12": clip12, "probe_clip_C5": clip5,
            "note": "裁定 10 条件 1：C 必须钉死在该 ckpt 自己的训练期归一化 |x| 上界。",
        },
        "cond2_verdicts_and_counts_identical": {
            "pass": bool(cond2), "verdict_diff_seeds": [d["seed"] for d in v12],
            "count_diff": count_diff, "counts_plain": ap, "counts_probe_C12": ac,
        },
        "cond3_diffs_enumerated_and_verdict_same": {
            "pass": bool(cond3), "n_residual_field_diffs": len(f12),
            "residual_row_diffs": f12,
            "all_verdict_same": bool(cond3),
        },
        "cond4_probe_path_C_build_recorded": {
            "pass": bool(cond4), "probe_artifact": CLIP12,
            "probe_sha256": sha256_file(CLIP12), "plain_artifact": PLAIN,
            "plain_sha256": sha256_file(PLAIN),
            "gate_version": mod.GATE_VERSION, "gate_build": mod.GATE_BUILD,
            "gate_spec_sha256": mod.GATE_SPEC_SHA,
        },
        "cond5_scope_measurement_valid_only": {
            "pass": bool(cond5),
            "plain_composite_policy": plain.get("composite_policy"),
            "probe_composite_policy": c12.get("composite_policy"),
            "probe_active_constraints": c12.get("active_constraints"),
            "note": ("探针产物必须自带 composite_policy=true ⇒ 它**不能**被当官方臂数字引用；"
                     "免罪只把 plain 的 measurement_valid 救回来，不碰三套账。"),
        },
        "cond1_discriminative_counterproof_C5": {
            "C5_violates_cond2": bool(v5 or accounts_flat(c5) != ac),
            "verdict_diff_seeds": [d["seed"] for d in v5], "verdict_diffs": v5,
            "counts_probe_C5": accounts_flat(c5),
            "n_residual_field_diffs": len(f5),
            "note": ("C=5.0 探针**不满足**条件 2 ⇒「截得越紧越安全」被证伪；"
                     "这条反证是 cond1 有判别力的唯一证据。"),
        },
        "ALL_FIVE_PASS": bool(cond1 and cond2 and cond3 and cond4 and cond5),
    }


def channel_probe(mod, plain, c12, variants):
    """通道实证：把 EXONERATION_DOC 在内存里换成 D 自己的候选册，调**真实**函数。

    不改 `configs/b_probe_exonerations.json`（B 的文件，DR-003 决定 8 单写者纪律），
    也不改门禁源码 —— 只换模块级路径常量，函数体是 B 的原文。
    """
    impl_status = (plain.get("input_contract") or {}).get("blown_metric_impl_status")
    mean_blown = (plain.get("input_contract") or {}).get("mean_blown_frames_frac")
    plain_sha = sha256_file(PLAIN)
    results = []
    saved = mod.EXONERATION_DOC
    try:
        for v in variants:
            reg_rel = "tmp/agentD_review_20260929/_D_sim_registry_%s.json" % v["name"]
            reg_path = ROOT / reg_rel
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            entry = dict(v["entry"])
            key = plain_sha if v["key"] == "<plain_sha256>" else v["key"]
            if entry.get("sha256") == "<probe_sha256>":
                entry["sha256"] = sha256_file(CLIP12)
            if entry.get("artifact") == "<probe_artifact>":
                entry["artifact"] = CLIP12
            reg_path.write_text(json.dumps({"entries": {key: entry}}, indent=1,
                                           ensure_ascii=False) + "\n", encoding="utf-8")
            mod.EXONERATION_DOC = reg_rel
            out = mod.probe_exoneration_check(str(ROOT / PLAIN), mean_blown, impl_status)
            promoted = bool(out and out.get("status") == "exonerated"
                            and (plain["input_contract"]["status"]
                                 in ("verified_ok", "not_applicable_verified")))
            results.append({
                "variant": v["name"], "registry_sim": reg_rel, "key": key,
                "scope": v["entry"].get("scope"), "probe_kind": v["entry"].get("probe_kind"),
                "exo_status": (out or {}).get("status"),
                "exo_note": (out or {}).get("note"),
                "mean_blown_frames_frac": mean_blown,
                "blown_impl_status": impl_status,
                "ic_status_of_plain": plain["input_contract"]["status"],
                "would_promote_to_probe_exonerated": promoted,
            })
    finally:
        mod.EXONERATION_DOC = saved
    return results


def promotion_gate_check(mod, plain, kind="clip_at_train_absmax"):
    """晋级分支的谓词实证（不改源码，只按源码原文判定）。

    v1.4：晋级闸硬编码 `ic_status in ("verified_ok","not_applicable_verified")`。
    v1.5（DR-008 决定 5 / 裁定 25）：改为按 probe_kind 分路的 `EXONERATION_PROMOTION_SOURCES`。
    本函数**两种都认**：模块暴露了分路表就按分路表判，否则按 v1.4 硬编码判 ——
    这样同一把尺子能量 v1.5 前后，不会「代码改好了反而判据变红」。
    """
    src = GATE_PY.read_text(encoding="utf-8").splitlines()
    hits = [(i + 1, ln.strip()) for i, ln in enumerate(src)
            if 'status"] == "exonerated"' in ln and "ic_status in" in ln]
    hits += [(i + 1, ln.strip()) for i, ln in enumerate(src)
             if "EXONERATION_PROMOTION_SOURCES" in ln and not ln.strip().startswith("#")]
    ic_observed = plain["input_contract"]["status"]
    # v1.5 下 judge_file **已经就地晋级**，所以 ic_observed 可能是晋级后的值。
    # 要判「晋级闸允不允许」必须还原**底层**状态：门禁 :793 的逻辑是
    # mean_blown > INPUT_BLOWUP_TOL ⇒ violated，否则 verified_ok（覆盖率全、无缺指纹）。
    mb = plain["input_contract"]["mean_blown_frames_frac"]
    tol = mod.INPUT_BLOWUP_TOL
    ic_underlying = "violated" if (mb is not None and mb > tol) else "verified_ok"
    ic = ic_underlying
    table = getattr(mod, "EXONERATION_PROMOTION_SOURCES", None)
    if isinstance(table, dict):
        allowed = tuple(table.get(kind) or getattr(mod, "DEFAULT_PROMOTION_SOURCES",
                                                  ("verified_ok", "not_applicable_verified")))
        mechanism = "EXONERATION_PROMOTION_SOURCES[%r]（v1.5 按 probe_kind 分路）" % kind
    else:
        allowed = ("verified_ok", "not_applicable_verified")
        mechanism = "硬编码 ic_status in (verified_ok, not_applicable_verified)（v1.4）"
    return {
        "source_lines": hits,
        "mechanism": mechanism,
        "probe_kind_assumed": kind,
        "plain_ic_status": ic_observed,
        "plain_ic_status_underlying": ic_underlying,
        "mean_blown_frames_frac": mb, "input_blownup_tol": tol,
        "promotion_allowed_statuses": list(allowed),
        "promotion_possible_without_code_change": bool(ic_underlying in allowed),
        "promotion_actually_happened": bool(ic_observed == "probe_exonerated"),
        "IC_VALID_STATUSES": list(mod.IC_VALID_STATUSES),
        "note": ("晋级闸机制 = %s；底层 ic_status=%s（blown %s vs tol %s）⇒ 允许晋级 = %s；"
                 "实测晋级**是否发生** = %s（门禁观察值 ic_status=%s）。"
                 % (mechanism, ic_underlying, mb, tol, bool(ic_underlying in allowed),
                    bool(ic_observed == "probe_exonerated"), ic_observed)),
    }


def crosscheck(plain, c12, mod):
    """与 B 的 v1.4 权威表 + D 昨天的 48 臂独立重判对账（计数层 / 分类层 / 产物归属）。"""
    out = {"gate_build_live": "%s/%s" % (mod.GATE_VERSION, mod.GATE_BUILD)}
    bpath = ROOT / "runs/infra/b_official_arms/reclassification.json"
    if bpath.exists():
        b = json.loads(bpath.read_text())
        out["B_authority"] = {
            "gate": "%s/%s" % (b.get("gate_version"), b.get("gate_build")),
            "summary_ic_status": (b.get("summary") or {}).get("ic_status"),
            "summary_citable": (b.get("summary") or {}).get("citable"),
            "n_artifacts": b.get("n_artifacts"),
            "controlled_success_total": sum(int(a.get("controlled_success") or 0)
                                            for a in (b.get("arms") or [])),
        }
        arms = {a.get("arm"): a for a in (b.get("arms") or [])}
        pair = {}
        for nm in (ARM, STDFLOOR_ARM):
            a = arms.get(nm) or {}
            pair[nm] = {"B_file": a.get("file"), "B_source": a.get("source"),
                        "B_ic_status": a.get("ic_status"),
                        "B_probe_exoneration": a.get("probe_exoneration"),
                        "B_controlled_success": a.get("controlled_success"),
                        "B_blown": a.get("mean_blown_frames_frac"),
                        "B_blown_impl_status": a.get("blown_impl_status")}
        out["B_arms"] = pair
        sf = arms.get(STDFLOOR_ARM) or {}
        out["stdfloor_provenance"] = {
            "B_gates": sf.get("file"),
            "D_regate48_gated": STDFLOOR_MAIN,
            "same_artifact": (sf.get("file") or "").endswith(STDFLOOR_MAIN.split("/")[-1])
                             and "reblown" not in (sf.get("file") or ""),
            "note": ("A §2.3 说 B「把不需要豁免的臂记成 probe_exonerated」。实测 B 判的是 "
                     "`reblown/` 取代产物（带指纹、blown=0.04 落在争议带 [0.03,0.08] 内），"
                     "A/D 的 48 臂表判的是主目录旧产物（无指纹）。两个标签各自都对，"
                     "分歧的真正机制是**产物归属**，不是误标。"),
        }
    dpath = ROOT / "tmp/agentD_review_20260929/D_regate48_rows.json"
    if dpath.exists():
        rows = json.loads(dpath.read_text())
        out["D_regate48"] = {
            "n_rows": len(rows),
            "controlled_success_total": sum(int(r.get("ctrl") or 0) for r in rows),
            "ic_status_counts": {s: sum(1 for r in rows if r.get("ic") == s)
                                 for s in sorted({r.get("ic") for r in rows})},
            "measurement_valid_counts": {str(v): sum(1 for r in rows if bool(r.get("mv")) == v)
                                         for v in (True, False)},
            "gate_builds": sorted({r.get("gate") for r in rows}),
            "stdfloor_exo_reason": next((r.get("exo") for r in rows
                                         if r.get("arm") == STDFLOOR_ARM), None),
        }
    out["D_live_rejudge_of_plain"] = {
        "counts": accounts_flat(plain),
        "ic_status": plain["input_contract"]["status"],
        "measurement_valid": plain.get("measurement_valid"),
        "mean_blown_frames_frac": plain["input_contract"]["mean_blown_frames_frac"],
    }
    return out


def main():
    ap = argparse.ArgumentParser(description="D 线：裁定 16.4 免罪册条目会签前核验（只读）")
    ap.add_argument("--out", default="tmp/agentD_review_20260929/D_cosign_k2seed0.json")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--expect", choices=("auto", "blocked", "exonerated", "rejected"), default="auto",
                    help="本轮期望。blocked = v1.5 前（三处阻塞必须命中，DR-D14）；"
                         "exonerated = v1.5 后复签（阻塞必须全部消失，DR-D22 验收判据）；"
                         "auto（默认）= 由实测推断并把推断值写进产物。"
                         "**判据不恒真**：两种期望各自都有会红的条件。")
    a = ap.parse_args()

    mod = load_gate_module()
    missing = [p for p in (PLAIN, CLIP12, CLIP5, STDFLOOR_REBLOWN, STDFLOOR_MAIN)
               if not (ROOT / p).exists()]
    if missing:
        raise SystemExit("缺产物，无法核验：%s" % missing)

    plain = judge(mod, PLAIN)
    c12 = judge(mod, CLIP12)
    c5 = judge(mod, CLIP5)
    sf_reblown = judge(mod, STDFLOOR_REBLOWN)
    sf_main = judge(mod, STDFLOOR_MAIN)

    conds = ruling10_conditions(mod, plain, c12, c5)
    conds5 = {k: True for k in ("cond1_C_equals_train_absmax",
                                "cond2_verdicts_and_counts_identical",
                                "cond3_diffs_enumerated_and_verdict_same",
                                "cond4_probe_path_C_build_recorded",
                                "cond5_scope_measurement_valid_only")}
    cosign_ok = {"by": "D", "fact_basis": True, "date": _now(),
                 "gate_build_at_cosign": mod.GATE_BUILD, "verifier": Path(__file__).name}
    base_entry = {"probe_kind": "clip_at_train_absmax",
                  "artifact": "<probe_artifact>", "sha256": "<probe_sha256>",
                  "clip_C": 12.469445, "ruling10_conditions": conds5, "cosign": cosign_ok,
                  "ruling_ref": "增补四 §3 裁定 10 / 增补五 裁定 16.4", "reason": "D 的模拟候选条目"}
    variants = [
        {"name": "v15_shape_scope_artifact", "key": "<plain_sha256>",
         "entry": dict(base_entry, scope="artifact")},
        {"name": "v15_shape_scope_arm", "key": ARM,
         "entry": dict(base_entry, scope="arm")},
        {"name": "mutant_clipC_wrong_5p0", "key": "<plain_sha256>",
         "entry": dict(base_entry, scope="artifact", clip_C=5.0)},
        {"name": "mutant_cond2_false", "key": "<plain_sha256>",
         "entry": dict(base_entry, scope="artifact",
                       ruling10_conditions=dict(conds5, cond2_verdicts_and_counts_identical=False))},
        {"name": "mutant_cosign_missing", "key": "<plain_sha256>",
         "entry": dict(base_entry, scope="artifact", cosign={"by": "", "fact_basis": None})},
        {"name": "reblown_kind_out_of_band", "key": "<plain_sha256>",
         "entry": {"scope": "artifact", "probe_kind": "reblown_single_source",
                   "artifact": "<probe_artifact>", "sha256": "<probe_sha256>",
                   "ruling_ref": "增补三 §12",
                   "reason": "反例：带内通道对 blown=0.212 必须仍然不受理（裁定 13 的牙不能被 v1.5 拔掉）"}},
    ]
    chans = channel_probe(mod, plain, c12, variants)
    real = mod.probe_exoneration_check(
        str(ROOT / PLAIN), plain["input_contract"]["mean_blown_frames_frac"],
        plain["input_contract"]["blown_metric_impl_status"])
    real_row = {
        "variant": "REAL_REGISTRY(configs/b_probe_exonerations.json)", "registry_sim": None,
        "key": (real or {}).get("key"), "scope": (real or {}).get("scope"),
        "probe_kind": (real or {}).get("probe_kind"),
        "exo_status": (real or {}).get("status"), "exo_note": (real or {}).get("note"),
        "mean_blown_frames_frac": plain["input_contract"]["mean_blown_frames_frac"],
        "blown_impl_status": plain["input_contract"]["blown_metric_impl_status"],
        "ic_status_of_plain": plain["input_contract"]["status"],
        "would_promote_to_probe_exonerated": False,
    }
    promo = promotion_gate_check(mod, plain, real_row["probe_kind"] or "clip_at_train_absmax")
    real_row["would_promote_to_probe_exonerated"] = bool(
        real_row["exo_status"] == "exonerated" and promo["promotion_actually_happened"])
    real_row["promotion_consistent"] = bool(
        promo["promotion_actually_happened"]
        == (real_row["exo_status"] == "exonerated"
            and promo["promotion_possible_without_code_change"]))
    chans = [real_row] + chans
    xchk = crosscheck(plain, c12, mod)

    sim = {c["variant"]: c["exo_status"] for c in chans if c["registry_sim"]}
    real_exonerated = bool(real_row["exo_status"] == "exonerated"
                           and real_row["would_promote_to_probe_exonerated"])

    # ---- 阻塞 vs 护栏：两类必须分开，否则判据会自相矛盾 ----
    # 「阻塞」= 挡在 裁定 10 通道（clip_at_train_absmax + scope=artifact）前面的东西，v1.5 后必须消失。
    # 「护栏」= 本来就该继续拒绝的情形（臂级豁免的指纹前置、争议带通道对带外值），v1.5 后必须**仍然**拒绝。
    # 早期版本把两类混在一个 blocker_* 计数里，导致 v1.5 落地后「blocker 仍为 true」——
    # 那其实是护栏在正常工作。混在一起就等于写了一把**永远红**或**永远绿**的尺子。
    clip_variant = next((k for k in sim if k.startswith("v15_shape_scope_artifact")),
                        "scope_artifact_clipkind")
    arm_variant = next((k for k in sim if k.startswith("v15_shape_scope_arm")), "scope_arm_clipkind")
    blocker_band = sim.get(clip_variant) == "out_of_band_refused"
    blocker_scope = sim.get(clip_variant) == "scope_requires_known_impl"
    blocker_promo = not promo["promotion_possible_without_code_change"]
    guard_arm_scope = sim.get(arm_variant) == "scope_requires_known_impl"
    guard_reblown_band = sim.get("reblown_kind_out_of_band") == "out_of_band_refused"

    verdict = {
        "cosign_fact_basis": bool(conds["ALL_FIVE_PASS"]),
        "registry_alone_is_sufficient": real_exonerated,
        "real_registry_exonerates_target": real_exonerated,
        "plain_ic_status_now": plain["input_contract"]["status"],
        "plain_measurement_valid_now": plain.get("measurement_valid"),
        "blocker_out_of_band_refused_hit": blocker_band,
        "blocker_scope_requires_known_impl_hit": blocker_scope,
        "blocker_promotion_guard_hit": blocker_promo,
        "blocker_definitions": {
            "blocker_*": "挡在 裁定 10 通道（clip_at_train_absmax + scope=artifact）前面 ⇒ v1.5 后必须**全 false**",
            "guard_*": "本该继续拒绝的情形 ⇒ v1.5 后必须**全 true**（护栏没被新通道拆掉）",
            "clip_channel_variant": clip_variant, "arm_scope_variant": arm_variant,
        },
        "guard_arm_scope_still_requires_impl": guard_arm_scope,
        "guard_reblown_channel_still_band_limited": guard_reblown_band,
    }
    if not verdict["cosign_fact_basis"]:
        verdict["COSIGN_DECISION"] = "**不予会签**：裁定 10 五条准入未全过，见 cond1..cond5。"
        auto_expect = "rejected"
    elif verdict["registry_alone_is_sufficient"]:
        verdict["COSIGN_DECISION"] = (
            "**复签通过**：事实基础成立（cond1..cond5 全过）且**真册子 + 现构建**已能让目标臂免罪"
            "（exo_status=exonerated、晋级闸 %s→%s、measurement_valid=%s）。"
            "本次会签锚在 gate_build=%s；`PENDING_IMPL` 标注可撤下。"
            % (promo["plain_ic_status_underlying"], promo["plain_ic_status"],
               verdict["plain_measurement_valid_now"], mod.GATE_BUILD))
        auto_expect = "exonerated"
    else:
        verdict["COSIGN_DECISION"] = (
            "事实基础成立（cond1..cond5 全过），但**登记册单独补条目不生效**：需 B 先改门禁两处代码"
            "（:374 争议带判定按 probe_kind 分通道 + :806 晋级闸允许 violated→probe_exonerated），"
            "且条目必须写 scope=artifact（:359 的 scope=arm 指纹前置会拒受理）。"
            "改任一处 GATE_BUILD 必变 ⇒ 裁定 16.3 改判 7 再次触发，会签须引用新 build。")
        auto_expect = "blocked"
    expect = a.expect if a.expect != "auto" else auto_expect
    verdict["expectation"] = expect
    verdict["expectation_source"] = ("--expect 显式指定" if a.expect != "auto" else "auto（由实测结果推断）")
    verdict["mutant_statuses"] = sim
    mutants_caught = bool(
        sim.get("v15_shape_scope_artifact") == "exonerated"
        and sim.get("v15_shape_scope_arm") != "exonerated"
        and sim.get("mutant_clipC_wrong_5p0") != "exonerated"
        and sim.get("mutant_cond2_false") != "exonerated"
        and sim.get("mutant_cosign_missing") != "exonerated"
        and sim.get("reblown_kind_out_of_band") != "exonerated")
    verdict["mutants_all_caught"] = mutants_caught
    if expect == "exonerated":
        # v1.5 复签：阻塞全消 + 护栏全在 + 晋级真的发生 + 反例全抓
        verdict["ACCEPTANCE"] = bool(
            conds["ALL_FIVE_PASS"] and real_exonerated
            and promo["promotion_actually_happened"] and real_row.get("promotion_consistent")
            and not (blocker_band or blocker_scope or blocker_promo)
            and guard_arm_scope and guard_reblown_band and mutants_caught)
    elif expect == "blocked":
        # v1.5 前：裁定 10 通道必须被挡住（带判定 + 晋级闸），且真册子救不动目标臂
        verdict["ACCEPTANCE"] = bool(conds["ALL_FIVE_PASS"] and not real_exonerated
                                     and (blocker_band or blocker_scope) and blocker_promo)
    else:
        verdict["ACCEPTANCE"] = False

    out = {
        "_doc": ("D 线会签前独立核验产物。只读 A/B/C 文件；模拟用的候选豁免册写在 "
                 "tmp/agentD_review_20260929/_D_sim_registry_*.json，**未触碰 configs/**。"),
        "generated_at": _now(),
        "generated_by": "scripts/d_verify_exoneration_cosign.py",
        "gate_live": {"gate_version": mod.GATE_VERSION, "gate_build": mod.GATE_BUILD,
                      "gate_spec_sha256": mod.GATE_SPEC_SHA,
                      "disputed_blown_band": list(mod.DISPUTED_BLOWN_BAND),
                      "input_blownup_tol": mod.INPUT_BLOWUP_TOL},
        "artifacts": {
            "plain": {"path": PLAIN, "sha256": sha256_file(PLAIN), "counts": accounts_flat(plain),
                      "ic_status": plain["input_contract"]["status"],
                      "mean_blown_frames_frac": plain["input_contract"]["mean_blown_frames_frac"],
                      "blown_impl_status": plain["input_contract"]["blown_metric_impl_status"],
                      "measurement_valid": plain.get("measurement_valid")},
            "clipC12p469445": {"path": CLIP12, "sha256": sha256_file(CLIP12),
                               "counts": accounts_flat(c12),
                               "clip": (c12.get("execution_constraints") or {}).get("norm_input_clip"),
                               "ic_status": c12["input_contract"]["status"],
                               "composite_policy": c12.get("composite_policy")},
            "clipC5p0": {"path": CLIP5, "sha256": sha256_file(CLIP5),
                         "counts": accounts_flat(c5),
                         "clip": (c5.get("execution_constraints") or {}).get("norm_input_clip"),
                         "ic_status": c5["input_contract"]["status"]},
            "stdfloor_reblown": {"path": STDFLOOR_REBLOWN, "sha256": sha256_file(STDFLOOR_REBLOWN),
                                 "counts": accounts_flat(sf_reblown),
                                 "ic_status": sf_reblown["input_contract"]["status"],
                                 "blown_impl_status": sf_reblown["input_contract"]["blown_metric_impl_status"],
                                 "probe_exoneration_status": ((sf_reblown.get("probe_exoneration") or {}).get("status")
                                                              if isinstance(sf_reblown.get("probe_exoneration"), dict)
                                                              else sf_reblown.get("probe_exoneration"))},
            "stdfloor_maindir": {"path": STDFLOOR_MAIN, "sha256": sha256_file(STDFLOOR_MAIN),
                                 "counts": accounts_flat(sf_main),
                                 "ic_status": sf_main["input_contract"]["status"],
                                 "blown_impl_status": sf_main["input_contract"]["blown_metric_impl_status"],
                                 "probe_exoneration_status": ((sf_main.get("probe_exoneration") or {}).get("status")
                                                              if isinstance(sf_main.get("probe_exoneration"), dict)
                                                              else sf_main.get("probe_exoneration"))},
        },
        "ruling10_five_conditions": conds,
        "exoneration_channel_probe": chans,
        "promotion_gate": promo,
        "crosscheck": xchk,
        "verdict": verdict,
    }

    op = ROOT / a.out
    op.parent.mkdir(parents=True, exist_ok=True)
    op.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    if not a.quiet:
        print("门禁构建（现场）：%s / %s / spec %s" % (mod.GATE_VERSION, mod.GATE_BUILD, mod.GATE_SPEC_SHA))
        print("\n== 裁定 10 五条准入（D 独立复算，现场重判）==")
        for k in ("cond1_C_equals_train_absmax", "cond2_verdicts_and_counts_identical",
                  "cond3_diffs_enumerated_and_verdict_same", "cond4_probe_path_C_build_recorded",
                  "cond5_scope_measurement_valid_only"):
            print("  %-42s %s" % (k, "PASS" if conds[k]["pass"] else "FAIL"))
        cp = conds["cond1_discriminative_counterproof_C5"]
        print("  %-42s verdict_diff_seeds=%s counts=%s"
              % ("cond1_counterproof_C5", cp["verdict_diff_seeds"], cp["counts_probe_C5"]))
        print("  ALL_FIVE_PASS = %s" % conds["ALL_FIVE_PASS"])
        print("\n== 豁免通道实证（真实 probe_exoneration_check，候选册在 tmp/）==")
        for c in chans:
            print("  %-30s scope=%-9s kind=%-24s -> %s"
                  % (c["variant"], c["scope"], c["probe_kind"], c["exo_status"]))
        print("  反例全部被抓 = %s" % verdict.get("mutants_all_caught"))
        print("  阻塞（v1.5 后须全 false）：band=%s scope=%s promotion=%s"
              % (verdict["blocker_out_of_band_refused_hit"],
                 verdict["blocker_scope_requires_known_impl_hit"],
                 verdict["blocker_promotion_guard_hit"]))
        print("  护栏（v1.5 后须全 true）：arm_scope_requires_impl=%s reblown_band_limited=%s"
              % (verdict["guard_arm_scope_still_requires_impl"],
                 verdict["guard_reblown_channel_still_band_limited"]))
        print("\n== 晋级闸（:807）==")
        print("  机制 = %s" % promo["mechanism"])
        print("  底层 ic_status = %s（blown %s > tol %s）；允许晋级 = %s；实测晋级发生 = %s；观察值 = %s"
              % (promo["plain_ic_status_underlying"], promo["mean_blown_frames_frac"],
                 promo["input_blownup_tol"], promo["promotion_possible_without_code_change"],
                 promo["promotion_actually_happened"], promo["plain_ic_status"]))
        for ln, txt in promo["source_lines"]:
            print("  源码 %s:%d  %s" % (GATE_PY.name, ln, txt[:100]))
        print("\n== 对账 ==")
        if "B_authority" in xchk:
            print("  B 权威表 %s：ic_status=%s" % (xchk["B_authority"]["gate"],
                                                  xchk["B_authority"]["summary_ic_status"]))
            print("  B 受控合计 %s；D 昨日 48 臂重判受控合计 %s"
                  % (xchk["B_authority"]["controlled_success_total"],
                     (xchk.get("D_regate48") or {}).get("controlled_success_total")))
        print("  stdfloor：B 判 %s" % (xchk.get("B_arms", {}).get(STDFLOOR_ARM, {}).get("B_file")))
        print("           D 现场判 reblown -> %s / 主目录 -> %s"
              % (out["artifacts"]["stdfloor_reblown"]["ic_status"],
                 out["artifacts"]["stdfloor_maindir"]["ic_status"]))
        print("\n== 会签结论 ==\n  %s" % verdict["COSIGN_DECISION"])
        print("\n写出:", a.out)

    ok = bool(verdict.get("ACCEPTANCE"))
    if not a.quiet:
        print("本轮期望：%s（%s）⇒ ACCEPTANCE=%s" % (expect, verdict["expectation_source"], ok))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
