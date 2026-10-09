#!/usr/bin/env python3
"""**标准同步执行通路（裁定 95.3-④）出口判据** —— 人算手算表 + 12 道带牙的闸。

## 为什么有这个脚本（派工原文，不重新解释）
`rl_harness_supervision/d_handoff_to_a2_20260930.md` 补单二-§二：「把 S4b 的准备收到
**『标准同步执行通路能跑』**这一件 —— 它是第 1–3 步的**共同前置**，也是本轮唯一必须新增的
运行时能力」；`work/project_parameters.json` rev20 `prerequisite_before_step_1` 同义。
裁定 95.3-④ 的判据原文：「现运行时 `execution_mask = bc_mask = [0,0,1,1]`，模型输出 50 步而
**只执行 idx 25–49**、帧 0–24 是 prime hold。**问题不在时间对齐、在状态对齐**……
⇒ **第 1–2 步一律用标准同步动作块执行**；第 3 步才做配对比较；**两种执行的数字不得互搬**。」

`harness/vla_runtime.py` 已落两个 `exec_mode`：
* `harness_second_half`（**默认**，= v4 附录二的 C/E/D 调度：执行 idx `[n,2n)`、帧 `0..n-1` 是 prime hold）
* `standard_sync`（裁定 95.3-④：执行 idx `[0,n)`、**无** priming、推理阻塞控制环）

本脚本验的是**后者的语义**、**两者不得互搬**（`exec=` token 是机器判据），以及
**默认路径零漂移**（G2 直接拿 S4a 的 `HAND_TABLE` 与原闸函数比，不抄一份）。

## 手算表 A（`n_replan=2, H=4, prime_mode="none", exec_mode="standard_sync"`，8 帧）
第 `g` 代在 `t_g = 2g` 发请求，**同一帧立刻执行本代 idx 0**（推理阻塞 ⇒ 仿真时间在推理期间
不推进）；`idx = f - t_g = f mod 2`；stub 策略的动作口径 = `[100g + idx, -(100g + idx)]`。

| abs_frame | 请求发生在这一帧？ | source | chunk(gen) | chunk_index | 执行的动作 | 人算依据 |
|---|---|---|---|---|---|---|
| 0 | 是（g=0） | **policy** | **0** | **0** | `[0, -0]`     | `idx = 0 - t_0 = 0 ∈ [0,n)` |
| 1 | —         | policy     | 0       | **1** | `[1, -1]`     | `idx = 1 - 0 = 1` |
| 2 | 是（g=1） | policy     | **1**   | **0** | `[100, -100]` | `idx = 2 - t_1 = 2-2 = 0` |
| 3 | —         | policy     | 1       | **1** | `[101, -101]` | `idx = 3 - 2 = 1` |
| 4 | 是（g=2） | policy     | **2**   | **0** | `[200, -200]` | `idx = 4 - t_2 = 4-4 = 0` |
| 5 | —         | policy     | 2       | **1** | `[201, -201]` | `idx = 5 - 4 = 1` |
| 6 | 是（g=3） | policy     | **3**   | **0** | `[300, -300]` | `idx = 6 - t_3 = 6-6 = 0` |
| 7 | —         | policy     | 3       | **1** | `[301, -301]` | `idx = 7 - 6 = 1` |

⇒ 请求数 = **4**；**hold 帧 = 0**；`expired` = **0**；`execution_mask = bc_mask = [1,1,0,0]`。
**对照（同一 stub / 同一 seed / 同一 n、H，只换 `exec_mode`）**：`harness_second_half` 的
f0/f1 = **prime hold**、f2/f3 执行的是**第 0 代 idx 2/3** ⇒ 表 = S4a 的 `HAND_TABLE`、
mask = `[0,0,1,1]`。**两张表在 f0–f3 上逐格不同 ⇒ 这不是重命名，是换了执行的索引段。**

## 手算表 B（`n_replan=4 = H=4`，只有 `standard_sync` 合法；8 帧）
`g = f//4`、`t_g = 4g`、`idx = f - t_g`；`harness_second_half` 在这一档**必须拒绝构造**
（v4 附录一 :103 的 `H ≥ 2n` 不成立）。

| abs_frame | source | gen | idx | 动作 |
|---|---|---|---|---|
| 0–3 | policy | **0** | 0,1,2,3 | `[0,-0] [1,-1] [2,-2] [3,-3]` |
| 4–7 | policy | **1** | 0,1,2,3 | `[100,-100] [101,-101] [102,-102] [103,-103]` |

⇒ 请求数 = **2**；`execution_mask = bc_mask = [1,1,1,1]`（整个 chunk 都被执行）。

## 用法
    MUJOCO_GL=osmesa /root/venvs/pi05_sim/bin/python scripts/a2_standard_sync_exec_verify.py
    ... --no-real-env   # 只跑 stub 臂 ⇒ G11 = not_measured ⇒ **exit 3**（"通路能跑"没被证明）
**不占 GPU**（`gpu_used=false`；真实 env 臂走 `MUJOCO_GL=osmesa` 软渲染）。真模型臂属 S4b
（`scripts/a2_s4b_pi05_gpu_run.py`，上卡前须按裁定 94.9-1 的过渡协议申报 + `GPU_WINDOW.json`）。
**能力声明禁令（裁定 46）不变**：本脚本不产出任何 policy 指标；`capability_claim=false`、
`success_rate_column="not_an_exit_criterion"`。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import pathlib
import sys
from datetime import datetime
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness import vla_runtime as VR                                     # noqa: E402
from harness.contracts import EVENT_KINDS as CONTRACT_KINDS               # noqa: E402
from harness.ledger import (EVENT_KINDS as LEDGER_KINDS, EXECUTION_STATUS,  # noqa: E402
                            FRAME_SOURCES, FactLedger)

# 复用已验过的 stub 与手算表（**不重造**：两个位置各写一份 = 本仓已发生四次的事故形状）
sys.path.insert(0, str(REPO / "scripts"))
import a2_s4a_vla_runtime_verify as S4A                                   # noqa: E402
import a2_s4b_outcome_ledger_verify as S4B                                # noqa: E402

# ───────────────────────── 人算常量（**人写的，不是脚本算的**）─────────────────────────
# (abs_frame, source, lease_generation, chunk_index, action)
HAND_TABLE_STANDARD_SYNC = [
    (0, "policy", 0, 0, [0.0, -0.0]),
    (1, "policy", 0, 1, [1.0, -1.0]),
    (2, "policy", 1, 0, [100.0, -100.0]),
    (3, "policy", 1, 1, [101.0, -101.0]),
    (4, "policy", 2, 0, [200.0, -200.0]),
    (5, "policy", 2, 1, [201.0, -201.0]),
    (6, "policy", 3, 0, [300.0, -300.0]),
    (7, "policy", 3, 1, [301.0, -301.0]),
]
HAND_TABLE_N_EQ_H = [
    (0, "policy", 0, 0, [0.0, -0.0]),
    (1, "policy", 0, 1, [1.0, -1.0]),
    (2, "policy", 0, 2, [2.0, -2.0]),
    (3, "policy", 0, 3, [3.0, -3.0]),
    (4, "policy", 1, 0, [100.0, -100.0]),
    (5, "policy", 1, 1, [101.0, -101.0]),
    (6, "policy", 1, 2, [102.0, -102.0]),
    (7, "policy", 1, 3, [103.0, -103.0]),
]
MASK_STANDARD_SYNC_N2_H4 = [1, 1, 0, 0]      # 执行的是 idx [0,n) ⇒ 前两格
MASK_HARNESS_N2_H4 = [0, 0, 1, 1]            # 裁定 95.3-④ 引用的现状（= S4a 的表）
MASK_N_EQ_H = [1, 1, 1, 1]                   # n=H ⇒ 整个 chunk 都被执行
N_REQUESTS_N2 = 4                            # 8 帧 / n=2
N_REQUESTS_N4 = 2                            # 8 帧 / n=4

BAND_ARTIFACTS = [                            # 权威延迟带产物（裁定 84§6 / params `timing`）
    "runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep4.json",
    "runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep5.json",
]
BAND_VALUES_QUOTED_FOR_SCOPE_ONLY = {"rep4_budget_fraction": 0.8009, "rep5_budget_fraction": 0.7766,
                                     "rep4_ms_per_ctrl_step": 27.230, "rep5_ms_per_ctrl_step": 26.405}


def sha12(p: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except Exception:                                                 # noqa: BLE001
        return None


# ───────────────── 变异体：一个**谎报槽位**的策略（G8 的对象）─────────────────
class SlotLiarPolicy:
    """把 `slot_e` 报成 `(1,2,3)`（既不是 `[0,n)` 也不是 `[n,2n)`）⇒ 验「**槽位归属是运行时的
    语义、不是策略的自述**」。裁定 95.3-④ 落地时在 `_request_and_commit` 里**重盖**槽位
    （`slots_restamped_by_runtime=True`），所以这个谎报对**执行行为**必须零影响。
    """

    def __init__(self, inner, *, n_replan: int = 2):
        self._inner = inner
        self._n = n_replan
        self.chunk_size = inner.chunk_size
        self.policy_version = inner.policy_version
        self.stats_version = inner.stats_version

    @property
    def calls(self) -> int:
        return self._inner.calls

    def reset(self, seed: int) -> None:
        self._inner.reset(seed)

    def select_chunk(self, obs) -> VR.ActionChunk:
        c = self._inner.select_chunk(obs)
        H = c.chunk_size
        lied = tuple(range(1, min(H, 4)))                 # (1,2,3) —— 故意与两种语义都不符
        return VR.ActionChunk(**{**c.__dict__, "slot_c": (0,), "slot_e": lied,
                                 "slot_d": tuple(i for i in range(H) if i not in (0,) + lied)})


# ───────────────────────── stub 臂（可手算，不需要 mujoco）────────────────────────
def run_case(*, exec_mode: str = VR.EXEC_MODE_STANDARD_SYNC,
             prime_mode: str = VR.PRIME_MODE_NONE,
             n_replan: int = 2, chunk_size: int = 4, n_frames: int = 8,
             slow_factor: float = 0.0, stats_version: str = "s2_stats@stub1234",
             slot_liar: bool = False, ledger_path: pathlib.Path | None = None,
             env_horizon: int | None = None, seed: int = 1000,
             episode_id: str = "ss-ep0") -> dict:
    """跑一条**可手算**的短轨迹。默认 `env_horizon = n_frames + 4` ⇒ 不触发 TimeLimit 截断
    （`terminal_kind="none"`），这样 mask/eligible 的读数不被 timeout 口径混进来。
    """
    horizon = (env_horizon if env_horizon is not None else n_frames + 4)
    env = S4A.StubEnv(n_frames=horizon)
    pol: Any = S4A.StubPolicy(stats_version=stats_version, slow_factor=slow_factor)
    pol.chunk_size = chunk_size
    if slot_liar:
        pol = SlotLiarPolicy(pol, n_replan=n_replan)
    ledger = None
    if ledger_path is not None:
        if ledger_path.exists():                    # 不用 rm ⇒ 旧账本改名留档（裁定 35.1）
            ledger_path.rename(ledger_path.with_suffix(
                f".before_{datetime.now().strftime('%H%M%S_%f')}.sqlite"))
        ledger = FactLedger(ledger_path)
    rt = VR.ChunkedVlaRuntime(pol, env, episode_id=episode_id, goal_id="A_to_B", epoch=7,
                              n_replan=n_replan, dt_s=0.034, prime_mode=prime_mode,
                              exec_mode=exec_mode, ledger=ledger,
                              shim_sha256_12="stub_shim_1234")
    rt.reset(seed=seed)
    steps: list[dict] = []
    tv = None
    err = None
    ended = "none"
    try:
        for _ in range(n_frames):
            r = rt.step()
            steps.append({"abs_frame": r.abs_frame, "source": r.source,
                          "execution_status": r.execution_status, "chunk_index": r.chunk_index,
                          "lease_generation": r.lease_generation, "late_choice": r.late_choice,
                          "action": [float(x) for x in r.action]})
            if r.truncated:
                ended = "timeout"
                break
            if r.terminated:
                ended = "terminated"
                break
        tv = rt.finalize(ended, reward=0.0)
    except Exception as exc:                                        # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    rep = rt.representation_version
    act_rows = [r for r in rt.frame_facts if r["execution_status"] == "activated"]
    out = {
        "arm": f"stub:{exec_mode}:n{n_replan}:H{chunk_size}"
               f"{':liar' if slot_liar else ''}{':slow' if slow_factor else ''}",
        "exec_mode_requested": exec_mode, "prime_mode_requested": prime_mode,
        "steps": steps, "error": err, "n_requests": pol.calls, "terminal_kind": ended,
        "representation_version": rep,
        "exec_caliber": VR.exec_caliber_of_representation_version(rep),
        "manifest_caliber": rt.manifest_caliber(),
        "contract_event_kinds": [k for e in rt.contract_events if (k := getattr(e, "kind", ""))],
        "schedule_event_kinds": [e["kind"] for e in rt.schedule_events],
        "timing_report": rt.timing_report(),
        "frame_facts": rt.frame_facts,
        "late_records": rt.late_records,
        "sync_overload_records": rt.sync_overload_records,
        "isolation_reasons": rt.isolation_reasons,
        "n_hold_frames": sum(1 for s in steps if s["source"] == "hold"),
        "n_policy_frames": sum(1 for s in steps if s["source"] == "policy"),
        "executed_indices": sorted({r["chunk_index"] for r in act_rows
                                    if r["chunk_index"] is not None}),
        "committed_chunks": {str(g): {"slot_c": list(c.slot_c), "slot_e": list(c.slot_e),
                                      "slot_d": list(c.slot_d),
                                      "slots_restamped_by_runtime": c.slots_restamped_by_runtime,
                                      "exec_mode": c.exec_mode,
                                      "created_at_frame": c.created_at_frame,
                                      "inference_wall_s": c.inference_wall_s,
                                      "deadline_s": c.deadline_s}
                             for g, c in sorted(rt.chunks.items())},
        "training_view": (None if tv is None else {
            "td_eligible": tv.td_eligible, "bc_eligible": tv.bc_eligible,
            "execution_mask": list(tv.execution_mask), "bc_mask": list(tv.bc_mask),
            "terminal_kind": tv.terminal_kind, "isolation_reasons": list(tv.isolation_reasons)}),
        "vocabularies": {"contract": sorted(CONTRACT_KINDS), "ledger": sorted(LEDGER_KINDS),
                         "frame_sources": sorted(FRAME_SOURCES),
                         "execution_status": sorted(EXECUTION_STATUS)},
    }
    if ledger is not None:
        out["ledger"] = {"path": str(ledger_path), "stats": ledger.stats(),
                         "n_frames_rows": len(ledger.frames(episode_id=episode_id)),
                         "n_event_rows": len(ledger.events(episode_id=episode_id))}
        ledger.close()
    return out


def try_construct(**kw) -> dict:
    """互锁闸用：构造必须**抛**（不是告警）。返回实测到的异常类型与消息。"""
    env = S4A.StubEnv(n_frames=12)
    pol = S4A.StubPolicy()
    pol.chunk_size = kw.pop("chunk_size", 4)
    try:
        VR.ChunkedVlaRuntime(pol, env, episode_id="interlock", goal_id="A_to_B",
                             shim_sha256_12="stub_shim_1234", **kw)
        return {"raised": False, "exc_type": None, "message": None}
    except Exception as exc:                                        # noqa: BLE001
        return {"raised": True, "exc_type": type(exc).__name__, "message": str(exc)[:600]}


# ───────────────────────── 真实 env 臂（G11 = 「通路能跑」的验收）─────────────────────
def run_real_case(args, ledger_dir: pathlib.Path) -> dict:
    """真实 `gym_aloha/AlohaTransferCube-v0`（C2 的 `GymAlohaJudgedAdapter`）+ 真实 ledger
    + **C2 的四类判定**，全程 `exec_mode=standard_sync`。

    **判定层不归 A2**：`outcome_class` 只来自 `harness/env_gym_aloha.py`（579 ln `6c4d71eb732e`）
    的 `judge_from_facts()`，本脚本一条都不重算（复用 S4b 已验的接线，见 B14）。
    **不占 GPU**：`MUJOCO_GL=osmesa` 软渲染 ⇒ 本臂的任何 wall/budget 数字**不得**与 GPU 干净窗
    （rep4 0.8009 / rep5 0.7766）互搬（裁定 46.4 / 53.6 / 71）。
    """
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    ep_id = f"ss-real-{args.direction}"
    ledger_path = ledger_dir / "ledger_standard_sync_real_env.sqlite"
    if ledger_path.exists():
        ledger_path.rename(ledger_path.with_suffix(
            f".before_{datetime.now().strftime('%H%M%S_%f')}.sqlite"))
    ledger = FactLedger(ledger_path)
    ad = VR.GymAlohaJudgedAdapter(direction=args.direction, image_size=args.image_size,
                                  render=not args.no_render)
    n = VR.MAINLINE_N_REPLAN
    policy = S4B.HoldPolicy(ad, n_replan=n, stats_version="s4b_test_stats@offline_arm")
    rt = VR.ChunkedVlaRuntime(policy, ad, episode_id=ep_id, goal_id=ad.goal_id, epoch=0,
                              n_replan=n, prime_mode=VR.PRIME_MODE_NONE,
                              exec_mode=VR.EXEC_MODE_STANDARD_SYNC, ledger=ledger,
                              shim_sha256_12=ad.jenv.timing.get("shim_sha256_12", "unspecified"),
                              max_episode_steps=ad.max_episode_steps)
    rt.reset(seed=args.seed)
    n_frames = min(int(args.real_frames), ad.max_episode_steps)
    per_frame = []
    err = None
    try:
        for _ in range(n_frames):
            sr = rt.step()
            per_frame.append({"abs_frame": sr.abs_frame, "source": sr.source,
                              "execution_status": sr.execution_status,
                              "chunk_index": sr.chunk_index,
                              "lease_generation": sr.lease_generation,
                              "outcome_class": sr.info.get("outcome_class"),
                              "env_reward": sr.info.get("env_reward")})
    except Exception as exc:                                        # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    ad.measure_renderer_at_end()
    out = (rt.finalize_from_env_judgment(ad, ledger=ledger) if err is None else None)
    rt_roundtrip = VR.s4b_outcome_from_ledger(ledger, episode_id=ep_id)
    rep = rt.representation_version
    tv = (out.training_view if out is not None else None)
    res = {
        "arm": "real_env_standard_sync_end_to_end",
        "episode_id": ep_id, "direction": args.direction, "n_frames_driven": n_frames,
        "n_replan": n, "chunk_size": policy.chunk_size, "seed": args.seed,
        "error": err, "ledger_path": str(ledger_path),
        "mujoco_gl": os.environ.get("MUJOCO_GL"), "gpu_used": False,
        "renderer_class_three_points": ad.renderer_ledger.snapshot(),
        "env_manifest": ad.manifest(),
        "representation_version": rep,
        "exec_caliber": VR.exec_caliber_of_representation_version(rep),
        "manifest_caliber": rt.manifest_caliber(),
        "timing_report": rt.timing_report(),
        "per_frame_first6": per_frame[:6], "per_frame_last3": per_frame[-3:],
        "n_hold_frames": sum(1 for p in per_frame if p["source"] == "hold"),
        "n_policy_frames": sum(1 for p in per_frame if p["source"] == "policy"),
        "executed_indices": sorted({p["chunk_index"] for p in per_frame
                                    if p["chunk_index"] is not None}),
        "n_chunks_committed": len(rt.committed_generations),
        "expected_n_chunks": math.ceil(n_frames / n),
        "committed_chunks_slots": {str(g): {"slot_e": list(c.slot_e)[:3],
                                            "slot_e_len": len(c.slot_e),
                                            "slots_restamped_by_runtime": c.slots_restamped_by_runtime}
                                   for g, c in sorted(rt.chunks.items())},
        "sync_overload_records": rt.sync_overload_records,
        "late_records": rt.late_records,
        "isolation_reasons": list(rt.isolation_reasons),
        "outcome_class": (out.outcome_class if out is not None else None),
        "outcome": (out.as_dict() if out is not None else None),
        "ledger_roundtrip": rt_roundtrip,
        "n_episode_end_events": sum(1 for e in rt.schedule_events if e["kind"] == "episode_end"),
        "event_kinds_used": sorted({e["kind"] for e in rt.schedule_events}),
        "training_view": (None if tv is None else {
            "td_eligible": tv.td_eligible, "bc_eligible": tv.bc_eligible,
            "execution_mask_head": list(tv.execution_mask)[:n],
            "execution_mask_tail": list(tv.execution_mask)[n:],
            "terminal_kind": tv.terminal_kind}),
        "judgment_layer_identity": VR.env_gym_aloha_identity(),
        "caliber_note": ("**CPU 软渲染口径**（osmesa）⇒ wall/budget 数字不得与 GPU 干净窗互搬；"
                         "`renderer_class` 在 osmesa 下读不到 ⇒ 恒 `not_measured_no_gl_context`"),
    }
    # 四字段（裁定 95.3-①）在**真实通路**上跑一遍，证明它不是只在 stub 上成立
    ff = VR.four_fields_from_episode(
        outcome_class=res["outcome_class"],
        ledger_roundtrip_status=rt_roundtrip.get("measurement_status"),
        timing_measured=(rt.timing_report().get("wall_ms_per_ctrl_step") is not None),
        isolation_reasons=rt.isolation_reasons,
        ood_signals={"state_out_of_normalizer_range": None,
                     "action_clipped_at_ctrlrange": None,
                     "prompt_bins_saturated_255": None,
                     "prompt_bins_illegal_minus1": None,
                     "action_unit_mismatch_suspected": None},
        seed=args.seed, direction=args.direction,
        autonomous_success=(True if res["outcome_class"] == "success"
                            else (False if res["outcome_class"] in ("failure", "timeout") else None)),
        evidence={"exec_mode": VR.EXEC_MODE_STANDARD_SYNC,
                  "policy_is_deterministic_hold": True,
                  "note": "**不是能力测量**：策略是确定性 hold（裁定 46 禁令不变）"})
    res["four_fields"] = ff.as_dict()
    res["capability_stats_single_episode"] = VR.aggregate_capability_stats([ff])
    ledger.close()
    ad.close()
    return res


# ═══════════════════════════════ 闸（每条都要能被具体篡改打红）═══════════════════════════
def _cmp_hand_table(steps: list[dict], table: list[tuple], n_requests_expected: int,
                    n_requests_got: int) -> list[str]:
    diffs: list[str] = []
    if len(steps) != len(table):
        diffs.append(f"帧数 {len(steps)} != 手算表 {len(table)}")
    for i, (f, src, gen, idx, act) in enumerate(table):
        if i >= len(steps):
            break
        g = steps[i]
        if g["abs_frame"] != f:
            diffs.append(f"frame {i}: abs_frame {g['abs_frame']} != {f}")
        if g["source"] != src:
            diffs.append(f"frame {f}: source {g['source']!r} != {src!r}")
        if g["lease_generation"] != gen:
            diffs.append(f"frame {f}: lease_generation {g['lease_generation']} != {gen}")
        if g["chunk_index"] != idx:
            diffs.append(f"frame {f}: chunk_index {g['chunk_index']} != {idx}")
        if [round(x, 6) for x in (g["action"] or [])] != act:
            diffs.append(f"frame {f}: action {g['action']} != {act}")
        if src == "policy" and g["execution_status"] != "activated":
            diffs.append(f"frame {f}: policy 帧必须 activated，实为 {g['execution_status']}")
    if n_requests_got != n_requests_expected:
        diffs.append(f"请求数 {n_requests_got} != 手算 {n_requests_expected}")
    return diffs


def gate_g1_standard_sync_hand_table(res: dict) -> dict:
    """G1：**逐字段手核**标准同步执行的手算表 A（含动作数值、idx、代际、请求数、mask）。"""
    diffs = list(res.get("_hand_diffs") or [])
    tv = res.get("training_view") or {}
    if tv.get("execution_mask") != MASK_STANDARD_SYNC_N2_H4:
        diffs.append(f"execution_mask {tv.get('execution_mask')} != 手算 {MASK_STANDARD_SYNC_N2_H4}")
    if tv.get("bc_mask") != MASK_STANDARD_SYNC_N2_H4:
        diffs.append(f"bc_mask {tv.get('bc_mask')} != 手算 {MASK_STANDARD_SYNC_N2_H4}")
    if res.get("n_hold_frames") != 0:
        diffs.append(f"hold 帧 {res.get('n_hold_frames')} != 0（标准同步执行**无** priming）")
    if "expired" in (res.get("contract_event_kinds") or []):
        diffs.append("出现 `expired` 契约事件（同步阻塞下不存在「结果没赶上它所属的槽」这个事实）")
    bad_src = sorted({s["source"] for s in res["steps"]} - {"policy"})
    if bad_src:
        diffs.append(f"非 policy 来源 {bad_src}")
    bad_idx = sorted(set(res.get("executed_indices") or []) - {0, 1})
    if bad_idx:
        diffs.append(f"执行的 idx {bad_idx} 越出 [0,n)=[0,2)")
    return {"ok": not diffs and res.get("error") is None, "diffs": diffs,
            "error": res.get("error"), "hand_table": HAND_TABLE_STANDARD_SYNC,
            "mask_expected": MASK_STANDARD_SYNC_N2_H4, "mask_got": tv.get("execution_mask"),
            "n_requests_expected": N_REQUESTS_N2, "n_requests_got": res.get("n_requests"),
            "note": "手算表在**本文件顶部由人算出**（`n=2,H=4`，`idx = f - 2·(f//2)`），闸只做比对"}


def gate_g2_harness_matches_s4a(res_h: dict) -> dict:
    """G2：**默认路径零漂移** —— 同一 stub 在 `harness_second_half` 下必须**逐格** reproduces
    S4a 的 `HAND_TABLE`（用 **S4a 自己的闸函数**判，不抄一份表：抄一份 = 缺陷类 ⑲ 的形状）。
    """
    s4a_gate = S4A.gate_hand_table(res_h)
    tv = res_h.get("training_view") or {}
    checks = {
        "s4a_gate_hand_table_ok": bool(s4a_gate.get("ok")),
        "s4a_table_is_the_imported_object": (S4A.HAND_TABLE is not None
                                             and len(S4A.HAND_TABLE) == 8),
        "mask_is_second_half": tv.get("execution_mask") == MASK_HARNESS_N2_H4,
        "two_hold_frames_at_head": res_h.get("n_hold_frames") == 2,
        "executed_indices_are_n_to_2n": sorted(set(res_h.get("executed_indices") or [])) == [2, 3],
        "version_token_is_harness": (res_h.get("exec_caliber") or {}).get("exec_mode")
                                    == VR.EXEC_MODE_HARNESS_SECOND_HALF,
        "no_error": res_h.get("error") is None,
    }
    return {"ok": all(checks.values()), "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "s4a_gate_diffs": s4a_gate.get("diffs"),
            "s4a_hand_table_first_row": list(S4A.HAND_TABLE[0]),
            "s4a_hand_table_last_row": list(S4A.HAND_TABLE[-1]),
            "mask_got": tv.get("execution_mask"),
            "note": ("S4a 17/17 与本闸同时成立 ⇒ `exec_mode` 的引入**没有改变默认路径的行为**；"
                     "版本串多了 `:exec=` token 这件事在 G4 单独处置（不是行为漂移）")}


def gate_g3_two_modes_differ(res_ss: dict, res_h: dict) -> dict:
    """G3：两种执行语义在前 4 帧上**逐格不同** ⇒ 证明 `exec_mode` 不是装饰性开关（裁定 95.3-④）。

    牙的形状：若两者只在字段名上不同、执行的**动作值**相同，本闸必须红。
    """
    ss, hh = res_ss["steps"], res_h["steps"]
    first4_ss = [(s["abs_frame"], s["source"], s["lease_generation"], s["chunk_index"],
                  [round(x, 6) for x in (s["action"] or [])]) for s in ss[:4]]
    first4_hh = [(s["abs_frame"], s["source"], s["lease_generation"], s["chunk_index"],
                  [round(x, 6) for x in (s["action"] or [])]) for s in hh[:4]]
    checks = {
        "head_frames_differ": first4_ss != first4_hh,
        "ss_f0_is_policy": ss[0]["source"] == "policy",
        "hh_f0_is_prime_hold": hh[0]["source"] == "hold",
        "executed_index_sets_disjoint": (set(res_ss["executed_indices"])
                                         .isdisjoint(set(res_h["executed_indices"]))),
        "ss_indices_are_head": sorted(set(res_ss["executed_indices"])) == [0, 1],
        "hh_indices_are_second_half": sorted(set(res_h["executed_indices"])) == [2, 3],
        "executed_action_values_differ": ([round(x, 6) for x in (ss[2]["action"] or [])]
                                          != [round(x, 6) for x in (hh[2]["action"] or [])]),
        "segment_labels_differ": (res_ss["manifest_caliber"]["executed_index_segment"] == "[0,n)"
                                  and res_h["manifest_caliber"]["executed_index_segment"] == "[n,2n)"),
        "hold_frame_counts_differ": (res_ss["n_hold_frames"] == 0 and res_h["n_hold_frames"] == 2),
        "same_stub_same_seed_same_nH": (res_ss["arm"].startswith("stub:")
                                        and res_h["arm"].startswith("stub:")),
    }
    return {"ok": all(checks.values()), "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "first4_standard_sync": first4_ss, "first4_harness_second_half": first4_hh,
            "state_alignment_ruling": VR.EXEC_MODE_CALIBER[
                VR.EXEC_MODE_HARNESS_SECOND_HALF]["state_alignment_risk"],
            "note": ("f=2 在 harness 模式下执行的是**第 0 代 idx 2**，在标准同步下执行的是"
                     "**第 1 代 idx 0** ⇒ 连「哪一代」都不同，不只是索引不同")}


def gate_g4_exec_token_and_transplant_ban(res_ss: dict, res_h: dict) -> dict:
    """G4：`exec=` token 进版本串 + 两模式版本串不同 + **历史产物归一规则**实测 + 延迟带不受影响。"""
    vss, vh = res_ss["representation_version"], res_h["representation_version"]
    v_stripped = vh.replace(":exec=harness_second_half", "")
    band_probe: dict[str, Any] = {}
    for rel in BAND_ARTIFACTS:
        p = REPO / rel
        if not p.exists():
            band_probe[rel] = {"measurement_status": "not_measured", "why": "产物不在盘（读不到≠测到没有）"}
            continue
        txt = p.read_text(errors="replace")
        band_probe[rel] = {
            "measurement_status": "measured", "sha256_12": sha12(p), "bytes": p.stat().st_size,
            "contains_vla_runtime_version_string": ("vla_runtime_v1:" in txt),
            "contains_exec_token": (":exec=" in txt),
            "contains_env_shim_version": ("gym_aloha_dt0.034_29.4118hz_shim_v1" in txt),
        }
    band_measurable = all(v.get("measurement_status") == "measured" for v in band_probe.values())
    checks = {
        "ss_token_present": ":exec=standard_sync:" in vss,
        "h_token_present": ":exec=harness_second_half:" in vh,
        "two_version_strings_differ": vss != vh,
        "only_the_exec_and_prime_tokens_differ": (
            vss.replace(":prime=none:exec=standard_sync", "")
            == vh.replace(":prime=hold:exec=harness_second_half", "")),
        "caliber_reader_ss": (res_ss["exec_caliber"].get("exec_mode") == VR.EXEC_MODE_STANDARD_SYNC
                              and res_ss["exec_caliber"].get("token_present") is True),
        "caliber_reader_h": (res_h["exec_caliber"].get("exec_mode")
                             == VR.EXEC_MODE_HARNESS_SECOND_HALF),
        "historical_absent_token_normalizes_to_harness": (
            VR.exec_caliber_of_representation_version(v_stripped)
            == {"measurement_status": "measured", "token_present": False,
                "exec_mode": VR.EXEC_MODE_HARNESS_SECOND_HALF,
                "normalized_from_absent_token": True,
                "rule": VR.exec_caliber_of_representation_version(v_stripped)["rule"]}),
        "cross_mode_transplant_refused": (
            VR.cross_mode_transplant_allowed(vss, vh)["transplant_allowed"] is False
            and VR.cross_mode_transplant_allowed(vss, vh)["paired_comparison_allowed"] is True),
        "historical_band_comparable_to_new_harness_runs": (
            VR.cross_mode_transplant_allowed(v_stripped, vh)["transplant_allowed"] is True),
        "unknown_token_is_not_measured": (
            VR.exec_caliber_of_representation_version(vh.replace("harness_second_half", "weird"))
            ["measurement_status"] == "not_measured"),
        "missing_version_is_not_measured": (
            VR.exec_caliber_of_representation_version(None)["exec_mode"] is None),
        "band_artifacts_measurable": band_measurable,
        "band_artifacts_carry_no_runtime_version_string": band_measurable and all(
            v.get("contains_vla_runtime_version_string") is False for v in band_probe.values()),
    }
    return {"ok": all(checks.values()), "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "version_standard_sync": vss, "version_harness_second_half": vh,
            "version_historical_shape_token_stripped": v_stripped,
            "band_artifact_probe": band_probe,
            "band_values_quoted_for_scope_only": BAND_VALUES_QUOTED_FOR_SCOPE_ONLY,
            "band_scope_statement": (
                "**实测（不是推断）**：rep4/rep5 的产物里**没有** `vla_runtime_v1:` 串、只有 env shim "
                "版本 ⇒ `exec=` token 的引入**不改变**权威延迟带的身份。该带的执行语义按归一规则读作 "
                "`harness_second_half`；**standard_sync 的延迟必须另测**，不得沿用这条带（裁定 95.3-④）"),
            "as_of": datetime.now().astimezone().isoformat(timespec="seconds")}


def gate_g5_interlock_standard_sync_needs_prime_none(t_hold: dict, t_first: dict,
                                                     t_none: dict) -> dict:
    """G5：`standard_sync` + `prime≠none` ⇒ **构造就抛**（让混搭不可表达，不是混搭后告警）。"""
    checks = {
        "prime_hold_refused": t_hold["raised"] and t_hold["exc_type"] == "VlaRuntimeError",
        "prime_first_chunk_refused": t_first["raised"] and t_first["exc_type"] == "VlaRuntimeError",
        "prime_none_accepted": t_none["raised"] is False,
        "message_names_the_ruling": ("不可共存" in (t_hold["message"] or "")),
        "message_names_state_alignment": ("状态对齐" in (t_hold["message"] or "")),
    }
    return {"ok": all(checks.values()), "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "probe_prime_hold": t_hold, "probe_prime_first_chunk": t_first,
            "probe_prime_none": t_none,
            "rule": "裁定 95.3-④：给标准同步执行配 prime hold = 把要绕开的状态对齐问题又装回来"}


def gate_g6_interlock_harness_rejects_prime_none(t_probe: dict, t_ok: dict) -> dict:
    """G6：反向互锁 —— `harness_second_half` + `prime=none` 也必须抛（否则 t=0 无源）。"""
    checks = {
        "prime_none_refused_under_harness": (t_probe["raised"]
                                            and t_probe["exc_type"] == "VlaRuntimeError"),
        "message_explains_no_source_at_t0": ("无源" in (t_probe["message"] or "")
                                             or "priming" in (t_probe["message"] or "")),
        "prime_hold_still_accepted_under_harness": t_ok["raised"] is False,
    }
    return {"ok": all(checks.values()), "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "probe_prime_none": t_probe, "probe_prime_hold": t_ok,
            "rule": "两个开关**互锁**：任一方向的静默混搭都会让「执行语义」变成读不出来的隐含状态"}


def gate_g7_n_eq_h(res_nh: dict, t_harness_nh: dict) -> dict:
    """G7：`n = H` 只在 `standard_sync` 下合法（手算表 B）；`harness_second_half` 必须拒绝构造。"""
    diffs = _cmp_hand_table(res_nh["steps"], HAND_TABLE_N_EQ_H, N_REQUESTS_N4,
                            res_nh["n_requests"])
    tv = res_nh.get("training_view") or {}
    if tv.get("execution_mask") != MASK_N_EQ_H:
        diffs.append(f"execution_mask {tv.get('execution_mask')} != 手算 {MASK_N_EQ_H}")
    if res_nh.get("n_hold_frames") != 0:
        diffs.append(f"hold 帧 {res_nh.get('n_hold_frames')} != 0")
    checks = {
        "hand_table_B_matches": not diffs,
        "no_error": res_nh.get("error") is None,
        "harness_refuses_n_eq_H": (t_harness_nh["raised"]
                                   and "H≥2n" in (t_harness_nh["message"] or "")),
        "caliber_says_h_ge_2n_not_required": (
            res_nh["manifest_caliber"]["h_ge_2n_required_by_this_exec_mode"] is False),
        "caliber_still_reports_actual_h_ge_2n_false": (
            res_nh["manifest_caliber"]["h_ge_2n"] is False),
    }
    return {"ok": all(checks.values()), "checks": checks, "diffs": diffs,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "hand_table": HAND_TABLE_N_EQ_H, "probe_harness_n_eq_H": t_harness_nh,
            "note": ("`standard_sync` 的约束是 **1 ≤ n ≤ H**（执行 chunk 的**前** n 项）；"
                     "`harness_second_half` 保留 v4 附录一 :103 的 **H ≥ 2n**。**不要**把 "
                     "`H ≥ 2n` 当成全局不变量去要求 standard_sync —— 那会把 n=H 这个"
                     "出厂默认档（裁定 65-1 提到的形态）误判为非法")}


def gate_g8_slots_restamped_by_runtime(res_liar: dict, res_honest: dict) -> dict:
    """G8：**槽位归属是运行时的语义**——策略谎报 `slot_e=(1,2,3)` 对执行行为必须零影响。"""
    g0 = (res_liar.get("committed_chunks") or {}).get("0") or {}
    checks = {
        "no_error": res_liar.get("error") is None,
        "stamp_flag_set": g0.get("slots_restamped_by_runtime") is True,
        "slot_e_restamped_to_head": list(g0.get("slot_e") or []) == [0, 1],
        "slot_c_emptied": list(g0.get("slot_c") or []) == [],
        "slot_d_is_the_rest": list(g0.get("slot_d") or []) == [2, 3],
        "chunk_exec_mode_stamped": g0.get("exec_mode") == VR.EXEC_MODE_STANDARD_SYNC,
        "executed_indices_still_head": sorted(set(res_liar["executed_indices"])) == [0, 1],
        "steps_identical_to_honest_policy": (
            [{k: s[k] for k in ("abs_frame", "source", "lease_generation", "chunk_index", "action")}
             for s in res_liar["steps"]]
            == [{k: s[k] for k in ("abs_frame", "source", "lease_generation", "chunk_index", "action")}
                for s in res_honest["steps"]]),
        "honest_policy_also_stamped": (
            ((res_honest.get("committed_chunks") or {}).get("0") or {})
            .get("slots_restamped_by_runtime") is True),
    }
    return {"ok": all(checks.values()), "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "liar_proposed_slots": {"slot_c": [0], "slot_e": [1, 2, 3], "slot_d": []},
            "runtime_committed_slots_gen0": g0,
            "rule": ("`_request_and_commit` 在 `exec_mode=standard_sync` 下**重盖** "
                     "slot_c/slot_e/slot_d 并置 `slots_restamped_by_runtime=True` ⇒ "
                     "「策略自述的执行语义」不可能改变实际执行")}


def gate_g9_over_budget_no_frame_discarded(res_slow: dict, res_fast: dict) -> dict:
    """G9：标准同步执行**不因超预算丢帧**（裁定 75.4 软约束）：零 `expired`、零丢帧、只单列记账。"""
    recs = res_slow.get("sync_overload_records") or []
    checks = {
        "no_error": res_slow.get("error") is None,
        "overload_records_present": len(recs) == N_REQUESTS_N2,
        "every_record_discards_zero_frames": all(r.get("frames_discarded") == 0 for r in recs),
        "every_record_emits_no_contract_event": all(r.get("contract_event_emitted") is None
                                                    for r in recs),
        "late_records_empty": (res_slow.get("late_records") or []) == [],
        "no_expired_contract_event": "expired" not in (res_slow.get("contract_event_kinds") or []),
        "all_frames_still_policy": res_slow.get("n_policy_frames") == 8
                                   and res_slow.get("n_hold_frames") == 0,
        "executed_actions_unchanged_by_overload": (
            [{ "abs_frame": s["abs_frame"], "action": s["action"]} for s in res_slow["steps"]]
            == [{"abs_frame": s["abs_frame"], "action": s["action"]} for s in res_fast["steps"]]),
        "over_budget_actually_happened": all(
            (r.get("inference_wall_s") or 0) > (r.get("deadline_s") or 0) for r in recs),
        "fast_arm_has_no_overload_records": (res_fast.get("sync_overload_records") or []) == [],
        "timing_report_labels_soft_constraint": (
            res_slow["timing_report"].get("exec_mode") == VR.EXEC_MODE_STANDARD_SYNC),
    }
    return {"ok": all(checks.values()), "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "sync_overload_records": recs,
            "n_late_records": len(res_slow.get("late_records") or []),
            "contrast_harness_mode": ("`harness_second_half` 下同样的超预算会走 `late_records` + "
                                      "发 `expired` + 按 `late_policy=hold` 处置（S4a G7 已验）⇒ "
                                      "**两种语义对超预算的处置不同**，这条差异本身就是 G3 的一部分"),
            "rule": "裁定 75.4（仿真里 34 ms/步是软约束）+ 95.3-④（同步阻塞 ⇒ 不存在过期的槽）"}


def gate_g10_four_fields(records: list[dict], agg: dict, empty_agg: dict,
                         merged_probe: dict) -> dict:
    """G10：裁定 95.3-① 的四字段**分开记** + OOD **只标注不剔除** + 空集 ⇒ `null` + 非零退出。"""
    by_tag = {r["probe_tag"]: r for r in records}
    r_ood = by_tag["ood_true_b_class"]
    r_in = by_tag["polarity_anchor_in_distribution"]
    r_partial = by_tag["tri_anchor_partially_measured"]
    r_unknown = by_tag["all_unmeasured"]
    mismatches = [{"probe_tag": r["probe_tag"], "field": k, "got": r.get(k),
                   "hand_expected": r["hand_expected"][k]}
                  for r in records for k in VR.FOUR_FIELDS
                  if r.get(k) != r["hand_expected"][k]]
    n = len(records)
    checks = {
        "hand_expectations_all_match": not mismatches,
        "polarity_anchor_in_distribution_is_false": r_in["out_of_distribution"] is False,
        "ood_true_when_a_b_signal_fires": r_ood["out_of_distribution"] is True,
        "tri_anchor_partially_measured_is_none": r_partial["out_of_distribution"] is None,
        "all_unmeasured_is_none_not_false": r_unknown["out_of_distribution"] is None,
        "measurement_unreliable_is_none_not_false": r_unknown["measurement_reliable"] is None,
        "four_fields_all_present_separately": all(
            all(k in r for k in VR.FOUR_FIELDS) for r in records),
        "no_merged_field_in_records": all(r.get("merged_field_present") is False for r in records),
        "ood_episode_not_excluded": (r_ood["out_of_distribution"] is True
                                     and r_ood["excluded_from_capability_stats"] is False),
        "aggregate_excludes_nothing": agg.get("n_excluded_from_capability_stats") == 0,
        "aggregate_includes_ood_in_denominator": agg.get("n_episodes") == n,
        "ood_ratio_reported": agg.get("ood_ratio") == round(1 / n, 4),
        "ood_count_is_one": agg.get("ood_count") == 1,
        "task_success_rate_includes_ood": (
            agg.get("task_success_rate_including_ood") == round(1 / n, 4)),
        "unknown_outcome_is_not_measured_not_false": (
            r_unknown["task_success"] is None and agg.get("task_success_not_measured_count") == 1),
        "by_seed_reported_individually": set(agg.get("by_seed") or {}) == {"1", "2"},
        "by_direction_reported_separately": set(agg.get("by_direction") or {})
                                            == {"right_to_left", "left_to_right"},
        "three_way_all_not_measured_before_step4": all(
            v.get("measurement_status") == "not_measured"
            for k, v in (agg.get("three_way_statistics") or {}).items()
            if isinstance(v, dict)),
        "empty_set_is_null_and_nonzero_exit": (
            empty_agg.get("measurement_status") == "not_measured"
            and empty_agg.get("verdict") is None
            and empty_agg.get("nonzero_exit_required") is True
            and empty_agg.get("task_success_count") is None),
        "merged_validity_key_raises": merged_probe.get("raised") is True
                                      and merged_probe.get("exc_type") == "MergedValidityError",
        "merged_validity_in_aggregate_input_raises":
            merged_probe.get("raised_in_aggregate") is True,
        "clean_record_does_not_raise": merged_probe.get("clean_raised") is False,
        "capability_claim_false": agg.get("capability_claim") is False,
        "success_rate_column_not_exit_criterion": (
            agg.get("success_rate_column") == "not_an_exit_criterion"),
    }
    return {"ok": all(checks.values()), "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "hand_expectation_mismatches": mismatches,
            "polarity_anchor_note": (
                "第 1 局（五个 OOD 信号全 False）必须判 `out_of_distribution=False`；"
                "第 4 局（信号只采到一部分）必须判 `None`。这两条锚曾抓住 "
                "`vla_runtime.py` 的 `_tri([not x …])` **极性反向**缺陷（`ood_ratio` 恒 = 1.0）"),
            "records": records, "aggregate": agg, "aggregate_empty_set": empty_agg,
            "merged_validity_probe": merged_probe,
            "forbidden_merged_keys": sorted(VR.FORBIDDEN_MERGED_VALIDITY_KEYS),
            "field_meanings": VR.FOUR_FIELD_MEANINGS,
            "rule": VR.RULING_95_3_1}


def gate_g11_real_env_end_to_end(res: dict | None, skipped_reason: str | None) -> dict:
    """G11：**「通路能跑」的验收** —— 真实 env（osmesa）+ C2 判定 + ledger round-trip，
    全程 `standard_sync`。**跳过 ⇒ 红**（`not_measured` 不等于"通过"，裁定 88.3-1）。
    """
    if res is None:
        return {"ok": False, "measurement_status": "not_measured",
                "checks": {}, "failed_checks": {"real_env_arm_ran": False},
                "why": skipped_reason or "真实 env 臂未跑",
                "rule": ("读不到 ≠ 测到没有；本闸是「标准同步执行通路能跑」的**唯一**端到端证据，"
                         "跳过就没有证明 ⇒ 判红 + 非零退出，不判绿")}
    n = res["n_replan"]
    rt = res.get("ledger_roundtrip") or {}
    rt_status = rt.get("measurement_status")
    rt_labels = [x.get("outcome_class") for x in (rt.get("outcome_labels") or [])]
    rt_observed = list(rt.get("outcome_classes_observed") or [])
    rt_event_classes = [e.get("s4b_outcome_class") for e in (rt.get("episode_end_events") or [])]
    checks = {
        "no_runtime_error": res.get("error") is None,
        "exec_caliber_is_standard_sync": (res.get("exec_caliber") or {}).get("exec_mode")
                                         == VR.EXEC_MODE_STANDARD_SYNC,
        "zero_hold_frames": res.get("n_hold_frames") == 0,
        "all_frames_from_policy": res.get("n_policy_frames") == res.get("n_frames_driven"),
        "executed_indices_within_head_segment": (
            all(0 <= i < n for i in (res.get("executed_indices") or [0]))
            and len(res.get("executed_indices") or []) > 0),
        "chunk_count_matches_closed_form": (res.get("n_chunks_committed")
                                            == res.get("expected_n_chunks")),
        "slots_restamped_on_real_policy": all(
            c.get("slots_restamped_by_runtime") is True and c.get("slot_e_len") == n
            for c in (res.get("committed_chunks_slots") or {}).values()),
        "outcome_class_in_c2_vocabulary": res.get("outcome_class") in VR.S4B_OUTCOME_CLASSES,
        "judgment_layer_is_c2s": (
            (res.get("judgment_layer_identity") or {}).get("authority")
            == VR.S4B_JUDGMENT_AUTHORITY),
        "ledger_roundtrip_measured": rt_status == "measured",
        "ledger_roundtrip_agrees_with_memory": (
            rt_labels == [res.get("outcome_class")]
            and rt_observed == [res.get("outcome_class")]
            and rt_event_classes == [res.get("outcome_class")]),
        "ledger_roundtrip_has_exactly_one_label": len(rt_labels) == 1,
        "cross_check_verdict_present": all(
            e.get("cross_check_verdict") in ("GREEN", "RED")
            for e in (rt.get("episode_end_events") or [])) and bool(rt.get("episode_end_events")),
        "exactly_one_episode_end_event": res.get("n_episode_end_events") == 1,
        "event_kinds_within_ledger_vocabulary": all(
            k in LEDGER_KINDS for k in (res.get("event_kinds_used") or [])),
        "mask_tail_is_all_zero": all(v == 0 for v in
                                     (res.get("training_view") or {}).get("execution_mask_tail") or [0]),
        "mask_head_has_ones": any(v == 1 for v in
                                  (res.get("training_view") or {}).get("execution_mask_head") or []),
        "four_fields_computed_on_real_path": all(
            k in (res.get("four_fields") or {}) for k in VR.FOUR_FIELDS),
        "gpu_not_used": res.get("gpu_used") is False,
        "sync_overload_records_are_facts_not_drops": all(
            r.get("frames_discarded") == 0 for r in (res.get("sync_overload_records") or [])),
    }
    return {"ok": all(checks.values()), "measurement_status": "measured", "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "n_frames_driven": res.get("n_frames_driven"),
            "outcome_class": res.get("outcome_class"),
            "ledger_roundtrip_status": rt_status,
            "ledger_roundtrip_read_back": {"outcome_labels": rt_labels,
                                           "outcome_classes_observed": rt_observed,
                                           "episode_end_s4b_outcome_class": rt_event_classes},
            "roundtrip_read_note": ("**三处都读**（label 行 / `outcome_classes_observed` / "
                                    "`episode_end` 的 payload）：只读一处会让「账本里没有」与"
                                    "「读错了键」两种情况长得一样（本闸首跑就是这样假红的，"
                                    "已改为三处同读）"),
            "mujoco_gl": res.get("mujoco_gl"),
            "renderer_class_three_points": res.get("renderer_class_three_points"),
            "per_frame_first6": res.get("per_frame_first6"),
            "caliber_note": res.get("caliber_note"),
            "capability_claim": False,
            "policy_executed_is_not_a_capability_claim": (
                "本臂策略 = **确定性 hold**（S4b 的 `HoldPolicy`）⇒ 验的是接线与执行语义，"
                "**不是**任何 policy 能力（裁定 46 禁令不变）"),
            "rule": "补单二-§二：「标准同步执行通路能跑」= 第 1–3 步的共同前置"}


def gate_g12_no_silent_degradation(probe_ss: dict, probe_h: dict) -> dict:
    """G12：`standard_sync` 下缺 chunk ⇒ **抛**，绝不静默退化成 hold（hold 正是 95.3-④ 要绕开的
    那个状态对齐问题的来源）。对照：`harness_second_half` 的 f0 返回 `hold/prime` 是**既定语义**。
    """
    checks = {
        "missing_chunk_raises_under_standard_sync": (
            probe_ss["raised"] and probe_ss["exc_type"] == "VlaRuntimeError"),
        "message_calls_it_structural_bug": ("结构性 bug" in (probe_ss["message"] or "")),
        "message_forbids_silent_hold": ("不许静默退化" in (probe_ss["message"] or "")),
        "harness_prime_hold_is_by_design_not_an_error": (
            probe_h["raised"] is False and probe_h.get("source") == "hold"
            and probe_h.get("hold_reason") == "prime"),
        "the_two_fallbacks_differ": probe_ss["raised"] is True and probe_h["raised"] is False,
    }
    return {"ok": all(checks.values()), "checks": checks,
            "failed_checks": {k: v for k, v in checks.items() if not v},
            "probe_standard_sync": probe_ss, "probe_harness_prime": probe_h,
            "note": ("直接调 `_resolve_frame` 才走得到这条路（`step()` 在同一帧先请求再执行）⇒ "
                     "本闸守的是**结构性 bug 不许被 hold 掩盖**，不是守正常路径")}


# ═══════════════════════════ 四字段探针（G10 的输入）═══════════════════════════
def build_four_field_probes() -> tuple[list[dict], dict, dict, dict]:
    """四局手算输入（**每局的四字段期望值都是人算的**，写在 `EXPECT` 里）。

    第 1 局是**极性锚**：五个 OOD 信号全部采到且全部为 `False` ⇒ `out_of_distribution` 必须
    是 `False`。这一条曾在本仓**反向**成立过（`vla_runtime.py` 的 `_tri([not x …])` 写法把
    「全不在分布外」聚合成 `True` ⇒ 每局都标 OOD、`ood_ratio` 恒 = 1.0），
    由本闸的手算期望抓住并已在 `harness/vla_runtime.py` 修正（前像
    `tmp/vla_runtime_pre_oodpolarity_8f35376ba2bb.py`）。**锚留在脚本里，缺陷类就回不来。**
    第 4 局是**三值锚**：信号只采到一部分 ⇒ 必须 `None`（not_measured），**不是** `False`。
    """
    base_ood_false = {"state_out_of_normalizer_range": False, "action_clipped_at_ctrlrange": False,
                      "prompt_bins_saturated_255": False, "prompt_bins_illegal_minus1": False,
                      "action_unit_mismatch_suspected": False}
    partial = {**base_ood_false, "action_clipped_at_ctrlrange": None,
               "prompt_bins_saturated_255": None}
    specs = [
        # (tag, outcome_class, seed, direction, ledger_status, timing, ood_signals)
        ("polarity_anchor_in_distribution", "success", 1, "right_to_left", "measured", True,
         base_ood_false),
        ("ood_true_b_class", "failure", 1, "left_to_right", "measured", True,
         {**base_ood_false, "state_out_of_normalizer_range": True,
          "state_out_of_normalizer_range_detail": "qpos[3] 越出 normalizer 区间（(b) 类）"}),
        ("all_unmeasured", "unknown", 2, "right_to_left", None, None, {}),
        ("tri_anchor_partially_measured", "failure", 2, "left_to_right", "measured", True, partial),
    ]
    # 人算期望：(measurement_reliable, interface_conformant, out_of_distribution, task_success)
    EXPECT = {
        "polarity_anchor_in_distribution": (True, None, False, True),
        "ood_true_b_class": (True, None, True, False),
        "all_unmeasured": (None, None, None, None),
        "tri_anchor_partially_measured": (True, None, None, False),
    }
    recs, objs = [], []
    for tag, oc, seed, direction, ledger_st, timing, ood in specs:
        ff = VR.four_fields_from_episode(
            outcome_class=oc, ledger_roundtrip_status=ledger_st, timing_measured=timing,
            isolation_reasons=[], ood_signals=ood, seed=seed, direction=direction)
        d = ff.as_dict()
        d["outcome_class_input"] = oc
        d["probe_tag"] = tag
        d["hand_expected"] = dict(zip(VR.FOUR_FIELDS, EXPECT[tag]))
        recs.append(d)
        objs.append(ff)
    agg = VR.aggregate_capability_stats(objs)
    empty = VR.aggregate_capability_stats([])
    probe: dict[str, Any] = {}
    try:
        VR.assert_no_merged_validity({"episode": {"is_valid": True, "task_success": True}})
        probe.update(raised=False, exc_type=None, message=None)
    except Exception as exc:                                        # noqa: BLE001
        probe.update(raised=True, exc_type=type(exc).__name__, message=str(exc)[:400])
    try:
        VR.aggregate_capability_stats([{"is_valid": True, "task_success": True, "seed": 1}])
        probe["raised_in_aggregate"] = False
    except Exception as exc:                                        # noqa: BLE001
        probe["raised_in_aggregate"] = True
        probe["aggregate_exc_type"] = type(exc).__name__
    try:
        VR.assert_no_merged_validity({"measurement_reliable": True, "interface_conformant": True,
                                      "out_of_distribution": False, "task_success": True})
        probe["clean_raised"] = False
    except Exception as exc:                                        # noqa: BLE001
        probe["clean_raised"] = True
        probe["clean_exc"] = f"{type(exc).__name__}: {exc}"
    return recs, agg, empty, probe


# ═══════════════════════════════ 变异自检（裁定 93.8 两向）══════════════════════════
def mutation_self_test(C: dict) -> dict:
    """对**产物**做一处具体篡改、跑真实闸函数，闸必须变红。没有这一步，
    每条闸 docstring 里那句「要能被具体篡改打红」就只是注释（裁定 72：自检走真实取数路径）。
    """
    detail: dict[str, Any] = {}

    def rec(name: str, baseline: dict, mutant: dict, tamper: str) -> None:
        detail[name] = {"baseline_ok": bool(baseline.get("ok")),
                        "mutant_ok": bool(mutant.get("ok")),
                        "teeth": bool(baseline.get("ok")) and not bool(mutant.get("ok")),
                        "tamper": tamper,
                        "mutant_failed_checks": list((mutant.get("failed_checks") or {}).keys())
                        if isinstance(mutant.get("failed_checks"), dict) else None}

    def cp(k: str) -> dict:
        return copy.deepcopy(C[k])

    # G1：把一个执行动作改成 harness 模式的值（= 假装两种语义一样）
    m = cp("ss"); m["steps"][2]["action"] = [2.0, -2.0]
    m["_hand_diffs"] = _cmp_hand_table(m["steps"], HAND_TABLE_STANDARD_SYNC, N_REQUESTS_N2,
                                       m["n_requests"])
    rec("G1", gate_g1_standard_sync_hand_table(C["ss"]),
        gate_g1_standard_sync_hand_table(m), "steps[2].action → [2,-2]（harness 模式的值）")

    # G1b：把 mask 改成 harness 的 [0,0,1,1]
    m = cp("ss"); m["training_view"]["execution_mask"] = MASK_HARNESS_N2_H4
    m["_hand_diffs"] = []
    rec("G1b", gate_g1_standard_sync_hand_table(C["ss"]),
        gate_g1_standard_sync_hand_table(m), "execution_mask → [0,0,1,1]")

    # G2：把 harness 臂的 f0 改成 policy（假装没有 prime hold）
    m = cp("h"); m["steps"][0]["source"] = "policy"
    rec("G2", gate_g2_harness_matches_s4a(C["h"]), gate_g2_harness_matches_s4a(m),
        "harness 臂 steps[0].source hold→policy")

    # G3：把 standard_sync 的前 4 帧改成与 harness 相同（假装 exec_mode 是装饰）
    m = cp("ss"); m["steps"] = copy.deepcopy(C["h"]["steps"])
    rec("G3", gate_g3_two_modes_differ(C["ss"], C["h"]), gate_g3_two_modes_differ(m, C["h"]),
        "standard_sync 的 steps 整体替换成 harness 的 steps")

    # G4：把 standard_sync 的版本串 token 改成 harness（假装可互搬）
    m = cp("ss")
    m["representation_version"] = m["representation_version"].replace(
        ":exec=standard_sync:", ":exec=harness_second_half:")
    m["exec_caliber"] = VR.exec_caliber_of_representation_version(m["representation_version"])
    rec("G4", gate_g4_exec_token_and_transplant_ban(C["ss"], C["h"]),
        gate_g4_exec_token_and_transplant_ban(m, C["h"]),
        "版本串 exec=standard_sync → harness_second_half")

    # G5：假装互锁没抛
    rec("G5", gate_g5_interlock_standard_sync_needs_prime_none(
            C["t_ss_hold"], C["t_ss_first"], C["t_ss_none"]),
        gate_g5_interlock_standard_sync_needs_prime_none(
            {"raised": False, "exc_type": None, "message": None}, C["t_ss_first"], C["t_ss_none"]),
        "prime=hold 的构造探针改成「没抛」")

    # G6：反向互锁假装没抛
    rec("G6", gate_g6_interlock_harness_rejects_prime_none(C["t_h_none"], C["t_h_hold"]),
        gate_g6_interlock_harness_rejects_prime_none(
            {"raised": False, "exc_type": None, "message": None}, C["t_h_hold"]),
        "harness+prime=none 的构造探针改成「没抛」")

    # G7：把 n=H 的手算表改成 harness 的表
    m = cp("nh"); m["steps"] = copy.deepcopy(C["h"]["steps"])
    rec("G7", gate_g7_n_eq_h(C["nh"], C["t_h_nh"]), gate_g7_n_eq_h(m, C["t_h_nh"]),
        "n=H 臂的 steps 换成 harness 的表（请求数也变）")

    # G7b：假装 harness 也接受 n=H
    rec("G7b", gate_g7_n_eq_h(C["nh"], C["t_h_nh"]),
        gate_g7_n_eq_h(C["nh"], {"raised": False, "exc_type": None, "message": None}),
        "harness+n=H 的构造探针改成「没抛」")

    # G8：把重盖章的证据改回策略谎报的值
    m = cp("liar"); m["committed_chunks"]["0"]["slot_e"] = [1, 2, 3]
    m["committed_chunks"]["0"]["slots_restamped_by_runtime"] = False
    rec("G8", gate_g8_slots_restamped_by_runtime(C["liar"], C["ss"]),
        gate_g8_slots_restamped_by_runtime(m, C["ss"]),
        "gen0 的 slot_e 改回谎报值 (1,2,3) + restamped→False")

    # G8b：谎报真的改变了执行（idx 变成 1,2）
    m = cp("liar")
    for s in m["steps"]:
        s["chunk_index"] = (s["chunk_index"] + 1) % 3
    m["executed_indices"] = sorted({s["chunk_index"] for s in m["steps"]})
    rec("G8b", gate_g8_slots_restamped_by_runtime(C["liar"], C["ss"]),
        gate_g8_slots_restamped_by_runtime(m, C["ss"]), "执行的 idx 整体 +1（谎报生效了）")

    # G9：塞一条 expired 契约事件（假装同步阻塞下也有"过期的槽"）
    m = cp("slow"); m["contract_event_kinds"].append("expired")
    rec("G9", gate_g9_over_budget_no_frame_discarded(C["slow"], C["ss"]),
        gate_g9_over_budget_no_frame_discarded(m, C["ss"]), "contract_event_kinds 里加 'expired'")

    # G9b：把超预算改成"丢了 2 帧"
    m = cp("slow")
    for r in m["sync_overload_records"]:
        r["frames_discarded"] = 2
    rec("G9b", gate_g9_over_budget_no_frame_discarded(C["slow"], C["ss"]),
        gate_g9_over_budget_no_frame_discarded(m, C["ss"]), "frames_discarded 0→2")

    # G10：把 OOD 局剔出统计（= 裁定 95.3-① 明令禁止的选择偏差）
    m = cp("agg"); m["n_excluded_from_capability_stats"] = 1; m["n_episodes"] = 2
    rec("G10", gate_g10_four_fields(C["ff_records"], C["agg"], C["agg_empty"], C["ff_probe"]),
        gate_g10_four_fields(C["ff_records"], m, C["agg_empty"], C["ff_probe"]),
        "aggregate 的 n_excluded 0→1（OOD 被剔除）")

    # G10b：空集写成 0 + GREEN
    m = cp("agg_empty")
    m.update(measurement_status="measured", verdict="GREEN", task_success_count=0,
             nonzero_exit_required=False)
    rec("G10b", gate_g10_four_fields(C["ff_records"], C["agg"], C["agg_empty"], C["ff_probe"]),
        gate_g10_four_fields(C["ff_records"], C["agg"], m, C["ff_probe"]),
        "空集聚合改成 measured/GREEN/0（裁定 88.3-1 的反面）")

    # G10c：合并字段没被拦下
    m = copy.deepcopy(C["ff_probe"]); m["raised"] = False
    rec("G10c", gate_g10_four_fields(C["ff_records"], C["agg"], C["agg_empty"], C["ff_probe"]),
        gate_g10_four_fields(C["ff_records"], C["agg"], C["agg_empty"], m),
        "`assert_no_merged_validity` 的探针改成「没抛」")

    # G10d：**极性锚反向**（= `vla_runtime.py` 曾真实发生的那个缺陷）
    m = copy.deepcopy(C["ff_records"])
    for r in m:
        if r["probe_tag"] == "polarity_anchor_in_distribution":
            r["out_of_distribution"] = True
    rec("G10d", gate_g10_four_fields(C["ff_records"], C["agg"], C["agg_empty"], C["ff_probe"]),
        gate_g10_four_fields(m, C["agg"], C["agg_empty"], C["ff_probe"]),
        "全 False 信号那局的 out_of_distribution False→True（复现已修的极性缺陷）")

    # G10e：三值锚被写成 False（把 not_measured 当成"在分布内"）
    m = copy.deepcopy(C["ff_records"])
    for r in m:
        if r["probe_tag"] == "tri_anchor_partially_measured":
            r["out_of_distribution"] = False
    rec("G10e", gate_g10_four_fields(C["ff_records"], C["agg"], C["agg_empty"], C["ff_probe"]),
        gate_g10_four_fields(m, C["agg"], C["agg_empty"], C["ff_probe"]),
        "部分未采那局的 out_of_distribution None→False")

    # G11：真实 env 臂跳过
    rec("G11", gate_g11_real_env_end_to_end(C.get("real"), None),
        gate_g11_real_env_end_to_end(None, "变异体：假装真实 env 臂跑过了"),
        "真实 env 臂的产物换成 None（跳过）")

    # G12：缺 chunk 的探针改成"没抛"（= 静默退化成 hold）
    rec("G12", gate_g12_no_silent_degradation(C["t_missing_chunk"], C["t_h_prime"]),
        gate_g12_no_silent_degradation(
            {"raised": False, "exc_type": None, "message": None}, C["t_h_prime"]),
        "缺 chunk 的 `_resolve_frame` 探针改成「没抛」")

    tested = len(detail)
    with_teeth = sum(1 for v in detail.values() if v["teeth"])
    no_teeth = [k for k, v in detail.items() if not v["teeth"]]
    return {"gates_tested": tested, "gates_with_teeth": with_teeth,
            "all_have_teeth": with_teeth == tested, "without_teeth": no_teeth,
            "detail": detail,
            "two_way_note": ("裁定 93.8：Ⅰ 类闸必须**两向**（正向证明闸会绿、反向证明篡改会红）。"
                             "本脚本每条变异体都是「一处具体篡改 + 跑真实闸函数」，不是断言常量")}


# ══════════════════════════════════════ main ══════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(description="标准同步执行通路（裁定 95.3-④）出口判据")
    ap.add_argument("--out-dir", default="runs/vla/a2_standard_sync_exec_20260930")
    ap.add_argument("--no-real-env", action="store_true",
                    help="只跑 stub 臂 ⇒ G11 = not_measured ⇒ **exit 3**（通路没被证明）")
    ap.add_argument("--no-render", action="store_true", help="真实 env 臂不渲染（只验接线）")
    ap.add_argument("--direction", default="right_to_left",
                    choices=["right_to_left", "left_to_right"])
    ap.add_argument("--image-size", type=int, default=224)
    ap.add_argument("--real-frames", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    load0 = S4A.load_snapshot()

    # ── stub 臂（全部可手算；不占 GPU、不需要 mujoco）──
    print("[arm] standard_sync 手算表 A（n=2,H=4,prime=none）…", flush=True)
    ss = run_case(exec_mode=VR.EXEC_MODE_STANDARD_SYNC, prime_mode=VR.PRIME_MODE_NONE,
                  n_replan=2, chunk_size=4, episode_id="ss-handA")
    ss["_hand_diffs"] = _cmp_hand_table(ss["steps"], HAND_TABLE_STANDARD_SYNC,
                                        N_REQUESTS_N2, ss["n_requests"])
    print("[arm] harness_second_half 对照（同一 stub / 同一 seed / 同一 n、H）…", flush=True)
    h = run_case(exec_mode=VR.EXEC_MODE_HARNESS_SECOND_HALF, prime_mode="hold",
                 n_replan=2, chunk_size=4, episode_id="ss-handA-harness")
    print("[arm] n = H = 4（手算表 B；harness 下必须拒绝构造）…", flush=True)
    nh = run_case(exec_mode=VR.EXEC_MODE_STANDARD_SYNC, prime_mode=VR.PRIME_MODE_NONE,
                  n_replan=4, chunk_size=4, episode_id="ss-handB")
    print("[arm] 谎报槽位的策略（G8）…", flush=True)
    liar = run_case(exec_mode=VR.EXEC_MODE_STANDARD_SYNC, prime_mode=VR.PRIME_MODE_NONE,
                    n_replan=2, chunk_size=4, slot_liar=True, episode_id="ss-liar")
    print("[arm] 超预算（推理墙钟 5 s ≫ 槽预算 0.068 s；G9）…", flush=True)
    slow = run_case(exec_mode=VR.EXEC_MODE_STANDARD_SYNC, prime_mode=VR.PRIME_MODE_NONE,
                    n_replan=2, chunk_size=4, slow_factor=5.0, episode_id="ss-slow")
    print("[arm] 互锁探针（G5/G6/G7/G12：构造与 `_resolve_frame` 必须抛）…", flush=True)
    t_ss_hold = try_construct(exec_mode=VR.EXEC_MODE_STANDARD_SYNC, prime_mode="hold", n_replan=2)
    t_ss_first = try_construct(exec_mode=VR.EXEC_MODE_STANDARD_SYNC, prime_mode="first_chunk",
                               n_replan=2)
    t_ss_none = try_construct(exec_mode=VR.EXEC_MODE_STANDARD_SYNC, prime_mode=VR.PRIME_MODE_NONE,
                              n_replan=2)
    t_h_none = try_construct(exec_mode=VR.EXEC_MODE_HARNESS_SECOND_HALF,
                             prime_mode=VR.PRIME_MODE_NONE, n_replan=2)
    t_h_hold = try_construct(exec_mode=VR.EXEC_MODE_HARNESS_SECOND_HALF, prime_mode="hold",
                             n_replan=2)
    t_h_nh = try_construct(exec_mode=VR.EXEC_MODE_HARNESS_SECOND_HALF, prime_mode="hold",
                           n_replan=4, chunk_size=4)

    # G12 的探针：standard_sync 下**不先 step**、直接问 f=0 的来源
    t_missing_chunk: dict[str, Any] = {}
    t_h_prime: dict[str, Any] = {}
    env_p = S4A.StubEnv(n_frames=12)
    pol_p = S4A.StubPolicy()
    pol_p.chunk_size = 4
    rt_p = VR.ChunkedVlaRuntime(pol_p, env_p, episode_id="probe", goal_id="A_to_B",
                                n_replan=2, prime_mode=VR.PRIME_MODE_NONE,
                                exec_mode=VR.EXEC_MODE_STANDARD_SYNC,
                                shim_sha256_12="stub_shim_1234")
    rt_p.reset(seed=1000)
    try:
        r = rt_p._resolve_frame(0)
        t_missing_chunk = {"raised": False, "exc_type": None, "message": None, "returned": list(r)}
    except Exception as exc:                                        # noqa: BLE001
        t_missing_chunk = {"raised": True, "exc_type": type(exc).__name__, "message": str(exc)[:600]}
    env_p2 = S4A.StubEnv(n_frames=12)
    pol_p2 = S4A.StubPolicy()
    pol_p2.chunk_size = 4
    rt_p2 = VR.ChunkedVlaRuntime(pol_p2, env_p2, episode_id="probe2", goal_id="A_to_B",
                                 n_replan=2, prime_mode="hold",
                                 exec_mode=VR.EXEC_MODE_HARNESS_SECOND_HALF,
                                 shim_sha256_12="stub_shim_1234")
    rt_p2.reset(seed=1000)
    try:
        owner_g, idx, source, status, late_choice, hold_reason = rt_p2._resolve_frame(0)
        t_h_prime = {"raised": False, "source": source, "execution_status": status,
                     "hold_reason": hold_reason, "owner_generation": owner_g, "idx": idx}
    except Exception as exc:                                        # noqa: BLE001
        t_h_prime = {"raised": True, "exc_type": type(exc).__name__, "message": str(exc)[:400]}

    print("[arm] 四字段（裁定 95.3-①）：分开记 + OOD 不剔除 + 空集三值…", flush=True)
    ff_records, agg, agg_empty, ff_probe = build_four_field_probes()

    real = None
    real_skip_reason = None
    if args.no_real_env:
        real_skip_reason = "`--no-real-env` ⇒ 真实 env 臂未跑（G11 判 not_measured、脚本非零退出）"
        print(f"[arm] 真实 env 臂**跳过**：{real_skip_reason}", flush=True)
    else:
        print(f"[arm] 真实 env（C2 的 GymAlohaJudgedAdapter，MUJOCO_GL=osmesa，"
              f"{args.real_frames} 帧，standard_sync）…", flush=True)
        real = run_real_case(args, out_dir)

    gates = {
        "G1_standard_sync_hand_table_field_by_field": gate_g1_standard_sync_hand_table(ss),
        "G2_harness_mode_still_matches_s4a_hand_table": gate_g2_harness_matches_s4a(h),
        "G3_two_exec_calibers_differ_on_head_frames": gate_g3_two_modes_differ(ss, h),
        "G4_exec_token_and_cross_mode_transplant_ban": gate_g4_exec_token_and_transplant_ban(ss, h),
        "G5_interlock_standard_sync_requires_prime_none":
            gate_g5_interlock_standard_sync_needs_prime_none(t_ss_hold, t_ss_first, t_ss_none),
        "G6_interlock_harness_rejects_prime_none":
            gate_g6_interlock_harness_rejects_prime_none(t_h_none, t_h_hold),
        "G7_n_eq_H_legal_only_under_standard_sync": gate_g7_n_eq_h(nh, t_h_nh),
        "G8_slots_restamped_by_runtime_not_by_policy": gate_g8_slots_restamped_by_runtime(liar, ss),
        "G9_over_budget_discards_no_frame_no_expired": gate_g9_over_budget_no_frame_discarded(slow, ss),
        "G10_four_fields_separate_ood_not_excluded": gate_g10_four_fields(
            ff_records, agg, agg_empty, ff_probe),
        "G11_real_env_standard_sync_end_to_end": gate_g11_real_env_end_to_end(real, real_skip_reason),
        "G12_missing_chunk_raises_never_degrades_to_hold": gate_g12_no_silent_degradation(
            t_missing_chunk, t_h_prime),
    }

    C = {"ss": ss, "h": h, "nh": nh, "liar": liar, "slow": slow, "real": real,
         "agg": agg, "agg_empty": agg_empty, "ff_records": ff_records, "ff_probe": ff_probe,
         "t_ss_hold": t_ss_hold, "t_ss_first": t_ss_first, "t_ss_none": t_ss_none,
         "t_h_none": t_h_none, "t_h_hold": t_h_hold, "t_h_nh": t_h_nh,
         "t_missing_chunk": t_missing_chunk, "t_h_prime": t_h_prime}
    print("[selftest] 变异自检：逐闸一处具体篡改，证明闸会红…", flush=True)
    mutation = mutation_self_test(C)

    n_ok = sum(1 for g in gates.values() if g.get("ok"))
    load1 = S4A.load_snapshot()
    payload = {
        "artifact": "a2_standard_sync_exec_verification",
        "stage": "S4b-prep / 裁定 95.2 六步序列第 1–3 步的共同前置",
        "task_id": "T-A2-6-prep（补单二-§二：把准备收到「标准同步执行通路能跑」这一件）",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "scripts/a2_standard_sync_exec_verify.py",
        "generator_sha256_12": sha12(pathlib.Path(__file__).resolve()),
        "target_file": "harness/vla_runtime.py",
        "target_sha256_12": sha12(REPO / "harness/vla_runtime.py"),
        "target_lines": len((REPO / "harness/vla_runtime.py").read_text().splitlines()),
        "before_image_of_target": "tmp/vla_runtime_pre_execnorm_78de1211df94.py",
        "reused_not_reimplemented": {
            "stub_env_policy": "scripts/a2_s4a_vla_runtime_verify.py（`StubEnv`/`StubPolicy`/"
                               "`gate_hand_table`/`load_snapshot`，直接 import）",
            "real_env_hold_policy": "scripts/a2_s4b_outcome_ledger_verify.py（`HoldPolicy`）",
            "judgment_layer": ("harness/env_gym_aloha.py 的 `judge_from_facts()`（C2 拥有；"
                               "A2 一条都不重算，见 G11 `judgment_layer_is_c2s`）"),
            "why": "两个位置各写一份口径 = 本仓已发生四次的事故形状（裁定 83§7 / 缺陷类 ⑲）"},
        "criterion_verbatim": ("「把 S4b 的准备收到『**标准同步执行通路能跑**』这一件 —— 它是第 1–3 步的"
                               "**共同前置**，也是本轮唯一必须新增的运行时能力」"
                               "（rl_harness_supervision/d_handoff_to_a2_20260930.md 补单二-§二）"),
        "criterion_source": "rl_harness_supervision/d_handoff_to_a2_20260930.md（123 ln 8b08e087763a）",
        "ruling_source": ("work/decisions/decisions_20260929.md §95.3-④ / §95.3-① / §95.5 "
                          "（3675 ln 4249cc539db2）+ work/project_parameters.json rev20/rev21 "
                          "`ruling95_critical_path_six_steps_rev20`"),
        "contracts_py_sha256_12": sha12(REPO / "harness/contracts.py"),
        "ledger_py_sha256_12": sha12(REPO / "harness/ledger.py"),
        "contracts_py_modified": False, "ledger_py_modified": False,
        "frozen_surface_touched": [], "other_line_files_modified": [],
        "args": vars(args),
        "gates": gates, "n_gates": len(gates), "n_ok": n_ok, "all_ok": n_ok == len(gates),
        "gate_teeth_mutation_selftest": mutation,
        "hand_tables_are_human_computed": {
            "A_standard_sync_n2_H4": "true_hand_written（本文件顶部 `HAND_TABLE_STANDARD_SYNC`，"
                                     "含每帧动作值与 `idx = f - 2·(f//2)` 的算式）",
            "B_n_eq_H": "true_hand_written（`HAND_TABLE_N_EQ_H`，`idx = f - 4·(f//4)`）",
            "harness_control": ("**不在本文件重写**：直接用 `S4A.HAND_TABLE` + `S4A.gate_hand_table` "
                                "（G2），避免「两份手算表」分叉")},
        "exec_mode_caliber_registry": VR.EXEC_MODE_CALIBER,
        "version_string_migration": {
            "fact": ("`representation_version()` 里的 `:exec=` token 是**无条件**拼接的 ⇒ 默认路径"
                     "（`harness_second_half`）的版本串也**多了一段**"),
            "earlier_claim_in_code_was_false": ("`vla_runtime.py` 的 docstring 曾写「既有产物的版本串"
                                                "一字节不变」⇒ **实测为假**，已在同一处更正并给出"
                                                "改前/改后产物对照路径"),
            "before_after_evidence": {
                "before": "runs/vla/a2_s4b_outcome_ledger_20260930_dbg7/s4b_verification.json",
                "after": "runs/vla/a2_s4b_outcome_ledger_20260930_execmode_reg2/s4b_verification.json",
                "diff": "两条 `vla_runtime_v1:…` 串**只差 `:exec=` 这一个 token**，其余逐字相同"},
            "normalization_rule": ("缺 `exec=` token ⇒ 读作 `harness_second_half`"
                                   "（`VR.EXEC_TOKEN_ABSENT_MEANS`；理由：该开关本轮才引入，"
                                   "引入前只存在这一种执行语义）"),
            "authoritative_latency_band_impact": (
                "**实测无影响**：`latency_quiet_window_rep{4,5}.json` 不含任何 `vla_runtime_v1:` 串"
                "（只带 env shim 版本）⇒ rep4 0.8009 / rep5 0.7766 的身份不变。"
                "**但那条带的执行语义 = `harness_second_half`**；`standard_sync` 的延迟必须另测、"
                "不得沿用（裁定 95.3-④ 的互搬禁令）"),
            "behavioral_regression_status": ("S4a 17/17 + 21/21、S4b 15/15 + 22/22 全绿"
                                             "（as_of 2026-09-30 12:5x，osmesa，gpu_used=false）")},
        "capability_claim": False,
        "policy_executed": False,
        "success_metrics_collected": False,
        "success_rate_column": "not_an_exit_criterion（裁定 65-6③ / 46）",
        "forbidden_words_not_used": ["跑通", "学会", "达标"],
        "gpu_used": False,
        "render_backend_of_real_arm": (real or {}).get("mujoco_gl"),
        "cross_caliber_transplant_ban": VR.EXEC_MODE_CALIBER["cross_mode_transplant_ban"],
        "load_before": load0, "load_after": load1,
        "cgroup_caliber": ("v1 `/sys/fs/cgroup/cpu/cpu.stat`；quota=1200000us / period=100000us ⇒ "
                           "**12 核**（`nproc=112` 是假象，裁定 94.9-1）"),
        "cases": {"standard_sync_n2_H4": ss, "harness_control_n2_H4": h,
                  "standard_sync_n_eq_H": nh, "slot_liar": liar, "over_budget": slow,
                  "real_env": real, "real_env_skip_reason": real_skip_reason,
                  "interlock_probes": {"standard_sync_prime_hold": t_ss_hold,
                                       "standard_sync_prime_first_chunk": t_ss_first,
                                       "standard_sync_prime_none": t_ss_none,
                                       "harness_prime_none": t_h_none,
                                       "harness_prime_hold": t_h_hold,
                                       "harness_n_eq_H": t_h_nh,
                                       "standard_sync_missing_chunk": t_missing_chunk,
                                       "harness_prime_hold_resolve_frame": t_h_prime},
                  "four_fields": {"records": ff_records, "aggregate": agg,
                                  "aggregate_empty_set": agg_empty, "probe": ff_probe}},
    }
    payload["nr_throttled_delta_total"] = (
        (load1.get("cpu_stat", {}) or {}).get("nr_throttled", 0)
        - (load0.get("cpu_stat", {}) or {}).get("nr_throttled", 0))
    p = out_dir / "standard_sync_exec_verification.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    print(f"[written] {p}", flush=True)
    for k, v in gates.items():
        print(f"  [{'PASS' if v.get('ok') else 'FAIL'}] {k}", flush=True)
        if not v.get("ok"):
            shown = {kk: vv for kk, vv in v.items()
                     if kk in ("failed_checks", "diffs", "checks", "why", "error",
                               "measurement_status")}
            print("         " + json.dumps(shown, ensure_ascii=False, default=str)[:500], flush=True)
    print(f"[summary] {n_ok}/{len(gates)} gates PASS", flush=True)
    print(f"[summary] 变异自检 {mutation['gates_with_teeth']}/{mutation['gates_tested']} 条有牙"
          f"（all_have_teeth={mutation['all_have_teeth']}）", flush=True)
    if mutation["without_teeth"]:
        print(f"[summary] **无牙的变异体**：{mutation['without_teeth']}", flush=True)
    if real is not None:
        print(f"[summary] 真实 env 臂：{real['n_frames_driven']} 帧 / hold 帧 {real['n_hold_frames']}"
              f" / chunk {real['n_chunks_committed']} / outcome_class={real['outcome_class']}"
              f" / ledger round-trip={(real.get('ledger_roundtrip') or {}).get('measurement_status')}",
              flush=True)
    print(f"[summary] 两种执行语义的版本串：", flush=True)
    print(f"         standard_sync      = {ss['representation_version'][:120]}…", flush=True)
    print(f"         harness_second_half= {h['representation_version'][:120]}…", flush=True)
    print(f"[exit] rc={0 if (n_ok == len(gates) and mutation['all_have_teeth']) else 3}", flush=True)
    return 0 if (n_ok == len(gates) and mutation["all_have_teeth"]) else 3


if __name__ == "__main__":
    sys.exit(main())
