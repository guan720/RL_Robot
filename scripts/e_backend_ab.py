#!/usr/bin/env python
"""E 线 E2（P1，条件触发）：GPU 渲染下的吞吐重标定 —— **同 venv / 同模型 / 同分辨率，只换后端**。

D 执行单 §3.3-6 的硬要求：跨 venv/后端/模型的数字不得互相搬用（裁定 46.4），
所以 A/B 必须自己两臂都在**本批**测出来，不许拿留档基线当对照臂。
留档基线只作为"第三点"引用，并标明口径差异：
  - D 12.88 ctrl steps/s：osmesa / mujoco 3.9.0 / 单臂 Piper STL / 3 cam 224² / decim16 /
    ctrl 31.25 Hz / 独立进程 3 重复 / loadavg 35.86（`runs/vla/d_render_probe_20260929/single_arm_controlled.json`）
  - D 12.03 ctrl steps/s：同上但 timestep=1/480 / ctrl 30.0 Hz / loadavg 61.89
    （`runs/vla/d_render_probe_20260929/ctrl_hz_alignment.json` → summary.B）
    ⇒ **这两个数在 D 自己的文书里并存**（执行单 §3.3-6 引 12.88，MANIFEST
    `authoritative_numbers` 写 12.03），口径差 = ctrl_hz + timestep + 机器负载，需 D 指定唯一权威值。
  - A2 14.83 ctrl steps/s：egl(实为 llvmpipe) / mujoco 3.8.1 / gym-aloha 双臂 viperx / 3 cam 224² /
    **同进程** 3 重复 / bench_seconds=5 / loadavg 53.5（`runs/vla/a2_pi05_zeroshot_20260929/render_throughput_a2.json`）

两个 case：
  piper_single_arm —— 直接复用 D 的 worker `runs/vla/d_render_probe_20260929/piper_single_arm_sweep.py one`
                      （**只读复用，不改 D 的脚本**），保证模型/decim/相机/分辨率与 D 的基线逐字同口径；
                      只跑单臂（用户指令「先只渲染单臂」），不碰 arms=2 分支。
  gym_aloha        —— 按 A2 `sec_throughput` 的 render-only 口径复现（3 cam 224²、bench_seconds=5），
                      但改成**独立进程重复**（D 的协议偏好），并同时记录 A2 的同进程口径差异。

后端三臂（每条都带 `GL_RENDERER` 实证，标签不许自证）：
  osmesa     —— MUJOCO_GL=osmesa，CPU 软渲染（对照臂）
  egl_nvidia —— MUJOCO_GL=egl + 前缀 LD_LIBRARY_PATH + 前缀 10_nvidia.json（GPU 臂）
  egl_mesa   —— MUJOCO_GL=egl + 前缀在 LD_LIBRARY_PATH 上，但 ICD 指回 50_mesa.json
                ⇒ 变异体：证明"快"来自 vendor ICD 选中 NVIDIA，不是来自"设了 egl"

并行度扫描 1/2/4（**上限 4，裁定 42 / D §5**）。全程记录 loadavg 与 nr_throttled。

用法：
  python scripts/e_backend_ab.py --case piper_single_arm --workers 1,2,4 --reps 3
  python scripts/e_backend_ab.py --case gym_aloha --workers 1 --reps 3
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import e_gpu_egl_verify as ev  # noqa: E402
import e_egl_probe as ep       # noqa: E402  复用前缀/边界闸，避免两处定义漂移

D_WORKER = REPO_ROOT / "runs" / "vla" / "d_render_probe_20260929" / "piper_single_arm_sweep.py"
OUT_DIR = REPO_ROOT / "runs" / "infra" / "e_egl_probe_20260929"

BACKENDS = {
    "osmesa": {"mujoco_gl": "osmesa", "vendor": None, "prefix": False},
    "egl_nvidia": {"mujoco_gl": "egl", "vendor": str(ep.PREFIX / "10_nvidia.json"), "prefix": True},
    "egl_mesa": {"mujoco_gl": "egl", "vendor": ep.MESA_ICD, "prefix": True},
}
PY = {
    "piper_single_arm": "/root/venvs/rlrobot/bin/python",      # mujoco 3.9.0，与 D 基线同 venv
    "gym_aloha": "/root/venvs/pi05_sim/bin/python",            # mujoco 3.8.1，与 A2 基线同 venv
}

_GYM_ALOHA_CHILD = r'''
import json, os, re, sys, time
import numpy as np

def gl_strings():
    try:
        from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString
        return [s.decode() if isinstance(s, bytes) else str(s)
                for s in (glGetString(GL_VENDOR), glGetString(GL_RENDERER), glGetString(GL_VERSION)) if s]
    except Exception as exc:
        return [f"(unavailable: {type(exc).__name__})"]

bench_seconds = float(sys.argv[2])
cams = ["angle", "left_wrist", "right_wrist"]
h = w = 224
out = {"case": "gym_aloha", "mujoco_gl": os.environ.get("MUJOCO_GL"),
       "resolution": [h, w], "n_cameras": len(cams), "bench_seconds": bench_seconds,
       "protocol": "render_only（A2 sec_throughput 口径），独立进程单次"}
try:
    import gymnasium as gym
    import gym_aloha  # noqa: F401
    import mujoco
    out["mujoco_version"] = mujoco.__version__
    env = gym.make("gym_aloha/AlohaTransferCube-v0", obs_type="pixels_agent_pos",
                   render_mode="rgb_array")
    physics = env.unwrapped._env.physics
    env.reset(seed=1000)
    # 预热，排除首帧上下文/编译开销（A2 未预热 ⇒ 这是与 A2 的第二处口径差，记录之）
    for c in cams:
        physics.render(height=h, width=w, camera_id=c)
    img = np.asarray(physics.render(height=h, width=w, camera_id=cams[0]))
    out["image"] = {"shape": list(img.shape), "mean": round(float(img.mean()), 3),
                    "std": round(float(img.std()), 4), "raw_len": int(img.tobytes().__len__())}
    out["gl_strings"] = gl_strings()
    t0 = time.perf_counter(); n = 0
    while time.perf_counter() - t0 < bench_seconds:
        for c in cams:
            physics.render(height=h, width=w, camera_id=c)
        n += 1
    dt = time.perf_counter() - t0
    out.update({"control_steps": n, "wall_s": round(dt, 3),
                "ctrl_steps_per_s": round(n / dt, 2),
                "ms_per_control_step": round(1000 * dt / n, 2),
                "images_per_s": round(n * len(cams) / dt, 2), "ok": True})
except Exception as exc:
    import traceback
    out["ok"] = False
    out["error"] = f"{type(exc).__name__}: {exc}"
    out["traceback_tail"] = traceback.format_exc().strip().splitlines()[-6:]
    out.setdefault("gl_strings", gl_strings())
print("RESULT_JSON" + json.dumps(out))
'''


def backend_env(backend: str) -> dict:
    spec = BACKENDS[backend]
    env = dict(os.environ)
    if spec["prefix"]:
        env["LD_LIBRARY_PATH"] = str(ep.PREFIX) + (
            ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    else:
        env.pop("__EGL_VENDOR_LIBRARY_FILENAMES", None)
        env.pop("__EGL_VENDOR_LIBRARY_DIRS", None)
    if spec["vendor"]:
        env["__EGL_VENDOR_LIBRARY_FILENAMES"] = spec["vendor"]
    env.pop("__EGL_VENDOR_LIBRARY_DIRS", None)
    env["MUJOCO_GL"] = spec["mujoco_gl"]
    env["PYOPENGL_PLATFORM"] = "egl" if spec["mujoco_gl"] == "egl" else "osmesa"
    env["BENCH_BACKEND"] = spec["mujoco_gl"]      # D 的 worker 读这个
    return env


def renderer_evidence(case: str, backend: str) -> dict:
    """后端标签不能自证：同 venv 同环境下取一次 GL_RENDERER + 子进程 /dev/nvidia* fd。"""
    env = backend_env(backend)
    code = ("import os,json\n"
            "os.environ.setdefault('MUJOCO_GL', %r)\n"
            "import mujoco\n"
            "m=mujoco.MjModel.from_xml_string(\"<mujoco><worldbody><light/><camera name='c' pos='1.5 0 1' xyaxes='0 1 0 -0.6 0 1'/><geom type='box' size='.1 .1 .1'/></worldbody></mujoco>\")\n"
            "d=mujoco.MjData(m); mujoco.mj_forward(m,d)\n"
            "r=mujoco.Renderer(m,64,64); r.update_scene(d,camera='c'); r.render()\n"
            "s=''\n"
            "try:\n"
            "    from OpenGL.GL import GL_RENDERER,GL_VENDOR,GL_VERSION,glGetString\n"
            "    s=' | '.join(x.decode() if isinstance(x,bytes) else str(x) for x in (glGetString(GL_VENDOR),glGetString(GL_RENDERER),glGetString(GL_VERSION)) if x)\n"
            "except Exception as e:\n"
            "    s=f'(unavailable: {type(e).__name__})'\n"
            "r.close()\n"
            "print('GLJSON'+json.dumps({'mujoco':mujoco.__version__,'gl':s,'python':__import__('sys').executable}))\n"
            % env["MUJOCO_GL"])
    p = subprocess.Popen([PY[case], "-c", code], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env=env)
    fds = set()
    while p.poll() is None:
        fds.update(ev.child_nvidia_fds(p.pid))
        time.sleep(0.1)
    out, err = p.communicate(timeout=300)
    res = {"backend": backend, "child_nvidia_fds": sorted(fds)}
    for line in out.splitlines():
        if line.startswith("GLJSON"):
            res.update(json.loads(line[len("GLJSON"):]))
    if "gl" not in res:
        res["error"] = (err or out).strip().splitlines()[-4:]
    gl = res.get("gl") or ""
    res["is_nvidia"] = ("NVIDIA" in gl) and ("llvmpipe" not in gl)
    return res


def run_one(case: str, backend: str, rep: int, bench_seconds: float) -> dict:
    env = backend_env(backend)
    if case == "piper_single_arm":
        cmd = [PY[case], str(D_WORKER), "one", f"3,224,224,{rep}"]
    else:
        cmd = [PY[case], "-c", _GYM_ALOHA_CHILD, case, str(bench_seconds)]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=900)
    wall = time.time() - t0
    rec = {"backend": backend, "rep": rep, "subprocess_wall_s": round(wall, 2),
           "returncode": p.returncode}
    txt = p.stdout.strip()
    try:
        rec["result"] = json.loads(txt.splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        rec["parse_error"] = f"{type(exc).__name__}: {exc}"
        rec["stdout_tail"] = txt.splitlines()[-4:]
        rec["stderr_tail"] = p.stderr.strip().splitlines()[-6:]
    return rec


def run_worker_set(case: str, backend: str, workers: int, rep: int, bench_seconds: float) -> dict:
    """并行度档：workers 个**独立进程同时**跑，聚合吞吐 = 各进程吞吐之和。"""
    env = backend_env(backend)
    if case == "piper_single_arm":
        cmd = [PY[case], str(D_WORKER), "one", f"3,224,224,{rep}"]
    else:
        cmd = [PY[case], "-c", _GYM_ALOHA_CHILD, case, str(bench_seconds)]
    load_before = [round(x, 2) for x in os.getloadavg()]
    thr_before = ev.cpu_stat().get("nr_throttled")
    t0 = time.time()
    procs = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, env=env) for _ in range(workers)]
    fd_seen: set[str] = set()
    while any(p.poll() is None for p in procs):
        for p in procs:
            if p.poll() is None:
                fd_seen.update(ev.child_nvidia_fds(p.pid))
        time.sleep(0.2)
    outs = [p.communicate(timeout=900) for p in procs]
    wall = time.time() - t0
    per = []
    for o, e in outs:
        try:
            line = o.strip().splitlines()[-1]
            if line.startswith("RESULT_JSON"):        # 忘了剥前缀会让整批数字变 None（本脚本第一版踩了）
                line = line[len("RESULT_JSON"):]
            per.append(json.loads(line))
        except Exception as exc:  # noqa: BLE001
            per.append({"parse_error": str(exc), "stdout_tail": o.strip().splitlines()[-3:],
                        "stderr_tail": e.strip().splitlines()[-6:]})
    key = "ctrl_steps_per_s"
    vals = [r.get(key) for r in per if r.get(key) is not None]
    return {"backend": backend, "workers": workers, "rep": rep, "wall_s": round(wall, 3),
            "per_worker": per, "per_worker_ctrl_steps_per_s": vals,
            "aggregate_ctrl_steps_per_s": round(sum(vals), 2) if vals else None,
            "per_worker_mean": round(statistics.mean(vals), 2) if vals else None,
            "child_nvidia_fds_union": sorted(fd_seen),
            "loadavg_before": load_before, "nr_throttled_before": thr_before,
            "loadavg_after": [round(x, 2) for x in os.getloadavg()],
            "nr_throttled_after": ev.cpu_stat().get("nr_throttled"),
            "n_ok": len(vals)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True, choices=tuple(PY))
    ap.add_argument("--backends", default="osmesa,egl_nvidia,egl_mesa")
    ap.add_argument("--workers", default="1", help="并行度档，逗号分隔；上限 4（裁定 42）")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--bench-seconds", type=float, default=5.0, help="gym_aloha 用（A2 口径 5 s）")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    guard = ep.boundary_guard()
    if not guard["ok"]:
        print("REFUSE: 系统目录被污染（§3.2 边界）。先跑 "
              "bash scripts/e_install_nvidia_gl_590.sh --uninstall --apply", file=sys.stderr)
        return 3
    if not guard["prefix_libs_complete"]:
        print(f"REFUSE: 前缀库不全 {guard['prefix_libs']}", file=sys.stderr)
        return 3
    worker_counts = [int(x) for x in args.workers.split(",") if x.strip()]
    if max(worker_counts) > 4:
        print("REFUSE: 并行度 >4，违反 D §5 与裁定 42", file=sys.stderr)
        return 3
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]

    report = {
        "case": args.case, "backends": backends, "workers": worker_counts, "reps": args.reps,
        "bench_seconds": args.bench_seconds,
        "agent": "E", "task_order": "rl_harness_supervision/d_handoff_to_e_20260929.md §4",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "python": PY[args.case], "prefix": str(ep.PREFIX),
        "boundary_guard": guard,
        "cpu_stat_before": ev.cpu_stat(),
        "renderer_evidence": {}, "runs": {}, "summary": {},
    }
    print(f"==== E2 后端 A/B · case={args.case} · python={PY[args.case]} ====", flush=True)
    for b in backends:
        report["renderer_evidence"][b] = renderer_evidence(args.case, b)
        e = report["renderer_evidence"][b]
        print(f"  [{b}] GL = {e.get('gl')}  is_nvidia={e.get('is_nvidia')} "
              f"fds={e.get('child_nvidia_fds')}", flush=True)

    for b in backends:
        for w in worker_counts:
            reps = []
            for rep in range(args.reps):
                reps.append(run_worker_set(args.case, b, w, rep, args.bench_seconds))
                print(f"  [{b}] workers={w} rep={rep} agg={reps[-1]['aggregate_ctrl_steps_per_s']} "
                      f"per_worker={reps[-1]['per_worker_ctrl_steps_per_s']} "
                      f"loadavg={reps[-1]['loadavg_before']}", flush=True)
            report["runs"][f"{b}__w{w}"] = reps

    for b in backends:
        for w in worker_counts:
            aggs = [r["aggregate_ctrl_steps_per_s"] for r in report["runs"][f"{b}__w{w}"]
                    if r["aggregate_ctrl_steps_per_s"] is not None]
            pers = [r["per_worker_mean"] for r in report["runs"][f"{b}__w{w}"]
                    if r["per_worker_mean"] is not None]
            report["summary"][f"{b}__w{w}"] = {
                "n": len(aggs),
                "aggregate_ctrl_steps_per_s_median": round(statistics.median(aggs), 2) if aggs else None,
                "aggregate_min": min(aggs) if aggs else None,
                "aggregate_max": max(aggs) if aggs else None,
                "per_worker_mean_median": round(statistics.median(pers), 2) if pers else None,
                "spread_pct": round(100 * (max(aggs) - min(aggs)) / statistics.median(aggs), 1)
                if len(aggs) > 1 and statistics.median(aggs) else None,
            }
    base = report["summary"].get(f"osmesa__w1", {}).get("aggregate_ctrl_steps_per_s_median")
    for b in backends:
        for w in worker_counts:
            v = report["summary"][f"{b}__w{w}"]["aggregate_ctrl_steps_per_s_median"]
            if base and v:
                report["summary"][f"{b}__w{w}"]["speedup_vs_osmesa_w1"] = round(v / base, 2)
    if worker_counts and len(worker_counts) > 1:
        for b in backends:
            one = report["summary"].get(f"{b}__w1", {}).get("aggregate_ctrl_steps_per_s_median")
            for w in worker_counts[1:]:
                agg = report["summary"].get(f"{b}__w{w}", {}).get("aggregate_ctrl_steps_per_s_median")
                if one and agg:
                    report["summary"][f"{b}__w{w}"]["scaling_efficiency_vs_w1"] = round(agg / (one * w), 3)
    report["cpu_stat_after"] = ev.cpu_stat()

    # 判据有牙：后端标签必须与 GL_RENDERER 实证一致，否则 A/B 无效
    mism = []
    for b in backends:
        e = report["renderer_evidence"][b]
        want = (b == "egl_nvidia")
        if e.get("is_nvidia") is not want:
            mism.append(f"{b}: 期望 is_nvidia={want}，实测 {e.get('is_nvidia')}（GL={e.get('gl')}）")
    report["label_integrity"] = {"ok": not mism, "mismatches": mism}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = args.label or time.strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"ab_{args.case}_{stamp}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print("-" * 78)
    for k, v in report["summary"].items():
        print(f"  {k:<26} agg_median={v['aggregate_ctrl_steps_per_s_median']} "
              f"per_worker={v['per_worker_mean_median']} n={v['n']} spread={v['spread_pct']}% "
              f"speedup_vs_osmesa_w1={v.get('speedup_vs_osmesa_w1')} "
              f"scaling_eff={v.get('scaling_efficiency_vs_w1')}")
    print(f"  后端标签完整性: {'OK' if report['label_integrity']['ok'] else report['label_integrity']['mismatches']}")
    print(f"  loadavg: before={report['cpu_stat_before'].get('loadavg')} "
          f"after={report['cpu_stat_after'].get('loadavg')}")
    print(f"  nr_throttled: before={report['cpu_stat_before'].get('nr_throttled')} "
          f"after={report['cpu_stat_after'].get('nr_throttled')}")
    print(f"  产物: {out_path}")
    return 0 if report["label_integrity"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
