#!/usr/bin/env python
"""纯观测反应式 Lift 控制器：把示范变成「obs 的一致函数」，修 MSE-BC 的病根。

背景（2026-09-24 的否证链）：BC-only 在 5k/20k/20k过采样 三档示范下 = 5%/0%/0%。
机制诊断：旧示范源 `LiftStateMachine` 带**隐藏相位**（approach/descend/grasp/lift 是内部
状态机变量），同一 obs（例如「末端在 cube 上方 2cm、夹爪开」）在不同相位对应不同动作
（继续降 / 原地闭 / 闭后升），MSE-BC 只能学条件均值 -> 平均策略哪个相位都做不对。
示范数量/初始位姿多样性/事件过采样都救不了「数据本身自相矛盾」。

本控制器是 obs 的**纯函数**（eef、cube、夹爪开口宽度三个信号决定一切，无内部相位）：
    夹爪夹着 cube（开口 0.012~0.035）: cube 还低 -> 升；cube 已高 -> 保持
    夹爪开（>0.035）                : 没对准/不够高 -> 去 cube 上方；对准且在高处 -> 降到抓取位
                                      对准且在抓取位 -> 原地闭
    夹爪空闭（<=0.012）             : 张开并去更低一档抓取位（用 obs 里的开口宽度当「抓空」信号，
                                      不引入计数器隐藏状态）
这样示范数据里 obs->action 不再自相矛盾，BC 问题是良定的；它同时是「怎样构造才有用的示范」
这一问题的可检验答案。

用法：
    MUJOCO_GL=egl OMP_NUM_THREADS=1 python scripts/demo_reactive_lift_rs.py --episodes 6 --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("robosuite", "numpy")

import numpy as np  # noqa: E402

from envs.robosuite_lift import RobosuiteLift  # noqa: E402

OPEN_W = 0.035        # 开口宽度大于此 = 夹爪张开
GRASP_W_LO = 0.012    # 0.012~0.035 = 夹着 cube（cube 半宽 0.025）；<=0.012 = 空闭
PRE_HEIGHT = 0.10
GRASP_Z = 0.02        # 抓取位：cube 中心上方 2cm
LOW_Z = 0.008         # 抓空重试档：cube 中心上方 0.8cm
XY_TOL = 0.008
LIFT_TARGET = 0.05
HOLD_STEPS = 30


class ReactiveLiftPolicy:
    """obs -> action 的纯函数。唯一「状态」是构造时的 cube 初始高度（参考线）。"""

    def __init__(self, cube_z0: float) -> None:
        self.cube_z0 = float(cube_z0)
        self.hold_steps = 0

    @property
    def phase(self) -> str:
        # 兼容 fill_demo_buffer 的「done」约定：保持段够久就结束本局
        return "done" if self.hold_steps >= HOLD_STEPS else "run"

    def __call__(self, obs: dict) -> np.ndarray:
        eef = np.asarray(obs["robot0_eef_pos"], dtype=np.float64)
        cube = np.asarray(obs["cube_pos"], dtype=np.float64)
        width = float(np.max(np.abs(np.asarray(obs["robot0_gripper_qpos"], dtype=np.float64))))
        grasped = GRASP_W_LO < width <= OPEN_W
        opened = width > OPEN_W
        xy_ok = abs(eef[0] - cube[0]) < XY_TOL and abs(eef[1] - cube[1]) < XY_TOL
        grip = 1.0

        if grasped:
            if cube[2] > self.cube_z0 + LIFT_TARGET:
                target = eef.copy()
                self.hold_steps += 1
            else:
                target = eef + np.array([0.0, 0.0, 0.3])
        elif opened:
            if not xy_ok or eef[2] < cube[2] + 0.06:
                target = cube + np.array([0.0, 0.0, PRE_HEIGHT])
                grip = -1.0
            elif eef[2] > cube[2] + GRASP_Z + 0.008:
                target = cube + np.array([0.0, 0.0, GRASP_Z])
                grip = -1.0
            else:
                target = cube + np.array([0.0, 0.0, GRASP_Z])
                grip = 1.0          # 对准且在抓取位：原地闭
        else:                        # 空闭：张开 + 去更低一档
            target = cube + np.array([0.0, 0.0, LOW_Z])
            grip = -1.0

        action = np.zeros(7, dtype=np.float64)
        action[:3] = np.clip((target - eef) / 0.05, -1.0, 1.0)
        action[6] = grip
        return action


def run_episode(env: RobosuiteLift, seed: int, horizon: int, verbose: bool) -> dict:
    obs, _ = env.reset(seed=seed)
    raw = env._env._get_observations()
    pol = ReactiveLiftPolicy(cube_z0=float(raw["cube_pos"][2]))
    succ, steps = False, 0
    for t in range(horizon):
        action = pol(raw)
        obs, r, term, trunc, info = env.step(action)
        raw = env._env._get_observations()
        steps = t + 1
        if info["success"] and not succ:
            succ = True
            if verbose:
                print(f"    seed {seed}: 第 {steps} 步提起成功")
        if pol.phase == "done" or term or trunc:
            break
    if verbose:
        print(f"    seed {seed}: success={succ} 步数={steps}")
    return {"seed": seed, "success": bool(succ), "steps": steps}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", type=int, default=6)
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    env = RobosuiteLift(obs_mode="state", horizon=args.horizon, reward_shaping=False)
    per = [run_episode(env, seed=e, horizon=args.horizon, verbose=args.verbose) for e in range(args.episodes)]
    env.close()
    n_succ = sum(p["success"] for p in per)
    summary = {"controller": "reactive", "episodes": args.episodes, "success": n_succ,
               "success_rate": n_succ / args.episodes, "per_episode": per}
    out_dir = REPO_ROOT / "runs" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_reactive_lift_rs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[反应式 Lift] {n_succ}/{args.episodes} 成功  -> {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
