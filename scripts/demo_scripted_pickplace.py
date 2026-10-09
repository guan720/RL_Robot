#!/usr/bin/env python
"""脚本式 pick-place 控制器：PickPlaceCan 上的「示范源」与「成功长什么样」可视化。

为什么现在写它（`docs/plan_alignment_2026-09-23.md` 实验队列第 2 项）：
    1. 示范预填在阶段 2 已实测 +27 点（150k 臂），PickPlaceCan 稀疏/shaped 两臂之后
       下一个杠杆就是它——而示范必须来自一个**能成功**的控制器；
    2. 它同时是「成功长什么样」的视频素材：robosuite 的 `info["success"]`、
       画面里 can 进篮、以及本控制器的阶段日志三者互相印证；
    3. 残差 RL 三臂对照里的 base 策略就是它（或 pd 版）。

七段状态机（完全不学习，纯规则；动作语义 = robosuite 默认 OSC_POSE）：
    approach       末端移到 can 正上方 PRE_HEIGHT
    descend        下降到抓取高度（can 顶附近）
    grasp          夹爪闭合 GRASP_STEPS 步
    lift           上升到 can 离桌面 LIFT_TARGET
    carry          水平移到目标篮正上方 CARRY_HEIGHT
    place_descend  下降直到 can 底接近篮底
    release        张夹爪 RELEASE_STEPS 步 -> retreat 抬一点 -> done
成功后本局不再动作（PickPlaceCan 只有一个 can，一局一个 task）。

用法：
    MUJOCO_GL=egl OMP_NUM_THREADS=1 python scripts/demo_scripted_pickplace.py --episodes 5
    MUJOCO_GL=egl OMP_NUM_THREADS=1 python scripts/demo_scripted_pickplace.py --episodes 1 --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("robosuite", "numpy", "imageio")

import imageio.v2 as imageio  # noqa: E402
import numpy as np  # noqa: E402
import robosuite  # noqa: E402

STEP_SCALE = 0.05      # OSC_POSE 每步最大位移 5cm
PRE_HEIGHT = 0.12      # can 正上方 12cm
GRASP_OFFSET_Z = 0.015  # 夹爪中心比 can 中心高 1.5cm：指腹包住中段侧壁，抓得更牢（0.025 会滑）
XY_TOL = 0.008
Z_TOL = 0.008
GRASP_STEPS = 25
LIFT_TARGET = 0.05     # can 离桌面 5cm（robosuite 判定进篮不要求高度，但拎起来才搬得动）
CARRY_HEIGHT = 0.16    # 搬运高度：篮子上方 16cm
PLACE_CAN_Z = 0.07     # can 中心降到篮子坐标 + 7cm（can 底接近篮底）就松手
MAX_GRASP_TRIES = 3    # 抓空重试次数（夹爪闭合后宽度仍接近 0 = 没夹到东西）
RELEASE_STEPS = 15


class PickPlaceStateMachine:
    """七段状态机。输入 obs（robosuite OrderedDict），输出 7 维 action。"""

    def __init__(self, bin2_pos: np.ndarray, can_z0: float, target_xy: np.ndarray | None = None) -> None:
        self.bin2 = np.asarray(bin2_pos, dtype=np.float64)
        # 关键几何：目标「篮子」是 2x2 篮格的一个象限（can 的 object id = 3 -> 右上象限），
        # bin2_pos 是四格交点，直接放上去会坐在篮墙上。象限中心用 robosuite 自己的真值表
        # env.target_bin_placements[env.object_to_id["can"]]，不再手推公式。
        self.target_xy = (np.asarray(target_xy, dtype=np.float64)[:2].copy()
                          if target_xy is not None else self.bin2[:2].copy())
        self.can_z0 = float(can_z0)      # 首帧 can 高度 = 「还在桌上」的参考线
        self.grasp_try = 0
        self.regrasp = 0
        self.phase = "approach"
        self.phase_step = 0
        self.log: list[str] = ["approach"]

    def _set(self, phase: str) -> None:
        self.phase = phase
        self.phase_step = 0
        self.log.append(phase)

    def __call__(self, obs: dict) -> np.ndarray:
        eef = np.asarray(obs["robot0_eef_pos"], dtype=np.float64)
        can = np.asarray(obs["Can_pos"], dtype=np.float64)
        self.phase_step += 1
        xy_ok = abs(eef[0] - can[0]) < XY_TOL and abs(eef[1] - can[1]) < XY_TOL

        if self.phase == "approach":
            target = can + np.array([0.0, 0.0, PRE_HEIGHT])
            if xy_ok and eef[2] > can[2] + PRE_HEIGHT - 0.02:
                self._set("descend")
        elif self.phase == "descend":
            target = can + np.array([0.0, 0.0, GRASP_OFFSET_Z])
            if xy_ok and abs(eef[2] - can[2] - GRASP_OFFSET_Z) < Z_TOL:
                self._set("grasp")
        elif self.phase == "grasp":
            target = can + np.array([0.0, 0.0, GRASP_OFFSET_Z - 0.004 * self.grasp_try])
            if self.phase_step >= GRASP_STEPS:
                # 注意：robosuite 的 gripper_qpos 是两指**反号**（开 = ±0.04），求和恒为 0；
                # 取绝对值才是开口宽度。夹到 can（半径 2.5cm）时约 0.025，空合接近 0。
                width = float(np.max(np.abs(np.asarray(obs["robot0_gripper_qpos"], dtype=np.float64))))
                if width > 0.012:                      # 夹爪没合到底 = 夹到东西了
                    self.grasp_try = 0
                    self._set("lift")
                elif self.grasp_try < MAX_GRASP_TRIES:  # 抓空：再降一点重夹
                    self.grasp_try += 1
                    self.phase_step = 0
                    self.log.append(f"grasp_retry{self.grasp_try}")
                else:
                    self.grasp_try = 0
                    self._set("approach")              # 彻底抓空：重新来过
        elif self.phase == "lift":
            target = eef + np.array([0.0, 0.0, 0.3])
            if can[2] > self.can_z0 + LIFT_TARGET:
                self._set("settle")
        elif self.phase == "settle":
            target = eef.copy()                        # 拎起来先停 10 步消摆，再平移
            if self.phase_step >= 10:
                self._set("carry")
        elif self.phase == "carry":
            if can[2] < self.can_z0 + 0.02:            # 搬运途中掉了 -> 回去重抓（恢复行为）
                self.regrasp += 1
                self.log.append(f"regrasp{self.regrasp}")
                self._set("approach")
                target = eef.copy()                    # 本步先停住，下一步进 approach
            elif eef[2] < self.bin2[2] + CARRY_HEIGHT - 0.02:
                target = eef + np.array([0.0, 0.0, 0.3])          # 先垂直升到搬运高度
            else:
                # 用 can 的实际 xy 做闭环（can 吊在夹爪下会偏），把 can 搬到篮子正上方
                target = np.array([eef[0] + (self.target_xy[0] - can[0]),
                                   eef[1] + (self.target_xy[1] - can[1]), eef[2]])
            if (abs(can[0] - self.target_xy[0]) < XY_TOL and abs(can[1] - self.target_xy[1]) < XY_TOL
                    and eef[2] >= self.bin2[2] + CARRY_HEIGHT - 0.02):
                self._set("place_descend")
        elif self.phase == "place_descend":
            if abs(can[0] - self.target_xy[0]) > XY_TOL or abs(can[1] - self.target_xy[1]) > XY_TOL:
                # 没对准就下降会坐在篮子边上：先平移对准，再降
                target = np.array([eef[0] + (self.target_xy[0] - can[0]),
                                   eef[1] + (self.target_xy[1] - can[1]), eef[2]])
            else:
                target = np.array([eef[0], eef[1], self.bin2[2] + PLACE_CAN_Z + GRASP_OFFSET_Z])
            if can[2] < self.bin2[2] + PLACE_CAN_Z + 0.02:
                self._set("release")
        elif self.phase == "release":
            target = eef.copy()
            if self.phase_step >= RELEASE_STEPS:
                self._set("retreat")
        elif self.phase == "retreat":
            target = eef + np.array([0.0, 0.0, 0.10])
            if self.phase_step >= 20:
                self._set("done")
        else:  # done
            target = eef.copy()

        delta = target - eef
        action = np.zeros(7, dtype=np.float32)
        action[:3] = np.clip(delta / STEP_SCALE, -1.0, 1.0)
        action[6] = 1.0 if self.phase in ("grasp", "lift", "settle", "carry", "place_descend") else -1.0
        return action

def run_episode(env, seed: int, verbose: bool, want_video: bool, camera: str):
    env.rng = np.random.default_rng(seed)
    obs = env.reset()
    # 目标象限：_check_success 对 objects 列表逐个用 not_in_bin(pos, i)，PickPlaceCan 的
    # objects = [Milk, Bread, Cereal, Can]（未激活的也在列表里），can 的下标 =
    # object_to_id["can"] = 3 -> 目标象限中心 = target_bin_placements[3]（not_in_bin 探针验证过）。
    ctrl = PickPlaceStateMachine(env.bin2_pos, can_z0=float(obs["Can_pos"][2]),
                                 target_xy=env.target_bin_placements[env.object_to_id["can"]])
    frames = [] if want_video else None
    succ_step, steps, reward_sum = -1, 0, 0.0
    while steps < env.horizon:
        action = ctrl(obs)
        obs, reward, done, info = env.step(action)
        steps += 1
        reward_sum += float(reward)
        if env._check_success() and succ_step < 0:
            succ_step = steps
        if want_video:
            frames.append(np.asarray(obs[f"{camera}_image"], dtype=np.uint8)[::-1])
        if verbose and steps % 25 == 0:
            can = obs["Can_pos"]
            print(f"    step {steps:4d} phase={ctrl.phase:<14} can_z={can[2]:.3f} "
                  f"success={bool(env._check_success())}", flush=True)
        if done:
            break
    return {"seed": seed, "success": succ_step >= 0, "success_step": succ_step,
            "steps": steps, "reward": reward_sum, "phases": ctrl.log}, frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--camera", default="agentview")
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else REPO_ROOT / "runs" / f"{ts}_scripted_pickplace"
    out_dir.mkdir(parents=True, exist_ok=True)

    env = robosuite.make("PickPlaceCan", robots="Panda", has_renderer=False,
                         has_offscreen_renderer=True, use_camera_obs=True,
                         camera_heights=args.size, camera_widths=args.size,
                         camera_names=[args.camera], use_object_obs=True,
                         control_freq=20, horizon=400, hard_reset=False)
    results, video_path = [], None
    t0 = time.perf_counter()
    for e in range(args.episodes):
        want_video = video_path is None  # 只录第一段成功视频
        res, frames = run_episode(env, seed=args.seed + e, verbose=args.verbose,
                                  want_video=want_video, camera=args.camera)
        if want_video and res["success"]:
            video_path = out_dir / "scripted_pickplace_success.mp4"
            imageio.mimwrite(str(video_path), frames, fps=20)
        results.append(res)
        print(f"  ep{e} seed={args.seed + e} success={res['success']} "
              f"step={res['success_step']} phases={'->'.join(dict.fromkeys(res['phases']))}", flush=True)
    secs = time.perf_counter() - t0
    n_succ = sum(r["success"] for r in results)
    summary = {"episodes": args.episodes, "success": n_succ,
               "success_rate": n_succ / args.episodes, "seconds": secs,
               "per_episode": results, "video": str(video_path) if video_path else None}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n脚本控制器：{n_succ}/{args.episodes} 成功（{secs:.0f} 秒）")
    print(f"[saved] {out_dir / 'summary.json'}" + (f"\n[video] {video_path}" if video_path else ""))
    env.close()


if __name__ == "__main__":
    main()
