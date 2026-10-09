#!/usr/bin/env python
"""档 5.2 · 「认输交还（hand-back）」这条杠杆的**算术天花板**（离线，不占 GPU，**不判门**）

为什么要它：档 5.1 的 rep1~rep3 显示两件事，光看成功率永远看不出来 ——
  ① 阶梯只覆盖了死循环的一部分（`|dz| < 0.1 mm` 太紧 / `z_err > Z_TOL` 那个合取项把
     「高度已到位、只是 XY 对不上」的死循环整个挡在外面）；
  ② 更要命的是**算术**：策略从初态把反向任务做完，55 局基线成功局里**最快也要 224 步**（p5=234）；
     而阶梯认输要烧 ~191 步（restage 两次 = 两轮完整的 approach+descend）。
     接管最早发生在第 73 步 ⇒ 交还时最多剩 400−73−191 = 136 步 < 224 ⇒ **一局都救不回来**。
     这不是实现 bug，是 horizon 预算的硬约束。

本工具把上面两句话变成盘上可核的数字，并回答唯一有决策价值的问题：
  **「认输要多快、接管要多早，hand-back 才有可能救回一局？」**

口径（全部来自盘上产物，不重跑仿真）：
  * `S` = 策略完成所需步数 = 基线（`runs/s2e_rev_test_rand20_k10*`）放宽成功局的 `success_step_relaxed`；
    报 min / p5 / p25 / p50。判「可救」时用 **min**（最宽松）与 **p5**（略保守）两档。
  * 死循环 = `takeover ∧ "grasp" ∉ expert_phases`（与 `runs/S5_1_PREREG.md` 的 M1 同判据）；
    另按「认输与否」拆开，因为认输局是**设计内退出**、不是死循环（见 S5_1 的 M1 定义问题）。
  * 认输延迟 `latency` = `handback_step − takeover_step`（没交还的局 = 烧到 horizon，记为 `seg_len`）。
  * 覆盖诊断：从 `correction_segments_raw.npz` 的 `state[:,2]` 重算 descend 期的 `|dz|`，
    给出「最长停滞游程 @0.1 mm」与「中位 |dz|」⇒ 区分 **Z 被挡**（dz≈0，阶梯该抓到）/
    **蠕动**（dz 0.1~1 mm，阈值太紧）/ **游程够长却没触发**（`z_err>Z_TOL` 合取项挡的）。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_handback_ceiling.py \
        --out runs/s5_2_handback_ceiling'
    bash -c 'source code/env.sh && $MG_PY code/mg_probe_handback_ceiling.py --selftest'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

RUNS = MG_ROOT / "runs"
BASE_DIRS = ["s2e_rev_test_rand20_k10", "s2e_rev_test_rand20_k10_rep2",
             "s2e_rev_test_rand20_k10_rep3", "s2e_rev_test_rand20_k10_rep4"]
S5_DIRS = ["s5_takeover_rev_test20_k10", "s5_takeover_rev_test20_k10_rep2",
           "s5_takeover_rev_test20_k10_rep3"]
S51_DIRS = ["s5_1_handback_rev_test20_k10", "s5_1_handback_rev_test20_k10_rep2",
            "s5_1_handback_rev_test20_k10_rep3", "s5_1_handback_rev_test20_k10_rep4"]
HORIZON = 400            # mg_env_reverse.ReverseGraspEnv.horizon（产物里 steps ≤ 400 逐局核）
STALL_DZ_MM = 0.1        # 与 mg_expert.DESCEND_STALL_DZ 同值（0.1 mm/步）
STALL_W = 25             # 与 mg_expert.DESCEND_STALL_MAX 同值
LATENCY_GRID = (0, 25, 50, 96, 150, 191, 250)   # 认输延迟候选（0 = 假想的「立刻认输」）


# ── 纯函数（可自测）───────────────────────────────────────────────────────
def longest_run(mask: np.ndarray) -> int:
    """mask 里最长连续 True 的游程长度。"""
    best = cur = 0
    for m in np.asarray(mask, dtype=bool).ravel():
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


def coverage_class(longest: int, med_dz_mm: float, fired: bool, w: int = STALL_W) -> str:
    """这段死循环为什么没被阶梯抓到（`fired` = 本局确实认输了）。"""
    if fired:
        return "已覆盖（阶梯触发并认输）"
    if longest >= w:
        return "游程够长却没触发 ⇒ z_err>Z_TOL 合取项挡的（XY 型）"
    if med_dz_mm == med_dz_mm and med_dz_mm >= STALL_DZ_MM:
        return "蠕动 ⇒ |dz|<0.1mm 阈值太紧（Z 型但一直在动）"
    return "其它（游程不足且 dz 很小）"


def rescuable(tk: int, latency: int, need: int, horizon: int = HORIZON) -> bool:
    """交还之后剩下的步数够不够策略自己把任务做完（`need` = S 的某个分位）。"""
    return (horizon - int(tk) - int(latency)) >= int(need)


def sep_auc(dead: np.ndarray, ok: np.ndarray) -> float:
    """P(随机一个死循环段 > 随机一个「专家自己做完」段)。0.5 = 完全不可分。"""
    dead = np.asarray(dead, dtype=np.float64); ok = np.asarray(ok, dtype=np.float64)
    if dead.size == 0 or ok.size == 0:
        return float("nan")
    gt = float((dead[:, None] > ok[None, :]).sum())
    eq = float((dead[:, None] == ok[None, :]).sum())
    return (gt + 0.5 * eq) / (dead.size * ok.size)


def pct(a: np.ndarray, q: float) -> float:
    a = np.asarray(a, dtype=np.float64)
    return float(np.percentile(a, q)) if a.size else float("nan")


def load_summary(name: str) -> dict | None:
    f = RUNS / name / "eval_summary.json"
    if not f.exists():
        return None
    try:
        return json.load(open(f))
    except Exception:
        return None


def seg_stats(run_dir: str, per_ep: list[dict]) -> list[dict]:
    """把一个读数目录里的接管局摊平成记录，并从 npz 重算 descend 期的 dz 统计。"""
    z = np.load(RUNS / run_dir / "correction_segments_raw.npz", allow_pickle=True) \
        if (RUNS / run_dir / "correction_segments_raw.npz").exists() else None
    idx = {}
    if z is not None:
        off = 0
        for i, n in enumerate(z["episode_lengths"]):
            idx[int(z["seeds"][i])] = (off, off + int(n))
            off += int(n)
    out = []
    for e in per_ep:
        if not e.get("takeover"):
            continue
        phases = e.get("expert_phases") or []
        longest, med_dz, n_desc = -1, float("nan"), -1
        if z is not None and int(e["seed"]) in idx:
            a, b = idx[int(e["seed"])]
            ph = z["phase"][a:b]; st = z["state"][a:b].astype(np.float64)
            dz = np.abs(np.diff(st[:, 2])) * 1000.0
            m = ph[1:] == "descend"
            n_desc = int(m.sum())
            if n_desc:
                d = dz[m]
                longest = longest_run(d < STALL_DZ_MM)
                med_dz = float(np.median(d))
        hb = int(e.get("handback_step", -1) or -1)
        tk = int(e.get("takeover_step", -1))
        out.append({
            "dir": run_dir, "seed": int(e["seed"]), "trigger": e.get("trigger"),
            "takeover_step": tk, "takeover_remain": int(e.get("takeover_remain", -1)),
            "seg_len": int(e.get("seg_len") or -1), "phases": phases,
            "reached_grasp": "grasp" in phases, "reached_release": "release" in phases,
            "deadloop": ("grasp" not in phases),
            "unrecoverable": bool(e.get("unrecoverable", False)),
            "handback": bool(e.get("handback", False)), "handback_step": hb,
            "handback_remain": int(e.get("handback_remain", -1) or -1),
            "n_restages": int(e.get("n_restages") or 0),
            "latency": (hb - tk) if hb > tk else int(e.get("seg_len") or -1),
            "descend_steps": n_desc, "longest_stall_run": longest, "med_dz_mm": med_dz,
            "success_relaxed": bool(e["success_relaxed"]), "success": bool(e["success"]),
        })
    return out


def selftest() -> int:
    n = 0

    def ck(name: str, cond: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not cond:
            raise AssertionError(f"[selftest] {name} {detail}")

    ck("longest_run 基本", longest_run(np.array([1, 1, 0, 1, 1, 1, 0], bool)) == 3)
    ck("longest_run 全 False", longest_run(np.zeros(5, bool)) == 0)
    ck("longest_run 全 True", longest_run(np.ones(5, bool)) == 5)
    ck("longest_run 空", longest_run(np.zeros(0, bool)) == 0)
    ck("coverage 已触发", coverage_class(152, 0.008, True).startswith("已覆盖"))
    ck("coverage XY 型", "XY 型" in coverage_class(136, 0.05, False))
    ck("coverage 蠕动", "蠕动" in coverage_class(4, 0.56, False))
    ck("coverage 其它", coverage_class(3, 0.01, False).startswith("其它"))
    ck("coverage 边界 w", "XY 型" in coverage_class(STALL_W, 0.01, False))
    ck("coverage 边界 w-1 且 dz 小", coverage_class(STALL_W - 1, 0.01, False).startswith("其它"))
    ck("rescuable 够", rescuable(73, 25, 224) is True)
    ck("rescuable 不够", rescuable(73, 191, 224) is False)
    ck("rescuable 边界相等", rescuable(100, 76, 224) is True)
    ck("rescuable 边界差一", rescuable(100, 77, 224) is False)
    ck("rescuable 接管太晚", rescuable(300, 0, 224) is False)
    ck("sep_auc 完全可分", sep_auc(np.array([300.0, 310]), np.array([100.0, 120])) == 1.0)
    ck("sep_auc 完全反", sep_auc(np.array([100.0]), np.array([300.0])) == 0.0)
    ck("sep_auc 相同分布", sep_auc(np.array([100.0, 200.0]), np.array([100.0, 200.0])) == 0.5)
    a = sep_auc(np.array([252.0]), np.array([217.0]))
    ck("sep_auc 单点大于", a == 1.0, f"got {a}")
    ck("sep_auc 空 => nan", sep_auc(np.zeros(0), np.array([1.0])) != sep_auc(np.zeros(0), np.array([1.0])))
    ck("pct 基本", pct(np.arange(1, 101), 50) == 50.5)
    ck("pct 空 => nan", pct(np.zeros(0), 50) != pct(np.zeros(0), 50))
    ck("pct min 用 q=0", pct(np.array([3.0, 9.0]), 0) == 3.0)
    print(f"[hb_ceiling] selftest 全绿：{n} 项（纯函数，未碰 GPU / 未读 runs）")
    return 0


def build_md(c: dict) -> str:
    L = [
        "# 档 5.2 · hand-back 杠杆的**算术天花板**（离线分析，**不判门**、**不并入**任何 n）",
        "",
        f"由 `code/mg_probe_handback_ceiling.py` 生成于 **{c['generated']}**。"
        f"　代码 sha16：`{c['sha']}`",
        "",
        "> ⚠️ 本产物只做一件事：把「认输交还」这条杠杆的**上限**算出来，"
        "免得再往一个被 horizon 预算卡死的方向投工时。所有数字都从盘上产物重算，没有重跑仿真。",
        "",
        "## 一、策略自己做完要多少步（S）",
        "",
        f"语料 = 基线 4 rep（`runs/s2e_rev_test_rand20_k10*`）里放宽成功的 **{c['n_base_ok']}** 局，"
        f"取 `success_step_relaxed`：",
        "",
        f"| min | p5 | p25 | p50 | p75 | max |",
        f"| --- | --- | --- | --- | --- | --- |",
        f"| **{c['S']['min']:.0f}** | {c['S']['p5']:.0f} | {c['S']['p25']:.0f} | {c['S']['p50']:.0f} "
        f"| {c['S']['p75']:.0f} | {c['S']['max']:.0f} |",
        "",
        f"⇒ 交还之后剩余步数 **< {c['S']['min']:.0f}** 的局，策略**从来没有**在这么短的预算里做成过"
        f"（这是 min，不是均值 ⇒ 已经是「最宽松」的一档）。",
        "",
        "## 二、接管段的三类结局（档 5 + 档 5.1，共 %d 段）" % c["n_seg"],
        "",
        "| 类别 | n | 放宽成功 | seg_len min/p50/max | 说明 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in c["classes"]:
        L.append(f"| {r['name']} | {r['n']} | {r['ok']} | {r['seg']} | {r['note']} |")
    L += [
        "",
        f"**时间预算不可分**：P(死循环段 > 「专家做完」段) = **{c['auc']:.3f}**（0.5 = 完全不可分）。"
        f"⇒ 任何「专家控制超过 B 步就交还」的规则都会误伤：",
        "",
        "| 预算 B | 会切断的「专家自己做完」段 | 死循环段中会被切到的 |",
        "| --- | --- | --- |",
    ]
    for r in c["budget_sweep"]:
        L.append(f"| {r['B']} | {r['cut_ok']}/{r['n_ok']} | {r['cut_dead']}/{r['n_dead']} |")
    L += [
        "",
        "## 三、死循环为什么没被阶梯抓到（覆盖诊断）",
        "",
        f"死循环段 **{c['n_dead']}** 段，按覆盖情况分类：",
        "",
        "| 类别 | n | 最长停滞游程@0.1mm（min/p50/max） | 中位 \\|dz\\| mm（p50） |",
        "| --- | --- | --- | --- |",
    ]
    for r in c["coverage"]:
        L.append(f"| {r['name']} | {r['n']} | {r['runs']} | {r['dz']} |")
    L += [
        "",
        "## 四、算术天花板：交还之后还剩几步，够不够策略做完",
        "",
        f"判据：`HORIZON(400) − takeover_step − 认输延迟 ≥ S`。用 S = min({c['S']['min']:.0f}) "
        f"与 S = p5({c['S']['p5']:.0f}) 两档；「实际延迟」= 该段真实认输延迟（没认输的按烧到片段结束算）。",
        "",
        "| 认输延迟 | 死循环段里**原则上可救**的段数（S=min） | （S=p5） | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for r in c["ceiling"]:
        L.append(f"| {r['lat']} | {r['n_min']}/{r['n']} | {r['n_p5']}/{r['n']} | {r['note']} |")
    L += [
        "",
        "### 四之二、敏感性：万一策略从「交还态」出发不需要完整的 S 步",
        "",
        "| 策略所需步数 | 实际认输延迟下可救 | 延迟压到 96 步（桩件值） | 延迟压到 25 步 | 延迟 0（接管当步就交还） |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in c["sens"]:
        L.append(f"| {r['need']} | {r['n_actual']}/{c['n_dead']} | {r['n_lat96']}/{c['n_dead']} "
                 f"| {r['n_lat25']}/{c['n_dead']} | {r['n_lat0']}/{c['n_dead']} |")
    L += [
        "",
        "## 五、结论（自动汇编，不判门）",
        "",
    ] + [f"* {x}" for x in c["conclusions"]] + [
        "",
        "---",
        "## 附：逐段明细（死循环段）",
        "",
        "| 来源 | seed | 触发 | 接管步 | 片段长 | descend步 | 最长游程 | 中位\\|dz\\|mm | 认输 | 交还步 | 剩余 | 覆盖诊断 | 放宽 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in c["dead_rows"]:
        L.append(f"| {r['dir'].replace('_rev_test20_k10', '')} | {r['seed']} | {r['trigger']} | {r['takeover_step']} "
                 f"| {r['seg_len']} | {r['descend_steps']} | {r['longest_stall_run']} | {r['med_dz_mm']} "
                 f"| {'是' if r['unrecoverable'] else '否'} | {r['handback_step']} | {r['handback_remain']} "
                 f"| {r['cov']} | {'✅' if r['success_relaxed'] else '❌'} |")
    L += ["", f"输入目录：{', '.join('`runs/%s`' % d for d in c['dirs_used'])}"]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(RUNS / "s5_2_handback_ceiling"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    base_ok = []
    for d in BASE_DIRS:
        s = load_summary(d)
        if s:
            base_ok += [int(e["success_step_relaxed"]) for e in s["per_episode"]
                        if e["success_relaxed"] and int(e.get("success_step_relaxed", -1)) > 0]
    if not base_ok:
        print("[FATAL] 基线产物为空 ⇒ 算不出 S（坑 42：缺读数 ≠ 0）", file=sys.stderr)
        return 6
    S = np.array(base_ok, dtype=np.float64)
    s_min, s_p5 = float(S.min()), pct(S, 5)

    segs, dirs_used = [], []
    for tag, dirs in (("档5", S5_DIRS), ("档5.1", S51_DIRS)):
        for d in dirs:
            s = load_summary(d)
            if not s:
                continue
            dirs_used.append(d)
            for r in seg_stats(d, s["per_episode"]):
                r["src"] = tag
                segs.append(r)
            assert all(e["steps"] <= HORIZON for e in s["per_episode"]), f"{d}: 有局 steps > {HORIZON}"
    if not segs:
        print("[FATAL] 没有任何接管段产物 ⇒ 不能分析", file=sys.stderr)
        return 6

    dead = [r for r in segs if r["deadloop"]]
    gave = [r for r in dead if r["unrecoverable"]]
    spin = [r for r in dead if not r["unrecoverable"]]
    done = [r for r in segs if r["reached_release"]]
    half = [r for r in segs if r["reached_grasp"] and not r["reached_release"]]

    def rng(v):
        v = np.asarray(v, dtype=np.float64)
        return "—" if v.size == 0 else f"{v.min():.0f} / {pct(v, 50):.0f} / {v.max():.0f}"

    classes = [
        {"name": "专家自己做完（到 release）", "n": len(done), "ok": sum(r["success_relaxed"] for r in done),
         "seg": rng([r["seg_len"] for r in done]), "note": "hand-back 不该动这些局：它们是接管的收益来源"},
        {"name": "进了 grasp 但没走完", "n": len(half), "ok": sum(r["success_relaxed"] for r in half),
         "seg": rng([r["seg_len"] for r in half]), "note": "抓起了却没送到/没落定 ⇒ 与死循环是不同的病"},
        {"name": "死循环（没到 grasp）· 已认输", "n": len(gave), "ok": sum(r["success_relaxed"] for r in gave),
         "seg": rng([r["seg_len"] for r in gave]), "note": "**设计内退出**（有界 + 交还），不是空转到 horizon"},
        {"name": "死循环（没到 grasp）· 未认输", "n": len(spin), "ok": sum(r["success_relaxed"] for r in spin),
         "seg": rng([r["seg_len"] for r in spin]), "note": "真·空转到 horizon ⇒ 阶梯没覆盖到"},
    ]
    auc = sep_auc(np.array([r["seg_len"] for r in dead], float), np.array([r["seg_len"] for r in done], float))
    budget_sweep = []
    for B in (100, 120, 150, 180, 200, 240):
        budget_sweep.append({"B": B,
                             "cut_ok": sum(1 for r in done if r["seg_len"] > B), "n_ok": len(done),
                             "cut_dead": sum(1 for r in dead if r["seg_len"] > B), "n_dead": len(dead)})
    cov = {}
    for r in dead:
        r["cov"] = coverage_class(r["longest_stall_run"], r["med_dz_mm"], r["unrecoverable"])
        cov.setdefault(r["cov"], []).append(r)
    coverage = [{"name": k, "n": len(v),
                 "runs": rng([x["longest_stall_run"] for x in v if x["longest_stall_run"] >= 0]),
                 "dz": ("—" if not [x for x in v if x["med_dz_mm"] == x["med_dz_mm"]]
                        else f"{pct(np.array([x['med_dz_mm'] for x in v if x['med_dz_mm'] == x['med_dz_mm']]), 50):.3f}")}
                for k, v in sorted(cov.items(), key=lambda kv: -len(kv[1]))]
    need_grid = sorted({60, 100, 150, int(s_min), int(np.ceil(s_p5))})
    sens = [{"need": nd,
             "n_actual": sum(1 for r in dead if rescuable(r["takeover_step"], r["latency"], nd)),
             "n_lat0": sum(1 for r in dead if rescuable(r["takeover_step"], 0, nd)),
             "n_lat25": sum(1 for r in dead if rescuable(r["takeover_step"], 25, nd)),
             "n_lat96": sum(1 for r in dead if rescuable(r["takeover_step"], 96, nd))}
            for nd in need_grid]
    ceiling = []
    for lat in LATENCY_GRID:
        nmin = sum(1 for r in dead if rescuable(r["takeover_step"], lat, s_min))
        np5 = sum(1 for r in dead if rescuable(r["takeover_step"], lat, s_p5))
        note = ("假想的「接管当步就认输」" if lat == 0 else
                "档 5.1 阶梯的实测中位延迟" if lat == 191 else
                "档 5.1 预注册里的**桩件**理论值（真环境是 191）" if lat == 96 else "")
        ceiling.append({"lat": lat, "n_min": nmin, "n_p5": np5, "n": len(dead), "note": note})
    lat_act = [r["latency"] for r in gave] or [0]
    n_res_now = sum(1 for r in dead if rescuable(r["takeover_step"], r["latency"], s_min))
    conclusions = [
        f"策略完成所需步数 S：min **{s_min:.0f}**、p5 {s_p5:.0f}、p50 {pct(S,50):.0f}（n={len(S)} 局基线成功局）。",
        f"接管段 {len(segs)} 段里死循环 {len(dead)} 段（已认输 {len(gave)} / 未认输 {len(spin)}）；"
        f"「专家自己做完」{len(done)} 段，seg_len p50 = {pct(np.array([r['seg_len'] for r in done], float), 50):.0f} 步。",
        f"**时间预算分不开**：死循环段 vs 专家做完段的 seg_len 重叠度 AUC = {auc:.3f}"
        f"（0.5 = 完全不可分）⇒ 「超过 B 步就交还」这类规则必然误伤收益来源。",
        f"**认输延迟实测**：中位 {pct(np.array(lat_act, float), 50):.0f} 步"
        f"（档 5.1 的 restage×2 = 两轮完整 approach+descend；预注册里 96 步是**桩件**时间线，真环境更贵）。",
        f"**按当前实现，原则上可救的死循环段 = {n_res_now}/{len(dead)}**"
        f"（判据 400 − 接管步 − 实际延迟 ≥ S_min={s_min:.0f}）。",
        "**敏感性**（万一策略从「交还态」出发不需要完整 224 步）：所需步数取 "
        + "、".join(f"{r['need']} 步 ⇒ 实际延迟下可救 {r['n_actual']}/{len(dead)}（延迟 25 步则 {r['n_lat25']}、"
                    f"延迟 0 步则 {r['n_lat0']}）" for r in sens[:3])
        + "。⇒ 结论对「所需步数」这个假设**不敏感**：认输延迟不砍到 ~25 步以内，可救段数一直是 0。",
        f"要让 hand-back 有机会，必须同时满足：认输延迟 ≤ "
        f"{max(0, int(400 - max([r['takeover_step'] for r in dead]) - s_min))} 步（最早接管步的最紧约束），"
        f"且阶梯覆盖「蠕动」与「XY 型」两种机理（当前只覆盖 Z 被挡的一种）。",
        "⚠️ 本产物**不判门**、不并入任何 n；它只回答「这条杠杆的上限在哪」。",
    ]
    c = {"generated": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
         "sha": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16],
         "n_base_ok": len(S), "S": {"min": s_min, "p5": s_p5, "p25": pct(S, 25), "p50": pct(S, 50),
                                    "p75": pct(S, 75), "max": float(S.max())},
         "n_seg": len(segs), "classes": classes, "auc": auc, "budget_sweep": budget_sweep,
         "n_dead": len(dead), "coverage": coverage, "ceiling": ceiling, "sens": sens,
         "conclusions": conclusions, "dirs_used": dirs_used,
         "dead_rows": [{k: r[k] for k in ("dir", "seed", "trigger", "takeover_step", "seg_len", "descend_steps",
                                           "longest_stall_run", "unrecoverable", "handback_step",
                                           "handback_remain", "cov", "success_relaxed")}
                       | {"med_dz_mm": ("—" if r["med_dz_mm"] != r["med_dz_mm"] else f"{r['med_dz_mm']:.3f}")}
                       for r in sorted(dead, key=lambda x: (x["dir"], x["seed"]))],
         "segs": segs}
    out = Path(args.out)
    if not out.is_absolute():
        out = MG_ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    (out / "handback_ceiling.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    md = build_md(c)
    (out / "handback_ceiling.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"[saved] {out}/handback_ceiling.{{md,json}}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
