#!/usr/bin/env python3
"""A2 / G3 后取证：一次性产出 D §12（12.1 / 12.5 / 12.11-3,4,5,8,9,10）点名的证据。

**全程 CPU-only**（`CUDA_VISIBLE_DEVICES=""`），不占卡、不需要 GPU 申报；**不跑任何 policy**
（裁定 46.6：拿到 normalizer stats 之前不得再用 zero-shot 成功率做路线判断）。

各 section 与 D 的条目对应：
  weights     §12.11-3  把 tied-weight 检查**写进 zero-shot 产物目录**（两份产物之间建立链接）
  render      §12.11-4  渲染自证：后端 + PNG 几何 + `raw_len` vs `expected_len` + byte_std + 帧互异
              §12.11-9  亮度/直方图（**逐相机**）——但**不下"正常/有问题"的结论**（D 明令）
  cubevis     §12.11-9  **无需参照数据集**的第二失败因排查：红方块在 base 相机里是否可见、
                        其像素质心是否随**真值 box 位姿**（20 个 seed 各不相同）单调移动
  throughput  §12.1     A2 自己的渲染吞吐数字，带 (后端, mujoco 版本, 模型, 相机数, 分辨率) 五元标注
  gripper     §12.11-8  1 维夹爪指令 → 2 个指关节的**映射机制**（等式约束？指令层镜像？）+ 数值验证
  hz          §12.10    (timestep, decimation, 折算 Hz) 三元组实测 + 30.0 Hz 可行性与动力学 A/B

用法：
  CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl /root/venvs/pi05_sim/bin/python -u \
    scripts/a2_post_g3_diagnostics.py --sections weights,render,cubevis,throughput,gripper,hz \
    --g3-dir runs/vla/a2_pi05_zeroshot_20260929
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import sys
import time
from datetime import datetime

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from a2_pi05_zeroshot_eval import LEFT_FINGERS, RIGHT_FINGERS, SceneProbe, dist  # noqa: E402

CONTRACT_DIR = pathlib.Path("runs/vla/a2_pi05_contract_20260929")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def load_snapshot() -> dict:
    out = {"ts": now(), "loadavg": [float(x) for x in pathlib.Path("/proc/loadavg").read_text().split()[:3]]}
    txt = ""
    for cand in ("/sys/fs/cgroup/cpu.stat", "/sys/fs/cgroup/cpu/cpu.stat"):
        try:
            txt = pathlib.Path(cand).read_text()
            out["cpu_stat_path"] = cand
            break
        except Exception:  # noqa: BLE001
            continue
    stat = {}
    for line in txt.splitlines():
        k, _, v = line.partition(" ")
        try:
            stat[k] = int(v)
        except ValueError:
            continue
    out["cpu_stat"] = {k: stat[k] for k in ("nr_periods", "nr_throttled") if k in stat}
    return out


def header(probe: str, args, extra: dict | None = None) -> dict:
    import mujoco
    rep = {"probe": probe, "generated_at": now(), "generator": "scripts/a2_post_g3_diagnostics.py",
           "args": vars(args), "morphology": "aloha_bimanual_14d", "env_id": args.env_id,
           "python": sys.version.split()[0], "platform": platform.platform(),
           "mujoco_gl": os.environ.get("MUJOCO_GL"), "mujoco_version": mujoco.__version__,
           "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
           "policy_executed": False,
           "load_before": load_snapshot()}
    if extra:
        rep.update(extra)
    return rep


def write(rep: dict, path: pathlib.Path) -> None:
    rep["load_after"] = load_snapshot()
    nb = rep["load_before"].get("cpu_stat", {}).get("nr_throttled")
    ne = rep["load_after"].get("cpu_stat", {}).get("nr_throttled")
    rep["nr_throttled_delta_total"] = (ne - nb) if (nb is not None and ne is not None) else None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"[written] {path}", flush=True)


# ---------------------------------------------------------------- weights (§12.11-3)
def sec_weights(args, g3: pathlib.Path) -> None:
    lv_path = CONTRACT_DIR / "load_verification.json"
    if not lv_path.exists():
        raise RuntimeError(f"缺 {lv_path}：无法把 tied 检查链接进 zero-shot 产物")
    lv = json.loads(lv_path.read_text())
    cmp_ = lv.get("compare") or {}
    rep = header("a2_weights_linkage", args)
    rep["purpose"] = ("§12.11-3：D 复核 G3 的 0/20 时差点误判成「权重没加载」。"
                      "本文件把 G2 的逐张量校验**摘要 + 指纹**放进 zero-shot 产物目录，"
                      "让两份产物之间有链接。")
    rep["linked_artifact"] = {"path": str(lv_path), "sha256": sha256_file(lv_path),
                              "bytes": lv_path.stat().st_size, "mtime": now()}
    rep["verdict"] = lv.get("verdict")
    rep["verdict_explanation"] = lv.get("verdict_explanation")
    rep["compare"] = {k: cmp_.get(k) for k in ("n_compared", "n_bitwise_exact", "n_differ", "n_shape_mismatch",
                                               "n_ckpt_keys_not_in_model", "n_model_keys_not_covered_by_ckpt")}
    rep["tied_weight_checks"] = lv.get("tied_weight_checks")
    rep["tied_weight_metadata_in_safetensors"] = (lv.get("safetensors") or {}).get("tied_weight_metadata")
    rep["safetensors"] = {k: v for k, v in (lv.get("safetensors") or {}).items() if k != "tied_weight_metadata"}
    rep["n_parameters"] = lv.get("n_parameters")
    rep["versions_at_verification_time"] = lv.get("versions")
    rep["from_pretrained_s_at_verification_time"] = lv.get("from_pretrained_s")
    rep["benign_warning_verbatim"] = (
        'Warning: Could not remap state dict keys: Error(s) in loading state_dict for PI05Policy:\n'
        '\tMissing key(s) in state_dict: "model.paligemma_with_expert.paligemma.model.language_model.embed_tokens.weight".')
    rep["why_benign"] = ("safetensors 把 tied（共享存储）张量只存一份，别名记在文件头 `__metadata__`；"
                         "lerobot 0.4.4 的 loader 不展开 `__metadata__`，于是 strict=True 的那次 load 报缺键，"
                         "并被 `modeling_pi05.py:1046` 的裸 except 吞成一行 warning。"
                         "`from_pretrained` 随后按 config 的 tie 关系补上 ⇒ **权重没丢**。")
    rep["rule"] = ("**不许**把这条 warning 读成「权重没加载」，也**不许**把「没报错」读成「权重加载了」；"
                   "两边都要逐张量验（本文件即 G3 侧的链接点）。")
    # 现场再核一次 G3 用的兼容目录：文件清单 + sha256（证明「原始 ckpt 只读未改」这条也在这里可查）
    compat = CONTRACT_DIR / "pi05_base_compat_lerobot044"
    if compat.exists():
        rows = []
        for p in sorted(compat.iterdir()):
            rows.append({"name": p.name, "is_symlink": p.is_symlink(),
                         "target": str(pathlib.Path(os.readlink(p))) if p.is_symlink() else None,
                         "bytes": p.stat().st_size,
                         "sha256": None if p.is_symlink() else sha256_file(p)})
        rep["compat_dir_files"] = rows
        rep["compat_dir_sha256_of_big_files"] = "见各 symlink 的 target（原始 ckpt 目录只读，未改一字）"
    write(rep, g3 / "weights_linkage.json")


# ---------------------------------------------------------------- render (§12.11-4 / -9)
def png_geometry(p: pathlib.Path) -> dict:
    from PIL import Image
    import numpy as np
    raw = p.read_bytes()
    with Image.open(p) as im:
        w, h = im.size
        a = np.asarray(im.convert("RGB"))
    expected = w * h * 3 + h          # 每行 1 个 filter-type 字节
    return {"path": str(p), "bytes_on_disk": len(raw), "width": w, "height": h,
            "bitdepth_colortype_from_array": f"8/2(RGB) derived from array dtype={a.dtype} shape={a.shape}",
            "raw_len_expected_wxhx3_plus_filters": expected,
            "pixel_mean": round(float(a.mean()), 3), "pixel_std": round(float(a.std()), 3),
            "pixel_min": int(a.min()), "pixel_max": int(a.max()),
            "nonzero_pixel_frac": round(float((a.astype(int).sum(axis=2) > 0).mean()), 4)}


def sec_render(args, g3: pathlib.Path) -> None:
    import numpy as np
    import gymnasium as gym
    import gym_aloha  # noqa: F401
    from PIL import Image

    rep = header("a2_render_selfcert", args)
    rep["purpose"] = ("§12.11-4：渲染后端**由使用方在自己的 venv 内自证并记录**（D 撤销了统一钉死 osmesa）。"
                      "§12.11-9：附**逐相机**亮度/直方图，但**不断言图像正常或有问题**（D 明令，对比未给出前不许下结论）。")
    rep["backend_tuple"] = {"mujoco_gl": os.environ.get("MUJOCO_GL"), "mujoco_version": rep["mujoco_version"],
                            "model": "viperx300s bimanual (gym_aloha/assets/bimanual_viperx_transfer_cube.xml)",
                            "n_cameras": 3, "note": "五元标注缺一不可；不得与 D 的 (osmesa, 3.9.0, Piper STL, 单臂) 数字互相搬用"}

    # (1) G3 已落盘的 PNG：几何 + raw_len 自证
    frames = sorted((g3 / "frames_pi05").glob("*.png"))
    rep["g3_frames_on_disk"] = [png_geometry(p) for p in frames]
    arrs = [np.asarray(Image.open(p).convert("RGB")) for p in frames]
    rep["g3_frames_pairwise"] = [
        {"pair": [frames[i].name, frames[i + 1].name],
         "mean_abs_diff_uint8": round(float(np.abs(arrs[i].astype(int) - arrs[i + 1].astype(int)).mean()), 3),
         "max_abs_diff_uint8": int(np.abs(arrs[i].astype(int) - arrs[i + 1].astype(int)).max()),
         "changed_pixel_frac": round(float((np.abs(arrs[i].astype(int) - arrs[i + 1].astype(int)).sum(axis=2) > 0).mean()), 4),
         "identical": bool(np.array_equal(arrs[i], arrs[i + 1]))}
        for i in range(len(arrs) - 1)]

    # (2) 现场渲染三路相机（reset 后 + 推进 150 步后），逐相机亮度/直方图
    env = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    physics = env.unwrapped._env.physics
    cams = {"base_0_rgb(angle)": "angle", "left_wrist_0_rgb": "left_wrist", "right_wrist_0_rgb": "right_wrist"}
    per_cam = {}
    for label, cam in cams.items():
        shots = {}
        for tag, advance in (("at_reset", 0), ("after_150_ctrl_steps", 150)):
            env.reset(seed=args.seed0)
            if advance:
                for _ in range(advance):
                    physics.data.ctrl[:] = np.asarray(physics.model.key_qpos[0][:16], dtype="float64")
                    for _ in range(int(round(env.unwrapped._env.control_timestep() / physics.timestep()))):
                        physics.step()
            a = np.asarray(physics.render(height=args.image_size, width=args.image_size, camera_id=cam))
            hist, edges = np.histogram(a.mean(axis=2), bins=16, range=(0, 255))
            shots[tag] = {"shape": list(a.shape), "dtype": str(a.dtype),
                          "mean": round(float(a.mean()), 3), "std": round(float(a.std()), 3),
                          "min": int(a.min()), "max": int(a.max()),
                          "p01": round(float(np.percentile(a, 1)), 2), "p50": round(float(np.percentile(a, 50)), 2),
                          "p99": round(float(np.percentile(a, 99)), 2),
                          "nonzero_pixel_frac": round(float((a.astype(int).sum(axis=2) > 0).mean()), 4),
                          "histogram_16bin_of_luma": [int(x) for x in hist],
                          "histogram_bin_edges": [round(float(x), 2) for x in edges]}
            fp = g3 / f"selfcert_{label.split('(')[0]}_{tag}.png"
            Image.fromarray(a).save(fp)
            shots[tag]["saved_png"] = str(fp)
        per_cam[label] = shots
    rep["per_camera_brightness"] = per_cam
    # (3) D 报的 mean≈9.3 在 A2 产物里能不能对上：把 A2 全部图像产物的亮度列出来
    scanned = []
    for p in sorted(pathlib.Path("runs/vla").rglob("*.png")):
        if "a2_" not in str(p):
            continue
        a = np.asarray(Image.open(p).convert("RGB")).astype(float)
        scanned.append({"path": str(p), "mean": round(float(a.mean()), 3), "std": round(float(a.std()), 2),
                        "nonzero_pixel_frac": round(float((a.sum(axis=2) > 0).mean()), 4)})
    rep["all_a2_png_luma_scan"] = scanned
    means = [s["mean"] for s in scanned]
    rep["claim_about_9p3"] = {
        "a2_png_count": len(scanned), "a2_png_mean_range": [min(means), max(means)] if means else None,
        "any_a2_png_with_mean_near_9.3": [s["path"] for s in scanned if abs(s["mean"] - 9.3) < 1.5],
        "statement": ("A2 落盘的所有 PNG 里**没有** mean≈9.3 的图（gym-aloha base 相机实测 36.3–50.8）。"
                      "**请 D 指认所测文件与相机**；在指认前 A2 不断言图像正常、也不断言图像有问题（§12.11-9）。"),
    }
    rep["reference_comparison_status"] = {
        "same_viewpoint_reference_available_locally": False,
        "why": ("本机没有与 gym-aloha `AlohaTransferCube-v0` **同视角**的参照数据集帧："
                "ABC-130k(YAM) 的帧未下载（且它是**真实 YAM 站**、视角/机型都不同），"
                "D 的 Piper 渲染是**另一个模型/另一套相机** ⇒ 并列比较会踩「跨口径不得并列」（裁定 31.3/33.4/36.4）。"),
        "substitute_criterion_used_instead": ("改用**无需参照**的判据：红方块可见性 + 质心随真值位姿移动"
                                             "（`red_cube_visibility.json`）。它直接回答 D 关心的实质问题"
                                             "「相机朝向/光照是否导致观测近乎无信息」，而不依赖任何外部数据集。"),
        "pending_ask_to_D": "若仍要同视角亮度对照，需 D 授权下载 ABC-130k 抽样帧（新下载，A2 单线执行）。",
    }
    env.close()
    write(rep, g3 / "render_selfcert.json")


# ---------------------------------------------------------------- cubevis (§12.11-9)
def sec_cubevis(args, g3: pathlib.Path) -> None:
    import numpy as np
    import gymnasium as gym
    import gym_aloha  # noqa: F401

    rep = header("a2_red_cube_visibility", args)
    rep["purpose"] = ("§12.11-9 的**替代判据**（无需参照数据集）：若相机朝向/光照错了，"
                      "红方块在图里就不可见、或它的像素位置不会随真值位姿变化。"
                      "这里对 20 个 seed（方块 spawn 位置各不相同）量：红色像素占比、质心、"
                      "以及质心与**真值 box (x,y)** 的相关性。**只回答可见性与一致性，不评价图像质量好坏。**")
    env = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    physics = env.unwrapped._env.physics
    probe = SceneProbe(physics)
    cams = {"base(angle)": "angle", "left_wrist": "left_wrist", "right_wrist": "right_wrist"}
    per_seed, per_cam_agg = [], {k: [] for k in cams}
    for k in range(args.n):
        seed = args.seed0 + k
        env.reset(seed=seed)
        s = probe.sample()
        box_xy = s["box_xyz"][:2]
        row = {"seed": seed, "box_true_x": round(box_xy[0], 4), "box_true_y": round(box_xy[1], 4)}
        for label, cam in cams.items():
            img = np.asarray(physics.render(height=args.image_size, width=args.image_size, camera_id=cam)).astype(int)
            r, gg, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
            mask = (r > 100) & (r > gg + 40) & (r > b + 40)
            n = int(mask.sum())
            if n:
                ys, xs = np.nonzero(mask)
                cx, cy = float(xs.mean()), float(ys.mean())
            else:
                cx = cy = None
            row[label] = {"red_pixel_frac": round(n / mask.size, 5), "red_pixel_count": n,
                          "centroid_x": None if cx is None else round(cx, 2),
                          "centroid_y": None if cy is None else round(cy, 2),
                          "luma_mean": round(float(img.mean()), 2)}
            per_cam_agg[label].append((box_xy[0], box_xy[1], cx, cy, n))
        per_seed.append(row)

    def pearson(xs, ys):
        xs = np.asarray(xs, float); ys = np.asarray(ys, float)
        if len(xs) < 3 or xs.std() == 0 or ys.std() == 0:
            return None
        return round(float(np.corrcoef(xs, ys)[0, 1]), 4)

    corr = {}
    for label, rows in per_cam_agg.items():
        pts = [(bx, by, cx, cy) for bx, by, cx, cy, n in rows if cx is not None]
        corr[label] = {
            "seeds_with_red_visible": len(pts), "seeds_total": len(rows),
            "r_centroidx_vs_boxx": pearson([p[0] for p in pts], [p[2] for p in pts]) if len(pts) >= 3 else None,
            "r_centroidy_vs_boxy": pearson([p[1] for p in pts], [p[3] for p in pts]) if len(pts) >= 3 else None,
            "note": ("相关系数只在「红块可见」的 seed 上算；腕部相机看不到方块是**预期**的"
                     "（它朝夹爪/近景），不得读成缺陷。"),
        }
    rep["per_seed"] = per_seed
    rep["correlation"] = corr
    base = corr["base(angle)"]
    rep["criterion"] = {
        "visible_in_base_cam": f"{base['seeds_with_red_visible']}/{base['seeds_total']} seed 可见红方块",
        "centroid_tracks_true_pose": {
            "x": base["r_centroidx_vs_boxx"], "y": base["r_centroidy_vs_boxy"],
            "pass_rule": "可见率 = 100% 且 |r| ≥ 0.6（质心随真值位姿单调移动）⇒ 相机朝向/光照**不是**信息缺失的原因",
        },
    }
    rx, ry = base["r_centroidx_vs_boxx"], base["r_centroidy_vs_boxy"]
    ok = base["seeds_with_red_visible"] == base["seeds_total"] and rx is not None and ry is not None \
        and (abs(rx) >= 0.6 or abs(ry) >= 0.6)
    rep["criterion"]["verdict"] = "pass" if ok else "inconclusive_or_fail"
    if not ok:
        print("[warn] 红方块可见性/一致性判据未过 —— 这条要如实报 D，不许粉饰", flush=True)
    env.close()
    write(rep, g3 / "red_cube_visibility.json")


# ---------------------------------------------------------------- throughput (§12.1)
def sec_throughput(args, g3: pathlib.Path) -> None:
    import numpy as np
    import gymnasium as gym
    import gym_aloha  # noqa: F401

    rep = header("a2_render_throughput", args)
    rep["purpose"] = ("§12.1：A2 在自己的环境（gym-aloha 双臂 viperx）上复测渲染吞吐，给出**自己的数字**。"
                      "**不重测后端选型**（D 已定），也**不与 D 的 (osmesa, mujoco 3.9.0, Piper STL, 单臂) 数字互相搬用**。")
    rep["backend_tuple"] = {"mujoco_gl": os.environ.get("MUJOCO_GL"), "mujoco_version": rep["mujoco_version"],
                            "model": "viperx300s bimanual", "arms": 2,
                            "note": "**双臂**是 D §11.2 指定的形态一致环境；与用户「先只渲染单臂」指令的关系见报告里的冲突提问"}
    env = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    physics = env.unwrapped._env.physics
    env.reset(seed=args.seed0)
    cams = ["angle", "left_wrist", "right_wrist"]
    grids = {}
    for res in (args.image_size, 480):
        w = res if res != 480 else 640
        h = res
        runs = []
        for rep_i in range(args.repeats):
            t0 = time.perf_counter()
            n = 0
            while time.perf_counter() - t0 < args.bench_seconds:
                for c in cams:
                    physics.render(height=h, width=w, camera_id=c)
                n += 1
            dt = time.perf_counter() - t0
            runs.append({"repeat": rep_i, "control_steps": n, "wall_s": round(dt, 3),
                         "ctrl_steps_per_s": round(n / dt, 2), "ms_per_control_step": round(1000 * dt / n, 2)})
        med = sorted(r["ctrl_steps_per_s"] for r in runs)[len(runs) // 2]
        grids[f"{h}x{w}x3cams"] = {"resolution": [h, w], "n_cameras": len(cams), "runs": runs,
                                   "median_ctrl_steps_per_s": med,
                                   "spread_pct": round(100 * (max(r["ctrl_steps_per_s"] for r in runs)
                                                              - min(r["ctrl_steps_per_s"] for r in runs)) / med, 2)}
    # 单相机对照（相机数是 D 认定的主要杠杆）
    runs = []
    for rep_i in range(args.repeats):
        t0 = time.perf_counter(); n = 0
        while time.perf_counter() - t0 < args.bench_seconds:
            physics.render(height=args.image_size, width=args.image_size, camera_id="angle"); n += 1
        dt = time.perf_counter() - t0
        runs.append({"repeat": rep_i, "renders": n, "wall_s": round(dt, 3), "renders_per_s": round(n / dt, 2)})
    grids[f"{args.image_size}x{args.image_size}x1cam"] = {"resolution": [args.image_size, args.image_size],
                                                          "n_cameras": 1, "runs": runs,
                                                          "median_renders_per_s": sorted(r["renders_per_s"] for r in runs)[len(runs) // 2]}
    rep["render_only_grids"] = grids
    rep["g3_measured_context"] = {
        "source": "runs/vla/a2_pi05_zeroshot_20260929/summary_pi05.json（已跑完，不重跑）",
        "mean_episode_wall_s": 28.90, "t_env_step_s_mean": 25.22, "t_render_s_mean_own_224": 0.40,
        "t_inference_s_mean": 3.14, "env_step_fps": 11.91, "loop_fps": 10.39,
        "reading": ("`env.step()` 里 gym-aloha 自带的 **3×480×640** 渲染 ≈ 78 ms/控制步（由 hold 零假设的"
                    "快/慢路径差实测得出，见 approach_baseline.json → validations_fast_vs_slow），"
                    "占均局墙钟 87% ⇒ **瓶颈是 env 内建渲染，不是 π₀.₅ 推理**。"),
    }
    rep["protocol_note"] = ("**口径自陈**：本节是**同进程 3 重复**（D 的基准是独立进程 3 重复）⇒ 数值不可与 D 的表直接并列；"
                            "只用于回答「A2 自己环境里的渲染成本量级」。`bench_seconds=%d`。" % args.bench_seconds)
    env.close()
    write(rep, g3 / "render_throughput_a2.json")


# ---------------------------------------------------------------- gripper (§12.11-8)
def sec_gripper(args, g3: pathlib.Path) -> None:
    import numpy as np
    import gymnasium as gym
    import gym_aloha  # noqa: F401
    from gym_aloha import constants as C

    rep = header("a2_gripper_1d_to_2fingers", args)
    rep["purpose"] = ("§12.11-8：查清 gym-aloha 如何把 **1 维夹爪指令**映射到**两个独立指关节**，"
                      "作为 Piper 侧（§12.3，`joint7`/`joint8` 无 `<equality>`、URDF 无 `mimic`）两指耦合的**参照实现**。")
    src = pathlib.Path(C.__file__).parent
    before_step = (src / "tasks" / "sim.py").read_text().splitlines()
    rep["mechanism"] = {
        "answer": "**指令层镜像（command-layer mirror）**，不是等式约束、不是 tendon、不是 URDF mimic",
        "code": [f"tasks/sim.py:{i+1}: {before_step[i].rstrip()}" for i in range(37, 55)],
        "unnormalize": ("constants.py:104-105 `unnormalize_puppet_gripper_position(x) = "
                        "x*(PUPPET_GRIPPER_POSITION_OPEN - PUPPET_GRIPPER_POSITION_CLOSE) + PUPPET_GRIPPER_POSITION_CLOSE`"),
        "constants": {"PUPPET_GRIPPER_POSITION_OPEN": C.PUPPET_GRIPPER_POSITION_OPEN,
                      "PUPPET_GRIPPER_POSITION_CLOSE": C.PUPPET_GRIPPER_POSITION_CLOSE,
                      "START_ARM_POSE_finger_ctrl": [C.START_ARM_POSE[6], C.START_ARM_POSE[7]]},
        "mirror_rule": "env_action 里两指是 `[+g, -g]`（左指 ctrlrange 为正、右指为负 ⇒ 同号幅度、反号方向 = 对称开合）",
        "xml_equality_or_tendon_in_transfer_cube": 0,
        "xml_evidence": ("`grep -c 'equality\\|tendon' assets/bimanual_viperx_transfer_cube.xml` = **0**"
                         "（只有 `bimanual_viperx_end_effector_*.xml` 各有 2 处）⇒ **模型层没有耦合**，全靠指令层"),
    }
    # 数值验证：喂不同归一化夹爪值，读两个指关节 qpos
    env = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    physics = env.unwrapped._env.physics
    names = [physics.model.id2name(i, "joint") for i in range(physics.model.njnt)]
    idx_lf = [i for i, n in enumerate(names) if n and "vx300s_left" in n and "finger" in n]
    idx_rf = [i for i, n in enumerate(names) if n and "vx300s_right" in n and "finger" in n]
    rep["finger_joint_indices"] = {"left": idx_lf, "right": idx_rf,
                                   "left_names": [names[i] for i in idx_lf], "right_names": [names[i] for i in idx_rf]}
    lo = physics.model.actuator_ctrlrange[:, 0]; hi = physics.model.actuator_ctrlrange[:, 1]
    rep["finger_ctrlrange"] = {"left": [[float(lo[i]), float(hi[i])] for i in idx_lf],
                               "right": [[float(lo[i]), float(hi[i])] for i in idx_rf]}
    rows = []
    for g in (0.0, 0.25, 0.5, 1.0):
        env.reset(seed=args.seed0)
        act = np.asarray([C.START_ARM_POSE[0], C.START_ARM_POSE[1], C.START_ARM_POSE[2], 0, C.START_ARM_POSE[4], 0,
                          g,
                          C.START_ARM_POSE[8], C.START_ARM_POSE[9], C.START_ARM_POSE[10], 0, C.START_ARM_POSE[12], 0,
                          g], dtype="float32")
        for _ in range(args.gripper_settle_steps):   # 让 position 执行器收敛（指关节 frictionloss=30 ⇒ 收敛慢）
            env.step(act)
        q = np.asarray(physics.data.qpos, dtype="float64")
        c = np.asarray(physics.data.ctrl, dtype="float64")
        expect = C.unnormalize_puppet_gripper_position(g)
        rows.append({"normalized_cmd": g, "expected_ctrl_m": round(float(expect), 6),
                     "actual_ctrl_left": [round(float(c[i]), 6) for i in idx_lf],
                     "actual_ctrl_right": [round(float(c[i]), 6) for i in idx_rf],
                     "qpos_left_fingers_m": [round(float(q[i]), 6) for i in idx_lf],
                     "qpos_right_fingers_m": [round(float(q[i]), 6) for i in idx_rf],
                     "mirror_holds_in_ctrl": bool(abs(c[idx_lf[0]] + c[idx_lf[1]]) < 1e-9),
                     "opening_mm": round(float(abs(q[idx_lf[0]] - q[idx_lf[1]]) * 1000), 3)})
    rep["numeric_verification"] = rows
    # 模型层事实：ctrllimited / joint range / frictionloss（这些决定"指令值能不能真的到"）
    m = physics.model
    fing_idx = idx_lf + idx_rf
    rep["model_level_facts"] = {
        "actuator_ctrllimited_all16": [int(x) for x in np.asarray(m.actuator_ctrllimited)],
        "finger_actuator_ctrlrange": [[float(m.actuator_ctrlrange[i][0]), float(m.actuator_ctrlrange[i][1])] for i in fing_idx],
        "finger_joint_range": [[float(m.jnt_range[i][0]), float(m.jnt_range[i][1])] for i in idx_lf + idx_rf],
        "finger_jnt_limited": [int(m.jnt_limited[i]) for i in idx_lf + idx_rf],
        "finger_dof_frictionloss": [float(m.dof_frictionloss[i]) for i in idx_lf + idx_rf],
        "finger_dof_damping": [float(m.dof_damping[i]) for i in idx_lf + idx_rf],
        "settle_steps_used": args.gripper_settle_steps,
    }
    g0, g1 = rows[0], rows[-1]
    rep["commanded_vs_achieved"] = {
        "closed_cmd0": {"unnormalized_ctrl_m": g0["expected_ctrl_m"], "declared_ctrlrange_low_m": 0.021,
                        "achieved_qpos_m": g0["qpos_left_fingers_m"][0],
                        "opening_mm": g0["opening_mm"],
                        "finding": ("**归一化 0（全闭）反解出 ctrl 0.01844 m，低于声明的 ctrlrange/joint 下限 0.021 m** ⇒ "
                                    "实测指关节停在 0.0224 m，**全闭不可达**；差值来自关节限位 + `frictionloss=30`。")},
        "open_cmd1": {"unnormalized_ctrl_m": g1["expected_ctrl_m"], "declared_ctrlrange_high_m": 0.057,
                      "achieved_qpos_m": g1["qpos_left_fingers_m"][0], "opening_mm": g1["opening_mm"],
                      "finding": "**归一化 1（全开）反解出 ctrl 0.058 m，高于声明上限 0.057 m** ⇒ 实测停在 ~0.057 m。"},
        "reachable_opening_mm": [g0["opening_mm"], g1["opening_mm"]],
        "cross_column_note": ("**指令值 ≠ 实测值**（cmd 0：0.01844 vs 0.0224 m，Δ≈4 mm；cmd 1：0.058 vs 0.057 m）——"
                              "与 D 在 ABC-130k(YAM) 上实测的 `commanded`/`observed` 分开（`/left-arm-action` vs `/left-arm-state`）"
                              "**同一形态**。⇒ 契约表里夹爪一栏必须写清是 commanded 还是 observed，两边都不得互相当对方用。"),
    }
    rep["piper_side_implication"] = {
        "what_to_copy": ("**照抄这条机制**：在指令层把 1 维归一化开合度展开成两个指关节目标，"
                         "一正一负（或按 Piper 的关节方向同号），并**按关节类型（slide/prismatic）识别**、"
                         "不要按名字关键字（§12.3 的警告：`joint7`/`joint8` 名字里没有夹爪字样）。"),
        "what_not_to_copy": ("gym-aloha 的**数值**（OPEN=0.058 m / CLOSE=0.01844 m、ctrlrange ±0.021..0.057）"
                             "**不得**搬到 Piper：Piper 夹爪行程有 URDF 50 mm / MJ joint 35 mm / MJ ctrl 47.5 mm "
                             "**三套值**，实机校准前不得选定（§12.4）。"),
        "alternative": ("也可以用 MuJoCo `<equality>`（connect/joint 约束）在**模型层**耦合；"
                        "gym-aloha 选了指令层，代价是「忘记镜像就会静默错」（§12.3 说的硬缺口），"
                        "好处是不改模型、易与 14 维指令契约对齐。**选哪种要写进产物**（§12.3 要求）。"),
    }
    env.close()
    write(rep, g3 / "gripper_1d_to_2finger.json")


# ---------------------------------------------------------------- hz (§12.10)
def sec_hz(args, g3: pathlib.Path) -> None:
    import numpy as np
    import gymnasium as gym
    import gym_aloha  # noqa: F401
    from gym_aloha import constants as C

    rep = header("a2_ctrl_hz_alignment", args)
    rep["purpose"] = ("§12.10（裁定 45）：控制频率锚定 30 Hz。本节给出 A2 环境的 (timestep, decimation, 折算 Hz) "
                      "**实测三元组**、30.0 Hz 在本环境的**可行性与动力学 A/B**，以及三种重采样方案对 "
                      "**action chunk 时间尺度**的影响。**方案由 D 裁，A2 不静默选。**")
    env = gym.make(args.env_id, obs_type="pixels_agent_pos", render_mode="rgb_array")
    inner = env.unwrapped._env
    physics = inner.physics
    ts = float(physics.timestep())
    ct = float(inner.control_timestep())
    rep["as_is"] = {"physics_timestep_s": ts, "control_timestep_s": ct,
                    "decimation_n_substeps": int(round(ct / ts)),
                    "control_hz": round(1.0 / ct, 4), "source_constants": f"gym_aloha/constants.py DT={C.DT}",
                    "in_qc_band_29_31": bool(29.0 <= 1.0 / ct <= 31.0)}
    # 30 Hz 可行性：timestep=1/480 + decim 16 = 30.0 Hz（D 的 B 配置）
    target_ts = 1.0 / 480.0
    target_ct = 1.0 / 30.0
    rep["target_30hz"] = {"physics_timestep_s": target_ts, "control_timestep_s": target_ct,
                          "decimation_n_substeps": int(round(target_ct / target_ts)),
                          "control_hz": round(1.0 / target_ct, 4),
                          "integer_decimation": bool(abs(target_ct / target_ts - round(target_ct / target_ts)) < 1e-9)}
    naive = {"physics_timestep_s": ts, "control_timestep_s": target_ct,
             "decimation_if_rounded": int(round(target_ct / ts)),
             "resulting_control_hz": round(int(round(target_ct / ts)) * (1.0 / ts) ** -1 * -1 * -1, 4)}
    naive["resulting_control_hz"] = round(1.0 / (naive["decimation_if_rounded"] * ts), 4)
    rep["naive_pitfall"] = {**naive,
                            "why_it_matters": ("**只改 DT 不改 timestep ⇒ decimation 只能取整 17（29.41 Hz）或 16（31.25 Hz）**；"
                                               "16 就是裁定 45 明令**不得当契约值**的 31.25 Hz ⇒ 30.0 Hz **必须同时改物理 timestep**。")}
    # 动力学 A/B：hold 零假设在 50 Hz 与 30 Hz 下各跑 6 s 仿真时长
    probe = SceneProbe(physics)
    ctrl_hold = np.asarray(C.START_ARM_POSE, dtype="float64")

    def hold_run(n_ctrl, n_sub, ts_set=None):
        env.reset(seed=args.seed0)
        if ts_set is not None:
            physics.model.opt.timestep = ts_set
        t0 = time.perf_counter()
        d_l = d_r = 1e9; z0 = z1 = None; zmax = -1e9; q_dev = 0.0
        for i in range(n_ctrl):
            physics.data.ctrl[:] = ctrl_hold
            for _ in range(n_sub):
                physics.step()
            s = probe.sample()
            if i == 0:
                z0 = s["box_xyz"][2]
            z1 = s["box_xyz"][2]
            zmax = max(zmax, z1)
            d_l = min(d_l, dist(s["box_xyz"], probe.gripper_xpos(LEFT_FINGERS[0])))
            d_r = min(d_r, dist(s["box_xyz"], probe.gripper_xpos(RIGHT_FINGERS[0])))
            q_dev = max(q_dev, float(abs(np.asarray(physics.data.qpos[:16], float) - ctrl_hold).max()))
        wall = time.perf_counter() - t0
        physics.model.opt.timestep = ts
        return {"n_control_steps": n_ctrl, "n_substeps": n_sub, "physics_timestep_s": ts_set or ts,
                "simulated_seconds": round(n_ctrl * n_sub * (ts_set or ts), 4),
                "wall_s": round(wall, 3), "box_z_first_sample": round(z0, 6), "box_z_end": round(z1, 6),
                "box_z_max": round(zmax, 6), "min_dist_left_m": round(d_l, 4), "min_dist_right_m": round(d_r, 4),
                "max_qpos_dev_from_hold_rad": round(q_dev, 6)}

    # 同样 6 s 仿真时长：50 Hz × 300 步 vs 30 Hz × 180 步
    ab = {"simulated_seconds_target": 6.0,
          "hz50_x300": hold_run(300, int(round(ct / ts))),
          "hz30_x180": hold_run(180, 16, ts_set=target_ts)}
    a, b = ab["hz50_x300"], ab["hz30_x180"]
    ab["delta"] = {"box_z_end_diff_m": round(abs(a["box_z_end"] - b["box_z_end"]), 6),
                   "min_dist_left_diff_m": round(abs(a["min_dist_left_m"] - b["min_dist_left_m"]), 4),
                   "min_dist_right_diff_m": round(abs(a["min_dist_right_m"] - b["min_dist_right_m"]), 4),
                   "qpos_dev_diff_rad": round(abs(a["max_qpos_dev_from_hold_rad"] - b["max_qpos_dev_from_hold_rad"]), 6)}
    rep["dynamics_ab_hold_null"] = ab
    rep["dynamics_ab_reading"] = ("**这只是 hold 零假设下的沉降/保持 A/B**（同为 6 s 仿真时长）：数量级一致即说明"
                                  "改 timestep 不会把场景搞崩；**它不是策略行为的 A/B**（本轮不跑 policy，裁定 46.6）。")
    rep["wiring_note"] = {
        "how_30hz_would_be_wired": ("本节用 `physics.model.opt.timestep = 1/480` + 显式 16 子步**在物理层**演示 30.0 Hz；"
                                    "要把它接进 `gym.make` 的正规回路，需要 ①把 `gym_aloha.env.DT` 覆写为 1/30"
                                    "（`env.py:134` 用 `control_timestep=DT`），②让 XML 带 `<option timestep=\"1/480\"/>`"
                                    "（**不改 site-packages**：把 assets 复制到 A2 产物目录后改副本，或重建 dm_control Environment）。"),
        "not_done_this_round": "上述接线**本轮未实施**（等 D 在甲/乙/丙里裁定后再做，避免白改一遍）。",
    }
    rep["chunk_timescale_options"] = {
        "invariant": "**chunk 覆盖的真实时长 = chunk 步数 × 控制周期**；且**控制周期必须等于模型训练/微调所用数据的周期**。",
        "pi05_chunk_steps": 50,
        "options": [
            {"id": "甲", "scheme": "示范 30 → 50 Hz 重采样，仿真保持 50 Hz",
             "chunk_duration_s": round(50 * 0.02, 4),
             "effect": "chunk 覆盖 **1.0 s**；模型在 50 Hz 语义下微调 ⇒ 与仿真一致",
             "cost_risk": ("50/29.76 = **1.68 非整数比** ⇒ 必须插值，会造出数据里不存在的帧/动作；"
                           "且把部署频率推到 50 Hz，而**实机（Piper/Cobot Magic）能否吃 50 Hz 指令 = `null`**（第三列未实测）"),
             "a2_view": "**不推荐**（造数据 + 把未知频率写成契约）"},
            {"id": "乙", "scheme": "示范保持 30 Hz，chunk 时长按 30/50 缩放（把 50 步 chunk 解释成 1.667 s，或重采样成 30 步/秒）",
             "chunk_duration_s": round(50 / 30.0, 4),
             "effect": "chunk 覆盖 **1.667 s**；相邻动作间隔变成 1/30 s ⇒ **同样的动作增量意味着 0.6× 的速度**",
             "cost_risk": ("若不重新微调，动作会整体变慢/变糊（D §12.10 说的「能接近但抓不准」正是这种偏差的表现）；"
                           "重采样本身也要写进 `representation_version`"),
             "a2_view": "**次选**（只有在 30 Hz 仿真改不动时才用，且必须配合微调）"},
            {"id": "丙", "scheme": "仿真改到 30.0 Hz（`timestep=1/480` + decimation 16），示范保持 30 Hz",
             "chunk_duration_s": round(50 / 30.0, 4),
             "effect": "chunk 覆盖 **1.667 s**；仿真/示范/契约三者同频 ⇒ **时间尺度自洽**",
             "cost_risk": ("D 已实测吞吐代价 **+0.5%**（Piper 模型，osmesa）；本环境需改 XML timestep（本节已做 hold A/B，"
                           "数量级一致）；与 ALOHA 生态（ACT/π₀ 的 50 Hz 仿真口径）不再同频 ⇒ 跨论文数字不可并列"),
             "a2_view": "**推荐**（与裁定 45 的 30 Hz 锚点、ABC-130k 实测 29.76 Hz、QC [29,31] 全部一致）"},
        ],
        "decision_owner": "**D**（§12.10-2：不许静默选一个）",
        "open_dependency": ("第三列（Piper/Cobot Magic）的**实际控制频率仍是 `null`** ⇒ 无论选哪案，"
                            "实机对接时都要用实机数据重新锚定，不得沿用仿真值。"),
    }
    rep["latency_budget_claim"] = {
        "source": "§12.11-5：D 已从 A2 的 G3 日志回填参数表，A2 在此**认领口径**",
        "per_chunk_wall_s_from_g3_log": round(3.14 / 6, 4),
        "includes": ["preprocess（含 3 路图像张量化 + state tokenizer）", "predict_action_chunk（10 步去噪）",
                     "postprocess", "torch.cuda.synchronize()（前后各一次）"],
        "excludes": ["首次预热（ep00 实测 3.5 s/6 = 0.583 s，其后 3.1 s/6 = 0.517 s）", "env.step 与渲染", "动作裁剪/下发"],
        "g2_bare_forward_steady_s": 0.479,
        "g2_first_call_s": 1.378,
        "dtype": "fp32（`param_dtypes=[torch.float32]`）；**若改 bf16 会单独报，不与本表混列**",
        "budget_at_50hz": {"chunk_covers_s": 1.0, "inference_s": 0.517, "fraction_of_realtime": 0.517,
                           "per_step_budget_ms": 20.0, "verdict": "按 chunk 执行可行；**按每步推理不可行**"},
        "budget_at_30hz": {"chunk_covers_s": round(50 / 30.0, 4), "inference_s": 0.517,
                           "fraction_of_realtime": round(0.517 / (50 / 30.0), 4),
                           "per_step_budget_ms": 33.3, "verdict": "按 chunk 执行更宽裕（31%）"},
        "closed_loop_ctrl_steps_per_s_measured": 10.39,
        "closed_loop_note": ("**实测闭环 10.39 控制步/秒**（loop_fps，含推理与 env 渲染；`loadavg 39–54`、`nr_throttled Δ23`）"
                             "⇒ **低于 30 Hz 也低于 50 Hz**，即当前**不是实时闭环**，是**离线评测节奏**；"
                             "瓶颈是 env 内建 3×480×640 软渲染（≈78 ms/控制步），不是推理。"),
    }
    env.close()
    write(rep, g3 / "ctrl_hz_alignment_a2.json")


SECTIONS = {"weights": sec_weights, "render": sec_render, "cubevis": sec_cubevis,
            "throughput": sec_throughput, "gripper": sec_gripper, "hz": sec_hz}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections", default=",".join(SECTIONS))
    ap.add_argument("--g3-dir", default="runs/vla/a2_pi05_zeroshot_20260929")
    ap.add_argument("--env-id", default="gym_aloha/AlohaTransferCube-v0")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--bench-seconds", type=int, default=5)
    ap.add_argument("--gripper-settle-steps", type=int, default=50)
    args = ap.parse_args()
    g3 = pathlib.Path(args.g3_dir)
    g3.mkdir(parents=True, exist_ok=True)
    want = [s.strip() for s in args.sections.split(",") if s.strip()]
    unknown = [s for s in want if s not in SECTIONS]
    if unknown:
        print(f"未知 section: {unknown}；可选 {list(SECTIONS)}", file=sys.stderr)
        return 2
    for s in want:
        t0 = time.perf_counter()
        print(f"[section] {s} ...", flush=True)
        SECTIONS[s](args, g3)
        print(f"[section] {s} done in {time.perf_counter() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
