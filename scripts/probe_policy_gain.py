"""把「SAC 在 reach_perturbed 上只有 0.68」分解成可归因的机制量（零训练）。

为什么要这个脚本
    `scripts/probe_fullstate_ceiling.py` 已经证明：6 维观测上**存在**满分的手写
    控制器（朴素 P 控制 g=0.5 -> 标准/严酷都 1.000，4.88 步）。也就是说 SAC 的
    0.68 不是「信息不够」，而是「没学到那个解」。但「没学到」有三种完全不同的
    病因，对应的下一步也完全不同：

      病因 1  增益太大：延迟 1 步时闭环增益 g*gain_noise 会 >1 -> 过冲振荡。
              对策 = 调 SAC 的探索/熵系数，或改奖励，让策略学会保守。
      病因 2  增益对了但方向不准：动作不指向目标（学了奇怪的补偿）。
              对策 = 检查观测/动作语义，可能是接口 bug 而不是学习问题。
      病因 3  近目标处不收口：远段没问题，最后 2cm 抖出去。
              对策 = 奖励塑形 / 成功圈附近的采样密度。

    本脚本把策略在真实环境里跑一遍，逐步记录
        r        = 到目标的距离
        g_eff    = 等效比例增益 = (a·û) / (r/action_scale)   （û 指向目标）
        cos      = a 与 (goal-ee) 的夹角余弦（方向对准度）
        |a|      = 动作模长（区分「饱和」和「保守」）
    然后按距离分箱得到**增益曲线**，并做两件事：
      A. 和手写 g=1.0 / g=0.5 的参考曲线并排比，看差在哪一段距离；
      B. 用测出来的增益曲线造一个「增益回放」手写控制器再评一次分 ——
         若它能复现 SAC 的分数，病因就是**增益曲线本身**（病因 1/3）；
         若它明显更高，说明 SAC 还额外损失在方向/形状上（病因 2）。

用法：
    /root/venvs/rlrobot/bin/python scripts/probe_policy_gain.py \
        --ckpt runs/ab_stage3/run5_labelcond60k/uniform_s1/round08_train/candidate.zip
    可多次 --ckpt 一次比多个检查点。只吃 CPU 几十秒，不训练、不写 registry。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.env_factory import install_env_factory           # noqa: E402
from harness.trainer import load_train_config                 # noqa: E402
from registry.publish import score_skill                      # noqa: E402
from scripts.probe_fullstate_ceiling import (Proportional6D,  # noqa: E402
                                             decode_ee_goal, obs_layout)
from skills.base import Skill, SkillMeta, compute_config_hash  # noqa: E402

R_EDGES = [0.0, 0.02, 0.04, 0.06, 0.08, 0.12, 0.16, 0.25, np.inf]


class GainScheduleSkill(Skill):
    """把测出来的 g_eff(r) 曲线原样回放成手写控制器（方向永远精确对准目标）。

    这是「病因归因」的关键夹具：它保留了 SAC 的**径向增益决策**，但去掉了 SAC 的
    方向误差和一切非径向结构。所以
        score(GainSchedule) ≈ score(SAC)  -> 损失全在增益曲线上
        score(GainSchedule) >> score(SAC) -> SAC 还额外损失在方向/形状上
    """

    def __init__(self, edges: list[float], gains: list[float], half_space: float,
                 action_scale: float, layout: dict, version: str = "v1") -> None:
        self.edges = np.asarray(edges, dtype=np.float64)
        self.gains = np.asarray(gains, dtype=np.float64)
        self.half_space, self.action_scale, self.layout = half_space, action_scale, layout
        self.meta = SkillMeta(
            name="probe_gain_schedule", version=version, kind="planner",
            source="scripts/probe_policy_gain.py::GainScheduleSkill",
            trained_on="无需训练（回放实测增益曲线）",
            config_hash=compute_config_hash({"edges": list(self.edges),
                                             "gains": [round(float(g), 4) for g in self.gains]}),
            notes="回放 SAC 的等效增益曲线，方向精确对准",
        )

    def _gain(self, r: float) -> float:
        idx = int(np.searchsorted(self.edges, r, side="right") - 1)
        idx = min(max(idx, 0), len(self.gains) - 1)
        return float(self.gains[idx])

    def act(self, obs: np.ndarray) -> np.ndarray:
        ee, goal = decode_ee_goal(obs, self.half_space, self.layout)
        delta = goal - ee
        r = float(np.linalg.norm(delta))
        if r < 1e-9:
            return np.zeros(3, dtype=np.float32)
        return np.clip(self._gain(r) * delta / self.action_scale, -1.0, 1.0).astype(np.float32)


def _rollout_stats(env, act, episodes: int, seed: int, action_scale: float,
                   half_space: float, lay: dict) -> dict:
    """跑一批局，收集 (r, g_eff, cos, |a|) 逐步样本。"""
    rs, gs, cs, ms, succ_steps = [], [], [], [], []
    n_succ = 0
    for ep in range(episodes):
        obs, _ = env.reset(seed=seed + ep)
        done = False
        steps = 0
        ok = False
        while not done:
            ee, goal = decode_ee_goal(obs, half_space, lay)
            delta = goal - ee
            r = float(np.linalg.norm(delta))
            a = np.asarray(act(obs), dtype=np.float64).reshape(3)
            if r > 1e-9:
                u = delta / r
                rs.append(r)
                gs.append(float(a @ u) / (r / action_scale))
                na = float(np.linalg.norm(a))
                cs.append(float(a @ u) / na if na > 1e-9 else 0.0)
                ms.append(na)
            obs, _r, term, trunc, info = env.step(a.astype(np.float32))
            steps += 1
            ok = bool(info.get("success", False))
            done = term or trunc
        n_succ += int(ok)
        succ_steps.append(steps)
    return {
        "success_rate": round(n_succ / max(1, episodes), 4),
        "mean_steps": round(float(np.mean(succ_steps)), 2),
        "r": np.asarray(rs), "g_eff": np.asarray(gs),
        "cos": np.asarray(cs), "mag": np.asarray(ms),
    }


def _bins(stats: dict) -> list[dict]:
    r = stats["r"]
    rows = []
    for lo, hi in zip(R_EDGES[:-1], R_EDGES[1:]):
        m = (r >= lo) & (r < hi)
        n = int(m.sum())
        rows.append({
            "r_range": [round(float(lo), 3), (None if np.isinf(hi) else round(float(hi), 3))],
            "n_steps": n,
            "g_eff_mean": round(float(stats["g_eff"][m].mean()), 4) if n else None,
            "g_eff_std": round(float(stats["g_eff"][m].std()), 4) if n else None,
            "cos_mean": round(float(stats["cos"][m].mean()), 4) if n else None,
            "abs_a_mean": round(float(stats["mag"][m].mean()), 4) if n else None,
        })
    return rows


def _bin_centers_gains(rows: list[dict]) -> tuple[list[float], list[float]]:
    edges, gains = [], []
    for row in rows:
        lo, hi = row["r_range"]
        edges.append(float(lo))
        gains.append(float(row["g_eff_mean"]) if row["g_eff_mean"] is not None else 0.0)
    edges.append(float(R_EDGES[-2]))
    return edges, gains


def _print_rows(label: str, rows: list[dict]) -> None:
    print(f"  {label}")
    print("    距离区间(m)      步数   g_eff均值  g_eff方差  cos对准  |a|均值")
    for row in rows:
        lo, hi = row["r_range"]
        rng = f"[{lo:.2f},{hi:.2f})" if hi is not None else f"[{lo:.2f},  inf)"
        if not row["n_steps"]:
            print(f"    {rng:14s} {row['n_steps']:6d}      —        —        —       —")
            continue
        print(f"    {rng:14s} {row['n_steps']:6d}   {row['g_eff_mean']:+7.3f}  "
              f"{row['g_eff_std']:8.3f}  {row['cos_mean']:+6.3f}  {row['abs_a_mean']:6.3f}")


def analyse_ckpt(ckpt: Path, env_kwargs: dict, lay: dict, episodes: int, seed: int,
                 do_score: bool) -> dict:
    from envs.reach_perturbed import PerturbedReachEnv
    from skills.reach_skills import ReachPolicySkill

    half = float(env_kwargs.get("half_space", 0.15))
    scale = float(env_kwargs.get("action_scale", 0.05))
    skill = ReachPolicySkill(ckpt, deterministic=True, name="probe_gain_policy")
    out: dict = {"ckpt": str(ckpt), "algo": skill.algo}

    if do_score:
        scores = score_skill(skill, env_kwargs, n_episodes=episodes, seed=seed, harsh=True)
        out["score"] = {"standard": scores["standard"]["success_rate"],
                        "standard_mean_steps": scores["standard"]["mean_steps"],
                        "harsh": (scores["harsh"] or {}).get("success_rate")}
        print(f"  冻结评测（seed {seed} / {episodes} 局）: 标准 {out['score']['standard']:.3f} · "
              f"严酷 {out['score']['harsh']:.3f} · 均步 {out['score']['standard_mean_steps']:.2f}",
              flush=True)

    env = PerturbedReachEnv(**env_kwargs)
    st = _rollout_stats(env, skill.act, episodes, seed, scale, half, lay)
    out["rollout_success_rate"] = st["success_rate"]
    out["gain_curve"] = _bins(st)
    _print_rows(f"[SAC {ckpt.parent.parent.name}/{ckpt.parent.name}] 回放成功率 {st['success_rate']:.3f}",
                out["gain_curve"])

    edges, gains = _bin_centers_gains(out["gain_curve"])
    replay = GainScheduleSkill(edges, gains, half, scale, lay)
    rs = score_skill(replay, env_kwargs, n_episodes=episodes, seed=seed, harsh=False)
    out["gain_replay"] = {"success_rate": rs["standard"]["success_rate"],
                          "mean_steps": rs["standard"]["mean_steps"],
                          "edges": [round(e, 4) for e in edges],
                          "gains": [round(g, 4) for g in gains]}
    print(f"  增益回放（只保留径向增益、方向精确对准）: 标准 {out['gain_replay']['success_rate']:.3f} · "
          f"均步 {out['gain_replay']['mean_steps']:.2f}", flush=True)
    gap = out["gain_replay"]["success_rate"] - st["success_rate"]
    if st["success_rate"] >= 0.99 and out["gain_replay"]["success_rate"] >= 0.99:
        # 两边都满分 => 没有损失可归因。早先这里会退化成「增益曲线本身」，
        # 把一个"无病"的检查点误标成"有病"，读 JSON 的人会被带偏。
        out["attribution"] = "无损失可归因（实测与回放都已满分）"
    elif abs(gap) <= 0.08:
        out["attribution"] = "增益曲线本身"
    elif gap > 0:
        out["attribution"] = "方向/非径向结构"
    else:
        out["attribution"] = "回放更差（曲线拟合失真）"
    print(f"  归因: 回放-实测 = {gap:+.3f} -> 损失主要在【{out['attribution']}】", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", action="append", required=True, help="SB3 .zip，可多次给")
    ap.add_argument("--config", default="configs/reach_perturbed.yaml")
    ap.add_argument("--episodes", type=int, default=50)
    ap.add_argument("--seed", type=int, default=999)
    ap.add_argument("--skip-reference", action="store_true", help="不跑手写参考曲线")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    cfg_path = REPO_ROOT / args.config
    if not cfg_path.exists():
        print(f"[ERR] 配置不存在: {cfg_path}", file=sys.stderr)
        return 2
    cfg = load_train_config(cfg_path)
    install_env_factory(str(cfg.get("env_factory", "reach")))
    env_kwargs = dict(cfg.get("env") or {})
    lay = obs_layout(env_kwargs)
    half = float(env_kwargs.get("half_space", 0.15))
    scale = float(env_kwargs.get("action_scale", 0.05))

    t0 = time.time()
    result: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "config": str(cfg_path),
        "obs_layout": {k: (list(v) if isinstance(v, tuple) else v) for k, v in lay.items()},
        "eval_protocol": {"n_episodes": args.episodes, "seed": args.seed},
        "r_edges": [None if np.isinf(e) else e for e in R_EDGES],
    }

    print("=" * 78)
    print("参考基线 · 手写比例控制的增益曲线（同一环境、同一评测 seed）")
    print("=" * 78)
    refs = {}
    if not args.skip_reference:
        from envs.reach_perturbed import PerturbedReachEnv
        env = PerturbedReachEnv(**env_kwargs)
        for gain in (1.0, 0.5, 0.3):
            skill = Proportional6D(half, scale, gain=gain, layout=lay)
            st = _rollout_stats(env, skill.act, args.episodes, args.seed, scale, half, lay)
            refs[f"prop_g{gain}"] = {"success_rate": st["success_rate"],
                                     "mean_steps": st["mean_steps"],
                                     "gain_curve": _bins(st)}
            _print_rows(f"[手写 P g={gain}] 回放成功率 {st['success_rate']:.3f} · "
                        f"均步 {st['mean_steps']:.2f}", refs[f"prop_g{gain}"]["gain_curve"])
    result["reference"] = refs

    ckpts = []
    for raw in args.ckpt:
        p = Path(raw)
        p = p if p.is_absolute() else REPO_ROOT / p
        if not p.exists():
            print(f"[ERR] 找不到检查点: {p}", file=sys.stderr)
            return 2
        ckpts.append(p)

    print("=" * 78)
    print("SAC 检查点 · 等效增益分解与归因")
    print("=" * 78)
    result["checkpoints"] = [analyse_ckpt(c, env_kwargs, lay, args.episodes, args.seed, True)
                             for c in ckpts]

    result["elapsed_sec"] = round(time.time() - t0, 2)
    out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / \
        f"{time.strftime('%Y%m%d_%H%M%S')}_policy_gain.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print("-" * 78)
    print(f"已写出: {out}  ({result['elapsed_sec']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
