#!/usr/bin/env python
"""档 5.1 · `descend` 停滞判据标定（**不判门**；只为选两个常数）

为什么要有它（坑 46 + 坑 48 的后续）：
  档 5 实测 23 次接管里 11 次卡死在 `descend`（原地打转 162~305 步），根因是
  `descend → grasp` 判据没有任何超时/退路。修法（档 5.1 第 2 步）是给 descend 加
  「连续 W 步没有实质下降 ⇒ 退回 approach 重新对准（restage），最多 N 次 ⇒ 仍失败就
  显式 `unrecoverable` 交还」。但 **W 和「没有实质下降」的阈值 T 不能拍脑袋**：
    * T/W 太松 ⇒ 卡死照旧（白改）；
    * T/W 太紧 ⇒ **干净专家跑**也会被 restage 打断 ⇒ 破 G1（专家动作流逐比特回归）、
      破上界锚 `runs/s2f_ceiling_rev_test20_n05`，连带把档 6 的示范源搞脏。
  所以先用数据把两侧的余量算出来：本探针在**同一套定义**下量
    ① 干净专家跑（`--mode clean`，与 G1 同配置：reverse / 20 局 / seed7000 / noise 0.05 / rng12345）；
    ② 接管跑（`--mode trace`，直接读 `runs/s5_diag_resume/diag_resume_trace.npz` 的专家步）
  每段 descend 游程里「连续 stalled 步数」的最大值，并给出候选 (T, W) 网格上会不会触发。

  stalled 的定义与将要写进 `mg_expert.py` 的实现**逐字对应**：
      stalled[t] = (z_err[t] > Z_TOL) ∧ (|eef_z[t] − eef_z[t−1]| < T)
      其中 z_err = eef_z − can_z − GRASP_OFFSET_Z（descend→grasp 判据的同一个残差）
  ⇒ 触发 = 某个连续 stalled 游程长度 ≥ W。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_stall_calib.py --mode clean \
        --task-mode reverse --episodes 20 --seed 7000 --noise 0.05 --out runs/s5_1_stall_calib_clean_rev'
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_stall_calib.py --mode trace \
        --trace runs/s5_diag_resume/diag_resume_trace.npz --out runs/s5_1_stall_calib_trace'
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_stall_calib.py --selftest'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_expert import GRASP_OFFSET_Z, PRE_HEIGHT, Z_TOL  # noqa: E402

RUNS = MG_ROOT / "runs"
# 候选网格：T 单位 mm/步，W 单位步。T 的下沿取 0.05 mm（档 5 实测卡死局的中位每步位移 0.03 mm），
# 上沿取 1.0 mm（成功局 7003 的中位每步位移 0.16 mm，不能被算成 stalled）。
T_GRID_MM = (0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, 1.00)
W_GRID = (10, 15, 20, 25, 30, 40, 60)
DESCEND_RUN_MIN = 5      # 短于它的 descend 游程不统计（正常收敛也就十几步）


# ── 纯函数（可自测）───────────────────────────────────────────────────────
def stall_mask(z_err_mm: np.ndarray, dz_mm: np.ndarray, t_mm: float) -> np.ndarray:
    """stalled[t] = (z_err > Z_TOL) ∧ (|dz| < T)。dz[0] 无定义 ⇒ 一律 False（保守：不算停滞）。"""
    z_err_mm = np.asarray(z_err_mm, dtype=np.float64)
    dz_mm = np.asarray(dz_mm, dtype=np.float64)
    m = (z_err_mm > Z_TOL * 1000) & (np.abs(dz_mm) < t_mm)
    if len(m):
        m[0] = False
    return m


def longest_stall_run(mask: np.ndarray) -> int:
    best = cur = 0
    for v in np.asarray(mask, dtype=bool):
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return int(best)


def first_trigger(mask: np.ndarray, w: int) -> int:
    """第一个「连续 stalled 达到 w 步」的步索引（0-based，指游程末尾那一步）；没有 ⇒ -1。"""
    cur = 0
    for i, v in enumerate(np.asarray(mask, dtype=bool)):
        cur = cur + 1 if v else 0
        if cur >= w:
            return int(i)
    return -1


def descend_runs(phase: np.ndarray, want: str = "descend") -> list[tuple[int, int]]:
    """把相位序列切成游程，返回所有 `want` 游程的 (起, 止)（左闭右开）。"""
    out, start = [], None
    for i, p in enumerate(phase):
        if p == want and start is None:
            start = i
        elif p != want and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(phase)))
    return out


def summarize_runs(runs: list[dict], t_mm: float, w: int) -> dict:
    """在一组 descend 游程记录上判「(T, W) 会不会触发」。"""
    fired = [r for r in runs if first_trigger(r["mask_t"], w) >= 0]
    return {"T_mm": t_mm, "W": w, "n_runs": len(runs), "n_fired": len(fired),
            "fired": [{"tag": r["tag"], "at": first_trigger(r["mask_t"], w), "len": r["n"],
                       "longest": longest_stall_run(r["mask_t"])} for r in fired],
            "max_longest": max((longest_stall_run(r["mask_t"]) for r in runs), default=0)}


def selftest() -> int:
    n = 0

    def ck(name: str, cond: bool, detail: str = "") -> None:
        nonlocal n
        if not cond:
            raise AssertionError(f"自测失败：{name} {detail}")
        n += 1

    ck("游程切分", descend_runs(["approach", "descend", "descend", "grasp", "descend"])
       == [(1, 3), (4, 5)])
    ck("游程切分到末尾", descend_runs(["descend", "descend"]) == [(0, 2)])
    ck("没有 descend", descend_runs(["approach", "grasp"]) == [])
    ze = np.array([50.0, 30.0, 5.0, 20.0, 20.0])
    dz = np.array([9.0, 0.01, 0.01, 0.01, 0.01])
    m = stall_mask(ze, dz, 0.1)
    ck("z_err 在带内不算 stalled", list(m) == [False, True, False, True, True], str(list(m)))
    ck("首步 dz 无定义 ⇒ False", stall_mask(np.array([50.0]), np.array([0.0]), 0.1).tolist() == [False])
    ck("最长游程", longest_stall_run(np.array([0, 1, 1, 0, 1, 1, 1], dtype=bool)) == 3)
    ck("最长游程 空", longest_stall_run(np.array([], dtype=bool)) == 0)
    ck("触发点=游程末尾", first_trigger(np.array([0, 1, 1, 1, 0], dtype=bool), 3) == 3)
    ck("不够长不触发", first_trigger(np.array([0, 1, 1, 0, 1, 1], dtype=bool), 3) == -1)
    ck("W=1 触发在首个 stalled", first_trigger(np.array([0, 0, 1, 0], dtype=bool), 1) == 2)
    runs = [{"tag": "a", "n": 5, "mask_t": np.array([0, 1, 1, 1, 1], dtype=bool)},
            {"tag": "b", "n": 3, "mask_t": np.array([1, 1, 1], dtype=bool)}]
    s = summarize_runs(runs, 0.1, 3)
    ck("汇总：两条都触发", s["n_fired"] == 2 and s["max_longest"] == 4, json.dumps(s))
    s = summarize_runs(runs, 0.1, 5)
    ck("汇总：W 太大就都不触发", s["n_fired"] == 0, json.dumps(s))
    print(f"[stall_calib] selftest 全绿：{n} 项（纯函数，未碰仿真 / 未占 GPU）")
    return 0


# ── 数据源 1：干净专家跑（与 G1 同配置）───────────────────────────────────
def collect_clean(args) -> tuple[list[dict], dict]:
    if args.task_mode == "reverse":
        from mg_env_reverse import TASK_REVERSE, ReverseGraspEnv
        from mg_expert_reverse import ReverseScriptedExpert as ExpertCls
        env, task_str = ReverseGraspEnv(img_size=args.img_size), TASK_REVERSE
    else:
        from mg_env import TASK, SingleArmGraspEnv
        from mg_expert import ScriptedExpert as ExpertCls
        env, task_str = SingleArmGraspEnv(img_size=args.img_size), TASK
    rng = np.random.default_rng(12345)          # 与 mg_ceiling.py 同一颗噪声流
    runs: list[dict] = []
    eps: list[dict] = []
    print(f"[calib] mode=clean task_mode={args.task_mode} expert={ExpertCls.__name__} "
          f"horizon={env.horizon} eps={args.episodes} seed={args.seed_mode}/{args.seed} "
          f"noise={args.noise} rng=12345", flush=True)
    for ep in range(args.episodes):
        seed = args.seed if args.seed_mode == "fixed" else args.seed + ep
        env.reset(seed=seed)
        expert = ExpertCls(env).reset()
        phases: list[str] = []
        eef_z: list[float] = []
        can_z: list[float] = []
        steps, succ = 0, -1
        while steps < env.horizon:
            phases.append(str(expert.phase))
            eef_z.append(float(env.eef_pos[2]))
            can_z.append(float(env.object_pos[2]))
            act = np.asarray(expert(), dtype=np.float32)
            if args.noise > 0.0:
                act[:3] = np.clip(act[:3] + rng.normal(0.0, args.noise, size=3), -1.0, 1.0)
            _o, _r, terminated, truncated, info = env.step(act)
            steps += 1
            if info["success"] and succ < 0:
                succ = steps
            if terminated or truncated:
                break
        ph = np.asarray(phases)
        ez = np.asarray(eef_z, dtype=np.float64)
        cz = np.asarray(can_z, dtype=np.float64)
        z_err_mm = (ez - cz - GRASP_OFFSET_Z) * 1000
        dz_mm = np.concatenate([[0.0], np.diff(ez)]) * 1000
        n_run = 0
        for a, b in descend_runs(ph):
            if b - a < DESCEND_RUN_MIN:
                continue
            n_run += 1
            rec = {"tag": f"ep{ep}/seed{seed}/run{n_run}", "n": int(b - a),
                   "ep": ep, "seed": seed, "reached_grasp": bool((ph[a:b + 1] == "grasp").any())}
            for t in T_GRID_MM:
                rec[f"mask_{t}"] = stall_mask(z_err_mm[a:b], dz_mm[a:b], t)
            runs.append(rec)
        eps.append({"ep": ep, "seed": seed, "steps": steps, "success": succ > 0,
                    "n_descend_runs": n_run, "phases": "->".join(dict.fromkeys(phases))})
        print(f"  ep{ep} seed={seed} success={succ > 0} steps={steps} descend游程={n_run} "
              f"phases={eps[-1]['phases']}", flush=True)
    env.close()
    meta = {"mode": "clean", "task_mode": args.task_mode, "expert": ExpertCls.__name__,
            "task": task_str, "episodes": args.episodes, "seed": args.seed,
            "seed_mode": args.seed_mode, "noise": args.noise, "rng": 12345,
            "horizon": int(env.horizon) if hasattr(env, "horizon") else -1}
    return runs, {"eps": eps, "meta": meta}


# ── 数据源 2：档 5 诊断 trace（接管段的专家步）─────────────────────────────
PHASES = ["init", "approach", "descend", "grasp", "lift", "settle", "carry",
          "place_descend", "release", "retreat", "done"]


def collect_trace(args) -> tuple[list[dict], dict]:
    p = Path(args.trace)
    if not p.is_absolute():
        p = MG_ROOT / p
    if not p.is_file():
        raise SystemExit(f"[calib] --trace 不存在：{p}（坑 41：路径自查）")
    with np.load(p, allow_pickle=False) as z:
        tr = z["trace"].astype(np.float64)
        lengths = z["episode_lengths"].astype(int).tolist()
        seeds = z["seeds"].astype(int).tolist()
        cols = [str(c) for c in z["cols"]]
        phases_tbl = [str(x) for x in z["phases"]]
    if phases_tbl != PHASES:
        raise SystemExit(f"[calib] --trace 的相位表与本探针不一致：{phases_tbl}")
    ix = {c: i for i, c in enumerate(cols)}
    for need in ("src", "phase", "eef_z", "can_z"):
        if need not in ix:
            raise SystemExit(f"[calib] --trace 缺列 {need}")
    runs: list[dict] = []
    eps: list[dict] = []
    off = 0
    for ln, seed in zip(lengths, seeds):
        m = tr[off:off + ln]
        off += ln
        tk = m[m[:, ix["src"]] == 1]           # 只看专家步（策略步的 dz 与本判据无关）
        if len(tk) == 0:
            continue
        ph = np.asarray([PHASES[int(v)] for v in tk[:, ix["phase"]]])
        ez = tk[:, ix["eef_z"]]
        cz = tk[:, ix["can_z"]]
        z_err_mm = (ez - cz - GRASP_OFFSET_Z) * 1000
        dz_mm = np.concatenate([[0.0], np.diff(ez)]) * 1000
        n_run = 0
        for a, b in descend_runs(ph):
            if b - a < DESCEND_RUN_MIN:
                continue
            n_run += 1
            rec = {"tag": f"seed{seed}/run{n_run}", "n": int(b - a), "seed": int(seed),
                   "reached_grasp": bool((ph[b:] == "grasp").any())}
            for t in T_GRID_MM:
                rec[f"mask_{t}"] = stall_mask(z_err_mm[a:b], dz_mm[a:b], t)
            runs.append(rec)
        eps.append({"seed": int(seed), "tk_steps": int(len(tk)), "n_descend_runs": n_run,
                    "phases": "->".join(dict.fromkeys(ph.tolist()))})
    if off != len(tr):
        raise SystemExit(f"[calib] --trace 局长度之和对不上：{off} vs {len(tr)}")
    meta = {"mode": "trace", "trace": str(p), "n_episodes_with_takeover": len(eps),
            "sha256_16": hashlib.sha256(p.read_bytes()).hexdigest()[:16],
            "note": "dz 由 trace 的 eef_z 差分重算（= 专家实现里的 prev_eef_z 口径），不用盘上的 dz_act 列"}
    return runs, {"eps": eps, "meta": meta}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("clean", "trace"), default="clean")
    ap.add_argument("--task-mode", choices=("forward", "reverse"), default="reverse")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7000)
    ap.add_argument("--seed-mode", choices=("fixed", "random"), default="random")
    ap.add_argument("--noise", type=float, default=0.05)
    ap.add_argument("--img-size", type=int, default=224)
    ap.add_argument("--trace", default="runs/s5_diag_resume/diag_resume_trace.npz")
    ap.add_argument("--out", default="")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    t0 = time.perf_counter()
    runs, aux = collect_clean(args) if args.mode == "clean" else collect_trace(args)
    out_dir = Path(args.out) if args.out else RUNS / f"s5_1_stall_calib_{args.mode}_{datetime.now():%H%M%S}"
    if not out_dir.is_absolute():
        out_dir = MG_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    grid = []
    for t in T_GRID_MM:
        for r in runs:
            r["mask_t"] = r[f"mask_{t}"]
        for w in W_GRID:
            grid.append(summarize_runs(runs, t, w))
    n_ok_run = sum(1 for r in runs if r["reached_grasp"])
    L = []
    L.append(f"# 档 5.1 · descend 停滞判据标定（**不判门**，mode={args.mode}）")
    L.append("")
    L.append(f"生成：**{datetime.now():%Y-%m-%d %H:%M:%S}**（`code/mg_probe_stall_calib.py`，"
             f"用时 {time.perf_counter() - t0:.0f} s）")
    L.append("")
    L.append("```json")
    L.append(json.dumps(aux["meta"], ensure_ascii=False, indent=1))
    L.append("```")
    L.append("")
    L.append(f"descend 游程（≥{DESCEND_RUN_MIN} 步）共 **{len(runs)}** 段，其中走到 grasp 的 "
             f"**{n_ok_run}** 段、没走到的 **{len(runs) - n_ok_run}** 段。")
    L.append("")
    L.append("## 一、每段 descend 游程的「最长连续 stalled 游程」（单位：步）")
    L.append("")
    L.append("stalled[t] = (z_err > %.0f mm) ∧ (|Δeef_z| < T)。" % (Z_TOL * 1000))
    L.append("")
    L.append("| 游程 | 步数 | 到 grasp | " + " | ".join(f"T={t:g}mm" for t in T_GRID_MM) + " |")
    L.append("| --- | --- | --- | " + " | ".join("---" for _ in T_GRID_MM) + " |")
    for r in runs:
        L.append(f"| {r['tag']} | {r['n']} | {'✅' if r['reached_grasp'] else '❌'} | "
                 + " | ".join(str(longest_stall_run(r[f"mask_{t}"])) for t in T_GRID_MM) + " |")
    L.append("")
    L.append("## 二、(T, W) 网格：会不会触发 restage")
    L.append("")
    L.append("| T (mm/步) | W (步) | 触发段数 | 其中「没到 grasp」的段 | 最长 stalled 游程 |")
    L.append("| --- | --- | --- | --- | --- |")
    for g in grid:
        n_bad = sum(1 for f in g["fired"]
                    if not next(r["reached_grasp"] for r in runs if r["tag"] == f["tag"]))
        L.append(f"| {g['T_mm']:g} | {g['W']} | {g['n_fired']}/{g['n_runs']} | {n_bad} | {g['max_longest']} |")
    L.append("")
    L.append("## 三、逐局")
    L.append("")
    L.append("```json")
    L.append(json.dumps(aux["eps"], ensure_ascii=False, indent=1))
    L.append("```")
    L.append("")
    L.append("---")
    L.append("⚠️ 本产物**不判门**、不并入任何 n=60 / n=80 读数（坑 40）；用途只有一个："
             "为 `mg_expert.py` 的 `DESCEND_STALL_DZ` / `DESCEND_STALL_MAX` 两个常数选值，"
             "并把「干净专家跑不会被误触发」的余量写进 `runs/S5_1_PREREG.md`。")
    (out_dir / "stall_calib.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (out_dir / "stall_calib.json").write_text(json.dumps(
        {"generated": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "meta": aux["meta"], "eps": aux["eps"],
         "runs": [{k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in r.items()
                   if not k.startswith("mask_")} | {"n": r["n"]} for r in runs],
         "longest": {f"T={t:g}": {r["tag"]: longest_stall_run(r[f"mask_{t}"]) for r in runs}
                     for t in T_GRID_MM},
         "grid": grid,
         "code_sha256_16": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                            for p in sorted(HERE.glob("mg_*.py"))
                            if p.name in ("mg_probe_stall_calib.py", "mg_expert.py",
                                          "mg_expert_reverse.py", "mg_diag_resume.py")},
         "gates": "本产物不判门"}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[calib] descend 游程 {len(runs)} 段（到 grasp {n_ok_run}）⇒ {out_dir / 'stall_calib.md'}",
          flush=True)
    for g in grid:
        if g["W"] == 25:
            print(f"        T={g['T_mm']:g}mm W=25 ⇒ 触发 {g['n_fired']}/{g['n_runs']}  "
                  f"最长游程 {g['max_longest']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
