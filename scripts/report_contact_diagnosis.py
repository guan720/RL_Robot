#!/usr/bin/env python
"""接触任务诊断汇总：把 `probe_contact_ceiling.py --task pickplace` 的多个臂打成一张结论表。

为什么要有这一步（而不是直接看四份探针日志）
--------------------------------------------
探针回答的是「这一臂发生了什么」，而决策需要的是「四臂放在一起，瓶颈在**同一段**吗」。
本脚本只做三件事，全部基于产物里已有的实测字段，不重新仿真、不引入新阈值：

  1. **漏斗对齐**：抓 → 搬到篮上方 → 真进篮 → 判成功，四臂逐级并排。
     哪一级先掉到 0，瓶颈就在那一级；这决定了下一步该改奖励、改示范、改采样，
     还是改**评测口径**（四种修法互斥，选错就是白烧一轮预算）。
  2. **可比性核对**：四个臂的 `object_geom`（同一个 can？同一个篮位？）与手写参照臂的
     逐 seed 出生点/成功是否**跨进程逐位相同**。这是接触任务敢做 A/B 的前提 ——
     物体尺寸没钉死之前，跨进程的"冻结评测"评的是不同物体（§12.11-M）。
  3. **与训练侧对账**：把探针口径的成功率和对方 `runs/*/result.json` 里的
     `eval_final.episode_success` 摆在一起。两边不一致时，先查评测口径再谈结论。

用法
----
    /root/venvs/rlrobot/bin/python scripts/report_contact_diagnosis.py \
        runs/infra/diag_pickplace_*.json \
        --out runs/infra/contact_diagnosis_summary.json
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 「够到了」的判据线复用探针的常量，不在这里另立一个（两处阈值不同 = 结论无法互相对照）
from scripts.probe_contact_ceiling import REACH_XY  # noqa: E402

# 漏斗的四级。名字与 probe_contact_ceiling.place_funnel 的字段一一对应。
STAGES = (("held", "真抓住"), ("ever_above_bin", "搬到篮上方"),
          ("ever_in_bin", "真进篮"), ("success", "判成功"))

FIX_HINT = {
    "held": ("接近/抓取段就断了：策略几乎没到过物体旁边。先查学习信号有没有梯度"
             "（稀疏档若 mean_reward≈0，则整轮训练是零信号，不是'学不会'而是'没得学'），"
             "再查动作空间/探索范围；此时改采样分布没有意义"),
    "ever_above_bin": ("抓到了但搬不到篮上方：瓶颈在**搬运段**。放置段的奖励/示范覆盖不足，"
                       "针对性采样应挂在「抓起之后的水平位移」上，而不是出生位置"),
    "ever_in_bin": ("到过篮上方却没落进去：瓶颈在**释放段**（下降高度与松手时机）。"
                    "这一段对手写控制器也不容易（见参照臂的 lift_no_carry / in_bin_no_success）"),
    "success": ("can 真进过篮却没判成功：卡在成功判据的第二半（`r_reach<0.6`，末端要退开 "
                "4.2 cm）⇒ 真实能力被**系统性低估**。先确认策略是否会松手退开，"
                "再决定是判据太严还是释放段没学会；这种状态下开 A/B 比的是噪声"),
    "none": ("四级都有量：该臂已具备非零成功率，可以进 A/B（配合 grasp-verified 口径与"
             "逐题配对门禁）"),
}

# 细分诊断：由**主导失败标签**驱动（标签是探针用环境真值打出来的，见 classify）。
#
# 为什么不用漏斗瓶颈来驱动：漏斗给的是「最深没到哪一级」，也就是**能力天花板**；
# 而该先修哪里，取决于「大多数局死在哪一段」。本轮实测这两者会分叉 ——
# shaped100k 的漏斗瓶颈在"搬到篮上方"（因为只有 3/32 抓到过），但 75% 的局其实死在
# 接近段（no_reach）。照漏斗去修搬运段，等于放着 3/4 的失败不管。
# 所以两个都报：`funnel_bottleneck`=天花板，`sub_diagnosis`=该先修的那一段。
SUB_DIAGNOSIS = {
    "approach_missing": ("末端从没接近物体（min_xy 中位 > 2x REACH_XY = 0.06 m）=> "
                         "**学习信号/探索**问题。先看训练期奖励是否恒 0（零信号时"
                         "「学不会」和「没得学」是两件事）；此时调采样分布、加示范都没用，"
                         "因为策略连物体附近都没去过"),
    "approach_precision": ("末端已经贴近物体（min_xy 中位 <= 0.06 m）却仍判 no_reach => "
                           "**最后几厘米的对准精度**问题，不是探索问题。对症的是抓取段的"
                           "示范/奖励细化、或提高动作分辨率，而不是扩大采样范围"),
    "gripper_channel_unused": ("到了物体旁边却**从没下发闭合指令** => 夹爪通道（OSC_POSE 第 7 维）"
                               "没被学会用。这是最便宜的一种失败：先查动作空间与奖励是否"
                               "让这一维有梯度，再谈更复杂的修法"),
    "grasp_timing": ("下发了闭合却没夹住（`_check_grasp` 真值全程为假）=> **闭合时机 / 对准**"
                     "问题。配合 min_xy 与 max_rise 看：若 min_xy 已 <= 0.03 而 max_rise ~ 0，"
                     "差的是下降深度与闭合时刻，不是水平定位"),
    "lift_missing": ("真抓住了却提不起来 => **力/姿态/提升段**问题（抓持质量不足或提升方向不对）"),
    "carry_missing": ("抓起来且提得动，但搬不到篮上方 => **搬运段**问题。放置段的奖励/示范"
                      "覆盖不足；针对性采样应挂在「抓起之后的水平位移」上，而不是出生位置"),
    "release_missing": ("到过篮上方却没落进篮 => **释放段**问题（下降高度与松手时机）。"
                        "这一段连手写参照臂都在漏（见其 lift_no_carry / in_bin_no_success）"),
    "criterion_retreat": ("can 真进过篮却没判成功 => 卡在成功判据的第二半（`r_reach<0.6`，"
                          "末端要退开 4.2 cm）=> 真实能力被**系统性低估**。先确认策略会不会"
                          "松手退开，再决定是判据太严还是释放段没学会；这种状态下开 A/B 比的是噪声"),
    "ready_for_ab": ("主导标签已经是成功 => 该臂有非零成功率，可以进 A/B"
                     "（配 grasp-verified 口径 + 逐题配对门禁）"),
}

# 主导标签 -> 细分码。no_reach 还要按 min_xy 再分「差得远」和「只差精度」。
LABEL_TO_SUB = {
    "no_reach": "approach",                # 特殊：按 min_xy 中位数二分
    "reach_no_close": "gripper_channel_unused",
    "reach_no_hold": "grasp_timing",
    "grasp_no_lift": "lift_missing",
    "lift_no_carry": "carry_missing",
    "dropped": "carry_missing",            # Lift 口径的「起来过又掉了」也归到抓持/搬运
    "lifted_below": "lift_missing",
    "above_bin_no_drop": "release_missing",
    "in_bin_no_success": "criterion_retreat",
    "success": "ready_for_ab",
    "success_flick": "criterion_retreat",  # 弹一下算成功 => 指标口径问题，不是能力问题
}


def _pct(vals, qs=(10, 25, 50, 75, 90)) -> dict:
    vals = [v for v in vals if v is not None]
    if not vals:
        return {}
    arr = np.asarray(vals, dtype=float)
    return {f"p{q}": round(float(np.percentile(arr, q)), 4) for q in qs}


def sub_diagnosis(rows: list, funnel: dict) -> tuple:
    """返回 `(sub_code, dominant_label, dominant_frac)`：该先修哪一段。

    只看**主导标签**（失败质量最大的那一段）；漏斗瓶颈另报，不当修法依据（见 SUB_DIAGNOSIS 注释）。
    """
    if not rows:
        return "n/a", None, None
    counts = {}
    for r in rows:
        counts[r.get("label")] = counts.get(r.get("label"), 0) + 1
    dom = max(counts, key=lambda k: counts[k])
    frac = round(counts[dom] / len(rows), 3)
    code = LABEL_TO_SUB.get(dom, dom or "n/a")
    if code == "approach":
        mxy = [r.get("min_xy") for r in rows if r.get("min_xy") is not None]
        med = float(np.median(mxy)) if mxy else float("inf")
        code = "approach_missing" if med > 2 * REACH_XY else "approach_precision"
    return code, dom, frac


def _load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _training_side(ckpt: str) -> dict:
    """读对方训练 run 的 result.json（**只读**），把训练侧自报的评测摆进来对账。"""
    if not ckpt:
        return {}
    p = Path(ckpt)
    p = p if p.is_absolute() else REPO_ROOT / p
    rj = p.parent / "result.json"
    if not rj.exists():
        return {"result_json": str(rj), "found": False}
    try:
        d = json.loads(rj.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"result_json": str(rj), "found": False, "error": f"{type(exc).__name__}: {exc}"}
    curve = d.get("curve") or []
    rewards = [c.get("mean_reward") for c in curve if isinstance(c, dict)
               and c.get("mean_reward") is not None]
    succ = [c.get("episode_success") for c in curve if isinstance(c, dict)]
    return {"found": True, "run_dir": p.parent.name, "result_json": str(rj),
            "steps": d.get("steps"), "reward_shaping": d.get("reward_shaping"),
            "demo_steps": d.get("demo_steps"), "bc_steps": d.get("bc_steps"),
            "eval_final": d.get("eval_final"),
            "curve_success_max": max([s for s in succ if s is not None], default=None),
            "curve_reward_range": [round(min(rewards), 3), round(max(rewards), 3)] if rewards else None,
            "train_seconds": d.get("train_seconds"),
            "steps_per_second": d.get("steps_per_second")}


def bottleneck(funnel: dict) -> str:
    """漏斗里第一个掉到 0 的级别 = 瓶颈段。全非零则 'none'（该臂可以进 A/B）。"""
    if not funnel or not funnel.get("applicable"):
        return "n/a"
    for key, _name in STAGES:
        if int(funnel.get(key) or 0) == 0:
            return key
    return "none"


def arm_row(doc: dict, path: Path) -> dict:
    sac = doc.get("sac") or {}
    funnel = sac.get("place_funnel") or {}
    bn = bottleneck(funnel)
    rows = sac.get("episodes") or []
    sub, dom_label, dom_frac = sub_diagnosis(rows, funnel)
    row = {
        "tag": path.stem.replace("diag_pickplace_", "").replace("diag_lift_", ""),
        "artifact": str(path),
        "task": doc.get("task"), "horizon": doc.get("horizon"),
        "episodes": doc.get("episodes"),
        "ckpt": sac.get("ckpt"), "algo": sac.get("algo"),
        "success_rate": sac.get("success_rate"),
        "success_rate_grasp_verified": sac.get("success_rate_grasp_verified"),
        "flick_frac": sac.get("flick_frac"),
        "labels": sac.get("labels"),
        "funnel": {key: funnel.get(key) for key, _ in STAGES} if funnel else None,
        "funnel_frac": ({key: funnel.get(f"{key}_frac") for key, _ in STAGES
                         if funnel.get(f"{key}_frac") is not None} if funnel else None),
        "min_bin_dist_min": funnel.get("min_bin_dist_min") if funnel else None,
        "open_cmd_above_bin_episodes": funnel.get("open_cmd_above_bin_episodes") if funnel else None,
        "blocked_by_reach_seeds": funnel.get("blocked_by_reach_seeds") if funnel else None,
        # 能力天花板：漏斗里第一个掉到 0 的级别（"最深只走到这里"）
        "funnel_bottleneck": bn, "funnel_bottleneck_name": dict(STAGES).get(bn, bn),
        "funnel_hint": FIX_HINT.get(bn, ""),
        # 该先修哪一段：主导失败标签（"大多数局死在这里"）
        "sub_diagnosis": sub, "sub_hint": SUB_DIAGNOSIS.get(sub, ""),
        "dominant_label": dom_label, "dominant_label_frac": dom_frac,
        # 支撑细分的实测分布（全部来自探针的逐局记录，不是新算的指标）
        "min_xy_pct": _pct([r.get("min_xy") for r in rows]),
        "min_xy_frac_within_reach": (round(sum(1 for r in rows
                                               if (r.get("min_xy") or 9) <= REACH_XY)
                                           / max(1, len(rows)), 3) if rows else None),
        "close_cmd_frac_median": (round(float(np.median([r.get("close_cmd_frac") or 0.0
                                                         for r in rows])), 3) if rows else None),
        "max_rise_median": (round(float(np.median([r.get("max_rise") or 0.0
                                                   for r in rows])), 4) if rows else None),
        "reach_xy_threshold": REACH_XY,
        "sec_per_episode": (round(sum(r["wall_sec"] for r in sac.get("episodes") or [])
                                 / max(1, len(sac.get("episodes") or [])), 2)
                            if sac.get("episodes") else None),
        "mean_steps": (round(sum(r["steps"] for r in sac.get("episodes") or [])
                            / max(1, len(sac.get("episodes") or [])), 1)
                       if sac.get("episodes") else None),
        "paired": {k: (doc.get("paired") or {}).get(k)
                   for k in ("n_pairs", "both_success", "scripted_only", "sac_only",
                             "both_fail", "frontier_frac", "too_hard_frac")},
        "dominant_segment": (doc.get("axis_diagnosis") or {}).get("dominant_segment"),
        "dominant_frac": (doc.get("axis_diagnosis") or {}).get("dominant_frac"),
        "axis_verdict": (doc.get("axis_diagnosis") or {}).get("verdict"),
        "training_side": _training_side(sac.get("ckpt") or ""),
    }
    return row


def comparability(docs: list[tuple[Path, dict]]) -> dict:
    """跨 run 可比性：同一个物体/篮位？手写参照臂跨进程逐位相同？出题真的可复现？"""
    out: dict = {"n_artifacts": len(docs)}
    geoms = {}
    for path, doc in docs:
        g = doc.get("object_geom") or {}
        geoms[path.stem] = {k: g.get(k) for k in ("object", "body_mass_kg", "bottom_offset",
                                                  "horizontal_radius", "bin_size", "bin2_pos",
                                                  "target_bin_center", "pinned_object_seed")}
    uniq = {json.dumps(v, sort_keys=True, default=str) for v in geoms.values()}
    out["object_geom"] = geoms
    out["object_geom_identical"] = bool(len(uniq) <= 1)
    out["object_geom_note"] = ("四个臂评的是同一个 can / 同一个篮位 ⇒ 成功率可以互比"
                               if out["object_geom_identical"] else
                               "**物体或篮位不一致 ⇒ 成功率不可互比**，先查 pin_seed")

    seeds_ok = docs and all((doc.get("seeding_check") or {}).get("reproducible")
                            for _, doc in docs)
    legacy = [(path.stem, (doc.get("seeding_legacy_check") or {}).get("reproducible"))
              for path, doc in docs]
    out["seeding_reproducible_all"] = bool(seeds_ok)
    out["seeding_legacy_reproducible"] = legacy
    out["seeding_note"] = (
        "受控 reset 在所有臂上都可复现；而迁移前的写法（只播种 composite.rng）"
        + ("同样可复现 ⇒ 叶子播种在这里不是承重的（值得复查）"
           if all(v for _, v in legacy) else
           "**不可复现** ⇒ 叶子播种是承重的，没有它逐题配对就是在配噪声")
        if seeds_ok else "**有臂的出题不可复现 ⇒ 逐题配对无效，别开 A/B**")

    # 手写参照臂跨进程逐位对照（同一批 seed，四个进程各跑一遍）
    ref = []
    for path, doc in docs:
        rows = (doc.get("scripted") or {}).get("episodes") or []
        ref.append((path.stem, {int(r["seed"]): (r["spawn_xy"], bool(r["success"]),
                                                  int(r["steps"]), r["max_rise"], r["min_xy"],
                                                  r["label"])
                                for r in rows}))
    if len(ref) >= 2:
        base_tag, base = ref[0]
        diffs = []
        for tag, cur in ref[1:]:
            common = sorted(set(base) & set(cur))
            mismatch = [s for s in common if base[s] != cur[s]]
            diffs.append({"vs": tag, "n_common_seeds": len(common),
                          "n_identical": len(common) - len(mismatch),
                          "mismatched_seeds": mismatch[:8]})
        out["scripted_cross_process"] = {
            "reference": base_tag, "comparisons": diffs,
            "all_identical": all(d["n_common_seeds"] and not d["mismatched_seeds"] for d in diffs),
            "note": ("手写参照臂在不同进程里逐 seed 完全一致 ⇒ 钉死物体尺寸 + 按叶子播种之后，"
                     "接触任务的冻结评测**跨进程真的冻结了**（这是 Lift 上花了 300 局才买到的性质）"
                     if all(d["n_common_seeds"] and not d["mismatched_seeds"] for d in diffs)
                     else "**跨进程不一致 ⇒ 还有没钉死的随机源，A/B 结论不可信**"),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsons", nargs="*", help="probe_contact_ceiling.py 的产物（可多个）")
    ap.add_argument("--pattern", default="runs/infra/diag_pickplace_*.json",
                    help="没给位置参数时用的 glob（相对仓库根）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    paths = [Path(p) for p in args.jsons] if args.jsons else \
        [Path(p) for p in sorted(glob.glob(str(REPO_ROOT / args.pattern)))]
    paths = [p if p.is_absolute() else REPO_ROOT / p for p in paths]
    paths = [p for p in paths if p.exists()]
    if not paths:
        print(f"[ERR] 没找到产物（pattern={args.pattern}）", file=sys.stderr)
        return 2
    docs = [(p, _load(p)) for p in paths]

    rows = [arm_row(doc, p) for p, doc in docs]
    ref = (docs[0][1].get("scripted") or {})
    ref_funnel = ref.get("place_funnel") or {}
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "task": docs[0][1].get("task"),
        "n_arms": len(rows),
        "scripted_reference": {
            "success_rate": ref.get("success_rate"),
            "success_rate_grasp_verified": ref.get("success_rate_grasp_verified"),
            "flick_frac": ref.get("flick_frac"),
            "labels": ref.get("labels"),
            "funnel": {k: ref_funnel.get(k) for k, _ in STAGES},
            "mean_wall_sec": ref.get("mean_wall_sec"),
            "note": ("手写参照臂**不是满分** ⇒ 任务顶端本身有难度梯度（与 Lift 的恒 1.000 相反），"
                     "这意味着 pickplace 上存在可测的爬升空间；但也意味着 A/B 的'上限'不是 1.0，"
                     "min_gain 要按 0.72 这个天花板来定，不能照搬 reach 的口径"
                     if (ref.get("success_rate") or 0) < 0.9 else
                     "手写参照臂接近满分 ⇒ 上限侧饱和，可判定性取决于策略侧有没有爬升段"),
        },
        "arms": rows,
        "comparability": comparability(docs),
    }
    bns, subs = {}, {}
    for r in rows:
        bns.setdefault(r["funnel_bottleneck"], []).append(r["tag"])
        subs.setdefault(r["sub_diagnosis"], []).append(r["tag"])
    summary["funnel_bottleneck_groups"] = dict(bns)
    summary["sub_diagnosis_groups"] = dict(subs)
    summary["verdict"] = (
        "该先修的段（按主导标签分组）：" + "；".join(f"{k} -> {v}" for k, v in subs.items())
        + "。能力天花板（按漏斗分组）："
        + "；".join(f"{dict(STAGES).get(k, k)} -> {v}" for k, v in bns.items())
        + "。手写参照臂 "
        f"{summary['scripted_reference']['success_rate']}（非满分 ⇒ 任务本身可诊断）。"
        + ("**没有任何一臂拿到非零成功率 ⇒ 接触 A/B 现在没有可比的臂**，"
           "先按各臂 sub_hint 把主导失败段修出来（能力天花板另看 funnel_hint），"
           "再谈门禁与采样。"
           if all((r["success_rate"] or 0) == 0 for r in rows) else
           "已有非零成功率的臂 ⇒ 可以按 §12.11-P 的 F2/F3 口径开 A/B。"))

    print("=" * 78)
    print(f"接触任务诊断汇总 · task={summary['task']} · {len(rows)} 臂 · "
          f"手写参照 {summary['scripted_reference']['success_rate']}")
    print("=" * 78)
    hdr = (f"{'臂':22s} {'success':>8s} {'grasp':>6s} {'抓':>4s}{'篮上':>5s}{'进篮':>5s}"
           f"{'成功':>5s}  能力天花板 / 该先修哪段")
    print(hdr)
    print("-" * 78)
    for r in rows:
        f = r["funnel"] or {}
        print(f"{r['tag']:22s} {str(r['success_rate']):>8s} "
              f"{str(r['success_rate_grasp_verified']):>6s} "
              f"{str(f.get('held', '-')):>4s}{str(f.get('ever_above_bin', '-')):>5s}"
              f"{str(f.get('ever_in_bin', '-')):>5s}{str(f.get('success', '-')):>5s}  "
              f"天花板={r['funnel_bottleneck_name']} · 主修={r['sub_diagnosis']}")
    print("-" * 78)
    for r in rows:
        ts = r["training_side"]
        print(f"· {r['tag']}: 标签 {r['labels']}")
        print(f"    训练侧对账: {ts.get('run_dir')} steps={ts.get('steps')} "
              f"shaped={ts.get('reward_shaping')} demo={ts.get('demo_steps')} bc={ts.get('bc_steps')} "
              f"eval_final={json.dumps(ts.get('eval_final'), ensure_ascii=False)} "
              f"reward区间={ts.get('curve_reward_range')}")
        print(f"    配对: {json.dumps(r['paired'], ensure_ascii=False)}")
        print(f"    成本: {r['sec_per_episode']} s/局 · 平均 {r['mean_steps']} 步 · "
              f"主导失败段 {r['dominant_segment']}({r['dominant_frac']})")
        print(f"    接近精度: min_xy 分位 {r['min_xy_pct']} · 够到(<= {r['reach_xy_threshold']}) "
              f"比例 {r['min_xy_frac_within_reach']} · 闭合指令占比中位 "
              f"{r['close_cmd_frac_median']} · max_rise 中位 {r['max_rise_median']}")
        print(f"    => 该先修 [{r['sub_diagnosis']}]（主导标签 {r['dominant_label']} 占 "
              f"{r['dominant_label_frac']}）: {r['sub_hint']}")
        if r["funnel_bottleneck"] != "none":
            print(f"    => 能力天花板 [{r['funnel_bottleneck']}]（漏斗最深只到这）: "
                  f"{r['funnel_hint']}")
    c = summary["comparability"]
    print("-" * 78)
    print(f"可比性: 物体/篮位一致={c['object_geom_identical']} · "
          f"出题可复现(全臂)={c['seeding_reproducible_all']} · "
          f"旧写法可复现={c['seeding_legacy_reproducible']}")
    print(f"  {c['object_geom_note']}")
    print(f"  {c['seeding_note']}")
    if "scripted_cross_process" in c:
        xp = c["scripted_cross_process"]
        print(f"  手写参照跨进程: all_identical={xp['all_identical']} · "
              f"{json.dumps(xp['comparisons'], ensure_ascii=False)}")
        print(f"  {xp['note']}")
    print("-" * 78)
    print(f"结论: {summary['verdict']}")

    out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / \
        f"contact_diagnosis_summary_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out = out if out.is_absolute() else REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")
    print(f"已写出: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
