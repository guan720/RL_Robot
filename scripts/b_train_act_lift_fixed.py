#!/usr/bin/env python3
"""B 支线：与 scripts/train_act_lift.py 的单变量对照——只改优化循环，其余全部复用。

复用的部分（不复制、直接 import，保证数据/架构/归一化完全一致）：
  - scripts.train_act_lift.collect       teacher 数据采集
  - scripts.train_act_lift.ChunkPolicy   同一 MLP chunk 策略
  - harness.env_factory                  pinned object / reset_contact

唯一变量：梯度调度。
  baseline 每 epoch 一次全批量更新，epochs=40 -> 共 40 步梯度；
  本脚本改成 minibatch，按 --grad-steps 预算训练（默认 5600 步）。

checkpoint 字段与 baseline 完全相同，因此可直接用
scripts/eval_act_lift_truth.py 做同一套 20 局真值评测。
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.env_factory import PINNED_OBJECT_SEED, contact_object_geom, make_contact_env  # noqa: E402
from scripts.train_act_lift import ChunkPolicy, collect  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/infra/b_act_lift_mb_hist1_seed0")
    ap.add_argument("--chunk-length", type=int, default=4)
    ap.add_argument("--history", type=int, default=1)
    ap.add_argument("--train-episodes", type=int, default=24)
    ap.add_argument("--val-episodes", type=int, default=8)
    ap.add_argument("--grad-steps", type=int, default=5600)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--horizon", type=int, default=300)
    a = ap.parse_args()
    np.random.seed(a.seed); torch.manual_seed(a.seed)

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    env = make_contact_env("lift", horizon=a.horizon, reward_shaping=True, obs_mode="state")
    train_seeds = list(range(1000, 1000 + a.train_episodes))
    val_seeds = list(range(2000, 2000 + a.val_episodes))
    tr = collect(env, train_seeds, a.horizon, a.chunk_length, a.history)
    va = collect(env, val_seeds, a.horizon, a.chunk_length, a.history)
    geom = contact_object_geom(env, "lift", PINNED_OBJECT_SEED)
    env.close()

    x = np.stack([s for s, _ in tr]); y = np.stack([b for _, b in tr])
    xv = np.stack([s for s, _ in va]); yv = np.stack([b for _, b in va])
    mean = x.mean(0).astype(np.float32)
    std = (x.std(0) + 1e-6).astype(np.float32)          # 与 baseline 完全一致的归一化
    dead = [int(i) for i in range(y.shape[2]) if np.abs(y[:, :, i]).max() < 1e-9]

    model = ChunkPolicy(x.shape[1], a.chunk_length)
    opt = torch.optim.Adam(model.parameters(), lr=a.lr)
    tx = torch.tensor((x - mean) / std); ty = torch.tensor(y)
    vx = torch.tensor((xv - mean) / std); vy = torch.tensor(yv)

    n = len(tx); bs = min(a.batch_size, n)
    g = torch.Generator().manual_seed(a.seed)
    best = float("inf"); steps = 0; curve = []
    while steps < a.grad_steps:
        model.train()
        for idx in torch.randperm(n, generator=g).split(bs):
            loss = ((model(tx[idx]) - ty[idx]) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step(); steps += 1
            if steps % 200 == 0 or steps >= a.grad_steps:
                model.eval()
                with torch.no_grad():
                    vl = ((model(vx) - vy) ** 2).mean().item()
                curve.append({"step": steps, "val_mse": vl})
                if vl < best:
                    best = vl
                    torch.save({"model": model.state_dict(), "obs_dim": x.shape[1], "history": a.history,
                                "chunk_length": a.chunk_length, "obs_mean": mean.tolist(),
                                "obs_std": std.tolist(), "action_dim": 7, "object_geom": geom,
                                "pinned_object_seed": PINNED_OBJECT_SEED}, out / "model_best.pt")
                model.train()
            if steps >= a.grad_steps:
                break

    model.eval()
    torch.save({"model": model.state_dict(), "obs_dim": x.shape[1], "history": a.history,
                "chunk_length": a.chunk_length, "obs_mean": mean.tolist(), "obs_std": std.tolist(),
                "action_dim": 7, "object_geom": geom, "pinned_object_seed": PINNED_OBJECT_SEED},
               out / "model_final.pt")
    cfg = {"task": "lift", "obs": "state", "history": a.history, "chunk_length": a.chunk_length,
           "action_dim": 7, "train_seeds": train_seeds, "val_seeds": val_seeds, "horizon": a.horizon,
           "grad_steps": steps, "batch_size": bs, "lr": a.lr, "seed": a.seed,
           "pinned_object_seed": PINNED_OBJECT_SEED, "object_geom": geom,
           "train_samples": len(tr), "val_samples": len(va), "best_val_mse": best,
           "dead_action_dims": dead, "diff_vs_baseline": "only optimizer schedule: minibatch + grad-step budget",
           "val_curve": curve}
    (out / "config.json").write_text(json.dumps(cfg, indent=2))
    (out / "train_result.json").write_text(json.dumps({"best_val_mse": best, "grad_steps": steps,
                                                       "train_samples": len(tr), "val_samples": len(va),
                                                       "dead_action_dims": dead}, indent=2))
    print(json.dumps({k: v for k, v in cfg.items() if k not in ("object_geom", "val_curve")}, indent=2))


if __name__ == "__main__":
    main()
