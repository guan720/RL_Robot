#!/usr/bin/env python
"""配对评测产物的离线验收 + 口径重算（不重跑仿真）。

三个用途，都是「量」和「判」分离这条纪律的直接后果：

1. **验收固化**。`probe_paired_lift_eval.py` 的验收清单（跨臂同题 / 确定性地板 /
   物体尺寸钉死 / 恒等式 d−|δ|=2·min(b,c)/n / d>=|δ| / 弹起式成功占比）以前靠人肉
   核对，这里变成脚本：跑一次 ~1 s，哪一项不过就点名哪一项。
2. **统计口径漂移**。探针进程用的是**它启动那一刻**的 `harness/sampling_design.py`。
   本轮刚改过 `required_episodes`（加 `d>=|δ|` 硬约束、`paired_floor_pairs` 数学下界、
   `paired_cheaper_by_n`），所以要用磁盘上的当前实现把保存的逐局数据重算一遍，与产物
   里的数字逐项对照 —— 对不上就说明结论要按新口径重写。
3. **换指标口径重判**。Lift 的 `success` 含「弹起式成功」（§12.11-N）：最弱那条臂
   44% 的成功局其实全程没抓住物体，是指间把 cube 弹过了高度阈值。要写进结论的配对
   判定必须在 `success_grasp`（grasp-verified）口径下再过一遍；两个口径 decision 不同
   时以 grasp-verified 为准，并把差异显式印出来。

统计实现只有一份，在 `harness/sampling_design.py`（mcnemar / paired_gate /
required_episodes / min_detectable_effect）；本脚本只做逐局计数、读数和对照。

用法：
    python scripts/report_paired_workpoint.py runs/infra/paired_lift_d_workpoint.json
    # 成本是机器速度的函数（§12.11-O），换个 sec/episode 做敏感性：
    python scripts/report_paired_workpoint.py <json> --sec-per-episode 25.5
    # 按别的目标效应量买预算（可多次给）：
    python scripts/report_paired_workpoint.py <json> --min-gain 0.10 --min-gain 0.20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy")

from harness.sampling_design import (mcnemar, mde_worst_case,  # noqa: E402
                                     min_detectable_effect, paired_gate, required_episodes)

# 与 frontier_verdict 的 metric 规则同阈值：改这里等于改门禁，别悄悄改
FLICK_MAX = 0.5
GRASP_GAP_WARN = 0.05


def tabulate(rows_a: list[dict], rows_b: list[dict], key: str = "success") -> dict:
    """逐题配对计数。A=现任、B=候选，所以 only_a=只现任成(only_inc)、only_b=只候选成(only_new)。

    只认 `seed` 相同的两行为同一道题；`key` 决定用哪个成功口径
    （`success` = 任务自带判据，`success_grasp` = 真抓起来）。
    """
    by_a = {r["seed"]: bool(r.get(key)) for r in rows_a}
    pairs = [(by_a[r["seed"]], bool(r.get(key))) for r in rows_b if r["seed"] in by_a]
    n = len(pairs)
    both = sum(1 for x, y in pairs if x and y)
    only_a = sum(1 for x, y in pairs if x and not y)
    only_b = sum(1 for x, y in pairs if y and not x)
    if n == 0:
        return {"n": 0, "both": 0, "only_a": 0, "only_b": 0, "neither": 0,
                "p_a": None, "p_b": None, "delta": None, "d": None}
    return {"n": n, "both": both, "only_a": only_a, "only_b": only_b,
            "neither": n - both - only_a - only_b,
            "p_a": round((both + only_a) / n, 4), "p_b": round((both + only_b) / n, 4),
            "delta": round((only_b - only_a) / n, 4), "d": round((only_a + only_b) / n, 4),
            # 未取整的原值：`required_episodes` 的样本量是 ceil(闭式)，吃 4 位小数的
            # δ/d 会与探针里的原值差 1~3 局（实测 91 vs 90、28516 vs 28513），
            # 看起来像"统计口径漂移"，其实只是舍入。算局数一律用原值，展示用取整值。
            "delta_raw": (only_b - only_a) / n, "d_raw": (only_a + only_b) / n,
            "p_a_raw": (both + only_a) / n, "p_b_raw": (both + only_b) / n}


def stat_pair(t: dict, *, alpha: float = 0.05) -> dict:
    """给一组计数配上检验、门禁判定与「检出这么大的差要几局」。"""
    out = dict(t)
    if not t["n"]:
        return out
    p_bar = (t["p_a"] + t["p_b"]) / 2.0
    out["p_bar"] = round(p_bar, 4)
    out["pairing_break_even_d"] = round(2.0 * p_bar * (1.0 - p_bar), 4)
    out["mcnemar"] = mcnemar(t["only_a"], t["only_b"])
    out["paired_gate"] = paired_gate(t["n"], t["only_b"], t["only_a"], alpha=alpha)
    out["mde_at_n"] = round(min_detectable_effect(t["n"], p_bar, alpha=alpha), 4)
    out["mde_worst_case_at_n"] = round(mde_worst_case(t["n"], alpha=alpha), 4)
    # 恒等式：d − |δ| = 2·min(b,c)/n，逐对自校验（防角色接反 / 计数写错）
    excess = round(t["d_raw"] - abs(t["delta_raw"]), 6)
    expect = round(2.0 * min(t["only_a"], t["only_b"]) / t["n"], 6)
    out["identity"] = {"excess_over_floor": excess, "expected_2min_bc_over_n": expect,
                       "identity_ok": bool(abs(excess - expect) < 1e-9)}
    adelta = abs(t["delta_raw"])
    p_bar_raw = (t["p_a_raw"] + t["p_b_raw"]) / 2.0
    out["episodes_needed"] = (required_episodes(adelta, p_bar_raw, discordant=t["d_raw"],
                                                alpha=alpha)
                              if adelta > 0 else {})
    en = out["episodes_needed"]
    unp, pr = en.get("unpaired_per_arm"), en.get("paired_pairs")
    out["episodes_needed"]["saving_factor"] = (round(unp / pr, 2) if unp and pr else None)
    out["d_ge_abs_delta"] = bool(t["d_raw"] >= adelta - 1e-12)
    return out


def arm_summary(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    succ = sum(bool(r.get("success")) for r in rows)
    gv = sum(bool(r.get("success_grasp")) for r in rows)
    flick = sum(1 for r in rows if r.get("success_kind") == "flick")
    return {"n": n, "success_rate": round(succ / n, 4),
            "success_rate_grasp_verified": round(gv / n, 4),
            "flick_frac": round(flick / succ, 4) if succ else 0.0,
            "n_success": succ, "n_grasp_verified": gv, "n_flick": flick,
            "sec_per_episode": round(sum(float(r.get("wall_sec") or 0.0) for r in rows) / n, 2)}


def acceptance_checks(doc: dict, *, flick_max: float = FLICK_MAX,
                      grasp_gap_warn: float = GRASP_GAP_WARN) -> list[dict]:
    """验收清单：每项给 status(ok/warn/fail) + 为什么。任一 fail ⇒ 这份产物不能写进结论。"""
    checks: list[dict] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"check": name, "status": status, "detail": detail})

    aud = doc.get("spawn_audit") or {}
    ok = bool(aud.get("pairing_valid")) and aud.get("identical_frac") == 1.0
    add("跨臂同题(spawn_audit)", "ok" if ok else "fail",
        f"identical_frac={aud.get('identical_frac')} max_abs_diff={aud.get('max_abs_diff')} "
        f"seeds={aud.get('seeds_identical')}/{aud.get('seeds_checked')} ⇒ "
        + ("同 seed 出的是同一道题，配对有效" if ok else "配对无效，d 里混了出题噪声"))

    floor = doc.get("determinism_floor") or {}
    d_floor = floor.get("d_floor")
    add("确定性地板(a vs a2)", "ok" if d_floor == 0 else ("warn" if d_floor else "fail"),
        f"d_floor={d_floor} n={floor.get('n')} ⇒ "
        + ("仿真确定性成立，实测 d 可全部归因于策略差异" if d_floor == 0 else
           "同 ckpt 重跑就有不一致，所有 ckpt 对的 d 都要减掉这个地板"))

    geom = doc.get("object_geom") or {}
    pinned = geom.get("pinned_object_seed")
    add("物体尺寸已钉死", "ok" if pinned else "fail",
        (f"pinned_object_seed={pinned} mass={geom.get('body_mass_kg')} kg "
         f"bottom_offset={geom.get('bottom_offset')}") if pinned else
        "产物没有 pinned_object_seed：robosuite 构造期用未播种的 default_rng 抽 cube 尺寸，"
        "跨进程评的是不同物体（§12.11-M），本份数据只能进程内比较")

    pairs = [p for p in (doc.get("pairs") or []) if p.get("pair_kind") == "ckpt_pair"]
    bad_id = [p["label"] for p in pairs if not (p.get("identity") or {}).get("identity_ok")]
    add("恒等式 d−|δ|=2min(b,c)/n", "ok" if pairs and not bad_id else "fail",
        f"{len(pairs) - len(bad_id)}/{len(pairs)} 对通过" + (f"；异常: {bad_id}" if bad_id else ""))

    arms = doc.get("arms") or {}
    flick_bad, gap_bad = [], []
    for tag, a in arms.items():
        if (a.get("flick_frac") or 0.0) >= flick_max:
            flick_bad.append(f"{tag}={a.get('flick_frac')}")
        gap = (a.get("success_rate") or 0.0) - (a.get("success_rate_grasp_verified") or 0.0)
        if gap >= grasp_gap_warn:
            gap_bad.append(f"{tag}: {a.get('success_rate')} vs gv {a.get('success_rate_grasp_verified')}")
    add("指标可信度(弹起式成功)", "ok" if not flick_bad and not gap_bad else
        ("fail" if flick_bad else "warn"),
        (f"flick_frac>={flick_max}: {flick_bad}" if flick_bad else f"没有臂的 flick_frac 超过 {flick_max}")
        + (f"；success 与 grasp-verified 差>={grasp_gap_warn}: {gap_bad}" if gap_bad else "")
        + " ⇒ 结论一律用 grasp-verified 口径" if (flick_bad or gap_bad) else "")

    if doc.get("partial"):
        cfg_n = (doc.get("config") or {}).get("episodes")
        got = max((a.get("n") or 0) for a in arms.values()) if arms else 0
        add("产物完整性", "warn", f"partial=True：{got}/{cfg_n} 局，数字会随后续 seed 变")
    else:
        add("产物完整性", "ok", "partial=False，正式产物")

    ref = doc.get("reference_replay") or {}
    if ref:
        add("跨进程参照复现", "ok" if ref.get("object_geom_comparable") else "warn",
            ref.get("verdict") or json.dumps(ref, ensure_ascii=False)[:200])
    return checks


def drift_against_stored(doc: dict, recomputed: dict[str, dict]) -> list[dict]:
    """产物里存的配对数字 vs 用当前代码重算的数字，逐项对照。

    为什么要做：探针进程内的那份 `required_episodes` 是它启动时刻的版本。统计口径改过之后，
    产物里的 `episodes_needed` 可能是旧口径 —— 不逐字段对照就会把旧数字抄进文档。
    """
    rows = []
    # 产物字段名 → 重算字段名（探针那边叫 discordant_rate，这边叫 d）
    field_map = {"p_a": "p_a", "p_b": "p_b", "delta": "delta", "discordant_rate": "d"}
    for stored in doc.get("pairs") or []:
        label = stored.get("label")
        fresh = recomputed.get(label)
        if not fresh:
            continue
        diffs = {}
        for k, fk in field_map.items():
            sv, fv = stored.get(k), fresh.get(fk)
            if sv is not None and fv is not None and abs(float(sv) - float(fv)) > 1e-9:
                diffs[k] = {"stored": sv, "recomputed": fv}
        sen, fen = stored.get("episodes_needed") or {}, fresh.get("episodes_needed") or {}
        for k in ("unpaired_per_arm", "paired_pairs", "paired_floor_pairs", "saving_factor"):
            sv, fv = sen.get(k), fen.get(k)
            if (sv is None) != (fv is None) or (sv is not None and fv is not None
                                                and abs(float(sv) - float(fv)) > 1e-9):
                diffs[f"episodes_needed.{k}"] = {"stored": sv, "recomputed": fv}
        sdec = (stored.get("paired_gate") or {}).get("decision")
        fdec = (fresh.get("paired_gate") or {}).get("decision")
        if sdec != fdec:
            diffs["paired_gate.decision"] = {"stored": sdec, "recomputed": fdec}
        rows.append({"label": label, "n_pairs": fresh.get("n"),
                     "identical": not diffs, "diffs": diffs})
    return rows


def budget_translation(pairs: list[dict], *, min_gains: list[float], sec_per_episode: float,
                       eval_episodes: int) -> dict:
    """把实测 d 阶梯翻译成预算：δ 目标 × (最坏 d / 最好 d) × 独立/配对/配对下界。

    成本口径：**一对 = 2 局**，独立两臂 n 局/臂也是 2n 局，所以
    `saving = n_unpaired / n_pairs` 同时就是总成本的节省倍数，不要再乘 2。
    设计按**最坏 d** 买（不按最好情况买），最好 d 只用来展示区间。
    """
    usable = [p for p in pairs if p.get("d") is not None and abs(p.get("delta") or 0.0) > 0]
    out = {"sec_per_episode": round(sec_per_episode, 2),
           "sec_per_episode_note": "成本是机器速度的函数（§12.11-O）：同一台机器上 Lift 一局"
                                   "实测过 25.5 s 与 2.4 s，差 10 倍；小时数必须与这个值一起读",
           "pairs_measured": len(usable), "current_eval_hours_2arms":
               round(2 * eval_episodes * sec_per_episode / 3600.0, 3)}
    if not usable:
        out["text"] = "没有 |δ|>0 的可用配对，无法翻译预算"
        return out
    worst = max(usable, key=lambda p: p["d"])
    best = min(usable, key=lambda p: p["d"])
    rows = {}
    for delta in min_gains:
        per_delta = {}
        for name, pair in (("worst_d", worst), ("best_d", best)):
            p_base = pair["p_bar"]
            need = required_episodes(delta, p_base, discordant=pair["d"])
            n_unp, n_pair = need.get("unpaired_per_arm"), need.get("paired_pairs")
            n_floor = need.get("paired_floor_pairs")
            per_delta[name] = {
                "label": pair.get("label"), "d": pair["d"], "delta_of_that_pair": pair["delta"],
                "target_delta": delta, "p_base": round(p_base, 4),
                "unpaired_per_arm": n_unp, "paired_pairs": n_pair,
                "paired_floor_pairs": n_floor, "paired_at_floor": need.get("paired_at_floor"),
                "paired_cheaper": need.get("paired_cheaper"),
                "paired_cheaper_by_n": need.get("paired_cheaper_by_n"),
                "paired_note": need.get("paired_note") or need.get("paired_reason"),
                "saving_factor": round(n_unp / n_pair, 2) if n_unp and n_pair else None,
                "hours_unpaired": round(2 * n_unp * sec_per_episode / 3600.0, 3) if n_unp else None,
                "hours_paired": round(2 * n_pair * sec_per_episode / 3600.0, 3) if n_pair else None,
                "hours_at_floor": (round(2 * n_floor * sec_per_episode / 3600.0, 3)
                                   if n_floor else None),
            }
        rows[f"delta_{delta:g}"] = per_delta
    out["at_target_delta"] = rows
    w = rows[f"delta_{min_gains[0]:g}"]["worst_d"]
    deltas = sorted(abs(p["delta"]) for p in usable)
    caliber = ("一致" if w["paired_cheaper"] == w["paired_cheaper_by_n"] else
               f"**两个判据打架**：方差判据 d={w['d']:g} vs 2p(1-p)={2 * w['p_base'] * (1 - w['p_base']):.3f} "
               f"说{'省' if w['paired_cheaper'] else '不省'}，按局数说"
               f"{'省' if w['paired_cheaper_by_n'] else '不省'}（做预算按局数）")
    out["text"] = (
        f"实测 d 阶梯 {min(p['d'] for p in usable):.3f}~{max(p['d'] for p in usable):.3f}"
        f"（这些对各自的 |δ| 是 {deltas[0]:.3f}~{deltas[-1]:.3f}，d 全都远高于数学下界 |δ|）。"
        f"按最坏 d 买 δ={min_gains[0]:g}："
        f"独立 {w['unpaired_per_arm']} 局/臂 = {w['hours_unpaired']} h，"
        f"配对 {w['paired_pairs']} 对 = {w['hours_paired']} h"
        + (f"（省 {w['saving_factor']}×）" if w["saving_factor"] else "（配对不可达/不省）")
        + f"；配对数学下界 {w['paired_floor_pairs']} 对 = {w['hours_at_floor']} h。"
        f"现行 {eval_episodes} 局独立评测两臂 = {out['current_eval_hours_2arms']} h。判据：{caliber}。")
    return out


def report(doc: dict, args, *, source: str) -> dict:
    episodes = doc.get("episodes") or {}
    # 自对照臂（role=self_control）只跟第一臂配一对，别把它和其它臂的两两组合也印出来
    self_tag = next((t for t, c in ((doc.get("config") or {}).get("arms") or {}).items()
                     if c.get("role") == "self_control"), None)
    tags = list(episodes)
    main_tags = [t for t in tags if t != self_tag]
    floor_label = next((p.get("label") for p in doc.get("pairs") or []
                        if p.get("pair_kind") == "determinism_floor"), None)
    pair_specs = [(x, y) for i, x in enumerate(main_tags) for y in main_tags[i + 1:]]
    if self_tag and main_tags and (floor_label or self_tag in episodes):
        pair_specs.append((main_tags[0], self_tag))
    cost = doc.get("cost") or {}
    sec_ep = (float(args.sec_per_episode) if args.sec_per_episode is not None
              else float(cost.get("sec_per_episode_mean") or 0.0))
    sec_src = "override(--sec-per-episode)" if args.sec_per_episode is not None else "product(cost.sec_per_episode_mean)"

    # 逐局重算：两个成功口径各一套（success = 任务判据，success_grasp = 真抓起来）
    recomputed: dict[str, dict[str, dict]] = {"success": {}, "success_grasp": {}}
    for key in recomputed:
        for x, y in pair_specs:
            if not episodes.get(x) or not episodes.get(y):
                continue
            is_floor = (y == self_tag)
            label = floor_label if (is_floor and floor_label) else f"{x} vs {y}"
            t = stat_pair(tabulate(episodes[x], episodes[y], key))
            t["pair_kind"] = "determinism_floor" if is_floor else "ckpt_pair"
            recomputed[key][label] = t

    checks = acceptance_checks(doc, flick_max=args.flick_max, grasp_gap_warn=args.grasp_gap_warn)
    arms = {t: arm_summary(episodes[t]) for t in tags if episodes.get(t)}

    # d>=|δ| 硬约束：重算口径下也要成立（这是本轮修的坑 22）
    viol = [f"{k}:{lab}" for k in recomputed for lab, p in recomputed[k].items()
            if p.get("n") and p.get("d_ge_abs_delta") is False]
    if viol:
        checks.append({"check": "d>=|δ| 硬约束", "status": "fail",
                       "detail": f"违反: {viol}（不可能出现，说明计数或角色接反了）"})
    else:
        checks.append({"check": "d>=|δ| 硬约束", "status": "ok",
                       "detail": "所有重算配对都满足 |δ|<=d"})

    drift = drift_against_stored(doc, recomputed["success"])
    if drift:
        n_same = sum(1 for r in drift if r["identical"])
        checks.append({"check": "统计口径漂移", "status": "ok" if n_same == len(drift) else "warn",
                       "detail": f"{n_same}/{len(drift)} 对与产物完全一致"
                                 + ("" if n_same == len(drift) else
                                    f"；有差异: {[r['label'] for r in drift if not r['identical']]}")})

    budget = {k: budget_translation(list(v.values()), min_gains=args.min_gain,
                                    sec_per_episode=sec_ep,
                                    eval_episodes=args.eval_episodes)
              for k, v in recomputed.items()}

    # decision 是否随口径改变（弹起式成功会不会把结论顶上去）
    flips = []
    for label in recomputed["success"]:
        raw = recomputed["success"][label]
        gvv = recomputed["success_grasp"].get(label)
        if not gvv or not raw.get("paired_gate"):
            continue
        d1 = raw["paired_gate"]["decision"]
        d2 = gvv["paired_gate"]["decision"]
        if d1 != d2:
            flips.append({"label": label, "success_verdict": d1, "grasp_verified_verdict": d2,
                          "raw": f"p_a={raw['p_a']} p_b={raw['p_b']} d={raw['d']} "
                                 f"p={raw['mcnemar']['exact_p']:.4f}",
                          "gv": f"p_a={gvv['p_a']} p_b={gvv['p_b']} d={gvv['d']} "
                                f"p={gvv['mcnemar']['exact_p']:.4f}"})

    n_fail = sum(1 for c in checks if c["status"] == "fail")
    return {
        "source": source,
        "generated_at_product": doc.get("generated_at"),
        "partial": bool(doc.get("partial")),
        "n_target": (doc.get("config") or {}).get("episodes"),
        "object_geom": {"pinned_object_seed": (doc.get("object_geom") or {}).get("pinned_object_seed"),
                        "body_mass_kg": (doc.get("object_geom") or {}).get("body_mass_kg"),
                        "size": (doc.get("object_geom") or {}).get("size")},
        "machine": doc.get("machine"),
        "sec_per_episode": round(sec_ep, 2), "sec_per_episode_source": sec_src,
        "checks": checks,
        "overall": "fail" if n_fail else ("warn" if any(c["status"] == "warn" for c in checks) else "ok"),
        "arms": arms,
        "pairs_recomputed": recomputed,
        "drift_vs_stored": drift,
        "verdict_flips_by_metric": flips,
        "budget": budget,
        "params": dict(vars(args)),
    }


def print_report(rep: dict) -> None:
    print("=" * 78)
    print(f"配对工作点验收 · {Path(rep['source']).name}"
          + ("（partial）" if rep["partial"] else "") + f" · 总判定 {rep['overall'].upper()}")
    print("=" * 78)
    print(f"  物体: pinned_seed={rep['object_geom']['pinned_object_seed']} "
          f"mass={rep['object_geom']['body_mass_kg']} kg · "
          f"sec/episode={rep['sec_per_episode']}（{rep['sec_per_episode_source']}）")
    print("\n[验收清单]")
    for c in rep["checks"]:
        mark = {"ok": "PASS", "warn": "WARN", "fail": "FAIL"}[c["status"]]
        print(f"  {mark} {c['check']}: {c['detail']}")
    print("\n[各臂口径]")
    print(f"  {'arm':<5}{'n':>5}{'success':>10}{'grasp_ver':>11}{'flick%':>9}{'sec/ep':>9}")
    for tag, a in rep["arms"].items():
        print(f"  {tag:<5}{a['n']:>5}{a['success_rate']:>10.3f}"
              f"{a['success_rate_grasp_verified']:>11.3f}{100 * a['flick_frac']:>8.1f}%"
              f"{a['sec_per_episode']:>9.2f}")
    for key, title in (("success", "任务判据 success"), ("success_grasp", "grasp-verified")):
        print(f"\n[配对重算 · {title}]")
        for label, p in rep["pairs_recomputed"][key].items():
            if not p.get("n"):
                continue
            en = p.get("episodes_needed") or {}
            print(f"  {label:<16} n={p['n']:<4} p_a={p['p_a']:.3f} p_b={p['p_b']:.3f} "
                  f"δ={p['delta']:+.3f} d={p['d']:.3f}(盈亏平衡 {p['pairing_break_even_d']:.3f}) "
                  f"翻转 {p['only_b']}:{p['only_a']} McNemar p={p['mcnemar']['exact_p']:.4f} "
                  f"⇒ {p['paired_gate']['decision']}")
            if en.get("paired_pairs") or en.get("paired_floor_pairs"):
                print(f"      检出 |δ|={abs(p['delta']):.3f}: 独立 {en.get('unpaired_per_arm')} 局/臂 · "
                      f"配对 {en.get('paired_pairs')} 对（下界 {en.get('paired_floor_pairs')}，"
                      f"省 {en.get('saving_factor')}×）· MDE(n={p['n']})={p.get('mde_at_n')}")
    if rep["verdict_flips_by_metric"]:
        print("\n[口径改变结论 ← 这是必须写进报告的一条]")
        for f in rep["verdict_flips_by_metric"]:
            print(f"  {f['label']}: success ⇒ {f['success_verdict']}，"
                  f"grasp-verified ⇒ {f['grasp_verified_verdict']}")
            print(f"      raw[{f['raw']}]  gv[{f['gv']}]")
    else:
        print("\n[口径改变结论] 无：两个成功口径给出同样的判定")
    drift_bad = [d for d in rep["drift_vs_stored"] if not d["identical"]]
    print("\n[统计口径漂移对照]")
    if not drift_bad:
        print(f"  全部 {len(rep['drift_vs_stored'])} 对与产物存的数字一致（当前代码重算）")
    for d in drift_bad:
        print(f"  {d['label']}: {json.dumps(d['diffs'], ensure_ascii=False)}")
    for key in ("success", "success_grasp"):
        b = rep["budget"][key]
        print(f"\n[预算翻译 · {key}]")
        print(f"  {b.get('text', '')}")
        for dname, per in (b.get("at_target_delta") or {}).items():
            for which, row in per.items():
                print(f"    {dname} {which}: d={row['d']} p_base={row['p_base']} → "
                      f"独立 {row['unpaired_per_arm']} 局/臂={row['hours_unpaired']} h · "
                      f"配对 {row['paired_pairs']} 对={row['hours_paired']} h"
                      f"{'（省 %s×）' % row['saving_factor'] if row['saving_factor'] else ''} · "
                      f"下界 {row['paired_floor_pairs']} 对={row['hours_at_floor']} h")
                if row["paired_cheaper"] != row["paired_cheaper_by_n"]:
                    print(f"        注: 方差判据说{'省' if row['paired_cheaper'] else '不省'}、"
                          f"按局数说{'省' if row['paired_cheaper_by_n'] else '不省'}"
                          f"（盈亏平衡点附近两者本就不同步；做预算按局数）")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsons", nargs="+", help="probe_paired_lift_eval.py 的输出（partial 也可）")
    ap.add_argument("--min-gain", action="append", type=float, default=None,
                    help="要检出的目标效应量 δ，可多次给（默认 0.20）")
    ap.add_argument("--sec-per-episode", type=float, default=None,
                    help="覆盖产物里实测的每局墙钟，做机器速度敏感性（§12.11-O）")
    ap.add_argument("--eval-episodes", type=int, default=120,
                    help="现行独立评测局数，用来算对照基线小时数（§12.11-I 用 120）")
    ap.add_argument("--flick-max", type=float, default=FLICK_MAX)
    ap.add_argument("--grasp-gap-warn", type=float, default=GRASP_GAP_WARN)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if not args.min_gain:
        args.min_gain = [0.20]

    paths = [Path(p) for p in args.jsons]
    paths = [p if p.is_absolute() else REPO_ROOT / p for p in paths]
    reps = {}
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        rep = report(doc, args, source=str(path))
        reps[str(path)] = rep
        print_report(rep)
        print()

    out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / "paired_workpoint_report.json"
    payload = reps if len(reps) > 1 else next(iter(reps.values()))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=float),
                   encoding="utf-8")
    print(f"已写出: {out}")
    worst = max(reps.values(), key=lambda r: {"ok": 0, "warn": 1, "fail": 2}[r["overall"]])
    return 1 if worst["overall"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
