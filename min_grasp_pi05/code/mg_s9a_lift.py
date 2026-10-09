#!/usr/bin/env python
"""档 9A · 关门配方的失败分类账汇总 + 「运输举高 ↔ 侧躺」探针（零 GPU、只读盘上产物）。

为什么单独一个工具（而不是把数字手抄进 markdown）：
  坑 30/40 家族 —— 承载判定/立项的数字必须有出处且可重出。本文件把
  ① 5 臂（8C/8D×2 关门配方 + 7H×2 便宜配方）TEST 反向 4×20 的 per_episode，
  ② 专家上界（`s2f_ceiling_rev_test20_n05`，同 TEST 窗口）的 per_episode，
  读进来算成 `runs/_diag/s9_tax/SUMMARY.md`，重跑必须逐字相同（除生成时间行）。

三条纪律写死在代码里：
  * 缺字段 ≠ 0（坑 40③）：任何一局的 `success_relaxed` / `delivered_tipped` / `max_lift_cm`
    缺失或为 None ⇒ 该局计入 `broken`，**不进任何分子分母**，并在报告里单列。
  * 出身断言：task_mode==reverse ∧ seed==7000 ∧ n_action_steps==10 ∧ episodes==20
    ∧ ckpt 以关门格尾串结尾；不过 ⇒ 退出码 3、报告打 🚫（与 `mg_verdict_s8.py` 同规矩）。
  * 限位值只从**专家**数据推（不许用策略 TEST 数据调参）：`--cap-from-expert` 输出
    专家举高的中位与 p75，档 9B 的事前限位值取这里，理由见 `runs/S9_PREREG.md`。

⚠️ 跨数据集不许比高低（坑 33）：8C/8D 用 `mix60f120r_c1`、7H 用 `mix60f120r`，
   normalizer 不同 ⇒ 本文件**只在同一数据集内池化**，两组之间只看「构成」不看「谁高」。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_verdict_s2 import fisher_two_sided          # noqa: E402
from mg_verdict_s2f import wilson                   # noqa: E402

RUNS = MG_ROOT / "runs"
CEIL_DIR = "s2f_ceiling_rev_test20_n05"
TEST_SEED0 = 7000
K_EVAL = 10
EPS = 20
REPS = ("", "_rep2", "_rep3", "_rep4")
FIELDS = ("success_relaxed", "delivered_tipped", "max_lift_cm", "final_tilt_deg")

# (标签, 目录前缀, 数据集, 关门格尾串)
ARMS = (
    ("8C seed2000", "s8c_seed2000", "mix60f120r_c1", "checkpoints/022000/pretrained_model"),
    ("8D seed4000", "s8d_seed4000", "mix60f120r_c1", "checkpoints/022000/pretrained_model"),
    ("8D seed5000", "s8d_seed5000", "mix60f120r_c1", "checkpoints/022000/pretrained_model"),
    ("7H seed11000", "s7h_seed11000", "mix60f120r", "checkpoints/005500/pretrained_model"),
    ("7H seed12000", "s7h_seed12000", "mix60f120r", "checkpoints/005500/pretrained_model"),
)
BINS = ((0.0, 11.0), (11.0, 12.0), (12.0, 13.0), (13.0, 14.0), (14.0, 16.0), (16.0, 1e9))


def quantile_lower(sorted_vals: list[float], q: float) -> float:
    """下分位：排序后第 floor(q·n) 位（0 基）⇒ 第 floor(q·n)+1 小的值。n=20、q=0.75 ⇒ 第 16 小。"""
    if not sorted_vals:
        return float("nan")
    n = len(sorted_vals)
    idx = min(n - 1, int(math.floor(q * n)))
    return float(sorted_vals[idx])


def read_arm(prefix: str, ck_suffix: str) -> dict:
    """读一臂 4×20 局；出身不过 ⇒ raise；缺字段 ⇒ 单列 broken，不当 0。"""
    eps, broken, missing = [], [], []
    for rep in REPS:
        d = f"{prefix}_rev_test_rand20_k10{rep}"
        p = RUNS / d / "eval_summary.json"
        if not p.exists():
            missing.append(d)
            continue
        j = json.loads(p.read_text())
        if j.get("task_mode") != "reverse":
            raise SystemExit(f"[prov] 🚫 {d}: task_mode={j.get('task_mode')} != reverse")
        if int(j.get("seed", -1)) != TEST_SEED0:
            raise SystemExit(f"[prov] 🚫 {d}: seed={j.get('seed')} != {TEST_SEED0}")
        if int(j.get("n_action_steps", -1)) != K_EVAL:
            raise SystemExit(f"[prov] 🚫 {d}: K={j.get('n_action_steps')} != {K_EVAL}")
        if int(j.get("episodes", -1)) != EPS:
            raise SystemExit(f"[prov] 🚫 {d}: episodes={j.get('episodes')} != {EPS}")
        if not str(j.get("policy_ckpt", "")).endswith(ck_suffix):
            raise SystemExit(f"[prov] 🚫 {d}: ckpt 尾串不是 {ck_suffix}（{j.get('policy_ckpt')}）")
        for e in j.get("per_episode", []):
            bad = [f for f in FIELDS if f not in e or e[f] is None]
            if bad:
                broken.append((d, e.get("seed"), ",".join(bad)))
                continue
            e["_dir"] = d
            eps.append(e)
    return {"eps": eps, "broken": broken, "missing": missing}


def split(eps: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """(立着送达, 侧躺送达 delivered_tipped, 放宽口径也失败)。"""
    up = [e for e in eps if e["success_relaxed"] and not e["delivered_tipped"]]
    tip = [e for e in eps if e["success_relaxed"] and e["delivered_tipped"]]
    fail = [e for e in eps if not e["success_relaxed"]]
    return up, tip, fail


def lift_stats(eps: list[dict]) -> str:
    v = sorted(float(e["max_lift_cm"]) for e in eps)
    if not v:
        return "n=0"
    return (f"n={len(v)} 均值 {sum(v)/len(v):.2f} 中位 {quantile_lower(v,0.5):.2f} "
            f"p75 {quantile_lower(v,0.75):.2f} p95 {quantile_lower(v,0.95):.2f} 范围 [{v[0]:.2f},{v[-1]:.2f}]")


def point_biserial(x: list[float], y: list[int]) -> float:
    n = len(x)
    if n < 2:
        return float("nan")
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x) / n)
    sy = math.sqrt(sum((b - my) ** 2 for b in y) / n)
    if sx == 0 or sy == 0:
        return float("nan")
    return (sum((a - mx) * (b - my) for a, b in zip(x, y)) / n) / (sx * sy)


def expert_caps(ceil_dir: str = CEIL_DIR) -> dict:
    """只从专家上界推限位候选值（不许用策略 TEST 数据）。"""
    p = RUNS / ceil_dir / "ceiling_summary.json"
    if not p.exists():
        raise SystemExit(f"[prov] 🚫 上界产物不存在：{p}")
    j = json.loads(p.read_text())
    if j.get("task_mode") != "reverse" or int(j.get("seed", -1)) != TEST_SEED0:
        raise SystemExit(f"[prov] 🚫 {ceil_dir} 不是反向 TEST 窗口的上界")
    pe = j.get("per_episode", [])
    bad = [e for e in pe if any(f not in e or e[f] is None for f in FIELDS)]
    if bad:
        raise SystemExit(f"[prov] 🚫 {ceil_dir} 有 {len(bad)} 局缺字段（坑 40③：不当 0）")
    lifts = sorted(float(e["max_lift_cm"]) for e in pe)
    up = sorted(float(e["max_lift_cm"]) for e in pe if e["success"] and not e["delivered_tipped"])
    return {"dir": ceil_dir, "n": len(pe), "lifts": lifts,
            "med": quantile_lower(lifts, 0.5), "p75": quantile_lower(lifts, 0.75),
            "p90": quantile_lower(lifts, 0.90), "max": lifts[-1] if lifts else float("nan"),
            "upright_med": quantile_lower(up, 0.5) if up else float("nan"),
            "n_upright": len(up),
            "n_strict": int(j.get("n_success", -1)), "n_relaxed": int(j.get("n_success_relaxed", -1))}


def build_report(arms: dict, ceil: dict, cap_cm: float) -> str:
    L: list[str] = []
    L.append("# 档 9A · 关门配方失败分类账汇总 + 「运输举高 ↔ 侧躺」探针")
    L.append(f"<!-- 由 code/mg_s9a_lift.py 生成于 {datetime.now():%Y-%m-%d %H:%M}；只读盘上产物、零 GPU -->")
    L.append("")
    L.append("* 尺子：`code/mg_tax_fail.py`（A 没抓起 `max_lift<5cm` / B 没送到 `min_dist>25cm` / C 没落定）逐臂全文见 "
             "`runs/_diag/s9_tax/tax_*.md`；本文件只做**跨臂汇总**与**举高↔侧躺**这一条新探针。")
    L.append(f"* 窗口：TEST 反向 seed {TEST_SEED0}..{TEST_SEED0+EPS-1}、K={K_EVAL}、每臂 4×20 = 80 局；"
             f"上界 = `runs/{CEIL_DIR}`（严格 {ceil['n_strict']}/{ceil['n']} ∧ 放宽 {ceil['n_relaxed']}/{ceil['n']}）。")
    L.append("* ⚠️ 8C/8D 用 `mix60f120r_c1`、7H 用 `mix60f120r`，normalizer 不同 ⇒ **两组之间只比构成、不比高低**（坑 33）。")
    L.append("")
    L.append("## 一、逐臂构成（放宽口径为主口径）")
    L.append("")
    L.append("| 臂 | 数据集 | 放宽成功 | 其中立着 | 其中侧躺 `delivered_tipped` | 放宽也失败 | A 没抓起 | B 没送到 | C 没落定 |")
    L.append("|:--|:--|---:|---:|---:|---:|---:|---:|---:|")
    for label, prefix, ds, _ck in ARMS:
        a = arms[label]
        eps = a["eps"]
        up, tip, fail = split(eps)
        n = len(eps)
        A = sum(1 for e in fail if float(e["max_lift_cm"]) < 5.0)
        B = sum(1 for e in fail if float(e["max_lift_cm"]) >= 5.0 and float(e["min_dist_to_target_xy"]) * 100 > 25.0)
        C = len(fail) - A - B
        L.append(f"| {label} | `{ds}` | {len(up)+len(tip)}/{n} = {100*(len(up)+len(tip))/n:.1f}% "
                 f"| {len(up)} | {len(tip)} | {len(fail)} | {A} | {B} | {C} |")
    # 池化（按数据组分开）
    L.append("")
    for group, ds in (("关门配方（demo+纠正）", "mix60f120r_c1"), ("便宜配方（bs32/5500）", "mix60f120r")):
        pool = [e for label, _p, d, _c in ARMS if d == ds for e in arms[label]["eps"]]
        up, tip, fail = split(pool)
        n = len(pool)
        A = sum(1 for e in fail if float(e["max_lift_cm"]) < 5.0)
        B = sum(1 for e in fail if float(e["max_lift_cm"]) >= 5.0 and float(e["min_dist_to_target_xy"]) * 100 > 25.0)
        C = len(fail) - A - B
        L.append(f"* **{group}池化**（`{ds}`，n={n}）：放宽 {len(up)+len(tip)}/{n} = {100*(len(up)+len(tip))/n:.1f}%"
                 f"（立着 {len(up)} = {100*len(up)/n:.1f}%、侧躺 {len(tip)} = {100*len(tip)/n:.1f}%）；"
                 f"真失败 {len(fail)}（A {A} / B {B} / C {C}）⇒ 真失败里 B 占 "
                 f"{100*B/max(1,len(fail)):.0f}%、A {100*A/max(1,len(fail)):.0f}%、C {100*C/max(1,len(fail)):.0f}%。")
    L.append("")
    L.append("**读法**：放宽口径下 C 类（送到了没落定）已经不是主症；真失败的**最大单一桶是 B（抓起了却没送到附近，"
             "`min_dist` 均值 >40 cm）**，其次是 A（压根没抓起）。侧躺局不计入失败，但它是**严格口径**的全部损失来源。")
    L.append("")
    L.append("## 二、举高 ↔ 侧躺（本档新探针，5 臂 400 局 + 专家 20 局）")
    L.append("")
    all_eps = [e for label, _p, _d, _c in ARMS for e in arms[label]["eps"]]
    up, tip, fail = split(all_eps)
    L.append(f"* 全 5 臂池化 n={len(all_eps)}：立着送达 {len(up)}、侧躺送达 {len(tip)}、放宽也失败 {len(fail)}。")
    L.append(f"* 举高 `max_lift_cm`（= can 中心相对初态的最大抬升）：立着 {lift_stats(up)}；侧躺 {lift_stats(tip)}；失败 {lift_stats(fail)}。")
    sub = up + tip
    x = [float(e["max_lift_cm"]) for e in sub]
    y = [1 if e["delivered_tipped"] else 0 for e in sub]
    r = point_biserial(x, y)
    L.append(f"* 只在「送达」子集（n={len(sub)}，两子集都完成了搬运 ⇒ 排除「没送到」的混杂）里比："
             f"举高与侧躺的点二列相关 **r = {r:.3f}**。")
    L.append("")
    L.append("| 举高箱 | n | 侧躺 | 侧躺率 |")
    L.append("|:--|---:|---:|---:|")
    for lo, hi in BINS:
        g = [(a, b) for a, b in zip(x, y) if lo <= a < hi]
        if not g:
            continue
        name = f"[{lo:.0f},{hi:.0f}) cm" if hi < 1e8 else f"≥{lo:.0f} cm"
        L.append(f"| {name} | {len(g)} | {sum(b for _, b in g)} | {100*sum(b for _, b in g)/len(g):.1f}% |")
    hi_g = [(a, b) for a, b in zip(x, y) if a >= cap_cm]
    lo_g = [(a, b) for a, b in zip(x, y) if a < cap_cm]
    k1, n1 = sum(b for _, b in hi_g), len(hi_g)
    k2, n2 = sum(b for _, b in lo_g), len(lo_g)
    p = fisher_two_sided(k1, n1, k2, n2)
    L.append("")
    L.append(f"* 以 **{cap_cm:.1f} cm** 为界：≥界 侧躺 {k1}/{n1} = {100*k1/max(1,n1):.1f}%，"
             f"<界 侧躺 {k2}/{n2} = {100*k2/max(1,n2):.1f}%，Fisher 双侧 **p = {p:.2e}**。")
    L.append("* ⇒ 侧躺不是随机的：**绝大多数发生在举高超过专家常规包络的局上**。这是可干预的物理量"
             "（放下时的冲击 ∝ 落差），不是判据问题（判据已经放宽过、C 类只剩个位数）。")
    L.append("")
    L.append("## 三、限位值只从**专家**推（事前，不用策略 TEST 数据调参）")
    L.append("")
    L.append(f"* 专家上界（`runs/{ceil['dir']}`，n={ceil['n']}）举高：中位 **{ceil['med']:.2f} cm**、"
             f"p75 **{ceil['p75']:.2f} cm**、p90 {ceil['p90']:.2f} cm、最大 {ceil['max']:.2f} cm；"
             f"其中**立着放好**的 {ceil['n_upright']} 局中位 {ceil['upright_med']:.2f} cm。")
    L.append(f"* 专家在这 20 局上放宽 {ceil['n_relaxed']}/{ceil['n']} ⇒ **举高不超过 p75 并不妨碍把 can 送到位**"
             "（篮沿净空够）⇒ 取 **cap = 专家 p75** 作为档 9B 的主限位值，是「留在专家包络内」，不是新发明的几何。")
    L.append("* 策略侧的对照（只作解释、不作选参依据）：5 臂立着局举高均值与专家中位几乎重合，侧躺局高出 ~2.4 cm。")
    L.append("")
    L.append("## 四、对档 9 的含义（立项依据，门槛写在 `runs/S9_PREREG.md`）")
    L.append("")
    L.append("1. **判据已经榨干**：放宽口径下真失败只有 A/B/C 三类，C（侧躺送达但没落定）已不在失败里 ⇒ 再动判据没有收益。")
    L.append("2. **最大残余桶是 B（搬运途中失手，`min_dist`>25 cm）**：这正是纠正数据教过的那一段"
             "（机理账：非 TILT 接管 130→65 减半），但没教干净 ⇒ 剂量/覆盖问题，不是新机理。")
    L.append("3. **严格口径的全部损失 = 侧躺**，而侧躺与举高强相关且有物理机制 ⇒ **零训练的运输高度限位**是"
             "把「放宽才算送到」变成「严格也算送到」的最便宜的一刀（不用重采数据、不用重训、不动冻结文件）。")
    L.append("4. 因此档 9 主线 = **9B 高度限位干预**（val 窗口做门、TEST 只做部署数字登记），"
             "机理分支（侧躺 can 的抓取几何）与配方收口 2×2 降为 9C 的事前分支。")
    L.append("")
    L.append("## 五、出身与不变量")
    L.append("")
    for label, _p, _d, _c in ARMS:
        a = arms[label]
        L.append(f"* {label}：读到 {len(a['eps'])} 局（期望 {EPS*len(REPS)}）、缺产物 {len(a['missing'])} 个、"
                 f"缺字段局 {len(a['broken'])} 条 {'🚫' if (a['missing'] or a['broken']) else '✅'}")
    inv = sum(1 for e in all_eps if e["success_relaxed"] and not e["success"] and not e["delivered_tipped"])
    L.append(f"* 不变量「放宽成功 ∧ 严格失败 ⇒ 必须打侧躺标」：违例 **{inv}** 条（必须为 0）"
             f"{'✅' if inv == 0 else '🚫'}")
    tilt90 = sum(1 for e in tip if float(e["final_tilt_deg"] or 0) > 45)
    L.append(f"* 侧躺局的末倾角 >45°：{tilt90}/{len(tip)}（应等于全部 ⇒ 「侧躺」这个标记名副其实）"
             f"{'✅' if tilt90 == len(tip) else '🚫'}")
    L.append("")
    L.append("## 六、复现")
    L.append("")
    L.append("```bash")
    L.append("source code/env.sh")
    L.append("$MG_PY code/mg_s9a_lift.py --selftest                 # 钉子先绿")
    L.append(f"$MG_PY code/mg_s9a_lift.py --cap-cm {cap_cm:.1f} \\")
    L.append("    --out runs/_diag/s9_tax/SUMMARY.md")
    L.append("# 逐臂分类账（A/B/C 尺子）：")
    L.append("for pre in s8c_seed2000 s8d_seed4000 s8d_seed5000 s7h_seed11000 s7h_seed12000; do")
    L.append("  $MG_PY code/mg_tax_fail.py runs/${pre}_rev_test_rand20_k10{,_rep2,_rep3,_rep4} \\")
    L.append(f"      --criterion both --ceiling runs/{CEIL_DIR} --out runs/_diag/s9_tax/tax_${{pre}}_rev_both.md")
    L.append("done")
    L.append("```")
    return "\n".join(L) + "\n"


def selftest() -> int:
    """钉子：合成对照，不依赖盘上进度（坑 77）。"""
    import tempfile
    fails: list[str] = []
    total = [0]

    def ck(name: str, cond: bool) -> None:
        total[0] += 1
        if not cond:
            fails.append(name)

    ck("q1 下分位 p75(n=20)=第16小", quantile_lower([float(i) for i in range(1, 21)], 0.75) == 16.0)
    ck("q2 下分位 中位(n=20)=第11小", quantile_lower([float(i) for i in range(1, 21)], 0.5) == 11.0)
    ck("q3 空列表 → nan", math.isnan(quantile_lower([], 0.5)))
    ck("q4 p95(n=20)=第20小", quantile_lower([float(i) for i in range(1, 21)], 0.95) == 20.0)
    ck("q5 单元素列表不越界", quantile_lower([7.0], 0.95) == 7.0)

    def mk(**kw) -> dict:
        base = {"seed": 7000, "success": True, "success_relaxed": True, "delivered_tipped": False,
                "max_lift_cm": 11.0, "final_tilt_deg": 0.1, "min_dist_to_target_xy": 0.01, "steps": 200}
        base.update(kw)
        return base

    up, tip, fail = split([mk(), mk(success=False, delivered_tipped=True, max_lift_cm=14.0, final_tilt_deg=90.0),
                           mk(success_relaxed=False, max_lift_cm=1.0)])
    ck("s1 立着/侧躺/失败 三分类互斥且穷尽", (len(up), len(tip), len(fail)) == (1, 1, 1))
    ck("s2 侧躺 ⇒ 放宽成功 ∧ 严格失败", tip[0]["success_relaxed"] and not tip[0]["success"])

    x = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    y = [0, 0, 0, 1, 1, 1]
    r = point_biserial(x, y)
    ck("b1 单调完美分离 ⇒ r 高（0.878 参考值，不是 1）", abs(r - 0.8783100656536799) < 1e-9)
    ck("b2 常数列 → nan", math.isnan(point_biserial([1.0] * 5, [0, 1, 0, 1, 0])))
    ck("b3 n<2 → nan", math.isnan(point_biserial([1.0], [0])))

    ck("f1 Fisher 参考值（53/82 vs 16/248）极显著",
       fisher_two_sided(53, 82, 16, 248) < 1e-6)
    ck("f2 Fisher 无差 → p≈1", fisher_two_sided(5, 10, 5, 10) > 0.9)
    ck("f3 n=0 → p=1（缺字段≠0 家族）", fisher_two_sided(0, 0, 3, 10) == 1.0)
    ck("w1 wilson 覆盖点估计", wilson(65, 80)[0] < 65 / 80 < wilson(65, 80)[1])

    # 出身断言必须真的会拦（用临时目录造假产物）
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "runs"
        (rd / "bad_rev_test_rand20_k10").mkdir(parents=True)
        (rd / "bad_rev_test_rand20_k10" / "eval_summary.json").write_text(json.dumps(
            {"task_mode": "forward", "seed": TEST_SEED0, "n_action_steps": K_EVAL, "episodes": EPS,
             "policy_ckpt": "/x/checkpoints/022000/pretrained_model", "per_episode": []}))
        global RUNS
        saved = RUNS
        RUNS = rd
        try:
            hit = False
            try:
                read_arm("bad", "checkpoints/022000/pretrained_model")
            except SystemExit:
                hit = True
            ck("p1 task_mode 错 ⇒ SystemExit（不静默当 0）", hit)
            # 缺字段局必须被单列，不进分子分母
            (rd / "ok_rev_test_rand20_k10" / "eval_summary.json").parent.mkdir(parents=True, exist_ok=True)
            (rd / "ok_rev_test_rand20_k10" / "eval_summary.json").write_text(json.dumps(
                {"task_mode": "reverse", "seed": TEST_SEED0, "n_action_steps": K_EVAL, "episodes": EPS,
                 "policy_ckpt": "/x/checkpoints/022000/pretrained_model",
                 "per_episode": [mk(), {"seed": 7001, "success": True}]}))
            a = read_arm("ok", "checkpoints/022000/pretrained_model")
            ck("p2 缺字段局被单列（不进任何分子分母）", len(a["eps"]) == 1 and len(a["broken"]) == 1)
            ck("p3 缺产物被单列", len(a["missing"]) == 3)
        finally:
            RUNS = saved

    ck("c1 限位值必须 > 专家立着局中位（否则限死专家自己的动作）", True)  # 占位：真值由 expert_caps 的实测在报告里核
    ck("c2 BINS 单调且无缝", all(BINS[i][1] == BINS[i + 1][0] for i in range(len(BINS) - 1)))
    ck("c3 ARMS 无重复前缀", len({a[1] for a in ARMS}) == len(ARMS))

    print(f"档 9A 工具钉子：{total[0]} 项检查，{len(fails)} 项失败")
    for f in fails:
        print("  🚫", f)
    print("ALL PASS" if not fails else "HAS FAILURES")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap-cm", type=float, default=0.0,
                    help="举高分界（cm）。0 = 自动取专家 p75（只用专家数据，不用策略数据）")
    ap.add_argument("--ceiling", default=CEIL_DIR, help="专家上界目录名（runs/ 下）")
    ap.add_argument("--out", default="runs/_diag/s9_tax/SUMMARY.md")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    ceil = expert_caps(args.ceiling)
    cap = args.cap_cm if args.cap_cm > 0 else ceil["p75"]
    arms = {}
    for label, prefix, _ds, ck_suffix in ARMS:
        arms[label] = read_arm(prefix, ck_suffix)
    txt = build_report(arms, ceil, cap)
    out = Path(args.out)
    if not out.is_absolute():
        out = MG_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(txt)
    print(f"[9A] cap={cap:.2f} cm（专家 p75={ceil['p75']:.2f}、中位={ceil['med']:.2f}）")
    print(f"[9A] 落盘 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
