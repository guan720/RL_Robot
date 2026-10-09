#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C2 · S4/B4 `harness/env_gym_aloha.py` 的闸（双向有牙；裁定 54 指派 C2 主责）。

## 两种模式（**默认不占 GPU**）
* `--mode offline`（默认）：只测 `judge_from_facts` 这个**纯函数**层 —— 不 import mujoco、
  不构造 env、不渲染。四类判定（success/failure/timeout/unknown）、方向参数化、
  反 flick 持稳、与 env `reward==4` 的交叉核验，全部可在 CPU 上判定。
* `--mode online`：构造真 env（需要 `pi05_sim` venv + 可用 GL 后端）。测实测 Hz / 子步数 /
  扁平化 obs 可入库 / 嵌套原样 obs 不可入库 / manifest / DT 变异。
  **会用到 GPU（EGL 渲染）**：单卡优先权 A2 > C2（裁定 46.x），所以只在 `--online` 时碰，
  并在产物里记 GPU 显存前后值与 `MUJOCO_GL`。
* `--with-render`（仅在 online 下有意义）：额外测「三路图像 + state 入库 → 消费侧按 env 的
  键契约返回 14 维向量」，即 **B3（键覆盖闸）× B4（env 接线）的端到端对接**。

## 牙（裁定 27.1：恒真的闸等于没有闸）
* 正向：J1–J10 / E1–E6 全绿才 PASS。
* 反向：
  - `J11`：把 `hold_min_steps` 降到 0 ⇒ J2 的"持稳不足"必须**变成 success**
    （证明反 flick 的牙真来自阈值，不是文案）；
  - `J12`：把 `target_side` 写死成 `left` ⇒ 反向（left_to_right）判定必须被翻转
    （证明方向是**参数**而不是装饰）；
  - `E6`：把 `dt` 改回 0.02（50 Hz）⇒ 构造必须 `EnvContractError`（裁定 53 的频率红线）。

## 纪律
* 不改任何人的文件；变异用**进程内替换**并在产物里标 `mutation_kind=in_process`。
* 计数/不存在类主张带 (mtime, 行数, 命令)；数值主张带 loadavg + nr_throttled。
* 状态词只用 v4 五档；产物里不出现「跑通 / 学会 / 达标」。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CST = timezone(timedelta(hours=8))
GATE_ID = "c2_gate_env_gym_aloha"
TASK_ID = "S4/B4"


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def sha12(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:12]


def fingerprint(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    raw = p.read_bytes()
    return {"path": str(p), "sha256_12": sha12(raw), "n_bytes": len(raw),
            "n_lines": raw.decode("utf-8", "replace").count("\n"),
            "mtime": datetime.fromtimestamp(p.stat().st_mtime, CST).isoformat(timespec="seconds")}


def machine_block() -> dict:
    la = Path("/proc/loadavg").read_text().split()
    cs = {}
    p = Path("/sys/fs/cgroup/cpu/cpu.stat")
    if p.exists():
        for line in p.read_text().splitlines():
            k, _, v = line.partition(" ")
            cs[k] = int(v)
    return {"ts": now_iso(), "loadavg_1m": float(la[0]), "loadavg_5m": float(la[1]),
            "loadavg_15m": float(la[2]), "cpu_stat": cs,
            "parallelism_denominator": "12-core cgroup quota（不是 nproc）",
            "nproc_host_not_the_denominator": os.cpu_count(),
            "mujoco_gl": os.environ.get("MUJOCO_GL"),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}


def gpu_block() -> dict:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True,
                             timeout=30)
        return {"available": out.returncode == 0, "raw": out.stdout.strip()}
    except Exception as exc:                                   # noqa: BLE001
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------ offline：纯判定层
# 夹具用**二进制可精确表示**的数（0.25 / 0.375 / 0.125）：
# 早先一版把 box_z 放在 0.30、table_z 0.25，离桌高度算出 0.04999999999999999 < 0.05
# ⇒ J1/J2/J5/J11/J12 五条一起假红。边界效应必须**显式**测（见 J14），不许靠夹具巧合踩到。
def facts(box=(0.30, 0.00, 0.375), speed=0.05, table_z=0.25,
          left_finger=(0.30, 0.02, 0.375), right_finger=(0.10, -0.30, 0.10),
          contact_left=True, contact_right=False, contact_table=False,
          env_reward=4, env_is_success=True, step=10, horizon=300):
    from harness.env_gym_aloha import JudgmentFacts
    return JudgmentFacts(box_xyz=tuple(box), box_speed_mps=speed, table_z_ref=table_z,
                         finger_xyz={"left": tuple(left_finger), "right": tuple(right_finger)},
                         contact_box_finger={"left": contact_left, "right": contact_right},
                         contact_box_table=contact_table, env_reward=env_reward,
                         env_is_success=env_is_success, step_index=step, horizon=horizon)


def run_offline() -> list[dict]:
    import harness.env_gym_aloha as g
    import harness.ledger as ledger
    checks: list[dict] = []

    def add(cid, claim, expected, measured, evidence=None):
        checks.append({"id": cid, "claim": claim, "expected": expected, "measured": measured,
                       "ok": expected == measured, "evidence": evidence})

    th = g.JudgeThresholds()

    # J1 正常成功（右→左，左爪夹住、离桌、慢、持稳够）
    j = g.judge_from_facts(facts(), direction="right_to_left", thresholds=th, hold_steps=6)
    add("J1", "右→左：左爪夹住 + 离桌 + 低速 + 持稳 6 步 ⇒ success / value=1.0 / label=success",
        {"outcome": "success", "value": 1.0, "label": "success"},
        {"outcome": j.outcome_class, "value": j.value, "label": j.label_kind},
        {"reasons": list(j.reasons), "geometric_success": j.geometric_success})

    # J2 持稳不足 ⇒ 不许判成功（反 flick 主力）
    j2 = g.judge_from_facts(facts(), direction="right_to_left", thresholds=th, hold_steps=2)
    add("J2", "同样几何但只持稳 2 步 < hold_min_steps=5 ⇒ 非 success，且理由点名持稳",
        {"not_success": True, "mentions_hold": True},
        {"not_success": j2.outcome_class != "success",
         "mentions_hold": any("持稳" in r for r in j2.reasons)},
        {"outcome": j2.outcome_class, "reasons": list(j2.reasons)})

    # J3 弹射：高速 ⇒ 非 success，理由点名 flick
    j3 = g.judge_from_facts(facts(speed=3.0), direction="right_to_left", thresholds=th, hold_steps=9)
    add("J3", "方块线速度 3.0 m/s > 上限 0.60 ⇒ 非 success，理由点名弹射/flick",
        {"not_success": True, "mentions_flick": True},
        {"not_success": j3.outcome_class != "success",
         "mentions_flick": any("flick" in r or "弹射" in r for r in j3.reasons)},
        {"outcome": j3.outcome_class, "reasons": list(j3.reasons)})

    # J4 反向任务里 env 的 reward==4 假阳性 ⇒ 交叉核验必须红
    #   事实：左爪把方块抬起来了（env: reward=4 / is_success=True），但方向是**左→右**，
    #   目标侧是右爪，而右爪离方块很远 ⇒ 几何真值 = 未成功。
    f4 = facts(contact_left=True, contact_right=False, env_reward=4, env_is_success=True)
    j4 = g.judge_from_facts(f4, direction="left_to_right", thresholds=th, hold_steps=9)
    raised = None
    try:
        g.GymAlohaSimEnv.cross_check(None, j4) if False else None
    except Exception:                                          # noqa: BLE001
        pass
    # cross_check 是实例方法；这里直接用它的判据（agreement is False ⇒ 红）并复现其抛出行为
    try:
        _CrossCheckStub(j4).run(g)
        raised = False
    except g.JudgmentDisagreement as exc:
        raised = str(exc)
    add("J4", "反向（左→右）任务里 env `reward==4` 假阳性 ⇒ 几何真值不采信、交叉核验判红",
        {"geometric_success": False, "env_success": True, "agreement": False, "raises": True},
        {"geometric_success": j4.geometric_success, "env_success": j4.env_success,
         "agreement": j4.agreement, "raises": bool(raised)},
        {"env_judgment_source": "gym_aloha/env.py:178-180 reward==4；tasks/sim.py:145-148 只要求接触+离桌",
         "disagreement_message": (raised or "")[:300], "reasons": list(j4.reasons)})

    # J5 方向是参数：同一份事实，方向翻 ⇒ 目标侧翻 ⇒ 结论翻
    j5a = g.judge_from_facts(facts(), direction="right_to_left", thresholds=th, hold_steps=9)
    j5b = g.judge_from_facts(facts(), direction="left_to_right", thresholds=th, hold_steps=9)
    add("J5", "同一份几何事实下方向翻转 ⇒ 结论必须翻转（方向不是写死的常量）",
        {"r2l": "success", "l2r_not": True},
        {"r2l": j5a.outcome_class, "l2r_not": j5b.outcome_class != "success"},
        {"r2l_reasons": list(j5a.reasons)[:2], "l2r_reasons": list(j5b.reasons)[:3]})

    # J6 读不到目标侧指位置 ⇒ unknown（不猜）
    j6 = g.judge_from_facts(facts(left_finger=(float("nan"),) * 3), direction="right_to_left",
                            thresholds=th, hold_steps=9)
    add("J6", "目标侧指 geom 位置不可读 ⇒ outcome=unknown / value=None / label_kind=unknown",
        {"outcome": "unknown", "value": None, "label": "unknown"},
        {"outcome": j6.outcome_class, "value": j6.value, "label": j6.label_kind},
        {"reasons": list(j6.reasons)})

    # J7 到 horizon 且未成功 ⇒ timeout（不是 failure）
    j7 = g.judge_from_facts(facts(contact_left=False, contact_table=True, env_reward=0,
                                  env_is_success=False, step=300, horizon=300,
                                  left_finger=(0.9, 0.9, 0.9)),
                            direction="right_to_left", thresholds=th, hold_steps=0)
    add("J7", "步数达到 horizon 且未成功 ⇒ timeout（与 failure 分开，不许混成一类）",
        "timeout", j7.outcome_class, {"reasons": list(j7.reasons)})

    # J8 四类都映射到 ledger 既有词表（不新造 label_kind）
    produced = {j.label_kind for j in (
        g.judge_from_facts(facts(), direction="right_to_left", thresholds=th, hold_steps=9),
        j2, j7, j6)}
    add("J8", "四类判定映射出的 label_kind 全在 harness/ledger.py 的 LABEL_KINDS 里（不新造词表）",
        {"subset": True, "kinds": sorted(produced)},
        {"subset": produced <= set(ledger.LABEL_KINDS), "kinds": sorted(produced)},
        {"ledger_LABEL_KINDS": list(ledger.LABEL_KINDS),
         "ledger_file": fingerprint(REPO_ROOT / "harness" / "ledger.py")})

    # J9 env 没给判定 ⇒ agreement=None（不是"一致"）
    j9 = g.judge_from_facts(facts(env_is_success=None, env_reward=None),
                            direction="right_to_left", thresholds=th, hold_steps=9)
    add("J9", "env 未给 is_success ⇒ agreement=None（不可比 ≠ 一致，不许静默当绿）",
        None, j9.agreement, {"env_success": j9.env_success})

    # J10 仍接触桌面 ⇒ 非 success
    j10 = g.judge_from_facts(facts(contact_table=True), direction="right_to_left",
                             thresholds=th, hold_steps=9)
    add("J10", "方块仍与桌面接触 ⇒ 非 success（沿用 env 的离桌语义，但只是几何条件之一）",
        True, j10.outcome_class != "success", {"reasons": list(j10.reasons)})

    # J11 反向变异：hold_min_steps=0 ⇒ J2 的事实必须变成 success（牙来自阈值）
    loose = g.JudgeThresholds(hold_min_steps=0)
    j11 = g.judge_from_facts(facts(), direction="right_to_left", thresholds=loose, hold_steps=2)
    add("J11", "反向变异：hold_min_steps=0 ⇒ 只持稳 2 步也判 success（证明 J2 的牙来自阈值）",
        {"j2_strict": "not_success", "j11_loose": "success"},
        {"j2_strict": "not_success" if j2.outcome_class != "success" else "success",
         "j11_loose": j11.outcome_class},
        {"mutation_kind": "in_process（换阈值对象，不改文件）",
         "thresholds_loose": loose.as_dict()})

    # J12 反向变异：target_side 写死 left ⇒ 反向判定被翻转（证明方向是参数）
    original = g.target_side
    g.target_side = lambda direction: "left"
    try:
        j12 = g.judge_from_facts(facts(), direction="left_to_right", thresholds=th, hold_steps=9)
    finally:
        g.target_side = original
    add("J12", "反向变异：把 target_side 写死成 left ⇒ 左→右的判定被翻转成 success（方向确实在起作用）",
        {"before_mutation": "not_success", "after_mutation": "success"},
        {"before_mutation": "not_success" if j5b.outcome_class != "success" else "success",
         "after_mutation": j12.outcome_class},
        {"mutation_kind": "in_process（临时替换 target_side，已 finally 复原）",
         "restored": g.target_side is original})

    # J14 边界语义：离桌高度**恰好等于**阈值 ⇒ 判成功（>= 语义，不是 >）
    exact = g.JudgeThresholds(lift_min_height_m=0.125)
    j14 = g.judge_from_facts(facts(), direction="right_to_left", thresholds=exact, hold_steps=9)
    add("J14", "离桌高度恰好等于阈值（0.375-0.25=0.125，二进制精确）⇒ success（>= 语义，不是 >）",
        {"height_exact": 0.125, "outcome": "success"},
        {"height_exact": round(float(np.asarray(facts().box_xyz)[2] - facts().table_z_ref), 12),
         "outcome": j14.outcome_class},
        {"thresholds": exact.as_dict(), "reasons": list(j14.reasons)})

    # J15 裁定 62-③：超时判定按**秒**登记（300 步 @29.4118 Hz = 10.2 s），不按步数并列
    add("J15", "timeout 判定带秒口径：elapsed_s / horizon_s = 步数 × dt（300×0.034 = 10.2 s）",
        {"outcome": "timeout", "horizon_s": round(300 * g.shim.MAINLINE_DT, 4),
         "mentions_seconds": True},
        {"outcome": j7.outcome_class, "horizon_s": j7.horizon_s,
         "mentions_seconds": any(" s" in r and "10.2" in r for r in j7.reasons)},
        {"elapsed_s": j7.elapsed_s, "reasons": [r for r in j7.reasons if "timeout" in r or "s（" in r or "10.2" in r],
         "dt_source": "envs/gym_aloha_shim.MAINLINE_DT（A2 拥有）"})

    # J13 outcome_class 词表封闭
    allj = [j, j2, j3, j4, j5a, j5b, j6, j7, j9, j10, j11, j12, j14]
    add("J13", "所有判定的 outcome_class 都在四类词表内（不许冒出第五类）",
        True, all(x.outcome_class in g.OUTCOME_CLASSES for x in allj),
        {"observed": sorted({x.outcome_class for x in allj}), "vocabulary": list(g.OUTCOME_CLASSES)})

    return checks


class _CrossCheckStub:
    """复用 `GymAlohaSimEnv.cross_check` 的判据而不构造 env（它需要 GL 后端）。

    之所以不直接调实例方法：cross_check 只依赖 judgment，不依赖物理状态；
    这里把它的**判定逻辑**原样搬过来会造成分叉 ⇒ 改为构造一个只带 `_last_judgment`
    的空壳对象，调**同一个**未绑定函数，保证测的是仓库里那份实现。
    """

    def __init__(self, judgment):
        self._last_judgment = judgment

    def run(self, g):
        return g.GymAlohaSimEnv.cross_check(self, None)


# ------------------------------------------------------------------ online：真 env
def run_online(*, with_render: bool) -> list[dict]:
    import harness.env_gym_aloha as g
    from harness.obs_store import ObsStore
    from harness import queue_td_learner as qtl

    checks: list[dict] = []

    def add(cid, claim, expected, measured, evidence=None):
        checks.append({"id": cid, "claim": claim, "expected": expected, "measured": measured,
                       "ok": expected == measured, "evidence": evidence})

    gpu_before = gpu_block()
    spec = g.EnvSpec(render_images=with_render)
    env = g.GymAlohaSimEnv(spec)
    t = env.timing

    add("E1", "实测控制频率 = 29.4118 Hz（DT=0.034、17 子步），且 site-packages 未被改",
        {"hz": round(g.shim.MAINLINE_HZ, 6), "substeps": g.shim.MAINLINE_SUBSTEPS,
         "qc": True, "mainline": True, "sitepackages": False},
        {"hz": t.get("control_hz"), "substeps": t.get("n_sub_steps"),
         "qc": t.get("in_qc_band_29_31"), "mainline": t.get("matches_mainline"),
         "sitepackages": bool(env.apply_record.get("site_packages_modified", False))},
        {"timing": t, "apply_record": env.apply_record, "gpu_before": gpu_before})

    obs0 = env.reset(seed=20260929)
    st = np.asarray(obs0[g.STATE_KEY])
    add("E2", "reset 后 state 是 14 维、桌面参考 z 可自标定、方块与双指 geom 都读得到",
        {"state_shape": [g.STATE_DIM], "table_z_finite": True, "geoms_finite": True},
        {"state_shape": list(st.shape), "table_z_finite": bool(np.isfinite(env._table_z_ref)),
         "geoms_finite": bool(np.isfinite(env._prev_box).all() if env._prev_box is not None
                              else np.isfinite(np.asarray(
                                  env.physics.named.data.geom_xpos[g.GEOM_BOX])).all())},
        {"table_z_ref": env._table_z_ref,
         "box_xyz": list(np.asarray(env.physics.named.data.geom_xpos[g.GEOM_BOX], dtype=float)),
         "state_14d": [round(float(x), 6) for x in st],
         "max_abs_state": round(float(np.abs(st).max()), 6)})

    # E3 嵌套原样 obs 不可入库 / 扁平化后可以（G12 的在线复核）
    raw_obs, _info = env.env.reset(seed=20260929)
    store = ObsStore(root=REPO_ROOT / "runs/vla/c2_env_gym_aloha_20260929/gate_obs_store",
                     contract_version="v4-appendix01-2.3")
    try:
        store.put(raw_obs, sampled_at_ns=1, representation_version="c2-e3", episode_id="e3raw")
        nested = {"raised": False}
    except TypeError as exc:
        nested = {"raised": True, "message": str(exc)}
    flat_keys = sorted(env.observation())
    try:
        meta = store.put(env.observation(), sampled_at_ns=2,
                         representation_version="c2-e3", episode_id="e3flat")
        flat = {"raised": False, "keys": list(meta.keys), "nbytes": int(meta.nbytes)}
    except Exception as exc:                                   # noqa: BLE001
        flat = {"raised": True, "message": f"{type(exc).__name__}: {exc}"}
    add("E3", "env 原样 obs 是嵌套 dict ⇒ 不可内容寻址；本模块扁平化后可以（含键集合枚举）",
        {"nested_raises": True, "flat_raises": False},
        {"nested_raises": nested.get("raised", False), "flat_raises": flat.get("raised", True)},
        {"raw_obs_top_level_keys": sorted(raw_obs),
         "raw_obs_is_nested": any(isinstance(v, dict) for v in raw_obs.values()),
         "nested_error": nested.get("message"),
         "flat_keys_stored": flat_keys, "n_flat_keys": len(flat_keys),
         "flat_payload_nbytes": flat.get("nbytes"),
         "provenance": "gym_aloha/env.py:143-148；harness/obs_store.py:92 的 object 数组卫语句"})

    # E4 manifest 完整性
    man = env.manifest()
    required = ["module_sha256_12", "shim_sha256_12", "measured_control_hz", "dt",
                "direction", "horizon_option", "horizon_decision_status", "cam_map",
                "obs_contract", "judge_thresholds", "env_judgment_semantics",
                "site_packages_modified", "qc_band_hz", "per_step_budget_ms"]
    add("E4", "manifest 含 shim sha256-12 / 实测 Hz / 方向 / 阈值 / 键契约 / horizon 待裁状态",
        {"missing": []}, {"missing": [k for k in required if k not in man]},
        {"manifest_subset": {k: man[k] for k in required if k in man},
         "shim_path": str(g.shim.SHIM_PATH)})

    # E5 反向方向可构造，且 target_side 翻
    spec_r = g.EnvSpec(direction="left_to_right", render_images=False)
    add("E5", "反向（left_to_right）spec 合法且目标侧翻成 right",
        {"side": "right", "in_vocabulary": True},
        {"side": g.target_side(spec_r.direction), "in_vocabulary": spec_r.direction in g.DIRECTIONS})

    # E6 DT 变异：改回 0.02（50 Hz）⇒ 必须拒绝构造
    try:
        g.GymAlohaSimEnv(g.EnvSpec(dt=0.02, render_images=False))
        dt_mut = {"raised": False}
    except g.EnvContractError as exc:
        dt_mut = {"raised": True, "message": str(exc)}
    except Exception as exc:                                   # noqa: BLE001
        dt_mut = {"raised": True, "type": type(exc).__name__, "message": str(exc)}
    add("E6", "反向变异：把 dt 改回 0.02（50 Hz）⇒ 构造必须被拒（裁定 53 的频率红线）",
        True, dt_mut.get("raised", False),
        {"mutation_kind": "input（换 spec.dt，不改文件）", "detail": dt_mut})

    # E7 端到端：三路图像 + state 入库 → 消费侧按 env 的键契约返回 14 维（B3 × B4 对接）
    if with_render:
        # 用**不同 seed** 走包装器的 reset：ObsStore 是内容寻址的，
        # 同 seed 会得到逐字节相同的观测，再 put 会触发 StaleObservation（那是 obs_store 的既有纪律）。
        env.reset(seed=20260930)
        obs = env.observation()
        meta = store.put(obs, sampled_at_ns=3, representation_version="c2-e7", episode_id="e7")
        cfg = qtl.LearnerConfig(state_dim=g.STATE_DIM, action_dim=g.STATE_DIM, n=2, gamma=0.99,
                                obs_key_contract=spec.obs_contract())
        try:
            vec = qtl._obs_vector(store, meta.obs_ref, cfg, kind="E7")
            res = {"outcome": "returned", "width": int(vec.shape[0])}
        except qtl.LearnerRefused as exc:
            res = {"outcome": "refused", "message": str(exc)}
        add("E7", "带三路图像的扁平 obs 入库后，消费侧按 env 的键契约返回 14 维（B3×B4 端到端对接）",
            {"outcome": "returned", "width": g.STATE_DIM}, res,
            {"keys_stored": list(meta.keys), "payload_nbytes": int(meta.nbytes),
             "payload_KB": round(int(meta.nbytes) / 1024, 2),
             "contract": spec.obs_contract().as_dict()})
        # E8 反向：不声明图像键（用默认契约）⇒ 必须点名拒绝
        cfg_def = qtl.LearnerConfig(state_dim=g.STATE_DIM, action_dim=g.STATE_DIM, n=2, gamma=0.99)
        try:
            qtl._obs_vector(store, meta.obs_ref, cfg_def, kind="E8")
            res8 = {"outcome": "returned"}
        except qtl.LearnerRefused as exc:
            res8 = {"outcome": "refused",
                    "named_all_three": all(k in str(exc) for k in spec.image_keys())}
        add("E8", "同一条带图像的快照、但消费侧不声明图像键 ⇒ 必须点名拒绝三路（不许静默丢图）",
            {"outcome": "refused", "named_all_three": True}, res8,
            {"message": (res8.get("message") or "")[:300]})

    # E11 反向变异（裁定 62-② / 57.4）：**只改一半的 monkeypatch** 必须被判红
    #   `gym_aloha/env.py:7`–`:12` 是 `from gym_aloha.constants import (…, DT, …)` ⇒
    #   只改 `constants.DT` 对已 import 的 `env.DT` 无效，会**静默留在 50 Hz**。
    import gymnasium as gym
    import gym_aloha                                    # noqa: F401  触发注册
    import gym_aloha.constants as ga_const
    import gym_aloha.env as ga_env
    saved = (ga_const.DT, ga_env.DT)
    half = {"constructed": False, "measured_hz": None, "refused": False, "message": None,
            "constants_dt": None, "env_module_dt": None}
    half_env = None
    try:
        ga_const.DT = g.shim.MAINLINE_DT                   # **只改这一半**
        half["constants_dt"] = ga_const.DT
        half["env_module_dt"] = ga_env.DT
        half_env = gym.make(g.shim.ENV_ID, obs_type="pixels_agent_pos", render_mode="rgb_array")
        half["constructed"] = True
        half["measured_hz"] = g.shim.read_live_timing(half_env).get("control_hz")
        try:
            g.GymAlohaSimEnv(g.EnvSpec(render_images=False), env=half_env,
                             apply_record={"applied": True, "site_packages_modified": False})
        except g.EnvContractError as exc:
            half["refused"] = True
            half["message"] = str(exc)
    finally:
        ga_const.DT, ga_env.DT = saved
        if half_env is not None:
            try:
                half_env.close()
            except Exception:                              # noqa: BLE001
                pass
    add("E11", "反向变异（裁定 62-②）：只改 `constants.DT`、不改 `env.DT` ⇒ 实测仍是 50 Hz，本模块必须拒绝构造",
        {"half_patch_silently_50hz": True, "refused": True, "restored": True},
        {"half_patch_silently_50hz": half["measured_hz"] is not None
         and abs(float(half["measured_hz"]) - 50.0) < 1e-6,
         "refused": half["refused"],
         "restored": (ga_const.DT, ga_env.DT) == saved},
        {"mutation_kind": "in_process monkeypatch（只改一半；finally 复原，不改 site-packages 文件）",
         "detail": half, "a2_reference": "envs/gym_aloha_shim.py 模块 docstring + scripts/a2_hz_shim_verify.py 的 patch_mechanism_proof",
         "restored_dt": [ga_const.DT, ga_env.DT]})

    # E12 裁定 62-③：manifest 必须带 episode_horizon_s（10.2 s），不是只给步数
    add("E12", "manifest 带 `episode_horizon_s` = 300 × 0.034 = 10.2 s（裁定 58.3 / 62-③）",
        {"episode_horizon_s": 10.2, "horizon_steps": 300},
        {"episode_horizon_s": man.get("episode_horizon_s"), "horizon_steps": man.get("horizon_steps")},
        {"horizon_decision_status": man.get("horizon_decision_status"),
         "horizon_ruling_ref": man.get("horizon_ruling_ref"),
         "note": "裁定 58.3 已裁：保持 300 步不缩放；A2 的 B 案（rescale_176=6.0 s）已作废"})

    # E14 裁定 58.3 的牙：选已作废的 B 案（rescale_176）必须**响亮拒绝**，不静默执行
    try:
        g.EnvSpec(horizon_option="rescale_176").horizon_steps()
        refused176 = {"raised": False}
    except g.EnvContractError as exc:
        refused176 = {"raised": True, "message": str(exc)}
    add("E14", "裁定 58.3 的牙：horizon_option='rescale_176'（B 案已作废）⇒ 必须拒绝，不静默换步数",
        True, refused176.get("raised", False),
        {"detail": refused176, "registered_300_steps": g.EnvSpec().horizon_steps(),
         "episode_horizon_s": round(g.EnvSpec().horizon_steps() * g.shim.MAINLINE_DT, 4)})

    # E13 裁定 59：后端必须进五元标注（跨后端吞吐数字不得互搬）
    five = man.get("five_tuple_annotation", {})
    add("E13", "manifest 的五元标注齐（venv / MUJOCO_GL 后端 / mujoco 版本 / 模型 / 相机与分辨率）",
        {"missing": []},
        {"missing": [k for k in ("venv", "mujoco_gl_backend", "mujoco_version", "model",
                                 "cameras", "resolution") if not five.get(k)]},
        {"five_tuple": five,
         "why": "裁定 59：egl+NVIDIA vendor 与 osmesa 差 13.8×，后端不入标注就等于允许互搬"})

    gpu_after = gpu_block()
    checks.append({"id": "E9", "claim": "GPU 占用记录（单卡优先权 A2 > C2；本次为秒级）",
                   "expected": True, "measured": True, "ok": True,
                   "evidence": {"gpu_before": gpu_before, "gpu_after": gpu_after,
                                "mujoco_gl": os.environ.get("MUJOCO_GL"),
                                "interpreter": sys.executable}})
    try:
        env.env.close()
    except Exception as exc:                                   # noqa: BLE001
        checks.append({"id": "E10", "claim": "env.close() 不崩（A2 记录过 osmesa 在 close 时崩）",
                       "expected": True, "measured": False, "ok": False,
                       "evidence": {"error": f"{type(exc).__name__}: {exc}",
                                    "mujoco_gl": os.environ.get("MUJOCO_GL")}})
    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description="C2 · S4/B4 env 接线闸")
    ap.add_argument("--mode", default="offline", choices=["offline", "online", "full"])
    ap.add_argument("--with-render", action="store_true",
                    help="online 下额外跑 E7/E8（需要可用 GL 后端，会渲染三路图像）")
    ap.add_argument("--out", default="runs/vla/c2_env_gym_aloha_20260929")
    args = ap.parse_args()

    out_root = Path(args.out) if Path(args.out).is_absolute() else (REPO_ROOT / args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    before = machine_block()
    t0 = time.time()
    checks: list[dict] = []
    modes_run = []
    if args.mode in ("offline", "full"):
        checks += run_offline()
        modes_run.append("offline")
    if args.mode in ("online", "full"):
        checks += run_online(with_render=args.with_render)
        modes_run.append("online" + ("+render" if args.with_render else ""))
    after = machine_block()

    reds = [c["id"] for c in checks if not c["ok"]]
    report = {
        "gate_id": GATE_ID, "task_id": TASK_ID, "generated_at": now_iso(),
        "modes_run": modes_run, "with_render": bool(args.with_render),
        "verdict": "PASS" if not reds else "RED",
        "n_checks": len(checks), "n_red": len(reds), "red_ids": reds,
        "checks": checks,
        "machine_before": before, "machine_after": after,
        "nr_throttled_delta": after["cpu_stat"].get("nr_throttled", 0)
        - before["cpu_stat"].get("nr_throttled", 0),
        "elapsed_s": round(time.time() - t0, 3),
        "gate_script": fingerprint(Path(__file__).resolve()),
        "probed_files": [fingerprint(REPO_ROOT / "harness" / "env_gym_aloha.py"),
                         fingerprint(REPO_ROOT / "envs" / "gym_aloha_shim.py"),
                         fingerprint(REPO_ROOT / "harness" / "obs_key_coverage.py")],
        "interpreter": {"path": sys.executable, "python": platform.python_version(),
                        "numpy": np.__version__},
        "status_word_v4": ("回放通过（离线纯判定层）" if args.mode == "offline"
                           else "仿真通过（真 env 构造与判定层，不含任何能力主张）"),
    }
    suffix = "offline" if args.mode == "offline" else args.mode
    path = out_root / f"gate_verdict_{suffix}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[{GATE_ID}] mode={args.mode} verdict={report['verdict']} "
          f"n_checks={report['n_checks']} red={reds} "
          f"nr_throttled_delta={report['nr_throttled_delta']} -> {path}", flush=True)
    for c in checks:
        print(f"  [{'PASS' if c['ok'] else 'RED '}] {c['id']}: {c['claim'][:88]}", flush=True)
    return 0 if not reds else 1


if __name__ == "__main__":
    raise SystemExit(main())
