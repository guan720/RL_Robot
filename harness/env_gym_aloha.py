"""C2 · S4/B4 主线仿真代理环境：`gym-aloha` → harness 的**加法式**接线（裁定 54 指派 C2 主责）。

## 为什么需要这个文件（D 的实测缺口，不是推测）
`harness/runtime_adapter.py`（全文 77 行）是 **mock 驱动 + 单 slot**，`harness/env_factory.py:1`–`:45`
是 **reach/robosuite 的 monkeypatch shim** ⇒ 两者都承载不了 π₀.₅ 的
「chunk=50 动作 → 29.4118 Hz 逐步下发」。出处：`d_simchain_e2emin_20260929.md` §4-S4、阻塞台账 B4。

## 分工（不越界、不重复造）
* **频率 shim 不归本文件**：`DT=0.034`（17×0.002 ⇒ 29.4118 Hz）由 **A2 的 `envs/gym_aloha_shim.py`**
  拥有（裁定 53 / §2-4）。本文件**只 import 它、只读它的常量与实测**，绝不重新声明 DT
  —— 两个位置各写一份口径正是本仓已发生四次的事故形状（裁定 46.4 / §5.3）。
* **chunk 取用/逐步下发不归本文件**：那是 A2 的 `harness/vla_runtime.py`。
* **闸与三版本记录不归本文件**：那是 B2（policy version / stats version / shim version）。
* 本文件负责：① obs 扁平化到 π₀.₅ 键契约；② 成功/失败/超时/未知四类判定；
  ③ **独立于 `reward==4` 的几何真值**并与 env 判定交叉核验（不一致 ⇒ 红）；④ 账本落行；
  ⑤ 把 ①③ 的口径写成 manifest（含 shim sha256-12 与实测 Hz）。

## ① obs 键契约（与 T-C2-2 的覆盖闸同源，不是两套口径）
`harness/obs_key_coverage.py` 的闸实测过两件事（`runs/vla/c2_obs_key_whitelist_20260929/`）：
* `gym-aloha` 的 `pixels_agent_pos` **原样返回是嵌套 dict** `{"pixels": {"top": …}, "agent_pos": …}`，
  `harness/obs_store.py:92` 的 object 数组卫语句会直接 `TypeError` ⇒ **必须扁平化后再入库**（G12）；
* 只带 `state` 而契约未声明图像 ⇒ 消费侧点名拒绝（G3/G8）；声明为必需却缺席 ⇒ 也拒绝（G5）。
⇒ 本文件的 `obs_contract()` **产出**消费侧要的那份契约，env 与 learner 用同一份键名，
不存在"env 写它的、learner 读它的"这种分叉。键名口径来自 A2：
`scripts/a2_pi05_contract_probe.py:91`–`:105`（`observation.images.base_0_rgb ← angle` 等）。

## ③ 为什么判定必须独立于 `reward==4`（读到实现原文，不是转述）
`gym_aloha/env.py:178`–`:180`：`terminated = is_success = reward == 4`；
`gym_aloha/tasks/sim.py:125`–`:149` 的 `TransferCubeTask.get_reward`：
`reward=4` 的条件是 **`("red_box","vx300s_left/10_left_gripper_finger")` 有接触 且 red_box 不接触 table`**。
由此得到两条**实测可推的缺陷**（`kind=code_read_semantics`，非能力主张）：
1. **方向写死右→左**：反向任务（左→右）里，**左爪夹起方块离桌的瞬间就满足 `reward==4`** ⇒
   反向示范会被 env 判成"成功"，而这恰恰是反向任务的**起点**，不是终点。
   （D 在 §4-S1 已写明「反向任务必须自建判据」；本文件把它变成可执行代码。）
2. **只要接触、不要求持稳**：一次弹射（flick）让方块在空中擦到左指即可判成功 ⇒
   与 `work/project_parameters.json → task.success_failure_unknown_rules` 点名的
   「须含 grasp 真值与 flick/弹射检出」直接冲突。
⇒ 本文件的几何真值判据：**目标侧夹爪夹住（几何距离）+ 离桌高度 + 连续持稳 k 步 + 速度上限**，
四条都过才算 `success`；并与 env 的 `is_success` **交叉核验**，不一致 ⇒ `JudgmentDisagreement`。

## 边界与纪律
* **不改** `harness/contracts.py`（冻结面）、**不改** `harness/ledger.py`（C 的冻结产物）：
  账本落行走**既有公开 API**（`append_label` / `append_event` / `ingest_runtime_result`），
  本文件只在外面组装。
* 四类判定映射到既有词表，不新造 label_kind：
  `success` → `label_kind="success", value=1.0`；`failure` / `timeout` → `label_kind="success", value=0.0`
  （细分进 `value_json.outcome_class`）；`unknown` → `label_kind="unknown", value=None`。
* env 产出的行入账必须声明 `observation_only=True`（`harness/ledger.py:377` 起的 fail-closed 准入闸：
  env 判定**不是**被门禁分级的裁定，不给身份就不许冒充 `physical_fact`）。
* `max_episode_steps` 语义在改 DT 后会变（300 步 = **10.2 s**，不是 6.0 s）。**裁定 58.3 已裁**：
  保持 **300 步、不缩放**，`episode_horizon_s=10.2` 必须进每份 manifest，**超时/失败一律按秒登记**，
  **跨频率对比不得按步数并列**。A2 曾提的 B 案（缩到 176 步）**已作废** ⇒ 本文件选它会**响亮拒绝**。
* 产物禁用「跑通/学会/达标」；状态词只用 v4 五档。
"""
from __future__ import annotations

import hashlib
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
CST = timezone(timedelta(hours=8))

# ---------------- A2 的频率 shim（单一事实源；本文件不重复声明 DT） ----------------
import sys                                                     # noqa: E402

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from envs import gym_aloha_shim as shim                        # noqa: E402
from harness import obs_key_coverage as okc                    # noqa: E402

MODULE_PATH = Path(__file__).resolve()
MODULE_REPRESENTATION_VERSION = "c2-env-gym-aloha-v1"

# ---------------- 键名口径（A2 实测，不自创） ----------------
STATE_KEY = "state"
CAM_MAP_DEFAULT: dict[str, str] = {
    "observation.images.base_0_rgb": "angle",
    "observation.images.left_wrist_0_rgb": "left_wrist",
    "observation.images.right_wrist_0_rgb": "right_wrist",
}
STATE_DIM = 14

# ---------------- 几何真值用到的 geom 名（读自 tasks/sim.py:125-149，不是猜的） ----------------
GEOM_BOX = "red_box"
GEOM_TABLE = "table"
GEOM_FINGER = {"left": "vx300s_left/10_left_gripper_finger",
               "right": "vx300s_right/10_right_gripper_finger"}

DIRECTIONS = ("right_to_left", "left_to_right")
OUTCOME_CLASSES = ("success", "failure", "timeout", "unknown")
HORIZON_OPTIONS = ("registered_300", "rescale_176")


class EnvContractError(RuntimeError):
    """env 侧口径不符（频率不在 QC 区间 / shim 未生效 / 键契约对不上）⇒ 拒绝构造，不静默降级。"""


class JudgmentDisagreement(RuntimeError):
    """几何真值与 env 的 `reward==4` 判定不一致 ⇒ 红（裁定 54 的显式要求）。"""


def module_sha256_12() -> str:
    return hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()[:12]


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


# ========================================================================== 判定：纯函数层
@dataclass(frozen=True)
class JudgeThresholds:
    """几何真值判据的阈值。**全部显式**，不许埋在代码里；换阈值 = 换 `rubric_version`。

    阈值的量纲与来源：
    * `grasp_max_dist_m` —— 方块中心到目标侧指 geom 的距离上限（米）。
    * `lift_min_height_m` —— 方块中心高出**桌面参考 z** 的下限（米）。
    * `hold_min_steps` —— 连续满足上述条件的控制步数下限（**这条是反 flick 的主力**）。
    * `box_speed_max_mps` —— 持稳期间方块线速度上限（米/秒）；弹射会远超它。
    * `require_no_table_contact` —— 沿用 env 的"离桌"语义，但作为**几何**条件之一而非唯一条件。
    """

    grasp_max_dist_m: float = 0.045
    lift_min_height_m: float = 0.05
    hold_min_steps: int = 5
    box_speed_max_mps: float = 0.60
    require_no_table_contact: bool = True
    rubric_version: str = "c2-geom-truth-transfer-cube-v1"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JudgmentFacts:
    """从物理状态里读出来的**事实**（不含判定）。判定与读数分开 ⇒ 判定可离线单测，不占 GPU。"""

    box_xyz: tuple[float, float, float]
    box_speed_mps: float
    table_z_ref: float
    finger_xyz: dict[str, tuple[float, float, float]]     # {"left": …, "right": …}
    contact_box_finger: dict[str, bool]                   # {"left": bool, "right": bool}
    contact_box_table: bool
    env_reward: int | None                                # env 自己的 reward（只作交叉核验）
    env_is_success: bool | None
    step_index: int
    horizon: int
    dt: float = shim.MAINLINE_DT       # 裁定 62-③：判定按**秒**登记，dt 来自 A2 的 shim（不另立）
    source: str = "measured_from_physics"

    @property
    def elapsed_s(self) -> float:
        return round(self.step_index * self.dt, 6)

    @property
    def horizon_s(self) -> float:
        return round(self.horizon * self.dt, 6)

    def as_dict(self) -> dict[str, Any]:
        return {"box_xyz": list(self.box_xyz), "box_speed_mps": self.box_speed_mps,
                "table_z_ref": self.table_z_ref,
                "finger_xyz": {k: list(v) for k, v in self.finger_xyz.items()},
                "contact_box_finger": dict(self.contact_box_finger),
                "contact_box_table": self.contact_box_table,
                "env_reward": self.env_reward, "env_is_success": self.env_is_success,
                "step_index": self.step_index, "horizon": self.horizon, "dt": self.dt,
                "elapsed_s": self.elapsed_s, "horizon_s": self.horizon_s, "source": self.source}


@dataclass(frozen=True)
class Judgment:
    outcome_class: str                 # success / failure / timeout / unknown
    value: float | None                # 1.0 / 0.0 / None（unknown）
    label_kind: str                    # "success" / "unknown"（映射到 ledger 既有词表）
    direction: str
    hold_steps: int
    reasons: tuple[str, ...]
    geometric_success: bool
    env_success: bool | None
    agreement: bool | None             # None = env 未给判定（不可比，不是"一致"）
    thresholds: JudgeThresholds
    elapsed_s: float | None = None     # 裁定 62-③：按秒登记
    horizon_s: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"outcome_class": self.outcome_class, "value": self.value,
                "label_kind": self.label_kind, "direction": self.direction,
                "hold_steps": self.hold_steps, "reasons": list(self.reasons),
                "geometric_success": self.geometric_success, "env_success": self.env_success,
                "agreement": self.agreement, "thresholds": self.thresholds.as_dict(),
                "rubric_version": self.thresholds.rubric_version,
                "elapsed_s": self.elapsed_s, "horizon_s": self.horizon_s,
                "time_unit": "s（裁定 62-③：跨频率对比不得按步数并列）"}


def target_side(direction: str) -> str:
    """方向 → 目标侧。**方向是参数，不是写死的常量**（env 的 `reward==4` 写死了右→左）。"""
    if direction == "right_to_left":
        return "left"
    if direction == "left_to_right":
        return "right"
    raise EnvContractError(f"未知方向 {direction!r}，可选 {DIRECTIONS}")


def judge_from_facts(facts: JudgmentFacts, *, direction: str,
                     thresholds: JudgeThresholds = JudgeThresholds(),
                     hold_steps: int = 0) -> Judgment:
    """纯函数判定：给事实 + 方向 + 阈值 ⇒ 四类结论。**不读物理、不渲染、不占 GPU** ⇒ 可单测。

    `hold_steps` 由调用方（env 包装器）跨步累积：本函数无状态。
    """
    side = target_side(direction)
    reasons: list[str] = []

    box = np.asarray(facts.box_xyz, dtype=np.float64)
    finger = np.asarray(facts.finger_xyz.get(side, (np.nan,) * 3), dtype=np.float64)
    if not np.isfinite(finger).all():
        return Judgment(outcome_class="unknown", value=None, label_kind="unknown",
                        direction=direction, hold_steps=hold_steps,
                        reasons=(f"目标侧 {side} 指 geom 位置不可读 ⇒ 判 unknown，不猜",),
                        geometric_success=False, env_success=facts.env_is_success,
                        agreement=None, thresholds=thresholds,
                        elapsed_s=facts.elapsed_s, horizon_s=facts.horizon_s)

    dist = float(np.linalg.norm(box - finger))
    height = float(box[2] - facts.table_z_ref)
    grasp_ok = dist <= thresholds.grasp_max_dist_m
    lift_ok = height >= thresholds.lift_min_height_m
    speed_ok = facts.box_speed_mps <= thresholds.box_speed_max_mps
    table_ok = (not facts.contact_box_table) if thresholds.require_no_table_contact else True

    if not grasp_ok:
        reasons.append(f"方块到{side}指距离 {dist:.4f} m > {thresholds.grasp_max_dist_m} m（未夹住）")
    if not lift_ok:
        reasons.append(f"离桌高度 {height:.4f} m < {thresholds.lift_min_height_m} m")
    if not speed_ok:
        reasons.append(f"方块线速度 {facts.box_speed_mps:.3f} m/s > "
                       f"{thresholds.box_speed_max_mps} m/s（弹射/flick 嫌疑）")
    if not table_ok:
        reasons.append("方块仍与桌面接触")
    # 接触真值与几何真值不一致 ⇒ 记进理由（不单独判红，但必须可见）
    if facts.contact_box_finger.get(side) and not grasp_ok:
        reasons.append(f"env 侧读到 {side} 指接触、但几何距离超限 ⇒ 属"
                       f"「擦到即算」形态（tasks/sim.py:145-148），几何判据不采信")

    instant_ok = grasp_ok and lift_ok and speed_ok and table_ok
    geometric_success = bool(instant_ok and hold_steps >= thresholds.hold_min_steps)
    if instant_ok and not geometric_success:
        reasons.append(f"瞬时条件已满足但连续持稳 {hold_steps} < {thresholds.hold_min_steps} 步"
                       f"（反 flick：必须持稳）")
    if geometric_success:
        reasons.append(f"几何真值成立：{side} 指夹住 + 离桌 {height:.4f} m + "
                       f"持稳 {hold_steps} 步 + 速度 {facts.box_speed_mps:.3f} m/s")

    env_success = facts.env_is_success
    agreement = None if env_success is None else bool(geometric_success == bool(env_success))

    if geometric_success:
        outcome, value, label_kind = "success", 1.0, "success"
    elif facts.step_index >= facts.horizon:
        outcome, value, label_kind = "timeout", 0.0, "success"
        reasons.append(f"仿真时长 {facts.elapsed_s:.3f} s 达到 horizon {facts.horizon_s:.3f} s"
                       f"（= {facts.step_index} 步 × dt {facts.dt}）⇒ timeout（不是 failure）；"
                       f"跨频率对比一律按秒，不按步数并列（裁定 62-③）")
    else:
        outcome, value, label_kind = "failure", 0.0, "success"
    return Judgment(outcome_class=outcome, value=value, label_kind=label_kind,
                    direction=direction, hold_steps=hold_steps, reasons=tuple(reasons),
                    geometric_success=geometric_success, env_success=env_success,
                    agreement=agreement, thresholds=thresholds,
                    elapsed_s=facts.elapsed_s, horizon_s=facts.horizon_s)


# ========================================================================== 读数层
def read_facts(physics, *, step_index: int, horizon: int, table_z_ref: float,
               prev_box_xyz: np.ndarray | None, dt: float,
               env_reward: int | None = None, env_is_success: bool | None = None) -> JudgmentFacts:
    """从 dm_control 的 `physics` 里读事实。geom 名读不到就**抛**，不静默填 0/NaN 当判定输入。"""
    named = physics.named.data
    try:
        box_xyz = np.asarray(named.geom_xpos[GEOM_BOX], dtype=np.float64).copy()
    except KeyError as exc:
        raise EnvContractError(f"读不到方块 geom {GEOM_BOX!r}（模型换了？必须重核，不许假设）") from exc
    finger = {}
    for side, geom in GEOM_FINGER.items():
        try:
            finger[side] = tuple(float(x) for x in np.asarray(named.geom_xpos[geom], dtype=np.float64))
        except KeyError:
            finger[side] = (float("nan"),) * 3          # 交给 judge 判 unknown（不猜）
    pairs = set()
    for i in range(int(physics.data.ncon)):
        c = physics.data.contact[i]
        pairs.add((physics.model.id2name(c.geom1, "geom"), physics.model.id2name(c.geom2, "geom")))
    contact_finger = {side: ((GEOM_BOX, geom) in pairs or (geom, GEOM_BOX) in pairs)
                      for side, geom in GEOM_FINGER.items()}
    contact_table = (GEOM_BOX, GEOM_TABLE) in pairs or (GEOM_TABLE, GEOM_BOX) in pairs
    if prev_box_xyz is None:
        speed = 0.0
    else:
        speed = float(np.linalg.norm(box_xyz - prev_box_xyz) / max(dt, 1e-9))
    return JudgmentFacts(box_xyz=tuple(float(x) for x in box_xyz), box_speed_mps=speed,
                         table_z_ref=float(table_z_ref), finger_xyz=finger,
                         contact_box_finger=contact_finger, contact_box_table=contact_table,
                         env_reward=env_reward, env_is_success=env_is_success,
                         step_index=int(step_index), horizon=int(horizon))


# ========================================================================== env 包装
@dataclass(frozen=True)
class EnvSpec:
    """构造口径。**所有会影响可比性的量都必须在这里显式出现**（跨口径禁令：裁定 46.4 / 53.3）。"""

    env_id: str = shim.ENV_ID
    dt: float = shim.MAINLINE_DT                       # 来自 A2 的 shim，不另立
    cam_map: Mapping[str, str] = field(default_factory=lambda: dict(CAM_MAP_DEFAULT))
    image_size: int = 224
    direction: str = "right_to_left"
    horizon_option: str = "registered_300"             # pending D ruling（A2 建议 rescale_176）
    render_images: bool = True
    thresholds: JudgeThresholds = field(default_factory=JudgeThresholds)
    seed: int | None = None

    def horizon_steps(self) -> int:
        """**裁定 58.3 已裁**：保持 300 步、不缩放（= 10.2 s @29.4118 Hz）。

        A2 的 `episode_horizon()` 曾并列 A/B 两案（B = 缩到 176 步以保持 6.0 s），
        **B 案已作废** ⇒ 选它必须**响亮拒绝**，不静默执行（红线要吵，不要忍）。
        """
        h = shim.episode_horizon(dt=self.dt)
        if self.horizon_option == "registered_300":
            return int(h["registered_max_episode_steps"])
        if self.horizon_option == "rescale_176":
            raise EnvContractError(
                "horizon_option='rescale_176' 已被**裁定 58.3 作废**（裁：保持 300 步、不缩放，"
                "300 步 @29.4118 Hz = 10.2 s）。若 D 改判，先改本卫语句并在 manifest 留改判出处，"
                "不要在调用点静默换步数。")
        raise EnvContractError(f"未知 horizon_option {self.horizon_option!r}，可选 {HORIZON_OPTIONS}"
                               f"（其中 rescale_176 已作废，见裁定 58.3）")

    def image_keys(self) -> tuple[str, ...]:
        return tuple(self.cam_map)

    def obs_contract(self) -> okc.ObsKeyContract:
        """**env 产出、learner 消费**的同一份键契约（T-C2-2 的闸就是照它判的）。"""
        return okc.declare_contract(state_keys=(STATE_KEY,), required_keys=self.image_keys(),
                                    representation_version=MODULE_REPRESENTATION_VERSION,
                                    note=f"env={self.env_id} direction={self.direction} "
                                         f"image_size={self.image_size}")


class GymAlohaSimEnv:
    """主线仿真代理：29.4118 Hz、扁平化 π₀.₅ 键、四类判定 + 几何真值交叉核验。"""

    def __init__(self, spec: EnvSpec | None = None, *, env=None, apply_record: dict | None = None):
        self.spec = spec or EnvSpec()
        if self.spec.direction not in DIRECTIONS:
            raise EnvContractError(f"direction {self.spec.direction!r} 不在 {DIRECTIONS}")
        if env is None:
            env, apply_record = shim.make_env(self.spec.env_id, dt=self.spec.dt,
                                              obs_type="pixels_agent_pos",
                                              render_mode="rgb_array")
        self.env = env
        self.apply_record = apply_record or {}
        self._inner = getattr(env, "unwrapped", env)
        self._dm = getattr(self._inner, "_env", None)
        if self._dm is None:
            raise EnvContractError("找不到 AlohaEnv._env（gym_aloha 版本变了？必须重核，不许假设）")
        self.physics = self._dm.physics
        self.timing = shim.read_live_timing(env)
        self._verify_timing()
        self.horizon = self.spec.horizon_steps()
        self._step_index = 0
        self._hold_steps = 0
        self._prev_box = None
        self._table_z_ref: float | None = None
        self._last_judgment: Judgment | None = None

    # ---------- 口径自检 ----------
    def _verify_timing(self) -> None:
        t = self.timing
        if t.get("error"):
            raise EnvContractError(f"读不到活体时序：{t['error']}")
        if not t.get("matches_mainline"):
            raise EnvContractError(
                f"控制周期不是主线口径：实测 control_timestep_s={t.get('control_timestep_s')} "
                f"≠ {shim.MAINLINE_DT}（shim 未生效？裁定 53）")
        if not t.get("in_qc_band_29_31"):
            raise EnvContractError(f"实测 {t.get('control_hz')} Hz 不在 QC 区间 {shim.QC_BAND_HZ}")
        if int(t.get("n_sub_steps", -1)) != shim.MAINLINE_SUBSTEPS:
            raise EnvContractError(f"子步数 {t.get('n_sub_steps')} ≠ {shim.MAINLINE_SUBSTEPS}")

    # ---------- obs ----------
    def _state(self) -> np.ndarray:
        from gym_aloha.tasks.sim import BimanualViperXTask
        s = np.asarray(BimanualViperXTask.get_qpos(self.physics), dtype=np.float32)
        if s.shape != (STATE_DIM,):
            raise EnvContractError(f"state 形状 {s.shape} ≠ {(STATE_DIM,)}（形态变了必须重核）")
        return s

    def _images(self) -> dict[str, np.ndarray]:
        if not self.spec.render_images:
            return {}
        out = {}
        h = w = int(self.spec.image_size)
        for key, cam in self.spec.cam_map.items():
            arr = np.asarray(self.physics.render(height=h, width=w, camera_id=cam))
            if arr.shape != (h, w, 3):
                raise EnvContractError(f"相机 {cam} 渲染形状 {arr.shape} ≠ {(h, w, 3)}")
            out[key] = arr.transpose(2, 0, 1).astype(np.float32) / 255.0     # A2 的口径
        return out

    def observation(self) -> dict[str, np.ndarray]:
        """**扁平**观测（无嵌套 dict ⇒ 可被 `harness/obs_store.py` 内容寻址，见 G12）。"""
        obs: dict[str, np.ndarray] = {STATE_KEY: self._state()}
        obs.update(self._images())
        return obs

    # ---------- 生命周期 ----------
    def reset(self, seed: int | None = None) -> dict[str, np.ndarray]:
        s = self.spec.seed if seed is None else seed
        self.env.reset(seed=s)
        self._step_index = 0
        self._hold_steps = 0
        self._prev_box = None
        self._last_judgment = None
        # 桌面参考 z：用 reset 后方块的 z（此时方块静止在桌面上）⇒ 自标定，不解析 geom 尺寸
        box_z = float(np.asarray(self.physics.named.data.geom_xpos[GEOM_BOX], dtype=np.float64)[2])
        self._table_z_ref = box_z
        return self.observation()

    def step(self, action) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        act = np.asarray(action, dtype=np.float32).reshape(-1)
        raw_obs, reward, terminated, truncated, info = self.env.step(act)
        self._step_index += 1
        facts = read_facts(self.physics, step_index=self._step_index, horizon=self.horizon,
                           table_z_ref=float(self._table_z_ref), prev_box_xyz=self._prev_box,
                           dt=float(shim.MAINLINE_DT),
                           env_reward=int(reward) if reward is not None else None,
                           env_is_success=bool(info.get("is_success")) if info else None)
        self._prev_box = np.asarray(facts.box_xyz, dtype=np.float64)
        side = target_side(self.spec.direction)
        instant = (facts.contact_box_finger.get(side)
                   and np.linalg.norm(np.asarray(facts.box_xyz) - np.asarray(facts.finger_xyz[side]))
                   <= self.spec.thresholds.grasp_max_dist_m
                   and (facts.box_xyz[2] - facts.table_z_ref) >= self.spec.thresholds.lift_min_height_m
                   and facts.box_speed_mps <= self.spec.thresholds.box_speed_max_mps
                   and not facts.contact_box_table)
        self._hold_steps = self._hold_steps + 1 if instant else 0
        judgment = judge_from_facts(facts, direction=self.spec.direction,
                                    thresholds=self.spec.thresholds, hold_steps=self._hold_steps)
        self._last_judgment = judgment
        self._facts = facts
        return self.observation(), {"judgment": judgment.as_dict(), "facts": facts.as_dict(),
                                     "env_info_keys": sorted(info or {}),
                                     "step_index": self._step_index,
                                     "done": bool(terminated or truncated or judgment.outcome_class == "success"),
                                     "env_terminated": bool(terminated),
                                     "env_truncated": bool(truncated)}

    # ---------- 交叉核验（裁定 54：不一致 ⇒ 红） ----------
    def cross_check(self, judgment: Judgment | None = None) -> dict[str, Any]:
        j = judgment or self._last_judgment
        if j is None:
            raise EnvContractError("还没有任何判定可交叉核验（先 step）")
        out = {"direction": j.direction, "geometric_success": j.geometric_success,
               "env_success": j.env_success, "agreement": j.agreement,
               "env_judgment_source": "gym_aloha/env.py:178-180 terminated=is_success=reward==4",
               "geometric_rubric_version": j.thresholds.rubric_version}
        if j.agreement is False:
            out["verdict"] = "RED"
            out["why"] = ("几何真值与 env 的 reward==4 不一致 ⇒ 按裁定 54 判红；"
                          "反向任务里这是**预期形态**（env 判定只覆盖右→左）")
            raise JudgmentDisagreement(json_dumps(out))
        out["verdict"] = "GREEN" if j.agreement else "NOT_COMPARABLE"
        return out

    # ---------- 账本落行（只用 ledger 既有公开 API，不改 ledger.py） ----------
    def ledger_label_kwargs(self, judgment: Judgment, *, episode_id: str,
                            target_seq: int | None = None,
                            target_request_id: str | None = None) -> dict[str, Any]:
        if judgment.label_kind not in ("success", "unknown"):
            raise EnvContractError(f"映射出的 label_kind {judgment.label_kind!r} 不在既有词表")
        return {"episode_id": episode_id, "label_kind": judgment.label_kind,
                "target_kind": "frame", "target_seq": target_seq,
                "target_request_id": target_request_id, "value": judgment.value,
                "value_json": judgment.as_dict(), "rubric_version": judgment.thresholds.rubric_version,
                "source": "env_geometric_truth", "reason": "; ".join(judgment.reasons)[:900]}

    # ---------- manifest ----------
    def manifest(self) -> dict[str, Any]:
        return {
            "module": "harness/env_gym_aloha.py",
            "module_sha256_12": module_sha256_12(),
            "module_representation_version": MODULE_REPRESENTATION_VERSION,
            "generated_at": now_iso(),
            "env_id": self.spec.env_id,
            "direction": self.spec.direction,
            "dt": self.spec.dt,
            "dt_source": f"envs/gym_aloha_shim.py（A2 拥有，sha256-12 {shim.shim_sha256_12()}）",
            "shim_representation_version": shim.REPRESENTATION_VERSION,
            "shim_sha256_12": shim.shim_sha256_12(),
            "measured_timing": self.timing,
            "measured_control_hz": self.timing.get("control_hz"),
            "qc_band_hz": list(shim.QC_BAND_HZ),
            "per_step_budget_ms": shim.PER_STEP_BUDGET_MS,
            "horizon_option": self.spec.horizon_option,
            "horizon_steps": self.horizon,
            "episode_horizon_s": round(self.horizon * float(self.spec.dt), 4),
            "episode_horizon_s_note": ("裁定 62-③ / 58.3：300 步 @29.4118 Hz = 10.2 s。"
                                       "超时/失败判定按秒登记；跨频率对比不得按步数并列"),
            "horizon_decision_status": ("ruled_per_裁定58.3：保持 300 步、不缩放；"
                                        "A2 的 B 案（rescale_176 = 6.0 s）已作废，选它会被拒绝构造"),
            "horizon_ruling_ref": "supervisor_memo_20260929.md:2291（裁定 58.3）；"
                                  "d_simchain_e2emin_20260929.md:270；d_handoff_to_c2_20260929.md:256",
            "horizon_detail": shim.episode_horizon(dt=self.spec.dt),
            "cam_map": dict(self.spec.cam_map),
            "image_size": self.spec.image_size,
            "render_images": self.spec.render_images,
            "obs_contract": self.spec.obs_contract().as_dict(),
            "judge_thresholds": self.spec.thresholds.as_dict(),
            "env_judgment_semantics": {
                "source": "gym_aloha/env.py:178-180 + tasks/sim.py:125-149",
                "kind": "code_read_semantics",
                "defect_direction_hardcoded": "reward==4 只覆盖右→左；反向任务里左爪抬起即误判成功",
                "defect_contact_not_hold": "只要求接触+离桌，不要求持稳 ⇒ flick 可判成功",
            },
            "site_packages_modified": bool(self.apply_record.get("site_packages_modified", False)),
            "five_tuple_annotation": five_tuple_annotation(self.spec, self.timing),
            "python": platform.python_version(),
            "interpreter": sys.executable,
            "status_word_v4": "已实现未验证（构造与判定层）；端到端证据待 S1 示范数据落地后由 B2 的闸出",
        }


def five_tuple_annotation(spec: "EnvSpec", timing: dict[str, Any]) -> dict[str, Any]:
    """任何吞吐/延迟/容量数字都必须带这五元（+负载对），否则不得与别处数字并列。

    五元 = (venv, MUJOCO_GL 后端, mujoco 版本, 模型, 相机数与分辨率)。
    裁定 59 之后后端**必须**入标注：`egl+NVIDIA vendor` 与 `osmesa` 差 13.8×，互搬即失真。
    """
    import os
    try:
        import mujoco
        mujoco_version = getattr(mujoco, "__version__", "unknown")
    except Exception as exc:                                    # noqa: BLE001
        mujoco_version = f"unreadable({type(exc).__name__})"
    exe = sys.executable
    venv = exe.split("/venvs/")[-1].split("/")[0] if "/venvs/" in exe else exe
    return {
        "venv": venv,
        "interpreter": exe,
        "mujoco_gl_backend": os.environ.get("MUJOCO_GL"),
        "egl_vendor_filenames": os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES"),
        "ld_library_path_prefix_only": os.environ.get("LD_LIBRARY_PATH"),
        "mujoco_version": mujoco_version,
        "model": {"env_id": spec.env_id,
                  "control_timestep_s": timing.get("control_timestep_s"),
                  "physics_timestep_s": timing.get("physics_timestep_s"),
                  "n_sub_steps": timing.get("n_sub_steps"),
                  "control_hz": timing.get("control_hz")},
        "cameras": {"n": len(spec.cam_map), "names": list(spec.cam_map.values()),
                    "policy_layer_keys": list(spec.cam_map),
                    "rendered_this_run": bool(spec.render_images)},
        "resolution": {"image_size": spec.image_size,
                       "shape_per_camera": [3, spec.image_size, spec.image_size]},
        "cross_backend_numbers_must_not_be_juxtaposed": True,
    }


def json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
