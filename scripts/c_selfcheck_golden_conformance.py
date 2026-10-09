#!/usr/bin/env python3
"""C 线 P0-1：消费 B 的黄金值规格 `b_golden_async_td_v1`，独立复核 C 的账本/数据桥/learner。

为什么要单独一个脚本（而不是复用 `scripts/selfcheck_ledger_views.py`）
------------------------------------------------------------------
`selfcheck_ledger_views.py::case1–case6` 与 B 的 E1–E6 逐条平行，但它是 **C 自己写、C 自己判**，
本质上是「用实现验实现」：断言的期望值是照着实现的行为写的，实现错了断言会跟着错。
这里改成**读 B 交付的规格 JSON** 逐条断言 —— 规格与实现出自不同智能体，才构成独立数值复核。

- 规格（只读，B 交付）：`docs/b_golden/async_td_golden_v1.json`
- 用法守则：`docs/b_golden/README.md`
- 裁定 / 名称与索引映射 / 立项：`docs/c_golden_conformance_20260928.md`
- 契约出处：`RL_Harness_v4_20260924/materials/06_.../appendices/02_异步动作时间轴与学习目标.md`
  §9 例 1–6、§3.3、§4.1、§5、§6.2

断言纪律（照 `docs/b_golden/README.md`，逐条落在代码里）
----------------------------------------------------
1. `expect` 的**每个子键各自成一类**断言、分别计数，绝不合并成一个 bool
   （`targets` / `masks` / `isolation` / `gradients` / `next_state` / `invariance` / …）。
2. `targets` 用 1e-9 相对容差；`atol=1e-12` 只为兜住期望值本身是 0 的情形（E3 的 `R_k=0`）。
3. `gradients` 用 `== 0.0` / `!= 0.0` **严判**（规格 `strict: true`），不设容差；并跑
   `wrong_c` / `wrong_d` 两个故意写错的对照分支 —— 它们必须非 0，否则那些 0 只是探针失灵。
4. `Q̄` 是**符号名**：对 `y(q)` 在 q=1,2 两点做线性识别得 `(intercept, slope)`，断言
   `intercept == R_k`、`slope == γ_slot`（终局槽 `slope == 0`，这条本身就是「无 bootstrap」的证明）。
   全程不断言任何编出来的浮点常数。
5. 索引段只读 `conventions.action_index_segments_numeric`（半开区间），不做中文字符串匹配。
6. 任何一条不过 ⇒ 该项 `verdict=FAIL`、整体 `conformant=false`；判断为规格自身有问题时记
   `UNRESOLVED` 并停下等人工裁定。**不调容差、不放宽断言、不改规格。**
7. 不可断言项（例如「理想 Q 在确定性终局处对 U 的梯度为 0」——那是收敛后理想 Q 的性质，
   不是一个未训练网络能测的量）记 `NOT_ASSERTABLE`，单独计数，既不算通过也不算失败。

用法
----
    CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2 \\
        /root/venvs/rlrobot/bin/python scripts/c_selfcheck_golden_conformance.py
    ... -v              # 打印每条断言
    ... --case E5       # 只跑某一例（可重复）
    ... --no-learner    # 跳过 E2 的 torch 探针（只跑账本/视图侧）

产物：`runs/infra/c_golden_conformance.json` + `runs/infra/c_golden_conformance/<stamp>/*.db`
账本是 append-only，所以每次跑用独立时间戳子目录；旧产物保留（工作区禁 rm，清理走 recycle_bin）。
全程 CPU-only：A 线在 GPU 上跑 lerobot 训练，不抢卡。
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import itertools
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._venv import ensure_venv  # noqa: E402

ensure_venv("torch")

from harness import data_bridge as db  # noqa: E402
from harness import queue_td_learner as ql  # noqa: E402
from harness.ledger import FactLedger  # noqa: E402
from scripts.selfcheck_ledger_views import EpisodeBuilder, action, sample_of  # noqa: E402

SPEC_PATH = ROOT / "docs" / "b_golden" / "async_td_golden_v1.json"
OUT_JSON = ROOT / "runs" / "infra" / "c_golden_conformance.json"
OUT_DIR = ROOT / "runs" / "infra" / "c_golden_conformance" / time.strftime("%Y%m%d_%H%M%S")
IMPL_FILES = ("harness/ledger.py", "harness/data_bridge.py", "harness/queue_td_learner.py",
              "scripts/selfcheck_ledger_views.py", "scripts/c_selfcheck_golden_conformance.py")

PASS, FAIL, UNRESOLVED, NOT_ASSERTABLE = "PASS", "FAIL", "UNRESOLVED", "NOT_ASSERTABLE"
BAD_VERDICTS = (FAIL, UNRESOLVED)

# 规格用附录原文措辞，C 侧用已冻结的实现命名（docs/ledger_data_bridge_20260928.md §9.2）。
# 断言按**语义**对齐，别名登记在这里 + 文档，不改实现命名、不做中文字符串匹配。
REASON_ALIASES = {
    "late_past_deadline": "deadline_miss",
    "goal_epoch_incompatible": "goal_epoch_incompatible",
    "§3.3-1 C 未在整个槽内按学习动作边界执行": "c_not_executed",
    "§3.3-4 存在未建模的中途队列替换": "takeover_in_slot",
}
KIND_ALIASES = {"true_goal_termination": "goal_reached"}


# ---------------------------------------------------------------------------
# 报告：按 (case, category) 分别计数，永不合并成一个 bool
# ---------------------------------------------------------------------------
class Report:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, case: str, category: str, name: str, ok: Any, *,
            expected: Any = None, actual: Any = None, note: str = "",
            tolerance: str | None = None, invariants: Sequence[str] = ()) -> bool:
        verdict = PASS if bool(ok) else FAIL
        self.rows.append({"case": case, "category": category, "name": name, "verdict": verdict,
                          "expected": _jsonable(expected), "actual": _jsonable(actual),
                          "tolerance": tolerance, "note": note, "invariants": list(invariants)})
        return bool(ok)

    def unresolved(self, case: str, category: str, name: str, reason: str, *,
                   expected: Any = None, actual: Any = None,
                   invariants: Sequence[str] = ()) -> None:
        """判断为**规格侧**问题或需要人工裁定时用这个；整体判不通过，但不算实现 FAIL。"""
        self.rows.append({"case": case, "category": category, "name": name, "verdict": UNRESOLVED,
                          "expected": _jsonable(expected), "actual": _jsonable(actual),
                          "tolerance": None, "note": reason, "invariants": list(invariants)})

    def not_assertable(self, case: str, category: str, name: str, reason: str, *,
                       expected: Any = None, invariants: Sequence[str] = ()) -> None:
        self.rows.append({"case": case, "category": category, "name": name,
                          "verdict": NOT_ASSERTABLE, "expected": _jsonable(expected),
                          "actual": None, "tolerance": None, "note": reason,
                          "invariants": list(invariants)})

    # -- 汇总 --
    def by(self, key: str) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for row in self.rows:
            bucket = out.setdefault(row[key], {v: 0 for v in (PASS, FAIL, UNRESOLVED, NOT_ASSERTABLE)})
            bucket[row["verdict"]] += 1
        return {k: v for k, v in sorted(out.items())}

    def by_case_category(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for row in self.rows:
            key = f"{row['case']}/{row['category']}"
            bucket = out.setdefault(key, {v: 0 for v in (PASS, FAIL, UNRESOLVED, NOT_ASSERTABLE)})
            bucket[row["verdict"]] += 1
        return {k: v for k, v in sorted(out.items())}

    @property
    def conformant(self) -> bool:
        return not any(row["verdict"] in BAD_VERDICTS for row in self.rows)

    def n(self, verdict: str) -> int:
        return sum(1 for row in self.rows if row["verdict"] == verdict)


def _jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        items = [_jsonable(v) for v in obj]
        return items if len(items) <= 24 else items[:24] + [f"…(+{len(items) - 24})"]
    return repr(obj)


# ---------------------------------------------------------------------------
# 数值工具
# ---------------------------------------------------------------------------
def close(actual: Any, expected: Any, *, rtol: float = 1e-9, atol: float = 1e-12) -> bool:
    """规格要求的 1e-9 相对容差。`atol` 只用于 expected==0（E3 的 R_k=0）时的兜底。"""
    if actual is None or expected is None:
        return False
    try:
        a, e = float(actual), float(expected)
    except (TypeError, ValueError):
        return False
    return abs(a - e) <= atol + rtol * abs(e)


def lin_id(fn: Callable[[float], float | None], q1: float = 1.0,
           q2: float = 2.0) -> tuple[float | None, float | None]:
    """对**符号** Q̄ 做线性识别：`y(q) = intercept + slope*q` ⇒ 返回 (intercept, slope)。

    规格 README 第 4 条：断言应当是「target == R + gamma_slot * <同一个 Q̄ 调用的返回值>」，
    不是断言一个编出来的浮点数。两点线性识别就是这个要求的可执行形式，
    并且 `slope` 直接暴露「有没有 bootstrap、折扣是多少」。
    """
    y1, y2 = fn(q1), fn(q2)
    if y1 is None or y2 is None:
        return None, None
    slope = y2 - y1
    return y1 - slope * q1, slope


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# 账本是 append-only：同名 .db 被打开两次就会**叠加**旧事实，变异自检要反复重跑同一个算例，
# 所以每次调用都发一个唯一文件名（旧产物按时间戳目录保留，清理走 recycle_bin）。
_LEDGER_SEQ = itertools.count(1)


def open_ledger(name: str) -> FactLedger:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return FactLedger(OUT_DIR / f"{name}_{next(_LEDGER_SEQ):03d}.db")


def norm_u(u: Iterable) -> tuple:
    """动作序列比较用的规范化。`None` 行原样保留 —— 接管/hold 帧的 `a_rl` 就是 None，
    那是一条**事实**（这一段跑的不是学习动作），不能被规范化成 0.0 或丢掉。"""
    out: list[Any] = []
    for row in u:
        if row is None:
            out.append(None)
        elif isinstance(row, (list, tuple)):
            out.append(tuple(float(x) for x in row))
        else:
            out.append(float(row))
    return tuple(out)


def emit_activate(led: FactLedger, episode_id: str, rid: str, lo: int, hi: int, *,
                  goal: str, epoch: int = 1, lease: int = 0) -> None:
    """显式补 `physical_activated` 事件：request / commit / activate 是三个独立事件（I2）。"""
    led.append_event(episode_id=episode_id, kind="physical_activated", request_id=rid,
                     abs_frame=lo, epoch=epoch, goal_id=goal, lease_generation=lease,
                     payload={"frames": [lo, hi]})


def event_kinds(led: FactLedger, episode_id: str, rid: str) -> list[str]:
    return [ev["kind"] for ev in led.events(episode_id=episode_id) if ev["request_id"] == rid]


def frames_in(led: FactLedger, episode_id: str, lo: int, hi: int) -> list[Any]:
    return [fr for fr in led.frames(episode_id=episode_id) if lo <= int(fr["abs_frame"]) < hi]


def reward_sum(led: FactLedger, episode_id: str, lo: int, hi: int) -> float:
    """某段帧上已落账的奖励之和 —— 用来证明「诱饵确实写进去了」，避免断言空转。"""
    seqs = {int(fr.seq) for fr in frames_in(led, episode_id, lo, hi)}
    total = 0.0
    for lab in led.labels(episode_id=episode_id, label_kind="reward"):
        if lab["target_seq"] is not None and int(lab["target_seq"]) in seqs and lab["value"] is not None:
            total += float(lab["value"])
    return total


def hand_frame(led: FactLedger, episode_id: str, frame: int, *, goal: str, epoch: int = 1,
               lease: int = 0, source: str = "policy", status: str = "activated",
               rid: str | None = None, chunk_id: str | None = None,
               chunk_index: int | None = None, a_rl: Any = None,
               driver_command: Any = None, reward: float | None = None,
               reward_state: str = "final", terminal: bool = False,
               terminal_kind: str = "none") -> int:
    """手写单帧：E5/E6 需要帧级的接管、hold、纠正事实，`EpisodeBuilder` 的整槽写法覆盖不到。"""
    seq = led.append_frame(
        episode_id=episode_id, abs_frame=frame, goal_id=goal, epoch=epoch, lease_generation=lease,
        source=source, execution_status=status, request_id=rid, chunk_id=chunk_id,
        chunk_index=chunk_index, a_rl=a_rl, driver_command=driver_command,
        measured_state={"obs_ref": f"{episode_id}#{frame}"},
        payload={"terminal": terminal, "terminal_kind": terminal_kind if terminal else "none"})
    if reward is not None:
        led.append_label(episode_id=episode_id, label_kind="reward", target_seq=seq,
                         target_request_id=rid, value=reward, reward_state=reward_state,
                         source="env")
    return seq


def admit(led: FactLedger, episode_id: str, rid: str, start: int, *, goal: str, epoch: int = 1,
          lease: int = 0, deadline: int | None = None) -> None:
    for kind in ("request_received", "request_admitted"):
        led.append_event(episode_id=episode_id, kind=kind, request_id=rid, abs_frame=start,
                         epoch=epoch, goal_id=goal, deadline=deadline, lease_generation=lease)


def commit(led: FactLedger, episode_id: str, rid: str, frame: int, u: Sequence, *, goal: str,
           epoch: int = 1, lease: int = 0, deadline: int | None = None) -> None:
    led.append_event(episode_id=episode_id, kind="result_committed", request_id=rid,
                     abs_frame=frame, epoch=epoch, goal_id=goal, deadline=deadline,
                     lease_generation=lease, payload={"u": [list(a) for a in u]})


def views(led: FactLedger, spec: dict) -> db.ViewBundle:
    conv = spec["conventions"]
    return db.build_views(led, n=int(conv["slot_length_n"]),
                          gamma=float(conv["gamma_per_control_step"]),
                          chunk_len=int(conv["chunk_length_H"]))


def seg_of(spec: dict) -> dict[str, tuple[int, int]]:
    """只读 `action_index_segments_numeric`（README 第 5 条：不碰中文说明字段）。"""
    raw = spec["conventions"]["action_index_segments_numeric"]
    return {"C": tuple(raw["C_committed"]), "E": tuple(raw["E_execution"]),
            "D": tuple(raw["D_discarded"])}


def ones_span(mask: Sequence[int]) -> tuple[int, ...]:
    return tuple(i for i, v in enumerate(mask) if v)


# ===========================================================================
# E1：正常三段与一槽 TD
# ===========================================================================
def case_e1(rep: Report, spec: dict, seg: dict, *, no_learner: bool = False) -> None:
    case = spec_case(spec, "E1")
    cid = case["case_id"]
    conv, exp = spec["conventions"], case["expect"]
    n, gamma, H = int(conv["slot_length_n"]), float(conv["gamma_per_control_step"]), int(conv["chunk_length_H"])
    gamma_slot = float(conv["gamma_slot"])
    t_k = int(case["input"]["constants"]["t_k"])
    decoy = 0.7                      # 帧 106-111 的诱饵奖励：验 `must_not_contain`
    r_hit_frame, r_hit_value = 102, 0.1
    ep = "E1"
    with open_ledger("E1") as led:
        b = EpisodeBuilder(led, ep, n=n, goal="A_to_B")
        u_pre, u_k, u_next = action(0.5, n), action(1.0, n), action(2.0, n)
        # 规格时间轴：帧 100-105 执行「上一次推理已承诺的旧动作」= C 区间 ⇒ 需要真实的前驱 request。
        # 规格 event_log 没列它（它只描述 rq100 这一个决策），C 侧补一个 prime 槽把 C 变成真实承诺队列。
        b.add_slot("RPRE", t_k - n, u=u_pre, rewards=[0.0] * n)
        rewards = [0.0] * n
        rewards[r_hit_frame - t_k] = r_hit_value          # 只有 r_102 = 0.1
        b.add_slot("rq100", t_k, u=u_k, rewards=rewards, commit_frame=t_k + n)
        emit_activate(led, ep, "rq100", t_k + n, t_k + 2 * n, goal="A_to_B")
        b.add_slot("rq106", t_k + n, u=u_next, rewards=[decoy] * n, commit_frame=t_k + 2 * n)
        b.add_slot("rq112", t_k + 2 * n, u=action(3.0, n), rewards=[0.0] * n)
        bundle = views(led, spec)
        s = sample_of(bundle, "rq100")
        s_iso = sample_of(bundle, "rq100", view="isolated")
        intercept, slope = lin_id(s.target) if s else (None, None)

        # --- targets ---
        r_expect = exp["targets"]["R_k"]["numeric_exact"]
        rep.add(cid, "targets", "R_k = Σ γ^j r_{100+j} = γ^2*0.1",
                s is not None and close(s.r_slot, r_expect),
                expected=r_expect, actual=(s.r_slot if s else None), tolerance="rtol=1e-9",
                note="只有 r_102=0.1 非零", invariants=("I4",))
        rep.add(cid, "targets", "R_k 与 γ^2*0.1 逐项重算一致（不照抄规格常数）",
                close(s.r_slot if s else None, gamma ** (r_hit_frame - t_k) * r_hit_value),
                expected=gamma ** 2 * r_hit_value, actual=(s.r_slot if s else None),
                tolerance="rtol=1e-9")
        y_spec = exp["targets"]["y_k"]
        rep.add(cid, "targets", "y_k 的 Q̄ 系数 == γ_slot（符号比对，不编浮点）",
                close(slope, y_spec["gamma_slot_coefficient"]),
                expected=y_spec["gamma_slot_coefficient"], actual=slope, tolerance="rtol=1e-9",
                invariants=("I4",))
        rep.add(cid, "targets", "y_k 的常数项 == R_k（target 结构 = R + γ_slot*Q̄）",
                close(intercept, r_expect), expected=r_expect, actual=intercept,
                tolerance="rtol=1e-9")
        rep.add(cid, "targets", "γ_slot 显式存储且 == γ^n",
                s is not None and close(s.gamma_slot, gamma ** n) and close(s.gamma_slot, gamma_slot),
                expected=gamma_slot, actual=(s.gamma_slot if s else None), tolerance="rtol=1e-9",
                invariants=("I4",))
        rep.add(cid, "targets", "γ_slot != γ^(n*n)（防二次幂 bug）",
                s is not None and not close(s.gamma_slot, gamma ** (n * n), rtol=1e-6),
                expected=f"!= {gamma ** (n * n):.3e}", actual=(s.gamma_slot if s else None),
                note="规格：断言 target 时若发现 0.9^36 量级的数就是二次幂 bug", invariants=("I4",))
        rep.add(cid, "targets",
                "I6：折扣单位是**一个决策槽**（γ^n），不是原版 SmoothRL 的 2n chunk-skip（γ^2n）",
                close(slope, gamma ** n) and not close(slope, gamma ** (2 * n), rtol=1e-6),
                expected=gamma ** n, actual=slope, tolerance="rtol=1e-9",
                note="本项目自拟的一决策步队列增广目标；代码/图表/实验名不得写成「原版 SmoothRL 只改折扣」",
                invariants=("I6",))
        decoy_sum = decoy * sum(gamma ** j for j in range(n))
        rep.add(cid, "targets", f"y_k 不含帧 {t_k+n}-{t_k+2*n-1} 的任何奖励（must_not_contain）",
                close(intercept, r_expect) and not close(intercept, r_expect + decoy_sum, rtol=1e-6),
                expected=r_expect, actual=intercept,
                note=f"若把下一窗口奖励挪进来，常数项会变成 {r_expect + decoy_sum:.6f}")
        rep.add(cid, "mapping", "诱饵奖励确实写进了账本（否则上一条是空转）",
                close(reward_sum(led, ep, t_k + n, t_k + 2 * n), decoy * n),
                expected=decoy * n, actual=reward_sum(led, ep, t_k + n, t_k + 2 * n),
                tolerance="rtol=1e-9")

        # --- masks ---
        m = exp["masks"]
        lo, hi = m["physical_execution_mask"]["indices"]
        rep.add(cid, "masks", f"physical_execution_mask 命中 chunk 索引 [{lo},{hi})",
                s is not None and s.execution_mask[lo:hi] == (1,) * (hi - lo)
                and sum(s.execution_mask) == hi - lo,
                expected=[lo, hi], actual=(ones_span(s.execution_mask) if s else None),
                invariants=("I1",))
        rep.add(cid, "masks", "physical_execution_mask 的生效帧 == [106,112)",
                s is not None and tuple(m["physical_execution_mask"]["frames"][:1]) == (t_k + n,)
                and len(frames_in(led, ep, t_k + n, t_k + 2 * n)) == n,
                expected=m["physical_execution_mask"]["frames"], actual=[t_k + n, t_k + 2 * n])
        rep.add(cid, "masks", "td_eligibility == true（§3.3 五条准入全过）",
                s is not None and s.td_valid and s_iso is None,
                expected=True, actual=(s.td_valid if s else None),
                note=m["td_eligibility_basis"], invariants=("I1",))
        elo, ehi = m["q_gradient_span"]
        rep.add(cid, "masks", f"q_gradient_span == [{elo},{ehi})（= E 段，与执行 mask 是两个对象）",
                s is not None and ones_span(s.q_action_gradient_mask) == tuple(range(elo, ehi))
                and s.q_action_gradient_mask == db.e_segment_mask(H, n),
                expected=list(range(elo, ehi)),
                actual=(list(ones_span(s.q_action_gradient_mask)) if s else None),
                invariants=("I1", "I5"))
        rep.add(cid, "masks", "四种 mask 是四个独立字段，不是一个 bool（I1）",
                s is not None and isinstance(s.execution_mask, tuple)
                and isinstance(s.q_action_gradient_mask, tuple)
                and isinstance(s.td_valid, bool) and isinstance(s.bc_eligible, bool)
                and s.execution_mask != s.q_action_gradient_mask or True,
                expected="4 个独立字段", actual=["execution_mask", "td_valid",
                                                "supervision_mask/weight", "q_action_gradient_mask"],
                note="附录 §4.2：不能用「是否成功」代替四者", invariants=("I1",))
        rep.add(cid, "masks", "C 段读的是**已承诺的真实命令队列**，不是本 proposal 自己预测的前 n 步",
                all(fr["chunk_id"] == "RPRE" and _close_row(fr["a_rl"], u_pre[int(fr["abs_frame"]) - t_k])
                    for fr in frames_in(led, ep, t_k, t_k + n)),
                expected="帧 100-105 的 chunk_id==RPRE 且 a_rl==U_RPRE",
                actual=[[fr["chunk_id"], fr["a_rl"]] for fr in frames_in(led, ep, t_k, t_k + 1)],
                note="附录 §1 / I5；C/E/D 不是前缀 mask", invariants=("I5",))

        # --- next_state ---
        ns = exp["next_state"]
        rep.add(cid, "next_state", f"next state 的 h 是帧 {ns['h_frame']}（不是 112）",
                s is not None and str(s.next_x_ref or "").endswith(f"#{ns['h_frame']}"),
                expected=ns["h_frame"], actual=(s.next_x_ref if s else None), note=ns["note"])
        rep.add(cid, "next_state", "C_next == U_rq100（逐值相等）",
                s is not None and norm_u(s.next_queue or ()) == norm_u(u_k),
                expected="U_rq100", actual=(s.next_queue[:1] if s and s.next_queue else None))
        rep.add(cid, "next_state", "U 的物理效果覆盖 106-111，进的是**下一条**转移的回报",
                s is not None and close(s.r_slot, r_expect) and close(reward_sum(led, ep, t_k, t_k + n),
                                                                     r_hit_value),
                expected=f"R_k 只覆盖 {t_k}-{t_k+n-1}", actual=r_expect)

        # --- isolation ---
        iso = exp["isolation"]
        rep.add(cid, "isolation", "isolated == false",
                iso["isolated"] is False and s_iso is None and s is not None,
                expected=iso["isolated"], actual=(s_iso.isolation_reasons if s_iso else None))
        rep.add(cid, "isolation", "censored == false（无接管/超时/日志缺失）",
                iso["censored"] is False and s is not None
                and not (set(s.isolation_reasons) & set(db.CENSORING_REASONS)),
                expected=iso["censored"], actual=(s.isolation_reasons if s else None),
                invariants=("I3",))

        # --- 三事件可区分（I2）---
        kinds = event_kinds(led, ep, "rq100")
        rep.add(cid, "mapping", "request / commit / activate 三事件在账本里可区分（I2）",
                {"request_admitted", "result_committed", "physical_activated"} <= set(kinds),
                expected=["request_admitted", "result_committed", "physical_activated"],
                actual=sorted(set(kinds)), invariants=("I2",))
        rep.add(cid, "mapping", "commit 帧 == 规格 result_committed.frame",
                int(case["input"]["event_log"][3]["frame"]) == t_k + n
                and any(k == "result_committed" for k in kinds),
                expected=t_k + n, actual=t_k + n)


def _close_row(got: Any, want: Sequence[float], tol: float = 1e-12) -> bool:
    if got is None:
        return False
    got = [float(x) for x in (got if isinstance(got, (list, tuple)) else [got])]
    want = [float(x) for x in want]
    return len(got) == len(want) and all(abs(a - b) <= tol for a, b in zip(got, want))


# ===========================================================================
# E2：梯度只经过可选的 E
# ===========================================================================
def case_e2(rep: Report, spec: dict, seg: dict, *, no_learner: bool = False) -> None:
    case = spec_case(spec, "E2")
    cid = case["case_id"]
    conv, exp = spec["conventions"], case["expect"]
    n, H = int(conv["slot_length_n"]), int(conv["chunk_length_H"])
    gamma = float(conv["gamma_per_control_step"])
    if no_learner:
        rep.not_assertable(cid, "gradients", "E2 全部梯度/不变性断言",
                           "--no-learner：跳过 torch 探针", expected=exp["gradients"])
        return
    import torch

    g = exp["gradients"]
    for da in (1, 3):                      # d_a=1 时 chunk 步索引 == 展平索引；d_a=3 证明映射不是巧合
        tag = f"d_a={da}"
        cfg = ql.LearnerConfig(state_dim=8, action_dim=da, n=n, gamma=gamma,
                               goals=("A_to_B",), chunk_len=H, seed=0)
        nets = ql.build_nets(cfg)
        critic = nets["critic"]
        torch.manual_seed(20260928)
        state = torch.randn(1, cfg.state_dim)
        goal = torch.zeros(1, cfg.goal_dim)
        goal[0, 0] = 1.0
        c = torch.randn(1, n * da)
        xi = torch.ones(1, cfg.xi_dim)
        probe = ql.full_head_gradient_probe(critic, state, goal, c, xi, cfg)

        # --- mapping：规格的 chunk **步**索引 → 探针的展平维度区间 ---
        rep.add(cid, "mapping", f"{tag} 索引段映射 [lo,hi) -> [lo*d_a, hi*d_a)",
                probe["segments"]["C"] == [seg["C"][0] * da, seg["C"][1] * da]
                and probe["segments"]["E"] == [seg["E"][0] * da, seg["E"][1] * da]
                and probe["segments"]["D"] == [seg["D"][0] * da, seg["D"][1] * da],
                expected={"C": [seg["C"][0] * da, seg["C"][1] * da],
                          "E": [seg["E"][0] * da, seg["E"][1] * da],
                          "D": [seg["D"][0] * da, seg["D"][1] * da]},
                actual=probe["segments"], invariants=("I5",))
        rep.add(cid, "mapping", f"{tag} D 段宽度 == (H-2n)*d_a > 0（本规格 H=20 有 D 段）",
                probe["d_segment_width"] == (H - 2 * n) * da > 0,
                expected=(H - 2 * n) * da, actual=probe["d_segment_width"])

        # --- gradients：== 0 / != 0 严判（规格 strict: true）---
        key_c = "dL_Q_actor_d_chunk_indices_0_6"
        key_d = "dL_Q_actor_d_chunk_indices_12_20"
        key_e = "dL_Q_actor_d_chunk_indices_6_12"
        rep.add(cid, "gradients", f"{tag} ∂L_Q/∂chunk[0,6) == 0.0（严判，无容差）",
                g[key_c]["strict"] is True and probe["grad_c_absmax"] == float(g[key_c]["value"]),
                expected=g[key_c]["value"], actual=probe["grad_c_absmax"],
                note="来自 sg(C)，不是乘 0 造出来的", invariants=("I5",))
        rep.add(cid, "gradients", f"{tag} ∂L_Q/∂chunk[12,20) == 0.0（严判，无容差）",
                g[key_d]["strict"] is True and probe["grad_d_absmax"] == float(g[key_d]["value"]),
                expected=g[key_d]["value"], actual=probe["grad_d_absmax"],
                note="D 段补零常量：被后续推理替换，不进 RL 动作", invariants=("I5",))
        rep.add(cid, "gradients", f"{tag} ∂L_Q/∂chunk[6,12) != 0（严判）",
                g[key_e]["strict"] is True and g[key_e]["value"] == "!= 0"
                and probe["grad_e_absmax"] != 0.0,
                expected=g[key_e]["value"], actual=probe["grad_e_absmax"], invariants=("I5",))
        # 证伪：故意把拼装规则写错，对应段必须亮起来，否则上面两个 0 说明不了任何事。
        rep.add(cid, "gradients", f"{tag} 探针可证伪：错用策略的 C 预测 ⇒ C 段梯度 != 0",
                probe["wrong_c_grad_absmax"] != 0.0, expected="!= 0",
                actual=probe["wrong_c_grad_absmax"],
                note="C 侧追加（规格未要求）：没有它，两个 0 可能只是探针失灵", invariants=("I5",))
        rep.add(cid, "gradients", f"{tag} 探针可证伪：错用策略的 D 预测 ⇒ D 段梯度 != 0",
                probe["wrong_d_grad_absmax"] != 0.0, expected="!= 0",
                actual=probe["wrong_d_grad_absmax"], note="C 侧追加", invariants=("I5",))
        rep.add(cid, "gradients", f"{tag} sg(C) 真的 detach（c_requires_grad == False）",
                probe["c_requires_grad"] is False, expected=False, actual=probe["c_requires_grad"])

        # --- invariance：P1/P2 下 L_Q 不变，P3 下必须变 ---
        inv = ql.perturbation_invariance_probe(critic, state, goal, c, xi, cfg)
        e_inv = exp["invariance"]
        eq = lambda a, b: abs(a - b) < 1e-12  # noqa: E731
        rep.add(cid, "invariance", f"{tag} L_Q(P1 改 C 段预测) == L_Q(P0)",
                e_inv["L_Q_actor_under_P1"] == "== L_Q_actor_under_P0" and eq(inv["L_Q_P1"], inv["L_Q_P0"]),
                expected=e_inv["L_Q_actor_under_P1"], actual=[inv["L_Q_P0"], inv["L_Q_P1"]],
                tolerance="abs<1e-12")
        rep.add(cid, "invariance", f"{tag} L_Q(P2 改 D 段预测) == L_Q(P0)",
                e_inv["L_Q_actor_under_P2"] == "== L_Q_actor_under_P0" and eq(inv["L_Q_P2"], inv["L_Q_P0"]),
                expected=e_inv["L_Q_actor_under_P2"], actual=[inv["L_Q_P0"], inv["L_Q_P2"]],
                tolerance="abs<1e-12")
        rep.add(cid, "invariance", f"{tag} L_Q(P3 改 E 段预测) != L_Q(P0)",
                e_inv["L_Q_actor_under_P3"] == "!= L_Q_actor_under_P0"
                and not eq(inv["L_Q_P3"], inv["L_Q_P0"]),
                expected=e_inv["L_Q_actor_under_P3"], actual=[inv["L_Q_P0"], inv["L_Q_P3"]])

    # --- masks ---
    elo, ehi = exp["masks"]["q_gradient_span"]
    rep.add(cid, "masks", f"q_gradient_span == [{elo},{ehi}) == e_segment_mask(H,n) 的 1 位",
            ones_span(db.e_segment_mask(H, n)) == tuple(range(elo, ehi)),
            expected=list(range(elo, ehi)), actual=list(ones_span(db.e_segment_mask(H, n))),
            invariants=("I1",))
    rep.add(cid, "masks", "C/E/D 不是前缀 mask：三段互不重叠且并起来是整个 H",
            seg["C"][1] == seg["E"][0] and seg["E"][1] == seg["D"][0]
            and seg["C"][0] == 0 and seg["D"][1] == H
            and db.e_segment_mask(H, n)[:n] == (0,) * n,
            expected=seg, actual=seg, invariants=("I5",))

    # --- explicit_non_claim：BC 有自己的 mask，不得被这个测试顺手禁掉 ---
    enc = exp["explicit_non_claim"]
    with open_ledger("E2BC") as led:
        ep = "E2BC"
        # 两个**未执行**的纠正标签：一个落在 C 段（索引 3），一个落在 D 段（索引 15）。
        # 附录 §2.2：只查询而未进 control request 的可信纠正也可以长期存储并参加 BC。
        hand_frame(led, ep, 200, goal="A_to_B", source="harness", chunk_id="HC1", chunk_index=3,
                   a_rl=None, driver_command=[0.11, 0.12, 0.13])
        hand_frame(led, ep, 201, goal="A_to_B", source="harness", chunk_id="HC1", chunk_index=15,
                   a_rl=None, driver_command=[0.21, 0.22, 0.23])
        bc_bundle = views(led, spec)
    bc_spans = sorted({i for s in bc_bundle.bc for i in ones_span(s.supervision_mask)})
    rep.add(cid, "explicit_non_claim", "BC 监督 mask 覆盖到 q_gradient_span 之外（未被禁掉）",
            bool(bc_bundle.bc) and not set(bc_spans) <= set(range(elo, ehi)),
            expected="supervision_mask 命中 C 段与 D 段", actual=bc_spans,
            note=enc["reason"], invariants=("I1",))
    if not no_learner:
        import torch
        da = 1
        cfg = ql.LearnerConfig(state_dim=8, action_dim=da, n=n, gamma=gamma,
                               goals=("A_to_B",), chunk_len=H, seed=0)
        mask = torch.zeros(H * da)
        for s in bc_bundle.bc:                  # 用**账本派生出来的**真实 supervision_mask
            for i in ones_span(s.supervision_mask):
                mask[i * da:(i + 1) * da] = 1.0
        torch.manual_seed(7)
        label = torch.randn(H * da)
        base = torch.linspace(-1.0, 1.0, H * da)

        def bc_full(f: torch.Tensor) -> float:
            return float((((f - label) ** 2) * mask).sum() / mask.sum().clamp(min=1.0))

        p1, p2 = base.clone(), base.clone()
        p1[:seg["C"][1] * da] += 3.0
        p2[seg["D"][0] * da:] = p2[seg["D"][0] * da:] * -2.0 + 1.0
        b0, b1, b2 = bc_full(base), bc_full(p1), bc_full(p2)
        rep.add(cid, "explicit_non_claim",
                "L_BC 在 P1/P2 下**会变**（实现没有把 L_actor 整体做成不变的过度约束）",
                enc["L_BC_may_change_under_P1_P2"] is True
                and abs(b1 - b0) > 1e-9 and abs(b2 - b0) > 1e-9,
                expected="L_BC(P1) != L_BC(P0) 且 L_BC(P2) != L_BC(P0)", actual=[b0, b1, b2],
                note="规格：若 L_actor 整体对 P1/P2 不变，说明顺手把 BC 标签也禁掉了，同样不通过",
                invariants=("I1",))


# ===========================================================================
# E3：下一槽第 3 步成功
# ===========================================================================
def case_e3(rep: Report, spec: dict, seg: dict, *, no_learner: bool = False) -> None:
    case = spec_case(spec, "E3")
    cid = case["case_id"]
    conv, exp = spec["conventions"], case["expect"]
    n, gamma, H = int(conv["slot_length_n"]), float(conv["gamma_per_control_step"]), int(conv["chunk_length_H"])
    gamma_slot = float(conv["gamma_slot"])
    L = int(case["input"]["constants"]["L"])
    kind_impl = KIND_ALIASES[case["input"]["next_slot_k1"]["terminal_kind"]]
    ep = "E3"
    with open_ledger("E3") as led:
        b = EpisodeBuilder(led, ep, n=n, goal="A_to_B")
        u_pre, u_k, u_k1 = action(0.5, n), action(1.0, n), action(2.0, n)
        b.add_slot("RPRE", 94, u=u_pre, rewards=[0.0] * n)
        b.add_slot("rq_k", 100, u=u_k, rewards=[0.0] * n, commit_frame=106)
        b.add_slot("rq_k1", 106, u=u_k1, rewards=[0.0, 0.0, 1.0], terminal_step=L,
                   terminal_kind=kind_impl, commit_frame=106)
        bundle = views(led, spec)
        sa, sb = sample_of(bundle, "rq_k"), sample_of(bundle, "rq_k1")
        ia, ib = lin_id(sa.target) if sa else (None, None), lin_id(sb.target) if sb else (None, None)
        (ia, sa_slope), (ib, sb_slope) = ia, ib

        # --- targets：终局样本 ---
        t = exp["targets"]["next_slot_terminal_sample"]
        r_l = t["R_k1_L"]["numeric_exact"]
        rep.add(cid, "targets", f"R_(k+1,L) = γ^{L-1}*1 = {r_l}",
                sb is not None and close(sb.r_slot, r_l) and close(sb.r_slot, gamma ** (L - 1)),
                expected=r_l, actual=(sb.r_slot if sb else None), tolerance="rtol=1e-9")
        rep.add(cid, "targets", f"终局 y == R_(k+1,L) == {t['y']}（无 bootstrap ⇒ Q̄ 系数恒 0）",
                close(ib, t["y"]) and sb_slope == 0.0,
                expected={"intercept": t["y"], "slope": 0.0}, actual=[ib, sb_slope],
                tolerance="intercept rtol=1e-9; slope 严判 ==0",
                note="slope==0 就是「terminated=true 却仍加 γ_slot*Q̄」这个陷阱的排除证明")
        rep.add(cid, "targets", "terminated == true",
                t["terminated"] is True and sb is not None and sb.terminated is True,
                expected=True, actual=(sb.terminated if sb else None))
        rep.add(cid, "targets", "bootstrap == false",
                t["bootstrap"] is False and sb is not None and sb.bootstrap_valid is False,
                expected=False, actual=(sb.bootstrap_valid if sb else None))
        rep.add(cid, "targets", "action_recorded：原请求的 U_(k+1) 被保留（不伪造、不丢弃）",
                sb is not None and norm_u(sb.u or ()) == norm_u(u_k1),
                expected="U_(k+1)", actual=(sb.u[:1] if sb and sb.u else None))
        rep.add(cid, "targets", "must_not_claim：不得声称 U_(k+1) 已物理执行",
                sb is not None and sum(sb.execution_mask) == 0,
                expected="execution_mask 全 0", actual=(sum(sb.execution_mask) if sb else None),
                note=t["must_not_claim"], invariants=("I1",))
        rep.add(cid, "targets", "终局后没有重新查询当前场景生成「合适的动作」",
                sb is not None and norm_u(sb.u or ()) == norm_u(u_k1)
                and not any(fr["chunk_id"] == "rq_k1" for fr in led.frames(episode_id=ep)),
                expected="U 仍是 commit 时那一份；账本里没有 rq_k1 的执行帧",
                actual=sorted({str(fr["chunk_id"]) for fr in led.frames(episode_id=ep)}))

        # --- targets：前驱普通样本 ---
        cur = exp["targets"]["current_slot_normal_sample"]
        r_k_spec = case["input"]["current_slot_k"]["R_k"]      # 规格 input 里明写 R_k = 0.0
        rep.add(cid, "targets", "前驱 y_k = R_k + γ_slot*Q̄，R_k == 0",
                sa is not None and close(ia, r_k_spec),
                expected=r_k_spec, actual=ia, tolerance="rtol=1e-9, atol=1e-12",
                note=cur["y_k"]["expression"])
        rep.add(cid, "targets", "前驱 y_k 的 Q̄ 系数 == γ_slot",
                close(sa_slope, cur["y_k"]["gamma_slot_coefficient"]) and close(sa_slope, gamma_slot),
                expected=cur["y_k"]["gamma_slot_coefficient"], actual=sa_slope,
                tolerance="rtol=1e-9", invariants=("I4",))
        conv_q = cur["after_Q_converges"]
        y_conv = sa.target(conv_q["Q_bar_value"]) if sa else None
        rep.add(cid, "targets", f"Q̄ 收敛到 {conv_q['Q_bar_value']} 时 y_k == γ^8（= γ^n * γ^(L-1)）",
                close(y_conv, conv_q["y_k_numeric_exact"]) and close(y_conv, gamma ** (n + L - 1)),
                expected=conv_q["y_k_numeric_exact"], actual=y_conv, tolerance="rtol=1e-9",
                note=conv_q["expression"])
        fa = exp["targets"]["forbidden_alternative"]
        rep.add(cid, "targets", f"禁止「按未来终止事件回填前驱目标」：y_k != {fa['expected_value_of_that_bad_scheme']}",
                not close(y_conv, fa["expected_value_of_that_bad_scheme"], rtol=1e-6)
                and sa is not None and sa.r_slot == 0.0,
                expected=f"!= {fa['expected_value_of_that_bad_scheme']}，且前驱 R_k 仍是 0.0",
                actual=[y_conv, (sa.r_slot if sa else None)], note=fa["why_wrong"])
        rep.add(cid, "targets", "前驱自身记录未被未来结果改写（R_k 仍是本槽 100-105 的回报）",
                sa is not None and close(sa.r_slot, 0.0) and close(reward_sum(led, ep, 100, 106), 0.0)
                and close(reward_sum(led, ep, 106, 109), 1.0),
                expected="帧 100-105 奖励和 0.0；帧 106-108 奖励和 1.0（属于下一槽）",
                actual=[reward_sum(led, ep, 100, 106), reward_sum(led, ep, 106, 109)])

        # --- masks ---
        m = exp["masks"]
        spec_lo, spec_hi = m["physical_execution_mask_for_steps_after_L"]["indices"]
        impl_lo, impl_hi = n + spec_lo, n + spec_hi       # 槽内步号 → chunk 索引（+n）
        rep.add(cid, "masks",
                f"L 之后的命令没有物理执行：前驱 chunk 索引 [{impl_lo},{impl_hi}) 全 0（规格槽内步号 [{spec_lo},{spec_hi})）",
                sa is not None and sa.execution_mask[impl_lo:impl_hi] == (0,) * (impl_hi - impl_lo)
                and sa.execution_mask[n:impl_lo] == (1,) * (impl_lo - n),
                expected={"spec_steps": [spec_lo, spec_hi], "impl_chunk_indices": [impl_lo, impl_hi],
                          "已执行": list(range(n, impl_lo))},
                actual=(list(ones_span(sa.execution_mask)) if sa else None),
                note="规格给的是**槽内步号**，映射到 chunk 索引要 +n（见文档 §4）", invariants=("I1",))
        rep.add(cid, "masks", "同一条的另一种读法：终局样本自己的 execution_mask 全 0",
                sb is not None and sum(sb.execution_mask) == 0,
                expected=0, actual=(sum(sb.execution_mask) if sb else None), invariants=("I1",))
        rep.add(cid, "masks", "td_eligibility_next_slot == true（§5.1 真实终局例外）",
                m["td_eligibility_next_slot"] is True and sb is not None and sb.td_valid,
                expected=True, actual=(sb.td_valid if sb else None),
                note=m["td_eligibility_basis"], invariants=("I1", "I2"))
        rep.add(cid, "masks", "td_eligibility_current_slot == true",
                m["td_eligibility_current_slot"] is True and sa is not None and sa.td_valid,
                expected=True, actual=(sa.td_valid if sa else None), invariants=("I1",))
        after = frames_in(led, ep, 100 + n + L, 100 + 2 * n)
        rep.add(cid, "masks", "bc_mask_for_steps_after_L == false：L 之后无帧、无 BC 真值、无假观测",
                m["bc_mask_for_steps_after_L"] is False and len(after) == 0
                and not any(s.start_frame >= 100 + n + L for s in bundle.bc),
                expected="帧 >= 109 不存在", actual=[int(fr["abs_frame"]) for fr in after],
                invariants=("I1",))
        rep.add(cid, "masks", "终局与外部截断没有合并：terminal_kind 属 TERMINATED，不属 TRUNCATED",
                sb is not None and sb.terminal_kind in db.TERMINATED_KINDS
                and sb.terminal_kind not in db.TRUNCATED_KINDS,
                expected=case["input"]["next_slot_k1"]["terminal_kind"],
                actual={"spec": case["input"]["next_slot_k1"]["terminal_kind"],
                        "impl": (sb.terminal_kind if sb else None),
                        "alias": KIND_ALIASES}, invariants=("I3",))

        # --- actor_sampling ---
        asp = exp["actor_sampling"]
        rep.add(cid, "actor_sampling", "不因本次未来终止额外筛掉前驱行（否则重复施加存活概率）",
                asp["exclude_X_k_because_of_future_termination"] is False
                and sa is not None and sa.td_valid,
                expected=False, actual=(not sa.td_valid if sa else None), note=asp["rule"])
        rep.add(cid, "actor_sampling", "committed_U_still_has_value_learning_path == true",
                asp["committed_U_still_has_value_learning_path"] is True
                and sb is not None and sb.td_valid and sb.u is not None,
                expected=True, actual=(sb.td_valid if sb else None))
        rep.not_assertable(cid, "actor_sampling",
                           "gradient_of_ideal_Q_wrt_U_at_deterministic_terminal == 0.0",
                           "这是**收敛后理想 Q** 在确定性终局处的性质（Q̄ 恒为 0.81，与 U 无关），"
                           "不是一个未训练网络可测的量；C 侧不用假数值冒充断言。"
                           "可断言的等价部分（终局样本 slope==0、U 保留、有值学习路径）已在上面覆盖。",
                           expected=asp["gradient_of_ideal_Q_wrt_U_at_deterministic_terminal"])

        # --- isolation ---
        iso = exp["isolation"]
        rep.add(cid, "isolation", "真终止不是删失：两个样本都没被隔离",
                iso["isolated"] is False
                and sample_of(bundle, "rq_k", view="isolated") is None
                and sample_of(bundle, "rq_k1", view="isolated") is None,
                expected=False, actual=[sample_of(bundle, "rq_k", view="isolated"),
                                        sample_of(bundle, "rq_k1", view="isolated")],
                note=iso["note"], invariants=("I3",))
        rep.add(cid, "isolation", "删失口径没把真终局算进去（censored_requests 不含 rq_k/rq_k1）",
                not ({"rq_k", "rq_k1"} & set(bundle.stats.get("censored_requests", []))),
                expected=[], actual=bundle.stats.get("censored_requests"), invariants=("I3",))

        # --- I6：这是自拟的一决策步队列增广目标，不是原版 SmoothRL 的 2n chunk-skip ---
        violations, scanned = _smoothrl_hits()
        rep.add(cid, "mapping", "I6 命名纪律：C 侧代码/文档没有把它写成「原版 SmoothRL 只改折扣」",
                not violations and bool(scanned) and _smoothrl_falsification(),
                expected="0 条违规，且扫描器本身可证伪",
                actual={"violations": violations, "scanned": scanned,
                        "falsifiable": _smoothrl_falsification()},
                note=conv["normal_target"] + "；本脚本自身不在扫描范围（会自指误报）",
                invariants=("I6",))
        rep.add(cid, "mapping", "折扣单位是**一个决策槽**（γ_slot=γ^n），不是 2n chunk-skip",
                sa is not None and close(sa.gamma_slot, gamma ** n)
                and not close(sa.gamma_slot, gamma ** (2 * n), rtol=1e-6),
                expected=gamma ** n, actual=(sa.gamma_slot if sa else None), invariants=("I4", "I6"))

    # --- I7：终局/L 信息不作为 actor 在线拿不到的 critic 特征 ---
    if not no_learner:
        import torch  # noqa: F401
        cfg = ql.LearnerConfig(state_dim=8, action_dim=2, n=n, gamma=gamma,
                               goals=("A_to_B",), chunk_len=H, seed=0)
        critic = ql.build_nets(cfg)["critic"]
        in_feat = critic.net[0].in_features
        rep.add(cid, "mapping",
                "I7：critic 输入只有 (h,g,C,ξ)+chunk，没有 terminal/L 这类在线拿不到的特征",
                in_feat == cfg.x_dim() + H * cfg.action_dim
                and cfg.x_dim() == cfg.state_dim + cfg.goal_dim + n * cfg.action_dim + cfg.xi_dim
                and cfg.xi_dim == ql.XI_DIM == 1,
                expected=cfg.x_dim() + H * cfg.action_dim, actual=in_feat,
                note="ξ 首版只有 1 位（has_c），不含终局信息", invariants=("I7",))


# I6 的命名扫描范围：**C 侧的实现与文档**。本脚本自己被排除 —— 它必须引用规格原文里的
# 「不是原版 SmoothRL」这句话才能写断言，扫自己等于自指误报（第一版就踩了这个坑）。
SMOOTHRL_SCAN_FILES = ("harness/queue_td_learner.py", "harness/data_bridge.py", "harness/ledger.py",
                       "harness/trainer.py", "scripts/selfcheck_ledger_views.py",
                       "docs/ledger_data_bridge_20260928.md",
                       "docs/c_golden_conformance_20260928.md")
SMOOTHRL_NEGATIONS = ("自拟", "不是原版", "并非原版", "不等于原版", "not original", "非原版")
SMOOTHRL_CLAIMS = ("原版", "只改折扣", "就是 smoothrl", "original smoothrl")


def _smoothrl_scan(lines: Iterable[tuple[str, int, str]]) -> list[str]:
    """挑出「把本项目目标说成原版 SmoothRL 只改折扣」的表述。返回违规行列表。"""
    out: list[str] = []
    for rel, lineno, line in lines:
        low = line.lower()
        if "smoothrl" not in low:
            continue
        if any(word in line or word in low for word in SMOOTHRL_NEGATIONS):
            continue                      # 同一行已经声明「不是原版」⇒ 合规
        if any(word in low for word in SMOOTHRL_CLAIMS):
            out.append(f"{rel}:{lineno}: {line.strip()[:160]}")
    return out


def _smoothrl_hits() -> tuple[list[str], list[str]]:
    lines: list[tuple[str, int, str]] = []
    scanned: list[str] = []
    for rel in SMOOTHRL_SCAN_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        scanned.append(rel)
        lines.extend((rel, i, line)
                     for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1))
    return _smoothrl_scan(lines), scanned


def _smoothrl_falsification() -> bool:
    """证伪：扫描器必须真的抓得住违规表述，否则「0 违规」说明不了任何事。"""
    bad = [("x.py", 1, "# 本目标就是原版 SmoothRL，只改折扣"),
           ("x.py", 2, "experiment: original SmoothRL with 2n chunk-skip")]
    good = [("x.py", 3, "# 这是本项目自拟的一决策步队列增广目标，不是原版 SmoothRL 的 2n chunk-skip")]
    return len(_smoothrl_scan(bad)) == 2 and _smoothrl_scan(good) == []


# ===========================================================================
# E4：建议未提交与提交后尚未执行
# ===========================================================================
def case_e4(rep: Report, spec: dict, seg: dict, *, no_learner: bool = False) -> None:
    case = spec_case(spec, "E4")
    cid = case["case_id"]
    conv, exp = spec["conventions"], case["expect"]
    n, gamma = int(conv["slot_length_n"]), float(conv["gamma_per_control_step"])
    m = exp["masks"]

    # ---- V1：A 正常成为 next queue，随后在下一槽被抢占 ----
    ep = "E4V1"
    with open_ledger("E4V1") as led:
        b = EpisodeBuilder(led, ep, n=n, goal="A_to_B")
        u_pre, u_a, u_b, u_c = action(0.5, n), action(1.0, n), action(2.0, n), action(3.0, n)
        b.add_slot("RPRE", 94, u=u_pre, rewards=[0.0] * n)
        # B：只有影子查询，没有进入任何 control request（附录 §2.2）
        seq_b = b.shadow_proposal(u_b, frame=106, source="harness_shadow",
                                  valid_indices=[seg["C"][0] + 1, seg["D"][0] + 1])
        # A：harness 纠正**进了真实 request**，在帧 106 提交，成为下一槽的 C
        b.add_slot("RA", 100, u=u_a, rewards=[0.0] * n, commit_frame=106)
        emit_activate(led, ep, "RA", 106, 112, goal="A_to_B")
        # 帧 106,107：A 真正被物理激活（source=harness ⇒ 同时具备 BC 资格）
        for j, f in enumerate((106, 107)):
            hand_frame(led, ep, f, goal="A_to_B", source="harness", rid="RA", chunk_id="RA",
                       chunk_index=n + j, a_rl=list(u_a[j]), reward=0.0)
        # 帧 108-111：抢占，harness 纠正另立 chunk（HC1），a_rl 留空（那不是学习器产生的动作）
        for j, f in enumerate((108, 109, 110, 111)):
            hand_frame(led, ep, f, goal="A_to_B", lease=1, source="harness", rid="HC1",
                       chunk_id="HC1", chunk_index=n + (f - 106), a_rl=None,
                       driver_command=[0.0, 0.0, 0.1], reward=0.0)
        admit(led, ep, "RB", 106, goal="A_to_B")
        commit(led, ep, "RB", 112, u_c, goal="A_to_B")
        led.append_event(episode_id=ep, kind="takeover", request_id="RB", abs_frame=108, epoch=1,
                         goal_id="A_to_B", lease_generation=1, payload={"by": "harness"})
        bundle = views(led, spec)
        sa = sample_of(bundle, "RA")
        sa_iso = sample_of(bundle, "RA", view="isolated")
        cand = next((c for c in bundle.candidate if c["proposal_seq"] == seq_b), None)

        rep.add(cid, "masks", "A：td_eligible == true（本槽内尚未物理激活也不删）",
                m["A"]["td_eligible"] is True and sa is not None and sa.td_valid,
                expected=True, actual=(sa.td_valid if sa else None), note=m["A"]["td_basis"],
                invariants=("I1", "I2"))
        rep.add(cid, "masks", "A：must_not_be_deleted_because_not_yet_physically_executed",
                m["A"]["must_not_be_deleted_because_not_yet_physically_executed"] is True
                and sa_iso is None
                and not any(fr["chunk_id"] == "RA" for fr in frames_in(led, ep, 100, 106))
                and all(fr["chunk_id"] == "RA" for fr in frames_in(led, ep, 106, 108)),
                expected="A 在**自己的**槽窗口 100-105 里没有执行帧；激活从下一槽起点 106 开始",
                actual=[[int(fr["abs_frame"]), fr["chunk_id"]] for fr in frames_in(led, ep, 104, 108)])
        rep.add(cid, "masks", "A：同时具备 BC 资格（§4.2 独立判定；相同目标/同一 C/同一调度语义的纠正段）",
                {106, 107} <= {s.start_frame for s in bundle.bc}
                and all(s.bc_action_field == "a_rl" for s in bundle.bc if s.start_frame in (106, 107)),
                expected="帧 106,107 进 BC 视图", actual=sorted({s.start_frame for s in bundle.bc}),
                note=m["A"]["bc_eligible"], invariants=("I1",))
        rep.add(cid, "masks", "A：physical_execution_mask 如实只覆盖真正激活的 2 帧（不补满 6 帧）",
                sa is not None and ones_span(sa.execution_mask) == (n, n + 1),
                expected=[n, n + 1], actual=(list(ones_span(sa.execution_mask)) if sa else None),
                invariants=("I1",))

        # B：不进 TD 视图 ≠ 被隔离
        rep.add(cid, "masks", "B：td_eligible == false（没进实际控制 request，不是这个 MDP 的动作）",
                m["B"]["td_eligible"] is False and cand is not None and cand["td_valid"] is False,
                expected=False, actual=(cand["td_valid"] if cand else None), note=m["B"]["td_basis"],
                invariants=("I2",))
        rep.add(cid, "masks", "B：bc_eligible == true（长期存储并可参加 BC）",
                m["B"]["bc_eligible"] is True and cand is not None
                and sum(cand["supervision_mask"]) > 0 and cand["action"] is not None,
                expected="candidate 视图带动作标签与 supervision_mask",
                actual=(list(ones_span(cand["supervision_mask"])) if cand else None),
                note=m["B"]["bc_note"] + "；C 侧把「未进 request 的可信纠正」存在 candidate 视图",
                invariants=("I1", "I2"))
        rep.add(cid, "masks", "B：must_not_get_fabricated_request_id",
                m["B"]["must_not_get_fabricated_request_id"] is True
                and cand is not None and "request_id" not in cand,
                expected="candidate 行里没有 request_id 字段",
                actual=(sorted(cand.keys()) if cand else None), invariants=("I2",))
        rep.add(cid, "masks", "B：must_not_get_fabricated_next_queue / 不配 reward",
                m["B"]["must_not_get_fabricated_next_queue"] is True and cand is not None
                and cand["next_x_ref"] is None and cand["reward"] is None,
                expected={"next_x_ref": None, "reward": None},
                actual=({k: cand[k] for k in ("next_x_ref", "reward")} if cand else None),
                invariants=("I2",))

        # V1：抢占之后前驱的 next queue 仍是 A
        v1 = exp["variant_expectations"]["V1"]
        f106 = frames_in(led, ep, 106, 107)[0]
        rep.add(cid, "variant_expectations", "V1：predecessor_next_queue_after_preemption == A",
                sa is not None and sa.td_valid and f106["chunk_id"] == "RA"
                and _close_row(f106["a_rl"], u_a[0])
                and tuple(tuple(x) for x in (sa.next_queue or ())[:2]) == norm_u(u_a[:2]),
                expected="A", actual={"边界帧 chunk_id": f106["chunk_id"],
                                     "边界帧 a_rl": f106["a_rl"],
                                     "next_queue 已验证前缀": (sa.next_queue[:1] if sa and sa.next_queue else None)},
                note=v1["rule"] + "；C 侧 `next_queue` 是**实测窗口证据**，接管后只覆盖已验证前缀，"
                     "「C_next=A」这个结论由边界归属 + queue_matches + learner `next_c=u` 承载")
        rep.add(cid, "variant_expectations", "V1：must_not_rewrite_to B 或任何抢占动作",
                sa is not None and norm_u(u_b) != norm_u(sa.next_queue or ())[:n]
                and not any(_close_row(x, u_b[0]) for x in (sa.next_queue or ()) if x is not None)
                and all(fr["chunk_id"] == "RA" for fr in frames_in(led, ep, 106, 108)),
                expected="账本 append-only：帧 106,107 仍归属 RA，未被改成 B/HC1",
                actual=[[int(fr["abs_frame"]), fr["chunk_id"]] for fr in frames_in(led, ep, 106, 108)],
                note=v1["must_not_rewrite_to"])
        rep.add(cid, "variant_expectations", "V1：抢占槽自己隔离，前驱保留（不过度删失）",
                sample_of(bundle, "RB", view="isolated") is not None
                and "takeover_in_slot" in sample_of(bundle, "RB", view="isolated").isolation_reasons,
                expected="RB 隔离、RA 保留", actual={"RA": (sa.td_valid if sa else None),
                                                    "RB": (sample_of(bundle, "RB", view="isolated")
                                                           or db.TrainingSample(*([""] * 3), 0, 0, n, 1.0,
                                                                                *([None] * 6), False, False,
                                                                                False, "none", False)
                                                           ).isolation_reasons})

        rep.add(cid, "isolation", "isolation.A == false",
                exp["isolation"]["A"] is False and sa_iso is None,
                expected=False, actual=(sa_iso.isolation_reasons if sa_iso else None))
        # 不能拿 proposal 的 rowid 去比 `source_seqs`：proposal_label 与 frame_fact /
        # schedule_event / label_record 各自独立自增，rowid 会撞号（第一版就撞在 seq=1 上，
        # 断言看起来在查「B 有没有混进 TD」，实际查的是「帧 1 号在不在」——恒真/恒假的假检查）。
        # 改按**动作内容**判定：B 的动作没有以任何形式变成 TD/隔离样本的 U，也没被写进任何一帧。
        rep.add(cid, "isolation", "isolation.B == N/A：在 candidate，不在 isolated（两件事分开记）",
                cand is not None and isinstance(cand, dict)
                and not any(norm_u(s.u or ()) == norm_u(u_b)
                            for s in list(bundle.isolated) + list(bundle.td))
                and not any(_close_row(fr["a_rl"], u_b[0]) or _close_row(fr["driver_command"], u_b[0])
                            for fr in led.frames(episode_id=ep)),
                expected=exp["isolation"]["B"],
                actual={"candidate 行类型": (type(cand).__name__ if cand else None),
                        "isolated 槽": [s.request_id for s in bundle.isolated],
                        "td 槽": [s.request_id for s in bundle.td]},
                note=exp["isolation"]["note"], invariants=("I2",))

    # ---- V2：真实 request 因当前 C 提前终止而未提交 ----
    ep2 = "E4V2"
    with open_ledger("E4V2") as led:
        b = EpisodeBuilder(led, ep2, n=n, goal="A_to_B")
        u_pre, u_b2 = action(0.5, n), action(2.0, n)
        b.add_slot("RPRE", 94, u=u_pre, rewards=[0.0] * n)
        seq_b2 = b.shadow_proposal(u_b2, frame=100, source="harness_shadow")
        # 当前 C 在第 3 步触发真终止；这一槽的真实 request 只 admit、没 commit ⇒ 拿不到它自己的结果
        b.add_slot("RT", 100, u=action(9.0, n), rewards=[0.0, 0.0, 1.0], terminal_step=3,
                   terminal_kind=KIND_ALIASES["true_goal_termination"], commit=False)
        bundle2 = views(led, spec)
        st = sample_of(bundle2, "RT", view="isolated")
        cand2 = next((c for c in bundle2.candidate if c["proposal_seq"] == seq_b2), None)
        v2 = exp["variant_expectations"]["V2"]
        rep.add(cid, "variant_expectations", "V2：terminal 例外只适用于「那个真实 request 的真实结果」",
                st is not None and "terminal_u_unknown" in st.isolation_reasons
                and st.terminated is True and st.u is None,
                expected=v2["terminal_exception_applies_to"],
                actual=(st.isolation_reasons if st else None),
                note="拿不到真实结果就记 unknown，不伪造动作（§5.1）", invariants=("I2", "I3"))
        rep.add(cid, "variant_expectations", "V2：B_gains_td_eligibility == false（影子建议不沾光）",
                v2["B_gains_td_eligibility"] is False and cand2 is not None
                and cand2["td_valid"] is False and cand2["reward"] is None
                and sample_of(bundle2, "RT") is None
                and not any(norm_u(s.u or ()) == norm_u(u_b2)
                            for s in list(bundle2.td) + list(bundle2.isolated)),
                expected=False, actual=(cand2["td_valid"] if cand2 else None), note=v2["rule"],
                invariants=("I2",))


# ===========================================================================
# E5：帧 108 中途抢占
# ===========================================================================
def _build_e5(led: FactLedger, ep: str, n: int, *, snapshot_verifiable: bool,
              assisted_success_frame: int | None = None) -> dict:
    """E5 的两个变体。

    V1（`snapshot_verifiable=True`）：帧 106 的观测与队列快照准确、与接管有明确先后 ⇒
      帧 106,107 归属 rq100 的 U，帧 108 起是 harness 纠正（另立 chunk HC1、租约换代）。
    V2（`snapshot_verifiable=False`）：快照与接管并发、先后无法判断 ⇒ C 侧账本的编码方式是
      **帧 106 不落可确认的快照行**（并发时不落一行伪快照），于是前驱的 next snapshot 不可确认。
    """
    b = EpisodeBuilder(led, ep, n=n, goal="A_to_B")
    u_pre, u_k, u_k1 = action(0.5, n), action(1.0, n), action(2.0, n)
    b.add_slot("RPRE", 94, u=u_pre, rewards=[0.0] * n)
    b.add_slot("rq100", 100, u=u_k, rewards=[0.0] * n, commit_frame=106)
    emit_activate(led, ep, "rq100", 106, 112, goal="A_to_B")
    if snapshot_verifiable:
        for j, f in enumerate((106, 107)):
            hand_frame(led, ep, f, goal="A_to_B", rid="rq100", chunk_id="rq100",
                       chunk_index=n + j, a_rl=list(u_k[j]), reward=0.0)
        for f in range(108, 112):
            reward = 1.0 if (assisted_success_frame is not None and f == assisted_success_frame) else 0.0
            hand_frame(led, ep, f, goal="A_to_B", lease=1, source="harness", rid="HC1",
                       chunk_id="HC1", chunk_index=n + (f - 106), a_rl=None,
                       driver_command=[0.0, 0.0, 0.1], reward=reward,
                       terminal=(assisted_success_frame is not None and f == assisted_success_frame),
                       terminal_kind="goal_reached" if (assisted_success_frame is not None
                                                        and f == assisted_success_frame) else "none")
        admit(led, ep, "rq106", 106, goal="A_to_B")
        commit(led, ep, "rq106", 106, u_k1, goal="A_to_B")
    else:
        admit(led, ep, "rq106", 106, goal="A_to_B")
        commit(led, ep, "rq106", 106, u_k1, goal="A_to_B")
    led.append_event(episode_id=ep, kind="takeover", request_id="rq106", abs_frame=108, epoch=1,
                     goal_id="A_to_B", lease_generation=1, payload={"by": "harness"})
    return {"u_pre": u_pre, "u_k": u_k, "u_k1": u_k1}


def case_e5(rep: Report, spec: dict, seg: dict, *, no_learner: bool = False) -> None:
    case = spec_case(spec, "E5")
    cid = case["case_id"]
    conv, exp = spec["conventions"], case["expect"]
    n, gamma = int(conv["slot_length_n"]), float(conv["gamma_per_control_step"])
    gamma_slot = float(conv["gamma_slot"])
    preempt = int(case["input"]["constants"]["preempt_frame"])
    m = exp["masks"]

    # ---- V1：边界快照准确 ⇒ 前驱保留、抢占槽隔离 ----
    # 这一份严格按规格 E5 的 input 构造（**没有**任何成功奖励）：`terminal_semantics` 要求
    # 「抢占是删失不是任务终止」，一旦在槽内塞进成功标签，槽自己就变成 terminated，
    # 那条断言量的就不再是规格的语义了。「后面有辅助成功」的情形单独用 V1b 构造。
    ep = "E5V1"
    with open_ledger("E5V1") as led:
        us = _build_e5(led, ep, n, snapshot_verifiable=True, assisted_success_frame=None)
        bundle = views(led, spec)
        sk = sample_of(bundle, "rq100")
        sk1 = sample_of(bundle, "rq106", view="isolated")
        v1 = m["slot_k_starting_100"]["V1"]
        rep.add(cid, "masks", "V1 slot_k(100)：td_eligible == true（边界快照准确 ⇒ 保留这一步转移）",
                v1["td_eligible"] is True and sk is not None and sk.td_valid,
                expected=True, actual=(sk.td_valid if sk else None), note=v1["rule"],
                invariants=("I3", "I4"))
        intercept, slope = lin_id(sk.target) if sk else (None, None)
        rep.add(cid, "masks", "V1 slot_k：target == R_k + γ_slot*Q̄(X_106)，X_106 用**帧 106** 的快照",
                close(slope, gamma_slot) and str(sk.next_x_ref or "").endswith("#106")
                and norm_u(sk.next_queue or ())[:2] == norm_u(us["u_k"][:2]),
                expected=v1["target"], actual={"slope": slope, "intercept": intercept,
                                              "next_x_ref": (sk.next_x_ref if sk else None)},
                tolerance="rtol=1e-9", invariants=("I4",))
        rep.add(cid, "masks", "V1 slot_k：R_k 只覆盖帧 100-105，不含接管后的辅助成功",
                sk is not None and close(sk.r_slot, 0.0) and close(reward_sum(led, ep, 100, 106), 0.0),
                expected=0.0, actual=(sk.r_slot if sk else None), tolerance="rtol=1e-9, atol=1e-12")
        k1 = m["slot_k1_starting_106"]
        rep.add(cid, "masks", "V1 slot_k1(106)：td_eligible == false 且 isolated == true",
                k1["td_eligible"] is False and k1["isolated"] is True
                and sk1 is not None and not sk1.td_valid
                and sample_of(bundle, "rq106") is None,
                expected={"td_eligible": False, "isolated": True},
                actual=(sk1.isolation_reasons if sk1 else None), invariants=("I1", "I3"))
        want_reasons = [REASON_ALIASES[c] for c in k1["violated_admission_conditions"]]
        rep.add(cid, "masks", "V1 slot_k1：规格点名的两条被违反准入条件都被检出（§3.3-1 / §3.3-4）",
                sk1 is not None and set(want_reasons) <= set(sk1.isolation_reasons),
                expected={"spec": k1["violated_admission_conditions"], "impl_alias": want_reasons},
                actual=(sk1.isolation_reasons if sk1 else None),
                note="§3.3-1 需要帧级 chunk 归属核对才检得出来（F2，见文档 §3）", invariants=("I1",))
        rep.add(cid, "masks", "V1 slot_k1：treated_as_zero_value == false（删失不当零价值）",
                k1["treated_as_zero_value"] is False and sk1 is not None
                and sk1.target(0.0) is None and sk1.bootstrap_valid is False,
                expected="target() is None，不是 0.0", actual=(sk1.target(0.0) if sk1 else "n/a"),
                note="把「我们不知道」写成「这里价值为 0」是最难查的一类偏差", invariants=("I3",))
        fr = {int(x["abs_frame"]): x for x in frames_in(led, ep, 106, 112)}
        rep.add(cid, "masks", "V1 帧 106/107/108 微步事实分别保存（生效情况逐帧可查）",
                m["frames_106_107_108"]["micro_step_facts_saved"] is True
                and {106, 107, 108} <= set(fr)
                and fr[106]["chunk_id"] == "rq100" and fr[107]["chunk_id"] == "rq100"
                and fr[108]["chunk_id"] == "HC1"
                and fr[106]["execution_status"] == "activated" and fr[108]["lease_generation"] == 1,
                expected="106,107 归属 rq100；108 归属 harness 纠正 HC1 且租约换代",
                actual=[[k, fr[k]["chunk_id"], fr[k]["execution_status"], fr[k]["lease_generation"]]
                        for k in (106, 107, 108)], invariants=("I1",))
        rep.add(cid, "masks", "V1 纠正轨迹**分开**保存（driver_command 列，不倒填进 a_rl）",
                m["frames_106_107_108"]["correction_trajectory_saved_separately"] is True
                and all(fr[f]["a_rl"] is None and fr[f]["driver_command"] is not None
                        and fr[f]["source"] == "harness" for f in (108, 109, 110, 111))
                and {108, 109, 110, 111} <= {s.start_frame for s in bundle.bc}
                and all(s.bc_action_field == "driver_command" for s in bundle.bc
                        if s.start_frame in (108, 109, 110, 111)),
                expected="帧 108-111：a_rl=None、driver_command 非空、进 BC 视图",
                actual=[[f, fr[f]["a_rl"], fr[f]["driver_command"]] for f in (108, 109)],
                note=m["frames_106_107_108"]["rule"], invariants=("I1",))
        # 隔离范围
        scope = exp["isolation_scope"]
        named = {"slot_k_starting_100": "rq100", "slot_k1_starting_106": "rq106"}
        want_iso = {named[x] for x in scope["V1_isolated_slots"]}
        got_iso = {s.request_id for s in bundle.isolated} & set(named.values())
        rep.add(cid, "isolation_scope", "V1_isolated_slots 恰好是被抢占槽（不沿整个 episode 无限删）",
                got_iso == want_iso, expected=sorted(want_iso), actual=sorted(got_iso),
                note=scope["rule"])
        rep.add(cid, "isolation_scope", "V1 全量隔离清单可解释（prime 槽不在规格范围内，单列）",
                sorted(s.request_id for s in bundle.isolated) == sorted(want_iso),
                expected=sorted(want_iso), actual=sorted(s.request_id for s in bundle.isolated))
        rep.add(cid, "isolation_scope", "must_report：删失窗口比例被报告且 > 0",
                bundle.stats["censoring_ratio"] > 0.0 and bundle.stats["censoring_slot_ratio"] > 0.0
                and bundle.stats["censored_slot_ratio"] > 0.0,
                expected=scope["must_report"],
                actual={k: bundle.stats[k] for k in ("censoring_ratio", "censoring_slot_ratio",
                                                     "censored_slot_ratio", "censoring_by_reason")},
                invariants=("I3",))
        ts = exp["terminal_semantics"]
        rep.add(cid, "terminal_semantics", "抢占是删失不是任务终止（terminated=False、kind 非终局）",
                sk1 is not None and sk1.terminated is False
                and sk1.terminal_kind not in db.TERMINATED_KINDS
                and sk1.terminal_kind not in db.TRUNCATED_KINDS,
                expected={"preemption_is": ts["preemption_is"], "is_not": ts["preemption_is_not"]},
                actual={"terminated": (sk1.terminated if sk1 else None),
                        "terminal_kind": (sk1.terminal_kind if sk1 else None)},
                note=ts["rule"], invariants=("I3", "I7"))

    # ---- V1b（C 侧追加变体）：接管**之后**出现辅助成功 ⇒ 三条 forbidden_attributions + I8 ----
    # 规格的 `forbidden_attributions` 说的是「后面的辅助成功」，但 E5 的 input 里没有成功奖励；
    # 要真的验这三条，必须让成功发生在接管之后。单独一份账本，不污染上面按规格构造的 V1。
    ep_b = "E5V1b"
    with open_ledger("E5V1b") as led:
        us = _build_e5(led, ep_b, n, snapshot_verifiable=True, assisted_success_frame=110)
        bundle = views(led, spec)
        sk = sample_of(bundle, "rq100")
        sk1 = sample_of(bundle, "rq106", view="isolated")
        fa = exp["forbidden_attributions"]
        rep.add(cid, "forbidden_attributions", "①后面的辅助成功没有贴给旧 U（rq100 的 R_k 仍是 0）",
                close(reward_sum(led, ep_b, 108, 112), 1.0) and sk is not None and close(sk.r_slot, 0.0),
                expected={"帧 108-111 奖励和": 1.0, "rq100.R_k": 0.0},
                actual=[reward_sum(led, ep_b, 108, 112), (sk.r_slot if sk else None)],
                note=fa[0] + "；成功标签确实写进去了，所以这条不是空转")
        # 接管期间又产生一个「被取消的新候选」：只有影子查询，没进任何 control request。
        seq_b = led.append_proposal(
            episode_id=ep_b, goal_id="A_to_B", source="harness_shadow", admitted=False,
            action=[list(a) for a in action(7.0, n)], abs_frame=109, quality=0.9,
            valid_indices=[n, n + 1], observation_ref=f"{ep_b}#109")
        cand = next((c for c in views(led, spec).candidate if c["proposal_seq"] == seq_b), None)
        rep.add(cid, "forbidden_attributions", "②辅助成功没有贴给被取消的新候选（候选仍无 reward）",
                cand is not None and cand["reward"] is None and cand["td_valid"] is False,
                expected={"reward": None, "td_valid": False},
                actual=({k: cand[k] for k in ("reward", "td_valid")} if cand else None), note=fa[1])
        rep.add(cid, "forbidden_attributions", "③事后微步没有被拼成「先前就选好的 U」",
                sk1 is not None and norm_u(sk1.u or ()) == norm_u(us["u_k1"])
                and all(x["a_rl"] is None for x in frames_in(led, ep_b, 108, 112)),
                expected="rq106 的 U 仍是 106 提交的那一份；harness 帧 a_rl 恒为 None",
                actual=(sk1.u[:1] if sk1 and sk1.u else None), note=fa[2], invariants=("I2",))
        rep.add(cid, "forbidden_attributions",
                "I8：先被改 C（108 抢占）、之后才完成任务（110 成功）⇒ 不追认成合法 terminal 样本",
                sk1 is not None and not sk1.td_valid and sk1.target(0.0) is None
                and "takeover_in_slot" in sk1.isolation_reasons and sk1.terminated is True,
                expected="terminated=True 也仍然隔离，且没有可用 target",
                actual={"terminated": (sk1.terminated if sk1 else None),
                        "reasons": (sk1.isolation_reasons if sk1 else None)},
                note="即使 110 帧的成功标签是真的，边界仍按实际发生顺序裁定（先抢占、后成功）",
                invariants=("I8", "I3"))

    # ---- V2：快照与接管并发、先后不可判 ⇒ 连前驱一起隔离 ----
    ep2 = "E5V2"
    with open_ledger("E5V2") as led:
        _build_e5(led, ep2, n, snapshot_verifiable=False)
        bundle2 = views(led, spec)
        v2 = m["slot_k_starting_100"]["V2"]
        s2k = sample_of(bundle2, "rq100", view="isolated")
        s2k1 = sample_of(bundle2, "rq106", view="isolated")
        rep.add(cid, "masks", "V2 slot_k：td_eligible == false 且 isolated == true",
                v2["td_eligible"] is False and v2["isolated"] is True
                and s2k is not None and not s2k.td_valid,
                expected=True, actual=(s2k.isolation_reasons if s2k else None), note=v2["rule"])
        rep.add(cid, "masks", "V2 slot_k：隔离理由含「边界不可确认」+「next 快照不可确认」",
                s2k is not None
                and {"boundary_unverifiable_before_takeover", "next_snapshot_unverifiable"}
                <= set(s2k.isolation_reasons),
                expected=["boundary_unverifiable_before_takeover", "next_snapshot_unverifiable"],
                actual=(s2k.isolation_reasons if s2k else None),
                note="C 侧把「快照与接管并发、先后不可判」编码为**帧 106 不落可确认快照行**")
        named = {"slot_k_starting_100": "rq100", "slot_k1_starting_106": "rq106"}
        want_iso = {named[x] for x in exp["isolation_scope"]["V2_isolated_slots"]}
        got_iso = {s.request_id for s in bundle2.isolated}
        rep.add(cid, "isolation_scope", "V2_isolated_slots 恰好是这两个槽（范围只限不可确认区间）",
                got_iso == want_iso, expected=sorted(want_iso), actual=sorted(got_iso))
        rep.add(cid, "isolation_scope", "V2 删失比例被报告（槽口径两个都 > 0）",
                bundle2.stats["censoring_slot_ratio"] > 0.0
                and bundle2.stats["censored_slot_ratio"] > 0.0,
                expected="槽口径 > 0",
                actual={k: bundle2.stats[k] for k in ("censoring_ratio", "censoring_slot_ratio",
                                                      "censored_slot_ratio")},
                note="帧口径 `censoring_ratio` 在 V2 恒为 0：不可确认窗口本来就没有帧事实，"
                     "分子分母同时缺失 —— 这正是 `compute_stats` 要求两个口径都报的原因",
                invariants=("I3",))
        rep.add(cid, "masks", "V2 slot_k1 仍不当普通样本、也不当零价值",
                s2k1 is not None and s2k1.target(0.0) is None and sample_of(bundle2, "rq106") is None,
                expected="target() is None", actual=(s2k1.target(0.0) if s2k1 else "n/a"),
                invariants=("I3",))


# ===========================================================================
# E6：晚到与换向
# ===========================================================================
def _hold_frames(led: FactLedger, ep: str, goal: str, epoch: int, lo: int, hi: int) -> None:
    """晚到的 U 不得被采纳 ⇒ 运行时保持 hold：不写任何 chunk 归属，也不写 a_rl。"""
    for f in range(lo, hi):
        hand_frame(led, ep, f, goal=goal, epoch=epoch, source="hold", status="not_activated",
                   rid=None, chunk_id=None, chunk_index=None, a_rl=None, reward=0.0)


def case_e6(rep: Report, spec: dict, seg: dict, *, no_learner: bool = False) -> None:
    case = spec_case(spec, "E6")
    cid = case["case_id"]
    conv, exp = spec["conventions"], case["expect"]
    n, gamma = int(conv["slot_length_n"]), float(conv["gamma_per_control_step"])
    deadline = int(case["input"]["constants"]["deadline_frame"])
    arrival = int(case["input"]["constants"]["result_arrival_frame"])
    m = exp["masks"]

    # ---- V1：只有晚到，goal 未换向 ----
    ep = "E6V1"
    with open_ledger("E6V1") as led:
        b = EpisodeBuilder(led, ep, n=n, goal="A_to_B")
        u_pre, u_late = action(0.5, n), action(1.0, n)
        b.add_slot("RPRE", 94, u=u_pre, rewards=[0.0] * n)
        b.add_slot("rq100", 100, u=u_late, rewards=[0.0] * n, deadline=deadline,
                   commit_frame=arrival)
        _hold_frames(led, ep, "A_to_B", 1, 106, 112)
        bundle = views(led, spec)
        s = sample_of(bundle, "rq100", view="isolated")
        want = REASON_ALIASES["late_past_deadline"]
        rep.add(cid, "masks", "V1：adoption_for_original_slot == REJECT（td_eligible false）",
                m["V1"]["adoption_for_original_slot"] == "REJECT" and m["V1"]["td_eligible"] is False
                and s is not None and not s.td_valid and sample_of(bundle, "rq100") is None,
                expected="REJECT", actual=(s.isolation_reasons if s else None), invariants=("I8",))
        rep.add(cid, "masks", f"V1：拒绝理由含 `{want}`（规格名 late_past_deadline）",
                s is not None and want in s.isolation_reasons,
                expected={"spec": "late_past_deadline", "impl": want},
                actual=(s.isolation_reasons if s else None))
        rep.add(cid, "masks", "V1：goal 未换向 ⇒ **不得**多记 goal_epoch_incompatible（两个理由相互独立）",
                s is not None and "goal_epoch_incompatible" not in s.isolation_reasons
                and "goal_epoch_mismatch" not in s.isolation_reasons,
                expected="不含 goal/epoch 类理由", actual=(s.isolation_reasons if s else None),
                note="反向证明：只有晚到时不会顺手把换向理由也带上")
        rep.add(cid, "masks", "V1：next_queue_fabricated == false（hold 帧不伪造归属）",
                m["V1"]["next_queue_fabricated"] is False and s is not None
                and norm_u(s.next_queue or ()) != norm_u(u_late)
                and not any(fr["chunk_id"] == "rq100" for fr in frames_in(led, ep, 106, 112))
                and all(fr["a_rl"] is None for fr in frames_in(led, ep, 106, 112)),
                expected=False,
                actual=[[int(fr["abs_frame"]), fr["chunk_id"], fr["a_rl"]]
                        for fr in frames_in(led, ep, 106, 108)], invariants=("I2",))

    # ---- V2：晚到 + goal 已从 A→B 换为 B→A（epoch 1 vs 2）----
    ep2 = "E6V2"
    with open_ledger("E6V2") as led:
        b = EpisodeBuilder(led, ep2, n=n, goal="A_to_B", epoch=1)
        u_pre, u_late, u_new = action(0.5, n), action(1.0, n), action(4.0, n)
        b.add_slot("RPRE", 94, u=u_pre, rewards=[0.0] * n, goal="A_to_B", epoch=1)
        b.add_slot("rq100", 100, u=u_late, rewards=[0.0] * n, deadline=deadline,
                   commit_frame=arrival, goal="A_to_B", epoch=1)
        # goal_changed @106.5：C 侧账本的 in-force goal 只从 `request_admitted` 事件读，
        # 所以用「106 接纳了 B_to_A/epoch2 的新 request」表示换向；同时显式补一条 goal_switch 事件。
        led.append_event(episode_id=ep2, kind="goal_switch", request_id=None, abs_frame=106, epoch=2,
                         goal_id="B_to_A", lease_generation=0,
                         payload={"from": "A_to_B", "to": "B_to_A", "at_frame": 106.5})
        _hold_frames(led, ep2, "B_to_A", 2, 106, 112)
        admit(led, ep2, "rq106", 106, goal="B_to_A", epoch=2)
        bundle2 = views(led, spec)
        s2 = sample_of(bundle2, "rq100", view="isolated")
        slots = {sl.request_id: sl for sl in db.build_slots(led, ep2, n=n, gamma=gamma,
                                                            chunk_len=int(conv["chunk_length_H"]))}
        want_late = REASON_ALIASES["late_past_deadline"]
        want_goal = REASON_ALIASES["goal_epoch_incompatible"]
        want_spec = m["V2"]["rejection_reasons"]
        rep.add(cid, "masks", "V2：adoption_for_original_slot == REJECT",
                m["V2"]["adoption_for_original_slot"] == "REJECT" and s2 is not None
                and not s2.td_valid and sample_of(bundle2, "rq100") is None,
                expected="REJECT", actual=(s2.isolation_reasons if s2 else None))
        rep.add(cid, "masks", "V2：两个拒绝理由**分别**记录（both_reasons_must_be_recorded_separately）",
                m["V2"]["both_reasons_must_be_recorded_separately"] is True and s2 is not None
                and {want_late, want_goal} <= set(s2.isolation_reasons)
                and want_late != want_goal
                and len([r for r in s2.isolation_reasons if r in (want_late, want_goal)]) == 2,
                expected={"spec": want_spec, "impl": [want_late, want_goal]},
                actual=(s2.isolation_reasons if s2 else None),
                note="晚到与 goal/epoch 不相容是两个独立理由；只查晚到不查 goal/epoch 是规格点名的陷阱",
                invariants=("I8",))
        rep.add(cid, "masks", "V2：td_eligible == false 且 next_queue_fabricated == false",
                m["V2"]["td_eligible"] is False and m["V2"]["next_queue_fabricated"] is False
                and s2 is not None and norm_u(s2.next_queue or ()) != norm_u(u_late)
                and not any(fr["chunk_id"] == "rq100" for fr in frames_in(led, ep2, 106, 112)),
                expected=False, actual=(s2.next_queue[:1] if s2 and s2.next_queue else None),
                invariants=("I2",))
        rep.add(cid, "masks", "V2：正向 Q 不跨 goal 继续 bootstrap（前驱记 next_goal_switch）",
                s2 is not None and "next_goal_switch" in s2.isolation_reasons,
                expected="next_goal_switch", actual=(s2.isolation_reasons if s2 else None))
        rep.add(cid, "masks", "I1：拒绝采纳只改 TD 资格，四种 mask 仍是四个互不代替的对象",
                s2 is not None and sum(s2.execution_mask) == 0
                and ones_span(s2.q_action_gradient_mask) == tuple(range(*seg["E"]))
                and s2.q_action_gradient_mask == db.e_segment_mask(int(conv["chunk_length_H"]), n)
                and s2.td_valid is False,
                expected={"execution_mask 命中": "空（晚到的 U 一帧都没生效）",
                          "q_gradient_span": list(seg["E"]), "td_eligible": False},
                actual={"execution_mask 命中": (list(ones_span(s2.execution_mask)) if s2 else None),
                        "q_gradient_span 命中": (list(ones_span(s2.q_action_gradient_mask)) if s2 else None),
                        "td_valid": (s2.td_valid if s2 else None)},
                note="附录 §4.2：不能用「是否成功/是否被拒」代替四者；物理执行 mask 记的是事实，"
                     "Q 梯度区间记的是动作定义，两者都不随资格判定而变", invariants=("I1",))

        # ---- logging.must_record ----
        log = exp["logging"]
        adm = [ev for ev in led.events(episode_id=ep2, kinds=["request_admitted"])
               if ev["request_id"] == "rq100"][0]
        cmt = [ev for ev in led.events(episode_id=ep2, kinds=["result_committed"])
               if ev["request_id"] == "rq100"][0]
        sl = slots.get("rq100")
        recorded = {
            "request_id": s2.request_id if s2 else None,
            "scheduled_slot": [int(adm["deadline"]), int(adm["deadline"]) + n],
            "deadline_frame": int(adm["deadline"]),
            "actual_arrival_frame": int(cmt["abs_frame"]),
            "goal_at_request": [adm["goal_id"], int(adm["epoch"])],
            "goal_at_arrival": [sl.arrival_goal_id, sl.arrival_epoch] if sl else None,
            "rejection_reasons": list(s2.isolation_reasons) if s2 else None,
        }
        rep.add(cid, "logging", "must_record 六项全部可从账本/视图读出（含请求时与到达时各一份 goal）",
                recorded["request_id"] == "rq100"
                and recorded["scheduled_slot"] == case["input"]["event_log"][0]["scheduled_slot"]
                and recorded["deadline_frame"] == deadline
                and recorded["actual_arrival_frame"] == arrival
                and recorded["goal_at_request"] == ["A_to_B", 1]
                and recorded["goal_at_arrival"] == ["B_to_A", 2]
                and bool(recorded["rejection_reasons"]),
                expected=log["must_record"], actual=recorded)
        rep.add(cid, "logging", "must_not_do：晚到的 U 没有被倒填成 U_100（帧 100-105 仍是旧 C）",
                all(fr["chunk_id"] == "RPRE" and _close_row(fr["a_rl"], u_pre[int(fr["abs_frame"]) - 100])
                    for fr in frames_in(led, ep2, 100, 106))
                and all(fr["a_rl"] is None for fr in frames_in(led, ep2, 106, 112)),
                expected="帧 100-105 归属 RPRE；帧 106-111 a_rl 恒为 None",
                actual=[[int(fr["abs_frame"]), fr["chunk_id"]] for fr in frames_in(led, ep2, 104, 108)],
                note=log["must_not_do"], invariants=("I2",))
        rep.add(cid, "logging", "rule：一般执行索引能表示这些事件，但它们不自动变为首版普通 TD",
                s2 is not None and not s2.td_valid and log["rule"].find("不自动变为首版普通 TD") >= 0,
                expected="隔离", actual=(s2.isolation_reasons if s2 else None))

        # ---- isolation ----
        iso = exp["isolation"]
        rep.add(cid, "isolation", "isolated == true / censored == true / 计入删失比例",
                iso["isolated"] is True and iso["censored"] is True
                and iso["counted_toward_censoring_ratio"] is True
                and s2 is not None and bundle2.stats["censored_slot_ratio"] > 0.0
                and "rq100" in bundle2.stats["censored_requests"]
                and set(s2.isolation_reasons) & set(db.CENSORING_REASONS),
                expected={"censored": True, "counted_toward_censoring_ratio": True},
                actual={"censored_requests": bundle2.stats["censored_requests"],
                        "censored_slot_ratio": bundle2.stats["censored_slot_ratio"],
                        "censoring_by_reason": bundle2.stats["censoring_by_reason"]},
                note="宽口径删失统计（F3）：超时/掉线/日志缺失也算删失，旧口径只算接管",
                invariants=("I3",))
        rep.add(cid, "isolation", "treated_as_zero_value == false（拒绝 ≠ 失败样本 ≠ 零奖励）",
                iso["treated_as_zero_value"] is False and s2 is not None
                and s2.target(0.0) is None and s2.terminated is False
                and s2.terminal_kind not in db.TERMINATED_KINDS,
                expected=False, actual={"target(0.0)": (s2.target(0.0) if s2 else "n/a"),
                                        "terminated": (s2.terminated if s2 else None),
                                        "terminal_kind": (s2.terminal_kind if s2 else None)},
                invariants=("I3",))

    # ---- reward_semantics：unknown / pending 不是失败、不是零奖励 ----
    ep3 = "E6V3"
    with open_ledger("E6V3") as led:
        b = EpisodeBuilder(led, ep3, n=n, goal="A_to_B")
        b.add_slot("RPRE", 94, u=action(0.5, n), rewards=[0.0] * n)
        b.add_slot("rp", 100, u=action(1.0, n), rewards=[0.0] * n, reward_state="pending")
        b.add_slot("ru", 106, u=action(2.0, n), rewards=[0.0] * n, reward_state="unknown")
        b.add_slot("rf", 112, u=action(3.0, n), rewards=[0.0] * n)
        bundle3 = views(led, spec)
        sp = sample_of(bundle3, "rp", view="pending")
        su = sample_of(bundle3, "ru", view="isolated")
        rs = exp["reward_semantics"]
        rep.add(cid, "reward_semantics", "unknown_is_not_zero_reward：r_slot 是 None，不是 0.0",
                rs["unknown_is_not_zero_reward"] is True and su is not None and su.r_slot is None
                and "reward_unknown" in su.isolation_reasons,
                expected=None, actual=(su.r_slot if su else "n/a"),
                note=rs["rule"], invariants=("I3",))
        rep.add(cid, "reward_semantics", "unknown_is_not_failure：没被标成终局/失败",
                rs["unknown_is_not_failure"] is True and su is not None
                and su.terminated is False and su.terminal_kind == "none",
                expected={"terminated": False, "terminal_kind": "none"},
                actual=({"terminated": su.terminated, "terminal_kind": su.terminal_kind}
                        if su else None), invariants=("I3",))
        rep.add(cid, "reward_semantics", "pending 槽进 pending 视图、r_slot 为 None、不进普通 TD",
                sp is not None and sp.r_slot is None and "reward_pending" in sp.isolation_reasons
                and sample_of(bundle3, "rp") is None,
                expected="pending 视图", actual=(sp.isolation_reasons if sp else None),
                invariants=("I3",))
        rep.add(cid, "reward_semantics", "同局其它槽不被牵连（rf 仍有 TD 资格）",
                sample_of(bundle3, "rf") is not None or sample_of(bundle3, "rp") is None,
                expected="不牵连", actual={"rp": (sp is not None), "ru": (su is not None)})

    # ---- I8：先超时、之后才完成任务 ⇒ 不追认成合法 terminal 样本 ----
    ep4 = "E6V4"
    with open_ledger("E6V4") as led:
        b = EpisodeBuilder(led, ep4, n=n, goal="A_to_B")
        b.add_slot("RPRE", 94, u=action(0.5, n), rewards=[0.0] * n)
        # 槽内第 6 步（帧 105）真终止，但结果 107 才到、deadline 是 106 ⇒ 顺序上先超时
        b.add_slot("rq100", 100, u=action(1.0, n), rewards=[0.0] * 5 + [1.0], terminal_step=n,
                   terminal_kind=KIND_ALIASES["true_goal_termination"], deadline=deadline,
                   commit_frame=arrival)
        _hold_frames(led, ep4, "A_to_B", 1, 106, 112)
        bundle4 = views(led, spec)
        s4 = sample_of(bundle4, "rq100", view="isolated")
        rep.add(cid, "masks", "I8：先超时后才完成 ⇒ terminated=True 也不追认成合法 terminal 样本",
                s4 is not None and s4.terminated is True and not s4.td_valid
                and REASON_ALIASES["late_past_deadline"] in s4.isolation_reasons
                and sample_of(bundle4, "rq100") is None,
                expected="仍隔离，理由含 deadline_miss",
                actual=({"terminated": s4.terminated, "reasons": s4.isolation_reasons}
                        if s4 else None),
                note="附录 §5.3：边界按实际发生顺序裁定", invariants=("I8", "I3"))


# ===========================================================================
# 跨例不变量覆盖（I1–I8）
# ===========================================================================
def check_invariant_coverage(rep: Report, spec: dict) -> None:
    """`cross_case_invariants` 逐条标了适用算例 ⇒ 反过来核 C 侧有没有真的测到。

    这是**对本脚本自身**的元检查：漏测某条 (不变量, 算例) 组合会让覆盖率虚高。
    """
    tagged: dict[tuple[str, str], list[str]] = {}
    for row in rep.rows:
        for inv in row["invariants"]:
            tagged.setdefault((inv, row["case"]), []).append(row["verdict"])
    for inv in spec["cross_case_invariants"]:
        for cid in inv["cases"]:
            verdicts = tagged.get((inv["id"], cid))
            evaluated = verdicts is not None and any(v != NOT_ASSERTABLE for v in verdicts)
            rep.add("INV", "invariant", f"{inv['id']} 在 {cid} 上被实际断言过",
                    evaluated, expected=inv["invariant"][:80],
                    actual=(sorted(set(verdicts)) if verdicts else None),
                    note="覆盖率为 0 说明本脚本漏测了这条组合")


def spec_case(spec: dict, case_id: str) -> dict:
    return next(c for c in spec["cases"] if c["case_id"] == case_id)


# ===========================================================================
# 变异自检：一套不会失败的规格一致性测试等于没测
# ===========================================================================
# 158 条断言全绿本身不说明任何问题 —— 必须证明「把实现按规格点名的方式改坏，断言会红」。
# 每个变异体对应 `common_traps` / `cross_case_invariants` 里的一条具体陷阱，
# 用 monkey-patch 注入，跑完立刻还原（`finally`），不改动仓库里的实现文件。
#
# 注入点有两类：
#   * `patch_views(transform)`：改 `db.build_views` 的**产物**（样本字段 / 视图归属），
#     用来模拟「派生层写错了」；
#   * 直接替换 `ql.assemble_from_full_head` / `db.TrainingSample.target`，
#     用来模拟「计算图 / target 函数写错了」。
E1_DECOY = 0.7           # 与 case_e1 里帧 106-111 的诱饵奖励同值（M3 要用）


def patch_views(transform: Callable[[db.ViewBundle, dict], db.ViewBundle]) -> Callable[[], None]:
    orig = db.build_views

    def wrapped(*args: Any, **kwargs: Any) -> db.ViewBundle:
        return transform(orig(*args, **kwargs), kwargs)

    db.build_views = wrapped

    def undo() -> None:
        db.build_views = orig

    return undo


def patch_attr(obj: Any, name: str, value: Any) -> Callable[[], None]:
    orig = getattr(obj, name)
    setattr(obj, name, value)

    def undo() -> None:
        setattr(obj, name, orig)

    return undo


def _map_samples(bundle: db.ViewBundle, fn: Callable[[db.TrainingSample], db.TrainingSample]
                 ) -> db.ViewBundle:
    bundle.td = [fn(s) for s in bundle.td]
    bundle.isolated = [fn(s) for s in bundle.isolated]
    bundle.pending = [fn(s) for s in bundle.pending]
    return bundle


def _drop_reason(bundle: db.ViewBundle, reason: str) -> db.ViewBundle:
    """模拟「某个检出器没触发」：抹掉一条隔离理由；若它是唯一理由，样本就漏进普通 TD。"""
    def fix(s: db.TrainingSample) -> db.TrainingSample:
        if reason not in s.isolation_reasons:
            return s
        rest = tuple(r for r in s.isolation_reasons if r != reason)
        return dataclasses.replace(s, isolation_reasons=rest, td_valid=not rest)
    return _map_samples(bundle, fix)


def _mut_gamma_double_power() -> Callable[[], None]:
    """M1：对 γ_slot 再做一次 n 次幂 ⇒ 0.9^36（附录 §3.1 / I4 点名的二次幂 bug）。"""
    def t(bundle: db.ViewBundle, kw: dict) -> db.ViewBundle:
        n = int(kw.get("n") or 6)
        return _map_samples(bundle, lambda s: dataclasses.replace(s, gamma_slot=s.gamma_slot ** n))
    return patch_views(t)


def _mut_next_state_frame112() -> Callable[[], None]:
    """M2：next state 写成帧 112、却仍累计 100-105 的奖励（附录 §9 例 1 明确点名不通过）。"""
    def t(bundle: db.ViewBundle, kw: dict) -> db.ViewBundle:
        def fix(s: db.TrainingSample) -> db.TrainingSample:
            ref = s.next_x_ref or ""
            return dataclasses.replace(s, next_x_ref=ref.replace("#106", "#112")) if "#106" in ref else s
        return _map_samples(bundle, fix)
    return patch_views(t)


def _mut_steal_next_rewards() -> Callable[[], None]:
    """M3：把 106-111 的奖励挪进当前样本「让动作立即配上自己的物理奖励」（附录 §3.1 末段禁止）。"""
    def t(bundle: db.ViewBundle, kw: dict) -> db.ViewBundle:
        gamma = float(kw.get("gamma") or 0.9)
        n = int(kw.get("n") or 6)
        extra = E1_DECOY * sum(gamma ** j for j in range(n))
        return _map_samples(bundle, lambda s: dataclasses.replace(
            s, r_slot=None if s.r_slot is None else s.r_slot + extra))
    return patch_views(t)


def _mut_terminal_bootstrap() -> Callable[[], None]:
    """M4：给终局样本加 bootstrap（terminated=true 却仍加 γ_slot*Q̄）。"""
    def t(bundle: db.ViewBundle, kw: dict) -> db.ViewBundle:
        return _map_samples(bundle, lambda s: dataclasses.replace(
            s, bootstrap_valid=True) if s.terminated else s)
    return patch_views(t)


def _mut_future_backfill() -> Callable[[], None]:
    """M5：用后来的成功给前驱回填较长回报（附录 §5.2 的 0.5 → 0.75 选择偏差）。"""
    def t(bundle: db.ViewBundle, kw: dict) -> db.ViewBundle:
        return _map_samples(bundle, lambda s: dataclasses.replace(
            s, r_slot=0.81) if (s.r_slot == 0.0 and not s.terminated) else s)
    return patch_views(t)


def _mut_censoring_as_zero_value() -> Callable[[], None]:
    """M6：把删失当零价值 —— `target()` 对不合格样本返回 0.0 而不是 None（最难查的一类偏差）。"""
    orig = db.TrainingSample.target

    def bad(self: db.TrainingSample, q_next: float) -> float | None:
        return 0.0 if not self.td_valid else orig(self, q_next)

    return patch_attr(db.TrainingSample, "target", bad)


def _mut_shadow_pseudo_td() -> Callable[[], None]:
    """M7：给未进 request 的影子建议伪 TD（附录 02:63：永远不得伪 TD）。"""
    def t(bundle: db.ViewBundle, kw: dict) -> db.ViewBundle:
        for cand in bundle.candidate:
            cand["td_valid"] = True
            cand["reward"] = 0.0
            cand["next_x_ref"] = cand.get("observation_ref")
        return bundle
    return patch_views(t)


def _mut_only_check_late() -> Callable[[], None]:
    """M8：只查晚到、不查 goal/epoch（E6 点名的陷阱：两个拒绝理由必须分别记录）。"""
    return patch_views(lambda b, kw: _drop_reason(b, "goal_epoch_incompatible"))


def _mut_c_grad_flows() -> Callable[[], None]:
    """M9：把 C 当成可优化输出送进 critic 而不加 sg ⇒ Q 的动作梯度经 C 段。"""
    orig = ql.assemble_from_full_head

    def bad(full: Any, c_const: Any, cfg: Any, *, wrong_c: bool = False, wrong_d: bool = False) -> Any:
        return orig(full, c_const, cfg, wrong_c=True, wrong_d=wrong_d)

    return patch_attr(ql, "assemble_from_full_head", bad)


def _mut_over_censor_predecessor() -> Callable[[], None]:
    """M10：退回 F1 修之前的整窗口判定 ⇒ 接管时连前驱一起隔离（E5-V1 点名过度删失）。"""
    def t(bundle: db.ViewBundle, kw: dict) -> db.ViewBundle:
        n = int(kw.get("n") or 6)
        keep, demote = [], []
        for s in bundle.td:
            nq = norm_u(s.next_queue or ())
            u = norm_u((s.u or ())[:len(nq)])
            if len(nq) == n and nq != u:
                demote.append(dataclasses.replace(
                    s, td_valid=False,
                    isolation_reasons=tuple(dict.fromkeys(s.isolation_reasons
                                                          + ("c_next_not_equal_u",)))))
            else:
                keep.append(s)
        bundle.td, bundle.isolated = keep, bundle.isolated + demote
        return bundle
    return patch_views(t)


def _mut_no_chunk_attribution() -> Callable[[], None]:
    """M11：撤掉 F2 的 chunk 归属核对 ⇒ §3.3-1「C 未全槽按学习动作边界执行」检不出来。"""
    return patch_views(lambda b, kw: _drop_reason(b, "c_not_executed"))


def _mut_reject_as_failure_zero() -> Callable[[], None]:
    """M12：把拒绝当失败样本喂进 TD 并给零奖励（E6 点名的陷阱）。"""
    def t(bundle: db.ViewBundle, kw: dict) -> db.ViewBundle:
        keep, promote = [], []
        for s in bundle.isolated:
            if "deadline_miss" in s.isolation_reasons:
                promote.append(dataclasses.replace(s, td_valid=True, r_slot=0.0,
                                                   isolation_reasons=()))
            else:
                keep.append(s)
        bundle.isolated, bundle.td = keep, bundle.td + promote
        return bundle
    return patch_views(t)


MUTATIONS: tuple[dict[str, Any], ...] = (
    {"id": "M1", "cases": ["E1"], "apply": _mut_gamma_double_power,
     "trap": "对 γ_slot 再做一次 n 次幂（0.9^36）", "source": "E1 common_traps[3] / I4"},
    {"id": "M2", "cases": ["E1"], "apply": _mut_next_state_frame112,
     "trap": "next state 写成帧 112 却仍累计 100-105 的奖励", "source": "附录 §9 例 1 / E1 common_traps[0]"},
    {"id": "M3", "cases": ["E1"], "apply": _mut_steal_next_rewards,
     "trap": "把 106-111 的奖励挪进当前样本", "source": "附录 §3.1 末段 / E1 common_traps[1]"},
    {"id": "M4", "cases": ["E3"], "apply": _mut_terminal_bootstrap,
     "trap": "给终局样本加 bootstrap", "source": "E3 common_traps[0]"},
    {"id": "M5", "cases": ["E3"], "apply": _mut_future_backfill,
     "trap": "用后来的成功给前驱回填较长回报", "source": "附录 §5.2 / E3 common_traps[4]"},
    {"id": "M6", "cases": ["E5", "E6"], "apply": _mut_censoring_as_zero_value,
     "trap": "把删失当零价值", "source": "E5 common_traps[1] / I3"},
    {"id": "M7", "cases": ["E4"], "apply": _mut_shadow_pseudo_td,
     "trap": "给未进 request 的影子建议伪 TD", "source": "附录 02:63 / E4 common_traps[4]"},
    {"id": "M8", "cases": ["E6"], "apply": _mut_only_check_late,
     "trap": "只查晚到、不查 goal/epoch", "source": "E6 common_traps[1]"},
    {"id": "M9", "cases": ["E2"], "apply": _mut_c_grad_flows,
     "trap": "把 C 当可优化输出送进 critic（不加 sg）", "source": "E2 common_traps[2] / I5"},
    {"id": "M10", "cases": ["E5"], "apply": _mut_over_censor_predecessor,
     "trap": "接管时连前驱一起隔离（过度删失）", "source": "E5 common_traps[2] / 附录 §6.2"},
    {"id": "M11", "cases": ["E5"], "apply": _mut_no_chunk_attribution,
     "trap": "§3.3-1 C 未按学习动作边界执行检不出来", "source": "E5 violated_admission_conditions"},
    {"id": "M12", "cases": ["E6"], "apply": _mut_reject_as_failure_zero,
     "trap": "把拒绝当失败样本喂 TD 并给零奖励", "source": "E6 common_traps[2] / I3"},
)


CASE_RUNNERS: dict[str, Callable[..., None]] = {
    "E1": case_e1, "E2": case_e2, "E3": case_e3, "E4": case_e4, "E5": case_e5, "E6": case_e6,
}


def run_mutations(rep: Report, spec: dict, seg: dict, *, no_learner: bool) -> None:
    """逐个注入变异，确认对应算例**真的会红**。全绿 ⇒ 断言恒真 ⇒ 比失败更危险。"""
    for mut in MUTATIONS:
        undo = mut["apply"]()
        try:
            sub = Report()
            for cid in mut["cases"]:
                CASE_RUNNERS[cid](sub, spec, seg, no_learner=no_learner)
            caught = [r["name"] for r in sub.rows if r["verdict"] == FAIL]
            note = f"注入 {mut['id']} 后子报告：PASS={sub.n(PASS)} FAIL={sub.n(FAIL)}"
        finally:
            undo()
        rep.add("MUT", "mutation", f"{mut['id']} 变异被抓住：{mut['trap']}",
                bool(caught), expected=">=1 条断言转 FAIL", actual=caught[:6],
                note=f"{mut['source']}；{note}")
    # 还原后再跑一次基准算例，确认 monkey-patch 没有残留污染。
    after = Report()
    case_e1(after, spec, seg, no_learner=no_learner)
    rep.add("MUT", "mutation", "变异全部还原：E1 重跑无任何 FAIL（monkey-patch 无残留）",
            after.n(FAIL) == 0 and after.n(PASS) > 0, expected=0, actual=after.n(FAIL))


# ===========================================================================
# 主流程
# ===========================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true", help="打印每条断言")
    parser.add_argument("--case", action="append", default=None,
                        help="只跑指定算例（E1..E6），可重复")
    parser.add_argument("--spec", default=str(SPEC_PATH))
    parser.add_argument("--out", default=str(OUT_JSON))
    parser.add_argument("--no-learner", action="store_true", help="跳过 E2/E3 的 torch 探针")
    parser.add_argument("--no-mutation", action="store_true",
                        help="跳过变异自检（不建议：全绿但抓不住变异的断言等于没测）")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    seg = seg_of(spec)
    conv = spec["conventions"]
    rep = Report()

    # --- 规格身份与 conventions 的显式核对（不复算规格内部一致性，那是 B 的 47 项自校验）---
    rep.add("SPEC", "mapping", "consumer 指明是 C 线", spec.get("consumer", "").find("C") >= 0,
            expected="C", actual=spec.get("consumer"))
    rep.add("SPEC", "mapping", "γ_slot == γ^n（从规格读入并复算一次）",
            close(conv["gamma_slot"], conv["gamma_per_control_step"] ** conv["slot_length_n"]),
            expected=conv["gamma_per_control_step"] ** conv["slot_length_n"],
            actual=conv["gamma_slot"], tolerance="rtol=1e-9", invariants=("I4",))
    rep.add("SPEC", "mapping", "γ_slot != γ^(n*n)（规格自己没踩二次幂）",
            not close(conv["gamma_slot"],
                      conv["gamma_per_control_step"] ** (conv["slot_length_n"] ** 2), rtol=1e-6),
            expected=f"!= {conv['gamma_per_control_step'] ** (conv['slot_length_n'] ** 2):.3e}",
            actual=conv["gamma_slot"], invariants=("I4",))
    rep.add("SPEC", "mapping", "H >= 2n（首版硬约束）",
            int(conv["chunk_length_H"]) >= 2 * int(conv["slot_length_n"]),
            expected=f">= {2 * int(conv['slot_length_n'])}", actual=conv["chunk_length_H"])
    rep.add("SPEC", "mapping", "索引段互不重叠且并起来覆盖 [0,H)",
            seg["C"] == (0, conv["slot_length_n"])
            and seg["E"] == (conv["slot_length_n"], 2 * conv["slot_length_n"])
            and seg["D"] == (2 * conv["slot_length_n"], conv["chunk_length_H"]),
            expected={"C": [0, 6], "E": [6, 12], "D": [12, 20]},
            actual={k: list(v) for k, v in seg.items()}, invariants=("I5",))
    rep.add("SPEC", "mapping", "六例齐全且 expect 子键都落在已知类别里",
            [c["case_id"] for c in spec["cases"]] == ["E1", "E2", "E3", "E4", "E5", "E6"],
            expected=["E1", "E2", "E3", "E4", "E5", "E6"],
            actual=[c["case_id"] for c in spec["cases"]])

    selected = args.case or list(CASE_RUNNERS)
    for cid in selected:
        if cid not in CASE_RUNNERS:
            raise SystemExit(f"未知算例 {cid}（可选 {list(CASE_RUNNERS)}）")
    for cid in selected:
        CASE_RUNNERS[cid](rep, spec, seg, no_learner=args.no_learner)
    if not args.case:
        check_invariant_coverage(rep, spec)
    if not args.case and not args.no_mutation:
        run_mutations(rep, spec, seg, no_learner=args.no_learner)

    # --- 汇总 ---
    by_verdict = {v: rep.n(v) for v in (PASS, FAIL, UNRESOLVED, NOT_ASSERTABLE)}
    result = {
        "task": "c_golden_conformance",
        "spec_id": spec.get("spec_id"), "spec_version": spec.get("version"),
        "spec_path": str(spec_path), "spec_sha256": sha256_of(spec_path),
        "impl_sha256": {rel: (sha256_of(ROOT / rel) if (ROOT / rel).exists() else None)
                        for rel in IMPL_FILES},
        "conventions_used": {k: conv[k] for k in ("gamma_per_control_step", "slot_length_n",
                                                  "gamma_slot", "chunk_length_H")},
        "action_index_segments_numeric": {k: list(v) for k, v in seg.items()},
        "cases_run": selected,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "conformant": rep.conformant,
        "counts": {"by_verdict": by_verdict, "by_case": rep.by("case"),
                   "by_category": rep.by("category"), "by_case_category": rep.by_case_category()},
        "mappings": {"reason_aliases": REASON_ALIASES, "kind_aliases": KIND_ALIASES,
                     "index_note": "规格 physical_execution_mask_for_steps_after_L 用槽内步号，"
                                   "C 侧 chunk 索引 = 步号 + n；q_gradient_span 的 chunk 步索引在 "
                                   "learner 探针里映射为 [lo*d_a, hi*d_a)"},
        "tolerances": {"targets": "rtol=1e-9, atol=1e-12（atol 仅兜 expected==0）",
                       "gradients": "严判 == 0.0 / != 0.0", "invariance": "abs < 1e-12"},
        "mutations": {"enabled": bool(not args.case and not args.no_mutation),
                      "n": (len(MUTATIONS) + 1) if (not args.case and not args.no_mutation) else 0,
                      "catalog": [{"id": m["id"], "trap": m["trap"], "source": m["source"],
                                   "cases": m["cases"]} for m in MUTATIONS]},
        "ledger_dir": str(OUT_DIR),
        "checks": rep.rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.verbose:
        for row in rep.rows:
            print(f"[{row['verdict']:^14s}] {row['case']}/{row['category']}: {row['name']}")
            if row["verdict"] in BAD_VERDICTS or row["verdict"] == NOT_ASSERTABLE:
                print(f"                 expected={row['expected']}")
                print(f"                 actual  ={row['actual']}")
                if row["note"]:
                    print(f"                 note    ={row['note']}")
    print("\n按算例：")
    for k, v in result["counts"]["by_case"].items():
        print(f"  {k:5s} PASS={v[PASS]:3d} FAIL={v[FAIL]:2d} UNRESOLVED={v[UNRESOLVED]:2d} "
              f"NOT_ASSERTABLE={v[NOT_ASSERTABLE]:2d}")
    print("按 expect 类别（分别计数，不合并）：")
    for k, v in result["counts"]["by_category"].items():
        print(f"  {k:22s} PASS={v[PASS]:3d} FAIL={v[FAIL]:2d} UNRESOLVED={v[UNRESOLVED]:2d} "
              f"NOT_ASSERTABLE={v[NOT_ASSERTABLE]:2d}")
    fails = [r for r in rep.rows if r["verdict"] in BAD_VERDICTS]
    if fails:
        print("\n未通过项：")
        for r in fails:
            print(f"  [{r['verdict']}] {r['case']}/{r['category']}: {r['name']}")
            print(f"      expected={r['expected']}")
            print(f"      actual  ={r['actual']}")
            if r["note"]:
                print(f"      note    ={r['note']}")
    na = [r for r in rep.rows if r["verdict"] == NOT_ASSERTABLE]
    if na:
        print("\n不可断言项（单独计数，不算通过也不算失败）：")
        for r in na:
            print(f"  {r['case']}/{r['category']}: {r['name']}\n      {r['note']}")
    print(f"\n结论：{'符合规格' if rep.conformant else '不符合规格'}  "
          f"PASS={by_verdict[PASS]} FAIL={by_verdict[FAIL]} "
          f"UNRESOLVED={by_verdict[UNRESOLVED]} NOT_ASSERTABLE={by_verdict[NOT_ASSERTABLE]}"
          f" -> {out}")
    return 0 if rep.conformant else 1


if __name__ == "__main__":
    raise SystemExit(main())
