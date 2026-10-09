#!/usr/bin/env python
"""训练**在飞**时的早期哨兵：新配方 vs 历史参照臂，逐点同样本窗对比 loss / grdn（**零 GPU**）。

为什么要有它（档 7B 的实际情况）：
  7B 一发要烧 6 h 51 m（5500 步 × 4.49 s），而预注册的 M3 哨兵（末点 loss ≤ 0.042、
  grdn 末值 > 1.0 ⇒ 训崩 / < 0.05 且 loss 高 ⇒ 欠拟合）**只在末点判**。
  如果 lr=2e-4 配 5500 步是错的（训崩或严重欠拟合），末点才发现就等于白烧 6 h 51 m。
  本工具在训练途中就能读出一个**方向性**信号：把新配方与历史参照臂放在
  **同样本窗**上逐点对比 —— 两者的 log_freq 都是「800 样本/记录点」
  （batch8 的 log_freq=100、bs32 的 log_freq=25，出处 `runs/S7_PREREG.md` §1.3 与
  `code/run_pi05_s7b.sh` 里 `lf = round(800/BS)`）⇒ **第 i 个记录点就是第 800×(i+1) 个样本**，
  可以直接按下标配对，再用 `epch` 字段复核（差 > 0.01 就报警，说明窗长对不上）。

⚠️ 纪律（写死在这里，免得下次被当成判据用）：
  * 本工具**不产出任何判据读数**。M1~M5（档 7B）与 C1~C3（档 7C）仍然只在末点/TEST 上判，
    出处 `runs/S7_PREREG.md` §3。哨兵只回答一个问题：「这一发还要不要继续烧」。
  * 「中止一发明显训崩的训练」**不是**改判据（坑 40）：判据仍是末点那五条，
    中止只会让这一发没有末点读数 ⇒ 链会 die，人会来看。
  * 阈值全部来自预注册已写死的常数（1.5×、grdn 1.0 / 0.05），**不新造阈值**。
  * 早期 loss 受 warmup 与「预训练基座刚接上新数据」影响，前若干点比值天然偏大 ⇒
    规则要求「连续 ≥ `--streak` 个点」（默认 5，= 4000 样本）才触发，避免单点噪声误报。

⚠️ 日志位置（坑，实测吃到）：`code/mg_train.py` 先把日志写到 `runs/<job>_meta/train.log`，
  **训练成功结束后**才 `replace` 进 `runs/<job>/train.log`（`code/mg_train.py:187,210`）。
  所以在飞期间只有 `_meta` 那一份 ⇒ 本工具两个路径都试，并把实际读到的路径打进报告（坑 30）。

用法：
    $MG_PY code/mg_early_sentinel.py --selftest
    $MG_PY code/mg_early_sentinel.py \\
      --new s7b_bs32_seed2000:runs/pi05_mix60f120r_s7b_bs32_seed2000 \\
      --ref b8_seed2000:runs/pi05_mix60f120r_s3r_seed2000 \\
      --out runs/_diag/s7b_early_sentinel.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_seedcurve import parse_train_log  # noqa: E402  同一套解析，绝不重写（坑 54）

# ── 阈值：全部出自 runs/S7_PREREG.md §3 的 M3（不新造）─────────────────────────
GRDN_CRASH = 1.0        # M3 诊断分支：grdn > 1.0 ⇒ 训崩（lr 太大）
GRDN_UNDER = 0.05       # M3 诊断分支：grdn < 0.05 且 loss 高 ⇒ 欠拟合
LOSS_RATIO_MAX = 1.5    # M3 的门就是 1.5 × 参照末点 loss（0.042 = 1.5 × 0.0280）
EPOCH_TOL = 0.01        # 逐点同 epoch 的复核容差（每点 800 样本 ≈ 0.0172 epoch）


# ─────────────────────────── 纯函数 ───────────────────────────
def find_log(run: Path) -> tuple[Path | None, str]:
    """在飞期间日志在 `<run>_meta/train.log`；收工后才搬进 `<run>/train.log`。两个都试。"""
    for cand, why in ((run / "train.log", "run 目录（训练已收工）"),
                      (run.parent / f"{run.name}_meta" / "train.log", "_meta 目录（训练在飞）")):
        if cand.is_file():
            return cand, why
    return None, "两处都没有 train.log"


def pair_rows(new: list[dict], ref: list[dict]) -> list[dict]:
    """按下标配对（第 i 点 = 第 800×(i+1) 个样本），并用 epch 复核窗长是否真的对齐。"""
    out = []
    for i, (a, b) in enumerate(zip(new, ref)):
        ep_a, ep_b = a.get("epch"), b.get("epch")
        de = abs(ep_a - ep_b) if isinstance(ep_a, float) and isinstance(ep_b, float) else None
        ratio = (a["loss"] / b["loss"]) if (b.get("loss") or 0) > 0 else None
        out.append({"i": i + 1, "samples": 800 * (i + 1), "epch_new": ep_a, "epch_ref": ep_b,
                    "depoch": de, "loss_new": a.get("loss"), "loss_ref": b.get("loss"),
                    "ratio": ratio, "grdn_new": a.get("grdn"), "grdn_ref": b.get("grdn"),
                    "lr_new": a.get("lr")})
    return out


def streak_flag(vals: list[bool], streak: int) -> bool:
    """末尾是否**连续** streak 个 True（不足 streak 点 ⇒ False，不猜）。"""
    return len(vals) >= streak and all(vals[-streak:])


def rising(xs: list[float], streak: int) -> bool:
    """末尾 streak 个点是否单调上升（需要 streak+1 个点才有 streak 段差分）。"""
    if len(xs) < streak + 1:
        return False
    tail = xs[-(streak + 1):]
    return all(tail[j + 1] > tail[j] for j in range(streak))


def sentinel(rows: list[dict], streak: int) -> dict:
    """哨兵规则：只用预注册已有的常数（GRDN_CRASH / GRDN_UNDER / LOSS_RATIO_MAX）。"""
    if not rows:
        return {"state": "NA", "why": "没有配对点（新配方还没写出第一个记录点）", "flags": []}
    ep_bad = [r for r in rows if r["depoch"] is not None and r["depoch"] > EPOCH_TOL]
    crash_grdn = streak_flag([bool(r["grdn_new"] is not None and r["grdn_new"] > GRDN_CRASH)
                              for r in rows], streak)
    ratios = [r["ratio"] for r in rows if r["ratio"] is not None]
    losses = [r["loss_new"] for r in rows if r["loss_new"] is not None]
    crash_ratio = (streak_flag([x > LOSS_RATIO_MAX * 2 for x in ratios], streak)
                   and rising(losses, streak))
    under = (streak_flag([x > LOSS_RATIO_MAX for x in ratios], streak)
             and streak_flag([bool(r["grdn_new"] is not None and r["grdn_new"] < GRDN_UNDER)
                              for r in rows], streak))
    flags = []
    if ep_bad:
        flags.append(f"窗长对不上：{len(ep_bad)} 个点的 epoch 差 > {EPOCH_TOL}"
                     f"（最大 {max(r['depoch'] for r in ep_bad):.4f}）⇒ 同样本窗前提被破坏，本哨兵不可用")
    if crash_grdn:
        flags.append(f"疑似**训崩**：末尾连续 {streak} 点 grdn > {GRDN_CRASH}"
                     f"（末值 {rows[-1]['grdn_new']:.3f}）⇒ 预注册 M3 的『lr 太大』分支")
    if crash_ratio:
        flags.append(f"疑似**训崩**：末尾连续 {streak} 点 loss > {LOSS_RATIO_MAX*2:.1f}× 参照 且仍在上升"
                     f"（末点比值 {ratios[-1]:.2f}）")
    if under:
        flags.append(f"疑似**欠拟合**：末尾连续 {streak} 点 loss > {LOSS_RATIO_MAX}× 参照 且 "
                     f"grdn < {GRDN_UNDER} ⇒ 预注册 M3 的『欠拟合』分支（lr/步数配错）")
    if ep_bad:
        state = "NA"
    elif crash_grdn or crash_ratio:
        state = "CRASH"
    elif under:
        state = "UNDERFIT"
    else:
        state = "OK"
    why = {"OK": "没触发任何哨兵规则 ⇒ 继续烧（不代表末点一定过 M3）",
           "CRASH": "**建议人工决定中止**：继续烧大概率是白烧 6h51m（中止不是改判据，见工具头注释）",
           "UNDERFIT": "**建议人工决定中止**：lr/步数这一组绑定项可能配错，处方是开 lr 对照臂",
           "NA": "哨兵不可用（前提没满足）"}[state]
    return {"state": state, "why": why, "flags": flags,
            "last_ratio": ratios[-1] if ratios else None,
            "mean_ratio_tail": (sum(ratios[-streak:]) / len(ratios[-streak:])) if ratios else None,
            "max_grdn": max((r["grdn_new"] for r in rows if r["grdn_new"] is not None), default=None)}


# ─────────────────────────── 报告 ───────────────────────────
def build_report(new_lab: str, new_run: Path, ref_lab: str, ref_run: Path,
                 streak: int, tail: int, out: Path) -> dict:
    nlog, nwhy = find_log(new_run)
    rlog, rwhy = find_log(ref_run)
    lines = [f"# 早期哨兵：`{new_lab}` vs 参照 `{ref_lab}`（同样本窗逐点，**零 GPU**）", "",
             f"* 生成时间：{datetime.now():%F %T}（`code/mg_early_sentinel.py`）",
             f"* 新配方日志：`{nlog or '（缺）'}` —— {nwhy}",
             f"* 参照日志：`{rlog or '（缺）'}` —— {rwhy}",
             f"* 配对前提：两者每记录点都是 **800 样本**（batch8 log_freq=100 / bs32 log_freq=25）"
             f"⇒ 第 i 点 = 第 800×(i+1) 样本；用 `epch` 字段复核，容差 {EPOCH_TOL}", ""]
    if nlog is None or rlog is None:
        lines += ["## 读数：**不可用**（缺日志）", ""]
        out.write_text("\n".join(lines))
        return {"state": "NA", "n": 0}
    nrows = parse_train_log(nlog.read_text(errors="ignore"))
    rrows = parse_train_log(rlog.read_text(errors="ignore"))
    rows = pair_rows(nrows, rrows)
    s = sentinel(rows, streak)
    lines += [f"## 一、哨兵结论：**{s['state']}**", "", f"* {s['why']}"]
    if s["flags"]:
        lines += [f"* {f}" for f in s["flags"]]
    else:
        lines += ["* 触发的规则：无"]
    lines += [f"* 记录点：新 {len(nrows)} / 参照 {len(rrows)} ⇒ 配对 **{len(rows)}** 点"
              + (f"（= {rows[-1]['samples']} 样本、epoch {rows[-1]['epch_new']:.3f}）" if rows else ""),
              ""]
    if rows:
        lines += [f"* 末点 loss 比值（新/参照）= **{s['last_ratio']:.3f}**；"
                  f"末尾 {streak} 点均值 = {s['mean_ratio_tail']:.3f}（门 {LOSS_RATIO_MAX}）",
                  f"* 新配方 grdn：末值 {rows[-1]['grdn_new']:.3f}、全程最大 "
                  f"{s['max_grdn']:.3f}（训崩阈 {GRDN_CRASH}、欠拟合阈 {GRDN_UNDER}）",
                  f"* 新配方 lr 末值 = {rows[-1]['lr_new']:.3e}", "",
                  "## 二、逐点明细（末尾 %d 点 + 头 3 点）" % tail, "",
                  "| # | 样本 | epoch(新) | epoch(参照) | Δepoch | loss 新 | loss 参照 | 比值 | grdn 新 | grdn 参照 |",
                  "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        show = rows[:3] + ([{"sep": True}] if len(rows) > tail + 3 else []) + rows[-tail:]
        for r in show:
            if r.get("sep"):
                lines.append("| … | … | … | … | … | … | … | … | … | … |")
                continue
            lines.append(f"| {r['i']} | {r['samples']} | {r['epch_new']:.4f} | {r['epch_ref']:.4f} | "
                         f"{r['depoch']:.4f} | {r['loss_new']:.4f} | {r['loss_ref']:.4f} | "
                         f"{r['ratio']:.3f} | {r['grdn_new']:.3f} | {r['grdn_ref']:.3f} |")
        lines += ["", "## 三、这条读数**不能**用来做什么（诚实标注）", "",
                  "* 不能替代 M3：M3 判的是**末点** loss ≤ 0.042，本哨兵只判「趋势是否明显跑偏」。",
                  "* 不能推出「新配方更好/更差」：早期 loss 高低与闭环成功率**已知不相关**"
                  "（`runs/S7_PREREG.md` §1.3：崩掉的 seed2000 末点 loss 最低 0.0280）。",
                  "* 参照臂只有一个（batch8-seed2000）⇒ 比值里含参照臂自身的 run 间噪声"
                  "（极差 38.8 pp 的那套噪声），单点比值 ±20% 属正常。",
                  "* 前若干点受 warmup（200 步）与基座刚接新数据影响，比值天然偏大 ⇒ 规则要求连续 "
                  f"{streak} 点才触发。", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    return {"state": s["state"], "n": len(rows), "last_ratio": s.get("last_ratio"),
            "max_grdn": s.get("max_grdn"), "out": str(out)}


# ─────────────────────────── 自测 ───────────────────────────
def selftest() -> int:
    npass = nfail = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal npass, nfail
        if cond:
            npass += 1
        else:
            nfail += 1
            print(f"  [FAIL] {name}")

    import tempfile

    LOG = ("INFO 2026-10-03 14:29:34 ot_train.py:435 step:25 smpl:1K ep:3 epch:0.0172 "
           "loss:0.090 grdn:0.400 lr:2.0e-04 updt_s:4.48 data_s:0.01\n")
    chk("parse_train_log 复用：能读出 1 点", len(parse_train_log(LOG)) == 1)
    chk("parse_train_log 复用：字段齐", parse_train_log(LOG)[0]["grdn"] == 0.400)
    chk("进度条行不会被当成记录点（无 updt_s）",
        len(parse_train_log("Training: 4%|▍ | 200/5500 [15:06<6:37:03, 4.49s/step]")) == 0)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        run = root / "runs" / "jobA"
        (run.parent / "jobA_meta").mkdir(parents=True)
        (run.parent / "jobA_meta" / "train.log").write_text("x")
        chk("在飞：只有 _meta/train.log 也能找到",
            find_log(run)[0] == run.parent / "jobA_meta" / "train.log")
        run.mkdir(parents=True)
        (run / "train.log").write_text("x")
        chk("收工后：优先读 run 目录那一份", find_log(run)[0] == run / "train.log")
        chk("缺日志：返回 None 而不是抛", find_log(root / "nope")[0] is None)

    mk = lambda i, ep, lo, gr: {"i": i + 1, "samples": 800 * (i + 1), "epch_new": ep, "epch_ref": ep,
                                "depoch": 0.0, "loss_new": lo, "loss_ref": lo, "ratio": 1.0,
                                "grdn_new": gr, "grdn_ref": gr, "lr_new": 2e-4}
    ok = [mk(i, 0.0172 * (i + 1), 0.09 - 0.005 * i, 0.4) for i in range(10)]
    chk("健康轨迹 ⇒ OK", sentinel(ok, 5)["state"] == "OK")
    chk("健康轨迹：无 flag", sentinel(ok, 5)["flags"] == [])

    crash = [dict(r, grdn_new=1.5) for r in ok]
    chk("连续 5 点 grdn>1.0 ⇒ CRASH", sentinel(crash, 5)["state"] == "CRASH")
    crash4 = [dict(r, grdn_new=(1.5 if i >= 6 else 0.4)) for i, r in enumerate(ok)]
    chk("只有 4 点 grdn>1.0 ⇒ 不触发（不许单点误报）", sentinel(crash4, 5)["state"] == "OK")

    under = [dict(r, loss_new=r["loss_new"] * 2.0, ratio=2.0, grdn_new=0.01) for r in ok]
    chk("loss>1.5× 且 grdn<0.05 ⇒ UNDERFIT", sentinel(under, 5)["state"] == "UNDERFIT")
    hi_loss_only = [dict(r, loss_new=r["loss_new"] * 2.0, ratio=2.0) for r in ok]
    chk("loss 高但 grdn 正常 ⇒ 不判欠拟合（要两个条件同时成立）",
        sentinel(hi_loss_only, 5)["state"] == "OK")

    blow = [dict(r, loss_new=0.1 + 0.05 * i, ratio=3.0 + 0.1 * i) for i, r in enumerate(ok)]
    chk("比值>3.0 且 loss 单调上升 ⇒ CRASH", sentinel(blow, 5)["state"] == "CRASH")
    flat = [dict(r, loss_new=0.5, ratio=3.0) for i, r in enumerate(ok)]
    chk("比值高但 loss 不上升（已平台）⇒ 不判训崩", sentinel(flat, 5)["state"] == "OK")

    epbad = [dict(r, depoch=0.5) for r in ok]
    chk("epoch 差超容差 ⇒ NA（同样本窗前提被破坏）", sentinel(epbad, 5)["state"] == "NA")
    chk("点数不足 streak ⇒ 不猜，判 OK", sentinel(ok[:3], 5)["state"] == "OK")
    chk("空 rows ⇒ NA", sentinel([], 5)["state"] == "NA")

    chk("streak_flag：正好 5 个 True", streak_flag([False] * 3 + [True] * 5, 5) is True)
    chk("streak_flag：中间断一次就不算", streak_flag([True] * 4 + [False, True, True, True, True, False], 5) is False)
    chk("streak_flag：点数不足 ⇒ False", streak_flag([True, True], 5) is False)
    chk("rising：单调上升", rising([1, 2, 3, 4, 5, 6], 5) is True)
    chk("rising：有一处下降 ⇒ False", rising([1, 2, 3, 4, 6, 5], 5) is False)
    chk("rising：点数不足 ⇒ False", rising([1, 2, 3], 5) is False)

    a = [{"epch": 0.0172, "loss": 0.1, "grdn": 0.4, "lr": 2e-4},
         {"epch": 0.0344, "loss": 0.09, "grdn": 0.4, "lr": 2e-4}]
    b = [{"epch": 0.0172, "loss": 0.1, "grdn": 0.4, "lr": 1e-4},
         {"epch": 0.0344, "loss": 0.1, "grdn": 0.4, "lr": 1e-4}]
    pr = pair_rows(a, b)
    chk("pair_rows：按下标配对", len(pr) == 2 and pr[1]["samples"] == 1600)
    chk("pair_rows：比值算对", abs(pr[0]["ratio"] - 1.0) < 1e-9)
    c = [{"epch": 0.5, "loss": 0.1, "grdn": 0.4}, {"epch": 0.6, "loss": 0.1, "grdn": 0.4}]
    chk("pair_rows：epoch 差被记下来（复核用）", abs(pair_rows(a, c)[0]["depoch"] - 0.4828) < 1e-3)
    chk("pair_rows：参照 loss=0 不给 inf", pair_rows(a, [{"epch": 0.0172, "loss": 0.0, "grdn": 0.4}])[0]["ratio"] is None)

    chk("常数：grdn 训崩阈 = 1.0（出自预注册 M3）", GRDN_CRASH == 1.0)
    chk("常数：grdn 欠拟合阈 = 0.05（出自预注册 M3）", GRDN_UNDER == 0.05)
    chk("常数：loss 比值门 = 1.5（0.042 = 1.5×0.0280）", abs(LOSS_RATIO_MAX - 1.5) < 1e-9)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name, rows in (("jobNew", a), ("jobRef", b)):
            d = root / "runs" / name
            d.mkdir(parents=True)
            (d / "train.log").write_text(
                "\n".join(f"INFO x ot_train.py:435 step:{25*(i+1)} smpl:1K ep:3 "
                          f"epch:{r['epch']:.4f} loss:{r['loss']:.4f} grdn:{r['grdn']:.3f} "
                          f"lr:{r.get('lr', 1e-4):.1e} updt_s:4.48 data_s:0.01"
                          for i, r in enumerate(rows)))
        info = build_report("new", root / "runs" / "jobNew", "ref", root / "runs" / "jobRef",
                            5, 8, root / "out.md")
        chk("端到端：state=OK", info["state"] == "OK")
        chk("端到端：配对 2 点", info["n"] == 2)
        chk("端到端：报告落盘且非空", (root / "out.md").is_file() and (root / "out.md").stat().st_size > 200)
        txt = (root / "out.md").read_text()
        chk("报告里写了「不能替代 M3」", "不能替代 M3" in txt)
        chk("报告里写了日志实际路径（坑 30）", "train.log" in txt)
        miss = build_report("new", root / "runs" / "nope", "ref", root / "runs" / "jobRef",
                            5, 8, root / "out2.md")
        chk("缺日志：state=NA 且不抛", miss["state"] == "NA")
        chk("缺日志：也落一份报告说明原因", (root / "out2.md").is_file())

    print(f"[selftest] {npass} passed, {nfail} failed")
    return 1 if nfail else 0


# ─────────────────────────── CLI ───────────────────────────
def parse_spec(s: str) -> tuple[str, Path]:
    lab, _, path = s.partition(":")
    p = Path(path)
    return lab, (p if p.is_absolute() else MG / p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new", required=False, metavar="LABEL:RUN_PATH", help="在飞/新配方的 run 目录")
    ap.add_argument("--ref", required=False, metavar="LABEL:RUN_PATH", help="历史参照臂的 run 目录")
    ap.add_argument("--streak", type=int, default=5, help="连续多少点才触发（默认 5 = 4000 样本）")
    ap.add_argument("--tail", type=int, default=12, help="明细表里显示末尾多少点")
    ap.add_argument("--out", default=str(MG / "runs" / "_diag" / "early_sentinel.md"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.new or not args.ref:
        raise SystemExit("[sentinel] 需要 --new 与 --ref（或 --selftest）")
    nl, np_ = parse_spec(args.new)
    rl, rp = parse_spec(args.ref)
    out = Path(args.out)
    out = out if out.is_absolute() else MG / out
    info = build_report(nl, np_, rl, rp, args.streak, args.tail, out)
    print(f"[sentinel] state={info['state']} 配对点={info['n']} "
          f"末点比值={info.get('last_ratio')} grdn最大={info.get('max_grdn')}")
    print(f"[sentinel] 报告 -> {info.get('out', out)}")
    return 0 if info["state"] in ("OK", "NA") else 7


if __name__ == "__main__":
    raise SystemExit(main())
