#!/usr/bin/env python
"""档 9B · Z0b 可行性台（**纯 CPU、零 GPU**）：末端高度保持器到底按不按得住天花板。

为什么先做这一步：`runs/S9_PREREG.md` 增补 1 ① 已经证伪了「把 dz 置 0」这种被动限位
（OSC 的 dz 是速度级指令，末端滑行中位 3.77 / p90 5.87 cm）。上 GPU 跑闭环（~2.5 h）之前，
先用**已录的动作**重放一遍，量「换成主动 P 控制后，搬运期末端升程能不能被压在 cap 之内」——
按不住就别烧卡（这是本档最便宜的一道止损闸）。

做法：从样本里挑「侧躺 ∧ 搬运期末端升程最高」的 N=12 局，每局重放两遍：
  (a) **不加限位** ⇒ 必须与 npz 里录的 `state[:,2]` 逐位相符（`max|Δ| < 1e-5`）——重放台自证；
  (b) **加限位**（同一套 `CarryCeiling`，与 GPU 上跑的是**同一份代码**，不是复制品）⇒ 量搬运期最大升程。

两个样本（`--sample`）：
  * `test` = **Z0b 主闸**：TEST 7000..7019，5 臂 × 4 rep = 400 局（档 8/7H 的既有产物；v2 常数也在这批上量）。
  * `val`  = **Z0b′ 独立确认台**：val 8000..8019，5 个关门格（8C/8D×2 @022000 + 7H×2 @005500）= 100 局。
    为什么要有它：v2 的动力学常数是在 TEST 400 局上量的 ⇒ 按坑 27/42，「按住」这件事要在**另一批数据**上再确认一遍，
    否则「在拟合用的那批局上按得住」没有说服力。⚠️ 本台只比控制器行为、**不比策略高低**（坑 33 不适用）。

⚠️ 诚实标注（预注册 增补 1 ④）：(b) 是**开环**重放——限位改变轨迹后，录制动作对新状态不再最优，
   所以本台只回答「按不按得住高度」，**不回答**「按住了还能不能把 can 送到」。后者是 Z1–Z3 的闭环实验。

退出码：0 = 闸过（≥ need/N 局按住）；1 = 不过；3 = 重放台自证失败（(a) 对不上 ⇒ 全部读数作废）。
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

from mg_eval_zlim import (B_CARRY, GRASP_THR, OPEN_THR, RELEASE_THR, SAFETY,  # noqa: E402
                          build_filter)

RUNS = MG_ROOT / "runs"
TEST_ARMS = (("8C_s2000", "s8c_seed2000"), ("8D_s4000", "s8d_seed4000"), ("8D_s5000", "s8d_seed5000"),
             ("7H_s11000", "s7h_seed11000"), ("7H_s12000", "s7h_seed12000"))
VAL_ARMS = (("8C_s2000", "pi05_mix60f120r_c1_s8c_seed2000/sweep_rev/step_22000_rev"),
            ("8D_s4000", "pi05_mix60f120r_c1_s8d_seed4000/sweep_rev/step_22000_rev"),
            ("8D_s5000", "pi05_mix60f120r_c1_s8d_seed5000/sweep_rev/step_22000_rev"),
            ("7H_s11000", "pi05_mix60f120r_s7h_seed11000/sweep_rev/step_5500_rev"),
            ("7H_s12000", "pi05_mix60f120r_s7h_seed12000/sweep_rev/step_5500_rev"))
REPS = ("", "_rep2", "_rep3", "_rep4")
CAP_MAIN = 12.15          # 示范搬运升程 p90（runs/S9_PREREG.md 增补 1 ③）
TOL_CM = 1.0              # 「按住」= 搬运期最大升程 ≤ cap + 1.0 cm
NEED = 11                 # ≥ 11/12 局按住才算过（预注册 增补 1 ④）
N_PICK = 12
FID_TOL = 1e-5
MODE_DEF = "ceilpred"     # v2（终点预测式节流）；v1 = ceilhold（Z0b 实测 0/12，留档）


def carry_window(width: np.ndarray) -> tuple[int, int] | None:
    """从夹爪宽度序列定位搬运段 [t_grasp, t_release]。阈值来自 mg_env 的实测常数。"""
    op = np.where(width > OPEN_THR)[0]
    if len(op) == 0:
        return None
    t0 = int(op[0])
    af = np.where(width[t0:] < GRASP_THR)[0]
    if len(af) == 0:
        return None
    tg = t0 + int(af[0])
    rel = np.where(width[tg:] > RELEASE_THR)[0]
    tr = tg + int(rel[0]) if len(rel) else len(width) - 1
    return (tg, max(tr, tg))


def rise_cm(eef_z: np.ndarray, tg: int, tr: int) -> float:
    seg = eef_z[tg:tr + 1]
    return float((seg.max() - eef_z[tg]) * 100.0)


def sample_dirs(sample: str) -> list[tuple[str, Path]]:
    if sample == "test":
        return [(arm, RUNS / f"{base}_rev_test_rand20_k10{r}") for arm, base in TEST_ARMS for r in REPS]
    if sample == "val":
        return [(arm, RUNS / rel) for arm, rel in VAL_ARMS]
    raise ValueError(f"未知 sample={sample}（可选 test / val）")


def scan(sample: str) -> list[dict]:
    """零重放、只读 npz：把每局的搬运升程算出来，用于挑最坏的 N 局。"""
    out = []
    for arm, d in sample_dirs(sample):
        npz, summ = d / "rollout_actions.npz", d / "eval_summary.json"
        if not (npz.exists() and summ.exists()):
            continue
        z = np.load(npz)
        s = json.loads(summ.read_text())
        st, lens = z["state"], z["episode_lengths"]
        off = 0
        for i, L in enumerate(lens):
            S = st[off:off + int(L)]
            off += int(L)
            pe = s["per_episode"][i]
            cw = carry_window(S[:, 7])
            if cw is None:
                continue
            out.append({"arm": arm, "sample": sample, "path": str(d), "dir": d.name, "ep": i,
                        "seed": int(pe["seed"]), "steps": int(L),
                        "tipped": bool(pe["delivered_tipped"]), "relaxed": bool(pe["success_relaxed"]),
                        "strict": bool(pe["success"]), "can_lift_cm": float(pe["max_lift_cm"]),
                        "t_grasp": cw[0], "t_release": cw[1],
                        "eef_rise_cm": rise_cm(S[:, 2], cw[0], cw[1])})
    return out


def pick(cands: list[dict], n: int = N_PICK) -> list[dict]:
    tipped = [c for c in cands if c["tipped"]]
    return sorted(tipped, key=lambda c: -c["eef_rise_cm"])[:n]


def replay_one(cand: dict, cap_cm: float, kp: float, img_size: int = 8, mode: str = MODE_DEF,
               b=B_CARRY, safety: float = SAFETY) -> dict:
    """在真 env 里重放一局的已录动作；cap_cm<=0 = 不加限位（用于重放台自证）。"""
    from mg_env_reverse import ReverseGraspEnv
    d = Path(cand["path"])
    z = np.load(d / "rollout_actions.npz")
    acts, st, lens = z["action"], z["state"], z["episode_lengths"]
    off = int(sum(lens[:cand["ep"]]))
    L = int(lens[cand["ep"]])
    env = ReverseGraspEnv(img_size=img_size)
    env.reset(seed=cand["seed"])
    filt = build_filter(mode, cap_cm, kp, b, safety)
    max_dev = 0.0
    eefs: list[float] = []
    widths: list[float] = []
    n_held = 0
    for t in range(L):
        a = np.array(acts[off + t], dtype=np.float32)
        w = float(env.gripper_width)
        ez = float(env.eef_pos[2])
        was = filt.anchor is None
        filt.phase(w)
        if was and filt.opened and not filt.released and w < GRASP_THR:
            filt.arm(ez, t)
        if filt.apply(a, ez):
            n_held += 1
        eefs.append(float(env.eef_pos[2]))
        widths.append(w)
        max_dev = max(max_dev, abs(float(env.eef_pos[2]) - float(st[off + t, 2])))
        _o, _r, term, trunc, _i = env.step(a)
        if term or trunc:
            break
    env.close()
    ez = np.array(eefs)
    wd = np.array(widths)
    cw = carry_window(wd)
    rise = rise_cm(ez, cw[0], cw[1]) if cw else float("nan")
    return {"arm": cand["arm"], "sample": cand.get("sample"), "dir": cand["dir"], "seed": cand["seed"],
            "ep": cand["ep"], "cap_cm": cap_cm, "kp": kp, "mode": filt.mode,
            "k_eff": getattr(filt, "k_eff", None), "safety": getattr(filt, "safety", None),
            "steps": len(eefs), "carry": (list(cw) if cw else None),
            "rise_cm": rise, "rise_offline_cm": cand["eef_rise_cm"], "n_held": n_held,
            "anchor": filt.anchor, "max_rise_filt_cm": filt.max_rise_cm,
            "fid_max_dev": max_dev, "can_lift_cm": cand["can_lift_cm"], "tipped": cand["tipped"]}


def need_of(n: int) -> int:
    """门槛局数：样本够 N_PICK 就是预注册写死的 NEED；侧躺局不足 N_PICK 时按同比例缩（且至少 1 局）。

    ⚠️ 只在**样本本身不够**时缩，不许因为「跑挂了 1 局」而缩（那由 `not_held` 记账）。
    """
    if n >= N_PICK:
        return NEED
    return max(1, -(-NEED * n // N_PICK))


def gate(results: list[dict], cap: float = CAP_MAIN, tol: float = TOL_CM, need: int | None = None) -> dict:
    ok = [r for r in results if r["rise_cm"] == r["rise_cm"] and r["rise_cm"] <= cap + tol]
    if need is None:
        need = need_of(len(results))
    return {"n": len(results), "held": len(ok), "need": need, "pass": len(ok) >= need,
            "cap": cap, "tol": tol,
            "not_held": [r for r in results if r not in ok]}


def write_md(cands: list[dict], off: list[dict], on: list[dict], g: dict, fid: float, meta: dict) -> str:
    cap, kp, mode = meta["cap"], meta["kp"], meta["mode"]
    tag, sample, n_pool = meta["tag"], meta["sample"], meta["n_pool"]
    law = (f"控制律 = **终点预测式节流**：`dz = clip(min(dz_policy, (cap − rise − safety·inflight)/(safety·k)), −1, 1)`，"
           f"k={meta.get('k', float('nan')):.4f}、safety={meta.get('safety', float('nan')):.4f}、"
           f"k_eff={meta.get('k_eff', float('nan')):.4f}" if mode == "ceilpred" else
           f"控制律 = 越界反向 P：`dz = −min(1, KP·err)`，KP={kp}（**v1，已被本台判为按不住**）")
    L = []
    L.append(f"# 档 9B · {tag} 可行性台：末端高度保持器按不按住天花板（**纯 CPU、零 GPU**）")
    L.append(f"<!-- 由 code/mg_zlim_replay.py 生成于 {datetime.now():%Y-%m-%d %H:%M}；mode={mode}、"
             f"cap={cap} cm（示范搬运升程 p90）、sample={sample} -->")
    L.append("")
    L.append(f"* {law}")
    L.append(f"* 样本：`{sample}` 共 {n_pool} 局里「侧躺 ∧ 搬运期末端升程最高」的 **{len(cands)} 局**（挑最坏的 ⇒ 保守）。")
    L.append("* 每局重放两遍：不加限位（自证重放台）+ 加限位（与 GPU 上跑的是**同一份** `mg_eval_zlim` 代码，不是复制品）。")
    L.append(f"* 重放台自证：不加限位时 `eef_z` 与 npz 记录的 `state[:,2]` 的 `max|Δ| = {fid:.2e}`（容差 {FID_TOL:g}）"
             f"{'✅' if fid < FID_TOL else '🚫'}")
    L.append(f"* 门槛（预注册 增补 1 ④）：**≥ {g['need']}/{g['n']} 局**的搬运期最大升程 ≤ cap + {g['tol']} cm = {cap + g['tol']:.2f} cm"
             + ("（样本侧躺局不足 12 ⇒ 按 11/12 同比例缩，见 `need_of`）" if g["n"] < N_PICK else ""))
    L.append("")
    L.append("| 臂 | seed | 局 | 不加限位升程 | **加限位后升程** | 压低了 | 限位介入步数 | 侧躺 |")
    L.append("|:--|--:|--:|---:|---:|---:|---:|:--|")
    for c, o, n in zip(cands, off, on):
        L.append(f"| {c['arm']} | {c['seed']} | {o['dir'][-14:]}#{c['ep']} | {o['rise_cm']:.2f} cm "
                 f"| **{n['rise_cm']:.2f} cm** | {o['rise_cm'] - n['rise_cm']:+.2f} | {n['n_held']} | {'侧躺' if c['tipped'] else '立着'} |")
    L.append("")
    held_off = sum(1 for r in off if r["rise_cm"] == r["rise_cm"] and r["rise_cm"] <= cap + TOL_CM)
    L.append(f"* 不加限位时本来就在天花板内的：{held_off}/{len(off)} 局；加限位后：{g['held']}/{g['n']} 局 ⇒ "
             f"**{tag} = {'PASS ✅' if g['pass'] else 'FAIL 🚫'}**")
    over = [r["rise_cm"] - cap for r in on if r["rise_cm"] == r["rise_cm"]]
    if over:
        L.append(f"* 加限位后的升程：min {min(over) + cap:.2f} / 中位 {float(np.median(over)) + cap:.2f} / "
                 f"max {max(over) + cap:.2f} cm（cap={cap:.2f}，门线={cap + g['tol']:.2f}）")
    L.append(f"* 平均压低 {np.mean([o['rise_cm'] - n['rise_cm'] for o, n in zip(off, on)]):.2f} cm；"
             f"限位介入步数均值 {np.mean([n['n_held'] for n in on]):.1f} 步/局")
    L.append("")
    L.append("## 判读")
    L.append("")
    if g["pass"]:
        L.append(f"* ✅ 控制器**有力气**把搬运升程按在示范 p90 之内 ⇒ 可以上 GPU 跑 Z1–Z3 的闭环实验。")
        L.append("* ⚠️ 但这只证明「按得住高度」。「按住了还能不能把 can 送到、会不会把侧躺变成别的失败」"
                 "⇒ 只有闭环评测能答（预注册 §4 诚实标注 4）。")
    else:
        L.append("* 🚫 控制器按不住（或按住的局数不够）⇒ **不许上 GPU**；处方 = 换控制律 / 提高增益 / 承认这条路线不通，"
                 "回 `runs/S9_PREREG.md` §3.4 的分支乙。任何改动都要先写增补、再重跑本台（门槛与样本不许动）。")
    L.append("")
    L.append("## 复现")
    L.append("")
    L.append("```bash")
    L.append("source code/env.sh")
    L.append("$MG_PY code/mg_zlim_replay.py --selftest")
    L.append(f"$MG_PY {meta['argv']}")
    L.append("```")
    return "\n".join(L) + "\n"


def selftest() -> int:
    fails: list[str] = []
    total = [0]

    def ck(name: str, cond: bool) -> None:
        total[0] += 1
        if not cond:
            fails.append(name)

    w = np.array([0.0417] * 5 + [0.079] * 5 + [0.050] * 20 + [0.079] * 5)
    cw = carry_window(w)
    ck("c1 搬运段定位（张开 5..9 → 合上 10 → 释放 30）", cw == (10, 30))
    ck("c2 从没张开 ⇒ None", carry_window(np.array([0.0417] * 10)) is None)
    ck("c3 张开了但没合上 ⇒ None", carry_window(np.array([0.0417] * 3 + [0.079] * 10)) is None)
    ck("c4 没释放 ⇒ 段尾 = 序列末", carry_window(np.array([0.079] * 3 + [0.050] * 7))[1] == 9)
    ck("c5 复位开口 0.0417 不算张开（阈值来自 env 实测常数）",
       carry_window(np.array([0.0417] * 10 + [0.050] * 5)) is None)

    z = np.array([0.95, 0.96, 1.07, 1.0715, 1.06])
    ck("r1 升程 = 段内最大 − 锚点（cm）", abs(rise_cm(z, 0, 4) - 12.15) < 1e-9)
    ck("r2 锚点在段起点，不是序列起点", abs(rise_cm(np.array([0.5, 0.95, 1.07]), 1, 2) - 12.0) < 1e-9)
    ck("r3 单步段 ⇒ 升程 0", rise_cm(np.array([1.0, 1.05]), 1, 1) == 0.0)

    cands = [{"tipped": True, "eef_rise_cm": v, "seed": i} for i, v in enumerate([13.0, 18.0, 12.0, 22.0])]
    cands += [{"tipped": False, "eef_rise_cm": 99.0, "seed": 100}]
    pk = pick(cands, 3)
    ck("p1 只挑侧躺局", all(c["tipped"] for c in pk))
    ck("p2 按升程降序挑最坏的 N 局", [c["eef_rise_cm"] for c in pk] == [22.0, 18.0, 13.0])
    ck("p3 立着局再高也不进样本（本闸只问「最坏情况按不按得住」）", 100 not in [c["seed"] for c in pk])

    good = [{"rise_cm": CAP_MAIN + 0.5}] * 11 + [{"rise_cm": CAP_MAIN + 3.0}]
    ck("g1 11/12 按住 ⇒ PASS", gate(good)["pass"] is True)
    ck("g2 10/12 按住 ⇒ FAIL", gate([{"rise_cm": CAP_MAIN + 0.5}] * 10 + [{"rise_cm": 99.0}] * 2)["pass"] is False)
    ck("g3 恰好 cap+tol ⇒ 算按住", gate([{"rise_cm": CAP_MAIN + TOL_CM}] * 12)["held"] == 12)
    ck("g4 nan（没定位到搬运段）⇒ 不算按住", gate([{"rise_cm": float("nan")}] * 12)["held"] == 0)
    ck("g5 常数与预注册一致", (CAP_MAIN, TOL_CM, NEED, N_PICK) == (12.15, 1.0, 11, 12))

    # 限位器同源（本台用的必须是 GPU 上那一份，不是复制品）
    f = build_filter("ceilhold", 12.15, 0.5)
    a = np.array([0.0, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    f.phase(0.079); f.arm(0.95, 1)
    hit = f.apply(a, 0.95 + 0.1315)
    ck("s1 同源 CarryCeiling：越界 1 cm ⇒ dz=-0.5", hit and abs(float(a[2]) + 0.5) < 1e-6)
    ck("s2 阈值常数来自 mg_eval_zlim（单一真理源）", (OPEN_THR, GRASP_THR, RELEASE_THR) == (0.07, 0.058, 0.062))
    f2 = build_filter(MODE_DEF, 12.15)
    ck("s3 本台默认用 v2（ceilpred），且与 GPU 上跑的是同一个类", f2.mode == "ceilpred"
       and type(f2).__name__ == "CarryPredict" and abs(f2.k_eff - 1.2981 * 1.4702) < 1e-3)
    ck("s4 样本表：test = 20 个目录、val = 5 个关门格", (len(sample_dirs("test")), len(sample_dirs("val"))) == (20, 5))
    try:
        sample_dirs("nope"); ck("s5 未知样本必须抛", False)
    except ValueError:
        ck("s5 未知样本必须抛", True)
    ck("s6 门槛缩放：n=12 ⇒ 11；n=6 ⇒ 6；n=1 ⇒ 1；n=0 ⇒ 1（不许假过）",
       (need_of(12), need_of(6), need_of(1), need_of(0)) == (11, 6, 1, 1))
    ck("s7 n=0 时 gate 必不过", gate([], 12.15, 1.0)["pass"] is False)
    ck("s8 v1 留档可复现（同一台上 ceilhold 仍能构造）", build_filter("ceilhold", 12.15, 0.5).mode == "ceilhold")

    print(f"Z0b 可行性台钉子：{total[0]} 项检查，{len(fails)} 项失败")
    for x in fails:
        print("  🚫", x)
    print("ALL PASS" if not fails else "HAS FAILURES")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap-cm", type=float, default=CAP_MAIN)
    ap.add_argument("--kp", type=float, default=0.5)
    ap.add_argument("--n", type=int, default=N_PICK)
    ap.add_argument("--img-size", type=int, default=8, help="重放渲染尺寸（8 ⇒ 快；已证不扰动物理，见重放台对账）")
    ap.add_argument("--mode", choices=("ceilpred", "ceilhold"), default=MODE_DEF,
                    help="ceilpred=v2 终点预测式节流（本档）；ceilhold=v1 越界反向 P（留档复现 0/12 那次）")
    ap.add_argument("--sample", choices=("test", "val"), default="test",
                    help="test=Z0b 主闸（TEST 7000..，400 局）；val=Z0b′ 独立确认台（val 8000..，100 局）")
    ap.add_argument("--safety", type=float, default=SAFETY, help="v2 安全系数（默认 = mg_s9b_gain 的公式值 1.4702）")
    ap.add_argument("--b", default="", help="v2 脉冲响应 b0,b1,b2,b3（默认 = mg_s9b_gain 量出的 B_CARRY）")
    ap.add_argument("--out", default="")
    ap.add_argument("--json-out", default="")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    tag = "Z0b" if args.sample == "test" else "Z0b′"
    suffix = ("" if args.sample == "test" else "_val") + ("" if args.mode == MODE_DEF else f"_{args.mode}")
    outp = Path(args.out) if args.out else MG_ROOT / f"runs/_diag/s9_tax/z0b_feasibility{suffix}.md"
    jp = Path(args.json_out) if args.json_out else MG_ROOT / f"runs/_diag/s9_tax/z0b_feasibility{suffix}.json"
    b = tuple(float(x) for x in args.b.split(",")) if args.b.strip() else B_CARRY

    cands = scan(args.sample)
    if not cands:
        print(f"[z0b] 🚫 样本 {args.sample} 扫不到任何产物 ⇒ 无法做可行性闸", file=sys.stderr)
        return 3
    pk = pick(cands, args.n)
    print(f"[z0b] {tag} sample={args.sample} mode={args.mode} cap={args.cap_cm} safety={args.safety}；"
          f"扫到 {len(cands)} 局；挑「侧躺 ∧ 升程最高」的 {len(pk)} 局（升程 "
          f"{pk[-1]['eef_rise_cm']:.2f}~{pk[0]['eef_rise_cm']:.2f} cm）")
    if len(pk) < args.n:
        print(f"[z0b] ⚠️ 侧躺局只有 {len(pk)} 条（< {args.n}）⇒ 门槛按 need_of 同比例缩到 {need_of(len(pk))}")
    off, on = [], []
    for c in pk:
        o = replay_one(c, 0.0, args.kp, args.img_size, args.mode, b, args.safety)
        n = replay_one(c, args.cap_cm, args.kp, args.img_size, args.mode, b, args.safety)
        off.append(o); on.append(n)
        print(f"  {c['arm']} seed={c['seed']} ep={c['ep']}: 不加限位 {o['rise_cm']:6.2f} cm（离线 {o['rise_offline_cm']:6.2f}，"
              f"保真 {o['fid_max_dev']:.1e}）→ 加限位 {n['rise_cm']:6.2f} cm（介入 {n['n_held']} 步）")
    fid = max(r["fid_max_dev"] for r in off)
    if fid >= FID_TOL:
        print(f"[z0b] 🚫 重放台自证失败：max|Δeef_z| = {fid:.2e} ≥ {FID_TOL:g} ⇒ 全部读数作废", file=sys.stderr)
        return 3
    g = gate(on, args.cap_cm, TOL_CM)
    meta = {"cap": args.cap_cm, "kp": args.kp, "mode": args.mode, "tag": tag, "sample": args.sample,
            "n_pool": len(cands), "safety": args.safety, "k": float(sum(b)),
            "k_eff": float(sum(b)) * args.safety, "argv": " ".join(sys.argv)}
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(write_md(pk, off, on, g, fid, meta))
    jp.write_text(json.dumps({"tag": tag, "sample": args.sample, "mode": args.mode, "cap_cm": args.cap_cm,
                              "kp": args.kp, "b": list(b), "safety": args.safety, "k": float(sum(b)),
                              "k_eff": float(sum(b)) * args.safety, "n_pool": len(cands),
                              "gate": {k: v for k, v in g.items() if k != "not_held"},
                              "fid_max_dev": fid, "off": off, "on": on,
                              "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                             ensure_ascii=False, indent=1, default=str))
    print(f"[z0b] 重放台自证 max|Δ| = {fid:.2e} ✅；按住 {g['held']}/{g['n']}（门 ≥{g['need']}）⇒ "
          f"{tag} = {'PASS' if g['pass'] else 'FAIL'}")
    print(f"[z0b] 落盘 -> {outp} / {jp}")
    return 0 if g["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
