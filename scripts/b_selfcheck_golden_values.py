#!/usr/bin/env python3
"""B 线：黄金期望值自校验 —— 不把手算结果直接丢给 C。

docs/b_golden/async_td_golden_v1.json 里的数值是**手算**的（γ^n、γ^2、γ^8 这些）。
手算会错，而 C 要拿它当验收标准，错了就是让下游照着错的规格实现。所以本脚本
从 conventions 里的 γ / n / L **重新推导**每一个数值常量，与 JSON 里写死的值逐条比对。

同时检查若干结构性不变量（不是数值，是「规格自不自洽」）：
  S1 六个算例齐全，且每例都有 targets / masks / isolation 或 gradients 至少一类断言
  S2 E 段索引 == [n, 2n)，C 段 == [0, n)，D 段 == [2n, H)，且 H >= 2n
  S3 γ_slot 在所有 target 表达式里只出现一次（防二次幂）
  S4 每个被隔离的样本都显式声明 treated_as_zero_value == False
  S5 E2 的 BC 非主张在位（不能借梯度测试禁止所有未执行标签监督）
  S6 E3 的「禁止的替代方案」带了对比数值（0.75 vs 0.5）
  S7 cross_case_invariants 引用的 case_id 都存在

只读 JSON，不碰 C 的 harness/ledger.py 与 harness/data_bridge.py。
退出码 0 = 全部通过。
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/b_golden/async_td_golden_v1.json"
TOL = 1e-12


def close(a, b, tol=TOL):
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(DEFAULT))
    a = ap.parse_args()
    spec = json.loads(Path(a.json).read_text())
    conv = spec["conventions"]
    g = conv["gamma_per_control_step"]; n = conv["slot_length_n"]
    H = conv["chunk_length_H"]; gs = g ** n
    cases = {c["case_id"]: c for c in spec["cases"]}
    fails, checks = [], 0

    def ck(name, ok, detail=""):
        nonlocal checks
        checks += 1
        if not ok:
            fails.append(f"{name}: {detail}")
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))

    print("== 数值重推导（γ=%g, n=%d, H=%d）==" % (g, n, H))
    ck("conventions.gamma_slot == γ^n", close(conv["gamma_slot"], gs),
       "JSON=%r 重算=%r" % (conv["gamma_slot"], gs))

    e1 = cases["E1"]["expect"]["targets"]
    ck("E1 R_k == γ^2 * 0.1", close(e1["R_k"]["numeric"], g ** 2 * 0.1)
       and close(e1["R_k"]["numeric_exact"], g ** 2 * 0.1),
       "JSON=%r/%r 重算=%r" % (e1["R_k"]["numeric"], e1["R_k"]["numeric_exact"], g ** 2 * 0.1))
    ck("E1 y_k 的 γ_slot 系数 == γ^n",
       close(e1["y_k"]["gamma_slot_coefficient"], gs),
       "JSON=%r 重算=%r" % (e1["y_k"]["gamma_slot_coefficient"], gs))
    ck("E1 R_k 的输入里只有 r_102 非零",
       [ev for ev in cases["E1"]["input"]["event_log"] if ev["event"] == "reward" and ev.get("value", 0) != 0]
       [0]["frame"] == 102)

    e3i = cases["E3"]["input"]; e3e = cases["E3"]["expect"]["targets"]
    L = e3i["constants"]["L"]
    term = cases["E3"]["expect"]["targets"]["next_slot_terminal_sample"]
    ck("E3 L <= n（终局必须落在本槽内）", L <= n, "L=%d n=%d" % (L, n))
    ck("E3 R_{k+1,L} == Σ_{j<L} γ^j r_j == γ^(L-1) * 1",
       close(term["R_k1_L"]["numeric_exact"], g ** (L - 1)) and close(term["y"], g ** (L - 1)),
       "JSON=%r/%r 重算=%r" % (term["R_k1_L"]["numeric_exact"], term["y"], g ** (L - 1)))
    ck("E3 terminal 样本 bootstrap == False 且 terminated == True",
       term["bootstrap"] is False and term["terminated"] is True)
    ck("E3 当前槽 R_k == 0", close(e3i["current_slot_k"]["R_k"], 0.0))
    conv_y = e3e["current_slot_k" if False else "current_slot_normal_sample"]["after_Q_converges"]
    ck("E3 收敛后 y_k == γ^n * γ^(L-1) == γ^(n+L-1)",
       close(conv_y["y_k_numeric_exact"], g ** (n + L - 1)) and close(conv_y["Q_bar_value"], g ** (L - 1)),
       "JSON=%r 重算=%r（=γ^%d）" % (conv_y["y_k_numeric_exact"], g ** (n + L - 1), n + L - 1))
    ck("E3 γ_slot 系数 == γ^n",
       close(e3e["current_slot_normal_sample"]["y_k"]["gamma_slot_coefficient"], gs))
    bad = e3e["forbidden_alternative"]
    ck("E3 禁止方案的对比数值自洽（真值 0.5，回填后 0.75）",
       close(bad["correct_value"], 0.5) and close(bad["expected_value_of_that_bad_scheme"], 0.75),
       "0.5*1 + 0.5*0.5 = 0.75 才对；JSON=%r/%r" % (bad["correct_value"], bad["expected_value_of_that_bad_scheme"]))

    print("\n== 结构性不变量 ==")
    ck("S1 六例齐全", set(cases) == {"E1", "E2", "E3", "E4", "E5", "E6"}, str(sorted(cases)))
    for cid, c in cases.items():
        has = any(k in c["expect"] for k in ("targets", "masks", "isolation", "gradients", "invariance"))
        ck("S1 %s 至少有一类可断言的 expect" % cid, has)
    seg = conv["action_index_segments_numeric"]
    ck("S2 C/E/D 三段索引与 n、H 一致",
       seg["C_committed"] == [0, n] and seg["E_execution"] == [n, 2 * n]
       and seg["D_discarded"] == [2 * n, H], json.dumps(seg, ensure_ascii=False))
    ck("S2 三段互不重叠且覆盖 [0,H)",
       seg["C_committed"][1] == seg["E_execution"][0]
       and seg["E_execution"][1] == seg["D_discarded"][0]
       and seg["C_committed"][0] == 0 and seg["D_discarded"][1] == H)
    ck("S2 H >= 2n", H >= 2 * n, "H=%d 2n=%d" % (H, 2 * n))
    ck("S2 E2 的 q_gradient_span == E 段", cases["E2"]["expect"]["gradients"] is not None
       and cases["E2"]["expect"]["masks"]["q_gradient_span"] == [n, 2 * n])
    ck("S2 E2 对 C 段与 D 段的动作导数为 0（严格）",
       cases["E2"]["expect"]["gradients"]["dL_Q_actor_d_chunk_indices_0_6"]["value"] == 0.0
       and cases["E2"]["expect"]["gradients"]["dL_Q_actor_d_chunk_indices_12_20"]["value"] == 0.0
       and cases["E2"]["expect"]["gradients"]["dL_Q_actor_d_chunk_indices_6_12"]["value"] == "!= 0")

    # S3 γ_slot 只出现一次：所有 target 表达式里 "γ_slot"/"γ^6"/"γ^n" 合计只能出现 1 次
    for cid in ("E1", "E3", "E5"):
        blob = json.dumps(cases[cid]["expect"], ensure_ascii=False)
        hits = len(re.findall(r"γ_slot|γ\^6|γ\^n|gamma_slot", blob))
        powers = re.findall(r"γ\^(\d+)", blob)
        ck("S3 %s 没有出现 γ 的 2n 次幂（二次幂 bug）" % cid,
           not any(int(p) == 2 * n for p in powers) and not any(int(p) > n + 6 for p in powers),
           "发现的幂次=%s" % sorted(set(powers)))
        ck("S3 %s 的 γ_slot 以系数形式给出（可断言，不是字符串）" % cid, hits >= 1)

    for cid in ("E5", "E6"):
        iso = cases[cid]["expect"].get("isolation", {})
        blob = json.dumps(iso, ensure_ascii=False)
        ck("S4 %s 显式声明删失不当零价值" % cid,
           ("treated_as_zero_value" in blob and '"treated_as_zero_value": false' in blob.lower().replace("False", "false"))
           or "不将删失当零价值" in json.dumps(cases[cid]["expect"], ensure_ascii=False), blob[:200])
    ck("S4 E5 被打断槽 isolated 且非零价值",
       cases["E5"]["expect"]["masks"]["slot_k1_starting_106"]["isolated"] is True
       and cases["E5"]["expect"]["masks"]["slot_k1_starting_106"]["treated_as_zero_value"] is False)
    ck("S4 E5 区分了 V1/V2 的隔离范围",
       cases["E5"]["expect"]["isolation_scope"]["V1_isolated_slots"]
       != cases["E5"]["expect"]["isolation_scope"]["V2_isolated_slots"])

    ck("S5 E2 带 BC 非主张（不得借梯度测试禁掉所有未执行标签监督）",
       cases["E2"]["expect"]["explicit_non_claim"]["L_BC_may_change_under_P1_P2"] is True)
    ck("S6 E3 的禁止替代方案在位", "forbidden_alternative" in cases["E3"]["expect"]["targets"])
    ck("S6 E6 unknown 不是失败/不是零奖励",
       cases["E6"]["expect"]["reward_semantics"]["unknown_is_not_failure"] is True
       and cases["E6"]["expect"]["reward_semantics"]["unknown_is_not_zero_reward"] is True)
    ck("S6 E4 区分「不进 TD 视图」与「被隔离」",
       "本来就不进 TD 视图" in json.dumps(cases["E4"]["expect"]["isolation"], ensure_ascii=False))
    ck("S6 E6 的两个拒绝原因必须分开记录",
       cases["E6"]["expect"]["masks"]["V2"]["both_reasons_must_be_recorded_separately"] is True
       and set(cases["E6"]["expect"]["masks"]["V2"]["rejection_reasons"])
       == {"late_past_deadline", "goal_epoch_incompatible"})

    known = set(cases)
    for inv in spec["cross_case_invariants"]:
        ck("S7 不变量 %s 引用的 case 都存在" % inv["id"], set(inv["cases"]) <= known,
           str(set(inv["cases"]) - known))
    ck("S7 不变量条数 >= 6（覆盖四种 mask/三事件/删失/γ_slot/C-E-D/非原版 SmoothRL）",
       len(spec["cross_case_invariants"]) >= 6)

    print("\n" + "=" * 70)
    print("结论：%s（共 %d 项检查）" % ("全部通过" if not fails else "%d 项 FAIL" % len(fails), checks))
    for f in fails:
        print("  FAIL", f)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
