#!/usr/bin/env python
"""档 5 · Harness 接管判定汇编（门与归因分支全部照抄 runs/S5_PREREG.md，不许事后改）。

读数结构（三组，都是反向 TEST seed 7000..7019、K=10、检查点 s2e/022000）：
  正式  runs/s5_takeover_rev_test20_k10{,_rep2,_rep3}   接管打开，3×20 = 60 局
  G0b   runs/s5_g0b_observe_rev_test20_k10{,_rep2,_rep3} 只检测不接管，3×20 = 60 局
  基线  runs/s2e_rev_test_rand20_k10{,_rep2,_rep3}       档 2e 原读数，3×20 = 60 局（同 seed 同窗口）
 pairing key = (rep 序号, seed)。基线与正式读数是**两次独立随机 rollout**（坑 39：flow-matching
 未钉种子），所以「基线本来会成功」是**同初态下的估计**，不是反事实。这条限制在产物里明写，
 并同时报不配对版本（接管局自身的成功率），两个数一起看。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_verdict_s5.py'            # 出 markdown
    bash -c 'source code/env.sh && $MG_PY code/mg_verdict_s5.py --selftest' # 纯 CPU 自测
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
RUNS = MG_ROOT / "runs"
LOGS = MG_ROOT / "logs"
sys.path.insert(0, str(HERE))

# ── 预注册门（出处 runs/S5_PREREG.md 第四节，写盘 2026-10-02 20:33，早于任何档 5 读数）──
GATE_H1 = 0.85          # harness 放宽成功率 ≥85% ⇒ H1 的必要条件之一
GATE_H0 = 0.75          # ≤75% ⇒ H0（接管无效）
GATE_TAKEOVER_MAX = 0.50    # 接管率 ≤50%
GATE_FALSE_TK_MAX = 0.25    # 误接管率 ≤25%
GATE_MS_STEP_MAX = 50.0     # 实时性 ≤50 ms/step（20 Hz 预算），只在 timing_isolated 时判
REMAIN_OK = 250         # 归因分档：剩余 ≥250 步算「预算够」（出处 S5_PREREG 六之一，探针实测）
ATTRIB_RESCUE_MIN = 0.70  # 四之一分支 1：预算够的接管局救回率 ≥70% ⇒ 约束是步数预算不是检测器
BASELINE_DOC = {"strict": (42, 80), "relaxed": (55, 80)}   # 档 2e 80 局基线（runs/S2F_RELAX_VERDICT.md）

TAKEOVER_DIRS = ["s5_takeover_rev_test20_k10", "s5_takeover_rev_test20_k10_rep2",
                 "s5_takeover_rev_test20_k10_rep3"]
OBSERVE_DIRS = ["s5_g0b_observe_rev_test20_k10", "s5_g0b_observe_rev_test20_k10_rep2",
                "s5_g0b_observe_rev_test20_k10_rep3"]
BASE_DIRS = ["s2e_rev_test_rand20_k10", "s2e_rev_test_rand20_k10_rep2", "s2e_rev_test_rand20_k10_rep3"]
BASE_DIRS_ALL = BASE_DIRS + ["s2e_rev_test_rand20_k10_rep4"]


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score 95% 区间（与 mg_verdict_s2f.py 同一实现，p=0/1 不塌成零宽）。"""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1.0 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def fisher_two_sided(a: int, n1: int, b: int, n2: int) -> float:
    """两组二项成功率的双侧 Fisher 精确检验 p 值。**参数是 成功数/试验数**（坑 35）。

    纯 stdlib（math.comb）实现，小样本下是精确值，不给判定工具添 scipy 依赖。
    """
    if n1 <= 0 or n2 <= 0:
        return 1.0
    total = a + b
    lo, hi = max(0, total - n2), min(n1, total)
    xs = list(range(lo, hi + 1))
    weights = [comb(n1, x) * comb(n2, total - x) for x in xs]
    denom = sum(weights)
    if denom == 0:
        return 1.0
    p_obs = weights[a - lo] / denom
    return min(1.0, sum(w / denom for w in weights if w / denom <= p_obs + 1e-12))


def load(d: str) -> dict | None:
    p = RUNS / d / "eval_summary.json"
    if not p.exists():
        return None
    try:
        j = json.loads(p.read_text())
    except Exception as exc:
        return {"_error": f"读不动 {p}: {exc}", "_dir": d}
    j["_dir"] = d
    return j


def cells(dirs: list[str]) -> list[dict]:
    """把若干次读数摊成可配对的 (rep, seed) 单元。缺读数的 rep 直接不进列表（不算 0 分，坑 42）。"""
    out: list[dict] = []
    for rep, d in enumerate(dirs, start=1):
        j = load(d)
        if not j or "_error" in j or "per_episode" not in j:
            continue
        for e in j["per_episode"]:
            out.append({"rep": rep, "seed": int(e["seed"]), "dir": d,
                        "success": bool(e.get("success", False)),
                        "success_relaxed": bool(e.get("success_relaxed", False)),
                        "delivered_tipped": bool(e.get("delivered_tipped", False)),
                        "takeover": bool(e.get("takeover", False)),
                        "trigger": e.get("trigger"),
                        "takeover_step": int(e.get("takeover_step", -1)),
                        "takeover_remain": int(e.get("takeover_remain", -1)),
                        "would_have_fired": e.get("would_have_fired"),
                        "would_have_step": int(e.get("would_have_step", -1)),
                        "steps": int(e.get("steps", -1)),
                        "max_lift_cm": float(e.get("max_lift_cm", 0.0)),
                        "min_dist_cm": float(e.get("min_dist_to_target_xy", 9.9)) * 100.0})
    return out


def rate(k: int, n: int) -> float:
    return (k / n) if n else float("nan")


def verdict_of(succ_rate: float, takeover_rate: float, false_tk_rate: float) -> tuple[str, str]:
    """预注册判定（S5_PREREG 第四节）。返回 (档位, 理由)。"""
    if succ_rate != succ_rate:      # nan：没有读数
        return "无读数", "正式读数为空 ⇒ 不能判"
    if succ_rate <= GATE_H0:
        return "H0 接管无效", (f"放宽成功率 {succ_rate * 100:.1f}% ≤ H0 门 {GATE_H0 * 100:.0f}%。"
                              "处方：先修 resume() 的相位推断（拿专家上界 20 局逐局核对相位轨迹），再谈阈值")
    if succ_rate >= GATE_H1 and takeover_rate <= GATE_TAKEOVER_MAX and false_tk_rate <= GATE_FALSE_TK_MAX:
        return "H1 接管有效", (f"放宽 {succ_rate * 100:.1f}% ≥ {GATE_H1 * 100:.0f}% ∧ "
                              f"接管率 {takeover_rate * 100:.1f}% ≤ {GATE_TAKEOVER_MAX * 100:.0f}% ∧ "
                              f"误接管率 {false_tk_rate * 100:.1f}% ≤ {GATE_FALSE_TK_MAX * 100:.0f}% ⇒ "
                              "监督器能救回残余失败且不是「退化成专家重放」。处方：进档 6")
    why = []
    if succ_rate < GATE_H1:
        why.append(f"成功率 {succ_rate * 100:.1f}% < {GATE_H1 * 100:.0f}%")
    if takeover_rate > GATE_TAKEOVER_MAX:
        why.append(f"接管率 {takeover_rate * 100:.1f}% > {GATE_TAKEOVER_MAX * 100:.0f}%")
    if false_tk_rate > GATE_FALSE_TK_MAX:
        why.append(f"误接管率 {false_tk_rate * 100:.1f}% > {GATE_FALSE_TK_MAX * 100:.0f}%")
    return "部分有效", "；".join(why) + " ⇒ 只报点估计 + Wilson + 对基线的 Fisher，不下强结论"


def paired_stats(base: list[dict], tk: list[dict]) -> dict:
    """按 (rep, seed) 配对：误接管率、救回率、以及四之一的归因分档。"""
    bmap = {(c["rep"], c["seed"]): c for c in base}
    tmap = {(c["rep"], c["seed"]): c for c in tk}
    keys = sorted(set(bmap) & set(tmap))
    base_ok = [k for k in keys if bmap[k]["success_relaxed"]]
    base_bad = [k for k in keys if not bmap[k]["success_relaxed"]]
    false_tk = [k for k in base_ok if tmap[k]["takeover"]]
    fired_bad = [k for k in base_bad if tmap[k]["takeover"]]
    rescued = [k for k in fired_bad if tmap[k]["success_relaxed"]]
    ge = [k for k in fired_bad if tmap[k]["takeover_remain"] >= REMAIN_OK]
    ge_resc = [k for k in ge if tmap[k]["success_relaxed"]]
    lt = [k for k in fired_bad if tmap[k]["takeover_remain"] < REMAIN_OK]
    lt_resc = [k for k in lt if tmap[k]["success_relaxed"]]
    return {"n_paired": len(keys), "base_ok": len(base_ok), "base_bad": len(base_bad),
            "false_tk": len(false_tk), "false_tk_keys": [(k, tmap[k]["trigger"]) for k in false_tk],
            "false_tk_rate": rate(len(false_tk), len(base_ok)),
            "fired_on_fail": len(fired_bad), "rescued": len(rescued),
            "rescue_rate": rate(len(rescued), len(fired_bad)),
            "rescue_ge": (len(ge_resc), len(ge)), "rescue_ge_rate": rate(len(ge_resc), len(ge)),
            "rescue_lt": (len(lt_resc), len(lt)), "rescue_lt_rate": rate(len(lt_resc), len(lt)),
            "tk_success_on_takeover": (sum(1 for k in keys if tmap[k]["takeover"] and tmap[k]["success_relaxed"]),
                                       sum(1 for k in keys if tmap[k]["takeover"]))}


def attribution(ps: dict) -> tuple[str, str]:
    """S5_PREREG 四之一的三条归因分支（读数前写死）。"""
    ge_ok, ge_n = ps["rescue_ge"]
    lt_ok, lt_n = ps["rescue_lt"]
    ge_rate = rate(ge_ok, ge_n)
    false_tk_rate = ps["false_tk_rate"]
    if false_tk_rate == false_tk_rate and false_tk_rate > GATE_FALSE_TK_MAX:
        return ("分支 3", f"误接管率 {false_tk_rate * 100:.1f}% > {GATE_FALSE_TK_MAX * 100:.0f}% ⇒ "
                        "检测器在帮倒忙。处方 = 下一轮提高 N_EMPTY（本轮不改）")
    if ge_n == 0:
        return ("不可判", f"没有任何「剩余 ≥{REMAIN_OK} 步」的接管局 ⇒ 归因分支无法执行")
    if ge_rate >= ATTRIB_RESCUE_MIN:
        return ("分支 1", f"剩余 ≥{REMAIN_OK} 步的接管局救回率 {ge_ok}/{ge_n} = {ge_rate * 100:.1f}% "
                        f"≥ {ATTRIB_RESCUE_MIN * 100:.0f}% ⇒ **约束是步数预算不是检测器**。"
                        f"（剩余 <{REMAIN_OK} 步的 {lt_ok}/{lt_n} = {rate(lt_ok, lt_n) * 100:.1f}%）"
                        "处方 = 让触发更早 / 用档 6 纠正数据把晚期失败消灭在发生前；不许为此调检测器阈值")
    return ("分支 2", f"剩余 ≥{REMAIN_OK} 步的接管局救回率只有 {ge_ok}/{ge_n} = {ge_rate * 100:.1f}% "
                    f"< {ATTRIB_RESCUE_MIN * 100:.0f}% ⇒ resume()/专家在续跑时无能。"
                    "处方 = 按 H0 的处方修相位推断，用 runs/s5_resume_probe* 逐局核对")


def log_pass(path: Path, needle: str) -> tuple[bool, str]:
    if not path.exists():
        return False, f"日志不存在：{path.name}"
    txt = path.read_text(errors="ignore")
    return (needle in txt), (f"{path.name} {'含' if needle in txt else '不含'} {needle!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    tk, ob, base = cells(TAKEOVER_DIRS), cells(OBSERVE_DIRS), cells(BASE_DIRS)
    base_all = cells(BASE_DIRS_ALL)
    print("# 档 5 · Harness 接管判定  (code/mg_verdict_s5.py)")
    print()
    print(f"预注册：`runs/S5_PREREG.md`（写盘 2026-10-02 20:33，回填 20:35，均早于任何档 5 读数）")
    print(f"检查点：`pi05_mix60f120r_s2e/022000`（`readlink last` = 022000，坑 38 已核）")
    print()

    # ── 护栏 ──────────────────────────────────────────────────────────────
    g1, g1s = log_pass(LOGS / "g1_expert_regression.log", "[G1] PASS")
    g0a, g0as = log_pass(LOGS / "s5_g0a.log", "[G0a] PASS")
    print("## 一、护栏")
    print()
    print("| 护栏 | 状态 | 证据 |")
    print("| --- | --- | --- |")
    print(f"| G1 专家动作流回归 | {'✅ PASS' if g1 else '❌ 未过'} | {g1s}（20 局逐比特，严格 14/20 ∧ 放宽 20/20）|")
    print(f"| G0a 外壳确定性等价 | {'✅ PASS' if g0a else '❌ 未过'} | {g0as}"
          "（判据 = G0a-1 CPU 确定性 7 项 ∧ G0a-2 GPU **噪声地板**对照；"
          "**不是**逐比特——GPU 前向本身不可逐比特复现，见 README 坑 44 与 `code/mg_g0a_equiv.py`）|")
    missing = [d for d in TAKEOVER_DIRS + OBSERVE_DIRS + BASE_DIRS if load(d) is None]
    print(f"| 读数齐不齐 | {'✅' if not missing else '⚠️ 缺'} | 缺 {missing if missing else '无'} |")
    print()
    if not (g1 and g0a):
        print("🚫 **护栏未全过 ⇒ 本档读数不可用**，不出判定。")
        return 1

    # ── G0b 观察模式等价性 ────────────────────────────────────────────────
    print("## 二、G0b 观察模式等价性（套上 harness 外壳有没有扰动策略路径）")
    print()
    n_ob = len(ob)
    k_ob = sum(c["success_relaxed"] for c in ob)
    k_ob_s = sum(c["success"] for c in ob)
    n_b = len(base)
    k_b = sum(c["success_relaxed"] for c in base)
    k_b_s = sum(c["success"] for c in base)
    p_ob, p_b = rate(k_ob, n_ob), rate(k_b, n_b)
    sigma = math.sqrt(0.5 * 0.5 / n_ob) if n_ob else float("nan")   # 保守：p=0.5 时 1σ 最大
    dp = p_ob - p_b
    p_f = fisher_two_sided(k_ob, n_ob, k_b, n_b)
    g0b_ok = (abs(dp) <= sigma) and p_f >= 0.05
    print(f"| 组 | n | 严格 | 放宽 | Wilson 95% |")
    print(f"| --- | --- | --- | --- | --- |")
    for lab, kk, kss, nn in (("G0b 观察模式", k_ob, k_ob_s, n_ob), ("档 2e 基线（同 3 个 rep）", k_b, k_b_s, n_b)):
        lo, hi = wilson(kk, nn)
        print(f"| {lab} | {nn} | {kss}/{nn} = {rate(kss, nn) * 100:.1f}% | {kk}/{nn} = {rate(kk, nn) * 100:.1f}% "
              f"| [{lo * 100:.1f}, {hi * 100:.1f}] |")
    print()
    print(f"差 = {dp * 100:+.1f} pp，1σ（p=0.5 保守）= {sigma * 100:.1f} pp，Fisher p = {p_f:.4f}")
    print()
    print(f"**G0b {'✅ PASS' if g0b_ok else '❌ FAIL'}**：{'差在 1σ 内且 Fisher 不显著 ⇒ 外壳没扰动策略路径' if g0b_ok else '外壳扰动了策略路径 ⇒ 正式读数不可归因给检测器，本档作废'}")
    fires = [c for c in ob if c["would_have_fired"]]
    trig_ob: dict[str, int] = {}
    for c in fires:
        trig_ob[str(c["would_have_fired"])] = trig_ob.get(str(c["would_have_fired"]), 0) + 1
    print(f"观察模式本来会触发：{len(fires)}/{n_ob} = {rate(len(fires), n_ob) * 100:.1f}%  计数 {trig_ob}")
    print(f"（标定预测档 2e 臂接管率 36.2%，出处 `runs/_diag/harness_calib.md` 第三节）")
    print()

    # ── 正式读数 ──────────────────────────────────────────────────────────
    n_tk = len(tk)
    k_tk = sum(c["success_relaxed"] for c in tk)
    k_tk_s = sum(c["success"] for c in tk)
    n_tip = sum(c["delivered_tipped"] for c in tk)
    lo, hi = wilson(k_tk, n_tk)
    n_to = sum(c["takeover"] for c in tk)
    trig: dict[str, int] = {}
    for c in tk:
        if c["trigger"]:
            trig[c["trigger"]] = trig.get(c["trigger"], 0) + 1
    ps = paired_stats(base, tk)
    verdict, why = verdict_of(rate(k_tk, n_tk), rate(n_to, n_tk), ps["false_tk_rate"])
    branch, bwhy = attribution(ps)

    print("## 三、正式读数（接管打开，3×20）")
    print()
    print("| 指标 | 值 | 门 | 判定 |")
    print("| --- | --- | --- | --- |")
    print(f"| harness 放宽成功率（主口径） | **{k_tk}/{n_tk} = {rate(k_tk, n_tk) * 100:.1f}%**  Wilson [{lo * 100:.1f}, {hi * 100:.1f}] "
          f"| H1 ≥{GATE_H1 * 100:.0f}% / H0 ≤{GATE_H0 * 100:.0f}% | {'≥H1' if rate(k_tk, n_tk) >= GATE_H1 else ('≤H0' if rate(k_tk, n_tk) <= GATE_H0 else '中间')} |")
    print(f"| harness 严格成功率（并列报） | {k_tk_s}/{n_tk} = {rate(k_tk_s, n_tk) * 100:.1f}% | 不判 | — |")
    print(f"| 其中侧躺标记 delivered_tipped | {n_tip} 局 | 追加标记 | — |")
    print(f"| 接管率 | {n_to}/{n_tk} = {rate(n_to, n_tk) * 100:.1f}%  触发计数 {trig} "
          f"| ≤{GATE_TAKEOVER_MAX * 100:.0f}% | {'✅' if rate(n_to, n_tk) <= GATE_TAKEOVER_MAX else '❌'} |")
    print(f"| 误接管率（配对：基线成功的局里被接管） | {ps['false_tk']}/{ps['base_ok']} = {ps['false_tk_rate'] * 100:.1f}% "
          f"| ≤{GATE_FALSE_TK_MAX * 100:.0f}% | {'✅' if ps['false_tk_rate'] <= GATE_FALSE_TK_MAX else '❌'} |")
    r_ok, r_n = ps["tk_success_on_takeover"]
    print(f"| 救回率（配对：基线失败且被接管） | {ps['rescued']}/{ps['fired_on_fail']} = {ps['rescue_rate'] * 100:.1f}% | 不设门 | — |")
    print(f"| 不配对版：接管局自身成功率 | {r_ok}/{r_n} = {rate(r_ok, r_n) * 100:.1f}% | 不设门 | — |")
    print(f"| 实时性 ms/step | 见第五节 | ≤{GATE_MS_STEP_MAX:.0f} ms | 只在隔离跑时判 |")
    print()
    print(f"配对样本 {ps['n_paired']} 对（基线成功 {ps['base_ok']} / 失败 {ps['base_bad']}）。")
    print(f"⚠️ 配对是**同初态两次独立随机 rollout**（坑 39），不是反事实；不配对版并列在上面。")
    print()
    p_f2 = fisher_two_sided(k_tk, n_tk, k_b, n_b)
    print(f"对基线（同 3 个 rep，放宽 {k_b}/{n_b} = {rate(k_b, n_b) * 100:.1f}%）：Fisher p = {p_f2:.4f}，"
          f"差 {(rate(k_tk, n_tk) - rate(k_b, n_b)) * 100:+.1f} pp")
    k_ba = sum(c["success_relaxed"] for c in base_all)
    print(f"对基线（全 4 个 rep = {len(base_all)} 局，放宽 {k_ba}/{len(base_all)} = "
          f"{rate(k_ba, len(base_all)) * 100:.1f}%）：Fisher p = "
          f"{fisher_two_sided(k_tk, n_tk, k_ba, len(base_all)):.4f}")
    print(f"文档记载的档 2e 80 局基线：严格 {BASELINE_DOC['strict'][0]}/{BASELINE_DOC['strict'][1]}、"
          f"放宽 {BASELINE_DOC['relaxed'][0]}/{BASELINE_DOC['relaxed'][1]}（一致性自检："
          f"{'✅' if (k_ba, len(base_all)) == BASELINE_DOC['relaxed'] else '❌ 与文档不符'}）")
    print()

    # ── 四、判定与归因 ────────────────────────────────────────────────────
    print("## 四、判定与归因（预注册分支）")
    print()
    print(f"### 判定：**{verdict}**")
    print()
    print(why)
    print()
    print(f"### 归因：**{branch}**")
    print()
    print(bwhy)
    print()
    print(f"| 分档 | 救回 | 说明 |")
    print(f"| --- | --- | --- |")
    print(f"| 剩余 ≥{REMAIN_OK} 步 | {ps['rescue_ge'][0]}/{ps['rescue_ge'][1]} = {ps['rescue_ge_rate'] * 100:.1f}% | 预算够 ⇒ 这一档的救回率直接检验「检测器+resume」是否有效 |")
    print(f"| 剩余 <{REMAIN_OK} 步 | {ps['rescue_lt'][0]}/{ps['rescue_lt'][1]} = {ps['rescue_lt_rate'] * 100:.1f}% | 预算不够 ⇒ 救不回来是步数问题（探针实测 T1 需 ~220 步、T3 需 ~190 步 + 10 步落定）|")
    print()
    print(f"预注册预测（S5_PREREG 六之一，读数前写死）：救回 13.0/25 ⇒ 85.0%（误接管全丢则 80.0%）。")
    print(f"实测：救回 {ps['rescued']}/{ps['fired_on_fail']}，成功率 {rate(k_tk, n_tk) * 100:.1f}%。")
    print()

    # ── 五、实时性与纠正片段 ──────────────────────────────────────────────
    print("## 五、实时性与纠正片段（档 6 原料）")
    print()
    ms_all, iso = [], True
    seg_n = seg_steps = 0
    for d in TAKEOVER_DIRS:
        j = load(d)
        if not j:
            continue
        h = j.get("harness", {})
        ms_all.append(h.get("ms_per_step", {}))
        iso = iso and bool(h.get("timing_isolated", False))
        seg_n += int(h.get("n_segments", 0))
        seg_steps += int(h.get("segment_steps", 0))
    pol = [m.get("policy") for m in ms_all if m.get("policy") is not None]
    exp = [m.get("expert") for m in ms_all if m.get("expert") is not None]
    print(f"| 项 | 值 |")
    print(f"| --- | --- |")
    print(f"| 策略 ms/step（各次读数） | {pol} |")
    print(f"| 专家 ms/step（接管段，无推理） | {exp} |")
    print(f"| timing_isolated | {iso} |")
    if iso:
        worst = max(pol + exp) if (pol or exp) else float("nan")
        print(f"| 实时性门 ≤{GATE_MS_STEP_MAX:.0f} ms | {'✅ PASS' if worst <= GATE_MS_STEP_MAX else '❌ FAIL'}（最差 {worst:.1f} ms）|")
    else:
        print(f"| 实时性门 ≤{GATE_MS_STEP_MAX:.0f} ms | ⏸ **本链与档 3r 训练并发 ⇒ 不判**（产物 timing_isolated=false）；"
              "隔离测另跑，命令见 S5_PREREG 第四节 |")
    print(f"| 纠正片段 | {seg_n} 段 / {seg_steps} 步 → `runs/s5_takeover_*/correction_segments_raw.npz` |")
    print()

    # ── 六、不变量与逐局表 ────────────────────────────────────────────────
    bad_inv = [c for c in tk if c["success"] and not c["success_relaxed"]]
    print("## 六、不变量自检")
    print()
    print(f"* 严格 ⊆ 放宽：违背 {len(bad_inv)} 局 {'✅' if not bad_inv else '❌ 判据实现有 bug，本档读数不可用'}")
    print(f"* 接管后专家相位出现在产物里：{sum(1 for c in tk if c['takeover'])} 局接管，"
          f"其中 takeover_step > 0 的 {sum(1 for c in tk if c['takeover'] and c['takeover_step'] > 0)} 局 "
          f"{'✅' if all(c['takeover_step'] > 0 for c in tk if c['takeover']) else '❌'}")
    print(f"* 观察模式不得接管：{sum(1 for c in ob if c['takeover'])} 局 "
          f"{'✅' if not any(c['takeover'] for c in ob) else '❌'}")
    print()
    print("## 七、逐局明细（正式读数）")
    print()
    print("| rep | seed | 放宽 | 严格 | 接管 | 触发 | 触发步 | 剩余 | 基线放宽 | 结局 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    bmap = {(c['rep'], c['seed']): c for c in base}
    for c in tk:
        b = bmap.get((c["rep"], c["seed"]))
        if c["takeover"]:
            out = "救回" if c["success_relaxed"] else "接管后仍失败"
        else:
            out = "策略自成功" if c["success_relaxed"] else "策略自失败(未触发)"
        print(f"| {c['rep']} | {c['seed']} | {'✅' if c['success_relaxed'] else '❌'} "
              f"| {'✅' if c['success'] else '❌'} | {'是' if c['takeover'] else '否'} "
              f"| {c['trigger'] or '-'} | {c['takeover_step']} | {c['takeover_remain']} "
              f"| {'✅' if (b and b['success_relaxed']) else '❌'} | {out} |")
    print()
    print("---")
    print(f"由 code/mg_verdict_s5.py 生成；门与归因分支照抄 runs/S5_PREREG.md（写盘 2026-10-02 20:33/20:35）。")
    return 0


# ────────────────────────────── 自测（纯 CPU，不读 runs/）──────────────────────────────
def _mk(rep, seed, succ_r, succ=False, tk=False, trig=None, step=-1, remain=-1, fired=None):
    return {"rep": rep, "seed": seed, "dir": "x", "success": succ, "success_relaxed": succ_r,
            "delivered_tipped": False, "takeover": tk, "trigger": trig, "takeover_step": step,
            "takeover_remain": remain, "would_have_fired": fired, "would_have_step": step,
            "steps": 400, "max_lift_cm": 10.0, "min_dist_cm": 1.0}


def selftest() -> int:
    n_ok = 0

    def ck(name, cond, detail=""):
        nonlocal n_ok
        if not cond:
            raise AssertionError(f"selftest 失败：{name} {detail}")
        n_ok += 1

    # 1) 判定门的三个边界（85% 恰好过、84.9% 不过、75% 判 H0）
    v, _ = verdict_of(0.85, 0.36, 0.07)
    ck("85.0% + 门内 ⇒ H1", v == "H1 接管有效", v)
    v, _ = verdict_of(50 / 60, 0.36, 0.07)      # 83.3%
    ck("83.3% ⇒ 部分有效", v == "部分有效", v)
    v, _ = verdict_of(0.75, 0.36, 0.07)
    ck("75.0% ⇒ H0（门是 ≤）", v == "H0 接管无效", v)
    v, _ = verdict_of(0.76, 0.36, 0.07)
    ck("76% ⇒ 部分有效", v == "部分有效", v)
    v, _ = verdict_of(0.90, 0.55, 0.07)
    ck("成功率高但接管率超门 ⇒ 部分有效", v == "部分有效", v)
    v, _ = verdict_of(0.90, 0.36, 0.30)
    ck("成功率高但误接管超门 ⇒ 部分有效", v == "部分有效", v)
    v, _ = verdict_of(float("nan"), 0.0, 0.0)
    ck("无读数 ⇒ 不判", v == "无读数", v)
    # 2) 配对统计：误接管率的分母是「基线成功的局」，不是全部局
    base = [_mk(1, 7000, True), _mk(1, 7001, True), _mk(1, 7002, False), _mk(1, 7003, False)]
    tk = [_mk(1, 7000, True, tk=True, trig="T3", step=200, remain=200),      # 误接管且专家做成了
          _mk(1, 7001, False, tk=True, trig="T3", step=250, remain=150),     # 误接管且做坏了
          _mk(1, 7002, True, tk=True, trig="T1", step=80, remain=320),       # 救回
          _mk(1, 7003, False, tk=True, trig="T3", step=300, remain=100)]     # 预算不够，没救回
    ps = paired_stats(base, tk)
    ck("配对数", ps["n_paired"] == 4)
    ck("误接管率 = 2/2（分母是基线成功局）", ps["false_tk"] == 2 and ps["false_tk_rate"] == 1.0, str(ps))
    ck("救回率 = 1/2", ps["rescued"] == 1 and ps["fired_on_fail"] == 2 and ps["rescue_rate"] == 0.5)
    ck("剩余≥250 的救回 1/1", ps["rescue_ge"] == (1, 1) and ps["rescue_ge_rate"] == 1.0)
    ck("剩余<250 的救回 0/1", ps["rescue_lt"] == (0, 1) and ps["rescue_lt_rate"] == 0.0)
    ck("接管局自身成功 2/4", ps["tk_success_on_takeover"] == (2, 4))
    # 3) 归因分支
    b, _ = attribution(ps)
    ck("误接管率超门 ⇒ 分支 3 优先", b == "分支 3", b)
    ps2 = dict(ps, false_tk_rate=0.10)
    b, _ = attribution(ps2)
    ck("预算够的救回率 100% ⇒ 分支 1", b == "分支 1", b)
    ps3 = dict(ps, false_tk_rate=0.10, rescue_ge=(0, 3), rescue_ge_rate=0.0)
    b, _ = attribution(ps3)
    ck("预算够也救不回 ⇒ 分支 2", b == "分支 2", b)
    ps4 = dict(ps, false_tk_rate=0.10, rescue_ge=(0, 0), rescue_ge_rate=float("nan"))
    b, _ = attribution(ps4)
    ck("没有预算够的局 ⇒ 不可判", b == "不可判", b)
    # 4) Fisher 与 Wilson 的基本性质（坑 35：参数是 成功数/试验数）
    ck("同比例 p=1", abs(fisher_two_sided(30, 60, 30, 60) - 1.0) < 1e-9, str(fisher_two_sided(30, 60, 30, 60)))
    ck("极端差异 p 很小", fisher_two_sided(55, 60, 20, 60) < 0.001, str(fisher_two_sided(55, 60, 20, 60)))
    ck("n=0 不炸", fisher_two_sided(0, 0, 1, 2) == 1.0)
    ck("对称", abs(fisher_two_sided(10, 40, 20, 40) - fisher_two_sided(20, 40, 10, 40)) < 1e-12)
    lo, hi = wilson(0, 60)
    ck("Wilson p=0 不塌成零宽", lo == 0.0 and hi > 0.0, f"{lo},{hi}")
    lo, hi = wilson(60, 60)
    ck("Wilson p=1 不塌成零宽", hi > 0.999 and lo < hi, f"{lo},{hi}")
    lo, hi = wilson(51, 60)
    ck("Wilson 85% 的区间含 0.85", lo < 0.85 < hi, f"{lo},{hi}")
    ck("Wilson n=0 给 nan", wilson(0, 0)[0] != wilson(0, 0)[0])
    # 5) rate 的除零
    ck("rate(0,0) = nan", rate(0, 0) != rate(0, 0))
    ck("rate(1,2) = 0.5", rate(1, 2) == 0.5)
    # 6) cells() 不许把缺读数当 0 分（坑 42）：不存在的目录直接跳过
    ck("缺产物不产生单元", cells(["__definitely_not_a_run__"]) == [])
    # 7) 门常数与预注册文档一致（文档改了这里必须跟着改，反之亦然）
    ck("H1 门 = 85%", GATE_H1 == 0.85)
    ck("H0 门 = 75%", GATE_H0 == 0.75)
    ck("接管率门 = 50%", GATE_TAKEOVER_MAX == 0.50)
    ck("误接管率门 = 25%", GATE_FALSE_TK_MAX == 0.25)
    ck("实时性门 = 50 ms", GATE_MS_STEP_MAX == 50.0)
    ck("归因分档 = 250 步", REMAIN_OK == 250)
    ck("正式读数是 3 个目录", len(TAKEOVER_DIRS) == 3)
    ck("基线与读数同窗口（3 个 rep）", len(BASE_DIRS) == len(TAKEOVER_DIRS))
    ck("基线全量是 4 个 rep", len(BASE_DIRS_ALL) == 4)
    print(f"[verdict_s5] selftest 全绿：{n_ok} 项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
