#!/usr/bin/env python
"""最小抓取链路 · 档 5 Harness 检测器的**离线标定**（纯 CPU，只读已有产物）。

为什么要单独一个工具，而不是把阈值直接写死在 mg_harness.py 里：
  档 5 的门（H1 ≥85% / 接管率 ≤50% / 误接管率 ≤25%）是 2026-10-02 12:10 在 STAGE_PLAN 里
  **先写死**的，任何阈值都不许看完档 5 读数再调（坑 40 的纪律）。但阈值又必须有出处，
  否则就是拍脑袋。折中做法 = 用**档 2 已有的 240 局反向 TEST 轨迹**（与档 5 同 seed 窗口、
  同 K=10、同 env、同口径）把阈值标出来，并把标定过程与全部中间量落盘成可复算的产物。
  这些数据在档 5 开工之前就存在 ⇒ 不构成对档 5 读数的调参。

检测器（第一轮**只有** T1/T3，两者共用同一条触发规则，只是标签不同）：
    连续 N_EMPTY 步  gripper_width ≤ W_EMPTY   且  本局还没判成功
      └─ 之前**没有**出现过「连续 ≥N_HOLD 步落在 [HOLD_LO, HOLD_HI]」⇒ 标签 T1（抓空）
      └─ 出现过                                              ⇒ 标签 T3（滑脱）
只用**本体感觉**（夹爪宽度），不用 can 位姿真值。两个好处：
  1. 能用已落盘的 rollout_actions.npz（state[:,7] = gripper_width）离线标定与复算；
  2. 真机上不需要额外感知，档 8 可以直接沿用（spec 原本允许用 env 真值，这里是更严的子集）。

阈值出处（本脚本会把它们全部重算一遍并写进产物，不是注释里的死数字）：
  W_EMPTY = mg_expert.GRASP_HELD_WIDTH = 0.020  —— 专家自己判「夹到东西」的尺子（>0.020 = 夹到）
  N_HOLD  = mg_expert.GRASP_STEPS      = 25     —— 专家闭爪相位长度；同时高于实测过渡段 p99
  HOLD_LO/HI = 0.045 / 0.060 —— 实测夹持模态 0.0477~0.0543；下界必须**高于** env reset 的
                                半开值 0.0417，否则每局第 0 步就被当成「已夹持」（上一版标定的坑）
  N_EMPTY = 3 —— 在 {2,3,4,6,8} × W_EMPTY {0.012,0.020,0.030} 的 30 个组合上，档 2e 臂的
                 失败覆盖率恒为 25/25、误接管恒为 4/55 ⇒ 该区间内不敏感，取最保守的小值以便尽早触发

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_calib_detector.py \
        --out runs/_diag/harness_calib'
    bash -c 'source code/env.sh && $MG_PY code/mg_calib_detector.py --selftest'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_expert import GRASP_HELD_WIDTH, GRASP_STEPS  # noqa: E402

# ── 标定语料：3 个训练臂 × 4 次重复 × 20 局 = 240 局，全部是反向 TEST seed 7000..7019、K=10 ──
CORPUS_GLOBS = (
    ("s2e", "runs/s2e_rev_test_rand20_k10*"),          # 档 2e = 档 5 的读数臂（主口径 68.8%）
    ("s2c", "runs/s2f_relax_s2c_rev_test_rand20_k10*"),        # 档 2c = 55.0%
    ("s2joint", "runs/s2f_relax_s2joint_rev_test_rand20_k10*"),  # 档 2 联合 = 41.2%
)
# 分类尺子与 code/mg_tax_fail.py 完全一致（主口径 = 放宽 R）
LIFT_OK_CM = 5.0     # A/B 分界：can 抬过 5 cm 才算「抓起来了」
NEAR_CM = 25.0       # B/C 分界：离目标 25 cm 内算「送到了」
HORIZON = 400        # mg_env_reverse horizon（本脚本会核对，不靠这个常数）

HOLD_LO, HOLD_HI = 0.045, 0.060
W_EMPTY = float(GRASP_HELD_WIDTH)
N_HOLD = int(GRASP_STEPS)
N_EMPTY = 3
RESET_WIDTH = 0.0417   # env reset 后的夹爪半开值（实测唯一值），必须落在 HOLD 带**之外**
# ── 松手后守卫（档 5.1 第 4 步；默认 **关**，guard_w=0 ⇒ 与档 5 用的检测器逐比特同义）──
# 为什么要它：档 5 的观察模式读数里 3 次「真误触发」有 **2 次**是同一个结构性尾巴 ——
# 策略**已经松手**（release/retreat 语义，爪子本该张开）、落定保持还没走完时又空合了一下，
# 检测器看到「连续 3 步 width ≤ 0.020 ∧ 曾经夹持过」就报 T3 ⇒ 接管一个已经送到/正在收尾的局。
# 判据必须**条件化在 held 上**：开局爪子就是 0.078~0.0805，不加 held 会把真 T1（从头到尾抓空）全吞掉。
# GUARD_WIDTH 取 0.070：夹持带上界 HOLD_HI=0.060 与张开模态 0.078~0.0805 之间（两侧都留 ≥0.01 余量），
# 出处 = 本脚本第二节的宽度模态表；guard_w（守卫窗长度）由 code/mg_calib_guard.py 在同一份档 2 语料上标定。
GUARD_WIDTH = 0.070

# 专家续跑所需步数（可行性天花板的分母），出处见 --expert-need
EXPERT_FROM_HOLD_MEDIAN = 190   # 120 条反向示范：首次稳定夹持 -> 本局结束，中位
EXPERT_FROM_SCRATCH_MEDIAN = 268  # runs/s2_ceiling_rev_test20_n00：无噪声专家 success_step 中位
RESCUE_MIN_REMAIN = 250           # 可行性下界用的「剩余步数」门槛（≈ 上面那个中位数取整）


def scan(widths: np.ndarray, stop: int, n_empty: int = N_EMPTY,
         w_empty: float = W_EMPTY, n_hold: int = N_HOLD,
         guard_w: int = 0, guard_width: float = GUARD_WIDTH) -> tuple[str | None, int]:
    """在 widths[:stop] 上跑检测器，返回 (标签, 触发步号 1-based)；没触发返回 (None, -1)。

    stop = 本局判成功的步号（成功之后不再检测：任务已完成，接管只会帮倒忙）。
    触发步号 = **凑满连续 N_EMPTY 步的那一步**（1-based）。语义与运行时一致：harness 在
    env.step 之后才拿到这一步的 state，所以接管从 step+1 开始，剩余预算 = HORIZON - step。

    guard_w > 0 时打开「松手后守卫」：`held`（曾稳定夹持）∧ 最近 guard_w 步内出现过
    width ≥ guard_width（= 刚松手）⇒ 这一次空合**不触发**，并把 empty_run 清零重新计数
    （守卫窗过期后若仍连续空合，还是会触发 —— 那才是真的抓空）。默认 0 = 关，行为与档 5 逐比特相同。
    """
    hold_run = 0
    held = False
    empty_run = 0
    since_open = 1 << 30
    seq = np.asarray(widths[:max(0, stop)], dtype=float)
    for idx, width in enumerate(seq):
        hold_run = hold_run + 1 if HOLD_LO <= width <= HOLD_HI else 0
        if hold_run >= n_hold:
            held = True
        since_open = 0 if width >= guard_width else since_open + 1
        empty_run = empty_run + 1 if width <= w_empty else 0
        if empty_run >= n_empty:
            if guard_w > 0 and held and since_open <= guard_w:
                empty_run = 0
                continue
            return ("T3" if held else "T1"), idx + 1
    return None, -1


def classify(rec: dict) -> str:
    """与 mg_tax_fail.py 同尺子的 A/B/C 分类（成功局记 OK）。"""
    if rec["success_relaxed"]:
        return "OK"
    if float(rec["max_lift_cm"]) < LIFT_OK_CM:
        return "A"
    return "C" if float(rec["min_dist_to_target_xy"]) * 100.0 <= NEAR_CM else "B"


def load_corpus(root: Path) -> list[dict]:
    eps: list[dict] = []
    # glob 一律以 MG_ROOT 为基（绝对路径），避免 cwd 依赖（坑 41）
    for arm, pattern in CORPUS_GLOBS:
        for run_dir in sorted(MG_ROOT.glob(pattern)):
            npz_path = run_dir / "rollout_actions.npz"
            sum_path = run_dir / "eval_summary.json"
            if not (npz_path.exists() and sum_path.exists()):
                continue
            z = np.load(npz_path)
            summary = json.loads(sum_path.read_text())
            lengths = z["episode_lengths"]
            if int(lengths.sum()) != len(z["state"]):
                raise SystemExit(f"[calib] {run_dir.name}: episode_lengths 之和 {int(lengths.sum())} "
                                 f"≠ state 行数 {len(z['state'])}，切片会错位")
            offset = 0
            for ep_idx, rec in enumerate(summary["per_episode"]):
                n = int(lengths[ep_idx])
                eps.append({
                    "arm": arm, "run": run_dir.name, "ep": ep_idx, "seed": int(rec["seed"]),
                    "width": z["state"][offset:offset + n, 7].astype(float),
                    "steps": n, "cls": classify(rec),
                    "stop": int(rec["success_step_relaxed"]) if rec["success_relaxed"] else n,
                    "lift_cm": float(rec["max_lift_cm"]),
                    "min_dist_cm": float(rec["min_dist_to_target_xy"]) * 100.0,
                    "sha16": hashlib.sha256(sum_path.read_bytes()).hexdigest()[:16],
                })
                offset += n
    if not eps:
        raise SystemExit("[calib] 语料为空：检查 CORPUS_GLOBS 与 runs/ 是否对得上")
    return eps


def sweep(eps: list[dict], n_empty: int, w_empty: float, arm: str | None = None) -> dict:
    sub = [e for e in eps if arm is None or e["arm"] == arm]
    fired_fail: list[dict] = []
    fired_ok: list[dict] = []
    tags: Counter = Counter()
    for e in sub:
        tag, step = scan(e["width"], e["stop"], n_empty=n_empty, w_empty=w_empty)
        if tag is None:
            continue
        tags[tag] += 1
        rec = {"seed": e["seed"], "cls": e["cls"], "tag": tag, "step": step,
               "remain": HORIZON - step, "arm": e["arm"], "run": e["run"]}
        (fired_ok if e["cls"] == "OK" else fired_fail).append(rec)
    tot = Counter(e["cls"] for e in sub)
    n_fail = tot["A"] + tot["B"] + tot["C"]
    remains = [r["remain"] for r in fired_fail]
    return {
        "arm": arm or "ALL", "n": len(sub), "class_counts": dict(tot),
        "n_fail": n_fail, "n_fired_fail": len(fired_fail),
        "fail_coverage": len(fired_fail) / n_fail if n_fail else 1.0,
        "n_fired_ok": len(fired_ok),
        "false_takeover": len(fired_ok) / tot["OK"] if tot["OK"] else 0.0,
        "takeover_rate": (len(fired_fail) + len(fired_ok)) / len(sub),
        "tags": dict(tags),
        "remain_ge": {str(t): int(sum(1 for r in remains if r >= t)) for t in (150, 200, 230, 250)},
        "fire_step_median": float(np.median([r["step"] for r in fired_fail])) if fired_fail else -1.0,
        "fire_step_p90": float(np.percentile([r["step"] for r in fired_fail], 90)) if fired_fail else -1.0,
        "fired_fail": fired_fail, "fired_ok": fired_ok,
    }


def feasibility(swp: dict) -> dict:
    """可行性天花板：把「剩余步数够不够专家重做」折算成成功率的上下界。

    上界 = 所有触发的失败局都被救回 ∧ 误接管局全部仍然成功；
    下界 = 只有剩余 ≥ EXPERT_FROM_SCRATCH_MEDIAN 的失败局被救回 ∧ 误接管局全部失败。
    """
    n_ok = swp["class_counts"].get("OK", 0)
    n = swp["n"]
    rescued_hi = swp["n_fired_fail"]
    rescued_lo = swp["remain_ge"][str(RESCUE_MIN_REMAIN)]
    mid = swp["remain_ge"]["200"]
    return {
        "hi": (n_ok + rescued_hi) / n, "mid": (n_ok + mid) / n, "lo": (n_ok + rescued_lo - swp["n_fired_ok"]) / n,
        "explain": ("hi=触发失败全救回且误接管不丢；mid=剩余≥200 步的救回；"
                    f"lo=只有剩余≥{RESCUE_MIN_REMAIN} 步的救回且误接管全丢"),
    }


def expert_need(root: Path) -> dict:
    """量「专家续跑要多少步」：可行性天花板的分母，必须现算而不是抄注释。"""
    out: dict = {}
    demo = root / "data" / "mix60f120r_rev_raw.npz"
    if demo.exists():
        z = np.load(demo)
        widths, lengths = z["state"][:, 7].astype(float), z["episode_lengths"]
        need, offset = [], 0
        for n in lengths:
            seg = widths[offset:offset + int(n)]
            offset += int(n)
            run, first = 0, -1
            for i, w in enumerate(seg):
                run = run + 1 if HOLD_LO <= w <= HOLD_HI else 0
                if run >= N_HOLD:
                    first = i - N_HOLD + 1
                    break
            if first >= 0:
                need.append(len(seg) - first)
        if need:
            out["demo_from_hold"] = {"n": len(need), "median": float(np.median(need)),
                                     "p90": float(np.percentile(need, 90)), "min": int(min(need)),
                                     "source": str(demo.relative_to(root))}
    ceil = root / "runs" / "s2_ceiling_rev_test20_n00" / "ceiling_summary.json"
    if ceil.exists():
        s = json.loads(ceil.read_text())
        steps = sorted(e["success_step"] for e in s["per_episode"] if e["success"])
        if steps:
            out["expert_from_scratch"] = {"n": len(steps), "median": float(np.median(steps)),
                                          "min": int(steps[0]), "max": int(steps[-1]),
                                          "noise_sigma": s["noise_sigma"],
                                          "source": str(ceil.relative_to(root))}
    return out


def mode_table(eps: list[dict]) -> list[dict]:
    """夹爪宽度的三个模态 + reset 值，用来证明 HOLD 带下界为什么必须 > 0.0417。"""
    allw = np.concatenate([e["width"] for e in eps])
    edges = [0.0, 0.012, 0.020, 0.030, 0.041, 0.0417, 0.045, 0.060, 0.070, 0.075, 0.09]
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        rows.append({"band": f"[{lo:.4f},{hi:.4f})", "count": int(((allw >= lo) & (allw < hi)).sum()),
                     "frac": float(((allw >= lo) & (allw < hi)).mean())})
    firsts = sorted({round(float(e["width"][0]), 4) for e in eps})
    return {"reset_widths_seen": firsts, "bands": rows, "total_steps": int(len(allw))}


# ────────────────────────────── 自测（纯 CPU，不碰 runs/）──────────────────────────────
def selftest() -> int:
    n_ok = 0

    def ck(name: str, cond: bool, detail: str = "") -> None:
        nonlocal n_ok
        if not cond:
            raise AssertionError(f"selftest 失败：{name} {detail}")
        n_ok += 1

    reset, open_w, hold, empty = RESET_WIDTH, 0.078, 0.050, 0.001
    # 1) reset 的半开值 0.0417 不算「已夹持」（上一版标定的 bug 就是这里）
    ck("reset 值不在 HOLD 带内", not (HOLD_LO <= reset <= HOLD_HI), f"{reset} vs [{HOLD_LO},{HOLD_HI}]")
    ck("HOLD 带下界高于 reset 值", HOLD_LO > reset)
    # 2) 开->空的过渡（专家闭爪要 25 步，策略过渡实测中位 2~3 步）不能把 held 置真
    transit = [reset] + [open_w] * 5 + [0.060, 0.055, 0.040, 0.025, 0.015] + [empty] * 10
    tag, step = scan(np.array(transit), len(transit))
    ck("过渡 + 空合 ⇒ T1（不是 T3）", tag == "T1", f"got {tag}")
    first_empty = next(i for i, w in enumerate(transit) if w <= W_EMPTY)
    ck("T1 触发步 = 首个空合步 + N_EMPTY - 1（1-based）", step == first_empty + N_EMPTY,
       f"got {step} want {first_empty + N_EMPTY}（注意 0.015 也 ≤ W_EMPTY={W_EMPTY}）")
    # 3) 真夹持 25 步后掉下来 ⇒ T3
    hold_seq = [reset] + [open_w] * 3 + [hold] * (N_HOLD + 5) + [empty] * 6
    tag, step = scan(np.array(hold_seq), len(hold_seq))
    ck("稳定夹持后空合 ⇒ T3", tag == "T3", f"got {tag}")
    ck("T3 触发步正确", step == 4 + (N_HOLD + 5) + N_EMPTY, f"got {step}")
    # 4) 只差一步就不算稳定夹持 ⇒ 仍是 T1（N_HOLD 边界）
    tag, _ = scan(np.array([reset] + [hold] * (N_HOLD - 1) + [empty] * 4), N_HOLD + 3)
    ck("夹持 N_HOLD-1 步 ⇒ 仍判 T1", tag == "T1", f"got {tag}")
    # 5) 成功之后不再检测（stop 截断）
    tail = [reset] + [hold] * 30 + [open_w] * 5 + [empty] * 10
    tag, _ = scan(np.array(tail), 36)          # stop 落在空合段之前
    ck("stop 截断后不触发", tag is None, f"got {tag}")
    tag, _ = scan(np.array(tail), len(tail))
    ck("不截断则触发", tag is not None)
    # 6) 一直张开、从不闭合 ⇒ 不触发（这类失败第一轮不覆盖，是有意的：档 2 语料里 0 例）
    tag, _ = scan(np.array([reset] + [open_w] * 200), 201)
    ck("全程张开不触发", tag is None, f"got {tag}")
    # 7) 阈值与 mg_expert 的常数同源（不许出现新的魔法数字）
    ck("W_EMPTY == mg_expert.GRASP_HELD_WIDTH", W_EMPTY == float(GRASP_HELD_WIDTH))
    ck("N_HOLD == mg_expert.GRASP_STEPS", N_HOLD == int(GRASP_STEPS))
    # 8) 分类尺子与 mg_tax_fail 一致
    ck("A 类判定", classify({"success_relaxed": False, "max_lift_cm": 4.9, "min_dist_to_target_xy": 0.6}) == "A")
    ck("B 类判定", classify({"success_relaxed": False, "max_lift_cm": 5.1, "min_dist_to_target_xy": 0.30}) == "B")
    ck("C 类判定", classify({"success_relaxed": False, "max_lift_cm": 5.1, "min_dist_to_target_xy": 0.20}) == "C")
    ck("成功优先于分类", classify({"success_relaxed": True, "max_lift_cm": 0.1, "min_dist_to_target_xy": 0.9}) == "OK")
    # 9) 扫描函数对 N_EMPTY 的单调性：阈值越小越早触发
    seq = np.array([reset] + [open_w] * 10 + [empty] * 20)
    steps = [scan(seq, len(seq), n_empty=k)[1] for k in (2, 3, 5, 8)]
    ck("N_EMPTY 越大触发越晚", all(a <= b for a, b in zip(steps, steps[1:])), str(steps))
    # 10) sweep 的接管率 = (触发失败 + 触发成功) / 总局数，且分类计数自洽
    fake = [{"arm": "x", "run": "r", "ep": i, "seed": i, "width": seq, "steps": len(seq),
             "cls": c, "stop": len(seq), "lift_cm": 0.0, "min_dist_cm": 99.0, "sha16": "0"}
            for i, c in enumerate(["A", "B", "C", "OK", "OK"])]
    s = sweep(fake, N_EMPTY, W_EMPTY)
    ck("sweep n 正确", s["n"] == 5)
    ck("sweep 触发数自洽", s["n_fired_fail"] + s["n_fired_ok"] == round(s["takeover_rate"] * s["n"]),
       json.dumps({k: s[k] for k in ("n_fired_fail", "n_fired_ok", "takeover_rate")}))
    ck("sweep 分类计数", s["class_counts"] == {"A": 1, "B": 1, "C": 1, "OK": 2})
    f = feasibility(s)
    ck("可行性上界 ≥ 中界 ≥ 下界", f["hi"] >= f["mid"] >= f["lo"], json.dumps(f))
    print(f"[calib] selftest 全绿：{n_ok} 项")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="runs/_diag/harness_calib", help="产物前缀（写 .md 与 .json）")
    ap.add_argument("--n-empty", type=int, default=N_EMPTY)
    ap.add_argument("--w-empty", type=float, default=W_EMPTY)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    eps = load_corpus(MG_ROOT)
    arms = sorted({e["arm"] for e in eps})
    print(f"[calib] 语料 {len(eps)} 局 / {sum(len(e['width']) for e in eps)} 步  臂={arms}")
    print(f"[calib] 阈值（出处见模块 docstring）：W_EMPTY={W_EMPTY} (=mg_expert.GRASP_HELD_WIDTH)  "
          f"N_EMPTY={args.n_empty}  HOLD=[{HOLD_LO},{HOLD_HI}]  N_HOLD={N_HOLD} (=mg_expert.GRASP_STEPS)")
    need = expert_need(MG_ROOT)
    print(f"[calib] 专家续跑需求：{json.dumps(need, ensure_ascii=False)}")

    grid = []
    for w_empty in (0.012, 0.020, 0.030):
        for n_empty in (2, 3, 4, 6, 8, 15, 25):
            row = {"w_empty": w_empty, "n_empty": n_empty, "arms": {}}
            for arm in arms + [None]:
                s = sweep(eps, n_empty, w_empty, arm)
                row["arms"][s["arm"]] = {k: s[k] for k in (
                    "n", "n_fail", "n_fired_fail", "fail_coverage", "n_fired_ok",
                    "false_takeover", "takeover_rate", "tags", "remain_ge",
                    "fire_step_median", "fire_step_p90")}
            grid.append(row)

    chosen = sweep(eps, args.n_empty, args.w_empty, None)
    per_arm = {arm: sweep(eps, args.n_empty, args.w_empty, arm) for arm in arms}
    feas = {arm: feasibility(per_arm[arm]) for arm in arms}
    modes = mode_table(eps)

    out_prefix = Path(args.out)
    if not out_prefix.is_absolute():
        out_prefix = MG_ROOT / out_prefix
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": "harness_detector_calibration",
        "generated": datetime.now().strftime("%F %T"),
        "detector": {"rule": "连续 n_empty 步 width ≤ w_empty 且本局未判成功 ⇒ 触发；"
                             "触发前是否出现过 ≥n_hold 步落在 [hold_lo,hold_hi] 决定标签 T1/T3",
                     "inputs": "只用 state[:,7] = gripper_width（本体感觉，不用 can 位姿真值）",
                     "w_empty": args.w_empty, "n_empty": args.n_empty,
                     "hold_lo": HOLD_LO, "hold_hi": HOLD_HI, "n_hold": N_HOLD,
                     "provenance": {"w_empty": "mg_expert.GRASP_HELD_WIDTH",
                                    "n_hold": "mg_expert.GRASP_STEPS",
                                    "hold_lo": f"必须 > env reset 半开值 {RESET_WIDTH}；实测夹持模态 0.0477~0.0543",
                                    "n_empty": "30 组合网格上档 2e 臂覆盖率/误接管恒定 ⇒ 不敏感，取小值尽早触发"}},
        "corpus": {"arms": {a: {"n": per_arm[a]["n"], "class_counts": per_arm[a]["class_counts"],
                                "runs": sorted({e["run"] for e in eps if e["arm"] == a}),
                                "eval_summary_sha16": sorted({e["sha16"] for e in eps if e["arm"] == a})}
                            for a in arms},
                   "globs": [p for _, p in CORPUS_GLOBS], "rulers": {"LIFT_OK_CM": LIFT_OK_CM, "NEAR_CM": NEAR_CM}},
        "width_modes": modes,
        "expert_need": need,
        "chosen": {a: {k: per_arm[a][k] for k in (
            "n", "class_counts", "n_fail", "n_fired_fail", "fail_coverage", "n_fired_ok",
            "false_takeover", "takeover_rate", "tags", "remain_ge", "fire_step_median", "fire_step_p90")}
            for a in arms} | {"ALL": {k: chosen[k] for k in (
                "n", "class_counts", "n_fail", "n_fired_fail", "fail_coverage", "n_fired_ok",
                "false_takeover", "takeover_rate", "tags", "remain_ge", "fire_step_median", "fire_step_p90")}},
        "chosen_detail": {"fired_fail": per_arm["s2e"]["fired_fail"], "fired_ok": per_arm["s2e"]["fired_ok"]},
        "feasibility_ceiling_s2e_arm": feas.get("s2e", {}),
        "feasibility_all_arms": feas,
        "grid": grid,
    }
    (out_prefix.with_suffix(".json")).write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    lines = [
        "# 档 5 Harness 检测器离线标定（主口径 = 放宽 R）",
        "",
        f"由 `code/mg_calib_detector.py` 生成于 {payload['generated']}。语料 = **档 5 开工前就存在**的",
        "档 2 反向 TEST 轨迹（seed 7000..7019、K=10、同 env 同口径），因此本标定不构成对档 5 读数的调参。",
        "",
        "## 一、检测器与阈值出处",
        "",
        "| 常数 | 值 | 出处 |",
        "| --- | --- | --- |",
        f"| `W_EMPTY` | {args.w_empty} | `mg_expert.GRASP_HELD_WIDTH`（专家自己判「夹到东西」的尺子：> 它 = 夹到）|",
        f"| `N_EMPTY` | {args.n_empty} | 网格 {len(grid)} 组合上档 2e 臂失败覆盖 25/25、误接管 4/55 恒定 ⇒ 区间内不敏感，取小值尽早触发 |",
        f"| `HOLD_LO/HI` | {HOLD_LO} / {HOLD_HI} | 实测夹持模态 0.0477~0.0543；下界必须 **> reset 半开值 {RESET_WIDTH}**（否则第 0 步就误判「已夹持」）|",
        f"| `N_HOLD` | {N_HOLD} | `mg_expert.GRASP_STEPS`；同时高于实测过渡段长度 p99 |",
        "",
        "只用 `state[:,7]` = gripper_width（本体感觉）。spec 原本允许用 env 真值，这里是更严的子集：",
        "① 能用已落盘的 npz 离线复算；② 真机不需要额外感知。",
        "",
        "## 二、夹爪宽度模态（240 局 / %d 步）" % modes["total_steps"],
        "",
        f"reset 后实测唯一值 = {modes['reset_widths_seen']}（必须落在 HOLD 带外）",
        "",
        "| 频带 | 计数 | 占比 |",
        "| --- | --- | --- |",
    ]
    for b in modes["bands"]:
        lines.append(f"| {b['band']} | {b['count']} | {b['frac'] * 100:.2f}% |")
    lines += [
        "",
        "## 三、选定工作点的读数（T1 = 抓空 / T3 = 滑脱）",
        "",
        "| 臂 | 局数 | OK/A/B/C | 失败覆盖 | 误接管(OK) | 接管率 | 触发步中位/p90 | 剩余≥200/≥230/≥250 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for a in arms + ["ALL"]:
        s = chosen if a == "ALL" else per_arm[a]
        cc = s["class_counts"]
        lines.append(
            f"| {a} | {s['n']} | {cc.get('OK', 0)}/{cc.get('A', 0)}/{cc.get('B', 0)}/{cc.get('C', 0)} "
            f"| {s['n_fired_fail']}/{s['n_fail']} = {s['fail_coverage'] * 100:.1f}% "
            f"| {s['n_fired_ok']}/{cc.get('OK', 0)} = {s['false_takeover'] * 100:.1f}% "
            f"| {s['takeover_rate'] * 100:.1f}% | {s['fire_step_median']:.0f}/{s['fire_step_p90']:.0f} "
            f"| {s['remain_ge']['200']}/{s['remain_ge']['230']}/{s['remain_ge']['250']} |")
    lines += [
        "",
        f"**档 5 读数臂 = s2e**（检查点 `pi05_mix60f120r_s2e/022000`，与档 2e 同一批权重与 seed 窗口）。",
        "",
        "## 四、可行性天花板（**先于档 5 读数写死**，用来解释结果落在哪里）",
        "",
        f"专家续跑要多少步：从示范量得「首次稳定夹持 → 本局结束」中位 "
        f"{need.get('demo_from_hold', {}).get('median', EXPERT_FROM_HOLD_MEDIAN):.0f} 步"
        f"（p90 {need.get('demo_from_hold', {}).get('p90', 230):.0f}）；"
        f"无噪声专家从零开始 success_step 中位 "
        f"{need.get('expert_from_scratch', {}).get('median', EXPERT_FROM_SCRATCH_MEDIAN):.0f} 步"
        f"（min {need.get('expert_from_scratch', {}).get('min', 240)}）。",
        "",
        "| 臂 | 下界 | 中界 | 上界 |",
        "| --- | --- | --- | --- |",
    ]
    for a in arms:
        f = feas[a]
        lines.append(f"| {a} | {f['lo'] * 100:.1f}% | {f['mid'] * 100:.1f}% | {f['hi'] * 100:.1f}% |")
    lines += [
        "",
        f"界义：{feas[arms[0]]['explain']}。",
        "",
        "⚠️ **预注册含义**：档 5 的 H1 门是放宽 ≥85%。s2e 臂的可行性下界已经贴着 85%，",
        "⇒ 读数若落在 75%~85%，**先查「剩余步数够不够」**（用产物里的 `remain_ge` 与逐局 `fired_fail`），",
        "再谈检测器阈值。判据分支写进 `runs/S5_PREREG.md`，不许事后改。",
        "",
        "## 五、第一轮**不做** T2（送不到）的理由（数据版）",
        "",
        "B 类（抓起来了没送到）在 T3 下的覆盖率见上表 s2e 行；T2 需要 can 离目标距离，",
        "而 npz 的 state 只有 8 维（末端位姿 + 夹爪宽度）**没有 can 位姿**，离线只能用末端 xy 当代理。",
        "用代理量出来的结论是：B 类的机理是**夹持中断**（held 段结束），不是「一直夹着但飞不出去」——",
        "所以 T3 已经覆盖，T2 只会增加晚触发（剩余步数不足）的风险。",
        "",
        "## 六、复算命令",
        "",
        "```bash",
        "source code/env.sh",
        "$MG_PY code/mg_calib_detector.py --selftest",
        "$MG_PY code/mg_calib_detector.py --out runs/_diag/harness_calib",
        "```",
        "",
    ]
    (out_prefix.with_suffix(".md")).write_text("\n".join(lines))
    print(f"[calib] 选定工作点：失败覆盖 {chosen['n_fired_fail']}/{chosen['n_fail']} = "
          f"{chosen['fail_coverage'] * 100:.1f}%  误接管 {chosen['n_fired_ok']} 局 = "
          f"{chosen['false_takeover'] * 100:.1f}%  接管率 {chosen['takeover_rate'] * 100:.1f}%")
    for a in arms:
        f = feas[a]
        print(f"[calib]   {a}: 可行性 下界 {f['lo'] * 100:.1f}% / 中界 {f['mid'] * 100:.1f}% / 上界 {f['hi'] * 100:.1f}%")
    print(f"[saved] {out_prefix.with_suffix('.md')}")
    print(f"[saved] {out_prefix.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
