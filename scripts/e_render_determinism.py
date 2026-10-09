#!/usr/bin/env python
"""E 线取证：**同一物理状态下重复渲染是否逐位确定**（分后端 / 分相机）。

## 为什么单独取这一件证
给渲染加"保真闸"时最自然的判据是"回到同一 reset 态重拍，`sha256` 必须逐字复现"。
实测发现这个判据**在 GPU 臂上会误杀干净批**：

| 后端 | `angle` | `left_wrist` | `right_wrist` |
|---|---|---|---|
| `osmesa`（llvmpipe，CPU） | 逐位确定 | 逐位确定 | 逐位确定 |
| `egl`+NVIDIA（A800，GPU） | 逐位确定 | **不确定**（±1 LSB，5–7 px / 150528） | **不确定**（±1 LSB，9–21 px / 150528） |

即：GPU 光栅化对 wrist 相机存在 **±1 LSB 的非确定性抖动**，跨进程、跨 reset 都会变；
`angle` 相机与整个 CPU 臂则完全稳定。差异量级极小（`mean_abs_diff ≤ 0.00042`，
`max_abs_diff = 1`），**不影响图像语义**，但**足以让任何 sha/逐位比较失效**。

## 影响面（跨线）
- 本仓任何"用图像 sha 做回归/幂等判据"的地方，在 **GPU 渲染 + wrist 相机**上都不可靠；
  A2 的亮度/图像参照工作若用哈希比对，需改成**数值容差**比对。
- E 的 `e_mainline_render_calib.py` 保真闸因此用容差判据（`FID_MAX_ABS_DIFF=4` /
  `FID_MAX_FRAC_DIFF=0.02` / `FID_MAX_MEAN_DIFF=0.05`），不用 sha 相等。
- 跨后端"图像语义一致"的主张也必须带容差：GPU 与 CPU 的 reset 态 mean 差 ~0.1–0.3%，
  远大于本抖动（~0.0004），所以两者是**不同来源**的差异，不可混为一谈。

用法：
  python3 scripts/e_render_determinism.py --backends egl_nvidia,osmesa --reps 3

## 三条机器闸（都是事故换来的，不靠自觉）
1. **拒绝覆写**（裁定 82 §2-4 append-only / 裁定 83.5）：目标产物已存在 ⇒ `REFUSE` + exit 3。
   `--out-name` 让扩展轮另落新件（如 `RENDER_DETERMINISM_REPS5.json`），**不覆盖 D 已引用的那一版**。
2. **批级让位闸**（裁定 76.2 / 82.5-6②）：每个 GPU rep 起跑前查卡，卡上有他线 ⇒ 跳过该 rep 并登记
   `skipped_reason`。检测复用 `e_mainline_render_calib.card_busy()` 的**三网**（compute-apps / `/proc/*/fd`
   持有 `/dev/nvidia*` / 他线 cmdline），**不另造一份**，避免两处定义漂移。
3. **口径不得移植**（裁定 71 `caliber_transplant_ban` / 裁定 83.4）：本件测的是「**同状态重复渲染**」regime，
   `RAW_PROBE_INTERFERENCE.json` 的 `FID_*` 属「**跨臂污染检测**」regime ⇒ 本件的 `implication_for_gates`
   **不得**再把 `FID_*` 当 replay 容差开出去（旧版文案犯过这个错，已改）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import e_gpu_egl_verify as ev  # noqa: E402
import e_egl_probe as ep       # noqa: E402
import e_mainline_render_calib as calib  # noqa: E402  只借 card_busy() 三网检测，不另造一份口径

ACTIVATE = REPO_ROOT / "scripts" / "e_activate_gpu_render.sh"
PY = "/root/venvs/pi05_sim/bin/python"
CAMS = ["angle", "left_wrist", "right_wrist"]   # π₀.₅ 三键臂的默认相机集（224²）
DEFAULT_RESOLUTION = (224, 224)                 # 默认分辨率；与历史产物逐字一致
# 团队三槽的相机映射（T-E-DET-480，裁定 86.3）：抄 B2 的定义，不抄 B2 的任何阈值。
# 来源 = scripts/b2_s1_generate_dataset.py:167 `TEAM_SLOT_CAMERA`（head 槽用**真 top 相机**）。
TEAM_SLOT_CAMERA = {"head": "top", "left_wrist": "left_wrist", "right_wrist": "right_wrist"}
GPU_ARMS = {"egl_nvidia"}   # 需要查卡的臂；osmesa 纯 CPU 不占卡

_CHILD = r'''
import hashlib, importlib.util, json, os, sys
import numpy as np

REPO = sys.argv[1]; SEED = int(sys.argv[2]); NRESET = int(sys.argv[3]); NSHOOT = int(sys.argv[4])
# argv[5..7] = 相机集 / H / W，由父进程传入（T-E-DET-480 要跑 480×640 团队三槽）。
# 缺省时用与历史产物**逐字相同**的默认值 ⇒ 旧调用方式的子进程行为不变。
CAMS = [c for c in (sys.argv[5] if len(sys.argv) > 5 else "angle,left_wrist,right_wrist").split(",") if c]
H = int(sys.argv[6]) if len(sys.argv) > 6 else 224
W = int(sys.argv[7]) if len(sys.argv) > 7 else 224

spec = importlib.util.spec_from_file_location("gym_aloha_shim", os.path.join(REPO, "envs", "gym_aloha_shim.py"))
shim = importlib.util.module_from_spec(spec); spec.loader.exec_module(shim)
import mujoco
env, rec = shim.make_env(shim.ENV_ID, dt=shim.MAINLINE_DT,
                         obs_type="pixels_agent_pos", render_mode="rgb_array")
ph = env.unwrapped._env.physics
out = {"pid": os.getpid(), "seed": SEED, "mujoco_gl": os.environ.get("MUJOCO_GL"),
       "mujoco_version": mujoco.__version__, "shim_sha256_12": shim.shim_sha256_12(),
       "n_reset": NRESET, "n_shoot_per_state": NSHOOT, "resolution": [H, W], "cams": {}}

def shoot(c):
    a = np.asarray(ph.render(height=H, width=W, camera_id=c))
    return a, hashlib.sha256(a.tobytes()).hexdigest()[:12]

for c in CAMS:
    same_state_shas, across_reset_shas, refs = [], [], []
    env.reset(seed=SEED)
    for _ in range(NSHOOT):                      # 同一状态连拍（不 reset）
        a, s = shoot(c); same_state_shas.append(s); refs.append(a)
    for _ in range(NRESET):                      # 每次重新 reset 到同一 seed 再拍
        env.reset(seed=SEED)
        a, s = shoot(c); across_reset_shas.append(s); refs.append(a)
    diffs = []
    for i in range(1, len(refs)):
        d = np.abs(refs[0].astype(np.int16) - refs[i].astype(np.int16))
        diffs.append({"n_diff_px": int((d.sum(axis=2) > 0).sum()),
                      "n_px_total": int(d.shape[0] * d.shape[1]),
                      "max_abs_diff": int(d.max()),
                      "mean_abs_diff": round(float(d.mean()), 6)})
    out["cams"][c] = {
        "same_state_shas": same_state_shas,
        "across_reset_shas": across_reset_shas,
        "n_unique_shas": len(set(same_state_shas + across_reset_shas)),
        "bitwise_deterministic": len(set(same_state_shas + across_reset_shas)) == 1,
        "mean": round(float(refs[0].mean()), 4),
        "std": round(float(refs[0].std()), 4),
        "pixel_diffs_vs_first": diffs,
        "max_abs_diff_worst": max([d["max_abs_diff"] for d in diffs], default=0),
        "max_frac_diff_px_worst": round(max([d["n_diff_px"] / d["n_px_total"] for d in diffs], default=0.0), 6),
        "max_mean_abs_diff_worst": round(max([d["mean_abs_diff"] for d in diffs], default=0.0), 6),
    }
out["loadavg"] = os.getloadavg()[0]
out["ok"] = True
print("DET_JSON" + json.dumps(out))
'''


def activation_env(mode: str) -> dict:
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backends", default="egl_nvidia,osmesa")
    ap.add_argument("--reps", type=int, default=2, help="独立进程重复次数（跨进程确定性）")
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--n-reset", type=int, default=3)
    ap.add_argument("--n-shoot", type=int, default=3)
    ap.add_argument("--cams", default=",".join(CAMS),
                    help="逗号分隔的相机名。默认 = π₀.₅ 三键臂（angle,left_wrist,right_wrist @224²）；"
                         "T-E-DET-480（裁定 86.3）用团队三槽的相机 top,left_wrist,right_wrist")
    ap.add_argument("--resolution", default="224x224",
                    help="HxW。默认 224x224（π₀.₅ 键）；团队三槽 = 480x640（裁定 86.3）")
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "runs" / "infra" / "e_mainline_calib_20260929"))
    ap.add_argument("--out-name", default="RENDER_DETERMINISM.json",
                    help="产物文件名；扩展轮请换新名（append-only，不得覆盖 D 已引用的那一版）")
    ap.add_argument("--allow-shared-gpu", action="store_true",
                    help="显式允许与他线共卡（默认每个 GPU rep 前查卡，卡上有他线就跳过）")
    args = ap.parse_args()

    cams = [c.strip() for c in args.cams.split(",") if c.strip()]
    if not cams:
        print(json.dumps({"verdict": "REFUSE", "reason": "--cams 解析为空 ⇒ 拒绝起跑"}, ensure_ascii=False))
        return 3
    try:
        res_h, res_w = (int(x.strip()) for x in args.resolution.lower().split("x", 1))
    except Exception:
        print(json.dumps({"verdict": "REFUSE",
                          "reason": f"--resolution 必须是 HxW（收到 {args.resolution!r}）"}, ensure_ascii=False))
        return 3
    # 「默认臂」= π₀.₅ 三键 224²（历史口径）。**非默认臂不得沿用裁定 83.3 的可推翻条件**：
    # 那三条是为 224² 采集臂定的，搬到 480×640 就是裁定 71 `caliber_transplant_ban` 禁止的动作。
    default_arm = (cams == CAMS and (res_h, res_w) == DEFAULT_RESOLUTION)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / args.out_name
    if out_path.exists():
        print(json.dumps({"verdict": "REFUSE", "reason": f"{out_path.name} 已存在；本件 append-only，"
                          "重跑请换 --out-name 或先把旧件移进 recycle_bin（不 rm）",
                          "existing_sha256_12": ev.sha256_of(str(out_path))[:12]}, ensure_ascii=False))
        return 3
    doc: dict = {
        "artifact": args.out_name,
        "agent": "E",
        "task": "E3-2/3/4 配套取证：同状态重复渲染的逐位确定性（分后端 / 分相机）",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "generator": "scripts/e_render_determinism.py",
        "generator_sha256_12": ev.sha256_of(str(Path(__file__)))[:12],
        "python_child": PY,
        "env": "gym_aloha/AlohaTransferCube-v0 + envs/gym_aloha_shim.py（主线口径）",
        "cams": cams, "resolution": [res_h, res_w], "seed": args.seed,
        "reps": args.reps,
        "n_reset": args.n_reset, "n_shoot_per_state": args.n_shoot,
        "boundary_guard_before": ep.boundary_guard(),
        "load_before": ev.cpu_stat(),
        "gpu_before": ev.nvidia_smi_sample(),
        "runs": [],
        "gpu_yield_gate": {"enabled": not args.allow_shared_gpu, "detector": "e_mainline_render_calib.card_busy(strict=True) 三网",
                           "checks": []},
    }
    if not doc["boundary_guard_before"]["ok"]:
        doc["verdict"] = "refused"
        out_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1

    for mode in [m.strip() for m in args.backends.split(",") if m.strip()]:
        env = activation_env(mode)
        for rep in range(args.reps):
            # 批级让位闸（裁定 76.2 / 82.5-6②）：只对占卡的臂查；跳过要**登记**，不许静默丢
            if mode in GPU_ARMS and not args.allow_shared_gpu:
                busy = calib.card_busy(strict=True)
                doc["gpu_yield_gate"]["checks"].append(
                    {"mode": mode, "rep": rep, "busy": busy["busy"],
                     "compute_procs": busy["compute_procs"], "nvidia_fd_holders": busy["nvidia_fd_holders"],
                     "cmdline_hits": busy["cmdline_hits"], "loadavg": ev.cpu_stat().get("loadavg")})
                if busy["busy"]:
                    doc["runs"].append({"mode": mode, "rep": rep, "ok": False,
                                        "skipped_reason": "gpu_yield_gate_card_busy", "card_busy": busy})
                    print(f"[det] {mode} rep{rep} SKIPPED（批级让位闸：卡上有他线 ⇒ 不起 GPU 进程）", flush=True)
                    continue
            p = subprocess.run([PY, "-c", _CHILD, str(REPO_ROOT), str(args.seed),
                                str(args.n_reset), str(args.n_shoot),
                                ",".join(cams), str(res_h), str(res_w)],
                               capture_output=True, text=True, env=env, timeout=900)
            payload = None
            for line in p.stdout.splitlines():
                if line.startswith("DET_JSON"):
                    payload = json.loads(line[len("DET_JSON"):])
            if payload is None:
                payload = {"ok": False, "returncode": p.returncode,
                           "stderr_tail": (p.stderr or "").strip().splitlines()[-8:]}
            payload["mode"] = mode
            payload["rep"] = rep
            doc["runs"].append(payload)
            print(f"[det] {mode} rep{rep} " + " ".join(
                f"{c}={'det' if (payload.get('cams') or {}).get(c, {}).get('bitwise_deterministic') else 'NONDET'}"
                for c in cams), flush=True)

    # 汇总：逐 (后端, 相机) 是否逐位确定 + 最坏抖动量级
    table = {}
    for mode in {r["mode"] for r in doc["runs"] if r.get("ok")}:
        rs = [r for r in doc["runs"] if r["mode"] == mode and r.get("ok")]
        per_cam = {}
        for c in cams:
            cs = [(r["cams"][c]) for r in rs if c in (r.get("cams") or {})]
            if not cs:
                continue
            per_cam[c] = {
                "bitwise_deterministic_in_process_all_reps": all(x["bitwise_deterministic"] for x in cs),
                "n_unique_shas_per_rep": [x["n_unique_shas"] for x in cs],
                "cross_process_same_sha": (len({x["same_state_shas"][0] for x in cs}) == 1),
                "cross_process_shas": [x["same_state_shas"][0] for x in cs],
                "max_abs_diff_worst": max(x["max_abs_diff_worst"] for x in cs),
                "max_frac_diff_px_worst": max(x["max_frac_diff_px_worst"] for x in cs),
                "max_mean_abs_diff_worst": max(x["max_mean_abs_diff_worst"] for x in cs),
                "mean": cs[0]["mean"],
            }
        table[mode] = {"reps": len(rs), "cams": per_cam}
    doc["per_backend"] = table

    # ── 第四道闸：「没测到」不许报绿（2026-09-30 02:22:37 的实测教训）──────────────
    # 那一轮 B2 的采集进程在卡上（fd 网 PID 388252 持 /dev/nvidia2），批级让位闸把 5 个 rep 全跳过，
    # 而汇总只在 `ok=true` 的 rep 上算 ⇒ 空集 ⇒ `nondet=[]` ⇒ 产物写着 `all_bitwise_deterministic: true`。
    # **没测到却报绿**，与本仓禁止的静默降级同型 ⇒ 这里显式区分「测到全逐位」与「根本没测」，
    # 并且**没测到就 exit 4**（不是 0），调用方不可能把它当成通过。
    requested_modes = [m.strip() for m in args.backends.split(",") if m.strip()]
    measured_modes = sorted(m for m, e in table.items() if e["reps"] > 0)
    unmeasured = [m for m in requested_modes if m not in measured_modes]
    n_ok = sum(1 for r in doc["runs"] if r.get("ok"))
    n_skipped_yield = sum(1 for r in doc["runs"] if r.get("skipped_reason") == "gpu_yield_gate_card_busy")
    if n_ok > 0 and not unmeasured:
        measurement_status = "measured"
    elif n_ok == 0 and n_skipped_yield > 0:
        measurement_status = "not_measured_all_reps_skipped_by_yield_gate"
    elif n_ok == 0:
        measurement_status = "not_measured_no_successful_rep"
    else:
        measurement_status = "partially_measured_some_backends_unmeasured"
    doc["measurement_status"] = measurement_status
    doc["unmeasured_backends"] = unmeasured

    nondet = [f"{m}/{c}" for m, e in table.items() for c, v in e["cams"].items()
              if not v["bitwise_deterministic_in_process_all_reps"] or not v["cross_process_same_sha"]]
    doc["verdict"] = {
        "non_deterministic_backend_cam_pairs": nondet,
        "all_bitwise_deterministic": not nondet,
        "implication_for_gates": (
            "**不能用 sha/逐位相等做渲染保真闸**（会在 GPU 臂误杀干净批）。"
            "**但本件不给出容差数值** —— 本件测的是「同状态重复渲染」regime，容差由 D 定（裁定 83.4 的 "
            "`replay_max_abs_diff<=2` / `replay_frac_diff_px<=0.005` / `replay_mean_abs_diff<=0.005`）；"
            "`RAW_PROBE_INTERFERENCE.json` 的 `FID_*` 属「跨臂污染检测」regime，"
            "**禁止移植到 replay 口径**（裁定 71 `caliber_transplant_ban` / 裁定 83.4）。"
            if nondet else "sha 逐位相等可用（本环境实测全确定）。"),
        "regime": "same_state_repeat_render（**不是** cross_arm_pollution_detection）",
        "applies_when": {
            "keyed_on": "实测 GL_RENDERER（裁定 83 §5 全线规则：**不以 MUJOCO_GL 环境变量为键**）",
            "nvidia_gpu": {"wrist_cams": "不逐位，需容差（数值由 D 定）", "angle_cam": "**仍逐位 = 硬判据**"},
            "llvmpipe": {"all_cams": "**全部逐位 = 硬判据，不带任何容差**"},
        },
        "falsification_conditions_ruling_83_3": {
            "frac_diff_px_gt": 0.01, "max_abs_diff_gt": 8, "or_angle_also_non_bitwise": True,
            "consequence": "任一成立 ⇒ 裁定 83.3「维持 egl 作采集后端」自动失效，改走「osmesa 采集 + egl 吞吐」双后端并回到用户裁",
            "observed_this_round": None,
        },
        "implication_for_image_semantics": (
            "抖动量级 max_abs_diff=1、mean_abs_diff<=0.00042（<=0.0004%），**远小于**跨后端 reset 态 "
            "mean 差（~0.1-0.3%）⇒ 不影响图像语义结论，但任何哈希比对都要换成容差比对。"),
        "cross_line_note": ("A2 的图像/亮度参照工作若在 GPU 渲染下用哈希比对 wrist 相机，需改容差比对；"
                            "`angle` 相机与 osmesa 臂不受影响。"),
    }

    # ── 非默认臂（T-E-DET-480：团队三槽 480×640）的判据文案与登记带 ──────────────
    # 默认臂（π₀.₅ 三键 224²）**一个字节都不改**：下面这些覆盖只在 `default_arm=False` 时执行，
    # 所以历史产物 `RENDER_DETERMINISM.json` / `RENDER_DETERMINISM_REPS5.json` 的口径不受影响。
    if not default_arm:
        worst_frac = max([v["max_frac_diff_px_worst"] for e in table.values()
                          for v in e["cams"].values()] or [0])
        worst_abs = max([v["max_abs_diff_worst"] for e in table.values()
                         for v in e["cams"].values()] or [0])
        worst_mean = max([v["max_mean_abs_diff_worst"] for e in table.values()
                          for v in e["cams"].values()] or [0])
        doc["arm"] = "team_slots_480x640_T-E-DET-480"
        doc["arm_ruling"] = "裁定 86.3（RR-B2-21 采纳）：把确定性轮扩到 480×640 团队三槽，同 regime、同脚本、--reps 5"
        doc["team_slot_map"] = dict(TEAM_SLOT_CAMERA)
        doc["team_slot_map_source"] = ("scripts/b2_s1_generate_dataset.py:167 `TEAM_SLOT_CAMERA`"
                                       "（B2 的定义；E 只登记映射，不改 B2 的件）")
        v = doc["verdict"]
        v["implication_for_gates"] = (
            "本件给的是**480×640 团队三槽在该 regime 下的实测抖动**，用途 = 给 B2 的 G4d 提供登记带基础"
            "（裁定 86.3-5：**容差取本件实测最差值，倍数由 D 定**；方法照裁定 83.4）。"
            "**本件不给出容差数值、不自造阈值、不判定 G4d 绿或红**（三值纪律）。"
            "仍适用：sha/逐位相等**不能**做渲染保真闸（裁定 85.2-2 的红线 "
            "`render_bitwise_equality_ban_on_egl`）。")
        v["applies_when"] = {
            "keyed_on": "实测 GL_RENDERER（裁定 83 §5：**不以 MUJOCO_GL 环境变量为键**）",
            "resolution": [res_h, res_w],
            "cam_set": cams,
            "note": ("本轮相机集**不含 `angle`**（团队 head 槽用真 `top` 相机）⇒ 224² 那一轮关于 "
                     "`angle` 仍逐位的陈述**不适用于本轮**，本轮也不重判它。"),
        }
        v["falsification_conditions_ruling_83_3"] = {
            "rejudged_this_round": False,
            "reason": ("裁定 83.3 的三条可推翻条件是为 **π₀.₅ 采集臂 224²**（`angle`/`left_wrist`/"
                       "`right_wrist`）定的。本轮是 **480×640 团队三槽**（`top`/`left_wrist`/"
                       "`right_wrist`），相机集与分辨率都不同 ⇒ 把那三条搬过来判 = 裁定 71 "
                       "`caliber_transplant_ban` 禁止的动作。故本轮**只登记实测值，不重判 83.3**；"
                       "83.3 的状态以 224² 那一轮（`RENDER_DETERMINISM_REPS5.json`）为准。"),
            "measured_this_round_no_criteria_attached": {
                "worst_frac_diff_px": worst_frac, "worst_max_abs_diff": worst_abs,
                "worst_mean_abs_diff": worst_mean},
        }
        v["implication_for_image_semantics"] = (
            "本轮的量级见 `register_band_for_g4d.per_camera_worst`（机器读，不手抄）。"
            "跨后端/跨分辨率的 mean 差（~0.1–0.3%）与本抖动是**不同来源**，不得混为一谈（裁定 71）。")
        v["cross_line_note"] = (
            "给 B2：G4d 的登记带基础在 `per_backend.<mode>.cams[<camera>]`（结构与 224² 那一轮**同名同义**，"
            "所以 `e_reps5_per_cam_band()` 的读法可以照搬，只需换文件路径与相机名 `angle→top`）。"
            "给 D：倍数由 D 定；E 不预设。")
        v["register_band_for_g4d"] = {
            "resolution": [res_h, res_w],
            "regime": "same_state_repeat_render（与 224² 那一轮同 regime、同脚本、同 seed 口径）",
            "reps": args.reps,
            "camera_to_team_slot": {cam: slot for slot, cam in TEAM_SLOT_CAMERA.items()},
            "machine_readable_at": ("per_backend.<mode>.cams[<camera>]."
                                    "{max_abs_diff_worst,max_frac_diff_px_worst,max_mean_abs_diff_worst,"
                                    "bitwise_deterministic_in_process_all_reps,cross_process_same_sha}"),
            "worst_over_all_cams_and_backends": {
                "max_abs_diff": worst_abs, "frac_diff_px": worst_frac, "mean_abs_diff": worst_mean},
            "who_sets_the_tolerance": "D（裁定 86.3-5）；E 只交实测最差值",
        }

    # 「没测到」必须在**判定字段本身上**可见，不能只在旁边加个说明字段（否则引用方只读 verdict 就会中招）
    if measurement_status != "measured":
        doc["verdict"]["all_bitwise_deterministic"] = None
        doc["verdict"]["measurement_status"] = measurement_status
        doc["verdict"]["not_a_pass"] = (
            "**本轮没有有效测量**：`non_deterministic_backend_cam_pairs=[]` 是**空集上的平凡真**，"
            "不是「测到全逐位」。任何文书**不得**引用本件作确定性证据；请在他线让出卡之后重跑"
            "（换 `--out-name`，本件按 append-only 保留原字节并登记为作废件）。"
            f"实测：`n_ok_runs={n_ok}`、`n_skipped_by_yield_gate={n_skipped_yield}`、"
            f"`unmeasured_backends={unmeasured}`。")
    doc["load_after"] = ev.cpu_stat()
    doc["gpu_after"] = ev.nvidia_smi_sample()
    doc["boundary_guard_after"] = ep.boundary_guard()

    # 裁定 83.3 的可推翻条件：用本轮实测现算，不留空（**只对默认臂 224² 成立**；
    # 非默认臂已在上面记 `rejudged_this_round=False` + 理由，不在这里重判）
    if default_arm:
        worst_frac = max([v["max_frac_diff_px_worst"] for e in table.values() for v in e["cams"].values()] or [0])
        worst_abs = max([v["max_abs_diff_worst"] for e in table.values() for v in e["cams"].values()] or [0])
        angle_nondet = [f"{m}/angle" for m, e in table.items()
                        if not e["cams"].get("angle", {}).get("bitwise_deterministic_in_process_all_reps", True)
                        or not e["cams"].get("angle", {}).get("cross_process_same_sha", True)]
        fc = doc["verdict"]["falsification_conditions_ruling_83_3"]
        fc["observed_this_round"] = {"worst_frac_diff_px": worst_frac, "worst_max_abs_diff": worst_abs,
                                     "angle_non_bitwise_pairs": angle_nondet}
        fc["any_condition_met"] = bool(worst_frac > fc["frac_diff_px_gt"] or worst_abs > fc["max_abs_diff_gt"]
                                       or angle_nondet)
        fc["ruling_83_3_stands"] = not fc["any_condition_met"]

    path = out_path
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"artifact": str(path), "measurement_status": measurement_status,
                      "verdict": doc["verdict"],
                      "per_backend": {m: {c: {"det": v["bitwise_deterministic_in_process_all_reps"]
                                              and v["cross_process_same_sha"],
                                             "max_abs_diff": v["max_abs_diff_worst"],
                                             "max_frac_diff_px": v["max_frac_diff_px_worst"]}
                                      for c, v in e["cams"].items()} for m, e in table.items()},
                      "boundary_guard_after_ok": doc["boundary_guard_after"]["ok"]},
                     ensure_ascii=False, indent=1))
    if measurement_status != "measured":
        # 没测到就**不许 exit 0**：调用方（含未来的驱动脚本）不可能把它当成通过
        print(f"[det] **{measurement_status}** ⇒ exit 4（不是 0）：本件不构成确定性证据；"
              f"n_ok_runs={n_ok}、n_skipped_by_yield_gate={n_skipped_yield}、unmeasured_backends={unmeasured}",
              file=sys.stderr, flush=True)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
