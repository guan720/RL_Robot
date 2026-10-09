#!/usr/bin/env python
"""阶段 2：在正反向交替搬运环境上训练 SAC，并把「覆盖率」当成一等公民记录下来。

和阶段 1 的 train_reach.py 相比，这个脚本多做了三件事，都是阶段 2 的研究问题逼出来的：

1. **评测指标换了**。Reach 只需要成功率；搬运任务要同时看
      · 完成了多少个 task（一局 400 步里会连续做很多个）
      · 正向 / 反向各自成功多少（会不会偏科）
      · 触发了几次规则式救场（= 策略自己搞不定、要外部兜底）
      · 起始状态覆盖了多少格子、分布熵多少（= 学习数据有没有塌缩）
   SB3 自带的 EvalCallback 只会记 mean_reward / mean_length，所以下面自己写了一个
   TransportEvalCallback，它调用 eval/transport_eval.evaluate_transport —— 和
   compare_reset_modes.py 用的是**同一把尺子**，两张表的数字才能直接对比。

2. **训练用的复位模式可以切**（--mode alternate|fixed）。这本身就是一个对照实验：
      alternate（reset-free）：起始状态由策略自己上一轮的放置点决定 -> 分布内生、可能收窄
      fixed：每个 task 都重采样 -> 分布外生、均匀，但要付复位成本
   两种模式各训一个策略，再用同一套冻结评测比较，就能回答
   「交替省下的复位成本，是不是用学习分布的多样性换来的」。

3. **训练结束后做「跨模式」冻结评测**：把在 alternate 下训出来的策略拿到 fixed 下评一遍，
   反之亦然。这是检查策略有没有过拟合到自己的起始状态分布。

耗时预期：本机是共享节点（load average 常在 500 上下），单线程 SAC 约 10–15 步/秒，
40000 步大约 45–70 分钟。跑长任务请用（普通 `nohup &` 会被杀，必须带 setsid）：

    RUN=runs/$(date +%Y%m%d_%H%M%S)_sac_transport
    OMP_NUM_THREADS=1 setsid nohup python -u scripts/train_transport.py \
        > /tmp/train_transport.log 2>&1 < /dev/null & disown
    tail -f /tmp/train_transport.log

用法：
    python scripts/train_transport.py --steps 3000                 # 冒烟，几分钟
    python scripts/train_transport.py                              # 全量，alternate 模式
    python scripts/train_transport.py --mode fixed                 # 对照组：每次人工复位
    python scripts/train_transport.py --config configs/transport_sac.yaml --seed 1
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

ensure_venv("stable_baselines3", "yaml", "gymnasium", "numpy")

import numpy as np  # noqa: E402
import yaml  # noqa: E402

SAC_KWARGS = ("learning_rate", "buffer_size", "batch_size", "gamma", "tau", "train_freq", "gradient_steps")

# 训练过程中要盯的几个数（也是最终画图的纵轴）
TRACK_KEYS = ("tasks_done", "tasks_per_1k_steps", "success_rate", "success_forward", "success_backward",
              "manual_resets", "start_cells", "entropy_start", "coverage_start", "place_cells",
              "endogenous_start_share", "mean_reward",
              # 扰动环境的过程指标：RL 有没有学会「轻拿轻放」，看 push 次数掉不掉最直观
              "slip_events", "push_events", "pushes_per_task")


# 这几行必须在 ensure_venv 之后、且在文件顶部设好 OMP_NUM_THREADS 之后才 import，
# 因为 stable_baselines3 会把 torch 拉起来，而 torch 的线程数在 import 时就定型了。
from stable_baselines3.common.callbacks import BaseCallback  # noqa: E402


class TransportEvalCallback(BaseCallback):
    """每 eval_freq 步做一次「冻结策略」独立评测，记录任务数 / 正反向 / 覆盖率。

    为什么不用 SB3 自带的 EvalCallback？因为它只存 mean_reward 和 mean_length，
    而阶段 2 要回答的问题全在 info 里（完成几个 task、正反向各多少、覆盖多少格子、
    触发了几次救场）。所以自己写一个，指标直接调 eval/transport_eval.py ——
    和 compare_reset_modes.py 用**同一把尺子**，两张表的数字才能直接对比。

    评测环境是**另外新建**的：拿训练环境去评测会打断正在进行的 episode，
    既污染回放池里的数据，也让曲线不可比。
    """

    def __init__(self, run_dir: Path, env_kwargs: dict, eval_freq: int, budget_steps: int,
                 seeds: list[int], reset_cost_steps: float, reset_mode: str,
                 env_factory: str = "abstract") -> None:
        super().__init__(verbose=0)
        self.run_dir = run_dir
        self.env_kwargs = dict(env_kwargs)
        self.env_factory = env_factory
        self.eval_freq = max(1, int(eval_freq))
        self.budget_steps = budget_steps
        self.seeds = list(seeds)
        self.reset_cost_steps = reset_cost_steps
        self.reset_mode = reset_mode
        self.history: list[dict] = []
        self.best_score = -1.0
        self.started = time.time()
        self.jsonl = run_dir / "stage2_eval.jsonl"

    def _on_step(self) -> bool:
        # n_calls 是「这个 callback 被调过多少次」，单环境时等于已走的环境步数
        if self.n_calls % self.eval_freq != 0:
            return True
        self.evaluate(self.num_timesteps)
        return True

    def evaluate(self, num_timesteps: int) -> dict:
        from eval.transport_eval import evaluate_transport

        report = evaluate_transport(
            self.model, self.env_kwargs, budget_steps=self.budget_steps, seeds=self.seeds,
            deterministic=True, reset_mode=self.reset_mode, reset_cost_steps=self.reset_cost_steps,
            env_factory=self.env_factory,
        )
        mean = report["mean"]
        row: dict = {"num_timesteps": int(num_timesteps),
                     "wall_sec": round(time.time() - self.started, 1),
                     "mean_reward": _mean_reward(self.model)}
        row.update({k: mean.get(k) for k in TRACK_KEYS if k != "mean_reward"})
        row["std_tasks_done"] = report["std"].get("tasks_done")
        self.history.append(row)
        with open(self.jsonl, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

        score = float(mean.get("tasks_per_1k_steps") or 0.0)
        star = ""
        if score > self.best_score:
            self.best_score = score
            self.model.save(str(self.run_dir / "best_model"))
            star = "  <- best"
        print(f"  [eval @ {num_timesteps:>7} 步] 任务 {row['tasks_done']:>6.1f}"
              f"  成功率 {row['success_rate'] * 100:>5.1f}%"
              f"  正/反 {row['success_forward']:>5.1f}/{row['success_backward']:<5.1f}"
              f"  救场 {row['manual_resets']:>5.1f}"
              f"  起始格子 {row['start_cells']:>5.1f}  熵 {row['entropy_start']:.3f}{star}",
              flush=True)
        self.save_npz()
        return row

    def save_npz(self) -> None:
        """存成 npz，让 show_curve.py / plot_stage2.py 能直接读。"""
        arrays = {"timesteps": np.array([h["num_timesteps"] for h in self.history], dtype=np.int64)}
        for key in TRACK_KEYS + ("std_tasks_done", "wall_sec"):
            arrays[key] = np.array([np.nan if h.get(key) is None else h[key] for h in self.history],
                                   dtype=np.float64)
        np.savez(self.run_dir / "evaluations_transport.npz", **arrays)


def _mean_reward(model) -> float:
    """训练侧的平均单局回报（拿不到就返回 nan）。

    为什么不读 model.logger.name_to_value？因为 SB3 每次 dump() 之后会把它清空，
    callback 里读到的几乎总是空的。真正稳定的是 model.ep_info_buffer：
    Monitor 包装器把每局的 reward/length 塞进这个 deque（最近 100 局）。
    """
    buffer = getattr(model, "ep_info_buffer", None)
    if not buffer:
        return float("nan")
    try:
        return round(float(np.mean([float(ep["r"]) for ep in buffer])), 4)
    except Exception:
        return float("nan")


def fill_demo_buffer(model, env_kwargs: dict, env_factory: str, demo_steps: int,
                     kind: str = "pd", kp: float = 1.0, kd: float = 0.5, gain: float = 0.7,
                     seed: int = 0) -> dict:
    """用脚本控制器跑 demo_steps 步，把转移**直接塞进 SAC 的回放池**再开始训练。

    为什么需要这一步（实测驱动，不是抄论文）：
        扰动环境里 SAC 从零训 50000 步只做出 1 个任务（runs/20260923_1147*_sac_transport_perturbed_*）。
        原因很具体：SAC 的探索噪声初始 log_std=0 -> 动作标准差 1 -> 经过 tanh 后几乎均匀铺满
        [-1,1]，也就是每步 4cm 的乱撞；而这个环境里「进入抓取圈那一刻速度超过 3cm 就把物体撞飞」，
        所以**探索动作本身在破坏场景**：越探索，物体被打得越远，+2 的抓取奖励越拿不到，
        Q 函数没有任何成功样本可以自举 -> 一直卡在 0。
        同一个网络结构、同一个奖励，在理想环境里 7500~10000 步就起飞（阶段 2 实测），
        差别只在于「乱动会不会把任务搞坏」。

    这正是 SERL / HIL-SERL 在真机上的做法：先放少量示范进回放池，再开在线 RL。
    对应到本项目最终要做的 harness，就是「LLM/技能层接管几次 -> 纠正轨迹进回放池 -> 续训」。
    这里用 PD 控制器当「接管者」，因为它不需要人，可复现。

    两个实现细节（都踩过）：
        · SB3 2.x 的回放池签名是 add(obs, next_obs, action, reward, done, infos)，
          和 1.x 的顺序不同；action 存的是**环境空间**的 [-1,1] 值（训练时内部再 unsquash）。
        · 环境的 truncated（400 步到点）在 SB3 里会被当成真终止，因为 info 里没有
          "TimeLimit.truncated" 键。这与正常训练路径完全一致（DummyVecEnv 也不加这个键），
          所以示范数据和在线数据的口径一样，不引入新的偏差。
    """
    from eval.transport_eval import make_env
    from scripts.compare_reset_modes import PDController, PController

    env = make_env(dict(env_kwargs), env_factory)
    controller = (PDController(seed=seed, easy_radius=None, kp=kp, kd=kd) if kind == "pd"
                  else PController(seed=seed, easy_radius=None, gain=gain))
    prm = {"half": env.half, "gap": env.gap, "action_scale": env.action_scale}
    on_episode_start = getattr(controller, "on_episode_start", None)

    filled = 0
    tasks = 0
    episodes = 0
    obs, info = env.reset(seed=seed)
    if on_episode_start is not None:
        on_episode_start(obs, info)
    # 环境的计数器每次 reset() 会清零，所以任务数必须**逐段累加**（阶段 2 踩过的同一个坑）
    last_done = int(info["tasks_done"])
    while filled < demo_steps:
        action = np.asarray(controller.act(obs, info, prm), dtype=np.float32).reshape(1, 2)
        next_obs, reward, terminated, truncated, info = env.step(action[0])
        model.replay_buffer.add(
            obs.reshape(1, -1).astype(np.float32), next_obs.reshape(1, -1).astype(np.float32),
            action, np.array([reward], dtype=np.float32),
            np.array([bool(terminated or truncated)], dtype=np.float32), [info],
        )
        filled += 1
        if int(info["tasks_done"]) > last_done:
            tasks += int(info["tasks_done"]) - last_done
            last_done = int(info["tasks_done"])
        obs = next_obs
        if terminated or truncated:
            episodes += 1
            obs, info = env.reset(seed=seed + filled)
            if on_episode_start is not None:
                on_episode_start(obs, info)
            last_done = int(info["tasks_done"])
    env.close()
    return {"demo_steps": filled, "demo_policy": kind, "demo_episodes": episodes,
            "demo_tasks": tasks,
            "buffer_pos": int(model.replay_buffer.pos), "buffer_full": bool(model.replay_buffer.full)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "transport_sac.yaml"))
    parser.add_argument("--steps", type=int, default=0, help="覆盖 config 里的 total_timesteps")
    parser.add_argument("--mode", default="", choices=["", "alternate", "fixed"],
                        help="训练用的复位模式：alternate=reset-free 交替（默认，取 config）；fixed=每次人工复位")
    parser.add_argument("--recovery-mode", default="", choices=["", "resample", "home"],
                        help="救场时把物体放哪：resample=均匀重采样 / home=固定 home 点")
    parser.add_argument("--seed", type=int, default=-1, help="覆盖 config 里的训练 seed")
    parser.add_argument("--device", default="cpu", help="这个网络很小，CPU 通常比 GPU 快")
    parser.add_argument("--threads", type=int, default=1, help="torch 线程数；小网络用 1 最快")
    parser.add_argument("--run-name", default="transport")
    parser.add_argument("--init-from", default="",
                        help="从已有 model.zip 继续训练（微调），而不是从零初始化。"
                             "对应 harness 的「环境变了 -> 旧策略掉分 -> 在它基础上续训」这一环")
    parser.add_argument("--demo-steps", type=int, default=0,
                        help="先用脚本控制器跑这么多步、把转移塞进回放池再开始训练（0 = 关闭）。"
                             "扰动环境里 SAC 从零探索起不来，必须给少量示范（SERL/HIL-SERL 的做法）")
    parser.add_argument("--demo-policy", default="pd", choices=["pd", "perfect"],
                        help="示范由谁产生：pd = 带速度反馈的比例微分控制（默认，最强脚本基线）；"
                             "perfect = 纯比例控制")
    parser.add_argument("--demo-kp", type=float, default=1.0)
    parser.add_argument("--demo-kd", type=float, default=0.5)
    parser.add_argument("--demo-gain", type=float, default=0.7)
    parser.add_argument("--env-factory", default="", choices=["", "abstract", "perturbed"],
                        help="覆盖 config 顶层的 env_factory：abstract=理想单积分器（阶段2原始结果），"
                             "perturbed=带延迟/增益/漂移/负载/限速/滑落的版本")
    parser.add_argument("--no-cross-eval", action="store_true", help="跳过训练后的跨模式评测")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with open(args.config, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    env_kwargs = dict(config.get("env", {}))
    train_cfg = dict(config.get("train", {}))
    eval_cfg = dict(config.get("eval", {}))
    cmp_cfg = dict(config.get("compare", {}))
    # 用哪套环境实现由 config 顶层的 env_factory 决定（命令行可覆盖）：
    #   abstract   envs/bidirectional_pickplace.py  理想单积分器（阶段 2 原始结果）
    #   perturbed  envs/transport_perturbed.py      加了执行延迟/增益/漂移/负载/限速/滑落
    # 两者共用同一份评测代码（eval/transport_eval.py），所以指标口径一致、数字可直接对比。
    env_factory = (args.env_factory or str(config.get("env_factory", "abstract"))).lower()

    if args.steps:
        train_cfg["total_timesteps"] = args.steps
    if args.seed >= 0:
        train_cfg["seed"] = args.seed
    if args.mode:
        env_kwargs["reset_mode"] = args.mode
    if args.recovery_mode:
        env_kwargs["recovery_mode"] = args.recovery_mode
    env_kwargs.setdefault("reset_mode", "alternate")

    reset_cost_steps = float(cmp_cfg.get("reset_cost_steps", 30.0))
    eval_seeds = [int(x) for x in eval_cfg.get("seeds", [0, 1, 2])]
    eval_budget = int(eval_cfg.get("steps", 20000))
    # 训练途中的评测要便宜：预算小一点、seed 少一点，否则评测比训练还慢
    inline_budget = int(eval_cfg.get("inline_steps", 4000))
    inline_seeds = [int(x) for x in eval_cfg.get("inline_seeds", eval_seeds[:1])]

    import torch

    torch.set_num_threads(max(1, args.threads))
    try:
        torch.set_num_interop_threads(max(1, args.threads))
    except RuntimeError:
        pass  # 已经跑过并行任务后不能再改，忽略即可

    algo = str(train_cfg.get("algo", "sac")).lower()
    total_timesteps = int(train_cfg.get("total_timesteps", 40000))
    seed = int(train_cfg.get("seed", 0))
    reset_mode = env_kwargs["reset_mode"]
    recovery_mode = env_kwargs.get("recovery_mode", "resample")

    run_dir = REPO_ROOT / "runs" / f"{time.strftime('%Y%m%d_%H%M%S')}_sac_{args.run_name}_{reset_mode}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.resolved.yaml").write_text(
        yaml.safe_dump({"env_factory": env_factory, "env": env_kwargs, "train": train_cfg,
                        "eval": eval_cfg, "compare": cmp_cfg},
                       allow_unicode=True), encoding="utf-8")

    from stable_baselines3 import SAC
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    from eval.transport_eval import evaluate_transport, make_env

    print("=" * 78)
    print(f"[SAC] 正反向交替搬运训练 · steps={total_timesteps} · seed={seed}")
    print(f"      复位模式 = {reset_mode}（{'reset-free 交替' if reset_mode == 'alternate' else '每个 task 人工复位'}）"
          f" · 救场 = {recovery_mode}")
    print(f"      环境实现 = {env_factory}"
          f"{'（带扰动）' if env_factory == 'perturbed' else '（理想单积分器）'}")
    print(f"      device={args.device} · threads={torch.get_num_threads()} · run 目录: {run_dir}")
    print("=" * 78)

    # 三段式对比（和阶段 1 一样的纪律）：随机 / 未训练网络 / 训练后
    probe_kwargs = dict(env_kwargs, reset_mode=reset_mode)
    baseline_random = evaluate_transport(None, probe_kwargs, budget_steps=eval_budget,
                                        seeds=eval_seeds, reset_cost_steps=reset_cost_steps,
                                        env_factory=env_factory)
    _print_eval("(1/3) 随机策略基线  ", baseline_random)

    vec_env = DummyVecEnv([lambda: Monitor(make_env(env_kwargs, env_factory))])
    algo_kwargs = {key: train_cfg[key] for key in SAC_KWARGS if key in train_cfg}
    model = SAC(
        policy="MlpPolicy",
        env=vec_env,
        seed=seed,
        device=args.device,
        verbose=0,               # 自己打评测行，SB3 的 rollout 日志太吵
        tensorboard_log=str(run_dir / "tb"),
        policy_kwargs=dict(train_cfg.get("policy_kwargs", {})),
        **algo_kwargs,
    )
    if args.init_from:
        # 微调入口：加载旧版本的权重 + 优化器状态 + 自动温度系数 alpha，然后继续 learn()。
        # 这正是上层 harness「跨回合学习闭环」里最常见的一种参数更新：环境/任务变了，
        # 旧策略从满分掉到 X%，在它的基础上续训，而不是每一轮都从零开始。
        # 两个必须知道的事实：
        #   1. SB3 存出的 .zip **不含 replay buffer**，所以续训开始时回放池是空的，
        #      前面若干步会重新填一遍（阶段 3 的 harness 踩过这个坑）；
        #   2. 旧的探索温度 alpha 会被一起恢复。旧策略已经收敛到较小的动作噪声，
        #      所以续训不会像从零开始时那样大幅乱撞——在「撞飞物体」型环境里这很关键。
        model = SAC.load(args.init_from, env=vec_env, device=args.device)
        model.tensorboard_log = str(run_dir / "tb")
        print(f"  [微调] 从 {args.init_from} 继续训练（回放池为空，会自动重填）")
    n_params = sum(p.numel() for p in model.policy.parameters())
    print(f"  策略网络参数量：{n_params}（结构 {train_cfg.get('policy_kwargs', {}).get('net_arch')}）")

    baseline_untrained = evaluate_transport(model, probe_kwargs, budget_steps=eval_budget,
                                            seeds=eval_seeds, deterministic=True,
                                            reset_cost_steps=reset_cost_steps,
                                            env_factory=env_factory)
    _print_eval("(2/3) 未训练的网络  ", baseline_untrained)

    demo_info: dict = {}
    if args.demo_steps > 0:
        # 必须在 baseline_untrained 之后填池：那一行要如实反映「网络本身还没学过」，
        # 填了示范再评就看不出起点了。
        demo_info = fill_demo_buffer(
            model, env_kwargs, env_factory, args.demo_steps, kind=args.demo_policy,
            kp=args.demo_kp, kd=args.demo_kd, gain=args.demo_gain, seed=seed,
        )
        print(f"  [示范预填] {args.demo_policy} 控制器跑了 {demo_info['demo_steps']} 步"
              f"（{demo_info['demo_episodes']} 局 / 完成 {demo_info['demo_tasks']} 个任务）"
              f" -> 回放池 {demo_info['buffer_pos']}/{train_cfg.get('buffer_size', 100000)}"
              f"{'（已满）' if demo_info['buffer_full'] else ''}", flush=True)

    callback = TransportEvalCallback(
        run_dir, dict(env_kwargs), int(train_cfg.get("eval_freq", 2500)),
        inline_budget, inline_seeds, reset_cost_steps, reset_mode,
        env_factory,
    )
    started = time.time()
    model.learn(total_timesteps=total_timesteps, callback=callback, progress_bar=False)
    train_sec = time.time() - started
    model.save(str(run_dir / "model_final"))
    callback.evaluate(total_timesteps)          # 收尾再评一次，保证曲线最后一个点是最终模型
    print(f"  训练耗时 {train_sec:.1f} 秒 = {train_sec / 60:.1f} 分钟"
          f"（{total_timesteps / max(train_sec, 1e-6):.1f} 步/秒）")

    trained = evaluate_transport(model, probe_kwargs, budget_steps=eval_budget, seeds=eval_seeds,
                                 deterministic=True, reset_cost_steps=reset_cost_steps,
                                 env_factory=env_factory)
    _print_eval("(3/3) 训练后的网络  ", trained)

    cross = {}
    if not args.no_cross_eval:
        # 跨模式评测：在 alternate 下训出来的策略，拿到 fixed 下还行不行？
        # 这是「策略有没有过拟合到自己的起始状态分布」的检查，也是阶段 2 的核心疑问之一。
        other = "fixed" if reset_mode == "alternate" else "alternate"
        cross[other] = evaluate_transport(model, dict(env_kwargs, reset_mode=other),
                                          budget_steps=eval_budget, seeds=eval_seeds,
                                          deterministic=True, reset_mode=other,
                                          reset_cost_steps=reset_cost_steps,
                                          env_factory=env_factory)
        print(f"\n  [跨模式冻结评测] 在 {other} 模式下："
              f" 任务 {cross[other]['mean']['tasks_done']:.1f}"
              f"  成功率 {cross[other]['mean']['success_rate'] * 100:.1f}%"
              f"  起始格子 {cross[other]['mean']['start_cells']:.1f}"
              f"  起始熵 {cross[other]['mean']['entropy_start']:.3f}"
              f"  复位 {cross[other]['mean']['total_resets']:.0f}")

    _print_final_summary(baseline_untrained, trained, reset_mode)

    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": 2,
        "algo": algo,
        "env_factory": env_factory,
        "total_timesteps": total_timesteps,
        "seed": seed,
        "reset_mode": reset_mode,
        "recovery_mode": recovery_mode,
        "init_from": args.init_from or None,
        "demo": demo_info or None,
        "device": args.device,
        "threads": torch.get_num_threads(),
        "train_seconds": round(train_sec, 1),
        "steps_per_second": round(total_timesteps / max(train_sec, 1e-6), 2),
        "policy_params": n_params,
        "env_kwargs": env_kwargs,
        "eval": {
            "budget_steps_per_seed": eval_budget,
            "seeds": eval_seeds,
            "reset_cost_steps": reset_cost_steps,
            "random_policy": _slim(baseline_random),
            "untrained_model": _slim(baseline_untrained),
            "trained_model": _slim(trained),
            "cross_mode": {k: _slim(v) for k, v in cross.items()},
        },
        "artifacts": {
            "final_model": str(run_dir / "model_final.zip"),
            "best_model": str(run_dir / "best_model.zip"),
            "eval_jsonl": str(callback.jsonl),
            "eval_npz": str(run_dir / "evaluations_transport.npz"),
            "tensorboard": str(run_dir / "tb"),
        },
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "eval_trained.json").write_text(json.dumps(trained, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    print(f"\n[已保存] {run_dir / 'result.json'}")
    print(f"[下一步] python scripts/plot_stage2.py --train {run_dir}")
    print(f"[对照  ] python scripts/compare_reset_modes.py --policies ckpt --ckpt {run_dir / 'model_final.zip'}")
    vec_env.close()
    return 0


def _slim(report: dict) -> dict:
    """result.json 里只留汇总，不留每局的格子计数（太大）。"""
    return {"mean": {k: v for k, v in report["mean"].items()
                     if not k.endswith("_cell_counts") and k != "start_sources"},
            "std": report["std"], "reset_mode": report["reset_mode"],
            "recovery_mode": report["recovery_mode"]}


def _print_eval(tag: str, report: dict) -> None:
    m = report["mean"]
    print(f"  {tag}  任务 {m['tasks_done']:>7.1f}  成功率 {m['success_rate'] * 100:>5.1f}%"
          f"  正/反 {m['success_forward']:>6.1f}/{m['success_backward']:<6.1f}"
          f"  救场 {m['manual_resets']:>5.0f}  起始格子 {m['start_cells']:>5.1f}"
          f"  熵 {m['entropy_start']:.3f}  吞吐 {m['throughput_per_1k']:>6.2f}/千步", flush=True)


def _print_final_summary(untrained: dict, trained: dict, reset_mode: str) -> None:
    u, t = untrained["mean"], trained["mean"]
    print("\n" + "=" * 78)
    print("怎么读这个结果")
    print("=" * 78)
    print(f"  完成任务数：{u['tasks_done']:.1f} -> {t['tasks_done']:.1f}"
          f"（{t['tasks_done'] - u['tasks_done']:+.1f}）")
    print(f"  每任务成功率：{u['success_rate'] * 100:.1f}% -> {t['success_rate'] * 100:.1f}%")
    print(f"  正向/反向：{u['success_forward']:.0f}/{u['success_backward']:.0f}"
          f" -> {t['success_forward']:.0f}/{t['success_backward']:.0f}"
          f"（两个方向都要涨，只涨一边说明偏科）")
    print(f"  规则式救场：{u['manual_resets']:.0f} -> {t['manual_resets']:.0f}"
          f"（策略变强，需要外部兜底的次数应该下降）")
    print(f"  起始状态覆盖：{u['start_cells']:.1f} -> {t['start_cells']:.1f} 格，"
          f"熵 {u['entropy_start']:.3f} -> {t['entropy_start']:.3f}")
    print(f"  内生起始占比：{u['endogenous_start_share'] * 100:.0f}% -> "
          f"{t['endogenous_start_share'] * 100:.0f}%"
          f"（{reset_mode} 模式下，出发点有多少是策略自己上一轮造成的）")
    print("\n  变的是什么？只有 model_final.zip 里的网络权重。环境、奖励、评测 seed 都没动。")
    print("  这就是「机器人通过数据学会了任务」的最小可验证形式；覆盖与救场两行则告诉你")
    print("  它学会的方式有没有让学习分布收窄——这正是阶段 2 要盯住的东西。")
    print("=" * 78)


if __name__ == "__main__":
    raise SystemExit(main())
