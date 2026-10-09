"""阶段 2 的独立评测模块：把「一段交互」折算成可对比的指标。

为什么单独一个模块（和 eval/reach_eval.py 同一个理由）：
    训练时看到的 reward 曲线，和「把策略冻结、换一批没见过的初始状态、数它完成了几个任务」
    是两件事。阶段 2 要回答的三个问题（交替是否更省 / 代价是什么 / 谁兜底复位）
    全部依赖后者，所以指标定义必须只有一处，被对照实验和训练评测共用。
    否则两张表用了不同的分母，结论就不可比。

三类分布必须分开记，这是本阶段最重要的一件事：
    goal_cells   环境**请求**的目标格子   —— 两种模式下都是均匀采样（外生）
    start_cells  策略**实际经历**的起始格子 —— alternate 下由上一轮放置点决定（内生）
    place_cells  策略**真正做到**的放置格子
    「交替 != 遍历」的证据就在 goal 很均匀、而 start 收窄的反差里。

policy 支持四种形态（与 reach_eval 一致）：
    None            -> 随机策略基线
    SB3 模型对象     -> model.predict(obs, deterministic=...)
    可调用对象       -> policy(obs) -> action
    带 act(obs, info) 的对象 -> 由调用方自己包
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

import numpy as np

COUNT_KEYS = ("start_cell_counts", "goal_cell_counts", "pick_cell_counts", "place_cell_counts")
_COUNT_TAG = {"start_cell_counts": "start", "goal_cell_counts": "goal",
              "pick_cell_counts": "pick", "place_cell_counts": "place"}
_SUM_KEYS = ("tasks_done", "tasks_attempted", "success_forward", "success_backward",
             "manual_resets", "fixed_resets", "slip_events", "push_events")


ABSTRACT = "abstract"
PERTURBED = "perturbed"
ENV_FACTORIES = (ABSTRACT, PERTURBED)


def make_env(env_kwargs: dict | None = None, env_factory: str = ABSTRACT):
    """按 `env_factory` 造环境。指标口径与 env 实现无关，所以两套环境的数字可直接对比。

        abstract   envs/bidirectional_pickplace.py  理想单积分器（阶段 2 原始结果用的就是它）
        perturbed  envs/transport_perturbed.py      延迟/增益/漂移/负载/限速/滑落（子类，钩子覆写）
    """
    kwargs = dict(env_kwargs or {})
    name = (env_factory or ABSTRACT).lower()
    if name in (PERTURBED, "transport_perturbed"):
        from envs.transport_perturbed import make_perturbed_transport

        return make_perturbed_transport(**kwargs)
    if name in (ABSTRACT, "base", "transport"):
        from envs.bidirectional_pickplace import make_transport_env

        return make_transport_env(**kwargs)
    raise ValueError(f"未知 env_factory: {env_factory!r}，可选 {ENV_FACTORIES}")


def cell_key(cell: Any) -> str:
    """格子坐标统一成 "i,j" 字符串：JSON 能存、画图能解析、跨模块能对齐。"""
    if isinstance(cell, str):
        return cell
    return f"{int(cell[0])},{int(cell[1])}"


def normalized_entropy(counts: dict, n_cells: int) -> float:
    """把「各格子被访问的次数」压成 0~1 的一个数。

    1.0 = 完全均匀地走遍整个网格；0 = 全挤在一个格子里。
    分母用 log(全网格格子数) 而不是 log(出现过的格子数)，否则
    「只去过 2 个格子但很均匀」也会得 1.0，塌缩就被掩盖了。
    """
    total = sum(counts.values())
    if total <= 0 or n_cells <= 1:
        return 0.0
    probs = np.array(list(counts.values()), dtype=np.float64) / total
    entropy = float(-(probs * np.log(probs)).sum())
    return round(entropy / np.log(n_cells), 4)


def merge_episode_reports(reports: list[dict]) -> dict:
    """把多局的 coverage_report 累计起来。

    注意：环境的计数器在每次 reset() 时清零，所以**必须逐局取 report 再累加**。
    只在循环结束后取一次，会丢掉前面所有局的数据（很容易踩的坑）。
    """
    totals: Counter = Counter()
    sources: Counter = Counter()
    counts = {name: Counter() for name in COUNT_KEYS}
    for rep in reports:
        for key in _SUM_KEYS:
            totals[key] += rep.get(key, 0)
        sources.update({k: int(v) for k, v in rep.get("start_sources", {}).items()})
        for name in COUNT_KEYS:
            counts[name].update({cell_key(k): int(v) for k, v in rep.get(name, {}).items()})
    merged = dict(totals)
    for key in _SUM_KEYS:
        merged.setdefault(key, 0)
    for name in COUNT_KEYS:
        merged[name] = dict(counts[name])
    merged["start_sources"] = dict(sources)
    return merged


def summarize(rep: dict, steps: int, n_cells: int, reset_cost_steps: float,
              extra: dict | None = None) -> dict:
    """把累计计数折算成一张可对比的指标表。"""
    done = rep.get("tasks_done", 0)
    attempted = rep.get("tasks_attempted", 0)
    total_resets = rep.get("manual_resets", 0) + rep.get("fixed_resets", 0)
    effective_steps = steps + total_resets * reset_cost_steps
    counts = {name: {cell_key(k): int(v) for k, v in rep.get(name, {}).items()} for name in COUNT_KEYS}

    out: dict = {
        "steps": steps,
        "tasks_attempted": attempted,
        "tasks_done": done,
        # success_rate = 完成的 / 请求的。分母是「环境要求它做多少次」，
        # 不是「它做成了多少次里有多少是正向」——后者永远接近 100%，没有信息量。
        "success_rate": round(done / attempted, 4) if attempted else 0.0,
        "success_forward": rep.get("success_forward", 0),
        "success_backward": rep.get("success_backward", 0),
        "manual_resets": rep.get("manual_resets", 0),
        "fixed_resets": rep.get("fixed_resets", 0),
        "total_resets": total_resets,
        "resets_per_task": round(total_resets / done, 3) if done else None,
        # 扰动环境专属的两个「过程指标」。它们不参与成败判定，但能解释**为什么**慢/为什么救场：
        #   slip_events  搬运途中掉物次数 -> 掉了要重抓，拖长每个 task
        #   push_events  接近过快把物体撞开的次数 -> 抓取落空，是「必须学会减速」的证据
        # 抽象环境里恒为 0，所以两张表的列可以完全一致地对比。
        "slip_events": rep.get("slip_events", 0),
        "push_events": rep.get("push_events", 0),
        "slips_per_task": round(rep.get("slip_events", 0) / done, 3) if done else None,
        "pushes_per_task": round(rep.get("push_events", 0) / done, 3) if done else None,
        "steps_per_task": round(steps / done, 2) if done else None,
        "tasks_per_1k_steps": round(done / steps * 1000, 3) if steps else 0.0,
        "effective_steps": round(effective_steps, 1),
        "throughput_per_1k": round(done / effective_steps * 1000, 3) if effective_steps else 0.0,
    }
    for name in COUNT_KEYS:
        tag = _COUNT_TAG[name]
        out[f"{tag}_cells"] = len(counts[name])
        out[f"coverage_{tag}"] = round(len(counts[name]) / n_cells, 4)
        out[f"entropy_{tag}"] = normalized_entropy(counts[name], n_cells)
    # 正反向是否均衡：只报比例会被「任务少」骗到，所以同时留原始计数
    if out["success_forward"] + out["success_backward"] > 0:
        out["forward_share"] = round(out["success_forward"] / done, 4) if done else 0.0
    else:
        out["forward_share"] = None
    # 起始状态来源分布：一眼看出「出发点是策略自己造的还是环境给的」
    src = {k: int(v) for k, v in rep.get("start_sources", {}).items()}
    total_src = sum(src.values()) or 1
    out["start_sources"] = src
    out["start_source_share"] = {k: round(v / total_src, 4) for k, v in src.items()}
    out["endogenous_start_share"] = round(src.get("prev_place", 0) / total_src, 4)
    out.update(counts)
    if extra:
        out.update(extra)
    return out


def make_action_fn(policy: Any, rng: np.random.Generator, deterministic: bool = True) -> Callable:
    """把四种 policy 形态统一成 act(obs, info) -> action。"""
    if policy is None:
        def act_random(obs, info):
            return rng.uniform(-1.0, 1.0, size=2).astype(np.float32)
        return act_random
    if hasattr(policy, "predict"):
        def act_sb3(obs, info):
            action, _ = policy.predict(obs.astype(np.float32), deterministic=deterministic)
            return np.asarray(action, dtype=np.float32).reshape(-1)
        return act_sb3
    if callable(policy):
        def act_callable(obs, info):
            return np.asarray(policy(obs), dtype=np.float32).reshape(-1)
        return act_callable
    raise TypeError(f"不支持的 policy 类型: {type(policy)}")


def rollout_budget(env, act: Callable, budget_steps: int, seed: int,
                   reset_cost_steps: float = 30.0,
                   on_task_start: Callable[[np.ndarray, dict], None] | None = None,
                   on_episode_start: Callable[[np.ndarray, dict], None] | None = None) -> tuple[dict, int]:
    """在同一个环境上连续跑满 budget_steps 步（跨多局），返回汇总指标。

    on_task_start(obs, info)：每检测到一个新 task 开始就回调一次，
    给调用方用来统计「这个目标在不在策略的舒适区」之类的额外信息。

    on_episode_start(obs, info)：每局 reset 之后回调一次。
    有状态的控制器（比如用「上一步末端位置」估速度的 PD）必须在这里清掉历史，
    否则跨局会拿上一局最后的 ee 当本局的第一步速度，白白挨一下冲击。
    """
    n_cells = env.grid_n * env.grid_n
    rng = np.random.default_rng(seed + 777)
    reports: list[dict] = []
    steps_used = 0
    episodes = 0

    while steps_used < budget_steps:
        obs, info = env.reset(seed=int(rng.integers(0, 2**31 - 1)))
        if on_episode_start is not None:
            on_episode_start(obs, info)
        if on_task_start is not None:
            on_task_start(obs, info)
        last_attempted = info["tasks_attempted"]
        truncated = False
        while not truncated:
            obs, _reward, _term, truncated, info = env.step(act(obs, info))
            steps_used += 1
            if info["tasks_attempted"] != last_attempted:
                last_attempted = info["tasks_attempted"]
                if on_task_start is not None:
                    on_task_start(obs, info)
        episodes += 1
        reports.append(env.coverage_report())

    merged = merge_episode_reports(reports)
    merged["episodes"] = episodes
    return summarize(merged, steps_used, n_cells, reset_cost_steps), episodes


def mean_summaries(rows: list[dict]) -> dict:
    """跨 seed 求均值；格子计数与来源计数则累加（覆盖率看的是合计经历）。"""
    out: dict = {}
    numeric = {k for row in rows for k, v in row.items()
               if isinstance(v, (int, float)) and not isinstance(v, bool)}
    for key in sorted(numeric):
        values = [row[key] for row in rows if isinstance(row.get(key), (int, float))]
        out[key] = float(np.mean(values)) if values else 0.0
    for key in ("resets_per_task", "steps_per_task", "forward_share",
                "slips_per_task", "pushes_per_task"):
        out.setdefault(key, None)
    for key in COUNT_KEYS + ("start_sources",):
        merged: Counter = Counter()
        for row in rows:
            merged.update(row.get(key, {}))
        out[key] = dict(merged)
    total_src = sum(out["start_sources"].values()) or 1
    out["start_source_share"] = {k: round(v / total_src, 4) for k, v in out["start_sources"].items()}
    return out


def std_summaries(rows: list[dict], keys: tuple[str, ...]) -> dict:
    out = {}
    for key in keys:
        values = [row[key] for row in rows if isinstance(row.get(key), (int, float))]
        out[key] = round(float(np.std(values)), 4) if len(values) > 1 else 0.0
    return out


def evaluate_transport(
    policy: Any = None,
    env_kwargs: dict | None = None,
    budget_steps: int = 20000,
    seeds: tuple[int, ...] | list[int] = (0, 1, 2),
    deterministic: bool = True,
    reset_mode: str | None = None,
    reset_cost_steps: float = 30.0,
    recovery_mode: str | None = None,
    env_factory: str = ABSTRACT,
) -> dict:
    """冻结策略、固定 seed、烧掉固定交互预算，输出一张可对比的成绩单。

    这就是阶段 2 的「验收函数」：训练脚本的评测回调、最终对比、
    以及将来 harness 的「新版本能不能发布」，都应该调它，保证同一把尺子。
    """
    kwargs = dict(env_kwargs or {})
    if reset_mode is not None:
        kwargs["reset_mode"] = reset_mode
    if recovery_mode is not None:
        kwargs["recovery_mode"] = recovery_mode
    kwargs.setdefault("reset_mode", "alternate")

    per_seed: list[dict] = []
    for seed in seeds:
        env = make_env(kwargs, env_factory)
        rng = np.random.default_rng(seed)
        act = make_action_fn(policy, rng, deterministic)
        # 策略对象自带 on_episode_start 就自动接上（PD 这类有状态控制器需要），
        # 这样调用方不用记着传第二个回调。
        summary, episodes = rollout_budget(
            env, act, budget_steps, seed, reset_cost_steps,
            on_episode_start=getattr(policy, "on_episode_start", None),
        )
        summary["seed"] = seed
        summary["episodes"] = episodes
        per_seed.append(summary)

    mean = mean_summaries(per_seed)
    std = std_summaries(per_seed, ("tasks_done", "success_rate", "total_resets",
                                   "coverage_start", "entropy_start", "throughput_per_1k"))
    return {
        "budget_steps_per_seed": budget_steps,
        "seeds": list(seeds),
        "deterministic": deterministic,
        "reset_mode": kwargs["reset_mode"],
        "recovery_mode": kwargs.get("recovery_mode", "resample"),
        "env_factory": env_factory,
        "reset_cost_steps": reset_cost_steps,
        "mean": mean,
        "std": std,
        "per_seed": per_seed,
    }
