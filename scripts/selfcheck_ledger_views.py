#!/usr/bin/env python3
"""C 线自检：事实账本 + 四种训练视图，对 v4 附录 02 §9 的六个手核算例。

与既有 `scripts/selfcheck_harness_contracts.py`（只测内存态 `ReplayDriver`）互补：
这里测**持久账本 → 派生视图**这一段，即 appendices/01 §5.1 的五类数据对象与
appendices/02 §3.3 的普通样本准入。全部离线、不训练、不联网、不碰 robosuite。

用法：
    /root/venvs/rlrobot/bin/python scripts/selfcheck_ledger_views.py
    /root/venvs/rlrobot/bin/python scripts/selfcheck_ledger_views.py -v   # 打印每条断言
产物：runs/infra/c_ledger_selfcheck.json（判定）+ runs/infra/c_ledger_selfcheck/*.db（可复查账本）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("torch")

from harness import data_bridge as db  # noqa: E402
from harness.ledger import FactLedger  # noqa: E402

OUT_JSON = ROOT / "runs" / "infra" / "c_ledger_selfcheck.json"
# 账本是 append-only：同一份 .db 重跑会叠加旧事实，所以每次跑用独立子目录，
# 旧产物按时间戳保留（工作区禁止 rm，需要清理时 mv 到 recycle_bin）。
OUT_DIR = ROOT / "runs" / "infra" / "c_ledger_selfcheck" / time.strftime("%Y%m%d_%H%M%S")


class EpisodeBuilder:
    """按附录 02 §1 的时间轴把一个决策槽写进账本。

    槽 k：request `Rk` 在 `t_k` 被接纳；本槽物理执行的 C 是**上一个** request 的 U
    （`chunk_id=R_{k-1}`、`chunk_index ∈ [n,2n)`）；本槽提交的 `U_k` 在
    `[t_k+n, t_k+2n)` 生效，构成下一条转移的回报来源。
    """

    def __init__(self, ledger: FactLedger, episode_id: str, *, n: int, goal: str = "lift",
                 epoch: int = 1, lease: int = 0, policy_version: str = "v1"):
        self.ledger, self.episode_id, self.n = ledger, episode_id, n
        self.goal, self.epoch, self.lease, self.policy_version = goal, epoch, lease, policy_version
        self.prev_rid: str | None = None
        self.prev_u: tuple | None = None
        self.frames_written = 0

    def add_slot(self, rid: str, start: int, *, u: tuple, rewards: list[float],
                 commit_frame: int | None = None, deadline: int | None = None,
                 commit: bool = True, terminal_step: int | None = None,
                 terminal_kind: str = "success", takeover_frame: int | None = None,
                 c_override: tuple | None = None, write_frames: bool = True,
                 reward_state: str = "final", source: str = "policy",
                 goal: str | None = None, epoch: int | None = None,
                 lease: int | None = None, exec_status: str | None = None,
                 obs_ref_of: Any = None, time_ns_of: Any = None) -> None:
        n = self.n
        goal = goal or self.goal
        epoch = self.epoch if epoch is None else epoch
        lease = self.lease if lease is None else lease
        c = list(c_override if c_override is not None else (self.prev_u or ()))
        length = terminal_step if terminal_step is not None else n
        if write_frames:
            for j in range(length):
                frame = start + j
                seq = self.ledger.append_frame(
                    episode_id=self.episode_id, abs_frame=frame, goal_id=goal, epoch=epoch,
                    lease_generation=lease, source=source if self.prev_rid else "hold",
                    execution_status=exec_status or ("activated" if self.prev_rid else "not_activated"),
                    request_id=self.prev_rid, chunk_id=self.prev_rid,
                    chunk_index=(n + j) if self.prev_rid else None,
                    a_rl=(c[j] if j < len(c) else None),
                    measured_state={"obs_ref": f"{self.episode_id}#{frame}"},
                    policy_version=self.policy_version,
                    obs_ref=(obs_ref_of(frame) if callable(obs_ref_of) else None),
                    abs_time_ns=(time_ns_of(frame) if callable(time_ns_of) else None),
                    payload={"terminal": terminal_step is not None and j == terminal_step - 1,
                             "terminal_kind": terminal_kind if (terminal_step is not None and
                                                                j == terminal_step - 1) else "none"})
                self.frames_written += 1
                value = rewards[j] if j < len(rewards) else 0.0
                self.ledger.append_label(episode_id=self.episode_id, label_kind="reward",
                                         target_seq=seq, target_request_id=self.prev_rid,
                                         value=value, reward_state=reward_state, source="env")
        self.ledger.append_event(episode_id=self.episode_id, kind="request_received",
                                 request_id=rid, abs_frame=start, epoch=epoch, goal_id=goal,
                                 deadline=deadline, lease_generation=lease)
        self.ledger.append_event(episode_id=self.episode_id, kind="request_admitted",
                                 request_id=rid, abs_frame=start, epoch=epoch, goal_id=goal,
                                 deadline=deadline, lease_generation=lease)
        if commit:
            self.ledger.append_event(episode_id=self.episode_id, kind="result_committed",
                                     request_id=rid, abs_frame=commit_frame if commit_frame is not None
                                     else start, epoch=epoch, goal_id=goal, deadline=deadline,
                                     lease_generation=lease, payload={"u": list(u)})
        if takeover_frame is not None:
            self.ledger.append_event(episode_id=self.episode_id, kind="takeover", request_id=rid,
                                     abs_frame=takeover_frame, epoch=epoch, goal_id=goal,
                                     lease_generation=lease, payload={"by": "harness"})
        self.prev_rid, self.prev_u = rid, tuple(u)

    def shadow_proposal(self, proposal_action: tuple, *, frame: int, quality: float = 0.9,
                        source: str = "harness_shadow", valid_indices: list[int] | None = None,
                        goal: str | None = None) -> int:
        return self.ledger.append_proposal(
            episode_id=self.episode_id, goal_id=goal or self.goal, source=source, admitted=False,
            action=[list(a) for a in proposal_action], abs_frame=frame, quality=quality,
            valid_indices=valid_indices if valid_indices is not None else [self.n, self.n + 1],
            observation_ref=f"{self.episode_id}#{frame}")


def action(base: float, n: int, dim: int = 3) -> tuple:
    """一段 U：n 个动作，每个 dim 维（首版 U=E 段，长度就是 n）。"""
    return tuple(tuple(round(base + 0.01 * j + 0.001 * i, 6) for i in range(dim)) for j in range(n))


def open_ledger(name: str) -> FactLedger:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return FactLedger(OUT_DIR / f"{name}.db")


def sample_of(bundle: db.ViewBundle, rid: str, *, view: str = "td") -> db.TrainingSample | None:
    pool = {"td": bundle.td, "isolated": bundle.isolated, "pending": bundle.pending}[view]
    return next((s for s in pool if s.request_id == rid), None)


# ---------------- 例 1：正常三段与一槽 TD ----------------
def case1_normal_three_segments(checks: list) -> None:
    n, gamma = 6, 0.99
    with open_ledger("case1") as led:
        b = EpisodeBuilder(led, "ep1", n=n)
        u1, u2, u3 = action(1.0, n), action(2.0, n), action(3.0, n)
        # t=100 起三槽；H=2n=12（首版要求 H>=2n），U 用 proposal 索引 6-11。
        b.add_slot("R1", 100, u=u1, rewards=[0.1] * n)
        b.add_slot("R2", 106, u=u2, rewards=[0.2] * n)
        b.add_slot("R3", 112, u=u3, rewards=[0.3] * n)
        bundle = db.build_views(led, n=n, gamma=gamma)
        s1 = sample_of(bundle, "R1")
        checks.append(("例1 R1 进普通 TD", s1 is not None and s1.td_valid))
        # 回报覆盖帧 100-105，折扣 γ^6，next state 是帧 106 的观测与队列 C_next=U。
        expect_r = sum(gamma ** j * 0.1 for j in range(n))
        checks.append(("例1 R1 回报覆盖 100-105", s1 is not None and abs(s1.r_slot - expect_r) < 1e-12))
        checks.append(("例1 γ_slot=γ^6 只算一次", s1 is not None and abs(s1.gamma_slot - gamma ** n) < 1e-12))
        checks.append(("例1 next state 是帧 106 而非 112",
                       s1 is not None and s1.next_x_ref == "ep1#106"))
        checks.append(("例1 C_next=U（逐值相等）", s1 is not None and s1.next_queue == u1))
        checks.append(("例1 execution_mask 命中索引 6-11",
                       s1 is not None and s1.execution_mask[n:2 * n] == (1,) * n
                       and sum(s1.execution_mask) == n))
        checks.append(("例1 R2 同样成立（三段链）", sample_of(bundle, "R2") is not None))
        # 最后一槽没有 next 快照 -> 不得伪造成普通 TD。
        s3 = sample_of(bundle, "R3", view="isolated")
        checks.append(("例1 末槽缺 next 快照被隔离",
                       s3 is not None and "next_snapshot_unverifiable" in s3.isolation_reasons))


# ---------------- 例 2：梯度只经过可选的 E ----------------
def case2_gradient_only_through_e(checks: list) -> None:
    """附录 02 例2：Q 的动作梯度只经 E 段。

    ## 构造要点（旧写法是假绿，别退回去）

    不能用 `0.0 * c_pred` 这种「乘 0 挂到图上」的探针：那样 `grad_c` 恒等于 0，
    **与拼装规则无关** —— 哪怕把 C 段错接成策略自己的预测，断言照样通过，
    它证明的只是「0 乘任何数得 0」。同理，把 D 段探针直接拼进 chunk，量到的是
    Q 对 D *输入*的敏感度（本来就该非 0），不是「策略的 D 预测有没有拿到梯度」。

    正确做法：用**一个** `full` 张量代表完整头的整块 H 长预测，按契约规则拼装
    （C 段取 `sg(C)` 常量、E 段取 `full[n:2n]`、D 段取零常量），再对 `full` 求导按段切片。
    这个构造可证伪：把 `c_const` 换成 `full[:n]`，C 段立刻亮起来 —— 下面就显式跑一遍。
    动作维度取 1，便于手核；learner 侧同构实现见
    `harness/queue_td_learner.py::gradient_isolation_report`。
    """
    import torch
    n, H = 6, 20
    tail = H - 2 * n
    mask = db.e_segment_mask(H, n)
    checks.append(("例2 mask 只覆盖 [n,2n)", sum(mask) == n and set(mask[:n]) == {0}
                   and set(mask[2 * n:]) == {0}))
    torch.manual_seed(0)
    q_weight = torch.randn(H)
    c_const = torch.randn(n)                      # 已承诺的 C：常量，sg(C)
    d_const = torch.zeros(tail)                   # D 段：补零常量

    def assemble(full: torch.Tensor, *, wrong_c: bool = False, wrong_d: bool = False):
        """按契约拼 H 长 chunk 再算 -Q。wrong_* 是故意写错的对照分支。"""
        parts = [full[:n] if wrong_c else c_const, full[n:2 * n],
                 full[2 * n:] if wrong_d else d_const]
        return -(q_weight * torch.cat(parts)).sum()

    full = torch.randn(H, requires_grad=True)
    loss = assemble(full)
    grad = torch.autograd.grad(loss, full)[0]
    checks.append(("例2 Q 对 C 段预测的动作梯度为 0（来自 sg(C)，不是乘 0 造出来的）",
                   float(grad[:n].abs().max()) == 0.0))
    checks.append(("例2 Q 对 D 段预测的动作梯度为 0（来自补零常量）",
                   float(grad[2 * n:].abs().max()) == 0.0))
    checks.append(("例2 Q 对 E 的导数非 0", float(grad[n:2 * n].abs().max()) > 0.0))
    # 可证伪：故意把拼装规则写错，对应段必须亮起来，否则上面两个 0 说明不了任何事。
    wrong_c = torch.autograd.grad(assemble(full, wrong_c=True), full)[0]
    wrong_d = torch.autograd.grad(assemble(full, wrong_d=True), full)[0]
    checks.append(("例2 探针可证伪：错用策略的 C 预测 ⇒ C 段梯度非 0",
                   float(wrong_c[:n].abs().max()) > 0.0))
    checks.append(("例2 探针可证伪：错用策略的 D 预测 ⇒ D 段梯度非 0",
                   float(wrong_d[2 * n:].abs().max()) > 0.0))
    # 改 C/D 段预测 loss 数值不变（它们没被接进图）；改 E 才变。
    perturbed = full.detach().clone()
    perturbed[:n] += 3.0
    perturbed[2 * n:] *= -2.0
    shifted = full.detach().clone()
    shifted[n:2 * n] += 1.0
    checks.append(("例2 改 C/D 段预测 loss 不变",
                   bool(torch.allclose(assemble(perturbed), assemble(full)))))
    checks.append(("例2 改 E 段预测 loss 改变",
                   not bool(torch.allclose(assemble(shifted), assemble(full)))))


# ---------------- 例 3：下一槽第 3 步成功 ----------------
def case3_next_slot_third_step_success(checks: list) -> None:
    n, gamma = 6, 0.9
    with open_ledger("case3") as led:
        b = EpisodeBuilder(led, "ep3", n=n)
        ua, ub = action(1.0, n), action(2.0, n)
        b.add_slot("RA", 100, u=ua, rewards=[0.0] * n)                       # 当前槽奖励全零
        b.add_slot("RB", 106, u=ub, rewards=[0.0, 0.0, 1.0], terminal_step=3,
                   terminal_kind="success")                                   # 下一槽第 3 步成功并终止
        bundle = db.build_views(led, n=n, gamma=gamma)
        sa = sample_of(bundle, "RA")
        sb = sample_of(bundle, "RB")
        checks.append(("例3 终局槽进 TD 且不 bootstrap",
                       sb is not None and sb.td_valid and sb.bootstrap_valid is False
                       and sb.terminated is True))
        checks.append(("例3 R_terminal=0.9^2=0.81", sb is not None and abs(sb.r_slot - 0.81) < 1e-12))
        checks.append(("例3 终局 target=0.81（U 未物理激活也保留）",
                       sb is not None and abs(sb.target(0.0) - 0.81) < 1e-12
                       and tuple(tuple(a) for a in sb.u) == ub))
        checks.append(("例3 终局槽 U 无执行帧（execution_mask 全 0）",
                       sb is not None and sum(sb.execution_mask) == 0))
        checks.append(("例3 前驱自身记录未被未来结果改写",
                       sa is not None and sa.r_slot == 0.0 and sa.next_x_ref == "ep3#106"))
        checks.append(("例3 前驱 target 经 0.9^6×0.9^2=0.9^8 传回",
                       sa is not None and abs(sa.target(0.81) - gamma ** 8) < 1e-12))
        checks.append(("例3 前驱不因本次未来终止被排除采样", sa is not None and sa.td_valid))
        after = led.frames(episode_id="ep3", lo=109)
        checks.append(("例3 第 3 步之后无帧/无奖励/无假观测", len(after) == 0))


# ---------------- 例 4：建议未提交与提交后尚未执行 ----------------
def case4_shadow_vs_committed(checks: list) -> None:
    n, gamma = 6, 0.99
    with open_ledger("case4") as led:
        b = EpisodeBuilder(led, "ep4", n=n)
        ua, ub, uc = action(1.0, n), action(2.0, n), action(3.0, n)
        b.add_slot("RA", 100, u=ua, rewards=[0.0] * n)
        seq_b = b.shadow_proposal(ub, frame=106)              # 候选 B：只有影子查询，没有 request
        b.add_slot("RB", 106, u=ua, rewards=[0.0] * n)        # 真实 request 采用的是 A
        b.add_slot("RC", 112, u=uc, rewards=[0.0] * n, takeover_frame=114)   # 之后 A 被抢占
        bundle = db.build_views(led, n=n, gamma=gamma)
        sa = sample_of(bundle, "RA")
        cand = next((c for c in bundle.candidate if c["proposal_seq"] == seq_b), None)
        checks.append(("例4 被真实 request 采用的 A 进 TD", sa is not None and sa.td_valid))
        checks.append(("例4 影子建议 B 只进候选池", cand is not None and cand["td_valid"] is False))
        checks.append(("例4 B 不配 reward / next state",
                       cand is not None and cand["reward"] is None and cand["next_x_ref"] is None))
        checks.append(("例4 A 被后续抢占后，前一条 next queue 仍是 A",
                       sa is not None and sa.next_queue == ua))
        checks.append(("例4 抢占槽自身隔离",
                       "takeover_in_slot" in (sample_of(bundle, "RC", view="isolated")
                                              or db.TrainingSample("", "", "", 0, 0, n, 1.0, None,
                                                                   None, None, None, None, False,
                                                                   False, False, "none", False)
                                              ).isolation_reasons))
        # 未提交的 request（只 admit 不 commit）不得因终局例外获得 TD。
        b.add_slot("RD", 118, u=action(4.0, n), rewards=[0.0] * n, commit=False)
        bundle2 = db.build_views(led, n=n, gamma=gamma)
        sd = sample_of(bundle2, "RD", view="isolated")
        checks.append(("例4 未提交的 request 无 TD 资格",
                       sd is not None and "result_not_committed" in sd.isolation_reasons))


# ---------------- 例 5：帧 108 中途抢占 ----------------
def case5_mid_slot_takeover(checks: list) -> None:
    n, gamma = 6, 0.99
    with open_ledger("case5") as led:
        b = EpisodeBuilder(led, "ep5", n=n)
        u1, u2 = action(1.0, n), action(2.0, n)
        b.add_slot("R1", 100, u=u1, rewards=[0.5] * n)
        b.add_slot("R2", 106, u=u2, rewards=[0.0, 0.0, 0.0], takeover_frame=108)
        bundle = db.build_views(led, n=n, gamma=gamma)
        s1, s2 = sample_of(bundle, "R1"), sample_of(bundle, "R2", view="isolated")
        checks.append(("例5 帧 106 快照准确 -> 100-105 一步转移保留", s1 is not None and s1.td_valid))
        checks.append(("例5 106 起的槽不当普通样本", s2 is not None and not s2.td_valid))
        checks.append(("例5 抢占槽隔离原因记 takeover_in_slot",
                       s2 is not None and "takeover_in_slot" in s2.isolation_reasons))
        checks.append(("例5 删失比例被报告（不宣称自动无偏）",
                       bundle.stats["censoring_ratio"] > 0.0))
    # 变体：边界快照与接管并发、无法判断先后 -> 连前驱一起隔离。
    with open_ledger("case5b") as led:
        b = EpisodeBuilder(led, "ep5b", n=n)
        b.add_slot("R1", 100, u=action(1.0, n), rewards=[0.5] * n)
        b.add_slot("R2", 106, u=action(2.0, n), rewards=[], takeover_frame=108, write_frames=False)
        bundle = db.build_views(led, n=n, gamma=gamma)
        s1 = sample_of(bundle, "R1", view="isolated")
        checks.append(("例5b 边界不可确认 -> 前驱一并隔离",
                       s1 is not None and "boundary_unverifiable_before_takeover" in s1.isolation_reasons
                       and "next_snapshot_unverifiable" in s1.isolation_reasons))
        checks.append(("例5b 隔离范围只限不可确认区间",
                       len(bundle.isolated) == 2 and bundle.stats["n_td"] == 0))


# ---------------- 例 6：晚到与换向 ----------------
def case6_late_and_goal_switch(checks: list) -> None:
    n, gamma = 6, 0.99
    with open_ledger("case6") as led:
        b = EpisodeBuilder(led, "ep6", n=n)
        b.add_slot("R1", 100, u=action(1.0, n), rewards=[0.0] * n, deadline=106, commit_frame=107)
        b.add_slot("R2", 106, u=action(2.0, n), rewards=[0.0] * n)
        bundle = db.build_views(led, n=n, gamma=gamma)
        s1 = sample_of(bundle, "R1", view="isolated")
        checks.append(("例6 结果 107 到、错过 106 deadline -> 拒绝",
                       s1 is not None and "deadline_miss" in s1.isolation_reasons))
    with open_ledger("case6b") as led:
        b = EpisodeBuilder(led, "ep6b", n=n, goal="A_to_B", epoch=1)
        b.add_slot("RG1", 100, u=action(1.0, n), rewards=[0.0] * n, goal="A_to_B", epoch=1)
        b.add_slot("RG2", 106, u=action(2.0, n), rewards=[0.0] * n, goal="B_to_A", epoch=2)
        bundle = db.build_views(led, n=n, gamma=gamma)
        s2 = sample_of(bundle, "RG2", view="isolated")
        s1 = sample_of(bundle, "RG1", view="isolated")
        checks.append(("例6 换向后旧结果因 goal/epoch 不相容被拒",
                       s2 is not None and "goal_epoch_mismatch" in s2.isolation_reasons))
        checks.append(("例6 正向 Q 不跨 goal 继续 bootstrap",
                       s1 is not None and "next_goal_switch" in s1.isolation_reasons))
        checks.append(("例6 双向 TD 覆盖分别记账", bundle.stats["td_per_goal"] == {}))


# ---------------- 回归：账本追加语义、撤销追踪、pending、四种 mask ----------------
def case_append_only_and_revocation(checks: list) -> None:
    n, gamma = 6, 0.99
    with open_ledger("case_rev") as led:
        b = EpisodeBuilder(led, "epR", n=n)
        b.add_slot("R1", 100, u=action(1.0, n), rewards=[0.0] * n)
        b.add_slot("R2", 106, u=action(2.0, n), rewards=[0.0] * n)
        bundle = db.build_views(led, n=n, gamma=gamma)
        manifests = db.write_manifests(led, bundle, run_id="c-selfcheck", gamma=gamma, n=n,
                                       label_version="rubric-v1")
        checks.append(("回归 每个视图都有 manifest", set(manifests) == {"td", "bc", "candidate",
                                                                     "isolated", "pending"}))
        reward_labels = [lab for lab in led.labels(label_kind="reward") if lab["value"] is not None]
        target = int(reward_labels[0].seq)
        revoke_seq = led.revoke_label(target, reason="rubric 误判复核", rubric_version="rubric-v2")
        impact = led.revocation_impact(revoke_seq)
        original = [lab for lab in led.labels() if lab.seq == target]
        revokes = led.labels(target_seq=target, label_kind="revoke")
        checks.append(("回归 撤销只追加、原行仍在",
                       len(original) == 1 and len(revokes) == 1 and original[0]["label_kind"] == "reward"))
        checks.append(("回归 撤销沿 manifest 反查到受影响视图",
                       "c-selfcheck:td" in impact["affected_manifests"]))
        for table in ("frame_fact", "label_record"):
            try:
                led.conn.execute(f"UPDATE {table} SET episode_id='hacked' WHERE rowid=1")
                blocked = False
            except Exception:
                blocked = True
            checks.append((f"回归 {table} 拒绝改写（append-only）", blocked))


def case_revocation_invalidates_views(checks: list) -> None:
    """撤销一条标签后，依赖它的视图必须真的变（2026-09-28 修掉的真实 bug）。

    修之前 `data_bridge` 从不查 `revoked_seqs()`：被撤销的奖励照样进 `reward_by_frame`；
    而且 `reward_state` 优先级是 final 压过 unknown，于是「六帧里撤销一帧」会静默按 0 计进
    完整回报 —— 一次 rubric 误判复核就能悄悄改掉学习目标，而账本上看不出任何异常。
    撤销的正确语义是：这一帧退回「无标签」⇒ 整槽 unknown ⇒ 进隔离视图，不是 0 分、不是失败。
    """
    n, gamma = 6, 0.99
    with open_ledger("case_revoke_views") as led:
        b = EpisodeBuilder(led, "epRV", n=n)
        b.add_slot("R1", 200, u=action(1.0, n), rewards=[0.1] * n)
        b.add_slot("R2", 206, u=action(2.0, n), rewards=[0.2] * n)
        b.add_slot("R3", 212, u=action(3.0, n), rewards=[0.0] * n,
                   terminal_step=2, terminal_kind="success")
        # H1 的帧 source="harness" ⇒ BC 视图的合法来源（真实执行过的纠正）
        b.add_slot("H0", 300, u=action(4.0, n), rewards=[0.0] * n)
        b.add_slot("H1", 306, u=action(5.0, n), rewards=[0.0] * n, source="harness")
        before = db.build_views(led, n=n, gamma=gamma)
        db.write_manifests(led, before, run_id="c-revoke", gamma=gamma, n=n,
                           label_version="rubric-v1")
        r1_before = sample_of(before, "R1")
        checks.append(("回归 撤销前 R1 有 TD 资格且 R_k 已算出",
                       r1_before is not None and r1_before.r_slot is not None))

        harness_frames = [fr for fr in led.frames(episode_id="epRV")
                          if 306 <= int(fr["abs_frame"]) < 306 + n]
        q_seq = led.append_label(episode_id="epRV", label_kind="quality",
                                 target_seq=int(harness_frames[0].seq), value=0.1,
                                 reward_state="final", source="gpt", rubric_version="rubric-v1")
        gated = db.build_views(led, n=n, gamma=gamma)
        n_bc_gated = len([s for s in gated.bc if s.start_frame == 306])

        target_frame = [fr for fr in led.frames(episode_id="epRV")
                        if int(fr["abs_frame"]) == 202][0]
        original = led.labels(target_seq=int(target_frame.seq), label_kind="reward")[0]
        revoke_seq = led.revoke_label(int(original.seq), reason="rubric 误判复核",
                                      rubric_version="rubric-v2")
        led.revoke_label(q_seq, reason="评分复核：夹爪通道标错", rubric_version="rubric-v2")
        after = db.build_views(led, n=n, gamma=gamma)
        s = sample_of(after, "R1", view="isolated")
        checks.append(("回归 撤销槽内一帧奖励 -> 整槽退出普通 TD",
                       sample_of(after, "R1") is None and s is not None))
        checks.append(("回归 撤销记 unknown，不按 0 分继续算 R_k",
                       s is not None and "reward_unknown" in s.isolation_reasons
                       and s.r_slot is None))
        checks.append(("回归 撤销只影响依赖它的槽（R2 仍在 TD）",
                       sample_of(after, "R2") is not None))
        checks.append(("回归 撤销条数进 stats，删失来源可报告",
                       after.stats.get("revoked_labels") == 2))
        checks.append(("回归 撤销沿 manifest 反查到受影响视图",
                       "c-revoke:td" in led.revocation_impact(revoke_seq)["affected_manifests"]))
        n_bc_after = len([x for x in after.bc if x.start_frame == 306])
        checks.append(("回归 撤销 quality 标签 -> 纠正帧退回默认权重、不被废分数挡住",
                       n_bc_gated == 0 and n_bc_after == 1))


def case_pending_and_masks(checks: list) -> None:
    n, gamma = 6, 0.99
    with open_ledger("case_pending") as led:
        b = EpisodeBuilder(led, "epP", n=n)
        b.add_slot("R1", 100, u=action(1.0, n), rewards=[0.0] * n, reward_state="pending")
        b.add_slot("R2", 106, u=action(2.0, n), rewards=[0.0] * n)
        bundle = db.build_views(led, n=n, gamma=gamma)
        pending = sample_of(bundle, "R1", view="pending")
        checks.append(("回归 reward pending 不发布也不置零",
                       pending is not None and pending.r_slot is None
                       and "reward_pending" in pending.isolation_reasons))
        checks.append(("回归 pending 不进普通 TD", sample_of(bundle, "R1") is None))
        checks.append(("回归 候选池动作标签一律无 reward / next state",
                       all(c["reward"] is None and c["next_x_ref"] is None for c in bundle.candidate)))


def case_success_is_not_eligibility(checks: list) -> None:
    """四种 mask 分离：「是否成功 / 奖励多高」都不能代替 TD 资格（附录 02 §4.2）。"""
    n, gamma = 6, 0.99
    with open_ledger("case_mask") as led:
        b = EpisodeBuilder(led, "epM", n=n)
        # R1 奖励全 1（看起来很成功），但下一槽实际承诺的 C 被换成了别的动作。
        b.add_slot("R1", 100, u=action(1.0, n), rewards=[1.0] * n)
        b.add_slot("R2", 106, u=action(2.0, n), rewards=[1.0] * n, c_override=action(9.9, n))
        b.add_slot("R3", 112, u=action(3.0, n), rewards=[1.0] * n)
        b.add_slot("R4", 118, u=action(4.0, n), rewards=[1.0] * n)
        bundle = db.build_views(led, n=n, gamma=gamma)
        s1 = sample_of(bundle, "R1", view="isolated")
        checks.append(("回归 高奖励但 C_next≠U -> 无 TD 资格",
                       s1 is not None and "c_next_not_equal_u" in s1.isolation_reasons
                       and s1.r_slot == sum(gamma ** j for j in range(n))))
        # `c_override` 让帧 106-111 的 `chunk_id` 仍指 R1、`a_rl` 却是 9.9 系列：这是一份
        # **自相矛盾**的账本（声称在跑 R1 的 chunk，跑的却不是 R1 承诺的 U）。所以 R2 也不是
        # 「正常槽」—— 它的 C 没有按学习动作边界执行（附录 02 §3.3-1）。2026-09-28 之前
        # `c_not_executed` 只看 `execution_status`，检不出这种值级替换，于是这一条断言把 R2
        # 当成了清白样本（B 黄金值 E5 的 §3.3-1 要求把它检出来，见
        # docs/c_golden_conformance_20260928.md §3）。现在两条都断言，清白槽改用 R3。
        s2 = sample_of(bundle, "R2", view="isolated")
        checks.append(("回归 C 被值级替换 -> 该槽也不是正常槽（§3.3-1 c_not_executed）",
                       s2 is not None and "c_not_executed" in s2.isolation_reasons))
        checks.append(("回归 同一批数据里正常槽仍进 TD", sample_of(bundle, "R3") is not None))
    # 终局成功但拿不到原在途 U：保留终局事实，不伪造动作。
    with open_ledger("case_term_u") as led:
        b = EpisodeBuilder(led, "epT", n=n)
        b.add_slot("R1", 100, u=action(1.0, n), rewards=[0.0] * n)
        b.add_slot("R2", 106, u=action(2.0, n), rewards=[0.0, 0.0, 1.0], terminal_step=3,
                   terminal_kind="success", commit=False)
        bundle = db.build_views(led, n=n, gamma=gamma)
        s2 = sample_of(bundle, "R2", view="isolated")
        checks.append(("回归 终局但 U 不可得 -> 记 unknown，不伪造动作",
                       s2 is not None and "terminal_u_unknown" in s2.isolation_reasons
                       and s2.u is None))
        term_frames = [fr for fr in led.frames(episode_id="epT") if (fr["payload"] or {}).get("terminal")]
        checks.append(("回归 终局事实本身仍完整保留", len(term_frames) == 1))
    # C 段"发出去了但没确认真正生效"：不算普通样本。
    with open_ledger("case_noack") as led:
        b = EpisodeBuilder(led, "epN", n=n)
        b.add_slot("R1", 100, u=action(1.0, n), rewards=[0.0] * n)
        b.add_slot("R2", 106, u=action(2.0, n), rewards=[0.0] * n, exec_status="unknown")
        b.add_slot("R3", 112, u=action(3.0, n), rewards=[0.0] * n)
        bundle = db.build_views(led, n=n, gamma=gamma)
        s2 = sample_of(bundle, "R2", view="isolated")
        checks.append(("回归 驱动无回执 -> c_not_executed 隔离",
                       s2 is not None and "c_not_executed" in s2.isolation_reasons))
    # 外部截断（timeout）不冒充 done=1。
    with open_ledger("case_trunc") as led:
        b = EpisodeBuilder(led, "epX", n=n)
        b.add_slot("R1", 100, u=action(1.0, n), rewards=[0.0] * n)
        b.add_slot("R2", 106, u=action(2.0, n), rewards=[0.0] * n, terminal_step=n,
                   terminal_kind="timeout")
        bundle = db.build_views(led, n=n, gamma=gamma)
        s2 = sample_of(bundle, "R2", view="isolated")
        checks.append(("回归 外部截断不冒充 done=1",
                       s2 is not None and s2.terminated is False
                       and s2.terminal_kind == "timeout"
                       and "truncated_without_next_snapshot" in s2.isolation_reasons))


def case_export_roundtrip(checks: list) -> None:
    """导出 → 读回：learner 进程拿到的必须与内存里的视图逐值相同，且不许被悄悄改过。

    这一层存在的理由是：视图停在内存里等于没有。learner 跑在另一个进程/另一套依赖里，
    它只该读到「已经定资格、定 mask、定 label_version」的行；否则资格判定会在两处各写一遍
    并分叉。三条要守的：五视图各自成文件永不合并、只导 `x_ref` 不导表征、带内容身份。
    """
    n, gamma = 6, 0.99
    with open_ledger("case_export") as led:
        b = EpisodeBuilder(led, "epX", n=n)
        b.add_slot("R1", 400, u=action(1.0, n), rewards=[0.5] * n)
        b.add_slot("R2", 406, u=action(2.0, n), rewards=[0.0] * n, reward_state="pending")
        b.add_slot("R3", 412, u=action(3.0, n), rewards=[0.0] * n, takeover_frame=414)
        b.shadow_proposal(action(9.0, n), frame=400, quality=0.9)
        bundle = db.build_views(led, n=n, gamma=gamma)
        checks.append(("导出前提 五个视图里 td/pending/isolated/candidate 都非空",
                       bundle.td and bundle.pending and bundle.isolated and bundle.candidate))
        for fmt in ("parquet", "jsonl"):
            out = OUT_DIR / f"export_{fmt}"
            db.export_views(bundle, out, run_id=f"c-export-{fmt}", n=n, gamma=gamma,
                            label_version="rubric-v1", fmt=fmt)
            loaded, meta = db.load_views(out)
            checks.append((f"导出 {fmt}: 五个视图都落文件（空视图也落 0 行）",
                           set(loaded) == set(db.VIEW_NAMES)
                           and all((out / meta["views"][v]["path"]).exists()
                                   for v in db.VIEW_NAMES)))
            checks.append((f"导出 {fmt}: 行数与内存视图一致",
                           all(len(loaded[v]) == len(getattr(bundle, v))
                               for v in db.VIEW_NAMES)))
            row = next(r for r in loaded["td"] if r["request_id"] == "R1")
            mem = sample_of(bundle, "R1")
            checks.append((f"导出 {fmt}: r_slot / gamma_slot / 四种 mask / u 逐值往返",
                           abs(row["r_slot"] - mem.r_slot) < 1e-12
                           and abs(row["gamma_slot"] - gamma ** n) < 1e-12
                           and list(row["q_action_gradient_mask"]) == list(mem.q_action_gradient_mask)
                           and list(row["execution_mask"]) == list(mem.execution_mask)
                           and list(row["u"][0]) == list(mem.u[0])))
            checks.append((f"导出 {fmt}: td 分片只含 td_valid=True",
                           all(r["td_valid"] for r in loaded["td"])))
            checks.append((f"导出 {fmt}: pending/isolated 没有混进 td",
                           not ({r["request_id"] for r in loaded["td"]}
                                & {r["request_id"] for r in loaded["pending"] + loaded["isolated"]})))
            checks.append((f"导出 {fmt}: 候选行 reward / next_x_ref 恒为 None",
                           all(r["reward"] is None and r["next_x_ref"] is None
                               for r in loaded["candidate"])))
            checks.append((f"导出 {fmt}: pending 的 r_slot 读回是 None（不是 0.0）",
                           all(r["r_slot"] is None for r in loaded["pending"])))
            checks.append((f"导出 {fmt}: 隔离原因随行带出，learner 不需要再判一次",
                           all(r["isolation_reasons"] for r in loaded["isolated"])))
            victim = out / meta["views"]["td"]["path"]
            if fmt == "parquet":
                import pandas as pd

                # 原样重写是字节相同的（pandas 的 parquet writer 确定），那不算篡改。
                # 这里改一个值：把 r_slot 抹成 0.0 —— 正是「unknown/pending 被当零奖励」
                # 那条红线在导出层的样子，身份核对必须拦住。
                frame = pd.read_parquet(victim)
                frame["r_slot"] = 0.0
                frame.to_parquet(victim, index=False)
            else:
                victim.write_text(victim.read_text() + " ", encoding="utf-8")
            try:
                db.load_views(out)
                tampered = False
            except db.ViewExportTampered:
                tampered = True
            checks.append((f"导出 {fmt}: 分片被改过 -> 拒绝加载（内容身份）", tampered))


def case_runtime_adapter_ingest(checks: list) -> None:
    """集成：既有 `RuntimeAdapter` 的事件能原样落账本，再派生出普通 TD 样本。

    只读消费 `harness/contracts.py` 与 `harness/runtime_adapter.py`，不修改它们。
    """
    from harness.contracts import DecisionRequest, QueueState
    from harness.ledger import ingest_runtime_result
    from harness.runtime_adapter import RuntimeAdapter

    n, gamma = 1, 0.99
    with open_ledger("case_ingest") as led:
        for index, rid in enumerate(("RA", "RB")):
            adapter = RuntimeAdapter(driver=lambda r, s, a: {"activated": True, "reward": 0.5,
                                                             "phase": "approach",
                                                             "grasp_verified": False})
            adapter.start(DecisionRequest(rid, 1, "lift", {"cube_pos": [0.0, 0.0, 0.0]},
                                          "mock", "v1", 0, index, 10), QueueState())
            for _ in range(n):
                adapter.step([0.1, 0.2, 0.3])
            result = adapter.finalize("success", reward=1.0)
            ingest_runtime_result(led, result, episode_id="epI", goal_id="lift", epoch=1,
                                  lease_generation=0, source="mock",
                                  # P1-5：准入闸 fail-closed ⇒ 必须显式声明依据。
                                  # 这里是 env 直接产出的运行时观测（不是被门禁分级的裁定），
                                  # 所以声明 observation_only；账本会记一条
                                  # verdict_identity_absent 事件，下游发布包会拒绝把它当方向性结论。
                                  observation_only=True)
        stats = led.stats()
        checks.append(("集成 RuntimeResult 落账本（帧+事件+奖励标签）",
                       stats["frame_fact"] >= 2 and stats["schedule_event"] >= 6
                       and stats["label_record"] >= 2))
        kinds = {ev["kind"] for ev in led.events(episode_id="epI")}
        checks.append(("集成 request/commit/activate 三事件可区分",
                       {"request_admitted", "result_committed", "physical_activated"} <= kinds))
        checks.append(("集成 账本不含训练语义列",
                       all("td_valid" not in row.fields for row in led.frames(episode_id="epI"))))


CASES = (case1_normal_three_segments, case2_gradient_only_through_e, case3_next_slot_third_step_success,
         case4_shadow_vs_committed, case5_mid_slot_takeover, case6_late_and_goal_switch,
         case_append_only_and_revocation, case_pending_and_masks, case_success_is_not_eligibility,
         case_revocation_invalidates_views, case_export_roundtrip, case_runtime_adapter_ingest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="打印每条断言")
    args = parser.parse_args()

    checks: list[tuple[str, bool]] = []
    for case in CASES:
        before = len(checks)
        case(checks)
        for name, ok in checks[before:]:
            print(f"[{'PASS' if ok else 'FAIL'}] {name}" if args.verbose
                  else f"[{'PASS' if ok else 'FAIL'}] {name}", flush=True)
    failed = [name for name, ok in checks if not ok]
    print(f"--- 失败 {len(failed)} 条 ---" if failed else "--- 全部通过 ---")
    for name in failed:
        print(f"  FAIL {name}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "cases": [c.__name__ for c in CASES],
        "checks": [{"name": name, "ok": ok} for name, ok in checks],
        "pass": not failed, "n_checks": len(checks), "n_failed": len(failed),
        "ledger_dir": str(OUT_DIR),
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"结果: {len(checks) - len(failed)}/{len(checks)} PASS -> {OUT_JSON}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
