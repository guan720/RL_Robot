#!/usr/bin/env python
"""档 7B 判定汇编：把预注册的五条判据（M1~M5）读成一张表 + 一行结论。

**判据、阈值、分支全部出自 `runs/S7_PREREG.md`（2026-10-03 13:55 落盘，早于任何 7B 读数）。**
本文件只做三件事：读盘、按预注册阈值判、把出身核清楚。不新设门、不改门（坑 40）。

五条判据（出处 `runs/S7_PREREG.md` §3 格 7B）：
  M1（主，机理会）  7B 的 11 格 val 曲线 vs batch8-seed2000 的 11 格，epoch ≥ 1.03 的 9 格、
                    **放宽口径**配对符号检验；门 = **≥8 胜 且 0 负**（p ≤ 0.0078）。
  M2（副，防退化）  7B 的 TEST 放宽口径 ≥ **41.2%**（= batch8-seed2000 的 33/80）。
                    不过 ⇒ M1 即使过也**不采信**（一个塌到 0 的配方当然方差小）。
  M3（副，欠拟合哨兵）7B 末点 loss ≤ **0.042**（= 1.5 × batch8-seed2000 的 0.0280）。
  M4（主门，使命）  7B 的 TEST 放宽口径 ≥ **50%**（与档 3r 完全同一条门）。
  M5（护栏）        正向未见 20 局 vs 基线 193/300 = 64.3%，掉幅 ≤ **15 pp**。

⚠️ n=1 的配方高低比较没有意义（坑 57）⇒ M4 过了也只说「新配方至少不崩」，
   **不等于** seed 稳健性已解决；那需要 7C（同配方 3 个 seed，门 C2 = 最差 ≥50%）。

用法：
    $MG_PY code/mg_verdict_s7.py --selftest
    $MG_PY code/mg_verdict_s7.py > runs/S7_VERDICT.md
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

from mg_seedcurve import fisher2, parse_train_log, paired_grid, read_cells, sign_test_exact  # noqa: E402
from mg_verdict_s2 import fisher_two_sided  # noqa: E402
from mg_verdict_s2f import ci, collect, pct  # noqa: E402
import mg_epoch_curve as EC  # noqa: E402  冻结文件，只 import（steps_per_epoch）

# ── 预注册常数（改这里等于改门 ⇒ 必须先改 runs/S7_PREREG.md 并注明日期）──────
BS = 32
SEED = 2000
STEPS = 5500
SAVE_FREQ = 500
LR = "2e-4"
JOB = f"pi05_mix60f120r_s7b_bs{BS}_seed{SEED}"
RUN = MG / "runs" / JOB
BASE8 = MG / "runs" / "pi05_mix60f120r_s3r_seed2000"
TEST_DIRS = [f"s7b_bs{BS}_seed{SEED}_rev_test_rand20_k10" + ("" if i == 1 else f"_rep{i}")
             for i in range(1, 5)]
FWD_DIRS = [f"s7b_bs{BS}_seed{SEED}_fwd_test_rand20_k10"]
GATE_M1_WINS = 8            # ≥8 胜
GATE_M1_LOSSES = 0          # 且 0 负
M2_MIN = (33, 80)           # 41.2%
M3_LOSS_MAX = 0.042         # 1.5 × 0.0280
M4_GATE = 0.50
M5_BASELINE = (193, 300)    # 档 3 三个训练 seed 的正向未见合并
M5_DROP_PP = 15.0
MIN_EPOCH = 1.03
GRADNOISE = MG / "runs" / "s7_probe" / "gradnoise.json"
B8_FINAL_LOSS = 0.0280      # batch8-seed2000 的末点 loss（runs/_diag/seedcurve_sign_strict.md 第三节）


# ─────────────────────────── 纯函数 ───────────────────────────
def decide(m1: bool | None, m2: bool | None, m3: bool | None, m4: bool | None) -> dict:
    """预注册 §3 的判定表。评估顺序：M3 → M2 → M1/M4（表里未列的组合按同一优先级归并）。"""
    if m3 is False:
        return {"row": "lr/步数配错", "verdict": "⚠️ 配方参数错",
                "next": "开 lr 对照臂（1e-4 与 4e-4 各一发）；不要放弃 batch 假设",
                "trust_m1": False}
    # M3 之后才查 None：M3=False 本身就是决定性的（预注册表第 5 行里 M1/M2/M4 都是「—」），
    # 但其余判据缺读数时**不许静默当成通过** —— 那会造出一个看起来合理的错结论。
    if m1 is None or m2 is None or m3 is None or m4 is None:
        return {"row": "判据缺读数", "verdict": "⚠️ 无法判定",
                "next": "补齐缺的读数后重跑本工具（缺哪条看第一节表里的「—」）", "trust_m1": False}
    if m2 is False:
        return {"row": "M1 ✅ / M2 ❌（或 M1 也 ❌）", "verdict": "❌ **不采信**（配方退化）",
                "next": "查 M3 的 loss/grdn 诊断；开 lr 对照臂", "trust_m1": False}
    if m1 is True:
        if m4 is True:
            return {"row": "M1✅ M2✅ M3✅ M4✅", "verdict": "✅ **H7 支持，新配方达标**",
                    "next": "发 7C（seed 1000/3000 同配方），凑 n=3 看极差是否 < 38.8 pp",
                    "trust_m1": True}
        return {"row": "M1✅ M2✅ M3✅ M4❌", "verdict": "🟡 方向对但没过使命门",
                "next": "发 7C；若 7C 极差也收窄 ⇒ 用「新配方 + 早筛（epoch 1.72、T∈(0.05,0.30]）」组合",
                "trust_m1": True}
    if m1 is False:
        return {"row": "M1❌ M2✅ M3✅", "verdict": "❌ **H7 的 P2 预测失败**",
                "next": "转备择假设 A1（数据顺序）/ A3（简并解族太宽）：加数据或加 epoch；不再烧 batch",
                "trust_m1": True}
    return {"row": "落空（不该到这里）", "verdict": "⚠️ 无法判定",
            "next": "decide() 的分支没覆盖这个组合 ⇒ 先修 decide 再读判定", "trust_m1": False}


def m1_from_grids(g: list[dict]) -> dict:
    """把配对格表算成 M1 的读数。"""
    w = sum(1 for x in g if x["winner"] == "a")
    l = sum(1 for x in g if x["winner"] == "b")
    t = sum(1 for x in g if x["winner"] == "tie")
    return {"grids": len(g), "wins": w, "losses": l, "ties": t,
            "sign_p": sign_test_exact(w, l),
            "median_delta_pp": statistics.median([x["delta_pp"] for x in g]) if g else float("nan"),
            "pass": (len(g) >= 1 and w >= GATE_M1_WINS and l <= GATE_M1_LOSSES),
            "ref": "参照：batch8 的 seed3000 对 seed2000 正好是 9 胜 0 负（p=0.0039，放宽口径）"}


def loss_diag(rows: list[dict]) -> dict:
    """M3 的读数 + 预注册里写好的两个诊断分支（训崩 / 欠拟合）。"""
    if not rows:
        return {"ok": None, "final_loss": None, "final_grdn": None, "note": "训练日志解析出 0 行"}
    fl, fg = rows[-1]["loss"], rows[-1]["grdn"]
    note = ""
    if fl > M3_LOSS_MAX:
        note = ("grdn 末值 %.3f > 1.0 ⇒ **训崩**（lr 太大）" % fg) if fg > 1.0 else \
               ("grdn 末值 %.3f < 0.05 且 loss 高 ⇒ **欠拟合**" % fg if fg < 0.05
                else "loss 高但 grdn 正常 ⇒ 需要 lr 对照臂才能分清")
    return {"ok": fl <= M3_LOSS_MAX, "final_loss": fl, "final_grdn": fg,
            "ratio_vs_b8": fl / B8_FINAL_LOSS, "note": note or "loss 在门内"}


def provenance(d: str) -> dict:
    """出身核对：读错权重/错 K/错 seed 窗口的读数一律标 broken（坑 32/38）。"""
    f = MG / "runs" / d / "eval_summary.json"
    if not f.is_file():
        return {"dir": d, "ok": False, "why": "产物不在"}
    j = json.loads(f.read_text())
    ck = str(j.get("policy_ckpt", ""))
    bad = []
    if not ck.endswith(f"{JOB}/checkpoints/last/pretrained_model"):
        bad.append(f"policy_ckpt 不是 7B 的 last：{ck}")
    if int(j.get("n_action_steps", -1)) != 10:
        bad.append(f"K={j.get('n_action_steps')} ≠ 10")
    if j.get("seed_mode") != "random":
        bad.append(f"seed_mode={j.get('seed_mode')} ≠ random")
    if int(j.get("episodes", 0)) != 20:
        bad.append(f"episodes={j.get('episodes')} ≠ 20")
    want_seed = 7000 if "rev_test" in d else 2000
    if int(j.get("seed", -1)) != want_seed:
        bad.append(f"seed={j.get('seed')} ≠ {want_seed}")
    want_mode = "reverse" if "rev_test" in d else "forward"
    if j.get("task_mode") != want_mode:
        bad.append(f"task_mode={j.get('task_mode')} ≠ {want_mode}")
    return {"dir": d, "ok": not bad, "why": "; ".join(bad), "ckpt": ck,
            "task": j.get("task"), "criterion_prov": (j.get("criterion") or {}).get("provenance")}


# ─────────────────────────── 主流程 ───────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    missing = []
    for d in TEST_DIRS + FWD_DIRS:
        if not (MG / "runs" / d / "eval_summary.json").is_file():
            missing.append(d)
    if not (RUN / "train.log").is_file():
        missing.append(f"{JOB}/train.log")
    nd = len(list((RUN / "sweep_rev").glob("step_*_rev"))) if (RUN / "sweep_rev").is_dir() else 0
    if nd < 11:
        missing.append(f"{JOB}/sweep_rev（只有 {nd}/11 格）")
    if missing:
        print("# 档 7B 判定：**读数不齐，无法判定**\n")
        print("缺：")
        for m in missing:
            print(f"* `{m}`")
        print(f"\n（生成时间 {datetime.now():%F %T}；补齐后重跑 `$MG_PY code/mg_verdict_s7.py`）")
        return 2

    # 出身
    prov = [provenance(d) for d in TEST_DIRS + FWD_DIRS]
    bad_prov = [p for p in prov if not p["ok"]]

    # TEST 两口径
    rel = collect(TEST_DIRS, "n_success_relaxed", "pc_success_relaxed")
    strict = collect(TEST_DIRS, "n_success", "pc_success")
    fwd = collect(FWD_DIRS, "n_success_relaxed", "pc_success_relaxed")

    # M1
    spe7, src7 = EC.steps_per_epoch(RUN)
    spe8, src8 = EC.steps_per_epoch(BASE8)
    c7 = read_cells(RUN, "sweep_rev", "rev", spe7)
    c8 = read_cells(BASE8, "sweep_rev", "rev", spe8)
    g = paired_grid(c7, c8, MIN_EPOCH, "relaxed")
    m1 = m1_from_grids(g)

    # M3
    rows = parse_train_log((RUN / "train.log").read_text(errors="ignore"))
    m3 = loss_diag(rows)

    # M2 / M4
    rate_rel = rel["k"] / rel["n"] if rel["n"] else 0.0
    m2 = rate_rel >= M2_MIN[0] / M2_MIN[1] - 1e-9
    m4 = rate_rel >= M4_GATE

    # M5
    rate_fwd = fwd["k"] / fwd["n"] if fwd["n"] else 0.0
    base = M5_BASELINE[0] / M5_BASELINE[1]
    drop_pp = 100 * (base - rate_fwd)
    m5 = drop_pp <= M5_DROP_PP
    # 签名是 (k1, n1, k2, n2)（出处 code/mg_verdict_s2.py:147），不是 2×2 表
    m5_p = fisher_two_sided(fwd["k"], fwd["n"], M5_BASELINE[0], M5_BASELINE[1])

    # 7A-2
    gn = json.loads(GRADNOISE.read_text()) if GRADNOISE.is_file() else {}
    fit = gn.get("fit") or {}
    eta8 = (fit.get("eta") or {}).get("8") or (fit.get("eta") or {}).get(8)

    dec = decide(m1["pass"] if m1["grids"] else None, m2, m3["ok"], m4)

    L = ["# 档 7B 判定：把 run 间方差压下去（batch 8 → 32，等 epoch）", "",
         f"* 生成时间：{datetime.now():%F %T}（`code/mg_verdict_s7.py`）",
         f"* 预注册出处：`runs/S7_PREREG.md`（2026-10-03 13:55 落盘，**早于本档任何读数**）",
         f"* run：`runs/{JOB}`（bs={BS}、steps={STEPS}={3.79} ep、save_freq={SAVE_FREQ}、"
         f"log_freq=25、lr={LR}、grad-ckpt on、seed={SEED}、基座 `pi05_base_lr044`、"
         f"数据 `{RUN.name and 'mix60f120r'}`）",
         f"* 对照臂：`runs/{BASE8.name}`（batch8、22000 步、同数据同基座同 K，唯一差 batch 及其绑定项）",
         "", "## 一、五条判据", "",
         "| 判据 | 内容 | 读数 | 门 | 结果 |", "|:--|:--|:--|:--|:--|"]
    L.append(f"| **M1** 主（机理会） | 11 格 val 曲线 vs batch8-seed2000，epoch≥{MIN_EPOCH} 的配对格、"
             f"**放宽口径**符号检验 | {m1['wins']} 胜 / {m1['losses']} 负 / {m1['ties']} 平"
             f"（{m1['grids']} 格），Δrate 中位 {m1['median_delta_pp']:+.1f} pp，"
             f"符号 p={m1['sign_p']:.4f} | ≥{GATE_M1_WINS} 胜 且 {GATE_M1_LOSSES} 负 | "
             f"{'✅' if m1['pass'] else '❌'} |")
    L.append(f"| **M2** 副（防退化） | TEST 放宽口径 | {rel['k']}/{rel['n']} = {pct(rel['k'], rel['n'])}"
             f"（Wilson {ci(rel['k'], rel['n'])}） | ≥ {M2_MIN[0]}/{M2_MIN[1]} = "
             f"{100*M2_MIN[0]/M2_MIN[1]:.1f}% | {'✅' if m2 else '❌'} |")
    L.append(f"| **M3** 副（欠拟合哨兵） | 末点 loss | {m3['final_loss']:.4f}"
             f"（= batch8-seed2000 的 {m3['ratio_vs_b8']:.2f}×），末点 grdn {m3['final_grdn']:.3f} | "
             f"≤ {M3_LOSS_MAX} | {'✅' if m3['ok'] else '❌'} |")
    L.append(f"| **M4** 主门（使命） | TEST 放宽口径 | {rel['k']}/{rel['n']} = {pct(rel['k'], rel['n'])} | "
             f"≥ {M4_GATE:.0%} | {'✅' if m4 else '❌'} |")
    L.append(f"| **M5** 护栏（正向不退化） | 正向未见 20 局 | {fwd['k']}/{fwd['n']} = "
             f"{pct(fwd['k'], fwd['n'])} vs 基线 {M5_BASELINE[0]}/{M5_BASELINE[1]} = "
             f"{100*base:.1f}% ⇒ 掉 {drop_pp:+.1f} pp，Fisher p={m5_p:.4g} | 掉幅 ≤ {M5_DROP_PP} pp | "
             f"{'✅' if m5 else '🚫'} |")
    L += ["", f"- M1 参照：{m1['ref']}", f"- M3 诊断：{m3['note']}",
          f"- 侧躺标记（放宽算成功、严格不算）：{rel['tipped']} 局；严格口径并列 "
          f"{strict['k']}/{strict['n']} = {pct(strict['k'], strict['n'])}（不参与门）", ""]

    L += ["## 二、判定（预注册 §3 的判定表）", "",
          f"* 命中行：**{dec['row']}**", f"* {dec['verdict']}", f"* 下一步：{dec['next']}", "",
          f"* M1 是否采信：**{'是' if dec['trust_m1'] else '否'}**"
          + ("" if dec["trust_m1"] else "（M2/M3 不过 ⇒ 按预注册，M1 即使过也不采信）"),
          f"* M5 护栏：{'✅ 通过' if m5 else '🚫 不过（拆东墙补西墙）'}", ""]

    L += ["## 三、格 7A-2 的机理读数（H7 的必要条件）", ""]
    if fit.get("ok"):
        L += [f"* 分支 = **{gn.get('branch')}**；G = {fit.get('G'):.6f}、C = {fit.get('C'):.6f}",
              f"* η₈ = **{eta8:.2%}**（batch 8 下噪声占 E‖g‖² 的比例）；"
              f"η₃₂ = {((fit.get('eta') or {}).get('32') or (fit.get('eta') or {}).get(32)):.2%}",
              "* 出处 `runs/s7_probe/gradnoise.md`；⚠️ 这只是必要条件，"
              "「降噪声 ⇒ 降 run 间成功率方差」由 M1 检验", ""]
    else:
        L += ["* 7A-2 拟合不可用（见 `runs/s7_probe/gradnoise.md`）⇒ 机理这一栏空缺，不影响 M1~M5", ""]

    L += ["## 四、逐格明细（M1 的原始读数）", "",
          "| epoch | 7B step | 7B 放宽 | batch8-seed2000 step | batch8 放宽 | Δ(pp) | 胜方 | 单格 Fisher p |",
          "|---:|---:|---:|---:|---:|---:|:--|---:|"]
    for x in g:
        L.append(f"| {x['epoch']:.3f} | {x['step']} | {x['a_k']}/{x['a_n']} = {x['a_rate']:.0%} | "
                 f"{int(round(x['epoch'] * spe8))} | {x['b_k']}/{x['b_n']} = {x['b_rate']:.0%} | "
                 f"{x['delta_pp']:+.1f} | {'7B' if x['winner']=='a' else ('b8' if x['winner']=='b' else '平')} | "
                 f"{x['fisher_p']:.3f} |")
    L += ["", f"- steps/epoch：7B = {spe7}（{src7}）；batch8 = {spe8}（{src8}）",
          "- ⚠️ 单格 n=20、p≈0.3 时 1σ≈10 pp ⇒ **单格 Fisher 检不出**，M1 只看符号一致性",
          "- ⚠️ 同一 run 的相邻检查点相关 ⇒ 符号 p 读作「方向一致性强度」，不是无偏 I 类错误率", ""]

    L += ["## 五、出身核对", "", "| 读数 | 结果 | 说明 |", "|:--|:--|:--|"]
    for p in prov:
        L.append(f"| `{p['dir']}` | {'✅' if p['ok'] else '🚫'} | {p['why'] or 'ckpt/K/seed 窗口/task_mode/局数全对'} |")
    L += ["", f"* `collect` 的缺产物：{rel['missing'] or '无'}；缺放宽字段：{rel['nofield'] or '无'}；"
          f"不变量（严格 ⊆ 放宽）被破坏：{rel['broken'] or '无'}",
          f"* 判据串出处：{(prov[0].get('criterion_prov') or '（未记录）')}",
          f"* task 串：`{prov[0].get('task')}`", ""]

    L += ["## 六、这一档**没有**证明什么（诚实标注）", "",
          "* n=1 ⇒ **不能**说「bs32 配方比 bs8 配方好」（坑 57：run 间极差 38.8 pp ≫ 任何已知效应）。",
          "* M4 过了也只说「新配方这一发不崩」，**seed 稳健性缺口要靠 7C（n=3、门 C2）才能关闭**。",
          "* C1（极差 < 38.8 pp）在 n=3 上只有 2 个自由度 ⇒ 即使 7C 跑了也只能读方向。",
          "* 「早筛协议」的阈值来自 §1.6 的**回溯**表（21/81 组合完美分类）；"
          "要当协议用必须由 7C 的 C3 前瞻验证。",
          "* 本档不动任何冻结文件；档 3r 的 FAIL 判定**保持原样**，本档只新增本文件。", "",
          "## 七、复现", "", "```bash",
          f"bash code/chain_s7b.sh            # 闸 -> 7A-2 -> 训练 -> 扫描 -> TEST -> 判定",
          "$MG_PY code/mg_verdict_s7.py --selftest",
          "$MG_PY code/mg_verdict_s7.py > runs/S7_VERDICT.md", "```", ""]

    print("\n".join(L))
    if bad_prov:
        print(f"\n⚠️ 有 {len(bad_prov)} 个读数出身不对（见第五节）⇒ 本判定不采信", file=sys.stderr)
        return 3
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

    # --- decide：预注册判定表的每一行 + 未列组合 ---
    chk("M1✅M2✅M3✅M4✅ ⇒ H7 支持", decide(True, True, True, True)["row"] == "M1✅ M2✅ M3✅ M4✅")
    chk("  ⇒ 下一步是发 7C", "7C" in decide(True, True, True, True)["next"])
    chk("M1✅M2✅M3✅M4❌ ⇒ 方向对但没过门", decide(True, True, True, False)["verdict"].startswith("🟡"))
    chk("  ⇒ 仍发 7C", "7C" in decide(True, True, True, False)["next"])
    chk("M1✅M2❌ ⇒ 不采信", "不采信" in decide(True, False, True, True)["verdict"])
    chk("  ⇒ trust_m1=False", decide(True, False, True, True)["trust_m1"] is False)
    chk("M1❌M2✅M3✅ ⇒ P2 失败", "P2" in decide(False, True, True, True)["verdict"])
    chk("  ⇒ 转 A1/A3、不再烧 batch", "A1" in decide(False, True, True, True)["next"])
    chk("M3❌ ⇒ lr/步数配错（优先级最高）", decide(True, True, False, True)["row"] == "lr/步数配错")
    chk("M3❌ 时 M2 即使 ❌ 也走 lr 分支", decide(True, False, False, True)["row"] == "lr/步数配错")
    chk("M1❌M2❌M3✅ ⇒ 归到不采信（表里未列，按优先级）",
        "不采信" in decide(False, False, True, False)["verdict"])
    chk("M1=None（缺读数）⇒ 无法判定", decide(None, True, True, True)["verdict"].startswith("⚠️"))
    chk("M2=None ⇒ 无法判定", decide(True, None, True, True)["verdict"].startswith("⚠️"))
    chk("全 None ⇒ 无法判定", decide(None, None, None, None)["verdict"].startswith("⚠️"))
    chk("M4=None ⇒ 无法判定", decide(True, True, True, None)["verdict"].startswith("⚠️"))
    chk("M3=None ⇒ 无法判定", decide(True, True, None, True)["verdict"].startswith("⚠️"))
    chk("M3=False 优先于 None（它自己就是决定性的）",
        decide(None, None, False, None)["row"] == "lr/步数配错")
    chk("所有分支都带 next", all(decide(a, b, c, d).get("next")
                                 for a in (True, False, None) for b in (True, False, None)
                                 for c in (True, False, None) for d in (True, False, None)))
    chk("所有分支都带 verdict", all(decide(a, b, c, d).get("verdict")
                                    for a in (True, False, None) for b in (True, False, None)
                                    for c in (True, False, None) for d in (True, False, None)))

    # --- m1_from_grids：门 = ≥8 胜 且 0 负 ---
    mk = lambda w, l, t: ([{"winner": "a", "delta_pp": 10.0}] * w    # noqa: E731
                          + [{"winner": "b", "delta_pp": -10.0}] * l
                          + [{"winner": "tie", "delta_pp": 0.0}] * t)
    chk("9胜0负 ⇒ 过（p=0.0039）", m1_from_grids(mk(9, 0, 0))["pass"] is True)
    chk("8胜0负1平 ⇒ 过（p=0.0078）", m1_from_grids(mk(8, 0, 1))["pass"] is True)
    chk("8胜1负 ⇒ 不过（门要 0 负）", m1_from_grids(mk(8, 1, 0))["pass"] is False)
    chk("7胜0负 ⇒ 不过（门要 ≥8 胜）", m1_from_grids(mk(7, 0, 0))["pass"] is False)
    chk("0胜9负 ⇒ 不过", m1_from_grids(mk(0, 9, 0))["pass"] is False)
    chk("空格表 ⇒ 不过（不静默 PASS）", m1_from_grids([])["pass"] is False)
    chk("符号 p 算对（9/0 ⇒ 0.00390625）", abs(m1_from_grids(mk(9, 0, 0))["sign_p"] - 2 / 512) < 1e-12)
    chk("符号 p 算对（8/1 ⇒ 0.0390625）", abs(m1_from_grids(mk(8, 1, 0))["sign_p"] - 20 / 512) < 1e-12)
    chk("平局不计入符号检验", m1_from_grids(mk(8, 0, 1))["sign_p"] == m1_from_grids(mk(8, 0, 0))["sign_p"]
        or abs(m1_from_grids(mk(8, 0, 1))["sign_p"] - 2 / 256) < 1e-12)
    chk("Δrate 中位数算对", abs(m1_from_grids([{"winner": "a", "delta_pp": 5.0},
                                               {"winner": "a", "delta_pp": 15.0}])["median_delta_pp"] - 10.0) < 1e-9)
    chk("grids 计数对", m1_from_grids(mk(5, 2, 1))["grids"] == 8)

    # --- loss_diag ---
    r_ok = [{"loss": 0.030, "grdn": 0.15}]
    chk("loss 0.030 ≤ 0.042 ⇒ M3 过", loss_diag(r_ok)["ok"] is True)
    chk("边界 0.042 ⇒ 过（含等号）", loss_diag([{"loss": 0.042, "grdn": 0.1}])["ok"] is True)
    chk("0.0421 ⇒ 不过", loss_diag([{"loss": 0.0421, "grdn": 0.1}])["ok"] is False)
    chk("loss 高 + grdn>1 ⇒ 判「训崩」", "训崩" in loss_diag([{"loss": 0.9, "grdn": 3.0}])["note"])
    chk("loss 高 + grdn<0.05 ⇒ 判「欠拟合」", "欠拟合" in loss_diag([{"loss": 0.9, "grdn": 0.01}])["note"])
    chk("loss 高 + grdn 正常 ⇒ 判「需要 lr 对照臂」",
        "lr 对照臂" in loss_diag([{"loss": 0.9, "grdn": 0.2}])["note"])
    chk("ratio_vs_b8 = loss/0.0280", abs(loss_diag([{"loss": 0.056, "grdn": 0.1}])["ratio_vs_b8"] - 2.0) < 1e-9)
    chk("空日志 ⇒ ok=None 不崩", loss_diag([])["ok"] is None)
    chk("取的是**末点**不是均值", loss_diag([{"loss": 0.9, "grdn": 1.0}, {"loss": 0.02, "grdn": 0.1}])["final_loss"] == 0.02)

    # --- 常数对账：门必须与预注册一致 ---
    chk("M2 门 = 33/80 = 41.25%", abs(M2_MIN[0] / M2_MIN[1] - 0.4125) < 1e-9)
    chk("M3 门 = 1.5 × batch8 末点 loss 0.0280", abs(M3_LOSS_MAX - 1.5 * B8_FINAL_LOSS) < 1e-9)
    chk("M4 门 = 0.50（与档 3r 同一条）", M4_GATE == 0.50)
    chk("M5 基线 = 193/300（档 3 三 seed 合并）", M5_BASELINE == (193, 300))
    chk("M5 掉幅门 = 15 pp", M5_DROP_PP == 15.0)
    chk("min_epoch = 1.03（与档 3r 补充/档 6 早筛同一个切点）", MIN_EPOCH == 1.03)
    chk("等 epoch 步数 = 5500（bs32）", STEPS == 5500 and BS == 32)
    chk("save_freq=500 ⇒ steps 是整数倍（坑 33/38）", STEPS % SAVE_FREQ == 0)
    chk("TEST 读数目录 4 个（4×20=80 局）", len(TEST_DIRS) == 4)
    chk("TEST 目录命名含 rev_test_rand20_k10", all("rev_test_rand20_k10" in d for d in TEST_DIRS))
    chk("护栏目录命名含 fwd_test", all("fwd_test" in d for d in FWD_DIRS))

    # --- provenance（造盘）---
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 临时把 MG 指到 tmp，造一个合格读数
        import mg_verdict_s7 as V
        saved = V.MG
        try:
            V.MG = root
            d = root / "runs" / "s7b_bs32_seed2000_rev_test_rand20_k10"
            d.mkdir(parents=True)
            good = {"policy_ckpt": str(root / "runs" / JOB / "checkpoints" / "last" / "pretrained_model"),
                    "n_action_steps": 10, "seed_mode": "random", "episodes": 20, "seed": 7000,
                    "task_mode": "reverse", "task": "T", "criterion": {"provenance": "P"}}
            (d / "eval_summary.json").write_text(json.dumps(good))
            chk("合格读数 ⇒ ok", V.provenance("s7b_bs32_seed2000_rev_test_rand20_k10")["ok"] is True)
            (d / "eval_summary.json").write_text(json.dumps({**good, "n_action_steps": 50}))
            chk("K=50 ⇒ 揪出来", "K=50" in V.provenance("s7b_bs32_seed2000_rev_test_rand20_k10")["why"])
            (d / "eval_summary.json").write_text(json.dumps({**good, "seed": 9000}))
            chk("错 seed 窗口 ⇒ 揪出来", "seed=9000" in V.provenance("s7b_bs32_seed2000_rev_test_rand20_k10")["why"])
            (d / "eval_summary.json").write_text(json.dumps({**good, "episodes": 10}))
            chk("局数不对 ⇒ 揪出来", "episodes=10" in V.provenance("s7b_bs32_seed2000_rev_test_rand20_k10")["why"])
            (d / "eval_summary.json").write_text(json.dumps(
                {**good, "policy_ckpt": "/somewhere/else/checkpoints/last/pretrained_model"}))
            chk("读错权重 ⇒ 揪出来", "不是 7B 的 last" in V.provenance("s7b_bs32_seed2000_rev_test_rand20_k10")["why"])
            (d / "eval_summary.json").write_text(json.dumps({**good, "task_mode": "forward"}))
            chk("task_mode 反了 ⇒ 揪出来", "task_mode" in V.provenance("s7b_bs32_seed2000_rev_test_rand20_k10")["why"])
            chk("产物不在 ⇒ ok=False 且不崩", V.provenance("nope_not_here")["ok"] is False)
            # 正向护栏的期望 seed 是 2000 而不是 7000
            df = root / "runs" / "s7b_bs32_seed2000_fwd_test_rand20_k10"
            df.mkdir(parents=True)
            (df / "eval_summary.json").write_text(json.dumps(
                {**good, "seed": 2000, "task_mode": "forward",
                 "policy_ckpt": str(root / "runs" / JOB / "checkpoints" / "last" / "pretrained_model")}))
            chk("正向护栏期望 seed=2000 ⇒ ok", V.provenance("s7b_bs32_seed2000_fwd_test_rand20_k10")["ok"] is True)
            (df / "eval_summary.json").write_text(json.dumps(
                {**good, "seed": 7000, "task_mode": "forward",
                 "policy_ckpt": str(root / "runs" / JOB / "checkpoints" / "last" / "pretrained_model")}))
            chk("正向护栏用了反向 seed 窗口 ⇒ 揪出来",
                V.provenance("s7b_bs32_seed2000_fwd_test_rand20_k10")["ok"] is False)
        finally:
            V.MG = saved

    # --- fisher2 与 mg_verdict_s2.fisher_two_sided 必须同源（两套实现不许各说各话，坑 54）---
    # 注意签名不同：本模块 fisher2(a,b,c,d) 收 2×2 表；mg_verdict_s2.fisher_two_sided(k1,n1,k2,n2)
    # 收「成功数, 局数」⇒ 换算 (a, a+b, c, c+d)。搞混会得到一个看起来合理的错 p。
    for (a, b, c, d) in [(11, 9, 3, 17), (64, 16, 33, 47), (55, 25, 42, 38),
                         (20, 0, 0, 20), (13, 27, 9, 11), (7, 13, 7, 13)]:
        p1, p2 = fisher2(a, b, c, d), fisher_two_sided(a, a + b, c, c + d)
        chk(f"fisher2({a},{b},{c},{d})={p1:.6f} 与 mg_verdict_s2 的 {p2:.6f} 一致",
            abs(p1 - p2) < 1e-9)
    chk("fisher_two_sided 的参考值没漂（档 2 自测的同一个锚）",
        abs(fisher_two_sided(6, 20, 2, 20) - 0.23511623511623514) < 1e-12)
    chk("fisher2 同一锚（5/20 vs 15/20 的表）与上式一致",
        abs(fisher2(6, 14, 2, 18) - 0.23511623511623514) < 1e-12)
    chk("空表：fisher2 给 1.0 而 mg_verdict_s2 会 IndexError ⇒ 本模块只用 fisher2",
        fisher2(0, 0, 0, 0) == 1.0)

    print(f"[selftest] {ok} passed, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
