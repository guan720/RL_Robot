#!/usr/bin/env python3
"""B 线可辨识性探针：dz 学不好，是「观测里没信息」还是「损失函数不 care」？

背景（离线欠拟合探针的六个臂，runs/infra/b_bc_retrain/bc_underfit_probe_hist1_seed0.json）：
  A0_fullbatch40   dz r²=+0.542  bias=+0.019   grip r²=0.381   val_mse_all=0.02590
  A1_minibatch     dz r²=+0.158  bias=+0.111   grip r²=0.998   val_mse_all=0.00700
  A3_trunc         dz r²=-5.010  bias=+0.448   grip r²=0.997   val_mse_all=0.04826
  hist=4 的 A1     dz r²=-2.517  bias=+0.259   grip r²=0.999   val_mse_all=0.02834

注意 A0→A1：**总 val MSE 从 0.0259 降到 0.0070（好 3.7 倍），dz r² 却从 0.542 掉到 0.158。**
梯度预算翻 140 倍让 dz 变差，这不是欠拟合。teacher 逐 phase 的方差分解给出解释：
  grip total_var = 0.24684，dz total_var = 0.06062 —— grip 的方差是 dz 的 4.1 倍，
  而 7 维等权 MSE 的梯度几乎全部去拟合 grip；dz 有 90.9% 的帧恒等于 0
  （grasp 600 + hold 720 + done 5159 = 6479/7128），预测 0 就能拿到 r²=0。
  闭环里 dz 决定「下降够不够 / 何时抬升」，dz 系统性正偏 +0.111 = 手臂悬得偏高
  = 夹爪在对齐前闭合 = 漏抓（15/20 局 phase_at_end=approach、max_rise≈0）
  或夹到边角把方块弹射出去（3/20 局 success_step=29~33、max_rise=0.376~0.634）。

所以在花任何闭环算力之前，必须先回答：**dz 所需的信息在观测里吗？**
  T1 6 类 phase 分类器：teacher 的内部模式（approach/descend/grasp/lift/hold/done）
     能否从 obs 复原。lift 与 hold/grasp/done 的 grip 都是 +1，只有 dz 不同
     （lift dz=+1，其余 dz≈0），所以 lift 的召回率就是「该抬升时能不能知道要抬升」的上界。
  T2 二分类 lift vs 非 lift，只用 grip=+1 的帧（即夹爪已闭合的子集，最难的别名场景）。
  T3 二分类 descend-or-approach（dz<0）vs 其余，只用 grip=-1 的帧。
  T4 逐维损失加权扫描：唯一变量是 dz 的损失权重 w_dz，其余与 A1 完全一致
     （同架构、同归一化、同 5600 步预算、同 batch/lr）。看 dz r²/bias 能否被拉起来，
     且 grip/dx/dy 是否被牺牲。

离线，只读 runs/infra/lerobot_act_lift_state_overfit/data/，不碰 robosuite，
不碰 A/C 的文件，只写 runs/infra/b_observability/。
"""
from __future__ import annotations
import argparse, glob, json
from pathlib import Path
import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "runs/infra/lerobot_act_lift_state_overfit/data"
OUT = ROOT / "runs/infra/b_observability"
DIM_NAMES = ["dx", "dy", "dz", "droll", "dpitch", "dyaw", "grip"]
PHASES = ["approach", "descend", "grasp", "lift", "hold", "done"]
IDLE_PHASES = {"done", "hold"}
OSC_TRANS = 0.05


class ChunkPolicy(nn.Module):
    """与 scripts/train_act_lift.py 的 ChunkPolicy **缺省路径下逐层一致**（不 import，避免拉起 robosuite）。

    **内容锚，故意不写行号**（行号锚在别人改文件时会静默失效 ⇒ 变成假证据；
    命中行号由 `scripts/b_selfcheck_source_anchors.py` 现场搜索回显）：
      · `class ChunkPolicy`
      · `def __init__(self, obs_dim, chunk=4, *, goals=None)`
      · `nn.Linear(self.obs_dim+self.goal_dim,256)`

    上游 0929 起签名变成 `__init__(self, obs_dim, chunk=4, *, goals=None)`（T17 A 侧改动，
    `docs/a_handoff_to_b_anchor_shift_20260929.md` §1 第 3 行）：goal 相关参数一律**关键字、缺省关闭**，
    `goals=None` ⇒ `goal_dim=0` ⇒ 第一层就是 `Linear(obs_dim, 256)`，与本类**键序/形状/权重逐项相同**。
    这不是「我读代码觉得一样」：A 的 `scripts/a_selfcheck_goal_conditioning_t17.py` G5/G6 把
    **git HEAD（改动前）**的实现动态载入做对照实测过（产物 `runs/infra/a_t17_goal_conditioning.json`），
    既有 0924 ckpt 仍 `strict=True` 加载、`net.0.weight == (256, 60)`、预测逐元素相同。
    上游 `forward(x, goal=None)` 不传 goal 时同样逐元素不变 ⇒ 本类的 `forward(x)` 仍是合法对照。
    """
    def __init__(self, obs_dim, chunk=4):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(obs_dim, 256), nn.ReLU(), nn.Linear(256, 256), nn.ReLU(),
                                 nn.Linear(256, chunk * 7), nn.Tanh())
        self.chunk = chunk

    def forward(self, x):
        return self.net(x).view(-1, self.chunk, 7)


class Clf(nn.Module):
    def __init__(self, d, k):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d, 256), nn.ReLU(), nn.Linear(256, 256), nn.ReLU(),
                                 nn.Linear(256, k))

    def forward(self, x):
        return self.net(x)


def load(split, hist):
    """与 scripts/b_bc_underfit_probe.py 同一构造：只用当前及过去帧，首帧复制填充。"""
    X, C, PH = [], [], []
    for f in sorted(glob.glob(str(DATA / "episode_*.npz"))):
        z = np.load(f)
        if str(z["split"]) != split:
            continue
        s, c, ph = z["observation_state"], z["action_chunk"], z["phase"]
        for t in range(len(c)):
            X.append(np.concatenate([s[max(0, t - (hist - 1) + k)] for k in range(hist)]).astype(np.float32))
            C.append(c[t].astype(np.float32))
            PH.append(str(ph[t]))
    return np.asarray(X), np.asarray(C), np.asarray(PH)


def fit_clf(xtr, ytr, xva, yva, k, steps=3000, bs=256, lr=3e-4, seed=0):
    """类别平衡采样 + 交叉熵。返回 (acc, per_class_recall, confusion, prob)。"""
    torch.manual_seed(seed)
    m = Clf(xtr.shape[1], k)
    opt = torch.optim.Adam(m.parameters(), lr=lr)
    X = torch.tensor(xtr); Y = torch.tensor(ytr)
    cls, cnt = np.unique(ytr, return_counts=True)
    w = torch.tensor((cnt.sum() / (k * np.maximum(cnt, 1))).astype(np.float32))
    sampler_w = w[Y]
    g = torch.Generator().manual_seed(seed)
    for st in range(steps):
        idx = torch.multinomial(sampler_w, min(bs, len(Y)), replacement=True, generator=g)
        loss = nn.functional.cross_entropy(m(X[idx]), Y[idx])
        opt.zero_grad(); loss.backward(); opt.step()
    m.eval()
    with torch.no_grad():
        prob = torch.softmax(m(torch.tensor(xva)), 1).numpy()
    pred = prob.argmax(1)
    conf = np.zeros((k, k), int)
    for t, p in zip(yva, pred):
        conf[t, p] += 1
    rec = {int(c): (float(conf[c, c] / max(1, conf[c].sum())) if c in set(yva.tolist()) else None) for c in range(k)}
    return float((pred == yva).mean()), rec, conf.tolist(), prob


def train_arm(xtr, ctr_full, xva, cva_full, hist, dim_w, steps, bs, lr, seed):
    """ctr_full/cva_full 是完整 chunk (N,4,7)，与 A1 的训练目标一致；指标只取首步。"""
    """唯一变量是 dim_w（逐维损失权重）；其余与 A1_minibatch 完全一致。"""
    torch.manual_seed(seed); np.random.seed(seed)
    mean = xtr.mean(0).astype(np.float32); std = (xtr.std(0) + 1e-6).astype(np.float32)
    model = ChunkPolicy(xtr.shape[1], 4)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    tx = torch.tensor((xtr - mean) / std); ty = torch.tensor(ctr_full)
    vx = torch.tensor((xva - mean) / std); vy = torch.tensor(cva_full)
    W = torch.tensor(np.asarray(dim_w, dtype=np.float32))
    n = len(tx); g = torch.Generator().manual_seed(seed); step = 0
    while step < steps:
        model.train()
        for idx in torch.randperm(n, generator=g).split(min(bs, n)):
            loss = (((model(tx[idx]) - ty[idx]) ** 2) * W).mean()
            opt.zero_grad(); loss.backward(); opt.step(); step += 1
            if step >= steps:
                break
    model.eval()
    with torch.no_grad():
        pv = model(vx).numpy(); yv = vy.numpy()
    p0, y0 = pv[:, 0, :], yv[:, 0, :]
    task = ~np.isin(phva_global, list(IDLE_PHASES))
    per = {}
    for j, nm in enumerate(DIM_NAMES):
        tv = y0[:, j].var()
        e = {"r2": (None if tv < 1e-12 else float(1 - ((p0[:, j] - y0[:, j]) ** 2).mean() / tv)),
             "bias": float((p0[:, j] - y0[:, j]).mean()),
             "r2_task_relevant": (None if tv < 1e-12 else float(
                 1 - ((p0[task, j] - y0[task, j]) ** 2).mean() / max(y0[task, j].var(), 1e-12)))}
        per[nm] = e
    # 闭环最关心的两个诊断量
    desc = phva_global == "descend"; appr = phva_global == "approach"
    dn = phva_global == "done"; lf = phva_global == "lift"
    diag = {
        "descend_dz_sign_acc": float((p0[desc, 2] < 0).mean()) if desc.any() else None,
        "descend_dz_mean_pred": float(p0[desc, 2].mean()) if desc.any() else None,
        "descend_dz_mean_teacher": float(y0[desc, 2].mean()) if desc.any() else None,
        "lift_dz_sign_acc": float((p0[lf, 2] > 0).mean()) if lf.any() else None,
        "lift_dz_mean_pred": float(p0[lf, 2].mean()) if lf.any() else None,
        # 空转帧上的 dz 泄漏：teacher 恒 0，预测越正 -> 闭环里手臂无故上飘
        "done_dz_mean_pred": float(p0[dn, 2].mean()) if dn.any() else None,
        "done_dz_absmax_pred": float(np.abs(p0[dn, 2]).max()) if dn.any() else None,
        "done_dz_rmse_physical_m": (float(np.sqrt((p0[dn, 2] ** 2).mean()) * OSC_TRANS) if dn.any() else None),
        "grip_open_sign_acc": float((p0[~(phva_global == "approach") | True, 6] < 0).mean()),
    }
    va = float(((pv - vy.numpy()) ** 2).mean())
    return {"val_mse_all": va, "per_dim": per, "closed_loop_diag": diag,
            "dim_weights": list(map(float, dim_w))}


phva_global = None


def main():
    global phva_global
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", type=int, default=1)
    ap.add_argument("--grad-steps", type=int, default=5600)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--clf-steps", type=int, default=3000)
    ap.add_argument("--weights", default="1,3,10,30", help="dz 损失权重扫描（逗号分隔）")
    ap.add_argument("--skip-sweep", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    xtr, ctr, phtr = load("train", a.hist)
    xva, cva, phva = load("validation", a.hist)
    phva_global = phva
    mean = xtr.mean(0).astype(np.float32); std = (xtr.std(0) + 1e-6).astype(np.float32)
    ntr = (xtr - mean) / std; nva = (xva - mean) / std
    ytr = ctr[:, 0, :]; yva = cva[:, 0, :]
    res = {"hist": a.hist, "grad_steps": a.grad_steps, "n_train": int(len(ntr)), "n_val": int(len(nva)),
           "train_phase_counts": {p: int((phtr == p).sum()) for p in PHASES}}

    # ---- T1 六类 phase 可辨识性 ----
    ytr_c = np.array([PHASES.index(p) for p in phtr]); yva_c = np.array([PHASES.index(p) for p in phva])
    acc, rec, conf, _ = fit_clf(ntr, ytr_c, nva, yva_c, len(PHASES), steps=a.clf_steps, seed=a.seed)
    res["T1_phase_identifiability"] = {
        "balanced_accuracy": acc, "per_class_recall": {PHASES[k]: v for k, v in rec.items()},
        "confusion_rows_true": PHASES, "confusion": conf,
        "note": "lift 的召回率 = 「夹爪已闭合时能否知道该抬升」的上界；lift 与 hold/grasp/done 的 grip 同为 +1，只有 dz 不同"}

    # ---- T2 lift vs 非 lift，仅 grip=+1 子集 ----
    mtr = ytr[:, 6] > 0; mva = yva[:, 6] > 0
    b_tr = (ytr[mtr, 2] > 0.5).astype(np.int64); b_va = (yva[mva, 2] > 0.5).astype(np.int64)
    if b_tr.sum() > 0 and (1 - b_tr).sum() > 0:
        acc2, rec2, conf2, prob2 = fit_clf(ntr[mtr], b_tr, nva[mva], b_va, 2, steps=a.clf_steps, seed=a.seed)
        auc = float(np.mean([prob2[i, 1] > prob2[j, 1] for i in np.where(b_va == 1)[0][:60]
                             for j in np.where(b_va == 0)[0][:200]]) or 0.0)
        res["T2_lift_vs_rest_gripclosed"] = {"n_train": int(mtr.sum()), "n_val": int(mva.sum()),
                                             "n_val_lift": int(b_va.sum()), "accuracy": acc2,
                                             "recall_lift": rec2.get(1), "recall_nonlift": rec2.get(0),
                                             "approx_auc": auc, "confusion": conf2}
    else:
        res["T2_lift_vs_rest_gripclosed"] = {"error": "grip=+1 子集里没有 lift 帧，无法测"}

    # ---- T3 dz<0（approach/descend）vs 其余，仅 grip=-1 子集 ----
    otr = ytr[:, 6] < 0; ova = yva[:, 6] < 0
    c_tr = (ytr[otr, 2] < -0.05).astype(np.int64); c_va = (yva[ova, 2] < -0.05).astype(np.int64)
    if c_tr.sum() > 0 and (1 - c_tr).sum() > 0:
        acc3, rec3, conf3, _ = fit_clf(ntr[otr], c_tr, nva[ova], c_va, 2, steps=a.clf_steps, seed=a.seed)
        res["T3_descend_vs_rest_gripopen"] = {"n_train": int(otr.sum()), "n_val": int(ova.sum()),
                                              "n_val_descend": int(c_va.sum()), "accuracy": acc3,
                                              "recall_descend": rec3.get(1), "recall_non": rec3.get(0),
                                              "confusion": conf3}
    else:
        res["T3_descend_vs_rest_gripopen"] = {"error": "grip=-1 子集不足"}

    outp = Path(a.out or OUT / ("identifiability_hist%d_seed%d.json" % (a.hist, a.seed)))
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")   # 先落盘 T1-T3，T4 崩了也不丢

    # ---- T4 逐维损失加权扫描（唯一变量 = dz 权重）----
    if not a.skip_sweep:
        res["T4_dz_loss_weight_sweep"] = {}
        base = [1.0] * 7
        for w in [1.0] + [float(x) for x in a.weights.split(",")]:
            dw = list(base); dw[2] = w
            key = ("A1_reproduce" if w == 1.0 else "w_dz=%g" % w)
            print("  训练 %s ..." % key, flush=True)
            res["T4_dz_loss_weight_sweep"][key] = train_arm(
                xtr, ctr, xva, cva, a.hist, dw, a.grad_steps, a.batch_size, a.lr, a.seed)

    outp.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")

    t1 = res["T1_phase_identifiability"]
    print("\n== T1 teacher 内部模式可辨识性（6 类 phase，平衡采样）==")
    print("  balanced acc = %.3f" % t1["balanced_accuracy"])
    for p in PHASES:
        print("    recall[%-8s] = %s" % (p, ("%.3f" % t1["per_class_recall"][p])
                                         if t1["per_class_recall"][p] is not None else "na"))
    print("  混淆矩阵（行=真 phase，列=预测）：")
    print("        " + " ".join("%7s" % p[:7] for p in PHASES))
    for i, p in enumerate(PHASES):
        print("    %-6s" % p[:6] + " ".join("%7d" % v for v in t1["confusion"][i]))
    for key in ("T2_lift_vs_rest_gripclosed", "T3_descend_vs_rest_gripopen"):
        r = res[key]
        print("\n== %s ==" % key)
        print("  " + json.dumps(r, ensure_ascii=False))
    if "T4_dz_loss_weight_sweep" in res:
        print("\n== T4 逐维损失加权扫描（唯一变量 = dz 权重）==")
        print("  %-14s %9s | %-28s | %-24s | %s" % ("arm", "val_all", "dz", "descend/lift dz", "done 帧 dz 泄漏"))
        for name, r in res["T4_dz_loss_weight_sweep"].items():
            dz = r["per_dim"]["dz"]; d = r["closed_loop_diag"]
            print("  %-14s %9.5f | r2=%.3f r2tr=%.3f b=%+.3f | desc_sign=%.3f(mean %+.2f) lift_sign=%.3f | "
                  "mean %+.3f rmse %.1fmm"
                  % (name, r["val_mse_all"], dz["r2"], dz["r2_task_relevant"], dz["bias"],
                     d["descend_dz_sign_acc"], d["descend_dz_mean_pred"], d["lift_dz_sign_acc"],
                     d["done_dz_mean_pred"], 1000 * d["done_dz_rmse_physical_m"]))
            print("  %-14s %9s | dx r2=%.3f  dy r2=%.3f  grip r2=%.3f" % ("", "", r["per_dim"]["dx"]["r2"],
                                                                           r["per_dim"]["dy"]["r2"],
                                                                           r["per_dim"]["grip"]["r2"]))
    print("\n写出:", outp)


if __name__ == "__main__":
    main()
