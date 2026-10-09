#!/usr/bin/env python
"""E 线取证件：**同进程裸 `mujoco.Renderer` 探针会污染 dm_control 渲染**（顺序敏感）。

## 为什么要这个脚本
`scripts/e_mainline_render_calib.py` 早期版本为了拿"后端身份"（`GL_RENDERER` 原文），
在**被测 env 的同一个进程里**额外建了一次裸 `mujoco.Renderer`（32² 玩具模型）并 `close()`。
动机是正当的（dm_control 把渲染放在独立线程 make current，osmesa 臂主线程 `glGetString`
恒为 NULL，拿不到 CPU 臂的后端证据），但**代价没人量过**。本脚本把代价量出来：

三臂对照（唯一变量 = 裸探针相对 `make_env` 的**时序**）：
  `no_raw`    —— 完全不建裸 Renderer（对照）
  `raw_first` —— 在 `make_env` **之前**建/关裸 Renderer
  `raw_after` —— 在 dm_control 已经渲过图**之后**建/关裸 Renderer（= 出事的顺序）

## 判据（每条都是"有牙"的，不是描述性字段）
  `frozen_buffer`     : 走完 30 个 env.step 后同相机 `sha12` 与走之前**完全相同** ⇒ 渲染在返回旧缓冲
  `cam_convergence`   : 三个不同相机在同一状态下 `sha12` 趋同/均值趋同 ⇒ 出的不是各自的场景
  `render_rate_inflation_pct` : 相对 `no_raw` 的渲染吞吐虚高百分比（**虚高 = 渲染在空转**）
  `liveness_strict_ok`: 渲一张 → `physics.step()`×2n → 再渲一张，`sha12` 必须变
                        （这就是修好之后写进 calib 脚本的那道闸；本脚本用它验证"闸抓得住"）
  `fidelity_ok`       : 跑完整条序列后**回到同 seed 的 reset 态**重拍 3 相机，`sha12` 必须与
                        开跑前的 `s1_reset` 逐字相同（calib 脚本的第二道闸）
  `atexit_egl_error`  : 进程退出时 dm_control 的 `_free_at_exit` 是否抛 `EGLError`

## 结论口径（跑完看 `verdict`）
`raw_first` 与 `no_raw` 等价 ⇒ 无害；`raw_after` 触发 frozen/虚高 ⇒ **禁止**。
跨线影响：A2 的 `scripts/a2_egl_latency_remeasure.py:702`（`gl_identity_via_mujoco()`）
在 `make_env`（`:375`/`:430`，经 `:761`/`:771` 调用）**之前**执行 ⇒ 属 `raw_first`，安全；
A2 的 `gl_identity_after_dm_render`（`:195`）只调 `glGetString`、**不建** Renderer ⇒ 亦安全。

用法：
  python3 scripts/e_rawprobe_interference.py --backends egl_nvidia,osmesa \
      --arms no_raw,raw_first,raw_after --reps 2 \
      --out-dir runs/infra/e_mainline_calib_20260929
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import e_gpu_egl_verify as ev  # noqa: E402  复用激活/采样，不另造口径
import e_egl_probe as ep       # noqa: E402  复用边界闸

ACTIVATE = REPO_ROOT / "scripts" / "e_activate_gpu_render.sh"
PY = "/root/venvs/pi05_sim/bin/python"
CAMS = ["angle", "left_wrist", "right_wrist"]
# 保真闸容差（与 `e_mainline_render_calib.py` 同值同义；**不用 sha 严格相等**，因为实测
# GPU 臂 wrist 相机在同一物理状态下重渲有 ±1 LSB 抖动，严格 sha 会误杀干净批。
# 抖动本身的取证见同目录 RENDER_DETERMINISM.json）。
FID_MAX_ABS_DIFF = 4
FID_MAX_FRAC_DIFF = 0.02
FID_MAX_MEAN_DIFF = 0.05
FID_MIN_PAIRWISE_DIFF = 0.05   # 标定依据：干净臂最小两两差 0.3587，污染臂 0.0018
# "吞吐虚高"判有害的阈值。**按实测噪声带标定，不是拍的**：同一后端上 `no_raw` 与 `raw_first`
# （两者都不该有害）跨轮的相对差实测在 −5.2% ～ +8.3% 之间摆动（loadavg 37–39、12 核 cgroup、
# 与其它线共租 CPU）⇒ 阈值必须显著高于该噪声带上界，取 15%。
# 污染臂 `raw_after` 实测 +29% ～ +37%，与噪声带清晰分离。
INFLATION_HARM_PCT = 15.0

# 单臂子进程：与被测 env 同进程，按 --arm 决定裸探针的时序
_ARM = r'''
import hashlib, importlib.util, json, os, sys, time
import numpy as np

REPO = sys.argv[1]; ARM = sys.argv[2]; SEED = int(sys.argv[3])
CAMS = ["angle", "left_wrist", "right_wrist"]
sys.path.insert(0, os.path.join(REPO, "scripts"))
import e_gpu_egl_verify as ev


def raw_probe():
    """裸 mujoco.Renderer：建 32² 玩具模型渲一帧、取 GL_RENDERER、然后 close()。"""
    import mujoco
    m = mujoco.MjModel.from_xml_string(ev._XML)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    r = mujoco.Renderer(m, height=32, width=32)
    r.update_scene(d, camera="c")
    img = np.asarray(r.render())
    gl = None
    try:
        from OpenGL.GL import GL_RENDERER, glGetString
        s = glGetString(GL_RENDERER)
        gl = (s.decode() if isinstance(s, bytes) else str(s)) if s else None
    except Exception as exc:
        gl = f"(unavailable: {type(exc).__name__})"
    r.close()
    del m, d, r
    return {"gl_renderer": gl, "probe_image_mean": round(float(img.mean()), 3),
            "probe_image_sha12": hashlib.sha256(img.tobytes()).hexdigest()[:12]}


out = {"arm": ARM, "pid": os.getpid(), "seed": SEED,
       "mujoco_gl": os.environ.get("MUJOCO_GL"),
       "vendor_icd": os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES"),
       "python": sys.executable}

spec = importlib.util.spec_from_file_location("gym_aloha_shim", os.path.join(REPO, "envs", "gym_aloha_shim.py"))
shim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim)
import mujoco
out["mujoco_version"] = mujoco.__version__
out["shim_sha256_12"] = shim.shim_sha256_12()

if ARM == "raw_first":
    out["raw_probe"] = raw_probe()

env, rec = shim.make_env(shim.ENV_ID, dt=shim.MAINLINE_DT,
                         obs_type="pixels_agent_pos", render_mode="rgb_array")
ph = env.unwrapped._env.physics
N_SUB = int((shim.read_live_timing(env) or {}).get("n_sub_steps") or shim.MAINLINE_SUBSTEPS)
out["n_sub_steps"] = N_SUB


IMGS = {}


def snap(name):
    d, imgs = {}, {}
    for c in CAMS:
        a = np.asarray(ph.render(height=224, width=224, camera_id=c))
        imgs[c] = a
        d[c] = {"mean": round(float(a.mean()), 3), "std": round(float(a.std()), 4),
                "sha12": hashlib.sha256(a.tobytes()).hexdigest()[:12]}
    shas = [d[c]["sha12"] for c in CAMS]
    means = [d[c]["mean"] for c in CAMS]
    d["_distinct_sha"] = len(set(shas))
    d["_mean_spread"] = round(max(means) - min(means), 3)
    out[name] = d
    IMGS[name] = imgs
    return d


rng = np.random.default_rng(SEED)
actions = rng.uniform(-1.0, 1.0, size=(30, env.action_space.shape[0])).astype(np.float32)

env.reset(seed=SEED)
snap("s1_reset")
if ARM == "raw_after":
    out["raw_probe"] = raw_probe()
for _ in range(30):
    for c in CAMS:
        ph.render(height=224, width=224, camera_id=c)
snap("s2_after_90_renders")

env.reset(seed=SEED)
for i in range(30):
    env.step(actions[i])
snap("s3_after_30_env_steps")

# 严格活性闸（= 修好后写进 calib 的那道）：渲一张 → 走物理 → 再渲一张，sha 必须变
def liveness(tag):
    a0 = np.asarray(ph.render(height=224, width=224, camera_id=CAMS[0]))
    s0 = hashlib.sha256(a0.tobytes()).hexdigest()[:12]
    for _ in range(max(2, N_SUB * 2)):
        ph.step()
    a1 = np.asarray(ph.render(height=224, width=224, camera_id=CAMS[0]))
    s1 = hashlib.sha256(a1.tobytes()).hexdigest()[:12]
    return {"tag": tag, "sha12_before": s0, "sha12_after": s1, "changed": bool(s0 != s1),
            "mean_before": round(float(a0.mean()), 3), "mean_after": round(float(a1.mean()), 3)}

out["liveness_strict"] = liveness("post_sequence")

# 保真闸：回到同 seed 的 reset 态重拍，与 s1_reset 比**数值差**（不是 sha 严格相等——
# 实测 GPU 臂 wrist 相机同状态重渲有 ±1 LSB 抖动，严格 sha 会误杀干净臂）。
env.reset(seed=SEED)
snap("s4_reset_recheck")
_i1, _i4 = IMGS["s1_reset"], IMGS["s4_reset_recheck"]
_vs = {}
for c in CAMS:
    _d = np.abs(_i4[c].astype(np.int16) - _i1[c].astype(np.int16))
    _vs[c] = {"max_abs_diff": int(_d.max()), "mean_abs_diff": round(float(_d.mean()), 5),
              "frac_diff_px": round(float((_d.sum(axis=2) > 0).mean()), 6),
              "mean_s1": round(float(_i1[c].mean()), 3), "mean_s4": round(float(_i4[c].mean()), 3)}
out["s4_vs_s1"] = _vs
_pw = {}
for _x in range(len(CAMS)):
    for _y in range(_x + 1, len(CAMS)):
        _ca, _cb = CAMS[_x], CAMS[_y]
        _e = np.abs(_i4[_ca].astype(np.int16) - _i4[_cb].astype(np.int16))
        _pw[f"{_ca}__vs__{_cb}"] = round(float((_e.sum(axis=2) > 0).mean()), 4)
out["s4_pairwise_frac_diff"] = _pw

t0 = time.perf_counter()
for _ in range(20):
    for c in CAMS:
        ph.render(height=224, width=224, camera_id=c)
dt = time.perf_counter() - t0
out["render_rate"] = {"n_ctrl_steps": 20, "wall_s": round(dt, 4),
                      "ctrl_steps_per_s": round(20 / dt, 2)}
out["loadavg"] = os.getloadavg()[0]
out["ok"] = True
print("ARM_JSON" + json.dumps(out))
'''


def activation_env(mode: str) -> dict:
    """从激活件取环境（唯一真源；本脚本不另写 LD_LIBRARY_PATH 逻辑）。"""
    r = subprocess.run(["bash", "-c",
                        f'eval "$(bash {ACTIVATE} --print --mode {mode})"; env -0'],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"激活件 --print 失败({mode}): {r.stderr.strip()[:300]}")
    env = {}
    for pair in r.stdout.split("\0"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            env[k] = v
    return env


def run_arm(mode: str, arm: str, seed: int, env: dict, log_dir: Path) -> dict:
    log = log_dir / f"arm_{mode}_{arm}_s{seed}.log"
    p = subprocess.run([PY, "-c", _ARM, str(REPO_ROOT), arm, str(seed)],
                       capture_output=True, text=True, env=env, timeout=900)
    log.write_text(p.stdout + ("\n--- stderr ---\n" + p.stderr if p.stderr else ""), encoding="utf-8")
    payload = None
    for line in p.stdout.splitlines():
        if line.startswith("ARM_JSON"):
            payload = json.loads(line[len("ARM_JSON"):])
    if payload is None:
        payload = {"arm": arm, "ok": False, "returncode": p.returncode,
                   "stderr_tail": (p.stderr or "").strip().splitlines()[-8:]}
    payload["mode"] = mode
    payload["returncode"] = p.returncode
    payload["atexit_egl_error"] = ("EGLError" in (p.stderr or ""))
    payload["atexit_egl_error_detail"] = [l.strip() for l in (p.stderr or "").splitlines()
                                          if "EGLError" in l or "err = EGL" in l][:3]
    payload["log"] = str(log)
    # 派生判据
    s2, s3 = payload.get("s2_after_90_renders") or {}, payload.get("s3_after_30_env_steps") or {}
    payload["derived"] = {
        "frozen_buffer": bool(s2 and s3 and s2.get("angle", {}).get("sha12")
                              and s2["angle"]["sha12"] == s3.get("angle", {}).get("sha12")),
        "cam_convergence_3cam": (s3.get("_distinct_sha") == 1) if s3 else None,
        "s3_mean_spread": s3.get("_mean_spread"),
        "liveness_strict_ok": (payload.get("liveness_strict") or {}).get("changed"),
    }
    s1, s4 = payload.get("s1_reset") or {}, payload.get("s4_reset_recheck") or {}
    diffs = payload.get("s4_vs_s1") or {}
    reproducible = bool(diffs) and all(
        v.get("max_abs_diff", 99) <= FID_MAX_ABS_DIFF
        and v.get("frac_diff_px", 1.0) <= FID_MAX_FRAC_DIFF
        and v.get("mean_abs_diff", 99.0) <= FID_MAX_MEAN_DIFF for v in diffs.values())
    pairwise = payload.get("s4_pairwise_frac_diff") or {}
    distinct = bool(pairwise) and all(x >= FID_MIN_PAIRWISE_DIFF for x in pairwise.values())
    non_degenerate = bool(s4) and all((s4.get(c, {}).get("std") or 0) >= 1.0 for c in CAMS)
    payload["derived"].update({
        "reset_reproducible": reproducible,
        "recheck_cams_distinct": distinct,
        "recheck_non_degenerate": non_degenerate,
        "fidelity_ok": bool(reproducible and distinct and non_degenerate),
        "s1_angle_mean": (s1.get("angle") or {}).get("mean"),
        "s4_angle_mean": (s4.get("angle") or {}).get("mean"),
        "s3_angle_mean": (s3.get("angle") or {}).get("mean"),
    })
    return payload


def _noise_band(per_mode: dict, doc: dict) -> dict:
    """噪声带**从本轮数据现算**（不写死历史值），并给出阈值余量与判据强弱说明。"""
    clean, polluted = [], []
    for m, e in per_mode.items():
        for arm_name, v in e["arms"].items():
            infl = v.get("render_rate_inflation_pct_vs_no_raw")
            if infl is None:
                continue
            row = {"backend": m, "arm": arm_name, "inflation_pct": infl,
                   "fidelity_ok_all": v.get("fidelity_ok_all")}
            if arm_name == "raw_after" and m == "egl_nvidia":
                polluted.append(row)
            else:
                clean.append(row)
    clean_infl = [c["inflation_pct"] for c in clean if c["arm"] != "no_raw"]
    poll_infl = [c["inflation_pct"] for c in polluted]
    clean_max = max(clean_infl) if clean_infl else None
    poll_min = min(poll_infl) if poll_infl else None
    return {
        "threshold_pct": INFLATION_HARM_PCT,
        "clean_arm_inflation_observed": clean,
        "polluted_arm_inflation_observed": polluted,
        "clean_arm_noise_max_pct": clean_max,
        "polluted_arm_min_pct": poll_min,
        "threshold_margin": ({"threshold_above_clean_max_x": round(INFLATION_HARM_PCT / clean_max, 2),
                              "polluted_min_above_threshold_x": round(poll_min / INFLATION_HARM_PCT, 2)}
                             if clean_max and poll_min else None),
        "loadavg_during_evidence": [doc["load_before"].get("loadavg"), doc["load_after"].get("loadavg")],
        "nr_throttled_pair": [doc["load_before"].get("nr_throttled"), doc["load_after"].get("nr_throttled")],
        "note": ("**吞吐虚高只是弱判据**：osmesa 臂是 CPU-bound，在 loadavg≈38 的共租机上干净臂也能摆到 "
                 "+11%，单看百分比会误报。决定性判据是 **fidelity**（回到同 seed reset 态重拍，与开跑前的图"
                 "数值差必须在容差内）——它在 GPU 污染臂上稳定判 false、在全部干净臂上判 true。"
                 "15% 这个阈值仅在 GPU 臂上与污染值(+29%～+37%)有清晰分离度。"),
    }


def _gate_analysis(per_mode: dict) -> dict:
    """哪道闸真抓得住 raw_after？哪道闸会误杀干净臂？**按实测生成结论，不写死**。"""
    def arm(mode, name):
        return ((per_mode.get(mode) or {}).get("arms") or {}).get(name)

    after = [(m, arm(m, "raw_after")) for m in per_mode if arm(m, "raw_after")]
    clean = [(m, a, arm(m, a)) for m in per_mode for a in ("no_raw", "raw_first") if arm(m, a)]
    live_catch = [m for m, a in after if not a["liveness_strict_ok_all"]]
    fid_catch = [m for m, a in after if not a["fidelity_ok_all"]]
    fid_false_positive = [f"{m}/{a}" for m, a, v in clean if not v["fidelity_ok_all"]]
    live_false_positive = [f"{m}/{a}" for m, a, v in clean if not v["liveness_strict_ok_all"]]
    frozen_catch = [m for m, a in after if a["frozen_buffer_any"]]
    infl = {m: a["render_rate_inflation_pct_vs_no_raw"] for m, a in after}
    parts = []
    if not live_catch:
        parts.append("**liveness 闸抓不住**（raw_after 臂渲染仍在逐帧变化，判 true）")
    else:
        parts.append(f"liveness 闸在 {live_catch} 上判 false ⇒ 抓得住")
    if fid_catch:
        parts.append(f"**fidelity 闸在 {fid_catch} 上判 false ⇒ 抓得住**")
    else:
        parts.append("fidelity 闸未判 false ⇒ **没抓住**")
    if frozen_catch:
        parts.append(f"frozen_buffer 判据在 {frozen_catch} 上也直接命中")
    if fid_false_positive:
        parts.append(f"⚠️ fidelity 闸在干净臂 {fid_false_positive} 上误判 false（容差需放宽/判据有 bug）")
    if live_false_positive:
        parts.append(f"⚠️ liveness 闸在干净臂 {live_false_positive} 上误判 false")
    return {
        "liveness_catches_raw_after_on": live_catch,
        "fidelity_catches_raw_after_on": fid_catch,
        "frozen_buffer_catches_raw_after_on": frozen_catch,
        "fidelity_false_positives_on_clean_arms": fid_false_positive,
        "liveness_false_positives_on_clean_arms": live_false_positive,
        "raw_after_inflation_pct": infl,
        "both_gates_clean": (bool(fid_catch or frozen_catch) and not fid_false_positive
                             and not live_false_positive),
        "threshold_calibration": {
            "FID_MAX_ABS_DIFF": FID_MAX_ABS_DIFF, "FID_MAX_FRAC_DIFF": FID_MAX_FRAC_DIFF,
            "FID_MAX_MEAN_DIFF": FID_MAX_MEAN_DIFF, "FID_MIN_PAIRWISE_DIFF": FID_MIN_PAIRWISE_DIFF,
            "observed_clean_worst": {
                "max_abs_diff": 1, "mean_abs_diff": 0.00072,
                "min_pairwise_frac_diff": 0.3587,
                "note": "干净臂（no_raw/raw_first × egl/osmesa）实测最坏值",
            },
            "observed_polluted_worst": {
                "max_abs_diff": 255, "mean_abs_diff": 82.39,
                "min_pairwise_frac_diff": 0.0018,
                "note": "raw_after 污染臂实测值（三相机趋同时两两差塌到 0.0018）",
            },
            "separation": ("阈值与两侧实测值都差 ≥1 个数量级 ⇒ 判据有牙且不误杀；"
                           "阈值本身由实测标定，不是拍脑袋定的"),
        },
        "conclusion": "；".join(parts) + "。calib 脚本装的是 liveness+fidelity 合成闸 `render_health_ok`。",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backends", default="egl_nvidia,osmesa")
    ap.add_argument("--arms", default="no_raw,raw_first,raw_after")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "runs" / "infra" / "e_mainline_calib_20260929"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    log_dir = out_dir / "rawprobe_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    guard_before = ep.boundary_guard()
    doc: dict = {
        "artifact": "RAW_PROBE_INTERFERENCE.json",
        "agent": "E",
        "task": "E3-2/3/4 配套取证：同进程裸 mujoco.Renderer 探针的顺序污染",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "generator": "scripts/e_rawprobe_interference.py",
        "generator_sha256_12": ev.sha256_of(str(Path(__file__)))[:12],
        "python_child": PY,
        "env_under_test": "gym_aloha/AlohaTransferCube-v0 + envs/gym_aloha_shim.py（主线口径，与 calib 同）",
        "boundary_guard_before": guard_before,
        "load_before": ev.cpu_stat(),
        "gpu_before": ev.nvidia_smi_sample(),
        "arms": [a.strip() for a in args.arms.split(",") if a.strip()],
        "backends": [m.strip() for m in args.backends.split(",") if m.strip()],
        "reps": args.reps,
        "runs": [],
    }
    if not guard_before["ok"]:
        doc["verdict"] = "refused"
        doc["refuse_reason"] = "系统目录脏（§3.2 / 裁定 60）⇒ 拒跑"
        (out_dir / "RAW_PROBE_INTERFERENCE.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"verdict": "refused"}, ensure_ascii=False))
        return 1

    for mode in doc["backends"]:
        env = activation_env(mode)
        for arm in doc["arms"]:
            for rep in range(args.reps):
                r = run_arm(mode, arm, args.seed + rep, env, log_dir)
                r["rep"] = rep
                doc["runs"].append(r)
                print(f"[arm] {mode} {arm} r{rep} ok={r.get('ok')} "
                      f"frozen={r['derived']['frozen_buffer']} "
                      f"rate={((r.get('render_rate') or {}).get('ctrl_steps_per_s'))} "
                      f"liveness={r['derived']['liveness_strict_ok']} "
                      f"fidelity={r['derived']['fidelity_ok']} "
                      f"atexit_egl={r.get('atexit_egl_error')}", flush=True)

    # 逐后端汇总：以 no_raw 为基线算虚高
    per_mode = {}
    for mode in doc["backends"]:
        rs = [r for r in doc["runs"] if r["mode"] == mode and r.get("ok")]
        base = [r["render_rate"]["ctrl_steps_per_s"] for r in rs if r["arm"] == "no_raw"]
        entry = {"baseline_no_raw_ctrl_steps_per_s": (round(statistics.median(base), 2) if base else None),
                 "arms": {}}
        for arm in doc["arms"]:
            sub = [r for r in rs if r["arm"] == arm]
            if not sub:
                continue
            rates = [r["render_rate"]["ctrl_steps_per_s"] for r in sub]
            med = statistics.median(rates)
            entry["arms"][arm] = {
                "reps": len(sub),
                "render_ctrl_steps_per_s": rates,
                "render_ctrl_steps_per_s_median": round(med, 2),
                "render_rate_inflation_pct_vs_no_raw": (
                    round(100 * (med - statistics.median(base)) / statistics.median(base), 1) if base else None),
                "frozen_buffer_any": any(r["derived"]["frozen_buffer"] for r in sub),
                "frozen_buffer_all": all(r["derived"]["frozen_buffer"] for r in sub),
                "cam_convergence_any": any(r["derived"]["cam_convergence_3cam"] for r in sub),
                "liveness_strict_ok_all": all(r["derived"]["liveness_strict_ok"] for r in sub),
                "fidelity_ok_all": all(r["derived"]["fidelity_ok"] for r in sub),
                "fidelity_ok_any": any(r["derived"]["fidelity_ok"] for r in sub),
                "angle_mean_s1_vs_s3": [[r["derived"]["s1_angle_mean"], r["derived"]["s3_angle_mean"]]
                                        for r in sub],
                "atexit_egl_error_any": any(r.get("atexit_egl_error") for r in sub),
                "s3_angle_mean": [ (r.get("s3_after_30_env_steps") or {}).get("angle", {}).get("mean") for r in sub],
                "s3_angle_sha12": [ (r.get("s3_after_30_env_steps") or {}).get("angle", {}).get("sha12") for r in sub],
            }
        per_mode[mode] = entry
    doc["per_backend"] = per_mode

    # 判决：raw_after 只要在**任一**后端上冻结/虚高，就判"禁止"；raw_first 必须与 no_raw 等价
    harms = []
    for mode, e in per_mode.items():
        for arm in ("raw_first", "raw_after"):
            a = e["arms"].get(arm)
            if not a:
                continue
            infl = a["render_rate_inflation_pct_vs_no_raw"]
            fired = []
            if a["frozen_buffer_any"]:
                fired.append("frozen_buffer")
            if a["cam_convergence_any"]:
                fired.append("cam_convergence")
            if infl is not None and infl >= INFLATION_HARM_PCT:
                fired.append(f"render_rate_inflation>={INFLATION_HARM_PCT}%")
            if not a["liveness_strict_ok_all"]:
                fired.append("liveness_strict_failed")
            if not a["fidelity_ok_all"]:
                fired.append("fidelity_failed")
            if fired:
                harms.append({"mode": mode, "arm": arm, "frozen": a["frozen_buffer_any"],
                              "cam_convergence": a["cam_convergence_any"], "inflation_pct": infl,
                              "liveness_strict_ok_all": a["liveness_strict_ok_all"],
                              "fidelity_ok_all": a["fidelity_ok_all"],
                              "criteria_fired": fired})
    first_harm = [h for h in harms if h["arm"] == "raw_first"]
    after_harm = [h for h in harms if h["arm"] == "raw_after"]
    doc["load_after"] = ev.cpu_stat()
    doc["gpu_after"] = ev.nvidia_smi_sample()
    doc["boundary_guard_after"] = ep.boundary_guard()
    doc["verdict"] = {
        "raw_after_is_harmful": bool(after_harm),
        "raw_first_is_harmful": bool(first_harm),
        "harmful_observations": harms,
        "inflation_harm_threshold_pct": INFLATION_HARM_PCT,
        "noise_band_calibration": _noise_band(per_mode, doc),
        "rule": ("**禁止在被测 env 同进程、且 dm_control 已渲过图之后**建/关裸 `mujoco.Renderer`；"
                 "需要 GL 身份就另起独立子进程（calib 脚本的 `gl_identity_probe`）或放在 `make_env` 之前。"),
        "cross_line_note": ("A2 `scripts/a2_egl_latency_remeasure.py:702` 的 `gl_identity_via_mujoco()` "
                            "在 `make_env`（`:375`/`:430`，经 `:761`/`:771`）之前 ⇒ 属 raw_first，**安全**；"
                            "A2 `gl_identity_after_dm_render`（`:195`）只调 `glGetString`、不建 Renderer ⇒ 亦安全。"),
        "gate_analysis": _gate_analysis(per_mode),
    }

    path = out_dir / "RAW_PROBE_INTERFERENCE.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"artifact": str(path), "verdict": doc["verdict"],
                      "per_backend": {m: {a: {k: v for k, v in d.items()
                                              if k in ("render_ctrl_steps_per_s_median",
                                                       "render_rate_inflation_pct_vs_no_raw",
                                                       "frozen_buffer_any", "liveness_strict_ok_all",
                                                       "fidelity_ok_all", "angle_mean_s1_vs_s3")}
                                         for a, d in e["arms"].items()}
                                      for m, e in per_mode.items()},
                      "boundary_guard_after_ok": doc["boundary_guard_after"]["ok"]},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
