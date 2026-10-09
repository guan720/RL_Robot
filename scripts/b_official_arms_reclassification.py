#!/usr/bin/env python3
"""B③：A 的全部官方臂在**当前**门禁下的重判与重分类表（监管 增补二 §2 / §5.B③）。

为什么需要：监管 增补二 §2 定了两条「才允许作为率证据引用」的生效条件 ——
  ① `norm_input_blown_frames_frac` 已记录且 < 0.05；② 过官方门禁重判。
但截至本轮，仓库里**没有**一份覆盖全部官方臂、且带当前构建指纹的裁定产物：
  · `runs/infra/lerobot_act_env_20260928/gate_*.json` 有 43 份历史裁定，
    横跨至少 5 个不同 `gate_build`（无指纹 / 800e1d08a174 / 6bf27fa39e83 /
    369595c86a07 / 28290b9c1b25 / 22a7d92bec0a），**没有一份是当前构建**；
  · `runs/infra/b_gate_sensitivity/report.json` 只覆盖 12 个臂，且产物是阈值敏感性、不是裁定。
所以「哪些臂的数字现在可以引用」这个问题此前无法回答。

本脚本用当前门禁重判**全部** `official_act_truth20_*.json`，逐臂给出：
  裁定计数（受控/insuff/over_lift/flick）、输入契约状态、是否复合 policy、
  受控成功数在 C5 ±0.005 上的敏感带、以及**能否作为率证据引用**的三值结论。

只读：不修改任何评测产物，也不动 A 目录里的 43 份历史裁定（那是 A 的写入范围；
本脚本把结论写到 `runs/infra/b_official_arms/`）。

用法：
    python3 scripts/b_official_arms_reclassification.py
    python3 scripts/b_official_arms_reclassification.py --delta 0.005
"""
from __future__ import annotations
import argparse, glob as globmod, importlib.util, json, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "b_gate_controlled_success.py"
OFFICIAL_GLOB = "runs/infra/lerobot_act_env_20260928/official_act_truth20_*.json"
COUNT_KEYS = ("controlled_success", "provisional_pass", "over_lift", "flick", "insufficient_lift")
# v1.3：同名产物若存在**补测/重测**版本，以重测版为准（A 线 §9.A② 补测 5 个盲臂、
# §12 裁定 1 重测争议带 1 臂）。取代顺序自上而下，命中即用，并记下被取代的旧产物。
# 不做取代就会同时统计同一臂的两个世代，族均值分母被重复计数污染。
SUPERSEDE_DIRS = ("reblown", "blindfix")


def resolve_files(official):
    """返回 [(生效产物路径, source, 被取代的旧路径 or None)]。"""
    out = []
    for f in official:
        p = Path(f)
        chosen, source = p, "official"
        for sub in SUPERSEDE_DIRS:
            cand = p.parent / sub / p.name
            if cand.exists():
                chosen, source = cand, sub
                break                      # SUPERSEDE_DIRS 的顺序即优先级
        out.append((str(chosen), source, (str(p) if chosen != p else None)))
    return out


def load_gate():
    spec = importlib.util.spec_from_file_location("b_gate", str(GATE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Args:
    def __init__(self, rise_cap, final_rise, assist_off=False):
        self.rise_cap = rise_cap
        self.final_rise = final_rise
        self.assist_off = assist_off


def counts(row):
    a = (row.get("accounts") or {}).get("policy_independent", {}) or {}
    return {k: (a.get(k) or 0) for k in COUNT_KEYS}


def pooled_insuff(pool, thr):
    """B-3 的跨臂版本：把逐局 final_rise 汇到一起算，而不是对各臂中位数再取平均。

    为什么必须池化：`insufficient_lift` 在各臂分布极不均（有的臂 0 局、有的 11 局），
    按臂平均会让「1 局的臂」和「11 局的臂」等权，得到的数不是任何一局的真实差距。
    """
    if not pool:
        return {"n": 0}
    import numpy as np
    a = np.asarray([v for _, v in pool], dtype=float)
    t = float(thr)
    per_arm = Counter(arm for arm, _ in pool)
    return {
        "n": int(a.size), "n_arms": len(per_arm), "threshold": t,
        "final_rise_median": round(float(np.median(a)), 5),
        "final_rise_p10": round(float(np.percentile(a, 10)), 5),
        "final_rise_p90": round(float(np.percentile(a, 90)), 5),
        "final_rise_min": round(float(a.min()), 5), "final_rise_max": round(float(a.max()), 5),
        "gap_median": round(float(t - np.median(a)), 5),
        "gap_min_best": round(float(t - a.max()), 5),
        "n_within_0p005": int((a >= t - 0.005).sum()),
        "n_within_0p010": int((a >= t - 0.010).sum()),
        "frac_within_0p005": round(float((a >= t - 0.005).mean()), 3),
        "top_arms": per_arm.most_common(6),
        "c5_scenario_impact": c5_scenarios(a, t),
        "note": ("池化 %d 局 / %d 臂：中位差 %.4f m，最好一局只差 %.4f m，"
                 "%.0f%% 落在门槛下方 0.005 m 内。这个比例决定「该修策略还是该由 D 重定 C5」"
                 "（ADR-A-005 #3）：比例高 = 主要卡在阈值上，训练解决不了。"
                 % (a.size, len(per_arm), t - float(np.median(a)), t - float(a.max()),
                    100 * float((a >= t - 0.005).mean()))),
    }


# C5 情景表：只报「若把 C5 改成 X，池化 insuff 里有多少局会变成受控成功」。
# **B 不改 C5**（规格 §2.7：改这个值会放大所有历史臂的成功率，属监管裁决范围），
# 但 D 要裁 ADR-A-005 #3 就必须知道每个候选值的杠杆有多大 —— 这是门禁线的职责。
C5_SCENARIOS = [
    (0.04, "现行 C5 = 0.92 × 方块全高（0.04341）"),
    (0.035, "现行 −0.005（敏感带下沿）"),
    (0.03, "0.69 × 方块全高"),
    (0.0217, "0.50 × 方块全高（半高）"),
    (0.0085, "robosuite `_check_success` 换算到相对初始高度口径的等效阈（规格 §2.7 实测）"),
]


def c5_scenarios(arr, thr_now):
    """insufficient_lift 的局都是 held_at_end=True ∧ grasp_verified ∧ max_rise≤rise_cap，
    所以降低 C5 只会把它们**直接**变成 controlled_success，不会牵动 flick/over_lift 分类。
    这让「改阈值的杠杆」可以精确计算，不需要重跑评测。"""
    out = []
    for thr, why in C5_SCENARIOS:
        out.append({"c5": thr, "why": why,
                    "n_insuff_flipped_to_controlled": int((arr >= thr).sum()),
                    "frac_of_pooled_insuff": round(float((arr >= thr).mean()), 3),
                    "is_current": abs(thr - thr_now) < 1e-9})
    return out


def dedup_generations(members):
    """同一 (臂, 口径) 下若有多个世代，只保留一个 —— 否则族均值的 n 被重复计数灌水。

    实测（v1.3 首跑）：48 份产物里有 **5 组**这种重复，都是同一 checkpoint 的
    `X.json`（A 补测版 blindfix/，带 blown 指纹）与 `X_gatefields.json`（旧留档，走存量豁免）
    并存。两版 controlled_success 逐组相同（0/0、0/0、0/0、1/1、0/0），所以**均值没被带偏**，
    但 `n_arms` 从 3 灌成 6 —— 族会被看起来「采样更充分」，n 与摆幅的可信度都被高估。

    优先级：带已知 blown 指纹 > 补测/重测来源 > gatefields 世代。
    """
    src_rank = {"reblown": 3, "blindfix": 2, "official": 1}
    best = {}
    for m in members:
        core = m["arm"][:-len("_gatefields")] if m["arm"].endswith("_gatefields") else m["arm"]
        k = (m.get("seed") or "-", core)
        score = (1 if m.get("blown_impl_status") == "known" else 0,
                 src_rank.get(m.get("source"), 0),
                 1 if m.get("artifact_generation") == "gatefields" else 0)
        if k not in best or score > best[k][0]:
            best[k] = (score, m)
    kept = [v[1] for v in best.values()]
    kept_ids = {id(m) for m in kept}
    return kept, [m for m in members if id(m) not in kept_ids]


def family_of(arm: str):
    """把臂名拆成 (配置族, seed, replan 变体)。

    为什么必须有这一层：实测同一配置族跨 seed 的受控成功数能从 **0 摆到 19**
    （`trimdone0_minmax_k2_lr1e-5_s20k` 的 seed2=0 / seed3=17 / seed4=19）。
    在这种方差下引用任何**单个 seed** 的数字都会严重误导 —— 挑到 seed4 就高估 2.4 倍。
    所以可引用的单位是「族 × 口径」的汇总，不是臂。
    replan 变体单列，因为它是不同的运行口径（见 cadence 说明），不能与默认口径混算。
    """
    # `_gatefields` 标记的是**同一个臂的第二次评测**（A 补齐门禁字段后重跑），
    # 不是另一个配置。折进同一族，但把世代记下来。
    gen = "gatefields" if arm.endswith("_gatefields") else "legacy"
    core = arm[:-len("_gatefields")] if gen == "gatefields" else arm
    m = re.search(r"_replan(\d+)$", core)
    replan = ("@replan%s" % m.group(1)) if m else ""
    base = core[:m.start()] if m else core
    s = re.search(r"_seed(\d+)$", base)
    seed = ("seed%s" % s.group(1)) if s else None
    fam = base[:s.start()] if s else base
    return fam + replan, seed, gen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta", type=float, default=0.005, help="C5 敏感带半宽（默认 ±0.005 m）")
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_official_arms/reclassification.json"))
    a = ap.parse_args()

    gate = load_gate()
    base_args = Args(gate.RISE_CAP, gate.FINAL_RISE_MIN)
    lo_args = Args(gate.RISE_CAP, gate.FINAL_RISE_MIN - a.delta)
    hi_args = Args(gate.RISE_CAP, gate.FINAL_RISE_MIN + a.delta)

    official = sorted(globmod.glob(str(ROOT / OFFICIAL_GLOB)))
    resolved = resolve_files(official)
    files = [r[0] for r in resolved]
    src_of = {r[0]: (r[1], r[2]) for r in resolved}
    print("=" * 118)
    print("B③ 官方臂重分类表（当前门禁重判）")
    print("门禁构建：gate_version=%s gate_build=%s spec_sha256=%s"
          % (gate.GATE_VERSION, gate.GATE_BUILD, gate.GATE_SPEC_SHA))
    print("代码版本：git_commit=%s" % (gate.GIT_COMMIT or "非 git 环境"))
    print("判据：rise_cap=%.3f  final_rise_min=%.3f  敏感带 ±%.3f" % (gate.RISE_CAP, gate.FINAL_RISE_MIN, a.delta))
    print("命中官方产物：%d 份；其中被补测/重测版取代：%d 份（%s）"
          % (len(official), sum(1 for v in src_of.values() if v[1]),
             dict(Counter(v[0] for v in src_of.values()))))
    print("=" * 118)
    if not files:
        print("[FATAL] 没命中任何官方产物，检查 glob：%s" % OFFICIAL_GLOB)
        return 2

    rows = []
    insuff_pool = []      # B-3：跨臂池化的 insufficient_lift 逐局 final_rise（不是「均值的均值」）
    for f in files:
        rel = str(Path(f).relative_to(ROOT))
        r = gate.judge_file(f, base_args)
        if "error" in r:
            rows.append({"arm": Path(rel).stem, "file": rel, "judge_error": r["error"]})
            continue
        arm_name = Path(rel).stem.replace("official_act_truth20_", "")
        for e in (r.get("per_episode") or []):
            if e.get("verdict") == "insufficient_lift" and e.get("final_rise") is not None:
                insuff_pool.append((arm_name, float(e["final_rise"])))
        raw_doc = json.loads(Path(f).read_text())
        # 重规划口径必须进表：实测 44 个官方臂横跨 **8 种** (chunk, n_action_steps, replan_every)
        # 组合。k1 臂是 (1,1,1) —— 每帧都重新推理，推理次数是 (4,4,4) 组的 4 倍；
        # 把不同口径的臂按受控成功数排成一张平表，等于在比「策略好坏」和「算力多少」的混合物。
        cadence = {"chunk_size": raw_doc.get("chunk_size"),
                   "n_action_steps": raw_doc.get("n_action_steps"),
                   "replan_every": raw_doc.get("replan_every")}
        cadence_key = "%s/%s/%s" % (cadence["chunk_size"], cadence["n_action_steps"],
                                    cadence["replan_every"])
        ic = r.get("input_contract") or {}
        bm = r.get("blown_metric") or {}
        ex = r.get("probe_exoneration") or {}
        c = counts(r)
        lo = counts(gate.judge_file(f, lo_args))["controlled_success"]
        hi = counts(gate.judge_file(f, hi_args))["controlled_success"]
        # 监管 增补二 §2 的两条生效条件，逐条判定，不含糊。
        # v1.3：有效状态从 2 个变成 4 个（新增 not_applicable_verified / probe_exonerated），
        # 硬写 == "verified_ok" 会把裁定 2、裁定 3 放行的臂重新打成「条件不满足」。
        cond_blowup = (ic.get("status") in gate.IC_VALID_STATUSES)
        cond_rejudged = (r.get("gate_build") == gate.GATE_BUILD)
        cond_non_composite = not r.get("composite_policy")
        # 规格 §3.1 规则 3：口径不可解析（chunk/n_action/replan 任一为 None）的臂不进族均值分母，
        # 否则「无口径」的臂会和 (4,4,4)、(1,1,1) 混在一起平均，均值失去意义。
        cadence_resolved = "None" not in cadence_key
        if not r.get("measurement_valid"):
            citable = "NOT_CITABLE_measurement_invalid"
        elif c["controlled_success"] == 0:
            # 测量有效、但受控成功为 0：没有正的「率」可主张，
            # 但它**必须计入族均值** —— 把它排除会让均值系统性偏高
            # （实测 k1 族：只算 seed0 得 20.0/20，算上 seed1=0 才是真实的 10.0/20）。
            citable = "no_controlled_success_to_cite"
        elif cond_blowup and cond_rejudged and cond_non_composite:
            citable = "citable_with_sensitivity_band"
        else:
            citable = "candidate_only"
        if not cadence_resolved and citable != "NOT_CITABLE_measurement_invalid":
            citable = "candidate_only"          # 口径不明 -> 不得进入可引用集
        rows.append({
            "arm": Path(rel).stem.replace("official_act_truth20_", ""), "file": rel,
            "source": src_of.get(f, ("official", None))[0],
            "supersedes": src_of.get(f, (None, None))[1],
            "episodes": r.get("episodes_total"), "raw_success": r.get("raw_success"),
            "cadence": cadence, "cadence_key": cadence_key,
            "cadence_resolved": cadence_resolved,
            **c, "ic_status": ic.get("status"),
            "mean_blown_frames_frac": ic.get("mean_blown_frames_frac"),
            "blown_metric_impl": ic.get("blown_metric_impl"),
            "blown_impl_status": bm.get("status"),
            "threshold_provenance": ic.get("threshold_provenance"),
            "in_disputed_band": ic.get("in_disputed_band"),
            "probe_exoneration": ex.get("status"),
            # v1.5（DR-008）：豁免分两条通道，只记 status 无法区分「带内重测」与
            # 「带外的 裁定 10 clip 探针」。汇总与引用都要能分开看，故把 kind 也落到行级。
            "probe_exoneration_kind": ex.get("probe_kind"),
            "probe_exoneration_band_checked": ex.get("band_checked"),
            # 裁定 25 护栏①：「会签锚在哪个 build 上」是可核事实，必须随数字一起走，
            # 所以行级也要回显，不能只在 summary 层给个桶。
            "probe_exoneration_cosign_build": ex.get("cosign_build_current"),
            "probe_exoneration_cosign_build_matches": ex.get("cosign_build_matches"),
            # 裁定 23.4 的**聚合侧先行**（判定侧待 v1.6，见 DR-010）：这里只做聚合，
            # 不重算任何判定 —— 覆盖率直接取门禁已回报的 field_presence / episodes_total，
            # 避免出现「同一判据两个实现」（裁定 21 / DR-D17 的教训）。
            "terminal_kind_coverage": {"n": (r.get("field_presence") or {}).get("terminal_kind"),
                                       "of": r.get("episodes_total")},
            # D 的验收判据里有 measurement_valid 47/1，但它原先只能由 citable 反推。
            # 直接透出（纯聚合，不新判据），让「47/1」成为机器可核的一格而不是散文。
            "measurement_valid": r.get("measurement_valid"),
            "closed_loop_norm_absmax": ic.get("closed_loop_norm_absmax"),
            "composite_policy": r.get("composite_policy"),
            "active_constraints": r.get("active_constraints"),
            "gate_pass": r.get("gate_pass"), "gate_reason": r.get("gate_reason"),
            "measurement_invalid_reasons": r.get("measurement_invalid_reasons"),
            "n_phase_vocab_mismatch": r.get("n_phase_vocab_mismatch"),
            "ctrl_band": [min(lo, hi, c["controlled_success"]), max(lo, hi, c["controlled_success"])],
            "ctrl_lo": lo, "ctrl_hi": hi,
            "threshold_sensitive": (lo != hi),
            "conditions": {"blowup_recorded_and_under_tol": cond_blowup,
                           "rejudged_under_current_build": cond_rejudged,
                           "non_composite_policy": cond_non_composite},
            "citable": citable,
            # 族均值的分母口径：只排除**测量无效**的臂，不排除「有效但受控为 0」的臂。
            # v1.3 追加：口径不可解析的臂同样不进分母（规格 §3.1 规则 3）。
            "included_in_family_mean": (citable != "NOT_CITABLE_measurement_invalid"
                                        and cadence_resolved),
            "gate_build": r.get("gate_build"), "gate_spec_sha256": r.get("gate_spec_sha256"),
            "git_commit": r.get("git_commit"),
        })

    bad = [r for r in rows if "judge_error" in r]
    good = [r for r in rows if "judge_error" not in r]

    hdr = "%-52s %4s %4s %4s %5s %5s %5s %-12s %-9s %s"
    print("**按重规划口径分组打印**（chunk/n_action/replan）。跨组比较不是同算力比较：")
    print("  例如 (1,1,1) 每帧重新推理，推理次数是 (4,4,4) 组的 4 倍 —— 不得把两组的受控成功数直接排名。")
    for cad in sorted({r["cadence_key"] for r in good}):
        grp = [r for r in good if r["cadence_key"] == cad]
        print("\n--- 口径 chunk/n_action/replan = %s（%d 臂）---" % (cad, len(grp)))
        print(hdr % ("arm", "n", "raw", "ctrl", "insuf", "ovlft", "flick", "ic_status", "敏感带", "可引用性"))
        for r in sorted(grp, key=lambda x: (-x["controlled_success"], x["arm"])):
            print(hdr % (r["arm"][:52], r["episodes"], r["raw_success"], r["controlled_success"],
                         r["insufficient_lift"], r["over_lift"], r["flick"], r["ic_status"],
                         ("%d→%d" % (r["ctrl_lo"], r["ctrl_hi"])) if r["threshold_sensitive"] else "稳定",
                         r["citable"]))
    for r in bad:
        print("%-52s  judge_error: %s" % (r["arm"][:52], r["judge_error"]))

    # ---- 汇总 ----
    print("\n" + "=" * 118)
    print("汇总（%d 份产物）" % len(rows))
    print("  输入契约：%s" % dict(Counter(r.get("ic_status", "judge_error") for r in rows)))
    print("  可引用性：%s" % dict(Counter(r.get("citable", "judge_error") for r in rows)))
    n_ctrl = sum(1 for r in good if r["controlled_success"] > 0)
    n_sens = sum(1 for r in good if r["threshold_sensitive"])
    print("  有受控成功的臂：%d / %d；其中阈值敏感：%d" % (n_ctrl, len(good), n_sens))
    viol = [r["arm"] for r in good if r["ic_status"] == "violated"]
    miss = [r["arm"] for r in good if r["ic_status"] in ("unverified", "partial")]
    print("  **输入契约违例（不得引用任何率）**：%d 个%s" % (len(viol), ("：" + ", ".join(viol)) if viol else ""))
    print("  **缺/不全 blowup 字段（同样 INVALID）**：%d 个%s" % (len(miss), ("：" + ", ".join(miss)) if miss else ""))
    comp = [r["arm"] for r in good if r["composite_policy"]]
    print("  复合 policy：%d 个%s" % (len(comp), ("：" + ", ".join(comp)) if comp else ""))
    print("  重规划口径分布：%s"
          % dict(Counter(r["cadence_key"] for r in good)))
    print("  产物来源：%s（补测/重测版按 SUPERSEDE_DIRS 优先，取代 %d 份旧产物）"
          % (dict(Counter(r.get("source", "official") for r in good)),
             sum(1 for r in good if r.get("supersedes"))))
    print("  blown 指纹状态：%s" % dict(Counter(r.get("blown_impl_status") for r in good)))
    # v1.5（DR-008）修正一处**漏计**：旧写法把豁免统计按 in_disputed_band 过滤，
    # 在只有带内一条通道时是对的；v1.5 起 裁定 10 通道的目标臂 blown=0.212 必然带外，
    # 于是它 ic_status=probe_exonerated 却不进这个计数（实测报 {"exonerated": 1}，
    # 而真实是 2 臂）—— 权威表里的假陈述，必须按全通道统计。
    print("  争议带 [0.03,0.08] 内：%d 臂" % sum(1 for r in good if r.get("in_disputed_band")))
    print("  豁免状态（**全通道**，含带外的 裁定 10 通道）：%s"
          % dict(Counter(r.get("probe_exoneration") for r in good
                         if r.get("probe_exoneration"))))
    print("  豁免按通道：%s；其中带内豁免 %d 臂"
          % (dict(Counter(r.get("probe_exoneration_kind") for r in good
                          if r.get("probe_exoneration") == "exonerated")),
             sum(1 for r in good if r.get("in_disputed_band")
                 and r.get("probe_exoneration") == "exonerated")))
    print("  口径不可解析（不进族均值分母）：%d 臂"
          % sum(1 for r in good if not r.get("cadence_resolved")))
    pm = [r["arm"] for r in good if r.get("n_phase_vocab_mismatch")]
    print("  phase 词表矛盾（裁定 1）：%d 臂%s" % (len(pm), ("：" + ", ".join(pm)) if pm else ""))
    # 裁定 25 护栏①（DR-D22）：会签 build 不一致期间被豁免的臂，必须计入**独立桶**，
    # 不得直接算「已免罪」。实现为并列桶（不从 ic_status / by_kind 里扣减）：
    # D 在 裁定 27 §12.1/§12.2 已按「by_kind 2 臂 + 桶未实现」的实际形状预先认可了
    # ic_status 45/2/1 与 citable 25/22/1，扣减会与那份认可冲突；前提③ 换块后本桶 n=0，
    # 两种读法收敛于同一张表。
    # 判据必须是 `is False` 而不是 `is not True`：三值语义里
    #   True  = 会签锚在当前 build（已复签）
    #   False = 会签存在但锚在别的 build（**这才是**护栏①要承接的「待复签」）
    #   None  = 该通道**不要求**会签（reblown_single_source 的册子条目没有 cosign 字段，
    #           见 configs/b_probe_exonerations.json 的 _schema：cosign 仅 clip_at_train_absmax）
    # 把 None 也算进「待复签」会制造一条永不消失的假红 —— 与本仓「恒假的闸等于没有闸」
    # （裁定 27.1）同型：桶里长期挂着一条清不掉的臂，真待复签来的时候一样被忽略。
    exo = [r for r in good if r.get("probe_exoneration") == "exonerated"]
    pcr = [r["arm"] for r in exo
           if r.get("probe_exoneration_cosign_build_matches") is False]
    cna = [r["arm"] for r in exo
           if r.get("probe_exoneration_cosign_build_matches") is None]
    print("  待会签复验（裁定 25 护栏①）：%d 臂%s"
          % (len(pcr), ("：" + ", ".join(pcr)) if pcr else "（已清零：D 的复签块已换进 configs）"))
    print("  豁免通道不要求会签（cosign_build_matches=None，非待复签）：%d 臂%s"
          % (len(cna), ("：" + ", ".join(cna)) if cna else ""))
    # 裁定 23.4：终局语义自检**能不能跑**必须一句可说，不能逐份裁定里翻。
    # 覆盖不足时，门禁现值 suspect_truncation_labeled_as_failure 恒为 false（空转判据，
    # 裁定 23.2 要求改三值，属 v1.6 批次）⇒ 本桶是那之前唯一的可见性护栏。
    tsu = [r["arm"] for r in good
           if (r.get("terminal_kind_coverage") or {}).get("n") is not None
           and (r.get("terminal_kind_coverage") or {}).get("of") is not None
           and r["terminal_kind_coverage"]["n"] < r["terminal_kind_coverage"]["of"]]
    print("  终局语义自检不可用（terminal_kind 覆盖不足）：%d 臂%s"
          % (len(tsu), ("：" + ", ".join(tsu)) if tsu else ""))
    # 裁定 30 / DR-D29：分布层陈述必须带构建指纹，且必须能从权威表**机器核**。
    # 起因：A 的预登记写「21 臂里受控 4–9 = 0（中间是空的）」，在 v1.2.1 口径下成立
    # （目标臂当时 measurement_valid=False，不在有效臂集里）；裁定 10 免罪让它回到分布里
    # ⇒ 现口径下 4–9 = **1**，而那一步**没有任何一线传播**。
    # 一般规则（D 立的）：**计数层（逐局 verdict 计数）= 构建不变**（v1.4→v1.5 实测一格未动）；
    # **分布层（直方图 / 区间计数 / 极差 / 族均值的 n）= 构建相关**，因为它按 measurement_valid
    # 的**臂集**统计，而免罪/降级会改这个臂集（实测无效臂 v1.2.1 = 7 → v1.5 = 1）。
    # 所以这里把两套臂集的直方图都落进表里：谁要主张某个区间空不空，直接读本表 + 表头的 gate_build，
    # 不必再手工 join 一遍（手工 join 的结果不会随构建自动更新，这正是本次过期的成因）。
    hist_all = dict(sorted(Counter(r["controlled_success"] for r in good).items()))
    hist_valid = dict(sorted(Counter(r["controlled_success"] for r in good
                                     if r.get("measurement_valid")).items()))
    print("  受控成功直方图（全部 %d 臂）：%s" % (len(good), hist_all))
    print("  受控成功直方图（measurement_valid %d 臂）：%s"
          % (sum(1 for r in good if r.get("measurement_valid")), hist_valid))
    pooled = pooled_insuff(insuff_pool, gate.FINAL_RISE_MIN)
    if pooled.get("n"):
        print("  **B-3 insufficient_lift 池化诊断**：%s" % pooled["note"])
        print("      median=%.4f p10=%.4f p90=%.4f min=%.4f max=%.4f | 距 C5 中位差 %.4f、"
              "最好 %.4f | ≤0.005 有 %d 局(%.0f%%)、≤0.010 有 %d 局"
              % (pooled["final_rise_median"], pooled["final_rise_p10"], pooled["final_rise_p90"],
                 pooled["final_rise_min"], pooled["final_rise_max"], pooled["gap_median"],
                 pooled["gap_min_best"], pooled["n_within_0p005"],
                 100 * pooled["frac_within_0p005"], pooled["n_within_0p010"]))
        print("      贡献最多的臂：%s" % pooled["top_arms"])
        print("      C5 情景杠杆（B 不改 C5，只量化给 D 裁 ADR-A-005 #3）：")
        for sc in pooled["c5_scenario_impact"]:
            print("        C5=%-7s -> 池化 insuff 中 %3d/%3d 局（%5.1f%%）会变成受控成功%s   %s"
                  % (sc["c5"], sc["n_insuff_flipped_to_controlled"], pooled["n"],
                     100 * sc["frac_of_pooled_insuff"], "（现行）" if sc["is_current"] else "        ",
                     sc["why"]))

    # ---- 族 × 口径汇总（**这才是可引用的单位**）----
    fams = {}
    gen_dups = []
    for r in good:
        fam, seed, gen = family_of(r["arm"])
        key = (fam, r["cadence_key"])
        fams.setdefault(key, []).append({**r, "seed": seed, "artifact_generation": gen})
    print("\n--- 族 × 口径 汇总（可引用的单位；单臂数字不得单独引用）---")
    print("%-46s %-9s %4s %-14s %-22s %s"
          % ("配置族", "口径", "n臂", "受控 min~max", "均值(测量有效的臂)", "各 seed"))
    rollup = []
    for (fam, cad), members in sorted(fams.items(), key=lambda kv: -max(m["controlled_success"] for m in kv[1])):
        members, dropped = dedup_generations(members)
        gen_dups.extend(dropped)
        cit = [m for m in members if m["included_in_family_mean"]]
        vals = [m["controlled_success"] for m in members]
        cit_vals = [m["controlled_success"] for m in cit]
        mean_cit = (sum(cit_vals) / len(cit_vals)) if cit_vals else None
        per_seed = ", ".join("%s=%d%s" % (m["seed"] or "-", m["controlled_success"],
                                          "" if m["included_in_family_mean"] else "(测量无效,不计入)")
                             for m in sorted(members, key=lambda x: str(x["seed"])))
        print("%-46s %-9s %4d %-14s %-22s %s"
              % (fam[:46], cad, len(members), "%d~%d" % (min(vals), max(vals)),
                 ("%.1f/20 (n=%d)" % (mean_cit, len(cit_vals))) if mean_cit is not None else "无有效臂",
                 per_seed[:120]))
        rollup.append({"family": fam, "cadence_key": cad, "n_arms": len(members),
                       "ctrl_min": min(vals), "ctrl_max": max(vals),
                       "ctrl_mean_valid": mean_cit, "n_valid_for_mean": len(cit_vals),
                       "n_citable_positive": sum(1 for m in members
                                                 if m["citable"] == "citable_with_sensitivity_band"),
                       "seed_spread": (max(vals) - min(vals)),
                       "n_generation_duplicates_dropped": sum(
                           1 for dd in gen_dups
                           if family_of(dd["arm"])[0] == fam and dd["cadence_key"] == cad),
                       "generation_duplicates_dropped": [
                           {"arm": dd["arm"], "source": dd.get("source"),
                            "blown_impl_status": dd.get("blown_impl_status"),
                            "controlled_success": dd["controlled_success"]}
                           for dd in gen_dups
                           if family_of(dd["arm"])[0] == fam and dd["cadence_key"] == cad],
                       "members": [{k: m[k] for k in ("arm", "seed", "controlled_success",
                                                      "raw_success", "ic_status", "citable",
                                                      "included_in_family_mean",
                                                      "ctrl_lo", "ctrl_hi", "source",
                                                      "blown_impl_status")} for m in members]})
    worst = max(rollup, key=lambda x: x["seed_spread"]) if rollup else None
    if worst:
        print("\n  最大 seed 间摆动：%s（口径 %s）受控成功 %d~%d，摆幅 %d 局"
              % (worst["family"], worst["cadence_key"], worst["ctrl_min"], worst["ctrl_max"],
                 worst["seed_spread"]))
        print("  -> 任何「某臂受控成功 N/20」的单独引用都属挑 seed；对外只报族均值 + 摆幅。")
    if gen_dups:
        print("\n  同臂多世代去重：丢弃 %d 份重复成员（同一 checkpoint 的两个世代并存）" % len(gen_dups))
        for dd in gen_dups:
            print("    - %-56s src=%-9s impl=%-30s ctrl=%d"
                  % (dd["arm"][:56], dd.get("source"), str(dd.get("blown_impl_status"))[:30],
                     dd["controlled_success"]))
        print("  -> 不去重会让族的 n_arms 被灌水（实测 train24_lr1e-5_actionminmax 族 3 个 checkpoint 报成 6 臂）；")
        print("     本仓这 5 组两版受控成功数逐组相同，所以**均值未被带偏**，被带偏的是 n 与摆幅的可信度。")
    print("  历史裁定漂移：runs/infra/lerobot_act_env_20260928/gate_*.json 共 %d 份，"
          "本轮全部**未**被本脚本改写（A 的写入范围）"
          % len(globmod.glob(str(ROOT / "runs/infra/lerobot_act_env_20260928/gate_*.json"))))
    print("=" * 118)

    outp = Path(a.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({
        "gate_version": gate.GATE_VERSION, "gate_build": gate.GATE_BUILD,
        "gate_spec_sha256": gate.GATE_SPEC_SHA, "delta": a.delta,
        "citation_conditions_source": "rl_harness_supervision/supervisor_memo_20260928.md 增补二 §2",
        "n_artifacts": len(rows), "n_judge_error": len(bad),
        "summary": {"ic_status": dict(Counter(r.get("ic_status", "judge_error") for r in rows)),
                    "citable": dict(Counter(r.get("citable", "judge_error") for r in rows)),
                    "arms_with_controlled_success": n_ctrl, "threshold_sensitive": n_sens,
                    "violated": viol, "missing_blowup": miss, "composite": comp,
                    "source": dict(Counter(r.get("source", "official") for r in good)),
                    "n_superseded": sum(1 for r in good if r.get("supersedes")),
                    "blown_impl_status": dict(Counter(r.get("blown_impl_status") for r in good)),
                    "in_disputed_band": sum(1 for r in good if r.get("in_disputed_band")),
                    # v1.5（DR-008）：按**全通道**统计，理由同上（带内过滤会漏计带外免罪的臂）
                    "probe_exoneration": dict(Counter(r.get("probe_exoneration") for r in good
                                                      if r.get("probe_exoneration"))),
                    "probe_exoneration_by_kind": dict(Counter(
                        r.get("probe_exoneration_kind") for r in good
                        if r.get("probe_exoneration") == "exonerated")),
                    "exonerated_in_disputed_band": sum(
                        1 for r in good
                        if r.get("in_disputed_band") and r.get("probe_exoneration") == "exonerated"),
                    "cadence_unresolved": sum(1 for r in good if not r.get("cadence_resolved")),
                    "phase_vocab_mismatch_arms": pm,
                    "pending_cosign_reverify": {
                        "n": len(pcr), "arms": pcr,
                        "criterion": ("probe_exoneration == 'exonerated' 且 "
                                      "probe_exoneration_cosign_build_matches is False"
                                      "（三值：True=已复签 / False=待复签 / None=通道不要求会签）"),
                        "ruling_ref": "裁定 25 护栏① / DR-D22；DR-008 决定 7",
                        "cosign_not_required_arms": cna,
                        "zero_condition": ("D 的复签块（gate_build_at_cosign == 门禁现值 GATE_BUILD）"
                                           "已换进 configs/b_probe_exonerations.json")},
                    # D 的验收判据「measurement_valid 47/1」的直接可核形态（原先只能由 citable 反推）
                    "measurement_valid": {
                        "true": sum(1 for r in good if r.get("measurement_valid") is True),
                        "false": sum(1 for r in good if not r.get("measurement_valid")),
                        "false_arms": [r["arm"] for r in good if not r.get("measurement_valid")]},
                    "terminal_semantics_unavailable": {
                        "n": len(tsu), "arms": tsu,
                        "criterion": "field_presence.terminal_kind < episodes_total",
                        "ruling_ref": "裁定 23.4（聚合侧先行；判定侧三值化属 v1.6，DR-010）"},
                    # 裁定 30 / DR-D29：分布层可核化（两套臂集分开给，别混用）
                    "controlled_success_histogram": {
                        "all_arms": hist_all, "n_all_arms": len(good),
                        "measurement_valid_arms": hist_valid,
                        "n_measurement_valid_arms": sum(1 for r in good
                                                        if r.get("measurement_valid")),
                        "key_semantics": "键 = 该臂受控成功局数，值 = 臂数（分母 20 局/臂）",
                        "ruling_ref": "裁定 30 / DR-D29"}},
        # 裁定 30 立的规则，钉在产物里（表头已有 gate_build，两者要一起读）
        "distribution_layer_note": (
            "**计数层构建不变，分布层构建相关**（裁定 30 / DR-D29）：逐局 verdict 计数"
            "（controlled 135 / insuff 235 / flick 7 / over_lift 0 / provisional 0 / raw 377）"
            "在 v1.4→v1.5 实测一格未动；但直方图 / 区间计数 / 极差 / 族均值的 n 是按 "
            "measurement_valid 的**臂集**统计的，免罪或降级会改这个臂集（实测无效臂 v1.2.1 = 7 → v1.5 = 1）。"
            "⇒ **任何分布类陈述一律带构建指纹**（现值 v1.5 / f19f61341cbe，见本文件 gate_build），"
            "并写明臂集（全部 48 / measurement_valid 47 / A 的 21 actlog 子集）。"
            "禁用写法举例：「受控成功落在 4–9 的臂数 = 0」「中间是空的」——"
            "该主张在 v1.2.1 口径下成立、在 v1.5 下被恰好 1 臂证伪（就是 裁定 10 的免罪臂本尊，9/20）；"
            "准确定性是「强间隙分离（gap-separated）」：低簇 0–3 / 高簇 14–20 / 孤立 1 臂 = 9，"
            "空带是 **4–8 与 10–13**，不是「4–9」。"
            "**本表现值（v1.5 / 48 臂，实测）**：4–9 区间 = **3** 臂"
            "（trimdone0_minmax_k2_lr1e-5_s20k_seed0=9【裁定 10 免罪臂】、"
            "train120_trimdone0_minmax_k2_lr1e-5_s20k_seed0=9、trimdone0_minmax_lr1e-5_s20k_seed0_replan1=4），"
            "**全部 48 臂与 measurement_valid 47 臂两套臂集结果相同** —— 因为唯一 INVALID 臂"
            "（…k2_lr1e-5_s20k_seed0_replan1，blown 0.1692）的受控成功是 **0**、不落在 4–9。"
            "A 的 21 actlog 子集是**另一个臂集**，须由 A 侧 join 本表算，B 不代算（裁定 30 的四个限定之一）。"
            "另：引历史口径必须同时报 n_artifacts —— v1.2.1 历史表是 **44** 臂 / 132-208-23-0-1-364，"
            "与 v1.5 的 **48** 臂 / 135-235-7-0-0-377 **不可直接相减比较**"
            "（多出的 4 臂是后来的 blindfix/reblown 重测世代）。"),
        # 裁定 23.2/23.3 尚未落地（属 v1.6 批次）期间的**显式声明**：
        # 覆盖不足的产物上，这个字段是空转的 false，不是「查过没问题」。
        # 缺字段但被当基准必须是**声明过的状态**，不能是意外（裁定 23.5 同源）。
        "known_vacuous_fields_pending_v16": {
            "terminal_semantics.suspect_truncation_labeled_as_failure": {
                "vacuous_when": "field_presence.terminal_kind < episodes_total",
                "current_value_on_vacuous": False,
                "must_not_be_read_as": "清洁保证（「截断没有被伪装成失败」）",
                "affected_arms": tsu,
                "fix_ruling": "裁定 23.2/23.3 → 三值（null=不可判定）+ note 非空 + 回显覆盖率",
                "fix_batch": "v1.6（预登记 DR-010；改门禁脚本 ⇒ GATE_BUILD 会变 ⇒ 需 D 第三轮复签）",
                "interim_aggregate_guard": "summary.terminal_semantics_unavailable"}},
        "insuff_pooled": pooled,
        "n_generation_duplicates_dropped": len(gen_dups),
        "generation_duplicates_dropped": [
            {"arm": dd["arm"], "source": dd.get("source"),
             "blown_impl_status": dd.get("blown_impl_status"),
             "controlled_success": dd["controlled_success"]} for dd in gen_dups],
        "git_commit": gate.GIT_COMMIT,
        "arms": rows,
        "family_rollup": rollup,
        "citation_unit_note": ("可引用单位是「配置族 × 重规划口径」的汇总（均值 + seed 摆幅），"
                               "不是单个臂；实测同族跨 seed 受控成功数摆幅可达 20 局。"
                               "族均值分母只排除 measurement_valid=false 的臂，"
                               "**不排除**「测量有效但受控为 0」的臂（排除会系统性高估）；"
                               "口径不可解析的臂同样不进分母。跨口径禁止直接比较："
                               "(1,1,1) 每局推理次数是 (4,4,4) 的 4 倍，算力不是常量。"
                               "见规格 docs/b_controlled_success_v1_20260928.md §3.1"),
    }, indent=2, ensure_ascii=False) + "\n")
    print("写出:", outp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
