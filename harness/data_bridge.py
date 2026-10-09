"""C 线：从事实账本派生训练视图（普通 TD / BC / 候选 / 隔离）。

时间语义与资格判定严格按 v4 附录：
`RL_Harness_v4_20260924/materials/06_.../appendices/02_异步动作时间轴与学习目标.md`
（§3.1 回报与一决策 TD 目标、§3.3 普通样本准入、§4.2 四种 mask、§5 终局、§6.2 抢占隔离、§9 六算例）
与 `appendices/01_接口契约与开发验收.md` §5.3–§5.4。

关键不变量（改这里之前先读上面两节）：

* 一个决策槽 = 一个真实接纳的 request。`X_k=(h,g,C_k,ξ)`、`U_k=E_k` 只取 chunk 的
  `[n,2n)` 段；`R_k=Σ_{j=0..n-1} γ^j r_{t_k+j}` 由**旧 C** 产生，不是 U 自己的物理奖励。
* `γ_slot=γ^n` 只算一次并存下来，避免二次幂。
* `C_next=U_k` 必须由**当时的** next queue 快照证实；后一槽被抢占不改写已经成立的这一步，
  只有边界快照本身不可确认时才连前驱一起隔离。
* 终局（L≤n）用 `R_L` 且 `bootstrap_valid=False`；外部截断（timeout）**不**当 done=1。
* 四种 mask 严格分离：物理执行 / 普通 TD 资格 / BC 监督 / Q 动作梯度只经 E。
* 影子建议（未进 request）永远不得伪 TD：无 reward、无 next state，只进候选池。
* `unknown` 不是失败、不是零奖励；reward pending 不发布也不置零。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .ledger import FactLedger, Row
from .obs_store import ObsStore, StaleObservation, x_refs_of

# 终局 vs 外部截断 vs 需要隔离的异常，三类不能合并（附录 02 §5.3）。
TERMINATED_KINDS = ("success", "environment_done", "goal_reached", "released_stable")
TRUNCATED_KINDS = ("timeout", "budget_exhausted", "horizon_limit", "external_truncation")
ISOLATING_KINDS = ("takeover", "cancel", "deadline_miss", "early_termination",
                   "policy_failure", "unknown", "goal_switch", "version_switch")
DEFAULT_QUALITY_THRESHOLD = 0.5

# 删失（censoring）类隔离理由：附录 02 §5.3 把「Harness 抢占、超时、云服务掉线、日志缺失」
# 归为中断/删失 —— 它们的共同点是**我们不知道后续价值**，所以既不能当终止、也不能当零价值。
# 不在这个元组里的隔离理由分两类，故意不算删失：
#   * 换向族（goal_epoch_mismatch / goal_epoch_incompatible / next_goal_switch）：§5.5 的合法边界，
#     不是信息缺失；
#   * 契约违反族（c_next_not_equal_u / c_not_executed / post_terminal_queue_replaced）：
#     数据本身不合法，不是「没观测到」。
# 口径变更历史见 docs/c_golden_conformance_20260928.md §7（F3）。
CENSORING_REASONS = (
    "takeover_in_slot", "lease_generation_changed", "boundary_unverifiable_before_takeover",
    "deadline_miss", "result_not_committed", "u_unavailable",
    "next_snapshot_unverifiable", "frame_facts_incomplete",
    "reward_unknown", "observation_stale", "observation_age_unknown",
    "u_incomplete", "terminal_u_incomplete", "terminal_u_unknown",
    "terminal_kind:takeover", "terminal_kind:cancel", "terminal_kind:deadline_miss",
    "terminal_kind:unknown",
)


def e_segment_mask(chunk_len: int, n: int) -> tuple[int, ...]:
    """Q 的动作梯度只覆盖 E 段 `[n,2n)`；C 段与丢弃的 D 段为 0（附录 01 §5.4）。"""
    if chunk_len < 2 * n:
        raise ValueError(f"chunk_len {chunk_len} < 2n {2 * n}: 首版要求 H>=2n")
    return tuple(1 if n <= i < 2 * n else 0 for i in range(chunk_len))


def slot_return(rewards: Sequence[float], gamma: float) -> float:
    """`R_k=Σ_{j=0..L-1} γ^j r_{t_k+j}`，L 为实际生效步数（终局时 L≤n）。"""
    total = 0.0
    for j, r in enumerate(rewards):
        total += (gamma ** j) * float(r)
    return total


def td_target(r_slot: float, gamma_slot: float, bootstrap_valid: bool, q_next: float) -> float:
    """`y=R_k+γ^n·bootstrap_valid·Q_target(X_next,π_target(X_next))`。"""
    return float(r_slot) + (float(gamma_slot) * float(q_next) if bootstrap_valid else 0.0)


@dataclass(frozen=True)
class SlotFacts:
    """一个决策槽的全部物理事实（不做资格判定）。"""
    request_id: str
    episode_id: str
    goal_id: str
    epoch: int
    start_frame: int
    n: int
    gamma: float
    gamma_slot: float
    deadline: int | None = None
    committed_frame: int | None = None
    u: tuple | None = None
    u_available: bool = False
    u_complete: bool = False
    c_chunk_id: str | None = None
    rewards: tuple[float, ...] = ()
    reward_state: str = "final"
    r_slot: float | None = None
    terminal_step: int | None = None
    terminal_kind: str = "none"
    executed_indices: tuple[int, ...] = ()
    next_frame: int | None = None
    next_queue: tuple | None = None
    next_queue_matches_u: bool = False
    next_snapshot_verified: bool = False
    execution_window_complete: bool = False
    takeover_in_slot: bool = False
    goal_epoch_break: bool = False
    arrival_goal_id: str | None = None
    arrival_epoch: int | None = None
    c_not_executed: bool = False
    lease_generations: tuple[int, ...] = ()
    frame_seqs: tuple[int, ...] = ()
    event_seqs: tuple[int, ...] = ()
    label_seqs: tuple[int, ...] = ()
    policy_version: str | None = None
    x_ref: str | None = None
    next_x_ref: str | None = None
    x_obs_ref: str | None = None
    next_x_obs_ref: str | None = None
    observation_age_ns: int | None = None
    observation_stale: bool = False
    observation_age_unknown: bool = False
    representation_version: str | None = None


@dataclass(frozen=True)
class TrainingSample:
    """一条派生样本：四种 mask 分开存，`isolation_reasons` 为空才是普通 TD。"""
    request_id: str
    episode_id: str
    goal_id: str
    epoch: int
    start_frame: int
    n: int
    gamma_slot: float
    x_ref: str | None
    u: tuple | None
    r_slot: float | None
    next_x_ref: str | None
    next_queue: tuple | None
    td_valid: bool
    bootstrap_valid: bool
    terminated: bool
    terminal_kind: str
    bc_eligible: bool
    execution_mask: tuple[int, ...] = ()
    supervision_mask: tuple[int, ...] = ()
    supervision_weight: float = 0.0
    q_action_gradient_mask: tuple[int, ...] = ()
    isolation_reasons: tuple[str, ...] = ()
    label_version: str | None = None
    source_seqs: tuple[int, ...] = ()
    bc_action_field: str | None = None

    def target(self, q_next: float) -> float | None:
        return None if not self.td_valid else td_target(self.r_slot or 0.0, self.gamma_slot,
                                                        self.bootstrap_valid, q_next)


@dataclass
class ViewBundle:
    td: list[TrainingSample] = field(default_factory=list)
    bc: list[TrainingSample] = field(default_factory=list)
    candidate: list[dict[str, Any]] = field(default_factory=list)
    isolated: list[TrainingSample] = field(default_factory=list)
    pending: list[TrainingSample] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def _events_by_request(ledger: FactLedger, episode_id: str) -> dict[str, list[Row]]:
    out: dict[str, list[Row]] = {}
    for ev in ledger.events(episode_id=episode_id):
        rid = ev["request_id"]
        if rid:
            out.setdefault(rid, []).append(ev)
    return out


def build_slots(ledger: FactLedger, episode_id: str, *, n: int, gamma: float,
                chunk_len: int | None = None, obs_store: ObsStore | None = None,
                max_age_ns: int | None = None,
                max_sync_error_ns: int | None = None) -> list[SlotFacts]:
    """把账本里的事件与逐帧事实重组成决策槽。`chunk_len` 缺省取 `2n`。"""
    H = chunk_len or 2 * n
    gamma_slot = gamma ** n                      # 只算一次，存进每个槽
    events_by_request = _events_by_request(ledger, episode_id)
    admitted = [ev for ev in ledger.events(episode_id=episode_id, kinds=["request_admitted"])]
    admitted.sort(key=lambda ev: (ev["abs_frame"] if ev["abs_frame"] is not None else 0, ev.seq))
    frames = ledger.frames(episode_id=episode_id)
    by_frame = {int(fr["abs_frame"]): fr for fr in frames}
    labels = ledger.labels(episode_id=episode_id, label_kind="reward")
    # 撤销必须真正生效：账本 append-only 不删原行，所以过滤在读取侧做（附录 01 §5.1）。
    # 撤销 ≠ 零奖励 ≠ 失败：被撤销的帧退回「无标签」⇒ reward_state=unknown ⇒ 进隔离视图，
    # 绝不能当 0 分留在普通 TD 里（那等于用一次误判的 rubric 悄悄改了学习目标）。
    revoked = ledger.revoked_seqs()
    reward_by_frame: dict[int, tuple[float, str, int]] = {}
    for lab in labels:
        if int(lab.seq) in revoked:
            continue
        target = lab["target_seq"]
        frame_row = next((fr for fr in frames if fr.seq == target), None)
        if frame_row is None or lab["value"] is None:
            continue
        # 同一帧多条奖励标签时取最后一条 final；pending 不覆盖 final。
        prev = reward_by_frame.get(int(frame_row["abs_frame"]))
        state = lab["reward_state"] or "final"
        if prev is None or (prev[1] != "final" and state == "final"):
            reward_by_frame[int(frame_row["abs_frame"])] = (float(lab["value"]), state, int(lab.seq))

    slots: list[SlotFacts] = []
    for idx, ev in enumerate(admitted):
        rid = ev["request_id"]
        start = int(ev["abs_frame"])
        prev = admitted[idx - 1] if idx > 0 else None
        # §5.5：换向结束旧目标、清理旧 goal 的队列与推理结果；不跨 g 串接普通 bootstrap。
        goal_break = bool(prev is not None and (str(prev["goal_id"]) != str(ev["goal_id"])
                                                or int(prev["epoch"] or 0) != int(ev["epoch"] or 0)))
        evs = events_by_request.get(rid, [])
        ev_seqs = [int(e.seq) for e in evs]
        commit = next((e for e in evs if e["kind"] == "result_committed"), None)
        takeover = next((e for e in evs if e["kind"] == "takeover"), None)
        expired = next((e for e in evs if e["kind"] in ("expired", "cancelled")), None)
        u_raw = (commit["payload"] or {}).get("u") if commit else None
        u = tuple(u_raw) if u_raw is not None else None
        # 到达时的 in-force goal：取「提交帧之前最近一次被接纳的请求」。§5.5 要求换向时结束
        # 旧目标并清理旧 goal 的推理结果，所以晚到的 U 若在到达时 goal/epoch 已换过，它与当前
        # 目标不相容 —— 这与「错过 deadline」是**两个独立**的拒绝理由，必须分别记录
        # （B 的黄金值 E6 明确要求 `both_reasons_must_be_recorded_separately`）。
        arrival_goal_id, arrival_epoch = None, None
        if commit is not None and commit["abs_frame"] is not None:
            in_force = [e for e in admitted
                        if (e["abs_frame"] if e["abs_frame"] is not None else 0)
                        <= int(commit["abs_frame"])]
            if in_force:
                arrival_goal_id = str(in_force[-1]["goal_id"])
                arrival_epoch = int(in_force[-1]["epoch"] or 0)
        # 本槽 C 来自上一个已提交 request 的 U 段（chunk_id 指回来源 request）。
        prev_rid = admitted[idx - 1]["request_id"] if idx > 0 else None
        # C 的**承诺内容**：§3.3-1 的归属核对要用它逐行比对（见下面 `c_not_executed`）。
        prev_commit = (next((e for e in events_by_request.get(prev_rid, [])
                             if e["kind"] == "result_committed"), None) if prev_rid else None)
        prev_u_raw = (prev_commit["payload"] or {}).get("u") if prev_commit else None
        c_prev_u = tuple(_norm(a) for a in prev_u_raw) if prev_u_raw is not None else None

        # 终局步数 L：槽内第一帧 terminal 之后的步数；缺省为 n。
        term_step, term_kind = None, "none"
        window = [by_frame[f] for f in range(start, start + n) if f in by_frame]
        for offset, fr in enumerate(window):
            payload = fr["payload"] or {}
            if payload.get("terminal"):
                term_step, term_kind = offset + 1, str(payload.get("terminal_kind") or "none")
                break
        length = term_step if term_step is not None else n
        used = window[:length]
        rewards, states, label_seqs = [], [], []
        for fr in used:
            got = reward_by_frame.get(int(fr["abs_frame"]))
            rewards.append(got[0] if got else 0.0)
            states.append(got[1] if got else "unknown")
            if got:
                label_seqs.append(got[2])
        # 优先级 pending > unknown > final：R_k = Σ_{j<n} γ^j r_{t_k+j} 要求槽内**每一帧**都有
        # 可用标签。旧写法是 final 压过 unknown，于是「六帧里撤销/迟到一帧」会静默按 0 计进
        # 完整回报 —— 那等于用一次 rubric 误判悄悄改了学习目标。缺任何一帧就整槽 unknown。
        reward_state = ("pending" if "pending" in states
                        else ("unknown" if "unknown" in states else "final"))
        next_frame = start + length
        next_row = by_frame.get(next_frame)
        # next queue 快照：下一窗口**实测**到的 a_rl 序列，作为 `C_next=U` 的证据留存与人工核对。
        upcoming = [by_frame[f] for f in range(next_frame, next_frame + n) if f in by_frame]
        next_queue = tuple(_norm(fr["a_rl"]) for fr in upcoming) if upcoming else None
        # 但**资格判定**只看两件事（附录 §6.2）：边界帧上承诺的确实是本 request 的 U，且从边界起
        # 归属本 request 的那段前缀逐帧对得上 U 的对应行。前缀之后被 harness 纠正或别的 request
        # 替换，是**下一槽自己的**准入失败（§3.3-1 / §3.3-4），不能倒过来否定这条已经成立的一步
        # 转移 —— 否则一次接管就连带删掉合法数据，正是 B 黄金值 E5-V1 点名的过度删失
        # （裁定与推导见 docs/c_golden_conformance_20260928.md §2）。
        prefix: list[Row] = []
        for fr in upcoming:
            if fr["chunk_id"] != rid:
                break
            prefix.append(fr)
        prefix_ok = bool(u) and bool(prefix) and all(
            i < len(u) and fr["chunk_index"] == n + i and _norm(fr["a_rl"]) == _norm(u[i])
            for i, fr in enumerate(prefix))
        queue_matches = (next_row is not None and next_row["chunk_id"] == rid and prefix_ok)
        exec_window = upcoming
        # U 的物理效果覆盖 [t+n, t+2n)：execution_mask 只能取这一段，不能取本槽的 C 窗口。
        executed = tuple(sorted({int(fr["chunk_index"]) for fr in exec_window
                                 if fr["chunk_id"] == rid and fr["chunk_index"] is not None
                                 and fr["execution_status"] in ("activated", "partially_executed")}))
        kind = term_kind
        if term_step is None and expired is not None:
            kind = "deadline_miss" if expired["kind"] == "expired" else "cancel"
        # §3.3-1：C 必须**真的**按学习动作边界执行过。「命令执行了」不等于「执行的是本槽承诺的 C」
        # （附录 01 §2.1：四种动作量分开存）。接管帧的 `execution_status` 可以是 activated，
        # 但它跑的既不是 C 的 chunk_id、也不是 C 的动作值 ⇒ 同样算 C 未按学习动作边界执行。
        # U 短缺（partial）时只核对已承诺的那几行：短缺本身已由 `u_incomplete` 单独记账，
        # 不在这里重复计一条 `c_not_executed`（否则真机 smoke 的隔离原因集合会被污染）。
        c_not_executed = False
        if prev_rid:
            for fr in used:
                offset = int(fr["abs_frame"]) - start
                if (fr["execution_status"] not in ("activated", "partially_executed")
                        or fr["chunk_id"] != prev_rid
                        or fr["chunk_index"] != n + offset
                        or (c_prev_u is not None and offset < len(c_prev_u)
                            and _norm(fr["a_rl"]) != c_prev_u[offset])):
                    c_not_executed = True
                    break
        # 观测身份与新鲜度：x_ref 优先用内容寻址快照，退回 "<episode>#<frame>"。
        first_frame = used[0] if used else None
        x_obs_ref = first_frame["obs_ref"] if first_frame is not None else None
        next_x_obs_ref = next_row["obs_ref"] if next_row is not None else None
        age_ns, stale, age_unknown, repr_version = None, False, False, None
        if obs_store is not None and x_obs_ref:
            meta = obs_store.meta(x_obs_ref)
            repr_version = meta.representation_version
            decided_at = first_frame["abs_time_ns"] if first_frame is not None else None
            if decided_at is None:
                age_unknown = max_age_ns is not None
            else:
                age_ns = int(decided_at) - int(meta.sampled_at_ns)
                try:
                    obs_store.reuse_as(x_obs_ref, decided_at_ns=int(decided_at),
                                       max_age_ns=max_age_ns if max_age_ns is not None else 1 << 62,
                                       max_sync_error_ns=max_sync_error_ns)
                except StaleObservation:
                    stale = True
        slots.append(SlotFacts(
            request_id=rid, episode_id=episode_id, goal_id=str(ev["goal_id"]), epoch=int(ev["epoch"] or 0),
            start_frame=start, n=n, gamma=gamma, gamma_slot=gamma_slot,
            deadline=(commit["deadline"] if commit else None) or ev["deadline"],
            committed_frame=int(commit["abs_frame"]) if commit else None,
            u=u, u_available=u is not None, c_chunk_id=prev_rid,
            u_complete=bool(u is not None and len(u) == n),
            rewards=tuple(rewards), reward_state=reward_state,
            # 只有 final 才算得出 R_k；pending/unknown 一律 None（rewards 里的 0.0 只是占位，
            # 不能当成「这一帧奖励为 0」被下游读走）。
            r_slot=slot_return(rewards, gamma) if reward_state == "final" else None,
            terminal_step=term_step, terminal_kind=kind,
            executed_indices=executed, next_frame=next_frame, next_queue=next_queue,
            next_queue_matches_u=bool(queue_matches),
            next_snapshot_verified=next_row is not None,
            execution_window_complete=len(exec_window) == n,
            takeover_in_slot=takeover is not None and takeover["abs_frame"] is not None
            and start <= int(takeover["abs_frame"]) < next_frame,
            goal_epoch_break=goal_break,
            arrival_goal_id=arrival_goal_id, arrival_epoch=arrival_epoch,
            c_not_executed=c_not_executed,
            lease_generations=tuple(sorted({int(fr["lease_generation"]) for fr in used})),
            frame_seqs=tuple(int(fr.seq) for fr in used), event_seqs=tuple(ev_seqs),
            label_seqs=tuple(label_seqs),
            policy_version=used[0]["policy_version"] if used else None,
            x_ref=x_obs_ref or f"{episode_id}#{start}",
            next_x_ref=(next_x_obs_ref or f"{episode_id}#{next_frame}") if next_row else None,
            x_obs_ref=x_obs_ref, next_x_obs_ref=next_x_obs_ref,
            observation_age_ns=age_ns, observation_stale=stale,
            observation_age_unknown=age_unknown, representation_version=repr_version,
        ))
    return slots


def _norm(action: Any) -> Any:
    """动作值比较用的规范化：list→tuple，浮点保留原值（不做容差，容差属于 learner 侧）。"""
    if isinstance(action, (list, tuple)):
        return tuple(float(x) for x in action)
    return action


def _classify(slot: SlotFacts, *, n: int, chunk_len: int, label_version: str | None,
              extra_reasons: Sequence[str] = ()) -> TrainingSample:
    """按附录 02 §3.3 的五条准入 + §5/§6 的终局与抢占规则给资格。"""
    reasons: list[str] = list(extra_reasons)
    terminated = slot.terminal_kind in TERMINATED_KINDS
    truncated = slot.terminal_kind in TRUNCATED_KINDS
    if slot.terminal_kind in ISOLATING_KINDS:
        reasons.append(f"terminal_kind:{slot.terminal_kind}")
    if slot.committed_frame is None:
        reasons.append("result_not_committed")
    if slot.deadline is not None and slot.committed_frame is not None and slot.committed_frame > slot.deadline:
        reasons.append("deadline_miss")
    if slot.takeover_in_slot:
        reasons.append("takeover_in_slot")
    if slot.goal_epoch_break:
        reasons.append("goal_epoch_mismatch")
    if (slot.arrival_goal_id is not None
            and (slot.arrival_goal_id != slot.goal_id or slot.arrival_epoch != slot.epoch)):
        # 与 `goal_epoch_mismatch`（本槽相对**前一槽**换向）不同：这条说的是本槽的 U 到达时，
        # in-force 的 goal/epoch 已经不是它请求时那一个。晚到 + 换向必须同时留下两条理由。
        reasons.append("goal_epoch_incompatible")
    if len(slot.lease_generations) > 1:
        reasons.append("lease_generation_changed")
    if slot.c_chunk_id is not None and slot.c_not_executed:
        # §3.3 条件 1：C 必须真的按学习动作边界执行过；"发送成功"不等于"执行完成"。
        reasons.append("c_not_executed")
    if slot.observation_stale:
        # 附录 01 §2.3：超过新鲜度/同步容差的观测不能重打时间戳当新观察。
        reasons.append("observation_stale")
    if slot.observation_age_unknown:
        reasons.append("observation_age_unknown")
    if slot.u_available is False:
        # 终局例外：真实终局可保留原在途 U；拿不到就记 unknown，不伪造动作。
        reasons.append("terminal_u_unknown" if terminated else "u_unavailable")
    elif not slot.u_complete:
        # §3.3 条件 2 要求 U「准时、合法且**完整入队**」：只提交到 L'<n 行的 chunk 不是完整 U。
        # §4.3：learner 只吃固定 n 段时，短缺的行既不能重复也不能补零填成 n 行 —— 那是伪造动作。
        # §5.1：终局拿不到完整 U 就「保留终局事实，但不给它伪造 U」，隔离而不是硬塞进 TD。
        # 真机上 U 是 t_k 一次前向的产物，不会短缺；短缺只出现在录制到一半就停的重放/采集中，
        # 属于数据采集缺口，必须显式暴露成隔离原因，不能靠下游补帧掩盖。
        reasons.append("terminal_u_incomplete" if terminated else "u_incomplete")
    if slot.reward_state == "pending":
        reasons.append("reward_pending")
    if slot.reward_state == "unknown":
        reasons.append("reward_unknown")
    if not terminated and not truncated:
        if not slot.next_snapshot_verified:
            reasons.append("next_snapshot_unverifiable")
        elif not slot.next_queue_matches_u:
            reasons.append("c_next_not_equal_u")
        if len(slot.frame_seqs) < n:
            reasons.append("frame_facts_incomplete")
    if truncated and not slot.next_snapshot_verified:
        # 外部截断不冒充 done=1，但也没有可 bootstrap 的后继状态。
        reasons.append("truncated_without_next_snapshot")
    if terminated and slot.next_snapshot_verified and not slot.next_queue_matches_u:
        # 真实终局之后不该还有另一个队列在生效：说明存在未建模的中途队列替换（§3.3 条件 4）。
        reasons.append("post_terminal_queue_replaced")
    execution_mask = tuple(1 if i in slot.executed_indices else 0 for i in range(chunk_len))
    return TrainingSample(
        request_id=slot.request_id, episode_id=slot.episode_id, goal_id=slot.goal_id,
        epoch=slot.epoch, start_frame=slot.start_frame, n=n, gamma_slot=slot.gamma_slot,
        x_ref=slot.x_ref, u=slot.u, r_slot=slot.r_slot, next_x_ref=slot.next_x_ref,
        next_queue=slot.next_queue, td_valid=not reasons,
        bootstrap_valid=not terminated and bool(slot.next_snapshot_verified),
        terminated=terminated, terminal_kind=slot.terminal_kind,
        bc_eligible=False, execution_mask=execution_mask,
        q_action_gradient_mask=e_segment_mask(chunk_len, n),
        isolation_reasons=tuple(dict.fromkeys(reasons)), label_version=label_version,
        source_seqs=slot.frame_seqs + slot.event_seqs + slot.label_seqs)


def build_views(ledger: FactLedger, *, n: int, gamma: float, episode_ids: Iterable[str] | None = None,
                chunk_len: int | None = None, label_version: str | None = None,
                quality_threshold: float = DEFAULT_QUALITY_THRESHOLD,
                bc_sources: Sequence[str] = ("harness", "teleop"),
                obs_store: ObsStore | None = None, max_age_ns: int | None = None,
                max_sync_error_ns: int | None = None) -> ViewBundle:
    """派生四种视图。`episode_ids` 缺省为账本里出现过的全部 episode。"""
    H = chunk_len or 2 * n
    bundle = ViewBundle()
    if episode_ids is None:
        rows = ledger.conn.execute("SELECT DISTINCT episode_id FROM frame_fact ORDER BY episode_id").fetchall()
        episode_ids = [r["episode_id"] for r in rows]
    all_slots: list[SlotFacts] = []
    extra_reasons: dict[str, tuple[str, ...]] = {}
    for episode_id in episode_ids:
        slots = build_slots(ledger, episode_id, n=n, gamma=gamma, chunk_len=H,
                            obs_store=obs_store, max_age_ns=max_age_ns,
                            max_sync_error_ns=max_sync_error_ns)
        # §6.2：抢占槽自身隔离；若边界快照不可确认，连前驱一起隔离，范围只限不可确认区间。
        for i, slot in enumerate(slots):
            if slot.takeover_in_slot and i > 0 and not slots[i - 1].next_snapshot_verified:
                prev_reasons = extra_reasons.get(slots[i - 1].request_id, ())
                extra_reasons[slots[i - 1].request_id] = prev_reasons + (
                    "boundary_unverifiable_before_takeover",)
            if slot.goal_epoch_break and i > 0:
                prev_reasons = extra_reasons.get(slots[i - 1].request_id, ())
                extra_reasons[slots[i - 1].request_id] = prev_reasons + ("next_goal_switch",)
        all_slots.extend(slots)

    for slot in all_slots:
        sample = _classify(slot, n=n, chunk_len=H, label_version=label_version,
                           extra_reasons=extra_reasons.get(slot.request_id, ()))
        if "reward_pending" in sample.isolation_reasons:
            bundle.pending.append(sample)
        elif sample.td_valid:
            bundle.td.append(sample)
        else:
            bundle.isolated.append(sample)

    # BC 视图：真实执行过的纠正（frame.source ∈ bc_sources）+ 质量合格的标签，
    # supervision_mask 用真实 valid_indices，不截成 E 段（附录 01 §5.4）。
    frame_rows = ledger.frames()
    bc_frames = [fr for fr in frame_rows if fr["source"] in tuple(bc_sources)]
    quality: dict[int, float] = {}
    revoked = ledger.revoked_seqs()
    for lab in ledger.labels(label_kind="quality"):
        if int(lab.seq) in revoked:
            continue
        if lab["target_seq"] is not None and lab["value"] is not None:
            quality[int(lab["target_seq"])] = float(lab["value"])
    bc_skipped = {"no_action": 0, "no_chunk_index": 0, "low_quality": 0}
    for fr in bc_frames:
        weight = quality.get(int(fr.seq), 1.0)
        if weight < quality_threshold:
            bc_skipped["low_quality"] += 1
            continue
        # BC 目标是「真实下发的那条命令」：policy 帧取 `a_rl`；harness/recovery 纠正帧按契约
        # `a_rl` 必须是 None（那不是学习器产生的动作），命令在 `driver_command` 里。
        # 旧写法一律取 `a_rl` ⇒ 所有纠正帧 u=None，纠正数据永远进不了监督，
        # 而 n_bc 照样非零 —— H1/H2 想验证的「从纠正中学」会在数据层就悄悄落空。
        action_field, action_row = (("a_rl", fr["a_rl"]) if fr["a_rl"] is not None
                                    else ("driver_command", fr["driver_command"]))
        if action_row is None:
            bc_skipped["no_action"] += 1        # 没有可监督的命令：宁可不产样本，也不填 0
            continue
        valid = [fr["chunk_index"]] if fr["chunk_index"] is not None else []
        if not valid:
            # 没有 chunk_index 就没法把这条命令放进 H 维监督布局；产出全零 mask 的样本只会
            # 让 n_bc 好看而梯度恒为 0。纠正要可训，必须带自己的 chunk_id/chunk_index。
            bc_skipped["no_chunk_index"] += 1
            continue
        bundle.bc.append(TrainingSample(
            request_id=str(fr["request_id"] or ""), episode_id=fr["episode_id"],
            goal_id=str(fr["goal_id"]), epoch=int(fr["epoch"] or 0),
            start_frame=int(fr["abs_frame"]), n=n, gamma_slot=gamma ** n,
            # x_ref 语义与槽侧统一：优先内容地址快照，退回 "<episode>#<frame>"。
            # 旧写法在 BC 行上只写字符串 id，learner 拿到分片后 `resolve_x()` 一律 KeyError
            # ⇒ 纠正帧有动作标签却没有观测，BC 那一路根本装配不成张量。
            x_ref=(fr["obs_ref"] or f"{fr['episode_id']}#{int(fr['abs_frame'])}"),
            u=_norm(action_row), r_slot=None,
            next_x_ref=None, next_queue=None, td_valid=False, bootstrap_valid=False,
            terminated=False, terminal_kind="none", bc_eligible=True,
            execution_mask=tuple(1 if i == fr["chunk_index"] else 0 for i in range(H)),
            supervision_mask=tuple(1 if i in valid else 0 for i in range(H)),
            supervision_weight=weight, q_action_gradient_mask=(0,) * H,
            label_version=label_version, source_seqs=(int(fr.seq),),
            bc_action_field=action_field))

    # 候选视图：影子建议只有动作标签，绝不配 reward / next state（附录 01 §5.4）。
    for prop in ledger.proposals():
        if prop["admitted"]:
            continue
        if prop["quality"] is not None and float(prop["quality"]) < quality_threshold:
            continue
        valid = list(prop["valid_indices"] or [])
        bundle.candidate.append({
            "proposal_seq": int(prop.seq), "episode_id": prop["episode_id"],
            "goal_id": prop["goal_id"], "abs_frame": prop["abs_frame"],
            "source": prop["source"], "action": prop["action"],
            "supervision_mask": tuple(1 if i in valid else 0 for i in range(H)) if valid else (),
            "observation_ref": prop["observation_ref"], "quality": prop["quality"],
            "reward": None, "next_x_ref": None, "td_valid": False,
        })

    bundle.stats = compute_stats(bundle, all_slots, n=n)
    bundle.stats["revoked_labels"] = len(revoked)
    bundle.stats["bc_skipped"] = bc_skipped
    if obs_store is not None:
        # 一个训练视图只能有一个表征/归一化版本；混了就冻结视图，不静默混用。
        check = obs_store.assert_single_representation(x_refs_of(bundle.td), view_name="td",
                                                       ignore_unknown=True)
        bundle.stats["representation_check"] = check
        bundle.stats["view_frozen_reasons"] = check["problems"]
        bundle.stats["view_frozen"] = bool(check["problems"])
    return bundle


def resolve_x(obs_store: ObsStore, sample: TrainingSample, *, which: str = "x") -> dict[str, Any] | None:
    """把训练样本的 `x_ref` 解析回原始观测数组，供 learner 重算表征。"""
    ref = sample.x_ref if which == "x" else sample.next_x_ref
    if not ref:
        return None
    try:
        return obs_store.get(ref)
    except KeyError:
        return None


def compute_stats(bundle: ViewBundle, slots: Sequence[SlotFacts], *, n: int) -> dict[str, Any]:
    """删失比例、pending/unknown 计数、双向覆盖 —— 报告用，不参与资格判定。

    删失给两个口径，因为分母不一样、会被误读：
    - `censoring_ratio` 的分母是**被决策槽覆盖到的帧**。接管之后策略不再被询问，那段帧
      没有任何槽，于是既不进分子也不进分母 ⇒ 接管越久这个比例反而可能越小。
    - `censoring_slot_ratio` 的分母是全部决策槽，不受上面这条影响，跨 run 比较更稳。
    报告删失时两个都要给，只给前者会低估长接管的代价。

    上面两个是**窄口径（只算接管）**，已被 `c_contract_lift_*_smoke.py` 消费，语义不动。
    §5.3 的删失其实还包含超时/掉线/日志缺失，所以另给**宽口径**：`censored_slots` /
    `censored_slot_ratio` / `censoring_by_reason`，判据是 `CENSORING_REASONS`。
    B 的黄金值 E6 要求「晚到被拒」也 `counted_toward_censoring_ratio: true`，对的是宽口径。
    """
    takeover_frames = sum(len(s.frame_seqs) for s in slots if s.takeover_in_slot)
    total_frames = sum(len(s.frame_seqs) for s in slots) or 1
    takeover_slots = sum(1 for s in slots if s.takeover_in_slot)
    censored_requests = sorted({sample.request_id for sample in bundle.isolated
                                if set(sample.isolation_reasons) & set(CENSORING_REASONS)})
    censoring_by_reason: dict[str, int] = {}
    for sample in bundle.isolated:
        for reason in set(sample.isolation_reasons) & set(CENSORING_REASONS):
            censoring_by_reason[reason] = censoring_by_reason.get(reason, 0) + 1
    per_goal: dict[str, int] = {}
    for sample in bundle.td:
        per_goal[sample.goal_id] = per_goal.get(sample.goal_id, 0) + 1
    reasons: dict[str, int] = {}
    for sample in bundle.isolated:
        for reason in sample.isolation_reasons:
            reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "n_slots": len(slots), "n_td": len(bundle.td), "n_bc": len(bundle.bc),
        "n_candidate": len(bundle.candidate), "n_isolated": len(bundle.isolated),
        "n_pending": len(bundle.pending),
        "censoring_ratio": round(takeover_frames / total_frames, 6),
        "censoring_slot_ratio": round(takeover_slots / (len(slots) or 1), 6),
        "censored_slots": len(censored_requests),
        "censored_slot_ratio": round(len(censored_requests) / (len(slots) or 1), 6),
        "censored_requests": censored_requests,
        "censoring_by_reason": dict(sorted(censoring_by_reason.items())),
        "td_per_goal": per_goal, "isolation_reasons": reasons,
        "n_unknown_reward": sum(1 for s in bundle.isolated if "reward_unknown" in s.isolation_reasons),
        "slot_budget_n": n,
    }


def write_manifests(ledger: FactLedger, bundle: ViewBundle, *, run_id: str, gamma: float, n: int,
                    label_version: str | None = None, notes: str = "") -> dict[str, str]:
    """每个视图写一份 manifest，使任一训练样本都能反查原始证据、并支持撤销追踪。"""
    out: dict[str, str] = {}
    specs = (("td", bundle.td), ("bc", bundle.bc), ("isolated", bundle.isolated),
             ("pending", bundle.pending))
    for view_name, samples in specs:
        manifest_id = f"{run_id}:{view_name}"
        ledger.record_view_manifest(
            manifest_id=manifest_id, view_name=view_name, sample_count=len(samples), gamma=gamma, n=n,
            label_version=label_version, filter_rules={"stats": bundle.stats},
            source_seqs=[seq for s in samples for seq in s.source_seqs],
            affected_requests=[s.request_id for s in samples if s.request_id], notes=notes)
        out[view_name] = manifest_id
    manifest_id = f"{run_id}:candidate"
    ledger.record_view_manifest(
        manifest_id=manifest_id, view_name="candidate", sample_count=len(bundle.candidate),
        gamma=gamma, n=n, label_version=label_version,
        filter_rules={"rule": "shadow proposals: action label only, no reward/next state"},
        source_seqs=[c["proposal_seq"] for c in bundle.candidate], notes=notes)
    out["candidate"] = manifest_id
    return out


# ---------------------------------------------------------------------------
# 视图导出：让 learner 进程**真的**能读到这四个视图
# ---------------------------------------------------------------------------
# 为什么必须有这一层：视图停在内存里等于没有。learner（RLinf / LeRobot）跑在另一个进程、
# 另一套依赖里，它只应该读到「已经定资格、定 mask、定 label_version」的行，
# 而不是自己再去 join 账本 —— 否则资格判定会在两处各写一遍并悄悄分叉。
#
# 三条导出纪律：
#   1. **五个视图各自一个文件，永不合并**。把 isolated/pending 混进 td 就等于把
#      "不确定"当"失败"训（附录 02 §7）。空视图也要落 0 行文件，让 learner 能分清
#      "这一轮没有合格样本"和"忘了导"。
#   2. **只导 ref，不导表征**。`x_ref` 指向 ObsStore 的内容地址；learner 需要数组时
#      自己 `resolve_x()` 重算。导出缓存好的表征再让别人当新表征用，正是附录 01 §5.1
#      禁止的那件事。
#   3. **带内容身份**。manifest 记每个文件的 sha256 与行数，`load_views(verify=True)`
#      重新核对；对不上就抛，不静默读半截数据。

VIEW_NAMES = ("td", "bc", "candidate", "isolated", "pending")

SAMPLE_COLUMNS = (
    "view", "request_id", "episode_id", "goal_id", "epoch", "start_frame", "n", "gamma_slot",
    "x_ref", "next_x_ref", "r_slot", "td_valid", "bootstrap_valid", "terminated",
    "terminal_kind", "bc_eligible", "supervision_weight", "bc_action_field", "label_version",
    "representation_version", "u", "next_queue", "execution_mask", "supervision_mask",
    "q_action_gradient_mask", "isolation_reasons", "source_seqs",
)
CANDIDATE_COLUMNS = (
    "view", "proposal_seq", "episode_id", "goal_id", "abs_frame", "source", "quality",
    "observation_ref", "reward", "next_x_ref", "td_valid", "label_version",
    "representation_version", "action", "supervision_mask",
)
_JSON_FIELDS = ("u", "next_queue", "execution_mask", "supervision_mask",
                "q_action_gradient_mask", "isolation_reasons", "source_seqs", "action")


class ViewExportTampered(RuntimeError):
    """导出内容与 manifest 记的身份不一致（被改过、写半截、或换了表征版本）。"""


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _enc(value: Any) -> str | None:
    """变长字段（动作块 / mask / seq 列表）统一存 JSON 文本，schema 不随 n 与 H 变。"""
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    return json.dumps([_enc_item(v) for v in value] if isinstance(value, (list, tuple)) else value,
                      ensure_ascii=False)


def _enc_item(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_enc_item(v) for v in value]
    return value


def sample_to_row(sample: TrainingSample, *, view: str,
                  representation_version: str | None = None) -> dict[str, Any]:
    """一条派生样本 → 一行平面记录（四种 mask 各占一列，谁也不代替谁）。"""
    return {
        "view": view, "request_id": sample.request_id, "episode_id": sample.episode_id,
        "goal_id": sample.goal_id, "epoch": sample.epoch, "start_frame": sample.start_frame,
        "n": sample.n, "gamma_slot": sample.gamma_slot, "x_ref": sample.x_ref,
        "next_x_ref": sample.next_x_ref, "r_slot": sample.r_slot, "td_valid": sample.td_valid,
        "bootstrap_valid": sample.bootstrap_valid, "terminated": sample.terminated,
        "terminal_kind": sample.terminal_kind, "bc_eligible": sample.bc_eligible,
        "supervision_weight": sample.supervision_weight, "bc_action_field": sample.bc_action_field,
        "label_version": sample.label_version, "representation_version": representation_version,
        "u": _enc(sample.u), "next_queue": _enc(sample.next_queue),
        "execution_mask": _enc(sample.execution_mask),
        "supervision_mask": _enc(sample.supervision_mask),
        "q_action_gradient_mask": _enc(sample.q_action_gradient_mask),
        "isolation_reasons": _enc(list(sample.isolation_reasons)),
        "source_seqs": _enc(list(sample.source_seqs)),
    }


def candidate_to_row(item: dict[str, Any], *, label_version: str | None = None,
                     representation_version: str | None = None) -> dict[str, Any]:
    """候选（影子建议）行：`reward` / `next_x_ref` 恒为 None，导出也不许补上。"""
    return {
        "view": "candidate", "proposal_seq": item.get("proposal_seq"),
        "episode_id": item.get("episode_id"), "goal_id": item.get("goal_id"),
        "abs_frame": item.get("abs_frame"), "source": item.get("source"),
        "quality": item.get("quality"), "observation_ref": item.get("observation_ref"),
        "reward": None, "next_x_ref": None, "td_valid": False, "label_version": label_version,
        "representation_version": representation_version,
        "action": _enc(item.get("action")), "supervision_mask": _enc(item.get("supervision_mask")),
    }


def export_views(bundle: ViewBundle, out_dir: str | Path, *, run_id: str, n: int, gamma: float,
                 label_version: str | None = None, obs_store: ObsStore | None = None,
                 fmt: str = "parquet", notes: str = "",
                 unit_convention: dict[str, Any] | None = None) -> dict[str, Any]:
    """把五个视图写成分片 + `manifest.json`，返回 manifest 内容。

    `fmt="parquet"`（默认，learner 侧零解析成本）或 `"jsonl"`（无 pyarrow 依赖时的兜底）。
    传了 `obs_store` 就把每行的 `representation_version` 一并落盘，learner 可以据此拒绝
    混版本的批次，而不是事后靠猜。

    传了 `unit_convention`（P0-2，docs/c_golden_conformance_20260928.md §8）就把 γ/n 的
    **定标状态**（assumed / measured / spec）一并写进 manifest：分片是另一个进程的 learner
    真正读到的东西，定标状态只留在 smoke 报告里等于换进程就丢。γ/n 或 γ_slot 对不上直接抛，
    不许把 B 黄金值那套约定（γ=0.9, n=6）贴到用别的 γ/n 导出的分片上。
    """
    if fmt not in ("parquet", "jsonl"):
        raise ValueError(f"unknown export fmt: {fmt!r}")
    if unit_convention is not None:
        import math

        gamma_slot = gamma ** n
        if (int(unit_convention.get("n", -1)) != n
                or not math.isclose(float(unit_convention.get("gamma", math.nan)), gamma,
                                    rel_tol=1e-12, abs_tol=0.0)
                or not math.isclose(float(unit_convention.get("gamma_slot", math.nan)), gamma_slot,
                                    rel_tol=1e-12, abs_tol=0.0)):
            raise ValueError(
                f"unit_convention 与本次导出的 γ/n 不一致: convention={unit_convention} "
                f"export gamma={gamma} n={n} gamma_slot={gamma_slot}")
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    def _repr_of(x_ref: str | None) -> str | None:
        if obs_store is None or not x_ref:
            return None
        try:
            return obs_store.meta(x_ref).representation_version
        except KeyError:
            return None

    rows_by_view: dict[str, list[dict[str, Any]]] = {}
    for view, samples in (("td", bundle.td), ("bc", bundle.bc),
                          ("isolated", bundle.isolated), ("pending", bundle.pending)):
        rows_by_view[view] = [sample_to_row(s, view=view,
                                            representation_version=_repr_of(s.x_ref))
                              for s in samples]
    rows_by_view["candidate"] = [
        candidate_to_row(c, label_version=label_version,
                         representation_version=_repr_of(c.get("observation_ref")))
        for c in bundle.candidate]

    ext = "parquet" if fmt == "parquet" else "jsonl"
    files: dict[str, Any] = {}
    for view in VIEW_NAMES:
        rows = rows_by_view[view]
        columns = list(CANDIDATE_COLUMNS if view == "candidate" else SAMPLE_COLUMNS)
        path = root / f"{view}.{ext}"
        if fmt == "parquet":
            import pandas as pd

            pd.DataFrame(rows, columns=columns).to_parquet(path, index=False)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps({c: row.get(c) for c in columns},
                                        ensure_ascii=False, default=str) + "\n")
        files[view] = {"path": str(path.relative_to(root)), "rows": len(rows),
                       "sha256": _sha256(path), "columns": columns}

    manifest = {
        "run_id": run_id, "n": n, "gamma": gamma, "gamma_slot": gamma ** n,
        "label_version": label_version, "fmt": fmt, "notes": notes,
        "views": files, "stats": bundle.stats,
        "representation_versions": sorted({r["representation_version"]
                                           for rows in rows_by_view.values() for r in rows
                                           if r.get("representation_version")}),
        "invariant": ("td 只含 td_valid=True 的行；isolated/pending/candidate 各自独立文件，"
                      "永不合并进 td；只导 x_ref，不导表征"),
    }
    if unit_convention is not None:
        manifest["unit_convention"] = unit_convention
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                                   default=str) + "\n")
    return manifest


def load_views(out_dir: str | Path, *, verify: bool = True) -> tuple[dict[str, list[dict]], dict]:
    """读回导出的视图。`verify=True` 时先核 sha256 与行数，对不上直接抛。

    JSON 列还原成 list/tuple，parquet 的 NaN 还原成 None —— 否则 learner 会把
    「r_slot 未知」读成 0.0，那正是 §7 里 `unknown` 不许当零奖励的那条红线。
    """
    import math

    root = Path(out_dir)
    manifest = json.loads((root / "manifest.json").read_text())
    fmt = manifest.get("fmt", "parquet")
    out: dict[str, list[dict]] = {}
    for view, meta in manifest["views"].items():
        path = root / meta["path"]
        if not path.exists():
            raise ViewExportTampered(f"{view} 分片不存在: {path}")
        if verify and _sha256(path) != meta["sha256"]:
            raise ViewExportTampered(f"{view} 分片内容与 manifest 不符: {path}")
        if fmt == "parquet":
            import pandas as pd

            frame = pd.read_parquet(path)
            rows = frame.to_dict("records")
        else:
            rows = [json.loads(line) for line in
                    path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if verify and len(rows) != meta["rows"]:
            raise ViewExportTampered(f"{view} 行数不符: {len(rows)} != {meta['rows']}")
        for row in rows:
            for key, value in list(row.items()):
                if isinstance(value, float) and math.isnan(value):
                    row[key] = None
                if key in _JSON_FIELDS and isinstance(value, str):
                    row[key] = json.loads(value)
        out[view] = rows
    return out, manifest
