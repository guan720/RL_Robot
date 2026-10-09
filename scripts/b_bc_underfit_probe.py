#!/usr/bin/env python3
"""B 支线：判定「learned ACT 0/20」是欠拟合/数据分布伪影，还是真实能力上限。

离线实验，不需要 robosuite。只读 runs/infra/lerobot_act_lift_state_overfit/ 的已导出
teacher 数据，只写 runs/infra/b_bc_retrain/。不修改 A 的 checkpoint、数据或训练脚本。

所有臂共用同一 train/validation 划分、同一 obs 布局、同一 K=4、同一 lr。
  A0_fullbatch40  复现 scripts/train_act_lift.py 的训练循环（每 epoch 一次全批量更新 = 40 步梯度）
  A1_minibatch    同架构，改 minibatch（约 5600 步梯度）
  A2_deadzero     minibatch + teacher 恒零动作维（droll/dpitch/dyaw）输出强制置 0
  A3_trunc        A2 + 训练集丢弃 phase==done 的空转帧
  A4_trunc_w      A3 + 按 phase 反频率加权损失

评测同时报「全帧」和「任务相关帧（phase != done/hold）」两套指标：
后者才决定 approach/descend/lift 能否成功，全帧指标被 73% 的空转帧主导。
"""
from __future__ import annotations
import argparse, glob, itertools, json
from pathlib import Path
import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "runs/infra/lerobot_act_lift_state_overfit/data"
OUT = ROOT / "runs/infra/b_bc_retrain"
DIM_NAMES = ["dx", "dy", "dz", "droll", "dpitch", "dyaw", "grip"]
OSC_TRANS, OSC_ROT = 0.05, 0.5           # robosuite OSC_POSE 默认缩放
IDLE_PHASES = {"done", "hold"}           # 任务已完成、teacher 输出零动作的阶段（仅用于评测分层）
DROP_PHASES = {"done"}                   # 训练可丢弃的纯空转帧；hold 必须保留，否则抬起后会预测开爪掉块


class ChunkPolicy(nn.Module):
    def __init__(self, obs_dim, chunk=4):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(obs_dim, 256), nn.ReLU(),
                                 nn.Linear(256, 256), nn.ReLU(),
                                 nn.Linear(256, chunk * 7), nn.Tanh())
        self.chunk = chunk

    def forward(self, x):
        return self.net(x).view(-1, self.chunk, 7)


def load_split(split):
    out = []
    for f in sorted(glob.glob(str(DATA / "episode_*.npz"))):
        z = np.load(f)
        if str(z["split"]) == split:
            out.append(z)
    return out


def build(zs, hist):
    """返回 (X, Y, phase_of_chunk_first_frame)。history 只用当前及过去帧，首帧复制填充。"""
    X, Y, PH = [], [], []
    for z in zs:
        s, c, ph = z["observation_state"], z["action_chunk"], z["phase"]
        for t in range(len(c)):
            X.append(np.concatenate([s[max(0, t - (hist - 1) + k)] for k in range(hist)]).astype(np.float32))
            Y.append(c[t]); PH.append(str(ph[t]))
    return np.stack(X), np.stack(Y).astype(np.float32), np.array(PH)


def phase_weights(phases):
    cnt = {p: max(int((phases == p).sum()), 1) for p in set(phases.tolist())}
    n = len(phases)
    w = {p: (n / len(cnt)) / c for p, c in cnt.items()}
    scale = max(w.values())
    return np.array([w[p] / scale for p in phases], dtype=np.float32), cnt


def fit(arm, sched, Xtr, Ytr, Ptr, Xva, Yva, hist, epochs, bs, lr, grad_budget=0, seed=0):
    torch.manual_seed(seed); np.random.seed(seed)
    mean = Xtr.mean(0).astype(np.float32)
    std = Xtr.std(0).astype(np.float32) + np.float32(1e-6)
    dead = [i for i in range(7) if np.abs(Ytr[:, :, i]).max() < 1e-9]
    hard_zero = arm in ("A2_deadzero", "A3_trunc", "A4_trunc_w", "A5_all_w")

    sel = np.ones(len(Xtr), dtype=bool)
    if arm in ("A3_trunc", "A4_trunc_w"):
        sel = ~np.isin(Ptr, list(DROP_PHASES))
    Xf, Yf, Pf = Xtr[sel], Ytr[sel], Ptr[sel]

    sw = np.ones(len(Xf), dtype=np.float32)
    if arm in ("A4_trunc_w", "A5_all_w"):
        raw, _ = phase_weights(Pf)
        sw = raw / raw.mean()

    model = ChunkPolicy(Xtr.shape[1], 4)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    fx = torch.tensor((Xf - mean) / std); fy = torch.tensor(Yf); fw = torch.tensor(sw)
    tx = torch.tensor((Xtr - mean) / std)
    vx = torch.tensor((Xva - mean) / std)

    def loss_fn(pred, target, w):
        per = ((pred - target) ** 2).mean(dim=(1, 2))      # 每样本 MSE
        return (per * w).mean()

    steps = 0
    if sched == "fullbatch":
        for _ in range(epochs):
            model.train(); opt.zero_grad()
            loss_fn(model(fx), fy, fw).backward(); opt.step(); steps += 1
    else:
        n = len(fx); g = torch.Generator().manual_seed(seed)
        bpe = max(1, -(-n // min(bs, n)))
        ep = max(1, -(-grad_budget // bpe)) if grad_budget else epochs
        for _ in range(ep):
            model.train()
            if grad_budget and steps >= grad_budget:
                break
            for idx in torch.randperm(n, generator=g).split(bs):
                opt.zero_grad(); loss_fn(model(fx[idx]), fy[idx], fw[idx]).backward(); opt.step(); steps += 1
                if grad_budget and steps >= grad_budget:
                    break

    model.eval()
    with torch.no_grad():
        pva = model(vx).numpy(); ptr = model(tx).numpy()
    if hard_zero:
        for i in dead:
            pva[:, :, i] = 0.0; ptr[:, :, i] = 0.0
    return dict(model=model, mean=mean, std=std, steps=steps, dead=dead,
                ptr=ptr, pva=pva, train_kept=int(sel.sum()), train_total=len(Xtr))


def metrics(pred, true, phases, label):
    keep = ~np.isin(phases, list(IDLE_PHASES))
    out = {}
    for scope, m in (("all", np.ones(len(pred), bool)), ("task_relevant", keep)):
        blk = {"n_frames": int(m.sum())}
        pd = {}
        for i, nm in enumerate(DIM_NAMES):
            e = float(((pred[m, :, i] - true[m, :, i]) ** 2).mean())
            v = float(true[m, :, i].var())
            scale = OSC_ROT if nm in ("droll", "dpitch", "dyaw") else OSC_TRANS
            pd[nm] = {"val_mse": e, "r2": (1 - e / v) if v > 1e-12 else None,
                      "rmse_physical": e ** 0.5 * scale,
                      "bias": float(pred[m, :, i].mean() - true[m, :, i].mean()),
                      "std_ratio": float(pred[m, :, i].std() / max(true[m, :, i].std(), 1e-9))}
        blk["per_dim"] = pd
        blk["mse"] = float(((pred[m] - true[m]) ** 2).mean())
        # 关键帧上的方向正确率：teacher 要求明显下降(dz<-0.05)/上升(dz>0.05)/开爪(grip<-0.5) 时
        down = true[m, :, 2] < -0.05
        up = true[m, :, 2] > 0.05
        open_g = true[m, :, 6] < -0.5
        blk["critical"] = {
            "teacher_descend_frames": int(down.sum()),
            "descend_sign_acc": float((np.sign(pred[m, :, 2][down]) < 0).mean()) if down.any() else None,
            "descend_mean_pred": float(pred[m, :, 2][down].mean()) if down.any() else None,
            "teacher_lift_frames": int(up.sum()),
            "lift_sign_acc": float((np.sign(pred[m, :, 2][up]) > 0).mean()) if up.any() else None,
            "lift_mean_pred": float(pred[m, :, 2][up].mean()) if up.any() else None,
            "teacher_open_frames": int(open_g.sum()),
            "open_sign_acc": float((np.sign(pred[m, :, 6][open_g]) < 0).mean()) if open_g.any() else None,
        }
        out[scope] = blk
    return out


def report(name, r, Ytr, Yva, Pva, allres):
    m = metrics(r["pva"], Yva, Pva, name)
    allres["arms"][name] = {"grad_steps": r["steps"], "dead_action_dims": r["dead"],
                            "train_frames_kept": r["train_kept"], "train_frames_total": r["train_total"],
                            "train_mse_all": float(((r["ptr"] - Ytr) ** 2).mean()),
                            "val_mse_all": float(((r["pva"] - Yva) ** 2).mean()),
                            "metrics": m}
    ta = m["all"]; tr = m["task_relevant"]
    print(f"\n--- {name} ---  grad_steps={r['steps']}  train kept {r['train_kept']}/{r['train_total']}")
    print(f"  val_mse  all={ta['mse']:.6f}   task_relevant={tr['mse']:.6f}")
    print("  %-7s | %-32s | %-32s" % ("dim", "ALL  R2 / rmse_phys / bias", "TASK-RELEVANT  R2 / rmse_phys / bias"))
    for nm in DIM_NAMES:
        a, b = ta["per_dim"][nm], tr["per_dim"][nm]
        f = lambda d: ("%7s %10.2e %+9.4f" % ("nan" if d["r2"] is None else f"{d['r2']:.3f}",
                                              d["rmse_physical"], d["bias"]))
        print("  %-7s | %s | %s" % (nm, f(a), f(b)))
    c = tr["critical"]
    print("  critical frames (task-relevant): descend n=%d sign_acc=%s mean_pred=%s | lift n=%d sign_acc=%s | open n=%d sign_acc=%s"
          % (c["teacher_descend_frames"], _pct(c["descend_sign_acc"]), _f3(c["descend_mean_pred"]),
             c["teacher_lift_frames"], _pct(c["lift_sign_acc"]), c["teacher_open_frames"], _pct(c["open_sign_acc"])))


def _pct(x):
    return "n/a" if x is None else f"{x*100:.1f}%"


def _f3(x):
    return "n/a" if x is None else f"{x:+.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", type=int, default=1)
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--grad-budget", type=int, default=5600,
                    help="minibatch 臂统一的梯度步预算，使截断/加权臂与全量臂可比")
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tr, va = load_split("train"), load_split("validation")
    Xtr, Ytr, Ptr = build(tr, a.history)
    Xva, Yva, Pva = build(va, a.history)
    ph_cnt = {p: len(list(g)) for p, g in itertools.groupby(Ptr.tolist())}
    uniq = {p: int((Ptr == p).sum()) for p in sorted(set(Ptr.tolist()))}
    print(f"history={a.history}  train chunks {Xtr.shape}  val chunks {Xva.shape}")
    print(f"train phase frame counts: {uniq}  -> idle(done+hold) = "
          f"{(uniq.get('done',0)+uniq.get('hold',0))/len(Ptr)*100:.1f}%")
    allres = {"history": a.history, "lr": a.lr, "batch_size": a.batch_size, "epochs": a.epochs,
              "train_phase_counts": uniq, "grad_budget": a.grad_budget, "idle_frame_frac":
                  (uniq.get("done", 0) + uniq.get("hold", 0)) / len(Ptr), "arms": {}}
    for name in ["A0_fullbatch40", "A1_minibatch", "A2_deadzero", "A3_trunc", "A4_trunc_w", "A5_all_w"]:
        sched = "fullbatch" if name.startswith("A0") else "minibatch"
        r = fit(name, sched, Xtr, Ytr, Ptr, Xva, Yva, a.history,
                epochs=(40 if sched == "fullbatch" else a.epochs),
                bs=(10 ** 9 if sched == "fullbatch" else a.batch_size),
                lr=a.lr, grad_budget=(0 if sched == "fullbatch" else a.grad_budget), seed=a.seed)
        report(name, r, Ytr, Yva, Pva, allres)
    p = OUT / f"bc_underfit_probe_hist{a.history}_seed{a.seed}.json"
    p.write_text(json.dumps(allres, indent=2))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
