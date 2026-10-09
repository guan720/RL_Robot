#!/usr/bin/env python3
"""A 线：解释「截断生效但闭环真值逐位不变」这一类局（只读，逐帧取证）。

为什么需要它：`scripts/a_blown_metric_reconcile.py` 在 k2 seed0 上发现，有局
`norm_input_preclip_absmax` 远超截断电平 C（截断确实生效、`clip_events` 从 300 掉到 158、
逐帧动作有 144 帧不同），但 `max_rise / final_rise / rise_trace / phase_trace` 与未截断产物
**逐位相同**。如果不解释清楚，这看起来像「探针没生效」或「产物是复制的」，两种都会动摇
截断探针的证据力（监管备忘 增补二 §1：截断只作因果探针）。

本脚本用 `--log-actions` 产物把这个机制钉死，判据是三件事同时成立：
  1. 首个动作不同的 tick == `norm_input_first_clamped_frame × replan_every`（截断确实是唯一扰动源）；
  2. `rise_trace` 的峰值 tick **早于**首个不同 tick（决定成败的那一下发生在扰动之前）；
  3. 首个不同 tick 之后两条 `rise_trace` 逐位相同（扰动没有再影响方块）。
成立 ⇒ 该局「截断生效但真值不变」是**时序造成的**，不是探针失效，也不是产物复制。

用法：
    python3 scripts/a_clamp_bound_no_divergence_case.py \
        --plain runs/infra/lerobot_act_env_20260928/clampnochange/k2_seed0_ep5011_plain_logactions.json \
        --clip  runs/infra/lerobot_act_env_20260928/clampnochange/k2_seed0_ep5011_clipC5p0_logactions.json \
        --out   runs/infra/lerobot_act_env_20260928/clampnochange/k2_seed0_ep5011_explained.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser(description="解释「截断生效但闭环真值逐位不变」的局（只读）")
    ap.add_argument("--plain", required=True, help="未截断产物（需 --log-actions）")
    ap.add_argument("--clip", required=True, help="截断探针产物（需 --log-actions）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    plain = json.loads(Path(args.plain).read_text())
    clip = json.loads(Path(args.clip).read_text())
    if len(plain["rows"]) != 1 or len(clip["rows"]) != 1:
        raise SystemExit("[错误] 本脚本按**单局**取证，两份产物都必须只有 1 行")
    a, b = plain["rows"][0], clip["rows"][0]
    if a["seed"] != b["seed"]:
        raise SystemExit(f"[错误] seed 不一致：{a['seed']} vs {b['seed']}")
    for k in ("actions", "rise_trace"):
        if k not in a or k not in b:
            raise SystemExit(f"[错误] 产物缺 {k}，请用 --log-actions 重跑")

    A = np.asarray(a["actions"], dtype=np.float64)
    B = np.asarray(b["actions"], dtype=np.float64)
    rta = np.asarray(a["rise_trace"], dtype=np.float64)
    rtb = np.asarray(b["rise_trace"], dtype=np.float64)
    per_frame = np.abs(A - B).max(axis=1)
    diff_idx = np.nonzero(per_frame > 0)[0]
    first_diff = int(diff_idx[0]) if diff_idx.size else None
    R = int(clip.get("replan_every") or plain.get("replan_every") or 1)
    first_clamped_req = b.get("norm_input_first_clamped_frame")
    first_clamped_tick = None if first_clamped_req is None else int(first_clamped_req) * R
    peak = int(rta.argmax())

    c1 = first_diff is not None and first_clamped_tick is not None and first_diff == first_clamped_tick
    c2 = first_diff is not None and peak < first_diff
    c3 = first_diff is not None and bool(np.array_equal(rta[first_diff:], rtb[first_diff:]))
    explained = bool(c1 and c2 and c3)

    out = {
        "diagnostic": "clamp_bound_but_truth_unchanged_case",
        "read_only": True,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "script": "scripts/a_clamp_bound_no_divergence_case.py",
        "supervision_ref": "监管备忘 2026-09-28 增补三 §12（记录差异原因）",
        "arm": clip.get("checkpoint", {}).get("pretrained_model_dir", "").split("/")[-4] or None,
        "seed": int(a["seed"]),
        "plain_file": str(args.plain),
        "clip_file": str(args.clip),
        "C": (clip.get("execution_constraints") or {}).get("norm_input_clip"),
        "replan_every": R,
        "evidence": {
            "norm_input_absmax_plain": a.get("norm_input_absmax"),
            "norm_input_preclip_absmax_clip": b.get("norm_input_preclip_absmax"),
            "norm_input_blown_frames_frac_plain": a.get("norm_input_blown_frames_frac"),
            "norm_input_preclip_blown_frames_frac_clip": b.get("norm_input_preclip_blown_frames_frac"),
            "norm_input_clamped_frames": b.get("norm_input_clamped_frames"),
            "norm_input_first_clamped_frame_request": first_clamped_req,
            "norm_input_first_clamped_frame_tick": first_clamped_tick,
            "clip_events_action_plain": a.get("clip_events"),
            "clip_events_action_clip": b.get("clip_events"),
            "max_preclip_abs_action_plain": a.get("max_preclip_abs_action"),
            "max_preclip_abs_action_clip": b.get("max_preclip_abs_action"),
            "n_action_frames_differing": int(diff_idx.size),
            "first_action_diff_tick": first_diff,
            "per_dim_max_abs_action_diff": np.round(np.abs(A - B).max(axis=0), 6).tolist(),
            "per_dim_mean_abs_action_diff": np.round(np.abs(A - B).mean(axis=0), 6).tolist(),
            "rise_trace_peak_tick": peak,
            "rise_trace_peak_value": float(rta[peak]),
            "max_rise_plain_vs_clip": [a.get("max_rise"), b.get("max_rise")],
            "final_rise_plain_vs_clip": [a.get("final_rise"), b.get("final_rise")],
            "rise_trace_bitwise_identical_whole_episode": bool(np.array_equal(rta, rtb)),
            "phase_trace_identical": a.get("phase_trace") == b.get("phase_trace"),
        },
        "criteria": {
            "C1_first_action_diff_equals_first_clamped_tick": c1,
            "C2_rise_peak_before_first_diff": c2,
            "C3_rise_trace_identical_after_first_diff": c3,
        },
        "explained": explained,
        "conclusion": (
            "截断是该局唯一的扰动源（首个动作不同的 tick 恰等于首个被截断 request × replan_every）；"
            f"决定成败的抬起峰值出现在 tick {peak}，早于扰动开始的 tick {first_diff}；"
            "扰动之后两条 rise_trace 逐位相同。因此「截断生效但闭环真值不变」是**时序**造成的，"
            "不是探针失效，也不是产物复制——这一局本就不该被算作「截断改变了行为」。"
            if explained else
            "三条判据未全部成立：这一局的「真值不变」不能用时序解释，需要单独查（不得当作探针有效性的证据）。"
        ),
        "generalization": (
            "推论：mean_blown_frames_frac 度量的是**输入越界程度**，不是**行为后果**。"
            "对已经输出饱和/塌缩的 checkpoint，即使 48% 的帧越界、把输入从 93.4 截到 5.0，"
            "闭环真值也可能逐位不变。因此 blown 比例只能作为「测量是否可信」的门禁量，"
            "不能反推「炸穿导致了失败」；后者必须靠截断探针在**逐臂**层面上的行为差异来证。"
        ),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"[截断生效但真值不变] seed={a['seed']} explained={explained}")
    print(f"  C={out['C']} 首个动作不同 tick={first_diff} 首个被截断 tick={first_clamped_tick} 峰值 tick={peak}")
    print(f"  判据 C1/C2/C3 = {c1}/{c2}/{c3}")
    print(f"  动作差异帧数={int(diff_idx.size)} clip_events {a.get('clip_events')}->{b.get('clip_events')} "
          f"rise_trace 全等={out['evidence']['rise_trace_bitwise_identical_whole_episode']}")
    print(f"  写出：{args.out}")
    return 0 if explained else 1


if __name__ == "__main__":
    raise SystemExit(main())
