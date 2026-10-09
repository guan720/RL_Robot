#!/usr/bin/env python
"""档 3r · 反向任务训练 seed 稳健性判定（正向档 3 的同一道门，搬到反向 + 主口径换成放宽 R）。

要回答的唯一问题：**反向过门是不是 seed 运气？**
    反向至今只有一个训练 seed（1000）：档 2(1:1) 严格 37.5% → 档 2c(单任务) 45.0% →
    档 2e(2:1) 严格 52.5% / 放宽 68.8%。三档同 seed 不同数据、方向一致，但换个 seed 还成立吗没人答过。

预注册门（写在 chain_s3r_seed.sh 头注释，跑前定死）：
    **最差的那个 seed，放宽口径 ≥ 50%** ⇒ PASS（与正向档 3「最差 ≥50%」同一条规则）。
    严格口径 4×20 并列报，不参与门；两口径由同一次评测并行输出（不多花 GPU）。

护栏：每个 seed 各读一次正向未见（20 局）。2:1 配比把正向压到 1/3，必须证明没拆东墙补西墙。
    正向基线取档 3 的三个 seed（70.0% / 63.3% / 70.0%，合并 193/300 = 64.3%）；
    门沿用档 2 门 3 的口径：**掉幅 ≤15 pp**。

用法：
    $MG_PY code/mg_verdict_s3r.py
    $MG_PY code/mg_verdict_s3r.py --selftest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_verdict_s2 import fisher_two_sided  # noqa: E402
from mg_verdict_s2f import ci, collect, pct  # noqa: E402

GATE = 0.50
FWD_DROP_PP = 15.0
# 正向基线：档 3 三个训练 seed 的未见 TEST（各 60 局，见 README 链路状态第 20 行 / runs/s3_confirm.done）
FWD_BASELINE = (193, 300)

SEEDS = [
    # (训练 seed, 反向主读数 4×20, 正向护栏 1×20, 出处 run 目录)
    (1000, ["s2e_rev_test_rand20_k10", "s2e_rev_test_rand20_k10_rep2",
            "s2e_rev_test_rand20_k10_rep3", "s2e_rev_test_rand20_k10_rep4"],
     ["s2e_fwd_test_rand20_k10", "s2e_fwd_test_rand20_k10_rep2"], "pi05_mix60f120r_s2e"),
    (2000, ["s3r_seed2000_rev_test_rand20_k10", "s3r_seed2000_rev_test_rand20_k10_rep2",
            "s3r_seed2000_rev_test_rand20_k10_rep3", "s3r_seed2000_rev_test_rand20_k10_rep4"],
     ["s3r_seed2000_fwd_test_rand20_k10"], "pi05_mix60f120r_s3r_seed2000"),
    (3000, ["s3r_seed3000_rev_test_rand20_k10", "s3r_seed3000_rev_test_rand20_k10_rep2",
            "s3r_seed3000_rev_test_rand20_k10_rep3", "s3r_seed3000_rev_test_rand20_k10_rep4"],
     ["s3r_seed3000_fwd_test_rand20_k10"], "pi05_mix60f120r_s3r_seed3000"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    print("# 档 3r 判定：反向任务的训练 seed 稳健性")
    print()
    print("* 数据集 / 等 epoch 步数 / lr / warmup / batch / chunk_size / 基座 / K=10 / TEST 窗口 7000..7019")
    print("  全部相同，**唯一变量 = 训练 seed**（出处 `code/chain_s3r_seed.sh` 头注释）。")
    print("* 主口径 = 放宽 R（用户 2026-10-02：送到目标区为首要条件，侧躺算送到并打标）；严格并列。")
    print("* 门 = **最差 seed 的放宽口径 ≥ 50%**（与正向档 3 同规则）。")
    print()

    rows = []
    for sd, rdirs, fdirs, run in SEEDS:
        rs = collect(rdirs, "n_success", "pc_success")
        rr = collect(rdirs, "n_success_relaxed", "pc_success_relaxed")
        fw = collect(fdirs, "n_success", "pc_success")
        rows.append({"seed": sd, "run": run, "s": rs, "r": rr, "f": fw})

    print("## 一、三个训练 seed")
    print()
    print("| 训练 seed | run | 反向局数 | 严格 | **放宽 R（主口径）** | Wilson 95%（放宽） | 侧躺标记 | 正向护栏 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for x in rows:
        print("| %d | `%s` | %d | %d/%d = %s | **%d/%d = %s** | %s | %d | %s |"
              % (x["seed"], x["run"], x["r"]["n"],
                 x["s"]["k"], x["s"]["n"], pct(x["s"]["k"], x["s"]["n"]),
                 x["r"]["k"], x["r"]["n"], pct(x["r"]["k"], x["r"]["n"]),
                 ci(x["r"]["k"], x["r"]["n"]), x["r"]["tipped"],
                 pct(x["f"]["k"], x["f"]["n"])))
    print()
    for x in rows:
        for tag, c in (("严格", x["s"]), ("放宽", x["r"]), ("正向护栏", x["f"])):
            if c["missing"]:
                print("* ⚠️ seed %d [%s] 缺产物 %d 读：%s（不计入，**不当 0**）"
                      % (x["seed"], tag, len(c["missing"]), ", ".join(c["missing"])))
            for d, why in c["nofield"]:
                print("* ⚠️ seed %d [%s] `%s`：%s ⇒ 剔除，不当 0" % (x["seed"], tag, d, why))
            for d, why in c["broken"]:
                print("* 🚫 seed %d [%s] `%s` 不变量破了：%s ⇒ 作废" % (x["seed"], tag, d, why))
    print()

    have = [x for x in rows if x["r"]["n"]]
    print("## 二、seed 间差异")
    print()
    if len(have) < 2:
        print("* 有读数的 seed 不足 2 个 ⇒ 差异无法计算，本节**悬空**。")
    else:
        for i in range(len(have)):
            for j in range(i + 1, len(have)):
                A, B = have[i], have[j]
                dpp = 100.0 * (A["r"]["k"] / A["r"]["n"] - B["r"]["k"] / B["r"]["n"])
                p = fisher_two_sided(A["r"]["k"], A["r"]["n"], B["r"]["k"], B["r"]["n"])
                print("* 放宽口径 seed %d（%s）vs seed %d（%s）：Δ=%+.1f pp，Fisher p=%.4f%s"
                      % (A["seed"], pct(A["r"]["k"], A["r"]["n"]),
                         B["seed"], pct(B["r"]["k"], B["r"]["n"]), dpp, p,
                         "（显著）" if p < 0.05 else "（不显著）"))
                ds = 100.0 * ((A["s"]["k"] / A["s"]["n"] if A["s"]["n"] else 0)
                              - (B["s"]["k"] / B["s"]["n"] if B["s"]["n"] else 0))
                print("  严格口径同一对：Δ=%+.1f pp（并列参考，不参与门）" % ds)
        print()
        print("* 不显著读作「没测出 seed 差异」，**不是**「证明了 seed 无关」；")
        print("  n=80/seed 时 1σ≈5.6 pp，要判出 10 pp 的差大约需要 n≥300/seed。")
    print()

    print("## 三、护栏：正向未见（2:1 把正向压到 1/3，必须证明没拆东墙补西墙）")
    print()
    bk, bn = FWD_BASELINE
    print("* 正向基线（出处：档 3 三个训练 seed 各 60 局，合并 %d/%d = %s）；门 = 掉幅 ≤%.0f pp"
          % (bk, bn, pct(bk, bn), FWD_DROP_PP))
    for x in rows:
        if not x["f"]["n"]:
            print("* seed %d：正向护栏无产物 ⇒ 悬空" % x["seed"])
            continue
        drop = 100.0 * (bk / bn - x["f"]["k"] / x["f"]["n"])
        p = fisher_two_sided(x["f"]["k"], x["f"]["n"], bk, bn)
        print("* seed %d 正向 %s vs 基线 %s ⇒ 掉 %.1f pp，Fisher p=%.4g ⇒ %s"
              % (x["seed"], pct(x["f"]["k"], x["f"]["n"]), pct(bk, bn), drop, p,
                 "✅ 护栏通过" if drop <= FWD_DROP_PP else "🚫 护栏不过（掉幅超门）"))
    print()

    print("## 四、判定（预注册：最差 seed 放宽 ≥ 50%）")
    print()
    broken = [b for x in rows for c in (x["s"], x["r"]) for b in c["broken"]]
    if broken:
        print("🚫 **全部结论作废**：%d 处读数破了 严格 ⊆ 放宽 不变量 ⇒ 判据实现有 bug，先修再读。" % len(broken))
    elif not have:
        print("* **悬空**：一个 seed 的放宽读数都没有（chain_s3r_seed.sh 还没跑到）。")
    elif len(have) < len(SEEDS):
        print("* ⚠️ 只有 %d/%d 个 seed 有读数 ⇒ 下面是**中途判读**，不是终局。" % (len(have), len(SEEDS)))
        _verdict(have)
    else:
        _verdict(have)
    print()
    print("## 五、复现")
    print()
    print("```bash")
    print("bash code/chain_s3r_seed.sh        # 等 s2e.done + 判定非 P3 才发车；seed 2000/3000 各 22000 步")
    print("$MG_PY code/mg_verdict_s3r.py --selftest")
    print("```")
    return 0


def _verdict(have: list[dict]) -> None:
    worst = min(have, key=lambda x: x["r"]["k"] / x["r"]["n"])
    rate = worst["r"]["k"] / worst["r"]["n"]
    wrst_s = min((x for x in have if x["s"]["n"]), key=lambda x: x["s"]["k"] / x["s"]["n"], default=None)
    print("* 最差 seed = **%d**，放宽口径 %d/%d = %s（Wilson 95%% %s）"
          % (worst["seed"], worst["r"]["k"], worst["r"]["n"], pct(worst["r"]["k"], worst["r"]["n"]),
             ci(worst["r"]["k"], worst["r"]["n"])))
    if wrst_s:
        print("* 同一批 rollout 的严格口径最差 seed = %d，%s（并列，不参与门）"
              % (wrst_s["seed"], pct(wrst_s["s"]["k"], wrst_s["s"]["n"])))
    if rate >= GATE:
        print("* ✅ **PASS**：最差 seed 也过 %.0f%% 门 ⇒ 反向能力对训练 seed **稳健**，"
              "档 2e 的过门不是 seed 运气。" % (100 * GATE))
        print("  下一步：档 4r（反向 K 曲线，已在跑）→ 档 5（Harness 接管，按 K=10 / 50 ms 预算设计）。")
    else:
        print("* ❌ **FAIL**：最差 seed %s < %.0f%% ⇒ 反向过门含 seed 运气成分。"
              % (pct(worst["r"]["k"], worst["r"]["n"]), 100 * GATE))
        print("  处方：先看崩掉那个 seed 的 val 曲线（命令在 chain_s3r_seed.sh 的 note 里），")
        print("  区分「训崩了」与「本来就在门附近抖」；再决定多 seed 集成 / 加数据 / 修 A 类抓空。")


def selftest() -> int:
    fails, n = [], 0

    def chk(c, m):
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    import json
    import tempfile
    import mg_verdict_s2f as S2F

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # collect()/ci()/pct() 都是 mg_verdict_s2f 的函数，它们查的是 **s2f 的** 模块级 RUNS；
        # 只换本模块的名字没用（本模块根本没绑 RUNS）—— 2026-10-02 实测 AttributeError。
        old = S2F.RUNS
        S2F.RUNS = root

        def mk(name, ne, ns, nr=None, tip=0):
            d = root / name
            d.mkdir(parents=True, exist_ok=True)
            j = {"episodes": ne, "n_success": ns, "pc_success": ns / ne,
                 "per_episode": [{"seed": 7000 + i, "success": i < ns,
                                  "success_relaxed": i < (nr if nr is not None else ns),
                                  "delivered_tipped": False} for i in range(ne)]}
            if nr is not None:
                j.update({"n_success_relaxed": nr, "pc_success_relaxed": nr / ne,
                          "n_delivered_tipped": tip})
            (d / "eval_summary.json").write_text(json.dumps(j))

        try:
            # 四读合并（档 2e 的真实数字：严格 8/12/11/11、放宽 12/14/13/16）
            for r, ks, kr in (("", 8, 12), ("_rep2", 12, 14), ("_rep3", 11, 13), ("_rep4", 11, 16)):
                mk("s2e_rev_test_rand20_k10" + r, 20, ks, kr, kr - ks)
            c = collect(["s2e_rev_test_rand20_k10", "s2e_rev_test_rand20_k10_rep2",
                         "s2e_rev_test_rand20_k10_rep3", "s2e_rev_test_rand20_k10_rep4"],
                        "n_success_relaxed", "pc_success_relaxed")
            chk((c["k"], c["n"]) == (55, 80), "四读合并放宽应 55/80，实得 %d/%d" % (c["k"], c["n"]))
            cs = collect(["s2e_rev_test_rand20_k10", "s2e_rev_test_rand20_k10_rep2",
                          "s2e_rev_test_rand20_k10_rep3", "s2e_rev_test_rand20_k10_rep4"],
                         "n_success", "pc_success")
            chk((cs["k"], cs["n"]) == (42, 80), "四读合并严格应 42/80，实得 %d/%d" % (cs["k"], cs["n"]))
            chk(c["tipped"] == 13, "侧躺标记应合计 13，实得 %d" % c["tipped"])
            chk(c["k"] - cs["k"] == c["tipped"], "不变量：放宽-严格 必须 == 侧躺标记数（配对检验的 b）")
            # 最差 seed 的选法：造一个明显低的
            mk("low1", 20, 5, 9, 4)
            mk("high1", 20, 12, 16, 4)
            lo = collect(["low1"], "n_success_relaxed", "pc_success_relaxed")
            hi = collect(["high1"], "n_success_relaxed", "pc_success_relaxed")
            worst = min([lo, hi], key=lambda x: x["k"] / x["n"])
            chk(worst is lo, "最差 seed 应选 9/20 那一组")
            chk(9 / 20 < GATE, "9/20=45% 应判 FAIL")
            chk(16 / 20 >= GATE, "16/20=80% 应判 PASS")
            # 门是 ≥ 不是 >：恰好 50% 要过
            chk(10 / 20 >= GATE, "10/20=50% 恰好过门（≥）")
            chk(9 / 20 < GATE, "9/20 不过门")
            # 缺字段 ≠ 0
            mk("oldfmt", 20, 9)
            c2 = collect(["oldfmt"], "n_success_relaxed", "pc_success_relaxed")
            chk(c2["n"] == 0 and len(c2["nofield"]) == 1,
                "无放宽字段的旧产物必须剔除而不是当 0：n=%r nofield=%r" % (c2["n"], c2["nofield"]))
        finally:
            S2F.RUNS = old

    # 正向基线出处钉子：193/300 = 64.3%（档 3：70.0% + 63.3% + 70.0%，各 60 局）
    chk(FWD_BASELINE == (193, 300), "正向基线漂了：%r" % (FWD_BASELINE,))
    chk(abs(193 / 300 - 0.6433333333333333) < 1e-12, "193/300 应 = 64.33%")
    chk(pct(193, 300) == "64.3%", "pct(193,300) 应 64.3%%，实得 %r" % pct(193, 300))
    # 掉幅门：正向 55% vs 基线 64.3% = 掉 9.3 pp ⇒ 过；掉到 45% = 19.3 pp ⇒ 不过
    chk(100 * (193 / 300 - 0.55) <= FWD_DROP_PP, "55% 应在 15 pp 门内")
    chk(100 * (193 / 300 - 0.45) > FWD_DROP_PP, "45% 应超 15 pp 门")
    # Fisher 语义再钉一次（坑 35）
    chk(abs(fisher_two_sided(6, 20, 2, 20) - 0.23511623511623514) < 1e-12, "fisher 参考值漂了")

    print("档3r 判定工具钉子：%d 项检查，%d 项失败" % (n, len(fails)))
    for f in fails[:20]:
        print("  FAIL " + f)
    if fails:
        print("SELFTEST FAIL")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
