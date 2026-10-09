#!/usr/bin/env python3
"""按 teacher 相位分解官方 ACT 的动作预测偏差（只读、开环、非闭环成功）。

为什么需要它：`scripts/audit_lerobot_act_overfit.py` 只报全 300 帧的 mean|err|，而源数据里
`done` 相位占 72.5%（teacher 恒输出 `[0,0,0,0,0,0,+1]`）、真正的 `lift` 帧只占 2.3%，
整体误差被「什么都不做」的多数帧主导，看不出抬起信号学得怎样。本脚本把预测误差按
teacher 相位（approach / descend / grasp / lift / hold / done）分组，并对 dz 报**带符号**
偏差与「是否真的在命令抬起」（`pred_dz >= 0.5` 的帧占比），用来区分三种失败：
  1. dz 系统性偏小（回归到均值）  -> 数据配比 / 损失权重问题
  2. dz 符号学反                  -> 归一化或 gripper/dz 耦合问题
  3. dz 学对了但闭环抬不起来      -> 执行侧（chunk 开环时长 / 控制频率）问题

推理链路照官方 `select_action`（内部按 `n_action_steps` 缓冲 chunk），与闭环评测同一口径；
不训练、不写 checkpoint、不改任何实现文件。

用法：
    /root/venvs/lerobot_eval/bin/python scripts/audit_lerobot_act_lift_frames.py \
        --src-episode runs/infra/lerobot_act_lift_state_overfit/data/episode_0000.npz \
        --ckpt runs/infra/lerobot_act_lift_v30/train24_lr1e-5_actionminmax_s20k \
               runs/infra/lerobot_act_lift_v30/trimdone0_minmax_lr1e-5_s20k_seed0 \
        --out runs/infra/lerobot_act_env_20260928/lift_frames_dz_audit.json
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._lerobot_act import load_official_act, resolve_pretrained_dir, sha256_file  # noqa: E402

STATE_DIM = 50
ENV_DIM = 10
ACTION_DIM = 7
DIM_NAMES = ["dx", "dy", "dz", "droll", "dpitch", "dyaw", "gripper"]
DZ = 2
GRIP = 6
LIFT_CMD_THRESHOLD = 0.5
TASK_PHASES = ["approach", "descend", "grasp", "lift", "hold"]


def obs_dict(torch, state50: np.ndarray, env10: np.ndarray) -> dict:
    return {
        "observation.state": torch.from_numpy(np.ascontiguousarray(state50, dtype=np.float32)),
        "observation.environment_state": torch.from_numpy(np.ascontiguousarray(env10, dtype=np.float32)),
    }


def to_np(torch, x) -> np.ndarray:
    if isinstance(x, torch.Tensor):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def group_stats(pred: np.ndarray, teacher: np.ndarray, phases: np.ndarray, name: str) -> dict:
    """一个相位组内的动作预测统计（带符号偏差 + 是否真在命令抬起）。"""
    n = int(len(pred))
    if n == 0:
        return {"phase": name, "frames": 0}
    signed = pred - teacher
    dz_t, dz_p = teacher[:, DZ], pred[:, DZ]
    lift_frames = dz_t >= LIFT_CMD_THRESHOLD
    return {
        "phase": name,
        "frames": n,
        "share_of_episode": round(n / float(len(phases)), 4),
        "mean_abs_err_all_dims": round(float(np.abs(signed).mean()), 6),
        "dz_teacher_mean": round(float(dz_t.mean()), 6),
        "dz_pred_mean": round(float(dz_p.mean()), 6),
        "dz_signed_bias": round(float(signed[:, DZ].mean()), 6),
        "dz_mean_abs_err": round(float(np.abs(signed[:, DZ]).mean()), 6),
        "dz_teacher_lift_frames": int(lift_frames.sum()),
        "dz_pred_lift_cmd_rate": (round(float((dz_p[lift_frames] >= LIFT_CMD_THRESHOLD).mean()), 4)
                                  if int(lift_frames.sum()) else None),
        "dz_pred_mean_on_teacher_lift_frames": (round(float(dz_p[lift_frames].mean()), 6)
                                                if int(lift_frames.sum()) else None),
        "grip_sign_agreement": round(float((np.sign(pred[:, GRIP]) == np.sign(teacher[:, GRIP])).mean()), 4),
        "per_dim_mean_abs_err": {DIM_NAMES[d]: round(float(np.abs(signed[:, d]).mean()), 6)
                                 for d in range(ACTION_DIM)},
    }


def audit_one(ckpt: str, obs: np.ndarray, teacher: np.ndarray, phases: np.ndarray,
              device: str | None) -> dict:
    torch, cfg, policy, pre, post, pm_dir = load_official_act(ckpt, device=device)
    policy.reset()
    pred = np.zeros_like(teacher)
    for t in range(len(obs)):
        batch = pre(obs_dict(torch, obs[t, :STATE_DIM], obs[t, STATE_DIM:]))
        with torch.no_grad():
            pred[t] = to_np(torch, post(policy.select_action(batch))).reshape(-1)[:ACTION_DIM]

    groups = [group_stats(pred[phases == p], teacher[phases == p], phases, p)
              for p in TASK_PHASES + ["done"]]
    task_mask = np.isin(phases, TASK_PHASES)
    return {
        "arm": Path(ckpt).name,
        "checkpoint": {
            "pretrained_model_dir": str(pm_dir.resolve()),
            "model_safetensors_sha256": sha256_file(pm_dir / "model.safetensors"),
        },
        "policy_config": {
            "chunk_size": int(cfg.chunk_size),
            "n_action_steps": int(cfg.n_action_steps),
            "normalization_mapping": {str(k): str(v) for k, v in cfg.normalization_mapping.items()},
            "optimizer_lr": float(cfg.optimizer_lr),
        },
        "versions": {"torch": torch.__version__, "python": platform.python_version(),
                     "device": str(cfg.device)},
        "overall": group_stats(pred, teacher, phases, "all"),
        "task_relevant": group_stats(pred[task_mask], teacher[task_mask], phases[task_mask],
                                     "approach+descend+grasp+lift+hold"),
        "by_phase": groups,
        "pred_dz_on_teacher_lift_frames": pred[teacher[:, DZ] >= LIFT_CMD_THRESHOLD, DZ].round(4).tolist(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src-episode", required=True, help="interchange 的 episode_XXXX.npz（teacher 真值）")
    ap.add_argument("--ckpt", nargs="+", required=True, help="一个或多个 run/checkpoint 目录，同表对照")
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    z = np.load(Path(args.src_episode), allow_pickle=False)
    obs = np.asarray(z["observation_state"], dtype=np.float32)
    teacher = np.asarray(z["action"], dtype=np.float32)
    raw_ph = np.asarray(z["phase"])
    phases = np.array([p.decode() if isinstance(p, bytes) else str(p) for p in raw_ph])
    if obs.shape[1] != STATE_DIM + ENV_DIM:
        raise SystemExit(f"[错误] 源观测 {obs.shape[1]} 维，与 50+10 切分假设不符")
    print(f"teacher 源: {args.src_episode}  帧数 {len(teacher)}")
    print(f"相位分布: {json.dumps({p: int((phases == p).sum()) for p in sorted(set(phases))}, ensure_ascii=False)}")

    arms = [audit_one(c, obs, teacher, phases, args.device) for c in args.ckpt]

    hdr = f"{'arm':44}{'scope':16}{'n':>5}{'dz_t':>8}{'dz_pred':>9}{'dz_bias':>9}{'lift_cmd':>9}{'grip±':>7}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for a in arms:
        for scope in ("task_relevant", "lift", "descend", "done"):
            g = a["task_relevant"] if scope == "task_relevant" else next(
                (x for x in a["by_phase"] if x["phase"] == scope), None)
            if not g or not g.get("frames"):
                continue
            lc = g.get("dz_pred_lift_cmd_rate")
            print(f"{a['arm'][:43]:44}{scope:16}{g['frames']:>5}{g['dz_teacher_mean']:>8.3f}"
                  f"{g['dz_pred_mean']:>9.3f}{g['dz_signed_bias']:>9.3f}"
                  f"{(f'{lc:.3f}' if lc is not None else '-'):>9}{g['grip_sign_agreement']:>7.3f}")
        print()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "audit": "official_lerobot_act_open_loop_per_phase_dz",
        "claim": "open_loop_action_alignment",
        "not_a_claim": ["不是闭环成功率", "不是真机结果", "只在给定的单个 teacher episode 上开环对齐"],
        "read_only": True,
        "teacher_source": str(Path(args.src_episode).resolve()),
        "teacher_phase_counts": {p: int((phases == p).sum()) for p in sorted(set(phases))},
        "lift_cmd_threshold": LIFT_CMD_THRESHOLD,
        "task_phases": TASK_PHASES,
        "arms": arms,
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"写出: {out}")


if __name__ == "__main__":
    main()
