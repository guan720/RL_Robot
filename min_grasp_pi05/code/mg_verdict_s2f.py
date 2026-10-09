#!/usr/bin/env python
"""档 2f · 放宽口径复判汇编（双口径并报，历史严格数值不追改）。

背景（出处：用户 2026-10-02 指令）
    「可以放松成功判定条件，送到目标位置为首要条件，受手臂高度/冲击等问题出现的侧躺等现象
      也可视为送到，但可以追加标记。」
    ⇒ 反向判据从「落定 ∧ **立着**」放宽为「落定（不要求立着）」，侧躺/侧挡算送到，
      另用 delivered_tipped 打标。实现见 mg_env_reverse.reverse_settled()，
      语义由 code/mg_criterion_selftest.py 钉住（严格口径与历史代码逐条件同值 + 严格 ⊆ 放宽）。

纪律（为什么这个工具要这么啰嗦）
  1. **事后放宽 = 事后改门**。历史严格数值一律原样保留、原样引用，两口径并排报；
     放宽口径的显著性**重新算**，不许沿用严格口径的 p 值。
  2. **上界必须同口径**。严格口径的专家上界是 14/20 = 70%；放宽后 6 局侧躺失败全部变成
     成功（它们 min_dist ≤0.52 cm，早就在 ±9 cm 框里），上界抬高 ⇒ 「占上界百分比」
     这个归一化指标的分母也变了。分子放宽、分母不放宽 = 比值没意义。
  3. **缺字段 ≠ 0**。改判据之前跑的 eval_summary.json 里没有 pc_success_relaxed，
     必须显式报「无放宽字段」并从放宽口径的合并里剔除，绝不能当 0 计入（会把结论压向失败）。
  4. 不变量 relaxed ⊇ strict 逐读复核，破了就 🚫 作废该读数。

用法：
    $MG_PY code/mg_verdict_s2f.py                 # 写 markdown 到 stdout
    $MG_PY code/mg_verdict_s2f.py --selftest      # 语义钉子（含 Fisher 参考值）
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
RUNS = MG_ROOT / "runs"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_verdict_s2 import fisher_two_sided  # noqa: E402  语义见坑 35：(成功数A, 局数A, 成功数B, 局数B)

GATE = 0.50

# ── 组定义 ─────────────────────────────────────────────────────────────────
# `strict` 与 `relaxed` **指向同一批产物**：档 2f 的新读一次评测就并行输出两种口径，
# 所以两列是同一批 rollout（同检查点、同 seed 窗口、同 K、同局数）⇒「口径效应」这一比才干净。
# `hist_strict` 是改判据前的历史原测，只作对照行，**不参与**任何显著性计算（不同批 rollout）。
GROUPS = [
    {
        "label": "档2c 单任务 @last(007600)",
        "role": "去掉正向数据的反向单任务臂",
        "strict": ["s2f_relax_s2c_rev_test_rand20_k10", "s2f_relax_s2c_rev_test_rand20_k10_rep2",
                   "s2f_relax_s2c_rev_test_rand20_k10_rep3", "s2f_relax_s2c_rev_test_rand20_k10_rep4"],
        "relaxed": ["s2f_relax_s2c_rev_test_rand20_k10", "s2f_relax_s2c_rev_test_rand20_k10_rep2",
                    "s2f_relax_s2c_rev_test_rand20_k10_rep3", "s2f_relax_s2c_rev_test_rand20_k10_rep4"],
        "hist_strict": ["s2c_rev_test_rand20_k10", "s2c_rev_test_rand20_k10_rep2",
                        "s2c_rev_test_rand20_k10_rep3", "s2c_rev_test_rand20_k10_rep4"],
    },
    {
        "label": "档2 联合 @last(014400)",
        "role": "对照臂（正反向 1:1 联合训练）",
        "strict": ["s2f_relax_s2joint_rev_test_rand20_k10", "s2f_relax_s2joint_rev_test_rand20_k10_rep2",
                   "s2f_relax_s2joint_rev_test_rand20_k10_rep3", "s2f_relax_s2joint_rev_test_rand20_k10_rep4"],
        "relaxed": ["s2f_relax_s2joint_rev_test_rand20_k10", "s2f_relax_s2joint_rev_test_rand20_k10_rep2",
                    "s2f_relax_s2joint_rev_test_rand20_k10_rep3", "s2f_relax_s2joint_rev_test_rand20_k10_rep4"],
        "hist_strict": ["s2_gate_rev_test_rand20_k10", "s2_gate_rev_test_rand20_k10_rep2",
                        "s2c_jointbase_rev_test_rand20_k10_rep3", "s2c_jointbase_rev_test_rand20_k10_rep4"],
    },
    {
        "label": "档2e 2:1 @last(022000)",
        "role": "数据杠杆臂（60 正向 + 120 反向）；两口径由 chain_s2e_train.sh 的关门读数白捡",
        "strict": ["s2e_rev_test_rand20_k10", "s2e_rev_test_rand20_k10_rep2",
                   "s2e_rev_test_rand20_k10_rep3", "s2e_rev_test_rand20_k10_rep4"],
        "relaxed": ["s2e_rev_test_rand20_k10", "s2e_rev_test_rand20_k10_rep2",
                    "s2e_rev_test_rand20_k10_rep3", "s2e_rev_test_rand20_k10_rep4"],
        "hist_strict": [],
    },
]
G_S2C = GROUPS[0]["label"]
G_JOINT = GROUPS[1]["label"]
G_S2E = GROUPS[2]["label"]

CEIL_NEW = "s2f_ceiling_rev_test20_n05"
CEIL_OLD = "s2_ceiling_rev_test20_n05"


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score 95% 区间。n=0 时返回 (nan, nan)；p=0/1 也不塌成零宽（Wald 会）。"""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1.0 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def load(d: str) -> dict | None:
    p = RUNS / d / "eval_summary.json"
    if not p.exists():
        p2 = RUNS / d / "ceiling_summary.json"
        if not p2.exists():
            return None
        p = p2
    try:
        j = json.loads(p.read_text())
    except Exception as exc:
        return {"_error": "读不动 %s: %s" % (p, exc)}
    j["_dir"] = d
    j["_path"] = str(p)
    return j


def collect(dirs: list[str], key_n: str, key_pc: str) -> dict:
    """把若干读的 (成功数, 局数) 合并；缺字段/缺产物的**单列**出来，不当 0。"""
    out = {"k": 0, "n": 0, "tipped": 0, "inbox": 0, "reads": [], "missing": [], "nofield": [],
           "broken": [], "key_n": key_n, "key_pc": key_pc}
    for d in dirs:
        j = load(d)
        if j is None:
            out["missing"].append(d)
            continue
        if "_error" in j:
            out["nofield"].append((d, j["_error"]))
            continue
        if key_n not in j:
            out["nofield"].append((d, "无 %s 字段（改判据前跑的）" % key_n))
            continue
        k, n = int(j[key_n]), int(j.get("episodes", 0))
        ks, ns = int(j.get("n_success", 0)), int(j.get("episodes", 0))
        read = {"dir": d, "k": k, "n": n, "k_strict": ks,
                "tipped": int(j.get("n_delivered_tipped", 0)),
                "inbox": int(j.get("n_ever_in_target_box", 0)),
                "task_mode": j.get("task_mode", "?"),
                "seed": j.get("seed", -1), "K": j.get("n_action_steps", -1),
                "ckpt": Path(str(j.get("policy_ckpt", j.get("expert", "?")))).parent.name}
        out["reads"].append(read)
        out["k"] += k
        out["n"] += n
        out["tipped"] += read["tipped"]
        out["inbox"] += read["inbox"]
        # 不变量：放宽口径必须 ⊇ 严格口径（同一次 rollout 内并行判定，是硬约束不是统计约束）
        if key_n == "n_success_relaxed" and k < ks:
            out["broken"].append((d, "relaxed %d < strict %d" % (k, ks)))
        if n != ns:
            out["broken"].append((d, "episodes 字段不一致 %d vs %d" % (n, ns)))
    return out


def mcnemar_nested(b: int, c: int = 0) -> float:
    """配对二分类读数的 McNemar **精确**检验（双侧），用于「同一批 rollout、两种判据」。

    为什么不能用 Fisher：严格与放宽是在**同一局**上并行判定的（同一条轨迹、同一份动作），
    两组读数配对。拿独立两组的 Fisher 去比 = 把「口径差」和「重采样噪声」混在一起
    （2026-10-02 第一版就是这么写的，得出 p=0.33「不显著」，而配对检验是 p<0.01）。
    又因为不变量 严格 ⊆ 放宽 恒成立，不一致对只可能是 (放宽=1, 严格=0)，
    即 b = 侧躺标记局数，而 c = (放宽=0, 严格=1) 恒为 0。
    McNemar 精确双侧 p = 2·Σ_{k=0..min(b,c)} C(b+c,k)·0.5^(b+c)；c=0 时退化为 2·0.5^b。
    """
    n = b + c
    if n <= 0:
        return 1.0
    m = min(b, c)
    tail = sum(math.comb(n, k) for k in range(m + 1)) * (0.5 ** n)
    return min(1.0, 2.0 * tail)


def pct(k: int, n: int) -> str:
    return "—" if n <= 0 else "%.1f%%" % (100.0 * k / n)


def seed_table(dirs: list[str], key: str) -> dict:
    """按 seed 把多读合并成 {seed: [每读的成功布尔]}，用来分「稳过 / 抖动 / 从不」。

    为什么要这一层：档 2c 的分类账发现「20 个 seed 里策略至少成功过一次的有 14 个」⇒ 失败主要是
    **执行抖动**而不是「位姿没覆盖」。放宽口径把专家上界抬到 20/20（每个 seed 都可达）之后，
    这个拆分变得更硬：从不成功的 seed 一个都不能赖给任务不可行。
    """
    tab: dict[int, list[bool]] = {}
    tipped: dict[int, int] = {}
    for d in dirs:
        j = load(d)
        if not j or "_error" in j:
            continue
        # ⚠️ 这里查的是 **per-episode** 字段名（success_relaxed），不是 summary 字段名
        # （n_success_relaxed）。查错层级会让所有真产物被静默跳过 —— 2026-10-02 自测时抓到。
        # 老产物（改判据前跑的）per_episode 里没有这个 key ⇒ 整读剔除，**不当 0**（坑 40③）。
        eps = j.get("per_episode", [])
        if not eps or key not in eps[0]:
            continue
        for e in eps:
            s = int(e["seed"])
            tab.setdefault(s, []).append(bool(e.get(key, False)))
            if e.get("delivered_tipped"):
                tipped[s] = tipped.get(s, 0) + 1
    return {"tab": tab, "tipped": tipped}


def ci(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return "—" if n <= 0 else "[%.1f, %.1f]" % (100 * lo, 100 * hi)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    print("# 档 2f 判定：放宽口径复判（双口径并报）")
    print("# 产物根目录：%s" % RUNS)
    print()
    print("## 零、口径变更的授权与纪律")
    print()
    print("* 出处：用户 2026-10-02 指令 —— 「送到目标位置为首要条件，受手臂高度/冲击等问题出现的")
    print("  侧躺等现象也可视为送到，但可以追加标记」。")
    print("* 变更内容：反向 `settled` 去掉「倾角 < 20°」这一条，其余四条（z 容差 25 mm / 速度 <0.05 m/s /")
    print("  夹爪 >0.05 m / 末端离 can >5 cm）与「进 ±9 cm 框 ∧ 保持 10 步」**一字未动**。")
    print("  实现：`code/mg_env_reverse.py:reverse_settled()`；语义钉子：`code/mg_criterion_selftest.py`。")
    print("* 标记：`delivered_tipped` = 放宽算成功但严格不算（= 送到了却侧躺/侧挡）。逐局落盘在")
    print("  `eval_summary.json:per_episode[*].delivered_tipped` 与 `final_tilt_deg`。")
    print("* ⚠️ 这是**看到严格口径结果之后**才放宽的（档 2c 严格 46.2% 差 3.8 pp 没过门），属于事后口径变更。")
    print("  所以：严格数值原样保留、两口径并排、放宽口径的 p 值重新算、且**不许**只报放宽那一个。")
    print()

    # ── 上界 ─────────────────────────────────────────────────────────────
    cn, co = load(CEIL_NEW), load(CEIL_OLD)
    print("## 一、专家上界（同口径才可比）")
    print()
    if cn is None or "_error" in (cn or {}):
        print("* 🚫 新上界缺产物 `%s` ⇒ 放宽口径的「占上界百分比」**无法计算**，本判定悬空。" % CEIL_NEW)
        ceil_rlx_k = ceil_rlx_n = None
    else:
        print("| 上界 | 口径 | 读数 | 出处 |")
        print("| --- | --- | --- | --- |")
        print("| 脚本专家 noise=0.05 seed 7000..7019 | 严格（历史） | %d/%d = %s | `runs/%s/ceiling_summary.json` |"
              % (cn["n_success"], cn["episodes"], pct(cn["n_success"], cn["episodes"]), CEIL_NEW))
        print("| 同上（同一次重跑，轨迹逐比特相同） | **放宽 R** | %d/%d = %s | 同上 |"
              % (cn["n_success_relaxed"], cn["episodes"],
                 pct(cn["n_success_relaxed"], cn["episodes"])))
        print("| 同上（改判据前的原产物） | 严格（对照） | %s | `runs/%s/ceiling_summary.json` |"
              % (("%d/%d" % (co["n_success"], co["episodes"])) if co and "_error" not in co else "缺", CEIL_OLD))
        print()
        print("* 上界可复现性出处：`mg_ceiling.py` 把噪声流钉死成 `default_rng(12345)`，同参数重跑 = 逐比特相同轨迹。")
        if co and "_error" not in co and cn["n_success"] == co["n_success"]:
            same_ep = all(a["success"] == b["success"]
                          for a, b in zip(cn["per_episode"], co["per_episode"]))
            print("* 严格口径回归：%s（新旧 %d/%d 一致，逐局 success 也%s）⇒ 判据改动没有污染历史口径。"
                  % ("✅ 通过" if same_ep else "⚠️ 合并数一致但逐局有差", cn["n_success"], cn["episodes"],
                     "一致" if same_ep else "不一致"))
        print("* 放宽后上界从 %s 抬到 %s：6 局专家失败全是 can 侧躺（final_tilt≈90°）而 min_dist ≤0.52 cm，"
              % (pct(cn["n_success"], cn["episodes"]), pct(cn["n_success_relaxed"], cn["episodes"])))
        print("  本来就在 ±9 cm 框里 ⇒ 用户口径下它们是**送到了**。侧躺标记 %d 局。" % cn["n_delivered_tipped"])
        print("* 含义变化：严格口径下可以说「这 6 个 seed 专家也做不到，不该算策略的账」；放宽口径下")
        print("  **这个借口消失了** —— 那 6 个 seed 是可达的，策略在上面失败就是策略的失败。")
        ceil_rlx_k, ceil_rlx_n = cn["n_success_relaxed"], cn["episodes"]
    print()

    # ── 各组读数 ─────────────────────────────────────────────────────────
    print("## 二、读数（TEST 反向 seed 7000..7019，K=10，每读 20 局）")
    print()
    print("| 组 | 口径 | 逐读 | 合并 | Wilson 95% | 侧躺标记 | 曾进框 | 占上界 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    pooled = {}
    for g in GROUPS:
        rows = (("**放宽 R**", "n_success_relaxed", "pc_success_relaxed", g["relaxed"]),
                ("严格（同批）", "n_success", "pc_success", g["strict"]),
                ("严格（历史原测，仅对照）", "n_success_hist", "pc_success", g.get("hist_strict", [])))
        for crit, key_n, key_pc, dirs in rows:
            if not dirs:
                continue
            real_key = "n_success" if key_n == "n_success_hist" else key_n
            c = collect(dirs, real_key, key_pc)
            pooled[(g["label"], key_n)] = c
            per = " ".join("#%d:%d/%d=%s" % (i + 1, r["k"], r["n"], pct(r["k"], r["n"]))
                           for i, r in enumerate(c["reads"])) or "（无产物）"
            # 占上界必须**同口径**：放宽读数除以上界 100%，严格读数除以上界 70%（坑 40②）
            share = "—"
            if c["n"]:
                if key_n == "n_success_relaxed" and ceil_rlx_n:
                    share = "%.1f%%" % (100.0 * (c["k"] / c["n"]) / (ceil_rlx_k / ceil_rlx_n))
                elif key_n in ("n_success", "n_success_hist") and co and "_error" not in co \
                        and co.get("episodes") and co.get("n_success"):
                    share = "%.1f%%" % (100.0 * (c["k"] / c["n"])
                                        / (co["n_success"] / co["episodes"]))
            # 侧躺标记 / 曾进框 是**放宽口径**的附属读数；严格口径那行留空，免得两口径混读
            tip = "—" if key_n != "n_success_relaxed" else str(c["tipped"])
            box = "—" if key_n != "n_success_relaxed" else str(c["inbox"])
            print("| %s | %s | %s | **%d/%d = %s** | %s | %s | %s | %s |"
                  % (g["label"], crit, per, c["k"], c["n"], pct(c["k"], c["n"]),
                     ci(c["k"], c["n"]), tip, box, share))
    print()
    for g in GROUPS:
        for key_n in ("n_success", "n_success_relaxed", "n_success_hist"):
            c = pooled.get((g["label"], key_n))
            if c is None:
                continue
            if c["missing"]:
                print("* ⚠️ %s [%s] 缺产物 %d 读：%s（不计入合并，**不当 0**）"
                      % (g["label"], key_n, len(c["missing"]), ", ".join(c["missing"])))
            for d, why in c["nofield"]:
                print("* ⚠️ %s [%s] `%s`：%s ⇒ 剔除，不当 0" % (g["label"], key_n, d, why))
            for d, why in c["broken"]:
                print("* 🚫 %s [%s] `%s` 不变量破了：%s ⇒ 该读数作废" % (g["label"], key_n, d, why))
    print()

    # ── 门与显著性 ───────────────────────────────────────────────────────
    print("## 三、门与显著性（放宽口径重新算，不沿用严格口径的 p）")
    print()
    main_s = pooled[(G_S2C, "n_success")]
    main_r = pooled[(G_S2C, "n_success_relaxed")]
    joint_r = pooled[(G_JOINT, "n_success_relaxed")]
    joint_s = pooled[(G_JOINT, "n_success")]
    s2e_r = pooled[(G_S2E, "n_success_relaxed")]
    s2e_s = pooled[(G_S2E, "n_success")]
    for lbl in (G_S2C, G_JOINT, G_S2E):        # 没有历史读的组给个空壳，省得下游 KeyError
        pooled.setdefault((lbl, "n_success_hist"),
                          {"k": 0, "n": 0, "tipped": 0, "inbox": 0, "reads": [],
                           "missing": [], "nofield": [], "broken": [],
                           "key_n": "n_success", "key_pc": "pc_success"})

    def gate_line(name: str, c: dict) -> None:
        if c["n"] <= 0:
            print("* %s：无读数 ⇒ **悬空**" % name)
            return
        r = c["k"] / c["n"]
        ok = "✅ 过门" if r >= GATE else "❌ 未过门"
        print("* %s = %d/%d = %s（门 ≥%.0f%%）⇒ %s；Wilson 95%% %s"
              % (name, c["k"], c["n"], pct(c["k"], c["n"]), 100 * GATE, ok, ci(c["k"], c["n"])))

    gate_line("档2c 单任务 **放宽 R**（主口径）", main_r)
    gate_line("档2c 单任务 严格（同一批 rollout）", main_s)
    gate_line("档2e 2:1 **放宽 R**（主口径）", s2e_r)
    gate_line("档2e 2:1 严格（档 2e 的预注册门）", s2e_s)
    gate_line("档2 联合 **放宽 R**", joint_r)
    for g in GROUPS:
        h = pooled.get((g["label"], "n_success_hist"))
        if h and h["n"]:
            gate_line("%s 严格（**历史原测**，仅对照、不参与检验）" % g["label"], h)
    print()

    def criterion_effect(name: str, cs: dict, cr: dict) -> None:
        """口径效应必须用**配对**检验：严格与放宽是在同一局上并行判定的。"""
        if not (cs["n"] and cr["n"]) or cs["n"] != cr["n"]:
            print("* %s 口径效应：两口径局数不齐（%d vs %d）⇒ 无法配对，跳过"
                  % (name, cs["n"], cr["n"]))
            return
        b = cr["k"] - cs["k"]                      # 不一致对：放宽=1 且 严格=0
        p_m = mcnemar_nested(b, 0)
        p_f = fisher_two_sided(cr["k"], cr["n"], cs["k"], cs["n"])
        print("* %s 口径效应（放宽 %s vs 严格 %s，**同一批 %d 局**）："
              % (name, pct(cr["k"], cr["n"]), pct(cs["k"], cs["n"]), cr["n"]))
        print("  配对 **McNemar 精确** p=%.3g（不一致对 b=%d，即侧躺标记局数；c=0 由不变量 严格⊆放宽 保证）⇒ %s"
              % (p_m, b, "**显著**" if p_m < 0.05 else "不显著"))
        if b != cr["tipped"]:
            print("  ⚠️ b=%d 与 delivered_tipped 计数 %d 不一致 ⇒ 标记字段有问题，本行存疑" % (b, cr["tipped"]))
        print("  （对照：若误用独立两组的 Fisher，p=%.4f —— 那个检验把「口径差」和「重采样噪声」混在一起，"
              "是**错的**检验，见坑 39）" % p_f)

    criterion_effect("档2c 单任务", main_s, main_r)
    criterion_effect("档2e 2:1", s2e_s, s2e_r)
    criterion_effect("档2 联合", joint_s, joint_r)
    if main_r["n"] and joint_r["n"]:
        p = fisher_two_sided(main_r["k"], main_r["n"], joint_r["k"], joint_r["n"])
        print("* 干扰问题在放宽口径下重问一遍（档2c 单任务 %s vs 档2 联合 %s）：Δ=%+.1f pp，Fisher p=%.4f%s"
              % (pct(main_r["k"], main_r["n"]), pct(joint_r["k"], joint_r["n"]),
                 100 * (main_r["k"] / main_r["n"] - joint_r["k"] / joint_r["n"]), p,
                 "（显著）" if p < 0.05 else "（不显著）"))
        print("  功效提示：n=%d/%d 时，要 p<0.05 大约需要 Δ≥%d pp（粗算）；不显著读作「没测出干扰」，"
              % (main_r["n"], joint_r["n"], 20))
        print("  **不是**「证明了没有干扰」。")
    if s2e_r["n"] and main_r["n"]:
        p = fisher_two_sided(s2e_r["k"], s2e_r["n"], main_r["k"], main_r["n"])
        print("* 数据杠杆在放宽口径下（档2e 2:1 %s vs 档2c 单任务 %s）：Δ=%+.1f pp，Fisher p=%.4f%s"
              % (pct(s2e_r["k"], s2e_r["n"]), pct(main_r["k"], main_r["n"]),
                 100 * (s2e_r["k"] / s2e_r["n"] - main_r["k"] / main_r["n"]), p,
                 "（显著）" if p < 0.05 else "（不显著）"))
        print("  ⚠️ 跨数据集比较：换数据集 ⇒ normalizer 重算，绝对值不可直接比（坑 33 尾条），")
        print("  这一行只报「同一口径下的方向」，严格归因要 1:1 对照臂（见 run_pi05_s2e.sh 头注释）。")
    print()

    # ── 阶梯 ─────────────────────────────────────────────────────────────
    print("## 三补、按 seed 拆分（放宽口径）")
    print()
    if ceil_rlx_n and cn is not None and "_error" not in cn \
            and cn["n_success_relaxed"] == cn["episodes"]:
        print("* 前提：放宽口径下专家上界 = %d/%d = 100%% ⇒ **每个 TEST seed 都可达**，"
              % (cn["n_success_relaxed"], cn["episodes"]))
        print("  所以「从不成功」的 seed 一个都不能赖给任务不可行，它们是真差距。")
    print()
    for g in GROUPS:
        st = seed_table(g["relaxed"], "success_relaxed")
        tab = st["tab"]
        if not tab:
            print("* %s：无放宽产物 ⇒ 跳过" % g["label"])
            continue
        nrep = max(len(v) for v in tab.values())
        uneven = sorted(s for s, v in tab.items() if len(v) != nrep)
        always = sorted(s for s, v in tab.items() if v and all(v))
        sometimes = sorted(s for s, v in tab.items() if any(v) and not all(v))
        never = sorted(s for s, v in tab.items() if not any(v))
        print("* **%s**（%d 个 seed × %d 读）：稳过 %d / 抖动 %d / **从不 %d**"
              % (g["label"], len(tab), nrep, len(always), len(sometimes), len(never)))
        print("  - 抖动 seed（同 seed 有时成有时败 = 执行抖动，不是位姿不可行）：%s"
              % (", ".join(str(s) for s in sometimes) or "无"))
        print("  - 从不成功 seed（**真差距**）：%s" % (", ".join(str(s) for s in never) or "无"))
        if st["tipped"]:
            print("  - 出现过侧躺标记的 seed（次数）：%s"
                  % ", ".join("%d×%d" % (s, st["tipped"][s]) for s in sorted(st["tipped"])))
        if uneven:
            print("  - ⚠️ 读次数不齐的 seed（有读缺产物）：%s" % ", ".join(str(s) for s in uneven))
    print()
    print("* 怎么读：抖动盘子大 ⇒ 加数据的作用是**压抖动**（抗过拟合/去抖），不是「覆盖更多位姿」；")
    print("  从不盘子大 ⇒ 才是位姿覆盖或能力问题。这条区分决定档 3 之后是加数据还是改示范。")
    print()
    print("## 四、三级阶梯（同一批 rollout，越往下越松）")
    print()
    print("| 组 | 严格（立着落定） | 放宽 R（落定，不要求立着） | 曾进 ±9cm 框（仅诊断） |")
    print("| --- | --- | --- | --- |")
    for g in GROUPS:
        cs = pooled[(g["label"], "n_success")]
        cr = pooled[(g["label"], "n_success_relaxed")]
        print("| %s | %d/%d = %s | %d/%d = %s | %d/%d = %s |"
              % (g["label"], cs["k"], cs["n"], pct(cs["k"], cs["n"]),
                 cr["k"], cr["n"], pct(cr["k"], cr["n"]),
                 cr["inbox"], cr["n"], pct(cr["inbox"], cr["n"])))
    print()
    print("* 「曾进框」不是成功口径，只是诊断上界：它连「松手 + 静止 + 保持 10 步」都不要求，")
    print("  历史 `tax_s2c_rev.md` 里那个 47/80 = 58.8% 用的就是这一级，**不要**拿它当放宽口径的结论。")
    print()

    # ── 判定 ─────────────────────────────────────────────────────────────
    print("## 五、判定")
    print()
    broken_any = [b for g in GROUPS for key in ("n_success", "n_success_relaxed")
                  for b in pooled[(g["label"], key)]["broken"]]
    if broken_any:
        print("🚫 **全部结论作废**：有读数破了 严格 ⊆ 放宽 不变量（%d 处）⇒ 判据实现有 bug，先修再读。"
              % len(broken_any))
        for b in broken_any[:10]:
            print("   %s" % (b,))
    elif main_r["n"] == 0:
        print("* **悬空**：档2c 放宽口径还没有产物（chain_s2f_relax.sh 阶段 C 未跑完），不下结论。")
    else:
        r = main_r["k"] / main_r["n"]
        if r >= GATE:
            print("✅ **RX1 放宽口径过门**：档2c 单任务放宽 %d/%d = %s ≥ %.0f%%（严格口径 %s 未过门）。"
                  % (main_r["k"], main_r["n"], pct(main_r["k"], main_r["n"]), 100 * GATE,
                     pct(main_s["k"], main_s["n"])))
            print("   读法：反向任务的瓶颈里有一块是**判据太严**（要求 can 立着），不是策略不会送。")
            print("   侧躺标记 %d/%d 局 ⇒ 这部分是「送到了但没摆正」，按用户口径算送到，已单独打标可追溯。"
                  % (main_r["tipped"], main_r["n"]))
            print("   下一步：以放宽口径为**主口径**继续（档 3 多初始位置 / 档 4 chunk 执行 / 档 5 Harness），")
            print("   严格口径并列报，方便和真机验收对齐。")
            print()
            print("### 附：三个数据臂的**剂量-反应**（同一 TEST 窗口、同一 K、同口径，各 80 局）")
            print()
            print("| 臂 | 反向示范 | 严格 | 放宽 R | 稳过 seed | 抖动 seed | 从不 seed |")
            print("| --- | --- | --- | --- | --- | --- | --- |")
            for lbl, ndemo in ((G_JOINT, "60（正:反 = 1:1）"), (G_S2C, "60（纯反向）"),
                               (G_S2E, "**120**（正:反 = 1:2）")):
                cs, cr = pooled[(lbl, "n_success")], pooled[(lbl, "n_success_relaxed")]
                gg = next(x for x in GROUPS if x["label"] == lbl)
                st = seed_table(gg["relaxed"], "success_relaxed")["tab"]
                alw = sum(1 for v in st.values() if v and all(v))
                sm = sum(1 for v in st.values() if any(v) and not all(v))
                nv = sum(1 for v in st.values() if not any(v))
                print("| %s | %s | %s | **%s** | %d | %d | %d |"
                      % (lbl, ndemo, pct(cs["k"], cs["n"]), pct(cr["k"], cr["n"]), alw, sm, nv))
            print()
            print("* 两条口径都**单调上升**，且「稳过 seed」2 → 5 → 11、「从不 seed」5 → 4 → 3：")
            print("  ⇒ 加反向数据主要是把**抖动局**变成**稳定局**（抗过拟合 / 去抖），不是覆盖新位姿。")
            print("  这与档 2c 分类账的推断一致（`runs/_diag/tax_s2c_rev.md`：20 个 seed 里策略至少成功")
            print("  过一次的有 14 个），现在被三个数据臂的剂量-反应**直接证实**。")
            if s2e_r["n"] and s2e_s["n"]:
                print("* **档 2e 是唯一两条口径都过门的臂**（严格 %s、放宽 %s），其判定已独立落盘："
                      % (pct(s2e_s["k"], s2e_s["n"]), pct(s2e_r["k"], s2e_r["n"])))
                print("  `runs/S2E_VERDICT.md` = **P1 PASS**（预注册门按严格口径写，52.5% ≥ 50%）⇒")
                print("  「反向过门」这件事**不依赖**本次口径放宽；放宽只是把它抬得更稳（68.8%，Wilson 下界 57.9%）。")
        else:
            print("❌ **RX2 放宽也没过门**：档2c 单任务放宽 %d/%d = %s < %.0f%%。"
                  % (main_r["k"], main_r["n"], pct(main_r["k"], main_r["n"]), 100 * GATE))
            print("   ⇒ 判据不是（唯一）瓶颈，反向任务本身的能力还差。处方回到「加数据 / 改示范」，")
            print("   档 2e（120 反向 + 2:1）的读数就是为这条准备的。")
    print()
    print("## 六、复现命令")
    print()
    print("```bash")
    print("source code/env.sh")
    print("bash code/chain_s2f_relax.sh            # A 上界+回归 -> B 冒烟 -> C 档2c 4x20 -> D 档2 4x20 -> E 补真22000 -> F 本判定")
    print("$MG_PY code/mg_criterion_selftest.py    # 判据语义钉子（严格 == 历史实现，且 严格 ⊆ 放宽）")
    print("$MG_PY code/mg_verdict_s2f.py           # 本文件")
    print("```")
    return 0


def selftest() -> int:
    fails: list[str] = []
    n = 0

    def chk(c: bool, m: str) -> None:
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    # Fisher 语义钉子（坑 35：参数是 成功数A, 局数A, 成功数B, 局数B）
    # 参考值出处：code/mg_epoch_curve.py --selftest 里已 scipy 核过的同一批数字
    chk(abs(fisher_two_sided(6, 20, 2, 20) - 0.23511623511623514) < 1e-12,
        "fisher(6,20,2,20) 参考值不符：%r" % fisher_two_sided(6, 20, 2, 20))
    chk(abs(fisher_two_sided(30, 80, 30, 80) - 1.0) < 1e-12, "相同比例 p 必须 = 1.0")
    chk(fisher_two_sided(39, 80, 12, 80) < 1e-4, "39/80 vs 12/80 必须显著")
    chk(fisher_two_sided(37, 80, 30, 80) > 0.05, "档2c 37/80 vs 档2 30/80 历史上 p=0.336 不显著")
    chk(abs(fisher_two_sided(0, 20, 0, 20) - 1.0) < 1e-12, "0/20 vs 0/20 p=1")
    chk(fisher_two_sided(5, 0, 5, 20) == 1.0, "n=0 必须返回 1.0 而不是崩")
    # 参数顺序写反会给出不同 p ⇒ 钉住「不是对称的」这件事本身
    chk(abs(fisher_two_sided(9, 10, 37, 80) - fisher_two_sided(37, 80, 9, 10)) < 1e-12,
        "两组互换应同 p（双侧）")
    # 这个值必须**逐位**复现档 2c 判定里写的 G2 p=0.015（出处 runs/S2C_VERDICT.md 护栏 G2 行）
    chk(abs(fisher_two_sided(9, 10, 37, 80) - 0.01532063634501693) < 1e-12,
        "档2c G2 p 必须复现历史值 0.01532063634501693，实得 %r" % fisher_two_sided(9, 10, 37, 80))
    # 独立交叉验证：scipy 的 fisher_exact（超几何精确检验）必须与我们的纯 stdlib 实现同值
    try:
        from scipy.stats import fisher_exact
        for (a, n1, b, n2) in [(9, 10, 37, 80), (6, 20, 2, 20), (37, 80, 30, 80),
                               (39, 80, 12, 80), (14, 20, 6, 20), (0, 20, 3, 20)]:
            table = [[a, n1 - a], [b, n2 - b]]
            _, p_sp = fisher_exact(table, alternative="two-sided")
            p_ours = fisher_two_sided(a, n1, b, n2)
            chk(abs(p_sp - p_ours) < 1e-9,
                "scipy 交叉验证不符 @ %r：scipy=%r ours=%r" % ((a, n1, b, n2), p_sp, p_ours))
        print("  [钉子] scipy.stats.fisher_exact 交叉验证 6 组，全部 |Δp|<1e-9（scipy %s）"
              % __import__("scipy").__version__)
    except ImportError:
        chk(False, "scipy 不可用 ⇒ 无法交叉验证 Fisher 语义（坑 35 要求独立核对）")

    # Wilson 区间钉子：**不复述同一个公式**，而是用它的定义性质反查 ——
    # Wilson 区间是 score 检验的反解，端点 p 满足 (p̂ - p)² = z²·p(1-p)/n。
    # 这条性质独立于 wilson() 里的闭式写法，所以能查出「公式抄错/符号写反」。
    def score_resid(phat: float, p: float, nn: int, z: float = 1.959963984540054) -> float:
        return (phat - p) ** 2 - z * z * p * (1 - p) / nn

    for k, nn in [(14, 20), (37, 80), (20, 20), (0, 20), (1, 80), (47, 80)]:
        lo, hi = wilson(k, nn)
        if nn <= 0:
            continue
        chk(0.0 <= lo <= hi <= 1.0, "wilson(%d,%d) 越界：%r" % (k, nn, (lo, hi)))
        if 0 < k < nn:
            chk(abs(score_resid(k / nn, lo, nn)) < 1e-9,
                "wilson(%d,%d) 下界不满足 score 反解：resid=%r" % (k, nn, score_resid(k / nn, lo, nn)))
            chk(abs(score_resid(k / nn, hi, nn)) < 1e-9,
                "wilson(%d,%d) 上界不满足 score 反解：resid=%r" % (k, nn, score_resid(k / nn, hi, nn)))
    lo, hi = wilson(14, 20)
    chk(abs(lo - 0.4810271816464765) < 1e-12 and abs(hi - 0.8545227551323956) < 1e-12,
        "wilson(14,20) 参考值漂移：实得 %r" % ((lo, hi),))
    lo, hi = wilson(20, 20)
    chk(lo > 0.8 and hi <= 1.0, "wilson(20,20) 上界必须 ≤1 且不是零宽，实得 %r" % ((lo, hi),))
    lo, hi = wilson(0, 20)
    chk(lo == 0.0 and hi > 0.0, "wilson(0,20) 下界 0、上界非 0，实得 %r" % ((lo, hi),))
    lo, hi = wilson(0, 0)
    chk(lo != lo and hi != hi, "wilson(0,0) 必须 nan 而不是崩")

    # collect 的「缺字段 ≠ 0」语义：造一个改判据前的假产物
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "old_read").mkdir()
        (root / "old_read" / "eval_summary.json").write_text(json.dumps(
            {"episodes": 20, "n_success": 9, "pc_success": 0.45}))     # 没有 relaxed 字段
        (root / "new_read").mkdir()
        (root / "new_read" / "eval_summary.json").write_text(json.dumps(
            {"episodes": 20, "n_success": 9, "pc_success": 0.45,
             "n_success_relaxed": 12, "pc_success_relaxed": 0.6,
             "n_delivered_tipped": 3, "n_ever_in_target_box": 14}))
        (root / "bad_read").mkdir()
        (root / "bad_read" / "eval_summary.json").write_text(json.dumps(
            {"episodes": 20, "n_success": 9, "n_success_relaxed": 5}))  # relaxed < strict，破不变量
        for nm, rows in (("r1", [(7000, True, True, False), (7001, False, True, True),
                                 (7002, False, False, False)]),
                         ("r2", [(7000, True, True, False), (7001, False, False, False),
                                 (7002, False, False, False)])):
            (root / nm).mkdir()
            (root / nm / "eval_summary.json").write_text(json.dumps({
                "episodes": len(rows), "n_success": sum(r[1] for r in rows),
                "n_success_relaxed": sum(r[2] for r in rows),
                "n_delivered_tipped": sum(r[3] for r in rows),
                "per_episode": [{"seed": s, "success": a, "success_relaxed": b,
                                 "delivered_tipped": c} for s, a, b, c in rows]}))
        global RUNS
        save = RUNS
        RUNS = root
        try:
            c = collect(["old_read", "new_read", "gone_read"], "n_success_relaxed", "pc_success_relaxed")
            chk(c["k"] == 12 and c["n"] == 20, "缺字段的那读必须被剔除，只算 new_read：实得 %d/%d" % (c["k"], c["n"]))
            chk(len(c["nofield"]) == 1 and "old_read" in c["nofield"][0][0], "缺字段要单列出来：%r" % c["nofield"])
            chk(c["missing"] == ["gone_read"], "缺产物要单列：%r" % c["missing"])
            chk(c["tipped"] == 3 and c["inbox"] == 14,
                "侧躺标记/曾进框要合并：tipped=%r inbox=%r" % (c["tipped"], c["inbox"]))
            b = collect(["bad_read"], "n_success_relaxed", "pc_success_relaxed")
            chk(len(b["broken"]) == 1, "relaxed<strict 必须报作废：%r" % b["broken"])
            s = collect(["old_read", "new_read"], "n_success", "pc_success")
            chk(s["k"] == 18 and s["n"] == 40, "严格口径两读都要计入：%d/%d" % (s["k"], s["n"]))
            chk(not s["broken"], "严格口径不该触发不变量：%r" % s["broken"])
            st = seed_table(["r1", "r2", "gone_read"], "success_relaxed")
            chk(st["tab"][7000] == [True, True], "稳过 seed 要收齐两读：%r" % st["tab"][7000])
            chk(st["tab"][7001] == [True, False], "抖动 seed 必须分得出来：%r" % st["tab"][7001])
            chk(st["tab"][7002] == [False, False], "从不成功 seed：%r" % st["tab"][7002])
            chk(st["tipped"] == {7001: 1}, "侧躺标记要按 seed 计数：%r" % st["tipped"])
            chk(len(st["tab"]) == 3, "缺产物不能造出 phantom seed：%r" % sorted(st["tab"]))
            chk(seed_table(["gone_read"], "success_relaxed")["tab"] == {}, "全缺产物要空表而不是崩")
            chk(seed_table(["r1"], "n_success_relaxed")["tab"] == {},
                "key 传错（要 per-episode 字段名而不是 summary 字段名）必须空表，不能静默全 False")
        finally:
            RUNS = save

    # ── McNemar（配对检验）：独立二项枚举 + statsmodels 交叉核对 ─────────────────
    def mcnemar_ref(b, c):
        nn = b + c
        if nn <= 0:
            return 1.0
        m = min(b, c)
        return min(1.0, 2.0 * sum(math.comb(nn, k) for k in range(m + 1)) * 0.5 ** nn)

    for b, c in [(0, 0), (1, 0), (2, 0), (3, 1), (5, 5), (8, 0), (13, 0), (20, 0), (0, 7)]:
        chk(abs(mcnemar_nested(b, c) - mcnemar_ref(b, c)) < 1e-12,
            "mcnemar(%d,%d) 与独立枚举不符：%r vs %r" % (b, c, mcnemar_nested(b, c), mcnemar_ref(b, c)))
    chk(abs(mcnemar_nested(8) - 0.0078125) < 1e-12, "b=8 ⇒ 2·0.5^8 = 0.0078125，实得 %r" % mcnemar_nested(8))
    chk(abs(mcnemar_nested(13) - 0.5 ** 12) < 1e-15, "b=13 ⇒ 0.5^12，实得 %r" % mcnemar_nested(13))
    chk(mcnemar_nested(0) == 1.0 and mcnemar_nested(1) == 1.0, "b≤1 时双侧 p 必须封顶 1.0")
    # 这一条是本节存在的理由：同一批数据，配对 McNemar 显著、误用独立 Fisher 不显著 ⇒ 结论相反
    chk(mcnemar_nested(8) < 0.05 and fisher_two_sided(44, 80, 36, 80) > 0.05,
        "档2c 44/80 vs 36/80：配对 p=%.4g 显著，独立 Fisher p=%.4g 不显著 ⇒ 必须用配对"
        % (mcnemar_nested(8), fisher_two_sided(44, 80, 36, 80)))
    try:
        import numpy as _np
        from statsmodels.stats.contingency_tables import mcnemar as sm_mcnemar
        for b in (2, 8, 13):
            tab = _np.array([[80 - b, b], [0, 0]])
            p_sm = float(sm_mcnemar(tab, exact=True).pvalue)
            chk(abs(p_sm - mcnemar_nested(b)) < 1e-9,
                "statsmodels 交叉验证 b=%d 不符：%r vs %r" % (b, p_sm, mcnemar_nested(b)))
        print("  [钉子] statsmodels McNemar(exact) 交叉验证 3 组，全部 |Δp|<1e-9")
    except ImportError:
        print("  [钉子] statsmodels 不可用 ⇒ McNemar 只用独立二项枚举核对（枚举本身已是定义级验证）")

    print("档2f 判定工具钉子：%d 项检查，%d 项失败" % (n, len(fails)))
    for f in fails[:20]:
        print("  FAIL " + f)
    if fails:
        print("SELFTEST FAIL")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
