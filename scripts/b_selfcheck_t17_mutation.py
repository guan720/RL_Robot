#!/usr/bin/env python3
"""B-5 附件：T17 自检脚本自身的变异测试（meta-selfcheck）。

为什么需要这个：`scripts/b_selfcheck_goal_conditioning_t17.py` 的产出是一条**裁定**
（「T17 断言有牙 / 没有牙」），而这条裁定会被拿去决定 C 的 goal 贯通是否验收通过。
一个自己就是恒真的裁定，比没有裁定更危险 —— 本仓已有先例：
`scripts/b_selfcheck_reproducibility.py` 里那条 `record(..., True, ...)` 的恒真
「版本一致」检查，让 robosuite 1.5.2→1.5.1 的 pin 漂移在全绿自检下通过了
（docs/b_reproducibility_incident_20260928.md §2 缺陷 3）。

所以这里对 T17 自检脚本本身做变异测试：注入 5 种「裁定逻辑理应拒绝」的缺陷，
要求 `verdict.test_has_teeth` 翻成 False；再加 1 个未变异正对照 + 1 个
「合法变化」对照（坏实现里多一个 blocked 变体，裁定应当仍为 True）。

2026-09-28 晚实测发现的两个真缺陷就是靠这类变异暴露的：
  · blocked 变体（B1，单 goal 词表）被算进「常规维度检查会放行」的分母，
    导致 teeth 误判为 False（假阴性）；
  · 修好之后，`blocked_variants_cannot_silently_pass` 读的是与分类同源的标志位，
    恒真（假阳性的温床）—— 变异 M6 专门盯这一条。

用法：
    python3 scripts/b_selfcheck_t17_mutation.py
    python3 scripts/b_selfcheck_t17_mutation.py --json-out runs/infra/b_t17/t17_mutation.json
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "b_selfcheck_goal_conditioning_t17.py"

REF_OLD = '''variant("REF_embedding", "参考实现：goal 走可训练 embedding，五个组件各自吃 goal",
                lambda: GoalConditioned("embedding")),'''
B2_OLD = '''variant("B2_zero_gate", "goal embedding 乘一个零初始化的门 -> 前向恒 0，维度全对",
                lambda: GoalConditioned("embedding", zero_gate=True)),'''
B4_OLD = '''variant("B4_goal_not_wired", "goal 只参与维度检查，concat 前被丢成 0",
                lambda: GoalConditioned("embedding", drop_from=("actor", "critic", "editor",
                                                               "candidate_filter", "predictor"))),'''
BAD_LINE = '    bad = report["variants"][1:]'
BLOCKED_BRANCH = '''            t17 = {"all_pass": False, "a_actor_output_changes_with_goal": None,
                   "blocked_reason": "词表 %s 装不下本测试要的 goal %s，「同状态换 goal」构造不出来"
                                     % (tuple(m.vocab), missing)}'''

# expect=None 表示这条只观察、不参与通过判定（用于记录裁定对合法变化的反应）
MUTATIONS = [
    {"id": "M0_unmutated", "expect": True, "old": None, "new": None,
     "why": "正对照：未变异时必须裁定「有牙」"},
    {"id": "M1_ref_is_broken", "expect": False,
     "old": REF_OLD, "new": '''variant("REF_embedding", "MUT",
                lambda: GoalConditioned("embedding", zero_gate=True)),''',
     "why": "参考实现本身是坏的 -> reference_passes 必须让裁定翻 False"},
    {"id": "M2_undetectable_broken", "expect": False,
     "old": B2_OLD, "new": '''variant("B2_zero_gate", "MUT",
                lambda: GoalConditioned("embedding")),''',
     "why": "存在一个 T17 放过的坏实现 -> all_broken_variants_caught_by_t17 必须翻 False"},
    {"id": "M3_b4_also_blocked", "expect": True,
     "old": B4_OLD, "new": '''variant("B4_goal_not_wired", "MUT",
                lambda: GoalConditioned("embedding", vocab=("lift",))),''',
     "why": "合法变化：坏实现里多一个 blocked（runnable 4 个仍 >=1），裁定应仍为 True"},
    {"id": "M5_only_blocked_in_denominator", "expect": False,
     "old": BAD_LINE,
     "new": '    bad = [v for v in report["variants"][1:] if v["conventional_dim_checks_status"] == "blocked"]',
     "why": "分母只剩 blocked 变体时「常规检查不充分」的主张是空洞的 -> non_vacuous 必须翻 False"},
    {"id": "M6_blocked_silently_passes", "expect": False,
     "old": BLOCKED_BRANCH, "new": '            t17 = {"all_pass": True}',
     "why": "blocked 变体被静默放行 -> blocked_variants_cannot_silently_pass 必须翻 False"
            "（这条盯的是恒真断言：它必须读独立证据，不能读与分类同源的标志位）"},
]


def run_variant(src: str, tag: str) -> dict:
    out = Path(tempfile.mkdtemp(prefix="b_t17_mut_")) / ("%s.json" % tag)
    script = Path(tempfile.mkdtemp(prefix="b_t17_mut_")) / ("%s.py" % tag)
    script.write_text(src)
    proc = subprocess.run([sys.executable, str(script), "--json-out", str(out)],
                          capture_output=True, text=True)
    if not out.exists():
        return {"ran": False, "rc": proc.returncode,
                "stderr_tail": proc.stderr[-800:], "teeth": None}
    rep = json.loads(out.read_text())
    return {"ran": True, "rc": proc.returncode, "teeth": rep["teeth_check"],
            "verdict": rep["verdict"]["test_has_teeth"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=str(ROOT / "runs/infra/b_t17/t17_mutation.json"))
    a = ap.parse_args()

    if not TARGET.exists():
        print("找不到 %s" % TARGET)
        return 2
    code = TARGET.read_text()

    results, ok = [], True
    print("=" * 100)
    print("%-32s %-8s %-8s %s" % ("变异", "期望", "实际", "结论"))
    print("=" * 100)
    for m in MUTATIONS:
        src = code
        if m["old"] is not None:
            n = code.count(m["old"])
            if n != 1:
                # 锚点漂移必须**响亮地失败**，不能静默跳过（否则变异测试会退化成恒真）
                print("%-32s ANCHOR-MISS count=%d  ← T17 脚本已重构，请同步更新本文件的锚点"
                      % (m["id"], n))
                results.append({**{k: v for k, v in m.items() if k != "old" and k != "new"},
                                "status": "anchor_miss", "anchor_count": n})
                ok = False
                continue
            src = code.replace(m["old"], m["new"])
        r = run_variant(src, m["id"])
        got = r.get("verdict")
        status = ("pass" if got == m["expect"] else "fail") if m["expect"] is not None else "observe"
        if status == "fail":
            ok = False
        if not r["ran"]:
            status, ok = "no_json", False
        results.append({**{k: v for k, v in m.items() if k not in ("old", "new")},
                        "status": status, "got": got, "rc": r["rc"],
                        "teeth": r.get("teeth"), "stderr_tail": r.get("stderr_tail")})
        print("%-32s %-8s %-8s %s" % (m["id"], m["expect"], got, status))
    print("=" * 100)

    n_judged = sum(1 for r in results if r["status"] in ("pass", "fail"))
    print("变异测试：%d/%d 条判定符合预期（另 %d 条为观察项）→ %s"
          % (sum(1 for r in results if r["status"] == "pass"), n_judged,
             sum(1 for r in results if r["status"] == "observe"),
             "T17 裁定本身有牙" if ok else "**T17 裁定存在恒真/漏判，先修裁定再用它验收**"))

    outp = Path(a.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({"target": str(TARGET.relative_to(ROOT)), "ok": ok,
                                "results": results}, indent=2, ensure_ascii=False) + "\n")
    print("写出:", outp)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
