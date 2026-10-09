#!/usr/bin/env python3
"""C 线：让一个**真实 learner 进程**读一次导出的视图分片，并按附录 02 §3 更新参数。

## 为什么要有这一步

监管备忘录 §二C-1 写得很直白：`ledger / data_bridge / release_bundle` 的状态只能维持
「已实现未验证」，**至少要有一个真实调用方接入**。在此之前，四个视图只有内存里的自检，
没有任何进程真的把它们读成张量、算过 target、走过一次反向传播 —— 也就是说
「附录 02 的学习目标能不能落地」这个问题一直没人回答过。

本脚本就是那个调用方的最小实现：数据来自 `c_contract_lift_takeover_smoke` 同一套真实
Lift 帧（scripted teacher 重放），learner 是 `harness/queue_td_learner.py`（CPU、小 MLP、
确定性完整头，不用 SAC 的 log_pi/熵）。

**这不是能力主张**：十几条 TD 样本 + 3 步更新，学不出任何东西，成功率没有意义。
它验的是接线与数值语义：

- 只有 td/bc 进梯度，isolated/pending/candidate 计数后丢弃；
- Q 的动作梯度只经 E 段（C 是分片常量、D 补零），在真实数据上复核附录 02 §4.1／例2；
  探针是**可证伪**的：同一套探针故意错用策略的 C/D 预测时，对应段梯度必须亮起来，
  否则「C/D 梯度为 0」只是探针失灵（旧写法 `0.0*c_probe` 就是这种恒 0 的假绿）；
- `y = R_k + γ_slot·bootstrap·Q̄(X_{k+1}, π̄(X_{k+1}))` 逐行手算一致，`γ_slot = γ^n` 只乘一次；
- `C_{k+1} = U_k`、`C_k = U_{k-1}` 在张量层面逐值成立；终局槽无 bootstrap；
- 纠正帧的 BC 监督只落在 `supervision_mask` 指定的那一位，目标取自 `driver_command`；
- 分片被改过 / n 不符 / 混表征 / 观测反查不到 ⇒ 一律拒绝启动，不静默降级。

## 三条通道

| 通道 | 数据 | n / γ / H | 主要验什么 |
| --- | --- | --- | --- |
| `clean` | 真实 Lift 帧，无接管 | 4 / 0.99 / 2n | 装配、梯度隔离、`C_next=U`、无 BC 项 |
| `takeover` | 同一局，帧 18 兜底接管 | 4 / 0.99 / 2n | 纠正帧只进 BC、监督目标取自 `driver_command` |
| `terminal` | 合成时间轴（复用 `selfcheck_ledger_views.EpisodeBuilder`） | 6 / 0.9 / **3n** | 附录 02 §5 终局槽：`y=R_{k,L}` 无 bootstrap；H=3n 让 D 段真实存在 |

终局槽为什么必须合成：真帧重放的 U 由 teacher 逐帧动作拼出，尾槽的 `[t_k+n, t_k+2n)` 超出
录制范围 ⇒ U 不完整 ⇒ 按 §3.3 条件2「完整入队」与 §5.1「不给它伪造 U」被契约层隔离
（见 `c_contract_lift_smoke` 的 R010/R011）。真机上 U 是 `t_k` 一次前向的产物，终局槽照样有
完整 U、只是不再获得硬件执行资格 —— 合成通道就是把那种情况按同一套账本→视图→分片→learner
走一遍，learner 侧代码路径与真帧通道完全相同。

全程 CPU（`torch.cuda` 不初始化），不与 A/B 的 GPU 训练抢卡。

## 用法

    MUJOCO_GL=egl /root/venvs/rlrobot/bin/python scripts/c_learner_shard_smoke.py
    ... --steps 3 --seed 5000 --n 4

产物：`runs/infra/c_learner_shard_smoke.json` + `runs/infra/c_learner_shard_smoke/<时间戳>/`
（内含账本、观测快照、导出的 parquet 分片，可复查）。
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "robosuite", "gymnasium", "torch", "pandas", "pyarrow")

import torch  # noqa: E402

from harness import data_bridge as db  # noqa: E402
from harness import queue_td_learner as ql  # noqa: E402
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env  # noqa: E402
from harness.ledger import FactLedger  # noqa: E402
from harness.obs_store import ObsStore  # noqa: E402
from scripts.c_contract_lift_smoke import (GOAL_ID, GOAL_VOCAB,  # noqa: E402
                                           GOLDEN_SPEC_CONVENTION, REPR_VERSION, STATE_DIM,
                                           replay_into_contract, teacher_rollout, unit_convention)
from scripts.selfcheck_ledger_views import EpisodeBuilder  # noqa: E402
from scripts.selfcheck_ledger_views import action as synth_action  # noqa: E402

OUT_ROOT = ROOT / "runs" / "infra" / "c_learner_shard_smoke"
OUT_JSON = ROOT / "runs" / "infra" / "c_learner_shard_smoke.json"

# `td_targets` 返回 float32 张量，而手算走 float64 ⇒ 两者只能按 float32 精度比。
# 语义本身的精确性另由「db.td_target 在 float64 下精确」那条断言钉住，不靠放宽容差糊过去。
F32_TOL = 1e-5

# 终局通道的时间轴参数：与 `selfcheck_ledger_views.case3` 同构（RA 正常槽 + RB 第 3 步终止）。
TERM_N, TERM_GAMMA, TERM_L = 6, 0.9, 3
TERM_R_SLOT = TERM_GAMMA ** (TERM_L - 1)        # R_{k,L} = 0 + γ·0 + γ²·1 = 0.81
TERM_CHUNK_LEN = 3 * TERM_N                     # H=3n：让 D 段真实存在，"D 梯度为 0"才不是空过


def make_channel(stack: contextlib.ExitStack, name: str, work: Path, rollout: dict, *, n: int,
                 gamma: float, episode_id: str, takeover_frame: int | None,
                 label_version: str = "env-reward-v1",
                 convention: dict | None = None) -> dict:
    """建一条通道：账本 + 观测快照 + 四视图 + 导出分片，句柄全部挂在 stack 上保持打开。

    learner 需要 `ObsStore` 反查 `x_ref`，所以这里**不能**用 with 提前关掉。
    """
    ledger = stack.enter_context(FactLedger(work / f"ledger_{name}.db"))
    store = stack.enter_context(ObsStore(work / f"obs_{name}"))
    replay_into_contract(rollout, ledger, store, episode_id=episode_id, n=n,
                         takeover_frame=takeover_frame)
    bundle = db.build_views(ledger, n=n, gamma=gamma, obs_store=store,
                            max_age_ns=200_000_000, label_version=label_version)
    db.write_manifests(ledger, bundle, run_id=f"c-learner-{name}", gamma=gamma, n=n,
                       label_version=label_version)
    view_dir = work / f"views_{name}"
    manifest = db.export_views(bundle, view_dir, run_id=f"c-learner-{name}", n=n, gamma=gamma,
                               label_version=label_version, obs_store=store,
                               unit_convention=(convention if convention is not None
                                                else unit_convention(gamma, n)),
                               notes="learner smoke 导出的四视图分片")
    return {"name": name, "bundle": bundle, "store": store, "ledger": ledger,
            "view_dir": view_dir, "manifest": manifest,
            "counts": {view: len(getattr(bundle, view)) for view in db.VIEW_NAMES}}


def manual_bc_loss(batch: ql.ShardBatch, nets: dict, cfg: ql.LearnerConfig) -> float:
    """用显式 python 循环重算一遍 BC 损失（与 `ql.bc_loss` 是两条独立代码路径）。"""
    if not batch.bc:
        return 0.0
    bc = batch.bc
    with torch.no_grad():
        e = nets["actor"](bc["state"], bc["goal"], bc["c"], bc["xi"]).view(-1, cfg.n, cfg.action_dim)
    total, wsum = 0.0, 0.0
    for i in range(e.shape[0]):
        j = int(bc["e_index"][i])
        pred = e[i, j].detach().cpu().numpy().astype(np.float64)
        target = bc["target"][i].detach().cpu().numpy().astype(np.float64)
        weight = float(bc["weight"][i])
        total += weight * float(((pred - target) ** 2).sum())
        wsum += weight
    return total / max(wsum, 1e-9)


def make_terminal_channel(stack: contextlib.ExitStack, work: Path, *, state_dim: int,
                          action_dim: int, n: int = TERM_N, gamma: float = TERM_GAMMA,
                          terminal_step: int = TERM_L, chunk_len: int | None = TERM_CHUNK_LEN,
                          label_version: str = "env-reward-v1",
                          convention: dict | None = None) -> dict:
    """合成一条**终局槽 U 完整**的通道，专验附录 02 §5：终局槽进 TD、无 bootstrap、`y=R_{k,L}`。

    为什么这条必须合成：真帧重放的 U 由 teacher 逐帧动作拼出，尾槽的 `[t_k+n, t_k+2n)` 一旦
    超出录制范围就拼不全 ⇒ 按 §3.3 条件2「完整入队」与 §5.1「不给它伪造 U」只能隔离
    （见 `c_contract_lift_smoke` 里的 R010/R011）。真机上 U 是 `t_k` 一次前向的产物，终局槽
    照样有完整 U，只是不再获得硬件执行资格。这条通道把那种情况按**同一套**账本 → 视图 →
    导出分片 → learner 走一遍，时间轴复用 `selfcheck_ledger_views` 的 `EpisodeBuilder`
    （不另立事实源），观测走真实 `ObsStore`，所以 learner 侧路径与真帧通道完全一致。
    """
    episode_id = "lift_term_synth"
    ledger = stack.enter_context(FactLedger(work / "ledger_terminal.db"))
    store = stack.enter_context(ObsStore(work / "obs_terminal"))
    rng = np.random.default_rng(20260928)
    refs: dict[int, str] = {}
    for frame in range(100, 100 + n + terminal_step):
        refs[frame] = store.put(
            {"state": rng.normal(size=STATE_DIM).astype(np.float32).tolist(),
             "environment_state": rng.normal(
                 size=state_dim - STATE_DIM).astype(np.float32).tolist()},
            sampled_at_ns=1_000_000 * frame, representation_version=REPR_VERSION,
            episode_id=episode_id, abs_frame=frame).obs_ref
    builder = EpisodeBuilder(ledger, episode_id, n=n, goal=GOAL_ID)
    for rid, start, base, rewards, term in (
            ("RA", 100, 1.0, [0.0] * n, None),
            ("RB", 100 + n, 2.0, [0.0] * (terminal_step - 1) + [1.0], terminal_step)):
        builder.add_slot(rid, start, u=synth_action(base, n, dim=action_dim), rewards=rewards,
                         terminal_step=term, terminal_kind="success",
                         obs_ref_of=lambda f: refs.get(f), time_ns_of=lambda f: 1_000_000 * f)
    bundle = db.build_views(ledger, n=n, gamma=gamma, obs_store=store,
                            max_age_ns=200_000_000, label_version=label_version,
                            chunk_len=chunk_len)
    db.write_manifests(ledger, bundle, run_id="c-learner-terminal", gamma=gamma, n=n,
                       label_version=label_version)
    view_dir = work / "views_terminal"
    manifest = db.export_views(bundle, view_dir, run_id="c-learner-terminal", n=n, gamma=gamma,
                               label_version=label_version, obs_store=store,
                               # 终局通道用的就是 B 黄金值那套约定（γ=0.9, n=6），
                               # 与真机假设通道（γ=0.99, n=4）必须分开标注，不许混。
                               unit_convention=(convention if convention is not None
                                                else unit_convention(gamma, n, status="spec")),
                               notes="终局槽（U 完整）合成通道：验 §5 terminal TD 语义")
    return {"name": "terminal", "bundle": bundle, "store": store, "ledger": ledger,
            "view_dir": view_dir, "manifest": manifest,
            "counts": {view: len(getattr(bundle, view)) for view in db.VIEW_NAMES}}


def run_learner(ch: dict, cfg: ql.LearnerConfig, steps: int) -> dict:
    """把一条通道交给参考 learner：装配 → 梯度隔离复核 → target 审计 → 真实更新若干步。"""
    batch = ql.load_shard_batch(ch["view_dir"], ch["store"], cfg)
    nets = ql.build_nets(cfg)
    before = ql.param_snapshot(nets)
    iso = ql.gradient_isolation_report(batch, nets, cfg)
    falsify = ql.gradient_isolation_falsification(batch, nets, cfg)
    audit = ql.target_audit(batch, nets, cfg)
    # BC 手算必须在更新**之前**做：`history[0]["loss_bc"]` 是 step0 看到的损失，
    # 而 train_steps 会就地改 actor 参数，事后再算等于拿更新后的网络去比更新前的数。
    bc_manual = manual_bc_loss(batch, nets, cfg)
    history = ql.train_steps(batch, nets, cfg, steps=steps)
    return {"ch": ch, "cfg": cfg, "batch": batch, "nets": nets, "iso": iso,
            "falsify": falsify, "audit": audit,
            "history": history, "before": before, "after": ql.param_snapshot(nets),
            "bc_manual": bc_manual, "bc_manual_after": manual_bc_loss(batch, nets, cfg)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=5000)
    parser.add_argument("--n", type=int, default=4)
    parser.add_argument("--horizon", type=int, default=300)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--takeover-slot", type=int, default=4)
    parser.add_argument("--takeover-offset", type=int, default=2)
    parser.add_argument("--out", default=str(OUT_JSON))
    args = parser.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    work = OUT_ROOT / stamp
    work.mkdir(parents=True, exist_ok=True)
    n, gamma = args.n, args.gamma
    action_dim = 7                     # Lift: 6 关节/位姿增量 + 1 夹爪
    state_dim = 60                     # flat obs：proprio 50 + object 10

    env = make_contact_env("lift", horizon=args.horizon, reward_shaping=True, obs_mode="state")
    try:
        rollout = teacher_rollout(env, args.seed, args.horizon)
    finally:
        env.close()
    total = len(rollout["frames"])
    episode_id = f"lift_{args.seed}"
    takeover_frame = args.takeover_slot * n + args.takeover_offset
    if takeover_frame >= total - n:
        raise SystemExit(f"接管帧 {takeover_frame} 太靠后（本局 {total} 帧）")

    cfg = ql.LearnerConfig(state_dim=state_dim, action_dim=action_dim, n=n, gamma=gamma,
                           # 词表必须 ≥2：单 goal 下 one-hot 恒为 [1.0]，`_goal_onehot` 会直接拒绝
                           # （B→C 交接单 C-1/C-2）。真帧 teacher 只走 A→B，所以 batch 里出现的
                           # goal 只有一种；「同状态换 goal」的计算图验证另见
                           # scripts/c_selfcheck_goal_conditioning_t17.py。
                           goals=GOAL_VOCAB, hidden=args.hidden, device="cpu",
                           torch_threads=2, seed=0)
    report: dict = {
        "task": "robosuite Lift", "controller": rollout["controller"], "seed": args.seed,
        "steps_rollout": total, "n": n, "gamma": gamma, "H": cfg.H,
        "n_assumed": n, "gamma_assumed": gamma, "unit_convention": unit_convention(gamma, n),
        "state_dim": state_dim, "action_dim": action_dim,
        "pinned_object_seed": PINNED_OBJECT_SEED, "representation_version": REPR_VERSION,
        "artifact_dir": str(work), "learner_device": cfg.device,
        "train_steps": args.steps,
        "note": ("真实 Lift 帧（scripted teacher 重放）→ 契约层 → 导出分片 → 参考 learner 更新参数。"
                 "验接线与数值语义，不是能力主张；样本量与步数都不足以学出任何东西。"),
    }
    checks: dict[str, bool] = {}
    channels: dict[str, dict] = {}

    with contextlib.ExitStack() as stack:
        for name, tk in (("clean", None), ("takeover", takeover_frame)):
            ch = make_channel(stack, name, work, rollout, n=n, gamma=gamma,
                              episode_id=episode_id, takeover_frame=tk)
            channels[name] = run_learner(ch, cfg, args.steps)
        # 终局槽要 U 完整才有意义，真帧重放的尾槽拼不出完整 U（已被契约层隔离），
        # 所以 §5 的 terminal TD 语义单独走一条合成通道，learner 侧代码路径完全相同。
        cfg_term = dataclasses.replace(cfg, n=TERM_N, gamma=TERM_GAMMA, chunk_len=TERM_CHUNK_LEN)
        channels["terminal"] = run_learner(
            make_terminal_channel(stack, work, state_dim=state_dim, action_dim=action_dim),
            cfg_term, args.steps)

        clean, take = channels["clean"], channels["takeover"]
        cb, tb = clean["batch"], take["batch"]

        # ---------- 只读分片、只让 td/bc 进梯度 ----------
        checks["learner 只从分片装配（used 与视图行数一致）"] = (
            cb.used == {"td": clean["ch"]["counts"]["td"], "bc": clean["ch"]["counts"]["bc"]}
            and tb.used == {"td": take["ch"]["counts"]["td"], "bc": take["ch"]["counts"]["bc"]}
            and all(ch["batch"].used == {"td": ch["ch"]["counts"]["td"],
                                         "bc": ch["ch"]["counts"]["bc"]}
                    for ch in channels.values()))
        checks["isolated/pending/candidate 全部计数排除、零行进梯度"] = (
            cb.excluded["isolated"] == clean["ch"]["counts"]["isolated"]
            and cb.excluded["pending"] == clean["ch"]["counts"]["pending"]
            and cb.excluded["candidate"] == clean["ch"]["counts"]["candidate"]
            and tb.excluded["isolated"] == take["ch"]["counts"]["isolated"]
            and cb.td["state"].shape[0] == cb.used["td"])
        checks["takeover 通道确实有纠正帧进 BC"] = (
            tb.used["bc"] == total - takeover_frame and tb.bc["action_fields"] == ["driver_command"])

        # ---------- ξ 覆盖面普查（B→C 交接单 §4：把「已知近似」变成每 batch 可量化）----------
        cens = {name: ch["batch"].xi_census for name, ch in channels.items()}

        def _xi_recount(ch: dict) -> tuple[int, int]:
            """不看 `xi_census`，直接从张量再数一遍 —— 两条独立代码路径，防普查自己算错。"""
            b = ch["batch"]
            td1 = int((b.td["xi"][:, ql.XI_HAS_C] > 0.5).sum()) if b.td else 0
            bc0 = int((b.bc["xi"][:, ql.XI_HAS_C] < 0.5).sum()) if b.bc else 0
            return td1, bc0

        checks["ξ 普查：计数与 batch 行数自洽（td/bc 两侧）"] = all(
            c["td_rows_total"] == ch["batch"].used["td"]
            and c["bc_rows_total"] == ch["batch"].used["bc"]
            and 0 <= c["td_rows_at_xi1"] <= c["td_rows_total"]
            and 0 <= c["bc_rows_at_xi0"] <= c["bc_rows_total"]
            for c, ch in zip(cens.values(), channels.values()))
        checks["ξ 普查与张量独立复算逐值相同"] = all(
            (c["td_rows_at_xi1"], c["bc_rows_at_xi0"]) == _xi_recount(ch)
            for c, ch in zip(cens.values(), channels.values()))
        checks["ξ 普查有 BC 行时比例非空、无 BC 行时为 None（不伪造 0/0）"] = all(
            (c["bc_rows_at_xi0_ratio"] is None) == (c["bc_rows_total"] == 0)
            for c in cens.values())

        # ---------- 梯度只经 E 段（附录 02 §4.1／例2，真实数据）----------
        for label, ch in channels.items():
            iso, fals = ch["iso"], ch["falsify"]
            checks[f"{label}: Q 对 actor 的 E 输出导数非 0"] = iso["grad_e_absmax"] > 0.0
            # 完整头假设下：C 段用 sg(C) 常量、D 段用零常量拼装 ⇒ 策略在 C/D 的预测拿不到梯度。
            checks[f"{label}: 完整头探针下 C/D 段预测梯度为 0、E 段非 0"] = (
                iso["probe_grad_c_absmax"] == 0.0 and iso["probe_grad_d_absmax"] == 0.0
                and iso["probe_grad_e_absmax"] > 0.0)
            # 探针必须**可证伪**：故意把拼装规则写错时对应段要亮起来，否则那个 0 毫无意义
            # （旧写法 `0.0*c_probe` 就是恒 0 的假绿，见 queue_td_learner 的函数 docstring）。
            checks[f"{label}: 探针可证伪（错用策略 C/D 预测时梯度会亮）"] = (
                fals["wrong_c_grad_absmax"] > 0.0
                and (iso["d_segment_width"] == 0 or fals["wrong_d_grad_absmax"] > 0.0))
            checks[f"{label}: C 是分片常量（sg(C)）且 actor 只输出 E"] = (
                iso["c_requires_grad"] is False
                and iso["actor_out_width"] == iso["expected_e_width"]
                and iso["shard_mask_equals_e_segment"] is True)

        # ---------- TD 目标数值语义 ----------
        td = cb.td
        checks["γ_slot == γ^n（只乘一次，learner 不再自己乘）"] = all(
            abs(float(g) - gamma ** n) < F32_TOL for g in td["gamma_slot"].tolist())
        # 上面那条受 float32 存储限制，所以再用 float64 把「只乘一次」钉死：
        # γ_slot 必须等于 db 存的值本身，且终局分支彻底不含 q_next。
        checks["db.td_target 在 float64 下精确：终局 y==R_k、非终局 y==R_k+γ_slot·q"] = (
            db.td_target(0.81, 0.9 ** 6, False, 1234.5) == 0.81
            and abs(db.td_target(0.0, 0.9 ** 6, True, 2.0) - 0.9 ** 6 * 2.0) < 1e-15
            and abs(db.td_target(1.5, gamma ** n, True, 0.25) - (1.5 + gamma ** n * 0.25)) < 1e-15)
        checks["每行 target 与逐行手算一致"] = all(
            abs(row["y"] - row["y_handcheck"]) < F32_TOL
            for ch in channels.values() for row in ch["audit"])
        checks["C_{k+1} = U_k 逐值成立"] = bool(torch.equal(td["next_c"], td["u"]))
        has_c = td["xi"][:, ql.XI_HAS_C] > 0.5
        checks["C_k = U_{k-1}（连续槽）且首槽 has_c=0/C=0"] = (
            bool(torch.equal(td["c"][1:][has_c[1:]], td["u"][:-1][has_c[1:]]))
            and int(has_c[0].item()) == 0 and float(td["c"][0].abs().sum()) == 0.0)
        checks["target 网络参与 bootstrap（不是拿在线 Q 自己套自己）"] = all(
            row["q_next"] != 0.0 or not row["bootstrap_valid"]
            for ch in channels.values() for row in ch["audit"])

        # ---------- 终局槽语义（附录 02 §5：U 完整保留、无 bootstrap、y=R_{k,L}）----------
        term = channels["terminal"]
        audit_by_rid = {row["request_id"]: row for row in term["audit"]}
        ttd = term["batch"].td
        checks["终局通道：正常槽与终局槽都进 TD（U 完整 ⇒ 不被隔离）"] = (
            term["ch"]["counts"]["td"] == 2 and term["ch"]["counts"]["isolated"] == 0
            and set(audit_by_rid) == {"RA", "RB"})
        checks[f"终局槽无 bootstrap：y == R_(k,L) == {TERM_R_SLOT:.2f}"] = (
            audit_by_rid["RB"]["bootstrap_valid"] is False
            and abs(audit_by_rid["RB"]["r_slot"] - TERM_R_SLOT) < F32_TOL
            and abs(audit_by_rid["RB"]["y"] - TERM_R_SLOT) < F32_TOL)
        checks["终局槽 y 里确实没有 Q̄ 项（q_next 非 0 却没进目标）"] = (
            audit_by_rid["RB"]["q_next"] != 0.0
            and abs(audit_by_rid["RB"]["y"] - audit_by_rid["RB"]["r_slot"]) < F32_TOL)
        checks["前驱槽 RA 正常 bootstrap：γ_slot == γ^n 且 y == 手算"] = (
            audit_by_rid["RA"]["bootstrap_valid"] is True
            and abs(audit_by_rid["RA"]["gamma_slot"] - TERM_GAMMA ** TERM_N) < F32_TOL
            and abs(audit_by_rid["RA"]["y"] - audit_by_rid["RA"]["y_handcheck"]) < F32_TOL)
        checks["terminal 通道 H=3n：D 段真实存在，策略的 D 预测拿不到梯度"] = (
            term["iso"]["d_segment_width"] > 0 and term["iso"]["H"] == TERM_CHUNK_LEN
            and term["iso"]["probe_grad_d_absmax"] == 0.0
            and term["falsify"]["wrong_d_grad_absmax"] > 0.0)
        rb_idx = ttd["request_ids"].index("RB")
        checks["终局槽 next_x_ref=None ⇒ 零占位而非拒绝（不 bootstrap，占位不进 y）"] = (
            float(ttd["next_state"][rb_idx].abs().sum()) == 0.0
            and any("零占位" in note for note in term["batch"].notes))
        exec_ones = {row["request_id"]: sum(row["execution_mask"])
                     for row in term["batch"].td_rows}
        checks["终局槽 execution_mask 全 0（U 未物理激活，不冒充已执行）"] = (
            exec_ones["RB"] == 0 and exec_ones["RA"] > 0)

        # ---------- BC 监督 ----------
        checks["takeover: BC 损失 > 0 且与手算一致"] = (
            take["history"][0]["loss_bc"] > 0.0
            and abs(take["bc_manual"] - take["history"][0]["loss_bc"]) < 1e-4)
        checks["clean: 没有纠正帧就没有 BC 项"] = clean["history"][0]["loss_bc"] == 0.0
        checks["BC 监督位都落在 E 段内"] = all(
            0 <= int(i) < n for i in tb.bc["e_index"].tolist())

        # ---------- 真的更新了参数 ----------
        checks["actor/critic 参数确实变化且 target 随 polyak 跟随"] = (
            clean["before"]["actor"] != clean["after"]["actor"]
            and clean["before"]["critic"] != clean["after"]["critic"]
            and clean["before"]["actor_target"] != clean["after"]["actor_target"])
        checks["每步损失有限（不发散、不 NaN）"] = all(
            row["finite"] for row in clean["history"] + take["history"])

        # ---------- 拒绝路径 ----------
        def refuses(fn) -> str | None:
            try:
                fn()
            except (ql.LearnerRefused, db.ViewExportTampered) as exc:
                return f"{type(exc).__name__}: {exc}"[:220]
            except Exception as exc:  # noqa: BLE001 - 别的异常说明拒绝理由不对
                return f"WRONG-EXCEPTION {type(exc).__name__}: {exc}"[:220]
            return None

        tampered = work / "views_tampered"
        shutil.copytree(clean["ch"]["view_dir"], tampered)
        import pandas as pd
        victim = tampered / "td.parquet"
        frame = pd.read_parquet(victim)
        frame["r_slot"] = 0.0                      # 正是「unknown 被当零奖励」那种改动
        frame.to_parquet(victim, index=False)
        reason = refuses(lambda: ql.load_shard_batch(tampered, clean["ch"]["store"], cfg))
        checks["分片被改过 -> 拒绝加载（内容身份）"] = bool(reason) and "WRONG-EXCEPTION" not in reason

        wrong_n = refuses(lambda: ql.load_shard_batch(
            clean["ch"]["view_dir"], clean["ch"]["store"], dataclasses.replace(cfg, n=n + 1)))
        checks["槽预算 n 不一致 -> 拒绝（不猜）"] = bool(wrong_n) and "WRONG-EXCEPTION" not in wrong_n

        mixed = work / "views_mixed_repr"
        shutil.copytree(clean["ch"]["view_dir"], mixed)
        man = json.loads((mixed / "manifest.json").read_text())
        man["representation_versions"] = [REPR_VERSION, "lift-state-proprio50+obj10-v0-OLD"]
        (mixed / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n")
        reason = refuses(lambda: ql.load_shard_batch(mixed, clean["ch"]["store"], cfg))
        checks["混表征版本 -> 拒绝（不许把旧表征当新的用）"] = (
            bool(reason) and "WRONG-EXCEPTION" not in reason)

        empty_store = stack.enter_context(ObsStore(work / "obs_empty"))
        reason = refuses(lambda: ql.load_shard_batch(
            clean["ch"]["view_dir"], empty_store, cfg))
        checks["x_ref 反查不到观测 -> 拒绝（不拿零向量凑批）"] = (
            bool(reason) and "WRONG-EXCEPTION" not in reason)

        # §4.3：learner 只吃固定 n 段 ⇒ 短缺的行既不能补零也不能重复填成 n 段。
        checks["短缺的 U（n-1 行）-> 拒绝，不补零/不重复填成 n 段"] = bool(refuses(
            lambda: ql._action_matrix([[0.0] * action_dim] * (n - 1), cfg,
                                      kind="td/short-u", expect=n)))

        # §5：终局槽没有可确认的后继快照。把它谎称成「可 bootstrap」是最危险的一种改法 ——
        # 拿零向量当 h_{t_k+n} 会凭空造出一个后继价值。连 sha 一起改，绕过篡改检测再看。
        forged = work / "views_forged_bootstrap"
        shutil.copytree(term["ch"]["view_dir"], forged)
        forged_td = pd.read_parquet(forged / "td.parquet")
        forged_td.loc[forged_td["request_id"] == "RB", "bootstrap_valid"] = True
        forged_td.to_parquet(forged / "td.parquet", index=False)
        man = json.loads((forged / "manifest.json").read_text())
        man["views"]["td"]["sha256"] = db._sha256(forged / "td.parquet")
        (forged / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n")
        reason = refuses(lambda: ql.load_shard_batch(forged, term["ch"]["store"], cfg_term))
        checks["终局槽被谎称可 bootstrap（缺 next_x_ref）-> 拒绝，不拿零向量当后继状态"] = (
            bool(reason) and "WRONG-EXCEPTION" not in reason and "next_x_ref" in reason)

        # ---------- P0-2：γ/n 的定标状态必须跟着分片走，两套约定不许混 ----------
        # 真机通道（γ=0.99, n=4）至今是**假设值**：模板 timing 组仍是 null，n 要等 A 的
        # 延迟分布 + 位移增益反推。终局通道用的是 B 黄金值那套（γ=0.9, n=6, γ_slot=0.531441），
        # 只用于语义复核。两者必须在产物与分片 manifest 里各自标明，见
        # docs/c_golden_conformance_20260928.md §8。
        main_uc = report["unit_convention"]
        term_uc = term["ch"]["manifest"].get("unit_convention") or {}
        checks["真机通道标 assumed、终局通道标 spec：两套 γ/n 约定分开且不混"] = (
            main_uc["status"] == "assumed" and main_uc["gamma_is_assumed"]
            and main_uc["n_is_assumed"] and main_uc["n"] == n and main_uc["gamma"] == gamma
            and not main_uc["template_timing"].get("all_filled")
            and term_uc.get("status") == "spec"
            and float(term_uc.get("gamma", 0.0)) == GOLDEN_SPEC_CONVENTION["gamma"]
            and int(term_uc.get("n", -1)) == GOLDEN_SPEC_CONVENTION["n"]
            and all(ch["ch"]["manifest"].get("unit_convention", {}).get("status") == "assumed"
                    for cname, ch in channels.items() if cname != "terminal"))
        # γ_slot = γ^n **只算一次**：0.9^6=0.531441，不是 0.9^36（槽当折扣单位再幂一次）。
        checks["γ_slot 存的是 γ^n 本身（0.531441），没有二次幂成 γ^(n²)"] = (
            abs(GOLDEN_SPEC_CONVENTION["gamma_slot"] - 0.531441) < 1e-9
            and abs(float(term_uc.get("gamma_slot", 0.0)) - GOLDEN_SPEC_CONVENTION["gamma_slot"]) < 1e-12
            and abs(float(term_uc.get("gamma_slot", 0.0)) - 0.9 ** 36) > 1e-6)
        try:
            db.export_views(clean["ch"]["bundle"], work / "views_wrong_convention",
                            run_id="c-learner-negative", n=n, gamma=gamma,
                            unit_convention=GOLDEN_SPEC_CONVENTION)
            wrong_conv = "NO-RAISE"
        except ValueError as exc:
            wrong_conv = f"ValueError: {exc}"[:220]
        except Exception as exc:  # noqa: BLE001 - 别的异常说明拒绝理由不对
            wrong_conv = f"WRONG-EXCEPTION {type(exc).__name__}: {exc}"[:220]
        checks["把黄金值约定贴到 γ=0.99/n=4 的分片上会被拒（不静默混用）"] = (
            wrong_conv.startswith("ValueError"))

        checks["全程 CPU：torch.cuda 未被初始化（不与 A/B 抢卡）"] = (
            cfg.device == "cpu" and not torch.cuda.is_initialized())

    report["refusals"] = {"tampered": reason, "wrong_n": wrong_n,
                          "wrong_unit_convention": wrong_conv}
    report["channels"] = {
        name: {"n": ch["cfg"].n, "gamma": ch["cfg"].gamma, "gamma_slot": ch["cfg"].gamma ** ch["cfg"].n,
               "unit_convention": ch["ch"]["manifest"].get("unit_convention"),
               "counts": ch["ch"]["counts"], "used": ch["batch"].used,
               "excluded": ch["batch"].excluded, "notes": ch["batch"].notes,
               "xi_census": ch["batch"].xi_census,
               "gradient_isolation": ch["iso"], "target_audit": ch["audit"],
               "gradient_isolation_falsification": ch["falsify"],
               "history": ch["history"], "param_before": ch["before"], "param_after": ch["after"],
               "bc_manual_loss": ch["bc_manual"],
               "bc_manual_loss_after_steps": ch["bc_manual_after"],
               "view_dir": str(ch["ch"]["view_dir"]),
               "manifest_sha": {v: m["sha256"][:16] for v, m in ch["ch"]["manifest"]["views"].items()}}
               for name, ch in channels.items()}
    # B §4 要的是**显式结论**而非沉默。实测比例是 100%（BC 行全部在 ξ=0 上算），
    # 所以按 B 给的判据这是「实质缺口」而不是「已知近似」。这是现状登记，不是失败项：
    # 首版无法从分片重建 BC 行的 C（BC 行没有前后槽链），修它要动冻结面（导出列），
    # 属 v4 既定项，故只如实标注、不让 pass 变红。
    gap_channels = sorted(name for name, c in
                          ((n_, ch["batch"].xi_census) for n_, ch in channels.items())
                          if c["bc_rows_total"] > 0 and not c["bc_anchor_covers_xi1"])
    report["bc_anchor_xi0_gap"] = {
        "question": "λ_BC 锚是否覆盖部署区间（决策时 ξ=1）？",
        "bc_rows_at_xi0_ratio_by_channel": {
            name: ch["batch"].xi_census["bc_rows_at_xi0_ratio"] for name, ch in channels.items()},
        "td_rows_at_xi1_by_channel": {
            name: ch["batch"].xi_census["td_rows_at_xi1"] for name, ch in channels.items()},
        "channels_with_gap": gap_channels,
        "verdict": ("substantive_gap" if gap_channels else "none"),
        "verdict_note": ("BC 行 100% 在 ξ=0 上计算，而 TD 侧存在 ξ=1 的行 ⇒ "
                         "「有 BC 锚保护」在部署区间暂无证据。修法：harness 纠正也走 "
                         "request/commit 后从分片重建 BC 行的 C（属导出列变更 = 冻结面变更，"
                         "见 docs/ledger_data_bridge_20260928.md §9.2），不在 learner 侧偷偷补。"
                         if gap_channels else "已有 BC 行落在 ξ=1 上"),
    }
    report["checks"] = [{"name": k, "ok": bool(v)} for k, v in checks.items()]
    report["pass"] = all(checks.values())
    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    for name, ch in channels.items():
        print(f"{name}: counts={ch['ch']['counts']} used={ch['batch'].used} "
              f"excluded={ch['batch'].excluded}")
        cen = ch["batch"].xi_census
        print(f"  ξ 普查: td@ξ1={cen['td_rows_at_xi1']}/{cen['td_rows_total']} | "
              f"bc@ξ0={cen['bc_rows_at_xi0']}/{cen['bc_rows_total']} "
              f"(锚覆盖 ξ=1: {cen['bc_anchor_covers_xi1']})")
        iso, fals = ch["iso"], ch["falsify"]
        print(f"  grad: actorE={iso['grad_e_absmax']:.3e} | probe C={iso['probe_grad_c_absmax']:.1e} "
              f"E={iso['probe_grad_e_absmax']:.3e} D={iso['probe_grad_d_absmax']:.1e} "
              f"(d_width={iso['d_segment_width']})")
        print(f"  falsify: wrong_c={fals['wrong_c_grad_absmax']:.3e} "
              f"wrong_d={fals['wrong_d_grad_absmax']:.3e} | last step={ch['history'][-1]}")
        if name == "terminal":
            for row in ch["audit"]:
                print(f"  {row['request_id']}: R={row['r_slot']:.6f} "
                      f"γ_slot={row['gamma_slot']:.6f} bootstrap={row['bootstrap_valid']} "
                      f"q_next={row['q_next']:.6f} y={row['y']:.6f}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    print(f"结果: {'PASS' if report['pass'] else 'FAIL'} -> {out}")
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
