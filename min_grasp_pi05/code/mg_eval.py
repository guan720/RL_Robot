#!/usr/bin/env python
"""最小抓取链路 · 闭环评测（同步 BC / π₀.₅ 都走这一条路）。

口径：
  * 从**示范初态**出发（--seed 默认 = 采集时的固定 seed），单臂、单局、同步执行；
  * 成功 = robosuite 真值 env._check_success() 在局内**曾经**为 True（latch），不用奖励、不用自写几何；
  * 指标：pc_success（成功率）、avg_steps_to_success、每局动作/状态统计；
  * 诊断：把策略动作分布与示范动作分布并排打印——归一化/夹爪语义/动作处理器出错时，
    这里会先露馅（比如策略 gripper 恒为 +0.02、或位置增量量级差 20 倍）；
  * 不引入异步 chunk 调度：`--n-action-steps K` 只是改「执行 K 步再重规划」，K=1 是全闭环，
    K=chunk_size 是标准 chunk 执行，两者都是同步的。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_eval.py \
        --ckpt runs/act_fixed/checkpoints/last/pretrained_model --episodes 10 --video'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from mg_env import (  # noqa: E402
    ACTION_DIM, ACTION_KEY, ACTION_NAMES, CAM_BASE, FIXED_SEED, IMG_KEY_BASE, STATE_KEY, STATE_NAMES,
    TASK, SingleArmGraspEnv,
)

RUNS = MG_ROOT / "runs"


def to_tensor_obs(obs: dict, device: torch.device, task: str = TASK) -> dict:
    """环境 obs（numpy）-> lerobot 策略输入（batch=1 的 torch 张量）。

    task 默认 = mg_env.TASK（正向）。档 2 起反向局传 TASK_REVERSE —— 语言条件是 π₀.₅
    区分正/反向的唯一线索，喂错字符串 = 评测的不是你想评的那个任务。
    """
    out: dict = {}
    for key, val in obs.items():
        arr = np.asarray(val)
        if arr.dtype == np.uint8 and arr.ndim == 3:          # 图像 HWC uint8 -> CHW float[0,1]
            t = torch.from_numpy(arr).permute(2, 0, 1).contiguous().to(device=device, dtype=torch.float32)
            t = t / 255.0
            out[key] = t.unsqueeze(0)
        else:                                                # 状态向量 -> float32
            t = torch.from_numpy(np.asarray(arr, dtype=np.float32)).to(device=device)
            out[key] = t.unsqueeze(0)
    out["task"] = [task]
    return out


def load_policy(ckpt: Path, device: torch.device, use_amp: bool):
    """从 lerobot 检查点目录重建「策略 + 前后处理器」。

    三个坑（都在 0.4.4 上踩过）：
      * `PreTrainedPolicy` 是抽象类，必须先用 config.type 找到具体策略类；
      * `make_pre_post_processors` 只认 TypedDict 里的那几个 kwargs，`device=`/`use_amp=`
        会被静默丢掉——设备必须通过 `*_overrides` 打到 `device_processor` 步骤上，
        否则 batch 落在检查点保存时的设备上（π₀.₅ 基座的 JSON 里写的是 cpu）；
      * 处理器状态（归一化统计）跟着检查点走，评测端不需要数据集。
    """
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies.factory import get_policy_class, make_pre_post_processors

    config = PreTrainedConfig.from_pretrained(str(ckpt))
    policy_cls = get_policy_class(config.type)
    policy = policy_cls.from_pretrained(str(ckpt), config=config, local_files_only=True)
    policy.to(device)
    policy.eval()
    overrides = {"device_processor": {"device": device.type}}
    pre, post = make_pre_post_processors(
        policy.config,
        pretrained_path=str(ckpt),
        preprocessor_overrides=overrides,
        postprocessor_overrides=dict(overrides),
    )
    return policy, pre, post


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True, help="lerobot 检查点目录（含 config.json + model.safetensors）")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--seed", type=int, default=FIXED_SEED, help="评测初态 seed（默认 = 示范的固定初态）")
    ap.add_argument("--seed-mode", choices=("fixed", "random"), default="fixed")
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--n-action-steps", type=int, default=0,
                    help="覆盖 chunk 执行步数：0=用检查点自带值，1=全闭环逐步重规划")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--max-videos", type=int, default=1)
    ap.add_argument("--demo-npz", default="", help="示范 npz，用来做动作分布对照")
    ap.add_argument("--out", default="")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--use-amp", action="store_true")
    ap.add_argument("--task-mode", choices=("forward", "reverse"), default="forward",
                    help="forward=can 从托盘放进篮格（档 0/1）；reverse=can 从篮格放回托盘（档 2）。"
                         "反向用 mg_env_reverse.ReverseGraspEnv + TASK_REVERSE，其余口径完全一致")
    ap.add_argument("--num-inference-steps", type=int, default=0,
                    help="覆盖 flow-matching 去噪步数（π₀.₅ 默认 10）。采样更准 = 对噪声更不敏感；"
                         "ACT 等无此参数的策略忽略。")
    args = ap.parse_args()

    ckpt = Path(args.ckpt)
    if not ckpt.exists():
        print(f"[err] 检查点不存在：{ckpt}", file=sys.stderr)
        return 2
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else RUNS / f"eval_{ts}_{ckpt.parent.name}_{ckpt.name}"
    out_dir.mkdir(parents=True, exist_ok=True)

    policy, pre, post = load_policy(ckpt, device, args.use_amp)
    chunk_size = int(getattr(policy.config, "chunk_size", -1))
    # select_action() 读的是 policy.config.n_action_steps（动作队列长度），不是 policy 上的同名属性；
    # 而且它不能超过 chunk_size（PI05Config.__post_init__ 会直接报错）。
    n_action_steps = int(getattr(policy.config, "n_action_steps", 1) or 1)
    if args.n_action_steps:
        n_action_steps = min(int(args.n_action_steps), chunk_size) if chunk_size > 0 else int(args.n_action_steps)
        policy.config.n_action_steps = n_action_steps
    policy.reset()
    if args.num_inference_steps and hasattr(policy.config, "num_inference_steps"):
        policy.config.num_inference_steps = int(args.num_inference_steps)
    print(f"[policy] {type(policy).__name__} ckpt={ckpt}")
    print(f"[policy] chunk_size={chunk_size} n_action_steps={n_action_steps} device={device} "
          f"amp={args.use_amp} 参数量={sum(p.numel() for p in policy.parameters()) / 1e6:.1f}M")

    if args.task_mode == "reverse":
        from mg_env_reverse import TASK_REVERSE, ReverseGraspEnv   # 延迟 import：正向路径一行都不碰
        env = ReverseGraspEnv(img_size=args.img_size)
        task_str = TASK_REVERSE
    else:
        env = SingleArmGraspEnv(img_size=args.img_size)
        task_str = TASK
    print(f"[eval] task_mode={args.task_mode} task={task_str!r} env={type(env).__name__} "
          f"horizon={env.horizon}")
    per_ep = []
    all_actions: list[np.ndarray] = []
    all_states: list[np.ndarray] = []
    videos = 0
    t_start = time.perf_counter()

    for ep in range(args.episodes):
        seed = args.seed if args.seed_mode == "fixed" else args.seed + ep
        obs = env.reset(seed=seed)
        if hasattr(policy, "reset"):
            policy.reset()
        frames = []
        ep_actions = []
        ep_states = []
        ever_success = False
        succ_step = -1
        ever_success_rlx = False
        succ_step_rlx = -1
        ever_tipped = False
        ever_in_box = False
        final_tilt = float("nan")
        steps = 0
        min_dist = float("inf")
        max_lift = 0.0
        z0 = float(env.object_pos[2])
        while True:
            t_obs = to_tensor_obs(obs, device, task=task_str)
            with torch.inference_mode():
                t_obs = pre(t_obs)
                action = policy.select_action(t_obs)
                action = post(action)
            act = action.squeeze(0).detach().to("cpu").numpy().astype(np.float32)
            if act.shape[0] != ACTION_DIM:
                raise ValueError(f"策略输出 {act.shape[0]} 维，契约要求 {ACTION_DIM} 维")
            ep_actions.append(act)
            ep_states.append(obs[STATE_KEY])
            obs, _r, terminated, truncated, info = env.step(act)
            steps += 1
            ever_success = ever_success or info["success"]
            if info["success"] and succ_step < 0:
                succ_step = steps
            # 放宽口径与诊断阶梯：反向环境才有这些 key（正向判据本来就不含倾角 ⇒ 无需放宽）。
            # 用 .get 而不是直接下标：正向路径一行行为都不改。
            s_rlx = info.get("success_relaxed", info["success"])
            ever_success_rlx = ever_success_rlx or bool(s_rlx)
            if s_rlx and succ_step_rlx < 0:
                succ_step_rlx = steps
            ever_tipped = ever_tipped or bool(info.get("delivered_tipped", False))
            ever_in_box = ever_in_box or bool(info.get("ever_in_reverse_target", False))
            if "can_tilt_deg" in info:
                final_tilt = float(info["can_tilt_deg"])
            min_dist = min(min_dist, info["dist_to_target_xy"])
            max_lift = max(max_lift, float(info["object_pos"][2]) - z0)
            if args.video and videos < args.max_videos:
                frames.append(env.render(CAM_BASE))
            if terminated or truncated:
                break
        if frames and videos < args.max_videos:
            videos += 1
            try:
                import imageio.v2 as imageio
                imageio.mimwrite(str(out_dir / f"ep{ep}_{'succ' if ever_success else 'fail'}.mp4"),
                                 frames, fps=env.fps)
            except Exception as exc:
                print(f"    [warn] 视频失败：{exc}")
        all_actions.append(np.asarray(ep_actions))
        all_states.append(np.asarray(ep_states))
        tipped = bool(ever_success_rlx and not ever_success)
        per_ep.append({"ep": ep, "seed": seed, "success": ever_success, "success_step": succ_step,
                       "steps": steps, "min_dist_to_target_xy": round(min_dist, 4),
                       "max_lift_cm": round(max_lift * 100, 2),
                       "success_relaxed": bool(ever_success_rlx), "success_step_relaxed": succ_step_rlx,
                       "delivered_tipped": tipped, "ever_in_target_box": bool(ever_in_box),
                       "final_tilt_deg": (round(final_tilt, 2) if final_tilt == final_tilt else None)})
        print(f"  ep{ep} seed={seed} success={ever_success} step={succ_step} steps={steps} "
              f"max_lift={max_lift * 100:.1f}cm min_dist={min_dist * 100:.1f}cm"
              + (f" | 放宽={ever_success_rlx} 侧躺标记={tipped} 末倾角={final_tilt:.0f}°"
                 if args.task_mode == "reverse" else ""), flush=True)

    env.close()
    acts = np.concatenate(all_actions, axis=0)
    summary = {
        "policy_ckpt": str(ckpt),
        "policy_type": type(policy).__name__,
        "chunk_size": chunk_size,
        "n_action_steps": n_action_steps,
        "episodes": args.episodes,
        "seed_mode": args.seed_mode,
        "seed": args.seed,
        "pc_success": float(np.mean([e["success"] for e in per_ep])),
        "n_success": int(np.sum([e["success"] for e in per_ep])),
        # ── 放宽口径（用户 2026-10-02 授权）：同一条轨迹并行判定，不额外花 GPU ──────────
        "pc_success_relaxed": float(np.mean([e["success_relaxed"] for e in per_ep])),
        "n_success_relaxed": int(np.sum([e["success_relaxed"] for e in per_ep])),
        "n_delivered_tipped": int(np.sum([e["delivered_tipped"] for e in per_ep])),
        "n_ever_in_target_box": int(np.sum([e["ever_in_target_box"] for e in per_ep])),
        "avg_steps_to_success": float(np.mean([e["success_step"] for e in per_ep if e["success"]])
                                      if any(e["success"] for e in per_ep) else -1),
        "avg_steps": float(np.mean([e["steps"] for e in per_ep])),
        "seconds": round(time.perf_counter() - t_start, 1),
        "action_stats": {n: {"min": float(acts[:, i].min()), "max": float(acts[:, i].max()),
                             "mean": float(acts[:, i].mean()), "std": float(acts[:, i].std()),
                             "frac_at_plus1": float((acts[:, i] > 0.999).mean()),
                             "frac_at_minus1": float((acts[:, i] < -0.999).mean())}
                         for i, n in enumerate(ACTION_NAMES)},
        "per_episode": per_ep,
        "task": task_str,
        "task_mode": args.task_mode,
        "env_class": type(env).__name__,
        "criterion": {
            "pc_success_is": "strict（历史口径，预注册门用它；本字段语义自 2026-09-30 起未变）",
            "pc_success_relaxed_is": (
                "reverse: 送到 bin1 ±0.09 m 框 ∧ 物理落定(z/速度/夹爪/末端四条不变) ∧ 保持 10 步，"
                "**不要求立着**；forward: 与 strict 相同（正向判据本来就不含倾角项）"),
            "delivered_tipped": "放宽口径算成功但严格口径不算 = 送到了却侧躺/侧挡，按用户要求追加的标记",
            "invariant": "严格 ⊆ 放宽 ⇒ n_success_relaxed ≥ n_success（mg_criterion_selftest.py 钉住）",
            "provenance": "用户 2026-10-02：送到目标位置为首要条件，手臂高度/冲击造成的侧躺也算送到，但要打标",
        },
    }

    if args.demo_npz and Path(args.demo_npz).exists():
        demo = np.load(args.demo_npz)
        d = demo["action"]
        summary["demo_action_stats"] = {n: {"min": float(d[:, i].min()), "max": float(d[:, i].max()),
                                            "mean": float(d[:, i].mean()), "std": float(d[:, i].std()),
                                            "frac_at_plus1": float((d[:, i] > 0.999).mean()),
                                            "frac_at_minus1": float((d[:, i] < -0.999).mean())}
                                        for i, n in enumerate(ACTION_NAMES)}
        summary["demo_npz"] = args.demo_npz

    np.savez_compressed(out_dir / "rollout_actions.npz",
                        action=np.concatenate(all_actions, axis=0),
                        state=np.concatenate(all_states, axis=0),
                        episode_lengths=np.asarray([len(a) for a in all_actions], dtype=np.int32),
                        success=np.asarray([e["success"] for e in per_ep], dtype=bool),
                        success_relaxed=np.asarray([e["success_relaxed"] for e in per_ep], dtype=bool),
                        delivered_tipped=np.asarray([e["delivered_tipped"] for e in per_ep], dtype=bool),
                        final_tilt_deg=np.asarray(
                            [np.nan if e["final_tilt_deg"] is None else e["final_tilt_deg"]
                             for e in per_ep], dtype=np.float32))
    (out_dir / "eval_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\n成功率 pc_success = {summary['pc_success'] * 100:.1f}%  "
          f"({summary['n_success']}/{args.episodes})   用时 {summary['seconds']} s")
    if args.task_mode == "reverse":
        print(f"放宽口径 pc_success_relaxed = {summary['pc_success_relaxed'] * 100:.1f}%  "
              f"({summary['n_success_relaxed']}/{args.episodes})   "
              f"其中侧躺标记 delivered_tipped = {summary['n_delivered_tipped']} 局   "
              f"曾进框 = {summary['n_ever_in_target_box']} 局")
        if summary["n_success_relaxed"] < summary["n_success"]:
            print("[warn] 违背不变量 严格 ⊆ 放宽（relaxed < strict）⇒ 判据实现有 bug，本次读数不可用")
    print("动作分布对照（策略 vs 示范）：")
    for i, name in enumerate(ACTION_NAMES):
        pol = summary["action_stats"][name]
        line = (f"  {name:>8}: policy mean={pol['mean']:+.3f} std={pol['std']:.3f} "
                f"range=[{pol['min']:+.3f},{pol['max']:+.3f}] +1={pol['frac_at_plus1']:.2f} "
                f"-1={pol['frac_at_minus1']:.2f}")
        if "demo_action_stats" in summary:
            dm = summary["demo_action_stats"][name]
            line += (f" | demo mean={dm['mean']:+.3f} std={dm['std']:.3f} "
                     f"range=[{dm['min']:+.3f},{dm['max']:+.3f}] +1={dm['frac_at_plus1']:.2f} "
                     f"-1={dm['frac_at_minus1']:.2f}")
        print(line)
    print(f"[saved] {out_dir / 'eval_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
