#!/usr/bin/env python
"""档 2e 判定：反向数据翻倍 + 2:1 配比，能不能把反向抬过 50% 的门。

⚠️ 本文件的规则是在 **mix60f120r 还没收完、档 2e 一步都还没训**的时候写死的
   （2026-10-01 23:45）。跑完不许改：改规则重判 = 在 TEST 上挑结论，门就没意义了。

口径（与档 2 / 档 2c 逐字对齐，只有数据变）：
  主读数 P_2e = 反向 **未见** TEST seed 7000..7019、K=10、`last` 检查点、**4 读 × 20 局 = 80 局**。
  为什么是 80 局：坑 29 实测同检查点同 seed 三读能给出 30%/35%/55%，40 局判不了 50% 的门；
  80 局把 1σ 压到 ~5 pp，才谈得上「显著/不显著」。
  基线（都已在盘上，不重跑）：档 2 联合 @last = 30/80 = 37.5%；档 2c 反向单任务 @last（见 S2C_VERDICT.md）。

预注册判定：
  P1  P_2e ≥ 50%                                  ⇒ **PASS**：反向过门，处方（数据翻倍 + 2:1）有效。
  P2  P_2e < 50% 且 Fisher(P_2e vs 37.5%) p<0.05  ⇒ **FAIL 但数据是杠杆**：方向对、剂量不够
                                                    ⇒ 下一步继续加数据/加密度，不要转去改口径。
  P3  P_2e < 50% 且 p≥0.05                        ⇒ **FAIL 且数据量不是杠杆**：
                                                    ⇒ 转去修 A 类抓空（占失败 44%，示范/口径侧），
                                                      别再往「加数据」上烧 GPU。
护栏（任一 MISSING ⇒ 该项**悬空**，判定降级为「待补」，**不作废**，同 mg_verdict_s2c 的三态纪律）：
  GA 正向不回退：正向 TEST 2000..2019、K=10、2 读 40 局 ≥ 50%（档 2 门 1 同门）。
     2:1 把正向占比压到 1/3，正向掉了就是「拆东墙补西墙」，必须报出来。
  GB 无碾压式记忆：反向**训练 seed** 对照 4 读 40 局（坑 32：n=10 几乎没功效，要 ≥8/10 才触发；
     40 局才判得动）。判记忆的门槛沿用档 2c：Fisher p<0.05 **且** 对照比 TEST 高 >10 pp。
     注意措辞：通过只能说「没有碾压式记忆的证据」，不能说「排除了记忆」。
  GC 数据完整性：`runs/s2e_data.done` 必须存在（它背后是集数收满 / 正向逐比特复现 /
     反向是旧 60 条严格超集 + 不撞留出 seed 三道闸，见 code/chain_s2e_data.sh）。
  GD（**只报告、不判定**）normalizer 漂移：换数据集 ⇒ stats 重算，这是本档与档 2/2c 之间
     无法消除的第三个变量。所以把 mix60f60r 与 mix60f120r 的 stats.json 差值量出来写进判定，
     让读者知道「37.5% → P_2e」这个差里有多少可能来自归一化而不是数据量。
     严格的归因需要同数据集内的 1:1 对照臂（命令见 code/run_pi05_s2e.sh 头注释，备而不用）。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_verdict_s2e.py'
    bash -c 'source code/env.sh && $MG_PY code/mg_verdict_s2e.py --selftest'
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mg_verdict_s2 import fisher_two_sided  # noqa: E402
from mg_verdict_s2c import RUNS as _DEFAULT_RUNS, fmt, one, pool  # noqa: E402

RUNS = Path(os.environ.get("MG_RUNS", str(_DEFAULT_RUNS)))
MG = RUNS.parent
DATA = MG / "data"

GATE = 0.50
FWD_GATE = 0.50
MEMO_MIN_PP = 10.0
S2E_LAST = ["s2e_rev_test_rand20_k10", "s2e_rev_test_rand20_k10_rep2",
            "s2e_rev_test_rand20_k10_rep3", "s2e_rev_test_rand20_k10_rep4"]
JOINT_LAST = ["s2_gate_rev_test_rand20_k10", "s2_gate_rev_test_rand20_k10_rep2",
              "s2c_jointbase_rev_test_rand20_k10_rep3", "s2c_jointbase_rev_test_rand20_k10_rep4"]
S2C_LAST = ["s2c_rev_test_rand20_k10", "s2c_rev_test_rand20_k10_rep2",
            "s2c_rev_test_rand20_k10_rep3", "s2c_rev_test_rand20_k10_rep4"]
S2E_VALSEL = ["s2e_revsel_test_rand20_k10", "s2e_revsel_test_rand20_k10_rep2",
              "s2e_revsel_test_rand20_k10_rep3"]
S2E_FWD = ["s2e_fwd_test_rand20_k10", "s2e_fwd_test_rand20_k10_rep2"]
S2E_CTRL = ["s2e_rev_control_train10_k10", "s2e_rev_control_train10_k10_rep2",
            "s2e_rev_control_train10_k10_rep3", "s2e_rev_control_train10_k10_rep4"]
DATA_MARK = "s2e_data.done"
RUN_DIR = "pi05_mix60f120r_s2e"
OLD_STATS = "mix60f60r"
NEW_STATS = "mix60f120r"
# 放宽口径的专家上界（档 2f 阶段 A 重测，与策略同口径才可比 —— README 坑 40②）
CEIL_RELAX = "s2f_ceiling_rev_test20_n05"


def decide(p2e, n2e, pjb, njb, ga_state, gb_state, gc_state) -> list[str]:
    """执行预注册规则。*_state ∈ {'ok','bad','missing'}。返回判定文本行。"""
    out = []
    pending = [k for k, v in (("GA 正向不回退", ga_state), ("GB 无碾压式记忆", gb_state),
                              ("GC 数据完整性", gc_state)) if v == "missing"]
    bad = [k for k, v in (("GA 正向不回退", ga_state), ("GB 无碾压式记忆", gb_state),
                          ("GC 数据完整性", gc_state)) if v == "bad"]
    if n2e == 0:
        out.append("⏳ 主读数还没落盘 ⇒ **无法判定**（不是作废，等 4 读齐了重跑本工具）。")
        return out
    # ⚠️ 签名是 (成功数A, 试验数A, 成功数B, 试验数B)，不是 (成功, 失败, ...)
    pv = fisher_two_sided(p2e, n2e, pjb, njb) if njb else float("nan")
    rate = p2e / n2e
    if rate >= GATE:
        out.append("✅ **P1 PASS**：反向未见 %s ≥ 门 %.0f%% ⇒ 处方（反向翻倍 + 2:1 配比）有效。"
                   % (fmt(p2e, n2e), GATE * 100))
    elif pv == pv and pv < 0.05:
        out.append("❌ **P2 FAIL，但数据是杠杆**：%s < %.0f%%，然而对档 2 联合基线（%s）"
                   "Fisher **p=%.4g < 0.05** ⇒ 方向对、剂量不够。"
                   % (fmt(p2e, n2e), GATE * 100, fmt(pjb, njb), pv))
        out.append("   处方：**继续加反向数据/加位姿密度**，不要转去改成功口径（那是掩盖，不是解决）。")
    else:
        out.append("❌ **P3 FAIL，数据量不是杠杆**：%s < %.0f%%，且对基线（%s）Fisher p=%s ≥ 0.05。"
                   % (fmt(p2e, n2e), GATE * 100, fmt(pjb, njb),
                      "n/a" if pv != pv else "%.4g" % pv))
        out.append("   处方：**停止往「加数据」上烧 GPU**，转去修 A 类抓空（占失败 44%，"
                   "见 runs/_diag/lift_profile.md 与 diag_miss_s2c_rev.json 的 H1/H2/H3 归因）。")
    if pending:
        out.append("⚠️ 护栏 %s 的产物还没到 ⇒ 判定**悬空**（pending），补齐后重跑本工具；"
                   "**不作废**（同档 2c 的三态纪律）。" % "、".join(pending))
    if bad:
        out.append("🚫 护栏 %s **不成立** ⇒ 本档结论**作废**，先修护栏再谈成功率。" % "、".join(bad))
    return out


def relaxed_block(dirs: list[str], label: str) -> list[str]:
    """并列报「放宽口径」，**不参与** P1/P2/P3。

    为什么必须放进这份判定：预注册门是按严格口径（can 要**立着**落定）写的，而用户 2026-10-02
    把「送到目标区」定为首要条件、侧躺也算送到（要打标）。两个口径可能给出不同结论，
    这份文件若只印严格那一个，读者会以为档 2e 的结论跟 `runs/S2F_RELAX_VERDICT.md` 打架。
    纪律（README 坑 40）：历史数值不追改 / 两口径并排 / 上界同口径 / **缺字段 ≠ 0** / p 重算。
    """
    ks = ns = kr = nr = tip = 0
    missing, nofield = [], []
    for d in dirs:
        f = RUNS / d / "eval_summary.json"
        if not f.is_file():
            missing.append(d)
            continue
        try:
            j = json.loads(f.read_text())
        except Exception:
            nofield.append(d)
            continue
        if "n_success_relaxed" not in j:
            nofield.append(d)          # 改判据前跑的：剔除，绝不当 0 计入
            continue
        # 严格列**只**统计同时带放宽字段的读 ⇒ 两列是同一批 rollout，才谈得上「口径效应」
        ks += int(j.get("n_success", 0))
        ns += int(j.get("episodes", 0))
        kr += int(j["n_success_relaxed"])
        nr += int(j["episodes"])
        tip += int(j.get("n_delivered_tipped", 0))

    out = ["**放宽口径**（%s）：送到 bin1 ±0.09 m 框 ∧ 落定（z 容差 25 mm / 速度 <0.05 m/s / "
           "夹爪 >0.05 m / 末端离 can >5 cm 四条一字不动）∧ 保持 10 步，**不要求立着**；"
           "侧躺/侧挡算送到，另打 `delivered_tipped` 标记。" % label,
           "  出处：用户 2026-10-02 授权 → `code/mg_env_reverse.py:reverse_settled()`，"
           "语义由 `code/mg_criterion_selftest.py`（66066 项）钉住「严格 == 历史实现」与「严格 ⊆ 放宽」。"]
    if nr:
        out.append("  放宽 **%s**（门 ≥%.0f%% ⇒ %s）；严格 %s（历史口径，不追改）；侧躺标记 %d 局"
                   % (fmt(kr, nr), 100 * GATE,
                      "✅ 过门" if kr / nr >= GATE else "❌ 未过门", fmt(ks, ns), tip))
        cf = RUNS / CEIL_RELAX / "ceiling_summary.json"
        if cf.is_file():
            try:
                c = json.loads(cf.read_text())
                cs, cr, cn = int(c["n_success"]), int(c["n_success_relaxed"]), int(c["episodes"])
                out.append("  同口径上界（出处 `runs/%s/ceiling_summary.json`）：严格 %d/%d = %.0f%%、"
                           "放宽 %d/%d = %.0f%% ⇒ 占上界 严格 %.1f%% / 放宽 %.1f%%"
                           % (CEIL_RELAX, cs, cn, 100 * cs / cn, cr, cn, 100 * cr / cn,
                              100 * (ks / ns) / (cs / cn) if cs else float("nan"),
                              100 * (kr / nr) / (cr / cn) if cr else float("nan")))
                out.append("  ⚠️ 上界从 %.0f%% 抬到 %.0f%%（6 局专家侧躺失败 min_dist ≤0.52 cm，早在框内）"
                           "⇒「占上界百分比」可能**变差**而绝对成功率变好；门看绝对值，归一化只作并列。"
                           % (100 * cs / cn, 100 * cr / cn))
            except Exception as exc:
                out.append("  ⚠️ 上界产物读不动（%s）⇒ 占上界百分比悬空" % exc)
        else:
            out.append("  ⚠️ 缺放宽口径上界 `runs/%s/` ⇒ 占上界百分比悬空（档 2f 阶段 A 未跑完）" % CEIL_RELAX)
    else:
        out.append("  **悬空**：没有带放宽字段的产物（缺 %d 读）⇒ 不下结论" % len(missing + nofield))
    if missing:
        out.append("  ⚠️ 缺产物 %d 读：%s（不计入，**不当 0**）" % (len(missing), ", ".join(missing)))
    if nofield:
        out.append("  ⚠️ 无放宽字段 %d 读（改判据前跑的）：%s ⇒ 已剔除，**不当 0**"
                   % (len(nofield), ", ".join(nofield)))
    out.append("  ⚠️ 本节**不改** P1/P2/P3：预注册门是按严格口径写的，事后换门 = p-hacking。"
               "放宽口径的正式判定（含档 2c / 档 2 联合的同口径复判、按 seed 拆分、显著性重算）"
               "见 `runs/S2F_RELAX_VERDICT.md`（档 2f）。")
    return out


def stats_drift(old: str = OLD_STATS, new: str = NEW_STATS) -> list[str]:
    """量 normalizer 漂移（GD，只报告）。用 std 归一，报最差通道。"""
    po, pn = DATA / old / "meta" / "stats.json", DATA / new / "meta" / "stats.json"
    if not (po.is_file() and pn.is_file()):
        miss = [str(x) for x in (po, pn) if not x.is_file()]
        return ["GD normalizer 漂移：**悬空** —— 缺 %s（%s）"
                % ("、".join(miss), "还没收数据" if NEW_STATS in "".join(miss) else "路径不对")]
    a, b = json.loads(po.read_text()), json.loads(pn.read_text())
    lines = ["GD normalizer 漂移（出处 %s vs %s）：" % (po, pn)]
    worst = (0.0, "")
    for key in ("observation.state", "action"):
        if key not in a or key not in b:
            lines.append("  %s：缺键 ⇒ 悬空" % key); continue
        rows = []
        for stat in ("mean", "std", "q01", "q99"):
            va, vb = a[key].get(stat), b[key].get(stat)
            if not va or not vb:
                continue
            sd = [abs(x - y) / (abs(s) + 1e-8) for x, y, s in zip(vb, va, a[key]["std"])]
            i = max(range(len(sd)), key=lambda k: sd[k])
            rows.append("%s 最大 |Δ|/std = %.3f（通道 %d）" % (stat, sd[i], i))
            if stat in ("mean", "std") and sd[i] > worst[0]:
                worst = (sd[i], "%s.%s[ch%d]" % (key, stat, i))
        lines.append("  %s：%s" % (key, "；".join(rows)))
    lines.append("  ⇒ 最坏（mean/std）归一漂移 **%.3f σ** @ %s。%s"
                 % (worst[0], worst[1] or "n/a",
                    "< 0.1 σ：归一化基本没动，跨档比较可信。" if worst[0] < 0.1 else
                    "≥ 0.1 σ：归一化确实变了，跨档绝对数值比较要打折，严格归因需 1:1 对照臂。"))
    return lines


def main() -> int:
    print("# 档 2e 判定：反向数据翻倍 + 2:1 配比")
    print("# 产物根目录：%s" % RUNS)
    print("# 规则写死时间 2026-10-01 23:45（mix60f120r 尚未收完、档 2e 尚未开训）")
    print()
    p2e, n2e, r2e = pool(S2E_LAST)
    pjb, njb, rjb = pool(JOINT_LAST)
    ps2c, ns2c, rs2c = pool(S2C_LAST)
    print("## 一、读数")
    print()
    print("| 组 | 口径 | 逐次读数 | 合并 |")
    print("| --- | --- | --- | --- |")
    print("| **档 2e 2:1 @last** | 反向 TEST 7000..7019 K=10 | %s | **%s** |"
          % (" ".join(r2e), fmt(p2e, n2e)))
    print("| 档 2 联合 1:1 @last | 同上 | %s | **%s** |" % (" ".join(rjb), fmt(pjb, njb)))
    print("| 档 2c 反向单任务 @last | 同上 | %s | **%s** |" % (" ".join(rs2c), fmt(ps2c, ns2c)))
    pvs, nvs, rvs = pool(S2E_VALSEL)
    print("| 档 2e @**val选点**（并列读数，**不是门**） | 同上 | %s | %s |"
          % (" ".join(rvs), fmt(pvs, nvs)))
    print()
    print("* 门：反向未见 ≥ **%.0f%%**（与档 2 门 2 / 档 2c 同一个门）" % (GATE * 100))
    print("* **门只认 @last 那一行。** val 选点行是并列读数：坑 27 实测 val 选不出点"
          "（val 5/10=50% 的检查点 TEST 只有 26.7%，与 `last` 反序），所以它只用来回答"
          "「`last` 是不是落在下降尾巴上」，**不参与 P1/P2/P3**。")
    if nvs:
        print("* 若 @val选点 明显高于 @last，说明本档**训过头**了（档 2 的反向 val 在 2.89 ep 见顶、"
              "3.42 ep 崩到 0%，而 `last` 在 3.79 ep）⇒ 下一步是**减 epoch**，不是继续加数据。")
    print()
    print("## 二、护栏")
    print()
    pf, nf, rf = pool(S2E_FWD)
    if nf == 0:
        ga, ga_txt = "missing", "正向 TEST 读数还没落盘"
    elif pf / nf >= FWD_GATE:
        ga, ga_txt = "ok", "正向 TEST %s ≥ %.0f%%" % (fmt(pf, nf), FWD_GATE * 100)
    else:
        ga, ga_txt = "bad", "正向 TEST %s < %.0f%%（2:1 把正向挤掉了）" % (fmt(pf, nf), FWD_GATE * 100)
    pc, nc, rc = pool(S2E_CTRL)
    if nc == 0 or n2e == 0:
        gb, gb_txt = "missing", "反向训练 seed 对照还没落盘"
    else:
        pv = fisher_two_sided(pc, nc, p2e, n2e)
        dpp = (pc / nc - p2e / n2e) * 100
        if pv < 0.05 and dpp > MEMO_MIN_PP:
            gb, gb_txt = "bad", "训练 seed %s 比 TEST %s 高 %.1f pp（Fisher p=%.4g）⇒ 记忆嫌疑" % (
                fmt(pc, nc), fmt(p2e, n2e), dpp, pv)
        else:
            gb, gb_txt = "ok", "训练 seed %s vs TEST %s（差 %.1f pp，Fisher p=%.4g）⇒ 无碾压式记忆的证据" % (
                fmt(pc, nc), fmt(p2e, n2e), dpp, pv)
    mark = RUNS / DATA_MARK
    gc = "ok" if mark.is_file() else "missing"
    gc_txt = ("数据三道闸已过（%s）" % mark.read_text().strip()) if gc == "ok" else "数据标记还没落盘"
    for tag, txt in (("GA", ga_txt), ("GB", gb_txt), ("GC", gc_txt)):
        print("* %s %s" % (tag, txt))
    print()
    for line in stats_drift():
        print("* %s" % line)
    print()
    print("## 三、判定（预注册规则见本文件头注释）")
    print()
    for line in decide(p2e, n2e, pjb, njb, ga, gb, gc):
        print("* %s" % line)
    print()
    print("## 四、并列：放宽口径（**不参与**上面的 P1/P2/P3）")
    print()
    for line in relaxed_block(S2E_LAST, "档 2e 主读数，TEST 反向 7000..7019，K=10，4×20"):
        print("* %s" % line)
    return 0


# ── selftest ──────────────────────────────────────────────────────────────────
def _mk(root: Path, name: str, ns: int, ne: int):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "eval_summary.json").write_text(json.dumps(
        {"n_success": ns, "episodes": ne, "pc_success": ns / ne if ne else 0.0}))


def selftest() -> int:
    n_case = fails = 0

    def chk(name, cond, detail=""):
        nonlocal n_case, fails
        n_case += 1
        if cond:
            print("  ok   %s" % name)
        else:
            fails += 1
            print("  FAIL %s %s" % (name, detail))

    # 判定规则（纯函数，不需要产物）
    d = decide(45, 80, 30, 80, "ok", "ok", "ok")
    chk("P3：56% ≥ 门? 不，45/80=56% 应当 PASS", "P1 PASS" in d[0], str(d))
    d = decide(40, 80, 30, 80, "ok", "ok", "ok")
    chk("40/80=50% 恰好过门（≥ 而非 >）", "P1 PASS" in d[0], str(d))
    d = decide(39, 80, 30, 80, "ok", "ok", "ok")
    chk("39/80=48.8% < 门", "P1 PASS" not in d[0], str(d))
    # 大幅高于基线 => P2（数据是杠杆）
    d = decide(39, 80, 12, 80, "ok", "ok", "ok")
    chk("48.8% vs 15% 基线显著 ⇒ P2", "P2 FAIL" in d[0], str(d))
    # 与基线打平 => P3
    d = decide(30, 80, 30, 80, "ok", "ok", "ok")
    chk("37.5% vs 37.5% 不显著 ⇒ P3", "P3 FAIL" in d[0], str(d))
    chk("P3 的处方是「停止加数据、转修 A 类」", any("停止往" in x for x in d), str(d))
    chk("P2 的处方是「继续加数据」", any("继续加反向数据" in x for x in decide(39, 80, 12, 80, "ok", "ok", "ok")))
    # 三态：missing => 悬空不作废；bad => 作废
    d = decide(45, 80, 30, 80, "missing", "ok", "ok")
    chk("护栏 missing ⇒ 悬空、且明确写「不作废」",
        any("悬空" in x and "不作废" in x for x in d) and "作废" not in "".join(
            x for x in d if "不作废" not in x), str(d))
    d = decide(45, 80, 30, 80, "ok", "bad", "ok")
    chk("护栏 bad ⇒ 结论作废", any("作废" in x and "悬空" not in x for x in d), str(d))
    chk("主读数缺失 ⇒ 无法判定而不是 FAIL", "无法判定" in decide(0, 0, 30, 80, "ok", "ok", "ok")[0])
    chk("基线缺失时不误报显著（pv=nan 走 P3）",
        "P3 FAIL" in decide(20, 80, 0, 0, "ok", "ok", "ok")[0])
    # 禁用词回归：护栏 missing 时**绝不能**给出「结论作废」（那会把待补读数误判成白跑）。
    # 注意 pending 行里本来就有"不作废"三个字，所以不能用子串"作废"去查，要查作废标记 🚫。
    _dm = decide(45, 80, 30, 80, "missing", "missing", "missing")
    chk("护栏全 missing 时不得出现作废标记", not any("🚫" in x for x in _dm), str(_dm))
    chk("护栏全 missing 时必须显式写「不作废」", any("不作废" in x for x in _dm), str(_dm))
    chk("护栏 bad 时必须出现作废标记", any("🚫" in x for x in decide(45, 80, 30, 80, "bad", "ok", "ok")))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for nm, ns, ne in [(S2E_LAST[0], 6, 20), (S2E_LAST[1], 7, 20),
                           (JOINT_LAST[0], 6, 20), (JOINT_LAST[1], 7, 20)]:
            _mk(root, nm, ns, ne)
        import mg_verdict_s2e as M
        import mg_verdict_s2c as C
        # ⚠️ pool/one/fmt 是从 mg_verdict_s2c **import 进来的函数对象**，它们闭包读的是
        #    mg_verdict_s2c 自己的模块级 RUNS。只改 M.RUNS 不生效（第一版就是这么假失败的）。
        old_runs, old_c = M.RUNS, C.RUNS
        M.RUNS = root
        C.RUNS = root
        try:
            ns_, ne_, reads = M.pool(M.S2E_LAST)
            chk("pool 合并两读并标 MISSING", ns_ == 13 and ne_ == 40
                and reads[2] == "#3:MISSING", str(reads))
            chk("fmt 输出 13/40 = 32.5%", M.fmt(13, 40) == "13/40 = 32.5%", M.fmt(13, 40))
        finally:
            M.RUNS, C.RUNS = old_runs, old_c

        # GD 漂移：造两份 stats.json
        for tag, mean_shift in (("mix60f60r", 0.0), ("mix60f120r", 0.002)):
            dd = root / "data" / tag / "meta"
            dd.mkdir(parents=True, exist_ok=True)
            st = {"observation.state": {"mean": [0.13 + mean_shift, 0.07, 0.95, 0.99],
                                        "std": [0.0589, 0.272, 0.0369, 0.0136],
                                        "q01": [0, 0, 0, 0], "q99": [1, 1, 1, 1]},
                  "action": {"mean": [0.076, 0.057, 0.005, 0.0],
                             "std": [0.2503, 0.4534, 0.2591, 1.0],
                             "q01": [0, 0, 0, 0], "q99": [1, 1, 1, 1]}}
            (dd / "stats.json").write_text(json.dumps(st))
        old_data = M.DATA
        M.DATA = root / "data"
        try:
            lines = M.stats_drift()
            chk("GD 报告含两个 key", any("observation.state" in x for x in lines)
                and any("action" in x for x in lines), str(lines))
            chk("GD 小漂移判为「基本没动」", any("基本没动" in x for x in lines), str(lines))
            # 大漂移
            p = M.DATA / "mix60f120r" / "meta" / "stats.json"
            j = json.loads(p.read_text())
            j["observation.state"]["mean"][0] += 0.0589   # 正好 1 σ
            p.write_text(json.dumps(j))
            lines2 = M.stats_drift()
            chk("GD 1σ 漂移判为「确实变了」", any("确实变了" in x for x in lines2), str(lines2))
            chk("GD 缺 stats.json ⇒ 悬空而不是崩",
                any("悬空" in x for x in M.stats_drift("nope1", "nope2")))
        finally:
            M.DATA = old_data

    # Fisher 语义钉死（独立枚举超几何），防止再传成"失败数"
    from math import comb

    def fisher_ref(a, n1, b, n2):
        tot = a + b
        lo, hi = max(0, tot - n2), min(n1, tot)
        w = {x: comb(n1, x) * comb(n2, tot - x) for x in range(lo, hi + 1)}
        den = sum(w.values())
        po = w[a] / den
        return min(1.0, sum(v / den for v in w.values() if v / den <= po + 1e-12))

    for (a, n1, b, n2) in [(39, 80, 12, 80), (30, 80, 30, 80), (40, 80, 30, 80),
                           (28, 40, 12, 40)]:
        chk("fisher 语义钉死 (%d/%d vs %d/%d)" % (a, n1, b, n2),
            abs(fisher_two_sided(a, n1, b, n2) - fisher_ref(a, n1, b, n2)) < 1e-12)
    chk("48.8%% vs 15%% (n=80) 显著", fisher_two_sided(39, 80, 12, 80) < 1e-4)
    chk("48.8%% vs 37.5%% (n=80) 不显著", fisher_two_sided(39, 80, 30, 80) > 0.05)

    # 报告文本的回归：不许把 %% 直接印出来（无 % 运算的字符串里写 %% 就会漏）
    # ⚠️ 必须**在空目录上**跑（2026-10-02 修）：原来直接调 M.main() 读真 RUNS/DATA，
    # 写这个自测时 data/mix60f120r 还没收、s2e 读数也不存在，所以「无法判定 / GD 悬空」成立；
    # 01:25 数据落盘后同一份自测就假失败了（29/31）。自测必须自洽，不能依赖当天跑到哪一步。
    import io, contextlib
    import mg_verdict_s2c as S2C
    with tempfile.TemporaryDirectory() as td_empty:
        # 两处都要换：本模块的 RUNS/DATA，**以及** mg_verdict_s2c.RUNS ——
        # one()/pool() 是从 s2c import 进来的，它们查的是 s2c 自己的模块级 RUNS，
        # 只换 M.RUNS 的话主读数照样去读真产物（2026-10-02 实测：换了等于没换）。
        old = (M.RUNS, M.DATA, S2C.RUNS)
        M.RUNS = M.DATA = S2C.RUNS = Path(td_empty)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                M.main()
            rep = buf.getvalue()
        finally:
            M.RUNS, M.DATA, S2C.RUNS = old
    chk("报告里不得出现裸的 %%%%", "%%" not in rep, [x for x in rep.splitlines() if "%%" in x][:1])
    chk("报告必须写明「门只认 @last」", "门只认 @last" in rep)
    chk("报告必须含 val 选点并列行", "val选点" in rep and "不是门" in rep)
    # 注意别用子串「作废」去查：pending 那行本来就写着「（不是作废…）」，
    # 第一版就是这么假失败的。作废的唯一标记是 🚫（护栏 bad 时才出现）。
    chk("主读数缺失时报「无法判定」，且不出现作废标记",
        "无法判定" in rep and "🚫" not in rep and "P1 PASS" not in rep, rep[-200:])
    chk("GD 悬空时说明缺哪个文件", "GD normalizer 漂移：**悬空**" in rep, rep[-400:])

    # ── 放宽口径并列块（档 2f 口径）：缺字段≠0 / 门判对 / 上界同口径 / 免责声明必须在 ──
    with tempfile.TemporaryDirectory() as td_r:
        rr = Path(td_r)
        old_r = M.RUNS
        M.RUNS = rr

        def _mkf(name, ne, ns, nr=None, tip=0, ceiling=False):
            d = rr / name
            d.mkdir(parents=True, exist_ok=True)
            j = {"episodes": ne, "n_success": ns, "pc_success": ns / ne}
            if nr is not None:
                j.update({"n_success_relaxed": nr, "pc_success_relaxed": nr / ne,
                          "n_delivered_tipped": tip, "n_ever_in_target_box": nr})
            fn2 = "ceiling_summary.json" if ceiling else "eval_summary.json"
            (d / fn2).write_text(json.dumps(j))

        try:
            lines = M.relaxed_block(["nope1", "nope2"], "x")
            chk("放宽块 全缺产物 ⇒ 悬空", any("悬空" in x for x in lines), str(lines))
            chk("放宽块 缺产物必须写「不当 0」", any("不当 0" in x for x in lines), str(lines))
            _mkf("old_read", 20, 9)                       # 改判据前跑的：没有放宽字段
            lines = M.relaxed_block(["old_read"], "x")
            chk("放宽块 无字段 ⇒ 悬空而不是 0/20", any("悬空" in x for x in lines), str(lines))
            chk("放宽块 无字段要显式列出来", any("无放宽字段" in x for x in lines), str(lines))
            _mkf("r1", 20, 8, 12, 4)
            _mkf("r2", 20, 8, 11, 3)
            lines = M.relaxed_block(["r1", "r2", "old_read"], "x")
            chk("放宽块 合并 23/40（无字段那读要剔除）", any("23/40" in x for x in lines), str(lines))
            chk("放宽块 严格列只算同一批读 = 16/40", any("16/40" in x for x in lines), str(lines))
            chk("放宽块 23/40=57.5% ≥ 门 ⇒ 过门", any("✅ 过门" in x for x in lines), str(lines))
            chk("放宽块 侧躺标记合计 7 局", any("侧躺标记 7 局" in x for x in lines), str(lines))
            chk("放宽块 必须有免责声明（不改 P1/P2/P3）",
                any(("不改" in x and "P1/P2/P3" in x) for x in lines), str(lines))
            chk("放宽块 必须指向档 2f 判定", any("S2F_RELAX_VERDICT.md" in x for x in lines), str(lines))
            _mkf(M.CEIL_RELAX, 20, 14, 20, 6, ceiling=True)
            lines = M.relaxed_block(["r1", "r2"], "x")
            chk("放宽块 上界同口径 严格 70% / 放宽 100%",
                any(("严格 14/20 = 70%" in x and "放宽 20/20 = 100%" in x) for x in lines), str(lines))
            chk("放宽块 占上界两口径分别算",
                any(("占上界 严格" in x and "放宽 57.5%" in x) for x in lines), str(lines))
            chk("放宽块 不许印裸的 %%%%（有上界fixture 时才走到的那一行）",
                not any("%%" in x for x in lines), [x for x in lines if "%%" in x][:1])
            chk("放宽块 上界抬升要写实际数字 70% -> 100%",
                any(("从 70% 抬到 100%" in x) for x in lines), str(lines))
            _mkf("low", 20, 5, 9, 4)
            lines = M.relaxed_block(["low"], "x")
            chk("放宽块 9/20=45% < 门 ⇒ 未过门", any("❌ 未过门" in x for x in lines), str(lines))
        finally:
            M.RUNS = old_r
    chk("主报告里有放宽口径并列节", "并列：放宽口径" in rep, rep[-300:])

    print("\nselftest: %d/%d 通过" % (n_case - fails, n_case))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
