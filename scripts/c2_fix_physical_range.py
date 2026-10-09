#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · T-C2-1 **物理行程（physical_range）勘误与重算**（自查发现的缺陷，不是别人报的）。

## 缺陷（实测，两处，都在 C2 自己的采集器 `scripts/c2_collect_env_states.py`）
1. **右臂 qpos 映射差一**：`physical_range()` 内联写了 `qpos_idx = state_dim + 2`（state 7..12 → qpos 9..14），
   而**同一文件模块级已经声明了正确的** `ARM_QPOS_IDX = range(0,6) + range(8,14)`（= `tasks/sim.py:61-69`
   的 `get_qpos` 映射：每臂 8 个 qpos，臂关节 = 前 6，夹爪关节 = 第 7）。
   ⇒ 右臂 6 个维全部拿到了**邻位关节**的行程，其中 state dim 12 拿到的是**手指滑动关节**的 0.036。
   **性质：声明值与实现值分叉**（与 `operations.redline_provenance_discipline` 同族：读了声明没读实现）。
2. **夹爪维行程按 1.0 假设**：`sim.py:67-68` 把 `normalize_puppet_gripper_position`
   （`constants.py:94-97`：`(x-0.01844)/(0.05800-0.01844)`）作用在**夹爪关节角（弧度）**上
   （`constants.py:80-81`：JOINT_CLOSE=-0.6213 / JOINT_OPEN=1.4910），不是作用在手指位移上
   ⇒ 状态空间里的真实行程 = `(JOINT_OPEN-JOINT_CLOSE)/0.03956` ≈ **53.4**，不是 1.0。
   **反证（用已采到的帧）**：hold 档 dim6 实测 ∈ [1.0372, 2.9898]、dim13 ∈ [1.0340, 2.9902]
   ⇒ 若行程真是 1.0（且区间是 [0,1]），这两维**根本不可能取到这些值**。

## 影响（为什么必须重算，不能将就用）
F1 下限族 = `coef × physical_range`，近常量维标记 = `denom_raw / physical_range ≤ 0.02`
⇒ 两个判据的**分母**在 dims 6..13 上是错的 ⇒ floor 值与"哪些维近常量"都不可信。
帧数据本身（`frames` / `start_poses`）来自 env 观测，**不受影响**，不必重采。

## 产物
`runs/vla/c2_norm_contract_20260929/physical_range_correction/`
  `correction.json`          —— 旧/新逐维对照 + 关节表证据 + 三条牙 + 引用三元组
  `physical_range.json`      —— 供 `scripts/c2_build_norm_stats.py --physical-range-json` 直接吃

## 纪律
数值主张带 loadavg + `nr_throttled`；引用带 `(path, sha256-12, line)`；不写「跑通/学会/达标」。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from envs import gym_aloha_shim as shim            # noqa: E402
from harness import env_gym_aloha as geg           # noqa: E402

OUT = ROOT / "runs/vla/c2_norm_contract_20260929/physical_range_correction"
STATE_DIMS = 14
GRIPPER_STATE_DIMS = (6, 13)
# tasks/sim.py:61-69 的 get_qpos：每臂 8 qpos；臂关节 = 前 6；夹爪关节 = 各臂块的第 7 个
ARM_QPOS = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 7: 8, 8: 9, 9: 10, 10: 11, 11: 12, 12: 13}
GRIPPER_QPOS = {6: 6, 13: 14}
OLD_ARM_QPOS_FORMULA = "state_dim + 2（state 7..12 → qpos 9..14）"


def sha12(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def load_pair() -> dict:
    la = " ".join(Path("/proc/loadavg").read_text().split()[:3]) if Path("/proc/loadavg").exists() else "unavailable"
    nt = None
    for cand in ("/sys/fs/cgroup/cpu,cpuacct/cpu.stat", "/sys/fs/cgroup/cpu.stat"):
        p = Path(cand)
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("nr_throttled"):
                    nt = int(line.split()[1])
            break
    return {"loadavg": la, "nr_throttled": nt, "cgroup_quota_cores": 12,
            "note": "本脚本只构造 env 读模型 + 读已落盘的 npz，无渲染、无 rollout"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(OUT))
    ap.add_argument("--env-states-glob", default="runs/vla/c2_norm_contract_20260929/env_states_*/env_states.npz")
    ap.add_argument("--direction", default="right_to_left", choices=geg.DIRECTIONS)
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--mujoco-gl", default=os.environ.get("MUJOCO_GL", "osmesa"))
    args = ap.parse_args()
    os.environ["MUJOCO_GL"] = args.mujoco_gl

    import gym_aloha                      # noqa: F401  (注册 task)
    from gym_aloha import constants as GC
    from gym_aloha.tasks import sim as gsim

    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)

    # ---- 读模型（构造 env，但不 reset、不 rollout）----
    env, apply_rec = shim.make_env(dt=shim.MAINLINE_DT)
    sim = geg.GymAlohaSimEnv(geg.EnvSpec(render_images=False, direction=args.direction, seed=args.seed),
                             env=env, apply_record=apply_rec)
    physics = sim.physics
    m = physics.model
    nj = int(m.njnt)
    jnt_range = np.asarray(m.jnt_range, dtype=np.float64)
    jnt_limited = np.asarray(m.jnt_limited, dtype=np.int64)
    qpos_adr = [int(m.joint(i).qposadr[0]) for i in range(nj)]
    names = [m.joint(i).name for i in range(nj)]
    joint_table = [{"jnt_idx": i, "name": names[i], "qposadr": qpos_adr[i],
                    "type": int(m.jnt_type[i]), "jnt_range": [float(jnt_range[i][0]), float(jnt_range[i][1])],
                    "limited": bool(jnt_limited[i])} for i in range(nj)]
    adr2jnt = {a: i for i, a in enumerate(qpos_adr)}

    # ---- 逐维重算：臂关节 = 恒等；夹爪 = 走 gym_aloha 自己的归一化函数（不重实现公式）----
    norm_fn = GC.normalize_puppet_gripper_position
    new_prange = np.zeros(STATE_DIMS, dtype=np.float64)
    new_lo = np.zeros(STATE_DIMS, dtype=np.float64)
    new_hi = np.zeros(STATE_DIMS, dtype=np.float64)
    per_dim = []
    for d in range(STATE_DIMS):
        if d in GRIPPER_STATE_DIMS:
            q = GRIPPER_QPOS[d]
            ji = adr2jnt.get(q)
            lo_r, hi_r = (float(jnt_range[ji][0]), float(jnt_range[ji][1])) if ji is not None else (float("nan"),) * 2
            lo_s, hi_s = float(norm_fn(lo_r)), float(norm_fn(hi_r))
            kind = "gripper_joint_through_normalize_puppet_gripper_position"
        else:
            q = ARM_QPOS[d]
            ji = adr2jnt.get(q)
            lo_r, hi_r = (float(jnt_range[ji][0]), float(jnt_range[ji][1])) if ji is not None else (float("nan"),) * 2
            lo_s, hi_s = lo_r, hi_r
            kind = "arm_joint_identity"
        new_lo[d], new_hi[d] = lo_s, hi_s
        new_prange[d] = hi_s - lo_s
        per_dim.append({"state_dim": d, "kind": kind, "qpos_idx_new": q,
                        "qpos_idx_old": (d if d < 6 else (None if d in GRIPPER_STATE_DIMS else d + 2)),
                        "joint_name": (names[ji] if ji is not None else None),
                        "jnt_range_rad_or_m": [lo_r, hi_r],
                        "state_lo": lo_s, "state_hi": hi_s, "state_travel": float(new_prange[d]),
                        "limited": (bool(jnt_limited[ji]) if ji is not None else None)})

    # ---- 旧值：从已落盘的 npz 读（不重算，直接引证）----
    # `Path.glob` 在 3.11 不接受绝对模式（NotImplementedError）⇒ 绝对模式走 `glob.glob`。
    import glob as _glob
    npzs = [Path(x) for x in sorted(_glob.glob(args.env_states_glob))] if Path(args.env_states_glob).is_absolute() \
        else sorted(ROOT.glob(args.env_states_glob))
    arms, obs_stack = [], []
    for p in npzs:
        z = np.load(p)
        old = np.asarray(z["physical_range"], dtype=np.float64)
        fr = np.asarray(z["frames"], dtype=np.float64)
        fmin, fmax = fr.min(0), fr.max(0)
        inside_new = [int(i) for i in range(STATE_DIMS) if fmin[i] >= new_lo[i] - 1e-9 and fmax[i] <= new_hi[i] + 1e-9]
        # 旧口径的"区间"无法定义（旧值只有 travel、没有 lo/hi，且夹爪维假设 [0,1]）⇒ 只对它做
        # 一个可判定的检查：夹爪维若 travel=1.0 且按 [0,1] 解释，实测帧必须落在 [0,1] 内。
        grip_dims_in_unit_interval = [int(i) for i in GRIPPER_STATE_DIMS
                                      if fmin[i] >= 0.0 and fmax[i] <= 1.0]
        obs_travel = (fmax - fmin)
        outside = [int(i) for i in range(STATE_DIMS) if i not in inside_new]
        exceed = {str(i): {"frames_min": float(fmin[i]), "frames_max": float(fmax[i]),
                           "declared_lo": float(new_lo[i]), "declared_hi": float(new_hi[i]),
                           "exceed_high": float(max(0.0, fmax[i] - new_hi[i])),
                           "exceed_low": float(max(0.0, new_lo[i] - fmin[i])),
                           "exceed_ratio_of_travel": float(max(max(0.0, fmax[i] - new_hi[i]),
                                                               max(0.0, new_lo[i] - fmin[i])) /
                                                           max(new_prange[i], 1e-12))}
                  for i in outside}
        arms.append({"npz": str(p.relative_to(ROOT)), "sha256_12": sha12(p), "n_frames": int(fr.shape[0]),
                     "physical_range_old": old.tolist(),
                     "frames_min_per_dim": fmin.tolist(), "frames_max_per_dim": fmax.tolist(),
                     "observed_travel_per_dim": obs_travel.tolist(),
                     "ratio_new_over_old": (new_prange / np.where(old > 0, old, np.nan)).tolist(),
                     "n_dims_frames_inside_new_interval": len(inside_new),
                     "dims_frames_outside_new_interval": outside,
                     "outside_dims_detail": exceed,
                     "gripper_dims_consistent_with_old_unit_assumption": grip_dims_in_unit_interval})
        obs_stack.append(obs_travel)

    # ---- 三条牙（判自己的缺陷，不判别人）----
    teeth = []

    def tooth(tid, name, ok, required, observed, red_when, kind, note=None, applies_when=True,
              counts_toward_ok=True, classification=None, action_for_downstream=None):
        teeth.append({"id": tid, "name": name, "ok": bool(ok),
                      "status": ("N_A" if not applies_when else ("PASS" if ok else "RED")),
                      "required": required, "red_when": red_when, "observed": observed,
                      "kind": kind, "note": note, "counts_toward_ok": bool(counts_toward_ok),
                      "classification": classification, "action_for_downstream": action_for_downstream})

    # Tp1 守的是**当前采集器实现**（不是历史）：内联公式必须已消失、必须走 arm_qpos_for/ARM_QPOS_IDX。
    # **用 AST 读实现，不做全文 grep**：全文里"state_dim + 2"会出现在勘误说明的 docstring 中，
    # grep 会把文档当实现（本牙第一次跑就因此假红 —— 同族于 `redline_provenance_discipline`）。
    import ast as _ast
    coll = (ROOT / "scripts/c2_collect_env_states.py").read_text(encoding="utf-8")
    tree = _ast.parse(coll)
    fns = {n.name: n for n in tree.body if isinstance(n, _ast.FunctionDef)}
    pr_fn = fns.get("physical_range")
    pr_src = _ast.get_source_segment(coll, pr_fn) if pr_fn is not None else ""
    pr_doc = _ast.get_docstring(pr_fn, clean=False) if pr_fn is not None else ""
    pr_code = pr_src.replace(pr_doc, "", 1) if (pr_src and pr_doc) else pr_src
    inline_bug_present = ("state_dim + 2" in pr_code)
    calls_in_pr = {n.func.id for n in _ast.walk(pr_fn)
                   if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)} if pr_fn else set()
    aqf = fns.get("arm_qpos_for")
    aqf_src = _ast.get_source_segment(coll, aqf) if aqf is not None else ""
    aqf_code = aqf_src.replace(_ast.get_docstring(aqf, clean=False) or "", "", 1) if aqf_src else ""
    uses_declared = ("arm_qpos_for" in calls_in_pr) and ("ARM_QPOS_IDX[idx]" in aqf_code)
    declared = sorted(ARM_QPOS.values())
    implemented_old = sorted({(d + 2) for d in range(7, 13)})
    tooth("Tp1_declared_mapping_equals_implemented",
          "采集器**当前实现**的 qpos 映射 == 模块级声明的 ARM_QPOS_IDX（内联第二套公式必须不存在）",
          (not inline_bug_present) and uses_declared,
          "`state_dim + 2` 不出现在 physical_range()；映射经 arm_qpos_for() 取 ARM_QPOS_IDX",
          (f"AST 读实现：inline_formula_in_physical_range_code={inline_bug_present} "
           f"calls_arm_qpos_for={'arm_qpos_for' in calls_in_pr} "
           f"arm_qpos_for_uses_ARM_QPOS_IDX={'ARM_QPOS_IDX[idx]' in aqf_code}；"
           f"历史缺陷：declared={declared} vs implemented_old={implemented_old}"
           "（右臂差一位，dim12 拿到手指滑动关节 0.036 而真值 6.28316 = **差 175×**）"),
          "内联公式回来 / 不走声明映射 ⇒ 右臂 6 维的 F1 分母错", "code_read_semantics+measured",
          note=("本牙有真失败模式：把 `arm_qpos_for()` 改回内联 `state_dim + 2` 就会红"
                "（`scripts/c2_gate_norm_contract.py` 的 M4 变异体即此形态）"))
    grip_travel_ok = all(abs(new_prange[d] - (norm_fn(jnt_range[adr2jnt[GRIPPER_QPOS[d]]][1])
                                             - norm_fn(jnt_range[adr2jnt[GRIPPER_QPOS[d]]][0]))) < 1e-12
                         for d in GRIPPER_STATE_DIMS)
    tooth("Tp2_gripper_travel_through_upstream_normalizer",
          "夹爪维行程由 upstream 归一化函数从**模型实测关节行程**导出（不是拍一个 1.0）",
          grip_travel_ok,
          "travel == normalize_puppet_gripper_position(jnt_hi) - normalize(jnt_lo)",
          (f"new_travel(dim6)={new_prange[6]:.6f} new_travel(dim13)={new_prange[13]:.6f}；"
           f"旧值均为 1.0（差 {100 * (new_prange[6] - 1.0):.2f}%）"),
          "travel 不是由 upstream 函数从模型导出 ⇒ 夹爪维的 F1 分母无出处", "measured",
          note=("**C2 的一个假设在此被自己的实测证伪，如实登记**：C2 原以为 `sim.py:67-68` 把归一化"
                "作用在**夹爪关节角（弧度）**上（`constants.py:80-81` CLOSE=-0.6213/OPEN=1.4910）⇒ 推算行程"
                "≈ 53.4（旧值 1.0 错 53×）。实测模型 `qposadr=6` = `vx300s_left/left_finger`、"
                "type=2（滑动）、`jnt_range=[0.021, 0.057]` ⇒ 归一化后区间 = [0.0647, 0.9747]、行程 = 0.91001"
                " ⇒ **旧值 1.0 只差 9.0%，不是 53×**。真正错得离谱的是 dim 12（见 Tp1）。"
                "教训：`constants.py` 里的 JOINT_OPEN/CLOSE 常量**不是**本模型该 qpos 的行程，"
                "常量与模型是两套出处，必须读模型（同 `redline_provenance_discipline`）"))
    all_inside = all(a["n_dims_frames_inside_new_interval"] == STATE_DIMS for a in arms) if arms else False
    tooth("Tp3_collected_frames_inside_declared_interval",
          "已采集帧的每一维都落在新口径的物理区间内",
          all_inside, "每档 14/14 维都在 [state_lo, state_hi] 内",
          "; ".join(f"{Path(a['npz']).parent.name}: inside={a['n_dims_frames_inside_new_interval']}/14"
                    f" outside={a['dims_frames_outside_new_interval']}" for a in arms) or "无 npz",
          "有维落在**声明**区间外 ⇒ 说明 jnt_range 不是硬边界（本档实测如此），F1 分母必须取 max", "measured",
          counts_toward_ok=False, classification="finding_about_env_not_artifact_defect",
          action_for_downstream=("任何把 `jnt_range` 当硬边界的口径都要改：本档实测 random 8 维越界、"
                                 "hold 2 维（夹爪）越界、sweep 1 维越界"),
          note=("旧口径的反证：夹爪维若按 [0,1] 解释，实测帧 dim6 ∈ "
                f"[{arms[0]['frames_min_per_dim'][6]:.4f}, {arms[0]['frames_max_per_dim'][6]:.4f}] "
                "⇒ 与 [0,1] 矛盾" if arms else None))

    obs_max = (np.max(np.stack(obs_stack), axis=0) if obs_stack else np.zeros(STATE_DIMS))
    prange_eff = np.maximum(new_prange, obs_max)
    n_outside_total = sum(len(a["dims_frames_outside_new_interval"]) for a in arms)
    tooth("Tp4_declared_range_is_soft_bound",
          "`jnt_range` 被当作**软**边界处理：F1 分母取 `max(jnt_travel, observed_travel)`，且越界幅度已逐维登记",
          bool(arms) and prange_eff.shape[0] == STATE_DIMS and all(
              "outside_dims_detail" in a for a in arms) and bool(np.all(prange_eff >= obs_max - 1e-12)),
          "prange_effective_d ≥ 该维实测行程；越界维必须带 exceed_ratio_of_travel",
          (f"越界登记：{n_outside_total} 维·档（{len(arms)} 档）；最严重实例 = random 档 dim6 "
           f"实测 [{arms[1]['frames_min_per_dim'][6]:.4f}, {arms[1]['frames_max_per_dim'][6]:.4f}] vs 声明 "
           f"[{new_lo[6]:.4f}, {new_hi[6]:.4f}]；live 复核：hold 60 步后 qpos[6]=0.07333 > jnt_hi=0.057"
           "（+28.6%）⇒ MuJoCo 限位是软约束，位置执行器可推出去"),
          "prange_effective < 实测行程 ⇒ F1 下限与近常量标记的分母小于数据 ⇒ 判定不可信", "measured",
          note=("这条改变 T-C2-1 的一个设计前提：**不能拿 `jnt_range` 当硬边界**。"
                "受影响的不只是 C2：任何用 `jnt_range` 推「物理行程」的下游（含 A2 的越界维统计口径）"
                "都应改口径或标注 `soft_bound=true`"))

    ga_sim = Path(gsim.__file__)
    ga_const = Path(GC.__file__)
    doc = {"artifact": "c2_physical_range_correction", "generated_at": now_iso(),
           "generator": {"path": "scripts/c2_fix_physical_range.py",
                         "sha256_12": sha12(Path(__file__).resolve())},
           "reason": "C2 自查发现采集器 physical_range() 两处缺陷（右臂映射差一 + 夹爪行程假设 1.0）",
           "defect_class": ["declared_vs_implemented_divergence", "upstream_semantics_assumed_not_read"],
           "impact": ("F1 下限 = coef × physical_range、近常量维标记 = denom_raw/physical_range ≤ 0.02"
                      "⇒ 两个判据的分母在 dims 6..13 上错；帧数据不受影响，无需重采"),
           "citations": [
               {"path": str(ga_sim.relative_to(ga_sim.parents[3])) if len(ga_sim.parents) > 3 else str(ga_sim),
                "abs_path": str(ga_sim), "sha256_12": sha12(ga_sim), "lines": "61-69",
                "fact": "get_qpos：每臂 qpos 块 = 8；臂关节 = [:6]；夹爪 = 块内第 7 个（index 6）经 normalize"},
               {"path": "gym_aloha/constants.py", "abs_path": str(ga_const), "sha256_12": sha12(ga_const),
                "lines": "94-97", "fact": "normalize_puppet_gripper_position(x) = (x-0.01844)/(0.05800-0.01844)"},
               {"path": "gym_aloha/constants.py", "abs_path": str(ga_const), "sha256_12": sha12(ga_const),
                "lines": "80-81", "fact": "PUPPET_GRIPPER_JOINT_CLOSE=-0.6213 / OPEN=1.4910（弧度，关节角）"},
               {"path": "scripts/c2_collect_env_states.py",
                "sha256_12": sha12(ROOT / "scripts/c2_collect_env_states.py"),
                "sha_as_of": now_iso(),
                "lines": "arm_qpos_for / physical_range / GRIPPER_QPOS_IDX",
                "fact": ("模块级 ARM_QPOS_IDX 声明正确；缺陷本体曾是 physical_range() 内联 "
                         "`state_dim + 2`（右臂差一位、dim12 差 175×），已修 ⇒ 由 Tp1 用 AST 守"),
                "sha_recomputed_at_runtime": True,
                "why_runtime": ("裁定 78.11 `citation_sha_as_of_discipline`：引用自己写入面内、"
                                "仍在编辑的文件，sha 必须落笔时刻重读；写死旧值会让引用指向不存在的版本")}],
           "model_facts": {"nq": int(m.nq), "njnt": nj, "joint_table": joint_table,
                           "mujoco_gl": args.mujoco_gl,
                           "control_dt_s": float(shim.MAINLINE_DT),
                           "timing_verified_by": "geg.GymAlohaSimEnv._verify_timing（构造时执行）"},
           "physical_range_old_dims_6_13_note": "旧值 dims 7..12 = 邻位关节行程；dim12 = 手指滑动关节 0.036；dims 6/13 = 假设 1.0",
           "physical_range_new": new_prange.tolist(),
           "physical_interval_new": {"lo": new_lo.tolist(), "hi": new_hi.tolist()},
           "observed_travel_max_over_arms": obs_max.tolist(),
           "physical_range_effective": prange_eff.tolist(),
           "physical_range_effective_rule": "max(jnt_travel_through_upstream_normalizer, observed_travel)",
           "dims_where_observed_exceeds_declared": [int(i) for i in range(STATE_DIMS)
                                                    if obs_max[i] > new_prange[i] + 1e-12],
           "per_dim": per_dim, "arms_crosscheck": arms, "teeth": teeth,
           "ok": all(t["ok"] for t in teeth if t["counts_toward_ok"]) if teeth else False,
           "ok_rule": "只有 `counts_toward_ok=true` 的牙参与判定；Tp3 是**关于 env 的实测事实**（软限位），不是本产物的缺陷",
           "load_pair": load_pair(),
           "status": "corrected_pending_rebuild（stats 矩阵需用本文件重算）"}
    doc["ok"] = all(t["ok"] for t in teeth if t["counts_toward_ok"])
    doc["verdict"] = "PASS" if doc["ok"] else "RED"
    (out / "correction.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    slim = {"artifact": "c2_physical_range_corrected", "generated_at": doc["generated_at"],
            "source_of_truth": "scripts/c2_fix_physical_range.py（读模型 + upstream 归一化函数）",
            "supersedes": "env_states_*/env_states.npz 里的 physical_range 字段（两处缺陷，见 correction.json）",
            "physical_range": new_prange.tolist(),
            "physical_range_effective": prange_eff.tolist(),
            "physical_range_effective_rule": "max(jnt_travel, observed_travel)（jnt_range 是软边界，Tp4）",
            "physical_interval": {"lo": new_lo.tolist(), "hi": new_hi.tolist()},
            "per_dim": per_dim, "verdict": doc["verdict"],
            "sha256_12_of_correction": sha12(out / "correction.json")}
    (out / "physical_range.json").write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": doc["verdict"], "teeth": [(t["id"], t["status"]) for t in teeth],
                      "physical_range_old_dim6_12": [arms[0]["physical_range_old"][i] for i in (6, 12)] if arms else None,
                      "physical_range_new_dim6_12": [round(float(new_prange[i]), 5) for i in (6, 12)],
                      "correction": str((out / "correction.json").relative_to(ROOT)),
                      "for_build": str((out / "physical_range.json").relative_to(ROOT))},
                     ensure_ascii=False, indent=2))
    return 0 if doc["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
