#!/usr/bin/env python
"""档 7F / 7G 判定汇编：7B 失败的归因（F1~F4）+「缩短 epoch 预算」的前瞻验证（7G）。

**判据全部出自 `runs/S7F_PREREG.md`（2026-10-04 10:22 落盘，早于本档任何读数）。**

两个模式：
  `--mode f` -> `runs/S7F_DIAG.md`
    F1/F2（**零训练**）：三个 batch8 seed 的 `checkpoints/018000`（epoch 3.102 = 两条曲线的 val 峰）
      在 TEST 上的读数，与各自末点（022000）配对。决策规则（预注册 §3）：
      `MIN3102 = min(三个 seed 的反向放宽) ≥ 40/80` ⇒ **触发 7G**（并输出机器可读行 `7G_TRIGGER=YES`）；
      否则 `7G_TRIGGER=NO`（改跑 F4）。
      ⚠️ 这是**回溯**读数（检查点由 val 挑）⇒ 只用于决定「22.4 h 值不值得花」，
      **不是**使命门通过的证据（坑 27/42），也不改档 3r 的 FAIL 判定。
    F3（bs8 / 5500 步 / lr1e-4）：与 7B **同更新数**、不同 batch 与 epoch ⇒ 只用于**排除** H-B（步数）。
    F4（bs32 / 5500 步 / **lr1e-4**）：与 7B **唯一差 lr** ⇒ 判 H-A。仅在 7G 未触发时才有产物。
  `--mode g` -> `runs/S7G_VERDICT.md`
    G1（主门，与档 3r/7C 完全同一条）：**新 seed 4000/5000/6000**、bs8、**18000 步 = 3.102 ep**，
      最差 seed 的 TEST 反向放宽 ≥ 50%；G2（护栏）：三个 seed 的正向掉幅都 ≤15 pp；
    G3（副，只读方向）：极差 vs 38.8 pp（n=3、2 自由度 ⇒ **不作为门**）。

⚠️ 出身核对是本工具的重点（坑 38/42）：F1/F2 读的是**非 last** 的检查点，
   所以逐条断言 `policy_ckpt` 真的以 `checkpoints/018000/pretrained_model` 结尾、
   `task_mode` / `n_action_steps` / seed 窗口 / 局数全对；有一条不对就在报告里标 🚫 并让退出码非 0。

用法：
    $MG_PY code/mg_verdict_s7f.py --selftest
    $MG_PY code/mg_verdict_s7f.py --mode f > runs/S7F_DIAG.md
    $MG_PY code/mg_verdict_s7f.py --mode g > runs/S7G_VERDICT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG = HERE.parent
RUNS = MG / "runs"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_verdict_s2 import fisher_two_sided  # noqa: E402
from mg_verdict_s2f import ci, collect, load, pct  # noqa: E402
from mg_verdict_s7c import spread  # noqa: E402  同一个量不重写第二遍（坑 54）

# ── 预注册常数（出处 runs/S7F_PREREG.md，改这里等于改判据 ⇒ 必须先改预注册）──────
EPOCH_STEP = 18000                 # F1/F2 读的检查点 = epoch 3.102
B8 = {1000: "pi05_mix60f120r_s2e", 2000: "pi05_mix60f120r_s3r_seed2000",
      3000: "pi05_mix60f120r_s3r_seed3000"}
B8_TEST_REV = {1000: (55, 80), 2000: (33, 80), 3000: (64, 80)}   # 末点 022000 的既有读数
B8_TEST_FWD = {1000: (15, 20), 2000: (4, 20), 3000: (13, 20)}
S7B_REV = (13, 80)                 # 档 7B 的 TEST 反向放宽（runs/S7_VERDICT.md）
S7B_FWD = (1, 20)
B8_RANGE_PP = 38.8                 # 档 3r 三 seed 的极差（C1/G3 的对照）
FWD_BASELINE = (193, 300)          # 档 3 三 seed 合并的正向未见
FWD_DROP_PP = 15.0
TRIGGER_K, TRIGGER_N = 40, 80      # MIN3102 ≥ 40/80 = 50% ⇒ 触发 7G
DIFF_BAND_PP = 11.0                # ±2σ（n=80、p≈0.5 ⇒ 1σ≈5.6 pp）= 「无差别」带
DIFF_MIN_PP = 12.0                 # 「有差别」的下限（预注册 §3 的 F3/F4 判读表）
F3_JOB = "pi05_mix60f120r_s7f_bs8_5500_seed2000"
F4_JOB = "pi05_mix60f120r_s7f_bs32_lr1e4_seed2000"
G_SEEDS = [4000, 5000, 6000]
G_STEPS = 18000
K_EVAL = 10
REV_SEED0 = 7000
FWD_SEED0 = 2000
REPS = 4
EPS = 20


def rev_dirs(prefix: str) -> list[str]:
    return [f"{prefix}_rev_test_rand20_k10" + ("" if i == 1 else f"_rep{i}") for i in range(1, REPS + 1)]


def fwd_dirs(prefix: str) -> list[str]:
    return [f"{prefix}_fwd_test_rand20_k10"]


def f_prefix(seed: int) -> str:
    return f"s7f_seed{seed}_ep3102"


def g_prefix(seed: int) -> str:
    return f"s7g_seed{seed}"


# ─────────────────────────── 纯函数 ───────────────────────────
def trigger_of(min_k: int, min_n: int) -> dict:
    """预注册 §3 的 7G 触发规则：MIN3102 ≥ 40/80 ⇒ YES。缺读数 ⇒ None（不许静默当不触发）。"""
    if min_n <= 0:
        return {"yes": None, "text": "读数不足，无法算 MIN3102"}
    yes = (min_k / min_n) >= TRIGGER_K / TRIGGER_N - 1e-9
    return {"yes": yes, "rate": min_k / min_n,
            "text": f"MIN3102 = **{min_k}/{min_n} = {100*min_k/min_n:.1f}%**（Wilson {ci(min_k, min_n)}）"
                    f" ⇒ {'≥' if yes else '<'} 触发门 {TRIGGER_K}/{TRIGGER_N} = 50%"
                    f" ⇒ **{'触发 7G' if yes else '不触发 7G（改跑 F4）'}**"}


def worst_cell(rates: list[tuple[int, float]], rev: dict) -> tuple[int, int, int] | None:
    """从 `[(seed, rate), …]` 里取最差的一格，返回 `(seed, k, n)`；空表 ⇒ None。

    ⚠️ 元素是**元组**：`min(rates, key=lambda t: t[1])` 给的是 `(seed, rate)`，
    直接拿它去下标 `rev` 就是 `KeyError: (2000, 0.4375)` —— 2026-10-04 11:59 在 F1/F2 的
    早期触发读数上真吃到了（stdout 空、rc=1）。所以这段必须是个**有自测的纯函数**，
    不许再当 f-string 里的一次性表达式写（坑 65 的家族：判据代码里不留没被测过的表达式）。
    """
    if not rates:
        return None
    sd = min(rates, key=lambda t: t[1])[0]
    return sd, int(rev[sd]["k"]), int(rev[sd]["n"])


def diff_branch(k: int, n: int, ref_k: int, ref_n: int, arm: str) -> dict:
    """F3/F4 的三分支判读（阈值 DIFF_BAND_PP / DIFF_MIN_PP 出自预注册 §3 的表）。"""
    if n <= 0:
        return {"code": "NA", "text": "无读数"}
    d = 100 * (k / n - ref_k / ref_n)
    if abs(d) <= DIFF_BAND_PP:
        code = "SAME"
        txt = (f"|Δ| = {abs(d):.1f} pp ≤ {DIFF_BAND_PP:.0f} pp（2σ）⇒ **无差别**"
               + ("：H-B 成立（7B 的塌陷主要由更新步数少 4× 解释）" if arm == "F3"
                  else "：lr 不是 7B 塌陷的主因"))
    elif d <= -DIFF_MIN_PP:
        code = "LOWER"
        txt = (f"低 {abs(d):.1f} pp ≥ {DIFF_MIN_PP:.0f} pp ⇒ bs8@5500 更差 ⇒ 步数不是塌陷的原因，指向 H-A/H-C"
               if arm == "F3" else
               f"低 {abs(d):.1f} pp ⇒ lr 更小反而更差（欠拟合）⇒ 指向 H-B")
    else:
        code = "HIGHER"
        txt = (f"高 {d:.1f} pp ≥ {DIFF_MIN_PP:.0f} pp ⇒ **H-C**（大 batch 本身有害）"
               if arm == "F3" else
               f"高 {d:.1f} pp ≥ {DIFF_MIN_PP:.0f} pp ⇒ **H-A 成立**（lr=2e-4 是主因，sqrt 缩放过头）")
    return {"code": code, "delta_pp": d, "text": f"{arm} = {k}/{n} = {100*k/n:.1f}% vs 7B "
                                                 f"{ref_k}/{ref_n} = {100*ref_k/ref_n:.1f}% ⇒ {txt}"}


def prov(dirs: list[str], ck_suffix: str, mode: str, seed0: int, eps: int = EPS,
         k_eval: int = K_EVAL) -> list[str]:
    """出身核对：ckpt 尾串 / task_mode / K / seed 窗口 / 局数。返回问题清单（空 = 全对）。"""
    bad = []
    for i, d in enumerate(dirs):
        j = load(d)
        if j is None:
            bad.append(f"{d}: 产物不在")
            continue
        if "_error" in j:
            bad.append(f"{d}: {j['_error']}")
            continue
        ck = str(j.get("policy_ckpt", "?"))
        if not ck.endswith(ck_suffix):
            bad.append(f"{d}: policy_ckpt 尾巴是 …{ck[-46:]}，期望 …{ck_suffix}（坑 38/42：读错权重）")
        if j.get("task_mode") != mode:
            bad.append(f"{d}: task_mode={j.get('task_mode')} ≠ {mode}")
        if int(j.get("n_action_steps", -1)) != k_eval:
            bad.append(f"{d}: K={j.get('n_action_steps')} ≠ {k_eval}")
        if int(j.get("seed", -1)) != seed0:
            bad.append(f"{d}: seed={j.get('seed')} ≠ {seed0}（seed 窗口变了就不可配对）")
        if int(j.get("episodes", 0)) != eps:
            bad.append(f"{d}: episodes={j.get('episodes')} ≠ {eps}")
    return bad


# ─────────────────────────── mode f ───────────────────────────
def report_f() -> int:
    seeds = sorted(B8)
    rev, fwd, strict = {}, {}, {}
    for sd in seeds:
        rev[sd] = collect(rev_dirs(f_prefix(sd)), "n_success_relaxed", "pc_success_relaxed")
        strict[sd] = collect(rev_dirs(f_prefix(sd)), "n_success", "pc_success")
        fwd[sd] = collect(fwd_dirs(f_prefix(sd)), "n_success_relaxed", "pc_success_relaxed")
    ready = [sd for sd in seeds if rev[sd]["n"] == REPS * EPS]
    f3 = collect(rev_dirs("s7f_bs8_5500_seed2000"), "n_success_relaxed", "pc_success_relaxed")
    f3f = collect(fwd_dirs("s7f_bs8_5500_seed2000"), "n_success_relaxed", "pc_success_relaxed")
    f4 = collect(rev_dirs("s7f_bs32_lr1e4_seed2000"), "n_success_relaxed", "pc_success_relaxed")
    f4f = collect(fwd_dirs("s7f_bs32_lr1e4_seed2000"), "n_success_relaxed", "pc_success_relaxed")

    if not ready and f3["n"] == 0 and f4["n"] == 0:
        print("# 档 7F 诊断：**读数不齐，无法判定**\n")
        print(f"* 已齐的 seed（反向 4×20）：{ready or '无'}；缺：{[s for s in seeds if s not in ready]}")
        print(f"\n（生成时间 {datetime.now():%F %T}；补齐后重跑 `$MG_PY code/mg_verdict_s7f.py --mode f`）")
        return 2

    L = ["# 档 7F 诊断：7B 为什么崩 + 「缩短 epoch 预算」值不值得花 22.4 h", "",
         f"* 生成时间：{datetime.now():%F %T}（`code/mg_verdict_s7f.py --mode f`）",
         "* 预注册出处：`runs/S7F_PREREG.md`（2026-10-04 10:22 落盘，**早于本档任何读数**）",
         f"* 上游：`runs/S7_VERDICT.md` 判「不采信（配方退化）」；`runs/s7c.SKIPPED` 是闸按预注册正确拦下 7C",
         f"* 已齐读数的 seed：**{ready or '无'}**（需要 {seeds} 三个）", "",
         "## 一、F1/F2 · epoch 3.102 的检查点在 TEST 上（**回溯诊断**，零训练）", "",
         "| 训练 seed | 检查点 | 反向放宽（主口径） | Wilson | 严格 | 侧躺 | 末点(022000) 放宽 | Δ(pp) | Fisher p | 正向 20 局 | 末点正向 |",
         "|---:|:--|---:|:--|---:|---:|---:|---:|---:|---:|---:|"]
    prov_bad = []
    for sd in seeds:
        if rev[sd]["n"] == 0:
            L.append(f"| {sd} | `018000` | — | — | — | — | "
                     f"{pct(*B8_TEST_REV[sd])} | — | — | — | {pct(*B8_TEST_FWD[sd])} |")
            continue
        d = 100 * (rev[sd]["k"] / rev[sd]["n"] - B8_TEST_REV[sd][0] / B8_TEST_REV[sd][1])
        p = fisher_two_sided(rev[sd]["k"], rev[sd]["n"], B8_TEST_REV[sd][0], B8_TEST_REV[sd][1])
        L.append(f"| {sd} | `{B8[sd]}/checkpoints/018000` | **{rev[sd]['k']}/{rev[sd]['n']} = "
                 f"{pct(rev[sd]['k'], rev[sd]['n'])}** | {ci(rev[sd]['k'], rev[sd]['n'])} | "
                 f"{strict[sd]['k']}/{strict[sd]['n']} = {pct(strict[sd]['k'], strict[sd]['n'])} | "
                 f"{rev[sd]['tipped']} | {B8_TEST_REV[sd][0]}/{B8_TEST_REV[sd][1]} = "
                 f"{pct(*B8_TEST_REV[sd])} | {d:+.1f} | {p:.4f} | "
                 f"{fwd[sd]['k']}/{fwd[sd]['n']} = {pct(fwd[sd]['k'], fwd[sd]['n'])} | "
                 f"{pct(*B8_TEST_FWD[sd])} |")
        prov_bad += prov(rev_dirs(f_prefix(sd)), f"checkpoints/{EPOCH_STEP:06d}/pretrained_model",
                         "reverse", REV_SEED0)
        prov_bad += prov(fwd_dirs(f_prefix(sd)), f"checkpoints/{EPOCH_STEP:06d}/pretrained_model",
                         "forward", FWD_SEED0)
    rates = [(sd, rev[sd]["k"] / rev[sd]["n"]) for sd in ready]
    L += ["", f"* 缺产物：{[d for sd in seeds for d in (rev[sd]['missing'] + fwd[sd]['missing'])] or '无'}；"
              f"缺放宽字段：{[x for sd in seeds for x in rev[sd]['nofield']] or '无'}；"
              f"不变量（严格 ⊆ 放宽）被破坏：{[x for sd in seeds for x in rev[sd]['broken']] or '无'}", ""]

    trig = {"yes": None, "text": "三个 seed 未齐 ⇒ MIN3102 算不出来"}
    min_txt = "NA"
    if len(ready) == len(seeds):
        wsd, mk, mn = worst_cell(rates, rev)
        trig = trigger_of(mk, mn)
        min_txt = f"{mk}/{mn}"
        L += [f"* 最差的那个 seed = **{wsd}**（{pct(mk, mn)}）"]
    L += ["", "## 二、7G 触发判定（预注册 §3 的决策规则）", "", f"* {trig['text']}",
          f"* 机器可读行（`code/chain_s7g.sh` 就 grep 这一行）：",
          f"`7G_TRIGGER={'YES' if trig['yes'] else ('NO' if trig['yes'] is False else 'UNKNOWN')}`"
          f" MIN3102={min_txt}",
          "",
          "* ⚠️ 这是**回溯**读数：epoch 3.102 是看着 seed1000/2000 的 val 峰挑的（预注册 §1.2），"
          "所以 `7G_TRIGGER=YES` **不等于**使命门通过 —— 它只说明「花 22.4 h 做新 seed 的前瞻验证」有指望。",
          "* ⚠️ 档 3r 的 `runs/S3R_VERDICT.md` FAIL 判定**原样保留**；只有 7G 的 G1 在新 seed 上过门才能推翻它。", ""]

    L += ["## 三、F3/F4 · 归因对照臂（预注册 §2 的三个候选解释）", ""]
    if f3["n"]:
        b3 = diff_branch(f3["k"], f3["n"], *S7B_REV, "F3")
        L += [f"* **F3**（bs8 / 5500 步 = 0.948 ep / lr 1e-4 / seed2000，与 7B **同更新数**）：{b3['text']}",
              f"  * 正向护栏：{f3f['k']}/{f3f['n']} = {pct(f3f['k'], f3f['n'])}"
              f"（7B 是 {pct(*S7B_FWD)}、batch8-seed2000 末点是 {pct(*B8_TEST_FWD[2000])}）",
              f"  * ⇒ 命中分支 **{b3['code']}**"]
        prov_bad += prov(rev_dirs("s7f_bs8_5500_seed2000"), "checkpoints/005500/pretrained_model",
                         "reverse", REV_SEED0)
    else:
        L += ["* **F3**：还没有读数"]
    if f4["n"]:
        b4 = diff_branch(f4["k"], f4["n"], *S7B_REV, "F4")
        L += ["", f"* **F4**（bs32 / 5500 步 / **lr 1e-4** / seed2000，与 7B **唯一差 lr**）：{b4['text']}",
              f"  * 正向护栏：{f4f['k']}/{f4f['n']} = {pct(f4f['k'], f4f['n'])}",
              f"  * ⇒ 命中分支 **{b4['code']}**"]
        prov_bad += prov(rev_dirs("s7f_bs32_lr1e4_seed2000"), "checkpoints/005500/pretrained_model",
                         "reverse", REV_SEED0)
    else:
        L += ["", "* **F4**：还没有读数（预注册：仅当 7G 未触发时才跑）"]
    L += [""]

    L += ["## 四、归因小结（H-A / H-B / H-C 现在各是什么状态）", "",
          "| 解释 | 判别读数 | 状态 |", "|:--|:--|:--|"]
    sa = "未测（F4 未跑）" if not f4["n"] else diff_branch(f4["k"], f4["n"], *S7B_REV, "F4")["code"]
    sb = "未测（F3 未跑）" if not f3["n"] else diff_branch(f3["k"], f3["n"], *S7B_REV, "F3")["code"]
    L += [f"| **H-A** lr=2e-4 太大 | F4（与 7B 唯一差 lr） | `{sa}` |",
          f"| **H-B** 更新步数少 4× | F3（与 7B 同更新数） | `{sb}` |",
          "| **H-C** 大 batch 本身有害（噪声是正则） | F3 与 F4 都排除不了时才成立 | 见上两行 |", "",
          "* 判读规则出自预注册 §3 的表；`SAME` = |Δ|≤11 pp（2σ）、`HIGHER`/`LOWER` = |Δ|≥12 pp。",
          "* ⚠️ F3 与 7B **同时**差 batch 和 epoch ⇒ 它只能排除 H-B，**不能**给 batch 的效应量（坑 57）。",
          "* ⚠️ 无论归因落到哪一条，都**不许**说「bs32 比 bs8 差」：那是 n=1 的配方高低比较（坑 57）。", ""]

    L += ["## 五、出身核对", ""]
    if prov_bad:
        L += [f"* 🚫 有 **{len(prov_bad)}** 条不对 ⇒ 本诊断**不采信**："] + [f"  * {b}" for b in prov_bad]
    else:
        L += ["* ✅ 所有读数的 ckpt 尾串 / task_mode / K / seed 窗口 / 局数都对得上预注册"]
    L += ["", "## 六、复现", "", "```bash",
          "bash code/chain_s7f.sh                 # F1 -> F2 -> F3 -> 本诊断（7G 未触发时再跑 F4）",
          "$MG_PY code/mg_verdict_s7f.py --selftest",
          "$MG_PY code/mg_verdict_s7f.py --mode f > runs/S7F_DIAG.md", "```", ""]
    print("\n".join(L))
    return 3 if prov_bad else 0


# ─────────────────────────── mode g ───────────────────────────
def report_g() -> int:
    rev, fwd, strict = {}, {}, {}
    for sd in G_SEEDS:
        rev[sd] = collect(rev_dirs(g_prefix(sd)), "n_success_relaxed", "pc_success_relaxed")
        strict[sd] = collect(rev_dirs(g_prefix(sd)), "n_success", "pc_success")
        fwd[sd] = collect(fwd_dirs(g_prefix(sd)), "n_success_relaxed", "pc_success_relaxed")
    ready = [sd for sd in G_SEEDS if rev[sd]["n"] == REPS * EPS]
    if not ready:
        print("# 档 7G 判定：**读数不齐，无法判定**\n")
        print(f"* 已齐的训练 seed：{ready or '无'}；需要 {G_SEEDS}（bs8 / 18000 步 = 3.102 ep / 新 seed）")
        print(f"\n（生成时间 {datetime.now():%F %T}）")
        return 2

    rates = [rev[sd]["k"] / rev[sd]["n"] for sd in ready]
    worst = min(ready, key=lambda s: rev[s]["k"] / rev[s]["n"])
    g1 = rev[worst]["k"] / rev[worst]["n"] >= 0.50 - 1e-9
    drops = {}
    for sd in ready:
        base = FWD_BASELINE[0] / FWD_BASELINE[1]
        drops[sd] = 100 * (base - rev and 0) if False else 100 * (base - (fwd[sd]["k"] / fwd[sd]["n"]
                                                                          if fwd[sd]["n"] else float("nan")))
    g2 = all(d <= FWD_DROP_PP for d in drops.values() if d == d)
    sp = spread(rates)
    prov_bad = []
    for sd in ready:
        prov_bad += prov(rev_dirs(g_prefix(sd)), f"checkpoints/{G_STEPS:06d}/pretrained_model",
                         "reverse", REV_SEED0)
        prov_bad += prov(fwd_dirs(g_prefix(sd)), f"checkpoints/{G_STEPS:06d}/pretrained_model",
                         "forward", FWD_SEED0)

    L = ["# 档 7G 判定：把 epoch 预算固定在 3.102、用**新 seed** 前瞻验证", "",
         f"* 生成时间：{datetime.now():%F %T}（`code/mg_verdict_s7f.py --mode g`）",
         "* 预注册出处：`runs/S7F_PREREG.md` §3 格 7G（2026-10-04 10:22 落盘，**早于任何 7G 读数**）",
         f"* 配方：bs8 / **{G_STEPS} 步 = 3.102 ep** / lr 1e-4 / save_freq 2000 / 新 seed **{G_SEEDS}**，"
         f"其余逐项照抄档 3r；关门读数一律 `last`（= {G_STEPS:06d}），不做 val 选点（坑 27/38/42）",
         f"* 已齐读数的训练 seed：**{ready}**" + (f"；缺 {[s for s in G_SEEDS if s not in ready]}"
                                                  if len(ready) < len(G_SEEDS) else "（三个齐）"),
         f"* 对照（**既有** batch8 @3.79 ep，出处 `runs/S3R_VERDICT.md`）：seed1000 68.8% / seed2000 "
         f"**41.2%（打穿门 ⇒ 档 3r FAIL）** / seed3000 80.0%", "",
         "## 一、TEST 关门读数（反向 4×20 = 80 局/seed，K=10，seed 窗口 7000..7019）", "",
         "| 训练 seed | run | 严格 | **放宽 R（主口径）** | Wilson 95% | 侧躺 | 正向护栏 | 掉幅 vs 64.3% |",
         "|---:|:--|---:|---:|:--|---:|---:|---:|"]
    for sd in ready:
        d = drops[sd]
        L.append(f"| {sd} | `pi05_mix60f120r_s7g_seed{sd}` | "
                 f"{strict[sd]['k']}/{strict[sd]['n']} = {pct(strict[sd]['k'], strict[sd]['n'])} | "
                 f"**{rev[sd]['k']}/{rev[sd]['n']} = {pct(rev[sd]['k'], rev[sd]['n'])}** | "
                 f"{ci(rev[sd]['k'], rev[sd]['n'])} | {rev[sd]['tipped']} | "
                 f"{fwd[sd]['k']}/{fwd[sd]['n']} = {pct(fwd[sd]['k'], fwd[sd]['n'])} | "
                 f"{d:+.1f} pp {'✅' if d <= FWD_DROP_PP else '🚫'} |")
    L += ["", f"* 缺产物：{[d for sd in ready for d in rev[sd]['missing'] + fwd[sd]['missing']] or '无'}；"
              f"缺放宽字段：{[x for sd in ready for x in rev[sd]['nofield']] or '无'}；"
              f"不变量被破坏：{[x for sd in ready for x in rev[sd]['broken']] or '无'}", "",
          "## 二、判据", "",
          f"* **G1（主门，与档 3r/7C 完全同一条）**：最差 seed = **{worst}**，"
          f"{rev[worst]['k']}/{rev[worst]['n']} = {pct(rev[worst]['k'], rev[worst]['n'])}"
          f"（Wilson {ci(rev[worst]['k'], rev[worst]['n'])}）⇒ "
          f"**{'✅ PASS' if g1 else '❌ FAIL'}**（门 = 最差 seed 放宽 ≥ 50%）",
          f"`G1={'PASS' if g1 else 'FAIL'}`",
          f"* **G2（护栏）**：三个 seed 的正向掉幅 = "
          + ", ".join(f"seed{sd} {drops[sd]:+.1f} pp" for sd in ready)
          + f" ⇒ {'✅ 全部 ≤15 pp' if g2 else '🚫 有 seed 掉超 15 pp（拆东墙补西墙）'}",
          f"* **G3（副，只读方向）**：极差 **{sp['range_pp']:.1f} pp** vs batch8 的 {B8_RANGE_PP} pp、"
          f"sd {sp['sd_pp'] if sp['sd_pp'] == sp['sd_pp'] else '—'} pp、均值 {100*sp['mean']:.1f}% "
          f"⇒ {'收窄了' if sp['range_pp'] < B8_RANGE_PP else '没收窄'}"
          "（⚠️ n=3、2 个自由度 ⇒ **不作为门**；预注册 §4）", ""]
    if len(ready) >= 2:
        L += ["* 两两 Fisher（放宽口径，n=80/seed）："]
        for i, a in enumerate(ready):
            for b in ready[i + 1:]:
                p = fisher_two_sided(rev[a]["k"], rev[a]["n"], rev[b]["k"], rev[b]["n"])
                L.append(f"  * seed{a} vs seed{b}：Δ={100*(rev[a]['k']/rev[a]['n'] - rev[b]['k']/rev[b]['n']):+.1f} pp，p={p:.4f}")
        L += ["* 与**既有** batch8 @3.79 ep 的同门对照（⚠️ 不是配对设计：seed 不同、epoch 预算不同，"
              "这一列只给人看，不能当「3.102 优于 3.79」的证据 —— 那需要另一套 22.4 h）："]
        for sd in ready:
            for ref_sd, ref in B8_TEST_REV.items():
                pass
        for ref_sd, ref in sorted(B8_TEST_REV.items()):
            best = max(ready, key=lambda s: rev[s]["k"] / rev[s]["n"])
            p = fisher_two_sided(rev[best]["k"], rev[best]["n"], ref[0], ref[1])
            L.append(f"  * 7G 最好的 seed{best} vs batch8-seed{ref_sd}：p={p:.4f}")
        L.append("")

    L += ["## 三、结论与下一步", "",
          f"* **G1 = {'PASS' if g1 else 'FAIL'}**",
          "* 若 PASS：在「epoch 预算固定 3.102」这个**全局配方**下，三个**新** seed 的最差者也 ≥50% ⇒ "
          "档 3r 的 seed 稳健性缺口关闭、使命证据链补齐（正向未见 64.3%、反向放宽 ≥50% 对全部训练 seed 成立、"
          "专家上界严格 70%/放宽 100%、实时 28 ms）。⇒ 回用户阶梯第 6 步「纠正数据」，"
          "入口条件见 `runs/S5_1_SUPPLEMENT.md` §六 第 2 条（三条，缺一不可：片段按「所属局放宽成功」过滤 / "
          "认输局整段丢弃 / 先把认输延迟从 208 砍到 ≤25 步）。⚠️ 原写「§8」是引用走样（该文件只有七节，坑 55），2026-10-04 更正。",
          "* 若 FAIL：epoch 预算这条杠杆也死 ⇒ 与档 7B（batch）一起构成「配方侧两条杠杆都已试过且都不够」，"
          "⇒ 转档 8（纠正数据），**不再烧配方实验**。",
          "* ⚠️ 本判定**不改**任何历史文件：`runs/S3R_VERDICT.md` 的 FAIL 与 `runs/S7_VERDICT.md` 的"
          "「不采信」原样保留；G1=PASS 的含义是「存在一个通过使命门的配方」，不是「档 3r 当时判错了」。", ""]
    if prov_bad:
        L += [f"## 四、🚫 出身核对不过（{len(prov_bad)} 条）⇒ 本判定不采信", ""] + [f"* {b}" for b in prov_bad] + [""]
    else:
        L += ["## 四、出身核对", "", "* ✅ 所有读数的 ckpt 尾串（`checkpoints/018000/pretrained_model`）/ "
              "task_mode / K=10 / seed 窗口 / 局数 都对得上预注册", ""]
    print("\n".join(L))
    return 3 if prov_bad else 0


# ─────────────────────────── 自测 ───────────────────────────
def selftest() -> int:
    npass = nfail = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal npass, nfail
        if cond:
            npass += 1
        else:
            nfail += 1
            print(f"  [FAIL] {name}")

    chk("触发门 = 40/80 = 50%", abs(TRIGGER_K / TRIGGER_N - 0.50) < 1e-9)
    chk("40/80 触发", trigger_of(40, 80)["yes"] is True)
    chk("41/80 触发", trigger_of(41, 80)["yes"] is True)
    chk("39/80 不触发", trigger_of(39, 80)["yes"] is False)
    chk("33/80（= 末点水平）不触发", trigger_of(33, 80)["yes"] is False)
    chk("n=0 ⇒ None（不许静默当不触发）", trigger_of(0, 0)["yes"] is None)

    _rv = {2000: {"k": 35, "n": 80}, 1000: {"k": 53, "n": 80}, 3000: {"k": 64, "n": 80}}
    _rt = [(2000, 35 / 80), (1000, 53 / 80), (3000, 64 / 80)]
    chk("worst_cell 取到最差的那一格（元组要 [0]，2026-10-04 的 KeyError 回归钉）",
        worst_cell(_rt, _rv) == (2000, 35, 80))
    chk("worst_cell 与顺序无关", worst_cell(list(reversed(_rt)), _rv) == (2000, 35, 80))
    chk("worst_cell 平手取先出现的那个", worst_cell([(1, 0.5), (2, 0.5)], {1: {"k": 40, "n": 80},
                                                                        2: {"k": 40, "n": 80}}) == (1, 40, 80))
    chk("worst_cell 空表 ⇒ None", worst_cell([], {}) is None)
    chk("worst_cell 出来的 k/n 能直接喂 trigger_of", trigger_of(*worst_cell(_rt, _rv)[1:])["yes"] is False)
    chk("触发文案含 MIN3102", "MIN3102" in trigger_of(40, 80)["text"])

    chk("无差别带 = 11 pp（2σ）", DIFF_BAND_PP == 11.0)
    chk("有差别下限 = 12 pp", DIFF_MIN_PP == 12.0)
    chk("10.0 pp（21/80 vs 13/80）在 11 pp 带内 ⇒ SAME",
        diff_branch(21, 80, 13, 80, "F3")["code"] == "SAME")
    chk("11.25 pp（22/80 vs 13/80）出 11 pp 带 ⇒ HIGHER（带是闭区间，>11 即出界）",
        diff_branch(22, 80, 13, 80, "F3")["code"] == "HIGHER")
    chk("高 12.5 pp ⇒ HIGHER", diff_branch(23, 80, 13, 80, "F3")["code"] == "HIGHER")
    chk("低 12.5 pp ⇒ LOWER", diff_branch(3, 80, 13, 80, "F3")["code"] == "LOWER")
    chk("F3 的 HIGHER 文案指向 H-C", "H-C" in diff_branch(30, 80, 13, 80, "F3")["text"])
    chk("F3 的 SAME 文案指向 H-B", "H-B" in diff_branch(13, 80, 13, 80, "F3")["text"])
    chk("F4 的 HIGHER 文案指向 H-A", "H-A" in diff_branch(30, 80, 13, 80, "F4")["text"])
    chk("F4 的 SAME 文案说 lr 不是主因", "lr 不是" in diff_branch(13, 80, 13, 80, "F4")["text"])
    chk("F4 的 LOWER 文案指向 H-B（欠拟合）", "H-B" in diff_branch(0, 80, 13, 80, "F4")["text"])
    chk("n=0 ⇒ NA", diff_branch(0, 0, 13, 80, "F3")["code"] == "NA")

    chk("F1/F2 目录名：4 个反向 rep", len(rev_dirs(f_prefix(2000))) == 4)
    chk("F1/F2 目录名：rep 编号从 _rep2 起", rev_dirs(f_prefix(2000))[1].endswith("_rep2"))
    chk("F1/F2 目录名含 ep3102 标记", "ep3102" in rev_dirs(f_prefix(1000))[0])
    chk("7G 目录名不含 ep3102（它是新训练，不是回溯检查点）", "ep3102" not in rev_dirs(g_prefix(4000))[0])
    chk("三个 seed 的目录名互不相同", len({rev_dirs(f_prefix(s))[0] for s in (1000, 2000, 3000)}) == 3)
    chk("F3/F4 的 run 名不同", F3_JOB != F4_JOB)
    chk("7G 用新 seed（不与 1000/2000/3000 重叠）", not (set(G_SEEDS) & set(B8)))
    chk("7G 步数 = 18000 = epoch 3.102", abs(G_STEPS / (46426 / 8) - 3.1017) < 1e-3)
    chk("18000 是 save_freq 2000 的整数倍（last 会指对格，坑 38）", G_STEPS % 2000 == 0)

    chk("prov：产物不在要报出来", any("产物不在" in b for b in prov(["__nope__"], "x", "reverse", 7000)))
    chk("prov：空目录列表不报问题", prov([], "x", "reverse", 7000) == [])

    chk("Fisher 两套签名对账（坑 61）：同一张表同一个 p",
        abs(fisher_two_sided(40, 80, 33, 80) - __import__("mg_seedcurve").fisher2(40, 40, 33, 47)) < 1e-12)
    chk("spread 复用自 mg_verdict_s7c（不重写第二遍）", spread([0.5, 0.7, 0.9])["range_pp"] == 40.0)
    chk("既有常数：batch8 三 seed 的 TEST 放宽", B8_TEST_REV == {1000: (55, 80), 2000: (33, 80), 3000: (64, 80)})
    chk("既有常数：7B 的 TEST 反向 13/80", S7B_REV == (13, 80))
    chk("既有常数：极差对照 38.8 pp", abs(B8_RANGE_PP - 38.8) < 1e-9)
    chk("正向基线 193/300 = 64.3%", abs(FWD_BASELINE[0] / FWD_BASELINE[1] - 0.6433) < 1e-3)

    print(f"[selftest] {npass} passed, {nfail} failed")
    return 1 if nfail else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="f", choices=["f", "g"])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    return report_f() if args.mode == "f" else report_g()


if __name__ == "__main__":
    raise SystemExit(main())
