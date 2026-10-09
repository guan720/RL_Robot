#!/usr/bin/env python3
"""B-4：teacher 去饱和的**唯一测量仪器**（baseline 与 check 共用同一把尺）。

为什么需要它：`docs/b_normalization_incident_20260928.md` §5–§6.2 认定 over_lift 的根因是
teacher `lift` 段 dz 恒为 +1（`scripts/demo_scripted_lift_rs.py:99` 的 `target = eef + [0,0,0.3]`
经 `delta/0.05` 截断后饱和），hold/done 段恒为 0，MSE 回归在歧义区输出条件均值 → hold 段
dz 正偏 +0.052 → 无界上升。修法是「示范侧去饱和」，属 DR-001 明列的 **baseline 重置**，
必须先登记再动手，且验收标准要在**重采数据之前**钉死（否则整轮数据白费）。

本脚本是那份预登记（`docs/b_teacher_desaturation_prereg_20260928.md`）的可执行部分：
  --mode baseline  只测量、只落盘，不做任何判定（用于把「改动前」的数字锁进产物）
  --mode check     按预登记阈值逐条判定，任一 FAIL → 退出码 1

纪律：
  * 只读。不改 teacher、不改数据集、不改 A/C 的任何文件、不改门禁常量。
  * 它**不产生** RISE_CAP 的新值，只产生「按预登记规则算出来的候选值」；生效须走 DR。
  * 闭环类判据（B1–B4）需要 A 的评测产物；未提供输入时如实标 `not_measured`，
    绝不默认通过。

用法：
    # 改动前锁基线（teacher 数据集 + base-only 真值）
    python scripts/b_teacher_dz_audit.py --mode baseline \
        --data runs/infra/lerobot_act_lift_state_overfit/data \
        --base-truth runs/act_chunk_replay_20260924_k4_base_truth20.json \
        --out runs/infra/b_teacher_desat/baseline.json

    # 改动后验收（--baseline 传上一步的产物，用于单变量比对）
    python scripts/b_teacher_dz_audit.py --mode check \
        --data <new>/data --base-truth <new>/base_truth20.json \
        --baseline runs/infra/b_teacher_desat/baseline.json \
        --out runs/infra/b_teacher_desat/check.json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

DIM_NAMES = ["dx", "dy", "dz", "droll", "dpitch", "dyaw", "grip"]
DZ = 2
LIFT_PHASE = "lift"
HOLD_PHASE = "hold"
SAT_EPS = 0.99          # |a| >= 0.99 记为「命令饱和」（teacher 用 clip(delta/0.05, -1, 1)）
ZERO_EPS = 1e-6

# ---- 门禁现值（只读引用，本脚本不得修改；改动属监管裁决范围）----
FINAL_RISE_MIN = 0.04   # scripts/b_gate_controlled_success.py:38，几何锚 0.92 × 方块全高 0.04341
RISE_CAP = 0.15         # scripts/b_gate_controlled_success.py:27，≈2 × 旧 teacher base-only 0.0764
LIFT_TARGET = 0.05      # scripts/demo_scripted_lift_rs.py:48，hold 的触发高度（去饱和**不得**改它）

# ---- 预登记阈值（数值依据见 docs/b_teacher_desaturation_prereg_20260928.md §3/§4）----
PREREG = {
    # T：teacher 侧（数据集即可测，A 重采之前就能判）
    "T1_sat_frac_lift_max": 0.05,          # lift 段 dz 饱和帧占比上限（基线实测 1.000）
    "T2_mean_dz_lift_band": [0.10, 0.50],  # 去饱和后 lift 段 dz 均值应落在此带（§6.2 建议 +0.01 → dz≈0.2）
    "T3_separability_min": 0.10,           # |mean_dz(lift) − mean_dz(hold)| 下限：不得把 lift 塌进 hold
    "T4_hold_dz_absmax": ZERO_EPS,         # hold 段 teacher dz 必须仍恒为 0（单变量：只准动 lift）
    "T5_untouched_tol": 1e-6,              # 非 lift 相位的逐维统计与帧数必须与基线一致
    # A：锚点侧（新 teacher 的 base-only 真值，20 局 pinned seeds 5000–5019）
    "A1_base_success_min": 20,             # base-only 仍须 20/20，否则参考上界失效
    "A2_mean_final_rise_band": [0.050, 0.065],   # = LIFT_TARGET + 过冲 [0.000, 0.015]
    "A3_min_final_rise_margin": 0.010,     # min(final_rise) − FINAL_RISE_MIN 的下限（门禁仍可满足且有裕度）
    "A4_mean_max_rise_band": [0.052, 0.072],
    "A5_rise_cap_candidate_band": [0.10, 0.15],  # floor_to_0.01(2 × mean_max_rise) 后应落此带
    # A0 是「规则能不能复现任值」的自检：把锚点规则套在**旧** base-only 上必须精确得到 RISE_CAP=0.15。
    # 实测 2 × 0.07633 = 0.15266：floor_to_0.01 → 0.15 ✓（ceil_to_0.01 → 0.16 ✗）。
    # 门禁源码只写了「取约 2 倍」，没有可复现规则 —— 这本身是一条可复现性缺陷，见预登记 §2.3。
    "A0_rule_must_reproduce_incumbent": RISE_CAP,
    # B：闭环侧（需 A 的评测产物；未提供则 not_measured）
    "B1_over_lift_max": 0,
    "B2_insuff_max": 0,
    # B3 标定依据（预登记 §4-B3）：旧 teacher 的 clip3 臂逐帧取证 rise +0.099(f60) → +0.128(f200)
    # → +0.154(f299)，尾段速率 ≈1.9e-4 m/step 且**在 horizon 末端仍在涨**；外推 h300→h600 的
    # max_rise 漂移 ≈ +0.06 m。真停住的策略（teacher hold 段 `target = eef.copy()`）漂移 ≈ 0。
    # 阈值取两者之间靠「停住」一侧，旧行为必须 FAIL 6×/3.8× 以上，否则这条判据没有牙。
    "B3_horizon_drift_max": 0.010,         # max_rise(h=600) − max_rise(h=300) 的逐局中位数上限
    "B3_tail_rate_max": 5e-5,              # 末 100 步平均上升速率上限（m/step）
    "B4_held_dz_bias_absmax": 0.02,        # held 期间 dz_cmd 均值（旧 teacher 实测 +0.052）
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha12(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except Exception:                                   # noqa: BLE001
        return None


def _f(x) -> float | None:
    return None if x is None else float(x)


def floor_to(x: float, step: float) -> float:
    """锚点规则：向下取整到 step。cap 是**上限**，取 floor 是保守方向（更早抓到 flick）。"""
    return round(math.floor(round(x / step, 9) + 1e-9) * step, 6)


def rise_cap_rule(mean_max_rise: float | None) -> float | None:
    """RISE_CAP 的可复现规则（预登记 §2.3）：floor_to_0.01(2 × base-only mean_max_rise)。"""
    return None if mean_max_rise is None else floor_to(2.0 * float(mean_max_rise), 0.01)


# ---------------------------------------------------------------- teacher 数据集
def load_teacher(data_dir: Path, split: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """返回 (action[N,7], phase[N], 文件 sha 列表)。帧级（用 `action`，不用 `action_chunk`）。"""
    acts, phases, files = [], [], []
    for f in sorted(glob.glob(str(data_dir / "episode_*.npz"))):
        z = np.load(f)
        if split != "all" and str(z["split"]) != split:
            continue
        a = np.asarray(z["action"], dtype=np.float64)
        ph = np.asarray(z["phase"]).astype(str)
        n = min(len(a), len(ph))
        acts.append(a[:n])
        phases.append(ph[:n])
        files.append(f"{Path(f).name}:{_sha12(Path(f))}")
    if not acts:
        raise SystemExit(f"[b_teacher_dz_audit] {data_dir} 里没有 split={split} 的 episode_*.npz")
    return np.concatenate(acts), np.concatenate(phases), files


def phase_stats(act: np.ndarray, phases: np.ndarray) -> dict:
    out: dict[str, dict] = {}
    for ph in sorted(set(phases.tolist())):
        a = act[phases == ph]
        rec: dict = {"n_frames": int(len(a))}
        for i, name in enumerate(DIM_NAMES):
            col = a[:, i]
            rec[name] = {
                "mean": _f(col.mean()), "std": _f(col.std()),
                "min": _f(col.min()), "max": _f(col.max()),
                "sat_frac": _f((np.abs(col) >= SAT_EPS).mean()),
                "zero_frac": _f((np.abs(col) <= ZERO_EPS).mean()),
            }
        out[ph] = rec
    return out


def teacher_block(act: np.ndarray, phases: np.ndarray) -> dict:
    ps = phase_stats(act, phases)
    n = int(len(act))
    idle = int(sum(ps.get(p, {}).get("n_frames", 0) for p in ("done", "hold")))
    lift = ps.get(LIFT_PHASE, {}).get("dz", {})
    hold = ps.get(HOLD_PHASE, {}).get("dz", {})
    sep = None
    if lift.get("mean") is not None and hold.get("mean") is not None:
        sep = abs(lift["mean"] - hold["mean"])
    return {
        "n_frames": n,
        "phase_frame_counts": {p: ps[p]["n_frames"] for p in ps},
        "idle_frame_frac": _f(idle / n) if n else None,
        "per_phase": ps,
        "dz_lift_mean": _f(lift.get("mean")),
        "dz_lift_sat_frac": _f(lift.get("sat_frac")),
        "dz_hold_mean": _f(hold.get("mean")),
        "dz_hold_absmax": _f(max(abs(hold.get("min") or 0.0), abs(hold.get("max") or 0.0))) if hold else None,
        "dz_lift_hold_separability": _f(sep),
    }


# ---------------------------------------------------------------- base-only 真值
def base_truth_block(path: Path | None) -> dict:
    if path is None:
        return {"status": "not_provided"}
    d = json.loads(path.read_text())
    rows = d["rows"]
    mr = np.array([float(r["max_rise"]) for r in rows])
    fr = np.array([float(r["final_rise"]) for r in rows]) if all("final_rise" in r for r in rows) else None
    succ = int(sum(1 for r in rows if r.get("success_grasp_verified")))
    ends = sorted({str(r.get("phase_at_end")) for r in rows})
    held = sorted({str(r.get("held")) for r in rows})
    cap_cand = rise_cap_rule(float(mr.mean()))
    blk = {
        "source": str(path), "source_sha12": _sha12(path), "n_rows": len(rows),
        "controller": d.get("controller"),
        "success_grasp_verified": succ,
        "phase_at_end_set": ends, "held_set": held,
        "mean_max_rise": _f(mr.mean()), "min_max_rise": _f(mr.min()), "max_max_rise": _f(mr.max()),
        "rise_cap_candidate": cap_cand,
        "rise_cap_rule": "floor_to_0.01(2 * mean_max_rise)",
    }
    if fr is not None:
        blk.update({
            "mean_final_rise": _f(fr.mean()), "min_final_rise": _f(fr.min()), "max_final_rise": _f(fr.max()),
            "overshoot_over_lift_target_mean": _f(fr.mean() - LIFT_TARGET),
            "overshoot_over_lift_target_max": _f(fr.max() - LIFT_TARGET),
            "final_rise_margin_over_gate_min": _f(fr.min() - FINAL_RISE_MIN),
        }
        )
    else:
        blk["final_rise"] = "missing_in_source"
    return blk


# ---------------------------------------------------------------- 判据
def _rec(cid, metric, value, op, ok, note=""):
    return {"id": cid, "metric": metric, "value": _f(value) if isinstance(value, (int, float, np.floating)) else value,
            "criterion": op, "pass": None if ok is None else bool(ok),
            "status": "not_measured" if ok is None else ("PASS" if ok else "FAIL"), "note": note}


def in_band(v, band):
    return None if v is None else (band[0] <= v <= band[1])


def judge(rec: dict) -> dict:
    """rec 里需含 teacher / base_truth / baseline(可选) / policy(可选) 四块。"""
    P, out = PREREG, []
    t = rec["teacher"]
    out.append(_rec("T1", "dz_lift_sat_frac", t["dz_lift_sat_frac"], f"<= {P['T1_sat_frac_lift_max']}",
                    None if t["dz_lift_sat_frac"] is None else t["dz_lift_sat_frac"] <= P["T1_sat_frac_lift_max"],
                    "lift 段 dz 不再恒 ±1（去饱和的直接证据）"))
    out.append(_rec("T2", "dz_lift_mean", t["dz_lift_mean"], f"in {P['T2_mean_dz_lift_band']}",
                    in_band(t["dz_lift_mean"], P["T2_mean_dz_lift_band"]),
                    "仍保留明确的上升命令，不是把 lift 也压成 0"))
    out.append(_rec("T3", "dz_lift_hold_separability", t["dz_lift_hold_separability"],
                    f">= {P['T3_separability_min']}",
                    None if t["dz_lift_hold_separability"] is None else t["dz_lift_hold_separability"] >= P["T3_separability_min"],
                    "lift 与 hold 的命令幅度仍可区分"))
    out.append(_rec("T4", "dz_hold_absmax", t["dz_hold_absmax"], f"<= {P['T4_hold_dz_absmax']}",
                    None if t["dz_hold_absmax"] is None else t["dz_hold_absmax"] <= P["T4_hold_dz_absmax"],
                    "hold 段 teacher 未被顺手改动"))

    # T5 单变量：与 baseline 逐相位逐维比对（lift 相位除外）
    base = rec.get("baseline")
    if not base:
        out.append(_rec("T5", "single_variable_vs_baseline", None, "baseline not provided", None,
                        "check 模式必须传 --baseline，否则无法证明「只动了 lift 段」"))
    else:
        bt = base["teacher"]
        diffs, cnt_diff = [], []
        for ph, st in bt["per_phase"].items():
            if ph == LIFT_PHASE:
                continue
            ns = t["per_phase"].get(ph)
            if ns is None:
                diffs.append(f"{ph}:missing")
                continue
            if ns["n_frames"] != st["n_frames"]:
                cnt_diff.append(f"{ph}:{st['n_frames']}->{ns['n_frames']}")
            for d in DIM_NAMES:
                for k in ("mean", "std", "min", "max"):
                    a, b = ns[d][k], st[d][k]
                    if a is None or b is None or abs(a - b) > P["T5_untouched_tol"]:
                        diffs.append(f"{ph}.{d}.{k}:{b}->{a}")
        ok = not diffs and not cnt_diff
        out.append(_rec("T5", "single_variable_vs_baseline", {"stat_diffs": diffs[:12], "n_stat_diffs": len(diffs),
                                                               "frame_count_diffs": cnt_diff},
                        f"0 diff outside phase={LIFT_PHASE}", ok,
                        "非 lift 相位的 teacher 命令必须逐位不变（防夹带其他改动）"))

    # A：锚点
    a = rec["base_truth"]
    # A0：锚点规则必须能复现任值（用**旧** base-only，即 baseline 里的那份）
    ref = ((rec.get("baseline") or {}).get("base_truth") or a)
    ref_mmr = ref.get("mean_max_rise") if isinstance(ref, dict) else None
    got = rise_cap_rule(ref_mmr)
    out.append(_rec("A0", "rise_cap_rule_reproduces_incumbent",
                    {"reference_mean_max_rise": ref_mmr, "rule_output": got, "incumbent": RISE_CAP,
                     "reference_source": ref.get("source") if isinstance(ref, dict) else None},
                    f"rule(old base-only) == RISE_CAP == {P['A0_rule_must_reproduce_incumbent']}",
                    None if got is None else abs(got - P["A0_rule_must_reproduce_incumbent"]) < 1e-9,
                    "规则若连任值都复现不了，就不配用来推新值；这是防「悄悄换锚」的牙"))
    if a.get("status") == "not_provided":
        for cid in ("A1", "A2", "A3", "A4", "A5"):
            out.append(_rec(cid, "base_truth", None, "not provided", None, "缺 --base-truth"))
    else:
        out.append(_rec("A1", "base_success_grasp_verified", a["success_grasp_verified"],
                        f">= {P['A1_base_success_min']} 且 phase_at_end 全 done 且 held 全 True",
                        a["success_grasp_verified"] >= P["A1_base_success_min"]
                        and a["phase_at_end_set"] == ["done"] and a["held_set"] == ["True"],
                        "参考上界自身仍成立"))
        out.append(_rec("A2", "mean_final_rise", a.get("mean_final_rise"), f"in {P['A2_mean_final_rise_band']}",
                        in_band(a.get("mean_final_rise"), P["A2_mean_final_rise_band"]),
                        f"= LIFT_TARGET {LIFT_TARGET} + 过冲；过冲应变小但不为负"))
        out.append(_rec("A3", "final_rise_margin_over_gate_min", a.get("final_rise_margin_over_gate_min"),
                        f">= {P['A3_min_final_rise_margin']}",
                        None if a.get("final_rise_margin_over_gate_min") is None
                        else a["final_rise_margin_over_gate_min"] >= P["A3_min_final_rise_margin"],
                        f"FINAL_RISE_MIN={FINAL_RISE_MIN} 是几何锚，**不随 teacher 改**；只验门禁仍可满足且有裕度"))
        out.append(_rec("A4", "mean_max_rise", a.get("mean_max_rise"), f"in {P['A4_mean_max_rise_band']}",
                        in_band(a.get("mean_max_rise"), P["A4_mean_max_rise_band"]),
                        "新 base-only 参考上界落在预测带内"))
        out.append(_rec("A5", "rise_cap_candidate", a.get("rise_cap_candidate"),
                        f"in {P['A5_rise_cap_candidate_band']}",
                        in_band(a.get("rise_cap_candidate"), P["A5_rise_cap_candidate_band"]),
                        f"候选值 = floor_to_0.01(2 × mean_max_rise)；生效须另走 DR，现值 {RISE_CAP} 不自动变"))

    # B：闭环
    p = rec.get("policy") or {}
    out.append(_rec("B1", "over_lift_episodes", p.get("over_lift"), f"<= {P['B1_over_lift_max']}",
                    None if p.get("over_lift") is None else p["over_lift"] <= P["B1_over_lift_max"],
                    "20 局 pinned seeds 5000–5019，horizon 300"))
    out.append(_rec("B2", "insufficient_lift_episodes", p.get("insufficient_lift"), f"<= {P['B2_insuff_max']}",
                    None if p.get("insufficient_lift") is None else p["insufficient_lift"] <= P["B2_insuff_max"],
                    "insuff 应转成受控成功，不是转成 over_lift"))
    hp = rec.get("horizon_probe") or {}
    out.append(_rec("B3", "median_max_rise_drift_h600_minus_h300", hp.get("median_drift"),
                    f"<= {P['B3_horizon_drift_max']} 且 tail_rate <= {P['B3_tail_rate_max']}",
                    None if hp.get("median_drift") is None else
                    (hp["median_drift"] <= P["B3_horizon_drift_max"]
                     and (hp.get("median_tail_rate") is None or hp["median_tail_rate"] <= P["B3_tail_rate_max"])),
                    "**漂移有界性**：区分「因为停住了所以有界」与「因为 horizon 用完所以还没漂出去」"))
    out.append(_rec("B4", "held_dz_cmd_bias", p.get("held_dz_bias"), f"abs <= {P['B4_held_dz_bias_absmax']}",
                    None if p.get("held_dz_bias") is None else abs(p["held_dz_bias"]) <= P["B4_held_dz_bias_absmax"],
                    "旧 teacher 逐帧取证为 +0.052（docs/b_normalization_incident_20260928.md §5）"))

    measured = [r for r in out if r["status"] != "not_measured"]
    return {
        "criteria": out,
        "n_criteria": len(out),
        "n_measured": len(measured),
        "n_pass": sum(1 for r in measured if r["status"] == "PASS"),
        "n_fail": sum(1 for r in measured if r["status"] == "FAIL"),
        "verdict": "FAIL" if any(r["status"] == "FAIL" for r in measured)
        else ("PASS" if measured else "NOT_MEASURED"),
    }


# ---------------------------------------------------------------- 可选闭环输入
def policy_from_gate(path: Path) -> dict:
    """从门禁裁定 JSON 抽 B1/B2 计数（reclassification 或单臂裁定均可）。"""
    d = json.loads(path.read_text())
    txt = json.dumps(d)
    out: dict = {"source": str(path), "source_sha12": _sha12(path)}
    for key in ("over_lift", "insufficient_lift", "controlled_success"):
        if f'"{key}"' in txt:
            out[key] = _deep_sum(d, key)
    return out


def _deep_sum(obj, key):
    """把嵌套结构里所有 `key` 的整数计数求和（用于 reclassification 汇总）。"""
    tot = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, (int, float)):
                tot += int(v)
            else:
                tot += _deep_sum(v, key)
    elif isinstance(obj, list):
        for v in obj:
            tot += _deep_sum(v, key)
    return tot


def horizon_probe(p300: Path, p600: Path) -> dict:
    a = json.loads(p300.read_text())["rows"]
    b = json.loads(p600.read_text())["rows"]
    by = {int(r["seed"]): float(r["max_rise"]) for r in b}
    drifts = [by[int(r["seed"])] - float(r["max_rise"]) for r in a if int(r["seed"]) in by]
    return {
        "h300": str(p300), "h600": str(p600), "n_paired": len(drifts),
        "median_drift": _f(np.median(drifts)) if drifts else None,
        "max_drift": _f(np.max(drifts)) if drifts else None,
        "median_tail_rate": None,   # 需要逐帧 rise 序列，见预登记 §4-B3 的取值方式
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("baseline", "check"), required=True)
    ap.add_argument("--data", required=True, help="teacher 数据集目录（episode_*.npz）")
    ap.add_argument("--split", default="train", choices=("train", "val", "all"))
    ap.add_argument("--base-truth", default=None, help="base-only 真值 JSON（audit_lift_base_truth.py 产物）")
    ap.add_argument("--baseline", default=None, help="check 模式必传：baseline 模式的产物")
    ap.add_argument("--policy-eval", default=None, help="可选：门禁裁定 JSON，用于 B1/B2")
    ap.add_argument("--held-dz-bias", type=float, default=None, help="可选：B4，held 期间 dz_cmd 均值")
    ap.add_argument("--horizon300", default=None)
    ap.add_argument("--horizon600", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = Path(args.data)
    act, phases, files = load_teacher(data, args.split)
    rec: dict = {
        "tool": "scripts/b_teacher_dz_audit.py",
        "tool_sha12": _sha12(Path(__file__).resolve()),
        "mode": args.mode, "generated_at": _now(), "split": args.split,
        "prereg": PREREG,
        "gate_constants_readonly": {"FINAL_RISE_MIN": FINAL_RISE_MIN, "RISE_CAP": RISE_CAP,
                                    "LIFT_TARGET": LIFT_TARGET},
        "data_dir": str(data), "episode_files": files,
        "teacher": teacher_block(act, phases),
        "base_truth": base_truth_block(Path(args.base_truth) if args.base_truth else None),
    }
    if args.baseline:
        rec["baseline"] = json.loads(Path(args.baseline).read_text())
    pol = {}
    if args.policy_eval:
        pol.update(policy_from_gate(Path(args.policy_eval)))
    if args.held_dz_bias is not None:
        pol["held_dz_bias"] = args.held_dz_bias
    if pol:
        rec["policy"] = pol
    if args.horizon300 and args.horizon600:
        rec["horizon_probe"] = horizon_probe(Path(args.horizon300), Path(args.horizon600))

    if args.mode == "check":
        rec["judgement"] = judge(rec)
    else:
        rec["judgement"] = {"verdict": "BASELINE_NOT_JUDGED",
                            "note": "baseline 模式只锁数字；判定在 check 模式按同一 PREREG 执行"}

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(rec, indent=2, ensure_ascii=False))

    t = rec["teacher"]
    print(f"[b_teacher_dz_audit] mode={args.mode} frames={t['n_frames']} idle_frac={t['idle_frame_frac']:.3f}")
    print(f"  dz lift mean={t['dz_lift_mean']} sat_frac={t['dz_lift_sat_frac']} | "
          f"hold mean={t['dz_hold_mean']} absmax={t['dz_hold_absmax']} | sep={t['dz_lift_hold_separability']}")
    bt = rec["base_truth"]
    if bt.get("status") != "not_provided":
        print(f"  base-only: succ={bt['success_grasp_verified']}/{bt['n_rows']} "
              f"mean_max_rise={bt['mean_max_rise']:.5f} mean_final_rise={bt.get('mean_final_rise')} "
              f"margin_over_gate_min={bt.get('final_rise_margin_over_gate_min')} "
              f"rise_cap_candidate={bt.get('rise_cap_candidate')}")
    j = rec["judgement"]
    print(f"  verdict={j['verdict']}")
    for r in j.get("criteria", []):
        print(f"    {r['id']:<3} {r['status']:<12} {r['metric']}={r['value']}  ({r['criterion']})")
    print(f"[b_teacher_dz_audit] wrote {outp}")
    if args.mode == "check" and j["verdict"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
