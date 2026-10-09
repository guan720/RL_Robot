"""C2 · 消费侧 obs 键覆盖契约（**加法式新增文件**，裁定 49.2 / 54）。

## 补的是哪个缺口（有实测，不是推测）

`harness/queue_td_learner.py` 的 `_obs_vector` 原来只挑 `("state", "environment_state")`
两个键（原文 `:134`–`:135`），其余键**被静默丢弃**，而宽度检查（`:139`–`:140`）只看
拼出来的状态向量 ⇒ **恒过**。实测证据（`scripts/c2_probe_obs_key_drop.py`，只读探针）：

    runs/vla/c2_obs_key_whitelist_20260929/probe_20260929/probe_main.json
      verdict = DEFECT_REPRODUCED
      pi05_policy_layer / pi05_policy_layer_altimg / pi05_env_camera_names /
      pi05_env_camera_names_altimg 四个带图像变体的 `vec_sha12` **全部 = `4fd32aacc677`**，
      与只有 `state` 的 ACT 线旧快照**逐字节相同** ⇒ 图像内容对 learner 输入的影响 = 0。
      `dropped_value_ratio` = 0.999969（策略层 3×[3,224,224]）/ 0.99999494（env 相机 3×480×640×3）。

对应缺口原文：`docs/ledger_data_bridge_20260928.md:210`「x_ref → 表征重算（现在只重算
flat 状态向量，没有任何视觉表征）」；阻塞台账 B3：`d_simchain_e2emin_20260929.md:203`。

## 设计约束（裁定 49.2 四条，逐条对应）

1. **不写死键名清单**：契约由调用方声明；未声明时**从消费侧自身的读取集合推导**
   （`derive_contract()` 的默认值 = `_obs_vector` 真的会读的那两个键）⇒ 清单与实现
   同源，不会出现"白名单说读了、实现没读"的分叉（本仓已发生四次的同族事故）。
2. **双向牙**：只有 `state`（或 `state`+`environment_state`）的旧快照**仍须绿**
   （不破坏 ACT 线回归基线与 C 的 17/17）；带图像键而契约未声明 ⇒ **红**；
   契约声明为必需却缺席 ⇒ **也红**（观测通道缺失不是"信息少一点"，是契约不符）。
3. **不改 `state_dim` 语义**：宽度检查原样保留，本模块只在它**之前**补一层键覆盖判定。
4. **错误信息点名**：被丢弃 / 缺席的键名逐个列出，并给出「存入键集合 vs 消费键集合」
   的双向差集（`CoverageResult.as_dict()` 可直接落盘）。

## 边界

* 本文件**不 import** `queue_td_learner`（避免循环导入）；由消费侧捕获
  `ObsKeyCoverageViolation` 并转成它自己的 `LearnerRefused`。
* 本文件**不做**归一化、不做奖励、不做训练语义（那是 T-C2-1 / ledger 的职责）。
* 不改 `harness/contracts.py`（冻结面）；本文件是新增，属裁定 54 允许的加法。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

# **单一事实源**：`_obs_vector` 真正会读来拼状态向量的键。
# 改这里 = 改消费语义，必须同时改 `LearnerConfig`/闸的期望值，并留 before 影像（裁定 35.1）。
DEFAULT_STATE_KEYS: tuple[str, ...] = ("state", "environment_state")

CONTRACT_VERSION = "c2-obs-key-coverage-v1"


class ObsKeyCoverageViolation(RuntimeError):
    """快照的键集合与消费契约不符：有键被静默丢弃，或必需键缺席。"""


@dataclass(frozen=True)
class ObsKeyContract:
    """消费侧声明「我会读哪些键」。三类语义**故意分开**，不要合并成一个集合：

    * `state_keys`  —— **any-of**：至少一个在位即可（缺席时由 `_obs_vector` 既有文案
      `快照 … 里没有 state / environment_state` 拒绝，本模块不抢那条文案，避免改变既有判据）。
      顺序 = 状态向量的拼接顺序（**改顺序就是改表征**，必须换 `representation_version`）。
    * `required_keys` —— **all-of**：每个都必须在位（例如 π₀.₅ 的三路图像）。
    * `optional_keys` —— 可在可不在；**在位即视为被消费**（不算丢弃）。
    """

    state_keys: tuple[str, ...] = DEFAULT_STATE_KEYS
    required_keys: tuple[str, ...] = ()
    optional_keys: tuple[str, ...] = ()
    source: str = "derived_from_consumer"     # derived_from_consumer | declared_by_caller
    representation_version: str | None = None  # 只作记录，不参与判定
    note: str = ""
    contract_version: str = CONTRACT_VERSION

    @property
    def consumed_keys(self) -> tuple[str, ...]:
        """消费者会读的键全集（去重、保序）。"""
        return tuple(dict.fromkeys(self.state_keys + self.required_keys + self.optional_keys))

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "source": self.source,
            "state_keys": list(self.state_keys),
            "required_keys": list(self.required_keys),
            "optional_keys": list(self.optional_keys),
            "consumed_keys": list(self.consumed_keys),
            "representation_version": self.representation_version,
            "note": self.note,
        }


@dataclass(frozen=True)
class CoverageResult:
    """「存入键集合 vs 消费键集合」的双向差集 —— 裁定 49.2 要求 4 要它落盘。"""

    kind: str
    keys_stored: tuple[str, ...]
    keys_consumed: tuple[str, ...]
    keys_unconsumed: tuple[str, ...]     # 存了但没人读 = 静默丢弃集
    keys_missing: tuple[str, ...]        # 契约要求必需、但快照里没有
    covered: bool
    contract: ObsKeyContract

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "covered": self.covered,
            "n_keys_stored": len(self.keys_stored),
            "keys_stored": list(self.keys_stored),
            "n_keys_consumed": len(self.keys_consumed),
            "keys_consumed": list(self.keys_consumed),
            "n_keys_unconsumed": len(self.keys_unconsumed),
            "keys_unconsumed": list(self.keys_unconsumed),
            "n_keys_missing": len(self.keys_missing),
            "keys_missing": list(self.keys_missing),
            "contract": self.contract.as_dict(),
        }

    def explain(self) -> str:
        """点名文案：静默失败的反面不是报错，是**报得能定位**（裁定 49.2 要求 4）。"""
        parts = [f"{self.kind}: obs 键覆盖不符（契约 {self.contract.source}）"]
        if self.keys_unconsumed:
            parts.append(
                f"存入 {len(self.keys_stored)} 键 {list(self.keys_stored)}、"
                f"消费 {len(self.keys_consumed)} 键 {list(self.keys_consumed)}；"
                f"被静默丢弃的键={list(self.keys_unconsumed)}")
        if self.keys_missing:
            parts.append(f"契约声明为必需但快照缺席的键={list(self.keys_missing)}")
        parts.append("处置：把该键写进消费契约（required/optional）或从快照里去掉；"
                     "不许让观测通道静默消失")
        return "；".join(parts)


def derive_contract(state_keys: Sequence[str] = DEFAULT_STATE_KEYS, *,
                    representation_version: str | None = None,
                    note: str = "未声明契约 ⇒ 从消费侧实际读取的键推导（any-of state）") -> ObsKeyContract:
    """默认契约：**只有 state 类键**。这正是 ACT 线旧快照的形态 ⇒ 旧快照仍绿。"""
    return ObsKeyContract(state_keys=tuple(state_keys), required_keys=(), optional_keys=(),
                          source="derived_from_consumer",
                          representation_version=representation_version, note=note)


def declare_contract(*, state_keys: Sequence[str] = DEFAULT_STATE_KEYS,
                     required_keys: Iterable[str] = (),
                     optional_keys: Iterable[str] = (),
                     representation_version: str | None = None,
                     note: str = "") -> ObsKeyContract:
    """调用方显式声明（例如 π₀.₅ 形态：三路图像进 `required_keys`）。

    **不在这里写死任何键名**：键名由调用方给（本仓的键名口径来自
    `scripts/a2_pi05_contract_probe.py:91`–`:105` 与 `d_simchain_e2emin_20260929.md:143`）。
    """
    return ObsKeyContract(state_keys=tuple(state_keys), required_keys=tuple(required_keys),
                          optional_keys=tuple(optional_keys), source="declared_by_caller",
                          representation_version=representation_version, note=note)


def evaluate_coverage(stored_keys: Iterable[str], contract: ObsKeyContract, *,
                      kind: str = "obs") -> CoverageResult:
    """纯函数判定，**不抛**（给闸与产物用）。"""
    stored = tuple(dict.fromkeys(str(k) for k in stored_keys))
    consumed_set = set(contract.consumed_keys)
    consumed_present = tuple(k for k in stored if k in consumed_set)
    unconsumed = tuple(k for k in stored if k not in consumed_set)
    missing = tuple(k for k in contract.required_keys if k not in set(stored))
    covered = not unconsumed and not missing
    return CoverageResult(kind=kind, keys_stored=stored, keys_consumed=consumed_present,
                          keys_unconsumed=unconsumed, keys_missing=missing,
                          covered=covered, contract=contract)


def check_coverage(stored_keys: Iterable[str], contract: ObsKeyContract | None = None, *,
                   kind: str = "obs") -> CoverageResult:
    """判定并在不符时抛 `ObsKeyCoverageViolation`（消息里点名被丢弃/缺席的键）。"""
    result = evaluate_coverage(stored_keys, contract or derive_contract(), kind=kind)
    if not result.covered:
        raise ObsKeyCoverageViolation(result.explain())
    return result


def coverage_from_mapping(obs: Mapping[str, Any], contract: ObsKeyContract | None = None, *,
                          kind: str = "obs") -> CoverageResult:
    """便利入口：直接吃 obs 字典（消费侧最常有的形态）。"""
    return check_coverage(obs.keys(), contract, kind=kind)
