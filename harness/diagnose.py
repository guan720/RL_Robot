"""诊断层：把「失败了」变成「为什么失败」，再变成「下一轮该采什么题」。

这是 harness 相对于「无脑多训一会儿」的唯一价值所在，也是 RoboRSI 里 Reviewer
角色干的事（见 `docs/roborsi-callchain.md`）。三段式：

    1. label_episode   一条轨迹 -> 一个失败标签（只看距离轨迹，不猜内部原因）
    2. summarize       一批轨迹 -> 失败分布 + 建议的距离采样区间
    3. SamplingPlan    把建议交给 `harness/sampling.py` 去真正改变训练时看到的题

标签的定义刻意只用**客观量**（init/min/final 距离、步数），不用任何模型解释。
原因和 `skills/base.py` 里「成败只认环境判定」是同一条纪律：诊断可以启发采样，
但不能改写成功判定，否则会出现「诊断说成功了所以算成功」的 reward hacking。

五个标签：
    success        环境判定成功
    never_moved    几乎没动（min ≈ init）。多半是动作没接上 / 输出恒 0 / 死区太大
    no_precision   曾经进到 2×半径内（含边界），最后却停在圈外。控制精度问题，不是找不着路
    timeout_far    超时且离目标还远（> 4×半径）。探索/可达性问题
    timeout_mid    超时，最近距离落在 2×~4×半径之间（开区间）。介于「找不着」和「差一点」
    diverged       越走离目标越远。方向性错误

边界约定：`NEAR_FACTOR` / `FAR_FACTOR` 的比较都是「最近距离 <= 2×半径」这种闭区间，
所以 `min_dist` 正好等于 2×半径时判为 `no_precision` 而不是 `timeout_mid`。
这不是随意选的：既然曾经摸到 2×半径，就说明「路是找得到的」，问题出在收尾精度上，
该采的下一批题是边界目标而不是更近的目标。
"""

from __future__ import annotations

import dataclasses
import math
from collections import Counter

import numpy as np

from skills.base import EpisodeRecord

NEVER_MOVED_RATIO = 0.97     # min_dist / init_dist 高于此值 = 基本没动
NEAR_FACTOR = 2.0            # 曾进入 goal_radius 的多少倍以内算「到过附近」
FAR_FACTOR = 4.0             # 超过 goal_radius 的多少倍算「还很远」


def label_episode(record: EpisodeRecord, goal_radius: float, moved_eps: float = 0.01) -> str:
    """给一条轨迹贴失败标签。`goal_radius` 必须与评测时一致，否则标签不可比。"""
    if record.success:
        return "success"
    init = record.init_dist
    best = record.min_dist
    final = record.final_dist
    if not all(math.isfinite(x) for x in (init, best, final)) or init <= 0:
        return "unknown"
    if final > init * 1.02:
        return "diverged"
    if best >= init * NEVER_MOVED_RATIO and (init - best) < moved_eps:
        return "never_moved"
    if best <= goal_radius * NEAR_FACTOR:
        return "no_precision"
    if final > goal_radius * FAR_FACTOR:
        return "timeout_far"
    return "timeout_mid"


def label_all(records: list[EpisodeRecord], goal_radius: float) -> list[EpisodeRecord]:
    """就地补齐 record.label 并返回，方便直接序列化。"""
    for record in records:
        if not record.label:
            record.label = label_episode(record, goal_radius)
    return records


@dataclasses.dataclass
class SamplingPlan:
    """诊断层给采样层的唯一接口：一个「初始目标距离」的加权分布。

    Reach 的难度几乎完全由「起点到目标的距离」决定（起点固定在原点），
    所以针对性采样最干净的表达就是：多采失败集中的那个距离带。
    换成 PickPlace 之后，这里会换成 (物体初位, 目标位) 的联合分布，
    但接口形状不变 —— 上层只认 `bands` 和 `weights`。
    """

    bands: list[tuple[float, float]]      # [(lo, hi), ...] 单位米
    weights: list[float]                  # 与 bands 等长，会被归一化
    reason: dict = dataclasses.field(default_factory=dict)

    def normalized(self) -> "SamplingPlan":
        total = sum(self.weights) or 1.0
        return SamplingPlan(self.bands, [w / total for w in self.weights], self.reason)

    def to_dict(self) -> dict:
        return {
            "bands": [[round(float(a), 4), round(float(b), 4)] for a, b in self.bands],
            "weights": [round(float(w), 4) for w in self.weights],
            "reason": self.reason,
        }


def summarize(records: list[EpisodeRecord], goal_radius: float, half_space: float = 0.15,
              band_mode: str = "range", floor: float = 0.15, n_bands: int = 4) -> dict:
    """汇总一批轨迹：成功率、按方向拆分、标签分布、以及建议的采样计划。"""
    label_all(records, goal_radius)
    total = len(records)
    counts = Counter(r.label for r in records)
    by_direction: dict[str, dict] = {}
    for direction in sorted({r.direction for r in records}):
        sub = [r for r in records if r.direction == direction]
        by_direction[direction] = {
            "n": len(sub),
            "success_rate": round(sum(r.success for r in sub) / max(1, len(sub)), 4),
            "mean_final_dist": round(sum(r.final_dist for r in sub) / max(1, len(sub)), 5),
            "labels": dict(Counter(r.label for r in sub)),
        }

    failures = [r for r in records if not r.success]
    plan = build_sampling_plan(failures, goal_radius, half_space,
                               n_bands=n_bands, floor=floor, band_mode=band_mode)

    # Phase counts are deliberately descriptive only: they never override the
    # environment success flag.  ACT/RL and contact skills can expose a phase
    # in ``info``; legacy Reach records simply produce an empty mapping.
    phase_counts = Counter(p for r in records for p in r.phase_trace if p)
    failure_phases = Counter(r.failure_phase for r in failures if r.failure_phase)
    grasp_values = [r.success_grasp_verified for r in records
                    if r.success_grasp_verified is not None]

    return {
        "n_episodes": total,
        "success_rate": round(sum(r.success for r in records) / max(1, total), 4),
        "env_steps": int(sum(r.env_steps for r in records)),
        "labels": dict(counts),
        "by_direction": by_direction,
        "mean_final_dist": round(sum(r.final_dist for r in records) / max(1, total), 5),
        "mean_steps": round(sum(r.steps for r in records) / max(1, total), 2),
        "phase_counts": dict(phase_counts),
        "failure_phases": dict(failure_phases),
        "success_raw_rate": round(sum(bool(r.success_raw) for r in records) / max(1, total), 4)
        if any(r.success_raw is not None for r in records) else None,
        "success_grasp_verified_rate": round(sum(grasp_values) / max(1, len(grasp_values)), 4)
        if grasp_values else None,
        "mean_max_rise": round(float(np.nanmean([r.max_rise for r in records
                                                   if r.max_rise is not None])), 5)
        if any(r.max_rise is not None for r in records) else None,
        "sampling_plan": plan.to_dict(),
    }


def build_sampling_plan(
    failures: list[EpisodeRecord],
    goal_radius: float,
    half_space: float = 0.15,
    n_bands: int = 4,
    floor: float = 0.15,
    band_mode: str = "range",
) -> SamplingPlan:
    """把失败轨迹的**初始距离**直方图变成加权采样区间。

    `floor` 是给每个区间保底权重：即使某个距离带一次都没失败，也要继续采一点，
    否则会退化成只在窄带上训练 —— 那就是灾难性遗忘的起点，也是「累计覆盖涨了、
    旧任务掉点」这种指标陷阱的成因（见 `docs/ROADMAP.md` §5）。

    `band_mode` 是 2026-09-23 加的旋钮，起因是一次实测的自我纠错：
      · `range`（原行为）：带边铺满 [2*goal_radius, half*sqrt(3)]。但扰动基准的环境
        最小目标距离是 0.1，于是**第一条带 [0.04, 0.095) 构造上永远为空**，
        权重永远等于 floor；外圈带失败又少 -> 实测 17/18 轮两头的带被钉死，
        干预的总变差距离只有 0.24，A/B 测不出差异（见 notes_stage3.md §6.6）。
      · `quantile`：带边取失败初始距离的经验分位数，保证每条带都有失败样本，
        floor 只负责「防遗忘」而不是「填空带」。干预强度先用量探针验证
        （`scripts/probe_intervention_design.py`），TV 过门槛才允许花预算跑 A/B。
    失败样本少于 n_bands 时 quantile 退化成 range —— 没数据就别装有针对性。

    `labelcond`（2026-09-23 探针实测后加的第三种）：不按「失败发生在哪个初始距离」分带，
    而按「这类失败**应该**在哪个距离练」分带（`LABEL_TARGET_DISTANCE`）：
      · no_precision  在它卡住的半径（min_dist）上练 —— 精度失败要推边界，不是重做整局；
      · diverged / never_moved  拉近了练（×0.6 / ×0.5）—— 先学会短距离收敛；
      · timeout_far / timeout_mid  在 ×0.8 / ×1.0 的初始距离上练。
    探针（scripts/probe_intervention_design.py）实测：quantile 分带因为**构造上把失败
    均分到各带**，TV≈0，等于没有干预；range 分带把 TV 卡在 0.2~0.3；只有换条件变量
    （labelcond）+ 调低 floor 才可能把干预强度推过门槛。
    """
    lo, hi = goal_radius * 2.0, half_space * math.sqrt(3.0)
    if band_mode not in ("range", "quantile", "labelcond", "frontier"):
        raise ValueError(f"band_mode 只能是 range/quantile/labelcond/frontier，收到 {band_mode!r}")
    distances = sorted(float(r.init_dist) for r in failures)
    if band_mode == "labelcond":
        distances = sorted(target_distance(r) for r in failures)
    elif band_mode == "frontier":
        # 能力前沿分带：不看目标在哪、看策略**实际摸到过**多近（min_dist）。
        # 动机来自探针实测：labelcond 对早期失败（diverged 为主）仍然弱，
        # 因为早期失败的目标距离 spread 很大；而「最近摸到哪儿」在每一个训练阶段
        # 都贴着策略当前的能力边界，早期也集中 —— 干预强度不依赖策略水平。
        distances = sorted(float(r.min_dist) for r in failures)
    # labelcond 的目标距离可能落在带域之外（no_precision 的 min_dist 常常 < lo，
    # 意思是「尽量近地练」）。不钳进去的话这些失败一条带都进不了，
    # hist 全零 -> floor=0 时权重全零 -> TV 变 nan（探针实测踩过）。
    distances = [min(max(d, lo), hi - 1e-9) for d in distances]
    if band_mode == "quantile" and len(distances) >= n_bands:
        quantiles = np.linspace(0.0, 1.0, n_bands + 1)
        edges = [float(np.quantile(distances, q)) for q in quantiles]
        # 分位数可能重合（失败挤在同一个距离上）；重合的带采不到合法点，
        # 会被 sampler 记成 fallback。这里把重合边向外推开一点，保证带宽非零。
        for i in range(1, len(edges)):
            if edges[i] <= edges[i - 1]:
                edges[i] = edges[i - 1] + 1e-3
        edges[0] = min(edges[0], lo)
        edges[-1] = max(edges[-1], hi)
    else:
        edges = [lo + (hi - lo) * i / n_bands for i in range(n_bands + 1)]
    bands = [(edges[i], edges[i + 1]) for i in range(n_bands)]

    hist = [0] * n_bands
    for d in distances:
        for idx, (b_lo, b_hi) in enumerate(bands):
            if b_lo <= d < b_hi or (idx == n_bands - 1 and d >= b_hi):
                hist[idx] += 1
                break

    total = sum(hist) or 1
    if sum(hist) == 0:
        # 一个失败都没落进带里（要么全成功，要么 labelcond 目标全被钳到同一带外）。
        # 此时「针对性」没有依据，退化成均匀 —— 绝不能返回全零权重。
        weights = [1.0] * n_bands
    else:
        weights = [floor + (count / total) for count in hist]
    reason = {
        "n_failures": len(failures),
        "failure_dist_hist": dict(zip([f"{a:.3f}-{b:.3f}" for a, b in bands], hist)),
        "hist_variable": {"labelcond": "label_target_dist",
                          "frontier": "min_dist"}.get(band_mode, "init_dist"),
        "fell_back_to_uniform": sum(hist) == 0,
        "policy": "weight = floor + 失败占比；floor 防止只在窄带训练导致旧能力退化",
        "band_mode": band_mode,
        "floor": round(float(floor), 4),
    }
    return SamplingPlan(bands=bands, weights=weights, reason=reason).normalized()


# labelcond 分带：每类失败「应该在哪个距离练」。
#   "min_dist"     用该局实际卡住的半径（精度失败要推边界，不是重做整局）
#   ("factor", k)  用初始距离乘 k（发散/超时失败先拉近了练收敛）
# 这张表是**设计假设**，不是真理：探针（scripts/probe_intervention_design.py）
# 负责量它到底把干预推离均匀多远，A/B 负责量它到底学不学得更快。
LABEL_TARGET_DISTANCE: dict[str, Any] = {
    "no_precision": "min_dist",
    "diverged": ("factor", 0.6),
    "never_moved": ("factor", 0.5),
    "timeout_far": ("factor", 0.8),
    "timeout_mid": ("factor", 1.0),
}


def target_distance(record: EpisodeRecord) -> float:
    spec = LABEL_TARGET_DISTANCE.get(record.label or "", ("factor", 1.0))
    if spec == "min_dist":
        return float(record.min_dist)
    _kind, factor = spec
    return float(record.init_dist) * float(factor)
