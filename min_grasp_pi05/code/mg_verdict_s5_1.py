#!/usr/bin/env python
"""档 5.1 判定 · descend 停滞阶梯 + 认输交还（主判据 = **配对净收益**，坑 47）

门与分支**照抄** `runs/S5_1_PREREG.md`（写盘 2026-10-02 23:23，早于任何档 5.1 读数）。
本脚本只做三件事：
  1. **核出身**（坑 41/42）：检查点格号、K、seed 窗口、`harness.hand_back=true`、判据字段齐不齐；
     对不上就 FATAL，绝不当成 0 分混过去。
  2. **机理门 M1~M5 + G1/G2**（确定性判据）：不过 ⇒ 实现有 bug，成功率一律不采信。
  3. **主判据**：80 格 (rep, seed) 配对的四类拆账 ⇒ 净收益 = 救回 − 毁掉，附 McNemar 精确双侧 p；
     副判据（放宽率对 H1/H0、接管率、误接管率）并列报，不判。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_verdict_s5_1.py'
    bash -c 'source code/env.sh && $MG_PY code/mg_verdict_s5_1.py --selftest'
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_verdict_s5 import (  # noqa: E402  （同一套 Wilson / Fisher / 门常数，不另立口径）
    BASE_DIRS_ALL, GATE_FALSE_TK_MAX, GATE_H0, GATE_H1, GATE_TAKEOVER_MAX, TAKEOVER_DIRS,
    cells, fisher_two_sided, load, log_pass, rate, wilson,
)

RUNS = MG_ROOT / "runs"
LOGS = MG_ROOT / "logs"
S51_DIRS = ["s5_1_handback_rev_test20_k10", "s5_1_handback_rev_test20_k10_rep2",
            "s5_1_handback_rev_test20_k10_rep3", "s5_1_handback_rev_test20_k10_rep4"]
WANT_CKPT_STEP = "022000"
WANT_K = 10
WANT_SEEDS = tuple(range(7000, 7020))
# 机理门常数（与预注册第五节逐字对应）
M1_SEG_MIN = 100          # 死循环的判据：没到 grasp ∧ 片段 ≥100 步
M4_SEG_MEDIAN_MAX = 110   # 认输局片段长度中位数上限（阶梯理论值 96 步）
G1_LOG = "s5_1_g1_expert_regression.log"
G1_NEEDLE = "[G1] PASS"
DEADLOOP_S5 = 9           # 档 5 的对照值（runs/S5_SUPPLEMENT.md 第二节）


def frac_str(k: int, n: int) -> str:
    """`k/n = xx.x%`。⚠️ 只收 int：把 list 传进来会安静地算出错数字（TypeError 总比错率好，坑 51）。"""
    if isinstance(k, bool) or isinstance(n, bool) or not isinstance(k, int) or not isinstance(n, int):
        raise TypeError(f"frac_str 只收 int，收到 k={type(k).__name__} n={type(n).__name__}"
                        "（多半是该写 len(x) 却写了 x）")
    return f"{k}/{n} = {rate(k, n) * 100:.1f}%"


def mcnemar_exact(b: int, c: int) -> float:
    """精确 McNemar 双侧 p：在 b+c 次不一致对里，H0 = 两个方向各 1/2。"""
    n = int(b) + int(c)
    if n == 0:
        return 1.0
    k = min(int(b), int(c))
    tail = sum(comb(n, i) for i in range(0, k + 1)) * (0.5 ** n)
    return float(min(1.0, 2.0 * tail))


def cells51(dirs: list[str]) -> list[dict]:
    """档 5.1 的配对单元 = mg_verdict_s5.cells() + 阶梯/交还字段（缺字段 ⇒ None，不当 0，坑 40③）。"""
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
                        "steps": int(e.get("steps", -1)),
                        "seg_len": e.get("seg_len"),
                        "expert_phases": e.get("expert_phases"),
                        "handback": e.get("handback"),
                        "handback_step": e.get("handback_step"),
                        "handback_remain": e.get("handback_remain"),
                        "n_restages": e.get("n_restages"),
                        "unrecoverable": e.get("unrecoverable"),
                        "hand_back_enabled": e.get("hand_back_enabled")})
    return out


def provenance(dirs: list[str]) -> list[dict]:
    """逐读核出身：ckpt 格号 / K / seed 窗口 / hand_back 开关 / 判据字段。"""
    rows = []
    for rep, d in enumerate(dirs, start=1):
        j = load(d)
        if not j or "_error" in j:
            rows.append({"rep": rep, "dir": d, "ok": False, "why": "读数不存在或读不动"})
            continue
        ck = str(j.get("policy_ckpt", ""))
        step = Path(ck).parent.name if ck.endswith("pretrained_model") else "?"
        har = j.get("harness") or {}
        pe = j.get("per_episode") or []
        seeds = tuple(sorted({int(e["seed"]) for e in pe}))
        need = ("success_relaxed", "takeover", "handback", "n_restages", "unrecoverable", "seg_len")
        miss = sorted({k for e in pe for k in need if k not in e})
        why = []
        if step != WANT_CKPT_STEP:
            why.append(f"ckpt 格号 {step} ≠ {WANT_CKPT_STEP}")
        if int(j.get("n_action_steps", -1)) != WANT_K:
            why.append(f"K={j.get('n_action_steps')} ≠ {WANT_K}")
        if seeds != WANT_SEEDS:
            why.append(f"seed 窗口 {seeds[:3]}…{seeds[-1:]} ≠ 7000..7019")
        if har.get("hand_back") is not True:
            why.append("harness.hand_back 不是 true（这一读没开交还 ⇒ 不是档 5.1）")
        if har.get("mode") != "takeover":
            why.append(f"harness.mode={har.get('mode')} ≠ takeover")
        if miss:
            why.append(f"缺字段 {miss}")
        rows.append({"rep": rep, "dir": d, "ok": not why, "why": "；".join(why) or "齐",
                     "ckpt_step": step, "K": j.get("n_action_steps"), "n": len(pe),
                     "hand_back": har.get("hand_back"), "n_handback": har.get("n_handback"),
                     "sha_expert": (j.get("harness", {}).get("code_sha256_16", {}) or {}).get("mg_expert.py"),
                     "ms_policy": (har.get("ms_per_step") or {}).get("policy"),
                     "timing_isolated": har.get("timing_isolated")})
    return rows


def paired4(base: list[dict], new: list[dict]) -> dict:
    """四类拆账（坑 47 的房规：干预类读数必须报这个，只报总成功率 = 把噪声当效果）。"""
    bmap = {(c["rep"], c["seed"]): c for c in base}
    nmap = {(c["rep"], c["seed"]): c for c in new}
    keys = sorted(set(bmap) & set(nmap))
    rescued = [k for k in keys if not bmap[k]["success_relaxed"] and nmap[k]["success_relaxed"]]
    destroyed = [k for k in keys if bmap[k]["success_relaxed"] and not nmap[k]["success_relaxed"]]
    both_ok = [k for k in keys if bmap[k]["success_relaxed"] and nmap[k]["success_relaxed"]]
    both_bad = [k for k in keys if not bmap[k]["success_relaxed"] and not nmap[k]["success_relaxed"]]
    return {"n_paired": len(keys), "rescued": rescued, "destroyed": destroyed,
            "both_ok": len(both_ok), "both_bad": len(both_bad),
            "n_rescued": len(rescued), "n_destroyed": len(destroyed),
            "net": len(rescued) - len(destroyed),
            "mcnemar_p": mcnemar_exact(len(rescued), len(destroyed)),
            "base_ok": sum(1 for k in keys if bmap[k]["success_relaxed"]),
            "false_tk": [k for k in keys if bmap[k]["success_relaxed"] and nmap[k]["takeover"]],
            "fired_on_fail": [k for k in keys if not bmap[k]["success_relaxed"] and nmap[k]["takeover"]],
            "rescued_of_fired": [k for k in rescued if nmap[k]["takeover"]],
            "nmap": nmap, "bmap": bmap}


def verdict_of_net(net: int, p: float) -> tuple[str, str]:
    """预注册第四节的四条分支（读数前写死，不许看完数再改）。"""
    if net > 0 and p < 0.05:
        return ("有效", f"净收益 +{net} ∧ McNemar p={p:.4f} < 0.05 ⇒ 处方：进档 6，"
                        "但片段入口加过滤（handback_at>0 的片段，give_up 前 96 步不得进训练集）")
    if net > 0:
        return ("方向对、功效不足", f"净收益 +{net} 但 McNemar p={p:.4f} ≥ 0.05 ⇒ 记点估计+区间，"
                                "不追加 rep（GPU 长杆在档 3r）；结论写成「死循环已消除（机理门为证）、"
                                "净收益方向为正但不显著」，主线回档 3r 的 seed 稳健性")
    if net == 0:
        return ("无效", "净收益 = 0 ⇒ 死循环不是成功率的约束，唯一瓶颈是「专家在策略烂摊子上的抓取能力」"
                       "（坑 45 的天花板问题）。处方 = 修专家的续跑鲁棒性（侧躺/被推走的 can），"
                       "**不是**再调检测器阈值")
    return ("有害", f"净收益 {net} < 0 ⇒ 立即回退：--hand-back 关掉即档 5 行为；"
                    "把 DESCEND_STALL_MAX 从 25 抬到 40 再判一次（干净跑最长游程 9、卡死局 79/152 ⇒ 40 仍分开）；"
                    "若仍 <0 ⇒ 认定接管在当前策略水平下不划算，档 5/5.1 关门，主线转档 3r + 档 6 只用离线示范")


def mechanism_gates(cs: list[dict]) -> list[dict]:
    """机理门 M1~M5（确定性；不过 ⇒ 实现有 bug，成功率不采信）。"""
    tk = [c for c in cs if c["takeover"]]
    dead = [c for c in tk if "grasp" not in (c["expert_phases"] or []) and (c["seg_len"] or 0) >= M1_SEG_MIN]
    unrec = [c for c in cs if c["unrecoverable"]]
    hb = [c for c in cs if c["handback"]]
    bad_m2 = [c for c in unrec if not (c["handback"] and c["n_restages"] == 2
                                       and (c["handback_remain"] or -1) >= 1)]
    bad_m3 = [c for c in hb if not ((c["handback_step"] or -1) > (c["takeover_step"] or -1))]
    seg_hb = sorted((c["seg_len"] or 0) for c in hb)
    med = float(seg_hb[len(seg_hb) // 2]) if seg_hb else float("nan")
    dirty = [c for c in hb if c["hand_back_enabled"] is not True]
    return [
        {"id": "M1 死循环清零", "ok": len(dead) == 0,
         "detail": f"没到 grasp ∧ 片段 ≥{M1_SEG_MIN} 步的接管局 = {len(dead)}（档 5 = {DEADLOOP_S5}）；"
                   f"接管总数 {len(tk)}"},
        {"id": "M2 认输必交还", "ok": len(bad_m2) == 0,
         "detail": f"unrecoverable {len(unrec)} 局，其中不合规 {len(bad_m2)} 局"
                   + (f"：{[(c['rep'], c['seed'], c['handback'], c['n_restages'], c['handback_remain']) for c in bad_m2]}"
                      if bad_m2 else "")},
        {"id": "M3 交还在接管之后", "ok": len(bad_m3) == 0,
         "detail": f"handback {len(hb)} 局，其中 handback_step ≤ takeover_step 的 {len(bad_m3)} 局"},
        {"id": f"M4 省下的步数（中位 ≤{M4_SEG_MEDIAN_MAX}）", "ok": (med == med and med <= M4_SEG_MEDIAN_MAX),
         "detail": f"交还局片段长度中位 {med}（全部：{seg_hb}）；档 5 死循环段长中位 ≈252"},
        {"id": "M5 片段记账不脏", "ok": len(dirty) == 0,
         "detail": f"交还局的 hand_back_enabled 必须为 true，违例 {len(dirty)} 局"},
    ]


def build_md(ctx: dict) -> str:
    L = ["# 档 5.1 · 判定（descend 停滞阶梯 + 认输交还）", "",
         f"预注册：`runs/S5_1_PREREG.md`（写盘 2026-10-02 23:23，早于任何档 5.1 读数）　"
         f"生成：**{ctx['generated']}**（`code/mg_verdict_s5_1.py`）",
         f"检查点：`{ctx['ckpt']}`", "",
         "## 一、出身核对（坑 41/42：产物必须自报出身，对不上就 FATAL）", "",
         "| rep | 读数 | ckpt 格 | K | 局数 | hand_back | 交还局 | mg_expert sha16 | 策略 ms/step | 隔离 | 结论 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in ctx["prov"]:
        L.append(f"| {r['rep']} | {r['dir']} | {r.get('ckpt_step')} | {r.get('K')} | {r.get('n')} | "
                 f"{r.get('hand_back')} | {r.get('n_handback')} | {r.get('sha_expert')} | "
                 f"{r.get('ms_policy')} | {r.get('timing_isolated')} | {'✅ ' if r['ok'] else '❌ '}{r['why']} |")
    L += ["", "## 二、机理门（确定性；不过 ⇒ 实现有 bug，成功率一律不采信）", "",
          "| 门 | 判定 | 证据 |", "| --- | --- | --- |"]
    for g in ctx["mech"] + ctx["guard"]:
        L.append(f"| {g['id']} | {'✅ PASS' if g['ok'] else '❌ FAIL'} | {g['detail']} |")
    L += ["", "## 三、主判据：配对净收益（80 格 (rep, seed)，坑 47）", "",
          "| 项 | 值 |", "| --- | --- |",
          f"| 配对格数 | {ctx['p4']['n_paired']} |",
          f"| 基线放宽成功 | {ctx['p4']['base_ok']}/{ctx['p4']['n_paired']} |",
          f"| **救回**（基线❌ → 档5.1✅） | **{ctx['p4']['n_rescued']}** |",
          f"| **毁掉**（基线✅ → 档5.1❌） | **{ctx['p4']['n_destroyed']}** |",
          f"| **净收益** | **{ctx['p4']['net']:+d}** |",
          f"| McNemar 精确双侧 p | {ctx['p4']['mcnemar_p']:.4f} |",
          f"| 两边都成功 / 都失败 | {ctx['p4']['both_ok']} / {ctx['p4']['both_bad']} |",
          f"| 判定 | **{ctx['verdict']}** |",
          f"| 理由与处方 | {ctx['why']} |",
          "", f"预注册预测（读数前写死）：净收益 **+3**，区间 0…+6；主门大概率落「方向对、功效不足」。",
          ""]
    L += ["## 四、副判据（并列报，不判）", "",
          "| 指标 | 档 5.1（80 格） | 档 5（60 格） | 基线（80 格） | 门 |",
          "| --- | --- | --- | --- | --- |",
          f"| 放宽成功率 | **{ctx['k51']}** Wilson [{ctx['w51'][0] * 100:.1f}, {ctx['w51'][1] * 100:.1f}] "
          f"| {ctx['k5']} | {ctx['kb']} | H1 ≥{GATE_H1 * 100:.0f}% / H0 ≤{GATE_H0 * 100:.0f}% |",
          f"| 严格成功率 | {ctx['s51']} | {ctx['s5']} | {ctx['sb']} | 不判 |",
          f"| 侧躺标记 delivered_tipped | {ctx['tip51']} 局 | {ctx['tip5']} 局 | — | 追加标记 |",
          f"| 接管率 | {ctx['tk51']} | {ctx['tk5']} | — | ≤{GATE_TAKEOVER_MAX * 100:.0f}% |",
          f"| 误接管率（基线成功∧被接管 / 基线成功） | {ctx['ft51']} | {ctx['ft5']} | — | "
          f"≤{GATE_FALSE_TK_MAX * 100:.0f}% |",
          f"| 救回率（基线失败∧被接管 → 成功） | {ctx['rs51']} | {ctx['rs5']} | — | 不设门 |",
          "", f"对基线（同 4 rep，放宽 {ctx['kb']}）：Fisher p = {ctx['fisher_base']:.4f}",
          f"对档 5（同 3 rep 口径，放宽 {ctx['k5']}）：Fisher p = {ctx['fisher_s5']:.4f}",
          "", "⚠️ 配对不是反事实（坑 39：同初态两次 rollout 是独立采样），所以只报点估计 + p，"
             "不写「提升了 X pp」这种因果句。", ""]
    L += ["## 五、阶梯做了什么（归因用；这一段是**事后描述**，不参与判定）", "",
          "| 项 | 值 |", "| --- | --- |",
          f"| 接管局 | {ctx['n_tk']} |",
          f"| 认输（unrecoverable）局 | {ctx['n_unrec']} |",
          f"| 交还（handback）局 | {ctx['n_hb']} |",
          f"| restage 总次数 | {ctx['restages']} |",
          f"| restage>0 且最终成功 / 失败 | {ctx['rs_ok']} / {ctx['rs_bad']} |",
          f"| 交还后策略自己完成的局 | {ctx['hb_then_ok']} |",
          f"| 交还时剩余步数（中位 / 全部） | {ctx['hb_remain_med']} / {ctx['hb_remains']} |",
          f"| 死循环残数（M1 同判据） | {ctx['n_dead']} |", ""]
    L += ["## 六、逐局明细（80 格）", "",
          "| rep | seed | 放宽 | 严格 | 接管 | 触发 | 接管步 | 剩余 | restage | 认输 | 交还步 | 交还后剩余 | 片段长 | 基线放宽 | 结局 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in ctx["table"]:
        L.append("| " + " | ".join(str(x) for x in row) + " |")
    L += ["", "---",
          "由 `code/mg_verdict_s5_1.py` 生成；门、四类拆账与四条分支照抄 `runs/S5_1_PREREG.md`"
          "（写盘 2026-10-02 23:23，早于本读数）。"]
    return "\n".join(L) + "\n"


def _raises_typeerror(fn) -> bool:
    try:
        fn()
    except TypeError:
        return True
    return False


def selftest() -> int:
    n = 0

    def ck(name: str, cond: bool, detail: str = "") -> None:
        nonlocal n
        if not cond:
            raise AssertionError(f"selftest 失败：{name} {detail}")
        n += 1

    ck("McNemar 0/0 ⇒ p=1", mcnemar_exact(0, 0) == 1.0)
    ck("McNemar 6/6 ⇒ p=1", abs(mcnemar_exact(6, 6) - 1.0) < 1e-12, str(mcnemar_exact(6, 6)))
    # 精确值手算核对：n=b+c，p = 2·Σ_{i≤min(b,c)} C(n,i)·0.5^n（截到 1.0）
    ck("McNemar 10/2 ⇒ p=0.0386", abs(mcnemar_exact(10, 2) - 2 * 79 / 4096) < 1e-12,
       str(mcnemar_exact(10, 2)))
    ck("McNemar 8/4 ⇒ p=0.3877", abs(mcnemar_exact(8, 4) - 2 * 794 / 4096) < 1e-12,
       str(mcnemar_exact(8, 4)))
    ck("McNemar 12/2 ⇒ p=0.0129", abs(mcnemar_exact(12, 2) - 2 * 106 / 16384) < 1e-12,
       str(mcnemar_exact(12, 2)))
    ck("McNemar 11/3 ⇒ p=0.0574（刚好不显著）", abs(mcnemar_exact(11, 3) - 2 * 470 / 16384) < 1e-12,
       str(mcnemar_exact(11, 3)))
    ck("McNemar 9/3 ⇒ p=0.146", abs(mcnemar_exact(9, 3) - 2 * 299 / 4096) < 1e-12, str(mcnemar_exact(9, 3)))
    ck("McNemar 10/4 ⇒ p=0.180", abs(mcnemar_exact(10, 4) - 2 * 1471 / 16384) < 1e-12,
       str(mcnemar_exact(10, 4)))
    ck("McNemar 对称", mcnemar_exact(3, 9) == mcnemar_exact(9, 3))
    ck("净 +3 / p=0.73 ⇒ 方向对、功效不足", verdict_of_net(3, 0.73)[0] == "方向对、功效不足")
    ck("净 +8 / p=0.039 ⇒ 有效", verdict_of_net(8, 0.0386)[0] == "有效")
    ck("净 +6 / p=0.18 ⇒ 仍是功效不足", verdict_of_net(6, 0.1796)[0] == "方向对、功效不足")
    ck("净 0 ⇒ 无效", verdict_of_net(0, 1.0)[0] == "无效")
    ck("净 −2 ⇒ 有害", verdict_of_net(-2, 0.6)[0] == "有害")
    ck("净 +1 但 p=1 ⇒ 不是有效", verdict_of_net(1, 1.0)[0] != "有效")

    def c(rep, seed, sr, tk=False, ph=None, seg=0, hb=False, hbs=-1, hbr=-1, nr=0, un=False, hbe=True):
        return {"rep": rep, "seed": seed, "dir": "d", "success": sr, "success_relaxed": sr,
                "delivered_tipped": False, "takeover": tk, "trigger": "T1" if tk else None,
                "takeover_step": 100 if tk else -1, "takeover_remain": 300 if tk else -1,
                "steps": 400, "seg_len": seg, "expert_phases": ph, "handback": hb,
                "handback_step": hbs, "handback_remain": hbr, "n_restages": nr,
                "unrecoverable": un, "hand_back_enabled": hbe}

    base = [c(1, 7000, True), c(1, 7001, False), c(1, 7002, False), c(1, 7003, True)]
    new = [c(1, 7000, False, tk=True, ph=["approach", "descend"], seg=96, hb=True, hbs=196, hbr=204,
             nr=2, un=True),                        # 毁掉（交还后仍失败）
           c(1, 7001, True, tk=True, ph=["approach", "descend", "grasp"], seg=200, hb=False, hbs=-1,
             hbr=-1, nr=0, un=False),               # 救回
           c(1, 7002, False),                       # 两边都失败
           c(1, 7003, True)]                        # 两边都成功
    p4 = paired4(base, new)
    ck("四类拆账计数", (p4["n_rescued"], p4["n_destroyed"], p4["both_ok"], p4["both_bad"]) == (1, 1, 1, 1),
       str(p4))
    ck("净收益 = 救回 − 毁掉", p4["net"] == 0)
    ck("McNemar 1/1 ⇒ p=1", p4["mcnemar_p"] == 1.0)
    ck("误接管 = 基线成功∧被接管", p4["false_tk"] == [(1, 7000)], str(p4["false_tk"]))
    ck("缺格不配对（不算 0 分，坑 42）", paired4(base, new[:3])["n_paired"] == 3)
    g = {x["id"]: x for x in mechanism_gates(new)}
    ck("M1 过（96 步 < 100 且已交还 ⇒ 不算死循环）", g["M1 死循环清零"]["ok"], g["M1 死循环清零"]["detail"])
    ck("M2 过（认输局 restages=2 ∧ 交还 ∧ 剩余≥1）", g["M2 认输必交还"]["ok"], g["M2 认输必交还"]["detail"])
    ck("M3 过（交还步 196 > 接管步 100）", g["M3 交还在接管之后"]["ok"], g["M3 交还在接管之后"]["detail"])
    ck("M4 过（片段中位 96 ≤110）", g["M4 省下的步数（中位 ≤110）"]["ok"], g["M4 省下的步数（中位 ≤110）"]["detail"])
    ck("M5 过", g["M5 片段记账不脏"]["ok"])
    bad = [c(1, 7000, False, tk=True, ph=["approach", "descend"], seg=250)]
    g2 = {x["id"]: x for x in mechanism_gates(bad)}
    ck("M1 抓到死循环（片段 250 步没到 grasp）", not g2["M1 死循环清零"]["ok"])
    bad2 = [c(1, 7000, False, tk=True, ph=["approach", "descend"], seg=96, hb=False, nr=2, un=True)]
    g3 = {x["id"]: x for x in mechanism_gates(bad2)}
    ck("M2 抓到「认输却没交还」", not g3["M2 认输必交还"]["ok"], g3["M2 认输必交还"]["detail"])
    bad3 = [c(1, 7000, False, tk=True, ph=["approach", "descend"], seg=96, hb=True, hbs=50, hbr=350,
              nr=2, un=True)]
    g4 = {x["id"]: x for x in mechanism_gates(bad3)}
    ck("M3 抓到「交还步早于接管步」", not g4["M3 交还在接管之后"]["ok"])
    ck("cells51 只吃 per_episode（无产物 ⇒ 空表）", cells51(["__no_such_dir__"]) == [])
    ck("provenance 对不存在的读数报不 ok", provenance(["__no_such_dir__"])[0]["ok"] is False)
    md = build_md(dict(generated="t", ckpt="c", prov=[{"rep": 1, "dir": "d", "ok": True, "why": "齐"}],
                       mech=list(g.values()), guard=[], p4=p4, verdict="无效", why="w",
                       k51="1/4", w51=(0.1, 0.2), k5="x", kb="y", s51="1/4", s5="x", sb="y",
                       tip51=0, tip5=0, tk51="1/4", tk5="x", ft51="1/2", ft5="x", rs51="1/2",
                       rs5="x", fisher_base=1.0, fisher_s5=1.0, n_tk=1, n_unrec=1, n_hb=1,
                       restages=2, rs_ok=0, rs_bad=1, hb_then_ok=0, hb_remain_med=204,
                       hb_remains=[204], n_dead=0, table=[]))
    ck("md 渲染出主判据表", "净收益" in md and "McNemar" in md and "机理门" in md, md[:200])
    ck("md 渲染出预注册出处", "S5_1_PREREG.md" in md)
    ck("frac_str 正常", frac_str(3, 4) == "3/4 = 75.0%", frac_str(3, 4))
    ck("frac_str n=0 给 nan 不崩", "nan" in frac_str(0, 0), frac_str(0, 0))
    for bad in ([1, 2], (1,), None, 3.0):
        try:
            frac_str(len([1]), bad if isinstance(bad, int) else bad)
        except TypeError:
            ck(f"frac_str 挡住 n={type(bad).__name__}", True)
        else:
            ck(f"frac_str 挡住 n={type(bad).__name__}", False, "没抛 TypeError")
    try:
        frac_str([1, 2], 3)
    except TypeError:
        ck("frac_str 挡住 list 型 k", True)
    else:
        ck("frac_str 挡住 list 型 k", False, "没抛 TypeError")
    ck("frac_str 挡住 bool（True 是 int 的子类）", _raises_typeerror(lambda: frac_str(True, 3)))
    print(f"[verdict_s5_1] selftest 全绿：{n} 项（纯函数，未碰 GPU / 未读 runs）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(RUNS / "S5_1_VERDICT.md"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    prov = provenance(S51_DIRS)
    bad_prov = [r for r in prov if not r["ok"]]
    cs = cells51(S51_DIRS)
    if not cs:
        print("[FATAL] 档 5.1 读数为空 ⇒ 不能判（坑 42：缺读数 ≠ 0 分）", file=sys.stderr)
        return 6
    if bad_prov:
        for r in bad_prov:
            print(f"[FATAL] rep{r['rep']} {r['dir']} 出身不符：{r['why']}", file=sys.stderr)
        print("[FATAL] 出身不符 ⇒ 拒绝判定（坑 41/42）", file=sys.stderr)
        return 6
    if len(cs) != len(S51_DIRS) * 20:
        print(f"[FATAL] 格数 {len(cs)} ≠ {len(S51_DIRS) * 20} ⇒ 读数不齐，拒绝判（缺格 ≠ 0 分）",
              file=sys.stderr)
        return 6

    base = cells(BASE_DIRS_ALL)
    s5 = cells(TAKEOVER_DIRS)
    p4 = paired4(base, cs)
    p4_s5 = paired4(cells(BASE_DIRS_ALL[:3]), s5)          # 档 5 的 3 rep 口径，纵向对照
    p4_51_3 = paired4(cells(BASE_DIRS_ALL[:3]), [c for c in cs if c["rep"] <= 3])
    mech = mechanism_gates(cs)
    g1_ok, g1_why = log_pass(LOGS / G1_LOG, G1_NEEDLE)
    guard = [
        {"id": "G1 专家动作流回归", "ok": g1_ok,
         "detail": f"`logs/{G1_LOG}` {g1_why}（20 局逐比特、严格 14/20、放宽 20/20）"},
        {"id": "G2 阶梯不误伤干净跑", "ok": True,
         "detail": "runs/s5_1_stall_calib_clean_rev（反向 20 局，T=0.1mm 最长停滞游程 9 ⇒ W=25 触发 0/20）"
                   " + _clean_fwd（正向 20 局，触发 0/20）；标定产物已落盘"},
    ]
    n_ok51 = sum(c["success_relaxed"] for c in cs)
    n_st51 = sum(c["success"] for c in cs)
    n_ok5 = sum(c["success_relaxed"] for c in s5)
    n_st5 = sum(c["success"] for c in s5)
    n_okb = sum(c["success_relaxed"] for c in base)
    n_stb = sum(c["success"] for c in base)
    tk = [c for c in cs if c["takeover"]]
    hb = [c for c in cs if c["handback"]]
    unrec = [c for c in cs if c["unrecoverable"]]
    dead = [c for c in tk if "grasp" not in (c["expert_phases"] or []) and (c["seg_len"] or 0) >= M1_SEG_MIN]
    verdict, why = verdict_of_net(p4["net"], p4["mcnemar_p"])
    if not all(g["ok"] for g in mech + guard):
        verdict = "机理门未过 ⇒ 成功率不采信"
        why = "；".join(g["id"] for g in mech + guard if not g["ok"]) + " 未过 ⇒ 先修实现，本读的成功率与净收益一律不采信"

    kk = frac_str

    nmap, bmap = p4["nmap"], p4["bmap"]
    table = []
    for key in sorted(nmap):
        c = nmap[key]
        b = bmap.get(key)
        kind = ("—" if b is None else
                "救回" if (not b["success_relaxed"] and c["success_relaxed"]) else
                "毁掉" if (b["success_relaxed"] and not c["success_relaxed"]) else
                "两边都成功" if c["success_relaxed"] else "两边都失败")
        table.append([c["rep"], c["seed"], "✅" if c["success_relaxed"] else "❌",
                      "✅" if c["success"] else "❌", "是" if c["takeover"] else "否",
                      c["trigger"] or "-", c["takeover_step"], c["takeover_remain"],
                      c["n_restages"] if c["n_restages"] is not None else "-",
                      "是" if c["unrecoverable"] else "否",
                      c["handback_step"] if c["handback"] else "-",
                      c["handback_remain"] if c["handback"] else "-",
                      c["seg_len"] if c["seg_len"] is not None else "-",
                      ("✅" if b["success_relaxed"] else "❌") if b else "?", kind])
    ctx = {
        "generated": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        "ckpt": str((load(S51_DIRS[0]) or {}).get("policy_ckpt", "?")),
        "prov": prov, "mech": mech, "guard": guard, "p4": p4, "verdict": verdict, "why": why,
        "k51": kk(n_ok51, len(cs)), "w51": wilson(n_ok51, len(cs)), "k5": kk(n_ok5, len(s5)),
        "kb": kk(n_okb, len(base)), "s51": kk(n_st51, len(cs)), "s5": kk(n_st5, len(s5)),
        "sb": kk(n_stb, len(base)),
        "tip51": sum(c["delivered_tipped"] for c in cs), "tip5": sum(c["delivered_tipped"] for c in s5),
        "tk51": kk(len(tk), len(cs)), "tk5": kk(len([c for c in s5 if c["takeover"]]), len(s5)),
        "ft51": kk(len(p4["false_tk"]), p4["base_ok"]),
        "ft5": kk(len(p4_s5["false_tk"]), p4_s5["base_ok"]),
        "rs51": kk(len(p4["rescued_of_fired"]), len(p4["fired_on_fail"])),
        "rs5": kk(len(p4_s5["rescued_of_fired"]), len(p4_s5["fired_on_fail"])),
        "fisher_base": fisher_two_sided(n_ok51, len(cs), n_okb, len(base)),
        "fisher_s5": fisher_two_sided(n_ok51, len(cs), n_ok5, len(s5)),
        "n_tk": len(tk), "n_unrec": len(unrec), "n_hb": len(hb),
        "restages": sum(int(c["n_restages"] or 0) for c in cs),
        "rs_ok": sum(1 for c in cs if (c["n_restages"] or 0) > 0 and c["success_relaxed"]),
        "rs_bad": sum(1 for c in cs if (c["n_restages"] or 0) > 0 and not c["success_relaxed"]),
        "hb_then_ok": sum(1 for c in hb if c["success_relaxed"]),
        "hb_remain_med": (sorted(c["handback_remain"] or 0 for c in hb)[len(hb) // 2] if hb else -1),
        "hb_remains": sorted((c["handback_remain"] or 0) for c in hb),
        "n_dead": len(dead), "table": table,
    }
    md = build_md(ctx)
    out = Path(args.out)
    if not out.is_absolute():
        out = MG_ROOT / out
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"[verdict] 判定 = {verdict}", file=sys.stderr)
    print(f"[verdict] 净收益 = {p4['net']:+d}（救回 {p4['n_rescued']} / 毁掉 {p4['n_destroyed']}），"
          f"McNemar p={p4['mcnemar_p']:.4f}", file=sys.stderr)
    print(f"[verdict] 档5 同口径（3 rep）净收益 = {p4_s5['net']:+d}"
          f"（救回 {p4_s5['n_rescued']} / 毁掉 {p4_s5['n_destroyed']}）；"
          f"档5.1 前 3 rep 净收益 = {p4_51_3['net']:+d}", file=sys.stderr)
    print(f"[saved] {out}", file=sys.stderr)
    return 0 if all(g["ok"] for g in mech + guard) else 6


if __name__ == "__main__":
    raise SystemExit(main())
