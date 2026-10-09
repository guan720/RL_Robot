#!/usr/bin/env python
"""把本目录所有评测产物汇总成一张表（唯一口径：mg_eval.py 的 eval_summary.json）。

扫两类产物：
  runs/<run>/sweep/step_<N>/eval_summary.json   —— 检查点扫描曲线
  runs/eval_*/eval_summary.json                 —— 单点定版评测
  runs/**/ceiling_summary.json                  —— 脚本专家上界（mg_ceiling.py）
输出按 (run, step, K) 排序的 markdown 表 + 每个 run 的最好成绩。
档 2 起有正/反两个 task_mode，所以表里带上 task_mode 与 seed 区间，
并单独给一张「策略 vs 专家上界」对照（反向的上界只有 70%，不对照就会误读）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MG = Path(__file__).resolve().parent.parent
RUNS = MG / "runs"

rows = []
for f in sorted(RUNS.glob("**/eval_summary.json")):
    try:
        d = json.loads(f.read_text())
    except Exception:
        continue
    ckpt = d.get("policy_ckpt", "")
    m = re.search(r"runs/([^/]+)/checkpoints/([^/]+)/", ckpt)
    run = m.group(1) if m else "?"
    step = m.group(2) if m else "?"
    if step.isdigit():
        step = str(int(step))
    rows.append({
        "run": run,
        "ckpt": step,
        "type": d.get("policy_type", "?"),
        "K": d.get("n_action_steps", -1),
        "eps": d.get("episodes", 0),
        "succ": d.get("n_success", 0),
        "pc": d.get("pc_success", 0.0),
        "avg_step": d.get("avg_steps_to_success", -1),
        "src": str(f.relative_to(MG)),
    })
    rows[-1]["task_mode"] = d.get("task_mode", "forward")
    rows[-1]["seeds"] = f"{d.get('seed')}/{d.get('seed_mode', '?')}"

rows.sort(key=lambda r: (r["task_mode"], r["run"], int(r["ckpt"]) if r["ckpt"].isdigit() else 0, r["K"]))
print("| task | run | ckpt | policy | K | seeds | 成功/局数 | pc_success | 平均成功步 | 来源 |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
for r in rows:
    print(f"| {r['task_mode']} | {r['run']} | {r['ckpt']} | {r['type']} | {r['K']} | {r['seeds']} | "
          f"{r['succ']}/{r['eps']} | {r['pc'] * 100:.0f}% | {r['avg_step']:.0f} | `{r['src']}` |")

print("\n=== 每个 (run, task, K) 的最好成绩（局数多者优先）===")
best = {}
for r in rows:
    key = (r["run"], r["task_mode"], r["K"])
    cur = best.get(key)
    if cur is None or (r["pc"], r["eps"]) > (cur["pc"], cur["eps"]):
        best[key] = r
for (run, tm, K), r in sorted(best.items()):
    print(f"  [{tm}] {run}  K={K}: {r['succ']}/{r['eps']} = {r['pc'] * 100:.0f}%  @ckpt {r['ckpt']}")

# ── 专家上界（mg_ceiling.py 的 ceiling_summary.json）──────────────────────────
ceil_rows = []
for f in sorted(RUNS.glob("**/ceiling_summary.json")):
    try:
        d = json.loads(f.read_text())
    except Exception:
        continue
    ceil_rows.append({"task_mode": d.get("task_mode", "?"), "sigma": d.get("noise_sigma", -1),
                      "seeds": f"{d.get('seed')}..{(d.get('seeds_used') or [-1])[-1]}",
                      "eps": d.get("episodes", 0), "succ": d.get("n_success", 0),
                      "pc": d.get("pc_success", 0.0), "avg_steps": d.get("avg_steps", -1),
                      "src": str(f.relative_to(MG))})
if ceil_rows:
    print("\n=== 脚本专家上界（门是百分比，没有上界就没法解释 50% 是好是坏）===")
    print("| task | 噪声 σ | seeds | 成功/局数 | 上界 | 平均步数 | 来源 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for c in ceil_rows:
        print(f"| {c['task_mode']} | {c['sigma']} | {c['seeds']} | {c['succ']}/{c['eps']} | "
              f"{c['pc'] * 100:.0f}% | {c['avg_steps']:.0f} | `{c['src']}` |")
    ceil_by_task = {}
    for c in ceil_rows:
        cur = ceil_by_task.get(c["task_mode"])
        if cur is None or c["eps"] > cur["eps"]:
            ceil_by_task[c["task_mode"]] = c
    print("\n=== 策略 vs 上界（同 task_mode，取局数最多的上界做分母）===")
    for tm, c in sorted(ceil_by_task.items()):
        cands = [r for r in rows if r["task_mode"] == tm and r["eps"] >= 20]
        if not cands:
            print(f"  [{tm}] 上界 {c['succ']}/{c['eps']} = {c['pc'] * 100:.0f}%；暂无 ≥20 局的策略读数")
            continue
        top = max(cands, key=lambda r: (r["pc"], r["eps"]))
        print(f"  [{tm}] 上界 {c['succ']}/{c['eps']} = {c['pc'] * 100:.0f}% | "
              f"最好策略读数 K={top['K']} {top['succ']}/{top['eps']} = {top['pc'] * 100:.0f}% "
              f"= 上界的 {(top['pc'] / c['pc'] * 100) if c['pc'] else 0:.0f}%  ({top['run']} @ckpt {top['ckpt']})")
