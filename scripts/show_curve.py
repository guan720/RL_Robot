#!/usr/bin/env python
"""看训练曲线，不需要 tensorboard（本机走代理，起 web 端口不方便）。

数据来源是 SB3 EvalCallback 存下的 evaluations.npz：每隔 eval_freq 步，
用固定的评测环境跑 n_eval_episodes 局，记录每局的 reward 与长度。

用法：
    python scripts/show_curve.py --run runs/20260922_160000_sac_reach
    python scripts/show_curve.py --run runs/xxx --png        # 额外存一张 png
    python scripts/show_curve.py --latest                    # 自动挑最新的 run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

# 忘了 activate venv 时给出人话提示，而不是甩一堆 traceback
ensure_venv("numpy")

import numpy as np  # noqa: E402


def find_latest_run() -> Path:
    runs = sorted((REPO_ROOT / "runs").glob("*_*"), key=lambda p: p.stat().st_mtime)
    runs = [r for r in runs if (r / "evaluations.npz").exists()]
    if not runs:
        raise SystemExit("runs/ 下还没有带 evaluations.npz 的训练结果，先跑 scripts/train_reach.py")
    return runs[-1]


def ascii_curve(x: np.ndarray, y: np.ndarray, width: int = 56, height: int = 14) -> str:
    grid = [[" "] * width for _ in range(height)]
    x_min, x_max = float(x.min()), float(x.max())
    y_min, y_max = float(y.min()), float(y.max())
    if x_max == x_min:
        x_max = x_min + 1.0
    if y_max == y_min:
        y_max = y_min + 1.0
    for xi, yi in zip(x, y):
        col = int((xi - x_min) / (x_max - x_min) * (width - 1))
        row = int((yi - y_min) / (y_max - y_min) * (height - 1))
        grid[height - 1 - row][col] = "*"
    lines = []
    for idx, row in enumerate(grid):
        label = f"{y_max - (y_max - y_min) * idx / (height - 1):>8.2f} |"
        lines.append(label + "".join(row))
    lines.append(" " * 9 + "+" + "-" * width)
    lines.append(" " * 10 + f"{int(x_min):<20}{int((x_min + x_max) / 2):<20}{int(x_max):>10}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default="")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--png", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run) if args.run else find_latest_run()
    if not run_dir.is_absolute():
        run_dir = REPO_ROOT / run_dir
    npz_path = run_dir / "evaluations.npz"
    if not npz_path.exists():
        raise SystemExit(f"找不到 {npz_path}")

    data = np.load(npz_path)
    timesteps = data["timesteps"]
    results = data["results"]            # shape: (n_evals, n_eval_episodes)
    ep_lengths = data.get("ep_lengths")  # 可能不存在

    mean_reward = results.mean(axis=1)
    print("=" * 72)
    print(f"run: {run_dir.name}")
    print(f"评测点: {len(timesteps)} 个，每点 {results.shape[1]} 局")
    print("=" * 72)
    print()
    if len(timesteps) < 2:
        # 只有一个评测点时画不出趋势线，别硬画（ascii_curve 的 x 轴会退化成同一个数）
        print(f"平均 episode reward：{mean_reward[0]:.3f}（只有 1 个评测点，看不出趋势）")
        print("  说明：eval_freq 大于总步数时就只会在训练结束时评一次。")
        print("  想看曲线请让 total_timesteps >= 2 * eval_freq，例如 --steps 50000 配 eval_freq 5000。")
    else:
        print("平均 episode reward 随训练步数的变化：")
        print(ascii_curve(timesteps.astype(float), mean_reward))
    print()
    print(f"  {'步数':>10}{'平均奖励':>12}{'最好一局':>12}")
    for step, mean, best in zip(timesteps, mean_reward, results.max(axis=1)):
        print(f"  {int(step):>10}{mean:>12.3f}{best:>12.3f}")

    if ep_lengths is not None:
        print()
        print("平均 episode 长度（Reach 里越短越好：说明越快到达目标）：")
        print(f"  起点 {ep_lengths[0].mean():.1f} 步 -> 终点 {ep_lengths[-1].mean():.1f} 步")

    result_path = run_dir / "result.json"
    if result_path.exists():
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        ev = payload.get("eval", {})
        print()
        print("独立评测对比（固定 seed）：")
        for key, label in [("random_policy", "随机策略"), ("untrained_model", "未训练"), ("trained_model", "训练后")]:
            if key in ev:
                print(f"  {label:<8} 成功率 {ev[key]['success_rate'] * 100:>6.1f}%"
                      f"   平均末距 {ev[key]['mean_final_dist']:.4f} m")

    if args.png:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(timesteps, mean_reward, label="mean reward")
        ax.fill_between(timesteps, results.min(axis=1), results.max(axis=1), alpha=0.2, label="min-max")
        ax.set_xlabel("timesteps")
        ax.set_ylabel("episode reward")
        ax.set_title(run_dir.name)
        ax.legend()
        fig.tight_layout()
        out_png = run_dir / "curve.png"
        fig.savefig(out_png, dpi=120)
        print(f"\n图已保存: {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
