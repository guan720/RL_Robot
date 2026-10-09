#!/usr/bin/env python
"""参照控制器（对方的 `PickPlaceStateMachine`）三类缺陷的**最小复现 + 逐步取证**。

为什么要单独一个脚本（`probe_contact_ceiling.py` 不够用）
--------------------------------------------------------
天花板探针只记**每局的汇总真值**（`min_bin_dist` / `final_rise` / 相位日志），
它能说"这局死在 carry 段、800 步里 `min_bin_dist` 一步没进"，但说不出**为什么**。
要把 §12.11-R.4 那三类缺陷交给对方去修，需要的是**步级**证据：
  · carry 段到底在两条分支之间怎么摆（`eef[2]` 与门限差多少、动作有没有饱和）；
  · 每次 `regrasp` 之后，夹爪究竟有没有真的夹住（`_check_grasp` 真值）；
  · `release` 段夹爪有没有张开、张开之后 can 是不是还粘在指间被 `retreat` 拖走。
本脚本只**读**对方的状态机（`make_scripted` 走的是同一条只读 import 路径），
不改他们任何文件；判定口径全部复用 `harness.env_factory` 与 `probe_contact_ceiling`
（同一个 can、同一种出题、同一套放置段真值），所以这里的 seed 与天花板探针逐题对得上。

三类缺陷（脚本会自动归类并给出决定性数字）
------------------------------------------
D1 `carry_deadlock`  对方的 carry 段是 `if 掉了 / elif 还没到搬运高度 / else 水平搬`
                      三分支（`demo_scripted_pickplace.py` 的 carry 段）。若手臂在
                      当前 xy 上**升不到**门限 `bin2[2]+CARRY_HEIGHT-0.02`，就永远进不了
                      `else` 那条水平分支 ⇒ 原地死锁。判据：carry 步数很大、
                      水平分支占比≈0、末段净位移≈0。
D2 `regrasp_loop`    carry 段掉罐后 `regrasp += 1` 回 approach，**没有次数上限**，
                      且 `lift` 的出口只看 can 高度（`can[2] > can_z0+LIFT_TARGET`），
                      不校验抓持是否真的稳 ⇒ 抓不稳→搬→掉→重抓 循环烧完预算。
                      判据：regrasp ≥ 1 且每次 lift 出口时 `_check_grasp` 为假的次数。
D3 `release_drag`    `release` 只张开 15 步、`retreat` 直接抬 10 cm，两处都**不校验 can
                      是否真的离手** ⇒ can 卡在指间/篮墙时被拖出篮，`in_bin` 只瞬时为真，
                      而成功判据的第二半（末端离 can > 4.23 cm）永远不满足。
                      判据：release 段夹爪宽度是否张开、release 结束时 `_check_grasp`
                      是否仍为真、retreat 结束时 can 的 rise。

`--carry-height` 是什么（以及为什么它不算改对方文件）
----------------------------------------------------
实测（本脚本 + 直接读 sim 的 geom）：目标篮 `bin2` 的**墙顶在 z=0.9000**（box geom
`xpos=[0.1,0.03,0.85] size=[0.21,0.01,0.05]`），而对方 carry 段的门限是
`eef_z >= bin2_z + CARRY_HEIGHT - 0.02 = 0.94`，can 吊在 eef 下约 0.017 ⇒ 搬运时
can 中心 ≈0.923、**can 底 ≈0.882 < 0.90** —— 也就是说，按当前 `CARRY_HEIGHT=0.16`，
can 在越过近侧墙板（y=0.03）时**必然与墙干涉**，能不能过去全靠搬运途中的摆动/超调
把它甩高一点。这解释了为什么四个 D1 局把 can 丢在**同一个位置**
（(0.2035, 0.0251)，正是那面墙；`min_bin_dist` 0.3753~0.37724）。
`--carry-height` 就是在**运行时**覆盖对方模块的那个常量（monkeypatch，只在本进程内、
只为验证因果），用来回答"把它抬高到能清过墙顶，D1 是否消失"。对方文件一个字节都没改。

用法
----
    /root/venvs/rlrobot/bin/python scripts/probe_scripted_defect_repro.py \
        --seeds 1010,1013,1021 --horizon 800
    # 默认跑 §12.11-R.4 那 9 个失败局 + 2 个对照（1 个成功、1 个 horizon-bound）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.env_factory import (contact_object_geom, make_contact_env,  # noqa: E402
                                 place_truth_fn, reset_contact)
from scripts.probe_contact_ceiling import (build_env, grasp_truth_fn,  # noqa: E402
                                           make_scripted_factory)

# §12.11-R.4 里那 9 个失败局 + 2 个对照（同一批 seed ⇒ 与天花板探针逐题可对）
DEFECT_SEEDS = [1010, 1012, 1018, 1023,      # D1 carry 死锁（min_bin_dist 400→800 逐位不动）
                1013, 1015, 1016,            # D2 掉罐后 regrasp 循环
                1021,                        # D3 释放不彻底、退开时把 can 拖出篮
                1009,                        # 对照：真·horizon-bound（713 步成功）
                1000]                        # 对照：健康局（162 步成功）
# 对方控制器里读不到的量（只读 import，不改他们文件），这里用他们模块的常量自己算门限
TRACE_EVERY = 20        # 每 20 步留一行轨迹，够看摆动又不把产物撑爆


def carry_gate(bin2_z: float) -> float:
    """对方 carry 段的垂直升高门限：`bin2[2] + CARRY_HEIGHT - 0.02`。"""
    from scripts.demo_scripted_pickplace import CARRY_HEIGHT
    return float(bin2_z) + float(CARRY_HEIGHT) - 0.02


def run_seed(env, task: str, seed: int, horizon: int, factory,
             trace_every: int = TRACE_EVERY) -> dict:
    """跑一局并逐步取证。返回可直接进产物的 dict。"""
    from scripts.demo_scripted_pickplace import RELEASE_STEPS, XY_TOL

    flat = reset_contact(env, seed)
    raw = env._env._get_observations()
    ctrl = factory(raw)
    inner = env._env
    grasp_fn = grasp_truth_fn(env, task)
    place_fn = place_truth_fn(env, task)
    bin2 = np.asarray(inner.bin2_pos, dtype=np.float64)
    gate = carry_gate(bin2[2])
    oid = int(getattr(inner, "object_id", 0))
    tgt = np.asarray(inner.target_bin_placements, dtype=np.float64)[oid]

    obj_pos = (lambda o: np.asarray(o["Can_pos"], dtype=np.float64)) if task == "pickplace" \
        else (lambda o: np.asarray(o["cube_pos"] if "cube_pos" in o else o["Can_pos"],
                                  dtype=np.float64))
    can0 = obj_pos(raw)
    z0 = float(can0[2])
    width_open0 = float(np.max(np.abs(np.asarray(raw["robot0_gripper_qpos"], dtype=np.float64))))

    rec = {"seed": seed, "horizon": horizon, "carry_gate_eef_z": round(gate, 4),
           "xy_tol": XY_TOL, "release_steps_cfg": RELEASE_STEPS,
           "spawn_xy": [round(float(can0[0]), 4), round(float(can0[1]), 4)],
           "spawn_z0": round(z0, 4),
           "dist_spawn_to_target": round(float(np.linalg.norm(tgt[:2] - can0[:2])), 4),
           "success": False, "success_step": None, "steps": 0,
           "phases": [], "carry_steps": 0, "carry_rise_branch": 0, "carry_move_branch": 0,
           "carry_drop_branch": 0, "carry_eef_z_min": None, "carry_eef_z_max": None,
           "carry_action_z_saturated": 0, "carry_xy_progress_last200": None,
           "regrasp_events": [], "lift_exits_without_grasp": 0, "lift_exits": 0,
           "release_width_max": None, "grasp_after_release": None,
           "rise_at_retreat_end": None, "min_dist_target": None,
           "ever_in_bin": False, "steps_in_bin": 0, "min_r_reach_in_bin": None,
           "min_rise_after_grasp": None, "trace": []}
    prev_phase = None
    prev_dist = None
    prev_log_len = len(getattr(ctrl, "log", None) or [])
    dist_200_ago = None
    held_now = False
    t0 = time.time()
    for t in range(horizon):
        action = ctrl(raw, flat)
        flat, _r, term, trunc, info = env.step(action)
        raw = env._env._get_observations()
        eef = np.asarray(raw["robot0_eef_pos"], dtype=np.float64)
        can = obj_pos(raw)
        rise = float(can[2]) - z0
        dist = float(np.linalg.norm(tgt[:2] - can[:2]))
        width = float(np.max(np.abs(np.asarray(raw["robot0_gripper_qpos"], dtype=np.float64))))
        phase = ctrl.phase
        rec["steps"] = t + 1
        rec["min_dist_target"] = dist if rec["min_dist_target"] is None else min(rec["min_dist_target"], dist)
        d_eef_can = float(np.linalg.norm(eef - can))
        rec["min_d_eef_can"] = d_eef_can if rec.get("min_d_eef_can") is None else min(rec["min_d_eef_can"], d_eef_can)
        rec["max_d_eef_can"] = d_eef_can if rec.get("max_d_eef_can") is None else max(rec["max_d_eef_can"], d_eef_can)
        rec["last_eef"] = [round(float(v), 4) for v in eef]
        rec["last_can"] = [round(float(v), 4) for v in can]
        rec["last_rise"] = round(rise, 4)
        # 抓持真值：每步都问会把每局拖慢 3 倍（见 probe_contact_ceiling 的门控说明），
        # 这里只在**相位切换点**和 release/retreat 段问 —— 那正是需要它的地方。
        phase_edge = phase != prev_phase
        want_grasp = phase_edge or phase in ("release", "retreat", "done", "lift", "carry")
        if grasp_fn is not None and want_grasp:
            g = grasp_fn()
            held_now = bool(g) if g is not None else held_now
        if phase == "carry":
            rec["carry_steps"] += 1
            rec["carry_eef_z_min"] = float(eef[2]) if rec["carry_eef_z_min"] is None \
                else min(rec["carry_eef_z_min"], float(eef[2]))
            rec["carry_eef_z_max"] = float(eef[2]) if rec["carry_eef_z_max"] is None \
                else max(rec["carry_eef_z_max"], float(eef[2]))
            az = float(np.asarray(action, dtype=np.float64).reshape(-1)[2])
            axy = np.asarray(action, dtype=np.float64).reshape(-1)[:2]
            if abs(az) > 0.99 and float(np.linalg.norm(axy)) < 1e-6:
                rec["carry_rise_branch"] += 1          # 只在垂直升（else 分支进不去）
                if az > 0.99:
                    rec["carry_action_z_saturated"] += 1
            elif float(np.linalg.norm(axy)) > 1e-6:
                rec["carry_move_branch"] += 1          # 水平搬运分支
            if rise < 0.02 and rec["carry_drop_branch"] == 0:
                rec["carry_drop_branch"] = t + 1       # 掉罐（对方按 can_z0+0.02 判）
            if t >= 200 and dist_200_ago is None:
                dist_200_ago = dist
        if phase == "release":
            rec["release_width_max"] = width if rec["release_width_max"] is None \
                else max(rec["release_width_max"], width)
        if phase_edge and prev_phase == "lift":
            rec["lift_exits"] += 1
            if not held_now:
                rec["lift_exits_without_grasp"] += 1
        # `regrasp{n}` / `grasp_retry{n}` 只进状态机的 **log**，不是它的 phase
        # （对方 `_set("approach")` 之前先 `log.append`），所以只能盯着 log 的增长看。
        log = getattr(ctrl, "log", None) or []
        if len(log) > prev_log_len:
            for entry in log[prev_log_len:]:
                if str(entry).startswith(("regrasp", "grasp_retry")):
                    rec["regrasp_events"].append({"step": t + 1, "entry": str(entry),
                                                  "rise": round(rise, 4),
                                                  "dist_target": round(dist, 4),
                                                  "can": [round(float(v), 4) for v in can],
                                                  "grasp_truth": held_now})
            prev_log_len = len(log)
        if phase_edge and prev_phase == "release":
            rec["grasp_after_release"] = held_now      # 张开之后还粘着吗（D3 的决定性数字）
        if phase_edge and prev_phase == "retreat":
            rec["rise_at_retreat_end"] = round(rise, 4)
        if place_fn is not None:
            pt = place_fn()
            if pt["in_bin"]:
                rec["ever_in_bin"] = True
                rec["steps_in_bin"] += 1
                if rec["min_r_reach_in_bin"] is None or pt["r_reach"] < rec["min_r_reach_in_bin"]:
                    rec["min_r_reach_in_bin"] = pt["r_reach"]
        if phase_edge or (t % trace_every == 0) or t >= horizon - 40:
            rec["trace"].append({"step": t + 1, "phase": phase,
                                 "eef": [round(float(v), 4) for v in eef],
                                 "can": [round(float(v), 4) for v in can],
                                 "eef_z": round(float(eef[2]), 4),
                                 "gate_minus_eef_z": round(gate - float(eef[2]), 4),
                                 "d_eef_can": round(float(np.linalg.norm(eef - can)), 4),
                                 "rise": round(rise, 4), "dist_target": round(dist, 4),
                                 "width": round(width, 4), "grasp": bool(held_now),
                                 "action": [round(float(v), 2) for v in
                                            np.asarray(action, dtype=np.float64).reshape(-1)]})
        if info.get("success") and not rec["success"]:
            rec["success"] = True
            rec["success_step"] = t + 1
            break
        prev_phase = phase
        prev_dist = dist
        if term or trunc:
            break
    if dist_200_ago is not None and prev_dist is not None:
        rec["carry_xy_progress_last_steps"] = round(dist_200_ago - prev_dist, 4)
    if grasp_fn is not None:
        g = grasp_fn()
        rec["grasp_at_end"] = bool(g) if g is not None else None
    for k in ("min_d_eef_can", "max_d_eef_can"):
        if rec.get(k) is not None:
            rec[k] = round(float(rec[k]), 4)
    for k in ("carry_eef_z_min", "carry_eef_z_max", "min_dist_target"):
        if rec.get(k) is not None:
            rec[k] = round(float(rec[k]), 4)
    if rec.get("release_width_max") is not None:
        rec["release_width_max"] = round(rec["release_width_max"], 4)
    rec["width_open0"] = round(width_open0, 4)
    rec["phases"] = list(getattr(ctrl, "log", []) or [])   # 状态机自己的相位日志才是权威
    rec["phase_at_end"] = rec["phases"][-1] if rec["phases"] else ""
    rec["grasp_ever"] = bool(rec.get("min_d_eef_can") is not None and rec["min_d_eef_can"] < 0.03)
    rec["wall_sec"] = round(time.time() - t0, 2)
    rec["defect"] = classify_defect(rec)
    return rec


def classify_defect(rec: dict) -> dict:
    """按步级证据归类缺陷。返回 `{"code", "evidence"}`；健康局 code=`none`。"""
    ev = {}
    if rec["success"]:
        return {"code": "none", "evidence": {"success_step": rec["success_step"],
                                            "regrasp_events": len(rec["regrasp_events"])}}
    carry = rec["carry_steps"]
    if carry:
        ev = {"carry_steps": carry,
              "rise_branch_frac": round(rec["carry_rise_branch"] / carry, 3),
              "move_branch_frac": round(rec["carry_move_branch"] / carry, 3),
              "action_z_saturated": rec["carry_action_z_saturated"],
              "eef_z_max_minus_gate": (round(rec["carry_eef_z_max"] - rec["carry_gate_eef_z"], 4)
                                       if rec["carry_eef_z_max"] is not None else None),
              "xy_progress_after_step200": rec.get("carry_xy_progress_last_steps"),
              "min_dist_target": rec["min_dist_target"]}
    if carry:
        ev["grasp_at_end"] = rec.get("grasp_at_end")
        ev["last_rise"] = rec.get("last_rise")
        ev["d_eef_can_range"] = [rec.get("min_d_eef_can"), rec.get("max_d_eef_can")]
        ev["last_eef"] = rec.get("last_eef")
        ev["last_can"] = rec.get("last_can")
    if rec["regrasp_events"]:
        ev["regrasp_events"] = rec["regrasp_events"]
        ev["lift_exits_without_grasp"] = f'{rec["lift_exits_without_grasp"]}/{rec["lift_exits"]}'
    if rec["release_width_max"] is not None:
        ev["release_width_max"] = rec["release_width_max"]
        ev["width_open0"] = rec["width_open0"]
        ev["grasp_after_release"] = rec["grasp_after_release"]
        ev["rise_at_retreat_end"] = rec["rise_at_retreat_end"]
        ev["steps_in_bin"] = rec["steps_in_bin"]
        ev["min_r_reach_in_bin"] = rec["min_r_reach_in_bin"]
    # 优先级：进过篮却没成功 = D3（释放/退开）；否则有 regrasp = D2；否则 carry 死锁 = D1
    if rec["ever_in_bin"]:
        return {"code": "D3_release_drag", "evidence": ev}
    if rec["regrasp_events"]:
        # 与 D1 同一根因（搬运高度清不过 0.90 的墙顶）的另一种后果：can 被撞**落回桌面**
        # （rise≈0）⇒ 对方的掉罐检测（`can[2] < can_z0+0.02`）这次会触发 ⇒ 回 approach 重抓，
        # 而重抓后仍按同一个高度搬 ⇒ 再撞，循环烧完预算。
        return {"code": "D2_regrasp_loop", "evidence": ev}
    # D1 的判据是**净推进为零**，不是"进不去水平分支"：实测 seed 1010 有 59% 的 carry 步
    # 在水平分支上、动作 xy 饱和，却 500 步没靠近篮子一步（xy_progress=0.0）。
    prog = rec.get("carry_xy_progress_last_steps")
    if carry and prog is not None and abs(prog) < 0.01:
        return {"code": "D1_carry_no_progress", "evidence": ev}
    return {"code": "unclassified", "evidence": ev}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", default="pickplace")
    ap.add_argument("--seeds", default=",".join(str(s) for s in DEFECT_SEEDS))
    ap.add_argument("--horizon", type=int, default=800)
    ap.add_argument("--pinned-object-seed", type=int, default=20260923)
    ap.add_argument("--carry-height", type=float, default=None,
                    help="实验用：运行时覆盖对方 demo_scripted_pickplace.CARRY_HEIGHT"
                         "（默认 0.16）。只影响本进程，不改对方文件")
    ap.add_argument("--trace-every", type=int, default=TRACE_EVERY)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]

    import scripts.demo_scripted_pickplace as dsp
    carry_default = float(dsp.CARRY_HEIGHT)
    if args.carry_height is not None:
        # 只在本进程覆盖模块常量：对方 carry 段每步都重新读它，所以立刻生效。
        dsp.CARRY_HEIGHT = float(args.carry_height)
        print(f"[覆盖] CARRY_HEIGHT {carry_default} -> {dsp.CARRY_HEIGHT}"
              f"（运行时 monkeypatch，对方文件未改）", flush=True)
    trace_every = int(args.trace_every)

    # 与 probe_contact_ceiling 同一个入口：pin_seed 直接传 int，构造期钉死物体尺寸随机化
    pin = None if not args.pinned_object_seed else int(args.pinned_object_seed)
    env = build_env(args.task, args.horizon, False, pin)
    factory = make_scripted_factory(args.task, env)
    inner = env._env
    geom = contact_object_geom(env, args.task, args.pinned_object_seed)

    print("=" * 92)
    print(f"参照控制器缺陷取证 · task={args.task} · horizon={args.horizon} · {len(seeds)} 局")
    print(f"物体 {geom.get('object')} mass={geom.get('body_mass_kg')} · "
          f"篮心 {geom.get('target_bin_center')} · carry 门限 eef_z>="
          f"{carry_gate(np.asarray(inner.bin2_pos, dtype=np.float64)[2]):.4f}")
    print("=" * 92, flush=True)

    rows = []
    for seed in seeds:
        rec = run_seed(env, args.task, seed, args.horizon, factory, trace_every)
        rows.append(rec)
        ev = rec["defect"]["evidence"]
        brief = {k: ev[k] for k in ("carry_steps", "rise_branch_frac", "move_branch_frac",
                                    "eef_z_max_minus_gate", "xy_progress_after_step200",
                                    "min_dist_target", "lift_exits_without_grasp",
                                    "release_width_max", "grasp_after_release",
                                    "rise_at_retreat_end", "steps_in_bin",
                                    "min_r_reach_in_bin", "grasp_at_end", "last_rise",
                                    "d_eef_can_range", "last_eef", "last_can") if k in ev}
        print(f"  seed {seed} -> {rec['defect']['code']:18s} 步={rec['steps']:3d} "
              f"success={int(rec['success'])} regrasp={len(rec['regrasp_events'])} "
              f"{rec['wall_sec']}s\n      {json.dumps(brief, ensure_ascii=False)}", flush=True)

    tally: dict[str, int] = {}
    for r in rows:
        tally[r["defect"]["code"]] = tally.get(r["defect"]["code"], 0) + 1
    out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / \
        f"{time.strftime('%Y%m%d_%H%M%S')}_scripted_defect_repro_{args.task}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "machine": {"loadavg": [round(v, 1) for v in os.getloadavg()]},
           "task": args.task, "horizon": args.horizon, "seeds": seeds,
           "controller": "scripts/demo_scripted_pickplace.py::PickPlaceStateMachine（只读 import）",
           "carry_height": float(dsp.CARRY_HEIGHT),
           "carry_height_default": carry_default,
           "carry_gate_eef_z": round(float(np.asarray(inner.bin2_pos, dtype=np.float64)[2]
                                                + dsp.CARRY_HEIGHT - 0.02), 4),
           "bin_wall_top_z": 0.90,   # 实测：bin2 的 box 墙 geom xpos_z=0.85 + size_z=0.05
           "note": "口径与 probe_contact_ceiling 完全一致（同一 pinned 物体、同一出题、"
                   "同一套放置段真值）⇒ seed 可与 runs/infra/diag_pickplace_*.json 逐题对照",
           "object_geom": geom, "tally": tally, "episodes": rows}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print("-" * 92)
    print(f"  归类汇总: {tally}")
    print(f"已写出: {out}")
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
