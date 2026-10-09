#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 · S1 · probe5：**egl_nvidia 下**关节模型的逐相机渲染成本 + GL 身份取证（采集排期用）。

为什么必须有这一探针（三条裁定压着）
------------------------------------
* **裁定 70**：渲染前缀目录名不许硬编码，一律走 `scripts/e_activate_gpu_render.sh --print`
  的解析结果；产物必须落 `activation_env` + `prefix_paths_verified` 三条布尔。
* **裁定 72-1 `renderer_identity_evidence_discipline`**：`MUJOCO_GL` 只表达意图，`GL_RENDERER`
  才表达事实 ⇒ 必须落 `GL_VENDOR`/`GL_RENDERER`/`GL_VERSION` 原文 + `renderer_class` + `identity_source`。
* **裁定 71**：E3-③ 落地前**不得声明任何单一"主线渲染口径"数值**；任何吞吐数字必须成对带
  `loadavg` 三点 + `nr_throttled` 增量，且必须标明它自己的协议维度。
  ⇒ 本探针的一切吞吐字段都带 `caliber_status="b2_planning_only_protocol_mismatched_not_mainline"`，
  **不许被任何文书当主线口径引用**。

它测什么
--------
在**关节模型**（`bimanual_viperx_transfer_cube.xml`，`AlohaTransferCube-v0` 用的那个，`nu=16`）里：
1. `mujoco.Renderer` 独立取 GL 身份（A2 的取法，`scripts/a2_egl_latency_remeasure.py`）；
2. 四个相机 × 两档分辨率的单帧渲染墙钟（`top`/`angle`/`left_wrist`/`right_wrist`；480×640 与 224²）；
3. 一次"物理步 + 6 渲染"的整步墙钟（= S1 采集的真实单步成本：团队三槽 480×640 + π₀.₅ 三键 224²）；
4. 由此外推 5 集 / 20 集 / 40 集的墙钟，与 GPU 10 min 申报门槛比对。

只读边界：不写 `datasets/`、不碰 `workplace/`、不改团队流水线、不改 site-packages。
写入面：只有 `--out`（默认 `runs/vla/b2_sim_demo_bidir_20260930/probe/probe5.json`）。

用法
----
    eval "$(bash scripts/e_activate_gpu_render.sh --print)"
    /root/venvs/pi05_sim/bin/python scripts/b2_s1_probe5_egl_render_cost.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CST = timezone(timedelta(hours=8))
SCRIPT = Path(__file__).resolve()
PREFIX_CANDIDATES = ("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01",)
CALIBER_STATUS = "b2_planning_only_protocol_mismatched_not_mainline"


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sha12(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def loadavg3() -> list:
    a = os.getloadavg()
    return [round(a[0], 2), round(a[1], 2), round(a[2], 2)]


def cpu_stat() -> dict:
    for cand in ("/sys/fs/cgroup/cpu.stat", "/sys/fs/cgroup/cpu/cpu.stat"):
        p = Path(cand)
        if p.exists():
            out = {"source": cand}
            for line in p.read_text().splitlines():
                k, _, v = line.partition(" ")
                try:
                    out[k] = int(v)
                except ValueError:
                    out[k] = v
            return out
    return {"source": None}


def nvidia_smi(query: str) -> dict:
    try:
        p = subprocess.run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=30)
        return {"ok": p.returncode == 0, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()[:300]}
    except Exception as e:                                   # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def nvidia_compute_apps() -> dict:
    try:
        p = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                            "--format=csv"], capture_output=True, text=True, timeout=30)
        return {"ok": p.returncode == 0, "verbatim": p.stdout.strip()}
    except Exception as e:                                   # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def foreign_processes() -> list:
    """裁定 73：臂内**非本线**进程清单（`b2_`/`e_`/`a2_`/`c2_` 前缀按线归类）。"""
    try:
        p = subprocess.run(["ps", "-eo", "pid,etimes,pcpu,args", "--no-headers"],
                           capture_output=True, text=True, timeout=30)
    except Exception as e:                                   # noqa: BLE001
        return [{"error": f"{type(e).__name__}: {e}"}]
    out = []
    for line in p.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, etimes, pcpu, args = parts
        if str(Path(sys.argv[0]).name) in args:
            continue
        tag = "b2" if "/b2_" in args or " b2_" in args else (
            "a2" if "/a2_" in args else ("c2" if "/c2_" in args else (
                "e" if "/e_" in args else "other")))
        if tag in ("a2", "c2", "e") or ("python" in args and "RL_Robot" in args):
            out.append({"pid": int(pid), "etimes_s": int(etimes), "pcpu": float(pcpu),
                        "line_tag": tag, "args": args[:220]})
    return out


def activation_env() -> dict:
    ld = os.environ.get("LD_LIBRARY_PATH") or ""
    vendor_json = os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES")
    prefix_active = any(c in ld for c in PREFIX_CANDIDATES)
    vj_in_prefix = bool(vendor_json) and any(vendor_json.startswith(c) for c in PREFIX_CANDIDATES)
    vj_exists = bool(vendor_json) and Path(vendor_json).exists()
    vj_points_into_prefix = False
    if vj_exists:
        try:
            txt = json.loads(Path(vendor_json).read_text())
            lib = txt["ICD"]["library_path"]
            vj_points_into_prefix = any(str(lib).startswith(c) for c in PREFIX_CANDIDATES) or \
                any(c in str(lib) for c in PREFIX_CANDIDATES)
        except Exception:                                    # noqa: BLE001
            vj_points_into_prefix = False
    return {
        "MUJOCO_GL": os.environ.get("MUJOCO_GL"),
        "PYOPENGL_PLATFORM": os.environ.get("PYOPENGL_PLATFORM"),
        "LD_LIBRARY_PATH": ld or None,
        "__EGL_VENDOR_LIBRARY_FILENAMES": vendor_json,
        "__EGL_VENDOR_LIBRARY_DIRS": os.environ.get("__EGL_VENDOR_LIBRARY_DIRS"),
        "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "nvidia_prefix_active": prefix_active,
        "prefix_paths_verified": {
            "prefix_in_ld_library_path": prefix_active,
            "vendor_json_points_into_prefix": vj_points_into_prefix,
            "vendor_json_exists": vj_exists,
        },
        "activation_authority": "eval \"$(bash scripts/e_activate_gpu_render.sh --print)\"（裁定 70：不硬编码目录名）",
    }


def gl_identity() -> dict:
    """裁定 72-1：用 `mujoco.Renderer` 存活期内的 `glGetString` 取**事实**（A2 的取法）。"""
    import mujoco
    out = {"method": "mujoco.Renderer + OpenGL.GL.glGetString（renderer 存活期内）",
           "mujoco_version": mujoco.__version__, "identity_source": "mujoco.Renderer(独立探针)"}
    try:
        m = mujoco.MjModel.from_xml_string(
            "<mujoco><worldbody><geom type='box' size='.1 .1 .1'/></worldbody></mujoco>")
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        r = mujoco.Renderer(m, 64, 64)
        r.update_scene(d)
        px = r.render()
        from OpenGL import GL
        strs = {k: GL.glGetString(getattr(GL, k)) for k in ("GL_VENDOR", "GL_RENDERER", "GL_VERSION")}
        out["render_ok"] = True
        out["render_shape"] = list(px.shape)
        out["render_byte_mean"] = round(float(px.mean()), 4)
        out["gl_strings"] = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in strs.items()}
        rend = (out["gl_strings"].get("GL_RENDERER") or "")
        out["renderer_class"] = ("nvidia_gpu" if "NVIDIA" in rend.upper() else
                                 ("mesa_cpu_software" if "llvmpipe" in rend or "softpipe" in rend
                                  else "unknown"))
        r.close()
    except Exception as e:                                   # noqa: BLE001
        import traceback
        out.update({"render_ok": False, "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc()[-1500:], "renderer_class": "unknown_error"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/vla/b2_sim_demo_bidir_20260930/probe/probe5.json")
    ap.add_argument("--n-steps", type=int, default=40)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--dt", type=float, default=0.034)
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    import b2_s1_scripted_expert as exp                     # noqa: E402

    out = {
        "probe": "b2_s1_probe5_egl_render_cost",
        "generated_at": now_iso(),
        "generator": "scripts/b2_s1_probe5_egl_render_cost.py",
        "generator_sha256_12": sha12(SCRIPT),
        "expert_module": "scripts/b2_s1_scripted_expert.py",
        "expert_module_sha256_12": sha12(ROOT / "scripts" / "b2_s1_scripted_expert.py"),
        "args": vars(args),
        "purpose": "S1 采集排期与 GPU 申报依据（egl_nvidia 下逐相机渲染成本 + GL 身份取证）",
        "caliber_status": CALIBER_STATUS,
        "caliber_status_why": ("裁定 71：E3-③ 落地前不得声明任何单一『主线渲染口径』数值；"
                              "本探针的协议维度（关节模型/6 渲染/含物理步/n_steps=%d/reps=%d）"
                              "与 E 的 render-only 档、A2 的 3cam224² 档**都不同** ⇒ 不得互搬"
                              % (args.n_steps, args.reps)),
        "morphology": "aloha_bimanual_14d",
        "env_id": "gym_aloha/AlohaTransferCube-v0（旁路 AlohaEnv，直接 control.Environment）",
        "model_xml": "gym_aloha/assets/bimanual_viperx_transfer_cube.xml（关节版，nu=16，裁定 66）",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "venv": sys.executable,
        "activation_env": activation_env(),
        "gl_identity": gl_identity(),
        "no_multiprocess_rendering": True,
        "policy_executed": False,
        "capability_claim": False,
        "success_metrics_collected": False,
    }
    import importlib.metadata as md
    out["versions"] = {m: (md.version(m) if _has(m) else None)
                       for m in ("mujoco", "dm_control", "gym-aloha", "lerobot", "numpy", "torch")}
    try:
        from envs import gym_aloha_shim as shim
        out["shim"] = {"path": "envs/gym_aloha_shim.py", "sha256_12": sha12(ROOT / "envs" / "gym_aloha_shim.py"),
                       "representation_version": shim.REPRESENTATION_VERSION,
                       "MAINLINE_DT": shim.MAINLINE_DT, "MAINLINE_SUBSTEPS": shim.MAINLINE_SUBSTEPS,
                       "MAINLINE_HZ": shim.MAINLINE_HZ}
    except Exception as e:                                   # noqa: BLE001
        out["shim"] = {"error": f"{type(e).__name__}: {e}"}

    out["load_before"] = {"loadavg": loadavg3(), "cpu_stat": cpu_stat(), "ts": now_iso()}
    out["nvidia_smi_before"] = {"gpu": nvidia_smi("memory.used,utilization.gpu,temperature.gpu"),
                                "compute_apps": nvidia_compute_apps()}
    out["cotenant_before"] = foreign_processes()

    # **6 个渲染槽**（S1 采集的真实每步渲染面）：团队三槽 480×640 + π₀.₅ 三键 224²。
    # 两个腕相机**各出两档**，且两档不是缩放关系（MuJoCo `fovy` 固定、`fx=fy` ⇒ 4:3 与 1:1 视锥不同）。
    spec = (("team_top", "top", 480, 640),
            ("team_left_wrist", "left_wrist", 480, 640),
            ("team_right_wrist", "right_wrist", 480, 640),
            ("pi05_base_0_rgb", "angle", 224, 224),
            ("pi05_left_wrist_0_rgb", "left_wrist", 224, 224),
            ("pi05_right_wrist_0_rgb", "right_wrist", 224, 224))
    # 单相机单档成本（重复 reps 次取中位数）
    per_cam = {}
    box = exp.sample_box_pose_seeded(1000, "forward")
    env0 = exp.JointEnv(args.dt, box, render_spec=spec)
    env0.reset()
    for _ in range(12):
        env0.step(env0.make_action({}, {"left": 1.0, "right": 1.0}))
    for cam in ("top", "angle", "left_wrist", "right_wrist"):
        for tag, (h, w) in (("480x640", (480, 640)), ("224x224", (224, 224))):
            ts = []
            for _ in range(args.reps):
                t0 = time.perf_counter()
                for _ in range(5):
                    env0.physics.render(height=h, width=w, camera_id=cam)
                ts.append((time.perf_counter() - t0) / 5.0)
            ts.sort()
            per_cam[f"{cam}@{tag}"] = {"median_s": round(ts[len(ts) // 2], 6),
                                       "min_s": round(ts[0], 6), "max_s": round(ts[-1], 6),
                                       "h": h, "w": w}
    env0.close()

    # 整步成本：物理步（17 子步）+ 6 渲染（3×480×640 + 3×224²）
    env = exp.JointEnv(args.dt, box, render_spec=spec)
    env.reset()
    steps_phys, steps_all = [], []
    for i in range(args.n_steps):
        a = env.make_action({}, {"left": 1.0, "right": 1.0})
        t0 = time.perf_counter()
        env.step(a)
        t1 = time.perf_counter()
        env.render()
        t2 = time.perf_counter()
        steps_phys.append(t1 - t0)
        steps_all.append(t2 - t0)
    live = {"control_timestep_s": None, "n_sub_steps": None, "measured_hz": None}
    ct = env.env.control_timestep
    live["control_timestep_s"] = float(ct() if callable(ct) else ct)
    live["n_sub_steps"] = int(getattr(env.env, "_n_sub_steps", -1))
    live["measured_hz"] = round(1.0 / live["control_timestep_s"], 6)
    live["model_timestep_s"] = float(env.physics.timestep())
    env.close()

    def stat(v):
        s = sorted(v)
        return {"median_s": round(s[len(s) // 2], 6), "mean_s": round(sum(s) / len(s), 6),
                "min_s": round(s[0], 6), "max_s": round(s[-1], 6),
                "p90_s": round(s[int(0.9 * (len(s) - 1))], 6)}

    out["per_camera_render_cost"] = per_cam
    out["step_cost"] = {"physics_only": stat(steps_phys), "physics_plus_6_renders": stat(steps_all),
                        "n_steps": args.n_steps, "renders_per_step": len(spec),
                        "renders_per_step_detail": [{"slot": s, "camera": c, "h": h, "w": w}
                                                    for s, c, h, w in spec]}
    out["live_timing"] = live
    med = out["step_cost"]["physics_plus_6_renders"]["median_s"]
    hz = live["measured_hz"] or 29.411765
    out["extrapolation"] = {
        "per_episode_300_steps_s": round(med * 300, 2),
        "pilot_5_plus_5_s": round(med * 300 * 10, 1),
        "formal_20_plus_20_s": round(med * 300 * 40, 1),
        "formal_20_plus_20_min": round(med * 300 * 40 / 60.0, 2),
        "gpu_10min_declaration_threshold_crossed_at_40ep": bool(med * 300 * 40 > 600),
        "effective_steps_per_s": round(1.0 / med, 3) if med else None,
        "vs_control_hz_ratio": round((1.0 / med) / hz, 3) if med else None,
        "note": "外推基于**本探针协议**（含 6 渲染 + 物理步，n_steps=%d），不是主线渲染口径（裁定 71）" % args.n_steps,
    }
    out["load_after"] = {"loadavg": loadavg3(), "cpu_stat": cpu_stat(), "ts": now_iso()}
    out["nvidia_smi_after"] = {"gpu": nvidia_smi("memory.used,utilization.gpu,temperature.gpu"),
                               "compute_apps": nvidia_compute_apps()}
    out["cotenant_after"] = foreign_processes()
    b, a = out["load_before"]["cpu_stat"], out["load_after"]["cpu_stat"]
    out["nr_throttled_delta"] = (a.get("nr_throttled", 0) - b.get("nr_throttled", 0)
                                 if isinstance(a.get("nr_throttled"), int)
                                 and isinstance(b.get("nr_throttled"), int) else None)
    out["contaminated_by_cotenant"] = bool(out["cotenant_before"] or out["cotenant_after"])
    out["gpu_deregister_note"] = "跑完 GPU 读数见 nvidia_smi_after；B2 无长驻进程（单进程串行渲染）"

    p = ROOT / args.out
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"out": str(p), "gl": out["gl_identity"].get("gl_strings"),
                      "renderer_class": out["gl_identity"].get("renderer_class"),
                      "activation": out["activation_env"]["prefix_paths_verified"],
                      "step_cost": out["step_cost"], "live_timing": live,
                      "extrapolation": out["extrapolation"],
                      "load_before": out["load_before"]["loadavg"],
                      "load_after": out["load_after"]["loadavg"],
                      "nr_throttled_delta": out["nr_throttled_delta"],
                      "contaminated_by_cotenant": out["contaminated_by_cotenant"],
                      "cotenant_before": out["cotenant_before"],
                      "cotenant_after": out["cotenant_after"]},
                     ensure_ascii=False, indent=1))
    return 0


def _has(mod: str) -> bool:
    import importlib.metadata as md
    try:
        md.version(mod)
        return True
    except Exception:                                        # noqa: BLE001
        return False


if __name__ == "__main__":
    raise SystemExit(main())
