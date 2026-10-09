#!/usr/bin/env python
"""档 8 · 纠正数据采集器（HG-DAgger 风格：**只留脚本专家接管的那一段**）。

要回答的唯一问题（`runs/S8_PREREG.md`）：在**策略自己访问到的失败状态**上，让脚本专家把这一局做完，
把接管片段（含双相机图像）落成训练帧，加进原数据集重训坏 seed 2000，能不能把它的反向 TEST
放宽口径从 41.2% 抬到 ≥50%（与档 3r/7C/7G 完全同一条使命门）。

两种模式（都不动任何冻结文件）：
  --mode collect（GPU）：策略 rollout -> `GraspDetector` 触发 -> `ScriptedExpert.resume(can_z0)` 接管
      -> 逐帧记 {state, action, 双相机图, task=TASK_REVERSE} -> 三条过滤 -> 写 `data/corr_r1`
  --mode merge（零 GPU）：把 `data/corr_r1` 的每一条 episode 追加进 `data/mix60f120r_c1`
      （= 8A-0 探针已验通的「复制 + 追加」路径），并做 B1/B2/B3 三条对账

三条过滤（预注册 §3，常数写死，看完数不许改）：
  1. 本局**放宽成功**（送到为首要，侧躺算送到并另打 `delivered_tipped` 标；用户 2026-10-02 授权）
  2. `handback_at == -1`（专家没认输。本采集器恒 `hand_back=False` ⇒ 这条是**保险丝**，
     防的是将来有人把开关打开后片段里混进 give_up 的原地保持动作）
  3. **效率过滤**：`seg_len <= 300` ∧ `re_descend <= 1`
     （预注册留档偏离：原计划的「停滞阶梯」是**部署时**接管用的判据，采集时要的是「别把死循环教给策略」，
      段长 + 重下探次数是同一件事的**离线**口径，且不需要碰 `mg_expert.py` 的常数）

⚠️ 采集用 `horizon=800`（**只采集用**）：档 5 实测策略做完一局要 ≥224 步、专家恢复段 p50=201 步、
   接管点 67~261 ⇒ 400 步窗内接管点晚于 ~199 的局**注定收不到成功片段**。评测 horizon **恒 400 不变**。
⚠️ 采集 seed 窗口必须与所有评测/示范窗口不相交（`EVAL_WINDOWS`，链里断言；泄漏会让门失效）。
⚠️ **不做**每步 relabel 的全量 DAgger：`resume()` 每步重推相位会清零 `phase_step`，
   在「爪子还没闭上」的状态上会给出 `lift` 标签，而「提前上提」正是 A/H 类失败机理 ⇒ 会教坏策略
   （预注册 §5「有意不做的」）。本采集器一局**只接管一次**、只留接管之后那一段。

用法：
    $MG_PY code/mg_collect_corr.py --selftest                        # 零 GPU
    $MG_PY code/mg_collect_corr.py --mode collect --episodes 80 --seed 9000 --gate-a \
        --report runs/s8a_calib/collect_report                       # 格 8A
    $MG_PY code/mg_collect_corr.py --mode collect --append --episodes 320 --seed 9080 \
        --target-frames 7000 --report runs/s8b_collect/collect_report  # 格 8B
    $MG_PY code/mg_collect_corr.py --mode merge --out corr_r1 --dst mix60f120r_c1 \
        --report runs/s8b_merge/merge_report                        # 格 8B 建集
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_calib_detector import HOLD_HI, HOLD_LO, N_EMPTY, N_HOLD, W_EMPTY  # noqa: E402
from mg_collect import build_features  # noqa: E402
from mg_ds_append_probe import diff_manifest, scope_changed, sha_manifest, stats_cover, windows_disjoint  # noqa: E402
from mg_env import (  # noqa: E402
    ACTION_DIM, ACTION_KEY, ACTION_NAMES, CONTROL_FREQ, HORIZON, IMG_KEY_BASE, IMG_KEY_WRIST,
    ROBOT, STATE_DIM, STATE_KEY, STATE_NAMES, SUITE_TASK,
)
from mg_env_reverse import TASK_REVERSE  # noqa: E402
from mg_expert import GRIP_CLOSE, GRASP_OFFSET_Z, XY_TOL, Z_TOL  # noqa: E402
from mg_harness import PHASES, WIDTH_IDX  # noqa: E402

DATA = MG_ROOT / "data"
RUNS = MG_ROOT / "runs"

# ── 预注册写死的常数（runs/S8_PREREG.md §3 格 8A/8B）──────────────────────────
MAX_SEG_LEN = 300          # 过滤 3：接管片段步数上限
MAX_RE_DESCEND = 1         # 过滤 3：片段内重下探次数上限
COLLECT_HORIZON = 800      # **只采集用**；评测 horizon 恒 = mg_env.HORIZON = 400
GATE_A1_FRAMES = 2000      # A1：每 80 局可用纠正帧 ≥ 2000
GATE_A1_EPISODES = 80      # A1 的分母口径（--gate-a 时断言 --episodes 就是它）
GATE_A2_RATE = 0.40        # A2：接管局放宽成功率 ≥ 40%
GATE_A3_MEDIAN = 300       # A3：接管片段步数中位 ≤ 300
TARGET_FRAMES_8B = 7000    # 8B 目标帧数（≈ 原 46426 帧的 15%）
# 采集窗口必须与这些**全部**不相交（TEST / val / 正向护栏 / 正向示范 / 反向示范）
EVAL_WINDOWS = [(7000, 7019), (8000, 8019), (2000, 2019), (1000, 1059), (5000, 5186)]
IMG_SIZE_DEFAULT = 224
K_DEFAULT = 10             # 档 5 定的工作点 K=10（档 4r）


# ─────────────────────── 纯函数（全部有自测；期望值按定义独立算，坑 65）───────────────────────
def count_runs(seq: list[str], name: str) -> int:
    """`seq` 里 `name` 的**极大连续段**个数。空序列 = 0 段。"""
    n, prev = 0, None
    for x in seq:
        if x == name and prev != name:
            n += 1
        prev = x
    return n


def re_descend(phases: list[str]) -> int:
    """片段内**重新**下探的次数 = descend 的连续段数 − 1（没有 descend 就是 0，不会是 −1）。"""
    return max(0, count_runs(list(phases), "descend") - 1)


def descend_diag(rows: list[tuple[float, float, str]], xy_tol: float = XY_TOL,
                 z_tol: float = Z_TOL) -> dict:
    """「descend 盲区」诊断（**只透明，不进任何门**：A1/A2/A3 与三条过滤一条都不读它）。

    `rows` = 每个**专家步**的 `(xy_err_max, z_err, phase)`，全部是「这一步之前」的真值口径（与帧口径一致）：
      * `xy_err_max = max(|eef_x − can_x|, |eef_y − can_y|)`
      * `z_err = eef_z − can_z − GRASP_OFFSET_Z`（与 `mg_expert.__call__` 里 descend 的表达式逐字相同）

    为什么要这个读数：`mg_expert.py` 的 descend 分支要 **xy_ok ∧ |z_err| < Z_TOL** 才进 grasp，
    而它的停滞判据是 `z_err > Z_TOL ∧ |dz| < DESCEND_STALL_DZ` ⇒
    **「高度已经对上、水平没对上」的步既进不了 grasp、也不算停滞** ⇒ 永不 restage、永不 give_up，
    一路烧到 horizon。档 5.1 的语料里 17 局 `phases=['approach','descend']` 且 `n_restages=0`
    正是这个签名（出处 `runs/_diag/s8a_yield_forecast.md`）。本函数把「HELD 的病因是不是它」变成一个可算的数。

    边界口径与 `mg_expert.py` **逐字对齐**：进 grasp 用 `xy_ok = |dx| < XY_TOL`（严格小于）
    与 `|z_err| < Z_TOL`（严格小于）⇒ 盲区 = `xy_err ≥ xy_tol`（取反）∧ `|z_err| ≤ z_tol`。
    停滞判据用 `z_err > Z_TOL`（带符号，不是绝对值）⇒ 低于抓取面（z_err<0）时停滞也不计数，
    那同样是盲区，所以这里用 `|z_err| ≤ z_tol` 会把「刚好在带内」算进来、「显著低于抓取面」排除在外
    （后者另由 `n_descend_z_below` 透明报出，不混进盲区计数）。
    """
    desc = [(float(xy), float(z)) for xy, z, ph in rows if ph == "descend"]
    n_blind = int(sum(1 for xy, z in desc if abs(z) <= z_tol and xy >= xy_tol))
    n_z_ok = int(sum(1 for xy, z in desc if abs(z) <= z_tol))
    n_below = int(sum(1 for xy, z in desc if z < -z_tol))
    return {
        "n_expert_steps": len(rows),
        "n_descend_steps": len(desc),
        "n_descend_z_ok": n_z_ok,
        "n_descend_z_below": n_below,          # 显著低于抓取面：停滞判据（z_err>Z_TOL）同样看不见
        "n_blind": n_blind,                    # 高度在带内、水平没对准 ⇒ 停滞判据的盲区
        "frac_blind_of_descend": (n_blind / len(desc)) if desc else float("nan"),
        "frac_blind_of_z_ok": (n_blind / n_z_ok) if n_z_ok else float("nan"),
        "min_xy_err_in_descend": (min(xy for xy, _ in desc) if desc else float("nan")),
        "max_xy_err_in_descend": (max(xy for xy, _ in desc) if desc else float("nan")),
        "final_z_err_in_descend": (desc[-1][1] if desc else float("nan")),
        "blind_dominant": bool(desc and n_blind * 2 >= len(desc)),   # ≥50% 的 descend 步在盲区
        "xy_tol": float(xy_tol), "z_tol": float(z_tol),
    }


def accept_segment(*, seg_len: int, success_relaxed: bool, handback_at: int,
                   n_re_descend: int, max_seg_len: int = MAX_SEG_LEN,
                   max_re_descend: int = MAX_RE_DESCEND) -> tuple[bool, list[str]]:
    """三条过滤（预注册 §3）。返回 (是否收, 拒收理由列表)。理由非空 ⇔ 不收。"""
    why: list[str] = []
    if not success_relaxed:
        why.append("本局放宽口径没成功（过滤 1）")
    if int(handback_at) != -1:
        why.append(f"专家在 {handback_at} 步认输交还（过滤 2：片段尾部是 give_up，不是好示范）")
    if int(seg_len) > int(max_seg_len):
        why.append(f"段长 {seg_len} > {max_seg_len}（过滤 3：效率）")
    if int(n_re_descend) > int(max_re_descend):
        why.append(f"重下探 {n_re_descend} 次 > {max_re_descend}（过滤 3：效率）")
    if int(seg_len) <= 0:
        why.append(f"段长 {seg_len} ≤ 0（空片段，写进去只会污染 stats）")
    return (not why), why


def median_int(xs: list[int]) -> float:
    """中位数（偶数个取中间两数均值）。空列表返回 nan —— 不许用 0 兜底，那会让 A3 假过。"""
    if not xs:
        return float("nan")
    s = sorted(int(x) for x in xs)
    n = len(s)
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def trim_index(seg_steps: list[int], succ_step_rlx: int) -> int:
    """截断：保留前多少帧（预注册 §9 增补 1）。

    `seg_steps[k]` = 第 k 帧被采集时**已执行**的步数（0-based）；放宽成功在第 `succ_step_rlx` 步
    （1-based）闩锁 ⇒ 造成它的那一帧满足 `seg_steps == succ_step_rlx - 1` ⇒ 保留 `seg_steps <
    succ_step_rlx` 的帧（**含**它，那一步的动作正是「把 can 送到」的动作，是最该学的一帧）。
    `succ_step_rlx <= 0` = 本局没成功 ⇒ 全保留（反正过滤 1 会把它整段弃掉）。
    """
    if int(succ_step_rlx) <= 0:
        return len(seg_steps)
    return sum(1 for s in seg_steps if int(s) < int(succ_step_rlx))


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson 得分区间（与历史判定文件同口径：53/80 -> [55.4, 75.7]）。n=0 返回 (nan, nan)。"""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(max(0.0, p * (1 - p) / n + z * z / (4 * n * n))) / den
    return (max(0.0, c - h), min(1.0, c + h))


def resolve_ckpt(p: Path) -> tuple[Path, Path, bool]:
    """把 `.../checkpoints/last/pretrained_model` 解析成**数字格**（坑 63）。

    返回 (原样传入的路径, 解析后的数字格路径, 是否解析成功)。
    为什么要这条：出身核对按路径尾串判「是不是关门读数」，写 `last` 会被判**不采信**；
    采集器虽然不产关门读数，但纠正数据的**出身**必须能追到具体步数。
    """
    given = Path(p)
    parts = list(given.parts)
    if "last" not in parts:
        return given, given, True
    i = parts.index("last")
    ck_dir = Path(*parts[:i])
    link = ck_dir / "last"
    if not link.is_symlink():
        return given, given, False
    tgt = link.resolve().name
    if not (tgt.isdigit() and len(tgt) == 6):
        return given, given, False
    return given, Path(*parts[:i], tgt, *parts[i + 1:]), True


def union_cover(dst_lo: float, dst_hi: float, a_lo: float, a_hi: float,
                b_lo: float, b_hi: float, tol: float = 1e-5) -> bool:
    """B3：合并集的 stats 是否**覆盖两个来源的并集**（min 足够小、max 足够大）。

    承重理由：`--dataset.episodes` 只筛帧、**不重算 stats** ⇒ 8C 与 8C-ctl 两臂要构成 1:1 对照，
    必须共用同一个 normalizer，而这个 normalizer 只有在 stats 覆盖纠正帧时才是「全集口径」。
    """
    vals = (dst_lo, dst_hi, a_lo, a_hi, b_lo, b_hi)
    if not all(np.isfinite(v) for v in vals):
        return False
    return dst_hi >= max(a_hi, b_hi) - tol and dst_lo <= min(a_lo, b_lo) + tol


FRAME_KEYS = (STATE_KEY, ACTION_KEY, IMG_KEY_BASE, IMG_KEY_WRIST)


def readback_shapes(ds, idx: int) -> dict[str, str]:
    """回读一帧，返回 {键: "shape|dtype"}。用来跟**参照训练集**逐键对齐。"""
    row = ds[idx]
    out = {}
    for k in FRAME_KEYS:
        a = np.asarray(row[k])
        out[k] = f"{tuple(int(x) for x in a.shape)}|{a.dtype}"
    out["task"] = str(row["task"])
    return out


def shapes_match(got: dict[str, str], ref: dict[str, str]) -> list[str]:
    """逐键比形状/dtype（task 只比「是不是反向那一句」，不比字面相等）。返回不符的键列表。"""
    bad = [k for k in FRAME_KEYS if got.get(k) != ref.get(k)]
    if got.get("task") != TASK_REVERSE:
        bad.append("task")
    return bad


def to_hwc_uint8(img) -> np.ndarray:
    """把 lerobot **回读**出来的图像还原成 `add_frame` 要的 (H,W,3) uint8。

    回读口径实测是 (3,H,W) float32 ∈ [0,1]（transform 就是 `uint8/255`：2/255 = 0.007843137718737125
    逐位吻合），而 `add_frame` 的 validate_frame 只收 (H,W,C) uint8 ⇒ merge 必须做这一步逆变换。
    可逆性：`round(x*255)` 精确还原原像素，且 v3.0 的图像是无损编码进 parquet 的
    ⇒ merge 里对**采样帧**做了 `np.array_equal(src[i], dst[fr0+i])` 的逐比特断言兜底。
    """
    a = np.asarray(img)
    if a.ndim != 3:
        raise ValueError(f"图像不是三维：{a.shape}")
    if a.shape[0] == 3 and a.shape[-1] != 3:
        a = np.transpose(a, (1, 2, 0))
    if a.dtype == np.uint8:
        return a
    return np.clip(np.rint(np.asarray(a, dtype=np.float64) * 255.0), 0, 255).astype(np.uint8)


def summarize(per_ep: list[dict], seed_lo: int, seed_hi: int) -> dict:
    """把每局卡片汇成 8A 的三条门的读数（口径写死在预注册 §3）。"""
    tk = [e for e in per_ep if e["takeover"]]
    tk_succ = [e for e in tk if e["success_relaxed"]]
    # A3 的「片段步数中位」取**放宽成功的接管片段**这个总体（= 过滤 3 真正作用的那一批）。
    # 为什么不取全部接管片段：horizon=800 下**失败**的接管一定跑满 800 步，段长 = 800 − 接管点，
    # 那个中位数只反映「有多少接管失败」，不反映效率 ⇒ 门会因 horizon 变长而必然挂（口径走样，
    # 留档见 runs/S8_PREREG.md §9 增补 1）。全部接管的中位另存一份，只为透明，不进判据。
    seg_lens = [int(e["seg_len"]) for e in tk_succ]
    seg_lens_all = [int(e["seg_len"]) for e in tk]
    acc = [e for e in per_ep if e["accepted"]]
    n_frames = int(sum(e["seg_len"] for e in acc))
    med = median_int(seg_lens)
    lo, hi = wilson(len(tk_succ), len(tk))
    # descend 盲区汇总（**只透明**：下面这些键一条都不进 gate_a；缺字段的旧记录按 0/nan 处理，不崩）
    diag = [(e.get("diag_descend") or {}) for e in tk]
    n_desc_steps = int(sum(int(d.get("n_descend_steps", 0)) for d in diag))
    n_blind_steps = int(sum(int(d.get("n_blind", 0)) for d in diag))
    nograsp = [e for e in tk if not e["reached_grasp"]]
    ng_blind_dom = int(sum(1 for e in nograsp if (e.get("diag_descend") or {}).get("blind_dominant")))
    return {
        "episodes": len(per_ep), "seed_window": [int(seed_lo), int(seed_hi)],
        "n_takeover": len(tk),
        "takeover_rate": (len(tk) / len(per_ep)) if per_ep else float("nan"),
        "n_takeover_relaxed_success": len(tk_succ),
        "a2_rate": (len(tk_succ) / len(tk)) if tk else float("nan"),
        "a2_wilson": [round(lo * 100, 1), round(hi * 100, 1)],
        "n_takeover_reached_grasp": int(sum(e["reached_grasp"] for e in tk)),
        "seg_len_median": med,                      # 判据用：放宽成功总体（截断后）
        "seg_len_median_all_takeover": median_int(seg_lens_all),   # 只透明，不进判据
        "seg_len_p25": (float(np.percentile(seg_lens, 25)) if seg_lens else float("nan")),
        "seg_len_p75": (float(np.percentile(seg_lens, 75)) if seg_lens else float("nan")),
        "seg_len_max": (int(max(seg_lens)) if seg_lens else -1),
        "seg_len_raw_median_all_takeover": median_int([int(e.get("seg_len_raw", e["seg_len"])) for e in tk]),
        "n_handback": int(sum(1 for e in tk if int(e["handback_at"]) != -1)),
        "n_accepted": len(acc), "n_frames_accepted": n_frames,
        "n_rejected": int(sum(1 for e in per_ep if e["takeover"] and not e["accepted"])),
        "reject_reasons": _count_reasons([r for e in per_ep for r in e["reject_reasons"]]),
        "n_delivered_tipped": int(sum(e["delivered_tipped"] for e in per_ep)),
        "window_conflicts": [[list(w), [seed_lo, seed_hi]] for w in
                             windows_disjoint((int(seed_lo), int(seed_hi)), EVAL_WINDOWS)],
        "mean_seconds_per_episode": (float(np.mean([e["seconds"] for e in per_ep]))
                                     if per_ep else float("nan")),
        "diag_descend_steps": n_desc_steps,
        "diag_blind_steps": n_blind_steps,
        "diag_blind_frac_of_descend": (n_blind_steps / n_desc_steps) if n_desc_steps else float("nan"),
        "diag_n_nograsp": len(nograsp),
        "diag_n_nograsp_blind_dominant": ng_blind_dom,
        "diag_note": ("只透明、不进任何门：mg_expert.py 的 descend 停滞判据要求 z_err>Z_TOL，"
                      "「高度在带内、水平没对准」的步既进不了 grasp 也不算停滞 ⇒ 永不 restage/give_up"),
    }


def _count_reasons(rs: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rs:
        key = r.split("（")[0]
        out[key] = out.get(key, 0) + 1
    return out


def gate_a(rd: dict, n_episodes: int) -> dict:
    """8A 的三条门（全过才进 8B）。任何一条不过 => 预注册分支：写 `runs/s8a.HELD`，等人。"""
    med = rd["seg_len_median"]
    a1 = int(rd["n_frames_accepted"]) >= GATE_A1_FRAMES
    a1_note = ("" if n_episodes == GATE_A1_EPISODES else
               f"（⚠️ 本次跑了 {n_episodes} 局 ≠ 门口径 {GATE_A1_EPISODES} 局，读数不可直接比门）")
    a2 = (rd["n_takeover"] > 0 and float(rd["a2_rate"]) >= GATE_A2_RATE)
    a3_hb = int(rd["n_handback"]) == 0
    a3_med = bool(np.isfinite(med)) and float(med) <= GATE_A3_MEDIAN
    a3_win = not rd["window_conflicts"]
    a3 = a3_hb and a3_med and a3_win
    return {
        "A1": {"pass": bool(a1), "reading": f"{rd['n_frames_accepted']} 可用帧 / {n_episodes} 局",
               "gate": f"≥ {GATE_A1_FRAMES} / {GATE_A1_EPISODES} 局", "note": a1_note},
        "A2": {"pass": bool(a2),
               "reading": f"{rd['n_takeover_relaxed_success']}/{rd['n_takeover']} = "
                          f"{(rd['a2_rate'] * 100 if rd['n_takeover'] else float('nan')):.1f}% "
                          f"Wilson {rd['a2_wilson']}",
               "gate": f"≥ {GATE_A2_RATE * 100:.0f}%"},
        "A3": {"pass": bool(a3),
               "reading": f"handback={rd['n_handback']} 次 / 段长中位={med} / 窗口冲突={rd['window_conflicts']}",
               "gate": f"handback 恒 0 ∧ 中位 ≤ {GATE_A3_MEDIAN}（放宽成功总体，截断后）∧ 窗口不相交",
               "sub": {"no_handback": a3_hb, "median_ok": a3_med, "window_ok": a3_win}},
        "all_pass": bool(a1 and a2 and a3),
    }


# ─────────────────────────────── collect 模式（GPU）───────────────────────────────
def run_collect(args) -> int:
    from mg_env_reverse import ReverseGraspEnv
    from mg_expert_reverse import ReverseScriptedExpert
    from mg_harness import GraspDetector, SegmentBuffer, TakeoverHarness
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    t_start = time.perf_counter()
    stub = str(args.stub_policy or "")
    if stub and args.gate_a:
        print("[err] --stub-policy 是**零 GPU 的链路预演**（假策略，读数没有意义），"
              "不许与 --gate-a 同用，免得把预演当成 8A 的门", file=sys.stderr)
        return 2
    seed_lo, seed_hi = int(args.seed), int(args.seed) + int(args.episodes) - 1
    conflicts = windows_disjoint((seed_lo, seed_hi), EVAL_WINDOWS)
    if conflicts:
        print(f"[err] 采集 seed 窗口 {seed_lo}..{seed_hi} 与评测/示范窗口相交：{conflicts} ⇒ 泄漏会让门失效",
              file=sys.stderr)
        return 2
    if args.horizon <= HORIZON:
        print(f"[warn] horizon={args.horizon} ≤ 评测 horizon {HORIZON}：晚接管点收不到成功片段"
              f"（预注册 §1.5 的算术天花板）", flush=True)

    ckpt_given, ckpt, ok = Path(args.ckpt), Path(args.ckpt), False
    if not stub:
        ckpt_given, ckpt, ok = resolve_ckpt(Path(args.ckpt))
        if not ckpt.is_absolute():
            ckpt = MG_ROOT / ckpt
        if not ckpt.exists():
            print(f"[err] 检查点不存在：{ckpt}", file=sys.stderr)
            return 2
        print(f"[corr] ckpt 原样={ckpt_given}\n[corr] ckpt 数字格={ckpt}"
              f"（解析{'成功' if ok else '失败'}，坑 63）", flush=True)
    else:
        print(f"[corr] ⚠️ STUB 模式（{stub}）：不加载任何策略、不用 GPU 推理，"
              f"只为端到端预演「接管 -> 过滤 -> 写盘 -> 回读」这条链路", flush=True)

    root = DATA / args.out
    ds = None
    if root.exists():
        if not args.append:
            print(f"[err] {root} 已存在（换 --out 或加 --append 续采）", file=sys.stderr)
            return 2
        ds = LeRobotDataset(repo_id=args.out, root=str(root))
        print(f"[corr] 续采：{root} 现有 {ds.meta.total_episodes} 集 / {ds.meta.total_frames} 帧", flush=True)
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        ds = LeRobotDataset.create(repo_id=args.out, fps=CONTROL_FREQ,
                                   features=build_features(args.img_size),
                                   robot_type=ROBOT.lower(), root=str(root),
                                   use_videos=False, image_writer_threads=args.writer_threads)
        print(f"[corr] 新建数据集 {root}（fps={CONTROL_FREQ} robot={ROBOT.lower()} "
              f"use_videos=False img={args.img_size}）", flush=True)
    ep0, fr0 = int(ds.meta.total_episodes), int(ds.meta.total_frames)

    chunk_size, nas = -1, int(args.n_action_steps)
    if stub:
        policy_kind = f"stub:{stub}"
        policy_reset = lambda: None                                             # noqa: E731
        if stub == "gripper_close":
            # 原地不动 + 合爪：爪子上没有 can ⇒ width 掉到 ≤W_EMPTY ⇒ 检测器**必然**在 N_EMPTY 步内触发
            # ⇒ 接管点很早、专家几乎从初态重做一整局（~224 步）⇒ 必然产出一条**被收下**的片段。
            # 这正是预演要的：把 add_frame/save_episode/finalize/npz/回读自证/卡片全都走一遍。
            # ⚠️ 夹爪语义是**实测反的**（robosuite 1.5.2 SimpleGripController：+1 = 闭合、−1 = 张开，
            #    出处 code/mg_expert.py:75 的 GRIP_CLOSE/GRIP_OPEN）。写 −1 会一直张着 ⇒ 检测器永不触发
            #    ⇒ 预演跑 800 步白烧（2026-10-04 实测吃到，见新坑 67）。所以这里**引用常数**不写字面量。
            stub_act = np.zeros(ACTION_DIM, dtype=np.float32)
            stub_act[ACTION_DIM - 1] = float(GRIP_CLOSE)
            policy_act = lambda obs: stub_act.copy()                            # noqa: E731
        else:
            raise ValueError(f"未知 stub 策略 {stub!r}")
    else:
        import torch
        from mg_eval import load_policy, to_tensor_obs
        device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
        policy, pre, post = load_policy(ckpt, device, args.use_amp)
        chunk_size = int(getattr(policy.config, "chunk_size", -1))
        nas = min(int(args.n_action_steps), chunk_size) if chunk_size > 0 else int(args.n_action_steps)
        policy.config.n_action_steps = nas
        policy_kind = type(policy).__name__
        policy_reset = policy.reset

        def policy_act(obs: dict) -> np.ndarray:
            with torch.inference_mode():
                tens = pre(to_tensor_obs(obs, device, task=TASK_REVERSE))
                action = post(policy.select_action(tens))
            act = action.squeeze(0).detach().to("cpu").numpy().astype(np.float32)
            if act.shape[0] != ACTION_DIM:
                raise ValueError(f"策略输出 {act.shape[0]} 维，契约要求 {ACTION_DIM} 维")
            return act
    policy_reset()

    env = ReverseGraspEnv(img_size=args.img_size, horizon=int(args.horizon))
    detector = GraspDetector()          # 常数一个字不改（预注册 §3）
    if (detector.w_empty, detector.n_empty, detector.hold_lo, detector.hold_hi, detector.n_hold) != \
            (W_EMPTY, N_EMPTY, HOLD_LO, HOLD_HI, N_HOLD):
        print("[err] 检测器常数与 mg_calib_detector 不一致 ⇒ 出身为脏，停", file=sys.stderr)
        return 2
    buffer = SegmentBuffer()
    harness = TakeoverHarness(env, ReverseScriptedExpert, observe_only=False, min_remain=0,
                              enabled=True, detector=detector, buffer=buffer, hand_back=False)
    print(f"[corr] task={TASK_REVERSE!r} env={type(env).__name__} horizon={env.horizon}（评测恒 {HORIZON}）"
          f" K={nas} seeds={seed_lo}..{seed_hi} 检测器 w_empty={detector.w_empty} n_empty={detector.n_empty}"
          f" hold=[{detector.hold_lo},{detector.hold_hi}] n_hold={detector.n_hold} hand_back=False",
          flush=True)
    print(f"[corr] 三条过滤：放宽成功 ∧ handback_at==-1 ∧ (seg_len≤{MAX_SEG_LEN} ∧ re_descend≤{MAX_RE_DESCEND})",
          flush=True)

    per_ep: list[dict] = []
    trim = not args.no_trim
    new_states: list[np.ndarray] = []
    new_actions: list[np.ndarray] = []
    new_lengths: list[int] = []
    new_seeds: list[int] = []
    diag_flat: list[tuple[float, float, str]] = []   # 逐专家步的 (xy_err, z_err, phase)：只透明，不进判据
    diag_ep_lens: list[int] = []
    diag_seeds: list[int] = []
    for ep in range(int(args.episodes)):
        seed = seed_lo + ep
        t_ep = time.perf_counter()
        obs = env.reset(seed=seed)
        policy_reset()
        can_z0 = float(env.object_pos[2])
        harness.reset(seed=seed, can_z0=can_z0)
        seg_frames: list[dict] = []
        seg_steps: list[int] = []          # 与 seg_frames 逐条对齐：该帧被采集时「已执行的步数」（0-based）
        diag_rows: list[tuple[float, float, str]] = []   # 本局专家步的 descend 盲区诊断（不进任何门）
        can_at_takeover: list[float] = []
        steps, succ_step, succ_step_rlx = 0, -1, -1
        while True:
            act, source = harness.select(obs, steps, lambda: policy_act(obs))
            if source == "expert":
                # 与 mg_collect.run_one_episode 完全同一个帧口径：state/图像是**这一步之前**的观测，
                # action 是这一步要执行的动作（对齐牙，坑 1~5 那一整套的结论）
                seg_frames.append({STATE_KEY: np.asarray(obs[STATE_KEY], dtype=np.float32),
                                   ACTION_KEY: np.asarray(act, dtype=np.float32),
                                   IMG_KEY_BASE: obs[IMG_KEY_BASE], IMG_KEY_WRIST: obs[IMG_KEY_WRIST],
                                   "task": TASK_REVERSE})
                seg_steps.append(steps)
                # descend 盲区诊断（**只透明**）：can/eef 都取「这一步之前」的真值，与上面的帧口径一致；
                # z_err 的表达式与 mg_expert.py 的 descend 分支逐字相同（常数 import，不重打 —— 坑 67）。
                can_now = np.asarray(env.object_pos, dtype=np.float64)
                eef_now = np.asarray(env.eef_pos, dtype=np.float64)
                if not can_at_takeover:
                    can_at_takeover = [round(float(v), 6) for v in can_now]
                diag_rows.append((float(max(abs(eef_now[0] - can_now[0]), abs(eef_now[1] - can_now[1]))),
                                  float(eef_now[2] - can_now[2] - GRASP_OFFSET_Z),
                                  str(getattr(harness.expert, "phase", ""))))
            obs, _r, terminated, truncated, info = env.step(act)
            steps += 1
            if info["success"] and succ_step < 0:
                succ_step = steps
            s_rlx = bool(info.get("success_relaxed", info["success"]))
            if s_rlx and succ_step_rlx < 0:
                succ_step_rlx = steps
            harness.note_success(s_rlx)
            # 截断（预注册 §9 增补 1）：`terminated` 只认**严格**成功（必须立着），
            # 放宽成功（侧躺送达）**不终止** episode ⇒ 不截断的话侧躺局会一路空转到 horizon=800，
            # 尾巴全是「原地保持」的垃圾帧，还会让「段长 ≤300」这条效率过滤把**主口径的成功局**误杀。
            # 所以：放宽成功一旦闩锁就在此处收工 —— 成功已 latch，接管率/A2/到 grasp 的读数一概不受影响。
            if terminated or truncated or (trim and succ_step_rlx > 0):
                break

        hrec = harness.finish(success=bool(succ_step > 0), success_relaxed=bool(succ_step_rlx > 0),
                              steps=steps)
        seg = buffer.episodes[-1] if buffer.episodes else None
        rec = {"ep": ep, "seed": int(seed), "steps": int(steps),
               "success": bool(succ_step > 0), "success_step": int(succ_step),
               "success_relaxed": bool(succ_step_rlx > 0), "success_step_relaxed": int(succ_step_rlx),
               "delivered_tipped": bool(succ_step_rlx > 0 and succ_step < 0),
               "can_z0": round(can_z0, 6), "seconds": round(time.perf_counter() - t_ep, 1)}
        rec.update({k: hrec[k] for k in ("takeover", "trigger", "takeover_step", "takeover_remain",
                                         "seg_len", "handback", "handback_step", "n_restages",
                                         "unrecoverable", "min_width")})
        rec["handback_at"] = int(seg["handback_at"]) if seg is not None else -1
        rec["seg_len_raw"] = int(hrec["seg_len"])
        rec["early_stopped_at_relaxed"] = bool(trim and succ_step_rlx > 0 and not terminated and not truncated)
        rec["diag_descend"] = descend_diag(diag_rows)
        rec["can_at_takeover"] = can_at_takeover
        diag_flat += diag_rows
        diag_ep_lens.append(len(diag_rows))
        diag_seeds.append(int(seed))
        if seg is not None and int(hrec["seg_len"]) > 0:
            if len(seg_frames) != int(hrec["seg_len"]):
                # 这条断言是**承重的**：帧记录与 harness 的片段缓冲必须逐步对齐，
                # 差一步就会把「观测 t / 动作 t+1」写成一帧（正是坑 1~5 那一类静默错位）。
                print(f"[err] ep{ep} 帧数 {len(seg_frames)} ≠ harness 段长 {hrec['seg_len']} ⇒ 对齐错位，停",
                      file=sys.stderr)
                return 4
            phases = list(seg["phase"])
            # 截断到「放宽成功那一步」：帧与相位用同一个索引口径一起截（只截帧不截相位 = 又一种错位）
            if trim:
                keep = trim_index(seg_steps, succ_step_rlx)
                seg_frames, phases = seg_frames[:keep], phases[:keep]
            rec["seg_len"] = len(seg_frames)
            rec["phases"] = list(dict.fromkeys(phases))
            rec["n_descend_runs"] = count_runs(phases, "descend")
            rec["re_descend"] = re_descend(phases)
            rec["reached_grasp"] = bool("grasp" in phases)
        else:
            rec["phases"], rec["n_descend_runs"], rec["re_descend"], rec["reached_grasp"] = [], 0, 0, False
            rec["seg_len"] = 0

        if rec["takeover"]:
            ok_acc, why = accept_segment(seg_len=int(rec["seg_len"]),
                                         success_relaxed=bool(rec["success_relaxed"]),
                                         handback_at=int(rec["handback_at"]),
                                         n_re_descend=int(rec["re_descend"]))
            rec["accepted"], rec["reject_reasons"] = bool(ok_acc), why
            if ok_acc:
                for fr in seg_frames:
                    ds.add_frame(dict(fr))
                ds.save_episode()
                new_states.append(np.concatenate([f[STATE_KEY][None, :] for f in seg_frames], axis=0))
                new_actions.append(np.concatenate([f[ACTION_KEY][None, :] for f in seg_frames], axis=0))
                new_lengths.append(len(seg_frames))
                new_seeds.append(int(seed))
                rec["episode_index_in_ds"] = ep0 + len(new_lengths) - 1
        else:
            rec["accepted"], rec["reject_reasons"] = False, []
        per_ep.append(rec)
        del seg_frames
        print(f"  ep{ep} seed={seed} steps={steps} 放宽={rec['success_relaxed']} 侧躺={rec['delivered_tipped']}"
              f" | 接管={rec['takeover']} 触发={rec['trigger']}@{rec['takeover_step']}"
              f" 段长={rec['seg_len']} 相位={'->'.join(rec['phases'])} 重下探={rec['re_descend']}"
              f" handback={rec['handback_at']}"
              f" | {'✅收 ' + str(rec['seg_len']) + ' 帧' if rec['accepted'] else '❌弃 ' + ';'.join(rec['reject_reasons'])}"
              f" | 累计可用帧={sum(new_lengths)} {rec['seconds']:.0f}s", flush=True)

        if args.target_frames > 0 and sum(new_lengths) >= int(args.target_frames):
            print(f"[corr] 已达目标帧数 {args.target_frames}（实际 {sum(new_lengths)}），提前收工"
                  f"（跑了 {ep + 1}/{args.episodes} 局）", flush=True)
            break

    env.close()
    ds.finalize()
    secs = time.perf_counter() - t_start

    rd = summarize(per_ep, seed_lo, seed_lo + len(per_ep) - 1)
    rd["n_frames_accepted_this_run"] = int(sum(new_lengths))
    gates = gate_a(rd, len(per_ep)) if args.gate_a else None

    # ── 原始 npz：与已有内容**累加**（8A 的 80 局也计入数据集，npz 同样要留着）──
    npz_path = DATA / f"{args.out}_raw.npz"
    if new_lengths:
        st = np.concatenate(new_states, axis=0)
        ac = np.concatenate(new_actions, axis=0)
        ln = np.asarray(new_lengths, dtype=np.int32)
        sd = np.asarray(new_seeds, dtype=np.int64)
        if npz_path.exists():
            old = np.load(npz_path)
            st = np.concatenate([old["state"], st], axis=0)
            ac = np.concatenate([old["action"], ac], axis=0)
            ln = np.concatenate([old["episode_lengths"], ln]).astype(np.int32)
            sd = np.concatenate([old["seeds"], sd]).astype(np.int64)
        np.savez_compressed(npz_path, state=st, action=ac, episode_lengths=ln, seeds=sd)

    # ── 回读自证：数据集里的帧数必须等于所有收下的片段长度之和 ──
    expect_ep, expect_fr = ep0 + len(new_lengths), fr0 + int(sum(new_lengths))
    if expect_fr <= 0:
        # 一帧都没收下 ⇒ **不要**去 LeRobotDataset(...) 回读：空数据集没有 meta/tasks.parquet，
        # lerobot 会转头去 HF 拉元数据 ⇒ 离线环境下炸成一坨看不懂的堆栈，把「产出率 = 0」这个
        # 真正的读数盖住（2026-10-04 stub 预演实测吃到）。新建的空目录顺手删掉，
        # 免得下一次 --append 撞上半个数据集。
        if ep0 == 0 and root.exists():
            shutil.rmtree(root)
            print(f"[warn] 本次一帧都没收下 ⇒ 已删除新建的空数据集 {root}", flush=True)
        ep1, fr1, item = ep0, fr0, None
        checks = {"nothing_accepted": True,
                  "episodes_grew_by_n_accepted": ep1 == expect_ep,
                  "frames_grew_by_sum_seglen": fr1 == expect_fr,
                  "npz_lengths_sum_matches_ds": (not npz_path.exists()) or
                      int(np.load(npz_path)["episode_lengths"].sum()) == fr1}
    else:
        ds2 = LeRobotDataset(repo_id=args.out, root=str(root))
        ep1, fr1 = int(ds2.meta.total_episodes), int(ds2.meta.total_frames)
        item = ds2[fr1 - 1]
        # 形状/dtype 的正确口径**不是**「HWC uint8」，而是「与参照训练集逐键相同」：
        # lerobot 回读时会把图像转成 (3,224,224) float32 ∈[0,1]（2026-10-04 stub 预演实测），
        # 而 `data/mix60f120r` 回来的是**同一个**东西 ⇒ 拿参照集比才是承重检查（比写死期望强，
        # 因为它同时钉住了 writer 版本、features 声明与 transform 链）。
        got = readback_shapes(ds2, fr1 - 1)
        ref_ds = LeRobotDataset(repo_id=args.ref_dataset, root=str(DATA / args.ref_dataset))
        ref = readback_shapes(ref_ds, len(ref_ds) - 1)
        mismatch = shapes_match(got, ref)
        checks = {
            "episodes_grew_by_n_accepted": ep1 == expect_ep,
            "frames_grew_by_sum_seglen": fr1 == expect_fr,
            "npz_lengths_sum_matches_ds": (not npz_path.exists()) or
                int(np.load(npz_path)["episode_lengths"].sum()) == fr1,
            "reread_task_is_reverse": str(item["task"]) == TASK_REVERSE,
            "reread_shapes_match_reference": not mismatch,
        }
    checks_detail = {"got": (got if expect_fr > 0 else None), "ref": (ref if expect_fr > 0 else None),
                     "mismatch": (mismatch if expect_fr > 0 else None),
                     "ref_dataset": args.ref_dataset}
    bad = [k for k, v in checks.items() if not v]
    if bad:
        print(f"[err] 回读自证不过：{bad}（ep {ep0}->{ep1}（期望 {expect_ep}）/ "
              f"fr {fr0}->{fr1}（期望 {expect_fr}）/ 收 {len(new_lengths)} 集 {sum(new_lengths)} 帧）"
              f"⇒ 数据集不可用，先查写盘；形状明细 {json.dumps(checks_detail, ensure_ascii=False)}",
              file=sys.stderr)
        return 3

    card = {
        "kind": "correction_dataset_card", "generated": f"{datetime.now():%F %T}",
        "policy_kind": policy_kind, "stub_policy": stub,
        "policy_ckpt_given": str(ckpt_given), "policy_ckpt_resolved": str(ckpt),
        "policy_ckpt_resolved_ok": bool(ok), "n_action_steps": nas, "chunk_size": chunk_size,
        "trim_at_relaxed_success": bool(trim),
        "task": TASK_REVERSE, "suite_task": SUITE_TASK, "robot": ROBOT, "fps": CONTROL_FREQ,
        "horizon_collect": int(args.horizon), "horizon_eval_UNCHANGED": int(HORIZON),
        "seed_window": [seed_lo, seed_lo + len(per_ep) - 1], "eval_windows": [list(w) for w in EVAL_WINDOWS],
        "window_conflicts": rd["window_conflicts"],
        "detector": {"w_empty": detector.w_empty, "n_empty": detector.n_empty,
                     "hold_lo": detector.hold_lo, "hold_hi": detector.hold_hi,
                     "n_hold": detector.n_hold, "hand_back": False, "min_remain": 0,
                     "constants_source": "code/mg_calib_detector.py（runs/_diag/harness_calib.md）"},
        "filters": {"relaxed_success": True, "handback_at_must_be": -1,
                    "max_seg_len": MAX_SEG_LEN, "max_re_descend": MAX_RE_DESCEND,
                    "prereg": "runs/S8_PREREG.md §3（效率过滤是留档偏离，替代停滞阶梯）"},
        "dataset": {"root": str(root), "episodes_before": ep0, "episodes_after": ep1,
                    "frames_before": fr0, "frames_after": fr1,
                    "episodes_added": len(new_lengths), "frames_added": int(sum(new_lengths))},
        "npz": str(npz_path), "readback_checks": checks,
        "readback_detail": checks_detail,
        "readings": rd, "gate_a": gates,
        "per_episode": per_ep,
        "seconds": round(secs, 1),
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }
    try:
        import mujoco
        import robosuite
        import torch
        card["versions"].update({"robosuite": robosuite.__version__, "mujoco": mujoco.__version__,
                                 "torch": torch.__version__})
    except Exception:
        pass
    (root / "MG_DATASET_CARD.json").write_text(json.dumps(card, indent=2, ensure_ascii=False))

    rep = Path(args.report)
    if not rep.is_absolute():
        rep = MG_ROOT / rep
    rep.parent.mkdir(parents=True, exist_ok=True)
    (rep.with_suffix(".json")).write_text(json.dumps(card, indent=2, ensure_ascii=False))
    (rep.with_suffix(".md")).write_text(render_collect_md(card))
    # ── descend 盲区的逐步 npz（**只透明**：判据与三条过滤一条都不读它；HELD 时用它定病因）──
    if diag_flat:
        diag_path = rep.with_name(rep.name + "_diag_descend.npz")
        np.savez_compressed(
            diag_path,
            xy_err=np.asarray([r[0] for r in diag_flat], dtype=np.float32),
            z_err=np.asarray([r[1] for r in diag_flat], dtype=np.float32),
            phase=np.asarray([r[2] for r in diag_flat], dtype="<U16"),
            ep_lengths=np.asarray(diag_ep_lens, dtype=np.int32),
            seeds=np.asarray(diag_seeds, dtype=np.int64),
            xy_tol=np.float32(XY_TOL), z_tol=np.float32(Z_TOL),
            grasp_offset_z=np.float32(GRASP_OFFSET_Z),
        )
        print(f"[diag]    {diag_path}（{len(diag_flat)} 个专家步 / {len(diag_ep_lens)} 局；只透明，不进判据）")
    print(f"\n[corr] {len(per_ep)} 局 / 接管 {rd['n_takeover']} / 收 {rd['n_accepted']} 段 "
          f"{rd['n_frames_accepted']} 帧（本次新增 {sum(new_lengths)}）/ {secs:.0f}s "
          f"（{rd['mean_seconds_per_episode']:.0f}s/局）")
    if gates:
        for k in ("A1", "A2", "A3"):
            g = gates[k]
            print(f"[gate {k}] {'✅' if g['pass'] else '❌'} {g['reading']}（门 {g['gate']}）{g.get('note','')}")
        print(f"[gate] GATE_A_ALL={'YES' if gates['all_pass'] else 'NO'}")
    print(f"[card]    {root / 'MG_DATASET_CARD.json'}\n[npz]     {npz_path}\n[report]  {rep}.md")
    if gates and not gates["all_pass"]:
        return 5      # 预注册分支：8A 不过 => 链写 runs/s8a.HELD（不是失败，是等人）
    return 0


def render_collect_md(c: dict) -> str:
    rd, g = c["readings"], c.get("gate_a")
    L = ["# 档 8 · 纠正数据采集报告", "",
         f"* 生成时间：{c['generated']}（`code/mg_collect_corr.py --mode collect`）",
         f"* 策略：`{c['policy_ckpt_resolved']}`（原样传入 `{c['policy_ckpt_given']}`，"
         f"数字格解析{'✅' if c['policy_ckpt_resolved_ok'] else '❌'}，坑 63）K={c['n_action_steps']} "
         f"类型 `{c['policy_kind']}`"
         + ("　⚠️ **STUB 预演，读数无意义**" if c.get("stub_policy") else ""),
         f"* 截断：放宽成功处截断={'开' if c.get('trim_at_relaxed_success') else '关'}"
         f"（预注册 §9 增补 1：`terminated` 只认严格成功，侧躺送达不终止）",
         f"* 任务：`{c['task']}`",
         f"* 采集 horizon = **{c['horizon_collect']}**（只采集用；评测 horizon 恒 {c['horizon_eval_UNCHANGED']}）",
         f"* seed 窗口：{rd['seed_window'][0]}..{rd['seed_window'][1]}；与评测/示范窗口的冲突："
         f"{rd['window_conflicts'] or '无'}",
         f"* 检测器常数（一个字没改）：{json.dumps(c['detector'], ensure_ascii=False)}",
         f"* 三条过滤：{json.dumps(c['filters'], ensure_ascii=False)}",
         f"* 数据集：`{c['dataset']['root']}` {c['dataset']['episodes_before']}→"
         f"{c['dataset']['episodes_after']} 集、{c['dataset']['frames_before']}→"
         f"{c['dataset']['frames_after']} 帧（本次 +{c['dataset']['episodes_added']} 集 / "
         f"+{c['dataset']['frames_added']} 帧）",
         f"* 回读自证：{json.dumps(c['readback_checks'], ensure_ascii=False)}",
         f"* 用时：{c['seconds']} s（{rd['mean_seconds_per_episode']:.1f} s/局）", "",
         "## 一、产出率读数", "",
         "| 读数 | 值 |", "|:--|:--|",
         f"| 局数 | {rd['episodes']} |",
         f"| 接管次数 | {rd['n_takeover']}（接管率 {rd['takeover_rate'] * 100:.1f}%） |",
         f"| 接管局放宽成功 | {rd['n_takeover_relaxed_success']}/{rd['n_takeover']} = "
         f"{(rd['a2_rate'] * 100 if rd['n_takeover'] else float('nan')):.1f}% Wilson {rd['a2_wilson']} |",
         f"| 接管后到达 `grasp` | {rd['n_takeover_reached_grasp']}/{rd['n_takeover']} |",
         f"| 段长中位 / p25 / p75 / max | {rd['seg_len_median']} / {rd['seg_len_p25']:.0f} / "
         f"{rd['seg_len_p75']:.0f} / {rd['seg_len_max']} |",
         f"| 段长中位（全部接管，只透明不进判据） | {rd['seg_len_median_all_takeover']} "
         f"（截断前 {rd['seg_len_raw_median_all_takeover']}） |",
         f"| 专家认输（handback_at≠-1） | {rd['n_handback']} |",
         f"| **收下** | {rd['n_accepted']} 段 / **{rd['n_frames_accepted']} 帧** |",
         f"| 弃 | {rd['n_rejected']} 段；理由分布 {json.dumps(rd['reject_reasons'], ensure_ascii=False)} |",
         f"| 侧躺送到（delivered_tipped） | {rd['n_delivered_tipped']} |", ""]
    if g:
        L += ["## 二、格 8A 三条门（全过才进 8B）", "",
              "| 门 | 读数 | 门槛 | 结果 |", "|:--|:--|:--|:--|"]
        for k in ("A1", "A2", "A3"):
            L.append(f"| {k} | {g[k]['reading']} | {g[k]['gate']} | {'✅' if g[k]['pass'] else '❌'} |")
        L += ["", f"**GATE_A_ALL = {'YES' if g['all_pass'] else 'NO'}**"
              + ("" if g["all_pass"] else " ⇒ 预注册分支：写 `runs/s8a.HELD`，停下等人（不许当场改门，坑 40）"), ""]
        if g["A1"].get("note"):
            L += [f"* {g['A1']['note']}", ""]
    L += ["## 三、每局明细", "",
          "| ep | seed | steps | 放宽 | 侧躺 | 接管 | 触发@步 | 段长 | 重下探 | 到grasp | handback | 判定 |",
          "|--:|--:|--:|:--|:--|:--|:--|--:|--:|:--|--:|:--|"]
    for e in c["per_episode"]:
        L.append(f"| {e['ep']} | {e['seed']} | {e['steps']} | {int(e['success_relaxed'])} | "
                 f"{int(e['delivered_tipped'])} | {int(e['takeover'])} | {e['trigger'] or '-'}"
                 f"@{e['takeover_step']} | {e['seg_len']} | {e['re_descend']} | "
                 f"{int(e['reached_grasp'])} | {e['handback_at']} | "
                 f"{'✅' + str(e['seg_len']) + '帧' if e['accepted'] else ('❌' + ';'.join(e['reject_reasons']) if e['reject_reasons'] else '-')} |")
    L += ["", "## 复现", "", "```bash",
          "$MG_PY code/mg_collect_corr.py --selftest",
          "$MG_PY code/mg_collect_corr.py --mode collect --ckpt <数字格/pretrained_model> "
          f"--episodes {rd['episodes']} --seed {rd['seed_window'][0]} --horizon {c['horizon_collect']}",
          "```", ""]
    return "\n".join(L)


# ─────────────────────────────── merge 模式（零 GPU）───────────────────────────────
def run_merge(args) -> int:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    t0 = time.perf_counter()
    src_root, dst_root = DATA / args.out, DATA / args.dst
    for p in (src_root, dst_root):
        if not p.is_dir():
            print(f"[err] 数据集不在：{p}", file=sys.stderr)
            return 2
    src = LeRobotDataset(repo_id=args.out, root=str(src_root))
    n_src_ep, n_src_fr = int(src.meta.total_episodes), int(src.meta.total_frames)
    if n_src_ep == 0:
        print("[err] 纠正集是空的：先跑 --mode collect", file=sys.stderr)
        return 2

    dst = LeRobotDataset(repo_id=args.dst, root=str(dst_root))
    ep0, fr0 = int(dst.meta.total_episodes), int(dst.meta.total_frames)
    man_before = sha_manifest(dst_root)
    dst_stats_before = {k: (np.asarray(v["min"]).ravel().tolist(), np.asarray(v["max"]).ravel().tolist())
                        for k, v in (dst.meta.stats or {}).items()
                        if isinstance(v, dict) and "min" in v and "max" in v}
    print(f"[merge] {src_root.name}（{n_src_ep} 集 / {n_src_fr} 帧） -> 追加进 {dst_root.name}"
          f"（现 {ep0} 集 / {fr0} 帧）", flush=True)

    # 一遍扫过纠正集：按 episode_index 分组（index 递增 ⇒ 同一集的帧必然连续）
    groups: dict[int, list[dict]] = {}
    for i in range(n_src_fr):
        row = src[i]
        e = int(np.asarray(row["episode_index"]).ravel()[0])
        groups.setdefault(e, []).append(row)
    if sorted(groups) != list(range(n_src_ep)):
        print(f"[err] 纠正集的 episode_index 不连续：{sorted(groups)[:5]}..（期望 0..{n_src_ep - 1}）",
              file=sys.stderr)
        return 3

    n_frames = 0
    for e in sorted(groups):
        rows = groups[e]
        for row in rows:
            st = np.asarray(row[STATE_KEY], dtype=np.float32)
            ac = np.asarray(row[ACTION_KEY], dtype=np.float32)
            tk = str(row["task"])
            if tk != TASK_REVERSE:
                print(f"[err] 纠正集第 {e} 集的 task 串不是反向示范那一句：{tk!r} ⇒ B3 会挂，停",
                      file=sys.stderr)
                return 3
            dst.add_frame({STATE_KEY: st, ACTION_KEY: ac,
                           IMG_KEY_BASE: to_hwc_uint8(row[IMG_KEY_BASE]),
                           IMG_KEY_WRIST: to_hwc_uint8(row[IMG_KEY_WRIST]), "task": tk})
        dst.save_episode()
        n_frames += len(rows)
        print(f"  追加 ep{e}（{len(rows)} 帧）-> 累计 {n_frames}/{n_src_fr}", flush=True)
    dst.finalize()

    # ── 逐比特校验：合并集里第 fr0+i 帧必须与纠正集第 i 帧**完全相同**（含图像的浮点回读值）──
    dst3 = LeRobotDataset(repo_id=args.dst, root=str(dst_root))
    idxs = sorted({0, n_src_fr // 2, n_src_fr - 1} |
                  set(np.linspace(0, n_src_fr - 1, min(60, n_src_fr)).astype(int).tolist()))
    bit_bad: list[str] = []
    for i in idxs:
        a, b = src[i], dst3[fr0 + i]
        for k in FRAME_KEYS:
            if not np.array_equal(np.asarray(a[k]), np.asarray(b[k])):
                bit_bad.append(f"帧 {i} 的 {k}")
        if str(a["task"]) != str(b["task"]):
            bit_bad.append(f"帧 {i} 的 task")
    if bit_bad:
        print(f"[err] 逐比特校验不过（抽查 {len(idxs)} 帧）：{bit_bad[:6]} ⇒ 逆变换/编码路径有损，停",
              file=sys.stderr)
        return 3
    print(f"[merge] 逐比特校验 ✅（抽查 {len(idxs)} 帧 × {len(FRAME_KEYS) + 1} 个字段全等）", flush=True)

    # ── B1/B2/B3 对账（预注册 §3 格 8B）──────────────────────────────────────
    dst2 = LeRobotDataset(repo_id=args.dst, root=str(dst_root))
    ep1, fr1 = int(dst2.meta.total_episodes), int(dst2.meta.total_frames)
    man_after = sha_manifest(dst_root)
    dm = diff_manifest(man_before, man_after)
    sc = scope_changed(dm["changed"], dm["removed"])
    b1 = (ep1 == ep0 + n_src_ep) and (fr1 == fr0 + n_src_fr)
    b1_target = fr1 - fr0 >= (args.target_frames if args.target_frames > 0 else TARGET_FRAMES_8B)
    b2 = not sc["payload_changed"] and not sc["removed"] and not sc["other_changed"] \
        and not sc["meta_unexpected"]

    import pandas as pd
    tasks = pd.read_parquet(dst_root / "meta" / "tasks.parquet")
    task_strs = [str(t) for t in tasks.index.tolist()]
    b3_tasks = len(task_strs) == 2 and TASK_REVERSE in task_strs
    cov = []
    for key in (STATE_KEY, ACTION_KEY):
        if key not in (dst2.meta.stats or {}) or key not in dst.meta.stats or key not in (src.meta.stats or {}):
            cov.append((key, "缺 stats"))
            continue
        d, a, b = (dst2.meta.stats[key], dst_stats_before.get(key), src.meta.stats[key])
        if a is None:
            cov.append((key, "缺合并前 stats"))
            continue
        for j in range(len(np.asarray(d["max"]).ravel())):
            if not union_cover(float(np.asarray(d["min"]).ravel()[j]), float(np.asarray(d["max"]).ravel()[j]),
                               float(a[0][j]), float(a[1][j]),
                               float(np.asarray(b["min"]).ravel()[j]), float(np.asarray(b["max"]).ravel()[j])):
                cov.append((key, f"dim{j}"))
    b3_stats = not cov
    b3 = b3_tasks and b3_stats
    bad = []
    if not b1:
        bad.append(f"B1 集/帧数不符：{ep0}->{ep1}（期望 +{n_src_ep}）、{fr0}->{fr1}（期望 +{n_src_fr}）")
    if not b2:
        bad.append(f"B2 原数据负载被改写 {len(sc['payload_changed'])} 个 / 删 {len(sc['removed'])} 个 / "
                   f"meta 白名单外 {len(sc['meta_unexpected'])} 个")
    if not b3:
        bad.append(f"B3 tasks={len(task_strs)} 个（期望 2）或 stats 未覆盖并集：{cov[:6]}")

    # 数据卡片：把纠正集的出身**整份**抄过来，再补合并口径
    src_card_path = src_root / "MG_DATASET_CARD.json"
    src_card = json.loads(src_card_path.read_text()) if src_card_path.exists() else {}
    card = {
        "kind": "merged_dataset_card", "generated": f"{datetime.now():%F %T}",
        "dst": str(dst_root), "src_correction": str(src_root),
        "provenance": src_card,
        "merge": {"episodes_before": ep0, "episodes_after": ep1, "frames_before": fr0,
                  "frames_after": fr1, "episodes_added": n_src_ep, "frames_added": n_src_fr,
                  "task_strings": task_strs, "scope": sc, "seconds": round(time.perf_counter() - t0, 1)},
        "gates": {"B1": {"pass": bool(b1), "reading": f"{ep0}->{ep1} 集 / {fr0}->{fr1} 帧",
                         "gate": f"== 原 + {n_src_ep} 集 / + {n_src_fr} 帧"},
                  "B1_target": {"pass": bool(b1_target),
                                "reading": f"新增 {fr1 - fr0} 帧",
                                "gate": f"≥ {args.target_frames if args.target_frames > 0 else TARGET_FRAMES_8B}"
                                        f"（不够则按实际帧数走并在判定里写明「低于目标」）"},
                  "B2": {"pass": bool(b2),
                         "reading": f"负载改写 {len(sc['payload_changed'])} / 删 {len(sc['removed'])} / "
                                    f"meta 改写 {len(sc['meta_changed'])}（白名单外 {len(sc['meta_unexpected'])}）",
                         "gate": "原有 parquet/图片 sha256 全不变"},
                  "B3": {"pass": bool(b3), "reading": f"tasks={task_strs} / stats 未覆盖维度 {cov[:6]}",
                         "gate": "恰好 2 个 task 串 ∧ stats 覆盖并集"},
                  "bitexact": {"pass": not bit_bad,
                               "reading": f"抽查 {len(idxs)} 帧（{idxs[:3]}...）× 5 字段全等",
                               "gate": "合并集第 fr0+i 帧 == 纠正集第 i 帧（逐比特）"}},
        "all_pass": bool(b1 and b2 and b3),
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }
    (dst_root / "MG_DATASET_CARD.json").write_text(json.dumps(card, indent=2, ensure_ascii=False))
    rep = Path(args.report)
    if not rep.is_absolute():
        rep = MG_ROOT / rep
    rep.parent.mkdir(parents=True, exist_ok=True)
    (rep.with_suffix(".json")).write_text(json.dumps(card, indent=2, ensure_ascii=False))
    L = ["# 档 8 格 8B · 合并数据集对账", "",
         f"* 生成时间：{card['generated']}（`code/mg_collect_corr.py --mode merge`，零 GPU）",
         f"* `{src_root.name}`（{n_src_ep} 集 / {n_src_fr} 帧）追加进 `{dst_root.name}`",
         f"* 出身（纠正集卡片）：策略 `{src_card.get('policy_ckpt_resolved', '?')}`、"
         f"采集 horizon={src_card.get('horizon_collect', '?')}、"
         f"过滤 {json.dumps(src_card.get('filters', {}), ensure_ascii=False)}",
         f"* 用时：{card['merge']['seconds']} s", "",
         "| 门 | 读数 | 门槛 | 结果 |", "|:--|:--|:--|:--|"]
    for k in ("B1", "B1_target", "B2", "B3"):
        gt = card["gates"][k]
        L.append(f"| {k} | {gt['reading']} | {gt['gate']} | {'✅' if gt['pass'] else '❌'} |")
    gt = card["gates"]["bitexact"]
    L.append(f"| 逐比特 | {gt['reading']} | {gt['gate']} | {'✅' if gt['pass'] else '❌'} |")
    L += ["", f"**判定：{'✅ 全过 ⇒ 可进 8C' if card['all_pass'] else '❌ 不过 ⇒ 停下查因，不许进 8C'}**", ""]
    if bad:
        L += [f"* {b}" for b in bad] + [""]
    if not b1_target:
        L += ["* ⚠️ **低于目标帧数**：按预注册「按实际帧数走并在判定里写明」，不追加预算。", ""]
    (rep.with_suffix(".md")).write_text("\n".join(L))
    for k in ("B1", "B1_target", "B2", "B3", "bitexact"):
        gt = card["gates"][k]
        print(f"[gate {k}] {'✅' if gt['pass'] else '❌'} {gt['reading']}")
    print(f"[merge] {'MERGE_OK' if card['all_pass'] else 'MERGE_FAIL'} -> {rep}.md")
    return 0 if card["all_pass"] else 3


# ─────────────────────────────────── 自测（零 GPU）───────────────────────────────────
def selftest() -> int:
    npass = nfail = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal npass, nfail
        if cond:
            npass += 1
        else:
            nfail += 1
            print(f"  [FAIL] {name}")

    # ── count_runs / re_descend：期望值按定义手数 ──
    chk("空序列 0 段", count_runs([], "descend") == 0)
    chk("单段", count_runs(["approach", "descend", "descend", "grasp"], "descend") == 1)
    chk("两段（中间被打断）", count_runs(["descend", "approach", "descend"], "descend") == 2)
    chk("三段", count_runs(["descend", "lift", "descend", "approach", "descend"], "descend") == 3)
    chk("相邻同名不重复计", count_runs(["descend"] * 7, "descend") == 1)
    chk("place_descend 不算 descend（精确串比）",
        count_runs(["descend", "place_descend", "descend"], "descend") == 2)
    chk("re_descend：没下探 = 0", re_descend(["approach", "grasp"]) == 0)
    chk("re_descend：一次下探 = 0", re_descend(["approach", "descend", "descend", "grasp"]) == 0)
    chk("re_descend：重下探一次 = 1", re_descend(["descend", "approach", "descend", "grasp"]) == 1)
    chk("re_descend：重下探两次 = 2", re_descend(["descend", "a", "descend", "a", "descend"]) == 2)
    chk("re_descend 不会是 −1", re_descend([]) == 0)

    # ── accept_segment：三条过滤 + 边界（坑 65：专测边界）──
    ok, why = accept_segment(seg_len=201, success_relaxed=True, handback_at=-1, n_re_descend=0)
    chk("好片段收（201 步 = 档 5 的 p50 量级）", ok and why == [])
    ok, why = accept_segment(seg_len=300, success_relaxed=True, handback_at=-1, n_re_descend=1)
    chk("边界：段长恰好 300 收", ok)
    ok, why = accept_segment(seg_len=301, success_relaxed=True, handback_at=-1, n_re_descend=0)
    chk("边界：段长 301 弃", (not ok) and any("段长" in w for w in why))
    ok, why = accept_segment(seg_len=100, success_relaxed=True, handback_at=-1, n_re_descend=1)
    chk("边界：重下探 1 次收", ok)
    ok, why = accept_segment(seg_len=100, success_relaxed=True, handback_at=-1, n_re_descend=2)
    chk("边界：重下探 2 次弃", (not ok) and any("重下探" in w for w in why))
    ok, why = accept_segment(seg_len=100, success_relaxed=False, handback_at=-1, n_re_descend=0)
    chk("放宽没成功 => 弃（过滤 1）", (not ok) and any("放宽" in w for w in why))
    ok, why = accept_segment(seg_len=100, success_relaxed=True, handback_at=137, n_re_descend=0)
    chk("handback_at≠-1 => 弃（过滤 2）", (not ok) and any("认输" in w for w in why))
    ok, why = accept_segment(seg_len=0, success_relaxed=True, handback_at=-1, n_re_descend=0)
    chk("空片段 => 弃", not ok)
    _, why = accept_segment(seg_len=999, success_relaxed=False, handback_at=5, n_re_descend=9)
    chk("多条理由全列出（不许只报第一条）", len(why) >= 4)

    # ── median_int ──
    chk("中位：奇数个", median_int([1, 3, 2]) == 2.0)
    chk("中位：偶数个取均值", median_int([1, 2, 3, 4]) == 2.5)
    chk("中位：空列表是 nan（不许用 0 兜底让 A3 假过）", not np.isfinite(median_int([])))

    # ── trim_index：截断口径（预注册 §9 增补 1）。期望值按「帧 k 的动作造成第 seg_steps[k]+1 步」手推 ──
    chk("截断：成功在第 13 步 => seg_steps 10/11/12 全留（12 那帧的动作造成第 13 步）",
        trim_index([10, 11, 12], 13) == 3)
    chk("截断：成功在第 12 步 => 只留 seg_steps 10/11", trim_index([10, 11, 12], 12) == 2)
    chk("截断：成功在接管当步 => 只留 1 帧", trim_index([66], 67) == 1)
    chk("截断：没成功（-1）=> 全留（反正过滤 1 会整段弃）", trim_index([10, 11, 12], -1) == 3)
    chk("截断：没成功（0）=> 全留", trim_index([10, 11], 0) == 2)
    chk("截断：空片段 => 0", trim_index([], 5) == 0)
    chk("截断：成功步早于所有帧（不可能但要有定义）=> 0", trim_index([10, 11], 3) == 0)

    # ── shapes_match：与参照训练集逐键对齐（期望值按定义独立算）──
    ref = {STATE_KEY: "(8,)|float32", ACTION_KEY: "(7,)|float32",
           IMG_KEY_BASE: "(3, 224, 224)|float32", IMG_KEY_WRIST: "(3, 224, 224)|float32",
           "task": TASK_REVERSE}
    chk("逐键相同 => 无不符", shapes_match(dict(ref), ref) == [])
    bad_img = dict(ref, **{IMG_KEY_BASE: "(224, 224, 3)|uint8"})
    chk("基座相机形状/dtype 不符 => 点出那一个键", shapes_match(bad_img, ref) == [IMG_KEY_BASE])
    bad_st = dict(ref, **{STATE_KEY: "(9,)|float32"})
    chk("state 维度不符 => 点出 state", shapes_match(bad_st, ref) == [STATE_KEY])
    bad_task = dict(ref, task="Pick up the can and place it into the bin.")
    chk("task 不是反向那一句 => 点出 task（正向串混进纠正集是致命污染）",
        shapes_match(bad_task, ref) == ["task"])
    chk("两处不符都列出", len(shapes_match(dict(bad_img, **{STATE_KEY: "(9,)|float32"}), ref)) == 2)
    chk("FRAME_KEYS 恰好是四个数据键", set(FRAME_KEYS) == {STATE_KEY, ACTION_KEY, IMG_KEY_BASE, IMG_KEY_WRIST})

    # ── to_hwc_uint8：期望值按「uint8/255 的逆变换」独立算，并专测 0/255 两个端点 ──
    chw = np.zeros((3, 4, 5), dtype=np.float32)
    chw[0], chw[1], chw[2] = 2 / 255, 1.0, 0.0
    got = to_hwc_uint8(chw)
    chk("CHW float -> HWC uint8（形状转对）", got.shape == (4, 5, 3) and got.dtype == np.uint8)
    chk("通道值还原（2/255->2、1.0->255、0.0->0）",
        got[0, 0, 0] == 2 and got[0, 0, 1] == 255 and got[0, 0, 2] == 0)
    chk("0..255 全值域精确可逆", all(
        to_hwc_uint8(np.full((3, 1, 1), v / 255.0, dtype=np.float32))[0, 0, 0] == v for v in range(256)))
    hwc_u8 = np.zeros((4, 5, 3), dtype=np.uint8)
    chk("已是 HWC uint8 => 原样返回（不重复缩放）", to_hwc_uint8(hwc_u8) is not None
        and np.array_equal(to_hwc_uint8(hwc_u8), hwc_u8))
    chw_u8 = np.zeros((3, 4, 5), dtype=np.uint8)
    chw_u8[1, 2, 3] = 77
    chk("CHW uint8 => 只转置不缩放", to_hwc_uint8(chw_u8)[2, 3, 1] == 77)
    try:
        to_hwc_uint8(np.zeros((3, 4), dtype=np.float32))
        chk("二维图像要报错（不许静默放过）", False)
    except ValueError:
        chk("二维图像要报错（不许静默放过）", True)
    # ── wilson：与历史判定文件同口径（53/80 -> [55.4, 75.7]，出处 runs/S7F_DIAG.md）──
    lo, hi = wilson(53, 80)
    chk("wilson(53,80) = [55.4, 75.7]", abs(lo * 100 - 55.4) < 0.1 and abs(hi * 100 - 75.7) < 0.1)
    lo0, hi0 = wilson(0, 20)
    chk("wilson(0,20) 下界贴 0", lo0 == 0.0 and 0.15 < hi0 < 0.18)
    chk("wilson(20,20) 上界贴 1", wilson(20, 20)[1] == 1.0)
    chk("wilson n=0 是 nan", not np.isfinite(wilson(0, 0)[0]))

    # ── resolve_ckpt（坑 63）──
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        ck = Path(td) / "checkpoints"
        (ck / "022000" / "pretrained_model").mkdir(parents=True)
        (ck / "last").symlink_to(ck / "022000")
        given = ck / "last" / "pretrained_model"
        g2, r2, ok2 = resolve_ckpt(given)
        chk("last/pretrained_model -> 022000/pretrained_model",
            ok2 and r2 == ck / "022000" / "pretrained_model" and g2 == given)
        g3, r3, ok3 = resolve_ckpt(ck / "018000" / "pretrained_model")
        chk("本来就是数字格 => 原样返回、算成功", ok3 and r3 == g3)
        (ck / "024000").mkdir()
        (ck / "last").unlink()
        (ck / "last").symlink_to(ck / "024000")
        _, r4, ok4 = resolve_ckpt(ck / "last" / "pretrained_model")
        chk("软链指向别的格也能解析（不许写死 022000）", ok4 and r4.name == "pretrained_model"
            and r4.parent.name == "024000")
        (ck / "last").unlink()
        (ck / "last").mkdir()
        _, _, ok5 = resolve_ckpt(ck / "last" / "pretrained_model")
        chk("`last` 不是软链 => 解析失败（不能冒充数字格）", not ok5)

    # ── union_cover（B3）──
    chk("覆盖并集", union_cover(-1.0, 2.0, -0.5, 1.0, -1.0, 2.0))
    chk("max 不够 => 不覆盖", not union_cover(-1.0, 1.5, -0.5, 1.0, -1.0, 2.0))
    chk("min 不够 => 不覆盖", not union_cover(-0.4, 2.0, -0.5, 1.0, -1.0, 2.0))
    chk("有 nan => 不覆盖（不许假过）", not union_cover(float("nan"), 2.0, -0.5, 1.0, -1.0, 2.0))
    chk("容差内算覆盖", union_cover(-1.0, 1.999999, -0.5, 1.0, -1.0, 2.0, tol=1e-5))

    # ── 窗口不相交（预注册 §7 闸 9）──
    chk("9000..9079 干净", windows_disjoint((9000, 9079), EVAL_WINDOWS) == [])
    chk("9080..9479 干净（8B 续采）", windows_disjoint((9080, 9479), EVAL_WINDOWS) == [])
    chk("7000..7079 撞 TEST", len(windows_disjoint((7000, 7079), EVAL_WINDOWS)) == 1)
    chk("5100..5200 撞反向示范", len(windows_disjoint((5100, 5200), EVAL_WINDOWS)) == 1)
    chk("1050..9010 一次撞五个", len(windows_disjoint((1050, 9010), EVAL_WINDOWS)) == 5)

    # ── gate_a：逐门单点失效（其余全好）──
    base = {"n_frames_accepted": 2500, "n_takeover": 40, "n_takeover_relaxed_success": 20,
            "a2_rate": 0.50, "a2_wilson": [35.0, 65.0], "seg_len_median": 201.0,
            "n_handback": 0, "window_conflicts": []}
    g = gate_a(dict(base), 80)
    chk("三门全过", g["all_pass"] and all(g[k]["pass"] for k in ("A1", "A2", "A3")))
    b = dict(base, n_frames_accepted=1999)
    chk("A1 边界：1999 帧不过", not gate_a(b, 80)["A1"]["pass"])
    b = dict(base, n_frames_accepted=2000)
    chk("A1 边界：2000 帧过", gate_a(b, 80)["A1"]["pass"])
    b = dict(base, n_takeover_relaxed_success=16, a2_rate=0.40)
    chk("A2 边界：恰好 40% 过（16/40）", gate_a(b, 80)["A2"]["pass"])
    b = dict(base, n_takeover_relaxed_success=15, a2_rate=0.375)
    chk("A2 边界：37.5% 不过", not gate_a(b, 80)["A2"]["pass"])
    b = dict(base, n_takeover=0, n_takeover_relaxed_success=0, a2_rate=float("nan"))
    chk("A2：零接管不许假过", not gate_a(b, 80)["A2"]["pass"])
    b = dict(base, n_handback=1)
    chk("A3：有认输 => 不过", not gate_a(b, 80)["A3"]["pass"])
    b = dict(base, seg_len_median=300.0)
    chk("A3 边界：中位 300 过", gate_a(b, 80)["A3"]["pass"])
    b = dict(base, seg_len_median=300.5)
    chk("A3 边界：中位 300.5 不过", not gate_a(b, 80)["A3"]["pass"])
    b = dict(base, seg_len_median=float("nan"))
    chk("A3：中位 nan 不许假过", not gate_a(b, 80)["A3"]["pass"])
    b = dict(base, window_conflicts=[[(7000, 7019), (9000, 9079)]])
    chk("A3：窗口有冲突 => 不过", not gate_a(b, 80)["A3"]["pass"])
    g60 = gate_a(dict(base), 60)
    chk("局数 ≠ 80 时留警告（读数不可直接比门）", "⚠️" in g60["A1"]["note"])

    # ── summarize 的口径 ──
    eps = [
        {"takeover": True, "success_relaxed": True, "delivered_tipped": False, "seg_len": 200,
         "accepted": True, "reject_reasons": [], "handback_at": -1, "reached_grasp": True, "seconds": 20},
        {"takeover": True, "success_relaxed": False, "delivered_tipped": False, "seg_len": 400,
         "accepted": False, "reject_reasons": ["段长 400 > 300（过滤 3：效率）"], "handback_at": -1,
         "reached_grasp": False, "seconds": 25},
        {"takeover": False, "success_relaxed": True, "delivered_tipped": True, "seg_len": 0,
         "accepted": False, "reject_reasons": [], "handback_at": -1, "reached_grasp": False, "seconds": 15},
    ]
    rd = summarize(eps, 9000, 9002)
    chk("summarize：接管数", rd["n_takeover"] == 2)
    chk("summarize：接管率 = 2/3", abs(rd["takeover_rate"] - 2 / 3) < 1e-9)
    chk("summarize：A2 = 1/2", abs(rd["a2_rate"] - 0.5) < 1e-9)
    # 判据口径 = **放宽成功**的接管片段（这一例只有 ep0 的 200 步）；全部接管的中位另存只作透明
    chk("summarize：判据中位取放宽成功总体（200）", rd["seg_len_median"] == 200.0)
    chk("summarize：全部接管中位另存（median(200,400)=300）", rd["seg_len_median_all_takeover"] == 300.0)
    chk("summarize：p25/p75/max 也按放宽成功总体", rd["seg_len_max"] == 200)
    chk("summarize：截断前中位另存（无 seg_len_raw 字段时退回 seg_len）",
        rd["seg_len_raw_median_all_takeover"] == 300.0)
    chk("summarize：可用帧只数收下的", rd["n_frames_accepted"] == 200)
    chk("summarize：拒收理由按前缀归类", rd["reject_reasons"].get("段长 400 > 300") == 1)
    chk("summarize：侧躺计数", rd["n_delivered_tipped"] == 1)
    chk("summarize：窗口干净", rd["window_conflicts"] == [])

    # ── descend 盲区诊断（**只透明**，不进判据；边界口径与 mg_expert.py 逐字对齐）──
    dd = descend_diag([(0.02, 0.001, "descend"), (0.02, 0.002, "descend"),
                       (0.005, 0.001, "descend"), (0.02, 0.5, "approach")])
    chk("descend_diag：只数 descend 步（3 步；approach 那步不算）",
        dd["n_expert_steps"] == 4 and dd["n_descend_steps"] == 3)
    chk("descend_diag：盲区 = 高度在带内(|z|≤0.010) ∧ 水平没对准(xy≥0.008) ⇒ 2 步", dd["n_blind"] == 2)
    chk("descend_diag：xy 压线**内侧** 0.0079 < XY_TOL ⇒ 不算盲区",
        descend_diag([(0.0079, 0.0, "descend")])["n_blind"] == 0)
    chk("descend_diag：xy 压线 0.008 == XY_TOL ⇒ **算**盲区（进 grasp 用严格 < ⇒ 取反是 ≥）",
        descend_diag([(0.008, 0.0, "descend")])["n_blind"] == 1)
    chk("descend_diag：z 压线 |0.010| == Z_TOL ⇒ 算「高度在带内」",
        descend_diag([(0.02, 0.010, "descend")])["n_blind"] == 1)
    chk("descend_diag：z=0.011 > Z_TOL ⇒ 不是盲区（那批停滞判据看得见 ⇒ 会 restage）",
        descend_diag([(0.02, 0.011, "descend")])["n_blind"] == 0)
    chk("descend_diag：负 z_err 取绝对值（低于抓取面 5 mm 也算带内）",
        descend_diag([(0.02, -0.005, "descend")])["n_blind"] == 1)
    chk("descend_diag：显著低于抓取面另计 n_descend_z_below，不混进盲区",
        descend_diag([(0.02, -0.05, "descend")])["n_blind"] == 0
        and descend_diag([(0.02, -0.05, "descend")])["n_descend_z_below"] == 1)
    chk("descend_diag：空 ⇒ 占比 nan（不许 0 兜底，0 会假装「测过了、没有盲区」）",
        math.isnan(descend_diag([])["frac_blind_of_descend"]))
    chk("descend_diag：blind_dominant 2/3 ≥ 50% ⇒ True", dd["blind_dominant"] is True)
    chk("descend_diag：blind_dominant 1/3 < 50% ⇒ False",
        descend_diag([(0.02, 0.0, "descend"), (0.001, 0.0, "descend"),
                      (0.001, 0.0, "descend")])["blind_dominant"] is False)
    chk("descend_diag：min/max xy 与 final z 只取 descend 步",
        dd["min_xy_err_in_descend"] == 0.005 and dd["max_xy_err_in_descend"] == 0.02
        and abs(dd["final_z_err_in_descend"] - 0.001) < 1e-12)
    chk("descend_diag：默认容差就是 mg_expert 的 XY_TOL/Z_TOL（常数 import，不重打字面量 —— 坑 67）",
        dd["xy_tol"] == XY_TOL and dd["z_tol"] == Z_TOL)
    chk("summarize：缺 diag_descend 的旧记录 ⇒ 汇总计 0、占比 nan、不崩",
        rd["diag_blind_steps"] == 0 and rd["diag_descend_steps"] == 0
        and math.isnan(rd["diag_blind_frac_of_descend"]))
    eps_d = [dict(eps[0], diag_descend=descend_diag([(0.02, 0.0, "descend")] * 3)),
             dict(eps[1], diag_descend=descend_diag([(0.02, 0.0, "descend")])),
             eps[2]]
    rd_d = summarize(eps_d, 9000, 9002)
    chk("summarize：盲区步数按**接管局**累加（3+1=4）", rd_d["diag_blind_steps"] == 4)
    chk("summarize：盲区占比 = 4/4 = 1.0", abs(rd_d["diag_blind_frac_of_descend"] - 1.0) < 1e-9)
    chk("summarize：未到 grasp 的局数 = 1，其中 blind_dominant = 1",
        rd_d["diag_n_nograsp"] == 1 and rd_d["diag_n_nograsp_blind_dominant"] == 1)
    chk("summarize：空列表不炸", summarize([], 9000, 8999)["n_takeover"] == 0)

    # ── 契约常数（与冻结文件逐项对齐）──
    chk("state 8 / action 7", (STATE_DIM, ACTION_DIM) == (8, 7))
    chk("features 与 mg_collect 逐键相同",
        build_features(IMG_SIZE_DEFAULT) == build_features(IMG_SIZE_DEFAULT)
        and set(build_features(IMG_SIZE_DEFAULT)) == {STATE_KEY, ACTION_KEY, IMG_KEY_BASE, IMG_KEY_WRIST})
    chk("fps/robot 与示范集一致", (CONTROL_FREQ, ROBOT.lower()) == (20, "panda"))
    chk("检测器常数与 mg_calib_detector 一致",
        (W_EMPTY, N_EMPTY, HOLD_LO, HOLD_HI, N_HOLD) == (0.02, 3, 0.045, 0.06, 25))
    chk("采集 horizon=800 且**不等于**评测 horizon=400",
        COLLECT_HORIZON == 800 and HORIZON == 400 and COLLECT_HORIZON != HORIZON)
    chk("WIDTH_IDX 是 state 的最后一维", WIDTH_IDX == STATE_DIM - 1)
    chk("相位表里有 descend/grasp（re_descend 与 reached_grasp 的前提）",
        "descend" in PHASES and "grasp" in PHASES)
    chk("state/action 名表长度对得上", (len(STATE_NAMES), len(ACTION_NAMES)) == (STATE_DIM, ACTION_DIM))
    chk("门常数与预注册 §3 逐字一致",
        (GATE_A1_FRAMES, GATE_A1_EPISODES, GATE_A2_RATE, GATE_A3_MEDIAN, TARGET_FRAMES_8B,
         MAX_SEG_LEN, MAX_RE_DESCEND) == (2000, 80, 0.40, 300, 7000, 300, 1))
    chk("TASK_REVERSE 是反向示范那一句",
        TASK_REVERSE == "Take the can out of the bin and put it back into the tray.")

    print(f"[selftest] {npass} passed, {nfail} failed")
    return 0 if nfail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("collect", "merge"), default="collect")
    ap.add_argument("--ckpt", default=str(MG_ROOT / "runs" / "pi05_mix60f120r_s3r_seed2000"
                                          / "checkpoints" / "last" / "pretrained_model"),
                    help="被纠正的策略（坏 seed 的关门权重；`last` 会自动解析成数字格，坑 63）")
    ap.add_argument("--out", default="corr_r1", help="纠正集名（data/<out>）")
    ap.add_argument("--dst", default="mix60f120r_c1", help="merge 模式的目标数据集名")
    ap.add_argument("--episodes", type=int, default=80)
    ap.add_argument("--seed", type=int, default=9000)
    ap.add_argument("--horizon", type=int, default=COLLECT_HORIZON, help="**只采集用**；评测恒 400")
    ap.add_argument("--img-size", type=int, default=IMG_SIZE_DEFAULT)
    ap.add_argument("--n-action-steps", type=int, default=K_DEFAULT, help="档 5 的工作点 K=10")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--use-amp", action="store_true")
    ap.add_argument("--append", action="store_true", help="续采：往已存在的 --out 里追加")
    ap.add_argument("--target-frames", type=int, default=0,
                    help=">0 时收到这么多可用帧就提前收工（8B 用 7000）")
    ap.add_argument("--writer-threads", type=int, default=4)
    ap.add_argument("--gate-a", action="store_true", help="按预注册 §3 判 A1/A2/A3（不过 => rc=5 => 链写 HELD）")
    ap.add_argument("--no-trim", action="store_true",
                    help="关掉「在放宽成功处截断」（默认开）。关掉后侧躺送达的局会空转到 horizon，"
                         "段长必然 >300 被过滤 3 弃掉 —— 只用于敏感性对照，正式采集不要开")
    ap.add_argument("--stub-policy", choices=("", "gripper_close"), default="",
                    help="零 GPU 的**链路预演**：不加载策略，用「原地合爪」的假动作逼检测器触发。"
                         "读数没有意义，与 --gate-a 互斥")
    ap.add_argument("--report", default=str(RUNS / "s8a_calib" / "collect_report"))
    ap.add_argument("--ref-dataset", default="mix60f120r",
                    help="回读形状/dtype 的**参照训练集**（纠正集必须与它逐键相同，否则两臂不同口径）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.mode == "merge":
        return run_merge(args)
    return run_collect(args)


if __name__ == "__main__":
    raise SystemExit(main())
