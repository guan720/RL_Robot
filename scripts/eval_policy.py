#!/usr/bin/env python
"""独立评测一个已保存的策略（不训练，只打分）。

用法：
    python scripts/eval_policy.py --ckpt runs/<run>/model_final.zip
    python scripts/eval_policy.py --ckpt runs/<run>/best_model.zip --episodes 100 --seed 999
    python scripts/eval_policy.py --random          # 随机策略基线

为什么要单独一个脚本？因为评测必须在训练之外、用另一批 seed 跑，
否则「训练时顺便报的高分」无法证明策略真的学到了东西。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 与 train_reach.py 同理：小网络单线程比 56 线程快得多，且必须在 import torch 之前设。
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

# 忘了 activate venv 时给出人话提示，而不是甩一堆 traceback
ensure_venv("stable_baselines3", "yaml", "gymnasium")

import yaml  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ckpt", default="", help="SB3 模型 .zip 路径；不填则用 --random")
    parser.add_argument("--random", action="store_true", help="评测随机策略基线")
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "reach_sac.yaml"),
                        help="提供环境参数的 yaml（必须与训练时一致，否则评测不公平）")
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--stochastic", action="store_true", help="采样动作而不是取均值")
    # 严酷探针：不改训练，只在评测时把条件收紧，回答「冻结的策略在更难的条件下还行不行」。
    # 为什么要这个？因为默认配置下随机策略就有 ~19% 成功率（见 docs/notes_stage1.md），
    # 只看「成功率涨了」不足以说明学到了东西。收紧之后随机基线掉到 ~3.5%，信号就干净了。
    parser.add_argument("--max-steps", type=int, default=0, help="覆盖环境 max_steps（0=用 config）")
    parser.add_argument("--goal-radius", type=float, default=0.0,
                        help="覆盖成功圈半径，单位米（0=用 config）")
    return parser.parse_args()


def load_any_policy(ckpt: str):
    """加载一个 SB3 模型，自动识别它是哪种算法。

    为什么不能直接 BaseAlgorithm.load()？因为 BaseAlgorithm 是**抽象类**
    （缺 _setup_model / learn），Python 会直接报
    `TypeError: Can't instantiate abstract class BaseAlgorithm`。
    必须用具体子类：SAC.load(...) / PPO.load(...)。

    识别办法：模型 zip 里的 `data` 开头是一段 JSON，
    policy_class 的 __module__ 形如 `stable_baselines3.sac.policies` → 算法是 SAC。
    万一读不出来，就按候选类逐个试。
    """
    import re
    import zipfile

    from stable_baselines3 import A2C, DDPG, DQN, PPO, SAC, TD3

    candidates = {"sac": SAC, "ppo": PPO, "td3": TD3, "ddpg": DDPG, "a2c": A2C, "dqn": DQN}
    try:
        with zipfile.ZipFile(ckpt) as archive:
            head = archive.read("data")[:4096].decode("utf-8", "ignore")
        found = re.search(r"stable_baselines3\.(\w+)\.policies", head)
        if found and found.group(1) in candidates:
            return candidates[found.group(1)].load(ckpt), found.group(1).upper()
    except Exception:
        pass
    for name, cls in candidates.items():
        try:
            return cls.load(ckpt), name.upper()
        except Exception:
            continue
    raise SystemExit(f"无法识别 {ckpt} 的算法类型，请确认它是 stable-baselines3 存的 .zip")


def main() -> int:
    args = parse_args()
    with open(args.config, "r", encoding="utf-8") as handle:
        env_kwargs = dict(yaml.safe_load(handle).get("env", {}))

    overrides = {}
    if args.max_steps:
        overrides["max_steps"] = args.max_steps
    if args.goal_radius:
        overrides["goal_radius"] = args.goal_radius
    env_kwargs.update(overrides)

    from eval.reach_eval import evaluate_reach

    algo_name = "random"
    if args.random or not args.ckpt:
        policy = None
        label = "random"
    else:
        policy, algo_name = load_any_policy(args.ckpt)
        label = Path(args.ckpt).name
        print(f"  识别为 {algo_name} 模型")

    metrics = evaluate_reach(policy, env_kwargs, n_episodes=args.episodes, seed=args.seed,
                             deterministic=not args.stochastic)

    print("=" * 72)
    probe = "默认" if not overrides else "严酷探针 " + str(overrides)
    print(f"评测对象: {label} · episodes={args.episodes} · seed={args.seed} · 条件: {probe}")
    print("=" * 72)
    print(f"  成功率      {metrics['success_rate'] * 100:.1f}%")
    print(f"  平均奖励    {metrics['mean_reward']:.3f}")
    print(f"  平均步数    {metrics['mean_steps']:.1f}")
    print(f"  平均末距    {metrics['mean_final_dist']:.4f} m")

    out_dir = REPO_ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{Path(label).stem or 'random'}.json"
    payload = {"policy": label, "algo": algo_name if policy is not None else "random",
               "config": args.config, "env_kwargs": env_kwargs,
               "overrides": overrides, **metrics}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  结果已存: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
