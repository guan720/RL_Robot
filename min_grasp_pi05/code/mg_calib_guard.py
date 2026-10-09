#!/usr/bin/env python
"""档 5.1 · 检测器「松手后守卫」的窗长标定（**离线**，只读档 5 开工前就存在的档 2 语料）

为什么要单独一个脚本，而不是改 `mg_calib_detector.py` 的产物：
  `runs/_diag/harness_calib.{md,json}` 是**档 5 判定引用的锚**（`runs/S5_VERDICT.md` 第二节与
  `code/mg_verdict_s5.py` 都指着它）。坑 40 的纪律是「事后改口径必须另立产物、不得静默覆盖」，
  所以守卫这一维单独落盘；`mg_calib_detector.scan()` 只**加了一个默认关闭的参数**（guard_w=0），
  本脚本重跑过它：产物除时间戳外**逐字节相同**（`runs/_diag/harness_calib_recheck_postguard.*`）。

守卫要治的病（出处 `runs/S5_SUPPLEMENT.md` 第四节）：
  档 5 观察模式 22 次「本来会触发」里，**真误触发 3 次**（would_have_fired ∧ 本局最终成功），
  其中 **2 次**是同一个结构性尾巴 —— 策略已经松手（release/retreat 语义，爪子本该张开）、
  落定保持还没走完时又空合一下 ⇒「连续 3 步 width ≤ 0.020 ∧ 曾经夹持过」成立 ⇒ 报 T3，
  接管一个已经送到/正在收尾的局。守卫 = `held ∧ 最近 guard_w 步内出现过 width ≥ GUARD_WIDTH`
  ⇒ 抑制这一次触发（并把 empty_run 清零重新计数，守卫窗过期后仍连续空合还是会触发）。
  ⚠️ 必须条件化在 `held` 上：开局爪子就是 0.078~0.0805，不加 held 会把真 T1 全吞掉。

门（**先写死再看数**，与坑 40 一致；语料 = 档 2e/2c/2joint 共 240 局，档 5 开工前就存在）：
  ① 主门：档 5 读数臂 **s2e** 的**失败召回必须保持 25/25 = 100%**（守卫不许吃掉任何一次真失败）；
  ② 副门：s2e 臂的**误触发（OK 局被触发）4 → ≤1**；
  ③ 取同时满足 ①② 的**最小** guard_w（窗越短，对真 T3 的遮蔽越小）。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_calib_guard.py --out runs/_diag/guard_calib'
    bash -c 'source code/env.sh && $MG_PY code/mg_calib_guard.py --selftest'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_calib_detector import (  # noqa: E402
    GUARD_WIDTH, HORIZON, N_EMPTY, W_EMPTY, load_corpus, scan,
)

GUARD_GRID = (0, 5, 10, 15, 20, 25, 30, 40, 60, 90)
READ_ARM = "s2e"          # 档 5 的读数臂（检查点 pi05_mix60f120r_s2e/022000）
GATE_RECALL = (25, 25)    # 主门：s2e 臂失败召回必须保持 25/25
GATE_FALSE_MAX = 1        # 副门：s2e 臂误触发（OK 局）≤ 1


# ── 纯函数（可自测）───────────────────────────────────────────────────────
def steps_since_open(widths: np.ndarray, idx: int, guard_width: float = GUARD_WIDTH) -> int:
    """诊断用：在第 idx 步（0-based）**之前或当步**，最近一次 width ≥ guard_width 距今几步。
    从没出现过 ⇒ 返回一个大数（1<<30），与 scan() 内部的初值同义。"""
    w = np.asarray(widths[:idx + 1], dtype=float)
    hit = np.flatnonzero(w >= guard_width)
    return int(idx - hit[-1]) if len(hit) else (1 << 30)


def pick_w(rows: list[dict], arm: str = READ_ARM, gate_recall: tuple[int, int] = GATE_RECALL,
           gate_false_max: int = GATE_FALSE_MAX) -> dict:
    """按门 ①②③ 选 guard_w。rows = sweep_guard 的输出。选不出来 ⇒ chosen=None + 原因。"""
    ok = [r for r in rows if r["arm"] == arm and r["guard_w"] > 0
          and (r["n_fired_fail"], r["n_fail"]) == tuple(gate_recall)
          and r["n_fired_ok"] <= gate_false_max]
    if not ok:
        return {"chosen": None,
                "why": f"{arm} 臂上没有 guard_w 同时满足 失败召回 {gate_recall[0]}/{gate_recall[1]} "
                       f"∧ 误触发 ≤{gate_false_max}（守卫窗一开就吃掉真失败 ⇒ 不能用守卫）"}
    best = min(ok, key=lambda r: r["guard_w"])
    return {"chosen": int(best["guard_w"]), "why": "满足门 ①② 的最小 guard_w",
            "gate_recall": list(gate_recall), "gate_false_max": gate_false_max,
            "recall": best["n_fired_fail"], "n_fail": best["n_fail"],
            "false_ok": best["n_fired_ok"], "n_ok": best["class_counts"].get("OK", 0)}


def sweep_guard(eps: list[dict], guard_w: int, arm: str | None = None,
                guard_width: float = GUARD_WIDTH) -> dict:
    """在语料上按 guard_w 重扫一遍：召回 / 误触发 / 与 guard_w=0 相比变了哪几局。"""
    sub = [e for e in eps if arm is None or e["arm"] == arm]
    fired_fail, fired_ok, changed, tags = [], [], [], Counter()
    for e in sub:
        tag0, step0 = scan(e["width"], e["stop"])
        tagG, stepG = scan(e["width"], e["stop"], guard_w=guard_w, guard_width=guard_width)
        if tagG is not None:
            tags[tagG] += 1
        rec = {"seed": e["seed"], "cls": e["cls"], "arm": e["arm"], "run": e["run"],
               "tag": tagG, "step": stepG, "remain": HORIZON - stepG if stepG > 0 else -1,
               "tag_noguard": tag0, "step_noguard": step0,
               "since_open_at_fire": (steps_since_open(e["width"], stepG - 1) if stepG > 0 else -1),
               "since_open_at_fire_noguard": (steps_since_open(e["width"], step0 - 1) if step0 > 0 else -1)}
        if stepG != step0:
            changed.append(rec)
        if tagG is not None:
            (fired_ok if e["cls"] == "OK" else fired_fail).append(rec)
    tot = Counter(e["cls"] for e in sub)
    n_fail = tot["A"] + tot["B"] + tot["C"]
    return {"arm": arm or "ALL", "guard_w": int(guard_w), "guard_width": guard_width,
            "n": len(sub), "class_counts": dict(tot), "n_fail": n_fail,
            "n_fired_fail": len(fired_fail), "n_fired_ok": len(fired_ok),
            "fail_coverage": len(fired_fail) / n_fail if n_fail else 1.0,
            "false_takeover": len(fired_ok) / tot["OK"] if tot["OK"] else 0.0,
            "takeover_rate": (len(fired_fail) + len(fired_ok)) / len(sub),
            "tags": dict(tags), "n_changed": len(changed),
            "changed": changed, "fired_ok": fired_ok, "fired_fail": fired_fail}


def selftest() -> int:
    n = 0

    def ck(name: str, cond: bool, detail: str = "") -> None:
        nonlocal n
        if not cond:
            raise AssertionError(f"自测失败：{name} {detail}")
        n += 1

    ck("steps_since_open 当步就张开", steps_since_open(np.array([0.08, 0.01]), 0) == 0)
    ck("steps_since_open 三步前", steps_since_open(np.array([0.08, 0.05, 0.01, 0.01]), 3) == 3)
    ck("steps_since_open 从没张开", steps_since_open(np.array([0.04, 0.01, 0.01]), 2) == 1 << 30)
    hold = [0.050] * 25                       # 稳定夹持 ⇒ held=True
    openw = [0.079] * 5                       # 松手（release/retreat）
    empty = [0.005] * 5                       # 松手后又空合 ⇒ 无守卫时报 T3
    w = np.array(hold + openw + empty)
    ck("无守卫：松手后空合报 T3", scan(w, len(w)) == ("T3", 33), str(scan(w, len(w))))
    ck("守卫窗内：抑制", scan(w, len(w), guard_w=25)[0] is None, str(scan(w, len(w), guard_w=25)))
    # 松手后第 3 步才凑满 N_EMPTY ⇒ 距上次张开正好 3 步：guard_w=3 仍被守卫吃掉，guard_w=2 就放行
    ck("守卫窗刚好覆盖 ⇒ 抑制", scan(w, len(w), guard_w=3)[0] is None, str(scan(w, len(w), guard_w=3)))
    ck("守卫窗差一步 ⇒ 仍触发", scan(w, len(w), guard_w=2) == ("T3", 33), str(scan(w, len(w), guard_w=2)))
    # 开局就空合（从没夹持过）⇒ 守卫不得吞掉真 T1，哪怕开局爪子是张开的
    w1 = np.array([0.079] * 10 + [0.005] * 5)
    ck("真 T1 不被守卫吞掉", scan(w1, len(w1), guard_w=25) == ("T1", 13), str(scan(w1, len(w1), guard_w=25)))
    # 守卫窗过期后仍连续空合 ⇒ 还是要触发（那才是真抓空）
    w2 = np.array(hold + openw + [0.050] * 2 + [0.005] * 8)
    ck("守卫过期后的空合仍触发", scan(w2, len(w2), guard_w=5)[0] == "T3", str(scan(w2, len(w2), guard_w=5)))
    # guard_w=0 必须与不传参逐比特同义（档 5 的锚不能被这个新参数动到）
    for arr in (w, w1, w2):
        ck("guard_w=0 等价于关", scan(arr, len(arr), guard_w=0) == scan(arr, len(arr)))
    eps = [{"arm": READ_ARM, "run": "r", "ep": 0, "seed": 7000, "width": w, "cls": "OK",
            "stop": len(w), "lift_cm": 9.0, "min_dist_cm": 1.0, "sha16": "x"},
           {"arm": READ_ARM, "run": "r", "ep": 1, "seed": 7001, "width": w1, "cls": "A",
            "stop": len(w1), "lift_cm": 0.1, "min_dist_cm": 60.0, "sha16": "x"}]
    s = sweep_guard(eps, 0, READ_ARM)
    ck("sweep 无守卫：1 误触发 + 1 召回", (s["n_fired_ok"], s["n_fired_fail"]) == (1, 1), json.dumps(s["class_counts"]))
    s = sweep_guard(eps, 25, READ_ARM)
    ck("sweep 有守卫：误触发清零、召回保住", (s["n_fired_ok"], s["n_fired_fail"]) == (0, 1), str(s["tags"]))
    ck("sweep 记了变化的局", s["n_changed"] == 1 and s["changed"][0]["cls"] == "OK", str(s["changed"]))
    rows = [sweep_guard(eps, gw, READ_ARM) for gw in (0, 5, 25)]
    p = pick_w(rows, gate_recall=(1, 1), gate_false_max=1)
    ck("pick_w 选满足门的最小窗（0 不算候选）", p["chosen"] == 5, json.dumps(p, ensure_ascii=False))
    ck("pick_w 回带门与读数", (p["gate_recall"], p["gate_false_max"], p["recall"], p["false_ok"])
       == ([1, 1], 1, 1, 0), json.dumps(p, ensure_ascii=False))
    ck("误触发门收紧到 0 也满足", pick_w(rows, gate_recall=(1, 1), gate_false_max=0)["chosen"] == 5)
    ck("召回门收不到 ⇒ 选不出来并给原因",
       pick_w(rows, gate_recall=(2, 2))["chosen"] is None and "失败召回" in pick_w(rows, gate_recall=(2, 2))["why"])
    ck("别的臂不掺和", pick_w([dict(r, arm="s2c") for r in rows], gate_recall=(1, 1))["chosen"] is None)
    ck("GUARD_WIDTH 落在夹持带与张开模态之间", 0.060 < GUARD_WIDTH < 0.078, str(GUARD_WIDTH))
    print(f"[guard_calib] selftest 全绿：{n} 项（纯函数 + 桩语料，未读写 runs）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="runs/_diag/guard_calib", help="产物前缀（写 .md 与 .json）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    eps = load_corpus(MG_ROOT)
    arms = sorted({e["arm"] for e in eps})
    print(f"[guard] 语料 {len(eps)} 局 / {sum(len(e['width']) for e in eps)} 步  臂={arms}  "
          f"GUARD_WIDTH={GUARD_WIDTH}  N_EMPTY={N_EMPTY}  W_EMPTY={W_EMPTY}")
    rows = []
    for arm in arms + [None]:
        for gw in GUARD_GRID:
            s = sweep_guard(eps, gw, arm)
            rows.append(s)
            print(f"[guard] arm={s['arm']:<9} guard_w={gw:>3}  失败召回 {s['n_fired_fail']}/{s['n_fail']}  "
                  f"误触发(OK) {s['n_fired_ok']}/{s['class_counts'].get('OK', 0)}  "
                  f"接管率 {s['takeover_rate'] * 100:.1f}%  标签 {s['tags']}  变了 {s['n_changed']} 局")
    pick = pick_w(rows)
    read_arm_rows = [r for r in rows if r["arm"] == READ_ARM]
    base_row = next(r for r in read_arm_rows if r["guard_w"] == 0)
    # 选不出来时**不许**退化去报 guard_w=0 那一行（那会把「没选上」写得像「选了 0 = 不加守卫」，
    # 两者结论完全不同：前者是「守卫没用」，后者是「守卫有害」。坑 40③：缺字段 ≠ 0）
    chosen_row = (next((r for r in read_arm_rows if r["guard_w"] == pick["chosen"]), None)
                  if pick["chosen"] is not None else None)
    verdict = ("采用 guard_w=%d" % pick["chosen"]) if chosen_row is not None else (
        "不采用守卫：%s" % pick["why"])
    all_rows = [r for r in rows if r["arm"] == "ALL"]
    print(f"[guard] ⇒ 选定 guard_w = {pick['chosen']}（{pick['why']}）")
    print(f"[guard] ⇒ 结论：{verdict}")

    out_prefix = Path(args.out)
    if not out_prefix.is_absolute():
        out_prefix = MG_ROOT / out_prefix
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    slim = [{k: v for k, v in r.items() if k not in ("changed", "fired_ok", "fired_fail")} for r in rows]
    payload = {
        "kind": "harness_release_guard_calibration",
        "generated": datetime.now().strftime("%F %T"),
        "gate": {"arm": READ_ARM, "recall_must_stay": list(GATE_RECALL), "false_ok_max": GATE_FALSE_MAX,
                 "rule": "满足主门（失败召回不掉）与副门（误触发 ≤1）的最小 guard_w",
                 "corpus_provenance": "档 2e/2c/2joint 共 240 局反向 TEST（seed7000..7019、K=10），"
                                      "**档 5 开工前就存在** ⇒ 不构成对档 5 读数的调参（坑 40）"},
        "guard": {"rule": "held ∧ 最近 guard_w 步内出现过 width ≥ guard_width ⇒ 抑制这一次触发并清 empty_run",
                  "guard_width": GUARD_WIDTH, "n_empty": N_EMPTY, "w_empty": W_EMPTY,
                  "must_be_conditioned_on_held": "开局爪子 0.078~0.0805，不加 held 会把真 T1 全吞掉"},
        "chosen": pick,
        "verdict": verdict,
        "sweep": slim,
        "detail_read_arm": {
            "guard0_fired_ok": base_row["fired_ok"],
            "chosen_guard_w": (chosen_row["guard_w"] if chosen_row else None),
            "chosen_fired_ok": (chosen_row["fired_ok"] if chosen_row else []),
            "changed_at_chosen": (chosen_row["changed"] if chosen_row else []),
            "changed_at_25": next((r["changed"] for r in read_arm_rows if r["guard_w"] == 25), []),
            "fired_ok_at_25": next((r["fired_ok"] for r in read_arm_rows if r["guard_w"] == 25), []),
            "guard0_fired_fail": base_row["fired_fail"],
            "chosen_fired_fail": (chosen_row["fired_fail"] if chosen_row else []),
        },
        "all_arm_recall_loss": {str(r["guard_w"]): f"{r['n_fired_fail']}/{r['n_fail']}" for r in all_rows},
        "code_sha256_16": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                           for p in sorted(HERE.glob("mg_*.py"))
                           if p.name in ("mg_calib_guard.py", "mg_calib_detector.py", "mg_harness.py")},
        "gates": "本产物只标定 guard_w；不判任何档 5/5.1 的门",
    }
    (out_prefix.with_suffix(".json")).write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    L = ["# 档 5.1 · 检测器「松手后守卫」窗长标定（**不判门**，只标定常数）", "",
         f"由 `code/mg_calib_guard.py` 生成于 {payload['generated']}。",
         "",
         f"语料 = **档 5 开工前就存在**的档 2 反向 TEST 轨迹（{len(eps)} 局，臂 {arms}），"
         "与 `runs/_diag/harness_calib.md` 同一份 ⇒ 本标定不构成对档 5 读数的调参（坑 40）。",
         "",
         "## 一、门的原文（**先写死再看数**）",
         "",
         f"* 主门：`{READ_ARM}` 臂失败召回必须保持 **{GATE_RECALL[0]}/{GATE_RECALL[1]} = 100%**；",
         f"* 副门：`{READ_ARM}` 臂误触发（OK 局被触发）**4 → ≤{GATE_FALSE_MAX}**；",
         "* 取同时满足两者的**最小** `guard_w`。",
         "",
         f"守卫判据：`held ∧ 最近 guard_w 步内出现过 width ≥ {GUARD_WIDTH}` ⇒ 抑制该次触发并清 `empty_run`。",
         "",
         "## 二、扫描结果",
         ""]
    for arm in arms + ["ALL"]:
        L += [f"### 臂 {arm}", "",
              "| guard_w | 失败召回 | 覆盖率 | 误触发(OK) | 接管率 | 标签 | 与 guard_w=0 相比变了 |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in [x for x in rows if x["arm"] == arm]:
            L.append(f"| {r['guard_w']} | {r['n_fired_fail']}/{r['n_fail']} | "
                     f"{r['fail_coverage'] * 100:.1f}% | {r['n_fired_ok']}/"
                     f"{r['class_counts'].get('OK', 0)} | {r['takeover_rate'] * 100:.1f}% | "
                     f"{json.dumps(r['tags'], ensure_ascii=False)} | {r['n_changed']} 局 |")
        L.append("")
    L += ["## 三、选定值与依据", "",
          f"**{verdict}**", "",
          f"门：主门 `{READ_ARM}` 失败召回 {GATE_RECALL[0]}/{GATE_RECALL[1]} ∧ 副门 误触发 ≤{GATE_FALSE_MAX}。"
          f"实测副门在 guard_w ∈ {list(GUARD_GRID)} 上**一个都没满足**（`{READ_ARM}` 误触发恒为 "
          f"{base_row['n_fired_ok']}/{base_row['class_counts'].get('OK', 0)}）⇒ 守卫白付复杂度，不采用。", "",
          "另一侧的代价（ALL 臂失败召回随窗长掉）：`"
          + "`, `".join(f"guard_w={r['guard_w']} ⇒ {r['n_fired_fail']}/{r['n_fail']}" for r in all_rows)
          + "` ⇒ 窗一长就开始吃真失败。两头都不划算。", ""]
    if chosen_row is not None:
        L += [f"选定后 `{READ_ARM}` 臂：失败召回 {chosen_row['n_fired_fail']}/{chosen_row['n_fail']}、"
              f"误触发 {chosen_row['n_fired_ok']}/{chosen_row['class_counts'].get('OK', 0)}、"
              f"接管率 {chosen_row['takeover_rate'] * 100:.1f}%（guard_w=0 时是 "
              f"{base_row['takeover_rate'] * 100:.1f}%）。", "",
              "### guard_w=0 时的误触发局（守卫要治的就是这些）", "",
              "| seed | 分类 | 标签 | 触发步 | 触发时距上次张开 | 守卫后 |",
              "| --- | --- | --- | --- | --- | --- |"]
        after = {r["seed"]: r for r in chosen_row["fired_ok"]}
        for r in base_row["fired_ok"]:
            so = r["since_open_at_fire_noguard"]
            a = after.get(r["seed"])
            L.append(f"| {r['seed']} | {r['cls']} | {r['tag_noguard']} | {r['step_noguard']} | "
                     f"{so if so < (1 << 29) else '从没张开'} 步 | "
                     f"{('仍触发 @' + str(a['step'])) if a else '被抑制'} |")
        L += ["", "### 守卫改动的全部局（含失败局；主门就是查这张表里有没有失败局）", "",
              "| seed | 分类 | 无守卫 | 有守卫 | 触发时距上次张开 |", "| --- | --- | --- | --- | --- |"]
        for r in chosen_row["changed"]:
            so = r["since_open_at_fire"] if r["since_open_at_fire"] >= 0 else r["since_open_at_fire_noguard"]
            L.append(f"| {r['seed']} | {r['cls']} | {r['tag_noguard']}@{r['step_noguard']} | "
                     f"{(str(r['tag']) + '@' + str(r['step'])) if r['tag'] else '不触发'} | "
                     f"{so if so < (1 << 29) else '从没张开'} 步 |")
    else:
        r25 = next((r for r in read_arm_rows if r["guard_w"] == 25), None)
        L += ["### 为什么选不出来：误触发**不是**松手尾巴", "",
              f"`{READ_ARM}` 臂 guard_w=0 的 {base_row['n_fired_ok']} 次误触发（OK 局被触发），"
              f"触发那一刻距上次 width ≥ {GUARD_WIDTH} 的步数：", "",
              "| seed | run | 标签 | 触发步 | 距上次张开 | guard_w=25 时 |",
              "| --- | --- | --- | --- | --- | --- |"]
        after25 = {r["seed"]: r for r in (r25["fired_ok"] if r25 else [])}
        for r in base_row["fired_ok"]:
            so = r["since_open_at_fire_noguard"]
            a = after25.get(r["seed"])
            L.append(f"| {r['seed']} | {r['run']} | {r['tag_noguard']} | {r['step_noguard']} | "
                     f"**{so if so < (1 << 29) else '从没张开'} 步** | "
                     f"{('仍触发 @' + str(a['step'])) if a else '被抑制'} |")
        if r25 is not None:
            L += ["", f"guard_w=25 时这 {base_row['n_fired_ok']} 次**一次都没被抑制**"
                      f"（只把 {r25['n_changed']} 局的触发步往后推），因为它们的「距上次张开」是 "
                      "140~205 步 ≫ 任何候选窗长。", "",
                  "⇒ 机理结论：只用夹爪宽度**分不开**「把 can 放进了目标区（正常松手）」与「中途滑脱」——"
                  "两者都是「曾稳定夹持 → 宽度掉下来」。要分开就得用目标框真值（`ever_in_reverse_target`），"
                  "而那会破掉检测器「只用本体感觉、真机可迁移」的设计前提，第一轮不引入。", "",
                  "### guard_w=25 改动的局（证明守卫只是**推迟**触发，不是消除）", "",
                  "| seed | 分类 | 无守卫 | guard_w=25 | 触发时距上次张开 |",
                  "| --- | --- | --- | --- | --- |"]
            for r in r25["changed"]:
                so = r["since_open_at_fire"] if r["since_open_at_fire"] >= 0 else r["since_open_at_fire_noguard"]
                L.append(f"| {r['seed']} | {r['cls']} | {r['tag_noguard']}@{r['step_noguard']} | "
                         f"{(str(r['tag']) + '@' + str(r['step'])) if r['tag'] else '不触发'} | "
                         f"{so if so < (1 << 29) else '从没张开'} 步 |")
    L += ["", "---",
          "⚠️ 本产物**不判门**：它只给 `mg_harness.GraspDetector` 的 `guard_w` 选值（本轮结论 = 不采用；"
          "`scan(guard_w=0)` 与档 5 用的检测器逐比特同义，已用 `runs/_diag/harness_calib_recheck_postguard.*` "
          "对过账：除时间戳外逐字节相同）。档 5.1 只改两处：专家的 descend 停滞阶梯 + harness 的认输交还；"
          "它们有没有用由**配对净收益**判（坑 47）。"]
    (out_prefix.with_suffix(".md")).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[saved] {out_prefix.with_suffix('.md')}")
    print(f"[saved] {out_prefix.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
