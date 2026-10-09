#!/usr/bin/env python
"""脚本式 Lift 控制器（robosuite）：「栈 vs 任务」的判别实验。

背景（2026-09-23）：Lift SAC 臂的奖励在涨但成功率在 0/20% 之间抖。要判断
「是 SAC 预算/探索不够」还是「这套动作接口根本抓不起来」，最便宜的办法是
拿一个**完全不学习的规则控制器**跑同一套包装层：它能稳定提起 → 栈没问题，
问题在学习侧；它也提不起 → 先查 OSC 动作语义/夹爪映射，别浪费训练算力。

四段状态机（approach → descend → grasp → lift → hold），动作语义 = robosuite 默认
OSC_POSE（7 维：6 维末端增量 + 1 维夹爪），几何常数沿用 demo_scripted_pickplace.py
实测值（夹爪中心比物体中心高 1.5cm 抓得牢；gripper_qpos 两指反号要取绝对值）。

用法：
    MUJOCO_GL=egl OMP_NUM_THREADS=1 python scripts/demo_scripted_lift_rs.py --episodes 6
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

PRE_HEIGHT = 0.10
GRASP_OFFSET_Z = 0.02
XY_TOL = 0.008
Z_TOL = 0.008
GRASP_STEPS = 25
LIFT_TARGET = 0.05
HOLD_STEPS = 30
MAX_GRASP_TRIES = 3


def _cube_pos(obs: dict) -> np.ndarray:
    for key in ("cube_pos", "Cube_pos", "Can_pos"):   # Lift 的键是小写 cube_pos（实测）
        if key in obs:
            return np.asarray(obs[key], dtype=np.float64)
    raise KeyError(f"obs 里找不到物体位姿键，现有键：{[k for k in obs if k.endswith('_pos')]}")


class LiftStateMachine:
    def __init__(self, cube_z0: float) -> None:
        self.cube_z0 = float(cube_z0)
        self.grasp_try = 0
        self.phase = "approach"
        self.phase_step = 0
        self.log: list[str] = ["approach"]

    def _set(self, phase: str) -> None:
        self.phase = phase
        self.phase_step = 0
        self.log.append(phase)

    def __call__(self, obs: dict) -> np.ndarray:
        eef = np.asarray(obs["robot0_eef_pos"], dtype=np.float64)
        cube = _cube_pos(obs)
        self.phase_step += 1
        xy_ok = abs(eef[0] - cube[0]) < XY_TOL and abs(eef[1] - cube[1]) < XY_TOL

        if self.phase == "approach":
            target = cube + np.array([0.0, 0.0, PRE_HEIGHT])
            if xy_ok and eef[2] > cube[2] + PRE_HEIGHT - 0.02:
                self._set("descend")
        elif self.phase == "descend":
            target = cube + np.array([0.0, 0.0, GRASP_OFFSET_Z])
            if xy_ok and abs(eef[2] - cube[2] - GRASP_OFFSET_Z) < Z_TOL:
                self._set("grasp")
        elif self.phase == "grasp":
            target = cube + np.array([0.0, 0.0, GRASP_OFFSET_Z - 0.004 * self.grasp_try])
            if self.phase_step >= GRASP_STEPS:
                width = float(np.max(np.abs(np.asarray(obs["robot0_gripper_qpos"], dtype=np.float64))))
                if width > 0.012:
                    self.grasp_try = 0
                    self._set("lift")
                elif self.grasp_try < MAX_GRASP_TRIES:
                    self.grasp_try += 1
                    self.phase_step = 0
                    self.log.append(f"grasp_retry{self.grasp_try}")
                else:
                    self.grasp_try = 0
                    self._set("approach")
        elif self.phase == "lift":
            target = eef + np.array([0.0, 0.0, 0.3])
            if cube[2] > self.cube_z0 + LIFT_TARGET:
                self._set("hold")
        elif self.phase == "hold":
            target = eef.copy()
            if self.phase_step >= HOLD_STEPS:
                self._set("done")      # 转移放类里：示范预填循环只认 ctrl.phase == "done"
        else:  # done
            target = eef.copy()

        delta = target - eef
        action = np.zeros(7, dtype=np.float64)
        action[:3] = np.clip(delta / 0.05, -1.0, 1.0)     # OSC_POSE：±1 对应每步 5cm
        # 夹爪语义实测（2026-09-23，与 demo_scripted_pickplace.py 一致）：**+1 = 闭合，-1 = 张开**。
        # 写反的症状：approach 段夹爪自己合拢、grasp 段反而张开，width 检查假阳性进 lift，cube 永不动。
        action[6] = 1.0 if self.phase in ("grasp", "lift", "hold", "done") else -1.0
        return action


def run_episode(env: RobosuiteLift, seed: int, horizon: int, verbose: bool) -> dict:
    obs, _ = env.reset(seed=seed)
    raw = env._env._get_observations()
    ctrl = LiftStateMachine(cube_z0=float(_cube_pos(raw)[2]))
    succ, steps = False, 0
    for t in range(horizon):
        action = ctrl(raw)
        obs, r, term, trunc, info = env.step(action)
        raw = env._env._get_observations()
        steps = t + 1
        if info["success"] and not succ:
            succ = True
            if verbose:
                print(f"    seed {seed}: 第 {steps} 步提起成功")
        if term or trunc:
            break
    if verbose:
        print(f"    seed {seed}: success={succ} 步数={steps} 阶段链={'->'.join(ctrl.log)}")
    return {"seed": seed, "success": bool(succ), "steps": steps, "phases": ctrl.log}


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
    summary = {"episodes": args.episodes, "success": n_succ,
               "success_rate": n_succ / args.episodes, "per_episode": per}
    out_dir = REPO_ROOT / "runs" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_scripted_lift_rs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[脚本 Lift] {n_succ}/{args.episodes} 成功  -> {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
