#!/usr/bin/env python3
"""A2 / G2 —— π₀.₅ 动作与时间契约**实测**（v4 §12 P0 的核心交付）。

依据 `rl_harness_supervision/d_handoff_to_a2_20260929.md` §4、§11.3。
要回答的不是"能不能跑"，而是**六个契约问题**：
  ① chunk 长度；② 单步动作维度与顺序；③ 单位；④ 参考系；⑤ 夹爪语义；⑥ 推理延迟（首帧/稳态分开）。
**能从 ckpt/实测拿到的就填实，拿不到的一律 `unknown` + 说明为什么拿不到，不许猜**
（`02_开发实施指南.md:7`：未知保留 null，不用论文默认值猜）。

观测用 **gym-aloha 的真实渲染帧**（不是随机张量），这样 G2 与 G3 的观测管线是同一套：
  base_0_rgb          <- camera "angle"（外部视角）
  left_wrist_0_rgb    <- camera "left_wrist"
  right_wrist_0_rgb   <- camera "right_wrist"
  observation.state   <- gym-aloha `get_qpos()` 的 14 维（左臂6+左夹爪1+右臂6+右夹爪1）

用法：
  MUJOCO_GL=egl python scripts/a2_pi05_contract_probe.py \
      --weights-dir <NFS>/lerobot/pi05_base \
      --tokenizer-dir <NFS>/google/paligemma-3b-pt-224 \
      --out runs/vla/a2_pi05_contract_20260929/contract.json
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

# gym-aloha 的 dm_control 渲染必须在 import 前定好后端，否则 reset() 直接 FatalError
os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("OMP_NUM_THREADS", "4")


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
            "cpu_stat": stat, "ts": datetime.now().astimezone().isoformat(timespec="seconds")}


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


def make_physics(args):
    """用**真的 `env.reset(seed=...)`** 建一个可复用的 physics 句柄。

    为什么不用 `Physics.from_xml_path()`（本脚本第一版就是这么写的，**是个缺陷**）：
    XML 默认位姿下 14 维 state 是「6 关节全 0 + 夹爪 -0.466」，既不是一局真实起点，
    又把「state 超出 [-1,1] 会被静默离散化饱和」这条**测小了**——真实起点
    `START_ARM_POSE`（gym_aloha/constants.py:53-70）里 `elbow = 1.16 > 1`，
    正是要量化的那一维。走 `env.reset()` 才能同时拿到 START_ARM_POSE 与采样过的 box 位姿。
    """
    import gymnasium as gym
    import gym_aloha  # noqa: F401  注册 env

    env = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    env.reset(seed=args.seed)
    inner = env.unwrapped._env
    return inner.physics, f"{args.env_id} (task={type(inner.task).__name__}, reset seed={args.seed})", env


def build_observation(args, physics):
    """用 gym-aloha 的真实场景渲染 π₀.₅ 要的三路 224² 图像 + 14 维 state。"""
    import numpy as np
    import mujoco
    from gym_aloha.tasks.sim import BimanualViperXTask

    h = w = args.image_size
    cam_map = {"observation.images.base_0_rgb": args.base_camera,
               "observation.images.left_wrist_0_rgb": "left_wrist",
               "observation.images.right_wrist_0_rgb": "right_wrist"}
    imgs = {}
    for key, cam in cam_map.items():
        a = physics.render(height=h, width=w, camera_id=cam)      # (H,W,3) uint8
        a = np.asarray(a).transpose(2, 0, 1).astype("float32") / 255.0   # -> (3,H,W) [0,1]
        imgs[key] = a
    state = BimanualViperXTask.get_qpos(physics)                   # 14 维
    return imgs, np.asarray(state, dtype="float32"), cam_map, \
        sorted(mujoco.mj_id2name(physics.model.ptr, mujoco.mjtObj.mjOBJ_CAMERA, i)
               for i in range(physics.model.ncam))


def advance_physics(physics, n_steps, rng, scale=0.08):
    """在当前 qpos 附近做随机游走并 step n_steps 次，返回**活性证据**。

    活性纪律来自 G0.5 的教训（探针自己没推进仿真 ⇒ 8/8 档假红）：
    这里**推进后 state 与图像都必须变**，否则「观测敏感性」判据会把
    "探针没换观测" 误报成 "图像没进模型"。不变 ⇒ **响亮失败**，不出报告。
    """
    import numpy as np

    q_before = np.asarray(physics.data.qpos[:16], dtype="float64").copy()
    img_before = np.asarray(physics.render(height=64, width=64, camera_id="top"), dtype="float64")
    lo = np.asarray(physics.model.actuator_ctrlrange[:, 0], dtype="float64")
    hi = np.asarray(physics.model.actuator_ctrlrange[:, 1], dtype="float64")
    for _ in range(n_steps):
        target = np.asarray(physics.data.qpos[:16], dtype="float64") + rng.normal(0.0, scale, size=16)
        physics.data.ctrl[:] = np.clip(target, lo, hi)
        physics.step()
    q_after = np.asarray(physics.data.qpos[:16], dtype="float64")
    img_after = np.asarray(physics.render(height=64, width=64, camera_id="top"), dtype="float64")
    live = {
        "n_steps": int(n_steps),
        "qpos_max_abs_delta": float(np.abs(q_after - q_before).max()),
        "image_mean_abs_delta_uint8": round(float(np.abs(img_after - img_before).mean()), 4),
        "image_max_abs_delta_uint8": float(np.abs(img_after - img_before).max()),
    }
    live["changed"] = bool(live["qpos_max_abs_delta"] > 1e-9 and live["image_max_abs_delta_uint8"] > 0)
    if not live["changed"]:
        raise RuntimeError(f"liveness check failed: physics did not advance -> {live}")
    return live


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights-dir", required=True)
    ap.add_argument("--tokenizer-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--task", default="Transfer the red cube from the right arm to the left arm.")
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--base-camera", default="angle")
    ap.add_argument("--repeat", type=int, default=12, help="稳态延迟的重复次数")
    ap.add_argument("--n-obs", type=int, default=4, help="换几组不同观测看动作是否随观测变化")
    ap.add_argument("--advance-steps", type=int, default=10,
                    help="换观测前推进多少个控制步（DT=0.02 ⇒ 10 步 = 0.2 s 仿真时间）")
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--env-id", default="gym_aloha/AlohaTransferCube-v0",
                    help="G2 的观测来源；与 G3 同一个 env，保证两条产物共用一套观测管线")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    import numpy as np
    import torch
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.policies.pi05.configuration_pi05 import PI05Config
    from lerobot.policies.pi05.modeling_pi05 import PI05Policy

    rep: dict = {
        "probe": "a2_pi05_contract",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_pi05_contract_probe.py",
        "args": vars(args),
        "morphology": "aloha_bimanual_14d",        # D §11.2 要求产物必须带这个标注
        "python": sys.version.split()[0], "platform": platform.platform(),
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "load_before": load_snapshot(),
        "versions": {},
    }
    import importlib.metadata as md
    for m in ("torch", "transformers", "lerobot", "safetensors", "accelerate", "gym-aloha", "mujoco", "numpy"):
        try:
            rep["versions"][m] = md.version(m)
        except Exception:
            rep["versions"][m] = None
    rep["versions"]["torch.__version__"] = torch.__version__

    # ---------------- 1. 加载 ----------------
    torch.cuda.reset_peak_memory_stats() if torch.cuda.is_available() else None
    t0 = time.perf_counter()
    policy = PI05Policy.from_pretrained(args.weights_dir)
    t_load_cpu = time.perf_counter() - t0
    cfg: PI05Config = policy.config
    n_params = sum(p.numel() for p in policy.parameters())
    dtypes = {str(p.dtype) for p in policy.parameters()}
    rep["load"] = {
        "from_pretrained_s": round(t_load_cpu, 2),
        "n_parameters": n_params,
        "n_parameters_billion": round(n_params / 1e9, 4),
        "param_dtypes": sorted(dtypes),
        "config_dtype_field": cfg.dtype,
        "config_device_as_shipped": getattr(cfg, "device", None),
        "gpu_before_to_device": gpu_stats(),
    }
    t0 = time.perf_counter()
    policy = policy.to(args.device).eval()
    if args.device.startswith("cuda"):
        torch.cuda.synchronize()
    rep["load"]["to_device_s"] = round(time.perf_counter() - t0, 2)
    rep["load"]["gpu_after_to_device"] = gpu_stats()
    print(f"[load] from_pretrained={t_load_cpu:.1f}s params={n_params/1e9:.3f}B "
          f"dtypes={sorted(dtypes)} gpu={rep['load']['gpu_after_to_device']}", flush=True)

    # ---------------- 2. 处理器管线 ----------------
    t0 = time.perf_counter()
    preprocess, postprocess = make_pre_post_processors(
        cfg, args.weights_dir,
        preprocessor_overrides={
            "device_processor": {"device": str(args.device)},
            "tokenizer_processor": {"tokenizer_name": args.tokenizer_dir},   # 本地路径：HF 上该仓 gated=403
        },
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )
    rep["processors"] = {"build_s": round(time.perf_counter() - t0, 2),
                         "tokenizer_dir": args.tokenizer_dir,
                         "pre_steps": [type(s).__name__ for s in getattr(preprocess, "steps", [])],
                         "post_steps": [type(s).__name__ for s in getattr(postprocess, "steps", [])]}
    print(f"[processors] pre={rep['processors']['pre_steps']}", flush=True)
    print(f"[processors] post={rep['processors']['post_steps']}", flush=True)

    # 归一化统计量到底有没有 —— 这条决定 ③④⑤ 能不能填实
    norm_info = {}
    for s in getattr(preprocess, "steps", []):
        if type(s).__name__ == "NormalizerProcessorStep":
            st = getattr(s, "stats", None)
            norm_info["pre_normalizer_stats_present"] = bool(st)
            norm_info["pre_normalizer_stats_keys"] = sorted(st.keys()) if isinstance(st, dict) else str(type(st))
            norm_info["pre_normalizer_norm_map"] = str(getattr(s, "norm_map", None))[:300]
        if type(s).__name__ == "Pi05PrepareStateTokenizerProcessorStep":
            norm_info["state_tokenizer_max_state_dim"] = getattr(s, "max_state_dim", None)
    for s in getattr(postprocess, "steps", []):
        if type(s).__name__ == "UnnormalizerProcessorStep":
            st = getattr(s, "stats", None)
            norm_info["post_unnormalizer_stats_present"] = bool(st)
    rep["normalization"] = norm_info
    print(f"[normalization] {json.dumps(norm_info, ensure_ascii=False)[:400]}", flush=True)

    # ---------------- 3. 真实观测 ----------------
    physics, xml, env = make_physics(args)
    rng = np.random.default_rng(args.seed)
    imgs, state, cam_map, all_cams = build_observation(args, physics)
    rep["observation"] = {
        "source_xml": xml, "camera_map": cam_map, "model_cameras_available": all_cams,
        "image_shape": {k: list(v.shape) for k, v in imgs.items()},
        "image_dtype": "float32 in [0,1]",
        "image_stats": {k: {"min": float(v.min()), "max": float(v.max()),
                            "mean": round(float(v.mean()), 4), "std": round(float(v.std()), 4)}
                        for k, v in imgs.items()},
        "state_raw_14d": [round(float(x), 6) for x in state],
        "state_dim_from_env": int(state.shape[0]),
        "state_semantics": ("gym-aloha BimanualViperXTask.get_qpos()："
                            "[左臂 joint x6 (rad), 左夹爪 normalized 0..1, 右臂 joint x6 (rad), 右夹爪 normalized 0..1]"),
    }
    print(f"[obs] images={ {k: list(v.shape) for k, v in imgs.items()} } state_dim={state.shape}", flush=True)

    # state 饱和量化：processor 假定 state 已在 [-1,1]，超出就贴到端点 bin
    sat = np.clip(state, -1, 1)
    rep["state_saturation"] = {
        "n_dims": int(state.size),
        "n_dims_outside_[-1,1]": int((np.abs(state) > 1).sum()),
        "dims_outside": [int(i) for i in np.where(np.abs(state) > 1)[0]],
        "max_abs": round(float(np.abs(state).max()), 4),
        "note": ("Pi05PrepareStateTokenizerProcessorStep 用 np.digitize(state, linspace(-1,1,257)[:-1]) 离散化，"
                 "注释明写 'State should already be normalized to [-1,1] by the NormalizerProcessorStep'。"
                 "但 base ckpt 的 normalizer features={} ⇒ **不做任何归一化**，"
                 "所以超出 [-1,1] 的维度会**静默饱和到端点 bin**（信息丢失且不报错）。"),
    }
    print(f"[state] 超出[-1,1]的维度数={rep['state_saturation']['n_dims_outside_[-1,1]']}/{state.size} "
          f"max|state|={rep['state_saturation']['max_abs']}", flush=True)

    # ---------------- 4. 前向：chunk 形状 + 延迟 ----------------
    def make_batch(img_dict, st):
        b = {k: torch.from_numpy(v) for k, v in img_dict.items()}
        b["observation.state"] = torch.from_numpy(np.asarray(st, dtype="float32"))
        b["task"] = args.task
        return b

    lat_first = None
    chunks = []
    lat_steady = []
    liveness = []
    obs_states = []
    for i in range(args.n_obs):
        # 每组观测**真的推进仿真**若干个控制步，保证图像与 state 变了（同 G0.5 的活性纪律）
        if i > 0:
            liveness.append(advance_physics(physics, args.advance_steps, rng))
            imgs, state, _, _ = build_observation(args, physics)
            print(f"[advance {i}] qpos_Δmax={liveness[-1]['qpos_max_abs_delta']:.4f} "
                  f"img_Δmean={liveness[-1]['image_mean_abs_delta_uint8']} state[:3]="
                  f"{[round(float(x), 4) for x in state[:3]]}", flush=True)
        batch = preprocess(make_batch(imgs, state))
        obs_states.append([round(float(x), 6) for x in state])
        rep.setdefault("batch_keys", sorted([str(k) for k in batch.keys()]))
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.inference_mode():
            chunk = policy.predict_action_chunk(batch)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        dt = time.perf_counter() - t0
        if lat_first is None:
            lat_first = dt
        else:
            lat_steady.append(dt)
        chunk = postprocess(chunk)
        c = chunk.detach().to("cpu").numpy()
        chunks.append(c)
        print(f"[fwd {i}] chunk={c.shape} latency={dt:.3f}s "
              f"absmax={np.abs(c).max():.4f} gpu_peak={gpu_stats().get('max_allocated_MiB')}MiB", flush=True)

    c0 = chunks[0]
    rep["forward"] = {
        "chunk_shape": list(c0.shape),
        "chunk_len_steps": int(c0.shape[1]) if c0.ndim == 3 else None,
        "action_dim": int(c0.shape[-1]),
        "config_chunk_size": cfg.chunk_size,
        "config_n_action_steps": cfg.n_action_steps,
        "config_max_action_dim": cfg.max_action_dim,
        "config_num_inference_steps": cfg.num_inference_steps,
        "n_obs": len(chunks),
        "latency_first_s": round(lat_first, 4),
        "latency_steady_mean_s": round(float(np.mean(lat_steady)), 4) if lat_steady else None,
        "latency_steady_std_s": round(float(np.std(lat_steady)), 4) if lat_steady else None,
        "latency_steady_all_s": [round(x, 4) for x in lat_steady],
        "per_chunk_s_per_step": round(float(np.mean(lat_steady)) / max(1, c0.shape[1]), 5) if lat_steady else None,
        "gpu": gpu_stats(),
        "load_after_forward": load_snapshot(),
    }

    # 动作统计：哪些维度是"活的"，哪些恒为 0（padding）
    per_dim = []
    for d in range(c0.shape[-1]):
        vals = np.concatenate([c[:, :, d].ravel() for c in chunks])
        per_dim.append({"dim": d, "mean": round(float(vals.mean()), 6),
                        "std": round(float(vals.std()), 6),
                        "min": round(float(vals.min()), 6), "max": round(float(vals.max()), 6),
                        "absmax": round(float(np.abs(vals).max()), 6),
                        "degenerate": bool(vals.std() < 1e-8)})
    rep["action_dim_stats"] = per_dim

    # ---- state ↔ action 对应关系 ----
    # 动机：ckpt 不带 embodiment 槽位语义（q2 = unknown），但**绝对关节位置控制**的策略
    # 在一局起点附近应当输出「≈ 当前 state + 小增量」。若 action[0:14] 与 state[0:14]
    # 逐维接近，那就是「前 14 维 = ALOHA 14 维、单位与 state 同」的**经验证据**（仍非证明）。
    # 判据要能红：若逐维 |action-state| 与 state 本身量级同阶甚至更大 ⇒ 假设不成立。
    st_arr = np.asarray(obs_states, dtype="float64")                     # (n_obs, 14)
    ac_arr = np.asarray([c[0, 0, :] for c in chunks], dtype="float64")    # 每 chunk 第 1 步 (n_obs, 32)
    corr_rows = []
    for d in range(ac_arr.shape[1]):
        row = {"action_dim": d,
               "action_mean": round(float(ac_arr[:, d].mean()), 5),
               "action_std": round(float(ac_arr[:, d].std()), 5)}
        if d < st_arr.shape[1]:
            diff = ac_arr[:, d] - st_arr[:, d]
            denom = max(float(np.abs(st_arr[:, d]).mean()), 1e-6)
            row.update({"state_dim_compared": d,
                        "state_mean": round(float(st_arr[:, d].mean()), 5),
                        "state_absmean": round(float(np.abs(st_arr[:, d]).mean()), 5),
                        "mean_abs_action_minus_state": round(float(np.abs(diff).mean()), 5),
                        "rel_dev_vs_state_scale": round(float(np.abs(diff).mean()) / denom, 4)})
        corr_rows.append(row)
    first14 = [r for r in corr_rows if "rel_dev_vs_state_scale" in r]
    pad = [r for r in corr_rows if "rel_dev_vs_state_scale" not in r]
    rep["state_action_correspondence"] = {
        "n_obs": len(chunks),
        "per_dim": corr_rows,
        "first14_mean_rel_dev": round(float(np.mean([r["rel_dev_vs_state_scale"] for r in first14])), 4),
        "first14_mean_abs_diff": round(float(np.mean([r["mean_abs_action_minus_state"] for r in first14])), 5),
        "pad_dims_absmean": round(float(np.mean([abs(r["action_mean"]) for r in pad])), 5) if pad else None,
        "interpretation": ("first14_mean_rel_dev << 1 ⇒ 前 14 维与 state 的 14 维**同尺度同单位**（绝对关节位置）；"
                           ">= 1 ⇒ 该假设不成立。padding 区（14..31）的 absmean 只说明模型在 padding 槽位也吐了"
                           "非零值，**不能**据此推断语义。"),
        "status": "empirical_evidence_not_proof",
    }
    print(f"[corr] first14_mean_rel_dev={rep['state_action_correspondence']['first14_mean_rel_dev']} "
          f"first14_mean_abs_diff={rep['state_action_correspondence']['first14_mean_abs_diff']} "
          f"pad_absmean={rep['state_action_correspondence']['pad_dims_absmean']}", flush=True)
    rep["action_dims_nondegenerate"] = [p["dim"] for p in per_dim if not p["degenerate"]]
    rep["action_dims_degenerate"] = [p["dim"] for p in per_dim if p["degenerate"]]
    # 观测敏感性：换观测后动作变不变（判据要能红：不变 ⇒ 图像/状态没真进模型）
    if len(chunks) >= 2:
        d01 = float(np.abs(chunks[0] - chunks[1]).mean())
        dmax = max(float(np.abs(chunks[j] - chunks[j + 1]).mean()) for j in range(len(chunks) - 1))
        rep["observation_sensitivity"] = {
            "mean_abs_diff_chunk0_vs_chunk1": round(d01, 6),
            "changes_with_observation": bool(d01 > 1e-6),
            "max_mean_abs_diff_over_consecutive_pairs": round(dmax, 6),
            "liveness_evidence": liveness,
            "state_per_observation": obs_states,
            "n_observations": len(chunks),
            "note": "不同观测（推进了仿真）应给出不同动作；恒等 ⇒ 图像/state 没有真正进模型",
        }
    # 一个 chunk 内部的时序结构：动作是否随步变化（flow-matching 应给出轨迹而非重复帧）
    rep["chunk_temporal_structure"] = {
        "mean_abs_diff_between_consecutive_steps": round(
            float(np.abs(np.diff(c0[0], axis=0)).mean()), 6),
        "first_step": [round(float(x), 5) for x in c0[0, 0, :16]],
        "last_step": [round(float(x), 5) for x in c0[0, -1, :16]],
    }

    # ---------------- 5. 六问 ----------------
    rep["six_questions"] = {
        "q1_chunk_length": {
            "value": int(cfg.chunk_size), "unit": "control steps",
            "measured_chunk_shape": list(c0.shape),
            "n_action_steps": int(cfg.n_action_steps),
            "evidence": "config.chunk_size / 实测 predict_action_chunk 的第二维",
            "status": "measured",
            "note": ("select_action() 每次弹 1 步、内部维护长度 n_action_steps=%d 的队列；"
                     "predict_action_chunk() 一次给 (%d, %d)。" % (cfg.n_action_steps, cfg.chunk_size, c0.shape[-1])),
        },
        "q2_action_dim_and_order": {
            "value_dim": int(c0.shape[-1]),
            "measured_nondegenerate_dims": rep["action_dims_nondegenerate"],
            "measured_degenerate_dims": rep["action_dims_degenerate"],
            "status": "partially_measured",
            "evidence": "predict_action_chunk 输出的最后一维 + 逐维 std",
            "unknown": "**32 个槽位的语义（哪几维是左臂/右臂/夹爪）不由 base ckpt 携带**",
            "why_unknown": ("config.output_features['action'].shape=[32] 只是 max_action_dim 的 padding 上限；"
                            "槽位含义由**微调数据集**的 feature 顺序决定。pi05_base 是"
                            "'base model to fine tune on your specific use case'（README 原文），"
                            "checkpoint 里没有 embodiment 映射表 ⇒ 不许猜。"),
        },
        "q3_units": {
            "value": None, "status": "unknown",
            "evidence": ("policy_preprocessor.json 的 normalizer_processor.config.features = {} （空），"
                          "norm_map 却是 STATE/ACTION → QUANTILES ⇒ **base ckpt 不带任何归一化统计量**；"
                          "postprocessor 的 unnormalizer 同样无 stats ⇒ 输出没有被反归一化到任何物理单位。"),
            "measured_output_range": {"min": round(float(c0.min()), 5), "max": round(float(c0.max()), 5),
                                      "absmax": round(float(np.abs(c0).max()), 5)},
            "why_unknown": "没有数据集统计量就没有'从模型内部空间到弧度/米'的映射；只能标 unknown。",
        },
        "q4_reference_frame": {
            "value_relative_or_absolute": "absolute",
            "status": "partially_measured",
            "evidence": ("policy_preprocessor.json 的 relative_actions_processor.enabled = **false**，"
                          "postprocessor 的 absolute_actions_processor.enabled = false ⇒ **不是增量动作**。"),
            "unknown": "绝对量所在的**坐标系/空间**（关节空间 vs 末端位姿；base frame vs world）由数据集决定 ⇒ unknown",
        },
        "q5_gripper_semantics": {
            "value": None, "status": "unknown",
            "why_unknown": ("同 q2/q3：哪一维是夹爪、连续开合度还是二值，都由微调数据集定义。"
                            "（对照：**gym-aloha 侧是实测已知的** —— 连续归一化开合度 0=close/1=open，"
                            "见 sim.py:before_step 的 unnormalize_puppet_gripper_position）"),
        },
        "q6_inference_latency": {
            "status": "measured",
            "first_call_s": rep["forward"]["latency_first_s"],
            "steady_mean_s": rep["forward"]["latency_steady_mean_s"],
            "steady_std_s": rep["forward"]["latency_steady_std_s"],
            "includes_pre_post_processor": False,
            "note": ("首帧含 CUDA context/kernel 编译，**必须与稳态分开记**（D §4-②）。"
                     "本数字**未**含 preprocessor/postprocessor 开销，下面单列。"),
            "loadavg_during": rep["forward"]["load_after_forward"]["loadavg_1m"],
            "nr_throttled_delta": (rep["forward"]["load_after_forward"]["cpu_stat"].get("nr_throttled", 0)
                                   - rep["load_before"]["cpu_stat"].get("nr_throttled", 0)),
        },
    }

    # 含 pre/post 的端到端延迟（D §4-⑥ 要求"含 preprocessor/postprocessor 的开销"）
    e2e = []
    for _ in range(max(3, args.repeat // 3)):
        batch_raw = make_batch(imgs, state)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        b = preprocess(batch_raw)
        with torch.inference_mode():
            a = policy.select_action(b)
        a = postprocess(a)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        e2e.append(time.perf_counter() - t0)
    policy.reset()
    rep["six_questions"]["q6_inference_latency"]["end_to_end_select_action_s"] = {
        "mean": round(float(np.mean(e2e)), 4), "std": round(float(np.std(e2e)), 4),
        "all": [round(x, 4) for x in e2e],
        "note": "preprocess + select_action(单步出队) + postprocess，含 H2D 拷贝",
    }
    # select_action 的队列语义：连续调用 51 次，看第 1 次与后续的耗时差（第 1 次才真跑扩散）
    q_lat = []
    policy.reset()
    b = preprocess(make_batch(imgs, state))
    for i in range(int(cfg.n_action_steps) + 2):
        t0 = time.perf_counter()
        with torch.inference_mode():
            policy.select_action(b)
        q_lat.append(round(time.perf_counter() - t0, 5))
    nq = int(cfg.n_action_steps)
    rep["select_action_queue_latency_s"] = {
        "call_1_triggers_inference_s": q_lat[0],
        "calls_2_to_n_dequeue_mean_s": round(float(np.mean(q_lat[1:nq])), 6),
        "call_n_plus_1_queue_drained_triggers_inference_s": q_lat[nq],
        "call_n_plus_2_dequeue_s": q_lat[nq + 1],
        "all_calls_s": q_lat,
        "n_action_steps": nq,
        "note": ("第 1 次与第 n+1 次（队列耗尽）才真跑扩散（≈ chunk 推理），中间 %d 次只是出队 ⇒ "
                 "**控制回路的有效推理频率 = n_action_steps / chunk 推理耗时**，不是 1 / 单步耗时。"
                 "这条是 G3 的成本模型基础。（第一版把第 n+1 次混进了出队均值，标签已修正。）" % (nq - 1)),
    }
    print(f"[latency] first={rep['forward']['latency_first_s']}s "
          f"steady={rep['forward']['latency_steady_mean_s']}s "
          f"e2e={rep['six_questions']['q6_inference_latency']['end_to_end_select_action_s']['mean']}s", flush=True)

    rep["gpu_final"] = gpu_stats()
    rep["load_after"] = load_snapshot()
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print(f"[written] {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
