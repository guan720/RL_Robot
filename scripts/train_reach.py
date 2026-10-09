#!/usr/bin/env python
"""阶段 1b：在自写 Reach 环境上用 SAC 训练，并做「训练前 vs 训练后」对比。

这是整个项目的第一个真正的强化学习实验。它要回答一个问题：

    机器人「执行了一次任务」和机器人「通过数据学会了任务」，区别在哪？

区别就在于：训练之后，某个文件里的数字（神经网络权重）变了，而且在**没见过的**
初始状态下表现更好。所以本脚本会固定评测 seed，跑三次评测：

    1. 随机策略        -> 完全不学习的基线
    2. 未训练的网络    -> 有网络结构、但权重是随机初始化的
    3. 训练后的网络    -> 同一份权重，被数据改写过

只有 (3) 明显好于 (1)(2)，才能说「参数学习带来了提升」。

用法：
    python scripts/train_reach.py --steps 5000            # 快速冒烟（不够学会，但能看到方向）
    python scripts/train_reach.py --config configs/reach_sac.yaml   # 全量 50000 步
    python scripts/train_reach.py --algo ppo --steps 50000
    python scripts/train_reach.py --threads 4             # 换图像策略后再放开线程

耗时预期：本机是共享节点（load average 常在 1000 上下），单线程 SAC 约 15 步/秒，
50000 步要 **50–60 分钟**，其中大部分时间是在排队等 CPU。这不是代码慢。
跑长任务请用：
    setsid nohup python -u scripts/train_reach.py --config configs/reach_sac.yaml \
        > /tmp/train.log 2>&1 < /dev/null & disown
然后 `tail -f /tmp/train.log` 看进度。普通 `nohup ... &` 会被杀，必须带 setsid。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 这台机有 112 核，torch 默认会开 56 个 intra-op 线程。但本项目的策略网络只有两层 64，
# 单次前向/反向的计算量极小，线程同步开销远大于计算本身：实测 CPU 占用 1100%+，
# 5000 步反而跑不完。所以默认单线程，等接了图像策略（CNN/ViT）再放开。
# 注意：这两个变量必须在 torch 被 import 之前设置才有效。
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

# 忘了 activate venv 时给出人话提示，而不是甩一堆 traceback
ensure_venv("stable_baselines3", "yaml", "gymnasium")

import yaml  # noqa: E402

SAC_KWARGS = ("learning_rate", "buffer_size", "batch_size", "gamma", "tau", "train_freq", "gradient_steps")
PPO_KWARGS = ("learning_rate", "batch_size", "gamma", "n_steps", "n_epochs", "gae_lambda", "clip_range")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "reach_sac.yaml"))
    parser.add_argument("--steps", type=int, default=0, help="覆盖 config 里的 total_timesteps")
    parser.add_argument("--algo", default="", choices=["", "sac", "ppo"], help="覆盖 config 里的算法")
    parser.add_argument("--seed", type=int, default=-1, help="覆盖 config 里的训练 seed")
    parser.add_argument("--device", default="cpu", help="这个网络只有两层 64，CPU 通常比 GPU 快；可改 cuda")
    parser.add_argument("--threads", type=int, default=1,
                        help="torch 线程数。小网络用 1 最快（默认）；换图像策略后可调大")
    parser.add_argument("--run-name", default="reach")
    return parser.parse_args()


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def print_table(rows: list[tuple[str, dict]]) -> None:
    print()
    print("=" * 72)
    print("固定 seed 评测对比（同一批初始状态，同题同卷）")
    print("=" * 72)
    print(f"  {'策略':<18}{'成功率':>10}{'平均奖励':>12}{'平均步数':>10}{'平均末距(m)':>14}")
    for name, metrics in rows:
        print(f"  {name:<18}{metrics['success_rate'] * 100:>9.1f}%"
              f"{metrics['mean_reward']:>12.3f}{metrics['mean_steps']:>10.1f}"
              f"{metrics['mean_final_dist']:>14.4f}")


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    env_kwargs = dict(config.get("env", {}))
    train_cfg = dict(config.get("train", {}))
    eval_cfg = dict(config.get("eval", {}))

    if args.steps:
        train_cfg["total_timesteps"] = args.steps
    if args.algo:
        train_cfg["algo"] = args.algo
    if args.seed >= 0:
        train_cfg["seed"] = args.seed

    import torch

    torch.set_num_threads(max(1, args.threads))
    try:
        torch.set_num_interop_threads(max(1, args.threads))
    except RuntimeError:
        pass  # 已经跑过并行任务后不能再改，忽略即可

    algo = str(train_cfg.get("algo", "sac")).lower()
    total_timesteps = int(train_cfg.get("total_timesteps", 50000))
    seed = int(train_cfg.get("seed", 0))
    n_eval_episodes = int(eval_cfg.get("n_episodes", 50))
    eval_seed = int(eval_cfg.get("seed", 12345))

    run_dir = REPO_ROOT / "runs" / f"{time.strftime('%Y%m%d_%H%M%S')}_{algo}_{args.run_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.resolved.yaml").write_text(
        yaml.safe_dump({"env": env_kwargs, "train": train_cfg, "eval": eval_cfg}, allow_unicode=True),
        encoding="utf-8",
    )

    from stable_baselines3 import PPO, SAC
    from stable_baselines3.common.callbacks import EvalCallback
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    from envs.reach_env import make_reach_env
    from eval.reach_eval import evaluate_reach

    print("=" * 72)
    print(f"[{algo.upper()}] Reach 训练 · steps={total_timesteps} · seed={seed} "
          f"· device={args.device} · threads={torch.get_num_threads()}")
    print(f"run 目录: {run_dir}")
    print("=" * 72)

    baseline_random = evaluate_reach(None, env_kwargs, n_episodes=n_eval_episodes, seed=eval_seed)
    print(f"  (1/3) 随机策略基线:      成功率 {baseline_random['success_rate'] * 100:.1f}%")

    vec_env = DummyVecEnv([lambda: Monitor(make_reach_env(**env_kwargs))])
    algo_cls = SAC if algo == "sac" else PPO
    allowed = SAC_KWARGS if algo == "sac" else PPO_KWARGS
    algo_kwargs = {key: train_cfg[key] for key in allowed if key in train_cfg}
    model = algo_cls(
        policy="MlpPolicy",
        env=vec_env,
        seed=seed,
        device=args.device,
        verbose=1,
        tensorboard_log=str(run_dir / "tb"),
        policy_kwargs=dict(train_cfg.get("policy_kwargs", {})),
        **algo_kwargs,
    )

    baseline_untrained = evaluate_reach(model, env_kwargs, n_episodes=n_eval_episodes, seed=eval_seed)
    print(f"  (2/3) 未训练的网络:      成功率 {baseline_untrained['success_rate'] * 100:.1f}%")

    # 评测必须用一个**独立**的环境：拿训练环境去评测会把训练中的 episode 打断，
    # 既污染学习数据，也让曲线不可比。
    eval_env = DummyVecEnv([lambda: Monitor(make_reach_env(**env_kwargs))])
    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=str(run_dir),
        # log_path 决定 evaluations.npz 存哪；不设的话 show_curve.py 就没数据可画。
        log_path=str(run_dir),
        eval_freq=max(1000, int(train_cfg.get("eval_freq", 5000))),
        n_eval_episodes=int(train_cfg.get("n_eval_episodes", 20)),
        deterministic=True,
    )

    started = time.time()
    model.learn(total_timesteps=total_timesteps, callback=eval_cb, progress_bar=False)
    train_sec = time.time() - started
    model.save(str(run_dir / "model_final"))

    trained = evaluate_reach(model, env_kwargs, n_episodes=n_eval_episodes, seed=eval_seed)
    print(f"  (3/3) 训练后的网络:      成功率 {trained['success_rate'] * 100:.1f}%")

    print_table([
        ("随机策略", baseline_random),
        ("未训练的网络", baseline_untrained),
        ("训练后", trained),
    ])

    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "algo": algo,
        "total_timesteps": total_timesteps,
        "seed": seed,
        "device": args.device,
        "threads": torch.get_num_threads(),
        "train_seconds": round(train_sec, 1),
        "env_kwargs": env_kwargs,
        "eval": {
            "random_policy": {k: v for k, v in baseline_random.items() if k != "episodes"},
            "untrained_model": {k: v for k, v in baseline_untrained.items() if k != "episodes"},
            "trained_model": {k: v for k, v in trained.items() if k != "episodes"},
        },
        "artifacts": {
            "final_model": str(run_dir / "model_final.zip"),
            "best_model": str(run_dir / "best_model.zip"),
            "tensorboard": str(run_dir / "tb"),
        },
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "eval_trained.json").write_text(json.dumps(trained, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 72)
    print("怎么读这个结果")
    print("=" * 72)
    print(f"  训练耗时 {train_sec:.1f} 秒，交互 {total_timesteps} 步。")
    delta = trained["success_rate"] - baseline_untrained["success_rate"]
    print(f"  成功率变化：{baseline_untrained['success_rate'] * 100:.1f}% -> {trained['success_rate'] * 100:.1f}%"
          f"（{'提升' if delta >= 0 else '下降'} {abs(delta) * 100:.1f} 个百分点）")
    print(f"  平均末距：{baseline_untrained['mean_final_dist']:.4f} m -> {trained['mean_final_dist']:.4f} m"
          f"（成功圈半径 {env_kwargs.get('goal_radius', 0.03)} m）")
    print()
    print("  变的是什么？只有 model_final.zip 里的网络权重。环境、奖励函数、评测 seed 都没动。")
    print("  这就是「机器人通过数据学会了任务」的最小可验证形式。")
    print()
    print(f"  曲线查看: tensorboard --logdir {run_dir / 'tb'}")
    print(f"  复现评测: python scripts/eval_policy.py --ckpt {run_dir / 'model_final.zip'} --episodes {n_eval_episodes}")
    vec_env.close()
    eval_env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
