#!/usr/bin/env python
"""配对评测探针：同一批 seed 上评两个策略，量 McNemar 的不一致率 d 与显著性。

为什么需要它（§12.11-F/G/H）：接触任务里**评测**占总成本 59%（6 臂 × 10 轮 × 50 局
= 21.2 h），而 50 局的噪声地板 MDE≈0.22~0.28，`min_gain=0.02` / `regression_tol=0`
两个方向都在量噪声（run7 决定性臂 round 6 用 +0.02、p=0.31 发布；rounds 2/3 用
p=0.076 / 0.335 拒绝）。出路不是把评测局数堆上去（堆不起），而是**逐题配对**：
两臂跑同一批 seed，用 McNemar 检验。它能省多少局数取决于不一致率 d，而
`harness/sampling_design.py::required_episodes` 的配对口径需要 d 作为输入 ——
d 至今只是"两个相似策略应该很小"的猜测。本脚本把 d 变成实测值。

顺带它还能回答一个具体问题：harness 已经发布过的那些「提升/掉点」，
在配对检验下到底显不显著。

口径完全复用 `eval/reach_eval.py::evaluate_reach`（只读 import，不修改）：
`env.reset(seed=seed+ep)`，所以两臂的第 i 局是**同一道题**。环境参数直接从
`journal.jsonl` 的 `train.env_kwargs` 取，保证与该臂训练/评测时的语义一致。

用法：
    # 先按 harness 自己的口径（50 局）复现 journal 里的数字，确认协议对得上
    python scripts/probe_paired_eval.py \
        --journal runs/ab_stage3/run7_fullstate/noearly_s0/journal.jsonl \
        --round-a 5 --round-b 6 --n 50
    # 再扩到大样本量 d（reach 环境很便宜）
    python scripts/probe_paired_eval.py --journal <journal> --round-a 5 --round-b 6 --n 500
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from eval.reach_eval import evaluate_reach  # noqa: E402
from harness.env_factory import install_env_factory  # noqa: E402
from harness.sampling_design import (mcnemar, min_detectable_effect,  # noqa: E402
                                     mde_worst_case, paired_gate, required_episodes)
from registry.publish import INDEP_EVAL_SEED, harsh_probe_kwargs  # noqa: E402
from scripts.eval_policy import load_any_policy  # noqa: E402


def load_journal_round(journal: Path, which: int | None) -> dict:
    """从 journal 里取一个 train 轮次的记录（默认最后一轮）。"""
    rows = [json.loads(ln) for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip()]
    trains = [r for r in rows if r.get("phase") == "train"]
    if not trains:
        raise SystemExit(f"[ERR] {journal} 里没有 train 记录")
    if which is None:
        return trains[-1]
    for r in trains:
        if int(r.get("round", -1)) == int(which):
            return r
    raise SystemExit(f"[ERR] 找不到 round={which}，现有 {[r.get('round') for r in trains]}")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def compare(rows_a: list[dict], rows_b: list[dict], label: str,
            a_role: str = "incumbent", b_role: str = "candidate") -> dict:
    """逐题配对（同 seed = 同一道题），给出四类格子 + 两种检验 + 分辨率对照。

    **角色不能弄反**：`a_role` 默认是现任（incumbent）、`b_role` 默认是候选（candidate），
    所以 `paired_gate(only_new=只 B 成, only_inc=只 A 成)`。第一版把两个参数接反了，
    于是「B 显著更好（13:0，p=0.0002）」被印成 `reject_regression` —— 一个方向性错误
    足以把整份报告的结论倒过来，所以这里显式带角色名，并在输出里回显。
    """
    by_seed_a = {r["seed"]: bool(r["success"]) for r in rows_a}
    pairs = [(by_seed_a[r["seed"]], bool(r["success"])) for r in rows_b if r["seed"] in by_seed_a]
    n = len(pairs)
    both = sum(1 for x, y in pairs if x and y)
    b = sum(1 for x, y in pairs if x and not y)      # 只 A（现任）成
    c = sum(1 for x, y in pairs if y and not x)      # 只 B（候选）成
    neither = sum(1 for x, y in pairs if not x and not y)
    p_a, p_b = (both + b) / n, (both + c) / n
    d = (b + c) / n
    # 统计实现只有一份，在 harness/sampling_design.py（探针不自己写检验）
    mc = mcnemar(b, c)
    only_new, only_inc = (c, b) if b_role == "candidate" else (b, c)
    pg = paired_gate(n, only_new, only_inc)

    # 独立（未配对）口径的 z，用来对照"配对到底省了多少"
    se_unpaired = math.sqrt(p_a * (1 - p_a) / n + p_b * (1 - p_b) / n)
    z_unpaired = (p_b - p_a) / se_unpaired if se_unpaired > 0 else 0.0
    p_unpaired = math.erfc(abs(z_unpaired) / math.sqrt(2.0))
    delta = abs(p_b - p_a)
    p_bar = (p_a + p_b) / 2.0
    break_even = 2.0 * p_bar * (1.0 - p_bar)     # 配对盈亏平衡点，随工作点变化
    # 一次调用同时拿独立/配对/下界三个口径（`required_episodes` 现在带 |δ|<=d 的硬约束）
    need = required_episodes(delta, p_bar, discordant=d) if delta > 0 else {}
    need_unpaired = need.get("unpaired_per_arm")
    need_paired = need.get("paired_pairs")
    out = {
        "label": label, "n_pairs": n, "a_role": a_role, "b_role": b_role,
        "only_new": only_new, "only_inc": only_inc,
        "both_success": both, "only_a": b, "only_b": c, "both_fail": neither,
        "p_a": round(p_a, 4), "p_b": round(p_b, 4),
        "ci_a_wilson": wilson(both + b, n), "ci_b_wilson": wilson(both + c, n),
        "delta": round(p_b - p_a, 4),
        "discordant_rate": round(d, 4),
        "mcnemar": mc, "paired_gate": pg,
        "unpaired": {"z": round(z_unpaired, 3), "p": round(p_unpaired, 6),
                     "se": round(se_unpaired, 5)},
        "mde_at_n_paired_workpoint": round(min_detectable_effect(n, p_bar), 4),
        "p_bar": round(p_bar, 4), "pairing_break_even_d": round(break_even, 4),
        "mde_worst_case_at_n": round(mde_worst_case(n), 4),
        "episodes_needed": {"unpaired_per_arm": need_unpaired, "paired_pairs": need_paired,
                            "paired_floor_pairs": need.get("paired_floor_pairs"),
                            "paired_at_floor": need.get("paired_at_floor"),
                            "paired_note": need.get("paired_note") or need.get("paired_reason"),
                            "saving_factor": (round(need_unpaired / need_paired, 2)
                                              if need_unpaired and need_paired else None)},
        "paired_cheaper": (bool(need_paired and need_unpaired and need_paired < need_unpaired)
                           if delta > 0 else None),
    }
    out["verdict"] = (
        f"{label}: 现任({a_role})={p_a:.3f} 候选({b_role})={p_b:.3f} 差 {p_b - p_a:+.3f}；"
        f"翻转题 只候选成 {c} / 只现任成 {b}（d={d:.3f}，配对盈亏平衡点 d={break_even:.3f}）；"
        f"McNemar 精确 p={mc['exact_p']:.4f}（未配对 z={z_unpaired:+.2f}, p={p_unpaired:.4f}）⇒ "
        f"配对门禁判定 = **{pg['decision']}**"
        + (f"；检出这么大的差，独立口径需 {need_unpaired} 局/臂、配对需 {need_paired} 对"
           f"（{out['episodes_needed']['saving_factor']}×，"
           + ("配对更省" if (need_paired or 0) < (need_unpaired or 0) else
              "配对不省：d 已高于盈亏平衡点，通常因为两臂都贴近饱和")
           + "）" if need_paired else "")
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", required=True, help="harness 闭环的 journal.jsonl")
    ap.add_argument("--round-a", type=int, default=None, help="A 臂轮次（默认倒数第二轮）")
    ap.add_argument("--round-b", type=int, default=None, help="B 臂轮次（默认最后一轮）")
    ap.add_argument("--ckpt-a", default="", help="覆盖 A 的 ckpt 路径")
    ap.add_argument("--ckpt-b", default="", help="覆盖 B 的 ckpt 路径")
    ap.add_argument("--n", type=int, default=500, help="配对局数")
    ap.add_argument("--seed", type=int, default=INDEP_EVAL_SEED,
                    help=f"起始 seed（默认 {INDEP_EVAL_SEED} = registry 的独立评测 seed）")
    ap.add_argument("--harsh", action="store_true", help="用严酷探针口径（更短 max_steps）")
    ap.add_argument("--n-replay", type=int, default=50,
                    help="额外按 harness 原口径（前 N 局）复算一遍，用来复现 journal 数字")
    ap.add_argument("--env-factory", default="",
                    help="reach / perturbed；留空则按 env_kwargs 里有没有扰动键自动判定")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    journal = Path(args.journal)
    journal = journal if journal.is_absolute() else REPO_ROOT / journal
    trains = [json.loads(ln) for ln in journal.read_text(encoding="utf-8").splitlines()
              if ln.strip() and json.loads(ln).get("phase") == "train"]
    rounds = [int(r["round"]) for r in trains]
    ra = args.round_a if args.round_a is not None else (rounds[-2] if len(rounds) > 1 else rounds[-1])
    rb = args.round_b if args.round_b is not None else rounds[-1]
    rec_a, rec_b = load_journal_round(journal, ra), load_journal_round(journal, rb)
    env_kwargs = dict(rec_b["train"]["env_kwargs"])
    if args.harsh:
        env_kwargs = harsh_probe_kwargs(env_kwargs)
    # `evaluate_reach` 内部走 `envs.reach_env.make_reach_env`，而扰动键（action_delay /
    # gain_noise / drift / expose_queue）只有 `envs/reach_perturbed.py` 认。
    # harness 是靠 `env_factory.install_env_factory` 在**建环境之前**打 shim 的
    # （见 harness/loop.py:143），这里必须照做，否则 TypeError: unexpected keyword。
    factory = args.env_factory or (
        "perturbed" if any(k in env_kwargs for k in
                           ("action_delay", "gain_noise", "drift", "obs_noise", "expose_queue"))
        else "reach")
    installed = install_env_factory(factory)

    ck_a = args.ckpt_a or rec_a["train"]["ckpt"]
    ck_b = args.ckpt_b or rec_b["train"]["ckpt"]
    print("=" * 78)
    print(f"配对评测 · A=round{ra}({Path(ck_a).parent.name}) vs B=round{rb}({Path(ck_b).parent.name})")
    print(f"  n={args.n} seed0={args.seed} harsh={args.harsh} env_factory={installed}")
    print(f"  env_kwargs={env_kwargs}")
    print(f"  journal 记录的未配对成绩: A={rec_a['candidate_metrics']['success_rate']} "
          f"B={rec_b['candidate_metrics']['success_rate']} "
          f"（各 50 局，seed {INDEP_EVAL_SEED}）")
    print("=" * 78, flush=True)

    res = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "journal": str(journal), "round_a": ra, "round_b": rb,
           "ckpt_a": ck_a, "ckpt_b": ck_b, "n": args.n, "seed": args.seed,
           "harsh": args.harsh, "env_kwargs": env_kwargs, "env_factory": installed,
           "machine": {"loadavg": [round(v, 1) for v in os.getloadavg()],
                       "cpu_count": os.cpu_count()},
           "journal_unpaired": {"a": rec_a["candidate_metrics"], "b": rec_b["candidate_metrics"]}}

    rows = {}
    for tag, ck in (("a", ck_a), ("b", ck_b)):
        model, algo = load_any_policy(str(REPO_ROOT / ck if not Path(ck).is_absolute() else ck))
        t0 = time.time()
        scored = evaluate_reach(model, env_kwargs, n_episodes=args.n, seed=args.seed)
        rows[tag] = scored["episodes"]
        wall = time.time() - t0
        res[f"arm_{tag}"] = {"algo": algo, "ckpt": ck, "success_rate": scored["success_rate"],
                             "mean_steps": scored.get("mean_steps"),
                             "wall_sec": round(wall, 1),
                             "sec_per_episode": round(wall / max(args.n, 1), 3)}
        print(f"  臂 {tag.upper()} ({algo}) 跑完 {args.n} 局: sr={scored['success_rate']:.3f} "
              f"· {wall:.1f} s · {wall / max(args.n, 1):.3f} s/局", flush=True)

    res["paired_full"] = compare(rows["a"], rows["b"], f"n={args.n} 全样本")
    if args.n_replay and args.n_replay < args.n:
        res["paired_replay"] = compare(rows["a"][:args.n_replay], rows["b"][:args.n_replay],
                                       f"n={args.n_replay}（harness 原口径）")
    for key in ("paired_replay", "paired_full"):
        if key in res:
            print("-" * 78)
            print("  " + res[key]["verdict"], flush=True)

    full = res["paired_full"]
    d = full["discordant_rate"]
    be = full["pairing_break_even_d"]
    cheaper = bool(d < be)
    need = full["episodes_needed"]
    delta = abs(full["delta"])
    # d 的硬下界是 |δ|（δ=(c−b)/n、d=(b+c)/n、b,c>=0）。d 贴着下界 = 翻转全部同向 =
    # 配对已经把能消掉的题目方差**全部**消掉了，此时"配对不省"不是判据问题，是无可省。
    at_floor = bool(need.get("paired_at_floor")) or (delta > 0 and d <= delta + 1e-9)
    res["design_implication"] = {
        "measured_discordant_rate": d,
        "break_even_d": be,
        "break_even_note": "盈亏平衡点是 2p̄(1-p̄)，**随工作点变化**；p̄≈0.99 时只有 0.02，"
                           "p̄≈0.5 时才是 0.5。写死 0.5 会把贴近饱和的测量误读成'配对很划算'",
        "floor_d": round(delta, 4),
        "floor_note": "d 还有第二条更硬的下界 |δ|（不是 δ²）：想检出多大的差，不一致率就至少"
                      "有多大，所以配对能省的局数被效应量卡死。δ=0.20/p=0.17 时下界 37 对"
                      "（独立 79 局/臂 ⇒ 最多省 2.1×，不是早先写的 4.4×——那个 d=0.10<|δ| 不可达）",
        "at_floor": at_floor,
        "paired_cheaper": cheaper,
        "p_bar": full["p_bar"],
        "text": (f"实测 d={d:.4f} vs 盈亏平衡点 {be:.4f}（p̄={full['p_bar']:.3f}）"
                 f"⇒ 配对{'更省' if cheaper else '**不省**'}局数"
                 + (f"；且 d={d:.4f} 已贴硬下界 |δ|={delta:.4f}（翻转全部同向）⇒ 配对"
                    f"能消掉的题目难度方差**已经消完**，再加配对也没有余量" if at_floor else "")
                 + ("" if cheaper else
                    "：这一对候选都贴近饱和（p̄≈0.99），独立口径的方差本来就很小，"
                    "配对能消掉的题目难度方差没剩多少。要量配对收益必须在 A/B 真正运行的"
                    f"工作点上量（Lift 是 p≈0.17，平衡点 d=2p̄(1-p̄)≈0.28，硬下界 |δ|；"
                    f"独立 {need.get('unpaired_per_arm')} 局/臂 vs 配对下界 "
                    f"{need.get('paired_floor_pairs')} 对）")),
    }
    print("-" * 78)
    print("  " + res["design_implication"]["text"], flush=True)

    out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / \
        f"{time.strftime('%Y%m%d_%H%M%S')}_paired_eval_r{ra}_r{rb}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(f"\n已写出: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
