#!/usr/bin/env python3
"""B 线：跨文件**内容锚**登记册 + 闸（D→B 执行单 §5 / 验收 §8.5）。

0929 A 主动报出 B 的 4 处行号锚移位（`docs/a_handoff_to_b_anchor_shift_20260929.md`），
其中 `b_eval_act_lift_v1.py` 引的 `train_act_lift.py:44` 在 A 动手**之前**就已失效
（HEAD 里那行本来在 `:36`，A 改后移到 `:156`）。D §5 的要求是：
**借这次把可改的三处从「行号锚」改成「内容锚」**，并按规范化文本搜索、**回显命中行号**。

本脚本就是那三处的集中登记与校验，另加两类特殊条目：
  · `frozen`：`b_gate_controlled_success.py:961` 那处锚**不能改** —— 该文件是冻结门禁本体，
    改一个字节（连注释都算）`GATE_BUILD = sha12(自身)` 就变 ⇒ 要 D 跑第三轮复签、A 重出权威表。
    所以这里反过来断言「陈旧锚仍在原处、且构建仍是 `f19f61341cbe`」，把它登记成 **v1.6 待修项**，
    而不是假装它已经修好。
  · `historical`：`docs/b_normalization_incident_20260928.md` 与 `docs/b_handoff_to_a_20260928.md`
    引的 `:36` 是**当时正确**的历史记录 ⇒ 按 A 的建议留档不追改；这里断言它**没被人「好心」改写**
    （改写历史留档会让 0928 事故的时间线不可核）。

**可红条件（裁定 27.1：判据必须写明怎样才能红）**
  1. 目标文件里内容锚命中数 != `expect`（含 `expect=0` 的「必须已删除」断言被违反）⇒ RED；
  2. 目标文件缺失 ⇒ RED（不降级成「锚点还在」）；
  3. 引用方文件里**旧行号锚未清除**，或**内容锚文本不在**（= 修完又被回退）⇒ RED；
  4. `frozen` 条目：冻结文件的 sha12 != `f19f61341cbe`，或陈旧锚已不在原处 ⇒ RED
     （后者意味着有人改了冻结文件却没走 v1.6 + D 复签）；
  5. `historical` 条目：留档里的 `:36` 被改写 ⇒ RED。

**不红条件（反向，防恒红）**：只改条目的 `why` / `id` 这类说明字段 ⇒ 仍 GREEN
（本闸比的是锚点语义，不是登记册整份相等）；`--selftest` 的 M7 专门盯这条。

用法：
    python3 scripts/b_selfcheck_source_anchors.py
    python3 scripts/b_selfcheck_source_anchors.py --selftest
    python3 scripts/b_selfcheck_source_anchors.py --json-out runs/infra/b_source_anchors/report.json
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.b_source_anchor import find_lines, owner_carries, render   # noqa: E402

GATE_REL = "scripts/b_gate_controlled_success.py"
GATE_BUILD_FROZEN = "f19f61341cbe"

# kind: "content"（可改的三处）/ "frozen"（冻结门禁里的陈旧锚，登记为 v1.6 待修）/
#       "historical"（当时正确的历史留档，断言未被改写）
ANCHORS = [
    {"id": "A1_eval_norm_root_cause", "kind": "content",
     "owner": "scripts/b_eval_act_lift_v1.py",
     "target": "scripts/train_act_lift.py",
     "snippet": "std = x.std(0) + 1e-6", "expect": 1,
     "why": "归一化根因：近常量维无下限保护（0928 事故）。旧行号锚 `:44` 在 A 改动前就已失效。",
     "owner_must_contain": ["std = x.std(0) + 1e-6"],
     "owner_must_not_contain": ["train_act_lift.py:44"]},

    {"id": "A2_probe_dz_chunkpolicy_ctor", "kind": "content",
     "owner": "scripts/b_probe_dz_identifiability.py",
     "target": "scripts/train_act_lift.py",
     "snippet": "def __init__(self, obs_dim, chunk=4, *, goals=None)", "expect": 1,
     "why": "B 的本地 ChunkPolicy 副本声称与上游「逐层一致」；上游 0929 加了 keyword-only 的 goals，"
            "缺省路径 goal_dim=0 ⇒ 层结构不变，但**签名锚必须跟着记**，否则下次对照无从核。",
     "owner_must_contain": ["def __init__(self, obs_dim, chunk=4, *, goals=None)"],
     "owner_must_not_contain": ["train_act_lift.py:14 的 ChunkPolicy"]},

    {"id": "A3_probe_dz_first_layer", "kind": "content",
     "owner": "scripts/b_probe_dz_identifiability.py",
     "target": "scripts/train_act_lift.py",
     "snippet": "nn.Linear(self.obs_dim+self.goal_dim,256)", "expect": 1,
     "why": "「逐层一致」的**结构**锚：goal 真进了第一层输入维度（不是只加个参数不用）。",
     "owner_must_contain": ["nn.Linear(self.obs_dim+self.goal_dim,256)"],
     "owner_must_not_contain": []},

    {"id": "A4_t17_audit_goal_epoch", "kind": "content",
     "owner": "scripts/b_selfcheck_goal_conditioning_t17.py",
     "target": "scripts/run_act_lift_runtime_failure_audit.py",
     "snippet": "'epoch':epoch,'goal_id':goal_id", "expect": 2,
     "why": "**语义变了**：旧锚 `:36,39` 是两处写死的 `'epoch':1,'goal_id':'lift'`，"
            "现由 make_goal_resolver 统一给出 ⇒ 期望命中 **2** 处（frame_records 与 chunks）。",
     "owner_must_contain": ["'epoch':epoch,'goal_id':goal_id"],
     "owner_must_not_contain": ["run_act_lift_runtime_failure_audit.py:36,39"]},

    {"id": "A5_t17_audit_hardcode_gone", "kind": "content",
     "owner": "scripts/b_selfcheck_goal_conditioning_t17.py",
     "target": "scripts/run_act_lift_runtime_failure_audit.py",
     "snippet": "'goal_id':'lift'", "expect": 0,
     "why": "反向断言：写死的 goal_id 必须**一处不剩**。expect=0 的条目一旦命中就是 RED "
            "—— 这条是「硬编码已清除」的牙，不是排版检查。",
     "owner_must_contain": [], "owner_must_not_contain": []},

    {"id": "F1_gate_frozen_stale_anchor", "kind": "frozen",
     "owner": GATE_REL,
     "target": GATE_REL,
     "snippet": "scripts/train_act_lift.py:44", "expect": 1,
     "why": "**不能改**：门禁本体冻结，改一个字节 GATE_BUILD 就变（⇒ D 第三轮复签 + A 重出权威表）。"
            "登记为 v1.6 待修项；这里断言陈旧锚仍在原处、且构建仍是 f19f61341cbe。",
     "owner_must_contain": [], "owner_must_not_contain": []},

    {"id": "H1_incident_doc_leave_as_is", "kind": "historical",
     "owner": "docs/b_normalization_incident_20260928.md",
     "target": "docs/b_normalization_incident_20260928.md",
     "snippet": "scripts/train_act_lift.py:36", "expect": 1,
     "why": "0928 事故留档引的 `:36` 是**当时正确**的 ⇒ 不追改；断言它没被「好心」改写，"
            "否则事故时间线不可核。",
     "owner_must_contain": [], "owner_must_not_contain": []},

    {"id": "H2_handoff_doc_leave_as_is", "kind": "historical",
     "owner": "docs/b_handoff_to_a_20260928.md",
     "target": "docs/b_handoff_to_a_20260928.md",
     "snippet": "scripts/train_act_lift.py:36", "expect": 1,
     "why": "同 H1：B→A 0928 交接单里的 `:36` 属历史留档。",
     "owner_must_contain": [], "owner_must_not_contain": []},
]


def _sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def evaluate(anchors, root: Path = ROOT) -> dict:
    rows, n_fail = [], 0
    for e in anchors:
        res = find_lines(e["target"], e["snippet"], root=root, expect=e["expect"])
        row = {"id": e["id"], "kind": e["kind"], "why": e["why"],
               "target": e["target"], "snippet": e["snippet"], "expect": e["expect"],
               "n_hits": res["n_hits"], "lines": res["lines"],
               "anchor_status": res["status"], "rendered": render(res),
               "owner": e["owner"], "owner_status": "n/a", "detail": res["detail"]}
        ok = res["status"] == "ok"
        # frozen 条目额外断言构建指纹未动（有人「顺手修好」冻结文件就必须红）
        if e["kind"] == "frozen":
            gp = root / GATE_REL
            got = _sha12(gp) if gp.exists() else None
            row["gate_build_observed"] = got
            row["gate_build_expected"] = GATE_BUILD_FROZEN
            if got != GATE_BUILD_FROZEN:
                ok = False
                row["detail"] = ((row["detail"] + "；") if row["detail"] else "") + (
                    "冻结门禁 sha12 实测 %s != %s ⇒ 有人改了冻结文件却没走 v1.6 + D 复签"
                    % (got, GATE_BUILD_FROZEN))
        # content 条目额外断言引用方**确实带着内容锚、且旧行号锚已清除**（防修完又回退）
        if e["kind"] == "content" and (e["owner_must_contain"] or e["owner_must_not_contain"]):
            oc = owner_carries(e["owner"], e["owner_must_contain"],
                               e["owner_must_not_contain"], root=root)
            row["owner_status"] = oc["status"]
            if oc["status"] != "ok":
                ok = False
                row["detail"] = ((row["detail"] + "；") if row["detail"] else "") + oc["detail"]
        row["ok"] = bool(ok)
        n_fail += 0 if ok else 1
        rows.append(row)
        print("  [%s] %-32s %-9s %s" % ("PASS" if ok else "FAIL", row["id"], row["kind"],
                                        row["rendered"]))
        if not ok:
            print("         ↳ %s" % row["detail"])
    n_content = sum(1 for e in anchors if e["kind"] == "content")
    return {"spec": "跨文件内容锚登记册（D→B 执行单 §5 / 验收 §8.5）",
            "ok": n_fail == 0, "summary": {"pass": len(rows) - n_fail, "fail": n_fail,
                                            "total": len(rows), "n_content": n_content},
            "anchors": rows,
            "note": ("content 条目 = 本轮从行号锚改成内容锚的三处（A1/A2+A3/A4+A5）；"
                     "frozen 条目 F1 是**不能改**的门禁本体陈旧锚，登记为 v1.6 待修；"
                     "historical 条目 H1/H2 是当时正确的留档，断言未被改写。"),
            "red_conditions": [
                "内容锚命中数 != expect（含 expect=0 的「必须已删除」被违反）",
                "目标文件缺失",
                "引用方旧行号锚未清除 / 内容锚文本不在（修完又回退）",
                "frozen 条目：门禁 sha12 != %s，或陈旧锚已不在原处" % GATE_BUILD_FROZEN,
                "historical 条目：留档里的 `:36` 被改写",
            ]}


def selftest() -> int:
    """正反变异：证明本闸会红，且不是恒红。"""
    def mut(fn):
        def apply():
            reg = copy.deepcopy(ANCHORS)
            fn(reg)
            return reg
        return apply

    def by_id(reg, aid):
        return next(e for e in reg if e["id"] == aid)

    muts = [
        ("M0_unmutated", False, None, "正对照：原样必须绿"),
        ("M1_expect_count_wrong", True,
         mut(lambda r: by_id(r, "A1_eval_norm_root_cause").update(expect=2)),
         "命中数期望写错（1→2）⇒ count_mismatch 必须红"),
        ("M2_snippet_absent", True,
         mut(lambda r: by_id(r, "A4_t17_audit_goal_epoch").update(
             snippet="'epoch':epoch,'goal_id':NONEXISTENT")),
         "内容锚文本不存在 ⇒ not_found 必须红"),
        ("M3_hardcode_back", True,
         mut(lambda r: by_id(r, "A5_t17_audit_hardcode_gone").update(expect=1)),
         "反向断言被反转（要求写死的 goal_id 还在）⇒ 必须红"),
        ("M4_owner_anchor_regressed", True,
         mut(lambda r: by_id(r, "A1_eval_norm_root_cause")["owner_must_not_contain"].append(
             "clip_norm_input")),
         "引用方侧断言不是摆设：加一条**实际存在**的禁用串 ⇒ 必须红"),
        ("M5_gate_build_drift", True,
         mut(lambda r: by_id(r, "F1_gate_frozen_stale_anchor").update(
             snippet="scripts/train_act_lift.py:44_NONEXISTENT")),
         "冻结条目：陈旧锚不在原处 ⇒ 必须红（意味着有人动了冻结文件）"),
        ("M6_historical_rewritten", True,
         mut(lambda r: by_id(r, "H1_incident_doc_leave_as_is").update(
             snippet="scripts/train_act_lift.py:156")),
         "历史留档条目：把 `:36` 换成 `:156` ⇒ 必须红（不许改写历史）"),
        ("M7_doc_field_only", False,
         mut(lambda r: by_id(r, "A1_eval_norm_root_cause").update(
             why="只改说明字段", id="A1_eval_norm_root_cause")),
         "**反向变异**：只改 why 这类说明字段 ⇒ 必须仍绿（防本闸恒红）"),
    ]
    print("=" * 104)
    print("%-30s %-8s %-8s %s" % ("变异", "期望红", "实际", "结论"))
    print("=" * 104)
    allok, results = True, []
    for mid, expect_red, mk, why in muts:
        reg = ANCHORS if mk is None else mk()
        rep = evaluate(reg) if mk is None else _quiet(reg)
        got_red = not rep["ok"]
        status = "pass" if got_red == expect_red else "FAIL"
        if status == "FAIL":
            allok = False
        results.append({"id": mid, "expect_red": expect_red, "got_red": got_red,
                        "status": status, "why": why,
                        "failed_ids": [r["id"] for r in rep["anchors"] if not r["ok"]]})
        print("%-30s %-8s %-8s %-6s %s" % (mid, expect_red, got_red, status, why))
    print("=" * 104)
    n = sum(1 for r in results if r["status"] == "pass")
    print("selftest：%d/%d 符合预期 → 本闸%s有牙" % (n, len(results), "" if allok else "**不**"))
    print("teeth.non_vacuous =", allok and n == len(results))
    return 0 if allok else 1


def _quiet(reg):
    """selftest 里跑变异体时不刷屏（只回报告）。"""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return evaluate(reg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_source_anchors/report.json"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rep = evaluate(ANCHORS)
    outp = Path(a.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("=" * 104)
    print("内容锚登记册：%d PASS / %d FAIL（其中 content %d 条）→ %s"
          % (rep["summary"]["pass"], rep["summary"]["fail"], rep["summary"]["n_content"],
             "全部成立" if rep["ok"] else "**有锚点漂移，先修锚再用它下结论**"))
    print("产物：%s" % outp)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
