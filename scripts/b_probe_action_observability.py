#!/usr/bin/env python3
"""B 线可学性预检：teacher 动作到底是不是观测的函数？BC 的 r² 上界在哪？

为什么需要它（v4 P1「可控与可学性预检」的落地）：
  离线欠拟合探针（runs/infra/b_bc_retrain/bc_underfit_probe_hist1_seed0.json）显示，六个臂里
  **没有一个** 把 dz 学到 r²>0.6：A1 minibatch dz r²=0.158 / bias=+0.111，
  A3 丢空转帧反而掉到 -5.01 / bias=+0.448，hist=4 同样更差。
  加梯度预算、加历史、改样本配比三种「训练侧」修法全部无效——这提示瓶颈可能不在优化，
  而在 (a) 观测不含区分 teacher 模式所需的信息（真部分可观测），或
  (b) 输入归一化病态导致网络无法利用已有信息。

本脚本离线、只读 runs/infra/lerobot_act_lift_state_overfit/data/，不碰 robosuite、
不碰 A/C 的文件，只写 runs/infra/b_observability/。

三个测量，互相独立：
  M1 归一化条件数：逐维 std，以及归一化后 |x| 的最大值。std≈0 的维会被放大数千倍，
     第一层权重的梯度被它主导 -> 其余维有效学习率坍缩。
  M2 kNN 条件方差上界：对每个 val 帧找 k 个最近 train 帧，teacher 动作在这些近邻里
     的方差 = 任何**确定性**回归器在该观测下不可消除的误差。
     ceiling_r2 = 1 - E[Var(a|o)] / Var(a)。它给出「训练侧再怎么调都到不了」的硬上界。
  M3 别名取证：把 obs 距离极小但 |Δdz| 很大的帧对打印出来，连同各自 phase。
     若这些对跨越 lift/hold 或 grasp/descend，就说明 teacher 依赖观测里没有的内部计时器。
"""
from __future__ import annotations
import argparse, glob, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "runs/infra/lerobot_act_lift_state_overfit/data"
OUT = ROOT / "runs/infra/b_observability"
DIM_NAMES = ["dx", "dy", "dz", "droll", "dpitch", "dyaw", "grip"]
IDLE_PHASES = {"done", "hold"}


def pdist2(a, b):
    """||a_i - b_j||^2，用 matmul 避免 (n,m,d) 中间张量（2376x5448x60 会吃 3GB）。"""
    return (np.maximum((a * a).sum(1)[:, None] + (b * b).sum(1)[None, :] - 2.0 * (a @ b.T), 0.0))


def load(split, hist):
    """按 scripts/b_bc_underfit_probe.py 的同一构造：history 只用当前及过去帧，首帧复制填充。"""
    X, A, PH, EP = [], [], [], []
    for f in sorted(glob.glob(str(DATA / "episode_*.npz"))):
        z = np.load(f)
        if str(z["split"]) != split:
            continue
        s, c, ph = z["observation_state"], z["action_chunk"], z["phase"]
        ep = int(z["episode_index"])
        for t in range(len(c)):
            X.append(np.concatenate([s[max(0, t - (hist - 1) + k)] for k in range(hist)]).astype(np.float32))
            A.append(c[t][0].astype(np.float32))     # 与训练目标一致：chunk 的首步动作
            PH.append(str(ph[t])); EP.append(ep)
    return (np.asarray(X), np.asarray(A), np.asarray(PH), np.asarray(EP))


def knn_cond_var(xtr, atr, xva, ava, k):
    """返回 (per_dim_cond_var, per_dim_ceil_r2, nn_dist, idx)。距离在归一化空间里算。"""
    d = pdist2(xva, xtr)
    idx = np.argpartition(d, k, axis=1)[:, :k]
    nn_d = np.take_along_axis(d, idx, 1).max(1) ** 0.5
    nb = atr[idx]                                   # (n_va, k, 7)
    cond_var = nb.var(0).mean(0)                    # E[Var(a|o)]
    tot_var = ava.var(0)
    ceil_r2 = np.where(tot_var > 1e-12, 1.0 - cond_var / np.maximum(tot_var, 1e-12), np.nan)
    return cond_var, ceil_r2, nn_d, idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", type=int, default=1)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--alias-dist", type=float, default=0.05,
                    help="别名取证的归一化 obs 距离阈值")
    ap.add_argument("--alias-ddz", type=float, default=0.5,
                    help="别名取证的 |Δdz| 阈值")
    ap.add_argument("--val-split", default="validation", choices=["validation", "test"],
                    help="ceiling 用哪个 held-out 集；test = pinned 5000-5019（闭环评测同一题集）")
    ap.add_argument("--out", default=str(OUT / "observability_hist{k}_seed0.json"))
    a = ap.parse_args()

    xtr, atr, phtr, eptr = load("train", a.hist)
    xva, ava, phva, epva = load(a.val_split, a.hist)
    mean = xtr.mean(0).astype(np.float32)
    std = (xtr.std(0) + 1e-6).astype(np.float32)          # 与 train_act_lift.py 完全一致
    ntr = (xtr - mean) / std
    nva = (xva - mean) / std

    # ---- M1 归一化条件数 ----
    absmax = np.abs(ntr).max(0)
    m1 = {"n_dims": int(xtr.shape[1]),
          "std_min": float(std.min()), "std_max": float(std.max()),
          "std_ratio_max_over_min": float(std.max() / max(std.min(), 1e-12)),
          "dims_std_below_1e-3": [int(i) for i in np.where(xtr.std(0) < 1e-3)[0]],
          "normalized_absmax_top10": [{"dim": int(i), "absmax": float(absmax[i]),
                                       "raw_std": float(xtr.std(0)[i])}
                                      for i in np.argsort(-absmax)[:10]],
          "n_dims_absmax_over_100": int((absmax > 100).sum()),
          "n_dims_absmax_over_1000": int((absmax > 1000).sum())}

    # ---- M2 kNN 条件方差上界 ----
    cv, ceil_r2, nn_d, idx = knn_cond_var(ntr, atr, nva, ava, a.k)
    mask_tr = ~np.isin(phva, list(IDLE_PHASES))
    cv_t, ceil_t, _, _ = knn_cond_var(ntr, atr, nva[mask_tr], ava[mask_tr], a.k)
    achieved = {"A1_minibatch_dz_r2": 0.158, "A1_task_rel_dz_r2": 0.420,
                "A0_fullbatch40_dz_r2": 0.542, "A3_trunc_dz_r2": -5.010}
    m2 = {"k": a.k, "n_train": int(len(ntr)), "n_val": int(len(nva)),
          "per_dim": {DIM_NAMES[j]: {"total_var": float(ava[:, j].var()),
                                     "cond_var": float(cv[j]),
                                     "ceiling_r2": (None if np.isnan(ceil_r2[j]) else float(ceil_r2[j])),
                                     "ceiling_r2_task_relevant": (None if np.isnan(ceil_t[j]) else float(ceil_t[j]))}
                      for j in range(7)},
          "median_nn_dist": float(np.median(nn_d)), "p95_nn_dist": float(np.percentile(nn_d, 95)),
          "achieved_for_reference": achieved}

    # ---- M3 别名取证（在 train 内部找近邻对，保证是训练时真实存在的冲突）----
    d = pdist2(ntr, ntr)
    np.fill_diagonal(d, np.inf)
    same_ep = eptr[:, None] == eptr[None, :]
    d = np.where(same_ep, np.inf, d)                       # 只看跨 episode 的别名，排除时间相邻帧
    j = d.argmin(1); nd = d[np.arange(len(d)), j] ** 0.5
    ddz = np.abs(atr[:, 2] - atr[j, 2])
    sel = np.where((nd < a.alias_dist) & (ddz > a.alias_ddz))[0][:20]
    m3 = {"n_pairs_checked": int(len(nd)),
          "n_pairs_dist_below_thr": int((nd < a.alias_dist).sum()),
          "n_aliasing_pairs": int(((nd < a.alias_dist) & (ddz > a.alias_ddz)).sum()),
          "thresholds": {"obs_dist": a.alias_dist, "abs_ddz": a.alias_ddz},
          "examples": [{"i": int(p), "j": int(j[p]), "obs_dist": round(float(nd[p]), 5),
                        "phase_i": phtr[p], "phase_j": phtr[j[p]],
                        "dz_i": round(float(atr[p, 2]), 3), "dz_j": round(float(atr[j[p], 2]), 3),
                        "grip_i": round(float(atr[p, 6]), 3), "grip_j": round(float(atr[j[p], 6]), 3)}
                       for p in sel]}

    # ---- 按 phase 分层的 teacher 动作分布（看 dz 在哪些模式里冲突）----
    by_phase = {}
    for p in sorted(set(phtr.tolist())):
        m = phtr == p
        by_phase[p] = {"n": int(m.sum()),
                       "dz_mean": round(float(atr[m, 2].mean()), 4),
                       "dz_std": round(float(atr[m, 2].std()), 4),
                       "grip_mean": round(float(atr[m, 6].mean()), 4)}

    res = {"hist": a.hist, "val_split": a.val_split, "measurements": {"M1_normalization_conditioning": m1,
                                            "M2_knn_bc_ceiling": m2,
                                            "M3_aliasing_evidence": m3},
           "teacher_action_by_phase": by_phase,
           "data": str(DATA), "n_train_frames": int(len(xtr)), "n_val_frames": int(len(xva))}
    outp = Path(a.out.replace("{k}", str(a.hist)))
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")

    print("== M1 归一化条件数 ==")
    print("  std 范围 %.2e ~ %.2e（比值 %.1e）；std<1e-3 的维: %s"
          % (m1["std_min"], m1["std_max"], m1["std_ratio_max_over_min"], m1["dims_std_below_1e-3"]))
    print("  归一化后 |x|>100 的维数 %d，>1000 的维数 %d" % (m1["n_dims_absmax_over_100"], m1["n_dims_absmax_over_1000"]))
    print("  Top5 放大维: %s" % ", ".join("d%d(|x|max=%.0f,std=%.1e)" % (t["dim"], t["absmax"], t["raw_std"])
                                          for t in m1["normalized_absmax_top10"][:5]))
    print("== M2 BC 的 r² 上界（k=%d，确定性回归器不可逾越）==" % a.k)
    print("  %-6s %10s %10s %10s %10s" % ("dim", "total_var", "cond_var", "ceil_r2", "ceil_r2_tr"))
    for nm in DIM_NAMES:
        e = m2["per_dim"][nm]
        f = lambda v: ("   na    " if v is None else "%10.3f" % v)
        print("  %-6s %10.5f %10.5f %s %s" % (nm, e["total_var"], e["cond_var"], f(e["ceiling_r2"]), f(e["ceiling_r2_task_relevant"])))
    print("  近邻距离中位数 %.4f / p95 %.4f" % (m2["median_nn_dist"], m2["p95_nn_dist"]))
    print("== M3 别名取证 ==")
    print("  跨 episode 近邻里 obs 距离<%.3f 的对: %d，其中 |Δdz|>%.2f 的: %d"
          % (a.alias_dist, m3["n_pairs_dist_below_thr"], a.alias_ddz, m3["n_aliasing_pairs"]))
    for e in m3["examples"][:8]:
        print("    dist=%.4f  %s(dz=%+.2f,grip=%+.2f)  <->  %s(dz=%+.2f,grip=%+.2f)"
              % (e["obs_dist"], e["phase_i"], e["dz_i"], e["grip_i"], e["phase_j"], e["dz_j"], e["grip_j"]))
    print("== teacher 动作按 phase ==")
    for p, e in by_phase.items():
        print("  %-9s n=%5d dz_mean=%+.3f dz_std=%.3f grip_mean=%+.3f" % (p, e["n"], e["dz_mean"], e["dz_std"], e["grip_mean"]))
    print("写出:", outp)


if __name__ == "__main__":
    main()
