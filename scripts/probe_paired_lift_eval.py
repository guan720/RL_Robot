#!/usr/bin/env python
"""配对评测探针（接触任务版）：在 Lift 的**真实工作点**上量 McNemar 的不一致率 d。

为什么要单独做这件事（§12.11-H/L 缺的最后一块实测）
--------------------------------------------------
§12.11-F 实测：接触任务里**评测**占总成本 59%（6 臂 × 10 轮 × 50 局 = 21.2 h），
而 50 局的噪声地板 MDE≈0.22~0.28，`min_gain=0.02` 两个方向都在量噪声（§12.11-G，
run7 决定性臂逐轮实证）。出路不是把评测局数堆上去（堆不起），而是**逐题配对 +
McNemar**（§12.11-H）。但配对能省多少局数取决于不一致率 d，而
`required_episodes(delta, p_base, discordant=d)` 需要 d 作为输入 ——
**d 在 Lift 的工作点上至今只是猜测**（"两个相似策略应该很小"）。

reach 侧量过一次（`runs/infra/paired_eval_r5_r6.json`，r5 vs r6，n=500）：d=0.026。
但那是**饱和退化**案例：p̄=0.987、13:0 全部同向翻转 ⇒ d 正好贴在硬下界 |δ|=0.026 上，
配对能消掉的题目方差**已经消完**（300 对 vs 297 局/臂，反而更贵）。这个数**不能外推**
到 Lift 的工作点（p≈0.10~0.17）：那里盈亏平衡点是 2p̄(1−p̄)≈0.28，比 0.026 高一个量级。

本探针就在 Lift 工作点上量 d。素材是对方已经训完的三个 60k ckpt，固定 seed 复评
（`reeval_fixed_success.json`，20 局）分别是 0.05 / 0.10 / 0.15 —— 三个**相近**工作点，
两两配对给出 δ≈0.05 与 δ≈0.10 的小阶梯，正好能回答「d 随 δ 怎么变」。

与 `scripts/probe_paired_eval.py`（reach 版）的分工
------------------------------------------------
reach 版从 `journal.jsonl` 取两轮 ckpt、走 `eval.reach_eval`。本探针改的是三件事：
  1. 环境换成接触任务：物理与真值口径**全部复用** `scripts/probe_contact_ceiling.py`
     （`make_env` / `reset_controlled` / `run_one` / `calibrate_rise` / `truth_consistency`），
     成功只认 `env._check_success()`，失败标签只认 `_check_grasp` 真值。
  2. 统计**不写第二份**：直接复用 `probe_paired_eval.compare()`（它内部调
     `harness/sampling_design.py` 的 mcnemar / paired_gate / required_episodes）。
  3. 加两个 reach 侧不需要的守卫（见下）。

两个必须先过的守卫（否则量到的 d 是假的）
----------------------------------------
· **跨臂同题审计**：包装层 `envs/robosuite_pickplace.py::reset(seed=N)` 只播种
  `inner.rng`，物体摆放由 `placement_initializer.rng` 决定、没人播种 ⇒ 同 seed 四次四个
  出生点（修法属对方文件，只上报未代改）。探针侧用 `reset_controlled()` 绕过，但**绕过
  不等于成立**：本脚本逐 seed 比对所有臂的 `spawn_xy`，不完全一致就早退（前
  `--abort-after` 个 seed 内发现不一致直接 exit 3），并把 `spawn_audit` 记进产物。
  McNemar 的前提是"同一道题"，这一条不成立时配对就是在配噪声。
· **确定性地板自对照**：把**同一个 ckpt**在同一批 seed 上再跑一遍（臂 `a2`）。
  两遍之间的不一致**不是策略差异**，是仿真/数值残留的非确定性。若 d_floor>0，
  所有实测 d 都只能读成「策略差异 + 地板」，本脚本同时给 `d_policy_lower_bound =
  max(0, d − d_floor)`。没有这一条，"d 很小 ⇒ 配对很省"可能是把噪声当成了策略一致性。

另外一条跨进程复现性检查：seed 1000~1011 与已有产物
`runs/infra/paired_lift_default_spawn.json`（同一个 `demo5k` ckpt、同一档出生盒子）重叠，
逐 seed 对照成功/失败。它在 load≈1150 时跑的、本次 load≈700，若结论不同就说明
墙钟/负载能改变仿真结果 —— 那配对本身也不可信。

用法
----
    # 冒烟（4 局，约 2~4 分钟）
    MUJOCO_GL=egl OMP_NUM_THREADS=1 /root/venvs/rlrobot/bin/python \
        scripts/probe_paired_lift_eval.py --episodes 4 --self-control 2

    # 正式（3 臂 × 100 局 + 25 局自对照）
    setsid nohup nice -n 15 env MUJOCO_GL=egl OMP_NUM_THREADS=1 \
        /root/venvs/rlrobot/bin/python -u scripts/probe_paired_lift_eval.py \
        --episodes 100 --self-control 25 \
        > runs/infra/probe_paired_lift_eval.log 2>&1 &
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 物理与真值口径：全部复用接触探针，不在这里重写第二份
from scripts.probe_contact_ceiling import (PINNED_OBJECT_SEED, build_env,  # noqa: E402
                                          calibrate_rise, classify,
                                          object_geom_audit, reset_controlled,
                                          run_one, set_spawn_range,
                                          truth_consistency, verify_seeding)
# 统计口径：复用 reach 版探针的 compare()，它内部只调 harness/sampling_design.py
from scripts.probe_paired_eval import compare  # noqa: E402
from harness.sampling_design import required_episodes  # noqa: E402
from scripts.eval_policy import load_any_policy  # noqa: E402

# 与已有产物重叠的那一段 seed（跨进程复现性检查用）
REF_ARTIFACT = REPO_ROOT / "runs" / "infra" / "paired_lift_default_spawn.json"
DEFAULT_CKPTS = [
    "runs/20260923_162317_sac_lift_state_shaped/model_final.zip",
    "runs/20260923_164831_sac_lift_state_shaped_demo5k/model_final.zip",
    "runs/20260923_171636_sac_lift_state_shaped_demo5k_bc3k/model_final.zip",
]


def arm_tags(n: int) -> list[str]:
    return [chr(ord("a") + i) for i in range(n)]


def _proc_counts() -> dict:
    """容器内可见的 R/D 状态进程数。

    为什么要记这个：`os.getloadavg()` 读到的是**宿主机**的 load（本机常年 500~1400），
    而容器里只看得到自己的进程。实测 load≈580 时容器内 R=1、D=1 —— 也就是说 loadavg
    在这里几乎不携带"我的进程能拿到多少 CPU"的信息。两个都记，成本结论只认实测
    `sec_per_episode`；loadavg 仅作事后归因的粗线索。
    """
    counts = {"r": None, "d": None}
    try:
        states = []
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/stat", "rb") as fh:
                    tail = fh.read().rsplit(b")", 1)[-1].split()
                states.append(tail[0].decode(errors="ignore"))
            except Exception:
                continue
        counts = {"r": states.count("R"), "d": states.count("D"), "total": len(states)}
    except Exception:
        pass
    return counts


def spawn_audit(rows_by_tag: dict[str, list[dict]]) -> dict:
    """跨臂同题审计：同一个 seed 在所有臂上的物体出生点必须**逐位相同**。

    这是 McNemar 成立的前提。reach 侧不需要这一步（那边 `reset(seed=)` 真的固定了题目），
    接触侧需要，因为决定摆放的 `placement_initializer.rng` 默认没人播种。
    """
    seeds = sorted({r["seed"] for rows in rows_by_tag.values() for r in rows})
    n_checked = n_identical = 0
    max_diff = 0.0
    bad: list[dict] = []
    for s in seeds:
        pts = {t: np.asarray(r["spawn_xy"], dtype=np.float64)
               for t, rows in rows_by_tag.items()
               for r in rows if r["seed"] == s}
        if len(pts) < 2:
            continue
        n_checked += 1
        vals = list(pts.values())
        diff = float(max(np.max(np.abs(v - vals[0])) for v in vals[1:]))
        max_diff = max(max_diff, diff)
        if diff == 0.0:
            n_identical += 1
        elif len(bad) < 5:
            bad.append({"seed": s, "spawn": {t: list(map(float, v)) for t, v in pts.items()}})
    return {"seeds_checked": n_checked, "seeds_identical": n_identical,
            "identical_frac": round(n_identical / n_checked, 4) if n_checked else None,
            "max_abs_diff": round(max_diff, 6), "examples": bad,
            "pairing_valid": bool(n_checked > 0 and n_identical == n_checked)}


def identity_check(pair: dict) -> dict:
    """内部一致性：d − |δ| 必须正好等于 2·min(b,c)/n（"超出下界的不一致"=双向翻转）。

    这不是新统计，是把 d 拆成「净差」与「双向噪声翻转」两部分：
        d = (b+c)/n，|δ| = |c−b|/n  ⇒  d − |δ| = 2·min(b,c)/n
    d 贴下界 = 翻转全同向（配对已无可省，reach r5vr6 就是这种）；
    d 远高于下界 = 两臂在大量题目上**互有胜负**，那才是配对真正能吃掉的方差。
    写死这条恒等式，任何一边的实现被改动都会立刻被抓到。
    """
    n = pair["n_pairs"]
    excess = pair["discordant_rate"] - abs(pair["delta"])
    expect = 2.0 * min(pair["only_a"], pair["only_b"]) / n if n else 0.0
    ok = abs(excess - expect) < 2e-3          # 两边都四舍五入到 4 位，容差放宽到 2e-3
    return {"excess_over_floor": round(excess, 4), "expected_2min_bc_over_n": round(expect, 4),
            "identity_ok": ok,
            "reading": ("翻转几乎全同向：配对已经把能消掉的题目方差消完了"
                        if excess < 0.02 else
                        "存在双向翻转：这部分才是配对能吃掉的方差")}


def reference_check(rows_by_tag: dict[str, list[dict]], ckpt_of: dict[str, str],
                    ref_path: Path = REF_ARTIFACT, obj_geom: dict | None = None) -> dict | None:
    """跨进程复现性：与 `paired_lift_default_spawn.json` 的 SAC 臂对照。

    **对照之前必须先比物体几何**：robosuite 的 cube 尺寸是构造期用未播种的
    `np.random.default_rng()` 抽的（`lift.py:311` 的 `size_min/size_max`），所以
    早于 `pinned_object_rng` 的产物评的是**另一个 cube**（实测半高 0.020175 vs 0.020347、
    质量差 ~0.9%、初始 z 差 1.6 mm），接触动力学把它混沌放大 ⇒ 逐 seed 必然不同。
    几何不可比时只报聚合成功率并说明原因，**不能**当成"配对无效"（那是 `spawn_audit`
    与确定性地板的职责）。

    ckpt 匹配要用 **run 目录名**：所有 ckpt 的文件名都叫 `model_final.zip`，
    按 basename 匹配会把参照对到错误的臂上（本探针第一版就是这么错的）。
    """
    if not ref_path.exists():
        return None
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    sac = ref.get("sac") or {}
    ref_ckpt = str(sac.get("ckpt") or "")
    ref_run = Path(ref_ckpt).parent.name
    ref_eps = {r["seed"]: bool(r["success"]) for r in sac.get("episodes", [])}
    if not ref_run or not ref_eps:
        return None
    tag = next((t for t, c in ckpt_of.items() if Path(c).parent.name == ref_run), None)
    if tag is None:
        return {"skipped": f"本次没有跑参照产物用的那个 ckpt（{ref_run}）"}
    mine = {r["seed"]: bool(r["success"]) for r in rows_by_tag.get(tag, [])}
    overlap = sorted(set(mine) & set(ref_eps))
    agree = [s for s in overlap if mine[s] == ref_eps[s]]
    ref_geom = ref.get("object_geom")
    same_geom = bool(ref_geom and obj_geom and
                     ref_geom.get("bottom_offset") == obj_geom.get("bottom_offset") and
                     ref_geom.get("horizontal_radius") == obj_geom.get("horizontal_radius"))
    out = {"ref_artifact": str(ref_path.relative_to(REPO_ROOT)), "arm": tag,
           "ref_run": ref_run, "n_overlap": len(overlap), "n_agree": len(agree),
           "object_geom_comparable": same_geom,
           "ref_object_geom": (ref_geom or {}).get("bottom_offset"),
           "mine_object_geom": (obj_geom or {}).get("bottom_offset"),
            "agree_frac": round(len(agree) / len(overlap), 4) if overlap else None,
            "disagreements": [{"seed": s, "mine": mine[s], "ref": ref_eps[s]}
                              for s in overlap if mine[s] != ref_eps[s]][:10],
            "ref_prefix_success_rate": (round(sum(ref_eps[s] for s in overlap) / len(overlap), 4)
                                        if overlap else None),
            "mine_prefix_success_rate": (round(sum(mine[s] for s in overlap) / len(overlap), 4)
                                         if overlap else None),
            "machine_then": (ref.get("machine") or {}).get("loadavg"),
           }
    if same_geom:
        out["reproducible"] = bool(overlap) and len(agree) == len(overlap)
        out["verdict"] = ("几何相同 ⇒ 逐 seed 必须完全一致"
                          + ("：一致 OK" if out["reproducible"] else "：**不一致 FAIL**"))
    else:
        out["reproducible"] = None
        out["verdict"] = ("几何不可比（参照产物没有 object_geom 字段，早于物体尺寸钉死）⇒ "
                          "它评的是**另一个 cube**，逐 seed 差异是已知的跨进程混淆，不是配对失效；"
                          "只能比聚合成功率，且必须带区间")
    return out


def design_translation(pairs: list[dict], *, sec_per_episode: float, args) -> dict:
    """把实测 d 翻译成 §12.11-I 那套可行配置的评测预算。

    成本口径必须说清楚：**一对 = 2 局**（同一 seed 两臂各跑一次），而独立两臂 n 局/臂
    也是 2n 局。所以 `saving_factor = n_unpaired / n_pairs` 同时就是**总成本**的节省倍数，
    不需要再乘 2 —— 这一条很容易算错，写在代码里免得口头传错。
    """
    usable = [p for p in pairs if p.get("discordant_rate") is not None and p["delta"] > 0]
    out = {"sec_per_episode": round(sec_per_episode, 2),
           "eval_episodes_current": args.eval_episodes, "min_gain": args.min_gain,
           "budget_hours": args.budget_hours, "pairs_measured": len(usable)}
    if not usable:
        out["text"] = "没有 δ>0 的可用配对，无法翻译预算"
        return out
    # 用最保守（d 最大）的那一对做预算：设计要按最坏情况买，不按最好情况买
    worst = max(usable, key=lambda p: p["discordant_rate"])
    best = min(usable, key=lambda p: p["discordant_rate"])
    p_base = worst["p_bar"]
    rows = {}
    for name, pair in (("worst_d", worst), ("best_d", best)):
        d = pair["discordant_rate"]
        need = required_episodes(args.min_gain, p_base, discordant=d)
        n_unp = need["unpaired_per_arm"]
        n_pair = need["paired_pairs"]
        floor = need["paired_floor_pairs"]
        rows[name] = {
            "label": pair["label"], "d": d, "delta_of_that_pair": pair["delta"],
            "target_delta": args.min_gain, "p_base": round(p_base, 4),
            "unpaired_per_arm": n_unp, "paired_pairs": n_pair, "paired_floor_pairs": floor,
            "paired_reason": need.get("paired_reason"),
            "hours_unpaired": round(2 * n_unp * sec_per_episode / 3600.0, 2) if n_unp else None,
            "hours_paired": round(2 * n_pair * sec_per_episode / 3600.0, 2) if n_pair else None,
            "hours_at_floor": round(2 * floor * sec_per_episode / 3600.0, 2),
        }
    out["at_target_delta"] = rows
    w = rows["worst_d"]
    # 现行配置（120 局独立评测，§12.11-I）的实际开销，作为对照基线
    out["current_eval_hours_2arms"] = round(2 * args.eval_episodes * sec_per_episode / 3600.0, 2)
    out["mde_at_current_eval"] = None
    if w["paired_pairs"] is None:
        out["text"] = (f"实测 d={w['d']:.3f} < |δ|={args.min_gain:g}？不可达，检查输入"
                       f"（{w['paired_reason']}）")
        return out
    fits = (w["hours_paired"] + args.train_sec_per_round * args.rounds / 3600.0) <= args.budget_hours
    out["verdict_fits_budget"] = bool(fits)
    out["text"] = (
        f"要判 δ={args.min_gain:g}（p_base={w['p_base']:.3f}）：独立口径 "
        f"{w['unpaired_per_arm']} 局/臂 = {w['hours_unpaired']} h（两臂）；"
        f"用实测最坏的 d={w['d']:.3f} 配对口径 {w['paired_pairs']} 对 = {w['hours_paired']} h；"
        f"配对数学下界（d=|δ|）{w['paired_floor_pairs']} 对 = {w['hours_at_floor']} h。"
        f"现行 §12.11-I 的 120 局独立评测 = {out['current_eval_hours_2arms']} h。"
        + (f"⇒ 配对能把评测压到 {w['hours_paired']} h，加训练 "
           f"{args.rounds * args.train_sec_per_round / 3600.0:.1f} h 后"
           f"{'仍在' if fits else '**超出**'} {args.budget_hours:g} h 预算"
           if w["hours_paired"] < out["current_eval_hours_2arms"] else
           f"⇒ 实测 d 下配对**并不比 120 局独立评测便宜**"
           f"（{w['hours_paired']} h vs {out['current_eval_hours_2arms']} h）"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpts", default=",".join(DEFAULT_CKPTS),
                    help="逗号分隔的 SB3 .zip；第一个当现任(incumbent)，其余当候选(candidate)")
    ap.add_argument("--task", default="lift", choices=["lift", "pickplace"])
    ap.add_argument("--episodes", type=int, default=100, help="每个臂的配对局数")
    ap.add_argument("--seed0", type=int, default=1000,
                    help="起始 seed（默认 1000，与 paired_lift_default_spawn.json 重叠前 12 个）")
    ap.add_argument("--horizon", type=int, default=300)
    ap.add_argument("--reward-shaping", action="store_true",
                    help="与训练配置一致地打开 shaping。注意：包装层 `_obs()` 不读这个开关，"
                         "shaping 只改 reward，**不改观测也不改成功判定**，所以对 d 无影响")
    ap.add_argument("--spawn-range", type=float, default=None,
                    help="出生盒子半宽（米）。默认环境 ±0.03 = 训练分布 = 唯一的可用工作点")
    ap.add_argument("--no-pin-object", action="store_true",
                    help="不钉死物体尺寸随机化（每进程一个不同的 cube，跨进程不可比；仅用于演示）")
    ap.add_argument("--pin-seed", type=int, default=PINNED_OBJECT_SEED,
                    help=f"钉死物体尺寸的种子（默认 {PINNED_OBJECT_SEED}）；改它=换 cube")
    ap.add_argument("--self-control", type=int, default=25,
                    help="把第一个 ckpt 在前 N 个 seed 上再跑一遍，量确定性地板 d_floor；0=关")
    ap.add_argument("--abort-after", type=int, default=3,
                    help="前 N 个 seed 内发现跨臂出生点不一致就直接退出（省得白跑几小时）")
    ap.add_argument("--dump-every", type=int, default=10, help="每 N 个 seed 落一次中间产物")
    # §12.11-I 的可行配置，用来把实测 d 翻译成评测预算
    ap.add_argument("--eval-episodes", type=int, default=120)
    ap.add_argument("--min-gain", type=float, default=0.20)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--train-sec-per-round", type=float, default=671.0)
    ap.add_argument("--budget-hours", type=float, default=8.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    ckpts = [c.strip() for c in args.ckpts.split(",") if c.strip()]
    if len(ckpts) < 2:
        print("[ERR] 至少需要两个 ckpt 才能配对", file=sys.stderr)
        return 2
    resolved = []
    for c in ckpts:
        p = Path(c)
        p = p if p.is_absolute() else REPO_ROOT / p
        if not p.exists():
            print(f"[ERR] 找不到 ckpt: {p}", file=sys.stderr)
            return 2
        resolved.append(str(p))

    tags = arm_tags(len(resolved))
    ckpt_of = dict(zip(tags, resolved))
    # 自对照臂复用**同一个 model 对象**：要量的是仿真/数值非确定性，不是重新加载的差异
    arms = list(zip(tags, resolved))
    self_tag = "a2"
    do_self = args.self_control > 0
    if do_self:
        arms = arms + [(self_tag, resolved[0])]

    pin = None if args.no_pin_object else int(args.pin_seed)
    env = build_env(args.task, args.horizon, args.reward_shaping, pin)
    obj_geom = object_geom_audit(env, args.task, pin)
    set_spawn_range(env, args.spawn_range)
    seeds = [args.seed0 + i for i in range(args.episodes)]

    vs = verify_seeding(env)
    print(f"出题可复现自校验: seed={vs['seed']} 两次出生点 {vs['spawn_a']} / {vs['spawn_b']} "
          f"-> {'一致 OK' if vs['reproducible'] else '不一致 FAIL'}", flush=True)
    if not vs["reproducible"]:
        print("[ERR] 出生点不可复现 ⇒ 逐题配对无意义，拒绝继续", file=sys.stderr)
        return 3

    print("=" * 86)
    print(f"接触任务配对评测 · task={args.task} · {args.episodes} 局/臂 · horizon={args.horizon}")
    for t, c in arms:
        role = "确定性地板自对照（同 ckpt 重跑）" if t == self_tag else \
            ("现任 incumbent" if t == tags[0] else "候选 candidate")
        print(f"  臂 {t}: {role} · {Path(c).parent.name}")
    print(f"  出生盒子: {'环境默认 ±0.03' if args.spawn_range is None else f'±{args.spawn_range}'}"
          f" · reward_shaping={args.reward_shaping}（不影响 obs/成功判定）")
    print(f"  物体几何: pin_seed={pin} bottom_offset={obj_geom.get('bottom_offset')} "
          f"horizontal_radius={obj_geom.get('horizontal_radius')} "
          f"mass={obj_geom.get('body_mass_kg')} kg")
    print("=" * 86, flush=True)

    models: dict[str, object] = {}
    algos: dict[str, str] = {}
    for t, c in arms:
        if t == self_tag:
            models[t], algos[t] = models[tags[0]], algos[tags[0]]
            continue
        models[t], algos[t] = load_any_policy(c)
        print(f"  已加载臂 {t}: {algos[t]}", flush=True)

    def ctrl_for(tag: str):
        m = models[tag]
        return lambda raw, flat, _m=m: np.asarray(_m.predict(flat, deterministic=True)[0],
                                                  dtype=np.float64).reshape(-1)

    ctrls = {t: ctrl_for(t) for t, _ in arms}
    rows_by_tag: dict[str, list[dict]] = {t: [] for t, _ in arms}
    cal = calibrate_rise([])            # 先用兜底阈值，跑完用成功样本标定后重打标签

    out = Path(args.out) if args.out else REPO_ROOT / "runs" / "infra" / \
        f"{time.strftime('%Y%m%d_%H%M%S')}_paired_lift_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    aborted = None

    def snapshot(partial: bool) -> dict:
        """把当前进度整理成产物。中间态也用它，所以被打断/超时也不丢数据。"""
        done = {t: rows_by_tag[t] for t in rows_by_tag if rows_by_tag[t]}
        res: dict = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "partial": partial,
            "machine": {"loadavg": [round(v, 1) for v in os.getloadavg()],
                        "cpu_count": os.cpu_count(),
                        "procs_r_d": _proc_counts(),
                        "wall_sec": round(time.time() - t_start, 1),
                        "note": "sec_per_episode 必须和负载一起读；但注意 loadavg 是**宿主机**"
                                "口径、容器里只看得到自己的进程（实测 load≈580 时容器内 R/D "
                                "各只有 1 个），所以它只能当粗协变量，成本结论一律以实测"
                                "sec_per_episode 为准（本轮同一台机器上 25.5 s/局 与 2.4 s/局"
                                "都出现过，差 10 倍）"},
            "config": {"task": args.task, "episodes": args.episodes, "horizon": args.horizon,
                       "seed0": args.seed0, "spawn_range": args.spawn_range,
                       "reward_shaping": args.reward_shaping, "self_control": args.self_control,
                       "arms": {t: {"ckpt": c, "algo": algos.get(t),
                                    "role": ("self_control" if t == self_tag else
                                             ("incumbent" if t == tags[0] else "candidate"))}
                                for t, c in arms}},
            "seeding_verified": vs,
            "object_geom": obj_geom,
            "rise_calibration": cal,
        }
        aud = spawn_audit(done)
        res["spawn_audit"] = aud
        # 每臂汇总
        arms_sum = {}
        for t, rows in done.items():
            if not rows:
                continue
            ws = [r["wall_sec"] for r in rows]
            st = [r["steps"] for r in rows]
            tc = truth_consistency(rows)
            arms_sum[t] = {
                "n": len(rows),
                "success_rate": round(sum(r["success"] for r in rows) / len(rows), 4),
                # grasp-verified 才是"真抓起来"的成功率；`success_rate` 含弹起式成功
                "success_rate_grasp_verified": tc["success_rate_grasp_verified"],
                "flick_frac": tc["flick_frac"],
                "truth_status": tc["status"],
                "labels": {k: sum(1 for r in rows if r["label"] == k)
                           for k in sorted({r["label"] for r in rows})},
                "mean_wall_sec": round(float(np.mean(ws)), 2),
                "mean_steps": round(float(np.mean(st)), 1),
                "sec_per_episode": round(float(np.mean(ws)), 2),
                "grasp_truth_check": tc,
            }
        res["arms"] = arms_sum
        # 逐对比较（统计实现只有一份：compare -> harness/sampling_design）
        pairs: list[dict] = []
        pair_specs = [(x, y) for x, y in itertools.combinations(tags, 2)]
        if do_self and done.get(self_tag):
            pair_specs.append((tags[0], self_tag))
        for x, y in pair_specs:
            if not done.get(x) or not done.get(y):
                continue
            is_floor = (y == self_tag)
            p = compare(done[x], done[y],
                        label=(f"确定性地板 {x} vs {x}2" if is_floor else f"{x} vs {y}"),
                        a_role="incumbent", b_role="candidate")
            p["pair_kind"] = "determinism_floor" if is_floor else "ckpt_pair"
            p["identity"] = identity_check(p)
            pairs.append(p)
        res["pairs"] = pairs
        floor_pairs = [p for p in pairs if p["pair_kind"] == "determinism_floor"]
        d_floor = floor_pairs[0]["discordant_rate"] if floor_pairs else None
        res["determinism_floor"] = {
            "d_floor": d_floor, "n": floor_pairs[0]["n_pairs"] if floor_pairs else None,
            "interpretation": ("同一 ckpt 重跑零不一致 ⇒ 仿真确定性成立，"
                               "实测 d 可全部归因于策略差异" if d_floor == 0 else
                               f"同一 ckpt 重跑就有 d_floor={d_floor} 的不一致 ⇒ 存在"
                               f"仿真/数值非确定性，所有 ckpt 对的 d 都要减掉这个地板")
            if d_floor is not None else "未跑自对照",
        }
        if d_floor:
            for p in pairs:
                if p["pair_kind"] == "ckpt_pair":
                    p["d_policy_lower_bound"] = round(
                        max(0.0, p["discordant_rate"] - d_floor), 4)
        # 跨进程复现性（与已有产物重叠的 seed）
        res["reference_replay"] = reference_check(done, ckpt_of, obj_geom=obj_geom)
        # 预算翻译：成本按**最贵的那一臂**算
        all_ws = [r["wall_sec"] for rows in done.values() for r in rows]
        sec_ep = float(np.mean(all_ws)) if all_ws else 0.0
        res["cost"] = {"sec_per_episode_mean": round(sec_ep, 2),
                       "episodes_total": len(all_ws),
                       "hours_so_far": round((time.time() - t_start) / 3600.0, 3)}
        if not partial and all_ws:
            res["design_translation"] = design_translation(
                [p for p in pairs if p["pair_kind"] == "ckpt_pair"],
                sec_per_episode=sec_ep, args=args)
        res["episodes"] = done
        return res

    def dump(partial: bool) -> None:
        out.write_text(json.dumps(snapshot(partial), ensure_ascii=False, indent=2,
                                  default=float), encoding="utf-8")

    try:
        for i, seed in enumerate(seeds):
            spawns: dict[str, list[float]] = {}
            for t, _ in arms:
                if t == self_tag and i >= args.self_control:
                    continue
                row = run_one(env, args.task, ctrls[t], seed, args.horizon,
                              stop_on_success=True, cal=cal)
                row["arm"] = t
                rows_by_tag[t].append(row)
                spawns[t] = row["spawn_xy"]
            uniq = {tuple(v) for v in spawns.values()}
            if len(uniq) > 1:
                print(f"  [FATAL] seed {seed} 跨臂出生点不一致: {spawns}", flush=True)
                aborted = f"seed {seed} 跨臂出生点不一致 ⇒ 同 seed 不是同一道题，配对无效"
                if i < args.abort_after:
                    break
            line = " ".join(f"{t}:{int(rows_by_tag[t][-1]['success'])}"
                            f"({rows_by_tag[t][-1]['label'][:9]})"
                            for t, _ in arms if t in spawns)
            print(f"  [{i + 1}/{args.episodes}] seed {seed} spawn={spawns[tags[0]]} {line} "
                  f"· {time.time() - t_start:.0f}s", flush=True)
            if (i + 1) % args.dump_every == 0:
                dump(partial=True)
    finally:
        # 跑完（或被打断）都用**成功样本标定后**的阈值重打一遍失败标签
        all_rows = [r for rows in rows_by_tag.values() for r in rows]
        cal = calibrate_rise(all_rows)
        for r in all_rows:
            r["label"] = classify(r, cal)
        dump(partial=False)

    res = snapshot(partial=False)
    res["aborted"] = aborted
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float),
                   encoding="utf-8")

    print("=" * 86)
    print(f"rise 阈值标定: {json.dumps(cal, ensure_ascii=False)}")
    aud = res["spawn_audit"]
    print(f"跨臂同题审计: {aud['seeds_identical']}/{aud['seeds_checked']} 个 seed 出生点逐位相同 "
          f"(max|Δ|={aud['max_abs_diff']}) -> {'配对有效 OK' if aud['pairing_valid'] else '配对无效 FAIL'}")
    print(f"确定性地板: {res['determinism_floor']['interpretation']}")
    for t, s in res["arms"].items():
        tc = s["grasp_truth_check"]
        print(f"  臂 {t}: sr={s['success_rate']:.3f} ({s['n']} 局) 标签={s['labels']} "
              f"· {s['sec_per_episode']} s/局 · 真值自校验 "
              f"{'OK' if tc['consistent'] else 'FAIL'}")
    print("-" * 86)
    for p in res["pairs"]:
        print("  " + p["verdict"], flush=True)
        print(f"      d−|δ|={p['identity']['excess_over_floor']} "
              f"(=2·min(b,c)/n={p['identity']['expected_2min_bc_over_n']}, "
              f"恒等式{'OK' if p['identity']['identity_ok'] else 'FAIL'}) · "
              f"{p['identity']['reading']}"
              + (f" · d_policy≥{p['d_policy_lower_bound']}"
                 if "d_policy_lower_bound" in p else ""), flush=True)
    rr = res.get("reference_replay")
    if rr and "skipped" not in rr:
        print("-" * 86)
        print(f"  跨进程对照（vs {rr['ref_artifact']}，臂 {rr['arm']}={rr['ref_run']}）: "
              f"{rr['n_agree']}/{rr['n_overlap']} 个 seed 结论相同"
              f"（参照 sr={rr['ref_prefix_success_rate']} vs 本次 {rr['mine_prefix_success_rate']}）")
        print(f"      {rr['verdict']}")
        for dg in rr["disagreements"][:5]:
            print(f"      不一致 seed {dg['seed']}: 本次={dg['mine']} 参照={dg['ref']}")
    if "design_translation" in res:
        print("-" * 86)
        print("  " + res["design_translation"]["text"])
    print("=" * 86)
    print(f"已写出: {out}  · 总耗时 {res['cost']['hours_so_far']} h "
          f"· loadavg {res['machine']['loadavg']}")
    env.close()
    if aborted:
        print(f"[ERR] {aborted}", file=sys.stderr)
        return 3
    if not aud["pairing_valid"]:
        print("[ERR] 跨臂同题审计未通过，本产物的所有配对结论作废", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
