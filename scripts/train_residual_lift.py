#!/usr/bin/env python
"""训练 Lift 的 bounded-residual SAC，并与脚本 base controller 对齐评测口径。

2026-09-28（A-5，监管增补四 裁定 9 / 增补五 §8）：SAC 无归一化 ⇒ 输入契约状态是
`not_applicable_unnormalized`，而**只有声明不算**，必须落盘证据。本脚本从此前瞻记录
「训练期 raw obs 逐维 absmax」与「闭环 raw obs 相对该 absmax 的越界比例」，写 `obs_stats.json`。
**只对未来的 run 生效**：09-24 的 residual 臂不重跑（用户指令 + 增补五 §8 A-5），
在补齐这份证据之前它们维持 INVALID / `not_applicable_unnormalized`，不得放行。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")
sys.modules.setdefault("torch.utils.tensorboard", None)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts._venv import ensure_venv  # noqa: E402
ensure_venv("stable_baselines3", "numpy", "torch")

import gymnasium as gym  # noqa: E402
import numpy as np  # noqa: E402
from stable_baselines3 import SAC  # noqa: E402

from envs.residual_lift import ResidualLiftEnv  # noqa: E402
from harness.env_factory import PINNED_OBJECT_SEED, pinned_object_rng, reset_contact  # noqa: E402


OBS_TOLERANCE = 0.05


class ObsStatsRecorder(gym.Wrapper):
    """裁定 9 的 ②③：逐维记录 raw obs 的 |x| 上界，并统计相对给定 bound 的越界比例。

    SAC 没有 replay buffer 可事后取证（`model_final.zip` 里不存 obs），所以只能在训练期前瞻落盘。
    `bound=None` 时只记 absmax；`set_bound(train_absmax)` 后才统计越界（用于闭环侧 ③）。
    """

    def __init__(self, env, tag: str):
        super().__init__(env)
        self.tag = tag
        self.absmax = None
        self.n_obs = 0
        self.bound = None
        self.n_elems = 0
        self.n_exceed = 0

    def __getattr__(self, name):
        # gymnasium 1.x 的 Wrapper 不再自动转发属性；evaluate()/reset_env() 会直接摸底层 env 的
        # _obs / _env / hist / tasks_done，所以这里显式转发（双下划线除外，避免递归）。
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(object.__getattribute__(self, "env"), name)

    def set_bound(self, bound):
        self.bound = None if bound is None else np.asarray(bound, dtype=np.float64).reshape(-1)

    def _record(self, obs):
        a = np.abs(np.asarray(obs, dtype=np.float64).reshape(-1))
        self.absmax = a.copy() if self.absmax is None else np.maximum(self.absmax, a)
        self.n_obs += 1
        if self.bound is not None and self.bound.size == a.size:
            self.n_elems += int(a.size)
            self.n_exceed += int(np.count_nonzero(a > self.bound))

    def reset(self, **kwargs):
        out = self.env.reset(**kwargs)
        self._record(out[0] if isinstance(out, tuple) else out)
        return out

    def step(self, action):
        out = self.env.step(action)
        self._record(out[0])
        return out

    def dump(self) -> dict:
        frac = (self.n_exceed / self.n_elems) if self.n_elems else None
        return {"tag": self.tag, "n_obs_recorded": self.n_obs,
                "obs_dim": (None if self.absmax is None else int(self.absmax.size)),
                "raw_obs_absmax_global": (None if self.absmax is None
                                          else round(float(self.absmax.max()), 6)),
                "raw_obs_absmax_per_dim": (None if self.absmax is None
                                           else [round(float(x), 6) for x in self.absmax]),
                "bound_exceed_elems": self.n_exceed, "bound_elems": self.n_elems,
                "bound_exceed_frac": (None if frac is None else round(frac, 6)),
                "bound_tolerance": (None if self.bound is None else OBS_TOLERANCE),
                "bound_satisfied": (None if frac is None else bool(frac <= OBS_TOLERANCE))}


def make_env(args, tag: str | None = None):
    with pinned_object_rng(PINNED_OBJECT_SEED):
        env = ResidualLiftEnv(obs_mode="state", horizon=args.horizon,
                              reward_shaping=True, hist=args.hist,
                              residual_scale=args.residual_scale,
                              residual_phases=args.residual_phases)
    return env if tag is None else ObsStatsRecorder(env, tag)


def reset_env(env, seed):
    obs = reset_contact(env, seed)
    if getattr(env, "hist", 1) > 1:
        env._hist_buf = []
        obs = env._obs(env._env._get_observations())
    return np.asarray(obs)


def evaluate(model, args, episodes=20, seed_base=5000, tag="eval", bound=None):
    env = make_env(args, tag=tag)
    env.set_bound(bound)
    successes = tasks = 0
    rewards = []
    residual_norm = 0.0
    residual_steps = 0
    for i in range(episodes):
        obs = reset_env(env, seed_base + i)
        ep_r = 0.0
        ep_success = False
        for _ in range(args.horizon):
            action, _ = model.predict(obs, deterministic=True)
            obs, r, term, trunc, info = env.step(action)
            ep_r += float(r)
            applied = np.asarray(info.get("residual_action", 0.0))
            residual_norm += float(np.linalg.norm(applied))
            residual_steps += int(np.any(np.asarray(info.get("residual_gate", 0.0))))
            ep_success = ep_success or bool(info.get("success", False))
            if term or trunc:
                break
        tasks += int(env.tasks_done)
        successes += int(ep_success)
        rewards.append(ep_r)
    obs_stats = env.dump()
    env.close()
    return {"episodes": episodes, "success": successes,
            "success_rate": successes / episodes, "tasks_done": tasks,
            "mean_reward": float(np.mean(rewards)),
            "mean_residual_norm": residual_norm / max(1, residual_steps),
            "residual_active_steps": residual_steps,
            "obs_stats": obs_stats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=60000)
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eval-freq", type=int, default=10000)
    ap.add_argument("--eval-episodes", type=int, default=5)
    ap.add_argument("--residual-scale", type=float, default=0.25)
    ap.add_argument("--hist", type=int, default=1)
    ap.add_argument("--residual-phases", default="grasp,lift",
                    help="允许 residual 的 phase，默认只在接触阶段启用")
    ap.add_argument("--run-name", default="")
    args = ap.parse_args()
    args.residual_phases = tuple(x.strip() for x in args.residual_phases.split(",") if x.strip())
    name = args.run_name or "sac_lift_bounded_residual"
    out = ROOT / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}_{name}"
    out.mkdir(parents=True, exist_ok=True)
    env = make_env(args, tag="train")
    model = SAC("MlpPolicy", env, seed=args.seed, verbose=0,
                learning_rate=3e-4, buffer_size=100000, batch_size=256,
                learning_starts=1000, train_freq=1, gradient_steps=1,
                policy_kwargs={"net_arch": [256, 256]})
    curve = []
    for target in range(args.eval_freq, args.steps + 1, args.eval_freq):
        model.learn(total_timesteps=args.eval_freq, reset_num_timesteps=False)
        ev = evaluate(model, args, episodes=args.eval_episodes, seed_base=2000 + target)
        ev["step"] = target
        curve.append(ev)
        print(f"[residual] step={target} success={ev['success_rate']:.1%} "
              f"tasks={ev['tasks_done']} reward={ev['mean_reward']:.2f}", flush=True)
    model.save(str(out / "model_final"))
    train_stats = env.dump()
    # 裁定 9③：闭环 raw obs 相对**训练期** absmax 的越界比例必须 <= 0.05；
    # bound 只能在训练结束后装（训练中 absmax 还在长），所以只有这次 20 局终评带越界统计。
    final = evaluate(model, args, episodes=20, tag="closed_loop_final",
                     bound=train_stats["raw_obs_absmax_per_dim"])
    (out / "eval_curve.json").write_text(json.dumps(curve, indent=2))
    (out / "result.json").write_text(json.dumps(final, indent=2))
    (out / "config.json").write_text(json.dumps(vars(args), indent=2))
    (out / "obs_stats.json").write_text(json.dumps({
        "normalization": "none",
        "input_contract_status": "not_applicable_unnormalized",
        "ruling": "监管增补四 裁定 9：无归一化学习策略的 4 条准入（声明 + 训练期逐维 absmax + "
                  "闭环越界 <= 0.05 + threshold 来源），只有声明不算",
        "threshold_source": "训练期 raw obs 逐维 absmax（本 run 实测，见 train.raw_obs_absmax_per_dim）；"
                            "SAC 无归一化 ⇒ 没有 normalizer stats 可引用，阈值只能取自训练分布本身",
        "tolerance": OBS_TOLERANCE,
        "train": train_stats,
        "closed_loop_final": final.get("obs_stats"),
        "intermediate_evals": [c.get("obs_stats") for c in curve],
        "note": "本文件由 A-5 前瞻落盘；09-24 的 residual 臂没有它，维持 INVALID，不重跑",
        "generated_at": f"{datetime.now():%Y-%m-%dT%H:%M:%S}",
    }, indent=2))
    env.close()
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
