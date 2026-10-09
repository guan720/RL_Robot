#!/usr/bin/env python
"""档 9B · dz→末端升程 的**脉冲响应**测量（零 GPU）：给「末端高度保持」控制器定常数。

为什么需要：增补 1 的 v1 控制器（越界才 `dz=-min(1,KP*err)`）在 Z0b 可行性台上 **0/12 按住**
（`runs/_diag/s9_tax/z0b_feasibility.json`：15.22~21.30 cm 被压到 13.38~14.67，门是 ≤ cap+1.0 = 13.15）。
原因不是「没力气」，是**只在越界之后才反应**：`OSC_POSE` 的 dz 是速度级指令、响应有滞后
（本工具量出的脉冲响应 b1 > b0 ⇒ 峰值出现在**下一步**），所以带着上升速度撞天花板必然过冲。

v2 的做法 = **预测式节流**：把「本步命令 dz 之后、末端最终还会升到哪」预测出来，让预测终点 ≤ cap：
    Δz[t] ≈ Σ_j b_j · dz[t-j]      （j=0..L，b 由本工具在 400 局已录 npz 上最小二乘拟合）
    inflight = Σ_{j≥1} b_j · dz[t-j]     （已下发命令里还没兑现的部分）
    dz_allow = (cap - rise - inflight) / k ,  k = Σ_j b_j   （= 单位 dz 的「总升程/制动距离」）
    dz = min(dz_policy, dz_allow)         （只允许比策略更保守；headroom 大时 dz_allow>1 ⇒ 恒等放行）

⚠️ 全部输入都是**已落盘**的 TEST 400 局 npz（`runs/*_rev_test_rand20_k10*`，档 8/7H 的既有产物），
   不含任何本档新跑的读数；b、k 是**动力学常数**，不是从成功/失败率上挑出来的（坑 27/40/42 不适用）。

用法：`$MG_PY code/mg_s9b_gain.py [--selftest] [--out runs/_diag/s9_tax/dz_gain_400.json]`
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_eval_zlim import GRASP_THR, OPEN_THR, RELEASE_THR  # noqa: E402  单一真理源

RUNS = MG_ROOT / "runs"
BASES = ("s8c_seed2000", "s8d_seed4000", "s8d_seed5000", "s7h_seed11000", "s7h_seed12000")
REPS = ("", "_rep2", "_rep3", "_rep4")
DZ = 2
Z = 2
W = 7
LAGS = 3          # 拟合 b0..b3（更长尾在 L=6 上只把 k 抬 1.2%，见 --verbose）


def dirs() -> list[Path]:
    out = []
    for b in BASES:
        for r in REPS:
            d = RUNS / f"{b}_rev_test_rand20_k10{r}"
            if (d / "rollout_actions.npz").exists():
                out.append(d)
    return out


def carry_windows(w: np.ndarray) -> list[tuple[int, int]]:
    """逐段定位搬运窗 [t_grasp, t_release]（与 Z0b 台 `mg_zlim_replay.carry_window` 同一套阈值/语义）。

    一局里可能开合多次（抓空后又抓）⇒ 返回多段，不是只取第一段。
    """
    n = len(w)
    segs: list[tuple[int, int]] = []
    i = 0
    while i < n:
        while i < n and not (w[i] > OPEN_THR):          # 1) 等「张开过」
            i += 1
        if i >= n:
            break
        j = i
        while j < n and not (w[j] <= GRASP_THR):        # 2) 张开之后**首次**合到 ≤GRASP（吃掉闭合过渡值）
            j += 1
        if j >= n:
            break
        tg = j
        k = tg
        while k < n and not (w[k] > RELEASE_THR):       # 3) 之后首次张过 RELEASE = 释放
            k += 1
        tr = k if k < n else n - 1
        segs.append((tg, tr))
        i = max(tr, i + 1)      # 从释放处继续找下一段（释放段本身就是下一段的「张开」候选）
    return [(a, b) for a, b in segs if b > a]


def collect(lags: int = LAGS) -> tuple[np.ndarray, np.ndarray, int]:
    """搬运段内的 (dz 滞后向量, 下一步 Δeef_z[cm]) 样本。

    对齐（坑：`rollout_actions.npz` 的 `state` 行数 == 步数，**没有末态**）：
    `state[t]` = 下 `action[t]` **之前**的观测 ⇒ `Δz[t] = state[t+1].z - state[t].z` 是 `action[t]` 的后果，
    且 `t` 只能取到 `n-2`。跨局切片会把下一局的首态串进来 ⇒ 这里逐局切。
    """
    X: list[list[float]] = []
    Y: list[float] = []
    for d in dirs():
        z = np.load(d / "rollout_actions.npz")
        A, S, L = z["action"], z["state"], z["episode_lengths"]
        off = 0
        for n in L:
            n = int(n)
            a, s = A[off:off + n], S[off:off + n]
            if len(a) == n and len(s) == n and n > lags + 2:
                zc = s[:, Z].astype(np.float64) * 100.0
                for tg, tr in carry_windows(s[:, W].astype(np.float64)):
                    for t in range(tg, min(tr, n - 2) + 1):
                        row = [float(a[t - j, DZ]) if t - j >= 0 else 0.0 for j in range(lags + 1)]
                        X.append(row)
                        Y.append(float(zc[t + 1] - zc[t]))
            off += n
    return np.asarray(X, dtype=np.float64), np.asarray(Y, dtype=np.float64), len(dirs())


def fit(X: np.ndarray, Y: np.ndarray) -> dict:
    b, *_ = np.linalg.lstsq(X, Y, rcond=None)
    pred = X @ b
    ss = float(((Y - pred) ** 2).sum())
    st = float(((Y - Y.mean()) ** 2).sum())
    k = float(b.sum())
    out = {"b": [float(x) for x in b], "k": k, "tail": k - float(b[0]),
           "r2": 1.0 - ss / st if st > 0 else float("nan"),
           "resid_std_cm": float(np.sqrt(ss / max(1, len(Y)))), "n": int(len(Y))}
    # 制动保真比：模型对**负** dz 的预测 vs 实测（<1 ⇒ 真实制动比模型弱 ⇒ 控制器要留裕度）
    neg = X[:, 0] < -0.05
    if neg.sum() > 50:
        out["brake_fidelity"] = float(Y[neg].mean() / pred[neg].mean())
        out["n_neg"] = int(neg.sum())
    # 上升保真比：模型对**正** dz 的预测 vs 实测（>1 ⇒ 真实上升比模型猛 ⇒ 同样要留裕度）
    pos = X[:, 0] > 0.05
    if pos.sum() > 50:
        out["accel_fidelity"] = float(Y[pos].mean() / pred[pos].mean())
        out["n_pos"] = int(pos.sum())
    return out


def design(g: dict) -> dict:
    """把测量结果翻成 v2 控制器常数（**safety 由公式定，不许从 Z0b 成败反推**）。

    v2 控制律（终点预测式节流）：
        inflight = Σ_{j≥1} b_j·dz_exec[t-j]        已下发但还没兑现的升程
        dz_allow = (cap - rise - safety·inflight) / (safety·k),  k = Σ_j b_j
        dz_exec  = clip(min(dz_policy, dz_allow), -1, 1)
    safety 的两个来源（都是同一批 400 局 npz 上量出来的**保真比**，与成败无关）：
        * 上升保真比 f_pos = 实测/模型（>1 ⇒ 真实上升更猛 ⇒ 要更早节流）
        * 制动保真比 f_brk = 实测/模型（<1 ⇒ 真实制动更弱 ⇒ 越界后压不回来 ⇒ 要更早节流）
        safety = max(f_pos, 1/f_brk)  ≥ 1 ⇒ k_eff = safety·k ⇒ 恒不比 v1 激进。
    """
    f_pos = g.get("accel_fidelity", 1.0)
    f_brk = g.get("brake_fidelity", 1.0)
    safety = max(f_pos, 1.0 / f_brk if f_brk > 0 else 1.0, 1.0)
    return {"k": g["k"], "b": g["b"], "safety": safety, "k_eff": g["k"] * safety,
            "accel_fidelity": f_pos, "brake_fidelity": f_brk,
            "note": ("b1>b0 ⇒ 响应峰值在下一步；k = 单位 dz 脉冲的总升程 = 节流尺度；"
                     f"safety = max(f_pos={f_pos:.3f}, 1/f_brk={1.0/f_brk if f_brk > 0 else float('nan'):.3f}) = {safety:.3f}")}


def report(out_json: Path, verbose: bool) -> int:
    X, Y, nd = collect()
    if len(X) < 500:
        print(f"[gain] 🚫 搬运段样本只有 {len(X)} 条（<{500}）⇒ 常数不可信，拒绝落盘", file=sys.stderr)
        return 3
    g = fit(X, Y)
    d = design(g)
    payload = {"tool": "mg_s9b_gain.py", "dirs": nd, "lags": LAGS, "fit": g, "design": d,
               "thresholds": {"open": OPEN_THR, "grasp": GRASP_THR, "release": RELEASE_THR},
               "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if verbose:
        for lg in (2, 4, 6):
            Xv, Yv, _ = collect(lg)
            gv = fit(Xv, Yv)
            payload.setdefault("lag_sweep", []).append({"lags": lg, "k": gv["k"], "r2": gv["r2"], "n": gv["n"]})
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"[gain] 搬运段样本 {g['n']} 条（{nd} 个 npz）；b={np.round(g['b'], 4).tolist()}")
    print(f"[gain] k = Σb = {g['k']:.4f} cm/单位dz（尾 = {g['tail']:.4f}）；R² = {g['r2']:.4f}；残差 σ = {g['resid_std_cm']:.3f} cm")
    print(f"[gain] 制动保真比（负 dz：实测/模型）= {g.get('brake_fidelity', float('nan')):.3f}（n={g.get('n_neg', 0)}）")
    print(f"[gain] v2 设计常数：dz_allow = (cap - rise - inflight) / k_eff，k_eff = {d['k_eff']:.4f}")
    print(f"[gain] 落盘 -> {out_json}")
    return 0


def selftest() -> int:
    fails: list[str] = []
    total = [0]

    def ck(name: str, cond: bool) -> None:
        total[0] += 1
        if not cond:
            fails.append(name)

    w = np.array([0.0417] * 4 + [0.079] * 3 + [0.050] * 6 + [0.079] * 3 + [0.050] * 5 + [0.079] * 2)
    segs = carry_windows(w)
    ck("w1 定位到两段搬运窗（开→合→释放→再开→再合）", segs == [(7, 13), (16, 21)])
    ck("w2 复位开口 0.0417 不算张开", carry_windows(np.array([0.0417] * 8 + [0.050] * 4)) == [])
    ck("w3 只张不合 ⇒ 没有搬运段", carry_windows(np.array([0.0417] * 3 + [0.079] * 6)) == [])
    ck("w4 合到释放但没再张 ⇒ 段尾 = 序列末", carry_windows(np.array([0.079] * 2 + [0.050] * 6))[0][1] == 7)
    wc = np.array([0.0417] * 3 + [0.079] * 2 + [0.070, 0.065, 0.060] + [0.050] * 5 + [0.079] * 2)
    ck("w5 闭合过渡值（0.070/0.065/0.060）不许把搬运段打断（真实 npz 就是这样）",
       carry_windows(wc) == [(8, 13)])
    ck("w6 与 mg_zlim_replay.carry_window 的首段语义一致",
       carry_windows(w)[0] == __import__("mg_zlim_replay").carry_window(w))

    # 合成一阶系统：Δz[t] = 0.4*dz[t] + 0.6*dz[t-1] + 0.2*dz[t-2] ⇒ 估计器必须原样收回（坑 77）
    rng = np.random.default_rng(7)
    u = rng.uniform(-1, 1, 4000)
    b_true = np.array([0.4, 0.6, 0.2, 0.0])
    y = np.convolve(u, b_true)[:4000] + rng.normal(0, 0.01, 4000)
    Xs = np.stack([u, np.roll(u, 1), np.roll(u, 2), np.roll(u, 3)], axis=1)
    gs = fit(Xs[20:], y[20:])
    ck("f1 无噪声合成系统 ⇒ 收回真 b（误差 <0.02）", max(abs(a - c) for a, c in zip(gs["b"], b_true)) < 0.02)
    ck("f2 k = Σb 与真值一致", abs(gs["k"] - b_true.sum()) < 0.02)
    ck("f3 R² 接近 1", gs["r2"] > 0.99)
    ck("f4 制动保真比 ≈ 1（线性系统）", abs(gs["brake_fidelity"] - 1.0) < 0.05)
    dd = design(gs)
    ck("d1 线性合成系统 ⇒ safety = 1（f_pos=f_brk=1）", abs(dd["safety"] - 1.0) < 0.05
       and abs(dd["k_eff"] - gs["k"] * dd["safety"]) < 1e-12)
    ck("d4 制动弱一半 ⇒ safety = 2（1/f_brk 支路生效）", design({"k": 1.3, "b": [0.4, 0.6, 0.2, 0.1],
                                                                  "accel_fidelity": 1.0, "brake_fidelity": 0.5})["safety"] == 2.0)
    ck("d5 上升猛 1.4 倍且制动准 ⇒ safety = 1.4（f_pos 支路生效）", design({"k": 1.3, "b": [0.4, 0.6, 0.2, 0.1],
                                                                       "accel_fidelity": 1.4, "brake_fidelity": 1.0})["safety"] == 1.4)
    ck("d6 safety 恒 ≥ 1（绝不比 v1 激进）", design({"k": 1.3, "b": [0.4], "accel_fidelity": 0.3,
                                                 "brake_fidelity": 5.0})["safety"] == 1.0)
    ck("d7 缺保真比 ⇒ safety = 1（保守退化到纯模型）", design({"k": 1.3, "b": [0.4]})["safety"] == 1.0)
    ck("d2 阈值常数来自 mg_eval_zlim（单一真理源）", (OPEN_THR, GRASP_THR, RELEASE_THR) == (0.07, 0.058, 0.062))
    ck("d3 LAGS = 3（b0..b3）", LAGS == 3)

    print(f"dz 增益台钉子：{total[0]} 项检查，{len(fails)} 项失败")
    for f in fails:
        print("  🚫", f)
    print("ALL PASS" if not fails else "HAS FAILURES")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="附 lag 扫描（L=2/4/6 的 k 与 R²）")
    ap.add_argument("--out", default="runs/_diag/s9_tax/dz_gain_400.json")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    p = Path(args.out)
    return report(p if p.is_absolute() else MG_ROOT / p, args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
