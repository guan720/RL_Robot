#!/usr/bin/env python
"""档 7C 判定汇编：新配方（bs32 等 epoch）三个 seed 的方差与使命门。

**判据全部出自 `runs/S7_PREREG.md` §3 格 7C（2026-10-03 13:55 落盘，早于任何 7B/7C 读数）。**

  C1（方差，**只读方向、不作为门**）：新配方三个 seed 的 TEST 放宽口径**极差 < 38.8 pp**
      （= batch8 三 seed 的极差，出处 `runs/S3R_VERDICT.md`）。
      ⚠️ n=3 的 sd 只有 2 个自由度 ⇒ 极差估计本身极不稳，**不能**声称「方差显著下降」；
      要声称需要 n≥5（≈35 h GPU）。这条写在预注册里，不是事后找借口（坑 53/57）。
  C2（使命门，**与档 3r 完全同一条**）：**最差 seed 的 TEST 放宽口径 ≥ 50%**。
      ✅ ⇒ 档 3r 的 FAIL 被推翻、seed 稳健性缺口关闭、使命证据链补齐。
      ❌ ⇒ 记录「batch 抬到 32 仍不足」，处方转备择假设 A1（数据顺序）/ A3（简并解族太宽）。
  C3（免费，前瞻验证早筛）：用新配方三条 val 曲线在 **epoch 1.72** 那格（bs32 = step 2500）
      前瞻检验档 3r 补充那张**回溯**表里的 T ∈ (0.05, 0.30] 规则（出处
      `runs/_diag/seedcurve_sign_strict.md` 第四节：回溯能完美分类的 (step,T) = 21/81，
      窗口 ≥3 格的最早点 = 全程 45.5%）。这条不额外花 GPU（11 格扫描已经跑了）。

⚠️ 与 `code/mg_verdict_s7.py`（档 7B 判定）的分工：那份判 M1~M5（单 seed 的机理会 + 使命门），
   本份判 C1~C3（三 seed 的方差与稳健性）。两份都不改档 3r 的 FAIL 判定，只新增自己的文件。

用法：
    $MG_PY code/mg_verdict_s7c.py --selftest
    $MG_PY code/mg_verdict_s7c.py > runs/S7C_VERDICT.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_seedcurve import fisher2, kof, read_cells, screen_backtest, sign_test_exact  # noqa: E402
from mg_verdict_s2 import fisher_two_sided  # noqa: E402
from mg_verdict_s2f import ci, collect, pct  # noqa: E402
import mg_epoch_curve as EC  # noqa: E402

# ── 预注册常数 ───────────────────────────────────────────────────────────────
BS = 32
STEPS = 5500
SAVE_FREQ = 500
LR = "2e-4"
SEEDS = [2000, 1000, 3000]        # 2000 = 7B（先跑）；1000/3000 = 7C
B8_SEEDS = {1000: "pi05_mix60f120r_s2e", 2000: "pi05_mix60f120r_s3r_seed2000",
            3000: "pi05_mix60f120r_s3r_seed3000"}
# batch8 三 seed 的 TEST 放宽口径（出处 runs/S3R_VERDICT.md 第一节）
B8_TEST = {1000: (55, 80), 2000: (33, 80), 3000: (64, 80)}
B8_RANGE_PP = 38.8                 # 80.0 − 41.2（C1 的对照）
C2_GATE = 0.50
FWD_BASELINE = (193, 300)
FWD_DROP_PP = 15.0
SCREEN_EPOCH = 1.72                # C3 的前瞻筛点（= 全程 45.5%，窗口 ≥3 格的最早点）
SCREEN_THRS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


def job_of(seed: int) -> str:
    return f"pi05_mix60f120r_s7b_bs{BS}_seed{seed}"


def test_dirs(seed: int) -> list[str]:
    return [f"s7b_bs{BS}_seed{seed}_rev_test_rand20_k10" + ("" if i == 1 else f"_rep{i}")
            for i in range(1, 5)]


def fwd_dirs(seed: int) -> list[str]:
    return [f"s7b_bs{BS}_seed{seed}_fwd_test_rand20_k10"]


# ─────────────────────────── 纯函数 ───────────────────────────
def spread(rates: list[float]) -> dict:
    """极差 / sd / 最差值。n<2 时 sd 无定义 ⇒ 返回 nan，不静默给 0。"""
    if not rates:
        return {"n": 0, "range_pp": float("nan"), "sd_pp": float("nan"),
                "worst": float("nan"), "best": float("nan"), "mean": float("nan")}
    return {"n": len(rates), "range_pp": round(100 * (max(rates) - min(rates)), 1),
            "sd_pp": round(100 * statistics.stdev(rates), 1) if len(rates) >= 2 else float("nan"),
            "worst": min(rates), "best": max(rates), "mean": statistics.fmean(rates)}


def c1_verdict(new_range_pp: float) -> dict:
    """C1 只读方向：极差是否小于 batch8 的 38.8 pp。**不是门**（预注册写明）。"""
    if new_range_pp != new_range_pp:
        return {"ok": None, "text": "读数不足，无法算极差"}
    ok = new_range_pp < B8_RANGE_PP
    return {"ok": ok,
            "text": f"新配方极差 **{new_range_pp:.1f} pp** {'<' if ok else '≥'} batch8 的 {B8_RANGE_PP} pp "
                    f"⇒ {'收窄了' if ok else '没收窄'}（⚠️ n=3、2 个自由度 ⇒ **只读方向，不作为门**）"}


def c2_verdict(k: int, n: int, worst_seed: int) -> dict:
    """C2 = 与档 3r 完全同一条使命门：最差 seed 的放宽口径 ≥ 50%。"""
    if n <= 0:
        return {"ok": None, "text": "没有 TEST 读数"}
    rate = k / n
    return {"ok": rate >= C2_GATE, "rate": rate, "worst_seed": worst_seed,
            "text": f"最差 seed = **{worst_seed}**，放宽 {k}/{n} = {100*rate:.1f}%"
                    f"（Wilson {ci(k, n)}）⇒ {'✅ 过门' if rate >= C2_GATE else '❌ 未过门'}"
                    f"（门 = {C2_GATE:.0%}，与档 3r 同一条）"}


def screen_step_for_epoch(spe: float, target_epoch: float, save_freq: int) -> int:
    """把「epoch 1.72」翻译成该 batch 下的检查点步数（必须是 save_freq 的整数倍）。"""
    raw = target_epoch * spe
    return int(round(raw / save_freq)) * save_freq


# ─────────────────────────── 主流程 ───────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    have, missing = [], []
    for sd in SEEDS:
        ok = all((MG / "runs" / d / "eval_summary.json").is_file() for d in test_dirs(sd))
        (have if ok else missing).append(sd)
    if len(have) < 2:
        print("# 档 7C 判定：**读数不齐，无法判定**\n")
        print(f"* 已齐的训练 seed：{have or '无'}；缺：{missing}")
        print(f"* 需要 {SEEDS} 三个 seed 的反向 TEST 各 4×20 局")
        print(f"\n（生成时间 {datetime.now():%F %T}；补齐后重跑 `$MG_PY code/mg_verdict_s7c.py`）")
        return 2

    rel, strict, fwd = {}, {}, {}
    for sd in have:
        rel[sd] = collect(test_dirs(sd), "n_success_relaxed", "pc_success_relaxed")
        strict[sd] = collect(test_dirs(sd), "n_success", "pc_success")
        fwd[sd] = collect(fwd_dirs(sd), "n_success_relaxed", "pc_success_relaxed")

    rates = [rel[sd]["k"] / rel[sd]["n"] for sd in have if rel[sd]["n"]]
    sp_new = spread(rates)
    b8_rates = [B8_TEST[sd][0] / B8_TEST[sd][1] for sd in B8_TEST]
    sp_b8 = spread(b8_rates)
    worst = min(have, key=lambda s: rel[s]["k"] / rel[s]["n"]) if rates else None
    c1 = c1_verdict(sp_new["range_pp"])
    c2 = c2_verdict(rel[worst]["k"], rel[worst]["n"], worst) if worst else {"ok": None, "text": "无"}

    L = ["# 档 7C 判定：新配方（bs32 等 epoch）的 seed 稳健性", "",
         f"* 生成时间：{datetime.now():%F %T}（`code/mg_verdict_s7c.py`）",
         f"* 预注册出处：`runs/S7_PREREG.md` §3 格 7C（13:55 落盘，**早于任何读数**）",
         f"* 配方：bs={BS}、steps={STEPS}（3.79 ep）、save_freq={SAVE_FREQ}、log_freq=25、lr={LR}、"
         f"grad-ckpt on、基座 `pi05_base_lr044`、数据 `mix60f120r`（46426 帧 / 180 集 / 2:1）",
         f"* 已到齐的训练 seed：**{have}**" + (f"；缺 {missing}" if missing else "（三个齐）"),
         f"* 对照：batch8 三 seed（`runs/S3R_VERDICT.md`）= "
         + ", ".join(f"seed{sd} {B8_TEST[sd][0]}/{B8_TEST[sd][1]}={100*B8_TEST[sd][0]/B8_TEST[sd][1]:.1f}%"
                     for sd in sorted(B8_TEST)),
         "", "## 一、TEST 关门读数（反向 4×20 = 80 局/seed，K=10，seed 窗口 7000..7019）", "",
         "| 训练 seed | run | 局数 | 严格 | **放宽 R（主口径）** | Wilson 95% | 侧躺标记 | 正向护栏 | 护栏掉幅 |",
         "|---:|:--|---:|---:|---:|:--|---:|---:|---:|"]
    for sd in have:
        r, st, f = rel[sd], strict[sd], fwd[sd]
        fr = f["k"] / f["n"] if f["n"] else float("nan")
        base = FWD_BASELINE[0] / FWD_BASELINE[1]
        drop = 100 * (base - fr) if fr == fr else float("nan")
        L.append(f"| {sd} | `{job_of(sd)}` | {r['n']} | {st['k']}/{st['n']} = {pct(st['k'], st['n'])} | "
                 f"**{r['k']}/{r['n']} = {pct(r['k'], r['n'])}** | {ci(r['k'], r['n'])} | {r['tipped']} | "
                 f"{f['k']}/{f['n']} = {pct(f['k'], f['n'])} | {drop:+.1f} pp "
                 f"{'✅' if drop <= FWD_DROP_PP else '🚫'} |")
    L += ["", f"* 缺产物：{[d for sd in have for d in (rel[sd]['missing'] + fwd[sd]['missing'])] or '无'}；"
          f"缺放宽字段：{[x for sd in have for x in rel[sd]['nofield']] or '无'}；"
          f"不变量（严格 ⊆ 放宽）被破坏：{[x for sd in have for x in rel[sd]['broken']] or '无'}", ""]

    L += ["## 二、C1 · 方差（**只读方向，不作为门**）", "",
          "| 配方 | n | 各 seed 放宽口径 | 极差 | sd | 最差 | 均值 |", "|:--|---:|:--|---:|---:|---:|---:|",
          f"| batch8（档 3r） | {sp_b8['n']} | "
          + ", ".join(f"{100*x:.1f}%" for x in sorted(b8_rates, reverse=True))
          + f" | **{sp_b8['range_pp']:.1f} pp** | {sp_b8['sd_pp']:.1f} pp | {100*sp_b8['worst']:.1f}% | "
            f"{100*sp_b8['mean']:.1f}% |",
          f"| **bs32（档 7B/7C）** | {sp_new['n']} | "
          + ", ".join(f"{100*x:.1f}%" for x in sorted(rates, reverse=True))
          + f" | **{sp_new['range_pp']:.1f} pp** | "
          + (f"{sp_new['sd_pp']:.1f} pp" if sp_new["sd_pp"] == sp_new["sd_pp"] else "—")
          + f" | {100*sp_new['worst']:.1f}% | {100*sp_new['mean']:.1f}% |",
          "", f"* {c1['text']}",
          "* ⚠️ 预注册里就写明：n=3 的 sd 只有 **2 个自由度**，极差/sd 的估计本身极不稳；"
          "要声称「方差显著下降」需要 n≥5（≈35 h GPU）。**C1 不参与判定。**",
          "* ⚠️ 另一个必须并列的读数：新配方的**均值**是否也保住了。若极差收窄是因为三个 seed 一起塌到低位，"
          "那不是改进（这正是 7B 的 M2 要防的事，在 7C 这里表现为均值对照）。", ""]

    L += ["## 三、C2 · 使命门（与档 3r 完全同一条）", "", f"* {c2['text']}", ""]
    if len(have) >= 2:
        L += ["* 两两 Fisher（放宽口径，n=80/seed）："]
        for i, a in enumerate(have):
            for b in have[i + 1:]:
                p = fisher_two_sided(rel[a]["k"], rel[a]["n"], rel[b]["k"], rel[b]["n"])
                L.append(f"  * seed{a}（{pct(rel[a]['k'], rel[a]['n'])}） vs seed{b}"
                         f"（{pct(rel[b]['k'], rel[b]['n'])}）：Δ={100*(rel[a]['k']/rel[a]['n'] - rel[b]['k']/rel[b]['n']):+.1f} pp，"
                         f"p={p:.4f}")
        L += ["* 与 batch8 同 seed 标签的对照（⚠️ 换 batch 后随机流全变，**seed 标签不控制任何东西**，"
              "这一列只是给人看的锚）："]
        for sd in have:
            if sd in B8_TEST:
                p = fisher_two_sided(rel[sd]["k"], rel[sd]["n"], B8_TEST[sd][0], B8_TEST[sd][1])
                L.append(f"  * seed{sd}：bs32 {pct(rel[sd]['k'], rel[sd]['n'])} vs batch8 "
                         f"{100*B8_TEST[sd][0]/B8_TEST[sd][1]:.1f}% ⇒ "
                         f"Δ={100*(rel[sd]['k']/rel[sd]['n'] - B8_TEST[sd][0]/B8_TEST[sd][1]):+.1f} pp，p={p:.4f}")
    L.append("")

    L += ["## 四、C3 · 早筛规则的**前瞻**验证（免费，不额外花 GPU）", "",
          f"* 被检验的规则（出处 `runs/_diag/seedcurve_sign_strict.md` 第四节，**回溯**得出）："
          f"在 epoch ≈ {SCREEN_EPOCH}（= 全程 45.5%）那格，若 val 放宽 rate ≥ T（T ∈ "
          f"({min(SCREEN_THRS):.2f}, {max(SCREEN_THRS):.2f}]）就留、否则杀。",
          f"* 回溯表在 batch8 三 seed 上完美分类（TP=2、FN=0、FP=0、TN=1）；"
          f"这一节要问的是：**换到新配方的三个 seed 上还成立吗**。", ""]
    runs_cells, tests = {}, {}
    for sd in have:
        rp = MG / "runs" / job_of(sd)
        if not rp.is_dir():
            continue
        spe, src = EC.steps_per_epoch(rp)
        runs_cells[f"bs32_seed{sd}"] = read_cells(rp, "sweep_rev", "rev", spe)
        tests[f"bs32_seed{sd}"] = (rel[sd]["k"], rel[sd]["n"])
        sstep = screen_step_for_epoch(spe, SCREEN_EPOCH, SAVE_FREQ)
        cell = next((c for c in runs_cells[f"bs32_seed{sd}"] if c["step"] == sstep), None)
        L.append(f"* `seed{sd}`：steps/epoch={spe}（{src}）⇒ epoch {SCREEN_EPOCH} 对应 step **{sstep}**；"
                 + (f"该格 val 放宽 = {cell['k_relaxed']}/{cell['n']} = {100*cell['p_relaxed']:.0f}%，"
                    f"TEST 放宽 = {pct(*tests[f'bs32_seed{sd}'])}"
                    if cell and cell["k_relaxed"] is not None else "该格无放宽读数"))
    bt = screen_backtest(runs_cells, tests, C2_GATE, SCREEN_THRS, SCREEN_EPOCH - 0.02, "relaxed",
                         total_steps=STEPS)
    if bt:
        L += ["", "| step | epoch | 阈值 T | 留 | TP | FN（白烧） | FP（漏网） | TN | 完美分类 |",
              "|---:|---:|---:|:--|---:|---:|---:|---:|:--|"]
        for r in bt:
            L.append(f"| {r['step']} | {r['epoch']} | {r['thr']:.2f} | {','.join(r['kept']) or '（全杀）'} | "
                     f"{r['TP']} | {r['FN']} | {r['FP']} | {r['TN']} | {'✅' if r['perfect'] else ''} |")
        perf = [r for r in bt if r["perfect"]]
        n_runs = len(runs_cells)
        L += ["", f"* 前瞻结果：能完美分类的 (step,T) = **{len(perf)}/{len(bt)}**"
              + (f"；最早 = step {min(r['step'] for r in perf)}" if perf else ""),
              f"* 判读：{'✅ 回溯规则在新数据上站得住 ⇒ 早筛协议可以写进方案' if perf else '❌ 回溯规则在新数据上失效 ⇒ 早筛协议不成立，档 3r 补充第四节的那张表只能当历史读数'}",
              f"* ⚠️ 样本只有 {n_runs} 个 run、且新旧配方的筛点是各自的 epoch 网格 ⇒ 这条也只能读方向。", ""]
    else:
        L += ["* 扫描格不齐 ⇒ C3 跳过（不影响 C1/C2）", ""]

    L += ["## 五、结论与下一步", "",
          f"* **C2（唯一参与判定的门）**：{'✅ PASS' if c2['ok'] else ('❌ FAIL' if c2['ok'] is False else '⚠️ 读数不足')}"
          f" —— {c2['text']}",
          f"* C1（方向性）：{c1['text']}",
          "* 若 C2 ✅：档 3r 的 FAIL 被推翻，**seed 稳健性缺口关闭** ⇒ 使命证据链补齐"
          "（正向未见 63.7~75%、反向放宽 ≥50% 对全部训练 seed 成立、专家上界严格 70%/放宽 100%、实时 28 ms）。"
          "下一步回用户阶梯：阶梯 4（标准 chunk 执行）已关门、阶梯 5（Harness）已关门为「不是成功率杠杆」⇒ "
          "剩下的真杠杆是阶梯 6「纠正数据」，其入口条件见 `runs/S5_1_SUPPLEMENT.md` 第八节的三条。",
          "* 若 C2 ❌：记录「batch 抬到 32 仍不足」，处方转 `runs/S7_PREREG.md` §2 的备择假设 "
          "A1（数据顺序）/ A3（简并解族太宽 ⇒ 加数据或加 epoch）；**不再烧 batch**。",
          "* 本档不改任何历史判定文件（档 3r 的 `runs/S3R_VERDICT.md` 保持原样），只新增本文件。", "",
          "## 六、复现", "", "```bash",
          "bash code/chain_s7c.sh          # 等 s7b.done + 预注册闸（M1∧M2∧M3）才发车；seed 1000/3000",
          "$MG_PY code/mg_verdict_s7c.py --selftest",
          "$MG_PY code/mg_verdict_s7c.py > runs/S7C_VERDICT.md", "```", ""]
    print("\n".join(L))
    return 0


# ─────────────────────────── 自测 ───────────────────────────
def selftest() -> int:
    ok = bad = 0

    def chk(name, cond, detail=""):
        nonlocal ok, bad
        if cond:
            ok += 1
        else:
            bad += 1
            print(f"  ✗ {name} {detail}")

    # --- spread ---
    s3 = spread([0.412, 0.688, 0.800])
    chk("batch8 三 seed 极差 = 38.8 pp（历史真值锚）", abs(s3["range_pp"] - 38.8) < 0.05, f"{s3['range_pp']}")
    chk("batch8 sd ≈ 19.5 pp", 18.0 < s3["sd_pp"] < 21.0, f"{s3['sd_pp']}")
    chk("batch8 最差 = 0.412", abs(s3["worst"] - 0.412) < 1e-9)
    chk("batch8 最好 = 0.800", abs(s3["best"] - 0.800) < 1e-9)
    chk("batch8 均值 = 0.6333", abs(s3["mean"] - (0.412 + 0.688 + 0.800) / 3) < 1e-9)
    s1 = spread([0.5])
    chk("单点：极差 0、sd = nan（不静默给 0）", s1["range_pp"] == 0.0 and s1["sd_pp"] != s1["sd_pp"])
    s0 = spread([])
    chk("空表：n=0 且全 nan", s0["n"] == 0 and s0["range_pp"] != s0["range_pp"])
    chk("全同 ⇒ 极差 0、sd 0", spread([0.6, 0.6, 0.6])["range_pp"] == 0.0
        and spread([0.6, 0.6, 0.6])["sd_pp"] == 0.0)
    chk("两点也算 sd（自由度 1）", spread([0.4, 0.6])["sd_pp"] == round(100 * statistics.stdev([0.4, 0.6]), 1))

    # --- c1_verdict：只读方向、不是门 ---
    chk("极差 20 < 38.8 ⇒ ok=True", c1_verdict(20.0)["ok"] is True)
    chk("极差 38.8 ⇒ ok=False（严格小于才算收窄）", c1_verdict(38.8)["ok"] is False)
    chk("极差 50 ⇒ ok=False", c1_verdict(50.0)["ok"] is False)
    chk("nan ⇒ ok=None", c1_verdict(float("nan"))["ok"] is None)
    chk("文案写明「不作为门」", "不作为门" in c1_verdict(20.0)["text"])
    chk("文案带两个数字", "20.0" in c1_verdict(20.0)["text"] and "38.8" in c1_verdict(20.0)["text"])

    # --- c2_verdict：门 = 最差 seed ≥ 50% ---
    chk("40/80 = 50.0% ⇒ 过（含等号）", c2_verdict(40, 80, 1000)["ok"] is True)
    chk("39/80 = 48.75% ⇒ 不过", c2_verdict(39, 80, 1000)["ok"] is False)
    chk("33/80 = 41.2% ⇒ 不过（batch8-seed2000 的真值）", c2_verdict(33, 80, 2000)["ok"] is False)
    chk("64/80 = 80.0% ⇒ 过", c2_verdict(64, 80, 3000)["ok"] is True)
    chk("n=0 ⇒ ok=None 不崩", c2_verdict(0, 0, 0)["ok"] is None)
    chk("文案含 Wilson CI", "Wilson" in c2_verdict(40, 80, 1000)["text"])
    chk("文案含最差 seed 标签", "1000" in c2_verdict(40, 80, 1000)["text"])

    # --- screen_step_for_epoch：bs32 下 epoch 1.72 ⇒ step 2500 ---
    chk("bs32（spe=1450.8125）epoch1.72 ⇒ step 2500",
        screen_step_for_epoch(1450.8125, 1.72, 500) == 2500)
    chk("bs8（spe=5803.25）epoch1.72 ⇒ step 10000（历史真值）",
        screen_step_for_epoch(5803.25, 1.72, 2000) == 10000)
    chk("bs16（spe=2901.625）epoch1.72 ⇒ step 5000",
        screen_step_for_epoch(2901.625, 1.72, 1000) == 5000)
    chk("结果是 save_freq 的整数倍",
        screen_step_for_epoch(1450.8125, 1.72, 500) % 500 == 0)
    chk("epoch 0 ⇒ step 0", screen_step_for_epoch(1450.8125, 0.0, 500) == 0)

    # --- 目录/常数对账 ---
    chk("7B 的 job 名与 chain_s7b.sh 一致", job_of(2000) == "pi05_mix60f120r_s7b_bs32_seed2000")
    chk("7C 的 job 名同构", job_of(1000) == "pi05_mix60f120r_s7b_bs32_seed1000"
        and job_of(3000) == "pi05_mix60f120r_s7b_bs32_seed3000")
    chk("TEST 目录 4 个/seed（4×20=80 局）", len(test_dirs(1000)) == 4)
    chk("TEST 目录命名与 chain_s7b.sh 的 run_eval 一致",
        test_dirs(3000)[0] == "s7b_bs32_seed3000_rev_test_rand20_k10"
        and test_dirs(3000)[3] == "s7b_bs32_seed3000_rev_test_rand20_k10_rep4")
    chk("护栏目录命名一致", fwd_dirs(1000) == ["s7b_bs32_seed1000_fwd_test_rand20_k10"])
    chk("C2 门 = 0.50（与档 3r 同一条）", C2_GATE == 0.50)
    chk("C1 对照极差 = 38.8 pp（出自 runs/S3R_VERDICT.md）", B8_RANGE_PP == 38.8)
    chk("batch8 TEST 真值与 S3R_VERDICT 一致",
        B8_TEST == {1000: (55, 80), 2000: (33, 80), 3000: (64, 80)})
    chk("batch8 极差复算 = 38.8", abs(spread([v[0] / v[1] for v in B8_TEST.values()])["range_pp"] - 38.8) < 0.05)
    chk("等 epoch 步数是 save_freq 整数倍（坑 33/38）", STEPS % SAVE_FREQ == 0 and STEPS == 5500)
    chk("正向基线 = 193/300（档 3 三 seed 合并）", FWD_BASELINE == (193, 300))
    chk("筛点 epoch = 1.72（回溯表里窗口≥3格的最早点）", abs(SCREEN_EPOCH - 1.72) < 1e-9)
    chk("SEEDS 含 7B 那个 seed（2000 先跑）", SEEDS[0] == 2000 and sorted(SEEDS) == [1000, 2000, 3000])

    # --- 与 mg_seedcurve 的同源性（坑 54/61：不许两套实现各说各话）---
    chk("fisher2 与 fisher_two_sided 同源（签名不同，换算 (a,a+b,c,c+d)）",
        all(abs(fisher2(a, b, c, d) - fisher_two_sided(a, a + b, c, c + d)) < 1e-9
            for (a, b, c, d) in [(40, 40, 33, 47), (64, 16, 55, 25), (30, 50, 30, 50)]))
    chk("sign_test_exact 复用同一实现（9胜0负 = 0.00390625）", abs(sign_test_exact(9, 0) - 2 / 512) < 1e-12)
    chk("kof/read_cells 复用 mg_seedcurve（不重实现读盘）",
        kof({"k": 3, "k_relaxed": 5}, "strict") == 3 and kof({"k": 3, "k_relaxed": 5}, "relaxed") == 5)

    print(f"[selftest] {ok} passed, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
