#!/usr/bin/env python3
"""B 线：门禁 v1.3 断言的**变异自检**（证明 §7 回归表真的有牙）。

为什么需要它：`b_selfcheck_gate_regression.py` 报 85/85 通过，只能说明「门禁与断言一致」，
不能说明「断言能抓住门禁退化」。把裁定 1/2/3 与 §12 指纹的实现逐个改坏，对应用例必须
**变红**；如果改坏了还全绿，说明那条断言是装饰性的。

做法：不改盘上门禁源码（改完还要还原，风险高），而是在内存里替换 gate 模块的函数，
再对同一批夹具重跑断言。每个变异体记录「哪几条断言由绿转红」。

用法：python scripts/b_selfcheck_gate_mutation.py [--json-out ...]
"""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "b_gate_controlled_success.py"
REGRESSION = ROOT / "scripts" / "b_selfcheck_gate_regression.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Args:
    def __init__(self, rise_cap, final_rise, assist_off=False):
        self.rise_cap, self.final_rise, self.assist_off = rise_cap, final_rise, assist_off


# 每个变异体：名字 -> (要打补丁的属性, 替换函数, 应当变红的用例 id 集合, 这个变异在模拟什么退化)
def mutations(gate):
    return {
        "M1_裁定1_词表矛盾不再拦": (
            "phase_vocab_status",
            lambda row, kind, end_phase: ("consistent", ""),
            {9, 10},
            "把裁定 1 关掉：phase_at_end 与 phase_trace 矛盾时也当一致处理"
            "（退回 v1.2.1 的静默 per-frame 兜底 -> 假 flick）"),
        "M2_裁定2_声明无条件放行": (
            "not_applicable_check",
            lambda d, rows, n_with, learned: {"declared": True, "status": "verified_in_range",
                                              "note": "mutant", "reason": None, "obs_space": None,
                                              "train_time_obs_absmax": None,
                                              "closed_loop_obs_absmax": None,
                                              "rows_with_raw_obs_absmax": 0,
                                              "limit_with_tol": None, "rows_out_of_range": None,
                                              "oob_frac": None, "tol": 0.05},
            {14, 15, 16},
            "把裁定 2 的牙拔掉：只要声明了 not_applicable 就放行，不查 reason / 训练期区间 / 闭环区间"),
        "M3_§12_缺指纹不再拒判": (
            "blown_impl_check",
            lambda path, d, n_with: {"impl": None, "source": None, "blowup_threshold": None,
                                     "gate_tolerance": None, "known_impls": list(gate.KNOWN_BLOWN_IMPLS),
                                     "grandfather_registry": gate.GRANDFATHER_DOC,
                                     "artifact_sha256": None, "status": "known", "reject": False,
                                     "note": "mutant"},
            {18},
            "把 §12 分派关掉：缺 blown_metric_impl 指纹也当已知实现放行"),
        "M4_裁定3_带外也受理豁免": (
            "probe_exoneration_check",
            lambda path, mean_blown, impl_status=None, artifact=None: {
                "registry": gate.EXONERATION_DOC, "registry_error": None, "key": "mutant",
                "scope": "arm", "probe_kind": "mutant", "ruling_ref": "mutant",
                "evidence_artifact": None, "evidence_sha256": None,
                "disputed_band": list(gate.DISPUTED_BLOWN_BAND),
                "mean_blown_frames_frac": mean_blown, "status": "exonerated", "note": "mutant"},
            {20},
            "把裁定 3 的带外护栏拆掉：mean_blown=0.5 也发豁免（豁免册变成翻案万能钥匙）"),
        "M5_B3_诊断恒报零": (
            "insuff_diagnostic",
            lambda judged, thr: {"n": 0, "note": "mutant"},
            {21},
            "把 B-3 的「差多少」诊断关掉：insufficient_lift 只剩计数"),
        # ---- v1.4 裁定 14（DR-D09）：两个方向都必须有牙 ----
        "M6_裁定14_弃权被关掉": (
            "LABEL_CRITICAL_FIELDS",
            (),
            {22},
            "把裁定 14 静默移除（关键字段集合清空 -> labels_reportable 恒 True）："
            "证据不足时又会一路返回最重的失效模式 flick。退回 v1.3 的 16 局假 flick"),
        "M7_裁定14_按DR-D09字面实现": (
            "LABEL_CRITICAL_FIELDS",
            ("final_rise", "held_at_end", "phase_at_end", "terminal_kind"),
            {1, 24},
            "**反方向**：把 terminal_kind 也算进标签关键字段（= DR-D09 的字面口径 "
            "`field_class != strict` 即弃权）。后果是 base-only 标定件（只缺 terminal_kind）"
            "被判 measurement_valid=False -> 门禁作废自己的 rise_cap=0.15 锚点。"
            "这条变异体存在，就是为了把 DR-007 的收窄理由变成可执行的证据，"
            "而不是只写在注释里；哪天有人想「按裁定原文改回来」，本条会立刻红给他看"),
        # ---- v1.5 裁定 10 通道（DR-008）：每颗牙单独一个变异体 ----
        "M8_DR008_分通道被撤掉": (
            "BAND_EXEMPT_PROBE_KINDS",
            (),
            {25},
            "把 DR-008 决定 1 静默撤销（白名单清空 -> 所有 kind 都要过争议带）。后果：裁定 16.4 "
            "要求登记的带外臂（blown=0.212）重新永远无法受理，48 臂权威表的三分类退回 24/22/2，"
            "与增补五 §3 的 25/22/1 冲突 —— 也就是 A 的移交单白做一遍"),
        "M9_DR008_晋级闸被放宽": (
            "EXONERATION_PROMOTION_SOURCES",
            {gate.PROBE_KIND_REBLOWN: ("verified_ok", "not_applicable_verified", "violated"),
             gate.PROBE_KIND_CLIP_AT_TRAIN_ABSMAX: ("violated",)},
            {39},
            "**反方向**：把带内重测通道也允许从 violated 晋级（= 有人图省事写成「exonerated 即晋级」）。"
            "后果：一次「换把尺子重测」就能推翻一个**真的**超阈（0.06 > 0.05），裁定 12 被架空。"
            "DR-008 决定 5 的分路必须精确到 kind，本条把这个理由钉成可执行证据"),
        "M10_DR008_C不必等于train_absmax": (
            "CLIP_C_TOL",
            1e9,
            {27},
            "把 裁定 10 条件 ① 的容差放到无穷大（= 不再核对登记的 C 与产物自报的训练期 absmax）。"
            "后果：册子里写任意一个 C 都能免罪。A 的判别力反证已实测 C=5.0 时 seed 5007 的 verdict "
            "翻转、insufficient_lift 1→0，即「截得越紧越安全」是假的"),
        "M11_DR008_会签不再核验": (
            "_clip_channel_precheck",
            lambda hit, path, _o=gate._clip_channel_precheck: _o(
                dict(hit, cosign={"by": "D", "fact_basis": True}), path),
            {29, 30},
            "把 裁定 16.4「B 写、D 会签」的核验关掉（代码不再真读 cosign 字段）。后果：B 可以自签免罪。"
            "注意 fact_basis 写成字符串 \"yes\" 也必须被拒 —— 真值判断是 `is True`，不是 truthiness"),
        "M12_DR008_五条准入不再核验": (
            "_clip_channel_precheck",
            lambda hit, path, _o=gate._clip_channel_precheck: _o(
                dict(hit, ruling10_conditions={k: True for k in gate.RULING10_CONDITION_KEYS}), path),
            {31, 32},
            "把「五条准入逐条核对」的结构化要求关掉。后果：条目可以只写一句 reason 就免罪，"
            "漏项（少登记一条）会被读成通过"),
        "M13_DR008_臂级也受理": (
            "_clip_channel_precheck",
            lambda hit, path, _o=gate._clip_channel_precheck: _o(dict(hit, scope="artifact"), path),
            {26},
            "把 DR-008 决定 2 的 scope 牙拔掉（裁定 10 通道也受理 scope=arm）。后果：豁免随臂迁移 —— "
            "同臂重新评测后不必重做探针就被免罪，而 artifact scope 本来是「重跑即失效」的"),
        "M14_DR008_探针自报截断值不再核验": (
            "_clip_evidence_check",
            lambda hit, clip_c, evidence_path: (None, ""),
            {33, 34},
            "把证据侧那条**独立**核验关掉：只看册子登记了什么，不看探针产物自己记录了什么。"
            "后果：登记 C=12.469445 而证据其实是 C=5.0 的探针（或根本没截断）也能过"),
        "M15_DR008_假证据不再判invalid": (
            "EXONERATION_EVIDENCE_FAILURES",
            ("evidence_missing", "evidence_sha_mismatch"),
            {33, 34},
            "保留核验、但**不接线**到后果：probe_clip_* 命中后 ic_status 维持原判而不是 "
            "probe_exoneration_invalid。后果：登记了不支持自己的假证据，读起来却像「只是没豁免」"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_gate_regression/mutation.json"))
    a = ap.parse_args()

    gate0 = _load(GATE, "b_gate_ref")
    reg = _load(REGRESSION, "b_gate_regression_ref")
    synth = reg.make_fixtures(gate0)
    cases = []
    for c in reg.CASES:
        cc = dict(c)
        if cc.get("fixture_from"):
            cc["fixture"] = synth[cc["fixture_from"]]
        if cc.get("exoneration_registry_from"):
            cc["exoneration_registry"] = synth[cc["exoneration_registry_from"]]
        cases.append(cc)
    args = Args(gate0.RISE_CAP, gate0.FINAL_RISE_MIN)

    def judge(gate, case):
        """按用例临时替换候选豁免册（v1.5 / DR-008 的用例需要），跑完还原。"""
        saved = gate.EXONERATION_DOC
        if case.get("exoneration_registry"):
            gate.EXONERATION_DOC = case["exoneration_registry"]
        try:
            return gate.judge_file(str(ROOT / case["fixture"]), args)
        finally:
            gate.EXONERATION_DOC = saved

    # 基线：未变异时必须全绿（否则「变红」没有参照）
    base = {}
    for c in cases:
        row = judge(gate0, c)
        base[c["id"]] = all(reg.eval_assert(row, s)["ok"] for s in c["asserts"])
    n_base_ok = sum(1 for v in base.values() if v)
    print("=" * 96)
    print("门禁 %s 变异自检（gate_build=%s，%d 个用例）"
          % (gate0.GATE_VERSION, gate0.GATE_BUILD, len(cases)))
    print("基线：未变异时 %d/%d 个用例全绿%s"
          % (n_base_ok, len(cases), "" if n_base_ok == len(cases) else "  ✗ 基线不干净，变异结论不可信"))
    print("=" * 96)

    results, all_ok = [], (n_base_ok == len(cases))
    for name, (attr, mutant, target_ids, simulates) in mutations(gate0).items():
        gate = _load(GATE, "b_gate_" + name)
        setattr(gate, attr, mutant)
        turned = []
        for c in cases:
            if c["id"] not in target_ids:
                continue
            row = judge(gate, c)
            oks = [reg.eval_assert(row, s) for s in c["asserts"]]
            red = [o["note"] for o in oks if not o["ok"]]
            if red:
                turned.append((c["id"], red))
        caught = sorted(i for i, _ in turned) == sorted(target_ids)
        all_ok &= caught
        results.append({"mutation": name, "attr": attr, "simulates": simulates,
                        "target_cases": sorted(target_ids), "turned_red": caught and sorted(i for i, _ in turned) or [],
                        "expected_red": sorted(target_ids), "caught": caught})
        print("\n[%s] %s" % ("CAUGHT " if caught else "MISSED", name))
        print("    模拟退化：%s" % simulates)
        print("    应变红：%s   实际变红：%s" % (sorted(target_ids), sorted(i for i, _ in turned)))
        for cid, red in turned:
            for r in red[:3]:
                print("      #%-3d ✗ %s" % (cid, r))
        if not caught:
            print("    ✗ 断言没有牙：改坏实现后对应用例仍然全绿")

    print("\n" + "=" * 96)
    print("结论：%d/%d 个变异体被抓住%s"
          % (sum(1 for r in results if r["caught"]), len(results),
             "" if all_ok else " -> FAIL：存在装饰性断言"))
    print("=" * 96)
    outp = Path(a.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({
        "gate_build": gate0.GATE_BUILD, "gate_version": gate0.GATE_VERSION,
        "gate_spec_sha256": gate0.GATE_SPEC_SHA, "n_cases": len(cases),
        "baseline_all_green": bool(n_base_ok == len(cases)),
        "n_mutations": len(results), "n_caught": sum(1 for r in results if r["caught"]),
        "all_ok": bool(all_ok), "mutations": results,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("写出:", outp)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
