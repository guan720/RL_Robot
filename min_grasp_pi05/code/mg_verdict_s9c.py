#!/usr/bin/env python3
"""档 9C 判定：**配方收口** —— 2×2 因子设计唯一缺的那格（便宜配方 × 纠正数据）能不能过同一条使命门

预注册出处：`runs/S9_PREREG.md` **增补 2**（2026-10-07 14:4x 落盘，**早于本档任何读数**）+ **增补 4**（9B 在设计阶段关闭 ⇒ 本档无条件接续）。

2×2 因子表（唯一变量 = batch/步数 与 纠正帧在不在）：

|            | 无纠正（`mix60f120r`）          | 有纠正（`mix60f120r_c1`）      |
|:--         |:--                              |:--                             |
| bs8/22000  | 档 3r：min 33/80 = 41.2% ❌      | 档 8（8C/8D）：min 64/80 ✅     |
| bs32/5500  | 档 7H：min 67/80 ✅（等 3.791 ep）| **档 9C（本档）= 唯一缺格**     |

判据（阈值写死在增补 2；改这里等于改判据 ⇒ 必须先改预注册，坑 40）：
  C1（主门）= 3 个新训练 seed 的 TEST 反向**放宽** k/80 的 **min ≥ 40/80 = 50%**（与档 3r/7C/7G/8D/7H **完全同一条**使命门）
  C2（护栏）= 每个 seed 的正向未见 20 局，掉幅 vs 193/300 = 64.3% **都 ≤ 15.0 pp**
  C3（副）  = 3 个 seed 的极差 vs 档 8 的 1.25 pp 与档 3r 的 38.8 pp —— **不是门**（n=3、2 自由度 ⇒ 无功效）
  C4（副）  = 每个 seed 的 11 格 val 曲线 vs **8D seed4000**（同数据集、bs8/22000、**同一张 epoch 网格**）
              逐格（按 epoch，不是按 step）配对符号检验 —— **不是门**
出身核对（不过 ⇒ 报告打 🚫、退出码 **3**、判定**不采信**）：`policy_ckpt` 尾串 == `checkpoints/005500/pretrained_model`、
  ckpt 路径含本档 run 名、`task_mode`、`n_action_steps == 10`、seed 窗口（反向 7000 / 正向 2000）、`episodes == 20`。
退出码：0 = 判定成立；2 = 读数不齐（**C1 = UNKNOWN，不许当 0 计**，坑 40 ③）；3 = 出身核对不过 ⇒ 不采信。

⚠️ 与 8C/8D **同数据集** ⇒ 可以并列比高低（坑 33 不适用）；与 7H/档 3r **不同数据集**（normalizer 不同）⇒ 只比形状、不比高低。

用法：
    $MG_PY code/mg_verdict_s9c.py --selftest
    $MG_PY code/mg_verdict_s9c.py > runs/S9C_VERDICT.md
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

# ── 预注册常数（出处 runs/S9_PREREG.md 增补 2）────────────────────────────────────
DATASET = "mix60f120r_c1"       # 与档 8 的 8C/8D **同一份**（含纠正帧）⇒ 可以并列比高低
EPISODES_DS = 219               # data/mix60f120r_c1/meta/info.json
FRAMES = 53638
BS = 32
C_SEEDS = [21000, 22000, 23000]  # 预注册写死：避开全部已用训练 seed（1000/2000/3000/4000/5000/11000/12000/13000）与全部保留评测窗口
C_STEPS = 5500                  # = 3.2813 ep（与 bs8/22000 的 176000 采样预算逐位相同）
C_SAVE = 500
C_NCELLS = 11
C_EPOCHS = 3.2813
SPE = FRAMES / BS               # steps/epoch @ bs32 = 1676.1875
CK_SUFFIX = f"checkpoints/{C_STEPS:06d}/pretrained_model"
C1_K, C1_N = 40, 80             # 主门：min ≥ 40/80 = 50%（同一条使命门）
# 同数据集的既有臂（档 8，出处 runs/S8_VERDICT.md）⇒ 合法对照
S8_REV = {2000: (65, 80), 4000: (65, 80), 5000: (64, 80)}
S8_FWD = {2000: (16, 20), 4000: (12, 20), 5000: (16, 20)}
S8_RANGE_PP = 1.25              # 80.0% → 78.8%（64/80）
S8_RUNS = {2000: "pi05_mix60f120r_c1_s8c_seed2000", 4000: "pi05_mix60f120r_c1_s8d_seed4000",
           5000: "pi05_mix60f120r_c1_s8d_seed5000"}
S8_SPE = FRAMES / 8             # bs8 ⇒ steps/epoch = 6704.75（C4 的 epoch 网格换算）
PAIR_ARM = 4000                 # C4 的配对对象 = 8D seed4000（预注册增补 4 写死，不许事后挑最好/最差的那臂）
H7_RUNS = {11000: "pi05_mix60f120r_s7h_seed11000", 12000: "pi05_mix60f120r_s7h_seed12000",
           13000: "pi05_mix60f120r_s7h_seed13000"}


def c_prefix(seed: int) -> str:
    return f"s9c_seed{seed}"


def c_run(seed: int) -> str:
    return f"pi05_{DATASET}_s9c_seed{seed}"


# ─────────────────────────── 纯函数（判据）───────────────────────────
def gate_c1(per_seed: dict[int, tuple[int, int]]) -> dict:
    """C1：3 个新 seed 的 TEST 反向放宽 **min ≥ 40/80**。缺任何一个 ⇒ UNKNOWN（不许当 0，坑 40 ③）。"""
    have = {s: v for s, v in per_seed.items() if v and v[1] == C1_N}
    missing = sorted(set(C_SEEDS) - set(have))
    if missing:
        return {"pass": None, "unknown": True, "missing": missing, "per_seed": have,
                "gate": f"min ≥ {C1_K}/{C1_N}", "note": f"缺 seed {missing} 的齐读数（4×20 = 80 局）"}
    worst_seed = min(have, key=lambda s: have[s][0] / have[s][1])
    wk = have[worst_seed][0]
    return {"pass": bool(wk >= C1_K), "unknown": False, "missing": [], "per_seed": have,
            "worst_seed": worst_seed, "min_k": wk, "gate": f"min ≥ {C1_K}/{C1_N}", "note": ""}


def fwd_drop(k: int, n: int) -> float:
    """正向掉幅（pp）vs 档 3 合并基线 193/300 = 64.3%。无读数 ⇒ nan（不静默当 0）。"""
    if n <= 0:
        return float("nan")
    return round(100.0 * (FWD_BASELINE[0] / FWD_BASELINE[1]) - 100.0 * k / n, 2)


def gate_c2(drops: dict[int, float]) -> dict:
    """C2：三个 seed 的正向掉幅**都** ≤ 15.0 pp。缺读数 ⇒ UNKNOWN。"""
    have = {s: d for s, d in drops.items() if d == d}
    missing = [s for s in C_SEEDS if s not in have]
    gate_txt = (f"三个都 ≤ {FWD_DROP_PP} pp vs {FWD_BASELINE[0]}/{FWD_BASELINE[1]} = "
                f"{100 * FWD_BASELINE[0] / FWD_BASELINE[1]:.1f}%")
    if missing:
        return {"pass": None, "unknown": True, "missing": missing, "drops": have, "gate": gate_txt, "note": "读数不齐"}
    bad = [s for s, d in have.items() if d > FWD_DROP_PP]
    return {"pass": not bad, "unknown": False, "missing": [], "drops": have, "bad": bad, "gate": gate_txt,
            "note": ("拆东墙：" + ", ".join(f"seed{s} 掉 {have[s]:+.2f} pp" for s in bad)) if bad else ""}


def c4_cells(seed: int) -> list[dict]:
    """本格 11 格反向 val 曲线（放宽口径），复用 mg_seedcurve.read_cells（冻结语义只 import）。"""
    return read_cells(RUNS / c_run(seed), "sweep_rev", "rev", SPE)


def c4_pair(a: list[dict], b: list[dict], tol: float = 1e-6) -> dict:
    """**按 epoch 网格**逐格配对（不是按 step）：bs32/500 与 bs8/2000 的 11 格是同一张 epoch 网格。

    合法性：两臂同数据集、同 val 窗口（8000..8019）、同 K=10、同局数 ⇒ 每格是同一批 20 个初态；
    且两臂的**采样预算逐格相同**（每格 0.2983 ep）⇒ 这是合法的配对二值设计（同 mg_verdict_s8.pair_outcomes
    与 mg_verdict_s7h.h4_pair 的论证），不是「另一次采样」的伪配对。网格对不上 ⇒ 返回 grid_ok=False、不判。
    """
    n = min(len(a), len(b))
    grid_ok = bool(n) and all(abs(a[i].get("ep", -1) - b[i].get("ep", -2)) <= tol for i in range(n))
    wins = losses = ties = 0
    if grid_ok:
        for i in range(n):
            ka, kb = a[i].get("k_relaxed"), b[i].get("k_relaxed")
            if ka is None or kb is None:      # 缺放宽字段的格跳过（不当 0，坑 40 ③）
                continue
            if ka > kb:
                wins += 1
            elif ka < kb:
                losses += 1
            else:
                ties += 1
    np_ = wins + losses + ties
    note = "" if (grid_ok and n == C_NCELLS and np_ == C_NCELLS) else (
        f"⚠️ epoch 网格对不上（不判）" if not grid_ok else f"⚠️ 只配上 {np_}/{C_NCELLS} 格")
    return {"wins": wins, "losses": losses, "ties": ties, "n_pairs": np_, "grid_ok": grid_ok,
            "p": (sign_test_exact(wins, losses) if grid_ok and np_ else float("nan")), "note": note}


def prov_c(dirs: list[str], ck_suffix: str, mode: str, seed0: int, run_name: str) -> list[str]:
    """出身核对 = 复用 mg_verdict_s7f.prov + 一条更严的：ckpt 路径必须含**本档 run 名**。"""
    bad = prov(dirs, ck_suffix, mode, seed0)
    import json
    for d in dirs:
        f = RUNS / d / "eval_summary.json"
        if f.exists():
            ck = str(json.loads(f.read_text()).get("policy_ckpt", ""))
            if f"runs/{run_name}/" not in ck:
                bad.append(f"{d}: policy_ckpt 不在本档 run 里（{ck}），期望含 runs/{run_name}/")
    return bad


# ─────────────────────────── 报告 ───────────────────────────
def report() -> int:
    rev, strict, fwd = {}, {}, {}
    for sd in C_SEEDS:
        rev[sd] = collect(rev_dirs(c_prefix(sd)), "n_success_relaxed", "pc_success_relaxed")
        strict[sd] = collect(rev_dirs(c_prefix(sd)), "n_success", "pc_success")
        fwd[sd] = collect(fwd_dirs(c_prefix(sd)), "n_success_relaxed", "pc_success_relaxed")
    ready = [sd for sd in C_SEEDS if rev[sd]["n"] == REPS * EPS]

    if not ready:
        print("# 档 9C 判定：**读数不齐，无法判定**\n")
        print(f"* 已齐的训练 seed：无；需要 {C_SEEDS}（`{DATASET}` / bs{BS} / {C_STEPS} 步 = {C_EPOCHS} ep / lr 1e-4 / 新 seed）")
        miss = [d for sd in C_SEEDS for d in rev_dirs(c_prefix(sd)) if not (RUNS / d / "eval_summary.json").exists()]
        print(f"* 缺产物（前 6）：{miss[:6]}")
        print(f"\n（生成时间 {datetime.now():%F %T}）")
        return 2

    per_seed = {sd: (rev[sd]["k"], rev[sd]["n"]) for sd in ready}
    c1 = gate_c1(per_seed)
    drops = {sd: fwd_drop(fwd[sd]["k"], fwd[sd]["n"]) for sd in ready}
    c2 = gate_c2(drops)
    sp = spread([rev[sd]["k"] / rev[sd]["n"] for sd in ready])

    pair_cells = read_cells(RUNS / S8_RUNS[PAIR_ARM], "sweep_rev", "rev", S8_SPE)
    c4 = {sd: c4_pair(c4_cells(sd), pair_cells) for sd in ready}

    prov_bad = []
    for sd in ready:
        prov_bad += prov_c(rev_dirs(c_prefix(sd)), CK_SUFFIX, "reverse", REV_SEED0, c_run(sd))
        prov_bad += prov_c(fwd_dirs(c_prefix(sd)), CK_SUFFIX, "forward", FWD_SEED0, c_run(sd))
    trust = not prov_bad

    def mark(b) -> str:
        return "⏳ UNKNOWN" if b is None else ("✅ PASS" if b else "❌ FAIL")

    L = [f"# 档 9C 判定：配方收口 —— 便宜配方（bs{BS} / {C_STEPS} 步 = {C_EPOCHS} ep / lr 1e-4）× **纠正数据**（`{DATASET}`）", "",
         f"* 生成时间：{datetime.now():%F %T}（`code/mg_verdict_s9c.py`）",
         "* 预注册出处：`runs/S9_PREREG.md` **增补 2**（14:4x 落盘，早于本档任何读数）+ **增补 4**（9B 设计阶段关闭 ⇒ 本档接续）",
         f"* 配方：`{DATASET}`（{EPISODES_DS} 集 / {FRAMES} 帧，**含**纠正帧）/ bs{BS} / {C_STEPS} 步 = {C_EPOCHS} ep / "
         f"lr 1e-4 / save_freq {C_SAVE}（{C_NCELLS} 格）/ warmup 200 / 新 seed **{C_SEEDS}**",
         f"* 与档 8 的 8C/8D **等采样预算**（5500×32 = 22000×8 = 176000）、**等 epoch**（{C_EPOCHS}）、**同数据集同 normalizer** ⇒ 2×2 四格两两可比",
         f"* 主口径 = **放宽 R**（送到为首要，侧躺另打 `delivered_tipped` 标）；关门格 = `last` = {C_STEPS:06d}，**不做 val 选点**（坑 27/38/42）",
         f"* 出身核对：{'✅ 全对' if trust else f'🚫 {len(prov_bad)} 条不对 ⇒ 本判定不采信'}",
         f"* 已齐读数的训练 seed：**{ready}**" + (f"；缺 {[s for s in C_SEEDS if s not in ready]}"
                                                if len(ready) < len(C_SEEDS) else "（三个齐）"), "",
         "## 一、判据", "",
         "| 判据 | 读数 | 门槛 | 结果 |", "|:--|:--|:--|:--|"]

    if c1["unknown"]:
        L.append(f"| **C1** 主门（3 个新 seed 的 TEST 反向放宽 min） | 读数不齐（缺 {c1['missing']}） | "
                 f"{c1['gate']} | ⏳ UNKNOWN |")
    else:
        ws = c1["worst_seed"]
        L.append(f"| **C1** 主门 | min = **{c1['min_k']}/{C1_N} = {pct(c1['min_k'], C1_N)}**（最差 seed = {ws}，"
                 f"Wilson {ci(c1['min_k'], C1_N)}） | {c1['gate']} | "
                 f"{'✅ PASS' if (c1['pass'] and trust) else '❌ FAIL'} |")
    if c2["unknown"]:
        L.append(f"| **C2** 护栏（正向未见 20 局 ×3） | 读数不齐（缺 {c2['missing']}） | {c2['gate']} | ⏳ UNKNOWN |")
    else:
        txt = "、".join(f"seed{s} {fwd[s]['k']}/{fwd[s]['n']}（掉 {drops[s]:+.2f} pp）" for s in C_SEEDS if s in drops)
        L.append(f"| **C2** 护栏 | {txt} | {c2['gate']} | "
                 f"{'✅ PASS' if (c2['pass'] and trust) else '❌ FAIL'}{(' ｜ ' + c2['note']) if c2['note'] else ''} |")
    L.append(f"| **C3** 副（极差，**不是门**） | {sp['n']} 个 seed 极差 **{sp['range_pp']} pp**（sd {sp['sd_pp']} pp）"
             f" vs 档 8 的 {S8_RANGE_PP} pp（同数据集、bs8）与档 3r 的 {B8_RANGE_PP} pp（无纠正、bs8） | — | 🔎 只读方向 |")
    for sd in C_SEEDS:
        if sd in c4:
            r = c4[sd]
            ptxt = "nan" if r["p"] != r["p"] else f"{r['p']:.4f}"
            L.append(f"| **C4** 副（seed{sd} vs 8D seed{PAIR_ARM} 按 **epoch 网格**逐格配对，**不是门**） | "
                     f"{r['n_pairs']} 格：**{r['wins']}胜 {r['losses']}负 {r['ties']}平**，双侧 p = {ptxt}"
                     f"{(' ｜ ' + r['note']) if r['note'] else ''} | — | 🔎 只读方向 |")

    L += ["", f"## 二、逐 seed 明细（TEST 反向 {REPS}×{EPS} = {C1_N} 局，K={K_EVAL}，seed 窗口 {REV_SEED0}..{REV_SEED0+EPS-1}）", "",
          "| 训练 seed | 放宽 k/80 | Wilson | 严格 | 侧躺 | 送达框内 | 正向 1×20 | ckpt 尾串 |", "|---:|---:|:--|---:|--:|--:|---:|:--|"]
    for sd in C_SEEDS:
        if sd not in ready:
            L.append(f"| {sd} | （读数不齐） | | | | | | |")
            continue
        r, s, f = rev[sd], strict[sd], fwd[sd]
        L.append(f"| **{sd}** | **{r['k']}/{r['n']} = {pct(r['k'], r['n'])}** | {ci(r['k'], r['n'])} | "
                 f"{s['k']}/{s['n']} | {r['tipped']} | {r['inbox']} | {f['k']}/{f['n']} = {pct(f['k'], f['n'])} | …{C_STEPS:06d} |")

    L += ["", "## 三、2×2 因子表（**同数据集才比高低**；跨数据集只看形状 —— 坑 33/57）", "",
          "| 配方 | 数据集 | 训练 seed | TEST 反向放宽 | min | 正向未见 | 出处 |", "|:--|:--|:--|---:|---:|---:|:--|"]
    L.append(f"| bs8 / 22000 步 / lr1e-4 | `mix60f120r`（无纠正） | 1000/2000/3000 | 55、33、64 /80 | **33/80 = 41.2% ❌** "
             f"| 15、4、13 /20 | `runs/S3R_VERDICT.md` |")
    L.append(f"| bs8 / 22000 步 / lr1e-4 | `{DATASET}`（**有纠正**） | 2000/4000/5000 | "
             + "、".join(f"{S8_REV[s][0]}" for s in (2000, 4000, 5000)) + " /80 | **64/80 = 80.0% ✅** | "
             + "、".join(f"{S8_FWD[s][0]}" for s in (2000, 4000, 5000)) + " /20 | `runs/S8_VERDICT.md`（D4） |")
    h7 = {sd: collect(rev_dirs(f"s7h_seed{sd}"), "n_success_relaxed", "pc_success_relaxed") for sd in H7_RUNS}
    h7_ready = [sd for sd, v in h7.items() if v["n"] == REPS * EPS]
    # 7H 还在飞（seed13000）⇒ 正/反向都**从盘上读**，不写死读数（写死会在它收工后变成假数）
    h7f = {sd: collect(fwd_dirs(f"s7h_seed{sd}"), "n_success_relaxed", "pc_success_relaxed") for sd in H7_RUNS}
    h7f_txt = "、".join(f"{h7f[sd]['k']}" for sd in sorted(h7_ready) if h7f[sd]["n"] == EPS) or "—"
    L.append(f"| bs32 / 5500 步 / lr1e-4 | `mix60f120r`（无纠正） | 11000/12000/13000 | "
             + ("、".join(f"{h7[sd]['k']}" for sd in sorted(h7_ready)) + " /80" if h7_ready else "（在飞）")
             + f" | **{min((h7[sd]['k'] for sd in h7_ready), default='?')}/80"
               f"{'（2/3 seed，interim）' if len(h7_ready) < 3 else ''}** | {h7f_txt} /20 | `runs/S7H_VERDICT.md` |")
    L.append(f"| **bs32 / {C_STEPS} 步 / lr1e-4** | **`{DATASET}`（有纠正）** | {'/'.join(str(s) for s in C_SEEDS)} | "
             + ("、".join(f"{rev[sd]['k']}" for sd in ready) + " /80" if ready else "（在飞）")
             + f" | **{c1.get('min_k', '?')}/{C1_N} = {pct(c1['min_k'], C1_N) if not c1['unknown'] else '—'}** | "
             + ("、".join(f"{fwd[sd]['k']}" for sd in ready) + " /20" if ready else "—") + " | 本档 |")
    L += ["", f"* ⚠️ 第 1、3 行是 `mix60f120r`（normalizer 不同）⇒ **只**用于看「便宜配方/纠正数据各自的形状」，不与本档比高低（坑 33）。",
          f"* ✅ 第 2 行（8C/8D）与本档**同数据集、同 normalizer、等采样预算** ⇒ 唯一变量 = batch/步数 ⇒ 这一对是 1:1 可比。", ""]

    L += ["## 四、机器可读行（链脚本 grep 这几行）", "", "```"]
    if c1["unknown"]:
        L.append("S9C_C1=UNKNOWN")
    else:
        L.append(f"S9C_C1={'PASS' if (c1['pass'] and trust) else 'FAIL'} min={c1['min_k']}/{C1_N} worst_seed={c1['worst_seed']}")
    if c2["unknown"]:
        L.append("S9C_C2=UNKNOWN")
    else:
        L.append(f"S9C_C2={'PASS' if (c2['pass'] and trust) else 'FAIL'} "
                 + " ".join(f"seed{s}={drops[s]:+.2f}pp" for s in C_SEEDS if s in drops))
    L.append(f"S9C_C3=INFO range_pp={sp['range_pp']} vs_s8={S8_RANGE_PP} vs_3r={B8_RANGE_PP}")
    L.append("S9C_C4=INFO " + " ".join(
        f"seed{s}={c4[s]['wins']}w{c4[s]['losses']}l{c4[s]['ties']}t:p="
        + ("nan" if c4[s]["p"] != c4[s]["p"] else f"{c4[s]['p']:.4f}") for s in C_SEEDS if s in c4))
    L.append(f"S9C_TRUST={'YES' if trust else 'NO'}")
    L += ["```", "", "## 五、决策（预注册 增补 2 的决策树，照抄）", ""]
    if c1["unknown"] or c2["unknown"]:
        L.append("* 读数不齐 ⇒ **不判**（缺的 seed 不许当 0 计，坑 40 ③）；补齐后重跑本工具。")
    elif c1["pass"] and c2["pass"] and trust:
        L.append("* **C1 ✅ ∧ C2 ✅** ⇒ 2×2 补齐：「便宜配方 + 纠正数据」三个 seed 全过使命门 ⇒ "
                 "**部署配方 = bs32/5500 + 纠正数据**（单臂 ~7 h 而不是 ~17 h，等 epoch 等采样预算）⇒ "
                 "下一步按 `STAGE_PLAN.md` 走用户阶梯：标准 chunk 执行 → Harness 接管 → RL 微调 → 真机。")
    elif c1["pass"] and not c2["pass"] and trust:
        L.append("* **C1 ✅ ∧ C2 ❌** ⇒ 反向过门但**拆了东墙** ⇒ 标「不可作为部署配方」，只记录；"
                 "处方 = 重做正反向配比（另起预注册，不在本档内调参）。")
    elif trust:
        L.append("* **C1 ❌** ⇒ 「便宜配方」与「纠正数据」**不叠加** ⇒ 部署配方回到档 8 已关门的那格"
                 "（bs8/22000 + 纠正，min 64/80 = 80.0%）；便宜配方只在**无纠正**数据上成立（档 7H）。"
                 "⇒ 2×2 表照实填「交互作用为负」，这本身就是收口结论。")
    if not trust:
        L.append("* 🚫 **出身核对不过 ⇒ 本判定不采信**（逐条见下）。")

    L += ["", "## 六、诚实标注（发车前写死，不许事后找补）", "",
          f"1. C1 ✅ 时**可以**说：「在 {C_EPOCHS} ep 预算、bs32/lr1e-4、含纠正帧的数据集上，3 个新训练 seed 的最差者 ≥ 50%」。",
          "2. C1 ✅ 时**仍然不能**说：「便宜配方比 bs8/22000 更好/更稳」—— 两臂的 seed **不是同一批**"
          "（8C/8D 用 2000/4000/5000，本档用 21000/22000/23000）⇒ 高低比较只在「都过同一条门」这个层面上成立，"
          "效应量比较需要同一批 seed 各跑 3 发（坑 57）。C4 的逐格配对只读**方向**。",
          "3. C3/C4 **永不**作为门（n=3、2 自由度；11 格曲线是同一批 val 初态的重复测量 ⇒ 只作形状佐证）。",
          f"4. 本档与档 8 同数据集 ⇒ **可以**并列比；与档 7H / 档 3r 不同数据集 ⇒ normalizer 不同 ⇒ **禁止**比高低（坑 33）。", ""]
    if not trust:
        L += ["## 七、出身核对逐条（🚫）", ""] + [f"* {b}" for b in prov_bad] + [""]
    L += ["## 复现", "", "```bash", "source code/env.sh",
          "$MG_PY code/mg_verdict_s9c.py --selftest",
          "bash code/chain_s9c.sh                        # 自己等 runs/s7h.done + runs/s9b 终态，不抢卡",
          "$MG_PY code/mg_verdict_s9c.py > runs/S9C_VERDICT.md", "```"]
    print("\n".join(L))
    if not trust:
        return 3
    return 0 if not (c1["unknown"] or c2["unknown"]) else 2


# ─────────────────────────── 自测（零 GPU、不依赖盘上进度：坑 77）───────────────────────────
def selftest() -> int:
    fails: list[str] = []
    total = [0]

    def chk(name: str, cond: bool) -> None:
        total[0] += 1
        if not cond:
            fails.append(name)

    chk("目录名：c_prefix/c_run 与链脚本一致", c_prefix(21000) == "s9c_seed21000"
        and c_run(21000) == "pi05_mix60f120r_c1_s9c_seed21000")
    chk("rev_dirs 4 读（复用 s7f 的冻结语义）", rev_dirs(c_prefix(21000)) == [
        "s9c_seed21000_rev_test_rand20_k10", "s9c_seed21000_rev_test_rand20_k10_rep2",
        "s9c_seed21000_rev_test_rand20_k10_rep3", "s9c_seed21000_rev_test_rand20_k10_rep4"])
    chk("fwd_dirs 1 读", fwd_dirs(c_prefix(23000)) == ["s9c_seed23000_fwd_test_rand20_k10"])

    # C1
    g = gate_c1({21000: (45, 80), 22000: (40, 80), 23000: (60, 80)})
    chk("C1：min=40 ⇒ PASS（门槛是 ≥）", g["pass"] and g["min_k"] == 40 and g["worst_seed"] == 22000)
    g = gate_c1({21000: (45, 80), 22000: (39, 80), 23000: (60, 80)})
    chk("C1：min=39 ⇒ FAIL", g["pass"] is False and not g["unknown"])
    g = gate_c1({21000: (45, 80), 23000: (60, 80)})
    chk("C1：缺 seed22000 ⇒ UNKNOWN（不许当 0）", g["pass"] is None and g["unknown"] and g["missing"] == [22000])
    g = gate_c1({21000: (45, 80), 22000: (20, 40), 23000: (60, 80)})
    chk("C1：局数不齐（40≠80）⇒ UNKNOWN", g["unknown"] and g["missing"] == [22000])
    g = gate_c1({21000: (0, 80), 22000: (0, 80), 23000: (0, 80)})
    chk("C1：全 0 ⇒ FAIL（不是 UNKNOWN）", g["pass"] is False and not g["unknown"])

    # C2
    chk("正向掉幅：16/20 ⇒ 64.33-80.0 = -15.67 pp（比基线好）", fwd_drop(16, 20) == -15.67)
    chk("正向掉幅：12/20 ⇒ +4.33 pp（8D seed4000 的实测）", fwd_drop(12, 20) == 4.33)
    chk("正向掉幅：无读数 ⇒ nan（不静默当 0）", fwd_drop(0, 0) != fwd_drop(0, 0))
    h = gate_c2({21000: -15.67, 22000: 5.0, 23000: 15.0})
    chk("C2：三个都 ≤15 ⇒ PASS（15.0 是边界，含等号）", h["pass"] and not h["unknown"])
    h = gate_c2({21000: -15.67, 22000: 15.01, 23000: 5.0})
    chk("C2：有一个 15.01 ⇒ FAIL 且点名 seed22000", h["pass"] is False and h["bad"] == [22000])
    h = gate_c2({21000: 1.0, 23000: 2.0})
    chk("C2：缺 seed22000 ⇒ UNKNOWN", h["pass"] is None and h["missing"] == [22000])

    # C4（按 epoch 网格配对）
    mkc = lambda ks, spe: [{"step": int(round(500 * (i + 1) * (spe / SPE) if spe != SPE else 500 * (i + 1))),
                            "ep": 500 * (i + 1) / SPE, "k_relaxed": k, "n": 20} for i, k in enumerate(ks)]
    a = mkc([20] * 11, SPE); b = mkc([0] * 11, SPE)
    r = c4_pair(a, b)
    chk("C4：11 格全胜 ⇒ wins=11、p=2/2^11", r["wins"] == 11 and r["losses"] == 0 and r["grid_ok"]
        and abs(r["p"] - 2 / 2048) < 1e-12 and r["note"] == "")
    r = c4_pair(mkc([5] * 11, SPE), mkc([5] * 11, SPE))
    chk("C4：全平 ⇒ ties=11、p=1.0（平局丢弃）", r["ties"] == 11 and r["p"] == 1.0)
    r = c4_pair(mkc([10] * 8 + [0] * 3, SPE), mkc([0] * 8 + [10] * 3, SPE))
    chk("C4：8胜3负 ⇒ 双侧 p=0.2265625", r["wins"] == 8 and r["losses"] == 3 and abs(r["p"] - 0.2265625) < 1e-9)
    b8d = [{"step": 2000 * (i + 1), "ep": 2000 * (i + 1) / S8_SPE, "k_relaxed": 5, "n": 20} for i in range(11)]
    chk("C4：9C(bs32/500) 与 8D(bs8/2000) 的 11 格确为同一张 epoch 网格 ⇒ grid_ok=True（配对合法性）",
        c4_pair(a, b8d)["grid_ok"] is True
        and all(abs(500 * (i + 1) / SPE - 2000 * (i + 1) / S8_SPE) <= 1e-6 for i in range(11)))
    bad = [{"step": 2000 * (i + 1) + 700, "ep": (2000 * (i + 1) + 700) / S8_SPE, "k_relaxed": 5, "n": 20}
           for i in range(11)]
    r = c4_pair(a, bad)
    chk("C4：epoch 网格对不上 ⇒ 不判（grid_ok=False、p=nan）", r["grid_ok"] is False and r["p"] != r["p"]
        and "网格对不上" in r["note"])
    r = c4_pair(mkc([1, 2], SPE), mkc([0, 1, 2], SPE))
    chk("C4：格数不齐 ⇒ 打 ⚠️", r["n_pairs"] == 2 and "只配上 2/11" in r["note"])
    x = mkc([3] * 11, SPE); x[0]["k_relaxed"] = None
    r = c4_pair(x, mkc([3] * 11, SPE))
    chk("C4：缺放宽字段的格跳过（不当 0，坑 40 ③）", r["n_pairs"] == 10)

    # 常数与预注册/既有判定文件一致（防手抄走样，坑 55）
    chk("C1 门 = min ≥ 40/80（同一条使命门）", (C1_K, C1_N) == (40, 80) and REPS * EPS == C1_N)
    chk("配方常数 = bs32/5500/save500/11 格/3.2813 ep", (BS, C_STEPS, C_SAVE, C_NCELLS) == (32, 5500, 500, 11)
        and abs(C_EPOCHS - C_STEPS * BS / FRAMES) < 1e-3)
    chk("等采样预算：5500×32 == 22000×8", C_STEPS * BS == 22000 * 8)
    chk("关门格尾串 = 005500", CK_SUFFIX == "checkpoints/005500/pretrained_model")
    chk("新 seed 避开全部已用训练 seed 与保留窗口",
        not (set(C_SEEDS) & {1000, 2000, 3000, 4000, 5000, 6000, 11000, 12000, 13000, 7000, 8000, 9000})
        and all(21000 <= s <= 23000 for s in C_SEEDS))
    chk("档 8 对照常数与 runs/S8_VERDICT.md 一致",
        S8_REV == {2000: (65, 80), 4000: (65, 80), 5000: (64, 80)} and abs(S8_RANGE_PP - 1.25) < 1e-9)
    chk("档 8 三臂 run 名在盘上（C4 的配对对象）", all((RUNS / v).is_dir() for v in S8_RUNS.values()))
    chk("评测口径复用 s7f 的冻结常数", (K_EVAL, REV_SEED0, FWD_SEED0, EPS, REPS) == (10, 7000, 2000, 20, 4))

    # prov_c：产物不在 ⇒ 报 1 条（复用 prov 的语义）
    bad = prov_c(["__不存在的目录__"], CK_SUFFIX, "reverse", REV_SEED0, c_run(21000))
    chk("prov_c：产物不在 ⇒ 报错且不静默通过", len(bad) >= 1 and "产物不在" in bad[0])

    print(f"[selftest] 档 9C 判定钉子：{total[0]} 项检查，{len(fails)} 项失败")
    for f in fails:
        print("  🚫", f)
    print("ALL PASS" if not fails else "HAS FAILURES")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    return report()


if __name__ == "__main__":
    raise SystemExit(main())
