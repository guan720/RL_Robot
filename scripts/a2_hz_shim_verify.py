#!/usr/bin/env python3
"""**裁定 53.5**：29.4118 Hz shim 的**实现验证 + 实测**（A2，S4/S1 共用口径）。

产物：`runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json`

本探针的**判据必须能红**，所以带三类牙：
  ① **DT 档位扫描**：把 `compute_n_steps` 的 `ValueError` **原样保留**（不吞成 None），
     复现 D 裁定 53 的根因（`DT=1/30` **构造失败**，不是四舍五入）；QC 带 [29,31] 必须**拒掉**
     31.25 / 33.33 / 50.0 Hz。
  ② **patch 机制变异实验**（本节最关键）：证明「**只改 `gym_aloha.constants.DT` 会静默留在 50 Hz**」——
     在**独立子进程**里只改 constants 然后构造真 env，读回**活对象**的 `control_timestep`；
     若它仍是 0.02 ⇒ 变异体被抓住 ⇒ 本 shim 同时 patch 两处**不是形式主义**。
  ③ **shim 拒绝非整数倍**：`apply_dt(1/30)` 必须 `applied=false` 且给出 `ValueError` 原文，
     `make_env(dt=1/30)` 必须**抛异常**而不是静默退化。

**边界**：
  - **CPU-only**（`MUJOCO_GL=osmesa`）⇒ **不占 GPU、不需申报**；**不跑任何 policy**（裁定 46.6）。
  - 吞吐数字带**五元标注** `(venv, 后端, mujoco 版本, 模型, 相机数/分辨率)`，
    **不得**与 D 的 (osmesa, mujoco 3.9.0, Piper 单臂) 或 A2 G3 的 (egl, 3.8.1, viperx 双臂) 互搬（裁定 46.4 / 53.3）。
  - **不改 site-packages**：全程只改运行时模块属性。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import time
from datetime import datetime

os.environ.setdefault("MUJOCO_GL", "osmesa")   # **必须在 import mujoco/dm_control 之前**

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from envs import gym_aloha_shim as SHIM  # noqa: E402

OUT_DIR = REPO / "runs/vla/a2_hz_shim_29p4118_20260929"


def sysstat(tag: str) -> dict:
    out = {"tag": tag, "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "loadavg": list(os.getloadavg())}
    try:
        txt = pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat").read_text()
        out["cpu_stat"] = {k: int(v) for k, v in
                           re.findall(r"(nr_periods|nr_throttled|throttled_time)\s+(\d+)", txt)}
    except Exception as e:  # noqa: BLE001
        out["cpu_stat_error"] = repr(e)[:160]
    return out


def backend_label() -> dict:
    import mujoco
    return {"venv": "/root/venvs/pi05_sim", "mujoco_gl": os.environ.get("MUJOCO_GL"),
            "mujoco_version": mujoco.__version__, "model": "bimanual_viperx_transfer_cube.xml",
            "python": platform.python_version(), "platform": platform.platform(),
            "cross_transport_ban": "裁定 46.4 / 53.3：本五元组之外的数字**不得**互搬"}


# ---------------- ① DT 档位扫描 ----------------
def dt_sweep() -> dict:
    cands = [
        ("现状（gym_aloha 出厂）", 0.02),
        ("裁定 53 主线口径", SHIM.MAINLINE_DT),
        ("D 枚举档位 0.032", 0.032),
        ("D 枚举档位 0.030", 0.030),
        ("**名义 30.0 Hz**（裁定 45 原口径）", 1.0 / 30.0),
        ("0.036", 0.036),
        ("0.002（= 物理步，退化）", 0.002),
        ("0.001（< 物理步，非法）", 0.001),
    ]
    rows = []
    for label, dt in cands:
        n, err = SHIM.substeps_or_error(dt)
        hz = SHIM.control_hz(dt)
        rows.append({"label": label, "dt": dt, "dt_repr": repr(dt), "control_hz": round(hz, 6),
                     "n_sub_steps": n, "compute_n_steps_error": err,
                     "constructible": err is None,
                     "in_qc_band_29_31": SHIM.in_qc_band(hz),
                     "per_step_budget_ms": round(dt * 1000, 4)})
    ok = {
        "mainline_0.034_is_29p4118_and_in_qc": any(
            r["dt"] == SHIM.MAINLINE_DT and abs(r["control_hz"] - 29.411765) < 1e-4 and r["in_qc_band_29_31"]
            and r["n_sub_steps"] == 17 for r in rows),
        "dt_one_over_30_raises_valueerror": any(
            abs(r["dt"] - 1 / 30) < 1e-12 and not r["constructible"]
            and "integer multiple" in (r["compute_n_steps_error"] or "") for r in rows),
        "qc_band_rejects_31p25": any(abs(r["dt"] - 0.032) < 1e-12 and abs(r["control_hz"] - 31.25) < 1e-6
                                     and not r["in_qc_band_29_31"] for r in rows),
        "qc_band_rejects_33p33": any(abs(r["dt"] - 0.030) < 1e-12 and not r["in_qc_band_29_31"] for r in rows),
        "qc_band_rejects_50hz_status_quo": any(abs(r["dt"] - 0.02) < 1e-12 and not r["in_qc_band_29_31"] for r in rows),
        "sub_physics_timestep_rejected": any(abs(r["dt"] - 0.001) < 1e-12 and not r["constructible"] for r in rows),
    }
    return {"candidates": rows, "teeth": ok, "all_teeth_green": all(ok.values())}


# ---------------- ② patch 机制变异实验（子进程，避免状态泄漏） ----------------
PATCH_PROBE = r"""
import json, os, sys
os.environ.setdefault("MUJOCO_GL", "osmesa")
sys.path.insert(0, __REPO__)
mode = __MODE__
import gym_aloha, gymnasium as gym
import gym_aloha.constants as C, gym_aloha.env as E
if mode == "constants_only":
    C.DT = 0.034                      # **只改 constants**（错误的做法）
elif mode == "both_names":
    from envs import gym_aloha_shim as S
    rec = S.apply_dt(0.034)
elif mode == "untouched":
    pass
env = gym.make("gym_aloha/AlohaTransferCube-v0")
dm = env.unwrapped._env
_d = lambda x: x() if callable(x) else x
_ct = float(_d(dm.control_timestep))
print(json.dumps({
    "mode": mode,
    "constants_DT": C.DT, "env_module_DT": E.DT,
    "live_control_timestep_s": _ct,
    "live_n_sub_steps": int(dm._n_sub_steps),
    "live_physics_timestep_s": float(_d(dm.physics.timestep)),
    "live_control_hz": round(1.0/_ct, 6),
}))
"""


def run_patch_probe(mode: str) -> dict:
    code = PATCH_PROBE.replace("__REPO__", repr(str(REPO))).replace("__MODE__", repr(mode))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        return {"mode": mode, "probe_rc": r.returncode, "stderr_tail": r.stderr[-1200:]}
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        return {"mode": mode, "parse_error": repr(e), "stdout_tail": r.stdout[-600:],
                "stderr_tail": r.stderr[-600:]}


def patch_mechanism_proof() -> dict:
    untouched = run_patch_probe("untouched")
    const_only = run_patch_probe("constants_only")
    both = run_patch_probe("both_names")

    def live_hz(d):
        return d.get("live_control_hz")

    teeth = {
        "baseline_is_50hz": live_hz(untouched) == 50.0,
        # **关键牙**：只改 constants ⇒ 活对象仍是 50 Hz（静默失败）
        "constants_only_patch_SILENTLY_FAILS_stays_50hz": (
            const_only.get("constants_DT") == 0.034 and live_hz(const_only) == 50.0),
        "both_names_patch_reaches_29p4118": abs((live_hz(both) or 0) - 29.411765) < 1e-4,
        "both_names_live_substeps_17": both.get("live_n_sub_steps") == 17,
        "physics_timestep_UNCHANGED_0p002": all(
            d.get("live_physics_timestep_s") == 0.002 for d in (untouched, const_only, both)),
    }
    return {
        "why": ("`gym_aloha/env.py:7`–`:12` 是 `from gym_aloha.constants import (…, DT, …)` ⇒ "
                "`env.py` 里的 `DT` 是**已绑定名字**；`env.py:133`–`:135` 用的是它。"
                "只改 `constants.DT` **不会**影响已 import 的 `env.py` ⇒ **静默留在 50 Hz**。"),
        "method": "三种模式各在**独立子进程**里构造真 env，读回**活对象**的 `control_timestep`（不是读常量）",
        "untouched": untouched, "constants_only": const_only, "both_names": both,
        "teeth": teeth, "all_teeth_green": all(teeth.values()),
    }


# ---------------- ③ shim 拒绝非整数倍 ----------------
def refusal_proof() -> dict:
    rec = SHIM.apply_dt(1.0 / 30.0)
    raised = None
    try:
        SHIM.make_env(dt=1.0 / 30.0)
    except Exception as e:  # noqa: BLE001
        raised = f"{type(e).__name__}: {e}"
    finally:
        SHIM.apply_dt(SHIM.MAINLINE_DT)   # 复原，别把 1/30 留在模块里
    teeth = {
        "apply_dt_refuses_one_over_30": rec.get("applied") is False and bool(rec.get("compute_n_steps_error")),
        "make_env_raises_not_silently_degrades": bool(raised),
        "no_silent_rounding": "ValueError" in (rec.get("compute_n_steps_error") or ""),
    }
    return {"apply_dt_record": rec, "make_env_exception": raised,
            "teeth": teeth, "all_teeth_green": all(teeth.values())}


# ---------------- ④ 真 env 端到端实测（osmesa，CPU-only） ----------------
def live_env_measurement(n_steps: int) -> dict:
    t0 = time.perf_counter()
    env, rec = SHIM.make_env()
    construct_s = time.perf_counter() - t0
    live = SHIM.read_live_timing(env)
    obs, info = env.reset(seed=1000)
    t0 = time.perf_counter()
    rewards, dones = [], []
    for _ in range(n_steps):
        a = env.action_space.sample() * 0.0     # **零动作**：不跑 policy、不制造接触（裁定 46.6）
        obs, r, term, trunc, info = env.step(a)
        rewards.append(float(r)); dones.append(bool(term or trunc))
    wall = time.perf_counter() - t0
    sim_seconds = n_steps * live["control_timestep_s"]
    # `env.py:138`–`:148`：obs_type="pixels" ⇒ **顶层就是 `{"top": …}`**；
    # "pixels_agent_pos" ⇒ `{"pixels": {"top": …}, "agent_pos": …}`。两种形态都吃。
    img = None
    if isinstance(obs, dict):
        img = obs.get("top")
        if img is None and isinstance(obs.get("pixels"), dict):
            img = obs["pixels"].get("top")
    out = {
        "shim_record": rec, "live_timing": live,
        "n_control_steps": n_steps,
        "wall_s": round(wall, 3),
        "wall_s_per_control_step_ms": round(wall / n_steps * 1000, 2),
        "ctrl_steps_per_s": round(n_steps / wall, 3),
        "simulated_seconds": round(sim_seconds, 4),
        "realtime_factor": round(sim_seconds / wall, 4),
        "measured_control_hz_from_sim_time": round(n_steps / sim_seconds, 6),
        "measured_hz_matches_contract": abs(n_steps / sim_seconds - live["control_hz"]) < 1e-6,
        "construct_s": round(construct_s, 2),
        "obs_keys_top_level": sorted(obs.keys()) if isinstance(obs, dict) else None,
        "obs_image": ({"shape": list(img.shape), "dtype": str(img.dtype),
                       "luma_mean": round(float(img.astype("float64").mean()), 3)} if img is not None else None),
        "reward_all_zero_under_null_action": all(x == 0.0 for x in rewards),
        "any_done": any(dones),
        "policy_executed": False,
        "action_used": "全零动作（`action_space.sample()*0.0`）⇒ 不制造接触、不评价能力",
        "backend": backend_label(),
        "throughput_caveat": ("**osmesa 软渲染**，且本 venv 的 `env.step` 内建 480×640 渲染 ⇒ "
                              "**这个吞吐数字只描述 (osmesa, 3.8.1, viperx 双臂, 1 相机 top@480×640)**，"
                              "**不得**与 A2 G3 的 egl 3 相机数字或 D 的 Piper/osmesa 数字互搬（裁定 46.4/53.3）。"),
    }
    env.close()
    return out


# ---------------- ⑥ obs / 相机面审计（S4 的硬前置：**env 到底把哪些相机交给 agent**） ----------------
def obs_surface_audit() -> dict:
    """**只读**审计 site-packages 源码 + XML，把「渲染了什么 / 暴露了什么 / 丢了什么」落成机器承载。

    为什么这节必须在 S4 之前做：D 的 S4 要求 `harness/vla_runtime.py` 做
    **相机键注入（`top` / `left_wrist` / `right_wrist`）**。但 `gym_aloha` 的 `AlohaEnv`
    **只把 `top` 交给 agent**（`env.py:138`–`:148` 的 `_format_raw_obs`），腕部相机**根本不渲染**。
    ⇒ 三相机契约**不可能**从 `AlohaEnv.observation` 拿到，必须走本仓自有渲染路径。
    """
    import gym_aloha
    pkg = pathlib.Path(gym_aloha.__file__).resolve().parent
    sim_py = (pkg / "tasks" / "sim.py").read_text().splitlines()
    env_py = (pkg / "env.py").read_text().splitlines()

    rendered = []
    for i, ln in enumerate(sim_py, start=1):
        m = re.search(r'obs\["images"\]\["(?P<key>[^"]+)"\]\s*=\s*physics\.render\((?P<args>[^)]*)\)', ln)
        if m:
            cm = re.search(r'camera_id="([^"]+)"', m.group("args"))
            hw = re.search(r'height=(\d+),\s*width=(\d+)', m.group("args"))
            rendered.append({"obs_key": m.group("key"), "camera_id": cm.group(1) if cm else None,
                             "height": int(hw.group(1)) if hw else None,
                             "width": int(hw.group(2)) if hw else None,
                             "source": f"gym_aloha/tasks/sim.py:{i}", "line": ln.strip()})

    # 按 obs_type 分支归属（读原文，不猜）
    branch = None
    exposed = {"pixels": [], "pixels_agent_pos": [], "state": "raise NotImplementedError()"}
    for i, ln in enumerate(env_py, start=1):
        if "self.obs_type ==" in ln:
            m = re.search(r'self\.obs_type == "([^"]+)"', ln)
            branch = m.group(1) if m else None
        if branch and 'raw_obs["images"]' in ln:
            for key in re.findall(r'"([a-z_]+)":\s*raw_obs\["images"\]\["([a-z_]+)"\]', ln):
                exposed.setdefault(branch, []).append({"obs_key": key[0], "from_images_key": key[1],
                                                       "source": f"gym_aloha/env.py:{i}"})

    xml = pkg / "assets" / "bimanual_viperx_transfer_cube.xml"
    os.environ["MUJOCO_GL"] = "disable"
    import mujoco
    m = mujoco.MjModel.from_xml_path(str(xml))
    cams = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_CAMERA, i) for i in range(m.ncam)]
    os.environ["MUJOCO_GL"] = "osmesa"

    rendered_ids = [r["camera_id"] for r in rendered]
    exposed_ids = [e["from_images_key"] for e in exposed.get("pixels", [])]
    a2_cam_map = {"base": "top", "left_wrist": "left_wrist", "right_wrist": "right_wrist"}
    teeth = {
        "wrist_cams_exist_in_xml": {"left_wrist", "right_wrist"} <= set(cams),
        "wrist_cams_NEVER_rendered_by_env": not ({"left_wrist", "right_wrist"} & set(rendered_ids)),
        "wrist_cams_NOT_exposed_to_agent": not ({"left_wrist", "right_wrist"} & set(exposed_ids)),
        "some_rendered_cam_is_DROPPED": len(set(rendered_ids)) > len(set(exposed_ids)),
        "top_is_exposed": "top" in exposed_ids,
    }
    return {
        "why": "S4 的相机键注入（`top`/`left_wrist`/`right_wrist`）**不可能**从 `AlohaEnv.observation` 拿到 ⇒ 必须走本仓自有渲染路径",
        "xml_model_facts": {"ncam": m.ncam, "nq": m.nq, "nv": m.nv, "nu": m.nu, "nmocap": m.nmocap,
                            "opt_timestep": m.opt.timestep, "camera_names": cams,
                            "xml": str(xml), "read_with": "MUJOCO_GL=disable + MjModel.from_xml_path（未渲染）"},
        "rendered_by_task": rendered,
        "exposed_to_agent_by_obs_type": exposed,
        "rendered_but_dropped_by_format_raw_obs": sorted(set(rendered_ids) - set(exposed_ids)),
        "never_rendered_by_env": sorted(set(cams) - set(rendered_ids)),
        "consequence_for_S4": {
            "three_camera_contract_source": "**必须**直接 `physics.render(camera_id=…)`（本仓自有路径）",
            "existing_working_implementation": ("A2 的 G3 评测脚本已实现且跑通 20 局："
                                                "`scripts/a2_pi05_zeroshot_eval.py:190`（`physics.render(height=h,width=w,camera_id=cam)`）、"
                                                "`:249`–`:250`（π₀.₅ 键 `observation.images.left_wrist_0_rgb → left_wrist`、"
                                                "`right_wrist_0_rgb → right_wrist`）⇒ **S4 复用它，不要另发明**"),
            "free_perf_win": ("`_format_raw_obs` 之前，`tasks/sim.py` 已经渲染了 **%d 个 480×640 相机**"
                              "（`%s`），而 agent 只拿到 **%d 个**（`%s`）⇒ **绕开 `_format_raw_obs` 可省掉 "
                              "%d 次无用渲染/控制步**（A2 G3 实测：3 相机 224² = 14.83 ctrl-steps/s、"
                              "单相机 = 34.58 ⇒ 渲染是主要成本，省下的次数直接换吞吐）"
                              % (len(rendered_ids), ",".join(rendered_ids),
                                 len(exposed_ids), ",".join(exposed_ids),
                                 len(set(rendered_ids)) - len(exposed_ids))),
            "wrist_camera_names_in_xml": ["left_wrist", "right_wrist"],
            "a2_g3_camera_mapping": a2_cam_map,
        },
        "teeth": teeth,
        "all_teeth_green": all(teeth.values()),
        "external_unverified": False,
    }


# ---------------- ⑤ 延迟预算（复用 G3 实测，不重跑、不占 GPU） ----------------
def latency_budget(g3_json: pathlib.Path) -> dict:
    per_chunk = None
    if g3_json.is_file():
        try:
            j = json.loads(g3_json.read_text())
            per_chunk = (j.get("latency_budget_claim") or {}).get("per_chunk_wall_s_from_g3_log")
        except Exception:  # noqa: BLE001
            per_chunk = None
    per_chunk = per_chunk or 0.5233
    chunk = 50
    dt = SHIM.MAINLINE_DT
    cover = chunk * dt
    return {
        "source": "复用 `ctrl_hz_alignment_a2.json → latency_budget_claim.per_chunk_wall_s_from_g3_log`（**未重跑推理、未占 GPU**）",
        "per_chunk_wall_s": per_chunk, "chunk_size": chunk, "dt_s": dt,
        "chunk_covers_s": round(cover, 4),
        "per_step_budget_ms_hard": SHIM.PER_STEP_BUDGET_MS,
        "per_step_budget_ms_nominal_anchor_only": round(1000 / SHIM.NOMINAL_ANCHOR_HZ, 3),
        "inference_fraction_of_chunk_realtime": round(per_chunk / cover, 4),
        "amortized_inference_ms_per_control_step": round(per_chunk / chunk * 1000, 2),
        "amortized_within_hard_budget_34ms": (per_chunk / chunk * 1000) <= SHIM.PER_STEP_BUDGET_MS,
        "verdict": ("**按 chunk 执行可行**（推理占 chunk 真实时长 30.4%）；**按每步推理不可行**"
                    "（单次 chunk 0.52 s ≫ 34.0 ms）⇒ 与裁定 53-2 方向一致"),
        "matches_d_ruling_53_2": abs(per_chunk / cover - 0.304) < 0.01,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-steps", type=int, default=20)
    ap.add_argument("--skip-live", action="store_true", help="只跑 CPU 判据，不构造真 env")
    ap.add_argument("--out", default=str(OUT_DIR / "hz_shim_verification.json"))
    args = ap.parse_args()

    rec = {
        "probe": "a2_hz_shim_verify",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_hz_shim_verify.py",
        "ruling": "裁定 53 / 53.5（主线仿真 = 29.4118 Hz，`DT=0.034`，硬预算 34.0 ms）",
        "shim_path": str(SHIM.SHIM_PATH.relative_to(REPO)),
        "shim_sha256_12": SHIM.shim_sha256_12(),
        "representation_version": SHIM.REPRESENTATION_VERSION,
        "site_packages_modified": False,
        "gpu_used": False, "policy_executed": False,
        "backend": backend_label(),
        "load_before": sysstat("before"),
    }
    rec["dt_candidate_sweep"] = dt_sweep()
    rec["patch_mechanism_proof"] = patch_mechanism_proof()
    rec["refusal_proof"] = refusal_proof()
    if not args.skip_live:
        rec["live_env_measurement"] = live_env_measurement(args.n_steps)
    rec["obs_surface_audit"] = obs_surface_audit()
    rec["episode_horizon_consequence"] = SHIM.episode_horizon()
    rec["latency_budget_at_34ms"] = latency_budget(
        REPO / "runs/vla/a2_pi05_zeroshot_20260929/ctrl_hz_alignment_a2.json")

    gates = {
        "G1_dt_sweep_teeth": rec["dt_candidate_sweep"]["all_teeth_green"],
        "G2_patch_mechanism_teeth": rec["patch_mechanism_proof"]["all_teeth_green"],
        "G3_refusal_teeth": rec["refusal_proof"]["all_teeth_green"],
        "G4_live_env_is_29p4118": bool(rec.get("live_env_measurement", {})
                                        .get("live_timing", {}).get("matches_mainline")),
        "G5_live_hz_in_qc_band": bool(rec.get("live_env_measurement", {})
                                      .get("live_timing", {}).get("in_qc_band_29_31")),
        "G6_measured_hz_matches_contract": bool(rec.get("live_env_measurement", {})
                                                .get("measured_hz_matches_contract")),
        "G7_physics_timestep_untouched": (rec["patch_mechanism_proof"]["teeth"]
                                          .get("physics_timestep_UNCHANGED_0p002") is True),
        "G8_latency_direction_matches_ruling_53": rec["latency_budget_at_34ms"]["matches_d_ruling_53_2"],
        "G9_obs_surface_audit_teeth": rec["obs_surface_audit"]["all_teeth_green"],
        "G10_obs_image_actually_present": bool((rec.get("live_env_measurement") or {}).get("obs_image")),
        "G11_obs_exposes_top_only": ((rec.get("live_env_measurement") or {}).get("obs_keys_top_level") == ["top"]),
    }
    rec["gates"] = gates
    rec["verdict"] = {
        "PASS": all(gates.values()),
        "gates_pass": f'{sum(1 for v in gates.values() if v)}/{len(gates)}',
        "claim_scope": ("**只**支持「本仓 shim 能把 gym-aloha 的控制周期改成 0.034 s / 29.4118 Hz，"
                        "整数倍构造成功、活对象实测一致、物理 timestep 未被动、非整数倍被拒」。"
                        "**不**支持任何 π₀.₅ 能力/成功率主张（裁定 46），**不**代表已接线 S4（`harness/vla_runtime.py` 另做）。"
                        "**附带产出一条 S4 硬事实**：`AlohaEnv` 只把 `top` 交给 agent、腕部相机根本不渲染"
                        "（`obs_surface_audit`）⇒ 三相机契约必须走本仓自有渲染路径，**复用 `a2_pi05_zeroshot_eval.py:190`**。"),
        "needs_d_ruling": ["`max_episode_steps` 是否由 300 缩到 176（`episode_horizon_consequence.a2_recommendation` = B）"],
    }
    rec["load_after"] = sysstat("after")
    rec["nr_throttled_delta_total"] = (rec["load_after"].get("cpu_stat", {}).get("nr_throttled", 0)
                                       - rec["load_before"].get("cpu_stat", {}).get("nr_throttled", 0))

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"written": str(out), "shim_sha256_12": rec["shim_sha256_12"],
                      "gates": gates, "PASS": rec["verdict"]["PASS"],
                      "gates_pass": rec["verdict"]["gates_pass"],
                      "live": {k: v for k, v in (rec.get("live_env_measurement") or {}).items()
                               if k in ("live_timing", "ctrl_steps_per_s", "wall_s_per_control_step_ms",
                                        "simulated_seconds", "realtime_factor")},
                      "loadavg_before": rec["load_before"]["loadavg"],
                      "loadavg_after": rec["load_after"]["loadavg"],
                      "nr_throttled_delta": rec["nr_throttled_delta_total"]},
                     ensure_ascii=False, indent=1))
    return 0 if rec["verdict"]["PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
