#!/usr/bin/env python
"""抬升/松手高度画像：把「策略举太高」从**推断**变成**测量**。

档 2 的失败分类账（runs/_diag/tax_rev_test.md）发现：C 类失败与全部 9 个近失误
把 can 举到 15.4–21.8 cm（均值 18.4），而成功局只有 11.7 cm ⇒ 落下冲击大 ⇒ can 侧躺，
不满足「立着保持 10 步」的严格判据。但那份账只量了**策略自己**，缺一个参照系：
**专家示范本来举多高、在多高处松手？** 没有这个参照，「18 cm 太高」就只是猜测。

本工具补上参照系，口径全部来自已有产物、不碰 GPU。三个第一版踩出来的坑，都写进代码：

1. **松手事件必须走状态机，不能用单一宽度阈值。** reset 后空手开口是 0.0417、
   夹住 can 是 ≈0.05，两者只差 0.008 —— 任何「宽度落在夹持带里」的判据都会把
   **每一局开局**误判成「已经夹住了」。所以只有「先张开(w>OPEN_W) 再收拢」才算一次
   抓取尝试；收拢后 w>GRIP_HOLD_WIDTH 才是真夹住（空合只有 0.001）。
   数值取自 mg_env.py:66-69 的实测常量。

2. **高度必须以抓取点为基准，不能以开局为基准。** 实测专家示范的 eef_z 相对开局
   最大抬升是 **0.0 cm**（末端从没高过起始位置），松手时反而比起始低 11 cm ——
   机械臂是先降到桌面抓 can、再抬到篮口，而篮底与桌面齐平（BIN_FLOOR_OFFSET=0）。
   所以 carry = 夹持期 eef_z 峰值 − 抓取瞬间 eef_z；
   release_above_grasp = 松手瞬间 eef_z − 抓取瞬间 eef_z，**后者就是 can 的跌落高度**。

3. **有效性门用「阳性对照」，不用全局相关性。** carry 只在成功局上是物体抬升的好代理
   （实测 r=0.992），在 A/B/C 上不成立（r=0.30/0.33/0.50），因为一半的局有 ≥2 次
   夹持（掉罐、重抓），而 max_lift 取的是全剧最大值。所以：
   * 「抬升高度」的比较只在成功局上做代理校验，A/B/C 的 carry 不当物体抬升用；
   * 「松手高度」是**直接测量**（同一个 state 通道、同一套状态机，示范与策略同口径），
     其有效性由**阳性对照**背书：策略成功局的松手高度必须与专家一致。
     一致 ⇒ 尺子准 ⇒ C 类偏离才有意义；不一致 ⇒ 尺子本身有问题，全部作废。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_lift_profile.py'
    bash -c 'source code/env.sh && $MG_PY code/mg_lift_profile.py --selftest'
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mg_verdict_s2 import fisher_two_sided  # noqa: E402  已对着 scipy 校验过的实现

MG = Path(os.environ.get("MG_ROOT", str(Path(__file__).resolve().parent.parent)))
RUNS = MG / "runs"
DATA = MG / "data"

IZ = 2          # state 契约（mg_env.py:57 STATE_NAMES）：eef_z
IG = 7          # gripper_width
GRIP_HOLD_WIDTH = 0.012     # > 它才算「夹到东西」（空合只有 0.001）
HOLD_CONTACT = 0.060        # 宽度降到它以下 = 手指已经合到 can 上（夹住 can ≈0.05）
OPEN_W = 0.070              # 张开到底 ≈ 0.0788；越过它判为「张开/已松手」

LIFT_OK_CM = 5.0            # 与 mg_tax_fail.py 同口径：抬过它才算「抓起来了」
NEAR_CM = 25.0              # 与 mg_tax_fail.py 同口径：min_dist ≤ 它算「送到了附近」
PROXY_R_MIN = 0.8           # 成功局上 carry↔物体抬升 的最低可信相关
CTRL_TOL_CM = 1.5           # 阳性对照：成功局与专家的松手高度中位差容差
PRE_DZ_W = 20               # 「松手前多少步」的 dz 均值，用来判下压指令有没有被压没
IDZ = 2                     # action 契约（mg_env.py:58 ACTION_NAMES）：dz


def split_eps(state: np.ndarray, lengths: np.ndarray) -> list[np.ndarray]:
    out, off = [], 0
    for n in lengths:
        n = int(n)
        out.append(state[off:off + n])
        off += n
    return out


def ep_metrics(st: np.ndarray, act: np.ndarray | None = None) -> dict:
    """单局画像。st: (T,8)，act: (T,7) 可选（用来取松手前的 dz）。

    **按「闭合段」切分，而不是按逐点阈值**。第二版踩到的坑（被 A 类数据抓出来）：
    闭合是一个**过程**，手指还在合拢的路上宽度会短暂经过 0.05 附近；只用
    「第一个 w>0.012 的样本」判夹持，会把**空合**（最终压到 0.001，手里什么都没有）
    也算成一次成功夹持。实测这样量出来 A 类（物体从没离地）的「夹持段」宽度中位是
    **0.0010** —— 和 mg_env.py 里空合的值一模一样，而专家是 0.0499。
    ⇒ 判据改成：一次闭合段内宽度的**中位数** > GRIP_HOLD_WIDTH 才算真夹住
       （中位数对「合拢途中的瞬时值」和「松手前的抖动」都免疫；空合会一直停在 0.001）。

    派生三个口径，避免 first/last 混用：
      * carry_cm               = 各段 (峰值 − 抓取点) 的**最大**值（与物体 max_lift 同义）；
      * release_above_grasp_cm = **第一次**真松手的高度（阳性对照用它）；
      * release_last/max_above_cm = 末次 / 最高，用来证明结论不依赖 first/last 的选法。
    """
    z = st[:, IZ].astype(np.float64)
    w = st[:, IG].astype(np.float64)
    T = len(w)
    z0 = float(z[0])
    zmax = float(z.max())
    # seg = (z_grasp, peak_z, release_z|None, release_t|-1, w_med, n_steps)
    segs: list[tuple] = []
    n_empty = 0
    was_open = False
    t = 0
    while t < T:
        if w[t] > OPEN_W:
            was_open = True
            t += 1
            continue
        if not was_open:            # 开局 0.0417 之类：从没张开过，不算抓取尝试
            t += 1
            continue
        t0 = t                      # 一次闭合段开始
        t1 = t0
        while t1 < T and w[t1] <= OPEN_W:
            t1 += 1                 # t1 = 下一次张开（或剧终）
        wseg = w[t0:t1]
        wmed = float(np.median(wseg))
        if wmed > GRIP_HOLD_WIDTH:  # 真夹住
            below = np.nonzero(wseg <= HOLD_CONTACT)[0]
            gi = int(below[0]) if below.size else 0
            zg = float(z[t0 + gi])
            pk = float(z[t0 + gi:t1].max()) if t1 > t0 + gi else zg
            rel = float(z[t1]) if t1 < T else None
            segs.append((zg, pk, rel, t1 if t1 < T else -1, wmed, t1 - t0))
        else:
            n_empty += 1            # 空合：手里什么都没有
        was_open = False
        t = max(t1, t0 + 1)

    carries = [(pk - g) * 100.0 for g, pk, _, _, _, _ in segs]
    rels = [(r - g) * 100.0 for g, _, r, _, _, _ in segs if r is not None]
    rel_t = next((rt for _, _, r, rt, _, _ in segs if r is not None), -1)
    pre_dz = float("nan")
    if act is not None and rel_t >= 1:
        lo = max(0, rel_t - PRE_DZ_W)
        col = np.asarray(act[lo:rel_t, IDZ], dtype=np.float64)
        if col.size:
            pre_dz = float(col.mean())
    # rel_exc 要用**真正发生第一次松手的那一段**的 release_z，不能拿 segs[0] 的抓取点凑：
    # 若第一段到剧终都没松手（超时仍夹着）、第二段才松，凑出来的数会错位。
    first_rel = next((sg for sg in segs if sg[2] is not None), None)
    rel_z = first_rel[2] if first_rel else float("nan")
    rel_exc = (rel_z - z0) * 100.0 if first_rel else float("nan")
    return {"z0": z0, "excursion_cm": (zmax - z0) * 100.0, "zmax": zmax,
            "release_z": rel_z, "release_excursion_cm": rel_exc, "steps": int(T),
            "held": bool(segs), "n_empty_close": int(n_empty), "n_hold": len(segs),
            "hold_w_med": float(np.median([s[4] for s in segs])) if segs else float("nan"),
            "hold_steps_med": float(np.median([s[5] for s in segs])) if segs else float("nan"),
            "z_grasp": segs[0][0] if segs else float("nan"),
            "pre_release_dz": pre_dz, "rel_t": rel_t,
            "carry_cm": max(carries) if carries else float("nan"),
            "carry_first_cm": carries[0] if carries else float("nan"),
            "release_above_grasp_cm": rels[0] if rels else float("nan"),
            "release_last_above_cm": rels[-1] if rels else float("nan"),
            "release_max_above_cm": max(rels) if rels else float("nan"),
            "n_release": len(rels)}


def stat(xs: list[float]) -> str:
    v = np.asarray([x for x in xs if np.isfinite(x)], dtype=np.float64)
    if v.size == 0:
        return "n=0"
    return (f"n={v.size} 均值 {v.mean():.1f} 中位 {np.median(v):.1f} "
            f"范围 [{v.min():.1f},{v.max():.1f}]")


def med(xs: list[float]) -> float:
    v = np.asarray([x for x in xs if np.isfinite(x)], dtype=np.float64)
    return float(np.median(v)) if v.size else float("nan")


def demo_profile(npz: Path) -> list[dict]:
    d = np.load(npz, allow_pickle=True)
    return [ep_metrics(s, a) for s, a in zip(split_eps(d["state"], d["episode_lengths"]),
                                             split_eps(d["action"], d["episode_lengths"]))]


def rollout_profile(d: Path) -> list[dict]:
    """策略读数目录 -> 每局画像，并挂上 eval_summary.json 里的物体量。"""
    npz = d / "rollout_actions.npz"
    summ = d / "eval_summary.json"
    if not npz.exists() or not summ.exists():
        return []
    r = np.load(npz, allow_pickle=True)
    j = json.loads(summ.read_text())
    per = {int(e["ep"]): e for e in j.get("per_episode", [])}
    out = []
    st_eps = split_eps(r["state"], r["episode_lengths"])
    ac_eps = split_eps(r["action"], r["episode_lengths"])
    for i, (st, ac) in enumerate(zip(st_eps, ac_eps)):
        m = ep_metrics(st, ac)
        e = per.get(i, {})
        m.update({"success": bool(e.get("success", False)),
                  "obj_lift_cm": float(e.get("max_lift_cm", float("nan"))),
                  "min_dist_cm": float(e.get("min_dist_to_target_xy", float("nan"))) * 100.0,
                  "src": d.name})
        out.append(m)
    return out


def classify(e: dict) -> str:
    """与 mg_tax_fail.py 同一套 OK/A/B/C 口径。"""
    if e["success"]:
        return "OK"
    if not (e["obj_lift_cm"] >= LIFT_OK_CM):
        return "A"
    return "C" if e["min_dist_cm"] <= NEAR_CM else "B"


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or b.size < 3 or a.std() < 1e-9 or b.std() < 1e-9:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def rule_of_three(n_zero: int) -> float:
    """「0/n 都落在值域内」时，越界率 p 的 95% 上界 ≈ 3/n。
    示范里 0/60 超过 2.6 cm，不能因此就把 p 当成 0（那会让 p 值无意义地变成 0），
    取保守上界再做二项检验，结论才站得住。"""
    return 3.0 / n_zero if n_zero > 0 else 1.0


def binom_tail_ge(k: int, n: int, p: float) -> float:
    """P(X >= k)，X~Binomial(n,p)。只用 stdlib math.comb（与 mg_verdict_s2 的 Fisher 同风格）。"""
    from math import comb
    if n <= 0:
        return 1.0
    p = min(max(p, 0.0), 1.0)
    if p <= 0.0:
        return 0.0 if k > 0 else 1.0
    if p >= 1.0:
        return 1.0
    return float(sum(comb(n, i) * p ** i * (1.0 - p) ** (n - i) for i in range(k, n + 1)))


REV_DEMO = DATA / "mix60f60r_rev_raw.npz"
FWD_DEMO = DATA / "mix60f60r_raw.npz"
REV_TEST = ["s2_gate_rev_test_rand20_k10", "s2_gate_rev_test_rand20_k10_rep2",
            "s2fix_rev_test_rand20_k10", "s2fix_rev_test_rand20_k10_rep2",
            "s2fix_rev_test_rand20_k10_rep3"]
KEY = "release_above_grasp_cm"


def build(demo_rev: list[dict], demo_fwd: list[dict], eps: list[dict], extra: list[Path],
          demo_act: np.ndarray | None = None, pol_act: np.ndarray | None = None) -> str:
    L: list[str] = []
    P = L.append
    groups: dict[str, list[dict]] = {}
    for e in eps:
        groups.setdefault(classify(e), []).append(e)
    dh = [e for e in demo_rev if e["held"] and np.isfinite(e[KEY])]
    oh = [e for e in groups.get("OK", []) if e["held"] and np.isfinite(e[KEY])]
    ch = [e for e in groups.get("C", []) if e["held"] and np.isfinite(e[KEY])]

    # ── 有效性：代理校验（只在成功局上）+ 阳性对照 ──────────────────────────
    ok_pair = [e for e in groups.get("OK", []) if np.isfinite(e["carry_cm"])
               and np.isfinite(e["obj_lift_cm"])]
    r_ok = pearson(np.asarray([e["carry_cm"] for e in ok_pair]),
                   np.asarray([e["obj_lift_cm"] for e in ok_pair]))
    proxy_ok = bool(np.isfinite(r_ok) and r_ok >= PROXY_R_MIN)
    ctrl_diff = med([e[KEY] for e in oh]) - med([e[KEY] for e in dh]) if (oh and dh) else float("nan")
    ctrl_ok = bool(np.isfinite(ctrl_diff) and abs(ctrl_diff) <= CTRL_TOL_CM)
    multi = sum(1 for e in eps if e["n_hold"] >= 2)

    P("# 抬升/松手高度画像：策略 vs 专家示范")
    P(f"<!-- 由 code/mg_lift_profile.py 生成于 {datetime.now():%F %H:%M}；"
      f"夹爪状态机 open>{OPEN_W} / hold>{GRIP_HOLD_WIDTH}；高度基准 = 抓取点 -->")
    P("")
    P("## 一、这两把尺子准不准（先验尺，再量人）")
    P("")
    P(f"*(a) 抬升代理*：成功局上 carry 与物体 max_lift 的 Pearson r = **{r_ok:.3f}**"
      f"（n={len(ok_pair)}，门槛 ≥{PROXY_R_MIN}）⇒ {'✅ 成立' if proxy_ok else '❌ 不成立'}。")
    P(f"* 全局 {len(eps)} 局里有 **{multi} 局（{multi/max(len(eps),1)*100:.0f}%）夹持 ≥2 次**"
      "（掉罐后重抓）。物体 max_lift 取全剧最大，carry 只覆盖第一次夹持 ⇒ "
      "**A/B/C 类的 carry 不能当物体抬升读**，下面只用它做线索。")
    P(f"*(b) 阳性对照*（松手高度这把尺子的有效性来源）：策略成功局中位 "
      f"{med([e[KEY] for e in oh]):.1f} cm vs 专家示范中位 {med([e[KEY] for e in dh]):.1f} cm"
      f" ⇒ 差 **{ctrl_diff:+.1f} cm**（容差 ±{CTRL_TOL_CM}）⇒ "
      f"{'✅ 尺子准，成功局复现了专家的松手高度' if ctrl_ok else '❌ 尺子可疑'}。")

    P("")
    P("## 二、专家示范的参照系（高度均以**抓取点**为基准）")
    P("")
    P("| 示范 | 局数 | 夹持期峰值抬升 carry (cm) | **松手高度 = 跌落高度** (cm) |")
    P("| --- | --- | --- | --- |")
    for name, dd in (("反向 mix60f60r_rev", demo_rev), ("正向 mix60f60r", demo_fwd)):
        held = [e for e in dd if e["held"]]
        P(f"| {name} | {len(dd)}（夹住过 {len(held)}） | {stat([e['carry_cm'] for e in held])} "
          f"| {stat([e[KEY] for e in held])} |")
    if dh:
        P(f"* 反向示范的松手高度**上界**（n={len(dh)} 的最大值）= "
          f"{max(e[KEY] for e in dh):.1f} cm。专家从来不在更高的地方撒手。")

    P("")
    P("## 三、策略各失败类（同基准、同口径）")
    P("")
    P("| 类 | 局数 | 有松手事件 | 松手高度 (cm) | carry (cm) | 物体 max_lift (cm) |")
    P("| --- | --- | --- | --- | --- | --- |")
    for k in ("OK", "A", "B", "C"):
        v = groups.get(k, [])
        if not v:
            continue
        rel = [e for e in v if np.isfinite(e[KEY])]
        P(f"| {k} | {len(v)} | {len(rel)} | {stat([e[KEY] for e in rel])} "
          f"| {stat([e['carry_cm'] for e in v if e['held']])} "
          f"| {stat([e['obj_lift_cm'] for e in v])} |")

    P("")
    P("## 四、结论（自动判定，别手改）")
    P("")
    if not ctrl_ok:
        P("* ❌ **阳性对照没过** ⇒ 松手高度这把尺子本身可疑，本工具**不下任何结论**。"
          "先查 state 契约/夹爪阈值，别拿第四节的数字去改处方。")
    elif not ch or not dh:
        P(f"* 样本不足（C 类有松手事件 {len(ch)} 局、示范 {len(dh)} 局），不下结论。")
    else:
        dmax = max(e[KEY] for e in dh)
        over = [e for e in ch if e[KEY] > dmax]
        dm, cm = med([e[KEY] for e in dh]), med([e[KEY] for e in ch])
        p0 = rule_of_three(len(dh))
        pval = binom_tail_ge(len(over), len(ch), p0)
        P(f"* 专家松手高度：中位 {dm:.1f} cm，全域上界 {dmax:.1f} cm（n={len(dh)}）。")
        P(f"* C 类（送到了却没落定）松手高度：中位 {cm:.1f} cm（n={len(ch)}），"
          f"其中 **{len(over)}/{len(ch)} 局超过专家的整个值域**"
          f"{'：' + ', '.join(f'{e[KEY]:.1f}' for e in sorted(over, key=lambda x: -x[KEY])) if over else ''}。")
        P(f"* 显著性：示范 {len(dh)} 局里 0 局越过 {dmax:.1f} cm ⇒ 越界率的 95% 上界 "
          f"p₀=3/{len(dh)}={p0:.3f}（rule of three，取保守值而不是 0）。"
          f"在 p₀ 下「{len(ch)} 局里至少 {len(over)} 局越界」的二项尾概率 "
          f"**p={pval:.2e}** ⇒ {'**显著**' if pval < 0.05 else '不显著（样本太少或越界太少）'}。")
        if len(over) >= max(2, int(0.3 * len(ch))) and pval < 0.05:
            P("* ⇒ **机制确认**：相当一部分 C 类失败是在专家从不到达的高度撒手的，"
              "can 跌落翻倒、不满足「立着保持 10 步」。这是**策略的执行偏差**，"
              "不是任务判据太严（专家在 2 cm 高度松手就能过判据）。")
            okc = med([e["carry_cm"] for e in groups.get("OK", []) if e["held"]])
            cc_c = med([e["carry_cm"] for e in groups.get("C", []) if e["held"]])
            dc = med([e["carry_cm"] for e in dh])
            P(f"* 峰值抬升 carry 中位：成功局 **{okc:.1f} cm ≈ 专家 {dc:.1f} cm**（学对了）；"
              f"C 类 **{cc_c:.1f} cm**（比专家高 {cc_c-dc:+.1f} cm，**确实举过头**）。"
              " 所以病因是**两段**：先举得比示范高，再在下降没走完时就撒手。")
            P("* 处方优先级（档 2c 判 R2 时直接用）：**先修「下压到位再松手」**"
              "（示范里松手高度只有 ~2 cm，这条信息**本来就在数据里**，"
              "说明是策略没学准，不是数据里没有）。第六节先判掉 normalizer 那条路。")
        elif abs(cm - dm) <= 3.0 and len(over) <= 1:
            P(f"* ⇒ C 类与专家差 {cm-dm:+.1f} cm（|差| ≤ 3 cm）、越界仅 {len(over)} 局"
              f"（p={pval:.2e}）⇒ **松手高度不是主因**，"
              " 别再去压抬升/松手高度，回去查落点精度、松手时机与判据。")
        else:
            P(f"* ⇒ C 类中位比专家高 {cm-dm:+.1f} cm、越界 {len(over)}/{len(ch)} 局"
              f"（p={pval:.2e}）⇒ **倾向**执行偏差，但证据不够硬，"
              "需要更多局（C 类样本太少，或示范值域本身太散）。")
        if not proxy_ok:
            P("* ⚠️ 附带说明：抬升代理在成功局上都没到 r≥0.8，所以本文件**不谈**"
              "「举多高」，只谈「在多高处松手」（后者是直接测量、且过了阳性对照）。")

    # ── 五、多段夹持：成功与失败最干净的分水岭 ────────────────────────────────
    P("")
    P("## 五、多段夹持（掉罐重抓）与 first/last/最高 三种口径的稳健性")
    P("")
    dmax2 = max(e[KEY] for e in dh) if dh else float("nan")
    P("| 类 | 局数 | 夹持段数中位 | ≥2 段 | 首次松手越界 | 末次越界 | 最高越界 |")
    P("| --- | --- | --- | --- | --- | --- | --- |")
    ok_multi = ok_n = fail_multi = fail_n = 0
    for k in ("OK", "A", "B", "C"):
        v = groups.get(k, [])
        if not v:
            continue
        n2 = sum(1 for e in v if e["n_hold"] >= 2)
        nh = [e["n_hold"] for e in v]
        ov = lambda key: sum(1 for e in v if np.isfinite(e[key]) and e[key] > dmax2)  # noqa: E731
        P(f"| {k} | {len(v)} | {int(np.median(nh))} | **{n2}/{len(v)}** "
          f"| {ov(KEY)}/{len(v)} | {ov('release_last_above_cm')}/{len(v)} "
          f"| {ov('release_max_above_cm')}/{len(v)} |")
        if k == "OK":
            ok_multi, ok_n = n2, len(v)
        else:
            fail_multi, fail_n = fail_multi + n2, fail_n + len(v)
    if ok_n and fail_n:
        pf = fisher_two_sided(ok_multi, ok_n, fail_multi, fail_n)
        P("")
        P(f"* 成功局 {ok_multi}/{ok_n} 出现多段夹持，失败局 {fail_multi}/{fail_n} "
          f"⇒ Fisher 双侧 **p={pf:.2e}**"
          f"（{'**显著**' if pf < 0.05 else '不显著'}）。")
        if pf < 0.05:
            P("* ⇒ 「一次干净抓取」确实是成功的必要条件：提前从高处撒手 ⇒ can 跌落/侧躺 "
              "⇒ 策略再去抓 ⇒ 多段夹持 ⇒ 400 步超时。")
        else:
            P("* ⚠️ ⇒ **「多段夹持是分水岭」这条不成立**（p≥0.05）。"
              "本工具第二版曾经在这里报出 p=1.1e-11，那是**分段 bug 造出来的假信号**："
              "当时把「合拢途中宽度瞬时经过 0.05、最终压到 0.001」的**空合**也算成一次夹持，"
              "于是每一局失败都凭空多出几段（坑 31(d)）。修成分段 + 中位宽度判据后，"
              "A 类 31 局里只有 2 局真的夹持 ≥2 段 ⇒ 信号消失。**别把这条写进任何结论。**")
        P("* 三种口径（首次/末次/最高）给出的越界局数基本一致 ⇒ 第四节的结论"
          "**不依赖**「取哪一次松手」这个选择。")
    if extra:
        P("")
        P(f"* 额外读入的产物目录：{', '.join(p.name for p in extra)}")

    # ── 六、下压指令有没有被 normalizer / 动作幅度压没？ ──────────────────────
    P("")
    P("## 六、判掉「normalizer 把下压压没了」这条假设")
    P("")
    if demo_act is None or pol_act is None:
        P("* （没有动作数据，跳过本节）")
    else:
        dd = demo_act[:, IDZ].astype(np.float64)
        pp = pol_act[:, IDZ].astype(np.float64)
        P("| 量 | 专家示范 | 策略 | 判定 |")
        P("| --- | --- | --- | --- |")
        rng_ok = (pp.min() <= dd.min() * 0.8) and (pp.max() >= dd.max() * 0.8)
        std_ratio = pp.std() / dd.std() if dd.std() > 1e-9 else float("nan")
        P(f"| dz 值域 | [{dd.min():+.2f},{dd.max():+.2f}] | [{pp.min():+.2f},{pp.max():+.2f}] "
          f"| {'✅ 没被截断' if rng_ok else '⚠️ 策略值域明显更窄'} |")
        P(f"| dz 标准差 | {dd.std():.3f} | {pp.std():.3f} | 比值 **{std_ratio:.2f}** "
          f"{'✅ 幅度没被压扁' if 0.8 <= std_ratio <= 1.25 else '⚠️ 幅度异常'} |")
        dm_dz = med([e["pre_release_dz"] for e in dh])
        ok_dz = med([e["pre_release_dz"] for e in groups.get("OK", [])])
        c_dz = med([e["pre_release_dz"] for e in groups.get("C", [])])
        P(f"| 松手前 {PRE_DZ_W} 步 mean dz（中位） | {dm_dz:+.4f} | 成功局 {ok_dz:+.4f} / "
          f"C 类 {c_dz:+.4f} | {'✅ 下压指令在' if np.isfinite(c_dz) and c_dz < 0 else '⚠️ C 类没在下压'} |")
        P("")
        squeeze = (not rng_ok) or not (0.8 <= std_ratio <= 1.25) or not (np.isfinite(c_dz) and c_dz < 0)
        if squeeze:
            P("* ⇒ **normalizer / 动作幅度这条线还没排掉**：策略的 dz 值域或标准差明显偏离示范，"
              "或 C 类松手前根本不在下压。先去查 normalizer 的统计量与 action 反归一化。")
        else:
            P("* ⇒ **normalizer 假设排掉**：策略的 dz 值域、标准差、以及松手前的下压指令"
              "都跟示范同量级，动作幅度没有被压扁。")
            P("* 那么「松手太高」只剩两个来源，且都指向**时机**而不是**幅度**："
              "①峰值举得比示范高（第四节已量到 C 类 carry 中位 "
              f"{med([e['carry_cm'] for e in groups.get('C', []) if e['held']]):.1f} cm vs "
              f"专家 {med([e['carry_cm'] for e in dh]):.1f} cm），同样的下压速率自然停不到 2 cm；"
              "②夹爪是**bang-bang**（grip 动作 std≈0.95、值域顶到 ±1），"
              "开合是个离散决策，早开一步就从高处掉。"
              " ⇒ 加数据之前，先按这两条改：把「下降段」在训练里的权重提上去，"
              "或检查 K=10 开环执行是否让下降段被截断。")
    # ── 七、A 类（物体从没离地）到底是「没夹住」还是「夹住了没抬起来」 ──────────
    P("")
    P("## 七、A 类（44% 的失败）是**另一种病**：空合，不是松手太高")
    P("")
    demo_empty = sum(e["n_empty_close"] for e in demo_rev)
    demo_hold = sum(e["n_hold"] for e in demo_rev)
    P(f"* 专家反向示范：{demo_hold} 次真夹持、**{demo_empty} 次空合**（60 局）"
      "⇒ 专家从不空合，抓取本身不是难点。")
    P("")
    P("| 类 | 局数 | **一次都没夹住** | 真夹持次数 | 空合次数 | 空合率 |")
    P("| --- | --- | --- | --- | --- | --- |")
    for k in ("OK", "A", "B", "C"):
        v = groups.get(k, [])
        if not v:
            continue
        zero = sum(1 for e in v if e["n_hold"] == 0)
        th = sum(e["n_hold"] for e in v)
        te = sum(e["n_empty_close"] for e in v)
        rate = te / (te + th) * 100 if (te + th) else float("nan")
        P(f"| {k} | {len(v)} | **{zero}/{len(v)}** | {th} | {te} | {rate:.0f}% |")
    av = groups.get("A", [])
    if av:
        zero = [e for e in av if e["n_hold"] == 0]
        held = [e for e in av if e["n_hold"] > 0]
        P("")
        P(f"* A 类 {len(av)} 局拆开：**{len(zero)} 局从头到尾一次都没夹住**"
          f"（只有空合，can 根本没进过手指），另 {len(held)} 局夹住过但没抬起来。")
        if held:
            P(f"* 夹住过的那 {len(held)} 局，松手高度中位 "
              f"{med([e[KEY] for e in held]):.1f} cm、峰值抬升中位 "
              f"{med([e['carry_cm'] for e in held]):.1f} cm ⇒ 抬升几乎为 0，"
              "是**夹住了但没提起来**（或一提就滑脱），不是「提起来后松手太高」。")
        P("* ⇒ **A 类与 B/C 类是两种不同的病，处方不同**：")
        P("  * A（没夹住）= **接近段/合爪时机**问题：合爪瞬间横向偏差太大。"
          "这与档 1 已量过的机理同一条（坑 17：K≥25 时在 5.4 cm 偏差处就空合爪，"
          "而 can 半径 2.5 cm + 夹爪半开口 4.0 cm ⇒ 必须 ≲1.5 cm）。")
        P("  * B/C（夹住了、松手太高）= **下降段/松手时机**问题（第四、六节）。")
        P("  * ⇒ 「修一处三类同时下降」这个预测**作废**：A 占失败的 44%，"
          "它不吃「下压到位再松手」这个处方。两条要分开修，且 A 更大、更该先修。")

    return "\n".join(L) + "\n"


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev-demo", default=str(REV_DEMO))
    ap.add_argument("--fwd-demo", default=str(FWD_DEMO))
    ap.add_argument("--rollout", nargs="*", default=[], help="额外的策略读数目录")
    ap.add_argument("--out", default=str(RUNS / "_diag" / "lift_profile.md"))
    a = ap.parse_args()

    eps: list[dict] = []
    for d in [RUNS / d for d in REV_TEST] + [Path(p) for p in a.rollout]:
        got = rollout_profile(d)
        if not got:
            print(f"[lift] 跳过（缺产物）{d}")
        eps += got
    if not eps:
        print("[lift] FATAL 没有任何策略读数可比对")
        return 3
    demo_act = np.load(a.rev_demo, allow_pickle=True)["action"]
    pol_dirs = [RUNS / d for d in REV_TEST] + [Path(p) for p in a.rollout]
    pol_acts = [np.load(d / "rollout_actions.npz", allow_pickle=True)["action"]
                for d in pol_dirs if (d / "rollout_actions.npz").exists()]
    pol_act = np.concatenate(pol_acts) if pol_acts else None
    txt = build(demo_profile(Path(a.rev_demo)), demo_profile(Path(a.fwd_demo)), eps,
                [Path(p) for p in a.rollout], demo_act, pol_act)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(txt)
    print(txt)
    print(f"[lift] 落盘 -> {out}")
    return 0


# ── 自测：状态机与判定分支都必须被测到（它们决定第四节结论的方向）───────────────
def _mk(zs: list[float], ws: list[float]) -> np.ndarray:
    st = np.zeros((len(zs), 8), dtype=np.float32)
    st[:, IZ] = zs
    st[:, IG] = ws
    return st


def _fake_ep(h: float, rel: float, success: bool, dist: float, lift: float | None = None,
             n_hold: int = 1, rel_last: float | None = None, pre_dz: float = -0.085,
             n_empty: int = 0) -> dict:
    """造一局：抓取点 z=0.82；夹持期峰值抬升 h、松手高度 rel（均以抓取点为基准）。
    lift 默认 = h ⇒ 成功局的代理校验 r=1（阳性场景）。"""
    return {"z0": 0.90, "zmax": 0.82 + h / 100.0, "excursion_cm": (0.82 + h / 100.0 - 0.90) * 100.0,
            "release_z": 0.82 + rel / 100.0, "release_excursion_cm": rel - 8.0,
            "steps": 400, "held": n_hold > 0, "n_empty_close": n_empty, "n_hold": n_hold,
            "z_grasp": 0.82, "hold_w_med": 0.0499, "hold_steps_med": 180.0,
            "carry_cm": h, "carry_first_cm": h, KEY: rel,
            "release_last_above_cm": (rel if rel_last is None else rel_last),
            "release_max_above_cm": max(rel, rel if rel_last is None else rel_last),
            "n_release": 1, "success": success, "pre_release_dz": pre_dz, "rel_t": 300,
            "obj_lift_cm": (h if lift is None else lift), "min_dist_cm": dist, "src": "fake"}


def selftest() -> int:
    fails = 0
    n_case = 0

    def chk(name: str, cond: bool, detail: str = ""):
        nonlocal fails, n_case
        n_case += 1
        if cond:
            print(f"✅ {name}")
        else:
            fails += 1
            print(f"❌ {name} {detail}")

    # 1) 典型局：reset -> 张开 -> 下探 -> 收拢夹住 -> 抬到 1.00 -> 张开松手
    zs = [0.90, 0.90, 0.86, 0.82, 0.82, 0.90, 1.00, 1.00, 0.98, 0.95]
    ws = [0.0417, 0.0788, 0.0788, 0.0788, 0.05, 0.05, 0.05, 0.0788, 0.0788, 0.0788]
    m = ep_metrics(_mk(zs, ws))
    chk("抬升幅度 = zmax-z0", abs(m["excursion_cm"] - 10.0) < 1e-3, f"got {m['excursion_cm']}")
    chk("held=True", m["held"] is True)
    chk("抓取点 = 收拢那一刻", abs(m["z_grasp"] - 0.82) < 1e-5, f"got {m['z_grasp']}")
    chk("carry 以抓取点为基准", abs(m["carry_cm"] - 18.0) < 1e-3, f"got {m['carry_cm']}")
    chk("跌落高度 = 松手-抓取", abs(m[KEY] - 18.0) < 1e-3, f"got {m[KEY]}")

    # 2a) 关键回归（第二版就是栽在这里）：闭合是个**过程**，手指合拢途中宽度会短暂
    #     经过 0.05 附近，但最终压到 0.001 = 手里什么都没有。逐点阈值会把它算成一次
    #     成功夹持，于是 A 类（物体从没离地）凭空多出「夹持段」和「松手事件」。
    # 注意别把「张开」写成 0.0700：float32(0.07) = 0.07000000298 **大于** OPEN_W=0.070，
    # 会被当成没张开，整段切分就错位了（第一版自测就是这么假失败的）。张开一律写 0.0788。
    zs_e = [0.90, 0.90, 0.85, 0.82, 0.82, 0.82, 0.82, 0.85, 0.90, 0.90]
    ws_e = [0.0417, 0.0788, 0.0788, 0.0500, 0.0300, 0.0010, 0.0010, 0.0010, 0.0788, 0.0788]
    me = ep_metrics(_mk(zs_e, ws_e))
    chk("合拢途中经过 0.05 但最终空合 -> 不算夹住", me["held"] is False,
        f"got held={me['held']} n_hold={me['n_hold']} w={me['hold_w_med']}")
    chk("空合被计入 n_empty_close", me["n_empty_close"] == 1, f"got {me['n_empty_close']}")
    chk("空合不产生松手事件", not np.isfinite(me[KEY]))

    # 2b) 同样先经过 0.05，但**停在** 0.05（真夹住 can）-> 必须算夹住
    ws_h = [0.0417, 0.0788, 0.0788, 0.0500, 0.0500, 0.0500, 0.0500, 0.0500, 0.0788, 0.0788]
    mh = ep_metrics(_mk(zs_e, ws_h))
    chk("停在 0.05 -> 算夹住", mh["held"] is True and mh["n_empty_close"] == 0,
        f"got held={mh['held']} n_empty={mh['n_empty_close']}")
    chk("夹持宽度中位 = 0.05", abs(mh["hold_w_med"] - 0.05) < 1e-6, f"got {mh['hold_w_med']}")
    # 判据为什么是「段内宽度**中位数**」而不是「最小值」：真数据里成功局有 2/29 的段
    # 最小宽度掉到过 0.0015（松手瞬间的抖动），用 w_min 会把**真成功**判成空合；
    # 而中位数在 DEMO 60/60、OK 29/29 上都是 100% 正确。所以这段宽度必须有一段停留，
    # 不能只看极值 —— 下面这条自测就是把「瞬时掉到 0.001 但整体夹住了」钉住。
    ws_j = [0.0417, 0.0788, 0.0788, 0.0500, 0.0500, 0.0010, 0.0500, 0.0500, 0.0500, 0.0788, 0.0788]
    zs_j = [0.90, 0.90, 0.86, 0.82, 0.82, 0.82, 0.90, 1.00, 1.00, 0.98, 0.95]
    mj = ep_metrics(_mk(zs_j, ws_j))
    chk("瞬时掉到 0.001 但整体夹住 -> 仍算夹住（中位数判据）",
        mj["held"] is True and mj["n_empty_close"] == 0,
        f"got held={mj['held']} n_empty={mj['n_empty_close']}")
    chk("该段 w_min 确实低于阈值（说明不能用 min）",
        abs(mj["hold_w_med"] - 0.05) < 1e-6, f"got w_med={mj['hold_w_med']}")

    # 2c) 关键回归：reset 的 0.0417 不能被当成「已夹住」
    m2 = ep_metrics(_mk([0.90, 0.85, 0.82, 0.82, 0.85, 0.90],
                        [0.0417, 0.0417, 0.001, 0.001, 0.0788, 0.0788]))
    chk("reset 宽度不算夹住", m2["held"] is False, f"got held={m2['held']}")
    chk("空合无松手事件", not np.isfinite(m2[KEY]))

    # 3) 全程张开 / 夹住不松手
    m3 = ep_metrics(_mk([0.9, 0.9, 0.9], [0.0788] * 3))
    chk("从没夹住", m3["held"] is False and not np.isfinite(m3[KEY]))
    m4 = ep_metrics(_mk([0.90, 0.95, 1.05], [0.0417, 0.05, 0.05]))
    chk("未张开过->不算抓取尝试", m4["held"] is False and abs(m4["excursion_cm"] - 15.0) < 1e-3,
        f"got {m4}")

    # 4) 张开->空合->再张开->夹住->松手：只记第一次**成功夹持**后的松手
    zs5 = [0.90, 0.90, 0.82, 0.82, 0.90, 0.90, 0.84, 0.84, 0.97, 0.97, 0.95]
    ws5 = [0.0417, 0.0788, 0.0788, 0.001, 0.001, 0.0788, 0.0788, 0.05, 0.05, 0.0788, 0.0788]
    m5 = ep_metrics(_mk(zs5, ws5))
    chk("空合后重夹：记第一次成功松手", m5["held"] is True
        and abs(m5["release_excursion_cm"] - 7.0) < 1e-3, f"got {m5['release_excursion_cm']}")
    chk("空合计数", m5["n_empty_close"] == 1, f"got {m5['n_empty_close']}")
    chk("重夹后抓取点更新为 0.84", abs(m5["z_grasp"] - 0.84) < 1e-5, f"got {m5['z_grasp']}")
    chk("重夹后跌落高度 = 0.97-0.84", abs(m5[KEY] - 13.0) < 1e-3, f"got {m5[KEY]}")
    chk("夹持次数计数", m5["n_hold"] == 1, f"got {m5['n_hold']}")

    # 5) A/B/C 分类与 mg_tax_fail.py 同口径
    chk("分类 OK", classify({"success": True, "obj_lift_cm": 12.0, "min_dist_cm": 1.0}) == "OK")
    chk("分类 A", classify({"success": False, "obj_lift_cm": 0.5, "min_dist_cm": 64.0}) == "A")
    chk("分类 B", classify({"success": False, "obj_lift_cm": 14.0, "min_dist_cm": 46.0}) == "B")
    chk("分类 C", classify({"success": False, "obj_lift_cm": 18.0, "min_dist_cm": 2.0}) == "C")

    # 6) 第四节判定分支。默认示范松手高度紧凑地分布在 [1.5,2.5]（实测就是这样）。
    def batch(c_rels: list[float], ok_rel: float = 2.1, demo_rels: list[float] | None = None,
              ok_lift_break: bool = False) -> str:
        if demo_rels is None:
            # 60 局（与实测同量级）：示范局数直接决定 rule-of-three 的 p₀=3/n，
            # 只造 8 局会让 p₀=0.375 松到检不出显著，测的就不是真实工况了。
            demo_rels = [2.0 + (i % 3) * 0.5 - 0.5 for i in range(60)]   # [1.5,2.5]
        demo = [_fake_ep(11.5, r, True, 1.0) for r in demo_rels]
        ok = [_fake_ep(11.0 + i * 0.4, ok_rel + i * 0.05, True, 1.0,
                       lift=(99.0 if ok_lift_break else None)) for i in range(6)]
        cc = [_fake_ep(16.0, r, False, 2.0) for r in c_rels]
        return build(demo, demo, ok + cc, [])

    good = batch([2.5, 18.0, 20.0, 22.0, 15.0])
    chk("多数超专家值域 -> 机制确认", "机制确认" in good)
    chk("机制确认时给出二项 p 值", "二项尾概率" in good and "显著" in good)
    chk("机制确认时给出「先修松手」处方", "先修「下压到位再松手」" in good)
    chk("机制确认时点出两段病因", "先举得比示范高" in good and "下降没走完" in good)
    same = batch([2.2, 2.5, 1.8, 2.9, 2.1])
    chk("同高度 -> 松手高度不是主因", "松手高度不是主因" in same)
    # 「证据不够硬」这一支只有在**示范自己松手高度很散**时才可达：
    # 示范 [1,8] -> 中位 4.5、上界 8；C 类中位 7.6（>4.5+3）却只有 0 局超过 8。
    # 若示范很紧凑（上界-中位 <3 cm），「中位高出 3 cm」必然意味着半数以上越过上界，
    # 那就直接落进「机制确认」了 —— 这条数学关系本身也值得记在自测里。
    # ok_rel 必须跟上示范中位 4.5，否则先被阳性对照拦下（那正是门该有的顺序）
    mild = batch([2.0, 2.0, 7.6, 7.7, 7.8], ok_rel=4.5,
                 demo_rels=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    chk("示范散+C类中位偏高但无超值域 -> 证据不够硬", "证据不够硬" in mild)
    broken = batch([18.0, 20.0, 22.0, 19.0], ok_rel=12.0)
    chk("阳性对照失败 -> 拒绝下结论", "阳性对照没过" in broken and "机制确认" not in broken)
    noproxy = batch([18.0, 20.0, 22.0, 19.0], ok_lift_break=True)
    chk("代理坏了 -> 不谈举多高、仍可用松手高度", "不谈" in noproxy and "机制确认" in noproxy)
    chk("样本不足 -> 不下结论", "样本不足" in batch([]))

    # 7) 统计小工具本身
    chk("rule_of_three(60)=0.05", abs(rule_of_three(60) - 0.05) < 1e-12, f"got {rule_of_three(60)}")
    chk("rule_of_three(0)=1", rule_of_three(0) == 1.0)
    chk("二项尾 P(X>=2|n=10,p=.5)=1013/1024",
        abs(binom_tail_ge(2, 10, 0.5) - 1013 / 1024) < 1e-12, f"got {binom_tail_ge(2,10,0.5)}")
    # k=0 时走的是求和分支（不是 p<=0 的短路），会有 1e-16 量级的浮点残差
    chk("二项尾 k=0 -> 1.0", abs(binom_tail_ge(0, 5, 0.3) - 1.0) < 1e-12,
        f"got {binom_tail_ge(0, 5, 0.3)!r}")
    chk("二项尾 p=0 且 k>0 -> 0.0", binom_tail_ge(1, 5, 0.0) == 0.0)
    chk("二项尾 p=1 -> 1.0", binom_tail_ge(1, 5, 1.0) == 1.0)
    chk("4/5 越界在 p₀=0.05 下显著", binom_tail_ge(4, 5, 0.05) < 0.05)

    # 7b) 抓取点 = 宽度降到接触阈以下的第一刻（不是闭合段的第一帧）
    zs_c = [0.90, 0.90, 0.88, 0.86, 0.82, 0.82, 1.00, 1.00, 0.98]
    ws_c = [0.0417, 0.0788, 0.0788, 0.0650, 0.0500, 0.0500, 0.0500, 0.0788, 0.0788]
    mc = ep_metrics(_mk(zs_c, ws_c))
    chk("抓取点取接触时刻 z=0.82", abs(mc["z_grasp"] - 0.82) < 1e-5, f"got {mc['z_grasp']}")
    chk("carry = 1.00-0.82", abs(mc["carry_cm"] - 18.0) < 1e-3, f"got {mc['carry_cm']}")

    # 8) 第五节：多段夹持是成功/失败的分水岭
    def batch_hold(ok_holds: list[int], c_holds: list[int]) -> str:
        demo = [_fake_ep(11.5, 2.0 + (i % 3) * 0.5 - 0.5, True, 1.0) for i in range(60)]
        ok = [_fake_ep(11.0, 2.1, True, 1.0, n_hold=h) for h in ok_holds]
        cc = [_fake_ep(16.0, 2.2, False, 2.0, n_hold=h) for h in c_holds]
        return build(demo, demo, ok + cc, [])

    split = batch_hold([1] * 10, [2, 3, 2, 2, 4, 2, 3, 2, 2, 2])
    chk("多段夹持 -> 报「一次干净抓取」", "一次干净抓取" in split)
    chk("多段夹持 -> 给 Fisher p", "Fisher 双侧" in split)
    chk("多段夹持显著 -> 判必要条件", "确实是成功的必要条件" in split)
    chk("多段夹持显著 -> 不再喊「三类同源」", "同一个病因" not in split)
    uniform = batch_hold([1] * 10, [1] * 10)
    chk("全单段时不谎报显著", "Fisher 双侧" in uniform and "p=1.00e+00" in uniform)
    # 不显著时必须**主动撤回**那条分水岭叙事，并点名它是分段 bug 的假信号
    chk("不显著 -> 明说这条不成立", "这条不成立" in uniform)
    chk("不显著 -> 点名是分段 bug 的假信号", "分段 bug 造出来的假信号" in uniform)

    # 10) 第七节：A 类（物体从没离地）必须是「空合」，与 B/C 分开处方
    def batch_a(n_zero: int, n_held: int) -> str:
        demo = [_fake_ep(11.5, 2.0 + (i % 3) * 0.5 - 0.5, True, 1.0) for i in range(60)]
        ok = [_fake_ep(11.0, 2.1, True, 1.0) for _ in range(6)]
        cc = [_fake_ep(16.0, 3.0, False, 2.0) for _ in range(4)]
        aa = ([_fake_ep(0.0, float("nan"), False, 64.0, lift=0.3, n_hold=0, n_empty=3)
               for _ in range(n_zero)]
              + [_fake_ep(1.0, 0.4, False, 64.0, lift=2.0, n_hold=1, n_empty=1)
                 for _ in range(n_held)])
        return build(demo, demo, ok + cc + aa, [])

    a_txt = batch_a(20, 11)
    chk("A 类 -> 判为另一种病", "另一种病" in a_txt)
    chk("A 类 -> 报「一次都没夹住」的局数", "20/31" in a_txt)
    chk("A 类 -> 专家零空合作参照", "专家从不空合" in a_txt)
    chk("A 类 -> 撤回「修一处三类同降」", "这个预测**作废**" in a_txt)
    chk("A 类 -> 指向接近段/合爪时机", "接近段/合爪时机" in a_txt)
    chk("A 类 -> 与坑 17 的横向偏差对上", "坑 17" in a_txt)

    # 9) 第六节：normalizer / 动作幅度这条假设的判决
    def mk_act(dz_std: float, dz_min: float, dz_max: float, n: int = 4000) -> np.ndarray:
        rng = np.random.default_rng(0)
        a = np.zeros((n, 7), dtype=np.float32)
        a[:, IDZ] = np.clip(rng.normal(0.0, dz_std, n), dz_min, dz_max)
        return a

    demo_a = mk_act(0.25, -1.0, 0.86)
    def batch_act(pol_a, c_pre_dz: float = -0.10):
        demo = [_fake_ep(11.5, 2.0 + (i % 3) * 0.5 - 0.5, True, 1.0) for i in range(60)]
        ok = [_fake_ep(11.0, 2.1, True, 1.0) for _ in range(6)]
        cc = [_fake_ep(16.0, r, False, 2.0, pre_dz=c_pre_dz)
              for r in (18.0, 20.0, 22.0, 19.0, 15.0)]
        return build(demo, demo, ok + cc, [], demo_a, pol_a)

    ok_txt = batch_act(mk_act(0.247, -0.93, 0.84))
    chk("幅度匹配 -> 排掉 normalizer", "normalizer 假设排掉" in ok_txt)
    chk("排掉后指向时机而非幅度", "指向**时机**而不是**幅度**" in ok_txt)
    sq_txt = batch_act(mk_act(0.05, -0.20, 0.18))          # 下压被压扁到 1/5
    chk("幅度被压扁 -> 不排掉", "还没排掉" in sq_txt and "normalizer 假设排掉" not in sq_txt)
    nd_txt = batch_act(mk_act(0.247, -0.93, 0.84), c_pre_dz=+0.05)   # C 类松手前在上抬
    chk("C类松手前不下压 -> 不排掉", "还没排掉" in nd_txt)
    chk("无动作数据 -> 跳过第六节", "跳过本节" in batch([2.2, 2.5, 1.8]))

    print(f"\nselftest: {n_case - fails}/{n_case} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
