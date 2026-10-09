#!/usr/bin/env python
"""阶段 3：跑一次完整的自学习闭环（采集 -> 诊断 -> 训练 -> 独立评测 -> 门禁发布）。

这是 `scripts/demo_harness_tree.py` 的下一步：demo 用假机械臂讲控制流，
这里用**真环境 + 真技能 + 真训练**，并且带预算记账和发布门禁。

用法：
    # 冒烟（几分钟，只验证闭环通不通，不指望学会）
    python scripts/run_harness_loop.py --mode diagnosed --budget-steps 1200 \
        --steps-per-round 600 --episodes 10 --rounds 2

    # 正式对照实验的一臂（另一臂把 --mode 换成 uniform）
    python scripts/run_harness_loop.py --mode diagnosed --budget-steps 12000 \
        --steps-per-round 4000 --episodes 20 --skill-name reach_harness_diagnosed

    # 两臂一起跑 + 出对照表（推荐，省得手抖把参数写得不一致）
    python scripts/compare_harness_ab.py --budget-steps 12000 --steps-per-round 4000

本机是共享节点（load average 常在 1000 上下），单线程 SAC 约 15 步/秒，
所以 12000 步的一臂大约 15-20 分钟。长任务请后台跑：
    setsid nohup python -u scripts/compare_harness_ab.py --budget-steps 12000 \
        > /tmp/ab.log 2>&1 < /dev/null & disown
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

ensure_venv("stable_baselines3", "yaml", "gymnasium", "py_trees")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", default="diagnosed", choices=["uniform", "diagnosed"],
                        help="uniform=固定均匀采样(对照组)；diagnosed=按失败诊断针对性采样(实验组)")
    parser.add_argument("--budget-steps", type=int, default=12000,
                        help="总交互预算（采集 + 训练都算进去）。对照实验两臂必须一致")
    parser.add_argument("--steps-per-round", type=int, default=4000, help="每轮训练步数")
    parser.add_argument("--episodes", type=int, default=20, help="每轮采集多少局用来诊断")
    parser.add_argument("--rounds", type=int, default=8, help="最多跑几轮")
    parser.add_argument("--target-success", type=float, default=0.95,
                        help="采集成功率达到就提前停（已经会了，别再烧预算）")
    parser.add_argument("--init", default="random",
                        help="起点：random / untrained / 或一个 SB3 .zip 路径")
    parser.add_argument("--skill-name", default="",
                        help="发布到 registry 的技能名。默认 harness_<config名>_<mode>："
                             "名字里必须带环境标识，否则换环境跑会把两个环境的分数"
                             "混进同一条版本线（门禁现在会拦，但别依赖它兜底）")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval-episodes", type=int, default=50)
    parser.add_argument("--eval-seed", type=int, default=999,
                        help="独立评测 seed，必须不同于训练 seed 和采集 seed")
    parser.add_argument("--min-gain", type=float, default=0.02,
                        help="门禁：候选要比现任高这么多才发布（防止把评测噪声当进步）")
    parser.add_argument("--regression-tol", type=float, default=0.0,
                        help="门禁：允许比现任低多少。默认 0 = 零容忍，配 50 局评测时"
                             "真值相同也有约一半概率被判掉点（§12.11-G）；接触任务建议 0.20")
    parser.add_argument("--min-success", type=float, default=0.0,
                        help="门禁：标准条件成功率的绝对下限（默认 0 = 不设限）")
    parser.add_argument("--gate-stats", default="legacy", choices=["legacy", "paired_v1"],
                        help="发布判定的统计口径。legacy=二态（历史 run 的口径，默认）；"
                             "paired_v1=三态 publish/reject/inconclusive，用逐题配对的 McNemar "
                             "精确检验（同一批 seed，零额外成本），分辨不出时**不**判该方向失败。"
                             "评测局数的 MDE 大于 min_gain 时必须打开，否则门禁在量噪声")
    parser.add_argument("--success-metric", default="success_rate",
                        choices=["success_rate", "success_rate_grasp_verified"],
                        help="门禁判哪个成功口径。默认 success_rate（reach 历史行为）；"
                             "接触任务必须用 success_rate_grasp_verified —— 环境的 "
                             "_check_success 不要求真抓住，Lift 最弱那档实测 flick_frac=0.500，"
                             "即一半的“成功”是指间把 cube 弹过阈值（§12.11-N）")
    parser.add_argument("--require-grasp-verified", action="store_true",
                        help="打分结果里没有 grasp-verified 口径就硬拒发布（不许静默按 0.0 判）。"
                             "接触 A/B 建议与 --success-metric success_rate_grasp_verified 一起开")
    parser.add_argument("--deploy", default="latest", choices=["latest", "published"],
                        help="latest=每轮把最新权重投入采集(在线RL,默认)；"
                             "published=只部署过了门禁的版本(生产口径)")
    parser.add_argument("--mix-uniform", type=float, default=0.25,
                        help="实验组里保留的均匀采样比例，防止只在窄带训练导致旧能力退化")
    parser.add_argument("--band-mode", default="range",
                        choices=["range", "quantile", "labelcond", "frontier"],
                        help="诊断分带方式。quantile = 带边取失败距离的分位数（干预更强），"
                             "见 harness/diagnose.py 的说明与 scripts/probe_intervention_design.py")
    parser.add_argument("--plan-floor", type=float, default=0.15,
                        help="归一化前的保底权重。range 分带下 0.15 会把 37.5%% 的质量喂给空带")
    parser.add_argument("--plan-bands", type=int, default=4)
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "reach_sac.yaml"))
    parser.add_argument("--out", default="", help="输出目录，默认 runs/<时间戳>_harness_<mode>")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from harness.loop import HarnessLoop, LoopConfig
    from harness.trainer import load_train_config

    trainer_cfg = load_train_config(args.config)
    env_kwargs = trainer_cfg["env"]
    from harness.env_factory import from_config

    from_config(trainer_cfg)
    skill_name = args.skill_name or f"harness_{Path(args.config).stem}_{args.mode}"

    cfg = LoopConfig(
        mode=args.mode,
        budget_steps=args.budget_steps,
        episodes_per_round=args.episodes,
        steps_per_round=args.steps_per_round,
        max_rounds=args.rounds,
        target_success=args.target_success,
        eval_episodes=args.eval_episodes,
        eval_seed=args.eval_seed,
        seed=args.seed,
        skill_name=skill_name,
        init=args.init,
        min_gain=args.min_gain,
        regression_tol=args.regression_tol,
        min_success=args.min_success,
        gate_stats=args.gate_stats,
        success_metric=args.success_metric,
        require_grasp_verified=args.require_grasp_verified,
        mix_uniform=args.mix_uniform,
        band_mode=args.band_mode,
        plan_floor=args.plan_floor,
        plan_bands=args.plan_bands,
        deploy=args.deploy,
        env_kwargs=env_kwargs,
        config_path=args.config,
        out_dir=args.out,
        device=args.device,
        threads=args.threads,
    )
    HarnessLoop(cfg, verbose=not args.quiet).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
