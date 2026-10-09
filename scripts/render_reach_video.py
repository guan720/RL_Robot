#!/usr/bin/env python
"""把 Reach 任务**画出来**：随机策略 vs 训练后策略，并排动画，存成 mp4。

为什么需要这个？`envs/reach_env.py` 是纯 numpy 的抽象环境，`render()` 返回 None，
**它本身没有任何画面**。所以光跑训练你「什么都看不见」——这不是你的问题，是环境没渲染。

这个脚本用 matplotlib 把抽象环境画成 3D：
    - 灰色线框   = 工作空间盒子 [-15cm, 15cm]^3
    - 绿球       = 目标点 + 成功判定范围（goal_radius）
    - 蓝/灰点    = 末端（end-effector）当前位置
    - 拖尾       = 走过的路径
    - 顶部文字   = 步数 / 离目标距离 / 结果

左边是随机策略（你会看到它在盒子里乱撞、最后超时），
右边是训练后的策略（你会看到它几乎直线扎进绿球）。
**「成功」在这个环境里就是：末端点进入绿球，这一局立刻结束。**

用法：
    python scripts/render_reach_video.py --run runs/20260922_170720_sac_reach
    python scripts/render_reach_video.py --latest --steps 40 --fps 8
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "matplotlib", "imageio", "yaml")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from envs.reach_env import make_reach_env  # noqa: E402
from scripts.eval_policy import load_any_policy  # noqa: E402


def run_episode(policy, env_kwargs: dict, seed: int) -> dict:
    """跑一局，逐帧记录末端位置、目标、距离、结果。"""
    env = make_reach_env(**env_kwargs)
    half = float(env_kwargs.get("half_space", 0.15))
    rng = np.random.default_rng(0)
    obs, info = env.reset(seed=seed)
    frames = [{"ee": obs[:3].copy() * half, "dist": float(info["dist"]),
               "success": False, "reward": 0.0}]
    goal = obs[3:].copy() * half
    total_reward = 0.0
    while True:
        if policy is None:
            action = rng.uniform(-1.0, 1.0, size=env.action_space.shape).astype(np.float32)
        else:
            action, _ = policy.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += float(reward)
        frames.append({"ee": obs[:3].copy() * half, "dist": float(info["dist"]),
                       "success": bool(info.get("success", False)), "reward": float(reward)})
        if terminated or truncated:
            break
    return {"frames": frames, "goal": goal, "total_reward": total_reward,
            "success": frames[-1]["success"], "steps": len(frames) - 1}


def draw_box(ax, half: float) -> None:
    """画工作空间盒子的 12 条棱。"""
    h = half
    corners = np.array([[x, y, z] for x in (-h, h) for y in (-h, h) for z in (-h, h)])
    edges = [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
             (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7)]
    for a, b in edges:
        ax.plot(*zip(corners[a], corners[b]), color="#bbbbbb", lw=0.8, alpha=0.7)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default="")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--ckpt", default="")
    parser.add_argument("--steps", type=int, default=40, help="动画最多画多少步（默认 40）")
    parser.add_argument("--fps", type=int, default=8)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--out", default="", help="输出 mp4 路径，默认 runs/<run>/reach_random_vs_trained.mp4")
    args = parser.parse_args()

    import json

    if args.run:
        run_dir = Path(args.run)
    else:
        runs = [r for r in sorted((REPO_ROOT / "runs").glob("*_*")) if (r / "result.json").exists()]
        if not runs:
            raise SystemExit("runs/ 下还没有训练结果")
        run_dir = max(runs, key=lambda p: p.stat().st_mtime)
    if not run_dir.is_absolute():
        run_dir = REPO_ROOT / run_dir

    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    env_kwargs = dict(result.get("env_kwargs", {}))
    half = float(env_kwargs.get("half_space", 0.15))
    radius = float(env_kwargs.get("goal_radius", 0.03))

    ckpt = args.ckpt or str(run_dir / "model_final.zip")
    policy, algo = load_any_policy(ckpt)
    print(f"run={run_dir.name}  policy={Path(ckpt).name} ({algo})")

    random_ep = run_episode(None, env_kwargs, args.seed)
    trained_ep = run_episode(policy, env_kwargs, args.seed)
    print(f"  random : {random_ep['steps']} steps, success={random_ep['success']}, reward={random_ep['total_reward']:.2f}")
    print(f"  trained: {trained_ep['steps']} steps, success={trained_ep['success']}, reward={trained_ep['total_reward']:.2f}")

    out_path = Path(args.out) if args.out else run_dir / "reach_random_vs_trained.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import imageio

    n_frames = min(args.steps, max(random_ep["steps"], trained_ep["steps"])) + 1
    print(f"  渲染 {n_frames} 帧 -> {out_path}")

    writer = imageio.get_writer(str(out_path), fps=args.fps, codec="libx264", quality=8)
    for t in range(n_frames):
        fig = plt.figure(figsize=(11, 5.2))
        for col, (ep, title, color) in enumerate([
                (random_ep, "RANDOM policy", "#888888"),
                (trained_ep, "TRAINED policy (SAC, 50k steps)", "#2f7ed8")]):
            ax = fig.add_subplot(1, 2, col + 1, projection="3d")
            draw_box(ax, half)
            goal = ep["goal"]
            # 成功判定范围：画一个半透明球面
            u, v = np.mgrid[0:2*np.pi:18j, 0:np.pi:10j]
            ax.plot_surface(goal[0] + radius * np.cos(u) * np.sin(v),
                            goal[1] + radius * np.sin(u) * np.sin(v),
                            goal[2] + radius * np.cos(v),
                            color="#2ecc71", alpha=0.18, linewidth=0)
            ax.scatter(*goal, color="#2ecc71", marker="*", s=160, depthshade=False)

            idx = min(t, len(ep["frames"]) - 1)
            trail = np.array([f["ee"] for f in ep["frames"][:idx + 1]])
            if len(trail) > 1:
                ax.plot(trail[:, 0], trail[:, 1], trail[:, 2], "-", color=color, lw=1.4, alpha=0.8)
            ax.scatter(*trail[-1], color=color, s=70, depthshade=False, edgecolors="black")

            ax.set_xlim(-half, half)
            ax.set_ylim(-half, half)
            ax.set_zlim(-half, half)
            ax.set_xlabel("x")
            ax.set_ylabel("y")
            ax.set_zlabel("z")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_zticks([])

            frame = ep["frames"][idx]
            done = idx >= len(ep["frames"]) - 1
            status = "SUCCESS" if frame["success"] else ("TIMEOUT" if done else "running")
            ax.set_title(f"{title}\nstep {idx}/{ep['steps']}   dist {frame['dist']*1000:5.1f} mm   "
                         f"{status}", fontsize=10)

        fig.suptitle("Reach3D — success = end-effector enters the green sphere (30 mm)", fontsize=12)
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        fig.canvas.draw()
        image = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
        writer.append_data(image)
        plt.close(fig)
    writer.close()
    print(f"  视频已保存: {out_path}")
    print()
    print("  怎么读：左边的点在盒子里乱走、距离一直在 200mm 上下晃、最后 TIMEOUT；")
    print("          右边的点 2-3 步就扎进绿球，dist 掉到 10mm 以内，状态变 SUCCESS。")
    print("          绿球就是环境代码里 `dist <= goal_radius` 这一行判定的可视化。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
