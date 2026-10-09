#!/usr/bin/env python
"""最小抓取链路 · 档 5 监督器（检测器 + 一次性接管 + 纠正片段落盘）。

要回答的唯一问题（STAGE_PLAN 档 5 第一节）：
    一个**确定性、实时可跑、不含 LLM** 的监督器，能不能把策略的残余失败救回来，
    并且顺手把「接管片段」落成档 6 的纠正数据？

第一轮**只有**这些，其余一律不引入（用户 2026-10-02 的边界）：
    单臂、反向、同步执行、K=10、一次接管、无 LLM、无 RL、无异步 chunk 调度、无真机接口。

三块：
  1. `GraspDetector` —— O(1)/步的本体感觉检测器。阈值全部来自 `mg_calib_detector`（同一份常数，
     不在这里重新拍脑袋），标定出处见 `runs/_diag/harness_calib.md`。
  2. `TakeoverHarness` —— 触发后把控制权交给脚本专家（`ScriptedExpert.resume`），跑到本局结束。
     只接管**一次**：来回切换会让「谁造成的失败」不可归因，档 6 的片段也会被切碎。
  3. 纠正片段缓冲 —— 从接管那一刻到本局结束的 (state, action, 相位)，格式与
     `data/*_raw.npz` 一致（state/action/episode_lengths/seeds），档 6 可以直接沿用同一条转换路径。

时序约定（与离线标定**逐下标对齐**，这是 G0 等价性护栏成立的前提）：
    mg_eval.py 落盘的 state 第 i 行 = 执行第 i 个动作**之前**的观测。检测器在运行时也看这一行，
    即「先检测、再选动作」：在第 idx 行凑满 N_EMPTY 步空合就触发，触发步号记 idx+1（1-based），
    专家从**同一个 idx** 开始出动作（不浪费一步）。
    成功闩锁：info["success_relaxed"] 为真之后本局不再检测（离线标定的 stop 就是它，语义一致）。

用法：见 code/mg_eval_harness.py（评测入口）；本文件只做逻辑，`--selftest` 是纯 CPU 的假 env 桩。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MG_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from mg_calib_detector import (  # noqa: E402
    HOLD_HI, HOLD_LO, N_EMPTY, N_HOLD, W_EMPTY,
)
from mg_env import STATE_KEY  # noqa: E402

WIDTH_IDX = 7          # state[:,7] = gripper_width（mg_env.STATE_NAMES 的最后一维）
PHASES = ("approach", "descend", "grasp", "lift", "settle", "carry",
          "place_descend", "release", "retreat", "done")


class GraspDetector:
    """T1（抓空）/ T3（滑脱）检测器。每步只吃一个 float，开销 ≈0。

    触发规则（与 mg_calib_detector.scan 逐字对应，那边是离线版、这边是在线版）：
        连续 n_empty 步 width ≤ w_empty  ⇒ 触发；
        触发前是否出现过「连续 ≥n_hold 步落在 [hold_lo, hold_hi]」决定标签 T1 / T3。
    T2（送不到）第一轮**不做**：B 类的机理实测是「夹持中断」，T3 已经覆盖（档 2e 臂 B 13/13），
    而 T2 只能在很晚才触发（剩余步数不够专家重做），出处见 runs/_diag/harness_calib.md 第五节。
    """

    def __init__(self, w_empty: float = W_EMPTY, n_empty: int = N_EMPTY,
                 hold_lo: float = HOLD_LO, hold_hi: float = HOLD_HI, n_hold: int = N_HOLD) -> None:
        self.w_empty = float(w_empty)
        self.n_empty = int(n_empty)
        self.hold_lo, self.hold_hi = float(hold_lo), float(hold_hi)
        self.n_hold = int(n_hold)
        self.reset()

    def reset(self) -> None:
        self.hold_run = 0
        self.empty_run = 0
        self.held = False       # 曾经稳定夹持过（决定标签）
        self.done = False       # 成功闩锁 / 已触发 ⇒ 本局不再检测

    def update(self, width: float) -> str | None:
        """喂一步的夹爪宽度，返回 "T1"/"T3" 或 None。触发后自动闭嘴（一局只报一次）。"""
        if self.done:
            return None
        width = float(width)
        self.hold_run = self.hold_run + 1 if self.hold_lo <= width <= self.hold_hi else 0
        if self.hold_run >= self.n_hold:
            self.held = True
        self.empty_run = self.empty_run + 1 if width <= self.w_empty else 0
        if self.empty_run >= self.n_empty:
            self.done = True
            return "T3" if self.held else "T1"
        return None

    def latch_success(self) -> None:
        """本局已判成功（放宽口径）⇒ 停止检测。接管一个已经成功的局只会帮倒忙。"""
        self.done = True


class SegmentBuffer:
    """接管片段缓冲：档 6 纠正数据的原料，格式对齐 data/*_raw.npz。"""

    def __init__(self) -> None:
        self.episodes: list[dict] = []
        self._cur: dict | None = None

    def open(self, seed: int, trigger: str, takeover_step: int, remain: int) -> None:
        self._cur = {"seed": int(seed), "trigger": trigger, "takeover_step": int(takeover_step),
                     "remain": int(remain), "state": [], "action": [], "phase": [], "expert_phase": []}

    def mark_handback(self, step_1based: int, n_restages: int, expert_log: list[str]) -> None:
        """档 5.1：专家认输（`unrecoverable`）⇒ 记下交还点，片段**继续开着**（不 close）。

        为什么不在这里 close()：片段的 success / success_relaxed 必须是**本局最终**结局，
        交还之后策略还可能把这一局做完；提前 close 会把「交还后成功」的片段标成失败，
        档 6 的片段过滤就会用错标签（坑 40③：缺字段/错字段 ≠ 0）。
        """
        if self._cur is None:
            return
        self._cur["handback_at"] = int(step_1based)
        self._cur["n_restages"] = int(n_restages)
        self._cur["unrecoverable"] = True
        self._cur["expert_log"] = list(expert_log)

    def add(self, state: np.ndarray, action: np.ndarray, expert) -> None:
        if self._cur is None:
            return
        self._cur["state"].append(np.asarray(state, dtype=np.float32))
        self._cur["action"].append(np.asarray(action, dtype=np.float32))
        self._cur["phase"].append(getattr(expert, "phase", "?"))
        self._cur["expert_phase"].append(int(getattr(expert, "phase_step", -1)))

    def close(self, success: bool, success_relaxed: bool, steps: int) -> dict | None:
        if self._cur is None:
            return None
        cur = self._cur
        self._cur = None
        cur["success"] = bool(success)
        cur["success_relaxed"] = bool(success_relaxed)
        cur["ep_steps"] = int(steps)
        cur["seg_len"] = len(cur["action"])
        cur.setdefault("handback_at", -1)
        cur.setdefault("n_restages", 0)
        cur.setdefault("unrecoverable", False)
        self.episodes.append(cur)
        return cur

    def dump(self) -> dict[str, np.ndarray]:
        """打包成 np.savez 的 kwargs；没有任何片段时返回空 dict（调用方据此跳过落盘）。"""
        if not self.episodes:
            return {}
        return {
            "state": np.concatenate([np.asarray(e["state"], dtype=np.float32) for e in self.episodes], axis=0),
            "action": np.concatenate([np.asarray(e["action"], dtype=np.float32) for e in self.episodes], axis=0),
            "episode_lengths": np.asarray([e["seg_len"] for e in self.episodes], dtype=np.int32),
            "seeds": np.asarray([e["seed"] for e in self.episodes], dtype=np.int32),
            "trigger": np.asarray([e["trigger"] for e in self.episodes], dtype="<U2"),
            "takeover_step": np.asarray([e["takeover_step"] for e in self.episodes], dtype=np.int32),
            "phase": np.concatenate([np.asarray(e["phase"], dtype="<U14") for e in self.episodes], axis=0),
            "phase_step": np.concatenate([np.asarray(e["expert_phase"], dtype=np.int32) for e in self.episodes], axis=0),
            # 档 5.1：-1 = 专家跑到底；>0 = 专家认输、在该步（1-based）把控制权交还策略。
            # 档 6 过滤片段时用得上：交还前的最后一步是 give_up（原地保持 + 开爪），不是好示范。
            "handback_at": np.asarray([int(e.get("handback_at", -1)) for e in self.episodes], dtype=np.int32),
            "n_restages": np.asarray([int(e.get("n_restages", 0)) for e in self.episodes], dtype=np.int32),
        }


class TakeoverHarness:
    """把检测器 + 专家接管 + 片段记录串起来。每局 reset()，每步 select()。"""

    def __init__(self, env, expert_cls, *, observe_only: bool = False, min_remain: int = 0,
                 enabled: bool = True, detector: GraspDetector | None = None,
                 buffer: SegmentBuffer | None = None, hand_back: bool = False) -> None:
        self.env = env
        self.expert_cls = expert_cls
        self.observe_only = bool(observe_only)   # G0 护栏：只记录不接管，用来证明「套上 harness」没扰动策略路径
        self.enabled = bool(enabled)             # False = 检测器整个关掉（G0a 的对照组，只留 harness 外壳）
        self.min_remain = int(min_remain)        # 剩余步数不足时不接管（默认 0 = 关；第一轮只记录不拦截）
        # 档 5.1：专家显式认输（mg_expert 的 descend 停滞阶梯 ⇒ unrecoverable）时把控制权**交还策略**，
        # 而不是让专家在 give_up 里原地保持到 horizon。默认 False = 档 5 语义（专家跑到本局结束），
        # 这样 chain_s5_timing.sh 那条待判链拿到的仍是档 5 的外壳行为（出身不脏）。
        # 「只接管一次」的原则不破：检测器触发时已把自己 done 掉，交还之后不会再触发第二次。
        self.hand_back = bool(hand_back)
        self.detector = detector or GraspDetector()
        self.buffer = buffer if buffer is not None else SegmentBuffer()
        self.reset(seed=0, can_z0=0.0)

    # ── 每局 ──────────────────────────────────────────────────────────────
    def reset(self, seed: int, can_z0: float) -> None:
        """必须在 env.reset() 之后调用：can_z0 = 本局起始的 can 静止 z（专家 lift 判据的参考线）。"""
        self.seed = int(seed)
        self.can_z0 = float(can_z0)
        self.detector.reset()
        self.expert = None
        self.trigger: str | None = None
        self.takeover_step = -1
        self.takeover_remain = -1
        self.would_have_fired = None    # observe-only 模式下「本来会接管」的记录
        self.would_have_step = -1
        self.min_width = float("inf")
        self.n_empty_steps = 0
        self.handed_back = False        # 档 5.1：本局有没有把控制权交还过策略
        self.handback_step = -1
        self.n_restages = 0
        self.unrecoverable = False
        self.expert_log_at_handback: list[str] = []

    # ── 每步 ──────────────────────────────────────────────────────────────
    def select(self, obs: dict, idx: int, policy_fn) -> tuple[np.ndarray, str]:
        """返回 (要执行的动作, 来源)。来源 ∈ {"policy", "expert"}。

        policy_fn 是零参回调，只在该由策略出动作时才调用 —— 观察模式下每步都调用（与基线同路径），
        接管模式下接管之后**不再调用**（这正是实时性收益的来源：接管段无推理）。
        """
        state = np.asarray(obs[STATE_KEY], dtype=np.float32)
        width = float(state[WIDTH_IDX])
        self.min_width = min(self.min_width, width)
        if width <= self.detector.w_empty:
            self.n_empty_steps += 1

        if self.expert is not None:                       # 已接管：专家跑到本局结束
            if (self.hand_back and not self.handed_back
                    and getattr(self.expert, "unrecoverable", False)):
                # 专家认输（descend 停滞阶梯用满）⇒ 关片段记账、交还策略、本局不再二次接管。
                # 动机（runs/S5_SUPPLEMENT.md 第三节 + runs/s5_diag_resume/）：档 5 里 9 次死循环
                # 平均烧掉 172~307 步，其中 3 次把「基线本来会成功」的局做成失败；阶梯让它在
                # 96 步内认输，剩下的 75~210 步还给策略（配对净收益 = 档 5.1 的主判据，坑 47）。
                self.handed_back = True
                self.handback_step = idx + 1
                self.n_restages = int(getattr(self.expert, "restages", 0))
                self.unrecoverable = True
                self.expert_log_at_handback = list(dict.fromkeys(getattr(self.expert, "log", [])))
                self.buffer.mark_handback(idx + 1, self.n_restages, self.expert_log_at_handback)
                self.expert = None
            else:
                action = np.asarray(self.expert(), dtype=np.float32)
                self.buffer.add(state, action, self.expert)
                return action, "expert"

        tag = self.detector.update(width) if self.enabled else None
        if tag is not None:
            step_1based = idx + 1                         # 与离线标定的触发步号同定义
            remain = int(self.env.horizon) - step_1based
            if self.observe_only:
                self.would_have_fired = tag
                self.would_have_step = step_1based
            elif remain < self.min_remain:
                self.trigger = None                       # 剩余步数不够 ⇒ 不接管（只记录）
            else:
                self.trigger = tag
                self.takeover_step = step_1based
                self.takeover_remain = remain
                self.expert = self.expert_cls(self.env).resume(can_z0=self.can_z0)
                self.buffer.open(self.seed, tag, step_1based, remain)
                action = np.asarray(self.expert(), dtype=np.float32)
                self.buffer.add(state, action, self.expert)
                return action, "expert"

        return policy_fn(), "policy"

    def note_success(self, success_relaxed: bool) -> None:
        """env.step 之后调用：成功闩锁（离线标定的 stop 语义）。"""
        if success_relaxed:
            self.detector.latch_success()

    def finish(self, success: bool, success_relaxed: bool, steps: int) -> dict:
        """本局收尾，返回要写进 eval_summary.per_episode 的档 5 字段。"""
        seg = self.buffer.close(success, success_relaxed, steps)
        fired = self.trigger if self.trigger is not None else self.would_have_fired
        step = self.takeover_step if self.takeover_step > 0 else self.would_have_step
        rec = {
            "takeover": bool(self.trigger is not None),
            "trigger": self.trigger,
            "takeover_step": self.takeover_step,
            "takeover_remain": self.takeover_remain,
            "would_have_fired": fired,          # 观察模式下 = 本来会触发；接管模式下与 trigger 同值
            "would_have_step": step,
            "expert_phases": (list(dict.fromkeys(seg["phase"])) if seg else []),
            "seg_len": (seg["seg_len"] if seg else 0),
            "min_width": (round(self.min_width, 5) if self.min_width < float("inf") else None),
            "n_empty_steps": self.n_empty_steps,
            "observe_only": self.observe_only,
            "detector_enabled": self.enabled,
            # ── 档 5.1 增量字段（hand_back=False 时恒为默认值 ⇒ 档 5 的产物口径不变）──
            "hand_back_enabled": self.hand_back,
            "handback": bool(self.handed_back),
            "handback_step": int(self.handback_step),
            "handback_remain": (int(self.env.horizon) - int(self.handback_step)
                                if self.handed_back else -1),
            "n_restages": int(self.n_restages),
            "unrecoverable": bool(self.unrecoverable),
            "expert_log_at_handback": list(self.expert_log_at_handback),
        }
        return rec


# ────────────────────────────── 自测（纯 CPU，假 env / 假专家）──────────────────────────────
class _FakeEnv:
    horizon = 400


class _FakeExpert:
    """假专家：动作是常量哨兵，用来验证「接管之后走的确实是专家的动作」。"""

    def __init__(self, env) -> None:
        self.env = env
        self.phase = "carry"
        self.phase_step = 0
        self.resumed_with = "NOT_CALLED"
        self.calls = 0

    def resume(self, can_z0=None):
        self.resumed_with = can_z0
        return self

    def __call__(self):
        self.calls += 1
        self.phase_step = self.calls
        return np.full(7, 0.5, dtype=np.float32)


class _GiveUpExpert(_FakeExpert):
    """假专家：第 GIVE_UP_AFTER 次调用时**显式认输**（模拟 mg_expert 的 descend 停滞阶梯）。

    时序与真专家逐字对应：认输发生在 `__call__` **内部**（同一步就把 give_up 动作返回出去），
    所以 harness 是在**下一步**的 select() 开头才看到 `unrecoverable=True` 并交还控制权。
    """

    GIVE_UP_AFTER = 5

    def __init__(self, env) -> None:
        super().__init__(env)
        self.phase = "descend"
        self.restages = 0
        self.unrecoverable = False
        self.log = ["resume:descend"]

    def __call__(self):
        if self.calls + 1 >= self.GIVE_UP_AFTER:
            self.calls += 1
            self.phase_step = self.calls
            self.restages = 2
            self.unrecoverable = True
            self.phase = "give_up"
            self.log += ["descend_restage1", "descend_restage2", "descend_unrecoverable", "give_up"]
            return np.array([0, 0, 0, 0, 0, 0, -1.0], dtype=np.float32)   # 原地保持 + 开爪
        return super().__call__()


def selftest() -> int:
    n_ok = 0

    def ck(name: str, cond: bool, detail: str = "") -> None:
        nonlocal n_ok
        if not cond:
            raise AssertionError(f"selftest 失败：{name} {detail}")
        n_ok += 1

    reset_w, open_w, hold_w, empty_w = 0.0417, 0.078, 0.050, 0.001
    env = _FakeEnv()

    def run(widths, *, observe_only=False, min_remain=0, success_at=-1,
            expert_cls=_FakeExpert, hand_back=False):
        """把一串宽度喂给 harness，返回 (harness, 每步来源, 片段 dict|None)。"""
        h = TakeoverHarness(env, expert_cls, observe_only=observe_only, min_remain=min_remain,
                            hand_back=hand_back)
        h.reset(seed=7000, can_z0=0.8603)
        srcs = []
        created = []
        real_cls = h.expert_cls

        def cls_wrap(e):
            ex = real_cls(e)
            created.append(ex)
            return ex
        h.expert_cls = cls_wrap
        for i, w in enumerate(widths):
            obs = {STATE_KEY: np.array([0.1, -0.25, 0.95, 0, 0, 0, 1, w], dtype=np.float32)}
            _a, src = h.select(obs, i, lambda: np.zeros(7, dtype=np.float32))
            srcs.append(src)
            if i + 1 == success_at:
                h.note_success(True)
        seg = h.finish(success=(success_at > 0), success_relaxed=(success_at > 0), steps=len(widths))
        return h, srcs, seg, created

    # 1) 抓空（从未稳定夹持）⇒ T1，触发步 = 首个空合步 + N_EMPTY - 1（0-based idx）⇒ 1-based idx+1
    widths = [reset_w] + [open_w] * 10 + [empty_w] * 8 + [open_w] * 5
    h, srcs, seg, created = run(widths)
    ck("T1 触发", h.trigger == "T1", str(h.trigger))
    ck("T1 触发步 1-based", h.takeover_step == 11 + N_EMPTY, f"{h.takeover_step} vs {11 + N_EMPTY}")
    ck("触发后来源变 expert", set(srcs[11 + N_EMPTY - 1:]) == {"expert"}, str(srcs[10:]))
    ck("触发前来源全是 policy", set(srcs[:11 + N_EMPTY - 1]) == {"policy"})
    ck("专家被 resume 且拿到 can_z0", created and created[0].resumed_with == 0.8603,
       str(created[0].resumed_with if created else None))
    ck("片段长度 = 触发后剩余步数", seg["seg_len"] == len(widths) - (11 + N_EMPTY - 1), str(seg["seg_len"]))
    ck("剩余步数记账", h.takeover_remain == 400 - h.takeover_step, f"{h.takeover_remain}")

    # 2) 稳定夹持后掉下来 ⇒ T3
    widths = [reset_w] + [hold_w] * (N_HOLD + 3) + [empty_w] * 5
    h, srcs, _seg, _c = run(widths)
    ck("T3 触发", h.trigger == "T3", str(h.trigger))
    ck("T3 触发步", h.takeover_step == 1 + N_HOLD + 3 + N_EMPTY,
       f"{h.takeover_step} vs {1 + N_HOLD + 3 + N_EMPTY}")

    # 3) 差一步就不算稳定夹持 ⇒ 仍是 T1（N_HOLD 边界，防「过渡带被当成夹持」这个上一版的坑）
    widths = [reset_w] + [hold_w] * (N_HOLD - 1) + [empty_w] * 5
    h, _s, _g, _c = run(widths)
    ck("夹持 N_HOLD-1 步 ⇒ T1", h.trigger == "T1", str(h.trigger))
    ck("reset 半开值 0.0417 不算夹持", not (HOLD_LO <= reset_w <= HOLD_HI))

    # 4) 观察模式：记录但**绝不**接管（G0 护栏的前提）
    widths = [reset_w] + [open_w] * 5 + [empty_w] * 10
    h, srcs, seg, created = run(widths, observe_only=True)
    ck("观察模式不接管", h.trigger is None and set(srcs) == {"policy"}, str(set(srcs)))
    ck("观察模式仍记录 would_have_fired", h.would_have_fired == "T1", str(h.would_have_fired))
    ck("观察模式不产生片段", seg["seg_len"] == 0 and not created)
    ck("观察模式 rec.takeover=False", seg["takeover"] is False)

    # 5) 成功闩锁：成功之后即使空合也不再触发
    widths = [reset_w] + [hold_w] * (N_HOLD + 2) + [open_w] * 3 + [empty_w] * 6
    h, srcs, _g, _c = run(widths, success_at=1 + N_HOLD + 2 + 1)
    ck("成功后不再触发", h.trigger is None, str(h.trigger))
    ck("成功后来源全是 policy", set(srcs) == {"policy"})

    # 6) 全程张开（从不闭合）⇒ 不触发（档 2 语料里 0 例，第一轮有意不覆盖）
    h, srcs, _g, _c = run([reset_w] + [open_w] * 200)
    ck("全程张开不触发", h.trigger is None and set(srcs) == {"policy"})

    # 7) min_remain：剩余步数不足时不接管（第一轮默认关，但逻辑必须对）
    widths = [reset_w] + [empty_w] * 5
    h, srcs, _g, _c = run(widths + [open_w] * 10, min_remain=400)
    ck("min_remain 拦住接管", h.trigger is None and set(srcs) == {"policy"}, str(h.trigger))
    h, _s, _g, _c = run(widths + [open_w] * 10, min_remain=0)
    ck("min_remain=0 时照常接管", h.trigger == "T1", str(h.trigger))

    # 8) 一局只接管一次（来回切换会让失败不可归因）
    widths = [reset_w] + [empty_w] * 5 + [open_w] * 3 + [empty_w] * 5 + [hold_w] * 4
    h, srcs, seg, created = run(widths)
    ck("只创建一个专家", len(created) == 1, str(len(created)))
    ck("触发后不再回策略", "policy" not in srcs[N_EMPTY + 4:], str(srcs))
    ck("片段连续到本局结束", seg["seg_len"] == len(widths) - (1 + N_EMPTY - 1), str(seg["seg_len"]))

    # 9) 片段缓冲的数组自洽（档 6 要按 episode_lengths 切片，错位就全废）
    buf = SegmentBuffer()
    buf.open(7001, "T1", 100, 300)
    for k in range(4):
        buf.add(np.zeros(8, dtype=np.float32), np.zeros(7, dtype=np.float32), _FakeExpert(env))
    buf.close(True, True, 400)
    buf.open(7002, "T3", 200, 200)
    for k in range(3):
        buf.add(np.zeros(8, dtype=np.float32), np.zeros(7, dtype=np.float32), _FakeExpert(env))
    buf.close(False, True, 400)
    d = buf.dump()
    ck("片段 state 行数 = 各段之和", d["state"].shape == (7, 8), str(d["state"].shape))
    ck("片段 action 行数 = 各段之和", d["action"].shape == (7, 7), str(d["action"].shape))
    ck("episode_lengths 求和 = 行数", int(d["episode_lengths"].sum()) == len(d["state"]))
    ck("trigger/seeds 每局一个", d["trigger"].tolist() == ["T1", "T3"] and d["seeds"].tolist() == [7001, 7002])
    ck("空缓冲返回空 dict", SegmentBuffer().dump() == {})

    # 9b) enabled=False（G0a 对照组）：连 would_have_fired 都不记，动作全走策略
    h, srcs, seg, created = run([reset_w] + [empty_w] * 10)
    ck("空合会触发（对照组前置）", h.trigger == "T1", str(h.trigger))
    h2 = TakeoverHarness(env, _FakeExpert, enabled=False)
    h2.reset(seed=7000, can_z0=0.8603)
    srcs2 = []
    for i, w in enumerate([reset_w] + [empty_w] * 10):
        _a, src = h2.select({STATE_KEY: np.array([0, 0, .95, 0, 0, 0, 1, w], dtype=np.float32)},
                            i, lambda: np.zeros(7, dtype=np.float32))
        srcs2.append(src)
    seg2 = h2.finish(False, False, 11)
    ck("enabled=False 不接管", set(srcs2) == {"policy"} and h2.trigger is None)
    ck("enabled=False 也不记录 would_have_fired", h2.would_have_fired is None and seg2["seg_len"] == 0)
    ck("enabled=False 写进产物", seg2["detector_enabled"] is False)

    # 10) 阈值与标定脚本同源（不许在 harness 里另立一套魔法数字）
    det = GraspDetector()
    ck("w_empty 同源", det.w_empty == W_EMPTY)
    ck("n_empty 同源", det.n_empty == N_EMPTY)
    ck("hold 带同源", (det.hold_lo, det.hold_hi, det.n_hold) == (HOLD_LO, HOLD_HI, N_HOLD))
    ck("WIDTH_IDX 指向 gripper_width", STATE_KEY is not None and WIDTH_IDX == 7)

    # 11) 在线检测器与离线 scan 逐局一致（这是 G0 等价性的逻辑基础）
    from mg_calib_detector import scan
    rng = np.random.default_rng(20261002)
    for trial in range(200):
        n = int(rng.integers(20, 300))
        w = rng.choice([reset_w, open_w, hold_w, empty_w, 0.030, 0.055], size=n)
        stop = int(rng.integers(1, n + 1))
        tag_off, step_off = scan(w, stop)
        det.reset()
        tag_on, step_on = None, -1
        for i in range(stop):
            t = det.update(float(w[i]))
            if t is not None:
                tag_on, step_on = t, i + 1
                break
        ck(f"在线/离线一致 trial{trial}", (tag_off, step_off) == (tag_on, step_on),
            f"off=({tag_off},{step_off}) on=({tag_on},{step_on}) w={w[:stop].tolist()}")

    # 12) 档 5.1 · hand_back：专家认输 ⇒ 关片段记账、交还策略、本局不再二次接管
    N_GIVEUP = _GiveUpExpert.GIVE_UP_AFTER
    widths = [reset_w] + [open_w] * 10 + [empty_w] * 8 + [open_w] * 12
    fire = 11 + N_EMPTY - 1                      # 0-based：首个空合步 + N_EMPTY - 1
    hb_idx = fire + N_GIVEUP                     # 0-based：交还发生在认输后的下一步
    h, srcs, seg, created = run(widths, expert_cls=_GiveUpExpert, hand_back=True)
    ck("hand_back：照常接管", h.trigger == "T1" and h.takeover_step == fire + 1, str(h.trigger))
    ck("hand_back：认输后交还", h.handed_back and h.handback_step == hb_idx + 1,
       f"{h.handed_back}/{h.handback_step} vs {hb_idx + 1}")
    ck("hand_back：交还前是专家、交还后是策略",
       set(srcs[fire:hb_idx]) == {"expert"} and set(srcs[hb_idx:]) == {"policy"}, str(srcs[fire:]))
    ck("hand_back：只创建一个专家（不二次接管）", len(created) == 1, str(len(created)))
    ck("hand_back：片段只记专家那几步", seg["seg_len"] == N_GIVEUP, str(seg["seg_len"]))
    raw = h.buffer.episodes[-1]
    ck("hand_back：片段记下交还点", raw["handback_at"] == hb_idx + 1, str(raw["handback_at"]))
    ck("hand_back：片段记下 restage 次数", raw["n_restages"] == 2 and raw["unrecoverable"] is True)
    ck("hand_back：rec 与片段同一个交还步", seg["handback_step"] == raw["handback_at"],
       f"{seg['handback_step']} vs {raw['handback_at']}")
    ck("hand_back：rec 带全新字段", (seg["handback"], seg["hand_back_enabled"], seg["n_restages"],
                                  seg["unrecoverable"], seg["handback_remain"])
       == (True, True, 2, True, 400 - (hb_idx + 1)),
       str({k: seg[k] for k in ("handback", "handback_step", "handback_remain", "n_restages",
                                "unrecoverable", "hand_back_enabled")}))
    ck("hand_back：专家 log 落进 rec", "descend_unrecoverable" in seg["expert_log_at_handback"],
       str(seg["expert_log_at_handback"]))
    ck("hand_back：认输那一步的动作进了片段（原地保持 + 开爪）",
       np.allclose(np.asarray(raw["action"][-1]), np.array([0, 0, 0, 0, 0, 0, -1.0]))
       and created[0].phase == "give_up" and created[0].calls == N_GIVEUP,
       str(np.asarray(raw["action"][-1])))

    # 12b) 交还之后策略把这一局做成了 ⇒ 片段必须记**最终**结局（不能提前 close 成失败）
    h, srcs, seg, created = run(widths, expert_cls=_GiveUpExpert, hand_back=True,
                                success_at=hb_idx + 3)
    raw = h.buffer.episodes[-1]
    ck("交还后成功：片段标成功", raw["success_relaxed"] is True and raw["success"] is True,
       f"{raw['success']}/{raw['success_relaxed']}")
    ck("交还后成功：片段仍只含专家步", seg["seg_len"] == N_GIVEUP, str(seg["seg_len"]))
    ck("交还后成功：ep_steps 是本局总步数", raw["ep_steps"] == len(widths), str(raw["ep_steps"]))

    # 12c) 默认 hand_back=False ⇒ 档 5 语义：认输的专家也一路带到本局结束
    h, srcs, seg, created = run(widths, expert_cls=_GiveUpExpert)
    ck("默认不交还：专家跑到本局结束", h.handed_back is False and set(srcs[fire:]) == {"expert"},
       str(srcs[fire:]))
    ck("默认不交还：片段长度 = 触发后剩余步数", seg["seg_len"] == len(widths) - fire, str(seg["seg_len"]))
    ck("默认不交还：rec 字段全是默认值",
       (seg["handback"], seg["handback_step"], seg["handback_remain"], seg["n_restages"],
        seg["unrecoverable"], seg["hand_back_enabled"], seg["expert_log_at_handback"])
       == (False, -1, -1, 0, False, False, []), str(seg))
    ck("默认不交还：片段 handback_at = -1", h.buffer.episodes[-1]["handback_at"] == -1,
       str(h.buffer.episodes[-1]["handback_at"]))

    # 12d) 观察模式下 hand_back 不得改变任何东西（G0b 等价性的前提：观察模式永不接管）
    h, srcs, seg, created = run(widths, expert_cls=_GiveUpExpert, hand_back=True, observe_only=True)
    ck("观察模式 + hand_back：不接管不交还",
       h.trigger is None and h.handed_back is False and set(srcs) == {"policy"} and not created)
    ck("观察模式 + hand_back：仍记录 would_have_fired", h.would_have_fired == "T1")

    # 12e) dump() 的新数组：与 episode_lengths 一一对应，缺省 -1 / 0
    buf = SegmentBuffer()
    buf.open(7001, "T1", 100, 300)
    for _ in range(4):
        buf.add(np.zeros(8, dtype=np.float32), np.zeros(7, dtype=np.float32), _FakeExpert(env))
    buf.mark_handback(104, 2, ["resume:descend", "descend_unrecoverable"])
    buf.close(False, True, 400)
    buf.open(7002, "T3", 200, 200)
    for _ in range(3):
        buf.add(np.zeros(8, dtype=np.float32), np.zeros(7, dtype=np.float32), _FakeExpert(env))
    buf.close(True, True, 400)
    d = buf.dump()
    ck("dump 带 handback_at/n_restages", set(("handback_at", "n_restages")) <= set(d))
    ck("handback_at 每段一个且对齐", d["handback_at"].tolist() == [104, -1], str(d["handback_at"].tolist()))
    ck("n_restages 每段一个且对齐", d["n_restages"].tolist() == [2, 0], str(d["n_restages"].tolist()))
    ck("mark_handback 不改片段长度", d["episode_lengths"].tolist() == [4, 3], str(d["episode_lengths"]))
    ck("mark_handback 在无片段时是空操作", (SegmentBuffer().mark_handback(1, 1, []) is None))

    print(f"[harness] selftest 全绿：{n_ok} 项（含 200 局在线/离线一致性对拍）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    print(__doc__)
    print("本文件只提供逻辑；评测入口是 code/mg_eval_harness.py，标定是 code/mg_calib_detector.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
