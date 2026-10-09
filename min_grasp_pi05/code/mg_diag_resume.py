#!/usr/bin/env python
"""档 5.1 第 1 步 · `resume()` 卡死诊断（**不判门**，只落 can 真值 + 对准残差 + 实际位移）

为什么要有这个脚本（出处 `runs/S5_SUPPLEMENT.md` 第五节）：
  档 5 正式读数里 **23 次接管有 11 次从未离开 `approach`/`descend`**，原地打转 162~305 步；
  但 `correction_segments_raw.npz` 的 `state` 只有 8 维（eef_pos + eef_quat + width），
  **没有 can 位姿**，也没有判据残差 ⇒「到底卡在 `xy_ok`（±8 mm）还是 z 带（±10 mm）」离线判不了。
  本脚本把每步的判据残差、can 真值、以及「命令了多少 vs 实际动了多少」全部落盘，
  用来把 S5_SUPPLEMENT 第三节第 4、5 条**定案**，然后才谈改专家（先量再修）。

设计约束：
  * **不改任何既有文件**（`mg_eval_harness.py` / `mg_harness.py` / `mg_expert*.py` 一个字都不动）：
    `chain_s5_timing.sh` 还要用 `mg_eval_harness.py` 判实时性门，动它 = 让待判读数的代码出身变脏。
  * 诊断口径与正式读数**完全一致**（同 ckpt / 同 env / 同 K=10 / 同 seed 窗口 / 同检测器常数），
    唯一差别是每步多记几个诊断量；**产物不参与任何门**，也不许并入 n=60（坑 40）。
  * 只 import：`mg_eval.load_policy/to_tensor_obs`（冻结文件，只读）、`mg_harness.TakeoverHarness`、
    `mg_expert` 的几何常数。

关键判别量（这三个能把「对不上」与「被挡住」分开）：
  `z_err = eef_z − can_z − GRASP_OFFSET_Z`，`xy_err = eef_xy − can_xy`：判据本身的残差；
  `dz_cmd`（由 action[2] 反解的命令位移）vs `dz_act`（实测 eef z 变化）：**命令了却不动 = 接触阻挡**；
  `dcan_xy`（can 每步位移）：**can 一直在动 = 被爪子推着滚**，8 mm 容差永远追不上。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_diag_resume.py \
        --ckpt runs/pi05_mix60f120r_s2e/checkpoints/022000/pretrained_model \
        --episodes 20 --seed 7000 --n-action-steps 10 --out runs/s5_diag_resume'
    bash -c 'source code/env.sh && $MG_PY code/mg_diag_resume.py --selftest'
    # 统计口径改了之后，在**同一份 trace** 上离线重算（不重跑仿真、不占 GPU；原版自动留档）：
    bash -c 'source code/env.sh && $MG_PY code/mg_diag_resume.py \
        --reanalyze runs/s5_diag_resume --reanalyze-reason "修 stuck_verdict 的 mm/m 单位 bug（坑 48）"'
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
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

import torch  # noqa: E402

from mg_env import STATE_KEY, SingleArmGraspEnv  # noqa: E402
from mg_eval import load_policy, to_tensor_obs  # noqa: E402  （只 import，绝不改 mg_eval.py）
from mg_expert import (  # noqa: E402
    GRASP_OFFSET_Z, PRE_HEIGHT, SPEED, STEP_SCALE, XY_TOL, Z_TOL,
)
from mg_harness import GraspDetector, SegmentBuffer, TakeoverHarness  # noqa: E402

RUNS = MG_ROOT / "runs"
WIDTH_IDX = 7
PHASES = ["init", "approach", "descend", "grasp", "lift", "settle", "carry",
          "place_descend", "release", "retreat", "done"]
PHASE_ID = {p: i for i, p in enumerate(PHASES)}
# 每步诊断量的列名（落盘顺序 = 本列表）
TRACE_COLS = ["step", "src", "phase", "phase_step", "eef_x", "eef_y", "eef_z", "width",
              "can_x", "can_y", "can_z", "tilt", "xy_err_x", "xy_err_y", "z_err",
              "dz_cmd", "dz_act", "dcan_xy", "act_x", "act_y", "act_z"]
# 「命令了却没动」的阈值：命令位移 ≥1 mm 而实测 <20% ⇒ 判接触阻挡
CMD_MIN_M = 0.001
PROGRESS_RATIO = 0.20
# can 每步位移超过它 ⇒ 判「can 在被推着走」
CAN_MOVING_M = 0.0005


# ── 纯函数（可自测，不碰仿真）─────────────────────────────────────────────
def residuals(eef: np.ndarray, can: np.ndarray) -> tuple[float, float, float]:
    """返回 (xy_err_x, xy_err_y, z_err)；与 mg_expert 的 descend→grasp 判据同一个定义。"""
    return (float(eef[0] - can[0]), float(eef[1] - can[1]),
            float(eef[2] - can[2] - GRASP_OFFSET_Z))


def xy_ok(ex: float, ey: float, tol: float = XY_TOL) -> bool:
    return abs(ex) < tol and abs(ey) < tol


def z_ok(ez: float, tol: float = Z_TOL) -> bool:
    return abs(ez) < tol


def blocker(ex: float, ey: float, ez: float) -> str:
    """descend 相位某一步「卡在哪个条件」：ok / xy / z_above / z_below / xy+z_above / xy+z_below。"""
    x_bad, z_bad = not xy_ok(ex, ey), not z_ok(ez)
    if not x_bad and not z_bad:
        return "ok"
    ztag = "" if not z_bad else ("z_above" if ez > 0 else "z_below")
    if x_bad and z_bad:
        return f"xy+{ztag}"
    return "xy" if x_bad else ztag


def dz_commanded(act_z: float, phase: str) -> float:
    """由动作反解「这一步命令了多少 z 位移」（m）。action = clip(delta/STEP_SCALE,-1,1)*speed。"""
    speed = SPEED.get(phase, 1.0)
    if speed <= 0:
        return 0.0
    u = float(act_z) / speed
    return float(np.clip(u, -1.0, 1.0) * STEP_SCALE)


def stuck_verdict(rows: np.ndarray, cols: dict[str, int]) -> dict:
    """对一次接管的 descend 步做统计，给出**主因**判定。rows = 该局诊断矩阵（含策略段）。"""
    ix = {k: cols[k] for k in cols}
    desc = rows[rows[:, ix["phase"]] == PHASE_ID["descend"]]
    out = {"descend_steps": int(len(desc)), "blocker_census": {}, "verdict": "无 descend 步"}
    if len(desc) == 0:
        return out
    cens: dict[str, int] = {}
    for r in desc:
        tag = blocker(r[ix["xy_err_x"]], r[ix["xy_err_y"]], r[ix["z_err"]])
        cens[tag] = cens.get(tag, 0) + 1
    out["blocker_census"] = cens
    out["med_abs_xy_err_mm"] = float(np.median(np.hypot(desc[:, ix["xy_err_x"]],
                                                       desc[:, ix["xy_err_y"]])) * 1000)
    out["med_z_err_mm"] = float(np.median(desc[:, ix["z_err"]]) * 1000)
    out["med_dcan_xy_mm"] = float(np.median(desc[:, ix["dcan_xy"]]) * 1000)
    # 命令了下降却没动 ⇒ 接触阻挡
    want = desc[:, ix["dz_cmd"]] < -CMD_MIN_M
    if want.sum() > 0:
        ratio = np.abs(desc[want, ix["dz_act"]]) / np.abs(desc[want, ix["dz_cmd"]])
        out["n_cmd_descend"] = int(want.sum())
        out["frac_cmd_blocked"] = float(np.mean(ratio < PROGRESS_RATIO))
    else:
        out["n_cmd_descend"] = 0
        out["frac_cmd_blocked"] = float("nan")
    dom = max(cens, key=lambda k: cens[k])
    xy_share = cens.get("xy", 0) + cens.get("xy+z_above", 0) + cens.get("xy+z_below", 0)
    z_above = cens.get("z_above", 0) + cens.get("xy+z_above", 0)
    blocked = out.get("frac_cmd_blocked", float("nan"))
    # med_dcan_xy_mm 已经是 mm，只能和 CAN_MOVING_M*1000 比（旧版多乘了一次 1000 ⇒
    # 0.005 mm 的静止 can 被判成「被推着走」，见 README 坑 48）
    if xy_share / len(desc) >= 0.5 and out["med_dcan_xy_mm"] >= CAN_MOVING_M * 1000:
        out["verdict"] = "XY 追不上：can 在被推着走（每步中位位移 %.2f mm）" % out["med_dcan_xy_mm"]
    elif xy_share / len(desc) >= 0.5:
        out["verdict"] = "XY 对不上：can 静止但末端进不了 ±%.0f mm（中位误差 %.1f mm）" % (
            XY_TOL * 1000, out["med_abs_xy_err_mm"])
    elif z_above / len(desc) >= 0.5 and blocked == blocked and blocked >= 0.5:
        out["verdict"] = "Z 下不去：命令下降却不动（%.0f%% 的下降步实测位移 <%.0f%% 命令）⇒ 接触阻挡" % (
            blocked * 100, PROGRESS_RATIO * 100)
    elif z_above / len(desc) >= 0.5:
        out["verdict"] = "Z 停在抓取带上方（中位 %+.1f mm），但没有接触阻挡证据 ⇒ 控制器稳态误差" % out["med_z_err_mm"]
    elif cens.get("z_below", 0) / len(desc) >= 0.5:
        out["verdict"] = "Z 掉到抓取带下方（中位 %+.1f mm）⇒ can 比静止值低（侧躺/沉底）" % out["med_z_err_mm"]
    else:
        out["verdict"] = "混合：主因标签 %s（占比 %.0f%%），无单一主因" % (dom, 100 * cens[dom] / len(desc))
    return out


def code_sha() -> dict:
    """记录参与本产物的代码出身（坑 41/42：产物必须能自证出身）。"""
    names = ("mg_diag_resume.py", "mg_harness.py", "mg_expert.py", "mg_expert_reverse.py", "mg_eval_harness.py")
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            for p in sorted(HERE.glob("mg_*.py")) if p.name in names}


def build_report(per_ep: list[dict], meta: dict) -> str:
    """把逐局记录渲染成 `diag_resume.md`。meta 需含：
    generated / ckpt / task / K / episodes / seed / seed_mode / horizon / elapsed_s，
    以及（仅重算版）reanalyze / reanalyzed_at。渲染是纯函数 ⇒ 离线重算与在线跑共用同一份代码。"""
    tks = [r for r in per_ep if r["takeover"]]
    stuck = [r for r in tks if not r["reached_grasp"] and r["descend_steps"] > 50]
    L = []
    L.append("# 档 5.1 · resume() 卡死诊断（**不判门**）")
    L.append("")
    if meta.get("reanalyze"):
        L.append(f"生成时间：**{meta['generated']}**　离线重算：**{meta.get('reanalyzed_at', '?')}**"
                 f"（`code/mg_diag_resume.py --reanalyze`，用时 {meta.get('elapsed_s', 0.0):.0f} s）  ")
        L.append("")
        L.append(f"> ⚠️ **本文件是重算版**，重算原因：{meta['reanalyze']}  ")
        L.append("> 只重跑了 `stuck_verdict()` 这一层**纯函数统计**，**没有重跑仿真**；输入仍是同一份 "
                 "`diag_resume_trace.npz`（float32 落盘 ⇒ 中位数末位可能与在线版差 <0.001 mm）。"
                 "重算前的原版留档为 `diag_resume.md.pre_reanalyze_*`，"
                 "旧的逐局判定留在 `diag_summary.json` 的 `per_episode_pre_reanalyze`（坑 40：不静默覆盖）。")
    else:
        L.append(f"生成时间：**{meta['generated']}**（`code/mg_diag_resume.py`，"
                 f"用时 {meta.get('elapsed_s', 0.0):.0f} s）  ")
    L.append(f"检查点：`{meta['ckpt']}`　任务：{meta['task']!r}　K={meta['K']}　局数={meta['episodes']}　"
             f"seed={meta['seed_mode']}/{meta['seed']}　horizon={meta['horizon']}")
    L.append("")
    L.append(f"判据常数：`XY_TOL={XY_TOL * 1000:.0f} mm`、`Z_TOL={Z_TOL * 1000:.0f} mm`、"
             f"`GRASP_OFFSET_Z={GRASP_OFFSET_Z * 1000:.0f} mm`、`STEP_SCALE={STEP_SCALE}`。")
    L.append("")
    L.append(f"接管 {len(tks)}/{len(per_ep)} 局；其中**卡在 descend**（>50 步未进 grasp）{len(stuck)} 局。")
    L.append("")
    L.append("| seed | 触发 | 接管步 | 剩余 | 到 grasp | 放宽 | descend 步 | 主因判定 | 接管瞬间 can 倾角 | can 离起点 xy | eef-can 距离 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in tks:
        s = r.get("takeover_snapshot") or {}
        L.append(f"| {r['seed']} | {r['trigger']} | {r['takeover_step']} | {r['takeover_remain']} | "
                 f"{'✅' if r['reached_grasp'] else '❌'} | {'✅' if r['success_relaxed'] else '❌'} | "
                 f"{r['descend_steps']} | {r['verdict']} | {s.get('can_tilt_deg')}° | "
                 f"{s.get('can_dxy_from_start_mm')} mm | {s.get('eef_can_dist_mm')} mm |")
    L.append("")
    L.append("## 主因分布（卡死的局）")
    L.append("")
    tally: dict[str, int] = {}
    for r in stuck:
        key = str(r["verdict"]).split("：")[0]
        tally[key] = tally.get(key, 0) + 1
    for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
        L.append(f"* {k}：**{v}** 局")
    if not stuck:
        L.append("* 本轮没有卡死的接管局。")
    L.append("")
    L.append("## 逐局 blocker 普查（descend 步里各判据不成立的占比）")
    L.append("")
    L.append("| seed | xy | z_above | z_below | xy+z_above | xy+z_below | ok | 中位\\|xy\\|误差 | 中位 z 误差 | 中位 can 位移 | 命令下降却被挡比例 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in tks:
        c = r.get("blocker_census") or {}
        n = max(1, r["descend_steps"])
        L.append(f"| {r['seed']} | {c.get('xy', 0) / n * 100:.0f}% | {c.get('z_above', 0) / n * 100:.0f}% | "
                 f"{c.get('z_below', 0) / n * 100:.0f}% | {c.get('xy+z_above', 0) / n * 100:.0f}% | "
                 f"{c.get('xy+z_below', 0) / n * 100:.0f}% | {c.get('ok', 0) / n * 100:.0f}% | "
                 f"{r.get('med_abs_xy_err_mm')} mm | {r.get('med_z_err_mm')} mm | {r.get('med_dcan_xy_mm')} mm | "
                 f"{r.get('frac_cmd_blocked')} |")
    L.append("")
    L.append("---")
    L.append("⚠️ 本产物**不参与任何门**、**不并入** `runs/S5_VERDICT.md` 的 n=60（坑 40 纪律）；"
             "用途只有一个：把 `runs/S5_SUPPLEMENT.md` 第三节第 4、5 条定案，作为档 5.1 修专家的依据。")
    return "\n".join(L) + "\n"


def write_summary(out_dir: Path, per_ep: list[dict], meta: dict, extra: dict | None = None) -> None:
    tks = [r for r in per_ep if r["takeover"]]
    stuck = [r for r in tks if not r["reached_grasp"] and r["descend_steps"] > 50]
    payload = {k: meta[k] for k in ("generated", "ckpt", "task", "task_mode", "K", "episodes",
                                   "seed", "seed_mode", "horizon", "constants")}
    payload.update({"n_takeover": len(tks), "n_stuck": len(stuck), "per_episode": per_ep,
                    "code_sha256_16": code_sha(),
                    "gates": "本产物不判门；实时性/成功率一律不采信本读"})
    if extra:
        payload.update(extra)
    (out_dir / "diag_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                               encoding="utf-8")


SV_KEYS = ("med_abs_xy_err_mm", "med_z_err_mm", "med_dcan_xy_mm", "n_cmd_descend", "frac_cmd_blocked")


def sv_to_record(sv: dict) -> dict:
    """把 stuck_verdict 的输出压成逐局记录里那几个字段（与在线跑同一条口径）。"""
    rec = {k: sv[k] for k in ("descend_steps", "blocker_census", "verdict") if k in sv}
    for k in SV_KEYS:
        if k in sv:
            rec[k] = round(sv[k], 3) if isinstance(sv[k], float) else sv[k]
    return rec


def reanalyze(out_dir: Path, reason: str) -> int:
    """离线重算：读盘上的 trace + summary，重跑 stuck_verdict，重写 md（原版留档）。
    不碰仿真、不占 GPU ⇒ 修了统计口径之后可以在**同一份数据**上重出结论（坑 40：不静默覆盖）。"""
    t0 = time.perf_counter()
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = MG_ROOT / out_dir
    npz_p, js_p = out_dir / "diag_resume_trace.npz", out_dir / "diag_summary.json"
    for p in (npz_p, js_p):
        if not p.is_file():
            raise SystemExit(f"[diag] --reanalyze 缺产物：{p}（坑 41：路径自查）")
    with np.load(npz_p, allow_pickle=False) as z:
        trace = z["trace"].astype(np.float64)
        lengths = z["episode_lengths"].astype(int).tolist()
        seeds = z["seeds"].astype(int).tolist()
        cols_arr = [str(c) for c in z["cols"]]
        phases_arr = [str(p) for p in z["phases"]]
    if cols_arr != TRACE_COLS or phases_arr != PHASES:
        raise SystemExit("[diag] --reanalyze 拒绝：npz 的列名/相位表与当前代码不一致（出身不符）")
    summ = json.loads(js_p.read_text(encoding="utf-8"))
    consts = summ.get("constants") or {}
    for k, v in (("XY_TOL", XY_TOL), ("Z_TOL", Z_TOL), ("GRASP_OFFSET_Z", GRASP_OFFSET_Z),
                 ("STEP_SCALE", STEP_SCALE)):
        if k in consts and abs(float(consts[k]) - float(v)) > 1e-12:
            raise SystemExit(f"[diag] --reanalyze 拒绝：判据常数 {k} 已变（盘上 {consts[k]} vs 现在 {v}）"
                             "⇒ 重算会把新口径混进旧读数")
    per_old = copy.deepcopy(summ["per_episode"])
    per_ep = copy.deepcopy(summ["per_episode"])
    if len(per_ep) != len(lengths) or len(seeds) != len(lengths):
        raise SystemExit(f"[diag] --reanalyze 拒绝：局数对不上（summary {len(per_ep)} vs trace {len(lengths)}）")
    cols = {c: i for i, c in enumerate(TRACE_COLS)}
    changed, off = [], 0
    for i, (ln, rec) in enumerate(zip(lengths, per_ep)):
        if int(rec["seed"]) != int(seeds[i]):
            raise SystemExit(f"[diag] --reanalyze 拒绝：第 {i} 局 seed 对不上（{rec['seed']} vs {seeds[i]}）")
        mat = trace[off:off + ln]
        off += ln
        if not rec["takeover"]:
            continue
        sv = stuck_verdict(mat[mat[:, cols["src"]] == 1], cols)
        new = sv_to_record(sv)
        old = {k: rec.get(k) for k in new}
        if any(old.get(k) != new[k] for k in new):
            changed.append({"ep": rec["ep"], "seed": rec["seed"],
                            "old_verdict": old.get("verdict"), "new_verdict": new["verdict"]})
        rec.update(new)
    if off != len(trace):
        raise SystemExit(f"[diag] --reanalyze 拒绝：episode_lengths 之和 {off} != trace 行数 {len(trace)}")
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    md_p = out_dir / "diag_resume.md"
    if md_p.is_file():
        shutil.copy2(md_p, out_dir / f"diag_resume.md.pre_reanalyze_{stamp}")
    shutil.copy2(js_p, out_dir / f"diag_summary.json.pre_reanalyze_{stamp}")
    meta = {k: summ.get(k) for k in ("generated", "ckpt", "task", "task_mode", "K", "episodes",
                                     "seed", "seed_mode", "horizon", "constants")}
    meta["reanalyze"] = reason or "（未给原因——房规要求写明）"
    meta["reanalyzed_at"] = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    meta["elapsed_s"] = time.perf_counter() - t0
    md_p.write_text(build_report(per_ep, meta), encoding="utf-8")
    write_summary(out_dir, per_ep, meta,
                  extra={"reanalyzed_at": meta["reanalyzed_at"], "reanalyze_reason": meta["reanalyze"],
                         "reanalyze_changed": changed, "per_episode_pre_reanalyze": per_old,
                         "reanalyze_note": "trace 为 float32 落盘，重算的中位数末位可能差 <0.001 mm"})
    print(f"[diag] 离线重算完成：{len(changed)} 局判定变化 ⇒ {md_p}", flush=True)
    for c in changed:
        print(f"       seed={c['seed']}\n         旧: {c['old_verdict']}\n         新: {c['new_verdict']}",
              flush=True)
    return 0


def selftest() -> int:
    n_ok = 0

    def ck(name: str, cond: bool, detail: str = "") -> None:
        nonlocal n_ok
        if not cond:
            raise AssertionError(f"自测失败：{name} {detail}")
        n_ok += 1

    ex, ey, ez = residuals(np.array([0.1, 0.2, 0.9]), np.array([0.102, 0.2, 0.875]))
    ck("residuals xy", abs(ex - (-0.002)) < 1e-9 and ey == 0.0, f"{ex},{ey}")
    ck("residuals z = eef-can-0.015", abs(ez - 0.010) < 1e-9, f"{ez}")
    ck("xy_ok 边界内", xy_ok(0.0079, -0.0079))
    ck("xy_ok 边界外", not xy_ok(0.0081, 0.0))
    ck("z_ok 边界内", z_ok(0.0099))
    ck("z_ok 边界外", not z_ok(0.0101))
    ck("blocker ok", blocker(0.0, 0.0, 0.0) == "ok")
    ck("blocker xy", blocker(0.02, 0.0, 0.0) == "xy")
    ck("blocker z_above", blocker(0.0, 0.0, 0.02) == "z_above")
    ck("blocker z_below", blocker(0.0, 0.0, -0.02) == "z_below")
    ck("blocker xy+z_below", blocker(0.02, 0.0, -0.02) == "xy+z_below")
    # descend 里命令 7 mm 下降 => action_z = clip(-0.007/0.05)*0.7 = -0.098；反解要拿回 -0.007
    ck("dz_commanded 反解", abs(dz_commanded(-0.098, "descend") + 0.007) < 1e-9,
       str(dz_commanded(-0.098, "descend")))
    ck("dz_commanded settle 速度 0", dz_commanded(0.5, "settle") == 0.0)
    ck("dz_commanded 饱和不外推", abs(dz_commanded(-1.0 * 0.7, "descend") + 0.05) < 1e-9)

    cols = {c: i for i, c in enumerate(TRACE_COLS)}

    def mk(n, phase="descend", ex=0.02, ez=0.02, dz_cmd=-0.005, dz_act=-0.005, dcan=0.0):
        m = np.zeros((n, len(TRACE_COLS)), dtype=np.float64)
        m[:, cols["phase"]] = PHASE_ID[phase]
        m[:, cols["xy_err_x"]] = ex
        m[:, cols["z_err"]] = ez
        m[:, cols["dz_cmd"]] = dz_cmd
        m[:, cols["dz_act"]] = dz_act
        m[:, cols["dcan_xy"]] = dcan
        return m

    v = stuck_verdict(mk(10, ez=0.0, ex=0.0), cols)
    ck("全 ok 时不进任何 blocker", v["blocker_census"].get("ok") == 10, str(v["blocker_census"]))
    v = stuck_verdict(mk(10, ex=0.02, ez=0.0, dcan=0.002), cols)
    ck("can 在动 ⇒ 判追着跑", v["verdict"].startswith("XY 追不上"), v["verdict"])
    v = stuck_verdict(mk(10, ex=0.02, ez=0.0, dcan=0.0), cols)
    ck("can 静止但 xy 超差 ⇒ 判对不上", v["verdict"].startswith("XY 对不上"), v["verdict"])
    v = stuck_verdict(mk(10, ex=0.0, ez=0.02, dz_cmd=-0.005, dz_act=-0.0001), cols)
    ck("命令下降却不动 ⇒ 判接触阻挡", v["verdict"].startswith("Z 下不去"), v["verdict"])
    v = stuck_verdict(mk(10, ex=0.0, ez=0.02, dz_cmd=-0.005, dz_act=-0.0048), cols)
    ck("在动但没到位 ⇒ 判稳态误差", v["verdict"].startswith("Z 停在抓取带上方"), v["verdict"])
    v = stuck_verdict(mk(10, ex=0.0, ez=-0.02), cols)
    ck("掉到带下方 ⇒ 判 can 偏低", v["verdict"].startswith("Z 掉到抓取带下方"), v["verdict"])
    v = stuck_verdict(mk(10, phase="approach"), cols)
    ck("没有 descend 步 ⇒ 明确说无", v["descend_steps"] == 0 and v["verdict"] == "无 descend 步")

    # ── 单位 bug 回归（坑 48）：med_dcan_xy_mm 已经是 mm，绝不能再乘 1000 ──
    v = stuck_verdict(mk(10, ex=0.02, ez=0.0, dcan=0.000005), cols)
    ck("can 每步 0.005 mm ⇒ 判静止（旧版会误判成被推着走）",
       v["verdict"].startswith("XY 对不上"), v["verdict"])
    ck("误判文案不得再出现", "被推着走" not in v["verdict"], v["verdict"])
    v = stuck_verdict(mk(10, ex=0.02, ez=0.0, dcan=CAN_MOVING_M), cols)
    ck("can 每步正好 0.5 mm（=阈值）⇒ 判被推着走", v["verdict"].startswith("XY 追不上"), v["verdict"])
    v = stuck_verdict(mk(10, ex=0.02, ez=0.0, dcan=CAN_MOVING_M * 0.999), cols)
    ck("阈值下沿 ⇒ 判静止", v["verdict"].startswith("XY 对不上"), v["verdict"])

    # ── 离线重算（--reanalyze）往返：同一份 trace 上重出结论，原版必须留档 ──
    import tempfile

    def fake_npz(d: Path, cols_arr: list[str], n_policy: int = 3, n_tk: int = 60) -> None:
        m0 = mk(6, phase="approach", ex=0.0, ez=0.0)
        m0[:, cols["src"]] = 0
        tk = mk(n_tk, ex=0.02, ez=0.0, dz_cmd=-0.005, dz_act=-0.0001, dcan=0.000005)
        tk[:, cols["src"]] = 1
        m1 = np.vstack([np.zeros((n_policy, len(TRACE_COLS))), tk])
        np.savez_compressed(d / "diag_resume_trace.npz",
                            trace=np.vstack([m0, m1]).astype(np.float32),
                            episode_lengths=np.asarray([6, n_policy + n_tk], dtype=np.int32),
                            seeds=np.asarray([7000, 7001], dtype=np.int32),
                            cols=np.asarray(cols_arr), phases=np.asarray(PHASES))

    def fake_summary(bad_verdict: str) -> dict:
        rec0 = {"ep": 0, "seed": 7000, "steps": 6, "success": True, "success_step": 6,
                "success_relaxed": True, "success_step_relaxed": 6, "takeover": False,
                "trigger": None, "takeover_step": -1, "takeover_remain": -1, "expert_phases": [],
                "reached_grasp": False, "takeover_snapshot": {}, "descend_steps": 0,
                "blocker_census": {}, "verdict": "未接管"}
        rec1 = dict(rec0, ep=1, seed=7001, steps=63, success=False, success_step=-1,
                    success_relaxed=False, success_step_relaxed=-1, takeover=True, trigger="T1",
                    takeover_step=3, takeover_remain=397, expert_phases=["approach", "descend"],
                    takeover_snapshot={"can_tilt_deg": 0.5, "can_dxy_from_start_mm": 1.0,
                                       "eef_can_dist_mm": 40.0},
                    descend_steps=60, blocker_census={"xy": 60}, verdict=bad_verdict,
                    med_abs_xy_err_mm=20.0, med_z_err_mm=0.0, med_dcan_xy_mm=0.005,
                    n_cmd_descend=60, frac_cmd_blocked=1.0)
        return {"generated": "2026-10-02 22:17:12", "ckpt": "runs/fake", "task": "fake",
                "task_mode": "reverse", "K": 10, "episodes": 2, "seed": 7000,
                "seed_mode": "random", "horizon": 400,
                "constants": {"XY_TOL": XY_TOL, "Z_TOL": Z_TOL, "GRASP_OFFSET_Z": GRASP_OFFSET_Z,
                              "STEP_SCALE": STEP_SCALE, "W_EMPTY": 0.02, "N_EMPTY": 3},
                "n_takeover": 1, "n_stuck": 1, "per_episode": [rec0, rec1],
                "code_sha256_16": {}, "gates": "本产物不判门"}

    BAD = "XY 追不上：can 在被推着走（每步中位位移 0.01 mm）"
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        fake_npz(d, TRACE_COLS)
        (d / "diag_summary.json").write_text(json.dumps(fake_summary(BAD), ensure_ascii=False, indent=1),
                                             encoding="utf-8")
        (d / "diag_resume.md").write_text("# 旧版（含错误判定）\n" + BAD + "\n", encoding="utf-8")
        ck("reanalyze 返回 0", reanalyze(d, "自测：修 mm/m 单位 bug") == 0)
        md = (d / "diag_resume.md").read_text(encoding="utf-8")
        ck("md 头部标注重算版 + 原因", "本文件是重算版" in md and "自测：修 mm/m 单位 bug" in md)
        ck("md 里判定已修正", "XY 对不上" in md, md[:400])
        ck("md 里错误判定已消失", "被推着走" not in md)
        ck("md 保留原始生成时间", "2026-10-02 22:17:12" in md)
        s2 = json.loads((d / "diag_summary.json").read_text(encoding="utf-8"))
        ck("新逐局判定已改", s2["per_episode"][1]["verdict"].startswith("XY 对不上"))
        ck("旧逐局判定留档", s2["per_episode_pre_reanalyze"][1]["verdict"] == BAD)
        ck("变化清单记了且只记了 1 局", len(s2["reanalyze_changed"]) == 1
           and s2["reanalyze_changed"][0]["seed"] == 7001)
        ck("重算原因写进 json", "mm/m 单位 bug" in s2["reanalyze_reason"])
        ck("原版 md 留档", len(list(d.glob("diag_resume.md.pre_reanalyze_*"))) == 1)
        ck("原版 json 留档", len(list(d.glob("diag_summary.json.pre_reanalyze_*"))) == 1)
        ck("留档的旧 md 内容没被动过", BAD in list(d.glob("diag_resume.md.pre_reanalyze_*"))[0]
           .read_text(encoding="utf-8"))
        ck("未接管局不被改写", s2["per_episode"][0]["verdict"] == "未接管")
        # 出身不符必须拒绝（坑 41/42）：列名、判据常数、seed 对账、局长度对账
        fake_npz(d, ["bogus"] + TRACE_COLS[1:])
        try:
            reanalyze(d, "x")
            ck("列名不符必须拒绝", False)
        except SystemExit:
            ck("列名不符必须拒绝", True)
        fake_npz(d, TRACE_COLS)
        bad = fake_summary(BAD)
        bad["constants"]["XY_TOL"] = XY_TOL * 2
        (d / "diag_summary.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        try:
            reanalyze(d, "x")
            ck("判据常数变了必须拒绝", False)
        except SystemExit:
            ck("判据常数变了必须拒绝", True)
        bad = fake_summary(BAD)
        bad["per_episode"][1]["seed"] = 9999
        (d / "diag_summary.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        try:
            reanalyze(d, "x")
            ck("seed 对不上必须拒绝", False)
        except SystemExit:
            ck("seed 对不上必须拒绝", True)
        (d / "diag_summary.json").write_text(json.dumps(fake_summary(BAD), ensure_ascii=False),
                                             encoding="utf-8")
        np.savez_compressed(d / "diag_resume_trace.npz",
                            trace=np.zeros((5, len(TRACE_COLS)), dtype=np.float32),
                            episode_lengths=np.asarray([6, 63], dtype=np.int32),
                            seeds=np.asarray([7000, 7001], dtype=np.int32),
                            cols=np.asarray(TRACE_COLS), phases=np.asarray(PHASES))
        try:
            reanalyze(d, "x")
            ck("局长度对不上必须拒绝", False)
        except SystemExit:
            ck("局长度对不上必须拒绝", True)
    ck("PHASES 覆盖专家全部相位", set(PHASES) >= {"approach", "descend", "grasp", "lift", "settle", "carry",
                                                "place_descend", "release", "retreat", "done"})
    ck("TRACE_COLS 与列索引一致", len(TRACE_COLS) == len(cols))
    ck("报告渲染是纯函数（同输入同输出）",
       build_report(fake_summary(BAD)["per_episode"],
                    dict(fake_summary(BAD), elapsed_s=1.0, reanalyze=""))
       == build_report(fake_summary(BAD)["per_episode"],
                       dict(fake_summary(BAD), elapsed_s=1.0, reanalyze="")))
    print(f"[diag_resume] selftest 全绿：{n_ok} 项（纯函数，未碰仿真 / 未占 GPU）")
    return 0


# ── 主流程 ────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", default="")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7000)
    ap.add_argument("--seed-mode", choices=("fixed", "random"), default="random")
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--n-action-steps", type=int, default=10)
    ap.add_argument("--task-mode", choices=("forward", "reverse"), default="reverse")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--use-amp", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--min-remain", type=int, default=0)
    ap.add_argument("--reanalyze", default="",
                    help="只离线重算该产物目录（读 diag_resume_trace.npz + diag_summary.json，"
                         "重跑 stuck_verdict 并重写 diag_resume.md；原版留档，不重跑仿真）")
    ap.add_argument("--reanalyze-reason", default="",
                    help="重算原因，会写进产物头部与 diag_summary.json（房规：事后改口径必须写明出处）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.reanalyze:
        return reanalyze(Path(args.reanalyze), args.reanalyze_reason)
    if not args.ckpt:
        ap.error("需要 --ckpt（或用 --selftest / --reanalyze）")

    out_dir = Path(args.out) if args.out else RUNS / f"s5_diag_resume_{datetime.now():%Y%m%d_%H%M%S}"
    if not out_dir.is_absolute():
        out_dir = MG_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = Path(args.ckpt)
    if not ckpt.is_absolute():
        ckpt = MG_ROOT / ckpt

    # load_policy 要的是 torch.device（不是字符串）：与 mg_eval_harness.py:94 同一写法
    device = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    policy, pre, post = load_policy(ckpt, device, args.use_amp)
    chunk_size = int(getattr(policy.config, "chunk_size", -1))
    n_action_steps = int(getattr(policy.config, "n_action_steps", 1) or 1)
    if args.n_action_steps:
        n_action_steps = min(int(args.n_action_steps), chunk_size) if chunk_size > 0 else int(args.n_action_steps)
    policy.config.n_action_steps = n_action_steps
    policy.reset()

    if args.task_mode == "reverse":
        from mg_env_reverse import TASK_REVERSE, ReverseGraspEnv
        from mg_expert_reverse import ReverseScriptedExpert as ExpertCls
        env, task_str = ReverseGraspEnv(img_size=args.img_size), TASK_REVERSE
    else:
        from mg_expert import ScriptedExpert as ExpertCls
        env, task_str = SingleArmGraspEnv(img_size=args.img_size), TASK
    detector = GraspDetector()
    harness = TakeoverHarness(env, ExpertCls, observe_only=False, min_remain=args.min_remain,
                              detector=detector, buffer=SegmentBuffer())
    horizon = int(env.horizon)          # 先存下来：env.close() 之后不能再指望它
    print(f"[diag] mode=takeover+trace task={task_str!r} env={type(env).__name__} horizon={horizon} "
          f"K={n_action_steps} eps={args.episodes} seeds={args.seed_mode}/{args.seed}", flush=True)
    print(f"[diag] ckpt={ckpt}", flush=True)
    print(f"[diag] 判据常数 XY_TOL={XY_TOL * 1000:.0f}mm Z_TOL={Z_TOL * 1000:.0f}mm "
          f"GRASP_OFFSET_Z={GRASP_OFFSET_Z * 1000:.0f}mm PRE_HEIGHT={PRE_HEIGHT * 1000:.0f}mm "
          f"STEP_SCALE={STEP_SCALE}", flush=True)

    def policy_act(obs: dict) -> np.ndarray:
        with torch.inference_mode():
            tens = pre(to_tensor_obs(obs, device, task=task_str))
            action = post(policy.select_action(tens))
        return action.squeeze(0).detach().to("cpu").numpy().astype(np.float32)

    cols = {c: i for i, c in enumerate(TRACE_COLS)}
    per_ep: list[dict] = []
    traces: list[np.ndarray] = []
    lengths: list[int] = []
    t0 = time.perf_counter()
    for ep in range(args.episodes):
        seed = args.seed if args.seed_mode == "fixed" else args.seed + ep
        obs = env.reset(seed=seed)
        policy.reset()
        can_z0 = float(env.object_pos[2])
        can0 = np.asarray(env.object_pos, dtype=np.float64).copy()
        harness.reset(seed=seed, can_z0=can_z0)
        rows: list[list[float]] = []
        steps, succ, succ_rlx = 0, -1, -1
        prev_eef_z = float(np.asarray(obs[STATE_KEY], dtype=np.float64)[2])
        prev_can = np.asarray(env.object_pos, dtype=np.float64).copy()
        tk_snap: dict = {}
        while True:
            st = np.asarray(obs[STATE_KEY], dtype=np.float64)
            eef = st[:3].copy()
            width = float(st[WIDTH_IDX])
            can = np.asarray(env.object_pos, dtype=np.float64).copy()
            try:
                tilt = float(env.can_tilt_deg())
            except Exception:
                tilt = float("nan")
            act, source = harness.select(obs, steps, lambda: policy_act(obs))
            exp = harness.expert
            phase = exp.phase if exp is not None else "policy"
            pstep = int(exp.phase_step) if exp is not None else -1
            ex, ey, ez = residuals(eef, can)
            dz_cmd = dz_commanded(float(act[2]), phase) if exp is not None else 0.0
            if exp is not None and not tk_snap:
                tk_snap = {"can_tilt_deg": round(tilt, 2),
                           "can_dxy_from_start_mm": round(float(np.hypot(*(can[:2] - can0[:2]))) * 1000, 1),
                           "can_dz_from_start_mm": round(float(can[2] - can_z0) * 1000, 1),
                           "eef_can_dist_mm": round(float(np.linalg.norm(eef - can)) * 1000, 1),
                           "eef_z": round(float(eef[2]), 4),
                           "eef_xy_err_mm": round(float(np.hypot(ex, ey)) * 1000, 1),
                           "z_err_mm": round(ez * 1000, 1),
                           "width": round(width, 4),
                           "resume_phase": phase}
            obs, _r, terminated, truncated, info = env.step(np.asarray(act, dtype=np.float32))
            steps += 1
            new_eef = np.asarray(obs[STATE_KEY], dtype=np.float64)[:3]
            new_can = np.asarray(env.object_pos, dtype=np.float64)
            rows.append([steps - 1, 1 if source == "expert" else 0,
                         PHASE_ID.get(phase, -1), pstep, eef[0], eef[1], eef[2], width,
                         can[0], can[1], can[2], tilt, ex, ey, ez,
                         dz_cmd, float(new_eef[2] - prev_eef_z),
                         float(np.hypot(*(new_can[:2] - prev_can[:2]))),
                         float(act[0]), float(act[1]), float(act[2])])
            prev_eef_z = float(new_eef[2])
            prev_can = new_can.copy()
            if info["success"] and succ < 0:
                succ = steps
            if info.get("success_relaxed", info["success"]) and succ_rlx < 0:
                succ_rlx = steps
            harness.note_success(bool(info.get("success_relaxed", info["success"])))
            if terminated or truncated:
                break
        mat = np.asarray(rows, dtype=np.float64)
        traces.append(mat)
        lengths.append(len(mat))
        hrec = harness.finish(success=succ > 0, success_relaxed=succ_rlx > 0, steps=steps)
        tk_rows = mat[mat[:, cols["src"]] == 1] if hrec["takeover"] else np.zeros((0, len(TRACE_COLS)))
        sv = stuck_verdict(tk_rows, cols) if len(tk_rows) else {"descend_steps": 0, "verdict": "未接管",
                                                                "blocker_census": {}}
        reached = "grasp" in (hrec["expert_phases"] or [])
        rec = {"ep": ep, "seed": seed, "steps": steps, "success": succ > 0, "success_step": succ,
               "success_relaxed": succ_rlx > 0, "success_step_relaxed": succ_rlx,
               "takeover": hrec["takeover"], "trigger": hrec["trigger"],
               "takeover_step": hrec["takeover_step"], "takeover_remain": hrec["takeover_remain"],
               "expert_phases": hrec["expert_phases"], "reached_grasp": bool(reached),
               "takeover_snapshot": tk_snap, **{k: sv[k] for k in
                                               ("descend_steps", "blocker_census", "verdict")
                                               if k in sv},
               **{k: (round(sv[k], 3) if isinstance(sv.get(k), float) else sv.get(k))
                  for k in ("med_abs_xy_err_mm", "med_z_err_mm", "med_dcan_xy_mm",
                            "n_cmd_descend", "frac_cmd_blocked") if k in sv}}
        per_ep.append(rec)
        if hrec["takeover"]:
            print(f"  ep{ep} seed={seed} 接管={hrec['trigger']}@{hrec['takeover_step']} "
                  f"剩余={hrec['takeover_remain']} 到grasp={reached} 放宽={succ_rlx > 0}", flush=True)
            print(f"      接管瞬间: {tk_snap}", flush=True)
            print(f"      descend {sv['descend_steps']} 步 census={sv['blocker_census']} ⇒ {sv['verdict']}",
                  flush=True)
        else:
            print(f"  ep{ep} seed={seed} 未接管 放宽={succ_rlx > 0} steps={steps}", flush=True)

    env.close()
    np.savez_compressed(out_dir / "diag_resume_trace.npz",
                        trace=np.concatenate(traces, axis=0).astype(np.float32),
                        episode_lengths=np.asarray(lengths, dtype=np.int32),
                        seeds=np.asarray([r["seed"] for r in per_ep], dtype=np.int32),
                        cols=np.asarray(TRACE_COLS),
                        phases=np.asarray(PHASES))
    tks = [r for r in per_ep if r["takeover"]]
    stuck = [r for r in tks if not r["reached_grasp"] and r["descend_steps"] > 50]
    meta = {"generated": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "ckpt": str(ckpt), "task": task_str,
            "task_mode": args.task_mode, "K": n_action_steps, "episodes": args.episodes,
            "seed": args.seed, "seed_mode": args.seed_mode, "horizon": horizon,
            "constants": {"XY_TOL": XY_TOL, "Z_TOL": Z_TOL, "GRASP_OFFSET_Z": GRASP_OFFSET_Z,
                          "STEP_SCALE": STEP_SCALE, "W_EMPTY": detector.w_empty,
                          "N_EMPTY": detector.n_empty},
            "elapsed_s": time.perf_counter() - t0, "reanalyze": ""}
    (out_dir / "diag_resume.md").write_text(build_report(per_ep, meta), encoding="utf-8")
    write_summary(out_dir, per_ep, meta)
    print(f"[diag] 接管 {len(tks)}/{len(per_ep)}，卡死 {len(stuck)} ⇒ {out_dir / 'diag_resume.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
