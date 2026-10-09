"""固定训练程序：harness 只决定「什么时候训、拿哪些题去训」，不改「怎么训」。

这条边界是整个自学习闭环能不能排障的关键。如果让上层框架（或大模型）同时改
算法、改奖励、改采样、改评测，那么成功率一变，你永远说不清是哪一边带来的 ——
`skills/README.md` 里「代码变更与参数变更分开记账」说的就是这件事。

所以本模块刻意做得很笨：
    · 超参全部从 `configs/reach_sac.yaml` 的 `train:` 段读，代码里不留魔法数字；
    · 唯一能被 harness 改变的量是 `steps`（预算）、`seed`、`sampler`（题目分布）；
    · 只保存最终权重，不做 best-model 挑选 —— 挑模型属于评测环节，不能混进训练。

阶段 4 想让智能体去改奖励或训练配置时，改的应该是**传给这里的 config**，
并且必须把改了什么写进 meta 的 `config_hash`，让每次变化都可追溯。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "reach_sac.yaml"
SAC_KWARGS = ("learning_rate", "buffer_size", "batch_size", "gamma", "tau", "train_freq", "gradient_steps")


def load_train_config(config_path: str | Path = DEFAULT_CONFIG) -> dict:
    import yaml

    with open(config_path, "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    return {
        # 顶层可选键：reach（默认，单积分器）| perturbed（带延迟/增益噪声/漂移）。
        # 见 harness/env_factory.py。
        "env_factory": str(cfg.get("env_factory", "reach")),
        "env": dict(cfg.get("env", {})),
        "train": dict(cfg.get("train", {})),
        "eval": dict(cfg.get("eval", {})),
    }


def train_candidate(
    *,
    steps: int,
    seed: int = 0,
    sampler: Any = None,
    env_kwargs: dict | None = None,
    out_dir: str | Path = "",
    config_path: str | Path = DEFAULT_CONFIG,
    algo: str = "sac",
    device: str = "cpu",
    threads: int = 1,
    resume_from: str | Path = "",
) -> dict:
    """训一个候选策略，返回 ckpt 路径与训练账目。

    `sampler=None` 表示用环境自带的均匀采样（对照组）。
    `resume_from` 不为空时从已有权重继续训（round>1 时接着上一版学，
    这才是「迭代自学习」；每轮都从零开始的话，预算再大也只是重复第一次）。
    """
    import torch

    torch.set_num_threads(max(1, threads))
    try:
        torch.set_num_interop_threads(max(1, threads))
    except RuntimeError:
        pass

    from stable_baselines3 import SAC
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    cfg = load_train_config(config_path)
    # 必须在 make_reach_env 被取用之前安装：训练/采集/评测要指向同一个环境实现。
    from harness.env_factory import from_config

    from_config(cfg)
    from envs.reach_env import make_reach_env
    from harness.sampling import GoalSamplingWrapper, UniformGoalSampler

    train_cfg = dict(cfg["train"])
    base_env_kwargs = dict(env_kwargs if env_kwargs is not None else cfg["env"])

    if sampler is None:
        sampler = UniformGoalSampler(
            half_space=float(base_env_kwargs.get("half_space", 0.15)),
            min_goal_dist=float(base_env_kwargs.get("min_goal_dist", 0.08)),
            seed=seed,
        )

    def _make_env():
        env = make_reach_env(**base_env_kwargs)
        # 顺序是 Monitor(Wrapper(env))：采样注入要在 Monitor 之内，
        # 这样 Monitor 记的 episode 长度/回报仍然是真实环境的量。
        return Monitor(GoalSamplingWrapper(env, sampler))

    algo_name = str(algo or train_cfg.get("algo", "sac")).lower()
    if algo_name != "sac":
        raise ValueError(f"固定训练程序目前只钉了 sac（收到 {algo_name}）。换算法请先改 configs 再改这里。")

    algo_kwargs = {key: train_cfg[key] for key in SAC_KWARGS if key in train_cfg}
    started = time.time()

    replay_restored = 0
    if resume_from:
        # 继续训必须换环境：SB3 的 load() 不接受 vec_env，需要用 set_env 绑上
        # 带采样 wrapper 的新环境，否则会在旧环境（均匀采样）上训，实验组就白设了。
        model = SAC.load(str(resume_from), device=device)

        # 坑：SB3 存 .zip 时**默认不含 replay buffer**（它在 `_excluded_save_params` 里），
        # 所以 SAC.load() 之后 buffer 是 None，set_env 会新建一个空的。
        # 结果就是「每轮续训都从零经验开始重新探索」——权重延续了，数据全丢了，
        # 迭代式自学习会退化成每轮重新热身。这里显式把 buffer 一起存/取。
        # 顺序很重要：必须在 set_env 之前 load_replay_buffer，
        # 因为 _setup_model() 只在 buffer 为 None 时才新建。
        replay_pkl = Path(resume_from).with_name("candidate_replay.pkl")
        if replay_pkl.exists():
            model.load_replay_buffer(replay_pkl)
            replay_restored = int(model.replay_buffer.size())
        model.set_env(DummyVecEnv([_make_env]))
    else:
        model = SAC(
            policy="MlpPolicy",
            env=DummyVecEnv([_make_env]),
            seed=seed,
            device=device,
            verbose=0,
            policy_kwargs=dict(train_cfg.get("policy_kwargs", {})),
            **algo_kwargs,
        )

    model.learn(total_timesteps=int(steps), progress_bar=False)
    train_sec = time.time() - started

    out = Path(out_dir) if out_dir else REPO_ROOT / "runs" / f"{time.strftime('%Y%m%d_%H%M%S')}_candidate"
    out.mkdir(parents=True, exist_ok=True)
    ckpt = out / "candidate.zip"
    model.save(str(ckpt.with_suffix("")))
    # 与权重一起保存经验池，供下一轮真正「接着学」（见上面 resume 分支的说明）
    model.save_replay_buffer(str(out / "candidate_replay.pkl"))
    # 注意 BaseBuffer.size 是**方法**不是属性，写成 model.replay_buffer.size 会拿到
    # 一个 bound method（int() 直接 TypeError）。
    buffer = getattr(model, "replay_buffer", None)
    replay_size = int(buffer.size()) if buffer is not None else 0

    from harness.sampling import init_dist_histogram

    return {
        "ckpt": str(ckpt),
        "algo": algo_name,
        "steps": int(steps),
        "seed": int(seed),
        "resumed_from": str(resume_from) if resume_from else "",
        "replay_restored_transitions": replay_restored,
        "replay_saved_transitions": replay_size,
        "device": device,
        "threads": int(torch.get_num_threads()),
        "train_seconds": round(train_sec, 1),
        "steps_per_sec": round(int(steps) / train_sec, 2) if train_sec > 0 else None,
        "env_kwargs": base_env_kwargs,
        "sampler": sampler.describe(),
        "init_dist": init_dist_histogram(list(getattr(sampler, "history", []))),
        "hyper": {**algo_kwargs, "policy_kwargs": dict(train_cfg.get("policy_kwargs", {}))},
    }
