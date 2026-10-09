#!/usr/bin/env python
"""用修复后的成功口径重评 PickPlaceCan 的 ckpt。

背景（2026-09-23 的坑）：robosuite 1.5 的 `info` 是空 dict，早期代码读 `info["success"]`
恒为 False；真值在 `env._check_success()`。修复前跑的训练，其「episode 成功率」列不可信
（奖励列仍可信），用本脚本对保存的 model_final.zip 重评。

用法：
    python scripts/eval_pickplace_ckpt.py --run runs/20260923_135619_sac_pickplace_state
    python scripts/eval_pickplace_ckpt.py --ckpt runs/xxx/model_final.zip --obs state --episodes 10
    # 监护配对（裸策略 vs 带抓取监护，同 seed）：
    python scripts/eval_pickplace_ckpt.py --run runs/xxx --episodes 20 --guard
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("stable_baselines3", "numpy", "torch")

sys.modules.setdefault("torch.utils.tensorboard", None)  # 本脚本不建渲染环境，但保持与训练脚本一致

from stable_baselines3 import SAC  # noqa: E402

from scripts.train_pickplace_sac import evaluate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="")
    ap.add_argument("--ckpt", default="")
    ap.add_argument("--obs", default="")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--horizon", type=int, default=400)
    ap.add_argument("--seed-base", type=int, default=5000)
    ap.add_argument("--tag", default="",
                    help="产物文件名后缀：同一个 run 里评多个 ckpt（final/best）时别互相覆盖")
    ap.add_argument("--guard", action="store_true",
                    help="配对评测：裸策略 vs 带抓取监护（harness/grasp_guard.py），输出 rescue_delta")
    ap.add_argument("--guard-max", type=int, default=2, help="监护每局最多接管几次")
    ap.add_argument("--guard-dwell", type=int, default=8,
                    help="在抓取窗口内连续多少步不合爪才接管（防抢策略自己的合爪动作）")
    ap.add_argument("--guard-mode", default="window", choices=["window", "stall"],
                    help="window=只补'到了抓取位却不合爪'；stall=放宽到'在物体附近停住不动又不合爪'"
                         "（PickPlace 那种连抓取窗口都进不去的失败要用 stall）")
    ap.add_argument("--guard-stall-steps", type=int, default=20,
                    help="stall 模式：判定'停在原地'的窗长（=1s @20Hz）")
    ap.add_argument("--no-pin-object", action="store_true",
                    help="复现旧口径（物体尺寸/出生点不钉死）；默认按 config 的 pin_object，缺省钉死")
    args = ap.parse_args()

    # 只给 --ckpt 时，从 ckpt 所在目录反查 config.json：task/hist 不读回来会把 Lift 的模型
    # 套到 PickPlaceCan 环境上（观测 60 维 vs 64 维，2026-09-24 实测直接 ValueError）。
    run_dir = Path(args.run) if args.run else (
        Path(args.ckpt).resolve().parent if args.ckpt else None)
    cfg = {}
    if run_dir is not None and (run_dir / "config.json").exists():
        cfg = json.loads((run_dir / "config.json").read_text())
    ckpt = args.ckpt or str(run_dir / "model_final.zip")
    tag = f"_{args.tag}" if args.tag else ""
    obs_mode = args.obs or cfg.get("obs", "state")
    cams = tuple(cfg.get("cams", ["agentview"]))
    cam_size = int(cfg.get("cam_size", 64))
    reward_shaping = bool(cfg.get("reward_shaping", False))

    model = SAC.load(ckpt, device="cpu")
    model.obs_mode, model.cams, model.cam_size = obs_mode, cams, cam_size
    model.reward_shaping = reward_shaping
    model.task = cfg.get("task", "pickplace")
    model.hist = int(cfg.get("hist", 1))
    model.pin_object = bool(cfg.get("pin_object", 1)) and not args.no_pin_object

    if args.guard:
        from harness.grasp_guard import GuardConfig, evaluate_guarded
        gcfg = GuardConfig(max_per_episode=args.guard_max, dwell_steps=args.guard_dwell,
                           mode=args.guard_mode, stall_steps=args.guard_stall_steps)
        gres = evaluate_guarded(model, seed_base=args.seed_base, episodes=args.episodes,
                                horizon=args.horizon, cfg=gcfg)
        po, gu = gres["policy_only"], gres["guarded"]
        print(f"[监护配对] {ckpt}")
        print(f"       task={model.task} obs={obs_mode} hist={model.hist} shaping={reward_shaping} "
              f"({args.episodes} 局 · seed_base={args.seed_base})")
        print(f"       模式={args.guard_mode} pin_object={model.pin_object}")
        print(f"       裸策略   成功率 {po['success_rate']*100:5.1f}%  抓住 {po['held_rate']*100:5.1f}%  "
              f"tasks {po['tasks_done']}")
        print(f"       带监护   成功率 {gu['success_rate']*100:5.1f}%  抓住 {gu['held_rate']*100:5.1f}%  "
              f"tasks {gu['tasks_done']}  "
              f"接管 {gu['interventions']} 次/{gu['guard_steps']} 步  "
              f"干预局占比 {gu['intervention_rate']*100:.0f}%  救回 {gu['rescued_episodes']} 局")
        print(f"       rescue_delta = {gres['rescue_delta']*100:+.1f} 个百分点 · "
              f"held_delta = {gres['held_delta']*100:+.1f} 个百分点"
              f"（正数 = 监护确实救回了局；≈0 = 成绩是策略自己的）")
        if gu["interventions"] == 0:
            print("       注：监护一次都没出手 => 失败不在'合爪'这一环（多半是接近/对齐段），"
                  "此时加抓取示范或抓取监护都不会有效")
        if run_dir is not None:
            out = run_dir / f"guard_rescue{tag}.json"
            out.write_text(json.dumps({"ckpt": ckpt, "guard_cfg": vars(gcfg),
                                       **{k: v for k, v in gres.items() if k != "per_episode"},
                                       "per_episode": gres["per_episode"]}, indent=2))
            print(f"[saved] {out}")
        return

    res = evaluate(model, seed_base=args.seed_base, episodes=args.episodes, horizon=args.horizon,
                   pin=model.pin_object)
    print(f"[重评] {ckpt}\n       obs={obs_mode} shaping={reward_shaping} "
          f"episode 成功率 {res['episode_success']*100:.1f}%  tasks {res['tasks_done']}  "
          f"mean_reward {res['mean_reward']:.2f}  ({args.episodes} 局)")
    if run_dir is not None:
        out = run_dir / f"reeval_fixed_success{tag}.json"
        out.write_text(json.dumps({"ckpt": ckpt, **res}, indent=2))
        print(f"[saved] {out}")


if __name__ == "__main__":
    main()
