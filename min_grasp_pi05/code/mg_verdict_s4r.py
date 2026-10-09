#!/usr/bin/env python
"""档 4r · 反向 chunk 执行（K 曲线）判定汇编。

复用档 2f 的合并/区间/检验函数（同一套语义、同一套钉子），只加两件本档特有的事：
  1. 把 K=10（档 2e 的 4×20 关门读数）当**工作点**，其余 K 都对它做 Fisher；
  2. 从每读的 `seconds` 与逐局 `steps` 现算 **ms/step**，对着 50 ms 实时预算判「可不可部署」
     —— 但必须同时说明：本档的读数是**与训练/其它评测并发**跑出来的，墙钟被拉长，
     所以 ms/step 只作量级参考；定版的实时结论在档 4（正向）那边，见 README 链路状态第 20 行。

用法：
    $MG_PY code/mg_verdict_s4r.py
    $MG_PY code/mg_verdict_s4r.py --selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_verdict_s2 import fisher_two_sided  # noqa: E402
from mg_verdict_s2f import RUNS, ci, collect, mcnemar_nested, pct, wilson  # noqa: E402

GATE = 0.50
REALTIME_BUDGET_MS = 50.0        # 出处：档 4（README 链路状态），控制周期 20 Hz ⇒ 50 ms/step
DROP_PP = 20.0                   # 预注册：相对 K=10 掉 ≥20 pp 判「与正向同一条曲线」

# K=10 的工作点读数 = 档 2e 的关门 4×20（同一检查点 022000、同一 TEST 窗口），**不重跑**
KPOINT = {
    10: ["s2e_rev_test_rand20_k10", "s2e_rev_test_rand20_k10_rep2",
         "s2e_rev_test_rand20_k10_rep3", "s2e_rev_test_rand20_k10_rep4"],
    1: ["s4r_rev_test_rand20_k1"],
    25: ["s4r_rev_test_rand20_k25"],
    50: ["s4r_rev_test_rand20_k50"],
}


def ms_per_step(dirs: list[str]) -> tuple[float, int]:
    """从产物现算墙钟 ms/step。返回 (ms/step, 总步数)；缺产物返回 (nan, 0)。"""
    tot_s = 0.0
    tot_n = 0
    for d in dirs:
        f = RUNS / d / "eval_summary.json"
        if not f.is_file():
            continue
        try:
            j = json.loads(f.read_text())
        except Exception:
            continue
        n = sum(int(e.get("steps", 0)) for e in j.get("per_episode", []))
        if n and j.get("seconds"):
            tot_s += float(j["seconds"])
            tot_n += n
    if not tot_n:
        return (float("nan"), 0)
    return (1000.0 * tot_s / tot_n, tot_n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    print("# 档 4r 判定：反向任务的 chunk 执行（K 曲线）")
    print("# 产物根目录：%s" % RUNS)
    print()
    print("* 检查点：档 2e `last`（022000，60 正向 + 120 反向、2:1、3.79 epoch）。唯一变量 = K。")
    print("* TEST 窗口 seed 7000..7019；K=10 用档 2e 的关门 4×20 = 80 局（不重跑），其余 K 各 20 局。")
    print("* 主口径 = **放宽 R**（用户 2026-10-02）；严格口径并列。上界同口径：放宽 100% / 严格 70%。")
    print()

    data = {}
    for k, dirs in sorted(KPOINT.items()):
        data[k] = {"s": collect(dirs, "n_success", "pc_success"),
                   "r": collect(dirs, "n_success_relaxed", "pc_success_relaxed")}
        data[k]["ms"], data[k]["nsteps"] = ms_per_step(dirs)

    print("## 一、K 曲线")
    print()
    print("| K | 局数 | 严格 | 放宽 R（主口径） | Wilson 95%%（放宽） | 侧躺标记 | 墙钟 ms/step | 实时（≤%.0f ms） |"
          % REALTIME_BUDGET_MS)
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for k in sorted(data):
        s, r = data[k]["s"], data[k]["r"]
        ms = data[k]["ms"]
        rt = "—" if ms != ms else ("✅" if ms <= REALTIME_BUDGET_MS else "❌ 超预算 %.1f×"
                                    % (ms / REALTIME_BUDGET_MS))
        print("| %d%s | %d | %d/%d = %s | **%d/%d = %s** | %s | %d | %s | %s |"
              % (k, "（工作点）" if k == 10 else "", r["n"],
                 s["k"], s["n"], pct(s["k"], s["n"]),
                 r["k"], r["n"], pct(r["k"], r["n"]), ci(r["k"], r["n"]), r["tipped"],
                 "—" if ms != ms else "%.1f" % ms, rt))
    print()
    for k in sorted(data):
        for tag, c in (("严格", data[k]["s"]), ("放宽", data[k]["r"])):
            if c["missing"]:
                print("* ⚠️ K=%d [%s] 缺产物 %d 读：%s（不计入，**不当 0**）"
                      % (k, tag, len(c["missing"]), ", ".join(c["missing"])))
            for d, why in c["broken"]:
                print("* 🚫 K=%d [%s] `%s` 不变量破了：%s ⇒ 作废" % (k, tag, d, why))
    print()
    print("* ⚠️ 墙钟 ms/step 是**与训练/其它评测并发**跑出来的，被拉长过 ⇒ 只作量级参考。")
    print("  定版的实时结论在档 4（正向）：K=1 超预算 6.5 倍不可部署、K=10 是唯一「又准又实时」的点。")
    print("  另见坑 36：K<10 不是实时的，别指望用调 K 去修 A 类抓空。")
    print()

    print("## 二、对 K=10 工作点的检验（放宽口径为主）")
    print()
    base = data[10]["r"]
    if not base["n"]:
        print("* 🚫 工作点 K=10 没有读数 ⇒ 本档**悬空**，下面全部不作数")
    else:
        for k in sorted(data):
            if k == 10:
                continue
            r = data[k]["r"]
            if not r["n"]:
                print("* K=%d：无产物 ⇒ 跳过" % k)
                continue
            dpp = 100.0 * (r["k"] / r["n"] - base["k"] / base["n"])
            p = fisher_two_sided(r["k"], r["n"], base["k"], base["n"])
            print("* K=%d 放宽 %s vs K=10 放宽 %s：Δ=%+.1f pp，Fisher 双侧 p=%.4f%s"
                  % (k, pct(r["k"], r["n"]), pct(base["k"], base["n"]), dpp, p,
                     "（显著）" if p < 0.05 else "（不显著）"))
            print("  ⚠️ n=%d vs %d，1σ 量级 ~%d pp；不显著读作「没测出差别」，不是「证明了没差别」。"
                  % (r["n"], base["n"], round(100 * 0.5 ** 0.5 * (1 / r["n"] + 1 / base["n"]) ** 0.5)))
        print()

    print("## 三、判定（预注册规则见 chain_s4r_kcurve.sh 头注释）")
    print()
    if not base["n"]:
        print("* **悬空**：K=10 工作点无读数。")
    else:
        br = base["k"] / base["n"]
        concl = []
        for k in (25, 50):
            r = data[k]["r"]
            if not r["n"]:
                concl.append("K=%d 无产物 ⇒ 该格悬空" % k)
                continue
            dpp = 100.0 * (br - r["k"] / r["n"])
            if dpp >= DROP_PP:
                concl.append("K=%d 相对工作点掉 %.1f pp（≥%.0f pp）⇒ 开环 chunk 执行不行，"
                             "与正向同一条曲线" % (k, dpp, DROP_PP))
            else:
                concl.append("K=%d 相对工作点只差 %.1f pp（<%.0f pp）⇒ 这一格没看出塌陷"
                             % (k, dpp, DROP_PP))
        r1 = data[1]["r"]
        if r1["n"]:
            dpp = 100.0 * (r1["k"] / r1["n"] - br)
            concl.append("K=1 全闭环 %s，比工作点 %+.1f pp ⇒ %s"
                         % (pct(r1["k"], r1["n"]), dpp,
                            "反向也吃「纠偏密度」，但 K=1 不可部署，只作能力上限参考"
                            if dpp >= 10 else "与工作点打平，反向不额外依赖逐步纠偏"))
        else:
            concl.append("K=1 无产物 ⇒ 能力上限参考悬空")
        for c in concl:
            print("* %s" % c)
        print()
        print("* 工作点结论：K=10 放宽 %s（门 ≥%.0f%% ⇒ %s），Wilson 95%% %s"
              % (pct(base["k"], base["n"]), 100 * GATE,
                 "✅ 过门" if br >= GATE else "❌ 未过门", ci(base["k"], base["n"])))
        print("* 档 5（Harness 接管）按 **K=10 / 50 ms 预算**设计，不要按 K=1。")
    print()
    print("## 四、复现")
    print()
    print("```bash")
    print("bash code/chain_s4r_kcurve.sh     # K=1/25/50 各 20 局（K=10 沿用档 2e 的 4×20）")
    print("$MG_PY code/mg_verdict_s4r.py --selftest")
    print("```")
    return 0


def selftest() -> int:
    fails, n = [], 0

    def chk(c, m):
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    # ms_per_step：造产物核对算术
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for nm, secs, steps in (("a", 100.0, [400, 400]), ("b", 50.0, [200])):
            (root / nm).mkdir()
            (root / nm / "eval_summary.json").write_text(json.dumps(
                {"seconds": secs, "per_episode": [{"steps": s} for s in steps]}))
        import mg_verdict_s4r as M
        old = M.RUNS
        M.RUNS = root
        try:
            ms, tot = M.ms_per_step(["a", "b"])
            chk(abs(ms - 150.0 * 1000 / 1000) < 1e-9, "ms/step 应为 (100+50)s/1000 步 = 150.0，实得 %r" % ms)
            chk(tot == 1000, "总步数应 1000，实得 %r" % tot)
            ms2, tot2 = M.ms_per_step(["gone"])
            chk(ms2 != ms2 and tot2 == 0, "缺产物要 nan/0 而不是崩：%r %r" % (ms2, tot2))
        finally:
            M.RUNS = old

    # 复用的语义钉子在这里再钉一遍，防止上游改了签名这边静默算错
    chk(abs(wilson(14, 20)[1] - 0.8545227551323956) < 1e-12, "wilson(14,20) 上界漂了")
    chk(abs(fisher_two_sided(6, 20, 2, 20) - 0.23511623511623514) < 1e-12, "fisher 参考值漂了")
    chk(abs(mcnemar_nested(8) - 0.0078125) < 1e-12, "mcnemar(8) 参考值漂了")
    chk(pct(42, 80) == "52.5%", "pct(42,80) 应为 52.5%%，实得 %r" % pct(42, 80))
    chk(pct(0, 0) == "—", "pct 零分母要给破折号")
    # 实时预算判定的算术
    chk(abs(65.0 / REALTIME_BUDGET_MS - 1.3) < 1e-9, "65ms 应为预算的 1.3 倍")

    print("档4r 判定工具钉子：%d 项检查，%d 项失败" % (n, len(fails)))
    for f in fails[:20]:
        print("  FAIL " + f)
    if fails:
        print("SELFTEST FAIL")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
