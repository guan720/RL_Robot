#!/usr/bin/env python
"""把已有的接触探针 JSON 重算成 frontier 门禁 + 难度轴诊断（不重跑仿真）。

为什么要单独一个脚本：探针跑一次要十几分钟到一小时（接触任务每局 30~40 s，还要排队
抢 CPU），而门禁参数（预算 / 臂数 / 评测局数 / min_gain / 掉点容忍）是**设计变量**，
会被反复调整。把「量」和「判」分开，改判据时就不必重新量 —— 和 §6.7 里
「跑崩了不用重跑，直接重算已有产物」是同一条纪律。

用法：
    python scripts/report_contact_gate.py runs/infra/paired_lift_default_spawn.json \\
        runs/infra/paired_lift_wide_spawn.json --arms 6 --budget-hours 8
    # 想知道「评测要加到多少局才判得起 min_gain=0.02」：
    python scripts/report_contact_gate.py <json> --eval-episodes 20000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from harness.sampling_design import frontier_verdict  # noqa: E402
from scripts.probe_contact_ceiling import axis_diagnosis  # noqa: E402


def rung_from(doc: dict) -> dict:
    """把一份探针 JSON 翻成 `frontier_verdict` 的一个难度档。"""
    scr = doc.get("scripted") or {}
    sac = doc.get("sac") or {}
    paired = doc.get("paired") or {}
    # 成本按**贵的那一臂**算：SAC 失败局要跑满 horizon（30~40 s），
    # 手写成功局 40 步就收（4~6 s）。用平均会把预算算乐观一个量级。
    rows = sac.get("episodes") or scr.get("episodes") or []
    secs = [float(r.get("wall_sec") or 0.0) for r in rows]
    steps = [float(r.get("steps") or 0) for r in rows]
    tc = doc.get("grasp_truth_check") or {}
    geom = doc.get("object_geom") or {}
    sac_tc = doc.get("sac_grasp_truth_check") or {}
    return {
        "half_range": doc.get("spawn_range") if doc.get("spawn_range") is not None else 0.03,
        "scripted_success": scr.get("success_rate"),
        "sac_success": sac.get("success_rate"),
        "frontier_frac": paired.get("frontier_frac"),
        "too_hard_frac": paired.get("too_hard_frac"),
        "sec_per_episode": round(float(np.mean(secs)), 2) if secs else 0.0,
        "steps_per_sec": (round(float(np.sum(steps) / max(np.sum(secs), 1e-9)), 2)
                          if secs else None),
        "seeding_ok": bool(doc.get("seeding_verified", True)),
        "ctrl_z0_mismatch": sum(1 for r in scr.get("episodes") or []
                                if r.get("z0_matches_spawn") is False),
        "grasp_truth_consistent": tc.get("consistent"),
        "labels_sac": sac.get("labels"),
        "labels_scripted": scr.get("labels"),
        # 门禁支持、以前没人填的三个字段（缺了会报假的"产物没有 object_geom"警告，
        # 而"未钉死 ⇒ 整档作废""弹起式成功 ⇒ 指标不可用"两条规则永远不触发）：
        "object_pinned": (geom.get("pinned_object_seed") is not None) if geom else None,
        "object_geom": geom or None,
        "flick_frac": sac.get("flick_frac", sac_tc.get("flick_frac")),
        "success_rate_grasp_verified": sac.get("success_rate_grasp_verified",
                                               sac_tc.get("success_rate_grasp_verified")),
        "scripted_flick_frac": scr.get("flick_frac"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsons", nargs="+", help="probe_contact_ceiling.py 的输出")
    ap.add_argument("--budget-hours", type=float, default=8.0)
    ap.add_argument("--arms", type=int, default=6)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--episodes-per-round", type=int, default=8)
    ap.add_argument("--train-sec-per-round", type=float, default=0.0,
                    help="每轮训练墙钟（journal.train.train_seconds；Lift 60k 步实测约 6840 s/臂）")
    ap.add_argument("--eval-episodes", type=int, default=50)
    ap.add_argument("--min-gain", type=float, default=0.02)
    ap.add_argument("--regression-tol", type=float, default=0.0)
    ap.add_argument("--eval-every", type=int, default=1)
    ap.add_argument("--eval-sec-per-episode", type=float, default=None)
    ap.add_argument("--sec-per-episode", type=float, default=None,
                    help="覆盖产物里实测的每局墙钟。**成本判定是机器速度的函数**：同一台机器"
                         "上 Lift 一局实测过 25.5 s（宿主 load≈1250）与 2.4 s（load≈600），"
                         "差 10 倍，足以把「6 臂买不起」翻成「6 臂买得起」。用这个开关做"
                         "敏感性分析，不要拿某一次的墙钟当常数。")
    ap.add_argument("--delta", type=float, default=0.30, help="难度轴要检出的桶间效应")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rungs, docs = [], {}
    for path in args.jsons:
        p = Path(path)
        p = p if p.is_absolute() else REPO_ROOT / p
        doc = json.loads(p.read_text(encoding="utf-8"))
        docs[str(p)] = doc
        rung = rung_from(doc)
        rung["sec_per_episode_json"] = rung["sec_per_episode"]
        if args.sec_per_episode is not None:
            rung["sec_per_episode"] = float(args.sec_per_episode)
            rung["sec_per_episode_source"] = "override"
            # 步频按同一比例缩放，否则 steps_per_sec 会与新的墙钟自相矛盾
            if rung.get("steps_per_sec") and rung["sec_per_episode_json"]:
                rung["steps_per_sec"] = round(
                    rung["steps_per_sec"] * rung["sec_per_episode_json"]
                    / max(rung["sec_per_episode"], 1e-9), 2)
        else:
            rung["sec_per_episode_source"] = "json"
        rungs.append(rung)

    gate = frontier_verdict(
        rungs, budget_sec=args.budget_hours * 3600.0, arms=args.arms, rounds=args.rounds,
        episodes_per_round=args.episodes_per_round, train_sec_per_round=args.train_sec_per_round,
        eval_episodes=args.eval_episodes, min_gain=args.min_gain,
        regression_tol=args.regression_tol, eval_every=args.eval_every,
        eval_sec_per_episode=args.eval_sec_per_episode)

    print("=" * 78)
    print(f"frontier 门禁 · 预算 {args.budget_hours:g} h · {args.arms} 臂 × {args.rounds} 轮 × "
          f"{args.episodes_per_round} 局 · 训练 {args.train_sec_per_round:g} s/轮 · "
          f"评测 {args.eval_episodes} 局 / min_gain {args.min_gain:g} / 掉点容忍 "
          f"{args.regression_tol:g}")
    print("=" * 78)
    for rung, src in zip(gate["rungs"], rungs):     # gate 的行只保留规则用得到的字段，
        mark = "通过" if rung["ok"] else "拒绝[" + "/".join(rung["failed"]) + "]"   # 标签从源行取
        print(f"\n档 half_range={rung['half_range']} · {mark}")
        for reason in rung["reasons"]:
            print(f"    - {reason}")
        print(f"    标签(策略侧) {src.get('labels_sac')} · 标签(手写侧) {src.get('labels_scripted')}")
        print(f"    每局 {src.get('sec_per_episode')} s"
              + (f"（覆盖；产物实测 {src.get('sec_per_episode_json')} s）"
                 if src.get("sec_per_episode_source") == "override" else "（产物实测）")
              + f" · {src.get('steps_per_sec')} 步/s · "
              f"抓取真值一致 {src.get('grasp_truth_consistent')}")
    res = gate["checks"]["resolution"]
    print(f"\n分辨率（全局）: {'OK' if res['ok'] else 'FAIL'}\n    {res['reason']}")
    print(f"推荐档位: {gate['recommended']['half_range'] if gate['recommended'] else '无'}")
    for warn in gate["warnings"]:
        print(f"[WARN] {warn}")
    print(f"=> 总判定: {'允许开 A/B' if gate['ok'] else '不允许开 A/B'}")

    axes = {}
    for path, doc in docs.items():
        sac_rows = (doc.get("sac") or {}).get("episodes") or []
        if not sac_rows:
            continue
        secs = [float(r.get("wall_sec") or 0.0) for r in sac_rows]
        ad = axis_diagnosis(sac_rows, int(doc.get("grid") or 3),
                            sec_per_episode=(float(args.sec_per_episode)
                                             if args.sec_per_episode is not None
                                             else float(np.mean(secs))),
                            budget_sec=args.budget_hours * 3600.0, delta=args.delta)
        axes[path] = ad
        print("\n" + "=" * 78)
        print(f"难度轴诊断 · {Path(path).name}（δ={args.delta:g}）")
        print("=" * 78)
        print(f"  失败标签: {ad['labels']}")
        print(f"  主导段: {ad['dominant_segment']} 占 {ad['dominant_frac']}")
        for key in ("spatial", "segment"):
            a = ad[key]
            print(f"  {key:8s}: {a['buckets']} 桶 · 当前每桶 {a['observed_n_per_bucket']} 局"
                  f"（MDE {a['mde_at_observed_n']}）· 判 δ 需每桶 "
                  f"{a['episodes_per_bucket_for_delta']} 局 = 共 {a['total_episodes']} 局"
                  f" ≈ {a['total_hours']} h · 预算内{'可判' if a['decidable_within_budget'] else '不可判'}")
        print(f"  => {ad['verdict']}")

    out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / "contact_gate_report.json"
    payload = {"gate": gate, "axes": axes,
               "rungs": rungs,
               "params": {k: v for k, v in vars(args).items() if k != "jsons"},
               "sources": list(docs)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=float),
                   encoding="utf-8")
    print(f"\n已写出: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
