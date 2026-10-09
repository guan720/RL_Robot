#!/usr/bin/env python3
"""档 7H 判定：「便宜配方」（bs32 / lr 1e-4 / 5500 步 = 3.791 ep）在 **3 个新训练 seed** 上能不能过使命门

预注册出处：`runs/S7H_PREREG.md`（2026-10-05 21:0x 落盘，**早于本档任何读数**、也早于 8D 的 D4 读数）。
判据（阈值全部写死在预注册 §3.3；改这里等于改判据 ⇒ 必须先改预注册，坑 40）：
  H1（主门）  = 3 个新 seed 的 TEST 反向**放宽** k/80 的 **min ≥ 40/80 = 50%**（与档 3r/7C/7G/8D 同一条使命门）
  H2（护栏）  = 每个 seed 的正向未见 20 局，掉幅 vs 193/300 = 64.3% **都 ≤ 15.0 pp**
  H3（副）    = 3 个 seed 的极差 vs 标准配方的 38.8 pp —— **不是门**（n=3、2 自由度 ⇒ 无功效）
  H4（副）    = 每个新 seed 的 11 格 val 曲线 vs **F4**（同配方、seed2000）逐格配对符号检验 —— **不是门**
出身核对（不过 ⇒ 报告打 🚫、退出码 **3**、判定**不采信**）：`policy_ckpt` 尾串 == `checkpoints/005500/pretrained_model`、
  `task_mode`、`n_action_steps == 10`、seed 窗口（反向 7000 / 正向 2000）、`episodes == 20`。
退出码：0 = 判定成立；2 = 读数不齐（**H1 = UNKNOWN，不许当 0 计**，坑 40 ③）；3 = 出身核对不过 ⇒ 不采信。

用法：
    $MG_PY code/mg_verdict_s7h.py --selftest
    $MG_PY code/mg_verdict_s7h.py > runs/S7H_VERDICT.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG = HERE.parent
RUNS = MG / "runs"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_seedcurve import read_cells, sign_test_exact          # noqa: E402  同一个量不重写第二遍（坑 54）
from mg_verdict_s2f import ci, collect, pct                   # noqa: E402
from mg_verdict_s7c import spread                             # noqa: E402
from mg_verdict_s7f import (B8_RANGE_PP, EPS, FWD_BASELINE,    # noqa: E402
                            FWD_DROP_PP, FWD_SEED0, K_EVAL, REPS, REV_SEED0, fwd_dirs, prov, rev_dirs)

# ── 预注册常数（出处 runs/S7H_PREREG.md §1.3 / §3.1 / §3.3）────────────────────────
DATASET = "mix60f120r"          # **不含**纠正帧 ⇒ normalizer 与档 8 的 mix60f120r_c1 不同（坑 33：禁止跨数据集比高低）
FRAMES = 46426                  # data/mix60f120r/meta/info.json
BS = 32
H_SEEDS = [11000, 12000, 13000]  # 预注册写死：必须是**新** seed（避开所有保留窗口，见预注册 §1.4）
H_STEPS = 5500                  # = 3.791 ep（与 bs8/22000 逐位相同的 epoch 预算）
H_SAVE = 500
H_NCELLS = 11
SPE = FRAMES / BS               # steps/epoch @ bs32 = 1450.8125
CK_SUFFIX = f"checkpoints/{H_STEPS:06d}/pretrained_model"
H1_K, H1_N = 40, 80             # 主门：min ≥ 40/80 = 50%
F4_RUN = "pi05_mix60f120r_s7f_bs32_lr1e4_seed2000"
F4_REV = (60, 80)               # 动机读数（**回溯、n=1**，不计入判定）
F4_FWD = (16, 20)
B8_TEST_REV = {1000: (55, 80), 2000: (33, 80), 3000: (64, 80)}   # 标准配方（runs/S3R_VERDICT.md）
B8_TEST_FWD = {1000: (15, 20), 2000: (4, 20), 3000: (13, 20)}


def h_prefix(seed: int) -> str:
    return f"s7h_seed{seed}"


def h_run(seed: int) -> str:
    return f"pi05_{DATASET}_s7h_seed{seed}"


# ─────────────────────────── 纯函数（判据）───────────────────────────
def gate_h1(per_seed: dict[int, tuple[int, int]]) -> dict:
    """H1：3 个新 seed 的 TEST 反向放宽 **min ≥ 40/80**。缺任何一个 ⇒ UNKNOWN（不许当 0）。"""
    have = {s: v for s, v in per_seed.items() if v and v[1] == H1_N}
    missing = sorted(set(H_SEEDS) - set(have))
    if missing:
        return {"pass": False, "unknown": True, "missing": missing, "per_seed": have,
                "gate": f"min ≥ {H1_K}/{H1_N}", "note": f"缺 seed {missing} 的齐读数（4×20 = 80 局）"}
    worst_seed = min(have, key=lambda s: have[s][0] / have[s][1])
    wk = have[worst_seed][0]
    return {"pass": bool(wk >= H1_K), "unknown": False, "missing": [], "per_seed": have,
            "worst_seed": worst_seed, "min_k": wk, "gate": f"min ≥ {H1_K}/{H1_N}", "note": ""}


def fwd_drop(k: int, n: int) -> float:
    """正向掉幅（pp）vs 档 3 合并基线 193/300 = 64.3%。无读数 ⇒ nan（不静默当 0）。"""
    if n <= 0:
        return float("nan")
    return round(100.0 * (FWD_BASELINE[0] / FWD_BASELINE[1]) - 100.0 * k / n, 2)


def gate_h2(drops: dict[int, float]) -> dict:
    """H2：三个 seed 的正向掉幅**都** ≤ 15.0 pp。缺读数 ⇒ UNKNOWN。"""
    need = list(H_SEEDS)
    have = {s: d for s, d in drops.items() if d == d}
    missing = [s for s in need if s not in have]
    if missing:
        return {"pass": False, "unknown": True, "missing": missing, "drops": have,
                "gate": f"三个都 ≤ {FWD_DROP_PP} pp vs {FWD_BASELINE[0]}/{FWD_BASELINE[1]}", "note": "读数不齐"}
    bad = [s for s, d in have.items() if d > FWD_DROP_PP]
    return {"pass": not bad, "unknown": False, "missing": [], "drops": have, "bad": bad,
            "gate": f"三个都 ≤ {FWD_DROP_PP} pp vs {FWD_BASELINE[0]}/{FWD_BASELINE[1]} = "
                    f"{100*FWD_BASELINE[0]/FWD_BASELINE[1]:.1f}%",
            "note": ("拆东墙：" + ", ".join(f"seed{s} 掉 {have[s]:+.2f} pp" for s in bad)) if bad else ""}


def h4_cells(seed: int) -> list[dict]:
    """本格 11 格反向 val 曲线（放宽口径），复用 mg_seedcurve.read_cells（冻结语义只 import）。"""
    return read_cells(RUNS / h_run(seed), "sweep_rev", "rev", SPE)


def h4_pair(a: list[dict], b: list[dict]) -> dict:
    """逐格配对（按 step）比较放宽成功数：返回 wins/losses/ties/n_pairs/p（双侧精确符号检验）。

    合法性：两臂是**同配方同数据集同 val 窗口同 K** 的两个训练 seed，逐格是同一批 20 个初态
      ⇒ 这是合法的配对二值设计（同 mg_verdict_s8.pair_outcomes 的论证），不是「另一次采样」的伪配对。
    """
    bb = {r["step"]: r for r in b}
    wins = losses = ties = 0
    for r in a:
        o = bb.get(r["step"])
        if not o or r.get("k_relaxed") is None or o.get("k_relaxed") is None:
            continue
        if r["k_relaxed"] > o["k_relaxed"]:
            wins += 1
        elif r["k_relaxed"] < o["k_relaxed"]:
            losses += 1
        else:
            ties += 1
    n = wins + losses + ties
    return {"wins": wins, "losses": losses, "ties": ties, "n_pairs": n,
            "p": sign_test_exact(wins, losses),
            "note": ("" if n == H_NCELLS else f"⚠️ 只配上 {n}/{H_NCELLS} 格")}


# ─────────────────────────── 报告 ───────────────────────────
def report() -> int:
    rev, strict, fwd = {}, {}, {}
    for sd in H_SEEDS:
        rev[sd] = collect(rev_dirs(h_prefix(sd)), "n_success_relaxed", "pc_success_relaxed")
        strict[sd] = collect(rev_dirs(h_prefix(sd)), "n_success", "pc_success")
        fwd[sd] = collect(fwd_dirs(h_prefix(sd)), "n_success_relaxed", "pc_success_relaxed")
    ready = [sd for sd in H_SEEDS if rev[sd]["n"] == REPS * EPS]

    if not ready:
        print("# 档 7H 判定：**读数不齐，无法判定**\n")
        print(f"* 已齐的训练 seed：无；需要 {H_SEEDS}（bs{BS} / {H_STEPS} 步 = 3.791 ep / lr 1e-4 / **新** seed）")
        print(f"* 缺产物：{[d for sd in H_SEEDS for d in rev_dirs(h_prefix(sd)) if not (RUNS / d / 'eval_summary.json').exists()][:6]} …")
        print(f"\n（生成时间 {datetime.now():%F %T}）")
        return 2

    per_seed = {sd: (rev[sd]["k"], rev[sd]["n"]) for sd in ready}
    h1 = gate_h1(per_seed)
    drops = {sd: fwd_drop(fwd[sd]["k"], fwd[sd]["n"]) for sd in ready}
    h2 = gate_h2(drops)
    sp = spread([rev[sd]["k"] / rev[sd]["n"] for sd in ready])

    f4_cells = read_cells(RUNS / F4_RUN, "sweep_rev", "rev", SPE)
    h4 = {sd: h4_pair(h4_cells(sd), f4_cells) for sd in ready}

    prov_bad = []
    for sd in ready:
        prov_bad += prov(rev_dirs(h_prefix(sd)), CK_SUFFIX, "reverse", REV_SEED0)
        prov_bad += prov(fwd_dirs(h_prefix(sd)), CK_SUFFIX, "forward", FWD_SEED0)
    trust = not prov_bad

    def yn(b: bool | None) -> str:
        return "⏳ UNKNOWN" if b is None else ("✅ PASS" if b else "❌ FAIL")

    L = ["# 档 7H 判定：便宜配方（bs32 / lr 1e-4 / 5500 步 = 3.791 ep）在 3 个**新**训练 seed 上的前瞻验证", "",
         f"* 生成时间：{datetime.now():%F %T}（`code/mg_verdict_s7h.py`）",
         "* 预注册出处：`runs/S7H_PREREG.md`（2026-10-05 21:0x 落盘，**早于本档任何读数**，也早于 8D 的 D4）",
         f"* 配方：数据集 `{DATASET}`（180 集 / {FRAMES} 帧，**不含**纠正帧）/ bs{BS} / {H_STEPS} 步 = 3.791 ep / "
         f"lr 1e-4 / save_freq {H_SAVE}（{H_NCELLS} 格）/ 新 seed **{H_SEEDS}**",
         f"* 主口径 = **放宽 R**（送到为首要，侧躺另打 `delivered_tipped` 标）；关门格 = `last` = {H_STEPS:06d}，**不做 val 选点**（坑 27/38/42）",
         f"* 出身核对：{'✅ 全对' if trust else f'🚫 {len(prov_bad)} 条不对 ⇒ 本判定不采信'}",
         f"* 已齐读数的训练 seed：**{ready}**" + (f"；缺 {[s for s in H_SEEDS if s not in ready]}"
                                                if len(ready) < len(H_SEEDS) else "（三个齐）"), "",
         "## 一、判据", "",
         "| 判据 | 读数 | 门槛 | 结果 |", "|:--|:--|:--|:--|"]

    if h1["unknown"]:
        L.append(f"| **H1** 主门（3 个新 seed 的 TEST 反向放宽 min） | 读数不齐（缺 {h1['missing']}） | "
                 f"{h1['gate']} | ⏳ UNKNOWN |")
    else:
        ws = h1["worst_seed"]
        L.append(f"| **H1** 主门 | min = **{h1['min_k']}/{H1_N} = {pct(h1['min_k'], H1_N)}**（最差 seed = {ws}，"
                 f"Wilson {ci(h1['min_k'], H1_N)}） | {h1['gate']} | "
                 f"{'✅ PASS' if (h1['pass'] and trust) else '❌ FAIL'} |")
    if h2["unknown"]:
        L.append(f"| **H2** 护栏（正向未见 20 局 ×3） | 读数不齐（缺 {h2['missing']}） | {h2['gate']} | ⏳ UNKNOWN |")
    else:
        txt = "、".join(f"seed{s} {fwd[s]['k']}/{fwd[s]['n']}（掉 {drops[s]:+.2f} pp）" for s in H_SEEDS if s in drops)
        L.append(f"| **H2** 护栏 | {txt} | {h2['gate']} | "
                 f"{'✅ PASS' if (h2['pass'] and trust) else '❌ FAIL'}{(' ｜ ' + h2['note']) if h2['note'] else ''} |")
    L.append(f"| **H3** 副（极差，**不是门**） | {sp['n']} 个 seed 极差 **{sp['range_pp']} pp**"
             f"（sd {sp['sd_pp']} pp）vs 标准配方 {B8_RANGE_PP} pp | — | 🔎 只读方向 |")
    for sd in H_SEEDS:
        if sd in h4:
            r = h4[sd]
            L.append(f"| **H4** 副（seed{sd} vs F4 逐格配对，**不是门**） | {r['n_pairs']} 格："
                     f"**{r['wins']}胜 {r['losses']}负 {r['ties']}平**，双侧 p = {r['p']:.4f}{(' ｜ ' + r['note']) if r['note'] else ''}"
                     f" | — | 🔎 只读方向 |")
    L += ["", "## 二、逐 seed 明细（TEST 反向 4×20 = 80 局，K=10，seed 窗口 7000..7019）", "",
          "| 训练 seed | 放宽 k/80 | Wilson | 严格 | 侧躺 | 送达框内 | 正向 1×20 | ckpt 尾串 |", "|---:|---:|:--|---:|--:|--:|---:|:--|"]
    for sd in H_SEEDS:
        if sd not in ready:
            L.append(f"| {sd} | （读数不齐） | | | | | | |")
            continue
        r, s, f = rev[sd], strict[sd], fwd[sd]
        L.append(f"| **{sd}** | **{r['k']}/{r['n']} = {pct(r['k'], r['n'])}** | {ci(r['k'], r['n'])} | "
                 f"{s['k']}/{s['n']} | {r['tipped']} | {r['inbox']} | {f['k']}/{f['n']} = {pct(f['k'], f['n'])} | …{H_STEPS:06d} |")
    L += ["", "## 三、对照（**同数据集**才列；跨数据集不许比高低 —— 坑 33/57）", "",
          "| 臂 | 配方 | TEST 反向放宽 | 正向未见 | 出处 |", "|:--|:--|---:|---:|:--|"]
    for sd in (1000, 2000, 3000):
        k, n = B8_TEST_REV[sd]
        fk, fn = B8_TEST_FWD[sd]
        L.append(f"| 标准配方 seed{sd} | bs8 / 22000 步 / lr1e-4 | {k}/{n} = {pct(k, n)} | {fk}/{fn} = {pct(fk, fn)} "
                 f"| `runs/S3R_VERDICT.md`（❌ 最差 41.2% ⇒ 档 3r FAIL） |")
    L.append(f"| **F4（动机读数，回溯、n=1）** | bs32 / 5500 步 / lr1e-4 / seed2000 | {F4_REV[0]}/{F4_REV[1]} = "
             f"{pct(*F4_REV)} | {F4_FWD[0]}/{F4_FWD[1]} = {pct(*F4_FWD)} | `runs/S7F_DIAG.md` §三 |")
    for sd in ready:
        L.append(f"| **7H seed{sd}（本档）** | bs32 / 5500 步 / lr1e-4 | {rev[sd]['k']}/{rev[sd]['n']} = "
                 f"{pct(rev[sd]['k'], rev[sd]['n'])} | {fwd[sd]['k']}/{fwd[sd]['n']} = "
                 f"{pct(fwd[sd]['k'], fwd[sd]['n'])} | 本档 |")
    L += ["", "## 四、机器可读行（链脚本 grep 这几行）", "", "```"]
    if h1["unknown"]:
        L.append("S7H_H1=UNKNOWN")
    else:
        L.append(f"S7H_H1={'PASS' if (h1['pass'] and trust) else 'FAIL'} min={h1['min_k']}/{H1_N} "
                 f"worst_seed={h1['worst_seed']}")
    if h2["unknown"]:
        L.append("S7H_H2=UNKNOWN")
    else:
        L.append(f"S7H_H2={'PASS' if (h2['pass'] and trust) else 'FAIL'} "
                 + " ".join(f"seed{s}={drops[s]:+.2f}pp" for s in H_SEEDS if s in drops))
    L.append(f"S7H_H3=INFO range_pp={sp['range_pp']} vs_b8={B8_RANGE_PP}")
    L.append(f"S7H_H4=INFO " + " ".join(f"seed{s}={h4[s]['wins']}w{h4[s]['losses']}l{h4[s]['ties']}t:p={h4[s]['p']:.4f}"
                                        for s in H_SEEDS if s in h4))
    L.append(f"S7H_TRUST={'YES' if trust else 'NO'}")
    L += ["```", "", "## 五、决策（预注册 §3.4 的决策树，照抄）", ""]
    if h1["unknown"] or h2["unknown"]:
        L.append("* 读数不齐 ⇒ **不判**（缺的 seed 不许当 0 计，坑 40 ③）；补齐后重跑本工具。")
    elif h1["pass"] and h2["pass"] and trust:
        L.append("* **H1 ✅ ∧ H2 ✅** ⇒ 「等 epoch 下换 batch/lr」这条杠杆**前瞻成立** ⇒ seed 稳健性缺口有"
                 "**第二条独立**关闭路线（第一条 = 档 8 的纠正数据，见 `runs/S8_VERDICT.md` 的 D4）⇒ "
                 "下一步按 `STAGE_PLAN.md` 排档 9（机理：TILT / 侧躺 can 的抓取几何）。")
    elif h1["pass"] and not h2["pass"] and trust:
        L.append("* **H1 ✅ ∧ H2 ❌** ⇒ 反向过门但**拆了东墙** ⇒ 标「不可作为部署配方」，只记录；"
                 "处方 = 若要这条路线，需重做正反向配比（另起预注册，不在本档内）。")
    elif trust:
        L.append("* **H1 ❌** ⇒ F4 的 75% 是 **n=1 的幸运 / seed2000 特异** ⇒ 便宜配方**不能**替代纠正数据路线 ⇒ "
                 "唯一已证路线 = 「demo + 纠正」（档 8）；处方按 **8D 的 D4** 走（D4 ✅ ⇒ 档 8 关门；"
                 "D4 ❌ ⇒ 每 seed 各采一份纠正集，另起预注册）。")
    if not trust:
        L.append("* 🚫 **出身核对不过 ⇒ 本判定不采信**（逐条见下）。")
    L += ["", "## 六、诚实标注（预注册 §4 写死的三句话，不许事后找补）", "",
          "1. H1 ✅ 时**可以**说：「在 3.791 ep 预算、bs32/lr1e-4 下，3 个新训练 seed 的最差者 ≥ 50%」。",
          "2. H1 ✅ 时**仍然不能**说：「便宜配方比 bs8/22000 更稳健」—— 那需要两配方在**同一批新 seed**上各跑 3 发（≈52 h）；"
          "标准配方的 3 个 seed（1000/2000/3000）与本档的 3 个（11000/12000/13000）**不是同一批** ⇒ 不构成配对（坑 57）。",
          f"3. 本档数据集是 `{DATASET}`（**无**纠正帧）⇒ normalizer 与档 8 的 `{DATASET}_c1` **不同** ⇒ "
          "与 8C/8D 的任何数字**不构成可比对照**（坑 33）；第三节只列**同数据集**的臂。",
          "* ⚠️ H1 是 min-of-3 ⇒ **向下偏**的统计量，门是保守的；H3/H4 **永不**作为门（n=3、2 自由度 ⇒ 无功效）。", ""]
    if not trust:
        L += ["## 七、出身核对逐条（🚫）", ""] + [f"* {b}" for b in prov_bad] + [""]
    L += ["## 复现", "", "```bash",
          "$MG_PY code/mg_verdict_s7h.py --selftest",
          "bash code/chain_s7h.sh                       # 自己等 runs/s8d.done，不抢卡",
          "$MG_PY code/mg_verdict_s7h.py > runs/S7H_VERDICT.md", "```", ""]
    print("\n".join(L))
    return 0 if trust else 3


# ─────────────────────────── 自测 ───────────────────────────
def selftest() -> int:
    npass = nfail = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal npass, nfail
        if cond:
            npass += 1
        else:
            nfail += 1
            print(f"  ✗ {name}")

    # 常数与预注册一致
    chk("H_SEEDS = 11000/12000/13000（预注册 §3.1）", H_SEEDS == [11000, 12000, 13000])
    chk("三个新 seed 都不在保留窗口里（2000..2019 / 5062..5071 / 7000..7019 / 8000..8019 / 9000..9399）",
        all(not (2000 <= s <= 2019 or 5062 <= s <= 5071 or 7000 <= s <= 7019
                 or 8000 <= s <= 8019 or 9000 <= s <= 9399) for s in H_SEEDS))
    chk("三个新 seed 都不是已用过的训练 seed（1000/2000/3000/4000/5000）",
        not (set(H_SEEDS) & {1000, 2000, 3000, 4000, 5000}))
    chk("H1 门 = 40/80 = 50%（与档 3r/7C/7G/8D 同一条）", (H1_K, H1_N) == (40, 80))
    chk("H2 掉幅门 = 15.0 pp vs 193/300", FWD_DROP_PP == 15.0 and FWD_BASELINE == (193, 300))
    chk("ckpt 尾串 = checkpoints/005500/pretrained_model（数字格，坑 63）",
        CK_SUFFIX == "checkpoints/005500/pretrained_model")
    chk("epoch 预算对账：5500/(46426/32) = 3.791 ep", abs(H_STEPS / SPE - 3.791) < 5e-4)
    chk("bs8/22000 的 epoch 与本档相同（3.791）", abs(22000 / (FRAMES / 8) - H_STEPS / SPE) < 1e-9)
    chk("格数 = 5500/500 = 11", H_STEPS // H_SAVE == H_NCELLS)
    chk("数据集不含纠正帧（mix60f120r，不是 _c1）", DATASET == "mix60f120r")

    # 目录命名与链一致（对不上 ⇒ 判定永远读到空）
    chk("h_prefix(11000) = s7h_seed11000", h_prefix(11000) == "s7h_seed11000")
    chk("h_run(12000) = pi05_mix60f120r_s7h_seed12000", h_run(12000) == "pi05_mix60f120r_s7h_seed12000")
    chk("rev_dirs 4 读（rep2/3/4 后缀）", rev_dirs(h_prefix(11000)) == [
        "s7h_seed11000_rev_test_rand20_k10", "s7h_seed11000_rev_test_rand20_k10_rep2",
        "s7h_seed11000_rev_test_rand20_k10_rep3", "s7h_seed11000_rev_test_rand20_k10_rep4"])
    chk("fwd_dirs 1 读", fwd_dirs(h_prefix(13000)) == ["s7h_seed13000_fwd_test_rand20_k10"])

    # H1
    g = gate_h1({11000: (45, 80), 12000: (40, 80), 13000: (60, 80)})
    chk("H1：min=40 ⇒ PASS（门槛是 ≥）", g["pass"] and g["min_k"] == 40 and g["worst_seed"] == 12000)
    g = gate_h1({11000: (45, 80), 12000: (39, 80), 13000: (60, 80)})
    chk("H1：min=39 ⇒ FAIL", not g["pass"] and not g["unknown"])
    g = gate_h1({11000: (45, 80), 13000: (60, 80)})
    chk("H1：缺 seed12000 ⇒ UNKNOWN（不许当 0）", g["unknown"] and g["missing"] == [12000])
    g = gate_h1({11000: (45, 80), 12000: (20, 40), 13000: (60, 80)})
    chk("H1：局数不齐（40≠80）⇒ UNKNOWN", g["unknown"] and g["missing"] == [12000])
    g = gate_h1({11000: (80, 80), 12000: (80, 80), 13000: (80, 80)})
    chk("H1：全 80 ⇒ PASS 且 min_k=80", g["pass"] and g["min_k"] == 80)
    g = gate_h1({11000: (0, 80), 12000: (0, 80), 13000: (0, 80)})
    chk("H1：全 0 ⇒ FAIL（不是 UNKNOWN）", not g["pass"] and not g["unknown"])

    # H2
    chk("正向掉幅：16/20 ⇒ 64.33-80.0 = -15.67 pp（比基线好）", fwd_drop(16, 20) == -15.67)
    chk("正向掉幅：4/20 ⇒ +44.33 pp（档 3r seed2000 的实测）", fwd_drop(4, 20) == 44.33)
    chk("正向掉幅：无读数 ⇒ nan（不静默当 0）", fwd_drop(0, 0) != fwd_drop(0, 0))
    h = gate_h2({11000: -15.67, 12000: 5.0, 13000: 15.0})
    chk("H2：三个都 ≤15 ⇒ PASS（15.0 是边界，含等号）", h["pass"] and not h["unknown"])
    h = gate_h2({11000: -15.67, 12000: 15.01, 13000: 5.0})
    chk("H2：有一个 15.01 ⇒ FAIL 且点名 seed12000", not h["pass"] and h["bad"] == [12000])
    h = gate_h2({11000: 1.0, 13000: 2.0})
    chk("H2：缺 seed12000 ⇒ UNKNOWN", h["unknown"] and h["missing"] == [12000])
    h = gate_h2({11000: float("nan"), 12000: 1.0, 13000: 1.0})
    chk("H2：nan 不算有读数 ⇒ UNKNOWN", h["unknown"] and h["missing"] == [11000])

    # H4（配对符号检验）
    mk = lambda ks: [{"step": 500 * (i + 1), "k_relaxed": k, "n": 20} for i, k in enumerate(ks)]
    r = h4_pair(mk([20] * 11), mk([0] * 11))
    chk("H4：11 格全胜 ⇒ wins=11、ties=0、p=2·C(11,0)/2^11", r["wins"] == 11 and r["losses"] == 0
        and r["ties"] == 0 and abs(r["p"] - 2 / 2048) < 1e-12)
    chk("H4：11 格全配上 ⇒ n_pairs=11 且无 note", r["n_pairs"] == 11 and r["note"] == "")
    r = h4_pair(mk([5] * 11), mk([5] * 11))
    chk("H4：全平 ⇒ ties=11、p=1.0（平局丢弃）", r["ties"] == 11 and r["p"] == 1.0)
    r = h4_pair(mk([10] * 8 + [0] * 3), mk([0] * 8 + [10] * 3))
    chk("H4：8胜3负 ⇒ 双侧 p=2·ΣC(11,i≤3)/2^11=0.2265625", r["wins"] == 8 and r["losses"] == 3
        and r["ties"] == 0 and abs(r["p"] - 0.2265625) < 1e-9)
    r = h4_pair(mk([10] * 5 + [0] * 6), mk([0] * 5 + [10] * 6))
    chk("H4：5胜6负 ⇒ 双侧 p=1.0（对称，min 侧累加过半）", r["wins"] == 5 and r["losses"] == 6
        and abs(r["p"] - 1.0) < 1e-12)
    r = h4_pair(mk([1, 2]), mk([0, 1, 2]))
    chk("H4：格数不齐 ⇒ n_pairs<11 且打 ⚠️", r["n_pairs"] == 2 and "只配上 2/11" in r["note"])
    r = h4_pair([{"step": 500, "k_relaxed": None, "n": 20}], mk([3]))
    chk("H4：缺放宽字段的格跳过（不当 0，坑 40 ③）", r["n_pairs"] == 0)

    # 出身核对（prov 是复用的，只验调用口径）
    bad = prov(["__不存在的目录__"], CK_SUFFIX, "reverse", REV_SEED0)
    chk("prov：产物不在 ⇒ 报 1 条", len(bad) == 1 and "产物不在" in bad[0])
    chk("prov 的 seed 窗口用 7000（反向 TEST）", REV_SEED0 == 7000 and FWD_SEED0 == 2000)
    chk("prov 的 K 用 10", K_EVAL == 10)
    chk("每读 20 局、4 读 = 80 局", EPS == 20 and REPS == 4 and REPS * EPS == H1_N)

    # 对照常数与既有判定文件一致（防手抄走样，坑 55）
    chk("标准配方三 seed 的 TEST 反向 = 55/33/64（runs/S3R_VERDICT.md）",
        B8_TEST_REV == {1000: (55, 80), 2000: (33, 80), 3000: (64, 80)})
    chk("标准配方极差 38.8 pp（68.8→41.2 的差 = 38.8）",
        abs(B8_RANGE_PP - 100 * (64 / 80 - 33 / 80)) < 0.05 or abs(B8_RANGE_PP - 38.8) < 1e-9)
    chk("F4 动机读数 = 60/80 与 16/20（runs/S7F_DIAG.md §三）", F4_REV == (60, 80) and F4_FWD == (16, 20))
    chk("F4 的 run 名与盘上一致", (RUNS / F4_RUN).is_dir())
    chk("F4 的 11 格 val 产物在盘上（H4 的配对对象）",
        len(read_cells(RUNS / F4_RUN, "sweep_rev", "rev", SPE)) == H_NCELLS)

    print(f"[selftest] {npass} passed, {nfail} failed")
    return 1 if nfail else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    return report()


if __name__ == "__main__":
    raise SystemExit(main())
