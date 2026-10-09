#!/usr/bin/env python
"""E 线 E1（P0 判定型）：EGL vendor 可行性探针 —— 严格照 D 执行单 §3.1/§3.2/§3.3 实现。

执行单：`rl_harness_supervision/d_handoff_to_e_20260929.md`
落地方式**只允许一种**（§3.2）：库放 `.codex-persist/egl-libs/590.48.01/`（NFS 前缀），
只在**测试进程的环境变量**里生效（`LD_LIBRARY_PATH` + `__EGL_VENDOR_LIBRARY_FILENAMES`）。
**绝不**写 `/usr/share/glvnd/egl_vendor.d/`、**绝不**拷进 `/usr/lib/x86_64-linux-gnu/`、
**绝不** `ldconfig`、**绝不**改 `NVIDIA_DRIVER_CAPABILITIES`。

本脚本把这条边界做成**可执行的前置闸**（`boundary_guard`）：只要系统目录里出现
NVIDIA 渲染库或 vendor ICD，探针直接 exit 3 拒跑 —— 边界不靠自觉，靠代码。

六条绿判据（§3.3）逐条对应：
  C1 `eglQueryDevicesEXT` ≥1 设备且可归因 NVIDIA（记 `eglQueryString(display, EGL_VENDOR)` 原文）
  C2 `eglCreateContext` + `eglMakeCurrent` 成功（纯 ctypes 走完整条链，不借 mujoco）
  C3 mujoco 离屏渲染，`GL_RENDERER` 不含 llvmpipe、`GL_VENDOR` 不是 Mesa（打印原文）
  C4 渲染**进行中**采 `nvidia-smi`：utilization.gpu>0 或 memory.used 相对空载上升（同批记空载）
  C5 出图非黑且帧间互异：`raw_len == h*w*3`、`byte_std > 0`、连续三帧 `identical=false`
  C6 吞吐 A/B —— 由 `scripts/e_backend_ab.py` 承担（同 venv/同模型/同分辨率只换后端）
两条变异体：
  M1 `__EGL_VENDOR_LIBRARY_FILENAMES` 指回 `50_mesa.json` ⇒ `GL_RENDERER` 必须回到 llvmpipe
  M2 把前缀里的 `libEGL_nvidia.so.0` **移到 recycle_bin**（不 rm）⇒ 设备枚举必须 0 或报错
     （跑完自动移回并核 sha256，恢复失败则 exit 4）

**必须用带 mujoco 的解释器跑**（`/root/venvs/rlrobot/bin/python` 或 `/root/venvs/pi05_sim/bin/python`）：
自证子进程沿用 `sys.executable`，用裸 `python3`（conda，无 mujoco）会让 C3–C5b **假红**；
本脚本已把这种情况判为 `环境无效`（exit 5）而不是 `不通过`，但别指望它替你选解释器。

用法：
  /root/venvs/rlrobot/bin/python scripts/e_egl_probe.py --stage precheck
  /root/venvs/rlrobot/bin/python scripts/e_egl_probe.py --stage green [--vendor-mode filenames|dirs]
  /root/venvs/rlrobot/bin/python scripts/e_egl_probe.py --stage m1
  /root/venvs/rlrobot/bin/python scripts/e_egl_probe.py --stage m2
  /root/venvs/rlrobot/bin/python scripts/e_egl_probe.py --stage all
"""

from __future__ import annotations

import argparse
import ctypes
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import e_gpu_egl_verify as ev  # noqa: E402  复用采样/归因/库矩阵，不重复实现

PERSIST = Path("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist")
PREFIX = PERSIST / "egl-libs" / "590.48.01"
SRC_DEBS = PERSIST / "egl-libs" / "_src_590.48.01" / "deb"
RECYCLE = Path("/workspace/mnt/sppro/yhzhang91/recycle_bin")
OUT_DIR = REPO_ROOT / "runs" / "infra" / "e_egl_probe_20260929"
MESA_ICD = "/usr/share/glvnd/egl_vendor.d/50_mesa.json"
FORBIDDEN_SYSTEM_PATHS = (
    "/usr/lib/x86_64-linux-gnu/libEGL_nvidia.so.0",
    "/usr/lib/x86_64-linux-gnu/libGLX_nvidia.so.0",
    "/usr/lib/x86_64-linux-gnu/libnvidia-glcore.so.590.48.01",
    "/usr/lib/x86_64-linux-gnu/libnvidia-eglcore.so.590.48.01",
    "/usr/share/glvnd/egl_vendor.d/10_nvidia.json",
    "/usr/share/vulkan/icd.d/nvidia_icd.json",
)
REQUIRED_PREFIX_LIBS = (
    "libEGL_nvidia.so.0", "libGLX_nvidia.so.0", "libnvidia-glcore.so.590.48.01",
    "libnvidia-eglcore.so.590.48.01", "libnvidia-glsi.so.590.48.01",
    "libnvidia-gpucomp.so.590.48.01", "libnvidia-tls.so.590.48.01",
)

# ── §3.2 边界闸 ─────────────────────────────────────────────────────────────
def boundary_guard() -> dict:
    """系统目录必须干净；否则拒跑（这条闸是为了让 §3.2 的边界可核，而不是靠自觉）。"""
    present = [p for p in FORBIDDEN_SYSTEM_PATHS if os.path.exists(p)]
    listing = {}
    for d in ("/usr/share/glvnd/egl_vendor.d", "/usr/share/vulkan/icd.d"):
        listing[d] = sorted(os.listdir(d)) if os.path.isdir(d) else "(目录不存在)"
    render_lib_hits = sorted(
        os.path.basename(p) for p in glob.glob("/usr/lib/x86_64-linux-gnu/lib*nvidia*")
        if re.search(r"glcore|eglcore|glsi|gpucomp|EGL_nvidia|GLX_nvidia|glvkspirv|nvoptix", p))
    return {
        "ok": not present and not render_lib_hits,
        "forbidden_paths_present": present,
        "system_render_lib_hits": render_lib_hits,
        "icd_dir_listing": listing,
        "prefix": str(PREFIX),
        "prefix_exists": PREFIX.is_dir(),
        "prefix_libs": {n: (PREFIX / n).exists() for n in REQUIRED_PREFIX_LIBS},
        "prefix_libs_complete": all((PREFIX / n).exists() for n in REQUIRED_PREFIX_LIBS),
        "prefix_vendor_json": (PREFIX / "10_nvidia.json").exists(),
    }


def prefix_env(vendor_mode: str = "filenames", vendor_icd: str | None = None,
               mujoco_gl: str = "egl") -> dict:
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = str(PREFIX) + (
        ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    icd = vendor_icd or str(PREFIX / "10_nvidia.json")
    if vendor_mode == "dirs":
        env["__EGL_VENDOR_LIBRARY_DIRS"] = str(PREFIX)
        env.pop("__EGL_VENDOR_LIBRARY_FILENAMES", None)
    else:
        env["__EGL_VENDOR_LIBRARY_FILENAMES"] = icd
        env.pop("__EGL_VENDOR_LIBRARY_DIRS", None)
    env["MUJOCO_GL"] = mujoco_gl
    env["PYOPENGL_PLATFORM"] = "egl"
    return env


# ── §3.1 零成本前置检查（否定型主张必须枚举全清单）──────────────────────────
def precheck() -> dict:
    out: dict = {"stage": "precheck", "commands": []}

    def run(cmd: str, timeout: int = 60) -> dict:
        try:
            p = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout)
            rec = {"cmd": cmd, "rc": p.returncode,
                   "stdout_lines": len(p.stdout.splitlines()),
                   "stdout_head": p.stdout.strip().splitlines()[:12],
                   "stderr_head": p.stderr.strip().splitlines()[:6]}
        except subprocess.TimeoutExpired:
            rec = {"cmd": cmd, "rc": None, "timeout": True}
        out["commands"].append(rec)
        return rec

    # 1) libEGL.so.1 的符号面：先枚举全部符号再下结论（裁定 50.1）
    allsy = run("nm -D /usr/lib/x86_64-linux-gnu/libEGL.so.1 | wc -l")
    out["libegl_total_dynamic_symbols"] = int(allsy["stdout_head"][0]) if allsy["stdout_head"] else None
    want = ("eglQueryDevicesEXT", "eglQueryDeviceStringEXT", "eglGetPlatformDisplayEXT",
            "eglGetProcAddress", "eglGetPlatformDisplay")
    out["libegl_exported"] = {s: None for s in want}
    for s in want:
        r = run(f"nm -D /usr/lib/x86_64-linux-gnu/libEGL.so.1 | grep -c ' {s}$' || true")
        out["libegl_exported"][s] = int(r["stdout_head"][0]) if r["stdout_head"] else 0
    run("dpkg -l libglvnd0 libegl1 | grep ^ii")

    # 2) 590.48.01 的库是怎么进来的（deb？镜像层拷贝？）
    run("dpkg -l | grep -ci nvidia || true")
    run("dpkg -S libnvidia-ml.so.590.48.01 2>&1 | head -2 || true")
    run("dpkg -S libcuda.so.590.48.01 2>&1 | head -2 || true")

    # 3) 驱动版本逐字核对
    run("cat /proc/driver/nvidia/version")
    run("nvidia-smi --query-gpu=driver_version,name --format=csv,noheader")
    drv = ev.driver_version()
    out["driver_version"] = drv
    out["prefix_version_dir_name"] = PREFIX.parent.name + "/" + PREFIX.name
    out["version_exact_match"] = bool(drv) and drv == PREFIX.name

    # 4) 本地是否已有副本（限定超时，不扫全 NFS）
    for d in ("/var/cache/apt/archives", str(PERSIST / "pip-cache"), str(PERSIST / "uv-cache")):
        run(f"timeout 30 find {d} -maxdepth 3 \\( -name '*nvidia-gl*' -o -name 'libEGL_nvidia*' "
            f"-o -name 'NVIDIA-Linux-x86_64-*' \\) 2>/dev/null | wc -l")
    run("timeout 120 find / -xdev \\( -name 'libEGL_nvidia*' -o -name 'libnvidia-eglcore*' \\) "
        "-not -path '*/egl-libs/*' 2>/dev/null | wc -l")

    # 5) 下载来源与逐文件 sha256（§3.1-5 要求全记录）
    debs = []
    if SRC_DEBS.is_dir():
        for p in sorted(SRC_DEBS.glob("*.deb")):
            debs.append({"path": str(p), "bytes": p.stat().st_size,
                         "sha256": ev.sha256_of(str(p)),
                         "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime))})
    out["source_debs"] = debs
    out["source_urls"] = [
        "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/"
        "libnvidia-gl_590.48.01-0ubuntu1_amd64.deb",
        "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/"
        "libnvidia-gpucomp_590.48.01-0ubuntu1_amd64.deb",
    ]
    out["source_note"] = ("301 重定向到 developer.download.nvidia.cn；经公司代理 "
                          "http://10.2.162.180:3128；实测 41 MB/s（102 MiB 用 2.7 s）。"
                          "runfile 通道 download.nvidia.com/XFree86/Linux-x86_64/590.48.01/ 也可达"
                          "（HTTP 200，416,273,526 B，4.26 MB/s），未使用。"
                          "us.download.nvidia.com/tesla/590.48.01/ 超时（25 s，0 字节）。")
    out["prefix_lib_sha256"] = {}
    for n in REQUIRED_PREFIX_LIBS:
        p = PREFIX / n
        real = Path(os.path.realpath(p)) if p.exists() else None
        out["prefix_lib_sha256"][n] = {
            "exists": p.exists(), "resolved": str(real) if real else None,
            "bytes": real.stat().st_size if real and real.is_file() else None,
            "sha256": ev.sha256_of(str(real)) if real else None}
    return out


# ── C2：纯 ctypes 走完 EGL 建上下文全链（不借 mujoco）───────────────────────
_EGLCTX_CHILD = r'''
import ctypes, json, os, sys

EGL_PLATFORM_DEVICE_EXT = 0x313F
EGL_OPENGL_API = 0x30A2
EGL_SURFACE_TYPE, EGL_PBUFFER_BIT = 0x3033, 0x0001
EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT = 0x3040, 0x0008
EGL_ALPHA_SIZE, EGL_BLUE_SIZE, EGL_GREEN_SIZE, EGL_RED_SIZE = 0x3021, 0x3022, 0x3023, 0x3024
EGL_DEPTH_SIZE, EGL_STENCIL_SIZE = 0x3025, 0x3026
EGL_NONE, EGL_WIDTH, EGL_HEIGHT = 0x3038, 0x3057, 0x3058
EGL_VENDOR, EGL_VERSION, EGL_EXTENSIONS = 0x3053, 0x3054, 0x3055
EGL_CONTEXT_MAJOR_VERSION, EGL_CONTEXT_MINOR_VERSION = 0x3098, 0x30FB
GL_VENDOR, GL_RENDERER, GL_VERSION = 0x1F00, 0x1F01, 0x1F02

out = {"child_argv_env": {k: os.environ.get(k) for k in
                          ("LD_LIBRARY_PATH", "__EGL_VENDOR_LIBRARY_FILENAMES",
                           "__EGL_VENDOR_LIBRARY_DIRS", "MUJOCO_GL")},
       "steps": []}

def note(step, ok, **kw):
    out["steps"].append({"step": step, "ok": bool(ok), **kw})
    return ok

try:
    lib = ctypes.CDLL("libEGL.so.1", mode=ctypes.RTLD_GLOBAL)
    note("dlopen libEGL.so.1", True, path=lib._name)
except OSError as exc:
    note("dlopen libEGL.so.1", False, error=str(exc)); print("RESULT_JSON" + json.dumps(out)); raise SystemExit(0)

lib.eglGetProcAddress.restype = ctypes.c_void_p
lib.eglGetProcAddress.argtypes = [ctypes.c_char_p]
lib.eglGetError.restype = ctypes.c_int
lib.eglQueryString.restype = ctypes.c_char_p
lib.eglQueryString.argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.eglInitialize.restype = ctypes.c_int
lib.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
lib.eglBindAPI.restype = ctypes.c_int
lib.eglBindAPI.argtypes = [ctypes.c_uint]
lib.eglChooseConfig.restype = ctypes.c_int
lib.eglChooseConfig.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                                ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
lib.eglCreatePbufferSurface.restype = ctypes.c_void_p
lib.eglCreatePbufferSurface.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
lib.eglCreateContext.restype = ctypes.c_void_p
lib.eglCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.POINTER(ctypes.c_int)]
lib.eglMakeCurrent.restype = ctypes.c_int
lib.eglMakeCurrent.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

def ext(name, restype, argtypes):
    addr = lib.eglGetProcAddress(name.encode())
    return ctypes.CFUNCTYPE(restype, *argtypes)(addr) if addr else None

qdev = ext("eglQueryDevicesEXT", ctypes.c_int,
           [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int)])
gpd = ext("eglGetPlatformDisplayEXT", ctypes.c_void_p,
          [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p])
if not note("eglGetProcAddress(eglQueryDevicesEXT)", qdev is not None):
    print("RESULT_JSON" + json.dumps(out)); raise SystemExit(0)

n = ctypes.c_int(0)
ok = qdev(0, None, ctypes.byref(n))
if not note("eglQueryDevicesEXT(count)", ok and n.value >= 1, num_devices=n.value,
            egl_error=hex(lib.eglGetError())):
    print("RESULT_JSON" + json.dumps(out)); raise SystemExit(0)
out["num_devices"] = n.value
arr = (ctypes.c_void_p * n.value)()
qdev(n.value, arr, ctypes.byref(n))

chosen = None
for i in range(n.value):
    disp = gpd(EGL_PLATFORM_DEVICE_EXT, ctypes.c_void_p(arr[i]), None)
    if not disp:
        continue
    maj, mnr = ctypes.c_int(0), ctypes.c_int(0)
    if not lib.eglInitialize(ctypes.c_void_p(disp), ctypes.byref(maj), ctypes.byref(mnr)):
        continue
    v = lib.eglQueryString(ctypes.c_void_p(disp), EGL_VENDOR)
    vendor = v.decode() if v else None
    ver = lib.eglQueryString(ctypes.c_void_p(disp), EGL_VERSION)
    out.setdefault("displays", []).append(
        {"index": i, "vendor": vendor, "egl_version": ver.decode() if ver else None,
         "initialize_ok": True, "major": maj.value, "minor": mnr.value})
    if chosen is None:
        chosen = (disp, vendor)
if not note("eglGetPlatformDisplayEXT + eglInitialize", chosen is not None,
            vendor=(chosen[1] if chosen else None)):
    print("RESULT_JSON" + json.dumps(out)); raise SystemExit(0)
disp = ctypes.c_void_p(chosen[0])
out["display_vendor"] = chosen[1]

note("eglBindAPI(EGL_OPENGL_API)", lib.eglBindAPI(EGL_OPENGL_API) == 1, egl_error=hex(lib.eglGetError()))
cfg_attribs = (ctypes.c_int * 15)(EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                                  EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
                                  EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
                                  EGL_ALPHA_SIZE, 8, EGL_DEPTH_SIZE, 24, EGL_NONE)
cfg = ctypes.c_void_p()
ncfg = ctypes.c_int(0)
ok = lib.eglChooseConfig(disp, cfg_attribs, ctypes.byref(cfg), 1, ctypes.byref(ncfg))
if not note("eglChooseConfig", ok == 1 and ncfg.value >= 1, num_configs=ncfg.value,
            egl_error=hex(lib.eglGetError())):
    print("RESULT_JSON" + json.dumps(out)); raise SystemExit(0)
# C2 按**消费者的真实路径**判：mujoco 的 EGL 后端根本不建 pbuffer，它走 surfaceless
# （mujoco/egl/__init__.py:113-125：eglCreateContext(..., None) +
#   eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)）。
# 本机实测：NVIDIA vendor 在 device platform 上对 eglCreatePbufferSurface 返回
# EGL_BAD_PARAMETER(0x300c)，而 Mesa 能建 ⇒ pbuffer 只作为**信息项**记录，不作判据。
pb_attribs = (ctypes.c_int * 5)(EGL_WIDTH, 224, EGL_HEIGHT, 224, EGL_NONE)
surf = lib.eglCreatePbufferSurface(disp, cfg, pb_attribs)
out["pbuffer_probe"] = {"created": bool(surf), "egl_error": hex(lib.eglGetError()),
                        "note": "信息项，非判据；NVIDIA device platform 上返回 0x300c"}
ctx = lib.eglCreateContext(disp, cfg, None, None)
if not note("eglCreateContext", bool(ctx), requested="default(surfaceless, 与 mujoco 同路径)",
            egl_error=hex(lib.eglGetError())):
    print("RESULT_JSON" + json.dumps(out)); raise SystemExit(0)
if not note("eglMakeCurrent(surfaceless)",
            lib.eglMakeCurrent(disp, ctypes.c_void_p(0), ctypes.c_void_p(0),
                               ctypes.c_void_p(ctx)) == 1,
            egl_error=hex(lib.eglGetError())):
    print("RESULT_JSON" + json.dumps(out)); raise SystemExit(0)
try:
    gl = ctypes.CDLL("libGL.so.1")
    gl.glGetString.restype = ctypes.c_char_p
    gl.glGetString.argtypes = [ctypes.c_uint]
    strs = {}
    for name, const in (("GL_VENDOR", GL_VENDOR), ("GL_RENDERER", GL_RENDERER), ("GL_VERSION", GL_VERSION)):
        v = gl.glGetString(const)
        strs[name] = v.decode() if v else None
    out["gl_strings"] = strs
    note("glGetString", bool(strs.get("GL_RENDERER")), **strs)
except OSError as exc:
    note("glGetString", False, error=str(exc))
print("RESULT_JSON" + json.dumps(out))
'''

_SELFCERT_CHILD = r'''
import hashlib, json, os, sys, time
import numpy as np

XML = ("<mujoco><option gravity='0 0 -9.81'/>"
       "<visual><global offwidth='512' offheight='512'/></visual>"
       "<worldbody><light pos='0 0 3' dir='0 0 -1'/>"
       "<camera name='c' pos='1.6 0 1.0' xyaxes='0 1 0 -0.6 0 1'/>"
       "<body pos='0 0 1.2'><joint type='free'/><geom type='sphere' size='0.12' rgba='0.2 0.6 0.9 1'/></body>"
       "<geom type='plane' size='2 2 0.1'/></worldbody></mujoco>")
H = W = 224
out = {"model": "toy_freefall_sphere(自由落体，帧间必然互异)", "resolution": [H, W],
       "mujoco_gl": os.environ.get("MUJOCO_GL"), "frames": []}
try:
    import mujoco
    out["mujoco"] = mujoco.__version__
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)
    rend = mujoco.Renderer(model, height=H, width=W)
    prev = None
    for i in range(3):
        for _ in range(20):                      # 每帧之间推进物理，保证内容真的变了
            mujoco.mj_step(model, data)
        rend.update_scene(data, camera="c")
        img = rend.render()
        raw = np.asarray(img).tobytes()
        rec = {"frame": i, "raw_len": len(raw), "expected_raw_len": H * W * 3,
               "raw_len_ok": len(raw) == H * W * 3,
               "byte_std": round(float(np.asarray(img).std()), 4),
               "byte_mean": round(float(np.asarray(img).mean()), 4),
               "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
               "identical_to_prev": (prev == raw) if prev is not None else None}
        prev = raw
        out["frames"].append(rec)
    # GL 身份必须在 renderer 还活着时取（close() 之后 glGetString 返回 NULL）
    try:
        from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString
        out["gl_strings"] = [s.decode() if isinstance(s, bytes) else str(s)
                             for s in (glGetString(GL_VENDOR), glGetString(GL_RENDERER),
                                       glGetString(GL_VERSION)) if s]
    except Exception as exc:
        out["gl_strings_error"] = f"{type(exc).__name__}: {exc}"
    rend.close()
    out["ok"] = True
except Exception as exc:
    import traceback
    out["ok"] = False
    out["error"] = f"{type(exc).__name__}: {exc}"
    out["traceback_tail"] = traceback.format_exc().strip().splitlines()[-6:]
print("RESULT_JSON" + json.dumps(out))
'''


def _spawn_child(code: str, env: dict, timeout: int = 300) -> dict:
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=env, timeout=timeout)
    for line in p.stdout.splitlines():
        if line.startswith("RESULT_JSON"):
            res = json.loads(line[len("RESULT_JSON"):])
            res["returncode"] = p.returncode
            if p.stderr.strip():
                res["stderr_tail"] = p.stderr.strip().splitlines()[-8:]
            return res
    return {"ok": False, "error": "no result", "returncode": p.returncode,
            "stderr_tail": (p.stderr or p.stdout).strip().splitlines()[-10:]}


def gpu_idle_baseline(n: int = 5) -> dict:
    samples = [ev.nvidia_smi_sample() for _ in range(n)]
    ok = [s for s in samples if "utilization_gpu" in s]
    return {"n": len(ok),
            "utilization_gpu_max": max((s["utilization_gpu"] for s in ok), default=None),
            "memory_used_mib_max": max((s["memory_used_mib"] for s in ok), default=None),
            "samples": samples}


def environment_invalid(sc: dict) -> str | None:
    """自证子进程连 `mujoco` 都 import 不到 ⇒ **跑探针的解释器不对**，不是渲染坏了。

    这种情况下 C3/C5/C5b 会**假红**（`gl_strings_via_mujoco=null`、`frames=[]`、`fds=[]`），
    读起来像"GPU 渲染回归了" ⇒ 必须判 `环境无效`（`all_ok=None`）而不是 `不通过`。
    E 自己 22:28 就踩了一次：用裸 `python3`（conda，无 mujoco）跑 `--stage green`，
    三条判据全红，而同一时刻 `--selfcheck` 用 rlrobot 解释器是**六条全绿**。
    """
    err = str(sc.get("error") or "")
    if sc.get("mujoco") is None and ("No module named" in err or "ImportError" in err):
        return (f"自证子进程缺依赖：{err}；sys.executable={sys.executable}。"
                f"请用**带 mujoco 的解释器**重跑，例如："
                f"/root/venvs/rlrobot/bin/python scripts/e_egl_probe.py --stage all")
    return None


def run_green(vendor_mode: str, with_gpu_sampling: bool = True) -> dict:
    env = prefix_env(vendor_mode=vendor_mode)
    res: dict = {"stage": "green", "vendor_mode": vendor_mode,
                 "child_env": {k: env.get(k) for k in ("LD_LIBRARY_PATH",
                                                       "__EGL_VENDOR_LIBRARY_FILENAMES",
                                                       "__EGL_VENDOR_LIBRARY_DIRS", "MUJOCO_GL")},
                 "cpu_stat_before": ev.cpu_stat()}
    if with_gpu_sampling:
        res["gpu_idle_baseline"] = gpu_idle_baseline()
    res["C2_egl_context_chain"] = _spawn_child(_EGLCTX_CHILD, env)
    # C3/C5 + C4：mujoco 自证要在渲染**进行中**采 nvidia-smi，所以用 Popen 版本
    res["C3_C5_mujoco_selfcert"] = _run_selfcert_with_sampling(env, with_gpu_sampling)
    res["cpu_stat_after"] = ev.cpu_stat()
    inv = environment_invalid(res["C3_C5_mujoco_selfcert"])
    if inv:
        res["environment_invalid"] = inv
        res["criteria"] = {"expect_nvidia": True, "checks": {}, "all_ok": None,
                           "invalid_reason": inv, "evidence": None}
        return res
    res["criteria"] = judge_green(res, expect_nvidia=True)
    return res


def _run_selfcert_with_sampling(env: dict, sample: bool) -> dict:
    proc = subprocess.Popen([sys.executable, "-c", _SELFCERT_CHILD],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    samples, fds = [], set()
    while proc.poll() is None:
        if sample:
            samples.append(ev.nvidia_smi_sample())
            fds.update(ev.child_nvidia_fds(proc.pid))
        time.sleep(0.2)
    stdout, stderr = proc.communicate(timeout=300)
    payload = None
    for line in stdout.splitlines():
        if line.startswith("RESULT_JSON"):
            payload = json.loads(line[len("RESULT_JSON"):])
    out = payload or {"ok": False, "error": "no result",
                      "stderr_tail": (stderr or stdout).strip().splitlines()[-10:]}
    ok_s = [s for s in samples if "utilization_gpu" in s]
    out["gpu_samples_during_render"] = samples
    out["gpu_util_max_during_render"] = max((s["utilization_gpu"] for s in ok_s), default=None)
    out["gpu_mem_used_max_during_render"] = max((s["memory_used_mib"] for s in ok_s), default=None)
    out["concurrent_compute_procs"] = sorted({p for s in samples for p in (s.get("compute_procs") or [])})
    out["child_nvidia_fds"] = sorted(fds)
    out["returncode"] = proc.returncode
    return out


def judge_green(res: dict, expect_nvidia: bool) -> dict:
    ctx = res.get("C2_egl_context_chain") or {}
    sc = res.get("C3_C5_mujoco_selfcert") or {}
    steps = {s["step"]: s for s in ctx.get("steps", [])}
    gls = " | ".join(sc.get("gl_strings") or [])
    gls_ctx = " | ".join(
        str(v) for v in ((ctx.get("gl_strings") or {}).values()) if v)
    frames = sc.get("frames") or []
    nvidia_devices = [d for d in ctx.get("displays", [])
                      if "NVIDIA" in (d.get("vendor") or "")]
    idle = res.get("gpu_idle_baseline") or {}
    util = sc.get("gpu_util_max_during_render")
    mem = sc.get("gpu_mem_used_max_during_render")
    idle_mem = idle.get("memory_used_mib_max")
    checks = {
        "C1_egl_devices_nvidia": (len(nvidia_devices) >= 1) if expect_nvidia else (len(nvidia_devices) == 0),
        "C2_context_and_makecurrent": bool(steps.get("eglCreateContext", {}).get("ok"))
        and bool(steps.get("eglMakeCurrent(surfaceless)", {}).get("ok")),
        "C3_gl_renderer_not_llvmpipe": (("llvmpipe" not in gls) and ("Mesa" not in gls) and bool(gls))
        if expect_nvidia else (("llvmpipe" in gls) or ("Mesa" in gls)),
        "C4_gpu_busy_during_render": (expect_nvidia and (
            (util or 0) > (idle.get("utilization_gpu_max") or 0)
            or (mem or 0) > (idle_mem or 0))) or (not expect_nvidia and (util or 0) == 0),
        "C5_frames_nonblack_and_distinct": bool(frames) and all(
            f["raw_len_ok"] and f["byte_std"] > 0 for f in frames) and all(
            f["identical_to_prev"] is False for f in frames[1:]),
        "C5b_child_holds_nvidia_fd": (bool(sc.get("child_nvidia_fds")) if expect_nvidia
                                      else not sc.get("child_nvidia_fds")),
    }
    return {"expect_nvidia": expect_nvidia, "checks": checks,
            "all_ok": all(checks.values()),
            # 键名歧义自报（E3 轮补）：`checks` 里每个键的语义是**「是否符合本臂预期」**，不是字面断言。
            # 变异臂（expect_nvidia=false）里 `C3_gl_renderer_not_llvmpipe=true` 的意思是
            # **「确实是 llvmpipe/Mesa」= 符合预期**，而不是「不是 llvmpipe」。逻辑本身按 expect_nvidia
            # 分支取值（见上），**不是恒真闸**；但键名会误导读者 ⇒ 显式登记预期文本，并在回流单里自报。
            "check_expectations": {
                "C1_egl_devices_nvidia": "≥1 个 NVIDIA EGL 设备" if expect_nvidia else "0 个 NVIDIA EGL 设备",
                "C2_context_and_makecurrent": "eglCreateContext + eglMakeCurrent(surfaceless) 都成功",
                "C3_gl_renderer_not_llvmpipe": ("GL_RENDERER 不含 llvmpipe/Mesa 且非空" if expect_nvidia
                                                else "GL_RENDERER 含 llvmpipe 或 Mesa（变异臂预期）"),
                "C4_gpu_busy_during_render": ("渲染期间 util 或显存高于空载基线" if expect_nvidia
                                              else "渲染期间 util == 0（变异臂预期）"),
                "C5_frames_nonblack_and_distinct": "帧长 == h*w*3、byte_std>0、连续三帧互异",
                "C5b_child_holds_nvidia_fd": ("子进程持有 /dev/nvidia* fd" if expect_nvidia
                                              else "子进程**不**持有任何 /dev/nvidia* fd"),
            },
            "semantics_note": ("checks 各键 = 「符合本臂预期」；expect_nvidia=%s。"
                               "键名沿用 E1 首次落盘写法（改键名会动 D 已复核的产物 schema，本轮不改）。"
                               % expect_nvidia),
            "evidence": {
                "num_egl_devices": ctx.get("num_devices"),
                "egl_displays": ctx.get("displays"),
                "display_vendor": ctx.get("display_vendor"),
                "context_requested": ctx.get("context_requested"),
                "gl_strings_via_egl_context": ctx.get("gl_strings"),
                "gl_strings_via_mujoco": sc.get("gl_strings"),
                "gpu_util_max_during_render": util,
                "gpu_mem_used_max_during_render": mem,
                "gpu_idle_baseline": idle,
                "child_nvidia_fds": sc.get("child_nvidia_fds"),
                "concurrent_compute_procs": sc.get("concurrent_compute_procs"),
                "frames": frames,
                "mujoco_version": sc.get("mujoco"),
                "mujoco_gl": sc.get("mujoco_gl"),
                "model": sc.get("model"),
            }}


def run_m1() -> dict:
    """M1：ICD 指回 50_mesa.json ⇒ 必须回到 llvmpipe（证明"绿"是这套库带来的）。"""
    env = prefix_env(vendor_icd=MESA_ICD)
    res = {"stage": "m1", "mutation": "__EGL_VENDOR_LIBRARY_FILENAMES → 50_mesa.json",
           "child_env": {k: env.get(k) for k in ("LD_LIBRARY_PATH",
                                                 "__EGL_VENDOR_LIBRARY_FILENAMES", "MUJOCO_GL")},
           "cpu_stat_before": ev.cpu_stat(),
           "gpu_idle_baseline": gpu_idle_baseline()}
    res["C2_egl_context_chain"] = _spawn_child(_EGLCTX_CHILD, env)
    res["C3_C5_mujoco_selfcert"] = _run_selfcert_with_sampling(env, True)
    res["cpu_stat_after"] = ev.cpu_stat()
    inv = environment_invalid(res.get("C3_C5_mujoco_selfcert") or {})
    if inv:
        res["environment_invalid"] = inv
        res["criteria"] = {"expect_nvidia": False, "checks": {}, "all_ok": None,
                           "invalid_reason": inv, "evidence": None}
        res["mutation_verdict"] = {"ok": None, "invalid_reason": inv}
        return res
    res["criteria"] = judge_green(res, expect_nvidia=False)
    res["mutation_verdict"] = {
        "ok": res["criteria"]["all_ok"],
        "meaning": "M1 通过 = 判据有牙：同一套库、同一台机，只把 vendor ICD 换回 mesa，"
                   "GL_RENDERER 必须退回 llvmpipe 且 GPU 全程 0 占用。",
    }
    return res


def run_m2() -> dict:
    """M2：把前缀里的 libEGL_nvidia.so.0 移到 recycle_bin ⇒ 枚举必须 0 或报错；跑完移回并核 sha256。"""
    targets = [PREFIX / "libEGL_nvidia.so.0", PREFIX / "libEGL_nvidia.so.590.48.01"]
    ts = time.strftime("%Y%m%d_%H%M%S")
    rb = RECYCLE / f"e_egl_probe_m2_{ts}"
    before = {str(t): {"exists": t.exists(), "is_symlink": t.is_symlink(),
                       "sha256": ev.sha256_of(os.path.realpath(t)) if t.exists() else None}
              for t in targets}
    res = {"stage": "m2", "mutation": f"移出 {len(targets)} 个文件 → {rb}",
           "before": before, "recycle_bin": str(rb), "moved": [], "restored": False,
           "cpu_stat_before": ev.cpu_stat()}
    rb.mkdir(parents=True, exist_ok=True)
    try:
        for t in targets:
            if t.exists() or t.is_symlink():
                shutil.move(str(t), str(rb / t.name))     # 移动，不 rm
                res["moved"].append(t.name)
        env = prefix_env(vendor_mode="filenames")
        res["child_env"] = {k: env.get(k) for k in ("LD_LIBRARY_PATH",
                                                    "__EGL_VENDOR_LIBRARY_FILENAMES")}
        res["egl_probe_without_vendor_lib"] = _spawn_child(_EGLCTX_CHILD, env, timeout=180)
        res["mujoco_without_vendor_lib"] = _run_selfcert_with_sampling(env, False)
    finally:
        for t in targets:
            src = rb / t.name
            if src.exists() or src.is_symlink():
                shutil.move(str(src), str(t))
        res["restored"] = all(t.exists() or t.is_symlink() for t in targets)
        res["after"] = {str(t): {"exists": t.exists(), "is_symlink": t.is_symlink(),
                                 "sha256": ev.sha256_of(os.path.realpath(t)) if t.exists() else None}
                        for t in targets}
    sha_ok = all(res["after"][k]["sha256"] == v["sha256"] for k, v in res["before"].items())
    steps = {s["step"]: s for s in (res["egl_probe_without_vendor_lib"].get("steps") or [])}
    enum_step = steps.get("eglQueryDevicesEXT(count)") or {}
    enum_failed = (not enum_step.get("ok")) or (enum_step.get("num_devices", 1) == 0)
    gls = " | ".join(res["mujoco_without_vendor_lib"].get("gl_strings") or [])
    res["cpu_stat_after"] = ev.cpu_stat()
    res["mutation_verdict"] = {
        "ok": bool(res["restored"]) and sha_ok and enum_failed and ("NVIDIA A800" not in gls),
        "enumeration_returned_zero_or_error": enum_failed,
        "num_devices_observed": enum_step.get("num_devices"),
        "egl_error": enum_step.get("egl_error"),
        "gl_renderer_after_mutation": gls or "(空)",
        "prefix_restored": bool(res["restored"]),
        "sha256_matches_before": sha_ok,
        "meaning": "M2 通过 = 判据有牙：把 vendor 库从前缀移走，设备枚举必须归零/报错，"
                   "GL_RENDERER 不得再是 NVIDIA。前缀已按 sha256 复原。",
    }
    return res


MANIFEST_DESC = {
    "precheck_": ("§3.1 零成本前置检查：libEGL.so.1 全符号枚举、590.48.01 库来源(dpkg?)、"
                  "驱动版本逐字核对、本地副本搜索计数、源 deb 的 sha256 与前缀库 sha256 表",
                  "E1 判定依据（只读探测）"),
    "green_filenames_": ("§3.3 六条绿判据，vendor 注入方式 = __EGL_VENDOR_LIBRARY_FILENAMES",
                         "E1 主判定"),
    "green_dirs_": ("§3.3 六条绿判据，vendor 注入方式 = __EGL_VENDOR_LIBRARY_DIRS"
                    "（D 要求两种都试并记录哪个生效：**两种都生效**）", "E1 主判定"),
    "m1_": ("变异体 M1：ICD 指回 50_mesa.json ⇒ GL_RENDERER 必须回到 llvmpipe、GPU 全程 0 占用",
            "判据有牙的证据（负向）"),
    "m2_": ("变异体 M2：把前缀里的 libEGL_nvidia.so.0 移到 recycle_bin ⇒ 设备枚举必须归零/报错；"
            "跑完自动移回并按 sha256 复核", "判据有牙的证据（负向）"),
    "ab_piper_single_arm_": ("E2 后端 A/B：单臂 Piper 3cam 224²（复用 D 的 piper_single_arm_sweep.py "
                             "worker，只读不改），三后端 × 并行度 1/2/4 × 独立进程 3 重复",
                             "E2 吞吐重标定（D 权威口径）"),
    "ab_gym_aloha_": ("E2 后端 A/B：gym-aloha 双臂 3cam 224²（A2 sec_throughput 的 render-only 口径，"
                      "改独立进程重复），三后端 × 并行度 1 × 3 重复",
                      "E2 吞吐重标定（A2 口径；双臂，与用户「先只渲单臂」指令的冲突已报 D）"),
    "MANIFEST.json": ("本清单", "索引"),
}

# 逐文件的额外批注（**假红留档**必须点名，否则下一个复核的人会拿它当结论）
MANIFEST_FILE_NOTES = {
    "green_filenames_20260929_222803.json":
        "**假红留档，勿当结论**：这一批是用裸 `python3`（conda，无 mujoco）跑的，"
        "自证子进程 `ModuleNotFoundError: No module named 'mujoco'` ⇒ C3/C5/C5b 假红"
        "（`gl_strings_via_mujoco=null`、`frames=[]`、`fds=[]`），而同一时刻 C1/C2（纯 ctypes 的 EGL 链）"
        "仍绿、`GL_RENDERER=NVIDIA A800-SXM4-80GB`。**渲染没坏，是解释器不对**。"
        "已被 `green_filenames_20260929_223047.json`（rlrobot 解释器，六条全过）取代；"
        "保留它是为了留证 `environment_invalid` 这个闸为什么必须存在。",
    "green_dirs_20260929_222803.json":
        "**假红留档，勿当结论**：同上（裸 python3 缺 mujoco）。已被 `green_dirs_20260929_2230*.json` 取代。",
    "m1_20260929_222804.json":
        "**假红留档，勿当结论**：同上（裸 python3 缺 mujoco）⇒ 当时打印成「M1 未通过（判据可能恒真）」，"
        "其实是环境无效。已被 `m1_20260929_2230*.json`（M1 通过、判据有牙）取代。",
}


def write_manifest(payloads: dict | None = None, stages: list[str] | None = None) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = {}
    for p in sorted(OUT_DIR.iterdir()):
        if p.is_file():
            desc, scope = "(未登记)", "unlisted_引用前须核对"
            for prefix, (d, s) in MANIFEST_DESC.items():
                if p.name.startswith(prefix) or p.name == prefix:
                    desc, scope = d, s
                    break
            rows[p.name] = {"bytes": p.stat().st_size,
                            "sha256_12": (ev.sha256_of(str(p)) or "")[:12],
                            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime)),
                            "desc": desc, "scope": scope}
    man = {
        "manifest": str(OUT_DIR.relative_to(REPO_ROOT)) + "/MANIFEST.json",
        "agent": "E",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "task_order": "rl_harness_supervision/d_handoff_to_e_20260929.md",
        "prefix": str(PREFIX),
        "boundary": "prefix-only（未写系统目录 / 未 ldconfig / 未改 NVIDIA_DRIVER_CAPABILITIES）",
        "boundary_note": ("21:02–21:18 曾违规写入系统目录并已全量回滚，"
                          "见 docs/e_handoff_to_d_20260929.md §1"),
        "stages_run": sorted(stages or list(payloads or {})),
        "n_files": len(rows),
        "file_notes": {k: v for k, v in MANIFEST_FILE_NOTES.items() if (OUT_DIR / k).exists()},
        "files": rows,
    }
    path = OUT_DIR / "MANIFEST.json"
    path.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="all",
                    choices=("precheck", "green", "m1", "m2", "manifest", "all"))
    ap.add_argument("--vendor-mode", default="filenames", choices=("filenames", "dirs"))
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    guard = boundary_guard()
    print("=" * 78)
    print(f"E 线 E1 EGL 可行性探针 · stage={args.stage} · vendor-mode={args.vendor_mode}")
    print("=" * 78)
    print(f"  前缀            : {guard['prefix']} (exists={guard['prefix_exists']}, "
          f"libs_complete={guard['prefix_libs_complete']}, vendor_json={guard['prefix_vendor_json']})")
    print(f"  系统目录边界闸  : {'干净' if guard['ok'] else '被污染 → 拒跑'}")
    for d, files in guard["icd_dir_listing"].items():
        print(f"      {d}: {files}")
    if guard["system_render_lib_hits"]:
        print(f"      /usr/lib/x86_64-linux-gnu 渲染库命中: {guard['system_render_lib_hits']}")
    if not guard["ok"]:
        print("  REFUSE: §3.2 明写「绝不写系统目录 / 绝不 ldconfig」。当前系统目录里存在 NVIDIA 渲染库或")
        print("          vendor ICD ⇒ 本探针拒绝运行。请先回滚：")
        print("          bash scripts/e_install_nvidia_gl_590.sh --uninstall --apply")
        return 3
    if not guard["prefix_libs_complete"] or not guard["prefix_vendor_json"]:
        print(f"  REFUSE: 前缀不完整 {guard['prefix_libs']}")
        return 3

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stages = ["precheck", "green", "m1", "m2"] if args.stage == "all" else [args.stage]
    if args.stage == "manifest":
        man = write_manifest(stages=["precheck", "green_filenames", "green_dirs", "m1", "m2",
                                     "ab_piper_single_arm", "ab_gym_aloha"])
        print(f"  MANIFEST 重写: {man}")
        return 0
    payloads: dict = {}
    for stage in stages:
        if stage == "precheck":
            payloads[stage] = precheck()
            payloads[stage]["boundary_guard"] = guard
            pc = payloads[stage]
            print(f"\n---- precheck（§3.1）----")
            print(f"  libEGL.so.1 动态符号总数     : {pc['libegl_total_dynamic_symbols']}")
            print(f"  其中导出的关键符号计数        : {pc['libegl_exported']}")
            print(f"  驱动版本(/proc)              : {pc['driver_version']}")
            print(f"  与前缀目录名逐字一致          : {pc['version_exact_match']}")
            print(f"  源 deb 数                    : {len(pc['source_debs'])}")
            for d in pc["source_debs"]:
                print(f"      {Path(d['path']).name}  {d['bytes']} B  sha256={d['sha256'][:16]}…")
        elif stage == "green":
            for mode in (("filenames", "dirs") if args.stage == "all" else (args.vendor_mode,)):
                key = f"green_{mode}"
                payloads[key] = run_green(mode)
                r = payloads[key]
                print(f"\n---- green（vendor-mode={mode}）----")
                if r["criteria"].get("all_ok") is None:
                    print(f"  **环境无效（不是渲染失败）**：{r['criteria']['invalid_reason']}")
                    print(f"  EGL 侧仍可用：C1/C2 见 C2_egl_context_chain；本次未判 C3–C5b")
                    continue
                evd = r["criteria"]["evidence"]
                print(f"  EGL 设备数                   : {evd['num_egl_devices']}")
                for d in evd["egl_displays"] or []:
                    print(f"      [{d['index']}] vendor={d['vendor']} egl={d['egl_version']} "
                          f"init_ok={d['initialize_ok']}")
                print(f"  C2 上下文链                  : requested={evd['context_requested']} "
                      f"steps_ok={[s['step'] for s in r['C2_egl_context_chain'].get('steps', []) if s['ok']]}")
                print(f"  GL 身份(EGL 上下文直取)      : {evd['gl_strings_via_egl_context']}")
                print(f"  GL 身份(mujoco 内)           : {' | '.join(evd['gl_strings_via_mujoco'] or [])}")
                for f in evd["frames"]:
                    print(f"      frame{f['frame']}: raw_len={f['raw_len']}(期望{f['expected_raw_len']}) "
                          f"std={f['byte_std']} sha12={f['sha256_12']} identical_prev={f['identical_to_prev']}")
                print(f"  渲染中 GPU                   : util_max={evd['gpu_util_max_during_render']}% "
                      f"mem_max={evd['gpu_mem_used_max_during_render']}MiB "
                      f"(空载基线 {evd['gpu_idle_baseline']})")
                print(f"  子进程 /dev/nvidia* fd       : {evd['child_nvidia_fds']}")
                for k, v in r["criteria"]["checks"].items():
                    print(f"      {'PASS' if v else 'FAIL'}  {k}")
                print(f"  结论: {'六条判据通过' if r['criteria']['all_ok'] else '有不通过'}")
        elif stage == "m1":
            payloads["m1"] = run_m1()
            r = payloads["m1"]
            print(f"\n---- M1 变异体（ICD 指回 50_mesa.json）----")
            if r["criteria"].get("all_ok") is None:
                print(f"  **环境无效（不是判据恒真）**：{r['criteria']['invalid_reason']}")
                return 5
            print(f"  GL 身份                      : {' | '.join(r['criteria']['evidence']['gl_strings_via_mujoco'] or [])}")
            print(f"  渲染中 GPU util_max          : {r['criteria']['evidence']['gpu_util_max_during_render']}%")
            for k, v in r["criteria"]["checks"].items():
                print(f"      {'PASS' if v else 'FAIL'}  {k}")
            print(f"  M1 结论: {'通过（判据有牙）' if r['mutation_verdict']['ok'] else '未通过（判据可能恒真）'}")
        elif stage == "m2":
            payloads["m2"] = run_m2()
            r = payloads["m2"]
            print(f"\n---- M2 变异体（前缀里移走 libEGL_nvidia.so.0 → recycle_bin）----")
            print(f"  移走文件                     : {r['moved']}")
            print(f"  枚举结果                     : num_devices={r['mutation_verdict']['num_devices_observed']} "
                  f"egl_error={r['mutation_verdict']['egl_error']} "
                  f"归零或报错={r['mutation_verdict']['enumeration_returned_zero_or_error']}")
            print(f"  GL_RENDERER                  : {r['mutation_verdict']['gl_renderer_after_mutation'][:110]}")
            print(f"  前缀复原                     : restored={r['restored']} sha256一致={r['mutation_verdict']['sha256_matches_before']}")
            print(f"  M2 结论: {'通过（判据有牙）' if r['mutation_verdict']['ok'] else '未通过'}")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    for name, payload in payloads.items():
        payload["boundary_guard"] = guard
        payload["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
        label = args.label or stamp
        (OUT_DIR / f"{name}_{label}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    man = write_manifest(payloads)
    print(f"\n  产物目录: {OUT_DIR}")
    print(f"  MANIFEST: {man}")
    if any((v.get("criteria") or {}).get("all_ok") is None for v in payloads.values()):
        print("\n** 本轮有批次判为「环境无效」：解释器缺 mujoco，C3–C5b 未参与判定；"
              "换 /root/venvs/rlrobot/bin/python 重跑 **")
        return 5
    green_ok = all(v["criteria"]["all_ok"] for k, v in payloads.items() if k.startswith("green"))
    mut_ok = all(v.get("mutation_verdict", {}).get("ok", True)
                 for k, v in payloads.items() if k in ("m1", "m2"))
    if not green_ok or not mut_ok:
        return 1 if green_ok else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
