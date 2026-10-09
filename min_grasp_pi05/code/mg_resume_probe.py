#!/usr/bin/env python
"""档 5 预检 · resume() 在**真物理**里能不能把任务做完（不用策略、不用 GPU 推理，只要仿真）。

为什么自测不够：mg_expert_resume_selftest.py 只能钉住「相位标签推得对」，
但档 5 真正要的是「接管之后还能把 can 送进托盘」。这两件事之间隔着控制器、
夹爪动力学、can 的掉落姿态 —— 只有真跑一遍才知道。这条探针就是那道闸：
它不通过，档 5 的读数无论多好看都不可信（救回率会被 resume 的无能吃掉）。

三种接管场景，对应检测器的两个触发与档 2 量出来的失败机理：
  carry      正常专家跑到第 t 步 ⇒ 换新专家 resume 续跑（最理想情形：can 还夹着）
  slip       跑到第 t 步后**强制张爪**若干步让 can 掉下去 ⇒ resume（对应 T3 滑脱）
  graspfail  前 t 步**强制张爪**（永远抓不到）⇒ resume（对应 T1 抓空：can 还在原位、末端在附近乱晃）

判据（每个场景都要过）：
  * resume 推断出的相位必须与场景相符（carry ⇒ carry/lift；slip/graspfail ⇒ approach/descend/grasp）
  * 从 resume 那一刻到严格成功所用的步数 ≤ 剩余步数（否则接管了也做不完，这是档 5 的可行性天花板）
  * 放宽口径成功

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_resume_probe.py --seeds 7000,7001,7002,7003,7004 \
        --resume-at 100,160 --out runs/s5_resume_probe'
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

RUNS = MG_ROOT / "runs"
SLIP_SETTLE = 15   # 强制张爪之后留给 can 落地/静止的步数，然后才 resume（真实检测器只晚 3 步，
                   # 这里多留一点是为了让「can 已经躺在桌上」这个前提成立，量出来的是保守成本）


def run_one(env, expert_cls, seed: int, mode: str, t_resume: int, slip_steps: int,
            noise: float, rng) -> dict:
    """跑一局：前段按 mode 处理，第 t_resume 步换新专家 resume，然后跑到结束。"""
    env.reset(seed=seed)
    can_z0 = float(env.object_pos[2])
    expert = expert_cls(env).reset()
    succ_step, succ_step_rlx, steps = -1, -1, 0
    resume_phase, resume_at_step, steps_after_resume = None, -1, -1
    max_lift, min_dist = 0.0, float("inf")
    expert2 = None
    info: dict = {}
    while steps < env.horizon:
        if steps == t_resume and expert2 is None:
            expert2 = expert_cls(env).resume(can_z0=can_z0)
            resume_phase = expert2.phase
            resume_at_step = steps
        use = expert2 if expert2 is not None else expert
        act = np.asarray(use(), dtype=np.float32)
        # 场景注入：强制张爪（-1 = 张开，mg_probe --gripper 实测语义）。
        # ⚠️ 注入窗口必须在 resume **之前**结束：真实 harness 里 T3 是「宽度已经掉到空合 3 步之后」
        # 才触发的，也就是 can 已经掉了、专家接手时爪子是自由的。第一版把注入窗口放在 resume 之后，
        # 等于一边让专家救、一边按住它的爪子不让合 ⇒ 量出来的续跑成本是假的（实测偏低）。
        forcing = False
        if mode == "graspfail" and steps < t_resume:
            forcing = True
        elif mode == "slip" and t_resume - slip_steps - SLIP_SETTLE <= steps < t_resume - SLIP_SETTLE:
            forcing = True
        if forcing:
            act[6] = -1.0
        if noise > 0.0:
            act[:3] = np.clip(act[:3] + rng.normal(0.0, noise, size=3), -1.0, 1.0)
        _o, _r, terminated, truncated, info = env.step(act)
        steps += 1
        if expert2 is not None and steps_after_resume < 0:
            steps_after_resume = 0
        if expert2 is not None:
            steps_after_resume += 1
        if info["success"] and succ_step < 0:
            succ_step = steps
        s_rlx = info.get("success_relaxed", info["success"])
        if s_rlx and succ_step_rlx < 0:
            succ_step_rlx = steps
        max_lift = max(max_lift, float(info["object_pos"][2]) - can_z0)
        min_dist = min(min_dist, float(info["dist_to_target_xy"]))
        if terminated or truncated:
            break
    return {"seed": seed, "mode": mode, "t_resume": t_resume, "slip_steps": slip_steps,
            "resume_phase": resume_phase, "resume_at_step": resume_at_step,
            "steps": steps, "steps_after_resume": steps_after_resume,
            "remain_at_resume": env.horizon - t_resume,
            "cost_to_success": (succ_step - t_resume) if succ_step > 0 else -1,
            "success": bool(succ_step > 0), "success_relaxed": bool(succ_step_rlx > 0),
            "success_step": succ_step, "max_lift_cm": round(max_lift * 100, 2),
            "min_dist_cm": round(min_dist * 100, 2),
            "final_tilt_deg": round(float(info.get("can_tilt_deg", float("nan"))), 2),
            "expert_phases": list(dict.fromkeys(expert2.log)) if expert2 is not None else []}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="7000,7001,7002,7003,7004")
    ap.add_argument("--resume-at", default="100,160", help="在第几步接管（逗号分隔）")
    ap.add_argument("--slip-steps", type=int, default=12, help="slip 场景强制张爪的步数")
    ap.add_argument("--modes", default="carry,slip,graspfail")
    ap.add_argument("--noise", type=float, default=0.0, help="0 = 确定性（默认）；>0 复现采集时的动作噪声")
    ap.add_argument("--task-mode", choices=("forward", "reverse"), default="reverse")
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--baseline", action="store_true", help="同时跑不接管的基线（同 seed 对照）")
    ap.add_argument("--out", default="runs/s5_resume_probe")
    args = ap.parse_args()

    if args.task_mode == "reverse":
        from mg_env_reverse import ReverseGraspEnv
        from mg_expert_reverse import ReverseScriptedExpert as ExpertCls
        env = ReverseGraspEnv(img_size=args.img_size)
    else:
        from mg_env import SingleArmGraspEnv as EnvCls
        from mg_expert import ScriptedExpert as ExpertCls
        env = EnvCls(img_size=args.img_size)

    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    resumes = [int(x) for x in args.resume_at.split(",") if x.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    rng = np.random.default_rng(12345)
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = MG_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[probe] task_mode={args.task_mode} env={type(env).__name__} expert={ExpertCls.__name__} "
          f"horizon={env.horizon} noise={args.noise}", flush=True)
    print(f"[probe] seeds={seeds} resume_at={resumes} modes={modes} slip_steps={args.slip_steps}", flush=True)
    t0 = time.perf_counter()
    rows: list[dict] = []
    if args.baseline:
        for sd in seeds:
            r = run_one(env, ExpertCls, sd, "baseline", env.horizon + 1, 0, args.noise, rng)
            r["mode"] = "baseline"
            rows.append(r)
            print(f"  [baseline] seed={sd} 严格={r['success']} 放宽={r['success_relaxed']} "
                  f"成功步={r['success_step']} 总步={r['steps']}", flush=True)
    for mode in modes:
        for t in resumes:
            for sd in seeds:
                r = run_one(env, ExpertCls, sd, mode, t, args.slip_steps, args.noise, rng)
                rows.append(r)
                print(f"  [{mode:>9} t={t:>3}] seed={sd} resume相位={r['resume_phase']:<8} "
                      f"严格={r['success']} 放宽={r['success_relaxed']} "
                      f"接管后到成功={r['cost_to_success']} 步（剩余 {r['remain_at_resume']}）"
                      f" 末倾角={r['final_tilt_deg']}° 相位={'->'.join(r['expert_phases'])}", flush=True)
    env.close()

    # ── 汇总与判据 ──────────────────────────────────────────────────────────
    per_mode: dict[str, dict] = {}
    for mode in sorted({r["mode"] for r in rows}):
        sub = [r for r in rows if r["mode"] == mode]
        n = len(sub)
        per_mode[mode] = {
            "n": n,
            "strict": int(sum(r["success"] for r in sub)),
            "relaxed": int(sum(r["success_relaxed"] for r in sub)),
            "cost_median": float(np.median([r["cost_to_success"] for r in sub if r["cost_to_success"] > 0])
                                 if any(r["cost_to_success"] > 0 for r in sub) else -1),
            "cost_max": int(max([r["cost_to_success"] for r in sub] + [-1])),
            "over_budget": int(sum(r["cost_to_success"] > r["remain_at_resume"]
                                   for r in sub if r["cost_to_success"] > 0)),
            "resume_phases": sorted({str(r["resume_phase"]) for r in sub}),
        }
    print("\n[probe] === 汇总 ===", flush=True)
    for mode, s in per_mode.items():
        print(f"  {mode:>9}: n={s['n']} 严格 {s['strict']}/{s['n']} 放宽 {s['relaxed']}/{s['n']} "
              f"接管后到成功 中位={s['cost_median']:.0f} max={s['cost_max']} "
              f"超出剩余预算={s['over_budget']} 局  相位={s['resume_phases']}", flush=True)

    # 相位合理性判据：carry 场景必须判成夹持类相位；slip/graspfail 必须判成重新接近类相位
    HOLD_PHASES = {"carry", "lift"}
    REGain_PHASES = {"approach", "descend", "grasp"}
    bad = []
    for r in rows:
        if r["mode"] == "carry" and r["resume_phase"] not in HOLD_PHASES | {"settle", "place_descend"}:
            bad.append((r, f"carry 场景应判夹持类相位，实得 {r['resume_phase']}"))
        if r["mode"] in ("slip", "graspfail") and r["resume_phase"] not in (REGain_PHASES | HOLD_PHASES):
            bad.append((r, f"{r['mode']} 场景相位 {r['resume_phase']} 不在允许集内"))
    for r, why in bad:
        print(f"  [warn] seed={r['seed']} mode={r['mode']} t={r['t_resume']}: {why}", flush=True)

    summary = {
        "kind": "resume_probe",
        "generated": datetime.now().strftime("%F %T"),
        "task_mode": args.task_mode, "env_class": type(env).__name__, "expert": ExpertCls.__name__,
        "horizon": int(env.horizon), "noise": args.noise, "seeds": seeds,
        "resume_at": resumes, "modes": modes, "slip_steps": args.slip_steps,
        "per_mode": per_mode, "rows": rows,
        "phase_violations": [{"seed": r["seed"], "mode": r["mode"], "t_resume": r["t_resume"],
                              "resume_phase": r["resume_phase"], "why": w} for r, w in bad],
        "code_sha256_16": {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest()[:16]
                           for f in ("mg_expert.py", "mg_expert_reverse.py", "mg_env.py",
                                     "mg_env_reverse.py", "mg_resume_probe.py")},
        "note": ("档 5 预检：resume() 在真物理里能否把任务做完。cost_to_success = 严格成功步 - 接管步；"
                 "over_budget > 0 说明接管太晚（剩余步数不够），档 5 的可行性天花板由它决定"),
    }
    (out_dir / "resume_probe.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[probe] 用时 {time.perf_counter() - t0:.1f} s  -> {out_dir / 'resume_probe.json'}", flush=True)
    if bad:
        print(f"[probe] ⚠️ {len(bad)} 处相位推断与场景不符（不一定致命，但要在档 5 判定里说明）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
