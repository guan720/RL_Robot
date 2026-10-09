#!/usr/bin/env python3
"""档 10 判定：关门配方在**标准 chunk 执行（K = chunk_size = 50）**下还过不过同一条使命门

预注册出处：`runs/S10_PREREG.md`（**2026-10-07 17:4x 落盘，早于本档任何读数**）。
唯一变量 = **K**（10 → 50）；检查点/数据集/task 串/TEST seed 窗/局数/判据**逐字不变**。

判据（阈值写死在预注册 §3；改这里等于改判据 ⇒ 必须先改预注册，坑 40）：
  **E1（主门）** = 三臂 K=50 的 TEST 反向**放宽** k/80 的 **min ≥ 40/80 = 50%**（与档 3r/7C/7G/8D/7H/9C **完全同一条**使命门）
  **E2（副门）** = 逐臂 Δ = K50 − K10（放宽，各 80 局）：Δ ≤ −20 pp ⇒ **CRASH（塌陷）**；−20 < Δ ≤ −10 pp ⇒ **GREY（灰区）**；
                   Δ > −10 pp ⇒ **NONINF（非劣）**。取**三臂里最坏**的那档。−20 pp 沿用档 4r 的**事前规则**（不新造）。
  **E3（只读）** = 侧躺率 K50 vs K10（三臂池化各 240 局）Fisher 双侧；**不设门**，p≤0.05 且 K50 更低 ⇒ 登记为「极限 #1 的候选杠杆」
  **E4（部署门）** = 墙钟 **ms/控制步 ≤ 50 ms**（既有实时预算，坑 36）
  **E5（只读）** = 正向护栏各臂 1×20；三臂全 0/20 ⇒ 判「K=50 只在反向可用」并写进极限

K=10 的参照读数**原样从盘上并入、不重跑**（坑 40①），并与 `runs/S8_VERDICT.md:16` 公布的 **65/65/64** 逐臂对账；
对不上 ⇒ 报告打 🚫、退出码 **3**、判定**不采信**（要么读错权重、要么历史读数被改过）。

出身核对（不过 ⇒ 🚫 + 退出码 **3**）：`policy_ckpt` 尾串 == `checkpoints/022000/pretrained_model`、路径含本臂 run 名、
  `task_mode`、**`n_action_steps == 50`**、seed 窗口（反向 7000 / 正向 2000）、`episodes == 20`。
退出码：0 = 判定成立；2 = 读数不齐（**E1 = UNKNOWN，不许当 0 计**，坑 40③）；3 = 出身/对账不过 ⇒ 不采信。

⚠️ 三臂都是 `mix60f120r_c1` ⇒ 臂间可以并列比高低；与 7H/档 3r（`mix60f120r`，normalizer 不同）**只比形状、不比高低**（坑 33）。

用法：
    $MG_PY code/mg_verdict_s10.py --selftest
    $MG_PY code/mg_verdict_s10.py > runs/S10_VERDICT.md
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

from mg_verdict_s2 import fisher_two_sided                        # noqa: E402  已对着 scipy 校验过（坑 54，不重写）
from mg_verdict_s2f import ci, collect, load, pct                  # noqa: E402
from mg_verdict_s7f import (EPS, FWD_SEED0, REPS, REV_SEED0,       # noqa: E402
                            fwd_dirs, prov, rev_dirs)

# ── 预注册常数（出处 runs/S10_PREREG.md §1/§3）──────────────────────────────────────
K_NEW = 50                       # = chunk_size，模型原生 chunk（「标准 chunk 执行」）
K_REF = 10                       # 既有工作点（参照读数已在盘上）
CK_STEP = 22000
CK_SUFFIX = f"checkpoints/{CK_STEP:06d}/pretrained_model"
ARMS = ((2000, "s8c_seed2000", "pi05_mix60f120r_c1_s8c_seed2000"),
        (4000, "s8d_seed4000", "pi05_mix60f120r_c1_s8d_seed4000"),
        (5000, "s8d_seed5000", "pi05_mix60f120r_c1_s8d_seed5000"))
E1_K, E1_N = 40, 80              # 主门：min ≥ 40/80 = 50%（同一条使命门）
E2_CRASH_PP = -20.0              # 档 4r 的事前规则：掉 ≥20 pp ⇒ 塌陷
E2_GREY_PP = -10.0
E4_MS = 50.0                     # 实时预算（坑 36）
PUB_REV = {2000: (65, 80), 4000: (65, 80), 5000: (64, 80)}   # 出处 runs/S8_VERDICT.md:16（D4）
PUB_FWD = {2000: (16, 20), 4000: (12, 20), 5000: (16, 20)}   # 出处 runs/S9C_VERDICT 引用的 S8_FWD


# ─────────────────────────── 目录命名（K=50 是本档新产物；K=10 复用冻结口径）───────────────────────────
def k50_rev(prefix: str) -> list[str]:
    return [f"s10_{prefix}_rev_test_rand20_k{K_NEW}" + ("" if i == 1 else f"_rep{i}") for i in range(1, REPS + 1)]


def k50_fwd(prefix: str) -> list[str]:
    return [f"s10_{prefix}_fwd_test_rand20_k{K_NEW}"]


# ─────────────────────────── 纯函数（判据）───────────────────────────
def gate_e1(per_arm: dict) -> dict:
    """主门：三臂 K=50 反向放宽 k/80 的 min ≥ 40/80。任一臂局数不齐 ⇒ UNKNOWN（不当 0、不当过，坑 40③）。"""
    short = [sd for sd, kn in per_arm.items() if kn is None or kn[1] != E1_N]
    if short:
        return {"pass": None, "state": "UNKNOWN", "min_k": None, "min_n": None, "short": sorted(short),
                "detail": {sd: per_arm[sd] for sd in sorted(per_arm)}}
    mk = min(kn[0] for kn in per_arm.values())
    ok = mk >= E1_K
    return {"pass": ok, "state": "PASS" if ok else "FAIL", "min_k": mk, "min_n": E1_N, "short": [],
            "detail": {sd: per_arm[sd] for sd in sorted(per_arm)}}


def band_e2(delta_pp) -> str:
    """Δ = K50% − K10%（pp）。边界含在更坏的那一档（≤ −20 ⇒ CRASH；≤ −10 ⇒ GREY）。"""
    if delta_pp is None or delta_pp != delta_pp:
        return "UNKNOWN"
    if delta_pp <= E2_CRASH_PP:
        return "CRASH"
    if delta_pp <= E2_GREY_PP:
        return "GREY"
    return "NONINF"


def gate_e2(bands: dict) -> dict:
    """取三臂里**最坏**的那档；任一臂 UNKNOWN ⇒ 整体 UNKNOWN（不许用最臂的平均掩盖坏臂）。"""
    rank = {"CRASH": 3, "GREY": 2, "NONINF": 1}
    if any(v == "UNKNOWN" for v in bands.values()) or not bands:
        return {"state": "UNKNOWN", "worst": None, "bands": bands}
    worst = max(bands.values(), key=lambda b: rank[b])
    return {"state": worst, "worst": worst, "bands": bands,
            "pass": worst == "NONINF"}


def delta_pp(k50, k10):
    """两读的成功率差（pp）。任一 n=0 ⇒ None（不当 0，坑 40③）。"""
    if not k50 or not k10 or k50[1] <= 0 or k10[1] <= 0:
        return None
    return 100.0 * k50[0] / k50[1] - 100.0 * k10[0] / k10[1]


def e3_pooled(t50: list, t10: list) -> dict:
    """侧躺率：K50 池化 vs K10 池化，Fisher 双侧。**只读方向、不设门**。"""
    ta, na = sum(x[0] for x in t50), sum(x[1] for x in t50)
    tb, nb = sum(x[0] for x in t10), sum(x[1] for x in t10)
    if na <= 0 or nb <= 0:
        return {"p": None, "k50": (ta, na), "k10": (tb, nb), "lower": None}
    return {"p": fisher_two_sided(ta, na, tb, nb), "k50": (ta, na), "k10": (tb, nb),
            "rate50": 100.0 * ta / na, "rate10": 100.0 * tb / nb, "lower": ta / na < tb / nb}


def ms_per_step(dirs: list, loader=load) -> dict:
    """墙钟 ms/控制步 = Σseconds × 1000 / Σsteps（步数从 per_episode 的 `steps` 求和）。
    缺产物/缺字段的读**跳过并单列**；一条都不剩 ⇒ nan（不当 0，坑 40③）。
    `loader` 可注入 ⇒ 这个函数能在自测里被测到（不碰真产物，坑 77）。"""
    sec, stp, used, skip = 0.0, 0, 0, []
    for d in dirs:
        j = loader(d)
        if j is None:
            skip.append((d, "产物不在"))
            continue
        pe = j.get("per_episode") or []
        n_stp = sum(int(e.get("steps", 0) or 0) for e in pe)
        if j.get("seconds") is None or n_stp <= 0:
            skip.append((d, "缺 seconds 或 per_episode.steps"))
            continue
        sec += float(j["seconds"])
        stp += n_stp
        used += 1
    return {"ms_per_step": (sec * 1000.0 / stp) if stp else float("nan"),
            "seconds": round(sec, 1), "steps": stp, "reads_used": used, "skip": skip}


def xcheck(disk: dict, published: dict) -> list:
    """盘上的 K=10 参照读数必须与已公布值**逐臂相同**（坑 40①：历史读数原样并入、不许重算出别的数）。"""
    bad = []
    for sd, want in published.items():
        got = disk.get(sd)
        if got is None:
            bad.append(f"seed{sd}: 盘上没读到 K=10 参照（期望 {want[0]}/{want[1]}）")
        elif tuple(got) != tuple(want):
            bad.append(f"seed{sd}: 盘上 K=10 = {got[0]}/{got[1]}，与已公布 {want[0]}/{want[1]} 不符 ⇒ 读错权重或历史读数被改")
    return bad


def fmt_kn(c: dict) -> str:
    """把 collect() 的结果印成 `k/n`；**一局都没读到就印 `—`，绝不印 `0/20`**。
    为什么单独立个函数：`n=0` 有两种完全不同的意思 —— 「跑了 20 局、0 成功」和「产物根本不在」。
    前者是真读数（要如实印 0/20），后者是缺读（印 0/20 就等于把缺读当 0 计，坑 40③）。
    用 `n or EPS` 兜底会把两者印成同一个样子，2026-10-07 空跑时就撞见过。"""
    return "—" if c.get("n", 0) <= 0 else f"{c['k']}/{c['n']}"


# ─────────────────────────── 报告 ───────────────────────────
def report() -> int:
    rev50, rev10, fwd50, fwd10, tip50, tip10, strict50 = {}, {}, {}, {}, {}, {}, {}
    for sd, pre, run in ARMS:
        d50, d10 = k50_rev(pre), rev_dirs(pre)
        rev50[sd] = collect(d50, "n_success_relaxed", "pc_success_relaxed")
        rev10[sd] = collect(d10, "n_success_relaxed", "pc_success_relaxed")
        strict50[sd] = collect(d50, "n_success", "pc_success")
        fwd50[sd] = collect(k50_fwd(pre), "n_success_relaxed", "pc_success_relaxed")
        fwd10[sd] = collect(fwd_dirs(pre), "n_success_relaxed", "pc_success_relaxed")
        tip50[sd], tip10[sd] = (rev50[sd]["tipped"], rev50[sd]["n"]), (rev10[sd]["tipped"], rev10[sd]["n"])

    def kn(c):
        return None if c["n"] <= 0 else (c["k"], c["n"])

    e1 = gate_e1({sd: kn(rev50[sd]) for sd, _, _ in ARMS})
    deltas = {sd: delta_pp(kn(rev50[sd]), kn(rev10[sd])) for sd, _, _ in ARMS}
    e2 = gate_e2({sd: band_e2(deltas[sd]) for sd, _, _ in ARMS})
    e3 = e3_pooled([tip50[sd] for sd, _, _ in ARMS], [tip10[sd] for sd, _, _ in ARMS])
    e3_arm = {sd: e3_pooled([tip50[sd]], [tip10[sd]]) for sd, _, _ in ARMS}
    all50 = [d for _, pre, _ in ARMS for d in k50_rev(pre)] + [d for _, pre, _ in ARMS for d in k50_fwd(pre)]
    e4 = ms_per_step(all50)
    e5_zero = all(kn(fwd50[sd]) is not None and fwd50[sd]["k"] == 0 for sd, _, _ in ARMS)

    # 出身核对 + 与已公布 K=10 读数逐臂对账
    bad = []
    for sd, pre, run in ARMS:
        bad += [f"[{pre}] {x}" for x in prov(k50_rev(pre), CK_SUFFIX, "reverse", REV_SEED0, k_eval=K_NEW)]
        bad += [f"[{pre}] {x}" for x in prov(k50_fwd(pre), CK_SUFFIX, "forward", FWD_SEED0, k_eval=K_NEW)]
        for d in k50_rev(pre) + k50_fwd(pre):
            j = load(d)
            if j and "_error" not in j and f"runs/{run}/" not in str(j.get("policy_ckpt", "")):
                bad.append(f"[{pre}] {d}: policy_ckpt 不在本臂 run 里（{j.get('policy_ckpt')}），期望含 runs/{run}/")
    bad += xcheck({sd: kn(rev10[sd]) for sd, _, _ in ARMS}, PUB_REV)
    broken = [b for sd, _, _ in ARMS for b in rev50[sd]["broken"] + rev10[sd]["broken"]]
    missing = [m for sd, _, _ in ARMS for m in rev50[sd]["missing"] + fwd50[sd]["missing"]]
    nofield = [m for sd, _, _ in ARMS for m in rev50[sd]["nofield"]]

    trust = not bad and not broken
    print("# 档 10 判定：关门配方在**标准 chunk 执行（K=50 = chunk_size）**下还过不过同一条使命门")
    print(f"\n<!-- 由 code/mg_verdict_s10.py 生成于 {datetime.now():%Y-%m-%d %H:%M}；"
          f"预注册 runs/S10_PREREG.md（2026-10-07 17:4x 落盘，早于本档任何读数）-->")
    print(f"\n* 唯一变量 = **K**（{K_REF} → {K_NEW}）；检查点 = 三臂 `checkpoints/{CK_STEP:06d}`（编号格，不用 `last`，坑 38/42）。")
    print(f"* 三臂 = 使命门 D4 的那三个（`mix60f120r_c1`，同数据集 ⇒ 臂间可比高低；与 7H/档 3r 跨数据集 ⇒ 只比形状，坑 33）。")
    print(f"* K={K_REF} 参照读数**从盘上原样并入、没重跑**（坑 40①），并已逐臂对账 `runs/S8_VERDICT.md:16` 的 65/65/64。")

    print("\n## 一、主读数（TEST 反向 seed 7000..7019，各 4×20 = 80 局）\n")
    print("| 臂 | 检查点 | K=10 放宽（参照） | **K=50 放宽** | Δ (pp) | E2 档 | K=50 严格 | K=50 侧躺 | K=10 侧躺 | 正向 1×20 K=50 |")
    print("|:--|:--|---:|---:|---:|:--|---:|---:|---:|---:|")
    for sd, pre, run in ARMS:
        a, b = kn(rev10[sd]), kn(rev50[sd])
        dt = deltas[sd]
        print(f"| seed{sd} | `{run.split('pi05_mix60f120r_c1_')[1]}` | "
              f"{'—' if a is None else f'{a[0]}/{a[1]} = {pct(*a)}'} | "
              f"**{'—' if b is None else f'{b[0]}/{b[1]} = {pct(*b)}'}** | "
              f"{'—' if dt is None else f'{dt:+.1f}'} | {band_e2(dt)} | "
              f"{fmt_kn(strict50[sd])} | {tip50[sd][0]} | {tip10[sd][0]} | "
              f"{fmt_kn(fwd50[sd])} |")
    if e1["min_k"] is not None:
        print(f"\n* 逐 rep（K=50 反向，坑 39 的抖动要看得见）：" + "；".join(
            f"seed{sd} " + "/".join(str(r['k']) for r in rev50[sd]['reads']) for sd, _, _ in ARMS))
        print(f"* Wilson 95%（K=50 池化）：" + "；".join(
            f"seed{sd} {ci(*kn(rev50[sd])) if kn(rev50[sd]) else '—'}" for sd, _, _ in ARMS))

    print("\n## 二、判定（阈值来自 `runs/S10_PREREG.md` §3，跑前写死）\n")
    st = e1["state"]
    e1_txt = "—" if e1["min_k"] is None else f"{e1['min_k']}/{E1_N} = {pct(e1['min_k'], E1_N)}"
    e1_verdict = ("⏳ UNKNOWN（读数不齐，**不当 0 计**，坑 40③）" if st == "UNKNOWN"
                  else ("✅ PASS" if e1["pass"] else "❌ FAIL"))
    print(f"| **E1** 主门 | 三臂 K=50 反向放宽的 min ≥ {E1_K}/{E1_N} = 50% | {e1_txt} | {e1_verdict} |")
    print(f"| **E2** 副门 | 逐臂 Δ 最坏档 = NONINF（> −10 pp） | {e2['state']}"
          + (f"（{', '.join(f'seed{k}={v}' for k, v in sorted(e2['bands'].items()))}）" if e2.get('bands') else "")
          + f" | {'⏳ UNKNOWN' if e2['state'] == 'UNKNOWN' else ('✅ 非劣' if e2['pass'] else ('⚠️ 灰区（记为极限）' if e2['state'] == 'GREY' else '❌ 塌陷'))} |")
    if e3["p"] is None:
        print("| **E3** 只读 | 侧躺率 K50 vs K10（池化 Fisher） | 读数不齐 | ⏳ UNKNOWN |")
    else:
        verdict = ("**K=50 显著更低** ⇒ 登记为「极限 #1 TILT 残留」的候选杠杆（零训练；要动它必须另立预注册）"
                   if (e3["p"] <= 0.05 and e3["lower"]) else
                   ("K=50 更高且显著 ⇒ 反向结论，写进极限" if (e3["p"] <= 0.05 and not e3["lower"]) else
                    "**无显著差** ⇒ 档 4r 的 0/20 是 n=20 的偶然，不构成杠杆"))
        print(f"| **E3** 只读 | 侧躺率 K50 vs K10（池化 Fisher 双侧） | "
              f"{e3['k50'][0]}/{e3['k50'][1]} = {e3['rate50']:.1f}% vs {e3['k10'][0]}/{e3['k10'][1]} = {e3['rate10']:.1f}%，p={e3['p']:.4g} | {verdict} |")
    ms = e4["ms_per_step"]
    print(f"| **E4** 部署门 | 墙钟 ms/控制步 ≤ {E4_MS:.0f} ms | "
          f"{'—' if ms != ms else f'{ms:.1f} ms'}（{e4['reads_used']} 读、{e4['steps']} 步） | "
          f"{'⏳ UNKNOWN' if ms != ms else ('✅' if ms <= E4_MS else '❌ 超实时预算')} |")
    print(f"| **E5** 只读 | 正向护栏各臂 1×20（K=50） | "
          + "；".join(f"seed{sd} {fmt_kn(fwd50[sd])}" for sd, _, _ in ARMS)
          + f" | {'⚠️ 三臂全 0 ⇒ K=50 只在反向可用' if e5_zero else '—（参照 K=10：' + '；'.join(f'{PUB_FWD[sd][0]}/{PUB_FWD[sd][1]}' for sd, _, _ in ARMS) + '）'} |")

    print("\n### 机器可读\n```")
    print(f"S10_DATE={datetime.now():%Y-%m-%d %H:%M}")
    print(f"S10_K={K_NEW} S10_K_REF={K_REF} S10_CK={CK_STEP:06d}")
    for sd, _, _ in ARMS:
        a, b = kn(rev10[sd]), kn(rev50[sd])
        print(f"S10_ARM{sd}_K10={'NA' if a is None else f'{a[0]}/{a[1]}'} "
              f"S10_ARM{sd}_K50={'NA' if b is None else f'{b[0]}/{b[1]}'} "
              f"S10_ARM{sd}_DELTA={'NA' if deltas[sd] is None else round(deltas[sd], 2)} "
              f"S10_ARM{sd}_BAND={band_e2(deltas[sd])}")
    print(f"S10_E1={st}" + ("" if e1["min_k"] is None else f" k={e1['min_k']}/{E1_N}"))
    print(f"S10_E2={e2['state']}")
    print("S10_E3=" + ("UNKNOWN" if e3["p"] is None else f"p={e3['p']:.4g} lower={e3['lower']}"))
    print("S10_E4=" + ("UNKNOWN" if ms != ms else f"{ms:.1f}ms {'PASS' if ms <= E4_MS else 'FAIL'}"))
    print(f"S10_FWD_ALL_ZERO={'YES' if e5_zero else 'NO'}")
    print(f"S10_TRUST={'YES' if trust else 'NO'}")
    print("```")

    print("\n## 三、出身与不变量\n")
    print(f"* 出身核对问题：**{len(bad)}** 条" + (f" ⇒ 🚫 **判定不采信**\n" if bad else "（必须 0）✅\n"))
    for b in bad[:12]:
        print(f"  * 🚫 {b}")
    print(f"* 不变量「放宽 ⊇ 严格」违例：**{len(broken)}** 条（必须 0）" + ("✅" if not broken else "🚫"))
    for b in broken[:6]:
        print(f"  * 🚫 {b}")
    print(f"* K=50 缺产物：**{len(missing)}** 个目录" + (f" ⇒ {missing[:6]}" if missing else "（无）✅"))
    print(f"* K=50 缺字段：**{len(nofield)}** 条" + (f" ⇒ {nofield[:6]}" if nofield else "（无）✅"))
    print(f"* 侧躺率逐臂异质（池化前先看的）：" + "；".join(
        f"seed{sd} K50 {e3_arm[sd]['k50'][0]}/{e3_arm[sd]['k50'][1]} vs K10 {e3_arm[sd]['k10'][0]}/{e3_arm[sd]['k10'][1]}"
        for sd, _, _ in ARMS))

    print("\n## 四、判读纪律（写在预注册 §8，别事后合理化）\n")
    print(f"* **主口径只有放宽**；严格与侧躺**并列上报**，不许挑对自己有利的当结论（坑 17）。")
    print(f"* n=80 ⇒ 1σ ≈ 4.5 pp（p≈0.8）；**Δ 的 1σ ≈ 6.4 pp** ⇒ E2 的 −20 pp ≈ 3.1σ、−10 pp ≈ 1.6 σ。"
          "报「非劣」时必须带着这个功效账，不许把「没测出差别」说成「证明了等价」（档 4r 的原话纪律）。")
    print("* E3 **不设门**：即使显著，也只是**登记候选**；要拿 K=50 当治侧躺的处方必须**另立预注册**（坑 40）。")
    print("* 本档**不扫 K 曲线**：若 E2 判塌陷，**不许**事后补 K=25 去找「还能用的中间点」（那是看完数改设计）。")
    print("\n## 五、复现\n```bash\nsource code/env.sh\n$MG_PY code/mg_verdict_s10.py --selftest\n$MG_PY code/mg_verdict_s10.py > runs/S10_VERDICT.md\n```")

    if not trust:
        return 3
    if st == "UNKNOWN" or e2["state"] == "UNKNOWN":
        return 2
    return 0


# ── 自测：门若判错，比没有门更糟（坑 65 家族：判据代码里不留没被测过的表达式）──────────────
# 两层：① 纯函数边界（−20/−10 pp 的档位归属、UNKNOWN 传染、缺读数不当 0）；
#       ② 临时夹具跑完整条 report()，把退出码 0/2/3 三条路都走一遍。
# 夹具只写 tempdir + 只 patch `mg_verdict_s2f.RUNS`（`load` 在调用时才解析该全局 ⇒
# collect/prov 这些复用方一起指向夹具），**不碰真 runs/、不断言盘上进度**（坑 77）。
def _mk(root: Path, name: str, ns_rel: int, ne: int, *, k: int, seed: int, mode: str, ckpt: str,
        tipped: int = 0, legacy: bool = False, steps: int = 250, seconds: float = 200.0) -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    ns_strict = max(0, ns_rel - tipped)
    per = [{"ep": i, "seed": seed + i, "success": i < ns_strict, "success_relaxed": i < ns_rel,
            "delivered_tipped": ns_strict <= i < ns_rel, "steps": steps if i < ns_rel else 400,
            "max_lift_cm": 9.0, "min_dist_to_target_xy": 0.01} for i in range(ne)]
    j = {"n_action_steps": k, "episodes": ne, "task_mode": mode, "seed": seed, "seed_mode": "random",
         "policy_ckpt": ckpt, "seconds": seconds, "n_success": ns_strict, "pc_success": ns_strict / ne,
         "n_delivered_tipped": tipped, "n_ever_in_target_box": ns_rel, "per_episode": per}
    if not legacy:            # legacy = 「改判据前跑的」老产物：没有放宽字段（坑 40③ 的靶子）
        j["n_success_relaxed"] = ns_rel
        j["pc_success_relaxed"] = ns_rel / ne
    (d / "eval_summary.json").write_text(json.dumps(j))


def _split4(k: int) -> list:
    """把 k 局成功摊到 REPS 个 rep（每 rep ≤ EPS）。逐 rep 分布不影响任何门，只为造出真实的目录数。"""
    out, left = [], k
    for _ in range(REPS):
        take = min(EPS, max(0, left))
        out.append(take)
        left -= take
    return out


def _build(root: Path, rev50=None, fwd50=None, *, rev10=None, tip50=None, legacy50=(), k50=True):
    rev10 = {sd: v[0] for sd, v in PUB_REV.items()} if rev10 is None else rev10
    fwd50 = fwd50 or {}
    tip50 = tip50 or {}
    for sd, pre, run in ARMS:
        ck = f"/x/runs/{run}/checkpoints/{CK_STEP:06d}/pretrained_model"
        for name, kk in zip(rev_dirs(pre), _split4(rev10[sd])):
            _mk(root, name, kk, EPS, k=K_REF, seed=REV_SEED0, mode="reverse", ckpt=ck)
        for name, kk in zip(fwd_dirs(pre), _split4(PUB_FWD[sd][0])):
            _mk(root, name, kk, EPS, k=K_REF, seed=FWD_SEED0, mode="forward", ckpt=ck)
        if not k50:
            continue
        t = tip50.get(sd, 0)
        for i, (name, kk) in enumerate(zip(k50_rev(pre), _split4(rev50[sd]))):
            _mk(root, name, kk, EPS, k=K_NEW, seed=REV_SEED0, mode="reverse", ckpt=ck,
                tipped=(t if i == 0 else 0), legacy=(name in legacy50))
        for name in k50_fwd(pre):
            _mk(root, name, fwd50.get(sd, 0), EPS, k=K_NEW, seed=FWD_SEED0, mode="forward", ckpt=ck)


def selftest() -> int:
    import contextlib
    import io
    import tempfile

    import mg_verdict_s2f

    npass = nfail = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal npass, nfail
        if cond:
            npass += 1
        else:
            nfail += 1
            print(f"  [FAIL] {name}")

    def run_scene(build):
        """在 tempdir 里造夹具、把 s2f.RUNS 指过去、跑完整条 report()，返回 (退出码, stdout)。"""
        with tempfile.TemporaryDirectory() as td:
            old = mg_verdict_s2f.RUNS
            mg_verdict_s2f.RUNS = Path(td)
            try:
                build(Path(td))
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = report()
            finally:
                mg_verdict_s2f.RUNS = old
            return rc, buf.getvalue()

    # ── ① 常数与目录命名 ──
    chk("主门 = 40/80 = 50%（与档 3r/7C/7G/8D 同一条）", abs(E1_K / E1_N - 0.50) < 1e-12)
    chk("K_NEW = 50 = chunk_size", K_NEW == 50)
    chk("K_REF = 10 = 既有工作点", K_REF == 10)
    chk("检查点尾串 = checkpoints/022000/pretrained_model", CK_SUFFIX == "checkpoints/022000/pretrained_model")
    chk("三臂互不相同", len({r for _, _, r in ARMS}) == 3)
    chk("三臂都是 mix60f120r_c1（同数据集才允许比高低，坑 33）",
        all("mix60f120r_c1" in r for _, _, r in ARMS))
    chk("K=10 参照 = S8_VERDICT:16 公布的 65/65/64",
        {sd: v[0] for sd, v in PUB_REV.items()} == {2000: 65, 4000: 65, 5000: 64})
    chk("k50_rev 给 4 个目录", len(k50_rev("s8c_seed2000")) == 4)
    chk("k50_rev 首读不带 _rep、第二读带 _rep2",
        not k50_rev("s8c_seed2000")[0].endswith("_rep2") and k50_rev("s8c_seed2000")[1].endswith("_rep2"))
    chk("k50_rev 目录名含 _k50（K 是文件名的一部分，别和 K=10 撞名）",
        all("_k50" in d for d in k50_rev("s8d_seed4000")))
    chk("k50_rev 与 K=10 的 rev_dirs 完全不重叠",
        not (set(k50_rev("s8c_seed2000")) & set(rev_dirs("s8c_seed2000"))))
    chk("k50_fwd 只 1 读（正向是护栏，不是主口径）", len(k50_fwd("s8c_seed2000")) == 1)
    chk("_split4 摊得回原数且不超每 rep 上限", sum(_split4(65)) == 65 and max(_split4(65)) <= EPS)
    chk("_split4 少于 4 rep 也摊得回", sum(_split4(12)) == 12)

    # ── ② band_e2：边界含在更坏的那一档 ──
    chk("Δ=−20.0 ⇒ CRASH（边界含在更坏档）", band_e2(-20.0) == "CRASH")
    chk("Δ=−20.1 ⇒ CRASH", band_e2(-20.1) == "CRASH")
    chk("Δ=−19.9 ⇒ GREY", band_e2(-19.9) == "GREY")
    chk("Δ=−10.0 ⇒ GREY（边界含在更坏档）", band_e2(-10.0) == "GREY")
    chk("Δ=−9.9 ⇒ NONINF", band_e2(-9.9) == "NONINF")
    chk("Δ=0 ⇒ NONINF", band_e2(0.0) == "NONINF")
    chk("Δ>0（K=50 更好）⇒ NONINF", band_e2(+12.5) == "NONINF")
    chk("Δ=None ⇒ UNKNOWN", band_e2(None) == "UNKNOWN")
    chk("Δ=nan ⇒ UNKNOWN", band_e2(float("nan")) == "UNKNOWN")

    # ── ③ gate_e1 / gate_e2 / delta_pp ──
    chk("E1：min=40/80 ⇒ PASS（正好压线算过）", gate_e1({2000: (40, 80), 4000: (65, 80), 5000: (64, 80)})["pass"] is True)
    chk("E1：min=39/80 ⇒ FAIL", gate_e1({2000: (39, 80), 4000: (65, 80), 5000: (64, 80)})["pass"] is False)
    _u = gate_e1({2000: None, 4000: (65, 80), 5000: (64, 80)})
    chk("E1：任一臂缺读数 ⇒ UNKNOWN 且 min_k=None（不当 0、不当过，坑 40③）",
        _u["state"] == "UNKNOWN" and _u["min_k"] is None and _u["pass"] is None)
    chk("E1：局数不齐（60/60）也算 UNKNOWN", gate_e1({2000: (60, 60), 4000: (65, 80), 5000: (64, 80)})["state"] == "UNKNOWN")
    chk("E1：UNKNOWN 会点名是哪几臂", _u["short"] == [2000])
    chk("E2：取三臂最坏档（CRASH > GREY > NONINF）",
        gate_e2({2000: "NONINF", 4000: "CRASH", 5000: "GREY"})["worst"] == "CRASH")
    chk("E2：最坏是 GREY ⇒ pass=False 但不叫塌陷", gate_e2({2000: "NONINF", 4000: "GREY", 5000: "NONINF"})["pass"] is False)
    chk("E2：三臂全 NONINF ⇒ pass=True", gate_e2({2000: "NONINF", 4000: "NONINF", 5000: "NONINF"})["pass"] is True)
    chk("E2：任一臂 UNKNOWN ⇒ 整体 UNKNOWN（不许用好臂掩盖坏臂）",
        gate_e2({2000: "NONINF", 4000: "UNKNOWN", 5000: "CRASH"})["state"] == "UNKNOWN")
    chk("delta_pp：40/80 vs 52/80 = −15.0", abs(delta_pp((40, 80), (52, 80)) + 15.0) < 1e-9)
    chk("delta_pp：n=0 ⇒ None（不当 0）", delta_pp((0, 0), (52, 80)) is None and delta_pp((40, 80), (0, 0)) is None)
    chk("delta_pp：缺读 ⇒ None", delta_pp(None, (52, 80)) is None)

    # ── ④ e3_pooled / ms_per_step / xcheck ──
    _e3 = e3_pooled([(0, 80)] * 3, [(13, 80)] * 3)
    chk("E3：0/240 vs 39/240 ⇒ p 很小且判 K50 更低", _e3["p"] < 0.001 and _e3["lower"] is True)
    chk("E3：两侧全 0 ⇒ p=1.0（不是 None，不是显著）", e3_pooled([(0, 240)], [(0, 240)])["p"] == 1.0)
    chk("E3：一侧没局数 ⇒ p=None（只读量也不许编数）", e3_pooled([(0, 0)], [(3, 240)])["p"] is None)
    chk("E3：池化把三臂加起来", _e3["k10"] == (39, 240) and _e3["k50"] == (0, 240))
    _fake = {"a": {"seconds": 100.0, "per_episode": [{"steps": 400}] * 5},      # 2000 步 / 100 s = 50 ms
             "b": {"seconds": 100.0, "per_episode": [{"steps": 400}] * 5}}
    _ms = ms_per_step(["a", "b"], loader=lambda d: _fake.get(d))
    chk("ms/step：Σ秒×1000/Σ步 = 50.0", abs(_ms["ms_per_step"] - 50.0) < 1e-9 and _ms["steps"] == 4000)
    chk("ms/step：产物不在 ⇒ 跳过并单列，不炸", ms_per_step(["zzz"], loader=lambda d: None)["skip"][0][1] == "产物不在")
    _ms2 = ms_per_step(["c"], loader=lambda d: {"seconds": None, "per_episode": [{"steps": 10}]})
    chk("ms/step：缺 seconds ⇒ 跳过（不算进分母）", _ms2["reads_used"] == 0 and "缺 seconds" in _ms2["skip"][0][1])
    _ms3 = ms_per_step(["x"], loader=lambda d: None)
    chk("ms/step：一条都不剩 ⇒ nan（不当 0）", _ms3["ms_per_step"] != _ms3["ms_per_step"])
    chk("xcheck：逐臂相符 ⇒ 无问题", xcheck({2000: (65, 80), 4000: (65, 80), 5000: (64, 80)}, PUB_REV) == [])
    chk("xcheck：数目不符 ⇒ 点名并给出期望值",
        any("不符" in b and "65/80" in b for b in xcheck({2000: (60, 80), 4000: (65, 80), 5000: (64, 80)}, PUB_REV)))
    chk("xcheck：盘上没读到 ⇒ 也要报（不静默跳过）",
        any("盘上没读到" in b for b in xcheck({4000: (65, 80), 5000: (64, 80)}, PUB_REV)))
    chk("fmt_kn：缺读（n=0）印 —，不印 0/20", fmt_kn({"k": 0, "n": 0}) == "—")
    chk("fmt_kn：真跑了 20 局 0 成功 ⇒ 如实印 0/20（两种 n=0 不许印成一样）",
        fmt_kn({"k": 0, "n": 20}) == "0/20")

    # ── ⑤ 端到端场景（走完整条 report()，含退出码）──
    rc, out = run_scene(lambda r: _build(r, {2000: 66, 4000: 64, 5000: 65},
                                         {2000: 15, 4000: 11, 5000: 14}, tip50={2000: 3}))
    chk("场景A 非劣：rc=0（判定成立）", rc == 0)
    chk("场景A：E1 PASS 且报出 min", "S10_E1=PASS" in out and "64/80" in out)
    chk("场景A：E2 三臂 NONINF ⇒ ✅ 非劣", "S10_E2=NONINF" in out and "✅ 非劣" in out)
    chk("场景A：E4 算出 35.4 ms 并判 PASS（3000 s / 84750 步）", "S10_E4=35.4ms PASS" in out)
    chk("场景A：出身核对 0 条、对账通过 ⇒ TRUST=YES", "S10_TRUST=YES" in out and "出身核对问题：**0**" in out)
    chk("场景A：E3 无显著差（3/240 vs 0/240）", "S10_E3=" in out and "无显著差" in out)
    chk("场景A：正向非全 0 ⇒ 不触发 E5 那句极限", "S10_FWD_ALL_ZERO=NO" in out)
    chk("场景A：K=10 参照确实是从盘上读的（逐 rep 打出来了）", "逐 rep" in out and "Wilson 95%" in out)

    rc, out = run_scene(lambda r: _build(r, {2000: 65, 4000: 40, 5000: 56}, {2000: 0, 4000: 0, 5000: 0}))
    chk("场景B 塌陷：min=40 仍压线过 E1", "S10_E1=PASS" in out and "k=40/80" in out)
    chk("场景B：−31.25 pp 判 CRASH", "S10_ARM4000_BAND=CRASH" in out)
    chk("场景B：−10.0 pp 判 GREY（边界归更坏档）", "S10_ARM5000_BAND=GREY" in out)
    chk("场景B：取最坏 ⇒ ❌ 塌陷", "S10_E2=CRASH" in out and "❌ 塌陷" in out)
    chk("场景B：正向三臂全 0 ⇒ 打出「只在反向可用」", "S10_FWD_ALL_ZERO=YES" in out and "只在反向可用" in out)
    chk("场景B：正向那 0/20 是**真读数**⇒ 如实印出来", "0/20" in out)
    chk("场景B：塌陷但读数齐 ⇒ rc=0（结论成立，只是结论是塌陷）", rc == 0)

    rc, out = run_scene(lambda r: _build(r, {2000: 65, 4000: 65, 5000: 56}, {2000: 9, 4000: 9, 5000: 9}))
    chk("场景B2 灰区：最坏 GREY ⇒ ⚠️ 灰区（记为极限）", "S10_E2=GREY" in out and "灰区" in out)

    rc, out = run_scene(lambda r: _build(r, k50=False))
    chk("场景C K=50 全缺：rc=3 不采信", rc == 3)
    chk("场景C：E1=UNKNOWN 且**没有**被当成 0/80", "S10_E1=UNKNOWN" in out and "S10_E1=UNKNOWN k=" not in out)
    chk("场景C：TRUST=NO + 报告打 🚫", "S10_TRUST=NO" in out and "判定不采信" in out)
    chk("场景C：缺产物目录被逐个点名", "K=50 缺产物：**15**" in out)
    chk("场景C：缺读的正向/严格列印 —，全文不许出现「0/20」（缺读当 0 计就是坑 40③）", "0/20" not in out)
    chk("场景C：绝不印 ✅ PASS", "✅ PASS" not in out)

    _leg = k50_rev("s8c_seed2000")[3]
    rc, out = run_scene(lambda r: _build(r, {2000: 65, 4000: 65, 5000: 64},
                                         {2000: 12, 4000: 12, 5000: 12}, legacy50={_leg}))
    chk("场景D 老产物缺放宽字段：rc=2 读数不齐", rc == 2)
    chk("场景D：E1=UNKNOWN，缺字段**不当 0 计**（坑 40③）", "S10_E1=UNKNOWN" in out and "不当 0 计" in out)
    chk("场景D：缺字段被单列出来", "K=50 缺字段：**1**" in out)
    chk("场景D：出身核对仍干净 ⇒ TRUST=YES（区分「产物是老口径」和「读错权重」）", "S10_TRUST=YES" in out)

    rc, out = run_scene(lambda r: _build(r, {2000: 66, 4000: 64, 5000: 65},
                                         {2000: 15, 4000: 11, 5000: 14}, rev10={2000: 60, 4000: 65, 5000: 64}))
    chk("场景E K=10 参照对不上已公布值：rc=3 不采信", rc == 3)
    chk("场景E：点名是哪一臂、期望多少", "seed2000" in out and "与已公布 65/80 不符" in out)
    chk("场景E：TRUST=NO", "S10_TRUST=NO" in out)

    print(f"[selftest] {npass} passed, {nfail} failed")
    return 1 if nfail else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="用临时夹具自测判据本身（不碰真 runs/）")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    return report()


if __name__ == "__main__":
    raise SystemExit(main())
