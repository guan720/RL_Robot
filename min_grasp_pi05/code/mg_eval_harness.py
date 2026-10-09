#!/usr/bin/env python
"""最小抓取链路 · 档 5 评测入口（策略 + 监督器接管）。

与 code/mg_eval.py 的关系（房规：mg_eval.py 正被档 3r 链调用，**冻结不许改**）：
    本文件**只 import**（`to_tensor_obs` / `load_policy`）+ 复刻它的记账字段，
    产物 schema 是 mg_eval 的**超集**：eval_summary.json 里 mg_eval 的每个字段语义都不变，
    另加一个 "harness" 块与每局的接管字段；rollout_actions.npz 同样多加 source/trigger 列。
    ⇒ code/mg_tax_fail.py、code/mg_select_ckpt.py 这些读 mg_eval 产物的工具可以直接吃本文件的产物。

三种模式（G0 护栏就是拿它们对拍）：
    默认          检测 + 接管（档 5 的正式读数）
    --observe-only 检测 + 记录，**不接管**（G0b：与基线在二项噪声内一致 ⇒ 套壳没扰动策略路径）
    --detector-off 检测器整个关掉，只留外壳（G0a：与 --observe-only 在同一 --torch-seed 下
                   rollout 动作**逐比特相同** ⇒ 检测器不消耗随机数、不改动作流）

实时性门（≤50 ms/step，20 Hz 预算）只在 `--isolated-timing` 的产物上判：
    与训练/其它评测并发时 ms/step 会被 GPU 争用抬高，拿那种数去判门是自欺欺人。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_eval_harness.py \
        --ckpt runs/pi05_mix60f120r_s2e/checkpoints/022000/pretrained_model \
        --task-mode reverse --episodes 20 --seed-mode random --seed 7000 \
        --n-action-steps 10 --out runs/s5_takeover_rev_test20_k10'
"""

from __future__ import annotations

import argparse
import hashlib
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
    ACTION_DIM, ACTION_KEY, ACTION_NAMES, CAM_BASE, STATE_KEY, STATE_NAMES, TASK, SingleArmGraspEnv,
)
from mg_eval import load_policy, to_tensor_obs  # noqa: E402  （只 import，绝不改 mg_eval.py）
from mg_expert import (  # noqa: E402  （只取常数做 provenance，档 5.1 的停滞阶梯在专家里）
    DESCEND_MAX_RESTAGES, DESCEND_STALL_DZ, DESCEND_STALL_MAX, GIVE_UP_PHASE,
)
from mg_harness import (  # noqa: E402
    HOLD_HI, HOLD_LO, N_EMPTY, N_HOLD, W_EMPTY, GraspDetector, SegmentBuffer, TakeoverHarness,
)

RUNS = MG_ROOT / "runs"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7000)
    ap.add_argument("--seed-mode", choices=("fixed", "random"), default="random")
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--n-action-steps", type=int, default=10, help="档 5 工作点 K=10（档 4r 定的）")
    ap.add_argument("--task-mode", choices=("forward", "reverse"), default="reverse")
    ap.add_argument("--num-inference-steps", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--use-amp", action="store_true")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--max-videos", type=int, default=2)
    ap.add_argument("--demo-npz", default="")
    ap.add_argument("--out", default="")
    # ── 档 5 专有 ────────────────────────────────────────────────────────────
    ap.add_argument("--observe-only", action="store_true", help="G0b：只检测不接管")
    ap.add_argument("--detector-off", action="store_true", help="G0a：检测器整个关掉，只留 harness 外壳")
    ap.add_argument("--min-remain", type=int, default=0,
                    help="剩余步数 < 本值时不接管（默认 0 = 不拦；标定显示拦截会降低救回率，见 harness_calib.md）")
    ap.add_argument("--torch-seed", type=int, default=-1,
                    help="≥0 时按 seed+ep 钉 torch 随机流（只为 G0a 的逐比特对拍；正式读数**不要**开，"
                         "否则与历史基线的采样条件不一致，坑 39）")
    ap.add_argument("--isolated-timing", action="store_true",
                    help="声明本次是隔离跑的（无训练/其它评测并发）⇒ 才允许用它的 ms/step 判实时性门")
    ap.add_argument("--n-empty", type=int, default=N_EMPTY)
    ap.add_argument("--w-empty", type=float, default=W_EMPTY)
    ap.add_argument("--hand-back", action="store_true",
                    help="档 5.1：专家显式认输（descend 停滞阶梯用满 ⇒ unrecoverable）时把控制权交还策略，"
                         "而不是让专家在 give_up 里原地保持到 horizon。默认关 = 档 5 语义。")
    args = ap.parse_args()

    if args.observe_only and args.detector_off:
        print("[err] --observe-only 与 --detector-off 互斥（前者要检测器活着，后者要它死透）", file=sys.stderr)
        return 2
    ckpt = Path(args.ckpt)
    if not ckpt.is_absolute():
        ckpt = MG_ROOT / ckpt
    if not ckpt.exists():
        print(f"[err] 检查点不存在：{ckpt}", file=sys.stderr)
        return 2

    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    mode = "detector_off" if args.detector_off else ("observe_only" if args.observe_only else "takeover")
    out_dir = Path(args.out) if args.out else RUNS / f"s5_{mode}_{datetime.now():%Y%m%d_%H%M%S}"
    if not out_dir.is_absolute():
        out_dir = MG_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    policy, pre, post = load_policy(ckpt, device, args.use_amp)
    chunk_size = int(getattr(policy.config, "chunk_size", -1))
    n_action_steps = int(getattr(policy.config, "n_action_steps", 1) or 1)
    if args.n_action_steps:
        n_action_steps = min(int(args.n_action_steps), chunk_size) if chunk_size > 0 else int(args.n_action_steps)
    policy.config.n_action_steps = n_action_steps
    policy.reset()
    if args.num_inference_steps and hasattr(policy.config, "num_inference_steps"):
        policy.config.num_inference_steps = int(args.num_inference_steps)

    if args.task_mode == "reverse":
        from mg_env_reverse import TASK_REVERSE, ReverseGraspEnv
        from mg_expert_reverse import ReverseScriptedExpert as ExpertCls
        env, task_str = ReverseGraspEnv(img_size=args.img_size), TASK_REVERSE
    else:
        from mg_expert import ScriptedExpert as ExpertCls
        env, task_str = SingleArmGraspEnv(img_size=args.img_size), TASK

    detector = GraspDetector(w_empty=args.w_empty, n_empty=args.n_empty)
    buffer = SegmentBuffer()
    harness = TakeoverHarness(env, ExpertCls, observe_only=args.observe_only,
                              min_remain=args.min_remain, enabled=not args.detector_off,
                              detector=detector, buffer=buffer, hand_back=args.hand_back)

    print(f"[s5] mode={mode} task_mode={args.task_mode} task={task_str!r} env={type(env).__name__} "
          f"horizon={env.horizon} K={n_action_steps} eps={args.episodes} seeds={args.seed_mode}/{args.seed}",
          flush=True)
    print(f"[s5] ckpt={ckpt}", flush=True)
    print(f"[s5] 检测器 w_empty={detector.w_empty} n_empty={detector.n_empty} "
          f"hold=[{detector.hold_lo},{detector.hold_hi}] n_hold={detector.n_hold} "
          f"min_remain={args.min_remain} torch_seed={args.torch_seed} isolated_timing={args.isolated_timing}",
          flush=True)
    print(f"[s5] hand_back={args.hand_back}  专家停滞阶梯 stall_dz={DESCEND_STALL_DZ * 1000:.1f}mm/步 "
          f"stall_max={DESCEND_STALL_MAX} 步 restage上限={DESCEND_MAX_RESTAGES} 认输相位={GIVE_UP_PHASE}"
          f"（常数出处 runs/s5_1_stall_calib_*；阶梯在 mg_expert.py 里，hand_back 关时认输=原地保持到 horizon）",
          flush=True)

    per_ep: list[dict] = []
    all_actions: list[np.ndarray] = []
    all_states: list[np.ndarray] = []
    all_sources: list[np.ndarray] = []
    videos = 0
    t_start = time.perf_counter()
    ms = {"policy": [], "expert": []}

    def policy_act(obs: dict) -> np.ndarray:
        with torch.inference_mode():
            tens = pre(to_tensor_obs(obs, device, task=task_str))
            action = post(policy.select_action(tens))
        act = action.squeeze(0).detach().to("cpu").numpy().astype(np.float32)
        if act.shape[0] != ACTION_DIM:
            raise ValueError(f"策略输出 {act.shape[0]} 维，契约要求 {ACTION_DIM} 维")
        return act

    for ep in range(args.episodes):
        seed = args.seed if args.seed_mode == "fixed" else args.seed + ep
        obs = env.reset(seed=seed)
        if args.torch_seed >= 0:
            torch.manual_seed(int(args.torch_seed) + ep)
        policy.reset()
        can_z0 = float(env.object_pos[2])
        harness.reset(seed=seed, can_z0=can_z0)
        frames: list[np.ndarray] = []
        ep_actions: list[np.ndarray] = []
        ep_states: list[np.ndarray] = []
        ep_sources: list[int] = []
        succ_step, succ_step_rlx, steps = -1, -1, 0
        ever_in_box = False
        final_tilt = float("nan")
        min_dist, max_lift = float("inf"), 0.0
        last_info: dict = {}
        while True:
            t_sel = time.perf_counter()
            act, source = harness.select(obs, steps, lambda: policy_act(obs))
            ms[source].append((time.perf_counter() - t_sel) * 1000.0)
            ep_actions.append(act)
            ep_states.append(obs[STATE_KEY])
            ep_sources.append(1 if source == "expert" else 0)
            obs, _r, terminated, truncated, info = env.step(act)
            steps += 1
            last_info = info
            if info["success"] and succ_step < 0:
                succ_step = steps
            s_rlx = info.get("success_relaxed", info["success"])
            if s_rlx and succ_step_rlx < 0:
                succ_step_rlx = steps
            ever_in_box = ever_in_box or bool(info.get("ever_in_reverse_target", False))
            if "can_tilt_deg" in info:
                final_tilt = float(info["can_tilt_deg"])
            min_dist = min(min_dist, float(info["dist_to_target_xy"]))
            max_lift = max(max_lift, float(info["object_pos"][2]) - can_z0)
            harness.note_success(bool(s_rlx))
            if args.video and videos < args.max_videos:
                frames.append(env.render(CAM_BASE))
            if terminated or truncated:
                break
        if frames and videos < args.max_videos:
            videos += 1
            try:
                import imageio.v2 as imageio
                tag = "succ" if succ_step_rlx > 0 else "fail"
                tk = "tk" if harness.trigger else ("ob" if harness.would_have_fired else "no")
                imageio.mimwrite(str(out_dir / f"ep{ep}_{tag}_{tk}.mp4"), frames, fps=env.fps)
            except Exception as exc:
                print(f"    [warn] 视频失败：{exc}", flush=True)

        hrec = harness.finish(success=bool(succ_step > 0), success_relaxed=bool(succ_step_rlx > 0), steps=steps)
        rec = {"ep": ep, "seed": seed, "success": bool(succ_step > 0), "success_step": succ_step,
               "steps": steps, "min_dist_to_target_xy": round(min_dist, 4),
               "max_lift_cm": round(max_lift * 100, 2),
               "success_relaxed": bool(succ_step_rlx > 0), "success_step_relaxed": succ_step_rlx,
               "delivered_tipped": bool(succ_step_rlx > 0 and succ_step < 0),
               "ever_in_target_box": bool(ever_in_box),
               "final_tilt_deg": (round(final_tilt, 2) if final_tilt == final_tilt else None),
               "can_z0": round(can_z0, 6), "n_expert_steps": int(sum(ep_sources))}
        rec.update(hrec)
        per_ep.append(rec)
        all_actions.append(np.asarray(ep_actions))
        all_states.append(np.asarray(ep_states))
        all_sources.append(np.asarray(ep_sources, dtype=np.int8))
        print(f"  ep{ep} seed={seed} success={rec['success']} step={succ_step} steps={steps} "
              f"max_lift={rec['max_lift_cm']}cm min_dist={rec['min_dist_to_target_xy'] * 100:.1f}cm "
              f"| 放宽={rec['success_relaxed']} 侧躺={rec['delivered_tipped']} "
            f"| 接管={rec['takeover']} 触发={rec['trigger']} 步={rec['takeover_step']} "
            f"剩余={rec['takeover_remain']} 专家相位={'->'.join(rec['expert_phases'])} "
              f"(观察模式本来会触发={rec['would_have_fired']}@{rec['would_have_step']})"
              + (f" 交还={rec['handback']}@{rec['handback_step']} 剩余={rec['handback_remain']} "
                 f"restages={rec['n_restages']}" if rec.get("handback") else ""), flush=True)

    env.close()
    acts = np.concatenate(all_actions, axis=0)
    n_tk = int(sum(e["takeover"] for e in per_ep))
    n_fire = int(sum(e["would_have_fired"] is not None for e in per_ep))
    trig = {}
    for e in per_ep:
        key = e["trigger"] or e["would_have_fired"] or "none"
        trig[key] = trig.get(key, 0) + 1
    summary = {
        "policy_ckpt": str(ckpt),
        "policy_type": type(policy).__name__,
        "chunk_size": chunk_size,
        "n_action_steps": n_action_steps,
        "episodes": args.episodes,
        "seed_mode": args.seed_mode,
        "seed": args.seed,
        "seeds_used": [e["seed"] for e in per_ep],
        "pc_success": float(np.mean([e["success"] for e in per_ep])),
        "n_success": int(np.sum([e["success"] for e in per_ep])),
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
            "pc_success_is": "strict（历史口径；本字段语义自 2026-09-30 起未变）",
            "pc_success_relaxed_is": ("reverse: 送到 bin1 ±0.09 m 框 ∧ 物理落定 ∧ 保持 10 步，不要求立着；"
                                      "forward: 与 strict 相同"),
            "delivered_tipped": "放宽成功但严格不成功 = 送到了却侧躺/侧挡（用户 2026-10-02 要求追加的标记）",
            "provenance": "与 mg_eval.py 同一套判据字段，本文件不重新定义成功",
        },
        "harness": {
            "mode": mode,
            "rule": ("连续 n_empty 步 gripper_width ≤ w_empty 且本局未判成功 ⇒ 触发；"
                     "触发前是否出现过 ≥n_hold 步落在 [hold_lo,hold_hi] 决定标签 T1(抓空)/T3(滑脱)"),
            "inputs": "只用 state[:,7] = gripper_width（本体感觉，不用 can 位姿真值）",
            "w_empty": detector.w_empty, "n_empty": detector.n_empty,
            "hold_lo": detector.hold_lo, "hold_hi": detector.hold_hi, "n_hold": detector.n_hold,
            "min_remain": args.min_remain,
            "expert": ExpertCls.__name__,
            "takeover_policy": ("一局只接管一次；专家认输（unrecoverable）时交还策略、本局不再二次接管"
                                if args.hand_back else
                                "一局只接管一次，接管后专家跑到本局结束（不回交，便于归因）"),
            "hand_back": bool(args.hand_back),
            "stall_ladder": {"descend_stall_dz": DESCEND_STALL_DZ, "descend_stall_max": DESCEND_STALL_MAX,
                             "descend_max_restages": DESCEND_MAX_RESTAGES, "give_up_phase": GIVE_UP_PHASE,
                             "source": "runs/s5_1_stall_calib_clean_rev / _clean_fwd / _trace（两侧标定）",
                             "note": ("阶梯在 mg_expert.py 里，hand_back=False 时认输 = 原地保持 + 开爪到 horizon；"
                                      "G1 逐比特回归证明干净专家跑一次都不触发（runs/s5_1_g1_ceiling_rev_test20_n05）")},
            "n_handback": int(sum(bool(e.get("handback")) for e in per_ep)),
            "handback_rate": int(sum(bool(e.get("handback")) for e in per_ep)) / max(1, args.episodes),
            "n_unrecoverable": int(sum(bool(e.get("unrecoverable")) for e in per_ep)),
            "restages_total": int(sum(int(e.get("n_restages") or 0) for e in per_ep)),
            "n_deadloop_ge100": int(sum(bool(e["takeover"]) and "grasp" not in (e.get("expert_phases") or [])
                                        and int(e.get("seg_len") or 0) >= 100 for e in per_ep)),
            "n_takeover": n_tk,
            "takeover_rate": n_tk / max(1, args.episodes),
            "n_would_have_fired": n_fire,
            "would_fire_rate": n_fire / max(1, args.episodes),
            "trigger_counts": trig,
            "n_segments": len(buffer.episodes),
            "segment_steps": int(sum(e["seg_len"] for e in buffer.episodes)),
            "rescued": int(sum(e["takeover"] and e["success_relaxed"] for e in per_ep)),
            "took_over_and_failed": int(sum(e["takeover"] and not e["success_relaxed"] for e in per_ep)),
            "ms_per_step": {k: (round(float(np.mean(v)), 2) if v else None) for k, v in ms.items()}
                           | {"all": round(float(np.mean(ms["policy"] + ms["expert"])), 2)
                              if (ms["policy"] or ms["expert"]) else None},
            "n_steps_policy": len(ms["policy"]), "n_steps_expert": len(ms["expert"]),
            "timing_isolated": bool(args.isolated_timing),
            "timing_note": ("≤50 ms/step 的门只在 timing_isolated=true 的产物上判；"
                            "并发跑的数只能当参考"),
            "torch_seed": args.torch_seed,
            "calibration": {"source": "runs/_diag/harness_calib.md",
                            "tool": "code/mg_calib_detector.py",
                            "corpus": "档 2 反向 TEST 240 局（档 5 开工前就存在）"},
            "code_sha256_16": {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest()[:16]
                               for f in ("mg_harness.py", "mg_calib_detector.py", "mg_expert.py",
                                         "mg_expert_reverse.py", "mg_env.py", "mg_env_reverse.py",
                                         "mg_eval.py", "mg_eval_harness.py")},
        },
    }
    if args.demo_npz and Path(args.demo_npz).exists():
        summary["demo_npz"] = args.demo_npz

    np.savez_compressed(out_dir / "rollout_actions.npz",
                        action=acts,
                        state=np.concatenate(all_states, axis=0),
                        episode_lengths=np.asarray([len(a) for a in all_actions], dtype=np.int32),
                        source=np.concatenate(all_sources, axis=0),
                        success=np.asarray([e["success"] for e in per_ep], dtype=bool),
                        success_relaxed=np.asarray([e["success_relaxed"] for e in per_ep], dtype=bool),
                        delivered_tipped=np.asarray([e["delivered_tipped"] for e in per_ep], dtype=bool),
                        takeover=np.asarray([e["takeover"] for e in per_ep], dtype=bool),
                        takeover_step=np.asarray([e["takeover_step"] for e in per_ep], dtype=np.int32),
                        final_tilt_deg=np.asarray([np.nan if e["final_tilt_deg"] is None else e["final_tilt_deg"]
                                                   for e in per_ep], dtype=np.float32))
    seg = buffer.dump()
    if seg:
        np.savez_compressed(out_dir / "correction_segments_raw.npz", **seg)
    (out_dir / "eval_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\n严格 pc_success = {summary['pc_success'] * 100:.1f}% ({summary['n_success']}/{args.episodes})  "
          f"放宽 = {summary['pc_success_relaxed'] * 100:.1f}% ({summary['n_success_relaxed']}/{args.episodes})",
          flush=True)
    print(f"[s5] mode={mode} 接管 {n_tk}/{args.episodes} = {summary['harness']['takeover_rate'] * 100:.1f}%  "
          f"触发计数={trig}  接管后成功={summary['harness']['rescued']}  接管后仍失败="
          f"{summary['harness']['took_over_and_failed']}", flush=True)
    print(f"[s5] ms/step 策略={summary['harness']['ms_per_step']['policy']} "
          f"专家={summary['harness']['ms_per_step']['expert']} "
          f"（isolated={summary['harness']['timing_isolated']}）", flush=True)
    print(f"[s5] 纠正片段 {summary['harness']['n_segments']} 段 / "
          f"{summary['harness']['segment_steps']} 步 -> {out_dir / 'correction_segments_raw.npz'}", flush=True)
    if summary["n_success_relaxed"] < summary["n_success"]:
        print("[warn] 违背不变量 严格 ⊆ 放宽 ⇒ 判据实现有 bug，本次读数不可用", flush=True)
    print(f"[saved] {out_dir / 'eval_summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
