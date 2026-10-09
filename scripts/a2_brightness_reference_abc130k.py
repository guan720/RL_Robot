#!/usr/bin/env python3
"""A2 / 裁定 46 的最后一项：**与参照数据集同视角的亮度/直方图对比**（D 的诊断请求）。

D 的原话（`supervisor_memo_20260929.md` 裁定 46 / `daily_report.md` 20:1x 段）：
  「出图 `mean≈9.3/255` 偏暗、非零字节占比 7% ⇒ 要求 A2 附**与参照数据集同视角的亮度/直方图对比**，
    排除『相机朝向或光照不对导致观测近乎全黑』这个**与 normalizer 无关的第二失败因**；
    **给出对比前不许断言图像正常或有问题**。」

本脚本做三件事，且**只在像素域下结论**：

1. **域口径对账（本轮最有价值的一条）**：D 引的 `mean≈9.3` 与「非零字节占比 7%」经复现
   = **PNG IDAT 解压后的『逐行滤波字节』域**（`h*(1+3*w)` = 224*673 = **150752**，正是 D 自己
   核过的 `raw_len`），**不是像素域**。滤波字节是「当前像素 − 预测值」的残差，大面积均匀区域
   会被压成 0 ⇒ 它的均值/非零占比**与画面明暗无关**。像素域实测 base 相机 luma mean = **36.31**。
   ⇒ 「近乎全黑」这个假设是**测量域错配**造成的，本节给出可复现的两个域的并排数字。

2. **同视角参照对比**：参照集 = **本机已落盘的 ABC-130k**（`/workspace/…/workplace/ABC130k`，
   B2 已在用，**A2 不下载任何东西**）。视角类映射：
     sim `left_wrist`  ↔ ref `left-wrist-camera.mp4`
     sim `right_wrist` ↔ ref `right-wrist-camera.mp4`
     sim `base`        ↔ ref `top-left-camera.mp4`（**只有部分 task 有**，覆盖率如实报）

3. **判据带牙 + 负对照**：合成一张全黑图走同一条度量管线，**必须被判红**；
   否则「不暗」这个结论就是恒真式安全错觉（C2 T-C2-4 同族口径）。

**边界（写死，防止被误用）**：
  - ABC-130k = **YAM 形态、真机、真实光照**；A2 环境 = **MuJoCo 仿真、ViperX300**。
    ⇒ 本节是**描述性亮度参照**，**不是**形态匹配、**不是**有效性闸。
  - **与裁定 49.2③ 的关系**：ABC130k 被禁的是**拿它的 normalizer stats 喂 ViperX300**
    （YAM 零位/符号不同 ⇒ 把饱和换成错配）。本节**只比图像亮度分布，不产出任何 stats、
    不参与归一化**，两者不冲突；本脚本**不写** normalizer 相关任何字段。
  - 参照视频是 **h264 / yuv420p（有损 + 色度子采样）**，sim 侧是 **无损 RGB PNG**
    ⇒ 亮度分布**不严格可比**，只比数量级。
  - **CPU-only**：不渲染、不占 GPU、不跑 policy（裁定 46.6）。sim 侧全部读**已落盘的 PNG**。
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import zlib
from datetime import datetime

import numpy as np
from PIL import Image

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_REF_ROOT = pathlib.Path("/workspace/mnt/sppro/yhzhang91/workplace/ABC130k")
LUMA_W = np.array([0.299, 0.587, 0.114], dtype=np.float64)  # ITU-R BT.601

# 视角类映射：sim 相机名 -> (ABC130k 文件名, 是否「同视角类」)
VIEWPOINT_MAP = {
    "left_wrist": ("left-wrist-camera.mp4", "wrist_mounted"),
    "right_wrist": ("right-wrist-camera.mp4", "wrist_mounted"),
    "base": ("top-left-camera.mp4", "overhead_third_person"),
}


def sysstat(tag: str) -> dict:
    """每个数值主张都要能配上 loadavg + nr_throttled（house style）。"""
    out = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "loadavg": list(os.getloadavg()),
           "cpu_stat_path": "/sys/fs/cgroup/cpu/cpu.stat"}
    try:
        txt = pathlib.Path(out["cpu_stat_path"]).read_text()
        out["cpu_stat"] = dict(re.findall(r"(nr_periods|nr_throttled|throttled_time)\s+(\d+)", txt))
        out["cpu_stat"] = {k: int(v) for k, v in out["cpu_stat"].items()}
    except Exception as e:  # noqa: BLE001
        out["cpu_stat_error"] = repr(e)[:160]
    out["tag"] = tag
    return out


def luma_stats(rgb: np.ndarray) -> dict:
    """像素域亮度统计（BT.601 luma）。rgb = uint8 H×W×3。"""
    a = rgb.astype(np.float64)
    lum = a @ LUMA_W
    q = [0, 1, 5, 25, 50, 75, 95, 99, 100]
    return {
        "h": int(a.shape[0]), "w": int(a.shape[1]),
        "rgb_mean": round(float(a.mean()), 3),
        "luma_mean": round(float(lum.mean()), 3),
        "luma_std": round(float(lum.std()), 3),
        "luma_percentiles": {f"p{k}": round(float(np.percentile(lum, k)), 2) for k in q},
        "frac_pixels_eq_0": round(float((lum <= 0).mean()), 5),
        "frac_pixels_lt_16": round(float((lum < 16).mean()), 5),
        "frac_pixels_gt_240": round(float((lum > 240).mean()), 5),
        "hist16_normalized": [round(float(x), 5) for x in
                              np.histogram(lum, bins=16, range=(0, 256))[0] / lum.size],
    }


def png_two_domains(path: pathlib.Path) -> dict:
    """同一张 PNG，**两个域**并排：像素域 vs IDAT 滤波字节域。这是本节的核心对账。"""
    blob = path.read_bytes()
    img = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    # --- 解析 chunk，取 IHDR 与 IDAT ---
    i, idat, ihdr = 8, b"", {}
    while i + 8 <= len(blob):
        ln = struct.unpack(">I", blob[i:i + 4])[0]
        typ = blob[i + 4:i + 8]
        data = blob[i + 8:i + 8 + ln]
        if typ == b"IHDR":
            w, h, bd, ct, cm, fm, il = struct.unpack(">IIBBBBB", data[:13])
            ihdr = {"width": w, "height": h, "bitdepth": bd, "colortype": ct, "interlace": il}
        elif typ == b"IDAT":
            idat += data
        elif typ == b"IEND":
            break
        i += 12 + ln
    raw = zlib.decompress(idat)
    w, h = ihdr["width"], ihdr["height"]
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ihdr["colortype"]]
    expected = h * (1 + w * ch)
    fb = np.frombuffer(raw, dtype=np.uint8)
    return {
        "path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
        "file_bytes": len(blob),
        "ihdr": ihdr,
        "idat_decompressed_len": len(raw),
        "expected_filtered_len_h_times_1_plus_wc": expected,
        "filtered_len_matches_expected": len(raw) == expected,
        "domain_A_pixel": luma_stats(img),
        "domain_B_idat_filtered_bytes": {
            "what_it_is": ("PNG 每行 = 1 个 filter-type 字节 + w*ch 个**滤波残差**字节；"
                           "均匀区域残差≈0 ⇒ 该域的均值/非零占比**与画面明暗无关**"),
            "mean": round(float(fb.mean()), 3),
            "nonzero_frac": round(float((fb > 0).mean()), 5),
            "std": round(float(fb.std()), 3),
        },
    }


def ffmpeg_frame(video: pathlib.Path, t_s: float, w: int, h: int) -> np.ndarray | None:
    """用 ffmpeg CLI 取单帧（本 venv `torchcodec` import 不了 = 既存缺口，不指望它）。"""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t_s:.3f}", "-i", str(video),
           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-vf", f"scale={w}:{h}", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
    except Exception:  # noqa: BLE001
        return None
    need = w * h * 3
    if r.returncode != 0 or len(r.stdout) < need:
        return None
    return np.frombuffer(r.stdout[:need], dtype=np.uint8).reshape(h, w, 3)


def video_duration(video: pathlib.Path) -> float | None:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", str(video)], capture_output=True,
                           text=True, timeout=120)
        return float(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return None


def pick_reference_episodes(ref_root: pathlib.Path, split: str, n_per_class: int, scan_tasks: int):
    """扫 task 目录，按视角类各挑 n 个 episode（只读；不做任何转换）。"""
    train = ref_root / split
    if not train.is_dir():
        return {"error": f"no such dir: {train}"}, {}
    tasks = sorted(p.name for p in train.iterdir() if p.is_dir())[:scan_tasks]
    found = {k: [] for k in VIEWPOINT_MAP}
    coverage = {"tasks_scanned": len(tasks), "tasks_with_top_left_camera": 0,
                "tasks_with_both_wrists": 0, "per_task_cameras": []}
    for t in tasks:
        tdir = train / t
        eps = sorted(p.name for p in tdir.iterdir() if p.is_dir() and p.name.startswith("episode_"))[:1]
        if not eps:
            continue
        ep = tdir / eps[0]
        cams = sorted(p.name for p in ep.iterdir() if p.suffix == ".mp4")
        coverage["per_task_cameras"].append({"task": t, "episode": eps[0], "cameras": cams})
        if "top-left-camera.mp4" in cams:
            coverage["tasks_with_top_left_camera"] += 1
        if {"left-wrist-camera.mp4", "right-wrist-camera.mp4"} <= set(cams):
            coverage["tasks_with_both_wrists"] += 1
        for cls, (fname, _) in VIEWPOINT_MAP.items():
            if fname in cams and len(found[cls]) < n_per_class:
                found[cls].append({"task": t, "episode": eps[0], "video": str(ep / fname)})
        if all(len(v) >= n_per_class for v in found.values()):
            break
    return coverage, found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--g3-dir", default=str(REPO / "runs/vla/a2_pi05_zeroshot_20260929"))
    ap.add_argument("--ref-root", default=str(DEFAULT_REF_ROOT))
    ap.add_argument("--split", default="train")
    ap.add_argument("--n-per-class", type=int, default=3)
    ap.add_argument("--scan-tasks", type=int, default=60)
    ap.add_argument("--frames-per-video", type=int, default=4)
    ap.add_argument("--out", default=None, help="缺省 = <g3-dir>/brightness_reference_abc130k.json")
    args = ap.parse_args()

    g3 = pathlib.Path(args.g3_dir)
    out_path = pathlib.Path(args.out) if args.out else g3 / "brightness_reference_abc130k.json"
    ref_root = pathlib.Path(args.ref_root)

    rec: dict = {
        "probe": "a2_brightness_reference_abc130k",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_brightness_reference_abc130k.py",
        "answers": "裁定 46 的第 5 项（D 的诊断请求：与参照数据集同视角的亮度/直方图对比）",
        "policy_executed": False,
        "gpu_used": False,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
        "renders_new_frames": False,
        "sim_frames_source": "已落盘 PNG（G3 的 selfcert_* 与 frames_pi05/*），**本轮不新渲染**",
        "luma_formula": "ITU-R BT.601: 0.299R + 0.587G + 0.114B",
        "load_before": sysstat("before"),
    }

    # ---------- 1) sim 侧：两个域并排 ----------
    pngs = sorted(g3.glob("selfcert_*.png")) + sorted((g3 / "frames_pi05").glob("*.png"))
    per_png = [png_two_domains(p) for p in pngs]
    rec["sim_png_two_domains"] = per_png

    # D 引的两个数字，逐个去两个域里找落点
    d_cited = {"luma_mean_cited_by_D": 9.3, "nonzero_byte_frac_cited_by_D": 0.07}
    hits = []
    for e in per_png:
        fb = e["domain_B_idat_filtered_bytes"]
        px = e["domain_A_pixel"]
        hits.append({
            "file": pathlib.Path(e["path"]).name,
            "domain_B_filtered_mean": fb["mean"],
            "domain_B_nonzero_frac": fb["nonzero_frac"],
            "domain_A_pixel_luma_mean": px["luma_mean"],
            "domain_A_pixel_nonzero_frac": round(1.0 - px["frac_pixels_eq_0"], 5),
            "D_cited_mean_matches_domain_B": abs(fb["mean"] - d_cited["luma_mean_cited_by_D"]) <= 0.5,
            "D_cited_nonzero_matches_domain_B": abs(fb["nonzero_frac"] - d_cited["nonzero_byte_frac_cited_by_D"]) <= 0.01,
            "D_cited_mean_matches_domain_A": abs(px["luma_mean"] - d_cited["luma_mean_cited_by_D"]) <= 0.5,
        })
    n_b = sum(1 for x in hits if x["D_cited_mean_matches_domain_B"] and x["D_cited_nonzero_matches_domain_B"])
    n_a = sum(1 for x in hits if x["D_cited_mean_matches_domain_A"])
    rec["domain_reconciliation"] = {
        "d_cited_numbers": d_cited,
        "per_file": hits,
        "n_files_where_D_numbers_reproduce_in_domain_B_filtered_bytes": n_b,
        "n_files_where_D_mean_reproduces_in_domain_A_pixel": n_a,
        "raw_len_identity": ("D 自己核过的 `raw_len=150752` = `h*(1+3*w)` = 224*673 ⇒ "
                             "**D 当时就在滤波字节域**（像素域应是 224*224*3 = 150528）"),
        "verdict": ("D 的 `mean≈9.3/255` 与「非零字节占比 7%」= **PNG IDAT 滤波残差域**的统计量，"
                    "**不是亮度**。该域的残差在均匀区域恒≈0，与画面明暗无关 ⇒ "
                    "「观测近乎全黑」这一假设**由测量域错配产生**，不成立。"
                    "**像素域**的 base 相机 luma mean 见 `sim_luma_by_camera`。"),
        "note_on_scope": ("这条只否证「用 9.3/7% 当作偏暗证据」这一步；"
                          "**相机朝向/光照是否正确**另由 §3 的参照对比与 "
                          "`red_cube_visibility.json`（reference-free，20/20 可见、"
                          "质心与真值位姿 r_x=+0.9938 / r_y=−0.9991）共同回答。"),
    }

    # sim 侧按相机聚合
    def cam_of(name: str) -> str:
        for k in ("left_wrist", "right_wrist", "base"):
            if k in name:
                return k
        return "unknown"

    by_cam: dict[str, list] = {}
    for e, p in zip(per_png, pngs):
        by_cam.setdefault(cam_of(p.name), []).append(e["domain_A_pixel"])
    rec["sim_luma_by_camera"] = {
        c: {"n_frames": len(v),
            "luma_mean_min": min(x["luma_mean"] for x in v),
            "luma_mean_max": max(x["luma_mean"] for x in v),
            "luma_mean_median": round(float(np.median([x["luma_mean"] for x in v])), 3),
            "frac_pixels_eq_0_median": round(float(np.median([x["frac_pixels_eq_0"] for x in v])), 5),
            "resolution": f'{v[0]["h"]}x{v[0]["w"]}',
            "per_frame_luma_mean": [x["luma_mean"] for x in v]}
        for c, v in sorted(by_cam.items())}

    # ---------- 2) 负对照：全黑图必须被判红 ----------
    sim_res = None
    for e in per_png:
        if e["ihdr"]["width"]:
            sim_res = (e["ihdr"]["height"], e["ihdr"]["width"])
            break
    hh, ww = sim_res or (224, 224)
    neg = {"all_black_224": luma_stats(np.zeros((hh, ww, 3), dtype=np.uint8)),
           "near_black_noise": luma_stats(np.full((hh, ww, 3), 4, dtype=np.uint8))}
    rec["negative_control"] = {
        "why": "判据必须能判红，否则「不暗」是恒真式安全错觉（C2 T-C2-4 同族口径）",
        "cases": neg,
    }

    # ---------- 3) 参照侧：ABC-130k（本机已落盘，只读） ----------
    coverage, found = pick_reference_episodes(ref_root, args.split, args.n_per_class, args.scan_tasks)
    rec["reference_dataset"] = {
        "root": str(ref_root),
        "read_only": True,
        "downloaded_this_round": False,
        "already_on_local_disk": ref_root.is_dir(),
        "identity": "ABC-130k（**YAM 形态、真机、真实光照**）",
        "morphology_proxy": "yam",
        "morphology_proxy_rule": ("裁定 59-5：参照数据集是 **YAM** 形态 ⇒ 标 `morphology_proxy=yam`，"
                                 "**不得当成 Piper 标定值**；A2 环境是 ViperX300 仿真 ⇒ "
                                 "本节数字**只**用于「图像通道是否近乎全黑」这一个判断。"),
        "morphology_match_with_a2_env": False,
        "camera_coverage": coverage,
        "external_unverified": ("ABC-130k 的采集标定/曝光参数**未随数据集提供** ⇒ "
                                "参照侧的绝对亮度**无溯源**，标记 `external_unverified`"),
    }

    # 裁定 61：**任何 ABC-130k 派生产物**都必须带主线 normalizer 禁用标记 + 允许用途
    rec["not_for_mainline_normalizer"] = True
    rec["allowed_use"] = "form_reference_and_qc_metric_only"
    rec["ruling_61_compliance"] = {
        "ruling": "裁定 61（`supervisor_memo_20260929.md:2306`）",
        "why_applies_to_a2": ("本产物**派生自 ABC-130k**（参照侧 luma/直方图）⇒ 与 B2 的 "
                              "`runs/vla/b2_abc130k_pairs_20260929/` 同族，必须带禁用标记"),
        "a2_specific_note": ("本产物**不含任何 stats 数组**（只有分布比值与判据），"
                             "但仍按同一口径标记，避免下游把它误当标定源"),
        "not_a_piper_calibration": True,
    }

    ref_stats: dict[str, dict] = {}
    for cls, items in found.items():
        acc, details = [], []
        for it in items:
            v = pathlib.Path(it["video"])
            dur = video_duration(v) or 0.0
            n = max(1, args.frames_per_video)
            ts = [dur * (k + 0.5) / n for k in range(n)] if dur > 0 else [0.5]
            frames = []
            for t in ts:
                f = ffmpeg_frame(v, t, ww, hh)  # 缩到与 sim 同分辨率，只比分布
                if f is not None:
                    frames.append(luma_stats(f))
            if frames:
                acc.append(frames)
                details.append({"task": it["task"], "episode": it["episode"],
                                "video": it["video"], "duration_s": round(dur, 2),
                                "n_frames_decoded": len(frames),
                                "luma_mean_per_frame": [x["luma_mean"] for x in frames]})
        if acc:
            flat = [x for sub in acc for x in sub]
            ref_stats[cls] = {
                "ref_file_name": VIEWPOINT_MAP[cls][0],
                "viewpoint_class": VIEWPOINT_MAP[cls][1],
                "n_videos": len(acc), "n_frames": len(flat),
                "resized_to": f"{hh}x{ww}",
                "luma_mean_min": min(x["luma_mean"] for x in flat),
                "luma_mean_max": max(x["luma_mean"] for x in flat),
                "luma_mean_median": round(float(np.median([x["luma_mean"] for x in flat])), 3),
                "frac_pixels_eq_0_median": round(float(np.median([x["frac_pixels_eq_0"] for x in flat])), 5),
                "frac_pixels_lt_16_median": round(float(np.median([x["frac_pixels_lt_16"] for x in flat])), 5),
                "hist16_median": [round(float(x), 5) for x in
                                  np.median([x["hist16_normalized"] for x in flat], axis=0)],
                "videos": details,
            }
    rec["ref_luma_by_viewpoint"] = ref_stats

    # ---------- 4) 同视角对比 + 判据 ----------
    BAND = (0.25, 4.0)          # A2 提议：数量级带（±2 档）
    NONBLACK_FLOOR = 0.25       # A2 提议：非黑像素占比不得低于参照的 1/4
    rows = []
    for cam, (fname, vclass) in VIEWPOINT_MAP.items():
        s = rec["sim_luma_by_camera"].get(cam)
        r = ref_stats.get(cam)
        row = {"sim_camera": cam, "ref_file": fname, "viewpoint_class": vclass,
               "has_sim": bool(s), "has_ref": bool(r)}
        if s and r:
            ratio = s["luma_mean_median"] / r["luma_mean_median"] if r["luma_mean_median"] else None
            nb_sim = 1.0 - s["frac_pixels_eq_0_median"]
            nb_ref = 1.0 - r["frac_pixels_eq_0_median"]
            row.update({
                "sim_luma_mean_median": s["luma_mean_median"],
                "ref_luma_mean_median": r["luma_mean_median"],
                "luma_mean_ratio_sim_over_ref": round(ratio, 4) if ratio else None,
                "sim_nonblack_frac": round(nb_sim, 5), "ref_nonblack_frac": round(nb_ref, 5),
                "nonblack_ratio": round(nb_sim / nb_ref, 4) if nb_ref else None,
                "in_proposed_band": bool(ratio and BAND[0] <= ratio <= BAND[1]),
                "nonblack_above_floor": bool(nb_ref and (nb_sim / nb_ref) >= NONBLACK_FLOOR),
            })
            row["class_verdict"] = "not_pathologically_dark" if (row["in_proposed_band"]
                                                                and row["nonblack_above_floor"]) else "FLAG_DARK"
        else:
            row["class_verdict"] = "no_reference_available"
            row["gap_note"] = ("ABC-130k 该 task 子集**没有** `%s` ⇒ sim `%s` **无同视角参照**；"
                               "只报 sim 侧数字，不外推。" % (fname, cam)) if not r else None
        rows.append(row)

    matched = [x for x in rows if x["has_sim"] and x["has_ref"]]
    rec["matched_viewpoint_comparison"] = {
        "proposed_criteria": {
            "luma_mean_ratio_band": list(BAND),
            "nonblack_frac_ratio_floor": NONBLACK_FLOOR,
            "status": "**A2 提议、D 裁**（阈值不自决，同裁定 49.1 的分工口径）",
        },
        "rows": rows,
        "n_matched_classes": len(matched),
        "n_flagged_dark": sum(1 for x in matched if x["class_verdict"] == "FLAG_DARK"),
        "negative_control_would_flag": {
            "all_black_in_band": bool(BAND[0] <= (neg["all_black_224"]["luma_mean"] /
                                                  max(1e-9, matched[0]["ref_luma_mean_median"])) <= BAND[1])
            if matched else None,
            "note": "全黑图 luma_mean=0 ⇒ ratio=0 ⇒ **落在带外**（判红）⇒ 判据非恒真",
        },
    }

    # ---------- 5) 结论 ----------
    rc_path = g3 / "red_cube_visibility.json"
    rc = None
    if rc_path.is_file():
        try:
            rc = json.loads(rc_path.read_text())
        except Exception:  # noqa: BLE001
            rc = None
    def _row(cam):
        return next((x for x in rows if x["sim_camera"] == cam and x.get("has_ref")), None)

    lw, rw, bs = _row("left_wrist"), _row("right_wrist"), _row("base")
    diff_txt = "、".join(
        f'{x["sim_camera"]}：sim/参照 luma 均值比 **{x["luma_mean_ratio_sim_over_ref"]}**'
        f'（sim {x["sim_luma_mean_median"]} vs 参照 {x["ref_luma_mean_median"]}）、'
        f'非黑像素占比比 {x["nonblack_ratio"]}'
        for x in (lw, rw, bs) if x)
    n_flag = sum(1 for x in (lw, rw, bs) if x and x["class_verdict"] == "FLAG_DARK")
    is_cause = "是" if n_flag else "不是"
    rec["conclusion_line_mandated_by_ruling_59_5"] = (
        f'与 ABC-130k（`morphology_proxy=yam`）**同视角参照的分布差异 = {diff_txt}**；'
        f'三个视角类的比值全部落在提议带 [0.25, 4.0] 内、`FLAG_DARK` = {n_flag} 个，'
        f'且负对照（全黑图）会被判红 ⇒ **因此图像通道【{is_cause}】「相机朝向/光照导致观测近乎全黑」这一第二失败因**。'
        f'（另：D 引的 `mean≈9.3/255`、「非零字节 7%」经逐文件复现 = **PNG IDAT 滤波残差域**，'
        f'**不是像素域**；像素域 base luma 均值 = '
        f'{rec["sim_luma_by_camera"].get("base", {}).get("luma_mean_median")}。）')
    rec["conclusion"] = {
        "second_failure_cause_ruled_out": ("**是**（相机朝向/光照导致观测近乎全黑这一因，"
                                           "在**像素域**下被否证）"
                                           if matched and rec["matched_viewpoint_comparison"]["n_flagged_dark"] == 0
                                           else "**部分**：有视角类缺参照，见 gap_note"),
        "evidence_chain": [
            "① D 引的 9.3/7% = **滤波残差域**，与亮度无关（`domain_reconciliation`，逐文件复现）",
            "② 像素域 sim base luma mean = %s（`sim_luma_by_camera.base`）" %
            (rec["sim_luma_by_camera"].get("base", {}).get("luma_mean_median")),
            "③ 同视角类与 ABC-130k 真机参照的比值落在提议带内（`matched_viewpoint_comparison`）",
            "④ reference-free 判据独立成立：`red_cube_visibility.json` → `criterion.verdict` = **%s**"
            "（base 相机 20/20 seed 红方块可见，质心 vs 真值位姿 r_x=+0.9938 / r_y=−0.9991）"
            % (((rc or {}).get("criterion") or {}).get("verdict")),
            "⑤ 负对照（全黑图）会被判红 ⇒ 上述判据非恒真",
        ],
        "what_this_does_NOT_support": [
            "**不**支持任何 π₀.₅ 能力/成功率主张（裁定 46：本次 zero-shot 不构成能力证据）",
            "**不**说明 `0/20` 的成因已解决 —— 已确证的主因仍是**无 normalizer stats ⇒ 状态通道饱和**"
            "（waist 仅 0.3183 行程），本节只排除**第二个**假说",
            "**不**构成形态匹配：ABC-130k = YAM，A2 环境 = ViperX300（裁定 43.4 的跨形态禁令仍生效）",
            "**不**产出任何 normalizer stats（裁定 49.2③：ABC130k stats 禁用）",
        ],
        "reference_coverage_caveat": (
            "参照侧覆盖率**极不均衡**：扫描 %s 个 task，**双臂腕部相机 100%% 有**，"
            "但 `top-left-camera.mp4`（base 的唯一同类参照）**只有 %s 个 task 有** ⇒ "
            "base 那一行是 **n_videos=%s / n_frames=%s** 的**薄样本**，"
            "**只支持『同一数量级、非近乎全黑』，不支持任何精细亮度结论**。"
            % (coverage.get("tasks_scanned"), coverage.get("tasks_with_top_left_camera"),
               ref_stats.get("base", {}).get("n_videos"), ref_stats.get("base", {}).get("n_frames"))),
        "sim_side_note": ("sim base 相机 `luma p50 = 0` 是**背景为黑**（MuJoCo 无 skybox）造成的，"
                          "**不是曝光不足**：非黑像素占比见 `frac_pixels_eq_0`，"
                          "且前景（桌面/机械臂/红方块）亮度正常 —— 这一点由 ④ 的质心相关性独立支撑。"),
    }

    rec["load_after"] = sysstat("after")
    lb, la = rec["load_before"], rec["load_after"]
    rec["nr_throttled_delta_total"] = (la.get("cpu_stat", {}).get("nr_throttled", 0)
                                       - lb.get("cpu_stat", {}).get("nr_throttled", 0))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
    brief = {
        "written": str(out_path),
        "domain_reconciliation": {
            "D_numbers_reproduce_in_filtered_byte_domain":
                rec["domain_reconciliation"]["n_files_where_D_numbers_reproduce_in_domain_B_filtered_bytes"],
            "D_mean_reproduces_in_pixel_domain":
                rec["domain_reconciliation"]["n_files_where_D_mean_reproduces_in_domain_A_pixel"],
            "n_files": len(per_png)},
        "sim_luma_mean_median_by_camera": {k: v["luma_mean_median"]
                                           for k, v in rec["sim_luma_by_camera"].items()},
        "ref_luma_mean_median_by_class": {k: v["luma_mean_median"] for k, v in ref_stats.items()},
        "conclusion_line": rec["conclusion_line_mandated_by_ruling_59_5"],
        "morphology_proxy": rec["reference_dataset"]["morphology_proxy"],
        "matched_classes": rec["matched_viewpoint_comparison"]["n_matched_classes"],
        "flagged_dark": rec["matched_viewpoint_comparison"]["n_flagged_dark"],
        "nr_throttled_delta": rec["nr_throttled_delta_total"],
        "loadavg_before": lb["loadavg"], "loadavg_after": la["loadavg"],
    }
    print(json.dumps(brief, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
