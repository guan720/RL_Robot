#!/usr/bin/env python
"""标定 `envs/transport_perturbed.py`：给「正反向搬运」挑一档 RL 真有头可抬的难度。

为什么必须标定，不能拍脑袋定扰动参数？
    阶段 2 的实测结论是环境**已经到天花板**：SAC 训 60000 步 = 3637 个任务 / 98.6%，
    而 20 行手写比例控制器 = 3627 / 98.6%（runs/20260922_205020_stage2_compare）。
    RL 只打平了脚本上界，于是阶段 2 想研究的那个核心风险——reset-free 交替导致
    起始状态分布塌缩——在训练后的策略上**根本没机会出现**（覆盖满格 36/36、熵 0.994）。
    要让「策略不可靠」成为可研究的变量，就得先有一个不满分的基线。

    但难度也不能过头。对照实验要有分辨力，基线必须落在中间地带：
        · 随机策略接近 0%          -> 下限干净，「涨了」才是真涨
        · 最强脚本基线 55~88%      -> 任务不平凡，且 RL 有明确的超越目标
        · 太硬（<20%）             -> 大概率变成部分可观测问题，MLP 学不动
          （阶段 3 的教训：Reach 上 4 步延迟时 SAC 12000 步仍是 0.000）

为什么脚本基线要同时扫 P 和 PD（这一步最容易被跳过，但跳过就会自欺）
    只跟「调小增益的 P」比，RL 赢的那部分可能只是一个微分项就能白拿的东西。
    所以这里量两个族，取**两族里最好的那一档**当作脚本上界：
        P  族  action = clip(g*(subgoal-ee)/scale, -1, 1)          一个参数 g
        PD 族  action = clip((kp*(subgoal-ee) - kd*v)/scale, -1, 1) v = 相邻两帧位移差
    两个族在这个环境里的解析约束（离散单积分器 + k 步延迟 + 常值漂移 d）是：
        · 无延迟时 PD 的特征方程 det = kp - kd，kd 一大就振荡（实测 kp=kd=1 只有 47%）
        · 有延迟时 kd 提供阻尼，允许更大的 kp
        · 但常值漂移下稳态误差 |e_ss| = kd*d/kp -> **kd 越大越抓不住**
        · 接近限速又要求进入抓取圈时速度 <= limit -> kp 不能太大
    三条约束互相拉扯，固定增益的脚本只有一个很窄的可行带；而策略网络可以按状态调度增益
    （远处慢慢接近、近处硬顶漂移），这正是「RL 有可学的东西」的严格含义。

用法：
    python scripts/calibrate_transport.py
    python scripts/calibrate_transport.py --steps 20000 --seeds 0,1,2      # 更稳
    python scripts/calibrate_transport.py --ckpt runs/<run>/model_final.zip  # 多一列「阶段2模型掉多少」

输出：
    表 1 成功率矩阵（每档扰动 x 每个基线）——挑难度就看这张
    表 2 每档扰动下 P 族 / PD 族各自最优档的过程指标——解释**为什么**掉分
    runs/infra/<ts>_transport_calib.json 全部原始数字
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 与其它脚本一致：单线程，且必须在 import torch 之前设（--ckpt 会拉起 SB3/torch）
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "gymnasium", "yaml")

import numpy as np  # noqa: E402
import yaml  # noqa: E402

# 每行是一组候选扰动。先逐个旋钮单独加（看清到底哪一样在起作用），再上组合档位。
# 机理预期（阶段 3 在 Reach 上验证过一半）：
#   gain_noise / payload_gain 是「增益不确定」型，状态反馈能吸收 -> 单独加基本不掉分；
#   drift 是常值偏置 -> 稳态误差 e_ss ≈ d/增益，是唯一能把固定增益脚本顶出抓取圈的东西；
#   action_delay 引入相位滞后 -> 增益 1 的纯 P 满足 e_{t+1} = e_t - g*e_{t-1}，
#     g=1 时特征根模长恰为 1 -> 等幅振荡，永远停不进 2cm 圈（延迟是打破 P 的主力）；
#   approach_speed_limit / slip_prob 不改变「能不能到」，而是逼出「必须减速 / 掉了要重抓」
#     这类行为，主要打在 steps_per_task、撞飞次数和救场次数上。
PRESETS: list[dict] = [
    {"tag": "无扰动(=阶段2)"},
    # ---- 单旋钮：把功劳归因清楚 ----
    {"tag": "只加延迟1",           "action_delay": 1},
    {"tag": "只加延迟2",           "action_delay": 2},
    {"tag": "只加增益噪声35%",      "gain_noise": 0.35},
    {"tag": "只加漂移0.004",        "drift": 0.004},
    {"tag": "只加漂移0.010",        "drift": 0.010},
    {"tag": "只加负载降速0.75",     "payload_gain": 0.75},
    {"tag": "只加接近限速0.030",    "approach_speed_limit": 0.030, "push_dist": 0.035},
    {"tag": "只加接近限速0.018",    "approach_speed_limit": 0.018, "push_dist": 0.035},
    {"tag": "只加滑落3%",          "slip_prob": 0.03},
    # ---- 预设档位 ----
    {"tag": "mild 预设",           "level": "mild"},
    {"tag": "medium 预设",         "level": "medium"},
    {"tag": "hard 预设",           "level": "hard"},
    {"tag": "medium 去掉延迟",      "level": "medium", "action_delay": 0},
    {"tag": "hard 但延迟1",         "level": "hard", "action_delay": 1},
    # ---- 第二轮：用「漂移顶下界 + 限速压上界」把固定增益的可行带挤窄 ----
    # drift 要求增益够大（否则稳态误差超出 2cm 抓取圈），
    # approach_speed_limit 要求增益够小（否则冲进去把物体撞飞），
    # 两者同时收紧 -> 任何单一 (g) 或 (kp,kd) 都顾不过来，这就是 RL 的空间。
    {"tag": "漂0.008+限0.022+延1",  "action_delay": 1, "drift": 0.008,
     "approach_speed_limit": 0.022, "push_dist": 0.035},
    {"tag": "漂0.010+限0.022+延1",  "action_delay": 1, "drift": 0.010,
     "approach_speed_limit": 0.022, "push_dist": 0.035},
    {"tag": "漂0.012+限0.026+延1",  "action_delay": 1, "drift": 0.012,
     "approach_speed_limit": 0.026, "push_dist": 0.035},
    {"tag": "漂0.012+限0.022+延1+滑3%", "action_delay": 1, "drift": 0.012,
     "approach_speed_limit": 0.022, "push_dist": 0.035, "slip_prob": 0.03},
    {"tag": "漂0.016+限0.026+延1",  "action_delay": 1, "drift": 0.016,
     "approach_speed_limit": 0.026, "push_dist": 0.035},
    {"tag": "漂0.010+限0.026+延2",  "action_delay": 2, "drift": 0.010,
     "approach_speed_limit": 0.026, "push_dist": 0.035, "gain_noise": 0.35},
    {"tag": "漂0.012+限0.026+延1+噪35+载0.8", "action_delay": 1, "drift": 0.012,
     "approach_speed_limit": 0.026, "push_dist": 0.035, "gain_noise": 0.35,
     "payload_gain": 0.8, "slip_prob": 0.02},
    # ---- 第三轮：第一轮实测出来的关键发现是「漂移+限速」压不住脚本 ----
    # 常值漂移下 PD 的稳态误差 |e_ss| = kd*d/kp，只要 kd/kp <= pick_radius/d 就照样抓得住；
    # 限速也只是要求 kd 别太小（微分项本来就是刹车的）。实测漂0.012+限0.022 时
    # pd(kp=0.6,kd=0.3) 仍有 97%+（runs/infra/*_transport_calib.json）。
    # 真正把脚本压到 80% 以下的是**被控对象本身在变**：
    #   gain_noise（每局随机增益）  -> 固定 kp/kd 只对一部分局稳定
    #   payload_gain（抓着才降速）  -> 同一局里 seek 相和 carry 相是两个不同的被控对象，
    #                                  一套固定增益不可能同时最优
    # 这两样恰恰是「学出来的非线性反馈律」能吃下、而固定增益脚本吃不下的东西。
    # 下面几档在 hard 附近微调，目标是：脚本 70~88%、随机≈0、且吞吐别掉到训不动。
    {"tag": "候选A hard延1(=基准)", "level": "hard", "action_delay": 1},
    {"tag": "候选B 限速放宽0.026",  "level": "hard", "action_delay": 1,
     "approach_speed_limit": 0.026},
    {"tag": "候选C 限0.026滑4噪45", "level": "hard", "action_delay": 1,
     "approach_speed_limit": 0.026, "slip_prob": 0.04, "gain_noise": 0.45},
    {"tag": "候选D 限0.030载0.70",  "level": "hard", "action_delay": 1,
     "approach_speed_limit": 0.030, "slip_prob": 0.04, "payload_gain": 0.70},
    {"tag": "候选E A去掉滑落",      "level": "hard", "action_delay": 1, "slip_prob": 0.0},
    {"tag": "候选F 限0.026滑3漂0.006", "action_delay": 1, "gain_noise": 0.50, "drift": 0.006,
     "payload_gain": 0.65, "approach_speed_limit": 0.026, "push_dist": 0.040, "slip_prob": 0.03},
    {"tag": "候选G F去掉漂移",      "action_delay": 1, "gain_noise": 0.50,
     "payload_gain": 0.65, "approach_speed_limit": 0.026, "push_dist": 0.040, "slip_prob": 0.03},
    # ---- 第四轮：第一轮实测「漂0.016+限0.026+延1」= 81.8%，是机理最干净的一档 ----
    # 为什么这一档能把固定增益脚本压到 80% 上下，而漂0.012 压不动：
    #   要「停得住」 -> 稳态偏移 |e_ss| ~= drift/kp 必须小于 2cm 抓取圈 -> 要 kp 大
    #   要「不撞飞」 -> 进入抓取圈那一刻速度必须小于 limit             -> 要 kp 小
    #   drift=0.016 时这两条几乎顶死，任何单一固定增益都顾不过来；
    #   而策略网络可以做**增益调度**：远处用小增益慢慢蹭（不撞飞），
    #   进圈附近用大增益硬顶漂移（停得住）。这正是 RL 在这个环境里的可学空间。
    # 下面几档是在它周围加/减一个旋钮，看哪个的吞吐还够训练用。
    {"tag": "候选H 漂16限26延1",     "action_delay": 1, "drift": 0.016,
     "approach_speed_limit": 0.026, "push_dist": 0.035},
    {"tag": "候选I H+滑落2%",        "action_delay": 1, "drift": 0.016,
     "approach_speed_limit": 0.026, "push_dist": 0.035, "slip_prob": 0.02},
    {"tag": "候选J H+增益噪声25%",   "action_delay": 1, "drift": 0.016,
     "approach_speed_limit": 0.026, "push_dist": 0.035, "gain_noise": 0.25},
    {"tag": "候选K H+负载0.85",      "action_delay": 1, "drift": 0.016,
     "approach_speed_limit": 0.026, "push_dist": 0.035, "payload_gain": 0.85},
    {"tag": "候选L 漂18限24延1",     "action_delay": 1, "drift": 0.018,
     "approach_speed_limit": 0.024, "push_dist": 0.035},
    {"tag": "候选M H+滑落2+噪25",    "action_delay": 1, "drift": 0.016,
     "approach_speed_limit": 0.026, "push_dist": 0.035, "slip_prob": 0.02, "gain_noise": 0.25},
]

DEFAULT_GAINS = "1.0,0.7,0.5,0.35,0.25"
DEFAULT_PD = "1.0:0.5,1.5:1.0,2.0:1.0,1.0:0.2,0.6:0.3,2.5:1.5"
# 挑选标准：随机 < RANDOM_CEIL 且「最强脚本基线」落在 SCRIPT_BAND 内。
# 为什么 RANDOM_CEIL 是 10% 而不是像 Reach 那样的 2%：这个环境里随机游走的下限压不到 0——
# 30cm 见方的桌面 + 2cm 判定圈 + 每 120 步救场一次，瞎走也会在 6000 步里蒙对 4~8% 的任务
# （阶段 2 的对照表里随机策略就是 7.8%）。所以「下限干净」在这里的标准是 <10%，
# 而真正用来判断「有没有可学的空间」的是脚本基线那一列。
RANDOM_CEIL = 0.10
SCRIPT_BAND = (0.55, 0.88)
METRIC_KEYS = ("success_rate", "tasks_done", "tasks_attempted", "steps_per_task",
               "manual_resets", "fixed_resets", "total_resets", "slip_events", "push_events",
               "slips_per_task", "pushes_per_task", "start_cells", "entropy_start",
               "coverage_start", "throughput_per_1k", "success_forward", "success_backward")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "transport_sac.yaml"),
                        help="从这里读 env: 段（保证和对照实验同一套基础参数）")
    parser.add_argument("--steps", type=int, default=6000, help="每个 (扰动,策略,seed) 的交互步数预算")
    parser.add_argument("--seeds", default="0,1")
    parser.add_argument("--gains", default=DEFAULT_GAINS, help="P 族：逗号分隔的增益（<1 是阻尼版）")
    parser.add_argument("--pd-gains", default=DEFAULT_PD,
                        help="PD 族：逗号分隔的 kp:kd 对（kd=0 就退化成 P）")
    parser.add_argument("--reset-mode", default="alternate", choices=["alternate", "fixed"],
                        help="标定用哪种复位模式（默认 alternate，因为那才是实验的目标工况）")
    parser.add_argument("--recovery-mode", default="resample", choices=["resample", "home"])
    parser.add_argument("--reset-cost-steps", type=float, default=30.0)
    parser.add_argument("--filter", default="",
                        help="只跑 tag 里包含这些子串的预设（逗号分隔）；留空跑全部。"
                             "第二轮微调时用 --filter 候选 就只跑候选档")
    parser.add_argument("--ckpt", default="", help="阶段 2 训好的模型；给了就多一列「满分模型掉到多少」")
    parser.add_argument("--out", default="")
    return parser.parse_args()


def base_env_kwargs(config_path: str) -> dict:
    """从 config 读 env: 段，摘掉由命令行维度决定的两个键（同 compare_reset_modes.py 的做法）。"""
    cfg = {}
    path = Path(config_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as handle:
            cfg = yaml.safe_load(handle) or {}
    kwargs = dict(cfg.get("env", {}))
    kwargs.pop("reset_mode", None)
    kwargs.pop("recovery_mode", None)
    return kwargs


def preset_kwargs(preset: dict) -> dict:
    """把一行预设展开成环境 kwargs：level 先铺底，再被同行显式参数覆盖。"""
    from envs.transport_perturbed import LEVELS

    out: dict = {}
    if preset.get("level"):
        out.update(LEVELS[preset["level"]])
    for key, value in preset.items():
        if key not in ("tag", "level"):
            out[key] = value
    out["_tag"] = preset.get("tag", "")
    return out


class Scripted:
    """把 compare_reset_modes 里 `act(obs, info, prm)` 形态的脚本策略，包成
    `evaluate_transport` 认的 callable（`policy(obs) -> action`）。

    只用于 easy_radius=None 的「处处可靠」控制器：那种情况下 act() 根本不读 info，
    所以给个空 dict 是安全的。带舒适区的 biased 策略要读 info["direction"]，包进来会算错。
    on_episode_start 会被 evaluate_transport 自动调用（PD 需要它在每局清掉速度历史）。
    """

    def __init__(self, controller, prm: dict) -> None:
        if controller.easy_radius() is not None:
            raise ValueError("Scripted 只支持 easy_radius=None 的策略（biased 需要 info）")
        self.controller = controller
        self.prm = prm
        self.label = getattr(controller, "label", type(controller).__name__)
        if hasattr(controller, "on_episode_start"):
            self.on_episode_start = controller.on_episode_start

    def __call__(self, obs: np.ndarray) -> np.ndarray:
        return self.controller.act(obs, {}, self.prm)


def fmt(value, nd: int = 1) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{nd}f}"
    return str(value)


def print_table(title: str, header: list[str], rows: list[list[str]]) -> None:
    if not rows:
        return
    widths = [max(len(str(header[i])), *(len(str(r[i])) for r in rows)) for i in range(len(header))]
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(header))
    print(f"\n{title}\n{'-' * len(line)}\n{line}\n{'-' * len(line)}")
    for row in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def best_of(entries: dict, labels: list[str]) -> tuple[str, dict]:
    """在一族基线里挑成功率最高的那一档（并列时取靠前的，保证可复现）。"""
    best_label = labels[0]
    for label in labels[1:]:
        if entries[label]["success_rate"] > entries[best_label]["success_rate"]:
            best_label = label
    return best_label, entries[best_label]


def main() -> int:
    args = parse_args()
    from eval.transport_eval import PERTURBED, evaluate_transport, make_env
    from scripts.compare_reset_modes import PDController, PController, RandomPolicy

    base_kwargs = base_env_kwargs(args.config)
    seeds = tuple(int(x) for x in args.seeds.split(",") if x.strip())
    gains = [float(x) for x in args.gains.split(",") if x.strip()]
    pd_pairs = []
    for item in args.pd_gains.split(","):
        if item.strip():
            kp, kd = item.split(":")
            pd_pairs.append((float(kp), float(kd)))

    probe = make_env(dict(base_kwargs), PERTURBED)
    prm = {"half": probe.half, "gap": probe.gap, "action_scale": probe.action_scale}

    filters = [f.strip() for f in args.filter.split(",") if f.strip()]
    presets = [p for p in PRESETS
               if not filters or any(f in p.get("tag", "") for f in filters)]
    if not presets:
        raise SystemExit(f"--filter {args.filter!r} 没匹配到任何预设")

    ckpt_policy = None
    if args.ckpt:
        from scripts.eval_policy import load_any_policy

        ckpt_policy, algo = load_any_policy(args.ckpt)
        print(f"  已加载模型: {args.ckpt}（{algo}）")

    print("=" * 118)
    print(f"带扰动搬运环境标定 · 每格 {args.steps} 步 x seed {seeds} · 复位模式 {args.reset_mode}"
          f" · 救场 {args.recovery_mode}")
    print(f"基础环境参数（来自 {Path(args.config).name}）: {base_kwargs if base_kwargs else '全部默认'}")
    print(f"脚本基线：P 族 {gains} · PD 族 {pd_pairs}")
    print("=" * 118)

    rows: list[dict] = []
    started = time.time()
    for preset in presets:
        kwargs = preset_kwargs(preset)
        tag = kwargs.pop("_tag")
        env_kwargs = {**base_kwargs, **kwargs}
        entry: dict = {"tag": tag, "perturbation": kwargs, "env_kwargs": env_kwargs, "policies": {}}

        def evaluate(label: str, policy) -> dict:
            report = evaluate_transport(
                policy, env_kwargs, budget_steps=args.steps, seeds=seeds, deterministic=True,
                reset_mode=args.reset_mode, reset_cost_steps=args.reset_cost_steps,
                recovery_mode=args.recovery_mode, env_factory=PERTURBED,
            )
            mean = report["mean"]
            item = {k: mean.get(k) for k in METRIC_KEYS}
            item["std_tasks_done"] = report["std"].get("tasks_done")
            entry["policies"][label] = item
            return item

        evaluate("random", Scripted(RandomPolicy(seed=seeds[0]), prm))
        p_labels = []
        for gain in gains:
            label = f"p_g{gain:g}"
            p_labels.append(label)
            evaluate(label, Scripted(PController(seed=seeds[0], easy_radius=None, gain=gain), prm))
        pd_labels = []
        for kp, kd in pd_pairs:
            label = f"pd_{kp:g}:{kd:g}"
            pd_labels.append(label)
            evaluate(label, Scripted(PDController(seed=seeds[0], easy_radius=None,
                                                  kp=kp, kd=kd), prm))
        if ckpt_policy is not None:
            evaluate("stage2_sac", ckpt_policy)
        rows.append(entry)

        p_label, p_best = best_of(entry["policies"], p_labels)
        pd_label, pd_best = best_of(entry["policies"], pd_labels)
        top = p_best if p_best["success_rate"] >= pd_best["success_rate"] else pd_best
        top_label = p_label if top is p_best else pd_label
        ck = entry["policies"].get("stage2_sac")
        ckpt_text = "" if ck is None else f" | 阶段2模型 {ck['success_rate'] * 100:>5.1f}%"
        print(f"  · {tag:<26} 随机 {entry['policies']['random']['success_rate'] * 100:>5.1f}%"
              f" | 最强脚本 {top['success_rate'] * 100:>5.1f}%（{top_label}）"
              f"  任务 {top['tasks_done']:>5.0f}  步/任务 {fmt(top['steps_per_task'])}"
              f"  救场 {top['manual_resets']:>4.0f}  掉/任务 {fmt(top['slips_per_task'], 2)}"
              f"  撞/任务 {fmt(top['pushes_per_task'], 2)}{ckpt_text}", flush=True)

    elapsed = time.time() - started

    # ------------------------------------------------------------------ 表 1：成功率矩阵
    cols = ["random"] + [f"p_g{g:g}" for g in gains] + [f"pd_{kp:g}:{kd:g}" for kp, kd in pd_pairs]
    if ckpt_policy is not None:
        cols.append("stage2_sac")
    names = {"random": "随机", "stage2_sac": "阶段2模型"}
    matrix = [[entry["tag"]] + [f"{entry['policies'][c]['success_rate'] * 100:.1f}%" for c in cols]
              for entry in rows]
    print_table(
        "表 1 · 成功率矩阵（挑难度看这张：随机≈0% 且**所有**脚本列都落在 55~88% 的那一行最合适）",
        ["扰动配置"] + [names.get(c, c) for c in cols], matrix,
    )

    # ------------------------------------------------------------------ 表 2：两族各自最优档的过程指标
    detail = []
    for entry in rows:
        p_label, p_best = best_of(entry["policies"], [f"p_g{g:g}" for g in gains])
        pd_label, pd_best = best_of(entry["policies"], [f"pd_{kp:g}:{kd:g}" for kp, kd in pd_pairs])
        for label, item in ((p_label, p_best), (pd_label, pd_best)):
            detail.append([
                entry["tag"], label, f"{item['success_rate'] * 100:.1f}%",
                f"{item['tasks_done']:.0f}", fmt(item["steps_per_task"]),
                f"{item['success_forward']:.0f}/{item['success_backward']:.0f}",
                f"{item['manual_resets']:.0f}", fmt(item["slips_per_task"], 2),
                fmt(item["pushes_per_task"], 2), f"{item['start_cells']:.0f}",
                f"{item['entropy_start']:.3f}", fmt(item["throughput_per_1k"]),
            ])
    print_table(
        "表 2 · 每档扰动下 P 族 / PD 族各自最优档的过程指标（解释成功率为什么掉）",
        ["扰动配置", "最优脚本", "succ%", "tasks", "steps/task", "fwd/bwd", "救场",
         "掉物/task", "撞飞/task", "起始格子", "起始熵", "thr/1k"],
        detail,
    )

    # ------------------------------------------------------------------ 推荐
    print(f"\n推荐（自动筛：随机 < {RANDOM_CEIL * 100:.0f}%，"
          f"最强脚本基线落在 {SCRIPT_BAND[0] * 100:.0f}~{SCRIPT_BAND[1] * 100:.0f}%）")
    picks = []
    for entry in rows:
        rand = entry["policies"]["random"]["success_rate"]
        script_labels = [f"p_g{g:g}" for g in gains] + [f"pd_{kp:g}:{kd:g}" for kp, kd in pd_pairs]
        label, best = best_of(entry["policies"], script_labels)
        if rand < RANDOM_CEIL and SCRIPT_BAND[0] <= best["success_rate"] <= SCRIPT_BAND[1]:
            picks.append({"tag": entry["tag"], "best_script": label,
                          "script_success": best["success_rate"], "random_success": rand,
                          "tasks_done": best["tasks_done"], "perturbation": entry["perturbation"]})
    if picks:
        for pick in sorted(picks, key=lambda x: -x["script_success"]):
            print(f"  ✓ {pick['tag']:<26} 最强脚本 {pick['script_success'] * 100:5.1f}%"
                  f"（{pick['best_script']}） / 随机 {pick['random_success'] * 100:4.1f}%"
                  f"   参数 {pick['perturbation']}")
    else:
        print("  ✗ 没有一档落在目标带内：要么整体太简单（脚本仍满分），要么整体太硬。")
        print("    太简单 -> 加大 drift（顶高增益下界）+ 收紧 approach_speed_limit（压低增益上界）；")
        print("    太硬   -> 降回 mild，或把 action_delay 保持 1（阶段 3 实测长延迟下 MLP 学不动）。")
    print(f"\n  耗时 {elapsed:.1f} 秒（{len(presets)} 档 x {len(cols)} 个策略 x {len(seeds)} seed"
          f" x {args.steps} 步）")

    out_path = Path(args.out) if args.out else (
        REPO_ROOT / "runs" / "infra" / f"{time.strftime('%Y%m%d_%H%M%S')}_transport_calib.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": args.config, "base_env": base_kwargs, "steps": args.steps, "seeds": list(seeds),
        "gains": gains, "pd_gains": [list(p) for p in pd_pairs],
        "reset_mode": args.reset_mode, "recovery_mode": args.recovery_mode,
        "reset_cost_steps": args.reset_cost_steps, "ckpt": args.ckpt,
        "selection": {"random_ceiling": RANDOM_CEIL, "script_band": list(SCRIPT_BAND),
                      "picks": picks},
        "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  已存: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
