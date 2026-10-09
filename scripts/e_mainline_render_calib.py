#!/usr/bin/env python
"""E 线 E3-2/3/4：**prefix-only 合规路径下**的主线渲染口径重标定。

对应 D 执行单 §8.3 的三项（`rl_harness_supervision/d_handoff_to_e_20260929.md`）：
  E3-2 下游吞吐必须在**合规路径**下重测（既有 `downstream_gpu_*` 是系统安装态测的，主线不能用）；
  E3-3 主线口径 = `gym_aloha/AlohaTransferCube-v0` + **A2 的 29.4118 Hz shim**（`envs/gym_aloha_shim.py`）
       + **3 相机 224²** ⇒ 给 **ctrl-steps/s**，五元标注齐全 + `loadavg`/`nr_throttled` 成对；
  E3-4 GPU 渲染下的**并行度重标定 1/2/4/8**（`parallel_eval_workers_cap=4` 是 CPU 渲染口径）
       + **"训练并发占同一张卡时"的吞吐与显存**（本轮用占位共租 `proxy_a2`，真 A2 并发需 D 排窗）。

三条刻意的口径纪律（都是本仓已踩过的坑）：
1. **环境注入只用 `scripts/e_activate_gpu_render.sh --print`**（eval 后取 `env -0`）⇒ 激活件是**唯一真源**，
   本脚本不另写一份 LD_LIBRARY_PATH/ICD 逻辑（裁定 46.4 的根因就是"两处定义漂移"）。
2. **`env.step()` 里的 3 次 480×640 渲染是 `gym_aloha/tasks/sim.py:92-94` 硬编码的**，改它要动 site-packages
   （禁止）⇒ 所以把成本**拆成可归因的五个分量**分别测，而不是只报一个"快了多少"的总数：
     `physics_only` / `render_3cam_224`（π₀.₅ 输入口径）/ `render_native_3cam_480x640`（env 内建）
     / `env_step_native`（主线现状）/ `env_step_plus_3cam_224`（内建 + 自采 224²）。
3. **图像语义跨后端可比、吞吐数字不可比**：每个分量都带同 seed/同动作序列下的 `image_mean/std`，
   用来证明"换后端不改变图像语义"（D 已在 480×640 单帧上验过 39.892→39.869）。

用法：
  python scripts/e_mainline_render_calib.py --backends egl_nvidia,osmesa --workers 1,2,4,8 --steps 30
  python scripts/e_mainline_render_calib.py --backends egl_nvidia --workers 1,4 --cotenant proxy_a2
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import e_gpu_egl_verify as ev  # noqa: E402  复用采样/fd 归因，不重复实现
import e_egl_probe as ep       # noqa: E402  复用边界闸（§3.2）

ACTIVATE = REPO_ROOT / "scripts" / "e_activate_gpu_render.sh"
SHIM = REPO_ROOT / "envs" / "gym_aloha_shim.py"
OUT_DIR = REPO_ROOT / "runs" / "infra" / "e_mainline_calib_20260929"
PY = "/root/venvs/pi05_sim/bin/python"      # gym_aloha 只装在这个 venv（mujoco 3.8.1，与 A2 基线同）
CAMS_224 = ["angle", "left_wrist", "right_wrist"]          # A2 `render_throughput_a2.json` 的同一组
CAMS_NATIVE = ["top", "angle", "front_close"]              # gym_aloha/tasks/sim.py:92-94 硬编码
NATIVE_HW = (480, 640)
PER_STEP_BUDGET_MS = 34.0                                   # 裁定 53-2 的硬预算
# 渲染保真闸的容差。**为什么不是"sha 逐字相同"**：实测 GPU(egl/NVIDIA) 臂上 `left_wrist`/
# `right_wrist` 在同一物理状态下重复渲染**不是逐位确定的**（±1 LSB、5–21 个像素/15 万），
# 而 `angle` 与整个 osmesa 臂是逐位确定的（见 RENDER_DETERMINISM.json）。用 sha 严格相等会
# **误杀干净的 GPU 批** ⇒ 改成数值容差闸：允许 LSB 抖动，但抓住"内容变成垃圾"。
FID_MAX_ABS_DIFF = 4          # 单像素最大绝对差（实测干净臂：angle=0、wrist≤1）
FID_MAX_FRAC_DIFF = 0.02      # 有差异的像素占比上限（实测干净臂 ≤0.00042）
FID_MAX_MEAN_DIFF = 0.05      # 全图平均绝对差上限（实测干净臂 ≤0.00042）
FID_MIN_PAIRWISE_DIFF = 0.05  # 三相机两两之间至少 5% 像素不同（防"三相机趋同"）
                              # 阈值按实测标定，不是拍的：干净臂最小两两差 = 0.3587
                              # （`left_wrist` vs `right_wrist`，两腕相机视角本就相近），
                              # 污染臂 = 0.0018 ⇒ 0.05 可干净分离（见 RAW_PROBE_INTERFERENCE.json）

_CHILD = r'''
import importlib.util, json, os, re, sys, time
import numpy as np

REPO = sys.argv[1]; STEPS = int(sys.argv[2]); SEED = int(sys.argv[3]); TAG = sys.argv[4]

def gl_strings():
    try:
        from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString
        return [s.decode() if isinstance(s, bytes) else str(s)
                for s in (glGetString(GL_VENDOR), glGetString(GL_RENDERER), glGetString(GL_VERSION)) if s]
    except Exception as exc:
        return [f"(unavailable: {type(exc).__name__})"]

def nvidia_fds():
    out = []
    for fd in os.listdir("/proc/self/fd"):
        try: t = os.readlink(f"/proc/self/fd/" + fd)
        except OSError: continue
        if "/dev/nvidia" in t: out.append(t)
    return sorted(set(out))

def loaded_gl_libs():
    hits = {}
    for m in re.finditer(r"/\S*/(lib[A-Za-z0-9_.+-]*\.so[0-9.]*)", open("/proc/self/maps", errors="ignore").read()):
        n = m.group(1)
        if any(k in n for k in ("nvidia", "EGL", "GLX", "OSMesa", "swrast", "gallium")):
            hits[n] = hits.get(n, 0) + 1
    return hits

out = {"tag": TAG, "pid": os.getpid(), "mujoco_gl": os.environ.get("MUJOCO_GL"),
       "vendor_icd": os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES"),
       "ld_library_path": os.environ.get("LD_LIBRARY_PATH"), "steps": STEPS, "seed": SEED}
try:
    spec = importlib.util.spec_from_file_location("gym_aloha_shim", os.path.join(REPO, "envs", "gym_aloha_shim.py"))
    shim = importlib.util.module_from_spec(spec); spec.loader.exec_module(shim)
    import mujoco, gymnasium as gym, gym_aloha  # noqa: F401
    out["mujoco_version"] = mujoco.__version__
    out["shim"] = {"representation_version": shim.REPRESENTATION_VERSION,
                   "shim_sha256_12": shim.shim_sha256_12(), "mainline_dt": shim.MAINLINE_DT,
                   "per_step_budget_ms": shim.PER_STEP_BUDGET_MS}
    env, rec = shim.make_env(shim.ENV_ID, dt=shim.MAINLINE_DT,
                             obs_type="pixels_agent_pos", render_mode="rgb_array")
    out["shim"]["apply_record"] = {k: rec.get(k) for k in
        ("applied", "both_names_patched", "requested_hz", "in_qc_band_29_31",
         "n_sub_steps_from_dm_control", "site_packages_modified")}
    out["live_timing"] = shim.read_live_timing(env)
    inner = env.unwrapped; physics = inner._env.physics
    model = physics.model
    import gym_aloha.constants as GC
    xml_path = GC.ASSETS_DIR / "bimanual_viperx_transfer_cube.xml"
    import hashlib
    out["model"] = {"xml": str(xml_path),
                    "xml_sha256_12": hashlib.sha256(xml_path.read_bytes()).hexdigest()[:12],
                    "nq": int(model.nq), "nv": int(model.nv), "nu": int(model.nu),
                    "ncam": int(model.ncam), "nmesh": int(model.nmesh),
                    "nmeshvert": int(model.nmeshvert), "nmeshface": int(model.nmeshface),
                    "ngeom": int(model.ngeom), "physics_timestep": float(model.opt.timestep)}
    # `physics.model` 在本 venv 是 **dm_control 的包装类**（不是 `mujoco.MjModel`）⇒ `mj_id2name` 直接 TypeError。
    # 与 A2 shim 里 `_deref` 同族教训（裁定 53.3）：连**读法**都不能跨 venv/跨包装层搬。
    try:
        cam_names = [model.camera(i).name for i in range(model.ncam)]
    except Exception as exc:
        cam_names = [f"(unreadable: {type(exc).__name__}: {exc})"]
    out["model"]["camera_names"] = cam_names
    out["model"]["model_wrapper_type"] = type(model).__module__ + "." + type(model).__name__
    out["n_sub_steps"] = int(out["live_timing"].get("n_sub_steps") or shim.MAINLINE_SUBSTEPS)

    obs, _ = env.reset(seed=SEED)
    rng = np.random.default_rng(SEED)
    actions = rng.uniform(-1.0, 1.0, size=(STEPS, env.action_space.shape[0])).astype(np.float32)

    def img_stats(arr):
        a = np.asarray(arr)
        return {"shape": list(a.shape), "mean": round(float(a.mean()), 3),
                "std": round(float(a.std()), 4), "raw_len": int(a.size * a.itemsize),
                "sha12": hashlib.sha256(a.tobytes()).hexdigest()[:12]}

    # 同状态下的图像语义（跨后端可比）：reset 之后、步进之前
    out["images_at_reset"] = {}
    ref_imgs = {}
    for c in CAMS_224:
        ref_imgs[c] = np.asarray(physics.render(height=224, width=224, camera_id=c))
        out["images_at_reset"][c] = img_stats(ref_imgs[c])
    for c in CAMS_NATIVE:
        out["images_at_reset"][c + "@480x640"] = img_stats(
            physics.render(height=NATIVE_HW[0], width=NATIVE_HW[1], camera_id=c))
    out["gl_strings"] = gl_strings()
    # ⚠️ 这里**故意不再**建裸 `mujoco.Renderer` 取 glGetString。
    # 起因（22:5x 实测，见 runs/infra/e_mainline_calib_20260929/RAW_PROBE_INTERFERENCE.json）：
    # 同进程内"先 dm_control 渲染、再建/关裸 mujoco.Renderer"会让后续所有 `physics.render`
    # 返回**冻结的旧缓冲**（场景变了 sha12 不变、三相机趋同），且渲染吞吐**虚高 ~30%** ⇒
    # 既污染图像语义、又污染吞吐数字。后端身份改由**父进程另起独立子进程**取（`gl_identity_probe`）。
    out["gl_probe_note"] = ("gl_strings = dm_control 渲染后主线程取值（osmesa 臂恒为空，属**读法**差异不是后端差异）；"
                            "后端标签以 batch['gl_identity_probe']['gl_strings'] 为准（独立子进程实证，"
                            "**不在被测 env 同进程里建裸 mujoco.Renderer**，避免冻结缓冲污染）")

    # ---- 渲染活性闸（render liveness）----
    # 判据：渲一张 224² → 走物理若干步 → 再渲同一相机同一分辨率，`sha12` **必须变**。
    # 变了才说明 `physics.render` 真的在跟着场景出图；不变 = 拿到冻结缓冲（吞吐数字一律不可信）。
    def render_liveness(tag):
        import hashlib as _hl
        cam = CAMS_224[0]
        nsteps = max(2, int(out["n_sub_steps"]) * 2)
        a0 = np.asarray(physics.render(height=224, width=224, camera_id=cam))
        s0 = _hl.sha256(a0.tobytes()).hexdigest()[:12]
        for _ in range(nsteps):
            physics.step()
        a1 = np.asarray(physics.render(height=224, width=224, camera_id=cam))
        s1 = _hl.sha256(a1.tobytes()).hexdigest()[:12]
        return {"tag": tag, "camera": cam, "resolution": [224, 224], "n_physics_steps": nsteps,
                "sha12_before": s0, "sha12_after": s1,
                "mean_before": round(float(a0.mean()), 3), "mean_after": round(float(a1.mean()), 3),
                "changed": bool(s0 != s1)}
    out["render_liveness_pre"] = render_liveness("pre_warmup")

    # 预热：每个分量各跑 3 步，排除首帧上下文/着色器编译开销
    for _ in range(3):
        physics.render(height=224, width=224, camera_id=CAMS_224[0])
        physics.render(height=NATIVE_HW[0], width=NATIVE_HW[1], camera_id=CAMS_NATIVE[0])
    env.reset(seed=SEED)

    comps = {}
    def timeit(name, fn, n_ctrl_steps, n_images_per_step):
        t0 = time.perf_counter(); fn(); dt = time.perf_counter() - t0
        comps[name] = {"ctrl_steps": n_ctrl_steps, "wall_s": round(dt, 4),
                       "ctrl_steps_per_s": round(n_ctrl_steps / dt, 2),
                       "ms_per_ctrl_step": round(1000 * dt / n_ctrl_steps, 3),
                       "images_per_s": round(n_ctrl_steps * n_images_per_step / dt, 2),
                       "within_budget_34ms": bool(1000 * dt / n_ctrl_steps <= PER_STEP_BUDGET_MS)}

    n_sub = out["n_sub_steps"]
    def physics_only():
        for _ in range(STEPS):
            for _ in range(n_sub):
                physics.step()
    def render_3cam_224():
        for _ in range(STEPS):
            for c in CAMS_224:
                physics.render(height=224, width=224, camera_id=c)
    def render_native():
        for _ in range(STEPS):
            for c in CAMS_NATIVE:
                physics.render(height=NATIVE_HW[0], width=NATIVE_HW[1], camera_id=c)
    def step_seq(extra_render):
        env.reset(seed=SEED)
        for i in range(STEPS):
            _, _, term, trunc, _ = env.step(actions[i])
            if extra_render:
                for c in CAMS_224:
                    physics.render(height=224, width=224, camera_id=c)
            if term or trunc:
                env.reset(seed=SEED)

    timeit("physics_only", physics_only, STEPS, 0)
    timeit("render_3cam_224", render_3cam_224, STEPS, 3)
    timeit("render_native_3cam_480x640", render_native, STEPS, 3)
    timeit("env_step_native", lambda: step_seq(False), STEPS, 3)
    timeit("env_step_plus_3cam_224", lambda: step_seq(True), STEPS, 6)
    out["components"] = comps

    env.reset(seed=SEED)
    for i in range(STEPS):
        _, _, term, trunc, _ = env.step(actions[i])
        if term or trunc:
            env.reset(seed=SEED)
    out["images_after_steps"] = {c: img_stats(physics.render(height=224, width=224, camera_id=c))
                                 for c in CAMS_224}
    out["render_liveness_post"] = render_liveness("post_components")
    out["render_liveness_ok"] = bool(out["render_liveness_pre"]["changed"]
                                     and out["render_liveness_post"]["changed"])

    # ---- 渲染保真闸（render fidelity）----
    # 活性闸只能抓"完全冻结"：`raw_after` 那种污染下渲染**仍在逐帧变化**（liveness=true），
    # 但内容已是垃圾（`angle` 均值 36.2 → 0.88、三相机趋同）⇒ 光靠活性闸抓不住。
    # 所以再加一条**回到同一 reset 态必须复现同一张图**的闸：同 seed reset 后重拍 3 相机，
    # sha12 必须与开跑前的 `images_at_reset` 逐字相同，且三相机互不相同、非退化（std ≥ 1）。
    env.reset(seed=SEED)
    recheck_imgs = {}
    out["images_at_reset_recheck"] = {}
    for c in CAMS_224:
        recheck_imgs[c] = np.asarray(physics.render(height=224, width=224, camera_id=c))
        out["images_at_reset_recheck"][c] = img_stats(recheck_imgs[c])
    per_cam = {}
    for c in CAMS_224:
        dd = np.abs(recheck_imgs[c].astype(np.int16) - ref_imgs[c].astype(np.int16))
        per_cam[c] = {"max_abs_diff": int(dd.max()),
                      "mean_abs_diff": round(float(dd.mean()), 5),
                      "frac_diff_px": round(float((dd.sum(axis=2) > 0).mean()), 6),
                      "sha_same": bool(out["images_at_reset_recheck"][c]["sha12"]
                                       == out["images_at_reset"][c]["sha12"]),
                      "mean_before": out["images_at_reset"][c]["mean"],
                      "mean_recheck": out["images_at_reset_recheck"][c]["mean"],
                      "std_recheck": out["images_at_reset_recheck"][c]["std"]}
    pairwise = {}
    for _i in range(len(CAMS_224)):
        for _j in range(_i + 1, len(CAMS_224)):
            _a, _b = CAMS_224[_i], CAMS_224[_j]
            _d = np.abs(recheck_imgs[_a].astype(np.int16) - recheck_imgs[_b].astype(np.int16))
            pairwise[f"{_a}__vs__{_b}"] = round(float((_d.sum(axis=2) > 0).mean()), 4)
    reproducible = all(v["max_abs_diff"] <= FID_MAX_ABS_DIFF
                       and v["frac_diff_px"] <= FID_MAX_FRAC_DIFF
                       and v["mean_abs_diff"] <= FID_MAX_MEAN_DIFF for v in per_cam.values())
    distinct = bool(pairwise) and all(x >= FID_MIN_PAIRWISE_DIFF for x in pairwise.values())
    non_degenerate = all(v["std_recheck"] >= 1.0 for v in per_cam.values())
    out["render_fidelity"] = {
        "reset_reproducible_within_tolerance": bool(reproducible),
        "cams_mutually_distinct": bool(distinct),
        "cams_non_degenerate": bool(non_degenerate),
        "tolerance": {"max_abs_diff": FID_MAX_ABS_DIFF, "max_frac_diff_px": FID_MAX_FRAC_DIFF,
                      "max_mean_abs_diff": FID_MAX_MEAN_DIFF,
                      "min_pairwise_frac_diff_px": FID_MIN_PAIRWISE_DIFF},
        "per_cam_vs_reset_reference": per_cam,
        "pairwise_cam_frac_diff_px": pairwise,
        "why_not_exact_sha": ("GPU 臂 wrist 相机同状态重渲有 ±1 LSB 抖动（非逐位确定），"
                             "sha 严格相等会误杀干净批 ⇒ 用数值容差；osmesa 臂与 GPU 的 angle "
                             "相机则逐位确定（sha_same=true）"),
    }
    out["render_fidelity_ok"] = bool(reproducible and distinct and non_degenerate)
    # 两道闸都过才算"渲染健康"：liveness 抓冻结、fidelity 抓"在动但动错了"
    out["render_health_ok"] = bool(out["render_liveness_ok"] and out["render_fidelity_ok"])
    out["loaded_gl_libs"] = loaded_gl_libs()
    out["child_nvidia_fds"] = nvidia_fds()
    out["ok"] = True
except Exception as exc:
    import traceback
    out["ok"] = False
    out["error"] = f"{type(exc).__name__}: {exc}"
    out["traceback_tail"] = traceback.format_exc().strip().splitlines()[-8:]
    out.setdefault("gl_strings", gl_strings())
print("RESULT_JSON" + json.dumps(out))
'''

_CHILD_HEADER = f'''
CAMS_224 = {CAMS_224!r}
CAMS_NATIVE = {CAMS_NATIVE!r}
NATIVE_HW = {NATIVE_HW!r}
PER_STEP_BUDGET_MS = {PER_STEP_BUDGET_MS!r}
FID_MAX_ABS_DIFF = {FID_MAX_ABS_DIFF!r}
FID_MAX_FRAC_DIFF = {FID_MAX_FRAC_DIFF!r}
FID_MAX_MEAN_DIFF = {FID_MAX_MEAN_DIFF!r}
FID_MIN_PAIRWISE_DIFF = {FID_MIN_PAIRWISE_DIFF!r}
'''

# 占位共租：仿 A2 训练对同一张卡的显存/SM 占用（**不是** A2 训练本身，产物必须标 proxy）
_COTENANT = r'''
import os, sys, time
import torch
gib = float(sys.argv[1]); seconds = float(sys.argv[2])
dev = torch.device("cuda:0")
torch.cuda.init()
ballast = torch.empty(int(gib * (1024 ** 3) / 4), dtype=torch.float32, device=dev)
ballast[0] = 1.0
a = torch.randn(4096, 4096, device=dev, dtype=torch.float16)
b = torch.randn(4096, 4096, device=dev, dtype=torch.float16)
t0 = time.time(); iters = 0
while time.time() - t0 < seconds:
    c = a @ b
    iters += 1
    if iters % 50 == 0:
        torch.cuda.synchronize()
print("COTENANT_DONE", iters, round(time.time() - t0, 2), round(float(ballast.numel() * 4 / 1024**3), 2))
'''


def activation_env(mode: str) -> tuple[dict, str]:
    """从激活件取环境（唯一真源）。返回 (env, 原文 export 文本)。"""
    printed = subprocess.run(["bash", str(ACTIVATE), "--print", "--mode", mode],
                             capture_output=True, text=True, timeout=60)
    if printed.returncode != 0:
        raise RuntimeError(f"激活件 --print 失败({mode}): {printed.stderr.strip()[:300]}")
    resolved = subprocess.run(["bash", "-c",
                               f'eval "$(bash {ACTIVATE} --print --mode {mode})"; env -0'],
                              capture_output=True, text=True, timeout=60)
    env = {}
    for pair in resolved.stdout.split("\0"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            env[k] = v
    return env, printed.stdout


def gpu_snapshot() -> dict:
    return ev.nvidia_smi_sample()


def other_compute_procs(my_pids: set[int]) -> list[str]:
    snap = gpu_snapshot()
    return [p for p in (snap.get("compute_procs") or [])
            if p.split(",")[0].strip() and int(p.split(",")[0].strip()) not in my_pids]


# ── 「卡上有没有别人」的**三网并查**（23:58 抢卡事故的根因修复）─────────────────
# 事故：A2 的 `a2_egl_latency_remeasure.py --mode closed_loop --tag quiet_window_rep1`
#   23:57:37 起跑，但 π₀.₅ 的 `from_pretrained` 要 60–185 s 才真正分配显存 ⇒
#   E 在 23:58:35 查 `nvidia-smi --query-compute-apps` 看到「卡空」，于是起了 13.8 GB 假体，
#   正压进 A2 在 daily_report §9 申报的静默窗口（A2 自己的闸判 `contaminated=True`，
#   证据 `runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep1.json`
#   → `cotenant_evidence.non_self_gpu_procs_observed` = PID 156355 / 14714 MiB × 20 采样）。
# 根因：**`compute-apps` 只列已分配显存的进程**，对「正在加载模型的他线进程」是盲的。
# 修法：三网并查，任一命中即视为「卡忙」，E 让路（GPU 优先权 A2 > C2 > E）。
# 注意锚点：真实 cmdline 是 `... /bin/python scripts/a2_xxx.py --mode ...`，`scripts/` 前面是**空格**。
# 早先写的 `(?:^|/)` 要求行首或斜杠 ⇒ **宽档网永远不会命中**（自测时才发现，已修）。
# 用「前面不是单词字符」的负向后顾，既能吃到空格/引号/等号，又不会误吃 `myscripts/`。
OTHER_LINE_SCRIPT_RE = re.compile(r"(?<!\w)scripts/(a2?|b2?|c2?|d)_")
GPU_INTENT_PATTERNS = (
    "a2_egl_latency_remeasure", "a2_pi05_zeroshot_eval", "a2_s4a_vla_runtime_verify",
    "vla_runtime", "torchrun", "accelerate", "deepspeed", "lerobot-train",
    "--expect-renderer", "--mode closed_loop", "quiet_window",
)

# ── 裁定 96.1-③（同族缺陷：网在匹配「关于 GPU 的**文本**」，不是「GPU **占用**」）──────────
# F 的只读探针实测两起文本误触发（`runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json`
# = 74 ln `59fca05a6f68`）：宽档命中 PID **214244**，其 cmdline 是
# `/bin/bash -c cd … && python3 - <<'PY' … pathlib.Path("scripts/a2_s4b_outcome_ledger_verify.py") …`
# —— 那是在**改文件**（纯 CPU），不是在上卡。后果具体：A2 按裁定 94.9-1② 要在**起跑那一刻**
# 实测三网，若此刻别线正在读/写这些字面量 ⇒ A2 的窗口被判 `contaminated`（D 明示不认该窗口的
# 数字）或被起跑前拒绝逻辑挡下（`exit 3`）⇒ **白跑一轮上卡**，而裁定 95.2 的六步序列第 1–3 步
# 全部要上卡。与 B2 自报的 RR-B2-18 同族同因（那条归 B2、同批修）。
# 修法（D 已裁 · E 主责 · 纯 CPU · 不需窗口）：**真实执行形态 ∧ 关键字**，不是裸关键字；并排除
# `pcpu≈0` 的闲置进程；**两向都装对照探针**（裁定 93.8 / 缺陷类 ⑲，只装一向不许报绿）。
# `EXEC_FORM_RE` 逐字复用 F 的 `scripts/f_probe_card_busy.py`（as_of 12:3x = 207 ln `0c0034426d31`；
# 引用活件的身份串一律带 `as_of`，缺陷类 ㉒）——「读别人的工具、写自己的文件」，不另造口径；
# F 已实测它能把上述两类分开。本件每次跑探针都会**现取**该件身份落进产物
# （`CARD_BUSY_FIX_VERDICT.json` 的 `fix_summary.exec_form_re_reused_from`），故注释里的值只作锚点。
EXEC_FORM_RE = re.compile(r"(?:^|\s)(?:\S*python\S*|\S*/bin/\S+)\s+\S*scripts/(?:a2?|b2?|c2?|d|e|f)_\S+")
# 反漏检腿：argv0 **本身就是** GPU 启动器时，即使后面没有 `scripts/<line>_*.py` 也算真实执行形态
# （旧口径靠裸关键字 `torchrun` 命中这类；只收紧成"必须带线内脚本路径"会把它漏掉 ⇒ 显式补回）。
GPU_LAUNCHER_ARGV0 = ("torchrun", "accelerate", "deepspeed", "lerobot-train")
GPU_LAUNCHER_MODULES = ("torch.distributed.run", "torch.distributed.launch", "accelerate.commands.launch")
# 闲置判据的定标（实测见 `runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json` 的
# `idle_threshold_calibration`）：累计 CPU tick ≤ 1（=10 ms @ `SC_CLK_TCK`=100）且状态属 {S,T,Z}
# ⇒ 该进程自启动以来几乎没执行过指令。**刚 fork 出来的真跑不会被误排**（python 解释器启动自身
# 就 > 1 tick；探针实测这个裕度并断言它）；卡在 NFS I/O 的 `D` 态**不**排除 —— 那正是
# 「已起跑、尚未分配显存」的盲区（23:58 事故），此处宁可过判不可漏判。
IDLE_CPU_TICKS = 1
IDLE_PROC_STATES = ("S", "T", "Z")


def _cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
    except OSError:
        return ""
    return " ".join(raw.split())[:400]


def _argv(pid: int) -> list[str]:
    """`/proc/<pid>/cmdline` 的**原始 argv 列表**（不拼接、不按 400 字符截断）。

    `_cmdline()` 是给产物记录用的（拼接 + 截断）；而「关键字出现在**执行位**还是**文本位**」
    必须按 argv 边界判（裁定 96.1-③），所以另取一份列表。
    """
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [a.decode(errors="ignore") for a in raw.split(b"\0") if a][:64]


def _proc_cpu(pid: int) -> tuple[int, str]:
    """`(累计 utime+stime tick, 进程状态单字母)`；取不到 ⇒ `(-1, "")` = **不**判闲置。"""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(errors="ignore")
    except OSError:
        return -1, ""
    tail = stat.rsplit(")", 1)[-1].split()
    try:
        return int(tail[11]) + int(tail[12]), tail[0]
    except (IndexError, ValueError):
        return -1, ""


def classify_cmdline(argv: list[str], *, cpu_ticks: int = -1, proc_state: str = "") -> dict:
    """把一个进程的 argv 分成 `real_gpu_work` / `text_mention_only` / `idle_text_mention`。

    **纯函数**（不读 `/proc`、不起进程、不碰 GPU）⇒ 既能被对照探针两向注入（裁定 93.8），
    也能拿「历史上真实出现过的 cmdline」重放（F 的实测两起 + 23:58 抢卡事故 + A2 的延迟臂形态）。
    判据 = 裁定 96.1-③：**真实执行形态 ∧ 关键字 ∧ 非闲置**（不是裸关键字）。
    """
    joined = " ".join(argv)[:4000]
    intent = [f"gpu_intent:{pat}" for pat in GPU_INTENT_PATTERNS if pat in joined]
    broad = ["other_line_script"] if OTHER_LINE_SCRIPT_RE.search(joined) else []
    argv0 = argv[0] if argv else ""
    base0 = argv0.rsplit("/", 1)[-1]
    kind = None
    if EXEC_FORM_RE.search(joined):
        kind = "interpreter_plus_line_script"
    elif base0 in GPU_LAUNCHER_ARGV0:
        kind = "gpu_launcher_in_argv0"
    elif base0.startswith("python") and len(argv) > 2 and argv[1] == "-m" \
            and argv[2] in GPU_LAUNCHER_MODULES:
        kind = "gpu_launcher_module"
    ticks_known = cpu_ticks >= 0
    idle = bool(ticks_known and cpu_ticks <= IDLE_CPU_TICKS and proc_state in IDLE_PROC_STATES)
    matched = bool(intent or broad)
    counted = bool(matched and kind is not None and not idle)
    if not matched:
        classification = "no_keyword"
    elif kind is None:
        classification = "text_mention_only"
    elif idle:
        classification = "idle_text_mention"
    else:
        classification = "real_gpu_work"
    return {"argv0": argv0, "exec_form": kind is not None, "exec_form_kind": kind,
            "gpu_intent_matched": intent[:4], "other_line_script_matched": broad,
            "cpu_ticks": cpu_ticks, "cpu_ticks_known": ticks_known, "proc_state": proc_state,
            "idle": idle, "counted_toward_busy": counted, "classification": classification,
            # 分档的"是否计入"：窄档看关键字、宽档看他线脚本，两档共用同一个执行形态/非闲置门槛
            # （裁定 96.1-③「宽档同理」）。消费方（`card_busy()`）据此决定 `busy`。
            "counted_narrow": bool(counted and intent), "counted_broad": bool(counted and broad),
            "cmdline_head": " ".join(joined.split())[:200],
            "caliber": "裁定 96.1-③：真实执行形态 ∧ 关键字 ∧ 非闲置（裸关键字提及不计入 busy）"}


def _own_tree() -> set[int]:
    """E 自己的进程（本进程 + 祖先），避免把自己的 worker/假体当成「别人」。"""
    pids = {os.getpid()}
    pid = os.getpid()
    for _ in range(8):
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(errors="ignore")
            ppid = int(stat.rsplit(")", 1)[-1].split()[1])
        except (OSError, IndexError, ValueError):
            break
        if ppid <= 1 or ppid in pids:
            break
        pids.add(ppid)
        pid = ppid
    return pids


def nvidia_fd_holders(exclude_pids: set[int]) -> list[dict]:
    """扫全部可见进程的 `/proc/*/fd`，找**已持有 `/dev/nvidia*` 的进程**。

    比 `compute-apps` 早一步：进程 `torch.cuda.init()` / 打开设备后就会持有 fd，
    而 `nvidia-smi` 要等它**分配了显存**才列出来。这正是 23:58 事故的盲区。
    """
    hits = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return hits
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in exclude_pids:
            continue
        try:
            fds = os.listdir(f"/proc/{pid}/fd")
        except OSError:
            continue
        devs = set()
        for fd in fds:
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            if target.startswith("/dev/nvidia"):
                devs.add(target)
        if devs:
            hits.append({"pid": pid, "nvidia_devs": sorted(devs), "cmdline": _cmdline(pid)})
    return hits


def other_line_gpu_intent(exclude_pids: set[int]) -> list[dict]:
    """扫 cmdline，**分两档**返回（判据 = 裁定 96.1-③：**真实执行形态 ∧ 关键字 ∧ 非闲置**）：

    - `gpu_intent`（窄档）：明确的 GPU 入口/关键字（`a2_egl_latency_remeasure`、`torchrun`、
      `--mode closed_loop`、`quiet_window` …）**且**该进程确实是以解释器/启动器形态在跑一条
      线内脚本 ⇒ 该进程**很可能要上卡**，即使此刻还没分配显存。**批级闸用这一档**：E 的渲染批
      只占 ~102 MiB / ~3 s，不必因为别人在跑纯 CPU 脚本就让路，但对"正要上卡的人"必须让路。
    - `other_line_script`（宽档）：**任何**他线脚本（`scripts/{a,a2,b,b2,c,c2,d}_*`），过同一个
      执行形态 / 非闲置门槛 ⇒ 只用于**起假体**这种"按设计就占卡 13.8 GB + 100% util"的动作
      （`strict=True`）。
    - **不再计入 busy 的**（旧口径会计入 ⇒ 就是 F 实测的那两起假阳性）：关键字只出现在**文本位**
      （`grep`、`bash -c` 里的 heredoc、`python3 - <<PY` 里读写这些脚本）· 以及累计 CPU ≤ 1 tick
      的闲置进程。它们**仍原样登记**在 `*_matched` / `classification` / `counted_toward_busy`
      里，供消费方审计「为什么这一刻没判忙」（`card_busy()` 的 `cmdline_hits_text_mention_only`）。
    """
    hits = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return hits
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in exclude_pids:
            continue
        argv = _argv(pid)
        if not argv:
            continue
        ticks, state = _proc_cpu(pid)
        cls = classify_cmdline(argv, cpu_ticks=ticks, proc_state=state)
        if not (cls["gpu_intent_matched"] or cls["other_line_script_matched"]):
            continue
        counted = cls["counted_toward_busy"]
        hits.append({"pid": pid,
                     # `gpu_intent` / `other_line_script` = **计入 busy 的**命中。键名与"非空即计入"
                     # 的读法对消费方不变（`card_busy()` 的窄档过滤、A2 的
                     # `a2_egl_latency_remeasure.py`、`e_selfcheck_gate_mutation.py` 都读这两个键）；
                     # 未计入的原始匹配另存 `*_matched` ⇒ 两者分叉即"这是一次文本提及"。
                     "gpu_intent": cls["gpu_intent_matched"] if counted else [],
                     "other_line_script": cls["other_line_script_matched"] if counted else [],
                     "gpu_intent_matched": cls["gpu_intent_matched"],
                     "other_line_script_matched": cls["other_line_script_matched"],
                     "exec_form": cls["exec_form"], "exec_form_kind": cls["exec_form_kind"],
                     "cpu_ticks": cls["cpu_ticks"], "proc_state": cls["proc_state"],
                     "idle": cls["idle"], "classification": cls["classification"],
                     "counted_toward_busy": counted,
                     "cmdline": _cmdline(pid)})
    return hits


def card_busy(exclude_pids: set[int] | None = None, strict: bool = False) -> dict:
    """三网并查：`compute-apps` + `/dev/nvidia*` fd 持有者 + cmdline 网。

    `strict=False`（批级闸）：cmdline 网只算**窄档** `gpu_intent`。
    `strict=True`（起假体前）：cmdline 网把**宽档** `other_line_script` 也算上 —— 假体按设计
    就是占卡 13.8 GB + 100% util，而 E 的 GPU 优先权最低，只要有他线在跑就不该起。

    **cmdline 网口径（裁定 96.1-③，2026-09-30 收紧）**：只有**真实执行形态**（解释器 +
    `scripts/<line>_*.py`，或 argv0 本身是 GPU 启动器 / `-m` 分布式启动器）**且非闲置**的进程
    才计入 busy；只在文本里提到关键字的纯 CPU 进程（`grep`、heredoc、改文件）不再计入 ⇒
    修掉的是**假阳性**（别线在读这些字面量的那一刻，A2 的窗口被误判 `contaminated` 或被
    起跑前拒绝逻辑挡下）。网①②（`compute-apps` / fd）源码**一字未改** —— 它们是实测占用，
    不受文本影响（机器比对的证据见 `CARD_BUSY_FIX_VERDICT.json` 的 `nets_untouched`）。
    """
    excl = set(exclude_pids or set()) | _own_tree()
    compute = [p for p in gpu_snapshot().get("compute_procs") or []
               if p.split(",")[0].strip() and int(p.split(",")[0].strip()) not in excl]
    fd_holders = nvidia_fd_holders(excl)
    intent = other_line_gpu_intent(excl)
    cmd_hits = ([h for h in intent if h["counted_toward_busy"]] if strict
                else [h for h in intent if h["gpu_intent"]])
    return {
        "busy": bool(compute or fd_holders or cmd_hits),
        "strict": strict,
        "compute_procs": compute,
        "nvidia_fd_holders": fd_holders,
        "cmdline_hits": cmd_hits,
        "cmdline_hits_all_other_line": intent,
        "cmdline_hits_text_mention_only": [h for h in intent if not h["counted_toward_busy"]],
        "excluded_own_pids": sorted(excl),
        "cmdline_net_caliber": (
            f"裁定 96.1-③：真实执行形态（`EXEC_FORM_RE` 复用 F 的探针，或 argv0 ∈ "
            f"{list(GPU_LAUNCHER_ARGV0)}，或 `python -m` ∈ {list(GPU_LAUNCHER_MODULES)}）"
            f"∧ 关键字 ∧ 非闲置（累计 CPU ≤ {IDLE_CPU_TICKS} tick 且状态 ∈ "
            f"{list(IDLE_PROC_STATES)} ⇒ 排除）；裸关键字提及不计入 busy，只登记"),
        "detection_note": ("三网并查；`compute-apps` 对「已起跑但尚未分配显存」的进程是盲的，"
                           "fd 网与 cmdline 网补这个盲区（23:58 抢卡事故的根因）。"
                           "strict=True 时 cmdline 网含宽档（任何他线脚本）。"
                           "裁定 96.1-③ 起 cmdline 网要求「真实执行形态 ∧ 关键字 ∧ 非闲置」，"
                           "纯文本提及登记在 `cmdline_hits_text_mention_only` 而**不**计入 busy"),
    }


# 批级 GL 身份探针：**独立子进程**里建裸 mujoco 模型渲一帧，只为取 `glGetString` 三值。
# 为什么必须独立进程：dm_control 把渲染放在独立渲染线程里 make current，主线程 `glGetString`
# 在 osmesa 臂恒为空；而在**被测 env 同进程**里补一次裸 `mujoco.Renderer` 又会把后续
# `physics.render` 变成冻结缓冲（吞吐虚高 ~30%）。两头都不能占 ⇒ 把身份探针搬到另一个进程，
# 与被测 env 彻底解耦（XML 与 `e_gpu_egl_verify._XML` 逐字一致：不另造模型 = 不另造口径）。
_GLID_PROBE = r'''
import hashlib, json, os, re, sys
import numpy as np
XML = sys.argv[1]
out = {"pid": os.getpid(), "mujoco_gl": os.environ.get("MUJOCO_GL"),
       "vendor_icd": os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES"),
       "ld_library_path": os.environ.get("LD_LIBRARY_PATH"),
       "xml_sha256_12": hashlib.sha256(XML.encode()).hexdigest()[:12]}
try:
    import mujoco
    out["mujoco_version"] = mujoco.__version__
    m = mujoco.MjModel.from_xml_string(XML)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    r = mujoco.Renderer(m, height=32, width=32)
    r.update_scene(d, camera="c")
    img = np.asarray(r.render())
    out["probe_image"] = {"shape": list(img.shape), "mean": round(float(img.mean()), 3),
                          "sha12": hashlib.sha256(img.tobytes()).hexdigest()[:12]}
    from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString
    out["gl_strings"] = [s.decode() if isinstance(s, bytes) else str(s)
                         for s in (glGetString(GL_VENDOR), glGetString(GL_RENDERER),
                                   glGetString(GL_VERSION)) if s]
    r.close()
    out["ok"] = True
except Exception as exc:
    out["ok"] = False
    out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    out["gl_strings"] = []
fds = []
for fd in os.listdir("/proc/self/fd"):
    try: t = os.readlink("/proc/self/fd/" + fd)
    except OSError: continue
    if "/dev/nvidia" in t: fds.append(t)
out["nvidia_fds"] = sorted(set(fds))
libs = {}
for mt in re.finditer(r"/\S*/(lib[A-Za-z0-9_.+-]*\.so[0-9.]*)",
                      open("/proc/self/maps", errors="ignore").read()):
    n = mt.group(1)
    if any(k in n for k in ("nvidia", "EGL", "GLX", "OSMesa", "swrast", "gallium")):
        libs[n] = libs.get(n, 0) + 1
out["loaded_gl_libs"] = libs
print("GLID" + json.dumps(out))
'''


def gl_identity_probe(mode: str, env: dict) -> dict:
    """在**与激活件同一套环境**下、另起子进程取 GL 身份三值 + fd + 已加载库。"""
    note = {"mode": mode, "python": PY, "isolated_from_env_under_test": True}
    try:
        p = subprocess.run([PY, "-c", _GLID_PROBE, ev._XML], capture_output=True, text=True,
                           env=env, timeout=300)
    except Exception as exc:
        return {**note, "ok": False, "error": f"{type(exc).__name__}: {exc}", "gl_strings": []}
    payload = None
    for line in p.stdout.splitlines():
        if line.startswith("GLID"):
            payload = json.loads(line[len("GLID"):])
    if payload is None:
        return {**note, "ok": False, "error": "no GLID line in probe stdout",
                "returncode": p.returncode,
                "stderr_tail": (p.stderr or "").strip().splitlines()[-6:], "gl_strings": []}
    return {**note, **payload}


def run_batch(mode: str, workers: int, steps: int, seed: int, cotenant: str | None,
              cotenant_proc: subprocess.Popen | None) -> dict:
    env, export_text = activation_env(mode)
    batch: dict = {
        "mode": mode, "workers": workers, "steps": steps, "seed": seed,
        "python": PY, "activation_artifact": str(ACTIVATE),
        "activation_exports": export_text.strip().splitlines(),
        "backend_env": {k: env.get(k) for k in ("MUJOCO_GL", "PYOPENGL_PLATFORM", "LD_LIBRARY_PATH",
                                                "__EGL_VENDOR_LIBRARY_FILENAMES", "VK_ICD_FILENAMES")},
        "boundary_guard_before": ep.boundary_guard(),
        "load_before": ev.cpu_stat(),
        "gpu_baseline": gpu_snapshot(),
        "cotenant": cotenant,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }
    if not batch["boundary_guard_before"]["ok"]:
        batch["verdict"] = "refused"
        batch["refuse_reason"] = "系统目录脏（§3.2 / 裁定 60）⇒ 拒跑"
        return batch

    # GL 身份在**起 worker 之前**、用独立子进程取一次（批级证据，不进被测进程）
    batch["gl_identity_probe"] = gl_identity_probe(mode, env)

    procs = []
    for w in range(workers):
        p = subprocess.Popen([PY, "-c", _CHILD_HEADER + _CHILD, str(REPO_ROOT), str(steps),
                              str(seed + w), f"w{w}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        procs.append(p)

    samples, fds_per_worker = [], {w: set() for w in range(workers)}
    t_batch = time.perf_counter()
    while any(p.poll() is None for p in procs):
        snap = gpu_snapshot()
        snap["t_offset_s"] = round(time.perf_counter() - t_batch, 2)
        samples.append(snap)
        for w, p in enumerate(procs):
            fds_per_worker[w].update(ev.child_nvidia_fds(p.pid))
        time.sleep(0.3)
    batch_wall = time.perf_counter() - t_batch

    results = []
    for p in procs:
        stdout, stderr = p.communicate(timeout=600)
        payload = None
        for line in stdout.splitlines():
            if line.startswith("RESULT_JSON"):
                payload = json.loads(line[len("RESULT_JSON"):])
        results.append(payload or {"ok": False, "returncode": p.returncode,
                                   "error": "no result",
                                   "stderr_tail": (stderr or stdout).strip().splitlines()[-8:]})
    for w, r in enumerate(results):
        r["worker_index"] = w
        r["child_nvidia_fds_observed_by_parent"] = sorted(fds_per_worker[w])

    batch["children"] = results
    batch["wall_s"] = round(batch_wall, 3)
    batch["all_ok"] = all(r.get("ok") for r in results)
    batch["gpu_samples"] = samples
    ok_s = [s for s in samples if "utilization_gpu" in s]
    batch["gpu_util_max"] = max((s["utilization_gpu"] for s in ok_s), default=0)
    batch["gpu_mem_used_max_mib"] = max((s["memory_used_mib"] for s in ok_s), default=0)
    batch["workers_with_nvidia_fd"] = sorted(w for w in fds_per_worker if fds_per_worker[w])
    procs_seen = sorted({pr for s_ in samples for pr in (s_.get("compute_procs") or [])})
    batch["cotenant_actual"] = {
        "compute_procs_observed_during_batch": procs_seen,
        "interpretation": ("空 = 本批独占卡；非空 = 卡上有别的 compute 进程（**渲染进程不计入 compute apps**，"
                           "所以这里的 PID 一定不是本批的渲染 worker）"),
    }
    batch["load_after"] = ev.cpu_stat()
    batch["boundary_guard_after"] = ep.boundary_guard()

    # 分量聚合：吞吐 = 各 worker ctrl_steps_per_s 之和；也记墙钟口径（总步数 / 批墙钟）
    agg = {}
    comp_names = ["physics_only", "render_3cam_224", "render_native_3cam_480x640",
                  "env_step_native", "env_step_plus_3cam_224"]
    for name in comp_names:
        per = [r["components"][name] for r in results if r.get("ok") and name in r.get("components", {})]
        if not per:
            continue
        rates = [p["ctrl_steps_per_s"] for p in per]
        agg[name] = {
            "n_workers_ok": len(per),
            "per_worker_ctrl_steps_per_s": rates,
            "aggregate_ctrl_steps_per_s": round(sum(rates), 2),
            "wall_based_incl_startup_ctrl_steps_per_s": round(len(per) * steps / batch_wall, 2),
            "median_ms_per_ctrl_step": round(statistics.median(p["ms_per_ctrl_step"] for p in per), 3),
            "median_within_budget_34ms": bool(statistics.median(
                [1.0 if p["within_budget_34ms"] else 0.0 for p in per]) >= 0.5),
            "spread_pct": round(100 * (max(rates) - min(rates)) / statistics.mean(rates), 2) if len(rates) > 1 else 0.0,
        }
    batch["aggregate"] = agg

    # 后端标签完整性：**标签不许自证**，必须用进程内实证。
    # 四条证据（GPU 臂要求全中，CPU 臂要求"llvmpipe + 无 nvidia fd + 无 nvidia 库 + 渲染活着"）：
    #   ① `gl_strings`      —— 来自**批级独立子进程探针**（不是被测进程，理由见 `_GLIDPROBE` 注释）
    #   ② `nvidia_fds`      —— 每 worker 自己 /proc/self/fd 里的 /dev/nvidia*（父进程侧再核一次）
    #   ③ `loaded_gl_libs`  —— 每 worker /proc/self/maps 里已加载的 NVIDIA / Mesa 库
    #   ④ `render_health`   —— 两道渲染闸：liveness（换状态后 sha 必须变，防冻结缓冲刷虚高）
    #                          + fidelity（回到同 seed reset 态 sha 必须逐字复现，防"在动但内容是垃圾"）
    expect = {"egl_nvidia": "nvidia", "osmesa": "mesa", "cpu": "mesa", "mesa_egl": "mesa"}[mode]
    probe = batch.get("gl_identity_probe") or {}
    gls = " | ".join(probe.get("gl_strings") or [])
    probe_libs = probe.get("loaded_gl_libs") or {}
    probe_fds = probe.get("nvidia_fds") or []
    li = {"mode": mode, "expect": expect, "per_worker": [], "ok": True, "mismatches": [],
          "gl_identity_probe": {"ok": probe.get("ok"), "gl_strings": gls, "pid": probe.get("pid"),
                                "nvidia_fds": probe_fds, "probe_image": probe.get("probe_image"),
                                "nvidia_libs_loaded": sorted(probe_libs),
                                "error": probe.get("error"),
                                "semantics": "批级证据（独立子进程），对该批所有 worker 生效"}}
    if not probe.get("ok"):
        li["ok"] = False
        li["mismatches"].append(f"GL 身份探针本身失败：{probe.get('error') or 'no gl_strings'}")
    for w, r in enumerate(results):
        libs = r.get("loaded_gl_libs") or {}
        fds = r.get("child_nvidia_fds") or r.get("child_nvidia_fds_observed_by_parent") or []
        liveness = bool(r.get("render_health_ok"))
        nvidia_lib = any(k.startswith(("libEGL_nvidia", "libnvidia-glcore", "libnvidia-eglcore")) for k in libs)
        mesa_lib = any(("OSMesa" in k) or ("gallium" in k) or ("swrast" in k) for k in libs)
        checks = {
            "gl_renderer_is_nvidia": "NVIDIA" in gls and "llvmpipe" not in gls,
            "gl_renderer_is_llvmpipe": "llvmpipe" in gls or "Mesa" in gls,
            "holds_nvidia_fd": bool(fds),
            "nvidia_libs_loaded": nvidia_lib,
            "mesa_libs_loaded": mesa_lib,
            "render_health_ok": liveness,
            "render_liveness_ok": bool(r.get("render_liveness_ok")),
            "render_fidelity_ok": bool(r.get("render_fidelity_ok")),
        }
        if expect == "nvidia":
            ok = (checks["gl_renderer_is_nvidia"] and checks["holds_nvidia_fd"]
                  and nvidia_lib and liveness and bool(probe.get("ok")))
        else:
            ok = (checks["gl_renderer_is_llvmpipe"] and not fds and not nvidia_lib
                  and liveness and bool(probe.get("ok")))
        li["per_worker"].append({"worker": w, "ok": ok, "gl_renderer": gls,
                                 "child_nvidia_fds": fds, "nvidia_libs": nvidia_lib,
                                 "mesa_libs": mesa_lib, "render_health": liveness,
                                 "render_fidelity": r.get("render_fidelity"),
                                 "render_liveness_pre": r.get("render_liveness_pre"),
                                 "render_liveness_post": r.get("render_liveness_post"),
                                 "checks": checks})
        if not ok:
            li["ok"] = False
            li["mismatches"].append(
                f"w{w}: 标签={mode} 但实证不符（gl={gls[:80]}, fds={fds}, nvidia_lib={nvidia_lib}, "
                f"render_health_ok={liveness}, liveness={r.get('render_liveness_ok')}, "
                f"fidelity={r.get('render_fidelity_ok')}）")
    batch["label_integrity"] = li
    batch["render_liveness_all_ok"] = bool(results) and all(bool(r.get("render_liveness_ok")) for r in results)
    batch["render_fidelity_all_ok"] = bool(results) and all(bool(r.get("render_fidelity_ok")) for r in results)
    batch["render_health_all_ok"] = bool(results) and all(bool(r.get("render_health_ok")) for r in results)
    batch["render_health_note"] = ("liveness（渲→走物理→再渲，sha 必须变）抓**冻结缓冲**；"
                                   "fidelity（回到同 seed reset 态重拍，sha 必须逐字复现 + 三相机互异 + 非退化）"
                                   "抓**在动但内容是垃圾**。实测 raw_after 污染只被 fidelity 抓到，"
                                   "liveness 判 true ⇒ 两道闸缺一不可（见 RAW_PROBE_INTERFERENCE.json）")
    if results and results[0].get("ok"):
        batch["five_element_annotation"] = {
            "backend": f"{results[0].get('mujoco_gl')} + vendor_icd={os.path.basename(str(results[0].get('vendor_icd')))}",
            "mujoco_version": results[0].get("mujoco_version"),
            "model": {"env_id": "gym_aloha/AlohaTransferCube-v0",
                      "morphology": "aloha_bimanual_14d",
                      "nq_nv_nu_ncam": [results[0]["model"][k] for k in ("nq", "nv", "nu", "ncam")],
                      "nmeshface": results[0]["model"]["nmeshface"],
                      "nmeshvert": results[0]["model"]["nmeshvert"]},
            "n_cameras": {"render_3cam_224": len(CAMS_224), "env_step_native": len(CAMS_NATIVE)},
            "resolution": {"cam_224": [224, 224], "env_native": list(NATIVE_HW)},
            "control_hz": results[0]["live_timing"].get("control_hz"),
            "representation_version": results[0]["shim"].get("representation_version"),
            "shim_sha256_12": results[0]["shim"].get("shim_sha256_12"),
            "venv": PY,
        }
        batch["gl_strings_w0"] = (batch.get("gl_identity_probe") or {}).get("gl_strings") or results[0].get("gl_strings")
        batch["images_at_reset_w0"] = results[0].get("images_at_reset")
        batch["images_after_steps_w0"] = results[0].get("images_after_steps")
    return batch


MANIFEST_DESC = {
    "calib_egl_nvidia_": ("E3-2/3/4 单批原始产物：GPU 臂（MUJOCO_GL=egl + 前缀 NVIDIA vendor ICD），"
                          "含五个可归因分量、五元标注、shim 指纹、label_integrity、逐 0.3 s 的 GPU 采样与"
                          "子进程 /dev/nvidia* fd、`loadavg`+`nr_throttled` 成对",
                          "主线口径重标定（**权威：234814 轮**；220400 轮为无探针参照轮；"
                          "221443/222019 轮 GPU 数字已作废，见 INVALIDATED_RUNS.json）"),
    "calib_osmesa_": ("E3-2/3/4 单批原始产物：CPU 对照臂（MUJOCO_GL=osmesa，llvmpipe），字段同上；"
                      "**这是裁定 59 保留的退路/对照口径**", "主线口径重标定（对照臂）"),
    "summary_": ("一轮扫描的汇总：逐批 all_ok/label_integrity/GPU 峰值/负载对 + `sweep` 表"
                 "（跨 rep 中位数 + 相对 w=1 的并行扩展效率）+ 末态边界闸", "汇总（引用入口）"),
    "COTENANT_CORRECTION.json": ("**共租标签更正件**：`*_proxy_a2_*` 四个文件的假体从未启动"
                                 "（开跑前闸检测到卡上有别人的 compute 进程），实际共租方 = PID 559213，"
                                 "归因为 A2 的 π₀.₅ 闭环延迟重测（三条时间线证据），并自报"
                                 "「闸只挡假体、没挡自己的 GPU 批次」这个程序问题（已修为批级闸）",
                                 "口径更正（引用 `*_proxy_a2_*` 前必读）"),
    "selfcheck_egl_nvidia_": ("E3-1 激活件自证（GPU 臂）：L1–L6 全过 + `GL_RENDERER=NVIDIA A800-SXM4-80GB` "
                              "+ 子进程持 /dev/nvidia2、/dev/nvidiactl + 自证前后边界闸都干净",
                              "E3-1 交付判据"),
    "selfcheck_mesa_egl_": ("E3-1 激活件自证（变异臂：库在 LD_LIBRARY_PATH 上但 ICD 指回 50_mesa.json）"
                            "⇒ 必须回到 llvmpipe 且 fd 为空", "判据有牙的证据（负向）"),
    "selfcheck_cpu_": ("E3-1 激活件自证（对照臂：MUJOCO_GL=osmesa，不注入任何 NVIDIA 库）"
                       "⇒ llvmpipe、fd 为空、GPU 0 占用", "判据有牙的证据（负向）"),
    "MANIFEST.json": ("本清单", "索引"),
    "E_IDENTITY_TABLE_": (
        "**散文可核身份表（机器生成件，`scripts/e_write_identity_table.py`）**：D 的裁定 89.7 新规则 "
        "`prose_identity_must_be_verifiable_against_a_saved_artifact` 的落地件 —— **散文里引用的每个 sha 都必须与本表相等**；"
        "本表没有的路径，散文只引路径、不引 sha。每条给 **`sha256_12`（本仓引用口径）+ `sha1_12`（只为让算法错配一眼可见，不得引用）"
        "+ `n_lines`（`wc -l` 口径）+ `n_lines_splitlines` + `ends_with_newline` + bytes + mtime + `why_it_matters` + `citable_as`**。"
        "**起因**：E 在 §E12.6 把 sha1[:12] 当 sha256[:12] 写进散文，D 靠 before 影像一条命令判定（裁定 89.7 / 缺陷类 ⑨）。"
        "**内建三道闸且都装过牙**：① 拒绝覆写已存在的表（exit 3，实测）；② 缺失文件不静默跳过（`missing:true` + exit 5，"
        "实测注入 1 个不存在路径 ⇒ `n_missing=1` 且命中项正是注入项）；③ 空清单不生成（exit 4，裁定 88.3-2）",
        "引用纪律（**引用任何 E 侧 sha 前必读**；本表的 sha 由引用方重算）"),
    # 键以 `*` 开头 = **后缀匹配**（用来整批标注某个时间戳轮次的产物，不必逐文件写 32 条）
    "*_20260929_221443.json": ("**GPU 数字已作废**（raw-probe 污染：GPU 臂渲染吞吐虚高 +27%～+95%，"
                               "osmesa 臂与 `physics_only` 不受影响）。作废依据与替代产物见 "
                               "INVALIDATED_RUNS.json + RAW_PROBE_INTERFERENCE.json",
                               "口径更正（**禁止引用其 GPU 数字**）"),
    "*_20260929_222019.json": ("**GPU 数字已作废**（raw-probe 污染 + 共租标签误标：文件名里的 `proxy_a2` "
                               "是假的，真实共租方见 COTENANT_CORRECTION.json）",
                               "口径更正（**禁止引用其 GPU 数字**）"),
    "*_20260929_220400.json": ("**无探针参照轮**：该轮脚本尚未加入裸 mujoco 探针 ⇒ GPU 数字未受污染，"
                               "可用作 234814 权威轮的交叉验证（实测吻合：w1 `env_step_native` 135.24 vs 136.99 = +1.3%；"
                               "w8 741.85 vs 749.38 = +1.0%）。**弱点**：早于 `label_integrity`/`gl_identity_probe`/"
                               "渲染双闸 ⇒ 缺批级 GL 标签实证，只作参照不作权威",
                               "交叉验证（可引用，但须注明缺闸）"),
    "*_20260929_234814.json": ("**权威轮**（修复 raw-probe 污染之后重跑）：16 批全部 `all_ok` + "
                               "`render_health_all_ok`（liveness+fidelity）+ `label_integrity_ok` + "
                               "`gl_identity_probe_ok`，GPU 批次**全部独占卡**（`cotenant_actual` 为空），"
                               "`_excluded_batches` 为空 ⇒ §6.2/§6.3 主表的唯一数据源",
                               "主线口径重标定（**权威**）"),
    "GPU_YIELD_INCIDENT_2358.json": ("**E 抢卡事故取证件（第 3 次程序问题自报）**：E 的共租假体（PID 156355、"
                                     "14714 MiB、100% util）在 23:58:39–23:59:55（76 s = A2 申报窗口的 50.4%）"
                                     "压进 A2 裁定 76.4 的 quiet-window rep1 ⇒ A2 自己的闸判 `contaminated=true`、rep1 作废。"
                                     "根因 = `compute-apps` 看不见「已起跑但尚未分配显存」的进程；"
                                     "修法 = `card_busy()` 三网并查 + 起假体需 `--i-have-declared-gpu-window` + 起后复查即撤",
                                     "事故自报（跨线，A2/D 必读）"),
    "calib_osmesa_w1_r0_proxy_a2_20260929_235835": ("**不可当共租档用**：该轮两个 egl 批被 E 自己的批级闸跳过"
                                                    "（假体已上卡且 A2 在跑），只剩 2 个 osmesa 批；"
                                                    "文件名里的 `proxy_a2` 仍是误标。详见 GPU_YIELD_INCIDENT_2358.json",
                                                    "事故留档（**禁止引用其数字**）"),
    "calib_osmesa_w4_r0_proxy_a2_20260929_235835": ("同上：**不可当共租档用**、禁止引用其数字",
                                                    "事故留档（**禁止引用其数字**）"),
    "summary_20260929_235835.json": ("23:58 抢卡事故那一轮的汇总：`cotenant_started`（假体 PID 156355）+ "
                                     "`skipped_batches`（两个 egl 批被批级闸正确跳过）+ 2 个 osmesa 批。"
                                     "**本轮不构成 §8.3-4 共租档的交付**", "事故留档（引用前必读 GPU_YIELD_INCIDENT_2358.json）"),
    "RAW_PROBE_INTERFERENCE.json": ("**测量污染事故取证件**：同进程内"
                                    "「先 dm_control 渲染、再建/关裸 mujoco.Renderer」(raw_after) 会让后续所有 "
                                    "`physics.render` 返回冻结旧缓冲（sha12 不变、三相机趋同）且渲染吞吐虚高 ~30%；"
                                    "三臂对照 no_raw / raw_first / raw_after + 结论「A2 属 raw_first ⇒ 安全」",
                                    "口径更正（引用任何 GPU 吞吐数字前必读）"),
    "INVALIDATED_RUNS.json": ("**作废清单**：点名 22:14（`summary_20260929_221443.json`）与 22:20"
                              "（`summary_20260929_222019.json`）两轮的 GPU 数字全部作废（raw-probe 虚高 + 共租误标），"
                              "并给出替代产物", "口径更正（引用前必读）"),
    "RENDER_DETERMINISM.json": ("**渲染逐位确定性取证（n=2，`reps=2`）**：同一物理状态下重复渲染，`osmesa` 臂三相机"
                                "全部逐位确定；`egl`+NVIDIA 臂 `left_wrist`/`right_wrist` **不确定**"
                                "（±1 LSB、≤0.00072 的 mean_abs_diff、≤21 px/150528）⇒ 保真闸不能用 sha 严格相等，"
                                "必须用数值容差。**本件里「`angle` 确定 / `left_wrist` 跨进程稳定」两条只在 n=2 下成立，"
                                "已被 `RENDER_DETERMINISM_REPS5.json`（n=5）推翻**（`angle` 进程内 4/5、跨进程 5 个 sha 里 2 种）"
                                "⇒ **引用本件时必须同时引用 REPS5 件**；本件逐字未动（append-only）",
                                "跨线取证（图像哈希类判据前必读；`angle`/跨进程结论以 REPS5 件为准）"),
    "RENDER_DETERMINISM_REPS5.json": ("**渲染逐位确定性 `reps=5` 扩展轮（裁定 83 §8-①，D 指派 N≥5）**：5 个独立进程 × "
                                      "2 后端 × 3 相机。**直接回答裁定 83.4 的问题「`left_wrist` 跨进程稳定是不是运气」= 是运气**；"
                                      "更强的一条：**egl 下没有任何相机在跨进程意义上逐位可复现**（`angle` 进程内 4/5 det、"
                                      "`left_wrist` 0/5、`right_wrist` 0/5；osmesa 三相机 5/5 全 det 且跨进程同 sha）⇒ "
                                      "**裁定 83.3 的可推翻条件③ 被触发**（机器现算字段 `ruling_83_3_stands=false`）。"
                                      "最坏 `max_abs_diff=1`（1 LSB）/ `frac_diff_px=0.0518%` ⇒ D 定的 replay 容差**仍够用**"
                                      "（`<=0.005` 余量 9.7×），但「`angle` 逐位」当硬判据会有 **~1/5 的不可复现假红**",
                                      "跨线取证（**权威版**；B2 replay 闸 / A2 图像参照必读）"),
    "RENDER_DETERMINISM_TEAM480x640_OSMESA_REPS5.json": (
        "**T-E-DET-480（裁定 86.3 / RR-B2-21 采纳）的 osmesa 对照臂，`reps=5`，480×640 团队三槽**"
        "（相机 = `top`/`left_wrist`/`right_wrist`，抄 B2 的 `TEAM_SLOT_CAMERA`）。实测**三槽 5/5 全逐位确定**、"
        "`max_abs_diff=0`、`frac_diff_px=0.0`、`mean_abs_diff=0.0`、跨进程 sha 相同 ⇒ "
        "**丙案（裁定 85.2-2）把 osmesa 当「逐位对照后端」在 480×640 上也成立**。**纯 CPU、未触卡**"
        "（`gpu_before`/`gpu_after` 均 `0 MiB`）。本臂**不重判**裁定 83.3 的三条可推翻条件"
        "（那是 π₀.₅ 224² 采集臂的口径，裁定 71 `caliber_transplant_ban`）⇒ 产物写 `rejudged_this_round=false` + 理由",
        "跨线取证（**480×640 的 osmesa 侧有效**；egl 侧待重跑）"),
    "RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.json": (
        "**已作废，禁止引用**（`vacuous_all_reps_skipped_no_measurement`）：`02:22:37` 起跑前批级让位闸读到 fd 网有 "
        "B2 的 PID 388252 ⇒ **5 个 rep 全跳过**（`per_backend={}`），而**当时那一版**汇总在空集上算出 "
        "`all_bitwise_deterministic=true`（平凡真）= **没测到却报绿**。**让位闸本身判对了**（E 没抢卡），"
        "缺陷只在「跳过后如何汇报」⇒ 已加第四道闸修掉（`measurement_status` + `not_a_pass` + **exit 4**，"
        "变异体双向证明 M1/M2 见 `runs/infra/e_egl_coldstart_*/gate_mutation/`）。"
        "**原字节按 append-only 保留**（它是让位闸在真实抢卡场景下生效的唯一实证）；"
        "引用它必须同引 `VACUOUS_ARTIFACT_20260930_0222.md` 与 `*.INVALIDATED.json`",
        "口径更正（**禁止引用**；替代件 = 同名 `_r2`，**已于 03:02:48 测得**）"),
    "RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json": (
        "**T-E-DET-480（裁定 86.3）egl 臂的有效测量件 = 上面那个作废件的替代件**"
        "（裁定 88.5-5 / §D88.4；裁定 89.5-2 已验收，P1 关闭）。"
        "`reps=5`、480×640、相机 = `top`/`left_wrist`/`right_wrist`、`n_reset=3`、`n_shoot_per_state=3`、5 个独立子进程。"
        "**`measurement_status=measured`、`unmeasured_backends=[]`、`SKIPPED` 计数 = 0**"
        "（让位闸 5 次复测三网全 `busy=false`）⇒ **不构成裁定 88.3-2 的空集**，第四道闸未触发、`exit 0`。"
        "**实测结论：三槽在 `egl_nvidia` 上都不逐位**（`bitwise_deterministic_in_process_all_reps=false`、"
        "`cross_process_same_sha=false`），量级 = **1 LSB**：`max_abs_diff_worst` 三槽全 = 1，"
        "`max_frac_diff_px_worst` = `top 2.9e-05` / `left_wrist 9.4e-05` / `right_wrist 2.25e-04`（≈69 px / 307200）。"
        "**抖动出现在进程内**（`same_state_shas` 三张即不同，`n_unique_shas` 5–6/6）。"
        "osmesa 同分辨率对照臂三槽 5/5 全逐位、`max_abs_diff=0` ⇒ 模式与 224² 一致"
        "（egl 不逐位 / osmesa 逐位，与分辨率无关），**实证红线 `render_bitwise_equality_ban_on_egl`（裁定 85.2-2）**。"
        "**本件不重判裁定 83.3**（`rejudged_this_round=false` + 理由：83.3 的三条是为 224² 的 `angle`/… 定的，"
        "搬过来判 = 裁定 71 `caliber_transplant_ban`）。**本件不给容差、不自造阈值、不判 G4d 红绿**"
        "（裁定 87.1-2 / 三值纪律）；按 §D88.4 它**只是登记带**（`register_only`），倍数由 D 定",
        "跨线取证（**480×640 的 egl 侧权威件**；B2 的 G4d 登记带基础；给 B2 的读法 = "
        "`per_backend.<mode>.cams[<camera>]`，与 224² 同名同义，只需换路径 + 相机名 `angle→top`）"),
    "RENDER_DETERMINISM_TEAM480x640_EGL_REPS5.INVALIDATED.json": (
        "**机器可读的作废旁证件**：被作废件的身份（sha256-12 `ba1d1f56ab93` / 18,064 B / 598 ln / 生成器 `d592983ca264`）、"
        "作废类别与理由、`must_not_be_cited_as`、引用规则、让位闸判对的证据（fd 网 PID + `compute-apps` 盲 + 12 MiB）、"
        "修法的身份与变异体证明路径、替代件路径。**E 没有动 `INVALIDATED_RUNS.json`**（那是探针污染专用件、"
        "被裁定 85.1 引用的字节，不该被扩容成通用登记簿）",
        "口径更正（引用前必读；机器可判）"),
    "VACUOUS_ARTIFACT_20260930_0222.md": (
        "**作废标记（人读版）**：同上那件的人类可读说明 —— 作废件身份、类别、为什么作废（机器可核）、"
        "让位闸记功、已装的修法与变异体证明、为什么按 append-only 留在原地、替代件与已测得的 osmesa 臂",
        "口径更正（引用前必读）"),
    "RENDER_DETERMINISM_DEFAULTARM_REGRESSION_reps1.json": (
        "**默认臂回归自证件（不是测量件）**：给 `e_render_determinism.py` 加 `--cams`/`--resolution`（T-E-DET-480 需要）之后，"
        "用**默认参数**（224×224 + `angle,left_wrist,right_wrist`）真跑一条 osmesa rep 并逐键比对 "
        "`RENDER_DETERMINISM_REPS5.json`：顶层键序**完全一致**、`verdict` 键序一致、`applies_when` 逐字相同、"
        "12 个 rep 载荷共有键不变，**唯一差别 = 每个 rep 新增一个 `resolution` 字段**（加法，不改任何既有值）⇒ "
        "**D 在裁定 86.3 引用的那一版 `2449fef70b93` 的默认行为等价**",
        "自证（默认口径未漂移；**不得**当确定性数据引用，`reps=1`）"),
    "before_images/round5_docs/": (
        "**第 5 轮前像（裁定 35.1 / 83.5，03:1x）**：两件 —— ① `docs__infra-gpu-render.md.before` = 给 "
        "`docs/infra-gpu-render.md` 加 **§0.3 权威恢复块**之前留的字节前像"
        "；② `MANIFEST.json.before` = 本轮 `--manifest-only` 原地重写之前的清单字节"
        "（**因为 MANIFEST 是原地重写件，不留前像就会重演 `OVERWRITE_EVENT_20260929_2345.md` 那起事故**，裁定 83.5）"
        "（裁定 88.4-2 的第二步：点名 checkpoint §19.0 的临时版已被取代 + §19.0-3 的临时判据按其自身可推翻条件退役）。"
        "**改后实测：首 7 行原字节保留**（前后 `head -7 | sha256sum` 均为 `ad4bb4e9ed5c`）、386 → 415 ln"
        "（**该文件 03:4x 又因 exit 5 更正长到 432 ln**，见 `before_images/round6_exit5/`；本行记的是**第 5 轮那一次**的增量）",
        "前像（可复原第 5 轮编辑前的字节）"),
    "before_images/round6_exit5/": (
        "**第 6 轮前像（裁定 35.1 / 83.5，03:4x–03:5x）**：修 **`E_SKIP_GPU=1` 档的退出码假绿**之前留的字节前像 —— "
        "4 个被改对象（`scripts/e_coldstart_gpu_render.sh`、`scripts/e_egl_coldstart.py`、`docs/infra-gpu-render.md`、"
        "`docs/e_handoff_to_d_20260929.md`）+ `daily_report.md`（追加 §E12.10 前）。"
        "**缺陷本身**：那一档 stdout 诚实写着 `COLDSTART_PARTIAL_OK …（未实测 GL_RENDERER）`，**却 `exit 0`**；"
        "而裁定 89.5-1 之后 **exit code 就是权威判据**、`docs/infra-gpu-render.md` §0 第一行就是「exit 0 ⇒ GPU 渲染可用」"
        "⇒ **只看 `$?` 的调用方（编排器 / CI / `&&` 链）会把「GPU 根本没测」读成「可用」**。"
        "**修法**：该档 **`exit 0` → `exit 5`**（与 `e_egl_coldstart.py` 顶层 PARTIAL 同号同义），退出码全集变 **0 / 1 / 5**；"
        "`tooth_relink` 的断言 `exit_zero` → **`exit_partial_5`（精确等值，不是放宽）**，实测 `tooth_proven=true`。"
        "**同型 = 裁定 87.1-2 `partial_delivery_must_not_carry_a_whole_delivery_boolean` 在退出码这一维的实例**",
        "前像（可复原第 6 轮编辑前的字节；亦是 §E12.10 身份串的可核产物）"),
    "before_images/round4_window2/": (
        "**第 4 轮前像（裁定 35.1 / 83.5，03:0x）**：GPU 窗口 #2 的两次 `daily_report.md` 追加"
        "（§E12.6 申报 + §E12.7 销账与结果）之前留的字节前像"
        "（`daily_report.md.beforeE12_2` = 6436 ln / `4aeecfc97089` / 898026 B / mtime 02:35:29；"
        "`daily_report.md.beforeE12_7` = 6454 ln / `b145f7325ee2`）。"
        "**第二个用途 = 裁决散文 sha 冲突**：裁定 89.7 抓到 E 在 §E12.6 用了 sha1 而非本仓口径的 sha256[:12]，"
        "正是靠 `beforeE12_2` 一条命令判定（行数/字节/mtime 三项当时都对，只有 sha 用了另一算法）"
        "⇒ **before-image 纪律第三次证明其价值**；亦满足新规则 "
        "`prose_identity_must_be_verifiable_against_a_saved_artifact`",
        "前像（可复原第 4 轮编辑前的字节；亦是散文身份串的可核产物）"),
    "before_images/round3b_20260930/": (
        "**第 3b 轮前像（裁定 35.1 / 83.5，02:3x）**：修 P0 反向牙咬出的**采样窗竞态**之前，对 "
        "`scripts/e_gpu_egl_verify.py`（`run_child` 的采样逻辑）、`scripts/e_activate_selfcheck.py`"
        "（观测窗 + `invalid_measurement` 档）、`scripts/e_coldstart_gpu_render.sh`（exit 1/2/3 分流文案）"
        "留的字节前像 + 声明清单 + 全子树 stat 索引。**单独一轮**是因为这三件不在 round3 的声明里",
        "前像（可复原第 3b 轮编辑前的字节）"),
    "before_images/round3_20260930/": (
        "**第 3 轮前像（裁定 35.1 / 83.5，02:0x）**：本轮改 `e_render_determinism.py`（加 `--cams`/`--resolution`）、"
        "`docs/infra-gpu-render.md`（裁定 85.9-3-1 要求把冷启动那一条命令写进顶部）、"
        "`docs/e_handoff_to_d_20260929.md`（§4-2 结案更正 / §4-3 caveat / 新增 §4-10、§4-11 / §5 追加）、"
        "`daily_report.md`（只追加 §E12.0 申报 + §E12.1 销账 + §E12）、重生成 MANIFEST 之前留的前像 "
        "+ 声明清单（7 项）+ 全子树 stat 索引（33,788 文件）",
        "前像（可复原第 3 轮编辑前的字节）"),
    "OVERWRITE_EVENT_20260929_2345.md": ("**覆写事件登记件（裁定 83.5 要求，第 3 次程序问题自报）**：E 原地重生成 "
                                         "`RAW_PROBE_INTERFERENCE.json` 未留前像 ⇒ D 引用的 23:23:48 版字节串**灭失、不可恢复**。"
                                         "D 点名的六项逐条给全（被覆写文件名 / 两次旧 `generated_at` 23:23:48、23:42:22 / "
                                         "旧 generator sha `ae3e735a8719` / 新 sha `74e8afe88a4d`（产物 `57d284c2b9df`）/ "
                                         "「旧内容不可恢复」已确认 / 为何未按 append-only）+ 修法（拒绝覆写闸 + 复用 C2 守卫留前像）",
                                         "事故自报（裁定 83.5 / `citation_sha_as_of_discipline` 第 3 起）"),
    "GATE_POLARITY_RECHECK.json": ("**闸极性与文案复核件（裁定 83 §8-③④，纯离线反事实重算，未占 GPU）**："
                                   "① **确认 D 的根因推断 = `confirmed`（6/6 判据）**：严格 sha 版 fidelity 在 egl 干净臂 "
                                   "**4/4 假红**、osmesa 臂 0/6、干净臂最坏 `max_abs_diff=1`、污染臂 255、假红集中在 wrist "
                                   "⇒ **「现象 B（egl 下 wrist 不逐位）就是 fidelity 假红的根因」成立**；"
                                   "② **7 条闸逐条点名极性**：`cam_convergence` = **假绿**（文案写「三相机均值趋同」、"
                                   "实现只做 sha 半条；阈值由数据现算：污染臂 6.8812、干净臂最小分离 36.12×）、"
                                   "1 条 `stale_docstring`、2 条显式标「本 regime 无牙」；"
                                   "③ `correction_to_ruling_82_5_4_1`：**裁定 82.5-4① 的「区分信号是 frozen/cam_convergence "
                                   "而不是 fidelity」不成立**（只有 mean 收敛成立），请 D 更正",
                                   "口径更正（裁定 82.5-4① / 83.6 的 E 侧答复）"),
    "before_images/round2_20260930/": ("**第 2 轮前像（裁定 35.1）**：本轮（01:1x）改 §4-2/新增 §4-10~12/补 §6.1 + "
                                       "改 MANIFEST_DESC + 重生成 MANIFEST + 追加 daily_report §E12 之前，用 **C2 的守卫**"
                                       "（`scripts/c2_driver_output_guard.py snapshot`，未新写）对 4 个声明路径留的字节前像 "
                                       "+ 声明清单 + 全子树 stat 索引。**单独放子目录**是因为守卫的 `.before` 文件名固定，"
                                       "写回第 1 轮目录会**覆写第 1 轮前像**（= 再犯一次无守卫覆写）",
                                       "前像（可复原第 2 轮编辑前的字节）"),
    "before_images/": ("**第 1 轮前像（裁定 35.1，00:30:39）**：E 补 §1.5–§1.8 / 改 §6.0 / 重写 §7 之前，"
                       "对 11 个声明路径留的字节前像（含 `daily_report.md`、两份 docs、`e_mainline_render_calib.py`、"
                       "`e_rawprobe_interference.py` 与 5 份 runs 产物）+ 声明清单 + 全子树 stat 索引；"
                       "M2 复核 11/11 sha 一致。`docs__infra-gpu-render.md.before2` 是更早一轮（22:06）加 §7 前的前像",
                       "前像（可复原第 1 轮编辑前的字节）"),
    "WHY_BEFORE_IMAGE.md": ("**前像说明书**：为什么留前像、两轮各覆盖哪些文件、复核命令与实测输出、"
                            "以及「`daily_report.md` 的前像只有 00:30:39 那一版（5131 ln），之后 A2 又追加了 §12/§13 "
                            "⇒ **复原它会连带抹掉 A2 的追加**，故该前像只作取证、不作复原源」这一使用限制",
                            "前像说明（裁定 35.1）"),
    "rawprobe_logs": ("`e_rawprobe_interference.py` 三臂 × 两后端 × 2 rep 的**逐次原始 stdout/stderr**"
                      "（含 raw_after 臂退出时的 `EGLError: EGL_NOT_INITIALIZED` 原文）",
                      "取证明细（RAW_PROBE_INTERFERENCE.json 的原始日志）"),
}


def write_manifest(out_dir: Path, task: str, notes: dict | None = None) -> Path:
    """D 执行单 §1/§6-2：产物目录必须有逐文件用途 + 作用域的 MANIFEST。"""
    rows = {}
    # 递归登记：子目录（如 `rawprobe_logs/`）里的原始日志也必须进清单，否则"逐文件用途"有洞。
    for f in sorted(out_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(out_dir).as_posix()
        desc, scope = "(未登记)", "unlisted_引用前须核对"
        # **最长前缀优先**：否则 `summary_` 这种通用条目会盖掉 `summary_20260929_235835.json`
        # 这类专用条目（事故轮的汇总必须能被单独标注为"禁止引用"）。
        best = -1
        for prefix, (d, sc) in MANIFEST_DESC.items():
            hit = (f.name.endswith(prefix[1:]) if prefix.startswith("*")
                   else (rel.startswith(prefix) or f.name.startswith(prefix) or f.name == prefix))
            if hit:
                if len(prefix) > best:
                    best, desc, scope = len(prefix), d, sc
        rows[rel] = {"bytes": f.stat().st_size,
                     "sha256_12": (ev.sha256_of(str(f)) or "")[:12],
                     "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime)),
                     "desc": desc, "scope": scope}
    man = {
        "manifest": str(out_dir) + "/MANIFEST.json",
        "agent": "E",
        "task": task,
        "task_order": "rl_harness_supervision/d_handoff_to_e_20260929.md §8.3",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "prefix": str(ep.PREFIX),
        "boundary": ("prefix-only：只导出 LD_LIBRARY_PATH / __EGL_VENDOR_LIBRARY_FILENAMES / MUJOCO_GL；"
                     "**未写系统目录、未 ldconfig、未 apt/dpkg、未改 NVIDIA_DRIVER_CAPABILITIES**"
                     "（每批前后各核一次 boundary_guard，末态见 summary.boundary_guard_final）"),
        "activation_artifact": "scripts/e_activate_gpu_render.sh（+ scripts/e_activate_selfcheck.py）",
        "load": "每个数值主张同批带 loadavg + nr_throttled（cpu.stat），并行度分母 = cgroup 12 核",
        "notes": notes or {},
        "n_files": len(rows),
        "files": rows,
    }
    path = out_dir / "MANIFEST.json"
    path.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def build_sweep(batches: list[dict]) -> dict:
    """跨 rep 聚合出 (backend, workers) → 各分量吞吐中位数 + 相对 w=1 的并行扩展效率。

    注意两种口径分开记：`aggregate_ctrl_steps_per_s`（各 worker 速率之和，**吞吐**）
    与 `per_worker_median`（单 worker 速率中位数，**延迟**）；扩展效率用前者除以后者的 w=1 基线。
    """
    comps = ["physics_only", "render_3cam_224", "render_native_3cam_480x640",
             "env_step_native", "env_step_plus_3cam_224"]
    table: dict = {}
    excluded: list = []
    for b in batches:
        if not b.get("all_ok") or not b.get("aggregate"):
            excluded.append({"mode": b.get("mode"), "workers": b.get("workers"), "rep": b.get("rep"),
                             "file": b.get("file"), "reason": "not all_ok / no aggregate"})
            continue
        # 只有**渲染活着**且**后端标签实证相符**的批才进 sweep；否则它的吞吐数字可能是
        # 冻结缓冲刷出来的虚高值（22:14 / 22:20 两轮的教训）。
        if not b.get("render_health_all_ok") or not b.get("label_integrity_ok"):
            excluded.append({"mode": b.get("mode"), "workers": b.get("workers"), "rep": b.get("rep"),
                             "file": b.get("file"),
                             "reason": ("render_health_all_ok=false 或 label_integrity_ok=false "
                                        "⇒ 吞吐/图像数字不可信，不进 sweep")})
            continue
        key = (b["mode"], b["workers"])
        table.setdefault(key, []).append(b["aggregate"])
    out = {}
    for (mode, workers), aggs in sorted(table.items()):
        entry = {"reps": len(aggs), "components": {}}
        for c in comps:
            vals = [a[c] for a in aggs if c in a]
            if not vals:
                continue
            agg_sum = [v["aggregate_ctrl_steps_per_s"] for v in vals]
            per_worker = [statistics.median(v["per_worker_ctrl_steps_per_s"]) for v in vals]
            entry["components"][c] = {
                "aggregate_ctrl_steps_per_s_median": round(statistics.median(agg_sum), 2),
                "aggregate_spread_pct": round(100 * (max(agg_sum) - min(agg_sum)) / statistics.mean(agg_sum), 2)
                                       if len(agg_sum) > 1 else 0.0,
                "per_worker_ctrl_steps_per_s_median": round(statistics.median(per_worker), 2),
                "ms_per_ctrl_step_median": round(statistics.median(
                    [v["median_ms_per_ctrl_step"] for v in vals]), 3),
                "within_budget_34ms": bool(all(v["median_within_budget_34ms"] for v in vals)),
            }
        out[f"{mode}__w{workers}"] = entry
    # 二次遍历补扩展效率（第一遍时 w=1 可能还没进表）
    for key, entry in out.items():
        mode, w = key.split("__w")
        base = out.get(f"{mode}__w1", {}).get("components", {})
        for c, val in entry["components"].items():
            b = base.get(c, {}).get("aggregate_ctrl_steps_per_s_median")
            if b:
                val["parallel_scaling_efficiency"] = round(
                    val["aggregate_ctrl_steps_per_s_median"] / (b * int(w)), 3)
    if excluded:
        out["_excluded_batches"] = excluded
    out["_gate_note"] = ("入 sweep 的条件：all_ok + render_health_all_ok（liveness+fidelity）+ label_integrity_ok；"
                         "被排除的批见 _excluded_batches（**不是**静默丢弃）")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backends", default="egl_nvidia,osmesa")
    ap.add_argument("--workers", default="1,2,4,8")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--reps", type=int, default=1, help="同一 (backend, workers) 组合的独立重复批数（D 偏好独立进程重复）")
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--cotenant", choices=(None, "proxy_a2"), default=None)
    ap.add_argument("--cotenant-gib", type=float, default=13.8,
                    help="占位共租的显存球重（默认仿 A2 训练的 13.8 GB，D 断点文件 §3）")
    ap.add_argument("--cotenant-seconds", type=float, default=300.0)
    ap.add_argument("--allow-shared-gpu", action="store_true",
                    help="卡上已有别人（A2/C2）的 compute 进程时，仍跑 GPU 批次。**默认不跑**（D §8.3-4 不得抢卡）")
    ap.add_argument("--i-have-declared-gpu-window", action="store_true",
                    help="起 `proxy_a2` 假体（13.8 GB 球重 + 100%% util matmul，**按设计就是占卡**）前必须显式给出，"
                         "且要求已在 daily_report.md 申报过窗口。缺此旗标一律**不起假体**（23:58 抢卡事故的修法之一）")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--manifest-only", action="store_true",
                    help="只为 --out-dir 重写 MANIFEST.json（不跑任何测量、不占 GPU）")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.manifest_only:
        path = write_manifest(
            out_dir, "MANIFEST 重写（--manifest-only，未跑测量）",
            notes={
                "regeneration": ("MANIFEST.json 是**可重生成件**（每次 --manifest-only 原地重写）。"
                                 "**本轮（03:1x）重生成的原因** = ① 登记 T-E-DET-480 egl 臂的**有效测量件** "
                                 "`RENDER_DETERMINISM_TEAM480x640_EGL_REPS5_r2.json`（03:02:48，`measurement_status=measured`、"
                                 "5/5 无跳过；= 那个假绿作废件的替代件，裁定 89.5-2 已验收）；② 登记 round4_window2 / round5_docs "
                                 "两轮前像（round4 兼作散文 sha 冲突的可核产物，裁定 89.7）；③ 把作废件那一行的"
                                 "「替代件待重跑」改为「已于 03:02:48 测得」。**本轮只改 `MANIFEST_DESC` 与 `notes` 两处数据串，"
                                 "`card_busy()` 的源码字节逐字未动**（改前 `57a40d9d0e66` / 改后 `57a40d9d0e66`，机器比对）"
                                 "⇒ A2 / C2 复用该探测器的行为不受影响。"
                                 "上一轮（02:4x）重生成的原因 = ① 登记 T-E-DET-480（裁定 86.3）的 5 份新产物"
                                 "（480×640 的 osmesa 臂 / 默认臂回归自证 / 那个假绿作废件 + 它的标记件与机器旁证件）；"
                                 "② 登记 round3 / round3b 两轮前像；③ 修掉 01:19 版里 `WHY_BEFORE_IMAGE.md` 那一行的"
                                 "**过期 sha**（当时写 `65175328cef4`，实际文件已是 168 ln 的版本）。"
                                 "上一轮（01:1x）重生成的原因 = 登记 5 份新产物 + 更正 `RENDER_DETERMINISM.json` 的"
                                 "描述（其 `angle`/跨进程结论已被 REPS5 件推翻）。**重写前已按裁定 35.1 留前像**："
                                 "`before_images/round5_docs/`、`round4_window2/`（本轮；这两轮的前像是 `cp -p` 直存"
                                 "——被留前像的对象是 `docs/infra-gpu-render.md` 与共享的 `daily_report.md`，"
                                 "都不在本 `--out-dir` 的测量产物集合内，故不走 C2 守卫的声明清单流程）、"
                                 "`round3_20260930/`、`round3b_20260930/`、`round2_20260930/`"
                                 "（02:4x 及更早各轮，都用 C2 的 `c2_driver_output_guard.py snapshot`，未新写守卫）。"),
                "later_change_96_1_3": (
                    "**上面 `regeneration` 里那句「`card_busy()` 的源码字节逐字未动 ⇒ A2/C2 复用该探测器的行为"
                    "不受影响」只对 03:1x 那一轮成立，不得再被读成常驻事实**（缺陷类 ㉒）。"
                    "2026-09-30 12:4x 按**裁定 96.1-③**（E 主责 · P0.5 · A2 第一次真上卡之前修完）改了"
                    "**网③ cmdline** 的判据：裸关键字 ⇒ **真实执行形态 ∧ 关键字 ∧ 非闲置**，修的是 F 实测的"
                    "两起文本误触发（`runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json`）。"
                    "**网①（compute-apps）与网②（`/dev/nvidia*` fd）源码逐字未改**（ast 逐对象机器比对 7/7）。"
                    "改前身份 = `fd582e261e87`（1279 ln，前像 `runs/infra/e_card_busy_fix_20260930/before_images/"
                    "e_mainline_render_calib.py.before_96_1_3`）；**改后身份本条不自引** —— 本条注释自身也会改变"
                    "本文件的 sha（自指陷阱，裁定 89.7 同族），改动时刻的 after 身份钉死在 "
                    "`runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json` 的 `target_identity.after`。"
                    "**行为确实变了，这正是修法的目的**：文本提及不再计入 busy（另登记在 "
                    "`cmdline_hits_text_mention_only`），真跑照旧计入（反漏检腿 R4/R6/R12/L1 已验）。"),
                "self_sha_caveat": ("本清单**无法登记自己的最终 sha**：`rows` 在写盘前采集，"
                                    "所以 `files['MANIFEST.json'].sha256_12` 恒为**上一版**的字节身份。"
                                    "按 `citation_sha_as_of_discipline`，引用 MANIFEST 的 sha 一律**由引用方重算**，"
                                    "不得采信本行。"),
            })
        print(json.dumps({"manifest": str(path)}, ensure_ascii=False))
        return 0
    ts_all = time.strftime("%Y%m%d_%H%M%S")
    summary: dict = {
        "probe": "scripts/e_mainline_render_calib.py",
        "task": "E3-2 / E3-3 / E3-4（D 执行单 §8.3）",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "hostname": os.uname().nodename,
        "steps_per_component": args.steps, "seed": args.seed,
        "per_step_budget_ms": PER_STEP_BUDGET_MS,
        "cotenant": args.cotenant,
        "cotenant_note": ("**占位共租（proxy）**：由 E 自己起的 torch CUDA 假体，仿 A2 训练的显存/SM 占用；"
                          "**不是** A2 真训练 ⇒ 产物一律标 `proxy_a2`，真并发数字需 D 与 A2 排时间窗后重测。"
                          if args.cotenant else None),
        "batches": [],
    }

    cotenant_proc = None
    cotenant_label = args.cotenant
    if args.cotenant == "proxy_a2":
        # 三网并查（不是只看 compute-apps）：23:58 事故的根因就是 A2 已起跑但尚未分配显存，
        # `compute-apps` 看不见 ⇒ E 误判"卡空"起了假体，压进 A2 申报的静默窗口。
        busy = card_busy(strict=True)
        if not args.i_have_declared_gpu_window:
            cotenant_label = "refused_no_declared_window"
            summary["cotenant_refused"] = {
                "reason": ("`--cotenant proxy_a2` 的假体**按设计就是占卡**（13.8 GB + 100% util），"
                           "而 E 的 GPU 优先权最低（A2 > C2 > E）⇒ 未显式申报窗口一律不起假体"),
                "required_flag": "--i-have-declared-gpu-window",
                "card_busy_at_refusal": busy,
                "policy": ("**跳过所有 GPU 批次**，只跑 osmesa/cpu 臂；要跑共租档须先在 daily_report.md "
                           "申报窗口、确认无他线静默窗口，再带该旗标重跑"),
            }
            print("[refuse] --cotenant proxy_a2 但缺 --i-have-declared-gpu-window ⇒ 不起假体、不跑 GPU 批", flush=True)
        elif busy["busy"]:
            # 闸有牙版：检测到别人（三网任一命中）时，① 不起假体；② 不跑 GPU 批次，
            # 除非显式 --allow-shared-gpu（22:20 那轮的漏洞是只做了①，已在回流单自报）。
            cotenant_label = "blocked_no_proxy_real_cotenant_present"
            summary["cotenant_blocked"] = {
                "reason": "三网并查发现他线在用卡/正要上卡 ⇒ 按 D §8.3-4「不得抢卡」放弃共租假体",
                "card_busy": busy, "loadavg": ev.cpu_stat().get("loadavg"),
                "gpu_batch_policy": ("仍跑 GPU 批次（--allow-shared-gpu 已显式给出）"
                                     if args.allow_shared_gpu else
                                     "**跳过所有 GPU 批次**（只跑 osmesa/cpu 臂），要跑请加 --allow-shared-gpu"),
                "note": ("本轮 22:20 的 `*_proxy_a2_*` 产物是在**真实共租进程**（PID 见 gpu_samples.compute_procs）"
                         "下测的，假体**并未启动** ⇒ 那些文件名里的 proxy_a2 是误标，"
                         "详见同目录 COTENANT_CORRECTION.json。")}
        else:
            cotenant_proc = subprocess.Popen([PY, "-c", _COTENANT, str(args.cotenant_gib),
                                              str(args.cotenant_seconds)],
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(20.0)   # 等球重分配 + matmul 稳态
            # 起完再查一次：假体上卡的这 20 s 内别人可能刚起跑（同样看不见显存）⇒ 立刻撤下假体。
            recheck = card_busy(exclude_pids={cotenant_proc.pid}, strict=True)
            summary["cotenant_started"] = {
                "pid": cotenant_proc.pid, "requested_gib": args.cotenant_gib,
                "gpu_after_start": gpu_snapshot(), "loadavg": ev.cpu_stat().get("loadavg"),
                "recheck_after_start": recheck}
            if recheck["busy"]:
                cotenant_proc.terminate()
                try:
                    cotenant_proc.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    cotenant_proc.kill()
                cotenant_proc = None
                cotenant_label = "withdrawn_other_line_appeared"
                summary["cotenant_withdrawn"] = {
                    "reason": ("假体上卡后 20 s 复查发现他线进程（可能正在加载模型、尚未分配显存）"
                               "⇒ **立即撤下假体**，不占卡、不跑 GPU 批"),
                    "card_busy": recheck, "proxy_pid_withdrawn": summary["cotenant_started"]["pid"],
                    "incident_reference": "23:58 抢卡事故（见 docs/e_handoff_to_d_20260929.md §1.6）",
                }
                print(f"[withdraw] 假体已撤下：{recheck['compute_procs']} "
                      f"{[h['pid'] for h in recheck['nvidia_fd_holders']]} "
                      f"{[h['pid'] for h in recheck['cmdline_hits']]}", flush=True)

    try:
        for mode in [m.strip() for m in args.backends.split(",") if m.strip()]:
            if (cotenant_label == "blocked_no_proxy_real_cotenant_present"
                    or cotenant_label in ("refused_no_declared_window", "withdrawn_other_line_appeared")) \
                    and not args.allow_shared_gpu and mode not in ("osmesa", "cpu"):
                print(f"[skip] {mode}：卡上有别人的 compute 进程且未给 --allow-shared-gpu ⇒ 不抢卡", flush=True)
                summary.setdefault("skipped_batches", []).append(
                    {"mode": mode, "reason": f"cotenant_label={cotenant_label}, --allow-shared-gpu not given"})
                continue
            for workers in [int(w) for w in args.workers.split(",") if w.strip()]:
              for rep in range(args.reps):
                if mode not in ("osmesa", "cpu") and not args.allow_shared_gpu:
                    # 批级"不抢卡"闸（D §8.3-4 / §5：GPU 优先权 A2 > C2 > E）：
                    # **每批开跑前**都查一次卡上是否有别人的 compute 进程；有就跳过这批并登记，
                    # 不做"开跑前查一次就一路跑到底"（22:20 那轮的漏洞正是别人中途上卡）。
                    busy_now = card_busy(exclude_pids={cotenant_proc.pid} if cotenant_proc else None)
                    if busy_now["busy"]:
                        msg = (f"[skip] {mode} w={workers} r={rep}：三网查到他线在用卡/正要上卡 "
                               f"{busy_now['compute_procs']} "
                               f"{[h['pid'] for h in busy_now['nvidia_fd_holders']]} "
                               f"{[h['pid'] for h in busy_now['cmdline_hits']]} "
                               f"且未给 --allow-shared-gpu ⇒ 不抢卡")
                        print(msg, flush=True)
                        summary.setdefault("skipped_batches", []).append(
                            {"mode": mode, "workers": workers, "rep": rep,
                             "reason": "card busy (three-net detection)", "card_busy": busy_now,
                             "loadavg": ev.cpu_stat().get("loadavg")})
                        continue
                t0 = time.time()
                batch = run_batch(mode, workers, args.steps, args.seed, cotenant_label, cotenant_proc)
                batch["elapsed_s"] = round(time.time() - t0, 2)
                batch["rep"] = rep
                name = (f"calib_{mode}_w{workers}_r{rep}" + (f"_{args.cotenant}" if args.cotenant else "")
                        + f"_{ts_all}.json")   # 文件名沿用命令行请求的档位名；**真实共租状态以 JSON 内
                #   cotenant / cotenant_actual / gpu_samples.compute_procs 为准**（见 COTENANT_CORRECTION.json）
                (out_dir / name).write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
                summary["batches"].append({
                    "mode": mode, "workers": workers, "rep": rep, "file": name, "all_ok": batch.get("all_ok"),
                    "verdict": batch.get("verdict"), "wall_s": batch.get("wall_s"),
                    "gpu_util_max": batch.get("gpu_util_max"),
                    "gpu_mem_used_max_mib": batch.get("gpu_mem_used_max_mib"),
                    "workers_with_nvidia_fd": batch.get("workers_with_nvidia_fd"),
                    "aggregate": batch.get("aggregate"),
                    "gl_strings_w0": batch.get("gl_strings_w0"),
                    "gl_identity_probe_ok": (batch.get("gl_identity_probe") or {}).get("ok"),
                    "render_liveness_all_ok": batch.get("render_liveness_all_ok"),
                    "render_fidelity_all_ok": batch.get("render_fidelity_all_ok"),
                    "render_health_all_ok": batch.get("render_health_all_ok"),
                    "label_integrity_ok": (batch.get("label_integrity") or {}).get("ok"),
                    "label_integrity_mismatches": (batch.get("label_integrity") or {}).get("mismatches"),
                    "load_before": batch.get("load_before", {}).get("loadavg"),
                    "load_after": batch.get("load_after", {}).get("loadavg"),
                    "nr_throttled": [batch.get("load_before", {}).get("nr_throttled"),
                                     batch.get("load_after", {}).get("nr_throttled")],
                    "five_element_annotation": batch.get("five_element_annotation"),
                    "images_at_reset_w0": batch.get("images_at_reset_w0"),
                })
                print(f"[batch] {mode} w={workers} r={rep} ok={batch.get('all_ok')} wall={batch.get('wall_s')}s "
                      f"gpu_util_max={batch.get('gpu_util_max')}% mem_max={batch.get('gpu_mem_used_max_mib')}MiB",
                      flush=True)
        summary["sweep"] = build_sweep(summary["batches"])
    finally:
        if cotenant_proc and cotenant_proc.poll() is None:
            cotenant_proc.terminate()
            try:
                out, _ = cotenant_proc.communicate(timeout=30)
                summary["cotenant_stdout"] = (out or "").strip().splitlines()[-3:]
            except subprocess.TimeoutExpired:
                cotenant_proc.kill()
        summary["gpu_final"] = gpu_snapshot()
        summary["load_final"] = ev.cpu_stat()
        summary["boundary_guard_final"] = ep.boundary_guard()
        (out_dir / f"summary_{ts_all}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        write_manifest(out_dir, "E3-2/3/4：prefix-only 下的主线渲染口径重标定 + GPU 并行度重标定")
        print(json.dumps({"summary": str(out_dir / f"summary_{ts_all}.json"),
                          "batches": len(summary["batches"]),
                          "boundary_guard_final_ok": summary["boundary_guard_final"]["ok"],
                          "gpu_final": summary["gpu_final"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
