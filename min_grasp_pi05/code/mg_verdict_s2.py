#!/usr/bin/env python
"""档 2 判定汇编：把所有产物读成一张**可直接贴进 STAGE_PLAN 的判定表**，并自动出门/不出门。

为什么要有这个脚本，而不是人工看日志抄数字：
  * 档 2 的判定涉及 **7 个门组 + 2 个复跑 + 4 个专家上界 + 档 1 的 3 次基线读数**，
    分散在十几个 `eval_summary.json` 里。人工汇编在凌晨/交接班时极易抄错一格，
    而抄错的就是「过门/不过门」本身。
  * 判定规则是**阈值 + 相对上界 + 相对档 1 回退**三个条件同时成立，人脑同时握三条容易漏。
  * 反向的上界只有 70%，绝对数与相对数必须同时报（STAGE_PLAN「门与附加口径」），
    脚本强制两个都打出来，少一个就报警。

口径（与 STAGE_PLAN 档 2 一致，改这里=改结论，必须同步改文档）：
  门 1  正向 未见 20 局 K=10 ≥ 50%
  门 2  反向 未见 20 局 K=10 ≥ 50%
  门 3  正向 未见 相对**档 1**（rand60，同 seed 区间同 K）回退 ≤ 15 pp
  并列  正向/反向 K=50（标准 chunk 执行）如实报，不设门
  对照  训练 seed 组只用来判「是不是记忆」，不设门
  复跑  同一组有 ≥2 次读数时，**逐次都列出来** + 给合并值；单读 20 局 1σ≈10 pp，
        落在门 ±10 pp 内而没有第二次读数 ⇒ 直接标 `NEEDS_RERUN`，不给最终判定。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_verdict_s2.py'
    # 训练/评测还没跑完时也能用：缺的组会标 MISSING，不影响已到的组出数。
"""
from __future__ import annotations

import json
import os
import sys
from math import comb
from pathlib import Path

MG = Path(__file__).resolve().parent.parent
# MG_RUNS 可覆盖产物根目录：**只为了能用假数据自测判定逻辑**。
# 判定工具本身若坏了，比没有更糟（凌晨出结果时会给错门），所以必须能在不碰真产物的前提下测。
# 自测方法见文件末尾 `--selftest`。
RUNS = Path(os.environ.get("MG_RUNS", str(MG / "runs")))

GATE_FWD = 0.50          # 门 1 / 门 2
GATE_REV = 0.50
MAX_FWD_REGRESS_PP = 15.0  # 门 3：相对档 1 最多回退 15 个百分点
RERUN_BAND_PP = 10.0       # 落在门 ±10 pp 内必须有第二次读数


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def collect(dirs: list[str]) -> list[dict]:
    """把一组目录名（同一逻辑组、多次读数）的 eval_summary 收进来，按目录名排序保证稳定。"""
    out = []
    for d in dirs:
        s = load(RUNS / d / "eval_summary.json")
        if s is None:
            out.append({"dir": d, "missing": True})
        else:
            s = dict(s)
            s["dir"] = d
            out.append(s)
    return out


def fmt_reads(reads: list[dict]) -> tuple[str, float | None, int, int, bool]:
    """返回 (逐次读数字符串, 合并成功率 or None, 合并成功数, 合并局数, 是否有缺失)."""
    parts, ns, ne, missing = [], 0, 0, False
    for i, r in enumerate(reads, 1):
        if r.get("missing"):
            parts.append(f"#{i}:MISSING")
            missing = True
            continue
        parts.append(f"#{i}:{r['n_success']}/{r['episodes']}={r['pc_success']*100:.0f}%")
        ns += r["n_success"]
        ne += r["episodes"]
    pooled = (ns / ne) if ne else None
    # 分隔符用 <br> 而不是 " | "：本脚本的输出是要**直接贴进 markdown 表格**的，
    # 竖线会被当成列分隔符，把一格撑成好几列（第一版就是这么花的）。
    return "<br>".join(parts) if parts else "-", pooled, ns, ne, missing


# ── 组定义：(键, 人类名, 目录列表, 上界目录列表 or None) ────────────────────────
GROUPS = [
    ("FWD_TEST", "门1 正向 未见 2000..2019 K=10",
     # 后两格同样是补读（chain_s2c_jointbase.sh），同一个 `last`、同一批 TEST seed。
     # 补的理由见坑 29：判 50% 的门 40 局不够，而且只给失败方向补读 = 用两把尺子。
     ["s2_gate_fwd_test_rand20_k10", "s2_gate_fwd_test_rand20_k10_rep2",
      "s2c_jointbase_fwd_test_rand20_k10_rep3", "s2c_jointbase_fwd_test_rand20_k10_rep4"],
     ["s2_ceiling_fwd_test20_n05"]),
    ("REV_TEST", "门2 反向 未见 7000..7019 K=10",
     # 后两格是档 2c 补读的基线（chain_s2c_jointbase.sh）：**同一个** `last` 检查点、
     # **同一批** TEST seed、同一 K，所以可以并进同一组。补读的理由见 chain_s2c_jointbase.sh
     # 头注释（40 局判不了 50% 的门：实测同检查点同 seed 三读 = 30% / 35% / 55%）。
     ["s2_gate_rev_test_rand20_k10", "s2_gate_rev_test_rand20_k10_rep2",
      "s2c_jointbase_rev_test_rand20_k10_rep3", "s2c_jointbase_rev_test_rand20_k10_rep4"],
     ["s2_ceiling_rev_test20_n05"]),
    ("FWD_K50", "并列 正向 K=50（标准 chunk 执行）",
     ["s2_gate_fwd_test_rand20_k50"], ["s2_ceiling_fwd_test20_n05"]),
    ("REV_K50", "并列 反向 K=50（标准 chunk 执行）",
     ["s2_gate_rev_test_rand20_k50"], ["s2_ceiling_rev_test20_n05"]),
    ("FWD_CTRL", "对照 正向 训练 seed 1000..1009",
     ["s2_gate_fwd_control_train10_k10"], None),
    ("REV_CTRL", "对照 反向 训练 seed 5000..5009",
     ["s2_gate_rev_control_train10_k10"], None),
    ("FWD_REGR", "回归 档 0 固定初态 seed 0 K=10",
     ["s2_gate_fwd_regression_fixed20_k10"], None),
]

# 档 1 基线（门 3 的比较对象）：rand60 训出的检查点，同 seed 区间同 K，三次读数
S1_BASELINE = ["s1_gate_test_rand20_k10", "s1_gate_test_rand20_k10_rep2", "s1_gate_test_rand20_k10_rep3"]
# 档 0/档 1 的固定初态基线（回归项的参照）
FIXED_BASELINE = ["s1_gate_regression_fixed20_k10"]

# ── 修正口径：关门检查点 = val 选点（不是 last）────────────────────────────
# 为什么会有第二套读数：档 2 第一次关门用的是 `checkpoints/last`(=014400)，
# 而 sweep_bidir 的 val 曲线显示正反向**同时**在 011000 达峰、之后一路掉
# （rev 13000=0/10）。用 last 关门等于把「选点」交给了「训练什么时候停」。
# 修正读数由 code/chain_s2fix.sh 产出；选点规则与 val 曲线见
# runs/pi05_mix60f60r_s2/ckpt_selection.json（由 code/mg_select_ckpt.py 落盘）。
# ⚠️ 这套 TEST 只准读一次：读完再回来换规则重选 = 在 test 上挑检查点。
FIX_GROUPS = [
    ("FWD_TEST_FIX", "门1' 正向 未见 2000..2019 K=10 @val选点",
     ["s2fix_fwd_test_rand20_k10", "s2fix_fwd_test_rand20_k10_rep2"],
     ["s2_ceiling_fwd_test20_n05"]),
    ("REV_TEST_FIX", "门2' 反向 未见 7000..7019 K=10 @val选点",
     ["s2fix_rev_test_rand20_k10", "s2fix_rev_test_rand20_k10_rep2", "s2fix_rev_test_rand20_k10_rep3"],
     ["s2_ceiling_rev_test20_n05"]),
    ("FWD_CTRL_FIX", "对照 正向 训练 seed 1000..1009 @val选点",
     ["s2fix_fwd_control_train10_k10"], None),
    ("REV_CTRL_FIX", "对照 反向 训练 seed 5000..5009 @val选点",
     ["s2fix_rev_control_train10_k10"], None),
]


def ceiling_of(dirs):
    if not dirs:
        return None
    best = None
    for d in dirs:
        c = load(RUNS / d / "ceiling_summary.json")
        if c and (best is None or c["episodes"] > best["episodes"]):
            best = c
    return best


def fisher_two_sided(a: int, n1: int, b: int, n2: int) -> float:
    """两组二项成功率的双侧 Fisher 精确检验 p 值。

    为什么不用「c > t + 0.10」这种拍脑袋阈值：
    对照组只有 10 局（1σ≈16 pp），TEST 组 40 局（1σ≈8 pp）。
    2026-10-01 档 2 判定就用旧阈值把 50%(5/10) vs 32.5%(13/40) 判成
    「训练 seed 明显更好 ⇒ 有记忆成分，需查 seed 泄漏」，白追了一条不存在的线索
    （Fisher p≈0.34，两组差异完全在噪声内）。比例差必须配显著性一起报。
    纯 stdlib（math.comb）实现，小样本下是精确值，不给判定工具添 scipy 依赖。
    """
    if n1 <= 0 or n2 <= 0:
        return 1.0
    total = a + b
    lo, hi = max(0, total - n2), min(n1, total)
    xs = list(range(lo, hi + 1))
    weights = [comb(n1, x) * comb(n2, total - x) for x in xs]
    denom = sum(weights)
    if denom == 0:
        return 1.0
    p_obs = weights[a - lo] / denom
    return min(1.0, sum(w / denom for w in weights if w / denom <= p_obs + 1e-12))


def main() -> int:
    print("# 档 2 判定汇编  (mg_verdict_s2.py)")
    print(f"# 产物根目录：{RUNS}")

    def group_data(dirs, ceil_dirs) -> dict:
        reads = collect(dirs)
        s, pooled, ns, ne, missing = fmt_reads(reads)
        return {"pooled": pooled, "ns": ns, "ne": ne, "missing": missing, "reads_str": s,
                "n_reads": sum(1 for r in reads if not r.get("missing")),
                "ceiling": ceiling_of(ceil_dirs), "reads": reads}

    def group_row(key: str, name: str, g: dict) -> str:
        c, pooled = g["ceiling"], g["pooled"]
        if c:
            ctxt = f"{c['n_success']}/{c['episodes']}={c['pc_success']*100:.0f}%"
            rtxt = (f"{pooled*100:.0f}% / {c['pc_success']*100:.0f}% = "
                    f"{pooled/c['pc_success']*100:.0f}%") if pooled is not None else "-"
        else:
            ctxt, rtxt = "-", "-"
        ptxt = (f"**{g['ns']}/{g['ne']} = {pooled*100:.1f}%**" if pooled is not None
                else ("MISSING" if g["missing"] else "-"))
        return f"| `{key}` | {name} | {g['reads_str']} | {ptxt} | {ctxt} | {rtxt} |"

    data = {key: group_data(dirs, cdirs) for key, _, dirs, cdirs in GROUPS + FIX_GROUPS}

    print("\n## 一、门组与并列读数（原口径：关门检查点 = `checkpoints/last`）\n")
    print("| 组 | 口径 | 逐次读数 | 合并 | 专家上界 | 相对上界 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for key, name, _, _ in GROUPS:
        print(group_row(key, name, data[key]))

    # ── 档 1 基线 ──
    s1 = collect(S1_BASELINE)
    s1s, s1p, s1ns, s1ne, s1miss = fmt_reads(s1)
    fx = collect(FIXED_BASELINE)
    fxs, fxp, fxns, fxne, fxmiss = fmt_reads(fx)
    print("\n## 二、门 3 的比较基线（档 1，同 seed 区间同 K）\n")
    # 这两行在**列表**里而不是表格里，<br> 会渲染成生硬的换行，换回空格分隔。
    print(f"* 档 1 正向未见 K=10：{s1s.replace('<br>', '   ')}  ⇒ 合并 **{s1ns}/{s1ne}"
          f" = {(s1p*100 if s1p else 0):.1f}%**（三次独立读数，单读 1σ≈10 pp）")
    print(f"* 档 1 固定初态 K=10：{fxs.replace('<br>', '   ')}  ⇒ 合并 {fxns}/{fxne} = {(fxp*100 if fxp else 0):.1f}%")

    # ── 反向超时体检 ──
    print("\n## 三、反向超时体检（horizon=400；专家均值 312 步、最紧一局 375 步）\n")
    rev = [r for r in data["REV_TEST"]["reads"] if not r.get("missing")]
    if rev:
        steps = [e["steps"] for r in rev for e in r["per_episode"] if e["success"]]
        timeouts = [e["steps"] for r in rev for e in r["per_episode"] if not e["success"] and e["steps"] >= 400]
        if steps:
            print(f"* 反向成功局步数：n={len(steps)} 均值 {sum(steps)/len(steps):.0f} "
                  f"最大 {max(steps)}（余量 {400-max(steps)} 步）")
            print(f"* 反向超时局（跑满 400 步未成功）：{len(timeouts)} 局")
            if max(steps) > 385:
                print("* ⚠️ 成功局已逼近 horizon，**策略比专家慢**；若继续加数据/训练要先考虑抬 horizon（改口径需单独记录）")
        else:
            print("* 反向暂无成功局，无法体检步数")
    else:
        print("* MISSING（反向 TEST 组还没产物）")

    # ── 判定（两套读数共用同一份阈值与复跑规则，只有「关门检查点」不同）──
    def judge(fwd_key: str, rev_key: str, labels: tuple) -> tuple:
        verdicts, notes = [], []
        l1, l2, l3 = labels
        suffix = "_FIX" if fwd_key.endswith("_FIX") else ""

        def check(label, g, gate):
            pooled, n_reads, ne = g["pooled"], g["n_reads"], g["ne"]
            if pooled is None:
                verdicts.append((label, "MISSING", "产物未到，无法判"))
                return
            ok = pooled >= gate
            spread = abs(pooled - gate) * 100
            if spread <= RERUN_BAND_PP and n_reads < 2:
                verdicts.append((label, "NEEDS_RERUN",
                                 f"{pooled*100:.1f}% 距门 {gate*100:.0f}% 只有 {spread:.1f} pp"
                                 f"（≤{RERUN_BAND_PP:.0f} pp），而单读 {ne} 局的 1σ≈10 pp"
                                 " ⇒ **必须复跑再判**，现在不下结论"))
                return
            verdicts.append((label, "PASS" if ok else "FAIL",
                             f"{pooled*100:.1f}% {'≥' if ok else '<'} 门 {gate*100:.0f}%"
                             f"（{n_reads} 次读数 / {ne} 局）"))

        check(l1, data[fwd_key], GATE_FWD)
        check(l2, data[rev_key], GATE_REV)

        # 门 3：相对档 1 回退
        if data[fwd_key]["pooled"] is not None and s1p is not None:
            drop = (s1p - data[fwd_key]["pooled"]) * 100
            ok3 = drop <= MAX_FWD_REGRESS_PP
            verdicts.append((l3, "PASS" if ok3 else "FAIL",
                             f"档 2 {data[fwd_key]['pooled']*100:.1f}% vs 档 1 {s1p*100:.1f}%"
                             f" ⇒ 回退 {drop:+.1f} pp（门 ≤{MAX_FWD_REGRESS_PP:.0f} pp）"))
        else:
            verdicts.append((l3, "MISSING", "档 2 或档 1 基线缺产物"))

        # 记忆对照（不设门，但要报方向 + 显著性）
        for base, tkey in (("FWD", fwd_key), ("REV", rev_key)):
            key = base + "_CTRL" + suffix
            c, t = data[key]["pooled"], data[tkey]["pooled"]
            if c is None or t is None:
                continue
            cs, cn = data[key]["ns"], data[key]["ne"]
            ts, tn = data[tkey]["ns"], data[tkey]["ne"]
            pv = fisher_two_sided(cs, cn, ts, tn)
            diff_pp = (c - t) * 100
            if pv < 0.05 and diff_pp > 0:
                tag = f"⚠️ 训练 seed **显著**更好（Fisher 双侧 p={pv:.3f}）⇒ 有记忆成分，需查 seed 泄漏"
            elif diff_pp > 10:
                tag = (f"训练 seed 高 {diff_pp:+.0f} pp 但**不显著**（Fisher 双侧 p={pv:.2f}，"
                       f"对照组只有 {cn} 局）⇒ 局数不够，**不能**判记忆；要判就把对照组加到 ≥30 局")
            else:
                tag = f"训练 seed **不比**未见 seed 显著更好（Fisher 双侧 p={pv:.2f}）⇒ 没有记忆证据"
            notes.append(f"{key} {cs}/{cn}={c*100:.0f}% vs {tkey} {ts}/{tn}={t*100:.0f}%：{tag}")
        return verdicts, notes

    def report(verdicts, notes, rev_key: str, headline_pass: str, headline_fail: str):
        for label, st, why in verdicts:
            icon = {"PASS": "✅", "FAIL": "❌", "MISSING": "⏳", "NEEDS_RERUN": "⚠️"}[st]
            print(f"* {icon} **{label}** — {st}：{why}")
        if notes:
            print("\n对照读数（不设门）：")
            for n in notes:
                print(f"* {n}")
        decided = [v for v in verdicts if v[1] in ("PASS", "FAIL")]
        if len(decided) == len(verdicts) and decided:
            allpass = all(v[1] == "PASS" for v in decided)
            print(f"\n## 总判定：{headline_pass if allpass else headline_fail}")
            if not allpass:
                rev_p = data[rev_key]["pooled"]
                if rev_p is not None and 0.35 <= rev_p < GATE_REV:
                    print("→ 反向落在 35~50% = 「接近上界、未达门」。**机理诊断已经做完了，别重复**："
                          "A/B/C 分类账 + 逐 seed 对上界见 `runs/_diag/tax_rev_test.md`；"
                          "选点消融见本文「六、」；单任务干扰消融见 `runs/S2C_VERDICT.md`。"
                          "剩下的处方只有两条，按 S2C 的分支走：R1/R3 ⇒ 改数据配比；R2 ⇒ 加反向数据到 120 条。")
                elif rev_p is not None and rev_p < 0.35:
                    print("→ 反向 <35% **不是数据量问题**。机理诊断已经做完了（`runs/_diag/tax_rev_test.md`）："
                          "A 没抓起 / B 抓起了没送到 / C 送到了没落定 ≈ 44/39/17%，三类都有 ⇒ 不是单一 bug。"
                          "**别再回去翻 action 对齐 / normalizer / 夹爪语义**——那些在档 0、档 1 已逐条自证过，"
                          "而且正向同一模型能到 60~70%，管路是通的。")
            return allpass
        pend = [v[0] for v in verdicts if v[1] in ("MISSING", "NEEDS_RERUN")]
        print(f"\n## 总判定：⏳ 未定（待补：{', '.join(pend)}）")
        return None

    # 修正口径是否已经齐活：反向 ≥2 次读数 + 正向 ≥1 次读数（缺一就仍以原口径为准）
    fix_ready = data["REV_TEST_FIX"]["n_reads"] >= 2 and data["FWD_TEST_FIX"]["n_reads"] >= 1
    print("\n## 四、判定（原口径：关门检查点 = `checkpoints/last` = 014400）\n")
    if fix_ready:
        print("* ⚠️ 本节保留作**审计记录**（原口径用 last 关门，是协议缺陷）；"
              "权威判定见「六、关门检查点修正」。\n")
    report(*judge("FWD_TEST", "REV_TEST",
                  ("门1 正向未见 K=10", "门2 反向未见 K=10", "门3 正向相对档 1 回退")),
           "REV_TEST", "✅ 档 2 通过，可进档 3", "❌ 档 2 未通过")

    # 档 2b
    ci = load(RUNS / "s2_crossinstr" / "crossinstr_summary.json")
    if ci:
        print("\n## 五、档 2b 交叉指令探针（语言 vs 视觉捷径）\n")
        # 两个标志位分开报，别混成一个：
        #   conclusion_valid  = **出处**：检查点是不是正反向混合数据集训的（不是就没资格谈语言条件化）
        #   probe_conclusive  = **行为**：交叉格有没有「行为冻结」（can 根本没被碰过）
        # 第二项是 2026-10-01 补的：原实现把「can 纹丝不动」算成「照指令字符串走（不搬运）」，
        # 于是一次策略停摆就能被读成「π₀.₅ 真的在做语言条件化」。
        print(f"* 出处 conclusion_valid = {ci.get('conclusion_valid')}"
              f"（数据集 `{Path(str(ci.get('dataset_of_ckpt') or '')).name or '未知'}`）")
        pc = ci.get("probe_conclusive")
        print(f"* 行为 probe_conclusive = {pc}"
              + ("（旧产物没这个字段 ⇒ 跑 `mg_probe_crossinstr.py --rescore <dir>` 重算）"
                 if pc is None else ""))
        for v in ci.get("verdict", []):
            print(f"  * `{v.get('cell')}` 照场景 {v.get('follow_scene')} / 照字符串 {v.get('follow_string')}"
                  f" / 冻结 {v.get('frozen', '?')} / 混杂 {v.get('ambiguous')}"
                  f"（n={v.get('episodes')}）：{v.get('read')}")
        for c in ci.get("cells", []):
            print(f"  * 行为分布 `{c.get('tag')}`：{c.get('behavior_counts')}"
                  f"，场景判据成功率 {c.get('scene_success_rate', 0)*100:.0f}%")
        for k in ("frozen_note", "conclusion_warning"):
            if ci.get(k):
                print(f"* ⚠️ {ci[k]}")
        if pc:
            print("* ⇒ 可以据此谈语言条件化。")
        else:
            print("* ⇒ **本探针不出结论**。要真判语言条件化，得加一个能区分「冻结」与「听懂了不搬」"
                  "的观测量（例如 eef 是否到过本场景目标上方），或改用「同一场景、两条指令」的对照设计。")

    # ── 六、关门检查点修正（val 选点）──
    sel = load(RUNS / "pi05_mix60f60r_s2" / "ckpt_selection.json")
    has_fix = sel is not None or any(data[k]["n_reads"] for k, _, _, _ in FIX_GROUPS)
    if has_fix:
        print("\n## 六、关门检查点修正（val 选点 = 权威口径）\n")
        if sel:
            ck = "/".join(Path(sel["selected_ckpt"]).parts[-3:])
            curve = sel.get("curve", {}).get(str(sel.get("selected_step")), {})
            fs = curve.get("fwd", {}).get("seed_base", "?")
            rs = curve.get("rev", {}).get("seed_base", "?")
            print(f"* 选点规则（**事先写死**，不看 test）：`{sel.get('rule')}`")
            print(f"* 选中 step = **{sel.get('selected_step')}**"
                  f"（得分 {sel.get('selected_score')}，并列 {sel.get('tied_steps')}，"
                  f"扫描 {len(sel.get('curve', {}))} 个点）⇒ `{ck}`")
            print(f"* val seed：正向 {fs}.. / 反向 {rs}..（与训练 seed、TEST seed 三区互不相交）")
            print(f"* 原口径为什么偏低：正反向 val **同时**在 {sel.get('selected_step')} 达峰后回落"
                  "（反向 13000 一度 0/10），用 `last` 关门 = 交出训练尾巴上最差的那一步。")
        else:
            print("* ⚠️ 没有 `ckpt_selection.json`：选点过程不可审计，本节读数只能当参考。")
        print("\n| 组 | 口径 | 逐次读数 | 合并 | 专家上界 | 相对上界 |")
        print("| --- | --- | --- | --- | --- | --- |")
        for key, name, _, _ in FIX_GROUPS:
            print(group_row(key, name, data[key]))
        print()
        report(*judge("FWD_TEST_FIX", "REV_TEST_FIX",
                      ("门1' 正向未见 K=10 @val选点", "门2' 反向未见 K=10 @val选点",
                       "门3' 正向相对档 1 回退 @val选点")),
               "REV_TEST_FIX", "✅ 档 2 通过（修正口径），可进档 3", "❌ 档 2 仍未通过（修正口径）")
        print("\n* 口径说明：门3' 的比较基线（档 1 = 70%）当初也是用 `last` 关的门，"
              "严格比应把档 1 也换成它自己的 val 选点；本表按原基线报，差值属**保守**估计。")
    return 0


# ── 自测：用假产物验证判定逻辑本身 ────────────────────────────────────────────
# 为什么必须有：这个脚本是**门**的实现。门若判错，比没有门更糟 —— 它会在凌晨
# 给出一个看起来很权威的错结论，然后触发错误的预案（白采数据 + 10 小时重训）。
# 所以判定逻辑必须能在不碰真产物的前提下被测到。跑：`$MG_PY code/mg_verdict_s2.py --selftest`
def _mk(root: Path, name: str, ns: int, ne: int, k: int = 10, steps: int = 250):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    per = [{"ep": i, "seed": 2000 + i, "success": i < ns,
            "success_step": steps if i < ns else -1, "steps": steps if i < ns else 400,
            "min_dist_to_target_xy": 0.01, "max_lift_cm": 9.0} for i in range(ne)]
    (d / "eval_summary.json").write_text(json.dumps({
        "n_action_steps": k, "episodes": ne, "n_success": ns,
        "pc_success": (ns / ne if ne else 0.0), "per_episode": per,
        "task_mode": "reverse" if "rev" in name else "forward",
        "seed": 7000 if "rev" in name else 2000, "seed_mode": "random"}))


def _mk_ceil(root: Path, name: str, ns: int, ne: int):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "ceiling_summary.json").write_text(json.dumps({
        "episodes": ne, "n_success": ns, "pc_success": ns / ne}))


def _mk_sel(root: Path, step: int = 11000):
    """假的 ckpt_selection.json：只为让「六、」那节走完整条打印路径。"""
    d = root / "pi05_mix60f60r_s2"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ckpt_selection.json").write_text(json.dumps({
        "rule": "argmax(fwd_val_n + rev_val_n); tie-break earliest",
        "selected_step": step, "selected_score": 13, "tied_steps": [step],
        "selected_ckpt": f"/x/runs/pi05_mix60f60r_s2/checkpoints/{step:06d}/pretrained_model",
        "curve": {str(step): {"fwd": {"n_success": 8, "episodes": 10, "seed_base": 3000},
                              "rev": {"n_success": 5, "episodes": 10, "seed_base": 8000}}}}))


def selftest() -> int:
    import io
    import contextlib
    import tempfile
    global RUNS

    def run(build) -> str:
        with tempfile.TemporaryDirectory() as td:
            # ⚠️ 这里必须**再声明一次** global：外层 selftest 的 `global RUNS` 不会传进嵌套函数，
            #    少了这行，赋值只会建一个 run() 的局部变量，main() 仍然读**真的** runs/ ——
            #    于是假数据写进临时目录、判定读真产物，自测「看起来在跑」其实什么都没测到。
            #    第一版就是这么错的，靠场景 A 该 PASS 却报 MISSING 才暴露出来。
            global RUNS
            RUNS = Path(td)
            build(RUNS)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main()
            return buf.getvalue()

    def base(root: Path):
        """每个场景都有的公共背景：档 1 基线 70%、上界 正100%/反70%。"""
        for i, d in enumerate(S1_BASELINE):
            _mk(root, d, 14, 20)
        _mk(root, FIXED_BASELINE[0], 17, 20)
        _mk_ceil(root, "s2_ceiling_fwd_test20_n05", 20, 20)
        _mk_ceil(root, "s2_ceiling_rev_test20_n05", 14, 20)

    cases = []

    def scene_a(root):   # 双向都清楚过门
        base(root)
        _mk(root, "s2_gate_fwd_test_rand20_k10", 14, 20)
        _mk(root, "s2_gate_fwd_test_rand20_k10_rep2", 14, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10", 12, 20, steps=330)
        _mk(root, "s2_gate_rev_test_rand20_k10_rep2", 12, 20, steps=330)
    cases.append(("A 双向过门", scene_a, ["门1 正向未见 K=10** — PASS", "门2 反向未见 K=10** — PASS",
                                          "门3 正向相对档 1 回退** — PASS", "档 2 通过，可进档 3"]))

    def scene_b(root):   # 反向卡在门上且只有一次读数 -> 必须拒绝下结论
        base(root)
        _mk(root, "s2_gate_fwd_test_rand20_k10", 14, 20)
        _mk(root, "s2_gate_fwd_test_rand20_k10_rep2", 14, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10", 11, 20)   # 55%，距门 5 pp
    cases.append(("B 反向贴门单读→拒判", scene_b, ["门2 反向未见 K=10** — NEEDS_RERUN", "必须复跑再判", "总判定：⏳ 未定"]))

    def scene_c(root):   # 反向 40%（两次读数）-> FAIL + 走「接近上界」预案
        base(root)
        _mk(root, "s2_gate_fwd_test_rand20_k10", 14, 20)
        _mk(root, "s2_gate_fwd_test_rand20_k10_rep2", 14, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10", 8, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10_rep2", 8, 20)
    cases.append(("C 反向40%→FAIL+预案", scene_c, ["门2 反向未见 K=10** — FAIL", "档 2 未通过", "接近上界、未达门"]))

    def scene_d(root):   # 正向绝对值过门，但相对档 1 掉了 20 pp -> 门3 FAIL
        base(root)
        _mk(root, "s2_gate_fwd_test_rand20_k10", 10, 20)   # 50%
        _mk(root, "s2_gate_fwd_test_rand20_k10_rep2", 10, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10", 12, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10_rep2", 12, 20)
    cases.append(("D 正向回退20pp→门3 FAIL", scene_d, ["门1 正向未见 K=10** — PASS",
                                                       "门3 正向相对档 1 回退** — FAIL", "回退 +20.0 pp", "档 2 未通过"]))

    def scene_e(root):   # 什么都没有 -> 未定，且不崩
        base(root)
    cases.append(("E 产物全缺→未定", scene_e, ["FWD_TEST` | 门1", "MISSING", "总判定：⏳ 未定"]))

    def scene_f(root):   # last 反向 FAIL，但 val 选点后反向过门 -> 六节翻盘
        base(root)
        _mk(root, "s2_gate_fwd_test_rand20_k10", 12, 20)
        _mk(root, "s2_gate_fwd_test_rand20_k10_rep2", 12, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10", 6, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10_rep2", 7, 20)
        _mk_sel(root)
        _mk(root, "s2fix_rev_test_rand20_k10", 12, 20)
        _mk(root, "s2fix_rev_test_rand20_k10_rep2", 11, 20)
        _mk(root, "s2fix_rev_test_rand20_k10_rep3", 12, 20)
        _mk(root, "s2fix_fwd_test_rand20_k10", 13, 20)
        _mk(root, "s2fix_fwd_test_rand20_k10_rep2", 13, 20)
        _mk(root, "s2fix_rev_control_train10_k10", 6, 10)
        _mk(root, "s2fix_fwd_control_train10_k10", 7, 10)
    cases.append(("F val选点翻盘→修正口径PASS", scene_f, [
        "## 六、关门检查点修正", "门2' 反向未见 K=10 @val选点** — PASS",
        "档 2 通过（修正口径），可进档 3", "本节保留作**审计记录**",
        "门2 反向未见 K=10** — FAIL"]))

    def scene_g(root):   # val 选点后反向仍然不达标 -> 修正口径照样 FAIL，不许粉饰
        base(root)
        _mk(root, "s2_gate_fwd_test_rand20_k10", 12, 20)
        _mk(root, "s2_gate_fwd_test_rand20_k10_rep2", 12, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10", 6, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10_rep2", 7, 20)
        _mk_sel(root)
        _mk(root, "s2fix_rev_test_rand20_k10", 7, 20)
        _mk(root, "s2fix_rev_test_rand20_k10_rep2", 7, 20)
        _mk(root, "s2fix_rev_test_rand20_k10_rep3", 6, 20)
        _mk(root, "s2fix_fwd_test_rand20_k10", 12, 20)
        _mk(root, "s2fix_fwd_test_rand20_k10_rep2", 12, 20)
    cases.append(("G val选点后反向仍FAIL", scene_g, [
        "门2' 反向未见 K=10 @val选点** — FAIL", "档 2 仍未通过（修正口径）",
        "REV_TEST_FIX` | 门2'", "20/60 = 33.3%"]))

    def scene_h(root):   # 修正读数只有 1 次且贴门 -> 六节必须拒判，不能拿单读翻盘
        base(root)
        _mk(root, "s2_gate_fwd_test_rand20_k10", 12, 20)
        _mk(root, "s2_gate_fwd_test_rand20_k10_rep2", 12, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10", 6, 20)
        _mk(root, "s2_gate_rev_test_rand20_k10_rep2", 7, 20)
        _mk_sel(root)
        _mk(root, "s2fix_rev_test_rand20_k10", 11, 20)     # 55%，距门 5 pp，单读
        _mk(root, "s2fix_fwd_test_rand20_k10", 13, 20)
        _mk(root, "s2fix_fwd_test_rand20_k10_rep2", 13, 20)
    cases.append(("H 修正单读贴门→拒判", scene_h, [
        "门2' 反向未见 K=10 @val选点** — NEEDS_RERUN", "必须复跑再判"]))

    fails = 0
    for name, build, expects in cases:
        try:
            out = run(build)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ {name}: 抛异常 {type(exc).__name__}: {exc}")
            fails += 1
            continue
        bad = [e for e in expects if e not in out]
        if bad:
            fails += 1
            print(f"❌ {name}: 缺断言 {bad}")
            for line in out.splitlines():
                if "门" in line or "总判定" in line:
                    print(f"     | {line}")
        else:
            print(f"✅ {name}")
    print(f"\nselftest: {len(cases) - fails}/{len(cases)} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
