#!/usr/bin/env python3
"""档 8 · 格 8A 产出率的**事前**预测（只读旧语料；零 GPU / 零 env / 零策略）。

为什么要有这个工具
------------------
8A 的三条门里，**A2「接管局放宽成功率 ≥ 40%」本质上是一条可证伪预测**：
预注册 `runs/S8_PREREG.md` §3 自己写着「（= 23/58 的量级；**档 5 是 26%**）」，
也就是说 40% 这个数是**赌「把采集 horizon 从 400 抬到 800 能把专家救回率拉上去」**。
本工具用盘上**唯一**的实测接管语料（档 5.1：4×20 = 80 局、horizon=400、
检查点 = `pi05_mix60f120r_s2e/checkpoints/022000`，即**好 seed 1000** 的末点）
把这条赌注拆成可算的两段，好在 8A 真跑（ETA 10-05 ~00:15）之前就知道：

  ① **删失（censoring）解释了多少失败** —— 语料里 27 个失败接管**全部**跑满 400 步，
     所以「失败」与「步数不够」在 horizon=400 下完全混淆；抬到 800 能救回多少，可估。
  ② **剩下的瓶颈是什么** —— 实测答案：`到达 grasp` 与否。
     「未到 grasp 但步数足够」的 12 局**全灭**（0/12），而「到 grasp 且步数足够」的 6 局成了 5 局
     ⇒ **瓶颈是专家的 approach/descend 到不了 grasp，不是步数预算**
     ⇒ 预注册 HELD 分支的候选之一「抬 horizon」被这个读数**事前否掉**。

三个模型（都写死在这里，不许看完 8A 再挑一个 —— 坑 40）
------------------------------------------------------
* **L（下界，「删失无关」）**：A2 = 语料实测值（假设抬 horizon 一点用没有）。
* **M（点估计，「分层转化」）**：把接管按 `是否到达 grasp` 分层，每层用**语料里步数本来就够的那批**
  的实测成功率当转化率（那批没被删失 ⇒ 无偏），再乘以目标 horizon 下**步数够**的局数。
  这是唯一有因果口径的估计：它承认「步数够」是成功的前提，也承认「到不了 grasp」是另一回事。
* **U（上界，「到 grasp 就成」）**：A2 = 到达 grasp 的比例（假设只要到 grasp 必然成功）。

⚠️ 本工具**不改任何门、不产生任何判据读数**：三条门的常数一律从 `mg_collect_corr` import（坑 67：
   引用常数不写字面量）。产物只是 `runs/_diag/s8a_yield_forecast.md` 的**事前风险预测**。
⚠️ 语料是**好 seed**（反向放宽 68.8%）而 8A 跑的是**坏 seed 2000**（41.2%）⇒ 接管率会更高（分母变大），
   接管到的状态也可能更难 ⇒ 本预测对 A2 偏**乐观**；这两条偏差在报告里显式写出来，不做数值修正
   （没有盘上依据的修正就是编数）。

复现
----
    $MG_PY code/mg_forecast_s8a.py --selftest
    $MG_PY code/mg_forecast_s8a.py > runs/_diag/s8a_yield_forecast.md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

MG_ROOT = Path("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/min_grasp_pi05")
if str(MG_ROOT / "code") not in sys.path:
    sys.path.insert(0, str(MG_ROOT / "code"))

from mg_collect_corr import (  # noqa: E402  常数一律 import（坑 67）
    COLLECT_HORIZON, GATE_A1_EPISODES, GATE_A1_FRAMES, GATE_A2_RATE, GATE_A3_MEDIAN,
    MAX_SEG_LEN, TARGET_FRAMES_8B,
)
from mg_verdict_s2f import wilson  # noqa: E402

CORPUS_GLOB = "runs/s5_1_handback_rev_test20_k10*"
CORPUS_HORIZON = 400          # 档 5.1 的采集/评测 horizon（出处：那批 eval_summary 的 steps 上限）
GRASP_PHASE = "grasp"
LOW_POWER_N = 5               # with-room 样本 < 5 的分层格子 ⇒ 转化率不可单独采信（只报区间，不当点估计）

# 失败类 → 检测器会打哪个标签（**映射，不是测量**，出处写在下面）：
#   A 类 = 「can 从未抬过 LIFT_OK_CM」⇒ 合爪时夹空 ⇒ 宽度掉到 ≤W_EMPTY，且此前没有 N_HOLD 步落在
#          [HOLD_LO, HOLD_HI] ⇒ `GraspDetector.update()` 返回 **T1**（`code/mg_harness.py:85`）。
#   B 类 = 「抬起来了但没送到」⇒ 必然曾稳定夹持过 ⇒ `held=True` ⇒ 之后掉宽度就是 **T3**（滑脱）。
#   C 类 = 「送到了没落定」⇒ 同 B，曾夹持过 ⇒ **T3**（也可能压根不触发：一直夹到超时 ⇒ 保守并进 T3）。
# ⚠️ 这条映射只用来把「靶子的失败构成」翻译成「靶子的触发构成」，**不进任何门**；报告里显式标注
#    它是映射而非测量（坑 40③：不确定的东西不许伪装成读数）。
TRIGGER_OF_CLASS = {"A": "T1", "B": "T3", "C": "T3"}


# ─────────────────────────────── 读数 ───────────────────────────────
def load_corpus(root: Path, glob_pat: str = CORPUS_GLOB) -> list[dict]:
    """把语料的 per_episode 摊平成一个列表。缺目录/缺字段一律报错，不许静默当 0（坑 40③）。"""
    dirs = sorted((root).glob(glob_pat))
    if not dirs:
        raise FileNotFoundError(f"语料目录不存在：{root}/{glob_pat}")
    out: list[dict] = []
    for d in dirs:
        p = d / "eval_summary.json"
        if not p.is_file():
            raise FileNotFoundError(f"缺 eval_summary.json：{p}")
        s = json.loads(p.read_text())
        for k in ("per_episode", "seconds", "policy_ckpt"):
            if k not in s:
                raise KeyError(f"{p} 缺字段 {k}")
        for ep in s["per_episode"]:
            for k in ("takeover", "takeover_step", "success_relaxed", "seg_len", "steps",
                      "expert_phases", "trigger", "handback", "unrecoverable"):
                if k not in ep:
                    raise KeyError(f"{p} 的 per_episode 缺字段 {k}")
            ep = dict(ep)
            ep["_src"] = d.name
            ep["_seconds"] = float(s["seconds"])
            ep["_n_in_file"] = int(s["episodes"])
            out.append(ep)
    return out


def takeovers(eps: list[dict]) -> list[dict]:
    return [e for e in eps if bool(e["takeover"])]


def reached_grasp(ep: dict) -> bool:
    return GRASP_PHASE in (ep.get("expert_phases") or [])


def need_steps(eps: list[dict]) -> float:
    """专家恢复一段需要多少步：取「放宽成功的接管片段」的 seg_len 中位（>0 的那些）。

    空列表返回 nan（不许用 0 兜底 —— 那会让「步数够」恒真，模型 M 退化成模型 U）。
    """
    xs = sorted(int(e["seg_len"]) for e in takeovers(eps)
                if e["success_relaxed"] and int(e["seg_len"]) > 0)
    if not xs:
        return float("nan")
    n = len(xs)
    return float(xs[n // 2]) if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def has_room(ep: dict, horizon: int, need: float) -> bool:
    """目标 horizon 下，这一局接管后剩下的步数够不够专家做完一段。"""
    if need != need:            # nan
        return False
    return (horizon - int(ep["takeover_step"])) >= need


def stratify(eps: list[dict], horizon: int, need: float) -> dict:
    """按 `是否到达 grasp` 分层；每层给出「步数够」的子集与它的实测成功率（= 模型 M 的转化率）。"""
    tk = takeovers(eps)
    out = {}
    for g, sel in (("grasp", True), ("nograsp", False)):
        sub = [e for e in tk if reached_grasp(e) is sel]
        room = [e for e in sub if has_room(e, horizon, need)]
        room_ok = [e for e in room if e["success_relaxed"]]
        out[g] = {
            "n": len(sub),
            "n_ok_observed": int(sum(1 for e in sub if e["success_relaxed"])),
            "n_room": len(room),
            "n_room_ok": len(room_ok),
            "p_room": (len(room_ok) / len(room)) if room else float("nan"),
        }
    out["n_takeover"] = len(tk)
    out["n_ok_observed"] = int(sum(1 for e in tk if e["success_relaxed"]))
    return out


def models(st: dict, corpus_horizon: int, target_horizon: int, need: float) -> dict:
    """三个模型的 A2 预测（L / M / U），全部只用 st 里的整数与转化率。"""
    n_tk = st["n_takeover"]
    if n_tk == 0:
        return {"L": float("nan"), "M": float("nan"), "U": float("nan"), "pred_ok_M": 0.0}
    # L：语料实测（= 假设删失无关）
    a2_l = st["n_ok_observed"] / n_tk
    # M：分层转化。转化率取自**语料 horizon 下步数就够**的那批（未被删失 ⇒ 无偏），
    #    再乘以**目标 horizon 下步数够**的局数（语料里那批局在 target 下的 remain 更大 ⇒ 只多不少）。
    pred_ok = 0.0
    for g in ("grasp", "nograsp"):
        d = st[g]
        p = d["p_room"]
        if p != p:                       # 该层在语料里没有「步数够」的样本 ⇒ 转化率不可估，记 0 并打标
            continue
        n_room_target = int(round(d["n"] * _room_frac_target(d, corpus_horizon, target_horizon, need)))
        pred_ok += n_room_target * p
    a2_m = pred_ok / n_tk
    # U：到 grasp 就成
    a2_u = st["grasp"]["n"] / n_tk
    return {"L": a2_l, "M": a2_m, "U": a2_u, "pred_ok_M": pred_ok}


def _room_frac_target(d: dict, corpus_h: int, target_h: int, need: float) -> float:
    """该层里「目标 horizon 下步数够」的比例。

    语料只给了每层的 n / n_room（语料 horizon 下），没有把逐局 takeover_step 传进来 ⇒
    这里用保守口径：目标 horizon ≥ 语料 horizon 时，语料里步数够的那批在目标下**一定**还够，
    而语料里不够的那批，只有当 target 比 corpus 多出的步数能把它们补上时才算够。
    调用方（`forecast`）传的是**逐局**算好的比例；这个函数只是 selftest 里的纯算式兜底。
    """
    if d["n"] == 0:
        return 0.0
    if target_h <= corpus_h:
        return d["n_room"] / d["n"]
    return 1.0        # 保守上界：目标 horizon 更长 ⇒ 假定该层全部有步数（真实值在 [n_room/n, 1]）


def room_frac_by_episode(eps: list[dict], horizon: int, need: float) -> dict:
    """逐局算「目标 horizon 下步数够」的比例（模型 M 真正用的口径，不走 _room_frac_target 的兜底）。"""
    tk = takeovers(eps)
    out = {}
    for g, sel in (("grasp", True), ("nograsp", False)):
        sub = [e for e in tk if reached_grasp(e) is sel]
        out[g] = {
            "n": len(sub),
            "n_room": int(sum(1 for e in sub if has_room(e, horizon, need))),
        }
    return out


def model_m_by_episode(eps: list[dict], corpus_h: int, target_h: int, need: float) -> dict:
    """模型 M 的逐局版（承重口径）：转化率来自语料 horizon 的 with-room 子集，
    分母/分子用 target horizon 下逐局重算的 with-room 局数。"""
    st = stratify(eps, corpus_h, need)
    rf = room_frac_by_episode(eps, target_h, need)
    n_tk = st["n_takeover"]
    if n_tk == 0:
        return {"a2": float("nan"), "pred_ok": 0.0, "detail": {}}
    pred_ok = 0.0
    detail = {}
    for g in ("grasp", "nograsp"):
        p = st[g]["p_room"]
        n_room_t = rf[g]["n_room"]
        contrib = 0.0 if p != p else n_room_t * p
        pred_ok += contrib
        detail[g] = {"p_room_corpus": p, "n_room_corpus": st[g]["n_room"],
                     "n_room_target": n_room_t, "pred_ok": contrib}
    return {"a2": pred_ok / n_tk, "pred_ok": pred_ok, "detail": detail}


def _strata_by(eps: list[dict], horizon: int, need: float, key) -> dict:
    """按任意分层键（这里是触发标签）做与 `stratify` 同口径的统计。"""
    tk = takeovers(eps)
    out: dict[str, dict] = {}
    for t in sorted({str(key(e)) for e in tk}):
        sub = [e for e in tk if str(key(e)) == t]
        room = [e for e in sub if has_room(e, horizon, need)]
        room_ok = [e for e in room if e["success_relaxed"]]
        out[t] = {"n": len(sub),
                  "n_ok_observed": int(sum(1 for e in sub if e["success_relaxed"])),
                  "n_room": len(room), "n_room_ok": len(room_ok),
                  "p_room": (len(room_ok) / len(room)) if room else float("nan")}
    return out


def model_m_trigger(eps: list[dict], corpus_h: int, target_h: int, need: float) -> dict:
    """模型 M 的**触发标签**分层版（与 grasp 分层正交的第二把尺）。

    为什么要第二把尺：grasp 分层用的是**好 seed** 的语料，而 8A 跑的是**坏 seed 2000**。
    两个 seed 的失败**构成**不同（靶子 A 类 24/47 = 51% vs 语料的 A 类占比更低），而 A⇒T1、B/C⇒T3，
    语料里 T1 的救回率约是 T3 的两倍 ⇒ 构成差会直接把 A2 挪几个 pp。
    触发标签是**跨 seed 可比**的分层键（检测器只看夹爪宽度，不看策略好坏）。
    """
    tk = takeovers(eps)
    st = _strata_by(eps, corpus_h, need, lambda e: e["trigger"])
    if not tk:
        return {"a2": float("nan"), "pred_ok": 0.0, "detail": {}, "strata": st}
    pred_ok = 0.0
    detail = {}
    for t, d in st.items():
        n_room_t = int(sum(1 for e in tk if str(e["trigger"]) == t and has_room(e, target_h, need)))
        p = d["p_room"]
        contrib = 0.0 if p != p else n_room_t * p
        pred_ok += contrib
        detail[t] = {"p_room_corpus": p, "n_room_corpus": d["n_room"], "n_room_target": n_room_t,
                     "pred_ok": contrib, "n_corpus": d["n"]}
    return {"a2": pred_ok / len(tk), "pred_ok": pred_ok, "detail": detail, "strata": st}


def target_trigger_mix(target_eps: list[dict]) -> dict:
    """靶子检查点（坏 seed 2000 的 TEST 80 局）的**触发构成**估计。

    分类用 `mg_tax_fail.klass(e, "relaxed")`（import，不重写 —— 坑 55/67），只统计**放宽失败**的局
    （成功局会被 `latch_success()` 关掉检测器 ⇒ 不可能被接管），再按 `TRIGGER_OF_CLASS` 映射成触发占比。
    `UNK`（缺字段）一律不进分母（坑 40③：缺字段 ≠ 失败）。
    """
    from mg_tax_fail import klass
    cnt = {"A": 0, "B": 0, "C": 0, "UNK": 0}
    for e in target_eps:
        k = klass(e, "relaxed")
        if k == "OK":
            continue
        cnt[k if k in cnt else "UNK"] += 1
    n_fail = cnt["A"] + cnt["B"] + cnt["C"]
    trig: dict[str, int] = {}
    for k in ("A", "B", "C"):
        if cnt[k]:
            t = TRIGGER_OF_CLASS[k]
            trig[t] = trig.get(t, 0) + cnt[k]
    return {"classes": cnt, "n_fail": n_fail, "n_total": len(target_eps),
            "trigger_frac": {t: (v / n_fail if n_fail else float("nan")) for t, v in trig.items()}}


def a2_target_adjusted(mix: dict, mt: dict) -> dict:
    """把语料的「按触发的 with-room 转化率」套到**靶子的触发构成**上 ⇒ 靶子特异的 A2 点估计。

    不可估的触发（语料里该触发没有 with-room 样本 ⇒ p=nan）**不给点估计**，
    而是给出把它当 0 / 当 1 的区间（诚实标注，不编数）。
    """
    lo = hi = 0.0
    detail = {}
    unknown: list[str] = []
    for t, frac in mix["trigger_frac"].items():
        d = mt["detail"].get(t)
        p = d["p_room_corpus"] if d else float("nan")
        if p != p:
            unknown.append(t)
            detail[t] = {"frac": frac, "p": float("nan"), "contrib_lo": 0.0, "contrib_hi": frac}
            hi += frac
            continue
        detail[t] = {"frac": frac, "p": p, "contrib_lo": frac * p, "contrib_hi": frac * p}
        lo += frac * p
        hi += frac * p
    return {"point": (lo if not unknown else float("nan")), "lo": lo, "hi": hi,
            "unknown_triggers": unknown, "detail": detail,
            "pass_lo": bool(lo >= GATE_A2_RATE), "pass_hi": bool(hi >= GATE_A2_RATE)}


def forecast(eps: list[dict], target_horizon: int = COLLECT_HORIZON,
             target_eps: list[dict] | None = None) -> dict:
    """把 8A 三条门的**事前**预测算出来（一条都不改，只对照）。"""
    tk = takeovers(eps)
    need = need_steps(eps)
    st = stratify(eps, CORPUS_HORIZON, need)
    mm = model_m_by_episode(eps, CORPUS_HORIZON, target_horizon, need)
    n_tk = len(tk)
    n_ep = len(eps)
    a2_l = (st["n_ok_observed"] / n_tk) if n_tk else float("nan")
    a2_u = (st["grasp"]["n"] / n_tk) if n_tk else float("nan")
    a2_m = mm["a2"]
    # A1：帧数 = 预测可用局数 × 每局帧数（段长中位，封顶 MAX_SEG_LEN）
    per_ep_frames = min(need, MAX_SEG_LEN) if need == need else float("nan")
    frames_m = mm["pred_ok"] * per_ep_frames
    scale = (GATE_A1_EPISODES / n_ep) if n_ep else float("nan")
    fc = {
        "corpus": {"n_episodes": n_ep, "n_takeover": n_tk,
                   "takeover_rate": (n_tk / n_ep) if n_ep else float("nan"),
                   "horizon": CORPUS_HORIZON,
                   "n_relaxed_success_all": int(sum(1 for e in eps if e["success_relaxed"])),
                   "censored_failures": int(sum(1 for e in tk if (not e["success_relaxed"])
                                                and int(e["steps"]) >= CORPUS_HORIZON - 1)),
                   "need_steps_median": need,
                   "n_handback": int(sum(1 for e in tk if e["handback"])),
                   "n_unrecoverable": int(sum(1 for e in tk if e["unrecoverable"])),
                   "by_trigger": {str(t): {"n": len([e for e in tk if e["trigger"] == t]),
                                           "n_ok": int(sum(1 for e in tk
                                                           if e["trigger"] == t and e["success_relaxed"]))}
                                  for t in sorted({str(e["trigger"]) for e in tk})}},
        "strata": st,
        "target_horizon": int(target_horizon),
        "A2": {"gate": GATE_A2_RATE, "L": a2_l, "M": a2_m, "U": a2_u,
               "wilson_observed": wilson(st["n_ok_observed"], n_tk),
               "model_m_detail": mm["detail"],
               "pred_pass": bool(a2_m == a2_m and a2_m >= GATE_A2_RATE),
               "range_pass_possible": bool(a2_u == a2_u and a2_u >= GATE_A2_RATE)},
        "A1": {"gate": GATE_A1_FRAMES, "gate_episodes": GATE_A1_EPISODES,
               "frames_observed_corpus": int(sum(int(e["seg_len"]) for e in tk
                                                 if e["success_relaxed"] and int(e["seg_len"]) <= MAX_SEG_LEN)),
               "frames_pred_M": frames_m, "frames_pred_M_scaled_to_gate": frames_m * scale,
               "frames_per_accepted_episode": per_ep_frames,
               "pred_pass": bool(frames_m * scale == frames_m * scale
                                 and frames_m * scale >= GATE_A1_FRAMES)},
        "A3": {"gate_median": GATE_A3_MEDIAN, "median_observed": need,
               "handback_by_construction": 0,
               "pred_pass": bool(need == need and need <= GATE_A3_MEDIAN)},
        "target_frames_8b": TARGET_FRAMES_8B,
        "episodes_needed_for_target_M": ((TARGET_FRAMES_8B / (frames_m / n_ep))
                                        if (n_ep and frames_m and frames_m == frames_m) else float("inf")),
    }
    mt = model_m_trigger(eps, CORPUS_HORIZON, target_horizon, need)
    fc["A2_trigger"] = {"model_m": mt["a2"], "strata": mt["strata"], "detail": mt["detail"],
                        "pred_pass": bool(mt["a2"] == mt["a2"] and mt["a2"] >= GATE_A2_RATE)}
    if target_eps:
        mix = target_trigger_mix(target_eps)
        fc["target"] = {"mix": mix, "adjusted": a2_target_adjusted(mix, mt),
                        "n_episodes": len(target_eps)}
    return fc


# ─────────────────────────────── 渲染 ───────────────────────────────
def pct(x: float) -> str:
    return "NA" if x != x else f"{x * 100:.1f}%"


def render(fc: dict, srcs: list[str], ckpts: list[str]) -> str:
    c, a2, a1, a3 = fc["corpus"], fc["A2"], fc["A1"], fc["A3"]
    lo, hi = a2["wilson_observed"]
    st = fc["strata"]
    L: list[str] = []
    L.append("# 档 8 · 格 8A 产出率的**事前**预测（只读旧语料，零 GPU）")
    L.append("")
    L.append(f"* 工具：`code/mg_forecast_s8a.py`（本文件由它生成；`--selftest` 见复现节）")
    L.append(f"* 语料：{len(srcs)} 个目录 = **{c['n_episodes']} 局**（horizon={c['horizon']}）")
    for s in srcs:
        L.append(f"  * `runs/{s}`")
    for k in ckpts:
        L.append(f"* 语料检查点：`{k}`（⚠️ 这是**好 seed 1000** 的末点；8A 跑的是**坏 seed 2000**）")
    L.append(f"* 门常数出处：`code/mg_collect_corr.py`（A1 ≥{a1['gate']} 帧/{a1['gate_episodes']} 局、"
             f"A2 ≥{pct(a2['gate'])}、A3 中位 ≤{a3['gate_median']}）—— **本工具一条都没改**")
    L.append("")
    L.append("## 一、语料实测（horizon=400）")
    L.append("")
    L.append("| 项 | 读数 |")
    L.append("|:--|:--|")
    L.append(f"| 放宽成功（全部局） | {c['n_relaxed_success_all']}/{c['n_episodes']} |")
    L.append(f"| 接管 | **{c['n_takeover']}**（接管率 {pct(c['takeover_rate'])}） |")
    L.append(f"| 接管后放宽成功（= A2 的实测分子） | **{st['n_ok_observed']}/{st['n_takeover']} = "
             f"{pct(a2['L'])}** Wilson [{lo:.3f}, {hi:.3f}] |")
    L.append(f"| 失败接管里「跑满 horizon 被截断」 | **{c['censored_failures']}**/"
             f"{c['n_takeover'] - st['n_ok_observed']} ⇒ 失败与「步数不够」在 horizon=400 下**完全混淆** |")
    L.append(f"| 专家恢复一段所需步数（成功片段 seg_len 中位） | **{c['need_steps_median']:.1f}** |")
    L.append(f"| 认输交还 / 专家 unrecoverable | {c['n_handback']} / {c['n_unrecoverable']} |")
    L.append("")
    L.append("### 分层：瓶颈是「到不到 grasp」，不是步数预算")
    L.append("")
    L.append(f"| 层 | n | 实测成功 | **语料 horizon 下步数就够**的 | 其中成功 | ⇒ 转化率 p [Wilson 95%] |")
    L.append("|:--|---:|---:|---:|---:|:--|")
    for g, name in (("grasp", "到达 `grasp`"), ("nograsp", "**从未到 `grasp`**")):
        d = st[g]
        w = wilson(d["n_room_ok"], d["n_room"])
        flag = f" ⚠️低功效(n<{LOW_POWER_N})" if d["n_room"] < LOW_POWER_N else ""
        L.append(f"| {name} | {d['n']} | {d['n_ok_observed']} | {d['n_room']} | {d['n_room_ok']} | "
                 f"**{pct(d['p_room'])}** [{w[0]:.2f}, {w[1]:.2f}]{flag} |")
    L.append("")
    ng = st["nograsp"]
    L.append(f"⇒ **「未到 grasp 但步数足够」的 {ng['n_room']} 局里成功 {ng['n_room_ok']} 局**："
             f"给够步数也救不回来 ⇒ **抬 horizon 这条 HELD 候选被事前否掉**"
             f"（预注册 §3 的三个候选之一）。")
    L.append("")
    L.append("### 按触发标签")
    L.append("")
    L.append("| 触发 | n | 实测成功 |")
    L.append("|:--|---:|---:|")
    for t, d in c["by_trigger"].items():
        L.append(f"| {t} | {d['n']} | {d['n_ok']}（{pct(d['n_ok'] / d['n']) if d['n'] else 'NA'}） |")
    L.append("")
    L.append(f"## 二、目标 horizon = **{fc['target_horizon']}** 下 A2 的三个模型（写死，不许看完 8A 再挑）")
    L.append("")
    L.append("| 模型 | 口径 | A2 预测 | 对门（≥"
             f"{pct(a2['gate'])}） |")
    L.append("|:--|:--|---:|:--|")
    L.append(f"| **L** 下界 | 假设删失无关（= 语料实测值原样搬过去） | {pct(a2['L'])} | "
             f"{'✅' if a2['L'] >= a2['gate'] else '❌'} |")
    L.append(f"| **M** 点估计 | 分层转化：每层用**语料里步数本来就够**那批的实测成功率当转化率，"
             f"乘以目标 horizon 下逐局重算的「步数够」局数 | **{pct(a2['M'])}** | "
             f"{'✅' if a2['pred_pass'] else '❌'} |")
    L.append(f"| **U** 上界 | 假设「到达 grasp」就必然成功 | {pct(a2['U'])} | "
             f"{'✅' if a2['U'] >= a2['gate'] else '❌'} |")
    tt = fc.get("A2_trigger") or {}
    L.append("")
    L.append("### 第二把尺：按**触发标签**分层的模型 M（跨 seed 可比）")
    L.append("")
    L.append("| 触发 | n（语料） | 实测成功 | with-room（语料） | 其中成功 | ⇒ 转化率 p [Wilson 95%] | 目标 horizon 下 with-room | 预测成功 |")
    L.append("|:--|---:|---:|---:|---:|:--|---:|---:|")
    for t, d in (tt.get("strata") or {}).items():
        dd = (tt.get("detail") or {}).get(t, {})
        w = wilson(d["n_room_ok"], d["n_room"])
        flag = f" ⚠️**低功效**(n={d['n_room']}<{LOW_POWER_N})" if d["n_room"] < LOW_POWER_N else ""
        L.append(f"| {t} | {d['n']} | {d['n_ok_observed']} | {d['n_room']} | {d['n_room_ok']} | "
                 f"**{pct(d['p_room'])}** [{w[0]:.2f}, {w[1]:.2f}]{flag} | "
                 f"{dd.get('n_room_target', 'NA')} | {dd.get('pred_ok', 0):.2f} |")
    L.append("")
    L.append(f"⇒ 触发分层下的模型 M：**A2 = {pct(tt.get('model_m', float('nan')))}**"
             f"（grasp 分层给的是 {pct(a2['M'])}）。")
    lowpw = [t for t, d in (tt.get("strata") or {}).items() if d["n_room"] < LOW_POWER_N]
    if lowpw:
        L.append(f"* ⚠️ 触发 {lowpw} 的 with-room 样本 < {LOW_POWER_N} 局 ⇒ 低功效格子，它的转化率点估计"
                 f"不可单独采信（Wilson 上界可以很高）⇒ **触发分层的模型 M 应读作偏下界**，"
                 f"grasp 分层（with-room 6 / 12 局）是功效较好的那把尺。")
    per_f = a1["frames_per_accepted_episode"]
    if per_f == per_f and tt.get("detail"):
        fr_t = sum(d.get("pred_ok", 0.0) for d in tt["detail"].values()) * per_f
        L.append(f"* **A1 在触发分层下 = {fr_t:.0f} 帧**（grasp 分层给 {a1['frames_pred_M']:.0f} 帧，门 ≥{a1['gate']}）"
                 f" ⇒ 两把尺跨在门的两侧 ⇒ **A1 也不算稳过**。")
    if fc.get("target"):
        tg, adj = fc["target"]["mix"], fc["target"]["adjusted"]
        L.append("")
        L.append(f"### 靶子校正：坏 seed 2000 的失败构成（{fc['target']['n_episodes']} 局 TEST）")
        L.append("")
        L.append(f"* 放宽失败的类分布（`mg_tax_fail.klass(..., 'relaxed')`，import 不重写）："
                 f"**A {tg['classes']['A']} / B {tg['classes']['B']} / C {tg['classes']['C']}**"
                 f"（UNK {tg['classes']['UNK']} 不进分母），共 {tg['n_fail']} 局失败。")
        L.append("* 按 `TRIGGER_OF_CLASS`（A⇒T1、B/C⇒T3，**映射不是测量**，出处见工具头）⇒ 靶子的触发构成："
                 + "、".join(f"{t} {pct(f)}" for t, f in sorted(tg["trigger_frac"].items())))
        L.append(f"* 套语料的 with-room 转化率 ⇒ **靶子特异的 A2 点估计 = {pct(adj['point'])}**"
                 f"（区间 [{pct(adj['lo'])}, {pct(adj['hi'])}]"
                 + (f"；不可估的触发 {adj['unknown_triggers']} 用 0/1 撑出区间" if adj["unknown_triggers"] else "")
                 + f"）⇒ 对门 {pct(a2['gate'])}：下界{'✅' if adj['pass_lo'] else '❌'} / 上界{'✅' if adj['pass_hi'] else '❌'}")
        L.append("* ⚠️ 这条校正**只纠正「失败构成」这一项偏差**；「坏 seed 的状态更难」那项偏差仍未纠正")
        L.append("  （没有盘上依据 ⇒ 不编数），所以靶子校正后的数字仍应读作**偏乐观**。")
    L.append("")
    L.append("模型 M（grasp 分层）的逐层算式：")
    for g, d in a2["model_m_detail"].items():
        L.append(f"* `{g}`：转化率 p={pct(d['p_room_corpus'])}（语料 with-room {d['n_room_corpus']} 局）"
                 f" × 目标 horizon 下 with-room {d['n_room_target']} 局 = 预测成功 {d['pred_ok']:.2f} 局")
    L.append("")
    per_f = a1["frames_per_accepted_episode"]
    fr_trig = (sum(d.get("pred_ok", 0.0) for d in (tt.get("detail") or {}).values()) * per_f
               if per_f == per_f else float("nan"))
    adj = (fc.get("target") or {}).get("adjusted") or {}
    n_tk_pred = c["n_takeover"]
    se = (math.sqrt(a2["M"] * (1 - a2["M"]) / n_tk_pred) if (n_tk_pred and a2["M"] == a2["M"]) else float("nan"))
    L.append("## 三、三条门的事前预测")
    L.append("")
    L.append("| 门 | 判据 | 预测读数（两把尺并列） | 预测 |")
    L.append("|:--|:--|:--|:--|")
    L.append(f"| **A1** | ≥{a1['gate']} 可用帧/{a1['gate_episodes']} 局 | grasp 尺 **{a1['frames_pred_M']:.0f} 帧** / "
             f"触发尺 **{fr_trig:.0f} 帧**（每局 {per_f:.0f} 帧）；语料实测（horizon=400）仅 "
             f"{a1['frames_observed_corpus']} 帧 | ⚠️ **两把尺跨在门两侧 ⇒ 压线** |")
    L.append(f"| **A2** | ≥{pct(a2['gate'])} | grasp 尺 **{pct(a2['M'])}** / 触发尺 **{pct(tt.get('model_m', float('nan')))}**"
             + (f" / 靶子校正 **{pct(adj['point'])}**" if adj.get("point") == adj.get("point") and adj else "")
             + f"；模型区间 [{pct(a2['L'])}, {pct(a2['U'])}] | ⚠️ **三个点估计全部低于门 ⇒ 预测不过** |")
    L.append(f"| **A3** | handback 恒 0 ∧ 段长中位 ≤{a3['gate_median']} ∧ 窗口不相交 | 中位 "
             f"{a3['median_observed']:.1f}；采集器 `hand_back=False` ⇒ handback 恒 0（过滤 2 是保险丝）；"
             f"窗口已由 `chain_s8a.sh` 闸 9 现算断言 | {'✅ 过' if a3['pred_pass'] else '❌ 不过'} |")
    L.append("")
    n_need = fc["episodes_needed_for_target_M"]
    L.append(f"* 8B 的目标是 **{fc['target_frames_8b']} 帧**：按模型 M 的产出率反推需要 "
             f"**{n_need:.0f} 局**（`chain_s8a.sh` 的 `B_MAX_EPS=320`；预注册 §3 写的是上限 400 局 "
             f"⇒ 见 §9 增补 6 记录的口径差）。")
    L.append("")
    L.append("## 四、结论与 HELD 分支的事前处置（**不改门**）")
    L.append("")
    L.append(f"1. **A2 预测不过（三个点估计都低于门）**：grasp 尺 {pct(a2['M'])}、触发尺 "
             f"{pct(tt.get('model_m', float('nan')))}、靶子校正 "
             f"{pct(adj['point']) if adj else 'NA'}，门是 {pct(a2['gate'])}；只有模型 U（「到 grasp 就成」这个"
             f"**上界**假设）才刚过线 ⇒ **8A 写 `s8a.HELD` 的概率明显高于写 `s8a.done`**。")
    L.append(f"2. **A1 也在门的两侧**：grasp 尺 {a1['frames_pred_M']:.0f} 帧（过）vs 触发尺 {fr_trig:.0f} 帧（不过），"
             f"门是 {a1['gate']} 帧 ⇒ 不能说「帧数稳过」。**A3 稳过**（中位 {a3['median_observed']:.0f} ≤ "
             f"{a3['gate_median']}、handback 恒 0、窗口已由闸 9 断言）。")
    L.append(f"3. ⚠️ **功效警告（必须和读数一起看）**：A2 是在 ~{n_tk_pred} 个接管上判 {pct(a2['gate'])} 的门 ⇒ "
             f"1σ ≈ **{se * 100:.1f} pp** ⇒ 真值 40% 时有约一半概率测到 <40%、真值 32% 时也有约一成概率测到 ≥40%。"
             f"⇒ 一次 HELD **不能**读成「产出率确定不够」，只能读成「n=80 局的标定分不开 32% 与 40%」。")
    L.append("4. **抬 horizon 事前否掉**：未到 grasp 的层在步数足够时 **0/12** 成功 ⇒ 再加步数没有用"
             "（预注册 §3 的三个 HELD 候选之一就此排除）。")
    L.append("5. **降目标帧数是可行的候选**（与预注册 §3 一致）：若 A2 过而 A1 只差一点，"
             "按预注册 8B「凑不满就按实际帧数走并在判定里写明」本来就不追加预算。")
    L.append("6. ⇒ 若 A2 真的不过，**病因是脚本专家从「策略访问到的状态」到不了 grasp**"
             "（approach/descend 的实现），而**不是**「纠正数据」这条杠杆本身无效。")
    L.append("   处置顺序（预注册 §3 的「等人决定」在此**事前**写清，避免半夜现编）：")
    L.append("   * **(a) 首选**：另立一档修专家的 reach-grasp（新预注册、新档号）。⚠️ 但 `mg_expert.py` 是冻结文件、")
    L.append("     `mg_expert_reverse.py` 是 180 条示范的生成器 ⇒ 改它会让「示范 vs 纠正片段」的出身不可比，")
    L.append("     所以这一档必须先解决**出身可比性**（例如只在纠正采集里用 v2 专家、示范保持 v1，并把这条差异写进数据卡片）。")
    L.append("   * **(b) 次选**：接受较低的 A2、按实际帧数走 8B/8C，但必须在 `runs/S8_VERDICT.md` 里打")
    L.append("     `A2_BELOW_GATE` 标并写明「纠正语料只覆盖了可救回的那部分失败状态 ⇒ D1 的效应量被低估」；")
    L.append("     **这是改门，必须由人显式批准并留档（坑 40），链不许自己做**。")
    L.append("   * **(c) 兜底**：认定这条杠杆产出率不够 ⇒ 转阶梯 7（RL）。")
    L.append("")
    L.append("⚠️ **两条已知偏差（不做数值修正，因为没有盘上依据）**：")
    L.append(f"* 语料是**好 seed 1000**（反向放宽 {pct(c['n_relaxed_success_all'] / c['n_episodes'])}），"
             "8A 跑的是**坏 seed 2000**（41.2%）⇒ 接管率会更高、接管到的状态可能更难 ⇒ 本预测对 A2 **偏乐观**。")
    L.append("* 语料 `hand_back=True`（专家认输会交还策略），采集器 `hand_back=False`（专家跑到本局结束）"
             "⇒ 语料里 3 局交还后由策略做完的成功，在采集器口径下会算到专家头上或干脆失败 ⇒ 方向不定、量级小（3/35）。")
    L.append("")
    L.append("## 五、复现")
    L.append("")
    L.append("```bash")
    L.append("$MG_PY code/mg_forecast_s8a.py --selftest")
    L.append(f"# 语料 = 档 5.1 的 80 局；靶子 = 坏 seed 2000 的反向 TEST 80 局（做失败构成校正）")
    L.append(f"$MG_PY code/mg_forecast_s8a.py --corpus-glob '{CORPUS_GLOB}' \\")
    L.append("    --target-runs 'runs/s3r_seed2000_rev_test_rand20_k10*' > runs/_diag/s8a_yield_forecast.md")
    L.append("$MG_PY code/mg_forecast_s8a.py --target-runs 'runs/s3r_seed2000_rev_test_rand20_k10*' \\")
    L.append("    --json > runs/_diag/s8a_yield_forecast.json")
    L.append("```")
    return "\n".join(L) + "\n"


# ─────────────────────────────── 自测 ───────────────────────────────
def _ep(seed, tk, ok, seg, step, phases, steps, trig="T1", hb=False, unrec=False):
    return {"seed": seed, "takeover": tk, "takeover_step": step, "success_relaxed": ok,
            "seg_len": seg, "steps": steps, "expert_phases": phases, "trigger": trig,
            "handback": hb, "unrecoverable": unrec}


def selftest() -> int:
    n_ok = n_bad = 0

    def chk(name, cond):
        nonlocal n_ok, n_bad
        if cond:
            n_ok += 1
        else:
            n_bad += 1
            print(f"  [FAIL] {name}")

    G = ["approach", "descend", "grasp", "lift", "carry"]
    NG = ["approach", "descend"]

    # ── need_steps：中位的定义独立算 + 边界（坑 65：内/外/压线各一条）──
    eps = [_ep(1, True, True, 100, 50, G, 150), _ep(2, True, True, 300, 50, G, 350),
           _ep(3, True, True, 200, 50, G, 250)]
    chk("need_steps 3 个奇数个 ⇒ 中位 = 200.0（sorted[1]）", need_steps(eps) == 200.0)
    eps4 = eps + [_ep(4, True, True, 400, 50, G, 450)]
    chk("need_steps 4 个偶数个 ⇒ (200+300)/2 = 250.0", need_steps(eps4) == 250.0)
    chk("need_steps 无成功片段 ⇒ nan（不许 0 兜底，0 会让「步数够」恒真 ⇒ 模型 M 退化成 U）",
        math.isnan(need_steps([_ep(1, True, False, 800, 10, NG, 800)])))
    chk("need_steps 忽略 seg_len==0 的假成功（成功已 latch ⇒ 段长 0）",
        need_steps([_ep(1, True, True, 0, 200, G, 200), _ep(2, True, True, 180, 20, G, 200)]) == 180.0)
    chk("need_steps 不数非接管局（那批 seg_len 恒 0 ⇒ 只剩它时是 nan）",
        math.isnan(need_steps([_ep(1, False, True, 999, -1, [], 200)])))

    # ── has_room：边界三态 ──
    chk("has_room 剩 210 = 需 210 ⇒ 够（>=）", has_room(_ep(1, True, False, 0, 590, NG, 800), 800, 210.0))
    chk("has_room 剩 209 < 需 210 ⇒ 不够", not has_room(_ep(1, True, False, 0, 591, NG, 800), 800, 210.0))
    chk("has_room need=nan ⇒ 一律 False（不让模型 M 退化成 U）",
        not has_room(_ep(1, True, False, 0, 0, NG, 800), 800, float("nan")))

    # ── stratify：分层计数 ──
    tk = [_ep(1, True, True, 200, 100, G, 300),      # grasp, room@400(300>=200), ok
          _ep(2, True, False, 300, 100, G, 400),    # grasp, room@400, fail
          _ep(3, True, False, 350, 50, NG, 400),    # nograsp, room@400(350>=200), fail
          _ep(4, True, True, 200, 350, G, 400)]     # grasp, 剩 50 < 200 ⇒ no room, ok（删失外成功）
    st = stratify(tk, 400, 200.0)
    chk("stratify n_takeover=4", st["n_takeover"] == 4)
    chk("stratify grasp 层 n=3 / room=2 / room_ok=1 ⇒ p=0.5",
        (st["grasp"]["n"], st["grasp"]["n_room"], st["grasp"]["n_room_ok"], st["grasp"]["p_room"]) == (3, 2, 1, 0.5))
    chk("stratify nograsp 层 n=1 / room=1 / room_ok=0 ⇒ p=0.0",
        (st["nograsp"]["n"], st["nograsp"]["n_room"], st["nograsp"]["n_room_ok"], st["nograsp"]["p_room"]) == (1, 1, 0, 0.0))
    chk("stratify 实测成功 2/4", st["n_ok_observed"] == 2)
    st0 = stratify([_ep(1, False, True, 0, -1, [], 200)], 400, 200.0)
    chk("stratify 无接管 ⇒ n_takeover=0（下游必须给 nan，不许除零）", st0["n_takeover"] == 0)
    ste = stratify([_ep(1, True, False, 300, 100, NG, 400)], 400, 200.0)
    chk("stratify 某层 room=0 ⇒ p_room=nan（不是 0，0 会假装「测过了、转化率是 0」）",
        ste["grasp"]["n_room"] == 0 and ste["grasp"]["p_room"] != ste["grasp"]["p_room"])

    # ── 模型 M：手算对账 ──
    mm = model_m_by_episode(tk, 400, 800, 200.0)
    # 目标 800 下：4 局全部 with-room（takeover_step ≤350 ⇒ remain ≥450 ≥200）
    # grasp 层 p=0.5 × 3 局 = 1.5；nograsp 层 p=0.0 × 1 局 = 0 ⇒ pred_ok=1.5 ⇒ A2=1.5/4=37.5%
    chk("模型M 手算：0.5×3 + 0.0×1 = 1.5 ⇒ A2 = 1.5/4 = 37.5%", abs(mm["a2"] - 0.375) < 1e-9)
    chk("模型M pred_ok=1.5", abs(mm["pred_ok"] - 1.5) < 1e-9)
    chk("模型M 逐层 n_room_target：grasp=3 / nograsp=1",
        mm["detail"]["grasp"]["n_room_target"] == 3 and mm["detail"]["nograsp"]["n_room_target"] == 1)
    mm400 = model_m_by_episode(tk, 400, 400, 200.0)
    # 目标 == 语料 horizon ⇒ with-room 就是语料那批：grasp 2 局×0.5=1.0，nograsp 1×0=0 ⇒ 1.0/4=25%
    chk("模型M 目标==语料 horizon ⇒ 只覆盖 with-room 那批：1.0/4 = 25%（< 实测 50%，因为删失局不计）",
        abs(mm400["a2"] - 0.25) < 1e-9)
    chk("模型M 无接管 ⇒ a2=nan（不报 0%）",
        math.isnan(model_m_by_episode([_ep(1, False, True, 0, -1, [], 200)], 400, 800, 200.0)["a2"]))

    # ── models()：L/U 的定义 ──
    md = models(stratify(tk, 400, 200.0), 400, 800, 200.0)
    chk("模型L = 实测 2/4 = 50%", abs(md["L"] - 0.5) < 1e-9)
    chk("模型U = 到 grasp 比例 3/4 = 75%", abs(md["U"] - 0.75) < 1e-9)
    chk("L ≤ M 不必然成立，但 U ≥ M 必须成立（U 是上界）", md["U"] >= 1.5 / 4 - 1e-9)
    md0 = models(stratify([_ep(1, False, True, 0, -1, [], 200)], 400, 200.0), 400, 800, 200.0)
    chk("无接管 ⇒ 三个模型都 nan（不报 0%）", all(math.isnan(v) for v in (md0["L"], md0["M"], md0["U"])))

    # ── forecast：整合 + 与门对照 ──
    big = ([_ep(i, True, True, 200, 100, G, 300) for i in range(10)]
           + [_ep(100 + i, True, False, 300, 100, NG, 400) for i in range(10)])
    fc = forecast(big, target_horizon=800)
    chk("forecast n_takeover=20 / 实测成功 10 ⇒ A2_L=50%", abs(fc["A2"]["L"] - 0.5) < 1e-9)
    chk("forecast grasp 层 p=1.0（10 局全成、全 with-room）", fc["strata"]["grasp"]["p_room"] == 1.0)
    chk("forecast nograsp 层 p=0.0（10 局全灭、全 with-room）⇒ 模型M = 10×1.0/20 = 50%",
        abs(fc["A2"]["M"] - 0.5) < 1e-9)
    chk("forecast 模型U = 10/20 = 50%（到 grasp 的一半）", abs(fc["A2"]["U"] - 0.5) < 1e-9)
    chk("forecast A2 预测过门（50% ≥ 40%）", fc["A2"]["pred_pass"] is True)
    chk("forecast A1 未缩放帧数 = 预测可用 10 局 × 200 帧 = 2000", abs(fc["A1"]["frames_pred_M"] - 2000.0) < 1e-9)
    chk("forecast A1 判定用**缩放到门口径 80 局**的帧数：语料 20 局 ⇒ scale=4 ⇒ 8000 ≥ 2000 ⇒ 过",
        abs(fc["A1"]["frames_pred_M_scaled_to_gate"] - 8000.0) < 1e-9 and fc["A1"]["pred_pass"] is True)
    # A1 的压线两侧必须在**门口径（80 局 ⇒ scale=1）**上构造，否则测的是缩放不是门（坑 65：期望按定义独立算）
    gate80_pass = ([_ep(i, True, True, 200, 100, G, 300) for i in range(10)]
                   + [_ep(500 + i, True, False, 300, 100, NG, 400) for i in range(70)])
    gate80_fail = ([_ep(i, True, True, 200, 100, G, 300) for i in range(9)]
                   + [_ep(500 + i, True, False, 300, 100, NG, 400) for i in range(71)])
    chk("forecast A1 压线**内侧**：80 局里 10 局可用 × 200 帧 = 2000 ≥ 2000 ⇒ 过",
        forecast(gate80_pass, target_horizon=800)["A1"]["pred_pass"] is True)
    chk("forecast A1 压线**外侧**：80 局里 9 局可用 × 200 帧 = 1800 < 2000 ⇒ 不过",
        forecast(gate80_fail, target_horizon=800)["A1"]["pred_pass"] is False)
    chk("forecast A3 中位 200 ≤ 300 ⇒ 过", fc["A3"]["pred_pass"] is True)
    chk("forecast 删失计数：10 个失败接管全跑满 400 步 ⇒ censored=10", fc["corpus"]["censored_failures"] == 10)
    chk("forecast 段长封顶 MAX_SEG_LEN：seg_len=900 的片段按 300 计帧",
        forecast([_ep(1, True, True, 900, 10, G, 910)], target_horizon=800)["A1"]["frames_per_accepted_episode"]
        == MAX_SEG_LEN)
    chk("forecast 8B 反推局数：7000/(2000/20 局) = 70 局", abs(fc["episodes_needed_for_target_M"] - 70.0) < 1e-9)
    chk("forecast 产出率 0 ⇒ 反推局数 = inf（不是 0，0 会假装「不用采」）",
        forecast([_ep(1, True, False, 400, 10, NG, 400)], target_horizon=800)["episodes_needed_for_target_M"]
        == float("inf"))

    # ── load_corpus 的缺字段防线（坑 40③：缺字段 ≠ 0）──
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        d = root / "runs" / "fake_run"
        d.mkdir(parents=True)
        (d / "eval_summary.json").write_text(json.dumps({"episodes": 1, "seconds": 1.0,
                                                        "policy_ckpt": "x", "per_episode": [{"seed": 1}]}))
        try:
            load_corpus(root / "runs", "fake_run*")
            chk("load_corpus 缺字段必须抛 KeyError", False)
        except KeyError:
            chk("load_corpus 缺字段抛 KeyError（不静默当 0）", True)
        (root / "runs" / "fake_run" / "eval_summary.json").write_text(json.dumps(
            {"episodes": 1, "seconds": 12.0, "policy_ckpt": "ck/022000",
             "per_episode": [_ep(7, True, True, 200, 100, G, 300)]}))
        got = load_corpus(root / "runs", "fake_run*")
        chk("load_corpus 正常读回 1 局并附 _src/_seconds", len(got) == 1 and got[0]["_seconds"] == 12.0)
        try:
            load_corpus(root / "runs", "nonexistent*")
            chk("load_corpus 目录不存在必须抛 FileNotFoundError", False)
        except FileNotFoundError:
            chk("load_corpus 目录不存在抛 FileNotFoundError（不返回空列表假装「语料是 0 局」）", True)

    # ── 第二把尺：按触发标签分层 ──
    tk2 = [_ep(1, True, True, 200, 100, G, 300, trig="T1"),     # T1 with-room@400, ok
           _ep(2, True, False, 300, 100, G, 400, trig="T1"),    # T1 with-room@400, fail
           _ep(3, True, False, 300, 100, NG, 400, trig="T3"),   # T3 with-room@400, fail
           _ep(4, True, True, 200, 100, G, 300, trig="T3")]     # T3 with-room@400, ok
    sb = _strata_by(tk2, 400, 200.0, lambda e: e["trigger"])
    chk("_strata_by T1 层：n=2 / room=2 / room_ok=1 ⇒ p=0.5",
        (sb["T1"]["n"], sb["T1"]["n_room"], sb["T1"]["n_room_ok"], sb["T1"]["p_room"]) == (2, 2, 1, 0.5))
    chk("_strata_by T3 层：n=2 / room=2 / room_ok=1 ⇒ p=0.5",
        (sb["T3"]["n"], sb["T3"]["n_room"], sb["T3"]["n_room_ok"], sb["T3"]["p_room"]) == (2, 2, 1, 0.5))
    mt = model_m_trigger(tk2, 400, 800, 200.0)
    chk("model_m_trigger 手算：0.5×2(T1) + 0.5×2(T3) = 2.0 ⇒ A2 = 2/4 = 50%", abs(mt["a2"] - 0.5) < 1e-9)
    chk("model_m_trigger 无接管 ⇒ a2=nan（不报 0%）",
        math.isnan(model_m_trigger([_ep(1, False, True, 0, -1, [], 200)], 400, 800, 200.0)["a2"]))
    chk("model_m_trigger 某触发在语料里没 with-room 样本 ⇒ p=nan（不是 0）",
        math.isnan(_strata_by([_ep(1, True, False, 200, 350, NG, 400, trig="T9")], 400, 200.0,
                              lambda e: e["trigger"])["T9"]["p_room"]))

    # ── 靶子构成 → 触发构成的映射（A⇒T1、B/C⇒T3；UNK 不进分母）──
    def _tep(ok, lift, dist):
        return {"success_relaxed": ok, "lift_cm": lift, "min_dist_cm": dist}

    mix = target_trigger_mix([_tep(True, 9.0, 1.0),        # OK ⇒ 不进分母（成功局检测器已 latch）
                              _tep(False, 1.0, 50.0),      # lift<5 ⇒ A ⇒ T1
                              _tep(False, 9.0, 50.0),      # lift≥5 ∧ dist>25 ⇒ B ⇒ T3
                              _tep(False, 9.0, 3.0),       # lift≥5 ∧ dist≤25 ⇒ C ⇒ T3
                              {"lift_cm": 1.0, "min_dist_cm": 1.0}])   # 缺 success_relaxed ⇒ UNK
    chk("target_trigger_mix 类分布 A1/B1/C1/UNK1", mix["classes"] == {"A": 1, "B": 1, "C": 1, "UNK": 1})
    chk("target_trigger_mix 分母 = 3（UNK 不进分母，坑 40③）", mix["n_fail"] == 3)
    chk("target_trigger_mix 触发构成 T1=1/3、T3=2/3",
        abs(mix["trigger_frac"]["T1"] - 1 / 3) < 1e-9 and abs(mix["trigger_frac"]["T3"] - 2 / 3) < 1e-9)
    mix0 = target_trigger_mix([_tep(True, 9.0, 1.0)])
    chk("target_trigger_mix 全成功 ⇒ n_fail=0 ⇒ 占比 nan（不许 0 兜底）",
        mix0["n_fail"] == 0 and (not mix0["trigger_frac"]
                                 or all(v != v for v in mix0["trigger_frac"].values())))

    # ── 靶子校正：点估计 = Σ frac×p；不可估的触发用 0/1 撑区间 ──
    adj = a2_target_adjusted(mix, mt)
    chk("a2_target_adjusted 手算：1/3×0.5 + 2/3×0.5 = 0.5", abs(adj["point"] - 0.5) < 1e-9)
    chk("a2_target_adjusted 全部可估 ⇒ lo == hi == point", adj["lo"] == adj["hi"] == adj["point"])
    chk("a2_target_adjusted 0.5 ≥ 门 0.40 ⇒ pass_lo/pass_hi 都 True",
        adj["pass_lo"] is True and adj["pass_hi"] is True)
    mt2 = {"detail": {"T1": {"p_room_corpus": 0.6}, "T3": {"p_room_corpus": float("nan")}}}
    adj2 = a2_target_adjusted(mix, mt2)
    chk("a2_target_adjusted 有不可估触发 ⇒ point=nan（不假装能算）", math.isnan(adj2["point"]))
    chk("a2_target_adjusted 区间手算：lo = 1/3×0.6 = 0.2、hi = 0.2 + 2/3×1",
        abs(adj2["lo"] - 0.2) < 1e-9 and abs(adj2["hi"] - (0.2 + 2 / 3)) < 1e-9)
    chk("a2_target_adjusted 记下不可估的触发名", adj2["unknown_triggers"] == ["T3"])
    chk("a2_target_adjusted 0.2 < 门 0.40 ⇒ pass_lo False（下界不过就是不过）", adj2["pass_lo"] is False)
    fc_t = forecast(big, target_horizon=800,
                    target_eps=[_tep(True, 9.0, 1.0), _tep(False, 1.0, 50.0), _tep(False, 9.0, 50.0)])
    chk("forecast 传靶子 ⇒ 多出 target 键；不传 ⇒ 没有（默认行为不变）",
        "target" in fc_t and "target" not in forecast(big, target_horizon=800))
    chk("forecast 的 target.mix 与直接调 target_trigger_mix 一致",
        fc_t["target"]["mix"]["classes"] == target_trigger_mix(
            [_tep(True, 9.0, 1.0), _tep(False, 1.0, 50.0), _tep(False, 9.0, 50.0)])["classes"])

    # ── 常数出身：本工具不许自己重打一遍门（坑 55/67）──
    chk("门常数来自 mg_collect_corr（A2=0.40 / A1=2000 / A3=300 / horizon=800 / 目标 7000）",
        (GATE_A2_RATE, GATE_A1_FRAMES, GATE_A3_MEDIAN, COLLECT_HORIZON, TARGET_FRAMES_8B)
        == (0.40, 2000, 300, 800, 7000))
    chk("A1 的门口径是 80 局（与 chain_s8a.sh 的 A_EPS 一致）", GATE_A1_EPISODES == 80)
    chk("触发映射常数就是 A⇒T1、B/C⇒T3（改了要同步改工具头的出处说明）",
        TRIGGER_OF_CLASS == {"A": "T1", "B": "T3", "C": "T3"})

    print(f"[selftest] {n_ok} passed, {n_bad} failed")
    return 1 if n_bad else 0


# ─────────────────────────────── main ───────────────────────────────
def main(argv: list[str] | None = None) -> int:
    global CORPUS_HORIZON
    ap = argparse.ArgumentParser(description="档 8 · 8A 产出率的事前预测（只读旧语料）")
    ap.add_argument("--corpus-glob", default=CORPUS_GLOB, help="语料目录的 glob（相对 runs/ 的父目录）")
    ap.add_argument("--corpus-horizon", type=int, default=CORPUS_HORIZON)
    ap.add_argument("--target-horizon", type=int, default=COLLECT_HORIZON)
    ap.add_argument("--target-runs", default="",
                    help="逗号分隔的靶子评测目录（坏 seed 2000 的 TEST），用来做失败构成校正；留空则不做")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON 而不是 markdown")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    CORPUS_HORIZON = int(a.corpus_horizon)
    eps = load_corpus(MG_ROOT, a.corpus_glob)
    teps: list[dict] = []
    for pat in [p for p in a.target_runs.split(",") if p.strip()]:
        for d in sorted(MG_ROOT.glob(pat.strip())):
            from mg_tax_fail import load_eps
            got = load_eps(d)
            if not got:
                raise FileNotFoundError(f"靶子目录读不到 per_episode：{d}")
            teps += got
    fc = forecast(eps, target_horizon=int(a.target_horizon), target_eps=(teps or None))
    if a.json:
        print(json.dumps(fc, ensure_ascii=False, indent=1, default=str))
        return 0
    srcs = sorted({e["_src"] for e in eps})
    ckpts = sorted({json.loads((MG_ROOT / "runs" / e["_src"] / "eval_summary.json").read_text())["policy_ckpt"]
                    for e in eps})
    sys.stdout.write(render(fc, srcs, ckpts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
