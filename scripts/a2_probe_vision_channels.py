#!/usr/bin/env python3
"""A2 / G0.5 —— 视觉通道预检（阻塞门）。

依据：`rl_harness_supervision/d_handoff_to_a2_20260929.md` §8.2。
π₀.₅ 是视觉语言模型（`config.json` 要 3 路 224x224 图像 + 32 维 state），
所以"本节点能不能喂 VLA 图像、fps 够不够闭环评测"是 P0 的真问题。

三条通道各在自己的 venv 里跑（包不在一起）：
    gym_aloha  -> /root/venvs/pi05_sim      (dm_control + mujoco 3.8.1)
    robosuite  -> /root/venvs/rlrobot       (robosuite 1.5.2 + mujoco 3.9.0)
    maniskill  -> .codex-persist/envs/maniskill_probe  (mani_skill3 + sapien)

用法：
    MUJOCO_GL=egl   python scripts/a2_probe_vision_channels.py --channel gym_aloha
    MUJOCO_GL=osmesa python scripts/a2_probe_vision_channels.py --channel robosuite
    xvfb-run -a     python scripts/a2_probe_vision_channels.py --channel maniskill

每档都记：能否出图 / 分辨率 / 相机数 / 首帧耗时 / 稳态 fps / RSS / loadavg / nr_throttled。
**吞吐数字必须成对引用负载**（§8.3：同一任务两轮差 1.94x，不记负载的 fps 在本节点没有意义）。
产物：runs/vla/a2_g05_vision_precheck_20260929/channel_<name>_<gl>_<ts>.json
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import re
import resource
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "runs" / "vla" / "a2_g05_vision_precheck_20260929"

# π₀.₅ config.json 的 image_resolution = [224, 224]，input_features 有 3 路 VISUAL：
# base_0_rgb / left_wrist_0_rgb / right_wrist_0_rgb  ⇒ "3 相机 224²" 是 VLA 的真实需求档。
DEFAULT_GRID = "224x224x1,224x224x3,256x256x3,480x640x1,480x640x3"


# ---------------------------------------------------------------- 负载与资源口径

def _read(path: str):
    try:
        return Path(path).read_text().strip()
    except Exception:
        return None


def cpu_quota() -> dict:
    """**分母用 cgroup 配额，不用 nproc**（nproc=112 是宿主口径，本容器只有 12 核）。"""
    v2 = _read("/sys/fs/cgroup/cpu.max")
    if v2:
        parts = v2.split()
        if parts[0] != "max":
            return {"cores": round(int(parts[0]) / int(parts[1]), 2), "raw": v2, "cgroup": "v2"}
        return {"cores": "max", "raw": v2, "cgroup": "v2"}
    q, p = _read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"), _read("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if q and p and int(q) > 0:
        return {"cores": round(int(q) / int(p), 2), "quota_us": int(q), "period_us": int(p), "cgroup": "v1"}
    return {"cores": None, "cgroup": "unknown"}


def cpu_stat() -> dict:
    txt = _read("/sys/fs/cgroup/cpu.stat") or _read("/sys/fs/cgroup/cpu/cpu.stat") or ""
    out = {}
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            out[parts[0]] = int(parts[1])
    return out


def load_snapshot() -> dict:
    la = os.getloadavg()
    return {
        "loadavg_1m": round(la[0], 2), "loadavg_5m": round(la[1], 2), "loadavg_15m": round(la[2], 2),
        "cpu_stat": cpu_stat(), "cpu_quota_cores": cpu_quota().get("cores"),
        "nproc_host_misleading": os.cpu_count(),
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def gpu_mem_mib() -> dict | None:
    """渲染是不是真的走了 GPU：显存占用 + nvidia-smi 里有没有本进程。"""
    try:
        import subprocess
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=30)
        used = [int(x) for x in out.stdout.split() if x.strip().isdigit()]
        ps = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30)
        return {"memory_used_mib": used, "compute_apps": ps.stdout.strip() or "(none)"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


GL_LIB_RE = re.compile(r"(libEGL_nvidia|libGLX_nvidia|libEGL_mesa|libGLX_mesa|libOSMesa|libGL\.so|"
                       r"lvp_icd|vulkan_radeon|nvidia_icd|libvulkan|swrast|libEGL\.so)")


def gl_libraries_loaded() -> dict:
    """**直接证据**：本进程真的把哪个 GL/EGL 实现映射进来了。

    比"猜后端"可靠：`MUJOCO_GL=egl` 只说明想用什么，maps 里出现 `libEGL_mesa` 才说明
    实际落到了 mesa 的软件 EGL（llvmpipe），出现 `libEGL_nvidia` 才是 GPU。
    """
    hits: dict[str, int] = {}
    try:
        for line in Path("/proc/self/maps").read_text().splitlines():
            m = GL_LIB_RE.search(line)
            if m:
                hits[m.group(1)] = hits.get(m.group(1), 0) + 1
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    loaded = sorted(hits)
    return {
        "loaded": loaded,
        "counts": hits,
        "nvidia_graphics_stack_present": any(x in hits for x in ("libEGL_nvidia", "libGLX_nvidia")),
        "software_gl_present": any(x in hits for x in ("libEGL_mesa", "libOSMesa", "swrast", "lvp_icd")),
    }


def gl_renderer_string() -> str | None:
    """能拿到就报 GL_RENDERER（llvmpipe / softpipe / NVIDIA …）；拿不到不算失败。"""
    try:
        from OpenGL.GL import glGetString  # noqa: PLC0415
        from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION  # noqa: PLC0415
        vals = [glGetString(x) for x in (GL_VENDOR, GL_RENDERER, GL_VERSION)]
        return " | ".join(v.decode() if isinstance(v, bytes) else str(v) for v in vals if v)
    except Exception as exc:  # noqa: BLE001
        return f"(unavailable: {type(exc).__name__}: {str(exc)[:80]})"


def pkg_versions(names) -> dict:
    import importlib.metadata as md
    out = {}
    for n in names:
        try:
            out[n] = md.version(n)
        except Exception:
            out[n] = None
    return out


# ---------------------------------------------------------------- 通用计时

def time_frames(render_once, n_frames: int, warmup: int = 3) -> dict:
    """首帧与稳态分开记（D §4-②：首帧含 context/编译开销，混在一起会骗人）。"""
    first = None
    for i in range(warmup):
        t = time.perf_counter()
        render_once()
        if i == 0:
            first = time.perf_counter() - t
    gc.collect()
    t0 = time.perf_counter()
    for _ in range(n_frames):
        render_once()
    dt = time.perf_counter() - t0
    return {
        "first_frame_s": round(first, 4) if first is not None else None,
        "warmup": warmup, "frames": n_frames,
        "steady_s": round(dt, 3), "steady_fps": round(n_frames / dt, 3) if dt > 0 else None,
    }


def image_stats(img) -> dict:
    """出图**不等于**出对图：全零/全同值就是"出了个寂寞"，必须判非平凡性。"""
    import numpy as np
    a = np.asarray(img)
    u = np.unique(a)
    return {
        "shape": list(a.shape), "dtype": str(a.dtype),
        "min": float(a.min()), "max": float(a.max()),
        "mean": round(float(a.mean()), 4), "std": round(float(a.std()), 4),
        "n_unique": int(u.size),
        "nonzero_frac": round(float((a != 0).mean()), 4),
        "non_trivial": bool(a.std() > 1e-6 and u.size > 8),
    }


def liveness_check(capture, advance, n_pairs: int = 3, action=None) -> dict:
    """**出图 ≠ 出对图**：证明图像真的随仿真前进而变，排除"渲染被缓存/返回同一张图"的假过。

    fps 几乎不随分辨率变化时（本轮 robosuite 64²=133 / 224²=140），这条检查是唯一能
    区分"渲染真便宜"与"根本没重画"的判据。判据要能红：图像不变 ⇒ changed=False。
    """
    import hashlib

    import numpy as np

    frames, hashes = [], []
    prev = None
    diffs = []
    for i in range(n_pairs + 1):
        img = np.asarray(capture())
        frames.append(img)
        h = hashlib.sha256(np.ascontiguousarray(img).tobytes()).hexdigest()[:16]
        hashes.append(h)
        if prev is not None:
            a, b = prev.astype(np.int32), img.astype(np.int32)
            d = np.abs(a - b)
            diffs.append({"mean_abs_diff": round(float(d.mean()), 4),
                          "frac_pixels_changed": round(float((d > 0).mean()), 5),
                          "max_abs_diff": int(d.max())})
        prev = img
        if i < n_pairs:
            advance()
    changed = len(set(hashes)) > 1
    return {"changed": bool(changed), "n_unique_hashes": len(set(hashes)), "hashes": hashes,
            "pairwise": diffs,
            "any_pixel_changed": any(d["frac_pixels_changed"] > 0 for d in diffs) if diffs else False,
            "mean_abs_diff_max": max((d["mean_abs_diff"] for d in diffs), default=None)}


def parse_grid(spec: str):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        h, w, c = (int(x) for x in part.split("x"))
        out.append((h, w, c))
    return out


# ---------------------------------------------------------------- 通道 1：gym-aloha

def probe_gym_aloha(args) -> dict:
    """gym-aloha 0.1.4：dm_control + MuJoCo。

    `tasks/sim.py:get_observation` **无条件渲染 3 个相机**（top/angle/front_close，各 480x640），
    而 `env.py:_format_raw_obs` 只保留 `top` ⇒ 每步付 3 份渲染成本只用 1 份。这条必须量出来。
    """
    import numpy as np
    import gymnasium as gym
    import gym_aloha  # noqa: F401  注册入口
    from gym_aloha.constants import DT, FPS, JOINTS, ACTIONS, ASSETS_DIR

    res: dict = {"channel": "gym_aloha",
                 "packages": pkg_versions(["gym-aloha", "gymnasium", "mujoco", "dm-control", "numpy"])}
    res["constants"] = {"DT": DT, "FPS": FPS, "control_hz": round(1.0 / DT, 3),
                        "n_joints": len(JOINTS), "n_actions": len(ACTIONS),
                        "joints": JOINTS, "actions": ACTIONS}
    res["mujoco_gl_env"] = os.environ.get("MUJOCO_GL")

    # --- 直接驱动 physics.render，才能自由改分辨率/相机数（env 的 obs 分辨率是写死的）
    # 注意：`Physics` 在 **dm_control.mujoco**，不是 mujoco 原生绑定（gym_aloha/env.py:113 就是这么用的）
    import mujoco
    from dm_control import mujoco as dm_mujoco
    xml = ASSETS_DIR / "bimanual_viperx_transfer_cube.xml"
    res["xml_path"] = str(xml)
    physics = dm_mujoco.Physics.from_xml_path(str(xml))
    cam_ids = [mujoco.mj_id2name(physics.model.ptr, mujoco.mjtObj.mjOBJ_CAMERA, i)
               for i in range(physics.model.ncam)]
    res["model_cameras"] = cam_ids
    res["actuators"] = _actuator_table(physics)
    res["joint_table"] = _joint_table(physics)
    res["timestep"] = physics.model.opt.timestep
    res["ctrl_range_note"] = ("action_space 是 Box(-1,1) 而 ctrl 实际范围见 actuators.ctrlrange "
                              "⇒ 两者若不一致，就是喂动作时必须先解决的口径问题（G2 ②③）")

    sample = {}
    for (h, w, nc) in parse_grid(args.grid):
        cams = [c for c in cam_ids if c][:nc] or [cam_ids[0]]
        key = f"{h}x{w}x{len(cams)}"
        rec = {}
        try:
            def once(cams=cams, h=h, w=w):
                return [physics.render(height=h, width=w, camera_id=c) for c in cams]

            img = once()[0]
            rec["ok"] = True
            rec["image"] = image_stats(img)
            rec.update(time_frames(once, args.frames))
            rec["cameras_used"] = cams
            # 推进用 physics.step()（自由落体 + 接触），保证画面必然变化
            # 推进一个**控制步**（DT/timestep = 10 个物理子步），只推 1 个 2ms 子步的话
            # 画面变化小到接近噪声，"能红"但读起来像假红。
            rec["liveness"] = liveness_check(
                lambda: once()[0],
                lambda: [physics.step() for _ in range(args.substeps)])
            if key not in sample:
                sample[key] = np.asarray(img)
        except Exception as exc:  # noqa: BLE001
            rec = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:400]}
        rec["load_before"] = load_snapshot()
        rec["rss_mb"] = rss_mb()
        res.setdefault("grid", {})[key] = rec
        print(f"  [gym_aloha {key}] ok={rec.get('ok')} fps={rec.get('steady_fps')} "
              f"first={rec.get('first_frame_s')}s load={rec['load_before']['loadavg_1m']}", flush=True)

    res["gl_libraries"] = gl_libraries_loaded()
    res["gl_renderer"] = gl_renderer_string()
    res["gpu"] = gpu_mem_mib()

    # --- 整局口径：env.reset()/step() 的真实成本（含物理 + 那 3 份写死的渲染）
    for obs_type in ("pixels", "pixels_agent_pos"):
        rec = {}
        try:
            env = gym.make("gym_aloha/AlohaTransferCube-v0", obs_type=obs_type)
            t = time.perf_counter()
            obs, info = env.reset(seed=0)
            t_reset = time.perf_counter() - t
            rec["ok"] = True
            rec["reset_s"] = round(t_reset, 3)
            rec["obs_schema"] = _obs_schema(obs)
            rec["info_keys"] = sorted(info.keys())
            rec["action_space"] = {"shape": list(env.action_space.shape),
                                   "dtype": str(env.action_space.dtype),
                                   "low": [float(x) for x in env.action_space.low[:4]],
                                   "high": [float(x) for x in env.action_space.high[:4]]}
            rec["max_episode_steps"] = env.spec.max_episode_steps if env.spec else None

            def step_once():
                env.step(env.action_space.sample())

            rec.update(time_frames(step_once, args.frames, warmup=2))
            rec["load_before"] = load_snapshot()
            rec["rss_mb"] = rss_mb()
            env.close()
        except Exception as exc:  # noqa: BLE001
            rec = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:500]}
        res.setdefault("env_loop", {})[obs_type] = rec
        print(f"  [gym_aloha env_loop {obs_type}] ok={rec.get('ok')} fps={rec.get('steady_fps')} "
              f"err={rec.get('error_type')}", flush=True)

    res["gl_libraries_after_env"] = gl_libraries_loaded()
    _save_samples(sample, "gym_aloha")
    return res


def _obs_schema(obs) -> dict:
    import numpy as np
    out = {}
    for k, v in obs.items():
        if isinstance(v, dict):
            out[k] = {kk: {"shape": list(np.asarray(vv).shape), "dtype": str(np.asarray(vv).dtype)}
                      for kk, vv in v.items()}
        else:
            a = np.asarray(v)
            out[k] = {"shape": list(a.shape), "dtype": str(a.dtype)}
    return out


def _save_samples(sample: dict, channel: str) -> None:
    """留几张真图当证据：判"出图了"不能只靠数字，得能被人眼看。"""
    if not sample:
        return
    try:
        import numpy as np
        d = OUT_DIR / "samples"
        d.mkdir(parents=True, exist_ok=True)
        for key, img in sample.items():
            a = np.asarray(img)
            if a.ndim == 3 and a.shape[2] in (3, 4):
                a = a[..., :3].astype("uint8")
            np.save(d / f"{channel}__{key}.npy", a)
        try:
            import imageio.v2 as imageio
            for key, img in sample.items():
                a = np.asarray(img)
                if a.ndim == 3 and a.shape[2] in (3, 4):
                    imageio.imwrite(d / f"{channel}__{key}.png", a[..., :3].astype("uint8"))
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] 存样本图失败：{type(exc).__name__} {exc}", flush=True)


# ---------------------------------------------------------------- 通道 2：robosuite

def probe_robosuite(args) -> dict:
    import numpy as np
    import robosuite
    from robosuite import make

    res: dict = {"channel": "robosuite",
                 "packages": pkg_versions(["robosuite", "mujoco", "numpy", "imageio"]),
                 "robosuite_version": robosuite.__version__,
                 "mujoco_gl_env": os.environ.get("MUJOCO_GL")}

    # 相机名必须是 Lift/Panda 场景里真有的（robosuite 报错会列出可用集）：
    #   ('frontview','birdview','agentview','sideview','robot0_robotview','robot0_eye_in_hand')
    # 用不存在的 "side" 会让 3 相机档整档 FAIL，把"渲染慢"误读成"渲染不了"。
    all_cams = ["agentview", "robot0_eye_in_hand", "frontview", "sideview"]
    for (h, w, nc) in parse_grid(args.grid):
        cams = all_cams[:nc]
        key = f"{h}x{w}x{nc}"
        rec = {"cameras": cams}
        env = None
        try:
            env = make("Lift", robots="Panda", has_renderer=False, has_offscreen_renderer=True,
                       use_camera_obs=True, camera_names=cams, camera_heights=h, camera_widths=w,
                       reward_shaping=False, control_freq=20, horizon=args.horizon)
            t = time.perf_counter()
            obs = env.reset()
            rec["ok"] = True
            rec["reset_s"] = round(time.perf_counter() - t, 3)
            rec["obs_schema"] = {k: {"shape": list(np.asarray(v).shape), "dtype": str(np.asarray(v).dtype)}
                                 for k, v in obs.items()}
            img_keys = [k for k in obs if k.startswith("image") or k.endswith("_image")]
            rec["image_obs_keys"] = img_keys
            sample = {}
            if img_keys:
                rec["image"] = image_stats(obs[img_keys[0]])
                sample[img_keys[0]] = np.asarray(obs[img_keys[0]])

            obs_holder = {"last": obs}

            def once():
                obs_holder["last"] = env.step(np.zeros(env.action_dim))[0]

            rec.update(time_frames(once, args.frames, warmup=2))
            rec["per_camera_render_note"] = ("robosuite 在一次 step 内渲染全部 camera_names "
                                             "⇒ fps 已含 %d 路成本" % nc)
            if img_keys:
                box = {"i": 0}

                def advance():
                    box["i"] += 1
                    a = np.zeros(env.action_dim)
                    a[0] = 1.0 if box["i"] % 2 else -1.0   # 来回推，保证可见位移
                    # **必须把新 obs 存回去**：capture 读的是 obs_holder["last"]，
                    # 不存回去就会每帧返回同一张旧图 ⇒ liveness 恒 changed=False（假红）。
                    # 本轮第一次跑就中过这个坑：robosuite 8/8 档全报 changed=False，
                    # 差点被读成"robosuite 不重画"，实际是探针自己没接住返回值。
                    obs_holder["last"] = env.step(a)[0]

                rec["liveness"] = liveness_check(lambda: np.asarray(obs_holder["last"][img_keys[0]]),
                                                 advance)
            rec["load_before"] = load_snapshot()
            rec["rss_mb"] = rss_mb()
            _save_samples({f"{key}__{k}": v for k, v in sample.items()}, "robosuite")
        except Exception as exc:  # noqa: BLE001
            rec = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:500], "cameras": cams}
        finally:
            if env is not None:
                try:
                    env.close()
                except Exception:
                    pass
        res.setdefault("grid", {})[key] = rec
        print(f"  [robosuite {key}] ok={rec.get('ok')} fps={rec.get('steady_fps')} "
              f"first={rec.get('first_frame_s')}s err={rec.get('error_type')}", flush=True)

    res["gl_libraries"] = gl_libraries_loaded()
    res["gl_renderer"] = gl_renderer_string()
    res["gpu"] = gpu_mem_mib()
    res["has_offscreen_renderer_probe"] = _robosuite_renderer_flag()
    return res


def _robosuite_renderer_flag() -> dict:
    """robosuite 自己怎么判"有没有离屏渲染器"——这条决定它会不会静默降级成 state-only。"""
    try:
        from robosuite import bind_to_mujoco  # noqa: F401
    except Exception:
        pass
    out = {}
    for mod, attr in (("robosuite.utils.binding_utils", "get_mujoco_version"),
                      ("robosuite", "renderer")):
        try:
            m = __import__(mod, fromlist=[attr])
            out[mod] = getattr(m, attr, "(absent)")
        except Exception as exc:  # noqa: BLE001
            out[mod] = f"(import fail {type(exc).__name__})"
    try:
        import mujoco
        out["mujoco.__version__"] = mujoco.__version__
        out["mujoco.has_renderer"] = bool(getattr(mujoco, "Renderer", None))
    except Exception as exc:  # noqa: BLE001
        out["mujoco_error"] = str(exc)
    out = {k: (str(v) if not isinstance(v, (str, int, float, bool)) else v) for k, v in out.items()}
    return out


# ---------------------------------------------------------------- 通道 3：ManiSkill3

def probe_maniskill(args) -> dict:
    import numpy as np
    import gymnasium as gym

    res: dict = {"channel": "maniskill",
                 "packages": pkg_versions(["mani_skill", "mani_skill3", "sapien", "gymnasium", "numpy", "torch"]),
                 "vk_icd_filenames": os.environ.get("VK_ICD_FILENAMES"),
                 "display": os.environ.get("DISPLAY")}

    try:
        import mani_skill.envs  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        res["import_error"] = f"{type(exc).__name__}: {exc}"

    for env_id in [e.strip() for e in args.envs.split(",") if e.strip()]:
        for render_mode in ("rgb_array",):
            for obs_mode in ("rgb", "rgb+segmentation"):
                key = f"{env_id}|{render_mode}|{obs_mode}"
                rec = {"env_id": env_id, "render_mode": render_mode, "obs_mode": obs_mode}
                env = None
                try:
                    t = time.perf_counter()
                    env = gym.make(env_id, render_mode=render_mode, obs_mode=obs_mode, num_envs=1)
                    rec["make_s"] = round(time.perf_counter() - t, 2)
                    obs, info = env.reset(seed=0)
                    rec["ok"] = True
                    rec["obs_schema"] = {k: {"shape": list(np.asarray(v).shape),
                                             "dtype": str(np.asarray(v).dtype)} for k, v in obs.items()}
                    imgk = [k for k in obs if "rgb" in k.lower()]
                    if imgk:
                        rec["image"] = image_stats(np.asarray(obs[imgk[0]]).squeeze(0))

                    def once():
                        env.step(env.action_space.sample())

                    rec.update(time_frames(once, max(8, args.frames // 4), warmup=2))
                    rec["load_before"] = load_snapshot()
                    rec["rss_mb"] = rss_mb()
                except Exception as exc:  # noqa: BLE001
                    rec = {**rec, "ok": False, "error_type": type(exc).__name__, "error": str(exc)[:600]}
                finally:
                    if env is not None:
                        try:
                            env.close()
                        except Exception:
                            pass
                res.setdefault("grid", {})[key] = rec
                print(f"  [maniskill {key}] ok={rec.get('ok')} fps={rec.get('steady_fps')} "
                      f"err={rec.get('error_type')}: {str(rec.get('error'))[:120]}", flush=True)

    res["gl_libraries"] = gl_libraries_loaded()
    res["gl_renderer"] = gl_renderer_string()
    res["gpu"] = gpu_mem_mib()
    return res


# ---------------------------------------------------------------- 主入口

CHANNELS = {"gym_aloha": probe_gym_aloha, "robosuite": probe_robosuite, "maniskill": probe_maniskill}


def main() -> None:
    global OUT_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True, choices=sorted(CHANNELS))
    ap.add_argument("--grid", default=DEFAULT_GRID, help="HxWxN相机，逗号分隔")
    ap.add_argument("--frames", type=int, default=60, help="稳态计时帧数")
    ap.add_argument("--substeps", type=int, default=10, help="gym-aloha 活性检查每次推进的物理子步数")
    ap.add_argument("--horizon", type=int, default=200, help="robosuite 用")
    ap.add_argument("--envs", default="PickCube-v1", help="maniskill 用")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    OUT_DIR = Path(args.out_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gl = os.environ.get("MUJOCO_GL") or os.environ.get("MUJOCO_RENDER_BACKEND") or "default"
    report: dict = {
        "probe": "a2_g05_vision_channels",
        "channel": args.channel,
        "args": vars(args),
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "mujoco_gl": gl,
        "load_before": load_snapshot(),
        "cpu_quota": cpu_quota(),
        "gpu_before": gpu_mem_mib(),
    }
    print(f"== G0.5 通道 {args.channel}  MUJOCO_GL={gl}  pid={os.getpid()} ==", flush=True)
    print(f"   loadavg={report['load_before']['loadavg_1m']} "
          f"nr_throttled={report['load_before']['cpu_stat'].get('nr_throttled')} "
          f"cpu_quota={report['cpu_quota'].get('cores')} 核", flush=True)

    t0 = time.perf_counter()
    try:
        report["result"] = CHANNELS[args.channel](args)
        report["probe_ok"] = True
    except Exception as exc:  # noqa: BLE001
        import traceback
        report["probe_ok"] = False
        report["fatal"] = {"error_type": type(exc).__name__, "error": str(exc)[:800],
                           "traceback": traceback.format_exc()[-3000:]}
        print(f"[FATAL] {type(exc).__name__}: {exc}", flush=True)
    report["probe_wall_s"] = round(time.perf_counter() - t0, 1)
    report["load_after"] = load_snapshot()
    report["gpu_after"] = gpu_mem_mib()
    report["rss_mb_peak"] = rss_mb()
    nb, na = report["load_before"]["cpu_stat"], report["load_after"]["cpu_stat"]
    report["nr_throttled_delta"] = (na.get("nr_throttled", 0) - nb.get("nr_throttled", 0))
    report["throttled_time_delta_ns"] = (na.get("throttled_time", na.get("throttled_usec", 0))
                                         - nb.get("throttled_time", nb.get("throttled_usec", 0)))

    out = OUT_DIR / f"channel_{args.channel}_{gl}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    print(f"[written] {out}", flush=True)
    print(f"[load] {report['load_before']['loadavg_1m']} -> {report['load_after']['loadavg_1m']}  "
          f"nr_throttled Δ={report['nr_throttled_delta']}  wall={report['probe_wall_s']}s", flush=True)


def _actuator_table(physics) -> list:
    """动作到底是"关节目标"还是"末端位姿"，看 actuator 类型就有答案（G2 问题②③④）。"""
    import mujoco
    out = []
    m = physics.model
    for i in range(m.nu):
        name = mujoco.mj_id2name(m.ptr, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
        tr = m.actuator_trntype[i]
        gt = m.actuator_gaintype[i]
        out.append({
            "name": name,
            "trntype": int(tr),
            "trntype_name": {0: "JOINT", 1: "SITE", 2: "SLIDECRANK", 3: "TENDON"}.get(int(tr), str(int(tr))),
            "gaintype": int(gt),
            "ctrlrange": [round(float(x), 5) for x in m.actuator_ctrlrange[i]],
            "ctrllimited": bool(m.actuator_ctrllimited[i]),
            "gear": [round(float(x), 4) for x in m.actuator_gear[i]],
            "trnid0": [round(float(x), 4) for x in m.actuator_trnid[i]],
        })
    return out


def _joint_table(physics) -> list:
    import mujoco
    out = []
    m = physics.model
    for i in range(m.njnt):
        name = mujoco.mj_id2name(m.ptr, mujoco.mjtObj.mjOBJ_JOINT, i)
        out.append({"name": name, "type": int(m.jnt_type[i]),
                    "range": [round(float(x), 5) for x in m.jnt_range[i]],
                    "qpos_adr": int(m.jnt_qposadr[i])})
    return out


if __name__ == "__main__":
    main()
