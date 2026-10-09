#!/usr/bin/env python
"""按 epoch 对齐两条训练曲线的 val 读数（纯 CPU，不碰 GPU、不碰正在跑的脚本）。

为什么需要它：
  档 2c 拿「反向单任务 60 集」对照「正反向联合 120 集」，两边 steps 都是等 epoch 设计的
  （7600 vs 14400 ≈ 3.79 ep），但**扫描检查点的步号完全对不上**：单任务 16032 帧 / bs8
  = 2004 步一个 epoch，联合 30447 帧 / bs8 = 3806 步一个 epoch。直接拿 step 4000 比
  step 4000，等于拿「2.0 epoch 的单任务」比「1.05 epoch 的联合」—— 单任务当然赢，
  这个赢跟「干扰」一点关系都没有，纯粹是训练量不同。

  所以任何跨 run 的曲线比较都必须先换算成 epoch。本工具只做这一件事，并且把
  steps/epoch 的**来源打印出来**（坑 30：参考值必须自带出处），不接受"我记得是 2004"。

口径与纪律：
  * val 曲线的 n 通常只有 10–20 局，1σ≈10–15 pp。本工具**只报趋势**，
    并在每一行标出 ±1σ；它不是门，不产生判定（门在 mg_verdict_s2c.py 里，读 TEST）。
  * 坑 27：val 与 TEST 在档 2 上出现过**反序**（val 选点 50% → TEST 26.7%）。
    因此 epoch 对齐后的差值只回答「学得快不快」，不回答「关门能不能过」。
  * 对齐规则预先写死：对 A 的每个 epoch 网格点，取 B 中 |epoch 差| 最小的那一点；
    并列取**更早**的 step（更少训练）。跑完不许改规则。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_epoch_curve.py \
        --run revonly:runs/pi05_rev60_s2c --run joint:runs/pi05_mix60f60r_s2 --align'
    bash -c 'source code/env.sh && $MG_PY code/mg_epoch_curve.py --selftest'
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mg_verdict_s2 import fisher_two_sided  # noqa: E402  已对着 scipy 校验过的实现

MG = Path(os.environ.get("MG_ROOT", str(HERE.parent)))

ALIGN_RULE = ("for each epoch grid point of run A, take run B's point with minimal "
              "|epoch_A - epoch_B|; tie-break = earlier step (less training)")


# ── steps/epoch：只信 meta.json，且把出处打出来 ────────────────────────────────
def _rel(p: Path) -> str:
    return str(p.relative_to(MG)) if str(p).startswith(str(MG)) else str(p)


def steps_per_epoch(run: Path) -> tuple[float, str]:
    """返回 (steps_per_epoch, provenance)。找不到就抛，绝不猜默认值。

    优先级（每一步都把出处打进 provenance，坑 30）：
      1. meta.json 的 episodes_subset.n_frames —— 子集训练时**只有这个**是对的；
         用全集帧数会把 epoch 算小一半（档 2c 就是这么设计的：60/120 集）。
      2. meta.json 的 dataset_total_frames。
      3. meta.json 的 dataset_root -> <root>/meta/info.json 的 total_frames
         （老 run 的 meta.json 没存帧数，但存了数据集路径；读原始数据集比 --spe 手填可靠）。
    """
    cands = [run.parent / (run.name + "_meta") / "meta.json", run / "meta.json"]
    for mp in cands:
        if not mp.is_file():
            continue
        j = json.loads(mp.read_text())
        bs = j.get("batch_size")
        if not bs:
            continue
        sub = j.get("episodes_subset") or {}
        if sub.get("n_frames"):
            return sub["n_frames"] / bs, "%s: episodes_subset.n_frames=%d / batch_size=%d" % (
                _rel(mp), sub["n_frames"], bs)
        if j.get("dataset_total_frames"):
            return j["dataset_total_frames"] / bs, "%s: dataset_total_frames=%d / batch_size=%d" % (
                _rel(mp), j["dataset_total_frames"], bs)
        root = j.get("dataset_root")
        if root:
            ip = Path(root) / "meta" / "info.json"
            if ip.is_file():
                tf = json.loads(ip.read_text()).get("total_frames")
                if tf:
                    return tf / bs, "%s: batch_size=%d × %s: total_frames=%d" % (
                        _rel(mp), bs, _rel(ip), tf)
    raise SystemExit("FATAL 找不到 %s 的 frames/batch_size（meta.json / 数据集 info.json），"
                     "请用 --spe 显式给 steps-per-epoch，不要靠猜" % run)


def read_curve(run: Path, sub: str, want: set[str]) -> list[dict]:
    """读 run/<sub>/step_<s>_<dir>/eval_summary.json，返回按 (step, dir) 排序的表。"""
    d = run / sub
    out: list[dict] = []
    if not d.is_dir():
        return out
    for ep in sorted(d.glob("step_*")):
        m = re.fullmatch(r"step_(\d+)_(fwd|rev)", ep.name)
        if not m:
            continue
        direction = "fwd" if m.group(2) == "fwd" else "rev"
        if direction not in want:
            continue
        f = ep / "eval_summary.json"
        if not f.is_file():
            continue
        j = json.loads(f.read_text())
        n = int(j.get("episodes") or 0)
        k = int(j.get("n_success") or 0)
        if n <= 0:
            continue
        out.append({
            "step": int(m.group(1)), "dir": direction, "n": n, "k": k,
            "p": k / n, "sigma": math.sqrt((k / n) * (1 - k / n) / n),
            "K": j.get("n_action_steps"), "seed": j.get("seed"),
            "path": str(f.relative_to(MG)) if str(f).startswith(str(MG)) else str(f),
        })
    out.sort(key=lambda r: (r["dir"], r["step"]))
    return out


def detect_sub(run: Path) -> str:
    for name in ("sweep_rev", "sweep_bidir", "sweep"):
        if (run / name).is_dir():
            return name
    raise SystemExit("FATAL %s 下没有 sweep_rev/sweep_bidir/sweep，请用 --sweep 指定" % run)


def sig1(p: float, n: int) -> float:
    return math.sqrt(p * (1 - p) / n) if n > 0 else 0.0


def align(a: list[dict], b: list[dict]) -> list[tuple[dict, dict | None]]:
    """按 ALIGN_RULE 把 b 对到 a 的每个 epoch 网格点上（epoch 已经写进每行）。"""
    pairs: list[tuple[dict, dict | None]] = []
    for ra in a:
        best, bestd = None, None
        for rb in b:
            if rb["dir"] != ra["dir"]:
                continue
            dd = abs(rb["ep"] - ra["ep"])
            if bestd is None or dd < bestd - 1e-12 or (abs(dd - bestd) < 1e-12
                                                       and rb["step"] < best["step"]):
                best, bestd = rb, dd
        pairs.append((ra, best))
    return pairs


def fmt_run_table(label: str, spe: float, prov: str, rows: list[dict]) -> list[str]:
    L = ["## %s" % label, "",
         "- steps/epoch = **%.1f**  ← %s" % (spe, prov),
         "- 读数目录里 `ep` = step / steps_per_epoch；n 小时 1σ 很大，只看趋势。", "",
         "| step | epoch | dir | n | succ | rate | ±1σ | K |",
         "|---:|---:|:--|---:|---:|---:|---:|---:|"]
    for r in rows:
        L.append("| %d | %.2f | %s | %d | %d | %.1f%% | %.1f pp | %s |"
                 % (r["step"], r["ep"], r["dir"], r["n"], r["k"],
                    100 * r["p"], 100 * r["sigma"], r["K"]))
    return L


def fmt_align(la: str, lb: str, pairs: list[tuple[dict, dict | None]]) -> list[str]:
    L = ["## epoch 对齐：%s（基准） vs %s" % (la, lb), "",
         "- 规则：%s" % ALIGN_RULE, "",
         "| dir | %s step | epoch | rate | %s step | epoch | rate | Δ(pp) | Fisher p |"
         % (la, lb),
         "|:--|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for ra, rb in pairs:
        if rb is None:
            L.append("| %s | %d | %.2f | %.1f%% | — | — | — | — | — |"
                     % (ra["dir"], ra["step"], ra["ep"], 100 * ra["p"]))
            continue
        dp = 100 * (ra["p"] - rb["p"])
        # ⚠️ fisher_two_sided 的签名是 (成功数A, **试验数A**, 成功数B, **试验数B**)，
        #    不是 (成功, 失败, 成功, 失败)。第一版传了失败数，p 值全错但不报错 —— 静默错。
        pv = fisher_two_sided(ra["k"], ra["n"], rb["k"], rb["n"])
        L.append("| %s | %d | %.2f | %.1f%% | %d | %.2f | %.1f%% | %+.1f | %.3f |"
                 % (ra["dir"], ra["step"], ra["ep"], 100 * ra["p"],
                    rb["step"], rb["ep"], 100 * rb["p"], dp, pv))
    return L


def build(specs: list[tuple[str, Path, str, float | None]], want: set[str],
          do_align: bool) -> str:
    loaded = []
    for label, run, sub, spe_ov in specs:
        if spe_ov is not None:
            spe, prov = spe_ov, "--spe 手工指定（未经 meta.json 校验）"
        else:
            spe, prov = steps_per_epoch(run)
        rows = read_curve(run, sub, want)
        for r in rows:
            r["ep"] = r["step"] / spe
        loaded.append((label, run, sub, spe, prov, rows))

    out = ["# epoch 对齐 val 曲线", "",
           "生成时间：%s（%s）" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                   os.environ.get("MG_TAG", "mg_epoch_curve")),
           "", "> 这是**趋势工具**，不是门。val n 小、且坑 27 记录过 val/TEST 反序，",
           "> 任何「过没过」的结论只能由 mg_verdict_s2c.py 读 TEST 得出。", ""]
    for label, run, sub, spe, prov, rows in loaded:
        rel = str(run.relative_to(MG)) if str(run).startswith(str(MG)) else str(run)
        out += fmt_run_table("%s  ← %s/%s" % (label, rel, sub), spe, prov, rows)
        if not rows:
            out.append("- （没有可用读数）")
        out.append("")

    if do_align:
        if len(loaded) != 2:
            out += ["## epoch 对齐", "", "需要恰好 2 个 --run 才能对齐（当前 %d 个）。"
                    % len(loaded)]
        else:
            (la, _, _, _, _, ra_), (lb, _, _, _, _, rb_) = loaded
            out += fmt_align(la, lb, align(ra_, rb_))
            out.append("")
    return "\n".join(out) + "\n"


def parse_run(s: str) -> tuple[str, Path, str]:
    """LABEL:PATH[:SWEEPSUB] —— 第三段可省。

    为什么必须支持逐 run 指定：档 2c 的对照双方扫描目录**名字不一样**
    （单任务是 sweep_rev，档 2 联合是 sweep_bidir）。用全局 --sweep 会让
    其中一条静默读到 0 个点，输出一张"没有可用读数"的空表 —— 看起来像
    「联合模型完全学不会」，那会是彻底的误读。
    """
    parts = s.split(":")
    if len(parts) < 2:
        raise SystemExit("FATAL --run 需要 LABEL:PATH[:SWEEPSUB] 形式，收到 %r" % s)
    label, p = parts[0], parts[1]
    sub = parts[2].strip() if len(parts) > 2 else ""
    run = Path(p)
    if not run.is_absolute():
        run = MG / run
    return label.strip(), run, sub


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", default=[], metavar="LABEL:PATH[:SUB]",
                    help="可重复；LABEL 只用于表头；SUB 缺省时用 --sweep，再缺省则自动探测")
    ap.add_argument("--sweep", default="",
                    help="扫描子目录名的全局默认值（各 run 未自带 SUB 时才用）")
    ap.add_argument("--spe", action="append", default=[], metavar="LABEL:VALUE",
                    help="手工指定 steps-per-epoch（meta.json 缺失时才用）")
    ap.add_argument("--direction", default="both", choices=["rev", "fwd", "both"])
    ap.add_argument("--align", action="store_true", help="两条 run 时输出 epoch 对齐表")
    ap.add_argument("--out", default="", help="落盘 markdown 路径（默认只打印）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    if not args.run:
        ap.error("至少要一个 --run")
    want = {"rev", "fwd"} if args.direction == "both" else {args.direction}
    spe_ov = {}
    for s in args.spe:
        lab, v = s.split(":", 1)
        spe_ov[lab.strip()] = float(v)
    specs = []
    for s in args.run:
        label, run, sub = parse_run(s)
        sub = sub or args.sweep or detect_sub(run)
        specs.append((label, run, sub, spe_ov.get(label)))
    md = build(specs, want, args.align)
    if args.out:
        op = Path(args.out)
        if not op.is_absolute():
            op = MG / op
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(md)
        print("[epoch_curve] 落盘 -> %s" % op)
    print(md)
    return 0


# ── selftest：临时目录里造两个假 run，验换算/对齐/缺件不崩 ─────────────────────
def _mk_run(root: Path, name: str, frames: int, bs: int, sub: str,
            pts: list[tuple[int, str, int, int]], subset: bool = True) -> Path:
    run = root / name
    (run / sub).mkdir(parents=True, exist_ok=True)
    meta = {"batch_size": bs, "dataset_total_frames": 30447, "steps": 99999}
    if subset:
        meta["episodes_subset"] = {"n_frames": frames}
    mdir = root / (name + "_meta")
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "meta.json").write_text(json.dumps(meta))
    for step, d, n, k in pts:
        ed = run / sub / ("step_%d_%s" % (step, d))
        ed.mkdir(parents=True, exist_ok=True)
        (ed / "eval_summary.json").write_text(json.dumps({
            "episodes": n, "n_success": k, "pc_success": k / n if n else 0.0,
            "n_action_steps": 10, "seed": 8000, "task_mode":
                "reverse" if d == "rev" else "forward"}))
    return run


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except SystemExit:
        return True


def selftest() -> int:
    n_case = fails = 0

    def chk(name: str, cond: bool, detail: str = ""):
        nonlocal n_case, fails
        n_case += 1
        if cond:
            print("  ok   %s" % name)
        else:
            fails += 1
            print("  FAIL %s %s" % (name, detail))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # A：单任务 16032 帧 / bs8 = 2004 步每 epoch
        a = _mk_run(root, "runA", 16032, 8, "sweep_rev",
                    [(1000, "rev", 20, 0), (2000, "rev", 20, 0),
                     (3000, "rev", 20, 3), (4000, "rev", 20, 6)])
        # B：联合 30447 帧 / bs8 = 3805.875 步每 epoch
        b = _mk_run(root, "runB", 30447, 8, "sweep_bidir",
                    [(1000, "rev", 10, 0), (4000, "rev", 10, 1),
                     (7000, "rev", 10, 2), (8000, "rev", 10, 3),
                     (4000, "fwd", 10, 8)], subset=False)

        spe_a, prov_a = steps_per_epoch(a)
        chk("A steps/epoch = 2004", abs(spe_a - 2004.0) < 1e-9, str(spe_a))
        chk("A 出处写明 episodes_subset", "episodes_subset.n_frames=16032" in prov_a, prov_a)
        spe_b, prov_b = steps_per_epoch(b)
        chk("B steps/epoch = 3805.875", abs(spe_b - 30447 / 8) < 1e-9, str(spe_b))
        chk("B 回落到 dataset_total_frames", "dataset_total_frames=30447" in prov_b, prov_b)

        ra = read_curve(a, "sweep_rev", {"rev"})
        chk("A 读到 4 点", len(ra) == 4, str(len(ra)))
        for r in ra:
            r["ep"] = r["step"] / spe_a
        chk("A step4000 = 2.00 ep", abs(ra[-1]["ep"] - 4000 / 2004) < 1e-9)
        chk("A step4000 rate=30%", abs(ra[-1]["p"] - 0.30) < 1e-9)
        chk("A 1σ(6/20)≈10.2pp", abs(100 * ra[-1]["sigma"] - 10.25) < 0.1,
            str(100 * ra[-1]["sigma"]))

        rb = read_curve(b, "sweep_bidir", {"rev"})
        chk("B 只要 rev 时读到 4 点（fwd 被滤掉）", len(rb) == 4, str(len(rb)))
        for r in rb:
            r["ep"] = r["step"] / spe_b
        both = read_curve(b, "sweep_bidir", {"rev", "fwd"})
        chk("B both 时读到 5 点", len(both) == 5, str(len(both)))

        # 关键：step 号对齐是错的，epoch 对齐才对。
        chk("同 step 4000 的 epoch 不同（2.00 vs 1.05）",
            abs(ra[-1]["ep"] - 2.0) < 0.01 and abs([x for x in rb if x["step"] == 4000][0]["ep"] - 1.051) < 0.01)

        pairs = align(ra, rb)
        chk("对齐返回 4 对", len(pairs) == 4, str(len(pairs)))
        bystep = {x["step"]: y for x, y in pairs}
        # A step4000 = 2.00 ep；B 候选 epoch：1000/3806=0.26, 4000=1.05, 7000=1.84, 8000=2.10
        # 最近是 8000（|2.10-2.00|=0.10 < |1.84-2.00|=0.16）
        chk("A@2.00ep 对到 B step 8000（不是同号 4000）",
            bystep[4000] is not None and bystep[4000]["step"] == 8000,
            str(bystep[4000]["step"] if bystep[4000] else None))
        # A step3000 = 1.497 ep；最近是 7000（1.839，Δ0.342）vs 4000（1.051，Δ0.446）
        chk("A@1.50ep 对到 B step 7000", bystep[3000]["step"] == 7000,
            str(bystep[3000]["step"]))
        chk("A@0.50ep 对到 B step 1000（0.26 最近）", bystep[1000]["step"] == 1000)
        chk("并列时取更早 step", align(
            [{"dir": "rev", "ep": 1.0, "step": 100, "p": 0.5, "k": 5, "n": 10, "sigma": 0.1}],
            [{"dir": "rev", "ep": 0.9, "step": 900, "p": 0.4, "k": 4, "n": 10, "sigma": 0.1},
             {"dir": "rev", "ep": 1.1, "step": 1100, "p": 0.6, "k": 6, "n": 10, "sigma": 0.1}])[0][1]["step"] == 900)

        md = build([("revonly", a, "sweep_rev", None), ("joint", b, "sweep_bidir", None)],
                   {"rev"}, True)
        chk("markdown 含两条 run 表头", "## revonly" in md and "## joint" in md)
        chk("markdown 含对齐表", "epoch 对齐" in md and "Fisher p" in md)
        chk("steps/epoch 出处进 markdown", "episodes_subset.n_frames=16032" in md)
        chk("不是门的免责声明在", "趋势工具" in md)

        md3 = build([("x", a, "sweep_rev", None), ("y", b, "sweep_bidir", None),
                     ("z", a, "sweep_rev", None)], {"rev"}, True)
        chk("3 条 run 时 --align 优雅拒绝", "恰好 2 个" in md3)

        # 缺件：空 sweep 目录不崩；meta.json 缺失时报错而不是猜
        empty = root / "runEmpty"
        (empty / "sweep_rev").mkdir(parents=True)
        (root / "runEmpty_meta").mkdir(parents=True)
        (root / "runEmpty_meta" / "meta.json").write_text(json.dumps(
            {"batch_size": 8, "episodes_subset": {"n_frames": 8000}}))
        mde = build([("empty", empty, "sweep_rev", None)], {"rev"}, False)
        chk("空 sweep 输出'没有可用读数'", "没有可用读数" in mde)
        nom = root / "runNoMeta"
        (nom / "sweep_rev").mkdir(parents=True)
        try:
            steps_per_epoch(nom)
            chk("缺 meta.json 必须报错", False)
        except SystemExit as e:
            chk("缺 meta.json 必须报错", "--spe" in str(e), str(e))
        chk("--spe 覆盖时标注未校验", "未经 meta.json 校验" in build(
            [("ovr", a, "sweep_rev", 2000.0)], {"rev"}, False))

        # 老式 meta.json（无帧数字段，只有 dataset_root）-> 读数据集 info.json
        ds = root / "ds"
        (ds / "meta").mkdir(parents=True)
        (ds / "meta" / "info.json").write_text(json.dumps(
            {"total_episodes": 120, "total_frames": 30447}))
        old_run = root / "runOld"
        (old_run / "sweep_bidir").mkdir(parents=True)
        (root / "runOld_meta").mkdir(parents=True)
        (root / "runOld_meta" / "meta.json").write_text(json.dumps(
            {"batch_size": 8, "dataset_root": str(ds), "steps": 14400}))
        spe_o, prov_o = steps_per_epoch(old_run)
        chk("老 meta 回落到 info.json（3805.875）", abs(spe_o - 30447 / 8) < 1e-9, str(spe_o))
        chk("回落出处写明 info.json", "info.json" in prov_o and "total_frames=30447" in prov_o, prov_o)

        # 子集优先：同时有 episodes_subset 和 dataset_root 时必须用子集帧数
        sub_run = root / "runSub"
        (sub_run / "sweep_rev").mkdir(parents=True)
        (root / "runSub_meta").mkdir(parents=True)
        (root / "runSub_meta" / "meta.json").write_text(json.dumps(
            {"batch_size": 8, "dataset_root": str(ds),
             "episodes_subset": {"n_frames": 16032}}))
        spe_s, prov_s = steps_per_epoch(sub_run)
        chk("子集帧数优先于数据集全集（2004 而非 3806）",
            abs(spe_s - 2004.0) < 1e-9 and "episodes_subset" in prov_s, str(spe_s))
        chk("sig1(0.5,20)=11.2pp", abs(100 * sig1(0.5, 20) - 11.18) < 0.05)

        # 钉死 Fisher 的**参数语义**：用一个独立写法（直接枚举超几何）算参考值。
        # 这条就是为了抓「传失败数而不是试验数」那类静默错误 —— 传错了不报错、只给错 p。
        def fisher_ref(a, n1, b, n2):
            from math import comb
            tot = a + b
            lo, hi = max(0, tot - n2), min(n1, tot)
            w = {x: comb(n1, x) * comb(n2, tot - x) for x in range(lo, hi + 1)}
            den = sum(w.values())
            po = w[a] / den
            return min(1.0, sum(v / den for v in w.values() if v / den <= po + 1e-12))

        # 变量名刻意不用 a/b：selftest 里 a、b 是上面造出来的两条 run 路径，
        # 用同名循环变量会把它们覆盖成 int，后面的 build(...) 就炸在 'int' has no 'parent'。
        for (fa, fn1, fb, fn2) in [(6, 20, 2, 20), (3, 20, 1, 20), (0, 20, 0, 20),
                                   (39, 80, 12, 80), (30, 80, 30, 80)]:
            chk("fisher 语义钉死 (%d/%d vs %d/%d)" % (fa, fn1, fb, fn2),
                abs(fisher_two_sided(fa, fn1, fb, fn2) - fisher_ref(fa, fn1, fb, fn2)) < 1e-12)
        # 参考值来自 scipy.stats.fisher_exact([[6,14],[2,18]], alternative="two-sided")
        # = 0.23511623511623514，与本仓 mg_verdict_s2.fisher_two_sided 逐位相同（23:55 实测对过）。
        # 第一版这里硬写了个 0.1948（拍脑袋），被自测抓出来 —— 参考值必须是算出来的，不是记出来的。
        chk("6/20 vs 2/20 的 p = 0.23512（对齐 scipy）",
            abs(fisher_two_sided(6, 20, 2, 20) - 0.23511623511623514) < 1e-12,
            str(fisher_two_sided(6, 20, 2, 20)))
        chk("39/80 vs 12/80 显著（p<1e-4）", fisher_two_sided(39, 80, 12, 80) < 1e-4)
        chk("30/80 vs 30/80 p=1.0", abs(fisher_two_sided(30, 80, 30, 80) - 1.0) < 1e-12)

        # 逐 run 指定扫描目录（坑：全局 --sweep 会让另一条静默读成空表）
        chk("parse_run 两段式", parse_run("L:%s" % a) == ("L", a, ""), str(parse_run("L:%s" % a)))
        chk("parse_run 三段式带 SUB", parse_run("L:%s:sweep_bidir" % b)[2] == "sweep_bidir")
        chk("parse_run 缺 PATH 报错", _raises(lambda: parse_run("onlylabel")))
        md2 = build([("A", a, "sweep_rev", None), ("B", b, "sweep_bidir", None)],
                    {"rev"}, True)
        chk("两条 run 各自读到自己目录（对齐表非空）",
            "| rev | 4000 | 2.00 | 30.0% | 8000 |" in md2, md2[-500:])
        chk("错目录时确实读成空表（说明逐 run 指定是必需的）",
            "没有可用读数" in build([("B", b, "sweep_rev", None)], {"rev"}, False))
        chk("detect_sub 优先 sweep_rev", detect_sub(a) == "sweep_rev")
        chk("detect_sub 回落 sweep_bidir", detect_sub(b) == "sweep_bidir")

    print("\nselftest: %d/%d 通过" % (n_case - fails, n_case))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
