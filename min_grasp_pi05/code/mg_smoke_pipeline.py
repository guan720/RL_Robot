#!/usr/bin/env python
"""最小抓取链路 · 管线冒烟（假数据，不碰仿真、不碰真数据集）。

目的：在等 robosuite/示范数据的时候，先把「LeRobotDataset(dtype=image, use_videos=False) ->
lerobot-train(ACT) -> 检查点目录 -> 重新加载」这条管线单独验通，把训练侧的未知数清零。
产物全部落在 runs/_smoke/，不进 data/。

用法： bash -c 'source code/env.sh && $MG_PY code/mg_smoke_pipeline.py --steps 20'
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_collect import build_features  # noqa: E402
from mg_env import (  # noqa: E402
    ACTION_DIM, ACTION_KEY, IMG_KEY_BASE, IMG_KEY_WRIST, ROBOT, STATE_DIM, STATE_KEY, TASK,
)

SMOKE = MG_ROOT / "runs" / "_smoke"


def make_dummy_dataset(root: Path, repo_id: str, episodes: int, length: int, img_size: int) -> Path:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    if root.exists():
        shutil.rmtree(root)
    rng = np.random.default_rng(0)
    ds = LeRobotDataset.create(repo_id=repo_id, fps=20, features=build_features(img_size),
                               robot_type=ROBOT.lower(), root=str(root), use_videos=False,
                               image_writer_threads=2)
    for _ in range(episodes):
        for t in range(length):
            ds.add_frame({
                STATE_KEY: rng.normal(size=STATE_DIM).astype(np.float32),
                ACTION_KEY: rng.uniform(-1, 1, size=ACTION_DIM).astype(np.float32),
                IMG_KEY_BASE: rng.integers(0, 255, size=(img_size, img_size, 3), dtype=np.uint8),
                IMG_KEY_WRIST: rng.integers(0, 255, size=(img_size, img_size, 3), dtype=np.uint8),
                "task": TASK,
            })
        ds.save_episode()
    ds.finalize()          # 不调用 -> meta/episodes 没有 parquet，数据集读不回来（已踩）
    ds2 = LeRobotDataset(repo_id=repo_id, root=str(root))
    item = ds2[0]
    print(f"[smoke] 假数据集：episodes={ds2.meta.total_episodes} frames={ds2.meta.total_frames} "
          f"len={len(ds2)} state={tuple(np.asarray(item[STATE_KEY]).shape)} "
          f"img={tuple(np.asarray(item[IMG_KEY_BASE]).shape)} {np.asarray(item[IMG_KEY_BASE]).dtype}")
    print(f"[smoke] stats keys={sorted(ds2.meta.stats.keys())}")
    print(f"[smoke] state stats={json.dumps({k: [round(float(x), 4) for x in v] for k, v in ds2.meta.stats[STATE_KEY].items() if k in ('mean', 'std', 'min', 'max')})}")
    return root


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--episodes", type=int, default=2)
    ap.add_argument("--length", type=int, default=30)
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--skip-train", action="store_true")
    args = ap.parse_args()

    SMOKE.mkdir(parents=True, exist_ok=True)
    ds_root = SMOKE / "dataset"
    repo_id = "mg_smoke_dummy"
    make_dummy_dataset(ds_root, repo_id, args.episodes, args.length, args.img_size)
    if args.skip_train:
        return 0

    out = SMOKE / "train"
    if out.exists():
        shutil.rmtree(out)
    cmd = ["lerobot-train", f"--dataset.repo_id={repo_id}", f"--dataset.root={ds_root}",
           "--policy.type=act", f"--steps={args.steps}", "--batch_size=2", "--num_workers=2",
           "--save_freq=10", "--log_freq=5", "--eval_freq=-1", f"--output_dir={out}",
           "--job_name=smoke_act", "--wandb.enable=false", "--save_checkpoint=true",
           "--policy.device=cuda", "--policy.push_to_hub=false"]
    print("[smoke] " + " ".join(cmd))
    log = SMOKE / "train.log"
    with open(log, "w") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=str(MG_ROOT))
    print("".join(log.read_text(errors="ignore").splitlines(keepends=True)[-20:]))
    if proc.returncode != 0:
        print(f"[smoke] 训练失败 rc={proc.returncode}，完整日志 {log}")
        return proc.returncode

    ckpt = out / "checkpoints" / "last" / "pretrained_model"
    print(f"[smoke] 检查点 {ckpt} 内容：{sorted(p.name for p in ckpt.iterdir())}")

    # 重新加载 + 前向一步（验证 mg_eval 的加载路径可用）
    import torch
    from mg_eval import load_policy, to_tensor_obs
    policy, pre, post = load_policy(ckpt, torch.device("cuda" if torch.cuda.is_available() else "cpu"), False)
    obs = {STATE_KEY: np.zeros(STATE_DIM, dtype=np.float32),
           IMG_KEY_BASE: np.zeros((args.img_size, args.img_size, 3), dtype=np.uint8),
           IMG_KEY_WRIST: np.zeros((args.img_size, args.img_size, 3), dtype=np.uint8)}
    with torch.inference_mode():
        act = post(policy.select_action(pre(to_tensor_obs(obs, next(policy.parameters()).device))))
    act_np = act.squeeze(0).cpu().numpy()
    print(f"[smoke] 策略输出动作 shape={act_np.shape}（契约要求 ({ACTION_DIM},)）"
          f" chunk_size={getattr(policy.config, 'chunk_size', None)} "
          f"n_action_steps={getattr(policy, 'n_action_steps', None)}")
    ok = act_np.shape == (ACTION_DIM,)
    print(f"[smoke] {'PASS' if ok else 'FAIL'} 假数据管线打通")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
