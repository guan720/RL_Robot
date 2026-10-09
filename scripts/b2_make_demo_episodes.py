#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 线：双向 episode 的**形态生成器**（D→B2 执行单 §2.2 + 增补 §7.2）。

这个脚本现在产出的是什么、不是什么
--------------------------------
**是**：目录形态与字段口径**对齐团队流水线**的 episode 骨架，用来把
「validate → clean → qc」这条管路**先打通并证明可判**（生来帧数对齐、30 fps、
subtask range 连续且末端 == len(is_move)-1、17 个 DIMENSION_CONFIG 字段齐且维度对）。
轨迹是**解析合成**的（reach→grasp→lift→transfer→release 的平滑样条），
不是任何机器人或仿真器跑出来的。

**不是**：示范数据。产物里每一处都盖了 `data_kind` 戳，默认
`form_fixture_not_demonstration`。**不得**把这批产物当示范喂训练，也**不得**
用它声称任何能力（D→B2 §5：不得把「数据造出来了」写成「双向能力有了」）。

为什么要先做这个（D 增补 §7.2 的裁定）
------------------------------------
B2 的数据 schema **必须等 A2 的 G2 契约表落盘后定稿**（动作维度/单位/频率对不上，
数据就是废的）。但**目录形态与 QC 管路**不依赖 G2 ⇒ 可以先做，且必须先做：
团队真实语料的 QC 实测（B2 只读 `workplace/ABC130k/result/robot_clean_20260818/pipeline.db`，
67,434 条 episode、54,597 条完成）显示 **A 规则 100% 全红**（`字段缺失: intrinsic`，
而数据里的键叫 `intrinsics`）、**V09/V10/N/O 63% 红**（`subtask` 为空）。
⇒ 「过 QC」不是走个形式：不先把字段口径钉死，采完数据一样全红，而且红的原因会被误读成数据质量问题。

形态事实源（全部只读实测，不猜）
------------------------------
1. `vla_pipeline/rules/qc/_meta.py`：`DIMENSION_CONFIG` 17 个键与每帧维度
   （左右臂 joint6/pose7/velocity6、左右夹爪 joint1、`is_move` dim1）、
   `META_FIELDS = [task_info, subtask, file_path]`、pose 内序 `[x,y,z,qx,qy,qz,qw]`、
   夹爪开闭值在 `gripper.joint[0]`。
2. `vla_pipeline/configs/default.yaml`：视频槽位 `head/left_wrist/right_wrist` →
   `top-camera.mp4` / `left-wrist-camera.mp4` / `right-wrist-camera.mp4`；
   `expected` 四个文件；`fps ∈ [29,31]`；`frame_diff_threshold=5`。
3. `vla_pipeline/samples/demo_data/dual_arm_ok/`（团队自带的**已知合格**参照）：
   所有时间序列**等长**、`subtask=[{"range":[0,N-1],"memory":"demo"}]`、`is_move` 为标量序列。
4. `workplace/ABC130k/train/<task>/episode_<uuid>/`（真实语料，B2 只读实测一条）：
   `intrinsics` 是**单个 3×3 矩阵**（不是「3 组」）、各槽位帧数**互不相同**
   （action 24960/24967、state 33323/34901、is_move 3471）、`subtask` 为空、
   视频文件叫 `top-left-camera.mp4`（⇒ 被 V02 判「多余文件」）。
   **本生成器不复制这些缺陷**：帧数生来对齐、subtask 非空且连续、文件名按 default.yaml。

用法
----
    /opt/conda/bin/python3 scripts/b2_make_demo_episodes.py \
        --out-root runs/vla/b2_bidir_demo_form_20260929/data --n-per-direction 3

写入面：只写 `--out-root` 指定的目录（默认在 `runs/vla/b2_*` 下）。
不 `rm`；不碰 `vla_pipeline`、不碰 `ABC130k`、不碰 `/workspace/.../datasets`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT_DEFAULT = Path(__file__).resolve().parents[1]
DATA_KIND_DEFAULT = "form_fixture_not_demonstration"

# 视频槽位（事实源：vla_pipeline/configs/default.yaml 的 files.videos / files.expected）
VIDEO_SLOTS = {"head": "top-camera.mp4",
               "left_wrist": "left-wrist-camera.mp4",
               "right_wrist": "right-wrist-camera.mp4"}
METADATA_NAME = "converted_metadata_normal.json"

# 17 个 DIMENSION_CONFIG 键（事实源：vla_pipeline/rules/qc/_meta.py，逐条抄，不自创）
DIMENSION_CONFIG = [
    ("action.left_arm.joint", 6), ("action.left_arm.pose", 7), ("action.left_arm.velocity", 6),
    ("action.left_gripper.joint", 1),
    ("action.right_arm.joint", 6), ("action.right_arm.pose", 7), ("action.right_arm.velocity", 6),
    ("action.right_gripper.joint", 1),
    ("state.left_arm.joint", 6), ("state.left_arm.pose", 7), ("state.left_arm.velocity", 6),
    ("state.left_gripper.joint", 1),
    ("state.right_arm.joint", 6), ("state.right_arm.pose", 7), ("state.right_arm.velocity", 6),
    ("state.right_gripper.joint", 1),
    ("is_move", 1),
]

# 区域 A / B 的 x 坐标（米，仿真尺度）。**单位与参考系待 A2 的 G2 契约表定稿**，
# 这里只保证两方向互为镜像，且数值量级与 SO100/ALOHA 类桌面任务一致。
REGION_X = {"A": -0.25, "B": 0.25}
TABLE_Z = 0.0
OBJ_HALF = 0.02
HOME = {"xyz": (0.0, -0.30, 0.35), "gripper": 0.85}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _quat_from_axis_angle(axis, angle):
    """单位四元数 [qx,qy,qz,qw]（C02 要求 |q|^2 ∈ [0.98,1.02]）。"""
    n = math.sqrt(sum(a * a for a in axis)) or 1.0
    ax = [a / n for a in axis]
    s = math.sin(angle / 2.0)
    return [ax[0] * s, ax[1] * s, ax[2] * s, math.cos(angle / 2.0)]


def _qmul(q1, q2):
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return [w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2]


def _sstep(t):
    """平滑阶跃（3t²-2t³）：保证逐帧位移小，避开 C03 的跳变阈（0.1 m / 30°）。"""
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def plan_trajectory(n_frames, direction, active_arm, fps):
    """解析合成一条「抓 A 放 B」或「抓 B 放 A」的轨迹。

    返回 per-frame dict 列表：{xyz, quat, gripper, phase}。
    两个方向**互为镜像**（src/dst 对调），这是 T17 目标条件的最小可用结构：
    同状态、同 θ、只换 goal（src↔dst）⇒ 轨迹必须不同。
    """
    src, dst = ("A", "B") if direction == "A_to_B" else ("B", "A")
    xs, xd = REGION_X[src], REGION_X[dst]
    # 阶段边界（比例固定，两个方向一致 ⇒ 差异只来自 goal，不来自时序）
    b = [int(n_frames * f) for f in (0.30, 0.45, 0.58, 0.85)]
    grasp_z = TABLE_Z + OBJ_HALF + 0.005
    frames = []
    for i in range(n_frames):
        if i < b[0]:                                     # ① 接近源区上方
            t = _sstep(i / max(1, b[0]))
            xyz = (HOME["xyz"][0] + (xs - HOME["xyz"][0]) * t,
                   HOME["xyz"][1] + (0.05 - HOME["xyz"][1]) * t,
                   HOME["xyz"][2] + (grasp_z + 0.12 - HOME["xyz"][2]) * t)
            g, phase = HOME["gripper"], "approach"
        elif i < b[1]:                                   # ② 下降 + 闭合
            t = _sstep((i - b[0]) / max(1, b[1] - b[0]))
            xyz = (xs, 0.05, (grasp_z + 0.12) + (grasp_z - (grasp_z + 0.12)) * t)
            g, phase = HOME["gripper"] + (0.15 - HOME["gripper"]) * t, "grasp"
        elif i < b[2]:                                   # ③ 提起
            t = _sstep((i - b[1]) / max(1, b[2] - b[1]))
            xyz = (xs, 0.05, grasp_z + 0.18 * t)
            g, phase = 0.15, "lift"
        elif i < b[3]:                                   # ④ 搬运到目标区上方
            t = _sstep((i - b[2]) / max(1, b[3] - b[2]))
            xyz = (xs + (xd - xs) * t, 0.05 - 0.10 * math.sin(math.pi * t),
                   grasp_z + 0.18)
            g, phase = 0.15, "transfer"
        else:                                            # ⑤ 下降 + 张开 + 回位
            t = _sstep((i - b[3]) / max(1, n_frames - 1 - b[3]))
            z = (grasp_z + 0.18) + (grasp_z + 0.02 - (grasp_z + 0.18)) * min(1.0, t * 2.0)
            xyz = (xd, 0.05 - 0.05 * t, z)
            g = 0.15 + (HOME["gripper"] - 0.15) * max(0.0, (t - 0.45) / 0.55)
            phase = "release"
        # 末端姿态：夹爪朝下（绕 x 转 180°）+ 随搬运方向轻微偏摆（可被 T17 检出）
        base = _quat_from_axis_angle((1.0, 0.0, 0.0), math.pi)
        tilt = _quat_from_axis_angle((0.0, 1.0, 0.0), 0.12 * (xd - xs) / 0.5 * (i / max(1, n_frames)))
        frames.append({"xyz": xyz, "quat": _qmul(base, tilt), "gripper": float(g),
                       "phase": phase, "src": src, "dst": dst})
    return frames


def joints_from_tcp(xyz, quat, active_arm):
    """把 TCP 位姿**解析地**映到 6 维关节序列（不是真 IK）。

    诚实边界：真实关节值必须由 A2 的仿真器/机器人给出；这里只是让 17 个字段
    **维度对、数值平滑、无 NaN**，好把 QC 管路先跑通。schema 里标 `synthesized_analytic`。
    """
    x, y, z = xyz
    sign = 1.0 if active_arm == "left" else -1.0
    return [round(math.atan2(y, 0.30 + x) * sign, 6),
            round(0.60 + 0.90 * z, 6),
            round(0.70 - 0.55 * z + 0.20 * x * sign, 6),
            round(-0.10 + 0.35 * y, 6),
            round(0.05 * sign + 0.30 * x, 6),
            round(0.25 * sign * (1.0 - abs(quat[2])), 6)]


def velocity_from(seq, i, fps):
    """一阶差分速度（末帧复制）。单位 = 关节单位/秒；**单位口径待 G2 定稿**。"""
    if i == 0:
        return [0.0] * len(seq[0])
    a, b = seq[i - 1], seq[i]
    return [round((b[k] - a[k]) * fps, 6) for k in range(len(a))]


def render_frames(traj, n_frames, width, height, direction, active_arm):
    """三路相机的合成帧（uint8 RGB）。head 看全局、两路 wrist 跟随各自末端。

    只做「与 metadata 一致的可视渲染」，不是相机模型投影（无外参标定）。
    """
    import numpy as np
    W, H = width, height
    src, dst = traj[0]["src"], traj[0]["dst"]

    def px(x, y):
        # 世界 x∈[-0.4,0.4] → 画布 u；世界 y∈[-0.4,0.2] → 画布 v
        u = int((x + 0.40) / 0.80 * (W - 1))
        v = int((y + 0.40) / 0.60 * (H - 1))
        return max(0, min(W - 1, u)), max(0, min(H - 1, v))

    def rect(img, cx, cy, r, color):
        x0, y0 = max(0, cx - r), max(0, cy - r)
        x1, y1 = min(W, cx + r + 1), min(H, cy + r + 1)
        img[y0:y1, x0:x1] = color

    head, lwrist, rwrist = [], [], []
    for i, f in enumerate(traj):
        x, y, z = f["xyz"]
        for buf, kind in ((head, "head"), (lwrist, "left_wrist"), (rwrist, "right_wrist")):
            img = np.zeros((H, W, 3), dtype=np.uint8)
            img[:] = (32, 34, 40)                       # 背景
            for reg, col in (("A", (70, 90, 190)), ("B", (70, 170, 100))):
                rx, ry = px(REGION_X[reg], 0.05)
                rect(img, rx, ry, max(3, W // 24), col)  # 区域 A / B
            ox, oy = px(x, y)
            r = max(2, int(W // 30 * (0.6 + z)))
            rect(img, ox, oy, r, (210, 70, 60))          # 物体/末端
            if kind != "head":                           # 腕部相机：以末端为中心
                img[:, :max(1, W // 20)] = (120, 120, 130)
            buf.append(img.tobytes())
    return {"head": head, "left_wrist": lwrist, "right_wrist": rwrist}


def write_video(path: Path, raw_frames, width, height, fps, ffmpeg="ffmpeg"):
    """用 ffmpeg 编 H.264/yuv420p。**帧数必须精确等于 len(raw_frames)**（H 规则要 json==video）。"""
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (width, height),
           "-r", str(fps), "-i", "-",
           "-frames:v", str(len(raw_frames)),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
           "-pix_fmt", "yuv420p", "-r", str(fps), str(path)]
    p = subprocess.run(cmd, input=b"".join(raw_frames), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg 失败 rc=%s: %s" % (p.returncode, (p.stderr or b"")[-500:]))
    return cmd


def probe_frames(path: Path, ffprobe="ffprobe"):
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames",
           "-show_entries", "stream=nb_read_frames,r_frame_rate", "-of", "json", str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    st = (json.loads(r.stdout).get("streams") or [{}])[0]
    num, _, den = (st.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den) if den and float(den) else None
    return {"nb_read_frames": st.get("nb_read_frames"), "fps": fps}


def build_episode(out_dir: Path, n_frames, fps, width, height, direction, active_arm,
                  task_text, subtasks, seed, data_kind, ffmpeg, ffprobe):
    ep_id = "episode_%s" % uuid.uuid5(uuid.NAMESPACE_OID, "%s|%s|%d" % (direction, task_text, seed))
    ep = out_dir / ep_id
    ep.mkdir(parents=True, exist_ok=True)
    traj = plan_trajectory(n_frames, direction, active_arm, fps)

    inactive = "right" if active_arm == "left" else "left"
    # 主动臂：由轨迹生成；非主动臂：**保持静态但字段齐全**（v4：另一臂不参与）
    seq = {}
    for side in (active_arm, inactive):
        if side == active_arm:
            joints = [joints_from_tcp(f["xyz"], f["quat"], side) for f in traj]
            poses = [[round(f["xyz"][0], 6), round(f["xyz"][1], 6), round(f["xyz"][2], 6)]
                     + [round(q, 6) for q in f["quat"]] for f in traj]
            grip = [[round(f["gripper"], 6)] for f in traj]
        else:
            j0 = joints_from_tcp((-REGION_X["A"] if side == "right" else REGION_X["A"],
                                  -0.28, 0.30), _quat_from_axis_angle((1, 0, 0), math.pi), side)
            p0 = [round(v, 6) for v in (j0[0] * 0.0, -0.28, 0.30)] + [0.0, 0.0, 0.0, 1.0]
            joints = [[round(v, 6) for v in j0] for _ in range(n_frames)]
            poses = [list(p0) for _ in range(n_frames)]
            grip = [[0.85] for _ in range(n_frames)]
        seq[side] = {"joint": joints, "pose": poses, "gripper": grip,
                     "velocity": [velocity_from(joints, i, fps) for i in range(n_frames)]}

    is_move = []
    for i in range(n_frames):
        if i == 0:
            is_move.append(0)
            continue
        d = math.dist(seq[active_arm]["pose"][i][:3], seq[active_arm]["pose"][i - 1][:3])
        is_move.append(1 if d > 1e-4 else 0)

    meta = {
        "task_info": task_text,
        "subtask": subtasks,
        "file_path": str(ep),
        "intrinsics": [[520.0, 0.0, width / 2.0], [0.0, 520.0, height / 2.0], [0.0, 0.0, 1.0]],
        "is_move": is_move,
        "frame_validity": {"is_valid": [True] * n_frames, "message": [[] for _ in range(n_frames)]},
        "action": {}, "state": {},
        # ↓ B2 自加的溯源字段（团队 schema 之外的键，QC 不读；用于防止这批产物被误当示范）
        "b2_provenance": {
            "data_kind": data_kind,
            "direction": direction,
            "src_region": traj[0]["src"], "dst_region": traj[0]["dst"],
            "active_arm": active_arm, "inactive_arm": inactive,
            "generator": "scripts/b2_make_demo_episodes.py",
            "trajectory_kind": "synthesized_analytic_not_robot_not_sim",
            "fps": fps, "n_frames": n_frames, "seed": seed,
            "pending_a2_g2": ["action_dimensions_and_order", "units", "reference_frames",
                              "gripper_semantics", "control_hz_vs_video_fps"],
        },
    }
    for side in ("left", "right"):
        for block in ("action", "state"):
            meta[block]["%s_arm" % side] = {"joint": seq[side]["joint"],
                                            "pose": seq[side]["pose"],
                                            "velocity": seq[side]["velocity"]}
            meta[block]["%s_gripper" % side] = {"joint": seq[side]["gripper"]}
        meta["%s_hand" % side] = {"joint": [], "pose": []}   # ABC130k 真实形态：手可空

    mp = ep / METADATA_NAME
    mp.write_text(json.dumps(meta, ensure_ascii=False) + "\n")

    vids = render_frames(traj, n_frames, width, height, direction, active_arm)
    vinfo = {}
    for slot, name in VIDEO_SLOTS.items():
        vp = ep / name
        cmd = write_video(vp, vids[slot], width, height, fps, ffmpeg)
        pr = probe_frames(vp, ffprobe) or {}
        vinfo[slot] = {"file": name, "bytes": vp.stat().st_size,
                       "nb_read_frames": pr.get("nb_read_frames"), "fps": pr.get("fps"),
                       "ffmpeg_cmd": " ".join(cmd[:6]) + " ..."}
    return ep, ep_id, meta, vinfo


DEFECT_KINDS = (
    "subtask_empty", "subtask_absent", "frame_mismatch", "frame_mismatch_small", "bad_fps",
    "field_missing", "dim_mismatch", "nan_value", "gripper_far", "still_all_open",
    "extra_file", "missing_video", "task_info_empty", "memory_empty",
    # ---- 第二批（2026-09-29 19:4x 加）：把负对照从「只覆盖 validate/qc 段」扩到 clean 段 ----
    # 第一批 14 条全部落在 V*/A–O（validate + qc），**clean 段的 C01/C02/C03 一条都没覆盖**
    # ⇒ Q4b 只能对 C04/C07/C08 说"结构性不可证"，对 C01/C02/C03 却连试都没试过。
    # 这三条是**变更型/标注型**算子，正常路径不写 badcase（事实源：各规则文件的类文档字符串
    # 「MutationRule: 贡献 rejected_indices」「AnnotationRule: 只标,不写盘」），所以它们的
    # 敏感性证据在**别的通道**上 ⇒ 期望表里带 `primary_channel`，由 b2_run_team_qc.py 的 Q5 按通道核。
    "video_corrupt", "metadata_corrupt", "metadata_badformat",
    "is_move_short_small", "is_move_short_large",
    "static_head_tail", "pose_jump", "quat_denorm",
)
# 期望值 = **实测**得来，不是猜的（本仓纪律：实测值即期望值）。
# 实测环境：团队 vla_pipeline @ /workspace/mnt/sppro/yhzhang91/scripts/yhzhang91/vla_pipeline
#（只读；config sha256 记在 qc_verdict.json），base python3（av 17.1.0 / click 8.4.2），
# 数据集 = 本生成器 300 帧 @30fps 160x120 双臂形态。
# `primary` 是**点名该缺陷的那条规则**（必须触发，否则判 QC 不敏感）；
# `also_observed` 是同一缺陷连带触发的规则（记录用，不作为硬判据，避免把连带效应当牙）。
DEFECT_EXPECT = {
    # ------------------------------------------------------------------
    # 全表**实测校准**（本仓纪律：实测值即期望值，负对照期望从实测来，不猜）
    #   校准时间：2026-09-29 19:5x（第一轮 22 条负对照全量跑）
    #   事实源 db：runs/vla/b2_bidir_demo_form_20260929/qc_calib/neg/b2_neg_20260929T195039/pipeline.db
    #   团队流水线：/workspace/mnt/sppro/yhzhang91/scripts/yhzhang91/vla_pipeline（只读；
    #               config sha256 记在 qc_verdict.json），运行时 /opt/conda/bin/python3
    #   数据集：本生成器 300 帧 @30fps 160x120 双臂形态，22 条 = 22 种缺陷各一条（单缺陷构造）
    # 字段口径：
    #   primary        = **点名**该缺陷的规则（必须触发，否则判 QC 不敏感 ⇒ Q5 红）
    #   also_observed  = 同一缺陷连带触发的规则（记录用，不作硬判据；写进来是为了让 Q5 的
    #                    "触发了但期望表里没有"这颗牙只对**真意外**报警，不被连带效应淹掉）
    #   primary_channel= primary 的证据落在哪条通道（默认 badcase）：
    #       badcase           events.event='badcase' 且 rule 命中
    #       clean_rejected    clean 段 episode_done 的 detail_json.rejected_count > 0
    #                         （C01/C03 是 MutationRule，正常路径**不写 badcase**）
    #       clean_rule_event  clean 段该 rule 自己的事件 detail 里点名键非空
    #                         （C02 是 AnnotationRule「只标,不写盘」，这是它唯一的通道）
    #   expected_but_not_observed = 按 config 注释**应该**触发、实测**没有**的规则
    #                         （只报观测不下结论，那是团队资产；已作为 RR-B2-04 上报 D）
    # ------------------------------------------------------------------
    "subtask_empty":        {"primary": ["V09"], "also_observed": ["A", "N", "O", "V10"]},
    "subtask_absent":       {"primary": ["V11"], "also_observed": ["A", "K", "N", "O", "V09", "V10"]},
    "frame_mismatch":       {"primary": ["C"],   "also_observed": ["H", "N", "V09"]},
    # 实测更正（第二轮仍成立）：截 **action** 数组差 3 帧（<= frame_diff_threshold=5）时
    # 触发的是 C/H/N/V09，**没有** V07。default.yaml 的注释写「1..threshold -> V07 (repairable)」
    # ⇒ 观测与注释不符。谜底已实测到：V07/V08 比的是**视频帧数 vs len(is_move)**
    # （rules/validate/frame_mismatch.py:49），不是 action 长度 —— 见 is_move_short_small/large
    # 两条正对照（它们**确实**分别触发了 V07 与 V08）。仍只报观测，不改团队代码。
    "frame_mismatch_small": {"primary": ["C"],   "also_observed": ["H", "N", "V09"],
                             "expected_but_not_observed": ["V07"]},
    "bad_fps":              {"primary": ["V04"], "also_observed": ["G", "J"]},
    "field_missing":        {"primary": ["A"],   "also_observed": []},
    "dim_mismatch":         {"primary": ["B"],   "also_observed": []},
    "nan_value":            {"primary": ["D"],   "also_observed": []},
    "gripper_far":          {"primary": ["E"],   "also_observed": []},
    # 实测：这条除了 qc 的 I，clean 段还把它**整条 300 帧全拒**（rejected_count=300）
    # 并连带 C04 的 `reencode_error` 事件 ⇒ 它同时是 C01 的一条（非专门的）敏感性证据。
    "still_all_open":       {"primary": ["I"],   "also_observed": [],
                             "measured_clean": {"rejected_count": 300,
                                                "badcase_keys": ["C04"],
                                                "events": ["C04:reencode_error"]}},
    "extra_file":           {"primary": ["V02"], "also_observed": []},
    "missing_video":        {"primary": ["V01"], "also_observed": []},
    "task_info_empty":      {"primary": ["V12"], "also_observed": ["A", "L"]},
    "memory_empty":         {"primary": ["V13"], "also_observed": ["M"]},
    # ---- 第二批（8 条）：全部按 19:5x 实测填 ----
    "video_corrupt":        {"primary": ["V03"], "also_observed": ["G", "H"]},
    # metadata 不可解析 ⇒ 下游**全线**红（21 条规则）。这不是"期望表膨胀"，是实测事实：
    # 读不到 metadata 时每条依赖它的规则各自报一次。primary 仍只认 V05（点名"读取失败"的那条）。
    "metadata_corrupt":     {"primary": ["V05"],
                             "also_observed": ["A", "B", "C", "D", "E", "H", "I", "K", "L", "M",
                                               "N", "O", "V06", "V07", "V08", "V09", "V10",
                                               "V11", "V12", "V13"],
                             "measured_clean": {"rejected_count": 0,
                                                "badcase_keys": ["C01", "C03", "C06", "C08"],
                                                "note": ("这里的 badcase_keys 是**可读**的规则名"
                                                         "（各 C 规则的「metadata 读取失败」分支）； "
                                                         "pose_jump 那条的键是字面 0（C03 warning "
                                                         "走的是另一条写盘路径）⇒ 键名口径不统一，"
                                                         "归因不能只靠它")}},
    "metadata_badformat":   {"primary": ["V06"], "also_observed": ["A", "C"]},
    # V07 的**正对照**：截 is_move 差 3 帧（<=5）⇒ V07 触发（连带 C/H/N）。
    # 这条与 frame_mismatch_small 合起来把 RR-B2-04 的谜底钉死：V07 比的是 len(is_move)。
    "is_move_short_small":  {"primary": ["V07"], "also_observed": ["C", "H", "N"]},
    # V08 的正对照：差 8 帧（>5）⇒ V08（连带 C/N），且 clean 段的 C08（frame_align）报 badcase。
    "is_move_short_large":  {"primary": ["V08"], "also_observed": ["C", "N"],
                             "measured_clean": {"rejected_count": 0, "badcase_keys": ["C08"]}},
    # C01：实测 rejected_count=6 == 预测值（静止 156 帧 - window 150 帧 = 6 帧"多余"）；
    # 连带 qc 的 I（异常静止）。primary 走 clean_rejected 通道（C01 正常路径不写 badcase）。
    "static_head_tail":     {"primary": ["C01"], "also_observed": ["I"],
                             "primary_channel": "clean_rejected",
                             "measured_clean": {"rejected_count": 6, "badcase_keys": []}},
    # C03：实测 rejected_count=8（连续 8 帧 +0.5m 全被拒）、badcase_keys=["0"]（不可读的字面键），
    # 且 **events 表里一条 badcase 都没有** ⇒ 只能走 clean_rejected 通道。
    "pose_jump":            {"primary": ["C03"], "also_observed": [],
                             "primary_channel": "clean_rejected",
                             "measured_clean": {"rejected_count": 8, "badcase_keys": ["0"]}},
    # C02：实测**唯一**通道是它自己那条 clean 事件 `quaternion_problems`；
    # badcase 0 条、rejected_count 0（AnnotationRule 只标不写盘），rule_stats.C02.badcase_count=0。
    # 且如预测：×0.5 缩放**没有**连带触发 C03（quat_angle_deg 先归一化，q 与 0.5q 夹角为 0）。
    # 实测事件形态（19:5x，qc_b2/neg/b2_neg_20260929T195800/pipeline.db）：
    #   `rule='C02', event='quaternion_problems', detail_json={"count": 6}`
    # ⇒ **事件名**才是规则点名的地方，detail 里只有计数（不是问题清单）；核法必须两件都要：
    #   事件名命中 + detail['count'] 非零。第一版把 detail 键写成 'quaternion_problems'
    #   （拿事件名当 detail 键）⇒ 查空 ⇒ C02 被记成"未触发"（假红）。
    "quat_denorm":          {"primary": ["C02"], "also_observed": [],
                             "primary_channel": "clean_rule_event",
                             "primary_event_name": "quaternion_problems",
                             "primary_detail_key": "count",
                             "measured_clean": {"rejected_count": 0, "badcase_keys": [],
                                                "events": ["C02:quaternion_problems"],
                                                "event_detail": {"count": 6},
                                                "n_frames_injected": 3,
                                                "note": ("注入 3 帧 × 2 个 pose 键（action+state 的 "
                                                         "left_arm.pose）= 6 处 ⇒ detail.count=6，"
                                                         "与注入数一致（可用来核 C02 是不是**逐处**在数）")}},
}

def inject_defect(ep: Path, kind: str, n_frames: int, fps: int, width: int, height: int,
                  ffmpeg: str):
    """往一条已生成的 episode 里注入**一个**已知缺陷，返回期望抓住它的规则键。

    为什么必须有负对照：团队 QC 跑完报「0 badcase」有两种可能 —— 数据真合格，
    或者**算子根本没跑**（本仓吃过这个亏：空比对的「0 处变化」是空洞真，V6 专门单列一条红）。
    所以每种缺陷都要能被点名的规则抓住；抓不到就判 QC 管路对我们这批数据不敏感。
    """
    mp = ep / METADATA_NAME
    meta = json.loads(mp.read_text())

    def _save():
        mp.write_text(json.dumps(meta, ensure_ascii=False) + "\n")

    if kind == "subtask_empty":
        meta["subtask"] = []
        _save()
    elif kind == "subtask_absent":
        del meta["subtask"]
        _save()
    elif kind == "frame_mismatch":
        for k in ("joint", "pose", "velocity"):
            meta["action"]["left_arm"][k] = meta["action"]["left_arm"][k][:-6]
        meta["action"]["left_gripper"]["joint"] = meta["action"]["left_gripper"]["joint"][:-6]
        _save()
    elif kind == "frame_mismatch_small":
        # 差 3 帧（<= frame_diff_threshold=5）⇒ 走 V07（可修复）而不是 V08
        for k in ("joint", "pose", "velocity"):
            meta["action"]["left_arm"][k] = meta["action"]["left_arm"][k][:-3]
        _save()
    elif kind == "field_missing":
        del meta["action"]["left_arm"]["velocity"]
        _save()
    elif kind == "dim_mismatch":
        meta["action"]["left_arm"]["joint"] = [r[:5] for r in meta["action"]["left_arm"]["joint"]]
        _save()
    elif kind == "nan_value":
        meta["state"]["left_arm"]["joint"][n_frames // 2][2] = float("nan")
        _save()
    elif kind == "gripper_far":
        # 把非主动臂末端挪到 2.4 m 外（> euclidean_threshold=1.5）⇒ E
        for r in meta["action"]["right_arm"]["pose"]:
            r[0] = r[0] + 2.4
        for r in meta["state"]["right_arm"]["pose"]:
            r[0] = r[0] + 2.4
        _save()
    elif kind == "still_all_open":
        # 全程零位移 + 两夹爪全开（0.85 > gripper_open_threshold=0.6）⇒ I（异常静止）
        j0 = meta["action"]["left_arm"]["joint"][0]
        p0 = meta["action"]["left_arm"]["pose"][0]
        for side in ("left", "right"):
            for blk in ("action", "state"):
                meta[blk]["%s_arm" % side]["joint"] = [list(j0) for _ in range(n_frames)]
                meta[blk]["%s_arm" % side]["pose"] = [list(p0) for _ in range(n_frames)]
                meta[blk]["%s_arm" % side]["velocity"] = [[0.0] * 6 for _ in range(n_frames)]
                meta[blk]["%s_gripper" % side]["joint"] = [[0.85] for _ in range(n_frames)]
        meta["is_move"] = [0] * n_frames
        _save()
    elif kind == "task_info_empty":
        meta["task_info"] = ""
        _save()
    elif kind == "memory_empty":
        for st in meta["subtask"]:
            st["memory"] = ""
        _save()
    elif kind == "extra_file":
        (ep / "unexpected-extra-file.mp4").write_bytes(b"not-a-video")
    elif kind == "missing_video":
        # 不 rm：mv 到 episode 目录外的暂存处（AGENTS.md 禁 rm）
        stash = ep.parent / (".stashed_%s" % VIDEO_SLOTS["right_wrist"])
        stash.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(ep / VIDEO_SLOTS["right_wrist"]), str(stash))
    elif kind == "bad_fps":
        vp = ep / VIDEO_SLOTS["head"]
        raw = b"\x20\x22\x28" * (width * height) * n_frames
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", "%dx%d" % (width, height), "-r", "20", "-i", "-",
               "-frames:v", str(n_frames), "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "30", "-pix_fmt", "yuv420p", "-r", "20", str(vp)]
        r = subprocess.run(cmd, input=raw, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg(负对照 bad_fps) 失败：%s" % (r.stderr or b"")[-300:])
    # ---- 第二批：validate 段剩下的三条 + is_move 两档 + clean 段三条 ----
    elif kind == "video_corrupt":
        # V03：pyav 探测失败。文件**仍在**（⇒ V01「缺失文件」不红），红的是"读不出来"
        (ep / VIDEO_SLOTS["head"]).write_bytes(b"\x00\x01\x02\x03not-an-mp4" * 64)
    elif kind == "metadata_corrupt":
        # V05：JSON 解析失败（截掉后半，括号不闭合）。不 rm、不改名，只改内容
        txt = mp.read_text()
        mp.write_text(txt[: max(1, len(txt) // 2)])
    elif kind == "metadata_badformat":
        # V06：四个 pose 时间序列全部置空 ⇒ get_frame_reference 只能落到 DIMENSION_CONFIG 的
        # joint 键上，而它不在 POSE_KEYS 里 ⇒ 「缺少有效 pose 时间序列」。
        # 置**空列表**而不是删键：删键会先被 A（field_missing）抓到，归因就糊了。
        for blk in ("action", "state"):
            for side in ("left", "right"):
                meta[blk]["%s_arm" % side]["pose"] = []
        _save()
    elif kind == "is_move_short_small":
        # V07：diff = 视频帧数 - len(is_move) = 3 ≤ frame_diff_threshold(5) ⇒ "可修复"档。
        # 截的是 **is_move**（不是 action）：V07 比的就是视频帧数 vs len(is_move)，
        # 第一批的 frame_mismatch_small 截 action 所以没触发它（RR-B2-04 的谜底）。
        meta["is_move"] = meta["is_move"][:-3]
        _save()
    elif kind == "is_move_short_large":
        # V08：diff = 8 > 5 ⇒ "不可自动修复"档
        meta["is_move"] = meta["is_move"][:-8]
        _save()
    elif kind == "static_head_tail":
        # C01：开头 5.2 s（=156 帧 @30fps > window=fps*static_check_seconds=150）完全静止
        # + 四路夹爪全开（0.85 > static_open_threshold=0.6）⇒ 删掉超出 window 的 6 帧。
        # 做法是把第 n_static 帧的姿态**复制**到 0..n_static-1（不是把位移插值成 0），
        # 这样静止段与后续轨迹在衔接处**连续**，不会顺带造出 C03 的位姿跳变
        # —— 一条负对照同时踩两颗牙，归因就糊了（Q4b 的"单缺陷 episode"构造也就不成立）。
        ref = min(n_frames - 1, int(round(fps * 5.2)))
        for side in ("left", "right"):
            for blk in ("action", "state"):
                arm = meta[blk]["%s_arm" % side]
                grip = meta[blk]["%s_gripper" % side]
                for k in ("joint", "pose"):
                    arm[k][:ref] = [list(arm[k][ref]) for _ in range(ref)]
                arm["velocity"][:ref] = [[0.0] * len(arm["velocity"][ref]) for _ in range(ref)]
                grip["joint"][:ref] = [[0.85] for _ in range(ref)]
        meta["is_move"][:ref] = [0] * ref
        _save()
    elif kind == "pose_jump":
        # C03：连续 8 帧位置 +0.5 m（> position_threshold=0.1），8 >= max_consecutive_rejections=5
        # ⇒ detail.warning=True（`stages/clean.py` 才把它升成 badcase，键名是字面 "0"）。
        # action 与 state 的同侧 pose 一起改：POSE_KEYS 四个键取**并集**拒帧，改一个键就够，
        # 但只改 action 会让 action/state 不一致，可能连带触发一致性规则（归因糊）。
        j0 = n_frames // 3
        for blk in ("action", "state"):
            arr = meta[blk]["left_arm"]["pose"]
            for i in range(j0, min(len(arr), j0 + 8)):
                arr[i][0] = round(arr[i][0] + 0.5, 6)
        _save()
    elif kind == "quat_denorm":
        # C02：四元数 ×0.5 ⇒ |q|²=0.25 ∉ [min_norm_sq=0.98, max_norm_sq=1.02]。
        # **不会**连带触发 C03：`common/pose_math.py:18-30` 的 quat_angle_deg 先各自归一化
        # 再算夹角，q 与 0.5q 归一化后逐字相同 ⇒ 夹角 0。这正是 C02（合法性）与 C03（跳变）
        # 的口径分工，也是 C02 必须走 `clean_detail` 通道（AnnotationRule 只标不写盘）的原因。
        j0 = n_frames // 3
        for blk in ("action", "state"):
            arr = meta[blk]["left_arm"]["pose"]
            for i in (j0, j0 + 1, j0 + 2):
                if i < len(arr):
                    for j in (3, 4, 5, 6):
                        arr[i][j] = round(arr[i][j] * 0.5, 6)
        _save()
    else:
        raise ValueError("未知缺陷类型：%s" % kind)
    return DEFECT_EXPECT[kind]


def selfcheck_episode(meta, vinfo, n_frames, fps):
    """**出厂自检**：把团队 QC 会查的形态约束在本地先判一遍（不代替 QC，只提早暴露）。"""
    bad = []
    for key, dim in DIMENSION_CONFIG:
        cur = meta
        for part in key.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if not isinstance(cur, list):
            bad.append("缺字段 %s" % key)
            continue
        if len(cur) != n_frames:
            bad.append("%s 帧数 %d != %d" % (key, len(cur), n_frames))
            continue
        if key != "is_move" and cur and not isinstance(cur[0], list):
            bad.append("%s 每帧不是 list" % key)
        elif key != "is_move" and any(len(r) != dim for r in cur):
            bad.append("%s 每帧维度 != %d" % (key, dim))
    for f in ("task_info", "subtask", "file_path"):
        if not meta.get(f):
            bad.append("META_FIELDS 缺 %s" % f)
    st = meta.get("subtask") or []
    if not st:
        bad.append("subtask 为空（V09/V10/N/O/K 会红）")
    else:
        if st[0].get("range", [None])[0] != 0:
            bad.append("subtask[0].range[0] != 0（V10）")
        for i in range(1, len(st)):
            if st[i]["range"][0] != st[i - 1]["range"][1] + 1:
                bad.append("subtask range 不连续 @%d（V10/O）" % i)
        if max(s["range"][1] for s in st) != len(meta["is_move"]) - 1:
            bad.append("subtask range 末端 != len(is_move)-1（N）")
        for i, s in enumerate(st):
            if not str(s.get("memory") or "").strip():
                bad.append("subtask[%d].memory 为空（M/V13）" % i)
    for slot, v in vinfo.items():
        if str(v.get("nb_read_frames")) != str(n_frames):
            bad.append("%s 视频帧数 %s != json %d（H/V07/V08）" % (slot, v.get("nb_read_frames"), n_frames))
        if v.get("fps") is None or not (29.0 <= float(v["fps"]) <= 31.0):
            bad.append("%s fps %s 不在 [29,31]（V04/J）" % (slot, v.get("fps")))
    return bad


def main():
    ap = argparse.ArgumentParser(description="B2 线：双向 episode 形态生成器（**不是**示范数据）")
    ap.add_argument("--out-root", default="runs/vla/b2_bidir_demo_form_20260929/data")
    ap.add_argument("--split", default="train")
    ap.add_argument("--n-per-direction", type=int, default=3,
                    help="每个方向的条数（D→B2 §2.2：**两个方向必须相当**）")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--fps", type=int, default=30, help="必须落在 QC 的 [29,31] 内")
    ap.add_argument("--width", type=int, default=160)
    ap.add_argument("--height", type=int, default=120)
    ap.add_argument("--active-arm", choices=["left", "right"], default="left",
                    help="v4：首任务一臂抓取放，另一臂不参与")
    ap.add_argument("--task-forward", default="move the cube from region A to region B")
    ap.add_argument("--task-reverse", default="move the cube from region B to region A")
    ap.add_argument("--inject-defects", action="store_true",
                    help="负对照模式：每条 episode 注入一个**已知**缺陷，用来证明 QC 管路不是空洞真")
    ap.add_argument("--data-kind", default=DATA_KIND_DEFAULT,
                    help="盖在每条 episode 与 manifest 上的戳；默认明示「形态夹具，非示范」")
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    ap.add_argument("--root", default=str(ROOT_DEFAULT))
    a = ap.parse_args()

    root = Path(a.root).resolve()
    out_root = Path(a.out_root)
    if not out_root.is_absolute():
        out_root = root / out_root
    split_dir = out_root / a.split
    split_dir.mkdir(parents=True, exist_ok=True)

    if not (29.0 <= float(a.fps) <= 31.0):
        print("** fps=%s 不在 QC 的 [29,31] 内，V04/J 必红；先改 fps" % a.fps)
        sys.exit(2)

    subs = [{"range": [0, int(a.frames * 0.45) - 1], "memory": "approach and grasp the cube"},
            {"range": [int(a.frames * 0.45), int(a.frames * 0.58) - 1], "memory": "lift the cube"},
            {"range": [int(a.frames * 0.58), a.frames - 1], "memory": "transfer and release at target region"}]

    episodes, all_bad = [], []
    for d_idx, (direction, task_text, task_dir) in enumerate([
            ("A_to_B", a.task_forward, "move_cube_A_to_B"),
            ("B_to_A", a.task_reverse, "move_cube_B_to_A")]):
        for k in range(a.n_per_direction):
            seed = a.seed0 + d_idx * 100 + k
            ep, ep_id, meta, vinfo = build_episode(
                split_dir / task_dir, a.frames, a.fps, a.width, a.height,
                direction, a.active_arm, task_text, [dict(s) for s in subs], seed,
                a.data_kind, a.ffmpeg, a.ffprobe)
            defect = None
            parsable = True
            if a.inject_defects:
                idx = d_idx * a.n_per_direction + k
                kind = DEFECT_KINDS[idx % len(DEFECT_KINDS)]
                expect = inject_defect(ep, kind, a.frames, a.fps, a.width, a.height, a.ffmpeg)
                defect = {"kind": kind, "expected_badcase_keys": expect}
                try:
                    meta = json.loads((ep / METADATA_NAME).read_text())
                except Exception as e:
                    # `metadata_corrupt` 这条负对照**就是要**让文件不可解析（那正是 V05 的判据）。
                    # 第一版在这里崩了：注入完立刻无条件回读 ⇒ 一条负对照把整个生成器带崩，
                    # 后面 20 条一个都没生成。缺陷注入的副作用必须由注入方自己兜住。
                    meta, parsable = None, False
                    print("    注：%s 注入后 metadata 不可解析（%s）——这是该缺陷的定义，"
                          "不是生成器故障" % (kind, type(e).__name__))
                vinfo = {slot: dict(v, **({"fps": 20.0} if (kind == "bad_fps" and slot == "head")
                                          else {})) for slot, v in vinfo.items()}
            bad = [] if a.inject_defects else selfcheck_episode(meta, vinfo, a.frames, a.fps)
            all_bad.extend(["%s: %s" % (ep_id, b) for b in bad])
            episodes.append({
                "episode_id": ep_id, "direction": direction, "task_dir": task_dir,
                "task_info": task_text, "path": str(ep), "seed": seed,
                "n_frames": a.frames, "fps": a.fps,
                "metadata_sha256": _sha256(ep / METADATA_NAME),
                "metadata_bytes": (ep / METADATA_NAME).stat().st_size,
                "metadata_parsable_after_injection": parsable,
                "videos": vinfo, "selfcheck_badcases": bad,
                "data_kind": (a.data_kind if not a.inject_defects
                              else "negative_control_defective_by_design"),
                "negative_control": defect,
            })
            print("  [%s] %s frames=%d fps=%d 自检违例=%d"
                  % (direction, ep_id, a.frames, a.fps, len(bad)))

    per_dir = {}
    for e in episodes:
        per_dir[e["direction"]] = per_dir.get(e["direction"], 0) + 1
    manifest = {
        "dataset_kind": (a.data_kind if not a.inject_defects
                         else "negative_control_defective_by_design"),
        "negative_control": (None if not a.inject_defects else {
            "purpose": ("证明「QC 报 0 badcase」不是空洞真：每条 episode 带一个**已知**缺陷，"
                        "必须被点名的规则抓住（同 V6 对空比对单列一条红的纪律）"),
            "defect_expect": DEFECT_EXPECT,
            "n_defective": len(episodes)}),
        "NOT_A_DEMONSTRATION_DATASET": (
            "本目录是**形态/QC 管路验证夹具**：轨迹为解析合成（`trajectory_kind="
            "synthesized_analytic_not_robot_not_sim`），不来自任何机器人或仿真器。"
            "**不得**当示范喂训练，**不得**用它声称双向能力（D→B2 §5）。"),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_by": "scripts/b2_make_demo_episodes.py",
        "out_root": str(out_root), "split": a.split,
        "n_episodes": len(episodes), "n_per_direction": per_dir,
        "directions_balanced": (len(set(per_dir.values())) == 1 and len(per_dir) == 2),
        "frame_alignment": "born_aligned（json 17 个 DIMENSION_CONFIG 字段与三路视频**同帧数**）",
        "form_fact_sources": [
            "vla_pipeline/rules/qc/_meta.py（DIMENSION_CONFIG 17 键 / META_FIELDS / pose 内序）",
            "vla_pipeline/configs/default.yaml（视频槽位与文件名 / fps∈[29,31] / expected 文件）",
            "vla_pipeline/samples/demo_data/dual_arm_ok（团队自带已知合格参照）",
            "workplace/ABC130k/train/<task>/episode_<uuid>（真实语料，只读实测）",
        ],
        "pending_a2_g2": ["action_dimensions_and_order", "units", "reference_frames",
                          "gripper_semantics", "control_hz_vs_video_fps", "sim_env_choice"],
        "selfcheck_total_badcases": len(all_bad),
        "selfcheck_badcases": all_bad[:40],
        "episodes": episodes,
    }
    (out_root / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print("\n写出 manifest:", out_root / "dataset_manifest.json")
    print("条数：共 %d，按方向 %s，均衡=%s" % (len(episodes), per_dir,
                                              manifest["directions_balanced"]))
    print("出厂自检违例：%d 条%s" % (len(all_bad), "" if not all_bad else " ⇒ 见 manifest"))
    total = sum((e["metadata_bytes"] + sum(v["bytes"] for v in e["videos"].values()))
                for e in episodes)
    print("数据集体积：%.2f MiB（NFS 已用 94%%；> 10 GB 须先申报，本次远低于）" % (total / (1 << 20)))
    sys.exit(1 if all_bad else 0)


if __name__ == "__main__":
    main()
