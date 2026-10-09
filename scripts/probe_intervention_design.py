#!/usr/bin/env python
"""干预强度探针：不训练，只采集，量「采样设计把分布推离均匀多远」。

这是阶段 3 阴性结果之后的**预算门禁**（流程见 docs/notes_stage3.md §12）：

    探针 TV < 门槛  ->  不许跑 A/B（再跑只会多一个不可判定的阴性结果）
    探针 TV >= 门槛 ->  才允许把几万步交互预算烧在 A/B 上

门槛要和**天花板**一起读（`harness/sampling_design.py::tv_ceiling`）：
`TV_max = (1 - mix_uniform) * (1 - 1/n_bands)`，mix=0.25 时 2 带 0.375 / 3 带 0.500 /
4 带 0.563。所以默认的 0.4 门槛在 `n_bands=2` 下构造上不可达；而 TV=0.500 的三带候选
其实是「压满天花板」的 one-hot 计划（floor 被压到 0）—— 表格里的 `占顶` 列就是这件事，
过门禁时它会以 warning 形式一起打印，别把「够强」误读成「设计对」。

表里还有两列是**实测**口径（`--realized-draws`，默认 3000 次真采样）：
`TV距离` 把两个采样器各抽 N 个目标、比距离直方图，能看见名义 TV 看不见的事
（带被环境 `min_goal_dist` 截断、内外圈带体积不等）；`覆盖` 是干预后 P10~P90 的距离跨度
占环境距离域的比例 —— 覆盖太窄意味着「训练分布远窄于评测分布」，掉点风险高。
`TV距离` 必须和同一张表里的噪声地板（两个独立均匀采样器之间的 TV，约 0.03）比。

为什么在多个 ckpt 上量：干预强度随策略水平变化（随机策略失败全 diverged、
收敛期几乎不失败），只看一个点会高估或低估。默认取 run2 诊断臂的中段候选权重。

用法：
    python scripts/probe_intervention_design.py                      # 默认候选 + 默认 ckpt 组
    python scripts/probe_intervention_design.py --episodes 16 --seeds 0 1
    python scripts/probe_intervention_design.py --candidates quantile:0.05:4,quantile:0.05:6
    python scripts/probe_intervention_design.py --tv-gate 0.4 --out runs/infra
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "yaml")

import yaml  # noqa: E402

from harness import sampling_design as sd  # noqa: E402

DEFAULT_CKPTS = [
    "runs/ab_stage3/run2_perturbed/diagnosed_s0/round05_train/candidate.zip",
    "runs/ab_stage3/run2_perturbed/diagnosed_s0/round10_train/candidate.zip",
    "runs/ab_stage3/run2_perturbed/diagnosed_s0/round15_train/candidate.zip",
]
DEFAULT_CANDIDATES = ("range:0.15:4,range:0.05:4,range:0.0:4,"
                      "quantile:0.05:4,"
                      "labelcond:0.05:4,labelcond:0.0:3,"
                      "frontier:0.15:4,frontier:0.05:4,frontier:0.0:3,frontier:0.05:3")


def parse_candidates(text: str) -> list[dict]:
    out = []
    for item in [x for x in text.split(",") if x.strip()]:
        band_mode, floor, n_bands = (item.split(":") + ["0.15", "4"])[:3]
        out.append({"band_mode": band_mode.strip(), "floor": float(floor),
                    "n_bands": int(n_bands)})
    return out


def load_env_kwargs(config_path: Path) -> tuple[dict, float, str]:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    env_kwargs = dict(data.get("env") or {})
    goal_radius = float(env_kwargs.get("goal_radius", 0.02))
    factory = str(data.get("env_factory", "reach"))
    return env_kwargs, goal_radius, factory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "reach_perturbed.yaml"))
    parser.add_argument("--ckpt", action="append", default=[],
                        help="要量干预强度的策略权重，可重复；默认 run2 诊断臂的中段候选")
    parser.add_argument("--episodes", type=int, default=12, help="每个 ckpt x seed 采几局")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--mix-uniform", type=float, default=0.25)
    parser.add_argument("--realized-draws", type=int, default=3000,
                        help="实测口径每个采样器抽多少个目标（0 = 只算名义 TV）")
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES,
                        help="逗号分隔的 band_mode:floor:n_bands")
    parser.add_argument("--tv-gate", type=float, default=0.4,
                        help="TV 门槛：低于它就不许花预算跑 A/B")
    parser.add_argument("--objective", choices=("strength", "coverage"), default="strength",
                        help="strength=在合法候选里选 TV 最大（回答「有没有用」）；"
                             "coverage=在过强度门槛的候选里选覆盖最宽（回答「泛化跟不跟得上」）")
    parser.add_argument("--out", default="runs/infra")
    args = parser.parse_args()

    env_kwargs, goal_radius, factory = load_env_kwargs(Path(args.config))
    candidates = parse_candidates(args.candidates)
    ckpts = args.ckpt or DEFAULT_CKPTS

    print("=" * 92)
    print(f"干预强度探针 · config={Path(args.config).name} · env_factory={factory} · "
          f"{args.episodes} 局/ckpt/seed · seeds={args.seeds} · objective={args.objective}")
    print("=" * 92)

    report: dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": str(args.config),
        "env_kwargs": env_kwargs,
        "candidates": candidates,
        "mix_uniform": args.mix_uniform,
        "tv_gate": args.tv_gate,
        "realized_draws": args.realized_draws,
        "per_ckpt": {},
    }
    verdicts = []
    for ckpt in ckpts:
        path = REPO_ROOT / ckpt
        if not path.exists():
            print(f"[跳过] 找不到权重 {ckpt}")
            continue
        from skills.reach_skills import ReachPolicySkill

        skill = ReachPolicySkill(path, name="probe_policy")
        records = sd.collect_joint(skill, env_kwargs, episodes=args.episodes,
                                   seeds=args.seeds, goal_radius=goal_radius,
                                   env_factory=factory)
        failures = [r for r in records if not r.success]
        rows = sd.design_table(failures, goal_radius=goal_radius,
                               half_space=float(env_kwargs.get("half_space", 0.15)),
                               candidates=candidates, mix_uniform=args.mix_uniform,
                               min_goal_dist=env_kwargs.get("min_goal_dist"),
                               realized_draws=args.realized_draws)
        verdict = sd.gate_verdict(rows, tv_gate=args.tv_gate)
        verdict = sd.gate_verdict(rows, tv_gate=args.tv_gate, objective=args.objective)
        report["per_ckpt"][ckpt] = {
            "n_episodes": len(records),
            "n_failures": len(failures),
            "labels": dict(sorted({r.label: sum(1 for x in records if x.label == r.label)
                                   for r in records}.items(), key=lambda kv: -kv[1])),
            "rows": rows,
            "verdict": verdict,
        }
        verdicts.append(verdict)
        print(f"\n  ckpt {ckpt}  ({len(records)} 局, {len(failures)} 失败)")
        noise = next((r.get("tv_noise_floor") for r in rows if r.get("tv_noise_floor") is not None), None)
        print(f"    {'design':24s}{'TV名义':>8s}{'占顶':>7s}{'TV距离':>9s}{'覆盖':>7s}"
              f"{'饿带':>9s}  weights"
              + (f"   [TV距离噪声地板 {noise:.3f}]" if noise is not None else ""))
        for row in rows:
            tag = f"{row['band_mode']}/f{row['floor']:g}/b{row['n_bands']}"
            frac = row.get("tv_frac") or 0.0
            mark = " ←one-hot" if row.get("one_hot") else ""
            tv_d = row.get("tv_distance")
            sup = row.get("support_frac")
            print(f"    {tag:24s}{row['tv']:>8.3f}{frac:>6.0%}"
                  f"{(f'{tv_d:.3f}' if tv_d is not None else '-'):>9s}"
                  f"{(f'{sup:.0%}' if sup is not None else '-'):>7s}"
                  f"{str(row['starved_bands']):>9s}  {row['weights']}{mark}")
        print(f"    判定: {'允许跑 A/B' if verdict['ok'] else '拒绝跑 A/B'} —— {verdict['reason']}")
        for warning in verdict.get("warnings") or []:
            print(f"    ⚠ {warning}")

    ok_all = bool(verdicts) and all(v["ok"] for v in verdicts)
    phased = sd.gate_verdict_phased(verdicts, tv_gate=args.tv_gate)
    mean_best = (sum(v["best"]["tv"] for v in verdicts if v.get("best")) /
                 max(1, sum(1 for v in verdicts if v.get("best"))))
    all_warnings = [w for v in verdicts for w in (v.get("warnings") or [])]
    ceiling_by_bands = {str(n): round(sd.tv_ceiling(n, args.mix_uniform), 4)
                        for n in sorted({int(c.get("n_bands", 4)) for c in candidates})}
    report["gate"] = {
        "ok": bool(phased["ok"]),
        "policy": phased.get("policy"),
        "per_phase_tv": phased.get("per_phase_tv"),
        "reason": phased.get("reason"),
        "mean_best_tv": round(mean_best, 4),
        "warnings": sorted(set(all_warnings)),
        "tv_ceiling_by_bands": ceiling_by_bands,
        "note": ("v1（所有阶段都过门槛）保留在 per_ckpt 里作参考；总门禁用 v2："
                 "中后期过门槛 + 早期不退化 + 均值过门槛。规则与理由见 "
                 "harness/sampling_design.py::gate_verdict_phased 的 docstring"),
    }
    ok_all = bool(phased["ok"])
    out_dir = REPO_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{stamp}_intervention_probe.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "-" * 92)
    metric = phased.get("metric") or "tv"
    print(f"  跨 ckpt 最强候选 名义 TV 均值 = {mean_best:.3f}"
          f" · {metric} 均值 = {phased.get('mean_tv'):.3f} · 门槛 = {args.tv_gate:g}"
          f"（判定用 {metric}）")
    print(f"  TV 天花板（mix_uniform={args.mix_uniform:g}）= {ceiling_by_bands}"
          f" · 门槛可达的最少带数 = "
          f"{min([n for n in (2, 3, 4, 6, 8) if sd.tv_ceiling(n, args.mix_uniform) >= args.tv_gate], default='>8')}")
    print(f"  分阶段最佳 {metric}（早->晚）= {phased.get('per_phase_tv')}")
    print(f"  v2 门禁理由: {phased.get('reason')}")
    for warning in sorted(set(all_warnings)):
        print(f"  ⚠ {warning}")
    if phased.get("best"):
        b = phased["best"]
        print(f"  推荐设计: --band-mode {b['band_mode']} --plan-floor {b['floor']} "
              f"--plan-bands {b['n_bands']}（objective={phased.get('objective')}）")
    if ok_all and phased.get("best"):
        b = phased["best"]
        print(f"  门禁: 通过 —— 可以花预算跑 A/B（compare_harness_ab.py --band-mode "
              f"{b['band_mode']} --plan-floor {b['floor']} --plan-bands {b['n_bands']}）")
    else:
        print("  门禁: 不通过 —— 先改设计再量，别烧预算")
    print(f"  结果写入: {out_path.relative_to(REPO_ROOT)}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
