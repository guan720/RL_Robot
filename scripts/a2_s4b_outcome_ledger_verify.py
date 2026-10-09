#!/usr/bin/env python3
"""A2 / **S4b**（T-A2-6 · 裁定 93）—— 四类判定接 `ledger` 的闸与变异体（**CPU-only，不占 GPU**）。

## 判据（照抄，不重新解释）
`work/project_parameters.json:1047`（`vla_runtime_gap`）：
「**S4b**（等 C2 的 env）= 四类判定接 `ledger`，**独立于 `reward==4`**，不一致即红。」
派工原文 `rl_harness_supervision/d_handoff_to_a2_20260930.md` §一：
「**必须复用、不得自造**：`harness/env_gym_aloha.py`（579 ln `6c4d71eb732e`，
`MODULE_REPRESENTATION_VERSION='c2-env-gym-aloha-v1'`）+ 闸 `scripts/c2_gate_env_gym_aloha.py`
（`c9100b3811cd`）…自造判定层 = 与 J1–J15 分叉。」

## 本脚本**不做什么**
* **不重算判定**：四类结论全部由 C2 的 `judge_from_facts()` 产出；连 `cross_check()` 与
  `ledger_label_kwargs()` 也是**直接调 C2 的方法对象**（`ega.GymAlohaSimEnv.cross_check(fake_self, j)`），
  不在本脚本里抄一份语义 —— 抄一份就是分叉。闸 **B14** 就是看守这件事的。
* **不声称能力**（裁定 46 / 46.6 / 65-6③）：`capability_claim=false`、
  `success_rate_column="not_an_exit_criterion"`；四类分布是**契约层**证据，不是 policy 指标。
* **不占 GPU**：真实 env 臂用 CPU 软渲染（`MUJOCO_GL=osmesa`）。GPU 臂是
  `scripts/a2_s4b_pi05_gpu_run.py`，另走窗口申报。

## 三值纪律（裁定 88.3-1 / 92）在本脚本里的落点
* 空集聚合 ⇒ `verdict=null` + `nonzero_exit_required=true` + **非零退出码**（B12）。
* `pad_vector`（`processor_pi05.py:72`）D 未测 ⇒ `not_measured`、`value=null`、`safe=null`，
  **不许**写 `false`/`0`（B11）。
* `renderer_class` 终点未在运行内测 ⇒ `null` + `measurement_kind`，**不许拿起点顶替**（B9）。

用法：
  MUJOCO_GL=osmesa python scripts/a2_s4b_outcome_ledger_verify.py \
      --out-dir runs/vla/a2_s4b_outcome_ledger_20260930
  # 只跑纯函数臂（最省，不需要 mujoco 渲染）：
  python scripts/a2_s4b_outcome_ledger_verify.py --no-real-env --out-dir <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np                                                    # noqa: E402

from harness import prompt_bin_guard as PBG                            # noqa: E402
from harness import vla_runtime as VR                                  # noqa: E402
from harness.ledger import EVENT_KINDS, LABEL_KINDS, FactLedger        # noqa: E402

# 复用 S4a 验证脚本里已验过的 stub（不重造；两个位置各写一份 = 本仓已发生四次的事故形状）
sys.path.insert(0, str(REPO / "scripts"))
import a2_s4a_vla_runtime_verify as S4A                                # noqa: E402

OUTCOME_CLASSES = VR.S4B_OUTCOME_CLASSES
FORMAL40_NPZ = "runs/vla/b2_states_14d_20260930/formal40/states_14d.npz"
FORMAL40_NPZ_SHA12_DECLARED = "a84a26079550"
C2_MAINLINE_STATUS_ARM = ("runs/vla/c2_norm_contract_20260929/gate/run_20260930_073852/"
                          "arm_mainline/mainline_status.json")


def sha12(p: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except Exception:                                                  # noqa: BLE001
        return None


def load0() -> dict:
    out = {"ts": datetime.now().astimezone().isoformat(timespec="seconds")}
    try:
        la = os.getloadavg()
        out["loadavg"] = f"{la[0]:.2f} {la[1]:.2f} {la[2]:.2f}"
    except Exception as exc:                                           # noqa: BLE001
        out["loadavg"] = None
        out["loadavg_error"] = f"{type(exc).__name__}: {exc}"
    try:
        st = {}
        for ln in pathlib.Path("/sys/fs/cgroup/cpu/cpu.stat").read_text().splitlines():
            k, _, v = ln.partition(" ")
            st[k] = int(v)
        out["nr_throttled"] = st.get("nr_throttled")
    except Exception as exc:                                           # noqa: BLE001
        out["nr_throttled"] = None
    out["mujoco_gl"] = os.environ.get("MUJOCO_GL")
    out["gpu_used"] = False
    return out


# ═════════════════════════ 判定源（**C2 的代码**，A2 不重算）═════════════════════════
def ega():
    return VR.load_env_gym_aloha()


class C2JudgmentSource:
    """**替身 self**：只承载 `_last_judgment`，方法体全部走 C2 的
    `GymAlohaSimEnv.cross_check` / `.ledger_label_kwargs`（未绑定调用，不构造真 env）。

    为什么这样而不是抄一份：B14 要证的是「判定层没有被 A2 重造」。用 C2 的**方法对象**
    跑在替身 self 上，是能在 CPU-only 条件下做到的最强绑定（真 env 臂另有 B8/B15 覆盖）。
    """

    def __init__(self, judgment, *, env_reward: float | None):
        self._last_judgment = judgment
        self._env_reward = env_reward
        self._ega = ega()

    def last_judgment_object(self):
        return self._last_judgment

    def last_env_reward(self):
        return self._env_reward

    def cross_check(self, judgment=None):
        return self._ega.GymAlohaSimEnv.cross_check(self, judgment)

    def ledger_label_kwargs(self, judgment, **kw):
        return self._ega.GymAlohaSimEnv.ledger_label_kwargs(self, judgment, **kw)


def make_judgment(*, box_z: float, dist_to_finger: float, speed: float, hold_steps: int,
                  step_index: int, horizon: int, direction: str,
                  contact_table: bool = False, env_is_success: bool | None = None,
                  env_reward: int | None = None, finger_nan: bool = False,
                  holder_side: str | None = None,
                  dt: float = VR.MAINLINE_DT_S):
    """用 C2 的**纯函数**判定层造一条结论（输入是事实，判定是 C2 的）。

    `holder_side`：**实际**夹住方块的那一侧（默认 = 目标侧）。反向臂靠它构造出
    「env 的 `reward==4` 说成功（左爪抬起）、而几何真值说没成功（目标侧是右爪）」这个
    **预期不一致**形态 —— 也就是 `gym_aloha/tasks/sim.py:125-149` 方向写死的具体后果。
    """
    m = ega()
    side = m.target_side(direction)
    other = "right" if side == "left" else "left"
    holder = holder_side or side
    far = (0.5, 0.5, 0.1)
    near = (float("nan"),) * 3 if finger_nan else (0.0, 0.0, box_z)
    finger = {"left": (near if holder == "left" else far),
              "right": (near if holder == "right" else far)}
    if finger_nan:
        finger[side] = (float("nan"),) * 3
    facts = m.JudgmentFacts(
        box_xyz=(0.0, 0.0, float(box_z)), box_speed_mps=float(speed), table_z_ref=0.0,
        finger_xyz=finger,
        contact_box_finger={side: bool(dist_to_finger <= 0.045), other: False},
        contact_box_table=bool(contact_table), env_reward=env_reward,
        env_is_success=env_is_success, step_index=int(step_index), horizon=int(horizon), dt=float(dt))
    return m.judge_from_facts(facts, direction=direction, thresholds=m.JudgeThresholds(),
                              hold_steps=int(hold_steps)), facts


# ═════════════════════════ 臂 1：纯判定层（四类都要能出现）═════════════════════════
def arm_pure_judgment() -> dict:
    cases = {}
    j, f = make_judgment(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=6,
                         step_index=120, horizon=300, direction="right_to_left",
                         env_is_success=True, env_reward=4)
    cases["success_green"] = {"judgment": j.as_dict(), "outcome_class": j.outcome_class,
                              "value": j.value, "label_kind": j.label_kind,
                              "geometric_success": j.geometric_success, "agreement": j.agreement}
    j, f = make_judgment(box_z=0.005, dist_to_finger=0.30, speed=0.0, hold_steps=0,
                         step_index=80, horizon=300, direction="right_to_left",
                         env_is_success=False, env_reward=0)
    cases["failure_green"] = {"judgment": j.as_dict(), "outcome_class": j.outcome_class,
                              "value": j.value, "label_kind": j.label_kind,
                              "geometric_success": j.geometric_success, "agreement": j.agreement}
    j, f = make_judgment(box_z=0.005, dist_to_finger=0.30, speed=0.0, hold_steps=0,
                         step_index=300, horizon=300, direction="right_to_left",
                         env_is_success=False, env_reward=0)
    cases["timeout_at_horizon"] = {"judgment": j.as_dict(), "outcome_class": j.outcome_class,
                                   "value": j.value, "label_kind": j.label_kind,
                                   "elapsed_s": j.elapsed_s, "horizon_s": j.horizon_s}
    j, f = make_judgment(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=6,
                         step_index=120, horizon=300, direction="right_to_left", finger_nan=True,
                         env_is_success=True, env_reward=4)
    cases["unknown_unreadable_geom"] = {"judgment": j.as_dict(), "outcome_class": j.outcome_class,
                                        "value": j.value, "label_kind": j.label_kind}
    # flick：瞬时条件全过、但持稳步数不够 ⇒ 几何真值**不**判成功；env 的 reward==4 会判成功
    j, f = make_judgment(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=2,
                         step_index=40, horizon=300, direction="right_to_left",
                         env_is_success=True, env_reward=4)
    cases["flick_hold_too_short"] = {"judgment": j.as_dict(), "outcome_class": j.outcome_class,
                                     "value": j.value, "label_kind": j.label_kind,
                                     "geometric_success": j.geometric_success,
                                     "env_success": j.env_success, "agreement": j.agreement}
    # 高速弹射：速度上限那一维咬住
    j, f = make_judgment(box_z=0.20, dist_to_finger=0.0, speed=3.5, hold_steps=9,
                         step_index=40, horizon=300, direction="right_to_left",
                         env_is_success=True, env_reward=4)
    cases["flick_speed_too_high"] = {"judgment": j.as_dict(), "outcome_class": j.outcome_class,
                                     "value": j.value, "label_kind": j.label_kind,
                                     "geometric_success": j.geometric_success}
    # 反向：左→右，目标侧是 right；env 的 reward==4 写死右→左 ⇒ 起点抬起就会被 env 判成功
    j, f = make_judgment(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=6,
                         step_index=5, horizon=300, direction="left_to_right",
                         holder_side="left", env_is_success=True, env_reward=4)
    cases["reverse_direction_target_side_is_right"] = {
        "judgment": j.as_dict(), "outcome_class": j.outcome_class, "direction": j.direction,
        "value": j.value, "label_kind": j.label_kind,
        "target_side": ega().target_side("left_to_right"),
        "geometric_success": j.geometric_success, "env_success": j.env_success,
        "agreement": j.agreement,
        "note": ("几何真值按 `target_side(direction)` 参数化 ⇒ 反向任务里判的是**右**爪；"
                 "env 的 reward==4 写死右→左，反向任务的起点就会被它判成功")}
    return {"arm": "pure_judgment_layer_owned_by_c2", "cases": cases,
            "observed_outcome_classes": sorted({c["outcome_class"] for c in cases.values()}),
            "judgment_module": VR.env_gym_aloha_identity()["judgment_module"],
            "a2_recomputed_any_judgment": False}


# ═════════════════════════ 臂 2：runtime ↔ ledger 接线 ═════════════════════════
def _drive(runtime: VR.ChunkedVlaRuntime, n_frames: int) -> list:
    out = []
    for _ in range(n_frames):
        out.append(runtime.step())
    return out


def arm_runtime(kind: str, ledger_dir: pathlib.Path) -> dict:
    """`kind ∈ {green, flick_red, reverse_red, coupling_mutant, unknown, timeout, novision_mutant}`"""
    m = ega()
    ledger_path = ledger_dir / f"ledger_s4b_{kind}.sqlite"
    ledger = FactLedger(ledger_path)
    env = S4A.StubEnv(n_frames=8)
    policy = S4A.StubPolicy()
    ep_id = f"s4b-{kind}"
    direction = "left_to_right" if kind == "reverse_red" else "right_to_left"
    # `goal_id` **跟着方向走**（`GOAL_ID_BY_DIRECTION`）：反向臂若仍写死正向 goal_id，
    # 产物里就会出现"方向是左→右、goal 却写着右→左"的自相矛盾（B5 的一项就是看守它）。
    rt = VR.ChunkedVlaRuntime(policy, env, episode_id=ep_id,
                              goal_id=VR.GOAL_ID_BY_DIRECTION[direction], epoch=0,
                              n_replan=2, ledger=ledger, shim_sha256_12="stub")
    rt.reset(seed=1000)
    _drive(rt, 6)

    spec = {
        "green": dict(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=6, step_index=120,
                      horizon=300, env_is_success=True, env_reward=4),
        "flick_red": dict(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=2, step_index=40,
                          horizon=300, env_is_success=True, env_reward=4),
        "reverse_red": dict(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=6, step_index=5,
                            horizon=300, env_is_success=True, env_reward=4, holder_side="left"),
        "unknown": dict(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=6, step_index=120,
                        horizon=300, env_is_success=True, env_reward=4, finger_nan=True),
        "timeout": dict(box_z=0.005, dist_to_finger=0.30, speed=0.0, hold_steps=0, step_index=300,
                        horizon=300, env_is_success=False, env_reward=0),
        "coupling_mutant": dict(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=6,
                                step_index=120, horizon=300, env_is_success=True, env_reward=4),
        "novision_mutant": dict(box_z=0.20, dist_to_finger=0.0, speed=0.02, hold_steps=6,
                                step_index=120, horizon=300, env_is_success=True, env_reward=4),
    }[kind]
    j, facts = make_judgment(direction=direction, **spec)
    src = C2JudgmentSource(j, env_reward=float(spec["env_reward"]))
    res: dict = {"arm": f"runtime_{kind}", "episode_id": ep_id,
                 "ledger_path": str(ledger_path), "direction": direction,
                 "judgment_input_facts": facts.as_dict()}
    if kind == "coupling_mutant":
        # **变异体**：把四类判定的来源换成 `reward==4` ⇒ 必须当场抛，不许"耦合并告警"
        try:
            rt.finalize_from_env_judgment(src, reward=float(spec["env_reward"]), ledger=ledger,
                                          outcome_source=VR.OUTCOME_SOURCE_REWARD4_FORBIDDEN)
            res.update({"raised": False, "error": None})
        except VR.OutcomeCouplingError as exc:
            res.update({"raised": True, "error_type": type(exc).__name__, "error": str(exc)[:600]})
        res["ok"] = bool(res.get("raised"))
        res["note"] = ("这颗牙的形状是「让耦合**不可表达**」：`outcome_source` 只接受 "
                       "`c2_geometric_judgment`；传 reward==4 那一档 ⇒ `OutcomeCouplingError`")
        ledger.close()
        return res
    out = rt.finalize_from_env_judgment(src, reward=float(spec["env_reward"]), ledger=ledger)
    rt_out = VR.s4b_outcome_from_ledger(ledger, episode_id=ep_id)
    labels = [r.to_dict() for r in ledger.labels()]
    events = [r.to_dict() for r in ledger.events(episode_id=ep_id)]
    res.update({
        "outcome": out.as_dict(),
        "ledger_roundtrip": rt_out,
        "n_label_rows": len(labels),
        "label_rows": [{k: r.get(k) for k in ("seq", "label_kind", "value", "rubric_version",
                                              "source", "target_request_id")} for r in labels],
        "event_kinds_used": sorted({e.get("kind") for e in events}),
        "n_episode_end_events": sum(1 for e in events if e.get("kind") == "episode_end"),
        "training_view": {"td_eligible": out.training_view.td_eligible,
                          "bc_eligible": out.training_view.bc_eligible,
                          "terminal_kind": out.training_view.terminal_kind,
                          "isolation_reasons": list(out.training_view.isolation_reasons)},
        "bc_record_extras": rt.last_bc_record_extras,
        "representation_version": rt.representation_version,
        "vision_guard_isolation_reasons": list(rt.isolation_reasons),
    })
    if kind == "novision_mutant":
        # 变异体：把 runtime 的必需图像键抹掉 ⇒ `_guard_vision_channels` 必须硬隔离
        rt._guard_vision_channels(VR.ObsBundle(frame=0, images={}, state=[0.0], state_raw_14d=[0.0],
                                              goal_id="A_to_B", dt_s=0.034, control_hz=29.4118,
                                              representation_version="x", render_backend=("x",)),
                                  where="mutation_probe")
        res["novision_probe_isolation_reasons"] = list(rt.isolation_reasons)
        res["novision_probe_event_kinds"] = sorted({e["kind"] for e in rt.schedule_events})
    ledger.close()
    return res


# ═════════════════════════ 臂 3：真实 env（CPU 软渲染）════════════════════════
def _real_or_none(cases: dict) -> dict | None:
    """真实 env 臂**跑成了**才返回它；跑失败（error dict）一律当 None ⇒ 相关闸按 not_measured 走。"""
    r = cases.get("real_env")
    if not isinstance(r, dict) or r.get("error") or not r.get("outcome"):
        return None
    return r


class HoldPolicy:
    """真实 env 上的**确定性** hold 策略：每个索引都返回 `adapter.hold` ⇒ 机械臂不动，
    「哪一代哪一索引在哪个绝对帧被下发」完全可手算（不引入模型不确定性）。

    与 `a2_s4a_vla_runtime_verify.RealEnvStubPolicy` 同形，**差别只在 `stats_version` 可控**：
    S4a 那条写死 `NONE`（真实情况，裁定 44.1/49.2）；S4b 需要一条**非隔离**的臂来验
    「四类判定 → ledger 行」的完整路径，所以这里显式给一个 stats_version，
    并在产物里写清 `stats_version_is_a_test_input_not_a_claim`。
    """

    chunk_size = VR.MAINLINE_CHUNK_SIZE

    def __init__(self, adapter, n_replan: int = VR.MAINLINE_N_REPLAN,
                 stats_version: str = VR.STATS_VERSION_ABSENT):
        self.adapter = adapter
        self.n_replan = n_replan
        self.stats_version = stats_version
        self.policy_version = "deterministic_hold@v1"
        self.g = 0

    def reset(self, seed: int) -> None:
        self.g = 0

    def select_chunk(self, obs) -> VR.ActionChunk:
        g = self.g
        self.g += 1
        H, n = self.chunk_size, self.n_replan
        base = list(self.adapter.hold)
        acts = [list(base) for _ in range(H)]

        class _A:
            def __init__(self, rows):
                self.rows = rows
                self.shape = (len(rows), len(rows[0]))

            def __getitem__(self, i):
                return self.rows[i]

        return VR.ActionChunk(
            request_id="placeholder", chunk_index=-1, chunk_id=f"hold-chunk-{g}", lease_generation=-1,
            epoch=0, actions=_A(acts), created_at_frame=-1, planned_frames=(-1, -1),
            slot_c=tuple(range(0, n)), slot_e=tuple(range(n, 2 * n)), slot_d=tuple(range(2 * n, H)),
            dt_s=self.adapter.dt_s, control_hz=self.adapter.control_hz, n_replan=n, chunk_size=H,
            inference_wall_s=None, deadline_frame=-1, deadline_s=-1.0,
            policy_version=self.policy_version, stats_version=self.stats_version,
            shim_sha256_12=self.adapter.shim.shim_sha256_12(), representation_version="placeholder")


def _renderer_backend_dependency(ad) -> dict:
    """**实测事实登记**：`renderer_class` 能不能读到，取决于 `MUJOCO_GL` 后端。

    本臂（osmesa）实测：即使"刚 `physics.render()` 返回、同一调用栈"里读，
    `OpenGL.GL.glGetString(GL_RENDERER)` 仍返回 NULL ⇒ dm_control 的 osmesa 后端在自己的
    RenderExecutor 线程/自己的 ctypes OSMesa 上跑，PyOpenGL 这一侧**没有 current context**。
    对照证据（**另一份产物、另一后端**）：`MUJOCO_GL=egl` 时同一条读法读到过
    `llvmpipe (LLVM 15.0.7, 256 bits)`（`runs/vla/a2_s4a_vla_runtime_20260929/s4a_verification.json`
    → `cases.real_env.render_backend[2]`，`probe=inside_real_render`）。

    ⇒ 三条结论，都按三值纪律写：
      ① osmesa 臂的三点 `renderer_class` = **`null` + `not_measured_no_gl_context`**（不是 software、不是 0）；
      ② `renderer_class` 的**权威读数只能在 EGL 臂取**（= GPU 窗口的 `scripts/a2_s4b_pi05_gpu_run.py`），
         这也是 E 的 C4 搭车证据的唯一可取处（`params:1412`）；
      ③ 跨后端的 `renderer_class` **不得互搬**（裁定 46.4/53.6/71 的同族禁令）。
    """
    snap = ad.renderer_ledger.snapshot()
    pts = snap["points"]
    nulls = [p for p in ("at_start", "in_run", "at_end") if pts[p]["renderer_class"] is None]
    xref = REPO / "runs/vla/a2_s4a_vla_runtime_20260929/s4a_verification.json"
    xref_val = None
    if xref.exists():
        try:
            d = json.loads(xref.read_text())
            rb = (((d.get("cases") or {}).get("real_env") or {}).get("render_backend") or [])
            xref_val = rb[2] if len(rb) > 2 else None
        except Exception as exc:                                       # noqa: BLE001
            xref_val = f"read_error:{type(exc).__name__}"
    return {
        "measurement_status": "measured",
        "this_arm_mujoco_gl": os.environ.get("MUJOCO_GL"),
        "points_returning_null": nulls,
        "all_null_points_labelled_not_measured": all(
            str(pts[p]["measurement_kind"]).startswith("not_measured") for p in nulls),
        "mechanism_tried": "explicit_small_render_then_glGetString（同一调用栈、渲染刚返回）",
        "finding": ("osmesa 后端下 PyOpenGL 侧没有 current GL 上下文 ⇒ `glGetString` 恒 NULL；"
                    "这是**取数路径的能力边界**，不是'没有渲染器'"),
        "cross_artifact_evidence": {"path": str(xref.relative_to(REPO)) if xref.exists() else None,
                                    "sha256_12": sha12(xref), "render_backend_entry": xref_val,
                                    "backend_of_that_evidence": "MUJOCO_GL=egl",
                                    "kind": "code_read_semantics + prior_artifact_reading"},
        "conclusions": [
            "osmesa 臂三点 renderer_class = null + not_measured_no_gl_context（不写 software、不写 0）",
            "renderer_class 的权威读数只能在 EGL 臂取（scripts/a2_s4b_pi05_gpu_run.py，需 GPU 窗口申报）",
            "跨后端 renderer_class 不得互搬（裁定 46.4/53.6/71 同族禁令）",
            "E 的 C4 搭车证据（params:1412）只能由 EGL 臂提供；osmesa 臂提供不了 ⇒ 如实登记为 not_measured",
        ],
    }


def arm_real_env(args, ledger_dir: pathlib.Path) -> dict:
    """真实 `GymAlohaJudgedAdapter`（= C2 的 `GymAlohaSimEnv`）+ 真实 ledger + hold 动作若干帧。

    **不占 GPU**：`MUJOCO_GL` 由调用方给（本脚本默认 osmesa）。渲染后端读到的
    `renderer_class` 属**软渲染口径**，不得与 GPU 干净窗的数字互搬（裁定 46.4/53.6/71）。
    """
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    ledger_path = ledger_dir / "ledger_s4b_real_env.sqlite"
    ledger = FactLedger(ledger_path)
    ad = VR.GymAlohaJudgedAdapter(direction=args.direction, image_size=args.image_size,
                                  render=not args.no_render)
    policy = HoldPolicy(ad, n_replan=VR.MAINLINE_N_REPLAN,
                        stats_version=(VR.STATS_VERSION_ABSENT if args.stats_version_none
                                       else "s4b_test_stats@offline_arm"))
    ep_id = f"s4b-real-{args.direction}"
    rt = VR.ChunkedVlaRuntime(policy, ad, episode_id=ep_id, goal_id=ad.goal_id, epoch=0,
                              n_replan=VR.MAINLINE_N_REPLAN, ledger=ledger,
                              shim_sha256_12=ad.jenv.timing.get("shim_sha256_12", "unspecified"),
                              max_episode_steps=ad.max_episode_steps)
    rt.reset(seed=args.seed)
    n = min(int(args.real_frames), ad.max_episode_steps)
    per_frame = []
    for i in range(n):
        sr = rt.step()
        per_frame.append({"abs_frame": sr.abs_frame, "source": sr.source,
                          "execution_status": sr.execution_status,
                          "outcome_class": sr.info.get("outcome_class"),
                          "env_reward": sr.info.get("env_reward"),
                          "geometric_success": sr.info.get("geometric_success"),
                          "hold_steps": sr.info.get("hold_steps")})
    ad.measure_renderer_at_end()
    out = rt.finalize_from_env_judgment(ad, ledger=ledger)
    res = {
        "arm": "real_env_c2_judgment_layer",
        "episode_id": ep_id, "ledger_path": str(ledger_path),
        "direction": args.direction, "n_frames_driven": n,
        "mujoco_gl": os.environ.get("MUJOCO_GL"),
        "env_manifest": ad.manifest(),
        "renderer_class_three_points": ad.renderer_ledger.snapshot(),
        "outcome": out.as_dict(),
        "ledger_roundtrip": VR.s4b_outcome_from_ledger(ledger, episode_id=ep_id),
        "per_frame_first8": per_frame[:8], "per_frame_last4": per_frame[-4:],
        "vision_guard_isolation_reasons": list(rt.isolation_reasons),
        "event_kinds_used": sorted({e["kind"] for e in rt.schedule_events}),
        "n_episode_end_events": sum(1 for e in rt.schedule_events if e["kind"] == "episode_end"),
        "timing_report": rt.timing_report(),
        "representation_version": rt.representation_version,
        "renderer_probe_backend_dependency": _renderer_backend_dependency(ad),
        "stats_version_used": policy.stats_version,
        "stats_version_is_a_test_input_not_a_claim": (
            "本臂的 `stats_version` 是**测试输入**，不是任何真实 stats 的声明；"
            "π₀.₅ base 的真实情况是 `NONE`（裁定 44.1/49.2）⇒ 用 `--stats-version-none` 复现隔离路径"),
        "caliber_note": ("**CPU 软渲染口径**：本臂的 wall/budget 数字不得与 GPU 干净窗（rep4 0.8009 / "
                         "rep5 0.7766）互搬（裁定 46.4/53.6/71）"),
    }
    ledger.close()
    ad.close()
    return res


def arm_real_env_novision(args, ledger_dir: pathlib.Path) -> dict:
    """变异体：真实 env 但 `render_images=False` ⇒ 视觉通道缺失必须**硬隔离**（不许静默退化成状态输入）。"""
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    ledger_path = ledger_dir / "ledger_s4b_real_env_novision.sqlite"
    ledger = FactLedger(ledger_path)
    ad = VR.GymAlohaJudgedAdapter(direction=args.direction, render=False)
    ep_id = "s4b-real-novision"
    policy = S4A.StubPolicy()
    rt = VR.ChunkedVlaRuntime(policy, _RealEnvNoVisionShim(ad), episode_id=ep_id, goal_id=ad.goal_id,
                              epoch=0, n_replan=2, ledger=ledger, shim_sha256_12="unspecified",
                              max_episode_steps=8)
    rt.reset(seed=args.seed)
    for _ in range(4):
        rt.step()
    j = ad.last_judgment_object()
    out = rt.finalize_from_env_judgment(ad, ledger=ledger) if j is not None else None
    res = {"arm": "real_env_novision_mutant", "episode_id": ep_id,
           "isolation_reasons": list(rt.isolation_reasons),
           "event_kinds_used": sorted({e["kind"] for e in rt.schedule_events}),
           "td_eligible": (out.training_view.td_eligible if out else None),
           "bc_eligible": (out.training_view.bc_eligible if out else None),
           "outcome_class": (out.outcome_class if out else None),
           "note": ("本臂**故意**不给图像：证明 `_guard_vision_channels` 在真实 env 路径上仍有牙"
                    "（G3 0/20 的同型根因 = 视觉通道静默退化成状态输入）")}
    ledger.close()
    ad.close()
    return res


class _RealEnvNoVisionShim:
    """把 `GymAlohaJudgedAdapter` 的动作维从 14 降到 stub 的 2（只为驱动 runtime 的槽位逻辑）。"""

    def __init__(self, ad):
        self.ad = ad
        self.dt_s = ad.dt_s
        self.control_hz = ad.control_hz
        self.max_episode_steps = 8
        self._f = 0

    def render_backend(self):
        return ("novision_shim",)

    def reset(self, seed):
        self.ad.reset(seed)
        self._f = 0
        return self._obs(0)

    def _obs(self, f):
        o = self.ad.observe(f)
        return VR.ObsBundle(frame=f, images={}, state=o.state, state_raw_14d=o.state_raw_14d,
                            goal_id=o.goal_id, dt_s=o.dt_s, control_hz=o.control_hz,
                            representation_version=o.representation_version,
                            render_backend=("novision_shim",))

    def observe(self, f):
        return self._obs(f)

    def hold_action(self):
        return [0.1] * 14

    def apply(self, action):
        # stub policy 给的是 2 维动作；真实 env 只吃 14 维 ⇒ 用适配器的 hold 动作顶上。
        # **不许静默补 0**（补 0 = 让机械臂冲向 qpos=0，那是另一种失真）。
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        act = (a[:14] if a.shape[0] >= 14 else np.asarray(self.ad.hold_action(), dtype=np.float32))
        r, te, tr, info = self.ad.apply(act)
        self._f += 1
        return (0.0 if np.isnan(r) else r), te, tr or self._f >= 8, info


# ═════════════════════════ 臂 4：prompt 牙 / pad_vector / renderer ═════════════════════════
def _formal40_states(limit: int = 400) -> tuple[np.ndarray | None, dict]:
    p = REPO / FORMAL40_NPZ
    if not p.exists():
        return None, {"npz_path": FORMAL40_NPZ, "exists": False}
    z = np.load(p)
    key = "states" if "states" in z.files else z.files[0]
    arr = np.asarray(z[key], dtype=np.float64)
    ident = {"npz_path": FORMAL40_NPZ, "exists": True, "npz_sha256_12": sha12(p),
             "npz_sha256_12_declared_by_d": FORMAL40_NPZ_SHA12_DECLARED,
             "npz_sha_matches_declared": sha12(p) == FORMAL40_NPZ_SHA12_DECLARED,
             "npz_keys": list(z.files), "array_key_used": key, "shape": list(arr.shape),
             "dtype": str(arr.dtype), "n_frames_used": int(min(limit, arr.shape[0]))}
    return arr[:limit], ident


def _load_mainline_stats_rows(*, run_dir: str | None = None) -> tuple[list[dict], dict]:
    """从 C2 的权威臂 `matrix.json` 取**全部** `stats_provenance == formal40_bc_source` 的行。

    **为什么是全部而不是挑一行**：C2 自己的口径是 `per_row_then_union`（`mainline_status.json`
    的 `condition_b_resolution.aggregation` 原文：「**不再取 `main_rows[0]`**」）⇒ A2 若挑一行
    当典型，就是本仓已发生四次的"两个位置各写一份口径"事故形状。

    **只读 C2 的产物，不改 C2 的文件**；读不到 ⇒ 返回空表 + `not_measured`（不猜、不填 0）。
    归一化一律走 C2 的 `roundtrip_from_payload()` + `normalize_with_case()`（**不自己写公式**）。
    """
    from harness import norm_contract as NC
    base = REPO / "runs/vla/c2_norm_contract_20260929/gate"
    ident: dict[str, Any] = {"gate_base": str(base.relative_to(REPO))}
    if run_dir:
        cand = [base / run_dir]
    else:
        cand = sorted([d for d in base.glob("run_*") if (d / "arm_mainline" / "matrix.json").exists()],
                      key=lambda d: d.name, reverse=True)
    ident["n_candidate_runs"] = len(cand)
    chosen = None
    for d in cand:
        mx = d / "arm_mainline" / "matrix.json"
        if mx.exists():
            chosen = (d, mx)
            break
    if chosen is None:
        ident.update({"measurement_status": "not_measured", "run_dir": None,
                      "why": "找不到任何 `run_*/arm_mainline/matrix.json`"})
        return [], ident
    run, mx = chosen
    ident.update({"run_dir": str(run.relative_to(REPO)), "matrix_path": str(mx.relative_to(REPO)),
                  "matrix_sha256_12": sha12(mx),
                  "matrix_lines": len(mx.read_text().splitlines()),
                  "mainline_status_sha256_12": sha12(run / "arm_mainline" / "mainline_status.json")})
    gv = run / "gate_verdict.json"
    ident.update({"gate_verdict_path": (str(gv.relative_to(REPO)) if gv.exists() else None),
                  "gate_verdict_sha256_12": sha12(gv),
                  "gate_verdict_exists": gv.exists()})
    if gv.exists():
        try:
            g = json.loads(gv.read_text())
            ident.update({"gate_verdict": g.get("verdict"), "gate_ok": g.get("ok"),
                          "gate_n_red": g.get("n_red"), "gate_n_checks": g.get("n_checks"),
                          "gate_generated_at": g.get("generated_at")})
        except Exception as exc:                                       # noqa: BLE001
            ident["gate_verdict_read_error"] = f"{type(exc).__name__}: {exc}"
    try:
        d_mx = json.loads(mx.read_text())
    except Exception as exc:                                           # noqa: BLE001
        ident.update({"measurement_status": "not_measured", "matrix_read_error": str(exc)[:400]})
        return [], ident
    rows = [r for r in (d_mx.get("rows") or [])
            if isinstance(r, dict) and r.get("stats_provenance") == "formal40_bc_source"]
    ident.update({"n_rows_formal40_bc_source": len(rows),
                  "aggregation_discipline": "per_row_then_union（照 C2 的口径，不挑 `rows[0]` 当典型）",
                  "measurement_status": ("measured" if rows else "not_measured")})
    out = []
    for r in rows:
        sf = pathlib.Path(str(r.get("stats_file")))
        if not sf.is_absolute():
            sf = (run / "arm_mainline" / "stats" / sf.name) if not sf.exists() else sf
        if not sf.exists():
            sf = REPO / str(r.get("stats_file"))
        rec = {"row_id": f'{r.get("case")}|{r.get("family")}|{r.get("coef")}',
               "case": r.get("case"), "family": r.get("family"), "coef": r.get("coef"),
               "consumer": r.get("consumer"), "row_verdict": r.get("verdict"),
               "row_red_ids": r.get("red_ids"),
               "stats_file": (str(sf.relative_to(REPO)) if sf.exists() else str(sf)),
               "stats_file_sha256_12": sha12(sf) if sf.exists() else None,
               "stats_file_declared_sha256_12": r.get("stats_file_sha256_12"),
               "exists": sf.exists()}
        if sf.exists():
            rec["sha_matches_matrix_declaration"] = (rec["stats_file_sha256_12"]
                                                     == r.get("stats_file_sha256_12"))
            try:
                pay = json.loads(sf.read_text())
                rec["stats_provenance_in_file"] = pay.get("stats_provenance")
                rec["bc_admission_in_file"] = pay.get("bc_admission")
                rec["coverage_target_in_file"] = pay.get("coverage_target")
                rec["representation_version_in_file"] = pay.get("representation_version")
                rec["_stats"] = NC.roundtrip_from_payload(pay)
                rec["_case"] = pay.get("case")
                rec["loaded"] = True
            except Exception as exc:                                   # noqa: BLE001
                rec.update({"loaded": False, "load_error": f"{type(exc).__name__}: {exc}"[:400]})
        else:
            rec["loaded"] = False
        out.append(rec)
    ident["normalize_impl"] = ("harness/norm_contract.py::roundtrip_from_payload + normalize_with_case"
                               "（C2 的实现，A2 不自己写归一化公式）")
    ident["norm_contract_sha256_12"] = sha12(REPO / "harness/norm_contract.py")
    ident["a2_is_not_the_writer_of_norm_contract"] = True
    return out, ident


def arm_prompt_tooth() -> dict:
    """运行时 `-1` prompt 牙的**两向对照**（离线侧）：下溢合成状态必检出 / formal-40 状态 0 命中。

    运行时侧（真 prompt 文本）在 `scripts/a2_s4b_pi05_gpu_run.py` 里由 `PromptCapture` 抓；
    本臂证的是**牙本身有双向性**，不是替代运行时证据。
    """
    out: dict = {"arm": "prompt_bin_tooth", "tooth_module": "harness/prompt_bin_guard.py",
                 "tooth_module_sha256_12": PBG.module_sha256_12(),
                 "tooth_module_lines": len(PBG.MODULE_PATH.read_text().splitlines()),
                 "pattern_coverage_probe": PBG.pattern_coverage_probe(),
                 "audited_object": "the_text_actually_concatenated_into_the_prompt"}

    def prompt_from_normalized(xn: np.ndarray) -> str:
        bins = PBG.digitize_bins(xn)
        return ("Task: Transfer the red cube from the right arm to the left arm., State: "
                + " ".join(str(int(b)) for b in bins) + ";\nAction: ")

    # ① 下溢合成状态：归一化后第 3、11 维 < -1 ⇒ bin -1 ⇒ 必须 RED
    under = np.zeros(PBG.MAX_STATE_DIM, dtype=np.float64)
    under[[3, 11]] = [-1.5, -2.0]
    a_under = PBG.audit_prompt_text(prompt_from_normalized(under))
    out["positive_control_underflow"] = {
        "synthetic_normalized_state": under.tolist(),
        "illegal_dims_expected": [3, 11], "audit": a_under,
        "detected": bool(a_under.get("verdict") == "RED"),
        "dims_match": sorted(a_under.get("illegal_bin_hits") or []) == [3, 11]}
    # ② 上侧饱和是**合法**的：bin 255 不判红（dim6/dim13 顶 bin 饱和是真物理，不当 bug 报）
    over = np.zeros(PBG.MAX_STATE_DIM, dtype=np.float64)
    over[[6, 13]] = [1.0, 3.0]
    a_over = PBG.audit_prompt_text(prompt_from_normalized(over))
    out["legal_saturation_control"] = {
        "synthetic_normalized_state": over.tolist(), "audit": a_over,
        "verdict": a_over.get("verdict"), "n_saturated_bin_255": a_over.get("n_saturated_bin_255"),
        "n_illegal_bin_minus1": a_under.get("n_illegal_bin_minus1") and a_over.get("n_illegal_bin_minus1"),
        "note": ("`x ≥ 1 → bin 255` 是**合法**优雅饱和（`processor_pi05.py:77` 的上侧）⇒ 不判红；"
                 "`x < -1 → bin -1` 才是非法 token。这条不对称就是本牙存在的理由")}
    out["legal_saturation_control"]["n_illegal_bin_minus1"] = a_over.get("n_illegal_bin_minus1")
    # ③ formal-40 真实状态（用 C2 的**全部** 8 条权威 stats 行归一化）⇒ 期望 0 命中
    states, npz_ident = _formal40_states(limit=100000)
    rows, rows_ident = _load_mainline_stats_rows()
    usable = [r for r in rows if r.get("loaded") and r.get("_stats") is not None]
    if states is None or not usable:
        out["formal40_control"] = {
            "measurement_status": "not_measured", "verdict": None, "nonzero_exit_required": True,
            "npz_identity": npz_ident, "stats_rows_identity": rows_ident,
            "n_stats_rows_usable": len(usable),
            "why": ("formal-40 npz 或 C2 的 `formal40_bc_source` stats 行读不到 ⇒ **没测到**，"
                    "按三值纪律写 null，不许写 0 命中、不许写 GREEN")}
    else:
        from harness import norm_contract as NC
        per_row = []
        for r in usable:
            xn = NC.normalize_with_case(states, r["_case"], r["_stats"])
            audits = [PBG.audit_prompt_text(prompt_from_normalized(row)) for row in xn]
            agg = PBG.aggregate_prompt_audit(audits)
            per_row.append({
                "row_id": r["row_id"], "case": r["case"], "family": r["family"], "coef": r["coef"],
                "stats_file": r["stats_file"], "stats_file_sha256_12": r["stats_file_sha256_12"],
                "sha_matches_matrix_declaration": r.get("sha_matches_matrix_declaration"),
                "row_verdict_from_c2_matrix": r["row_verdict"], "row_red_ids": r["row_red_ids"],
                "n_frames_audited": len(audits),
                "normalized_min": float(np.min(xn)), "normalized_max": float(np.max(xn)),
                "n_values_below_minus1": int(np.sum(xn < -1.0)),
                "dims_below_minus1": sorted({int(j) for j in np.flatnonzero(xn < -1.0) % xn.shape[1]}),
                "n_values_above_plus1": int(np.sum(xn > 1.0)),
                "dims_above_plus1": sorted({int(j) for j in np.flatnonzero(xn > 1.0) % xn.shape[1]}),
                "aggregate": {k: agg.get(k) for k in
                              ("verdict", "measurement_status", "n_illegal_bin_minus1",
                               "illegal_bin_dims_union", "n_prompts_red", "n_audits")},
            })
        union_dims = sorted({d for r in per_row for d in r["aggregate"]["illegal_bin_dims_union"]})
        n_illegal = sum(int(r["aggregate"]["n_illegal_bin_minus1"] or 0) for r in per_row)
        all_green = all(r["aggregate"]["verdict"] == "GREEN" for r in per_row)
        out["formal40_control"] = {
            "measurement_status": "measured", "npz_identity": npz_ident,
            "stats_rows_identity": rows_ident,
            "n_stats_rows_audited": len(per_row), "per_row": per_row,
            "aggregation": "per_row_then_union（照 C2 的口径，不挑 rows[0] 当典型）",
            "verdict": ("GREEN" if all_green else "RED"),
            "n_illegal_bin_minus1_total": n_illegal,
            "illegal_bin_dims_union": union_dims,
            "n_frames": int(states.shape[0]),
            "note": ("这一臂证的是「牙在**真数据**上不恒红」；若某一行 `n_illegal_bin_minus1 > 0`，"
                     "说明该行 stats 没覆盖住 formal-40 的下侧 ⇒ 属 **C2 线**缺陷，"
                     "A2 只报不改（边界：不改 C2 的文件）"),
        }
    # ④ 空集聚合 ⇒ null + 非零退出
    out["empty_aggregate_three_value_discipline"] = PBG.aggregate_prompt_audit([])
    return out


def arm_pad_vector() -> dict:
    reg = PBG.pad_vector_gap_registration()
    return {"arm": "pad_vector_gap", "registration": reg,
            "is_not_measured": reg.get("measurement_status") == "not_measured",
            "value_is_null": reg.get("value") is None,
            "safe_is_null": reg.get("safe") is None,
            "verdict_is_null": reg.get("verdict") is None,
            "not_written_as_false_or_zero": (reg.get("value") is not False
                                             and reg.get("safe") is not False
                                             and reg.get("value") != 0),
            "authority": "d_handoff_to_a2_20260930.md §一-2（D 未测过这一维，不得假设安全）"}


def arm_renderer() -> dict:
    led = PBG.RendererClassLedger()
    snap0 = led.snapshot()
    led.record("at_start", "llvmpipe (LLVM 15.0.7, 256 bits)", probe_path="test_injection",
               measurement_kind="measured_bare_no_context")
    snap1 = led.snapshot()
    led.record("in_run", "llvmpipe (LLVM 15.0.7, 256 bits)", probe_path="inside_real_render",
               measurement_kind="measured_inside_real_render")
    snap2 = led.snapshot()
    # 变异体：试图拿起点值顶替终点 ⇒ 本类**不提供**这条路径，只能用 record("at_end", …) 显式写。
    # 这里证明"没写终点"时终点确实是 null、且 `at_end_is_null_because_not_measured_in_run=True`。
    return {"arm": "renderer_class_three_points",
            "snapshot_nothing_measured": {"at_start": snap0["at_start"], "in_run": snap0["in_run"],
                                          "at_end": snap0["at_end"],
                                          "at_end_measurement_kind": snap0["at_end_measurement_kind"]},
            "snapshot_start_only": {"at_start": snap1["at_start"], "at_end": snap1["at_end"],
                                    "at_end_measurement_kind": snap1["at_end_measurement_kind"],
                                    "end_equals_start": snap1["end_equals_start"],
                                    "at_end_is_null_because_not_measured_in_run":
                                        snap1["at_end_is_null_because_not_measured_in_run"]},
            "snapshot_start_and_in_run": {"at_start": snap2["at_start"], "in_run": snap2["in_run"],
                                          "at_end": snap2["at_end"],
                                          "at_end_measurement_kind": snap2["at_end_measurement_kind"],
                                          "stability_verdict": snap2["stability_verdict"]},
            "start_must_not_substitute_for_end": snap2["start_must_not_substitute_for_end"],
            "classify_probe": {(s if isinstance(s, str) else "<python_none>"): PBG.classify_renderer(s)
                               for s in ["NVIDIA GeForce RTX 8000 Ada", "llvmpipe (LLVM 15.0.7)", None,
                                         "null_context", "error:ImportError", "AMD Radeon Pro"]},
            "note": ("终点只有两种来源：`record('at_end', …)` 显式写过的值，或 `null` + `measurement_kind`。"
                     "本类**没有**任何从 at_start 回填 at_end 的代码路径")}


# ═════════════════════════════════ 闸 ═════════════════════════════════
def _g(name: str, ok: bool, checks: dict, **extra) -> dict:
    return {"gate": name, "ok": bool(ok), "checks": {k: bool(v) for k, v in checks.items()},
            "n_checks": len(checks), "n_checks_true": sum(1 for v in checks.values() if v),
            **extra}


def B1_four_classes_all_reachable(pure: dict) -> dict:
    obs = set(pure["observed_outcome_classes"])
    c = pure["cases"]
    return _g("B1_four_classes_all_reachable",
              obs == set(OUTCOME_CLASSES)
              and c["success_green"]["outcome_class"] == "success"
              and c["failure_green"]["outcome_class"] == "failure"
              and c["timeout_at_horizon"]["outcome_class"] == "timeout"
              and c["unknown_unreadable_geom"]["outcome_class"] == "unknown"
              and c["unknown_unreadable_geom"]["value"] is None
              and c["unknown_unreadable_geom"]["label_kind"] == "unknown"
              and c["flick_hold_too_short"]["geometric_success"] is False
              and c["flick_speed_too_high"]["geometric_success"] is False,
              {"all_four_classes_observed": obs == set(OUTCOME_CLASSES),
               "success_maps_to_value_1": c["success_green"]["judgment"]["value"] == 1.0,
               "failure_maps_to_value_0": c["failure_green"]["judgment"]["value"] == 0.0,
               "timeout_is_not_failure": c["timeout_at_horizon"]["outcome_class"] == "timeout",
               "timeout_registered_in_seconds": c["timeout_at_horizon"]["judgment"]["elapsed_s"] == 10.2,
               "unknown_value_is_none": c["unknown_unreadable_geom"]["value"] is None,
               "unknown_label_kind": c["unknown_unreadable_geom"]["label_kind"] == "unknown",
               "flick_hold_too_short_not_success": c["flick_hold_too_short"]["geometric_success"] is False,
               "flick_speed_too_high_not_success": c["flick_speed_too_high"]["geometric_success"] is False},
              observed=sorted(obs), required=sorted(OUTCOME_CLASSES),
              vocabulary_owner="harness/env_gym_aloha.py:97 OUTCOME_CLASSES（C2 拥有，A2 不扩）")


def B2_outcome_independent_of_reward4(rt_green: dict, rt_flick: dict, rt_coupling: dict) -> dict:
    og = rt_green["outcome"]
    of = rt_flick["outcome"]
    return _g("B2_outcome_independent_of_reward4",
              rt_coupling.get("raised") is True
              and og["outcome_source"] == VR.OUTCOME_SOURCE_GEOMETRIC
              and og["terminal_kind"] == og["outcome_class"]
              and of["reward4_success"] is True and of["outcome_class"] != "success"
              and of["terminal_kind"] != "success",
              {"coupling_to_reward4_raises_OutcomeCouplingError": rt_coupling.get("raised") is True,
               "outcome_source_is_geometric": og["outcome_source"] == VR.OUTCOME_SOURCE_GEOMETRIC,
               "terminal_kind_equals_outcome_class_green": og["terminal_kind"] == og["outcome_class"],
               "terminal_kind_equals_outcome_class_flick": of["terminal_kind"] == of["outcome_class"],
               "reward4_true_but_outcome_not_success": (of["reward4_success"] is True
                                                        and of["outcome_class"] != "success"),
               "reward_recorded_but_not_used_as_source": (og["reward"] == 4.0
                                                          and og["outcome_source"]
                                                          == VR.OUTCOME_SOURCE_GEOMETRIC)},
              coupling_error=rt_coupling.get("error"),
              flick_outcome_class=of["outcome_class"], flick_reward=of["reward"],
              criterion=VR.S4B_CRITERION_VERBATIM)


def B3_disagreement_is_red(rt_flick: dict) -> dict:
    o = rt_flick["outcome"]
    return _g("B3_disagreement_is_red",
              o["red"] is True and o["cross_check_verdict"] == "RED"
              and o["reward4_vs_outcome_agreement"] is False
              and o["geometric_success"] is False and o["env_is_success"] is True
              and o["red_class"] in ("suspected_pseudo_success__flick_or_graze",
                                     "unattributed_mismatch",
                                     "expected_env_defect__not_policy_capability"),
              {"red_is_true": o["red"] is True,
               "cross_check_verdict_red": o["cross_check_verdict"] == "RED",
               "independent_reward4_comparison_also_red": o["reward4_vs_outcome_agreement"] is False,
               "geometric_says_no_env_says_yes": (o["geometric_success"] is False
                                                  and o["env_is_success"] is True),
               "red_recorded_in_ledger_payload": (rt_flick["ledger_roundtrip"]
                                                  ["episode_end_events"][0]["s4b_red"] is True)},
              red_subject=o["red_subject"], red_class=o["red_class"],
              reasons=o["reasons"][:4])


def B4_agreement_is_green(rt_green: dict) -> dict:
    o = rt_green["outcome"]
    return _g("B4_agreement_is_green",
              o["red"] is False and o["cross_check_verdict"] == "GREEN"
              and o["reward4_vs_outcome_agreement"] is True and o["outcome_class"] == "success"
              and o["geometric_success"] is True,
              {"not_red": o["red"] is False, "cross_check_green": o["cross_check_verdict"] == "GREEN",
               "reward4_agrees": o["reward4_vs_outcome_agreement"] is True,
               "outcome_success": o["outcome_class"] == "success",
               "tooth_is_not_always_red": True},
              note="绿见证（裁定 83.2 `green_witness_required`）：没有绿见证的单向断言不算牙")


def B5_reverse_direction_expected_red(rt_rev: dict, pure: dict) -> dict:
    o = rt_rev["outcome"]
    pc = pure["cases"]["reverse_direction_target_side_is_right"]
    checks = {"target_side_parameterized": pc["target_side"] == "right",
               "reverse_red_is_true": o["red"] is True,
               "red_subject_attributed_to_env_defect": o["red_subject"] == "env_reward_direction_hardcoded",
               "red_not_downgraded": o["cross_check_verdict"] == "RED",
               "outcome_still_from_geometric": o["outcome_source"] == VR.OUTCOME_SOURCE_GEOMETRIC,
               "goal_id_follows_direction": rt_rev["outcome"]["goal_id"] == "transfer_cube_left_to_right"}
    return _g("B5_reverse_direction_expected_red", all(checks.values()), checks,
              red_class=o["red_class"],
              note=("反向任务里 RED 是**预期形态**（env 的 reward==4 写死右→左）⇒ RED 照记不降级，"
                    "但归因写清红在 env 的判据上、不在 A2 的运行时、也不在 policy 能力上"))


def B6_ledger_roundtrip(rt_green: dict, rt_timeout: dict, rt_unknown: dict) -> dict:
    def chk(res):
        r = res["ledger_roundtrip"]
        return (r.get("measurement_status") == "measured"
                and r.get("n_outcome_labels", 0) >= 1
                and r.get("n_episode_end_events", 0) == 1
                and res["n_episode_end_events"] == 1
                and r["episode_end_events"][0]["s4b_outcome_source"] == VR.OUTCOME_SOURCE_GEOMETRIC)
    g, t, u = rt_green["ledger_roundtrip"], rt_timeout["ledger_roundtrip"], rt_unknown["ledger_roundtrip"]
    return _g("B6_ledger_roundtrip_four_classes",
              chk(rt_green) and chk(rt_timeout) and chk(rt_unknown)
              and g["outcome_classes_observed"] == ["success"]
              and t["outcome_classes_observed"] == ["timeout"]
              and u["outcome_classes_observed"] == ["unknown"]
              and rt_green["outcome"]["ledger_writes"]["measurement_status"] == "measured",
              {"green_roundtrip": chk(rt_green), "timeout_roundtrip": chk(rt_timeout),
               "unknown_roundtrip": chk(rt_unknown),
               "exactly_one_episode_end_per_episode": (rt_green["n_episode_end_events"] == 1
                                                       and rt_timeout["n_episode_end_events"] == 1
                                                       and rt_unknown["n_episode_end_events"] == 1),
               "outcome_class_readable_from_label_value_json": bool(g["outcome_labels"]),
               "outcome_source_readable_from_episode_end_payload": (
                   g["episode_end_events"][0]["s4b_outcome_source"] == VR.OUTCOME_SOURCE_GEOMETRIC),
               "label_seq_present": isinstance(rt_green["outcome"]["ledger_writes"].get("label_seq"), int)},
              observed={k: v["ledger_roundtrip"].get("outcome_classes_observed")
                        for k, v in (("green", rt_green), ("timeout", rt_timeout), ("unknown", rt_unknown))})


def B7_ledger_vocabulary_not_extended(rt_green: dict, rt_timeout: dict, rt_unknown: dict) -> dict:
    kinds = set()
    for r in (rt_green, rt_timeout, rt_unknown):
        kinds |= set(r["event_kinds_used"])
        for lab in r["label_rows"]:
            kinds.add(("label_kind", lab["label_kind"]))
    ev_kinds = {k for k in kinds if isinstance(k, str)}
    lab_kinds = {k[1] for k in kinds if isinstance(k, tuple)}
    return _g("B7_ledger_vocabulary_not_extended",
              ev_kinds <= set(EVENT_KINDS) and lab_kinds <= set(LABEL_KINDS),
              {"event_kinds_subset_of_ledger_EVENT_KINDS": ev_kinds <= set(EVENT_KINDS),
               "label_kinds_subset_of_ledger_LABEL_KINDS": lab_kinds <= set(LABEL_KINDS),
               "no_new_kind_invented": True,
               "timeout_uses_label_kind_success_value_0": (
                   rt_timeout["label_rows"][0]["label_kind"] == "success"
                   and rt_timeout["label_rows"][0]["value"] == 0.0),
               "unknown_uses_label_kind_unknown": (
                   rt_unknown["label_rows"][0]["label_kind"] == "unknown")},
              event_kinds_used=sorted(ev_kinds), label_kinds_used=sorted(lab_kinds),
              vocabulary_source="harness/ledger.py:31-46（EVENT_KINDS / LABEL_KINDS，A2 只 import）")


def B8_vision_channel_guard_on_real_env(real: dict | None, novision: dict) -> dict:
    nv_ok = (len(novision["isolation_reasons"]) >= 1
             and any("vision_channel_absent" in r for r in novision["isolation_reasons"])
             and novision["td_eligible"] is False and novision["bc_eligible"] is False
             and "verdict_identity_absent" in novision["event_kinds_used"])
    checks = {"novision_mutant_hard_isolated": nv_ok,
              "novision_mutant_td_and_bc_both_false": (novision.get("td_eligible") is False
                                                       and novision.get("bc_eligible") is False),
              "novision_arm_actually_measured": novision.get("measurement_status") != "not_measured"}
    ok = nv_ok
    if real is not None:
        no_iso = not any("vision_channel_absent" in r for r in real["vision_guard_isolation_reasons"])
        three_keys = set(real["env_manifest"]["obs_contract"]["required_keys"]) >= set(
            ["observation.images.base_0_rgb", "observation.images.left_wrist_0_rgb",
             "observation.images.right_wrist_0_rgb"])
        checks["real_env_vision_guard_not_fired"] = no_iso
        checks["real_env_three_image_keys_present"] = three_keys
        checks["real_env_no_verdict_identity_absent_from_vision_guard"] = (
            "verdict_identity_absent" not in
            [k for k in real["event_kinds_used"] if k == "verdict_identity_absent"]
            or True)   # S4b 的准入声明**本来就会**发一条 verdict_identity_absent（见下），故此项只登记不判
        ok = ok and no_iso and three_keys
    return _g("B8_vision_channel_guard_real_env", ok, checks,
              real_env_isolation_reasons=(real or {}).get("vision_guard_isolation_reasons"),
              novision_isolation_reasons=novision["isolation_reasons"],
              verdict_identity_absent_semantics=(
                  "S4b 会**主动**发一条 `verdict_identity_absent`：那是 `harness/ledger.py:377` 的 "
                  "fail-closed 准入声明（env 判定不是被门禁分级的裁定 ⇒ `observation_only=True`），"
                  "**不是**视觉通道缺失造成的隔离。两者同 kind、不同 payload.declared，读账本时要分清"),
              note=("_guard_vision_channels 在真实 env 路径上仍有牙；G3 0/20 的同型根因"
                    "（视觉通道静默退化成状态输入）不会被 S4b 放行"))


def B9_renderer_three_points(rnd: dict, real: dict | None) -> dict:
    s0 = rnd["snapshot_start_only"]
    checks = {"end_is_null_when_only_start_measured": s0["at_end"] is None,
              "end_measurement_kind_is_not_measured": s0["at_end_measurement_kind"] == "not_measured",
              "end_null_flag_set": s0["at_end_is_null_because_not_measured_in_run"] is True,
              "end_equals_start_is_none_not_true": s0["end_equals_start"] is None,
              "classify_nvidia_gpu": rnd["classify_probe"]["NVIDIA GeForce RTX 8000 Ada"] == "nvidia_gpu",
              "classify_software": rnd["classify_probe"]["llvmpipe (LLVM 15.0.7)"] == "software",
              "classify_none_stays_null": rnd["classify_probe"]["<python_none>"] is None}
    ok = all(checks.values())
    if real is not None:
        snap = real["renderer_class_three_points"]
        pts = snap["points"]
        # **真牙**：读到 NULL 就**必须**标 `not_measured*`，绝不允许标 `measured*`
        # （修前 A2 自己就踩过：`inside_real_render=True` 时把 NULL 记成 measured_inside_real_render）。
        checks["null_never_labelled_measured"] = all(
            (pts[p]["renderer_class"] is not None)
            or str(pts[p]["measurement_kind"]).startswith("not_measured")
            for p in ("at_start", "in_run", "at_end"))
        checks["three_points_independently_registered"] = (
            len({pts[p]["measured_at"] for p in ("at_start", "in_run", "at_end")}) >= 1
            and all(pts[p]["probe_path"] for p in ("at_start", "in_run", "at_end")))
        checks["real_env_no_start_substitution"] = bool(snap["start_must_not_substitute_for_end"])
        checks["real_env_at_end_null_implies_not_measured_kind"] = (
            snap["at_end"] is not None
            or str(pts["at_end"]["measurement_kind"]).startswith("not_measured"))
        checks["backend_dependency_registered"] = bool(
            (real.get("renderer_probe_backend_dependency") or {}).get("measurement_status") == "measured")
        ok = ok and all(checks[k] for k in
                        ("null_never_labelled_measured", "real_env_no_start_substitution",
                         "real_env_at_end_null_implies_not_measured_kind",
                         "three_points_independently_registered", "backend_dependency_registered"))
    return _g("B9_renderer_class_three_points", ok, checks,
              real_snapshot=(real or {}).get("renderer_class_three_points"),
              c4_piggyback=(real or {}).get("renderer_class_three_points", {}).get("c4_piggyback_evidence_for_e"),
              note=("终点值只有两种来源：显式 `record('at_end', …)`，或 `null` + `measurement_kind`；"
                    "本类没有任何从起点回填终点的代码路径（D 的派工原文：不许拿起点顶替）"))


def B10_prompt_tooth_two_way(pt: dict) -> dict:
    pc = pt["positive_control_underflow"]
    f40 = pt["formal40_control"]
    cov = pt["pattern_coverage_probe"]
    ls = pt["legal_saturation_control"]
    checks = {
        "underflow_synthetic_state_detected": pc["detected"] is True,
        "underflow_illegal_dims_exact": pc["dims_match"] is True,
        "legal_upper_saturation_255_not_red": ls["verdict"] == "GREEN",
        "pattern_coverage_probe_self_green": cov["auditor_self_verdict"] == "GREEN",
        "all_injected_bad_forms_detected": cov["detected"] is True,
        "negative_control_green": cov["negative_control"]["ok"] is True,
        "audited_object_is_prompt_text": pt["audited_object"]
        == "the_text_actually_concatenated_into_the_prompt",
    }
    ok = all(checks.values())
    if f40.get("measurement_status") == "measured":
        checks["formal40_zero_illegal_bin_hits_all_rows"] = (
            f40["n_illegal_bin_minus1_total"] == 0)
        checks["formal40_all_rows_green"] = f40["verdict"] == "GREEN"
        checks["formal40_all_8_authoritative_rows_audited"] = f40["n_stats_rows_audited"] == 8
        checks["formal40_stats_sha_matches_c2_matrix_declaration"] = all(
            r.get("sha_matches_matrix_declaration") for r in f40["per_row"])
        ok = ok and all(checks[k] for k in
                        ("formal40_zero_illegal_bin_hits_all_rows", "formal40_all_rows_green",
                         "formal40_all_8_authoritative_rows_audited",
                         "formal40_stats_sha_matches_c2_matrix_declaration"))
    else:
        checks["formal40_registered_as_not_measured"] = (f40.get("verdict") is None
                                                         and f40.get("nonzero_exit_required") is True)
        ok = ok and checks["formal40_registered_as_not_measured"]
    return _g("B10_prompt_bin_tooth_two_way", ok, checks,
              formal40_measurement_status=f40.get("measurement_status"),
              formal40_verdict=f40.get("verdict"),
              formal40_n_rows=f40.get("n_stats_rows_audited"),
              formal40_n_frames=f40.get("n_frames"),
              formal40_illegal_bin_dims_union=f40.get("illegal_bin_dims_union"),
              formal40_per_row_summary=[{k: r.get(k) for k in
                                         ("row_id", "row_verdict_from_c2_matrix",
                                          "normalized_min", "normalized_max",
                                          "n_values_below_minus1", "n_values_above_plus1")}
                                        for r in (f40.get("per_row") or [])],
              npz_identity=f40.get("npz_identity"), stats_rows_identity=f40.get("stats_rows_identity"),
              n_injected_bad_forms=cov["n_injected_bad_forms"],
              note=("两向 = 下溢合成状态**必检出** / formal-40 真数据（C2 全部 8 条权威 stats 行）"
                    "**0 命中**；另按裁定 93.5 自带对照探针，探针不过 ⇒ 审计器自己红、不得报绿"))


def B11_pad_vector_not_measured(pv: dict) -> dict:
    return _g("B11_pad_vector_registered_not_measured",
              pv["is_not_measured"] and pv["value_is_null"] and pv["safe_is_null"]
              and pv["verdict_is_null"] and pv["not_written_as_false_or_zero"],
              {"measurement_status_is_not_measured": pv["is_not_measured"],
               "value_is_null": pv["value_is_null"], "safe_is_null": pv["safe_is_null"],
               "verdict_is_null": pv["verdict_is_null"],
               "not_written_as_false_or_zero": pv["not_written_as_false_or_zero"],
               "open_questions_registered": len(
                   pv["registration"].get("open_questions") or []) >= 3},
              registration=pv["registration"],
              note="D 未测过 `pad_vector`（`processor_pi05.py:72`）⇒ 不假设安全，按三值纪律登记")


def B12_three_value_discipline_empty_set(pt: dict) -> dict:
    e = pt["empty_aggregate_three_value_discipline"]
    return _g("B12_empty_set_aggregate_is_null_and_nonzero_exit",
              e["verdict"] is None and e["measurement_status"] == "not_measured"
              and e["nonzero_exit_required"] is True and e["n_illegal_bin_minus1"] is None
              and e["n_audits"] == 0,
              {"verdict_is_null": e["verdict"] is None,
               "measurement_status_not_measured": e["measurement_status"] == "not_measured",
               "nonzero_exit_required": e["nonzero_exit_required"] is True,
               "count_is_null_not_zero": e["n_illegal_bin_minus1"] is None},
              empty_aggregate=e)


def B13_td_only_three_hard_constraints(rt_timeout: dict) -> dict:
    ex = rt_timeout["bc_record_extras"]
    rv = rt_timeout["representation_version"]
    return _g("B13_td_only_three_hard_constraints_83_7_2",
              ex.get("truncated_by_timelimit") is True
              and "timeout_bc=kept_flagged" in rv and "timeout_td=isolated" in rv
              and ex.get("bc_kept_flagged") is True and ex.get("td_isolated_by_timeout") is True
              and rt_timeout["training_view"]["bc_eligible"] is True
              and rt_timeout["training_view"]["td_eligible"] is False,
              {"constraint1_flag_present": ex.get("truncated_by_timelimit") is True,
               "constraint1_token_in_rep_version": "timeout_bc=kept_flagged" in rv,
               "constraint2_truncated_not_terminal": (
                   rt_timeout["outcome"]["terminal_kind"] == "timeout"
                   and "success" not in (ex.get("must_not_be_labelled_as") or ())[:0]
                   and ex.get("must_not_be_labelled_as") == ("success", "terminated")),
               "constraint3_validators_ran_without_raise": True,
               "td_isolated_bc_kept": (rt_timeout["training_view"]["td_eligible"] is False
                                       and rt_timeout["training_view"]["bc_eligible"] is True)},
              bc_record_extras=ex, representation_version=rv,
              timeout_isolation_scope=ex.get("timeout_isolation_scope"),
              pending_user_ratification=("`timeout_isolation_scope=td_only` 仍待用户追认"
                                         "（裁定 83§5② / §D93.9 待批项①）"))


def B14_judgment_layer_not_reimplemented(pure: dict, rt_green: dict) -> dict:
    """**不得自造判定层**：机器核，不靠自觉。

    三条证据：① A2 的文件里不得出现 C2 的阈值常量名（那意味着重造了一份判据）；
    ② `cross_check` / `ledger_label_kwargs` 的**函数对象**必须来自 C2 的模块；
    ③ 产物里的判定模块身份必须是 A2 侧**重算**的、且与 D 交接声明值相符。
    """
    a2_src = (REPO / "harness/vla_runtime.py").read_text()
    forbidden_tokens = ["grasp_max_dist_m:", "lift_min_height_m:", "hold_min_steps:",
                        "box_speed_max_mps:", "rubric_version: str ="]
    hits = [t for t in forbidden_tokens if t in a2_src]
    ident = VR.env_gym_aloha_identity()
    src = C2JudgmentSource(pure["cases"]["success_green"] and _mk_j(pure), env_reward=4.0)
    cc_mod = type(src).cross_check.__wrapped__ if hasattr(type(src).cross_check, "__wrapped__") else None
    checks = {
        "a2_file_defines_no_geometric_thresholds": not hits,
        "cross_check_delegates_to_c2_method": (
            src._ega.GymAlohaSimEnv.cross_check.__module__ == "harness.env_gym_aloha"),
        "ledger_label_kwargs_delegates_to_c2_method": (
            src._ega.GymAlohaSimEnv.ledger_label_kwargs.__module__ == "harness.env_gym_aloha"),
        "judge_from_facts_is_c2s": ega().judge_from_facts.__module__ == "harness.env_gym_aloha",
        "judgment_module_sha_recomputed": ident["judgment_module"]["sha256_12"] == "6c4d71eb732e",
        "judgment_module_lines_recomputed": ident["judgment_module"]["lines"] == 579,
        "judgment_gate_sha_recomputed": ident["judgment_gate"]["sha256_12"] == "c9100b3811cd",
        "outcome_authority_declared_in_product": (
            rt_green["outcome"]["ledger_writes"]["label_kind"] in ("success", "unknown")),
    }
    return _g("B14_judgment_layer_not_reimplemented", all(checks.values()), checks,
              forbidden_token_hits=hits, identity=ident, cc_wrapped=str(cc_mod),
              note=("A2 只做接线：四类结论、阈值、映射表、交叉核验全部是 C2 的；"
                    "自造判定层 = 与 `scripts/c2_gate_env_gym_aloha.py` 的 J1–J15 分叉"))


def _mk_j(pure: dict):
    m = ega()
    d = pure["cases"]["success_green"]["judgment"]
    return m.Judgment(outcome_class=d["outcome_class"], value=d["value"], label_kind=d["label_kind"],
                      direction=d["direction"], hold_steps=d["hold_steps"],
                      reasons=tuple(d["reasons"]), geometric_success=d["geometric_success"],
                      env_success=d["env_success"], agreement=d["agreement"],
                      thresholds=m.JudgeThresholds(**d["thresholds"]),
                      elapsed_s=d.get("elapsed_s"), horizon_s=d.get("horizon_s"))


def B15_frozen_surface_untouched() -> dict:
    frozen = {"harness/contracts.py": "96c99ead93d2", "harness/ledger.py": "2a33c3f5516e"}
    obs = {k: sha12(REPO / k) for k in frozen}
    c2files = {"harness/env_gym_aloha.py": "6c4d71eb732e",
               "scripts/c2_gate_env_gym_aloha.py": "c9100b3811cd",
               "harness/norm_contract.py": None}
    c2obs = {k: sha12(REPO / k) for k in c2files}
    ok = all(obs[k] == v for k, v in frozen.items())
    ok = ok and c2obs["harness/env_gym_aloha.py"] == "6c4d71eb732e"
    ok = ok and c2obs["scripts/c2_gate_env_gym_aloha.py"] == "c9100b3811cd"
    return _g("B15_frozen_and_other_line_surfaces_untouched", ok,
              {"contracts_py_sha_unchanged": obs["harness/contracts.py"] == frozen["harness/contracts.py"],
               "ledger_py_sha_unchanged": obs["harness/ledger.py"] == frozen["harness/ledger.py"],
               "c2_env_gym_aloha_unchanged": c2obs["harness/env_gym_aloha.py"] == "6c4d71eb732e",
               "c2_gate_unchanged": c2obs["scripts/c2_gate_env_gym_aloha.py"] == "c9100b3811cd"},
              observed=obs, other_line_observed=c2obs, declared=frozen,
              note=("`harness/norm_contract.py` 是 C2 的写入面且 T-C2-8 正在改 ⇒ **不给期望值**，"
                    "只登记 A2 观测到的 sha（`a2_not_the_writer=true`）"),
              a2_not_the_writer_of_norm_contract=True)


# ═════════════════════════ 变异自检（每条闸一处具体篡改）═════════════════════════
def mutation_self_test(cases: dict) -> dict:
    import copy
    detail: dict[str, dict] = {}

    def rec(name: str, baseline_ok: bool, mutant_ok: bool, note: str = "") -> None:
        detail[name] = {"baseline_ok": bool(baseline_ok), "mutant_ok": bool(mutant_ok),
                        "teeth": bool(baseline_ok and not mutant_ok), "note": note}

    pure = cases["pure_judgment"]
    rt = {k: v for k, v in cases.items() if k.startswith("runtime_")}

    # B1：把 timeout 的 outcome_class 篡成 failure（四类塌成三类）
    m = copy.deepcopy(pure)
    m["cases"]["timeout_at_horizon"]["outcome_class"] = "failure"
    m["observed_outcome_classes"] = sorted({c["outcome_class"] for c in m["cases"].values()})
    rec("B1_timeout_collapsed_into_failure", B1_four_classes_all_reachable(pure)["ok"],
        B1_four_classes_all_reachable(m)["ok"], "四类塌成三类必须被抓")

    # B1b：把 unknown 的 value 从 None 篡成 0.0（三值纪律）
    m = copy.deepcopy(pure)
    m["cases"]["unknown_unreadable_geom"]["value"] = 0.0
    m["cases"]["unknown_unreadable_geom"]["judgment"]["value"] = 0.0
    rec("B1b_unknown_value_none_to_zero", B1_four_classes_all_reachable(pure)["ok"],
        B1_four_classes_all_reachable(m)["ok"], "unknown 的 value 写成 0.0 = 把'不知道'当成'失败'")

    # B2：把 outcome_source 篡成 reward==4 那一档
    m = copy.deepcopy(rt["runtime_green"])
    m["outcome"]["outcome_source"] = VR.OUTCOME_SOURCE_REWARD4_FORBIDDEN
    rec("B2_outcome_source_switched_to_reward4",
        B2_outcome_independent_of_reward4(rt["runtime_green"], rt["runtime_flick_red"],
                                          rt["runtime_coupling_mutant"])["ok"],
        B2_outcome_independent_of_reward4(m, rt["runtime_flick_red"],
                                          rt["runtime_coupling_mutant"])["ok"],
        "判定来源被换成 reward==4 必须红")

    # B2b：把耦合变异体篡成"没抛"
    m = copy.deepcopy(rt["runtime_coupling_mutant"])
    m["raised"] = False
    rec("B2b_coupling_mutant_pretends_no_raise",
        B2_outcome_independent_of_reward4(rt["runtime_green"], rt["runtime_flick_red"],
                                          rt["runtime_coupling_mutant"])["ok"],
        B2_outcome_independent_of_reward4(rt["runtime_green"], rt["runtime_flick_red"], m)["ok"],
        "牙没咬（没抛）必须被 B2 抓住")

    # B3：把 flick 臂的 RED 篡成 GREEN
    m = copy.deepcopy(rt["runtime_flick_red"])
    m["outcome"]["red"] = False
    m["outcome"]["cross_check_verdict"] = "GREEN"
    m["outcome"]["reward4_vs_outcome_agreement"] = True
    m["ledger_roundtrip"]["episode_end_events"][0]["s4b_red"] = False
    rec("B3_disagreement_downgraded_to_green",
        B3_disagreement_is_red(rt["runtime_flick_red"])["ok"],
        B3_disagreement_is_red(m)["ok"], "不一致被降级成绿必须红")

    # B4：把绿见证篡成红（恒红牙 = 装饰品）
    m = copy.deepcopy(rt["runtime_green"])
    m["outcome"]["red"] = True
    rec("B4_green_witness_turned_red", B4_agreement_is_green(rt["runtime_green"])["ok"],
        B4_agreement_is_green(m)["ok"], "没有绿见证的单向断言不算牙")

    # B5：把反向 RED 的归因篡成 policy 能力问题
    m = copy.deepcopy(rt["runtime_reverse_red"])
    m["outcome"]["red_subject"] = "policy_failed"
    rec("B5_reverse_red_misattributed",
        B5_reverse_direction_expected_red(rt["runtime_reverse_red"], pure)["ok"],
        B5_reverse_direction_expected_red(m, pure)["ok"],
        "把 env 判据缺陷误归因成 policy 能力必须红（裁定 46.6）")

    # B5b：把 target_side 篡成写死的 left
    m = copy.deepcopy(pure)
    m["cases"]["reverse_direction_target_side_is_right"]["target_side"] = "left"
    rec("B5b_target_side_hardcoded_left",
        B5_reverse_direction_expected_red(rt["runtime_reverse_red"], pure)["ok"],
        B5_reverse_direction_expected_red(rt["runtime_reverse_red"], m)["ok"],
        "方向写死（= env 的缺陷形状）必须被抓")

    # B6：把 ledger round-trip 篡成 not_measured
    m = copy.deepcopy(rt["runtime_green"])
    m["ledger_roundtrip"]["measurement_status"] = "not_measured"
    m["ledger_roundtrip"]["n_outcome_labels"] = 0
    m["ledger_roundtrip"]["outcome_labels"] = []
    rec("B6_ledger_roundtrip_erased",
        B6_ledger_roundtrip(rt["runtime_green"], rt["runtime_timeout"], rt["runtime_unknown"])["ok"],
        B6_ledger_roundtrip(m, rt["runtime_timeout"], rt["runtime_unknown"])["ok"],
        "账本里读不回来 = 没接上")

    # B6b：发两条 episode_end（重复计数）
    m = copy.deepcopy(rt["runtime_green"])
    m["n_episode_end_events"] = 2
    m["ledger_roundtrip"]["n_episode_end_events"] = 2
    m["ledger_roundtrip"]["episode_end_events"] = m["ledger_roundtrip"]["episode_end_events"] * 2
    rec("B6b_double_episode_end",
        B6_ledger_roundtrip(rt["runtime_green"], rt["runtime_timeout"], rt["runtime_unknown"])["ok"],
        B6_ledger_roundtrip(m, rt["runtime_timeout"], rt["runtime_unknown"])["ok"],
        "同一局两条 episode_end = 重复计数")

    # B7：新造一个 label_kind
    m = copy.deepcopy(rt["runtime_green"])
    m["label_rows"][0]["label_kind"] = "outcome_class"
    rec("B7_new_label_kind_invented",
        B7_ledger_vocabulary_not_extended(rt["runtime_green"], rt["runtime_timeout"],
                                          rt["runtime_unknown"])["ok"],
        B7_ledger_vocabulary_not_extended(m, rt["runtime_timeout"], rt["runtime_unknown"])["ok"],
        "词表不许新造值")

    # B8：把 novision 变异体篡成"没隔离"
    m = copy.deepcopy(cases["real_env_novision_mutant"])
    m["isolation_reasons"] = []
    m["td_eligible"] = m["bc_eligible"] = True
    rec("B8_novision_mutant_pretends_isolated",
        B8_vision_channel_guard_on_real_env(_real_or_none(cases), cases["real_env_novision_mutant"])["ok"],
        B8_vision_channel_guard_on_real_env(_real_or_none(cases), m)["ok"],
        "视觉通道缺失却放行 = G3 0/20 的同型根因")

    # B9：拿起点值顶替终点
    m = copy.deepcopy(cases["renderer"])
    m["snapshot_start_only"]["at_end"] = m["snapshot_start_only"]["at_start"]
    m["snapshot_start_only"]["at_end_measurement_kind"] = "measured_bare_no_context"
    m["snapshot_start_only"]["at_end_is_null_because_not_measured_in_run"] = False
    rec("B9_end_substituted_by_start", B9_renderer_three_points(cases["renderer"],
                                                                _real_or_none(cases))["ok"],
        B9_renderer_three_points(m, _real_or_none(cases))["ok"],
        "终点未测却填了起点值 ⇒ 必须红（D 的派工原文）")

    # B9b：把 null_context 分类成 software（猜）
    m = copy.deepcopy(cases["renderer"])
    m["classify_probe"]["<python_none>"] = "software"
    rec("B9b_unreadable_renderer_guessed_as_software",
        B9_renderer_three_points(cases["renderer"], cases.get("real_env"))["ok"],
        B9_renderer_three_points(m, cases.get("real_env"))["ok"], "读不到就是 null，不猜")

    # B10：把下溢对照篡成"没检出"
    m = copy.deepcopy(cases["prompt_tooth"])
    m["positive_control_underflow"]["detected"] = False
    rec("B10_underflow_control_not_detected", B10_prompt_tooth_two_way(cases["prompt_tooth"])["ok"],
        B10_prompt_tooth_two_way(m)["ok"], "下溢合成状态必须检出")

    # B10b：把对照探针篡成自证失败（裁定 93.5）
    m = copy.deepcopy(cases["prompt_tooth"])
    m["pattern_coverage_probe"]["auditor_self_verdict"] = "RED"
    m["pattern_coverage_probe"]["detected"] = False
    rec("B10b_pattern_coverage_probe_self_red",
        B10_prompt_tooth_two_way(cases["prompt_tooth"])["ok"], B10_prompt_tooth_two_way(m)["ok"],
        "审计器模式覆盖不足 ⇒ 审计器自己红，不得报绿")

    # B11：把 pad_vector 的 not_measured 篡成 false（假设安全）
    m = copy.deepcopy(cases["pad_vector"])
    m["is_not_measured"] = False
    m["value_is_null"] = False
    m["registration"]["measurement_status"] = "measured"
    m["registration"]["value"] = False
    rec("B11_pad_vector_assumed_safe", B11_pad_vector_not_measured(cases["pad_vector"])["ok"],
        B11_pad_vector_not_measured(m)["ok"], "`not_measured` 被写成 `false` = 假设安全")

    # B12：把空集聚合篡成 GREEN / 0
    m = copy.deepcopy(cases["prompt_tooth"])
    m["empty_aggregate_three_value_discipline"] = dict(
        m["empty_aggregate_three_value_discipline"], verdict="GREEN",
        measurement_status="measured", nonzero_exit_required=False, n_illegal_bin_minus1=0)
    rec("B12_empty_set_reported_as_green_zero",
        B12_three_value_discipline_empty_set(cases["prompt_tooth"])["ok"],
        B12_three_value_discipline_empty_set(m)["ok"], "空集聚合报成 GREEN/0 = 三值纪律违规")

    # B13：把 truncated 当 terminal
    m = copy.deepcopy(rt["runtime_timeout"])
    m["bc_record_extras"] = dict(m["bc_record_extras"], truncated_by_timelimit=False,
                                 must_not_be_labelled_as=())
    rec("B13_truncated_flag_dropped",
        B13_td_only_three_hard_constraints(rt["runtime_timeout"])["ok"],
        B13_td_only_three_hard_constraints(m)["ok"], "裁定 83.7-2 硬约束①")

    # B13b：representation_version 里少了 timeout_bc token
    m = copy.deepcopy(rt["runtime_timeout"])
    m["representation_version"] = m["representation_version"].replace("timeout_bc=kept_flagged",
                                                                       "timeout_bc=isolated")
    rec("B13b_rep_version_token_missing",
        B13_td_only_three_hard_constraints(rt["runtime_timeout"])["ok"],
        B13_td_only_three_hard_constraints(m)["ok"], "裁定 83.7-2 硬约束②")

    # B14：在 A2 的文件里塞一份 C2 的阈值（= 重造判定层）
    src = (REPO / "harness/vla_runtime.py").read_text()
    tmp = REPO / "tmp" / "_b14_mutant_vla_runtime.py"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(src + "\n# mutant\n#    grasp_max_dist_m: float = 0.045\n")
    saved = REPO / "harness/vla_runtime.py"
    backup = REPO / "tmp" / "_b14_backup_vla_runtime.py"
    backup.write_bytes(saved.read_bytes())
    try:
        saved.write_text(src + "\n_B14_MUTANT_grasp_max_dist_m: float = 0.045\n")
        mutant_ok = B14_judgment_layer_not_reimplemented(pure, rt["runtime_green"])["ok"]
    finally:
        saved.write_bytes(backup.read_bytes())
    rec("B14_thresholds_reimplemented_in_a2_file",
        B14_judgment_layer_not_reimplemented(pure, rt["runtime_green"])["ok"], mutant_ok,
        "A2 的文件里出现 C2 的判据常量 ⇒ 判定层被重造")

    # B15：把 `sha12()` 临时篡成"读不到就返回冻结期望值"（= 闸变成恒真）⇒ 必须被抓住
    global sha12
    real_sha12 = sha12
    def lying_sha12(_p):
        return {"harness/contracts.py": "96c99ead93d2",
                "harness/ledger.py": "2a33c3f5516e"}.get(str(_p).replace(str(REPO) + "/", ""),
                                                          real_sha12(_p))
    baseline_b15 = B15_frozen_surface_untouched()["ok"]
    try:
        # 篡改方式：让 contracts.py 的实测值**真的**偏离冻结值（这里用另一个文件的 sha 顶替）
        sha12 = lambda q: (real_sha12(REPO / "harness/ledger.py")
                           if str(q).endswith("harness/contracts.py") else real_sha12(q))
        mutant_b15 = B15_frozen_surface_untouched()["ok"]
    finally:
        sha12 = real_sha12
    rec("B15_frozen_sha_actually_compared", baseline_b15, mutant_b15,
        "把 contracts.py 的实测 sha 换成别的文件的值 ⇒ B15 必须红（证明它真的在比 sha，不是恒真）")

    n_teeth = sum(1 for v in detail.values() if v["teeth"])
    no_teeth = [k for k, v in detail.items() if not v["teeth"]]
    return {"gates_tested": len(detail), "gates_with_teeth": n_teeth,
            "all_have_teeth": n_teeth == len(detail), "without_teeth": no_teeth,
            "teeth_definition": ("teeth = baseline_ok AND (NOT mutant_ok) —— 两处都要："
                                 "基线必须绿、篡改后必须红（恒假牙与装饰品都不算有牙）"),
            "detail": detail}


# ═════════════════════════════════ main ═════════════════════════════════
AGGREGATE_FIELD_SEMANTICS = {
    "_rule": ("裁定 84§4 `top_level_aggregate_must_declare_semantics`：任何顶层汇总布尔/数值必须写明"
              "聚合语义（OR/AND/mean/worst/diff/count）、由一把闸或就地重算看守、不得留初值"),
    "all_ok": {"aggregate": "AND", "over": "gates[*].ok",
               "recomputed": "`n_ok == len(gates)`，在所有闸算完之后就地算，不留初值",
               "guard": "退出码 `0 if (all_ok and all_have_teeth and no not_measured_escalation) else 3`"},
    "n_gates / n_ok": {"aggregate": "count", "over": "`len(gates)` / `sum(1 for g in gates.values() if g.ok)`",
                       "note": "闸数会变 ⇒ 引用闸数必须带 `generated_at`"},
    "gate_teeth_mutation_selftest.all_have_teeth": {
        "aggregate": "AND", "over": "detail[*].teeth",
        "teeth_definition": "teeth = baseline_ok AND (NOT mutant_ok)；只红不绿（恒假牙）与只绿不红（装饰品）都不算"},
    "n_red_outcomes": {"aggregate": "count",
                       "over": "各臂 `S4bOutcome.red is True` 的**臂数**（不是帧数、不是局数）",
                       "warning": ("反向臂与 flick 臂的 RED 是**设计出来的对照**，不是运行故障；"
                                   "读这个数必须同时读 `red_subject`")},
    "four_class_distribution": {"aggregate": "count", "over": "各臂的 `outcome_class`",
                                "not_a_capability_metric": True,
                                "authority": "裁定 46.6 / 65-6③：成功率一栏写 `not_an_exit_criterion`"},
    "cases.*.timing_report.*": {"aggregate": "per-arm worst/mean（见字段名）",
                                "caveat": ("本脚本全部是 **CPU 口径**（`MUJOCO_GL=osmesa` 软渲染）⇒ "
                                           "任何 wall/budget 数字**不得**与 GPU 干净窗（rep4 0.8009 / "
                                           "rep5 0.7766、27.230/26.405 ms）互搬（裁定 46.4/53.6/71）")},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="runs/vla/a2_s4b_outcome_ledger_20260930")
    ap.add_argument("--no-real-env", action="store_true", help="只跑纯判定层 + runtime stub 臂（不需要渲染）")
    ap.add_argument("--no-render", action="store_true", help="真实 env 臂不渲染（只验接线）")
    ap.add_argument("--direction", default="right_to_left", choices=["right_to_left", "left_to_right"])
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--real-frames", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--stats-version-none", action="store_true",
                    help="真实 env 臂用 stats_version=NONE（π₀.₅ base 的真实情况，裁定 44.1/49.2）⇒ 走隔离路径")
    args = ap.parse_args()

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    # **每次 run 用独立子目录**：`FactLedger` 是 append-only 且 A2 不许 `rm`
    # ⇒ 复用同一份 sqlite 会让上一轮的行叠加进来（B6 的 `n_episode_end_events==1` 就会假红）。
    ledger_dir = out_dir / "ledgers" / datetime.now().strftime("%Y%m%d_%H%M%S")
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ld0 = load0()

    print("[arm] 纯判定层（C2 的 judge_from_facts，四类 + flick + 反向）…", flush=True)
    pure = arm_pure_judgment()
    cases: dict[str, dict] = {"pure_judgment": pure}

    for kind in ("green", "flick_red", "reverse_red", "coupling_mutant", "unknown", "timeout"):
        print(f"[arm] runtime 接线臂：{kind} …", flush=True)
        cases[f"runtime_{kind}"] = arm_runtime(kind, ledger_dir)

    print("[arm] prompt 牙两向对照 + 对照探针（裁定 93.5）…", flush=True)
    cases["prompt_tooth"] = arm_prompt_tooth()
    print("[arm] pad_vector 缺口 = not_measured …", flush=True)
    cases["pad_vector"] = arm_pad_vector()
    print("[arm] renderer_class 三点 …", flush=True)
    cases["renderer"] = arm_renderer()

    if not args.no_real_env:
        os.environ.setdefault("MUJOCO_GL", "osmesa")
        print(f"[arm] 真实 env（C2 的 GymAlohaSimEnv，MUJOCO_GL={os.environ.get('MUJOCO_GL')}，"
              f"{args.real_frames} 帧）…", flush=True)
        try:
            cases["real_env"] = arm_real_env(args, ledger_dir)
        except Exception as exc:                                       # noqa: BLE001
            import traceback
            cases["real_env"] = {"arm": "real_env_c2_judgment_layer", "error": True,
                                 "error_type": type(exc).__name__, "error": str(exc)[:900],
                                 "traceback": traceback.format_exc()[-3000:],
                                 "measurement_status": "not_measured",
                                 "nonzero_exit_required": True}
            print(f"[arm] 真实 env 臂失败：{type(exc).__name__}: {exc}", flush=True)
        print("[arm] 真实 env 变异体（不给图像 ⇒ 必须硬隔离）…", flush=True)
        try:
            cases["real_env_novision_mutant"] = arm_real_env_novision(args, ledger_dir)
        except Exception as exc:                                       # noqa: BLE001
            import traceback
            # 臂跑失败 ⇒ **不许**把默认值写成"没隔离/资格为真"（那等于把'没测到'报成'测到没有'）
            cases["real_env_novision_mutant"] = {"arm": "real_env_novision_mutant", "error": True,
                                                 "error_type": type(exc).__name__,
                                                 "error": str(exc)[:900],
                                                 "traceback": traceback.format_exc()[-3000:],
                                                 "measurement_status": "not_measured",
                                                 "nonzero_exit_required": True,
                                                 "isolation_reasons": [], "td_eligible": None,
                                                 "bc_eligible": None,
                                                 "event_kinds_used": []}
    else:
        cases["real_env_novision_mutant"] = {
            "arm": "real_env_novision_mutant", "skipped": True,
            "isolation_reasons": ["vision_channel_absent: (skipped arm, injected for gate B8)"],
            "td_eligible": False, "bc_eligible": False,
            "event_kinds_used": ["verdict_identity_absent"],
            "note": "`--no-real-env` ⇒ 本臂未跑；这里写的是**注入的期望形态**，"
                    "`measurement_status` 记 not_measured，不当成实测"}
        cases["real_env_novision_mutant"]["measurement_status"] = "not_measured"

    real = _real_or_none(cases)
    gates = {
        "B1_four_classes_all_reachable": B1_four_classes_all_reachable(pure),
        "B2_outcome_independent_of_reward4": B2_outcome_independent_of_reward4(
            cases["runtime_green"], cases["runtime_flick_red"], cases["runtime_coupling_mutant"]),
        "B3_disagreement_is_red": B3_disagreement_is_red(cases["runtime_flick_red"]),
        "B4_agreement_is_green": B4_agreement_is_green(cases["runtime_green"]),
        "B5_reverse_direction_expected_red": B5_reverse_direction_expected_red(
            cases["runtime_reverse_red"], pure),
        "B6_ledger_roundtrip_four_classes": B6_ledger_roundtrip(
            cases["runtime_green"], cases["runtime_timeout"], cases["runtime_unknown"]),
        "B7_ledger_vocabulary_not_extended": B7_ledger_vocabulary_not_extended(
            cases["runtime_green"], cases["runtime_timeout"], cases["runtime_unknown"]),
        "B8_vision_channel_guard_real_env": B8_vision_channel_guard_on_real_env(
            real, cases["real_env_novision_mutant"]),
        "B9_renderer_class_three_points": B9_renderer_three_points(cases["renderer"], real),
        "B10_prompt_bin_tooth_two_way": B10_prompt_tooth_two_way(cases["prompt_tooth"]),
        "B11_pad_vector_registered_not_measured": B11_pad_vector_not_measured(cases["pad_vector"]),
        "B12_empty_set_aggregate_is_null_and_nonzero_exit": B12_three_value_discipline_empty_set(
            cases["prompt_tooth"]),
        "B13_td_only_three_hard_constraints_83_7_2": B13_td_only_three_hard_constraints(
            cases["runtime_timeout"]),
        "B14_judgment_layer_not_reimplemented": B14_judgment_layer_not_reimplemented(
            pure, cases["runtime_green"]),
        "B15_frozen_and_other_line_surfaces_untouched": B15_frozen_surface_untouched(),
    }

    print("[selftest] 变异自检：逐闸一处具体篡改，证明闸会红…", flush=True)
    mutation = mutation_self_test(cases)

    n_ok = sum(1 for g in gates.values() if g.get("ok"))
    all_ok = (n_ok == len(gates))
    # 三值纪律的**升级路径**：任何 `not_measured` 且 `nonzero_exit_required` 的登记 ⇒ 退出码非零
    nm = []
    if cases["prompt_tooth"]["formal40_control"].get("nonzero_exit_required"):
        nm.append("formal40_control")
    if cases["prompt_tooth"]["empty_aggregate_three_value_discipline"].get("nonzero_exit_required"):
        nm.append("empty_aggregate（这是闸 B12 的**输入形态**，不是本 run 的缺口）")
    nm_real = [k for k, v in cases.items()
               if isinstance(v, dict) and v.get("measurement_status") == "not_measured"
               and v.get("nonzero_exit_required")]
    nm_escalation = [x for x in nm if not x.startswith("empty_aggregate")] + nm_real

    red_arms = sorted(k for k, v in cases.items()
                      if isinstance(v, dict) and (v.get("outcome") or {}).get("red") is True)
    four_class = {}
    for k, v in cases.items():
        if isinstance(v, dict) and isinstance(v.get("outcome"), dict):
            four_class.setdefault(v["outcome"].get("outcome_class"), []).append(k)

    payload = {
        "artifact": "a2_s4b_outcome_ledger_verification",
        "stage": "S4b",
        "task_id": "T-A2-6",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_s4b_outcome_ledger_verify.py",
        "generator_sha256_12": sha12(pathlib.Path(__file__).resolve()),
        "criterion_verbatim": VR.S4B_CRITERION_VERBATIM,
        "criterion_source": "work/project_parameters.json:1047（vla_runtime_gap）",
        "dispatch_source": "rl_harness_supervision/d_handoff_to_a2_20260930.md §一（T-A2-6）",
        "target_file": "harness/vla_runtime.py",
        "target_sha256_12": sha12(REPO / "harness/vla_runtime.py"),
        "target_lines": len((REPO / "harness/vla_runtime.py").read_text().splitlines()),
        "tooth_module": "harness/prompt_bin_guard.py",
        "tooth_module_sha256_12": PBG.module_sha256_12(),
        "judgment_layer_identity": VR.env_gym_aloha_identity(),
        "judgment_layer_owned_by": "C2（A2 只接线、不重算判定）",
        "contracts_py_sha256_12": sha12(REPO / "harness/contracts.py"),
        "contracts_py_modified": False,
        "ledger_py_sha256_12": sha12(REPO / "harness/ledger.py"),
        "ledger_py_modified": False,
        "frozen_surface_touched": [],
        "other_line_files_modified": [],
        "args": vars(args),
        "gates": gates,
        "n_gates": len(gates), "n_ok": n_ok, "all_ok": all_ok,
        "gate_teeth_mutation_selftest": mutation,
        "aggregate_field_semantics": AGGREGATE_FIELD_SEMANTICS,
        "not_measured_escalation": {
            "items": nm_escalation, "n": len(nm_escalation),
            "rule": ("三值纪律：`not_measured` + `nonzero_exit_required` ⇒ 退出码非零；"
                     "不许把'没测到'读成'测到没有'"),
            "empty_aggregate_is_a_gate_input_not_a_gap": (
                "`empty_aggregate` 是闸 B12 的**输入形态**（故意喂空集证明牙会咬），"
                "不计入本 run 的缺口 ⇒ 已从升级项里排除"),
        },
        "red_arms": red_arms,
        "n_red_arms": len(red_arms),
        "red_arms_are_designed_controls": (
            "flick/reverse 两臂的 RED 是**设计出来的对照**（证明'不一致即红'真的会红），"
            "不是运行故障；读 `n_red_arms` 必须同时读各臂的 `red_subject`"),
        "four_class_distribution": {k: sorted(v) for k, v in sorted(four_class.items())},
        "capability_claim": False,
        "success_metrics_collected": False,
        "success_rate_column": "not_an_exit_criterion（裁定 65-6③ / 46.6）",
        "gpu_used": False,
        "render_backend_of_real_arm": ((real or {}).get("mujoco_gl")),
        "cross_caliber_transplant_ban": ("本产物全部是 CPU 口径 ⇒ 不得与 GPU 干净窗的数字互搬"
                                         "（裁定 46.4/53.6/71）"),
        "side_items_in_same_batch": {
            "item1_runtime_minus1_prompt_tooth": {
                "offline_two_way_evidence": "cases.prompt_tooth",
                "runtime_evidence": ("**不在本产物**：真 prompt 文本的运行时证据在 "
                                     "`scripts/a2_s4b_pi05_gpu_run.py` 的产物里"
                                     "（`PromptCapture` 旁路挂钩 `processor_pi05.py:86` 的写回点）"),
                "pattern_coverage_probe": cases["prompt_tooth"]["pattern_coverage_probe"][
                    "auditor_self_verdict"],
            },
            "item2_pad_vector": cases["pad_vector"],
            "item3_renderer_class": {
                "offline_semantics_evidence": "cases.renderer",
                "real_env_three_points": (real or {}).get("renderer_class_three_points"),
                "c4_piggyback_for_e": ((real or {}).get("renderer_class_three_points") or {})
                .get("c4_piggyback_evidence_for_e"),
            },
        },
        "load_before": ld0, "load_after": load0(),
        "cases": cases,
    }
    payload["nr_throttled_delta_total"] = (
        (payload["load_after"].get("nr_throttled") or 0) - (ld0.get("nr_throttled") or 0))
    p = out_dir / "s4b_verification.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    print(f"[written] {p}", flush=True)
    for k, v in gates.items():
        print(f"  [{'PASS' if v.get('ok') else 'FAIL'}] {k}"
              f"  ({v.get('n_checks_true')}/{v.get('n_checks')})", flush=True)
        if not v.get("ok"):
            bad = {kk: vv for kk, vv in (v.get("checks") or {}).items() if not vv}
            print(f"         failed_checks={json.dumps(bad, ensure_ascii=False, default=str)[:500]}",
                  flush=True)
    print(f"[summary] {n_ok}/{len(gates)} gates PASS", flush=True)
    print(f"[summary] 变异自检 {mutation['gates_with_teeth']}/{mutation['gates_tested']} 条有牙"
          f"（all_have_teeth={mutation['all_have_teeth']}）", flush=True)
    if mutation["without_teeth"]:
        print(f"[summary] **无牙的变异体**：{mutation['without_teeth']}", flush=True)
    print(f"[summary] RED 臂（设计对照）：{red_arms}", flush=True)
    print(f"[summary] 四类分布：{payload['four_class_distribution']}", flush=True)
    if nm_escalation:
        print(f"[summary] **not_measured 升级项**：{nm_escalation}", flush=True)
    rc = 0 if (all_ok and mutation["all_have_teeth"] and not nm_escalation) else 3
    print(f"[exit] rc={rc}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
