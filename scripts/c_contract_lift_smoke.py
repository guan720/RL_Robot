#!/usr/bin/env python3
"""C 线：把契约层（账本 + 观测快照 + 四视图）接到**真实 robosuite Lift 帧**上。

这不是 learned policy 结果，也不是新的能力主张：先用 scripted teacher 跑一局拿到真实
观测/动作/奖励/真值，再按附录 02 §1 的固定槽时间轴**重放**，目的是回答一个问题——
真实接触任务的数据能不能正确落成账本与训练视图（此前只在合成时间轴上验过）。

时间轴构造（与 `scripts/act_chunk_replay_lift.py` 同一思路）：

    槽 k 起点 t_k = k·n；在 t_k 接纳 request Rk，提交 U_k = teacher[t_k+n : t_k+2n]
    （即 proposal 的 E 段）；帧 [t_k, t_k+n) 实际执行的是 U_{k-1}，
    所以这些帧的 chunk_id = R_{k-1}、chunk_index = n + (f - t_k) ∈ [n, 2n)。

观测按 A 线官方数据集的同一映射拆开：`flat[:50] -> state`（本体）、
`flat[50:] -> environment_state`（物体），本体那一半同时写进账本的 `measured_state`。

用法：
    /root/venvs/rlrobot/bin/python scripts/c_contract_lift_smoke.py
    /root/venvs/rlrobot/bin/python scripts/c_contract_lift_smoke.py --seed 5001 --n 4 --horizon 300
产物：runs/infra/c_lift_contract_smoke.json + runs/infra/c_lift_contract_smoke/<时间戳>/
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("numpy", "robosuite", "gymnasium")

from harness import data_bridge as db  # noqa: E402
from harness.env_factory import PINNED_OBJECT_SEED, make_contact_env  # noqa: E402
from harness.ledger import FactLedger  # noqa: E402
from harness.obs_store import ObsStore  # noqa: E402
from scripts.probe_contact_ceiling import (  # noqa: E402
    grasp_truth_fn,
    make_scripted_factory,
    reset_controlled,
)

OUT_ROOT = ROOT / "runs" / "infra" / "c_lift_contract_smoke"
OUT_JSON = ROOT / "runs" / "infra" / "c_lift_contract_smoke.json"
STATE_DIM = 50                 # flat[:50] = robot0 proprio
OBJ_DIM = 10                   # flat[50:60] = object state（cube_pos/quat/... 拼接后的宽度）
# obs 布局是**表征身份的一部分**，所以版本号由宽度拼出来，而不是手写一个字符串：
# 布局一变（例如按 D 线增补二 §4 加入 `cube_z − z0` ⇒ obj 10→11），版本号自动跟着变，
# `ObsStore` 与 learner 的混版本拒绝就会生效；手写字符串则会悄悄沿用旧版本，
# 让新旧表征混进同一个训练批次 —— 那正是附录 01 §5.1 禁止的「旧表征伪装成新表征」。
REPR_VERSION = f"lift-state-proprio{STATE_DIM}+obj{OBJ_DIM}-v1"

# --- goal 词表（B→C 交接单 C-1：单 goal 词表下 T17「同状态换 goal」构造不出来）-----------
# v4 附录 02 §12 与交付包 AGENTS.md 要的是「同一目标条件学 A→B 与 B→A」，所以词表天生是
# 双向的；真帧 teacher 只做 A→B 抬起，故本 smoke 落账本的 goal_id 恒为 GOAL_ID，
# 但 learner 配置必须带完整词表 —— 否则 one-hot 退化成常量 [1.0]（= 给第一层加固定偏置），
# goal 对输出的影响恒为 0，而维度/concat/forward 检查全都会过。
GOAL_VOCAB = ("lift_A_to_B", "lift_B_to_A")
GOAL_ID = "lift_A_to_B"

# --- γ / n 的单位约定与定标状态（P0-2，docs/c_golden_conformance_20260928.md §8）----------
# 真实帧路径的 γ/n 至今是**假设值**：`templates/项目参数模板.json` 的 timing 组仍全为 null，
# 槽预算 n 要由推理延迟分布 + 位移增益反推才能定标。所以产物必须显式写清「用的是哪一套约定、
# 是假设值还是实测值」，否则会出现两种事故：把假设的 n=4 当成实测口径跨线比较；
# 或把 B 黄金值的 γ=0.9 / n=6 / H=20 混进真机路径（附录 02 的 γ_slot 只许算一次）。
GOLDEN_SPEC_CONVENTION = {
    "gamma": 0.9, "n": 6, "H": 20, "gamma_slot": 0.9 ** 6,
    "source": "docs/b_golden/async_td_golden_v1.json",
    "status": "spec",
    "note": "只用于规格一致性复核（scripts/c_selfcheck_golden_conformance.py），不代表真机口径",
}
CONTROL_HZ_CLAIM = {
    "value": 20.0,
    "source": "docs/lerobot_official_act_lock_20260924.md:22",
    "registered_in_template": False,   # 模板 timing.control_hz 仍是 null：有文档口径 ≠ 已登记实测
}
TIMING_FIELDS_FOR_N = ("control_hz", "slot_n", "inference_latency_measurements", "deadline")


def template_timing_status() -> dict:
    """读参数模板的 timing 组，如实报告「定标 n/γ 所需字段」是否已填。

    读不到就说读不到，不假装已定标；填了就翻转 all_filled，让下游的假设标注自动变成过期。
    """
    path = ROOT / "RL_Harness_v4_20260924" / "templates" / "项目参数模板.json"
    try:
        timing = json.loads(path.read_text(encoding="utf-8")).get("timing", {})
    except Exception as exc:
        return {"readable": False, "source": str(path), "error": f"{type(exc).__name__}: {exc}",
                "all_filled": False}
    return {"readable": True, "source": str(path.relative_to(ROOT)),
            "fields": {k: timing.get(k) for k in TIMING_FIELDS_FOR_N},
            "all_filled": all(timing.get(k) is not None for k in TIMING_FIELDS_FOR_N)}


def unit_convention(gamma: float, n: int, *, status: str = "assumed") -> dict:
    """把这一份产物的 γ/n 约定与定标状态写进产物。

    status: assumed（假设值，未定标）| measured（已由 P0 实测定标）| spec（B 黄金值约定）。
    γ_slot 只在这里算一次并落盘，下游直接读，避免再对 γ^n 做二次幂。
    """
    if status not in ("assumed", "measured", "spec"):
        raise ValueError(f"未知的定标状态: {status}")
    conv = {
        "gamma": gamma, "n": n, "gamma_slot": gamma ** n, "status": status,
        "gamma_is_assumed": status == "assumed", "n_is_assumed": status == "assumed",
        "control_hz": CONTROL_HZ_CLAIM, "template_timing": template_timing_status(),
        "doc": "docs/c_golden_conformance_20260928.md#8",
        "golden_spec": GOLDEN_SPEC_CONVENTION,
    }
    conv["note"] = (
        "γ/n 为假设值，未经 P0 延迟分布与位移增益定标；与 B 黄金值（γ=0.9, n=6, H=20）"
        "不是同一套约定，跨线比较前必须先声明用哪一套。"
        if status == "assumed" else
        "γ/n 为 B 黄金值约定，只用于规格复核，不代表真机口径。"
        if status == "spec" else
        "γ/n 已由 P0 实测定标（模板 timing 组须同时为非 null）。")
    if status == "measured" and not conv["template_timing"].get("all_filled"):
        raise ValueError("标注为 measured，但模板 timing 组仍有 null：不许把假设值写成实测值")
    return conv


def assert_obs_layout(obs_flat) -> int:
    """逐帧核对 obs 宽度与声明的布局一致；不一致就**炸**，不猜、不截断、不补零。

    返回实际宽度。这条守卫是 D 线增补二 §5-C「核对账本/视图对 obs 维度与布局的假设」的落点：
    库层（`ledger` / `data_bridge` / `obs_store` / `release_bundle`）对维度**零假设**，
    维度假设只存在于这里的切分与 learner 的 `LearnerConfig.state_dim`，两处都必须显式拒绝漂移。
    """
    width = int(np.asarray(obs_flat).reshape(-1).shape[0])
    if width != STATE_DIM + OBJ_DIM:
        raise AssertionError(
            f"obs 宽度 {width} != 声明的 {STATE_DIM + OBJ_DIM}"
            f"（proprio{STATE_DIM}+obj{OBJ_DIM}）：布局已变，必须同时改 STATE_DIM/OBJ_DIM "
            f"让 REPR_VERSION 变成新版本号（当前 {REPR_VERSION!r}），"
            "不能沿用旧版本号让新旧表征混进同一批次")
    return width


def teacher_rollout(env, seed: int, horizon: int, task: str = "lift") -> dict:
    """跑一局 scripted teacher，逐帧记录真实事实。`_check_grasp` 按 run_one 的门控调用。"""
    flat = reset_controlled(env, seed, task=task)
    raw = env._env._get_observations()
    controller = make_scripted_factory(task, env)(raw)
    grasp_fn = grasp_truth_fn(env, task)
    frames: list[dict] = []
    held = False
    success = False
    for t in range(horizon):
        sampled_at = time.monotonic_ns()
        obs_flat = np.asarray(flat, dtype=np.float32).reshape(-1)
        assert_obs_layout(obs_flat)
        action = np.asarray(controller(raw, flat), dtype=np.float32).reshape(-1)
        phase = getattr(controller, "phase", None)
        flat, reward, term, trunc, info = env.step(action)
        raw = env._env._get_observations()
        eef = np.asarray(raw["robot0_eef_pos"], dtype=np.float64)
        obj = np.asarray(raw["cube_pos"], dtype=np.float64)
        dxy = float(np.linalg.norm(eef[:2] - obj[:2]))
        if grasp_fn is not None and not held and dxy < 0.06 and grasp_fn():
            held = True
        if info.get("success"):
            success = True
        kind = "success" if success else ("environment_done" if term else ("timeout" if trunc else "none"))
        frames.append({"abs_frame": t, "sampled_at_ns": sampled_at, "obs_flat": obs_flat,
                       "action": action, "reward": float(reward), "phase": str(phase or ""),
                       "grasp_verified": bool(held), "dxy": round(dxy, 4),
                       "success": bool(success), "terminal": bool(success or term or trunc),
                       "terminal_kind": kind})
        if success or term or trunc:
            break
    return {"frames": frames, "success": success, "held": held, "steps": len(frames),
            "phases": sorted({f["phase"] for f in frames if f["phase"]}),
            "controller": "scripted_teacher", "seed": seed}


def replay_into_contract(rollout: dict, ledger: FactLedger, store: ObsStore, *, episode_id: str,
                         n: int, goal_id: str = GOAL_ID, decision_lag_ns: int = 0,
                         takeover_frame: int | None = None, takeover_reason: str = "grasp_miss",
                         pending_frames: Sequence[int] = (),
                         revoke_frames: Sequence[int] = ()) -> dict:
    """把真实帧按固定槽时间轴写成账本事实 + 观测快照。

    可选注入三种真实运行里一定会出现的情况（默认全关 ⇒ 与基线 smoke 逐位同构）：

    - `takeover_frame=F`：harness 兜底在帧 F 接管。F 之后的帧按**纠正帧**写：
      `source="harness"`、`lease_generation=1`、`a_rl=None`（那不是学习器的动作）、
      命令落在 `driver_command`、自带纠正 chunk 的 `chunk_id/chunk_index`（沿用 E 段
      `[n,2n)` 布局，否则 BC 的 supervision_mask 无处安放）。策略侧只保留到**包含 F 的
      那个槽**为止：它的 U 仍照原样提交（契约要求保留在途请求的 U 用于日志与训练），
      但 hardware 执行资格被 takeover 事件撤销，F 之后不再接纳新的策略请求。
      纠正 chunk **不发 `request_admitted`** —— 否则 `build_slots` 会把它当成学习器的
      决策槽，让兜底动作混进普通 TD（附录 02：只有真实决策请求产生的 U 才可入 TD）。
    - `pending_frames`：这些帧的奖励标签写 `reward_state="pending"`（GPT 评分迟到），
      槽应进 pending 桶，既不当 0 分也不进 TD。
    - `revoke_frames`：这些帧的 final 标签事后再 `revoke_label`（rubric 误判复核），
      原行保留、槽退回 unknown。
    """
    frames = rollout["frames"]
    actions = [f["action"] for f in frames]
    total = len(frames)
    pending = set(int(f) for f in pending_frames)
    obs_refs: dict[int, str] = {}
    for row in frames:
        flat = row["obs_flat"]
        obs_refs[row["abs_frame"]] = store.put(
            {"state": flat[:STATE_DIM], "environment_state": flat[STATE_DIM:]},
            sampled_at_ns=row["sampled_at_ns"], representation_version=REPR_VERSION,
            episode_id=episode_id, abs_frame=row["abs_frame"],
            decided_at_ns=row["sampled_at_ns"] + decision_lag_ns).obs_ref

    last_policy_start = total                       # 不含
    if takeover_frame is not None:
        last_policy_start = (int(takeover_frame) // n) * n + n
    label_seqs: dict[int, int] = {}

    # (1) 逐帧写**物理事实**。帧与决策槽必须解耦：接管之后策略不再被询问，但机器人还在动，
    #     这些纠正帧正是 BC 唯一的数据来源。旧写法把帧绑在策略槽循环里，于是接管点之后的帧
    #     一条都没进账本（实测 46 帧的局只落下 2 条纠正帧）——账本看起来"干净"，实际丢了
    #     整段纠正数据，这正是 v4 反复强调"事实账本先于训练语义"的原因。
    for idx, row in enumerate(frames):
        f = row["abs_frame"]
        taken = takeover_frame is not None and f >= int(takeover_frame)
        payload = {"phase": row["phase"], "grasp_verified": row["grasp_verified"],
                   "dxy": row["dxy"], "terminal": row["terminal"],
                   "terminal_kind": row["terminal_kind"]}
        common = {"episode_id": episode_id, "abs_frame": f, "goal_id": goal_id, "epoch": 1,
                  "abs_time_ns": row["sampled_at_ns"] + decision_lag_ns,
                  "measured_state": row["obs_flat"][:STATE_DIM].tolist(),
                  "obs_ref": obs_refs[f]}
        if taken:
            j = f - int(takeover_frame)
            corr_id = f"H{j // n:03d}"
            seq = ledger.append_frame(
                **common, request_id=corr_id, chunk_id=corr_id, chunk_index=n + (j % n),
                lease_generation=1, source="harness", execution_status="activated",
                a_rl=None, driver_command=actions[idx].tolist(),
                policy_version="harness-fallback-v1",
                payload={**payload, "takeover_reason": takeover_reason, "correction_offset": j})
            label_request = corr_id
        else:
            slot_start = (f // n) * n
            # 本帧执行的是上一个 request 的 U（E 段）；首槽是 prime/hold，没有来源 chunk。
            previous = f"R{(slot_start - n) // n:03d}" if slot_start >= n else None
            offset = f - slot_start
            seq = ledger.append_frame(
                **common, request_id=previous, chunk_id=previous,
                chunk_index=(n + offset) if previous else None,
                lease_generation=0, source="script" if previous else "hold",
                execution_status="activated" if previous else "not_activated",
                a_rl=(actions[idx].tolist() if previous else None),
                policy_version="scripted-teacher-v1", payload=payload)
            label_request = previous
        label_seqs[f] = ledger.append_label(
            episode_id=episode_id, label_kind="reward", target_seq=seq,
            target_request_id=label_request, value=row["reward"],
            reward_state=("pending" if f in pending else "final"),
            source=("gpt_late" if f in pending else "env"))

    # (2) 逐槽写**决策事件**：request/commit 属于学习器；接管之后不再产生新的决策请求。
    n_slots = 0
    for start in range(0, last_policy_start, n):
        rid = f"R{start // n:03d}"
        window = frames[start:start + n]
        terminal_row = next((r for r in window if r["terminal"]), None)
        length = (terminal_row["abs_frame"] - start + 1) if terminal_row else len(window)
        for kind in ("request_received", "request_admitted"):
            ledger.append_event(episode_id=episode_id, kind=kind, request_id=rid, abs_frame=start,
                                epoch=1, goal_id=goal_id, deadline=start + n, lease_generation=0)
        # U_k = teacher[t_k+n : t_k+2n]：尾部不足 n 只能标 partial，不跨 episode 补帧。
        segment = actions[start + n:start + 2 * n]
        payload = {"u": [a.tolist() for a in segment], "partial": len(segment) < n,
                   "proposal_indices": [n + i for i in range(len(segment))]}
        ledger.append_event(episode_id=episode_id, kind="result_committed", request_id=rid,
                            abs_frame=start, epoch=1, goal_id=goal_id, deadline=start + n,
                            lease_generation=0, payload=payload)
        if takeover_frame is not None and start <= int(takeover_frame) < start + length:
            # 接管事件挂在**被抢占的那个 request** 上，并换代次：租约是按物理资源的独占权。
            ledger.append_event(episode_id=episode_id, kind="takeover", request_id=rid,
                                abs_frame=int(takeover_frame), epoch=1, goal_id=goal_id,
                                lease_generation=1,
                                payload={"by": "harness", "reason": takeover_reason})
        n_slots += 1

    revoked = [ledger.revoke_label(label_seqs[int(f)], reason="rubric 误判复核",
                                   rubric_version="rubric-v2")
               for f in revoke_frames if int(f) in label_seqs]
    n_harness = sum(1 for row in frames
                    if takeover_frame is not None and row["abs_frame"] >= int(takeover_frame))
    return {"n_slots": n_slots, "n_frames": total, "episode_id": episode_id,
            "takeover_frame": takeover_frame, "n_harness_frames": n_harness,
            "pending_frames": sorted(pending), "revoked_label_seqs": revoked,
            "policy_requests_after_takeover": 0 if takeover_frame is None else None}


def summarize(bundle: db.ViewBundle, rollout: dict, frames: list[dict], store: ObsStore, *,
              n: int, gamma: float) -> dict:
    """手核 identities：回报、终局 target、C_next=U、观测可反查。"""
    rewards = {f["abs_frame"]: f["reward"] for f in frames}
    checked = {"r_slot_recomputed": 0, "r_slot_mismatch": 0, "c_next_equals_u": 0,
               "obs_bitexact": 0, "obs_mismatch": 0}
    for sample in bundle.td:
        start = sample.start_frame
        expect = sum(gamma ** j * rewards.get(start + j, 0.0) for j in range(n))
        if abs((sample.r_slot or 0.0) - expect) < 1e-9:
            checked["r_slot_recomputed"] += 1
        else:
            checked["r_slot_mismatch"] += 1
        if sample.next_queue and tuple(tuple(a) for a in sample.next_queue) == \
                tuple(tuple(a) for a in sample.u[:len(sample.next_queue)]):
            checked["c_next_equals_u"] += 1
        restored = db.resolve_x(store, sample)
        original = next((f["obs_flat"] for f in frames if f["abs_frame"] == start), None)
        if restored is not None and original is not None:
            same = (np.array_equal(restored["state"], original[:STATE_DIM])
                    and np.array_equal(restored["environment_state"], original[STATE_DIM:]))
            checked["obs_bitexact" if same else "obs_mismatch"] += 1
    terminal = next((s for s in bundle.td if s.terminated), None)
    short_u = [s for s in bundle.isolated
               if {"u_incomplete", "terminal_u_incomplete"} & set(s.isolation_reasons)]
    return {"checked": checked,
            "n_td_terminal": sum(1 for s in bundle.td if s.terminated),
            "n_td_nonterminal": sum(1 for s in bundle.td if not s.terminated),
            "n_td_u_complete": sum(1 for s in bundle.td if len(s.u or ()) == n),
            "short_u_slots": [{"request_id": s.request_id, "start_frame": s.start_frame,
                               "u_rows": len(s.u or ()), "terminated": s.terminated,
                               "terminal_kind": s.terminal_kind, "r_slot": s.r_slot,
                               "bootstrap_valid": s.bootstrap_valid,
                               "isolation_reasons": list(s.isolation_reasons)} for s in short_u],
            "gamma_slot": gamma ** n,
            "terminal_sample": None if terminal is None else {
                "request_id": terminal.request_id, "start_frame": terminal.start_frame,
                "r_slot": terminal.r_slot, "bootstrap_valid": terminal.bootstrap_valid,
                "terminal_kind": terminal.terminal_kind,
                "target_with_zero_q": terminal.target(0.0)},
            "stats": bundle.stats,
            "rollout": {k: v for k, v in rollout.items() if k != "frames"}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=5000)
    parser.add_argument("--n", type=int, default=4, help="固定槽预算（首版应由 P0 实测定，这里标假设值）")
    parser.add_argument("--horizon", type=int, default=300)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--max-age-ms", type=float, default=200.0, help="观测新鲜度预算")
    parser.add_argument("--out", default=str(OUT_JSON))
    args = parser.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    work = OUT_ROOT / stamp
    work.mkdir(parents=True, exist_ok=True)
    n, gamma = args.n, args.gamma
    max_age_ns = int(args.max_age_ms * 1e6)

    env = make_contact_env("lift", horizon=args.horizon, reward_shaping=True, obs_mode="state")
    try:
        rollout = teacher_rollout(env, args.seed, args.horizon)
    finally:
        env.close()
    frames = rollout["frames"]

    report: dict = {"task": "robosuite Lift", "controller": rollout["controller"],
                    "seed": args.seed, "horizon": args.horizon, "n_assumed": n,
                    "gamma": gamma, "gamma_assumed": gamma,
                    "unit_convention": unit_convention(gamma, n),
                    "pinned_object_seed": PINNED_OBJECT_SEED,
                    "representation_version": REPR_VERSION, "artifact_dir": str(work),
                    "steps": rollout["steps"], "success": rollout["success"],
                    "held": rollout["held"], "phases": rollout["phases"],
                    "note": "scripted teacher 重放驱动的槽协议 smoke，不是 learned policy 结果"}

    passes = {}
    for name, lag_ns, budget_ns in (("fresh", 0, max_age_ns),
                                    ("stale", int(10 * max_age_ns), max_age_ns)):
        ledger = FactLedger(work / f"ledger_{name}.db")
        store = ObsStore(work / f"obs_{name}")
        with ledger, store:
            replay_into_contract(rollout, ledger, store, episode_id=f"lift_{args.seed}", n=n,
                                 decision_lag_ns=lag_ns)
            bundle = db.build_views(ledger, n=n, gamma=gamma, obs_store=store,
                                    max_age_ns=budget_ns, label_version="env-reward-v1")
            db.write_manifests(ledger, bundle, run_id=f"c-lift-{name}", gamma=gamma, n=n,
                               label_version="env-reward-v1")
            passes[name] = summarize(bundle, rollout, frames, store, n=n, gamma=gamma)
            passes[name]["decision_lag_ns"] = lag_ns
            passes[name]["max_age_ns"] = budget_ns
            passes[name]["ledger_stats"] = ledger.stats()
            passes[name]["obs_stats"] = store.stats()
    report["passes"] = passes

    fresh, stale = passes["fresh"], passes["stale"]
    # obs 布局守卫（D 线增补二 §5-C）：宽度是表征身份的一部分。正向核对本局每一帧，
    # 反向确认宽度漂移时守卫真的会炸 —— 只测正向等于没测（参见 §7.1 缺陷 6 的教训）。
    layout_ok = all(assert_obs_layout(f["obs_flat"]) == STATE_DIM + OBJ_DIM for f in frames)
    try:
        assert_obs_layout(np.concatenate([frames[0]["obs_flat"], np.zeros(1, dtype=np.float32)]))
        layout_guard_fires = False
    except AssertionError:
        layout_guard_fires = True

    # P0-2 的反向守卫：`status="measured"` 而模板 timing 未填 ⇒ 必须抛；模板填满 ⇒ 必须放行。
    # 两边都测，否则一个无条件 raise 也能骗过正向断言（§6.2 的教训：变异必须真的改变被测量）。
    # 用**注入的**模板状态测，这样将来模板真被填上时，这条守卫测试不会变成定时炸弹。
    real_template_status = template_timing_status

    def _fake_status(all_filled: bool):
        return lambda: {"readable": True, "source": "<injected>", "all_filled": all_filled,
                        "fields": {k: (20.0 if all_filled else None) for k in TIMING_FIELDS_FOR_N}}

    try:
        globals()["template_timing_status"] = _fake_status(False)
        try:
            unit_convention(gamma, n, status="measured")
            measured_guard = "NO-RAISE"
        except ValueError as exc:
            measured_guard = f"ValueError: {exc}"[:200]
        globals()["template_timing_status"] = _fake_status(True)
        measured_ok_when_calibrated = (
            unit_convention(gamma, n, status="measured")["status"] == "measured")
    finally:
        globals()["template_timing_status"] = real_template_status

    checks = {
        "真实帧能落成账本与视图": fresh["stats"]["n_td"] > 0,
        "回报可按手算复现（无 mismatch）": fresh["checked"]["r_slot_mismatch"] == 0
                                          and fresh["checked"]["r_slot_recomputed"] > 0,
        # 终局槽按契约不要求 next 快照（无 bootstrap），所以 C_next=U 只对非终局槽成立。
        "C_next=U 逐值成立（非终局槽）": (
            fresh["checked"]["c_next_equals_u"] == fresh["n_td_nonterminal"]
            and fresh["n_td_nonterminal"] > 0),
        "x_ref 能反查回逐位相同的观测": fresh["checked"]["obs_mismatch"] == 0
                                     and fresh["checked"]["obs_bitexact"] > 0,
        "终局槽若进 TD 则必无 bootstrap 且保留真实终局类型": (
            fresh["terminal_sample"] is None
            or (fresh["terminal_sample"]["bootstrap_valid"] is False
                and fresh["terminal_sample"]["terminal_kind"] in db.TERMINATED_KINDS)),
        # 尾槽 U 不完整：本重放的 U 由 teacher 逐帧动作拼出，[t_k+n, t_k+2n) 一旦超出录制
        # 范围就拼不全。附录 02 §3.3 条件2 要求「完整入队」，§4.3／§5.1 禁止补零或重复填成
        # n 行 —— 那是伪造动作。所以正确行为是隔离并显式报原因，而不是让它混进普通 TD。
        # 真机上 U 是 t_k 一次前向的产物，不会短缺；这是重放的采集缺口，不是策略缺陷。
        "普通 TD 里每一行 U 都是完整 n 段（短 chunk 不得混入）": (
            fresh["stats"]["n_td"] > 0
            and fresh["n_td_u_complete"] == fresh["stats"]["n_td"]),
        "尾槽 U 不完整 -> 隔离，且原样保留短缺行数（不补帧伪造）": (
            len(fresh["short_u_slots"]) >= 1
            and all(0 <= s["u_rows"] < n for s in fresh["short_u_slots"])
            and any("terminal_u_incomplete" in s["isolation_reasons"]
                    for s in fresh["short_u_slots"])),
        "终局事实仍被保留（terminated/success + 真实 R_L，只是动作未知）": (
            any(s["terminated"] and s["terminal_kind"] in db.TERMINATED_KINDS
                and s["r_slot"] is not None and s["bootstrap_valid"] is False
                for s in fresh["short_u_slots"])),
        "无接管时删失比例为 0": fresh["stats"]["censoring_ratio"] == 0.0,
        "表征版本单一、视图未冻结": fresh["stats"].get("view_frozen") is not True,
        "观测超龄时全部隔离而不是照常用": (
            stale["stats"]["n_td"] == 0
            and stale["stats"]["isolation_reasons"].get("observation_stale", 0) > 0),
        "teacher 本局真实抓取成功（否则只是协议 smoke）": bool(rollout["success"] and rollout["held"]),
        "obs 布局守卫：本局每一帧宽度都等于声明值": layout_ok,
        "obs 布局守卫：宽度漂移会炸（不沿用旧 REPR_VERSION 混表征）": (
            layout_guard_fires
            and REPR_VERSION == f"lift-state-proprio{STATE_DIM}+obj{OBJ_DIM}-v1"),
        # P0-2：定标状态必须与模板一致，且 γ_slot 只算一次落盘（不许下游再做二次幂）。
        "γ/n 标注与模板 timing 定标状态一致（模板未填⇒必须标 assumed）": (
            (report["unit_convention"]["status"] == "assumed")
            == (not report["unit_convention"]["template_timing"].get("all_filled"))),
        "产物把 γ/n 显式标为假设值，且 γ_slot == γ^n（只算一次）": (
            report["gamma_assumed"] == gamma and report["n_assumed"] == n
            and report["unit_convention"]["gamma_is_assumed"]
            and report["unit_convention"]["n_is_assumed"]
            and abs(report["unit_convention"]["gamma_slot"] - gamma ** n) < 1e-15),
        "定标守卫双向成立（未定标却标 measured 会被拒；已定标才放行）": (
            measured_guard.startswith("ValueError") and measured_ok_when_calibrated),
    }
    report["measured_guard"] = {"refusal": measured_guard,
                                "passes_when_calibrated": measured_ok_when_calibrated}
    report["checks"] = [{"name": k, "ok": bool(v)} for k, v in checks.items()]
    report["pass"] = all(checks.values())
    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"fresh: n_td={fresh['stats']['n_td']} isolated={fresh['stats']['n_isolated']} "
          f"pending={fresh['stats']['n_pending']} terminal={fresh['n_td_terminal']} "
          f"c_next_equals_u={fresh['checked']['c_next_equals_u']}/{fresh['n_td_nonterminal']} "
          f"reasons={fresh['stats']['isolation_reasons']}")
    print(f"fresh 尾槽（U 不完整、原样保留不补帧）: {fresh['short_u_slots']}")
    print(f"stale: n_td={stale['stats']['n_td']} isolated={stale['stats']['n_isolated']} "
          f"reasons={stale['stats']['isolation_reasons']}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    print(f"结果: {'PASS' if report['pass'] else 'FAIL'} -> {out}")
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
