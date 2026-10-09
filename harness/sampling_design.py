"""干预强度量探针：在**不训练**的前提下，回答「这套采样设计把分布推离均匀多远」。

为什么需要这一层
----------------
阶段 3 第一次 A/B 是阴性结果。机理分析（`docs/notes_stage3.md` §6.6）指出干预太弱：
`range` 分带 + `floor=0.15` 让归一化后 37.5% 的采样质量喂给了**构造上为空**的距离带
（扰动基准的环境最小目标距离 0.1 > 第一条带上界 0.095），实测 17/18 轮外圈两带被钉死，
有效分布与均匀采样的总变差距离只有 0.24 —— 这么弱的干预测不出学习速度差异。

改设计很容易，**改对很难**。所以流程必须是：先量 TV，过门槛才允许花预算跑 A/B。
本模块就是那把尺子：

    collect_joint(...)  只采集不训练，拿 (label, init_dist, success) 的联合样本
    design_table(...)   对候选设计（band_mode × floor × n_bands）算有效权重与 TV
    gate_verdict(...)   TV >= 门槛 -> 允许跑 A/B；否则明确拒绝并说明原因

TV 口径与 `scripts/plot_stage3.py::tv_vs_uniform` 完全一致（两处必须同口径，
否则「探针说够了、图上看着不够」这种鬼故事会出现）：

    effective = (1 - mix_uniform) * weights + mix_uniform * uniform
    TV        = 0.5 * Σ |effective - uniform|

由此能直接推出**这套设计空间的 TV 天花板**（`tv_ceiling`）：

    TV_max(n_bands, mix) = (1 - mix) * (1 - 1/n_bands)     # 质量全压一条带时取到

mix=0.25 时：2 带 0.375、3 带 0.500、4 带 0.563。所以「TV 门槛 0.4」不是能随便设的数：
`n_bands=2` 时它**构造上不可达**，再怎么调 floor 也过不了门禁。反过来，TV 贴近天花板
说明计划已经退化成 one-hot（floor 被压到 0）—— 过门禁 ≠ 好设计，抗遗忘能力最差，
遗忘风险得由 A/B 的「旧任务掉点」维度兜住。`gate_verdict` 把这两件事写进 warnings，
只解释判定、不改变判定。

一个刻意的设计决定：探针在**多个训练阶段的 ckpt** 上量 TV，而不是只在随机策略上量。
因为干预强度随策略水平变化——随机策略的失败全是 `diverged`、分布很宽，
收敛期策略几乎不失败、计划退化成 floor；只有中段策略的失败分布才代表
闭环真正会遇到的题目。只看一个点会高估或低估干预强度。

接触物理这一层还多两道门禁（v1，2026-09-23，`frontier_verdict`）
------------------------------------------------------------------
TV 门禁回答的是「采样分布被推得多远」，它假设**已经有一个值得采样的失败区域**。
换到 robosuite Lift/PickPlace 这种带真实接触的任务，这个假设会先崩：实测手写控制器
在环境默认出生盒子（±0.03 m）上 12/12 满分，SAC 60k 步只有 0.10 —— 上限侧饱和、
学习侧贴地，两头都不在可诊断区里，此时谈「诊断驱动的采样」没有对象。
所以在烧训练预算之前必须先量三件事，`frontier_verdict` 把它们写成硬门禁：

    1. 上限：手写参照得满分（否则「成功长什么样」都不可信，先修控制器/动作栈）；
    2. 带内：策略成功率落在 band 里（贴地 → 全局成功率无分辨力；饱和 → 无可学）；
    3. frontier：逐题配对里「手写成、策略不成」的占比够大、且「都不成」的占比够小
       —— 只有这一部分题目对「采样往哪儿放」敏感；
    4. 成本与分辨率：每局秒数 × 局数 × 轮数 × 臂数 <= 预算；且评测局数能检出
       门禁声称的 `min_gain`（50 局只能检出 ~0.28 的差，比 min_gain=0.02 大一个量级，
       这一条会把绝大多数"看着有提升"的 A/B 直接判为不可判定）。
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Iterable, Sequence

import numpy as np

from harness.diagnose import build_sampling_plan, label_all
from skills.base import EpisodeRecord, run_episode


def effective_tv(weights: Sequence[float], mix_uniform: float = 0.25) -> float:
    """有效采样分布与均匀分布的总变差距离。0 = 与均匀采样无区别。"""
    w = np.asarray(weights, dtype=np.float64)
    if w.size == 0 or w.sum() <= 0:
        return 0.0
    w = w / w.sum()
    uniform = np.full(w.size, 1.0 / w.size)
    effective = (1.0 - float(mix_uniform)) * w + float(mix_uniform) * uniform
    return float(0.5 * np.abs(effective - uniform).sum())


def tv_ceiling(n_bands: int, mix_uniform: float = 0.25) -> float:
    """给定带数与均匀混合比例，TV 的理论上界（采样质量全压一条带时取到）。

    两个用途，都是为了让门禁可解释而不是「凑到 0.4 就放行」：
      · 判**门槛可达吗**：`tv_gate > tv_ceiling(n_bands)` 时，这个设计族无论怎么调 floor
        都过不了门禁，该改的是带数或 mix_uniform；
      · 判**是不是压满了**：`tv / ceiling ≈ 1` 意味着 one-hot 计划，干预强度最大、
        抗遗忘最差，两个方向的风险都得写进结论。
    """
    n = int(n_bands)
    if n <= 1:
        return 0.0
    return (1.0 - float(mix_uniform)) * (1.0 - 1.0 / n)


def pinned_bands(weights: Sequence[float], tolerance: float = 0.01) -> list[int]:
    """单看一组权重判断不了「跨轮钉死」（那需要 journal，见 plot_stage3.py）；
    这里给的是单轮口径的「饿带」：权重低于均匀值的带 = 只吃到保底、没吃到失败质量。
    饿带越多，说明 floor 在替空带占预算。1-based 编号。"""
    w = np.asarray(weights, dtype=np.float64)
    if w.size == 0:
        return []
    uniform = 1.0 / w.size
    return [int(i) + 1 for i, value in enumerate(w) if value < uniform - 1e-9]


def design_table(failures: list[EpisodeRecord], *, goal_radius: float, half_space: float,
                 candidates: Iterable[dict], mix_uniform: float = 0.25,
                 min_goal_dist: float | None = None, realized_draws: int = 0) -> list[dict]:
    """对每个候选设计算「如果现在就用它，有效分布离均匀多远」。

    `candidates` 每项形如 {"band_mode": "quantile", "floor": 0.05, "n_bands": 4}。
    返回行里带 weights，方便画图或事后核对；TV 是主判据。

    `min_goal_dist` + `realized_draws` 打开**实测**口径（`realized_distance_profile`）：
    名义 TV 只看带索引上的权重，看不见「带被环境截断成薄壳」，两者可以差很远。
    """
    rows: list[dict] = []
    for cand in candidates:
        plan = build_sampling_plan(
            failures, goal_radius, half_space,
            n_bands=int(cand.get("n_bands", 4)),
            floor=float(cand.get("floor", 0.15)),
            band_mode=str(cand.get("band_mode", "range")),
        )
        weights = [float(w) for w in plan.normalized().weights]
        row = {
            "band_mode": str(cand.get("band_mode", "range")),
            "floor": float(cand.get("floor", 0.15)),
            "n_bands": int(cand.get("n_bands", 4)),
            "n_failures": len(failures),
            "weights": [round(w, 4) for w in weights],
            "tv": round(effective_tv(weights, mix_uniform), 4),
            "tv_ceiling": round(tv_ceiling(len(weights), mix_uniform), 4),
            "tv_frac": round(effective_tv(weights, mix_uniform) /
                             max(1e-9, tv_ceiling(len(weights), mix_uniform)), 4),
            "one_hot": bool(weights) and max(weights) >= 0.999,
            "starved_bands": pinned_bands(weights),
            "bands": [[round(a, 4), round(b, 4)] for a, b in plan.bands],
        }
        if min_goal_dist is not None and realized_draws > 0 and failures:
            row.update(realized_distance_profile(
                plan, half_space=half_space, min_goal_dist=float(min_goal_dist),
                mix_uniform=mix_uniform, n_draws=int(realized_draws)))
        rows.append(row)
    return rows


def realized_distance_profile(plan: Any, *, half_space: float, min_goal_dist: float,
                              mix_uniform: float = 0.25, n_draws: int = 3000,
                              seed: int = 12345, n_bins: int = 16) -> dict:
    """**实测**干预强度：把两个采样器各跑 `n_draws` 次，比它们的目标距离直方图。

    为什么名义 TV（`effective_tv`）不够：它比的是「带索引上的权重 vs 均匀」，可带在
    几何上并不等价，而且带的下界会被环境 `min_goal_dist` 截掉。实测踩到的例子：
    `labelcond/floor=0/bands=3` 名义 TV=0.500（正好压满三带天花板），但它独吃的那条带是
    [0.04, 0.1133)，环境不允许 < 0.1 的目标 —— 真正能练的只剩一个 0.013 m 厚的薄壳，
    占环境距离域 [0.1, 0.26] 的 8%。名义指标看不见这件事，跑采样器才看得见。

    返回（都会写进探针 JSON）：
      tv_distance    距离空间上的 TV，与名义 `tv` 同口径（0.5*Σ|p-q|），0 = 分不出来
      tv_noise_floor 两个**独立均匀**采样器之间的 TV，即「没有干预」时也会有多大读数
                     （直方图 + 有限抽样噪声）；tv_distance 只有明显高于它才有意义
      support_frac   干预后 P10~P90 距离跨度 / 环境距离域宽度（训练覆盖率的代理）
      fallback_rate  banded 采样器退回均匀的比例（带里没有合法点，说明带设计错了）
      mean/p10/p90   干预后实际练到的距离

    一个必须记住的实测事实：`tv_distance` 可以**大于**名义 `tv`。因为名义口径把
    「均匀」定义成「每条带等权」，而带在几何上并不等体积（内圈带体积小得多）。
    把质量压进内圈薄壳，在距离空间上偏离环境分布比名义数字更严重。
    """
    from harness.sampling import BandedGoalSampler, UniformGoalSampler

    lo = float(min_goal_dist)
    hi = float(half_space) * math.sqrt(3.0)
    edges = np.linspace(lo, hi, int(n_bins) + 1)
    uniform = UniformGoalSampler(half_space, min_goal_dist, seed)
    uniform_null = UniformGoalSampler(half_space, min_goal_dist, seed + 777)
    banded = BandedGoalSampler(plan, half_space, min_goal_dist, seed + 1, mix_uniform)
    dist_u = np.linalg.norm(np.asarray([uniform.draw() for _ in range(int(n_draws))]), axis=1)
    dist_n = np.linalg.norm(np.asarray([uniform_null.draw() for _ in range(int(n_draws))]), axis=1)
    dist_b = np.linalg.norm(np.asarray([banded.draw() for _ in range(int(n_draws))]), axis=1)
    hist_u, _ = np.histogram(dist_u, bins=edges)
    hist_n, _ = np.histogram(dist_n, bins=edges)
    hist_b, _ = np.histogram(dist_b, bins=edges)
    pu = hist_u / max(1, int(hist_u.sum()))
    pn = hist_n / max(1, int(hist_n.sum()))
    pb = hist_b / max(1, int(hist_b.sum()))
    p10, p90 = (float(x) for x in np.quantile(dist_b, [0.10, 0.90]))
    u10, u90 = (float(x) for x in np.quantile(dist_u, [0.10, 0.90]))
    return {
        "tv_distance": round(float(0.5 * np.abs(pb - pu).sum()), 4),
        "tv_noise_floor": round(float(0.5 * np.abs(pn - pu).sum()), 4),
        "support_frac": round((p90 - p10) / max(1e-9, hi - lo), 4),
        "uniform_support_frac": round((u90 - u10) / max(1e-9, hi - lo), 4),
        "fallback_rate": round(float(getattr(banded, "fallbacks", 0)) / max(1, int(n_draws)), 4),
        "realized_draws": int(n_draws),
        "mean_dist": round(float(dist_b.mean()), 4),
        "p10_dist": round(p10, 4),
        "p90_dist": round(p90, 4),
        "uniform_mean_dist": round(float(dist_u.mean()), 4),
    }


def collect_joint(skill: Any, env_kwargs: dict, *, episodes: int = 12,
                  seeds: Sequence[int] = (0, 1), goal_radius: float | None = None,
                  env_factory: str = "perturbed") -> list[EpisodeRecord]:
    """只采集、不训练：用环境默认（均匀）采样跑若干局，返回带标签的记录。

    用均匀采样是刻意的：探针要量的是「在闭环当前会遇到的题目分布上，失败长什么样」，
    而不是「在某个干预分布上失败长什么样」——后者会把设计自己的偏差喂回设计。
    """
    from harness.env_factory import get_factory

    radius = float(goal_radius if goal_radius is not None else env_kwargs.get("goal_radius", 0.02))
    make_env = get_factory(env_factory)
    records: list[EpisodeRecord] = []
    for seed in seeds:
        env = make_env(**env_kwargs)
        for episode in range(int(episodes)):
            record = run_episode(env, skill, seed=int(seed) * 1000 + episode,
                                 direction="forward", role="primary")
            records.append(record)
        env.close() if hasattr(env, "close") else None
    label_all(records, radius)
    return records


def gate_verdict(rows: list[dict], *, tv_gate: float = 0.4,
                 prefer: dict | None = None, fallback_tol: float = 0.05,
                 coverage_ratio: float = 0.5, objective: str = "strength") -> dict:
    """把**一个训练阶段**的探针结果变成一句可执行的判定（v3，2026-09-23）。

    三代规则，每一代都是被实测打脸之后改的：
      · v1  只看名义 TV（带索引权重 vs 等权带）。
      · v2  加分阶段规则（早期允许弱，见 `gate_verdict_phased`）。
      · v3  **改用实测距离 TV**（有 `tv_distance` 就用它），并把两类「名义上很强、
            实际在空转」的候选作废：
            (a) `fallback_rate > fallback_tol` —— 带里没有合法点（典型：带的上界低于
                环境 `min_goal_dist`），采样器静默退回均匀，名义权重根本没生效；
            (b) `support_frac < coverage_ratio × uniform_support_frac` —— 训练分布的
                距离跨度窄于环境本身的一半，那是拿遗忘换速度，标准评测必然暴露。

    v3 不是把门槛调松，而是把尺子换准。探针实测（runs/infra/20260923_142507）：
    `range/f0/b4` 名义 TV=0.375、实测只有 0.139（内外圈带体积不等，名义口径把
    「等权带」当基线，而环境基线是 ∝r² 的壳层）；`labelcond/f0.05/b4` 名义 0.469、
    实测 0.044（fallback 67%，质量全压在一个空带上）。用名义尺子会把这两种
    空转设计当成强干预放行 —— 这正是 run1/run2 阴性结果被误读成「诊断没用」的原因。

    `warnings` 记录不改变判定、但必须跟着结论走的风险（天花板不可达 / one-hot 压满 /
    候选作废）。判定结果只看 `ok`，别只看 `best`。

    `objective` 是 v3.1 加的选择策略（2026-09-23，run3 之后）：
      · `strength`（默认，run3 用的）：在合法候选里选 TV 最大 —— 适合回答
        「干预到底有没有用」，因为要先把效应放大到测得出来；
      · `coverage`：在**满足强度门槛且覆盖合格**的候选里选覆盖最宽的 —— 适合回答
        「强度够了之后，泛化能不能跟上来」。run3 的实测代价就是覆盖只剩均匀的 73%，
        末点被 uniform 反超（§6.9 第 3 条），所以 run4 换这个目标。
    两个目标都不改变 `ok` 的判定规则，只改变推荐谁。
    """
    if not rows:
        return {"ok": False, "reason": "没有候选设计", "best": None, "warnings": [],
                "metric": "tv"}
    if objective not in ("strength", "coverage"):
        raise ValueError(f"objective 只能是 strength/coverage，收到 {objective!r}")
    metric = "tv_distance" if any(r.get("tv_distance") is not None for r in rows) else "tv"

    def strength(row: dict) -> float:
        value = row.get(metric)
        if value is None:
            value = row.get("tv")
        return float(value or 0.0)

    def cov_ok(row: dict) -> bool:
        support = row.get("support_frac")
        uniform_support = float(row.get("uniform_support_frac") or 0.0)
        if support is None or uniform_support <= 0:
            return True
        return float(support) >= coverage_ratio * uniform_support

    warnings: list[str] = []
    usable = [r for r in rows if float(r.get("fallback_rate") or 0.0) <= fallback_tol]
    voided = [r for r in rows if float(r.get("fallback_rate") or 0.0) > fallback_tol]
    if voided:
        warnings.append(
            f"{len(voided)}/{len(rows)} 个候选作废（fallback_rate > {fallback_tol:.0%}，"
            f"带里没有合法点、抽样退回均匀，名义 TV 不成立）："
            + ", ".join(f"{r['band_mode']}/f{r['floor']:g}/b{r['n_bands']}"
                        f"[名义 {r['tv']:.3f} → 实测 {strength(r):.3f}, "
                        f"fallback {float(r.get('fallback_rate') or 0.0):.0%}]" for r in voided))
    pool = usable or rows
    if objective == "coverage":
        passing = [r for r in pool if strength(r) >= tv_gate and cov_ok(r)]
        if passing:
            best = max(passing, key=lambda r: (float(r.get("support_frac") or 0.0), strength(r)))
        else:
            best = max(pool, key=lambda r: (strength(r), -len(r.get("starved_bands") or [])))
    else:
        best = max(pool, key=lambda r: (strength(r), -len(r.get("starved_bands") or [])))
    if metric == "tv":
        ceilings = [float(r.get("tv_ceiling") or
                          tv_ceiling(int(r.get("n_bands", 4) or 4), 0.25)) for r in rows]
        if ceilings and max(ceilings) < tv_gate:
            warnings.append(f"门槛 {tv_gate:g} 在本候选集里构造上不可达（最高天花板 "
                            f"{max(ceilings):.3f}）：请加带数或降 mix_uniform，别再试 floor")
        warnings.append("本次只有名义 TV（--realized-draws 0）：名义口径看不见带被环境截断，"
                        "结论仅供参考")

    label = "实测 TV距离" if metric == "tv_distance" else "名义 TV"
    support = best.get("support_frac")
    uni_support = float(best.get("uniform_support_frac") or 0.0)
    coverage_ok = cov_ok(best)
    if strength(best) < tv_gate:
        return {
            "ok": False, "metric": metric, "best": best, "warnings": warnings,
            "coverage_ok": coverage_ok,
            "objective": objective,
            "reason": (f"最强候选{label}={strength(best):.3f} < 门槛 {tv_gate:g}"
                       f"（噪声地板 {best.get('tv_noise_floor', '?')}）：干预太弱，"
                       f"跑 A/B 只会再得到一个不可判定的阴性结果。先改设计再量。"),
        }
    if not coverage_ok:
        return {
            "ok": False, "metric": metric, "best": best, "warnings": warnings,
            "coverage_ok": coverage_ok,
            "objective": objective,
            "reason": (f"{label}={strength(best):.3f} 过了门槛，但距离覆盖 "
                       f"{float(support):.0%} < 均匀覆盖 {uni_support:.0%} 的 "
                       f"{coverage_ratio:.0%}：训练分布过窄，先加 floor / 加带数换覆盖"),
        }
    chosen = best
    if prefer:
        matching = [r for r in pool if all(r.get(k) == v for k, v in prefer.items())]
        if matching:
            chosen = max(matching, key=lambda r: (strength(r), -len(r.get("starved_bands") or [])))
    frac = float(chosen.get("tv_frac") or 0.0)
    if chosen.get("one_hot") or frac >= 0.95:
        warnings.append(
            f"推荐设计 {chosen.get('band_mode')}/f{chosen.get('floor'):g}"
            f"/b{chosen.get('n_bands')} 的名义权重已压满天花板（{frac:.0%}，"
            f"weights={chosen.get('weights')}）：干预最强、抗遗忘最弱，"
            f"A/B 结论必须同时看「旧任务掉点」维度")
    return {
        "ok": True,
        "metric": metric,
        "coverage_ok": coverage_ok,
        "objective": objective,
        "reason": (f"候选 {chosen['band_mode']}/floor={chosen['floor']}/bands={chosen['n_bands']} "
                   f"{label}={strength(chosen):.3f} >= 门槛 {tv_gate:g}"
                   f"（名义 {chosen['tv']:.3f} · 覆盖 {chosen.get('support_frac', '?')}"
                   f" vs 均匀 {chosen.get('uniform_support_frac', '?')}"
                   f" · fallback {chosen.get('fallback_rate', 0)}），允许花预算跑 A/B"),
        "best": chosen,
        "warnings": warnings,
    }


def gate_verdict_phased(per_ckpt_verdicts: list[dict], *, tv_gate: float = 0.4,
                        early_ratio: float = 0.6) -> dict:
    """跨训练阶段的总门禁（v3；v2 = 分阶段规则 + 名义 TV，v1 = 所有阶段都过门槛）。

    分阶段规则的来历（v2 定、v3 沿用）：探针实测显示**任何**设计在早期阶段
    （策略还接近随机）都到不了 0.4 —— 早期失败是「处处都差」，失败在任何距离变量上
    的分布都很宽，不存在可以瞄准的集中弱点；在这个阶段做针对性采样等于无信号地缩探索，
    本来就不该强。而被检验的科学命题是「诊断能加速中后期的精度阶段」——run2 里被撤回的
    「diagnosed 精调更快」说的正是中后期。所以门槛按阶段拆：

        (a) 中后期每个阶段的最佳候选 TV >= tv_gate；
        (b) 早期阶段最佳候选 TV >= tv_gate * early_ratio（可以不强，但不能退化到 0）；
        (c) 全阶段均值 >= tv_gate；
        (d) v3 新增：任一阶段因**覆盖率**被拒 -> 总门禁不通过。覆盖率是有效性条件，
            不是强度条件，不能靠别的阶段补回来（训练分布窄于环境一半，学出来的东西
            在标准评测上必然掉点）。

    TV 用哪个口径由每个阶段 verdict 的 `metric` 决定（有实测就用 `tv_distance`）。
    各阶段必须同口径，否则均值没有意义 —— 这里显式检查并写进返回的 `metric`。

    `per_ckpt_verdicts` 必须按训练阶段从早到晚排序（探针的 ckpt 顺序就是这个顺序）。
    """
    if not per_ckpt_verdicts:
        return {"ok": False, "reason": "没有探针结果", "best": None}
    pairs = [(v, v.get("best")) for v in per_ckpt_verdicts]
    if any(row is None for _, row in pairs):
        return {"ok": False, "reason": "存在没有候选的阶段", "best": None}
    metrics = sorted({(v.get("metric") or "tv") for v, _ in pairs})
    objectives = sorted({(v.get("objective") or "strength") for v, _ in pairs})

    def strength(pair: tuple) -> float:
        verdict, row = pair
        value = row.get(verdict.get("metric") or "tv")
        if value is None:
            value = row.get("tv")
        return float(value or 0.0)

    tvs = [strength(pair) for pair in pairs]
    label = "实测 TV距离" if metrics == ["tv_distance"] else "名义 TV"
    early, midlate = tvs[0], tvs[1:]
    reasons: list[str] = []
    ok = True
    if not midlate or min(midlate) < tv_gate:
        ok = False
        reasons.append(f"中后期最佳{label} {[round(t, 3) for t in midlate]} 有低于门槛 {tv_gate:g} 的")
    else:
        reasons.append(f"中后期最佳{label} {[round(t, 3) for t in midlate]} 全部 >= {tv_gate:g}")
    if early < tv_gate * early_ratio:
        ok = False
        reasons.append(f"早期最佳{label} {early:.3f} < {tv_gate * early_ratio:.3f}（退化）")
    else:
        reasons.append(f"早期最佳{label} {early:.3f} >= {tv_gate * early_ratio:.3f}"
                       f"（早期允许弱：失败尚无集中弱点）")
    mean_tv = float(np.mean(tvs))
    if mean_tv < tv_gate:
        ok = False
        reasons.append(f"全阶段均值 {mean_tv:.3f} < {tv_gate:g}")
    else:
        reasons.append(f"全阶段均值 {mean_tv:.3f} >= {tv_gate:g}")
    if any(v.get("coverage_ok") is False for v, _ in pairs):
        ok = False
        reasons.append("有阶段的训练距离覆盖窄于均匀的一半（有效性条件，不能被别的阶段补回）")
    if len(metrics) != 1:
        ok = False
        reasons.append(f"各阶段 TV 口径不一致 {metrics}，均值不可比")
    chosen = max((row for _, row in pairs),
                 key=lambda row: (float(row.get("tv_distance") if row.get("tv_distance") is not None
                                        else row.get("tv") or 0.0),
                                  -len(row.get("starved_bands") or [])))
    if objectives == ["coverage"]:
        chosen = max((row for _, row in pairs),
                     key=lambda row: (float(row.get("support_frac") or 0.0),
                                      float(row.get("tv_distance") if row.get("tv_distance") is not None
                                            else row.get("tv") or 0.0)))
    return {
        "ok": ok,
        "reason": "；".join(reasons),
        "best": chosen,
        "metric": "/".join(metrics),
        "objective": "/".join(objectives),
        "mean_tv": round(mean_tv, 4),
        "per_phase_tv": [round(t, 4) for t in tvs],
        "policy": ("gate_v3: 实测距离 TV（中后期过门槛 + 早期不退化 + 均值过门槛）"
                   " + 覆盖率合格 + fallback 带作废"),
    }


# ---------------------------------------------------------------------------
# 接触物理门禁 v1：上限 / 带内 / frontier / 成本 / 分辨率
# ---------------------------------------------------------------------------

_NORM = NormalDist()


def _zs(alpha: float, power: float) -> tuple[float, float]:
    """双侧 α 的临界值与功效对应的分位数（stdlib 精确值，不引 scipy）。"""
    return _NORM.inv_cdf(1.0 - alpha / 2.0), _NORM.inv_cdf(power)


def min_detectable_effect(n: int, p_base: float = 0.5, *, alpha: float = 0.05,
                          power: float = 0.8) -> float:
    """每臂 `n` 局的独立评测，能检出的最小成功率差 δ（两比例、双侧 α、功效 power）。

    解的是 `δ = (z_α + z_β) · sqrt(2·p̄(1-p̄)/n)`，其中 `p̄ = p_base + δ/2` 本身依赖 δ，
    所以定点迭代。

    **`p_base=0.5` 不是最保守口径**（这条被自检第 12 项抓出来过）：因为 δ 会把 p̄ 推到
    `p_base + δ/2`，`p_base=0.35` 时 p̄≈0.49 反而更靠近方差最大点，MDE(50, 0.35)=0.280
    > MDE(50, 0.5)=0.270。要上界请用 `mde_worst_case(n)`（p̄(1-p̄)=0.25 的闭式解）。

    这个数是 A/B 设计的地板：run7 的门禁 `min_gain=0.02` 配 `eval_episodes=50`，
    而 MDE(50) ≈ 0.28 —— 门禁放行的"提升"比它自己的噪声地板小一个量级，
    等价于按抛硬币发布版本。这条算术必须写在门禁里，不能靠人记。
    """
    if n <= 0:
        return float("inf")
    z_a, z_b = _zs(alpha, power)
    p = min(max(float(p_base), 1e-6), 1.0 - 1e-6)
    delta = (z_a + z_b) * math.sqrt(2.0 * p * (1.0 - p) / n)
    for _ in range(64):
        p_bar = min(max(p + delta / 2.0, 1e-6), 1.0 - 1e-6)
        new = (z_a + z_b) * math.sqrt(2.0 * p_bar * (1.0 - p_bar) / n)
        if abs(new - delta) < 1e-12:
            delta = new
            break
        delta = new
    return float(delta)


def mde_worst_case(n: int, *, alpha: float = 0.05, power: float = 0.8) -> float:
    """MDE 的闭式上界：`(z_α + z_β) · sqrt(0.5 / n)`（p̄(1-p̄) 取最大值 0.25）。

    任何 `p_base` 下 `min_detectable_effect(n, p_base) <= mde_worst_case(n)`，
    所以"最坏情况也判得起来吗"这句话要用它，不要用 `p_base=0.5`。
    """
    if n <= 0:
        return float("inf")
    z_a, z_b = _zs(alpha, power)
    return float((z_a + z_b) * math.sqrt(0.5 / n))


def required_episodes(delta: float, p_base: float = 0.5, *, alpha: float = 0.05,
                      power: float = 0.8, discordant: float | None = None) -> dict:
    """检出 δ 需要多少局：独立两臂口径 + （可选）逐题配对口径。

    配对口径用 McNemar 的样本量式
        n_pairs = [z_α·√d + z_β·√(d − δ²)]² / δ²
    `d` = 两臂结论不一致的题目占比，δ = 净成功率差。

    **硬约束 |δ| <= d**（比公式定义域 d >= δ² 强得多，别只查后者）：
    δ=(c−b)/n、d=(b+c)/n、b,c>=0 ⇒ |c−b| <= b+c。所以「想检出的差」本身就给
    不一致率封了下界，配对能省的局数**被效应量卡死**，不是可以无限小。
    δ=0.20 时 d 最小只能取 0.20（所有翻转同向），对应 n_pairs=37；
    旧版只查 d >= δ²=0.04，于是 (δ=0.20, d=0.10) 这种**不可达**组合被当成有解、
    给出 18 对，§12.11-H 一度照抄成「省 4.4×」（真实上界 79/37≈2.1×）。
    `paired_floor_pairs` 就是这条下界，报数不许低于它。

    **配对不是白省的**，这条必须写死在文档里，否则会被拿去合理化更小的评测预算：
    独立两臂的方差是 `2·p(1−p)/n`，配对是 `(d − δ²)/n`，所以
        d < 2·p(1−p)  ⇒ 配对省局数；   d > 2·p(1−p)  ⇒ 配对反而更贵。
    p≈0.5 时分界点 d=0.5。落到本项目：
      · 「手写控制器 vs SAC」配对（实测 d≈0.9：手写全成、SAC 全不成）—— 不省局数，
        这种配对的价值在**诊断**（失败卡在哪一段），不在预算；
      · A/B 两条臂（uniform 采样 vs 诊断采样，两个**相似**策略）配对 —— d 很小
        （绝大多数题目两臂同结论），这才是省局数的地方；但"很小"有下界 |δ|。
    配对口径成立的前提是同 seed 真出同一道题：robosuite 包装层的 `reset(seed=)` 只播种
    自己的 rng，物体摆放由 `placement_initializer.rng` 决定、没人播种 ⇒ 同 seed 四次
    四个出生点，配对会安静退化成配噪声（探针 `verify_seeding()` 就是为此存在的）。

    `paired_cheaper`（方差判据 d < 2p(1−p)）与 `paired_cheaper_by_n`（按算出来的局数比）
    在盈亏平衡点附近**会不一致**：独立口径的局数由 `min_detectable_effect` 定点迭代得到、
    配对口径是 McNemar 闭式，两者不是同一套近似。做预算按 `by_n`，讲原理按方差判据。
    """
    delta = float(delta)
    if delta <= 0:
        return {"delta": delta, "unpaired_per_arm": None, "paired_pairs": None,
                "reason": "δ<=0，无解"}
    z_a, z_b = _zs(alpha, power)
    lo, hi = 2.0, 1.0e9
    for _ in range(200):                       # 对 n 二分：MDE(n) 单调下降
        mid = math.sqrt(lo * hi)
        if min_detectable_effect(int(mid), p_base, alpha=alpha, power=power) > delta:
            lo = mid
        else:
            hi = mid
        if hi / lo < 1.0001:
            break
    out = {"delta": round(delta, 4), "p_base": round(float(p_base), 4),
           "alpha": alpha, "power": power,
           "unpaired_per_arm": int(math.ceil(hi)),
           "mde_at_50": round(min_detectable_effect(50, p_base, alpha=alpha, power=power), 4)}
    if discordant is not None:
        d = max(float(discordant), 1e-6)
        p_clamped = min(max(float(p_base), 0.0), 1.0)
        out["discordant"] = round(d, 4)
        break_even_d = 2.0 * p_clamped * (1.0 - p_clamped)

        def _n_pairs_at(dd: float) -> int:
            return int(math.ceil((z_a * math.sqrt(dd)
                                  + z_b * math.sqrt(max(dd - delta ** 2, 0.0))) ** 2
                                 / delta ** 2))

        # 配对样本量的数学下界：d 最小只能取 |δ|（全部翻转同向）
        out["paired_floor_pairs"] = _n_pairs_at(max(delta, 1e-6))
        if d < delta - 1e-12:
            out["paired_pairs"] = None
            out["paired_reason"] = (
                f"d={d:g} < |δ|={delta:g}：不一致率不可能小于净成功率差"
                f"（δ=(c−b)/n、d=(b+c)/n、b,c>=0 ⇒ |δ|<=d），该组合不可达；"
                f"配对最少也要 {out['paired_floor_pairs']} 对")
        else:
            out["paired_pairs"] = _n_pairs_at(d)
            out["paired_at_floor"] = bool(abs(d - delta) <= 1e-9)
            out["paired_cheaper"] = bool(d < break_even_d)
            out["paired_cheaper_by_n"] = bool(out["paired_pairs"] < out["unpaired_per_arm"])
            if out["paired_cheaper"] == out["paired_cheaper_by_n"]:
                out["paired_note"] = (
                    "配对省局数（d < 2p(1-p)，两臂高度一致）" if out["paired_cheaper"] else
                    "配对**更贵**（d > 2p(1-p)）：这种配对用于诊断，别拿它省预算")
            else:
                out["paired_note"] = (
                    f"两个口径不一致：方差判据 d={d:g} vs 2p(1-p)={break_even_d:.3f} 说"
                    f"{'省' if out['paired_cheaper'] else '不省'}，但按算出的局数 "
                    f"{out['paired_pairs']} vs {out['unpaired_per_arm']} 说"
                    f"{'省' if out['paired_cheaper_by_n'] else '不省'}。二者在盈亏平衡点附近"
                    f"本来就不严格同步（独立口径是定点迭代、配对是闭式）。"
                    f"做预算按局数，讲原理按方差判据。")
    return out


def frontier_verdict(rungs: list[dict], *, band: tuple[float, float] = (0.05, 0.90),
                     ceiling_min: float = 0.90, ceiling_broken: float = 0.50,
                     frontier_min: float = 0.10, too_hard_max: float = 0.50,
                     budget_sec: float = 8 * 3600.0, arms: int = 6, rounds: int = 10,
                     episodes_per_round: int = 8, train_sec_per_round: float = 0.0,
                     eval_every: int = 1, eval_sec_per_episode: float | None = None,
                     eval_episodes: int = 50, min_gain: float = 0.02,
                     regression_tol: float = 0.0, p_base: float | None = None,
                     alpha: float = 0.05, power: float = 0.8,
                     flick_max: float = 0.5, grasp_gap_warn: float = 0.05) -> dict:
    """接触任务的 A/B 前置门禁：把「先量上限、再算成本、最后才烧预算」变成代码。

    `rungs` 是难度阶梯（探针按物体出生盒子半宽扫出来的），每档一个 dict：
        half_range          难度旋钮取值（出生盒子半宽，米）
        scripted_success    手写参照成功率（上限）
        sac_success         被测策略成功率（可选，None = 只量了上限）
        frontier_frac       逐题配对里「手写成、策略不成」的占比（可选）
        too_hard_frac       「两者都不成」的占比（可选）
        sec_per_episode     实测每局墙钟秒数（成本规则要用实测值，不要用标称值）
        seeding_ok          同 seed 出题可复现（默认 True；False ⇒ 整档数据作废）
        ctrl_z0_mismatch    控制器初始高度与本局出生点不符的局数（默认 0）
        object_pinned       物体尺寸是否已钉死（True/False/None=产物没这个字段）。
                            robosuite 在**构造期**用未播种的 `np.random.default_rng()` 抽
                            cube 尺寸（`lift.py:311` 的 size_min/size_max），所以没钉死时
                            每个进程评的是**不同物体**（§12.11-M / §7 第 23 条）⇒ False 判废。
        flick_frac          成功局里"没有抓取真值"的占比（弹起式成功，§12.11-N）。
                            Lift 的 `_check_success` 只看高度，指间把 cube 弹过阈值也算成功。
        success_rate_grasp_verified
                            成功**且** `_check_grasp` 为真的比例（"真抓起来"的成功率）。

    六条规则，任一不过 ⇒ 这一档不能开 A/B（`ok=False`，`reasons` 说明是哪条）：
      · `data`       出题可复现 + 控制器 z0 与出生点一致 + **物体尺寸已钉死**
                     （否则量的是 bug / 是另一个物体，不是这个任务的物理难度）；
      · `ceiling`    手写上限 >= ceiling_min；< ceiling_broken 直接判「先修控制器」；
      · `band`       策略成功率落在 band 内（贴地=无分辨力，饱和=无可学）；
      · `frontier`   frontier_frac >= frontier_min 且 too_hard_frac <= too_hard_max；
      · `metric`     flick_frac < flick_max：成功率这个指标本身得是"完成任务"，
                     否则门禁会被"弹一下"通过（reward hacking 的最小 specimen）；
      · `cost`       (采集局/轮 + 评测局数/eval_every) × sec_per_ep × 轮 × 臂
                     + 训练秒 × 轮 × 臂 <= budget_sec。
                     **评测必须计入**：接触任务里失败局要跑满 horizon（Lift 实测 35 s/局），
                     `eval_episodes=50 × 10 轮` 就是 4.9 h/臂，比训练（671 s/轮 → 1.9 h/臂）
                     还贵一倍多。漏掉这一项会把「6 臂 8 h」算成买得起，实际单臂就要 7.5 h。
                     这也解释了为什么「加评测局数换分辨率」这条路在接触任务上走不通：
                     分辨率与成本在这里是**直接对立**的，出路是配对评测（同 seed 两臂、
                     McNemar，d 小 ⇒ 用更少局数检出同样效应）或只在 frontier 子集上评测。
    外加一条与档位无关的全局规则（两个方向都要过，因为它们坏的是同一件事——可解释性）：
      · `resolution` min_gain **和** regression_tol 都必须 >= MDE(eval_episodes)。
        前者不足 ⇒ 按噪声发布版本；后者不足 ⇒ 按噪声**拒绝**中性候选。
        零容忍掉点（`regression_tol=0`）配 50 局评测，真值相同时约一半概率被拒：
        run7 决定性臂的 round 3 就是这么被拒的（0.08 vs incumbent 0.14，差 0.06 ≈ 0.85σ），
        而 round 1 的 +0.140 也是 1.4σ 的噪声却被放行 —— 同一套门禁两头都在抛硬币。

    返回里 `recommended` 是**通过全部规则且 frontier 最大**的一档（针对性采样最有对象的
    地方）；`affordable_arms` 告诉你在预算内最多养几条臂 —— 阶段 3 想开 6 臂，
    接触任务实测每局 5~120 s，这条算术通常直接把臂数砍到 1~2。
    """
    if not rungs:
        return {"ok": False, "reason": "没有难度档数据", "rungs": [], "recommended": None,
                "checks": {}, "warnings": [], "policy": "frontier_v1"}
    # 分辨率算在哪个工作点上：`p_base=None` 时用**实测**的策略成功率均值（探针量到的），
    # 没有实测值才退回 0.5（最保守，p̄(1-p̄) 的最大值）。两者都写进 checks：
    # 保守值用于"最坏情况也过得去吗"，实测值用于"在当前水平上要几局"。
    if p_base is None:
        measured = [float(r["sac_success"]) for r in rungs if r.get("sac_success") is not None]
        p_base = float(np.mean(measured)) if measured else 0.5
        p_src = ("measured(mean sac_success=%.3f, n_rungs=%d)" % (p_base, len(measured))
                 if measured else "fallback 0.5（没有策略侧实测值，取最保守）")
    else:
        p_src = f"explicit({p_base:g})"
    mde = min_detectable_effect(eval_episodes, p_base, alpha=alpha, power=power)
    mde_worst = mde_worst_case(eval_episodes, alpha=alpha, power=power)
    gain_ok = bool(min_gain >= mde)
    tol_ok = bool(regression_tol >= mde)
    res_ok = gain_ok and tol_ok
    need = required_episodes(min_gain, p_base, alpha=alpha, power=power)
    need_tol = required_episodes(regression_tol, p_base, alpha=alpha, power=power) \
        if regression_tol > 0 else {"unpaired_per_arm": None}
    bad_bits = []
    if not gain_ok:
        bad_bits.append(f"min_gain={min_gain:g} < MDE ⇒ 按噪声**发布**")
    if not tol_ok:
        bad_bits.append(f"regression_tol={regression_tol:g} < MDE ⇒ 按噪声**拒绝**"
                        + ("（零容忍 = 真值相同时约一半概率被拒）" if regression_tol <= 0 else ""))
    checks = {
        "resolution": {
            "ok": res_ok, "gain_ok": gain_ok, "tol_ok": tol_ok,
            "eval_episodes": eval_episodes, "p_base": round(p_base, 4), "p_base_source": p_src,
            "min_detectable_effect": round(mde, 4),
            "min_detectable_effect_worst_case": round(mde_worst, 4),
            "min_gain": min_gain, "regression_tol": regression_tol,
            "episodes_needed_for_min_gain": need.get("unpaired_per_arm"),
            "episodes_needed_for_tol": need_tol.get("unpaired_per_arm"),
            "reason": (f"评测 {eval_episodes} 局的噪声地板 MDE={mde:.3f}"
                       f"（工作点 {p_src}；最坏情况上界 {mde_worst:.3f}）；"
                       + ("；".join(bad_bits) if bad_bits else "min_gain 与掉点容忍度都在噪声地板之上")
                       + ("" if res_ok else
                          f"。两条出路：把评测提到 {need.get('unpaired_per_arm')} 局量级，"
                          "或改成**逐题配对**评测（两臂同 seed 同题，用 McNemar；"
                          "两个相似策略的 d 很小，能省好几倍局数）")),
        },
        "band": list(band), "ceiling_min": ceiling_min, "ceiling_broken": ceiling_broken,
        "frontier_min": frontier_min, "too_hard_max": too_hard_max,
        "budget_sec": budget_sec, "arms": arms, "rounds": rounds,
        "episodes_per_round": episodes_per_round, "train_sec_per_round": train_sec_per_round,
        "eval_every": eval_every, "eval_sec_per_episode": eval_sec_per_episode,
    }

    per: list[dict] = []
    for rung in rungs:
        hr = rung.get("half_range")
        p_scr = rung.get("scripted_success")
        p_sac = rung.get("sac_success")
        ff = rung.get("frontier_frac")
        th = rung.get("too_hard_frac")
        sec = float(rung.get("sec_per_episode") or 0.0)
        failed: list[str] = []
        reasons: list[str] = []
        rung_warnings: list[str] = []
        pinned = rung.get("object_pinned")
        flick = rung.get("flick_frac")
        p_sac_gv = rung.get("success_rate_grasp_verified")

        if rung.get("seeding_ok", True) is False or int(rung.get("ctrl_z0_mismatch") or 0) > 0:
            failed.append("data")
            reasons.append(f"出题不可复现或控制器 z0 与出生点不符（{rung.get('ctrl_z0_mismatch')} 局）"
                           " ⇒ 这一档量到的是时序 bug，不是物理难度，整档作废")
        if pinned is False:
            failed.append("data")
            reasons.append("物体尺寸未钉死（`object_pinned=False`）⇒ robosuite 在构造期用"
                           "**未播种**的 default_rng() 抽 cube 尺寸，每个进程评的是不同物体"
                           "（实测质量差 0.9%、初始 z 差 1.6 mm，被接触动力学混沌放大成"
                           "完全不同的 rollout）⇒ 跨进程/跨 run 不可比，整档作废")
        elif pinned is None:
            # 旧产物没有这个字段：不追溯判废（否则历史数据全部读不了），但必须点名，
            # 否则会被当成"已验证可复现"。
            rung_warnings.append("产物没有 object_pinned/object_geom 字段（早于物体尺寸钉死的"
                                 "版本）⇒ 它评的 cube 与本 run 未必是同一个，逐 seed 对照必然失败，"
                                 "跨 run 只能带区间比聚合成功率")

        if flick is not None:
            if flick >= flick_max:
                failed.append("metric")
                reasons.append(f"弹起式成功占 {flick:.0%} >= {flick_max:.0%} ⇒ 成功率这个指标"
                               f"主要不是「真抓起来」（grasp-verified 只有 "
                               f"{p_sac_gv if p_sac_gv is not None else '未记录'}）；"
                               "先改成功口径（要求 `_check_grasp` 为真）再谈 A/B，"
                               "否则门禁会被「弹一下」通过")
            elif flick > 0:
                rung_warnings.append(f"有 {flick:.0%} 的成功局没有抓取真值（弹起式成功）⇒ "
                                     f"`sac_success` 被高估，grasp-verified 口径为 "
                                     f"{p_sac_gv}；band 规则用的仍是被高估的那个数")
        if (p_sac is not None and p_sac_gv is not None
                and p_sac - float(p_sac_gv) >= grasp_gap_warn):
            rung_warnings.append(f"策略成功率 {p_sac:.3f} 与 grasp-verified {float(p_sac_gv):.3f} "
                                 f"差 {p_sac - float(p_sac_gv):.3f} >= {grasp_gap_warn:g} ⇒ "
                                 "band/分辨率的工作点都该用后者重算")
        if p_scr is None:
            failed.append("ceiling")
            reasons.append("没有手写上限数据")
        elif p_scr < ceiling_broken:
            failed.append("ceiling")
            reasons.append(f"手写上限 {p_scr:.2f} < {ceiling_broken:g} ⇒ 先修控制器/动作栈，"
                           "现在连「成功长什么样」都没有可靠参照")
        elif p_scr < ceiling_min:
            failed.append("ceiling")
            reasons.append(f"手写上限 {p_scr:.2f} < {ceiling_min:g} ⇒ 上限侧本身在漏，"
                           "先把手写参照补到满分再谈策略")
        else:
            reasons.append(f"手写上限 {p_scr:.2f} 满分/接近满分，参照可信")

        if p_sac is None:
            reasons.append("未评测策略：这一档只能当上限数据用，还不能开 A/B")
            failed.append("band")
        elif not (band[0] <= p_sac <= band[1]):
            failed.append("band")
            side = "贴地" if p_sac < band[0] else "饱和"
            fix = ("全局成功率无分辨力（失败全长一个样），改用**条件成功率**"
                   "（按出生格/难度档）做统计量，或先降难度" if p_sac < band[0]
                   else "没有可学空间，加难度档或换任务")
            reasons.append(f"策略成功率 {p_sac:.2f} {side}（band {band[0]:g}~{band[1]:g}）⇒ {fix}")
        else:
            reasons.append(f"策略成功率 {p_sac:.2f} 在 band 内，存在爬升段")

        if ff is not None:
            if ff < frontier_min:
                failed.append("frontier")
                reasons.append(f"frontier 只占 {ff:.1%} < {frontier_min:.0%} ⇒ "
                               "针对性采样几乎无处发力，先降难度/加课程")
            elif th is not None and th > too_hard_max:
                failed.append("frontier")
                reasons.append(f"「都不成」占 {th:.1%} > {too_hard_max:.0%} ⇒ "
                               "采样放到这里也学不到，先降难度")
            else:
                reasons.append(f"frontier {ff:.1%}（都不成 {th if th is None else f'{th:.1%}'}）"
                               " ⇒ 有可瞄准的区域")

        eval_sec = sec if eval_sec_per_episode is None else float(eval_sec_per_episode)
        n_evals = rounds / max(int(eval_every), 1)
        collect = sec * episodes_per_round * rounds * arms
        evaluate = eval_sec * eval_episodes * n_evals * arms
        train = float(train_sec_per_round) * rounds * arms
        total = collect + evaluate + train
        if sec <= 0:
            reasons.append("缺 sec_per_episode 实测值，成本规则跳过（不要拿标称值替代）")
        elif total > budget_sec:
            failed.append("cost")
            reasons.append(f"成本 {total / 3600:.1f} h（采集 {collect / 3600:.1f} h + "
                           f"评测 {evaluate / 3600:.1f} h + 训练 {train / 3600:.1f} h）"
                           f" > 预算 {budget_sec / 3600:.1f} h；"
                           f"单臂 {(total / max(arms, 1)) / 3600:.1f} h")
        else:
            reasons.append(f"成本 {total / 3600:.1f} h（采集 {collect / 3600:.1f} + "
                           f"评测 {evaluate / 3600:.1f} + 训练 {train / 3600:.1f}）"
                           f" <= 预算 {budget_sec / 3600:.1f} h")
        per_arm = (sec * episodes_per_round * rounds + eval_sec * eval_episodes * n_evals
                   + float(train_sec_per_round) * rounds)
        affordable = int(budget_sec // max(per_arm, 1e-9)) if sec > 0 else None

        per.append({"half_range": hr, "ok": not failed, "failed": failed, "reasons": reasons,
                    "warnings": rung_warnings, "object_pinned": pinned, "flick_frac": flick,
                    "success_rate_grasp_verified": p_sac_gv,
                    "scripted_success": p_scr, "sac_success": p_sac,
                    "frontier_frac": ff, "too_hard_frac": th,
                    "sec_per_episode": sec,
                    "cost_hours": round(total / 3600, 2) if sec > 0 else None,
                    "affordable_arms": min(affordable, arms) if affordable is not None else None,
                    "affordable_arms_raw": affordable})

    feasible = [r for r in per if r["ok"]]
    recommended = None
    if feasible:
        recommended = max(feasible, key=lambda r: (r.get("frontier_frac") or 0.0,
                                                   -(r.get("sac_success") or 0.0)))
    warnings: list[str] = []
    if not res_ok:
        warnings.append(checks["resolution"]["reason"])
    elif not tol_ok or not gain_ok:
        warnings.append(checks["resolution"]["reason"])
    # 臂数上限对**所有**档位都算（包括因成本被拒的）：被拒的原因本身就是臂数太多，
    # 只在 feasible 里算会让最需要这条提示的档位反而没有提示。
    arm_caps = [r["affordable_arms_raw"] for r in per if r["affordable_arms_raw"] is not None]
    if arm_caps and min(arm_caps) < arms:
        checks["affordable_arms_min"] = min(arm_caps)
        warnings.append(f"按实测每局墙钟，预算 {budget_sec / 3600:.0f} h 内最多养 "
                        f"{min(arm_caps)} 条臂（计划 {arms} 条）：接触任务的每局秒数是硬约束，"
                        "先砍臂数或砍轮数，别砍评测局数（评测局数决定分辨率）")
    if any(r.get("frontier_frac") is None for r in per):
        warnings.append("有档位缺逐题配对数据（frontier_frac）：只凭上限+带内不足以选采样轴")
    for r in per:                                   # 档位级警告（去重后并进全局）
        for w in r.get("warnings") or []:
            if w not in warnings:
                warnings.append(w)
    reason = ("；".join(f"{r['half_range']}: " + ("通过" if r["ok"] else "/".join(r["failed"]))
                       for r in per))
    return {
        "ok": bool(feasible and res_ok),
        "reason": (f"可用难度档 {[r['half_range'] for r in feasible] or '无'}"
                   f"{'；分辨率规则未过：' + checks['resolution']['reason'] if not res_ok else ''}"),
        "detail": reason,
        "rungs": per,
        "recommended": recommended,
        "checks": checks,
        "warnings": warnings,
        "policy": ("frontier_v2: data(出题可复现 + 物体尺寸已钉死) + ceiling(手写满分) "
                   "+ band(策略在爬升段) + frontier(可瞄准区够大) + metric(成功率不是靠弹起) "
                   "+ cost(预算内，按实测每局墙钟) + resolution(评测局数能检出 min_gain)"),
    }


# ---------------------------------------------------------------------------
# 配对评测：接触任务里唯一买得起的分辨率（§12.11-F/H）
# ---------------------------------------------------------------------------

def mcnemar(only_a: int, only_b: int) -> dict:
    """McNemar 检验：`only_a` = 只 A 成功的题数，`only_b` = 只 B 成功的题数。

    为什么配对能省局数：两臂跑**同一批 seed**，题目难度这个最大的方差来源被消掉，
    检验只看「结论翻转」的题。方差从独立口径的 `2p(1-p)/n` 变成 `(d-δ²)/n`
    （d = 不一致率），所以 `d < 2p(1-p)` 时省、反之更贵（见 `required_episodes`）。

    精确口径用二项检验 `Binom(only_a+only_b, 0.5)`（大整数精确算，不做正态近似），
    同时给带连续性校正的 χ² 便于与文献对齐。`only_a+only_b = 0` 时两臂逐题同结论 ——
    这不是"证据不足"，而是差异为 0 的直接证据（p=1.0）。
    χ²(1) 的上尾概率用 `erfc` 闭式，避免为一个检验引入 scipy。
    """
    b, c = int(only_a), int(only_b)
    m = b + c
    if m == 0:
        return {"only_a": b, "only_b": c, "discordant": 0, "discordant_rate": None,
                "exact_p": 1.0, "chi2_cc": 0.0, "chi2_p": 1.0, "method": "no_discordant"}
    k = min(b, c)
    tail = sum(math.comb(m, i) for i in range(k + 1))
    exact_p = min(1.0, 2.0 * tail / (2 ** m))
    chi2 = (abs(b - c) - 1) ** 2 / m
    return {"only_a": b, "only_b": c, "discordant": m,
            "exact_p": round(float(exact_p), 6), "chi2_cc": round(chi2, 4),
            "chi2_p": round(math.erfc(math.sqrt(chi2 / 2.0)), 6),
            "method": "exact_binomial+chi2_cc"}


def paired_gate(n_pairs: int, only_new: int, only_inc: int, *, alpha: float = 0.05,
                min_pairs: int = 10) -> dict:
    """配对版的发布判定，**三态**：publish / reject_regression / inconclusive。

    现在的 `registry/publish.py::decide` 只有二态（过 min_gain 就发布、掉点就拒绝），
    而它的两个阈值（`min_gain=0.02`、掉点容忍 0）都低于 50 局评测的噪声地板
    MDE≈0.22~0.28 ⇒ 同一条臂上既能用 +0.02（p=0.31）发布，也能用 −0.06（p=0.34）拒绝
    （run7 决定性臂 rounds 6 与 3，§12.11-G）。**缺的就是第三态**：
    差异不显著时既不该发布也不该判掉点，应该记 `inconclusive` 并保留现任。

    规则：
      · `n_pairs < min_pairs` ⇒ inconclusive（样本太少，检验没有意义）；
      · McNemar 精确 p < alpha 且 only_new > only_inc ⇒ publish；
      · McNemar 精确 p < alpha 且 only_inc > only_new ⇒ reject_regression；
      · 其余 ⇒ inconclusive（保留现任，不做任何"提升/掉点"的断言）。
    """
    if n_pairs < min_pairs:
        return {"decision": "inconclusive", "reason": f"配对题数 {n_pairs} < {min_pairs}，检验无意义",
                "mcnemar": None, "alpha": alpha}
    mc = mcnemar(only_new, only_inc)
    p = mc["exact_p"]
    if p < alpha and only_new > only_inc:
        decision, reason = "publish", (
            f"新候选显著更好：翻转题 {only_new} vs {only_inc}，McNemar 精确 p={p:.4f} < {alpha:g}")
    elif p < alpha and only_inc > only_new:
        decision, reason = "reject_regression", (
            f"新候选显著更差（掉点）：翻转题 {only_new} vs {only_inc}，p={p:.4f} < {alpha:g}")
    else:
        decision, reason = "inconclusive", (
            f"翻转题 {only_new} vs {only_inc}，McNemar 精确 p={p:.4f} >= {alpha:g}："
            f"差异不显著，**既不能发布也不能判掉点**，保留现任（这正是旧二态门禁缺的那一态）")
    d = mc["discordant"] / max(n_pairs, 1)
    return {"decision": decision, "reason": reason, "mcnemar": mc, "alpha": alpha,
            "n_pairs": n_pairs, "discordant_rate": round(d, 4),
            "mde_worst_case": round(mde_worst_case(n_pairs), 4),
            "policy": "paired_gate_v1: McNemar 精确检验 + 三态判定（publish/reject/inconclusive）"}
