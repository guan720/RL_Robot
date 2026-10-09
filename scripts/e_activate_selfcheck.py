#!/usr/bin/env python
"""E 线 E3-1 的**自证件**：`scripts/e_activate_gpu_render.sh --selfcheck` 调它。

D 执行单 §8.3-1 要求的自证判据：**`GL_RENDERER` 含 `NVIDIA` + 子进程持有 `/dev/nvidia*` fd**。
本脚本把这两条放进 E1 已被 D 复核通过的同一套判据里（复用 `e_gpu_egl_verify.decide`
的 L1–L6 / N1–N4，**不另写一套**，避免两处定义漂移 = 裁定 46.4 的口径搬运根因）。

三件额外的、属于"激活件"本身的牙：
  A1 边界闸（前）：系统目录里若已有 NVIDIA 渲染库/vendor ICD ⇒ **exit 3 拒跑**（§3.2 / 裁定 60）；
  A2 版本一致：前缀库版本必须与 `nvidia-smi` 的驱动版本**逐字相同**（版本错配是这套方案唯一真风险）；
  A3 边界闸（后）：自证跑完**再核一次**系统目录 ⇒ 证明激活与自证过程本身零系统写入（幂等）。

`--mode cpu` / `mesa_egl` 走 N1–N4 负对照分支：**渲染子进程必须一个 /dev/nvidia* fd 都不持有**，
`GL_RENDERER` 必须是 llvmpipe —— 若变异臂也判绿，说明判据没牙，本脚本会红。

产物：`runs/infra/e_activate_selfcheck_20260929/selfcheck_<mode>_<ts>.json`（含 `loadavg`+`nr_throttled` 成对）。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import e_gpu_egl_verify as ev  # noqa: E402
import e_egl_probe as ep       # noqa: E402

MODE = os.environ.get("E_MODE", "egl_nvidia")
PREFIX = Path(os.environ.get("E_PREFIX") or str(ep.PREFIX))
VENDOR_ICD = os.environ.get("E_VENDOR_ICD") or str(PREFIX / "10_nvidia.json")
OUT_DIR = Path(os.environ.get("E_OUT_DIR")
               or str(REPO_ROOT / "runs" / "infra" / "e_activate_selfcheck_20260929"))
EXPECT = "cpu" if MODE in ("cpu", "osmesa", "mesa_egl") else "gpu"


def main() -> int:
    ts = time.strftime("%Y%m%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rep: dict = {
        "label": f"activate_selfcheck_{MODE}",
        "probe": "scripts/e_activate_selfcheck.py",
        "activation_artifact": "scripts/e_activate_gpu_render.sh",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "hostname": os.uname().nodename,
        "python": sys.executable,
        "mode": MODE,
        "expect": EXPECT,
        "ambient_env": {k: os.environ.get(k) for k in (
            "MUJOCO_GL", "PYOPENGL_PLATFORM", "LD_LIBRARY_PATH",
            "__EGL_VENDOR_LIBRARY_FILENAMES", "__EGL_VENDOR_LIBRARY_DIRS",
            "VK_ICD_FILENAMES", "NVIDIA_DRIVER_CAPABILITIES", "DISPLAY")},
        "prefix": str(PREFIX),
        "vendor_icd": VENDOR_ICD,
        "load_before": ev.cpu_stat(),
    }

    # A1 边界闸（前）—— 脏则拒跑，连库都不加载
    guard_before = ep.boundary_guard()
    rep["boundary_guard_before"] = guard_before
    if not guard_before["ok"]:
        rep["verdict"] = "refused"
        rep["refuse_reason"] = ("系统目录里出现 NVIDIA 渲染库 / vendor ICD ⇒ 违反 D 执行单 §3.2 与裁定 60。"
                                "先用 scripts/e_install_nvidia_gl_590.sh --uninstall 回滚（**需 D 批准**）再跑。")
        _dump(rep, ts)
        print(json.dumps({"ok": False, "verdict": "refused",
                          "hits": guard_before["forbidden_paths_present"],
                          "render_lib_hits": guard_before["system_render_lib_hits"]},
                         ensure_ascii=False, indent=1))
        return 3

    # A2 版本一致
    drv = ev.driver_version()
    prefix_libs = ev.lib_matrix(extra_dirs=(str(PREFIX),))
    rep["driver_version"] = drv
    rep["lib_matrix"] = prefix_libs
    version_ok = bool(drv) and prefix_libs.get("driver_version") == drv and prefix_libs.get("all_version_match")
    rep["A2_version_match"] = {"ok": bool(version_ok), "driver": drv,
                               "lib_matrix_driver_version": prefix_libs.get("driver_version"),
                               "all_version_match": prefix_libs.get("all_version_match"),
                               "all_present": prefix_libs.get("all_present")}

    # EGL 设备枚举 + 渲染子进程（GPU 采样 + 子进程 fd 归因）
    rep["egl_device_probe"] = ev.egl_device_probe() if MODE != "osmesa" else {"skipped": "osmesa 不走 EGL"}
    gpu_idle = ev.nvidia_smi_sample()
    rep["gpu_baseline_idle"] = gpu_idle
    # 观测窗必须**长于**采样周期，否则「没采到」会被读成「没有占用」——这正是 02:18:54 假红的根因
    # （旧值 0.6 s / 400 帧 ⇒ 子进程 wall_s≈1.0，而旧采样先 sleep 1.0 s ⇒ 采样窗为空）。
    # **只对 GPU 臂加长**（1.2 s / 8000 帧 ⇒ 子进程生命期 ≈3 s，够采 ≥4 个 nvidia-smi 样本 + 上百次 fd 轮询）；
    # 负对照臂（expect=cpu）**口径一字不动**，保住 N1–N4 与历史产物的可比性。
    # 两个值都可由环境覆盖，且**实测值写进产物**（口径可追溯，不靠记性）。
    probe_seconds = float(os.environ.get("E_PROBE_BENCH_SECONDS", "1.2" if EXPECT == "gpu" else "0.6"))
    probe_frames = int(os.environ.get("E_PROBE_FRAMES", "8000" if EXPECT == "gpu" else "400"))
    rep["probe_bench_seconds"] = probe_seconds
    rep["probe_frames_cap"] = probe_frames
    t0 = time.perf_counter()
    child = ev.run_child("egl" if EXPECT == "gpu" or MODE == "mesa_egl" else "osmesa",
                         [64], probe_seconds, probe_frames, {}, sample_gpu=(EXPECT == "gpu"))
    child["wall_s"] = round(time.perf_counter() - t0, 3)
    rep["render_probe"] = child

    ok_decide, passed, failed = ev.decide(rep, EXPECT)
    rep["criteria_passed"] = passed
    rep["criteria_failed"] = failed
    rep["decide_ok"] = ok_decide
    rep["A1_boundary_clean_before"] = guard_before["ok"]
    # A3 边界闸（后）：证明激活 + 自证过程零系统写入
    guard_after = ep.boundary_guard()
    rep["boundary_guard_after"] = guard_after
    rep["A3_boundary_clean_after"] = guard_after["ok"]
    rep["A3_no_system_write"] = guard_after["ok"] and guard_after == guard_before

    extra_failed = []
    if not version_ok:
        extra_failed.append(f"A2 版本不一致（driver={drv}, prefix={prefix_libs.get('driver_version')}）")
    if not guard_after["ok"]:
        extra_failed.append("A3 自证后系统目录变脏（激活件写了系统路径）")
    if EXPECT == "gpu" and not child.get("child_nvidia_fds"):
        extra_failed.append("S2 渲染子进程未持有任何 /dev/nvidia* fd（D §8.3-1 指定判据）")
    if EXPECT == "cpu" and child.get("child_nvidia_fds"):
        extra_failed.append(f"N5 变异臂却持有 /dev/nvidia* fd: {child['child_nvidia_fds']}")
    gls = " | ".join(child.get("gl_strings") or [])
    if EXPECT == "gpu" and "NVIDIA" not in gls:
        extra_failed.append(f"S1 GL_RENDERER 不含 NVIDIA（实测: {gls[:120]}）")
    if EXPECT == "cpu" and "llvmpipe" not in gls:
        extra_failed.append(f"N2b 变异臂 GL_RENDERER 不是 llvmpipe（实测: {gls[:120]}）")

    # ── 测量完整性（**先于**判定）：采样窗没覆盖子进程 ⇒ L5/L5b/S2 的空集合不是测量结果 ──
    # 这一档是为了把「GPU 真的坏了」（fail / exit 1）与「本轮没测到」（invalid_measurement / exit 2）分开：
    # 两者都不许采集 egl 数字，但处置完全不同（前者查驱动/库，后者重跑即可）。混为一谈会让运维在
    # 重启后拿着一个假红去查一块好卡——P0（裁定 85.9-3-1）的那一条命令必须能给出**正确**的响亮失败。
    samp = child.get("gpu_sampling") or {}
    integrity_bad = bool(samp) and not (samp.get("fds_measured_not_assumed", True)
                                        and samp.get("smi_measured_not_assumed", True))
    rep["measurement_integrity"] = {
        "ok": not integrity_bad,
        "observed": {k: samp.get(k) for k in ("n_fd_polls", "n_smi_samples", "child_lifetime_s",
                                              "fd_first_hit_at_s", "window_covered_child_lifetime",
                                              "fds_measured_not_assumed", "smi_measured_not_assumed")},
        "if_bad": ("本轮 L5 / L5b / S2 读到的空集合是「没采到」而不是「测到没有」⇒ 判 "
                   "`invalid_measurement` + **exit 2**（不是 `fail` + exit 1）：GPU 既没被证明坏、"
                   "也没被证明好 ⇒ 必须重跑，且**不得**据此采集任何标 egl 的数字。"),
    }
    if integrity_bad:
        extra_failed.append("M0 采样窗未覆盖子进程生命期 ⇒ L5/L5b/S2 不是测量结果"
                            "（判 invalid_measurement，**不是** GPU 坏了）")
    rep["activation_criteria_failed"] = extra_failed
    rep["verdict"] = ("invalid_measurement" if integrity_bad
                      else ("pass" if (ok_decide and not extra_failed) else "fail"))
    rep["gl_strings"] = child.get("gl_strings")
    rep["child_nvidia_fds"] = child.get("child_nvidia_fds")
    rep["load_after"] = ev.cpu_stat()
    path = _dump(rep, ts)

    print(json.dumps({
        "verdict": rep["verdict"], "mode": MODE, "expect": EXPECT,
        "gl_strings": rep["gl_strings"], "child_nvidia_fds": rep["child_nvidia_fds"],
        "measurement_integrity_ok": rep["measurement_integrity"]["ok"],
        "gpu_util_max": child.get("gpu_util_max"), "gpu_mem_used_max_mib": child.get("gpu_mem_used_max_mib"),
        "fps_64": (child.get("renders") or {}).get("64", {}).get("fps"),
        "passed": passed, "failed": failed + extra_failed,
        "loadavg": [rep["load_before"].get("loadavg"), rep["load_after"].get("loadavg")],
        "nr_throttled": [rep["load_before"].get("nr_throttled"), rep["load_after"].get("nr_throttled")],
        "artifact": str(path),
    }, ensure_ascii=False, indent=1))
    return 0 if rep["verdict"] == "pass" else (2 if rep["verdict"] == "invalid_measurement" else 1)


def _dump(rep: dict, ts: str) -> Path:
    path = OUT_DIR / f"selfcheck_{MODE}_{ts}.json"
    path.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
