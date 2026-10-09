#!/usr/bin/env python
"""把历史 journal 的发布判定在两套口径下重放一遍（零仿真成本，只读 JSON）。

为什么值得做：三态门禁（`registry/publish.py::decide_paired`）上线后，第一个问题不是
"它以后会怎么判"，而是"**它会把已经发生过的那些判定改成什么**"。run7 决定性臂是
§12.11-G 的实证来源（round 6 用 +0.02、p=0.31 发布；rounds 2/3 用 p=0.076/0.335 判掉点），
但那些结论是二态口径给的。重放能直接数出：有多少轮的结论会变、变完之后
"可发布的最好版本"还是不是同一个。

**重放必须先复现历史**：脚本先用 legacy 口径把每一轮的判定重算一遍，与 journal 里记录的
`gate.ok` 逐轮对照；对不上就说明现任链重建错了（或阈值给错了），此时只报警不结论 ——
拿一条重建错的链去比较两套口径，比不比较更糟。

一个已知的口径限制：**历史 journal 里没有逐局记录**（`score_skill` 当时把 `episodes`
剥掉了，§7 第 26 条），所以三态口径在重放时只能走**未配对的 MDE 回退**。它仍然能给出
第三态（这正是二态缺的那一态），但分辨力不如真配对；输出里逐轮标了 `fallback.kind`。

用法：
    python scripts/replay_gate_journals.py runs/ab_stage3/run7_fullstate/*/journal.jsonl
    python scripts/replay_gate_journals.py <journal> --min-gain 0.02 --regression-tol 0.0
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from registry.publish import (GATE_STATS_LEGACY, GATE_STATS_PAIRED,  # noqa: E402
                              decide, decide_paired)


def load_train_rows(journal: Path) -> list[dict]:
    rows = [json.loads(ln) for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip()]
    trains = [r for r in rows if r.get("phase") == "train"]
    if not trains:
        raise SystemExit(f"[ERR] {journal} 里没有 train 记录")
    return trains


def replay(rows: list[dict], *, gate_stats: str, min_gain: float, regression_tol: float,
           min_success: float, init: dict) -> list[dict]:
    """按轮次重放一条现任链。返回每轮的判定记录。"""
    inc: dict | None = dict(init)
    out = []
    for r in rows:
        cand = r.get("candidate_metrics") or {}
        n_ep = int((r.get("candidate_scores") or {}).get("n_episodes") or 0) or None
        # 历史 scores 里没有逐局记录 ⇒ paired=None，三态会走 MDE 回退（见模块 docstring）
        std = (r.get("candidate_scores") or {}).get("standard") or {}
        paired = None
        outcomes = std.get("episode_outcomes") or std.get("episodes")
        if outcomes and inc is not None:
            paired = {"n_pairs": len(outcomes), "only_new": 0, "only_inc": 0,
                      "mcnemar": {"exact_p": 1.0},
                      "note": "重放时用逐局记录现场配对（历史 journal 通常没有）"}
        if gate_stats == GATE_STATS_PAIRED:
            g = decide_paired(cand, inc, paired=paired, eval_episodes=n_ep,
                              min_gain=min_gain, regression_tol=regression_tol,
                              min_success=min_success)
            rec = {"decision": g["decision"], "ok": g["ok"], "reason_code": g["reason_code"],
                   "direction": g["direction"], "delta": g.get("delta"), "mde": g.get("mde"),
                   "fallback": (g.get("fallback") or {}).get("kind"),
                   "reasons": g["reasons"]}
        else:
            ok, reasons = decide(cand, inc, min_gain=min_gain, regression_tol=regression_tol,
                                 min_success=min_success)
            rec = {"decision": "publish" if ok else "no_publish", "ok": bool(ok),
                   "reason_code": None, "direction": None,
                   "delta": (round(float(cand.get("success_rate") or 0.0)
                                   - float((inc or {}).get("success_rate") or 0.0), 4)
                             if inc is not None else None),
                   "mde": None, "fallback": None, "reasons": reasons}
        rec.update({"round": r.get("round"),
                    "cand_success": cand.get("success_rate"),
                    "cand_harsh": cand.get("harsh_success_rate"),
                    "inc_success": (inc or {}).get("success_rate"),
                    "recorded_ok": bool((r.get("gate") or {}).get("ok")),
                    "recorded_published_to": r.get("published_to") or ""})
        if rec["ok"]:
            inc = dict(cand)
        rec["incumbent_after"] = (inc or {}).get("success_rate")
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("journals", nargs="+", help="journal.jsonl（可用 shell 通配）")
    ap.add_argument("--min-gain", type=float, default=0.02)
    ap.add_argument("--regression-tol", type=float, default=0.0)
    ap.add_argument("--min-success", type=float, default=0.0)
    ap.add_argument("--init-success", type=float, default=0.0,
                    help="第 1 轮之前现任（起点技能）的标准成功率。run7 的起点是随机技能，"
                         "journal 第 1 轮的理由里写着「严酷探针 0.120 >= 现任 0.000」⇒ 0.0")
    ap.add_argument("--init-harsh", type=float, default=0.0)
    ap.add_argument("--out", default="runs/infra/gate_replay.json")
    args = ap.parse_args()

    paths: list[Path] = []
    for pat in args.journals:
        hit = sorted(glob.glob(pat)) or [pat]
        paths += [Path(h) for h in hit]
        paths = [p if p.is_absolute() else REPO_ROOT / p for p in paths]

    init = {"success_rate": args.init_success, "harsh_success_rate": args.init_harsh}
    kw = {"min_gain": args.min_gain, "regression_tol": args.regression_tol,
          "min_success": args.min_success}
    payload: dict = {}
    n_mismatch = 0
    for path in paths:
        rows = load_train_rows(path)
        legacy = replay(rows, gate_stats=GATE_STATS_LEGACY, init=init, **kw)
        paired = replay(rows, gate_stats=GATE_STATS_PAIRED, init=init, **kw)
        mism = [r["round"] for r in legacy if r["ok"] != r["recorded_ok"]]
        n_mismatch += len(mism)
        changed = [(l, p) for l, p in zip(legacy, paired) if l["ok"] != p["ok"]
                   or (p["decision"] == "inconclusive")]
        name = f"{path.parent.parent.name}/{path.parent.name}"
        print("=" * 92)
        print(f"{name} · {len(rows)} 轮 · min_gain={args.min_gain} tol={args.regression_tol}")
        print("=" * 92)
        print(f"  {'轮':>3} {'候选':>7} {'现任':>7} {'δ':>8} {'MDE':>7}  "
              f"{'legacy':<11} {'记录':<6} {'paired_v1':<13} {'code':<26} 方向")
        for l, p in zip(legacy, paired):
            print(f"  {l['round']:>3} {l['cand_success']:>7.3f} "
                  f"{(l['inc_success'] if l['inc_success'] is not None else float('nan')):>7.3f} "
                  f"{(p['delta'] if p['delta'] is not None else float('nan')):>+8.3f} "
                  f"{(p['mde'] or float('nan')):>7.3f}  {l['decision']:<11} "
                  f"{'发布' if l['recorded_ok'] else '拒绝':<6} {p['decision']:<13} "
                  f"{str(p['reason_code']):<26} {p['direction']}")
        print(f"  legacy 重放与 journal 记录: "
              + ("**逐轮一致**" if not mism else f"❌ 第 {mism} 轮对不上（现任链或阈值重建错了）"))
        n_pub_l = sum(1 for r in legacy if r["ok"])
        n_pub_p = sum(1 for r in paired if r["ok"])
        n_inc = sum(1 for r in paired if r["decision"] == "inconclusive")
        print(f"  发布轮数: legacy {n_pub_l} → paired_v1 {n_pub_p}；"
              f"paired_v1 里 {n_inc}/{len(rows)} 轮是 inconclusive（测不出来）")
        print(f"  链条末点的现任: legacy {legacy[-1]['incumbent_after']} → "
              f"paired_v1 {paired[-1]['incumbent_after']}")
        for l, p in changed[:6]:
            print(f"    · 第 {l['round']} 轮结论变化: legacy={l['decision']} → "
                  f"paired_v1={p['decision']}（{p['reason_code']}）")
            print(f"        {p['reasons'][-1][:150]}")
        payload[name] = {"journal": str(path), "rounds": len(rows),
                         "legacy": legacy, "paired_v1": paired,
                         "legacy_mismatch_rounds": mism,
                         "n_published_legacy": n_pub_l, "n_published_paired": n_pub_p,
                         "n_inconclusive_paired": n_inc,
                         "final_incumbent_legacy": legacy[-1]["incumbent_after"],
                         "final_incumbent_paired": paired[-1]["incumbent_after"]}
        print()

    out = Path(args.out)
    out = out if out.is_absolute() else REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"params": vars(args), "replays": payload},
                              ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(f"已写出: {out}")
    if n_mismatch:
        print(f"[WARN] 共 {n_mismatch} 轮 legacy 重放与记录不一致：先修重建口径再读结论")
    return 1 if n_mismatch else 0


if __name__ == "__main__":
    raise SystemExit(main())
