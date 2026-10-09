#!/usr/bin/env python
"""最小抓取链路 · 脚本专家「上界」评测（正向 / 反向同一口径、同一 seed 序列）。

为什么要单独一个工具（档 2 的门需要它）：
  * 档 2 的门是「正、反各 ≥ 50%（未见 seed ×20）」，但**反向的可行初态域比正向小**
    （mg_probe_reverse.py --feasible 实测 dx∈[-0.08,+0.02] dy∈[-0.05,+0.05]，抖动框还取了内接保守框），
    专家自己在 σ=0.05 噪声下也只有 9/12 = 75%。策略天花板本来就不是 100%，
    没有同 seed 的上界，「50%」这个数就没有解释力。
  * 现有两个探针口径不齐：mg_probe.py --expert 只跑固定初态、无噪声、无 seed-base；
    mg_probe_reverse.py --expert 能跑随机 seed + 噪声但只有反向。
    本工具把两边统一：--task-mode {forward,reverse} × 与 mg_eval.py **完全相同的 seed 规则**
    （random 模式 seed = --seed + ep），于是「上界 vs 策略」是逐局可对齐的。
  * 隔离纪律：只 import（不改）mg_env / mg_expert / mg_env_reverse / mg_expert_reverse，
    因此不会影响正在跑的档 1 评测进程。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_ceiling.py --task-mode reverse \
        --episodes 20 --seed-mode random --seed 7000 --noise 0.05 \
        --out runs/s2_ceiling_rev_test20'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_env import (  # noqa: E402
    CAM_BASE, TASK, SingleArmGraspEnv,
)

RUNS = MG_ROOT / "runs"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task-mode", choices=("forward", "reverse"), default="forward")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed-mode", choices=("fixed", "random"), default="random")
    ap.add_argument("--seed", type=int, default=2000, help="random 模式下 seed = 本值 + ep（与 mg_eval.py 同规则）")
    ap.add_argument("--noise", type=float, default=0.05,
                    help="加在专家动作前 3 维上的高斯 σ（与采集端 --expert-noise 同义）；0 = 无噪声上界")
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--max-videos", type=int, default=1)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.task_mode == "reverse":
        from mg_env_reverse import TASK_REVERSE, ReverseGraspEnv
        from mg_expert_reverse import ReverseScriptedExpert as ExpertCls
        env, task_str = ReverseGraspEnv(img_size=args.img_size), TASK_REVERSE
    else:
        from mg_expert import ScriptedExpert as ExpertCls
        env, task_str = SingleArmGraspEnv(img_size=args.img_size), TASK

    # 噪声流钉死：与采集端一致用 default_rng(12345)，所以同一组参数重跑 = 逐比特相同的上界。
    rng = np.random.default_rng(12345)
    out_dir = Path(args.out) if args.out else RUNS / f"ceiling_{args.task_mode}_{args.seed}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[ceiling] task_mode={args.task_mode} expert={ExpertCls.__name__} "
          f"env={type(env).__name__} task={task_str!r} horizon={env.horizon} "
          f"seeds={args.seed_mode}/{args.seed} eps={args.episodes} noise_sigma={args.noise}", flush=True)

    per_ep: list[dict] = []
    videos = 0
    t0 = time.perf_counter()
    for ep in range(args.episodes):
        seed = args.seed if args.seed_mode == "fixed" else args.seed + ep
        env.reset(seed=seed)
        expert = ExpertCls(env).reset()
        frames: list[np.ndarray] = []
        want_frames = args.video and videos < args.max_videos
        succ_step, steps, max_lift, min_dist = -1, 0, 0.0, float("inf")
        succ_step_rlx = -1
        ever_in_box = False
        z0 = float(env.object_pos[2])
        last_info: dict = {}
        while steps < env.horizon:
            act = np.asarray(expert(), dtype=np.float32)
            if args.noise > 0.0:
                act[:3] = np.clip(act[:3] + rng.normal(0.0, args.noise, size=3), -1.0, 1.0)
            _o, _r, terminated, truncated, info = env.step(act)
            steps += 1
            last_info = info
            if info["success"] and succ_step < 0:
                succ_step = steps
            s_rlx = info.get("success_relaxed", info["success"])
            if s_rlx and succ_step_rlx < 0:
                succ_step_rlx = steps
            ever_in_box = ever_in_box or bool(info.get("ever_in_reverse_target", False))
            max_lift = max(max_lift, float(info["object_pos"][2]) - z0)
            min_dist = min(min_dist, float(info["dist_to_target_xy"]))
            if want_frames:
                frames.append(env.render(CAM_BASE))
            if terminated or truncated:
                break
        if frames:
            videos += 1
            try:
                import imageio.v2 as imageio
                imageio.mimwrite(str(out_dir / f"ep{ep}_{'succ' if succ_step > 0 else 'fail'}.mp4"),
                                 frames, fps=env.fps)
            except Exception as exc:
                print(f"    [warn] 视频写入失败：{exc}", flush=True)
        rec = {"ep": ep, "seed": seed, "success": bool(succ_step > 0), "success_step": succ_step,
               "steps": steps, "max_lift_cm": round(max_lift * 100, 2),
               "min_dist_to_target_cm": round(min_dist * 100, 2),
               "phases": list(expert.phase_seq), "regrasp": int(expert.regrasp), "slip": int(expert.slip)}
        rec["success_relaxed"] = bool(succ_step_rlx > 0)
        rec["success_step_relaxed"] = succ_step_rlx
        rec["delivered_tipped"] = bool(succ_step_rlx > 0 and succ_step < 0)
        rec["ever_in_target_box"] = bool(ever_in_box)
        if args.task_mode == "reverse":
            rec["final_tilt_deg"] = round(float(last_info.get("can_tilt_deg", float("nan"))), 2)
            rec["hold"] = int(last_info.get("hold", -1))
            rec["hold_relaxed"] = int(last_info.get("hold_relaxed", -1))
        per_ep.append(rec)
        print(f"  ep{ep} seed={seed} success={rec['success']} step={succ_step} steps={steps} "
              f"max_lift={rec['max_lift_cm']}cm min_dist={rec['min_dist_to_target_cm']}cm"
              + (f" tilt={rec['final_tilt_deg']}°" if args.task_mode == "reverse" else "")
              + (f" | 放宽={rec['success_relaxed']} 侧躺标记={rec['delivered_tipped']}"
                 if args.task_mode == "reverse" else "")
              + f" regrasp={rec['regrasp']} phases={'->'.join(rec['phases'])}", flush=True)

    env.close()
    n_ok = int(sum(e["success"] for e in per_ep))
    n_ok_rlx = int(sum(e["success_relaxed"] for e in per_ep))
    n_tipped = int(sum(e["delivered_tipped"] for e in per_ep))
    summary = {
        "kind": "expert_ceiling",
        "task_mode": args.task_mode,
        "task": task_str,
        "expert": ExpertCls.__name__,
        "env_class": type(env).__name__,
        "episodes": args.episodes,
        "seed_mode": args.seed_mode,
        "seed": args.seed,
        "seeds_used": [e["seed"] for e in per_ep],
        "noise_sigma": args.noise,
        "pc_success": n_ok / max(1, args.episodes),
        "n_success": n_ok,
        "pc_success_relaxed": n_ok_rlx / max(1, args.episodes),
        "n_success_relaxed": n_ok_rlx,
        "n_delivered_tipped": n_tipped,
        "n_ever_in_target_box": int(sum(e["ever_in_target_box"] for e in per_ep)),
        "avg_steps": float(np.mean([e["steps"] for e in per_ep])),
        "seconds": round(time.perf_counter() - t0, 1),
        "per_episode": per_ep,
        "code_sha256_16": {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest()[:16]
                           for f in ("mg_env.py", "mg_expert.py", "mg_env_reverse.py", "mg_expert_reverse.py")},
        "note": "脚本专家上界，与 mg_eval.py 同 seed 规则（random: seed = --seed + ep），可逐局对齐策略结果",
        "criterion": {
            "pc_success_is": "strict（历史口径；本字段语义自 2026-09-30 起未变）",
            "pc_success_relaxed_is": "reverse: 落定但不要求立着；forward: 与 strict 相同",
            "provenance": "用户 2026-10-02 放宽口径；上界必须与策略用**同一口径**比，否则分母是错的",
        },
    }
    (out_dir / "ceiling_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n专家上界 pc_success = {summary['pc_success'] * 100:.1f}%  ({n_ok}/{args.episodes})  "
          f"noise_sigma={args.noise}  用时 {summary['seconds']} s")
    if args.task_mode == "reverse":
        print(f"放宽口径专家上界 = {summary['pc_success_relaxed'] * 100:.1f}%  "
              f"({n_ok_rlx}/{args.episodes})   其中侧躺标记 {n_tipped} 局")
    print(f"[saved] {out_dir / 'ceiling_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
