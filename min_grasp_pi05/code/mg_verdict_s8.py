#!/usr/bin/env python
"""档 8 判定：纠正数据能不能把**坏 seed 2000** 抬过使命门（预注册 `runs/S8_PREREG.md`）。

四条判据（阈值在预注册 §3 写死，本文件只**读盘上产物**并照抄，不许在代码里放宽）：
  D1（主门）：8C 的 TEST 反向放宽 **≥ 40/80 = 50%**（与档 3r/7C/7G 完全同一条使命门）
  D2（护栏）：正向未见 20 局，掉幅 vs **193/300 = 64.3%** ≤ **15 pp**
              （D1 ✅ ∧ D2 🚫 ⇒ **不采信**：拆东墙补西墙，与档 7B 的 M5 同一条纪律）
  D3（归因）：8C vs 8C-ctl 在**同一批 (rep, seed)** 的 80 局上配对 —— 净胜 ≥ **+8** 且单侧 p ≤ **0.05**
              （方法学出处 `runs/S5_SUPPLEMENT.md` §一末：主判据应是**配对净收益**，不是总成功率）
  D4（稳健）：8D 的新 seed 4000/5000 与 seed2000 三个的反向 TEST 放宽 **min ≥ 40/80**

⚠️ 关门读数一律 `last`（= 022000，**不做 val 选点**，坑 27/38/42）；出身核对要求
   `policy_ckpt` 尾串是**数字格** `checkpoints/022000/pretrained_model`（坑 63：写 `last` 会被判不采信）。
⚠️ 跨数据集比较一律无效（normalizer 不同）⇒ 归因只能在 `mix60f120r_c1` 内部用
   `--dataset.episodes=0-179` 做 1:1（该 flag 只筛帧、不重算 stats）。

用法：
    $MG_PY code/mg_verdict_s8.py --selftest
    $MG_PY code/mg_verdict_s8.py > runs/S8_VERDICT.md          # 有几条读数就判几条
    $MG_PY code/mg_verdict_s8.py --mode c                      # 只看 8C（D1/D2）
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_verdict_s2f import ci, collect, load, wilson  # noqa: E402

RUNS = MG_ROOT / "runs"

# ── 口径常数（与档 3r/7B/7F 逐项相同，不许动）────────────────────────────────
EPS = 20            # 每读 20 局
REPS = 4            # 反向 TEST 4×20 = 80 局
K_EVAL = 10         # n_action_steps
REV_SEED0 = 7000    # TEST 反向窗口 7000..7019
FWD_SEED0 = 2000    # 正向护栏窗口 2000..2019
VAL_SEED0 = 8000    # 11 格 val 扫描窗口
CK_SUFFIX = "checkpoints/022000/pretrained_model"   # 关门格 = last = 22000 步

# ── 判据阈值（预注册 §3）────────────────────────────────────────────────────
D1_K, D1_N = 40, 80            # ≥ 50%
FWD_BASE_K, FWD_BASE_N = 193, 300      # 64.33%（三 seed 合并的正向基线）
D2_MAX_DROP_PP = 15.0
D3_MIN_NET = 8                 # 净胜局
D3_MAX_P = 0.05                # 单侧
D4_MIN_K, D4_MIN_N = 40, 80

# ── 参照读数（盘上既有产物，写在这里只为对照，不参与判定）──────────────────────
S3R_REV = {1000: (55, 80), 2000: (33, 80), 3000: (64, 80)}   # runs/S3R_VERDICT.md
S3R_FWD = {1000: (15, 20), 2000: (4, 20), 3000: (13, 20)}
ARM_C = "s8c_seed2000"          # 8C：mix60f120r_c1 全集
ARM_CTL = "s8c_ctl_seed2000"    # 8C-ctl：同数据集 --dataset.episodes=0-179
ARMS_D = {4000: "s8d_seed4000", 5000: "s8d_seed5000"}


def rev_dirs(prefix: str) -> list[str]:
    d = [f"{prefix}_rev_test_rand20_k10"]
    d += [f"{prefix}_rev_test_rand20_k10_rep{i}" for i in range(2, REPS + 1)]
    return d


def fwd_dir(prefix: str) -> str:
    return f"{prefix}_fwd_test_rand20_k10"


def pct(k: int, n: int) -> str:
    return "—" if n <= 0 else f"{100.0 * k / n:.1f}%"


# ─────────────── 纯函数（都有自测；期望值按定义独立算，坑 65）───────────────
def sign_test_one_sided(b: int, c: int) -> float:
    """配对二值的**单侧精确**符号检验：P(X ≥ b | n = b+c, p = 0.5)。

    b = 实验臂胜、对照臂负的配对数；c = 反过来。平局（两臂同结果）不进检验。
    n = 0 时返回 1.0（没有任何不一致 ⇒ 不能说有差异，绝不返回 0 让它假过）。
    """
    n = int(b) + int(c)
    if n <= 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(int(b), n + 1)) / (2.0 ** n)


def gate_d1(k: int, n: int) -> dict:
    ok = (n == D1_N and k >= D1_K)
    return {"pass": bool(ok), "k": int(k), "n": int(n), "pct": pct(k, n), "wilson": ci(k, n),
            "gate": f"≥ {D1_K}/{D1_N} = 50%",
            "note": ("" if n == D1_N else f"⚠️ 局数 {n} ≠ {D1_N}，读数不齐 ⇒ 不判")}


def gate_d2(k: int, n: int) -> dict:
    if n <= 0:
        return {"pass": False, "unknown": True, "drop_pp": float("nan"), "pct": "—",
                "gate": f"掉幅 ≤ {D2_MAX_DROP_PP} pp vs {FWD_BASE_K}/{FWD_BASE_N}", "note": "无读数"}
    base = 100.0 * FWD_BASE_K / FWD_BASE_N
    got = 100.0 * k / n
    drop = base - got
    return {"pass": bool(drop <= D2_MAX_DROP_PP), "unknown": False, "drop_pp": round(drop, 2),
            "pct": pct(k, n), "base_pct": round(base, 2),
            "gate": f"掉幅 ≤ {D2_MAX_DROP_PP} pp vs {FWD_BASE_K}/{FWD_BASE_N} = {base:.1f}%",
            "note": ""}


def gate_d3(net: int, p: float, n_pairs: int) -> dict:
    ok = (net >= D3_MIN_NET) and (p <= D3_MAX_P) and n_pairs >= D1_N
    return {"pass": bool(ok), "net": int(net), "p": p, "n_pairs": int(n_pairs),
            "gate": f"净胜 ≥ +{D3_MIN_NET} ∧ 单侧 p ≤ {D3_MAX_P} ∧ 配对数 ≥ {D1_N}",
            "note": ("" if n_pairs >= D1_N else f"⚠️ 只配上 {n_pairs} 对（应 ≥{D1_N}）⇒ 不判")}


def gate_d4(per_seed: dict[int, tuple[int, int]]) -> dict:
    """D4：三个训练 seed 的反向 TEST 放宽 **min ≥ 40/80**。缺任何一个 seed ⇒ UNKNOWN（不许当 0）。"""
    need = {2000, 4000, 5000}
    have = {s: v for s, v in per_seed.items() if v and v[1] == D4_MIN_N}
    missing = sorted(need - set(have))
    if missing:
        return {"pass": False, "unknown": True, "missing": missing, "per_seed": have,
                "gate": f"min ≥ {D4_MIN_K}/{D4_MIN_N}", "note": f"缺 seed {missing} 的齐读数"}
    worst = min(have.values(), key=lambda v: v[0] / v[1])
    wk = min(v[0] for v in have.values())
    return {"pass": bool(wk >= D4_MIN_K), "unknown": False, "missing": [], "per_seed": have,
            "min_k": worst[0], "gate": f"min ≥ {D4_MIN_K}/{D4_MIN_N}", "note": ""}


def pair_outcomes(a_dirs: list[str], b_dirs: list[str]) -> dict:
    """把两臂的 per_episode 按 (rep 序号, seed) 配对。返回 b/c/n_pairs/问题清单。

    ⚠️ 这是**合法**的配对二值设计：两臂是**同一批初态**上的两个策略（同 seed 窗口、同 K、同 task），
    不是档 5 那种「另一次采样」的伪配对（出处 runs/S5_SUPPLEMENT.md §一末）。
    """
    def table(dirs: list[str]) -> dict[tuple[int, int], bool]:
        out: dict[tuple[int, int], bool] = {}
        for rep, d in enumerate(dirs, start=1):
            j = load(d)
            if j is None or "_error" in j:
                continue
            for e in j.get("per_episode", []):
                out[(rep, int(e["seed"]))] = bool(e.get("success_relaxed", e.get("success", False)))
        return out

    ta, tb = table(a_dirs), table(b_dirs)
    keys = sorted(set(ta) & set(tb))
    b = sum(1 for k in keys if ta[k] and not tb[k])       # 实验臂胜
    c = sum(1 for k in keys if tb[k] and not ta[k])       # 对照臂胜
    both = sum(1 for k in keys if ta[k] and tb[k])
    neither = len(keys) - b - c - both
    problems = []
    if len(ta) != len(keys):
        problems.append(f"实验臂有 {len(ta)} 局但只配上 {len(keys)} 对")
    if len(tb) != len(keys):
        problems.append(f"对照臂有 {len(tb)} 局但只配上 {len(keys)} 对")
    return {"b": b, "c": c, "net": b - c, "both": both, "neither": neither,
            "n_pairs": len(keys), "p": sign_test_one_sided(b, c), "problems": problems}


def prov(dirs: list[str], ck_suffix: str, mode: str, seed0: int, eps: int = EPS) -> list[str]:
    """出身核对：ckpt 尾串（必须数字格，坑 63）/ task_mode / K / seed 窗口 / 局数。"""
    bad = []
    for d in dirs:
        j = load(d)
        if j is None:
            bad.append(f"{d}: 产物不在")
            continue
        if "_error" in j:
            bad.append(f"{d}: {j['_error']}")
            continue
        ck = str(j.get("policy_ckpt", "?"))
        if not ck.endswith(ck_suffix):
            bad.append(f"{d}: policy_ckpt 尾巴是 …{ck[-46:]}，期望 …{ck_suffix}（坑 38/42/63：读错权重）")
        if j.get("task_mode") != mode:
            bad.append(f"{d}: task_mode={j.get('task_mode')} ≠ {mode}")
        if int(j.get("n_action_steps", -1)) != K_EVAL:
            bad.append(f"{d}: K={j.get('n_action_steps')} ≠ {K_EVAL}")
        if int(j.get("seed", -1)) != seed0:
            bad.append(f"{d}: seed={j.get('seed')} ≠ {seed0}（seed 窗口变了就不可配对）")
        if int(j.get("episodes", 0)) != eps:
            bad.append(f"{d}: episodes={j.get('episodes')} ≠ {eps}")
    return bad


# ─────────────────────────────── 报告 ───────────────────────────────
def report(mode: str) -> int:
    rev_c = collect(rev_dirs(ARM_C), "n_success_relaxed", "pc_success_relaxed")
    str_c = collect(rev_dirs(ARM_C), "n_success", "pc_success")
    fwd_c = collect([fwd_dir(ARM_C)], "n_success_relaxed", "pc_success_relaxed")
    rev_ctl = collect(rev_dirs(ARM_CTL), "n_success_relaxed", "pc_success_relaxed")
    fwd_ctl = collect([fwd_dir(ARM_CTL)], "n_success_relaxed", "pc_success_relaxed")

    d1 = gate_d1(rev_c["k"], rev_c["n"]) if rev_c["n"] else None
    d2 = gate_d2(fwd_c["k"], fwd_c["n"]) if fwd_c["n"] else None
    paired = pair_outcomes(rev_dirs(ARM_C), rev_dirs(ARM_CTL)) if (rev_c["n"] and rev_ctl["n"]) else None
    d3 = gate_d3(paired["net"], paired["p"], paired["n_pairs"]) if paired else None
    per_seed_d = {}
    if rev_c["n"] == D1_N:
        per_seed_d[2000] = (rev_c["k"], rev_c["n"])
    for sd, arm in ARMS_D.items():
        r = collect(rev_dirs(arm), "n_success_relaxed", "pc_success_relaxed")
        if r["n"]:
            per_seed_d[sd] = (r["k"], r["n"])
    d4 = gate_d4(per_seed_d) if len(per_seed_d) == 3 else None

    prov_bad = []
    if rev_c["n"]:
        prov_bad += prov(rev_dirs(ARM_C), CK_SUFFIX, "reverse", REV_SEED0)
        prov_bad += prov([fwd_dir(ARM_C)], CK_SUFFIX, "forward", FWD_SEED0)
    if rev_ctl["n"]:
        prov_bad += prov(rev_dirs(ARM_CTL), CK_SUFFIX, "reverse", REV_SEED0)

    trust = not prov_bad
    L = ["# 档 8 判定：纠正数据能不能把坏 seed 2000 抬过使命门", "",
         f"* 生成时间：{datetime.now():%F %T}（`code/mg_verdict_s8.py --mode {mode}`）",
         "* 预注册出处：`runs/S8_PREREG.md`（2026-10-04 12:25 落盘 + §9 增补，**早于本档任何读数**）",
         "* 上游：`runs/S3R_VERDICT.md`（档 3r ❌ FAIL：最差 seed 41.2%）、"
         "`runs/S7_VERDICT.md`（7B 不采信）、`runs/_diag/s7f_trigger_interim.md`（7G_TRIGGER=NO）",
         f"* 主口径 = **放宽 R**（送到为首要，侧躺另打 `delivered_tipped` 标）；严格 ⊆ 放宽；关门格 = `last` = 022000",
         f"* 出身核对：{'✅ 全对' if trust else f'🚫 {len(prov_bad)} 条不对 ⇒ 本判定不采信'}", "",
         "## 一、四条判据", "",
         "| 判据 | 读数 | 门槛 | 结果 |", "|:--|:--|:--|:--|"]
    if d1:
        L.append(f"| **D1** 主门（TEST 反向放宽，8C） | **{d1['k']}/{d1['n']} = {d1['pct']}** "
                 f"Wilson {d1['wilson']}（严格 {str_c['k']}/{str_c['n']}） | {d1['gate']} | "
                 f"{'✅ PASS' if (d1['pass'] and trust) else '❌ FAIL'} |")
    else:
        L.append(f"| **D1** 主门 | 还没有读数（缺 {rev_c['missing'] or '全部'}） | ≥ {D1_K}/{D1_N} | ⏳ |")
    if d2:
        L.append(f"| **D2** 护栏（正向未见 20 局） | {d2['pct']}，掉幅 **{d2['drop_pp']} pp** | {d2['gate']} | "
                 f"{'✅ PASS' if (d2['pass'] and trust) else '🚫 FAIL'} |")
    else:
        L.append(f"| **D2** 护栏 | 还没有读数 | 掉幅 ≤ {D2_MAX_DROP_PP} pp | ⏳ |")
    if d3:
        L.append(f"| **D3** 归因（8C vs 8C-ctl 配对 {paired['n_pairs']} 对） | 净胜 **{d3['net']:+d}**"
                 f"（8C 独胜 {paired['b']} / ctl 独胜 {paired['c']} / 都成 {paired['both']} / "
                 f"都败 {paired['neither']}），单侧 p = **{d3['p']:.4f}** | {d3['gate']} | "
                 f"{'✅ PASS' if (d3['pass'] and trust) else '❌ FAIL'} |")
    else:
        L.append(f"| **D3** 归因 | 还没有读数（需要 8C 与 8C-ctl 两臂齐） | 净胜 ≥ +{D3_MIN_NET} ∧ p ≤ {D3_MAX_P} | ⏳ |")
    if d4:
        cells = "、".join(f"seed{s}={v[0]}/{v[1]}" for s, v in sorted(d4["per_seed"].items()))
        L.append(f"| **D4** 稳健（三个训练 seed） | {cells} ⇒ min = **{d4['min_k']}/{D4_MIN_N}** | "
                 f"{d4['gate']} | {'✅ PASS' if (d4['pass'] and trust) else '❌ FAIL'} |")
    else:
        L.append(f"| **D4** 稳健 | 还没有齐三个 seed 的读数（现有 {sorted(per_seed_d)}） | "
                 f"min ≥ {D4_MIN_K}/{D4_MIN_N} | ⏳ |")
    L += [""]

    L += ["## 二、与既有读数的对照（**不许**跨数据集比高低，这里只为看方向）", "",
          "| 臂 | TEST 反向放宽 | 正向未见 | 出处 |", "|:--|---:|---:|:--|"]
    for sd in sorted(S3R_REV):
        k, n = S3R_REV[sd]
        fk, fn = S3R_FWD[sd]
        L.append(f"| 档 3r seed{sd}（`mix60f120r`） | {k}/{n} = {pct(k, n)} | {fk}/{fn} | `runs/S3R_VERDICT.md` |")
    if rev_c["n"]:
        L.append(f"| **8C seed2000 + 纠正**（`mix60f120r_c1` 全集） | **{rev_c['k']}/{rev_c['n']} = "
                 f"{pct(rev_c['k'], rev_c['n'])}** | {fwd_c['k']}/{fwd_c['n']} | 本档 |")
    if rev_ctl["n"]:
        L.append(f"| 8C-ctl seed2000（同数据集，只用 0-179 集） | {rev_ctl['k']}/{rev_ctl['n']} = "
                 f"{pct(rev_ctl['k'], rev_ctl['n'])} | {fwd_ctl['k']}/{fwd_ctl['n']} | 本档 |")
    L += ["",
          "* ⚠️ 8C / 8C-ctl 的 normalizer 与档 3r **不同**（追加纠正帧后 stats 覆盖全集，"
          "出处 `runs/s8a_probe/append_probe.md` 断言 3）⇒ 与档 3r 的行**不构成**可比对照，",
          "  只有 8C vs 8C-ctl 这一对是 1:1（同数据集、同 stats、同步数、同 lr、同 seed，唯一差 = 纠正帧在不在被采样）。",
          "* ⚠️ 不说「纠正数据比更多示范好」这类 n=1 的配方高低话（坑 57）。", ""]

    L += ["## 三、机器可读行（链脚本 grep 这几行）", "", "```"]
    L.append(f"S8_D1={'PASS' if (d1 and d1['pass'] and trust) else ('FAIL' if d1 else 'UNKNOWN')} "
             f"k={rev_c['k']}/{rev_c['n']}")
    L.append(f"S8_D2={'PASS' if (d2 and d2['pass'] and trust) else ('FAIL' if d2 else 'UNKNOWN')} "
             f"drop_pp={d2['drop_pp'] if d2 else 'NA'}")
    L.append(f"S8_D3={'PASS' if (d3 and d3['pass'] and trust) else ('FAIL' if d3 else 'UNKNOWN')} "
             f"net={paired['net'] if paired else 'NA'} p={paired['p'] if paired else 'NA'}")
    L.append(f"S8_D4={'PASS' if (d4 and d4['pass'] and trust) else ('FAIL' if d4 else 'UNKNOWN')}")
    mission = "CLOSED" if (d1 and d2 and d3 and d1["pass"] and d2["pass"] and d3["pass"] and trust) else "OPEN"
    L.append(f"S8_MISSION_GATE={mission}")
    # 一条读数都没有时 TRUST 报 NA：`prov()` 对空清单返回「全对」，写 YES 会被误读成「已核过出身」
    n_reads = rev_c["n"] + rev_ctl["n"] + sum(r["n"] for sd, arm in ARMS_D.items()
                                              for r in [collect(rev_dirs(arm), "n_success_relaxed", "pc")])
    L.append(f"S8_TRUST={'NA' if n_reads == 0 else ('YES' if trust else 'NO')}")
    L += ["```", ""]

    L += ["## 四、决策（预注册 §3 的决策树，照抄）", ""]
    if d1 and not d1["pass"]:
        L += ["* **D1 ❌** ⇒ 判定写明「纠正数据在本产出率/占比下抬不动坏 seed」⇒ **转阶梯 7（RL）或收工**，"
              "不再烧数据侧实验。",
              "* 例外（预注册 §4）：若 8C 的 11 格 val 曲线**全程**在对照臂之上（配对符号 ≥9 胜 0 负），"
              "可写「方向为正、幅度不够」，处方 = 抬纠正帧占比（15%→30%）或每 seed 各采一份，**另起预注册**。"]
    elif d1 and d2 and d1["pass"] and not d2["pass"]:
        L += ["* **D1 ✅ ∧ D2 🚫** ⇒ **不采信**（拆东墙补西墙，与档 7B 的 M5 同纪律）⇒ 使命门不算关闭。"]
    elif d1 and d2 and d1["pass"] and d2["pass"]:
        L += ["* **D1 ✅ ∧ D2 ✅** ⇒ 触发 **8C-ctl**（1:1 归因）。"]
        if d3:
            L += [("* **D3 ✅** ⇒ 归因成立（是纠正数据的功劳，不是重训/新 stats 的副作用）⇒ 触发 **8D**（新 seed 4000/5000）。"
                  if d3["pass"] else
                  "* **D3 ❌** ⇒ 「D1 过了但归因不成立」⇒ **使命门不算关闭**（坑 57：n=1 的读数不当结论）。")]
        if d4:
            L += [("* **D4 ✅** ⇒ 「demo + 纠正」这个配方下**三个训练 seed 全过使命门** ⇒ 档 3r 的 seed 稳健性缺口关闭、"
                  "使命证据链补齐 ⇒ 回用户阶梯第 7 步（RL）或收工。"
                  if d4["pass"] else
                  "* **D4 ❌** ⇒ 纠正数据只在**采集它的那个 seed** 上有效（on-policy 特异性）⇒ 处方 = 每 seed 各采一份"
                  "（+2×1.5 h 采集 + 2×10 h 训练），**另起预注册**再执行。")]
    else:
        L += ["* 读数还没齐 ⇒ 不下结论（坑 57）。"]
    if not trust:
        L += ["", f"### 🚫 出身核对不过（{len(prov_bad)} 条）⇒ 本判定**不采信**", ""] + [f"* {b}" for b in prov_bad]
    L += [""]

    if rev_c["n"]:
        L += ["## 五、8C 逐读明细", "",
              "| 读 | k/n | 严格 | 侧躺 | 送达框内 | ckpt 尾串 | seed | K |", "|:--|---:|---:|--:|--:|:--|--:|--:|"]
        for r in rev_c["reads"]:
            L.append(f"| `{r['dir']}` | {r['k']}/{r['n']} | {r['k_strict']} | {r['tipped']} | {r['inbox']} | "
                     f"…{r['ckpt']} | {r['seed']} | {r['K']} |")
        L += [""]
        if rev_c["broken"]:
            L += ["* 🚫 不变量被破坏（严格 ⊆ 放宽）："] + [f"  * {b}" for b in rev_c["broken"]] + [""]
    if paired and paired["problems"]:
        L += ["## 六、配对口径的问题", ""] + [f"* {p}" for p in paired["problems"]] + [""]

    L += ["## 复现", "", "```bash",
          "$MG_PY code/mg_verdict_s8.py --selftest",
          "$MG_PY code/mg_verdict_s8.py > runs/S8_VERDICT.md",
          "bash code/chain_s8c.sh        # 8C -> 11 格扫描 -> TEST -> 本判定（D1∧D2 过才发 8C-ctl）",
          "```", ""]
    print("\n".join(L))
    return 0 if trust else 3


def selftest() -> int:
    npass = nfail = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal npass, nfail
        if cond:
            npass += 1
        else:
            nfail += 1
            print(f"  [FAIL] {name}")

    # ── sign_test_one_sided：期望值用二项分布定义独立算（坑 65）──
    chk("b=8,c=0 => p = 0.5^8 = 0.00390625", abs(sign_test_one_sided(8, 0) - 0.5 ** 8) < 1e-12)
    chk("b=0,c=8 => p = 1.0（一点没胜）", sign_test_one_sided(0, 8) == 1.0)
    # n=16, b=12: sum C(16,12..16)/2^16 = (1820+560+120+16+1)/65536
    chk("b=12,c=4 => p = 2517/65536 = 0.0384", abs(sign_test_one_sided(12, 4) - 2517 / 65536) < 1e-12)
    # n=15, b=10: sum C(15,10..15)/2^15 = (3003+1365+455+105+15+1)/32768
    chk("b=10,c=5 => p = 4944/32768 = 0.1509（不过门）",
        abs(sign_test_one_sided(10, 5) - 4944 / 32768) < 1e-12)
    chk("b=c => p ≈ 0.5 以上（对称，不能说有差异）", sign_test_one_sided(5, 5) > 0.5)
    chk("n=0 => p=1.0（绝不返回 0 让它假过）", sign_test_one_sided(0, 0) == 1.0)
    chk("单调：b 越大 p 越小", sign_test_one_sided(9, 3) < sign_test_one_sided(8, 4))

    # ── gate_d1：边界 ──
    chk("D1 边界：40/80 过", gate_d1(40, 80)["pass"])
    chk("D1 边界：39/80 不过", not gate_d1(39, 80)["pass"])
    chk("D1：局数不齐不判（60 局全成也不过）", not gate_d1(60, 60)["pass"] and "⚠️" in gate_d1(60, 60)["note"])
    chk("D1 读数串", gate_d1(33, 80)["pct"] == "41.2%")

    # ── gate_d2：掉幅边界（基线 193/300 = 64.3333%）──
    base = 100.0 * FWD_BASE_K / FWD_BASE_N
    k15 = round((base - 15.0) / 100.0 * 20)          # 掉幅恰好 15 pp 时的 20 局成功数
    g = gate_d2(k15, 20)
    chk(f"D2 边界：{k15}/20 掉幅 {g['drop_pp']}pp ≤ 15 => 过", g["pass"])
    chk("D2：0/20 掉幅 64.33pp => 不过", not gate_d2(0, 20)["pass"])
    chk("D2：13/20 = 65% 反而涨 => 过", gate_d2(13, 20)["pass"] and gate_d2(13, 20)["drop_pp"] < 0)
    chk("D2：4/20 = 20%（档 3r 的坏 seed 正向）掉幅 44.3pp => 不过", not gate_d2(4, 20)["pass"])
    chk("D2：无读数 => unknown 且不过", gate_d2(0, 0)["unknown"] and not gate_d2(0, 0)["pass"])

    # ── gate_d3：三个条件都要 ──
    chk("D3：净 +8 且 p=0.0039 且 80 对 => 过", gate_d3(8, sign_test_one_sided(8, 0), 80)["pass"])
    chk("D3：净 +7 不过（即使 p 小）", not gate_d3(7, sign_test_one_sided(7, 0), 80)["pass"])
    chk("D3：净 +8 但 p>0.05（b=8,c=4）不过", not gate_d3(4, sign_test_one_sided(8, 4), 80)["pass"]
        or not gate_d3(8, sign_test_one_sided(8, 4), 80)["pass"])
    chk("D3：配对数不足 80 不过（n=1 的读数不当结论，坑 57）", not gate_d3(20, 0.001, 40)["pass"])
    chk("D3：净负 => 不过", not gate_d3(-3, sign_test_one_sided(2, 5), 80)["pass"])

    # ── gate_d4：min 口径 + 缺 seed 不许当 0 ──
    g4 = gate_d4({2000: (45, 80), 4000: (41, 80), 5000: (60, 80)})
    chk("D4：三个都 ≥40 => 过（min=41）", g4["pass"] and g4["min_k"] == 41)
    g4b = gate_d4({2000: (45, 80), 4000: (39, 80), 5000: (60, 80)})
    chk("D4：一个 39 => 不过", not g4b["pass"])
    g4c = gate_d4({2000: (45, 80)})
    chk("D4：缺 seed => UNKNOWN 不过（不许把缺的当 0 也不许当过）", g4c["unknown"] and not g4c["pass"]
        and g4c["missing"] == [4000, 5000])
    g4d = gate_d4({2000: (45, 60), 4000: (41, 80), 5000: (60, 80)})
    chk("D4：局数不齐的 seed 不算有读数", g4d["unknown"] and 2000 in g4d["missing"])

    # ── pair_outcomes：用假产物钉住配对口径 ──
    import tempfile
    import mg_verdict_s2f as v2f
    with tempfile.TemporaryDirectory() as td:
        # ⚠️ `load()` 是 s2f 的函数，它读的是 **s2f 模块自己的** RUNS ⇒ 打桩必须打在它身上，
        #   改本模块的 RUNS 一点用没有（2026-10-04 自测实测：7 条配对/出身用例全挂）。
        saved = v2f.RUNS
        v2f.RUNS = Path(td)
        RUNS = Path(td)
        try:
            def mk(d: str, seeds: list[int], flags: list[bool]) -> None:
                (RUNS / d).mkdir(parents=True, exist_ok=True)
                (RUNS / d / "eval_summary.json").write_text(json.dumps({
                    "episodes": len(seeds), "seed": seeds[0], "n_action_steps": K_EVAL,
                    "task_mode": "reverse", "policy_ckpt": f"/x/checkpoints/022000/pretrained_model",
                    "per_episode": [{"seed": s, "success_relaxed": f} for s, f in zip(seeds, flags)]}))
            S = [7000, 7001, 7002, 7003]
            mk("A", S, [True, True, False, False])
            mk("B", S, [True, False, True, False])
            p = pair_outcomes(["A"], ["B"])
            chk("配对：b=1（A 独胜 7001）", p["b"] == 1)
            chk("配对：c=1（B 独胜 7002）", p["c"] == 1)
            chk("配对：净胜 0、都成 1、都败 1、共 4 对", p["net"] == 0 and p["both"] == 1
                and p["neither"] == 1 and p["n_pairs"] == 4)
            chk("配对：b=c=1 => p=0.75（n=2 的单侧）", abs(p["p"] - 0.75) < 1e-12)
            chk("配对：口径干净 => 无问题", p["problems"] == [])
            mk("C", S[:2], [True, True])
            p2 = pair_outcomes(["A"], ["C"])
            chk("配对：一臂缺局 => 只配 2 对并报问题", p2["n_pairs"] == 2 and len(p2["problems"]) == 1)
            chk("配对：产物缺失不炸（只少配对）", pair_outcomes(["A"], ["NOPE"])["n_pairs"] == 0)
            # 出身核对
            bad = prov(["A"], "checkpoints/022000/pretrained_model", "reverse", 7000, eps=4)
            chk("prov：全对 => 空清单", bad == [])
            bad2 = prov(["A"], "checkpoints/018000/pretrained_model", "reverse", 7000, eps=4)
            chk("prov：ckpt 尾串不对（写 last 或别的格）=> 报出来（坑 63）", len(bad2) == 1 and "坑" in bad2[0])
            bad3 = prov(["NOPE"], "checkpoints/022000/pretrained_model", "reverse", 7000, eps=4)
            chk("prov：产物不在 => 报出来", bad3 == ["NOPE: 产物不在"])
        finally:
            v2f.RUNS = saved

    # ── 口径常数与预注册一致 ──
    chk("口径：EPS=20 / REPS=4 / K=10", (EPS, REPS, K_EVAL) == (20, 4, 10))
    chk("口径：TEST 反向 7000、正向 2000、val 8000", (REV_SEED0, FWD_SEED0, VAL_SEED0) == (7000, 2000, 8000))
    chk("口径：关门格尾串是数字格 022000", CK_SUFFIX.endswith("checkpoints/022000/pretrained_model"))
    chk("阈值：D1=40/80、D2=15pp、D3=+8/0.05、D4=40/80",
        (D1_K, D1_N, D2_MAX_DROP_PP, D3_MIN_NET, D3_MAX_P, D4_MIN_K) == (40, 80, 15.0, 8, 0.05, 40))
    chk("基线：正向 193/300 = 64.3%", abs(100.0 * FWD_BASE_K / FWD_BASE_N - 64.3333) < 0.001)
    chk("rev_dirs 生成 4 个读且第一个无后缀",
        rev_dirs("X") == ["X_rev_test_rand20_k10", "X_rev_test_rand20_k10_rep2",
                          "X_rev_test_rand20_k10_rep3", "X_rev_test_rand20_k10_rep4"])
    chk("wilson/ci 复用 s2f 的实现（53/80 -> [55.4, 75.7]）", ci(53, 80) == "[55.4, 75.7]")

    print(f"[selftest] {npass} passed, {nfail} failed")
    return 0 if nfail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("all", "c", "ctl", "d"), default="all")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    return report(args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
