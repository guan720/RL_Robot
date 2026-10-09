#!/usr/bin/env python
"""E 线：NVIDIA GPU 渲染（EGL/GL）可用性验证器 —— 带负对照，判据有牙。

为什么不用 `scripts/check_gpu_render.py`？两个原因：
  1. 那个脚本的 `gpu_render_possible` 是**静态启发式**：它要求 `/dev/dri` 存在
     且 `NVIDIA_DRIVER_CAPABILITIES` 含 graphics（`scripts/check_gpu_render.py:106`）。
     这两条在容器里**都不是 GPU 渲染的必要条件**——NVIDIA 的 EGL device platform
     走 `/dev/nvidiactl` + `/dev/nvidiaN`，不经过 DRM 节点。用它会得到"装了库仍判 False"的假红。
     该脚本属环境调研线冻结面（裁定 38.7），**本脚本不改它**，只并行存在并在报告里注明分歧。
  2. 它不测"到底是谁在渲染"。本脚本的判据全部是**实测身份**：
     EGL 设备枚举 + `eglQueryString(EGL_VENDOR)` + `glGetString(GL_RENDERER)`
     + 进程 `/proc/self/maps` 里真正加载了哪些 NVIDIA 库 + 渲染期间 `nvidia-smi` 的
     utilization/memory 采样。

判据（`--expect gpu` 时全部满足才 exit 0）：
  L1 七个库齐全，且**文件名版本 == /proc/driver/nvidia/version 的驱动版本**（版本漂移即判红）
  L2 `eglQueryDevicesEXT` 至少枚举到 1 个设备，其 display 的 EGL_VENDOR 含 "NVIDIA"
  L3 mujoco EGL 后端 `glGetString(GL_RENDERER)` 含 "NVIDIA" 且不含 "llvmpipe"
  L4 渲染结果非黑（image_mean > 1.0）
  L5 渲染期间 `nvidia-smi` 的 utilization.gpu 或 memory.used 峰值 > 0
  L6 子进程 maps 里出现 libEGL_nvidia / libnvidia-glcore（证明不是"装了但没用上"）

负对照（`--expect cpu`）：同一套探测，但**期望结论相反**——必须是 Mesa/llvmpipe 且
没有 NVIDIA 渲染库被加载。它的作用是证明 L2/L3/L5 不是恒真：如果负对照也判"gpu 通过"，
说明判据没牙，脚本会以 exit 2 报"判据失效"。

用法：
    python scripts/e_gpu_egl_verify.py --label post_install --expect gpu
    python scripts/e_gpu_egl_verify.py --label neg_mesa_only --expect cpu \
        --vendor-icd /usr/share/glvnd/egl_vendor.d/50_mesa.json
    python scripts/e_gpu_egl_verify.py --label staged --expect gpu --lib-dir <staging>/usr/lib/x86_64-linux-gnu \
        --vendor-icd <staging>/usr/share/glvnd/egl_vendor.d/10_nvidia.json
"""

from __future__ import annotations

import argparse
import ctypes
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_LIBS = (
    "libEGL_nvidia.so.0",
    "libGLX_nvidia.so.0",
    "libnvidia-glcore.so",
    "libnvidia-eglcore.so",
    "libnvidia-glsi.so",
    "libnvidia-gpucomp.so",
    "libnvidia-tls.so",
)
SEARCH_DIRS = (
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib64",
    "/usr/local/nvidia/lib64",
    "/usr/local/nvidia/lib",
)

_XML = (
    "<mujoco>"
    "<visual><global offwidth='1024' offheight='1024'/></visual>"
    "<worldbody>"
    "<light pos='0 0 3' dir='0 0 -1'/>"
    "<camera name='c' pos='1.6 0 1.0' xyaxes='0 1 0 -0.6 0 1'/>"
    "<body pos='0 0 0.4'><joint type='free'/><geom type='sphere' size='0.12' rgba='0.2 0.6 0.9 1'/></body>"
    "<geom type='box' size='0.2 0.2 0.2' pos='0.35 0 0.2' rgba='0.9 0.4 0.2 1'/>"
    "<geom type='plane' size='2 2 0.1'/>"
    "</worldbody></mujoco>"
)

# 子进程探测体：MUJOCO_GL 在 import/建上下文时生效，必须与父进程隔离。
_CHILD = r'''
import ctypes, json, os, re, sys, time

def gl_strings():
    try:
        from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString
        vals = [glGetString(x) for x in (GL_VENDOR, GL_RENDERER, GL_VERSION)]
        return [v.decode() if isinstance(v, bytes) else str(v) for v in vals if v]
    except Exception as exc:
        return [f"(unavailable: {type(exc).__name__}: {str(exc)[:120]})"]

def loaded_nvidia_libs():
    hits = {}
    try:
        text = open("/proc/self/maps", "r", errors="ignore").read()
    except Exception as exc:
        return {"error": str(exc)}
    for m in re.finditer(r"/\S*/(lib[A-Za-z0-9_.+-]*\.so[0-9.]*)", text):
        name = m.group(1)
        if any(k in name for k in ("nvidia", "EGL", "GLX", "GLdispatch", "glapi", "OSMesa", "swrast", "gallium")):
            hits[name] = hits.get(name, 0) + 1
    return hits

out = {"cwd": os.getcwd(), "mujoco_gl": os.environ.get("MUJOCO_GL")}
try:
    import mujoco
    out["mujoco"] = mujoco.__version__
    sizes = [int(s) for s in sys.argv[1].split(",") if s.strip()]
    duration = float(sys.argv[2])
    cap = int(sys.argv[3])
    model = mujoco.MjModel.from_xml_string(''' + repr(_XML) + r''')
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    renders = {}
    for size in sizes:
        renderer = mujoco.Renderer(model, height=size, width=size)
        renderer.update_scene(data, camera="c")
        image = renderer.render()
        if "gl_strings" not in out:
            # 必须在 renderer 还活着、GL 上下文还 current 时取：close() 之后 glGetString
            # 返回 NULL（本机实测三个字符串全空 ⇒ L3 会假红）。这个坑记进报告。
            out["gl_strings"] = gl_strings()
        # 先测 RGB 再开深度：enable_depth_rendering() 之后 render() 返回深度图，
        # 两者差一个数量级，顺序反了会得到假数字（docs/infra-gpu-render.md §5-2 的坑）。
        t0 = time.perf_counter(); frames = 0
        while True:
            renderer.update_scene(data, camera="c")
            renderer.render()
            frames += 1
            elapsed = time.perf_counter() - t0
            if elapsed >= duration or frames >= cap:
                break
        rgb = {"frames": frames, "seconds": round(elapsed, 3),
               "fps": round(frames / elapsed, 2) if elapsed > 0 else None,
               "image_mean": round(float(image.mean()), 3)}
        renderer.enable_depth_rendering()
        renderer.update_scene(data, camera="c")
        depth = renderer.render()
        t0 = time.perf_counter(); dframes = 0
        while True:
            renderer.update_scene(data, camera="c")
            renderer.render()
            dframes += 1
            delapsed = time.perf_counter() - t0
            if delapsed >= duration or dframes >= cap:
                break
        rgb["depth_frames"] = dframes
        rgb["depth_seconds"] = round(delapsed, 3)
        rgb["depth_fps"] = round(dframes / delapsed, 2) if delapsed > 0 else None
        rgb["depth_ok"] = bool(depth is not None)
        renders[size] = rgb
        renderer.close()
    out["ok"] = True
    out["renders"] = renders
    out["gl_strings_after_close"] = gl_strings()
    out["loaded_gl_libs"] = loaded_nvidia_libs()
except Exception as exc:
    out["ok"] = False
    out["error"] = f"{type(exc).__name__}: {exc}"
    out.setdefault("gl_strings", gl_strings())
    out["loaded_gl_libs"] = loaded_nvidia_libs()
print("RESULT_JSON" + json.dumps(out))
'''


def sha256_of(path: str | None) -> str | None:
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def driver_version() -> str | None:
    """/proc 的 NVRM 行里 "Open Kernel Module" 之类描述词数目不定，不能按词数定位版本号。"""
    ver = None
    try:
        for line in Path("/proc/driver/nvidia/version").read_text().splitlines():
            if line.startswith("NVRM version:"):
                m = re.search(r"\b(\d+\.\d+\.\d+)\b", line)
                if m:
                    ver = m.group(1)
                break
    except OSError:
        pass
    if ver:
        return ver
    try:  # 交叉核对：nvidia-smi 的口径
        p = subprocess.run(["nvidia-smi", "--query-gpu=driver_version",
                            "--format=csv,noheader"], capture_output=True, text=True, timeout=20)
        return p.stdout.strip().splitlines()[0].strip() or None
    except Exception:  # noqa: BLE001
        return None


def lib_matrix(extra_dirs: tuple[str, ...] = ()) -> dict:
    dirs = tuple(extra_dirs) + SEARCH_DIRS
    drv = driver_version()
    found = {}
    for name in REQUIRED_LIBS:
        stem = name.rstrip("0123456789").rstrip(".")
        hit = None
        for d in dirs:
            for cand in sorted(glob.glob(f"{d}/{stem}*")):
                if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                    hit = cand
                    break
            if hit:
                break
        if hit is None:
            found[name] = {"present": False}
            continue
        real = os.path.realpath(hit)
        ver = re.search(r"\.so\.([0-9][0-9.]*)$", real)
        found[name] = {
            "present": True,
            "path": hit,
            "resolved": real,
            "size": os.path.getsize(real),
            "sha256": sha256_of(real),
            "version_in_name": ver.group(1) if ver else None,
            "matches_driver": bool(ver and drv and ver.group(1) == drv),
        }
    return {"driver_version": drv, "search_dirs": list(dirs), "libs": found,
            "all_present": all(v.get("present") for v in found.values()),
            "all_version_match": all(v.get("matches_driver") for v in found.values() if v.get("present"))}


def egl_vendor_icds() -> dict:
    out = {"env_dirs": os.environ.get("__EGL_VENDOR_LIBRARY_DIRS"),
           "env_filenames": os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES"),
           "icds": {}}
    dirs = ["/usr/share/glvnd/egl_vendor.d", "/etc/glvnd/egl_vendor.d"]
    if out["env_dirs"]:
        dirs = out["env_dirs"].split(":") + dirs
    for d in dirs:
        for p in sorted(glob.glob(f"{d}/*.json")):
            try:
                out["icds"][p] = json.loads(Path(p).read_text())["ICD"]["library_path"]
            except Exception as exc:  # noqa: BLE001
                out["icds"][p] = f"unreadable ({exc})"
    return out


# ── EGL 设备枚举（纯 ctypes，不依赖 PyOpenGL/mujoco） ────────────────────────
def egl_device_probe() -> dict:
    EGL_PLATFORM_DEVICE_EXT = 0x313F
    EGL_DRM_DEVICE_FILE_EXT = 0x3233
    EGL_EXTENSIONS = 0x3055
    EGL_VENDOR = 0x3053
    EGL_VERSION = 0x3054
    res: dict = {"devices": [], "error": None}
    try:
        lib = ctypes.CDLL("libEGL.so.1", mode=ctypes.RTLD_GLOBAL)
    except OSError as exc:
        res["error"] = f"libEGL.so.1 load failed: {exc}"
        return res

    lib.eglGetProcAddress.restype = ctypes.c_void_p
    lib.eglGetProcAddress.argtypes = [ctypes.c_char_p]
    lib.eglQueryString.restype = ctypes.c_char_p
    lib.eglQueryString.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.eglInitialize.restype = ctypes.c_int
    lib.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    lib.eglGetError.restype = ctypes.c_int
    lib.eglTerminate.restype = ctypes.c_int
    lib.eglTerminate.argtypes = [ctypes.c_void_p]

    def ext(name: str, restype, argtypes):
        addr = lib.eglGetProcAddress(name.encode())
        if not addr:
            return None
        return ctypes.CFUNCTYPE(restype, *argtypes)(addr)

    qdev = ext("eglQueryDevicesEXT", ctypes.c_int,
               [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int)])
    qstr = ext("eglQueryDeviceStringEXT", ctypes.c_char_p, [ctypes.c_void_p, ctypes.c_int])
    gpd = ext("eglGetPlatformDisplayEXT", ctypes.c_void_p,
              [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p])
    if not qdev or not gpd:
        res["error"] = ("eglQueryDevicesEXT/eglGetPlatformDisplayEXT 不可得"
                        "（没有任何 vendor 提供 EGL_EXT_device_enumeration）")
        return res

    n = ctypes.c_int(0)
    if not qdev(0, None, ctypes.byref(n)) or n.value <= 0:
        res["error"] = f"eglQueryDevicesEXT 返回 0 个设备 (eglError=0x{lib.eglGetError():04x})"
        return res
    arr = (ctypes.c_void_p * n.value)()
    got = ctypes.c_int(0)
    qdev(n.value, arr, ctypes.byref(got))
    res["device_count"] = got.value
    for i in range(got.value):
        dev = arr[i]
        entry = {"index": i, "drm_device_file": None, "device_extensions": None,
                 "vendor": None, "egl_version": None, "initialize_ok": None, "egl_error": None}
        if qstr:
            drm = qstr(dev, EGL_DRM_DEVICE_FILE_EXT)
            entry["drm_device_file"] = drm.decode() if drm else None
            ext_s = qstr(dev, EGL_EXTENSIONS)
            entry["device_extensions"] = ext_s.decode() if ext_s else None
        disp = gpd(EGL_PLATFORM_DEVICE_EXT, ctypes.c_void_p(dev), None)
        if disp:
            maj, minr = ctypes.c_int(0), ctypes.c_int(0)
            ok = lib.eglInitialize(ctypes.c_void_p(disp), ctypes.byref(maj), ctypes.byref(minr))
            entry["initialize_ok"] = bool(ok)
            entry["egl_error"] = hex(lib.eglGetError())
            if ok:
                v = lib.eglQueryString(ctypes.c_void_p(disp), EGL_VENDOR)
                entry["vendor"] = v.decode() if v else None
                vs = lib.eglQueryString(ctypes.c_void_p(disp), EGL_VERSION)
                entry["egl_version"] = vs.decode() if vs else None
                lib.eglTerminate(ctypes.c_void_p(disp))
        res["devices"].append(entry)
    return res


def cpu_stat() -> dict:
    out = {}
    try:
        for kv in Path("/sys/fs/cgroup/cpu/cpu.stat").read_text().splitlines():
            k, _, v = kv.partition(" ")
            out[k] = int(v)
    except (OSError, ValueError):
        pass
    try:
        out["quota_us"] = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text().strip())
        out["period_us"] = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text().strip())
    except (OSError, ValueError):
        pass
    try:
        out["loadavg"] = Path("/proc/loadavg").read_text().split()[:3]
    except OSError:
        pass
    return out


def nvidia_smi_sample() -> dict:
    try:
        p = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20)
        util, mem = [int(x) for x in p.stdout.strip().split(",")[:2]]
        out = {"utilization_gpu": util, "memory_used_mib": mem}
    except Exception as exc:  # noqa: BLE001
        out = {"error": f"{type(exc).__name__}: {exc}"}
    # 并发 GPU 进程：utilization/memory 是**整机**口径，会被别的进程污染，
    # 必须同时记下当时还有谁在用卡，否则 L5 可以被"别人在跑 CUDA"骗过。
    try:
        q = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=20)
        out["compute_procs"] = [ln.strip() for ln in q.stdout.strip().splitlines() if ln.strip()]
    except Exception as exc:  # noqa: BLE001
        out["compute_procs_error"] = f"{type(exc).__name__}: {exc}"
    return out


def child_nvidia_fds(pid: int) -> list[str]:
    """渲染子进程自己打开了哪些 /dev/nvidia* —— 进程级归因，无法被并发进程伪造。"""
    seen: set[str] = set()
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if "/dev/nvidia" in target:
                seen.add(target)
    except OSError:
        return []
    return sorted(seen)


def run_child(gl: str, sizes: list[int], duration: float, cap: int,
              env_extra: dict, sample_gpu: bool,
              fd_poll_s: float = 0.02, smi_interval_s: float = 0.30) -> dict:
    env = dict(os.environ)
    env["MUJOCO_GL"] = gl
    if gl == "egl":
        env["PYOPENGL_PLATFORM"] = "egl"
    env.update(env_extra)
    proc = subprocess.Popen(
        [sys.executable, "-c", _CHILD, ",".join(str(s) for s in sizes), str(duration), str(cap)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    samples = []
    fd_union: set[str] = set()
    # 采样窗必须**覆盖子进程的整个生命期**。旧实现是「先 `time.sleep(1.0)`，再 `while proc.poll() is None` 采样」
    # ⇒ 子进程活得比 1 s 短就**一个样本都采不到**，而下游把「没采到」读成「没有 fd / 整机没占用」
    # ⇒ **在健康 GPU 上假红**。实测：2026-09-30 02:18:54 子进程 `wall_s=1.001` ⇒ `gpu_samples` 字段整个不存在
    # ⇒ L5 / L5b / S2 三条同时红、`verdict=fail`；对照 21:54:06 子进程 `wall_s=1.343` 侥幸采到 1 个样本 ⇒ `pass`。
    # 同一份代码、同一块卡、结论相反 ⇒ 这是**测量窗竞态**，不是 GPU 状态差异。
    # fd 轮询很便宜（只 `readlink /proc/<pid>/fd/*`，不触卡）⇒ **不论 sample_gpu 与否都轮询**：
    # 这顺手修掉同族的另一处空洞——负对照臂（`expect=cpu`）以前 `sample_gpu=False` ⇒ fd 集恒空
    # ⇒ `N5 变异臂却持有 fd` 永远不可能触发（登记为空洞判据，现在变成真的）。
    fd_polls = 0
    fd_first_hit_s = None
    t0 = time.perf_counter()
    t_last_smi = -1e9
    while proc.poll() is None:
        fd_polls += 1
        fds = child_nvidia_fds(proc.pid)
        if fds:
            if fd_first_hit_s is None:
                fd_first_hit_s = round(time.perf_counter() - t0, 3)
            fd_union.update(fds)
        now = time.perf_counter()
        if sample_gpu and (now - t_last_smi) >= smi_interval_s:
            s = nvidia_smi_sample()
            s["t_offset_s"] = round(now - t0, 3)
            s["child_alive_at_sample"] = True
            samples.append(s)
            t_last_smi = time.perf_counter()
        time.sleep(fd_poll_s)
    child_lifetime_s = round(time.perf_counter() - t0, 3)
    stdout, stderr = proc.communicate(timeout=900)
    payload = None
    for line in stdout.splitlines():
        if line.startswith("RESULT_JSON"):
            payload = json.loads(line[len("RESULT_JSON"):])
    result = payload or {"ok": False, "error": "no result",
                         "stderr_tail": (stderr or stdout).strip().splitlines()[-8:]}
    result["gl"] = gl
    result["returncode"] = proc.returncode
    result["env_extra"] = env_extra
    if samples:
        ok_s = [s for s in samples if "utilization_gpu" in s]
        result["gpu_samples"] = samples
        result["gpu_util_max"] = max((s["utilization_gpu"] for s in ok_s), default=0)
        result["gpu_mem_used_max_mib"] = max((s["memory_used_mib"] for s in ok_s), default=0)
        procs = sorted({p for s in samples for p in (s.get("compute_procs") or [])})
        result["concurrent_compute_procs"] = procs
    result["child_nvidia_fds"] = sorted(fd_union)
    # 「没采到」与「采到但为空」必须是**两个不同的事实**，否则空集合会被读成测量结果。
    result["gpu_sampling"] = {
        "smi_enabled": bool(sample_gpu),
        "n_smi_samples": len(samples),
        "n_fd_polls": fd_polls,
        "fd_poll_interval_s": fd_poll_s,
        "smi_interval_s": smi_interval_s,
        "child_lifetime_s": child_lifetime_s,
        "fd_first_hit_at_s": fd_first_hit_s,
        "window_covered_child_lifetime": fd_polls > 0,
        "fds_measured_not_assumed": fd_polls > 0,
        "smi_measured_not_assumed": (not sample_gpu) or bool(samples),
        "why": ("采样窗覆盖子进程整个生命期（旧实现先 sleep 1.0 s ⇒ 短命子进程一个样本都采不到）。"
                "`*_measured_not_assumed=false` 时，空集合**不是测量结果**：不许读成「没有 fd / 整机没占用」，"
                "调用方必须把本轮判为 `invalid_measurement`（测量无效）而不是 `fail`（GPU 坏了）。"),
    }
    if stderr.strip():
        result["stderr_tail"] = stderr.strip().splitlines()[-8:]
    return result


def decide(report: dict, expect: str) -> tuple[bool, list[str], list[str]]:
    passed, failed = [], []
    libs = report["lib_matrix"]
    probe = report["egl_device_probe"]
    child = report["render_probe"]
    gls = " | ".join(child.get("gl_strings") or []) or "(glGetString 全空：上下文不 current)"
    loaded = child.get("loaded_gl_libs") or {}
    nvidia_loaded = any(k.startswith(("libEGL_nvidia", "libnvidia-glcore")) for k in loaded)
    is_nvidia = ("NVIDIA" in gls) and ("llvmpipe" not in gls) and ("Mesa" not in gls)
    util_max = child.get("gpu_util_max", 0) or 0
    mem_max = child.get("gpu_mem_used_max_mib", 0) or 0
    child_fds = child.get("child_nvidia_fds") or []
    nonblack = child.get("ok") and all(r.get("image_mean", 0) > 1.0
                                       for r in (child.get("renders") or {}).values())
    nvidia_devices = [d for d in probe.get("devices", [])
                      if (d.get("vendor") or "").upper().find("NVIDIA") >= 0]

    def check(cond: bool, label: str):
        (passed if cond else failed).append(label)

    if expect == "gpu":
        check(libs["all_present"], "L1 七个 NVIDIA 渲染库齐全")
        check(libs["all_version_match"],
              f"L1b 库版本 == 驱动版本 {libs['driver_version']}")
        check(len(nvidia_devices) >= 1, "L2 EGL 枚举到 NVIDIA 设备且 EGL_VENDOR 含 NVIDIA")
        check(bool(child.get("ok")) and bool(child.get("gl_strings")) and is_nvidia,
              f"L3 GL_RENDERER 是 NVIDIA（实测: {gls[:90]}）")
        check(bool(nonblack), "L4 渲染非黑")
        # L5 是**整机**口径，只能当旁证（本机实测：并行跑一个 torch CUDA 任务，
        # 连 osmesa 负对照都能采到 util=9%/mem=142MiB）。真正的归因靠 L5b。
        check(util_max > 0 or mem_max > 0,
              f"L5(旁证) 渲染期间整机 GPU 有占用（util_max={util_max}%, mem_max={mem_max} MiB）")
        check(bool(child_fds),
              f"L5b 渲染子进程自己持有 /dev/nvidia* fd（{child_fds or '无'}）")
        check(nvidia_loaded, "L6 进程内真的加载了 libEGL_nvidia/libnvidia-glcore")
    else:
        check(bool(child.get("ok")), "N1 负对照：CPU 后端仍可渲染（不因装库而回退）")
        check(not is_nvidia, f"N2 负对照：GL_RENDERER 不是 NVIDIA（实测: {gls[:90]}）")
        check(not nvidia_loaded, "N3 负对照：进程内没有加载 NVIDIA 渲染库")
        if child.get("gl") == "egl":
            # osmesa 后端根本不走 EGL，考设备枚举没有意义（会假红）
            check(len(nvidia_devices) == 0,
                  f"N4 负对照：EGL 未枚举到 NVIDIA 设备（实际 {len(nvidia_devices)} 个）")
        else:
            passed.append(f"N4 跳过（MUJOCO_GL={child.get('gl')} 不走 EGL）")
    return (not failed), passed, failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True, help="本次验证的标签，写进产物目录名")
    ap.add_argument("--expect", choices=("gpu", "cpu"), default="gpu")
    ap.add_argument("--gl", default="egl", choices=("egl", "osmesa", "glfw"))
    ap.add_argument("--sizes", default="256,512")
    ap.add_argument("--bench-seconds", type=float, default=3.0)
    ap.add_argument("--max-frames", type=int, default=20000)
    ap.add_argument("--lib-dir", action="append", default=[],
                    help="额外库搜索目录（也注入子进程 LD_LIBRARY_PATH，用于 staged 验证）")
    ap.add_argument("--vendor-icd", default=None,
                    help="只用这个 EGL vendor ICD（通过 __EGL_VENDOR_LIBRARY_FILENAMES 注入）")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--no-gpu-sample", action="store_true")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    env_extra: dict = {}
    if args.lib_dir:
        env_extra["LD_LIBRARY_PATH"] = ":".join(args.lib_dir) + (
            ":" + os.environ["LD_LIBRARY_PATH"] if os.environ.get("LD_LIBRARY_PATH") else "")
    if args.vendor_icd:
        env_extra["__EGL_VENDOR_LIBRARY_FILENAMES"] = args.vendor_icd

    report = {
        "label": args.label,
        "expect": args.expect,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "hostname": os.uname().nodename,
        "python": sys.executable,
        "argv": sys.argv,
        "parent_env": {k: os.environ.get(k) for k in (
            "MUJOCO_GL", "MUJOCO_EGL_DEVICE_ID", "NVIDIA_DRIVER_CAPABILITIES",
            "LD_LIBRARY_PATH", "__EGL_VENDOR_LIBRARY_DIRS", "__EGL_VENDOR_LIBRARY_FILENAMES",
            "VK_ICD_FILENAMES", "DISPLAY")},
        "child_env_extra": env_extra,
        "cpu_stat_before": cpu_stat(),
        "lib_matrix": lib_matrix(tuple(args.lib_dir)),
        "egl_vendor_icds": egl_vendor_icds(),
        "dri_nodes": sorted(glob.glob("/dev/dri/*")),
        "nvidia_dev_nodes": sorted(glob.glob("/dev/nvidia*")),
    }
    # 父进程自己做一次 EGL 设备枚举（不受 mujoco 影响）
    probe_env_note = "父进程探测；如需与子进程同环境，见 child_env_extra"
    report["egl_device_probe_note"] = probe_env_note
    report["egl_device_probe"] = _probe_with_env(env_extra)
    report["render_probe"] = run_child(
        args.gl, sizes, args.bench_seconds, args.max_frames, env_extra,
        sample_gpu=not args.no_gpu_sample)
    report["cpu_stat_after"] = cpu_stat()

    ok, passed, failed = decide(report, args.expect)
    report["verdict"] = {"ok": ok, "expect": args.expect, "passed": passed, "failed": failed}

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "runs" / "infra" / f"e_gpu_egl_verify_{time.strftime('%Y%m%d')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.label}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 76)
    print(f"E 线 GPU 渲染验证 · label={args.label} · expect={args.expect}")
    print("=" * 76)
    lm = report["lib_matrix"]
    print(f"  驱动版本(/proc)          : {lm['driver_version']}")
    for name, info in lm["libs"].items():
        if info.get("present"):
            flag = "✓" if info.get("matches_driver") else "✗版本不符"
            print(f"    {flag} {name:<26} {info['resolved']}  v{info['version_in_name']}")
        else:
            print(f"    ✗ {name:<26} 缺失")
    print(f"  /dev/dri                 : {report['dri_nodes'] or '不存在'}")
    print(f"  /dev/nvidia*             : {report['nvidia_dev_nodes']}")
    probe = report["egl_device_probe"]
    if probe.get("error"):
        print(f"  EGL 设备枚举             : 失败 —— {probe['error']}")
    else:
        print(f"  EGL 设备枚举             : {probe.get('device_count')} 个")
        for d in probe.get("devices", []):
            print(f"      [{d['index']}] vendor={d['vendor']} egl={d['egl_version']} "
                  f"drm={d['drm_device_file']} init_ok={d['initialize_ok']}")
    child = report["render_probe"]
    print(f"  mujoco({child.get('mujoco')}) MUJOCO_GL={args.gl} ok={child.get('ok')}")
    if not child.get("ok"):
        print(f"      error: {str(child.get('error'))[:200]}")
        for line in child.get("stderr_tail", []) or []:
            print(f"      | {line}")
    print(f"  GL 身份                  : {' | '.join(child.get('gl_strings') or [])}")
    for size, r in (child.get("renders") or {}).items():
        print(f"      {size}px  rgb {r['fps']:>8} fps ({r['frames']} 帧/{r['seconds']}s)"
              f"  depth {r.get('depth_fps')} fps  image_mean={r['image_mean']}")
    print(f"  渲染期 GPU 采样          : util_max={child.get('gpu_util_max')}% "
          f"mem_max={child.get('gpu_mem_used_max_mib')} MiB (n={len(child.get('gpu_samples') or [])})")
    nvl = sorted(k for k in (child.get("loaded_gl_libs") or {}) if "nvidia" in k.lower())
    print(f"  进程内 NVIDIA 库         : {nvl or '无'}")
    print(f"  loadavg                  : before={report['cpu_stat_before'].get('loadavg')} "
          f"after={report['cpu_stat_after'].get('loadavg')}")
    print(f"  nr_throttled             : before={report['cpu_stat_before'].get('nr_throttled')} "
          f"after={report['cpu_stat_after'].get('nr_throttled')}")
    print("-" * 76)
    for p in report["verdict"]["passed"]:
        print(f"  PASS  {p}")
    for f in report["verdict"]["failed"]:
        print(f"  FAIL  {f}")
    print("-" * 76)
    print(f"  结论: {'通过' if ok else '不通过'}   产物: {out_path}")
    if not ok and args.expect == "cpu":
        # 负对照没通过 = 判据可能恒真（没牙），这是比"GPU 不可用"更严重的问题
        print("  ⚠️ 负对照未通过：判据可能恒真（没牙）。按纪律记 exit 2。")
        return 2
    return 0 if ok else 1


def _probe_with_env(env_extra: dict) -> dict:
    """EGL 设备枚举必须在**与子进程相同的环境**下做，否则 LD_LIBRARY_PATH 不一致会给出假结论。"""
    if not env_extra:
        return egl_device_probe()
    code = ("import json,sys;sys.path.insert(0,%r);"
            "import importlib.util as u;"
            "spec=u.spec_from_file_location('ev',%r);m=u.module_from_spec(spec);spec.loader.exec_module(m);"
            "print('PROBE_JSON'+json.dumps(m.egl_device_probe()))" % (str(REPO_ROOT / "scripts"), __file__))
    env = dict(os.environ)
    env.update(env_extra)
    try:
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    except subprocess.TimeoutExpired:
        return {"error": "probe timeout"}
    for line in p.stdout.splitlines():
        if line.startswith("PROBE_JSON"):
            return json.loads(line[len("PROBE_JSON"):])
    return {"error": f"probe failed: {(p.stderr or p.stdout).strip()[-400:]}"}


if __name__ == "__main__":
    raise SystemExit(main())
