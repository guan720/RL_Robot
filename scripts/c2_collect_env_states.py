#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · T-C2-1 的**env 诊断档**状态采集器（不是主线 stats 源，裁定 52/69）。

## 它采什么、为什么
主线部署 stats 的源是 **B2 的 S1 仿真双向示范**（裁定 52/69：先导 5 集落地即算）。
本脚本采的是**关节模型里实测的状态分布**，用途只有两个（都写进产物）：
1. **诊断档**：解释 π₀.₅ zero-shot 的饱和现象（哪些维在 [-1,1] 外 / 近常量）；
2. 给 T-C2-1 的闸当**必红分支的输入**（用 env 版 stats 冒充主线 ⇒ 必须红）。
⇒ 产物一律带 `not_for_mainline_normalizer=true`（`harness/norm_contract.py` 的分级）。

## 口径纪律（裁定 53 / 53.6 / 62①）
* 频率**不自己声明**：`DT=0.034`（17×0.002 ⇒ 29.4118 Hz）来自 A2 的 `envs/gym_aloha_shim.py`
  （sha256-12 `dc14466fcdcf`）；本脚本只 import、只读实测，并**真跑核对** `env.unwrapped` 的 dt。
* `render_images=False`：只采 14 维状态，不采图像 ⇒ 不占 GPU、不产生 1.7 MB/帧的 obs。
  但底层 `gym_aloha` 的 `get_observation` 仍会渲一路 `top`（A2 实测 `tasks/sim.py`），
  ⇒ **仍需 GL 后端**，后端进五元标注，**跨后端数字不得互搬**（裁定 46.4）。
* 物理行程（F1 下限族要用）**读模型**，不猜：qpos 映射走模块级 `ARM_QPOS_IDX`
  （= `tasks/sim.py:61-69`）；夹爪维 = 手指滑动关节 `jnt_range` 经 upstream
  `normalize_puppet_gripper_position`（`constants.py:94-97`）换算 ⇒ 实测行程 **0.91001**（不是 1.0）。
  **`jnt_range` 是软边界**（live 实测 hold 60 步 `qpos[6]=0.07333 > jnt_hi=0.057`，+28.6%）⇒
  落盘同时给 `physical_range`（声明）与 `physical_range_effective = max(声明, 实测)`，F1 用后者。
  ⚠ 旧版本这里写的是"夹爪维行程 = 1.0"，且 `physical_range()` 内联了 `state_dim + 2` 的错映射
  （右臂差一位、dim12 差 175×）⇒ 已由 `scripts/c2_fix_physical_range.py` 勘误并留证。
* 数值主张带 loadavg + `nr_throttled`（分母 = cgroup 配额 12 核）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from envs import gym_aloha_shim as shim            # noqa: E402
from harness import env_gym_aloha as geg           # noqa: E402

GRIPPER_SPAN = 1.0        # constants.py:94-97 + :74-75（OPEN 0.05800 / CLOSE 0.01844）
ARM_QPOS_IDX = list(range(0, 6)) + list(range(8, 14))   # sim.py:61-69 的 get_qpos 映射
STATE_LAYOUT = ["left_arm_joint_%d" % i for i in range(6)] + ["left_gripper_normalized"] + \
               ["right_arm_joint_%d" % i for i in range(6)] + ["right_gripper_normalized"]


def sha12(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]


def load_pair() -> dict:
    la = " ".join(Path("/proc/loadavg").read_text().split()[:3]) if Path("/proc/loadavg").exists() else "unavailable"
    nt = None
    for cand in ("/sys/fs/cgroup/cpu,cpuacct/cpu.stat", "/sys/fs/cgroup/cpu.stat"):
        p = Path(cand)
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("nr_throttled"):
                    nt = int(line.split()[1])
            break
    return {"loadavg": la, "nr_throttled": nt, "cgroup_quota_cores": 12}


GRIPPER_STATE_DIMS = (6, 13)
GRIPPER_QPOS_IDX = {6: 6, 13: 14}   # tasks/sim.py:63-68：每臂 qpos 块 8 个，夹爪 = 块内 index 6


def arm_qpos_for(state_dim: int) -> int:
    """state 维 → qpos 索引。**只用模块级声明的 `ARM_QPOS_IDX`**，不再内联第二套公式。

    历史缺陷（2026-09-30 00:3x 自查发现，已修）：本函数不存在时，`physical_range()` 内联写了
    `qpos_idx = state_dim + 2`（state 7..12 → qpos 9..14），与同文件声明的
    `ARM_QPOS_IDX = range(0,6) + range(8,14)` **分叉** ⇒ 右臂 6 个维全部拿到邻位关节的行程，
    其中 dim12 拿到手指滑动关节的 0.036（真值 6.28316，**差 175×**）。
    """
    if state_dim in GRIPPER_STATE_DIMS:
        return GRIPPER_QPOS_IDX[state_dim]
    idx = state_dim if state_dim < 6 else state_dim - 1
    q = ARM_QPOS_IDX[idx]
    assert q == (state_dim if state_dim < 6 else state_dim + 1), (
        f"ARM_QPOS_IDX 与 tasks/sim.py:61-69 的映射不一致：state_dim={state_dim} → qpos={q}")
    return q


def physical_range(physics) -> tuple[np.ndarray, list[dict]]:
    """14 维物理行程（**状态空间单位**）。

    * 臂关节：`jnt_range` 宽度（qpos 映射走 `arm_qpos_for()` = 模块级 `ARM_QPOS_IDX`）。
    * 夹爪维：模型里 `qposadr=6/14` 是 `left_finger` 滑动关节（实测 `jnt_range=[0.021, 0.057]`），
      经 upstream `normalize_puppet_gripper_position`（`constants.py:94-97`）换算 ⇒ 行程 **0.91001**、
      区间 [0.0647, 0.9747]。**不再假设 1.0**（差 9.0%），也**不用** `constants.py:80-81` 的
      JOINT_OPEN/CLOSE 常量推（那是另一套出处，实测与本模型该 qpos 不符 ⇒ 会错 53×）。
    * ⚠ **`jnt_range` 是软边界**：MuJoCo 限位由约束力实现，位置执行器可推出去
      （live 实测：hold 60 步后 `qpos[6]=0.07333 > jnt_hi=0.057`，+28.6%；random 档 8 个维越界）
      ⇒ 本函数返回的是**声明行程**；调用方必须与**实测行程**取 max（见 `physical_range_effective`）。
    """
    rng = np.zeros(14, dtype=np.float64)
    prov = []
    nj = physics.model.njnt
    jnt_range = np.asarray(physics.model.jnt_range, dtype=np.float64)
    jnt_limited = np.asarray(physics.model.jnt_limited, dtype=np.int64)
    names = [physics.model.joint(i).name for i in range(nj)]
    # qpos 索引 → 关节索引：本模型 1 关节 1 自由度（nq=23 含浮动基座？实测登记）
    qpos_adr = [int(physics.model.joint(i).qposadr[0]) for i in range(nj)]
    from gym_aloha import constants as GC
    norm_grip = GC.normalize_puppet_gripper_position      # 用 upstream 函数，不重实现公式
    for state_dim in range(14):
        qpos_idx = arm_qpos_for(state_dim)
        ji = next((i for i in range(nj) if qpos_adr[i] == qpos_idx), None)
        if ji is None:
            prov.append({"dim": state_dim, "name": STATE_LAYOUT[state_dim], "range": None,
                         "qpos_idx": qpos_idx, "provenance": "declared_only：找不到对应关节"})
            continue
        lo, hi = jnt_range[ji]
        if state_dim in GRIPPER_STATE_DIMS:
            lo_s, hi_s = float(norm_grip(float(lo))), float(norm_grip(float(hi)))
            src = ("physics.model.jnt_range（qpos %d = 手指滑动关节）经 "
                   "constants.py:94-97 normalize_puppet_gripper_position 换算" % qpos_idx)
        else:
            lo_s, hi_s = float(lo), float(hi)
            src = "physics.model.jnt_range（实测读模型；qpos 映射 = 模块级 ARM_QPOS_IDX）"
        span = (hi_s - lo_s) if jnt_limited[ji] else float("nan")
        rng[state_dim] = span
        prov.append({"dim": state_dim, "name": STATE_LAYOUT[state_dim], "joint": names[ji],
                     "qpos_idx": qpos_idx, "jnt_range": [float(lo), float(hi)],
                     "state_interval": [lo_s, hi_s], "limited": bool(jnt_limited[ji]),
                     "range": span, "bound_kind": "soft（MuJoCo 限位可被位置执行器推出，实测 +28.6%）",
                     "provenance": src})
    return rng, prov


def policy_action(kind: str, t: int, rng: np.random.Generator, action_dim: int) -> np.ndarray:
    if kind == "hold":
        return np.zeros(action_dim, dtype=np.float32)
    if kind == "random":
        return rng.uniform(-1.0, 1.0, size=action_dim).astype(np.float32)
    if kind == "sweep":
        # 逐维正弦激励：让每一维都被驱动过（近常量维的判定需要"被激励过"才有意义）
        a = np.zeros(action_dim, dtype=np.float32)
        for d in range(action_dim):
            a[d] = float(np.sin(2 * np.pi * (t / 60.0) + d * (2 * np.pi / action_dim)))
        return a
    raise SystemExit(f"未知 policy {kind}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", type=int, default=2)
    ap.add_argument("--max-steps", type=int, default=300)
    ap.add_argument("--policy", default="random", choices=("hold", "random", "sweep"))
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--direction", default="right_to_left", choices=geg.DIRECTIONS)
    ap.add_argument("--out-dir", default="runs/vla/c2_norm_contract_20260929/env_states")
    args = ap.parse_args()

    out = ROOT / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    env, apply_rec = shim.make_env(dt=shim.MAINLINE_DT)
    sim = geg.GymAlohaSimEnv(geg.EnvSpec(render_images=False, direction=args.direction, seed=args.seed),
                             env=env, apply_record=apply_rec)
    timing = shim.read_live_timing(env)
    sim._verify_timing()                      # 半改的 monkeypatch 必须在这里炸（裁定 57.4 / 62②）
    prange, pprov = physical_range(sim.physics)

    rng = np.random.default_rng(args.seed)
    action_dim = int(np.asarray(sim.env.action_space.sample()).size)
    states, start_poses, per_ep = [], [], []
    for ep in range(args.episodes):
        obs = sim.reset(seed=args.seed + ep)
        start_poses.append(np.asarray(obs[geg.STATE_KEY], dtype=np.float64).copy())
        n = 0
        for t in range(args.max_steps):
            a = policy_action(args.policy, t, rng, action_dim)
            obs, extra = sim.step(a)
            states.append(np.asarray(obs[geg.STATE_KEY], dtype=np.float64).copy())
            n += 1
            if extra.get("done"):
                break
        per_ep.append({"episode": ep, "steps": n, "outcome": (extra.get("judgment") or {}).get("outcome_class"),
                       "env_reward_last": (extra.get("facts") or {}).get("env_reward")})
    frames = np.asarray(states, dtype=np.float64)
    observed_travel = (frames.max(0) - frames.min(0))
    # `jnt_range` 是软边界（实测会越出）⇒ F1 下限与近常量标记的分母必须取 max(声明, 实测)。
    prange_eff = np.maximum(prange, observed_travel)
    np.savez(out / "env_states.npz", frames=frames, start_poses=np.asarray(start_poses),
             physical_range=prange, physical_range_effective=prange_eff,
             observed_travel=observed_travel)
    wall = time.time() - t0
    manifest = {
        "artifact": "c2_env_state_collection",
        "generated_at": _dt.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "purpose": ["诊断档（解释 zero-shot 饱和）", "T-C2-1 闸的必红分支输入"],
        "not_for_mainline_normalizer": True,
        "mainline_stats_source_per_ruling": "s1_sim_demo_bidir（B2 先导 5 集；裁定 52/69）",
        "policy": args.policy, "episodes": args.episodes, "max_steps": args.max_steps,
        "action_dim": action_dim,
        "seed": args.seed, "direction": args.direction,
        "n_frames": int(frames.shape[0]), "state_dim": int(frames.shape[1]),
        "state_layout": STATE_LAYOUT,
        "start_pose_frames": np.asarray(start_poses).tolist(),
        "start_pose_abs_max": float(np.abs(np.asarray(start_poses)).max()),
        "physical_range": prange.tolist(), "physical_range_provenance": pprov,
        "physical_range_effective": prange_eff.tolist(),
        "observed_travel": observed_travel.tolist(),
        "physical_range_basis": "effective = max(jnt_range 声明行程, 本档实测行程)；jnt_range 是软边界",
        "dims_where_observed_exceeds_declared": [int(i) for i in range(14)
                                                 if observed_travel[i] > prange[i] + 1e-12],
        "physical_range_correction_ref": "runs/vla/c2_norm_contract_20260929/physical_range_correction/correction.json",
        "timing": timing,
        "measured_control_hz": (float(frames.shape[0]) / wall) if wall > 0 else None,
        "measured_control_hz_note": ("**墙钟吞吐**，本组合（venv/后端/模型/环境）实测；"
                                     "不得与 E 线 11.82× 或 A2 的任何数字互搬（裁定 53.6）"),
        "wall_seconds": round(wall, 3),
        "five_tuple": geg.five_tuple_annotation(sim.spec, timing),
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "render_images": False,
        "render_note": "本脚本不渲 3 相机；但 gym_aloha 的 get_observation 仍渲一路 top ⇒ 后端必须可用",
        "shim": {"path": "envs/gym_aloha_shim.py", "sha256_12": shim.shim_sha256_12(),
                 "mainline_dt": shim.MAINLINE_DT, "mainline_hz": shim.MAINLINE_HZ,
                 "substeps": shim.MAINLINE_SUBSTEPS},
        "env_module": {"path": "harness/env_gym_aloha.py", "sha256_12": geg.module_sha256_12()},
        "collector": {"path": "scripts/c2_collect_env_states.py",
                      "sha256_12": sha12(Path(__file__).resolve())},
        "python": sys.version.split()[0], "platform": platform.platform(),
        "venv": sys.prefix,
        "per_episode": per_ep,
        "load_pair": load_pair(),
        "frames_abs_max_per_dim": np.abs(frames).max(axis=0).tolist(),
        "frames_min_per_dim": frames.min(axis=0).tolist(),
        "frames_max_per_dim": frames.max(axis=0).tolist(),
        "n_dims_exceeding_unit_interval": int((np.abs(frames).max(axis=0) > 1.0).sum()),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"n_frames": manifest["n_frames"], "wall_s": manifest["wall_seconds"],
                      "measured_hz": manifest["measured_control_hz"],
                      "start_pose_abs_max": manifest["start_pose_abs_max"],
                      "n_dims_exceeding_unit_interval": manifest["n_dims_exceeding_unit_interval"],
                      "out": str(out.relative_to(ROOT))}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
