#!/usr/bin/env python
"""transport 技能的冒烟 / 发布入口（**只新增文件**，不碰另一条线的代码）。

回答三个问题，每个都有会明确失败的检查：

    1. 环境契约对不对？      观测 7 维、动作 2 维、量纲与 configs/transport_sac.yaml 一致
    2. 技能接口通不通？      比例控制与冻结 RL 权重都能在同一个 env 上跑出任务完成率
    3. env_hash 稳不稳？     同参数算两次必须相同；换扰动档位 / 换 ckpt 必须不同

为什么默认**不发布**：另一条线还在改 `envs/transport_perturbed.py`，
现在把分数写进 registry 只会制造「环境不一致」的旧版本。`--publish` 是显式开关，
而且门禁第 0 条（env_hash 一致）会替我们把并发污染挡在版本线外面。

用法：
    python scripts/smoke_transport_skill.py --list
    python scripts/smoke_transport_skill.py --smoke
    python scripts/smoke_transport_skill.py --smoke --episodes 3 --level nominal
    python scripts/smoke_transport_skill.py --publish --dry-run      # 只打分过门禁，不写 registry
    python scripts/smoke_transport_skill.py --publish                # 真的写 registry（显式）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "gymnasium", "stable_baselines3", "yaml")

import numpy as np  # noqa: E402

from skills import transport_skill as ts  # noqa: E402

DEFAULT_SKILL_NAME = "transport_frozen_wrap"     # 带 wrap 后缀，避免和另一条线的版本名撞车


# --------------------------------------------------------------------------- 工具
def find_candidate_ckpts() -> list[Path]:
    """扫 runs/ 下所有 transport 训练的冻结权重（只读）。"""
    found: list[Path] = []
    for pattern in ("*/model_final.zip", "*/best_model.zip"):
        for path in sorted((REPO_ROOT / "runs").glob(pattern)):
            if "transport" in path.parent.name:
                found.append(path)
    return found


def check_env_contract(env_kwargs: dict) -> list[str]:
    """环境契约检查：返回问题列表，空列表 = 全过。"""
    problems: list[str] = []
    env = ts.make_transport_env(env_kwargs, level="nominal")
    obs_shape = tuple(env.observation_space.shape)
    act_shape = tuple(env.action_space.shape)
    if obs_shape != (7,):
        problems.append(f"观测应为 7 维，实际 {obs_shape}")
    if act_shape != (2,):
        problems.append(f"动作应为 2 维，实际 {act_shape}")
    obs, info = env.reset(seed=0)
    if np.asarray(obs).shape != (7,):
        problems.append(f"reset 返回的观测形状不对: {np.asarray(obs).shape}")
    for key in ("direction", "held", "tasks_attempted"):
        if key not in info:
            problems.append(f"info 缺键 {key}（harness 记账依赖它）")
    return problems


def check_hash_stability(env_kwargs: dict, ckpt: Path | None) -> list[str]:
    """env_hash 的三个性质：自反、档位敏感、权重敏感。"""
    problems: list[str] = []
    first = ts.transport_env_hash(env_kwargs, ckpt=ckpt, level="nominal", harsh_level="medium")
    second = ts.transport_env_hash(env_kwargs, ckpt=ckpt, level="nominal", harsh_level="medium")
    if first != second:
        problems.append("env_hash 不稳定：同样参数算两次结果不同")
    levels = [name for name in ts.available_levels() if name != "nominal"]
    if levels:
        other = ts.transport_env_hash(env_kwargs, ckpt=ckpt, level=levels[0], harsh_level="medium")
        if other == first:
            problems.append(f"env_hash 对扰动档位不敏感（nominal == {levels[0]}）")
    if ckpt is not None and ckpt.exists():
        no_ckpt = ts.transport_env_hash(env_kwargs, ckpt=None, level="nominal", harsh_level="medium")
        if no_ckpt == first:
            problems.append("env_hash 对 ckpt 不敏感（带权重 == 不带权重）")
    return problems


# --------------------------------------------------------------------------- 子命令
def do_list(env_kwargs: dict, skill_name: str) -> int:
    print("=" * 88)
    print("transport 技能包装 · --list")
    print("=" * 88)
    print(f"  环境参数（来自 {ts.DEFAULT_CONFIG.name} 的 env 块）:")
    for key, value in env_kwargs.items():
        print(f"    {key:16s} = {value}")
    print(f"  扰动档位: {ts.available_levels()}")
    print(f"  候选冻结权重:")
    ckpts = find_candidate_ckpts()
    if not ckpts:
        print("    （runs/ 下没找到 transport 的 model_final/best_model）")
    for path in ckpts:
        print(f"    {path.relative_to(REPO_ROOT)}  ({path.stat().st_size/1e6:.2f} MB)")
    from registry import publish as pub

    versions = pub.list_versions(skill_name)
    print(f"  registry[{skill_name}] 已有版本: {len(versions)}")
    for meta in versions:
        print(f"    {meta.get('version')} env_hash={meta.get('env_hash')} "
              f"score={meta.get('eval_score', {}).get('success_rate')}")
    current = pub.load_current(skill_name)
    if current:
        print(f"  现任: {current.get('version')} env_hash={current.get('env_hash')}")
    else:
        print("  现任: 无（还没发布过）")
    return 0


def do_smoke(env_kwargs: dict, ckpt: Path | None, episodes: int, seed: int,
             level: str, harsh_level: str, out_dir: Path) -> int:
    print("=" * 88)
    print(f"transport 技能包装 · --smoke（level={level}, episodes={episodes}, seed={seed}）")
    print("=" * 88)
    report: dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "env_kwargs": env_kwargs,
        "level": level,
        "harsh_level": harsh_level,
        "ckpt": str(ckpt) if ckpt else "",
        "checks": {},
        "skills": {},
    }
    failed = False

    problems = check_env_contract(env_kwargs)
    report["checks"]["env_contract"] = problems
    print(f"  [1] 环境契约: {'OK' if not problems else 'FAIL ' + '; '.join(problems)}")
    failed = failed or bool(problems)

    hash_problems = check_hash_stability(env_kwargs, ckpt)
    report["checks"]["env_hash"] = hash_problems
    print(f"  [2] env_hash 稳定性: {'OK' if not hash_problems else 'FAIL ' + '; '.join(hash_problems)}")
    failed = failed or bool(hash_problems)

    env_hash = ts.transport_env_hash(env_kwargs, ckpt=ckpt, level=level, harsh_level=harsh_level)
    report["env_hash"] = env_hash
    print(f"      env_hash = {env_hash}")

    scripted = ts.ProportionalTransportSkill(
        half=env_kwargs["half"], action_scale=env_kwargs["action_scale"], env_hash=env_hash)
    print(f"  [3] 比例控制技能 {scripted.meta.short()}")
    result = ts.run_transport_episodes(scripted, env_kwargs, level=level,
                                       n_episodes=episodes, seed=seed)
    metrics = result["metrics"]
    report["skills"]["proportional"] = result
    ok = metrics["tasks_done"] > 0
    failed = failed or not ok
    print(f"      任务完成率 {metrics['success_rate']:.3f} "
          f"(forward {metrics['success_forward_rate']:.3f} / backward {metrics['success_backward_rate']:.3f}) "
          f"· 覆盖 {metrics['coverage']:.2f} · 救场 {metrics['manual_resets']} 次 "
          f"· {metrics['env_steps']} 环境步 -> {'OK' if ok else 'FAIL（一个 task 都没完成）'}")

    if ckpt is not None and ckpt.exists():
        policy = ts.TransportPolicySkill(ckpt, env_hash=env_hash, name="transport_frozen")
        print(f"  [4] 冻结 RL 技能 {policy.meta.short()}")
        obs, _ = ts.make_transport_env(env_kwargs, level=level).reset(seed=seed)
        action = np.asarray(policy(obs)).reshape(-1)
        shape_ok = action.shape == (2,) and bool(np.all(np.abs(action) <= 1.0 + 1e-6))
        result_policy = ts.run_transport_episodes(policy, env_kwargs, level=level,
                                                  n_episodes=episodes, seed=seed)
        pm = result_policy["metrics"]
        report["skills"]["policy"] = result_policy
        report["checks"]["policy_action_shape"] = [] if shape_ok else [f"动作形状/范围不对: {action.shape}"]
        failed = failed or not shape_ok
        print(f"      动作形状 {action.shape} 范围[-1,1] -> {'OK' if shape_ok else 'FAIL'}")
        print(f"      任务完成率 {pm['success_rate']:.3f} "
              f"(forward {pm['success_forward_rate']:.3f} / backward {pm['success_backward_rate']:.3f}) "
              f"· 覆盖 {pm['coverage']:.2f} · 救场 {pm['manual_resets']} 次 · {pm['env_steps']} 环境步")
    else:
        print(f"  [4] 跳过 RL 技能（找不到权重: {ckpt}）")
        report["checks"]["policy_action_shape"] = ["skipped: ckpt missing"]

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{stamp}_transport_skill_smoke.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  结果写入: {out_path.relative_to(REPO_ROOT)}")
    print(f"  结论: {'全部通过' if not failed else '有检查失败（见上）'}")
    return 1 if failed else 0


def do_publish(env_kwargs: dict, ckpt: Path, episodes: int, seed: int, level: str,
               harsh_level: str, skill_name: str, min_gain: float, min_success: float,
               dry_run: bool, notes: str) -> int:
    from registry import publish as pub

    if not ckpt.exists():
        print(f"[错误] 找不到要发布的权重: {ckpt}")
        return 2
    env_hash = ts.transport_env_hash(env_kwargs, ckpt=ckpt, level=level, harsh_level=harsh_level)
    skill = ts.TransportPolicySkill(ckpt, env_hash=env_hash, name="transport_frozen", notes=notes)
    print(f"打分中（标准 {level} + 探针 {harsh_level}，各 {episodes} 局）...")
    scores = ts.score_transport_skill(skill, env_kwargs, n_episodes=episodes, seed=seed,
                                      level=level, harsh_level=harsh_level)
    summary = ts.summarize_transport_scores(scores)
    print(f"  标准: 任务完成率 {summary['success_rate']:.3f} "
          f"(fwd {summary['success_forward_rate']:.3f} / bwd {summary['success_backward_rate']:.3f}) "
          f"覆盖 {summary['coverage']:.2f}")
    print(f"  探针: 任务完成率 {summary['harsh_success_rate']:.3f} 覆盖 {summary['harsh_coverage']:.2f}")

    incumbent = pub.current_metrics(skill_name)
    incumbent_hash = pub.current_env_hash(skill_name)
    ok, reasons = pub.decide(summary, incumbent, min_gain=min_gain, min_success=min_success,
                             candidate_env_hash=env_hash, incumbent_env_hash=incumbent_hash)
    print(f"  门禁: {'通过' if ok else '拒绝'}")
    for reason in reasons:
        print(f"    - {reason}")
    if dry_run:
        print("  --dry-run：不写 registry")
        return 0 if ok else 1
    if not ok:
        print("  门禁未过，不发布。")
        return 1
    skill.meta.eval_score = summary
    target = pub.publish(skill_name=skill_name, ckpt=ckpt, meta=skill.meta, scores=scores,
                         gate={"ok": ok, "reasons": reasons},
                         extra={"level": level, "harsh_level": harsh_level,
                                "env_kwargs": env_kwargs})
    print(f"  已发布: {target.relative_to(REPO_ROOT)}")
    return 0


# --------------------------------------------------------------------------- CLI
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="只列环境/档位/权重/版本库，不跑")
    parser.add_argument("--smoke", action="store_true", help="跑契约 + 接口冒烟（默认动作）")
    parser.add_argument("--publish", action="store_true", help="打分过门禁并发布（显式开关）")
    parser.add_argument("--dry-run", action="store_true", help="与 --publish 同用：只打分不写 registry")
    parser.add_argument("--ckpt", default=str(ts.FROZEN_CKPT), help="冻结权重路径")
    parser.add_argument("--config", default=str(ts.DEFAULT_CONFIG), help="环境参数 yaml")
    parser.add_argument("--episodes", type=int, default=2, help="每个技能的评测局数（冒烟用小的）")
    parser.add_argument("--seed", type=int, default=999)
    parser.add_argument("--level", default="nominal", help=f"标准条件档位: {ts.available_levels()}")
    parser.add_argument("--harsh-level", default="medium", help="扰动探针档位")
    parser.add_argument("--skill-name", default=DEFAULT_SKILL_NAME,
                        help="registry 里的技能名（默认带 wrap 后缀，避免和另一条线撞名）")
    parser.add_argument("--min-gain", type=float, default=0.02)
    parser.add_argument("--min-success", type=float, default=0.0)
    parser.add_argument("--notes", default="transport 冻结权重包装（并发期只包接口）")
    parser.add_argument("--out", default="runs/infra", help="冒烟 JSON 输出目录")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_kwargs = ts.load_transport_env_kwargs(args.config)
    ckpt = Path(args.ckpt)
    if args.list:
        return do_list(env_kwargs, args.skill_name)
    if args.publish:
        return do_publish(env_kwargs, ckpt, args.episodes, args.seed, args.level,
                          args.harsh_level, args.skill_name, args.min_gain, args.min_success,
                          args.dry_run, args.notes)
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    return do_smoke(env_kwargs, ckpt, args.episodes, args.seed, args.level,
                    args.harsh_level, out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
