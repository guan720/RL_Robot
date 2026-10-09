#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 / S1 前置探针：把「EE+mocap+weld 脚本专家通道」的**几何、频率、渲染、回放**四件事测实。

为什么先探针再写专家（裁定 53.3 口径搬运禁令 + 裁定 50.2 否定型主张纪律）
----------------------------------------------------------------------
D 在 `d_simchain_e2emin_20260929.md` §4 S1 给了三条"已实测的可行性事实"，其中一条
**B2 只读复核后不成立**，必须先落证据再动手，否则专家会建在一个错前提上：

  D 原文：「构造入口已存在但未注册：`env.py:120`–`:124` 支持
          `task="end_effector_transfer_cube"` ⇒ 直接构造 `AlohaEnv(task=...)`，不必 fork 包。」
  B2 实读：`gym_aloha/env.py:120`–`:124` 的该分支**第一行就是 `raise NotImplementedError()`**
          （:121），构造 `AlohaEnv(task="end_effector_transfer_cube")` 必抛。
          ⇒ 只能走 D 自己给的备选：「旁路 `AlohaEnv`、直接用 `dm_control.rl.control.Environment`」。
  另一条需要精确化：D 写 EE XML「含 2 处 `<equality>`」；B2 实读
          `grep -c '<equality>'` = **1**（1 个 `<equality>` 容器），其内 `<weld>` = **2**
          （mocap_left→vx300s_left/gripper_link、mocap_right→vx300s_right/gripper_link）。
          关节空间版两者皆 0。⇒ 结论方向不变（EE 版确有 weld 通道），但计数口径要写对。

本探针**只读** site-packages，一个字节都不改；频率口径用 A2 的
`envs/gym_aloha_shim.py`（裁定 53 的 29.4118 Hz），不自己另立一套。

产物：`runs/vla/b2_sim_demo_bidir_20260930/probe/probe.json`（+ `.log`）。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---- MUJOCO_GL 必须在 import dm_control/mujoco **之前** 定死（跨口径禁令：读法也不能搬） ----
_GL = "osmesa"
for i, a in enumerate(sys.argv):
    if a == "--gl" and i + 1 < len(sys.argv):
        _GL = sys.argv[i + 1]
    elif a.startswith("--gl="):
        _GL = a.split("=", 1)[1]
if _GL != "disable":
    os.environ["MUJOCO_GL"] = _GL
else:
    os.environ.pop("MUJOCO_GL", None)

import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CST = timezone(timedelta(hours=8))


def now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def _sha12(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def sec_versions() -> dict:
    import importlib
    out = {"python": platform.python_version(), "platform": platform.platform(),
           "mujoco_gl_env": os.environ.get("MUJOCO_GL", "(unset)")}
    for m in ("numpy", "mujoco", "dm_control", "gymnasium", "gym_aloha", "torch", "lerobot"):
        try:
            mod = importlib.import_module(m)
            out[m] = getattr(mod, "__version__", "unknown")
        except Exception as e:  # noqa: BLE001
            out[m] = f"IMPORT_ERROR: {type(e).__name__}: {e}"
    for m in ("gym_aloha", "dm_control", "mujoco"):
        try:
            mod = importlib.import_module(m)
            out[f"{m}.__file__"] = str(Path(mod.__file__).resolve())
        except Exception:
            pass
    out["loadavg"] = list(os.getloadavg())
    return out


def sec_files() -> dict:
    """否定型/计数型主张一律同批落 (mtime, 计数, 命令原文)（裁定 50.2 / 51.2）。"""
    import gym_aloha
    pkg = Path(gym_aloha.__file__).resolve().parent
    out = {"gym_aloha_pkg": str(pkg)}
    targets = {
        "env.py": pkg / "env.py",
        "constants.py": pkg / "constants.py",
        "tasks/sim.py": pkg / "tasks" / "sim.py",
        "tasks/sim_end_effector.py": pkg / "tasks" / "sim_end_effector.py",
        "assets/bimanual_viperx_end_effector_transfer_cube.xml":
            pkg / "assets" / "bimanual_viperx_end_effector_transfer_cube.xml",
        "assets/bimanual_viperx_transfer_cube.xml": pkg / "assets" / "bimanual_viperx_transfer_cube.xml",
        "assets/scene.xml": pkg / "assets" / "scene.xml",
        "gym_aloha_shim": REPO / "envs" / "gym_aloha_shim.py",
    }
    out["files"] = {}
    for k, p in targets.items():
        st = p.stat()
        out["files"][k] = {
            "path": str(p), "mtime": datetime.fromtimestamp(st.st_mtime, CST).isoformat(timespec="seconds"),
            "size": st.st_size, "sha256_12": _sha12(p),
            "n_lines": len(p.read_text(errors="replace").splitlines()),
        }
    ee = targets["assets/bimanual_viperx_end_effector_transfer_cube.xml"].read_text()
    js = targets["assets/bimanual_viperx_transfer_cube.xml"].read_text()
    out["equality_weld_counts"] = {
        "cmd": "python: text.count('<equality>') / text.count('<weld ') on the two asset XMLs",
        "ee_xml": {"n_equality_open_tags": ee.count("<equality>"), "n_weld": ee.count("<weld ")},
        "joint_xml": {"n_equality_open_tags": js.count("<equality>"), "n_weld": js.count("<weld ")},
        "d_claim_in_e2emin_s1": "EE XML「含 2 处 <equality>」；关节空间版 0 处",
        "b2_finding": ("EE XML 是 **1 个 <equality> 容器 + 2 个 <weld>**；关节空间版 0/0。"
                       "D 的『2 处』对应的是 weld 数，不是 <equality> 元素数 ⇒ 结论方向成立、计数口径已更正。"),
    }
    env_py = targets["env.py"].read_text().splitlines()
    out["env_py_ee_branch"] = {
        "cmd": "sed -n '120,124p' env.py",
        "lines": {str(120 + i): env_py[119 + i] for i in range(5)},
        "d_claim": "「env.py:120–:124 支持 task='end_effector_transfer_cube'，可直接构造 AlohaEnv」",
        "b2_finding": "**不成立**：:121 是 `raise NotImplementedError()`，在 xml_path/physics/task 三行之前 ⇒ 必抛。",
        "consequence": "S1 走 D 自己列的备选：旁路 AlohaEnv，直接构造 dm_control.rl.control.Environment。",
    }
    return out


def sec_model_facts() -> dict:
    """两个模型的 nq/nv/nu/ncam/相机名/物理步长/box 初始位姿（只读模型，不渲染）。"""
    import mujoco
    import gym_aloha
    pkg = Path(gym_aloha.__file__).resolve().parent / "assets"
    out = {}
    for tag, xml in (("ee", "bimanual_viperx_end_effector_transfer_cube.xml"),
                     ("joint", "bimanual_viperx_transfer_cube.xml")):
        m = mujoco.MjModel.from_xml_path(str(pkg / xml))
        cams = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_CAMERA, i) for i in range(m.ncam)]
        nq_box = None
        bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "box")
        out[tag] = {
            "xml": xml, "nq": int(m.nq), "nv": int(m.nv), "nu": int(m.nu), "ncam": int(m.ncam),
            "cameras": cams, "opt_timestep": float(m.opt.timestep),
            "n_mocap_bodies": int(m.nmocap),
            "body_box_id": int(bid),
            "n_equality": int(m.neq),
            "eq_types": [int(m.eq_type[i]) for i in range(m.neq)],
            "ctrlrange_first4": [[float(x) for x in m.actuator_ctrlrange[i]] for i in range(min(4, m.nu))],
        }
    out["note_eq_type"] = "mjtEq: 0=connect 1=weld 2=joint 3=tendon 4=flex 5=distance"
    return out


def sec_ee_env(dt: float, seed: int, box_pose) -> dict:
    """旁路 AlohaEnv 直接构造 EE 环境（因为 env.py:121 的 NotImplementedError），测频率与几何。"""
    from dm_control import mujoco as dm_mujoco
    from dm_control.rl import control
    import gym_aloha
    from gym_aloha.tasks.sim_end_effector import TransferCubeEndEffectorTask
    from gym_aloha.utils import sample_box_pose

    pkg = Path(gym_aloha.__file__).resolve().parent / "assets"
    out = {"dt_requested": dt, "seed": seed}

    bp = np.asarray(box_pose, dtype=np.float64) if box_pose is not None else sample_box_pose(seed)
    out["box_pose_used"] = [float(x) for x in bp]
    out["box_pose_kind"] = "explicit(probe)" if box_pose is not None else "sample_box_pose(seed)"

    class _SeededEE(TransferCubeEndEffectorTask):
        """只为**可复现**：上游 `initialize_episode` 调的是无种子的 `sample_box_pose()`。"""

        def initialize_episode(self, physics):
            self.initialize_robots(physics)
            idx = physics.model.name2id("red_box_joint", "joint")
            np.copyto(physics.data.qpos[idx: idx + 7], bp)
            physics.forward()
            super(TransferCubeEndEffectorTask, self).initialize_episode(physics)

    t0 = time.time()
    physics = dm_mujoco.Physics.from_xml_path(str(pkg / "bimanual_viperx_end_effector_transfer_cube.xml"))
    task = _SeededEE()
    env = control.Environment(physics, task, float("inf"), control_timestep=dt,
                              n_sub_steps=None, flat_observation=False)
    out["construct_s"] = round(time.time() - t0, 3)

    # --- 频率：读**活对象**，不是读常量（A2 shim 的 read_live_timing 口径） ---
    from envs import gym_aloha_shim as shim
    out["shim"] = {"sha256_12": shim.shim_sha256_12(),
                   "representation_version": shim.REPRESENTATION_VERSION,
                   "MAINLINE_DT": shim.MAINLINE_DT, "MAINLINE_HZ": round(shim.MAINLINE_HZ, 6),
                   "PER_STEP_BUDGET_MS": shim.PER_STEP_BUDGET_MS}
    n_sub, err = shim.substeps_or_error(dt)
    out["compute_n_steps"] = {"n_sub_steps": n_sub, "error": err}
    ct = float(shim._deref(env.control_timestep))
    phys_ts = float(shim._deref(env.physics.timestep))
    out["live_timing"] = {"control_timestep_s": ct, "physics_timestep_s": phys_ts,
                          "n_sub_steps_attr": int(getattr(env, "_n_sub_steps", -1)),
                          "control_hz": round(1.0 / ct, 6),
                          "in_qc_band_29_31": shim.in_qc_band(1.0 / ct),
                          "integer_multiple": abs(ct / phys_ts - round(ct / phys_ts)) <= 1e-8}

    # --- reset 后的几何 ---
    t0 = time.time()
    ts = env.reset()
    out["reset_s"] = round(time.time() - t0, 3)
    ph = env.physics
    names_l = "vx300s_left/gripper_link"
    names_r = "vx300s_right/gripper_link"
    def xpos(n):
        return np.asarray(ph.named.data.xpos[n], dtype=float).copy()
    out["geom_at_reset"] = {
        "mocap_pos": [[float(x) for x in ph.data.mocap_pos[i]] for i in range(ph.data.mocap_pos.shape[0])],
        "mocap_quat": [[float(x) for x in ph.data.mocap_quat[i]] for i in range(ph.data.mocap_quat.shape[0])],
        "gripper_link_xpos": {"left": [float(x) for x in xpos(names_l)], "right": [float(x) for x in xpos(names_r)]},
        "mocap_minus_gripperlink": {
            "left": [float(a - b) for a, b in zip(ph.data.mocap_pos[0], xpos(names_l))],
            "right": [float(a - b) for a, b in zip(ph.data.mocap_pos[1], xpos(names_r))]},
        "box_qpos7": [float(x) for x in ph.data.qpos[-7:]],
        "box_xpos": [float(x) for x in ph.named.data.xpos["box"]],
        "qpos_first16": [float(x) for x in ph.data.qpos[:16]],
        "ctrl4": [float(x) for x in ph.data.ctrl[:4]],
        "nq": int(ph.data.qpos.shape[0]),
    }
    # 手指尖（抓取点）相对 gripper_link 的偏移 —— 专家航点必须用它标定
    for side in ("left", "right"):
        cand = [f"vx300s_{side}/10_gripper_finger", f"vx300s_{side}/9_gripper_bar",
                f"vx300s_{side}/camera_focus"]
        found = {}
        for c in cand:
            try:
                found[c] = [float(x) for x in xpos(c)]
            except Exception as e:  # noqa: BLE001
                found[c] = f"ERR {type(e).__name__}: {e}"
        out["geom_at_reset"][f"finger_candidates_{side}"] = found
    out["geom_at_reset"]["body_names_with_gripper"] = [
        ph.model.id2name(i, "body") for i in range(ph.model.nbody)
        if "gripper" in (ph.model.id2name(i, "body") or "")]

    # --- weld 是否 1:1 跟随 mocap（专家通道的**核心前提**） ---
    delta = np.array([0.0, -0.05, 0.05])
    before_r = xpos(names_r)
    act = np.zeros(16)
    act[0:3] = ph.data.mocap_pos[0]
    act[3:7] = ph.data.mocap_quat[0]
    act[7] = 0.099848
    act[8:11] = np.asarray(ph.data.mocap_pos[1]) + delta
    act[11:15] = ph.data.mocap_quat[1]
    act[15] = 0.099848
    for _ in range(5):
        env.step(act)
    after_r = xpos(names_r)
    out["weld_tracking"] = {
        "cmd": "把 mocap_right 平移 [0,-0.05,+0.05]，step 5 次，读 gripper_link xpos 差",
        "mocap_delta": [float(x) for x in delta],
        "gripper_link_delta": [float(a - b) for a, b in zip(after_r, before_r)],
        "tracking_error_norm": float(np.linalg.norm((after_r - before_r) - delta)),
        "verdict_1to1_within_5mm": bool(np.linalg.norm((after_r - before_r) - delta) < 5e-3),
        "n_steps": 5,
    }
    return out, env


def sec_render_cost(env, sizes=((480, 640), (224, 224)), reps=3) -> dict:
    out = {"backend": os.environ.get("MUJOCO_GL", "(unset)"), "per_camera_s": {}}
    ph = env.physics
    cams = [ph.model.id2name(i, "camera") for i in range(ph.model.ncam)]
    out["cameras"] = cams
    for (h, w) in sizes:
        key = f"{h}x{w}"
        out["per_camera_s"][key] = {}
        for c in cams:
            ts = []
            err = None
            for _ in range(reps):
                t0 = time.time()
                try:
                    img = ph.render(height=h, width=w, camera_id=c)
                except Exception as e:  # noqa: BLE001
                    err = f"{type(e).__name__}: {e}"
                    break
                ts.append(time.time() - t0)
            rec = {"mean_s": round(float(np.mean(ts)), 4) if ts else None, "reps": len(ts)}
            if ts:
                rec["shape"] = list(np.asarray(img).shape)
            if err:
                rec["error"] = err
            out["per_camera_s"][key][c] = rec
    return out


def sec_joint_replay(dt: float, seed: int, box_pose_left: bool) -> dict:
    """关节空间 env（= 部署 env）里：① BOX_POSE 能否注入**左侧**方块（反向任务的入口）
    ② 用 qpos 当动作回放时跟踪误差多大（决定"EE 解算 → 关节回放"这条路能不能出干净示范）。"""
    import gymnasium as gym
    import gym_aloha  # noqa: F401
    from gym_aloha.tasks.sim import BOX_POSE
    from gym_aloha.utils import sample_box_pose
    from envs import gym_aloha_shim as shim

    out = {"box_pose_left": box_pose_left, "dt": dt}
    env, rec = shim.make_env("gym_aloha/AlohaTransferCube-v0", dt=dt, obs_type="pixels_agent_pos")
    out["shim_apply"] = rec
    bp = sample_box_pose(seed)
    if box_pose_left:
        bp = bp.copy()
        bp[0] = -abs(bp[0]) if abs(bp[0]) > 1e-9 else -0.15
        out["box_pose_note"] = "把 x 取负 ⇒ 方块落在左侧（x∈[-0.2,-0.0]），**不改 site-packages**，只写 BOX_POSE[0]"
    BOX_POSE[0] = bp
    out["BOX_POSE_injected"] = [float(x) for x in bp]
    obs, info = env.reset(seed=seed)
    ph = env.unwrapped._env.physics
    out["box_qpos_after_reset"] = [float(x) for x in ph.data.qpos[-7:]]
    out["box_spawn_matches_injection"] = bool(np.allclose(ph.data.qpos[-7:], bp, atol=1e-9))
    out["agent_pos_dim"] = int(np.asarray(obs["agent_pos"]).shape[0])

    # 回放：拿当前 qpos14 当动作，前后各加一点点位移，测跟踪误差
    q = np.asarray(ph.data.qpos[:14], dtype=float).copy()
    # 14 维装配序：left arm6 + left gripper1 + right arm6 + right gripper1（constants.JOINTS）
    errs = []
    traj = []
    for i in range(40):
        a = q.copy()
        a[1] = q[1] + 0.3 * np.sin(i / 8.0)      # 左 shoulder 小幅摆动
        a[8 + 1] = q[8 + 1] + 0.3 * np.sin(i / 8.0)
        traj.append(a)
    for a in traj:
        obs, rew, term, trunc, info = env.step(a.astype(np.float32))
        cur = np.asarray(ph.data.qpos[:14], dtype=float)
        errs.append(float(np.max(np.abs(cur - a))))
    out["replay_tracking"] = {
        "cmd": "40 步：动作=目标 qpos14（左右 shoulder 正弦 ±0.3 rad），逐步读回 qpos 比最大绝对误差",
        "max_abs_err_rad": round(float(np.max(errs)), 6),
        "mean_abs_err_rad": round(float(np.mean(errs)), 6),
        "p95_abs_err_rad": round(float(np.percentile(errs, 95)), 6),
        "note": "关节 env 是 position actuator（kp 800/1600/800/10/...），动作=绝对目标角 ⇒ 误差应很小；"
                "这条数字决定「EE 解算出的 qpos 轨迹能否直接当关节示范回放」。",
    }
    env.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gl", default="osmesa", choices=["egl", "osmesa", "glfw", "disable"])
    ap.add_argument("--dt", type=float, default=0.034)
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--out-dir", default="runs/vla/b2_sim_demo_bidir_20260930/probe")
    ap.add_argument("--box-x", type=float, default=0.15)
    ap.add_argument("--box-y", type=float, default=0.5)
    ap.add_argument("--skip-render", action="store_true")
    a = ap.parse_args()

    out = {"probe": "b2_s1_probe_ee_channel", "generated_at": now(), "argv": sys.argv[1:], "repo": str(REPO)}
    out["versions"] = sec_versions()
    out["files"] = sec_files()
    out["model_facts"] = sec_model_facts()

    box = np.array([a.box_x, a.box_y, 0.05, 1.0, 0.0, 0.0, 0.0])
    ee, env = sec_ee_env(a.dt, a.seed, box)
    out["ee_env"] = ee
    if not a.skip_render:
        try:
            out["render_cost"] = sec_render_cost(env)
        except Exception:
            out["render_cost"] = {"error": traceback.format_exc(limit=6)}
    # EE env 里能否 step 一段（专家可行性最低门槛）
    try:
        t0 = time.time()
        act = np.zeros(16)
        act[0:3] = env.physics.data.mocap_pos[0]
        act[3:7] = env.physics.data.mocap_quat[0]
        act[7] = 0.5
        act[8:11] = env.physics.data.mocap_pos[1]
        act[11:15] = env.physics.data.mocap_quat[1]
        act[15] = 0.5
        rewards = []
        for _ in range(20):
            _, r, _, _ = env.step(act)
            rewards.append(int(r))
        out["ee_step_smoke"] = {"n_steps": 20, "elapsed_s": round(time.time() - t0, 3),
                                "per_step_s": round((time.time() - t0) / 20, 4), "rewards": rewards}
    except Exception:
        out["ee_step_smoke"] = {"error": traceback.format_exc(limit=6)}

    for tag, left in (("joint_replay_box_right", False), ("joint_replay_box_left", True)):
        try:
            out[tag] = sec_joint_replay(a.dt, a.seed, left)
        except Exception:
            out[tag] = {"error": traceback.format_exc(limit=8)}

    outdir = REPO / a.out_dir
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / "probe.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[b2-s1-probe] wrote {p} ({p.stat().st_size} bytes) at {now()}")
    print(json.dumps({k: out[k] for k in ("ee_env", "weld_tracking") if k in out},
                     ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
