#!/usr/bin/env python
"""把一次 Reach 训练的结果画成图（PNG），存到 runs/<run>/figures/。

为什么需要这个？因为终端里的表格只能告诉你「100% vs 6%」，
但**看不出学习是怎么发生的**。图能回答三个表格回答不了的问题：

    1. 学习是渐变的还是突变的？            -> fig_curve.png
    2. 提升到底体现在哪一列？              -> fig_three_way.png
    3. 策略的**行为**变成了什么样？         -> fig_trajectories.png / fig_distance.png

第 3 点最重要：成功率是标量，行为是轨迹。两张轨迹图并排放，
你一眼就能看出「随机游走」和「直线冲过去」的区别——这比任何数字都直观。

注意：本机没有中文字体（matplotlib 只找到 21 个字体，全是西文），
所以**图里的标签一律用英文**，中文解释放在终端输出和 docs 里。

用法：
    python scripts/plot_results.py --run runs/20260922_170720_sac_reach
    python scripts/plot_results.py --latest
    python scripts/plot_results.py --latest --open      # 打印每张图的解读
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 和其它脚本一致：小网络单线程，且必须在 import torch 之前设（load_any_policy 会拉起 torch）
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "matplotlib", "yaml")

import matplotlib  # noqa: E402

matplotlib.use("Agg")          # 本机无显示器，必须用离屏后端
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

from envs.reach_env import make_reach_env  # noqa: E402
from scripts.eval_policy import load_any_policy  # noqa: E402

# 统一配色，四张图之间能对上号
COLORS = {"random": "#999999", "untrained": "#e8a33d", "trained": "#2f7ed8"}


def find_latest_run() -> Path:
    runs = [r for r in sorted((REPO_ROOT / "runs").glob("*_*")) if (r / "result.json").exists()]
    if not runs:
        raise SystemExit("runs/ 下还没有训练结果，先跑 scripts/train_reach.py")
    return max(runs, key=lambda p: p.stat().st_mtime)


def collect_traces(policy, env_kwargs: dict, seeds: list[int]) -> list[dict]:
    """跑几局，把末端轨迹和目标点记下来（单位：米，已反归一化）。"""
    env = make_reach_env(**env_kwargs)
    half = float(env_kwargs.get("half_space", 0.15))
    rng = np.random.default_rng(0)
    traces = []
    for seed in seeds:
        obs, info = env.reset(seed=seed)
        ee = [obs[:3].copy() * half]
        goal = obs[3:].copy() * half
        dists = [float(info["dist"])]
        while True:
            if policy is None:
                action = rng.uniform(-1.0, 1.0, size=env.action_space.shape).astype(np.float32)
            else:
                action, _ = policy.predict(obs, deterministic=True)
            obs, _reward, terminated, truncated, info = env.step(action)
            ee.append(obs[:3].copy() * half)
            dists.append(float(info["dist"]))
            if terminated or truncated:
                break
        traces.append({
            "seed": seed,
            "ee": np.asarray(ee),
            "goal": goal,
            "dists": np.asarray(dists),
            "success": bool(info.get("success", False)),
            "steps": int(info.get("steps", len(dists))),
        })
    return traces


def fig_curve(run_dir: Path, fig_dir: Path) -> Path | None:
    """图 1：学习曲线。回答「学习是渐变还是突变」。"""
    npz = run_dir / "evaluations.npz"
    if not npz.exists():
        print("  跳过 fig_curve.png（没有 evaluations.npz）")
        return None
    data = np.load(npz)
    steps = data["timesteps"].astype(float)
    results = data["results"]
    mean = results.mean(axis=1)
    lengths = data["ep_lengths"].mean(axis=1) if "ep_lengths" in data else None

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.fill_between(steps, results.min(axis=1), results.max(axis=1), alpha=0.18,
                    color=COLORS["trained"], label="min-max over 20 eval episodes")
    ax.plot(steps, mean, "-o", ms=4, color=COLORS["trained"], label="mean episode reward")
    ax.axhline(0, color="black", lw=0.8, ls=":")
    ax.set_xlabel("training timesteps")
    ax.set_ylabel("episode reward (deterministic eval)")
    ax.set_title("Learning curve — SAC on Reach3D")
    ax.grid(alpha=0.25)

    # 自动标出「相变」：第一次从负值跳到 >50% 最终值的那个点
    if len(mean) > 2 and mean[-1] > 0:
        jump = int(np.argmax(mean > 0.5 * mean[-1]))
        if jump > 0:
            ax.axvline(steps[jump], color="#cc4444", lw=1.2, ls="--", alpha=0.8)
            ax.annotate(f"phase transition\n~{int(steps[jump])} steps",
                        xy=(steps[jump], mean[jump]), xytext=(steps[jump] + 0.06 * steps[-1], min(mean)),
                        color="#cc4444", fontsize=9,
                        arrowprops=dict(arrowstyle="->", color="#cc4444", lw=1))

    if lengths is not None:
        ax2 = ax.twinx()
        ax2.plot(steps, lengths, "--", color="#444444", alpha=0.7, label="mean episode length")
        ax2.set_ylabel("episode length (steps)", color="#444444")
        ax2.tick_params(axis="y", labelcolor="#444444")
    # axhline/axvline 会自动生成 _child2 这类标签，必须过滤掉，否则图例里会出现垃圾项
    handles, labels = ax.get_legend_handles_labels()
    if lengths is not None:
        h2, l2 = ax2.get_legend_handles_labels()
        handles += h2
        labels += l2
    keep = [(h, l) for h, l in zip(handles, labels) if not l.startswith("_")]
    ax.legend([h for h, _ in keep], [l for _, l in keep], loc="lower right", fontsize=8)

    fig.tight_layout()
    out = fig_dir / "fig_curve.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def fig_three_way(result: dict, fig_dir: Path) -> Path | None:
    """图 2：三行对比表画成柱状图。回答「提升体现在哪一列」。"""
    ev = result.get("eval", {})
    order = [("random_policy", "random", "Random\npolicy"),
             ("untrained_model", "untrained", "Untrained\nnetwork"),
             ("trained_model", "trained", "Trained\n(50k steps)")]
    order = [(k, c, lab) for k, c, lab in order if k in ev]
    if len(order) < 2:
        print("  跳过 fig_three_way.png（result.json 里评测项不足）")
        return None

    metrics = [("success_rate", "Success rate", 100.0, "%"),
               ("mean_steps", "Mean steps to finish", 1.0, "steps"),
               ("mean_final_dist", "Mean final distance to goal", 1000.0, "mm")]

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    for ax, (key, title, scale, unit) in zip(axes, metrics):
        values = [ev[k][key] * scale for k, _c, _l in order]
        bars = ax.bar([lab for _k, _c, lab in order], values,
                      color=[COLORS[c] for _k, c, _l in order], width=0.62)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel(unit, fontsize=9)
        ax.grid(axis="y", alpha=0.25)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.1f}",
                    ha="center", va="bottom", fontsize=9)
        ax.set_ylim(0, max(values) * 1.22 + 1e-9)
        ax.tick_params(axis="x", labelsize=8)

    fig.suptitle("Same 50 initial states, same seed — only the network weights differ", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = fig_dir / "fig_three_way.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def fig_trajectories(traces_by_kind: dict, env_kwargs: dict, fig_dir: Path) -> Path | None:
    """图 3：轨迹对比（2D 俯视投影 + 3D）。回答「行为变成了什么样」。

    这是最能建立直觉的一张图：
      - 随机策略 = 一团乱走的折线，大部分局走满 max_steps
      - 训练后   = 从起点直奔目标的短直线
    绿色圆圈是成功圈（goal_radius），星号是目标点。
    """
    kinds = [k for k in ("random", "trained") if traces_by_kind.get(k)]
    if not kinds:
        return None
    n_col = max(len(traces_by_kind[k]) for k in kinds)
    radius = float(env_kwargs.get("goal_radius", 0.03))
    half = float(env_kwargs.get("half_space", 0.15))

    fig = plt.figure(figsize=(4.0 * n_col, 4.2 * len(kinds) + 4.0))
    gs = fig.add_gridspec(len(kinds) + 1, n_col, height_ratios=[1] * len(kinds) + [1.15])

    for row, kind in enumerate(kinds):
        for col, trace in enumerate(traces_by_kind[kind]):
            ax = fig.add_subplot(gs[row, col])
            ee, goal = trace["ee"], trace["goal"]
            circle = plt.Circle(goal[:2], radius, color="#2ecc71", alpha=0.22, label="success radius")
            ax.add_patch(circle)
            ax.plot(ee[:, 0], ee[:, 1], "-", color=COLORS[kind], lw=1.1, alpha=0.85, label="end-effector path")
            ax.plot(ee[0, 0], ee[0, 1], "o", color="black", ms=5, label="start")
            ax.plot(goal[0], goal[1], "*", color="#2ecc71", ms=15, mec="black", mew=0.5, label="goal")
            ax.plot(ee[-1, 0], ee[-1, 1], "s", color="#cc4444", ms=5, label="end")
            ax.set_xlim(-half, half)
            ax.set_ylim(-half, half)
            ax.set_aspect("equal")
            ax.grid(alpha=0.25)
            ax.set_title(f"{kind} · seed {trace['seed']} · {trace['steps']} steps · "
                         f"{'SUCCESS' if trace['success'] else 'fail'}", fontsize=9)
            ax.set_xlabel("x (m)", fontsize=8)
            ax.set_ylabel("y (m)", fontsize=8)
            if row == 0 and col == 0:
                ax.legend(fontsize=7, loc="upper right")

    # 最后一行：3D 视图，把所有训练后轨迹画在一起
    if "trained" in traces_by_kind:
        ax3 = fig.add_subplot(gs[len(kinds), :], projection="3d")
        for trace in traces_by_kind["trained"]:
            ee = trace["ee"]
            ax3.plot(ee[:, 0], ee[:, 1], ee[:, 2], "-", color=COLORS["trained"], lw=1.0, alpha=0.75)
            ax3.scatter(*trace["goal"], color="#2ecc71", marker="*", s=90)
            ax3.scatter(*ee[0], color="black", s=18)
        ax3.set_title("Trained policy in 3D — every episode is a near-straight line to its goal", fontsize=10)
        ax3.set_xlabel("x (m)")
        ax3.set_ylabel("y (m)")
        ax3.set_zlabel("z (m)")
        lim = half * 1.05
        ax3.set_xlim(-lim, lim)
        ax3.set_ylim(-lim, lim)
        ax3.set_zlim(-lim, lim)

    fig.tight_layout()
    out = fig_dir / "fig_trajectories.png"
    fig.savefig(out, dpi=125)
    plt.close(fig)
    return out


def fig_distance(traces_by_kind: dict, env_kwargs: dict, fig_dir: Path) -> Path | None:
    """图 4：单局内「离目标还有多远」随步数的变化。

    成功率是阶跃的（0 或 1），距离是连续的。学习早期成功率还不动的时候，
    距离曲线已经在降了——这张图能让你**提前**看到学习信号，不用干等成功率涨。
    """
    kinds = [k for k in ("random", "untrained", "trained") if traces_by_kind.get(k)]
    if not kinds:
        return None
    radius = float(env_kwargs.get("goal_radius", 0.03))

    fig, ax = plt.subplots(figsize=(8, 4.2))
    for kind in kinds:
        traces = traces_by_kind[kind]
        longest = max(len(t["dists"]) for t in traces)
        padded = np.full((len(traces), longest), np.nan)
        for i, trace in enumerate(traces):
            padded[i, :len(trace["dists"])] = trace["dists"]
        ax.plot(np.nanmean(padded, axis=0), color=COLORS[kind], lw=2,
                label=f"{kind} (mean of {len(traces)} episodes)")
    ax.axhline(radius, color="#2ecc71", ls="--", lw=1.2, label=f"success radius = {radius*1000:.0f} mm")
    ax.set_xlabel("step within episode")
    ax.set_ylabel("distance to goal (m)")
    ax.set_title("Distance to goal over time — why you should watch this, not just success rate")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = fig_dir / "fig_distance.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


EXPLAIN = {
    "fig_curve.png": [
        "看什么：蓝线是每 5000 步用**独立环境**评 20 局的平均奖励；灰虚线是平均 episode 长度。",
        "关键现象：0→10000 步奖励一直是负的，10000→15000 步直接跳到 +9，之后平台期。",
        "为什么：SAC 前期在高熵探索，而评测用 deterministic=True（取分布均值），",
        "       没成形的高熵分布，它的均值动作很差。所以**中途看到负数不要停训练**。",
        "灰虚线同步从 86 步掉到 2.3 步 → 不只是「能到」，而是「越来越快」。",
    ],
    "fig_three_way.png": [
        "看什么：同一批 50 个初始状态、同一个 seed，只有网络权重不同。",
        "左：成功率 16% → 6% → 100%。注意「未训练的网络」比纯随机还差，",
        "     这说明**加了网络结构本身不带来任何能力**，能力全部来自数据。",
        "中：平均步数 91.6 → 2.6。一步最大位移 8.7cm、目标平均 19cm，理论下限约 2.2 步，",
        "     所以 2.6 步已经接近最优，不是勉强蹭进成功圈。",
        "右：平均末距 211mm → 8mm，成功圈半径是 30mm。",
    ],
    "fig_trajectories.png": [
        "看什么：上排随机策略，下排训练后；每格是一局，俯视 x-y 投影。",
        "随机策略 = 一团折线，经常走满 100 步还在盒子里乱撞。",
        "训练后   = 从起点一条直线扎进绿圈。最下面 3D 图把所有局叠在一起，",
        "           能看到无论目标在哪个角落，策略都是直线过去 —— 这才是「学会」的样子。",
        "黑点=起点，绿星=目标，红方块=终点，绿圈=成功判定范围（30mm）。",
    ],
    "fig_distance.png": [
        "看什么：一局之内「离目标还有多远」随步数的平均变化。",
        "为什么重要：成功率是阶跃量（0/1），距离是连续量。",
        "           学习早期成功率还没动时，距离曲线已经在降 —— 这是**最早**的学习信号。",
        "绿色虚线是成功圈半径，曲线穿过它就代表成功。",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default="", help="run 目录，例如 runs/20260922_170720_sac_reach")
    parser.add_argument("--latest", action="store_true", help="自动挑最新的 run")
    parser.add_argument("--ckpt", default="", help="指定模型；默认用 run 目录里的 model_final.zip")
    parser.add_argument("--vis-episodes", type=int, default=3, help="轨迹图画几局（默认 3）")
    parser.add_argument("--seed", type=int, default=12345, help="画轨迹用的起始 seed")
    parser.add_argument("--explain", action="store_true", help="打印每张图该怎么读")
    args = parser.parse_args()

    run_dir = Path(args.run) if args.run else find_latest_run()
    if not run_dir.is_absolute():
        run_dir = REPO_ROOT / run_dir
    result_path = run_dir / "result.json"
    if not result_path.exists():
        raise SystemExit(f"{run_dir} 里没有 result.json，这不是一个训练 run 目录")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    env_kwargs = dict(result.get("env_kwargs", {}))
    fig_dir = run_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    ckpt = args.ckpt or str(run_dir / "model_final.zip")
    policy, algo = load_any_policy(ckpt)
    print("=" * 72)
    print(f"run     : {run_dir.name}")
    print(f"policy  : {Path(ckpt).name}（识别为 {algo}）")
    print(f"输出目录: {fig_dir}")
    print("=" * 72)

    seeds = [args.seed + i for i in range(args.vis_episodes)]
    print("  正在重跑轨迹用于绘图（不训练，只前向推理）...")
    traces_by_kind = {
        "random": collect_traces(None, env_kwargs, seeds),
        "untrained": [],
        "trained": collect_traces(policy, env_kwargs, seeds),
    }

    made = []
    for fn in (lambda: fig_curve(run_dir, fig_dir),
               lambda: fig_three_way(result, fig_dir),
               lambda: fig_trajectories(traces_by_kind, env_kwargs, fig_dir),
               lambda: fig_distance(traces_by_kind, env_kwargs, fig_dir)):
        out = fn()
        if out:
            made.append(out)
            print(f"  ✓ {out.relative_to(REPO_ROOT)}")

    print()
    for trace_kind in ("random", "trained"):
        successes = sum(t["success"] for t in traces_by_kind[trace_kind])
        steps = [t["steps"] for t in traces_by_kind[trace_kind]]
        print(f"  画图的 {len(steps)} 局里，{trace_kind:<8} 成功 {successes} 局，步数 {steps}")

    if args.explain:
        print()
        for name in made:
            print("=" * 72)
            print(name.name)
            print("=" * 72)
            for line in EXPLAIN.get(name.name, []):
                print("  " + line)
            print()
    else:
        print()
        print("  加 --explain 可以看每张图该怎么读。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
