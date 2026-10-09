#!/usr/bin/env python
"""把阶段 2 的结果画成图：覆盖热力图、可靠度扫描、学习曲线。

终端表格只能告诉你「36 格 vs 20 格」，图能回答表格答不了的三个问题：

    1. 塌缩发生在**哪块区域**？              -> fig_coverage_heatmaps.png
    2. 塌缩随策略可靠度怎么变化？            -> fig_reliability_scan.png
    3. 训练过程中覆盖是涨还是掉？            -> fig_learning_curves.png

第 1 张图最重要：它把「请求的目标」「实际经历的起始状态」「真正做到的放置」
三种分布并排画出来。你会看到目标格子铺满整张桌面，而起始格子缩到几个格子里——
这就是「交替 != 遍历」的可视化证据。

注意：本机没有中文字体，所以**图里的标签一律用英文**，中文解释放在终端输出和 docs 里。

用法：
    python scripts/plot_stage2.py --compare runs/20260922_205020_stage2_compare
    python scripts/plot_stage2.py --train runs/xxx_sac_transport_alternate
    python scripts/plot_stage2.py --train runs/xxx_alternate --train runs/xxx_fixed   # 两条课程叠加
    python scripts/plot_stage2.py --latest              # 自动挑最新的 compare + train
    python scripts/plot_stage2.py --latest --open       # 顺便打印每张图的解读
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

MODE_COLOR = {"alternate": "#2f7ed8", "fixed": "#e8a33d"}
# pd / pd_biased = 带速度反馈的脚本基线（扰动环境下它才是「不学习的天花板」）
POLICY_MARK = {"perfect": "o", "biased": "s", "random": "^", "ckpt": "D",
               "pd": "v", "pd_biased": "P"}


# --------------------------------------------------------------------------- 工具
def find_latest(pattern: str, marker: str) -> Path | None:
    candidates = [p for p in sorted((REPO_ROOT / "runs").glob(pattern)) if (p / marker).exists()]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def counts_to_grid(counts: dict, grid_n: int) -> np.ndarray:
    """把 {"i,j": n} 还原成 grid_n x grid_n 的矩阵。

    返回的矩阵下标是 [y][x]，配合 imshow(origin="lower") 就是「x 向右、y 向上」，
    和环境里的坐标方向一致（画反了会误判塌缩发生在哪半边）。
    """
    grid = np.zeros((grid_n, grid_n), dtype=np.float64)
    for key, value in (counts or {}).items():
        i, j = (int(x) for x in str(key).split(","))
        if 0 <= i < grid_n and 0 <= j < grid_n:
            grid[j, i] += float(value)
    return grid


def draw_cell_heatmap(ax, grid: np.ndarray, title: str, half: float, gap: float,
                      colormap: str = "Blues") -> float:
    """画一张格子热力图，并把 A/B 两个区域的分界线标出来。"""
    peak = float(grid.max())
    ax.imshow(grid, origin="lower", cmap=colormap, vmin=0.0, vmax=peak if peak > 0 else 1.0,
              extent=[-half, half, -half, half])
    n = grid.shape[0]
    # 索引 -> 物理坐标：cell i 覆盖 [-half + i*w, -half + (i+1)*w]
    width = 2 * half / n
    for boundary in (-gap, gap):
        ax.axvline(boundary, color="#666666", linestyle=":", linewidth=1.0)
    ax.axvline(0.0, color="#bbbbbb", linestyle="-", linewidth=0.6)
    ax.set_title(title, fontsize=9)
    ax.set_xticks([-half, 0, half])
    ax.set_yticks([-half, 0, half])
    ax.set_xticklabels([f"{-half * 100:.0f}", "0", f"{half * 100:.0f}"], fontsize=7)
    ax.set_yticklabels([f"{-half * 100:.0f}", "0", f"{half * 100:.0f}"], fontsize=7)
    ax.text(-half + width * 0.2, half - width * 0.4, "A", fontsize=8, color="#666666")
    ax.text(half - width * 0.8, half - width * 0.4, "B", fontsize=8, color="#666666")
    return peak


# --------------------------------------------------------------------------- compare 图
def plot_coverage_heatmaps(payload: dict, out_dir: Path, recovery: str) -> Path | None:
    """行 = 策略 x 复位模式，列 = 请求的目标 / 经历的起始 / 做到的放置。"""
    results = payload["results"]
    cfg = payload["config"]
    grid_n, half, gap = int(cfg["grid_n"]), float(cfg["half"]), float(cfg["gap"])
    kinds = []
    for key in results:
        kind = key.split("|")[0]
        if kind not in kinds:
            kinds.append(kind)
    modes = [m for m in ("alternate", "fixed") if any(f"|{m}|{recovery}" in k for k in results)]
    rows = [(kind, mode) for kind in kinds for mode in modes if f"{kind}|{mode}|{recovery}" in results]
    if not rows:
        return None

    columns = [("goal_cell_counts", "requested goals (exogenous)", "Purples"),
               ("start_cell_counts", "experienced starts", "Blues"),
               ("place_cell_counts", "achieved placements", "Greens")]
    fig, axes = plt.subplots(len(rows), len(columns),
                             figsize=(3.0 * len(columns), 2.7 * len(rows)), squeeze=False)
    for r, (kind, mode) in enumerate(rows):
        mean = results[f"{kind}|{mode}|{recovery}"]["mean"]
        for c, (field, label, cmap) in enumerate(columns):
            ax = axes[r][c]
            grid = counts_to_grid(mean.get(field, {}), grid_n)
            peak = draw_cell_heatmap(ax, grid, "", half, gap, cmap)
            n_vis = int(grid[grid > 0].size)
            ax.set_ylabel(f"{kind}\n{mode}", fontsize=8)
            ax.text(0.02, 0.05, f"{n_vis}/{grid_n * grid_n} cells\npeak {peak:.0f}",
                    transform=ax.transAxes, fontsize=7, va="bottom",
                    bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1.5))
            if c == 1:
                ax.set_xlabel(f"start entropy {mean['entropy_start']:.3f}", fontsize=8)
            elif c == 0:
                ax.set_xlabel(f"goal entropy {mean['entropy_goal']:.3f}", fontsize=8)
            else:
                ax.set_xlabel(f"place entropy {mean['entropy_place']:.3f}", fontsize=8)
            if r == 0:
                ax.set_title(label, fontsize=10)
    fig.suptitle(f"Stage 2 coverage maps (recovery={recovery}) - requested vs experienced vs achieved",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    path = out_dir / f"fig_coverage_heatmaps_{recovery}.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def plot_cost_bars(payload: dict, out_dir: Path, recovery: str) -> Path | None:
    """Q1 的图：复位成本与吞吐，按 策略 x 模式 分组。"""
    results = payload["results"]
    keys = [k for k in results if k.endswith(f"|{recovery}")]
    if not keys:
        return None
    labels = [k.replace(f"|{recovery}", "").replace("|", " / ") for k in keys]
    resets = [results[k]["mean"]["total_resets"] for k in keys]
    thr = [results[k]["mean"]["throughput_per_1k"] for k in keys]
    tasks = [results[k]["mean"]["tasks_done"] for k in keys]
    colors = [MODE_COLOR.get(k.split("|")[1], "#888888") for k in keys]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    for ax, values, title, ylabel in (
        (axes[0], tasks, "Tasks completed (same step budget)", "tasks"),
        (axes[1], resets, "Total resets paid (fixed + stall recovery)", "resets"),
        (axes[2], thr, "Throughput incl. reset cost", "tasks / 1k effective steps"),
    ):
        ax.bar(range(len(values)), values, color=colors)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(axis="y", alpha=0.3)
        for i, v in enumerate(values):
            ax.text(i, v, f"{v:.0f}" if v >= 10 else f"{v:.1f}", ha="center", va="bottom", fontsize=8)
    handles = [plt.Rectangle((0, 0), 1, 1, color=MODE_COLOR["alternate"]),
               plt.Rectangle((0, 0), 1, 1, color=MODE_COLOR["fixed"])]
    fig.legend(handles, ["alternate (reset-free)", "fixed (human reset each task)"],
               loc="upper center", ncol=2, fontsize=9)
    fig.suptitle(f"Stage 2 Q1: is alternating cheaper? (recovery={recovery})", fontsize=11, y=1.04)
    fig.tight_layout()
    path = out_dir / f"fig_cost_bars_{recovery}.png"
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_reliability_scan(payload: dict, out_dir: Path) -> Path | None:
    """Q2 的因果版：把策略可靠度扫一遍，看两种模式的起始状态多样性怎么分岔。"""
    scan = payload.get("scan") or []
    if not scan:
        return None
    recoveries = []
    for row in scan:
        if row["recovery"] not in recoveries:
            recoveries.append(row["recovery"])

    fig, axes = plt.subplots(1, 2 * len(recoveries), figsize=(5.0 * 2 * len(recoveries), 4.2),
                             squeeze=False)
    for ci, recovery in enumerate(recoveries):
        rows = [r for r in scan if r["recovery"] == recovery]
        for mode in ("alternate", "fixed"):
            sel = sorted([r for r in rows if r["mode"] == mode], key=lambda r: r["success_rate"])
            if not sel:
                continue
            x = [r["success_rate"] * 100 for r in sel]
            color = MODE_COLOR[mode]
            axes[0][ci * 2].plot(x, [r["entropy_start"] for r in sel], marker="o", color=color,
                                 label=mode)
            axes[0][ci * 2 + 1].plot(x, [r["total_resets"] for r in sel], marker="s", color=color,
                                     label=mode)
        for ax, title, ylab in ((axes[0][ci * 2], "Start-state diversity vs policy reliability",
                                 "normalized start entropy"),
                                (axes[0][ci * 2 + 1], "Reset cost vs policy reliability",
                                 "total resets per 20k steps")):
            ax.set_title(f"{title}\n(recovery={recovery})", fontsize=9)
            ax.set_xlabel("task success rate (%)", fontsize=9)
            ax.set_ylabel(ylab, fontsize=9)
            ax.grid(alpha=0.3)
            ax.legend(fontsize=8)
    fig.suptitle("Stage 2 Q2: alternating != covering - the gap depends on how reliable the policy is",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    path = out_dir / "fig_reliability_scan.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- train 图
def load_train(run_dir: Path) -> dict | None:
    npz_path = run_dir / "evaluations_transport.npz"
    if not npz_path.exists():
        return None
    data = dict(np.load(npz_path))
    result_path = run_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    return {"npz": data, "result": result, "dir": run_dir}


def plot_learning_curves(runs: list[dict], out_dir: Path) -> Path | None:
    """四联图：任务数 / 成功率与正反向 / 救场次数 / 起始覆盖与熵。"""
    runs = [r for r in runs if r is not None]
    if not runs:
        return None
    tags = [r["result"].get("reset_mode") or r["dir"].name for r in runs]
    if len(set(tags)) < len(tags):
        # 同一复位模式叠多条曲线时，用 run 目录名里剩下的片段区分（去掉时间戳和公共词）
        tags = [f"{t} [{_run_tag(r['dir'].name)}]" for t, r in zip(tags, runs)]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    panels = [
        (axes[0][0], [("tasks_per_1k_steps", "tasks / 1k steps")], "Throughput during training"),
        (axes[0][1], [("success_rate", "task success rate"),
                      ("endogenous_start_share", "endogenous start share")],
         "Success rate & self-generated starts"),
        (axes[1][0], [("manual_resets", "stall recoveries")], "Rule-based recovery triggers"),
        (axes[1][1], [("start_cells", "distinct start cells"), ("entropy_start", "start entropy")],
         "Start-state coverage"),
    ]
    for ax, series, title in panels:
        for i, (run, color) in enumerate(zip(runs, ("#2f7ed8", "#e8a33d", "#8bbc21", "#954e75"))):
            data = run["npz"]
            steps = data["timesteps"]
            label = tags[i]
            for key, _ylab in series:
                if key not in data:
                    continue
                linestyle = "-" if series.index((key, _ylab)) == 0 else "--"
                ax.plot(steps, data[key], linestyle=linestyle, color=color, marker="o",
                        markersize=3, linewidth=1.3, label=f"{label}: {key}")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("training steps", fontsize=9)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7)
    fig.suptitle("Stage 2 learning curves (in-training frozen evaluation)", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    # 单条曲线 -> fig_learning_curves.png；多条叠加 -> 另起一个名字，别把单条的覆盖掉
    path = out_dir / ("fig_learning_curves.png" if len(runs) == 1 else "fig_learning_curves_both.png")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _run_tag(name: str) -> str:
    parts = [p for p in name.split("_")[2:] if p not in ("sac", "transport", "smoke")]
    return "_".join(parts) or name


def plot_forward_backward(run: dict, out_dir: Path) -> Path | None:
    """偏科检查：正向和反向的成功数是不是同步上涨。"""
    data = run["npz"]
    if "success_forward" not in data:
        return None
    fig, ax = plt.subplots(figsize=(7, 4.2))
    steps = data["timesteps"]
    ax.plot(steps, data["success_forward"], marker="o", markersize=3, color="#2f7ed8",
            label="forward (A->B)")
    ax.plot(steps, data["success_backward"], marker="s", markersize=3, color="#e8537d",
            label="backward (B->A)")
    ax.set_title("Forward vs backward successes during training", fontsize=10)
    ax.set_xlabel("training steps", fontsize=9)
    ax.set_ylabel("tasks completed per eval budget", fontsize=9)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = out_dir / "fig_forward_backward.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def plot_two_curricula(runs: list[dict], out_dir: Path) -> Path | None:
    """两条课程（alternate / fixed）的最终冻结评测对比。"""
    runs = [r for r in runs if r is not None and r["result"].get("eval")]
    if len(runs) < 2:
        return None
    metrics = [("tasks_done", "tasks done"), ("success_rate", "success rate"),
               ("start_cells", "start cells"), ("entropy_start", "start entropy"),
               ("total_resets", "total resets"), ("throughput_per_1k", "throughput/1k")]
    labels = [f"{r['result'].get('reset_mode')}\n({r['dir'].name.split('_')[-1]})" for r in runs]
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.5))
    for ax, (key, title) in zip(axes.ravel(), metrics):
        for run, color in zip(runs, ("#2f7ed8", "#e8a33d", "#8bbc21")):
            mode = run["result"].get("reset_mode", "?")
            values = [run["result"]["eval"]["trained_model"]["mean"].get(key, 0.0)]
            cross = run["result"]["eval"].get("cross_mode", {})
            for other, rep in cross.items():
                values.append(rep["mean"].get(key, 0.0))
            names = [f"train {mode}"] + [f"test {k}" for k in cross]
            ax.bar([f"{n}" for n in names], values, color=color, alpha=0.85,
                   label=f"policy trained in {mode}")
            ax.set_xticks(range(len(names)))
            ax.set_xticklabels(names, fontsize=7, rotation=20, ha="right")
        ax.set_title(title, fontsize=9)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Stage 2: does the training curriculum (alternate vs fixed) change the policy?",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    path = out_dir / "fig_two_curricula.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- 解读
EXPLAIN = {
    "fig_coverage_heatmaps": """
  怎么看 fig_coverage_heatmaps_*.png：
    · 每一行是一种 (策略, 复位模式)，三列分别是「环境请求的目标」「策略实际经历的起始状态」
      「策略真正做到的放置」。颜色越深 = 访问次数越多，白格 = 从没发生过。
    · random / biased 行的第 2 列（起始状态）如果只剩几个格子，而第 1 列（请求目标）铺满，
      那就是「交替 != 遍历」的直接证据：环境要求它到处做，它却只在几个位置练习。
    · perfect 行三列都应该铺满 -> 说明塌缩不是交替机制造成的，而是策略不可靠造成的。
    · 灰色虚线是 A/B 区分界（中间 4cm 是无人区）。""",
    "fig_reliability_scan": """
  怎么看 fig_reliability_scan.png：
    · 横轴是策略的任务成功率（= 可靠度），纵轴左图是起始状态分布熵、右图是付出的复位次数。
    · 蓝线（alternate）在左图低于橙线（fixed）-> 交替确实让起始状态多样性变差；
      两条线的差距随可靠度上升而缩小 -> 策略越可靠，交替的代价越小。
    · 右图蓝线始终低于橙线 -> 交替始终更省复位。
    · 结论一句话：交替省的是复位成本，付的是起始状态多样性，汇率由策略可靠度决定。""",
    "fig_learning_curves": """
  怎么看 fig_learning_curves.png：
    · 左上：吞吐（每千步完成多少个 task）。这是最该涨的曲线。
    · 右上：成功率，以及「内生起始占比」（出发点由上一轮放置点决定的比例）。
      后者涨起来说明交替链条真的接上了：策略开始自己给自己造下一轮的初始状态。
    · 左下：规则式救场触发次数。策略变强，这条应该往下掉——掉不下去说明它在某些
      位置始终搞不定，正好对应热力图里的空白格。
    · 右下：起始格子数与熵。如果吞吐涨了但这条掉了，就是「学会了、但学窄了」，
      这正是 reset-free 自学习最需要警惕的失败模式。""",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--compare", default="", help="compare_reset_modes.py 的 run 目录")
    parser.add_argument("--train", action="append", default=[], help="train_transport.py 的 run 目录，可给多个")
    parser.add_argument("--recovery", default="", help="只画某个救场方式（resample/home）；默认全画")
    parser.add_argument("--latest", action="store_true", help="自动挑最新的 compare / train run")
    parser.add_argument("--open", action="store_true", help="打印每张图的解读")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    compare_dir = Path(args.compare) if args.compare else None
    train_dirs = [Path(p) for p in args.train]
    if args.latest:
        # 结尾带 * ：这样 ..._stage2_compare 和 ..._stage2_compare_perturbed 都能被 --latest 找到
        compare_dir = compare_dir or find_latest("*stage2_compare*", "compare.json")
        if not train_dirs:
            found = [p for p in sorted((REPO_ROOT / "runs").glob("*_sac_transport_*"))
                     if (p / "evaluations_transport.npz").exists()]
            train_dirs = found[-2:] if len(found) >= 2 else found
    if not compare_dir and not train_dirs:
        raise SystemExit("没找到可画的结果。先跑 scripts/compare_reset_modes.py 或 scripts/train_transport.py，"
                         "或者加 --latest。")

    made: list[Path] = []
    if compare_dir:
        compare_dir = compare_dir if compare_dir.is_absolute() else REPO_ROOT / compare_dir
        payload = json.loads((compare_dir / "compare.json").read_text(encoding="utf-8"))
        out_dir = compare_dir / "figures"
        out_dir.mkdir(parents=True, exist_ok=True)
        recoveries = payload["config"].get("recovery_modes", ["resample"])
        if args.recovery:
            recoveries = [r for r in recoveries if r == args.recovery] or [args.recovery]
        for recovery in recoveries:
            for fn in (plot_coverage_heatmaps, plot_cost_bars):
                path = fn(payload, out_dir, recovery)
                if path:
                    made.append(path)
        path = plot_reliability_scan(payload, out_dir)
        if path:
            made.append(path)

    if train_dirs:
        runs = []
        for run_dir in train_dirs:
            run_dir = run_dir if run_dir.is_absolute() else REPO_ROOT / run_dir
            run = load_train(run_dir)
            if run is None:
                print(f"  [跳过] {run_dir} 里还没有 evaluations_transport.npz（训练还没产出评测点）")
                continue
            runs.append(run)
            out_dir = run_dir / "figures"
            out_dir.mkdir(parents=True, exist_ok=True)
            for path in (plot_learning_curves([run], out_dir), plot_forward_backward(run, out_dir)):
                if path:
                    made.append(path)
        if len(runs) >= 2:
            out_dir = runs[0]["dir"] / "figures"
            out_dir.mkdir(parents=True, exist_ok=True)
            for path in (plot_learning_curves(runs, out_dir), plot_two_curricula(runs, out_dir)):
                if path:
                    made.append(path)

    if not made:
        raise SystemExit("没有画出任何图：检查目录里是否有 compare.json / evaluations_transport.npz")
    print("=" * 78)
    print(f"已生成 {len(made)} 张图：")
    for path in dict.fromkeys(made):
        print(f"  {path}")
    print("=" * 78)
    if args.open:
        for key, text in EXPLAIN.items():
            if any(key in p.name for p in made):
                print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
