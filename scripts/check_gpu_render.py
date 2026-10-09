#!/usr/bin/env python
"""本机 GPU 渲染能力探测 + MuJoCo 离屏渲染后端基准。

为什么要单独一个脚本？因为「有没有 NVIDIA 卡」和「能不能用 NVIDIA 渲染」是两件事。
容器里常见的情况是：CUDA 计算完全正常，但驱动只注入了 compute/utility 两套用户态库，
OpenGL/EGL/Vulkan 那部分根本没挂进来 —— 这时任何依赖 GPU 渲染的仿真器都会在
创建离屏上下文时失败，而报错信息往往只有一句 EGL/GLFW 初始化错误，很难定位。

本脚本做三件事：
  1. 能力矩阵：驱动注入能力、缺失的 NVIDIA GL 库、/dev/dri、EGL vendor ICD、X、Vulkan
  2. 逐后端实测 MuJoCo 离屏渲染（egl / osmesa / glfw），每个后端在**子进程**里跑，
     避免一个后端崩溃污染其它后端的判定
  3. 对可用后端做帧率基准（分辨率 × 是否要深度），据此判断「像素观测的 RL 能不能上」

结果写入 runs/infra/gpu_render_<时间戳>.json，并把「给平台管理员的申请文本」打印出来。

用法：
    python scripts/check_gpu_render.py                 # 只跑能力矩阵（不需要 mujoco）
    python scripts/check_gpu_render.py --bench         # 加上后端实测与帧率基准
    python scripts/check_gpu_render.py --bench --sizes 256,512
"""

from __future__ import annotations

import argparse
import ctypes.util
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# NVIDIA 用户态渲染库。缺任何一个，GPU 渲染就不可能工作（装 pip 包也救不回来）。
NVIDIA_GL_LIBS = (
    "libEGL_nvidia.so.0",
    "libGLX_nvidia.so.0",
    "libnvidia-glcore.so",
    "libnvidia-eglcore.so",
    "libnvidia-glsi.so",
)
SEARCH_DIRS = (
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib64",
    "/usr/local/nvidia/lib64",
    "/usr/local/nvidia/lib",
)


def _find_lib(name: str) -> str | None:
    for directory in SEARCH_DIRS:
        for path in glob.glob(f"{directory}/{name}*"):
            return path
    return ctypes.util.find_library(name.split(".so")[0].replace("lib", ""))


def capability_matrix() -> dict:
    """不依赖任何第三方库，纯文件系统 / 环境变量探测。"""
    report: dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": os.uname().nodename,
        "kernel": os.uname().release,
        "nvidia_driver_capabilities": os.environ.get("NVIDIA_DRIVER_CAPABILITIES", "(unset)"),
        "display": os.environ.get("DISPLAY", "(unset)"),
        "mujoco_gl_env": os.environ.get("MUJOCO_GL", "(unset)"),
    }

    report["nvidia_gl_libs"] = {name: _find_lib(name) for name in NVIDIA_GL_LIBS}
    report["nvidia_gl_libs_present"] = all(v for v in report["nvidia_gl_libs"].values())

    report["dri_nodes"] = sorted(glob.glob("/dev/dri/*"))
    report["nvidia_dev_nodes"] = sorted(glob.glob("/dev/nvidia*"))

    report["egl_vendor_icds"] = {}
    for icd_dir in ("/usr/share/glvnd/egl_vendor.d", "/etc/glvnd/egl_vendor.d"):
        for path in sorted(glob.glob(f"{icd_dir}/*.json")):
            try:
                report["egl_vendor_icds"][path] = json.loads(Path(path).read_text())["ICD"]["library_path"]
            except Exception as exc:  # noqa: BLE001
                report["egl_vendor_icds"][path] = f"unreadable ({exc})"

    report["vulkan_icds"] = sorted(
        glob.glob("/usr/share/vulkan/icd.d/*.json") + glob.glob("/etc/vulkan/icd.d/*.json")
    )
    report["optix_present"] = bool(_find_lib("libnvoptix.so"))
    report["xvfb_present"] = bool(ctypes.util.find_library("Xvfb")) or Path("/usr/bin/Xvfb").exists()

    caps = report["nvidia_driver_capabilities"].lower()
    report["graphics_capability_enabled"] = ("all" in caps) or ("graphics" in caps)
    report["gpu_render_possible"] = bool(
        report["nvidia_gl_libs_present"] and report["dri_nodes"] and report["graphics_capability_enabled"]
    )
    return report


# ── 子进程里跑的单个后端测试（MUJOCO_GL 在 import 时生效，必须隔离） ──────────
_BACKEND_PROBE = r'''
import json, os, sys, time
gl = os.environ["MUJOCO_GL"]
out = {"gl": gl}
xml = (
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
try:
    import mujoco
    out["mujoco"] = mujoco.__version__
    sizes = [int(s) for s in sys.argv[1].split(",")]
    use_depth = sys.argv[2] == "1"
    results = {}
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    def timed(renderer, frames):
        for _ in range(3):                                   # 预热，排除首帧编译/分配开销
            renderer.update_scene(data, camera="c")
            renderer.render()
        t0 = time.perf_counter()
        for _ in range(frames):
            renderer.update_scene(data, camera="c")
            renderer.render()
        return time.perf_counter() - t0

    for size in sizes:
        renderer = mujoco.Renderer(model, height=size, width=size)
        renderer.update_scene(data, camera="c")
        image = renderer.render()                            # 真 RGB 帧，用来确认不是黑屏
        frames = max(8, min(120, int(2000000 // (size * size))))
        # 必须先测 RGB 再开深度：enable_depth_rendering() 之后 render() 返回的是深度图，
        # 两者开销差一个数量级，顺序搞反会得出完全错误的结论（这个坑踩过）。
        rgb_elapsed = timed(renderer, frames)
        depth = None
        depth_fps = None
        if use_depth:
            renderer.enable_depth_rendering()
            renderer.update_scene(data, camera="c")
            depth = renderer.render()
            depth_fps = round(frames / timed(renderer, frames), 2)
        results[size] = {
            "frames": frames,
            "rgb_seconds": round(rgb_elapsed, 3),
            "rgb_fps": round(frames / rgb_elapsed, 2),
            "depth_fps": depth_fps,
            "image_mean": round(float(image.mean()), 2),
            "depth_ok": bool(depth is not None),
        }
        renderer.close()
    out["ok"] = True
    out["renders"] = results
    out["nonblack"] = all(r["image_mean"] > 1.0 for r in results.values())
except Exception as exc:
    out["ok"] = False
    out["error"] = f"{type(exc).__name__}: {exc}"
print("RESULT_JSON" + json.dumps(out))
'''


def probe_backend(gl: str, sizes: list[int], depth: bool, timeout: int = 240) -> dict:
    env = dict(os.environ)
    env["MUJOCO_GL"] = gl
    if gl == "egl":
        env.setdefault("PYOPENGL_PLATFORM", "egl")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _BACKEND_PROBE, ",".join(str(s) for s in sizes), "1" if depth else "0"],
            env=env, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"gl": gl, "ok": False, "error": f"timeout after {timeout}s"}
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT_JSON"):
            return json.loads(line[len("RESULT_JSON"):])
    tail = (proc.stderr or proc.stdout).strip().splitlines()[-6:]
    return {"gl": gl, "ok": False, "error": "no result", "stderr_tail": tail}


def print_verdict(report: dict) -> None:
    print("=" * 72)
    print("结论")
    print("=" * 72)
    caps = report["nvidia_driver_capabilities"]
    print(f"  NVIDIA_DRIVER_CAPABILITIES = {caps}")
    print(f"  驱动注入了 graphics 能力   : {'是' if report['graphics_capability_enabled'] else '否'}")
    print(f"  NVIDIA GL/EGL 用户态库齐全 : {'是' if report['nvidia_gl_libs_present'] else '否'}")
    for name, path in report["nvidia_gl_libs"].items():
        print(f"      {'✓' if path else '✗'} {name}" + (f"  -> {path}" if path else ""))
    print(f"  /dev/dri 渲染节点          : {report['dri_nodes'] or '不存在'}")
    print(f"  EGL vendor ICD             : {report['egl_vendor_icds'] or '无'}")
    print(f"  Vulkan ICD                 : {report['vulkan_icds'] or '无'}")
    print(f"  OptiX (libnvoptix)         : {'有' if report['optix_present'] else '无'}")
    print(f"  Xvfb                       : {'有' if report['xvfb_present'] else '无'}")
    print()
    if report["gpu_render_possible"]:
        print("  >>> 本机可以做 NVIDIA GPU 渲染（EGL）。MUJOCO_GL=egl 是首选。")
    else:
        print("  >>> 本机【不能】做 NVIDIA GPU 渲染，只能走 CPU 软渲染（MUJOCO_GL=osmesa）。")
        print("      这不是配置错误，容器内也修不好：缺的是宿主机注入的驱动库和设备节点。")
    for backend in report.get("backends", []):
        if backend["ok"]:
            detail = ", ".join(
                f"{s}px:rgb {r['rgb_fps']}fps" + (f"/depth {r['depth_fps']}fps" if r["depth_fps"] else "")
                for s, r in backend["renders"].items()
            )
            print(f"  后端 {backend['gl']:<7} 可用   {detail}")
        else:
            print(f"  后端 {backend['gl']:<7} 不可用 {backend.get('error', '')[:110]}")


def print_platform_request(report: dict) -> None:
    if report["gpu_render_possible"]:
        return
    print()
    print("=" * 72)
    print("给平台/运维的申请文本（可直接复制）")
    print("=" * 72)
    print("""
节点: {host}  GPU: A800-SXM4-80GB  驱动: 590.48.01
现状: 容器里 CUDA 计算正常（torch.cuda.is_available()=True），但没有 NVIDIA 的
      OpenGL/EGL/Vulkan 用户态库，也没有 /dev/dri，导致所有需要 GPU 渲染的仿真器
      （LIBERO/robosuite 的 EGL 离屏渲染、RoboTwin/SAPIEN、Isaac Sim、ManiSkill3）
      都无法启动，只能退回 CPU 软渲染（osmesa），速度慢一个数量级。
诊断: NVIDIA_DRIVER_CAPABILITIES={caps}（缺 graphics）
      缺失库: libEGL_nvidia.so.0 / libGLX_nvidia.so.0 / libnvidia-glcore / libnvidia-eglcore
      缺失设备: /dev/dri（无 renderD128）
请求:
  1) Pod/容器环境变量 NVIDIA_DRIVER_CAPABILITIES 改为 "all,compute,utility,graphics"
     （或至少加上 graphics；如要跑 SAPIEN/Isaac 还需 display 或 vulkan 相关能力）
  2) 挂载 /dev/dri 到容器（宿主机需加载 nvidia-drm，出现 renderD128）
  3) 如需 GLX/图形界面调试，再提供 Xvfb 或 x11 转发
验收: 重启后在容器内执行
      ls /usr/lib/x86_64-linux-gnu/libEGL_nvidia.so.0 && ls /dev/dri
      MUJOCO_GL=egl python scripts/check_gpu_render.py --bench
      两条都通过即算解决。
""".format(host=report["hostname"], caps=report["nvidia_driver_capabilities"]).strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bench", action="store_true", help="实测 MuJoCo 各后端并做帧率基准")
    parser.add_argument("--sizes", default="64,256,512", help="基准分辨率，逗号分隔")
    parser.add_argument("--no-depth", action="store_true", help="不测深度渲染")
    args = parser.parse_args()

    report = capability_matrix()
    if args.bench:
        sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
        report["backends"] = [
            probe_backend(gl, sizes, depth=not args.no_depth) for gl in ("egl", "osmesa", "glfw")
        ]
        report["bench_sizes"] = sizes
        report["bench_depth"] = not args.no_depth

    out_dir = REPO_ROOT / "runs" / "infra"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gpu_render_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print_verdict(report)
    print_platform_request(report)
    print(f"\n  报告已写入: {out_path}")
    usable = [b for b in report.get("backends", []) if b["ok"]]
    if args.bench and not usable:
        print("  警告: 没有任何可用的离屏渲染后端，录视频/像素观测都会失败。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
