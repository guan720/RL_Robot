#!/usr/bin/env python3
"""B 线评测器：输出完整《受控成功判据 v1》字段契约，并可注入执行侧动作约束。

与 scripts/eval_act_lift_truth.py 的关系：同一 pinned 题集、同一 ChunkPolicy、同一
runtime 语义（每 K 帧一次 request、逐帧 env.step、记录 activation mask），但

  1. 补齐 v1 要求的 5 个字段：final_rise / held_at_end / phase_at_end / rise_at_success /
     terminal_kind —— 这样 B 自己的臂走**严格**判定，不吃「C5 未评，偏松」的折扣；
  2. 可在执行侧注入单变量约束（--slew-cap / --dz-cap / --action-cap），用于定位 flick 根因。
     这些约束**只作用于下发给 env.step 的命令**，不改 checkpoint、不改训练。

不修改 A 的任何文件；ChunkPolicy / grasp_truth_fn / env 工厂全部 import 复用。
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.env_factory import (PINNED_OBJECT_SEED, contact_object_geom,  # noqa: E402
                                 make_contact_env, reset_contact)
from scripts.probe_contact_ceiling import grasp_truth_fn  # noqa: E402
from scripts.train_act_lift import ChunkPolicy  # noqa: E402

DZ_INDEX = 2


def phase_of(raw, z0):
    """与 scripts/eval_act_lift_truth.py 的 phase() 同口径（不含 step 参数）。"""
    z = float(raw["cube_pos"][2])
    e = np.asarray(raw["robot0_eef_pos"]); c = np.asarray(raw["cube_pos"])
    w = float(np.max(np.abs(raw["robot0_gripper_qpos"])))
    if z > z0 + 0.04:
        return "hold"
    if w > 0.012:
        return "grasp"
    if abs(e[2] - c[2]) < 0.035:
        return "descend"
    return "approach"


def apply_constraints(cmd, prev, slew_cap, action_cap, dz_cap, dz_deadband=None):
    """执行侧单变量约束。返回 (下发命令, 是否被修改, 修改前 inf 范数)。

    dz_deadband：|dz| < tau 时置 0。动机是可辨识性探针
    （runs/infra/b_observability/identifiability_hist1_seed0.json）的实测：
    teacher 的 dz 有 90.9% 的帧恒等于 0（grasp 600 + hold 720 + done 5159 / 7128），
    而 BC 模型在 hold/done 帧上把 dz 预测成 +0.143（= 每控制步 8.8mm 虚假上升），
    因为 lift 与 hold/done 的可观测差异只在 cube_z 绝对值，边界很薄，
    MSE 回归在饱和目标上必然产生泄漏。deadband 用来做**因果验证**：
    若只掐掉泄漏就能把 flick 变成受控成功，则泄漏即根因。
    tau 必须小于 teacher 的 descend 幅度（实测 mean -0.678），否则会把真下降一起掐掉。
    """
    out = np.array(cmd, dtype=np.float64)
    pre = out.copy()
    if action_cap is not None:
        out = np.clip(out, -action_cap, action_cap)
    if dz_cap is not None:
        out[DZ_INDEX] = np.clip(out[DZ_INDEX], -dz_cap, dz_cap)
    if dz_deadband is not None and abs(out[DZ_INDEX]) < dz_deadband:
        out[DZ_INDEX] = 0.0
    if slew_cap is not None and prev is not None:
        lo = np.maximum(prev - slew_cap, -1.0)
        hi = np.minimum(prev + slew_cap, 1.0)
        out = np.clip(out, lo, hi)
    return np.clip(out, -1.0, 1.0).astype(np.float32), bool(not np.allclose(out, pre)), float(np.abs(pre).max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=5000)
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--chunk-length", type=int, default=4)
    ap.add_argument("--history", type=int, default=None)
    ap.add_argument("--slew-cap", type=float, default=None,
                    help="相邻执行帧之间每维 |Δa| 上限；None=不限制")
    ap.add_argument("--action-cap", type=float, default=None, help="全维动作幅度上限")
    ap.add_argument("--dz-cap", type=float, default=None, help="仅 dz 维幅度上限")
    ap.add_argument("--dz-deadband", type=float, default=None,
                    help="|dz|<tau 置 0，用于验证 hold/done 帧的 dz 正泄漏是否为 flick 根因")
    ap.add_argument("--clip-norm-input", type=float, default=None,
                    help="把归一化后的策略输入逐维截到 ±C。用于验证「近常量维被 std 归一化放大」"
                         "是否是闭环发散的根因：state obs 的第 7/9/11 维是 cos(joint0/2/4)，"
                         "teacher 里这些关节几乎不动，std 只有 9.7e-05~9.3e-04，"
                         "训练时归一化 |x| 上界 23.7；闭环一旦偏离 teacher 轨迹，"
                         "这几维就会被放大到 1e3 量级，第一层激活炸穿、tanh 饱和。")
    ap.add_argument("--record-input-blowup", action="store_true",
                    help="逐帧记录归一化输入的逐维 |x| 上界，取证放大效应")
    ap.add_argument("--trace-seeds", default=None,
                    help="逗号分隔的 seed；对这些局逐帧记录 eef_z/cube_z/dz_cmd，用于取证机制")
    ap.add_argument("--label", default=None)
    a = ap.parse_args()

    ck = torch.load(a.ckpt, map_location="cpu", weights_only=False)
    assert int(ck["chunk_length"]) == a.chunk_length, "chunk_length 与 checkpoint 不一致"
    history = int(a.history or ck.get("history", 1))
    model = ChunkPolicy(int(ck["obs_dim"]), a.chunk_length)
    model.load_state_dict(ck["model"]); model.eval()
    mean = np.asarray(ck["obs_mean"], np.float32); std = np.asarray(ck["obs_std"], np.float32)

    env = make_contact_env("lift", horizon=a.horizon, reward_shaping=True, obs_mode="state")
    rows = []
    try:
        for i in range(a.episodes):
            seed = a.seed0 + i
            obs = reset_contact(env, seed)
            raw = env._env._get_observations()
            z0 = float(raw["cube_pos"][2])
            truth = grasp_truth_fn(env, "lift")
            trace_on = (a.trace_seeds is not None and str(seed) in a.trace_seeds.split(","))
            trace = []
            blow = [] if a.record_input_blowup else None
            blown_dim = [] if a.record_input_blowup else None
            raw_success = held_ever = False
            max_rise = 0.0; rise_at_success = None; success_step = None
            frames = 0; requests = 0; phases = []; chunks = []
            hist = []; prev_cmd = None
            events = {"partial": 0, "cancel": 0, "deadline": 0, "constrained_frames": 0}
            max_pre_abs = 0.0
            terminal_kind = "truncated_horizon"
            started = time.perf_counter()
            while frames < a.horizon:
                cur = np.asarray(obs, dtype=np.float32)
                hist.append(cur); hist = hist[-history:]
                while len(hist) < history:
                    hist.insert(0, hist[0].copy())
                xin = (np.concatenate(hist) - mean) / std
                if a.clip_norm_input is not None:
                    xin = np.clip(xin, -a.clip_norm_input, a.clip_norm_input)
                if blow is not None:
                    blow.append(float(np.abs(xin).max()))
                    blown_dim.append(int(np.abs(xin).argmax()))
                with torch.no_grad():
                    chunk = model(torch.tensor(xin[None].astype(np.float32)))[0].numpy()
                n = min(a.chunk_length, a.horizon - frames)
                mask = []; rid = requests
                for j in range(n):
                    cmd, changed, pre_abs = apply_constraints(chunk[j], prev_cmd, a.slew_cap,
                                                              a.action_cap, a.dz_cap,
                                                              a.dz_deadband)
                    if trace_on:
                        trace.append({"frame": frames, "dz_raw": round(float(chunk[j][DZ_INDEX]), 4),
                                      "dz_cmd": round(float(cmd[DZ_INDEX]), 4),
                                      "grip_cmd": round(float(cmd[6]), 4)})
                    prev_cmd = cmd
                    max_pre_abs = max(max_pre_abs, pre_abs)
                    events["constrained_frames"] += int(changed)
                    obs, _, term, trunc, info = env.step(cmd)
                    raw = env._env._get_observations()
                    frames += 1; mask.append(True)
                    rise = float(raw["cube_pos"][2]) - z0
                    max_rise = max(max_rise, rise)
                    if bool(info.get("success", False)):
                        raw_success = True
                        if rise_at_success is None:
                            rise_at_success = rise; success_step = frames
                    held_ever = held_ever or bool(truth())
                    phases.append(phase_of(raw, z0))
                    if trace_on:
                        trace[-1].update({"eef_z": round(float(raw["robot0_eef_pos"][2]), 4),
                                          "cube_z": round(float(raw["cube_pos"][2]), 4),
                                          "rise": round(float(raw["cube_pos"][2]) - z0, 4),
                                          "grip_w": round(float(np.max(np.abs(raw["robot0_gripper_qpos"]))), 4),
                                          "held": bool(truth()), "phase": phases[-1]})
                    if term or trunc:
                        events["cancel"] += 1
                        terminal_kind = "terminated_success" if raw_success else "terminated_failure"
                        break
                if n < a.chunk_length:
                    events["partial"] += 1
                chunks.append({"request_id": rid, "chunk_length": n,
                               "actual_activation_mask": mask, "start_step": frames - len(mask),
                               "phase": phases[-len(mask)] if mask else ""})
                requests += 1
                if term or trunc:
                    break
            held_at_end = bool(truth())
            final_rise = float(raw["cube_pos"][2]) - z0
            rows.append({
                "seed": seed, "success_raw": raw_success, "grasp_verified": held_ever,
                "success_grasp_verified": bool(raw_success and held_ever),
                "success_rise": bool(max_rise >= 0.04),
                "max_rise": round(max_rise, 6), "final_rise": round(final_rise, 6),
                "rise_at_success": (round(rise_at_success, 6) if rise_at_success is not None else None),
                "success_step": success_step, "held_at_end": held_at_end,
                "phase_at_end": (phases[-1] if phases else "unknown"),
                "terminal_kind": terminal_kind,
                "steps": frames, "chunk_count": requests,
                "actual_activation_frames": sum(len(c["actual_activation_mask"]) for c in chunks),
                "partial_events": events["partial"], "cancel_events": events["cancel"],
                "deadline_events": events["deadline"],
                "constrained_frames": events["constrained_frames"],
                "max_preclip_abs_action": round(max_pre_abs, 6),
                "guard_interventions": 0, "recovery_events": 0,
                "elapsed_sec": round(time.perf_counter() - started, 3),
                "phase_trace": phases, "chunks": chunks,
                **({"frame_trace": trace} if trace_on else {}),
                **({"norm_input_absmax": round(max(blow), 3),
                    "norm_input_absmax_median": round(float(np.median(blow)), 3),
                    "norm_input_blown_frames_frac": round(float(np.mean(np.asarray(blow) > 23.7)), 4),
                    "norm_input_top_dim": int(np.bincount(np.asarray(blown_dim)).argmax())}
                   if blow else {}),
            })
            print(f"  seed {seed}: raw={int(raw_success)} grasp={int(held_ever)} "
                  f"max_rise={max_rise:.4f} final_rise={final_rise:.4f} "
                  f"end={rows[-1]['phase_at_end']} term={terminal_kind} "
                  f"constrained={events['constrained_frames']}/{frames}")
        geom = contact_object_geom(env, "lift", PINNED_OBJECT_SEED)
    finally:
        env.close()

    n = len(rows)
    result = {
        "controller": (a.label or "ACT imitation (B v1 evaluator)"),
        "task": "lift", "history": history, "chunk_length": a.chunk_length,
        "ckpt": str(Path(a.ckpt).resolve()),
        "execution_constraints": {"slew_cap": a.slew_cap, "action_cap": a.action_cap,
                                  "dz_cap": a.dz_cap, "dz_deadband": a.dz_deadband},
        "input_constraints": {"clip_norm_input": a.clip_norm_input,
                              "train_time_norm_absmax": 23.7,
                              "note": ("clip_norm_input 属于策略输入预处理，改变的是复合 policy；"
                                       "根因在 scripts/train_act_lift.py 的 `std = x.std(0) + 1e-6`"
                                       "（(x-mean)/std 对近常量维无下限保护）。**内容锚，故意不写行号**："
                                       "旧写法 `:44` 在 A 0929 改动之前就已失效（HEAD 里那行本来在 `:36`，"
                                       "A 改后移到 `:156`）；命中行号由 scripts/b_selfcheck_source_anchors.py "
                                       "现场搜索回显（scripts/b_source_anchor.py）")},
        "episodes": n, "seed0": a.seed0, "horizon": a.horizon,
        "pinned_object_seed": PINNED_OBJECT_SEED, "object_geom": geom,
        "success_raw": sum(r["success_raw"] for r in rows),
        "grasp_verified": sum(r["grasp_verified"] for r in rows),
        "success_grasp_verified": sum(r["success_grasp_verified"] for r in rows),
        "success_rise": sum(r["success_rise"] for r in rows),
        "mean_max_rise": float(np.mean([r["max_rise"] for r in rows])) if rows else 0.0,
        "mean_final_rise": float(np.mean([r["final_rise"] for r in rows])) if rows else 0.0,
        "held_at_end_count": sum(r["held_at_end"] for r in rows),
        "terminal_kind_counts": {k: sum(1 for r in rows if r["terminal_kind"] == k)
                                 for k in sorted({r["terminal_kind"] for r in rows})},
        "failure_phase_counts": {p: sum(1 for r in rows if r["phase_at_end"] == p and not r["success_raw"])
                                 for p in sorted({r["phase_at_end"] for r in rows})},
        "total_constrained_frames": sum(r["constrained_frames"] for r in rows),
        "rows": rows,
    }
    outp = Path(a.out); outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "object_geom")},
                     indent=2, ensure_ascii=False))
    print("写出:", outp)


if __name__ == "__main__":
    main()
