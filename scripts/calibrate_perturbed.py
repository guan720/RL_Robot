#!/usr/bin/env python
"""标定 `envs/reach_perturbed.py`：找一组让「手写控制器不满分」的扰动参数。

为什么这一步必须做，而不是拍脑袋定参数？
    对照实验要有分辨力，基线必须落在**中间地带**：
        · 随机策略接近 0%    -> 下限干净，「涨了」才是真涨（默认 Reach 随机就有 16%，
                                这正是 `scripts/eval_policy.py` 要加严酷探针的原因）
        · 手写控制器 40~80%  -> 说明任务不平凡，RL 有可学的东西
        · 满分模型 < 100%    -> 说明天花板没被顶死，两臂不会同时饱和
    如果手写控制器是 100%，那这个环境就白搭了——`configs/reach_hard.yaml` 就是这么废掉的
    （实测比例控制在严酷口径下仍 100%）。

用法：
    python scripts/calibrate_perturbed.py                 # 跑预设的几组参数
    python scripts/calibrate_perturbed.py --episodes 100  # 基线更准（慢一点）

顺带会报一个有意思的数：**阶段 1 在无扰动环境里训出来的满分模型，
搬到有延迟/增益噪声的环境里还剩多少成功率**。这个落差就是「动力学没建模」的代价，
也是 sim2real 里最常见的那类失败。
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

ensure_venv("gymnasium", "numpy")

BASE_ENV = {"max_steps": 50, "action_scale": 0.05, "goal_radius": 0.02,
            "min_goal_dist": 0.10, "half_space": 0.15}

# 每行是一组候选扰动。delay/gain/drift 逐个加上去，好看清到底是哪一样在起作用。
PRESETS = [
    {"tag": "无扰动(对照)",        "action_delay": 0, "gain_noise": 0.0, "drift": 0.0},
    {"tag": "只加延迟1",           "action_delay": 1, "gain_noise": 0.0, "drift": 0.0},
    {"tag": "只加延迟2",           "action_delay": 2, "gain_noise": 0.0, "drift": 0.0},
    {"tag": "只加增益噪声50%",      "action_delay": 0, "gain_noise": 0.5, "drift": 0.0},
    {"tag": "只加漂移",            "action_delay": 0, "gain_noise": 0.0, "drift": 0.004},
    {"tag": "延迟2+增益50%",       "action_delay": 2, "gain_noise": 0.5, "drift": 0.0},
    {"tag": "延迟2+增益50%+漂移",   "action_delay": 2, "gain_noise": 0.5, "drift": 0.004},
    {"tag": "延迟3+增益60%+漂移",   "action_delay": 3, "gain_noise": 0.6, "drift": 0.006},
    {"tag": "延迟2+增益90%+漂移",   "action_delay": 2, "gain_noise": 0.9, "drift": 0.004},
    # 第二轮：连「保守比例控制」也要压下去，否则成功率还是会饱和
    {"tag": "延迟3+增益90%+漂移",   "action_delay": 3, "gain_noise": 0.9, "drift": 0.006},
    {"tag": "延迟4+增益80%+漂移",   "action_delay": 4, "gain_noise": 0.8, "drift": 0.008},
    {"tag": "延迟3+增益60%+观测噪声", "action_delay": 3, "gain_noise": 0.6, "drift": 0.006, "obs_noise": 0.05},
    {"tag": "延迟3+增益60%+步30",   "action_delay": 3, "gain_noise": 0.6, "drift": 0.006, "max_steps": 30},
    {"tag": "延迟4+增益70%+步40",   "action_delay": 4, "gain_noise": 0.7, "drift": 0.008, "max_steps": 40},
    {"tag": "延迟5+增益70%+步50",   "action_delay": 5, "gain_noise": 0.7, "drift": 0.008, "max_steps": 50},
]

STAGE1_CKPT = REPO_ROOT / "runs" / "20260922_170720_sac_reach" / "model_final.zip"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--seed", type=int, default=999)
    parser.add_argument("--out", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from eval.reach_eval import evaluate_reach
    from envs.reach_perturbed import make_perturbed_reach_env
    from skills.reach_skills import ProportionalReachSkill, ReachPolicySkill

    # evaluate_reach 内部用的是 make_reach_env，这里临时把工厂换成扰动版：
    # 复用同一份评测代码，保证口径完全一致，不另写一套评测。
    # evaluate_reach 内部是 `from envs.reach_env import make_reach_env`（函数内 import），
    # 所以替换模块属性就能生效，不需要另写一份评测代码。
    import envs.reach_env as reach_env_mod
    original_factory = reach_env_mod.make_reach_env
    reach_env_mod.make_reach_env = make_perturbed_reach_env

    stage1 = ReachPolicySkill(STAGE1_CKPT) if STAGE1_CKPT.exists() else None

    print("=" * 104)
    print(f"扰动 Reach 标定 · episodes={args.episodes} · seed={args.seed} · 基础环境 {BASE_ENV}")
    print("=" * 104)
    header = (f"  {'配置':<22}{'随机':>8}{'P控制 g=1':>11}{'P控制 g=0.5':>12}"
              f"{'阶段1满分模型':>14}{'P控制平均步数':>14}")
    print(header)
    print("  " + "-" * 100)

    rows = []
    for preset in PRESETS:
        tag = preset.pop("tag")
        env_kwargs = {**BASE_ENV, **preset}
        out = {"tag": tag, **preset, "env_kwargs": env_kwargs}
        for label, policy in (("random", None),
                              ("prop_g1", ProportionalReachSkill(action_scale=0.05, gain=1.0)),
                              ("prop_g05", ProportionalReachSkill(action_scale=0.05, gain=0.5))):
            metrics = evaluate_reach(policy, env_kwargs, n_episodes=args.episodes, seed=args.seed)
            out[label] = {"success_rate": metrics["success_rate"],
                          "mean_steps": metrics["mean_steps"],
                          "mean_final_dist": metrics["mean_final_dist"]}
        if stage1 is not None:
            metrics = evaluate_reach(stage1, env_kwargs, n_episodes=args.episodes, seed=args.seed)
            out["stage1_sac"] = {"success_rate": metrics["success_rate"],
                                 "mean_steps": metrics["mean_steps"],
                                 "mean_final_dist": metrics["mean_final_dist"]}
        rows.append(out)
        s1 = out.get("stage1_sac", {}).get("success_rate")
        print(f"  {tag:<22}{out['random']['success_rate'] * 100:>7.1f}%"
              f"{out['prop_g1']['success_rate'] * 100:>10.1f}%"
              f"{out['prop_g05']['success_rate'] * 100:>11.1f}%"
              f"{(f'{s1 * 100:.1f}%' if s1 is not None else 'n/a'):>14}"
              f"{out['prop_g1']['mean_steps']:>14.1f}")

    reach_env_mod.make_reach_env = original_factory

    print()
    print("怎么挑：随机接近 0%、P控制在 40~80%、阶段1模型明显低于 100% 的那一行最合适。")
    print("      P控制仍是 100% 的行 = 任务太简单，对照实验会饱和，不能用。")

    out_path = Path(args.out) if args.out else (
        REPO_ROOT / "runs" / "infra" / f"{time.strftime('%Y%m%d_%H%M%S')}_perturbed_calib.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "base_env": BASE_ENV, "episodes": args.episodes,
                                    "seed": args.seed, "rows": rows},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  已存: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
