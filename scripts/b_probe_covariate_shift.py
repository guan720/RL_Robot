#!/usr/bin/env python3
"""B 线：闭环失败的机制取证 —— 是「感知不足」还是「协变量漂移」？

前面两个探针已经把范围收窄：
  1. scripts/b_probe_dz_identifiability.py
     teacher 内部模式在观测里**是可辨识的**：lift vs 非 lift 在「夹爪已闭合」子集上
     recall_lift=1.000、approx_auc=0.996；descend vs 非 descend 在「夹爪张开」子集上
     recall=0.993。所以不是「ACT 拿到的信息不足」。
  2. 执行侧约束扫描（runs/infra/b_flick_sweep/、runs/infra/b_dzdeadband/）
     slew cap ∈ {0.5,0.25,0.1} 与 dz deadband ∈ {0.15,0.2,0.3} 共 7 个臂，
     **受控成功全部 0/20**。所以也不是「命令幅度过大」这种能在执行侧掐掉的东西。
  3. 逐帧取证（runs/infra/b_dzdeadband/none_trace.json，seed 5002）显示：
     帧 0-17 dz=-1 正确下降；帧 18-24 在正确高度闭爪、held=True；
     帧 24-33 正确抬升，rise 到 +0.069（teacher 的 LIFT_TARGET=0.05）——
     **前三段全对**。帧 34 起 dz 在 ±0.2~±1.0 之间来回摆，rise 在 0.058~0.072 抖动，
     随后 260 帧里 eef_z 从 0.827 单调漂到 1.200（远超任何 teacher 状态），
     而 dz_cmd 多数时候是 -1.0。命令与实际运动方向相反 = 已离开数据流形，
     策略在从未见过的状态上输出，闭环把它推得更远。

本脚本把这个论断量化：用训练集自己的最近邻距离当「流形内」的标尺，
统计闭环轨迹有多少帧落在示范流形之外，以及**从哪一帧开始跑出去、还回不回得来**。

只读 runs/infra/lerobot_act_lift_state_overfit/data/ 与既有 checkpoint，
只写 runs/infra/b_covariate_shift/。不修改 A/C 的文件。
"""
from __future__ import annotations
import argparse, glob, hashlib, json, sys, time
from pathlib import Path
import numpy as np
import torch

# 探针**构建指纹**。实测教训（2026-09-28 晚）：本脚本首轮在 raw 归一化空间里算最近邻距离，
# 被 3 个近常量维主导，量出 nn_median=1545 / OOD=99.3% / 首次越界帧=2 的**度量伪影**；
# 代码后来改成 robust 空间（std>=1e-3），但 runs/infra/b_covariate_shift/covariate_shift.json
# 仍是首轮产物（metric_note 为 null、rows 里没有 raw_norm_* 字段），
# 于是「代码已修、产物未重跑」被误当成「产物有缺陷、结论不采信」。
# 没有构建指纹时这种陈旧产物无法被自动识别，所以每份产物都必须自描述。
PROBE_BUILD = hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()[:12]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts._venv import ensure_venv  # noqa: E402
ensure_venv("robosuite", "numpy")

from harness.env_factory import (PINNED_OBJECT_SEED, contact_object_geom,  # noqa: E402
                                 make_contact_env, reset_contact)
from scripts.probe_contact_ceiling import grasp_truth_fn  # noqa: E402
from scripts.train_act_lift import ChunkPolicy  # noqa: E402

DATA = ROOT / "runs/infra/lerobot_act_lift_state_overfit/data"
OUT = ROOT / "runs/infra/b_covariate_shift"
# object-state 在 60 维 state obs 的末 10 维（实测 2026-09-28，见 obs 布局契约）
OBJ_SLICE = slice(50, 60)
CUBE_POS_SLICE = slice(50, 53)
G2C_SLICE = slice(57, 60)


def pdist2(a, b):
    return np.maximum((a * a).sum(1)[:, None] + (b * b).sum(1)[None, :] - 2.0 * (a @ b.T), 0.0)


def nn_stats(q, ref, topk=3):
    """最近邻距离 + **距离集中度**（前 topk 维贡献的平方距离占比）。

    为什么必须一起报：本探针首轮把距离算在 raw 归一化空间里，被 3 个近常量维主导，
    量出 nn_median=1545 / OOD=99.3% / 首次越界帧=2；改成剔除 std<1e-3 的维之后，
    2026-09-28 晚重跑仍是 OOD=99.3% / first_exit=2，而 top5 放大维变成了
    28/30/32/34/38（std 1e-3~1e-2，放大 100~600 倍）——说明 1e-3 这个绝对下限**还是太弱**，
    且「第 2 帧就越界」这种时序结论在度量被少数维主导时根本不可信。
    集中度就是这个度量的**自检**：若前 3 维贡献超过 50% 的平方距离，
    该距离不能用来主张 OOD 比例或首次越界帧（`metric_degenerate=True`）。
    """
    d2 = pdist2(q, ref)
    j = d2.argmin(1)
    d2min = d2[np.arange(len(q)), j]
    diff2 = (q - ref[j]) ** 2
    total = diff2.sum(1)
    srt = np.sort(diff2, 1)[:, ::-1]
    conc = srt[:, :topk].sum(1) / np.maximum(total, 1e-12)
    return d2min ** 0.5, conc, j
def load_teacher(split, hist):
    X, PH = [], []
    for f in sorted(glob.glob(str(DATA / "episode_*.npz"))):
        z = np.load(f)
        if str(z["split"]) != split:
            continue
        s, c, ph = z["observation_state"], z["action_chunk"], z["phase"]
        for t in range(len(c)):
            X.append(np.concatenate([s[max(0, t - (hist - 1) + k)] for k in range(hist)]).astype(np.float32))
            PH.append(str(ph[t]))
    return np.asarray(X), np.asarray(PH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="runs/infra/b_act_lift_mb_hist1_pinned_seed0/model_final.pt")
    ap.add_argument("--seeds", default="5000,5002,5015,5018,5005,5011")
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--chunk-length", type=int, default=4)
    ap.add_argument("--out", default=str(OUT / "covariate_shift.json"))
    a = ap.parse_args()

    ck = torch.load(ROOT / a.ckpt, map_location="cpu", weights_only=False)
    history = int(ck.get("history", 1))
    model = ChunkPolicy(int(ck["obs_dim"]), a.chunk_length)
    model.load_state_dict(ck["model"]); model.eval()
    mean = np.asarray(ck["obs_mean"], np.float32); std = np.asarray(ck["obs_std"], np.float32)

    xtr, phtr = load_teacher("train", history)
    xva, phva = load_teacher("validation", history)

    # 距离度量必须剔除退化维：state obs 的第 7/9/11 维是 cos(joint0/2/4)，teacher 里
    # 距离度量修过三轮，全部记录在这里，避免再拿旧结论当新结论：
    #   首轮：在 raw 归一化空间算距离 -> 被 dim 7/9/11（std 6.2e-04 / 9.7e-05 / 9.3e-04）主导，
    #         nn_median=1545 vs teacher 标尺 4.5。
    #   二轮：剔除 std<1e-3 的维 -> 重跑仍是 OOD=99.3% / first_exit=2，但 top5 放大维换成了
    #         28/30/32/34/38（std 1e-3~1e-2，放大 100~600 倍），说明**绝对下限 1e-3 还是太弱**。
    #   三轮（本次）：改用与交接单 1 训练修复**同一个**相对下限
    #         std_eff = max(std, 1e-2 * max|x_train|)，并用 nn_stats 报「距离集中度」自检。
    # 结论口径（重要）：OOD **比例**与「首次越界帧」只有在 metric_degenerate=False 时才可引用；
    #   而「网络实际输入 |x| 超界帧占比」是**直接测量**、不经任何度量，任何时候都可引用。
    STD_FLOOR_REL = 1e-2
    absmax_tr = np.maximum(np.abs(xtr).max(0), 1e-3)
    std_eff = np.maximum(std, STD_FLOOR_REL * absmax_tr).astype(np.float32)
    degenerate = [int(i) for i in np.where(std < 1e-3)[0]]
    floored = [[int(i), float(std[i]), float(std_eff[i]), float(std[i] / std_eff[i])]
               for i in np.where(std_eff > std)[0]]
    ntr = (xtr - mean) / std_eff
    nva = (xva - mean) / std_eff
    rtr, rva = ntr, nva

    # 标尺：held-out teacher 帧到训练流形的最近邻距离分布。
    # 这是「同一分布、只是不同 episode」的距离，所以它的 p99 就是流形内的合理上界。
    d_va, conc_va, _ = nn_stats(rva, rtr)
    thr = float(np.percentile(d_va, 99))
    ruler_conc = float(np.median(conc_va))
    scale = {"teacher_val_nn_dist_median": float(np.median(d_va)),
             "teacher_val_nn_dist_p95": float(np.percentile(d_va, 95)),
             "teacher_val_nn_dist_p99": float(thr),
             "teacher_val_nn_dist_max": float(d_va.max()),
             "ruler_dist_concentration_top3_median": ruler_conc,
             "std_floor_rel": STD_FLOOR_REL,
             "n_dims_floored": int((std_eff > std).sum()),
             "n_train_frames": int(len(ntr)), "n_val_frames": int(len(nva))}
    # 分 phase 看 held-out 距离，避免用 done 帧（占 72%，密集）拉低标尺
    per_phase = {p: {"n": int((phva == p).sum()),
                     "nn_median": float(np.median(d_va[phva == p])) if (phva == p).any() else None,
                     "nn_p99": float(np.percentile(d_va[phva == p], 99)) if (phva == p).any() else None}
                 for p in sorted(set(phva.tolist()))}
    thr_task = float(np.percentile(d_va[~np.isin(phva, ["done", "hold"])], 99))

    env = make_contact_env("lift", horizon=a.horizon, reward_shaping=True, obs_mode="state")
    seeds = [int(x) for x in a.seeds.split(",")]
    out_rows = []
    try:
        for seed in seeds:
            obs = reset_contact(env, seed)
            raw = env._env._get_observations()
            z0 = float(raw["cube_pos"][2]); truth = grasp_truth_fn(env, "lift")
            hist_buf, rec, frames, held_ever, raw_succ = [], [], 0, False, False
            t0 = time.perf_counter()
            while frames < a.horizon:
                cur = np.asarray(obs, dtype=np.float32)
                hist_buf.append(cur); hist_buf = hist_buf[-history:]
                while len(hist_buf) < history:
                    hist_buf.insert(0, hist_buf[0].copy())
                xin = np.concatenate(hist_buf)
                with torch.no_grad():
                    chunk = model(torch.tensor(((xin - mean) / std)[None]))[0].numpy()
                for j in range(min(a.chunk_length, a.horizon - frames)):
                    cmd = np.clip(chunk[j], -1.0, 1.0).astype(np.float32)
                    obs, _, term, trunc, info = env.step(cmd)
                    raw = env._env._get_observations(); frames += 1
                    held_ever = held_ever or bool(truth())
                    raw_succ = raw_succ or bool(info.get("success", False))
                    rec.append({"f": frames, "x": xin.copy(),
                                "eef_z": float(raw["robot0_eef_pos"][2]),
                                "cube_z": float(raw["cube_pos"][2]),
                                "rise": float(raw["cube_pos"][2]) - z0,
                                "g2c_z": float(raw["gripper_to_cube_pos"][2]),
                                "dz": float(cmd[2]), "held": bool(truth())})
                    xin = np.asarray(obs, dtype=np.float32)
                    if term or trunc:
                        break
                if term or trunc:
                    break
            X = np.stack([r["x"] for r in rec])
            # 两套量必须分开：NX_eff 只用于**度量**（相对下限，压掉平坦维的主导权）；
            # NX_raw 是训练时真实喂进网络的量，一字不改 —— 超界帧占比是直接测量，
            # 不依赖任何度量假设，因此它是本探针唯一无条件可引用的数字。
            NX_eff = (X - mean) / std_eff
            NX_raw = (X - mean) / std
            nn, conc, _ = nn_stats(NX_eff, rtr)
            raw_absmax_per_frame = np.abs(NX_raw).max(1)
            raw_absmax_per_dim = np.abs(NX_raw).max(0)
            ood = nn > thr
            first = int(np.argmax(ood)) if ood.any() else None
            # 「跑出去就回不来」：首次越界之后仍在流形外的帧占比
            tail_ood = float(ood[first:].mean()) if first is not None else 0.0
            row = {"seed": seed, "frames": frames, "success_raw": raw_succ, "held_ever": held_ever,
                   "rise_max": round(max(r["rise"] for r in rec), 4),
                   "rise_final": round(rec[-1]["rise"], 4),
                   "eef_z_final": round(rec[-1]["eef_z"], 4),
                   "eef_z_max": round(max(r["eef_z"] for r in rec), 4),
                  "nn_median": round(float(np.median(nn)), 4),
                  "nn_p95": round(float(np.percentile(nn, 95)), 4),
                  "nn_max": round(float(nn.max()), 4),
                  # 度量自检：前 3 维贡献的平方距离占比。>0.5 说明距离被少数维主导，
                  # 该行的 OOD% 与 first_ood_frame **不得**被引用（只能引用直接测量的超界帧%）。
                  "dist_concentration_top3_median": round(float(np.median(conc)), 4),
                  "metric_degenerate": bool(float(np.median(conc)) > 0.5),
                   "ood_frac_vs_teacher_p99": round(float(ood.mean()), 4),
                   "ood_frac_vs_task_p99": round(float((nn > thr_task).mean()), 4),
                   "first_ood_frame": (first + 1 if first is not None else None),
                   "ood_frac_after_first_exit": round(tail_ood, 4),
                   "raw_norm_input_absmax": round(float(raw_absmax_per_frame.max()), 2),
                   "raw_norm_input_median": round(float(np.median(raw_absmax_per_frame)), 2),
                   "raw_norm_input_frac_over_train_max": round(float((raw_absmax_per_frame > 23.7).mean()), 4),
                   "raw_norm_absmax_on_degenerate_dims": {str(i): round(float(raw_absmax_per_dim[i]), 1)
                                                          for i in degenerate},
                   "raw_norm_absmax_top5_dims": [[int(i), round(float(raw_absmax_per_dim[i]), 1)]
                                                 for i in np.argsort(-raw_absmax_per_dim)[:5]],
                   "elapsed_sec": round(time.perf_counter() - t0, 2)}
            out_rows.append(row)
            print("  seed %d frames=%d raw=%d rise_max=%.3f eef_z_max=%.3f | robust nn_med=%.2f "
                  "OOD=%.1f%% first_exit=%s | 网络实际输入 |x|max=%.0f（训练上界 23.7）超界帧=%.0f%%"
                  % (seed, frames, int(raw_succ), row["rise_max"], row["eef_z_max"], row["nn_median"],
                     100 * row["ood_frac_vs_teacher_p99"], row["first_ood_frame"],
                     row["raw_norm_input_absmax"], 100 * row["raw_norm_input_frac_over_train_max"]), flush=True)
        geom = contact_object_geom(env, "lift", PINNED_OBJECT_SEED)
    finally:
        env.close()

    n = len(out_rows)
    res = {"ckpt": str(Path(a.ckpt).resolve()), "history": history, "seeds": seeds,
           "manifold_ruler": scale, "teacher_val_nn_by_phase": per_phase,
           "thresholds": {"teacher_p99": thr, "task_relevant_p99": thr_task},
           "probe_build": PROBE_BUILD,
           "metric_space": {
               "kind": "floored_nn",
               "std_eff": "max(std, %.3g * max|x_train|)" % STD_FLOOR_REL,
               "std_floor_rel": STD_FLOOR_REL,
               "n_dims_total": int(len(std)),
               "n_dims_floored": int((std_eff > std).sum()),
               "degenerate_dims_std_lt_1e-3": degenerate,
               # [dim, std, std_eff, 被抬升的倍数] —— 抬升越多说明该维原本越会主导距离
               "floored_dims": [[i, round(s, 8), round(se, 8), round(s / se, 4)]
                                for i, s, se, _ in
                                [(f[0], f[1], f[2], f[3]) for f in floored]],
               "raw_norm_train_absmax_bound": 23.7,
               "history_of_metric": [
                   "round1: raw 归一化空间 -> 被 dim 7/9/11 主导，nn_median=1545（伪影）",
                   "round2: 剔除 std<1e-3 -> 仍 OOD=99.3%/first_exit=2，改由 dim 28-38 主导（下限太弱）",
                   "round3(本产物): 相对下限 std_eff + 距离集中度自检",
               ],
               "note": ("OOD 比例与 first_ood_frame 只在 metric_degenerate=False 时可引用；"
                        "raw_norm_input_frac_over_train_max 是直接测量，无条件可引用。")},
           "metric_note": ("距离在 floored 空间算：std_eff = max(std, %.3g*max|x_train|)，"
                           "%d/%d 维被抬升；标尺自身集中度 top3 = %.3f。"
                           "训练时归一化 |x| 上界 = 23.7。"
                           % (STD_FLOOR_REL, int((std_eff > std).sum()), int(len(std)), ruler_conc)),
            "object_geom": geom, "rows": out_rows,
            "summary": {"episodes": n,
                       "mean_ood_frac": round(float(np.mean([r["ood_frac_vs_teacher_p99"] for r in out_rows])), 4),
                       "mean_first_exit_frame": (round(float(np.mean([r["first_ood_frame"] for r in out_rows
                                                                      if r["first_ood_frame"]])), 1)
                                                 if any(r["first_ood_frame"] for r in out_rows) else None),
                       "mean_ood_after_exit": round(float(np.mean([r["ood_frac_after_first_exit"]
                                                                   for r in out_rows])), 4),
                       "n_reached_hold_region_then_left": sum(1 for r in out_rows if r["eef_z_max"] > 1.0),
                       # --- 度量自检：决定上面哪些数字可以被引用 ---
                       "mean_dist_concentration_top3": round(float(np.mean(
                           [r["dist_concentration_top3_median"] for r in out_rows])), 4),
                       "ruler_dist_concentration_top3": round(ruler_conc, 4),
                       "n_metric_degenerate_rows": sum(1 for r in out_rows if r["metric_degenerate"]),
                       "ood_numbers_citable": bool(ruler_conc <= 0.5 and
                                                   not any(r["metric_degenerate"] for r in out_rows)),
                       # 直接测量，不经度量，无条件可引用
                       "mean_raw_norm_frac_over_train_max": round(float(np.mean(
                           [r["raw_norm_input_frac_over_train_max"] for r in out_rows])), 4),
                       "max_raw_norm_input_absmax": round(float(max(
                           r["raw_norm_input_absmax"] for r in out_rows)), 1)}}
    outp = Path(a.out); outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")

    print("\n== 流形标尺（held-out teacher 帧 -> 训练集最近邻距离）==")
    print("  中位数 %.3f  p95 %.3f  p99 %.3f（= OOD 阈值）  max %.3f"
          % (scale["teacher_val_nn_dist_median"], scale["teacher_val_nn_dist_p95"], thr,
             scale["teacher_val_nn_dist_max"]))
    print("  任务相关帧（去掉 done/hold）p99 = %.3f" % thr_task)
    for p, e in per_phase.items():
        print("    %-9s n=%4d nn_median=%.3f nn_p99=%.3f" % (p, e["n"], e["nn_median"], e["nn_p99"]))
    print("\n== 闭环轨迹（floored 距离：std_eff = max(std, %.3g*max|x_train|)）==" % STD_FLOOR_REL)
    print("  %-6s %6s %4s %8s %9s %8s %8s %7s %7s %10s %9s" %
          ("seed", "frames", "raw", "rise_max", "eefz_max", "nn_med", "nn_max", "OOD%", "exit", "|x|max", "超界帧%"))
    for r in out_rows:
        print("  %-6d %6d %4d %8.3f %9.3f %8.2f %8.2f %7.1f %7s %10.0f %9.0f" %
              (r["seed"], r["frames"], int(r["success_raw"]), r["rise_max"], r["eef_z_max"],
               r["nn_median"], r["nn_max"], 100 * r["ood_frac_vs_teacher_p99"], r["first_ood_frame"],
               r["raw_norm_input_absmax"], 100 * r["raw_norm_input_frac_over_train_max"]))
    print("\n== 退化维上的输入放大（网络实际收到的量，训练时上界 23.7）==")
    for r in out_rows:
        print("  seed %-6d dims %s   top5 %s"
              % (r["seed"], r["raw_norm_absmax_on_degenerate_dims"], r["raw_norm_absmax_top5_dims"]))
    s = res["summary"]
    print("\n  平均 OOD 帧占比 = %.1f%%；平均首次越界帧 = %s；越界后仍在流形外的帧占比 = %.1f%%"
          % (100 * s["mean_ood_frac"], s["mean_first_exit_frame"], 100 * s["mean_ood_after_exit"]))
    print("  距离集中度 top3：标尺 = %.3f，闭环均值 = %.3f（>0.5 即度量被少数维主导）"
          % (s["ruler_dist_concentration_top3"], s["mean_dist_concentration_top3"]))
    if s["ood_numbers_citable"]:
        print("  裁定：度量非退化，OOD 比例与首次越界帧**可引用**。")
    else:
        print("  裁定：度量退化（%d/%d 行集中度 >0.5），OOD 比例与「首次越界帧」**不得引用**；"
              "只能引用直接测量：平均超界帧 = %.1f%%，|x|max = %.0f（训练上界 23.7）。"
              % (s["n_metric_degenerate_rows"], s["episodes"],
                 100 * s["mean_raw_norm_frac_over_train_max"], s["max_raw_norm_input_absmax"]))
    print("写出:", outp)


if __name__ == "__main__":
    main()
