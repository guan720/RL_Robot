#!/usr/bin/env python3
"""档 8D 的**出身核对**（只读盘上产物，不训练、不评测、不改任何门）

为什么要有它：`code/mg_verdict_s8.py` 的 `prov()` 只核对 **8C / 8C-ctl** 两臂（它写的时候 8D 还没发车）
⇒ 8D 的读数纪律原本**只靠 `code/chain_s8d.sh` 自己**（链里核对 `readlink last == 022000`、评测路径写数字格）。
D4 是**关使命门**的那一条（三个训练 seed 的 min），所以这里补一道**独立**核对：
  ① 5 个 TEST 读（反向 4×20 + 正向 1×20）的 `policy_ckpt` 尾串 == `checkpoints/022000/pretrained_model`、
     且路径里含**本臂自己的 run 目录名**（防「读了隔壁臂的权重」）、`task_mode`/`K`/seed 窗口/局数全对；
  ② 11 格 val 扫描的 `policy_ckpt` 必须与**格名里的 step 逐格对上**（坑 38/42 的独立复查：
     `checkpoints/last` 是每次 save 都重指的软链，历史上出现过「拿 020000 冒充 022000」）；
  ③ 放宽口径的不变量：`n_success ≤ n_success_relaxed ≤ episodes`（严格 ⊆ 放宽，坑 40 ①）。
退出码：0 = 全对；2 = 读数不齐（还没跑完，**不是失败**）；3 = 有一条不对 ⇒ **D4 的输入不采信**，人来查。

用法：
    $MG_PY code/mg_prov_s8d.py --selftest
    $MG_PY code/mg_prov_s8d.py                 # 8D 收工后跑；也可中途跑（只核已落盘的格）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG = HERE.parent
RUNS = MG / "runs"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mg_verdict_s7f import EPS, K_EVAL, REPS, prov, rev_dirs, fwd_dirs   # noqa: E402  同一个量不重写第二遍（坑 54）

# ── 与 chain_s8d.sh / mg_verdict_s8.py 的契约（改这里等于改核对口径）──────────────
ARMS = {4000: "s8d_seed4000", 5000: "s8d_seed5000"}          # 评测目录前缀（== mg_verdict_s8.ARMS_D）
RUN_OF = {4000: "pi05_mix60f120r_c1_s8d_seed4000",            # 权重必须出自这个 run 目录
          5000: "pi05_mix60f120r_c1_s8d_seed5000"}
CK = "checkpoints/022000/pretrained_model"                    # 关门格 = last = 22000 步（数字格，坑 63）
STEPS, SAVE_FREQ, NCELLS = 22000, 2000, 11
REV_SEED0, FWD_SEED0 = 7000, 2000


def load_sum(d: Path) -> dict | None:
    f = d / "eval_summary.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text())
    except Exception as exc:                                     # 读不动 ≠ 没有（坑 40 ③：不许静默当 0）
        return {"_error": f"读不动 {f}: {exc}"}


def ckpt_of(j: dict) -> str:
    return str(j.get("policy_ckpt", "?"))


def check_test_arm(seed: int) -> tuple[list[str], list[str], int, int]:
    """核 5 个 TEST 读；返回（出身问题, 还没落盘的读, 已核读数, 应有读数）。

    ⚠️ 「产物还没出现」与「产物出身不对」是**两件事**：前者只是链还没跑到（rc=2、不算失败），
       后者才是「读数不采信」（rc=3）。混在一起会把一次正常的中途查看报成事故（本工具第一版就吃到了）。
    """
    arm = ARMS[seed]
    rev, fwd = rev_dirs(arm), fwd_dirs(arm)
    have_rev = [d for d in rev if load_sum(RUNS / d) is not None]
    have_fwd = [d for d in fwd if load_sum(RUNS / d) is not None]
    missing = [d for d in rev + fwd if load_sum(RUNS / d) is None]
    bad: list[str] = []
    # 复用既有 prov（ckpt 尾串 / task_mode / K / seed 窗口 / 局数）—— **只喂已落盘的读**，缺产物由 missing 单列
    bad += prov(have_rev, CK, "reverse", REV_SEED0)
    bad += prov(have_fwd, CK, "forward", FWD_SEED0)
    for d in have_rev + have_fwd:                                # 追加两条 prov 不查的：权重出身 + 口径不变量
        j = load_sum(RUNS / d)
        if "_error" in j:
            bad.append(f"{d}: {j['_error']}")
            continue
        ck = ckpt_of(j)
        if RUN_OF[seed] not in ck:
            bad.append(f"{d}: policy_ckpt 里不含本臂 run 名 `{RUN_OF[seed]}`（…{ck[-70:]}）⇒ 可能读了隔壁臂的权重")
        ks, kr, n = j.get("n_success"), j.get("n_success_relaxed"), int(j.get("episodes") or 0)
        if ks is None or kr is None:
            bad.append(f"{d}: 缺 n_success/n_success_relaxed 字段（缺字段 ≠ 0，坑 40 ③）")
        elif not (0 <= ks <= kr <= n):
            bad.append(f"{d}: 口径不变量被破坏：严格 {ks} ≤ 放宽 {kr} ≤ 局数 {n} 不成立")
    return bad, missing, len(have_rev) + len(have_fwd), len(rev) + len(fwd)


def check_val_cells(seed: int) -> tuple[list[str], int]:
    """核 11 格 val：格名里的 step 必须与 `policy_ckpt` 的格号逐格对上（坑 38/42 的独立复查）。"""
    run = RUNS / RUN_OF[seed]
    bad: list[str] = []
    n_ok = 0
    for s in range(SAVE_FREQ, STEPS + 1, SAVE_FREQ):
        d = run / "sweep_rev" / f"step_{s}_rev"
        j = load_sum(d)
        if j is None:
            continue                                             # 还没扫到 ⇒ 不算错（链会补齐；不齐由链自己 die）
        if "_error" in j:
            bad.append(f"{d.name}: {j['_error']}")
            continue
        want = f"checkpoints/{s:06d}/pretrained_model"
        ck = ckpt_of(j)
        if not ck.endswith(want):
            bad.append(f"{d.name}: policy_ckpt 尾巴是 …{ck[-46:]}，期望 …{want}（坑 38：`last` 冒充终点格）")
        elif int(j.get("n_action_steps", -1)) != K_EVAL or int(j.get("episodes") or 0) != EPS \
                or int(j.get("seed", -1)) != 8000:
            bad.append(f"{d.name}: K/局数/val seed 不对（K={j.get('n_action_steps')} eps={j.get('episodes')} "
                       f"seed={j.get('seed')}，期望 {K_EVAL}/{EPS}/8000）")
        else:
            n_ok += 1
    return bad, n_ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    all_bad: list[str] = []
    n_have = n_need = 0
    print("# 档 8D 出身核对（只读；不改任何门）\n")
    print(f"* 生成口径：TEST 5 读/臂（反向 4×20 seed{REV_SEED0}.. + 正向 1×20 seed{FWD_SEED0}..）、"
          f"关门格尾串 `{CK}`、val {NCELLS} 格（step 与格号逐格对上）\n")
    for seed in sorted(ARMS):
        bad, missing, have, need = check_test_arm(seed)
        vbad, vok = check_val_cells(seed)
        all_bad += bad + vbad
        n_have += have
        n_need += need
        mark = "🚫" if (bad or vbad) else ("✅" if not missing else "⏳")
        print(f"| seed {seed}（`{ARMS[seed]}`） | TEST 读 {have}/{need} | val 格对上 {vok}/{NCELLS} | "
              f"出身问题 {len(bad) + len(vbad)} 条 | {mark} |")
        for b in bad + vbad:
            print(f"    - {b}")
        if missing and not (bad or vbad):
            print(f"    - ⏳ 还没落盘 {len(missing)} 读（{missing[0]} …）⇒ 链还没跑到，**不是失败**")
    print()
    if all_bad:
        print(f"## 🚫 {len(all_bad)} 条不对 ⇒ **D4 的输入不采信**（人来查；`runs/S8_VERDICT.md` 的 D1/D2/D3 不受影响）")
        return 3
    if n_have < n_need:
        print(f"## ⏳ 读数不齐（{n_have}/{n_need}）⇒ 还没跑完，**不是失败**；已落盘的部分出身全对")
        return 2
    print("## ✅ 全对：两个新 seed 的 5 个 TEST 读 + 11 格 val 的出身都核过 ⇒ D4 的输入可采信")
    return 0


def selftest() -> int:
    npass = nfail = 0

    def chk(name: str, cond: bool) -> None:
        nonlocal npass, nfail
        if cond:
            npass += 1
        else:
            nfail += 1
            print(f"  ✗ {name}")

    # 契约：与 chain_s8d.sh / mg_verdict_s8.py 逐字对上（对不上 ⇒ 核对的是别的臂，比不核更坏）
    chk("ARMS 的目录前缀 = s8d_seed4000 / s8d_seed5000", ARMS == {4000: "s8d_seed4000", 5000: "s8d_seed5000"})
    try:
        import mg_verdict_s8 as V8
        chk("与 mg_verdict_s8.ARMS_D 逐字相同", V8.ARMS_D == ARMS)
        chk("与 mg_verdict_s8.CK_SUFFIX 逐字相同", V8.CK_SUFFIX == CK)
    except Exception as exc:                                       # 判定工具读不动 ⇒ 契约核不了，明确报出来
        chk(f"能 import mg_verdict_s8（{exc}）", False)
    chk("rev_dirs 4 读 + fwd_dirs 1 读 = 5", len(rev_dirs(ARMS[4000])) == REPS == 4 and len(fwd_dirs(ARMS[4000])) == 1)
    chk("关门格是数字格 022000（坑 63）", CK == "checkpoints/022000/pretrained_model")
    chk("11 格 = 22000/2000", STEPS // SAVE_FREQ == NCELLS)
    chk("REPS×EPS = 80（D4 的分母）", REPS * EPS == 80)
    chk("run 名与前缀同源（前缀 = run 名剥掉 pi05_<数据集>_）",
        all(RUN_OF[s].endswith(ARMS[s]) for s in ARMS))

    # 不变量判据（用合成 json，不碰盘）
    ok = {"n_success": 13, "n_success_relaxed": 18, "episodes": 20,
          "policy_ckpt": f"/x/{RUN_OF[4000]}/{CK}", "task_mode": "reverse",
          "n_action_steps": 10, "seed": 7000}
    chk("合法读数 ⇒ ckpt_of 取到 policy_ckpt", ckpt_of(ok).endswith(CK))
    chk("合法读数 ⇒ 含本臂 run 名", RUN_OF[4000] in ckpt_of(ok))
    bad_ck = dict(ok, policy_ckpt=f"/x/{RUN_OF[5000]}/{CK}")
    chk("读了隔壁臂的权重 ⇒ 含 run 名的判据会抓到", RUN_OF[4000] not in ckpt_of(bad_ck))
    for ks, kr, n, want in ((13, 18, 20, True), (18, 13, 20, False), (13, 18, 12, False), (-1, 5, 20, False)):
        got = 0 <= ks <= kr <= n
        chk(f"不变量 严格{ks} ≤ 放宽{kr} ≤ 局数{n} ⇒ {want}", got == want)

    # ── 真盘不变量：**与盘上进度无关**（坑 77 —— 旧版在这里断言「产物还没落盘」，
    #    8D 收工后产物齐了 ⇒ 自测反而 2 条失败 ⇒ 旁链按纪律自杀、D4 的出身核对没跑成）──
    b1, miss1, have1, need1 = check_test_arm(4000)
    chk("check_test_arm 返回应有读数 5", need1 == 5)
    chk("missing + 已核 == 应有读数（不缺不漏、不重叠）", len(miss1) + have1 == need1)
    chk("missing 里的目录**不许**再出现在出身问题里（缺产物 ≠ 不采信）",
        not any(x.split(":")[0] in miss1 for x in b1))
    b2, vok = check_val_cells(4000)
    chk("val 核对不抛异常且 0 ≤ 对上格数 ≤ NCELLS", isinstance(b2, list) and 0 <= vok <= NCELLS)

    # ── 合成对照（临时目录 ⇒ **与盘上真实进度无关**，可反复跑）：好读 / 三种坏读 / 缺读 / val 坏格 ──
    import tempfile as _tf

    import mg_verdict_s2f as _V2F

    def _summ(ck_run: str, ck_step: int, mode: str, seed: int, ks: int = 13, kr: int = 18) -> str:
        return json.dumps({"policy_ckpt": f"/x/{ck_run}/checkpoints/{ck_step:06d}/pretrained_model",
                           "task_mode": mode, "n_action_steps": K_EVAL, "seed": seed, "episodes": EPS,
                           "n_success": ks, "n_success_relaxed": kr})

    with _tf.TemporaryDirectory() as td:
        root = Path(td)
        old_runs, old_runof, old_v2f = RUNS, dict(RUN_OF), _V2F.RUNS
        try:
            globals()["RUNS"] = root          # 本模块的取数根
            _V2F.RUNS = root                  # prov() -> load() 用的是 mg_verdict_s2f 的 RUNS
            RUN_OF[4000] = "fake_arm"
            rv, fd = rev_dirs(ARMS[4000]), fwd_dirs(ARMS[4000])
            # rep1 好读；rep2 关门格尾串错（坑 38）；rep3 权重出自隔壁臂；rep4 口径不变量被破坏；正向缺产物
            for name, payload in ((rv[0], _summ("fake_arm", 22000, "reverse", REV_SEED0)),
                                  (rv[1], _summ("fake_arm", 20000, "reverse", REV_SEED0)),
                                  (rv[2], _summ("other_arm", 22000, "reverse", REV_SEED0)),
                                  (rv[3], _summ("fake_arm", 22000, "reverse", REV_SEED0, ks=18, kr=13))):
                d = root / name
                d.mkdir(parents=True)
                (d / "eval_summary.json").write_text(payload)
            sbad, smiss, shave, sneed = check_test_arm(4000)
            chk("合成：4 读落盘 ⇒ have=4/5、缺的那读单列进 missing", shave == 4 and sneed == 5 and smiss == [fd[0]])
            chk("合成：三种坏读全部被抓（尾串 / 隔壁臂 / 不变量）", len(sbad) >= 3
                and any("020000" in x for x in sbad) and any("不含本臂 run 名" in x for x in sbad)
                and any("不变量" in x for x in sbad))
            chk("合成：缺产物**不**算出身问题（还没跑完 ≠ 不采信）", not any(x.split(":")[0] == fd[0] for x in sbad))
            # val：step_2000 好格 + step_4000 里装 002000 的权重（坑 38 的原形）
            for step, ck_step in ((2000, 2000), (4000, 2000)):
                d = root / "fake_arm" / "sweep_rev" / f"step_{step}_rev"
                d.mkdir(parents=True)
                (d / "eval_summary.json").write_text(_summ("fake_arm", ck_step, "reverse", 8000))
            vbad2, vok2 = check_val_cells(4000)
            chk("合成 val：好格不误伤、坏格被抓（对上 1 格 / 1 条问题）",
                vok2 == 1 and len(vbad2) == 1 and "step_4000_rev" in vbad2[0] and "坑 38" in vbad2[0])
        finally:
            globals()["RUNS"] = old_runs
            _V2F.RUNS = old_v2f
            RUN_OF.clear()
            RUN_OF.update(old_runof)
    chk("合成对照跑完后 RUNS 已还原（不污染真盘取数）", RUNS == old_runs)

    print(f"[selftest] {npass} passed, {nfail} failed")
    return 1 if nfail else 0


if __name__ == "__main__":
    raise SystemExit(main())
