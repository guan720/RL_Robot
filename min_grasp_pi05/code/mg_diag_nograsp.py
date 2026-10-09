#!/usr/bin/env python
"""档 8 事前诊断 · 「专家为什么到不了 `grasp`」的**离线**分类账（零 GPU 推理）。

### 为什么要有它
`runs/_diag/s8a_yield_forecast.md`（`runs/S8_PREREG.md` §9 增补 6）把格 8A 的 A2 三个点估计
全压在 40% 门下，并把承重机理定位成「**专家从策略访问到的状态到不了 `grasp`**，不是步数预算不够」
（语料里「未到 grasp 但步数足够」**12 局 0 成功**、「到 grasp 且步数足够」6 局 **5 成功**）。
但那份预测只拿**相位串**当签名（`phases=['approach','descend']` ∧ `n_restages=0`），
**没有**量到「卡在哪儿、差多少米、现有停滞判据看不看得见」。本工具补上这一步，且**完全离线**：
盘上的 `rollout_actions.npz` 已有逐步 `state[:,0:3] = eef_xyz` 与 `source`（1=专家），
缺的只有 can 的初态 —— 而 can 初态由 seed 决定 ⇒ **20 次 `env.reset(seed)`** 就能重建，
并拿每局记录里的 `can_z0` 做**交叉核对**（对不上就中止、不出数）。

### 口径为什么可信（逐字对齐，不猜相位）
`code/mg_eval_harness.py:183` 记的是 `env.step(act)` **之前**的 `obs[STATE_KEY]`，
而 `mg_expert.__call__` 用的 `self.env.eef_pos` 取自同一份 `_last_obs_raw`
⇒ 盘上的 `state[i,0:3]` **就是**专家算第 i 步动作时看到的那个 eef。can 在 grasp 之前不会动
⇒ 用初态当真值是**精确**的（不是近似）。所以本工具算的 `xy_err / z_err` 与专家当时算的
是同一个数（`z_err` 的表达式与 `code/mg_expert.py:227` 逐字相同，常数全部 import —— 坑 67）。

⚠️ **本工具不做相位重放**：`per_episode` 只存了相位的**去重有序表**、没有逐步相位，重放会引入
自己的分歧源。改用**相位无关**的判据 —— 「xy 有没有**曾经**对准过」（`min(xy_err) < XY_TOL`）
决定专家有没有可能离开 `approach`，「终态落在哪个几何区」决定停滞判据看不看得见。
每条结论都标了它依赖的前提。

### 三条诚实标注（写进报告，不许被摘掉）
1. 盘上**所有**带接管的语料都出自**好 seed 1000**（`pi05_mix60f120r_s2e`）；8A 跑的是**坏 seed 2000**
   ⇒ 本分类账只能读成「机理的**存在性与形状**」，**不能**读成 8A 的产出率（与增补 6 同一条偏差）。
2. 只统计**从未到 `grasp`** 的接管片段：进过 grasp 之后 can 被搬走，拿初态当真值就错了。
   那些局另计（`n_excl_reached_grasp`），一条都不混进来。
3. 样本量小（接管局 ~35、其中未到 grasp ~16）⇒ 报告里每个占比都带 Wilson 区间，
   并对 n<5 的格子打 `LOW_POWER` 标（口径同 `code/mg_forecast_s8a.py`）。

### 它**不改任何门**
A1/A2/A3、三条过滤、B1/B2/B3、D1~D4 一条都不读它的产物。用途只有一个：
8A 若写 `runs/s8a.HELD`，当晚就能拿盘上的数说清「该修专家的哪一段」，不必再开一档复现失败。

用法：
    $MG_PY code/mg_diag_nograsp.py --selftest                       # 纯 CPU、零仿真
    $MG_PY code/mg_diag_nograsp.py                                  # 默认语料 = 档 5.1 的 4×20
    $MG_PY code/mg_diag_nograsp.py --runs 'runs/s5_takeover_rev_test20_k10*' --out runs/_diag/nograsp_s5
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import math
import platform
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_env import HORIZON, IMG_KEY_BASE, STATE_NAMES  # noqa: E402
from mg_expert import (  # noqa: E402
    DESCEND_MAX_RESTAGES, DESCEND_STALL_DZ, GRASP_OFFSET_Z, PRE_HEIGHT, XY_TOL, Z_TOL,
)

RUNS = MG_ROOT / "runs"
DEFAULT_CORPUS = str(RUNS / "s5_1_handback_rev_test20_k10*")
LOW_POWER_N = 5                 # 与 code/mg_forecast_s8a.py 同口径
Z_WARN = 1.96
EEF_X, EEF_Y, EEF_Z, WIDTH = 0, 1, 2, 7      # STATE_NAMES 的下标（下面有自测钉住）

# 几何区（**相位无关**）。判据全部取自 code/mg_expert.py 的 descend 分支：
#   进 grasp   : xy_ok ∧ |z_err| < Z_TOL          （xy_ok = max(|dx|,|dy|) < XY_TOL，严格 <）
#   停滞可见   : z_err > Z_TOL ∧ |dz| < DESCEND_STALL_DZ   （**只在 descend 相位里跑**）
REGION_ORDER = ["S0_both_ok", "S1_above_xyoff", "S2_band_xyoff", "S3_below_band", "S4_above_xyok"]
# 「停滞判据**无论相位**都看不见」的区：S2/S3 的 z_err 不满足 > Z_TOL；
# S1 的 z_err 满足 > Z_TOL ⇒ 在 descend 里**可能**被看见，但在 approach 里**一定**看不见
# （approach 分支没有任何停滞判据）⇒ 所以 S1 的可见性是**相位依赖**的，单列。
ALWAYS_INVISIBLE = {"S2_band_xyoff", "S3_below_band"}
PHASE_DEPENDENT = {"S1_above_xyoff"}
STALL_VISIBLE_REGIONS = {"S4_above_xyok", "S1_above_xyoff"}


def wilson(k: int, n: int, z: float = Z_WARN) -> tuple[float, float]:
    """二项 Wilson 区间（%）。n=0 ⇒ (nan, nan)，**不许 0 兜底**（0 会假装「测过了、没有」）。"""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, 100 * (c - m) / d), min(100.0, 100 * (c + m) / d))


def region_of(xy_err: float, z_err: float, xy_tol: float = XY_TOL, z_tol: float = Z_TOL) -> str:
    """把一个专家步的 (xy_err, z_err) 归到几何区。边界口径与 mg_expert.py **逐字对齐**：
    进 grasp 用严格 `<` ⇒ 取反是 `>=`（压线**算**没对准）。"""
    xy_ok = xy_err < xy_tol
    if z_err < -z_tol:
        return "S3_below_band"
    if abs(z_err) <= z_tol:
        return "S0_both_ok" if xy_ok else "S2_band_xyoff"
    return "S4_above_xyok" if xy_ok else "S1_above_xyoff"


def stall_can_fire(region: str, dz: float | None, stall_dz: float = DESCEND_STALL_DZ) -> bool:
    """这一步**能不能**被 descend 的停滞判据看见（`z_err > Z_TOL ∧ |dz| < stall_dz`）。
    返回 True 只是「判据的条件成立」，**不代表当时真在 descend 相位**（S1 可能还在 approach）。"""
    if region not in STALL_VISIBLE_REGIONS:
        return False
    return dz is not None and abs(dz) < stall_dz


def seg_stats(xy: np.ndarray, z: np.ndarray, dz: np.ndarray,
              xy_tol: float = XY_TOL, z_tol: float = Z_TOL) -> dict:
    """一段专家步的几何汇总。`xy`/`z` 逐步，`dz` 长度 = len(xy)-1（第一步没有上一步）。"""
    n = int(len(xy))
    if n == 0:
        return {"n_steps": 0}
    reg = [region_of(float(a), float(b), xy_tol, z_tol) for a, b in zip(xy, z)]
    cnt = Counter(reg)
    fires = [stall_can_fire(r, (float(dz[i - 1]) if i > 0 and i - 1 < len(dz) else None))
             for i, r in enumerate(reg)]
    tail_invis = 0
    for f in reversed(fires):
        if f:
            break
        tail_invis += 1
    return {
        "n_steps": n,
        "region_counts": {k: int(cnt.get(k, 0)) for k in REGION_ORDER},
        "frac_always_invisible": float(sum(cnt.get(k, 0) for k in ALWAYS_INVISIBLE) / n),
        "frac_stall_could_fire": float(sum(fires) / n),
        "tail_run_stall_invisible": int(tail_invis),      # 收尾连续多少步停滞判据看不见
        "xy_err_first": float(xy[0]), "xy_err_last": float(xy[-1]),
        "xy_err_min": float(xy.min()), "xy_err_max": float(xy.max()),
        "z_err_first": float(z[0]), "z_err_last": float(z[-1]),
        "z_err_min": float(z.min()), "z_err_max": float(z.max()),
        "region_first": reg[0], "region_last": reg[-1],
        "ever_xy_ok": bool(xy.min() < xy_tol),            # 专家有没有**曾经**水平对准过
        "ever_in_band": bool(np.abs(z).min() <= z_tol),   # 有没有**曾经**进过抓取带
    }


def klass_stuck(ever_xy_ok: bool, region_last: str, n_restages: int, unrecoverable: bool,
                steps_remain: int, max_restages: int = DESCEND_MAX_RESTAGES,
                phase_implies_xy_ok: bool = False) -> tuple[str, str]:
    """「到不了 grasp」的**相位无关**归因（返回 (代码, 人话)）。

    前提：这一局**从未到 `grasp`**（调用方保证），且 can 全程在初态。

    ⚠️ **效度门（`phase_implies_xy_ok`，2026-10-04 加，是这份账最重要的一条）**：
    记录的相位串里出现 `descend` ⇒ 专家在**某一步**满足过 `xy_ok`，而 `xy_ok` 是拿
    `self.env.object_pos`（**当时的真 can**）算的（`code/mg_expert.py:186,221`）。
    所以「相位串含 descend ∧ 我按 `can_pos0` 重建出 `ever_xy_ok=False`」是**逻辑矛盾**，
    唯一解释是 **can 在接管之前就被策略撞走/夹走又掉了** ⇒ 本工具的重建对这一局**失效**，
    归到 `RX_can_moved`、**不进**归因分布（宁可少 15 局，也不出一份口径错的账）。
    独立佐证：这些局的 `max_lift_cm` 有 12~20 cm（can 被举起过），而 `max_lift` 只跟 z ⇒
    横向滑移连它都查不到 ⇒ 只有上面那条逻辑核对是决定性的。

      R1 卡在 approach：xy **从未**对准过 ⇒ `approach` 分支**没有任何停滞判据**、也没有重试阶梯
         （对比 `grasp` 有 `MAX_GRASP_TRIES`、`descend` 有 restage）⇒ 结构上必然烧满剩余步数。
      R2 descend 盲区：xy 对准过（⇒ 能进 descend），但终态落在 S2/S3 ⇒ 停滞判据要求 `z_err > Z_TOL`，
         S2（|z_err|≤Z_TOL）与 S3（z_err<−Z_TOL）都**不满足** ⇒ 既进不了 grasp 也不算停滞。
      R3 退路已用满：`n_restages ≥ 2` 或 `unrecoverable` ⇒ 停滞判据**看见了**、阶梯也跑了，是能力上限。
      R4 判据看得见但没救回来：终态在 S1/S4（`z_err > Z_TOL` ⇒ 判据可见）且退路没用满
         ⇒ 要么还没触发（`|dz|` 不够小 / 连续不足 25 步），要么剩余步数不够。
      R0 终态两个条件都满足（S0）⇒ 本该进 grasp；出现即说明前提被破坏（例如 can 被动过），**要查不要藏**。
    """
    if phase_implies_xy_ok and not ever_xy_ok:
        return "RX_can_moved", ("相位串含 descend ⇒ 对**真** can 必然 xy 对准过，而按 can_pos0 重建是"
                                f"从未对准（min={XY_TOL} 以上）⇒ **can 在接管前已被策略移动**，本局重建失效")
    if region_last == "S0_both_ok":
        return "R0_should_have_grasped", "终态 xy 与 z 都满足进 grasp 的条件 ⇒ 与「从未到 grasp」矛盾，需查（can 是否被动过 / 相位机是否在别的相位）"
    if not ever_xy_ok:
        return "R1_approach_stuck", f"xy 从未对准（min ≥ XY_TOL={XY_TOL}）⇒ 停在 approach；approach 无停滞判据、无重试阶梯 ⇒ 结构性烧满"
    if n_restages >= max_restages or unrecoverable:
        return "R3_ladder_exhausted", f"restage={n_restages}（上限 {max_restages}）/ unrecoverable={unrecoverable} ⇒ 停滞判据看见了、退路用满 ⇒ 能力上限"
    if region_last in ALWAYS_INVISIBLE:
        return "R2_descend_blind", f"终态 {region_last}（z_err 不满足 > Z_TOL）⇒ descend 的停滞判据**看不见**，永不 restage/give_up"
    return "R4_visible_not_rescued", f"终态 {region_last} 且 restage={n_restages} 未用满 ⇒ 判据可见但没救回来（剩余步数 {steps_remain}）"


def load_corpus(patterns: list[str]) -> list[dict]:
    """把语料的 eval_summary.json + rollout_actions.npz 摊平成「一局一条」。"""
    eps: list[dict] = []
    dirs: list[str] = []
    for pat in patterns:
        hits = sorted(p for p in globmod.glob(pat) if (Path(p) / "eval_summary.json").is_file())
        if not hits:
            print(f"[warn] 没匹配到产物：{pat}", file=sys.stderr)
        dirs += hits
    if not dirs:
        raise SystemExit("[err] 语料为空（--runs 没匹配到任何 eval_summary.json）")
    for d in dirs:
        dp = Path(d)
        j = json.loads((dp / "eval_summary.json").read_text())
        npz_path = dp / "rollout_actions.npz"
        if not npz_path.is_file():
            print(f"[warn] 缺 rollout_actions.npz，跳过：{d}", file=sys.stderr)
            continue
        z = np.load(npz_path)
        if "source" not in z.files:
            print(f"[warn] npz 里没有 source 列（不是 harness 产物），跳过：{d}", file=sys.stderr)
            continue
        state, source = z["state"], z["source"].astype(np.int8)
        lens = z["episode_lengths"].astype(int)
        if int(lens.sum()) != len(state) or len(source) != len(state):
            raise SystemExit(f"[err] {d}: episode_lengths 之和 {int(lens.sum())} != 帧数 {len(state)}")
        off = 0
        for e, L in zip(j["per_episode"], lens):
            sl = slice(off, off + int(L))
            eps.append(dict(e, _run=dp.name, _state=state[sl], _source=source[sl],
                            _policy_ckpt=j.get("policy_ckpt", "?"),
                            _hand_back=(j.get("harness") or {}).get("hand_back")))
            off += int(L)
    return eps


def reconstruct_can0(seeds: list[int], img_size: int, horizon: int,
                     z_tol_check: float = 5e-4) -> tuple[dict, dict]:
    """用 `env.reset(seed)` 重建 can 初态，并拿语料里记录的 `can_z0` 交叉核对。
    核对不过 ⇒ **抛异常中止**（宁可不出数，也不出一份口径错的分类账）。"""
    from mg_env_reverse import ReverseGraspEnv
    env = ReverseGraspEnv(img_size=img_size, horizon=horizon)
    can0, worst = {}, {"seed": None, "d_can_z0": 0.0}
    for s in sorted(set(seeds)):
        env.reset(seed=int(s))
        p = np.asarray(env.object_pos, dtype=np.float64)
        can0[int(s)] = [float(p[0]), float(p[1]), float(p[2])]
    return can0, worst


def check_can0(can0: dict, eps: list[dict], tol: float = 5e-4) -> dict:
    """拿每局记录里的 `can_z0` 与重建值比。这是整个离线口径的**承重交叉核对**。"""
    ds = [(abs(can0[int(e["seed"])][2] - float(e["can_z0"])), int(e["seed"]), e["_run"])
          for e in eps if int(e["seed"]) in can0 and e.get("can_z0") is not None]
    if not ds:
        return {"ok": False, "n": 0, "max_dz": float("nan"), "why": "语料里没有可比对的 can_z0"}
    bad = [d for d in ds if d[0] > tol]
    mx = max(ds, key=lambda t: t[0])
    return {"ok": not bad, "n": len(ds), "n_mismatch": len(bad), "max_dz": float(mx[0]),
            "max_dz_seed": mx[1], "max_dz_run": mx[2], "tol": tol,
            "mismatches": [{"seed": s, "run": r, "d": float(d)} for d, s, r in bad[:10]]}


def analyze(eps: list[dict], can0: dict, xy_tol: float = XY_TOL, z_tol: float = Z_TOL) -> dict:
    per_ep, excl = [], Counter()
    for e in eps:
        seed = int(e["seed"])
        rec = {"run": e["_run"], "seed": seed, "steps": int(e["steps"]),
               "takeover": bool(e["takeover"]), "takeover_step": int(e["takeover_step"]),
               "success_relaxed": bool(e["success_relaxed"]),
               "expert_phases": list(e.get("expert_phases") or []),
               "n_restages": int(e.get("n_restages", 0)),
               "handback": bool(e.get("handback", False)),
               "unrecoverable": bool(e.get("unrecoverable", False)),
               "n_expert_steps": int(e.get("n_expert_steps", 0))}
        if not e["takeover"]:
            excl["no_takeover"] += 1
            continue
        if seed not in can0:
            excl["seed_not_reconstructed"] += 1
            continue
        phases = rec["expert_phases"]
        if any(p in ("grasp", "lift", "settle", "carry", "place_descend", "release", "retreat")
               for p in phases):
            excl["reached_grasp"] += 1                 # can 被搬走了 ⇒ 初态真值失效
            rec["excluded"] = "reached_grasp"
            per_ep.append(rec)
            continue
        src = np.asarray(e["_source"], dtype=np.int8)
        st = np.asarray(e["_state"], dtype=np.float32)
        m = src == 1
        if int(m.sum()) == 0:
            excl["takeover_but_no_expert_step"] += 1
            continue
        eef = st[m][:, [EEF_X, EEF_Y, EEF_Z]].astype(np.float64)
        c = np.asarray(can0[seed], dtype=np.float64)
        xy = np.maximum(np.abs(eef[:, 0] - c[0]), np.abs(eef[:, 1] - c[1]))
        zz = eef[:, 2] - c[2] - GRASP_OFFSET_Z          # 与 mg_expert.py:227 逐字相同
        dz = np.diff(eef[:, 2])
        s = seg_stats(xy, zz, dz, xy_tol, z_tol)
        rec.update(s)
        rec["n_expert_steps_from_source"] = int(m.sum())
        rec["steps_remain_at_takeover"] = int(e["steps"]) - int(e["takeover_step"])
        # 相位串里出现 descend（或它之后的任何相位 / give_up / restage）⇒ 专家对**真** can 满足过 xy_ok
        implies = ("descend" in phases) or rec["n_restages"] > 0 or ("give_up" in phases)
        rec["phase_implies_xy_ok"] = bool(implies)
        code, why = klass_stuck(bool(s["ever_xy_ok"]), s["region_last"], rec["n_restages"],
                                rec["unrecoverable"], rec["steps_remain_at_takeover"],
                                phase_implies_xy_ok=bool(implies))
        rec["klass"], rec["klass_why"] = code, why
        # 独立佐证（不参与判定，只是让「can 动过」这件事在报告里可查）
        rec["max_lift_cm"] = e.get("max_lift_cm")
        rec["min_dist_to_target_mm"] = (None if e.get("min_dist_to_target_xy") is None
                                        else round(float(e["min_dist_to_target_xy"]) * 1000, 1))
        per_ep.append(rec)
    return {"per_episode": per_ep, "excluded": dict(excl)}


def summarize(res: dict) -> dict:
    pe = res["per_episode"]
    ng_all = [e for e in pe if "klass" in e]
    rx = [e for e in ng_all if e["klass"] == "RX_can_moved"]
    ng = [e for e in ng_all if e["klass"] != "RX_can_moved"]     # **可信子集**：can 未被策略移动过
    rg = [e for e in pe if e.get("excluded") == "reached_grasp"]
    kc = Counter(e["klass"] for e in ng)
    rc = Counter()
    for e in ng:
        for k, v in e["region_counts"].items():
            rc[k] += v
    nsteps = int(sum(e["n_steps"] for e in ng))
    succ = int(sum(1 for e in ng if e["success_relaxed"]))
    out = {
        "n_episodes_total": len(pe) + sum(v for k, v in res["excluded"].items() if k == "no_takeover"),
        "n_takeover": len(ng_all) + len(rg),
        "n_never_grasp": len(ng_all), "n_reached_grasp_excluded": len(rg),
        # ── 效度门（承重）：can 在接管前被策略移动过 ⇒ 离线重建失效，剔出全部几何统计 ──
        "n_never_grasp_trustworthy": len(ng),
        "n_never_grasp_can_moved": len(rx),
        "frac_can_moved_of_never_grasp": (round(len(rx) / len(ng_all), 4) if ng_all else None),
        "wilson_can_moved": [round(x, 1) for x in wilson(len(rx), len(ng_all))],
        "can_moved_seeds": sorted({f"{e['run']}/{e['seed']}" for e in rx}),
        "can_moved_max_lift_cm": [e.get("max_lift_cm") for e in rx],
        "validity_rule": ("相位串含 descend / restage>0 / 含 give_up ⇒ 专家对**真** can 满足过 xy_ok；"
                          "若按 can_pos0 重建出 ever_xy_ok=False ⇒ 逻辑矛盾 ⇒ can 已被移动 ⇒ 剔出"),
        "note_low_power": (f"可信子集只有 {len(ng)} 局（<{LOW_POWER_N} ⇒ `LOW_POWER`）"
                           if len(ng) < LOW_POWER_N else f"可信子集 {len(ng)} 局"),
        "excluded": res["excluded"],
        "klass_counts": {k: int(v) for k, v in sorted(kc.items())},
        "klass_wilson": {k: [round(x, 1) for x in wilson(v, len(ng))] for k, v in sorted(kc.items())},
        "low_power_klass": sorted(k for k, v in kc.items() if v < LOW_POWER_N),
        "region_step_counts": {k: int(rc.get(k, 0)) for k in REGION_ORDER},
        "region_step_frac": ({k: round(rc.get(k, 0) / nsteps, 4) for k in REGION_ORDER}
                             if nsteps else {k: None for k in REGION_ORDER}),
        "n_expert_steps_never_grasp": nsteps,       # 只数**可信子集**（RX 的几何量是错的，不许混进来）
        "n_expert_steps_can_moved": int(sum(e["n_steps"] for e in rx)),
        "frac_steps_always_invisible": (round(sum(rc.get(k, 0) for k in ALWAYS_INVISIBLE) / nsteps, 4)
                                        if nsteps else None),
        "frac_steps_stall_could_fire": (round(sum(e["frac_stall_could_fire"] * e["n_steps"]
                                                  for e in ng) / nsteps, 4) if nsteps else None),
        "n_never_xy_ok": int(sum(1 for e in ng if not e["ever_xy_ok"])),
        "n_never_in_band": int(sum(1 for e in ng if not e["ever_in_band"])),
        "xy_err_min_over_ng": (float(min(e["xy_err_min"] for e in ng)) if ng else float("nan")),
        "xy_err_last_median": (float(np.median([e["xy_err_last"] for e in ng])) if ng else float("nan")),
        "z_err_last_median": (float(np.median([e["z_err_last"] for e in ng])) if ng else float("nan")),
        "tail_run_invisible_median": (float(np.median([e["tail_run_stall_invisible"] for e in ng]))
                                      if ng else float("nan")),
        "n_never_grasp_relaxed_success": succ,
        "a2_if_only_never_grasp": (round(succ / len(ng), 4) if ng else None),
        "n_never_grasp_relaxed_success_all": int(sum(1 for e in ng_all if e["success_relaxed"])),
        "wilson_never_grasp_success": [round(x, 1) for x in wilson(succ, len(ng))],
        "constants": {"XY_TOL": XY_TOL, "Z_TOL": Z_TOL, "GRASP_OFFSET_Z": GRASP_OFFSET_Z,
                      "PRE_HEIGHT": PRE_HEIGHT, "DESCEND_STALL_DZ": DESCEND_STALL_DZ,
                      "DESCEND_MAX_RESTAGES": DESCEND_MAX_RESTAGES,
                      "source": "全部 import 自 code/mg_expert.py（坑 67：常数不重打字面量）"},
    }
    return out


def render_md(card: dict) -> str:
    s = card["summary"]
    L = ["# 「专家为什么到不了 `grasp`」· 离线分类账（零 GPU 推理）", "",
         f"* 生成时间：{card['generated']}（`code/mg_diag_nograsp.py`）",
         f"* 语料：{len(card['corpus_dirs'])} 个产物目录 / {s['n_episodes_total']} 局；"
         f"策略 `{card['policy_jobs']}`（**好 seed 1000**）",
         f"* can 初态重建的交叉核对：{'✅ 过' if card['can0_check']['ok'] else '❌ 不过'}"
         f"（{card['can0_check']['n']} 局，`max|Δcan_z0| = {card['can0_check']['max_dz']:.2e}`，"
         f"容差 {card['can0_check']['tol']:.0e}）",
         f"* 常数（全部 import 自 `code/mg_expert.py`）：{json.dumps(s['constants'], ensure_ascii=False)}",
         "",
         "## ⚠️ 三条诚实标注（不许摘）",
         "1. 盘上**所有**带接管的语料都出自**好 seed 1000**；8A 跑的是**坏 seed 2000** ⇒ 本账只能读成"
         "**机理的存在性与形状**，不能读成 8A 的产出率。",
         "2. 只统计**从未到 `grasp`** 的片段（进过 grasp 后 can 被搬走、初态真值失效）；"
         f"被排除的局数 = {s['n_reached_grasp_excluded']}。",
         f"3. 样本量**很小**：未到 grasp 共 {s['n_never_grasp']} 局，其中 {s['n_never_grasp_can_moved']} 局被效度门剔出"
         f" ⇒ 真正能用来算几何的只有 **{s['n_never_grasp_trustworthy']} 局**"
         + (f"（<{LOW_POWER_N} ⇒ **整份账都是 `LOW_POWER`**）" if s['n_never_grasp_trustworthy'] < LOW_POWER_N
            else f"（≥{LOW_POWER_N}，但每个格子仍分别判 `LOW_POWER`）") + "。"
         f"每个占比都带 Wilson 区间；n<{LOW_POWER_N} 的格子额外打标：{s['low_power_klass'] or '无'}。"
         "**⇒ 本账只能用来定『该修专家的哪一段』，不能用来定效应量。**",
         "",
         "## 〇、效度门：**can 在接管前就被策略移动了**（本账最重要的一条读数）", "",
         f"* 判据（`{s['validity_rule']}`）",
         f"* 未到 grasp 的 {s['n_never_grasp']} 局里，**{s['n_never_grasp_can_moved']} 局**触发矛盾 ⇒ "
         f"占 {100*(s['frac_can_moved_of_never_grasp'] or 0):.1f}%"
         f"（Wilson [{s['wilson_can_moved'][0]:.1f}, {s['wilson_can_moved'][1]:.1f}]）⇒ "
         f"**几何统计只按剩下的 {s['n_never_grasp_trustworthy']} 局算**（`{s['note_low_power']}`）。",
         f"* 这些局的 `max_lift_cm`（独立佐证，只跟 z、查不到横向滑移）：{s['can_moved_max_lift_cm']}",
         f"* 触发矛盾的局：{s['can_moved_seeds']}",
         "* ⇒ **离线路线到此为止**：盘上的 npz 只存了 `state[:,0:3]=eef`，**没有逐步 can 位姿**，"
         "所以「can 被动过」这件事只能被**检测**、不能被**修正**。",
         "* ⇒ 能修正它的只有采集器：`code/mg_collect_corr.py` 的 `descend_diag()` 每步读**当时**的 "
         "`env.object_pos`（不是初态），并另存 `can_at_takeover` ⇒ **格 8A 当晚就能给出无偏的同一份分类账**。",
         "",
         "## 一、归因分布（相位无关；**只按可信子集**）", "",
         "| 代码 | 含义 | 局数 | 占未到 grasp | Wilson95 |", "|:--|:--|--:|--:|:--|"]
    meaning = {
        "R0_should_have_grasped": "终态两条件都满足 ⇒ 本该进 grasp（**出现即要查**）",
        "R1_approach_stuck": "xy **从未**对准 ⇒ 停在 `approach`（该相位**无**停滞判据、**无**重试阶梯）",
        "R2_descend_blind": "进了 descend 但终态在 S2/S3 ⇒ 停滞判据要 `z_err>Z_TOL`，**看不见**",
        "R3_ladder_exhausted": "restage 用满 / unrecoverable ⇒ 判据看见了、退路跑完了（能力上限）",
        "R4_visible_not_rescued": "终态在 S1/S4（判据可见）且退路没用满 ⇒ 没触发或步数不够",
    }
    ng = max(1, s["n_never_grasp_trustworthy"])
    for k in sorted(meaning):
        v = s["klass_counts"].get(k, 0)
        lo, hi = s["klass_wilson"].get(k, [float("nan")] * 2)
        flag = " ⚠️`LOW_POWER`" if k in s["low_power_klass"] else ""
        L.append(f"| `{k}` | {meaning[k]} | {v} | {100*v/ng:.1f}% | [{lo:.1f}, {hi:.1f}]{flag} |")
    L += ["", f"## 二、逐步几何区的分布（**可信子集** {s['n_never_grasp_trustworthy']} 局，共 "
              f"{s['n_expert_steps_never_grasp']} 个专家步）", "",
          "| 区 | 定义（`xy_err=max(|dx|,|dy|)`、`z_err=eef_z-can_z-GRASP_OFFSET_Z`） | 步数 | 占比 | 停滞判据 |",
          "|:--|:--|--:|--:|:--|"]
    defs = {
        "S0_both_ok": f"`xy<{XY_TOL}` ∧ `|z_err|≤{Z_TOL}` ⇒ 本该进 grasp",
        "S1_above_xyoff": f"`z_err>{Z_TOL}` ∧ `xy≥{XY_TOL}`",
        "S2_band_xyoff": f"`|z_err|≤{Z_TOL}` ∧ `xy≥{XY_TOL}` ⇒ **盲区**",
        "S3_below_band": f"`z_err<-{Z_TOL}` ⇒ **盲区**",
        "S4_above_xyok": f"`z_err>{Z_TOL}` ∧ `xy<{XY_TOL}`",
    }
    vis = {"S0_both_ok": "—（已满足进 grasp）", "S1_above_xyoff": "**相位依赖**：descend 里可见、approach 里不可见",
           "S2_band_xyoff": "**永远看不见**", "S3_below_band": "**永远看不见**", "S4_above_xyok": "可见（若 |dz| 够小）"}
    tot = max(1, s["n_expert_steps_never_grasp"])
    for k in REGION_ORDER:
        v = s["region_step_counts"][k]
        L.append(f"| `{k}` | {defs[k]} | {v} | {100*v/tot:.1f}% | {vis[k]} |")
    inv = s["frac_steps_always_invisible"]
    fire = s["frac_steps_stall_could_fire"]
    inv_txt = "n/a" if inv is None else f"{100*inv:.1f}%"
    fire_txt = "n/a" if fire is None else f"{100*fire:.1f}%"
    rsc, tot2 = s["region_step_counts"], max(1, s["n_expert_steps_never_grasp"])
    xy_ok_steps = rsc["S0_both_ok"] + rsc["S4_above_xyok"]       # xy 对准（不论 z）
    band_steps = rsc["S0_both_ok"] + rsc["S2_band_xyoff"]        # z 在带内（不论 xy）
    both = rsc["S0_both_ok"]                                     # **两个条件同时**满足 = 能进 grasp
    L += ["", f"* **无论相位都看不见**的步占比（S2+S3）：{inv_txt}",
          f"* 停滞判据**条件成立**的步占比：{fire_txt}",
          "",
          "**最锋利的一条（进 grasp 的两个条件几乎不同时成立）**：",
          f"* xy 对准过的步（S0+S4）：{xy_ok_steps} / {tot2} = {100*xy_ok_steps/tot2:.1f}%",
          f"* z 在抓取带内的步（S0+S2）：{band_steps} / {tot2} = {100*band_steps/tot2:.1f}%",
          f"* **两者同时成立**（S0，= 真正能进 grasp 的窗口）：**{both} / {tot2} = {100*both/tot2:.2f}%**",
          f"* ⇒ xy 对准的 {xy_ok_steps} 步里只有 {both} 步高度也对（{100*both/max(1,xy_ok_steps):.1f}%）；"
          f"高度在带内的 {band_steps} 步里只有 {both} 步 xy 也对（{100*both/max(1,band_steps):.1f}%）",
          "* ⇒ 含义：`descend` 的进入条件是「xy 已对准」，但**下降过程中 xy 会漂出去**，"
          "而漂出去之后**没有任何机制能在 z 带内重新对准 xy**（restage 只在 `z_err>Z_TOL` 时才可能触发）",
          "",
          f"* xy **从未**对准的局数：{s['n_never_xy_ok']} / {s['n_never_grasp_trustworthy']}（可信子集）",
          f"* 从未进过抓取带的局数：{s['n_never_in_band']} / {s['n_never_grasp_trustworthy']}",
          f"* `xy_err` 的最小值（全部未到 grasp 的局里最小的那个）：{s['xy_err_min_over_ng']*1000:.2f} mm"
          f"（`XY_TOL` = {XY_TOL*1000:.0f} mm）",
          f"* 终态 `xy_err` 中位：{s['xy_err_last_median']*1000:.2f} mm；终态 `z_err` 中位："
          f"{s['z_err_last_median']*1000:.2f} mm",
          f"* 收尾「停滞判据看不见」的连续步数中位：{s['tail_run_invisible_median']:.0f}",
          f"* 这些局的放宽成功率：**{s['n_never_grasp_relaxed_success']}/{s['n_never_grasp_trustworthy']}**（可信子集）"
          f"（Wilson [{s['wilson_never_grasp_success'][0]:.1f}, {s['wilson_never_grasp_success'][1]:.1f}]）",
          f"* 对照：**含** RX 的全部未到 grasp 局的放宽成功率 = "
          f"{s['n_never_grasp_relaxed_success_all']}/{s['n_never_grasp']}（RX 的几何量无效，但成功/失败是真值）",
          "", "## 三、每局明细（**从未到 grasp** 的全部局；`RX_can_moved` 的几何列**不可信**，只为可查而列）", "",
          "| run | seed | steps | 接管@ | 专家步 | 剩余步 | restage | max_lift(cm) | 终态区 | 曾xy对准 | xy_min(mm) | 终态xy(mm) | 终态z(mm) | 归因 | 放宽 |",
          "|:--|--:|--:|--:|--:|--:|--:|--:|:--|:--|--:|--:|--:|:--|:--|"]
    for e in sorted((x for x in card["per_episode"] if "klass" in x),
                    key=lambda x: (x["klass"], x["run"], x["seed"])):
        bad = e["klass"] == "RX_can_moved"
        f3 = (lambda v: f"~~{v*1000:.1f}~~" if bad else f"{v*1000:.1f}")
        L.append(f"| {e['run'].replace('s5_1_handback_rev_test20_k10', 'hb')} | {e['seed']} | {e['steps']} "
                 f"| {e['takeover_step']} | {e['n_steps']} | {e['steps_remain_at_takeover']} | {e['n_restages']} "
                 f"| {e.get('max_lift_cm')} | `{e['region_last']}` | {'是' if e['ever_xy_ok'] else '**否**'} "
                 f"| {f3(e['xy_err_min'])} | {f3(e['xy_err_last'])} | {f3(e['z_err_last'])} | `{e['klass']}` "
                 f"| {'✅' if e['success_relaxed'] else '❌'} |")
    L += ["", "## 四、这份账**不改任何门**", "",
          "A1/A2/A3、三条过滤、B1/B2/B3、D1~D4 一条都不读它。用途只有一个：8A 若写 `runs/s8a.HELD`，",
          "当晚就能拿这些数说清「该修专家的哪一段」，不必再开一档去复现失败。",
          "", "## 五、复现", "", "```bash",
          "$MG_PY code/mg_diag_nograsp.py --selftest",
          "$MG_PY code/mg_diag_nograsp.py --runs '%s' --out %s" % (card["corpus_glob"][0], card["out_stem"]),
          "```", ""]
    return "\n".join(L)


# ─────────────────────────────── 自测（纯 CPU、零仿真）───────────────────────────────
def selftest() -> int:
    n_ok = n_bad = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal n_ok, n_bad
        if cond:
            n_ok += 1
        else:
            n_bad += 1
            print(f"  ❌ {name}")

    chk("STATE_NAMES 下标钉住（eef_x/y/z 与 gripper_width）",
        STATE_NAMES[EEF_X] == "eef_x" and STATE_NAMES[EEF_Y] == "eef_y"
        and STATE_NAMES[EEF_Z] == "eef_z" and STATE_NAMES[WIDTH] == "gripper_width")

    # region_of 的边界（进 grasp 用严格 < ⇒ 取反是 >=）
    chk("region：xy 压线内侧 0.0079 ∧ z 在带内 ⇒ S0", region_of(0.0079, 0.0) == "S0_both_ok")
    chk("region：xy 压线 0.008 == XY_TOL ∧ z 在带内 ⇒ S2（压线**算**没对准）",
        region_of(XY_TOL, 0.0) == "S2_band_xyoff")
    chk("region：z 压线 |0.010| == Z_TOL ⇒ 算带内", region_of(0.02, Z_TOL) == "S2_band_xyoff")
    chk("region：z=0.011 > Z_TOL ∧ xy 没对准 ⇒ S1", region_of(0.02, Z_TOL + 1e-3) == "S1_above_xyoff")
    chk("region：z=0.011 > Z_TOL ∧ xy 对准 ⇒ S4", region_of(0.001, Z_TOL + 1e-3) == "S4_above_xyok")
    chk("region：z=-0.011 < -Z_TOL ⇒ S3（无论 xy）", region_of(0.001, -Z_TOL - 1e-3) == "S3_below_band")
    chk("region：z=-0.010 == -Z_TOL ⇒ 带内（|z|≤Z_TOL）", region_of(0.02, -Z_TOL) == "S2_band_xyoff")
    chk("region：负 z 在带内 ∧ xy 对准 ⇒ S0", region_of(0.001, -0.005) == "S0_both_ok")

    # stall_can_fire
    chk("stall：S2 ⇒ 永远 False（z_err 不满足 > Z_TOL）",
        stall_can_fire("S2_band_xyoff", 0.0) is False)
    chk("stall：S3 ⇒ 永远 False", stall_can_fire("S3_below_band", 0.0) is False)
    chk("stall：S0 ⇒ False（已满足进 grasp，不该算停滞）", stall_can_fire("S0_both_ok", 0.0) is False)
    chk("stall：S4 ∧ |dz|=0 ⇒ True", stall_can_fire("S4_above_xyok", 0.0) is True)
    chk("stall：S4 ∧ |dz|=1e-4 == DESCEND_STALL_DZ ⇒ False（判据是严格 <）",
        stall_can_fire("S4_above_xyok", DESCEND_STALL_DZ) is False)
    chk("stall：S4 ∧ dz=None（第一步）⇒ False", stall_can_fire("S4_above_xyok", None) is False)
    chk("stall：S1 ∧ |dz|=0 ⇒ True（但**相位依赖**：approach 里不跑判据）",
        stall_can_fire("S1_above_xyoff", 0.0) is True)
    chk("ALWAYS_INVISIBLE 恰好是 S2/S3", ALWAYS_INVISIBLE == {"S2_band_xyoff", "S3_below_band"})

    # seg_stats
    xy = np.array([0.02, 0.02, 0.02, 0.005])
    zz = np.array([0.05, 0.005, 0.005, 0.005])
    dz = np.array([-0.045, 0.0, 0.0])
    s = seg_stats(xy, zz, dz)
    chk("seg：4 步 ⇒ n_steps=4", s["n_steps"] == 4)
    # 逐步：(0.02,0.05)->S1、(0.02,0.005)->S2、(0.02,0.005)->S2、(0.005,0.005)->S0
    chk("seg：区计数 S1=1 / S2=2 / S0=1（0.02≥XY_TOL 算没对准、0.005<XY_TOL 算对准）",
        s["region_counts"]["S1_above_xyoff"] == 1 and s["region_counts"]["S2_band_xyoff"] == 2
        and s["region_counts"]["S0_both_ok"] == 1)
    chk("seg：ever_xy_ok=True（最后一步 0.005 < XY_TOL）", s["ever_xy_ok"] is True)
    chk("seg：ever_in_band=True", s["ever_in_band"] is True)
    chk("seg：region_last=S0_both_ok", s["region_last"] == "S0_both_ok")
    chk("seg：xy_err_min=0.005 / max=0.02", s["xy_err_min"] == 0.005 and s["xy_err_max"] == 0.02)
    chk("seg：frac_always_invisible = 2/4（第 2、3 步是 S2）",
        abs(s["frac_always_invisible"] - 0.5) < 1e-12)
    chk("seg：收尾连续「停滞判据看不见」= 4（第 1 步 dz=None、第 2/3 步是 S2、第 4 步是 S0 ⇒ 全不满足）",
        s["tail_run_stall_invisible"] == 4)
    chk("seg：若末步真触发停滞则收尾游程归零（S4 ∧ dz=0 ⇒ 可见）",
        seg_stats(np.array([0.02, 0.001]), np.array([0.005, 0.05]), np.array([0.0]))
        ["tail_run_stall_invisible"] == 0)
    chk("seg：空输入 ⇒ n_steps=0 且不炸", seg_stats(np.array([]), np.array([]), np.array([]))["n_steps"] == 0)
    s2 = seg_stats(np.array([0.02, 0.02]), np.array([0.005, 0.005]), np.array([0.0]))
    chk("seg：全 S2 ⇒ frac_always_invisible=1.0、ever_xy_ok=False",
        s2["frac_always_invisible"] == 1.0 and s2["ever_xy_ok"] is False)

    # klass_stuck 的五条分支
    chk("klass：R1（xy 从未对准）优先于终态区", klass_stuck(False, "S2_band_xyoff", 0, False, 300)[0]
        == "R1_approach_stuck")
    chk("klass：R1 的文案点名 approach 无停滞判据", "approach" in klass_stuck(False, "S1_above_xyoff", 0, False, 300)[1])
    chk("klass：R3（restage 用满）优先于 R2", klass_stuck(True, "S2_band_xyoff", DESCEND_MAX_RESTAGES, False, 300)[0]
        == "R3_ladder_exhausted")
    chk("klass：R3（unrecoverable）也算退路用满", klass_stuck(True, "S2_band_xyoff", 0, True, 300)[0]
        == "R3_ladder_exhausted")
    chk("klass：R2（终态 S2、退路没用满）", klass_stuck(True, "S2_band_xyoff", 1, False, 300)[0]
        == "R2_descend_blind")
    chk("klass：R2 也吃 S3", klass_stuck(True, "S3_below_band", 0, False, 300)[0] == "R2_descend_blind")
    chk("klass：R4（终态 S4、退路没用满）", klass_stuck(True, "S4_above_xyok", 1, False, 300)[0]
        == "R4_visible_not_rescued")
    chk("klass：R4 也吃 S1（相位依赖，但退路没用满）", klass_stuck(True, "S1_above_xyoff", 0, False, 300)[0]
        == "R4_visible_not_rescued")
    chk("klass：R0（终态 S0 ⇒ 前提被破坏，要查不要藏）",
        klass_stuck(True, "S0_both_ok", 0, False, 300)[0] == "R0_should_have_grasped")
    chk("klass：R0 优先于 R1（终态 S0 就算 xy 从未对准也要报矛盾）",
        klass_stuck(False, "S0_both_ok", 0, False, 300)[0] == "R0_should_have_grasped")

    # ── 效度门（承重）：相位串蕴含 xy_ok ⇒ 与重建矛盾时判 RX_can_moved，不许硬套 R1 ──
    chk("效度门：相位蕴含 xy_ok ∧ 重建说从未对准 ⇒ RX_can_moved（**优先于 R1**）",
        klass_stuck(False, "S1_above_xyoff", 0, False, 300, phase_implies_xy_ok=True)[0] == "RX_can_moved")
    chk("效度门：RX 的文案点名「can 在接管前已被策略移动」",
        "移动" in klass_stuck(False, "S2_band_xyoff", 2, True, 300, phase_implies_xy_ok=True)[1])
    chk("效度门：restage>0 也走 RX（restage 只可能在 descend 里发生）",
        klass_stuck(False, "S1_above_xyoff", 2, False, 300, phase_implies_xy_ok=True)[0] == "RX_can_moved")
    chk("效度门：重建说**对准过** ⇒ 不矛盾 ⇒ 仍按 R2/R4 归因",
        klass_stuck(True, "S2_band_xyoff", 0, False, 300, phase_implies_xy_ok=True)[0] == "R2_descend_blind")
    chk("效度门：默认关掉（phase_implies_xy_ok=False）⇒ 行为与加门前一致",
        klass_stuck(False, "S1_above_xyoff", 0, False, 300)[0] == "R1_approach_stuck")

    # wilson
    chk("wilson：n=0 ⇒ (nan, nan) 不许 0 兜底", math.isnan(wilson(0, 0)[0]))
    lo, hi = wilson(0, 12)
    chk("wilson：0/12 ⇒ 上界 <40%（0 成功也能给出信息）", hi < 40.0 and lo == 0.0)
    lo, hi = wilson(5, 6)
    chk("wilson：5/6 ⇒ 下界 >30%", lo > 30.0)

    # summarize 的合成口径
    fake = {"per_episode": [
        {"klass": "R1_approach_stuck", "n_steps": 100, "success_relaxed": False, "ever_xy_ok": False,
         "ever_in_band": False, "region_counts": {k: 0 for k in REGION_ORDER},
         "xy_err_min": 0.02, "xy_err_last": 0.03, "z_err_last": 0.1, "tail_run_stall_invisible": 100,
         "frac_stall_could_fire": 0.0, "excluded": None},
        {"klass": "R2_descend_blind", "n_steps": 200, "success_relaxed": True, "ever_xy_ok": True,
         "ever_in_band": True, "region_counts": dict(zip(REGION_ORDER, [0, 0, 200, 0, 0])),
         "xy_err_min": 0.001, "xy_err_last": 0.012, "z_err_last": 0.002, "tail_run_stall_invisible": 200,
         "frac_stall_could_fire": 0.0, "excluded": None},
        {"excluded": "reached_grasp"}],
        "excluded": {"no_takeover": 5, "reached_grasp": 1}}
    fake["per_episode"][0]["region_counts"] = dict(zip(REGION_ORDER, [0, 100, 0, 0, 0]))
    sm = summarize(fake)
    chk("summarize：n_never_grasp=2 / 排除 reached_grasp=1", sm["n_never_grasp"] == 2
        and sm["n_reached_grasp_excluded"] == 1)
    chk("summarize：klass 计数 R1=1 / R2=1", sm["klass_counts"]["R1_approach_stuck"] == 1
        and sm["klass_counts"]["R2_descend_blind"] == 1)
    chk("summarize：区步数 S1=100 / S2=200、总 300", sm["region_step_counts"]["S1_above_xyoff"] == 100
        and sm["region_step_counts"]["S2_band_xyoff"] == 200
        and sm["n_expert_steps_never_grasp"] == 300)
    chk("summarize：frac_always_invisible = 200/300（报告里按 4 位小数存 ⇒ 用 1e-3 容差）",
        abs(sm["frac_steps_always_invisible"] - 200 / 300) < 1e-3)
    chk("summarize：frac_stall_could_fire = 0（两局都 0）", sm["frac_steps_stall_could_fire"] == 0.0)
    chk("summarize：n_never_xy_ok=1 / n_never_in_band=1", sm["n_never_xy_ok"] == 1
        and sm["n_never_in_band"] == 1)
    chk("summarize：low_power 标（每类都 <5）", set(sm["low_power_klass"])
        == {"R1_approach_stuck", "R2_descend_blind"})
    chk("summarize：放宽成功 1/2 ⇒ a2_if_only_never_grasp=0.5", sm["a2_if_only_never_grasp"] == 0.5)
    chk("summarize：空 ⇒ 不炸且占比是 None", summarize({"per_episode": [], "excluded": {}})
        ["frac_steps_always_invisible"] is None)

    # summarize 的可信子集切分（RX 必须被剔出**全部**几何统计）
    fake2 = {"per_episode": [
        dict(fake["per_episode"][1]),                                   # R2，可信，200 步全 S2
        {"klass": "RX_can_moved", "n_steps": 999, "success_relaxed": True, "ever_xy_ok": False,
         "ever_in_band": True, "region_counts": dict(zip(REGION_ORDER, [0, 999, 0, 0, 0])),
         "xy_err_min": 0.34, "xy_err_last": 0.35, "z_err_last": 0.05,
         "tail_run_stall_invisible": 999, "frac_stall_could_fire": 0.0,
         "run": "hb_rep2", "seed": 7010, "max_lift_cm": 13.8},
        {"excluded": "reached_grasp"}],
        "excluded": {"no_takeover": 5, "reached_grasp": 1}}
    sm2 = summarize(fake2)
    chk("summarize：n_never_grasp=2（含 RX）而 trustworthy=1", sm2["n_never_grasp"] == 2
        and sm2["n_never_grasp_trustworthy"] == 1 and sm2["n_never_grasp_can_moved"] == 1)
    chk("summarize：RX 的 999 步**没有**混进几何统计（总步数仍是 200）",
        sm2["n_expert_steps_never_grasp"] == 200 and sm2["n_expert_steps_can_moved"] == 999)
    chk("summarize：klass_counts 里没有 RX（它不是归因，是效度判定）",
        "RX_can_moved" not in sm2["klass_counts"] and sm2["klass_counts"] == {"R2_descend_blind": 1})
    chk("summarize：frac_can_moved = 1/2", abs(sm2["frac_can_moved_of_never_grasp"] - 0.5) < 1e-9)
    chk("summarize：can_moved_seeds 可查（run/seed）", sm2["can_moved_seeds"] == ["hb_rep2/7010"])
    chk("summarize：可信子集 <5 ⇒ note_low_power 打标", "LOW_POWER" in sm2["note_low_power"])
    chk("summarize：成功数分两口径（可信 1 vs 含 RX 2）", sm2["n_never_grasp_relaxed_success"] == 1
        and sm2["n_never_grasp_relaxed_success_all"] == 2)
    chk("summarize：validity_rule 写清了判据来源", "descend" in sm2["validity_rule"])
    chk("summarize：空 ⇒ n_never_grasp_trustworthy=0 且 frac 是 None",
        summarize({"per_episode": [], "excluded": {}})["frac_can_moved_of_never_grasp"] is None)
    chk("summarize：常数出处写了 mg_expert", "mg_expert" in sm["constants"]["source"])

    print(f"[selftest] {n_ok} passed, {n_bad} failed")
    return 0 if n_bad == 0 else 1


# ─────────────────────────────── 主流程 ───────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="*", default=[DEFAULT_CORPUS], help="语料目录的 glob（可多个）")
    ap.add_argument("--out", default=str(RUNS / "_diag" / "nograsp_corpus"),
                    help="产物 stem（写 <out>.md / <out>.json；相对路径按仓根解析）")
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--horizon", type=int, default=HORIZON,
                    help="重建 can 初态用的 horizon；必须与语料一致（评测恒 400）")
    ap.add_argument("--no-env", action="store_true",
                    help="不建仿真（只跑不需要 can 初态的部分；用于快速冒烟）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    eps = load_corpus(args.runs)
    # ckpt 形如 <MG>/runs/<JOB>/checkpoints/<STEP>/pretrained_model ⇒ 要的是 <JOB>（parents[2]）
    ck = sorted({Path(e["_policy_ckpt"]).parents[2].name
                 for e in eps if e["_policy_ckpt"] != "?"
                 and len(Path(e["_policy_ckpt"]).parents) > 2})
    print(f"[nograsp] 语料 {len(eps)} 局 / {len(set(e['_run'] for e in eps))} 个目录 / 策略 {ck}")
    takeover = [e for e in eps if e["takeover"]]
    nograsp0 = [e for e in takeover
                if not any(p in ("grasp", "lift", "settle", "carry", "place_descend", "release", "retreat")
                           for p in (e.get("expert_phases") or []))]
    print(f"[nograsp] 接管 {len(takeover)} 局；其中相位串里**没有** grasp 及其后相位 = {len(nograsp0)} 局")
    seeds = sorted({int(e["seed"]) for e in eps})
    if args.no_env:
        print("[nograsp] --no-env：跳过 can 初态重建与全部几何量（只出计数）")
        can0, chkres = {}, {"ok": None, "n": 0, "max_dz": float("nan"), "tol": 5e-4,
                            "why": "--no-env"}
    else:
        print(f"[nograsp] 重建 can 初态：{len(seeds)} 个 seed（{seeds[0]}..{seeds[-1]}），horizon={args.horizon}")
        can0, _ = reconstruct_can0(seeds, args.img_size, args.horizon)
        chkres = check_can0(can0, eps)
        print(f"[nograsp] 交叉核对 can_z0：{'✅' if chkres['ok'] else '❌'} "
              f"{chkres['n']} 局、max|Δ| = {chkres['max_dz']:.2e}（容差 {chkres['tol']:.0e}）")
        if not chkres["ok"]:
            print(f"[err] can 初态重建与语料记录的 can_z0 对不上 ⇒ **中止，不出数**：{json.dumps(chkres, ensure_ascii=False)}",
                  file=sys.stderr)
            return 3
    res = analyze(eps, can0)
    sm = summarize(res)
    card = {"kind": "nograsp_taxonomy", "generated": f"{datetime.now():%F %T}",
            "corpus_glob": list(args.runs),
            "out_stem": str(args.out),
            "corpus_dirs": sorted({e["_run"] for e in eps}),
            "policy_jobs": ck, "horizon": int(args.horizon),
            "can0": {str(k): v for k, v in can0.items()}, "can0_check": chkres,
            "summary": sm, "analyze": {k: v for k, v in res.items() if k != "per_episode"},
            "per_episode": res["per_episode"],
            "note": "**只透明、不进任何门**；语料是好 seed 1000、8A 是坏 seed 2000（见报告 §诚实标注）",
            "versions": {"python": platform.python_version(), "numpy": np.__version__}}
    out = Path(args.out)
    if not out.is_absolute():
        out = MG_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.with_suffix(".json")).write_text(json.dumps(card, indent=2, ensure_ascii=False, default=str))
    md = render_md(card)
    (out.with_suffix(".md")).write_text(md)
    print(f"[nograsp] 归因分布：{json.dumps(sm['klass_counts'], ensure_ascii=False)}")
    print(f"[nograsp] 逐步区分布：{json.dumps(sm['region_step_counts'], ensure_ascii=False)}")
    print(f"[nograsp] ⚠️ 效度门：{sm['n_never_grasp_can_moved']}/{sm['n_never_grasp']} 局的 can **在接管前已被策略移动**"
          f"（相位串含 descend ⇒ 对真 can 必然 xy 对准过，与重建矛盾）⇒ 几何统计只按"
          f"**可信子集 {sm['n_never_grasp_trustworthy']} 局**算")
    print(f"[nograsp] 可信子集：xy 从未对准 {sm['n_never_xy_ok']}/{sm['n_never_grasp_trustworthy']} 局；"
          f"无论相位都看不见的步占比 {sm['frac_steps_always_invisible']}；"
          f"两个条件同时成立（S0）= {sm['region_step_counts']['S0_both_ok']}/{sm['n_expert_steps_never_grasp']} 步")
    print(f"[nograsp] 可信子集的放宽成功 {sm['n_never_grasp_relaxed_success']}/{sm['n_never_grasp_trustworthy']}"
          f"（含 RX 的全部未到 grasp 局：{sm['n_never_grasp_relaxed_success_all']}/{sm['n_never_grasp']}）")
    print(f"[report]  {out}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
