#!/usr/bin/env python
"""最小抓取链路 · 失败分类账（只读已落盘的 eval_summary，不碰 GPU、不重建 env）。

为什么单独有这个工具，而不是每次现写一段 python：
  档 2 反向 FAIL 之后，「到底是没抓起、没送到、还是送到了没落定」这个问题被反复问了三次
  （last 检查点一次、011000 一次、逐 seed 对上界一次）。每次都是临时脚本，口径还不完全一样
  —— 而口径一变，结论就会变（min_dist 的阈值取 10 cm 还是 25 cm，A/B/C 三类的占比差一倍）。
  这里把口径钉死一次，之后所有档都用同一份分类账，数字可以跨档比。

三类互斥（按 can 的真实运动学结果分，不看夹爪宽度 —— 宽度在 reset 时就是 0.0417 的「半合」，
和「夹住 can」的 0.042~0.050 分不开，用宽度分类会把成功局判成空合爪）：
  A 没抓起   max_lift <  LIFT_OK_CM        （can 基本没离开初始高度）
  B 没送到   max_lift >= LIFT_OK_CM ∧ min_dist > NEAR_CM   （抓起来了但没搬到目标附近）
  C 没落定   max_lift >= LIFT_OK_CM ∧ min_dist <= NEAR_CM  （送到了目标附近却没判成功）
     ↳ C 类的典型机理：**侧躺**。严格判据要求 can「立着」静止并保持 10 步；
       专家上界的 6 局失败**全部**是 final_tilt≈90°（min_dist 只有 0.3~0.5 cm）——
       即送到位置对了、放下时翻了。策略若把 can 举得比专家高再放下，就会掉进同一类。

**双口径**（2026-10-02 用户授权放宽后加的，`--criterion`）：
  strict  = `success`（历史口径，语义自 2026-09-30 起未变，默认值）
  relaxed = `success_relaxed`（主口径：送到 ±9 cm 框 ∧ 落定 ∧ 保持 10 步，**不要求立着**）
  both    = 两套分类账并排 + 一张**交叉表**（谁从失败变成成功、原来属于哪一类）
  ⚠️ 坑 40③「缺字段 ≠ 0」：改判据**之前**落盘的产物没有 `success_relaxed`，
     这些局在放宽口径下**取消资格并逐条报出来**，绝不当 0 计入（当 0 会把结论系统性压向失败）。
  ⚠️ 放宽口径下 C 类会**塌掉**（送到了却侧躺 = 放宽算成功），所以「C 类占多少」这个数
     只在严格口径下有意义；放宽口径下要看的是 A+B（真抓不到 / 真送不到），
     那才是策略能力问题，也是档 5（Harness 接管）/ 档 6（纠正数据）的靶子。

同时报「逐 seed 对上专家上界」：哪些 seed 策略**从来没成过**、其中哪些是专家能成的
（=真差距）、哪些专家自己也成不了（=任务本身的物理天花板，不算策略的账）。
⚠️ 上界必须**同口径**：放宽口径要用 `runs/s2f_ceiling_rev_test20_n05`（严格 14/20 ∧ 放宽 20/20），
   拿旧上界（只有严格字段）配放宽策略读数，会把「专家也做不到」的锅继续扣在策略头上。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_tax_fail.py \
        runs/s2_gate_rev_test_rand20_k10 runs/s2fix_rev_test_rand20_k10 \
        --ceiling runs/s2_ceiling_rev_test20_n05 --out runs/_diag/tax_rev.md'
    # 双口径 + 交叉表：
    $MG_PY code/mg_tax_fail.py runs/s2e_rev_test_rand20_k10{,_rep2,_rep3,_rep4} \
        --criterion both --ceiling runs/s2f_ceiling_rev_test20_n05 --out runs/_diag/tax_s2e_rev_both.md
    $MG_PY code/mg_tax_fail.py --selftest
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent

LIFT_OK_CM = 5.0     # can 抬过这个高度才算「抓起来了」
NEAR_CM = 25.0       # 离目标近到这个程度才算「送到了」（分类账的粗口径，比真判据宽）
TARGET_TOL_CM = 9.0  # = mg_env_reverse.REVERSE_TARGET_TOL_XY(0.09 m) 换算成 cm，**真判据**的方框半宽

CRIT_FIELD = {"strict": "success", "relaxed": "success_relaxed"}
CRIT_NAME = {"strict": "严格（历史口径：要求 can 立着）",
             "relaxed": "**放宽 R**（主口径：送到即算，侧躺另打标）"}


def _norm(e: dict, src: str = "") -> dict:
    """把一局读数归一成分类账要用的形状（单位统一、加 src）。

    ⚠️ 上界产物用 `min_dist_to_target_cm`（厘米），评测产物用 `min_dist_to_target_xy`（**米**）
       —— 这两个字段差 100 倍，混用会把 B/C 分界整个搞错，所以换算只在这里做一次。
    """
    e = dict(e)
    e["src"] = src
    if "min_dist_to_target_xy" in e:
        e["min_dist_cm"] = float(e["min_dist_to_target_xy"]) * 100.0
    elif "min_dist_to_target_cm" in e:
        e["min_dist_cm"] = float(e["min_dist_to_target_cm"])
    else:
        e["min_dist_cm"] = float("nan")
    e["lift_cm"] = float(e.get("max_lift_cm", float("nan")))
    return e


def load_eps(d: Path) -> list[dict]:
    f = d / "eval_summary.json"
    if not f.exists():
        return []
    j = json.loads(f.read_text())
    return [_norm(e, d.name) for e in j.get("per_episode", [])]


def load_ceiling(d: Path) -> list[dict]:
    f = d / "ceiling_summary.json"
    if not f.exists():
        return []
    j = json.loads(f.read_text())
    return [_norm(e, d.name) for e in j.get("per_episode", [])]


def succ_of(e: dict, crit: str):
    """这一局在 `crit` 口径下成不成。缺字段返回 **None**（= 无从判定，不当 False）。"""
    f = CRIT_FIELD[crit]
    if f not in e or e[f] is None:
        return None
    return bool(e[f])


def klass(e: dict, crit: str = "strict") -> str:
    s = succ_of(e, crit)
    if s is None:
        return "UNK"          # 坑 40③：缺字段 ≠ 失败，单独一类，不进任何分母
    if s:
        return "OK"
    if not (e["lift_cm"] >= LIFT_OK_CM):
        return "A"
    return "C" if e["min_dist_cm"] <= NEAR_CM else "B"


def stat(xs: list[float]) -> str:
    if not xs:
        return "-"
    return f"n={len(xs)} 均值 {sum(xs)/len(xs):.1f} 中位 {sorted(xs)[len(xs)//2]:.1f} 范围 [{min(xs):.1f},{max(xs):.1f}]"


def build_report(eps: list[dict], crit: str, args, used: list[str], heading_prefix: str = "") -> list[str]:
    """一套分类账（单一口径）。`heading_prefix` 用来在 both 模式下区分两节。"""
    lines: list[str] = []
    P = lines.append
    known = [e for e in eps if succ_of(e, crit) is not None]
    unknown = [e for e in eps if succ_of(e, crit) is None]

    if heading_prefix:
        P(f"# {heading_prefix}失败分类账  {args.tag or ''}".rstrip())
    else:
        P(f"# 失败分类账  {args.tag or ''}".rstrip())
    P(f"<!-- 由 code/mg_tax_fail.py 生成于 {datetime.now():%F %H:%M}；口径 LIFT_OK={LIFT_OK_CM} cm / NEAR={NEAR_CM} cm -->")
    P("")
    P(f"* 成功判据：{CRIT_NAME[crit]}（字段 `{CRIT_FIELD[crit]}`）")
    P(f"* 读数来源：{', '.join(used)}")
    nsucc = sum(1 for e in known if succ_of(e, crit))
    P(f"* 总样本：**{len(known)} 局**，成功 {nsucc}"
      f" = {nsucc/len(known)*100:.1f}%" if known else "* 总样本：**0 局**")
    if unknown:
        srcs = sorted({e["src"] for e in unknown})
        P(f"* 🚫 **{len(unknown)} 局在{crit}口径下无从判定**（产物缺 `{CRIT_FIELD[crit]}` 字段）⇒ "
          f"**取消资格、不当 0 计入**（坑 40③）。出处：{', '.join(srcs)}")
        P("  这批局是判据放宽**之前**跑的；要纳入放宽口径必须重跑评测，不许回填。")
    if not known:
        P("")
        P("## 一、三类失败（占**失败局**的比例）")
        P("")
        P("* 🚫 没有任何一局带这个口径的字段 ⇒ 本节全悬空，下面不作数。")
        return lines

    buckets: dict[str, list[dict]] = {}
    for e in known:
        buckets.setdefault(klass(e, crit), []).append(e)
    nfail = sum(len(v) for k, v in buckets.items() if k != "OK")
    P("")
    P("## 一、三类失败（占**失败局**的比例）")
    P("")
    P("| 类 | 含义 | 局数 | 占失败 | max_lift_cm | min_dist_cm |")
    P("| --- | --- | --- | --- | --- | --- |")
    names = {"A": "没抓起（can 基本没离地）", "B": "抓起了但没送到目标附近",
             "C": "送到了目标附近却没判成功"}
    for k in ("A", "B", "C"):
        v = buckets.get(k, [])
        pc = f"{len(v)/nfail*100:.0f}%" if nfail else "-"
        P(f"| {k} | {names[k]} | {len(v)} | {pc} | {stat([e['lift_cm'] for e in v])} "
          f"| {stat([e['min_dist_cm'] for e in v])} |")
    ok = buckets.get("OK", [])
    P(f"| OK | 成功 | {len(ok)} | - | {stat([e['lift_cm'] for e in ok])} "
      f"| {stat([e['min_dist_cm'] for e in ok])} |")

    # C 类的举高对照：成功局 vs C 类失败局，谁把 can 举得更高？
    if buckets.get("C") and ok:
        hc = sum(e["lift_cm"] for e in buckets["C"]) / len(buckets["C"])
        ho = sum(e["lift_cm"] for e in ok) / len(ok)
        P("")
        P(f"* C 类平均举高 **{hc:.1f} cm** vs 成功局 **{ho:.1f} cm**（差 {hc-ho:+.1f} cm）。"
          "举得越高，放下时的冲击越大 ⇒ 越容易侧躺（严格判据要求 can「立着」保持 10 步）。")
    if crit == "relaxed":
        P("")
        P(f"* ⚠️ 放宽口径下 C 类**必然塌掉**（送到了却侧躺 = 放宽算成功，且 `delivered_tipped` 另打标）⇒ "
          f"本节要看的是 **A+B = {len(buckets.get('A', [])) + len(buckets.get('B', []))} 局"
          f"（占失败 {(len(buckets.get('A', [])) + len(buckets.get('B', [])))/nfail*100:.0f}%）**"
          if nfail else "* ⚠️ 放宽口径下无失败局。")
        P("  A+B 是**真抓不到 / 真送不到**，不是判据问题 ⇒ 这才是档 5（Harness 接管）/ 档 6（纠正数据）的靶子。")
        tipped = [e for e in ok if e.get("delivered_tipped")]
        if tipped:
            P(f"* 成功局里带**侧躺标记**的有 {len(tipped)} 局（`delivered_tipped`）⇒ 送到了但没摆正，"
              f"占成功 {len(tipped)/len(ok)*100:.0f}%；它们的 final_tilt："
              f"{[round(e.get('final_tilt_deg', float('nan'))) for e in tipped]}")

    # ── 「放宽判据能不能救回来」的上界 ────────────────────────────────────
    # 为什么必须算这一条：反向的严格判据是「can 在 ±9 cm 方框内 ∧ 落定 ∧ 立着 ∧ 保持 10 步」，
    # 而**专家自己**严格口径也只有 70%（6 局失败全是侧躺）。所以「判据太严」是一个非常诱人、
    # 而且听起来很合理的甩锅方向。这条把它的**上界**一次算死。
    # ⚠️ 注意这一级（曾进框）比用户的放宽口径**还要松**：它连「松手+静止+保持 10 步」都不要求，
    #    所以它是天花板、不是结论；用户口径的正式读数是 `success_relaxed`（本节第一行已给）。
    near = [e for e in known if not succ_of(e, crit) and e["min_dist_cm"] <= args.target_tol_cm]
    ub = (nsucc + len(near)) / len(known)
    P("")
    P(f"## 二、把判据再放宽到「can 曾进过 ±{args.target_tol_cm:.0f} cm 方框就算成功」的上界（**仅诊断，不是成功口径**）")
    P("")
    P(f"* 本口径成功 {nsucc} 局 + 进过方框却没成的 {len(near)} 局 = **{nsucc + len(near)}/{len(known)}"
      f" = {ub*100:.1f}%**（这是「曾进框」这一级能拿到的**天花板**）")
    P(f"* 门是 50% ⇒ 这一级**{'仍然过不了门' if ub < 0.50 else '就能过门'}**。"
      + ("别往这个方向走：判据不是瓶颈。" if ub < 0.50 else
         "⇒ 判据确实是瓶颈（这条推断已由档 2f 的 `success_relaxed` 正式口径证实/证伪，见 `runs/S2F_RELAX_VERDICT.md`）。"))
    if near:
        lifts = [e["lift_cm"] for e in near]
        P(f"* 这 {len(near)} 局的 max_lift：均值 {sum(lifts)/len(lifts):.1f} cm，"
          f"范围 [{min(lifts):.1f},{max(lifts):.1f}] cm；成功局均值 "
          f"{sum(e['lift_cm'] for e in ok)/len(ok):.1f} cm" if ok else "")
        P("* 逐局（min_dist / max_lift / steps）：")
        for e in sorted(near, key=lambda x: x["min_dist_cm"]):
            P(f"  * {e['min_dist_cm']:.1f} cm / {e['lift_cm']:.1f} cm / {e['steps']} 步")

    # 逐 seed 对上专家上界
    if args.ceiling:
        cpath = Path(args.ceiling)
        if not cpath.is_absolute():
            cpath = MG_ROOT / cpath
        cs = cpath / "ceiling_summary.json"
        if cs.exists():
            cj = json.loads(cs.read_text())
            ceil = {e["seed"]: e for e in load_ceiling(cpath)}
            cfield = CRIT_FIELD[crit]
            ceil_has = any(cfield in e for e in ceil.values())
            byseed: dict[int, list[dict]] = {}
            for e in known:
                if "seed" in e:
                    byseed.setdefault(int(e["seed"]), []).append(e)
            P("")
            if ceil_has:
                cn = sum(1 for e in ceil.values() if succ_of(e, crit))
                P(f"## 三、逐 seed 对专家上界（{cj.get('task_mode','?')} noise={cj.get('noise_sigma','?')}，"
                  f"**同口径**专家 {cn}/{cj.get('episodes')}）")
            else:
                P(f"## 三、逐 seed 对专家上界（{cj.get('task_mode','?')} noise={cj.get('noise_sigma','?')}，"
                  f"专家 {cj.get('n_success')}/{cj.get('episodes')}）")
                P("")
                P(f"* 🚫 上界产物里没有 `{cfield}` 字段 ⇒ **上界与策略不同口径**，本节只在严格口径下可比。"
                  "放宽口径请改用 `runs/s2f_ceiling_rev_test20_n05`（严格 14/20 ∧ 放宽 20/20）。")
            P("")
            P("| seed | 专家 | 专家 tilt° | 策略 | 策略失败类别 |")
            P("| --- | --- | --- | --- | --- |")
            for s in sorted(byseed):
                v = byseed[s]
                n_s = sum(1 for e in v if succ_of(e, crit))
                c = ceil.get(s)
                if c is None:
                    cflag = "-"
                elif not ceil_has:
                    cflag = "✅" if c["success"] else "❌"
                else:
                    cs_ = succ_of(c, crit)
                    cflag = "-" if cs_ is None else ("✅" if cs_ else "❌")
                tilt = "-" if c is None else f"{c.get('final_tilt_deg', float('nan')):.0f}"
                ks = "".join(sorted({klass(e, crit) for e in v if not succ_of(e, crit)})) or "-"
                P(f"| {s} | {cflag} | {tilt} | {n_s}/{len(v)} | {ks} |")
            never = [s for s, v in byseed.items() if not any(succ_of(e, crit) for e in v)]
            exp_ok = {s for s, e in ceil.items()
                      if (succ_of(e, crit) if ceil_has else e["success"])}
            P("")
            P(f"* 策略**从未**成功过的 seed：{len(never)}/{len(byseed)} ⇒ {sorted(never)}")
            if ceil_has:
                P(f"  * 其中专家（**同口径**）也失败：{sorted(set(never) - exp_ok)}")
                P(f"  * 其中专家能成（=**真差距**）：{sorted(set(never) & exp_ok)}")
            else:
                P(f"  * 其中专家也失败（物理天花板，不算策略的账）：{sorted(set(never) - exp_ok)}")
                P(f"  * 其中专家能成（=**真差距**）：{sorted(set(never) & exp_ok)}")
            P(f"* 至少成功过一次的 seed：{len(byseed) - len(never)}/{len(byseed)}"
              " ⇒ 剩下的失败主要是**执行抖动**，不是位姿覆盖不到。")
            if ceil:
                exp_fail_tilt = [e.get("final_tilt_deg") for e in ceil.values()
                                 if not e["success"] and e.get("final_tilt_deg") is not None]
                if exp_fail_tilt:
                    P(f"* 专家**严格口径**失败局的 final_tilt：{[round(t) for t in exp_fail_tilt]}"
                      " ⇒ 专家的失败全是侧躺（送到了、放下翻了），这就是严格上界 70% 的由来；"
                      "放宽口径下这 6 局算送到 ⇒ 上界 100%。")
        else:
            P("")
            P(f"* ⚠️ 没找到上界产物 {cs} ⇒ 跳过逐 seed 对账")
    return lines


def cross_tab(eps: list[dict]) -> list[str]:
    """两口径都有的那批局：谁从严格失败变成放宽成功、原来属于哪一类。"""
    both = [e for e in eps if succ_of(e, "strict") is not None and succ_of(e, "relaxed") is not None]
    lines = ["", "## 四、两口径交叉表（只统计**两字段都有**的 %d 局）" % len(both), ""]
    if not both:
        lines.append("* 🚫 没有一局同时带两个口径的字段 ⇒ 交叉表悬空（**不当 0 计入**，坑 40③）。")
        return lines
    cells: dict[tuple[str, str], int] = {}
    for e in both:
        cells[(klass(e, "strict"), klass(e, "relaxed"))] = \
            cells.get((klass(e, "strict"), klass(e, "relaxed")), 0) + 1
    lines += ["| 严格口径类 ↓ / 放宽口径类 → | OK | A | B | C | 行合计 |",
              "| --- | --- | --- | --- | --- | --- |"]
    for a in ("OK", "A", "B", "C"):
        row = [cells.get((a, b), 0) for b in ("OK", "A", "B", "C")]
        lines.append("| %s | %d | %d | %d | %d | %d |" % (a, *row, sum(row)))
    col = [sum(cells.get((a, b), 0) for a in ("OK", "A", "B", "C")) for b in ("OK", "A", "B", "C")]
    lines.append("| 列合计 | %d | %d | %d | %d | %d |" % (*col, len(both)))
    moved = sum(v for (a, b), v in cells.items() if a != "OK" and b == "OK")
    viol = sum(v for (a, b), v in cells.items() if a == "OK" and b != "OK")
    lines += ["",
              "* 严格失败 → 放宽成功：**%d 局**（= `delivered_tipped` 的量级）；其中原属 C 类 %d 局、B 类 %d 局、A 类 %d 局"
              % (moved, cells.get(("C", "OK"), 0), cells.get(("B", "OK"), 0), cells.get(("A", "OK"), 0)),
              "* 🚫 不变量检查：严格成功 → 放宽失败 = **%d 局**，必须为 0（严格 ⊆ 放宽，"
              "由 `code/mg_criterion_selftest.py` 钉住）%s" % (viol, "" if viol == 0 else " ⇒ **判据实现有 bug，本表作废**"),
              "* 两口径都失败：%d 局 ⇒ 这批是**真能力缺口**，与判据无关，是档 5/档 6 的靶子"
              % sum(v for (a, b), v in cells.items() if a != "OK" and b != "OK")]
    return lines


def main() -> int:
    # `global` 必须写在函数最前面：argparse 的 default= 会先读这两个全局名，
    # 之后再声明 global 就是 SyntaxError（"used prior to global declaration"），实测踩过。
    global LIFT_OK_CM, NEAR_CM
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*", help="评测产物目录（含 eval_summary.json）")
    ap.add_argument("--ceiling", default="", help="专家上界目录（含 ceiling_summary.json），用来逐 seed 对账")
    ap.add_argument("--tag", default="", help="写进标题的标签")
    ap.add_argument("--criterion", choices=("strict", "relaxed", "both"), default="strict",
                    help="按哪个成功口径分类（默认 strict = 历史口径，输出与旧版一致）")
    ap.add_argument("--lift-cm", type=float, default=LIFT_OK_CM, help="A/B 分界：can 抬过多少算「抓起来了」")
    ap.add_argument("--near-cm", type=float, default=NEAR_CM, help="B/C 分界：离目标多近算「送到了」")
    ap.add_argument("--target-tol-cm", type=float, default=TARGET_TOL_CM,
                    help="真判据的方框半宽（反向 = REVERSE_TARGET_TOL_XY = 9 cm），用来算「曾进框」的诊断天花板")
    ap.add_argument("--out", default="", help="落盘 markdown 路径（相对路径按 $MG_ROOT 解析）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.runs:
        ap.error("至少给一个评测产物目录（除非 --selftest）")

    LIFT_OK_CM, NEAR_CM = args.lift_cm, args.near_cm

    eps: list[dict] = []
    used = []
    for r in args.runs:
        d = Path(r)
        if not d.is_absolute():
            d = MG_ROOT / d
        got = load_eps(d)
        if got:
            used.append(f"{d.name}（{len(got)} 局）")
            eps += got
    if not eps:
        print("[tax] FATAL 没有任何可读产物")
        return 3

    if args.criterion == "both":
        lines = build_report(eps, "strict", args, used, "【严格口径】")
        lines += ["", "---", ""]
        lines += build_report(eps, "relaxed", args, used, "【放宽口径】")
        lines += cross_tab(eps)
    else:
        lines = build_report(eps, args.criterion, args, used)

    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        o = Path(args.out)
        if not o.is_absolute():
            o = MG_ROOT / o
        o.parent.mkdir(parents=True, exist_ok=True)
        o.write_text(text)
        print(f"[tax] 落盘 -> {o}")
    return 0


# ── 自测：钉住分类边界、缺字段处理、交叉表不变量 ─────────────────────────────
def selftest() -> int:
    import tempfile

    fails: list[str] = []
    n = 0

    def chk(cond, msg):
        nonlocal n
        n += 1
        if not cond:
            fails.append(msg)

    def ep(success, lift, dist, **kw):
        """造一局读数，**走与 load_eps 完全相同的归一路径**（免得自测绕开单位换算）。"""
        d = {"success": success, "max_lift_cm": lift,
             "min_dist_to_target_xy": dist / 100.0, "steps": 400, "seed": kw.pop("seed", 7000)}
        d.update(kw)
        return _norm(d, "selftest")

    # --- klass() 的三条边界（严格口径）-------------------------------------
    chk(klass(ep(False, 4.9, 60.0)) == "A", "lift 4.9 < 5.0 ⇒ A")
    chk(klass(ep(False, 5.0, 60.0)) == "B", "lift 5.0 恰好 >= 5.0 且远 ⇒ B")
    chk(klass(ep(False, 12.0, 25.0)) == "C", "lift 够 ∧ dist 25.0 恰好 <= 25.0 ⇒ C")
    chk(klass(ep(False, 12.0, 25.1)) == "B", "dist 25.1 > 25.0 ⇒ B")
    chk(klass(ep(True, 12.0, 1.0)) == "OK", "成功局必须 OK（不看几何）")
    chk(klass(ep(True, 0.1, 99.0)) == "OK", "成功局即使几何怪也判 OK")

    # --- 缺字段：None，不是 False（坑 40③）--------------------------------
    old = ep(True, 12.0, 1.0)                       # 改判据前的产物：没有 success_relaxed
    chk(succ_of(old, "strict") is True, "严格字段在 ⇒ 正常读")
    chk(succ_of(old, "relaxed") is None, "缺放宽字段必须返回 None，不是 False")
    chk(klass(old, "relaxed") == "UNK", "缺字段的局在放宽口径下必须是 UNK，不进 A/B/C")
    chk(succ_of({"success": None, "max_lift_cm": 1, "min_dist_to_target_xy": 1}, "strict") is None,
        "字段值为 null 也算无从判定")

    # --- 放宽口径下 C 类塌掉、侧躺标记局算成功 ------------------------------
    tipped = ep(False, 15.4, 0.5, success_relaxed=True, delivered_tipped=True, final_tilt_deg=90.0)
    chk(klass(tipped, "strict") == "C", "侧躺局严格口径 = C 类")
    chk(klass(tipped, "relaxed") == "OK", "同一局放宽口径 = 成功")
    nogrip = ep(False, 0.6, 63.0, success_relaxed=False, delivered_tipped=False)
    chk(klass(nogrip, "strict") == "A" and klass(nogrip, "relaxed") == "A",
        "真抓不到的局两口径都必须是 A（放宽不会把它救回来）")

    # --- cross_tab：不变量 + 计数 ------------------------------------------
    set_ok = [ep(True, 12.0, 1.0, success_relaxed=True),
              tipped,
              nogrip,
              ep(False, 12.0, 40.0, success_relaxed=False),      # B 两口径都失败
              ep(True, 12.0, 1.0)]                                # 缺放宽字段 ⇒ 不进交叉表
    ct = cross_tab(set_ok)
    txt = "\n".join(ct)
    chk("只统计**两字段都有**的 4 局" in txt, "交叉表必须排除缺字段的局，实得：%s" % ct[1])
    chk("严格失败 → 放宽成功：**1 局**" in txt, "应有 1 局从 C 变成 OK")
    chk("其中原属 C 类 1 局、B 类 0 局、A 类 0 局" in txt, "那 1 局应记在 C 类名下")
    chk("严格成功 → 放宽失败 = **0 局**" in txt, "不变量：严格 ⊆ 放宽")
    chk("两口径都失败：2 局" in txt, "A + B 各 1 局 ⇒ 真能力缺口 2 局")
    bad = [ep(True, 12.0, 1.0, success_relaxed=False)]            # 人为破坏不变量
    chk("本表作废" in "\n".join(cross_tab(bad)), "严格成功而放宽失败 ⇒ 必须报「判据实现有 bug」")
    chk("交叉表悬空" in "\n".join(cross_tab([ep(True, 12.0, 1.0)])),
        "全是缺字段的局 ⇒ 交叉表要悬空而不是崩")

    # --- build_report：缺字段要报出来、且不当 0 计入分母 --------------------
    class A:                                  # 顶替 argparse.Namespace
        tag = "自测"; ceiling = ""; target_tol_cm = 9.0; lift_cm = 5.0; near_cm = 25.0
    rep = build_report([ep(True, 12.0, 1.0, success_relaxed=True),
                        ep(False, 0.6, 63.0, success_relaxed=False),
                        ep(False, 0.6, 63.0)],                      # 缺放宽字段
                       "relaxed", A(), ["fake（3 局）"])
    t = "\n".join(rep)
    chk("**2 局**" in t and "成功 1" in t, "缺字段的局不许进分母：应报总样本 2 局、成功 1，实得 %r" % t[:400])
    chk("无从判定" in t and "不当 0 计入" in t, "必须显式报出缺字段的局数与出处")
    chk("fake" in t, "缺字段的出处目录要报出来")
    rep_s = build_report([ep(True, 12.0, 1.0, success_relaxed=True),
                          ep(False, 0.6, 63.0, success_relaxed=False),
                          ep(False, 0.6, 63.0)], "strict", A(), ["fake（3 局）"])
    chk("**3 局**" in "\n".join(rep_s), "严格口径下三局都有字段 ⇒ 分母应是 3")

    # 全缺字段的极端情形：不许崩，要悬空
    rep_u = build_report([ep(True, 12.0, 1.0), ep(False, 0.6, 63.0)], "relaxed", A(), ["old（2 局）"])
    chk("本节全悬空" in "\n".join(rep_u), "一个字段都没有时要报悬空，实得 %r" % "\n".join(rep_u)[:200])

    # --- 端到端：真产物（只读）+ 与旧版口径的一致性 ------------------------
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "e1").mkdir()
        (root / "e1" / "eval_summary.json").write_text(json.dumps({"per_episode": [
            ep(True, 12.0, 1.0, seed=7000, success_relaxed=True, success_step=250),
            ep(False, 15.4, 0.5, seed=7001, success_relaxed=True, delivered_tipped=True,
               final_tilt_deg=90.0),
            ep(False, 0.6, 63.0, seed=7002, success_relaxed=False),
            ep(False, 13.0, 40.0, seed=7003, success_relaxed=False),
        ]}))
        got = load_eps(root / "e1")
        chk(len(got) == 4, "load_eps 应读出 4 局")
        chk(abs(got[0]["min_dist_cm"] - 1.0) < 1e-9, "米→厘米换算应对（1.0 cm）")
        chk(sum(1 for e in got if klass(e, "strict") == "OK") == 1, "严格成功 1 局")
        chk(sum(1 for e in got if klass(e, "relaxed") == "OK") == 2, "放宽成功 2 局")
        chk([klass(e, "relaxed") for e in got] == ["OK", "OK", "A", "B"],
            "放宽口径四类应分别是 OK/OK/A/B，实得 %r" % [klass(e, "relaxed") for e in got])
        # min_dist 字段名兼容（上界产物用 _cm）
        (root / "c1").mkdir()
        (root / "c1" / "ceiling_summary.json").write_text(json.dumps({"per_episode": [
            {"seed": 7000, "success": True, "success_relaxed": True, "final_tilt_deg": 0.0,
             "min_dist_to_target_cm": 0.3, "max_lift_cm": 2.0, "steps": 229}]}))
        ce = load_ceiling(root / "c1")
        chk(len(ce) == 1 and abs(ce[0]["min_dist_cm"] - 0.3) < 1e-9, "上界产物的 _cm 字段要直接吃")

    print("分类账工具钉子：%d 项检查，%d 项失败" % (n, len(fails)))
    for f in fails[:20]:
        print("  FAIL " + f)
    if fails:
        print("SELFTEST FAIL")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
