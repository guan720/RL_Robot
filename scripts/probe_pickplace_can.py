#!/usr/bin/env python
"""robosuite PickPlaceCan 探针：把「视觉观测到底贵不贵、接口长什么样」量出来。

为什么先探针再训练：视觉 RL 的成本 = 渲染 + 策略网络两部分，本机渲染走 CPU 软渲染
（docs/infra-gpu-render.md：256x256 约 55-70 fps），而策略训练可以用 GPU。
不量清楚就开跑，很可能一夜之后发现瓶颈在渲染而不是算法。

本脚本量四件事：
    1. state-only（不渲染）一步多少毫秒 -> 物理 + 控制器本身的成本
    2. 像素观测（84x84 / 128x128 两档）一步多少毫秒 -> 渲染的边际成本
    3. 观测接口：obs 的键、图像 dtype/shape、动作空间、reward 与 success 从哪来
    4. 相机帧长什么样：存 PNG，肉眼看「策略将来能看到什么」

用法：
    MUJOCO_GL=egl OMP_NUM_THREADS=1 python scripts/probe_pickplace_can.py
    MUJOCO_GL=egl OMP_NUM_THREADS=1 python scripts/probe_pickplace_can.py --size 128 --steps 200
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")   # 本机实际是 llvmpipe 软渲染，见 docs/infra-gpu-render.md

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("robosuite", "numpy", "imageio")

import imageio.v2 as imageio  # noqa: E402
import numpy as np  # noqa: E402
import robosuite  # noqa: E402


def make_env(use_cam: bool, size: int, cams: list[str]):
    return robosuite.make(
        "PickPlaceCan",
        robots="Panda",
        has_renderer=False,
        has_offscreen_renderer=use_cam,
        use_camera_obs=use_cam,
        camera_heights=size,
        camera_widths=size,
        camera_names=cams,
        use_object_obs=True,
        control_freq=20,
        horizon=400,
        hard_reset=False,
    )


def timed_rollout(env, steps: int, tag: str, out_dir: Path | None, save_frames: bool,
                  lo: np.ndarray | None = None, hi: np.ndarray | None = None):
    obs = env.reset()          # robosuite 1.5 仍是旧 API：reset()->obs, step()->(obs,r,done,info)
    t0 = time.perf_counter()
    rewards, succ = [], 0
    frames = []
    for i in range(steps):
        action = np.random.uniform(lo, hi)
        obs, reward, done, info = env.step(action)
        rewards.append(float(reward))
        succ = max(succ, int(bool(info.get("success", False))))
        if save_frames and i in (0, steps // 2, steps - 1):
            frames.append((i, {k: np.asarray(obs[k]) for k in obs if k.endswith("_image")}))
        if done:
            obs = env.reset()
    dt = (time.perf_counter() - t0) / steps
    print(f"[{tag}] {steps} 步  {dt*1000:.1f} ms/步  ({1/max(dt,1e-9):.1f} fps)  "
          f"mean_reward {np.mean(rewards):.4f}  success_seen {succ}")
    if out_dir is not None:
        for i, imgs in frames:
            for name, img in imgs.items():
                p = out_dir / f"{tag}_step{i:04d}_{name}.png"
                imageio.imwrite(p, img)
                print(f"  [frame] {p}  shape={img.shape} dtype={img.dtype}")
    return dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--size", type=int, default=84)
    ap.add_argument("--out", default="runs/infra/pickplace_probe")
    ap.add_argument("--cams", default="agentview,robot0_eye_in_hand", help="逗号分隔的相机名")
    ap.add_argument("--no-state", action="store_true", help="跳过 state-only 档（只量相机）")
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "mujoco_gl": os.environ["MUJOCO_GL"]}

    cams = [c for c in args.cams.split(",") if c]
    env = make_env(use_cam=False, size=args.size, cams=cams)
    obs = env.reset()
    report["obs_keys_state"] = sorted(obs.keys())
    lo, hi = (np.asarray(x, dtype=np.float64) for x in env.action_spec)  # robosuite 1.5: (low, high) 二元组
    report["action_space"] = {"shape": [int(lo.size)], "low": lo.tolist(), "high": hi.tolist()}
    if not args.no_state:
        report["state_ms_per_step"] = timed_rollout(env, args.steps, "state-only", None, False, lo, hi)
    env.close()

    env = make_env(use_cam=True, size=args.size, cams=cams)
    obs = env.reset()
    img_keys = [k for k in obs if k.endswith("_image")]
    report["obs_keys_image"] = sorted(img_keys)
    report["image_shape"] = {k: list(np.asarray(obs[k]).shape) for k in img_keys}
    tag = f"cam{args.size}x{len(cams)}"
    report[f"{tag}_ms_per_step"] = timed_rollout(env, args.steps, tag, out_dir, True, lo, hi)
    env.close()

    (out_dir / "probe.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n[saved] {out_dir / 'probe.json'}")
    print("obs keys (state):", report["obs_keys_state"])
    print("action space:", report["action_space"]["shape"], report["action_space"]["low"], report["action_space"]["high"])


if __name__ == "__main__":
    main()
