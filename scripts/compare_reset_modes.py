#!/usr/bin/env python
"""阶段 2 核心对照实验：交替复位（reset-free） vs 每次人工复位，同预算下到底差在哪。

ROADMAP 阶段 2 的三个验收问题，本脚本一次性量出来：

    Q1 交替是否更快/更省？        -> 复位次数、每任务复位数、含复位成本的吞吐
    Q2 代价是什么？               -> 起始状态分布会不会塌缩（交替 != 遍历）
    Q3 两者都失败时谁负责复位？   -> 规则式救场（stall）触发次数，以及救场把物体摆哪的影响

为什么用「写死的脚本策略」而不是先训练？
    因为这里要回答的是**机制**问题，不是**算法**问题。脚本策略的可靠度可以精确设定，
    于是能把「覆盖塌缩」这件事归因清楚。三种策略构成一条谱：

        random   完全不可靠     -> 只能靠救场兜底（回答 Q3）
        biased   只在舒适区可靠 -> 交替省复位，但起始状态收窄（回答 Q2 的代价）
        perfect  处处可靠       -> 交替零成本且覆盖不塌（说明代价取决于策略可靠度）
        ckpt     真正训练出来的 SAC 策略，放进同一张表对照

biased 策略的「舒适区」怎么定义：
    真实机械臂策略就是这样——训练分布中心区域可靠，边缘就不行。这里用
    「请求的放置目标离目标区域中心超过 easy_radius 就算不会做」来模拟，
    对整个 task 生效（seek / carry 两相都不干活）。
    不会做的时候有两种表现（--bias-behavior）：
        freeze  停住不动（默认）。确定性失败 -> 干净的实验仪器，place 格子严格等于舒适区。
        wander  随机游走。更像真机，但随机游走偶尔会蒙对目标，把信号冲淡。

--scan-easy-radius 是这轮实验里最有价值的一张图的数据：
    把策略可靠度从「几乎不会做」扫到「处处会做」，看两种模式的起始状态熵怎么分岔。
    它直接回答「交替的代价到底取决于什么」。

用法：
    python scripts/compare_reset_modes.py                        # 用 config 里 compare: 段的设置
    python scripts/compare_reset_modes.py --steps 4000 --seeds 0 # 快速看一眼
    python scripts/compare_reset_modes.py --bias-behavior wander # 换成随机游走版 incompetent
    python scripts/compare_reset_modes.py --policies ckpt --ckpt runs/<run>/model_final.zip

输出：
    runs/<ts>_stage2_compare/compare.json   全部原始指标（scripts/plot_stage2.py 读这个）
    runs/<ts>_stage2_compare/config.json    本次实验参数（可复现）
    终端打印两张表 + 三个验收问题的答案
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
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

from eval.transport_eval import (  # noqa: E402
    ABSTRACT,
    make_env,
    mean_summaries,
    rollout_budget,
    std_summaries,
)

# 命令行没给、config 里也没有时的兜底默认值（保证脚本单独也能跑）
FALLBACK = {"steps": 20000, "seeds": [0, 1, 2], "easy_radius": 0.06,
            "reset_cost_steps": 30.0, "scan": [0.03, 0.05, 0.07, 0.09, 0.11, 0.13]}


# --------------------------------------------------------------------------- 策略
def region_center(region: str, half: float, gap: float) -> np.ndarray:
    """A/B 区域的几何中心：x = ±(gap+half)/2, y = 0。也就是 home 点。"""
    sign = -1.0 if region == "A" else 1.0
    return np.array([sign * (gap + half) / 2.0, 0.0])


class RandomPolicy:
    """完全不可靠：每步均匀随机。用来展示「两者都失败时会发生什么」。"""

    label = "random"

    def __init__(self, seed: int = 0, **_: object) -> None:
        self.rng = np.random.default_rng(seed)

    def easy_radius(self) -> float | None:
        return None

    def act(self, obs: np.ndarray, info: dict, prm: dict) -> np.ndarray:
        return self.rng.uniform(-1.0, 1.0, size=2).astype(np.float32)


class PController:
    """比例控制器：朝当前子目标（空手->物体，抓着->放置点）直线走。

    action = clip((subgoal - ee) / action_scale, -1, 1)
    一步走满 action_scale，直到进入半径圈。不需要学习，是这个环境的性能上界参照。

    easy_radius=None -> 处处可靠（perfect）；给了值 -> 只在舒适区可靠（biased）。
    """

    def __init__(self, seed: int = 0, easy_radius: float | None = None,
                 behavior: str = "freeze", gain: float = 1.0, **_: object) -> None:
        self.rng = np.random.default_rng(seed)
        self._easy_radius = easy_radius
        self.behavior = behavior
        # gain<1 = 阻尼比例控制。为什么需要它：有执行延迟时，增益 1 的纯比例控制
        # 满足 x_{t+1} = x_t - x_{t-1}，特征根模长恰为 1 -> 等幅振荡，永远停不进抓取圈。
        # 调小增益是「不学习也能修好」的那类修补，所以必须当基线一起量，
        # 否则会把「脚本调参就能解决的问题」误记成 RL 的功劳。
        self.gain = float(gain)
        tag = f"g={self.gain:g}" if self.gain != 1.0 else ""
        base = "perfect" if easy_radius is None else f"biased({easy_radius})"
        self.label = f"{base}{('(' + tag + ')') if tag else ''}"

    def easy_radius(self) -> float | None:
        return self._easy_radius

    def _in_comfort_zone(self, obs: np.ndarray, info: dict, prm: dict) -> bool:
        dst = "B" if info["direction"] == "forward" else "A"
        center = region_center(dst, prm["half"], prm["gap"])
        target = obs[4:6] * prm["half"]
        return float(np.linalg.norm(target - center)) <= self._easy_radius

    def act(self, obs: np.ndarray, info: dict, prm: dict) -> np.ndarray:
        if self._easy_radius is not None and not self._in_comfort_zone(obs, info, prm):
            # 舒适区外：策略「不会做」。freeze = 停住（确定性失败，实验仪器最干净）；
            # wander = 随机游走（更像真机，但偶尔会蒙对，信号被冲淡）。
            if self.behavior == "wander":
                return self.rng.uniform(-1.0, 1.0, size=2).astype(np.float32)
            return np.zeros(2, dtype=np.float32)
        half, scale = prm["half"], prm["action_scale"]
        ee = obs[0:2] * half
        subgoal = (obs[4:6] * half) if obs[6] > 0 else (obs[2:4] * half)
        return np.clip(self.gain * (subgoal - ee) / scale, -1.0, 1.0).astype(np.float32)


class PDController(PController):
    """比例-微分控制器：加了速度反馈，是「不学习」能拿出的最强基线。

        action = clip((kp*(subgoal-ee) - kd*v) / action_scale, -1, 1)
        v = 本步末端位移 - 上一步末端位移（从连续两帧观测就能估出来，不需要额外传感器）

    为什么必须把它也放进对照表：
        有执行延迟时，纯比例控制（PController）会因为相位滞后而等幅振荡，
        只能靠**把增益调小**来换取稳定——代价是稳态误差变大（漂移场下
        e_ss ≈ drift/gain），于是「增益调大」和「不振荡」互相矛盾，可行增益带很窄。
        微分项提供阻尼，能在不振荡的前提下用更大的 kp，从而把稳态误差压回去。
        如果只跟「调小增益的 P」比，RL 赢的那部分可能只是「一个 D 项就能白拿的东西」，
        所以脚本上界必须用 PD 来量，不能只用 P。

    继承 PController 是为了复用舒适区判定（easy_radius / behavior），
    只覆写 act() 并多带一个「上一帧末端位置」的状态。
    """

    def __init__(self, seed: int = 0, easy_radius: float | None = None,
                 behavior: str = "freeze", kp: float = 1.0, kd: float = 1.0, **_: object) -> None:
        super().__init__(seed=seed, easy_radius=easy_radius, behavior=behavior, gain=kp)
        self.kp = float(kp)
        self.kd = float(kd)
        self._prev_ee: np.ndarray | None = None
        base = "perfect" if easy_radius is None else f"biased({easy_radius})"
        self.label = f"pd[{base}](kp={self.kp:g},kd={self.kd:g})"

    def on_episode_start(self, obs: np.ndarray, info: dict) -> None:
        """每局开始清历史（rollout_budget 会自动调；见 eval/transport_eval.py）。"""
        self._prev_ee = None

    def act(self, obs: np.ndarray, info: dict, prm: dict) -> np.ndarray:
        if self._easy_radius is not None and not self._in_comfort_zone(obs, info, prm):
            if self.behavior == "wander":
                return self.rng.uniform(-1.0, 1.0, size=2).astype(np.float32)
            return np.zeros(2, dtype=np.float32)
        half, scale = prm["half"], prm["action_scale"]
        ee = obs[0:2] * half
        subgoal = (obs[4:6] * half) if obs[6] > 0 else (obs[2:4] * half)
        velocity = np.zeros(2) if self._prev_ee is None else (ee - self._prev_ee)
        self._prev_ee = ee.copy()
        return np.clip((self.kp * (subgoal - ee) - self.kd * velocity) / scale,
                       -1.0, 1.0).astype(np.float32)


class CkptPolicy:
    """把训练好的 SB3 策略放进同一张对照表（确定性推理）。"""

    def __init__(self, ckpt: str, seed: int = 0, **_: object) -> None:
        from scripts.eval_policy import load_any_policy  # 延迟导入：不用 ckpt 就不拉 torch

        self.model, algo = load_any_policy(ckpt)
        self.label = f"ckpt({algo}:{Path(ckpt).name})"

    def easy_radius(self) -> float | None:
        return None

    def act(self, obs: np.ndarray, info: dict, prm: dict) -> np.ndarray:
        action, _ = self.model.predict(obs.astype(np.float32), deterministic=True)
        return np.asarray(action, dtype=np.float32).reshape(2)


def build_policy(kind: str, seed: int, easy_radius: float, behavior: str, ckpt: str,
                 gain: float = 1.0, kp: float = 1.0, kd: float = 1.0):
    if kind == "random":
        return RandomPolicy(seed)
    if kind == "perfect":
        return PController(seed, easy_radius=None, behavior=behavior, gain=gain)
    if kind == "biased":
        return PController(seed, easy_radius=easy_radius, behavior=behavior, gain=gain)
    if kind == "pd":
        # 处处可靠 + 带速度反馈：这就是「不学习的天花板」参照
        return PDController(seed, easy_radius=None, behavior=behavior, kp=kp, kd=kd)
    if kind == "pd_biased":
        return PDController(seed, easy_radius=easy_radius, behavior=behavior, kp=kp, kd=kd)
    if kind == "ckpt":
        if not ckpt:
            raise SystemExit("--policies ckpt 需要同时给 --ckpt <model.zip>")
        return CkptPolicy(ckpt, seed)
    raise SystemExit(f"未知策略：{kind}（可选 random/perfect/biased/pd/pd_biased/ckpt）")


# --------------------------------------------------------------------------- 跑一个格子
def run_cell(kind: str, mode: str, recovery: str, seed: int, env_kwargs: dict,
             budget_steps: int, easy_radius: float, behavior: str, ckpt: str,
             reset_cost_steps: float, env_factory: str = ABSTRACT,
             p_gain: float = 1.0, pd_gains: tuple[float, float] = (1.0, 1.0)) -> dict:
    """一个 (策略, 复位模式, 救场方式, seed) 格子的完整 rollout。"""
    policy = build_policy(kind, seed, easy_radius, behavior, ckpt, gain=p_gain,
                          kp=pd_gains[0], kd=pd_gains[1])
    env = make_env(dict(env_kwargs, reset_mode=mode, recovery_mode=recovery), env_factory)
    prm = {"half": env.half, "gap": env.gap, "action_scale": env.action_scale}

    # 统计「请求的目标里有多少落在舒适区」——这是给成功率找分母的参照
    hits = {"easy": 0, "total": 0}
    radius = policy.easy_radius()

    def on_task_start(obs: np.ndarray, info: dict) -> None:
        hits["total"] += 1
        if radius is not None:
            dst = "B" if info["direction"] == "forward" else "A"
            center = region_center(dst, prm["half"], prm["gap"])
            if float(np.linalg.norm(obs[4:6] * prm["half"] - center)) <= radius:
                hits["easy"] += 1

    summary, episodes = rollout_budget(
        env, lambda obs, info: policy.act(obs, info, prm),
        budget_steps, seed, reset_cost_steps, on_task_start=on_task_start,
        on_episode_start=getattr(policy, "on_episode_start", None),
    )
    summary["episodes"] = episodes
    summary["easy_goal_hits"] = hits["easy"]
    summary["easy_goal_share"] = round(hits["easy"] / hits["total"], 4) if hits["total"] else 0.0
    summary["comfort_zone_share_analytic"] = (
        round(_comfort_zone_area_fraction(radius, env), 4) if radius is not None else 1.0)
    return summary


def _comfort_zone_area_fraction(radius: float, env) -> float:
    """舒适区占单个区域面积的比例（蒙特卡洛，1 万点足够稳）。"""
    rng = np.random.default_rng(0)
    lo, hi = env._region_bounds("B")
    pts = rng.uniform(lo, hi, size=(10000, 2))
    center = region_center("B", env.half, env.gap)
    return float((np.linalg.norm(pts - center, axis=1) <= radius).mean())


# --------------------------------------------------------------------------- 输出
def fmt(value, nd: int = 2) -> str:
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


def table_rows(results: dict, combos: list[tuple[str, str, str]], n_cells: int) -> tuple[list, list]:
    rows_a, rows_b = [], []
    for combo in combos:
        # combos 里是 (策略, 模式, 救场) 三元组，results 的键是 "策略|模式|救场" 字符串
        key = "|".join(combo)
        if key not in results:
            continue
        entry = results[key]
        m, per_seed = entry["mean"], entry["per_seed"]
        kind, mode, recovery = combo
        std = std_summaries(per_seed, ("tasks_done",))["tasks_done"]
        rows_a.append([
            kind, mode, recovery,
            f"{m['tasks_done']:.1f}±{std:.1f}",
            f"{m['success_rate'] * 100:.1f}%",
            f"{m['success_forward']:.0f}/{m['success_backward']:.0f}",
            f"{m['fixed_resets']:.0f}", f"{m['manual_resets']:.0f}", f"{m['total_resets']:.0f}",
            fmt(m.get("resets_per_task")), fmt(m.get("steps_per_task"), 1),
            f"{m['throughput_per_1k']:.2f}", f"{m['tasks_per_1k_steps']:.2f}",
            # 扰动环境的过程指标：解释「为什么这一行慢」。抽象环境里恒为 0.00。
            fmt(m.get("slips_per_task"), 2), fmt(m.get("pushes_per_task"), 2),
        ])
        rows_b.append([
            kind, mode, recovery,
            f"{m['goal_cells']:.0f}", f"{m['entropy_goal']:.3f}",
            f"{m['start_cells']:.1f}", f"{m['coverage_start'] * 100:.0f}%", f"{m['entropy_start']:.3f}",
            f"{m['endogenous_start_share'] * 100:.0f}%",
            f"{m['pick_cells']:.1f}", f"{m['place_cells']:.1f}", f"{m['entropy_place']:.3f}",
        ])
    return rows_a, rows_b


def print_answers(results: dict, combos: list[tuple[str, str, str]], recoveries: list[str],
                  n_cells: int, stall_limit: int, reset_cost_steps: float,
                  easy_radius: float) -> None:
    """把对照表直接翻译成 ROADMAP 阶段 2 的三个验收答案。"""
    print("\n" + "=" * 78)
    print("三个验收问题的答案（数字全部来自上表）")
    print("=" * 78)
    kinds = []
    for kind, _mode, _rec in combos:
        if kind not in kinds:
            kinds.append(kind)

    for recovery in recoveries:
        for kind in kinds:
            key_alt, key_fix = f"{kind}|alternate|{recovery}", f"{kind}|fixed|{recovery}"
            if key_alt not in results or key_fix not in results:
                continue
            alt, fix = results[key_alt]["mean"], results[key_fix]["mean"]
            print(f"\n[{kind} · 救场={recovery}]  easy_radius={easy_radius}（舒适区占单区面积 "
                  f"{alt.get('comfort_zone_share_analytic', 1.0) * 100:.0f}%）")
            print(f"  Q1 交替是否更省？  总复位 {alt['total_resets']:.0f} vs {fix['total_resets']:.0f} 次"
                  f"（1 次复位按 {reset_cost_steps:.0f} 步折算）")
            print(f"     含复位成本吞吐 {alt['throughput_per_1k']:.2f} vs {fix['throughput_per_1k']:.2f}"
                  f" 任务/千步；完成 {alt['tasks_done']:.0f} vs {fix['tasks_done']:.0f} 个任务；"
                  f"成功率 {alt['success_rate'] * 100:.1f}% vs {fix['success_rate'] * 100:.1f}%")
            print(f"     每任务步数 {fmt(alt.get('steps_per_task'), 1)} vs {fmt(fix.get('steps_per_task'), 1)}"
                  f"（交替时物体就停在上一轮的放置点，空行程更短）")
            print(f"  Q2 代价是什么？    经历过的起始格子 {alt['start_cells']:.1f} vs {fix['start_cells']:.1f}"
                  f" / {n_cells}，起始分布熵 {alt['entropy_start']:.3f} vs {fix['entropy_start']:.3f}")
            print(f"     起始状态来源   交替 {alt['start_source_share']}")
            print(f"                    固定 {fix['start_source_share']}")
            print(f"     而请求的目标格子 {alt['goal_cells']:.0f} vs {fix['goal_cells']:.0f}"
                  f"（目标熵 {alt['entropy_goal']:.3f} vs {fix['entropy_goal']:.3f}，两边都均匀）")
            print(f"  Q3 谁兜底复位？    规则式救场触发 {alt['manual_resets']:.0f} / {fix['manual_resets']:.0f} 次"
                  f"（连续 {stall_limit} 步无 task 完成即触发）")

    print("\n" + "-" * 78)
    print("怎么读：")
    print("  · perfect：策略处处可靠时，交替零复位、覆盖不塌、吞吐最高 -> 交替是净收益。")
    print("  · biased ：策略只在舒适区可靠时，交替照样省复位，但「起始状态由上一轮放置点决定」，")
    print("             内生起始占比 > 0，起始分布熵低于 fixed -> 这就是「交替 != 遍历」的硬证据。")
    print("  · random ：完全不可靠时两种模式都只能靠 stall 规则兜底 -> Q3 的答案：")
    print("             先由规则接管复位，接口留给阶段 3/4 换成 LLM 接管。")
    print("  · recovery=home vs resample：救场时把物体放回固定 home 点，起始熵会明显低于均匀重采样。")
    print("             也就是说——**复位策略本身是 reset-free RL 的一个设计变量**，")
    print("             它决定了系统还能不能看到新的起始状态，不是可有可无的实现细节。")
    print("-" * 78)


# --------------------------------------------------------------------------- main
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "transport_sac.yaml"))
    parser.add_argument("--policies", default="perfect,biased,random",
                        help="逗号分隔：perfect/biased/random/pd/pd_biased/ckpt")
    parser.add_argument("--modes", default="alternate,fixed", help="逗号分隔：alternate/fixed")
    parser.add_argument("--recovery-modes", default="resample",
                        help="逗号分隔：resample(救场时均匀重采样) / home(救场时放回固定 home 点)")
    parser.add_argument("--env-factory", default="", choices=["", "abstract", "perturbed"],
                        help="覆盖 config 顶层的 env_factory（perturbed = 带扰动的搬运环境）")
    parser.add_argument("--p-gain", type=float, default=1.0,
                        help="perfect/biased 比例控制的增益；<1 是阻尼版（有执行延迟时必须调小）")
    parser.add_argument("--pd-kp", type=float, default=1.0,
                        help="pd/pd_biased 的比例增益")
    parser.add_argument("--pd-kd", type=float, default=1.0,
                        help="pd/pd_biased 的微分增益（速度反馈，用来压住延迟引起的振荡）")
    parser.add_argument("--bias-behavior", default="freeze", choices=["freeze", "wander"],
                        help="biased 策略在舒适区外的表现：freeze=停住(默认) / wander=随机游走")
    # 下面几个默认 None = 「用 config 里 compare: 段的值」，命令行给了才覆盖
    parser.add_argument("--steps", type=int, default=None, help="每个格子的交互步数预算")
    parser.add_argument("--seeds", default=None, help="重复实验的 seed 列表，如 0,1,2")
    parser.add_argument("--easy-radius", type=float, default=None,
                        help="biased 策略的舒适区半径（米）。越小 -> 越不可靠")
    parser.add_argument("--reset-cost-steps", type=float, default=None,
                        help="一次复位折算成多少环境步（真机上人工复位远比这贵）")
    parser.add_argument("--scan-easy-radius", default="",
                        help="逗号分隔的半径列表；给了就额外跑一遍「策略可靠度扫描」，不跑就留空")
    parser.add_argument("--ckpt", default="", help="--policies ckpt 时的模型路径")
    parser.add_argument("--run-name", default="stage2_compare")
    parser.add_argument("--out", default="", help="输出目录；默认 runs/<ts>_stage2_compare")
    return parser.parse_args()


def load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def main() -> int:
    args = parse_args()
    policies = [p.strip() for p in args.policies.split(",") if p.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    recoveries = [r.strip() for r in args.recovery_modes.split(",") if r.strip()]

    cfg = load_config(args.config)
    cmp_cfg = dict(cfg.get("compare", {}))
    # 优先级：命令行 > config 的 compare: 段 > FALLBACK
    steps = args.steps if args.steps is not None else int(cmp_cfg.get("steps", FALLBACK["steps"]))
    easy_radius = (args.easy_radius if args.easy_radius is not None
                   else float(cmp_cfg.get("easy_radius", FALLBACK["easy_radius"])))
    reset_cost = (args.reset_cost_steps if args.reset_cost_steps is not None
                  else float(cmp_cfg.get("reset_cost_steps", FALLBACK["reset_cost_steps"])))
    seeds = ([int(x) for x in args.seeds.split(",") if x.strip()] if args.seeds is not None
             else [int(x) for x in cmp_cfg.get("seeds", FALLBACK["seeds"])])
    scan = ([float(x) for x in args.scan_easy_radius.split(",") if x.strip()] if args.scan_easy_radius
            else [float(x) for x in cmp_cfg.get("scan_easy_radius", FALLBACK["scan"])])

    env_kwargs = dict(cfg.get("env", {}))
    # reset_mode / recovery_mode 由命令行维度决定，config 里那两行只是训练用的默认值，
    # 必须摘掉，否则 BidirectionalTransport2D(reset_mode=..., **env_kwargs) 会重复传参。
    env_kwargs.pop("reset_mode", None)
    env_kwargs.pop("recovery_mode", None)
    env_factory = (args.env_factory or str(cfg.get("env_factory", ABSTRACT))).lower()
    probe = make_env(env_kwargs, env_factory)
    n_cells = probe.grid_n * probe.grid_n

    print("=" * 78)
    print("阶段 2 对照实验：交替复位 (alternate, reset-free) vs 每次人工复位 (fixed)")
    print("=" * 78)
    print(f"  环境实现      : env_factory = {env_factory}"
          f"{'（带扰动：延迟/增益/漂移/负载/限速/滑落）' if env_factory == 'perturbed' else '（理想单积分器）'}")
    print(f"  比例控制增益  : {args.p_gain:g}"
          f"{'（阻尼版）' if args.p_gain != 1.0 else ''}")
    if any(k.startswith("pd") for k in policies):
        print(f"  PD 基线增益   : kp={args.pd_kp:g} kd={args.pd_kd:g}"
              f"（带速度反馈，是「不学习」能拿到的最强脚本基线）")
    print(f"  环境参数      : {env_kwargs if env_kwargs else '（全部用默认值）'}")
    print(f"  网格          : {probe.grid_n}x{probe.grid_n} = {n_cells} 格"
          f"（每格 {(2 * probe.half / probe.grid_n) * 100:.1f}cm）")
    print(f"  交互预算      : 每个 (策略,模式,救场,seed) {steps} 步；seed = {seeds}")
    print(f"  救场放置方式  : {recoveries}（resample=均匀重采样，home=放回区域中心）")
    print(f"  biased 舒适区 : easy_radius = {easy_radius} m，行为 = {args.bias_behavior}"
          f"（占单区面积 {_comfort_zone_area_fraction(easy_radius, probe) * 100:.0f}%）")
    print(f"  复位成本折算  : 1 次复位 = {reset_cost:.0f} 步")
    combos = [(k, m, r) for k in policies for m in modes for r in recoveries]
    n_scan = len(scan) * len(modes) * len(recoveries) if "biased" in policies else 0
    print(f"  总格子数      : {len(combos)} 个对照 x {len(seeds)} seed"
          f"{f' + 可靠度扫描 {n_scan} 格' if n_scan else ''}"
          f" = {(len(combos) * len(seeds) + n_scan * len(seeds)) * steps} 环境步")

    results: dict = {}
    per_seed_all: dict = {}
    started = time.time()
    for kind, mode, recovery in combos:
        rows = []
        for seed in seeds:
            summary = run_cell(kind, mode, recovery, seed, env_kwargs, steps,
                               easy_radius, args.bias_behavior, args.ckpt, reset_cost,
                               env_factory, args.p_gain, (args.pd_kp, args.pd_kd))
            rows.append(summary)
            per_seed_all[f"{kind}|{mode}|{recovery}|seed{seed}"] = summary
            print(f"  · {kind:<8} {mode:<10} {recovery:<9} seed={seed}  任务 {summary['tasks_done']:>5}"
                  f"  成功率 {summary['success_rate'] * 100:5.1f}%  复位 {summary['total_resets']:>5}"
                  f"  起始格子 {summary['start_cells']:>3}/{n_cells}  熵 {summary['entropy_start']:.3f}"
                  f"  ({summary['episodes']} 局)")
        results[f"{kind}|{mode}|{recovery}"] = {"n_cells": n_cells, "per_seed": rows,
                                                "mean": mean_summaries(rows)}

    # ---------------- 可靠度扫描：把 biased 的舒适区从很小扫到很大
    scan_rows: list[dict] = []
    scan_kind = "biased" if "biased" in policies else ("pd_biased" if "pd_biased" in policies else "")
    if scan_kind and scan:
        print("\n  [可靠度扫描] 舒适区半径从小到大，看两种模式的起始状态熵怎么分岔")
        for radius in scan:
          for recovery in recoveries:
            for mode in modes:
                rows = [run_cell(scan_kind, mode, recovery, seed, env_kwargs, steps,
                                 radius, args.bias_behavior, args.ckpt, reset_cost,
                                 env_factory, args.p_gain, (args.pd_kp, args.pd_kd))
                        for seed in seeds]
                m = mean_summaries(rows)
                m["easy_radius"] = radius
                m["mode"] = mode
                m["recovery"] = recovery
                scan_rows.append(m)
                print(f"  · r={radius:.3f} {mode:<10} {recovery:<9} 舒适区 {m['comfort_zone_share_analytic'] * 100:4.0f}%"
                      f"  成功率 {m['success_rate'] * 100:5.1f}%  起始格子 {m['start_cells']:>5.1f}/{n_cells}"
                      f"  起始熵 {m['entropy_start']:.3f}  内生起始 {m['endogenous_start_share'] * 100:4.0f}%"
                      f"  复位 {m['total_resets']:>5.0f}")

    elapsed = time.time() - started
    rows_a, rows_b = table_rows(results, combos, n_cells)
    print_table(
        "表 A · 成本与吞吐（Q1：交替是否更快/更省）",
        ["policy", "mode", "recovery", "tasks", "succ%", "fwd/bwd", "fixed_rst", "stall_rst",
         "total_rst", "rst/task", "steps/task", "thr/1k(eff)", "tasks/1k(raw)",
         "slip/task", "push/task"],
        rows_a,
    )
    print_table(
        f"表 B · 覆盖与分布（Q2：交替的代价是什么）  ※ 格子数满格 = {n_cells}",
        ["policy", "mode", "recovery", "goal_cells", "goal_ent", "start_cells", "start_cov",
         "start_ent", "endo_start%", "pick_cells", "place_cells", "place_ent"],
        rows_b,
    )
    if scan_rows:
        print_table(
            "表 C · 策略可靠度扫描（Q2 的因果版：可靠度决定交替的代价）",
            ["easy_radius", "comfort%", "mode", "recovery", "succ%", "start_cells", "start_ent",
             "endo_start%", "place_cells", "total_rst", "thr/1k(eff)"],
            [[f"{r['easy_radius']:.3f}", f"{r['comfort_zone_share_analytic'] * 100:.0f}%", r["mode"],
              r["recovery"],
              f"{r['success_rate'] * 100:.1f}%", f"{r['start_cells']:.1f}", f"{r['entropy_start']:.3f}",
              f"{r['endogenous_start_share'] * 100:.0f}%", f"{r['place_cells']:.1f}",
              f"{r['total_resets']:.0f}", f"{r['throughput_per_1k']:.2f}"] for r in scan_rows],
        )
    print_answers(results, combos, recoveries, n_cells, int(probe.stall_limit), reset_cost, easy_radius)

    out_dir = Path(args.out) if args.out else REPO_ROOT / "runs" / f"{datetime.now():%Y%m%d_%H%M%S}_{args.run_name}"
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_sec": round(elapsed, 1),
        "config": {
            "policies": policies, "modes": modes, "recovery_modes": recoveries,
            "bias_behavior": args.bias_behavior, "seeds": seeds, "steps_per_cell": steps,
            "easy_radius": easy_radius, "scan_easy_radius": scan if scan_rows else [],
            "reset_cost_steps": reset_cost, "env_kwargs": env_kwargs,
            "env_factory": env_factory, "p_gain": args.p_gain,
            "pd_kp": args.pd_kp, "pd_kd": args.pd_kd,
            "n_cells": n_cells, "grid_n": probe.grid_n, "half": probe.half, "gap": probe.gap,
            "stall_limit": probe.stall_limit, "ckpt": args.ckpt,
        },
        "results": {k: {"n_cells": v["n_cells"], "mean": v["mean"]} for k, v in results.items()},
        "scan": scan_rows,
        "per_seed": per_seed_all,
    }
    (out_dir / "compare.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "config.json").write_text(json.dumps(payload["config"], ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(f"\n[已保存] {out_dir / 'compare.json'}")
    print(f"[下一步] python scripts/plot_stage2.py --compare {out_dir}   # 画覆盖热力图与对比图")
    print(f"[耗时] {elapsed:.1f} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
