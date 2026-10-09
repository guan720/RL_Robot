#!/usr/bin/env python
"""最小抓取链路 · 档 6：抓取失败的**机理分桶**（示范与策略同口径，纯离线，零 GPU）。

为什么不能直接用 `code/mg_diag_miss.py` 的读数下结论（本工具存在的唯一理由）：
  `mg_diag_miss.py` 定「合爪时刻」用了**两套不同的口径**——
    * 示范（`demo_reference()`）：`close_transition()` = 先张开 width>0.070 再合上 width<0.055；
    * 策略（`main()` 主循环）：`np.nonzero(width < W_EMPTY=0.020)[0]` = **首次空合到底**。
  这两者在成功局里差得很远：策略夹住 can 时 width=0.0417~0.050，**永远到不了 0.020**，
  所以「首次 width<0.020」只能发生在**后来某次空合**（实测 t=114~213，那时臂早已离开 can），
  于是 `dxy_at_close` 被打成 5~40 cm。**拿它跟专家的 0.6 cm 比 = 拿两个不同的事件比**，
  会得出「策略横向差一个数量级」的假结论（本会话 12:16 差点就这么写了）。
  本工具把两边**统一到 `close_transition()`**（直接 import，不重写口径），再分桶。

分桶（互斥，按顺序判；只用于 **A 类**失败 = `mg_tax_fail.klass` 判 A，即 can 基本没离地）：
  N  没合爪    t_close < 0                                    ⇒ 策略没进入抓取相位（时序/语言条件）
  L  没到过    min_dxy(t<=t_close) > DXY_FAR_CM(3.0)           ⇒ 接近段就没到位（视觉/动作尺度）
  H  合太高    dz_vs_ref > +DZ_TOL_CM(2.0)                     ⇒ 没下探到位就合爪（H2/H3）
  D  合太低    dz_vs_ref < -DZ_TOL_CM(2.0)                     ⇒ 下探过头，指头低于 can 中心
  X  横向偏    |dz|<=DZ_TOL ∧ dxy_at_close > DXY_BAD_CM(1.5)   ⇒ 高度对了、横向没对上
  F  细几何    |dz|<=DZ_TOL ∧ dxy_at_close <= DXY_BAD_CM       ⇒ **只有这一桶**才是「指隙 vs 容差」的战场
  非 A 类（OK/B/C）另计，不进上面的桶（它们的问题不在抓取）。

参照值 gz_ref（合爪高度）**必须自报出处**（坑 30）：默认 = `--demo-npz` 的反向示范在同一
`close_transition()` 口径下的 `z_at_close` 中位数；不给 demo 就退回 `mg_diag_miss.GRASP_Z_DEMO`
（那是**正向**的值，工具会打警告说反向不可信）。

can 初始位置不自建 env：从格 6A 的产物 `runs/_diag/miss_s3r_seed*_rev.json` 里读 `can_init`
（那是 `mg_diag_miss.can_init_positions()` 按同一 seed 重建的真值，已落盘 ⇒ 本工具保持零 GPU）。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_geom_taxonomy.py \
        --runs runs/s3r_seed3000_rev_test_rand20_k10{,_rep2,_rep3,_rep4} \
        --miss-json runs/_diag/miss_s3r_seed3000_rev.json \
        --demo-npz data/mix60f120r_rev_raw.npz --tag "seed3000 反向" \
        --out runs/_diag/geom_s3r_seed3000_rev.md'
    $MG_PY code/mg_geom_taxonomy.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

# 口径全部 import，**不在本文件里重新定义**（重新定义 = 又一套口径 = 结论不可比）
from mg_diag_miss import (  # noqa: E402
    CAN_RADIUS, CAN_TOP_Z, GRASP_Z_DEMO, IX, IY, IZ, IW, W_EMPTY, close_transition,
)
from mg_tax_fail import LIFT_OK_CM, NEAR_CM, _norm, klass, succ_of  # noqa: E402

DXY_FAR_CM = 3.0    # > can 半径 2.5 cm：合爪前 eef 从没到过 can 正上方 ⇒ 接近段失败
DXY_BAD_CM = 1.5    # can 半径的 60%；专家实测中位 0.6 cm（见 --demo-npz 参照），留 2.5× 余量
DZ_TOL_CM = 2.0     # 合爪高度容差；专家实测 z_at_close 中位 0.8784、范围 0.8666~0.9808
BUCKETS = ("N", "L", "H", "D", "X", "F")
BUCKET_NAME = {
    "N": "没合爪（未进入抓取相位）",
    "L": "合爪前没到过 can 附近（接近段失败）",
    "H": "合爪时太高（没下探到位）",
    "D": "合爪时太低（下探过头）",
    "X": "高度对、横向偏（>1.5 cm）",
    "F": "高度对、横向也对（≤1.5 cm）= 细几何/夹持",
}


def grasp_geom(states: np.ndarray, can0: np.ndarray, gz_ref: float) -> dict:
    """一局的抓取几何读数。states = (T,8) 的 observation.state；can0 = can 初始 xyz（米）。

    合爪时刻用 `close_transition()`（与示范同口径）。dxy/z 全部换算成 **cm** 再返回。
    """
    w = states[:, IW]
    t_close = close_transition(w)
    c0 = np.asarray(can0, dtype=np.float64)
    dvec = (states[:, IX:IY + 1] - c0[None, :2]) * 100.0          # 带符号 (dx,dy)，cm
    dxy = np.linalg.norm(dvec, axis=1)
    t_near = int(np.argmin(dxy))
    # 为什么必须带符号：|dxy| 只能说明「偏了多少」，说明不了「往哪边偏」。
    # 若 A 类失败一致偏向同一侧（例：dy 恒为正），那不是「精度不够要加数据」，
    # 而是**系统性偏置**（标定/归一化/手眼/相机镜像一类的 bug）——后者可以白修，前者要 10 h 重训。
    out = {
        "dx_at_close_cm": round(float(dvec[t_close, 0]), 2) if t_close >= 0 else None,
        "dy_at_close_cm": round(float(dvec[t_close, 1]), 2) if t_close >= 0 else None,
        "t_near": t_near,
        "dx_at_near_cm": round(float(dvec[t_near, 0]), 2),
        "dy_at_near_cm": round(float(dvec[t_near, 1]), 2),
        "t_close": int(t_close),
        "min_dxy_cm": round(float(dxy.min()), 2),
        "min_dxy_pre_cm": round(float(dxy[:t_close + 1].min()), 2) if t_close >= 0 else round(float(dxy.min()), 2),
        "dxy_at_close_cm": round(float(dxy[t_close]), 2) if t_close >= 0 else None,
        "z_at_close": round(float(states[t_close, IZ]), 4) if t_close >= 0 else None,
        "dz_vs_ref_cm": (round(float(states[t_close, IZ] - gz_ref) * 100.0, 2) if t_close >= 0 else None),
        "width_min": round(float(w.min()), 4),
        "ever_empty_close": bool((w < W_EMPTY).any()),
        "z_min": round(float(states[:, IZ].min()), 4),
        "below_can_top": bool((states[:, IZ] < CAN_TOP_Z).any()),
    }
    return out


def bucket_of(g: dict) -> str:
    """A 类失败的机理桶（互斥，按 N→L→H→D→X→F 顺序判）。非 A 类不该调这里。"""
    if g["t_close"] < 0:
        return "N"
    if g["min_dxy_pre_cm"] > DXY_FAR_CM:
        return "L"
    dz = g["dz_vs_ref_cm"]
    if dz is None:
        return "N"
    if dz > DZ_TOL_CM:
        return "H"
    if dz < -DZ_TOL_CM:
        return "D"
    if (g["dxy_at_close_cm"] or 0.0) > DXY_BAD_CM:
        return "X"
    return "F"


def demo_geom(npz_path: Path, can_init: dict[int, list[float]] | None) -> list[dict]:
    """示范在**同一口径**下的抓取几何（用来定 gz_ref，也用来给策略一个「专家有多准」的尺子）。"""
    d = np.load(npz_path)
    st_all, L = d["state"], np.asarray(d["episode_lengths"], dtype=int)
    seeds = [int(x) for x in np.asarray(d["seeds"]).reshape(-1)] if "seeds" in d else [-1] * len(L)
    out, off = [], 0
    for i, n in enumerate(L):
        st = st_all[off:off + n]
        off += n
        tc = close_transition(st[:, IW])
        c = (can_init or {}).get(seeds[i])
        rec = {"ep": i, "seed": seeds[i], "t_close": int(tc), "steps": int(n),
               "z_at_close": round(float(st[tc, IZ]), 4) if tc >= 0 else None,
               "width_min": round(float(st[:, IW].min()), 4)}
        if c is not None:
            rec["can_x"] = round(float(np.asarray(c, dtype=np.float64)[0]), 4)
            rec["can_y"] = round(float(np.asarray(c, dtype=np.float64)[1]), 4)
            dvec = (st[:, IX:IY + 1] - np.asarray(c, dtype=np.float64)[None, :2]) * 100.0
            dxy = np.linalg.norm(dvec, axis=1)
            rec["min_dxy_cm"] = round(float(dxy.min()), 2)
            tn = int(np.argmin(dxy))
            rec["dx_at_near_cm"] = round(float(dvec[tn, 0]), 2)
            rec["dy_at_near_cm"] = round(float(dvec[tn, 1]), 2)
            if tc >= 0:
                rec["dxy_at_close_cm"] = round(float(dxy[tc]), 2)
                rec["dx_at_close_cm"] = round(float(dvec[tc, 0]), 2)
                rec["dy_at_close_cm"] = round(float(dvec[tc, 1]), 2)
        out.append(rec)
    return out


def quantile(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    return float(np.quantile(np.asarray(xs, dtype=np.float64), q))


def describe(xs: list[float]) -> str:
    xs = [x for x in xs if x is not None]
    if not xs:
        return "-"
    return (f"n={len(xs)} 均值 {np.mean(xs):.2f} 中位 {np.median(xs):.2f} "
            f"p95 {quantile(xs, 0.95):.2f} 范围 [{min(xs):.2f},{max(xs):.2f}]")


def _ap(p) -> Path:
    """相对路径一律按 $MG_ROOT 解析（坑 41：路径全绝对，别让 cwd 决定读到哪个文件）。"""
    q = Path(p)
    return q if q.is_absolute() else MG_ROOT / q


def bias_stats(dxs: list[float], dys: list[float]) -> dict:
    """把「偏了多少」拆成**系统性偏置**与**随机散布**两部分。

    为什么要这个：|dxy| 一样是 2.6 cm，可以是「每局都往同一边偏 2.6 cm」（= 偏置，
    标定/归一化/手眼/镜像一类的 bug，能白修），也可以是「各方向乱偏、模长 2.6 cm」（= 精度不够，
    只能加数据/加训练）。两者的处方与代价差一个数量级，必须分开。

    concentration = ‖mean vector‖ / mean‖vector‖ ∈ [0,1]：
      → 1 表示全部指向同一方向（纯偏置）；→ 0 表示方向均匀（纯随机）。
    另给 mean 的 95% CI（正态近似）与符号检验的 p（双侧二项），两个都报，避免只看一个。
    """
    dx = np.asarray([v for v in dxs if v is not None], dtype=np.float64)
    dy = np.asarray([v for v in dys if v is not None], dtype=np.float64)
    n = int(min(len(dx), len(dy)))
    if n == 0:
        return {"n": 0}
    dx, dy = dx[:n], dy[:n]
    mag = np.hypot(dx, dy)
    mean_vec = np.array([dx.mean(), dy.mean()])
    conc = float(np.linalg.norm(mean_vec) / mag.mean()) if mag.mean() > 0 else 0.0
    out = {
        "n": n,
        "mean_dx": round(float(mean_vec[0]), 2), "mean_dy": round(float(mean_vec[1]), 2),
        "mean_mag": round(float(mag.mean()), 2),
        "mean_vec_mag": round(float(np.linalg.norm(mean_vec)), 2),
        "concentration": round(conc, 3),
        "bearing_deg": round(float(np.degrees(np.arctan2(mean_vec[1], mean_vec[0]))), 1),
    }
    for ax, v in (("dx", dx), ("dy", dy)):
        sem = float(v.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
        out[f"{ax}_ci95_lo"] = round(float(v.mean() - 1.96 * sem), 2)
        out[f"{ax}_ci95_hi"] = round(float(v.mean() + 1.96 * sem), 2)
        pos = int((v > 0).sum())
        # 符号检验：双侧二项 p（0.5），用正态近似 +  continuity correction，n 小时直接算组合数
        k = min(pos, n - pos)
        p = 2.0 * sum(_comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
        out[f"{ax}_sign_pos"] = pos
        out[f"{ax}_sign_p"] = round(min(1.0, p), 4)
    return out


def ols(xs: list[float], ys: list[float]) -> dict:
    """一元 OLS + 斜率的 95% CI（t 分布，n-2 自由度用正态近似兜底 n 小的情形）。

    返回 slope / intercept / r / n / slope_ci / gain（= 1 + slope）。
    ⚠️ **单位纪律**（本档 12:55 实测踩过）：`can_x` 是**米**、`dx_at_close_cm` 是**厘米**，
      直接 `gain = 1 + slope` 会算出 G=**-28.5** 这种荒谬值（真值 0.705）。slope 只有在 x 与 y
      **同长度单位**时才无量纲、`1+slope` 才有「增益」含义 ⇒ 调用方必须先把 x 换算成 cm。
    ⚠️ 名义 n 会骗人：本档 240 局只有 20 个不同的 can 位置，逐局回归的 CI 过窄。
      所以调用方必须**同时**用「先按位置取均值再回归」的保守口径，判定只认保守那一个
      （见 runs/S6_GEOM_PREREG.md 第五节）。
    """
    x = np.asarray([v for v in xs if v is not None], dtype=np.float64)
    y = np.asarray([v for v in ys if v is not None], dtype=np.float64)
    n = int(min(len(x), len(y)))
    if n < 3:
        return {"n": n}
    x, y = x[:n], y[:n]
    if x.std() == 0:
        return {"n": n}
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    dof = n - 2
    s2 = float(resid @ resid) / dof if dof > 0 else float("nan")
    se = float(np.sqrt(s2 / ((x - x.mean()) ** 2).sum())) if dof > 0 else float("nan")
    return {"n": n, "slope": round(float(b), 3), "intercept": round(float(a), 3),
            "r": round(float(np.corrcoef(x, y)[0, 1]), 3),
            "slope_se": round(se, 3),
            "slope_ci": (round(float(b - 1.96 * se), 3), round(float(b + 1.96 * se), 3)),
            "gain": round(1.0 + float(b), 3)}


def by_position_mean(pairs: list[tuple[float, float]]) -> tuple[list[float], list[float]]:
    """把 (can_x, dx) 按 **can_x 去重分组**取均值 ⇒ 每个位置一票，消除「同位置 12 次观测」的伪样本量。"""
    g: dict[float, list[float]] = {}
    for cx, dx in pairs:
        if cx is None or dx is None:
            continue
        g.setdefault(round(float(cx), 4), []).append(float(dx))
    xs = sorted(g)
    return xs, [float(np.mean(g[k])) for k in xs]


GAIN_GAP_TH = 0.30   # |G_策略 − G_专家| ≥ 它 ⇒ 判「x 方向系统性增益错」（预注册第五节）


def pearson_r(xs: list[float], ys: list[float]) -> tuple[float, int]:
    """皮尔逊相关 + n。**只在 |r| 与 n 一起读**：n=20 时 1σ(r)≈0.22，|r|<0.45 基本是噪声。"""
    x = np.asarray([v for v in xs if v is not None], dtype=np.float64)
    y = np.asarray([v for v in ys if v is not None], dtype=np.float64)
    n = int(min(len(x), len(y)))
    if n < 3:
        return float("nan"), n
    x, y = x[:n], y[:n]
    if x.std() == 0 or y.std() == 0:
        return float("nan"), n
    return round(float(np.corrcoef(x, y)[0, 1]), 3), n


def spatial_table(eps: list[dict], crit: str) -> list[dict]:
    """按 **TEST seed（= can 初始位置）** 聚合。reset(seed) 是确定的 ⇒ seed 唯一决定 can 初态。

    为什么要这一节：抖动区只有 x∈[-6,+1] cm、y∈[-4,+4] cm（`mg_env_reverse.INIT_JITTER_*`），
    20 个 TEST 位置 × 3 训练 seed × 4 rep = 每个位置 12 次观测。若失败**集中在个别位置**
    ⇒ 是示范覆盖漏洞，处方 = **定向**补那几格的数据（便宜）；
    若失败在位置上是**平的** ⇒ 是全局精度不足，处方 = 整体加数据/加训练（贵）。
    这两个处方代价差好几倍，必须先分开。
    """
    by: dict[int, list[dict]] = {}
    for e in eps:
        by.setdefault(int(e.get("seed", -1)), []).append(e)
    rows = []
    for sd, es in sorted(by.items()):
        c0 = es[0].get("_can_init")
        k_ok = sum(1 for e in es if klass(e, crit) == "OK")
        k_a = sum(1 for e in es if klass(e, crit) == "A")
        buckets = {b: 0 for b in BUCKETS}
        for e in es:
            if klass(e, crit) == "A":
                buckets[bucket_of(e["_geom"])] += 1
        rows.append({
            "seed": sd, "n": len(es), "n_ok": k_ok, "rate": round(100.0 * k_ok / len(es), 1),
            "can_x": round(float(c0[0]), 4) if c0 else None,
            "can_y": round(float(c0[1]), 4) if c0 else None,
            "n_A": k_a, "buckets": buckets,
            "mean_dx_close": round(float(np.mean([e["_geom"]["dx_at_close_cm"]
                                                  for e in es if e["_geom"]["dx_at_close_cm"] is not None])), 2)
            if any(e["_geom"]["dx_at_close_cm"] is not None for e in es) else None,
            "mean_dy_close": round(float(np.mean([e["_geom"]["dy_at_close_cm"]
                                                  for e in es if e["_geom"]["dy_at_close_cm"] is not None])), 2)
            if any(e["_geom"]["dy_at_close_cm"] is not None for e in es) else None,
            "mean_min_dxy_pre": round(float(np.mean([e["_geom"]["min_dxy_pre_cm"] for e in es])), 2),
        })
    rows.sort(key=lambda r: (r["rate"], -r["n_A"]))
    return rows


ZERO_RATE_MIN_N = 8       # 一个位置至少这么多次观测，0 成功才算「覆盖漏洞」而不是小样本噪声
TARGETED_MIN_SHARE = 0.30  # 0 成功位置贡献的 A 类失败占比 ≥ 它 ⇒ 定向补数据划算


def _comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return 0.0
    r = 1.0
    for i in range(min(k, n - k)):
        r = r * (n - i) / (i + 1)
    return r


BIAS_CONC_TH = 0.60   # concentration ≥ 它 ⇒ 方向集中 = 系统性偏置（不是随机不准）
BIAS_MAG_TH_CM = 1.0  # 且平均矢量模长 ≥ 1 cm ⇒ 偏置量级值得查（小于它就是噪声级）


def load_miss_can_init(paths: list[Path]) -> dict[str, dict[int, list[float]]]:
    """从格 6A 产物里取 can 初始位置：{run_name: {seed: [x,y,z]}}（保持本工具零 GPU）。"""
    out: dict[str, dict[int, list[float]]] = {}
    for p in paths:
        j = json.loads(p.read_text())
        for key, val in j.items():
            if not isinstance(val, dict) or "episodes" not in val:
                continue
            if key == "demo_reference":
                # 6A 产物里这一项是**示范**参照（seed 5000..），不是评测 run；
                # 它的 episodes 没有 can_init 字段，混进来会污染按 run 名的查表。
                continue
            name = Path(key).name
            m = out.setdefault(name, {})
            for e in val["episodes"]:
                if e.get("can_init") is not None:
                    m[int(e["seed"])] = e["can_init"]
    return out


def build_report(args, gz_ref: float, gz_src: str, demo: list[dict],
                 groups: list[tuple[str, list[dict]]]) -> list[str]:
    lines: list[str] = []
    P = lines.append
    P(f"# 档 6 · 抓取失败机理分桶  {args.tag}")
    P(f"<!-- 由 code/mg_geom_taxonomy.py 生成于 {datetime.now():%Y-%m-%d %H:%M}；"
      f"合爪口径 = mg_diag_miss.close_transition()（张开>{0.070} → 合上<{0.055}），示范与策略**同一口径** -->")
    P("")
    P(f"* 成功判据：{args.criterion}（`mg_tax_fail.klass`，A/B 分界 lift<{LIFT_OK_CM} cm、B/C 分界 min_dist>{NEAR_CM} cm）")
    P(f"* 合爪高度参照 gz_ref = **{gz_ref:.4f}**，来源：{gz_src}")
    P(f"* 分桶阈值：DXY_FAR={DXY_FAR_CM} cm / DXY_BAD={DXY_BAD_CM} cm / DZ_TOL={DZ_TOL_CM} cm；"
      f"can 半径 {CAN_RADIUS*100:.1f} cm、can 顶面 z={CAN_TOP_Z}")
    P(f"* 读数来源：{', '.join(args.runs)}")
    P("")

    if demo:
        P("## 一、专家参照（**同口径**重算，这才是策略要对标的尺子）")
        P("")
        P(f"* 示范条数 {len(demo)}，合爪时刻 t_close 中位 {np.median([d['t_close'] for d in demo if d['t_close']>=0]):.0f}"
          f"（有 {sum(1 for d in demo if d['t_close']<0)} 条没测到合爪跃变）")
        P(f"* 合爪时横向偏差 dxy_at_close_cm：{describe([d.get('dxy_at_close_cm') for d in demo])}")
        P(f"* 全程最近横向 min_dxy_cm：{describe([d.get('min_dxy_cm') for d in demo])}")
        P(f"* 合爪高度 z_at_close：{describe([d.get('z_at_close') for d in demo])}")
        P(f"* 空合到底（width<{W_EMPTY}）的示范条数：{sum(1 for d in demo if d['width_min'] < W_EMPTY)}/{len(demo)}"
          "  ← 专家抓空时才会空合到底；夹住 can 时 width≈0.042~0.050")
        P("")
        P(f"> ⚠️ `mg_diag_miss.py` 报的「策略空合时 dxy 5~40 cm」用的是**首次 width<{W_EMPTY}**，"
          "那是合爪失败**之后**的某次空合（臂已离开 can），不能与专家的 dxy_at_close 直接比。本节已换回同口径。")
        P("")

    P("## 二、A 类失败（can 从没离地）的机理分桶")
    P("")
    hdr = "| 组 | n局 | OK | A | B | C | " + " | ".join(BUCKETS) + " | A 类主桶 |"
    P(hdr)
    P("|" + " --- |" * (len(BUCKETS) + 6))
    pooled: dict[str, list] = {b: [] for b in BUCKETS}
    pooled_a = 0
    pooled_tot = 0
    pooled_succ = 0
    for name, eps in groups:
        cnt = {"OK": 0, "A": 0, "B": 0, "C": 0, "UNK": 0}
        bcnt = {b: 0 for b in BUCKETS}
        for e in eps:
            k = klass(e, args.criterion)
            cnt[k] = cnt.get(k, 0) + 1
            if k == "A":
                b = bucket_of(e["_geom"])
                bcnt[b] += 1
                pooled[b].append(e)
        pooled_a += cnt["A"]
        pooled_tot += len(eps)
        pooled_succ += cnt["OK"]
        main_b = max(BUCKETS, key=lambda b: bcnt[b]) if cnt["A"] else "-"
        P(f"| {name} | {len(eps)} | {cnt['OK']} | {cnt['A']} | {cnt['B']} | {cnt['C']} | "
          + " | ".join(str(bcnt[b]) for b in BUCKETS)
          + f" | {main_b}（{bcnt[main_b]}/{cnt['A']}） |" if cnt["A"] else
          f"| {name} | {len(eps)} | {cnt['OK']} | {cnt['A']} | {cnt['B']} | {cnt['C']} | "
          + " | ".join(str(bcnt[b]) for b in BUCKETS) + " | - |")
    P("")
    for b in BUCKETS:
        P(f"* **{b}** = {BUCKET_NAME[b]}：{len(pooled[b])} 局"
          + (f"（占 A 类 {100*len(pooled[b])/max(pooled_a,1):.0f}%）" if pooled_a else ""))
    P("")

    P("## 三、A 类各桶的几何读数（cm）")
    P("")
    P("| 桶 | n | dxy_at_close | min_dxy_pre | dz_vs_ref | z_at_close | 空合到底 |")
    P("| --- | ---: | --- | --- | --- | --- | ---: |")
    for b in BUCKETS:
        es = pooled[b]
        if not es:
            P(f"| {b} | 0 | - | - | - | - | - |")
            continue
        gs = [e["_geom"] for e in es]
        P(f"| {b} | {len(es)} | {describe([g['dxy_at_close_cm'] for g in gs])} "
          f"| {describe([g['min_dxy_pre_cm'] for g in gs])} "
          f"| {describe([g['dz_vs_ref_cm'] for g in gs])} "
          f"| {describe([g['z_at_close'] for g in gs])} "
          f"| {sum(1 for g in gs if g['ever_empty_close'])}/{len(gs)} |")
    P("")

    P("## 四、可修上限（**仅诊断，不是成功口径，不参与任何门**）")
    P("")
    P(f"* 现状：{pooled_succ}/{pooled_tot} = {100*pooled_succ/max(pooled_tot,1):.1f}%（{args.criterion} 口径成功）")
    fix_xf = len(pooled["X"]) + len(pooled["F"])
    fix_hdx = len(pooled["H"]) + len(pooled["D"]) + len(pooled["X"])
    P(f"* 若把「合爪执行」修到专家水平（X+F 全救回）：({pooled_succ}+{fix_xf})/{pooled_tot} = "
      f"{100*(pooled_succ+fix_xf)/max(pooled_tot,1):.1f}%  ⇒ 上界增益 +{100*fix_xf/max(pooled_tot,1):.1f} pp")
    P(f"* 若连「下探时机」也修好（H+D+X 全救回，F 不算）：({pooled_succ}+{fix_hdx})/{pooled_tot} = "
      f"{100*(pooled_succ+fix_hdx)/max(pooled_tot,1):.1f}%  ⇒ 上界增益 +{100*fix_hdx/max(pooled_tot,1):.1f} pp")
    P(f"* A 类里**够不到**（L）与**没合爪**（N）共 {len(pooled['L'])+len(pooled['N'])} 局："
      "这两桶**不是**合爪几何能救的，收紧专家 `XY_TOL` 对它们无效。")
    P("")
    P("> 上界增益是「假设该桶 100% 救回」的天花板，不是预测值；真收益要按预注册跑干预档才知道。")
    P("")

    P("## 五、方向性：横向偏差是**系统性偏置**还是**随机不准**（处方差一个数量级）")
    P("")
    P(f"* concentration = ‖mean(dx,dy)‖ / mean‖(dx,dy)‖；判据（读数前钉死）："
      f"concentration ≥ {BIAS_CONC_TH} **且** mean 矢量 ≥ {BIAS_MAG_TH_CM} cm ⇒ 系统性偏置（查标定/归一化/手眼/镜像，可白修）；"
      f"否则 ⇒ 随机不准（只能加数据/加训练）。")
    P("")
    P("| 组 | 取样时刻 | n | mean_dx | mean_dy | dx 95%CI | dy 95%CI | mean 矢量 | concentration | 方位 |")
    P("| --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |")

    def row(label, sample, dxk, dyk, when):
        b = bias_stats([e["_geom"].get(dxk) for e in sample], [e["_geom"].get(dyk) for e in sample])
        if not b.get("n"):
            P(f"| {label} | {when} | 0 | - | - | - | - | - | - | - |")
            return b
        P(f"| {label} | {when} | {b['n']} | {b['mean_dx']:+.2f} | {b['mean_dy']:+.2f} "
          f"| [{b['dx_ci95_lo']:+.2f},{b['dx_ci95_hi']:+.2f}] | [{b['dy_ci95_lo']:+.2f},{b['dy_ci95_hi']:+.2f}] "
          f"| {b['mean_vec_mag']:.2f} | **{b['concentration']:.2f}** | {b['bearing_deg']:+.0f}° |")
        return b

    all_eps = [e for _n, eps in groups for e in eps]
    a_eps = [e for e in all_eps if klass(e, args.criterion) == "A"]
    xl_eps = [e for e in a_eps if bucket_of(e["_geom"]) in ("X", "L")]
    ok_eps = [e for e in all_eps if klass(e, args.criterion) == "OK"]
    b_close = row("全部 A 类", a_eps, "dx_at_close_cm", "dy_at_close_cm", "合爪时刻")
    b_xl = row("A 类 X+L 桶", xl_eps, "dx_at_close_cm", "dy_at_close_cm", "合爪时刻")
    b_near = row("全部 A 类", a_eps, "dx_at_near_cm", "dy_at_near_cm", "最近接近")
    b_ok = row("成功局（对照）", ok_eps, "dx_at_close_cm", "dy_at_close_cm", "合爪时刻")
    if demo:
        bd = bias_stats([d.get("dx_at_close_cm") for d in demo], [d.get("dy_at_close_cm") for d in demo])
        if bd.get("n"):
            P(f"| 专家示范 | 合爪时刻 | {bd['n']} | {bd['mean_dx']:+.2f} | {bd['mean_dy']:+.2f} "
              f"| [{bd['dx_ci95_lo']:+.2f},{bd['dx_ci95_hi']:+.2f}] | [{bd['dy_ci95_lo']:+.2f},{bd['dy_ci95_hi']:+.2f}] "
              f"| {bd['mean_vec_mag']:.2f} | **{bd['concentration']:.2f}** | {bd['bearing_deg']:+.0f}° |")
        bn = bias_stats([d.get("dx_at_near_cm") for d in demo], [d.get("dy_at_near_cm") for d in demo])
        if bn.get("n"):
            P(f"| 专家示范 | 最近接近 | {bn['n']} | {bn['mean_dx']:+.2f} | {bn['mean_dy']:+.2f} "
              f"| [{bn['dx_ci95_lo']:+.2f},{bn['dx_ci95_hi']:+.2f}] | [{bn['dy_ci95_lo']:+.2f},{bn['dy_ci95_hi']:+.2f}] "
              f"| {bn['mean_vec_mag']:.2f} | **{bn['concentration']:.2f}** | {bn['bearing_deg']:+.0f}° |")
    P("")
    for label, b in (("全部 A 类·合爪时刻", b_close), ("A 类 X+L 桶·合爪时刻", b_xl),
                     ("全部 A 类·最近接近", b_near), ("成功局·合爪时刻", b_ok)):
        if not b.get("n"):
            continue
        sys_bias = b["concentration"] >= BIAS_CONC_TH and b["mean_vec_mag"] >= BIAS_MAG_TH_CM
        P(f"* {label}：n={b['n']}，concentration={b['concentration']:.2f}，mean 矢量={b['mean_vec_mag']:.2f} cm，"
          f"dx 符号检验 p={b['dx_sign_p']}（{b['dx_sign_pos']}/{b['n']} 为正）、"
          f"dy p={b['dy_sign_p']}（{b['dy_sign_pos']}/{b['n']} 为正）⇒ "
          + ("🚫 **判为系统性偏置**：先去查标定/归一化/手眼/相机镜像，别急着重训。"
             if sys_bias else
             "✅ **判为随机不准**：方向不集中，没有可白修的偏置；处方是加数据/加训练，不是查 bug。"))
    P("")
    P("")
    P("> 单位 cm；dx/dy = **eef 减 can**（带符号，世界系）。合爪时刻那几行会自动剔除 N 桶（t_close<0，"
      "没测到合爪跃变）⇒ 它的 n 可能比「最近接近」行小，这不是丢数据。")
    P("> ⚠️ 失败局的 mean 矢量天然带**选择效应**（只在偏了才失败），所以判「系统性偏置」必须"
      "**同时**看成功局那一行：成功局也偏 = 标定问题；只有失败局偏 = 选择效应，不是 bug。")
    P("")

    P("## 六、空间分布：失败是**个别位置的覆盖漏洞**还是**全局精度不足**（决定补数据的代价）")
    P("")
    rows = spatial_table(all_eps, args.criterion)
    P(f"* 按 TEST seed（= can 初始位置）聚合，共 {len(rows)} 个位置、{len(all_eps)} 局；"
      f"每位置 n={rows[0]['n'] if rows else 0}（3 训练 seed × 4 rep，**注意跨 seed 混合**）")
    P("")
    P("| TEST seed | can_x | can_y | n | 成功 | 成功率 | A 类 | X | L | H | N | mean_dx | mean_dy | min_dxy_pre |")
    P("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in rows:
        P(f"| {r['seed']} | {r['can_x']} | {r['can_y']} | {r['n']} | {r['n_ok']} | **{r['rate']:.0f}%** "
          f"| {r['n_A']} | {r['buckets']['X']} | {r['buckets']['L']} | {r['buckets']['H']} | {r['buckets']['N']} "
          f"| {r['mean_dx_close'] if r['mean_dx_close'] is not None else '-'} "
          f"| {r['mean_dy_close'] if r['mean_dy_close'] is not None else '-'} | {r['mean_min_dxy_pre']} |")
    P("")
    zero = [r for r in rows if r["n"] >= ZERO_RATE_MIN_N and r["n_ok"] == 0]
    hi = [r for r in rows if r["n"] >= ZERO_RATE_MIN_N and r["rate"] >= 90.0]
    a_from_zero = sum(r["n_A"] for r in zero)
    a_total = sum(r["n_A"] for r in rows)
    share = a_from_zero / a_total if a_total else 0.0
    P(f"* 0 成功的位置（n≥{ZERO_RATE_MIN_N}）：**{len(zero)} 个**"
      + (f"（{', '.join(str(r['seed']) for r in zero)}）" if zero else "")
      + f"；≥90% 成功的位置：{len(hi)} 个")
    P(f"* 这些 0 成功位置贡献的 A 类失败：{a_from_zero}/{a_total} = **{100*share:.0f}%**")
    P(f"* 判据（读数前钉死）：0 成功位置 ≥2 个 **且** 贡献 A 类 ≥{100*TARGETED_MIN_SHARE:.0f}% ⇒ "
      "**覆盖漏洞**，处方 = 定向补那几格的示范（便宜）；否则 ⇒ **全局精度不足**，处方 = 整体加数据/加训练（贵）。")
    verdict_cov = len(zero) >= 2 and share >= TARGETED_MIN_SHARE
    P(f"* ⇒ 本次判定：**{'🎯 覆盖漏洞（定向补数据）' if verdict_cov else '🌐 全局精度不足（整体加数据/加训练）'}**")
    P("")
    cx = [r["can_x"] for r in rows if r["can_x"] is not None]
    cy = [r["can_y"] for r in rows if r["can_y"] is not None]
    rate = [r["rate"] for r in rows]
    for label, v in (("can_x", cx), ("can_y", cy)):
        r1, n1 = pearson_r(v, rate)
        P(f"* {label} vs 成功率：r={r1}（n={n1} 个位置）"
          + ("  ⚠️ n 小、1σ(r)≈0.22 ⇒ |r|<0.45 读作噪声" if n1 < 50 else ""))
    r2, n2 = pearson_r([float(e["_can_init"][0]) for e in all_eps if e.get("_can_init")],
                       [e["_geom"]["dx_at_close_cm"] for e in all_eps if e.get("_can_init")
                      and e["_geom"]["dx_at_close_cm"] is not None])
    P(f"* can_x vs 合爪横向误差 dx：r={r2}（n={n2} 局）⇒ 若显著为负/正，说明误差随工作区位置**成比例**放大"
      "（那是尺度/标定问题的指纹）；接近 0 则与位置无关（精度问题）。")
    P("")

    P("## 七、x 方向增益回归：`dx_at_close[cm] = a + b·can_x[cm]`，隐含增益 `G = 1 + b`")
    P("")
    P("* G 的读法：can 往 +x 挪 1 cm，eef 在合爪时刻跟着挪 **G** cm。G=1 = 完美跟随；"
      "G<1 = 追不够（远端系统性欠伸）；G>1 = 追过头。")
    P("* 预注册见 `runs/S6_GEOM_PREREG.md` 第五节（判据在算斜率之前钉死）。")
    P("* **判定只认「按位置取均值」那一行**（n=20 个不同 can 位置）；逐局那行名义 n=239 但只有 20 个"
      "独立位置，CI 会**过窄**，只作对照。")
    P("")
    P("| 样本 | 口径 | n | slope b（cm/cm，无量纲） | 95%CI | 隐含增益 G=1+b | r |")
    P("| --- | --- | ---: | ---: | --- | ---: | ---: |")

    def gain_row(label, pairs):
        # can_x 由**米**换成 **cm**，与 dx 同单位 ⇒ slope 无量纲（cm/cm），gain=1+slope 才是增益。
        # 不换算会得到 cm/m（大 100 倍）、gain=-28.5 那种荒谬值（见 ols() 的单位纪律注）。
        pairs = [(None if cx is None else float(cx) * 100.0, dy) for cx, dy in pairs]
        out = {}
        for kind, (xx, yy) in (("逐局", ([p[0] for p in pairs], [p[1] for p in pairs])),
                               ("按位置均值", by_position_mean(pairs))):
            f = ols(xx, yy)
            if f.get("n", 0) < 3:
                P(f"| {label} | {kind} | {f.get('n',0)} | - | - | - | - |")
                out[kind] = None
                continue
            P(f"| {label} | {kind} | {f['n']} | {f['slope']:+.3f} "
              f"| [{f['slope_ci'][0]:+.3f},{f['slope_ci'][1]:+.3f}] | **{f['gain']:.3f}** | {f['r']:+.2f} |")
            out[kind] = f
        return out

    pol_all = [(e["_can_init"][0], e["_geom"]["dx_at_close_cm"]) for e in all_eps if e.get("_can_init")]
    pol_ok = [(e["_can_init"][0], e["_geom"]["dx_at_close_cm"]) for e in ok_eps if e.get("_can_init")]
    pol_a = [(e["_can_init"][0], e["_geom"]["dx_at_close_cm"]) for e in a_eps if e.get("_can_init")]
    g_all = gain_row("策略·全部局", pol_all)
    g_ok = gain_row("策略·成功局", pol_ok)
    g_a = gain_row("策略·A 类失败", pol_a)
    g_demo = gain_row("专家示范", [(d.get("can_x"), d.get("dx_at_close_cm")) for d in demo]) if demo else {}
    P("")
    gp = (g_all or {}).get("按位置均值")
    gd = (g_demo or {}).get("按位置均值")
    if gp and gd:
        gap = abs(gp["gain"] - gd["gain"])
        ci_has_zero = gp["slope_ci"][0] <= 0.0 <= gp["slope_ci"][1]
        demo_ci_has_zero = gd["slope_ci"][0] <= 0.0 <= gd["slope_ci"][1]
        same_sign = gp["slope"] * gd["slope"] > 0
        P(f"* 策略（按位置，**判定只认这一行**）G = **{gp['gain']:.3f}**，slope b = {gp['slope']:+.3f}，"
          f"95%CI [{gp['slope_ci'][0]:+.3f},{gp['slope_ci'][1]:+.3f}] ⇒ CI {'含' if ci_has_zero else '**不含**'} 0")
        P(f"* 专家（按位置，对照）G = **{gd['gain']:.3f}**，slope b = {gd['slope']:+.3f}，"
          f"95%CI [{gd['slope_ci'][0]:+.3f},{gd['slope_ci'][1]:+.3f}] ⇒ CI {'含' if demo_ci_has_zero else '**不含**'} 0")
        P(f"* |G_策略 − G_专家| = **{gap:.3f}**（预注册门 {GAIN_GAP_TH}）")
        P("")
        P("判定（照 `runs/S6_GEOM_PREREG.md` 第五节的表格逐行走，不事后改门）：")
        if (not ci_has_zero) and gap >= GAIN_GAP_TH:
            P("* ① 命中：策略 CI 不含 0 **且** |G_策略−G_专家| ≥ 门 ⇒ 🚫 **x 方向系统性增益/尺度错**。"
              "处方 = 先查 action normalizer 的 dx 通道与 OSC 的 x 增益（便宜、可能白修），"
              "**不要**直接花 15 h 重训。")
        else:
            P(f"* ② 命中：策略 CI {'含' if ci_has_zero else '**不含**'} 0，且 |G_策略−G_专家| = {gap:.3f} "
              f"{'<' if gap < GAIN_GAP_TH else '≥'} 门 {GAIN_GAP_TH} ⇒ ✅ **不是可白修的尺度问题**。"
              "处方回到「整体加数据 / 加训练」。")
        if (not demo_ci_has_zero) and same_sign:
            ratio = gp["slope"] / gd["slope"] if gd["slope"] else float("nan")
            P(f"* ③ 附注：**专家自己也有同向显著斜率**（b_专家={gd['slope']:+.3f} vs b_策略={gp['slope']:+.3f}，"
              f"比值 {ratio:.1f}×）⇒ 存在**任务固有的远端难度梯度**（can 越靠 +x 越难够），"
              "这部分是环境几何造成的，不能全算在策略头上；比值越大，策略相对专家的欠伸越严重。")
    P("")
    return lines


def selftest() -> int:
    fails: list[str] = []
    n_chk = 0

    def chk(cond, msg):
        nonlocal n_chk
        n_chk += 1
        if not cond:
            fails.append(msg)

    # --- close_transition 口径复用（不重新实现）---
    w_open_then_close = np.array([0.0417, 0.079, 0.0805, 0.079, 0.055, 0.050, 0.049])
    # 阈值是**严格小于** W_CLOSE_TH=0.055 ⇒ 0.055 那一步不算合上，落在下一步的 0.050
    chk(close_transition(w_open_then_close) == 5, "close_transition 应落在首次 <0.055 的那一步（0.055 不算）")
    chk(close_transition(np.array([0.0417, 0.079, 0.0805, 0.079, 0.050])) == 4, "同一口径的另一次核对")
    chk(close_transition(np.array([0.0417] * 5)) == -1, "从没张开过 ⇒ 不该判出合爪（reset 半合 0.0417）")

    # --- grasp_geom：合爪时高度/横向读数 ---
    T = 6
    st = np.zeros((T, 8), dtype=np.float64)
    st[:, IZ] = 0.92          # eef 高度恒定
    st[:, IW] = [0.0417, 0.080, 0.080, 0.050, 0.049, 0.049]
    st[:, IX] = np.linspace(0.30, 0.31, T)
    st[:, IY] = 0.0
    can0 = np.array([0.31, 0.0, 0.8603])
    g = grasp_geom(st, can0, gz_ref=0.8784)
    chk(g["t_close"] == 3, f"t_close 应=3，实得 {g['t_close']}")
    # IX = linspace(0.30, 0.31, 6) ⇒ 第 3 步 x=0.306，can 在 0.31 ⇒ dxy = 0.4 cm
    chk(abs(g["dxy_at_close_cm"] - 0.4) < 1e-3, f"dxy_at_close 应=0.4cm，实得 {g['dxy_at_close_cm']}")
    chk(abs(g["min_dxy_cm"] - 0.0) < 1e-3, "最后一步 eef 与 can 同 xy ⇒ min_dxy=0")
    chk(abs(g["dz_vs_ref_cm"] - (0.92 - 0.8784) * 100) < 1e-2, "dz_vs_ref 应是 (z-gz_ref)*100")
    chk(g["z_at_close"] == 0.92, "z_at_close 单位应是米")
    chk(g["ever_empty_close"] is False, "width 最低 0.049 ⇒ 不算空合到底")

    # --- bucket_of 的互斥与顺序 ---
    chk(bucket_of({"t_close": -1, "min_dxy_pre_cm": 40.0, "dz_vs_ref_cm": None,
                   "dxy_at_close_cm": None}) == "N", "没合爪 ⇒ N 优先")
    chk(bucket_of({"t_close": 5, "min_dxy_pre_cm": 5.0, "dz_vs_ref_cm": 0.5,
                   "dxy_at_close_cm": 5.0}) == "L", "合爪前没到过 can ⇒ L（即使 dz 正常）")
    chk(bucket_of({"t_close": 5, "min_dxy_pre_cm": 0.5, "dz_vs_ref_cm": 4.3,
                   "dxy_at_close_cm": 2.6}) == "H", "太高 ⇒ H 优先于 X")
    chk(bucket_of({"t_close": 5, "min_dxy_pre_cm": 0.5, "dz_vs_ref_cm": -3.0,
                   "dxy_at_close_cm": 0.5}) == "D", "太低 ⇒ D")
    chk(bucket_of({"t_close": 5, "min_dxy_pre_cm": 0.5, "dz_vs_ref_cm": 1.0,
                   "dxy_at_close_cm": 2.0}) == "X", "高度对横向偏 ⇒ X")
    chk(bucket_of({"t_close": 5, "min_dxy_pre_cm": 0.5, "dz_vs_ref_cm": 1.0,
                   "dxy_at_close_cm": 1.5}) == "F", "dxy 恰好=DXY_BAD ⇒ F（阈值是严格大于）")
    chk(bucket_of({"t_close": 5, "min_dxy_pre_cm": 3.0, "dz_vs_ref_cm": 1.0,
                   "dxy_at_close_cm": 1.0}) == "F", "min_dxy_pre 恰好=DXY_FAR ⇒ 不判 L（严格大于）")

    # --- 与 mg_tax_fail 的 A 类定义一致（不重复实现）---
    e_a = _norm({"success": False, "success_relaxed": False, "max_lift_cm": 0.6, "min_dist_to_target_xy": 0.65})
    chk(klass(e_a, "relaxed") == "A", "lift 0.6cm ⇒ A 类")
    chk(abs(e_a["min_dist_cm"] - 65.0) < 1e-9, "_norm 必须把米换成厘米（差 100 倍会让 B/C 分界全错）")
    e_c = _norm({"success": False, "success_relaxed": False, "max_lift_cm": 13.9, "min_dist_to_target_xy": 0.10})
    chk(klass(e_c, "relaxed") == "C", "抬高了且送到附近 ⇒ C 类")
    e_b = _norm({"success": False, "success_relaxed": False, "max_lift_cm": 9.0, "min_dist_to_target_xy": 0.60})
    chk(klass(e_b, "relaxed") == "B", "抬高了但离目标 60cm ⇒ B 类")
    e_u = _norm({"success": False, "max_lift_cm": 0.1, "min_dist_to_target_xy": 0.6})
    chk(klass(e_u, "relaxed") == "UNK", "缺 success_relaxed ⇒ UNK，不当失败（坑 40③）")
    chk(succ_of(e_u, "relaxed") is None, "succ_of 缺字段必须返回 None")

    # --- demo_geom：与策略同一函数算，口径必须一致 ---
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "d.npz"
        st_all = np.zeros((7, 8), dtype=np.float64)
        st_all[:, IW] = [0.0417, 0.080, 0.080, 0.050, 0.049, 0.049, 0.049]
        st_all[:, IZ] = 0.8784
        st_all[:, IX] = 0.31
        st_all[:, IY] = 0.0
        np.savez(p, state=st_all.astype(np.float32), episode_lengths=np.array([7]),
                 seeds=np.array([5000]))
        recs = demo_geom(p, {5000: [0.31, 0.0, 0.8603]})
        chk(len(recs) == 1 and recs[0]["t_close"] == 3, "demo_geom 的 t_close 应与 grasp_geom 同")
        chk(recs[0]["dxy_at_close_cm"] == 0.0, "can 与 eef 同 xy ⇒ dxy=0")
        chk(abs(recs[0]["z_at_close"] - 0.8784) < 1e-3, "z_at_close 应保留米制原值")
        recs2 = demo_geom(p, None)
        chk(recs2[0].get("dxy_at_close_cm") is None, "没给 can_init ⇒ 不编造 dxy（缺料不当 0）")

    # --- bias_stats：纯偏置 vs 纯随机必须能分开 ---
    b_bias = bias_stats([2.0, 2.0, 2.0, 2.0], [0.0, 0.0, 0.0, 0.0])
    chk(b_bias["concentration"] == 1.0, f"全往 +x 偏 2cm ⇒ concentration=1，实得 {b_bias['concentration']}")
    chk(b_bias["mean_vec_mag"] == 2.0 and b_bias["mean_dx"] == 2.0, "偏置矢量应等于 2cm/+x")
    chk(b_bias["bearing_deg"] == 0.0, f"方位应 0°，实得 {b_bias['bearing_deg']}")
    # n=4 全同号时符号检验的**最小可达 p** = 2*C(4,0)/2^4 = 0.125 ⇒ 小样本本来就判不出显著，
    # 这条钉子是防止有人把「p 不显著」误读成「没有偏置」（n 小的时候它什么也证明不了）。
    chk(b_bias["dx_sign_p"] == 0.125, f"4/4 同号 ⇒ p 应=0.125（小样本下限），实得 {b_bias['dx_sign_p']}")
    b_bias10 = bias_stats([2.0] * 10, [0.0] * 10)
    chk(b_bias10["dx_sign_p"] < 0.01, f"10/10 同号 ⇒ 符号检验应显著，实得 {b_bias10['dx_sign_p']}")
    chk(b_bias10["concentration"] == 1.0, "10 局全同向 ⇒ concentration=1")
    b_rand = bias_stats([2.0, -2.0, 0.0, 0.0], [0.0, 0.0, 2.0, -2.0])
    chk(b_rand["concentration"] < 0.05, f"四方向对称 ⇒ concentration≈0，实得 {b_rand['concentration']}")
    chk(abs(b_rand["mean_vec_mag"]) < 1e-9, "对称散布 ⇒ mean 矢量应 0")
    chk(b_rand["dx_sign_p"] > 0.05, "2/4 同号 ⇒ 符号检验不该显著")
    chk(bias_stats([], [])["n"] == 0, "空输入 ⇒ n=0，不编造")
    chk(bias_stats([None, 1.0], [None, 1.0])["n"] == 1, "None 必须被剔除而不是当 0")
    chk(_comb(4, 2) == 6.0 and _comb(5, 0) == 1.0 and _comb(3, 5) == 0.0, "_comb 组合数")
    # 带符号读数确实进了 grasp_geom
    chk("dx_at_close_cm" in g and "dy_at_near_cm" in g, "grasp_geom 必须带符号读数")
    chk(abs(g["dx_at_close_cm"] - (-0.4)) < 1e-3, f"eef 在 can 左边 0.4cm ⇒ dx=-0.4，实得 {g['dx_at_close_cm']}")

    # --- pearson_r / spatial_table ---
    r_, n_ = pearson_r([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0])
    chk(r_ == 1.0 and n_ == 4, f"完全线性 ⇒ r=1，实得 {r_},{n_}")
    r2_, n2_ = pearson_r([1.0, 1.0], [2.0, 3.0])
    chk(np.isnan(r2_), "x 常数 ⇒ r=nan，不能编造")
    chk(pearson_r([1.0], [2.0])[1] == 1 and np.isnan(pearson_r([1.0], [2.0])[0]), "n<3 ⇒ nan")
    # spatial_table 需要 _geom，构造两局最小样本
    def mk(seed, ok, lift, dx, dy):
        e = _norm({"seed": seed, "success_relaxed": ok, "max_lift_cm": lift, "min_dist_to_target_xy": 0.5})
        e["_geom"] = {"t_close": 3, "dx_at_close_cm": dx, "dy_at_close_cm": dy, "min_dxy_pre_cm": abs(dx),
                      "dxy_at_close_cm": abs(dx), "dz_vs_ref_cm": 0.1, "z_at_close": 0.878}
        e["_can_init"] = [0.2, 0.4, 0.8603]
        return e
    srows = spatial_table([mk(7000, False, 0.3, 2.5, 0.1), mk(7000, False, 0.2, 2.0, -0.2),
                           mk(7001, True, 12.0, 0.3, 0.1), mk(7001, True, 11.0, -0.2, 0.0)], "relaxed")
    chk(len(srows) == 2, f"应按 seed 聚成 2 行，实得 {len(srows)}")
    chk(srows[0]["seed"] == 7000 and srows[0]["rate"] == 0.0, "0 成功的位置应排在最前")
    chk(srows[0]["buckets"]["X"] == 2, f"dxy=2.0~2.5cm 且高度对 ⇒ 两局都该进 X 桶，实得 {srows[0]['buckets']}")
    chk(srows[1]["rate"] == 100.0 and srows[1]["n_A"] == 0, "全成功的位置 rate=100、A=0")

    # --- ols / by_position_mean：斜率与 CI 必须可复算 ---
    f = ols([0.0, 1.0, 2.0, 3.0], [1.0, 3.0, 5.0, 7.0])
    chk(abs(f["slope"] - 2.0) < 1e-6, f"完美线性 y=1+2x ⇒ slope=2，实得 {f['slope']}")
    chk(abs(f["intercept"] - 1.0) < 1e-6, f"intercept=1，实得 {f['intercept']}")
    chk(abs(f["gain"] - 3.0) < 1e-6, "gain = 1 + slope")
    chk(f["r"] == 1.0, "完美线性 ⇒ r=1")
    noisy = ols([0.14, 0.16, 0.18, 0.20], [1.9, -0.4, -1.6, -2.1])
    chk(noisy["slope"] < 0 and noisy["slope_ci"][0] <= noisy["slope"] <= noisy["slope_ci"][1],
        "负斜率且 CI 应夹住 slope")
    chk(ols([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]).get("slope") is None, "x 常数 ⇒ 不出斜率（除零）")
    chk(ols([1.0], [2.0])["n"] == 1 and ols([1.0], [2.0]).get("slope") is None, "n<3 ⇒ 不出斜率")
    chk(ols([None, None], [1.0, 2.0])["n"] == 0, "全 None ⇒ n=0")
    # 单位钉子：can_x 用**米**、dx 用**厘米**，回归前必须把 x 换算成 cm；
    # 否则 slope 变成 cm/m（大 100 倍）、gain 变成 -28.5 那种荒谬值（本档 12:55 实测踩过）。
    xs_m = [0.14, 0.16, 0.18, 0.20]
    dxs = [5.0 - 0.3 * (v * 100.0) for v in xs_m]        # 真值：G = 1 - 0.3 = 0.7
    f_cm = ols([v * 100.0 for v in xs_m], dxs)           # 正确：x 换算成 cm
    f_m = ols(xs_m, dxs)                                 # 错误：x 还是米
    chk(abs(f_cm["slope"] + 0.3) < 1e-6, f"同单位 ⇒ slope=-0.3（无量纲），实得 {f_cm['slope']}")
    chk(abs(f_cm["gain"] - 0.7) < 1e-6, f"同单位 ⇒ G=0.7（can 挪 1cm、eef 只挪 0.7cm），实得 {f_cm['gain']}")
    chk(abs(f_m["slope"] + 30.0) < 1e-3, f"混单位 ⇒ slope=-30 cm/m（大 100 倍），实得 {f_m['slope']}")
    chk(abs(f_m["gain"] + 29.0) < 1e-3, "混单位的 gain 是荒谬值 ⇒ 这就是为什么 gain_row 必须先换算")

    bx, by = by_position_mean([(0.20, 1.0), (0.20, 3.0), (0.14, -2.0), (None, 5.0),
                               (0.16, None), (0.16, 0.0)])
    chk(bx == [0.14, 0.16, 0.20], f"应按 can_x 升序去重，实得 {bx}")
    chk(by == [-2.0, 0.0, 2.0], f"同位置取均值，实得 {by}")
    chk(by_position_mean([(0.16, None), (None, 1.0)]) == ([], []),
        "can_x 或 dx 缺一个 ⇒ 该点整条剔除（缺料不当 0，坑 40③）")

    # --- describe/quantile 对空与含 None 稳健 ---
    chk(describe([]) == "-", "空列表 ⇒ '-'")
    chk(describe([None, None]) == "-", "全 None ⇒ '-'，不当 0")
    chk(np.isnan(quantile([], 0.5)), "空列表分位数 = nan")

    print(f"档 6 机理分桶工具钉子：{n_chk} 项检查，{len(fails)} 项失败")
    for f in fails:
        print("  FAIL:", f)
    print("ALL PASS" if not fails else "HAS FAILURES")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="*", default=[], help="评测产物目录（含 eval_summary.json + rollout_actions.npz）")
    ap.add_argument("--miss-json", nargs="*", default=[], help="格 6A 产物（提供 can_init，避免本工具重建 env）")
    ap.add_argument("--demo-npz", default="", help="示范 npz：同口径算专家参照 + 定 gz_ref")
    ap.add_argument("--criterion", choices=("strict", "relaxed"), default="relaxed", help="主口径默认放宽 R")
    ap.add_argument("--gz-ref", type=float, default=0.0, help="手动指定合爪高度参照（默认取示范中位数）")
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--dump-json", default="", help="把逐局读数也落一份 json（便于复查/复用）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.runs:
        print("[err] 需要 --runs（或 --selftest）", file=sys.stderr)
        return 2

    can_init_by_run = load_miss_can_init([_ap(p) for p in args.miss_json])
    # 兜底表：某个 run 的 map 里缺这个 seed 时，从**任意**一个 run 的 map 里取
    # （TEST 窗口 seed 7000..7019 在所有 rep 里是同一批，can 初态由 seed 唯一决定）。
    fallback_can_init: dict[int, list[float]] = {}
    for m in can_init_by_run.values():
        for sd, c in m.items():
            fallback_can_init.setdefault(sd, c)

    demo: list[dict] = []
    gz_ref, gz_src = GRASP_Z_DEMO, f"硬编码 mg_diag_miss.GRASP_Z_DEMO（没给 --demo-npz）⚠️ 这是**正向**值，反向不可信"
    if args.demo_npz:
        dp = _ap(args.demo_npz)
        # 示范的 seed 与 TEST 窗口不同 ⇒ can_init 得现算。这里用 mg_diag_miss 的重建函数（同一实现）。
        from mg_diag_miss import can_init_positions
        d = np.load(dp)
        dseeds = [int(x) for x in np.asarray(d["seeds"]).reshape(-1)] if "seeds" in d else []
        dcan = can_init_positions(dseeds, "reverse" if dp.name.endswith("_rev_raw.npz") else "forward", 64) \
            if dseeds else {}
        demo = demo_geom(dp, {k: v.tolist() for k, v in dcan.items()})
        zc = [r["z_at_close"] for r in demo if r.get("z_at_close") is not None]
        gz_ref = float(np.median(zc)) if zc else GRASP_Z_DEMO
        gz_src = (f"--demo-npz {dp.name} 同口径 z_at_close 中位数（n={len(zc)}，"
                  f"范围 {min(zc):.4f}~{max(zc):.4f}）" if zc else gz_src)
    if args.gz_ref:
        gz_ref, gz_src = float(args.gz_ref), f"--gz-ref 手动指定 {args.gz_ref:.4f}"

    groups: list[tuple[str, list[dict]]] = []
    for r in args.runs:
        run = _ap(r)
        summary = json.loads((run / "eval_summary.json").read_text())
        npz = np.load(run / "rollout_actions.npz")
        lengths = np.asarray(npz["episode_lengths"], dtype=int)
        states = npz["state"]
        per = summary.get("per_episode", [])
        cmap = can_init_by_run.get(run.name, {})
        eps, off = [], 0
        for i, Ln in enumerate(lengths):
            st = states[off:off + Ln]
            off += Ln
            pe = _norm(per[i], run.name) if i < len(per) else _norm({}, run.name)
            seed = int(pe.get("seed", -1))
            c = cmap.get(seed) or fallback_can_init.get(seed)
            if c is None:
                pe["_geom"] = None
                pe["_skip"] = "no can_init"
                eps.append(pe)
                continue
            pe["_geom"] = grasp_geom(np.asarray(st, dtype=np.float64), np.asarray(c, dtype=np.float64), gz_ref)
            pe["_can_init"] = list(c)
            pe["_src"] = run.name
            eps.append(pe)
        groups.append((run.name, [e for e in eps if e.get("_geom")]))
        skipped = sum(1 for e in eps if e.get("_skip"))
        if skipped:
            print(f"[warn] {run.name}: {skipped} 局缺 can_init，已**剔除**（不当失败计入）")

    lines = build_report(args, gz_ref, gz_src, demo, groups)
    txt = "\n".join(lines) + "\n"
    print(txt)
    if args.out:
        out = _ap(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(txt)
        print(f"[geom] 落盘 -> {out}")
    if args.dump_json:
        dj = _ap(args.dump_json)
        dj.parent.mkdir(parents=True, exist_ok=True)
        payload = {"gz_ref": gz_ref, "gz_source": gz_src, "criterion": args.criterion,
                   "thresholds": {"DXY_FAR_CM": DXY_FAR_CM, "DXY_BAD_CM": DXY_BAD_CM, "DZ_TOL_CM": DZ_TOL_CM},
                   "demo": demo,
                   "groups": {n: [{k: v for k, v in e.items()} for e in eps] for n, eps in groups}}
        dj.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        print(f"[geom] 逐局 json -> {dj}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
