#!/usr/bin/env python
"""档 2c 判定：反向单任务消融 vs 档 2 联合模型，回答「反向是不是被正向挤掉的」。

判定规则与 chain_s2c.sh 头注释里**预注册**的那份逐字一致（R1/R2/R3 + 护栏 G1/G2）。
规则写在跑之前、代码只是把它执行一遍 —— 这样事后无论结果朝哪个方向，都不会出现
「换个阈值就过门」的操作。显著性一律用 Fisher 精确检验（复用 mg_verdict_s2 里那份
已对着 scipy 校验过的实现），不用拍脑袋的百分点阈值（档 2 在这上面吃过一次误报）。

用法：
    bash -c 'source code/env.sh && $MG_PY code/mg_verdict_s2c.py'
    bash -c 'source code/env.sh && $MG_PY code/mg_verdict_s2c.py --selftest'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from mg_verdict_s2 import RUNS as _DEFAULT_RUNS  # noqa: E402
from mg_verdict_s2 import fisher_two_sided  # noqa: E402

RUNS = Path(os.environ.get("MG_RUNS", str(_DEFAULT_RUNS)))

GATE = 0.50              # 与档 2 门 2 同一个门：反向未见 ≥50%
# 联合基线 = 档 2 门那两读（40 局）+ 本档补的两读（40 局），同一个 `last` 检查点、同一批 TEST seed。
# 为什么要补：门那两读只有 40 局，而本档要和它做 Fisher 比较。n=40 vs n=60 时，
# 32.5%→50% 这种**正是我们要判的**差距只有 ~50% 的把握达到显著 —— 判不出就等于白跑 4 小时。
# 两边都加到 80 局，才谈得上「显著/不显著」。补读产物用 s2c_jointbase_* 前缀，
# 免得被 mg_verdict_s2.py 的档 2 门组误收（那边只认显式列出的两个目录）。
JOINT_LAST = ["s2_gate_rev_test_rand20_k10", "s2_gate_rev_test_rand20_k10_rep2",
              "s2c_jointbase_rev_test_rand20_k10_rep3", "s2c_jointbase_rev_test_rand20_k10_rep4"]
JOINT_VALSEL = ["s2fix_rev_test_rand20_k10", "s2fix_rev_test_rand20_k10_rep2",
                "s2fix_rev_test_rand20_k10_rep3"]
S2C_LAST = ["s2c_rev_test_rand20_k10", "s2c_rev_test_rand20_k10_rep2",
            "s2c_rev_test_rand20_k10_rep3", "s2c_rev_test_rand20_k10_rep4"]
S2C_VALSEL = ["s2c_revsel_test_rand20_k10", "s2c_revsel_test_rand20_k10_rep2",
              "s2c_revsel_test_rand20_k10_rep3"]
G1_FWD_ZEROSHOT = "s2c_fwd_zeroshot_rand20_k10"
G2_REV_CTRL = "s2c_rev_control_train10_k10"
G1_MAX_SUCC = 2          # 正向零样本最多允许 2/20；再多就说明子集过滤没生效
MEMO_MIN_PP = 10.0
RUN_DIR = "pi05_rev60_s2c"


def pool(dirs: list[str]) -> tuple[int, int, list[str]]:
    """把若干次读数合并成 (成功数, 局数, 逐次读数字符串列表)。缺产物的跳过。"""
    ns = ne = 0
    reads = []
    for i, d in enumerate(dirs, 1):
        f = RUNS / d / "eval_summary.json"
        if not f.exists():
            reads.append(f"#{i}:MISSING")
            continue
        try:
            j = json.loads(f.read_text())
        except Exception:
            reads.append(f"#{i}:BAD_JSON")
            continue
        ns += int(j["n_success"])
        ne += int(j["episodes"])
        reads.append(f"#{i}:{j['n_success']}/{j['episodes']}={j['pc_success']*100:.0f}%")
    return ns, ne, reads


def one(d: str) -> tuple[int, int]:
    ns, ne, _ = pool([d])
    return ns, ne


def fmt(ns: int, ne: int) -> str:
    return f"{ns}/{ne} = {ns/ne*100:.1f}%" if ne else "MISSING"


def decide(p_rev, n_rev, p_joint, n_joint, g1_state, g1_txt, g2_txt, g2_bad) -> list[str]:
    """执行预注册规则，返回判定行。

    g1_state ∈ {"missing", "ok", "bad"} —— 三态而不是布尔：
    「护栏产物还没跑出来」和「护栏跑出来但不合格」是两件完全不同的事，
    前者只能说「判定悬空」，后者才是「结论作废」。第一版用布尔，
    训练还在跑、产物自然缺失时就打印「❌ 全部结论作废」，是个会吓人的假报警。
    """
    out = [f"* 护栏 G1 正向零样本：{g1_txt}", f"* 护栏 G2 记忆对照：{g2_txt}"]
    if g1_state == "missing":
        out.append("* ⏳ 护栏 G1 的产物还没到 ⇒ 现在**无法确认**子集过滤是否生效，R1/R2/R3 悬空。"
                   "等 `runs/s2c_fwd_zeroshot_rand20_k10/` 落盘后重跑本工具。")
        return out
    if g1_state == "bad":
        out.append("* ❌ **护栏 G1 不成立** ⇒ 子集过滤没生效，本档训的其实还是联合模型，"
                   "**全部结论作废**，先修 `--dataset.episodes` 再重跑。")
        return out
    if g2_bad:
        out.append("* ⚠️ 护栏 G2 报警：训练 seed 显著优于未见 seed ⇒ 读数里混了记忆成分，"
                   "先看 G2 的局数够不够再下结论。")
    if p_rev is None or n_rev == 0:
        out.append("* ⏳ 主读数还没到，无法判 R1/R2/R3。")
        return out
    if p_joint is None or n_joint == 0:
        out.append("* ⏳ 档 2 联合基线缺产物，无法做显著性比较。")
        return out
    pv = fisher_two_sided(p_rev, n_rev, p_joint, n_joint)
    diff = (p_rev / n_rev - p_joint / n_joint) * 100
    sig = pv < 0.05
    out.append(f"* 单任务 {p_rev/n_rev*100:.1f}% vs 联合 {p_joint/n_joint*100:.1f}%"
               f" ⇒ 差 {diff:+.1f} pp，Fisher 双侧 p={pv:.3f}"
               f"（{'**显著**' if sig else '不显著'}）")
    passes = p_rev / n_rev >= GATE
    if sig and diff > 0 and passes:
        out.append("* ✅ **R1 干扰确认**：去掉正向数据后反向显著变好且过门 ⇒ 反向本身学得会，"
                   "档 2 的失败是**多任务干扰**。处方 = 改数据配比/采样（或分开训再合并），"
                   "**不是**「反向任务不可能」，也不必先无脑堆到 120 条。")
    elif sig and diff > 0:
        out.append("* ⚠️ **R3 干扰存在但不足以过门**：显著变好但仍未达 50% ⇒ 配比和反向数据量"
                   "两件事都要做（先调配比，再按 STAGE_PLAN 的 120 条预案加数据）。")
    elif not sig:
        out.append("* ❌ **R2 不是干扰**：去掉正向数据后反向没有显著变好 ⇒ 瓶颈在反向任务本身"
                   "（bin 内抓取的运动学极限 + 「立着保持 10 步」的判据；专家自己也只有 70%）。"
                   "处方 = 加反向数据 / 改示范 / 复核成功判据口径，**改配比没用**。")
    else:
        out.append("* ❌ 单任务**反而显著更差**：这不是干扰能解释的，先查子集过滤、"
                   "等 epoch 步数与 normalizer 是否真的与档 2 一致，别急着下结论。")
    return out


def curve(run_dir: Path, sub: str = "sweep_rev") -> str:
    d = run_dir / sub
    if not d.is_dir():
        return "（无 val 扫描产物）"
    rows = []
    for p in sorted(d.glob("step_*_rev/eval_summary.json"),
                    key=lambda x: int(x.parent.name.split("_")[1])):
        try:
            j = json.loads(p.read_text())
        except Exception:
            continue
        rows.append(f"{p.parent.name.split('_')[1]}:{j['n_success']}/{j['episodes']}")
    return "  ".join(rows) if rows else "（val 扫描还没出数）"


def main() -> int:
    print("# 档 2c 判定：反向单任务消融（干扰 vs 任务本身难）")
    print(f"# 产物根目录：{RUNS}")

    jl_s, jl_n, jl_r = pool(JOINT_LAST)
    jv_s, jv_n, jv_r = pool(JOINT_VALSEL)
    rl_s, rl_n, rl_r = pool(S2C_LAST)
    rv_s, rv_n, rv_r = pool(S2C_VALSEL)

    print("\n## 一、读数\n")
    print("| 组 | 口径 | 逐次读数 | 合并 |")
    print("| --- | --- | --- | --- |")
    print(f"| 档2 联合 @last | 反向 TEST 7000..7019 K=10 | {' '.join(jl_r)} | **{fmt(jl_s, jl_n)}** |")
    print(f"| 档2 联合 @val选点011000 | 同上 | {' '.join(jv_r)} | **{fmt(jv_s, jv_n)}** |")
    print(f"| 档2c 单任务 @last | 同上（**主读数**） | {' '.join(rl_r)} | **{fmt(rl_s, rl_n)}** |")
    if rv_n:
        print(f"| 档2c 单任务 @val选点 | 同上（并列） | {' '.join(rv_r)} | **{fmt(rv_s, rv_n)}** |")
    print(f"\n* 专家上界（同 20 个 TEST seed，noise=0.05）：**14/20 = 70%**，"
          "6 局失败全是 can 侧躺（final_tilt≈90°）")
    if jl_n and jv_n:
        pv0 = fisher_two_sided(jl_s, jl_n, jv_s, jv_n)
        print(f"* 联合模型两个选点规则的读数：@last {fmt(jl_s, jl_n)} vs @val选点 {fmt(jv_s, jv_n)}"
              f" ⇒ Fisher 双侧 p={pv0:.2f}（{'差异不显著 ⇒ 基线对「选点规则」不敏感' if pv0 >= 0.05 else '**差异显著**'}）。"
              " 主比较对象取 **@last**（与档 2c 的主读数同规则、等 epoch）。")
    print(f"* 反向 val 学习曲线（20 局/点）：{curve(RUNS / RUN_DIR)}")

    g1_s, g1_n = one(G1_FWD_ZEROSHOT)
    if g1_n == 0:
        g1_state, g1_txt = "missing", "MISSING（正向零样本对照还没跑）"
    elif g1_s <= G1_MAX_SUCC:
        g1_state = "ok"
        g1_txt = (f"{fmt(g1_s, g1_n)}（门槛 ≤{G1_MAX_SUCC}/{g1_n}）⇒ "
                  "✅ 子集过滤生效，模型确实没见过正向")
    else:
        g1_state = "bad"
        g1_txt = (f"{fmt(g1_s, g1_n)}（门槛 ≤{G1_MAX_SUCC}/{g1_n}）⇒ "
                  "❌ 正向也能成，子集过滤可疑")

    g2_s, g2_n = one(G2_REV_CTRL)
    g2_bad = False
    if g2_n and rl_n:
        pv2 = fisher_two_sided(g2_s, g2_n, rl_s, rl_n)
        d2 = (g2_s / g2_n - rl_s / rl_n) * 100
        g2_bad = bool(pv2 < 0.05 and d2 > MEMO_MIN_PP)
        g2_txt = (f"训练 seed {fmt(g2_s, g2_n)} vs 未见 TEST {fmt(rl_s, rl_n)} ⇒ {d2:+.1f} pp，"
                  f"Fisher p={pv2:.3f}（{'⚠️ 显著' if g2_bad else '无显著记忆'}）")
    else:
        g2_txt = "MISSING（反向训练 seed 对照还没跑）"

    print("\n## 二、护栏与判定（规则见 chain_s2c.sh 头注释，跑前预注册）\n")
    # 主比较对象 = 档 2 联合 @last（同规则、等 epoch）；联合两个读数一致，所以这个选择不动摇结论
    for line in decide(rl_s, rl_n, jl_s, jl_n, g1_state, g1_txt, g2_txt, g2_bad):
        print(line)

    print("\n## 三、下一步（按判定分支，只走一条）\n")
    if g1_state == "missing":
        print("* 等 G1（正向零样本对照）与主读数落盘，再重跑本工具出判定。")
    elif g1_state == "bad":
        print("* 修子集过滤 → 重跑档 2c。别的都先别动。")
    elif rl_n == 0:
        print("* 等主读数的 3×20 局跑完再看。")
    else:
        pv = fisher_two_sided(rl_s, rl_n, jl_s, jl_n) if (jl_n and rl_n) else 1.0
        diff = (rl_s / rl_n - jl_s / jl_n) * 100 if (jl_n and rl_n) else 0.0
        if pv < 0.05 and diff > 0:
            print("* R1/R3 分支：先做**数据配比**（反向:正向 = 2:1 或分开训再合并），"
                  "再决定要不要按 STAGE_PLAN 的 120 条预案加数据。")
        else:
            print("* R2 分支：走 STAGE_PLAN 档 2 失败预案（反向加到 120 条 + 等 epoch 重训 ~24600 步），"
                  "同时复核 C 类失败（送到却侧躺）——专家也栽在这里，可能是**判据**而不是策略。")
    return 0


# ── 自测：判定规则本身必须被测到（这是门；门判错比没门更糟）──────────────────
def _mk(root: Path, name: str, ns: int, ne: int):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "eval_summary.json").write_text(json.dumps({
        "n_success": ns, "episodes": ne, "pc_success": ns / ne if ne else 0.0}))


def selftest() -> int:
    import contextlib
    import io
    import tempfile
    global RUNS

    def run(build) -> str:
        with tempfile.TemporaryDirectory() as td:
            global RUNS
            RUNS = Path(td)
            build(RUNS)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main()
            return buf.getvalue()

    def base(root: Path, joint=(6, 7, 6, 7)):
        for d, ns in zip(JOINT_LAST, joint):
            _mk(root, d, ns, 20)              # 默认联合 @last = 26/80 = 32.5%
        for i, d in enumerate(JOINT_VALSEL):
            _mk(root, d, [7, 6, 3][i], 20)   # 联合 @val选点 = 16/60 = 26.7%
        _mk(root, G2_REV_CTRL, 4, 10)

    cases = []

    def s_r1(root):   # 单任务 60% 且显著 -> R1 干扰确认
        base(root)
        for d, ns in zip(S2C_LAST, [13, 12, 11, 12]):
            _mk(root, d, ns, 20)              # 48/80 = 60%
        _mk(root, G1_FWD_ZEROSHOT, 0, 20)
    cases.append(("R1 干扰确认", s_r1, ["R1 干扰确认", "G1 正向零样本：0/20", "子集过滤生效"]))

    def s_r2(root):   # 单任务 ~30% 不显著 -> R2 不是干扰
        base(root)
        for d, ns in zip(S2C_LAST, [6, 6, 5, 6]):
            _mk(root, d, ns, 20)              # 23/80 = 28.8%
        _mk(root, G1_FWD_ZEROSHOT, 1, 20)
    cases.append(("R2 不是干扰", s_r2, ["R2 不是干扰", "改配比没用"]))

    def s_r3(root):   # 单任务显著变好但仍 <50% -> R3（联合基线压低到 25% 才有足够功效）
        base(root, joint=(5, 5, 5, 5))
        for d, ns in zip(S2C_LAST, [10, 9, 10, 9]):
            _mk(root, d, ns, 20)              # 38/80 = 47.5%
        _mk(root, G1_FWD_ZEROSHOT, 0, 20)
    cases.append(("R3 显著但未过门", s_r3, ["R3 干扰存在但不足以过门"]))

    def s_g1(root):   # 正向零样本也能成 -> 结论作废
        base(root)
        for d, ns in zip(S2C_LAST, [15, 15, 15, 15]):
            _mk(root, d, ns, 20)
        _mk(root, G1_FWD_ZEROSHOT, 9, 20)
    cases.append(("G1 护栏拦下", s_g1, ["护栏 G1 不成立", "全部结论作废"]))

    def s_worse(root):  # 单任务反而显著更差 -> 不许硬套「干扰」，要求先查管路
        base(root, joint=(12, 12, 12, 12))     # 48/80 = 60%
        for d, ns in zip(S2C_LAST, [4, 4, 4, 4]):
            _mk(root, d, ns, 20)               # 16/80 = 20%
        _mk(root, G1_FWD_ZEROSHOT, 0, 20)
    cases.append(("单任务更差→先查管路", s_worse, ["反而显著更差", "先查子集过滤"]))

    def s_miss(root):  # 主读数没到 -> 不崩、不下结论
        base(root)
        _mk(root, G1_FWD_ZEROSHOT, 0, 20)
    cases.append(("主读数缺失→未定", s_miss, ["主读数还没到", "MISSING"]))

    def s_g1miss(root):  # 护栏产物没到、但主读数齐了 -> 只能说「悬空」，不许喊「结论作废」
        base(root)
        for d, ns in zip(S2C_LAST, [13, 12, 11, 12]):
            _mk(root, d, ns, 20)              # 48/80 = 60%，只差 G1 一个产物
    cases.append(("G1 缺失→悬空不作废", s_g1miss,
                  ["G1 的产物还没到", "无法确认", "悬空"], ["全部结论作废"]))

    fails = 0
    for case in cases:
        name, build, expects = case[0], case[1], case[2]
        forbid = case[3] if len(case) > 3 else []
        try:
            out = run(build)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ {name}: 抛异常 {type(exc).__name__}: {exc}")
            fails += 1
            continue
        bad = [e for e in expects if e not in out]
        leaked = [f for f in forbid if f in out]
        if bad or leaked:
            fails += 1
            if bad:
                print(f"❌ {name}: 缺断言 {bad}")
            if leaked:
                print(f"❌ {name}: 出现禁止字样 {leaked}（假报警回归）")
            for line in out.splitlines():
                if "R1" in line or "R2" in line or "R3" in line or "护栏" in line or "MISSING" in line:
                    print(f"     | {line}")
        else:
            print(f"✅ {name}")
    print(f"\nselftest: {len(cases) - fails}/{len(cases)} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
