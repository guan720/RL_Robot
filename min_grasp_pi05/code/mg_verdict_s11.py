#!/usr/bin/env python3
"""档 11 判定：语言泛化（同义改写指令）——策略学的是**任务**还是**那两句原话**？

预注册出处：`runs/S11_PREREG.md`（**2026-10-07 20:04 落盘，早于本档任何读数**；看完数不许改门，坑 40）。
唯一变量 = **指令串**；检查点/数据集/场景/seed 窗/局数/K/判据与关门读数**逐字相同**（原话读数从盘上并入、不重跑）。

判据（阈值写死在预注册 §3）：
  **L1（主门，筛查）** = 6 句改写各自 **3 臂池化 60 局**的放宽成功率 **≥ 30/60 = 50%**
  **L1b（副，只读）**   = 同一句的**最差臂** 20 局 ≥ 10/20；不过只记「臂间不稳」，**不改 L1**
  **L2（只读方向）**    = 每句 vs **原话 rep1** 在同一批 (臂, seed) 上配对：|Δ| ≤ 15 pp ⇒「无差别」，
                          > 15 pp ⇒「有差别」并报 McNemar 精确双侧 p（15 pp 沿用档 7F 的 2σ 带，不新造）
  **L3（只读，但决定结论写法）** = 负对照（RN/FN 各 20 局）：≤ 20% ⇒ 语言条件成立；≥ 50% ⇒ **假条件化**；其间 ⇒ 不确定
  **L4（出身核对）**    = task 串逐字 == 预注册那句 ∧ sidecar 证明 patch 真生效 ∧ task_mode/K/seed/episodes/ckpt 尾串全对；
                          另与 `runs/S8_VERDICT.md:16` 的原话参照（65/65/64、正向 16/12/16）逐臂对账 ⇒ 不过 = 🚫 不采信
退出码：0 = 判定成立；2 = 读数不齐（**L1 = UNKNOWN，不许当 0 计**，坑 40③）；3 = 出身/对账不过 ⇒ 不采信。

⚠️ 三臂同为 `mix60f120r_c1` ⇒ 臂间可比高低；与 7H（`mix60f120r`）**只比形状**（坑 33）。
⚠️ L1 是**筛查**不是证明：n=60/句 ⇒ 1σ ≈ 6.5 pp；「过门」≠「与原话等价」（那需要 ≥400 局/句，本档不做）。

用法：
    $MG_PY code/mg_verdict_s11.py --selftest
    $MG_PY code/mg_verdict_s11.py > runs/S11_VERDICT.md
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

from mg_eval_lang import (ARMS, CK_STEP, CODE_ORDER, DST, EPS,          # noqa: E402  单一真源（指令/臂/目录名）
                          EXPECT_FWD, EXPECT_REV, INSTR, K_EVAL, NEG_ARM,
                          plan_patch, plan_reads, scene_of)
from mg_verdict_s2 import fisher_two_sided                              # noqa: E402
from mg_verdict_s2f import (ci, collect, load, mcnemar_nested, pct,     # noqa: E402
                            seed_table)
from mg_verdict_s7f import (FWD_SEED0, REPS, REV_SEED0,                 # noqa: E402
                            fwd_dirs, rev_dirs)
from mg_verdict_s10 import (K_REF, PUB_FWD, PUB_REV,                     # noqa: E402  同一套参照常数不重写第二遍（坑 54）
                            fmt_kn, xcheck)

# ── 预注册常数（出处 runs/S11_PREREG.md §3）───────────────────────────────────
L1_K, L1_N = 30, 60          # 主门：每句 3 臂池化 ≥ 30/60 = 50%
L1B_K, L1B_N = 10, 20        # 副读：最差臂 ≥ 10/20
L2_BAND_PP = 15.0            # 2σ 带（档 7F 的事前规则，不新造）
L3_OK_PC, L3_FAKE_PC = 20.0, 50.0
PARA_CODES = tuple(c for c in CODE_ORDER if not c.endswith("N"))    # R1 R2 R3 F1 F2 F3
NEG_CODES = tuple(c for c in CODE_ORDER if c.endswith("N"))         # RN FN
ORIG = {"rev": "Take the can out of the bin and put it back into the tray.",
        "fwd": "Pick up the can and place it into the bin."}
EXPECT_ATTR = {"rev": "mg_env_reverse.TASK_REVERSE", "fwd": "mg_eval.TASK"}


def ref_dir_list(arm: str, scene: str) -> list:
    """原话参照读（盘上已有、**不重跑**）：反向 4 rep、正向 1 rep。"""
    return rev_dirs(arm) if scene == "rev" else fwd_dirs(arm)


def load_sidecar(d: str):
    p = RUNS / d / "lang_sidecar.json"
    if not p.exists():
        return None
    try:
        return json_loads(p.read_text())
    except Exception as exc:
        return {"_error": f"读不动 {p}: {exc}"}


def json_loads(t: str):
    return json.loads(t)


# ─────────────────────────── 纯函数（判据）───────────────────────────
def gate_l1(pooled: dict) -> dict:
    """主门：6 句改写各自池化 60 局 ≥ 30。任一句局数不齐 ⇒ UNKNOWN（不当 0、不当过，坑 40③）。"""
    short = [c for c in PARA_CODES if pooled.get(c) is None or pooled[c][1] != L1_N]
    if short:
        return {"pass": None, "state": "UNKNOWN", "short": short, "fails": [],
                "detail": {c: pooled.get(c) for c in PARA_CODES}}
    fails = [c for c in PARA_CODES if pooled[c][0] < L1_K]
    return {"pass": not fails, "state": "PASS" if not fails else "FAIL", "short": [], "fails": fails,
            "detail": {c: pooled[c] for c in PARA_CODES}}


def gate_l1b(per_arm: dict) -> dict:
    """副读：每句的**最差臂** ≥ 10/20。缺读的句子单列 `short`，不当 0。"""
    out = {}
    for c in PARA_CODES:
        cells = per_arm.get(c) or {}
        miss = [a for a in ARMS if cells.get(a) is None or cells[a][1] != L1B_N]
        if miss:
            out[c] = {"state": "UNKNOWN", "worst": None, "missing": miss}
            continue
        wa = min(ARMS, key=lambda a: cells[a][0])
        out[c] = {"state": "PASS" if cells[wa][0] >= L1B_K else "FAIL", "worst_arm": wa,
                  "worst": cells[wa], "missing": []}
    return out


def band_l2(delta_pp) -> str:
    if delta_pp is None or delta_pp != delta_pp:
        return "UNKNOWN"
    return "SAME" if abs(delta_pp) <= L2_BAND_PP else ("LOWER" if delta_pp < 0 else "HIGHER")


def paired_l2(para_tab: dict, ref_tab: dict) -> dict:
    """按 (臂, seed) 配对：b = 改写成功∧原话失败，c = 改写失败∧原话成功。缺 seed 的局**不计入**（不当 0）。"""
    b = c = npair = 0
    miss = []
    for arm in ARMS:
        pa, re_ = para_tab.get(arm) or {}, ref_tab.get(arm) or {}
        if not pa or not re_:
            miss.append(arm)
            continue
        for sd in sorted(set(pa) & set(re_)):
            if not pa[sd] or not re_[sd]:
                miss.append(f"{arm}/seed{sd}")
                continue
            npair += 1
            if pa[sd][0] and not re_[sd][0]:
                b += 1
            elif re_[sd][0] and not pa[sd][0]:
                c += 1
    if npair <= 0:
        return {"npair": 0, "b": b, "c": c, "delta_pp": None, "p": None, "band": "UNKNOWN", "missing": miss}
    d = 100.0 * (b - c) / npair
    return {"npair": npair, "b": b, "c": c, "delta_pp": d, "p": mcnemar_nested(b, c),
            "band": band_l2(d), "missing": miss}


def gate_l3(neg: dict) -> dict:
    """负对照：≤20% ⇒ 语言条件成立；≥50% ⇒ 假条件化；其间 ⇒ 不确定。缺读 ⇒ UNKNOWN。"""
    per = {}
    for code in NEG_CODES:
        kn = neg.get(code)
        if kn is None or kn[1] <= 0:
            per[code] = {"state": "UNKNOWN", "kn": None}
            continue
        r = 100.0 * kn[0] / kn[1]
        per[code] = {"state": "COND_OK" if r <= L3_OK_PC else ("FAKE_COND" if r >= L3_FAKE_PC else "UNCERTAIN"),
                     "kn": kn, "rate": r}
    states = [v["state"] for v in per.values()]
    if "UNKNOWN" in states:
        overall = "UNKNOWN"
    elif "FAKE_COND" in states:
        overall = "FAKE_COND"
    elif "UNCERTAIN" in states:
        overall = "UNCERTAIN"
    else:
        overall = "COND_OK"
    return {"state": overall, "per": per}


def prov_lang(reads: list) -> list:
    """L4 出身核对：task 串逐字、sidecar 证明 patch 生效、task_mode/K/seed/episodes/ckpt 尾串。"""
    bad = []
    for r in reads:
        d = r["out"]
        j = load(d)
        if j is None:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: 产物不在")
            continue
        if "_error" in j:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: {j['_error']}")
            continue
        got = j.get("task")
        if got != r["instruction"]:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: summary.task={got!r} ≠ 预注册那句 {r['instruction']!r}"
                       "（⇒ patch 没生效或跑了别的句子，L1 会假过）")
        if j.get("task_mode") != r["task_mode"]:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: task_mode={j.get('task_mode')} ≠ {r['task_mode']}")
        if int(j.get("n_action_steps", -1)) != K_EVAL:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: K={j.get('n_action_steps')} ≠ {K_EVAL}")
        if int(j.get("seed", -1)) != r["seed0"]:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: seed={j.get('seed')} ≠ {r['seed0']}（seed 窗变了就不能配对）")
        if int(j.get("episodes", 0)) != EPS:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: episodes={j.get('episodes')} ≠ {EPS}")
        ck = str(j.get("policy_ckpt", "?"))
        if not ck.endswith(f"checkpoints/{CK_STEP:06d}/pretrained_model"):
            bad.append(f"[{r['code']}/{r['arm']}] {d}: policy_ckpt 尾串 …{ck[-46:]}，期望 …checkpoints/{CK_STEP:06d}/pretrained_model（坑 38/42）")
        if f"runs/{r['run']}/" not in ck:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: policy_ckpt 不在本臂 run 里（{ck}）")
        sc = load_sidecar(d)
        if sc is None:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: 没有 lang_sidecar.json ⇒ **无法证明 patch 生效**（不许采信）")
            continue
        if "_error" in sc:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: {sc['_error']}")
            continue
        if sc.get("orig_task") != ORIG[r["scene"]]:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: sidecar.orig_task={sc.get('orig_task')!r} ≠ 该场景原话")
        if sc.get("patched_task") != r["instruction"]:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: sidecar.patched_task ≠ 预注册那句")
        if sc.get("orig_task") == sc.get("patched_task"):
            bad.append(f"[{r['code']}/{r['arm']}] {d}: sidecar 里 orig == patched ⇒ 这一格其实跑的是原话（重复参照，不是改写）")
        if sc.get("post_patch_readback") != r["instruction"]:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: sidecar.post_patch_readback ≠ 改写句 ⇒ patch 回读不符")
        if sc.get("module_attr") != EXPECT_ATTR[r["scene"]]:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: patch 打在 {sc.get('module_attr')} 而不是 {EXPECT_ATTR[r['scene']]}")
        if sc.get("summary_task_field") is not None and sc.get("summary_task_field") != got:
            bad.append(f"[{r['code']}/{r['arm']}] {d}: sidecar 记的 summary.task 与盘上的不一致")
    return bad


AMPL = {"R1": "最小（1 词）", "R2": "中（动词+介词）", "R3": "大（短语+语序）", "RN": "负对照（无关指令）",
        "F1": "最小（1 词）", "F2": "中（动词+**名词** bin→basket）", "F3": "大（句式+起点状语）",
        "FN": "负对照（无关指令）"}


def decide(l1: dict, l3: dict, trust: bool, bad_n: int) -> str:
    """预注册 §3 的决策树（照抄，不许事后合理化）。"""
    if not trust:
        return f"🚫 **判定不采信**（出身核对 {bad_n} 条问题）⇒ 先查工具/权重，不下任何结论"
    if l1["state"] == "UNKNOWN":
        return "⏳ **读数不齐**（缺的句子单列，**不当 0 计**，坑 40③）⇒ 补跑后再判"
    if l3["state"] == "UNKNOWN":
        return "⏳ 负对照缺读 ⇒ L3 不能判（L1 读数见上）"
    if l1["pass"] and l3["state"] == "FAKE_COND":
        return ("⚠️ **矛盾组合**（改写句过门 ∧ 无关指令也过门）⇒ 预注册 §3 规定**先查工具**"
                "（大概率 monkeypatch 没生效 / task 串没换），查完再判；**不许**直接写「语言不重要」")
    if l1["pass"]:
        extra = "（L3 不确定：负对照落在 20~50% 之间，只登记不改结论）" if l3["state"] == "UNCERTAIN" else ""
        return (f"✅ **不是记住那两句话**：6 句改写全部 ≥ {L1_K}/{L1_N}，负对照 {l3['state']} ⇒ "
                f"使命结论**加强**；`MISSION_VERDICT.md` §五 可新增一条「语言改写（3 句/场景、n=60/句）不掉门」{extra}")
    fails = l1["fails"]
    if fails == ["F2"]:
        return ("❌ **只有 F2 掉门**（`bin`→`basket` 的那句）⇒ 特别标注：**动词改写稳、名词替换不稳** ⇒ "
                "若做语言增广，优先补**名词同义词**（预注册 §3 决策树的这一支）")
    return (f"❌ **记为新极限**：{len(fails)} 句掉门（{'、'.join(fails)}）⇒ 「语言泛化未成立」写进 "
            "`MISSION_VERDICT.md` §五；**不加跑、不改判据**；处方 = 数据集 task 列语言增广 + 便宜配方重训"
            "（**另立预注册**，~7 h 训 + ~1 h 评；⚠️ 本档用过的 8 句必须整体排除出增广集，否则 TEST 就废了）")


def report() -> int:
    reads = plan_reads()
    by_code: dict = {}
    para_tab: dict = {}
    strict = {}
    tipped = {}
    for r in reads:
        c = collect([r["out"]], "n_success_relaxed", "pc_success_relaxed")
        by_code.setdefault(r["code"], {})[r["arm"]] = c
        para_tab.setdefault(r["code"], {})[r["arm"]] = seed_table([r["out"]], "success_relaxed")["tab"]
        strict[(r["code"], r["arm"])] = collect([r["out"]], "n_success", "pc_success")
        tipped[(r["code"], r["arm"])] = c["tipped"]

    # 原话参照（盘上已有、不重跑；坑 40①）
    ref_pool, ref_rep1_tab, ref_rep1_kn = {}, {}, {}
    for scene in ("rev", "fwd"):
        for arm in ARMS:
            ds = ref_dir_list(arm, scene)
            ref_pool[(scene, arm)] = collect(ds, "n_success_relaxed", "pc_success_relaxed")
            ref_rep1_tab[(scene, arm)] = seed_table([ds[0]], "success_relaxed")["tab"]
            rc1 = collect([ds[0]], "n_success_relaxed", "pc_success_relaxed")
            ref_rep1_kn[(scene, arm)] = None if rc1["n"] <= 0 else (rc1["k"], rc1["n"])

    def kn(c):
        return None if c["n"] <= 0 else (c["k"], c["n"])

    pooled, per_arm = {}, {}
    for code in CODE_ORDER:
        cells = by_code.get(code, {})
        ks = [kn(cells[a]) for a in ARMS if a in cells]
        ks = [x for x in ks if x is not None]
        pooled[code] = (sum(x[0] for x in ks), sum(x[1] for x in ks)) if ks else None
        per_arm[code] = {a: kn(cells[a]) for a in ARMS if a in cells}

    l1 = gate_l1(pooled)
    l1b = gate_l1b(per_arm)
    l2 = {}
    for code in PARA_CODES:
        sc = scene_of(code)
        l2[code] = paired_l2(para_tab.get(code, {}),
                             {a: ref_rep1_tab[(sc, a)] for a in ARMS})
    l3 = gate_l3({c: pooled.get(c) for c in NEG_CODES})

    # 参照的对账（与档 8 公布值逐臂相同，坑 40①）
    ref_disk_rev = {sd: kn(ref_pool[("rev", arm)]) for sd, arm in
                    zip((2000, 4000, 5000), ARMS)}
    ref_disk_fwd = {sd: kn(ref_pool[("fwd", arm)]) for sd, arm in
                    zip((2000, 4000, 5000), ARMS)}
    bad = list(prov_lang(reads))
    bad += xcheck(ref_disk_rev, PUB_REV)
    bad += [f"[正向参照] {x}" for x in xcheck(ref_disk_fwd, PUB_FWD)]
    # ⚠️ 这两行必须从**真的** collect 结果里取：写成 `collect([], "", "")["broken"]` 不会报错（键存在），
    # 但永远返回空表 ⇒ 「不变量违例 0 条」「缺字段 0 条」两项检查变成空转（比报错更坏，坑 65 家族）。
    broken = [b for r in reads for b in by_code.get(r["code"], {}).get(r["arm"], {}).get("broken", [])]
    missing = [r["out"] for r in reads
               if not (RUNS / r["out"] / "eval_summary.json").exists()]
    nofield = [x for r in reads for x in by_code.get(r["code"], {}).get(r["arm"], {}).get("nofield", [])]
    trust = not bad and not broken

    print("# 档 11 判定：语言泛化 —— 策略学的是**任务**，还是**那两句原话**？")
    print(f"\n<!-- 由 code/mg_verdict_s11.py 生成于 {datetime.now():%Y-%m-%d %H:%M}；"
          f"预注册 runs/S11_PREREG.md（2026-10-07 20:04 落盘，早于本档任何读数）-->")
    print(f"\n* 唯一变量 = **指令串**；检查点 = 三臂 `checkpoints/{CK_STEP:06d}`（数字格，坑 38/42/63）、K={K_EVAL}、"
          f"每读 {EPS} 局、反向 seed 7000..7019 / 正向 2000..2019（与关门读数**同一批** ⇒ 可配对）。")
    print(f"* 主口径 = **放宽 R**（送到为首要，侧躺另打 `delivered_tipped`）；严格与侧躺**并报**（坑 17）。")
    print(f"* 原话参照**从盘上并入、没重跑**（坑 40①），并与 `runs/S8_VERDICT.md:16` 逐臂对账"
          f"（反向 {PUB_REV[2000][0]}/{PUB_REV[4000][0]}/{PUB_REV[5000][0]}、正向 "
          f"{PUB_FWD[2000][0]}/{PUB_FWD[4000][0]}/{PUB_FWD[5000][0]}）。")

    print("\n## 一、指令集（预注册 §2.2，**跑前写死**）\n")
    print("| 代号 | 场景 | 指令串 | 改写幅度 |")
    print("|:--|:--|:--|:--|")
    for code in CODE_ORDER:
        sc = scene_of(code)
        tag = "反向" if sc == "rev" else "正向"
        print(f"| **{code}** | {tag} | `{INSTR[code]}` | {AMPL[code]} |")
    for sc, lab in (("rev", "反向"), ("fwd", "正向")):
        print(f"| {sc.upper()}0（参照） | {lab} | `{ORIG[sc]}` | **原话**（盘上已有，不重跑） |")

    print(f"\n## 二、主读数（放宽口径；每句池化 3 臂 × {EPS} 局 = {L1_N} 局，负对照 1 臂 {EPS} 局）\n")
    print(f"| 代号 | 池化 k/n | 逐臂 | 原话参照（rep1 池化） | Δ pp（配对） | b/c | McNemar p | L2 档 | 严格 | 侧躺 | **L1** |")
    print("|:--|---:|:--|---:|---:|:--|---:|:--|---:|--:|:--|")
    for code in CODE_ORDER:
        pc = pooled.get(code)
        cells = per_arm.get(code, {})
        arm_txt = "；".join(f"{a.split('_seed')[1]}:" + ("—" if cells.get(a) is None else f"{cells[a][0]}/{cells[a][1]}")
                            for a in ARMS)
        sc = scene_of(code)
        r1 = [ref_rep1_kn[(sc, a)] for a in ARMS]
        r1k = [x for x in r1 if x is not None]
        ref_txt = "—" if not r1k else f"{sum(x[0] for x in r1k)}/{sum(x[1] for x in r1k)}"
        if code in l2:
            d = l2[code]["delta_pp"]
            d_txt = "—" if d is None else f"{d:+.1f}"
            bc = f"{l2[code]['b']}/{l2[code]['c']}"
            p_txt = "—" if l2[code]["p"] is None else f"{l2[code]['p']:.4g}"
            band = l2[code]["band"]
        else:
            d_txt, bc, p_txt, band = "—", "—", "—", "（负对照不配对）"
        ks = sum(strict[(code, a)]["k"] for a in ARMS if (code, a) in strict)
        ns = sum(strict[(code, a)]["n"] for a in ARMS if (code, a) in strict)
        tp = sum(tipped[(code, a)] for a in ARMS if (code, a) in tipped)
        if code.endswith("N"):
            verdict = f"（L3：{l3['per'][code]['state']}）"
        elif l1["state"] == "UNKNOWN":
            verdict = "⏳ UNKNOWN" if code in l1["short"] or not l1["short"] else ("✅" if code not in l1["fails"] else "❌")
        else:
            verdict = "✅" if code not in l1["fails"] else "❌"
        print(f"| **{code}** | {fmt_kn({'k': pc[0], 'n': pc[1]}) if pc else '—'} | {arm_txt} | {ref_txt} | "
              f"{d_txt} | {bc} | {p_txt} | {band} | {ks}/{ns if ns else '—'} | {tp} | {verdict} |")
    print(f"\n* 池化 Wilson 95%：" + "；".join(
        f"{c} " + (ci(*pooled[c]) if pooled.get(c) else "—") for c in PARA_CODES))
    print(f"* **L1b（最差臂，只读）**：" + "；".join(
        f"{c} " + ("—" if l1b[c]["state"] == "UNKNOWN"
                   else f"{l1b[c]['worst'][0]}/{l1b[c]['worst'][1]}@{l1b[c]['worst_arm'].split('_seed')[1]} {l1b[c]['state']}")
        for c in PARA_CODES))

    print("\n## 三、判定（阈值来自 `runs/S11_PREREG.md` §3，跑前写死）\n")
    l1_txt = "—" if l1["state"] == "UNKNOWN" else "、".join(
        f"{c}={pooled[c][0]}/{pooled[c][1]}" for c in PARA_CODES if pooled.get(c))
    l1_verdict = (f"⏳ UNKNOWN（局数不齐/缺读：{'、'.join(l1['short'])} ⇒ **不当 0 计**，坑 40③）"
                  if l1["state"] == "UNKNOWN"
                  else ("✅ PASS（6 句全过）" if l1["pass"] else f"❌ FAIL（掉门：{'、'.join(l1['fails'])}）"))
    print(f"| **L1** 主门（筛查） | 每句 3 臂池化 {EPS}×3 = {L1_N} 局放宽 ≥ {L1_K}/{L1_N} = 50% | {l1_txt} | {l1_verdict} |")
    n_l3 = "；".join(f"{c} " + ("—" if l3["per"][c]["kn"] is None else
                               f"{l3['per'][c]['kn'][0]}/{l3['per'][c]['kn'][1]} = {l3['per'][c]['rate']:.1f}%")
                     for c in NEG_CODES)
    l3_txt = {"COND_OK": f"✅ 语言条件成立（≤ {L3_OK_PC:.0f}%）", "FAKE_COND": f"🚫 **假条件化**（≥ {L3_FAKE_PC:.0f}%）",
              "UNCERTAIN": f"⚠️ 不确定（{L3_OK_PC:.0f}~{L3_FAKE_PC:.0f}% 之间）", "UNKNOWN": "⏳ 缺读"}[l3["state"]]
    print(f"| **L3** 只读 | 负对照（无关指令）放宽成功率 | {n_l3} | {l3_txt} |")
    n_same = len([c for c in PARA_CODES if l2[c]["band"] == "SAME"])
    print(f"| **L2** 只读方向 | 每句 vs 原话 rep1 配对，|Δ| ≤ {L2_BAND_PP:.0f} pp 记「无差别」 | "
          f"{n_same}/{len(PARA_CODES)} 句在带内" + "；".join(
              f"；{c} {l2[c]['delta_pp']:+.1f} pp p={l2[c]['p']:.3g}" for c in PARA_CODES if l2[c]["delta_pp"] is not None)
          + f" | 🔎 只读（n={L1_N} ⇒ 1σ ≈ 6.5 pp，不许当等价证明） |")
    print(f"| **L4** 出身核对 | task 串逐字 + sidecar 证明 patch 生效 + mode/K/seed/局数/ckpt 尾串 + 参照对账 | "
          f"问题 **{len(bad)}** 条 | {'✅ 全对' if not bad else '🚫 不过 ⇒ 判定不采信'} |")
    print(f"\n### 决策（预注册 §3 的决策树，照抄）\n\n{decide(l1, l3, trust, len(bad))}\n")

    print("### 机器可读\n```")
    print(f"S11_DATE={datetime.now():%Y-%m-%d %H:%M}")
    print(f"S11_K={K_EVAL} S11_CK={CK_STEP:06d} S11_READS={len(reads)} S11_EPS_TOTAL={sum(r['episodes'] for r in reads)}")
    for code in CODE_ORDER:
        pc = pooled.get(code)
        print(f"S11_{code}={'NA' if not pc else f'{pc[0]}/{pc[1]}'} "
              f"S11_{code}_BAND={l2[code]['band'] if code in l2 else 'NEG'} "
              f"S11_{code}_DELTA={'NA' if code not in l2 or l2[code]['delta_pp'] is None else round(l2[code]['delta_pp'], 2)}")
    print(f"S11_L1={l1['state']}" + ("" if not l1["fails"] else f" fails={','.join(l1['fails'])}"))
    print(f"S11_L1B={'UNKNOWN' if any(l1b[c]['state'] == 'UNKNOWN' for c in PARA_CODES) else ('PASS' if all(l1b[c]['state'] == 'PASS' for c in PARA_CODES) else 'ARM_UNSTABLE')}")
    print(f"S11_L3={l3['state']}")
    print(f"S11_TRUST={'YES' if trust else 'NO'}")
    print("```")

    print("\n## 四、出身与不变量\n")
    print(f"* 出身核对问题：**{len(bad)}** 条" + (f" ⇒ 🚫 **判定不采信**\n" if bad else "（必须 0）✅\n"))
    for b in bad[:14]:
        print(f"  * 🚫 {b}")
    print(f"* 不变量「放宽 ⊇ 严格」违例：**{len(broken)}** 条（必须 0）" + ("✅" if not broken else "🚫"))
    for b in broken[:6]:
        print(f"  * 🚫 {b}")
    print(f"* 缺产物：**{len(missing)}** 个目录" + (f" ⇒ {missing[:6]}" if missing else "（无）✅"))
    print(f"* 缺字段：**{len(nofield)}** 条" + (f" ⇒ {nofield[:6]}" if nofield else "（无）✅"))
    print(f"* 负对照只在 `{NEG_ARM}` 名下（多臂/缺臂都算不符）："
          f"{'✅' if all(len([r for r in reads if r['code'] == c]) == 1 for c in NEG_CODES) else '🚫'}")

    print("\n## 五、判读纪律（预注册 §5，别事后合理化）\n")
    print(f"* **L1 是筛查不是证明**：n={L1_N}/句 ⇒ 1σ ≈ 6.5 pp（p≈0.8）；「过门」只说明没掉到 50% 以下，"
          f"**不等于**与原话等价（要证等价需 ≥400 局/句，本档不做）。")
    print(f"* **L2 的配对只在 rep1 上成立**：原话反向有 4 rep、本档取 rep1（同一批 seed）⇒ 配对有效，"
          f"但 rep1 只是 4 次独立读里的一次（坑 29：单读 1σ ≈ 4 pp）⇒ Δ 含 rep 间抖动，**只读方向**。")
    print(f"* **池化 vs min 的口径差**：使命门用 **min-over-臂**（保守），本档 L1 用**池化**（n=60）⇒ L1b 必须并报，"
          f"不许只报池化值。")
    print(f"* 跨数据集禁比高低（坑 33）：三臂同为 `{DST}` ⇒ 臂间可比；与 7H（`mix60f120r`）**只比形状**。")
    print(f"* 本档**不进任何既有门**：使命门（40/80）、D1–D4、H1–H4、C1–C4、E1–E5 一字未动。")

    print("\n## 六、复现\n```bash\nsource code/env.sh\n$MG_PY code/mg_eval_lang.py --selftest\n$MG_PY code/mg_verdict_s11.py --selftest\n$MG_PY code/mg_eval_lang.py --print-plan      # 20 读清单（链按它发车）\n$MG_PY code/mg_verdict_s11.py > runs/S11_VERDICT.md\n```")

    if not trust:
        return 3
    if l1["state"] == "UNKNOWN":
        return 2
    return 0


# ── 自测夹具 ──────────────────────────────────────────────────────────────────
# 门若判错，比没有门更糟（坑 65 家族：判据代码里不留没被测过的表达式）。两层：
#   ① 纯函数边界：30/60 压线归属、±15 pp 带界、UNKNOWN 传染、缺读不当 0、负对照 20%/50% 档界；
#   ② 临时夹具跑完整条 report()：退出码 0 / 2 / 3 三条路都走一遍（含 sidecar 自伤、参照对账、不变量违例）。
# 夹具只写 tempdir，并同时 patch `mg_verdict_s2f.RUNS`（`load` 在调用时才解析该全局 ⇒ collect/seed_table
# 一起指向夹具）与本模块的 `RUNS`（`load_sidecar`/缺产物检查用它）——**不碰真 runs/、不断言盘上进度**（坑 77）。
_ARM_SEED = dict(zip(ARMS, (2000, 4000, 5000)))
REF_REV = {arm: PUB_REV[sd][0] for arm, sd in _ARM_SEED.items()}   # 65/65/64（80 局 = REPS×EPS）
REF_FWD = {arm: PUB_FWD[sd][0] for arm, sd in _ARM_SEED.items()}   # 16/12/16（20 局 = 1 读）
REP1_REV = 17          # 夹具里参照 rep1 的成功数（L2 的配对只在 rep1 上成立 ⇒ 单独指定）
NEG_DEFAULT = {"RN": 1, "FN": 0}


def _splitn(total: int, nrep: int, rep1: int = None) -> list:
    """把 total 局成功摊到 nrep 个 rep（每 rep ≤ EPS），可指定 rep1 的值。逐 rep 分布不影响任何池化门。"""
    first = min(EPS, max(0, total)) if rep1 is None else rep1
    out, left = [first], total - first
    for _ in range(nrep - 1):
        take = min(EPS, max(0, left))
        out.append(take)
        left -= take
    return out


def _mk_raw(root: Path, name: str, ns_rel: int, ne: int, *, k: int, seed: int, mode: str, ckpt: str,
            task: str, tipped: int = 0, legacy: bool = False, strict_override=None,
            sum_patch=None, sidecar=None) -> None:
    """造一个 `eval_summary.json`（字段名与真产物逐字相同）+ 可选 sidecar。"""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    ns_strict = (ns_rel - tipped) if strict_override is None else strict_override
    per = [{"ep": i, "seed": seed + i, "success": i < ns_strict, "success_relaxed": i < ns_rel,
            "delivered_tipped": ns_strict <= i < ns_rel, "steps": 300, "max_lift_cm": 9.0,
            "min_dist_to_target_xy": 0.01} for i in range(ne)]
    j = {"n_action_steps": k, "episodes": ne, "task_mode": mode, "seed": seed, "seed_mode": "random",
         "policy_ckpt": ckpt, "seconds": 250.0, "task": task, "n_success": ns_strict,
         "pc_success": ns_strict / ne, "n_delivered_tipped": tipped,
         "n_ever_in_target_box": ns_rel, "per_episode": per}
    if not legacy:      # legacy = 「改判据前跑的」老产物：没有放宽字段（坑 40③ 的靶子）
        j["n_success_relaxed"] = ns_rel
        j["pc_success_relaxed"] = ns_rel / ne
    j.update(sum_patch or {})
    (d / "eval_summary.json").write_text(json.dumps(j, ensure_ascii=False))
    if sidecar is not None:
        (d / "lang_sidecar.json").write_text(json.dumps(sidecar, ensure_ascii=False))


def _sidecar_of(read: dict, task_field: str) -> dict:
    """照 `mg_eval_lang.main()` 真写的那几个字段造 sidecar（字段名必须逐字相同，否则 L4 会假过）。"""
    return {"tool": "mg_eval_lang.py", "task_mode": read["task_mode"],
            "module_attr": EXPECT_ATTR[read["scene"]], "orig_task": ORIG[read["scene"]],
            "patched_task": read["instruction"], "post_patch_readback": read["instruction"],
            "summary_task_field": task_field, "mg_eval_rc": 0}


def _mk_read(root: Path, read: dict, ns_rel: int, *, tipped: int = 0, legacy: bool = False,
             strict_override=None, sum_patch=None, side_patch=None, no_sidecar: bool = False) -> None:
    task_field = (sum_patch or {}).get("task", read["instruction"])
    sc = None if no_sidecar else dict(_sidecar_of(read, task_field), **(side_patch or {}))
    _mk_raw(root, read["out"], ns_rel, read["episodes"], k=read["k"], seed=read["seed0"],
            mode=read["task_mode"], ckpt=read["ckpt"], task=read["instruction"], tipped=tipped,
            legacy=legacy, strict_override=strict_override, sum_patch=sum_patch, sidecar=sc)


def _mk_ref(root: Path, arm: str, scene: str, total_k: int, rep1: int = None) -> None:
    """原话参照读（反向 REPS 个、正向 1 个），K=10、seed 窗与关门读数相同。"""
    ds = ref_dir_list(arm, scene)
    seed0 = REV_SEED0 if scene == "rev" else FWD_SEED0
    mode = "reverse" if scene == "rev" else "forward"
    ck = f"/x/runs/pi05_{DST}_{arm}/checkpoints/{CK_STEP:06d}/pretrained_model"
    for name, kk in zip(ds, _splitn(total_k, len(ds), rep1)):
        _mk_raw(root, name, kk, EPS, k=K_REF, seed=seed0, mode=mode, ckpt=ck, task=ORIG[scene])


def _build(root: Path, *, para=None, neg=None, ref_rev=None, ref_fwd=None, rep1_rev=None,
           skip_plan: bool = False, patches=None) -> None:
    """默认夹具 = **场景 A 全过**：每句改写逐臂 == 该臂参照 rep1 的成功数 ⇒ 配对 b=c=0、Δ=0。

    para    : {code: {arm: ns_rel}} 覆盖某句的逐臂成功数
    neg     : {code: ns_rel} 覆盖负对照
    ref_*   : {arm: 总成功数} 覆盖参照（用来造「对不上已公布值」）
    patches : {(code, arm): kwargs} 单格破坏（传给 `_mk_read`，出身核对的靶子）
    """
    patches = patches or {}
    rr = dict(REF_REV, **(ref_rev or {}))
    rf = dict(REF_FWD, **(ref_fwd or {}))
    r1 = REP1_REV if rep1_rev is None else rep1_rev
    for arm in ARMS:
        _mk_ref(root, arm, "rev", rr[arm], rep1=r1)
        _mk_ref(root, arm, "fwd", rf[arm])
    if skip_plan:
        return
    para = para or {}
    negd = dict(NEG_DEFAULT, **(neg or {}))
    for read in plan_reads():
        code, arm = read["code"], read["arm"]
        if code in NEG_CODES:
            ns = negd[code]
        else:
            ns = para.get(code, {}).get(arm, r1 if read["scene"] == "rev" else rf[arm])
        _mk_read(root, read, ns, **patches.get((code, arm), {}))


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
        """在 tempdir 里造夹具、把两处 RUNS 指过去、跑完整条 report()，返回 (退出码, stdout)。"""
        global RUNS      # 本模块的 RUNS 也要改：`load_sidecar`/缺产物检查用的是它，不是 s2f 的那份
        with tempfile.TemporaryDirectory() as td:
            old2f, old11 = mg_verdict_s2f.RUNS, RUNS
            mg_verdict_s2f.RUNS = Path(td)
            RUNS = Path(td)
            try:
                build(Path(td))
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = report()
            finally:
                mg_verdict_s2f.RUNS, RUNS = old2f, old11
            return rc, buf.getvalue()

    reads = plan_reads()
    by_out = {r["out"]: r for r in reads}

    # ── ① 常数 / 单一真源对账（走样 ⇒ 链跑了 A 目录、判定读 B 目录 ⇒ 永远 UNKNOWN）──
    chk("L1 主门 = 30/60 = 50%（预注册 §3）", abs(L1_K / L1_N - 0.50) < 1e-12 and (L1_K, L1_N) == (30, 60))
    chk("L1b = 最差臂 10/20", (L1B_K, L1B_N) == (10, 20))
    chk("L2 带 = ±15 pp（沿用档 7F 的 2σ 带，不新造）", L2_BAND_PP == 15.0)
    chk("L3 档界 = 20% / 50%", (L3_OK_PC, L3_FAKE_PC) == (20.0, 50.0))
    chk("6 句改写 + 2 句负对照", PARA_CODES == ("R1", "R2", "R3", "F1", "F2", "F3") and NEG_CODES == ("RN", "FN"))
    chk("20 读 = 6 句×3 臂 + 2 句×1 臂", len(reads) == 20 == 6 * len(ARMS) + len(NEG_CODES))
    chk("负对照只在 NEG_ARM 名下、各 1 读",
        all([r["arm"] for r in reads if r["code"] == c] == [NEG_ARM] for c in NEG_CODES) and NEG_ARM in ARMS)
    chk("每句改写恰好 3 臂、臂不重复",
        all(len({r["arm"] for r in reads if r["code"] == c}) == len(ARMS) == 3 for c in PARA_CODES))
    chk("20 个目录名互不相同（撞名 = 后跑的覆盖先跑的）", len(by_out) == 20)
    chk("目录名带 s11_ 前缀与 _k10（K 是名字的一部分，别和档 10 的 _k50 撞）",
        all(d.startswith("s11_") and f"_k{K_EVAL}" in d for d in by_out))
    chk("目录名不与参照读（K=10 原话）重叠",
        not (set(by_out) & {x for a in ARMS for s in ("rev", "fwd") for x in ref_dir_list(a, s)}))
    chk("每读 episodes=20、k=10", all(r["episodes"] == EPS == 20 and r["k"] == K_EVAL == 10 for r in reads))
    chk("seed 窗与关门读数**同一批**（反向 7000 / 正向 2000 ⇒ L2 才能配对）",
        all(r["seed0"] == (REV_SEED0 if r["scene"] == "rev" else FWD_SEED0) for r in reads))
    chk("task_mode 与场景一致", all(r["task_mode"] == ("reverse" if r["scene"] == "rev" else "forward") for r in reads))
    chk("scene_of：R* = 反向、F* = 正向", scene_of("R1") == "rev" and scene_of("FN") == "fwd")
    chk("ckpt 尾串 = checkpoints/022000/pretrained_model（数字格，坑 38/42/63）",
        all(r["ckpt"].endswith(f"checkpoints/{CK_STEP:06d}/pretrained_model") for r in reads))
    chk("ckpt 落在本臂 run 里（读错权重就是这条挡住的）", all(f"runs/{r['run']}/" in r["ckpt"] for r in reads))
    chk("三臂互不相同且同数据集 mix60f120r_c1（同数据集才允许比高低，坑 33）",
        len(set(ARMS)) == 3 and all(DST in r["run"] for r in reads))
    chk("npz 与场景配对（反向 rev_raw / 正向 raw）",
        all(r["npz"] == ("mix60f120r_rev_raw.npz" if r["scene"] == "rev" else "mix60f120r_raw.npz") for r in reads))
    chk("ORIG 与 mg_eval_lang 的 EXPECT_* 逐字相同（两文件不许各写一份原话）",
        ORIG["fwd"] == EXPECT_FWD and ORIG["rev"] == EXPECT_REV)
    _pr, _pf = plan_patch("reverse", INSTR["R1"]), plan_patch("forward", INSTR["F1"])
    chk("EXPECT_ATTR == mg_eval_lang.plan_patch 的 patch 目标（打错模块 = 静默跑原话）",
        EXPECT_ATTR["rev"] == f"{_pr['module']}.{_pr['attr']}"
        and EXPECT_ATTR["fwd"] == f"{_pf['module']}.{_pf['attr']}")
    chk("EXPECT_ATTR：反向打 mg_env_reverse.TASK_REVERSE、正向打 mg_eval.TASK",
        EXPECT_ATTR == {"rev": "mg_env_reverse.TASK_REVERSE", "fwd": "mg_eval.TASK"})
    chk("6 句改写都与该场景原话不同（相同 = 重复参照、白跑 GPU）",
        all(INSTR[c] != ORIG[scene_of(c)] for c in PARA_CODES))
    chk("两句负对照都与两句原话不同", all(INSTR[c] != ORIG[s] for c in NEG_CODES for s in ("rev", "fwd")))
    chk("两句负对照是同一句无关指令（RN/FN 只差场景）", INSTR["RN"] == INSTR["FN"])
    chk("8 句指令都是非空、无首尾空白的字符串",
        all(isinstance(v, str) and v == v.strip() and v for v in INSTR.values()))
    chk("ref_dir_list：反向 4 读、首读不带 _rep、第二读带 _rep2",
        len(ref_dir_list(ARMS[0], "rev")) == REPS == 4
        and not ref_dir_list(ARMS[0], "rev")[0].endswith("_rep2")
        and ref_dir_list(ARMS[0], "rev")[1].endswith("_rep2"))
    chk("ref_dir_list：正向 1 读", len(ref_dir_list(ARMS[0], "fwd")) == 1)
    chk("参照常数 = S8_VERDICT:16 公布的 65/65/64 与正向 16/12/16",
        [REF_REV[a] for a in ARMS] == [65, 65, 64] and [REF_FWD[a] for a in ARMS] == [16, 12, 16])
    chk("_splitn 摊得回原数、每 rep ≤ EPS、rep1 可指定",
        sum(_splitn(65, 4, 17)) == 65 and max(_splitn(65, 4, 17)) <= EPS and _splitn(65, 4, 17)[0] == 17)
    chk("_splitn 单 rep（正向）也摊得回", _splitn(12, 1) == [12])

    # ── ② gate_l1：压线归属 + UNKNOWN 传染 ──
    _p_ok = {c: (30, 60) for c in PARA_CODES}
    chk("L1：每句 30/60 ⇒ PASS（正好压线算过）", gate_l1(_p_ok)["pass"] is True and gate_l1(_p_ok)["state"] == "PASS")
    _p_bad = dict(_p_ok, F2=(29, 60))
    chk("L1：29/60 ⇒ FAIL 且点名 F2", gate_l1(_p_bad)["pass"] is False and gate_l1(_p_bad)["fails"] == ["F2"])
    _p_hi = {c: (60, 60) for c in PARA_CODES}
    chk("L1：60/60 ⇒ PASS", gate_l1(_p_hi)["pass"] is True)
    _p_none = dict(_p_ok, R3=None)
    chk("L1：任一句缺读 ⇒ UNKNOWN、pass=None（不当 0、不当过，坑 40③）",
        gate_l1(_p_none)["state"] == "UNKNOWN" and gate_l1(_p_none)["pass"] is None)
    chk("L1：UNKNOWN 会点名是哪几句", gate_l1(_p_none)["short"] == ["R3"])
    chk("L1：局数不齐（30/40）也算 UNKNOWN", gate_l1(dict(_p_ok, R1=(30, 40)))["state"] == "UNKNOWN")
    chk("L1：缺读句子之外的句子仍逐句给出 detail", gate_l1(_p_none)["detail"]["R1"] == (30, 60))

    # ── ③ gate_l1b：最差臂 ──
    _a_ok = {c: {a: (12, 20) for a in ARMS} for c in PARA_CODES}
    chk("L1b：最差臂 12/20 ⇒ PASS", gate_l1b(_a_ok)["R1"]["state"] == "PASS")
    _a_edge = {c: {a: (10, 20) for a in ARMS} for c in PARA_CODES}
    chk("L1b：最差臂 10/20 ⇒ PASS（压线算过）", gate_l1b(_a_edge)["R1"]["state"] == "PASS")
    _a_bad = {c: dict({a: (12, 20) for a in ARMS}, **{ARMS[1]: (9, 20)}) for c in PARA_CODES}
    chk("L1b：最差臂 9/20 ⇒ FAIL 且点名那一臂",
        gate_l1b(_a_bad)["R1"]["state"] == "FAIL" and gate_l1b(_a_bad)["R1"]["worst_arm"] == ARMS[1])
    _a_miss = {c: {ARMS[0]: (12, 20)} for c in PARA_CODES}
    chk("L1b：缺臂 ⇒ UNKNOWN 且点名缺哪几臂（不当 0）",
        gate_l1b(_a_miss)["R1"]["state"] == "UNKNOWN" and gate_l1b(_a_miss)["R1"]["missing"] == list(ARMS[1:]))
    chk("L1b：局数不齐（12/15）也算 UNKNOWN",
        gate_l1b({c: {a: (12, 15) for a in ARMS} for c in PARA_CODES})["R1"]["state"] == "UNKNOWN")

    # ── ④ band_l2：±15 pp 的归属 ──
    chk("L2：+15.0 ⇒ SAME（边界含在带内）", band_l2(15.0) == "SAME")
    chk("L2：−15.0 ⇒ SAME", band_l2(-15.0) == "SAME")
    chk("L2：+15.1 ⇒ HIGHER", band_l2(15.1) == "HIGHER")
    chk("L2：−15.1 ⇒ LOWER", band_l2(-15.1) == "LOWER")
    chk("L2：0 ⇒ SAME", band_l2(0.0) == "SAME")
    chk("L2：None ⇒ UNKNOWN", band_l2(None) == "UNKNOWN")
    chk("L2：nan ⇒ UNKNOWN", band_l2(float("nan")) == "UNKNOWN")

    # ── ⑤ paired_l2：按 (臂, seed) 配对 ──
    def _tab(kwin: int, seed0: int = REV_SEED0) -> dict:
        return {a: {seed0 + i: [i < kwin] for i in range(EPS)} for a in ARMS}

    _same = paired_l2(_tab(10), _tab(10))
    chk("配对：完全相同 ⇒ b=c=0、Δ=0、npair=60", (_same["b"], _same["c"], _same["npair"]) == (0, 0, 60)
        and abs(_same["delta_pp"]) < 1e-12 and _same["band"] == "SAME")
    _up = paired_l2(_tab(12), _tab(10))
    chk("配对：改写多成 2 局/臂 ⇒ b=6、c=0、Δ=+10.0", (_up["b"], _up["c"]) == (6, 0) and abs(_up["delta_pp"] - 10.0) < 1e-9)
    chk("配对：p = McNemar 精确双侧（b=6,c=0 ⇒ 2·0.5^6）", abs(_up["p"] - 2 * 0.5 ** 6) < 1e-12)
    _dn = paired_l2(_tab(2), _tab(10))
    chk("配对：改写少成 8 局/臂 ⇒ c=24、Δ=−40.0 ⇒ LOWER", (_dn["b"], _dn["c"]) == (0, 24)
        and abs(_dn["delta_pp"] + 40.0) < 1e-9 and _dn["band"] == "LOWER")
    _part = paired_l2({ARMS[0]: _tab(10)[ARMS[0]]}, _tab(10))
    chk("配对：缺臂 ⇒ 该臂单列、npair 只剩 20（不当 0）",
        _part["missing"] == [ARMS[1], ARMS[2]] and _part["npair"] == 20)
    _off = paired_l2({a: {9000 + i: [True] for i in range(EPS)} for a in ARMS}, _tab(10))
    chk("配对：seed 窗对不上 ⇒ npair=0、Δ=None、band=UNKNOWN（绝不编数）",
        _off["npair"] == 0 and _off["delta_pp"] is None and _off["band"] == "UNKNOWN")
    _emp = paired_l2({a: {REV_SEED0: []} for a in ARMS}, {a: {REV_SEED0: [True]} for a in ARMS})
    chk("配对：某一局没有 per-episode ⇒ 单列 seed 且不计入 npair",
        _emp["npair"] == 0 and any("seed7000" in m for m in _emp["missing"]))

    # ── ⑥ gate_l3：负对照三档 ──
    chk("L3：0/20 ⇒ COND_OK", gate_l3({"RN": (0, 20), "FN": (0, 20)})["state"] == "COND_OK")
    chk("L3：4/20 = 20.0% ⇒ COND_OK（边界含在成立档）", gate_l3({"RN": (4, 20), "FN": (0, 20)})["state"] == "COND_OK")
    chk("L3：5/20 = 25% ⇒ UNCERTAIN", gate_l3({"RN": (5, 20), "FN": (0, 20)})["state"] == "UNCERTAIN")
    chk("L3：9/20 = 45% ⇒ UNCERTAIN", gate_l3({"RN": (0, 20), "FN": (9, 20)})["state"] == "UNCERTAIN")
    chk("L3：10/20 = 50% ⇒ FAKE_COND（边界含在假条件化档）",
        gate_l3({"RN": (10, 20), "FN": (0, 20)})["state"] == "FAKE_COND")
    chk("L3：两句取最坏（一句 OK 一句 FAKE ⇒ FAKE）",
        gate_l3({"RN": (0, 20), "FN": (15, 20)})["state"] == "FAKE_COND")
    chk("L3：缺读 ⇒ UNKNOWN（不当 0）", gate_l3({"RN": None, "FN": (0, 20)})["state"] == "UNKNOWN")
    chk("L3：n=0 ⇒ UNKNOWN", gate_l3({"RN": (0, 0), "FN": (0, 20)})["state"] == "UNKNOWN")
    chk("L3：逐句 state 与 rate 都留着（报告要印百分比）",
        gate_l3({"RN": (15, 20), "FN": (0, 20)})["per"]["RN"]["rate"] == 75.0)

    # ── ⑦ decide：预注册 §3 的决策树逐支 ──
    _l1p = {"state": "PASS", "pass": True, "fails": [], "short": []}
    _l1u = {"state": "UNKNOWN", "pass": None, "fails": [], "short": ["R1"]}
    _l1f = {"state": "FAIL", "pass": False, "fails": ["F2"], "short": []}
    _l1fm = {"state": "FAIL", "pass": False, "fails": ["R2", "F2"], "short": []}
    _ok, _fake = {"state": "COND_OK"}, {"state": "FAKE_COND"}
    _unc, _unk = {"state": "UNCERTAIN"}, {"state": "UNKNOWN"}
    chk("决策：出身不过 ⇒ 🚫 不采信（优先级最高，压过一切 PASS）", "判定不采信" in decide(_l1p, _ok, False, 3))
    chk("决策：L1 UNKNOWN ⇒ ⏳ 读数不齐（不当 0 计）", "读数不齐" in decide(_l1u, _ok, True, 0))
    chk("决策：负对照缺读 ⇒ 只说 L3 不能判", "负对照缺读" in decide(_l1p, _unk, True, 0))
    chk("决策：改写过门 ∧ 无关指令也过门 ⇒ 矛盾组合、先查工具", "矛盾组合" in decide(_l1p, _fake, True, 0))
    chk("决策：矛盾组合时必须写「先查工具」+「不许」直接下结论", "先查工具" in decide(_l1p, _fake, True, 0)
        and "不许" in decide(_l1p, _fake, True, 0))
    chk("决策：过门 + COND_OK ⇒ 「不是记住那两句话」", "不是记住那两句话" in decide(_l1p, _ok, True, 0))
    chk("决策：过门 + UNCERTAIN ⇒ 仍算过，但登记 L3 不确定", "L3 不确定" in decide(_l1p, _unc, True, 0))
    chk("决策：只有 F2 掉门 ⇒ 动词改写稳、名词替换不稳", "名词替换不稳" in decide(_l1f, _ok, True, 0))
    chk("决策：多句掉门 ⇒ 记为新极限 + 处方是语言增广重训（另立预注册）",
        "记为新极限" in decide(_l1fm, _ok, True, 0) and "语言增广" in decide(_l1fm, _ok, True, 0))

    # ── ⑧ fmt_kn（缺读 vs 真 0，坑 40③/86 家族）──
    chk("fmt_kn：n=0 ⇒ 印 —", fmt_kn({"k": 0, "n": 0}) == "—")
    chk("fmt_kn：真跑 20 局 0 成功 ⇒ 如实印 0/20", fmt_kn({"k": 0, "n": 20}) == "0/20")

    # ── ⑨ 端到端：场景 A 全过（rc=0）──
    rc, out = run_scene(lambda r: _build(r))
    chk("场景A：rc=0（判定成立）", rc == 0)
    chk("场景A：S11_L1=PASS", "S11_L1=PASS" in out)
    chk("场景A：反向池化 51/60（17×3）、正向 44/60（16+12+16）", "51/60" in out and "44/60" in out)
    chk("场景A：S11_L1B=PASS（最差臂 ≥ 10/20）", "S11_L1B=PASS" in out)
    chk("场景A：S11_L3=COND_OK（RN=1/20、FN=0/20）", "S11_L3=COND_OK" in out)
    chk("场景A：Δ=0 ⇒ 6 句全在带内", "6/6 句在带内" in out and "S11_R1_BAND=SAME" in out and "S11_R1_DELTA=0.0" in out)
    chk("场景A：S11_TRUST=YES、出身核对 0 条", "S11_TRUST=YES" in out and "出身核对问题：**0**" in out)
    chk("场景A：不变量违例 0 条、缺产物 0、缺字段 0",
        "违例：**0**" in out and "缺产物：**0**" in out and "缺字段：**0**" in out)
    chk("场景A：决策 = 「不是记住那两句话」⇒ 使命结论加强", "不是记住那两句话" in out)
    chk("场景A：清单规模 20 读 / 400 局", "S11_READS=20" in out and "S11_EPS_TOTAL=400" in out)
    chk("场景A：负对照只在 1 臂名下 ⇒ ✅", "名下（多臂/缺臂都算不符）：✅" in out)
    chk("场景A：逐臂数字打出来了（池化不许掩盖臂间差）", "2000:17/20" in out)

    # ── ⑩ 场景 B：只有 F2 掉门（rc=0，结论是 FAIL）──
    rc, out = run_scene(lambda r: _build(r, para={"F2": {a: 4 for a in ARMS}}))
    chk("场景B：读数齐 ⇒ rc=0（结论成立，只是结论是掉门）", rc == 0)
    chk("场景B：S11_L1=FAIL fails=F2", "S11_L1=FAIL fails=F2" in out)
    chk("场景B：F2 池化 12/60 如实印出", "12/60" in out)
    chk("场景B：决策走「名词替换不稳」那一支", "名词替换不稳" in out)
    chk("场景B：最差臂 4/20 ⇒ S11_L1B=ARM_UNSTABLE", "S11_L1B=ARM_UNSTABLE" in out)
    chk("场景B：其余 5 句仍判过（一句掉门不拖垮全表）", "S11_R1_BAND=SAME" in out)

    # ── ⑪ 场景 C：假条件化（L1 过门 ∧ 负对照 75%）──
    rc, out = run_scene(lambda r: _build(r, neg={"RN": 15, "FN": 12}))
    chk("场景C：rc=0", rc == 0)
    chk("场景C：S11_L3=FAKE_COND", "S11_L3=FAKE_COND" in out)
    chk("场景C：负对照 15/20 = 75.0% 如实印出", "15/20 = 75.0%" in out)
    chk("场景C：决策 = 矛盾组合 ⇒ 先查工具，不许写「语言不重要」", "矛盾组合" in out and "先查工具" in out)

    # ── ⑫ 场景 D：产物全缺（rc=3；缺读**绝不当 0 计**，坑 40③/86）──
    rc, out = run_scene(lambda r: _build(r, skip_plan=True))
    chk("场景D：rc=3 不采信", rc == 3)
    chk("场景D：S11_L1=UNKNOWN、S11_TRUST=NO", "S11_L1=UNKNOWN" in out and "S11_TRUST=NO" in out)
    chk("场景D：机器行是 NA，不是 0/60", "S11_R1=NA" in out)
    chk("场景D：读数格不许出现 0/60 或 0/20（缺读当 0 计就是坑 40③；阈值文案里的 30/60 不算）",
        "| 0/60 |" not in out and "| 0/20 |" not in out and "=0/60" not in out and "=0/20" not in out)
    chk("场景D：绝不印 ✅ PASS", "✅ PASS" not in out)
    chk("场景D：缺产物 20 个目录被点名", "缺产物：**20**" in out)
    chk("场景D：报告打 🚫 判定不采信", "判定不采信" in out)
    chk("场景D：UNKNOWN 点名是哪几句缺读", "局数不齐/缺读：R1、R2、R3、F1、F2、F3" in out)

    # ── ⑬ 场景 E：sidecar 自伤（orig == patched ⇒ 这格其实跑的是原话）──
    _e = {("R1", ARMS[0]): {"side_patch": {"orig_task": INSTR["R1"]}}}
    rc, out = run_scene(lambda r: _build(r, patches=_e))
    chk("场景E：rc=3 不采信", rc == 3)
    chk("场景E：点名「其实跑的是原话」", "其实跑的是原话" in out)
    chk("场景E：同时点名 orig_task ≠ 该场景原话", "≠ 该场景原话" in out)
    chk("场景E：TRUST=NO（出身不过压过 L1 PASS）", "S11_TRUST=NO" in out)

    # ── ⑭ 场景 F：老产物缺放宽字段（rc=2 读数不齐；TRUST 仍 YES）──
    rc, out = run_scene(lambda r: _build(r, patches={("R1", ARMS[0]): {"legacy": True}}))
    chk("场景F：rc=2（读数不齐，不是不采信）", rc == 2)
    chk("场景F：S11_L1=UNKNOWN 且**不当 0 计**", "S11_L1=UNKNOWN" in out and "不当 0 计" in out)
    chk("场景F：R1 池化只剩 34/40（缺的那臂不进分母）", "34/40" in out)
    chk("场景F：缺字段被单列 1 条", "缺字段：**1**" in out)
    chk("场景F：出身核对仍干净 ⇒ TRUST=YES（区分「产物是老口径」与「读错权重」）", "S11_TRUST=YES" in out)

    # ── ⑮ 场景 G：参照对不上已公布值（rc=3）──
    rc, out = run_scene(lambda r: _build(r, ref_rev={ARMS[0]: 60}))
    chk("场景G：rc=3 不采信", rc == 3)
    chk("场景G：点名 seed2000 与已公布 65/80 不符", "seed2000" in out and "与已公布 65/80 不符" in out)
    chk("场景G：TRUST=NO", "S11_TRUST=NO" in out)
    rc, out = run_scene(lambda r: _build(r, ref_fwd={ARMS[1]: 9}))
    chk("场景G2：正向参照对不上 12/20 也要报（带 [正向参照] 前缀）",
        rc == 3 and "[正向参照]" in out and "与已公布 12/20 不符" in out)

    # ── ⑯ 场景 H：summary.task 不是预注册那句（patch 没生效的最大风险）──
    _h = {("R2", ARMS[1]): {"sum_patch": {"task": ORIG["rev"]},
                            "side_patch": {"summary_task_field": "Yet another sentence."}}}
    rc, out = run_scene(lambda r: _build(r, patches=_h))
    chk("场景H：rc=3", rc == 3)
    chk("场景H：点名 patch 没生效 / 跑了别的句子（L1 会假过）", "patch 没生效" in out)
    chk("场景H：sidecar 与 summary 不一致也被抓出来", "sidecar 记的 summary.task 与盘上的不一致" in out)

    # ── ⑰ 场景 I：不变量「放宽 ⊇ 严格」被破坏（rc=3）──
    rc, out = run_scene(lambda r: _build(r, patches={("R3", ARMS[2]): {"strict_override": 20}}))
    chk("场景I：rc=3（不变量违例 ⇒ 不采信）", rc == 3)
    chk("场景I：违例被数出来（这行以前恒为 0 = 空转）", "违例：**1**" in out and "relaxed 17 < strict 20" in out)
    chk("场景I：TRUST=NO", "S11_TRUST=NO" in out)

    # ── ⑱ 场景 J：没有 sidecar ⇒ 无法证明 patch 生效 ──
    rc, out = run_scene(lambda r: _build(r, patches={("F3", ARMS[0]): {"no_sidecar": True}}))
    chk("场景J：rc=3", rc == 3)
    chk("场景J：点名「无法证明 patch 生效」（不许采信）", "无法证明 patch 生效" in out)

    def _bad_sidecar(r: Path, name: str, text: str) -> None:
        _build(r)
        (r / name / "lang_sidecar.json").write_text(text)

    # ── ⑲ 场景 K：sidecar 是坏 JSON ⇒ 报错而不是静默跳过 ──
    _r1_out = [x["out"] for x in reads if x["code"] == "R1"][0]
    rc, out = run_scene(lambda r: _bad_sidecar(r, _r1_out, "{ 坏 JSON"))
    chk("场景K：rc=3 且点名读不动", rc == 3 and "读不动" in out)

    # ── ⑳ 场景 L：出身字段逐项（seed 窗 / K / episodes / ckpt 尾串 / 别的臂 / patch 目标 / 回读）──
    _ck_ok = [r for r in reads if r["code"] == "R1"][0]["ckpt"]
    _cases = [
        ("seed 窗变了就不能配对", {("R1", ARMS[0]): {"sum_patch": {"seed": 9999}}}),
        (f"K=7 ≠ {K_EVAL}", {("R1", ARMS[0]): {"sum_patch": {"n_action_steps": 7}}}),
        ("episodes=12 ≠ 20", {("R1", ARMS[0]): {"sum_patch": {"episodes": 12}}}),
        ("task_mode=forward ≠ reverse", {("R1", ARMS[0]): {"sum_patch": {"task_mode": "forward"}}}),
        ("期望 …checkpoints/022000/pretrained_model",
         {("R1", ARMS[0]): {"sum_patch": {"policy_ckpt": _ck_ok.replace("022000", "010000")}}}),
        ("不在本臂 run 里",
         {("R1", ARMS[0]): {"sum_patch": {"policy_ckpt": _ck_ok.replace(ARMS[0], ARMS[1])}}}),
        ("patch 打在 mg_env.TASK 而不是", {("R1", ARMS[0]): {"side_patch": {"module_attr": "mg_env.TASK"}}}),
        ("patch 回读不符", {("R1", ARMS[0]): {"side_patch": {"post_patch_readback": ORIG["rev"]}}}),
        ("sidecar.patched_task ≠ 预注册那句", {("R1", ARMS[0]): {"side_patch": {"patched_task": "Do something else."}}}),
    ]
    for _want, _pat in _cases:
        rc, out = run_scene(lambda r, _p=_pat: _build(r, patches=_p))
        chk(f"场景L：{_want} ⇒ rc=3 且点名", rc == 3 and _want in out)

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
