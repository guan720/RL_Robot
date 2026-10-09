"""独立评测模块：训练与评测必须解耦。

为什么要单独一个模块？因为「训练时的 reward 曲线」和「固定 seed 下的成功率」是两件事：
  - 曲线好看可能只是探索运气；
  - 成功率才回答「把这个策略冻结，换一批没见过的初始状态，还能不能成功」。

后面接 harness 时，这个函数就是「新版本能不能发布」的门槛。

policy 支持三种形态：
  None            -> 随机策略（基线，回答「不学习能得多少分」）
  SB3 模型对象     -> 用 model.predict()
  任意可调用对象   -> policy(obs) -> action
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np


def evaluate_reach(
    policy: Any = None,
    env_kwargs: dict | None = None,
    n_episodes: int = 50,
    seed: int = 12345,
    deterministic: bool = True,
) -> dict:
    from envs.reach_env import make_reach_env

    env = make_reach_env(**(env_kwargs or {}))
    rng = np.random.default_rng(seed)
    episodes: list[dict] = []

    for ep in range(n_episodes):
        obs, _ = env.reset(seed=seed + ep)
        total_reward = 0.0
        steps = 0
        success = False
        info: dict = {}
        while True:
            if policy is None:
                action = rng.uniform(-1.0, 1.0, size=env.action_space.shape).astype(np.float32)
            elif hasattr(policy, "predict"):
                action, _ = policy.predict(obs, deterministic=deterministic)
            elif isinstance(policy, Callable):
                action = policy(obs)
            else:
                raise TypeError(f"不支持的 policy 类型: {type(policy)}")

            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += float(reward)
            steps += 1
            if terminated or truncated:
                break

        episodes.append({
            "episode": ep,
            "seed": seed + ep,
            "steps": steps,
            "reward": round(total_reward, 4),
            "success": bool(info.get("success", False)),
            "final_dist": round(float(info.get("dist", float("nan"))), 5),
        })

    n = max(1, len(episodes))
    return {
        "n_episodes": len(episodes),
        "seed": seed,
        "deterministic": deterministic,
        "success_rate": round(sum(e["success"] for e in episodes) / n, 4),
        "mean_reward": round(sum(e["reward"] for e in episodes) / n, 4),
        "mean_steps": round(sum(e["steps"] for e in episodes) / n, 2),
        "mean_final_dist": round(sum(e["final_dist"] for e in episodes) / n, 5),
        "episodes": episodes,
    }
