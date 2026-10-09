#!/usr/bin/env python
"""E 线：GPU 渲染修好之后，**下游真实消费者**到底解锁了没有。

`e_gpu_egl_verify.py` 证明的是"渲染栈本身通了"（裸 mujoco XML）。但项目要的不是裸 mujoco，
是 robosuite / gym-aloha / ManiSkill 这三个真实入口。它们各自还有自己的坑：
  - robosuite：`has_offscreen_renderer=True` 走 mujoco GLContext，`MUJOCO_GL` 必须在 import 前设；
  - gym-aloha：A2 的 P0/P1 **形态代理**环境（`d_handoff_to_a2` Q2 甲案），像素档能不能出图直接决定
    π₀.₅ 的视觉输入是否可得；
  - ManiSkill/SAPIEN：历史上 `render_backend="gpu"` 直接
    `vk::createInstanceUnique: ErrorIncompatibleDriver`（`docs/infra-gpu-render.md` §6.1），
    因为 SAPIEN 的 `_vulkan_tricks.py` 会自动写一个指向 `libGLX_nvidia.so.0` 的 nvidia_icd.json，
    而那个库当时不存在。**这次装了 libGLX_nvidia.so.0，这条历史阻塞是否解除，必须实测。**

每个 case 在**各自 venv 的解释器**里跑子进程，父进程只做归因采样：
  - 子进程 `/proc/self/maps` 里加载了哪些 NVIDIA 库
  - 子进程是否自己持有 `/dev/nvidia*` fd（进程级归因，排除并发进程污染）
  - GL_RENDERER（mujoco 系）/ Vulkan 设备名（SAPIEN 系）
  - 出图是否非黑 + 吞吐（带 loadavg 与 nr_throttled 口径）

用法：
  python scripts/e_render_downstream_smoke.py                 # 跑全部三个 case
  python scripts/e_render_downstream_smoke.py --cases robosuite_lift,gym_aloha
  python scripts/e_render_downstream_smoke.py --expect cpu    # 负对照：强制 mesa ICD，必须全不是 NVIDIA
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import e_gpu_egl_verify as ev  # noqa: E402  复用归因/采样函数，不重复实现

PERSIST_ENVS = "/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/envs"

CASES = {
    "robosuite_lift": {
        "python": "/root/venvs/rlrobot/bin/python",
        "mujoco_gl": "egl",
        "timeout": 900,
    },
    "gym_aloha": {
        "python": "/root/venvs/pi05_sim/bin/python",
        "mujoco_gl": "egl",
        "timeout": 900,
    },
    "maniskill_pixel": {
        "python": f"{PERSIST_ENVS}/maniskill_probe/bin/python",
        "mujoco_gl": None,          # SAPIEN 走 Vulkan，不看 MUJOCO_GL
        "timeout": 1200,
    },
}

_CHILD_HEADER = r'''
import json, os, re, sys, time

def gl_strings():
    try:
        from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString
        vals = [glGetString(x) for x in (GL_VENDOR, GL_RENDERER, GL_VERSION)]
        return [v.decode() if isinstance(v, bytes) else str(v) for v in vals if v]
    except Exception as exc:
        return [f"(unavailable: {type(exc).__name__}: {str(exc)[:120]})"]

def loaded_gl_libs():
    hits = {}
    try:
        text = open("/proc/self/maps", "r", errors="ignore").read()
    except Exception as exc:
        return {"error": str(exc)}
    for m in re.finditer(r"/\S*/(lib[A-Za-z0-9_.+-]*\.so[0-9.]*)", text):
        n = m.group(1)
        if any(k in n for k in ("nvidia", "EGL", "GLX", "GLdispatch", "glapi", "OSMesa",
                                "swrast", "gallium", "vulkan", "sapien")):
            hits[n] = hits.get(n, 0) + 1
    return hits

def img_stats(a):
    import numpy as np
    dev = None
    if hasattr(a, "detach"):        # ManiSkill 的 render() 返回 torch tensor，而且在 cuda 上；
        dev = str(getattr(a, "device", "?"))   # 直接 np.asarray 会 TypeError（本脚本第一版踩了）
        a = a.detach().cpu().numpy()
    a = np.asarray(a)
    if a.ndim == 4:
        a = a[0]
    return {"shape": list(a.shape), "dtype": str(a.dtype),
            "mean": round(float(a.mean()), 3), "min": float(a.min()), "max": float(a.max()),
            "source_device": dev}

out = {"case": sys.argv[1]}
'''

_CHILD_BODY = {
    "robosuite_lift": r'''
try:
    import numpy as np
    import robosuite as suite
    out["robosuite"] = suite.__version__
    env = suite.make(
        "Lift", robots="Panda", has_offscreen_renderer=True, use_camera_obs=True,
        camera_names=["agentview", "robot0_eye_in_hand"],
        camera_heights=256, camera_widths=256, reward_shaping=False)
    obs = env.reset()
    img = obs["agentview_image"]
    out["gl_strings"] = gl_strings()
    out["image"] = img_stats(img)
    n = 60
    t0 = time.perf_counter()
    for _ in range(n):
        obs, _, _, _ = env.step(np.zeros(env.action_dim))
    dt = time.perf_counter() - t0
    out["steps"] = n
    out["seconds"] = round(dt, 3)
    out["steps_per_s"] = round(n / dt, 2) if dt > 0 else None
    out["camera_obs_keys"] = sorted(k for k in obs if k.endswith("_image"))
    out["ok"] = True
except Exception as exc:
    import traceback
    out["ok"] = False
    out["error"] = f"{type(exc).__name__}: {exc}"
    out["traceback_tail"] = traceback.format_exc().strip().splitlines()[-6:]
out["loaded_gl_libs"] = loaded_gl_libs()
print("RESULT_JSON" + json.dumps(out))
''',
    "gym_aloha": r'''
try:
    import numpy as np
    import gymnasium as gym
    import gym_aloha  # noqa: F401
    env = gym.make("gym_aloha/AlohaTransferCube-v0", render_mode="rgb_array")
    obs, info = env.reset(seed=0)
    frame = env.render()
    out["gl_strings"] = gl_strings()
    out["image"] = img_stats(frame)
    out["action_space"] = repr(env.action_space)
    n = 60
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    t0 = time.perf_counter()
    for _ in range(n):
        env.step(a)
        env.render()
    dt = time.perf_counter() - t0
    out["steps"] = n
    out["seconds"] = round(dt, 3)
    out["steps_per_s_with_render"] = round(n / dt, 2) if dt > 0 else None
    out["ok"] = True
except Exception as exc:
    import traceback
    out["ok"] = False
    out["error"] = f"{type(exc).__name__}: {exc}"
    out["traceback_tail"] = traceback.format_exc().strip().splitlines()[-6:]
out["loaded_gl_libs"] = loaded_gl_libs()
print("RESULT_JSON" + json.dumps(out))
''',
    "maniskill_pixel": r'''
try:
    import numpy as np
    import sapien, mani_skill, mani_skill.envs  # noqa: F401
    out["sapien"] = sapien.__version__
    out["mani_skill"] = mani_skill.__version__
    out["VK_ICD_FILENAMES"] = os.environ.get("VK_ICD_FILENAMES")
    import gymnasium as gym
    num_envs = int(os.environ.get("E_MS_NUM_ENVS", "4"))
    out["num_envs"] = num_envs
    env = gym.make("PickCube-v1", num_envs=num_envs,
                   render_mode="rgb_array", render_backend="gpu")
    obs, info = env.reset(seed=0)
    frame = env.render()
    out["image"] = img_stats(frame)
    n = 30
    a = np.zeros(env.action_space.shape, dtype=np.float32)
    t0 = time.perf_counter()
    for _ in range(n):
        env.step(a)
        env.render()
    dt = time.perf_counter() - t0
    out["steps"] = n
    out["seconds"] = round(dt, 3)
    out["steps_per_s_with_render"] = round(n / dt, 2) if dt > 0 else None
    out["ok"] = True
except Exception as exc:
    import traceback
    out["ok"] = False
    out["error"] = f"{type(exc).__name__}: {exc}"
    out["traceback_tail"] = traceback.format_exc().strip().splitlines()[-8:]
out["loaded_gl_libs"] = loaded_gl_libs()
print("RESULT_JSON" + json.dumps(out))
''',
}


def run_case(name: str, expect: str, vendor_icd: str | None) -> dict:
    spec = CASES[name]
    env = dict(os.environ)
    if spec["mujoco_gl"]:
        env["MUJOCO_GL"] = spec["mujoco_gl"]
        env["PYOPENGL_PLATFORM"] = "egl"
    if vendor_icd:
        env["__EGL_VENDOR_LIBRARY_FILENAMES"] = vendor_icd
    child_src = _CHILD_HEADER + _CHILD_BODY[name]
    proc = subprocess.Popen([spec["python"], "-c", child_src, name],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    fd_union: set[str] = set()
    samples = []
    t_start = time.time()
    while proc.poll() is None:
        fd_union.update(ev.child_nvidia_fds(proc.pid))
        samples.append(ev.nvidia_smi_sample())
        if time.time() - t_start > spec["timeout"]:
            proc.kill()
            break
        time.sleep(0.4)
    stdout, stderr = proc.communicate(timeout=120)
    payload = None
    for line in stdout.splitlines():
        if line.startswith("RESULT_JSON"):
            payload = json.loads(line[len("RESULT_JSON"):])
    res = payload or {"ok": False, "error": "no result",
                      "stderr_tail": (stderr or stdout).strip().splitlines()[-10:]}
    res["case"] = name
    res["python"] = spec["python"]
    res["returncode"] = proc.returncode
    res["child_nvidia_fds"] = sorted(fd_union)
    ok_s = [s for s in samples if "utilization_gpu" in s]
    res["gpu_util_max"] = max((s["utilization_gpu"] for s in ok_s), default=None)
    res["gpu_mem_used_max_mib"] = max((s["memory_used_mib"] for s in ok_s), default=None)
    res["concurrent_compute_procs"] = sorted({p for s in samples for p in (s.get("compute_procs") or [])})
    if stderr.strip():
        res["stderr_tail"] = stderr.strip().splitlines()[-10:]
    gls = " | ".join(res.get("gl_strings") or [])
    nvidia_libs = sorted(k for k in (res.get("loaded_gl_libs") or {}) if "nvidia" in k.lower())
    is_nvidia = ("NVIDIA" in gls) or bool(nvidia_libs) or bool(fd_union)
    if expect == "gpu":
        res["verdict"] = {
            "ok": bool(res.get("ok")) and is_nvidia and bool(fd_union),
            "checks": {
                "case_ran_ok": bool(res.get("ok")),
                "renderer_is_nvidia": is_nvidia,
                "child_holds_nvidia_fd": bool(fd_union),
                "image_nonblack": bool(res.get("image")) and res["image"].get("mean", 0) > 1.0,
            },
        }
    else:
        res["verdict"] = {
            "ok": bool(res.get("ok")) and not is_nvidia,
            "checks": {"case_ran_ok": bool(res.get("ok")),
                       "renderer_not_nvidia": not is_nvidia},
        }
    res["nvidia_libs_loaded"] = nvidia_libs
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--label", default=None)
    ap.add_argument("--expect", choices=("gpu", "cpu"), default="gpu")
    ap.add_argument("--vendor-icd", default=None,
                    help="负对照用：只暴露这个 EGL vendor ICD（例如 50_mesa.json）")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cases = [c.strip() for c in args.cases.split(",") if c.strip()]
    label = args.label or f"downstream_{args.expect}"
    report = {
        "label": label, "expect": args.expect, "cases": cases,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "vendor_icd_override": args.vendor_icd,
        "cpu_stat_before": ev.cpu_stat(),
        "results": {},
    }
    for name in cases:
        if name not in CASES:
            print(f"unknown case: {name}", file=sys.stderr)
            return 64
        print(f"---- case {name} ({CASES[name]['python']}) ----", flush=True)
        report["results"][name] = run_case(name, args.expect, args.vendor_icd)
    report["cpu_stat_after"] = ev.cpu_stat()
    report["all_ok"] = all(r["verdict"]["ok"] for r in report["results"].values())

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "runs" / "infra" / f"e_gpu_egl_verify_{time.strftime('%Y%m%d')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{label}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print(f"E 线 下游渲染冒烟 · label={label} · expect={args.expect}")
    print("=" * 78)
    for name, r in report["results"].items():
        print(f"  [{name}] ok={r.get('ok')} verdict={r['verdict']['ok']}")
        if r.get("error"):
            print(f"      error: {str(r['error'])[:220]}")
            for line in r.get("traceback_tail", []) or []:
                print(f"      | {line}")
        if r.get("gl_strings"):
            print(f"      GL: {' | '.join(r['gl_strings'])}")
        if r.get("image"):
            im = r["image"]
            print(f"      image: shape={im['shape']} mean={im['mean']} "
                  f"min={im['min']} max={im['max']}")
        for k in ("steps_per_s", "steps_per_s_with_render"):
            if r.get(k) is not None:
                print(f"      {k} = {r[k]}  ({r.get('steps')} 步 / {r.get('seconds')}s)")
        print(f"      child_nvidia_fds={r['child_nvidia_fds']} "
              f"gpu_util_max={r.get('gpu_util_max')}% mem_max={r.get('gpu_mem_used_max_mib')}MiB")
        print(f"      nvidia_libs={r['nvidia_libs_loaded'][:6]}")
        bad = [k for k, v in r["verdict"]["checks"].items() if not v]
        if bad:
            print(f"      ✗ 未满足: {bad}")
    print("-" * 78)
    print(f"  loadavg before={report['cpu_stat_before'].get('loadavg')} "
          f"after={report['cpu_stat_after'].get('loadavg')}")
    print(f"  nr_throttled before={report['cpu_stat_before'].get('nr_throttled')} "
          f"after={report['cpu_stat_after'].get('nr_throttled')}")
    print(f"  结论: {'全部通过' if report['all_ok'] else '有不通过'}   产物: {out_path}")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
