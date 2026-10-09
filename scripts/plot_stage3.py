#!/usr/bin/env python
"""把阶段 3 的闭环产物画成图：A/B 学习曲线、失败标签、采样权重、门禁时间线。

阶段 3 的 A/B 结论是**阴性**的（诊断 + 针对性采样没有加速学习）。阴性结论最怕
「从终端表格里挑两个好看的数字」，所以图的作用是让阴性结论**可核查**：

    1. 两臂的学习曲线到底差多少？               -> fig_ab_learning_curves.png
    2. 「达到阈值的步数」在两个 seed 上是否一致？ -> fig_steps_to_threshold.png
    3. 诊断看到的失败构成随训练怎么变？          -> fig_failure_labels_over_rounds.png
    4. 诊断**实际**改变了多少采样分布？          -> fig_sampling_weights_over_rounds.png
    5. 门禁放行了哪些轮、拒了哪些轮、凭什么？     -> fig_gate_timeline.png
    6. 行为树的哪条路径真的被走过？              -> fig_recovery_paths.png
    7. 预算记账对不对（环境步数 / 训练时间）？    -> fig_budget_and_cost.png

第 4 张是这次阴性结果的**机理解释**：实测两臂的采样分布总变差距离（TV）只有约 0.24，
而且外圈两个 band 每一轮都被 floor 钉死在 0.094。也就是说「针对性采样」这个干预
本身强度很弱、且几乎不随轮次变化 —— 弱干预测不出加速，是正常结果而不是 bug。

一个必须记住的坑（我第一版就画错了）：
    `collect_summary.sampling_plan` 在 **uniform 臂里也会被计算**，它只是
    「诊断本来会怎么说」的**反事实**记录；真正生效的采样器写在 `train.sampler`
    （uniform 臂是 `kind=uniform`、`weights=[]`）。画「实际采样分布」必须读后者，
    否则两臂会画成一模一样。

注意：本机没有中文字体，所以**图里的标签一律用英文**，中文解释放在终端输出和 docs 里。

用法：
    python scripts/plot_stage3.py --latest                       # 自动挑最新的 A/B 产物
    python scripts/plot_stage3.py --run runs/ab_stage3/run2_perturbed
    python scripts/plot_stage3.py --run runs/ab_stage3/run1 --run runs/ab_stage3/run2_perturbed
    python scripts/plot_stage3.py --latest --scripted-baseline 0.94   # 画上手写控制器基线
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "matplotlib")

import matplotlib  # noqa: E402

matplotlib.use("Agg")          # 本机无显示器，必须用离屏后端
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

MODE_COLOR = {"uniform": "#2f7ed8", "diagnosed": "#e8a33d"}
MODE_STYLE = {"uniform": "-", "diagnosed": "--"}
SEED_ALPHA = {0: 0.95, 1: 0.55, 2: 0.4}
LABEL_COLOR = {
    "success": "#3aa657",
    "no_precision": "#e0524d",
    "diverged": "#8e44ad",
    "timeout_far": "#7f8c8d",
    "timeout_mid": "#bdc3c7",
    "never_moved": "#2c3e50",
}
OUTCOME_COLOR = {
    "forward_success": "#3aa657",
    "backward_success": "#27783f",
    "recovered": "#e8a33d",
    "takeover": "#e0524d",
    "reset": "#7f8c8d",
}
ARM_ORDER = [("uniform", 0), ("uniform", 1), ("diagnosed", 0), ("diagnosed", 1)]


# --------------------------------------------------------------------------- 读取
def find_latest_run() -> Path | None:
    """挑 `runs/ab_stage3/*` 里最新的、含 compare.json 的那次。

    按 **compare.json 的 mtime** 排序，不是目录 mtime：本脚本自己会往
    `<run>/figures/` 写产物，目录 mtime 会被「刚画过图的那次」顶上去，
    于是 --latest 会永远停在第一次画图的 run 上（实测踩过）。
    """
    root = REPO_ROOT / "runs" / "ab_stage3"
    if not root.exists():
        return None
    candidates = [p for p in sorted(root.glob("*")) if (p / "compare.json").exists()]
    return max(candidates, key=lambda p: (p / "compare.json").stat().st_mtime) if candidates else None


def load_journal(arm_dir: Path) -> list[dict]:
    path = arm_dir / "journal.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # 进程被 kill 时最后一行可能是半截，跳过而不是崩
    return records


def load_run(run_dir: Path) -> dict | None:
    """把一次 A/B 跑的全部产物读进来：compare.json + 每臂 journal + loop_result。"""
    compare_path = run_dir / "compare.json"
    if not compare_path.exists():
        print(f"[跳过] {run_dir} 里没有 compare.json")
        return None
    compare = json.loads(compare_path.read_text(encoding="utf-8"))
    arms: dict[str, dict] = {}
    for row in compare.get("rows", []):
        mode, seed = str(row.get("mode")), int(row.get("seed", 0))
        key = f"{mode}_s{seed}"
        arm_dir = run_dir / key
        loop_result = {}
        loop_path = arm_dir / "loop_result.json"
        if loop_path.exists():
            try:
                loop_result = json.loads(loop_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                loop_result = {}
        arms[key] = {
            "key": key,
            "mode": mode,
            "seed": seed,
            "row": row,
            "curve": [tuple(c) for c in row.get("curve", [])],
            "journal": load_journal(arm_dir),
            "loop": loop_result,
            "dir": arm_dir,
        }
    return {
        "run_dir": run_dir,
        "name": run_dir.name,
        "compare": compare,
        "args": compare.get("args", {}),
        "note": compare.get("note", ""),
        "arms": arms,
    }


# --------------------------------------------------------------------------- 统计
def steps_to_threshold(curve: list[tuple], threshold: float) -> int | None:
    """第一次让独立评测成功率 >= threshold 的**累计环境步数**（与 compare 脚本同口径）。"""
    for point in curve:
        if len(point) >= 2 and float(point[1]) >= threshold:
            return int(point[0])
    return None


def actual_weights(arm: dict) -> tuple[np.ndarray, list[int], float]:
    """从 `train.sampler` 读**真正生效**的采样权重（不是反事实的 sampling_plan）。

    返回 (weights 矩阵[n_rounds, n_bands], 对应的 round 号, mix_uniform)。
    uniform 臂没有 weights，返回空矩阵。
    """
    rows, rounds, mix = [], [], 0.25
    for record in arm["journal"]:
        sampler = ((record.get("train") or {}).get("sampler") or {})
        weights = sampler.get("weights") or []
        if sampler.get("mix_uniform") is not None:
            mix = float(sampler["mix_uniform"])
        if len(weights) >= 2:
            rows.append([float(w) for w in weights])
            rounds.append(int(record.get("round", len(rounds) + 1)))
    if not rows:
        return np.zeros((0, 0)), rounds, mix
    width = min(len(r) for r in rows)
    return np.array([r[:width] for r in rows], dtype=float), rounds, mix


def counterfactual_weights(arm: dict) -> tuple[np.ndarray, list[int]]:
    """`collect_summary.sampling_plan`：诊断**本来会**给的权重（uniform 臂里不生效）。"""
    rows, rounds = [], []
    for record in arm["journal"]:
        plan = ((record.get("collect_summary") or {}).get("sampling_plan") or {})
        weights = plan.get("weights") or []
        if len(weights) >= 2:
            rows.append([float(w) for w in weights])
            rounds.append(int(record.get("round", len(rounds) + 1)))
    if not rows:
        return np.zeros((0, 0)), rounds
    width = min(len(r) for r in rows)
    return np.array([r[:width] for r in rows], dtype=float), rounds


def tv_vs_uniform(source: np.ndarray, mix: float) -> dict:
    """把一串 banded 权重换算成「离均匀采样有多远」。

    TV（total variation）= 0.5 * sum|p_effective - p_uniform|：0 表示与均匀采样无区别，
    1 表示完全不重叠。有效分布 = (1-mix_uniform)*banded + mix_uniform*uniform，
    因为采样器每轮都会掺 `mix_uniform` 比例的均匀样本（保底覆盖）。
    """
    n_bands = int(source.shape[1])
    uniform = np.full(n_bands, 1.0 / n_bands)
    effective = (1.0 - mix) * source + mix * uniform
    tv = 0.5 * np.abs(effective - uniform).sum(axis=1)
    return {
        "tv_mean": round(float(tv.mean()), 4),
        "tv_min": round(float(tv.min()), 4),
        "tv_max": round(float(tv.max()), 4),
    }


def pinned_bands(source: np.ndarray, tolerance: float = 0.01) -> tuple[list[float], list[int]]:
    """找出「整个训练里几乎没动过」的 band（被 floor 钉死）。

    用**跨度 max-min** 而不是 std：journal 里的权重只存了 4 位小数，
    0.0938 / 0.0937 这种舍入抖动会让 std 非零，用 std<1e-9 判定会一个都判不出来。
    """
    span = source.max(axis=0) - source.min(axis=0)
    return ([round(float(x), 4) for x in span],
            [i + 1 for i, value in enumerate(span) if float(value) < tolerance])


def intervention_strength(arm: dict) -> dict:
    """量化「诊断到底把**实际**采样分布推离均匀多少」——阴性结果的关键证据。

    两条口径必须分开，混起来就会得出假结论：
      · `tv_*`               实际生效的采样器离均匀有多远。uniform 臂**恒为 0**。
      · `counterfactual_tv_*` `sampling_plan` 离均匀有多远。uniform 臂里这个计划
                             **被计算并记录、但没有生效**（`train.sampler.kind=uniform`）。
    """
    weights, _rounds, mix = actual_weights(arm)
    plan, _plan_rounds = counterfactual_weights(arm)
    out: dict = {
        "sampler_kind": sorted({((r.get("train") or {}).get("sampler") or {}).get("kind", "?")
                                for r in arm["journal"]}),
        "applied": "banded" if len(weights) else "uniform",
        "n_rounds_with_weights": int(len(weights)),
        "mix_uniform": mix,
        "tv_mean": 0.0, "tv_min": 0.0, "tv_max": 0.0,
        "band_mean": [], "band_std": [], "band_range": [], "pinned_bands": [],
        "counterfactual_tv_mean": None, "counterfactual_tv_max": None,
        "counterfactual_band_range": [], "counterfactual_pinned_bands": [],
    }
    if len(weights):
        out.update(tv_vs_uniform(weights, mix))
        out["band_mean"] = [round(float(x), 4) for x in weights.mean(axis=0)]
        out["band_std"] = [round(float(x), 4) for x in weights.std(axis=0)]
        out["band_range"], out["pinned_bands"] = pinned_bands(weights)
    else:
        # uniform 臂：实际采样就是均匀的，TV 定义上为 0。别把反事实计划当成实际干预。
        out["tv_mean"] = out["tv_min"] = out["tv_max"] = 0.0
    if len(plan):
        stats = tv_vs_uniform(plan, mix)
        out["counterfactual_tv_mean"] = stats["tv_mean"]
        out["counterfactual_tv_max"] = stats["tv_max"]
        out["counterfactual_band_range"], out["counterfactual_pinned_bands"] = pinned_bands(plan)
    return out


def arm_summary(arm: dict, thresholds: list[float]) -> dict:
    row, loop = arm["row"], arm["loop"]
    gates = [r.get("gate") or {} for r in arm["journal"] if r.get("gate") is not None]
    accepted = sum(1 for g in gates if g.get("ok"))
    labels: dict[str, int] = {}
    outcomes: dict[str, int] = {}
    for record in arm["journal"]:
        for key, value in ((record.get("collect_summary") or {}).get("labels") or {}).items():
            labels[key] = labels.get(key, 0) + int(value)
        for key, value in ((record.get("collect_stats") or {}).get("outcomes") or {}).items():
            outcomes[key] = outcomes.get(key, 0) + int(value)
    return {
        "arm": arm["key"], "mode": arm["mode"], "seed": arm["seed"],
        "rounds": row.get("rounds"),
        "consumed_steps": row.get("consumed_steps"),
        "stop_reason": row.get("stop_reason", ""),
        "final_success": row.get("final_success"),
        "final_harsh": row.get("final_harsh"),
        "n_published": row.get("n_published"),
        "published_metrics": row.get("published_metrics", {}),
        "steps_to_threshold": {
            f"{t:g}": steps_to_threshold(arm["curve"], t) for t in thresholds
        },
        "gate_rounds": len(gates),
        "gate_accepted": accepted,
        "gate_accept_rate": round(accepted / len(gates), 3) if gates else None,
        "labels_total": dict(sorted(labels.items(), key=lambda kv: -kv[1])),
        "outcomes_total": dict(sorted(outcomes.items(), key=lambda kv: -kv[1])),
        "intervention": intervention_strength(arm),
        "final_deployed_skill": loop.get("final_deployed_skill", ""),
        "error": row.get("error", ""),
    }


def mode_mean_curve(arms: list[dict], index: int, n_points: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """把同一 mode 的多个 seed 插值到公共网格上取均值（只在所有 seed 都有数据的区间内）。"""
    usable = [a for a in arms if len(a["curve"]) >= 2]
    if not usable:
        return np.zeros(0), np.zeros(0)
    upper = min(max(c[0] for c in a["curve"]) for a in usable)
    grid = np.linspace(0.0, float(upper), n_points)
    stacked = []
    for arm in usable:
        steps = np.array([c[0] for c in arm["curve"]], dtype=float)
        values = np.array([c[index] for c in arm["curve"]], dtype=float)
        stacked.append(np.interp(grid, steps, values))
    return grid, np.mean(np.vstack(stacked), axis=0)


def threshold_verdicts(summaries: list[dict], thresholds: list[float]) -> list[dict]:
    """跨 seed 的阈值判定 —— 结论只认这里，不认单条曲线。

    四种判定（从严到松）：
      · `single_arm_only`        只有一臂有产物（uniform-only 的机理对照 run）-> 不做 A/B 判定
      · `no_resolution`          两臂都有数据、但都没有 seed 达到该阈值 -> 该阈值在本预算下没有分辨力
      · `not_comparable`         达标 seed 数不同 -> 均值不可比（只比达标的等于挑数据）
      · `inconsistent_across_seeds` 每个 seed 都达标，但**快慢方向在 seed 间相反** -> 噪声，不可判定
      · `uniform_faster` / `diagnosed_faster` / `tie`  方向在所有 seed 上一致，才允许这么说
    """
    uni = [s for s in summaries if s["mode"] == "uniform"]
    dia = [s for s in summaries if s["mode"] == "diagnosed"]
    verdicts: list[dict] = []
    if not uni or not dia:
        return verdicts
    seeds = sorted({s["seed"] for s in uni} & {s["seed"] for s in dia})
    for threshold in thresholds:
        key = f"{threshold:g}"
        pairs = []
        for seed in seeds:
            u = next((s for s in uni if s["seed"] == seed), None)
            d = next((s for s in dia if s["seed"] == seed), None)
            if u is None or d is None:
                continue
            pairs.append((seed,
                          (u["steps_to_threshold"] or {}).get(key),
                          (d["steps_to_threshold"] or {}).get(key)))
        entry: dict = {
            "threshold": threshold,
            "n_seeds": len(pairs),
            "uniform_steps": {str(seed): u for seed, u, _ in pairs},
            "diagnosed_steps": {str(seed): d for seed, _, d in pairs},
        }
        reached = [(seed, u, d) for seed, u, d in pairs if u is not None and d is not None]
        u_only = [(seed, u) for seed, u, _ in pairs if u is not None]
        d_only = [(seed, d) for seed, _, d in pairs if d is not None]
        if not pairs:
            entry["verdict"] = "no_data"
        elif not reached and (bool(u_only) != bool(d_only)):
            # 单臂 run（run6 / run7 这类 uniform-only 机理对照）。早先这里会掉进下面的
            # `no_resolution` 分支，印出「两臂都没有 seed 达到」—— 而 uniform 明明每个 seed
            # 都达标了。这是**事实性错误**的输出来自"缺臂被当成 0 分"，比崩溃更危险。
            side, data = (("uniform", u_only) if u_only else ("diagnosed", d_only))
            detail = ", ".join(f"seed{seed}:{steps/1000:.1f}k" for seed, steps in data)
            entry["verdict"] = "single_arm_only"
            entry["text"] = (f"**只有 {side} 一臂有产物**（{len(data)}/{len(pairs)} 个 seed 达标：{detail}）"
                             f" -> 这是单臂机理对照 run，**不做 A/B 快慢判定**；"
                             f"上面那串步数只描述该臂自己的学习速度")
        elif not reached:
            entry["verdict"] = "no_resolution"
            entry["text"] = "两臂都没有 seed 达到 -> 这个阈值在本预算下**无分辨力**，别拿它下结论"
        elif len(reached) != len(pairs):
            entry["verdict"] = "not_comparable"
            entry["text"] = (f"uniform {len([1 for _, u, _ in reached])}/{len(pairs)} 个 seed 达标，"
                             f"diagnosed {len([1 for _, _, d in reached])}/{len(pairs)} 个 seed 达标"
                             f" -> 均值**不可比**（只比达标的等于挑数据）；要么加预算，要么加 seed，"
                             f"要么换更低的阈值")
        else:
            u_mean = float(np.mean([u for _, u, _ in reached]))
            d_mean = float(np.mean([d for _, _, d in reached]))
            entry["uniform_mean"] = round(u_mean, 1)
            entry["diagnosed_mean"] = round(d_mean, 1)
            entry["per_seed_gap_pct"] = {
                str(seed): round((u - d) / max(u, d) * 100, 1) for seed, u, d in reached
            }
            deltas = [u - d for _, u, d in reached]        # >0 = diagnosed 用的步数更少
            gap = abs(u_mean - d_mean) / max(u_mean, d_mean) * 100
            entry["mean_gap_pct"] = round(gap, 1)
            # 只看**有产物**的臂：缺臂的 final_success 是 None，`or 0` 会把它当成 0 分，
            # 于是永远判不出 saturated（run6 三臂全是 1.00 却被漏判）。
            usable = [s for s in summaries if s.get("consumed_steps") is not None]
            saturated = bool(usable) and all((s["final_success"] or 0) >= 0.98
                                             for s in usable)
            if saturated:
                # 两臂都顶到天花板（阶段 3 第一次 A/B 就是这样）：此时「谁快 1%」毫无意义，
                # 因为所有阈值都在同一轮被跨过，比较的是评测噪声而不是学习速度。
                entry["verdict"] = "saturated"
                entry["text"] = ("两臂最终成功率都 >= 0.98（天花板），所有阈值几乎在同一轮被跨过"
                                 " -> 这个 run **无分辨力**，快慢差异没有意义")
            elif gap < TIE_GAP_PCT:
                entry["verdict"] = "tie"
                entry["text"] = f"方向虽一致，但差距只有 {gap:.1f}% < {TIE_GAP_PCT:g}%，在评测噪声量级内 -> 视为打平"
            elif all(delta > 0 for delta in deltas):
                entry["verdict"] = "diagnosed_faster"
            elif all(delta < 0 for delta in deltas):
                entry["verdict"] = "uniform_faster"
            elif all(delta == 0 for delta in deltas):
                entry["verdict"] = "tie"
                entry["text"] = "两臂步数完全相同"
            else:
                entry["verdict"] = "inconsistent_across_seeds"
                entry["text"] = ("每个 seed 都达标，但**快慢方向在 seed 间相反** -> 差异在噪声量级，"
                                 "不可判定")
        verdicts.append(entry)
    return verdicts


VERDICT_TEXT = {
    "uniform_faster": "uniform 更快（**所有 seed 方向一致**）",
    "diagnosed_faster": "diagnosed 更快（**所有 seed 方向一致**）",
}
# 差距小于这个百分比就当作打平：50 局独立评测的标准误约 ±7%，1%~2% 的差异没有物理意义。
TIE_GAP_PCT = 3.0


# --------------------------------------------------------------------------- 画图
def _save(fig, path: Path) -> Path:
    # 多面板图最容易出的问题：上一行的标题压到下一行的 x 轴标签。
    # 保存前统一 tight_layout；如果画了 suptitle（fig.texts 非空）就给它留出顶部空间。
    try:
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93 if fig.texts else 1.0))
    except Exception:
        pass                      # 个别后端/布局失败不该让整张图丢掉
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_learning_curves(run: dict, out_dir: Path, thresholds: list[float],
                         scripted_baseline: float | None) -> Path | None:
    """图 1：A/B 学习曲线（标准条件 + 严酷探针）。细线是单臂，粗线是同 mode 的 seed 均值。"""
    arms = list(run["arms"].values())
    if not arms or not any(a["curve"] for a in arms):
        return None
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.8))
    panels = [(1, "standard eval success rate"), (2, "harsh-probe success rate")]
    for ax, (index, title) in zip(axes, panels):
        for arm in arms:
            curve = arm["curve"]
            if len(curve) < 2:
                continue
            steps = [c[0] for c in curve]
            values = [c[index] for c in curve]
            ax.plot(steps, values, MODE_STYLE.get(arm["mode"], "-"),
                    color=MODE_COLOR.get(arm["mode"], "#333333"),
                    alpha=SEED_ALPHA.get(arm["seed"], 0.4), linewidth=1.3,
                    marker="o", markersize=3,
                    label=f"{arm['mode']} seed{arm['seed']}")
        for mode in ("uniform", "diagnosed"):
            same_mode = [a for a in arms if a["mode"] == mode]
            grid, mean = mode_mean_curve(same_mode, index)
            if len(grid) and len(same_mode) > 1:
                ax.plot(grid, mean, color=MODE_COLOR[mode], linewidth=3.0, alpha=0.95,
                        label=f"{mode} mean (n={len(same_mode)})")
        for threshold in thresholds:
            ax.axhline(threshold, color="#aaaaaa", linewidth=0.8, linestyle=":")
            ax.text(ax.get_xlim()[1], threshold, f" {threshold:g}", va="center",
                    ha="right", fontsize=7.5, color="#888888")
        if scripted_baseline is not None:
            ax.axhline(scripted_baseline, color="#444444", linewidth=1.4, linestyle="-.",
                       label=f"hand-written controller {scripted_baseline:.2f}")
        ax.set_title(title)
        ax.set_xlabel("cumulative env steps")
        ax.set_ylabel("independent-eval success rate")
        ax.set_ylim(-0.03, 1.03)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7.5, loc="lower right")
    fig.suptitle(f"stage-3 A/B learning curves - {run['name']} "
                 f"(budget {run['args'].get('budget_steps')}, "
                 f"{run['args'].get('rounds')} rounds x {run['args'].get('steps_per_round')} steps)",
                 fontsize=10.5)
    return _save(fig, out_dir / "fig_ab_learning_curves.png")


def plot_steps_to_threshold(run: dict, out_dir: Path, thresholds: list[float]) -> Path | None:
    """图 2：达到各阈值所需步数。这是唯一能跨 seed 比较的统计量，也是结论的主证据。"""
    summaries = run["summaries"]
    if not summaries:
        return None
    budget = float(run["args"].get("budget_steps") or 0) or 1.0
    modes = [m for m in ("uniform", "diagnosed") if any(s["mode"] == m for s in summaries)]
    seeds = sorted({s["seed"] for s in summaries})
    fig, ax = plt.subplots(figsize=(11.0, 4.6))
    n_bars = max(1, len(modes) * len(seeds))
    width = 0.8 / n_bars
    for gi, threshold in enumerate(thresholds):
        for bi, mode in enumerate(modes):
            for si, seed in enumerate(seeds):
                match = next((s for s in summaries if s["mode"] == mode and s["seed"] == seed), None)
                if match is None:
                    continue
                value = (match["steps_to_threshold"] or {}).get(f"{threshold:g}")
                slot = gi + (bi * len(seeds) + si) * width - 0.4 + width / 2
                if value is None:
                    ax.bar(slot, budget, width * 0.9, color="#eeeeee", edgecolor="#bbbbbb",
                           hatch="///", linewidth=0.8)
                    ax.text(slot, budget * 1.01, "not\nreached", ha="center", va="bottom",
                            fontsize=7, color="#888888")
                else:
                    ax.bar(slot, value, width * 0.9, color=MODE_COLOR[mode],
                           alpha=SEED_ALPHA.get(seed, 0.5))
                    ax.text(slot, value + budget * 0.012, f"{value/1000:.1f}k", ha="center",
                            va="bottom", fontsize=7.5)
    ax.set_xticks(range(len(thresholds)))
    ax.set_xticklabels([f"reach {t:g}" for t in thresholds])
    ax.set_ylabel("cumulative env steps needed")
    ax.set_title("steps-to-threshold per arm (hatched = never reached within budget)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=MODE_COLOR[m]) for m in modes]
    handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="#eeeeee", edgecolor="#bbbbbb", hatch="///"))
    labels = [f"{m} (dark=seed0, light=seed1)" for m in modes] + ["not reached"]
    ax.legend(handles, labels, fontsize=8, loc="upper left")
    ax.grid(axis="y", alpha=0.25)
    return _save(fig, out_dir / "fig_steps_to_threshold.png")


def plot_failure_labels(run: dict, out_dir: Path) -> Path | None:
    """图 3：每轮采集到的失败标签构成。诊断层的输入就是这张图，先看它有没有信息量。"""
    arms = [a for a in run["arms"].values() if a["journal"]]
    if not arms:
        return None
    ordered = sorted(arms, key=lambda a: (ARM_ORDER.index((a["mode"], a["seed"]))
                                         if (a["mode"], a["seed"]) in ARM_ORDER else 99))
    cols = min(2, len(ordered))
    rows = int(np.ceil(len(ordered) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(6.4 * cols, 3.6 * rows), squeeze=False)
    for ax, arm in zip(axes.ravel(), ordered):
        per_round = [((r.get("collect_summary") or {}).get("labels") or {}) for r in arm["journal"]]
        rounds = [int(r.get("round", i + 1)) for i, r in enumerate(arm["journal"])]
        names = sorted({k for d in per_round for k in d},
                       key=lambda k: (k != "success", k))
        bottom = np.zeros(len(rounds))
        for name in names:
            values = np.array([float(d.get(name, 0)) for d in per_round])
            ax.bar(rounds, values, bottom=bottom, width=0.72,
                   color=LABEL_COLOR.get(name, "#95a5a6"), label=name)
            bottom += values
        ax.set_title(f"{arm['key']} - failure labels per round "
                     f"({int(bottom.sum())} episodes)", fontsize=9.5)
        ax.set_xlabel("round")
        ax.set_ylabel("episodes")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=7, ncol=2)
    for ax in axes.ravel()[len(ordered):]:
        ax.axis("off")
    fig.suptitle("what the diagnoser actually sees (labels come from objective quantities only)",
                 fontsize=10.5)
    return _save(fig, out_dir / "fig_failure_labels_over_rounds.png")


def plot_sampling_weights(run: dict, out_dir: Path) -> Path | None:
    """图 4（本次阴性结果的机理解释）：**实际生效**的采样权重 vs 均匀采样。

    uniform 臂画 0.25 水平线 + 灰色反事实曲线（诊断算了但没用）；
    diagnosed 臂画实际 banded 权重的堆叠面积，并在标题里给出 TV 距离。
    """
    arms = [a for a in run["arms"].values() if a["journal"]]
    if not arms:
        return None
    ordered = sorted(arms, key=lambda a: (ARM_ORDER.index((a["mode"], a["seed"]))
                                         if (a["mode"], a["seed"]) in ARM_ORDER else 99))
    cols = min(2, len(ordered))
    rows = int(np.ceil(len(ordered) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(6.4 * cols, 3.8 * rows), squeeze=False)
    for ax, arm in zip(axes.ravel(), ordered):
        strength = next((s["intervention"] for s in run["summaries"] if s["arm"] == arm["key"]), {})
        weights, rounds, mix = actual_weights(arm)
        plan, plan_rounds = counterfactual_weights(arm)
        if len(weights):
            n_bands = weights.shape[1]
            ax.stackplot(rounds, weights.T, labels=[f"band {i+1}" for i in range(n_bands)],
                         colors=plt.cm.YlOrRd(np.linspace(0.25, 0.85, n_bands)), alpha=0.9)
            ax.axhline(1.0 / n_bands, color="#2f7ed8", linewidth=1.4, linestyle="--",
                       label=f"uniform = {1.0/n_bands:.3f}")
            applied = "banded weights actually applied"
        else:
            n_bands = plan.shape[1] if len(plan) else 4
            ax.axhline(1.0 / n_bands, color="#2f7ed8", linewidth=2.0,
                       label=f"uniform = {1.0/n_bands:.3f} (actually applied)")
            if len(plan):
                ax.plot(plan_rounds, plan.max(axis=1), color="#bbbbbb", linewidth=1.2,
                        linestyle=":", label="diagnosed plan computed but NOT applied (max band)")
            applied = "uniform sampler"
        tv = strength.get("tv_mean")
        # uniform 臂看反事实计划的「钉死 band」，diagnosed 臂看实际权重的
        locked = (strength.get("pinned_bands") or strength.get("counterfactual_pinned_bands") or [])
        ax.set_title(f"{arm['key']} - {applied}\n"
                     f"TV vs uniform = {tv if tv is not None else 'n/a'}"
                     + (f", bands pinned by floor: {locked}" if locked else ""),
                     fontsize=9.0)
        ax.set_xlabel("round")
        ax.set_ylabel("sampling weight")
        ax.set_ylim(0, 1.0)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7, loc="upper right")
    for ax in axes.ravel()[len(ordered):]:
        ax.axis("off")
    fig.suptitle("how far diagnosis actually pushed the training distribution "
                 f"(mix_uniform={run['args'].get('mix_uniform', 0.25)})", fontsize=10.5)
    return _save(fig, out_dir / "fig_sampling_weights_over_rounds.png")


def plot_gate_timeline(run: dict, out_dir: Path) -> Path | None:
    """图 5：门禁时间线。绿=放行、红=拒绝；阶跃线是当时的现任（incumbent）。"""
    arms = [a for a in run["arms"].values() if a["journal"]]
    if not arms:
        return None
    ordered = sorted(arms, key=lambda a: (ARM_ORDER.index((a["mode"], a["seed"]))
                                         if (a["mode"], a["seed"]) in ARM_ORDER else 99))
    cols = min(2, len(ordered))
    rows = int(np.ceil(len(ordered) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(6.4 * cols, 3.6 * rows), squeeze=False)
    for ax, arm in zip(axes.ravel(), ordered):
        rounds, cand, harsh, incumbent, accepted = [], [], [], [], []
        for record in arm["journal"]:
            gate = record.get("gate")
            metrics = record.get("candidate_metrics")
            if not isinstance(gate, dict) or not isinstance(metrics, dict):
                continue
            rounds.append(int(record.get("round", 0)))
            cand.append(float(metrics.get("success_rate", 0.0)))
            harsh.append(float(metrics.get("harsh_success_rate", 0.0)))
            inc = record.get("incumbent_metrics") or {}
            incumbent.append(float(inc.get("success_rate", 0.0)))
            accepted.append(bool(gate.get("ok")))
        if not rounds:
            ax.axis("off")
            continue
        ax.step(rounds, incumbent, where="post", color="#444444", linewidth=1.6,
                label="incumbent (deployed)")
        ok = [r for r, a in zip(rounds, accepted) if a]
        bad = [r for r, a in zip(rounds, accepted) if not a]
        ax.scatter(ok, [c for c, a in zip(cand, accepted) if a], s=52, color="#3aa657",
                   edgecolor="#1d6b36", zorder=3, label="published")
        ax.scatter(bad, [c for c, a in zip(cand, accepted) if not a], s=52, color="#e0524d",
                   zorder=3, marker="x", linewidths=1.8, label="rejected")
        ax.scatter(rounds, harsh, s=18, color="#8e44ad", alpha=0.75, zorder=2,
                   label="harsh-probe score")
        rate = (len(ok) / len(rounds)) if rounds else 0.0
        ax.set_title(f"{arm['key']} - gate decisions "
                     f"({len(ok)}/{len(rounds)} published = {rate:.0%})", fontsize=9.5)
        ax.set_xlabel("round")
        ax.set_ylabel("independent-eval success rate")
        ax.set_ylim(-0.03, 1.03)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7, loc="lower right")
    for ax in axes.ravel()[len(ordered):]:
        ax.axis("off")
    fig.suptitle("publish gate timeline (candidate vs incumbent, standard + harsh probe)",
                 fontsize=10.5)
    return _save(fig, out_dir / "fig_gate_timeline.png")


def plot_recovery_paths(run: dict, out_dir: Path) -> Path | None:
    """图 6：行为树每条路径实际被走了多少次。没走过的路径等于没测过。"""
    arms = [a for a in run["arms"].values() if a["journal"]]
    if not arms:
        return None
    ordered = sorted(arms, key=lambda a: (ARM_ORDER.index((a["mode"], a["seed"]))
                                         if (a["mode"], a["seed"]) in ARM_ORDER else 99))
    cols = min(2, len(ordered))
    rows = int(np.ceil(len(ordered) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(6.4 * cols, 3.4 * rows), squeeze=False)
    for ax, arm in zip(axes.ravel(), ordered):
        per_round = [((r.get("collect_stats") or {}).get("outcomes") or {}) for r in arm["journal"]]
        rounds = [int(r.get("round", i + 1)) for i, r in enumerate(arm["journal"])]
        names = sorted({k for d in per_round for k in d},
                       key=lambda k: (k not in ("forward_success", "backward_success"), k))
        bottom = np.zeros(len(rounds))
        for name in names:
            values = np.array([float(d.get(name, 0)) for d in per_round])
            ax.bar(rounds, values, bottom=bottom, width=0.72,
                   color=OUTCOME_COLOR.get(name, "#95a5a6"), label=name)
            bottom += values
        takeover = sum(int(d.get("takeover", 0)) for d in per_round)
        ax.set_title(f"{arm['key']} - behaviour-tree paths per round "
                     f"(takeover total {takeover})", fontsize=9.5)
        ax.set_xlabel("round")
        ax.set_ylabel("task rounds")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=7, ncol=2)
    for ax in axes.ravel()[len(ordered):]:
        ax.axis("off")
    fig.suptitle("which harness paths were actually exercised", fontsize=10.5)
    return _save(fig, out_dir / "fig_recovery_paths.png")


def plot_budget_and_cost(run: dict, out_dir: Path) -> Path | None:
    """图 7：预算记账。左=累计环境步数（对齐预算），右=每轮训练吞吐与耗时。"""
    arms = [a for a in run["arms"].values() if a["journal"]]
    if not arms:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 4.2))
    budget = float(run["args"].get("budget_steps") or 0)
    for arm in arms:
        rounds = [int(r.get("round", i + 1)) for i, r in enumerate(arm["journal"])]
        consumed = [int(r.get("consumed_steps", 0)) for r in arm["journal"]]
        if rounds:
            axes[0].plot(rounds, consumed, MODE_STYLE.get(arm["mode"], "-"),
                         color=MODE_COLOR.get(arm["mode"], "#333333"),
                         alpha=SEED_ALPHA.get(arm["seed"], 0.4), linewidth=1.6,
                         marker="o", markersize=3, label=arm["key"])
    if budget:
        axes[0].axhline(budget, color="#444444", linestyle="-.", linewidth=1.3,
                        label=f"budget {budget:.0f}")
    axes[0].set_title("budget accounting: cumulative env steps per round")
    axes[0].set_xlabel("round")
    axes[0].set_ylabel("cumulative env steps")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=7.5)

    throughput, wall = [], []
    for arm in arms:
        for record in arm["journal"]:
            train = record.get("train") or {}
            if train.get("steps_per_sec"):
                throughput.append(float(train["steps_per_sec"]))
            if train.get("train_seconds"):
                wall.append(float(train["train_seconds"]))
    if throughput:
        axes[1].hist(throughput, bins=18, color="#3aa657", alpha=0.85,
                     label=f"train steps/s (n={len(throughput)})")
        axes[1].axvline(float(np.median(throughput)), color="#1d6b36", linestyle="--",
                        label=f"median {np.median(throughput):.0f} steps/s")
    if wall:
        sec = axes[1].twinx()
        sec.hist(wall, bins=18, color="#e8a33d", alpha=0.45,
                 label=f"wall-clock s/round (n={len(wall)})")
        sec.set_ylabel("wall-clock seconds per round", color="#b5762a")
    axes[1].set_title("training cost per round (CPU, 1 thread)")
    axes[1].set_xlabel("train steps/s")
    axes[1].set_ylabel("rounds")
    axes[1].grid(alpha=0.25)
    handles, labels = axes[1].get_legend_handles_labels()
    axes[1].legend(handles, labels, fontsize=7.5, loc="upper right")
    return _save(fig, out_dir / "fig_budget_and_cost.png")


# --------------------------------------------------------------------------- 终端输出
def print_report(run: dict, thresholds: list[float], figures: list[Path]) -> None:
    summaries = run["summaries"]
    print("=" * 96)
    print(f"阶段 3 A/B 可视化 · {run['run_dir']}")
    print("=" * 96)
    args = run["args"]
    print(f"  预算 {args.get('budget_steps')} 步 · 每轮 {args.get('steps_per_round')} 步 · "
          f"{args.get('episodes')} 局/轮 · 最多 {args.get('rounds')} 轮 · "
          f"独立评测 {args.get('eval_episodes')} 局(seed {args.get('eval_seed', 999)})")
    print(f"  环境 {args.get('config')} · init={args.get('init')} · deploy={args.get('deploy')}")
    if run["note"]:
        print(f"  note: {run['note']}")

    header = f"{'arm':16s}{'rounds':>7s}{'steps':>9s}{'final':>7s}{'harsh':>7s}{'pub':>5s}{'gate%':>7s}"
    for t in thresholds:
        header += f"{f'reach{t:g}':>10s}"
    print("\n" + header)
    print("-" * len(header))
    def cell(value, fmt: str, placeholder: str = "—") -> str:
        """缺臂（没有 loop_result.json）时字段是 None，不能直接套数字格式。

        早先这里写的是 `s['rounds']:>7d`，在 uniform-only 的 run（run6 / run7 都只有
        uniform 臂）上直接 TypeError 崩掉整份报告；而 `(s['final_success'] or 0)` 更糟——
        它把「没有这一臂」印成 0.00，看起来像"这一臂彻底失败"。
        """
        return format(value, fmt) if value is not None else f"{placeholder:>{len(format(0, fmt))}}"

    missing = [s["arm"] for s in summaries if s.get("consumed_steps") is None]
    for s in summaries:
        gate = s["gate_accept_rate"]
        line = (f"{s['arm']:16s}{cell(s['rounds'], '>7d')}{cell(s['consumed_steps'], '>9d')}"
                f"{cell(s['final_success'], '>7.2f')}{cell(s['final_harsh'], '>7.2f')}"
                f"{cell(s['n_published'], '>5d')}"
                f"{(format(gate * 100, '>6.0f') + '%') if gate is not None else '     —':>7s}")
        for t in thresholds:
            value = (s["steps_to_threshold"] or {}).get(f"{t:g}")
            line += f"{(f'{value/1000:.1f}k' if value is not None else 'n.r.'):>10s}"
        print(line)
    if missing:
        print(f"  注：{len(missing)} 条臂没有产物（{', '.join(missing)}），表中以「—」显示。"
              f"uniform-only 的机理对照 run 属于正常情况，不是失败。")

    print("\n  干预强度（诊断到底把**实际**采样分布推离均匀多少）：")
    print(f"    {'arm':16s}{'实际采样器':>12s}{'实际TV均值':>12s}{'反事实TV':>10s}{'几乎没动过的band':>18s}")
    for s in summaries:
        iv = s["intervention"]
        kinds = "/".join(iv.get("sampler_kind") or ["?"])
        pinned = iv.get("pinned_bands") or iv.get("counterfactual_pinned_bands") or []
        counterfactual = iv.get("counterfactual_tv_mean")
        print(f"    {s['arm']:16s}{kinds:>12s}{(iv.get('tv_mean') or 0.0):>12.3f}"
              f"{(f'{counterfactual:.3f}' if counterfactual is not None else 'n/a'):>10s}"
              f"{str(pinned):>18s}")
    print("    注：TV = 0.5*Σ|p_实际 - p_均匀|，0 表示与均匀采样无区别。")
    print("        uniform 臂的**实际** TV 恒为 0；「反事实 TV」是 sampling_plan 的值 ——")
    print("        它被算出来并写进 journal，但 train.sampler.kind=uniform，**没有生效**。")

    print("\n  失败标签总量 / 行为树路径总量：")
    for s in summaries:
        labels = ", ".join(f"{k}={v}" for k, v in list(s["labels_total"].items())[:5])
        outcomes = ", ".join(f"{k}={v}" for k, v in list(s["outcomes_total"].items())[:5])
        print(f"    {s['arm']:16s} labels: {labels}")
        print(f"    {'':16s} paths : {outcomes}")

    print("\n  生成的图：")
    for path in figures:
        print(f"    {path.relative_to(REPO_ROOT)}")
    print()


def print_reading_guide(run: dict) -> None:
    """把「这几张图该怎么读」直接打在终端里，避免图存下来没人看得懂。

    这里刻意做了一件反直觉的事：**当两臂「达标的 seed 数」不一样时，拒绝给出快慢比较**。
    只拿达标的那些 seed 求均值，等于自动把「没达标」当成「很慢但不计入」，
    这正是阶段 3 第一版结论（只看 seed=0、按 60%/75% 阈值挑）出错的地方。
    """
    summaries = run["summaries"]
    uni = [s for s in summaries if s["mode"] == "uniform"]
    dia = [s for s in summaries if s["mode"] == "diagnosed"]
    print("-" * 96)
    print("怎么读（结论以本 run 实测为准）：")

    def fmt_steps(values) -> str:
        shown = ", ".join(f"seed{k}:{(f'{v/1000:.1f}k' if v is not None else 'n.r.')}"
                          for k, v in sorted((values or {}).items(), key=lambda kv: int(kv[0])))
        return shown or "无"

    for entry in run.get("verdicts", []):
        verdict = entry.get("verdict", "no_data")
        head = f"  · 达到 {entry['threshold']:g}（{entry.get('n_seeds', 0)} 个 seed 配对）: "
        if verdict == "single_arm_only":
            # 单臂 run 说「N 个 seed 配对」是错的（没有配对），表头单独写。
            print(f"  · 达到 {entry['threshold']:g}: " + entry.get("text", verdict))
            print(f"      逐 seed: uniform [{fmt_steps(entry['uniform_steps'])}] · "
                  f"diagnosed [{fmt_steps(entry['diagnosed_steps'])}]")
        elif verdict in VERDICT_TEXT:
            print(head + f"uniform 均值 {entry['uniform_mean']/1000:.1f}k vs "
                         f"diagnosed 均值 {entry['diagnosed_mean']/1000:.1f}k -> "
                         f"{VERDICT_TEXT[verdict]}，差 {entry['mean_gap_pct']:.0f}%")
            print(f"      逐 seed: uniform [{fmt_steps(entry['uniform_steps'])}] · "
                  f"diagnosed [{fmt_steps(entry['diagnosed_steps'])}] · "
                  f"gap% {entry.get('per_seed_gap_pct')}")
        elif verdict == "inconsistent_across_seeds":
            print(head + f"uniform 均值 {entry['uniform_mean']/1000:.1f}k vs "
                         f"diagnosed 均值 {entry['diagnosed_mean']/1000:.1f}k，"
                         f"但 {entry['text']}")
            print(f"      逐 seed: uniform [{fmt_steps(entry['uniform_steps'])}] · "
                  f"diagnosed [{fmt_steps(entry['diagnosed_steps'])}] · "
                  f"gap% {entry.get('per_seed_gap_pct')}（正号=diagnosed 更快，符号不一致）")
        elif verdict in ("no_resolution", "not_comparable", "saturated", "tie"):
            print(head + entry.get("text", verdict))
            print(f"      逐 seed: uniform [{fmt_steps(entry['uniform_steps'])}] · "
                  f"diagnosed [{fmt_steps(entry['diagnosed_steps'])}]")
        else:
            print(head + f"数据不足（{verdict}）")
    dia_tv = [s["intervention"]["tv_mean"] for s in dia
              if s["intervention"].get("applied") == "banded"]
    uni_cf = [s["intervention"].get("counterfactual_tv_mean") for s in uni]
    uni_cf = [x for x in uni_cf if x is not None]
    if dia_tv:
        print(f"  · diagnosed 臂的**实际**干预强度：TV = {float(np.mean(dia_tv)):.3f}"
              f"（0 = 与均匀采样无区别）。干预这么弱，测不出加速是预期结果，"
              f"**不能**反过来当成「诊断思路无效」的证据。")
    if uni_cf:
        print(f"  · uniform 臂里诊断同样会算出计划（反事实 TV = {float(np.mean(uni_cf)):.3f}），"
              f"但没有生效 —— 两臂的唯一差别就是这个开关，对照是干净的。")
    pinned = {tuple(s["intervention"].get("pinned_bands") or []) for s in dia}
    pinned = sorted(p for p in pinned if p)
    if pinned:
        print(f"  · 被 floor 钉死、整场几乎没动过的距离带：{[list(p) for p in pinned]}"
              f" -> 所谓「针对性」只发生在剩下的 band 之间，这是干预弱的直接原因。")
    print("  · 门禁图里绿点少于红点是正常的：门禁是保守的，宁可不发布也不回退。")
    print("  · 单条曲线的上下跳动幅度（±0.1 量级）就是 50 局评测的噪声，"
          "不要把单点差异当结论；跨 seed 一致的才算。")
    print("-" * 96)


# --------------------------------------------------------------------------- CLI
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="阶段 3 A/B 闭环产物可视化")
    parser.add_argument("--run", action="append", default=[],
                        help="A/B 产物目录（含 compare.json），可重复")
    parser.add_argument("--latest", action="store_true", help="自动挑最新的一次 A/B")
    parser.add_argument("--out", default="", help="图片输出目录，默认 <run>/figures")
    parser.add_argument("--thresholds", default="0.5,0.6,0.75,0.8",
                        help="逗号分隔的成功率阈值，用于 steps-to-threshold")
    parser.add_argument("--scripted-baseline", type=float, default=0.94,
                        help="手写比例控制器基线（画参考线）；传 <=0 或 nan 关闭")
    parser.add_argument("--no-guide", action="store_true", help="不打印读图指引")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]
    run_dirs: list[Path] = []
    for item in args.run:
        path = Path(item)
        run_dirs.append(path if path.is_absolute() else REPO_ROOT / path)
    if args.latest or not run_dirs:
        latest = find_latest_run()
        if latest is None:
            print("[错误] runs/ab_stage3/ 下找不到含 compare.json 的产物。先跑 "
                  "scripts/compare_harness_ab.py")
            return 2
        if latest not in run_dirs:
            run_dirs.append(latest)

    scripted = None
    if args.scripted_baseline and args.scripted_baseline > 0:
        scripted = float(args.scripted_baseline)

    exit_code = 0
    for run_dir in run_dirs:
        run = load_run(run_dir)
        if run is None:
            exit_code = 1
            continue
        run["summaries"] = [arm_summary(arm, thresholds) for arm in run["arms"].values()]
        run["summaries"].sort(key=lambda s: (ARM_ORDER.index((s["mode"], s["seed"]))
                                            if (s["mode"], s["seed"]) in ARM_ORDER else 99))
        run["verdicts"] = threshold_verdicts(run["summaries"], thresholds)
        out_dir = Path(args.out) if args.out else run_dir / "figures"
        if not out_dir.is_absolute():
            out_dir = REPO_ROOT / out_dir
        figures: list[Path] = []
        for drawer in (
            lambda: plot_learning_curves(run, out_dir, thresholds, scripted),
            lambda: plot_steps_to_threshold(run, out_dir, thresholds),
            lambda: plot_failure_labels(run, out_dir),
            lambda: plot_sampling_weights(run, out_dir),
            lambda: plot_gate_timeline(run, out_dir),
            lambda: plot_recovery_paths(run, out_dir),
            lambda: plot_budget_and_cost(run, out_dir),
        ):
            try:
                path = drawer()
            except Exception as error:                     # 单张图挂掉不该拖垮其余的
                print(f"[警告] {drawer.__name__ if hasattr(drawer,'__name__') else 'plot'} 失败: {error}")
                continue
            if path is not None:
                figures.append(path)
        summary_path = out_dir / "stage3_summary.json"
        out_dir.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps({
            "run_dir": str(run["run_dir"]),
            "timestamp": run["compare"].get("timestamp", ""),
            "args": run["args"],
            "thresholds": thresholds,
            "scripted_baseline": scripted,
            "arms": run["summaries"],
            "threshold_verdicts": run.get("verdicts", []),
            "figures": [str(p.relative_to(REPO_ROOT)) for p in figures],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        figures.append(summary_path)
        print_report(run, thresholds, figures)
        if not args.no_guide:
            print_reading_guide(run)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
