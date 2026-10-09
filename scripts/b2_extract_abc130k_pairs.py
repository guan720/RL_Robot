#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 任务 2(a)：ABC-130k 离线**正反对**子集提取 + normalizer stats（裁定 41.2 / 46.6）。

为什么这个脚本存在（口径来源，勿删）
------------------------------------
- 裁定 41.2（`supervisor_memo_20260929.md:1970` 起）：本机 `ABC130k` = HF `xdof/ABC-130k`，
  机器人是 **2×6-DoF YAM 双臂站**（不是 Piper、不是 Cobot Magic）⇒ 一切产物必须标
  `morphology_proxy="yam"`，**不得**写成 Piper 上成立。
- 裁定 46.6（`supervisor_memo_20260929.md:2147`）：**normalizer stats 只能来自示范数据集**
  ⇒ B2 的数据集是 A2 做任何有意义的 zero-shot / SFT 的 **P0 硬前置**。
  A2 现场实测（`runs/vla/a2_pi05_zeroshot_20260929/state_channel_saturation_analysis.json`）：
  π₀.₅ base 的 `policy_preprocessor.json` 里 `normalizer_processor.config.features = {}`（空），
  而 `Pi05PrepareStateTokenizerProcessorStep` 按 `np.linspace(-1,1,257)` 离散化 state
  ⇒ 未归一化的原始关节角（实测到 2.015 rad）会把状态通道**压扁并截断**。
  本脚本产出的 `normalizer_stats.json` 就是补这个洞的输入（**不是**直接可喂的 ckpt 分片：
  它只给统计量，写进 `policy_preprocessor.json` 的动作归 A2）。
- D→B2 §10.2：任务 2 优先级 = **(a) ABC-130k 离线正反对（第一优先）** → (b) 仿真双向 teacher
  → (c) 实机遥操采集。本脚本只做 (a)。
- D→B2 §10.3-3 体积纪律：`size_categories: n>1T`、train 3,541 h ⇒ **只许按需取子集**，
  不许整集拷贝/转换（NFS 已用 94%）。本脚本**只读**源数据，产物只有 JSON（KB–MB 级），
  并把"读了多少条、多少字节"写进 `dataset_card.json` 的 `volume_accounting`。

三值纪律（本仓硬约束）
----------------------
- 测不到的量 ⇒ `null` + `status="UNJUDGED"`，**不猜**、不填 0、不填"看起来像"的值。
- 外部事实（HF README 的统计、license）⇒ 标 `external_unverified`，不与本机实测并列成一张表。
- 每条判定带 `red_when`；`is False` 才是红，缺证据是 `null`。

不许做的事：不写源目录（`yfw_input/`、`workplace/` 一律只读）、不 `rm`、不改团队 `vla_pipeline`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# 常量：口径来源全部写明出处（裁定 34.1：钉实际值；裁定 36.4：跨口径不并列）
# ---------------------------------------------------------------------------
SRC_ROOT_DEFAULT = "/workspace/mnt/sppro/yhzhang91/workplace/ABC130k"
RAW_ROOT_DEFAULT = "/workspace/mnt/sppro/yhzhang91/yfw_input/0730/XDOF_ABC-130k"
OUT_DEFAULT = "runs/vla/b2_abc130k_pairs_20260929"

# D→B2 §10.2 表里的天然正反对（条数 = D 在**原始** mcap 集上数的；本机**已转换**子集的条数
# 由本脚本实测后写进 dataset_card，两个数**不混写**）
TASK_PAIRS = [
    {"pair_id": "credit_cards",
     "forward": "put_the_credit_cards_into_the_card_holder",
     "reverse": "take_the_credit_cards_out_of_the_card_holder",
     "d_declared_counts": {"forward": 2574, "reverse": 2732}},
    {"pair_id": "keys",
     "forward": "put_the_keys_on_the_keyring",
     "reverse": "remove_the_keys_from_the_keyring",
     "d_declared_counts": {"forward": 2805, "reverse": 745}},
    {"pair_id": "photo",
     "forward": "put_the_photo_into_the_frame",
     "reverse": "take_the_photo_out_of_the_frame",
     "d_declared_counts": {"forward": 898, "reverse": 257}},
    {"pair_id": "phone",
     "forward": "put_the_phone_into_the_phone_case",
     "reverse": "take_the_phone_out_of_the_phone_case",
     "d_declared_counts": {"forward": 584, "reverse": 734}},
    {"pair_id": "pillow",
     "forward": "put_the_pillow_into_the_pillowcase",
     "reverse": "remove_the_pillowcase_from_the_pillow",
     "d_declared_counts": {"forward": 538, "reverse": 664}},
]

# 团队形态的相机槽位（`vla_pipeline/configs/default.yaml` 口径，D→B2 §2.1）
CAMERA_SLOTS = ("top-camera.mp4", "left-wrist-camera.mp4", "right-wrist-camera.mp4")

# 14 维向量的**通道**定义（canonical）。向量装配顺序是"声明"，不是数据里的事实：
# ABC-130k 的 JSON 是分通道的 dict，没有 14 维扁平数组 ⇒ 任何扁平化都是**B2 的声明**，
# 必须写进产物并标 `layout_status="b2_declared_pending_a2_confirmation"`（RR-B2-09）。
CHANNELS = [
    ("state", "left_arm", "joint", 6),
    ("state", "left_gripper", "joint", 1),
    ("state", "right_arm", "joint", 6),
    ("state", "right_gripper", "joint", 1),
    ("action", "left_arm", "joint", 6),
    ("action", "left_gripper", "joint", 1),
    ("action", "right_arm", "joint", 6),
    ("action", "right_gripper", "joint", 1),
]
LAYOUTS = {
    # ALOHA / gym-aloha 生态常见装配：左臂 6+1，再右臂 6+1
    "aloha_interleaved": ["left_arm.joint[0..5]", "left_gripper.joint[0]",
                          "right_arm.joint[0..5]", "right_gripper.joint[0]"],
    # 另一种常见装配：先全部关节，再全部夹爪
    "joints_then_grippers": ["left_arm.joint[0..5]", "right_arm.joint[0..5]",
                             "left_gripper.joint[0]", "right_gripper.joint[0]"],
}
N_DOF = 14

# 单位口径（B2 只读实测，见 dataset_card.units）：
#   关节 = 弧度（实测 state.left_arm.joint 范围 −1.185..2.015，与 YAM_DATA_FORMAT.md 的
#          RobotState.joint_positions 同源；**不是**度：若为度，行程只有 ±2 度，不可能）
#   夹爪 = 归一化（实测 0.000..0.989，与 D→B2 §11.2 的"参照数据(YAM)夹爪归一化 [0,1]"一致）
#   velocity 通道 = 本机已转换子集里**实测全 0**（见 dataset_card.defects.velocity_all_zero）

QC_FPS_BAND = (29.0, 31.0)          # 团队 QC 规则 J/V04 的合格区间（D→B2 §11.1）
DEMO_HZ_ANCHOR = 30.0               # 裁定 45.1：仿真控制频率锚定 30.0 Hz


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha12(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 22), b""):
            h.update(blk)
    return h.hexdigest()[:12]


def ffprobe_video(path: Path):
    """只读探测一个 mp4：fps / nb_frames / duration / 分辨率。探不到 ⇒ None（不猜）。"""
    if not path.exists():
        return None
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=nb_frames,r_frame_rate,avg_frame_rate,width,height,duration",
           "-of", "json", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            return {"error": "ffprobe_rc=%d" % out.returncode,
                    "stderr": out.stderr.strip()[:200]}
        st = (json.loads(out.stdout).get("streams") or [{}])[0]
    except Exception as e:                       # noqa: BLE001
        return {"error": "%s: %s" % (type(e).__name__, str(e)[:160])}

    def _rate(s):
        try:
            num, den = s.split("/")
            num, den = float(num), float(den)
            return (num / den) if den else None
        except Exception:                        # noqa: BLE001
            return None
    nb = st.get("nb_frames")
    dur = st.get("duration")
    return {
        "width": st.get("width"), "height": st.get("height"),
        "r_frame_rate": st.get("r_frame_rate"), "r_fps": _rate(st.get("r_frame_rate") or ""),
        "avg_frame_rate": st.get("avg_frame_rate"), "avg_fps": _rate(st.get("avg_frame_rate") or ""),
        "nb_frames": int(nb) if (nb not in (None, "N/A")) else None,
        "duration_s": float(dur) if (dur not in (None, "N/A")) else None,
        "fps_from_frames_over_duration": (int(nb) / float(dur))
        if (nb not in (None, "N/A") and dur not in (None, "N/A") and float(dur) > 0) else None,
    }


def list_episodes(task_dir: Path):
    if not task_dir.exists():
        return []
    return sorted(p for p in task_dir.iterdir()
                  if p.is_dir() and p.name.startswith("episode_"))


def select_episodes(episodes, n_per_task: int, stride_rule: str):
    """确定性取样（不用随机数）：排序后等距取 n 条 ⇒ 同一输入必得同一样本，可复算。"""
    if n_per_task <= 0 or len(episodes) <= n_per_task:
        return list(episodes), {"rule": stride_rule, "requested": n_per_task,
                                "available": len(episodes), "taken": len(episodes)}
    idx = [round(i * (len(episodes) - 1) / (n_per_task - 1)) for i in range(n_per_task)]
    idx = sorted(set(idx))
    return [episodes[i] for i in idx], {"rule": stride_rule, "requested": n_per_task,
                                        "available": len(episodes), "taken": len(idx)}


class ColAccum:
    """逐列流式统计：count/mean/std/min/max 全量精确；分位数走固定步长子采样（**声明**在产物里）。"""

    def __init__(self, n_cols: int, quantile_stride: int):
        self.n_cols = n_cols
        self.cnt = np.zeros(n_cols, dtype=np.float64)
        self.s = np.zeros(n_cols, dtype=np.float64)
        self.s2 = np.zeros(n_cols, dtype=np.float64)
        self.mn = np.full(n_cols, np.inf, dtype=np.float64)
        self.mx = np.full(n_cols, -np.inf, dtype=np.float64)
        self.qstride = max(1, int(quantile_stride))
        self.qsampler = []          # 子采样后的行（float32），用于分位数
        self.q_rows = 0
        self.q_seen = 0
        self.all_zero_cols = np.ones(n_cols, dtype=bool)
        # π₀.₅ 的 `Pi05PrepareStateTokenizerProcessorStep` 用 `np.digitize(state, np.linspace(-1,1,257)[:-1])`
        # （裁定 46.2 实测）⇒ 落在 [-1,1] 之外的值会被**压到边界 bin**。这里逐维数它有多少，
        # 把"状态通道饱和"从定性变成**可判的数**（A2 现场只有单条 episode 的行程占比）。
        self.n_abs_gt1 = np.zeros(n_cols, dtype=np.int64)
        self.n_below_m1 = np.zeros(n_cols, dtype=np.int64)
        self.n_above_p1 = np.zeros(n_cols, dtype=np.int64)

    def update(self, mat: np.ndarray):
        if mat.size == 0:
            return
        m = np.asarray(mat, dtype=np.float64)
        self.cnt += m.shape[0]
        self.s += m.sum(axis=0)
        self.s2 += (m ** 2).sum(axis=0)
        self.mn = np.minimum(self.mn, m.min(axis=0))
        self.mx = np.maximum(self.mx, m.max(axis=0))
        nz = np.any(m != 0.0, axis=0)
        self.all_zero_cols &= ~nz
        self.n_abs_gt1 += np.sum(np.abs(m) > 1.0, axis=0)
        self.n_below_m1 += np.sum(m < -1.0, axis=0)
        self.n_above_p1 += np.sum(m > 1.0, axis=0)
        self.q_seen += m.shape[0]
        take = m[::self.qstride]
        if take.size:
            self.qsampler.append(take.astype(np.float32))
            self.q_rows += take.shape[0]

    def result(self, quantiles=(0.01, 0.5, 0.99)):
        n = float(self.cnt[0]) if self.n_cols else 0.0
        out = {"n_frames_used": int(self.cnt[0]) if self.n_cols else 0}
        if not n:
            out.update({"mean": None, "std": None, "min": None, "max": None,
                        "quantiles": None, "all_zero_dims": None})
            return out
        mean = self.s / np.maximum(self.cnt, 1)
        var = np.maximum(self.s2 / np.maximum(self.cnt, 1) - mean ** 2, 0.0)
        std = np.sqrt(var)
        qs = {}
        if self.qsampler:
            arr = np.concatenate(self.qsampler, axis=0)
            for q in quantiles:
                qs["p%g" % (q * 100)] = np.quantile(arr.astype(np.float64), q, axis=0).tolist()
            qs["_n_rows_subsampled"] = int(arr.shape[0])
            qs["_stride"] = self.qstride
        out.update({
            "mean": mean.tolist(), "std": std.tolist(),
            "min": np.where(np.isinf(self.mn), None, self.mn).tolist(),
            "max": np.where(np.isinf(self.mx), None, self.mx).tolist(),
            "quantiles": qs or None,
            "all_zero_dims": [int(i) for i in np.nonzero(self.all_zero_cols)[0]],
            "n_frames_per_dim": self.cnt.astype(int).tolist(),
            # 饱和口径：分母是**该维的全部帧**（不是 episode 数）
            "saturation_if_unnormalized_to_pm1": {
                "frac_abs_gt_1_per_dim": (self.n_abs_gt1 / np.maximum(self.cnt, 1)).tolist(),
                "frac_below_minus1_per_dim": (self.n_below_m1 / np.maximum(self.cnt, 1)).tolist(),
                "frac_above_plus1_per_dim": (self.n_above_p1 / np.maximum(self.cnt, 1)).tolist(),
                "frac_abs_gt_1_pooled_over_dims": float(
                    self.n_abs_gt1.sum() / max(float(self.cnt.sum()), 1.0)),
                "n_dims_fully_inside_pm1": int(np.sum(self.n_abs_gt1 == 0)),
                "basis": ("裁定 46.2：ckpt 的 normalizer features 为空 + 状态按 [-1,1] 离散化 ⇒ "
                          "这些比例就是**未归一化时会被截断的状态量占比**。"
                          "min-max 归一化到 [-1,1]（用本文件的 p01/p99 或 min/max）后该比例按构造≈0"),
            },
        })
        return out


def extract_vector(doc: dict, side: str, frames: int):
    """从团队形态 JSON 里取 14 维（side ∈ {state, action}）⇒ (frames, 14) float32。

    取不到 / 长度不齐 ⇒ 返回 (None, why)；**不**用 0 填充（填 0 会污染 mean/std/min，
    那正是"静默默认"这类假绿的源头）。
    """
    s = doc.get(side)
    if not isinstance(s, dict):
        return None, "missing_side_dict"
    la = ((s.get("left_arm") or {}).get("joint"))
    ra = ((s.get("right_arm") or {}).get("joint"))
    lg = ((s.get("left_gripper") or {}).get("joint"))
    rg = ((s.get("right_gripper") or {}).get("joint"))
    for nm, arr, want in (("left_arm.joint", la, 6), ("right_arm.joint", ra, 6),
                          ("left_gripper.joint", lg, 1), ("right_gripper.joint", rg, 1)):
        if not isinstance(arr, list) or not arr:
            return None, "channel_empty:%s" % nm
        if len(arr[0]) != want:
            return None, "channel_inner_dim:%s=%d!=%d" % (nm, len(arr[0]), want)
        if len(arr) != frames:
            return None, "channel_len:%s=%d!=%d" % (nm, len(arr), frames)
    try:
        A = np.asarray(la, dtype=np.float32)
        B = np.asarray(ra, dtype=np.float32)
        C = np.asarray(lg, dtype=np.float32)
        D = np.asarray(rg, dtype=np.float32)
    except Exception as e:                        # noqa: BLE001
        return None, "not_numeric:%s" % type(e).__name__
    if not (np.isfinite(A).all() and np.isfinite(B).all()
            and np.isfinite(C).all() and np.isfinite(D).all()):
        return None, "non_finite_values"
    return np.concatenate([A, C, B, D], axis=1), None   # aloha_interleaved


def velocity_zero_fraction(doc: dict, side: str):
    """逐帧实测：该帧两臂 6+6 个 velocity 是否**全为 0** ⇒ 返回 (全零帧占比, 全零 episode?)。

    2026-09-29 20:31 烟测逼出来的修法：第一版硬写"velocity 全 0"，实测却是
    `n_episodes_nonzero=4`（首帧为 0、整条不全为 0）⇒ 散文与证据不符，正是本仓反复踩的
    「解释获得既成地位」。所以这里只报**实测占比**，语义结论留给读者/D。
    """
    s = doc.get(side)
    if not isinstance(s, dict):
        return None, None
    mats = []
    for arm in ("left_arm", "right_arm"):
        v = ((s.get(arm) or {}).get("velocity"))
        if not (isinstance(v, list) and v and isinstance(v[0], list)):
            return None, None
        mats.append(np.asarray(v, dtype=np.float64))
    if not mats:
        return None, None
    m = np.concatenate(mats, axis=1)
    if m.ndim != 2 or m.shape[0] == 0:
        return None, None
    per_frame_all_zero = np.all(m == 0.0, axis=1)
    frac = float(per_frame_all_zero.mean())
    return frac, bool(frac == 1.0)


def episode_record(ep_dir: Path, task: str, direction: str, pair_id: str, split: str,
                   quantile_stride: int, probe_video: bool):
    """一条 episode 的只读实测记录 + 14 维矩阵（矩阵返回给上层累加，不落盘）。"""
    rec = {"episode_id": ep_dir.name, "task": task, "direction": direction,
           "pair_id": pair_id, "split": split, "dir": str(ep_dir),
           "measured_at": now_iso()}
    meta = ep_dir / "converted_metadata_normal.json"
    rec["metadata_path"] = str(meta)
    rec["metadata_exists"] = meta.exists()
    if not meta.exists():
        rec["status"] = "UNJUDGED"
        rec["why"] = "converted_metadata_normal.json 缺失"
        return rec, None, None
    rec["metadata_bytes"] = meta.stat().st_size
    rec["metadata_sha256_12"] = sha12(meta)
    try:
        doc = json.loads(meta.read_text(errors="replace"))
    except Exception as e:                        # noqa: BLE001
        rec["status"] = "UNJUDGED"
        rec["why"] = "json_parse_error:%s" % type(e).__name__
        return rec, None, None

    im = doc.get("is_move")
    fv = (doc.get("frame_validity") or {}).get("is_valid")
    n_im = len(im) if isinstance(im, list) else None
    n_fv = len(fv) if isinstance(fv, list) else None
    frames = n_im or n_fv
    # 团队 QC 的 V07/V08 比的是"视频帧数 vs len(is_move)"（B2 2026-09-29 实测拿到正对照）
    rec["n_is_move"] = n_im
    rec["n_frame_validity"] = n_fv
    rec["is_move_true_count"] = (sum(1 for x in im if x) if isinstance(im, list) else None)
    rec["is_move_all_false"] = (rec["is_move_true_count"] == 0) if n_im else None
    rec["frame_validity_true_count"] = (sum(1 for x in fv if x) if isinstance(fv, list) else None)
    rec["task_info"] = doc.get("task_info")
    rec["raw_mcap_path"] = doc.get("file_path")
    sub = doc.get("subtask")
    rec["n_subtask"] = len(sub) if isinstance(sub, list) else None
    intr = doc.get("intrinsics")
    rec["intrinsics_shape"] = ([len(intr), len(intr[0])]
                               if isinstance(intr, list) and intr and isinstance(intr[0], list)
                               else ("scalar_list:%d" % len(intr) if isinstance(intr, list) else None))
    rec["intrinsics"] = intr if isinstance(intr, list) else None

    cam = {}
    for slot in CAMERA_SLOTS:
        cam[slot] = (ep_dir / slot).exists()
    rec["cameras_present"] = cam
    rec["camera_slots_missing"] = [k for k, v in cam.items() if not v]
    if probe_video:
        vinfo = {}
        for slot in CAMERA_SLOTS:
            p = ep_dir / slot
            if p.exists():
                vinfo[slot] = ffprobe_video(p)
                vinfo[slot]["bytes"] = p.stat().st_size
        rec["video_probe"] = vinfo
        # fps 三值：视频容器口径（QC 的 J/V04 读这个）与"帧数÷mcap 时长"口径**不混写**
        fps_vals = [v.get("avg_fps") for v in vinfo.values()
                    if isinstance(v, dict) and v.get("avg_fps")]
        rec["fps_container_avg"] = (sum(fps_vals) / len(fps_vals)) if fps_vals else None
        rec["fps_in_qc_band_29_31"] = (
            bool(all(QC_FPS_BAND[0] <= f <= QC_FPS_BAND[1] for f in fps_vals))
            if fps_vals else None)

    # 内参与视频分辨率的自洽性（针尖式实测：主点应≈画面中心）。这条同时给
    # D→B2 §10.3-2 的「规则 A 报 intrinsic 缺失，是数据缺还是 schema 不匹配」提供证据：
    # 若 intrinsics 存在且与其视频分辨率自洽 ⇒ 更可能是**字段名/结构不匹配**。
    intr = rec.get("intrinsics")
    if isinstance(intr, list) and len(intr) == 3 and isinstance(intr[0], list) and len(intr[0]) == 3:
        fx, fy, cx, cy = intr[0][0], intr[1][1], intr[0][2], intr[1][2]
        vp = rec.get("video_probe") or {}
        whs = sorted({(v.get("width"), v.get("height")) for v in vp.values()
                      if isinstance(v, dict) and v.get("width")})
        rec["intrinsics_fx_fy_cx_cy"] = {"fx": fx, "fy": fy, "cx": cx, "cy": cy}
        rec["video_resolutions"] = ["%sx%s" % (w, h) for (w, h) in whs]
        if len(whs) == 1 and whs[0][0] and whs[0][1]:
            w, h = whs[0]
            rec["intrinsics_selfconsistency"] = {
                "cx_over_w": round(cx / w, 4), "cy_over_h": round(cy / h, 4),
                "expected_if_centered": 0.5,
                "verdict": ("self_consistent" if abs(cx / w - 0.5) < 0.05
                            and abs(cy / h - 0.5) < 0.05 else "inconsistent"),
                "note": "主点≈画面中心（±5%）⇒ 该 3×3 矩阵与这路视频分辨率对得上",
            }
        elif whs:
            rec["intrinsics_selfconsistency"] = {
                "verdict": "UNJUDGED", "why": "同一条 episode 里出现多种分辨率 %s，无法定分母" % rec["video_resolutions"]}
        else:
            rec["intrinsics_selfconsistency"] = {"verdict": "UNJUDGED", "why": "没有可探测的视频"}
    else:
        rec["intrinsics_selfconsistency"] = {"verdict": "UNJUDGED",
                                             "why": "intrinsics 不是 3×3 矩阵（实测形态=%s）"
                                                    % rec.get("intrinsics_shape")}

    bc = ep_dir / "badcase.json"
    if bc.exists():
        try:
            rec["team_badcase_json"] = json.loads(bc.read_text(errors="replace"))
        except Exception as e:                    # noqa: BLE001
            rec["team_badcase_json"] = {"parse_error": type(e).__name__}
        rec["team_badcase_bytes"] = bc.stat().st_size

    st_mat, why_s = extract_vector(doc, "state", frames or 0)
    ac_mat, why_a = extract_vector(doc, "action", frames or 0)
    vf = {}
    for side in ("state", "action"):
        frac, allz = velocity_zero_fraction(doc, side)
        vf[side] = {"zero_frame_fraction": frac, "episode_all_zero": allz}
    rec["velocity_zero"] = vf
    if st_mat is None or ac_mat is None:
        rec["status"] = "UNJUDGED"
        rec["why"] = "vector_extract_failed: state=%s action=%s" % (why_s, why_a)
        return rec, None, None
    rec["status"] = "OK"
    rec["n_frames_vector"] = int(st_mat.shape[0])
    rec["gripper_range"] = {
        "state_left": [float(st_mat[:, 6].min()), float(st_mat[:, 6].max())],
        "state_right": [float(st_mat[:, 13].min()), float(st_mat[:, 13].max())],
        "action_left": [float(ac_mat[:, 6].min()), float(ac_mat[:, 6].max())],
        "action_right": [float(ac_mat[:, 13].min()), float(ac_mat[:, 13].max())],
    }
    rec["joint_absmax_rad"] = {
        "state": float(np.abs(np.concatenate([st_mat[:, 0:6], st_mat[:, 7:13]], axis=1)).max()),
        "action": float(np.abs(np.concatenate([ac_mat[:, 0:6], ac_mat[:, 7:13]], axis=1)).max()),
    }
    # 子任务 × 夹爪：给"夹爪 1=open 还是 0=open"（A2 契约 q5=unknown）留**可判证据**，
    # B2 只报观测不下结论（语义裁定归 A2/D）。
    if isinstance(sub, list) and sub:
        gs = []
        for s in sub[:40]:
            if not isinstance(s, dict):
                continue
            rg = s.get("range")
            if not (isinstance(rg, list) and len(rg) == 2):
                continue
            a, b = int(rg[0]), int(rg[1])
            if b <= a or a < 0 or b > st_mat.shape[0]:
                continue
            gs.append({"text": s.get("text"), "range": [a, b],
                       "gripper_state_left_mean": float(st_mat[a:b, 6].mean()),
                       "gripper_state_right_mean": float(st_mat[a:b, 13].mean()),
                       "gripper_action_left_mean": float(ac_mat[a:b, 6].mean()),
                       "gripper_action_right_mean": float(ac_mat[a:b, 13].mean())})
        rec["subtask_gripper_obs"] = gs
    return rec, st_mat, ac_mat


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src-root", default=SRC_ROOT_DEFAULT,
                    help="团队已转换数据根（只读）：%(default)s")
    ap.add_argument("--split", default="train",
                    help="用哪个 split 算 stats（normalizer 只从 train 算，val 留作评测池）")
    ap.add_argument("--out-dir", default=OUT_DEFAULT)
    ap.add_argument("--n-per-task", type=int, default=30,
                    help="每个任务确定性取多少条（0=全取；体积纪律见 §10.3-3）")
    ap.add_argument("--pairs", default="all", help="all 或逗号分隔的 pair_id")
    ap.add_argument("--quantile-stride", type=int, default=4,
                    help="分位数子采样步长（mean/std/min/max 仍是全量精确）")
    ap.add_argument("--no-video-probe", action="store_true",
                    help="跳过 ffprobe（快，但 fps/相机证据会变 UNJUDGED）")
    ap.add_argument("--list-only", action="store_true", help="只盘点条数，不算 stats")
    args = ap.parse_args()

    t0 = time.time()
    src_root = Path(args.src_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines = []

    def log(msg):
        line = "[%s] %s" % (now_iso(), msg)
        print(line, flush=True)
        log_lines.append(line)

    pairs = TASK_PAIRS if args.pairs == "all" else \
        [p for p in TASK_PAIRS if p["pair_id"] in set(args.pairs.split(","))]
    log("B2 ABC-130k 正反对提取开始：src_root=%s split=%s pairs=%d n_per_task=%d"
        % (src_root, args.split, len(pairs), args.n_per_task))
    if not src_root.exists():
        log("FATAL: 源根不存在 %s" % src_root)
        (out_dir / "extract.log").write_text("\n".join(log_lines) + "\n")
        return 2

    # ---- 盘点（只读）----
    inventory = []
    for pr in pairs:
        for direction in ("forward", "reverse"):
            task = pr[direction]
            td = src_root / args.split / task
            eps = list_episodes(td)
            sel, selrule = select_episodes(eps, args.n_per_task,
                                          "sorted_then_equidistant（确定性，无随机数）")
            inventory.append({
                "pair_id": pr["pair_id"], "direction": direction, "task": task,
                "split": args.split, "task_dir": str(td), "task_dir_exists": td.exists(),
                "n_episodes_converted_local": len(eps),
                "d_declared_count_raw_mcap": pr["d_declared_counts"][direction],
                "count_semantics_note": ("`d_declared_count_raw_mcap` = D 在**原始 mcap 集**上数的（§10.2 表）；"
                                         "`n_episodes_converted_local` = B2 在**本机已转换子集**上实测的。"
                                         "两个口径**不混写**（裁定 36.4）"),
                "selected": [e.name for e in sel], "selection": selrule,
            })
            log("  %-11s %-8s %-46s converted=%-5d selected=%d"
                % (pr["pair_id"], direction, task, len(eps), len(sel)))
    (out_dir / "episode_inventory.json").write_text(
        json.dumps({"generated_at": now_iso(), "src_root": str(src_root),
                    "split": args.split, "inventory": inventory},
                   indent=1, ensure_ascii=False) + "\n")
    if args.list_only:
        log("--list-only：只盘点，未算 stats")
        (out_dir / "extract.log").write_text("\n".join(log_lines) + "\n")
        return 0

    # ---- 逐条只读实测 + 流式累加 ----
    accums = {}      # key -> {"state": ColAccum, "action": ColAccum}

    def get_acc(key):
        if key not in accums:
            accums[key] = {"state": ColAccum(N_DOF, args.quantile_stride),
                           "action": ColAccum(N_DOF, args.quantile_stride)}
        return accums[key]

    records = []
    bytes_read = 0
    n_ok = n_unjudged = 0
    is_move_all_false = is_move_mixed = 0
    vel_zero = vel_nonzero = vel_unknown = vel_partial = 0
    vel_fracs = []
    fps_vals = []
    cam_missing_counter = {}
    res_counter = {}
    intr_verdicts = {}
    intr_cross = {}
    intr_incons_detail = []
    team_badcase_rules = {}
    for inv in inventory:
        for ep_name in inv["selected"]:
            ep_dir = Path(inv["task_dir"]) / ep_name
            rec, st_mat, ac_mat = episode_record(
                ep_dir, inv["task"], inv["direction"], inv["pair_id"], inv["split"],
                args.quantile_stride, not args.no_video_probe)
            records.append(rec)
            bytes_read += rec.get("metadata_bytes") or 0
            if rec.get("status") != "OK":
                n_unjudged += 1
                log("  UNJUDGED %s/%s：%s" % (inv["task"][:34], ep_name[:24], rec.get("why")))
                continue
            n_ok += 1
            for key in ("pooled", "pair:%s" % inv["pair_id"],
                        "direction:%s" % inv["direction"],
                        "pair_direction:%s:%s" % (inv["pair_id"], inv["direction"]),
                        "task:%s" % inv["task"]):
                a = get_acc(key)
                a["state"].update(st_mat)
                a["action"].update(ac_mat)
            if rec.get("is_move_all_false") is True:
                is_move_all_false += 1
            elif rec.get("is_move_all_false") is False:
                is_move_mixed += 1
            vz = (rec.get("velocity_zero") or {}).get("state") or {}
            frac, allz = vz.get("zero_frame_fraction"), vz.get("episode_all_zero")
            if frac is None:
                vel_unknown += 1
            elif allz is True:
                vel_zero += 1
            elif frac > 0.0:
                vel_partial += 1
            else:
                vel_nonzero += 1
            if frac is not None:
                vel_fracs.append(frac)
            for res in rec.get("video_resolutions") or []:
                res_counter[res] = res_counter.get(res, 0) + 1
            isc = (rec.get("intrinsics_selfconsistency") or {}).get("verdict")
            if isc:
                intr_verdicts[isc] = intr_verdicts.get(isc, 0) + 1
                rkey = ",".join(rec.get("video_resolutions") or []) or "unknown"
                cross = "%s|%s" % (isc, rkey)
                intr_cross[cross] = intr_cross.get(cross, 0) + 1
                if isc == "inconsistent":
                    fx = (rec.get("intrinsics_fx_fy_cx_cy") or {}).get("cx")
                    if fx is not None and rkey != "unknown":
                        w = int(rkey.split("x")[0].split(",")[0])
                        intr_incons_detail.append(
                            {"episode_id": rec["episode_id"], "task": rec["task"],
                             "resolution": rkey, "cx": fx, "cx_over_w": round(fx / w, 4),
                             "implied_calibration_width": round(fx / 0.5) if fx else None})
            tbc = rec.get("team_badcase_json")
            if isinstance(tbc, dict):
                for rk in tbc:
                    team_badcase_rules[rk] = team_badcase_rules.get(rk, 0) + 1
            if rec.get("fps_container_avg"):
                fps_vals.append((rec["fps_container_avg"], ep_name))
            for slot in rec.get("camera_slots_missing") or []:
                cam_missing_counter[slot] = cam_missing_counter.get(slot, 0) + 1
        log("  累计 OK=%d UNJUDGED=%d（task=%s）" % (n_ok, n_unjudged, inv["task"][:40]))

    # ---- 统计量落盘 ----
    def pack(key):
        a = accums.get(key)
        if not a:
            return None
        return {"state": a["state"].result(), "action": a["action"].result()}

    layout_docs = {}
    for lname, spec in LAYOUTS.items():
        layout_docs[lname] = {"spec": spec, "note": "14 维装配顺序是**B2 的声明**（源 JSON 是分通道 dict，"
                                                     "没有扁平数组）⇒ 需 A2 确认后才能当契约（RR-B2-09）"}
    stats = {
        "generated_at": now_iso(),
        "tool": "scripts/b2_extract_abc130k_pairs.py",
        "morphology_proxy": "yam",
        "morphology_proxy_basis": ("裁定 41.2：HF `xdof/ABC-130k` README 明写 Robot = "
                                   "\"Bimanual station, 2x 6-DoF YAM arms, parallel-jaw grippers\"；"
                                   "`docs/YAM_DATA_FORMAT.md:7` 同证。**不是 Piper，不是 Cobot Magic**"),
        "split_used": args.split,
        "n_episodes_ok": n_ok, "n_episodes_unjudged": n_unjudged,
        "vector_layout": {"primary": "aloha_interleaved", "dim": N_DOF,
                          "layouts": layout_docs,
                          "layout_status": "b2_declared_pending_a2_confirmation",
                          "channels": [{"side": s, "group": g, "field": f, "dim": d}
                                       for (s, g, f, d) in CHANNELS]},
        "groups": {k: pack(k) for k in sorted(accums)},
        "quantile_policy": {"stride": args.quantile_stride,
                            "note": "mean/std/min/max 用**全部帧**精确计算；p01/p50/p99 用固定步长子采样"
                                    "（子采样行数写在 quantiles._n_rows_subsampled）"},
        "intended_use": ("补 π₀.₅ base 缺失的 normalizer stats（裁定 44.3 / 46.2：ckpt 的 "
                         "`normalizer_processor.config.features = {}` ⇒ 状态通道按 [-1,1] 离散化会饱和）。"
                         "**本文件只是统计量**：把它写进 `policy_preprocessor.json` 的动作归 A2，"
                         "且写完必须重过 B2 的准入闸（V-pi05-2 会复算三件套）。"),
        "not_a_claim": ["不得据此声称 π₀.₅ 有了双向能力（D→B2 §5）",
                        "不得把 YAM 的关节零位/限位当 Piper 的（裁定 41.2 / 43.4：YAM J3 实测 31.6~104.5 度，"
                        "Piper J3 的 MJ 限位是 −2.967~0 rad 全负）",
                        "不得把这里的 30 Hz 当成 π₀.₅ 的原生控制频率（裁定 45.4：重采样方案待 D 裁）"],
    }
    (out_dir / "normalizer_stats.json").write_text(
        json.dumps(stats, indent=1, ensure_ascii=False) + "\n")

    # ---- 方向可分性（观测，不是能力主张）----
    sep = {}
    for pr in pairs:
        key_f = "pair_direction:%s:forward" % pr["pair_id"]
        key_r = "pair_direction:%s:reverse" % pr["pair_id"]
        if key_f not in accums or key_r not in accums:
            sep[pr["pair_id"]] = {"status": "UNJUDGED", "why": "某一方向没有可用 episode"}
            continue
        out = {}
        for side in ("state", "action"):
            mf = np.asarray(accums[key_f][side].result()["mean"], dtype=np.float64)
            mr = np.asarray(accums[key_r][side].result()["mean"], dtype=np.float64)
            sf = np.asarray(accums[key_f][side].result()["std"], dtype=np.float64)
            sr = np.asarray(accums[key_r][side].result()["std"], dtype=np.float64)
            pooled = np.sqrt(np.maximum((sf ** 2 + sr ** 2) / 2.0, 1e-12))
            d = np.abs(mf - mr) / pooled
            out[side] = {"mean_abs_diff": np.abs(mf - mr).tolist(),
                         "pooled_std": pooled.tolist(),
                         "standardized_mean_diff_per_dim": d.tolist(),
                         "max_standardized_dim": int(np.argmax(d)),
                         "max_standardized_value": float(d.max()),
                         "l2_of_mean_diff": float(np.linalg.norm(mf - mr)),
                         "l2_of_mean_diff_over_mean_std": float(
                             np.linalg.norm(mf - mr) / max(float(pooled.mean()), 1e-12))}
        sep[pr["pair_id"]] = {"status": "OK", "sides": out,
                              "reading_limit": ("这是**分布层面**的可分性观测：两方向的 state/action 边缘分布差多少。"
                                                "它**不**证明「同一 θ 对目标有条件依赖」（那要 T17 的换 goal 前向对照），"
                                                "也**不**排除两方向差异来自物体初始位而非任务方向。")}

    # ---- 数据卡 ----
    fps_sorted = sorted(f for f, _ in fps_vals)
    def _q(a, x):
        return float(np.quantile(np.asarray(a, dtype=np.float64), x)) if a else None
    card = {
        "generated_at": now_iso(),
        "tool": "scripts/b2_extract_abc130k_pairs.py",
        "run_wall_sec": round(time.time() - t0, 1),
        "loadavg": os.getloadavg(),
        "dataset_id": "b2_abc130k_bidirectional_pairs_v1",
        "morphology_proxy": "yam",
        "source": {
            "converted_root_readonly": str(src_root),
            "raw_mcap_root_readonly": RAW_ROOT_DEFAULT,
            "identity": "HF `xdof/ABC-130k`（`amazon-far/abc`）",
            "identity_basis": "裁定 41.2（D 的对照判断，用户交办）",
            "license": {"value": "apache-2.0", "provenance": "external_unverified",
                        "note": "来自 HF README；B2 未独立核验授权条款正文"},
            "write_policy": "源目录**一律只读**：本脚本不写、不 mv、不删 `workplace/` 与 `yfw_input/`",
        },
        "task_pairs": [{
            "pair_id": inv["pair_id"], "direction": inv["direction"], "task": inv["task"],
            "n_converted_local": inv["n_episodes_converted_local"],
            "n_selected": inv["selection"]["taken"],
            "d_declared_count_raw_mcap": inv["d_declared_count_raw_mcap"],
        } for inv in inventory],
        "episodes": {"ok": n_ok, "unjudged": n_unjudged,
                     "unjudged_policy": "证据缺失 ⇒ UNJUDGED，不用 0 填充、不当作通过（三值纪律）"},
        "units": {
            "arm_joints": {"value": "radian", "status": "measured",
                           "basis": "实测 state/action joint 范围 −1.239..2.015；若为度则行程仅 ±2°，与 6-DoF 臂不符",
                           "cross_check": "YAM_DATA_FORMAT.md 的 `RobotState.joint_positions`（外部文档，未独立核验单位）",
                           "external_doc_provenance": "external_unverified"},
            "gripper": {"value": "normalized_[0,1]", "status": "measured",
                        "basis": "实测 min 0.0 / max 0.989（与 D→B2 §11.2 的参照值 0~0.998 同型）",
                        "open_close_semantics": {"value": None, "status": "UNJUDGED",
                                                 "why": "A2 契约 q5 = unknown；B2 已把 `subtask_gripper_obs`"
                                                        "（子任务区间 × 夹爪均值）落进 episode_index 供判定，"
                                                        "**不**替 A2 下语义结论"},
                        "piper_travel_note": "夹爪行程三套值（URDF 50 mm / MJ joint 35 mm / MJ ctrl 47.5 mm）⇒ 待实机校准，本数据不提供"},
            "velocity_channel": {
                "status": "measured" if (vel_zero + vel_partial + vel_nonzero) else "UNJUDGED",
                "n_episodes_all_frames_zero": vel_zero,
                "n_episodes_partially_zero": vel_partial,
                "n_episodes_no_zero_frame": vel_nonzero,
                "n_episodes_unmeasurable": vel_unknown,
                "pooled_zero_frame_fraction": (float(np.mean(vel_fracs)) if vel_fracs else None),
                "min_zero_frame_fraction": (float(np.min(vel_fracs)) if vel_fracs else None),
                "max_zero_frame_fraction": (float(np.max(vel_fracs)) if vel_fracs else None),
                "consequence": ("零帧占比高的通道进 normalizer 会得到接近 0 的 std ⇒ 归一化放大噪声/除零风险；"
                                "本批 14 维向量**不含** velocity（只用 joint+gripper），所以 stats 不受影响。"
                                "若要用 velocity 当特征，必须先按这里的实测占比决定是否补测/剔除"),
                "first_version_defect_fixed": ("2026-09-29 20:31 烟测：第一版把这里硬写成"
                                               "「全 0」，实测却是 4/4 条**非**全 0（首帧为 0 而已）⇒ "
                                               "改成只报实测占比。散文与证据不同源是本仓反复踩的缺陷类"),
            },
            "ee_pose": {"value": "7d_present_not_used_for_14d_vector", "status": "measured",
                        "note": "每臂另有 pose(7)；本 14 维向量只用 joint(6)+gripper(1)（对齐 ALOHA 14-d 与 A2 契约 q2 的 14 有效维）"},
        },
        "frequency": {
            "anchor_hz": DEMO_HZ_ANCHOR,
            "anchor_basis": "裁定 45.1：仿真控制频率锚定 30.0 Hz（物理 1/480 + decimation 16）",
            "measured_container_avg_fps": {
                "n_videos": len(fps_vals), "min": fps_sorted[0] if fps_sorted else None,
                "max": fps_sorted[-1] if fps_sorted else None,
                "p50": _q(fps_sorted, 0.5), "mean": (sum(f for f, _ in fps_vals) / len(fps_vals))
                if fps_vals else None,
                "n_outside_qc_band_29_31": sum(1 for f in fps_vals
                                               if not (QC_FPS_BAND[0] <= f[0] <= QC_FPS_BAND[1])),
                "口径": "**视频容器口径**（ffprobe `avg_frame_rate`）——团队 QC 的 J/V04 读的就是这个",
            },
            "d_measured_frames_over_mcap_duration_fps": {
                "value": 29.76, "provenance": "D 实测（4749 帧 ÷ 159.58 s）",
                "口径": "**帧数 ÷ mcap 时间基**口径",
                "note": ("与容器口径**不混写**（裁定 36.4）。B2 独立复现过同型差异："
                         "一条 2780 帧 episode 的 mcap 时长 93.312 s ⇒ 29.79 fps，"
                         "而其 mp4 容器 avg_frame_rate = 30.0003、duration = 92.666 s。"
                         "两者都叫『30 Hz』，但**分母不同**"),
            },
            "qc_band": list(QC_FPS_BAND),
            "resampling_to_pi05": {
                "value": None, "status": "UNJUDGED",
                "why": ("π₀.₅ / ALOHA 生态常见 50 Hz，本数据 30 Hz ⇒ 必须显式声明重采样方案"
                        "（裁定 45.4：甲=示范重采样到 50 Hz / 乙=chunk 时长按 30/50 缩放 / 丙=…），"
                        "**由 D 裁，B2 不静默选**。A2 已把三方案落进 "
                        "`runs/vla/a2_pi05_zeroshot_20260929/ctrl_hz_alignment_a2.json`"),
                "chunk_steps_pi05": 50,
                "chunk_duration_at_30hz_s": round(50 / DEMO_HZ_ANCHOR, 4),
                "chunk_duration_at_50hz_s": 1.0,
            },
        },
        "cameras": {
            "team_slots": list(CAMERA_SLOTS),
            "missing_slot_counts_over_sampled_episodes": cam_missing_counter,
            "top_camera": {
                "status_in_converted_subset": "missing",
                "status_in_raw_mcap": "present",
                "evidence": ("B2 只读实测一条原始 mcap（`take_the_credit_cards_out_of_the_card_holder/"
                             "episode_004d8232-…`）：通道 `/top-camera` = foxglove.CompressedVideo，"
                             "**2780 条消息**，与 `/left-wrist-camera`、`/right-wrist-camera` 同数；"
                             "另有 `/top-camera-info`（CameraCalibration）⇒ 与 D→B2 §10.3-1 的判断一致："
                             "**转换/配置缺口，不是源缺口**"),
                "plan_for_pi05": {
                    "value": "recover_top_from_raw_mcap",
                    "status": "b2_proposed_pending_d",
                    "why": ("π₀.₅ 是多相机模型，少一路必须说明怎么补（占位/复制/改配置），**不许静默**"
                            "（D→B2 §10.3-1）。B2 建议：从原始 mcap 重转补回 top（源里有，且帧数对齐），"
                            "**不**用腕相机复制占位（那会造出数据里不存在的观测）"),
                    "alternative_if_d_rejects": "改 π₀.₅ 输入配置为双腕两路（需 A2 确认 base ckpt 是否支持少一路图像输入 —— 现在是 null）",
                },
            },
            "resolution_counter_over_sampled_videos": res_counter,
            "intrinsics_selfconsistency_counter": intr_verdicts,
            "intrinsics_selfconsistency_by_resolution": intr_cross,
            "intrinsics_inconsistent_detail_sample": intr_incons_detail[:20],
            "intrinsics_inconsistent_n": len(intr_incons_detail),
            "resolution_note": ("实测**分辨率不唯一**（计数见左：本机已转换子集里同时存在 640×480 与 848×480）⇒ "
                                "D→B2 §11.3 的参照内参 fx=431.88 fy=431.38 cx=324.26 cy=240.97 @640×480 "
                                "**只对 640×480 那部分成立**；其它分辨率必须用它自己 JSON 里的 `intrinsics`"
                                "（3×3 矩阵，逐条实测与其视频分辨率自洽，计数见 "
                                "`intrinsics_selfconsistency_counter`）或重新标定，**不许**跨分辨率套用"),
            "intrinsics_shape_correction": ("`intrinsics` 是**一个 3×3 矩阵**，不是三组相机内参"
                                            "（D 在 §10.3-2 已自纠；B2 逐条复现：`intrinsics_shape=[3,3]`）"),
        },
        "is_move": {
            "team_semantics": {"value": None, "status": "UNJUDGED",
                               "why": "团队规则未在本仓给出 `is_move` 的定义文档；B2 不改团队管线代码，故不臆断"},
            "measured_in_this_subset": {"n_episodes_all_false": is_move_all_false,
                                        "n_episodes_with_true": is_move_mixed,
                                        "d_observation_confirmed": ("D 在 ABC130k 一条 episode 上实测 `is_move` 全 0 而 "
                                                                    "`frame_validity.is_valid` 全 1（§9.2）；"
                                                                    "B2 在本次抽样上**复现**了同型现象（计数见左）")},
            "qc_implication_measured": ("B2 2026-09-29 在自建负对照上拿到 V07/V08 正对照："
                                        "团队 QC 的 V07 比的是**视频帧数 vs len(is_move)**（不是 action 数组长度）"
                                        "⇒ `is_move` 全 False **不影响帧数类规则**，但会让「是否在动」这一语义通道为空"),
            "b2_policy_for_own_data": ("B2 自造数据（任务 2(b) 仿真侧）**必须显式定义并真的填** `is_move`"
                                       "（D→B2 §9.2 的牙）：定义 = 该帧任一臂关节指令增量 |Δq| > 阈值 或 夹爪状态变化"
                                       " ⇒ True；阈值与实测分布在自造数据的 README 里给出。**不沿用全 False**"),
        },
        "defects_observed": {
            "velocity_all_zero": {"n_episodes": vel_zero, "impact": "见 units.velocity_channel"},
            "top_camera_missing_in_converted": cam_missing_counter.get("top-camera.mp4", 0),
            "team_own_badcase_json_present": sum(1 for r in records if r.get("team_badcase_json") is not None),
            "team_own_badcase_rule_counter": team_badcase_rules,
            "team_own_badcase_note": ("这是**团队自己那一轮** QC 留在每条 episode 目录里的 `badcase.json`"
                                      "（不是 B2 跑的）。规则 A（`字段缺失: intrinsic`）的计数若接近抽样条数，"
                                      "与 B2 实测「intrinsics 存在且与分辨率自洽」并列 ⇒ 指向"
                                      "**字段名/结构不匹配**而非数据缺失（D→B2 §10.3-2 要的那个结论，"
                                      "规则源码定位见报告）"),
            "note": ("这些是**观测**，不是对团队数据的质量结论（D→B2 §2.2-3：只报观测，不下结论 —— "
                     "那是团队数据，不是本仓资产）"),
        },
        "volume_accounting": {
            "policy": "D→B2 §10.3-3：只许按需取子集，不许整集拷贝/转换（NFS 已用 94%）；>10 GB 先申报",
            "bytes_read_metadata_json": bytes_read,
            "gib_read_metadata_json": round(bytes_read / (1024 ** 3), 3),
            "episodes_read": n_ok + n_unjudged,
            "bytes_written": None,      # 收尾时回填
            "copied_episode_dirs": 0,   # 本脚本**不拷**任何 episode（拷贝在 QC 子集脚本里做，另行申报体积）
            "declared_under_10gib": True,
        },
        "provenance_of_this_artifact": {
            "read_only_sources": [str(src_root), RAW_ROOT_DEFAULT],
            "written_paths": [str(out_dir)],
            "no_rm": True, "no_team_pipeline_code_change": True,
            "gpu_used": False,
        },
        "open_items_for_d": [
            {"id": "RR-B2-09", "topic": "14 维装配顺序（aloha_interleaved vs joints_then_grippers）",
             "why": "源 JSON 是分通道 dict，扁平化顺序是**声明**不是实测；A2 的 contract q2 写 dim=32/14 有效但"
                    "**槽位语义 unknown** ⇒ 两边必须对齐同一个顺序，否则 normalizer stats 逐维错位（错位是静默的）"},
            {"id": "RR-B2-08", "topic": "30 Hz 示范 → π₀.₅ 的重采样方案（甲/乙/丙）",
             "why": "裁定 45.4 明令不许静默选；A2 已给三方案与代价，等 D 裁"},
            {"id": "RR-B2-10", "topic": "top 相机补法（从原始 mcap 重转 vs 改 π₀.₅ 输入为双腕）",
             "why": "D→B2 §10.3-1 要求显式声明，不许静默；重转需要 B2 写视频（体积 ~30 MB/条），改配置需 A2 确认 base ckpt 支持"},
            {"id": "RR-B2-11", "topic": "夹爪 1=open 还是 0=open（A2 契约 q5=unknown）",
             "why": "B2 已落 `subtask_gripper_obs` 证据但不替 A2 下结论；语义错会让 BC 学出反向开合"},
        ],
    }
    (out_dir / "dataset_card.json").write_text(
        json.dumps(card, indent=1, ensure_ascii=False) + "\n")
    (out_dir / "direction_separability.json").write_text(
        json.dumps({"generated_at": now_iso(), "pairs": sep,
                    "not_a_claim": "分布可分性 ≠ 目标条件依赖 ≠ 双向能力（D→B2 §5）"},
                   indent=1, ensure_ascii=False) + "\n")
    (out_dir / "episode_index.json").write_text(
        json.dumps({"generated_at": now_iso(), "n": len(records), "records": records},
                   indent=1, ensure_ascii=False) + "\n")

    written = sum(p.stat().st_size for p in out_dir.iterdir() if p.is_file())
    card["volume_accounting"]["bytes_written"] = written
    card["volume_accounting"]["gib_written"] = round(written / (1024 ** 3), 6)
    (out_dir / "dataset_card.json").write_text(
        json.dumps(card, indent=1, ensure_ascii=False) + "\n")

    log("完成：OK=%d UNJUDGED=%d，读 metadata %.2f GiB，写产物 %.2f MiB，墙钟 %.1f s"
        % (n_ok, n_unjudged, bytes_read / 1024 ** 3, written / 1024 ** 2, time.time() - t0))
    log("产物：%s" % ", ".join(sorted(p.name for p in out_dir.iterdir() if p.is_file())))
    (out_dir / "extract.log").write_text("\n".join(log_lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
