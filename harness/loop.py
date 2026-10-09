"""自学习闭环：把「跑策略 → 诊断 → 训练 → 独立评测 → 发布」串成一个可预算控制的循环。

对应最初计划里的第四步：

    运行当前策略
        ↓
    收集成功与失败轨迹        harness/tree.py（真 env + 真技能，正反向交替）
        ↓
    判断是否需要训练          harness/diagnose.py（失败标签 + 采样计划）
        ↓
    调用预先写好的训练程序     harness/trainer.py（固定超参，harness 不改它）
        ↓
    独立评测候选策略          registry/publish.py::score_skill（新 seed + 严酷探针）
        ↓
    通过则发布，否则保留原版本  registry/publish.py::decide + publish

两个必须分开的成功率（冒烟测出来的教训）
    primary_success_rate  只统计**主策略**自己跑出来的局 -> 这是训练信号
    task_success_rate     含「降级到恢复技能救场」之后本轮最终完成的比例 -> 这是系统可用性
行为树里恢复技能是个几乎不会失败的比例控制器，如果不把两者分开，采集成功率会被
救场记录抬到 0.5 以上，诊断层就以为策略已经很好了 —— 于是不再触发训练。

部署策略 `deploy`：
    latest     每轮把最新训练出来的权重投入下一轮采集（在线 RL 的做法）。
               诊断始终针对「当前真正在跑的策略」，学习不会停滞；代价是可能
               短暂部署一个比上一版更差的权重。
    published  只部署通过门禁的版本（生产环境的做法）。安全，但如果一直没有版本
               过线，采集就永远由起点策略产生，诊断也就永远停留在起点的失败分布上。
默认 latest：本阶段的目的是观察学习速度，不是保生产。

这个闭环存在的意义，是为了能回答一个**可验证的小研究问题**：

    在相同交互预算下，加入失败诊断 + 针对性采样的 harness，
    是否比固定均匀采样训练学得更快？

`mode` 是唯一的实验变量：
    uniform    每轮都用环境默认的均匀采样训练（对照组，等价于「不用 harness 直接训」）
    diagnosed  每轮先诊断失败分布，再把训练题目往失败集中的距离带倾斜（实验组）

两组的预算、seed、超参、评测口径完全相同，所以差别只能来自采样分布。
预算按**环境交互步数**记账（采集 + 训练都算），这是唯一公平的度量 ——
按「轮数」或「墙钟时间」记账都会被本机的 CPU 争抢污染。

三条纪律（违反任何一条，结论就不可信）：
  1. 评测永远用 `registry.INDEP_EVAL_SEED` 和环境默认采样，绝不用训练时的采样分布；
  2. 门禁不过就**不发布**，并且下一轮从现任版本继续训，被否的候选直接丢弃；
  3. 每一轮都往 `journal.jsonl` 追加一行完整账目，事后可以独立重算（RoboRSI 的
     append-only journal + eval-audit 就是这个思路，见 `docs/roborsi-callchain.md`）。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np

from harness.diagnose import summarize
from harness.tree import FORWARD, HarnessContext, run_rounds
from registry import publish as registry
from skills.base import Skill, SkillMeta, compute_config_hash, ensure_dir, run_tag, timestamp, write_json

MODES = ("uniform", "diagnosed")


def frozen_stop_decision(incumbent_metrics: dict | None, collect_success_rate: float,
                         target_success: float) -> dict:
    """提前停止判据：**只认已发布版本的冻结评测**，采集口径只记账、不作数。

    为什么要抽成函数：这条判据必须能被单独打（自检第 13 项），而它的错误形态
    恰好是「日志上完全正常」的那种 —— run7 s0 用 8 局采集成功率（1.000）判停，
    而报告/门禁用的是 50 局冻结评测（0.860），于是 22496/40000 步就停了，
    曲线还在 0.08→0.54→0.86 的陡升段，预登记的「≥0.9」既没证实也没证伪（§7 第 14 条）。
    两个口径的差不是小数点问题：8 局的 1.000 其 Wilson 95% CI 是 [0.63, 1.00]。

    `target_success > 1.0` 是「关掉提前停止跑满预算」的惯用法（run7 决定性臂用 1.01），
    这里天然支持：冻结评测最高就是 1.0，永远够不到 1.01。
    """
    frozen = float((incumbent_metrics or {}).get("success_rate") or 0.0)
    stop = frozen >= target_success
    return {
        "stop": stop,
        "converged_on": "frozen_eval" if stop else None,
        "frozen_success_rate": frozen,
        "collect_success_rate": float(collect_success_rate),
        "reason": (f"已发布版本的冻结评测 {frozen:.3f} >= 目标 {target_success}"
                   f"（同口径判据；本轮采集口径 {float(collect_success_rate):.3f}）" if stop else
                   f"冻结评测 {frozen:.3f} < 目标 {target_success} ⇒ 继续"
                   f"（采集口径 {float(collect_success_rate):.3f} 不作数，见 §7 第 14 条）"),
    }


@dataclasses.dataclass
class LoopConfig:
    mode: str = "diagnosed"
    budget_steps: int = 12000        # 总交互预算（采集 + 训练），两组必须一样
    episodes_per_round: int = 20     # 每轮用行为树采多少局来做诊断
    steps_per_round: int = 4000      # 每轮训练的交互步数
    target_success: float = 0.95     # 达到就提前停（已经会了，别再烧预算）
    eval_episodes: int = 50
    eval_seed: int = registry.INDEP_EVAL_SEED
    seed: int = 0
    skill_name: str = "reach_harness"
    init: str = "random"             # random | untrained | <ckpt 路径>
    max_rounds: int = 8
    min_gain: float = 0.02
    regression_tol: float = 0.0
    min_success: float = 0.0
    mix_uniform: float = 0.25        # 实验组里保留多少比例的均匀采样（防遗忘）
    band_mode: str = "range"         # 诊断分带方式：range（原行为）| quantile（见 diagnose.py）
    plan_floor: float = 0.15         # 归一化前的保底权重；quantile 分带下建议调小（0.05）
    plan_bands: int = 4              # 距离带条数
    deploy: str = "latest"           # latest | published，见模块 docstring
    # 发布判定的统计口径。默认 legacy（二态）以保持与历史 run 的可比性；
    # paired_v1 = 三态（publish / reject / inconclusive），见 registry/publish.py::decide_paired。
    # 什么时候必须打开：评测局数的噪声地板 MDE 大于 min_gain 时（接触任务 50 局 MDE≈0.26，
    # 而 min_gain=0.02），legacy 会用噪声发布、也会用噪声判掉点（§12.11-G/L 实证）。
    gate_stats: str = registry.GATE_STATS_LEGACY
    # 门禁判定用哪个成功口径（K11 硬前置之二，§12.11-N）。
    # 默认 success_rate = reach 的历史行为，逐字不变；接触任务必须显式换成
    # success_rate_grasp_verified —— 否则"弹一下"能过门禁（Lift 最弱那档实测
    # flick_frac=0.500，一半的"成功"没有抓取真值）。
    success_metric: str = registry.SUCCESS_RATE
    # True 时：bundle 里没有 grasp-verified 口径就**硬拒**（不许静默按 0.0 判）。
    require_grasp_verified: bool = False
    env_kwargs: dict = dataclasses.field(default_factory=dict)
    config_path: str = str(Path(__file__).resolve().parents[1] / "configs" / "reach_sac.yaml")
    out_dir: str = ""
    registry_root: str = str(registry.DEFAULT_REGISTRY)
    device: str = "cpu"
    threads: int = 1

    def validate(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode 只能是 {MODES}，收到 {self.mode!r}")
        if self.budget_steps < self.steps_per_round:
            raise ValueError("budget_steps 小于 steps_per_round，一轮都训不完")
        if self.deploy not in ("latest", "published"):
            raise ValueError(f"deploy 只能是 latest/published，收到 {self.deploy!r}")
        if self.success_metric not in registry.SUCCESS_KEYS:
            raise ValueError(f"success_metric 只能是 {registry.SUCCESS_KEYS}，"
                             f"收到 {self.success_metric!r}")
        if self.band_mode not in ("range", "quantile", "labelcond", "frontier"):
            raise ValueError(f"band_mode 只能是 range/quantile/labelcond/frontier，收到 {self.band_mode!r}")
        if self.gate_stats not in registry.GATE_STATS_CHOICES:
            raise ValueError(f"gate_stats 只能是 {registry.GATE_STATS_CHOICES}，收到 {self.gate_stats!r}")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def build_initial_skill(cfg: LoopConfig, env_kwargs: dict) -> tuple[Skill | None, str]:
    """造出闭环的起点技能。从随机起点开始，「学习带来的提升」才有对照。"""
    from skills.reach_skills import ProportionalReachSkill, RandomSkill, ReachPolicySkill

    if cfg.init == "random":
        return RandomSkill(seed=cfg.seed), "random"
    if cfg.init == "untrained":
        from stable_baselines3 import SAC

        from envs.reach_env import make_reach_env

        tmp = Path(cfg.out_dir) / "untrained_init"
        ensure_dir(tmp)
        model = SAC("MlpPolicy", make_reach_env(**env_kwargs), seed=cfg.seed,
                    device=cfg.device, verbose=0, policy_kwargs={"net_arch": [64, 64]})
        ckpt = tmp / "untrained.zip"
        model.save(str(ckpt.with_suffix("")))
        return ReachPolicySkill(ckpt, name=f"{cfg.skill_name}_untrained"), str(ckpt)
    if Path(cfg.init).exists():
        return ReachPolicySkill(cfg.init, name=cfg.skill_name), cfg.init
    raise FileNotFoundError(f"--init 既不是 random/untrained，也不是存在的 ckpt: {cfg.init}")


class HarnessLoop:
    def __init__(self, cfg: LoopConfig, verbose: bool = True) -> None:
        cfg.validate()
        self.cfg = cfg
        self.verbose = verbose
        trainer_cfg = registry_json_load(cfg.config_path)
        # 环境实现由 config 的顶层 env_factory 决定，必须在建环境之前安装，
        # 否则独立评测会用默认 Reach 给扰动策略打分，分数没有意义。
        from harness.env_factory import from_config

        self.env_factory = from_config(trainer_cfg)
        env_kwargs = dict(cfg.env_kwargs or trainer_cfg["env"])
        self.env_kwargs = env_kwargs
        # 环境指纹：环境实现 + 全部环境参数。registry 用它拦住「不同环境的分数混进同一条版本线」。
        self.env_hash = compute_config_hash({"env_factory": self.env_factory, **env_kwargs})
        self.goal_radius = float(env_kwargs.get("goal_radius", 0.03))
        self.half_space = float(env_kwargs.get("half_space", 0.15))

        self.out_dir = Path(cfg.out_dir) if cfg.out_dir else (
            Path(__file__).resolve().parents[1] / "runs" / f"{run_tag()}_harness_{cfg.mode}")
        ensure_dir(self.out_dir)
        self.journal = self.out_dir / "journal.jsonl"

        from envs.reach_env import make_reach_env

        self.env = make_reach_env(**env_kwargs)
        self.skill, self.skill_source = build_initial_skill(cfg, env_kwargs)
        # learner_ckpt = 最新训练出来的权重（用于续训，绝不因为门禁否决就丢弃：
        # 丢掉就等于把这一轮的梯度白烧了）。deployed = 下一轮采集时真正在跑的技能。
        self.learner_ckpt = self.skill_source if Path(str(self.skill_source)).exists() else ""
        self.published_ckpt = ""
        self.incumbent_metrics: dict | None = None
        self.incumbent_scores: dict | None = None      # 现任的逐局评测记录（配对检验用）
        self.history: list[dict] = []
        self.learner_metrics: dict = {}
        self.consumed = 0

    # ------------------------------------------------------------------
    def log(self, text: str) -> None:
        if self.verbose:
            print(text, flush=True)

    def append_journal(self, entry: dict) -> None:
        with open(self.journal, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    # ------------------------------------------------------------------
    def collect(self, episodes: int) -> tuple[dict, dict]:
        """用行为树采一批轨迹（正反向交替 + 降级 + 接管记账），再做诊断汇总。

        诊断只看 `role == "primary"` 的记录：救场记录衡量的是恢复技能，不是主策略，
        混进来会让「策略有多差」这个信号失真（见模块 docstring）。
        """
        from skills.reach_skills import ProportionalReachSkill

        ctx = HarnessContext(
            env=self.env,
            primary_skill=self.skill,
            # 恢复技能固定用不依赖训练的规划式技能：它的作用是「保住这一轮」，
            # 不该跟着学习进度变，否则恢复能力本身就成了实验变量。
            recovery_skill=ProportionalReachSkill(half_space=self.half_space,
                                                  action_scale=float(self.env_kwargs.get("action_scale", 0.05))),
            goal_radius=self.goal_radius,
            half_space=self.half_space,
            min_goal_dist=float(self.env_kwargs.get("min_goal_dist", 0.08)),
            seed=self.cfg.seed,
            verbose=False,
        )
        _tree, outcomes = run_rounds(ctx, episodes)
        primary = [r for r in ctx.records if r.role == "primary"]
        recovery = [r for r in ctx.records if r.role == "recovery"]

        summary = summarize(primary, self.goal_radius, self.half_space,
                            band_mode=self.cfg.band_mode, floor=self.cfg.plan_floor,
                            n_bands=self.cfg.plan_bands)
        summary["primary_success_rate"] = summary["success_rate"]
        task_success = sum(1 for o in outcomes if o.endswith("_success") or o == "recovered")
        summary["task_success_rate"] = round(task_success / max(1, len(outcomes)), 4)
        summary["n_recovery_attempts"] = len(recovery)
        summary["recovery_success_rate"] = round(
            sum(r.success for r in recovery) / len(recovery), 4) if recovery else None
        summary["n_records_total"] = len(ctx.records)

        stats = {
            "rounds": len(outcomes),
            "outcomes": dict(ctx.outcomes),
            "round_outcome_seq": outcomes,
            "env_steps": ctx.env_steps,
            "primary_episodes": len(primary),
            "goal_dist_by_direction": {
                direction: {"n": len(sampler.history),
                            "mean": round(float(np.mean([np.linalg.norm(g) for g in sampler.history])), 4)
                            if sampler.history else None}
                for direction, sampler in ctx.regions.items()
            },
        }
        return summary, stats

    def resolution_audit(self, cand_metrics: dict, cand_scores: dict) -> dict:
        """这次发布判定**有没有分辨力**：把门禁阈值和评测噪声地板放在一起算一遍。

        只记账、不改判定（改判定会让历史 run 的数字不可比），但账必须写进 journal：
        run7 决定性臂实测，同一条臂上 `min_gain=0.02` 让 round 6 用 +0.02
        （未配对 z=1.01, p=0.31）发布，`regression_tol=0` 让 rounds 7/8 用
        0.98 vs 1.00（**50 局里只翻了 1 局**）判「旧任务掉点」拒绝 —— 两个方向都在量噪声，
        而日志上毫无异常。MDE 口径见 `harness/sampling_design.py`（§12.11-G）。

        配对（McNemar）参考是**零额外成本**的：现任与候选的独立评测用的是同一批 seed
        （`INDEP_EVAL_SEED`），`score_skill` 把逐局结果精简成 `episode_outcomes`
        （seed + success）留在 scores 里，所以直接配对即可。**这条以前是断的**：
        `score_skill` 曾把 `episodes` 整个剥掉，配对分支静默退化成「无法配对」，
        而它当时只是 advisory 字段，日志上看不出来（§7 第 26 条）。
        它给出旧二态门禁缺的第三态 `inconclusive`（差异不显著 ⇒ 既不该发布也不该判掉点）。
        """
        from harness.sampling_design import (min_detectable_effect, mde_worst_case,
                                             paired_gate, required_episodes)
        n = int(self.cfg.eval_episodes)
        # 口径必须与门禁判定的那一个一致（cfg.success_metric）：审计算的是"这次判定
        # 有没有分辨力"，拿另一个口径的 p̄ 去算 MDE 会给出错的噪声地板。
        key = self.cfg.success_metric
        inc_sr = float((self.incumbent_metrics or {}).get(key) or 0.0)
        cand_sr = float(cand_metrics.get(key) or 0.0)
        p_base = (inc_sr + cand_sr) / 2.0
        mde = min_detectable_effect(n, p_base)
        audit: dict = {
            "eval_episodes": n, "p_base": round(p_base, 4), "success_key": key,
            "mde": round(mde, 4), "mde_worst_case": round(mde_worst_case(n), 4),
            "min_gain": self.cfg.min_gain, "regression_tol": self.cfg.regression_tol,
            "min_gain_resolvable": bool(self.cfg.min_gain >= mde),
            "regression_tol_resolvable": bool(self.cfg.regression_tol >= mde),
            "episodes_needed_for_min_gain": required_episodes(
                self.cfg.min_gain, p_base)["unpaired_per_arm"],
        }
        bits = []
        if not audit["min_gain_resolvable"]:
            bits.append(f"min_gain={self.cfg.min_gain:g} < 噪声地板 MDE={mde:.3f} ⇒ 会用噪声**发布**")
        if not audit["regression_tol_resolvable"]:
            bits.append(f"regression_tol={self.cfg.regression_tol:g} < MDE={mde:.3f} ⇒ 会用噪声**拒绝**")
        audit["warning"] = ("；".join(bits) +
                            f"（评测 {n} 局、工作点 p={p_base:.3f}；要判 min_gain 需 "
                            f"{audit['episodes_needed_for_min_gain']} 局/臂，或改配对检验）"
                            ) if bits else ""

        def outcomes(scores: dict | None) -> list[dict]:
            std = (scores or {}).get("standard") or {}
            # `score_skill` 存的是精简版 `episode_outcomes`；直接把 `evaluate_reach`
            # 的结果传进来的地方（老产物、自检用例）是完整 `episodes`，两种都认。
            return std.get("episode_outcomes") or std.get("episodes") or []

        # 配对读的 `success` 就是**被判口径**的逐局真值：reach 侧由 `score_skill` 给，
        # 接触侧由 `registry.contact_bundle_from_probe(success_key=...)` 给 —— 后者会按
        # success_key 把 `success_grasp` 写进 `success` 字段，所以这里不需要再分叉。
        inc_rows = outcomes(self.incumbent_scores)
        new_rows = outcomes(cand_scores)
        if inc_rows and len(inc_rows) == len(new_rows):
            by_seed = {r["seed"]: bool(r["success"]) for r in inc_rows}
            only_new = sum(1 for r in new_rows
                           if bool(r["success"]) and not by_seed.get(r["seed"], False))
            only_inc = sum(1 for r in new_rows
                           if not bool(r["success"]) and by_seed.get(r["seed"], False))
            gate = paired_gate(len(new_rows), only_new, only_inc)
            audit["paired"] = {"n_pairs": len(new_rows), "only_new": only_new,
                               "only_inc": only_inc, **gate}
        else:
            audit["paired"] = {
                "reason": f"无法配对：现任 {len(inc_rows)} 局 vs 候选 {len(new_rows)} 局"
                          "（缺逐局记录或局数不一致）",
                "hint": "检查 `score_skill` 有没有留 `standard.episode_outcomes`；配对断掉时"
                        "三态门禁会退回未配对的 MDE 口径（仍能出 inconclusive，但分辨力更差）",
            }
        return audit

    def evaluate(self, skill: Any) -> dict:
        """独立评测：新 seed + 严酷探针。训练时看到的题一律不参与打分。"""
        return registry.score_skill(skill, self.env_kwargs,
                                    n_episodes=self.cfg.eval_episodes, seed=self.cfg.eval_seed)

    def train(self, plan: dict | None, round_idx: int) -> dict:
        from harness.sampling import sampler_from_plan
        from harness.trainer import train_candidate

        seed = self.cfg.seed * 100 + round_idx
        sampler = sampler_from_plan(
            plan if self.cfg.mode == "diagnosed" else None,
            self.env_kwargs, seed=seed, mix_uniform=self.cfg.mix_uniform)
        out = Path(self.out_dir) / f"round{round_idx:02d}_train"
        return train_candidate(
            steps=self.cfg.steps_per_round,
            seed=seed,
            sampler=sampler,
            env_kwargs=self.env_kwargs,
            out_dir=out,
            config_path=self.cfg.config_path,
            device=self.cfg.device,
            threads=self.cfg.threads,
            resume_from=self.learner_ckpt,
        )

    # ------------------------------------------------------------------
    def run(self) -> dict:
        cfg = self.cfg
        self.log("=" * 76)
        self.log(f"自学习闭环 · mode={cfg.mode} · deploy={cfg.deploy} · 预算={cfg.budget_steps} 步 · "
                 f"每轮 {cfg.episodes_per_round} 局采集 + {cfg.steps_per_round} 步训练")
        self.log(f"起点技能: {self.skill.meta.short() if self.skill else 'None'} · 输出: {self.out_dir}")
        self.log("=" * 76)

        base_scores = self.evaluate(self.skill)
        self.incumbent_metrics = registry.summarize_scores(base_scores)
        self.incumbent_scores = base_scores
        self.learner_metrics = dict(self.incumbent_metrics)
        self.log(f"[round 0] 起点独立评测: 标准 {self.incumbent_metrics['success_rate']:.3f} "
                 f"/ 严酷 {self.incumbent_metrics['harsh_success_rate']:.3f}")
        curve = [{"round": 0, "consumed_steps": 0, "phase": "init", "published": False,
                  **self.incumbent_metrics}]
        self.history.append({"round": 0, "phase": "init", "consumed_steps": 0,
                             "metrics": self.incumbent_metrics})

        stop_reason = "达到 max_rounds"
        last_collect_sr: float | None = None
        last_audit: dict | None = None
        for round_idx in range(1, cfg.max_rounds + 1):
            # 预算检查放在采集**之前**：否则最后一轮会白采一批轨迹才发现训不起了。
            if self.consumed + cfg.steps_per_round > cfg.budget_steps:
                stop_reason = (f"剩余预算 {cfg.budget_steps - self.consumed} "
                               f"< 单轮训练 {cfg.steps_per_round}，停止")
                break

            self.log("-" * 76)
            summary, collect_stats = self.collect(cfg.episodes_per_round)
            self.consumed += collect_stats["env_steps"]
            self.log(f"[round {round_idx}] 采集 {collect_stats['rounds']} 轮 · "
                     f"主策略成功率 {summary['primary_success_rate']:.3f} · "
                     f"系统级(含救场) {summary['task_success_rate']:.3f} · "
                     f"消耗 {collect_stats['env_steps']} 步 (累计 {self.consumed}/{cfg.budget_steps})")
            self.log(f"           失败标签: {summary['labels']}")
            self.log(f"           本轮结局: {collect_stats['outcomes']}")

            # 提前停止判据必须和「用什么数字下结论」**同口径**（§7 第 14 条 / §12.11-K1）。
            # 旧判据用 episodes_per_round 局的**采集**成功率（还叠了采样器分布），而报告和
            # 门禁用的是 eval_episodes 局**冻结独立评测**（seed 999）。run7 s0 上两者差 0.14
            # （采集 1.000 / 冻结 0.860），结果 22496/40000 步就停了，曲线还在
            # 0.08→0.54→0.86 的陡升段，预登记的「≥0.9」既没证实也没证伪。
            # 8 局的 1.000 本身 Wilson 95% CI 就有 [0.63, 1.00] 那么宽 —— 拿它当停止条件
            # 等于让噪声决定预算花到哪里为止。
            last_collect_sr = float(summary["primary_success_rate"])
            decision = frozen_stop_decision(self.incumbent_metrics, last_collect_sr,
                                            cfg.target_success)
            if decision["stop"]:
                stop_reason = decision["reason"]
                self.append_journal({"round": round_idx, "phase": "collect", "summary": summary,
                                     "collect": collect_stats, "note": stop_reason,
                                     **decision})
                break

            plan = summary.get("sampling_plan") if cfg.mode == "diagnosed" else None
            train_info = self.train(plan, round_idx)
            self.consumed += train_info["steps"]
            # 续训永远接最新权重，跟「有没有过门禁」无关：门禁管的是发布，不是学习。
            self.learner_ckpt = train_info["ckpt"]

            from skills.reach_skills import ReachPolicySkill

            candidate = ReachPolicySkill(
                train_info["ckpt"], name=cfg.skill_name,
                trained_on=f"round{round_idx}|mode={cfg.mode}|steps={train_info['steps']}",
                env_hash=self.env_hash)
            cand_scores = self.evaluate(candidate)
            cand_metrics = registry.summarize_scores(cand_scores)
            self.learner_metrics = cand_metrics

            # 门禁比的是「能不能替换掉已发布的现任版本」，所以对照对象是 published 指标。
            # 版本线一致性：registry 里现任那个版本是不是在同一个环境下评出来的？
            registry_env_hash = registry.current_env_hash(cfg.skill_name, cfg.registry_root)
            # 分辨率审计先算：三态门禁要吃它里面的逐题配对结果。配对是**零额外成本**的
            # （现任与候选的独立评测用同一批 seed，`score_skill` 保留了逐局记录）。
            last_audit = self.resolution_audit(cand_metrics, cand_scores)
            paired = last_audit.get("paired") or {}
            gate: dict | None = None
            if cfg.gate_stats == registry.GATE_STATS_PAIRED:
                gate = registry.decide_paired(
                    cand_metrics, self.incumbent_metrics, paired=paired,
                    eval_episodes=cfg.eval_episodes,
                    min_gain=cfg.min_gain, regression_tol=cfg.regression_tol,
                    min_success=cfg.min_success,
                    success_key=cfg.success_metric,
                    require_grasp_verified=cfg.require_grasp_verified,
                    candidate_env_hash=self.env_hash, incumbent_env_hash=registry_env_hash)
                ok, reasons = gate["ok"], gate["reasons"]
            else:
                ok, reasons = registry.decide(
                    cand_metrics, self.incumbent_metrics,
                    min_gain=cfg.min_gain, regression_tol=cfg.regression_tol,
                    min_success=cfg.min_success,
                    candidate_env_hash=self.env_hash, incumbent_env_hash=registry_env_hash)
            gate_record = {"ok": bool(ok), "reasons": reasons, "gate_stats": cfg.gate_stats,
                           "min_gain": cfg.min_gain, "regression_tol": cfg.regression_tol,
                           "min_success": cfg.min_success,
                           "success_metric": cfg.success_metric,
                           "require_grasp_verified": bool(cfg.require_grasp_verified)}
            if gate:
                gate_record.update({
                    "decision": gate["decision"], "reason_code": gate["reason_code"],
                    "direction": gate["direction"], "significant": gate["significant"],
                    "delta": gate["delta"], "mde": gate["mde"],
                    "paired": gate["paired"], "fallback": gate["fallback"],
                    "episodes_needed_for_min_gain": gate.get("episodes_needed_for_min_gain"),
                })

            self.log(f"[round {round_idx}] 训练 {train_info['steps']} 步 "
                     f"({train_info['train_seconds']}s, {train_info['steps_per_sec']} 步/s) · "
                     f"采样器 {train_info['sampler']['kind']} · "
                     f"续训自 {Path(train_info['resumed_from']).parent.name if train_info['resumed_from'] else '从零'}")
            self.log(f"           候选独立评测: 标准 {cand_metrics['success_rate']:.3f} "
                     f"/ 严酷 {cand_metrics['harsh_success_rate']:.3f}")
            if cand_metrics.get("flick_frac") is not None:
                # 接触任务：两个口径必须一起露出来。它们不一致时（flick_frac>0），
                # 只报未校验口径就是把"弹一下"当成学会了（§12.11-N）。
                self.log(f"           口径核对[判定用 {cfg.success_metric}]: 未校验 "
                         f"{cand_metrics.get('success_rate')} · grasp-verified "
                         f"{cand_metrics.get('success_rate_grasp_verified')} · "
                         f"flick_frac {cand_metrics.get('flick_frac')}")
            verdict_txt = (f"{gate['decision']}（{gate['reason_code']}，方向 {gate['direction']}）"
                           if gate else ("通过" if ok else "不通过"))
            self.log(f"           发布门禁[{cfg.gate_stats}]: {verdict_txt}（现任 "
                     f"{float((self.incumbent_metrics or {}).get(cfg.success_metric) or 0.0):.3f}"
                     f"[{cfg.success_metric}] · env_hash {self.env_hash}）")
            for reason in reasons:
                self.log(f"             · {reason}")
            if last_audit.get("warning"):
                self.log(f"           [分辨率审计] {last_audit['warning']}")
            if paired.get("decision") and not gate:
                # legacy 口径下配对仍然只作参考（不改判定），但必须打出来：
                # 它与二态结论矛盾时，矛盾本身就是"这一轮在量噪声"的证据。
                self.log(f"           [配对参考] {paired['decision']} · {paired['reason']}")

            published_to = ""
            if ok:
                meta = SkillMeta(
                    name=cfg.skill_name, version="", kind="rl_policy",
                    source=train_info["ckpt"],
                    trained_on=candidate.meta.trained_on,
                    config_hash=compute_config_hash(train_info["hyper"]),
                    env_hash=candidate.meta.env_hash,
                    notes=f"harness loop round {round_idx}, mode={cfg.mode}",
                )
                target = registry.publish(
                    skill_name=cfg.skill_name, ckpt=train_info["ckpt"], meta=meta,
                    scores=cand_scores, registry_root=cfg.registry_root,
                    gate=gate_record,
                    extra={"round": round_idx, "mode": cfg.mode,
                           "band_mode": cfg.band_mode, "plan_floor": cfg.plan_floor,
                           "plan_bands": cfg.plan_bands,
                           "consumed_steps": self.consumed,
                           "collect_summary": summary, "train": train_info})
                published_to = str(target)
                self.published_ckpt = str(Path(target) / "model.zip")
                self.incumbent_metrics = cand_metrics
                self.incumbent_scores = cand_scores
                self.log(f"           已发布: {target}")

            # 部署决策与发布决策分开（见模块 docstring）
            if cfg.deploy == "latest" or ok:
                self.skill = candidate

            curve.append({"round": round_idx, "consumed_steps": self.consumed,
                          "phase": "train", "published": bool(ok),
                          "gate_decision": gate_record.get("decision")
                          or ("publish" if ok else "no_publish"),
                          "gate_reason_code": gate_record.get("reason_code"),
                          "gate_direction": gate_record.get("direction"), **cand_metrics})
            self.history.append({
                "round": round_idx, "phase": "train", "consumed_steps": self.consumed,
                "collect": summary, "collect_stats": collect_stats, "train": train_info,
                "candidate_metrics": cand_metrics, "gate": gate_record,
                "published_to": published_to,
                "deployed": self.skill.meta.short() if self.skill else None,
            })
            self.append_journal({
                "round": round_idx, "phase": "train", "timestamp": timestamp(),
                "mode": cfg.mode, "consumed_steps": self.consumed,
                "collect_summary": summary, "collect_stats": collect_stats,
                "train": train_info, "candidate_scores": cand_scores,
                "candidate_metrics": cand_metrics, "gate": gate_record,
                "incumbent_metrics": self.incumbent_metrics, "published_to": published_to,
                "resolution_audit": last_audit,
            })

        result = {
            "timestamp": timestamp(),
            "mode": cfg.mode,
            "deploy": cfg.deploy,
            "env_factory": self.env_factory,
            "config": cfg.to_dict(),
            "env_kwargs": self.env_kwargs,
            "budget_steps": cfg.budget_steps,
            "consumed_steps": self.consumed,
            "stop_reason": stop_reason,
            "gate_stats": cfg.gate_stats,
            # 有多少轮是「测不出来」而不是「判定了」——三态口径下这个数才是分辨率欠账的账本
            "n_inconclusive": sum(1 for c in curve if c.get("gate_decision") == "inconclusive"),
            "stopping_criterion": (f"frozen_eval：已发布版本的 {cfg.eval_episodes} 局独立评测"
                                   f" >= target_success（与报告/门禁同口径；旧版用采集口径，"
                                   f"会把 run 截断在爬升段，见 §7 第 14 条）"),
            "converged": bool(float((self.incumbent_metrics or {}).get("success_rate") or 0.0)
                              >= cfg.target_success),
            "truncated_not_converged": bool(
                float((self.incumbent_metrics or {}).get("success_rate") or 0.0)
                < cfg.target_success),
            "final_frozen_success_rate": float((self.incumbent_metrics or {}).get("success_rate") or 0.0),
            "final_collect_success_rate": last_collect_sr,
            "resolution_audit_last": last_audit,
            "init_skill": self.skill_source,
            "final_deployed_skill": self.skill.meta.short() if self.skill else None,
            # learner = 最新训练出来的权重（学习速度的度量对象）
            # published = 过了门禁、可发布的最好版本（上线的度量对象）
            "learner_metrics": self.learner_metrics,
            "published_metrics": self.incumbent_metrics,
            "learner_ckpt": self.learner_ckpt,
            "published_ckpt": self.published_ckpt,
            "n_published": sum(1 for c in curve if c.get("published")),
            "learning_curve": curve,
            "history": self.history,
            "out_dir": str(self.out_dir),
        }
        write_json(self.out_dir / "loop_result.json", result)
        self.log("-" * 76)
        self.log(f"闭环结束: {stop_reason}")
        self.log(f"  消耗交互步数 {self.consumed}/{cfg.budget_steps}")
        self.log(f"  学习到的最新权重  标准 {self.learner_metrics['success_rate']:.3f} "
                 f"/ 严酷 {self.learner_metrics['harsh_success_rate']:.3f}")
        self.log(f"  可发布的最好版本  标准 {self.incumbent_metrics['success_rate']:.3f} "
                 f"/ 严酷 {self.incumbent_metrics['harsh_success_rate']:.3f} "
                 f"（{result['n_published']} 个版本过线）")
        self.log(f"  结果: {self.out_dir / 'loop_result.json'}")
        self.log(f"  账目: {self.journal}")
        return result


def registry_json_load(path: str | Path) -> dict:
    """读 config yaml（放在这里只是为了解释：闭环不自己定义超参，全部来自 config）。"""
    from harness.trainer import load_train_config

    return load_train_config(path)
