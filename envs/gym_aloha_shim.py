"""**裁定 53 / 53.5** 的主线仿真频率 shim：把 `gym_aloha` 的控制周期从 50 Hz 改成 **29.4118 Hz**。

D 的实现约束（`rl_harness_supervision/d_simchain_e2emin_20260929.md` §2-4）原文：
  「`DT` 是 `gym_aloha/constants.py:4` 的模块级常量、被 `env.py:134` 传给
   `control.Environment(control_timestep=DT)` ⇒ **不许改 site-packages 原文件**。
   必须在**本仓自有 shim** 内（建议 `envs/gym_aloha_shim.py`）改口径，
   产物记 `representation_version` + shim 的 `sha256-12` + **实测 Hz**。」

## 为什么必须同时patch两个名字（本 shim 的核心，不是形式）

`gym_aloha/env.py:7`–`:12` 是 **`from gym_aloha.constants import (…, DT, …)`** ⇒ `DT` 在 `env.py`
里是**模块级已绑定名字**；`env.py:44` 在 `AlohaEnv.__init__` 里调 `_make_env_task()`，
`env.py:133`–`:135` 用的就是那个**已绑定的** `DT`。
⇒ **只改 `gym_aloha.constants.DT` 对已 import 的 `env.py` 无效**（会静默地仍是 50 Hz）。
本 shim **两个都改**，并把「只改 constants 不够」做成可复现的变异实验
（`scripts/a2_hz_shim_verify.py` 的 `patch_mechanism_proof` 段）。

## 为什么是 0.034 而不是 1/30（裁定 53）

`dm_control/rl/control.py:168`–`:194` 的 `compute_n_steps(control_timestep, physics_timestep, tolerance=1e-8)`
对**非整数倍是 `raise ValueError`，不是四舍五入** ⇒ `DT=1/30` 配 `timestep=0.002` **直接构造失败**。
精确 30.0 Hz 只能把模型 `timestep` 改成 `1/480`（= 改第三方资产，需接触/稳定性 A/B + D 批，默认不走）。
`DT=0.034 = 17 × 0.002` ⇒ **整数倍、构造成功**、折算 **29.411764… Hz**，落在团队 QC 区间 **[29.0, 31.0]**。

## 边界

- **不改 site-packages**：只在运行时改模块属性；`gym_aloha` 的文件**一个字节都不动**。
- **不碰冻结面**：本文件在 `envs/`（非 `harness/`、非 `registry/`、非 `configs/`）。
- **`max_episode_steps` 语义变化必须显式登记**：注册时是 300（`gym_aloha/__init__.py:16`），
  改 DT 后 **300 步 = 10.2 s 仿真时长**（原来 6.0 s）⇒ 见 `episode_horizon()`，**由 D 裁**是否同步缩放步数预算。
- **跨口径禁令（裁定 46.4 / 53.3）**：本 shim 产出的任何吞吐数字都必须带
  `(venv, MUJOCO_GL 后端, mujoco 版本, 模型, 相机数, 分辨率)`，**不得与 D 的 osmesa/Piper 数字或 A2 G3 的 egl 数字互搬**。
"""

from __future__ import annotations

import hashlib
import pathlib

# ---------------- 裁定 53 的主线口径（常量，不要就地改；改口径 = 换 representation_version） ----------------
MAINLINE_DT = 0.034                      # = 17 × 0.002 s
MAINLINE_PHYSICS_TIMESTEP = 0.002        # gym_aloha 的 XML 自带，本 shim **不改**它
MAINLINE_SUBSTEPS = 17
MAINLINE_HZ = 1.0 / MAINLINE_DT          # 29.411764705882355
QC_BAND_HZ = (29.0, 31.0)                # 团队 QC 区间（裁定 45/53 沿用）
PER_STEP_BUDGET_MS = 34.0                # 裁定 53-2：**硬预算 34.0 ms**（33.3 ms/30 Hz 降为名义锚）
NOMINAL_ANCHOR_HZ = 30.0                 # 仅作名义锚，**不得**用于延迟判定
REGISTERED_MAX_EPISODE_STEPS = 300       # gym_aloha/__init__.py:16
REPRESENTATION_VERSION = "gym_aloha_dt0.034_29.4118hz_shim_v1"
ENV_ID = "gym_aloha/AlohaTransferCube-v0"

SHIM_PATH = pathlib.Path(__file__).resolve()


def shim_sha256_12() -> str:
    """D §2-4 要求产物记 shim 的 `sha256-12`。"""
    return hashlib.sha256(SHIM_PATH.read_bytes()).hexdigest()[:12]


def control_hz(dt: float) -> float:
    return 1.0 / dt


def in_qc_band(hz: float) -> bool:
    return QC_BAND_HZ[0] <= hz <= QC_BAND_HZ[1]


def substeps_or_error(dt: float, physics_timestep: float = MAINLINE_PHYSICS_TIMESTEP):
    """复用 **dm_control 自己的** `compute_n_steps`（不另写一套判据）：整数倍 ⇒ 步数；否则 ⇒ 它抛的 ValueError。

    返回 `(n_sub_steps, None)` 或 `(None, error_repr)`。**故意不吞异常语义**：
    「非整数倍会失败」这件事必须原样可见，否则下一个改 DT 的人会以为是四舍五入。
    """
    from dm_control.rl.control import compute_n_steps
    try:
        return int(compute_n_steps(dt, physics_timestep)), None
    except ValueError as e:
        return None, f"ValueError: {e}"


def apply_dt(dt: float = MAINLINE_DT, verify: bool = True) -> dict:
    """把 `DT` 改成本仓口径。**必须两处都改**（见模块 docstring）。

    返回一份可落盘的记录（含改前/改后、两处名字是否都生效、QC 判定、指纹）。
    """
    import gym_aloha.constants as C
    import gym_aloha.env as E

    n_sub, err = substeps_or_error(dt)
    hz = control_hz(dt)
    rec = {
        "requested_dt": dt,
        "requested_hz": round(hz, 6),
        "in_qc_band_29_31": in_qc_band(hz),
        "physics_timestep_expected": MAINLINE_PHYSICS_TIMESTEP,
        "n_sub_steps_from_dm_control": n_sub,
        "compute_n_steps_error": err,
        "integer_multiple": err is None,
        "constants_dt_before": getattr(C, "DT", None),
        "env_module_dt_before": getattr(E, "DT", None),
        "representation_version": REPRESENTATION_VERSION,
        "shim_path": str(SHIM_PATH),
        "shim_sha256_12": shim_sha256_12(),
        "site_packages_modified": False,
    }
    if err is not None:
        rec["applied"] = False
        rec["why_not_applied"] = ("`compute_n_steps` 会 `raise ValueError` ⇒ **拒绝应用**，"
                                  "不静默退化成四舍五入（裁定 53 的根因就是这个误解）")
        return rec

    C.DT = dt
    E.DT = dt
    rec["applied"] = True
    rec["constants_dt_after"] = C.DT
    rec["env_module_dt_after"] = E.DT
    rec["both_names_patched"] = (C.DT == dt and E.DT == dt)
    if verify and not rec["both_names_patched"]:
        rec["applied"] = False
        rec["why_not_applied"] = "两处名字未同时生效 ⇒ 判失败（只改一处会静默留在 50 Hz）"
    return rec


def _deref(x):
    """`dm_control` 的 `Environment.control_timestep` 在**本 venv 是普通方法**（无 `@property`），
    在别的版本里可能是 property ⇒ 两种形态都吃，避免把「读不到」误报成「频率不对」。
    （同族教训：裁定 53.3 的口径搬运禁令 —— 连**读法**都不能跨 venv 搬。）"""
    return x() if callable(x) else x


def read_live_timing(env) -> dict:
    """从**已构造的** env 里把真实生效的三元组读回来（不是读常量，是读活对象）。"""
    inner = getattr(env, "unwrapped", env)
    dm = getattr(inner, "_env", None)
    out = {"read_from": "env.unwrapped._env（dm_control.rl.control.Environment）"}
    if dm is None:
        out["error"] = "找不到 AlohaEnv._env（gym_aloha 版本变了？必须重核，不许假设）"
        return out
    ct = float(_deref(dm.control_timestep))
    phys = float(_deref(dm.physics.timestep))
    out.update({
        "control_timestep_s": ct,
        "physics_timestep_s": phys,
        "control_timestep_attr_kind": "method" if callable(dm.control_timestep) else "property",
        "n_sub_steps": int(getattr(dm, "_n_sub_steps", -1)),
        "control_hz": round(1.0 / ct, 6),
        "in_qc_band_29_31": in_qc_band(1.0 / ct),
        "integer_multiple": abs(ct / phys - round(ct / phys)) <= 1e-8,
        "matches_mainline": abs(ct - MAINLINE_DT) <= 1e-12,
    })
    return out


def make_env(env_id: str = ENV_ID, dt: float = MAINLINE_DT, **kwargs):
    """先打 shim 再 `gym.make`（顺序**不能反**：`env.py:44` 在 `__init__` 里就构造了 dm_control env）。"""
    import gymnasium as gym
    import gym_aloha  # noqa: F401  触发注册
    rec = apply_dt(dt)
    if not rec.get("applied"):
        raise RuntimeError(f"gym_aloha shim 拒绝应用 dt={dt}: {rec.get('why_not_applied')} / {rec.get('compute_n_steps_error')}")
    env = gym.make(env_id, **kwargs)
    return env, rec


def episode_horizon(max_episode_steps: int = REGISTERED_MAX_EPISODE_STEPS,
                    dt: float = MAINLINE_DT, baseline_dt: float = 0.02) -> dict:
    """**改 DT 的隐藏后果**：`max_episode_steps` 是**步数**，不是秒 ⇒ 回合覆盖的仿真时长会变。

    这条必须显式登记给 S1（示范集数/时长）、S3（chunk 覆盖）、S5（评测回合）：
    300 步 @50 Hz = **6.0 s**；300 步 @29.4118 Hz = **10.2 s**（1.7×）。
    若要保持 6.0 s 的任务时长，步数预算应缩到 **176**（= round(6.0/0.034)）。
    **A2 不自行决定**，两案并列报 D。
    """
    sec = max_episode_steps * dt
    base_sec = max_episode_steps * baseline_dt
    keep = round(base_sec / dt)
    return {
        "registered_max_episode_steps": max_episode_steps,
        "simulated_seconds_at_baseline_50hz": round(base_sec, 4),
        "simulated_seconds_at_shim_hz": round(sec, 4),
        "horizon_inflation_factor": round(sec / base_sec, 4),
        "option_A_keep_300_steps": {"max_episode_steps": max_episode_steps,
                                    "simulated_seconds": round(sec, 4),
                                    "effect": "回合覆盖时长变成 1.7×；任务变**更容易**（给更多时间），与已发表的 300 步/6 s 口径不可并列"},
        "option_B_rescale_to_176_steps": {"max_episode_steps": keep,
                                          "simulated_seconds": round(keep * dt, 4),
                                          "effect": "保持 **6.0 s** 任务时长不变；但步数与 ALOHA 生态的 300 不再同值，跨论文数字要带口径"},
        "a2_recommendation": "**B（缩到 176 步）**：S1 的示范/S5 的评测应对齐**同一个任务时长**，"
                             "否则「成功率」在不同 horizon 下不可比；但**由 D 裁**，A2 不静默选。",
        "pi05_chunk_coverage_s_at_shim_hz": round(50 * dt, 4),
        "note": "π₀.₅ `chunk_size=50` ⇒ 覆盖 50×0.034 = **1.700 s**（与 D 裁定 53-2 的数字一致）",
    }
