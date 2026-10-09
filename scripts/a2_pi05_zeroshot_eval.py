#!/usr/bin/env python3
"""A2 / G3 —— π₀.₅ **零 SFT** 基线（20 局）+ **随机基线对照**（同环境、同判据、同 seed 序列）。

依据 `rl_harness_supervision/d_handoff_to_a2_20260929.md` §5、§11.2。
**本脚本只证明「接口贯通 + 判据可用」，不证明能力**（§5「不得声称」清单原文照抄进
`docs/a2_pi05_sim_readiness_20260929.md`）。

判据设计（§5：必须同时报「环境 success」与「grasp 真值 success」两列，并说明差异）
  env_success     = gym-aloha 自己的 `info["is_success"]`，即 `reward == 4`
                    （`gym_aloha/tasks/sim.py:127-149`：`touch_left_gripper and not touch_table`）。
                    注意它只看左夹爪的**一根**手指 geom（`vx300s_left/10_left_gripper_finger`）。
  grasp_truth     = 本脚本**独立**算的更严判据：左夹爪**任一根**手指与 `red_box` 接触、
                    `red_box` 不接触 `table`、且该状态**连续保持 ≥ --grasp-sustain-steps 步**
                    （默认 10 步 = 0.2 s @50 Hz）⇒ 能把一闪而过的 flick/弹射与「真夹住并搬起来」分开。
  flick_candidate = `env_success=True` 且 `grasp_truth=False`（伪成功候选，§5 点名要查的东西）。
  随机基线的意义 = **证明判据不是恒真**：若随机基线也拿到非零成功率，判据就有问题。

阶段分布（reward 语义见 `sim.py:127-149`；reward 本身**不是**单调阶段码，所以这里自己算）
  S0 未接触 / S1 右夹爪接触 / S2 右夹爪抬起(离桌) / S3 左夹爪接触(交接) / S4 左夹爪抬起(搬运成功)

**动作适配是"假设"不是"实测"**：π₀.₅ base ckpt 不携带 embodiment 槽位语义（见
`runs/vla/a2_pi05_contract_20260929/contract.json` 的 q2/q3 = unknown），所以
`model_out[0:14] -> gym_aloha action[0:14]` 这一步标 `assumed_from_convention`，
并把**裁剪失真**（多少维被 clip、clip 幅度）实测记下来。

用法：
  MUJOCO_GL=egl python scripts/a2_pi05_zeroshot_eval.py --policy pi05 \
      --weights-dir <NFS>/lerobot/pi05_base --tokenizer-dir <NFS>/google/paligemma-3b-pt-224 \
      --out-dir runs/vla/a2_pi05_zeroshot_20260929 --n-episodes 20
  MUJOCO_GL=egl python scripts/a2_pi05_zeroshot_eval.py --policy random \
      --out-dir runs/vla/a2_pi05_zeroshot_20260929 --n-episodes 20
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import sys
import time
from datetime import datetime

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("OMP_NUM_THREADS", "4")

RED_BOX = "red_box"
TABLE = "table"
LEFT_FINGERS = ("vx300s_left/10_left_gripper_finger", "vx300s_left/10_right_gripper_finger")
RIGHT_FINGERS = ("vx300s_right/10_left_gripper_finger", "vx300s_right/10_right_gripper_finger")
# gym-aloha 自己的 env_success 只看这一根（sim.py:141）
ENV_LEFT_FINGER = "vx300s_left/10_left_gripper_finger"
STAGE_NAMES = ["no_contact", "right_touch", "right_lift", "left_touch", "left_lift_success"]


def _read(path):
    try:
        return pathlib.Path(path).read_text().strip()
    except Exception:
        return None


def load_snapshot() -> dict:
    la = os.getloadavg()
    stat = {}
    txt = _read("/sys/fs/cgroup/cpu.stat") or _read("/sys/fs/cgroup/cpu/cpu.stat") or ""
    for line in txt.splitlines():
        p = line.split()
        if len(p) == 2 and p[1].lstrip("-").isdigit():
            stat[p[0]] = int(p[1])
    return {"loadavg_1m": round(la[0], 2), "loadavg_5m": round(la[1], 2),
            "loadavg_15m": round(la[2], 2), "cpu_stat": stat,
            "ts": datetime.now().astimezone().isoformat(timespec="seconds")}


def gpu_stats() -> dict:
    try:
        import torch
        if not torch.cuda.is_available():
            return {"available": False}
        return {"available": True,
                "allocated_MiB": round(torch.cuda.memory_allocated() / 2**20, 1),
                "reserved_MiB": round(torch.cuda.memory_reserved() / 2**20, 1),
                "max_allocated_MiB": round(torch.cuda.max_memory_allocated() / 2**20, 1),
                "device": torch.cuda.get_device_name(0)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


class SceneProbe:
    """从 physics 里读接触/位姿，算 env 判据 + 独立的 grasp 真值 + 阶段码。"""

    def __init__(self, physics):
        self.physics = physics
        self.geom_ids = {}
        errors = {}
        for name in (RED_BOX, TABLE, *LEFT_FINGERS, *RIGHT_FINGERS):
            # dm_control 的 MjModel 是 `name2id(name, kind)`，**没有** `geom_name2id`
            # （第一版写了后者 ⇒ 6 个名字全部读成 None；错误原文一并留下，不静默吞）
            try:
                self.geom_ids[name] = physics.model.name2id(name, "geom")
            except Exception as exc:  # noqa: BLE001
                self.geom_ids[name] = None
                errors[name] = f"{type(exc).__name__}: {exc}"
        missing = [k for k, v in self.geom_ids.items() if v is None]
        if missing:
            raise RuntimeError(f"geom names not found in model: {missing}; errors={errors}")

    def pairs(self):
        ph = self.physics
        out = set()
        for i in range(ph.data.ncon):
            c = ph.data.contact[i]
            n1 = ph.model.id2name(c.geom1, "geom")
            n2 = ph.model.id2name(c.geom2, "geom")
            if n1 and n2:
                out.add((n1, n2))
                out.add((n2, n1))
        return out

    def sample(self):
        p = self.pairs()
        touch_left = any((RED_BOX, f) in p for f in LEFT_FINGERS)
        touch_right = any((RED_BOX, f) in p for f in RIGHT_FINGERS)
        touch_table = (RED_BOX, TABLE) in p
        # 复刻 env 自己的判据（只看一根手指），用于交叉核对 env_success
        env_style_left = (RED_BOX, ENV_LEFT_FINGER) in p
        qpos = self.physics.data.qpos
        box_xyz = [float(x) for x in qpos[-7:-4]]
        qvel = self.physics.data.qvel
        box_vel = [float(x) for x in qvel[-6:-3]]
        stage = 0
        if touch_right:
            stage = 1
        if touch_right and not touch_table:
            stage = 2
        if touch_left:
            stage = 3
        if touch_left and not touch_table:
            stage = 4
        return {"touch_left": touch_left, "touch_right": touch_right,
                "touch_table": touch_table, "env_style_left": env_style_left,
                "off_table": (not touch_table), "stage": stage,
                "box_xyz": box_xyz, "box_speed": float(sum(v * v for v in box_vel) ** 0.5)}

    def gripper_xpos(self, name):
        gid = self.geom_ids[name]
        return [float(x) for x in self.physics.data.geom_xpos[gid]]


def dist(a, b):
    return float(sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5)


def build_policy(args):
    import torch
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.policies.pi05.modeling_pi05 import PI05Policy

    t0 = time.perf_counter()
    policy = PI05Policy.from_pretrained(args.weights_dir)
    t_load = time.perf_counter() - t0
    cfg = policy.config
    policy = policy.to(args.device).eval()
    if args.device.startswith("cuda"):
        torch.cuda.synchronize()
    preprocess, postprocess = make_pre_post_processors(
        cfg, args.weights_dir,
        preprocessor_overrides={
            "device_processor": {"device": str(args.device)},
            "tokenizer_processor": {"tokenizer_name": args.tokenizer_dir},
        },
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )
    info = {"load_s": round(t_load, 2), "chunk_size": int(cfg.chunk_size),
            "n_action_steps": int(cfg.n_action_steps), "max_action_dim": int(cfg.max_action_dim),
            "num_inference_steps": int(cfg.num_inference_steps), "device": str(args.device),
            "gpu_after_load": gpu_stats()}
    return policy, preprocess, postprocess, cfg, info


def render_obs(env, args, cam_map):
    import numpy as np
    physics = env.unwrapped._env.physics
    h = w = args.image_size
    imgs = {}
    t0 = time.perf_counter()
    for key, cam in cam_map.items():
        a = physics.render(height=h, width=w, camera_id=cam)
        imgs[key] = np.asarray(a).transpose(2, 0, 1).astype("float32") / 255.0
    state = np.asarray(env.unwrapped._env.task.get_qpos(physics), dtype="float32")
    return imgs, state, time.perf_counter() - t0


def adapt_action(a32, lo, hi, clip_stats):
    """32 维模型输出 -> gym-aloha 的 14 维动作。**假设**槽位顺序 = ALOHA 约定（见文件头）。"""
    import numpy as np
    a = np.asarray(a32, dtype="float64").reshape(-1)[:14].copy()
    raw = a.copy()
    idx_arms = list(range(0, 6)) + list(range(7, 13))
    act_idx = list(range(0, 6)) + list(range(8, 14))
    for k, ai in zip(idx_arms, act_idx):
        a[k] = min(max(a[k], lo[ai]), hi[ai])
    for gi in (6, 13):
        a[gi] = min(max(a[gi], 0.0), 1.0)
    clipped = np.abs(a - raw) > 1e-9
    clip_stats["n_values"] += a.size
    clip_stats["n_clipped"] += int(clipped.sum())
    clip_stats["max_clip_magnitude"] = max(clip_stats["max_clip_magnitude"],
                                           float(np.abs(a - raw).max()) if a.size else 0.0)
    clip_stats["raw_absmax"] = max(clip_stats["raw_absmax"], float(np.abs(raw).max()))
    return a.astype("float32")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=["pi05", "random"], required=True)
    ap.add_argument("--weights-dir")
    ap.add_argument("--tokenizer-dir")
    ap.add_argument("--env-id", default="gym_aloha/AlohaTransferCube-v0")
    ap.add_argument("--n-episodes", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--max-steps", type=int, default=300, help="env 注册时 max_episode_steps=300")
    ap.add_argument("--task", default="Transfer the red cube from the right arm to the left arm.")
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--base-camera", default="angle")
    ap.add_argument("--grasp-sustain-steps", type=int, default=10)
    ap.add_argument("--action-mode", choices=["queue", "select_action"], default="queue")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--save-frames-episodes", default="0", help="逗号分隔的 episode 序号，存 3 帧证据图")
    args = ap.parse_args()

    if args.policy == "pi05" and not (args.weights_dir and args.tokenizer_dir):
        print("--policy pi05 需要 --weights-dir 与 --tokenizer-dir", file=sys.stderr)
        return 2

    import numpy as np
    import torch
    import gymnasium as gym
    import gym_aloha  # noqa: F401  注册 env
    from gym_aloha.constants import DT, JOINTS

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cam_map = {"observation.images.base_0_rgb": args.base_camera,
               "observation.images.left_wrist_0_rgb": "left_wrist",
               "observation.images.right_wrist_0_rgb": "right_wrist"}

    rep = {"probe": "a2_pi05_zeroshot", "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "generator": "scripts/a2_pi05_zeroshot_eval.py", "args": vars(args),
           "morphology": "aloha_bimanual_14d",          # D §11.2 要求产物必须带这个标注
           "env_id": args.env_id, "policy_kind": args.policy,
           "python": sys.version.split()[0], "platform": platform.platform(),
           "mujoco_gl": os.environ.get("MUJOCO_GL"), "control_dt": DT, "joint_names": JOINTS,
           "camera_map": cam_map, "load_before": load_snapshot(), "versions": {}}
    import importlib.metadata as md
    for m in ("torch", "transformers", "lerobot", "gym-aloha", "mujoco", "numpy", "gymnasium"):
        try:
            rep["versions"][m] = md.version(m)
        except Exception:
            rep["versions"][m] = None

    policy = preprocess = postprocess = cfg = None
    if args.policy == "pi05":
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        policy, preprocess, postprocess, cfg, rep["model"] = build_policy(args)
        rep["versions"]["torch.__version__"] = torch.__version__
        print(f"[model] loaded in {rep['model']['load_s']}s chunk={cfg.chunk_size} "
              f"n_action_steps={cfg.n_action_steps}", flush=True)
    else:
        rep["versions"]["torch.__version__"] = torch.__version__

    env = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    physics0 = env.unwrapped._env.physics
    lo = np.asarray(physics0.model.actuator_ctrlrange[:, 0], dtype="float64")
    hi = np.asarray(physics0.model.actuator_ctrlrange[:, 1], dtype="float64")
    rep["actuator_ctrlrange"] = [[float(a), float(b)] for a, b in zip(lo, hi)]
    rep["env_action_space"] = {"low": float(env.action_space.low.min()), "high": float(env.action_space.high.max()),
                               "shape": list(env.action_space.shape),
                               "note": ("声明是 Box(-1,1)，但 arm 维在 before_step 里被当作"
                                        "**绝对关节角(rad)** 直接写进 ctrl（sim.py:38-55），"
                                        "夹爪维被当作**归一化开合度 0..1**；声明与语义不一致，"
                                        "MuJoCo 的 ctrllimited 会再夹一次（bimanual_viperx_transfer_cube.xml:17-33）。")}
    clip_stats = {"n_values": 0, "n_clipped": 0, "max_clip_magnitude": 0.0, "raw_absmax": 0.0}

    save_frames = {int(x) for x in str(args.save_frames_episodes).split(",") if x.strip() != ""}
    frames_dir = out_dir / f"frames_{args.policy}"
    if save_frames:
        frames_dir.mkdir(parents=True, exist_ok=True)

    episodes = []
    t_all0 = time.perf_counter()
    for ep in range(args.n_episodes):
        seed = args.seed0 + ep
        probe = None
        ep_load0 = load_snapshot()
        t_ep0 = time.perf_counter()
        obs, info = env.reset(seed=seed)
        probe = SceneProbe(env.unwrapped._env.physics)
        rng = np.random.default_rng(seed + 777)
        queue: list = []
        n_infer = 0
        t_infer = 0.0
        t_env = 0.0
        t_render = 0.0
        hold_run = 0
        max_hold_run = 0
        max_stage = 0
        max_reward = 0.0
        stage_hist = [0] * 5
        env_success = False
        grasp_truth = False
        flick_candidate = False
        steps = 0
        box_z_max = -1e9
        d_left_min = 1e9
        d_right_min = 1e9
        box0 = probe.sample()["box_xyz"]
        box_final = box0
        speed_at_success = None
        z_at_success = None
        terminal_reason = "limit"
        frame_store = []

        for step in range(args.max_steps):
            if args.policy == "pi05":
                if args.action_mode == "queue":
                    if not queue:
                        imgs, state, dt_r = render_obs(env, args, cam_map)
                        t_render += dt_r
                        batch = {k: torch.from_numpy(v) for k, v in imgs.items()}
                        batch["observation.state"] = torch.from_numpy(state)
                        batch["task"] = args.task
                        if torch.cuda.is_available():
                            torch.cuda.synchronize()
                        t0 = time.perf_counter()
                        b = preprocess(batch)
                        with torch.inference_mode():
                            chunk = policy.predict_action_chunk(b)
                        chunk = postprocess(chunk)
                        if torch.cuda.is_available():
                            torch.cuda.synchronize()
                        t_infer += time.perf_counter() - t0
                        n_infer += 1
                        c = chunk.detach().to("cpu").numpy()
                        if c.ndim == 3:
                            c = c[0]
                        if c.shape[0] != int(cfg.n_action_steps):
                            raise RuntimeError(f"chunk 长度 {c.shape[0]} != n_action_steps {cfg.n_action_steps}"
                                               " ⇒ 队列语义与 select_action 不等价，停下报 D")
                        queue = list(c)
                    a32 = queue.pop(0)
                else:
                    imgs, state, dt_r = render_obs(env, args, cam_map)
                    t_render += dt_r
                    batch = {k: torch.from_numpy(v) for k, v in imgs.items()}
                    batch["observation.state"] = torch.from_numpy(state)
                    batch["task"] = args.task
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                    t0 = time.perf_counter()
                    b = preprocess(batch)
                    with torch.inference_mode():
                        act = policy.select_action(b)
                    act = postprocess(act)
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                    t_infer += time.perf_counter() - t0
                    n_infer += 1
                    a32 = act.detach().to("cpu").numpy().reshape(-1)
                action = adapt_action(a32, lo, hi, clip_stats)
            else:
                action = rng.uniform(env.action_space.low, env.action_space.high).astype("float32")

            t0 = time.perf_counter()
            obs, reward, terminated, truncated, info = env.step(action)
            t_env += time.perf_counter() - t0
            steps += 1
            max_reward = max(max_reward, float(reward))

            s = probe.sample()
            stage_hist[s["stage"]] += 1
            max_stage = max(max_stage, s["stage"])
            box_final = s["box_xyz"]
            box_z_max = max(box_z_max, s["box_xyz"][2])
            d_left_min = min(d_left_min, dist(s["box_xyz"], probe.gripper_xpos(LEFT_FINGERS[0])))
            d_right_min = min(d_right_min, dist(s["box_xyz"], probe.gripper_xpos(RIGHT_FINGERS[0])))
            if s["touch_left"] and s["off_table"]:
                hold_run += 1
                max_hold_run = max(max_hold_run, hold_run)
                if max_hold_run >= args.grasp_sustain_steps:
                    grasp_truth = True
            else:
                hold_run = 0
            if bool(info.get("is_success")):
                env_success = True
                speed_at_success = s["box_speed"]
                z_at_success = s["box_xyz"][2]
                terminal_reason = "env_success(reward==4)"
            if ep in save_frames and steps in (1, args.max_steps // 2, args.max_steps):
                frame_store.append((steps, imgs if args.policy == "pi05" else None))
            if terminated or truncated:
                if truncated and not terminated:
                    terminal_reason = "time_limit"
                break

        if env_success and not grasp_truth:
            flick_candidate = True
        wall = time.perf_counter() - t_ep0
        ep_load1 = load_snapshot()
        rec = {"episode": ep, "seed": seed, "steps": steps, "wall_s": round(wall, 2),
               "terminal_reason": terminal_reason,
               "env_success": env_success, "grasp_truth": grasp_truth, "flick_candidate": flick_candidate,
               "max_stage": max_stage, "max_stage_name": STAGE_NAMES[max_stage],
               "max_reward": max_reward, "stage_hist_steps": stage_hist,
               "max_hold_run_steps": max_hold_run, "grasp_sustain_threshold_steps": args.grasp_sustain_steps,
               "box_start_xyz": [round(x, 4) for x in box0],
               "box_final_xyz": [round(x, 4) for x in box_final],
               "box_z_max": round(box_z_max, 4),
               "box_speed_at_env_success": None if speed_at_success is None else round(speed_at_success, 4),
               "box_z_at_env_success": None if z_at_success is None else round(z_at_success, 4),
               "min_dist_box_to_left_finger_m": round(d_left_min, 4),
               "min_dist_box_to_right_finger_m": round(d_right_min, 4),
               "n_inference_calls": n_infer, "t_inference_s": round(t_infer, 2),
               "t_env_step_s": round(t_env, 2), "t_render_s": round(t_render, 2),
               "env_step_fps": round(steps / t_env, 2) if t_env > 0 else None,
               "loop_fps": round(steps / wall, 2) if wall > 0 else None,
               "load_before": ep_load0, "load_after": ep_load1,
               "nr_throttled_delta": (ep_load1["cpu_stat"].get("nr_throttled", 0)
                                      - ep_load0["cpu_stat"].get("nr_throttled", 0))}
        episodes.append(rec)
        print(f"[ep {ep:02d}] seed={seed} steps={steps} env_success={env_success} "
              f"grasp_truth={grasp_truth} max_stage={max_stage}({STAGE_NAMES[max_stage]}) "
              f"wall={wall:.1f}s loop_fps={rec['loop_fps']} env_fps={rec['env_step_fps']} "
              f"infer={n_infer}x/{t_infer:.1f}s nr_throttled_Δ={rec['nr_throttled_delta']}", flush=True)
        if frame_store:
            try:
                from PIL import Image
                for st, im in frame_store:
                    if im is None:
                        continue
                    arr = (np.clip(im["observation.images.base_0_rgb"].transpose(1, 2, 0), 0, 1) * 255).astype("uint8")
                    fp = frames_dir / f"ep{ep:02d}_step{st:03d}_base.png"
                    Image.fromarray(arr).save(fp)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] frame save failed: {exc}", flush=True)

    total_wall = time.perf_counter() - t_all0
    n = len(episodes)
    summary = {
        "policy_kind": args.policy, "env_id": args.env_id, "n_episodes": n,
        "morphology": "aloha_bimanual_14d",
        "success": {
            "env_success_count": sum(1 for e in episodes if e["env_success"]),
            "env_success_rate": round(sum(1 for e in episodes if e["env_success"]) / max(1, n), 4),
            "grasp_truth_count": sum(1 for e in episodes if e["grasp_truth"]),
            "grasp_truth_rate": round(sum(1 for e in episodes if e["grasp_truth"]) / max(1, n), 4),
            "flick_candidate_count": sum(1 for e in episodes if e["flick_candidate"]),
            "definition_env_success": "gym-aloha info['is_success'] == (reward==4) == touch_left_gripper(单指) and not touch_table",
            "definition_grasp_truth": ("左夹爪任一手指接触 red_box 且 red_box 不接触 table，"
                                       f"连续 ≥ {args.grasp_sustain_steps} 步（{args.grasp_sustain_steps * DT:.2f} s）"),
            "difference_explanation": ("env_success 是**瞬时**判据且只看一根手指 ⇒ 一次弹射/擦碰就可能触发；"
                                       "grasp_truth 要求**持续持物离桌** ⇒ flick_candidate = 两者之差，就是伪成功候选。"),
        },
        "stage_distribution": {
            "max_stage_hist": {STAGE_NAMES[i]: sum(1 for e in episodes if e["max_stage"] == i) for i in range(5)},
            "steps_per_stage_total": [sum(e["stage_hist_steps"][i] for e in episodes) for i in range(5)],
            "stage_names": STAGE_NAMES,
        },
        "timing": {
            "total_wall_s": round(total_wall, 2),
            "mean_episode_wall_s": round(sum(e["wall_s"] for e in episodes) / max(1, n), 2),
            "mean_steps": round(sum(e["steps"] for e in episodes) / max(1, n), 1),
            "mean_env_step_fps": round(sum(e["env_step_fps"] or 0 for e in episodes) / max(1, n), 2),
            "mean_loop_fps": round(sum(e["loop_fps"] or 0 for e in episodes) / max(1, n), 2),
            "mean_inference_calls_per_ep": round(sum(e["n_inference_calls"] for e in episodes) / max(1, n), 2),
            "mean_inference_s_per_ep": round(sum(e["t_inference_s"] for e in episodes) / max(1, n), 2),
            "note": ("env_step_fps = 纯 env stepping（含 gym-aloha 自己那 3 路 480×640 渲染）；"
                     "loop_fps = 整局口径（含推理/出队/判据）。**两者不得混用**（D §5 不得声称第 3 条）。"),
            "load_before": rep["load_before"], "load_after": load_snapshot(),
            "nr_throttled_delta_total": (load_snapshot()["cpu_stat"].get("nr_throttled", 0)
                                         - rep["load_before"]["cpu_stat"].get("nr_throttled", 0)),
        },
        "gpu": gpu_stats(),
    }
    if args.policy == "pi05":
        summary["action_adapter"] = {
            "status": "assumed_from_convention",
            "mapping": "model_out[0:14] -> gym_aloha action[0:14]",
            "assumed_order": JOINTS,
            "evidence": [
                "gym_aloha/constants.py: JOINTS/ACTIONS 的 14 维顺序（左臂6+左夹爪1+右臂6+右夹爪1）",
                "lerobot/envs/configs.py:87-108 AlohaEnv.features ACTION shape=(14,) —— lerobot 自己的 gym-aloha 评测口径",
                "openpi/π₀ 的 ALOHA 约定（external_unverified，未在本机核对）",
            ],
            "unknowns": [
                "π₀.₅ 的 32 个输出槽位各是什么，不由 base ckpt 携带（contract.json q2 = unknown）",
                "输出的物理单位（rad / m / 归一化）无数据集统计量 ⇒ unknown（contract.json q3）",
            ],
            "clip": dict(clip_stats),
            "clip_fraction": round(clip_stats["n_clipped"] / max(1, clip_stats["n_values"]), 6),
            "note": ("因为 q2/q3 未知，这里的裁剪失真是**实测量**：clip_fraction 高说明模型输出与"
                     "本环境动作尺度不匹配，那是 zero-shot 的**预期结果**，不是 bug。"),
        }
        summary["model"] = rep.get("model")
    summary["episodes"] = episodes

    (out_dir / f"summary_{args.policy}.json").write_text(
        json.dumps({"report": {k: v for k, v in rep.items() if k != "episodes"}, "summary": summary},
                   ensure_ascii=False, indent=1, default=str))
    print(f"[written] {out_dir / f'summary_{args.policy}.json'}", flush=True)
    print(f"[done] env_success={summary['success']['env_success_count']}/{n} "
          f"grasp_truth={summary['success']['grasp_truth_count']}/{n} "
          f"flick_candidates={summary['success']['flick_candidate_count']} "
          f"wall={total_wall:.0f}s", flush=True)
    env.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
