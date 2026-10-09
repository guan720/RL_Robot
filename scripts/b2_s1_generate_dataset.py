#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 · S1 主交付：**仿真双向示范数据集生成器**（脚本专家 → 逐位重放校验 → 两个出口）。

它产出什么
----------
同一条回合被写成**两个出口**（同一份物理，不重跑两遍物理）：

1. `dataset/team_form/`：**团队 `vla_pipeline` 形态**（ABC-130k 同构）——
   `data/train/<task_dir>/episode_<uuid>/{converted_metadata_normal.json, top-camera.mp4,
   left-wrist-camera.mp4, right-wrist-camera.mp4}`，视频 480×640（对齐 ABC-130k 实测的 640×480 子集）、
   容器帧率 **500/17 = 29.411765 Hz**（`-r 500/17`，ffprobe 实测 `avg_frame_rate=500/17`）。
   → 交给 `scripts/b2_run_team_qc.py` 跑 validate→clean→qc。
2. `dataset/pi05_lerobot/`：**LeRobot v3.0 数据集**（`LeRobotDataset`，`fps=29.4118`），
   键名逐字走 A2 的 π₀.₅ 契约（`runs/vla/a2_pi05_contract_20260929/contract.json →
   observation.camera_map`：`base_0_rgb←angle`、`left_wrist_0_rgb←left_wrist`、
   `right_wrist_0_rgb←right_wrist`），图像 **224² 原生渲染**（不是从 480×640 缩的：MuJoCo `fovy`
   固定、`fx=fy`，4:3 与 1:1 的视锥不同 ⇒ 缩放会换一个视锥，那是口径搬运）。
   → 交给 C2 的 T-C2-1（stats 同源）与 A2 的 S3（BC）。

**图像为什么内嵌 parquet 而不是 mp4（两案并列，不静默选）**
lerobot 0.4.4 的视频编码路径把 fps 直接喂给 PyAV：`datasets/video_utils.py:460`
`output.add_stream(vcodec, fps, …)` → `av/utils.pyx:51 to_avrational` ⇒ **非整数 fps 直接
`AttributeError: 'float' object has no attribute 'numerator'`**（B2 2026-09-29 22:4x 实测，
`tmp/b2_lerobot_fps_probe/`）。而主线控制频率是 **29.4118 Hz（裁定 53，非整数，因为
`dm_control.compute_n_steps` 对非整数倍 `raise ValueError` 而不是四舍五入）**。三案：
  甲（本脚本采用）`dtype="image"` ⇒ PNG 内嵌 parquet，**无损**、`fps` 字段诚实、时间戳精确；体积大。
  乙 `dtype="video"` + 容器 30 fps ⇒ 体积 ~10× 小，但 `fps` 字段说谎、时间戳与真控制周期差 2%。
  丙 monkeypatch lerobot 的编码器注入 `Fraction(500,17)` ⇒ 体积小且诚实，但改第三方运行时行为。
**采甲，并把乙/丙报 D 裁**（裁定 51.1  polarity 教训 + 裁定 46.4 跨口径禁令）。

路线合规（裁定 66，§13.5）
--------------------------
**示范在关节模型里采**：物理与 IK 都用 `gym_aloha/assets/bimanual_viperx_transfer_cube.xml`
（`AlohaTransferCube-v0` 的模型，`nu=16`，用它自己的 position actuator 执行）。
**EE 模型一个字节都不加载** —— 因为 B2 probe2/probe4 实测 EE 的 weld 通道有三处硬伤
（`eq_data[3:6]` 带编译期 anchor2=±0.134706 m ⇒ 复位瞬间违反约束；右臂解析反解残差 0.247 m、
姿态偏 2.376 rad；`sim_end_effector.py:120` 无条件渲染 ⇒ `MUJOCO_GL=disable` 下不可用），
且 EE 的重力下垂 + soft-weld 滞后与关节模型的 actuator 动力学**不是同一套动力学**，
而 S5 评测必然在关节模型里跑（§13.5 原文）。**这是对裁定 66 字面路线（"EE 模型只作 IK oracle"）
的一处偏离，理由与实测证据在 `demo_manifest.json → route_compliance` 里逐条留痕，并报 D。**

采集与记录（裁定 66 §13.7 四条）
--------------------------------
① **方块先沉降**：`box_settle_steps=12`（seeding z=0.05 → 落定 0.0200，probe4 实测），
   沉降的 12 步**不进数据集**（否则前 12 帧教的是"方块凭空下落"），第 0 帧在沉降之后。
② **夹爪标定用 probe4 的表**：开 `cmd=1.0`（spread 0.08412 m）、闭 `cmd=0.0`（0.01833 m）、
   开合阈值 `cmd≈0.45`（spread=0.04=方块宽），全部写进 manifest。
③ **存 14 维动作，不存 16 维 `qpos`**：`tasks/sim.py:47-48` 实测 `env_action` 把 14 维的夹爪位
   展成 `(+v, −v)` 一对 ⇒ 映射写死在 `representation_version` 里（`grip14_to_qpos_pair=+v,-v`）。
④ **指尖偏置用实测 `tip_rel_gripframe=[0.0935, 0.0, 0.0021]`**（probe4 E1），不用 `gripper_link` 原点。

判据（S1 出口判据 §13.8 五条 ⇒ 本脚本的 12 道闸，全部三值 + `red_when` + 变异牙）
------------------------------------------------------------------------------
见 `GATES` 与 `demo_manifest.json → gates`。三个变异体（§13.8/S1 判据 5）：
  `dt-back-to-50hz`（DT=0.02 ⇒ 频率闸必须红，含团队 QC 的 V04/J）、
  `reverse-judge-flipped`（反向判据方向写反 ⇒ 必须红）、
  `random-actions`（随机动作当示范 ⇒ 专家闸必须红）、
  `replay-state-perturb-1e-3`（replay 状态扰动 1e-3 ⇒ G4 的逐位硬判据必须红）、
  `replay-state-1lsb`（replay 状态**只改 1 个 LSB/ULP** ⇒ G4 仍必须红；裁定 85.5 的牙②）、
  `replay-image-pixel-only`（只篡改像素、状态不动 ⇒ **必须仍绿**；裁定 85.5 的牙③）。

replay 闸的判据（**裁定 85.5 / d_handoff_to_b2 §18.5，即时生效，取代 §17-6 的过渡期口径**）
----------------------------------------------------------------------------------------
**硬判据（唯一判红的一条）= 状态逐位相等**（G4）。三相机像素**一律只登记不判红**：
E 的 n=5 实测（`RENDER_DETERMINISM_REPS5.json`，`767a2d984a5b`）表明 egl 下三相机
`cross_process_same_sha` 全 false、`angle` 也只有 4/5 逐位 ⇒ 拿像素逐位当判据 = **随机红**
（最坏的一种闸）。B2 首手实测更强：**同一进程内、同状态连渲两次** `angle` 就有帧不逐位。
⇒ 新红线 `render_bitwise_equality_ban_on_egl`：egl 臂上任何闸不得以渲染帧 sha 逐位相等为判据；
  `applies_when` 以**实测 `GL_RENDERER`** 为键（不以 `MUJOCO_GL` 为键）。osmesa/llvmpipe 臂不受此约束
  （n=5 三相机全逐位）⇒ 该臂上 G4b 仍是逐位硬判据。

边界（硬）
----------
只读：`gym_aloha`/`dm_control`/`lerobot` 的 site-packages（**一个字节都不改**）、团队 `vla_pipeline`
（由 `scripts/b2_run_team_qc.py` 只读调用）、`workplace/`、`yfw_input/`、A2 的契约产物。
禁写：`datasets/`。写入面：只有 `--out`（默认 `runs/vla/b2_sim_demo_bidir_20260930/`）。
不用 `rm`（要清旧产物走 `--trash`，移到回收站）。GPU：单进程串行渲染，不开多进程。

用法
----
    eval "$(bash scripts/e_activate_gpu_render.sh --print)"      # 裁定 70：不硬编码前缀目录名
    /root/venvs/pi05_sim/bin/python scripts/b2_s1_generate_dataset.py --stage pilot
    /root/venvs/pi05_sim/bin/python scripts/b2_s1_generate_dataset.py --stage formal
    /root/venvs/pi05_sim/bin/python scripts/b2_s1_generate_dataset.py --selftest
    /root/venvs/pi05_sim/bin/python scripts/b2_s1_generate_dataset.py --mutation dt-back-to-50hz \\
        --n-seeds 2 --out-subdir mutation_dt50 --skip-lerobot
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
CST = timezone(timedelta(hours=8))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import b2_s1_scripted_expert as expert                      # noqa: E402
from b2_make_demo_episodes import (DIMENSION_CONFIG, METADATA_NAME, VIDEO_SLOTS,  # noqa: E402
                                   probe_frames, write_video)

# ---------------- 口径常量（出处逐条标注；改口径 = 换 representation_version） ----------------
A2_CONTRACT = ROOT / "runs/vla/a2_pi05_contract_20260929/contract.json"
SHIM_PATH = ROOT / "envs/gym_aloha_shim.py"
MAINLINE_DT = 0.034
MAINLINE_HZ = 1.0 / MAINLINE_DT            # 29.411764705882355
FPS_RATIONAL = "500/17"                    # == 29.411764705882355，ffmpeg/ffprobe 实测原样保留
QC_FPS_BAND = (29.0, 31.0)
BOX_SETTLE_STEPS = 12                      # probe4：seeding z=0.05 → 12 步后 z=0.0200
BOX_Z_SEEDED = 0.05
BOX_Z_AT_REST = 0.0200
GRIP_CMD_OPEN = 1.0                        # probe4 E4：spread 0.08412 m
GRIP_CMD_CLOSE = 0.0                       # probe4 E4：spread 0.01833 m
GRIP_CMD_THRESHOLD = 0.45                  # spread ≈ 0.04 m = 方块宽
GRIP_CALIBRATION_TABLE = {"0.0": 0.01833, "0.25": 0.02828, "0.5": 0.0465,
                          "0.75": 0.06605, "1.0": 0.08412}
# --- G9 的判据参数（每条都由**实测量**导出，不写魔数带）---
# ① 张开容差 5 mm：probe4 的 E4 是在**复位构型**（START_ARM_POSE，臂垂在基座上方）测的
#    spread=0.08412；数据集里能拿到的"cmd=1.0 且准静态"帧都在**工作构型**（臂伸到交接点）。
#    位置伺服的稳态误差随构型变 ⇒ B2 2026-09-30 实测两处相差 3.34 mm（0.08746 vs 0.08412）。
#    取 5 mm：容得下这个实测构型差，又远小于"开/闭语义写反"会造成的 6.9 cm 差。
GRIP_TOL_OPEN_M = 0.005
# ② 夹持容差 2 mm：期望值 = probe4 空载闭合指距 0.01833 + 方块实测宽 0.04 = 0.05833，
#    实测中位 0.05837（差 0.04 mm）。这条其实是**抓握质量**证明：夹空了会掉到 0.018。
GRIP_TOL_CLOSE_M = 0.002
# ③ 动态过冲上限：cmd=1.0 的帧里实测指距最大值（甩动时伺服过冲），只做 sanity 上界。
GRIP_DYNAMIC_MAX_M = 0.12
# ④ "准静态"判据：该侧 6 个臂关节 |qvel| 全 < 0.1 rad/s（否则拿动态过冲去比静态标定表是错的口径）
QUIESCENT_QVEL_RAD_S = 0.1
QUIESCENT_MIN_FRAMES = 3                  # 准静态帧少于这个数 ⇒ 该侧判 UNJUDGED，不拿 0 填充
# G16 投影验证的**紧**半径：正确约定实测命中 0.37 px（team_head@480×640）/ 0.65 px（angle@224²），
# 错的约定落在 57.4 / 11.5 px ⇒ 8 px 能把两者分开；60 px 的松半径会让错的也算命中（⇒ 歧义、闸空转）。
PROJECTION_TIGHT_RADIUS_PX = 8
PROJECTION_LOOSE_RADIUS_PX = 60           # 只作上下文报告，不参与判定
TIP_REL_GRIPFRAME = [0.0935, 0.0, 0.0021]  # probe4 E1（左右同值）
TEAM_VIDEO_H, TEAM_VIDEO_W = 480, 640      # ABC-130k 实测分辨率子集之一（另一子集 848×480）
PI05_IMAGE_HW = 224                        # A2 契约 image_size=224
IS_MOVE_JOINT_EPS = 1e-3                   # rad；|Δ 命令关节| 超过它 ⇒ is_move=1（B2 自定义并自述语义）
IS_MOVE_GRIP_EPS = 1e-3
POSE_JUMP_POS_M = 0.1                      # 团队 C03 阈值（configs/default.yaml process.position_threshold）
POSE_JUMP_DEG = 30.0                       # 团队 C03 阈值（process.angle_threshold_deg）
WRIST_CAM_MAX_DIST_M = 1.2                 # 团队 M02 默认阈值（qc.wrist_camera_max_distance）
EUCLIDEAN_THRESHOLD_M = 1.5                # 团队 E 阈值（qc.euclidean_threshold）
STILL_SECONDS = 5.0                        # 团队 I / C01（qc.still_seconds、process.static_check_seconds）

# π₀.₅ 三键 ← 相机（**运行时从 A2 契约读并比对**，不硬编码；见 gate G13）
PI05_KEY_DEFAULT = {"observation.images.base_0_rgb": "angle",
                    "observation.images.left_wrist_0_rgb": "left_wrist",
                    "observation.images.right_wrist_0_rgb": "right_wrist"}
# 团队三槽 ← 相机（head 槽用**真 top 相机**，不张冠李戴；π₀.₅ 的 base 用 angle 相机）
TEAM_SLOT_CAMERA = {"head": "top", "left_wrist": "left_wrist", "right_wrist": "right_wrist"}
RENDER_SPEC: Tuple[Tuple[str, str, int, int], ...] = (
    ("team_head", "top", TEAM_VIDEO_H, TEAM_VIDEO_W),
    ("team_left_wrist", "left_wrist", TEAM_VIDEO_H, TEAM_VIDEO_W),
    ("team_right_wrist", "right_wrist", TEAM_VIDEO_H, TEAM_VIDEO_W),
    ("pi05_base_0_rgb", "angle", PI05_IMAGE_HW, PI05_IMAGE_HW),
    ("pi05_left_wrist_0_rgb", "left_wrist", PI05_IMAGE_HW, PI05_IMAGE_HW),
    ("pi05_right_wrist_0_rgb", "right_wrist", PI05_IMAGE_HW, PI05_IMAGE_HW),
)
SLOT_TO_PI05_KEY = {"pi05_base_0_rgb": "observation.images.base_0_rgb",
                    "pi05_left_wrist_0_rgb": "observation.images.left_wrist_0_rgb",
                    "pi05_right_wrist_0_rgb": "observation.images.right_wrist_0_rgb"}
SLOT_TO_TEAM = {"team_head": "head", "team_left_wrist": "left_wrist",
                "team_right_wrist": "right_wrist"}

# ---- replay 图像确定性：D 定的容差（裁定 82⑤ / 83.4）+ 它的**实测基础** ----
# **裁定 85.5（§18.5）之后，下面这两组数字都不是判据，只是「登记带」**：
#   `REPLAY_IMG_TOL`     = 裁定 83.4 的三容差（D 定的数值，85.5 明写「不需重定」）；
#   `e_reps5_per_cam_band()` = E 的 n=5 **逐相机**实测最差值（85.5 点名要登记的那一组：
#                          angle ≤0.002% / left_wrist ≤0.024% / right_wrist ≤0.052% / max_abs_diff ≤1）。
# 为什么这组数字对 π₀.₅ 三键（224²）可以搬用：E 的 `RENDER_DETERMINISM_REPS5.json`（reps=5）
# 实测 regime = `same_state_repeat_render`、分辨率 = **224×224**、相机 = angle/left_wrist/right_wrist
# ⇒ 与本闸对 π₀.₅ 三键做的事（**同状态连渲两次比像素**）**同口径、同分辨率、同相机名**。
# 团队三槽是 **480×640**，E 没测过 ⇒ 按裁定 71 `caliber_transplant_ban` **不搬用**这组数字，
# 只首手登记实测值 + 判 N_A，并提 RR 请 E 把 n=5 扩到 480×640。
# **超带不判红**（85.5：像素一律只登记）；超带的事实照写进产物 + 打进 stdout，供裁者看。
REPLAY_IMG_TOL = {"max_abs_diff": 2, "frac_diff_px": 0.005, "mean_abs_diff": 0.005}
E_REPS5_ARTIFACT = ROOT / "runs" / "infra" / "e_mainline_calib_20260929" / "RENDER_DETERMINISM_REPS5.json"
PI05_SLOTS = ("pi05_base_0_rgb", "pi05_left_wrist_0_rgb", "pi05_right_wrist_0_rgb")
TEAM_SLOTS = ("team_head", "team_left_wrist", "team_right_wrist")
# 变异体（红线 `tooth_must_be_mutant_proven`：**判红的闸**必须有变异体证明它会红；
# 裁定 85.5 的牙③反过来——**已降级的像素闸**必须有变异体证明它「不会红」）
MUT_IMG_SLOT = "pi05_base_0_rgb"     # 往哪个槽注入
MUT_IMG_DELTA = 3                    # > 容差 max_abs_diff=2
MUT_IMG_FRAC = 0.01                  # > 容差 frac_diff_px=0.005
MUT_STATE_EPS = 1e-3                 # D §17-6 指定的状态扰动量
MUT_IMG_PIXEL_ONLY = "replay-image-pixel-only"          # 裁定 85.5 牙③：只改像素 ⇒ 必须仍绿
MUT_IMG_PIXEL_ONLY_ALIAS = "replay-image-over-tolerance"  # 旧名（§17-6 时代它期望 G4b 红）⇒ 保留可读性
MUT_STATE_1LSB = "replay-state-1lsb"                    # 裁定 85.5 牙②：状态只改 1 个 ULP ⇒ 必须红
SLOT_CAMERA = {sl: cm for sl, cm, _, _ in RENDER_SPEC}


def e_reps5_per_cam_band() -> dict:
    """**机器读** E 的 n=5 逐相机实测最差值当「登记带」（不手抄数字，避免转录错）。

    取 `per_backend.egl_nvidia.cams[cam].max_frac_diff_px_worst / max_mean_abs_diff_worst /
    max_abs_diff_worst`。读不到就返回 `available=false` 且**不自造阈值**（三值纪律）。
    """
    out = {"source_artifact": str(E_REPS5_ARTIFACT.relative_to(ROOT)),
           "source_regime": "same_state_repeat_render（egl_nvidia / reps=5 / 224×224）",
           "ruling": "裁定 85.5（§18.5）：像素只登记不判红 ⇒ 本带是**登记参照**，不是判据",
           "available": False, "per_cam": {}}
    if not E_REPS5_ARTIFACT.exists():
        out["warning"] = "E 的 n=5 产物不在 ⇒ 登记带缺失（只登记本批实测值，不做任何比对）"
        return out
    try:
        d = json.loads(E_REPS5_ARTIFACT.read_text(encoding="utf-8"))
        cams = ((d.get("per_backend") or {}).get("egl_nvidia") or {}).get("cams") or {}
        out["sha256_12"] = sha12(E_REPS5_ARTIFACT)
        out["mtime"] = _mtime(E_REPS5_ARTIFACT)
        out["reps"] = ((d.get("per_backend") or {}).get("egl_nvidia") or {}).get("reps")
        out["resolution"] = d.get("resolution")
        for cam, v in cams.items():
            if not isinstance(v, dict):
                continue
            out["per_cam"][cam] = {
                "frac_diff_px": v.get("max_frac_diff_px_worst"),
                "mean_abs_diff": v.get("max_mean_abs_diff_worst"),
                "max_abs_diff": v.get("max_abs_diff_worst"),
                "cross_process_same_sha": v.get("cross_process_same_sha"),
                "bitwise_deterministic_in_process_all_reps":
                    v.get("bitwise_deterministic_in_process_all_reps")}
        out["available"] = bool(out["per_cam"])
    except Exception as e:                                       # noqa: BLE001
        out["warning"] = "读 E 的产物失败：%s: %s" % (type(e).__name__, e)
    return out


def replay_img_tol_basis() -> dict:
    """把"这组容差凭什么能用"写成可核验的证据（文件在不在、sha、它自己声明的 regime/分辨率）。"""
    out = {"tolerance_ruling": "裁定 82⑤-3 / 83.4（D 定）",
           "tolerance": dict(REPLAY_IMG_TOL),
           "measurement_basis_artifact": str(E_REPS5_ARTIFACT.relative_to(ROOT)),
           "exists": E_REPS5_ARTIFACT.exists()}
    if E_REPS5_ARTIFACT.exists():
        d = json.loads(E_REPS5_ARTIFACT.read_text(encoding="utf-8"))
        out.update({"sha256_12": sha12(E_REPS5_ARTIFACT), "mtime": _mtime(E_REPS5_ARTIFACT),
                    "generator": d.get("generator"), "generator_sha256_12": d.get("generator_sha256_12"),
                    "reps": d.get("reps"), "cams": d.get("cams"), "resolution": d.get("resolution"),
                    "regime": (d.get("verdict") or {}).get("regime"),
                    "applies_when": (d.get("verdict") or {}).get("applies_when"),
                    "observed_worst": ((d.get("verdict") or {})
                                       .get("falsification_conditions_ruling_83_3") or {})
                    .get("observed_this_round"),
                    "resolution_matches_pi05_slots": (d.get("resolution") == [PI05_IMAGE_HW, PI05_IMAGE_HW]),
                    "resolution_matches_team_slots": (d.get("resolution") == [TEAM_VIDEO_H, TEAM_VIDEO_W])})
    else:
        out["warning"] = "E 的实测件不在 ⇒ 容差失去实测基础，图像侧一律判 N_A（不拿无基础的阈值判红）"
    return out


def accum_image_repeat(acc: Dict[str, dict], imgs_a: Dict[str, np.ndarray],
                       imgs_b: Dict[str, np.ndarray], mutation: Optional[str] = None) -> None:
    """同状态连渲两次的**增量**比对（不留图 ⇒ 内存与单渲相同；6 槽 ×275 帧的 uint8 约 1.8 GB，留不起）。

    `frac_diff_px` 有两个可能口径，本闸**两个都算**、判红用**更严的那个**（按像素：任一通道不同即算该像素不同）：
    逐像素占比 ≥ 逐元素占比，所以用它判红不会放过事。E 的产物没写清是哪个口径 ⇒ 两个都登记，
    并在 `frac_diff_px_definition` 里写明本闸用的是哪个。
    """
    for slot, a in imgs_a.items():
        a = np.asarray(a, dtype=np.uint8)
        b = np.asarray(imgs_b[slot], dtype=np.uint8)
        injected = False
        if mutation in (MUT_IMG_PIXEL_ONLY, MUT_IMG_PIXEL_ONLY_ALIAS) and slot == MUT_IMG_SLOT:
            # 变异体：只污染**比对用的那一份副本**，落盘的数据集图像不动
            #（变异体的用途是证明牙会咬 / 证明已降级的牙**不会**咬，不是产坏数据）。
            b = b.copy()
            bf = b.reshape(-1)
            n = max(1, int(round(bf.size * MUT_IMG_FRAC)))
            idx = np.random.default_rng(20260930).choice(bf.size, size=n, replace=False)
            bf[idx] = np.clip(bf[idx].astype(np.int32) + MUT_IMG_DELTA, 0, 255).astype(np.uint8)
            injected = True
        if a.shape != b.shape:
            acc[slot] = {"slot": slot, "shape_mismatch": [list(a.shape), list(b.shape)]}
            continue
        d = np.abs(a.astype(np.int16) - b.astype(np.int16))
        e = acc.setdefault(slot, {"slot": slot, "shape": list(a.shape), "n_frames": 0,
                                  "n_frames_bitwise": 0, "max_abs_diff": 0, "sum_abs_diff": 0.0,
                                  "n_elements": 0, "n_elements_diff": 0,
                                  "n_pixels": 0, "n_pixels_diff_any_channel": 0,
                                  "worst_frame_index": None, "mutation_injected": False})
        e["n_frames"] += 1
        mx = int(d.max()) if d.size else 0
        if mx > e["max_abs_diff"]:
            e["max_abs_diff"] = mx
            e["worst_frame_index"] = e["n_frames"] - 1
        if mx == 0:
            e["n_frames_bitwise"] += 1
        e["sum_abs_diff"] += float(d.sum())
        e["n_elements"] += int(d.size)
        e["n_elements_diff"] += int((d != 0).sum())
        n_px = int(np.prod(a.shape[:2])) if a.ndim >= 2 else int(d.size)
        e["n_pixels"] += n_px
        e["n_pixels_diff_any_channel"] += int((d != 0).reshape(n_px, -1).any(axis=1).sum())
        e["mutation_injected"] = bool(e["mutation_injected"] or injected)


def finalize_image_repeat(acc: Dict[str, dict], regime: str = "same_state_repeat_render") -> dict:
    band_doc = e_reps5_per_cam_band()
    band_per_cam = band_doc.get("per_cam") or {}
    per = {}
    for slot, e in acc.items():
        if e.get("shape_mismatch"):
            per[slot] = e
            continue
        f = dict(e)
        f["frac_diff_px"] = (f["n_pixels_diff_any_channel"] / f["n_pixels"]) if f["n_pixels"] else None
        f["frac_diff_elements"] = (f["n_elements_diff"] / f["n_elements"]) if f["n_elements"] else None
        f["mean_abs_diff"] = (f["sum_abs_diff"] / f["n_elements"]) if f["n_elements"] else None
        f["all_frames_bitwise"] = bool(f["n_frames"] > 0 and f["n_frames_bitwise"] == f["n_frames"])
        f["within_tolerance"] = bool(
            f["max_abs_diff"] <= REPLAY_IMG_TOL["max_abs_diff"]
            and (f["frac_diff_px"] is not None and f["frac_diff_px"] <= REPLAY_IMG_TOL["frac_diff_px"])
            and (f["mean_abs_diff"] is not None and f["mean_abs_diff"] <= REPLAY_IMG_TOL["mean_abs_diff"]))
        f["tolerance_exceeded"] = {
            k: {"tolerance": REPLAY_IMG_TOL[k], "measured": f.get(k),
                "exceeded": bool(f.get(k) is not None and f[k] > REPLAY_IMG_TOL[k])}
            for k in ("max_abs_diff", "frac_diff_px", "mean_abs_diff")}
        # ---- 登记带（E 的 n=5 逐相机实测）：裁定 85.5 ⇒ **超带只登记，不判红** ----
        cam = SLOT_CAMERA.get(slot)
        band = band_per_cam.get(cam) or {}
        f["camera"] = cam
        f["register_band_e_reps5"] = dict(band) if band else None
        f["register_band_exceeded"] = {
            k: {"band": band.get(k), "measured": f.get(k),
                "exceeded": bool(band.get(k) is not None and f.get(k) is not None
                                 and f[k] > band[k])}
            for k in ("max_abs_diff", "frac_diff_px", "mean_abs_diff")} if band else None
        f["within_register_band"] = (
            None if not band else
            not any(v["exceeded"] for v in f["register_band_exceeded"].values()))
        f.pop("sum_abs_diff", None)
        per[slot] = f
    return {"regime": regime,
            "regime_note": ("**同一状态连渲两次**（不是跨进程、不是重放整条动作序列）。"
                            "为什么这个 regime 对：G4 已把三 pass 的**状态**判成逐位相同 ⇒ "
                            "图像侧能差的只剩渲染器本身，与 E 的 `same_state_repeat_render` 同口径。"),
            "frac_diff_px_definition": "按像素：任一通道不同即算该像素不同（比逐元素口径更严）",
            "blocking": False,
            "pixel_judges_red": False,
            "ruling_85_5": ("裁定 85.5（§18.5）：**硬判据只剩「状态逐位」（G4）**；三相机像素一律"
                            "**只登记不判红**。本 dict 里的 `within_tolerance` / `within_register_band` / "
                            "`tolerance_exceeded` / `register_band_exceeded` **全是登记项**，"
                            "任何下游都不得拿它们判红（新红线 `render_bitwise_equality_ban_on_egl`）。"),
            "register_band": band_doc,
            "tolerance_basis": replay_img_tol_basis(),
            "per_slot": per}

TASK_DIR = {"forward": "transfer_cube_right_to_left", "reverse": "transfer_cube_left_to_right"}
TASK_TEXT_PROPOSED = {"forward": "Transfer the red cube from the right arm to the left arm.",
                      "reverse": "Transfer the red cube from the left arm to the right arm."}
TASK_TEXT_STATUS = {"forward": "verbatim_from_a2_contract_args_task",
                    # 裁定 85.3（§18.3）：D **批准** RR-B2-10 的反向串（主/宾精确镜像），
                    # 并已核一致性（正向落 `transfer_cube_right_to_left`、终态被 left 夹爪握住、
                    # `reward=4`；反向 `reward=2` ≠ 4 ⇒ 满足 G1 的必红条件）。
                    # **两串一经采用即训练/评测共用的条件信号 ⇒ 改串 = 换 representation_version**；
                    # 本轮用的就是被批准的逐字串 ⇒ `REPRESENTATION_VERSION` 维持 `-v1` 冻结不变。
                    "reverse": "d_approved_ruling_85_3_rr_b2_10_verbatim_frozen"}
DIRECTION_LABEL = {"forward": "right_to_left", "reverse": "left_to_right"}
REVERSE_DIRECTION_LABEL = "left_to_right"
DATA_KIND = "sim_demonstration_scripted_expert"
DATASET_KIND = "sim_demonstration_bidirectional"
REPRESENTATION_VERSION = ("b2-s1-sim-bidir-aloha14d-dt0.034-29.4118hz-"
                          "grip14_to_qpos_pair(+v,-v)-team480x640+pi05x224-v1")
LEROBOT_REPO_ID = "b2/sim_transfer_cube_bidir_29p4118hz"
SUBTASK_GROUPS = (
    (("pick_approach", "pick_descend", "pick_close"),
     "approach and grasp the cube with the {pick} arm"),
    (("pick_lift",), "lift the cube with the {pick} arm"),
    (("carry", "place_lower", "place_release"),
     "carry the cube to the handover point and release it to the {receive} arm"),
    (("pick_retract", "recv_approach", "recv_descend", "recv_close"),
     "retract the {pick} arm while the {receive} arm approaches and grasps the cube"),
    (("recv_lift", "recv_hold"), "lift and hold the cube with the {receive} arm"),
)
PREFIX_CANDIDATES = ("/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01",)
RECYCLE_BIN = Path("/workspace/mnt/sppro/yhzhang91/recycle_bin")


def fps_rational(dt: float) -> str:
    """把控制周期写成 ffmpeg/ffprobe 都原样保留的**有理帧率**（`500/17` = 29.411764705882355）。

    为什么不用小数：`-r 29.411764705882355` ffmpeg 也会归一成 `500/17`（B2 2026-09-29 23:0x 实测
    五个变体全给 `r_frame_rate=500/17 avg_frame_rate=500/17`），但**写有理数才自证**"这不是四舍五入
    到 30"。变异臂 `dt-back-to-50hz`（DT=0.02）⇒ 本函数给 `50/1` ⇒ 容器 50 Hz ⇒ 团队 V04/J
    与本脚本 G3 都必须红。
    """
    from fractions import Fraction
    f = Fraction(dt).limit_denominator(10 ** 6)
    inv = Fraction(f.denominator, f.numerator)
    return "%d/%d" % (inv.numerator, inv.denominator)


def joint_xml_path() -> str:
    """关节模型（`AlohaTransferCube-v0` 用的那个，`nu=16`）的 XML 绝对路径（裁定 66：示范在这里采）。"""
    import gym_aloha
    return str(Path(gym_aloha.__file__).resolve().parent / "assets" /
               "bimanual_viperx_transfer_cube.xml")


# ========================================================================== 取证工具
def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sha12(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def loadavg3() -> List[float]:
    a = os.getloadavg()
    return [round(a[0], 2), round(a[1], 2), round(a[2], 2)]


def cpu_stat() -> dict:
    for cand in ("/sys/fs/cgroup/cpu.stat", "/sys/fs/cgroup/cpu/cpu.stat"):
        p = Path(cand)
        if p.exists():
            out = {"source": cand}
            for line in p.read_text().splitlines():
                k, _, v = line.partition(" ")
                try:
                    out[k] = int(v)
                except ValueError:
                    out[k] = v
            return out
    return {"source": None}


def nvidia_smi() -> dict:
    out = {}
    for tag, q in (("gpu", "memory.used,utilization.gpu,temperature.gpu"),):
        try:
            p = subprocess.run(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=30)
            out[tag] = {"ok": p.returncode == 0, "stdout": p.stdout.strip()}
        except Exception as e:                                   # noqa: BLE001
            out[tag] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    try:
        p = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                            "--format=csv"], capture_output=True, text=True, timeout=30)
        out["compute_apps_verbatim"] = p.stdout.strip()
    except Exception as e:                                       # noqa: BLE001
        out["compute_apps_verbatim"] = f"ERROR {type(e).__name__}: {e}"
    return out


def foreign_gpu_line_processes(exclude_pids: Optional[Set[int]] = None) -> List[dict]:
    """归线进程清单（信号② 的输入），**含本线 b2**（裁定 85.6-2 两处 + 裁定 96.1-③ 第三处）。

    ① 自己**按 PID（本进程 + 祖先）排除**，不再按脚本名排除：按名字排除会让「第二个
       `b2_s1_generate_dataset.py` 作业」**隐形**，而那正是 D 的牙③要求必须被看见的东西。
    ② 输出**包含 `b2` 归线**（旧版只留 a2/c2/e/other ⇒ 本线的并发作业永远不进产物，
       于是"归线且 pcpu>1%"这条信号对本线恒假 = 恒真的镜像毛病）。
    ③ **裁定 96.1-③ / RR-B2-18（本次修）**：归线与纳入都改按 **argv 的执行位**判，不再按
       `args` 全文的字面量判；旧版那句 `tag == "other" and "RL_Robot" in args` **已删** ——
       它让任何「在文本里提到仓库路径」的纯 CPU 进程（agent 的 grep/sed/heredoc、遗留 shell）
       都进清单，是 `contaminated_by_cotenant` **永久为真**的根因之一。
       计入信号② = 执行位上真有线内脚本（`line_job_evidence`）∧ 非闲置 ∧ `pcpu>1%`；
       网③ 计入的行也一并返回（供 `contamination_verdict` 与产物登记）。
       **被看见但不计入的行照样返回**并带 `not_counted_reason`（三值纪律：不静默丢证据）。
    """
    try:
        p = subprocess.run(["ps", "-eo", "pid,etimes,pcpu,args", "--no-headers"],
                           capture_output=True, text=True, timeout=30)
    except Exception as e:                                       # noqa: BLE001
        return [{"error": f"{type(e).__name__}: {e}"}]
    out = []
    excl = set(exclude_pids if exclude_pids is not None else own_tree_pids())
    for line in p.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, etimes, pcpu, args = parts
        if not pid.isdigit() or int(pid) in excl:
            continue
        ipid = int(pid)
        argv = _argv(ipid)
        if not argv:            # 取不到 cmdline ⇒ 无从判执行位（与旧版 `if not cl: continue` 同）
            continue
        ticks, state = _proc_cpu(ipid)
        lj = line_job_evidence(argv, cpu_ticks=ticks, proc_state=state)
        cl = classify_cmdline(argv, cpu_ticks=ticks, proc_state=state)
        if not (lj["counted_toward_signal2"] or cl["counted_toward_busy"]
                or lj["line_script_text_anywhere"] or cl["classification"] != "no_keyword"):
            continue            # 既不计入、也不是「提到过线内脚本/关键字」的证据行 ⇒ 与本判定无关
        fpcpu = float(pcpu)
        active_pcpu = fpcpu > GPU_LINE_ACTIVE_PCPU
        out.append({"pid": ipid, "etimes_s": int(etimes), "pcpu": fpcpu,
                    "line_tag": lj["line_tag"], "args": args[:200],
                    # 行级键把裁定 73/85.6-2 的 `pcpu>1%` 折进来（`line_job_evidence` 只报
                    # 「执行位 ∧ 非闲置」那一半，两半合起来才是信号②）
                    "counted_toward_signal2": bool(lj["counted_toward_signal2"] and active_pcpu),
                    "not_counted_reason": (
                        None if (lj["counted_toward_signal2"] and active_pcpu) else
                        (lj["not_counted_reason"] or
                         ("pcpu=%s ≤ %s%% ⇒ 不是活跃作业（裁定 73 的判据是「非本线 **GPU** 进程」，"
                          "不是「任何含仓库名的 CPU 进程」）" % (fpcpu, GPU_LINE_ACTIVE_PCPU)))),
                    "exec_form": lj["exec_form"], "exec_form_kind": lj["exec_form_kind"],
                    "exec_script": lj["exec_script"], "cpu_ticks": ticks, "proc_state": state,
                    "idle": lj["idle"], "net3_classification": cl["classification"],
                    "net3_counted_toward_busy": cl["counted_toward_busy"],
                    "caliber": lj["caliber"]})
    return out


def parse_compute_apps(verbatim: str) -> List[dict]:
    """解析 `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv` 原文。"""
    rows = []
    for ln in (verbatim or "").splitlines()[1:]:
        parts = [x.strip() for x in ln.split(",")]
        if len(parts) >= 3 and parts[0].isdigit():
            rows.append({"pid": int(parts[0]), "process_name": parts[1],
                         "used_memory_mib": parts[2]})
    return rows


# ---- 「卡上有没有别人」的**三网并查**（裁定 85.6-2 / §18.6-2；口径复用 E 的 `card_busy`）----
# 为什么必须三网：`nvidia-smi --query-compute-apps` **只列已分配显存的进程**，对
# 「已起 EGL 图形上下文但没分配 compute 显存」的进程是**盲的**（这正是 A2 的 rep4/rep5 被
# 判 `undetermined_detector_blind_to_egl` 的根因，也是 23:58 抢卡事故的根因）。
# 网①`compute-apps` + 网②`/proc/*/fd` 里的 `/dev/nvidia*` 持有者 + 网③ cmdline。
# **「外来」的口径是线相对的**：E 的 `OTHER_LINE_SCRIPT_RE` 是 `scripts/(a2?|b2?|c2?|d)_`
# （E 自己按 PID 排除）⇒ B2 的同口径版本排除 **b2_**，本线的并发作业改由信号②
# （归线 + `pcpu>1%`）承载 —— 这样 D 的牙③（第二个 b2 采集作业）仍然必被看见，
# 而"agent 自己 `sed` 一下 b2 脚本"这种瞬时 shell 不会把每份产物永久标 contaminated。
OTHER_LINE_SCRIPT_RE = re.compile(r"(?<!\w)scripts/(a2?|c2?|e|d)_")
GPU_INTENT_PATTERNS = (
    # 前 11 条与 E 的 `GPU_INTENT_PATTERNS` **逐字一致**（"复用 E 的实现口径"）
    "a2_egl_latency_remeasure", "a2_pi05_zeroshot_eval", "a2_s4a_vla_runtime_verify",
    "vla_runtime", "torchrun", "accelerate", "deepspeed", "lerobot-train",
    "--expect-renderer", "--mode closed_loop", "quiet_window",
    # 以下是 B2 侧补的（同性质：明确要上卡/要渲染的入口）
    "c2_collect_env_states", "c2_build_norm_stats", "e_mainline_render_calib",
    "MUJOCO_GL=egl", "--allow-cotenant", "ballast",
)


# ---- 裁定 96.1-③ / **RR-B2-18**（同族同因、同批修）：网③ 与信号② 的判据由「裸关键字」
#      改为「**真实执行形态 ∧ 关键字 ∧ 非闲置**」 ----
# 缺陷原文（B2 自报；`work/project_parameters.json →
# operations/card_busy_text_false_positive_fix_rev21/same_family_same_batch`）：
#   「`scripts/b2_s1_generate_dataset.py` 的 `tag=="other" and "RL_Robot" in args`
#     ⇒ `contaminated_by_cotenant` **永久为真**」。
# 根因（D 认定，裁定 96.1-③）：网在匹配「关于 GPU 的**文本**」，不是「GPU **占用**」。
#   旧 `cmdline_net()` 两档同样是裸字面量匹配 ⇒ agent 自己 `grep -n torchrun scripts/e_*.py`
#   就能让 `card_busy_three_net()` 报忙：轻则把权威吞吐/延迟数字标脏（狼来了 ⇒ 标志失效），
#   重则让裁定 73 的起跑硬闸拒绝起跑（六步序列第 1–3 步全部要上卡 ⇒ 白跑一轮）。
# 口径出处（**读别人的工具、写自己的文件**，裁定 96.1-③ 明示可复用；不另造口径）：
#   `EXEC_FORM_RE` 逐字来自 F 的只读探针 `scripts/f_probe_card_busy.py`；E 已把同一修法落进
#   参考实现 `scripts/e_mainline_render_calib.py`（`classify_cmdline` 是纯函数）。**本件不 import
#   它们**（避免采集器多一个跨线运行时依赖），改为自带同判据的实现 + 强制对齐探针
#   `cmdline_caliber_alignment_probe()`：跑 `--selftest-cotenant-detector` /
#   `--selftest-cmdline-caliber` 时**现取**两件的身份与判据、逐行等价对账，取不到 ⇒ `not_measured`
#   + 非零退出（裁定 89.7 / 96.1-①：活件身份不写死在注释里，漂移必须被机器看见，裁定 46.4）。
EXEC_FORM_RE = re.compile(r"(?:^|\s)(?:\S*python\S*|\S*/bin/\S+)\s+\S*scripts/(?:a2?|b2?|c2?|d|e|f)_\S+")
# 反漏检腿（与 E 的参考实现同）：argv0 **本身就是** GPU 启动器时，即使后面没有
# `scripts/<line>_*.py` 也算真实执行形态（只收紧成「必须带线内脚本路径」会把它漏掉）。
GPU_LAUNCHER_ARGV0 = ("torchrun", "accelerate", "deepspeed", "lerobot-train")
GPU_LAUNCHER_MODULES = ("torch.distributed.run", "torch.distributed.launch",
                        "accelerate.commands.launch")
# 闲置判据沿用 E 的**定标实测**（真跑诱饵 26 tick vs 闲置载体 0 tick，裕度 26×；出处
# `runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json → idle_threshold_calibration`）：
# 累计 CPU ≤1 tick（10 ms @ `SC_CLK_TCK`=100）且状态 ∈ {S,T,Z} ⇒ 自启动以来几乎没执行过指令。
# 取不到 `/proc/<pid>/stat` ⇒ **不**判闲置（宁可过判不可漏判）；`D` 态同理**不**排除 ——
# 那正是「已起跑、尚未分配显存」的盲区（23:58 抢卡事故）。
IDLE_CPU_TICKS = 1
IDLE_PROC_STATES = ("S", "T", "Z")
# 线内脚本路径（信号② 的**执行位**归线用；与 `OTHER_LINE_SCRIPT_RE` 不同，它**含** b2）
LINE_SCRIPT_RE = re.compile(r"(?<!\w)scripts/(a2?|b2?|c2?|d|e|f)_[\w.\-]+")
LINE_TAGS_FOR_SIGNAL2 = ("a2", "b2", "c2", "e")     # 档位沿用旧版，不新造（裁定 31.4）
CALIBER_REFERENCE_E = "scripts/e_mainline_render_calib.py"   # 参考实现（E 线，13:1x 修完）
CALIBER_REFERENCE_F = "scripts/f_probe_card_busy.py"         # `EXEC_FORM_RE` 的出处（F 线只读探针）
# 与参考实现**必须逐字相同**的常量（对齐探针 leg A 的对象）
SHARED_CALIBER_CONSTANTS = ("EXEC_FORM_RE", "GPU_LAUNCHER_ARGV0", "GPU_LAUNCHER_MODULES",
                            "IDLE_CPU_TICKS", "IDLE_PROC_STATES")
# 与参考实现**必须行为等价**的判定字段（对齐探针 leg B 的比较面；B2 自加的证据键不在内）
SHARED_CLASSIFY_KEYS = ("classification", "exec_form", "exec_form_kind", "idle",
                        "counted_narrow", "counted_broad", "counted_toward_busy")
CALIBER_RULING_96_1_3 = ("裁定 96.1-③：真实执行形态（`EXEC_FORM_RE`，或 argv0 ∈ GPU 启动器，"
                         "或 `python -m` ∈ 分布式启动器模块）∧ 关键字 ∧ 非闲置"
                         "（累计 CPU ≤%d tick 且状态 ∈ %s）⇒ 计入；**裸关键字提及不计入**"
                         % (IDLE_CPU_TICKS, list(IDLE_PROC_STATES)))


def _argv(pid: int) -> List[str]:
    """`/proc/<pid>/cmdline` 的**原始 argv 列表**（不拼接、不截断）。

    `_proc_cmdline()` 是给产物记录用的（拼接 + 截断 400）；而「关键字出现在**执行位**还是
    **文本位**」必须按 argv 边界判（裁定 96.1-③），所以另取一份列表。取不到 ⇒ `[]`。
    """
    try:
        raw = Path("/proc/%d/cmdline" % pid).read_bytes()
    except OSError:
        return []
    return [a.decode(errors="ignore") for a in raw.split(b"\0") if a][:64]


def _proc_cpu(pid: int) -> Tuple[int, str]:
    """`(累计 utime+stime tick, 进程状态单字母)`；取不到 ⇒ `(-1, "")` = **不**判闲置。"""
    try:
        stat = Path("/proc/%d/stat" % pid).read_text(errors="ignore")
    except OSError:
        return -1, ""
    tail = stat.rsplit(")", 1)[-1].split()
    try:
        return int(tail[11]) + int(tail[12]), tail[0]
    except (IndexError, ValueError):
        return -1, ""


def exec_form_of(argv: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
    """真实执行形态判定 ⇒ `(kind, 执行位上的线内脚本 token)`；无形态 ⇒ `(None, None)`。"""
    joined = " ".join(argv)[:4000]
    m = EXEC_FORM_RE.search(joined)
    if m:
        sm = LINE_SCRIPT_RE.search(m.group(0))
        return "interpreter_plus_line_script", (sm.group(0) if sm else None)
    argv0 = argv[0] if argv else ""
    base0 = argv0.rsplit("/", 1)[-1]
    if base0 in GPU_LAUNCHER_ARGV0:
        return "gpu_launcher_in_argv0", None
    if base0.startswith("python") and len(argv) > 2 and argv[1] == "-m" \
            and argv[2] in GPU_LAUNCHER_MODULES:
        return "gpu_launcher_module", None
    return None, None


def line_tag_of_script(script: Optional[str]) -> str:
    """按**执行位**上的脚本名归线（旧版按 args **全文**归线 ⇒ RR-B2-18 的一半根因）。

    档位沿用旧版（`a2`/`b2`/`c2`/`e`/`other`），**不新造**（裁定 31.4）。
    """
    if not script:
        return "other"
    base = script.rsplit("/", 1)[-1]
    for tag in ("b2_", "a2_", "c2_", "e_"):
        if base.startswith(tag):
            return tag[:-1]
    return "other"


def classify_cmdline(argv: Sequence[str], *, cpu_ticks: int = -1, proc_state: str = "",
                     intent_patterns: Sequence[str] = GPU_INTENT_PATTERNS,
                     other_line_re: Optional["re.Pattern[str]"] = None) -> dict:
    """把一个进程的 argv 分成 `real_gpu_work` / `text_mention_only` / `idle_text_mention` / `no_keyword`。

    **纯函数**（不读 `/proc`、不起进程、不碰 GPU）⇒ 既能被对照探针两向注入（裁定 93.8），
    也能拿「历史上真实出现过的 argv」重放。判据与 E 的参考实现 `classify_cmdline` 逐键等价，
    等价性由 `cmdline_caliber_alignment_probe()` 每次现取对账（裁定 46.4 的副本漂移防护）。
    `intent_patterns` / `other_line_re` 可注入：**「外来」的口径是线相对的**（B2 的宽档排除
    `b2_`、E 的排除 `e_`）⇒ 对账时用 E 的词表喂本函数，才能比「逻辑」而不是比「口径」。
    """
    othre = other_line_re if other_line_re is not None else OTHER_LINE_SCRIPT_RE
    joined = " ".join(argv)[:4000]
    intent = ["gpu_intent:%s" % pat for pat in intent_patterns if pat in joined]
    broad = ["other_line_script"] if othre.search(joined) else []
    kind, script = exec_form_of(argv)
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
    return {"argv0": (argv[0] if argv else ""), "exec_form": kind is not None,
            "exec_form_kind": kind, "exec_script": script,
            "gpu_intent_matched": intent[:4], "other_line_script_matched": broad,
            "cpu_ticks": cpu_ticks, "cpu_ticks_known": ticks_known, "proc_state": proc_state,
            "idle": idle, "counted_toward_busy": counted, "classification": classification,
            "counted_narrow": bool(counted and intent), "counted_broad": bool(counted and broad),
            "cmdline_head": " ".join(joined.split())[:200],
            "caliber": CALIBER_RULING_96_1_3}


def line_job_evidence(argv: Sequence[str], *, cpu_ticks: int = -1, proc_state: str = "") -> dict:
    """信号②（归线活跃作业）的判据：**执行位上真有线内脚本 ∧ 非闲置**。

    **为什么不加「∧ GPU 关键字」**：牙③（裁定 85.6-2）要求「args 含
    `scripts/b2_s1_generate_dataset.py`、`pcpu>1%`、**完全不碰 GPU**」的第二个采集作业**必须被
    看见**；而一条真的 `python scripts/b2_s1_generate_dataset.py --stage formal` 在 B2 的
    线相对宽档里**一个关键字都不命中**（宽档排除 `b2_`，本线由信号② 承载）⇒ 给信号② 加关键字
    合取就会把牙③ 判死，那正是本次修法要避免的「收紧到漏检」。关键字合取只加在**网③**上。
    只返回布尔证据 + 散文理由，**不新造分类档位**（裁定 31.4）。
    """
    joined = " ".join(argv)[:4000]
    kind, script = exec_form_of(argv)
    tag = line_tag_of_script(script)
    ticks_known = cpu_ticks >= 0
    idle = bool(ticks_known and cpu_ticks <= IDLE_CPU_TICKS and proc_state in IDLE_PROC_STATES)
    counted = bool(kind is not None and script is not None
                   and tag in LINE_TAGS_FOR_SIGNAL2 and not idle)
    if kind is None:
        reason = ("argv 里没有真实执行形态（线内脚本名只出现在**文本位**）⇒ 不计入信号②"
                  "（裁定 96.1-③；RR-B2-18 的根因形态）")
    elif script is None:
        reason = "有执行形态但执行位不是线内脚本（`scripts/<line>_*.py`）⇒ 不计入信号②"
    elif tag not in LINE_TAGS_FOR_SIGNAL2:
        reason = "执行位脚本归线 `%s`（不属 %s）⇒ 不计入信号②" % (tag, list(LINE_TAGS_FOR_SIGNAL2))
    elif idle:
        reason = ("闲置（累计 CPU %s tick ≤ %s 且状态 `%s` ∈ %s）⇒ 不计入信号②"
                  % (cpu_ticks, IDLE_CPU_TICKS, proc_state, list(IDLE_PROC_STATES)))
    else:
        reason = None
    return {"exec_form": kind is not None, "exec_form_kind": kind, "exec_script": script,
            "line_tag": tag, "cpu_ticks": cpu_ticks, "cpu_ticks_known": ticks_known,
            "proc_state": proc_state, "idle": idle,
            "line_script_text_anywhere": bool(LINE_SCRIPT_RE.search(joined)),
            "repo_name_text_anywhere": "RL_Robot" in joined,
            "counted_toward_signal2": counted, "not_counted_reason": reason,
            "caliber": ("裁定 96.1-③（执行位 ∧ 非闲置）+ 裁定 85.6-2 牙③（不要求 GPU 关键字，"
                        "否则第二个 B2 采集作业会隐形）")}


def _legacy_rr_b2_18_verdict(argv: Sequence[str], pcpu: Optional[float] = None) -> dict:
    """**只作差分对照**（裁定 93.8 的两向腿）—— 生产路径**不得**调用本函数。

    逐字复刻修法前（`b6af48fc6d58`）的两条判据：
      信号② 的纳入 = `tag in (a2,b2,c2,e) or (tag=="other" and "RL_Robot" in args)`，
                     tag 按 **args 全文**里出现 `/b2_`、`/a2_`、`/c2_`、`/e_` 归线；
      网③ 两档 = **裸字面量**匹配 `GPU_INTENT_PATTERNS` / `OTHER_LINE_SCRIPT_RE`。
    没有它，「修好了」这句话就没有对照物：探针必须能同时展示**旧判据会误判**（负向腿）
    与**新判据不漏判**（正向腿），只装一向不许报绿（缺陷类 ⑲）。
    """
    args = " ".join(argv)
    tag = ("b2" if "/b2_" in args or " b2_" in args else
           "a2" if "/a2_" in args else
           "c2" if "/c2_" in args else
           "e" if "/e_" in args else "other")
    listed = bool(tag in ("a2", "b2", "c2", "e") or (tag == "other" and "RL_Robot" in args))
    intent = [p for p in GPU_INTENT_PATTERNS if p in args]
    is_other_line = bool(OTHER_LINE_SCRIPT_RE.search(args))
    signal2 = bool(listed and tag in ("a2", "b2", "c2", "e")
                   and (pcpu is None or float(pcpu) > GPU_LINE_ACTIVE_PCPU))
    return {"line_tag_by_full_text": tag,
            "listed_by_foreign_gpu_line_processes": listed,
            "net3_narrow_hit": bool(intent), "net3_broad_hit": is_other_line,
            "signal2_active_line": signal2,
            "would_detect": bool(intent or is_other_line or signal2),
            "caliber": "修法前（RR-B2-18）：裸关键字 + args 全文归线 + 无闲置排除"}


def _proc_cmdline(pid: int) -> str:
    try:
        raw = Path("/proc/%d/cmdline" % pid).read_bytes().replace(b"\0", b" ").decode(errors="ignore")
    except OSError:
        return ""
    return " ".join(raw.split())[:400]


def own_tree_pids() -> Set[int]:
    """本进程 + 祖先（口径 = E 的 `_own_tree()`）。**按 PID 排除自己**，不按脚本名排除。"""
    pids = {os.getpid()}
    pid = os.getpid()
    for _ in range(8):
        try:
            stat = Path("/proc/%d/stat" % pid).read_text(errors="ignore")
            ppid = int(stat.rsplit(")", 1)[-1].split()[1])
        except (OSError, IndexError, ValueError):
            break
        if ppid <= 1 or ppid in pids:
            break
        pids.add(ppid)
        pid = ppid
    return pids


def _proc_pcpu() -> Dict[int, float]:
    out: Dict[int, float] = {}
    try:
        p = subprocess.run(["ps", "-eo", "pid,pcpu", "--no-headers"],
                           capture_output=True, text=True, timeout=30)
    except Exception:                                            # noqa: BLE001
        return out
    for ln in p.stdout.splitlines():
        parts = ln.split()
        if len(parts) >= 2 and parts[0].isdigit():
            try:
                out[int(parts[0])] = float(parts[1])
            except ValueError:
                continue
    return out


def nvidia_fd_holders(exclude_pids: Set[int]) -> List[dict]:
    """网②：扫全部可见进程的 `/proc/*/fd`，找**已持有 `/dev/nvidia*` 的进程**。

    比 `compute-apps` 早一步也**宽一步**：EGL 图形上下文持有 `/dev/nvidiactl` +
    `/dev/nvidia0` 却可能**永不出现**在 `compute-apps` 里（没分配 compute 显存）。
    """
    hits = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return hits
    pcpu = _proc_pcpu()
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in exclude_pids:
            continue
        try:
            fds = os.listdir("/proc/%d/fd" % pid)
        except OSError:
            continue
        devs = set()
        for fd in fds:
            try:
                target = os.readlink("/proc/%d/fd/%s" % (pid, fd))
            except OSError:
                continue
            if target.startswith("/dev/nvidia"):
                devs.add(target)
        if devs:
            hits.append({"pid": pid, "nvidia_devs": sorted(devs), "pcpu": pcpu.get(pid),
                         "cmdline": _proc_cmdline(pid)})
    return hits


def cmdline_net(exclude_pids: Set[int], strict: bool) -> dict:
    """网③：cmdline 网，**两档**（口径 = E 的 `other_line_gpu_intent` + 裁定 96.1-③ 的执行形态门槛）。

    窄档 `gpu_intent`：cmdline 里出现明确的上卡入口/关键字 ⇒ 很可能要上卡（即使还没分配显存）。
    宽档 `other_line_script`：cmdline 里出现**任何他线**脚本（`scripts/{a,a2,c2,e,d}_*`）。
    `strict=True`（起跑硬闸 / 污染判定的信号①′）两档都算；`strict=False`（批级让路闸）只算窄档。

    **裁定 96.1-③ / RR-B2-18（本次修）**：两档都加同一个门槛 —— **真实执行形态 ∧ 非闲置**。
    旧版是裸字面量匹配，于是「关于 GPU 的**文本**」被当成「GPU **占用**」：agent 自己
    `grep -n torchrun scripts/e_*.py` 就能让本网报忙（F 实测两起：PID 214244 = `text_mention_only`
    被计入宽档；同时 PID 214254/214257 两条真跑被正确分类）。
    不计入的行**不丢**：分别落进 `text_mention_only` / `idle_text_mention` 两个桶并写明理由
    （三值纪律 + 反漏检可核：收紧了多少、收紧掉的是什么，产物里看得见）。
    """
    narrow, broad, text_only, idle_only = [], [], [], []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return {"narrow_gpu_intent": narrow, "broad_other_line_script": broad,
                "hits": [], "strict": strict,
                "text_mention_only": text_only, "idle_text_mention": idle_only,
                "measurement_status": "not_measured",
                "not_measured_reason": "/proc 读不到 ⇒ 本网没有测量，不是「测到没有命中」",
                "cmdline_net_caliber": CALIBER_RULING_96_1_3}
    pcpu = _proc_pcpu()
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
        c = classify_cmdline(argv, cpu_ticks=ticks, proc_state=state)
        if c["classification"] == "no_keyword":
            continue
        row = {"pid": pid, "pcpu": pcpu.get(pid), "cmdline": c["cmdline_head"],
               "gpu_intent": [x.split(":", 1)[-1] for x in c["gpu_intent_matched"]][:4],
               "classification": c["classification"], "exec_form": c["exec_form"],
               "exec_form_kind": c["exec_form_kind"], "exec_script": c["exec_script"],
               "cpu_ticks": ticks, "proc_state": state, "idle": c["idle"]}
        if c["counted_narrow"]:
            narrow.append(row)
        elif c["counted_broad"]:
            broad.append({**row, "other_line_script": True})
        elif c["classification"] == "idle_text_mention":
            idle_only.append({**row, "not_counted_reason":
                              "关键字与执行形态都在，但自启动以来累计 CPU %s tick ≤ %s 且状态 `%s`"
                              " ⇒ 闲置载体，不计入（裁定 96.1-③）"
                              % (ticks, IDLE_CPU_TICKS, state)})
        else:
            text_only.append({**row, "not_counted_reason":
                              "关键字只出现在**文本位**（argv 里没有真实执行形态）⇒ 这是「关于 GPU 的"
                              "文本」，不是「GPU 占用」，不计入（裁定 96.1-③；RR-B2-18 同族）"})
    hits = (narrow + [b for b in broad if b["pid"] not in {x["pid"] for x in narrow}]
            if strict else narrow)
    return {"narrow_gpu_intent": narrow, "broad_other_line_script": broad,
            "hits": hits, "strict": strict,
            "text_mention_only": text_only, "idle_text_mention": idle_only,
            "n_counted": len(hits), "n_not_counted_but_registered": len(text_only) + len(idle_only),
            "measurement_status": "measured",
            "cmdline_net_caliber": CALIBER_RULING_96_1_3,
            "own_line_excluded_from_broad_net": "b2（本线并发作业由信号② 承载，见 D 牙③）"}


def card_busy_three_net(exclude_pids: Optional[Set[int]] = None, strict: bool = True) -> dict:
    """三网并查（裁定 85.6-2 的 ①′）。任一网命中外来 ⇒ `busy=True`。

    **只有网③ 加了执行形态门槛**（裁定 96.1-③ / RR-B2-18）：网①（`compute-apps` 里已分配显存）
    与网②（已持有 `/dev/nvidia*` fd）是**占用本身的直接证据**，不是「关于 GPU 的文本」⇒
    一个字节都不改（这也是牙① 那条「持 fd 但闲置的进程必须仍被看见」得以成立的原因）。
    """
    excl = set(exclude_pids if exclude_pids is not None else own_tree_pids())
    smi = nvidia_smi()
    apps = parse_compute_apps(smi.get("compute_apps_verbatim") or "")
    compute = [a for a in apps if a["pid"] not in excl]
    fd_holders = nvidia_fd_holders(excl)
    cmd = cmdline_net(excl, strict)
    return {"busy": bool(compute or fd_holders or cmd["hits"]),
            "strict": strict,
            "net1_compute_apps": compute,
            "net2_nvidia_fd_holders": fd_holders,
            "net3_cmdline_hits": cmd["hits"],
            "net3_detail": cmd,
            "net3_text_mention_only": cmd.get("text_mention_only"),
            "net3_idle_text_mention": cmd.get("idle_text_mention"),
            "net3_caliber": cmd.get("cmdline_net_caliber"),
            "net3_measurement_status": cmd.get("measurement_status"),
            "excluded_own_pids": sorted(excl),
            "gpu_verbatim": (smi.get("gpu") or {}).get("stdout"),
            "compute_apps_verbatim": smi.get("compute_apps_verbatim"),
            "detection_note": ("三网并查；`compute-apps` 对「已起 EGL 上下文但未分配 compute 显存」"
                               "的进程是盲的，网②（fd）与网③（cmdline）补这个盲区"
                               "（23:58 抢卡事故 + A2 rep4/rep5 `undetermined_detector_blind_to_egl` 的根因）"),
            "caliber_source": ("E 的 `scripts/e_mainline_render_calib.py:card_busy/nvidia_fd_holders/"
                               "other_line_gpu_intent`（复用口径，不另造）；「外来」按线相对定义。"
                               "网③ 的执行形态门槛 = 裁定 96.1-③，`EXEC_FORM_RE` 出自 F 的只读探针"
                               "`scripts/f_probe_card_busy.py`；两件的身份与等价性由 "
                               "`cmdline_caliber_alignment_probe()` 每轮现取对账（裁定 46.4）")}
def gpu_preflight() -> dict:
    """**起跑前实测 GPU 是否空载 —— 三网并查**（裁定 85.6-2 / §18.6-2：旧版只查 `compute-apps`）。

    为什么必须有它：B2 2026-09-30 00:21 的 selftest 与 A2 的 `a2_egl_latency_remeasure.py
    --tag quiet_window_rep5` **同卡在跑**，两边产物都被判 contaminated —— 而当时 manifest 里
    还写着一句 23:45 时间点的"起跑前已实测 GPU 空载"（**陈旧断言与自己同文件的实测证据打脸**）。
    所以：判定必须来自**本次进程起跑那一刻**的 `nvidia-smi`，且发现外来 GPU 进程就**拒绝起跑**。

    为什么必须三网（裁定 85.6-2）：`compute-apps` **只列已分配 compute 显存的进程**，对
    「已起 EGL 图形上下文、还没分配显存」的他线作业是盲的（A2 的 rep4/rep5 因此被判
    `undetermined_detector_blind_to_egl`）。⇒ 网①`compute-apps` + 网②`/dev/nvidia*` fd 持有者
    + 网③ cmdline（strict=True：窄档 gpu_intent + 宽档他线脚本），口径复用 E 的 `card_busy`。
    **GL 上下文必须在硬闸之后才起**（`_init_gl_identity()` 在 main 里排在它后面），否则
    自己就成了网②的命中者。
    """
    three = card_busy_three_net(strict=True)
    excl = set(three["excluded_own_pids"])
    procs = foreign_gpu_line_processes(excl)
    foreign = three["net1_compute_apps"]
    own_line_active = [p for p in procs
                       if p.get("counted_toward_signal2")
                       and p.get("line_tag") in LINE_TAGS_FOR_SIGNAL2
                       and float(p.get("pcpu") or 0) > GPU_LINE_ACTIVE_PCPU]
    busy = bool(three["busy"])
    return {"ts": now_iso(), "own_pid": os.getpid(), "parent_pid": os.getppid(),
            "excluded_own_pids": sorted(excl),
            "nvidia_smi_gpu_verbatim": three.get("gpu_verbatim"),
            "compute_apps_verbatim": three.get("compute_apps_verbatim"),
            "compute_apps_parsed": parse_compute_apps(three.get("compute_apps_verbatim") or ""),
            "three_net": three,
            "net_hits": {"net1_compute_apps": len(three["net1_compute_apps"]),
                         "net2_nvidia_fd_holders": len(three["net2_nvidia_fd_holders"]),
                         "net3_cmdline": len(three["net3_cmdline_hits"])},
            "foreign_gpu_processes": foreign,
            "n_foreign_gpu_processes": len(foreign),
            "foreign_gpu_line_procs_by_name": procs,
            "own_line_active_jobs": own_line_active,
            "loadavg3": loadavg3(),
            "idle": (not busy),
            "detector": "three_net_strict（裁定 85.6-2；旧口径 compute_apps_only 已废）",
            "net3_caliber": three.get("net3_caliber"),
            "signal2_caliber": ("裁定 96.1-③：执行位归线（`line_job_evidence`）∧ 非闲置 ∧ "
                                "pcpu>%s%%；旧口径「args 全文含仓库名/脚本名」已废（RR-B2-18）"
                                % GPU_LINE_ACTIVE_PCPU),
            "net3_seen_but_not_counted": {"text_mention_only": three.get("net3_text_mention_only"),
                                          "idle_text_mention": three.get("net3_idle_text_mention")},
            "verdict": ("gpu_idle_three_net_clean" if not busy else "gpu_busy_three_net_hit"),
            "ruling": ("裁定 73（静默窗口制度）+ 裁定 85.6-2（三网化）+ 单卡优先权"
                       "**A2（已申报的标定窗）> B2（S1 采集）> C2 > E**（裁定 85.7，关键路径感知；"
                       "取代裁定 73 的 A2>C2>E>B2）")}


GPU_LINE_ACTIVE_PCPU = 1.0     # 归线进程 pcpu 超过它才算"活跃作业"（0.0% 的遗留 shell 不算）
LOADAVG_SWING_THRESHOLD = 5.0  # 裁定 73 的另一半：loadavg_1m 高出 ≥5 ⇒ 自动标 contaminated


def contamination_verdict(before: dict, after: dict, preflight: Optional[dict],
                          throttled_delta: Optional[int]) -> dict:
    """`contaminated` 判定（裁定 73 → **裁定 85.6-2 三网化**）：只由 GPU/并发作业占用驱动。

    第一版的判据是"任何 args 里含仓库名的进程"⇒ 一个 **7.4 小时前遗留的空闲 bash**
    （PID 39153、`pcpu=0.0`、`find / -name .codex-persist`）就能让每份产物永久标 contaminated
    —— 狼来了 ⇒ 这个标志会彻底失去意义，而它恰恰是"吞吐数字能不能当口径"的开关。
    现在三条信号驱动（**①已按裁定 85.6-2 改为 ①′**）：
      ①′ `card_busy_three_net(strict=True)` 的**外来命中**（网①`compute-apps` + 网②`/dev/nvidia*`
         fd 持有者 + 网③ cmdline 两档）——旧版只有网①，而网①**对 EGL 盲**：A2 的 rep4/rep5 就是
         因此被判 `undetermined_detector_blind_to_egl`（裁定 85.0-2-②）；
      ②  归线为 `a2_/b2_/c2_/e_` 且 **pcpu>1%** 的活跃作业（D 批准；`pcpu>1%` 正是排除
         PID 39153 那种空闲遗留 shell 的正确键）——**本线 b2 也算**，这是 D 牙③的对象；
      ③  `loadavg_1m` 前后摆幅 ≥5（D 批准）。
    被忽略的空闲进程**照样落进产物**并写明忽略理由（三值纪律：不许静默丢弃证据）。

    **裁定 96.1-③ / RR-B2-18（本次修）**：①′ 的网③ 与 ② 的「归线」都改按 **argv 的执行位**判，
    不再按字面量文本判。修前一条 `grep … scripts/e_*.py` 或一个 `cd …/RL_Robot` 的遗留 shell
    就能让本判定**永久为真** —— 那不是"检测到污染"，是判据在匹配「关于 GPU 的**文本**」。
    修后只有**真实执行形态 ∧ 非闲置**才计入；`pcpu>1%` 与 loadavg 摆幅两条照旧（它们是负载
    条件量，不是文本判定）。**被看见但不计入的行仍全部登记**（`net3_seen_but_not_counted` 与
    `idle_procs_seen_but_ignored`）⇒「收紧了多少、收紧掉的是什么」可核，不是把证据删掉。
    """
    own = {os.getpid(), os.getppid()}
    if preflight:
        own |= {preflight.get("own_pid"), preflight.get("parent_pid")}
    own |= set((preflight or {}).get("excluded_own_pids") or [])
    own.discard(None)

    gpu_apps = []
    for tag, snap in (("preflight", preflight or {}), ("before", before.get("nvidia_smi") or {}),
                      ("after", after.get("nvidia_smi") or {})):
        for a in parse_compute_apps(snap.get("compute_apps_verbatim") or ""):
            if a["pid"] not in own:
                gpu_apps.append({"snapshot": tag, **a})

    # ---- ①′ 三网的外来命中（裁定 85.6-2）----
    three_hits, net1_pids = [], set()
    for tag, snap in (("preflight", preflight or {}), ("before", before), ("after", after)):
        tn = snap.get("three_net") or {}
        for net in ("net1_compute_apps", "net2_nvidia_fd_holders", "net3_cmdline_hits"):
            for h in (tn.get(net) or []):
                if h.get("pid") in own:
                    continue
                row = {"snapshot": tag, "net": net, "pid": h.get("pid"),
                       "pcpu": h.get("pcpu"),
                       "detail": (h.get("nvidia_devs") or h.get("gpu_intent")
                                  or h.get("used_memory_mib") or h.get("process_name")),
                       "cmdline": (h.get("cmdline") or "")[:160]}
                three_hits.append(row)
                if net == "net1_compute_apps":
                    net1_pids.add(h.get("pid"))
    blind_spot = [h for h in three_hits if h["net"] != "net1_compute_apps"
                  and h["pid"] not in net1_pids]

    active_line, ignored_idle, net3_not_counted = [], [], []
    for tag, snap in (("preflight", preflight or {}), ("before", before), ("after", after)):
        tn = snap.get("three_net") or {}
        for bucket in ("net3_text_mention_only", "net3_idle_text_mention"):
            for h in (tn.get(bucket) or []):
                if h.get("pid") in own:
                    continue
                net3_not_counted.append({"snapshot": tag, "bucket": bucket, **h})
    for tag, snap in (("before", before), ("after", after)):
        for pr in (snap.get("cotenant_processes") or []):
            row = {"snapshot": tag, **pr}
            if pr.get("counted_toward_signal2") and pr.get("line_tag") in LINE_TAGS_FOR_SIGNAL2 \
                    and float(pr.get("pcpu") or 0) > GPU_LINE_ACTIVE_PCPU:
                active_line.append(row)
            else:
                row["ignored_reason"] = pr.get("not_counted_reason") or (
                    "line_tag=%s 且 pcpu=%s ≤ %s ⇒ 不是活跃 GPU 作业（裁定 73 的判据是"
                    "『非本线 **GPU** 进程』，不是『任何含仓库名的 CPU 进程』）"
                    % (pr.get("line_tag"), pr.get("pcpu"), GPU_LINE_ACTIVE_PCPU))
                ignored_idle.append(row)

    lb = (before.get("loadavg") or [None])[0]
    la = (after.get("loadavg") or [None])[0]
    swing = (round(abs(float(la) - float(lb)), 2) if (lb is not None and la is not None) else None)
    reasons = []
    if three_hits:
        reasons.append("三网并查命中 %d 条**外来**记录（网①compute-apps / 网②/dev/nvidia* fd / "
                       "网③cmdline）：%s"
                       % (len(three_hits), [(h["snapshot"], h["net"], h["pid"], h["pcpu"])
                                            for h in three_hits][:8]))
    elif gpu_apps:
        reasons.append("nvidia-smi 上有 %d 条**非本进程**的 GPU compute 记录：%s"
                       % (len(gpu_apps), [(a["snapshot"], a["pid"], a["used_memory_mib"])
                                          for a in gpu_apps][:6]))
    if active_line:
        reasons.append("窗内有 %d 条别线**活跃**作业（pcpu>%s%%）：%s"
                       % (len(active_line), GPU_LINE_ACTIVE_PCPU,
                          [(a["snapshot"], a["pid"], a["line_tag"], a["pcpu"]) for a in active_line][:6]))
    if swing is not None and swing >= LOADAVG_SWING_THRESHOLD:
        reasons.append("loadavg_1m 前后摆幅 %s ≥ %s（%s → %s）⇒ 吞吐数字是负载条件量"
                       % (swing, LOADAVG_SWING_THRESHOLD, lb, la))
    contaminated = bool(reasons)
    return {
        "contaminated_by_cotenant": contaminated,
        "reasons": reasons,
        "authority": ("not_authoritative_trend_reference_only" if contaminated
                      else "authoritative_ok"),
        "authority_scope": (
            "**只覆盖吞吐/时延类数字**（`wall_s`、`s_per_episode`、`nr_throttled_delta`、"
            "任何由它们推出的产能/排期）。示范数据的**内容**由 G4 的「状态逐位」判据 + "
            "`recorded_vs_norender`（渲染不扰动物理）承载，与主机负载无关 ⇒ "
            "`contaminated_by_cotenant=true` **不使数据集内容失效**，只把产能数字降为趋势参考"
            "（裁定 73 原文即「吞吐数字是负载条件量」）。"),
        "authority_scope_why_written": (
            "本轮实测到这个字段必须写：teeth2 那一跑的 `reasons` 只有 "
            "`loadavg_1m 摆幅 11.24 ≥ 5.0（19.73 → 8.49）`——即**主机变安静了**，"
            "与 GPU/数据一无关。若下游把 `contaminated=true` 读成「数据不可用」，"
            "就会把一个纯计时口径的标志误用成数据质量判据（裁定 27.1 的同型毛病）。"),
        "signals": {
            "signal_1_prime_three_net_hits": three_hits,
            "signal_1_prime_blind_spot_of_old_detector": blind_spot,
            "signal_1_prime_blind_spot_note": (
                "这些命中**只有网②/网③能看见**（旧判据只有网①`compute-apps`）⇒ 若本列表非空，"
                "就说明三网化确实补上了旧探测器的盲区（EGL 上下文不分配 compute 显存 ⇒ 网①看不见）"),
            "legacy_compute_apps_only_hits": gpu_apps,
            "foreign_active_gpu_line_procs": active_line,
            "signal_2_criterion": ("**执行位**归线 a2_/b2_/c2_/e_（`line_job_evidence`）∧ 非闲置 ∧ "
                                   "pcpu>%s%%（**含本线 b2**：D 的牙③要求第二个 b2 采集作业必须被"
                                   "看见）；**不要求 GPU 关键字** —— 加了就会把牙③ 判死（裁定 96.1-③ "
                                   "的关键字合取只加在网③ 上）" % GPU_LINE_ACTIVE_PCPU),
            "net3_seen_but_not_counted": net3_not_counted,
            "net3_seen_but_not_counted_note": (
                "网③ 收紧（裁定 96.1-③）后**被看见但不计入**的行：`text_mention_only` = 关键字只在"
                "文本位、`idle_text_mention` = 闲置载体。留在这里是为了让「收紧」可核（反漏检）："
                "若这里出现**真上卡**的形态，就是修法漏检 ⇒ 必须报 D，不许静默"),
            "caliber_ruling_96_1_3": CALIBER_RULING_96_1_3,
            "rr_b2_18_fixed": ("旧纳入条件 `tag==\"other\" and \"RL_Robot\" in args` 已删；归线改按 "
                               "argv 执行位（`line_tag_of_script`）。差分对照（两向）见 "
                               "`cotenant_detector_teeth.json`，与 E/F 参考实现的等价对账见 "
                               "`CMDLINE_CALIBER_ALIGNMENT.json`"),
            "loadavg_1m_before": lb, "loadavg_1m_after": la,
            "loadavg_1m_swing": swing, "loadavg_swing_threshold": LOADAVG_SWING_THRESHOLD,
            "nr_throttled_delta": throttled_delta,
            "gpu_util_verbatim": {"before": (before.get("nvidia_smi") or {}).get("gpu"),
                                  "after": (after.get("nvidia_smi") or {}).get("gpu"),
                                  "preflight": (preflight or {}).get("nvidia_smi_gpu_verbatim")},
            "idle_procs_seen_but_ignored": ignored_idle,
            "idle_procs_ignored_criterion": ("执行位归线不属于 a2/c2/e/b2、或闲置（累计 CPU ≤%d tick "
                                             "且状态 ∈ %s）、或 pcpu ≤ %s%%"
                                             % (IDLE_CPU_TICKS, list(IDLE_PROC_STATES),
                                                GPU_LINE_ACTIVE_PCPU))},
        "detector": "three_net_strict（裁定 85.6-2；口径复用 E 的 card_busy/nvidia_fd_holders/cmdline 网）",
        "ruling": ("裁定 73 + **裁定 85.6-2** + **裁定 96.1-③**：三网任一命中外来 / 归线活跃作业"
                   "（执行位归线 + 非闲置 + pcpu>1%）/ loadavg_1m 摆幅 ≥5 ⇒ 自动标 contaminated；"
                   "窗口外测的一律可作趋势参考、不得作权威口径"),
        "priority_rank": ("**A2（已申报的标定窗）> B2（S1 采集）> C2 > E**（裁定 85.7，关键路径感知；"
                          "取代裁定 73 的 A2>C2>E>B2 —— B2 从末位升到第 2 位，因为 S1 是全仓唯一真阻塞）")}


# ---- 裁定 96.1-③ / RR-B2-18 的**对齐语料**：R1–R12 是「真实记录过的 argv 形态」（出处逐行标明，
# 取自 F 的实测件与 E 的修复验证件），R13/R14 是 RR-B2-18 与牙③ 的**字面形态**。
# 每行的 `expected_*` 都是**先声明后跑**的期望值（不是跑完回填的），跑不一致 ⇒ 探针红。
# `cpu_ticks`/`proc_state` 是纯函数重放的**输入**（不起进程、不读 /proc）：R1–R12 沿用 E 的
# 验证件里同名的重放输入，R13/R14 由 B2 声明；`pcpu` 全部由 B2 声明（只喂给修法前的差分对照，
# 因为旧信号② 有 `pcpu>1%` 这一条），**不是实测值**，故逐行标 `input_kind`（裁定 89.7）。
CMDLINE_CALIBER_CORPUS: Tuple[dict, ...] = (
    {"id": "R1_f_measured_text_mention_pid214244",
     "source": ("runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json → "
                "result.broad_band_hits[0].cmdline（F 实测 `text_mention_only`；E 的验证件 R1 同形）"),
     "why": ("在**改文件**（纯 CPU），只是 argv 里带了 `scripts/a2_…` 字面量；`python3` 后面跟的是 "
             "`-`（heredoc），不构成执行形态 ⇒ 修后不计入。旧判据还会把它**归线成 a2**（全文里有 "
             "`/a2_`）⇒ 连「是谁在跑」都报错"),
     "argv": ["/bin/bash", "-c",
              "cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot && python3 - <<'PY' "
              "import pathlib r=pathlib.Path(\"scripts/a2_s4b_outcome_ledger_verify.py\"); "
              "u=r.read_text() old = ''' ok = a"],
     "cpu_ticks": 40, "proc_state": "R", "pcpu": 12.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "text_mention_only",
                               "counted_narrow": False, "counted_broad": False},
     "expected_with_b2_lists": {"classification": "text_mention_only",
                                "counted_narrow": False, "counted_broad": False},
     "expected_signal2": False,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": False},
    {"id": "R2_f_measured_real_pid214254",
     "source": "同上件 → result.broad_band_hits[1].cmdline（F 实测 `real_gpu_work`；E 的验证件 R2 同形）",
     "why": ("`timeout … python scripts/a2_….py` = 真实执行形态 ⇒ 宽档**照旧**计入（反漏检）；"
             "它不带窄档关键字（这一轮是 CPU 臂）⇒ 窄档不计入"),
     "argv": ["timeout", "1800", "/root/venvs/pi05_sim/bin/python",
              "scripts/a2_s4b_outcome_ledger_verify.py", "--out-dir",
              "runs/vla/a2_s4b_outcome_ledger_20260930_dbg7", "--real-frames", "30"],
     "cpu_ticks": 900, "proc_state": "R", "pcpu": 85.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "real_gpu_work",
                               "counted_narrow": False, "counted_broad": True},
     "expected_with_b2_lists": {"classification": "real_gpu_work",
                                "counted_narrow": False, "counted_broad": True},
     "expected_signal2": True,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": True},
    {"id": "R3_f_measured_real_pid214257",
     "source": "同上件 → result.broad_band_hits[2].cmdline（F 实测 `real_gpu_work`；E 的验证件 R3 同形）",
     "why": "同 R2，无 `timeout` 前缀也必须命中（`EXEC_FORM_RE` 的 `^` 分支）",
     "argv": ["/root/venvs/pi05_sim/bin/python", "scripts/a2_s4b_outcome_ledger_verify.py",
              "--out-dir", "runs/vla/a2_s4b_outcome_ledger_20260930_dbg7", "--real-frames", "30"],
     "cpu_ticks": 700, "proc_state": "R", "pcpu": 80.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "real_gpu_work",
                               "counted_narrow": False, "counted_broad": True},
     "expected_with_b2_lists": {"classification": "real_gpu_work",
                                "counted_narrow": False, "counted_broad": True},
     "expected_signal2": True,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": True},
    {"id": "R4_a2_latency_arm_must_still_be_detected",
     "source": "裁定 85.0 记录的真实形态（E 的验证件 R4 同形）",
     "why": "**反漏检主腿**：A2 真要上卡的延迟臂，收紧之后必须照旧命中（窄档 3 个关键字 + 宽档）",
     "argv": ["/root/venvs/pi05_sim/bin/python", "scripts/a2_egl_latency_remeasure.py",
              "--mode", "closed_loop", "--tag", "quiet_window_rep1"],
     "cpu_ticks": 5000, "proc_state": "R", "pcpu": 95.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "real_gpu_work",
                               "counted_narrow": True, "counted_broad": True},
     "expected_with_b2_lists": {"classification": "real_gpu_work",
                                "counted_narrow": True, "counted_broad": True},
     "expected_signal2": True,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": True},
    {"id": "R5_2358_cotenant_proxy_form",
     "source": "23:58 抢卡事故的 E 侧假体（E 的验证件 R5 同形）",
     "why": ("E 侧两档关键字都不命中（`scripts/e_` 对 E 不属「他线」）⇒ E 记 `no_keyword`；"
             "**B2 侧不同**：B2 的窄档含 `e_mainline_render_calib`、宽档含 `scripts/e_` ⇒ "
             "`real_gpu_work`。这一行是「口径线相对」的证人，不是分歧"),
     "argv": ["/root/venvs/pi05_sim/bin/python", "scripts/e_mainline_render_calib.py",
              "--workers", "1,2,4,8"],
     "cpu_ticks": 3000, "proc_state": "R", "pcpu": 90.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "no_keyword",
                               "counted_narrow": False, "counted_broad": False},
     "expected_with_b2_lists": {"classification": "real_gpu_work",
                                "counted_narrow": True, "counted_broad": True},
     "expected_signal2": True,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": True},
    {"id": "R6_bare_torchrun_launcher",
     "source": "反漏检构造（六步序列第 2 步的 BC/SFT 可能用分布式启动器；E 的验证件 R6 同形）",
     "why": ("argv0 **本身就是** GPU 启动器 ⇒ 即使没有 `scripts/<line>_*.py` 也算真实执行形态"
             "（`GPU_LAUNCHER_ARGV0` 反漏检腿）；但它归不了线 ⇒ 信号② 不计入"),
     "argv": ["torchrun", "--nproc_per_node=1", "harness/train_bc.py"],
     "cpu_ticks": 800, "proc_state": "R", "pcpu": 50.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "real_gpu_work",
                               "counted_narrow": True, "counted_broad": False},
     "expected_with_b2_lists": {"classification": "real_gpu_work",
                                "counted_narrow": True, "counted_broad": False},
     "expected_signal2": False,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": True},
    {"id": "R7_coldstart_recovery_entry",
     "source": "T-E-11 第 3 项的恢复入口（`docs/infra-gpu-render.md` §0.4；E 的验证件 R7 同形）",
     "why": ("`/bin/bash` + 绝对路径里的 `scripts/e_…` 构成执行形态；E 侧两档都不命中 ⇒ `no_keyword`，"
             "B2 侧宽档命中 ⇒ `real_gpu_work`（同 R5，口径线相对）"),
     "argv": ["env", "-i", "/bin/bash",
              "/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot/scripts/"
              "e_coldstart_gpu_render.sh"],
     "cpu_ticks": 120, "proc_state": "R", "pcpu": 40.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "no_keyword",
                               "counted_narrow": False, "counted_broad": False},
     "expected_with_b2_lists": {"classification": "real_gpu_work",
                                "counted_narrow": False, "counted_broad": True},
     "expected_signal2": True,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": True},
    {"id": "R8_python_m_torch_distributed_run",
     "source": "**已登记的漏检缺口**（E 的验证件 R8 同形，E 报 D 未自决扩范围）",
     "why": ("`-m torch.distributed.run` 不含任何窄档关键字、也没有 `scripts/<line>_*.py` ⇒ 网③ "
             "**修法前后都不命中**；真上卡后由网②（fd）/网①（compute-apps）抓住。这一行存在的意义"
             "是**不许把缺口写成已修**（三值纪律：`registered_gap`）"),
     "argv": ["/root/venvs/pi05_sim/bin/python", "-m", "torch.distributed.run",
              "--nproc_per_node=1", "harness/train_bc.py"],
     "cpu_ticks": 800, "proc_state": "R", "pcpu": 50.0, "input_kind": "e_recorded_replay_input",
     "registered_gap": True,
     "expected_with_e_lists": {"classification": "no_keyword",
                               "counted_narrow": False, "counted_broad": False},
     "expected_with_b2_lists": {"classification": "no_keyword",
                                "counted_narrow": False, "counted_broad": False},
     "expected_signal2": False,
     "expected_legacy_would_detect": False, "expected_new_would_contaminate": False},
    {"id": "R9_f_injected_bad_form",
     "source": "F 的 93.8 对照探针注入串（同 F 件 `pattern_coverage_probe.injected_bad_form`）",
     "why": "`grep` 一个关键字 ≠ 要上卡 ⇒ **负向腿**：旧判据计入、新判据不计入",
     "argv": ["/bin/bash", "-c",
              "cd /repo && grep -n a2_egl_latency_remeasure harness/some_module.py"],
     "cpu_ticks": 30, "proc_state": "R", "pcpu": 8.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "text_mention_only",
                               "counted_narrow": False, "counted_broad": False},
     "expected_with_b2_lists": {"classification": "text_mention_only",
                                "counted_narrow": False, "counted_broad": False},
     "expected_signal2": False,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": False},
    {"id": "R10_shell_really_launching_a_gpu_run",
     "source": "残留风险构造（过判方向，安全侧；E 的验证件 R10 同形）",
     "why": ("`bash -c` 里**真要启动**一条 GPU 跑 ⇒ 计入是对的（`python` 在文本里但构成执行形态）；"
             "代价是同形的 `echo`/`cat` 纯文本也会被计入 —— 这条残留风险 E 已登记，B2 沿用不另裁"),
     "argv": ["/bin/bash", "-c",
              "cd /repo && python scripts/a2_egl_latency_remeasure.py --mode closed_loop"],
     "cpu_ticks": 60, "proc_state": "R", "pcpu": 30.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "real_gpu_work",
                               "counted_narrow": True, "counted_broad": True},
     "expected_with_b2_lists": {"classification": "real_gpu_work",
                                "counted_narrow": True, "counted_broad": True},
     "expected_signal2": True,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": True},
    {"id": "R11_idle_carrier_with_exec_form",
     "source": "闲置腿构造（E 的验证件 R11 同形；`pcpu≈0` 排除）",
     "why": "执行形态与关键字都在，但自启动以来几乎没执行过指令 ⇒ **负向腿**（闲置排除）",
     "argv": ["/bin/sleep", "scripts/a2_probe_idle.py", "--mode", "closed_loop", "30"],
     "cpu_ticks": 0, "proc_state": "S", "pcpu": 0.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "idle_text_mention",
                               "counted_narrow": False, "counted_broad": False},
     "expected_with_b2_lists": {"classification": "idle_text_mention",
                                "counted_narrow": False, "counted_broad": False},
     "expected_signal2": False,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": False},
    {"id": "R12_just_forked_real_run_must_not_be_idle_excluded",
     "source": "闲置腿的**反漏检**对照（刚 fork 出来的真跑；E 的验证件 R12 同形）",
     "why": ("6 tick（60 ms）> `IDLE_CPU_TICKS`=1 ⇒ 不被闲置排除（python 解释器启动自身就超过阈值；"
             "E 的活体腿 L1 实测裕度 26×）"),
     "argv": ["/root/venvs/pi05_sim/bin/python", "scripts/a2_egl_latency_remeasure.py",
              "--mode", "closed_loop"],
     "cpu_ticks": 6, "proc_state": "S", "pcpu": 20.0, "input_kind": "e_recorded_replay_input",
     "expected_with_e_lists": {"classification": "real_gpu_work",
                               "counted_narrow": True, "counted_broad": True},
     "expected_with_b2_lists": {"classification": "real_gpu_work",
                                "counted_narrow": True, "counted_broad": True},
     "expected_signal2": True,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": True},
    {"id": "R13_rr_b2_18_literal_form",
     "source": ("**RR-B2-18 的字面形态**（B2 自报的缺陷原文：`tag==\"other\" and \"RL_Robot\" in "
                "args` ⇒ `contaminated_by_cotenant` 永久为真）"),
     "why": ("agent 在仓库里 `grep` 自己的采集器（纯 CPU、`pcpu>1%`）：旧判据按**全文**归线成 `b2` "
             "⇒ 信号② 计入 ⇒ 每份产物永久标脏；新判据按执行位归线 ⇒ 不计入。**这一行就是本条 "
             "RR 的负向腿**"),
     "argv": ["/bin/bash", "-c",
              "cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot && grep -rn "
              "contaminated_by_cotenant scripts/b2_s1_generate_dataset.py"],
     "cpu_ticks": 45, "proc_state": "R", "pcpu": 3.0, "input_kind": "b2_declared",
     "expected_with_e_lists": {"classification": "text_mention_only",
                               "counted_narrow": False, "counted_broad": False},
     "expected_with_b2_lists": {"classification": "no_keyword",
                                "counted_narrow": False, "counted_broad": False},
     "expected_signal2": False,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": False},
    {"id": "R14_tooth3_real_second_b2_job",
     "source": "裁定 85.6-2 牙③ 的字面形态（第二个 B2 采集作业，**完全不碰 GPU**）",
     "why": ("B2 的线相对宽档排除 `b2_`、窄档一个关键字都不命中 ⇒ 网③ 记 `no_keyword`；"
             "**但信号② 必须计入**（牙③ 要求「第二个 b2 采集作业不许隐形」）⇒ 这一行证明了"
             "为什么信号② 不能加「∧ GPU 关键字」那个合取（E 侧宽档含 `b2?` ⇒ 记 `real_gpu_work`）"),
     "argv": ["/root/venvs/pi05_sim/bin/python", "scripts/b2_s1_generate_dataset.py",
              "--stage", "formal"],
     "cpu_ticks": 800, "proc_state": "R", "pcpu": 95.0, "input_kind": "b2_declared",
     "expected_with_e_lists": {"classification": "real_gpu_work",
                               "counted_narrow": False, "counted_broad": True},
     "expected_with_b2_lists": {"classification": "no_keyword",
                                "counted_narrow": False, "counted_broad": False},
     "expected_signal2": True,
     "expected_legacy_would_detect": True, "expected_new_would_contaminate": True},
)


def _is_re_compile_call(node: ast.Call) -> bool:
    """`re.compile(…)` 的 ast 形状判定（`func` 是 `Attribute(value=Name('re'), attr='compile')`）。"""
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr == "compile":
        return isinstance(f.value, ast.Name) and f.value.id == "re"
    return isinstance(f, ast.Name) and f.id == "compile"


def _extract_caliber_reference(rel_path: str) -> dict:
    """从参考实现里 **ast 现取**判据常量与 `classify_cmdline` 源码（不 import、不抄字面量）。

    为什么不 `import`：本件是**采集器**，多一个跨线运行时依赖 = 多一条「E 的文件坏了 ⇒ B2 采不了
    数据」的耦合；ast 现取只读文本。取不到 ⇒ 调用方登记 `not_measured` + 非零退出（裁定 89.7），
    **不静默降级成"没有漂移"**（那正是 `absence_of_measurement_is_not_measurement_of_absence`）。
    """
    p = ROOT / rel_path
    raw = p.read_bytes()
    src = raw.decode("utf-8", errors="ignore")
    tree = ast.parse(src)
    wanted = set(SHARED_CALIBER_CONSTANTS) | {"GPU_INTENT_PATTERNS", "OTHER_LINE_SCRIPT_RE"}
    consts: Dict[str, Any] = {}
    func_src = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                nm = getattr(t, "id", "")
                if nm not in wanted:
                    continue
                v = node.value
                if isinstance(v, ast.Call) and _is_re_compile_call(v):
                    lit = [a for a in v.args if isinstance(a, ast.Constant)]
                    consts[nm] = re.compile(str(lit[0].value)) if lit else None
                else:
                    try:
                        consts[nm] = ast.literal_eval(v)
                    except ValueError:
                        consts[nm] = None
        elif isinstance(node, ast.FunctionDef) and node.name == "classify_cmdline":
            func_src = ast.get_source_segment(src, node) or ""
    ident = {"path": rel_path, "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
             "n_lines": raw.count(b"\n"), "n_bytes": len(raw),
             "citation_algo": "sha256[:12]", "as_of": now_iso()}
    missing = sorted([n for n in wanted if consts.get(n) is None])
    return {"constants": consts, "func_source": func_src, "identity": ident, "missing": missing,
            "func_source_sha256_12": (hashlib.sha256(func_src.encode()).hexdigest()[:12]
                                      if func_src else None),
            "func_source_n_lines": (func_src.count("\n") + 1) if func_src else 0}


def _own_caliber_constants() -> Dict[str, Any]:
    """本件（B2 副本）的同名常量，归一化成可与参考实现直接 `==` 的形态。"""
    out = {}
    for nm in SHARED_CALIBER_CONSTANTS:
        v = globals()[nm]
        out[nm] = v.pattern if isinstance(v, re.Pattern) else v
    return out


def cmdline_caliber_alignment_probe(out_path: Optional[Path] = None) -> dict:
    """与 E 的参考实现 / F 的口径出处**现取对账**（裁定 46.4 副本漂移防护 + 裁定 93.8 两向）。

    B2 自带 `classify_cmdline` 的**副本**（不 import E 的模块，理由见 `_extract_caliber_reference`）
    ⇒ 副本会漂移，而漂移是**静默**的（裁定 46.4 的根因形态；E 在 §E13.1.6 明确点了这一条）。
    所以本探针每次跑都：
      **腿 A** 常量逐字相同：`EXEC_FORM_RE` 在 **B2 / E / F 三件**里必须逐字一致（F 是出处）；
              `GPU_LAUNCHER_ARGV0` / `GPU_LAUNCHER_MODULES` / `IDLE_CPU_TICKS` / `IDLE_PROC_STATES`
              与 E 的参考实现逐字一致。
      **腿 B** 逻辑等价 + 声明期望：14 行语料分别喂给 ① B2 的 `classify_cmdline`（注入 **E 的词表**
              ⇒ 比的是逻辑不是口径）② E 的 `classify_cmdline`（ast 取源码后在隔离命名空间 exec）
              ③ B2 的 `classify_cmdline`（用 **B2 自己的**线相对词表）④ `line_job_evidence`（信号②）
              ⑤ `_legacy_rr_b2_18_verdict`（修法前）⇒ ①==② 、且 ①③④⑤ 各自 == **先声明的**期望值。
      **腿 C** 两向都在：语料里必须**同时**有「旧判据计入 → 新判据不计入」的翻转行（负向腿，证明
              修法真会咬）与「新旧都计入」的保留行（正向腿，证明没漏检）；**缺一向 ⇒ 不报绿**
              （缺陷类 ⑲）。翻转行还必须落在 `text_mention_only` / `idle_text_mention` / `no_keyword`
              上（否则"翻转"可能来自别的原因，那就不算证明了本条修法）。
    参考件取不到 / 解析不了 ⇒ `measurement_status="not_measured"`、`ok=False`、退出码 3。
    **本探针纯 CPU**：不起进程、不读 `/proc`、不碰 GPU、不扫根文件系统。
    """
    gen_raw = SCRIPT.read_bytes()
    doc: Dict[str, Any] = {
        "artifact": "b2_cmdline_caliber_alignment", "line": "B2", "generated_at": now_iso(),
        "generator": "scripts/b2_s1_generate_dataset.py",
        "generator_identity": {"path": "scripts/b2_s1_generate_dataset.py",
                               "sha256_12": hashlib.sha256(gen_raw).hexdigest()[:12],
                               "n_lines": gen_raw.count(b"\n"), "n_bytes": len(gen_raw),
                               "citation_algo": "sha256[:12]", "as_of": now_iso()},
        "ruling": ("裁定 96.1-③（RR-B2-18 与 `card_busy()` 同族同批修）+ 裁定 46.4（副本漂移必须"
                   "被机器看见）+ 裁定 93.8（对照探针必须两向）"),
        "question": ("B2 自带的判定副本是否仍与 E 的参考实现**等价**、`EXEC_FORM_RE` 是否仍与 F 的"
                     "出处**逐字相同**；以及修法是否真的把「关于 GPU 的文本」排除掉而没漏掉真跑"),
        "scan_scope": "只读本仓库内两个参考件的源码文本（ast）+ 内存里的纯函数重放",
        "no_root_filesystem_scans": True, "policy_executed": False, "gpu_used": False,
        "capability_claim": None, "not_a_capability_claim": True,
    }
    try:
        ref_e = _extract_caliber_reference(CALIBER_REFERENCE_E)
        ref_f = _extract_caliber_reference(CALIBER_REFERENCE_F)
    except (OSError, SyntaxError, ValueError) as e:
        doc.update({"measurement_status": "not_measured",
                    "not_measured_reason": "参考件读不到或解析不了：%s: %s" % (type(e).__name__, e),
                    "ok": False, "exit_code": 3, "legs": {}, "rows": []})
        if out_path is not None:
            note_write(out_path).write_text(
                json.dumps(doc, ensure_ascii=False, indent=1, default=_json_default),
                encoding="utf-8")
        return doc

    e_needs = sorted(set(SHARED_CALIBER_CONSTANTS)
                     | {"GPU_INTENT_PATTERNS", "OTHER_LINE_SCRIPT_RE"})
    e_missing = [n for n in e_needs if n in ref_e["missing"]]
    f_exec_form = ref_f["constants"].get("EXEC_FORM_RE")
    blocked = bool(e_missing or not ref_e["func_source"] or f_exec_form is None)
    doc["references"] = {
        "e_reference": {**ref_e["identity"], "role": "参考实现（`classify_cmdline` 纯函数）",
                        "func_source_sha256_12": ref_e["func_source_sha256_12"],
                        "func_source_n_lines": ref_e["func_source_n_lines"],
                        "n_intent_patterns": len(ref_e["constants"].get("GPU_INTENT_PATTERNS") or ()),
                        "broad_regex": ((ref_e["constants"].get("OTHER_LINE_SCRIPT_RE") or
                                         re.compile("")).pattern or None),
                        "missing": e_missing},
        "f_reference": {**ref_f["identity"], "role": "`EXEC_FORM_RE` 的出处（只读探针）",
                        "exec_form_re_found": f_exec_form is not None},
        "b2_own": {"n_intent_patterns": len(GPU_INTENT_PATTERNS),
                   "broad_regex": OTHER_LINE_SCRIPT_RE.pattern,
                   "line_relative_note": ("B2 的宽档**排除 `b2_`**（本线由信号② 承载，牙③）、"
                                          "E 的宽档排除 `e_` ⇒ 词表不同是**设计**，不是漂移；"
                                          "所以腿 B 用 E 的词表喂 B2 的函数来比逻辑")},
    }
    if blocked:
        doc.update({"measurement_status": "not_measured",
                    "not_measured_reason": ("参考件里取不到判据（E 缺 %s；F 的 `EXEC_FORM_RE` %s）⇒ "
                                            "**不判「没有漂移」**，按三值登记"
                                            % (e_missing or "无",
                                               "已取到" if f_exec_form is not None else "没取到")),
                    "ok": False, "exit_code": 3, "legs": {}, "rows": []})
        if out_path is not None:
            note_write(out_path).write_text(
                json.dumps(doc, ensure_ascii=False, indent=1, default=_json_default),
                encoding="utf-8")
        return doc

    # ---- 腿 A：常量逐字相同（B2 副本 vs E 参考 vs F 出处）----
    mine = _own_caliber_constants()
    a_rows = []
    for nm in SHARED_CALIBER_CONSTANTS:
        ev = ref_e["constants"][nm]
        ev = ev.pattern if isinstance(ev, re.Pattern) else ev
        row = {"constant": nm, "b2_value": repr(mine[nm]), "e_value": repr(ev),
               "identical_to_e": bool(mine[nm] == ev)}
        if nm == "EXEC_FORM_RE":
            row["f_value"] = repr(f_exec_form.pattern)
            row["identical_to_f"] = bool(mine[nm] == f_exec_form.pattern)
            row["three_way_identical"] = bool(row["identical_to_e"] and row["identical_to_f"])
        a_rows.append(row)
    leg_a = {"leg": "A_constants_identical", "rows": a_rows, "n_rows": len(a_rows),
             "n_ok": sum(1 for r in a_rows if r["identical_to_e"]
                         and r.get("identical_to_f", True)),
             "claim": ("副本自带的常量必须与参考实现逐字相同；`EXEC_FORM_RE` 还须与 F 的出处"
                       "逐字相同（三方一致）"),
             "measurement_status": "measured"}
    leg_a["all_ok"] = bool(leg_a["n_ok"] == leg_a["n_rows"])

    # ---- 腿 B：逻辑等价 + 声明期望（E 的函数源码 ast 现取后在隔离命名空间里 exec）----
    ns: Dict[str, Any] = {"re": re}
    ns.update({k: v for k, v in ref_e["constants"].items() if v is not None})
    exec(ref_e["func_source"], ns)          # 只 exec 本仓库内 E 的纯函数源码（不 import 整个模块）
    e_classify = ns["classify_cmdline"]
    cmp_keys = SHARED_CLASSIFY_KEYS + ("gpu_intent_matched", "other_line_script_matched")
    rows = []
    for row in CMDLINE_CALIBER_CORPUS:
        argv, ticks, state = row["argv"], row["cpu_ticks"], row["proc_state"]
        b2_e = classify_cmdline(argv, cpu_ticks=ticks, proc_state=state,
                                intent_patterns=ref_e["constants"]["GPU_INTENT_PATTERNS"],
                                other_line_re=ref_e["constants"]["OTHER_LINE_SCRIPT_RE"])
        e_got = e_classify(argv, cpu_ticks=ticks, proc_state=state)
        b2_own = classify_cmdline(argv, cpu_ticks=ticks, proc_state=state)
        lj = line_job_evidence(argv, cpu_ticks=ticks, proc_state=state)
        legacy = _legacy_rr_b2_18_verdict(argv, row.get("pcpu"))
        new_would = bool(b2_own["counted_narrow"] or b2_own["counted_broad"]
                         or lj["counted_toward_signal2"])
        per_key = {k: {"b2_with_e_lists": b2_e.get(k), "e_impl": e_got.get(k),
                       "equal": bool(b2_e.get(k) == e_got.get(k))} for k in cmp_keys}
        checks = {
            "b2_with_e_lists_equals_e_impl": all(v["equal"] for v in per_key.values()),
            "b2_with_e_lists_equals_declared": all(b2_e.get(k) == v for k, v
                                                   in row["expected_with_e_lists"].items()),
            "b2_with_b2_lists_equals_declared": all(b2_own.get(k) == v for k, v
                                                    in row["expected_with_b2_lists"].items()),
            "signal2_equals_declared": (bool(lj["counted_toward_signal2"])
                                        == bool(row["expected_signal2"])),
            "legacy_equals_declared": (bool(legacy["would_detect"])
                                       == bool(row["expected_legacy_would_detect"])),
            "new_equals_declared": new_would == bool(row["expected_new_would_contaminate"]),
        }
        rows.append({"id": row["id"], "source": row["source"], "why": row["why"],
                     "input_kind": row["input_kind"], "registered_gap": bool(row.get("registered_gap")),
                     "argv": argv, "cpu_ticks": ticks, "proc_state": state, "pcpu": row.get("pcpu"),
                     "declared": {k: row[k] for k in
                                  ("expected_with_e_lists", "expected_with_b2_lists",
                                   "expected_signal2", "expected_legacy_would_detect",
                                   "expected_new_would_contaminate")},
                     "got": {"b2_with_e_lists": {k: b2_e.get(k) for k in cmp_keys},
                             "e_impl": {k: e_got.get(k) for k in cmp_keys},
                             "b2_with_b2_lists": {k: b2_own.get(k) for k in cmp_keys},
                             "exec_form_kind": b2_own["exec_form_kind"],
                             "exec_script": b2_own["exec_script"],
                             "signal2": {"line_tag": lj["line_tag"],
                                         "counted_toward_signal2": lj["counted_toward_signal2"],
                                         "not_counted_reason": lj["not_counted_reason"]},
                             "legacy_rr_b2_18": legacy,
                             "new_would_contaminate": new_would},
                     "per_key_agreement": per_key, "checks": checks,
                     "ok": all(checks.values())})
    leg_b = {"leg": "B_logic_equivalence_and_declared_expectations", "n_rows": len(rows),
             "n_ok": sum(1 for r in rows if r["ok"]),
             "caliber": ("纯函数重放：不起进程、不读 `/proc`；R1–R3/R9 的 argv 出自 F 的实测件，"
                         "R4–R8/R10–R12 出自 E 的修复验证件，R13/R14 是 RR-B2-18 与牙③ 的字面形态"),
             "claim": ("① B2 副本（喂 E 的词表）与 E 的实现**逐键相同**；② B2 用自己的线相对词表时"
                       "等于**先声明的**期望值；③ 信号② 与修法前的差分对照都等于声明值"),
             "measurement_status": "measured"}
    leg_b["all_ok"] = bool(leg_b["n_ok"] == leg_b["n_rows"])

    # ---- 腿 C：两向都在（裁定 93.8 / 缺陷类 ⑲）----
    flips = [r for r in rows if r["declared"]["expected_legacy_would_detect"]
             and not r["declared"]["expected_new_would_contaminate"]]
    keeps = [r for r in rows if r["declared"]["expected_legacy_would_detect"]
             and r["declared"]["expected_new_would_contaminate"]]
    gaps = [r for r in rows if not r["declared"]["expected_legacy_would_detect"]
            and not r["declared"]["expected_new_would_contaminate"]]
    flip_forms_ok = all(r["got"]["b2_with_b2_lists"]["classification"] != "real_gpu_work"
                        and not r["got"]["signal2"]["counted_toward_signal2"] for r in flips)
    leg_c = {"leg": "C_both_directions",
             "n_flip_rows": len(flips), "flip_ids": [r["id"] for r in flips],
             "n_keep_rows": len(keeps), "keep_ids": [r["id"] for r in keeps],
             "n_registered_gap_rows": len(gaps), "gap_ids": [r["id"] for r in gaps],
             "flip_rows_all_text_or_idle_form": flip_forms_ok,
             "both_directions": bool(flips and keeps and flip_forms_ok),
             "assertion": ("**只装一向不许报绿**：必须同时有「旧判据计入 → 新判据不计入」（负向腿）"
                           "与「新旧都计入」（正向腿/反漏检），且负向腿的形态必须落在"
                           "文本提及/闲置/无关键字上"),
             "vacuity_guard": ("`_legacy_rr_b2_18_verdict` 是修法前判据的逐字复刻，只被本探针与"
                               "牙的差分腿调用；若它在负向腿上行不再判 `would_detect=True`，"
                               "说明对照物本身失效 ⇒ `flip_ids` 会空 ⇒ 本腿红"),
             "measurement_status": "measured"}
    leg_c["all_ok"] = bool(leg_c["both_directions"])

    legs = {"A_constants_identical": leg_a,
            "B_logic_equivalence_and_declared_expectations": leg_b,
            "C_both_directions": leg_c}
    ok = bool(leg_a["all_ok"] and leg_b["all_ok"] and leg_c["all_ok"])
    doc.update({"legs": legs, "rows": rows, "n_rows": len(rows),
                "legs_all_ok": {k: v["all_ok"] for k, v in legs.items()},
                "measurement_status": "measured", "ok": ok, "exit_code": (0 if ok else 3),
                "verdict": ("aligned_with_reference_and_both_directions_proven" if ok
                            else "NOT_aligned_or_one_direction_only")})
    if out_path is not None:
        note_write(out_path).write_text(
            json.dumps(doc, ensure_ascii=False, indent=1, default=_json_default),
            encoding="utf-8")
    return doc


def cotenant_detector_teeth(out_root: Path, hold_s: int = 14, wait_s: float = 5.0) -> int:
    """裁定 85.6-2 的三条牙 + **裁定 96.1-③ / RR-B2-18 的两条新牙**：探测器真的会咬、也真的不会误咬。

    牙①：起一个**持 `/dev/nvidiactl` 的进程**（不分配 compute 显存 ⇒ 网①`compute-apps` 看不见它）
          ⇒ 探测器必须 `true`（由网② fd 命中）。这正是旧探测器（只查 compute-apps）的盲区。
          **本次修法一个字节都没碰网①/网②**（它们是「占用」的直接证据，不是文本）⇒ 这条牙照旧。
    牙②：只留一个 **`pcpu≈0` 的空闲 bash**（cmdline 里含仓库路径 ⇒ 第一版"任何含仓库名的进程"
          判据会永久标 contaminated = 狼来了）⇒ 探测器必须 `false`。
    牙③：起一个**执行位**上是 `scripts/b2_*.py` 且 **pcpu>1%**、但**不碰 GPU** 的进程
          ⇒ 探测器必须 `true`（由信号② 归线活跃作业命中；这是"第二个 B2 采集作业"的证人）。
          **本次改了证人的 argv 形态**：旧证人把脚本名当作 `-c` 之后的**附加参数**塞进去
          （`python -c <busy loop> scripts/b2_s1_generate_dataset.py`），那不是执行形态 —— 收紧之后
          它会被（正确地）判成文本提及。所以证人改成一个**真的以线内脚本路径启动**的 fixture
          （`tmp/b2_rr18_teeth/scripts/b2_tooth3_witness_busy.py`），牙③ 的原意（第二个采集作业
          不许隐形）保持不变，而旧形态本身降格为牙④ 的负向证人。
    牙④（**新 · 负向腿**，裁定 93.8）：起一个 **`pcpu>1%` 的纯 CPU 进程**，它的 cmdline 里
          **只在文本位**提到 `torchrun`/`a2_egl_latency_remeasure`/`--mode closed_loop`/
          `scripts/e_mainline_render_calib.py`/`RL_Robot` ⇒ 探测器必须 `false`，
          且**同一活体进程**在修法前的判据下必须 `true`（`legacy_caliber_would_detect`）。
          这一条就是 RR-B2-18 的字面形态：少了这个差分，"修好了"这句话没有对照物。
    牙⑤（**新 · 正向腿/反漏检**）：起一个**执行位上真是他线脚本**（`scripts/a_*`）且不碰 GPU 的
          进程 ⇒ 探测器必须 `true`（由网③ 宽档命中）⇒ 证明收紧没把"别线真在跑"漏掉。
          证人 fixture 走 `a_` 前缀（不是 `a2_`）⇒ 信号② 不归线，命中的**只能是网③**，
          两条信号不会互相打掩护。

    **判定按 witness PID 是否被命中**，不看全局 `busy`：否则机器上恰好有别人在跑时，
    牙②会假失败、牙①③会假成功 —— 那就不是探测器自证，是运气。

    同一次调用还会跑 `cmdline_caliber_alignment_probe()`（与 E/F 的参考实现现取对账）并把产物
    写在同一个 run 目录里；**两向都在**（`both_directions_proven`）与**对齐探针 ok** 都计入退出码。
    """
    out_root.mkdir(parents=True, exist_ok=True)
    baseline = {"three_net": card_busy_three_net(strict=True),
                "line_procs": foreign_gpu_line_processes(),
                "loadavg3": loadavg3(), "ts": now_iso()}
    teeth = []

    def _sample(pid: int) -> dict:
        three = card_busy_three_net(strict=True)
        procs = foreign_gpu_line_processes()
        nets = {"net1_compute_apps": any(h["pid"] == pid for h in three["net1_compute_apps"]),
                "net2_nvidia_fd": any(h["pid"] == pid for h in three["net2_nvidia_fd_holders"]),
                "net3_cmdline": any(h["pid"] == pid for h in three["net3_cmdline_hits"])}
        row = next((p for p in procs if p.get("pid") == pid), None)
        active = bool(row and row.get("counted_toward_signal2")
                      and row.get("line_tag") in LINE_TAGS_FOR_SIGNAL2
                      and float(row.get("pcpu") or 0) > GPU_LINE_ACTIVE_PCPU)
        argv = _argv(pid)
        ticks, state = _proc_cpu(pid)
        legacy = _legacy_rr_b2_18_verdict(argv, (row or {}).get("pcpu"))
        not_counted = [dict(b, bucket=nm) for nm in ("net3_text_mention_only",
                                                     "net3_idle_text_mention")
                       for b in (three.get(nm) or []) if b.get("pid") == pid]
        return {"witness_pid": pid, "nets": nets, "line_proc_row": row,
                "signal2_active_line": active,
                "three_net_busy_global": three["busy"],
                "detected": bool(nets["net1_compute_apps"] or nets["net2_nvidia_fd"]
                                 or nets["net3_cmdline"] or active),
                "detected_by": sorted([k for k, v in nets.items() if v]
                                      + (["signal2_active_line"] if active else [])),
                # ---- 差分腿（裁定 93.8 两向）：**同一个活体进程**，修法前的判据会怎么说 ----
                "live_argv": argv, "cpu_ticks": ticks, "proc_state": state,
                "legacy_caliber_would_detect": legacy["would_detect"],
                "legacy_caliber_detail": legacy,
                "net3_seen_but_not_counted": not_counted,
                "caliber": CALIBER_RULING_96_1_3,
                "loadavg3": loadavg3()}

    def _run_witness(name: str, argv: List[str], expect_detected: bool, why: str,
                     expect_nets: Sequence[str] = (),
                     expect_legacy_detected: Optional[bool] = None) -> dict:
        rec = {"tooth": name, "argv": argv, "expect_detected": expect_detected,
               "expect_hit_by": list(expect_nets),
               "expect_legacy_detected": expect_legacy_detected, "why_this_tooth": why}
        proc = None
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, start_new_session=True)
            time.sleep(wait_s)
            if proc.poll() is not None:
                out = (proc.stdout.read() if proc.stdout else "") or ""
                rec.update({"status": "N_A", "witness_exited_early": proc.returncode,
                            "witness_stdout": out[:400],
                            "n_a_reason": ("证人进程没能活着被采样（例如 `/dev/nvidiactl` 打不开）⇒ "
                                           "**不判 true 也不判 false**，只登记事实（三值纪律）")})
                return rec
            smp = _sample(proc.pid)
            legacy_ok = (None if expect_legacy_detected is None else
                         bool(smp["legacy_caliber_would_detect"] == expect_legacy_detected))
            new_ok = bool(smp["detected"] == expect_detected)
            rec.update({"status": "PASS" if (new_ok and legacy_ok is not False) else "RED",
                        "observed_detected": smp["detected"], "sample": smp,
                        "observed_legacy_detected": smp["legacy_caliber_would_detect"],
                        "new_criterion_ok": new_ok, "legacy_differential_ok": legacy_ok,
                        "expected_nets_hit": (sorted(smp["detected_by"]) == sorted(expect_nets)
                                              if expect_nets else None)})
            if legacy_ok is False:
                rec["legacy_mismatch_note"] = (
                    "差分腿不符：修法前的判据在这条活体进程上实测 %s、声明期望 %s ⇒ 对照物失效"
                    "（那「修好了」就没有证据），本牙判红（裁定 93.8：只装一向不许报绿）"
                    % (smp["legacy_caliber_would_detect"], expect_legacy_detected))
            if expect_nets and sorted(smp["detected_by"]) != sorted(expect_nets):
                rec["net_mismatch_note"] = ("命中网与预期不同：预期 %s、实测 %s（`detected` 仍按预期 ⇒ "
                                            "牙成立，但网归属要如实登记）"
                                            % (sorted(expect_nets), sorted(smp["detected_by"])))
        except Exception as e:                                       # noqa: BLE001
            rec.update({"status": "N_A", "error": "%s: %s" % (type(e).__name__, e)})
        finally:
            if proc is not None and proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), 15)
                except OSError:
                    proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            time.sleep(0.6)
        return rec

    py = sys.executable
    # ---- 牙③/牙⑤ 的证人 fixture：**真的以线内脚本路径启动**（裁定 96.1-③ 之后，"把脚本名当作
    #      `-c` 的附加参数塞进去" 已经不是执行形态了；那种形态降格为牙④ 的负向证人）。
    #      fixture 目录**故意不含 `/b2_` 路径段**：旧判据按 args 全文里的 `/b2_` 归线，若目录名自带
    #      `/b2_`，牙⑤ 的差分对照就会被**文本**归线成 b2 —— 那正是本次要修的缺陷，不许混进对照物。
    fixture_root = ROOT / "tmp" / "rr18_cotenant_teeth" / "scripts"
    fixture_root.mkdir(parents=True, exist_ok=True)
    witness_src = (
        "# B2 共租探测器的证人（牙③/牙⑤）：**纯 CPU 忙等**。不导入 torch/mujoco/OpenGL、\n"
        "# 不开 /dev/nvidia*、不创建任何 GL/CUDA 上下文（裁定 96.1-③ 的修法验证不许上卡）。\n"
        "import os, sys, time\n"
        "hold = float(sys.argv[sys.argv.index('--hold') + 1]) if '--hold' in sys.argv else 14.0\n"
        "print('WITNESS_ALIVE pid=%d argv=%s' % (os.getpid(), sys.argv[1:]), flush=True)\n"
        "t0 = time.time()\n"
        "while time.time() - t0 < hold:\n"
        "    pass\n"
        "print('WITNESS_DONE', flush=True)\n")
    fixtures = {}
    for nm in ("b2_tooth3_witness_busy.py", "a_b2tooth5_witness_real_form.py"):
        fp = note_write(fixture_root / nm)
        fp.write_text(witness_src, encoding="utf-8")
        fixtures[nm] = {"path": str(fp.relative_to(ROOT)), "sha256_12": sha12(fp),
                        "n_lines": witness_src.count("\n"),
                        "n_bytes": len(witness_src.encode("utf-8")),
                        "gpu_free_by_construction": ("只 import os/sys/time + 忙等循环；不开 "
                                                     "/dev/nvidia*、不建 GL/CUDA 上下文"),
                        "committed": "否（`tmp/` 不入库，与他线跑日志同口径）"}
    teeth.append(_run_witness(
        "tooth1_nvidia_fd_holder_must_be_true",
        [py, "-c",
         "import sys,time\n"
         "for mode in ('r+b','rb'):\n"
         "    try:\n"
         "        f=open('/dev/nvidiactl',mode); break\n"
         "    except OSError as e:\n"
         "        f=None; err=e\n"
         "if f is None:\n"
         "    print('OPENFAIL',err,flush=True); sys.exit(9)\n"
         "print('HELD /dev/nvidiactl',flush=True)\n"
         "time.sleep(%d)\n" % hold_s, "--b2-tooth1-fd-holder"],
        True, ("持 `/dev/nvidiactl` 但**不分配 compute 显存** ⇒ 网①（`nvidia-smi --query-compute-apps`）"
               "**看不见它**；只有网② 扫 `/proc/*/fd` 能看见。这条牙证明裁定 85.6-2 的三网化补上了"
               "旧探测器的 EGL 盲区（A2 的 rep4/rep5 就栽在这个盲区上）。"),
        expect_nets=["net2_nvidia_fd"], expect_legacy_detected=False))

    teeth.append(_run_witness(
        "tooth2_idle_bash_must_be_false",
        ["bash", "-c", "cd %s && sleep %d" % (ROOT, hold_s)],
        False, ("cmdline 里含仓库路径 ⇒ **第一版判据**（『任何 args 里含仓库名的进程』）会把它算成共租，"
                "于是一个 pcpu=0.0 的遗留 shell 就能让每份产物永久标 contaminated（狼来了）。"
                "这条牙证明修好之后它**不再**触发。"),
        expect_nets=[], expect_legacy_detected=False))

    teeth.append(_run_witness(
        "tooth3_own_line_busy_job_must_be_true",
        [py, str(fixture_root / "b2_tooth3_witness_busy.py"), "--hold", str(hold_s),
         "--b2-tooth3-busy-no-gpu"],
        True, ("**执行位**上是线内脚本 `scripts/b2_*.py` 且 `pcpu>1%`、**完全不碰 GPU** ⇒ "
               "网①/网② 都不会命中（它没有 GPU 上下文），必须由**信号②**（归线 `b2` + `pcpu>1%`）"
               "命中。这就是 D 牙③的字面要求，也是「第二个 B2 采集作业不许隐形」的证人。"
               "注意：网③ 的宽档按**线相对**口径排除了 `b2_`（否则 agent 自己 `sed` 一下本线脚本"
               "就会把每份产物标脏），本线由信号② 承载 ⇒ 这条牙同时证明了**信号② 不能加"
               "「∧ GPU 关键字」那个合取**（加了它就漏检，见 `line_job_evidence` 的 docstring）。"
               "**argv 形态已按裁定 96.1-③ 升级**：旧证人把脚本名塞在 `-c` 之后当附加参数，"
               "那不是执行形态；旧形态本身现在是牙④ 的负向证人。"),
        expect_nets=["signal2_active_line"], expect_legacy_detected=True))

    teeth.append(_run_witness(
        "tooth4_text_mention_only_busy_cpu_process_must_be_false",
        ["bash", "-c",
         "echo torchrun accelerate deepspeed lerobot-train a2_egl_latency_remeasure "
         "--mode closed_loop quiet_window MUJOCO_GL=egl ballast --allow-cotenant "
         "scripts/e_mainline_render_calib.py scripts/a2_s4b_outcome_ledger_verify.py "
         "cd %s RL_Robot > /dev/null; end=$((SECONDS+%d)); "
         "while [ $SECONDS -lt $end ]; do :; done" % (ROOT, hold_s)],
        False, ("**RR-B2-18 的字面形态 · 负向腿（裁定 93.8）**：一个 `pcpu>1%` 的**纯 CPU** 进程，"
                "cmdline 里把窄档关键字（`torchrun`/`a2_egl_latency_remeasure`/`--mode closed_loop`/"
                "`quiet_window`/`MUJOCO_GL=egl`/`ballast`/`--allow-cotenant`）、他线脚本名"
                "（`scripts/e_…`、`scripts/a2_…`）与仓库名（`RL_Robot`）**全说了一遍**，"
                "但一个都没**执行** ⇒ 必须**不**判 contaminated。修法前它必然被判脏"
                "（`legacy_caliber_would_detect=true`，且旧判据还会按全文里的 `/a2_` 把它"
                "**归线成 a2**）⇒ 这一条与牙⑤ 合起来才是两向；只装一向不许报绿（缺陷类 ⑲）。"
                "它**不是闲置**进程（在忙等）⇒ 排除它的只能是「执行形态」那一维，"
                "不会与牙② 的闲置排除互相打掩护。"),
        expect_nets=[], expect_legacy_detected=True))

    teeth.append(_run_witness(
        "tooth5_other_line_real_exec_form_must_be_true",
        [py, str(fixture_root / "a_b2tooth5_witness_real_form.py"), "--hold", str(hold_s),
         "--b2-tooth5-real-form-no-gpu"],
        True, ("**正向腿 / 反漏检**：执行位上真是**他线**脚本（`scripts/a_*`）、`pcpu>1%`、不碰 GPU "
               "⇒ 必须由**网③ 宽档**命中（收紧之后仍然咬得住「别线真在跑」）。证人走 `a_` 前缀"
               "而不是 `a2_` ⇒ 信号② 不归线（`line_tag=other`）⇒ 命中的只可能是网③，"
               "两条信号不会互相打掩护；`expect_nets` 因此是单元素。"),
        expect_nets=["net3_cmdline"], expect_legacy_detected=True))

    n_pass = sum(1 for t in teeth if t.get("status") == "PASS")
    n_red = sum(1 for t in teeth if t.get("status") == "RED")
    n_na = sum(1 for t in teeth if t.get("status") == "N_A")

    # ---- 裁定 96.1-③ 的对账腿：与 E 的参考实现 / F 的口径出处**现取**对账（同一 run 目录）----
    align_path = out_root / "CMDLINE_CALIBER_ALIGNMENT.json"
    align = cmdline_caliber_alignment_probe(align_path)
    align_ident = {"path": str(align_path),
                   "sha256_12": sha12(align_path) if align_path.exists() else None,
                   "n_lines": (align_path.read_bytes().count(b"\n")
                               if align_path.exists() else None),
                   "citation_algo": "sha256[:12]", "as_of": now_iso()}

    # ---- 差分两向（裁定 93.8）：同一条活体证人，修法前的判据 vs 修法后的判据 ----
    judged = [t for t in teeth if t.get("status") != "N_A"]
    flip_ids = [t["tooth"] for t in judged
                if t.get("observed_legacy_detected") and not t.get("observed_detected")]
    keep_ids = [t["tooth"] for t in judged
                if t.get("observed_legacy_detected") and t.get("observed_detected")]
    new_only_ids = [t["tooth"] for t in judged
                    if not t.get("observed_legacy_detected") and t.get("observed_detected")]
    neither_ids = [t["tooth"] for t in judged
                   if not t.get("observed_legacy_detected") and not t.get("observed_detected")]
    both_directions_proven = bool(flip_ids and keep_ids)

    doc = {"artifact": "b2_cotenant_detector_teeth", "generated_at": now_iso(),
           "generator": "scripts/b2_s1_generate_dataset.py", "generator_sha256_12": sha12(SCRIPT),
           "generator_n_lines": SCRIPT.read_bytes().count(b"\n"),
           "python": py, "hold_s": hold_s, "wait_s": wait_s,
           "detector": ("card_busy_three_net(strict=True) + 信号②（**执行位**归线 ∧ 非闲置 ∧ "
                        "pcpu>%s%%）" % GPU_LINE_ACTIVE_PCPU),
           "ruling": ("裁定 85.6-2（§18.6-2）：`contaminated_by_cotenant` 三信号驱动 + 三条牙；"
                      "`gpu_preflight()` 一并升级为三网。**裁定 96.1-③ / RR-B2-18（本次）**：网③ 与"
                      "信号② 的判据改为「真实执行形态 ∧ 关键字 ∧ 非闲置」；牙③ 的证人 argv 形态随之"
                      "升级；新增牙④（负向腿）与牙⑤（正向腿/反漏检）⇒ 五条牙"),
           "rr_b2_18": {
               "status": "fixed_this_run",
               "defect": ('旧纳入条件 `tag=="other" and "RL_Robot" in args` + 网③ 的裸字面量匹配 '
                          '⇒ `contaminated_by_cotenant` **永久为真**（B2 自报，D 认定与 E 的 '
                          '`card_busy()` 同族同因）'),
               "root_cause": ("网在匹配「关于 GPU 的**文本**」，不是「GPU **占用**」（裁定 96.1-③）"),
               "fix": CALIBER_RULING_96_1_3,
               "nets_not_touched": ("网①`compute-apps` 与网②`/dev/nvidia*` fd **一个字节都没改**："
                                    "它们是「占用」的直接证据，不是文本（牙① 因此照旧成立）"),
               "before_image": ("tmp/b2_before_images_rr18_20260930/"
                                "b2_s1_generate_dataset.py.before_rr18（4333 ln `b6af48fc6d58`）"),
               "generator_byte_identity_changed": True,
               "generator_byte_identity_note": (
                   "本件字节已**不等于**产出 formal-40 的那份生成器字节 `b6af48fc6d58`。"
                   "formal-40 的产物身份不受影响（本次只改共租判定，不重采、不动数据一个字节），"
                   "但从此引用本件身份**必须带 as_of**，且不得再声称 "
                   "`generator_sha_matches_formal_batch=true`（裁定 96.1-① / 缺陷类 ㉒）")},
           "judged_by": "**witness PID 是否被命中**（不看全局 busy，避免被别人在跑的作业污染判定）",
           "baseline_before_witnesses": baseline,
           "baseline_note": ("若 baseline 的三网已有外来命中，说明采样时机器上本来就有别人在跑；"
                             "这不影响按 PID 的判定，但要如实登记"),
           "witness_fixtures": fixtures,
           "fixture_naming_note": (
               "fixture 目录 `tmp/rr18_cotenant_teeth/scripts/` **故意不含 `/b2_` 路径段**："
               "旧判据按 args 全文里的 `/b2_` 归线，若目录名自带 `/b2_`，牙⑤ 的差分对照就会被"
               "**文本**归线成 b2 —— 那正是本次要修的缺陷，不许混进对照物"),
           "teeth": teeth,
           "n_teeth": len(teeth), "n_pass": n_pass, "n_red": n_red, "n_unjudged": n_na,
           "differential_two_way": {
               "flip_ids": flip_ids, "keep_ids": keep_ids,
               "new_only_ids": new_only_ids, "neither_ids": neither_ids,
               "both_directions_proven": both_directions_proven,
               "assertion": ("裁定 93.8：**只装一向不许报绿**（缺陷类 ⑲）。`flip` = 修法前判脏、"
                             "修法后不判脏（负向腿，必须 ≥1）；`keep` = 两版都判脏（正向腿/反漏检，"
                             "必须 ≥1）；`new_only` = 只有网①/网② 看得见的（牙①，与本次修法无关）；"
                             "`neither` = 两版都不判（牙②）"),
               "legacy_caliber": ("`_legacy_rr_b2_18_verdict`（修法前判据的逐字复刻）；**只被差分腿"
                                  "调用**，生产路径不用它"),
               "measurement_status": "measured"},
           "cmdline_caliber_alignment": {
               **align_ident, "ok": align.get("ok"), "verdict": align.get("verdict"),
               "measurement_status": align.get("measurement_status"),
               "legs_all_ok": align.get("legs_all_ok"),
               "not_measured_reason": align.get("not_measured_reason"),
               "references": align.get("references"),
               "why_it_exists": ("B2 自带 `classify_cmdline` 的**副本**（不 import E 的模块，理由见 "
                                 "`_extract_caliber_reference`）⇒ 副本会**静默**漂移（裁定 46.4 的"
                                 "根因形态；E 在 §E13.1.6 点了这一条）⇒ 每轮现取对账")},
           "gpu_boundary": {
               "gpu_used_for_render_or_compute": False,
               "dev_nvidia_opened_by": (
                   "牙① 的证人**故意**持 `/dev/nvidiactl` 的 fd（`r+b`，打不开则退 `rb`）—— 那正是"
                   "网② 要抓的形态；它**不分配 compute 显存、不建 GL/CUDA 上下文**（牙① 采样时"
                   "`compute-apps` 里没有它，就是这一句的实测证据）"),
               "other_teeth": "牙②–牙⑤ 的证人是纯 CPU（忙等 / `sleep` / `echo`），只 import os/sys/time",
               "nvidia_smi_queries": "只读（`card_busy_three_net` 的网①）",
               "no_root_filesystem_scans": True},
           "ok": bool(n_red == 0 and n_na == 0 and both_directions_proven and align.get("ok")),
           "ok_conjuncts": {"no_red_teeth": bool(n_red == 0), "no_unjudged_teeth": bool(n_na == 0),
                            "both_directions_proven": both_directions_proven,
                            "caliber_alignment_ok": bool(align.get("ok"))},
           "all_teeth_bite": bool(n_pass == len(teeth)),
           "policy_executed": False, "capability_claim": None, "not_a_capability_claim": True}
    p = note_write(out_root / "cotenant_detector_teeth.json")
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=_json_default),
                 encoding="utf-8")
    print(json.dumps({"artifact": str(p), "n_pass": n_pass, "n_red": n_red, "n_unjudged": n_na,
                      "ok": doc["ok"],
                      "ok_conjuncts": doc["ok_conjuncts"],
                      "differential_two_way": {k: doc["differential_two_way"][k] for k in
                                               ("flip_ids", "keep_ids", "new_only_ids",
                                                "neither_ids", "both_directions_proven")},
                      "cmdline_caliber_alignment": {
                          "artifact": str(align_path), "ok": align.get("ok"),
                          "verdict": align.get("verdict"),
                          "measurement_status": align.get("measurement_status"),
                          "legs_all_ok": align.get("legs_all_ok")},
                      "per_tooth": [{"tooth": t["tooth"], "status": t.get("status"),
                                     "expect": t.get("expect_detected"),
                                     "observed": t.get("observed_detected"),
                                     "legacy_observed": t.get("observed_legacy_detected"),
                                     "detected_by": ((t.get("sample") or {}).get("detected_by"))}
                                    for t in teeth]}, ensure_ascii=False, indent=1))
    return 0 if doc["ok"] else 3


def activation_env() -> dict:
    """裁定 70：只读环境变量事实 + `prefix_paths_verified` 三条布尔（A2 的格式为范例）。"""
    ld = os.environ.get("LD_LIBRARY_PATH") or ""
    vj = os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES")
    prefix_active = any(c in ld for c in PREFIX_CANDIDATES)
    vj_exists = bool(vj) and Path(vj).exists()
    vj_points = False
    if vj_exists:
        try:
            lib = json.loads(Path(vj).read_text())["ICD"]["library_path"]
            vj_points = any(str(lib).startswith(c) or c in str(lib) for c in PREFIX_CANDIDATES)
        except Exception:                                        # noqa: BLE001
            vj_points = False
    return {"MUJOCO_GL": os.environ.get("MUJOCO_GL"),
            "PYOPENGL_PLATFORM": os.environ.get("PYOPENGL_PLATFORM"),
            "LD_LIBRARY_PATH": ld or None,
            "__EGL_VENDOR_LIBRARY_FILENAMES": vj,
            "__EGL_VENDOR_LIBRARY_DIRS": os.environ.get("__EGL_VENDOR_LIBRARY_DIRS"),
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "nvidia_prefix_active": prefix_active,
            "prefix_paths_verified": {"prefix_in_ld_library_path": prefix_active,
                                      "vendor_json_points_into_prefix": vj_points,
                                      "vendor_json_exists": vj_exists},
            "activation_authority":
                'eval "$(bash scripts/e_activate_gpu_render.sh --print)"（裁定 70：不硬编码目录名）'}


def gl_identity() -> dict:
    """裁定 72-1：`MUJOCO_GL` 只表达意图，`GL_RENDERER` 才表达事实（A2 的取法）。"""
    import mujoco
    out = {"method": "mujoco.Renderer + OpenGL.GL.glGetString（renderer 存活期内）",
           "mujoco_version": mujoco.__version__,
           "identity_source": "mujoco.Renderer(独立探针)"}
    try:
        m = mujoco.MjModel.from_xml_string(
            "<mujoco><worldbody><geom type='box' size='.1 .1 .1'/></worldbody></mujoco>")
        d = mujoco.MjData(m)
        mujoco.mj_forward(m, d)
        r = mujoco.Renderer(m, 64, 64)
        r.update_scene(d)
        px = r.render()
        from OpenGL import GL
        strs = {k: GL.glGetString(getattr(GL, k)) for k in ("GL_VENDOR", "GL_RENDERER", "GL_VERSION")}
        out.update({"render_ok": True, "render_shape": list(px.shape),
                    "render_byte_mean": round(float(px.mean()), 4),
                    "gl_strings": {k: (v.decode() if isinstance(v, bytes) else v)
                                   for k, v in strs.items()}})
        rend = (out["gl_strings"].get("GL_RENDERER") or "").upper()
        out["renderer_class"] = ("nvidia_gpu" if "NVIDIA" in rend else
                                 "mesa_cpu_software" if ("LLVMPIPE" in rend or "SOFTPIPE" in rend)
                                 else "unknown")
        r.close()
    except Exception as e:                                       # noqa: BLE001
        import traceback
        out.update({"render_ok": False, "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc()[-1200:], "renderer_class": "unknown_error"})
    return out


def git_head() -> dict:
    out = {}
    for k, cmd in (("head", ["git", "rev-parse", "HEAD"]),
                   ("branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"]),
                   ("head_short", ["git", "rev-parse", "--short", "HEAD"])):
        try:
            p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            out[k] = p.stdout.strip() if p.returncode == 0 else f"ERROR rc={p.returncode}"
        except Exception as e:                                   # noqa: BLE001
            out[k] = f"ERROR {type(e).__name__}: {e}"
    try:
        p = subprocess.run(["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True,
                           text=True, timeout=60)
        lines = [l for l in p.stdout.splitlines() if l.strip()]
        out["n_dirty_paths"] = len(lines)
        out["dirty_paths_head"] = lines[:12]
    except Exception as e:                                       # noqa: BLE001
        out["n_dirty_paths"] = f"ERROR {type(e).__name__}: {e}"
    out["note"] = "runs/ 被 .gitignore:12 排除 ⇒ 本脚本的数据产物只在 NFS，不进 git（裁定 69.1）"
    return out


def versions() -> dict:
    import importlib.metadata as md
    out = {}
    for m in ("mujoco", "dm_control", "gym-aloha", "lerobot", "numpy", "torch", "transformers",
              "pyarrow", "av"):
        try:
            out[m] = md.version(m)
        except Exception:                                        # noqa: BLE001
            out[m] = None
    out["python"] = sys.version.split()[0]
    out["platform"] = platform.platform()
    out["venv_python"] = sys.executable
    return out


# ========================================================================== 三值判据聚合
class Report:
    """三值（PASS/WARN/RED/UNJUDGED）判据聚合。每道闸必须带 `required` / `red_when` /
    `applies_when`（裁定 72-2：不适用的闸输出 `n_a` + 理由，**不许**输出 `ok=false` 造假红）。"""

    def __init__(self):
        self.checks: List[dict] = []

    def add(self, cid: str, ok: Optional[bool], observed: Any, required: str, *,
            note: str = "", ruling_ref: str = "", red_when: str = "", applies_when: str = "always",
            mutation_expected_red: bool = False, blocking: bool = True):
        """`blocking=False`（裁定 85.5）：这条 check **只登记**，即使 `ok=False` 也不得让批次判红。

        为什么需要这个字段：像素侧被降级之后，闸仍然要跑、数仍然要落，但它的结论**不参与判定**。
        不写明 `blocking` 就会让下游分不清"哪条红是真红"⇒ 正是裁定 27.1「恒真的闸等于没有闸」
        的镜像毛病（恒不红的闸被当成保护层引用）。
        """
        status = "UNJUDGED" if ok is None else ("PASS" if ok else "RED")
        self.checks.append({"id": cid, "status": status, "ok": ok, "observed": observed,
                            "required": required, "note": note, "ruling_ref": ruling_ref,
                            "red_when": red_when, "applies_when": applies_when,
                            "mutation_expected_red": mutation_expected_red,
                            "blocking": bool(blocking)})
        return status

    def warn(self, cid: str, observed: Any, required: str, **kw):
        kw.pop("ok", None)
        self.checks.append({"id": cid, "status": "WARN", "ok": None, "observed": observed,
                            "required": required, **kw})

    def n_a(self, cid: str, reason: str, required: str, *, observed_extra: Optional[dict] = None,
            red_when: str = "", **kw):
        """N_A（裁定 72-2：不适用的闸输出 `n_a` + 理由，**不许**输出 `ok=false` 造假红）。

        实测量必须落在 `observed` **里面**（裁定 78.2 的最小公共 check schema =
        `id / ok / status / required / observed / red_when`）：第一版把它们放在同级的
        `observed_measured` 键上 ⇒ 任何只读 `observed` 的下游会看到"只有理由、没有数"。
        """
        obs = {"reason": reason, "n_a_kind": "criterion_not_applicable"}
        if observed_extra:
            obs["measured"] = observed_extra
        self.checks.append({"id": cid, "status": "N_A", "ok": None, "observed": obs,
                            "required": required, "red_when": red_when,
                            "applies_when": "conditional", "blocking": False, **kw})

    @property
    def blocking_red_ids(self) -> List[str]:
        """**只有 blocking 的 RED 才算失败**（裁定 85.5：像素侧登记项不参与判定）。"""
        return [c["id"] for c in self.checks
                if c["status"] == "RED" and c.get("blocking", True)]

    @property
    def n_nonblocking(self) -> int:
        return sum(1 for c in self.checks if not c.get("blocking", True))

    @property
    def n_red(self) -> int:
        return sum(1 for c in self.checks if c["status"] == "RED")

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c["status"] == "WARN")

    @property
    def n_a_count(self) -> int:
        return sum(1 for c in self.checks if c["status"] == "N_A")

    @property
    def n_unjudged(self) -> int:
        return sum(1 for c in self.checks if c["status"] == "UNJUDGED")

    @property
    def red_ids(self) -> List[str]:
        return [c["id"] for c in self.checks if c["status"] == "RED"]

    @property
    def verdict(self) -> str:
        if self.blocking_red_ids:
            return "RED"
        if self.n_warn or self.n_unjudged:
            return "WARN"
        return "PASS"


# ========================================================================== 相机/几何工具
_ctx_upstream_state14: Optional[dict] = None


def upstream_reset_state14() -> dict:
    """从**上游源码常量**重构复位 14 维状态（独立于本线的 env 封装，也不依赖 A2 的 JSON）。

    为什么要这一层：A2 契约的 `state_raw_14d` 是**四舍五入到 6 位小数**写进 JSON 的
    （0.099848331… → 0.099848），拿它做"逐位相同"必然差 3.3e-07 ⇒ 闸会永久红、也就永久没用。
    所以逐位比的对象换成"用上游 `START_ARM_POSE` + `normalize_puppet_gripper_position` 现算的值"，
    契约那份按它自己的 6 位小数口径比（两边都 round 到 6 位再逐位）。
    """
    global _ctx_upstream_state14
    if _ctx_upstream_state14 is None:
        try:
            from gym_aloha import constants as gc
            sap = [float(x) for x in gc.START_ARM_POSE]
            gl = float(gc.normalize_puppet_gripper_position(sap[6]))
            gr = float(gc.normalize_puppet_gripper_position(sap[14]))
            v = np.asarray(list(sap[0:6]) + [gl] + list(sap[8:14]) + [gr], dtype=np.float64)
            _ctx_upstream_state14 = {
                "status": "reconstructed_from_upstream_constants",
                "sources": ["gym_aloha/constants.py:START_ARM_POSE",
                            "gym_aloha/constants.py:normalize_puppet_gripper_position",
                            "gym_aloha/tasks/sim.py:113（qpos[:16] = START_ARM_POSE）",
                            "gym_aloha/tasks/sim.py:61-69（get_qpos 的 14 维装配与归一化）"],
                "start_arm_pose_16d": sap,
                "state14_reconstructed": [float(x) for x in v],
                "assembly_order": "[左臂6, 左夹爪1(normalized), 右臂6, 右夹爪1(normalized)]"}
        except Exception as exc:                                    # pragma: no cover
            _ctx_upstream_state14 = {"status": "UNJUDGED",
                                     "why": "读上游常量失败：%r" % (exc,),
                                     "state14_reconstructed": None}
    return _ctx_upstream_state14


_ctx_box_geom: Optional[dict] = None


def box_geom_measured() -> dict:
    """从模型里**实测**方块几何，不硬编码 0.04。

    G9 的夹持期望值 = probe4 空载闭合指距 + **方块实测宽**，所以方块宽必须是读出来的：
    mujoco 3.8.1 里 `geom_type==6` 是 mjGEOM_BOX，`geom_size` 存的是**半**长宽高。
    """
    global _ctx_box_geom
    if _ctx_box_geom is None:
        import mujoco
        m = mujoco.MjModel.from_xml_path(joint_xml_path())
        gid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "red_box")
        if gid < 0:
            _ctx_box_geom = {"status": "UNJUDGED", "why": "模型里没有名为 red_box 的 geom"}
        else:
            half = [round(float(v), 6) for v in np.asarray(m.geom_size[gid], dtype=float)[:3]]
            _ctx_box_geom = {
                "status": "measured_from_model", "geom": "red_box",
                "geom_type_id": int(m.geom_type[gid]),
                "geom_type_name": "mjGEOM_BOX" if int(m.geom_type[gid]) == 6 else "other",
                "half_extents_xyz_m": half, "width_m": round(2.0 * half[0], 6),
                "depth_m": round(2.0 * half[1], 6), "height_m": round(2.0 * half[2], 6),
                "is_cube": bool(len(set(half)) == 1),
                "note": "geom_size 是半长宽高 ⇒ 全宽 = 2×size[0]；立方体 ⇒ 沿哪个轴夹都一样"}
    return _ctx_box_geom


def _camera_xml_line(cam_name: str) -> Optional[str]:
    """从**资产 XML 原文**里把定义该相机的那一行捞出来（裁定 64：引用带文件身份；不靠记忆）。"""
    import gym_aloha
    import re
    pkg = Path(gym_aloha.__file__).resolve().parent / "assets"
    for fn in ("scene.xml", "vx300s_left.xml", "vx300s_right.xml",
               "bimanual_viperx_transfer_cube.xml", "vx300s_dependencies.xml"):
        f = pkg / fn
        if not f.exists():
            continue
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if "<camera" in line and ('name="%s"' % cam_name) in line:
                return "%s:%d: %s" % (fn, i, line.strip())
    return None


def camera_intrinsics(physics, cam_name: str, h: int, w: int) -> dict:
    """按**真相机模型**算内参（修正 ABC-130k 里 25 条 intrinsics 不自洽的同族问题）。

    MuJoCo 走 `gluPerspective(fovy, aspect=w/h)` 那条路 ⇒ `fy = (h/2)/tan(fovy/2)`、`fx = fy`
    （方形像素）、`cx = w/2`、`cy = h/2`，水平视场由宽高比导出
    （`fovx = 2·atan(tan(fovy/2)·w/h)`）。⇒ **同一相机在 480×640 与 224² 下 fx/fy/cx/cy 全不同**，
    两档必须各记各的（这也正是 224² 不能由 480×640 缩放代替的定量理由）。

    **不猜**：若 XML 显式给了 `intrinsic`/`sensorsize`/`resolution`（则 fovy 被覆盖），
    判 `UNJUDGED`（三值纪律）。判据取**XML 原文行**，不读模型里的默认值 ——
    mujoco 3.8.1 的 `cam_intrinsic` 即使 XML 没写也是 `[0.1,0.1,0,0]`、`cam_resolution=[1,1]`
    （B2 2026-09-29 23:3x 实测：toy XML 给 `[0.01,0.01,0,0]`，gym-aloha 给 `[0.1,0.1,0,0]`，
    两者都没写 intrinsic ⇒ 那是默认值不是声明值，拿它当判据会全判 UNJUDGED）。

    像素约定：图像行 0 在上 ⇒ `u = fx·X/Z + cx`、`v = cy − fy·Y/Z`（相机系 Y 向上、Z 向前）。
    这条约定由 `project_and_verify_intrinsics` **实测确认**，不是照抄文档。
    """
    import mujoco
    m = physics.model.ptr
    cid = physics.model.name2id(cam_name, "camera")
    fovy = float(m.cam_fovy[cid])
    xml_line = _camera_xml_line(cam_name)
    explicit = None
    if xml_line:
        for attr in ("intrinsic", "sensorsize", "resolution"):
            if (attr + "=") in xml_line:
                explicit = attr
    if explicit:
        return {"status": "UNJUDGED", "camera": cam_name, "h": h, "w": w, "fovy_deg": fovy,
                "xml_line": xml_line,
                "why": "XML 显式给了 %s ⇒ fovy 被覆盖，B2 不猜像素焦距（三值纪律）" % explicit}
    fy = (h / 2.0) / math.tan(math.radians(fovy) / 2.0)
    K = [[round(fy, 6), 0.0, round(w / 2.0, 6)],
         [0.0, round(fy, 6), round(h / 2.0, 6)],
         [0.0, 0.0, 1.0]]
    return {"status": "measured_from_model_and_xml", "camera": cam_name, "h": h, "w": w,
            "fovy_deg": fovy, "xml_line": xml_line,
            "model_defaults_not_used_as_evidence": {
                "cam_intrinsic": np.asarray(m.cam_intrinsic[cid], dtype=float).tolist(),
                "cam_resolution": np.asarray(m.cam_resolution[cid], dtype=float).tolist(),
                "cam_sensorsize": np.asarray(m.cam_sensorsize[cid], dtype=float).tolist()},
            "fx": round(fy, 6), "fy": round(fy, 6), "cx": round(w / 2.0, 6), "cy": round(h / 2.0, 6),
            "fovx_deg": round(math.degrees(2.0 * math.atan(math.tan(math.radians(fovy) / 2.0)
                                                           * (w / h))), 6),
            "K_3x3": K,
            "pixel_convention": "u=fx·X/Z+cx, v=cy−fy·Y/Z（图像行 0 在上；由 G16 实测确认）",
            "formula": "fy=(h/2)/tan(fovy/2); fx=fy（方形像素）; cx=w/2; cy=h/2"}


def project_and_verify_intrinsics(img: np.ndarray, w2c, K, world_xyz: np.ndarray,
                                  search_radius: int = 60,
                                  expect_depth_sign: Optional[int] = None,
                                  tight_radius: int = PROJECTION_TIGHT_RADIUS_PX) -> dict:
    """**用像素验证内参**（G16）：把一个已知世界点（红色方块中心）按 K 与 w2c 投到图像上，
    再看那附近有没有"红占优"的像素。投得准 ⇒ 内参与 w2c 都对；投歪了 ⇒ 至少一个是错的。

    这是"内参自洽"这句话的验收形式：ABC-130k 有 25 条 intrinsics 与自己的分辨率不自洽，
    而团队 QC 只查 `has_intrinsics_3x3`（`common/episode_stats.py:311`）⇒ **形状对就算过**，
    所以自洽性只能自己拿像素证。
    """
    W2C = np.asarray(w2c, dtype=float)
    R, t = W2C[:3, :3], W2C[:3, 3]
    cam_world = -R.T @ t
    p_cam = R @ (np.asarray(world_xyz, dtype=float) - cam_world)
    out = {"cam_world_xyz": [round(float(v), 4) for v in cam_world],
           "point_world_xyz": [round(float(v), 4) for v in world_xyz],
           "point_in_camera_xyz": [round(float(v), 4) for v in p_cam],
           "z_forward_positive": bool(p_cam[2] > 0)}
    K3 = np.asarray(K, dtype=float)
    fx, fy, cx, cy = K3[0, 0], K3[1, 1], K3[0, 2], K3[1, 2]
    h, w = img.shape[:2]
    # **四种约定都算一遍，由命中的那个定约定**（不照抄文档、不预设相机看 +z 还是 −z）。
    # B2 2026-09-30 实测：MuJoCo 固定相机的 `target_in_cam_xyz[2] = −0.8 < 0` ⇒ 相机沿自己的
    # **−z** 看（OpenGL 约定）⇒ 可见点的深度 = −p_cam[2]。第一版只试了 depth=+p_cam[2]，
    # 于是每个点都判 "Z<=0 投影无定义" ⇒ G16 全 UNJUDGED（闸空转，一个像素都没验到）。
    variants = {}
    for sz, szn in ((1.0, "depth_plus_z"), (-1.0, "depth_minus_z")):
        depth = sz * float(p_cam[2])
        if depth <= 1e-6:
            continue
        u = fx * p_cam[0] / depth + cx
        for sy, syn in ((-1.0, "v_up_minus"), (1.0, "v_up_plus")):
            variants["%s__%s" % (szn, syn)] = (float(u),
                                               float(cy + sy * fy * p_cam[1] / depth))
    if not variants:
        out["status"] = "UNJUDGED"
        out["why"] = ("点在两种深度符号下都落在焦平面上/相机后方（|Z| ≤ 1e-6）⇒ 投影无定义，"
                      "不拿 0 填充")
        return out
    a = np.asarray(img, dtype=int)
    red = (a[..., 0] > 90) & (a[..., 0] > a[..., 1] + 25) & (a[..., 0] > a[..., 2] + 25)
    ys, xs = np.nonzero(red)
    out["n_red_dominant_pixels"] = int(red.sum())
    centroid = ((float(xs.mean()), float(ys.mean())) if len(xs) else None)
    out["red_blob_centroid_uv"] = ([round(centroid[0], 2), round(centroid[1], 2)]
                                   if centroid else None)
    res = {}
    for name, (u, v) in variants.items():
        if not (0 <= u < w and 0 <= v < h):
            res[name] = {"u": round(float(u), 2), "v": round(float(v), 2), "inside": False,
                         "dist_to_nearest_red_px": None, "dist_to_red_centroid_px": None}
            continue
        dmin = float(np.hypot(xs - u, ys - v).min()) if len(xs) else None
        dcen = float(math.hypot(centroid[0] - u, centroid[1] - v)) if centroid else None
        res[name] = {"u": round(float(u), 2), "v": round(float(v), 2), "inside": True,
                     "dist_to_nearest_red_px": (round(dmin, 3) if dmin is not None else None),
                     "dist_to_red_centroid_px": (round(dcen, 3) if dcen is not None else None),
                     "hit_within_%dpx" % search_radius: bool(dmin is not None and
                                                             dmin <= search_radius),
                     "hit_within_%dpx_tight" % tight_radius: bool(dmin is not None and
                                                                  dmin <= tight_radius)}
    out["projections"] = res
    # **判定用紧半径**：方块是一整块红斑（team_head 里 306 px），60 px 的松半径会让**错的**
    # 约定也"命中"（实测错的 v_up_plus 落在 57.4 px 处 ⇒ ambiguous，闸什么也判不了）。
    # 紧半径 8 px 下正确的约定命中 0.37/0.65 px（亚像素），错的 57.4/11.5 px ⇒ 唯一命中。
    good = [k for k, v in res.items() if v.get("hit_within_%dpx_tight" % tight_radius)]
    out["loose_hits_within_%dpx" % search_radius] = [
        k for k, v in res.items() if v.get("hit_within_%dpx" % search_radius)]
    out["tight_radius_px"] = tight_radius
    # 两个 v 约定的**可分辨间距** = |v_up_minus − v_up_plus| = 2·fy·|Y|/depth。
    # 当被测点落在相机的光轴水平面附近（Y≈0）时这个间距 → 0，两种约定**物理上不可分辨**：
    # B2 2026-09-30 先导实测有 2/10 集栽在这里（间距 4.64 px < 2×8 px，两约定都命中 0.35 px）。
    # 这不是数据缺陷，是**探针点退化** ⇒ 按三值纪律标 UNJUDGED，而不是判红或硬挑一个。
    v_sep = {}
    for szn in ("depth_plus_z", "depth_minus_z"):
        km, kp = szn + "__v_up_minus", szn + "__v_up_plus"
        if km in variants and kp in variants:
            v_sep[szn] = round(abs(variants[km][1] - variants[kp][1]), 3)
    out["v_convention_separation_px"] = v_sep
    out["v_convention_resolvable"] = {k: bool(v >= 2.0 * tight_radius) for k, v in v_sep.items()}
    degenerate = False
    if len(good) > 1:
        signs = {k.split("__")[0] for k in good}
        degenerate = (len(signs) == 1 and
                      not out["v_convention_resolvable"].get(next(iter(signs)), True))
    out["projection_convention_measured"] = (
        good[0] if len(good) == 1 else
        ("%s__v_axis_UNJUDGED_degenerate" % next(iter({k.split("__")[0] for k in good}))
         if degenerate else ("ambiguous_%d_hit" % len(good) if good else "none_hit")))
    out["depth_sign_measured"] = (
        ("+z" if good[0].startswith("depth_plus") else "−z")
        if (len(good) == 1 or degenerate) else None)
    out["v_axis_measured"] = (
        ("v_up_minus" if good[0].endswith("v_up_minus") else "v_up_plus") if len(good) == 1
        else ("UNJUDGED_degenerate" if degenerate else None))
    if degenerate:
        out["why"] = ("被测点（方块中心）落在相机光轴水平面附近：两个 v 约定的投影只差 %s px "
                      "< 2×紧半径 %d px ⇒ v 轴约定**物理上不可分辨**，判 UNJUDGED（不硬挑一个、"
                      "也不判红）。深度符号仍由『点必须在相机前方』唯一确定为 %s，"
                      "且像素命中 %s px ⇒ K 与 w2c 本身是被验到的"
                      % (v_sep, tight_radius, out["depth_sign_measured"],
                         {k: v.get("dist_to_nearest_red_px") for k, v in res.items()}))
    out["status"] = ("measured_ok" if len(good) == 1 else
                     ("measured_ok_v_axis_degenerate" if degenerate else
                      ("measured_ambiguous" if len(good) > 1 else "measured_mismatch")))
    if len(good) == 0 and out["loose_hits_within_%dpx" % search_radius]:
        out["why"] = ("松半径（%d px）下有命中、紧半径（%d px）下没有 ⇒ 投影偏了 %s px，"
                      "内参或 w2c 至少一个是错的"
                      % (search_radius, tight_radius,
                         {k: v.get("dist_to_nearest_red_px") for k, v in res.items()}))
    out["search_radius_px"] = search_radius
    out["n_conventions_tried"] = len(variants)
    if expect_depth_sign is not None and (len(good) == 1 or degenerate):
        out["depth_sign_expected_from_targetbody_diag"] = ("+z" if expect_depth_sign > 0 else "−z")
        out["depth_sign_agrees_with_targetbody_diag"] = bool(
            (expect_depth_sign > 0) == (out["depth_sign_measured"] == "+z"))
        if not out["depth_sign_agrees_with_targetbody_diag"]:
            out["status"] = "measured_inconsistent"
            out["why"] = ("像素命中的深度符号（%s）与 targetbody 独立测出的轴约定（%s）不一致 ⇒ "
                          "两条独立测量互相打脸，w2c 或 K 至少有一个是错的"
                          % (out["depth_sign_measured"],
                             "+z" if expect_depth_sign > 0 else "−z"))
    return out


def camera_w2c(physics, cam_name: str) -> Tuple[List[List[float]], dict]:
    """world→camera 4×4（团队 M02 用它反求相机世界坐标）。

    MuJoCo 的 `cam_xmat` 是 **world←cam**（列为相机轴在世界系的方向）、`cam_xpos` 是相机世界位置。
    ⇒ `w2c = [[Rᵀ, −Rᵀt], [0,0,0,1]]`，且 `cam_world = −Rᵀt = t`（与轴约定无关，M02 只用这一条）。
    轴约定（相机看 +z 还是 −z）**实测判定**并记进返回的 diag，不靠记忆。
    """
    cid = physics.model.name2id(cam_name, "camera")
    R = np.asarray(physics.data.cam_xmat[cid], dtype=float).reshape(3, 3)
    t = np.asarray(physics.data.cam_xpos[cid], dtype=float)
    tgt = physics.model.name2id(physics.model.id2name(cid, "camera") or "", "camera")
    w2c = np.eye(4)
    w2c[:3, :3] = R.T
    w2c[:3, 3] = -R.T @ t
    tb = physics.named.data.xpos["table"]
    p_cam = R.T @ (np.asarray(tb, dtype=float) - t)
    diag = {"camera": cam_name, "cam_world_xyz": [round(float(x), 6) for x in t],
            "target_body": "table",
            "target_in_cam_xyz": [round(float(x), 6) for x in p_cam],
            "axis_convention": ("camera_looks_along_+z" if p_cam[2] > 0
                                else "camera_looks_along_-z"),
            "axis_convention_evidence": "table（相机 targetbody）在相机系里的 z 分量符号",
            "camera_id": int(cid), "_unused": int(tgt)}
    return [[round(float(v), 8) for v in row] for row in w2c], diag


def quat_wxyz_to_xyzw(q) -> List[float]:
    q = np.asarray(q, dtype=float)
    n = float(np.linalg.norm(q)) or 1.0
    q = q / n
    return [round(float(q[1]), 8), round(float(q[2]), 8), round(float(q[3]), 8),
            round(float(q[0]), 8)]


def rotmat_to_quat_wxyz(R) -> np.ndarray:
    """3×3 旋转矩阵 → MuJoCo 约定的四元数 **wxyz**。

    为什么需要：`JointEnv.grip_pose` 返回 `(xpos, xquat=wxyz)`，而 `KinPlanner.grip_pose`
    返回 `(xpos, xmat.reshape(3,3))` —— **同名不同义**（B2 2026-09-29 23:4x selftest 抓到：
    把 3×3 喂进 `pose7` 直接 `TypeError`）。转换用 mujoco 自己的 `mju_mat2Quat`
    （与产生 `xquat` 的同一套代码），不自手写开方分支。
    """
    import mujoco
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.asarray(R, dtype=float).reshape(9))
    return q


def pose7(xyz, q_wxyz) -> List[float]:
    """团队 schema 的 pose 内序 = `[x,y,z,qx,qy,qz,qw]`（事实源：B2 只读
    `vla_pipeline/rules/qc/_meta.py` 的 pose 键配置，已抄进
    `scripts/b2_make_demo_episodes.py:30`）。MuJoCo 的 `xquat` 是 **wxyz** ⇒ 必须换序。"""
    return [round(float(xyz[0]), 6), round(float(xyz[1]), 6), round(float(xyz[2]), 6)] \
        + quat_wxyz_to_xyzw(q_wxyz)


def quat_angle_deg(qa_xyzw, qb_xyzw) -> float:
    a = np.asarray([qa_xyzw[3], qa_xyzw[0], qa_xyzw[1], qa_xyzw[2]], dtype=float)
    b = np.asarray([qb_xyzw[3], qb_xyzw[0], qb_xyzw[1], qb_xyzw[2]], dtype=float)
    dot = abs(float(np.dot(a, b)))
    dot = min(1.0, max(-1.0, dot))
    return math.degrees(2.0 * math.acos(dot))


# ========================================================================== 采集
def build_subtasks(phases: Sequence[str], direction: str) -> Tuple[List[dict], List[str]]:
    """把相位标签折叠成团队 `subtask`（连续区间、末端 == n−1、每段 `memory` 非空）。"""
    pick = expert.DIRECTION[direction]["pick"]
    receive = expert.DIRECTION[direction]["receive"]
    group_of = {}
    for gi, (labels, _) in enumerate(SUBTASK_GROUPS):
        for lab in labels:
            group_of[lab] = gi
    unknown = sorted({p for p in phases if p not in group_of})
    groups = [group_of.get(p, len(SUBTASK_GROUPS)) for p in phases]
    out: List[dict] = []
    start = 0
    for i in range(1, len(groups) + 1):
        if i == len(groups) or groups[i] != groups[start]:
            gi = groups[start]
            if gi < len(SUBTASK_GROUPS):
                mem = SUBTASK_GROUPS[gi][1].format(pick=pick, receive=receive)
            else:
                mem = "unclassified phase: %s" % phases[start]
            out.append({"range": [start, i - 1], "memory": mem})
            start = i
    return out, unknown


def generate_episode(direction: str, seed: int, dt: float, *, jcfg=None, cfg=None,
                     mutation: Optional[str] = None, contract_state14=None,
                     do_replay_render: bool = True, do_replay_norender: bool = True,
                     image_repeat_render: bool = True) -> dict:
    """一条回合 = **专家 pass**（不渲染）+ **重放 pass**（渲染，出口判据 4）+ **重放 pass**（不渲染，
    用来把"渲染是否扰动物理"这件事单独隔离出来）。三 pass 的判词必须一致。"""
    jcfg = jcfg or expert.JudgeConfig()
    cfg = cfg or expert.ExpertConfig()
    if mutation == "reverse-judge-flipped" and direction in expert.DIRECTION:
        d = expert.DIRECTION[direction]
        d["pick"], d["receive"] = d["receive"], d["pick"]
        d["goal_x_sign"] = -d["goal_x_sign"]
    kw = {"action_noise": 1.0} if mutation == "random-actions" else {}
    t0 = time.perf_counter()
    res = expert.run_episode(direction, seed, dt=dt, cfg=cfg, jcfg=jcfg, **kw)
    t_expert = time.perf_counter() - t0
    actions = np.asarray(res["actions_f64"], dtype=np.float64)
    states_expert = np.asarray(res["states_f64"], dtype=np.float64)
    phases = [f["phase"] for f in res["frames"]]
    box_pose7 = np.asarray(res["box_pose_cmd"], dtype=float)
    settle = min(int(cfg.settle_steps), len(actions))

    def replay(render: bool) -> dict:
        env = expert.JointEnv(dt, box_pose7, render_spec=(RENDER_SPEC if render else ()))
        # 同状态连渲两次的**增量**比对累加器（每 pass 一份；不留图 ⇒ 内存不翻倍）
        img_acc: Dict[str, dict] = {}
        do_img_repeat = bool(render and image_repeat_render)
        judge = expert.SuccessJudge(direction, jcfg, box_spawn=box_pose7)
        rec: Dict[str, list] = {"state14": [], "qvel14": [], "action14": [], "box": [],
                                "grip_pose": {"left": [], "right": []},
                                "tip": {"left": [], "right": []}, "phase": [],
                                "images": {s: [] for s, _, _, _ in RENDER_SPEC} if render else {},
                                "env_reward": [], "box_speed": [], "finger_contacts": [],
                                "finger_spread": {"left": [], "right": []}}
        t0 = time.perf_counter()
        env.reset()
        # 复位态必须在 `env.reset()` **之后**取：dm_control 的 `Environment.reset()` 会调
        # `TransferCubeTask.initialize_episode()`（gym_aloha/tasks/sim.py:108-118），那里才写
        # `qpos[:16] = START_ARM_POSE`、`ctrl = START_ARM_POSE`、`qpos[-7:] = BOX_POSE[0]`。
        # 第一版在 `env.reset()` **之前**取 ⇒ 拿到的是构造态 qpos=0（臂全零、夹爪归一化 −0.466127），
        # 与 A2 契约的 state_raw_14d=[0,−0.96,1.16,0,−0.3,0,0.099848,…] 差 1.16 rad ⇒ G14 判红。
        # 红得对：这条闸就是为了钉死 14 维装配序（RR-B2-09）与"复位态跨线可核验"。
        reset_state = env.state14()
        for i in range(len(actions)):
            a = actions[i].astype(np.float32)
            if i >= settle:
                rec["state14"].append(env.state14())
                rec["qvel14"].append(env.qvel14())
                rec["action14"].append(np.asarray(a, dtype=np.float64))
                rec["box"].append(env.box_pos())
                rec["box_speed"].append(float(np.linalg.norm(env.box_qvel()[:3])))
                rec["phase"].append(phases[i] if i < len(phases) else "unknown")
                rec["env_reward"].append(env.env_reward())
                rec["finger_contacts"].append([list(c) for c in env.contacts_with_box()])
                for sd in ("left", "right"):
                    g = expert.FINGER_GEOMS[sd]
                    rec["finger_spread"][sd].append(float(np.linalg.norm(
                        env.finger_geom_pos(g[0]) - env.finger_geom_pos(g[1]))))
                for s in ("left", "right"):
                    p, q = env.grip_pose(s)
                    rec["grip_pose"][s].append((p, q))
                    rec["tip"][s].append(env.tip_pos(s))
                if render:
                    imgs = env.render()
                    for s, im in imgs.items():
                        rec["images"][s].append(np.asarray(im, dtype=np.uint8))
                    if do_img_repeat:
                        # 第二次渲染**不步物理**（`physics.render` 只读当前 state）⇒ 同状态、同相机、
                        # 同后端，唯一可能不同的就是渲染器自身的非确定性（E 的 n=5 实测对象）。
                        accum_image_repeat(img_acc, imgs, env.render(), mutation)
            env.step(a)
            judge.observe(env, i + 1, phases[i] if i < len(phases) else "unknown")
        wall = time.perf_counter() - t0
        states = (np.asarray(rec["state14"], dtype=np.float64).reshape(-1, 14)
                  if rec["state14"] else np.zeros((0, 14)))
        state_perturbation = None
        if mutation in ("replay-state-perturb-1e-3", MUT_STATE_1LSB) and render and states.size:
            # 变异体（裁定 85.5 的牙②：**篡改任一维状态 1 LSB ⇒ 必须红**）。
            # 保留 §17-6 那颗 1e-3 的粗牙（它证明"看得见的扰动会红"），另加 1 ULP 的细牙
            #（它证明判据真的是**逐位**、而不是某个偷偷带进去的容差）。
            # **只改用于比对的副本**：`rec["state14"]` 与落盘的数据集一个字节都不动
            #（变异体是证明牙会咬，不是产坏数据）。
            states = states.copy()
            if mutation == MUT_STATE_1LSB:
                before = float(states[0, 0])
                states[0, 0] = np.nextafter(before, np.inf)   # float64 的下一个可表示值 = +1 ULP
                how = {"kind": "float64_nextafter_plus_one_ulp",
                       "value_before": before, "value_after": float(states[0, 0]),
                       "abs_delta": abs(float(states[0, 0]) - before),
                       "abs_delta_note": ("量级 ~1e-16（比任何工程容差都小几个数量级）⇒ "
                                          "只有 `np.array_equal` 这种**逐位**判据会红")}
            else:
                states[0, 0] = states[0, 0] + MUT_STATE_EPS
                how = {"kind": "absolute_eps", "eps": MUT_STATE_EPS}
            state_perturbation = {
                "mutation": mutation, "dim": 0, "frame": 0, "how": how,
                "applied_to": "replay pass 的**比对副本**（rec['state14'] 与落盘数据集未动）",
                "purpose": ("证明 G4 的逐位硬判据会咬（红线 tooth_must_be_mutant_proven + "
                            "裁定 85.5 牙②：篡改任一维状态 1 LSB ⇒ 红）"),
                "ruling": "裁定 85.5（§18.5）：硬判据只剩「状态逐位」⇒ 这颗牙是**唯一**判红的牙"}
        live = {}
        ct = env.env.control_timestep
        live["control_timestep_s"] = float(ct() if callable(ct) else ct)
        live["n_sub_steps"] = int(getattr(env.env, "_n_sub_steps", -1))
        live["measured_hz"] = round(1.0 / live["control_timestep_s"], 6) if live[
            "control_timestep_s"] else None
        live["model_timestep_s"] = float(env.physics.timestep())
        out = {"n_frames": len(rec["state14"]), "states": states, "rec": rec,
               "judge": judge.verdict(), "wall_s": round(wall, 3), "live_timing": live,
               "reset_state14": np.asarray(reset_state, dtype=np.float64),
               "image_repeat": (finalize_image_repeat(img_acc) if do_img_repeat else None),
               "state_perturbation": state_perturbation,
               "intrinsics": {}, "w2c_diag": {}}
        for slot, cam, h, w in RENDER_SPEC:
            out["intrinsics"][slot] = camera_intrinsics(env.physics, cam, h, w)
        w2c, diag = camera_w2c(env.physics, TEAM_SLOT_CAMERA["head"])
        out["w2c_head"] = w2c
        out["w2c_diag"] = diag
        # 两个**固定**相机（targetbody=table，table 静止 ⇒ 位姿逐帧不变）的 w2c，
        # 用来把"内参自洽"这件事拿到像素上验（G16）。腕相机随臂动 ⇒ 不做这个检查。
        out["w2c_static"] = {}
        for cam in ("top", "angle"):
            wc, dc = camera_w2c(env.physics, cam)
            out["w2c_static"][cam] = {"w2c": wc, "diag": dc}
        out["intrinsics_projection_check"] = {}
        for slot, cam in (("team_head", "top"), ("pi05_base_0_rgb", "angle")):
            imgs = rec["images"].get(slot) or []
            K = (out["intrinsics"].get(slot) or {}).get("K_3x3")
            if imgs and K and rec["box"]:
                dsign = (1 if out["w2c_static"][cam]["diag"]["axis_convention"]
                         == "camera_looks_along_+z" else -1)
                out["intrinsics_projection_check"][slot] = project_and_verify_intrinsics(
                    imgs[0], out["w2c_static"][cam]["w2c"], K,
                    np.asarray(rec["box"][0], dtype=float), expect_depth_sign=dsign,
                    search_radius=PROJECTION_LOOSE_RADIUS_PX,
                    tight_radius=PROJECTION_TIGHT_RADIUS_PX)
            else:
                out["intrinsics_projection_check"][slot] = {
                    "status": "UNJUDGED",
                    "why": "没有图像或没有 K（intrinsics 判了 UNJUDGED）⇒ 不拿 0 填充"}
        env.close()
        return out

    rp_render = replay(do_replay_render) if (do_replay_render or do_replay_norender) else None
    rp_norender = replay(False) if (do_replay_norender and do_replay_render) else None
    if rp_norender is None and not do_replay_render:
        rp_norender = rp_render

    # ---- 逐位复现（出口判据 4）----
    def cmp_states(a: np.ndarray, b: np.ndarray) -> dict:
        if a.shape != b.shape:
            return {"shape_equal": False, "shape_a": list(a.shape), "shape_b": list(b.shape),
                    "bitwise_equal": False, "max_abs_diff": None}
        eq = bool(np.array_equal(a, b))
        return {"shape_equal": True, "n": int(a.shape[0]), "bitwise_equal": eq,
                "max_abs_diff": float(np.abs(a - b).max()) if a.size else 0.0}

    states_recorded = rp_render["states"] if rp_render is not None else np.zeros((0, 14))
    # **对齐口径（差一帧，第一版就是这里错的）**：
    #   专家 `states_f64[i]` = 执行完动作 i **之后**的状态（`emit` 里先 `env.step(a)` 再记）；
    #   数据集第 j 帧 = 执行动作 (j+settle) **之前**的状态（与同帧图像/动作配对，这才是 BC 的正确口径）。
    # ⇒ 数据集第 j 帧应当逐位等于专家第 (j+settle−1) 个 post-step 状态。
    # B2 2026-09-30 实测：用 `[settle:]` 比 ⇒ max|Δ|=2.78 rad（整条差一帧，G4 判红）；
    # 用 `[settle−1:]` 比 ⇒ **逐位相同**（6 集双向全 True）。所以修的是比较口径，不是数据。
    n_rec = int(states_recorded.shape[0])
    if settle >= 1 and states_expert.size:
        # 切到**同长度**再比：专家有 286 个 post-step 状态，数据集只存沉降后的 274 帧，
        # 直接 `states_expert[settle−1:]` 会多出一行 ⇒ `shape_equal=False`（第一版就栽在这里）。
        states_expert_rec = states_expert[settle - 1: settle - 1 + n_rec]
        align_note = "recorded[j] == expert_post_step[j+settle−1]（专家记 post-step、数据集记 pre-step）"
    elif states_expert.size:
        states_expert_rec = states_expert[:n_rec]
        align_note = "settle==0 ⇒ 数据集第 0 帧无对应的专家 post-step 状态，只能从第 1 帧起比"
    else:
        states_expert_rec = states_expert
        align_note = "专家没有 post-step 状态可参照"
    replay_cmp = {
        "recorded_vs_expert": cmp_states(states_recorded, states_expert_rec),
        "norender_vs_expert": (cmp_states(rp_norender["states"], states_expert_rec)
                               if rp_norender is not None else None),
        "recorded_vs_norender": (cmp_states(states_recorded, rp_norender["states"])
                                 if rp_norender is not None else None),
        "verdict_expert": res["judge"]["verdict"],
        "verdict_replay_render": rp_render["judge"]["verdict"] if rp_render else None,
        "verdict_replay_norender": rp_norender["judge"]["verdict"] if rp_norender else None,
        "verdicts_all_equal": bool(rp_render and rp_norender and
                                   res["judge"]["verdict"] == rp_render["judge"]["verdict"] ==
                                   rp_norender["judge"]["verdict"]),
        "terminal_box_expert": res["judge"]["evidence"]["final_box_xyz"],
        "terminal_box_replay": (rp_render["judge"]["evidence"]["final_box_xyz"]
                                if rp_render else None),
        "n_steps_expert": res["n_steps"],
        "n_frames_replay_recorded": int(states_recorded.shape[0]),
        "settle_steps_dropped": settle,
        "actions_replayed_are_the_executed_float32": True,
        "state_alignment_convention": align_note,
        "state_alignment_offset_expert_post_step": (settle - 1) if settle >= 1 else 0,
        "shape_accounting": {"n_expert_post_step_states": int(states_expert.shape[0]),
                             "n_recorded_frames": n_rec, "settle_dropped": settle,
                             "identity_expected": "n_expert_post_step_states − settle == n_recorded_frames",
                             "identity_holds": bool(int(states_expert.shape[0]) - settle == n_rec)},
        "image_repeat_render": (rp_render or {}).get("image_repeat"),
        "state_perturbation": (rp_render or {}).get("state_perturbation"),
        "note": ("重放喂的是**下发过的那串 float32**（`actions_f64`，非 round(·,6) 的报告副本）；"
                 "`norender_vs_expert` 隔离『动作记录是否无损』，`recorded_vs_norender` 隔离"
                 "『渲染是否扰动物理』——两者分开报，不合并成一个模糊的『重放一致』"),
    }
    return {"direction": direction, "seed": seed, "dt": dt, "mutation": mutation,
            "expert": res, "replay_render": rp_render, "replay_norender": rp_norender,
            "replay_cmp": replay_cmp, "actions": actions, "phases": phases,
            "box_pose7": box_pose7, "settle": settle, "t_expert_s": round(t_expert, 3),
            "contract_state14": contract_state14}


# ========================================================================== 出口 1：团队形态
def write_team_episode(ep_root: Path, rec: dict, task_text: str, intrinsics_top: dict,
                       w2c_head, w2c_diag: dict, ffmpeg: str, ffprobe: str,
                       provenance_extra: dict, fps_str: str = FPS_RATIONAL) -> dict:
    rp = rec["replay_render"] or rec["replay_norender"]
    if rp is None:
        raise RuntimeError("write_team_episode 需要至少一个重放 pass（render 或 norender）")
    r = rp["rec"]
    n = rp["n_frames"]
    actions = np.asarray(r["action14"], dtype=np.float64).reshape(-1, 14)
    states = np.asarray(r["state14"], dtype=np.float64).reshape(-1, 14)
    qvels = np.asarray(r["qvel14"], dtype=np.float64).reshape(-1, 14)
    direction = rec["direction"]
    ep_id = "episode_%s" % uuid.uuid5(uuid.NAMESPACE_OID, "b2-s1|%s|%d|%s" % (
        direction, rec["seed"], rec["dt"]))
    ep = ep_root / TASK_DIR[direction] / ep_id
    ep.mkdir(parents=True, exist_ok=True)

    planner = expert.KinPlanner(joint_xml_path())
    act_pose = {"left": [], "right": []}
    q23 = np.zeros(23)
    for i in range(n):
        a = actions[i]
        q23[:] = 0.0
        q23[0:6] = a[0:6]
        q23[6] = a[6]
        q23[7] = -a[6]
        q23[8:14] = a[7:13]
        q23[14] = a[13]
        q23[15] = -a[13]
        planner.sync(q23)
        for side in ("left", "right"):
            p, R = planner.grip_pose(side)          # planner 给的是旋转矩阵，不是四元数
            act_pose[side].append(pose7(p, rotmat_to_quat_wxyz(R)))
    st_pose = {"left": [pose7(p, q) for p, q in r["grip_pose"]["left"]],
               "right": [pose7(p, q) for p, q in r["grip_pose"]["right"]]}

    is_move = [0] * n
    for i in range(n):
        if i == 0:
            # 第 0 帧没有"上一帧"可比 ⇒ 按语义定：沉降已完成、抓取相位正要出发 ⇒ 记 1（自述进 manifest）
            is_move[i] = 1
            continue
        dj = np.abs(actions[i][[0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12]] -
                    actions[i - 1][[0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12]])
        dg = abs(float(actions[i][6] - actions[i - 1][6])) + abs(float(actions[i][13] -
                                                                       actions[i - 1][13]))
        is_move[i] = 1 if (float(dj.max()) > IS_MOVE_JOINT_EPS or dg > IS_MOVE_GRIP_EPS) else 0

    # frame_validity：**真定义**（不是全 True 填充）——该帧若出现 flick / 方块出工作区 ⇒ invalid
    jcfg = rec["expert"]["judge"]
    flick_thr = 1.5
    valid, msgs = [], []
    for i in range(n):
        m = []
        if r["box_speed"][i] > flick_thr:
            m.append("flick: box_speed=%.4f m/s > %.1f" % (r["box_speed"][i], flick_thr))
        bx = r["box"][i]
        if abs(float(bx[0])) > 0.45 or abs(float(bx[1]) - 0.6) > 0.45 or float(bx[2]) < -0.05:
            m.append("box_out_of_workspace: xyz=%s" % [round(float(v), 4) for v in bx])
        valid.append(not m)
        msgs.append(m)

    subtasks, unknown_phases = build_subtasks(r["phase"], direction)
    meta = {
        "task_info": task_text,
        "subtask": subtasks,
        "file_path": str(ep),
        "intrinsics": intrinsics_top["K_3x3"],
        "w2c_extrinsic": [w2c_head] * n,
        "is_move": is_move,
        "frame_validity": {"is_valid": valid, "message": msgs},
        "action": {}, "state": {},
    }
    for side in ("left", "right"):
        ai = expert.ARM_ACT_SLICE[side]
        si = slice(0, 6) if side == "left" else slice(7, 13)
        gi = 6 if side == "left" else 13
        meta["action"]["%s_arm" % side] = {
            "joint": [[round(float(v), 6) for v in actions[i][ai]] for i in range(n)],
            "pose": act_pose[side],
            "velocity": [[round(float(v), 6) for v in qvels[i][si]] for i in range(n)]}
        meta["action"]["%s_gripper" % side] = {
            "joint": [[round(float(actions[i][gi]), 6)] for i in range(n)]}
        meta["state"]["%s_arm" % side] = {
            "joint": [[round(float(v), 6) for v in states[i][si]] for i in range(n)],
            "pose": st_pose[side],
            "velocity": [[round(float(v), 6) for v in qvels[i][si]] for i in range(n)]}
        meta["state"]["%s_gripper" % side] = {
            "joint": [[round(float(states[i][gi]), 6)] for i in range(n)]}
        meta["%s_hand" % side] = {"joint": [], "pose": []}   # ABC130k 真实形态：手可空
    meta["b2_provenance"] = {
        "data_kind": DATA_KIND,
        "dataset_kind": DATASET_KIND,
        "not_a_capability_claim": True,
        "policy_executed": False,
        "trajectory_kind": "sim_scripted_expert_kinematic_ik_plan_then_replay",
        "direction": direction,
        "direction_label": DIRECTION_LABEL[direction],
        "generator": "scripts/b2_s1_generate_dataset.py",
        "expert_module": "scripts/b2_s1_scripted_expert.py",
        "seed": rec["seed"], "dt": rec["dt"],
        "control_hz": MAINLINE_HZ,
        "box_settle_steps": BOX_SETTLE_STEPS, "box_z_seeded": BOX_Z_SEEDED,
        "box_z_at_rest": BOX_Z_AT_REST,
        "box_spawn_xyz": rec["expert"]["box_spawn_xyz"],
        "box_rest_after_settle_xyz": rec["expert"]["box_rest_after_settle_xyz"],
        "grip_cmd_open": GRIP_CMD_OPEN, "grip_cmd_close": GRIP_CMD_CLOSE,
        "grip_cmd_open_close_threshold": GRIP_CMD_THRESHOLD,
        "grip_calibration_table_cmd_to_spread_m": GRIP_CALIBRATION_TABLE,
        "tip_rel_gripframe": TIP_REL_GRIPFRAME,
        "intrinsics_per_slot": {s: rp["intrinsics"][s] for s, _, _, _ in RENDER_SPEC},
        "intrinsics_note": ("团队 schema 的 `intrinsics` 是**单个 3×3**，而三槽是三个不同相机"
                            "（top fovy=78°、两腕 fovy=20°）⇒ 单矩阵无法与三视频同时自洽；"
                            "此处顶层填 **head(top)@480×640** 的真值，逐槽真值全记在本字段。"
                            "ABC-130k 实测有 25 条 intrinsics 与自身分辨率不自洽（同族问题）。"),
        "w2c_extrinsic_camera": TEAM_SLOT_CAMERA["head"],
        "w2c_extrinsic_diag": w2c_diag,
        "is_move_definition": ("1 ⇔ max|Δ 命令臂关节| > %g rad 或 Σ|Δ 命令夹爪| > %g；"
                               "第 0 帧记 1（沉降已完成、抓取相位即将出发）。"
                               "**不沿用 ABC-130k 的全 0**（B2 dataset_card 的 b2_policy_for_own_data））"
                               % (IS_MOVE_JOINT_EPS, IS_MOVE_GRIP_EPS)),
        "frame_validity_definition": "flick(方块速度>1.5 m/s) 或 方块出工作区 ⇒ 该帧 invalid",
        "n_frames": n, "fps_rational": FPS_RATIONAL, "fps_float": MAINLINE_HZ,
        "verdict_geometric_truth": rec["replay_cmp"]["verdict_replay_render"],
        "failure_class": (rec["replay_render"] or rec["replay_norender"])["judge"].get(
            "failure_class"),
        "env_reward4_terminal": (rec["replay_render"] or rec["replay_norender"])["judge"][
            "evidence"].get("env_reward4_terminal"),
        "unknown_phases": unknown_phases,
        "mutation": rec["mutation"],
    }
    meta["b2_provenance"].update(provenance_extra)
    mp = ep / METADATA_NAME
    mp.write_text(json.dumps(meta, ensure_ascii=False) + "\n", encoding="utf-8")

    vinfo = {}
    for slot, cam, h, w in RENDER_SPEC:
        if slot not in SLOT_TO_TEAM:
            continue
        team_slot = SLOT_TO_TEAM[slot]
        frames = r["images"][slot]
        vp = ep / VIDEO_SLOTS[team_slot]
        cmd = write_video(vp, [np.asarray(f, dtype=np.uint8).tobytes() for f in frames],
                          w, h, fps_str, ffmpeg)
        pr = probe_frames(vp, ffprobe) or {}
        vinfo[team_slot] = {"file": VIDEO_SLOTS[team_slot], "camera": cam, "h": h, "w": w,
                            "bytes": vp.stat().st_size, "n_input_frames": len(frames),
                            "nb_read_frames": pr.get("nb_read_frames"), "fps": pr.get("fps"),
                            "fps_rational_requested": fps_str,
                            "ffmpeg_cmd_head": " ".join(cmd[:8]) + " ..."}
    return {"ep_id": ep_id, "path": str(ep), "n_frames": n, "videos": vinfo,
            "metadata_bytes": mp.stat().st_size, "metadata_sha256": sha256(mp),
            "subtasks": subtasks, "unknown_phases": unknown_phases,
            "is_move_n_true": int(sum(is_move)), "frame_validity_n_invalid": int(
                sum(1 for v in valid if not v))}


# ========================================================================== 出口 2：LeRobot（π₀.₅）
STATE_NAMES = ["left_arm_j0", "left_arm_j1", "left_arm_j2", "left_arm_j3", "left_arm_j4",
               "left_arm_j5", "left_gripper_normalized", "right_arm_j0", "right_arm_j1",
               "right_arm_j2", "right_arm_j3", "right_arm_j4", "right_arm_j5",
               "right_gripper_normalized"]


def lerobot_features(cam_map: Dict[str, str]) -> dict:
    """π₀.₅ 数据集的 features。**只放策略真会消费的键**（state + action + 3 图像）：
    裁定 68 的 obs 键覆盖闸会点名"存入但被静默丢弃的键"，所以诊断量一律走 sidecar，不进数据集。"""
    feats = {"observation.state": {"dtype": "float32", "shape": (14,), "names": STATE_NAMES},
             "action": {"dtype": "float32", "shape": (14,), "names": STATE_NAMES}}
    for key, cam in cam_map.items():
        feats[key] = {"dtype": "image", "shape": (PI05_IMAGE_HW, PI05_IMAGE_HW, 3),
                      "names": ["height", "width", "channel"],
                      "info": {"image.codec": "png", "storage": "inline_parquet",
                               "camera_id_in_mujoco_model": cam,
                               "render_call": "physics.render(height=224, width=224, camera_id=%r)"
                                              % cam,
                               "source": "mujoco 3.8.1 / gym_aloha 0.1.4 关节模型原生渲染",
                               "video.fps": MAINLINE_HZ,
                               "video.height": PI05_IMAGE_HW, "video.width": PI05_IMAGE_HW,
                               "video.is_depth_map": False, "has_audio": False}}
    return feats


def create_lerobot(root: Path, cam_map: Dict[str, str]):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    return LeRobotDataset.create(
        repo_id=LEROBOT_REPO_ID, fps=MAINLINE_HZ, features=lerobot_features(cam_map),
        root=str(root), robot_type="aloha_bimanual_14d(gym_aloha vx300s dual-arm)",
        use_videos=True, image_writer_processes=0, image_writer_threads=0, vcodec="h264")


def add_episode_to_lerobot(ds, rec: dict, cam_map: Dict[str, str], task_text: str,
                           frame_offset: int = 0, roundtrip_sample: int = 3) -> dict:
    rp = rec["replay_render"] or rec["replay_norender"]
    r = rp["rec"]
    n = rp["n_frames"]
    states = np.asarray(r["state14"], dtype=np.float64).reshape(-1, 14)
    actions = np.asarray(r["action14"], dtype=np.float64).reshape(-1, 14)
    slot_by_key = {v: k for k, v in SLOT_TO_PI05_KEY.items()}
    # 无损往返只抽样几帧（全帧留在内存里 = 300×3×150 KB/集，不值得）；抽样索引写进产物。
    keep = sorted({0, n // 2, n - 1})[:roundtrip_sample] if n else []
    pix: Dict[str, List[Tuple[int, np.ndarray]]] = {}
    for i in range(n):
        frame = {"observation.state": states[i].astype(np.float32),
                 "action": actions[i].astype(np.float32), "task": task_text}
        for key in cam_map:
            slot = slot_by_key[key]
            img = np.asarray(r["images"][slot][i], dtype=np.uint8)
            frame[key] = img
            if i in keep:
                pix.setdefault(key, []).append((frame_offset + i, img))
        ds.add_frame(frame)
    ds.save_episode()
    return {"n_frames": n, "roundtrip_sampled_global_indices": [frame_offset + i for i in keep],
            "pixels_kept_for_roundtrip": pix}


def verify_lerobot(root: Path, expect_eps: int, expect_frames: int,
                   roundtrip: Dict[str, List[Tuple[int, np.ndarray]]]) -> dict:
    """读回自己写的数据集并逐字段核（"lerobot 可消费"这句话必须有牙，不能只看写成功）。"""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    out = {"root": str(root)}
    ds = LeRobotDataset(repo_id=LEROBOT_REPO_ID, root=str(root))
    out["num_episodes"] = int(ds.num_episodes)
    out["num_frames"] = int(ds.num_frames)
    out["fps"] = ds.fps
    out["fps_type"] = type(ds.fps).__name__
    out["fps_matches_control_hz"] = bool(abs(float(ds.fps) - MAINLINE_HZ) < 1e-9)
    out["feature_keys"] = sorted(k for k in ds.features)
    it0 = ds[0]
    out["item_keys"] = sorted(str(k) for k in it0.keys())
    out["state_shape"] = list(tuple(it0["observation.state"].shape))
    out["action_shape"] = list(tuple(it0["action"].shape))
    img_keys = [k for k in out["feature_keys"] if k.startswith("observation.images.")]
    out["image_keys"] = img_keys
    out["image_shapes"] = {k: list(tuple(ds[0][k].shape)) for k in img_keys}
    out["image_dtypes"] = {k: str(ds[0][k].dtype) for k in img_keys}
    out["image_range_min_max"] = {k: [round(float(ds[0][k].min()), 6),
                                      round(float(ds[0][k].max()), 6)] for k in img_keys}
    # 时间戳 = **集内** frame_index / 29.4118（**不是** /30）：这是"频率口径进了数据"的验收形式。
    # 第一版拿**全局** i 去比 ⇒ 第二集起每帧都差一整集时长（实测 max_abs_err=8.772 s = 258/29.4118），
    # 而 lerobot v3 的 `timestamp` 是**每集从 0 重新起算**的（`frame_index` 集内、`index` 全局）。
    ts_err, idx_bad, ep_seen = [], [], {}
    n_chk = min(expect_frames, int(ds.num_frames))
    for i in range(n_chk):
        it = ds[i]
        fi = int(it["frame_index"])
        gi = int(it["index"])
        ei = int(it["episode_index"])
        ts_err.append(abs(float(it["timestamp"]) - fi / MAINLINE_HZ))
        if gi != i:
            idx_bad.append({"global_i": i, "item_index": gi})
        ep_seen.setdefault(ei, []).append(fi)
    per_ep_ok = {ei: (v == list(range(len(v)))) for ei, v in ep_seen.items()}
    out["timestamp_check"] = {
        "n_checked": len(ts_err), "max_abs_err_s": max(ts_err) if ts_err else None,
        "tolerance_s": 1e-6,
        "expected_formula": "timestamp == 集内 frame_index / %.10f（每集从 0 重新起算）" % MAINLINE_HZ,
        "global_index_matches_position": (not idx_bad),
        "global_index_mismatches": idx_bad[:5],
        "n_episodes_seen": len(ep_seen),
        "frame_index_contiguous_from_0_per_episode": per_ep_ok,
        "per_episode_length": {ei: len(v) for ei, v in ep_seen.items()},
        "ok": bool(ts_err and max(ts_err) < 1e-6 and not idx_bad and all(per_ep_ok.values()))}
    # 无损往返：PNG 内嵌 ⇒ 解码回来的 uint8 必须与渲染原图**逐字节相同**
    rt = {}
    for key, samples in roundtrip.items():
        diffs = []
        for idx, orig in samples:
            got = ds[idx][key]
            back = (got.permute(1, 2, 0).numpy() * 255.0).round().astype(np.uint8) \
                if tuple(got.shape)[0] == 3 else (got.numpy() * 255.0).round().astype(np.uint8)
            diffs.append(int(np.abs(back.astype(int) - orig.astype(int)).max()))
        rt[key] = {"n_samples": len(samples), "max_abs_uint8_diff": max(diffs) if diffs else None,
                   "bitwise_equal": bool(diffs and max(diffs) == 0)}
    out["roundtrip_lossless"] = rt
    stats_p = root / "meta" / "stats.json"
    out["stats_json"] = {"exists": stats_p.exists(),
                         "keys": (sorted(json.loads(stats_p.read_text()).keys())
                                  if stats_p.exists() else None),
                         "note": ("这是 **lerobot 自己**算的 min/max/mean/std，"
                                  "**不是**主线 normalizer stats（QUANTILES 归 C2 的 T-C2-1，"
                                  "裁定 52/69：stats 源 = 本数据集，C2 自己算）")}
    info_p = root / "meta" / "info.json"
    out["info_json"] = json.loads(info_p.read_text()) if info_p.exists() else None
    out["episodes_expected"] = expect_eps
    out["frames_expected"] = expect_frames
    out["counts_match"] = bool(out["num_episodes"] == expect_eps and
                               out["num_frames"] == expect_frames)
    return out


# ========================================================================== 逐集度量
def episode_metrics(rec: dict, team: Optional[dict], contract: dict) -> dict:
    rp = rec["replay_render"] or rec["replay_norender"]
    r = rp["rec"]
    n = rp["n_frames"]
    actions = np.asarray(r["action14"], dtype=np.float64).reshape(-1, 14)
    states = np.asarray(r["state14"], dtype=np.float64).reshape(-1, 14)
    boxes = np.asarray(r["box"], dtype=np.float64).reshape(-1, 3)
    m: Dict[str, Any] = {"direction": rec["direction"], "seed": rec["seed"],
                         "n_frames": n, "n_actions": int(actions.shape[0]),
                         "state_dim": int(states.shape[1]) if states.size else None,
                         "action_dim": int(actions.shape[1]) if actions.size else None}
    m["verdict_expert"] = rec["expert"]["judge"]["verdict"]
    m["verdict_replay_render"] = rp["judge"]["verdict"]
    m["verdict_replay_norender"] = (rec["replay_norender"]["judge"]["verdict"]
                                    if rec["replay_norender"] else None)
    m["failure_class"] = rp["judge"].get("failure_class")
    ev = rp["judge"].get("evidence") or {}
    m["evidence"] = {k: ev.get(k) for k in ("max_held_run_steps", "final_box_xyz",
                                             "env_reward4_seen", "max_box_speed_mps",
                                             "max_box_speed_phase", "max_picker_held_run_steps",
                                             "box_horizontal_displacement_m",
                                             "on_goal_side_x_sign_diagnostic_only",
                                             "box_spawn_xyz")}
    m["env_reward_terminal"] = int(r["env_reward"][-1]) if r["env_reward"] else None
    m["env_reward4_terminal"] = bool(m["env_reward_terminal"] == 4)
    m["box_z_frame0"] = round(float(boxes[0][2]), 6) if boxes.size else None
    m["box_xyz_frame0"] = [round(float(v), 6) for v in boxes[0]] if boxes.size else None
    m["bitwise"] = rec["replay_cmp"]
    m["image_repeat_render"] = rec["replay_cmp"].get("image_repeat_render")
    m["replay_state_perturbation"] = rec["replay_cmp"].get("state_perturbation")
    # 图像统计
    img_stats = {}
    for slot, cam, h, w in RENDER_SPEC:
        arrs = r["images"].get(slot) or []
        if not arrs:
            img_stats[slot] = {"n_frames": 0}
            continue
        a0 = np.asarray(arrs[0])
        means = [float(np.asarray(x).mean()) for x in arrs[:: max(1, len(arrs) // 20)]]
        stds = [float(np.asarray(x).std()) for x in arrs[:: max(1, len(arrs) // 20)]]
        img_stats[slot] = {"camera": cam, "h": int(a0.shape[0]), "w": int(a0.shape[1]),
                           "channels": int(a0.shape[2]) if a0.ndim == 3 else None,
                           "dtype": str(a0.dtype), "n_frames": len(arrs),
                           "mean_of_frame0": round(float(a0.mean()), 4),
                           "std_of_frame0": round(float(a0.std()), 4),
                           "mean_range_sampled": [round(min(means), 4), round(max(means), 4)],
                           "std_min_sampled": round(min(stds), 4),
                           "frame_to_frame_max_abs_diff": int(max(
                               int(np.abs(np.asarray(arrs[i]).astype(int) -
                                          np.asarray(arrs[i - 1]).astype(int)).max())
                               for i in range(1, min(len(arrs), 60)))) if len(arrs) > 1 else 0}
    m["image_stats"] = img_stats
    # 夹爪标定（实测 spread，与 probe4 的表同定义：两指 geom 距离）
    # **按侧分开**统计（第一版用"任一侧 cmd 到端"的帧集去取某一侧的极值，口径是混的）。
    sp = r["finger_spread"]
    qv = np.asarray(r["qvel14"], dtype=np.float64).reshape(-1, 14) if n else np.zeros((0, 14))
    bg = box_geom_measured()
    box_w = bg.get("width_m")
    exp_close = (round(GRIP_CALIBRATION_TABLE["0.0"] + box_w, 6)
                 if (box_w is not None and bg.get("status") == "measured_from_model") else None)
    grip: Dict[str, Any] = {
        "cmd_min": round(float(actions[:, [6, 13]].min()), 6) if n else None,
        "cmd_max": round(float(actions[:, [6, 13]].max()), 6) if n else None,
        "box_geom": bg,
        "expected_spread_close_holding_box_m": exp_close,
        "expected_spread_open_m": GRIP_CALIBRATION_TABLE["1.0"],
        "tolerances_m": {"open_quasistatic": GRIP_TOL_OPEN_M, "close_holding_box": GRIP_TOL_CLOSE_M,
                         "dynamic_overshoot_upper_bound": GRIP_DYNAMIC_MAX_M},
        "quiescent_criterion": ("该侧 6 个臂关节 |qvel| 全 < %s rad/s（否则是拿动态过冲比静态标定表）"
                                % QUIESCENT_QVEL_RAD_S),
        "probe4_reference": {"open_1p0": 0.08412, "close_0p0": 0.01833,
                             "measured_in": "**复位构型**（START_ARM_POSE）",
                             "definition": "|finger_geom_1 − finger_geom_2|（probe4:150 同定义）"},
        "per_side": {}}
    bin_medians: Dict[str, List[float]] = {k: [] for k in GRIP_CALIBRATION_TABLE}
    for side in ("left", "right"):
        ci = 6 if side == "left" else 13
        arm_sl = slice(0, 6) if side == "left" else slice(7, 13)
        cmd = actions[:, ci]
        spd = np.asarray(sp[side], dtype=float)
        oidx = [i for i in range(n) if cmd[i] >= 0.999]
        cidx = [i for i in range(n) if cmd[i] <= 0.001]
        qs = [i for i in oidx if n and np.abs(qv[i][arm_sl]).max() < QUIESCENT_QVEL_RAD_S]
        row = {
            "n_frames_cmd_open": len(oidx), "n_frames_cmd_close": len(cidx),
            "n_frames_open_quasistatic": len(qs),
            "spread_open_dynamic_min": round(float(spd[oidx].min()), 5) if oidx else None,
            "spread_open_dynamic_max": round(float(spd[oidx].max()), 5) if oidx else None,
            "spread_open_quasistatic_median": (round(float(np.median(spd[qs])), 5)
                                               if len(qs) >= QUIESCENT_MIN_FRAMES else None),
            "spread_close_median": round(float(np.median(spd[cidx])), 5) if cidx else None,
            "spread_close_min": round(float(spd[cidx].min()), 5) if cidx else None,
            "spread_close_max": round(float(spd[cidx].max()), 5) if cidx else None,
            "open_status": ("measured" if len(qs) >= QUIESCENT_MIN_FRAMES else "UNJUDGED"),
            "close_status": ("measured" if cidx else "UNJUDGED"),
            "open_why": (None if len(qs) >= QUIESCENT_MIN_FRAMES else
                         "cmd=1.0 的准静态帧只有 %d 个（< %d）⇒ 不拿动态过冲当标定值，判 UNJUDGED"
                         % (len(qs), QUIESCENT_MIN_FRAMES)),
            "close_why": (None if cidx else "本集该侧从未 cmd=0.0 ⇒ 无从判夹持指距"),
        }
        grip["per_side"][side] = row
        for b in GRIP_CALIBRATION_TABLE:
            bt = float(b)
            for i in range(n):
                if abs(cmd[i] - bt) <= 0.02 and np.abs(qv[i][arm_sl]).max() < QUIESCENT_QVEL_RAD_S:
                    bin_medians[b].append(float(spd[i]))
    grip["calibration_bins_quasistatic"] = {
        b: {"n": len(v), "median_spread_m": (round(float(np.median(v)), 5) if v else None),
            "probe4_table_m": GRIP_CALIBRATION_TABLE[b],
            "abs_diff_m": (round(abs(float(np.median(v)) - GRIP_CALIBRATION_TABLE[b]), 5)
                           if v else None)}
        for b, v in bin_medians.items()}
    m["gripper"] = grip
    # 团队规则会读的量（自己先算，别等 QC 判红才知道）
    if team:
        meta = json.loads((Path(team["path"]) / METADATA_NAME).read_text())
        poses = {}
        for blk in ("action", "state"):
            for side in ("left", "right"):
                poses["%s.%s_arm.pose" % (blk, side)] = meta[blk]["%s_arm" % side]["pose"]
        qn2 = []
        dpos, dang = [], []
        for k, seq in poses.items():
            for i, p in enumerate(seq):
                q = p[3:]
                qn2.append(sum(v * v for v in q))
                if i:
                    dpos.append(math.dist(p[:3], seq[i - 1][:3]))
                    dang.append(quat_angle_deg(p[3:], seq[i - 1][3:]))
        w2c = np.asarray(meta["w2c_extrinsic"][0], dtype=float)
        cam_world = -w2c[:3, :3].T @ w2c[:3, 3]
        wrist_d, ee_d = [], []
        for i in range(n):
            pl = poses["action.left_arm.pose"][i][:3]
            pr = poses["action.right_arm.pose"][i][:3]
            wrist_d.append(max(math.dist(pl, cam_world.tolist()), math.dist(pr, cam_world.tolist())))
            ee_d.append(math.dist(pl, pr))
        # I / C01：连续"两夹爪都开(>0.6) 且 臂位移 < 0.05 m"的时长
        still_run, still_best = 0, 0
        for i in range(1, n):
            both_open = (meta["action"]["left_gripper"]["joint"][i][0] > 0.6 and
                         meta["action"]["right_gripper"]["joint"][i][0] > 0.6)
            moved = max(math.dist(poses["action.left_arm.pose"][i][:3],
                                  poses["action.left_arm.pose"][i - 1][:3]),
                        math.dist(poses["action.right_arm.pose"][i][:3],
                                  poses["action.right_arm.pose"][i - 1][:3]))
            if both_open and moved < 0.05:
                still_run += 1
                still_best = max(still_best, still_run)
            else:
                still_run = 0
        m["team_rule_inputs"] = {
            "quat_norm2_min": round(min(qn2), 6), "quat_norm2_max": round(max(qn2), 6),
            "c02_band": [0.98, 1.02],
            "max_frame_pose_delta_m": round(max(dpos), 6), "max_frame_pose_delta_deg":
                round(max(dang), 4),
            "c03_thresholds": {"position_m": POSE_JUMP_POS_M, "angle_deg": POSE_JUMP_DEG},
            "max_wrist_to_head_cam_m": round(max(wrist_d), 4),
            "m02_threshold_m": WRIST_CAM_MAX_DIST_M,
            "cam_world_from_w2c": [round(float(v), 4) for v in cam_world],
            "max_left_right_ee_dist_m": round(max(ee_d), 4),
            "e_threshold_m": EUCLIDEAN_THRESHOLD_M,
            "longest_all_open_still_run_frames": still_best,
            "longest_all_open_still_run_s": round(still_best * rec["dt"], 3),
            "i_threshold_s": STILL_SECONDS,
            "is_move_n_true": team["is_move_n_true"], "is_move_n_frames": n,
            "frame_validity_n_invalid": team["frame_validity_n_invalid"],
            "subtask_ranges": [t["range"] for t in team["subtasks"]],
            "subtask_contiguous": all(team["subtasks"][i]["range"][1] + 1 ==
                                      team["subtasks"][i + 1]["range"][0]
                                      for i in range(len(team["subtasks"]) - 1)),
            "subtask_last_end": team["subtasks"][-1]["range"][1] if team["subtasks"] else None,
            "dimension_config_check": _dim_check(meta, n),
            "video_nb_read_frames": {k: v.get("nb_read_frames") for k, v in team["videos"].items()},
            "video_container_fps": {k: v.get("fps") for k, v in team["videos"].items()},
        }
    rs = rp["reset_state14"]
    cref = contract.get("state_raw_14d")
    up = upstream_reset_state14()
    upv = up.get("state14_reconstructed")
    rs6 = [round(float(v), 6) for v in rs]
    rc = {"reset_value_full_precision": [float(v) for v in rs],
          "reset_value_round6": rs6,
          "contract_value": cref,
          "contract_rounding_decimals": 6,
          "upstream_reconstruction": up}
    if upv is not None:
        u = np.asarray(upv, dtype=np.float64)
        rc["vs_upstream_bitwise_equal"] = bool(np.array_equal(rs, u))
        rc["vs_upstream_max_abs_diff"] = float(np.abs(rs - u).max())
    else:
        rc["vs_upstream_bitwise_equal"] = None
        rc["vs_upstream_max_abs_diff"] = None
    if cref is not None:
        c6 = [round(float(v), 6) for v in np.asarray(cref, dtype=float)]
        rc["vs_contract_round6_bitwise_equal"] = bool(rs6 == c6)
        rc["vs_contract_max_abs_diff"] = float(
            np.abs(rs - np.asarray(cref, dtype=float)).max())
        rc["vs_contract_diff_explained_by_its_6dp_rounding"] = bool(
            rc["vs_contract_max_abs_diff"] <= 5e-7)
    else:
        rc["vs_contract_round6_bitwise_equal"] = None
        rc["status"] = "UNJUDGED"
        rc["why"] = "契约里没有 state_raw_14d"
    m["reset_state_vs_a2_contract"] = rc
    m["live_timing"] = rp["live_timing"]
    return m


def _dim_check(meta: dict, n: int) -> dict:
    """17 个 DIMENSION_CONFIG 键：键在不在 + 每帧维度对不对（事实源 `rules/qc/_meta.py`）。"""
    bad = []
    for key, dim in DIMENSION_CONFIG:
        if key == "is_move":
            v = meta.get("is_move")
            if not isinstance(v, list) or len(v) != n:
                bad.append({"key": key, "problem": "len=%s != n=%s" % (
                    len(v) if isinstance(v, list) else None, n)})
            continue
        cur = meta
        for part in key.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if not isinstance(cur, list) or len(cur) != n:
            bad.append({"key": key, "problem": "missing or len!=n",
                        "len": (len(cur) if isinstance(cur, list) else None)})
            continue
        widths = {len(x) if isinstance(x, list) else None for x in cur}
        if widths != {dim}:
            bad.append({"key": key, "problem": "per-frame width %s != %s" % (sorted(
                str(w) for w in widths), dim)})
    return {"n_keys": len(DIMENSION_CONFIG), "n_bad": len(bad), "bad": bad,
            "all_dims_ok": not bad}


# ========================================================================== 闸（S1 出口判据 §13.8）
MUTATION_EXPECT_RED = {
    "none": [],
    "dt-back-to-50hz": ["G3_frequency_dt_substeps_shim_container_fps"],
    "reverse-judge-flipped": ["G1_success_geometric_truth_vs_reward4",
                              "G5_reverse_criteria_self_built",
                              "G7_expert_gate_recorded_all_success"],
    "random-actions": ["G1_success_geometric_truth_vs_reward4",
                       "G7_expert_gate_recorded_all_success"],
    # ---- replay 闸的三颗牙（裁定 85.5 / §18.5：① 绿证人 ② 状态 1 LSB 必红 ③ 只改像素必**仍绿**）----
    # 红线 `tooth_must_be_mutant_proven`：只写 `red_when` 文案不算牙。
    "replay-state-perturb-1e-3": ["G4_replay_reproduces_bitwise"],   # 粗牙（§17-6 指定的 1e-3）
    "replay-state-1lsb": ["G4_replay_reproduces_bitwise"],           # 细牙（85.5 牙②：1 ULP 也必须红）
    # 85.5 牙③：只篡改像素、状态不动 ⇒ **一条都不许红**（`must_stay_green`）
    "replay-image-pixel-only": [],
    "replay-image-over-tolerance": [],   # 旧名（§17-6 时代它期望 G4b 红）⇒ 保留为别名，期望值随 85.5 改判
}

# 裁定 85.5 的牙③是**反向**牙：变异体必须证明「已降级的判据不会红」。
# `must_stay_green=True` ⇒ 验收条件 = `n_red==0` **且** `verdict=="PASS"` **且** rc==0。
MUTATION_MUST_STAY_GREEN = {
    "replay-image-pixel-only": True,
    "replay-image-over-tolerance": True,
}
MUTATION_ALIAS = {"replay-image-over-tolerance": "replay-image-pixel-only"}
MUTATION_ALL = ("none", "dt-back-to-50hz", "reverse-judge-flipped", "random-actions",
                "replay-state-perturb-1e-3", "replay-state-1lsb",
                "replay-image-pixel-only", "replay-image-over-tolerance")


def run_gates(reps: Report, *, eps: List[dict], ctx: dict) -> None:
    """12+3 道闸。每道都给 `required`（绿条件）/`red_when`（红条件原文）/`applies_when`。"""
    mut = ctx["mutation"]
    n_req = ctx["n_required_per_direction"]
    lr = ctx.get("lerobot_verify")
    contract = ctx["contract"]

    # ---- G1 几何真值成功 + 与 reward==4 的关系（§13.8-1）----
    bad, rows = [], []
    for e in eps:
        m = e["metrics"]
        d = e["direction"]
        v = m["verdict_replay_render"] or m["verdict_replay_norender"]
        term4 = m["env_reward4_terminal"]
        rows.append({"ep": e["ep_id"], "direction": d, "verdict": v,
                     "env_reward_terminal": m["env_reward_terminal"],
                     "env_reward4_seen_any_step": m["evidence"].get("env_reward4_seen"),
                     "failure_class": m["failure_class"],
                     "held_run_steps": m["evidence"].get("max_held_run_steps"),
                     "displacement_m": m["evidence"].get("box_horizontal_displacement_m"),
                     "max_box_speed_mps": m["evidence"].get("max_box_speed_mps")})
        if v != "success":
            bad.append("%s(%s)：几何真值判词=%s（failure_class=%s）" % (e["ep_id"], d, v,
                                                                       m["failure_class"]))
        if d == "forward" and not term4:
            bad.append("%s(forward)：几何真值 success 但 env 终态 reward!=4 ⇒ **两套判定不一致**"
                       % e["ep_id"])
        if d == "reverse" and term4:
            bad.append("%s(reverse)：终态 reward==4 —— 与『reward==4 只覆盖右→左』的实测事实矛盾，"
                       "说明判据被上游 reward 污染" % e["ep_id"])
    reps.add("G1_success_geometric_truth_vs_reward4", not bad, {"n_episodes": len(eps),
             "per_episode": rows, "violations": bad},
             "每条 recorded episode 的**几何真值**判词 == success；正向还必须与 env 终态 "
             "`reward==4` 一致（§13.8-1：两者不一致 ⇒ 红）；反向终态 `reward` 必须 != 4"
             "（因为 `sim.py:141-148` 的 reward==4 只覆盖右→左，反向是**左臂抓取相位**就会触发它）",
             ruling_ref="d_handoff_to_b2 §13.8-1 / 裁定 54（判定必须独立于 reward==4）",
             red_when="任一集判词非 success / 正向终态 reward!=4 / 反向终态 reward==4",
             mutation_expected_red=(mut in ("reverse-judge-flipped", "random-actions")))

    # ---- G2 3 相机 224² + 14 维动作（§13.8-2）----
    bad, rows = [], []
    for e in eps:
        m = e["metrics"]
        pi05_slots = [s for s, _, _, _ in RENDER_SPEC if s.startswith("pi05_")]
        per = {}
        for s in pi05_slots:
            st = m["image_stats"].get(s) or {}
            per[s] = {"n_frames": st.get("n_frames"), "h": st.get("h"), "w": st.get("w"),
                      "channels": st.get("channels"), "dtype": st.get("dtype"),
                      "std_min_sampled": st.get("std_min_sampled"),
                      "mean_range_sampled": st.get("mean_range_sampled"),
                      "frame_to_frame_max_abs_diff": st.get("frame_to_frame_max_abs_diff")}
            if st.get("n_frames") != m["n_frames"]:
                bad.append("%s/%s：图像帧数 %s != 记录帧数 %s" % (e["ep_id"], s,
                                                                  st.get("n_frames"), m["n_frames"]))
            if (st.get("h"), st.get("w")) != (PI05_IMAGE_HW, PI05_IMAGE_HW):
                bad.append("%s/%s：分辨率 %s×%s != 224×224" % (e["ep_id"], s, st.get("h"),
                                                                st.get("w")))
            if st.get("dtype") != "uint8":
                bad.append("%s/%s：dtype=%s != uint8" % (e["ep_id"], s, st.get("dtype")))
            if not st.get("std_min_sampled") or st["std_min_sampled"] < 1.0:
                bad.append("%s/%s：抽样帧 std=%s < 1.0 ⇒ 疑似常量/黑图（渲染没出东西）"
                           % (e["ep_id"], s, st.get("std_min_sampled")))
            if st.get("frame_to_frame_max_abs_diff", 0) < 1:
                bad.append("%s/%s：相邻帧最大像素差 %s < 1 ⇒ 视频是静止图（团队 frame_diff 也会红）"
                           % (e["ep_id"], s, st.get("frame_to_frame_max_abs_diff")))
        if m["state_dim"] != 14 or m["action_dim"] != 14:
            bad.append("%s：state_dim=%s / action_dim=%s != 14" % (e["ep_id"], m["state_dim"],
                                                                   m["action_dim"]))
        if m["n_frames"] != m["n_actions"]:
            bad.append("%s：n_frames=%s != n_actions=%s" % (e["ep_id"], m["n_frames"],
                                                            m["n_actions"]))
        rows.append({"ep": e["ep_id"], "n_frames": m["n_frames"], "state_dim": m["state_dim"],
                     "action_dim": m["action_dim"], "pi05_slots": per})
    reps.add("G2_three_cameras_224_and_14d", not bad, {"per_episode": rows, "violations": bad},
             "每集 3 个 π₀.₅ 图像键各 224×224×3 uint8、帧数与动作数一致；state/action 均 14 维；"
             "抽样帧非常量（std ≥ 1.0）且相邻帧有变化",
             ruling_ref="d_handoff_to_b2 §13.8-2 / A2 契约 observation.image_shape",
             red_when="分辨率/通道/dtype/帧数不符 / 常量图 / 相邻帧无变化 / 维度 != 14",
             mutation_expected_red=False)

    # ---- G3 频率三件套 + 容器帧率（§13.8-3、裁定 53/57/71）----
    bad, rows = [], []
    shim = ctx["shim"]
    for e in eps:
        m = e["metrics"]
        lt = m["live_timing"]
        row = {"ep": e["ep_id"], "measured_hz": lt.get("measured_hz"), "dt": e["dt"],
               "n_sub_steps": lt.get("n_sub_steps"),
               "model_timestep_s": lt.get("model_timestep_s"),
               "episode_horizon_s": ctx["episode_horizon_s"],
               "container_fps": (m.get("team_rule_inputs") or {}).get("video_container_fps")}
        rows.append(row)
        if lt.get("measured_hz") is None or abs(lt["measured_hz"] - round(MAINLINE_HZ, 6)) > 1e-6:
            bad.append("%s：实测 control_hz=%s != 29.411765（DT=%s）" % (e["ep_id"],
                                                                        lt.get("measured_hz"),
                                                                        e["dt"]))
        if abs(e["dt"] - MAINLINE_DT) > 1e-12:
            bad.append("%s：DT=%r != 0.034" % (e["ep_id"], e["dt"]))
        if lt.get("n_sub_steps") != 17:
            bad.append("%s：n_sub_steps=%s != 17" % (e["ep_id"], lt.get("n_sub_steps")))
        if lt.get("model_timestep_s") is not None and abs(lt["model_timestep_s"] - 0.002) > 1e-9:
            bad.append("%s：model timestep=%s != 0.002" % (e["ep_id"], lt["model_timestep_s"]))
        for slot, fps in ((m.get("team_rule_inputs") or {}).get("video_container_fps") or {}).items():
            if fps is None:
                bad.append("%s/%s：容器 fps 读不到" % (e["ep_id"], slot))
            elif not (QC_FPS_BAND[0] <= float(fps) <= QC_FPS_BAND[1]):
                bad.append("%s/%s：容器 fps=%s 不在 QC 区间 [29,31]" % (e["ep_id"], slot, fps))
            elif abs(float(fps) - MAINLINE_HZ) > 1e-6:
                bad.append("%s/%s：容器 fps=%s != 29.411765（不是四舍五入到 30 就是写错了）"
                           % (e["ep_id"], slot, fps))
    if shim.get("sha256_12") != "dc14466fcdcf":
        bad.append("shim sha256-12=%s != dc14466fcdcf（A2 的频率 shim 被换过）" % shim.get("sha256_12"))
    reps.add("G3_frequency_dt_substeps_shim_container_fps", not bad,
             {"per_episode": rows, "violations": bad, "shim": shim,
              "required_triple": {"DT": MAINLINE_DT, "n_sub_steps": 17, "model_timestep": 0.002,
                                  "control_hz": round(MAINLINE_HZ, 6),
                                  "episode_horizon_s": ctx["episode_horizon_s"],
                                  "qc_band": list(QC_FPS_BAND)},
              "episode_horizon_ruling": "裁定 65-2：max_episode_steps 维持 300 ⇒ 300×0.034=10.2 s"},
             "每集实测 control_hz == 29.411765（±1e-6）、DT==0.034、n_sub_steps==17、"
             "model timestep==0.002、shim sha256-12==dc14466fcdcf、`episode_horizon_s=10.2`，"
             "且团队三槽视频容器 fps 逐字 == 500/17（在 [29,31] 内）",
             ruling_ref="裁定 53/57/65-2/71；d_simchain §2 与 S1 判据 2",
             red_when="任一频率维度不符 / shim 指纹变了 / 容器 fps 出区间或不等于 500/17",
             mutation_expected_red=(mut == "dt-back-to-50hz"))

    # ---- G4 重放逐位复现（§13.8-4）----
    bad, rows = [], []
    for e in eps:
        c = e["metrics"]["bitwise"]
        rows.append({"ep": e["ep_id"],
                     "norender_vs_expert": c.get("norender_vs_expert"),
                     "recorded_vs_norender": c.get("recorded_vs_norender"),
                     "recorded_vs_expert": c.get("recorded_vs_expert"),
                     "verdicts_all_equal": c.get("verdicts_all_equal"),
                     "terminal_box_expert": c.get("terminal_box_expert"),
                     "terminal_box_replay": c.get("terminal_box_replay"),
                     "n_steps_expert": c.get("n_steps_expert"),
                     "settle_steps_dropped": c.get("settle_steps_dropped"),
                     "n_frames_replay_recorded": c.get("n_frames_replay_recorded")})
        for k in ("norender_vs_expert", "recorded_vs_norender", "recorded_vs_expert"):
            cc = c.get(k) or {}
            if cc.get("bitwise_equal") is not True:
                bad.append("%s：%s 不是逐位相同（max_abs_diff=%s，shape_equal=%s）"
                           % (e["ep_id"], k, cc.get("max_abs_diff"), cc.get("shape_equal")))
        if not c.get("verdicts_all_equal"):
            bad.append("%s：三 pass 判词不一致 %s/%s/%s" % (
                e["ep_id"], c.get("verdict_expert"), c.get("verdict_replay_render"),
                c.get("verdict_replay_norender")))
        if c.get("terminal_box_expert") != c.get("terminal_box_replay"):
            bad.append("%s：终态方块位置不一致 %s vs %s" % (
                e["ep_id"], c.get("terminal_box_expert"), c.get("terminal_box_replay")))
        if (c.get("n_steps_expert") or 0) - (c.get("settle_steps_dropped") or 0) != \
                c.get("n_frames_replay_recorded"):
            bad.append("%s：帧数账不平 n_steps−settle=%s != recorded=%s" % (
                e["ep_id"], (c.get("n_steps_expert") or 0) - (c.get("settle_steps_dropped") or 0),
                c.get("n_frames_replay_recorded")))
    reps.add("G4_replay_reproduces_bitwise", not bad, {"per_episode": rows, "violations": bad},
             "把**下发过的那串 float32 动作**在关节模型里重放：状态轨迹与专家 pass **逐位相同**"
             "（`norender_vs_expert` 证明动作记录无损、`recorded_vs_norender` 证明渲染不扰动物理）、"
             "三 pass 判词一致、终态方块位置一致、帧数账平",
             ruling_ref=("d_handoff_to_b2 §13.8-4 / 裁定 66（示范必须在关节模型里采并重放得回同一结果）；"
                         "**裁定 85.5（§18.5）：这是 replay 侧唯一的硬判据**"),
             red_when="任一比对不是逐位相同 / 判词不一致 / 终态方块不一致 / 帧数账不平",
             blocking=True,
             mutation_expected_red=(mut in ("replay-state-perturb-1e-3", MUT_STATE_1LSB)),
             note=("裁定 85.5 的三颗牙都落在这条硬判据上：① 干净批 ⇒ 本闸绿（绿证人）；"
                   "② 变异体 `%s`（状态只改 1 个 ULP ≈1e-16）与 `replay-state-perturb-1e-3`"
                   "（改 1e-3）⇒ 本闸**必须红**；③ 变异体 `%s`（只改像素、状态一个字节不动）"
                   "⇒ 本闸**必须仍绿**——第③颗牙证明「像素已降级」真的生效了。"
                   % (MUT_STATE_1LSB, MUT_IMG_PIXEL_ONLY)))

    # ---- G4b/G4c/G4d 图像侧 replay：**裁定 85.5 之后在 egl 臂一律只登记不判红** ----
    # 判据变迁（三值纪律：不静默执行、也不静默丢弃）：
    #   §17-6（过渡期口径）：状态逐位 + `angle` 逐位 + wrist 走 D 的三容差（**超容差判红**）。
    #   §18.5 / 裁定 85.5（现行，即时生效）：**硬判据只剩「状态逐位」（G4）**；三相机像素
    #        一律**只登记不判红**，登记带取 E 的 n=5 **逐相机**实测。
    #        依据：E 的 n=5 实测 egl 三相机 `cross_process_same_sha` 全 false、`angle` 只有 4/5 逐位；
    #        B2 首手实测更强——**同进程内、同状态连渲两次** `angle` 就有帧不逐位（2/274 与 17/271）
    #        ⇒ 拿像素逐位或像素容差当判据 = **随机红 / 常态红**（最坏的一种闸）。
    #        ⇒ 新红线 `render_bitwise_equality_ban_on_egl`：egl 臂上任何闸不得以渲染帧 sha 逐位相等为判据。
    #   **osmesa/llvmpipe 臂不受该红线约束**（n=5 三相机全逐位）⇒ 该臂上 G4b/G4c 仍是逐位硬判据。
    # 三条的分工（拆开的理由仍然成立：**判据基础强度不同**）：
    #   G4b：π₀.₅ 三键 224² ⇒ E 的 reps=5 同分辨率同相机同 regime ⇒ 有登记带；egl 臂 `blocking=False`。
    #   G4c：`angle` 逐位 ⇒ 争议**已由裁定 85.5 关闭**（降为登记项）；egl 臂判 N_A（它已不是判据）。
    #   G4d：团队三槽 480×640 ⇒ E **没测过这个分辨率** ⇒ 无登记带（RR-B2-21 仍开着）；只登记实测值。
    # **结构性缺陷不在"像素降级"范围内**：两次渲染 shape 不一致 = 管线错，与像素容差无关 ⇒ 仍判红。
    gli = ctx.get("gl_identity") or {}
    renderer_class = gli.get("renderer_class")
    gl_renderer = ((gli.get("gl_strings") or {}).get("GL_RENDERER"))
    nvidia_arm = (renderer_class == "nvidia_gpu")
    shim_sha = (ctx.get("shim") or {}).get("sha256_12")
    applies_common = ("实测 GL_RENDERER=%s / renderer_class=%s（**以实测渲染器为键，不以 MUJOCO_GL "
                      "环境变量为键**，裁定 83 §5 全线规则）+ shim sha256-12=%s + 主线 env "
                      "gym_aloha/AlohaTransferCube-v0 + regime=same_state_repeat_render"
                      % (gl_renderer, renderer_class, shim_sha))
    slot_cam = {sl: cm for sl, cm, _, _ in RENDER_SPEC}
    slot_hw = {sl: (h, w) for sl, _, h, w in RENDER_SPEC}

    def _collect(slots):
        """返回 `(rows, shape_bad, exceed, missing)`。

        `shape_bad`（**blocking**）：两次渲染 shape 不一致 ⇒ 结构性缺陷，判红。
        `exceed`（**只登记**）：像素差超出 83.4 三容差 / 超出 E 的 n=5 登记带 / 不是全帧逐位
            ⇒ 裁定 85.5 之后**一律不判红**，只把事实连同实测值一起落进产物。
        """
        rows, shape_bad, exceed, missing = [], [], [], []
        for e in eps:
            per = ((e["metrics"].get("image_repeat_render") or {}).get("per_slot") or {})
            for slot in slots:
                v = per.get(slot)
                if not v:
                    missing.append("%s/%s" % (e["ep_id"], slot))
                    continue
                exc_tol = sorted(k for k, d in (v.get("tolerance_exceeded") or {}).items()
                                 if d.get("exceeded"))
                exc_band = sorted(k for k, d in (v.get("register_band_exceeded") or {}).items()
                                  if d.get("exceeded"))
                rows.append({"ep": e["ep_id"], "slot": slot, "camera": slot_cam.get(slot),
                             "hw": list(slot_hw.get(slot) or []),
                             "n_frames": v.get("n_frames"),
                             "n_frames_bitwise": v.get("n_frames_bitwise"),
                             "all_frames_bitwise": v.get("all_frames_bitwise"),
                             "max_abs_diff": v.get("max_abs_diff"),
                             "frac_diff_px": v.get("frac_diff_px"),
                             "frac_diff_elements": v.get("frac_diff_elements"),
                             "mean_abs_diff": v.get("mean_abs_diff"),
                             "within_ruling_83_4_tolerance": v.get("within_tolerance"),
                             "exceeded_ruling_83_4_tolerance": exc_tol,
                             "register_band_e_reps5": v.get("register_band_e_reps5"),
                             "within_register_band": v.get("within_register_band"),
                             "exceeded_register_band": exc_band,
                             "mutation_injected": v.get("mutation_injected")})
                if v.get("shape_mismatch"):
                    shape_bad.append("%s/%s：两次渲染 shape 不一致 %s（结构性缺陷，与像素容差无关 ⇒ 判红）"
                                     % (e["ep_id"], slot, v["shape_mismatch"]))
                    continue
                if exc_tol or exc_band or not v.get("all_frames_bitwise"):
                    exceed.append({
                        "ep": e["ep_id"], "slot": slot, "camera": slot_cam.get(slot),
                        "all_frames_bitwise": v.get("all_frames_bitwise"),
                        "n_frames": v.get("n_frames"), "n_frames_bitwise": v.get("n_frames_bitwise"),
                        "exceeded_ruling_83_4_tolerance": exc_tol,
                        "exceeded_e_reps5_register_band": exc_band,
                        "measured": {k: v.get(k) for k in
                                     ("max_abs_diff", "frac_diff_px", "mean_abs_diff")},
                        "register_band": v.get("register_band_e_reps5"),
                        "judged_red": False,
                        "why_not_red": ("裁定 85.5（§18.5）：三相机像素**一律只登记不判红**；"
                                        "硬判据只剩 G4 的「状态逐位」")})
        return rows, shape_bad, exceed, missing

    # == G4b：π₀.₅ 三键 224²（egl/nvidia 臂 ⇒ 像素**只登记**；llvmpipe 臂 ⇒ 逐位硬判据）==
    rows_b, shape_bad_b, exceed_b, missing_b = _collect(PI05_SLOTS)
    band_doc_b = e_reps5_per_cam_band()
    worst_b = {k: max([r[k] for r in rows_b if isinstance(r.get(k), (int, float))], default=None)
               for k in ("max_abs_diff", "frac_diff_px", "mean_abs_diff")}
    obs_common_b = {
        "n_episodes": len(eps), "n_slot_rows": len(rows_b), "rows": rows_b,
        "missing": missing_b, "worst": worst_b,
        "structural_violations_shape_mismatch": shape_bad_b,
        "pixel_register_exceedances": exceed_b,
        "n_pixel_register_exceedances": len(exceed_b),
        "pixel_judges_red": (not nvidia_arm),
        "ruling_83_4_tolerance": dict(REPLAY_IMG_TOL),
        "e_reps5_register_band": band_doc_b,
        "tolerance_basis": (rows_b and (eps[0]["metrics"].get("image_repeat_render") or {})
                            .get("tolerance_basis"))}
    if missing_b and not rows_b:
        reps.n_a("G4b_image_replay_pi05_224_determinism",
                 "本轮没有采到「同状态连渲两次」的图像比对（--no-image-repeat-render 或渲染 pass 被跳过）",
                 "π₀.₅ 三键（224²）同状态连渲两次的像素差必须**被登记**（裁定 85.5：像素不判红）",
                 applies_when=applies_common, ruling_ref="裁定 85.5 / 82⑤-3 / 83.4")
    elif not nvidia_arm:
        nb = [r for r in rows_b if not r.get("all_frames_bitwise")]
        reps.add("G4b_image_replay_pi05_224_determinism", not (nb or shape_bad_b),
                 dict(obs_common_b, **{
                     "mode": "bitwise_hard（llvmpipe 臂 ⇒ E 的 n=5 实测三相机全部逐位可复现，不带容差）",
                     "not_bitwise_rows": nb}),
                 "llvmpipe 臂：π₀.₅ 三键（`angle`/`left_wrist`/`right_wrist` @224²）同状态连渲两次"
                 "必须**逐位**相同（裁定 85.5 的 egl 禁令**不适用于 osmesa/llvmpipe 臂**）",
                 ruling_ref=("E RENDER_DETERMINISM_REPS5.json → verdict.applies_when.llvmpipe；"
                             "裁定 85.5（osmesa 臂不受 `render_bitwise_equality_ban_on_egl` 约束）"),
                 red_when="llvmpipe 臂上任一 π₀.₅ 槽有一帧不逐位 / 两次渲染 shape 不一致",
                 applies_when=applies_common, blocking=True, mutation_expected_red=False)
    else:
        reps.add("G4b_image_replay_pi05_224_determinism", not shape_bad_b,
                 dict(obs_common_b, **{
                     "mode": ("register_only（egl/nvidia_gpu 臂 ⇒ 裁定 85.5：像素**一律只登记不判红**；"
                              "本闸唯一的红条件是结构性缺陷 shape 不一致）"),
                     "demoted_by": "裁定 85.5 / d_handoff_to_b2 §18.5（取代 §17-6 的过渡期容差判红）",
                     "hard_criterion_now": "只剩 G4 的「状态逐位」",
                     "would_have_been_red_under_ruling_17_6": sorted(
                         {x["slot"] for x in exceed_b if x["exceeded_ruling_83_4_tolerance"]}),
                     "would_have_been_red_under_ruling_17_6_note": (
                         "§17-6 时代这些槽会判红；裁定 85.5 之后**不判红**，只把事实登记在这里")}),
                 "π₀.₅ 三键（224²）**同一状态连渲两次**的像素差必须**被登记**（实测 "
                 "`max_abs_diff`/`frac_diff_px`/`mean_abs_diff`/逐位帧占比，对照裁定 83.4 三容差与 "
                 "E 的 n=5 逐相机登记带）；**像素本身不是判据**（裁定 85.5）",
                 ruling_ref=("裁定 85.5（§18.5，即时生效）+ 新红线 `render_bitwise_equality_ban_on_egl`；"
                             "登记带来源 E 的 RENDER_DETERMINISM_REPS5.json（同 regime/同 224²/同相机名）；"
                             "裁定 83.4 的三数值按 85.5 明写「不需重定」，继续作登记参照"),
                 red_when=("**只有**结构性缺陷会红：两次渲染 shape 不一致。像素差（含超 83.4 三容差、"
                           "超 E 的 n=5 登记带、不是全帧逐位）在 egl 臂**一律不判红**，只登记"),
                 applies_when=applies_common, blocking=True,
                 mutation_expected_red=False,
                 note=("裁定 85.5 的牙③：变异体 `%s` 只往 %s 的**比对副本**注入 +%d 到 %g 的像素"
                       "（状态一个字节不动、落盘图像不动）⇒ 本闸与整批**必须仍绿**（n_red=0）。"
                       "缺这颗牙就无法证明「像素已降级」——它会红就说明降级没生效。"
                       % (MUT_IMG_PIXEL_ONLY, MUT_IMG_SLOT, MUT_IMG_DELTA, MUT_IMG_FRAC)))

    # == G4c：`angle` 逐位（§17-6 曾定为硬判据 ⇒ **争议已由裁定 85.5 关闭**：降为登记项）==
    angle_rows = [r for r in rows_b if r.get("slot") == "pi05_base_0_rgb"]
    angle_all_bitwise = bool(angle_rows) and all(r.get("all_frames_bitwise") for r in angle_rows)
    if not nvidia_arm:
        reps.add("G4c_image_replay_angle_bitwise", angle_all_bitwise,
                 {"rows": angle_rows, "all_bitwise": angle_all_bitwise},
                 "llvmpipe 臂：`angle` 相机同状态连渲两次必须**逐位**相同（E 的 applies_when.llvmpipe）",
                 ruling_ref="E RENDER_DETERMINISM_REPS5.json → verdict.applies_when.llvmpipe",
                 red_when="llvmpipe 臂上 angle 有一帧不逐位", applies_when=applies_common,
                 blocking=True)
    else:
        reps.n_a("G4c_image_replay_angle_bitwise_demoted_by_ruling_85_5",
                 "**判据已被裁定 85.5 关闭，不再待裁**：§17-6 曾把「`angle` 逐位」定为 egl 臂的硬判据，"
                 "其依据「`angle` 相机必须逐位一致（实测成立）」来自 n=2/n=3；E 的 reps=5 轮"
                 "（`767a2d984a5b`，00:49:33）实测 **egl 下 angle 跨进程 4/5 逐位、1/5 不逐位**、"
                 "`ruling_83_3_stands=false`；B2 首手实测更强：**同进程内、同状态连渲两次** `angle` "
                 "就有帧不逐位（2/274 与 17/271，独立复现 13/274 与 14/271）⇒ 拿它当硬判据不是"
                 "「间歇性假红」而是**常态红**。D 于裁定 85.5（§18.5）据此改判："
                 "**硬判据只剩「状态逐位」，三相机像素一律只登记不判红**，并立新红线 "
                 "`render_bitwise_equality_ban_on_egl`。⇒ 本条在 egl 臂**不是判据**，判 N_A；"
                 "实测值照登记（见 observed.measured），登记带由 G4b 承载（angle 也在 π₀.₅ 三键里）。",
                 "`angle` 相机同状态连渲两次逐位相同（**该判据已被裁定 85.5 废除**：egl 臂上"
                 "渲染帧逐位相等不得作判据）",
                 red_when=("**永不判红**（裁定 85.5 + `render_bitwise_equality_ban_on_egl`）。"
                           "若将来 D 恢复该判据，则本闸在任一帧 angle 不逐位时红"
                           "（**本轮实测就会红**：见 observed.measured.hard_criterion_would_have_fired）"),
                 applies_when=applies_common,
                 ruling_ref=("裁定 85.5（§18.5，现行）；历史：D §17-6 / 裁定 82⑤-3 曾定为硬判据，"
                             "前提被 E §E11.2/§E11.3 的 n=5 与 B2 的首手实测推翻"),
                 observed_extra={"angle_rows": angle_rows, "all_frames_bitwise_this_run": angle_all_bitwise,
                                 "hard_criterion_would_have_fired": (not angle_all_bitwise),
                                 "n_frames_not_bitwise": [ (r.get("n_frames") or 0) - (r.get("n_frames_bitwise") or 0)
                                                           for r in angle_rows ],
                                 "regime_is_in_process": True,
                                 "stronger_than_e_evidence": ("E 的触发是**跨进程** sha 不同；本轮是**同一进程内**"
                                                              "同状态连渲两次就有帧不逐位 ⇒ 「angle 逐位」当硬判据"
                                                              "在干净批上也会红，不是间歇性问题而是常态"),
                                    "n_episodes": len(angle_rows),
                                    "this_run_regime": "same_state_repeat_render（**进程内**）",
                                    "e_artifact": str(E_REPS5_ARTIFACT.relative_to(ROOT)),
                                    "e_artifact_sha256_12": (sha12(E_REPS5_ARTIFACT)
                                                             if E_REPS5_ARTIFACT.exists() else None),
                                    "ruling_closed_by": ("裁定 85.5（§18.5）：采纳的正是 E 倾向的丙案"
                                                         "（硬判据只留状态逐位，像素侧全走登记）"),
                                    "pending_ruling": None})

    def _team_slot_evidence(rows, exceed):
        worst = {k: max([r[k] for r in rows if isinstance(r.get(k), (int, float))], default=None)
                 for k in ("max_abs_diff", "frac_diff_px", "mean_abs_diff")}
        would = {k: {"tolerance_224": REPLAY_IMG_TOL[k], "measured_480x640": worst.get(k),
                     "would_pass_if_transplanted": bool(worst.get(k) is not None
                                                        and worst[k] <= REPLAY_IMG_TOL[k])}
                 for k in ("max_abs_diff", "frac_diff_px", "mean_abs_diff")}
        return {"n_slot_rows": len(rows), "rows": rows, "worst": worst,
                "pixel_register_exceedances": exceed,
                "register_band": None,
                "register_band_status": ("**该分辨率（480×640）没有实测登记带**：E 的 n=5 只测了 224×224"
                                         "（`resolution=[224,224]`）⇒ 按裁定 71 `caliber_transplant_ban` "
                                         "不搬用；B2 也不自造阈值"),
                "rr": ("RR-B2-21（**仍开着**，但用途已变）：请 E 把 reps≥5 确定性轮扩到 480×640 团队三槽"
                       "——裁定 85.5 之后这不再是「判红阈值」的基础，只是**登记带**的基础"),
                "counterfactual_if_tolerance_were_extended": would,
                "counterfactual_note": ("**这不是判定**，只是把「若 D/E 决定把那组 224² 容差扩到 480×640，"
                                        "本批会不会过」现算出来给裁者看。B2 不搬用阈值（裁定 71），"
                                        "也不因为有这条现算就改变判定。")}

    # == G4d：团队三槽 480×640（裁定 85.5 之后：**只登记**；无该分辨率的登记带 ⇒ RR-B2-21 仍开着）==
    rows_d, shape_bad_d, exceed_d, missing_d = _collect(TEAM_SLOTS)
    all_bitwise_d = bool(rows_d) and all(r.get("all_frames_bitwise") for r in rows_d)
    if missing_d and not rows_d:
        reps.n_a("G4d_image_replay_team_480x640",
                 "本轮没有采到团队三槽的图像重复渲染比对",
                 "团队三槽（480×640）同状态连渲两次的差异必须被**登记**",
                 applies_when=applies_common, ruling_ref="裁定 71 caliber_transplant_ban",
                 observed_extra={"rows": rows_d, "missing": missing_d})
    else:
        reps.add("G4d_image_replay_team_480x640_register_only", not shape_bad_d,
                 dict(_team_slot_evidence(rows_d, exceed_d), **{
                     "mode": ("register_only（裁定 85.5：egl 臂像素**只登记不判红**；本闸唯一的红条件"
                              "是结构性缺陷 shape 不一致）"),
                     "all_frames_bitwise": all_bitwise_d,
                     "pixel_judges_red": False,
                     "structural_violations_shape_mismatch": shape_bad_d,
                     "missing": missing_d,
                     "id_history": ("旧 id `G4d_image_replay_team_480x640` / "
                                    "`G4d_image_replay_team_480x640_no_measured_basis`（§17-6 时代"
                                    "按「有没有阈值基础」在 PASS/N_A 之间切换）⇒ 裁定 85.5 之后"
                                    "像素不再是判据，两条合并成本条登记项")}),
                 "团队三槽（`top`/`left_wrist`/`right_wrist` @480×640）同状态连渲两次的差异必须**被登记**"
                 "（实测三项 + 逐位帧占比 + 首手登记的差异量级）；**像素本身不是判据**（裁定 85.5）",
                 ruling_ref="裁定 85.5（§18.5）+ `render_bitwise_equality_ban_on_egl`；裁定 71 "
                            "caliber_transplant_ban（不搬用 224² 的阈值到 480×640）",
                 red_when=("**只有**结构性缺陷会红：两次渲染 shape 不一致。像素差在 egl 臂**一律不判红**"
                           "（该分辨率连登记带都还没有 ⇒ RR-B2-21 开着，但那只影响登记、不影响判定）"),
                 applies_when=applies_common + " + 480×640", blocking=True,
                 mutation_expected_red=False)

    # ---- G5 反向判据自建（§13.8-5）----
    rev = [e for e in eps if e["direction"] == "reverse"]
    bad, rows = [], []
    for e in rev:
        m = e["metrics"]
        rows.append({"ep": e["ep_id"], "verdict": m["verdict_replay_render"],
                     "env_reward_terminal": m["env_reward_terminal"],
                     "env_reward4_seen_any_step": m["evidence"].get("env_reward4_seen"),
                     "on_goal_side_x_sign_diagnostic_only":
                         m["evidence"].get("on_goal_side_x_sign_diagnostic_only"),
                     "displacement_m": m["evidence"].get("box_horizontal_displacement_m")})
        if m["verdict_replay_render"] == "success" and m["env_reward4_terminal"]:
            bad.append("%s：反向成功集的终态 reward==4 ⇒ 判据可能是在读上游 reward（不独立）"
                       % e["ep_id"])
    indep_proof = ("反向成功的每一集，终态 `env_reward != 4` 而几何真值判词 == success ⇒ "
                   "判词**不可能**来自 reward==4（这是「独立性」的实测证明，不是声明）。"
                   "另：`SuccessJudge`（scripts/b2_s1_scripted_expert.py:337）只读几何量"
                   "（方块位姿/速度、指尖位置、指 geom 接触），代码里没有 reward 分支。")
    if not rev:
        reps.n_a("G5_reverse_criteria_self_built", "本臂没有反向集（--directions forward）",
                 "反向集必须存在且由自建几何判据判定")
    else:
        reps.add("G5_reverse_criteria_self_built", not bad,
                 {"n_reverse": len(rev), "per_episode": rows, "violations": bad,
                  "independence_proof": indep_proof,
                  "judge_source": "scripts/b2_s1_scripted_expert.py:337 SuccessJudge",
                  "judge_direction_params": {"pick": expert.DIRECTION["reverse"]["pick"],
                                             "receive": expert.DIRECTION["reverse"]["receive"],
                                             "goal_x_sign": expert.DIRECTION["reverse"][
                                                 "goal_x_sign"]},
                  "expected_direction_params": {"pick": "left", "receive": "right",
                                                "goal_x_sign": 1}},
                 "反向集由**自建几何真值判据**判定（不读 env reward==4），且判据方向参数与 "
                 "`DIRECTION['reverse']`（pick=left/receive=right/goal_x_sign=+1）一致",
                 ruling_ref="d_handoff_to_b2 §13.8-5；d_simchain S1 判据 3；裁定 54",
                 red_when="反向集为 0 / 反向成功集终态 reward==4（判据被污染）/ 方向参数被写反",
                 mutation_expected_red=(mut == "reverse-judge-flipped"))
        if expert.DIRECTION["reverse"] != {"pick": "left", "receive": "right", "goal_x_sign": 1}:
            reps.checks[-1]["status"] = "RED"
            reps.checks[-1]["ok"] = False
            reps.checks[-1]["observed"]["violations"].append(
                "DIRECTION['reverse'] 被改成 %s（判据方向写反）" % expert.DIRECTION["reverse"])

    # ---- G6 双向均衡 ----
    per_dir = {}
    for e in eps:
        per_dir[e["direction"]] = per_dir.get(e["direction"], 0) + 1
    ok6 = (len(per_dir) == 2 and min(per_dir.values()) >= n_req and
           len(set(per_dir.values())) == 1)
    reps.add("G6_directions_balanced", ok6,
             {"n_per_direction": per_dir, "n_required_per_direction": n_req,
              "direction_labels": {k: DIRECTION_LABEL[k] for k in per_dir},
              "reverse_label": REVERSE_DIRECTION_LABEL},
             "正反两向条数相等且各 ≥ N（N 见 manifest 的 `n_proposed`/`n_ruled_by_d`）；"
             "**反向为 0 是全项目最硬的数据缺口**",
             ruling_ref="D→B2 §2.2-1；裁定 54；A 线量化：输出空间 0.0028 / 权重空间 0.966",
             red_when="条数不等 / 任一方向 < N / 只跑了一个方向",
             mutation_expected_red=False)

    # ---- G7 专家闸 ----
    sv = ctx["self_verify"]
    bad = [e["ep_id"] for e in eps
           if (e["metrics"]["verdict_replay_render"] or e["metrics"]["verdict_replay_norender"])
           != "success"]
    rate = sv.get("success_rate")
    if sv.get("status") != "measured":
        bad.append("留出集自证证据 status=%s（%s）⇒ 不许拿它当专家闸的凭据"
                   % (sv.get("status"), sv.get("why")))
    ha = sv.get("horizon_accounting") or {}
    if ha.get("n_over_registered_horizon"):
        bad.append("留出集里有 %s 集 n_steps > 登记的 max_episode_steps=%s（裁定 65-2）"
                   % (ha["n_over_registered_horizon"], ha.get("registered_max_episode_steps")))
    ok7 = (not bad) and (rate is None or rate >= 0.5)
    reps.add("G7_expert_gate_recorded_all_success", ok7,
             {"n_recorded": len(eps), "n_not_success": len(bad), "not_success_eps": bad,
              "heldout_self_verify": sv,
              "threshold_d_ruled": 0.5, "threshold_b2_proposed_for_scaling": 0.9,
              "failure_classes_observed": sorted({str(e["metrics"]["failure_class"]) for e in eps})},
             "被记录进数据集的每一集都必须是几何真值 success（不达标的集**不入集**，不是入集后标注）；"
             "留出 seed 上的专家成功率必须报告且 ≥ 50%（D 的阈值），B2 建议扩量门槛 90%",
             ruling_ref="d_simchain S1 判据 4；d_handoff_to_b2 §13.9-②",
             red_when="任一 recorded 集判词非 success / 留出成功率 < 0.5",
             mutation_expected_red=(mut in ("reverse-judge-flipped", "random-actions")))

    # ---- G8 第 0 帧在沉降之后（裁定 66 §13.7-1）----
    bad, rows = [], []
    for e in eps:
        m = e["metrics"]
        z0 = m["box_z_frame0"]
        rows.append({"ep": e["ep_id"], "box_z_frame0": z0, "box_xyz_frame0": m["box_xyz_frame0"],
                     "settle_steps_dropped": m["bitwise"]["settle_steps_dropped"],
                     "box_z_seeded": BOX_Z_SEEDED, "box_z_at_rest": BOX_Z_AT_REST})
        if z0 is None or abs(z0 - BOX_Z_AT_REST) > 1e-3:
            bad.append("%s：第 0 帧方块 z=%s，与落定值 %s 差 > 1 mm ⇒ 前几帧在教『方块凭空下落』"
                       % (e["ep_id"], z0, BOX_Z_AT_REST))
        if m["bitwise"]["settle_steps_dropped"] != BOX_SETTLE_STEPS:
            bad.append("%s：丢弃的沉降噪步数=%s != 12" % (e["ep_id"],
                                                          m["bitwise"]["settle_steps_dropped"]))
    reps.add("G8_box_settle_before_frame0", not bad, {"per_episode": rows, "violations": bad},
             "第 0 帧的方块 z == 0.0200 ± 1 mm（seeding 0.05 → 12 步落定），且数据集**丢弃**了那 12 步",
             ruling_ref="裁定 66 §13.7-1（数字取自 B2 probe4，不许另测）",
             red_when="第 0 帧方块还在下落 / 沉降步数不是 12 / 沉降帧被记进数据集",
             mutation_expected_red=False)

    # ---- G9 夹爪标定与 probe4 一致（裁定 66 §13.7-2）----
    bad, rows, unjudged9 = [], [], []
    mono_rows = []
    for e in eps:
        g = e["metrics"]["gripper"]
        rows.append({"ep": e["ep_id"], "cmd_min": g["cmd_min"], "cmd_max": g["cmd_max"],
                     "expected_close": g["expected_spread_close_holding_box_m"],
                     "per_side": g["per_side"], "bins": g["calibration_bins_quasistatic"]})
        if g["cmd_max"] is not None and g["cmd_max"] < 0.999:
            bad.append("%s：命令开度最大值 %s < 1.0（没有真的张开）" % (e["ep_id"], g["cmd_max"]))
        if g["cmd_min"] is not None and g["cmd_min"] > 0.001:
            bad.append("%s：命令开度最小值 %s > 0.0（没有真的闭合）" % (e["ep_id"], g["cmd_min"]))
        exp_close = g["expected_spread_close_holding_box_m"]
        if exp_close is None:
            bad.append("%s：方块宽度没能从模型实测（%s）⇒ 夹持期望值无法导出"
                       % (e["ep_id"], g["box_geom"].get("why")))
        for side in ("left", "right"):
            r9 = g["per_side"][side]
            # ① 张开：准静态中位 vs probe4 表（±5 mm，容差理由见 GRIP_TOL_OPEN_M）
            so = r9["spread_open_quasistatic_median"]
            if r9["open_status"] != "measured":
                unjudged9.append("%s/%s：%s" % (e["ep_id"], side, r9["open_why"]))
            elif abs(so - GRIP_CALIBRATION_TABLE["1.0"]) > GRIP_TOL_OPEN_M:
                bad.append("%s/%s：cmd=1.0 准静态指距中位 %s 与 probe4 的 %s 差 > %s m"
                           % (e["ep_id"], side, so, GRIP_CALIBRATION_TABLE["1.0"], GRIP_TOL_OPEN_M))
            # ② 动态过冲只做 sanity 上界（不是标定值）
            if r9["spread_open_dynamic_max"] is not None and \
                    r9["spread_open_dynamic_max"] > GRIP_DYNAMIC_MAX_M:
                bad.append("%s/%s：cmd=1.0 时指距动态最大 %s > %s m（甩动过冲超出 sanity 上界）"
                           % (e["ep_id"], side, r9["spread_open_dynamic_max"], GRIP_DYNAMIC_MAX_M))
            # ③ 夹持：闭爪指距 == 空载闭合指距 + 方块实测宽（±2 mm）⇒ 证明**夹住了方块**而非夹空
            sc = r9["spread_close_median"]
            if r9["close_status"] != "measured":
                unjudged9.append("%s/%s：%s" % (e["ep_id"], side, r9["close_why"]))
            elif exp_close is not None and abs(sc - exp_close) > GRIP_TOL_CLOSE_M:
                bad.append("%s/%s：cmd=0.0 时指距中位 %s 与『空载闭合 %s + 方块实测宽 %s = %s』"
                           "差 > %s m ⇒ 要么夹空了（会掉到 %s），要么夹的不是方块"
                           % (e["ep_id"], side, sc, GRIP_CALIBRATION_TABLE["0.0"],
                              g["box_geom"].get("width_m"), exp_close, GRIP_TOL_CLOSE_M,
                              GRIP_CALIBRATION_TABLE["0.0"]))
        # ④ 单调性：准静态指距必须随 cmd 单调不减（开合语义写反会在这里露）
        seq = [(float(b), v["median_spread_m"]) for b, v in
               sorted(g["calibration_bins_quasistatic"].items(), key=lambda kv: float(kv[0]))
               if v["median_spread_m"] is not None]
        mono_ok = all(seq[i + 1][1] >= seq[i][1] - 1e-4 for i in range(len(seq) - 1))
        mono_rows.append({"ep": e["ep_id"], "n_bins_judged": len(seq), "monotonic": mono_ok,
                          "series_cmd_to_spread": seq})
        if len(seq) >= 2 and not mono_ok:
            bad.append("%s：准静态指距对 cmd 不单调：%s ⇒ 开/闭语义或标定表被写反" % (e["ep_id"], seq))
    # 三值取值：有违规 ⇒ RED（红优先）；没违规但有判不了的 ⇒ UNJUDGED；全判得了且没违规 ⇒ PASS
    ok9 = False if bad else (None if unjudged9 else True)
    reps.add("G9_gripper_calibration_matches_probe4", ok9,
             {"per_episode": rows, "violations": bad, "unjudged": unjudged9,
              "monotonicity": mono_rows,
              "manifest_constants": {"open_cmd": GRIP_CMD_OPEN, "close_cmd": GRIP_CMD_CLOSE,
                                     "open_close_threshold_cmd": GRIP_CMD_THRESHOLD,
                                     "calibration_table_cmd_to_spread_m": GRIP_CALIBRATION_TABLE,
                                     "box_geom_measured": box_geom_measured()},
              "expected_close_with_box_m": (round(GRIP_CALIBRATION_TABLE["0.0"]
                                                  + (box_geom_measured().get("width_m") or 0.0), 6)),
              "spread_definition": "|finger_geom_1 − finger_geom_2|（与 probe4:150 同定义）",
              "why_open_tolerance_is_5mm": ("probe4 在**复位构型**测 0.08412，数据集里准静态帧都在"
                                            "**工作构型**；B2 2026-09-30 实测两处差 3.34 mm"
                                            "（0.08746 vs 0.08412）⇒ 容差 5 mm 容得下构型差，"
                                            "又远小于开合写反会造成的 6.9 cm 差"),
              "why_close_expected_is_sum": ("闭爪夹住方块时，指距 = 空载闭合指距 + 方块宽："
                                            "0.01833 + 0.04 = 0.05833，实测中位 0.05837（差 0.04 mm）。"
                                            "第一版写的 [0.030,0.045] 是**没依据的手写带**，"
                                            "它把正确的数据判红了；正确期望值必须由实测量导出"),
              "gate_is_three_valued": ("准静态帧不够 ⇒ UNJUDGED（不判绿也不判红），"
                                       "不拿动态过冲去比静态标定表")},
             "开=cmd 1.0、闭=cmd 0.0、阈值 cmd≈0.45 全部进 manifest；**准静态**实测指距与 probe4 "
             "标定表一致（张开 ±5 mm）；闭爪夹持指距 == 空载闭合 + 方块实测宽（±2 mm）；"
             "指距对 cmd 单调不减；动态过冲 ≤ 0.12 m",
             ruling_ref="裁定 66 §13.7-2；probe/probe4.json → E4_gripper_spread；方块宽实测自模型 geom_size",
             red_when=("命令没到 0/1 两端 / 准静态张开指距偏离 probe4 表 > 5 mm / "
                       "夹持指距偏离『空载闭合+方块宽』> 2 mm（夹空或夹错物）/ 指距对 cmd 不单调 / "
                       "动态过冲 > 0.12 m / 方块宽无法实测"),
             mutation_expected_red=False)

    # ---- G10 体积与写入面 ----
    vol = ctx["volume"]
    ok10 = vol["gib_written"] < 10.0 and not vol["paths_outside_write_area"]
    reps.add("G10_volume_and_write_area", ok10, vol,
             "写入总量 < 10 GiB（超过必须先申报，NFS 已用 95%）；所有写入路径都在 B2 的写入面内"
             "（`runs/vla/b2_*`）；`datasets/`、`workplace/`、`yfw_input/`、团队 `vla_pipeline`、"
             "site-packages 一个字节都没写",
             ruling_ref="D→B2 §10.3-3 体积纪律；裁定 61/68（覆写违规）",
             red_when="≥10 GiB 未申报 / 任一写入落在写入面之外",
             mutation_expected_red=False)

    # ---- G11 溯源完整（裁定 50.2 / 70 / 72-1 / 73）----
    need = ctx["provenance_required_fields"]
    missing = [k for k in need if ctx["provenance_get"](k) in (None, "", [], {})]
    reps.add("G11_provenance_complete", not missing,
             {"n_required_fields": len(need), "missing_or_empty": missing,
              "required_fields": need},
             "manifest 必须齐：三件套版本（policy/stats/shim）、DT+n_sub_steps+model timestep+"
             "shim sha256-12、venv/python/包版本、GL 三条原文 + renderer_class + identity_source、"
             "activation_env + prefix_paths_verified 三布尔、git HEAD、脚本 sha256-12、"
             "loadavg 三点、nr_throttled 增量、cotenant_evidence、生成时刻与命令原文",
             ruling_ref="裁定 50.2（计数类主张同批落 mtime/计数/命令原文）、70、72-1、73",
             red_when="任一必填溯源字段缺失或为空",
             mutation_expected_red=False)

    # ---- G12 lerobot 可读回且无损 ----
    if lr is None:
        reps.n_a("G12_lerobot_readable_and_lossless", "本臂 --skip-lerobot（变异臂只验团队形态与频率）",
                 "数据集必须能被 LeRobotDataset 读回，且时间戳/图像/state/action 逐字段对得上")
    else:
        bad = []
        if not lr["counts_match"]:
            bad.append("集数/帧数不符：%s/%s vs 期望 %s/%s" % (lr["num_episodes"], lr["num_frames"],
                                                              lr["episodes_expected"],
                                                              lr["frames_expected"]))
        if not lr["fps_matches_control_hz"]:
            bad.append("info.fps=%s != 29.411764705882355" % lr["fps"])
        tc = lr["timestamp_check"]
        if not tc["ok"]:
            bad.append("时间戳 != **集内** frame_index/29.4118（max_abs_err=%s；%s；"
                       "全局 index 对位=%s；每集 frame_index 从 0 连续=%s）"
                       % (tc["max_abs_err_s"], tc["expected_formula"],
                          tc["global_index_matches_position"],
                          all((tc["frame_index_contiguous_from_0_per_episode"] or {}).values())))
        for k, v in lr["roundtrip_lossless"].items():
            if not v["bitwise_equal"]:
                bad.append("%s：PNG 往返不是逐字节相同（max_abs_uint8_diff=%s）"
                           % (k, v["max_abs_uint8_diff"]))
        for k in contract["camera_map"]:
            if k not in lr["feature_keys"]:
                bad.append("契约键 %s 不在数据集 features 里" % k)
            elif lr["image_shapes"].get(k) != [3, 224, 224]:
                bad.append("%s 读回形状 %s != [3,224,224]" % (k, lr["image_shapes"].get(k)))
        if lr["state_shape"] != [14] or lr["action_shape"] != [14]:
            bad.append("state/action 形状 %s/%s != [14]" % (lr["state_shape"], lr["action_shape"]))
        reps.add("G12_lerobot_readable_and_lossless", not bad,
                 {**{k: v for k, v in lr.items() if k not in ("info_json",)}, "violations": bad},
                 "`LeRobotDataset(root=…)` 能读回：集数/帧数对得上、`info.fps` 逐字等于 29.4118、"
                 "时间戳 == frame_index/29.4118（±1e-6）、三个 π₀.₅ 键读回形状 [3,224,224]、"
                 "PNG 内嵌往返**逐字节**相同、state/action 形状 [14]",
                 ruling_ref="d_simchain S1 判据 1（lerobot 可消费格式）；A2 契约 camera_map",
                 red_when="读不回 / 计数不符 / fps 或时间戳不是 29.4118 口径 / 往返有损 / 键或形状不符",
                 mutation_expected_red=False)

    # ---- G13 任务串与相机映射逐字对齐 A2 契约 ----
    bad = []
    if ctx["task_text"]["forward"] != contract.get("task"):
        bad.append("正向任务串 %r != A2 契约 args.task %r" % (ctx["task_text"]["forward"],
                                                              contract.get("task")))
    if ctx["cam_map"] != contract.get("camera_map"):
        bad.append("相机映射 %s != 契约 %s" % (ctx["cam_map"], contract.get("camera_map")))
    for e in eps:
        if e["task_text"] != ctx["task_text"][e["direction"]]:
            bad.append("%s：task_info 与本线声明的任务串不一致" % e["ep_id"])
    reps.add("G13_task_text_and_camera_map_match_a2_contract", not bad,
             {"violations": bad, "task_text": ctx["task_text"], "task_text_status": TASK_TEXT_STATUS,
              "cam_map": ctx["cam_map"], "contract_task": contract.get("task"),
              "contract_camera_map": contract.get("camera_map"),
              "contract_path": str(A2_CONTRACT), "contract_sha256_12": ctx["contract_sha12"],
              "d_naming_discrepancy": ctx["d_naming_discrepancy"]},
             "正向任务串与相机映射**运行时从 A2 契约读并逐字比对**（`args.task`、"
             "`observation.camera_map`）；反向任务串是 B2 的镜像提案，标 `b2_proposed_mirror_pending_d`",
             ruling_ref="裁定 64（引用必须带文件身份）；B2 排序裁定：G2 契约优先于 G3",
             red_when="任务串或相机映射与契约不符 / 契约文件读不到",
             mutation_expected_red=False)

    # ---- G14 复位 14 维状态与 A2 契约逐位相同（钉死装配序 RR-B2-09）----
    bad, rows = [], []
    for e in eps:
        c = e["metrics"]["reset_state_vs_a2_contract"]
        rows.append({"ep": e["ep_id"], **{k: v for k, v in c.items()
                                          if k != "upstream_reconstruction"}})
        if c.get("vs_upstream_bitwise_equal") is None:
            bad.append("%s：上游常量重构失败（%s）⇒ 无从做逐位比对"
                       % (e["ep_id"], (c.get("upstream_reconstruction") or {}).get("why")))
        elif c["vs_upstream_bitwise_equal"] is not True:
            bad.append("%s：复位 state14 与**上游常量重构值**不逐位相同（max_abs_diff=%s）⇒ "
                       "14 维装配序或夹爪归一化与上游不一致"
                       % (e["ep_id"], c.get("vs_upstream_max_abs_diff")))
        if c.get("vs_contract_round6_bitwise_equal") is None:
            bad.append("%s：契约里没有 state_raw_14d ⇒ 跨线比对做不了" % e["ep_id"])
        elif c["vs_contract_round6_bitwise_equal"] is not True:
            bad.append("%s：复位 state14（round 到 6 位）与 A2 契约 state_raw_14d 不逐位相同"
                       "（max_abs_diff=%s，超出契约自身 6 位小数的舍入容差 5e-07）"
                       % (e["ep_id"], c.get("vs_contract_max_abs_diff")))
    reps.add("G14_reset_state_bitwise_matches_a2_contract", not bad,
             {"per_episode": rows, "violations": bad,
              "assembly_order": "[左臂6, 左夹爪1, 右臂6, 右夹爪1]（constants.JOINTS / sim.py:38-53,61-69）",
              "grip14_to_qpos_pair": "+v, −v（tasks/sim.py:47-48 实测）",
              "upstream_reconstruction": upstream_reset_state14(),
              "why_two_tiers": ("A2 契约的 state_raw_14d 是**四舍五入到 6 位小数**写进 JSON 的"
                                "（0.099848331… → 0.099848），拿它做逐位比必然差 3.3e-07 ⇒ "
                                "闸会永久红、也就永久没用。所以：①**逐位**比的对象换成用上游 "
                                "`START_ARM_POSE`+`normalize_puppet_gripper_position` 现算的值；"
                                "②对契约按它自己的 6 位小数口径比（两边都 round(·,6) 再逐位），"
                                "并另外记录原始差值必须 ≤ 5e-07（= 6 位小数的半个舍入步长）"),
              "note": "这条把 RR-B2-09（14 维装配序）钉在**跨线可核验**的证据上：用错序会让 "
                      "max|Δ| 变成 O(1) rad（B2 probe2 实测用错序 ⇒ 跟踪误差 2.418 rad，对序 ⇒ 0.028 rad）"},
             "每集复位瞬间的 `state14()` 与**上游常量重构值逐位相同**，且与 A2 契约 "
             "`observation.state_raw_14d` 在契约自身的 6 位小数口径下逐位相同（原始差 ≤ 5e-07）",
             ruling_ref="RR-B2-09；裁定 66 §13.7-3（存 14 维不存 16 维 qpos）",
             red_when="任一集复位状态与契约不逐位相同",
             mutation_expected_red=False)

    # ---- G15 团队 schema 与团队规则阈值（自己先算，不等 QC 判红）----
    bad, rows = [], []
    for e in eps:
        t = e["metrics"].get("team_rule_inputs")
        if not t:
            continue
        rows.append({"ep": e["ep_id"], **{k: v for k, v in t.items()
                                          if k != "dimension_config_check"},
                     "dimension_config_check": t["dimension_config_check"]})
        if t["dimension_config_check"]["n_bad"]:
            bad.append("%s：DIMENSION_CONFIG %s 个键不合格 %s" % (
                e["ep_id"], t["dimension_config_check"]["n_bad"],
                t["dimension_config_check"]["bad"][:3]))
        if not (t["quat_norm2_min"] >= 0.98 and t["quat_norm2_max"] <= 1.02):
            bad.append("%s：四元数模² 越出 C02 的 [0.98,1.02]（%s..%s）" % (
                e["ep_id"], t["quat_norm2_min"], t["quat_norm2_max"]))
        if t["max_frame_pose_delta_m"] >= POSE_JUMP_POS_M or \
                t["max_frame_pose_delta_deg"] >= POSE_JUMP_DEG:
            bad.append("%s：逐帧 pose 跳变 %s m / %s° 触到 C03 阈值（%s m / %s°）⇒ clean 段会删帧" % (
                e["ep_id"], t["max_frame_pose_delta_m"], t["max_frame_pose_delta_deg"],
                POSE_JUMP_POS_M, POSE_JUMP_DEG))
        if t["max_wrist_to_head_cam_m"] >= WRIST_CAM_MAX_DIST_M:
            bad.append("%s：腕→头相机距离 %s m ≥ M02 阈值 %s m ⇒ 帧会被标 invalid" % (
                e["ep_id"], t["max_wrist_to_head_cam_m"], WRIST_CAM_MAX_DIST_M))
        if t["max_left_right_ee_dist_m"] > EUCLIDEAN_THRESHOLD_M:
            bad.append("%s：左右末端距离 %s m > E 阈值 %s m" % (
                e["ep_id"], t["max_left_right_ee_dist_m"], EUCLIDEAN_THRESHOLD_M))
        if t["longest_all_open_still_run_s"] >= STILL_SECONDS:
            bad.append("%s：连续 %s s 全开且不动 ≥ I/C01 的 %s s ⇒ 会被判异常静止/被截断" % (
                e["ep_id"], t["longest_all_open_still_run_s"], STILL_SECONDS))
        if not t["subtask_contiguous"] or t["subtask_last_end"] != e["metrics"]["n_frames"] - 1:
            bad.append("%s：subtask 区间不连续或末端 %s != n−1=%s" % (
                e["ep_id"], t["subtask_last_end"], e["metrics"]["n_frames"] - 1))
        for slot, nf in t["video_nb_read_frames"].items():
            if str(nf) != str(e["metrics"]["n_frames"]):
                bad.append("%s/%s：视频帧数 %s != json 帧数 %s（团队 V07/V08/H 会红）" % (
                    e["ep_id"], slot, nf, e["metrics"]["n_frames"]))
    reps.add("G15_team_schema_and_rule_thresholds", not bad,
             {"per_episode": rows, "violations": bad,
              "thresholds_source": "vla_pipeline/configs/default.yaml（只读，逐字抄，不放宽）"},
             "团队形态自洽：17 个 DIMENSION_CONFIG 键齐且每帧维度对、四元数模² ∈ C02 的 [0.98,1.02]、"
             "逐帧 pose 跳变 < C03 的 0.1 m / 30°、腕→头相机距离 < M02 的 1.2 m、左右末端距离 ≤ E 的 "
             "1.5 m、连续全开静止 < I/C01 的 5 s、subtask 连续且末端 == n−1、三视频帧数 == json 帧数",
             ruling_ref="D→B2 §2.2（过团队 validate→clean→qc，不放宽任何阈值）",
             red_when="任一团队规则的阈值被本数据触到（QC 会判红或 clean 会删帧）",
             mutation_expected_red=False)

    # ---- G16 内参自洽（拿像素验，不靠"形状对"）----
    bad, rows, conventions = [], [], set()
    degenerate_slots, depth_signs = [], set()
    for e in eps:
        vis = e.get("_s1_visual")
        if not vis:
            # 三值纪律：闸读的键**不存在**时不许空过变绿（B2 2026-09-29 自查抓到的接线 bug）
            bad.append("%s：缺 `_s1_visual` 证据（main 没把渲染 pass 的投影检查接进来）⇒ "
                       "G16 无法判，按红处理" % e["ep_id"])
            rows.append({"ep": e["ep_id"], "checks": {}, "intrinsics_status": {},
                         "evidence_missing": True})
            continue
        chk = vis.get("intrinsics_projection_check") or {}
        row = {"ep": e["ep_id"], "checks": chk,
               "intrinsics_status": {k: v.get("status") for k, v in
                                     (vis.get("intrinsics_status") or {}).items()},
               "evidence_pass_used": vis.get("pass_used"),
               "w2c_static_diag": vis.get("w2c_static_diag")}
        rows.append(row)
        for slot, c in chk.items():
            if c.get("status") not in ("measured_ok", "measured_ok_v_axis_degenerate"):
                bad.append("%s/%s：内参投影验证 status=%s（%s）⇒ 把方块中心投到图上，"
                           "紧半径 %d px 内不是**唯一**命中红占优像素（各约定到最近红像素的距离 %s）" % (
                               e["ep_id"], slot, c.get("status"), c.get("why", ""),
                               c.get("tight_radius_px", PROJECTION_TIGHT_RADIUS_PX),
                               {k: v.get("dist_to_nearest_red_px")
                                for k, v in (c.get("projections") or {}).items()}))
            else:
                if c.get("v_axis_measured") not in (None, "UNJUDGED_degenerate"):
                    conventions.add((c.get("depth_sign_measured"), c.get("v_axis_measured")))
                else:
                    degenerate_slots.append("%s/%s" % (e["ep_id"], slot))
                depth_signs.add(c.get("depth_sign_measured"))
            if c.get("status") == "measured_inconsistent":
                bad.append("%s/%s：%s" % (e["ep_id"], slot, c.get("why")))
        for slot, it in (vis.get("intrinsics_status") or {}).items():
            if it.get("status") != "measured_from_model_and_xml":
                bad.append("%s/%s：intrinsics status=%s（%s）" % (e["ep_id"], slot,
                                                                  it.get("status"), it.get("why", "")))
    if len(conventions) > 1:
        bad.append("两个固定相机测出的投影约定不一致：%s" % sorted(map(str, conventions)))
    if len(depth_signs) > 1:
        bad.append("不同集/槽测出的深度符号不一致：%s" % sorted(map(str, depth_signs)))
    if not conventions and not bad:
        # 整批**一次都没**把 v 轴定下来 ⇒ 这条闸等于没验到东西（不许空转判绿）
        bad.append("全部 %d 个投影检查都因探针点退化而判不出 v 轴约定 ⇒ G16 空转，"
                   "换探针点重测（退化槽：%s）" % (len(degenerate_slots), degenerate_slots[:6]))
    reps.add("G16_intrinsics_self_consistent_in_pixels", not bad,
             {"per_episode": rows, "violations": bad,
              "projection_convention_measured": sorted(map(str, conventions)),
              "depth_signs_measured": sorted(map(str, depth_signs)),
              "v_axis_degenerate_slots": {"n": len(degenerate_slots), "list": degenerate_slots},
              "v_axis_degenerate_explained": ("被测方块中心落在相机光轴水平面附近时，两个 v 约定的"
                                              "投影间距 2·fy·|Y|/depth → 0，**物理上不可分辨**；"
                                              "先导 10 集里有 2 集的 angle 相机栽在这里"
                                              "（间距 4.64 px < 2×8 px）⇒ 标 UNJUDGED 不判红，"
                                              "但要求整批至少有一次把 v 轴定下来，否则算空转"),
              "radii_px": {"tight_for_judgment": PROJECTION_TIGHT_RADIUS_PX,
                           "loose_for_context_only": PROJECTION_LOOSE_RADIUS_PX},
              "method": ("把第 0 帧的方块中心（世界坐标，取自 physics 的 body xpos）按 K 与 w2c 投到图上，"
                         "再在 **8 px 紧半径**内找『红占优』像素（r>90 且 r>g+25 且 r>b+25）；"
                         "60 px 松半径只作上下文（方块是整块红斑，松半径会让错的约定也命中）。"
                         "**四种约定**（深度 ±z × v 轴 ±）都算一遍，由命中的那个定约定（不照抄文档）；"
                         "命中的深度符号还要与 targetbody 独立测出的轴约定对账，两者打脸 ⇒ 判红"),
              "why_this_gate": ("团队 QC 只查 `has_intrinsics_3x3`（`common/episode_stats.py:311`）⇒ "
                                "形状对就算过；ABC-130k 实测有 25 条 intrinsics 与自己的分辨率不自洽。"
                                "自洽性只能自己拿像素证。")},
             "每个固定相机（top@480×640、angle@224²）的内参都能把已知世界点投到正确的像素上"
             "（8 px 紧半径内**唯一**命中红占优像素，实测命中距离 0.37/0.65 px），"
             "两相机测出的投影约定一致、深度符号与 "
             "targetbody 的独立测量对得上；intrinsics 全部 `measured_from_model_and_xml`"
             "（fovy 取自模型 + XML 原文行留证）",
             ruling_ref="裁定 64（引用带文件身份）；B2 对 ABC-130k 25 条不自洽 intrinsics 的同族修正",
             red_when=("投影落在 8 px 紧半径之外 / 找不到红占优像素 / 多于一种约定紧命中（歧义）/ "
                       "两相机约定不一致 / 深度符号与 targetbody 测量打脸 / intrinsics 非实测"),
             mutation_expected_red=False)


# ========================================================================== 溯源 / 体积
def self_verify_evidence(path: Path) -> dict:
    """裁定 50.2：计数类主张必须同批落 (mtime, 计数, 命令原文)。"""
    out = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        out["status"] = "UNJUDGED"
        out["why"] = "自证产物不存在 ⇒ 不拿 0 填充、不当作通过（三值纪律）"
        return out
    st = path.stat()
    d = json.loads(path.read_text())
    mod_now = ROOT / "scripts" / "b2_s1_scripted_expert.py"
    mi = d.get("module_identity") or {}
    sha_then = mi.get("sha256_12")
    sha_now = sha12(mod_now)
    out.update({"sha256_12": sha12(path), "bytes": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, CST).isoformat(timespec="seconds"),
                "command_verbatim": " ".join(d.get("args") or []) or None,
                "generated_at": d.get("generated_at"),
                "summary": d.get("summary"),
                "n_rows": len(d.get("rows") or []),
                "generator": "scripts/b2_s1_scripted_expert.py --selftest",
                "generator_sha256_12_now": sha_now,
                "generator_sha256_12_when_evidence_made": sha_then,
                "evidence_matches_current_module": (None if sha_then is None
                                                    else bool(sha_then == sha_now)),
                "horizon_accounting": {k: (d.get("summary") or {}).get(k) for k in
                                       ("n_steps_min", "n_steps_max", "n_steps_mean",
                                        "settle_steps_dropped", "n_frames_recorded_max",
                                        "registered_max_episode_steps",
                                        "n_over_registered_horizon", "horizon_ruling")},
                "note": ("自证在**每次改动专家模块后**都重跑（裁定 50.2/72：计数类主张必须同批落 "
                         "(mtime,计数,命令原文)，且证据要能对上当时那份模块）。历史产物一律保留不改写"
                         "（裁定 35.1），互为重复性对照。")})
    s = d.get("summary") or {}
    out["success_rate"] = (s.get("success") / s.get("total")) if s.get("total") else None
    out["status"] = "measured"
    if sha_then is None:
        out["status"] = "UNJUDGED"
        out["why"] = ("自证产物里没有 `module_identity.sha256_12` ⇒ 无法确认它是用**现在这份**"
                      "专家模块跑出来的（陈旧证据不能充数，三值纪律）")
    elif sha_then != sha_now:
        out["status"] = "STALE_EVIDENCE"
        out["why"] = ("自证产物由 sha=%s 的模块跑出，而现在 import 的是 sha=%s ⇒ 证据已过期，"
                      "必须重跑（裁定 72：selftest 必须真走取数路径）" % (sha_then, sha_now))
    return out


def volume_accounting(root: Path, allowed_prefixes: Sequence[str]) -> dict:
    total = 0
    n_files = 0
    outside: List[str] = []
    per_top: Dict[str, int] = {}
    for p in root.rglob("*"):
        if p.is_file():
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            total += sz
            n_files += 1
            rel = str(p.relative_to(root)).split("/")[0]
            per_top[rel] = per_top.get(rel, 0) + sz
    for p in ctx_written_paths:
        if not any(str(p).startswith(a) for a in allowed_prefixes):
            outside.append(str(p))
    return {"root": str(root), "n_files": n_files, "bytes_written": total,
            "gib_written": round(total / (1024 ** 3), 4), "per_top_level": per_top,
            "declared_under_10gib": total < 10 * 1024 ** 3,
            "paths_outside_write_area": outside,
            "write_area_allowed_prefixes": list(allowed_prefixes),
            "trash_policy": "不用 rm；要清旧产物走 --trash（移到 %s）" % RECYCLE_BIN}


ctx_written_paths: List[Path] = []
ctx_recycled: List[str] = []


C2_OUTPUT_GUARD = ROOT / "scripts" / "c2_driver_output_guard.py"


def guard_snapshot_before_overwrite(ds_root: Path, out_root: Path,
                                    manifest_name: str) -> dict:
    """裁定 85.6-1（§18.6-1）：覆写之前先给旧产物留 **before 影像**，并把旧 manifest 一并移进回收站。

    事故：00:26:58 那版 selftest 的 `demo_manifest.json` **灭失** ⇒ `unbacked_citation` 第 2 起。
    根因：旧版只在 `--trash` 里移走 `team_form/data` 与 `pi05_lerobot` 两个子树，而 manifest 写在
    `ds_root/<manifest_name>`（两个子树之外）⇒ 重跑时被**就地覆写**，旧字节无处可寻
    （`recycle_bin/` 里只有那两个子树，manifest 本体不在其中）。

    处置（按 D 的裁定，**不新写守卫**）：
    ① 复用 C2 的 `scripts/c2_driver_output_guard.py` 的 **`snapshot` 半段**留 before 影像
       （字节 + sha256-12 + mtime + 全子树 stat 索引）。**只跑 snapshot、不跑 restore**：
       C2 守卫的 `is_owned()` 只处置 `c_*` 前缀，`restore` 对本线产物不适用（E 已示范同一用法）。
    ② 之后把旧 manifest **移进回收站**（`trash_if_exists`）⇒ 即使①失败，旧字节也还在。
    """
    doc = {"ruling": "裁定 85.6-1（§18.6-1）", "guard_reused_not_rewritten": True,
           "guard_path": str(C2_OUTPUT_GUARD.relative_to(ROOT)),
           "guard_sha256_12": (sha12(C2_OUTPUT_GUARD) if C2_OUTPUT_GUARD.exists() else None),
           "guard_lines": (len(C2_OUTPUT_GUARD.read_text(encoding='utf-8').splitlines())
                           if C2_OUTPUT_GUARD.exists() else None),
           "guard_mtime": _mtime(C2_OUTPUT_GUARD),
           "halves_used": ["snapshot"],
           "halves_not_used": {"restore": ("C2 守卫的 `is_owned()` 只处置 `c_*` 前缀 ⇒ 对 b2 产物"
                                           "不适用（E 已示范同一用法并写明为何不跑 restore）")},
           "ds_root": str(ds_root), "manifest_name": manifest_name}
    manifest_path = ds_root / manifest_name
    doc["old_manifest_existed"] = manifest_path.exists()
    if not manifest_path.exists():
        doc["status"] = "N_A_no_preexisting_manifest"
        return doc
    doc["old_manifest_sha256_12_before"] = sha12(manifest_path)
    doc["old_manifest_generated_at"] = None
    try:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        doc["old_manifest_generated_at"] = old.get("generated_at")
    except Exception as e:                                       # noqa: BLE001
        doc["old_manifest_read_error"] = "%s: %s" % (type(e).__name__, e)
    gdir = out_root / "overwrite_guard"
    gdir.mkdir(parents=True, exist_ok=True)
    rel_manifest = str(manifest_path.relative_to(ROOT))
    declared = {"declared": {rel_manifest: {"declared_by": "scripts/b2_s1_generate_dataset.py",
                                            "line": "b2"}}}
    dpath = note_write(gdir / "declared.json")
    dpath.write_text(json.dumps(declared, ensure_ascii=False, indent=1), encoding="utf-8")
    py = "/opt/conda/bin/python3" if Path("/opt/conda/bin/python3").exists() else sys.executable
    cmd = [py, str(C2_OUTPUT_GUARD), "snapshot", "--root", str(ROOT),
           "--declared", str(dpath), "--before", str(gdir / "before"),
           "--out", str(gdir / "snapshot.json"),
           "--scan-root", str(ds_root.relative_to(ROOT))]
    doc["guard_command_verbatim"] = " ".join(cmd)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        doc.update({"guard_rc": p.returncode, "guard_stdout": p.stdout.strip()[:800],
                    "guard_stderr": p.stderr.strip()[:800],
                    "status": ("PASS_before_image_taken" if p.returncode == 0
                               else "WARN_guard_failed_manifest_still_trashed")})
    except Exception as e:                                       # noqa: BLE001
        doc.update({"guard_rc": None, "status": "WARN_guard_error_manifest_still_trashed",
                    "guard_error": "%s: %s" % (type(e).__name__, e)})
    if (gdir / "snapshot.json").exists():
        try:
            snap = json.loads((gdir / "snapshot.json").read_text(encoding="utf-8"))
            doc["guard_snapshot_summary"] = {
                "n_declared": snap.get("n_declared"), "n_snapshotted": snap.get("n_snapshotted"),
                "n_tree_files": snap.get("n_tree_files"),
                "before_image": [e.get("before_image") for e in (snap.get("index") or [])],
                "sha256_12": [e.get("sha256_12") for e in (snap.get("index") or [])]}
        except Exception as e:                                   # noqa: BLE001
            doc["guard_snapshot_read_error"] = "%s: %s" % (type(e).__name__, e)
    return doc


def trash_if_exists(path: Path, tag: str) -> Optional[str]:
    """**不用 `rm`**（D 的硬纪律）：要清旧产物就移进回收站，并把移动记进产物。

    为什么必须清：① `LeRobotDataset.create` 对已存在的 root 直接 `FileExistsError`
    （`lerobot_dataset.py:518 obj.root.mkdir(exist_ok=False)`，B2 22:5x 实测）；
    ② 团队形态目录的 episode id 是 `uuid5(direction|seed|dt)` 确定性的 ⇒ 重跑会**就地覆写**，
    而上一轮若用了不同 seed，旧 episode 会赖着不走 ⇒ 帧数账与 manifest 对不上（裁定 68 的覆写教训）。
    """
    path = Path(path)
    if not path.exists():
        return None
    RECYCLE_BIN.mkdir(parents=True, exist_ok=True)
    dst = RECYCLE_BIN / ("b2_s1_%s_%s" % (tag, datetime.now(CST).strftime("%Y%m%d_%H%M%S_%f")))
    shutil.move(str(path), str(dst))
    print("[trash] %s → %s（不用 rm）" % (path, dst), flush=True)
    return str(dst)


def note_write(p: Path) -> Path:
    ctx_written_paths.append(Path(p))
    return Path(p)


# ========================================================================== 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="runs/vla/b2_sim_demo_bidir_20260930")
    ap.add_argument("--out-subdir", default="")
    ap.add_argument("--stage", default="custom", choices=["pilot", "formal", "custom"])
    ap.add_argument("--n-seeds", type=int, default=None, help="每方向集数（pilot=5 / formal=20）")
    ap.add_argument("--seed0", type=int, default=2000)
    ap.add_argument("--directions", default="both", choices=["both", "forward", "reverse"])
    ap.add_argument("--dt", type=float, default=MAINLINE_DT)
    ap.add_argument("--mutation", default="none", choices=list(MUTATION_ALL),
                    help=("变异体（牙）。`replay-state-1lsb` = 状态只改 1 个 ULP ⇒ G4 必须红（裁定 85.5 牙②）；"
                          "`replay-image-pixel-only` = 只改像素、状态不动 ⇒ **必须仍绿**（牙③）；"
                          "`replay-image-over-tolerance` 是它的旧名别名（§17-6 时代它期望 G4b 红，"
                          "裁定 85.5 之后期望值改为「不许红」）"))
    ap.add_argument("--no-image-repeat-render", action="store_true",
                    help=("省掉「同状态连渲两次」的图像确定性比对（G4b/G4c/G4d 转 N_A）。默认开着："
                          "它是裁定 82⑤-3 要求的实测差异登记，代价 ≈ +1 次渲染/帧"))
    ap.add_argument("--skip-lerobot", action="store_true")
    ap.add_argument("--skip-team", action="store_true")
    ap.add_argument("--no-norender-pass", action="store_true",
                    help="省掉第三个 pass（渲染不变性对照）；默认开着，因为它是 G4 的隔离证据")
    ap.add_argument("--selftest", action="store_true", help="1+1 集、全闸、含 lerobot 往返")
    ap.add_argument("--selftest-cotenant-detector", action="store_true",
                    help=("只跑「共租探测器的**五条**牙」（裁定 85.6-2 + **裁定 96.1-③ / RR-B2-18**）"
                          "后退出：不起渲染、不产数据集、不上卡（牙① 只持 /dev/nvidiactl 的 fd）。"
                          "牙① 持 fd 的进程 ⇒ 必 true；牙② pcpu≈0 的空闲 bash ⇒ 必 false；"
                          "牙③ 执行位是 scripts/b2_*.py 且 pcpu>1%% 但不碰 GPU ⇒ 必 true；"
                          "牙④ 只在**文本位**提到关键字的忙 CPU 进程 ⇒ 必 false（且修法前必 true）；"
                          "牙⑤ 执行位真是他线脚本 ⇒ 必 true（网③ 反漏检）。"
                          "同一次调用还会跑与 E/F 参考实现的对齐探针并写 "
                          "CMDLINE_CALIBER_ALIGNMENT.json；两向缺一向或对账不过 ⇒ 退出码 3"))
    ap.add_argument("--selftest-cmdline-caliber", action="store_true",
                    help=("只跑「网③/信号② 判据与 E 的参考实现 + F 的 `EXEC_FORM_RE` 出处现取对账」"
                          "（裁定 46.4 副本漂移防护 + 裁定 93.8 两向）后退出：**纯 CPU**，不起证人进程、"
                          "不读 /proc、不碰 GPU。产物 = <out>/CMDLINE_CALIBER_ALIGNMENT.json"))
    ap.add_argument("--no-overwrite-guard", action="store_true",
                    help=("覆写前不调用 C2 的输出面守卫留 before 影像（默认调用；裁定 85.6-1）。"
                          "旧 manifest 无论如何都会被 `--trash` 进回收站，不会被就地覆写灭失"))
    ap.add_argument("--self-verify-json",
                    default="runs/vla/b2_sim_demo_bidir_20260930/probe/"
                            "expert_selfverify_40x2_postpatch2.json")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    ap.add_argument("--manifest-name", default="demo_manifest.json")
    ap.add_argument("--trash", default=None, help="把已存在的输出子目录移到回收站（不用 rm）")
    ap.add_argument("--allow-cotenant", action="store_true",
                    help="明知卡上有别线 GPU 进程仍起跑（产物会被标 contaminated，只作趋势参考）")
    ap.add_argument("--keep-existing", action="store_true",
                    help="不清旧产物（默认清：lerobot 的 create 要求 root 不存在，团队形态目录重跑会覆写）")
    a = ap.parse_args()

    # ---- 裁定 85.6-2 的三条牙：探测器自证（**必须在 GPU 硬闸之前**：它自己会造 fd 持有者）----
    if a.selftest_cmdline_caliber:
        out_root = ROOT / a.out
        out_root.mkdir(parents=True, exist_ok=True)
        doc = cmdline_caliber_alignment_probe(
            note_write(out_root / "CMDLINE_CALIBER_ALIGNMENT.json"))
        print(json.dumps({"artifact": str(out_root / "CMDLINE_CALIBER_ALIGNMENT.json"),
                          "ok": doc.get("ok"), "verdict": doc.get("verdict"),
                          "measurement_status": doc.get("measurement_status"),
                          "legs_all_ok": doc.get("legs_all_ok"),
                          "n_rows": doc.get("n_rows"),
                          "not_ok_rows": [r["id"] for r in (doc.get("rows") or [])
                                          if not r.get("ok")],
                          "references": doc.get("references")},
                         ensure_ascii=False, indent=1, default=_json_default))
        return int(doc.get("exit_code") or 0)

    # ---- 裁定 85.6-2 的五条牙：探测器自证（**必须在 GPU 硬闸之前**：它自己会造 fd 持有者）----
    if a.selftest_cotenant_detector:
        return cotenant_detector_teeth(ROOT / a.out)

    # ---- 裁定 73 硬闸：起跑前实测 GPU；有外来进程就**拒绝起跑**（除非显式 --allow-cotenant）----
    global ctx_gpu_preflight
    ctx_gpu_preflight = gpu_preflight()
    _check_quiet_window()
    if not ctx_gpu_preflight["idle"] and not a.allow_cotenant:
        refuse = {
            "artifact": "b2_s1_refused_to_start_gpu_busy",
            "generated_at": now_iso(),
            "command_verbatim": " ".join([sys.executable] + sys.argv),
            "preflight": ctx_gpu_preflight,
            "quiet_window": ctx_quiet_window,
            "reason": ("起跑那一刻**三网并查**命中外来（网①compute-apps %d / 网②/dev/nvidia* fd %d / "
                       "网③cmdline %d）⇒ 按裁定 73 + 85.6-2 与单卡优先权"
                       "（**A2 > B2 > C2 > E**，裁定 85.7），B2 不起 GPU 作业。要跑请加 "
                       "`--allow-cotenant`，但产物会被标 `contaminated_by_cotenant`，"
                       "只可作趋势参考、不得作权威口径。"
                       % (ctx_gpu_preflight["net_hits"]["net1_compute_apps"],
                          ctx_gpu_preflight["net_hits"]["net2_nvidia_fd_holders"],
                          ctx_gpu_preflight["net_hits"]["net3_cmdline"])),
            "incident_reference": "docs/b2_gpu_window_incident_and_rr_20260930.md（B2 曾污染 A2 的 quiet_window_rep5）",
            "detector": ctx_gpu_preflight.get("detector"),
            "policy_executed": False, "not_a_capability_claim": True}
        rp = ROOT / a.out
        rp.mkdir(parents=True, exist_ok=True)
        op = note_write(rp / "refused_gpu_busy_%s.json"
                        % datetime.now(CST).strftime("%Y%m%d_%H%M%S"))
        op.write_text(json.dumps(refuse, ensure_ascii=False, indent=1, default=_json_default),
                      encoding="utf-8")
        print("[refuse] GPU 非空载（三网命中 %s），B2 不起 GPU 作业（裁定 73 + 85.6-2）：%s"
              % (ctx_gpu_preflight["net_hits"],
                 [(h["net"], h["pid"], h.get("detail"))
                  for h in ((ctx_gpu_preflight["three_net"]["net1_compute_apps"] and
                             [{"net": "net1", "pid": x["pid"], "detail": x["used_memory_mib"]}
                              for x in ctx_gpu_preflight["three_net"]["net1_compute_apps"]]) or [])
                  + [{"net": "net2", "pid": x["pid"], "detail": x["nvidia_devs"]}
                     for x in ctx_gpu_preflight["three_net"]["net2_nvidia_fd_holders"]]
                  + [{"net": "net3", "pid": x["pid"], "detail": x.get("gpu_intent")}
                     for x in ctx_gpu_preflight["three_net"]["net3_cmdline_hits"]]]),
              flush=True)
        print("[refuse] 证据落盘：%s" % op, flush=True)
        return 4          # 与"闸判红"的 3 区分开：4=没起跑（GPU 非空载），3=跑完了但有红
    # 硬闸过了才起 GL 上下文（懒加载、幂等）
    _init_gl_identity()

    if a.selftest:
        a.n_seeds = a.n_seeds or 1
        a.out_subdir = a.out_subdir or "selftest"
    if a.stage == "pilot":
        a.n_seeds = a.n_seeds or 5
    elif a.stage == "formal":
        a.n_seeds = a.n_seeds or 20
    n_seeds = a.n_seeds or 1
    dt = 0.02 if a.mutation == "dt-back-to-50hz" else a.dt

    out_root = ROOT / a.out
    ds_root = out_root / (a.out_subdir or "dataset")
    team_root = ds_root / "team_form" / "data"
    lr_root = ds_root / "pi05_lerobot"
    sidecar = ds_root / "sidecar"
    ds_root.mkdir(parents=True, exist_ok=True)
    recycled: List[str] = []
    overwrite_guard: Optional[dict] = None
    if a.trash:
        for t in (ROOT / a.trash if not Path(a.trash).is_absolute() else Path(a.trash),):
            r = trash_if_exists(t, "explicit_" + t.name)
            if r:
                recycled.append(r)
    # 幂等：重跑同一 out-subdir 时，团队形态目录与 lerobot root 必须**先清后写**（理由见 trash_if_exists）
    if not a.keep_existing:
        # 裁定 85.6-1（§18.6-1）：**`demo_manifest.json` 也必须纳入** —— 旧版只移走 `team_form/data`
        # 与 `pi05_lerobot` 两个子树，而 manifest 写在它们**外面**（`ds_root/<manifest_name>`）
        # ⇒ 重跑时被就地覆写、旧字节灭失（00:26:58 那版 selftest manifest = `unbacked_citation` 第 2 起）。
        # 先用 C2 的守卫（只读复用、不新写）留 before 影像，再移进回收站 ⇒ 两条腿都不会丢。
        if not a.no_overwrite_guard:
            overwrite_guard = guard_snapshot_before_overwrite(ds_root, out_root, a.manifest_name)
        for t, tag in ((ds_root / a.manifest_name, "demo_manifest"),
                       (sidecar, "sidecar"),
                       (team_root, "team_form_data"), (lr_root, "pi05_lerobot")):
            r = trash_if_exists(t, tag)
            if r:
                recycled.append(r)
        # `sidecar` 也一并清：它按集写 metadata，旧一轮若用了不同 seed，残留文件会让帧数账对不上
        #（与 `trash_if_exists` 文档里团队形态目录 uuid5 覆写的问题同族）。
    team_root.mkdir(parents=True, exist_ok=True)
    sidecar.mkdir(parents=True, exist_ok=True)   # 上面可能刚把旧 sidecar 移进回收站 ⇒ 重建
    ctx_recycled.extend(recycled)

    t_start = time.time()
    prov_before = {"loadavg": loadavg3(), "cpu_stat": cpu_stat(), "nvidia_smi": nvidia_smi(),
                   "three_net": card_busy_three_net(strict=True),
                   "cotenant_processes": foreign_gpu_line_processes(), "ts": now_iso()}

    # ---- A2 契约（运行时读，逐字比对；裁定 64：引用带文件身份）----
    contract_doc = json.loads(A2_CONTRACT.read_text())
    contract = {"task": contract_doc["args"]["task"],
                "camera_map": contract_doc["observation"]["camera_map"],
                "image_shape": contract_doc["observation"]["image_shape"],
                "state_raw_14d": contract_doc["observation"]["state_raw_14d"],
                "image_size": contract_doc["args"]["image_size"],
                "env_id": contract_doc["args"]["env_id"],
                "generated_at": contract_doc["generated_at"]}
    cam_map = contract["camera_map"]
    if cam_map != PI05_KEY_DEFAULT:
        print("[warn] A2 契约的 camera_map 与本脚本默认值不同，以契约为准：%s" % cam_map)
    task_text = {"forward": contract["task"], "reverse": TASK_TEXT_PROPOSED["reverse"]}
    if task_text["forward"] != TASK_TEXT_PROPOSED["forward"]:
        task_text["forward"] = contract["task"]
    shim = {"path": "envs/gym_aloha_shim.py",
            "sha256_12": (sha12(SHIM_PATH) if SHIM_PATH.exists() else None),
            "representation_version": None, "MAINLINE_DT": MAINLINE_DT,
            "MAINLINE_SUBSTEPS": 17, "MAINLINE_HZ": MAINLINE_HZ}
    if SHIM_PATH.exists():
        sys.path.insert(0, str(ROOT))
        from envs import gym_aloha_shim as shim_mod
        shim["representation_version"] = shim_mod.REPRESENTATION_VERSION
        shim["live_control_hz"] = shim_mod.MAINLINE_HZ
        shim["qc_band"] = list(shim_mod.QC_BAND_HZ)
        shim["per_step_budget_ms"] = shim_mod.PER_STEP_BUDGET_MS

    directions = ["forward", "reverse"] if a.directions == "both" else [a.directions]
    episodes: List[dict] = []
    ds = None
    if not a.skip_lerobot:
        ds = create_lerobot(lr_root, cam_map)
    frame_offset = 0
    roundtrip: Dict[str, List[Tuple[int, np.ndarray]]] = {}
    fps_str = fps_rational(dt)
    hz_measured = round(1.0 / dt, 6)

    for d in directions:
        for i in range(n_seeds):
            seed = a.seed0 + i
            t0 = time.time()
            rec = generate_episode(d, seed, dt, mutation=(a.mutation if a.mutation != "none"
                                                          else None),
                                   contract_state14=contract["state_raw_14d"],
                                   do_replay_render=not a.skip_team or not a.skip_lerobot,
                                   do_replay_norender=not a.no_norender_pass,
                                   image_repeat_render=not a.no_image_repeat_render)
            rp = rec["replay_render"] or rec["replay_norender"]
            ep_id = None
            team_info = None
            if not a.skip_team:
                team_info = write_team_episode(
                    team_root / "train", rec, task_text[d],
                    rp["intrinsics"]["team_head"], rp["w2c_head"], rp["w2c_diag"],
                    a.ffmpeg, a.ffprobe,
                    {"control_hz_measured": hz_measured, "dt": dt,
                     "episode_horizon_s": round(300 * dt, 4),
                     "episode_horizon_steps_registered": 300,
                     "shim": shim, "representation_version": REPRESENTATION_VERSION,
                     "a2_contract": {"path": str(A2_CONTRACT), "sha256_12": sha12(A2_CONTRACT),
                                     "task": contract["task"], "camera_map": cam_map},
                     "gl_identity": ctx_gl_identity, "activation_env": ctx_activation,
                     "git": ctx_git, "generator_sha256_12": sha12(SCRIPT)},
                    fps_str=fps_str)
                ep_id = team_info["ep_id"]
                note_write(Path(team_info["path"]))
            if ep_id is None:
                ep_id = "episode_%s" % uuid.uuid5(uuid.NAMESPACE_OID, "b2-s1|%s|%d|%s" % (
                    d, seed, dt))
            if ds is not None:
                add = add_episode_to_lerobot(ds, rec, cam_map, task_text[d],
                                             frame_offset=frame_offset)
                for k, v in add["pixels_kept_for_roundtrip"].items():
                    roundtrip.setdefault(k, []).extend(v)
                frame_offset += add["n_frames"]
            metrics = episode_metrics(rec, team_info, contract)
            sc = sidecar / ("%s.json" % ep_id)
            sc.write_text(json.dumps({
                "ep_id": ep_id, "direction": d, "direction_label": DIRECTION_LABEL[d],
                "seed": seed, "dt": dt, "control_hz_measured": hz_measured,
                "task_info": task_text[d],
                "n_steps_expert": rec["expert"]["n_steps"], "settle_steps_dropped": rec["settle"],
                "n_frames_recorded": rp["n_frames"],
                "phase_timeline": _phase_timeline(rec["phases"], rec["settle"]),
                "phase_diag": rec["expert"]["phase_diag"],
                "plan_diag": rec["expert"]["plan_diag"],
                "judge_verdict": rp["judge"],
                "judge_verdict_expert_pass": rec["expert"]["judge"],
                "judge_config": rp["judge"].get("config"),
                "replay_comparison": rec["replay_cmp"],
                "box_spawn_xyz": rec["expert"]["box_spawn_xyz"],
                "box_rest_after_settle_xyz": rec["expert"]["box_rest_after_settle_xyz"],
                "box_trajectory_xyz_every_10": [[round(float(v), 5) for v in b]
                                                for b in np.asarray(rp["rec"]["box"]).reshape(-1, 3)[::10]],
                "env_reward_trace_every_10": rp["rec"]["env_reward"][::10],
                "grip_cmd_trace_every_10": {"left": [round(float(x[6]), 5) for x in
                                                     np.asarray(rp["rec"]["action14"]).reshape(-1, 14)[::10]],
                                            "right": [round(float(x[13]), 5) for x in
                                                      np.asarray(rp["rec"]["action14"]).reshape(-1, 14)[::10]]},
                "finger_spread_trace_every_10": {s: [round(v, 5) for v in vs[::10]]
                                                 for s, vs in rp["rec"]["finger_spread"].items()},
                "intrinsics_per_slot": rp["intrinsics"],
                "intrinsics_projection_check": rp["intrinsics_projection_check"],
                "w2c_head": rp["w2c_head"], "w2c_diag": rp["w2c_diag"],
                "w2c_static": rp["w2c_static"],
                "metrics": {k: v for k, v in metrics.items() if k != "bitwise"},
                "wall_s": {"expert_pass": rec["t_expert_s"], "replay_pass": rp["wall_s"],
                           "total": round(time.time() - t0, 2)},
                "not_a_capability_claim": True, "policy_executed": False,
            }, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8")
            note_write(sc)
            episodes.append({"ep_id": ep_id, "direction": d, "seed": seed, "dt": dt,
                             "task_text": task_text[d], "team": team_info, "metrics": metrics,
                             "replay_cmp": rec["replay_cmp"], "sidecar": str(sc),
                             "wall_s": round(time.time() - t0, 2),
                             # G16 的**小证据**：只留判定结果/投影坐标/相机 diag，
                             # 图像数组（rec["images"]）绝不进 manifest。
                             "_s1_visual": {
                                 "pass_used": ("replay_render" if rec["replay_render"] is not None
                                               else "replay_norender"),
                                 "intrinsics_projection_check": rp["intrinsics_projection_check"],
                                 "intrinsics_status": {
                                     sl: {"status": it.get("status"), "why": it.get("why"),
                                          "camera": it.get("camera"), "h": it.get("h"),
                                          "w": it.get("w"), "fovy_deg": it.get("fovy_deg")}
                                     for sl, it in (rp["intrinsics"] or {}).items()},
                                 "w2c_static_diag": {c: v["diag"] for c, v in
                                                     (rp.get("w2c_static") or {}).items()},
                                 "images_serialized": False}})
            v = metrics["verdict_replay_render"] or metrics["verdict_replay_norender"]
            print("[ep %2d] %s seed=%d %-8s frames=%3d verdict=%-8s rew_term=%s wall=%.1fs"
                  % (len(episodes), d, seed, "", metrics["n_frames"], v,
                     metrics["env_reward_terminal"], time.time() - t0), flush=True)

    lr_verify = None
    if ds is not None:
        ds.finalize()
        lr_verify = verify_lerobot(lr_root, len(episodes), frame_offset, roundtrip)
        note_write(lr_root)

    if not a.skip_team:
        _write_team_dataset_manifest(team_root, episodes, ds_root, contract, task_text, a, shim,
                                     hz_measured, fps_str)
    prov_after = {"loadavg": loadavg3(), "cpu_stat": cpu_stat(), "nvidia_smi": nvidia_smi(),
                  "three_net": card_busy_three_net(strict=True),
                  "cotenant_processes": foreign_gpu_line_processes(), "ts": now_iso()}
    vol = volume_accounting(ds_root, [str(ROOT / "runs" / "vla")])
    sv = self_verify_evidence(ROOT / a.self_verify_json)

    ctx = {"mutation": a.mutation, "n_required_per_direction": n_seeds, "lerobot_verify": lr_verify,
           "gl_identity": ctx_gl_identity,
           "contract": contract, "contract_sha12": sha12(A2_CONTRACT), "shim": shim,
           "episode_horizon_s": round(300 * dt, 4), "task_text": task_text, "cam_map": cam_map,
           "volume": vol, "self_verify": sv,
           "d_naming_discrepancy": {
               "issue": "D 在 §13.8-2 写键名为 `observation.images.{top,left_wrist,right_wrist}`，"
                        "而 A2 契约（**实测**自 π₀.₅ processors）是 "
                        "`{base_0_rgb←angle, left_wrist_0_rgb←left_wrist, right_wrist_0_rgb←right_wrist}`",
               "b2_choice": "以 A2 契约为准（读实现不读声明，裁定 9.1/64）；base 槽用 **angle** 相机",
               "impact": "键名/相机若照 D 的字面写，A2 的 S3 训练与 C2 的 obs 键覆盖闸会对不上 ⇒ 报 D 更正",
               "evidence": {"contract_path": str(A2_CONTRACT), "contract_sha256_12": sha12(A2_CONTRACT),
                            "contract_keys": cam_map,
                            "d_text": "rl_harness_supervision/d_handoff_to_b2_20260929.md:481"}},
           "provenance_required_fields": ctx_required_fields(),
           "provenance_get": None}
    prov_doc = _provenance(a, contract, task_text, cam_map, shim, prov_before, prov_after, vol,
                           sv, episodes, lr_verify, hz_measured, fps_str, dt)
    ctx["provenance_get"] = lambda k: _dig(prov_doc, k)

    reps = Report()
    run_gates(reps, eps=episodes, ctx=ctx)

    # 顶层四元组要的两个人（裁定 78.2 / 85.5）：**实测渲染器**决定像素侧是否参与判定；
    # 像素超带的槽位**汇总到顶层**（登记项，不判红），免得下游要翻进 checks 才看得见。
    nvidia_arm_now = ((ctx.get("gl_identity") or {}).get("renderer_class") == "nvidia_gpu")
    pix_exc_slots = sorted({
        str(r.get("slot")) for c in reps.checks
        if str(c.get("id", "")).startswith(("G4b", "G4d"))
        for r in (((c.get("observed") or {}).get("pixel_register_exceedances")) or [])})
    # 两种「超带」要分开：**超裁定 83.4 的三容差**（数值上更严重）与**只是不到全帧逐位**
    #（egl 上是常态，E 的 n=5 与 B2 的首手实测都证过）。混在一个列表里会让下游把常态读成异常。
    pix_tol_slots = sorted({
        str(r.get("slot")) for c in reps.checks
        if str(c.get("id", "")).startswith(("G4b", "G4d"))
        for r in (((c.get("observed") or {}).get("pixel_register_exceedances")) or [])
        if r.get("exceeded_ruling_83_4_tolerance")})
    ctx_mutation_tooth_ok = True

    manifest = {
        "artifact": "b2_s1_demo_manifest",
        "generated_at": now_iso(),
        "generator": "scripts/b2_s1_generate_dataset.py",
        "generator_sha256_12": sha12(SCRIPT),
        "expert_module": "scripts/b2_s1_scripted_expert.py",
        "expert_module_sha256_12": sha12(ROOT / "scripts" / "b2_s1_scripted_expert.py"),
        "args": vars(a),
        "command_verbatim": " ".join([sys.executable] + sys.argv),
        "stage": a.stage, "mutation": a.mutation,
        "dataset_kind": DATASET_KIND, "data_kind": DATA_KIND,
        "representation_version": REPRESENTATION_VERSION,
        "not_a_capability_claim": True, "policy_executed": False, "capability_claim": False,
        "success_metrics_collected": True,
        "success_metrics_scope": ("**脚本专家在仿真里的搬运成功率**，用于 S1 判据 4（专家自证）。"
                                  "这不是任何 policy 的能力结论（裁定 46：没跑过 policy 就不许声称能力）"),
        "n_proposed": {"pilot": 5, "formal": 20, "d_prior_suggestion": "先导 5 集 + 正式 20 集（裁定 66）",
                       "status": "proposed_pending_d"},
        "n_generated_per_direction": n_seeds,
        "directions": directions, "seed0": a.seed0,
        "frequency": {"DT": dt, "control_hz_measured": hz_measured, "n_sub_steps": 17,
                      "model_timestep_s": 0.002, "episode_horizon_steps_registered": 300,
                      "episode_horizon_s": round(300 * dt, 4),
                      "fps_rational_in_video_container": fps_str,
                      "qc_band_hz": list(QC_FPS_BAND),
                      "per_step_budget_ms": 34.0,
                      "nominal_anchor_hz_not_for_judgment": 30.0,
                      "ruling": "裁定 53（29.4118 Hz 为判据锚、30.0 降名义锚）/ 裁定 65-2（300 步维持）"},
        "shim": shim,
        "versions": ctx_versions,
        "venv": sys.executable,
        "activation_env": ctx_activation,
        "gl_identity": ctx_gl_identity,
        "git": ctx_git,
        "load_before": prov_before, "load_after": prov_after,
        "nr_throttled_delta": _throttled_delta(prov_before, prov_after),
        "cotenant_evidence": dict(
            contamination_verdict(prov_before, prov_after, ctx_gpu_preflight,
                                  _throttled_delta(prov_before, prov_after)),
            **{"before_proc_inventory": prov_before["cotenant_processes"],
               "after_proc_inventory": prov_after["cotenant_processes"],
               "preflight_gpu_guard": ctx_gpu_preflight,
               "quiet_window": ctx_quiet_window}),
        "route_compliance": {
            "ruling": "裁定 66 §13.5：EE 模型只作 IK oracle → 录 qpos → 在关节模型里用它自己的 "
                      "actuator 重放，并在关节模型里采 3 相机图像与 14 维动作；不允许在 EE 模型内直接采示范",
            "b2_implementation": "**物理与 IK 都在关节模型里**（bimanual_viperx_transfer_cube.xml，"
                                 "nu=16，用它自己的 position actuator 执行）；IK 是 B2 自写的"
                                 "运动学 DLS 规划器（KinPlanner，独立 MjData、mj_forward 不积分），"
                                 "**EE 模型一个字节都没加载**",
            "deviation_from_literal_route": "没有用 EE 模型当 oracle",
            "deviation_reasons_measured": [
                "① EE 的 weld 在**复位瞬间**就违反约束：`eq_data[3:6]` 带编译期 anchor2=±0.134706 m，"
                "而上游 `initialize_robots` 把 mocap 写成复位后的 gripper_link 位姿 ⇒ 第一步臂被猛拉 "
                "13.5 cm（probe/probe4.json → E2_zero_transient_init）",
                "② 右臂解析反解**发散**：位置残差 0.2469 m、姿态残差 2.376 rad（左臂 0.0013 m）；"
                "根因 `assets/vx300s_right.xml:3` 的 `euler=\"0 0 3.1416\"`（右臂基座绕 z 反装 180°）"
                "⇒ 两侧 weld 的 `relpose_quat` 不同构（左 [1,0,0,0]、右 w≈0/z≈1）",
                "③ probe2 实测 mocap 阶跃后 weld **不收敛反而变大**：`vx300s_right/gripper_link` 残差 "
                "step1 0.0872 m → step50 0.1359 m",
                "④ EE 模型 `nu=4` 且 4 个 actuator 名全为空串 ⇒ 整条臂只靠 soft weld 吊着（无臂 actuator），"
                "稳态下垂不可消除",
                "⑤ `tasks/sim_end_effector.py:120` 的 get_observation **无条件渲染** ⇒ EE 通道在 "
                "`MUJOCO_GL=disable` 下不可用（probe3 traceback 实证）"],
            "satisfies_ruling_purpose": [
                "示范的动力学 = 关节模型自己的 actuator 动力学（与 S5 评测同一套）⇒ 无训练/评测动力学错配",
                "存 14 维动作、不存 16 维 qpos（裁定 66 §13.7-3）",
                "3 相机图像在关节模型里渲（§13.8-2）",
                "重放可复现（§13.8-4，G4 逐位相同）"],
            "d_h1_verdict": ctx_d_h1_verdict,
            "status": "reported_to_d_for_confirmation"},
        "lerobot": lr_verify,
        "team_form": {"root": str(team_root), "video_slots": VIDEO_SLOTS,
                      "video_resolution": [TEAM_VIDEO_H, TEAM_VIDEO_W],
                      "metadata_name": METADATA_NAME,
                      "dimension_config_keys": [k for k, _ in DIMENSION_CONFIG],
                      "qc_runner": "scripts/b2_run_team_qc.py（只读调用团队 vla_pipeline）"},
        "volume": vol,
        "recycled_paths_not_rm": ctx_recycled,
        "overwrite_guard": overwrite_guard,
        "self_verify": sv,
        "episodes": [{k: v for k, v in e.items() if k != "replay_cmp"} for e in episodes],
        "episode_replay_comparison": {e["ep_id"]: e["replay_cmp"] for e in episodes},
        "gates": {"verdict": reps.verdict, "n_checks": len(reps.checks), "n_red": reps.n_red,
                  "n_warn": reps.n_warn, "n_a": reps.n_a_count, "n_unjudged": reps.n_unjudged,
                  "n_nonblocking": reps.n_nonblocking,
                  "red_ids": reps.red_ids, "blocking_red_ids": reps.blocking_red_ids,
                  "ok": bool(not reps.blocking_red_ids and reps.n_unjudged == 0),
                  "ok_criterion": ("裁定 78.2：顶层四元组 `n_red/n_warn/n_unjudged/ok`，`ok` 是唯一失败判据、"
                                   "`UNJUDGED` 计入非绿；裁定 85.5：只有 **blocking** 的 RED 才算失败"
                                   "（像素侧一律只登记，不参与判定）"),
                  "pixel_judges_red": (not nvidia_arm_now),
                  "pixel_register_exceedance_slots": pix_exc_slots,
                  "pixel_register_exceedance_slots_criterion": (
                      "**登记项，不是判据**（裁定 85.5）。列入的本批 = 「不是全帧逐位」或「超某条登记带」"
                      "的槽；egl 上腕相机大多数帧本就不逐位（E 的 n=5 + B2 首手实测），"
                      "所以这个列表非空**是常态**，不代表数据有问题"),
                  "slots_exceeding_ruling_83_4_tolerance": pix_tol_slots,
                  "slots_exceeding_ruling_83_4_tolerance_note": (
                      "上面那个列表的**严子集**：连裁定 83.4 的三容差（0.5%）都超了的槽。"
                      "干净批应为空；非空时按 85.5 仍**不判红**，但要报 D"),
                  "checks": reps.checks},
        "gates_all_ok": reps.n_red == 0,
        "open_items_for_d": ctx_open_items,
    }
    mp = note_write(ds_root / a.manifest_name)
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=_json_default),
                  encoding="utf-8")

    if a.mutation != "none":
        exp_red = MUTATION_EXPECT_RED[a.mutation]
        obs_red = reps.red_ids
        stay_green_required = bool(MUTATION_MUST_STAY_GREEN.get(a.mutation))
        stay_green_observed = bool(reps.n_red == 0 and reps.verdict == "PASS")
        tooth_bit = all(g in obs_red for g in exp_red)
        tooth_ok = bool(tooth_bit and (stay_green_observed if stay_green_required else True))
        mv = {"artifact": "b2_s1_mutation_verdict", "mutation": a.mutation, "generated_at": now_iso(),
              "generator": "scripts/b2_s1_generate_dataset.py", "generator_sha256_12": sha12(SCRIPT),
              "dataset_root": str(ds_root), "manifest": str(mp),
              "baseline_manifest": str(out_root / "dataset" / "demo_manifest.json"),
              "expected_must_go_red": exp_red, "observed_red_ids": obs_red,
              "missed_red": [g for g in exp_red if g not in obs_red],
              "extra_red_beyond_expected": [g for g in obs_red if g not in exp_red],
              "extra_red_explanation": _extra_red_explanation(a.mutation, obs_red, exp_red),
              "all_expected_red_caught": tooth_bit,
              "must_stay_green": stay_green_required,
              "stay_green_observed": stay_green_observed,
              "stay_green_criterion": ("n_red==0 且 verdict=='PASS'（裁定 85.5 牙③：只篡改像素、"
                                       "状态一个字节不动 ⇒ 整批**必须仍绿**；若它红了，说明"
                                       "「像素已降级」没生效）"),
              "tooth_verified": tooth_ok,
              "alias_of": MUTATION_ALIAS.get(a.mutation),
              "ruling_85_5_teeth": {
                  "tooth_1_green_witness": ("干净批（--mutation none）⇒ G4 绿、整批 PASS；"
                                            "见同目录的 baseline manifest"),
                  "tooth_2_state_1lsb_must_red": "mutation=replay-state-1lsb ⇒ G4 必须红",
                  "tooth_3_pixel_only_must_stay_green": ("mutation=replay-image-pixel-only ⇒ "
                                                         "**一条都不许红**（本条就是它的验收证据）"),
                  "this_run_covers": ("tooth_3" if stay_green_required else
                                      ("tooth_2" if a.mutation == MUT_STATE_1LSB else
                                       ("tooth_1" if a.mutation == "none" else "legacy_or_other"))),
                  "ruling": "裁定 85.5 / d_handoff_to_b2 §18.5（硬判据只剩「状态逐位」）"},
              "mutation_how": MUTATION_HOW[a.mutation],
              "gates": reps.checks, "n_red": reps.n_red, "verdict": reps.verdict}
        mvp = note_write(out_root / ("mutation_verdict_%s.json" % a.mutation))
        mvp.write_text(json.dumps(mv, ensure_ascii=False, indent=1, default=_json_default),
                      encoding="utf-8")
        print("[mutation] %s：expected_red=%s observed_red=%s missed=%s must_stay_green=%s "
              "stay_green_observed=%s tooth_verified=%s → %s"
              % (a.mutation, exp_red, obs_red, mv["missed_red"], stay_green_required,
                 stay_green_observed, tooth_ok, mvp))
        ctx_mutation_tooth_ok = tooth_ok

    print(json.dumps({"manifest": str(mp), "verdict": reps.verdict, "n_checks": len(reps.checks),
                      "n_red": reps.n_red, "red_ids": reps.red_ids, "n_warn": reps.n_warn,
                      "n_a": reps.n_a_count, "n_unjudged": reps.n_unjudged,
                      "ok": manifest["gates"]["ok"],
                      "mutation_tooth_ok": ctx_mutation_tooth_ok,
                      "pixel_register_exceedance_slots": pix_exc_slots,
                      "episodes": len(episodes), "frames_total": frame_offset,
                      "gib_written": vol["gib_written"],
                      "wall_s_total": round(time.time() - t_start, 1),
                      "nr_throttled_delta": manifest["nr_throttled_delta"],
                      "load_before": prov_before["loadavg"], "load_after": prov_after["loadavg"],
                      "contaminated_by_cotenant":
                          manifest["cotenant_evidence"]["contaminated_by_cotenant"]},
                     ensure_ascii=False, indent=1))
    # rc：0=干净；3=跑完了但有红（或 `UNJUDGED`，或**变异体的牙没咬 / 该绿的没绿**）。
    # 为什么把"牙没咬"也算 3：一颗不会红的闸等于没有闸（裁定 27.1），而牙验收失败**必须**让
    # 调用方非零退出，否则 CI 里跑变异体会静默通过 —— 那正是 85.5 牙③要防的事。
    gates_ok = bool(not reps.blocking_red_ids and reps.n_unjudged == 0 and ctx_mutation_tooth_ok)
    return 0 if gates_ok else 3


# ========================================================================== 辅助（main 用到）
MUTATION_HOW = {
    "none": "无变异（baseline）",
    "dt-back-to-50hz": "把控制周期改回上游的 `DT=0.02`（50 Hz）⇒ 实测 control_hz=50、n_sub_steps=10、"
                       "视频容器帧率写成 `50/1`。频率闸（G3）与团队 QC 的 V04/J 都必须红"
                       "（d_simchain S1 判据 5-①）。**其余闸若也红，属于数据本身在 50 Hz 下变差，"
                       "逐条写进 `extra_red_explanation`，不当作假红掩盖。**",
    "reverse-judge-flipped": "把判据的方向写反：`DIRECTION[d]` 的 pick/receive 互换、`goal_x_sign` 取反"
                             "（与专家脚本 `--mutation reverse-direction-flipped` 同一手法）⇒ "
                             "G1/G5/G7 必须红（d_simchain S1 判据 5-②）。",
    "random-actions": "把 `rng.uniform(-1,1,14)` 的随机动作当『示范』喂进同一条记录/判据链路 ⇒ "
                      "专家闸（G7）与 G1 必须红（d_simchain S1 判据 5-③）。"
                      "**G4 仍应绿**：随机动作的重放同样逐位可复现 ⇒ 证明 G4 不是「什么都红」的闸。",
    # ---- 以下三条是 replay 闸的牙（红线 `tooth_must_be_mutant_proven`：只写 `red_when` 文案不算牙）。
    #      裁定 85.5（§18.5）之后**硬判据只剩「状态逐位」**，所以牙的方向也变了：
    #      ①/② 证明"该红的会红"，③ 证明"已降级的像素判据**不会**红"。----
    "replay-state-perturb-1e-3": "把 replay pass 的**比对副本**第 0 帧第 0 维状态加 `1e-3`"
                                 "（D §17-6 指定的两种手法之一）⇒ G4 的「状态逐位」硬判据必须红。"
                                 "**落盘的数据集不动**（`rec['state14']` 未被改），所以这条变异只证明牙会咬、不产坏数据。",
    "replay-state-1lsb": "把 replay pass 的**比对副本**第 0 帧第 0 维状态推到 `np.nextafter(+1 ULP)`"
                         "（float64 的下一个可表示值，差 ~1e-16）⇒ G4 **仍必须红**。"
                         "为什么比 1e-3 那颗更强：任何偷偷带进比对的容差（哪怕 1e-12）都会放过 1e-3 之外的"
                         "扰动，却放不过 1 ULP 判据的**语义**检验——它证明 G4 用的真的是 `np.array_equal` "
                         "逐位比较（`cmp_states`，脚本内实测），而不是某个带 `atol/rtol` 的近似比较。"
                         "这是裁定 85.5 牙②的字面要求（「篡改任一维状态 1 LSB ⇒ 红」）。",
    "replay-image-pixel-only": "把第二次渲染的**比对副本**里 `%s` 槽的 `%g` 像素各加 `%d` 个灰阶"
                               "（⇒ max_abs_diff=%d > 裁定 83.4 的容差 2、frac_diff_px=%g > 容差 0.005），"
                               "而**状态一个字节不动** ⇒ 按裁定 85.5（§18.5）**整批必须仍绿**（n_red=0、"
                               "verdict=PASS、rc=0），像素超带只登记在 `pixel_register_exceedances` 里。"
                               "**落盘图像不动**（只污染比对用的那份 copy）。"
                               "为什么必须有它：这是裁定 85.5 专属的牙③——**缺它就无法证明「像素已降级」**。"
                               "若它红了，说明降级没生效（egl 上会随机红/常态红，最坏的一种闸）。"
                               % (MUT_IMG_SLOT, MUT_IMG_FRAC, MUT_IMG_DELTA, MUT_IMG_DELTA, MUT_IMG_FRAC),
    "replay-image-over-tolerance": "同 `replay-image-pixel-only`（旧名别名，§17-6 时代它期望 G4b 红；"
                                   "裁定 85.5 之后期望值改为「一条都不许红」）。保留别名只为让旧产物/旧命令行"
                                   "仍能跑，且在 `mutation_verdict.alias_of` 里写明它现在等价于哪条。",
}


def _extra_red_explanation(mutation: str, obs_red: List[str], exp_red: List[str]) -> List[dict]:
    why = {
        "dt-back-to-50hz": "DT=0.02 让同一串相位计划以 1.7× 的仿真速度执行（每步仍是 6 mm 指尖推进），"
                           "position actuator 的滞后按秒计变小/变大都可能让抓取相位错过方块 ⇒ "
                           "G1/G7 变红是**数据事实**，不是闸错。G3 是这条变异的目标牙。",
        "reverse-judge-flipped": "方向写反后，抓取臂变成够不到方块的那一侧（可达带重叠区只有 "
                                 "x∈[−0.125,+0.125]，probe/reach_sweep.json）⇒ 判词 failure ⇒ "
                                 "G1/G7 随之红，这是同一条根因的连带，不是独立缺陷。",
        "random-actions": "随机动作既不成功也不像示范 ⇒ G2 的『相邻帧有变化』仍绿（随机动作让画面乱动），"
                          "G8/G9 可能因夹爪命令没到 0/1 两端而红，都是数据事实。",
    }
    return [{"gate": g, "explanation": why.get(mutation, "")} for g in obs_red if g not in exp_red]


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, Path):
        return str(o)
    return str(o)


def _phase_timeline(phases: Sequence[str], settle: int) -> List[dict]:
    """把逐帧相位标签折叠成区间（丢弃前 `settle` 步），供 sidecar 与 subtask 对账。"""
    kept = list(phases[settle:])
    out: List[dict] = []
    start = 0
    for i in range(1, len(kept) + 1):
        if i == len(kept) or kept[i] != kept[start]:
            out.append({"phase": kept[start], "range": [start, i - 1], "n": i - start})
            start = i
    return out


def _throttled_delta(before: dict, after: dict) -> Optional[int]:
    b = (before.get("cpu_stat") or {}).get("nr_throttled")
    a = (after.get("cpu_stat") or {}).get("nr_throttled")
    return (a - b) if isinstance(a, int) and isinstance(b, int) else None


def _dig(doc: Any, path: str) -> Any:
    cur = doc
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


PROVENANCE_REQUIRED = (
    "versions.mujoco", "versions.dm_control", "versions.gym-aloha", "versions.lerobot",
    "versions.python", "venv", "shim.sha256_12", "shim.representation_version",
    "frequency.DT", "frequency.control_hz_measured", "frequency.n_sub_steps",
    "frequency.model_timestep_s", "frequency.episode_horizon_s",
    "frequency.fps_rational_in_video_container",
    "gl_identity.gl_strings.GL_VENDOR", "gl_identity.gl_strings.GL_RENDERER",
    "gl_identity.gl_strings.GL_VERSION", "gl_identity.renderer_class",
    "gl_identity.identity_source",
    "activation_env.prefix_paths_verified.prefix_in_ld_library_path",
    "activation_env.prefix_paths_verified.vendor_json_points_into_prefix",
    "activation_env.prefix_paths_verified.vendor_json_exists",
    "git.head", "generator_sha256_12", "expert_module_sha256_12",
    "load_before.loadavg", "load_after.loadavg", "cotenant_evidence.quiet_window",
    "command_verbatim", "generated_at", "representation_version",
    "a2_contract_reference.path", "a2_contract_reference.sha256_12",
    "three_piece_versions.policy", "three_piece_versions.stats", "three_piece_versions.shim",
)


def ctx_required_fields() -> List[str]:
    return list(PROVENANCE_REQUIRED)


def _provenance(a, contract, task_text, cam_map, shim, before, after, vol, sv, episodes,
                lr_verify, hz_measured, fps_str, dt) -> dict:
    """G11 的核对对象：把 manifest 的溯源面**先**拼出来，让闸去查它缺不缺（不是自己说齐了就齐）。"""
    return {"versions": ctx_versions, "venv": sys.executable, "shim": shim,
            "frequency": {"DT": dt, "control_hz_measured": hz_measured, "n_sub_steps": 17,
                          "model_timestep_s": 0.002, "episode_horizon_s": round(300 * dt, 4),
                          "fps_rational_in_video_container": fps_str},
            "gl_identity": ctx_gl_identity, "activation_env": ctx_activation, "git": ctx_git,
            "load_before": before, "load_after": after,
            "cotenant_evidence": {"quiet_window": ctx_quiet_window},
            "command_verbatim": " ".join([sys.executable] + sys.argv),
            "generated_at": now_iso(), "representation_version": REPRESENTATION_VERSION,
            "generator_sha256_12": sha12(SCRIPT),
            "expert_module_sha256_12": sha12(ROOT / "scripts" / "b2_s1_scripted_expert.py"),
            "a2_contract_reference": {"path": str(A2_CONTRACT), "sha256_12": sha12(A2_CONTRACT),
                                      "mtime": _mtime(A2_CONTRACT), "task": contract["task"],
                                      "camera_map": cam_map},
            "three_piece_versions": ctx_three_piece}


def _mtime(p: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(Path(p).stat().st_mtime, CST).isoformat(timespec="seconds")
    except OSError:
        return None


def _write_team_dataset_manifest(team_root: Path, episodes: List[dict], ds_root: Path,
                                 contract: dict, task_text: dict, a, shim, hz_measured,
                                 fps_str: str) -> None:
    """团队 QC 的 Q6/Q7 要读 `data/dataset_manifest.json`；这也是数据集的**门面账**。"""
    per_dir: Dict[str, int] = {}
    rows = []
    for e in episodes:
        lab = DIRECTION_LABEL[e["direction"]]
        per_dir[lab] = per_dir.get(lab, 0) + 1
        t = e["team"] or {}
        rows.append({"episode_id": e["ep_id"], "direction": e["direction"],
                     "direction_label": lab, "task_dir": TASK_DIR[e["direction"]],
                     "task_info": e["task_text"], "path": t.get("path"), "seed": e["seed"],
                     "n_frames": e["metrics"]["n_frames"], "fps": hz_measured,
                     "fps_rational": fps_str,
                     "metadata_sha256": t.get("metadata_sha256"),
                     "metadata_bytes": t.get("metadata_bytes"),
                     "videos": t.get("videos"),
                     "verdict_geometric_truth": e["metrics"]["verdict_replay_render"],
                     "env_reward_terminal": e["metrics"]["env_reward_terminal"],
                     "data_kind": DATA_KIND, "negative_control": None,
                     "sidecar": e["sidecar"]})
    balanced = (len(per_dir) == 2 and len(set(per_dir.values())) == 1) if len(per_dir) > 1 \
        else False
    man = {
        "dataset_kind": DATASET_KIND,
        "data_kind": DATA_KIND,
        "negative_control": None,
        "not_a_capability_claim": True,
        "policy_executed": False,
        "capability_claim": False,
        "WHAT_THIS_IS": ("**仿真双向示范**（gym-aloha 关节模型 + B2 自写脚本专家：运动学 DLS-IK "
                         "规划 → 关节模型自己的 actuator 执行 → 逐位重放校验）。"
                         "它**是**示范数据（可喂 BC / 算 stats），但**不是**任何 policy 的能力证据"
                         "（裁定 46：没跑过 policy 就不许声称能力）。"),
        "generated_at": now_iso(),
        "generated_by": "scripts/b2_s1_generate_dataset.py",
        "generator_sha256_12": sha12(SCRIPT),
        "out_root": str(team_root),
        "split": "train",
        "n_episodes": len(episodes),
        "n_per_direction": per_dir,
        "forward_direction_label": DIRECTION_LABEL["forward"],
        "reverse_direction_label": REVERSE_DIRECTION_LABEL,
        "directions_balanced": balanced,
        "frame_alignment": "born_aligned（17 个 DIMENSION_CONFIG 字段与三路视频**同帧数**；G15 自核）",
        "frequency": {"DT": a.dt if a.mutation != "dt-back-to-50hz" else 0.02,
                      "control_hz_measured": hz_measured, "n_sub_steps": 17,
                      "model_timestep_s": 0.002, "fps_rational_in_container": fps_str,
                      "qc_band_hz": list(QC_FPS_BAND),
                      "episode_horizon_s": round(300 * (1.0 / hz_measured), 4),
                      "ruling": "裁定 53（29.4118 Hz）/ 裁定 65-2（300 步 = 10.2 s）"},
        "shim": shim,
        "representation_version": REPRESENTATION_VERSION,
        "box_settle": {"box_settle_steps": BOX_SETTLE_STEPS, "box_z_seeded": BOX_Z_SEEDED,
                       "box_z_at_rest": BOX_Z_AT_REST,
                       "policy": "沉降的 12 步**不进数据集**（裁定 66 §13.7-1）"},
        "gripper_calibration": {"open_cmd": GRIP_CMD_OPEN, "close_cmd": GRIP_CMD_CLOSE,
                                "open_close_threshold_cmd": GRIP_CMD_THRESHOLD,
                                "cmd_to_spread_m": GRIP_CALIBRATION_TABLE, "box_width_m": 0.04},
        "action_representation": {"dim": 14,
                                  "assembly_order": "[左臂6, 左夹爪1, 右臂6, 右夹爪1]",
                                  "grip14_to_qpos_pair": "+v, −v（tasks/sim.py:47-48 实测）",
                                  "units": {"arm_joints": "radian（绝对关节目标位）",
                                            "gripper": "normalized_[0,1]（0=闭 1=开）",
                                            "velocity": "radian/s", "pose": "meter + quaternion xyzw",
                                            "pose_inner_order": "[x,y,z,qx,qy,qz,qw]"},
                                  "cross_check": "G14：复位 state14 与 A2 契约 state_raw_14d 逐位相同"},
        "task_text": task_text,
        "task_text_status": TASK_TEXT_STATUS,
        "a2_contract_reference": {"path": str(A2_CONTRACT), "sha256_12": sha12(A2_CONTRACT),
                                  "mtime": _mtime(A2_CONTRACT), "task": contract["task"],
                                  "camera_map": contract["camera_map"]},
        "camera_slots": {"team": TEAM_SLOT_CAMERA, "pi05": contract["camera_map"],
                         "note": ("团队 head 槽 = 真 `top` 相机（不张冠李戴）；π₀.₅ 的 base 槽 = "
                                  "`angle` 相机（A2 契约实测）。两腕相机同时出 480×640 与 224² 两档，"
                                  "**两档不是缩放关系**（fovy 固定 ⇒ 视锥不同），各渲各的。")},
        "episodes": rows,
        "form_fact_sources": [
            "vla_pipeline/rules/qc/_meta.py（DIMENSION_CONFIG 17 键 / META_FIELDS / pose 内序）",
            "vla_pipeline/configs/default.yaml（视频槽位与文件名 / fps∈[29,31] / expected 文件 / 各阈值）",
            "workplace/ABC130k（真实语料，只读实测：分辨率 640×480 与 848×480 两档、intrinsics 是单个 3×3）",
            "runs/vla/b2_bidir_demo_form_20260929/（B2 自己的形态夹具，Q0–Q8 已过）"],
        "resolved_a2_g2_items": ["action_dimensions_and_order(14, 实测钉死)",
                                 "units(radian / normalized[0,1] / m / xyzw)",
                                 "gripper_semantics(0=闭 1=开, probe4 标定表)",
                                 "control_hz_vs_video_fps(29.4118 逐字进容器 500/17)",
                                 "sim_env_choice(gym_aloha 关节模型 AlohaTransferCube-v0)"],
    }
    p = note_write(team_root / "dataset_manifest.json")
    p.write_text(json.dumps(man, ensure_ascii=False, indent=1, default=_json_default),
                 encoding="utf-8")


# ========================================================================== 模块级取证（import 时一次）
ctx_versions = versions()
ctx_activation = activation_env()
ctx_git = git_head()
ctx_gl_identity = None            # 懒加载：只有真要渲染时才起 GL 上下文
ctx_gpu_preflight: Optional[dict] = None
ctx_quiet_window = {
    "declared_by_b2": False,
    "reason": None,          # 由 `_check_quiet_window()` 用**起跑那一刻的实测**填写（不写死）
    "checked_daily_report_for_active_window": None,
    "priority_rank": "A2 > C2 > E > B2（B2 排最后，裁定 67/73）",
}
ctx_three_piece = {"policy": None, "stats": None, "shim": None}
ctx_d_h1_verdict = None
ctx_open_items: List[dict] = []


def _init_gl_identity() -> None:
    global ctx_gl_identity
    if ctx_gl_identity is None:
        ctx_gl_identity = gl_identity()


def _init_three_piece() -> None:
    """三件套版本（policy / stats / shim）必须写进每条轨迹（d_simchain S4：B2 主责）。"""
    ctx_three_piece["shim"] = {"path": "envs/gym_aloha_shim.py",
                               "sha256_12": sha12(SHIM_PATH) if SHIM_PATH.exists() else None,
                               "representation_version": None}
    try:
        from envs import gym_aloha_shim as shim_mod
        ctx_three_piece["shim"]["representation_version"] = shim_mod.REPRESENTATION_VERSION
    except Exception:                                            # noqa: BLE001
        pass
    # policy：本数据集**没有**跑过任何 policy ⇒ 只能记"底座身份"，不记微调版本
    ctx_three_piece["policy"] = {
        "value": "none_executed_base_only",
        "base_model_dir": "runs/vla/a2_pi05_contract_20260929/pi05_base_compat_lerobot044",
        "base_identity_source": "A2 的 weights_receipt / env_manifest（B2 不重复下载、不重复核验）",
        "why": "S1 只产示范；跑 policy 是 A2 的 S3/S5（裁定 46：没跑过 policy 不许声称能力）"}
    ctx_three_piece["stats"] = {
        "value": "not_yet_generated_owner_c2",
        "ruling": "裁定 52/69：主线 stats 源 = 本数据集（同源），生成器与闸归 C2 的 T-C2-1",
        "lerobot_own_stats_json": "meta/stats.json 是 lerobot 自动算的 min/max/mean/std，**不是**主线 stats",
        "abc130k_stats_banned": "裁定 43.4/49.1/52/61：YAM/ABC-130k stats 主线禁用"}


def _check_quiet_window() -> None:
    """裁定 73：开工前看 `daily_report.md` 有没有**生效中**的静默窗口（只读）。"""
    p = ROOT / "daily_report.md"
    out = {"daily_report_path": str(p), "active_window_found": None, "matched_lines": []}
    try:
        txt = p.read_text(encoding="utf-8", errors="replace").splitlines()
        hits = [(i + 1, l.strip()[:200]) for i, l in enumerate(txt)
                if "静默窗口" in l and ("申请" in l or "生效" in l or "起" in l)]
        out["matched_lines"] = hits[-8:]
        out["active_window_found"] = bool(hits)
        out["note"] = ("命中行只是**文本证据**，是否生效需 D 排窗确认；B2 本次采集 < 10 min GPU "
                       "且起跑前实测 GPU 空载 ⇒ 未占别人的窗口，也不申请自己的窗口")
    except OSError as e:
        out["error"] = f"{type(e).__name__}: {e}"
    ctx_quiet_window["checked_daily_report_for_active_window"] = out
    ctx_quiet_window["preflight_gpu_guard"] = ctx_gpu_preflight
    if ctx_gpu_preflight:
        idle = ctx_gpu_preflight["idle"]
        ctx_quiet_window["gpu_idle_at_start_measured"] = idle
        ctx_quiet_window["detector"] = ctx_gpu_preflight.get("detector")
        ctx_quiet_window["three_net_hits"] = ctx_gpu_preflight.get("net_hits")
        ctx_quiet_window["reason"] = (
            ("起跑那一刻**三网并查**（网①`compute-apps` + 网②`/dev/nvidia*` fd 持有者 + "
             "网③cmdline，裁定 85.6-2）实测**无外来命中**（own_pids=%s）⇒ 未占别人的窗口；"
             "本次 GPU 渲染预计 < 10 min（实测 ≈34–35 s/集，含同状态连渲两次），"
             "未触发裁定 73 的申请门槛，故不申请自己的窗口"
             % ctx_gpu_preflight["excluded_own_pids"]) if idle else
            ("起跑那一刻**三网并查**实测**有外来命中**（%s）⇒ 按裁定 73 + 85.6-2 本次产物"
             "一律标 `contaminated_by_cotenant`，只可作趋势参考、**不得作权威口径**"
             % ctx_gpu_preflight["net_hits"]))


def _load_d_h1_verdict() -> None:
    """裁定 66 §13.6：D 的右臂假设（`d_inference_not_measured`）由 B2 实测判定，不再问 D。"""
    global ctx_d_h1_verdict
    p4 = ROOT / "runs/vla/b2_sim_demo_bidir_20260930/probe/probe4.json"
    p3 = ROOT / "runs/vla/b2_sim_demo_bidir_20260930/probe/probe3.json"
    doc = {"ruling": "裁定 66 §13.6（D-H1：解析反解对右臂沿用了左臂的单位 qrel，未逐侧复合）",
           "d_h1_statement": "逐侧复合 qrel 后右臂位置残差应 < 3 mm；若仍 > 3 mm ⇒ D-H1 被否",
           "probe4_path": str(p4), "probe4_sha256_12": sha12(p4) if p4.exists() else None}
    if p4.exists():
        d = json.loads(p4.read_text())
        cal = d.get("calibration_analytic") or {}
        e2 = d.get("E2_zero_transient_init") or {}
        wr = d.get("weld_rows") or {}
        probe = {"calibration_analytic": cal, "E2_zero_transient_init": e2, "weld_rows": wr}
        probe = json.loads(json.dumps(probe, default=_json_default))
        probe = {k: v for k, v in probe.items() if v}
        # 判据：B2 的解析反解**已经**逐侧读了 eq_data[6:10] 的 relpose（不是沿用左臂单位 qrel）
        per_side = bool(wr) and (
            str((wr.get("right") or {}).get("relpose_quat_wxyz_raw")) !=
            str((wr.get("left") or {}).get("relpose_quat_wxyz_raw")))
        probe["per_side_relpose_actually_read"] = per_side
        probe["right_relpose_quat_wxyz_raw"] = (wr.get("right") or {}).get("relpose_quat_wxyz_raw")
        probe["left_relpose_quat_wxyz_raw"] = (wr.get("left") or {}).get("relpose_quat_wxyz_raw")
        probe["right_base_euler_in_xml"] = "assets/vx300s_right.xml:3 euler=\"0 0 3.1416\""
        doc["probe4_extract"] = probe
        doc["verdict"] = ("D-H1 **被否**（falsified）：B2 的 `calibration_analytic` 已经**逐侧**读了 "
                          "`eq_data[6:10]` 的 relpose（左 [1,0,0,0]、右 w≈0/z≈1，两侧确实不同），"
                          "复合之后右臂残差仍是 0.2469 m / 姿态 2.376 rad ⇒ 不是『沿用左臂单位 qrel』。"
                          "转 H2/H3：EE 模型 `nu=4` 且 4 个 actuator 名全为空串（D 自己 21:5x 实测）⇒ "
                          "**整条臂没有 actuator，只靠 soft weld 吊着**，右臂基座绕 z 反装 180° 使 weld 的 "
                          "relpose 与 anchor2（±0.134706 m）在复位瞬间就自相矛盾 ⇒ 姿态力矩把臂甩开，"
                          "这是**约束本身的不一致**，不是反解公式的错。")
        doc["verdict_status"] = "b2_measured_falsifies_d_inference"
        doc["consequence"] = ("EE-oracle 这条通道对右臂不可用 ⇒ S1 改在关节模型里做运动学 IK 规划 + "
                              "关节模型自己的 actuator 执行（见 route_compliance）。"
                              "否证结果按裁定 66 要求留痕（D 的推断被否也要写进产物）。")
        doc["how_to_reproduce"] = ("/root/venvs/pi05_sim/bin/python scripts/b2_s1_probe4_weld_calibration.py"
                                   "（产物 probe/probe4.json，保留不改写）")
    else:
        doc["verdict"] = None
        doc["verdict_status"] = "UNJUDGED_probe4_missing"
    if p3.exists():
        doc["probe3_crash_kept_verbatim"] = {
            "path": str(p3), "sha256_12": sha12(p3),
            "note": "probe3 的 traceback 如实留在 `error` 字段（裁定 66 记功项），不改写不隐藏"}
    ctx_d_h1_verdict = doc


def _load_open_items() -> None:
    ctx_open_items.extend([
        {"id": "RR-B2-10", "topic": "反向任务串（语言条件）",
         "value": TASK_TEXT_PROPOSED["reverse"],
         "status": "CLOSED_d_approved_ruling_85_3",
         "d_ruling": ("裁定 85.3（§18.3）**批准**本串（主/宾精确镜像）。D 已核一致性：正向落 "
                      "`transfer_cube_right_to_left`、终态被 **left** 夹爪握住、`reward=4`；"
                      "反向 `reward=2`（≠4）⇒ 满足 G1 的必红条件。**两串一经采用即训练/评测共用"
                      "条件信号，改串 = 换 `representation_version`**；本轮用的就是被批准的逐字串 "
                      "⇒ `REPRESENTATION_VERSION` 维持 `-v1` 冻结"),
         "why": "S3 是「同一 θ 学双目标、方向由语言指令区分」（d_simchain S3 口径）⇒ 反向串一旦定了就是"
                "训练/评测共用的条件信号，改串等于换 representation_version，必须 D 批",
         "forward_string_is_verbatim_from": "runs/vla/a2_pi05_contract_20260929/contract.json → args.task"},
        {"id": "RR-B2-11", "topic": "π₀.₅ 图像键名与 base 相机（D 的文书 vs A2 的契约不一致）",
         "status": "CLOSED_d_withdrew_own_wording_ruling_85_3",
         "d_ruling": ("裁定 85.3（§18.3）：**B2 正确，D 撤回自己的写法**。正确键名 = "
                      "`observation.images.{base_0_rgb,left_wrist_0_rgb,right_wrist_0_rgb}`"
                      "（A2 实测自 π₀.₅ processors）；D §13.8-2 的 `{top,left_wrist,right_wrist}` **错**。"
                      "B2「读实现不读声明」记功；pilot parquet 列名已合规。D 已立自查项 "
                      "`d_assertion_requires_artifact_or_tag`"),
         "detail": ("D §13.8-2 写 `observation.images.{top,left_wrist,right_wrist}`；A2 契约（实测自 "
                    "π₀.₅ processors）是 `base_0_rgb←angle`。B2 以契约为准（读实现不读声明）"),
         "impact_if_d_literal_were_used": "A2 的 S3 训练与 C2 的 obs 键覆盖闸会对不上键名 ⇒ 假红或静默丢图"},
        {"id": "RR-B2-12", "topic": "lerobot 数据集的图像存储档（PNG 内嵌 vs mp4）",
         "status": "CLOSED_d_ruled_keep_png_inline_ruling_85_3",
         "d_ruling": ("裁定 85.3（§18.3）**维持甲（PNG 内嵌），不做丙（monkeypatch）**：甲无损诚实且"
                      "体积已实测可承受（formal 外推 **0.22 GiB** vs 预算 10 GiB，余量 **45×**）；"
                      "乙让 fps 字段说谎违反裁定 53；丙要 monkeypatch 第三方运行时而体积**不是**约束 "
                      "⇒ 风险大于收益。**可推翻条件**：formal 实测 > 2 GiB，或训练侧改为直接消费 "
                      "`team_form` 的 mp4"),
         "measured_volume_formal_40_extrapolated_gib": 0.22,
         "detail": ("lerobot 0.4.4 的视频编码把 fps 直接喂 PyAV（video_utils.py:460 → av/utils.pyx:51）"
                    "⇒ **非整数 fps 抛 AttributeError**；主线是 29.4118 Hz（非整数）⇒ 甲 PNG 内嵌（无损、"
                    "诚实、体积大）/ 乙 容器 30 fps（体积小、fps 字段说谎）/ 丙 monkeypatch 编码器注入 "
                    "Fraction(500,17)（体积小且诚实、但改第三方运行时行为）。**采甲，报 D 裁是否要丙。**"),
         "measured_evidence": "tmp/b2_lerobot_fps_probe/（两臂实测：image 档成功、video 档 AttributeError）"},
        {"id": "RR-B2-13", "topic": "N 集数（正反各多少）",
         "status": "CLOSED_d_confirmed_per_direction_ruling_85_3",
         "d_ruling": ("裁定 85.3（§18.3）**确认为「每方向」**：先导 **10 集**（5/方向）、正式 **40 集**"
                      "（20/方向）。消解裁定 66 的歧义——S3 要求同一 θ 学双向，若按「总共 5 集」拆成 2/3，"
                      "任一方向都不够跑 q01–q99。**formal 40 集 = BC 的 stats 源，落地后需通知 C2 重算**"),
         "value": {"pilot": 5, "formal": 20, "d_prior": "裁定 66：先导 5 集 + 正式 20 集"},
         "b2_note": ("先导 5 集已够 C2 的 T-C2-1 stats 起跑（裁定 69）；正式 40 集的体积**已实测**："
                     "先导 10 集 = 0.0539 GiB ⇒ 40 集外推 ≈**0.22 GiB**（远低于 10 GiB 申报线；"
                     "上一棒「数 GiB / >10 GiB」的估算按实测**不成立**，已在 daily_report §B2-9.3 更正）")},
        {"id": "RR-B2-14", "topic": "专家成功率阈值（扩量门槛）",
         "status": "proposed_pending_d",
         "value": {"d_ruled_minimum": 0.5, "b2_proposed_for_scaling": 0.9,
                   "measured_on_heldout_seeds": None},
         "why": "d_simchain S1 判据 4 只给了『低于 50% 必须先修专家』；扩到 20 集/方向的门槛 B2 建议 90%"},
        {"id": "RR-B2-15", "topic": "**B2 污染了 A2 的第 5 次静默窗口**（自报，请转 A2）",
         "status": "b2_self_reported_fix_landed",
         "severity": "high（A2 的 rep1–rep3 已因污染作废，见 daily_report.md:5023/5042/5136）",
         "detail": ("B2 的 S1 selftest（2026-09-30 00:21:03 起、00:26:58 落盘，EGL 渲染 2 集）与 A2 的 "
                    "`scripts/a2_egl_latency_remeasure.py --mode closed_loop --tag quiet_window_rep5`"
                    "（PID 205499，14436–14990 MiB）**同卡在跑**。B2 自己的 "
                    "`cotenant_evidence.before/after` 抓到了它（`line_tag=a2`）⇒ "
                    "`contaminated_by_cotenant=true`、`nr_throttled_delta=106`"),
         "evidence": "runs/vla/b2_sim_demo_bidir_20260930/selftest/demo_manifest.json → cotenant_evidence",
         "b2_root_cause": ("`ctx_quiet_window.reason` 里那句『起跑前已实测 GPU 空载』是 23:45 写死的"
                           "**字符串**，不是起跑时的测量；`_check_quiet_window()` 只 grep "
                           "`daily_report.md` 的文本、从不查 `nvidia-smi`；也没有起跑前的拒绝逻辑 "
                           "⇒ 同一份 manifest 里口头承诺与实测证据互相打脸"),
         "fix_landed": ("① 新增 `gpu_preflight()`：起跑那一刻实测 `nvidia-smi --query-compute-apps`，"
                        "过滤 own_pid/parent_pid；② 发现外来 GPU 进程 ⇒ **拒绝起跑**（exit 3 + 落 "
                        "`refused_gpu_busy_<ts>.json` 证据），除非显式 `--allow-cotenant`（此时产物"
                        "一律标 contaminated、只作趋势参考）；③ GL 上下文挪到硬闸**之后**才起；"
                        "④ `ctx_quiet_window.reason` 改为由实测生成，不再写死"),
         "ask_of_d": ("① 请转 A2：`latency_quiet_window_rep5.json` 若其窗口覆盖 00:21–00:27，"
                      "应判 contaminated，**不要**当权威值；② 请裁 B2 的 S1 采集要不要申报窗口"
                      "（见 RR-B2-17 的 GPU 秒数拆分：正式 40 集只用 ≈2.7 min GPU，"
                      "低于裁定 73 的 10 min 门槛，但墙钟 ≈15 min）")},
        {"id": "RR-B2-16", "topic": "selftest 首轮 6 红里**4 红是闸自己写错**（闸的可信度自评）",
         "status": "fixed_all_six_selftest_now_16_of_16_pass",
         "detail": {
             "gate_was_wrong_4": [
                 "G9-①：拿『cmd=1.0 帧的**动态最大**指距』去比 probe4 的**静态**标定值 ⇒ 口径错。"
                 "改为准静态中位（|qvel|<0.1 rad/s），实测 0.08746 vs 表 0.08412（差 3.34 mm，"
                 "构型差：probe4 在复位构型测、数据在工作构型测）⇒ 容差 5 mm 并写明理由",
                 "G9-②：夹持指距的期望带 [0.030,0.045] 是**没有依据的手写魔数**。正确期望值 = "
                 "空载闭合指距 0.01833 + 方块实测宽 0.04（`geom_size`×2，实测自模型）= 0.05833，"
                 "实测中位 0.05837（差 0.04 mm）⇒ 这条其实是**抓握质量证明**（夹空会掉到 0.018）",
                 "G12：拿**全局**帧号算期望时间戳，而 lerobot v3 的 `timestamp` 是**每集从 0 起算**"
                 "（`frame_index` 集内、`index` 全局）⇒ 第二集起每帧差一整集时长（实测 8.772 s = 258/29.4118）",
                 "G16：只试了 depth=+p_cam[2]，而 MuJoCo 相机沿自己的 **−z** 看（实测 "
                 "`target_in_cam_xyz[2]=−0.8`）⇒ 所有点都判『Z≤0 投影无定义』，闸**空转**；"
                 "改成四约定（深度 ±z × v 轴 ±）全算、由命中的定约定，并与 targetbody 的独立测量对账。"
                 "另外 60 px 松半径会让错的约定也命中（57.4 px）⇒ 判定改用 8 px 紧半径"
                 "（正确约定实测命中 0.37/0.65 px，亚像素）"],
             "data_was_wrong_2": [
                 "G15（真缺陷，根因在专家）：每条臂的**第一个规划点**把腕从 START_ARM_POSE 猛拉到 "
                 "R_DOWN ⇒ 命令侧 0.127 m/175.75° 一步，实测侧因伺服欠阻尼冲到 42.0°/帧"
                 "（C03 阈值 0.1 m/30°，`clean` 段会删帧）。修法：新增 `plan_align()` 把 175° 腕对齐"
                 "放进**沉降的那 12 步**（本就不进数据集）+ `plan_line` 前 15 点球面插值兜残余。"
                 "修后 6 集双向最坏：命令 0.0161 m/1.84°、实测 0.0091 m/5.31°（低一个量级）",
                 "G14（真缺陷，根因在取数点）：`reset_state` 在 `env.reset()` **之前**取 ⇒ 拿到构造态 "
                 "qpos=0，而不是 `initialize_episode` 写入的 START_ARM_POSE（差 1.16 rad）。"
                 "红得对——这条闸就是为了钉死 14 维装配序。修后又发现第二层：A2 契约的 "
                 "`state_raw_14d` 是**四舍五入到 6 位小数**存进 JSON 的（0.099848331→0.099848），"
                 "拿它做『逐位相同』必然差 3.3e-07 ⇒ 改成两层：对**上游常量重构值**逐位比 + "
                 "对契约按它自己的 6 位口径比（原始差 ≤5e-07）"]},
         "why_this_matters": ("闸写错比数据写错更危险：错闸要么永久红（没人再看）、要么空转判绿"
                              "（假保证）。所以每条闸的红/绿都必须能用**变异体**证伪"),
         "followup_required": ("G9/G12/G14/G16 的判据都改过 ⇒ 三个变异体（dt-back-to-50hz / "
                               "reverse-judge-flipped / random-actions）必须**重跑**，"
                               "确认改后仍能红；另建议加第 4 个变异体 `intrinsics-fovy-wrong` "
                               "专门打 G16（否则 G16 至今只被『空转』证伪过，没被『真错』证伪过）")},
        {"id": "RR-B2-17", "topic": "每集成本拆分：GPU 只占 1/6，probe5 的外推口径要更正",
         "status": "measured_reported",
         "measured_selftest_2eps": {"per_episode_wall_s": {"forward": 23.2, "reverse": 21.9},
                                    "expert_pass_s": {"forward": 0.64, "reverse": 0.33},
                                    "replay_pass_render_s": {"forward": 4.11, "reverse": 4.05},
                                    "frames": {"forward": 274, "reverse": 271}},
         "derivation": ("GPU 侧 ≈4.1 s/集（渲染 6 槽 × 286 步 = 0.0144 s/步，与 probe5 的 0.0118 "
                        "同量级）；其余 ≈18.5 s/集是**第三个 pass（不渲染对照）+ 3 路 ffmpeg 视频 + "
                        "lerobot PNG 内嵌 parquet 写盘（NFS）**，属 CPU/IO 不属 GPU"),
         "impact_on_window_math": ("正式 40 集：GPU ≈2.7 min（**低于**裁定 73 的 10 min 门槛）、"
                                   "墙钟 ≈15 min。B2 之前按 probe5 外推写的『正式 40 集 ≈2.4 min』"
                                   "**低估了 6.5×**（只算了 GPU、没算编码与写盘）⇒ 更正"),
         "loadavg_discipline": "所有墙钟数字都是负载条件量：同批落 loadavg 三点 + nr_throttled 增量"},
    ])
    sv_path = ROOT / "runs/vla/b2_sim_demo_bidir_20260930/probe/expert_selfverify_40x2_postpatch2.json"
    if sv_path.exists():
        try:
            s = json.loads(sv_path.read_text()).get("summary") or {}
            rr14 = next((x for x in ctx_open_items if x.get("id") == "RR-B2-14"), None)
            if rr14 is not None:
                rr14["value"]["measured_on_heldout_seeds"] = {
                    "success": s.get("success"), "total": s.get("total"),
                    "rate": (s.get("success") / s.get("total")) if s.get("total") else None,
                    "seeds": "5000–5039 × {forward, reverse}（留出池，与开发 seed 1000–2002 不重叠）",
                    "artifact": str(sv_path), "sha256_12": sha12(sv_path), "mtime": _mtime(sv_path),
                    "expert_module_sha256_12_when_generated":
                        ((json.loads(sv_path.read_text()).get("module_identity") or {})
                         .get("sha256_12")),
                    "matches_current_expert_module": bool(
                        ((json.loads(sv_path.read_text()).get("module_identity") or {})
                         .get("sha256_12"))
                        == sha12(ROOT / "scripts" / "b2_s1_scripted_expert.py"))}
                rr14["value"]["b2_verdict_on_own_threshold"] = (
                    "实测留出成功率 %s ⇒ %s B2 自提的 90%% 扩量门槛，可以扩到 20 集/方向"
                    % (rr14["value"]["measured_on_heldout_seeds"]["rate"],
                       "达到" if (rr14["value"]["measured_on_heldout_seeds"]["rate"] or 0) >= 0.9
                       else "未达到"))
        except Exception:                                        # noqa: BLE001
            pass


if __name__ == "__main__":
    # 注意：**不在这里起 GL 上下文** —— 裁定 73 的 GPU 空载实测必须在起上下文之前完成
    # （否则本进程自己就上卡了，取证口径也乱）。`_init_gl_identity()` 挪到 main() 的硬闸之后。
    _init_three_piece()
    _check_quiet_window()
    _load_d_h1_verdict()
    _load_open_items()
    raise SystemExit(main())
