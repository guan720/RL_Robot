#!/usr/bin/env python3
"""只读审计官方 LeRobot ACT checkpoint：开环动作对齐（不是闭环成功率）。

它回答的问题只有一个：**官方 ACT 训练出来的权重，能不能在训练 episode 上复现 teacher 动作**。
这是 09-24 审计清单里「Official LeRobot ACT single-episode learned overfit」那一项的证据，
不能当成真实抓取成功，也不能替代 20 局真值评测。

两种口径，都跑：
  1. chunk 级（replan 边界）：每 4 帧一次 request，取 policy.predict_action_chunk()
     的 [4,7]，与 interchange 里的 action_chunk[i] 逐元素比。等价于 receding horizon=4。
  2. 逐帧级（执行队列）：policy.reset() 后连续 300 次 select_action()，让官方 action
     queue 自己决定何时重新推理，与 teacher action[t] 逐帧比。这是 RuntimeAdapter 会
     走的路径。

推理链路完全照官方 `lerobot/scripts/lerobot_eval.py`：
    preprocessor(obs) -> policy.select_action(...) -> postprocessor(action)
normalization stats 来自 checkpoint 自带的 `policy_preprocessor_step_*_normalizer_processor.safetensors`，
不重新从数据集统计，避免「训练/推理两套 normalizer」。

用法：
    /root/venvs/lerobot_act/bin/python scripts/audit_lerobot_act_overfit.py \
        --ckpt runs/infra/lerobot_act_lift_v30/overfit_ep0_lr1e-5_s20k/checkpoints/last/pretrained_model \
        --src-episode runs/infra/lerobot_act_lift_state_overfit/data/episode_0000.npz \
        --out runs/infra/lerobot_act_env_20260928/overfit_alignment_lr1e-5.json
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np

STATE_DIM = 50
ENV_DIM = 10
CHUNK = 4


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._lerobot_act import load_official_act, resolve_pretrained_dir, sha256_file  # noqa: E402


def obs_dict(torch, state50: np.ndarray, env10: np.ndarray) -> dict:
    return {
        "observation.state": torch.from_numpy(np.ascontiguousarray(state50, dtype=np.float32)),
        "observation.environment_state": torch.from_numpy(np.ascontiguousarray(env10, dtype=np.float32)),
    }


def to_np(torch, x) -> np.ndarray:
    if isinstance(x, torch.Tensor):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True, help="run 目录 / checkpoint 目录 / pretrained_model 目录")
    ap.add_argument("--src-episode", required=True, help="interchange 的 episode_XXXX.npz（teacher 真值）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default=None, help="覆盖 checkpoint 里的 device（默认沿用）")
    args = ap.parse_args()

    pm_dir = resolve_pretrained_dir(args.ckpt)
    src = Path(args.src_episode)
    z = np.load(src, allow_pickle=False)
    obs = np.asarray(z["observation_state"], dtype=np.float32)
    teacher_act = np.asarray(z["action"], dtype=np.float32)
    teacher_chunks = np.asarray(z["action_chunk"], dtype=np.float32)
    n_frames = len(teacher_act)
    if obs.shape[1] != STATE_DIM + ENV_DIM:
        raise SystemExit(f"[错误] 源观测 {obs.shape[1]} 维，与 50+10 切分假设不符")

    torch, cfg, policy, pre, post, pm_dir = load_official_act(pm_dir, device=args.device)

    import lerobot

    print(f"checkpoint : {pm_dir}")
    print(f"lerobot    : {lerobot.__version__}   torch {torch.__version__}   device {cfg.device}")
    print(f"config     : chunk_size={cfg.chunk_size} n_action_steps={cfg.n_action_steps} "
          f"temporal_ensemble_coeff={cfg.temporal_ensemble_coeff} use_vae={cfg.use_vae} kl={cfg.kl_weight}")

    # ---- 口径 1：chunk 级（每 4 帧一次 request）----
    requests = []
    policy.reset()
    chunk_err_first = []
    chunk_err_all = []
    for req_id, i in enumerate(range(0, n_frames - CHUNK + 1, CHUNK)):
        batch = pre(obs_dict(torch, obs[i, :STATE_DIM], obs[i, STATE_DIM:]))
        with torch.no_grad():
            pred = to_np(torch, post(policy.predict_action_chunk(batch)))[0]  # [K,7]
        ref = teacher_chunks[i]
        k = min(len(pred), len(ref))
        err = np.abs(pred[:k] - ref[:k])
        chunk_err_first.append(float(err[0].max()))
        chunk_err_all.append(err)
        requests.append(
            {
                "request_id": req_id,
                "frame": int(i),
                "planned_chunk": int(len(pred)),
                "executed_frames": int(k),
                "execution_mask": [True] * int(k),
                "partially_executed": bool(k < CHUNK),
                "cross_episode_padded": False,
                "max_abs_err": float(err.max()),
                "first_action_max_abs_err": float(err[0].max()),
                "deadline_miss": False,
                "takeover": False,
                "recovery": False,
            }
        )
    chunk_err = np.concatenate([e.reshape(-1) for e in chunk_err_all])

    # ---- 口径 2：逐帧执行队列（RuntimeAdapter 路径）----
    policy.reset()
    frame_pred = np.zeros_like(teacher_act)
    replan_frames = []
    for t in range(n_frames):
        batch = pre(obs_dict(torch, obs[t, :STATE_DIM], obs[t, STATE_DIM:]))
        with torch.no_grad():
            a = to_np(torch, post(policy.select_action(batch))).reshape(-1)[:7]
        frame_pred[t] = a
        if t % CHUNK == 0:
            replan_frames.append(t)
    frame_err = np.abs(frame_pred - teacher_act)

    per_dim = [
        {
            "dim": d,
            "name": ["dx", "dy", "dz", "droll", "dpitch", "dyaw", "gripper"][d],
            "frame_max_abs_err": float(frame_err[:, d].max()),
            "frame_mean_abs_err": float(frame_err[:, d].mean()),
        }
        for d in range(teacher_act.shape[1])
    ]
    gripper_sign_agree = float(
        np.mean(np.sign(frame_pred[:, -1]) == np.sign(teacher_act[:, -1]))
    )

    result = {
        "audit": "official_lerobot_act_open_loop_alignment",
        "read_only": True,
        "claim": "learned_offline_alignment_only",
        "not_a_claim": [
            "不是闭环真实抓取成功",
            "不是 20 局真值评测",
            "不含 residual / guard / recovery",
        ],
        "versions": {
            "lerobot": lerobot.__version__,
            "torch": torch.__version__,
            "python": platform.python_version(),
            "device": str(cfg.device),
            "cuda_available": bool(torch.cuda.is_available()),
        },
        "checkpoint": {
            "pretrained_model_dir": str(pm_dir.resolve()),
            "model_safetensors_sha256": sha256_file(pm_dir / "model.safetensors"),
            "files": sorted(p.name for p in pm_dir.iterdir() if p.is_file()),
        },
        "policy_config": {
            "type": cfg.type,
            "chunk_size": int(cfg.chunk_size),
            "n_action_steps": int(cfg.n_action_steps),
            "temporal_ensemble_coeff": cfg.temporal_ensemble_coeff,
            "use_vae": bool(cfg.use_vae),
            "kl_weight": float(cfg.kl_weight),
            "dim_model": int(cfg.dim_model),
            "n_encoder_layers": int(cfg.n_encoder_layers),
            "n_decoder_layers": int(cfg.n_decoder_layers),
            "dropout": float(cfg.dropout),
            "optimizer_lr": float(cfg.optimizer_lr),
            "normalization_mapping": {str(k): str(v) for k, v in cfg.normalization_mapping.items()},
            "input_features": {k: {"type": str(v.type), "shape": list(v.shape)} for k, v in cfg.input_features.items()},
            "output_features": {k: {"type": str(v.type), "shape": list(v.shape)} for k, v in cfg.output_features.items()},
            "normalizer_source": "checkpoint 自带 policy_preprocessor_step_*_normalizer_processor.safetensors",
        },
        "teacher_source": {
            "npz": str(src.resolve()),
            "npz_sha256": sha256_file(src),
            "frames": int(n_frames),
            "seed": int(z["seed"]),
            "split": str(z["split"]),
            "episode_index": int(z["episode_index"]),
        },
        "chunk_level": {
            "requests": len(requests),
            "frames_per_request": CHUNK,
            "first_action_max_abs_err": float(np.max(chunk_err_first)),
            "first_action_mean_abs_err": float(np.mean(chunk_err_first)),
            "all_frames_max_abs_err": float(chunk_err.max()),
            "all_frames_mean_abs_err": float(chunk_err.mean()),
            "teacher_action_reproduced_at_1e-2": bool(np.max(chunk_err_first) < 1e-2),
            "teacher_action_reproduced_at_1e-1": bool(np.max(chunk_err_first) < 1e-1),
        },
        "frame_level": {
            "frames": int(n_frames),
            "replan_frames_count": len(replan_frames),
            "max_abs_err": float(frame_err.max()),
            "mean_abs_err": float(frame_err.mean()),
            "gripper_sign_agreement": gripper_sign_agree,
            "per_dim": per_dim,
        },
        "requests": requests,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    print("\n=== chunk 级（replan 边界，共 %d 次 request）===" % len(requests))
    print(f"  首动作 max|err| = {result['chunk_level']['first_action_max_abs_err']:.6g}")
    print(f"  首动作 mean|err| = {result['chunk_level']['first_action_mean_abs_err']:.6g}")
    print(f"  整块   max|err| = {result['chunk_level']['all_frames_max_abs_err']:.6g}")
    print("=== 逐帧执行队列（%d 帧，%d 次重推理）===" % (n_frames, len(replan_frames)))
    print(f"  max|err| = {result['frame_level']['max_abs_err']:.6g}   mean|err| = {result['frame_level']['mean_abs_err']:.6g}")
    print(f"  gripper 符号一致率 = {gripper_sign_agree:.3f}")
    print(f"\n写出: {out}")


if __name__ == "__main__":
    main()
