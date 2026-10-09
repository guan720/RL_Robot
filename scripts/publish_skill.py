#!/usr/bin/env python
"""把一个已训练好的策略过门禁、发布进 registry（只增不覆盖）。

为什么需要单独一步？因为「训练完了」不等于「可以发布」。发布前必须：
    1. 用**独立 seed** 重新评测（不能用训练时那批题）；
    2. 跑一次**严酷探针**（成功圈收到 2cm、步数上限砍到 50）；
    3. 和 registry 里的现任版本比，确认**旧任务没掉点**且**确实有进步**。

用法：
    # 看看 registry 里现在有什么
    python scripts/publish_skill.py --list

    # 把阶段 1 训好的模型发布成第一个版本
    python scripts/publish_skill.py \
        --ckpt runs/20260922_170720_sac_reach/model_final.zip \
        --skill-name reach_sac --notes "阶段1b 全量 50000 步"

    # 只想看分数、不写入 registry
    python scripts/publish_skill.py --ckpt <path> --dry-run

    # 首个版本没有现任可比，门禁只卡绝对下限
    python scripts/publish_skill.py --ckpt <path> --min-success 0.9
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("stable_baselines3", "yaml", "gymnasium")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ckpt", default="", help="SB3 模型 .zip")
    parser.add_argument("--skill-name", default="reach_sac")
    parser.add_argument("--version", default="", help="留空则自动 v1/v2/... 递增")
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "reach_sac.yaml"))
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--seed", type=int, default=999)
    parser.add_argument("--notes", default="")
    parser.add_argument("--min-gain", type=float, default=0.02)
    parser.add_argument("--min-success", type=float, default=0.0)
    parser.add_argument("--regression-tol", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true", help="只评测打分，不写入 registry")
    parser.add_argument("--list", action="store_true", help="列出 registry 里已有的版本")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from registry import publish as registry

    if args.list or (not args.ckpt and not args.dry_run):
        root = Path(registry.DEFAULT_REGISTRY)
        for name_dir in sorted(p for p in root.iterdir()
                               if p.is_dir() and not p.name.startswith("__")) if root.exists() else []:
            current = registry.load_current(name_dir.name)
            versions = registry.list_versions(name_dir.name)
            print(f"{name_dir.name}: {len(versions)} 个版本，现任 "
                  f"{current['version'] if current else '无'}")
            for item in versions:
                score = item.get("eval_score", {})
                print(f"    {item['version']:<8} kind={item.get('kind','?'):<10} "
                      f"标准={score.get('success_rate')} 严酷={score.get('harsh_success_rate')} "
                      f"· {item.get('created_at','')}")
        return 0

    if not args.ckpt:
        raise SystemExit("需要 --ckpt（或用 --list 查看 registry）")

    import yaml

    from skills.base import SkillMeta, compute_config_hash
    from skills.reach_skills import ReachPolicySkill

    with open(args.config, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    env_kwargs = dict(raw.get("env", {}))
    from harness.env_factory import install_env_factory

    env_factory = install_env_factory(str(raw.get("env_factory", "reach")))
    print(f"环境实现: {env_factory}")

    # 版本号留空就用 registry 的自增号（v1/v2/...），不要用 ckpt hash：
    # 版本要能一眼看出先后顺序，hash 只适合放在 meta.source 里做溯源。
    version = args.version or registry.next_version(
        Path(registry.DEFAULT_REGISTRY) / args.skill_name)
    skill = ReachPolicySkill(args.ckpt, name=args.skill_name, version=version,
                             notes=args.notes, env_hash=compute_config_hash(env_kwargs))
    print("=" * 72)
    print(f"评测候选: {skill.meta.short()} · {args.ckpt}")
    print(f"独立 seed={args.seed} · episodes={args.episodes} · 环境 hash={skill.meta.env_hash}")
    print("=" * 72)

    scores = registry.score_skill(skill, env_kwargs, n_episodes=args.episodes, seed=args.seed)
    metrics = registry.summarize_scores(scores)
    incumbent = registry.current_metrics(args.skill_name)
    ok, reasons = registry.decide(metrics, incumbent, min_gain=args.min_gain,
                                  regression_tol=args.regression_tol,
                                  min_success=args.min_success)

    print(f"  标准条件   成功率 {metrics['success_rate']:.3f} · 平均步数 {metrics['mean_steps']} "
          f"· 平均末距 {metrics['mean_final_dist']:.4f} m")
    print(f"  严酷探针   成功率 {metrics['harsh_success_rate']:.3f} "
          f"· 平均末距 {metrics['harsh_mean_final_dist']:.4f} m  {registry.HARSH_PROBE}")
    print(f"  现任版本   {incumbent if incumbent else '无（首次发布）'}")
    print(f"  门禁判定   {'通过' if ok else '不通过'}")
    for reason in reasons:
        print(f"    · {reason}")

    if args.dry_run:
        print("  --dry-run：不写入 registry")
        return 0 if ok else 1
    if not ok:
        print("  门禁未通过，拒绝发布。（registry 是 append-only，只收过线的版本）")
        return 1

    target = registry.publish(
        skill_name=args.skill_name, ckpt=args.ckpt, meta=skill.meta, scores=scores,
        gate={"ok": ok, "reasons": reasons, "min_gain": args.min_gain,
              "min_success": args.min_success, "regression_tol": args.regression_tol},
        extra={"source_ckpt": str(Path(args.ckpt).resolve()), "config": args.config})
    print(f"  已发布: {target}")
    print(f"  现任指针: {Path(target).parent / 'current.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
