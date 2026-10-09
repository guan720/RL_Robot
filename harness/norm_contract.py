# -*- coding: utf-8 -*-
"""C2 · T-C2-1 归一化契约层（**加法新增**；不改 site-packages、不改任何冻结面）。

## 为什么需要这一层（读过实现原文，不是转述）
π₀.₅ 的状态不是"喂进网络的向量"，而是**被离散成 256 个 bin 后拼进文本 prompt** 的：

* `lerobot/policies/pi05/processor_pi05.py:72` 先把 state `pad_vector(state, max_state_dim=32)`；
* `:77` `np.digitize(state_np, bins=np.linspace(-1, 1, 256 + 1)[:-1]) - 1`；
* `:81`–`:84` 把离散值 `" ".join(map(str, ...))` 拼成 `f"Task: {task}, State: {state_str};\\nAction: "`。

⇒ **两条静默失效路径**（都不抛异常）：
1. `x ≥ 1` ⇒ `digitize` 返回 256 ⇒ `-1` 后 = **255**（饱和到最高 bin）；
   `x < -1` ⇒ 返回 0 ⇒ `-1` 后 = **`-1`**，一个**不是合法 bin id 的负数**被当文本塞进 prompt；
2. `lerobot/processor/normalize_processor.py:305`–`:307`：
   `norm_mode = self.norm_map.get(feature_type, NormalizationMode.IDENTITY)`；
   `if norm_mode == IDENTITY or key not in self._tensor_stats: return tensor`
   ⇒ **stats 缺失就静默走 IDENTITY**，原始物理量（例 `1.16`）直接进 digitize ⇒ 全部饱和。

而 QUANTILES 的分母**没有下限**：`:369` `denom = q99 - q01`，`:371`–`:374` 只做
`torch.where(denom == 0, eps, denom)`（`eps` 默认 **1e-8**，`:94` / `:419`），`:377`
`2.0 * (tensor - q01) / denom - 1.0`。⇒ **近常量维**（`q99-q01` 很小但不为 0）会把噪声放大到
远超 ±1 ⇒ 饱和。ACT 线当年 `(x-mean)/(std+1e-6)` 冲到 **20402** 是同族事故。

## 这一层做什么（三件，都不碰第三方代码）
1. **把"每维 scale 下限"烘进 stats**：处理器内部只会算 `q99-q01`，无法从外部注入下限，
   所以 `apply_scale_floor` 直接改写落盘的 `q01/q99`（对称围绕中位数展宽到 `denom_eff ≥ floor`）。
   这是唯一能"不改 site-packages 就让下限生效"的位置，也是本层最重要的实现结论。
2. **提供参考实现 + 逐维可测量报告**：`reference_normalize` / `reference_digitize` 逐字对应上面
   引的公式，用来**预测**处理器会做什么（bin 占用数、clip 比例、饱和维数），不靠"看起来没问题"。
3. **契约判定（双向有牙）**：`evaluate_contract` 落四条真牙（裁定 51①）+ 两条必红分支
   （近常量维无下限保护、用 YAM/ABC-130k 的 stats 喂 ViperX300），违规抛 `NormContractViolation`。

## 两案并列（裁定 69②：不许静默选）
* `case="quantiles_with_scale_floor"`：`norm_map` 保持 QUANTILES，下限烘进 q01/q99；
* `case="identity_with_explicit_scale"`：`norm_map` 走 IDENTITY（处理器原样返回，`:305`–`:307`），
  由**本仓**在进处理器之前显式做 `(x - center) * gain`。变换在自己的代码里、可审计，
  但**接口变了**（需要生产/消费侧都调用）⇒ 只报不改，等 D 裁。

## stats 源分级（裁定 43.4 / 52 / 61 / 69）
| 源 | 用途 | `not_for_mainline_normalizer` |
|---|---|---|
| `s1_sim_demo_bidir`（B2 的 S1 仿真双向示范，先导 5 集落地即算） | **主线部署** | false |
| `env_derived_diagnostic`（本仓在关节模型里实测的状态分布） | 诊断（解释 zero-shot 饱和）+ 立必红分支 | **true** |
| `yam_abc130k`（YAM 形态、零位/符号不同） | **只能当必红分支的输入** | **true** |

## 纪律
* 数值主张带 loadavg + `nr_throttled`（分母 = cgroup 配额 12 核）；
* 外部/未实测的量标 `declared_only`；不写「跑通 / 学会 / 达标」；状态词只用 v4 五档；
* 本文件**只加法**：不 import `harness.contracts`、不改 `harness/ledger.py`。
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

# ---------------- 实现原文事实源（sha256-12 由调用方在产物里登记） ----------------
N_BINS = 256                     # processor_pi05.py:77 的 linspace(-1,1,257)[:-1]
BIN_WIDTH = 2.0 / N_BINS         # 归一化空间里一个 bin 的宽度 = 0.0078125
# 覆盖头寸（bin 数）。**模块级单一真值**：`widen_to_cover()` 的默认值与
# `declared_interval_conformance()` 的"头寸消耗比"分母必须同源，否则会出现
# "留了多少头寸"与"消耗了几成头寸"两个口径（与 `NEAR_CONSTANT_REL_TOL` 曾各写一份同族）。
HEADROOM_BINS_DEFAULT = 1.0
# 窗口逃逸阈值（裁定 90.4-1）。**不是调参项、不得放宽**：`headroom_consumption ≥ 1.0` 的含义
# 就是"越界量已经吃掉为该维留的全部头寸"⇒ 状态逃出被覆盖窗口 ⇒ 归一化后必越 ±1，
# 而**下侧**越出会产生 `processor_pi05.py:77` 的非法 bin `-1`（静默拼进文本 prompt）。
# D 原文：「1.0 不是调出来的阈值，是**窗口逃逸的定义**」；90.6-1 明写若某 regime 实测 ≥1.0，
# 处置是提高 `headroom_bins` 或启用逐维覆盖并**新建 `representation_version`**，不是放宽 1.0。
WINDOW_ESCAPE_RATIO = 1.0
# 红信息的**字符串**分隔符（只服务 traceback 可读）。⚠ **不得用 `"；"`**：牙的 `required`/`observed`
# 文案里合法地含中文分号 ⇒ 拼接后再 `split("；")` 会切出**幻影红标签**。
# 本轮实测（M32 原型跑，`runs/vla/c2_norm_contract_20260929/gate/proto_teeth_20260930_0600/`）：
# `Tesc` 的 required 写了"…不是调参项；裁定 90.6-1 明令不得放宽"，头寸减半让它变红后，
# 主线 8 行的 `red_ids` 里各多出一个 `裁定` ⇒ 进而污染 `unexplained_red_teeth`
# （= 闸会报一个**根本不是牙**的"无法解释的红"，读者无从处置）。
# **权威口径 = 结构化的 `payload["red"]`**（消费方一律读它）；本常量只用于显示。
RED_MESSAGE_SEPARATOR = "\n"
# 近常量维标记阈值 = **最小候选下限系数**（下方 `F1_CANDIDATES`），模块级单一真值。
# 为什么必须有这一个常量而不是两处各写默认值（2026-09-30 00:0x 实测缺陷）：
# `near_constant_dims(rel_tol=1e-3)` 与 `ContractThresholds.near_constant_rel_tol=0.02` 曾**各写一份**
# ⇒ 闸内判定标出 7 维、build 侧的行级统计标出 0 维（同一份数据、同一天、两个答案）。
# 这就是"声明值 vs 实现值"分叉的最小实例 ⇒ 合并成一个常量，并在 F1_CANDIDATES 定义后 assert 一致。
# 实测依据：原提议 1e-3 在真实数据上**一个维都标不出来**（hold 相 denom_raw/行程 最小 = 1.648e-3、
# random 0.198、sweep 0.0229）⇒ 牙 Tr1 恒绿 = 恒真牙（裁定 27.1）。取 0.02 的语义是
# "原始分位距小于最小候选下限 ⇒ 该维需要下限保护"，与下限公式同源、可复算。
NEAR_CONSTANT_REL_TOL = 0.02
FLOOR_MATERIALITY_FRACTION = 0.02   # 同上；下限**实质性**阈值（牙 Tr3）
SAT_BIN_HIGH = N_BINS - 1        # x ≥ 1 ⇒ 255
SAT_BIN_LOW = -1                 # x < -1 ⇒ -1（**不是合法 bin id**）
MAX_STATE_DIM = 32               # processor_pi05.py:55 / :72
LEROBOT_EPS = 1e-8               # normalize_processor.py:94 / :419

SOURCE_S1_DEMO = "s1_sim_demo_bidir"
SOURCE_ENV_DERIVED = "env_derived_diagnostic"
SOURCE_YAM_ABC130K = "yam_abc130k"
MAINLINE_ALLOWED_SOURCES = (SOURCE_S1_DEMO,)
BANNED_FOR_MAINLINE = (SOURCE_ENV_DERIVED, SOURCE_YAM_ABC130K)

CASE_QUANTILES_FLOOR = "quantiles_with_scale_floor"
CASE_IDENTITY_EXPLICIT = "identity_with_explicit_scale"
KNOWN_CASES = (CASE_QUANTILES_FLOOR, CASE_IDENTITY_EXPLICIT)

# ── stats 溯源标签与消费方（裁定 85.4-2/85.4-3：**pilot 与 formal 的 stats 不得互替**）─────────
# 为什么这两个常量必须在契约层而不是只在生成器里：硬闸的判据若只活在生成器，
# 下游（BC 配置、`registry/`）就能绕过生成器直接吃 stats 文件 ⇒ 闸形同虚设。
# 标签是**结构性事实**（有/无、属于已知集合/不属于）⇒ 允许纯布尔判据
# （红线 `criterion_must_have_magnitude_floor` 的例外条款：纯布尔只用于结构性存在/缺失）。
STATS_PROVENANCE_FORMAL40_BC = "formal40_bc_source"          # 唯一可进 BC 的档
# 交叉核对档（裁定 90.4-4）：`--s1-lerobot` 直读 parquet 的那条读路径**不得**再产 BC 档标签。
# D 原文：「两个读取器产出**同一个** provenance 标签 = 无法回答『BC 到底吃了哪一份』，这正是要挡的
# 形态」⇒ 权威接口 = **npz + `--s1-frames`**（裁定 86.0 撤回 85.4-2），lerobot 臂保留为交叉核对臂。
# 两条读路径的数据经 D 亲测**逐位相同**（`np.array_equal=True`、content sha 双 `c9a72480fcb7`）
# ⇒ 这是**权威性冲突、不是正确性冲突**；分标签的唯一目的 = 让 BC 硬闸在**结构上**吃不到交叉核对臂。
STATS_PROVENANCE_FORMAL40_LEROBOT_CROSSCHECK = "formal40_lerobot_crosscheck"
# 通路验证档，**不得进 BC**。裁定 87.4 的正典字面是 `pre_pilot5_path_check`，
# `pilot10_path_check`（裁定 86.1 用的字面）**被撤回为别名**；两者都在已知集合里，
# 关系由下面的 `PROVENANCE_ALIAS_OF` 机器表达（不是散文），理由见 `canonical_provenance()`。
STATS_PROVENANCE_PILOT10_PATH_CHECK = "pilot10_path_check"
STATS_PROVENANCE_PRE_PILOT5_PATH_CHECK = "pre_pilot5_path_check"   # 裁定 87.4：**正典**
STATS_PROVENANCE_ENV_DIAGNOSTIC = "env_derived_diagnostic_only"
STATS_PROVENANCE_YAM_MUSTRED = "yam_abc130k_mustred_branch"
STATS_PROVENANCE_UNDECLARED = "undeclared"
KNOWN_STATS_PROVENANCES = (STATS_PROVENANCE_FORMAL40_BC, STATS_PROVENANCE_PILOT10_PATH_CHECK,
                           STATS_PROVENANCE_PRE_PILOT5_PATH_CHECK,
                           STATS_PROVENANCE_FORMAL40_LEROBOT_CROSSCHECK,
                           STATS_PROVENANCE_ENV_DIAGNOSTIC, STATS_PROVENANCE_YAM_MUSTRED)
# ⚠ 交叉核对档**故意不在此列**（裁定 90.4-4）：它在已知集合里（⇒ 牙 Tp4 不红，它是合法登记的档），
# 但不在 BC 准入集合里（⇒ 牙 Tp5 对 `consumer=bc` 必红）。这两件事必须分开，否则要么假红、要么放宽准入。
BC_ADMISSIBLE_PROVENANCES = (STATS_PROVENANCE_FORMAL40_BC,)
# 裁定 93.4（E2）：BC 准入不再只看溯源标签，还必须 AND **闸 verdict**。
# 这个字面值放契约层的理由与 `BC_ADMISSIBLE_PROVENANCES` 同：判据若只活在生成器/闸里，
# 下游（A2 的 S3 BC 入口、`registry/`）就能绕过它 ⇒ 消费方必须能自己复算同一份口径。
GATE_VERDICT_PASS = "PASS"
# 别名 → 正典（裁定 87.4）。**只**用于登记与显示；BC 硬闸判的是 `== formal40_bc_source`，
# 任何别名都不映射到它 ⇒ 别名表不可能被用来放宽准入（这是把它放进契约层的前提）。
PROVENANCE_ALIAS_OF = {STATS_PROVENANCE_PILOT10_PATH_CHECK: STATS_PROVENANCE_PRE_PILOT5_PATH_CHECK}
PROVENANCE_ALIAS_AUTHORITY = ("裁定 87.4：`pre_pilot5_path_check` 为正典、`pilot10_path_check` 撤回为别名。"
                              "理由（D 原文）：BC 硬闸只认 `== formal40_bc_source`，非 BC 标签的字面"
                              "**不承载判据** ⇒ 不值得为此改产物；但别名关系必须机器可读，"
                              "否则未来读者会以为存在两个档位")


def canonical_provenance(stats_provenance: str | None) -> dict[str, Any]:
    """标签的正典/别名关系（三态：正典 / 别名 / 未知）。未知 ⇒ 不猜正典。"""
    prov = normalize_provenance(stats_provenance)
    canon = PROVENANCE_ALIAS_OF.get(prov)
    return {"stats_provenance": prov,
            "canonical": (canon or (prov if prov in KNOWN_STATS_PROVENANCES else None)),
            "is_alias": canon is not None,
            "known": prov in KNOWN_STATS_PROVENANCES,
            "authority": (PROVENANCE_ALIAS_AUTHORITY if canon is not None else None)}



CONSUMER_BC = "bc"
CONSUMER_PATH_CHECK = "path_check"
CONSUMER_DIAGNOSTIC = "diagnostic"
KNOWN_CONSUMERS = (CONSUMER_BC, CONSUMER_PATH_CHECK, CONSUMER_DIAGNOSTIC)


# ── 评估帧口径（牙名承诺了什么，就必须在**牙自己身上**机器可读地写清）──────────────────────
# WHY（闸侧元审计 `name_semantics_audit` 规则 4 在真产物上实测到的形态，不是假想）：
#   `Td2_clip_heldout` / `Te2_no_illegal_bin_heldout` 的名字承诺"held-out 帧"，而 49 行里有 9 行
#   根本没有留出集（8 行 hold 相 + 1 行 YAM 必红臂：`eval_frames=None` ⇒ `eval_x = frames`）⇒
#   牙名承诺的对象在这些行上**不存在**，而牙记录里没有任何字段说明这件事（只有**行级**
#   `eval_frames_are_held_out` 说了，只读牙的人看不到）。规则
#   `gate_name_must_match_gate_semantics` 的处置**不是改牙名**（D 的文书已按现 id 引用，
#   改 id 会断链），而是把口径写进牙记录本身，并让闸机器核
#   "牙自报 scope == 行级 scope == 实际有没有留出集"三者一致（不一致 ⇒ 红）。
EVAL_SCOPE_HELD_OUT = "held_out_split"
EVAL_SCOPE_NO_SPLIT = "no_split_eval_frames_equal_build_frames"
KNOWN_EVAL_SCOPES = (EVAL_SCOPE_HELD_OUT, EVAL_SCOPE_NO_SPLIT)
# 最小公共 check schema（裁定 78.2）：牙记录里这几个字段是**闸与生成器共用的接口**，
# 任何追加字段（`tooth(..., extra=...)`）都不得覆盖它们 ⇒ 在 `tooth()` 里断言。
# 闸侧 `scripts/c2_gate_norm_contract.py` 的 `SCHEMA_NEED` 是它的**独立副本**（故意不复用：
# 两处漂移时由 `name_semantics_audit` 的 `schema_key_parity` 子句判红，而不是静默各判各的）。
SCHEMA_REQUIRED_KEYS = frozenset({"id", "ok", "status", "required", "observed", "red_when"})
EVAL_SCOPE_NOTE = {
    EVAL_SCOPE_HELD_OUT: "本行的 eval 帧是按集留出的 held-out 帧 ⇒ 牙名里的 held-out 成立",
    EVAL_SCOPE_NO_SPLIT: ("本行**没有**留出集（调用方 eval_frames=None ⇒ eval 帧就是建 stats 的帧）"
                          "⇒ 牙名里的 held-out 在本行**不成立**，本牙在此只判 in-sample，"
                          "不构成部署面证据（与诊断档把 held-out 牙降为 warning 是同一条理由）"),
}


def eval_scope_of(eval_frames: Any) -> str:
    """scope 的**唯一**判定处：契约层与生成器都调它 ⇒ 两处不可能各说各话（防口径漂移）。"""
    return EVAL_SCOPE_HELD_OUT if eval_frames is not None else EVAL_SCOPE_NO_SPLIT


# ── 覆盖目标（裁定 87.3-1 的 ①：`widen_to_cover` 的 `must_cover` = **声明物理区间**）──────────
# 为什么改（D 的论证比 C2 原提案更强，照此写进产物）：被防的失效模式是 `illegal_bin = -1` 被拼进
# π₀.₅ 的文本 prompt（`processor_pi05.py:77`、`:81-84`）⇒ **正确性缺陷**；① 的代价是分辨率
# ⇒ **质量代价**。关键路径上正确性压倒质量。且 ① 是**口径无关**的（声明区间是模型级几何量，
# 不随数据集变），而"build 帧 + 余量"（候选 ②）绑在样本上、换数据集就要重定余量（裁定 71 同族风险）。
# ① 与 ③ 不是替代项：③（采更多集）降低越界**频率**，① 消除任何物理合法状态产生非法 bin 的**可能性**。
COVERAGE_TARGET_DECLARED_INTERVAL = "declared_interval"   # ①（裁定 87.3-1，**强制**）
COVERAGE_TARGET_BUILD_ONLY = "build_only"                 # 修前行为；**只**作条件 a 臂 1 的对照
KNOWN_COVERAGE_TARGETS = (COVERAGE_TARGET_DECLARED_INTERVAL, COVERAGE_TARGET_BUILD_ONLY)
COVERAGE_TARGET_AUTHORITY = {
    COVERAGE_TARGET_DECLARED_INTERVAL: "裁定 87.3-1（①，强制）+ 条件 c（声明区间是**上限**，不得赦免）",
    COVERAGE_TARGET_BUILD_ONLY: ("修前行为（must_cover=(start_pose, frames)）；保留**仅**为裁定 87.3-2 "
                                 "条件 a 臂 1 的对照口径，不得作为交付档"),
}


def coverage_must_cover(*, target: str, frames: np.ndarray | None = None,
                        start_pose: np.ndarray | None = None,
                        physical_interval: Sequence[np.ndarray] | None = None) -> dict[str, Any]:
    """把"覆盖目标"变成**一份**可审计的构造（不许调用方各拼各的 `must_cover`）。

    ①（`declared_interval`）：`must_cover` = 声明区间的两端 ⇒ 任何**物理合法**状态都不会被裁、
      也不会产生非法 bin。**故意不含 build 帧与起态**：含了就等于"数据超出声明区间时也把窗口
      跟着展宽去覆盖它"。⚠ **理由已按裁定 90.4-1 更正**：修前这里写的是「条件 c 禁止的赦免令
      （超出声明区间 = 数据/契约缺陷，必须继续红）」，而 D 在裁定 90.2 #15 承认"超出声明区间 =
      缺陷"这个前提是**它自己的错误**（`jnt_range` 是软边界）。裁定 90.3 给的正确残余是：
      **不展宽的理由不是「越界 = 缺陷」，而是「越界部分是物理饱和平台，展宽无信息收益」**
      （formal-40 实测：dim6 落进顶 bin 255 的 6609 帧物理跨度只有 0.001098、119 段连续 run
      ⇒ 夹爪顶在软限位上只剩求解器抖动；展宽只会把抖动放大成假信号喂给 BC）。
      ⇒ 构造**不变**（覆盖集仍然只有区间两端），变的只是它的理由与极性：
      起态由 `Tc_start_pose_coverage` 判；越界量由 `Tiv_out_of_declared_interval_is_measured`
      **测量落盘**（不判红），窗口逃逸由 `Tesc_no_covered_window_escape` 判红，
      下侧**覆盖不足**由 `Tlo_no_downside_coverage_deficit` 判红，任一侧越界由
      `Tovr_out_of_interval_overflow_is_warned` 出 warning（带量级）。
      ⚠ 修前这两行引的是 `Tlo_no_state_below_declared_interval` / `Tovr_upside_overflow_is_warned`
      —— 两个**不存在的牙 id**（改名时漏改引用）。这属规则 `gate_name_must_match_gate_semantics`
      的违例形态（名字承诺了一个盘上没有的对象），已由闸侧 `G46_tooth_name_citation_integrity`
      机器核（引用到的牙 id 必须存在于实际产出的牙集合里，或显式带历史标记词）。
      缺 `physical_interval` ⇒ **抛**，不静默退回 `build_only`（红线
      `absence_of_measurement_is_not_measurement_of_absence`：没测到不等于测到了"没有"）。
    `build_only`：修前口径，`cover_cap=None`（无上限可查）。
    """
    if target not in KNOWN_COVERAGE_TARGETS:
        raise NormContractViolation(
            f"未知 coverage_target={target!r}；只允许 {list(KNOWN_COVERAGE_TARGETS)}（裁定 87.3-1）")
    if target == COVERAGE_TARGET_DECLARED_INTERVAL:
        if physical_interval is None:
            raise NormContractViolation(
                "coverage_target='declared_interval'（裁定 87.3-1 的 ①）需要**声明物理区间**，"
                "但 physical_interval 未提供 ⇒ 拒绝构造覆盖集（**不静默退回 build_only**：退回就等于"
                "把 ① 的保证换成『数据自己说自己覆盖了』）")
        lo = np.asarray(physical_interval[0], dtype=np.float64).reshape(1, -1)
        hi = np.asarray(physical_interval[1], dtype=np.float64).reshape(1, -1)
        if lo.shape != hi.shape or lo.size == 0:
            raise NormContractViolation(f"physical_interval 形状不符：lo={lo.shape} hi={hi.shape}")
        bad = [int(i) for i in np.nonzero(hi[0] <= lo[0])[0]]
        if bad:
            raise NormContractViolation(f"声明区间非法（hi <= lo）维={bad}")
        return {"target": target, "must_cover": (lo, hi), "cover_cap": (lo[0], hi[0]),
                "n_cover_rows": 2,
                "includes_build_frames": False, "includes_start_pose": False,
                "authority": COVERAGE_TARGET_AUTHORITY[target],
                "note": ("覆盖集 = 声明区间两端（各 1 行）。故意不含 build 帧与起态：含了就会在数据"
                         "越界时把窗口跟着展宽 ⇒ 裁定 87.3-2 条件 c 的『上限』失效")}
    mc = []
    if start_pose is not None:
        mc.append(np.asarray(start_pose, dtype=np.float64).reshape(1, -1))
    if frames is None:
        raise NormContractViolation("coverage_target='build_only' 需要 frames（修前口径的覆盖集就是"
                                    "起态 + 建 stats 的帧），实到 None ⇒ 拒绝")
    mc.append(np.atleast_2d(np.asarray(frames, dtype=np.float64)))
    return {"target": target, "must_cover": tuple(mc), "cover_cap": None,
            "n_cover_rows": int(sum(m.shape[0] for m in mc)),
            "includes_build_frames": True, "includes_start_pose": start_pose is not None,
            "authority": COVERAGE_TARGET_AUTHORITY[target],
            "note": "修前口径：覆盖集 = 起态 + build 帧 ⇒ 按构造 build 帧不会被裁（对未见集无保护）"}


def coverage_version_token(*, target: str, headroom_bins: float,
                           cover_cap: Sequence[np.ndarray] | None = None,
                           interval_source_sha256_12: str | None = None) -> str:
    """`representation_version` 的覆盖段。**值派生、不可手写**（裁定 83§5 / A2 `vla_runtime` 范式）。

    为什么把 cap 的哈希拼进去：① 的保证完全依赖"声明区间是**哪一份**"。区间换了而版本串没换，
    下游就会拿旧版本号当同一表示 ⇒ 与"源名进 representation_version"（裁定 52）同族的谎报。
    """
    if target not in KNOWN_COVERAGE_TARGETS:
        raise NormContractViolation(f"未知 coverage_target={target!r}（不得进版本串）")
    tok = f"cover-{target.replace('_', '-')}-hb{float(headroom_bins):g}"
    if cover_cap is not None:
        arr = np.concatenate([np.asarray(cover_cap[0], dtype=np.float64).ravel(),
                              np.asarray(cover_cap[1], dtype=np.float64).ravel()])
        tok += f"-cap{hashlib.sha256(arr.tobytes()).hexdigest()[:8]}"
    if interval_source_sha256_12:
        tok += f"-src{str(interval_source_sha256_12)[:8]}"
    return tok


def normalize_with_case(x: np.ndarray, case: str, stats: Mapping[str, np.ndarray]) -> np.ndarray:
    """按档归一化（**一份**实现：QUANTILES 走处理器公式，IDENTITY 走本仓显式 center/gain）。"""
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    if case == CASE_QUANTILES_FLOOR:
        return reference_normalize(x, "quantiles", {"q01": stats["q01"], "q99": stats["q99"]})
    if case == CASE_IDENTITY_EXPLICIT:
        return ((x - np.asarray(stats["center"], dtype=np.float64))
                * np.asarray(stats["gain"], dtype=np.float64))
    raise NormContractViolation(f"未知 case={case!r}（只允许 {list(KNOWN_CASES)}）")


# `declared_interval_conformance()` 两个分支的字段清单（**单一真值**，裁定 90.4-1 的测量面）。
# 为什么必须有这一份常量：null 分支修前是**手写**的，本轮实测漏了 5 个键
# （`measurement_bad_length_fields` / `measurement_nonfinite_fields` / `measurement_required_fields` 等）
# ⇒ 下游若用 `.get(k, 0)` 读 null 分支，就会把"没测"读成"测到 0"
# —— 正是红线 `absence_of_measurement_is_not_measurement_of_absence` 要挡的形态。
# 键集合恒等由 `conformance_schema_parity()` **机器核**（不靠人眼比两份清单）。
CONFORMANCE_PER_DIM_FIELDS = (
    "declared_lo", "declared_hi", "frame_min", "frame_max",
    "excess_below", "excess_above",
    "n_frames_out_per_dim", "n_frames_below_per_dim", "n_frames_above_per_dim",
    "frac_frames_out_per_dim", "headroom_per_dim", "declared_travel",
    "excess_above_pct_of_travel", "excess_below_pct_of_travel",
    "headroom_consumption_ratio", "headroom_consumption_above", "headroom_consumption_below")
CONFORMANCE_FIELDS = (
    "measurement_status", "why", "verdict_semantics", "conformant", "n_frames", "n_dims",
    "n_dims_out", "dims_out", "dims_below", "dims_above",
    "headroom_consumption_max", "headroom_consumption_max_above", "headroom_consumption_max_below",
    "dims_headroom_consumed_over_half", "window_escape", "dims_window_escape",
    "window_escape_ratio_threshold", "window_escape_threshold_authority",
    "downside_deficit", "dims_downside_deficit", "upside_overflow", "dims_upside_overflow",
    "measurement_complete", "measurement_missing_fields", "measurement_bad_length_fields",
    "measurement_nonfinite_fields", "measurement_required_fields") + CONFORMANCE_PER_DIM_FIELDS
# null 分支里**允许非 None** 的键（其余一律 None = 三态的"没测"）。
CONFORMANCE_NULL_BRANCH_NON_NULL_KEYS = ("measurement_status", "why")


def _conformance_null(status: str, why: str) -> dict[str, Any]:
    """区间缺失时的三态返回：**每个**测量字段都是 None（不是 0、不是 False、不是 []）。"""
    out: dict[str, Any] = {k: None for k in CONFORMANCE_FIELDS}
    out["measurement_status"] = status
    out["why"] = why
    return out


def conformance_schema_parity(probe_frames: np.ndarray | None = None) -> dict[str, Any]:
    """机器核：`measured` 与 `not_measured_interval_absent` 两个分支的**键集合恒等**。

    为什么要一把机器核而不是"写的时候小心点"：这两个分支在本轮就已经漂移过一次（null 少 5 键）。
    schema 漂移的后果不是崩溃，是**静默读成 0**（`.get(k, 0)`）⇒ 把"没测"当"合规"。
    变异体（闸侧登记）：从 null 分支删任一键 ⇒ 本函数 `parity=false`。
    """
    fr = (np.zeros((2, 3), dtype=np.float64) if probe_frames is None
          else np.atleast_2d(np.asarray(probe_frames, dtype=np.float64)))
    iv = [np.full(fr.shape[1], -1.0), np.full(fr.shape[1], 1.0)]
    meas = declared_interval_conformance(fr, iv)
    null = declared_interval_conformance(fr, None)
    leaked = sorted(k for k, v in null.items()
                    if v is not None and k not in CONFORMANCE_NULL_BRANCH_NON_NULL_KEYS)
    return {"parity": bool(set(meas) == set(null)),
            "n_keys_measured": len(meas), "n_keys_null": len(null),
            "only_in_measured": sorted(set(meas) - set(null)),
            "only_in_null": sorted(set(null) - set(meas)),
            "null_branch_non_null_keys": leaked,
            "null_branch_non_null_allowed": list(CONFORMANCE_NULL_BRANCH_NON_NULL_KEYS),
            "declared_field_list_matches_measured": bool(set(CONFORMANCE_FIELDS) == set(meas)),
            "field_list_only": sorted(set(CONFORMANCE_FIELDS) - set(meas)),
            "measured_only_vs_field_list": sorted(set(meas) - set(CONFORMANCE_FIELDS)),
            "per_dim_fields_match_required": bool(
                list(CONFORMANCE_PER_DIM_FIELDS) == list(meas.get("measurement_required_fields") or [])),
            "why": ("两条判据：① 两分支键集合恒等；② `CONFORMANCE_FIELDS` 与 measured 分支实际产出的"
                    "键集合恒等（防止只加进实现、忘了加进清单 ⇒ null 分支又漏键）")}


def declared_interval_conformance(frames: np.ndarray,
                                  physical_interval: Sequence[np.ndarray] | None) -> dict[str, Any]:
    """**测量**（不是判定）：数据里有多少状态落在声明物理区间之外、超出多少、头寸吃掉几成。

    为什么必须独立于 `Tsat` 再量一遍（本轮实测到的形态，不是假想）：`widen_to_cover()` 留了
    1 个 bin 的头寸，而 pilot-10 实测三个维的越界量（dim6 5.85e-4 / dim13 3.15e-4 /
    dim10 1.878e-2）**都小于该维头寸**（3.55e-3 / 3.55e-3 / 2.454e-2）⇒ 归一化后不越 ±1
    ⇒ `Tsat`/`Td1`/`Te1` 全绿。若只看那三把牙，「1605 帧（58.45%）超出声明区间」这个事实
    会被头寸**静默吸收** —— 那是缺陷类 ⑯ 的镜像：不是空集上的平凡真，而是**有余量上的平凡绿**。
    三态（红线 `absence_of_measurement_is_not_measurement_of_absence`，裁定 88.3-1）：
    区间缺失 ⇒ `measurement_status="not_measured_interval_absent"`、其余字段 null（**不**读成"合规"）。

    **裁定 90.4-1 改判后的口径（本函数是"必落盘的测量"，不是判据）**：
      · `jnt_range` 是**软边界**（勘误件 `physical_range_effective_rule` 自己写明；D 在裁定 90.2 #15
        承认把软边界当硬界是它的第 15 号同型错误）⇒ **越出声明区间本身是物理合法，永不因此判红**；
      · 判红移到有物理含义的量：`headroom_consumption_max ≥ WINDOW_ESCAPE_RATIO(=1.0)`（窗口逃逸）、
        以及**下侧**越界（`processor_pi05.py:77` 的结构不对称：`x ≥ 1` ⇒ 合法顶 bin 255 优雅饱和，
        `x < -1` ⇒ **非法 bin -1** 静默进 prompt ⇒ 下侧覆盖不足 = 正确性缺陷，上侧越界 = 分辨率/饱和事实）；
      · 因此本函数必须**分侧**给量（`*_above` / `*_below`）并给"占声明行程的百分比"，
        否则下游只能拿到一个混合了两侧的 max，无法执行上面的分治。
    """
    if physical_interval is None:
        # 裁定 90.4-1 的三态占位：区间缺失时**每个**字段都必须是 null，不许是 0/False/[]
        # （红线 `absence_of_measurement_is_not_measurement_of_absence`：没测 ≠ 测到没有）。
        # 字段集由 `_conformance_null()` 从**同一份**清单生成 ⇒ 两个分支的 schema 恒等，
        # 由 `conformance_schema_parity()` 机器核（手写两份清单必然漂移，本轮就漂移过一次）。
        return _conformance_null("not_measured_interval_absent",
                                 "physical_interval 未提供 ⇒ 无法测量；**不得**读成『没有越界』")
    fr = np.atleast_2d(np.asarray(frames, dtype=np.float64))
    lo = np.asarray(physical_interval[0], dtype=np.float64)
    hi = np.asarray(physical_interval[1], dtype=np.float64)
    below = np.maximum(lo - fr.min(axis=0), 0.0)
    above = np.maximum(fr.max(axis=0) - hi, 0.0)
    dims = sorted(set(int(i) for i in np.nonzero(below > 0)[0]) |
                  set(int(i) for i in np.nonzero(above > 0)[0]))
    n_below = [int((fr[:, i] < lo[i]).sum()) for i in range(fr.shape[1])]
    n_above = [int((fr[:, i] > hi[i]).sum()) for i in range(fr.shape[1])]
    n_out = [int(((fr[:, i] < lo[i]) | (fr[:, i] > hi[i])).sum()) for i in range(fr.shape[1])]
    headroom = HEADROOM_BINS_DEFAULT * BIN_WIDTH * np.maximum(hi - lo, 1e-12) / 2.0
    exc = np.maximum(below, above)
    ratio = np.where(headroom > 0, exc / headroom, np.inf)
    travel = np.maximum(hi - lo, 1e-12)
    # ⚠ 分侧比值不能写成 `np.inf * (x > 0)`：`inf * False = nan`（0×inf）⇒ 头寸为 0 且该侧无越界
    # 的维会落成 nan，而 nan 会让 `np.any(escape)` 与 `np.max` 静默失真。实测踩过（本轮）。
    safe_h = np.where(headroom > 0, headroom, 1.0)
    ratio_above = np.where(headroom > 0, above / safe_h, np.where(above > 0, np.inf, 0.0))
    ratio_below = np.where(headroom > 0, below / safe_h, np.where(below > 0, np.inf, 0.0))
    escape = ratio >= WINDOW_ESCAPE_RATIO
    res = {"measurement_status": "measured",
            # ⚠ `conformant` 是**测量名**不是判据名（裁定 90.4-1：越界本身不判红）。
            # 保留字段只为与修前产物可比；判据在 `Tlo`/`Tesc` 上，见 `verdict_semantics`。
            "conformant": bool(not dims),
            "n_frames": int(fr.shape[0]),
            "n_dims": int(fr.shape[1]),
            "declared_lo": lo.tolist(), "declared_hi": hi.tolist(),
            "frame_min": fr.min(axis=0).tolist(), "frame_max": fr.max(axis=0).tolist(),
            "n_dims_out": len(dims), "dims_out": dims,
            "dims_below": sorted(int(i) for i in np.nonzero(below > 0)[0]),
            "dims_above": sorted(int(i) for i in np.nonzero(above > 0)[0]),
            "excess_below": below.tolist(), "excess_above": above.tolist(),
            "n_frames_out_per_dim": n_out,
            "n_frames_below_per_dim": n_below,
            "n_frames_above_per_dim": n_above,
            "frac_frames_out_per_dim": [float(x) / float(fr.shape[0]) for x in n_out],
            "headroom_per_dim": headroom.tolist(),
            "headroom_consumption_ratio": [float(x) for x in ratio],
            "headroom_consumption_max": float(np.max(ratio)) if ratio.size else None,
            "dims_headroom_consumed_over_half": sorted(int(i) for i in np.nonzero(ratio > 0.5)[0]),
            # ---- 裁定 90.4-1 的分侧量（上侧 = 分辨率/饱和事实；下侧 = 正确性缺陷）----
            "declared_travel": travel.tolist(),
            "excess_above_pct_of_travel": [float(100.0 * a / t) for a, t in zip(above, travel)],
            "excess_below_pct_of_travel": [float(100.0 * b / t) for b, t in zip(below, travel)],
            "headroom_consumption_above": [float(x) for x in ratio_above],
            "headroom_consumption_below": [float(x) for x in ratio_below],
            "headroom_consumption_max_above": float(np.max(ratio_above)) if ratio_above.size else None,
            "headroom_consumption_max_below": float(np.max(ratio_below)) if ratio_below.size else None,
            "window_escape": bool(np.any(escape)) if escape.size else None,
            "dims_window_escape": sorted(int(i) for i in np.nonzero(escape)[0]),
            "window_escape_ratio_threshold": WINDOW_ESCAPE_RATIO,
            "window_escape_threshold_authority": ("裁定 90.4-1：`headroom_consumption_max ≥ 1.0` = "
                                                  "**窗口逃逸的定义**，不是调参项；90.6-1 禁止放宽"),
            "downside_deficit": bool(np.any(below > 0)),
            "dims_downside_deficit": sorted(int(i) for i in np.nonzero(below > 0)[0]),
            "upside_overflow": bool(np.any(above > 0)),
            "dims_upside_overflow": sorted(int(i) for i in np.nonzero(above > 0)[0]),
            "why": ("越界量 / 1 bin 头寸：≥1 ⇒ 头寸吸收不住（状态逃出被覆盖窗口 ⇒ 归一化后必越 ±1）；"
                    "<1 ⇒ **当前**被头寸吸收（`Tsat` 因此绿），但那是余量、不是合规"),
            "verdict_semantics": ("裁定 90.4-1：`dims_out` 非空**本身不判红**（软边界）。硬红只在 "
                                  "`window_escape`（`Tesc`）与 `downside_deficit`（`Tlo`）上；"
                                  "`upside_overflow` 出 **warning + 量级**（`Tovr`）；"
                                  "非法 bin -1 由 `Te1`/`Te2` 绝对硬红")}
    # 测量自证完整性：牙 `Tiv_out_of_declared_interval_is_measured` 判的是**这块**，
    # 不判越界量本身（否则又把"测量"变回"判据"）。缺字段/非有限/长度不符 ⇒ 该牙红。
    per_dim_fields = CONFORMANCE_PER_DIM_FIELDS
    missing = [k for k in per_dim_fields if res.get(k) is None]
    bad_len = [k for k in per_dim_fields
               if not missing and k not in missing and len(res[k]) != fr.shape[1]]
    nonfinite = [k for k in per_dim_fields
                 if k not in missing and k not in bad_len
                 and not bool(np.all(np.isfinite(np.asarray(res[k], dtype=np.float64))))]
    res["measurement_complete"] = bool(not missing and not bad_len and not nonfinite)
    res["measurement_missing_fields"] = missing
    res["measurement_bad_length_fields"] = bad_len
    res["measurement_nonfinite_fields"] = nonfinite
    res["measurement_required_fields"] = list(per_dim_fields)
    return res


def normalize_provenance(stats_provenance: str | None) -> str:
    """`None`/空串一律显式落成 `undeclared`（**不静默当绿**）。"""
    v = (stats_provenance or "").strip()
    return v or STATS_PROVENANCE_UNDECLARED


def bc_admission(stats_provenance: str | None, *, gate_verdict: str | None = None,
                 gate_run_dir: str | None = None,
                 gate_verdict_sha256_12: str | None = None,
                 gate_verdict_class1: str | None = None) -> dict[str, Any]:
    """BC 准入判定（供生成器/闸/下游共用同一份口径，避免三处各写一遍）。

    裁定 **93.4**（E2）起本函数**多带四个字段**：`gate_verdict` / `gate_verdict_green` /
    `gate_run_dir` / `gate_verdict_sha256_12`。
    为什么必须改（本轮**实测到过**的状态，不是假想）：修前判据只有
    `prov in BC_ADMISSIBLE_PROVENANCES`（纯标签派生）⇒ 对数据质量盲，出现过
    「`admissible_for_bc=true` 而同一批数据的 matrix 顶层 `verdict=RED`」这个分叉
    （`runs/vla/c2_norm_contract_20260929/mainline_status.json` vs 同目录 `matrix.json`，
    两者同批产出）。标签说的是"这批 stats 与 BC 数据同源"，它**说不出**"这批数据过了闸"。

    `admissible_for_bc` 的语义**保持不变**（= 标签派生；`pred_G40` 等既有消费方按它判），
    闸 verdict 走**独立字段** + 独立牙 `Tbcad_admission_requires_green_gate`，由消费方 AND。
    这样做的理由：把两件事压进一个布尔会让"标签错"与"闸红"两种完全不同的失效无法区分。

    三值纪律（红线 `absence_of_measurement_is_not_measurement_of_absence`）：调用方没给闸证据
    ⇒ `gate_verdict=null`、`gate_verdict_green=null`、`gate_verdict_measurement_status=
    "not_measured"`。**不写 `false`**（那等于宣称"测过了、闸是红的"），也**不静默当绿**。

    裁定 **97.3**（结构性收窄，用户三分类在码层的落地）起本函数**再多五个字段**：
    `gate_verdict_class1` / `gate_verdict_class1_green` / `gate_verdict_class1_measurement_status`
    / `gate_verdict_class1_required_for_bc` / `bc_blocking_caliber`，而**准入 AND 的对象从顶层
    `verdict` 改成 `verdict_class1`**。为什么必须改（本轮**实测到过**的形态，不是假想）：顶层
    `verdict` 只要被**任何**一颗 `blocking=True` 的 check 拉红就变 RED，而 `G20_write_scope`
    （写入面记账，Ⅲ 类）与 `G24`/`G25`（变异体台账完备性，Ⅱ 类）都是 **run 级元牙**、
    **一个字节都不碰训练数据** ⇒ **一颗 Ⅲ 类记账红就能把 BC 挡死**（= 用户点出的"第二类被升成
    第一类"；D 在裁定 94.3 犯的是同一个错，同型错误 #20）。收窄之后：**BC 被禁的判据 =
    `verdict_class1 = RED` 或 `admissible_for_bc = false` 或 `Tp5` 同源不成立**（裁定 97.5）。
    **顶层 `verdict` 的语义与极性一字未改**：class-2/3 的红照样让 `verdict = RED`、照样登记、
    照样在里程碑审查时看、照样必须在 **S5 前清零**；变的只是"它是否单独构成停训理由"。
    三值纪律对 `gate_verdict_class1` **同样适用**：调用方没给 ⇒ `null` + `not_measured`，
    **不写 `false`、不静默当绿**；且**早于裁定 97.3 的闸产物里没有 `verdict_class1` 字面值**
    ⇒ 解析方必须落 `not_measured`，**不许拿顶层 `verdict` 顶替**（顶替 = 把"没测这一项"
    谎报成"测了、且与顶层同值"）。
    """
    prov = normalize_provenance(stats_provenance)
    gv = (str(gate_verdict).strip() or None) if gate_verdict is not None else None
    gvc1 = ((str(gate_verdict_class1).strip() or None)
            if gate_verdict_class1 is not None else None)
    return {"stats_provenance": prov,
            "admissible_for_bc": prov in BC_ADMISSIBLE_PROVENANCES,
            "required_provenance_for_bc": list(BC_ADMISSIBLE_PROVENANCES),
            # ---- 裁定 93.4 新增（四字段 + 两个登记项）----
            "gate_verdict": gv,
            "gate_verdict_measurement_status": ("measured" if gv else "not_measured"),
            "gate_verdict_green": (None if not gv else bool(gv == GATE_VERDICT_PASS)),
            "gate_verdict_required_for_bc": GATE_VERDICT_PASS,
            "gate_run_dir": gate_run_dir,
            "gate_verdict_sha256_12": gate_verdict_sha256_12,
            # ---- 裁定 97.3-3 新增：准入 AND 的对象 = `verdict_class1`（不是顶层 `verdict`）----
            "gate_verdict_class1": gvc1,
            "gate_verdict_class1_measurement_status": ("measured" if gvc1 else "not_measured"),
            "gate_verdict_class1_green": (None if not gvc1 else bool(gvc1 == GATE_VERDICT_PASS)),
            "gate_verdict_class1_required_for_bc": GATE_VERDICT_PASS,
            "bc_blocking_caliber": ("verdict_class1（裁定 97.3-3 / 97.5）：BC 被禁的判据 = "
                                    "verdict_class1=RED 或 admissible_for_bc=false 或 Tp5 同源不成立；"
                                    "顶层 verdict=RED 本身**不再**等于 BC 被禁"),
            "authority": ("裁定 85.4-3（同源硬闸：pilot 与 formal 的 stats 不得互替）"
                          " + 裁定 93.4（BC 准入必须 AND 闸 verdict；消费方还须自己复算"
                          " `gate_verdict_sha256_12` 对账，不一致 ⇒ `LearnerRefused`）"
                          " + 裁定 97.3-3（AND 按类收窄到 `verdict_class1`；class-2/3 的 run 级"
                          "元牙不得单独禁 BC）与 97.5（顶层 RED 不是停训理由）")}


def crosscheck_freshness_tooth(*, checked_at: str | None, run_started_at: str | None,
                               generated_at: str | None, scope: str = "crosscheck_status",
                               blocking: bool = False,
                               clock_skew_tolerance_s: float = 2.0) -> dict[str, Any]:
    """裁定 **93.6**（E5）：`checked_at` 的**新鲜度牙**（WARN 级、非阻塞）。

    为什么需要（实测到的沉默缺口，不是理论）：`crosscheck_status.checked_at` 修前在**全仓没有任何
    消费方**（C2 grep 命中 0，D 在 M18 的注释里也把它登记为"沉默缺口"）⇒「落笔时刻真去看过那个
    路径」这条纪律在交叉核对臂上**没有牙**；同族形态本轮真踩过一次（01:3x C2 写"等 B2"时数据
    其实已落地 25 min）。

    判据（**参考区间 = 本次 run 的窗口 `[run_started_at, generated_at]`**，含时钟偏差容忍）：
    `checked_at` 必须存在、可解析，且落在该窗口内。
      · 早于窗口起点 ⇒ 它是**上一次的**读数被写死进本次产物（M18/M38 的形态）⇒ WARN；
      · 晚于窗口终点 ⇒ 时刻是**未来**的（凭空写一个还没发生的时刻）⇒ WARN。

    ⚠ **落点差异（C2 报 D，不改 D 的判词）**：裁定 93.6 的字面是「`checked_at` 不早于本次 run 的
    `generated_at`」。实测（`runs/vla/c2_norm_contract_20260929/gate/run_20260930_113655/`
    `arm_mainline/matrix.json`）：`generated_at = 11:37:01` 是在 **run 结束写盘那一刻**盖的，
    而 `crosscheck_status.checked_at = 11:37:00` 是**在 run 中途**真去看路径时盖的
    ⇒ `checked_at < generated_at` 恒成立 ⇒ 字面判据会**结构性恒 WARN**（裁定 27.1：恒红/恒真
    的闸等于没有闸）。本实现保留 D 的**意图**（"落笔时刻真去看过"）而把参考点换成可满足的
    run 窗口，并把两个 lag 都逐秒落盘 ⇒ D 可以按实测数字改判。

    三值纪律：任一侧缺失/不可解析 ⇒ `measurement_status = "not_measured"`、`ok = False` ⇒ WARN
    （**不**静默当绿，也**不**假装测到过）。
    `blocking` 默认 **False**（裁定 93.6：不升 P0 —— 交叉核对臂不是 BC 输入，风险不对称）。
    返回的 dict 与 `evaluate_contract()` 的 `tooth()` **同一个 schema**（裁定 78.2 的六个公共
    字段 + C2 扩展字段）⇒ 消费方（闸/生成器）可以用同一份代码读它。
    """
    tid = "Txr_crosscheck_freshness_is_registered"
    required = ("`checked_at` 存在且落在本次 run 的窗口 `[run_started_at, generated_at]` 内"
                f"（时钟偏差容忍 {clock_skew_tolerance_s}s）")
    parsed, parse_err = {}, None
    for key, val in (("checked_at", checked_at), ("run_started_at", run_started_at),
                     ("generated_at", generated_at)):
        try:
            parsed[key] = datetime.fromisoformat(str(val)) if val else None
        except (TypeError, ValueError) as exc:
            parsed[key] = None
            parse_err = f"{key}: {type(exc).__name__}: {exc}"
    tc, ts, tg = parsed["checked_at"], parsed["run_started_at"], parsed["generated_at"]
    if tc is None or ts is None or tg is None or parse_err is not None:
        status_meas, ok = "not_measured", False
        lag_before = lag_after = None
    else:
        status_meas = "measured"
        lag_before = float((ts - tc).total_seconds())   # > 0 ⇒ checked_at 早于 run 起点 = 陈旧
        lag_after = float((tc - tg).total_seconds())    # > 0 ⇒ checked_at 晚于 run 终点 = 未来时刻
        ok = bool(lag_before <= clock_skew_tolerance_s
                  and lag_after <= clock_skew_tolerance_s)
    return {"id": tid,
            "name": f"{scope}.checked_at 是新鲜的（落在本次 run 的窗口内）",
            "ok": ok,
            "status": ("PASS" if ok else ("RED" if blocking else "WARN")),
            "required": required, "red_when": required,
            "observed": (f"checked_at={checked_at} run_started_at={run_started_at} "
                         f"generated_at={generated_at} "
                         f"lag_before_run_start_s={lag_before} lag_after_generated_at_s={lag_after} "
                         f"measurement_status={status_meas}"
                         + ("" if parse_err is None else f" parse_error={parse_err}")),
            "authority": ("裁定 93.6（E5）：批准 C2 在自己的写入面补一颗 WARN 级新鲜度牙；不升 P0"
                          "（交叉核对臂不是 BC 输入，风险不对称）"),
            "note": ("变异体形态复用已有 **M18**（`checked_at` 写死成过去时刻）⇒ 必须出 WARN；"
                     "本牙的参考点是 **run 窗口**而不是裁定 93.6 的字面 `generated_at`，"
                     "理由与实测数字见本函数文档串（落点差异已报 D，C2 不改 D 的判词）。"
                     "本牙**不**替 `mainline_status_recheck`（G31）判 BC 侧的新鲜度。"),
            "applies_when": True, "blocking": bool(blocking),
            "blocking_reason": ("裁定 93.6：WARN 级、非阻塞（交叉核对臂不是 BC 输入）"
                                if not blocking else "调用方显式升为 blocking"),
            "scope": scope,
            "checked_at": checked_at, "run_started_at": run_started_at,
            "generated_at": generated_at,
            "lag_before_run_start_s": lag_before, "lag_after_generated_at_s": lag_after,
            "clock_skew_tolerance_s": clock_skew_tolerance_s,
            "reference_window": "[run_started_at, generated_at]",
            "literal_ruling_text_reference": "generated_at（实测为结构性不可满足 ⇒ 已报 D）",
            "measurement_status": status_meas,
            "parse_error": parse_err}


class NormContractViolation(RuntimeError):
    """契约违规（红）。消息里必须点名违规的维/条目与判据出处，不许只说"不合规"。

    `payload` = 抛出时刻的逐牙明细（含红的行）。带上它是为了**红的时候也能拿到证据**：
    调用方若在 `except` 里只留消息，就无法回答"哪把牙咬的、其它牙什么状态"。
    """

    def __init__(self, message: str, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload


# ---------------- 参考实现（逐字对应 site-packages 的公式） ----------------
def reference_normalize(x: np.ndarray, mode: str, stats: Mapping[str, np.ndarray],
                        eps: float = LEROBOT_EPS) -> np.ndarray:
    """对应 `normalize_processor.py:305`–`:395`。mode ∈ {identity,mean_std,min_max,quantiles,quantile10}。"""
    x = np.asarray(x, dtype=np.float64)
    if mode == "identity":
        return x                                    # :306-307 原样返回
    if mode == "mean_std":
        denom = stats["std"] + eps                  # :335
        return (x - stats["mean"]) / denom          # :338
    if mode == "min_max":
        denom = stats["max"] - stats["min"]         # :352
        denom = np.where(denom == 0, eps, denom)    # :353-355
        return 2.0 * (x - stats["min"]) / denom - 1.0   # :361
    if mode == "quantiles":
        denom = stats["q99"] - stats["q01"]         # :369
        denom = np.where(denom == 0, eps, denom)    # :371-374
        return 2.0 * (x - stats["q01"]) / denom - 1.0   # :377
    if mode == "quantile10":
        denom = stats["q90"] - stats["q10"]         # :386
        denom = np.where(denom == 0, eps, denom)    # :388-391
        return 2.0 * (x - stats["q10"]) / denom - 1.0   # :394
    raise ValueError(f"Unsupported normalization mode: {mode}")


def reference_digitize(xn: np.ndarray) -> np.ndarray:
    """对应 `processor_pi05.py:77`：`np.digitize(x, linspace(-1,1,257)[:-1]) - 1`。"""
    return np.digitize(np.asarray(xn, dtype=np.float64),
                       bins=np.linspace(-1, 1, N_BINS + 1)[:-1]) - 1


def saturation_report(xn: np.ndarray) -> dict[str, Any]:
    """归一化后的饱和/越界事实：多少维、多少帧落到 bin 255 或 -1。"""
    xn = np.atleast_2d(np.asarray(xn, dtype=np.float64))
    bins = reference_digitize(xn)
    above = xn >= 1.0
    below = xn < -1.0
    return {
        "n_frames": int(xn.shape[0]), "n_dims": int(xn.shape[1]),
        "n_values_above_1": int(above.sum()), "n_values_below_-1": int(below.sum()),
        "n_dims_with_high_sat": int(np.unique(np.nonzero(above)[1]).size),
        "n_dims_with_low_sat": int(np.unique(np.nonzero(below)[1]).size),
        "dims_with_high_sat": sorted(int(i) for i in np.unique(np.nonzero(above)[1])),
        "dims_with_low_sat": sorted(int(i) for i in np.unique(np.nonzero(below)[1])),
        "bin_min": int(bins.min()), "bin_max": int(bins.max()),
        "illegal_bin_values_present": bool((bins == SAT_BIN_LOW).any()),
        "abs_max_normalized": float(np.abs(xn).max()),
    }


# ---------------- stats 构建 ----------------
def _q(a: np.ndarray, p: float) -> np.ndarray:
    return np.quantile(a, p, axis=0)


def build_stats(frames: np.ndarray, *, quantile_policy: str = "q01_q99") -> dict[str, np.ndarray]:
    """从 [N,D] 真实帧算 stats。`frames` 必须是**实测**数据（源与 provenance 由调用方登记）。"""
    frames = np.atleast_2d(np.asarray(frames, dtype=np.float64))
    if frames.ndim != 2:
        raise NormContractViolation(f"frames 必须是 [N,D]，实测 shape={frames.shape}")
    out = {"mean": frames.mean(axis=0), "std": frames.std(axis=0),
           "min": frames.min(axis=0), "max": frames.max(axis=0),
           "median": np.median(frames, axis=0),
           "q01": _q(frames, 0.01), "q99": _q(frames, 0.99),
           "q10": _q(frames, 0.10), "q90": _q(frames, 0.90)}
    # 近常量维的两种客观刻画（都不依赖阈值拍脑袋）：分位距 与 逐步差分的中位绝对值（噪声尺度）
    out["span_q99_q01"] = out["q99"] - out["q01"]
    out["span_max_min"] = out["max"] - out["min"]
    if frames.shape[0] >= 2:
        d = np.diff(frames, axis=0)
        out["noise_mad_step"] = np.median(np.abs(d - np.median(d, axis=0)), axis=0)
        out["step_abs_median"] = np.median(np.abs(d), axis=0)
    else:
        out["noise_mad_step"] = np.zeros(frames.shape[1])
        out["step_abs_median"] = np.zeros(frames.shape[1])
    out["quantile_policy"] = np.full(frames.shape[1], quantile_policy, dtype=object)
    out["n_frames"] = np.full(frames.shape[1], int(frames.shape[0]))
    return out


def widen_to_cover(stats: Mapping[str, np.ndarray], must_cover: Sequence[np.ndarray],
                   *, headroom_bins: float = HEADROOM_BINS_DEFAULT,
                   cover_cap: Sequence[np.ndarray] | None = None) -> dict[str, Any]:
    """把 q01/q99 展宽到**覆盖必须覆盖的取值集合**（起态位姿 + 建 stats 的帧）。

    为什么必须这一步（实测，不是理论）：q01/q99 按定义把两端各 1% 甩在外面，而**起始位姿在
    示范里是重复出现的极值**（每集第 0 帧都是它）⇒ 用未展宽的 q01/q99 归一化，起态会落到
    [-1,1] 之外 ⇒ `processor_pi05.py:77` 的 digitize 给出 **bin -1**（非法 bin，静默进 prompt）。
    本线 env 诊断档实测：未展宽时起态越界维 = `[1, 9]`（原始越界维 = `[2, 9]`，`max|state|=1.16`）。

    `cover_cap`（裁定 87.3-2 **条件 c**：① 不得变成赦免令）：给定时，展宽结果**不得**超出
    `cap ± 头寸`。它是"覆盖到声明物理区间是**上限**"这句话的可执行形式 —— 谁把 build 帧塞回
    `must_cover`（= 数据越界就跟着展宽），这里就会点名到维地报 `cover_cap_violation_dims`，
    而不是让越界数据静默把自己的窗口撑大。`cover_cap=None`（修前口径）⇒ 无可查、字段为 null。
    """
    q01 = np.asarray(stats["q01"], dtype=np.float64).copy()
    q99 = np.asarray(stats["q99"], dtype=np.float64).copy()
    cov = np.concatenate([np.atleast_2d(np.asarray(m, dtype=np.float64)) for m in must_cover], axis=0)
    lo, hi = cov.min(axis=0), cov.max(axis=0)
    # 头寸 = 归一化空间里 `headroom_bins` 个 bin 折算回物理量纲（span/2 对应 1.0）。
    # 不留头寸时，起态的极值维归一化后正好 = ±1.0 ⇒ digitize 落进边界 bin（与越界值同 bin）。
    span = np.maximum(hi - lo, 1e-12)
    delta = headroom_bins * BIN_WIDTH * span / 2.0
    q01_new, q99_new = np.minimum(q01, lo - delta), np.maximum(q99, hi + delta)
    # 上限判据（条件 c）判的是**覆盖集**有没有超出声明区间，不是"最终窗口"有没有超出。
    # 为什么必须这样切（本轮实测到的形态）：下限烘入在前、覆盖在后，而 F1 下限是**围绕中位数对称**
    # 展宽的 ⇒ 中位数靠近限位的维（本轮 dim10：median≈3.11、声明 hi=π）烘完下限后 q99 就已经
    # 超出 `hi + 头寸` 了。若把判据写在最终 q01/q99 上，就会把"下限为防噪声放大而做的展宽"
    # 误报成"为了赦免越界数据而展宽" —— 两件事的成因与处置完全不同。
    # 覆盖集越界只有一种成因：有人把 build 帧（或别的实测数据）塞回 `must_cover`，
    # 那正是条件 c 要挡的赦免令 ⇒ 判据钉在 `lo/hi`（覆盖集的极值）上，非空即点名到维。
    if cover_cap is None:
        cap_lo = cap_hi = None
        viol = []
        respected = None          # **没测**，不是"通过"（红线 88.3-1：三态）
        beyond = None
    else:
        cap_lo = np.asarray(cover_cap[0], dtype=np.float64)
        cap_hi = np.asarray(cover_cap[1], dtype=np.float64)
        tol = 1e-12 + 1e-9 * np.maximum(cap_hi - cap_lo, 0.0)
        viol = sorted(int(i) for i in np.nonzero(
            (lo < cap_lo - tol) | (hi > cap_hi + tol))[0])
        respected = bool(not viol)
        # 另一件事必须**分开登记**（不是判据）：最终窗口比声明区间宽多少、宽在哪几维。
        # 它会被 `Tsat` 读到（窗口越宽，越界状态越不容易饱和）⇒ 不登记就等于让
        # "下限把窗口撑过限位"这件事静默地把条件 c 的牙钝掉。牙 `Tiv` 量的是数据本身，
        # 不受窗口影响 ⇒ 两者合起来才没有沉默缺口。
        beyond = {"dims_low": sorted(int(i) for i in np.nonzero(q01_new < cap_lo - tol)[0]),
                  "dims_high": sorted(int(i) for i in np.nonzero(q99_new > cap_hi + tol)[0]),
                  "amount_low": np.maximum(cap_lo - q01_new, 0.0).tolist(),
                  "amount_high": np.maximum(q99_new - cap_hi, 0.0).tolist(),
                  "cause": ("下限烘入（围绕中位数对称展宽）与 1 bin 头寸；**不是**为覆盖越界数据而展宽"
                            "（覆盖集越界由 `cover_cap_violation_dims` 单独判）"),
                  "effect_on_teeth": ("窗口越过声明区间会让 `Tsat`/`Td1` 对**小幅**越界状态失声"
                                     "（本轮实测 dim10 头寸消耗比 0.765）⇒ 由 "
                                      "`Tiv_out_of_declared_interval_is_measured`（测量）与 "
                                      "`Tesc_no_covered_window_escape` / "
                                      "`Tlo_no_downside_coverage_deficit`（判据）独立量数据本身兜住；"
                                      "裁定 90.4-1 前这里引的是 `Tiv_no_state_outside_declared_interval`，"
                                      "该牙的极性已被撤回")}
    return {"q01": q01_new, "q99": q99_new,
            "cover_min": lo, "cover_max": hi,
            "widened_dims_low": sorted(int(i) for i in np.nonzero(q01_new < q01)[0]),
            "widened_dims_high": sorted(int(i) for i in np.nonzero(q99_new > q99)[0]),
            "n_widened": int((q01_new < q01).sum() + (q99_new > q99).sum()),
            "headroom_bins": headroom_bins,
            "headroom_delta": delta.tolist(),
            "cover_cap": (None if cap_lo is None else {"lo": cap_lo.tolist(), "hi": cap_hi.tolist()}),
            "cover_cap_respected": respected,
            "cover_cap_violation_dims": viol,
            "window_beyond_declared_interval": beyond,
            # ⚠ 本行修前写的是"展宽在**下限烘入之前**做"，与实现相反（`build_case` 是**先烘下限、
            # 后覆盖**，且那里有实测理由：反过来时 `apply_scale_floor` 围绕 median 对称展宽会把刚
            # 覆盖进来的起态甩出 [-1,1] ⇒ Tc 恒红）。属"声明与实现分叉"（裁定 88 的
            # `redline_provenance_discipline` 同族：读实现原文，不读旧声明）⇒ 本轮按实现改正。
            "note": "调用顺序 = **先下限烘入、后覆盖展宽**；两者都作用于落盘的 q01/q99"}


def near_constant_dims(stats: Mapping[str, np.ndarray], *,
                       rel_tol: float = NEAR_CONSTANT_REL_TOL) -> list[int]:
    """近常量维 = **原始**分位距相对物理行程可忽略（`rel_tol` 是标记阈值，不是放大阈值）。

    为什么读 `denom_raw` 而不是 `span_q99_q01`（实测教训，2026-09-29 23:4x，变异体逼出来的）：
    `widen_to_cover()` 之后 build 侧把**展宽后**的 span 写回了 `span_q99_q01`，展宽量里混进了
    覆盖头寸 ⇒「这一维在示范里几乎不动」这个**数据事实**被抹掉 ⇒ hold 相那 10 个下限绑定维
    一个都不被判为近常量 ⇒ 牙 `Tr1`（近常量维无下限保护必须红）在 `--floor-coef-scale 0`
    变异体上**不红 = 恒真牙**（裁定 27.1：恒真的闸等于没有闸）。
    `denom_raw` = 下限烘入前、展宽前的原始分位距 ⇒ 只有它才是数据的性质。缺失时回落
    `span_q99_q01`（保持对旧调用方的兼容），并在返回值里无从体现——所以**调用方必须传
    `denom_raw`**；本模块的 `stats_payload()` 已把 `denom_raw` 列为必落盘键。
    """
    span = np.asarray(stats.get("denom_raw", stats["span_q99_q01"]), dtype=np.float64)
    rng = np.asarray(stats.get("physical_range", span), dtype=np.float64)
    rng = np.where(rng > 0, rng, 1.0)
    return sorted(int(i) for i in np.nonzero(span / rng <= rel_tol)[0])


# ---------------- scale 下限：两个候选族（裁定 51①：给两个候选值 + 各自真实数据效果） ----------------
@dataclass
class FloorFamily:
    """下限族。`coef` 就是 D 要的两个候选值所在。"""
    name: str
    coef: float
    formula: str
    rationale: str

    def floors(self, *, physical_range: np.ndarray, noise: np.ndarray) -> np.ndarray:
        if self.name == "F1_physical_range_fraction":
            return self.coef * np.asarray(physical_range, dtype=np.float64)
        if self.name == "F2_noise_scale_multiple":
            return self.coef * np.asarray(noise, dtype=np.float64)
        raise NormContractViolation(f"未知下限族：{self.name}")


F1_CANDIDATES = (0.05, 0.02)     # 物理行程比例：5% / 2%
# 加载期自检（恒真牙的反面：这条 assert 一旦不成立就 import 失败，不会静默给出错判据）
assert NEAR_CONSTANT_REL_TOL == min(F1_CANDIDATES), (
    f"NEAR_CONSTANT_REL_TOL={NEAR_CONSTANT_REL_TOL} 必须 = min(F1_CANDIDATES)={min(F1_CANDIDATES)}"
    "：两处默认值分叉会让闸内判定与行级统计对同一份数据给出不同的近常量维集合（本轮实测到过）")
assert FLOOR_MATERIALITY_FRACTION == min(F1_CANDIDATES)
F2_CANDIDATES = (4.0, 2.0)      # 噪声尺度倍数：4×MAD / 2×MAD


def floor_family(name: str, coef: float) -> FloorFamily:
    if name == "F1_physical_range_fraction":
        return FloorFamily(name, coef, "floor_d = coef * physical_range_d",
                           "示范不会用满行程，但**物理行程**是客观量纲：近常量维至少保留 coef 比例的"
                           "[-1,1] 行程 ⇒ 至少 coef*256 个 bin 可用（coef=0.05 ⇒ ≥12.8 bin）。")
    if name == "F2_noise_scale_multiple":
        return FloorFamily(name, coef, "floor_d = coef * noise_mad_step_d",
                           "小于噪声尺度的差异不携带信息：把 denom 抬到 coef×噪声，"
                           "噪声最多占 [-1,1] 的 1/coef ⇒ 不饱和，同时保留真实变化的分辨率。")
    raise NormContractViolation(f"未知下限族：{name}（只允许 F1_physical_range_fraction / F2_noise_scale_multiple）")


def apply_scale_floor(stats: Mapping[str, np.ndarray], floors: np.ndarray) -> dict[str, Any]:
    """把下限**烘进 q01/q99**（处理器内部只算 `q99-q01`，无法从外部注入下限）。

    展宽方式：围绕 `median` 对称展宽到 `denom_eff = max(q99-q01, floor)`。
    围绕 median 而不是围绕 q01，是为了让近常量维的**实测值仍落在 [-1,1] 内**（否则一展宽就越界）。
    """
    q01 = np.asarray(stats["q01"], dtype=np.float64).copy()
    q99 = np.asarray(stats["q99"], dtype=np.float64).copy()
    med = np.asarray(stats["median"], dtype=np.float64)
    floors = np.asarray(floors, dtype=np.float64)
    denom = q99 - q01
    denom_eff = np.maximum(denom, floors)
    binding = denom_eff > denom
    q01_new = np.where(binding, med - denom_eff / 2.0, q01)
    q99_new = np.where(binding, med + denom_eff / 2.0, q99)
    return {"q01": q01_new, "q99": q99_new, "denom_raw": denom, "denom_effective": denom_eff,
            "floor": floors, "floor_binding_dims": sorted(int(i) for i in np.nonzero(binding)[0]),
            "n_floor_binding": int(binding.sum()),
            "note": "下限烘进 q01/q99：normalize_processor.py:369 只算 q99-q01，无法外部注入下限"}


# ---------------- 逐维报告 ----------------
def dim_report(frames: np.ndarray, stats: Mapping[str, np.ndarray], *, case: str,
               physical_range: np.ndarray | None = None) -> dict[str, Any]:
    """给定 stats 与一案，逐维给出可测量事实（bin 占用、clip 比例、饱和、下限是否生效）。"""
    frames = np.atleast_2d(np.asarray(frames, dtype=np.float64))
    if case == CASE_QUANTILES_FLOOR:
        mode, st = "quantiles", {"q01": stats["q01"], "q99": stats["q99"]}
    elif case == CASE_IDENTITY_EXPLICIT:
        # IDENTITY 分支：处理器原样返回（:305-307），显式缩放由本仓做
        center = stats["center"]; gain = stats["gain"]
        xn = (frames - center) * gain
        return _report_from_normalized(frames, xn, stats, case, physical_range)
    else:
        raise NormContractViolation(f"未知 case：{case}（只允许 {KNOWN_CASES}）")
    xn = reference_normalize(frames, mode, st)
    return _report_from_normalized(frames, xn, stats, case, physical_range)


def _report_from_normalized(frames, xn, stats, case, physical_range) -> dict[str, Any]:
    bins = reference_digitize(xn)
    per_dim = []
    for d in range(xn.shape[1]):
        col, bcol = xn[:, d], bins[:, d]
        legal = bcol[(bcol >= 0) & (bcol <= SAT_BIN_HIGH)]
        per_dim.append({
            "dim": d,
            "denom_used": float(stats["q99"][d] - stats["q01"][d]) if "q01" in stats else None,
            "floor": float(stats["floor"][d]) if "floor" in stats else None,
            "floor_binding": bool(stats["denom_raw"][d] < stats["floor"][d]) if "floor" in stats else None,
            "normalized_min": float(col.min()), "normalized_max": float(col.max()),
            "normalized_abs_max": float(np.abs(col).max()),
            "clip_ratio": float(((col >= 1.0) | (col < -1.0)).mean()),
            "n_bins_occupied": int(np.unique(legal).size),
            "bins_occupied_ratio": float(np.unique(legal).size / N_BINS),
            "n_high_sat": int((col >= 1.0).sum()), "n_low_sat": int((col < -1.0).sum()),
            "illegal_bin_-1_present": bool((bcol == SAT_BIN_LOW).any()),
        })
    return {"case": case, "n_frames": int(xn.shape[0]), "n_dims": int(xn.shape[1]),
            "saturation": saturation_report(xn), "per_dim": per_dim,
            "physical_range": None if physical_range is None else np.asarray(physical_range).tolist()}


# ---------------- 契约判定（四条真牙 + 两条必红分支） ----------------
@dataclass
class ContractThresholds:
    """阈值。**clip 上限与两个下限系数都是 `proposed`：真实效果要 S1 先导 5 集数据才能定标（裁定 51①/69）。"""
    clip_ratio_cap: float = 0.01          # proposed_pending_s1（牙 d）
    min_bins_occupied: int = 8            # registered_measurement_not_a_judgment（牙 b 的可测量形式；裁定 93.1-2）
    start_pose_oob_dims_cap: int = 0      # 牙 c：起态归一化后越界维数必须 = 0（硬）
    # 近常量维标记阈值 = **最小候选下限系数**（不新造数）。
    # 实测（2026-09-29 23:5x，三份 env 采集）：原值 `1e-3` 在真实数据上**一个维都标不出来**
    # —— hold 相 `denom_raw/physical_range` 的最小值 = **1.648e-3 > 1e-3**（random 0.198、
    # sweep 0.0229）⇒ `near_constant_dims()` 恒返回 [] ⇒ 牙 `Tr1` 恒绿（恒真牙，裁定 27.1）。
    # 取 `min(F1_CANDIDATES)=0.02` 的语义是：**"原始分位距小于最小候选下限"= 该维需要下限保护**，
    # 与下限公式同源、可复算；hold 相标出 **7** 维（`<0.05` 则 10 维，与 floor_binding 实测一致）。
    ctrlrange_coverage_report_below: float = 0.95   # 只用于**记录**（裁定 51.1：不判红）
    near_constant_rel_tol: float = NEAR_CONSTANT_REL_TOL
    # 下限**实质性**阈值：下限值本身若小于 `该系数 × 物理行程`，对近常量维等于没有保护。
    # 实测依据：hold 相 `noise_mad_step` 最小 = **1.881e-07** ⇒ F2@2.0 的下限 = 3.76e-07，
    # 比 0.02 × 物理行程小 **5 个数量级** ⇒ F2 在"真正不动的维"上提供不了保护（牙 Tr3 的对象）。
    floor_materiality_fraction: float = FLOOR_MATERIALITY_FRACTION
    # ---- 裁定 93.2 补丁②：`Tres_per_dim_resolution_floor` 的三个下限（**逐维**，不用 median）----
    # 数值 **8 不是新造的**：它就是上面 `min_bins_occupied` 已有的值。裁定 93.2 改的是它的
    # **状态**（`proposed_pending_s1` → `d_calibrated_from_formal40_all_caliber`）、
    # **作用域**（只对**非近常量维**阻塞）与**口径**（全量帧 `summary_all`，不是 held-out）。
    # 定标依据（D 只读提取本轮主线臂 matrix 后落的实测件，不许改数）：
    #   `runs/vla/d_ruling_round_20260930_1010/probe_resolution_calibration_inputs.json`
    #   全量 n=11035 的 `bins_occupied_per_dim` = [23,117,114,3,47,24,87,22,117,117,5,48,22,72]
    #   ⇒ 非近常量维最小 22（**2.75×** 余量）；近常量维 dim3=3（**1.5×**）、dim10=5（**2.5×**）。
    # 近常量维的硬红下限取 **2**：低于 2 = 该维在全量帧上只占 0/1 个 bin ⇒ 归一化后**不携带任何
    # 可分辨信息**（这是算术下限、不是调参项）；`< 8` 只出 WARN 登记（= 裁定 90.4-3 的 P1 债，
    # 用户已批"速度优先"⇒ 不进 P0）。
    min_bins_occupied_non_near_constant: int = 8
    min_bins_occupied_near_constant: int = 2
    warn_bins_occupied_near_constant: int = 8
    provenance: dict[str, str] = field(default_factory=lambda: {
        "clip_ratio_cap": "proposed_pending_s1",
        # 裁定 93.1-2：`declared-only never blocking`。修前这两个值的状态串是
        # `proposed_pending_s1` / `derived_from_min_F1_candidate（C2 提议，待 S1 定标）`，
        # 而消费它们的 `Tb`/`Tr3` 却是 blocking ⇒ **未经定标的下限被当成阻塞判据**（E4 的实质）。
        # 现在状态串如实登记为"已登记的测量、不是判据"，两颗牙同时转 WARN（裁定 93.1-1）。
        "min_bins_occupied": "registered_measurement_not_a_judgment",
        "start_pose_oob_dims_cap": "ruling_51_1_c_hard",
        "ctrlrange_coverage_report_below": "ruling_51_1_downgraded_to_warning",
        "near_constant_rel_tol": "derived_from_min_F1_candidate（原 c2_proposal 1e-3 已实测为恒真，作废）",
        "floor_materiality_fraction": "registered_measurement_not_a_judgment",
        "min_bins_occupied_non_near_constant": "d_calibrated_from_formal40_all_caliber",
        "min_bins_occupied_near_constant": "d_calibrated_from_formal40_all_caliber",
        "warn_bins_occupied_near_constant": "d_calibrated_from_formal40_all_caliber"})


def evaluate_contract(*, case: str, stats: Mapping[str, np.ndarray], frames: np.ndarray,
                      start_pose: np.ndarray, source: str, features: Mapping[str, Any],
                      physical_range: np.ndarray, thresholds: ContractThresholds | None = None,
                      mainline: bool = True, eval_frames: np.ndarray | None = None,
                      force_blocking: bool = False,
                      physical_interval: Sequence[np.ndarray] | None = None,
                      stats_provenance: str | None = None,
                      consumer: str | None = None,
                      coverage_target: str | None = None,
                      all_frames: np.ndarray | None = None,
                      gate_verdict: str | None = None,
                      gate_run_dir: str | None = None,
                      gate_verdict_sha256_12: str | None = None,
                      gate_verdict_class1: str | None = None) -> dict[str, Any]:
    """返回逐牙结果；任何一条红 ⇒ 抛 `NormContractViolation`（消息点名到维）。

    牙（裁定 51①，D 已裁）：
      (a) `features` 非空 —— 清空必红（对应 A2 实测 `normalizer_processor.config.features={}`）；
      (b) 每维 scale 下限**生效** —— 近常量维不得被放大（可测量形式：合法 bin 占用数 ≥ 阈值）；
      (c) **起态覆盖闸** —— A2 实测起始位姿（`max|state|=1.16`、原始 2/14 维越界）经该 stats
          归一化后**越界维数 = 0**；
      (d) clip 比例 ≤ 上限（阈值 `proposed_pending_s1`）。
    必红分支（裁定 49.1 / 69）：
      (R1) 近常量维**没有**下限保护 ⇒ 红；
      (R2) 主线部署用 `env_derived` / `yam_abc130k` 的 stats ⇒ 红（YAM 只能当必红分支的输入）。
    溯源硬闸（裁定 85.4-2/85.4-3，本轮新增）：
      (P4) `stats_provenance` **必须显式声明且属于已知集合** —— 缺标签 ⇒ 红（不静默当绿）；
           `consumer` 若声明也必须属于已知集合；
      (P5) `consumer == "bc"` ⇒ `stats_provenance` **必须** = `formal40_bc_source`；
           喂 `pilot10_path_check` 的 stats 给 BC 配置 ⇒ **红**（D 点名的那条牙）。
           `applies_when = consumer == "bc"`：通路验证/诊断档不是 BC 输入，对它判红 = 极性错。

    裁定 **93.1**（E4 = 甲）：`Tb_scale_floor_effective` 与 `Tr3_near_constant_floor_material`
      的 `blocking` → **False**（红自动变 WARN，机制在 `tooth()` 的 status 分支）。断言文本、
      `applies_when`、`red_when` **一字未改** —— 被改的只是"未经定标的下限能否阻塞"。
      换上去的是裁定 **93.2** 的两颗 D 定标硬红：`Tz_denom_strictly_positive`（绝对硬红、全臂）
      与 `Tres_per_dim_resolution_floor`（逐维、全量口径）。**这不是放宽**：`Tr1`/`Te1`/`Te2`/
      `Tesc`/`Td1`/`Td2`/`Tp5`/`Tsat` 一颗都没动。
    裁定 **93.4**（E2）：`consumer == "bc"` 时另加 `Tbcad_admission_requires_green_gate`。
    裁定 **97.3-3**：那颗牙 AND 的对象是 **`verdict_class1`**（`gate_verdict_class1` 入参），
      **不是**顶层 `verdict`；调用方没给 ⇒ `not_measured` ⇒ 按 `!= PASS` 处理（不静默当绿）。
    """
    th = thresholds or ContractThresholds()
    frames = np.atleast_2d(np.asarray(frames, dtype=np.float64))
    # 评估帧与建 stats 的帧**分开**：同一批帧上算 clip 比例是自我印证（q01/q99 天然甩掉两端各 1%，
    # 实测 clip_max=0.0208 ≈ 2×1% 尾巴）⇒ 只有 held-out 帧上的 clip 才是"部署时会不会饱和"的事实。
    eval_x = frames if eval_frames is None else np.atleast_2d(np.asarray(eval_frames, dtype=np.float64))
    eval_scope = eval_scope_of(eval_frames)     # 牙名里的 "held-out" 在本行成不成立（见 EVAL_SCOPE_NOTE）
    start_pose = np.asarray(start_pose, dtype=np.float64).reshape(1, -1)
    teeth: list[dict[str, Any]] = []
    red: list[str] = []

    warnings: list[str] = []

    def tooth(tid, name, ok, required, observed, authority, blocking=True, note=None,
              applies_when=True, extra=None, blocking_reason=None):
        # `status` 区分 ok=false 与 n_a（裁定 72-2 审点①③：不适用的臂必须出 n_a，不许出红）。
        # 字段名照 D 的最小公共 check schema（裁定 78.2）：id / ok / status / required / observed / red_when。
        status = "N_A" if not applies_when else ("PASS" if ok else ("RED" if blocking else "WARN"))
        rec = {"id": tid, "name": name, "ok": bool(ok), "status": status,
               "required": required, "red_when": required, "observed": observed,
               "authority": authority, "note": note, "applies_when": bool(applies_when),
               "blocking": bool(blocking),
               # `blocking_reason` 可由调用方**显式给**（裁定 93.1 起需要）：默认文案说的是
               # "held-out 牙的极性"，而 93.1 转 WARN 的两颗牙（`Tb`/`Tr3`）转的理由是
               # "阈值未经定标不得阻塞"，**不是**极性 ⇒ 沿用默认文案会在产物里写一句假话
               # （裁定 84.5 `top_level_aggregate_must_declare_semantics` 的同族要求：
               # 自报语义必须是**当前**语义）。
               "blocking_reason": (blocking_reason if blocking_reason is not None else
                                   ("主线/stress ⇒ held-out 牙也 blocking" if blocking else
                                    "诊断档的 held-out 牙降为 warning：拿"
                                    "非部署分布的帧判红 = 极性错（同裁定 51① 对"
                                    "ctrlrange 覆盖率的处置）"))}
        if extra:
            rec.update(extra)   # 只**追加**字段：上面 6 个公共字段不可被覆盖（G6 的最小 schema 不受影响）
            assert not (set(extra) & SCHEMA_REQUIRED_KEYS), f"extra 不得覆盖公共字段：{sorted(extra)}"
        teeth.append(rec)
        if applies_when and not ok:
            msg = f"{tid} {name}: required={required} observed={observed}"
            (red if blocking else warnings).append(msg)

    # (S) stats 数组**显式存在**：`normalize_processor.py:305-307` 在 stats 缺失时静默走 IDENTITY，
    # 所以"没报错"不等于"有 stats"（A2 实测 pre/post_*_stats_present=False）。这里直接查数组本身。
    need_keys = (("q01", "q99") if case == CASE_QUANTILES_FLOOR else ("center", "gain"))
    missing = [k for k in need_keys if k not in stats or np.asarray(stats[k]).size == 0]
    arrs = {k: np.asarray(stats[k], dtype=np.float64) for k in need_keys if k not in missing}
    nonfinite = [k for k, v in arrs.items() if not bool(np.all(np.isfinite(v)))]
    if case == CASE_QUANTILES_FLOOR and not missing and not nonfinite:
        bad_order = [int(i) for i in np.nonzero(arrs["q99"] <= arrs["q01"])[0]]
    elif not missing and not nonfinite:
        bad_order = [int(i) for i in np.nonzero(arrs["gain"] <= 0)[0]]
    else:
        bad_order = []
    tooth("Ts_stats_arrays_present",
          f"stats 数组显式存在且合法（{case} 需要 {list(need_keys)}）",
          not missing and not nonfinite and not bad_order,
          f"missing=[] nonfinite=[] 且 " + ("q99 > q01（逐维）" if case == CASE_QUANTILES_FLOOR else "gain > 0（逐维）"),
          f"missing={missing} nonfinite={nonfinite} bad_order_dims={bad_order}",
          "裁定 78.2 F7 / §12-6②：不得依赖 `normalize_processor.py:305-307` 的静默 IDENTITY 默认",
          note="清空 stats ⇒ 本牙必须红（变异体 `clear_stats`）；本牙恒 blocking")
    if missing or nonfinite:
        # 结构性缺失：后面几把牙要在这些数组上做算术 ⇒ 继续跑只会抛 numpy 广播错，
        # 让"红的理由"变成 traceback。这里提前抛，消息仍点名牙 id 与缺哪个键。
        raise NormContractViolation(
            f"Ts_stats_arrays_present stats 数组缺失/非有限: required={list(need_keys)} 全部存在且有限 "
            f"observed=missing={missing} nonfinite={nonfinite}", payload={"teeth": teeth, "red": red,
            "early_raise": "Ts_stats_arrays_present", "verdict": "RED"})

    # (a) features 非空
    tooth("Ta_features_non_empty", "features 非空", len(features) > 0,
          "len(features) > 0", f"len(features)={len(features)}",
          "裁定 51①(a)；A2 实测 normalizer_processor.config.features={}")

    # (R2) stats 源分级
    src_ok = (source in MAINLINE_ALLOWED_SOURCES) if mainline else True
    tooth("Tr2_stats_source_allowed", f"stats 源允许用于主线（source={source}）", src_ok,
          f"mainline={mainline} ⇒ source ∈ {MAINLINE_ALLOWED_SOURCES}", f"source={source}",
          "裁定 43.4 / 52 / 61 / 69（ABC-130k/YAM 禁用；env 版仅诊断）")

    # (P4/P5) stats 溯源标签 + BC 准入硬闸（裁定 85.4-3）
    prov = normalize_provenance(stats_provenance)
    consumer_known = (consumer is None) or (consumer in KNOWN_CONSUMERS)
    tooth("Tp4_stats_provenance_declared",
          f"stats_provenance 已显式声明且属于已知集合（observed={prov}）",
          (prov in KNOWN_STATS_PROVENANCES) and consumer_known,
          f"stats_provenance ∈ {list(KNOWN_STATS_PROVENANCES)}"
          + (f" 且 consumer ∈ {list(KNOWN_CONSUMERS)}" if consumer is not None else ""),
          f"stats_provenance={prov} consumer={consumer}",
          "裁定 85.4-2（产物必须写明数据集身份）/ 85.4-3（同源硬闸的前提是标签存在）",
          note=("缺标签 ⇒ 本牙红（`undeclared` 不在已知集合里）。这是**结构性存在/缺失**判定，"
                "故允许纯布尔（红线 `criterion_must_have_magnitude_floor` 的例外条款）。"
                "变异体：把 `stats_provenance` 抹掉 ⇒ 必须红。"))
    if prov not in KNOWN_STATS_PROVENANCES or not consumer_known:
        # 标签缺失/非法时，下游的 BC 准入判定没有输入 ⇒ 继续跑只会得到"假绿"或 traceback。
        # 与 `Ts_stats_arrays_present` 同族处置：提前抛，消息点名牙 id 与实到值。
        raise NormContractViolation(
            f"Tp4_stats_provenance_declared stats 溯源标签缺失/非法: "
            f"required=stats_provenance ∈ {list(KNOWN_STATS_PROVENANCES)} observed={prov}"
            + ("" if consumer_known else f"；consumer 非法 observed={consumer}"),
            payload={"teeth": teeth, "red": red, "early_raise": "Tp4_stats_provenance_declared",
                     "verdict": "RED"})
    adm = bc_admission(prov)
    tooth("Tp5_bc_admission_requires_formal40_bc_source",
          f"BC 准入：consumer={consumer} ⇒ stats_provenance 必须 = {STATS_PROVENANCE_FORMAL40_BC}",
          adm["admissible_for_bc"],
          f"stats_provenance ∈ {list(BC_ADMISSIBLE_PROVENANCES)}",
          f"stats_provenance={prov} consumer={consumer} admissible_for_bc={adm['admissible_for_bc']}",
          "裁定 85.4-3【同源硬闸】：pilot 10 集与 formal 40 集不是同一批数据；"
          "拿 pilot 的 q01–q99 归一化 formal 的训练数据 = 裁定 52/69 要挡的 stats 与 BC 数据不同源",
          blocking=True, applies_when=(consumer == CONSUMER_BC),
          note=("`applies_when = consumer == 'bc'`：通路验证档（`pilot10_path_check`）与诊断档"
                "不是 BC 输入 ⇒ 出 `N_A` 而不是红（裁定 72-2 审点①③：不适用的臂必须出 n_a）。"
                "牙：喂 pilot10 的 stats 给 BC 配置（`consumer='bc'`）⇒ 必须红。"))

    # (P6) 裁定 93.4（E2）：BC 准入必须 **AND** 闸 verdict。
    # `adm` 保持标签语义不变（既有消费方 `pred_G40` 等按它判）；闸证据走 `adm_gate` 的独立字段。
    adm_gate = bc_admission(prov, gate_verdict=gate_verdict, gate_run_dir=gate_run_dir,
                            gate_verdict_sha256_12=gate_verdict_sha256_12,
                            gate_verdict_class1=gate_verdict_class1)
    tooth("Tbcad_admission_requires_green_gate",
          (f"BC 准入必须 AND 闸 verdict_class1：admissible_for_bc=true ⇒ gate_verdict_class1 必须 = "
           f"{GATE_VERDICT_PASS}"),
          (not adm_gate["admissible_for_bc"]) or (adm_gate["gate_verdict_class1_green"] is True),
          (f"admissible_for_bc=false（本牙不适用）或 gate_verdict_class1 == {GATE_VERDICT_PASS}"
           f"（缺 class-1 闸证据 = `not_measured` ⇒ 按 != PASS 处理，不静默当绿；"
           f"顶层 gate_verdict 只登记、不参与本牙的 ok —— 裁定 97.3-3）"),
          (f"admissible_for_bc={adm_gate['admissible_for_bc']} "
           f"gate_verdict={adm_gate['gate_verdict']} "
           f"gate_verdict_measurement_status={adm_gate['gate_verdict_measurement_status']} "
           f"gate_verdict_green={adm_gate['gate_verdict_green']} "
           f"gate_verdict_class1={adm_gate['gate_verdict_class1']} "
           f"gate_verdict_class1_measurement_status="
           f"{adm_gate['gate_verdict_class1_measurement_status']} "
           f"gate_verdict_class1_green={adm_gate['gate_verdict_class1_green']} "
           f"gate_run_dir={adm_gate['gate_run_dir']} "
           f"gate_verdict_sha256_12={adm_gate['gate_verdict_sha256_12']}"),
          "裁定 93.4（E2）：`bc_admission()` 修前只看 `prov in BC_ADMISSIBLE_PROVENANCES`"
          "（纯标签派生、对数据质量盲）；本轮**实测到过**「`admissible_for_bc=true` 而同批 "
          "matrix 顶层 `verdict=RED`」这个分叉。裁定 97.3-3 把 AND 的对象收窄到 "
          "`verdict_class1`：修前吃顶层 `verdict` ⇒ 一颗 Ⅲ 类记账红（`G20_write_scope`）"
          "或 Ⅱ 类台账红（`G24`/`G25`）就能把 BC 挡死，而它们一个字节都不碰训练数据",
          blocking=True, applies_when=(consumer == CONSUMER_BC),
          extra={"bc_admission_with_gate": adm_gate},
          note=("变异体两向：喂一个 `verdict_class1=RED` 的 run 目录（或**不给** class-1 证据 ⇒ "
                "`not_measured`）⇒ 必须红；喂 class-1 绿的权威跑 ⇒ 必须绿。"
                "**第三向（裁定 97.3-3 的新语义，必须被证明）**：顶层 `verdict=RED` 而 "
                "`verdict_class1=PASS` ⇒ 本牙必须 **PASS**（Ⅱ/Ⅲ 类的 run 级元牙红不再单独禁 BC；"
                "裁定 97.5：任何线不得再拿顶层 RED 当停训理由）。"
                "`applies_when = consumer == 'bc'` 与 `Tp5` 同口径（非 BC 消费方出 `N_A`，"
                "裁定 72-2）。消费方义务（A2 侧 T-A2-7）：**不得只读** `admissible_for_bc`，"
                "必须 AND `gate_verdict_class1_green` 并**自己复算** `gate_verdict_sha256_12` 对账，"
                "不一致 ⇒ `LearnerRefused`。"))

    # 下限是否真的存在（R1）
    floors = np.asarray(stats.get("floor", np.zeros(frames.shape[1])), dtype=np.float64)
    nc = near_constant_dims(stats, rel_tol=th.near_constant_rel_tol)
    unprotected = [d for d in nc if not (floors[d] > 0)]
    tooth("Tr1_near_constant_has_floor", f"近常量维都有下限保护（近常量维={nc}）", not unprotected,
          "unprotected=[]", f"unprotected={unprotected}",
          "裁定 49.1（近常量维无下限保护必须红）",
          note=("近常量维判据读 `denom_raw`（原始分位距）/ `physical_range` ≤ "
                f"{th.near_constant_rel_tol}；**不读** widen 后的 `span_q99_q01`，否则本牙恒真"
                "（23:4x 实测缺陷，已修，见 `near_constant_dims` 文档串）。"))

    # (R1b) 裁定 93.2 补丁①：**有效分母严格 > 0**（绝对硬红、全臂、无定标空间）。
    # 为什么需要（失效形态是实测到的，不是理论）：ACT 线的 `(x - mean) / (std + 1e-6)` 在
    # `std = 0` 的维上分母 = 1e-6 ⇒ 归一化值冲到 **20402** 量级（本仓 QUANTILES 归一化的
    # `normalize_processor.py:371-374` 有同形的 `np.where(denom == 0, eps, denom)` 兜底，
    # `eps = LEROBOT_EPS = 1e-8` ⇒ 更猛）。**eps 兜底不是保护，它是把"这一维没有分辨率"
    # 这个事实翻译成一个巨大的假信号喂给模型。** 所以本牙判的是"兜底路径**从未被走到**"，
    # 而不是"运行时拿到的分母非零"（后者被 eps 兜底做成恒真 = 裁定 27.1 的恒真闸）。
    # 三个判据一起构成"严格 > 0"：① 实际参与归一化的分母逐维 > 0 且有限；② **烘下限前**的
    # 原始分母 `denom_raw` 逐维 > 0（= 不依赖 eps 兜底）；③ 近常量维 `floor_d > 0`
    # （与 `Tr1` 重合是**故意的**：`Tr1` 保持 `blocking=True` 不跟着降级，两颗牙从两个方向
    # 咬同一个除零族，任何一颗被单独拔掉另一颗仍在）。
    if case == CASE_QUANTILES_FLOOR:
        denom_used = (np.asarray(stats["q99"], dtype=np.float64)
                      - np.asarray(stats["q01"], dtype=np.float64))
        denom_kind = "q99 - q01（下限已烘入；对应 normalize_processor.py:369）"
    else:
        denom_used = 2.0 / np.asarray(stats["gain"], dtype=np.float64)
        denom_kind = "2 / gain（IDENTITY 显式缩放；gain → ∞ 等价于分母 → 0）"
    denom_raw_z = np.asarray(stats.get("denom_raw", denom_used), dtype=np.float64)
    z_used_bad = sorted(int(i) for i in np.nonzero(~np.isfinite(denom_used) | ~(denom_used > 0))[0])
    z_raw_bad = sorted(int(i) for i in np.nonzero(~np.isfinite(denom_raw_z) | ~(denom_raw_z > 0))[0])
    z_floor_bad = sorted(int(d) for d in nc if not (floors[d] > 0))
    z_finite = bool(np.all(np.isfinite(denom_used)) and np.all(np.isfinite(denom_raw_z)))
    tooth("Tz_denom_strictly_positive",
          "每维**有效分母严格 > 0**（永不依赖 eps 兜底）且近常量维 `floor_d > 0`",
          (not z_used_bad) and (not z_raw_bad) and (not z_floor_bad),
          (f"denom_used_d > 0 且有限（逐维，denom_used = {denom_kind}）；denom_raw_d > 0 且有限；"
           f"近常量维 floor_d > 0。**无定标空间**：0 就是 0"),
          (f"denom_used≤0/非有限维={z_used_bad} denom_raw≤0/非有限维={z_raw_bad}（= 会走 "
           f"eps={LEROBOT_EPS} 兜底的维）近常量维 floor≤0={z_floor_bad} "
           f"denom_used_min={(None if not z_finite else float(np.min(denom_used)))}"),
          "裁定 93.2 补丁①（绝对硬红、全臂）；失效形态 = ACT 线 `(x-mean)/(std+1e-6)` 除零族；"
          "`normalize_processor.py:371-374` 的 eps 兜底",
          blocking=True, applies_when=True,
          extra={"denom_kind": denom_kind,
                 "denom_used_min": (None if not z_finite else float(np.min(denom_used))),
                 "denom_used_per_dim": (None if not z_finite else [float(x) for x in denom_used]),
                 "denom_raw_min": (None if not z_finite else float(np.min(denom_raw_z))),
                 "dims_relying_on_eps_fallback": z_raw_bad,
                 "eps_fallback_value": LEROBOT_EPS,
                 "near_constant_dims_floor_nonpositive": z_floor_bad},
          note=("变异体两向：构造一维 `q99 == q01` 且 `floor = 0` ⇒ 必须红；真实 formal-40 ⇒ 必须绿。"
                "**本牙与 `Ts_stats_arrays_present` 的分工**：`Ts` 判「落盘的 stats 数组形状合法」"
                "（`q99 > q01`），本牙判「归一化实际用的分母 + 下限」（含 IDENTITY 的 `2/gain`、"
                "含 `denom_raw` 的 eps 兜底路径、含近常量维 floor）⇒ 两者判据面不同，"
                "`Ts` 绿不蕴含本牙绿。与 `Tr1` 的重合是**故意冗余**（见上）。"))

    # (R3) 下限**实质性**：近常量维的下限值本身必须 >= `floor_materiality_fraction × 物理行程`。
    # 为什么需要（实测，不是理论）：`Tr1` 只问"有没有下限"（`floors[d] > 0`），而 F2 族的下限
    # = `coef × noise_MAD`，在真正不动的维上 MAD = 1.881e-07 ⇒ 下限 = 3.76e-07 > 0 ⇒ **Tr1 绿**，
    # 但这个下限比 0.02 × 物理行程小 5 个数量级，**放大倍数几乎没有约束** ⇒ 绿是假绿。
    # `applies_when = mainline`：诊断档（env/YAM）不是部署表示，对它判红 = 极性错（裁定 72-2 审点①），
    # 所以诊断臂出 `N_A` + 理由，主线臂才 blocking。
    pr_arr = np.asarray(physical_range, dtype=np.float64)
    pr_safe = np.where(pr_arr > 0, pr_arr, 1.0)
    immaterial = [d for d in nc
                  if floors[d] < th.floor_materiality_fraction * pr_safe[d]]
    tooth("Tr3_near_constant_floor_material",
          f"近常量维的下限**实质有效**（≥ {th.floor_materiality_fraction} × 物理行程）",
          not immaterial,
          (f"近常量维（{len(nc)} 个）的 floor_d ≥ {th.floor_materiality_fraction} × physical_range_d"
           f"（阈值状态 {th.provenance['floor_materiality_fraction']}）"),
          (f"不足维={immaterial}" + ("" if not immaterial else
           "（实测例：hold 相 F2@2.0 的 floor=3.76e-07，而 0.02×行程 ≈ 1e-2 量级）")),
          "裁定 49.1（近常量维无下限保护必须红）的**实质性**补强；C2 提议待 S1 定标",
          # 裁定 **93.1-1**（E4 = 甲）：`blocking` 由 `bool(mainline)` 改为 **`False`**。
          # 机制在 `tooth()` 的 status 分支（`"RED" if blocking else "WARN"`）⇒ 红自动变 WARN。
          # **断言文本 / `applies_when` / `red_when` 一字未改**（D 亲核要求）；被改的只有
          # "一个状态为 `registered_measurement_not_a_judgment` 的下限能否阻塞主线"。
          # 换上去的硬红 = `Tz_denom_strictly_positive` + `Tres_per_dim_resolution_floor`（裁定 93.2）。
          blocking=False, applies_when=bool(mainline),
          blocking_reason=("裁定 93.1-1：本牙的阈值 `floor_materiality_fraction` 状态 = "
                           "`registered_measurement_not_a_judgment`（从未被定标）⇒ 不得作为 "
                           "blocking 判据（红线 `redline_provenance_discipline`：只有声明值支撑的"
                           "一律 `declared_only`、不得 blocking）。**判据未放宽**，只改阻塞性；"
                           "登记义务由裁定 93.1-3 的不缩水牙承担。"),
          note=("非主线臂 ⇒ `status=N_A`（不适用不出红，裁定 72-2）；本牙的变异体在 "
                "`scripts/c2_gate_norm_contract.py` 里以 `mainline=True + F2 下限` 构造，"
                "**裁定 93.1-1 之后必须是 `WARN`（修前是 `RED`）**，否则本牙恒真。"
                "近常量维**必须有下限**这件事仍由 `Tr1`（`blocking=True`，裁定 93.2 明令不降级）"
                "与 `Tz`（近常量维 `floor_d > 0`，绝对硬红）两颗牙守着。"))

    rep = dim_report(eval_x, stats, case=case, physical_range=physical_range)
    per_dim = rep["per_dim"]

    # ---- 裁定 94.3 的**两个登记字段**（按裁定 95.1-1 降级为 Ⅱ 类「登记不阻塞」）----
    # WHY 只有两个字段、没有牙：94.3 原本要一颗 blocking 牙 + 双向变异体，但那属于
    # 「实验解释风险」（用户分诊表 Ⅱ 类）⇒ 裁定 95.1-1 把它从 T-C2-8 的 P0 批次里拿出来，
    # 牙与变异体**推迟到 S5 前**，本轮只落读数（逐维数据本来就有 ⇒ 成本近零）。
    # WHY 必须落：held-out 逐维占用实测 [3,97,106,2,38,3,35,4,111,108,5,46,5,36] ⇒ 正确性族
    # （`Td2`/`Te1`/`Te2`/`Tsat`/`Tcov`/`Tesc`，对象是 held-out 帧）在 6 个维上几乎无从触发
    # = 缺陷类 ⑲（报了绿、而绿来自覆盖不全）。不回退口径（94.5）⇒ 隐性盲点必须变成显性登记。
    # 纪律：**盲点维必须由逐维实测算出，不许硬编码 6**（阈值复用已定标的 8，不新造数）。
    _heldout_scope = (eval_scope == EVAL_SCOPE_HELD_OUT)
    heldout_bins_per_dim = ([int(p["n_bins_occupied"]) for p in per_dim] if _heldout_scope else None)
    correctness_blind = (sorted(int(p["dim"]) for p in per_dim
                                if p["n_bins_occupied"] < th.min_bins_occupied_non_near_constant)
                         if _heldout_scope else None)
    blindness_status = "measured" if _heldout_scope else "not_measured"

    # (b) 下限生效 ⇒ 每维合法 bin 占用数达标
    low_bins = [p["dim"] for p in per_dim if p["n_bins_occupied"] < th.min_bins_occupied]
    tooth("Tb_scale_floor_effective", f"每维合法 bin 占用 ≥ {th.min_bins_occupied}", not low_bins,
          f"min bins/dim ≥ {th.min_bins_occupied}（阈值状态 {th.provenance['min_bins_occupied']}）",
          f"不足维={low_bins}", "裁定 51①(b)；bin 定义 processor_pi05.py:77",
          # 裁定 **93.1-1**（E4 = 甲）：本牙修前**没有** `blocking=` 实参 ⇒ 取 `tooth()` 的默认
          # `True`（D 亲核 `d_verify_external_analysis.json` 的 `A4_tb_has_no_blocking_kwarg`
          # = CONFIRMED；D §93.0 原文写成"`blocking=bool(mainline)`"对这一行不精确）。
          # ⇒ 这里是**新增** `blocking=False`，不是改一个已有的实参。
          blocking=False,
          blocking_reason=("裁定 93.1-1：本牙的阈值 `min_bins_occupied` 状态 = "
                           "`registered_measurement_not_a_judgment`（`proposed_pending_s1`，"
                           "从未被定标）⇒ 不得作为 blocking 判据。**判据/口径/阈值一个字都没改**；"
                           "分辨率的硬红改由裁定 93.2 的 `Tres_per_dim_resolution_floor` 承担"
                           "（逐维、**全量口径**、D 用 formal-40 实测定标）。"),
          note=("**id 沿用不改（D 文书已引用），但本牙咬的是反方向**：bin 占用不足 = 下限过大把分辨率"
                "压死。实测（23:4x）：`--floor-coef-scale 0` 关掉全部下限时 hold 相 "
                "`bins_occupied_median` 12.0 → 13.5（**升高**）、`abs_max` 0.993 → 0.992 ⇒ 关下限"
                "**不会**让本牙变红；「近常量维无下限保护必须红」由 `Tr1` 承担。"
                "**口径披露（裁定 93.1-3 登记不缩水）**：本牙判的是 `eval_x`（= held-out 口径，"
                "无 held-out 划分时 = build 口径）；held-out 只有全量的 ~5%（formal-40："
                "547/11035）⇒ 同一维在子集上落进个位数 bin、在全量上不会（实测 dim0 3→23、"
                "dim7 4→22）。**裁定 94.2 改判**：原文把这个形态称作「采样计数假象」，该理由已判 "
                "REFUTED（D 同型错误 #19 `consistent_with_is_not_established_by`）—— D 的 8 个同 n "
                "iid 子集给 dim0 ∈ [20,22] 而真 held-out = 3、`arithmetic_bound_binding=false` "
                "（最多只用到 23 个 bin，不到上限 547 的 4%）⇒ 低占用来自**留出集的形状**"
                "（只有两条轨迹弧线），不是 n 的算术后果。本牙保留 held-out 口径**只作登记**，"
                "不再阻塞；分辨率的硬红由 `Tres`（全量口径）承担。"))

    # (b2) 裁定 93.2 补丁②：**逐维分辨率下限**（口径 = 全量帧 `summary_all`；不用 median）。
    # 为什么口径是全量而不是 held-out —— **裁定 94.2 的三条独立实测理由**（原 93.2 写的
    # 「采样计数假象」已判 **REFUTED**，记 D 同型错误 #19；证伪源 = C2 四点单调性探针的第三臂
    # `runs/vla/c2_norm_contract_20260929/probe_monotonicity_20260930/verdict.json`，
    # D 用 `d_probe_heldout_shape.json` 独立复算后确认）：
    #   ① **留出集形状说**：held-out n=547 的 `bins_occupied_per_dim` =
    #      [3,97,106,2,38,3,35,4,111,108,5,46,5,36]，其中 dim0/5/7/12 **不是**近常量维，而同一批
    #      数据的全量口径是 23/24/87/22 ⇒ 低占用来自"留出集只有两条轨迹弧线"。D 的 8 个**同 n**
    #      iid 随机子集（种子 904011，每个都触及 40 集全部）给 dim0 ∈ [20,22]、dim5 ∈ [20,23]、
    #      dim7 ∈ [17,22]、dim12 ∈ [19,22]，而真 held-out = 3/3/4/5 ⇒ 6 个诊断维里 5 个低于 iid
    #      下界，且 `arithmetic_bound_binding = false`（最多只用到 23 个 bin，不到上限 547 的 4%）。
    #   ② **无判据力说**：两整集留出在 held-out 口径下**多数**会硬红 —— C2 实测的 10 对**全部含
    #      episode 0 或 2**（有偏样本）10/10 红；D 独立随机抽样 5/6 与 4/6 红 —— 而**通过的少数
    #      余量只有 1.0×**（D 实测 `min_non_near_constant = 8` = 阈值本身）⇒ 本牙在 held-out 口径下
    #      **要么红、要么恰好压线**，两种都没有判据力（裁定 27.1 同族）。
    #      ⚠ 措辞纪律（裁定 94.6-1）：**不得**写成"结构性恒红"—— 那个全称断言已被 D 的反例
    #      `[1,26]`（n=560、`non_near_constant_dims_below_8 = []`）推翻。
    #   ③ **极性说**：回退到 held-out 口径 = 把「**评测集的身份属性**」当成「**数据集的分辨率
    #      不足**」来判红 ⇒ 极性错（裁定 94.5：不回退，`Tres` 分口径分叉 hereby 关闭）。
    # 代价必须写在脸上（裁定 94.5）：正确性族在盲点维上是 `not_measured`（逐维读数见
    # `heldout_bins_occupied_per_dim` / `correctness_blind_dims`，裁定 94.3 的登记字段）；
    # 该债由 94.3 的显性登记（现在）+ 94.4 的选集升级（裁定 95.1-2 降 P2、排第 2 步之后）偿还。
    # **偿清之前，任何"归一化器已通过正确性验证"的表述都必须带"盲点维 not_measured"的限定**
    # （红线 `absence_of_measurement_is_not_measurement_of_absence`）。
    if all_frames is not None:
        res_x = np.atleast_2d(np.asarray(all_frames, dtype=np.float64))
        res_caliber = "all"
        res_caliber_note = "all（调用方显式给了 `all_frames` = build ∪ held-out 全量帧）"
    elif eval_frames is None:
        res_x = frames
        res_caliber = "build_equals_all"
        res_caliber_note = ("build（本臂无 held-out 划分 ⇒ 全量 = build，与生成器 "
                            "`summary_all` 的既有约定同源）")
    else:
        res_x = np.concatenate([frames, eval_x], axis=0)
        res_caliber = "all_derived_from_build_plus_heldout"
        res_caliber_note = ("调用方给了 `eval_frames` 但没给 `all_frames` ⇒ 本函数自己拼 "
                            "build ∪ held-out。**显式登记**这个派生口径，不装作调用方给过。")
    rep_all_c = dim_report(res_x, stats, case=case, physical_range=physical_range)
    bins_all = [int(p["n_bins_occupied"]) for p in rep_all_c["per_dim"]]
    nc_set = set(int(d) for d in nc)
    res_below_main = sorted(d for d in range(len(bins_all))
                            if d not in nc_set
                            and bins_all[d] < th.min_bins_occupied_non_near_constant)
    res_below_nc = sorted(d for d in nc_set
                          if bins_all[d] < th.min_bins_occupied_near_constant)
    res_warn_nc = sorted(d for d in nc_set
                         if bins_all[d] < th.warn_bins_occupied_near_constant)
    non_nc_bins = [bins_all[d] for d in range(len(bins_all)) if d not in nc_set]
    nc_bins = [bins_all[d] for d in sorted(nc_set)]
    tooth("Tres_per_dim_resolution_floor",
          (f"逐维分辨率下限（全量口径）：非近常量维 bins_occupied_d ≥ "
           f"{th.min_bins_occupied_non_near_constant}；近常量维 ≥ "
           f"{th.min_bins_occupied_near_constant}"),
          not (res_below_main or res_below_nc),
          (f"非近常量维 bins_occupied_d ≥ {th.min_bins_occupied_non_near_constant} 且近常量维 "
           f"bins_occupied_d ≥ {th.min_bins_occupied_near_constant}"
           f"（阈值状态 {th.provenance['min_bins_occupied_non_near_constant']}；口径 = "
           f"{res_caliber}；**逐维**判，永不 median/mean）"),
          (f"不足维（非近常量）={res_below_main} 不足维（近常量）={res_below_nc} "
           f"bins_occupied_per_dim={bins_all} 近常量维={sorted(nc_set)} "
           f"n_frames={int(rep_all_c['n_frames'])} "
           f"margin_min_non_near_constant="
           f"{(None if not non_nc_bins else round(min(non_nc_bins) / th.min_bins_occupied_non_near_constant, 4))} "
           f"margin_min_near_constant="
           f"{(None if not nc_bins else round(min(nc_bins) / th.min_bins_occupied_near_constant, 4))}"),
          "裁定 93.2 补丁②，**阈值**由 D 用 formal-40 全量口径实测定标（"
          "`runs/vla/d_ruling_round_20260930_1010/probe_resolution_calibration_inputs.json`；"
          "余量 非近常量维 2.75× / dim3 1.5× / dim10 2.5×）；**口径 = 全量**的理由按裁定 94.2 "
          "改判为三条独立实测：① 留出集形状说（D 的 8 个同 n iid 子集 dim0 ∈ [20,22] vs 真 "
          "held-out 3，`arithmetic_bound_binding=false`，`d_probe_heldout_shape.json`）；"
          "② 无判据力说（held-out 口径下 C2 有偏样本 10/10 红、D 随机抽样 5/6 与 4/6 红，"
          "通过者余量仅 1.0× ⇒ **不是「恒红」而是「无判据力」**，裁定 94.6-1）；"
          "③ 极性说（裁定 94.5 不回退、分口径分叉已关闭）。原「采样计数假象」判 REFUTED"
          "（D 同型错误 #19）；bin 定义 processor_pi05.py:77",
          blocking=True, applies_when=True,
          extra={"resolution_caliber": res_caliber,
                 "resolution_caliber_note": res_caliber_note,
                 "n_frames_resolution_caliber": int(rep_all_c["n_frames"]),
                 "bins_occupied_per_dim_resolution_caliber": bins_all,
                 "near_constant_dims_used": sorted(nc_set),
                 "dims_below_non_near_constant_floor": res_below_main,
                 "dims_below_near_constant_floor": res_below_nc,
                 "dims_near_constant_below_warn_threshold": res_warn_nc,
                 "threshold_non_near_constant": th.min_bins_occupied_non_near_constant,
                 "threshold_near_constant": th.min_bins_occupied_near_constant,
                 "threshold_warn_near_constant": th.warn_bins_occupied_near_constant,
                 "threshold_status": th.provenance["min_bins_occupied_non_near_constant"],
                 "margin_min_non_near_constant": (None if not non_nc_bins else
                                                  min(non_nc_bins) / th.min_bins_occupied_non_near_constant),
                 "margin_min_near_constant": (None if not nc_bins else
                                              min(nc_bins) / th.min_bins_occupied_near_constant),
                 # 裁定 94.9-5（缺陷类 ⑳ `preregistered_condition_without_a_consumer`）：
                 # 预登记的可推翻条件必须写明**谁在什么时刻核它**，否则等于没写。
                 "preregistered_falsifiable_condition": {
                     "condition": "全量口径下任一非近常量维 bins_occupied_d < 8",
                     "action_if_true": ("C2 不得改阈值放行、不得升 P0，必须停手回报 D"
                                        "（裁定 93.2 预登记）"),
                     "checked_by": "C2（`harness/norm_contract.py` 的本次 `evaluate_contract` 调用）",
                     "checked_when": datetime.now().astimezone().isoformat(timespec="seconds"),
                     "result": ("TRIGGERED_stop_and_report_to_d" if res_below_main
                                else "not_triggered"),
                     "dims_below_non_near_constant_floor": res_below_main,
                     "checked_on_caliber": res_caliber},
                 # 裁定 94.3 的两个登记字段（Ⅱ 类「登记不阻塞」，牙推迟到 S5 前 = 裁定 95.1-1）
                 "heldout_bins_occupied_per_dim": heldout_bins_per_dim,
                 "correctness_blind_dims": correctness_blind,
                 "correctness_blind_dims_status": blindness_status,
                 "correctness_blind_dims_authority": (
                     "裁定 94.3（逐维登记，永不 median/mean；盲点维由实测算出、不硬编码）+ "
                     "裁定 95.1-1（牙 `Theldout_per_dim_blindness_is_registered` 与双向变异体"
                     "**推迟到 S5 前**，本轮只落两个字段）"),
                 "correctness_blind_dims_note": (
                     "在偿清之前，任何「归一化器已通过正确性验证」的表述都必须带「盲点维 "
                     "`not_measured`」的限定（裁定 94.5 的代价，红线 "
                     "`absence_of_measurement_is_not_measurement_of_absence`）"
                     if correctness_blind else
                     "本口径下实测无盲点维（占用 < 8 的维为空）")},
          note=("变异体两向：把某一**非近常量维**的 bin 占用压到 7 ⇒ 必须红；真实全量数据 ⇒ 必须绿。"
                "近常量维 `< 8` 不由本牙判红，由 `Tresw_near_constant_low_resolution_is_warned` "
                "出 WARN 登记（= 裁定 90.4-3 的 P1 债；用户已批速度优先 ⇒ 不进 P0）。"
                "**可推翻条件（裁定 93.2 预登记）**：全量口径下任一非近常量维 `< 8` ⇒ "
                "C2 不得改阈值放行，必须停手回报 D。该条件的 `checked_by`/`checked_when`/`result` "
                "随本牙 `extra.preregistered_falsifiable_condition` 逐次落盘（裁定 94.9-5）。"))
    tooth("Tresw_near_constant_low_resolution_is_warned",
          (f"近常量维 bins_occupied_d < {th.warn_bins_occupied_near_constant} ⇒ WARN 登记"
           f"（裁定 90.4-3 的 P1 分辨率债）"),
          not res_warn_nc,
          f"近常量维 bins_occupied_d ≥ {th.warn_bins_occupied_near_constant}",
          (f"低于登记阈值的近常量维={res_warn_nc}"
           + ("" if not res_warn_nc else
              f"（bins={[bins_all[d] for d in res_warn_nc]}；口径 {res_caliber}）")),
          "裁定 93.2（近常量维 `< 8` ⇒ WARN 登记）+ 裁定 90.4-3（P1，用户已批速度优先）",
          blocking=False, applies_when=bool(nc_set),
          blocking_reason=("裁定 93.2：近常量维的分辨率债是 **P1 登记项**（用户已批速度优先 ⇒ "
                           "不进 P0）⇒ 非 blocking。硬红只落在 `< "
                           f"{th.min_bins_occupied_near_constant}`（= 该维不携带任何可分辨信息）。"),
          extra={"resolution_caliber": res_caliber,
                 "dims_near_constant_below_warn_threshold": res_warn_nc,
                 "p1_debt_id": "resolution_floor_uncalibrated（裁定 90.4-3 / 93.3）"},
          note=("与 `Tovr_out_of_interval_overflow_is_warned` 同族形态（非 blocking 的**量级**登记）。"
                "无近常量维 ⇒ `status=N_A`（不适用不出 WARN，裁定 72-2）。"
                "变异体：把某近常量维的 bin 占用压到 1 ⇒ 本牙仍 WARN 而 `Tres` 转红（两颗牙的"
                "分工可分辨）；压到 7 ⇒ 只有本牙 WARN。"))

    # (c) 起态覆盖闸
    if case == CASE_QUANTILES_FLOOR:
        sn = reference_normalize(start_pose, "quantiles", {"q01": stats["q01"], "q99": stats["q99"]})[0]
    else:
        sn = ((start_pose - stats["center"]) * stats["gain"])[0]
    raw_oob = [int(i) for i in np.nonzero(np.abs(start_pose[0]) > 1.0)[0]]
    oob = [int(i) for i in np.nonzero((sn >= 1.0) | (sn < -1.0))[0]]
    tooth("Tc_start_pose_coverage", "起态归一化后越界维数 = 0", len(oob) <= th.start_pose_oob_dims_cap,
          f"≤ {th.start_pose_oob_dims_cap}（{th.provenance['start_pose_oob_dims_cap']}）",
          f"越界维={oob}（原始越界维={raw_oob}，max|state|={float(np.abs(start_pose[0]).max()):.6g}）",
          "裁定 51①(c)；A2 实测 hold_action_14d")

    hard = bool(mainline or force_blocking)   # 提前定义：Tsat 与 Td2/Te2 共用同一 blocking 口径

    # (e) 饱和维数 = 0（裁定 §12-6② 第三把牙）。诊断档降 warning（拿非部署分布判红 = 极性错）。
    sat = rep["saturation"]
    sat_dims = sorted(set(int(d) for d in sat.get("dims_with_high_sat", [])) |
                      set(int(d) for d in sat.get("dims_with_low_sat", [])))
    tooth("Tsat_saturation_dims_zero", "归一化后饱和维数 = 0（|x|>=1 即算饱和）",
          len(sat_dims) == 0, "n_dims_saturated == 0",
          (f"n_dims_saturated={len(sat_dims)} dims={sat_dims} "
           f"(above_1={sat.get('n_values_above_1')} below_-1={sat.get('n_values_below_-1')} "
           f"abs_max={sat.get('abs_max_normalized')})"),
          "§12-6②；饱和 = `processor_pi05.py:77` 的 digitize 落到边界/非法 bin",
          blocking=hard,
          note=("blocking 口径与 Td2/Te2 一致（主线/stress 才 blocking）；"
                "`n_values_above_1` 是**值计数**，本牙判的是**维计数**"))

    # (e2) 声明物理区间的**越界测量** + 三把判据牙 —— 裁定 **90.4-1**（撤回裁定 87.3-2 条件 c 的极性）。
    #
    # 修前这里是**一把**牙 `Tiv_no_state_outside_declared_interval`：越出声明区间就判红。
    # D 在裁定 90.2 承认那是它的第 15 号同型错误（把**软边界**当硬界）：`jnt_range` 是软边界这件事
    # 在裁定 87 落笔之前就已写在三处（`decisions_20260929.md:1930`、`b2_export_states_14d.py:422`、
    # `work/project_parameters.json:638`），而 C2 的勘误件自己就写着
    # `physical_range_effective_rule = max(jnt_travel, observed_travel)（jnt_range 是软边界）`。
    # 裁定 90.4-1 的新口径（**本节就是它的实现**）：
    #   · 越界量 = **必落盘的测量**，永不因"越界"本身出红（`Tiv_out_of_declared_interval_is_measured`）；
    #   · 硬红移到有物理含义的量：`headroom_consumption_max ≥ 1.0` = 窗口逃逸（`Tesc`）；
    #   · 下侧/上侧分治（`processor_pi05.py:77` 的结构不对称：`x ≥ 1` ⇒ 合法顶 bin 255 优雅饱和，
    #     `x < -1` ⇒ **非法 bin -1** 静默拼进 prompt）⇒ 下侧越界 = 正确性缺陷 = 硬红（`Tlo`）；
    #     上侧越界 = 分辨率/饱和事实 = **warning + 量级**（`Tovr`，非 blocking）；
    #   · `Te1`/`Te2` 的 `illegal_bin(-1)` 保持绝对硬红（那才是 ① 真正要防的失效模式）。
    # 为什么仍不能靠 `Tsat` 代劳（修前的实测理由，改判后依然成立）：1 bin 头寸把 pilot-10 的三维越界量
    # 全吸收了（dim6 5.85e-4 / dim13 3.15e-4 / dim10 1.878e-2）⇒ `Tsat` 绿，而「1605 帧 = 58.45%
    # 超出声明区间」这个事实**仍然存在** ⇒ 测量必须独立落盘，否则就是"有余量上的平凡绿"（缺陷类 ⑯ 镜像）。
    conf_frames = frames if eval_frames is None else np.concatenate([frames, eval_x], axis=0)
    iv_conf = declared_interval_conformance(conf_frames, physical_interval)
    iv_applies = (physical_interval is not None
                  and coverage_target == COVERAGE_TARGET_DECLARED_INTERVAL)
    # 量级串：裁定 90.4-1 要求 warning 也**带量级**，且四把牙共用同一份实测（不许各算一份）。
    def _fmt(v, spec="%.6g"):
        """三态格式化：`None` ⇒ 字面 `null`（不许格式化成 0.00 —— 那是把"没测"写成"测到 0"）。"""
        return "null" if v is None else (spec % v)

    def _mx(key, spec="%.6g"):
        v = iv_conf.get(key)
        return "null" if not v else (spec % max(v))
    iv_mag = (f"n_frames={iv_conf.get('n_frames')} n_dims_out={iv_conf.get('n_dims_out')} "
              f"dims_out={iv_conf.get('dims_out')} dims_above={iv_conf.get('dims_above')} "
              f"dims_below={iv_conf.get('dims_below')}")
    if iv_conf.get("measurement_status") == "measured":
        iv_mag += (f" excess_above_max={_mx('excess_above')}"
                   f"（{_mx('excess_above_pct_of_travel', '%.4g')}% 行程） "
                   f"excess_below_max={_mx('excess_below')} "
                   f"n_frames_out_per_dim={iv_conf['n_frames_out_per_dim']} "
                   f"headroom_consumption_max={_fmt(iv_conf.get('headroom_consumption_max'), '%.4g')}"
                   f"（above={_fmt(iv_conf.get('headroom_consumption_max_above'), '%.4g')} "
                   f"below={_fmt(iv_conf.get('headroom_consumption_max_below'), '%.4g')}） "
                   f"window_escape={iv_conf['window_escape']} "
                   f"dims_window_escape={iv_conf['dims_window_escape']}")
    else:
        iv_mag += f" measurement_status={iv_conf.get('measurement_status')}（三态：没测 ≠ 测到没有）"
    iv_na_obs = (f"coverage_target={coverage_target} physical_interval_provided="
                 f"{physical_interval is not None} ⇒ 本组牙只判 ①（declared_interval）档；"
                 f"测量块仍照产（measurement_status={iv_conf.get('measurement_status')}）")
    iv_na_note = ("`build_only` 档的覆盖集**就是数据自己** ⇒ 对它断言声明区间相关的覆盖/越界判据"
                  "是另一件事（那时窗口会跟着数据涨）⇒ 出 N_A 而不是红（裁定 72-2 审点①③）。"
                  "越界**测量**不受影响：`declared_interval_conformance` 照算照落盘")

    def iv_tooth(tid, name, ok, required, observed, authority, blocking, note):
        if iv_applies:
            tooth(tid, name, ok, required, observed, authority, blocking=blocking, note=note)
        else:
            tooth(tid, name, True, "n_a", iv_na_obs, authority, blocking=blocking,
                  applies_when=False, note=f"{note}｜N_A 理由：{iv_na_note}")

    # (e2-1) 测量必须存在且完整 —— **本牙永不因越界量本身判红**（裁定 90.4-1 第一条）。
    iv_tooth("Tiv_out_of_declared_interval_is_measured",
             f"声明区间越界量**已被测量并落盘**（实测 {iv_conf.get('n_frames')} 帧）",
             bool(iv_conf.get("measurement_status") == "measured"
                  and iv_conf.get("measurement_complete") is True),
             ("measurement_status == 'measured' 且 measurement_complete == true"
              "（逐维字段齐、长度 == n_dims、全有限）；**越界量大小不进判据**"),
             (f"measurement_status={iv_conf.get('measurement_status')} "
              f"complete={iv_conf.get('measurement_complete')} "
              f"missing={iv_conf.get('measurement_missing_fields')} "
              f"bad_len={iv_conf.get('measurement_bad_length_fields')} "
              f"nonfinite={iv_conf.get('measurement_nonfinite_fields')}｜{iv_mag}"),
             ("裁定 90.4-1（越界量 = 必落盘的测量，永不因越界本身出红）+ 红线 "
              "`absence_of_measurement_is_not_measurement_of_absence`（裁定 88.3-1）"),
             blocking=True,
             note=("修前本牙 id 是 `Tiv_no_state_outside_declared_interval`、判据是 `n_dims_out == 0`；"
                   "裁定 90.4-1 撤回该极性后**id 必须换**（留着旧 id 就等于名字承诺一条不再判的约束 "
                   "⇒ 规则 `gate_name_must_match_gate_semantics` 的违例形态）。"
                   "变异体：① 让 `declared_interval_conformance` 返回 not_measured 或删逐维字段 ⇒ 本牙必须红；"
                   "② 把本牙改成恒真 ⇒ 元闸 `gate_name_must_match_gate_semantics` 必须抓到"
                   "（裁定 90.4-1 双向牙③），牙台账必须报 missed/extra/all_caught（裁定 85.5 口径）"))

    # (e2-2) 窗口逃逸 = 硬红（裁定 90.4-1：硬红移到有物理含义的量）。
    iv_tooth("Tesc_no_covered_window_escape",
             "状态不逃出被覆盖窗口（头寸消耗比 < 1.0）",
             (iv_conf.get("window_escape") is not True),
             (f"headroom_consumption_max < {WINDOW_ESCAPE_RATIO}（= 窗口逃逸的**定义**，"
              f"不是调参项；裁定 90.6-1 明令不得放宽）"),
             (f"headroom_consumption_max={_fmt(iv_conf.get('headroom_consumption_max'), '%.4g')} "
              f"dims_window_escape={iv_conf.get('dims_window_escape')}｜{iv_mag}"),
             "裁定 90.4-1（硬红移到 `headroom_consumption_max ≥ 1.0`）",
             blocking=True,
             note=("物理含义：越界量吃光该维头寸 ⇒ 归一化后必越 ±1 ⇒ 下侧会产生非法 bin -1。"
                   "变异体（裁定 90.4-1 双向牙①）：把 `headroom_bins` 调小、或注入一个更远的状态，"
                   "把消耗比推过 1.0 ⇒ 本牙必须红；处置不得是放宽 1.0，而是升 `headroom_bins` "
                   "或启用逐维覆盖并**新建 `representation_version`**（裁定 90.6-1）"))

    # (e2-3) 下侧**覆盖不足** = 正确性缺陷 = 硬红（裁定 90.4-1 的下侧/上侧分治）。
    # ⚠ 判据是"覆盖不足"而**不是**"越出声明区间"，这两个词是 D 在同一节里刻意分开用的
    # （下侧写『覆盖不足』、上侧写『越界』），且该节第一条明写「**永不**因『越界』本身出红」。
    # 若把下侧也做成"越界即红"，就是把裁定 90.4-1 刚撤回的极性在下侧原样装回去 ——
    # `jnt_range` 是软边界（裁定 90.2 #15），下侧小幅越出同样物理合法；本轮 formal-40 实测
    # `ex_below` 14 维**全 0**，所以这条改判在本批数据上不改变读数，但它决定了**下一个 regime**
    # （policy_rollout / rl_exploration，裁定 90.6-2 预期越界量 ≈ 头寸预算的 73×）会不会假红。
    conf_n = normalize_with_case(conf_frames, case, stats)
    lo_deficit = sorted(int(i) for i in np.nonzero(conf_n.min(axis=0) < -1.0)[0])
    lo_deficit_amount = np.maximum(-1.0 - conf_n.min(axis=0), 0.0)
    iv_tooth("Tlo_no_downside_coverage_deficit",
             "**下侧**无覆盖不足（没有状态归一化到 -1 以下）",
             not lo_deficit,
             ("逐维 min(norm(state)) ≥ -1（= 被覆盖窗口包住下侧）。"
              "下侧**越出声明区间但被头寸吸收** ⇒ 不判红，由 `Tovr` 出 warning"),
             (f"dims_downside_coverage_deficit={lo_deficit} "
              f"deficit_amount_normalized={[float('%.6g' % v) for v in lo_deficit_amount]} "
              f"norm_min_per_dim={[float('%.6g' % v) for v in conf_n.min(axis=0)]} "
              f"｜声明区间口径的下侧越界（**测量，不是本牙判据**）："
              f"dims={iv_conf.get('dims_downside_deficit')} excess_below_max={_mx('excess_below')} "
              f"headroom_consumption_max_below="
              f"{_fmt(iv_conf.get('headroom_consumption_max_below'), '%.4g')}｜{iv_mag}"),
             ("裁定 90.4-1（下侧覆盖不足 = 正确性缺陷 = 硬红）+ `processor_pi05.py:77` 的结构不对称"
              "（裁定 90.3 实测：`x < -1` ⇒ digitize 返回 0 ⇒ bin -1 非法 token 静默进 prompt；"
              "`x ≥ 1` ⇒ 255 是合法顶 bin ⇒ 上侧溢出被合法吸收）"),
             blocking=True,
             note=("**与 `Te1`/`Te2` 的关系（如实登记，不假装独立）**：本牙判的是**窗口层**"
                   "（min(norm) ≥ -1，对 QUANTILES 即 `min(state) ≥ q01`），那两把判的是**digitize 之后**"
                   "是否出现 bin -1 ⇒ 在 `processor_pi05.py:77` 现有实现下两者**同时红**。保留本牙的理由是"
                   "裁定 90.4-1 要求下侧/上侧分治**在牙上可见**，且窗口层判据不依赖 tokenizer 的离散化："
                   "若哪天上游改成钳位（clamp），`Te1`/`Te2` 会静默转绿而下侧覆盖不足的事实仍在。"
                   "变异体：注入一个把某维推到 `q01` 以下的状态 ⇒ 本牙必须红，而**上侧**同幅度的注入"
                   "只能让 `Tesc` 红、本牙必须绿 ⇒ 两把牙极性可分辨（不是同一把牙的两个名字）"))

    # (e2-4) 越出声明区间（**任一侧**）= 分辨率/饱和事实 = warning + 量级（**不得**升为 blocking）。
    iv_tooth("Tovr_out_of_interval_overflow_is_warned",
             "越出声明区间的量只登记为 warning（带量级、分侧），不判红",
             (iv_conf.get("upside_overflow") is not True
              and iv_conf.get("downside_deficit") is not True),
             ("任一侧越界 ⇒ status=WARN（blocking=false）；**永不**因越界量本身出 RED"
              "（裁定 90.4-1 第一条）。硬红只在 `Tesc`（窗口逃逸）与 `Tlo`（下侧覆盖不足）上"),
             (f"dims_upside_overflow={iv_conf.get('dims_upside_overflow')} "
              f"dims_downside_overflow={iv_conf.get('dims_downside_deficit')} "
              f"n_frames_above_per_dim={iv_conf.get('n_frames_above_per_dim')} "
              f"n_frames_below_per_dim={iv_conf.get('n_frames_below_per_dim')} "
              f"excess_above_pct_of_travel={iv_conf.get('excess_above_pct_of_travel')} "
              f"excess_below_pct_of_travel={iv_conf.get('excess_below_pct_of_travel')}｜{iv_mag}"),
             "裁定 90.4-1（上侧越界 = 分辨率/饱和事实 = 测量 + warning；第一条 = 永不因越界本身出红）",
             blocking=False,
             note=("裁定 90.3 的实测性质判定：formal-40 上 dim6 落进顶 bin 255 的 6609 帧物理跨度只有 "
                   "0.001098（119 段连续 run、最长 177 帧）⇒ 真·物理饱和平台，塌进一个 bin **语义正确**；"
                   "D 明令**禁止**用「再展宽」消除它（只会把求解器抖动放大成假信号喂给 BC）。"
                   "把本牙升为 blocking = 把裁定 90.4-1 撤回的极性又装回去 ⇒ 闸侧登记为变异体"))

    # (f) q01–q99（或 center±1/gain）对 ctrlrange 的覆盖率 —— 裁定 51.1 明确**只作 warning**：
    # 示范本来不会用满关节行程，把覆盖率不足判红 = 极性错（D 已撤掉 C2 原来的 0.95 红判据）。
    if physical_interval is None:
        tooth("Tw_ctrlrange_coverage", "stats 覆盖区间对 ctrlrange 的覆盖率（记录用）",
              True, "n_a", "physical_interval 未提供 ⇒ 无法计算覆盖率",
              "裁定 51.1（降为 warning + 记录实际覆盖率）", blocking=False, applies_when=False,
              note="不适用 ⇒ `status=N_A`，不出红（裁定 72-2 审点①③）")
    else:
        dlo, dhi = (np.asarray(physical_interval[0], dtype=np.float64),
                    np.asarray(physical_interval[1], dtype=np.float64))
        dw = np.where((dhi - dlo) > 0, dhi - dlo, np.nan)
        if case == CASE_QUANTILES_FLOOR:
            clo, chi = np.asarray(stats["q01"], dtype=np.float64), np.asarray(stats["q99"], dtype=np.float64)
        else:
            ctr = np.asarray(stats["center"], dtype=np.float64)
            gn = np.asarray(stats["gain"], dtype=np.float64)
            half = np.where(gn > 0, 1.0 / np.where(gn > 0, gn, 1.0), np.inf)
            clo, chi = ctr - half, ctr + half
        ov = np.maximum(0.0, np.minimum(chi, dhi) - np.maximum(clo, dlo))
        cov = ov / dw
        cov_ok = np.nan_to_num(cov, nan=0.0)
        low_cov = [int(i) for i in np.nonzero(cov_ok < th.ctrlrange_coverage_report_below)[0]]
        tooth("Tw_ctrlrange_coverage",
              f"stats 覆盖区间对 ctrlrange 的覆盖率（< {th.ctrlrange_coverage_report_below} 只记录，不判红）",
              True, "记录实际覆盖率；**不判红**（裁定 51.1：示范不会用满行程）",
              (f"coverage_min={float(np.nanmin(cov_ok)):.4f} coverage_median={float(np.nanmedian(cov_ok)):.4f} "
               f"dims_below={low_cov}"),
              "裁定 51.1（原「≥0.95 判红」已被 D 撤销为极性错）", blocking=False,
              note=("本牙**故意恒 ok=true**：它是记录位，不是判定位。若要它咬人，必须先由 D 改判据；"
                    "C2 不自行把 warning 升成 red"))

    # (g) ① 的**保证**本身（裁定 87.3-1）：声明区间的两端归一化后必须落在 [-1,1) 内。
    # 为什么必须有这把牙：① 的全部意义是"任何**物理合法**状态都不产生非法 bin"。这句话若不落到
    # 区间端点上量一次，就只是散文 —— 而端点正是最坏情况（区间内任何状态的归一化值都在两端点之间）。
    # 判据用**端点的归一化值 + digitize 出来的 bin id**两件事同时判：`-1 ≤ norm(lo)` 且 `norm(hi) < 1`
    # ⇒ bin ∈ [0,255]；只要有一端越过去，`processor_pi05.py:77` 就会给出 `-1`（x<-1）或把 x≥1
    # 压进 255（饱和），两者都是喂进 prompt 的垃圾表示。
    cov_applies = (physical_interval is not None
                   and coverage_target == COVERAGE_TARGET_DECLARED_INTERVAL)
    if not cov_applies:
        tooth("Tcov_declared_interval_covered",
              "声明物理区间的两端归一化后都在 [-1,1) 内（① 的保证）", True, "n_a",
              (f"coverage_target={coverage_target}（本牙只判 ① 档）"
               f" physical_interval_provided={physical_interval is not None}"),
              "裁定 87.3-1（①）", blocking=hard, applies_when=False,
              note=("`build_only` 档按构造只覆盖 build 帧 ⇒ 对声明区间端点断言覆盖 = 极性错"
                    "（裁定 72-2 审点①③：不适用出 N_A）。① 的保证**只**在 ① 档有意义"))
    else:
        clo = np.asarray(physical_interval[0], dtype=np.float64).reshape(1, -1)
        chi = np.asarray(physical_interval[1], dtype=np.float64).reshape(1, -1)
        nlo = normalize_with_case(clo, case, stats)[0]
        nhi = normalize_with_case(chi, case, stats)[0]
        bad_lo = [int(i) for i in np.nonzero(nlo < -1.0)[0]]
        bad_hi = [int(i) for i in np.nonzero(nhi >= 1.0)[0]]
        bins_lo = reference_digitize(nlo)
        bins_hi = reference_digitize(nhi)
        illegal = sorted(set(int(i) for i in np.nonzero(bins_lo < 0)[0]) |
                         set(int(i) for i in np.nonzero(bins_hi < 0)[0]) |
                         set(int(i) for i in np.nonzero(bins_hi > SAT_BIN_HIGH)[0]))
        tooth("Tcov_declared_interval_covered",
              "声明物理区间的两端归一化后都在 [-1,1) 内（① 的保证）",
              (not bad_lo) and (not bad_hi) and (not illegal),
              "逐维 -1 ≤ norm(declared_lo) 且 norm(declared_hi) < 1，且两端 digitize 出合法 bin",
              (f"norm(lo)_min={float(nlo.min()):.6g} norm(hi)_max={float(nhi.max()):.6g} "
               f"bad_lo_dims={bad_lo} bad_hi_dims={bad_hi} illegal_bin_dims={illegal} "
               f"bin(lo)_min={int(bins_lo.min())} bin(hi)_max={int(bins_hi.max())}"),
              "裁定 87.3-1（①）+ processor_pi05.py:77/:81-84（非法 bin 会静默进文本 prompt）",
              blocking=hard,
              note=("本牙是 ① 的**验收判据**：它绿 = 任何声明区间内的状态都不会产生非法 bin"
                    "（端点是最坏情况，区间内其余状态的归一化值都在两端之间）。"
                    "变异体：把覆盖集缩回 build-only（`coverage_must_cover` 忽略 target）⇒ 本牙必须红"))

    # (d) clip 比例上限 —— 分 in-distribution（永远 blocking）与 held-out（按档）
    rep_build = dim_report(frames, stats, case=case, physical_range=physical_range)
    worst_build = max(rep_build["per_dim"], key=lambda p: p["clip_ratio"])
    tooth("Td1_clip_build_frames", f"建 stats 的帧 clip 比例 ≤ {th.clip_ratio_cap}",
          worst_build["clip_ratio"] <= th.clip_ratio_cap,
          f"≤ {th.clip_ratio_cap}", f"最差维={worst_build['dim']} clip_ratio={worst_build['clip_ratio']:.6g}",
          "裁定 51①(d)；已 widen_to_cover ⇒ 本批帧不该被裁", blocking=True)
    worst = max(per_dim, key=lambda p: p["clip_ratio"])
    tooth("Td2_clip_heldout", f"held-out 帧每维 clip 比例 ≤ {th.clip_ratio_cap}",
          worst["clip_ratio"] <= th.clip_ratio_cap,
          f"≤ {th.clip_ratio_cap}（{th.provenance['clip_ratio_cap']}）",
          f"最差维={worst['dim']} clip_ratio={worst['clip_ratio']:.6g}（n_eval={int(eval_x.shape[0])}）",
          "裁定 51①(d)；阈值待 S1 真实数据定标", blocking=hard,
          extra={"eval_scope": eval_scope, "eval_scope_note": EVAL_SCOPE_NOTE[eval_scope]})

    # 附加：非法 bin（-1）不得出现 —— digitize 的静默失效路径，必须显式看
    illegal_build = [p["dim"] for p in rep_build["per_dim"] if p["illegal_bin_-1_present"]]
    tooth("Te1_no_illegal_bin_build", "建 stats 的帧无非法 bin -1", not illegal_build,
          "dims_with_bin_-1=[]", f"dims={illegal_build}",
          "processor_pi05.py:77 + :81-84（离散值被拼进文本 prompt）", blocking=True)
    illegal = [p["dim"] for p in per_dim if p["illegal_bin_-1_present"]]
    tooth("Te2_no_illegal_bin_heldout", "held-out 帧无非法 bin -1", not illegal,
          "dims_with_bin_-1=[]", f"dims={illegal}",
          "processor_pi05.py:77 + :81-84", blocking=hard,
          extra={"eval_scope": eval_scope, "eval_scope_note": EVAL_SCOPE_NOTE[eval_scope]})

    payload = {"case": case, "source": source, "mainline": mainline,
               "stats_provenance": prov, "consumer": consumer,
               "bc_admission": adm,
               # 裁定 93.4：标签口径与闸口径**分开落**（`adm` 保持标签语义，供既有消费方；
               # `adm_gate` 多四个字段）。压成一个布尔会让"标签错"与"闸红"无法区分。
               "bc_admission_with_gate": adm_gate,
               "gate_verdict": adm_gate["gate_verdict"],
               "gate_verdict_green": adm_gate["gate_verdict_green"],
               "gate_verdict_measurement_status": adm_gate["gate_verdict_measurement_status"],
               # 裁定 97.3-3：准入 AND 的是 class-1 判词 ⇒ 三个字段必须与顶层判词**并排落盘**，
               # 否则下游只看得到顶层 `verdict`，会把 Ⅱ/Ⅲ 类红误读成"BC 被禁"（97.5 明禁）。
               "gate_verdict_class1": adm_gate["gate_verdict_class1"],
               "gate_verdict_class1_green": adm_gate["gate_verdict_class1_green"],
               "gate_verdict_class1_measurement_status":
                   adm_gate["gate_verdict_class1_measurement_status"],
               "bc_blocking_caliber": adm_gate["bc_blocking_caliber"],
               "gate_run_dir": adm_gate["gate_run_dir"],
               "gate_verdict_sha256_12": adm_gate["gate_verdict_sha256_12"],
               # 裁定 93.2 / 93.3：分辨率族的口径必须**随产物落盘**（不是只写在牙的 observed 串里），
               # 否则下一位读者无法判断这些逐维读数是哪个口径量出来的（本轮实测过两口径结论相反）。
               "resolution_caliber": res_caliber,
               "resolution_caliber_note": res_caliber_note,
               "n_frames_resolution_caliber": int(rep_all_c["n_frames"]),
               "bins_occupied_per_dim_resolution_caliber": bins_all,
               "coverage_target": coverage_target,
               # ---- 裁定 94.3 的两个登记字段（顶层也落一份：行级/臂级读者不必钻进牙的 extra）----
               "heldout_bins_occupied_per_dim": heldout_bins_per_dim,
               "correctness_blind_dims": correctness_blind,
               "correctness_blind_dims_status": blindness_status,
               "correctness_blind_dims_caliber": ("heldout（= 正确性族的口径，裁定 93.3）"
                                                 if _heldout_scope else
                                                 "not_measured（本臂无 held-out 划分 ⇒ 三值纪律："
                                                 "不写 []、不写 0，写未测）"),
               "coverage_target_known": coverage_target in KNOWN_COVERAGE_TARGETS,
               # 条件 c 的**测量**（三态：measured / not_measured_interval_absent）。
               # 落在这里而不是只落在牙的 observed 串里：牙的 observed 是给人读的一句话，
               # 下游（闸 G29 复算、B2 registry）要的是逐维数组本身。
               "declared_interval_conformance": iv_conf,
               "n_build_frames": int(frames.shape[0]), "n_eval_frames": int(eval_x.shape[0]),
               "eval_frames_are_held_out": eval_frames is not None,
               "eval_scope": eval_scope,
               "eval_scope_known": eval_scope in KNOWN_EVAL_SCOPES, "teeth": teeth,
               "n_teeth": len(teeth), "n_red": len(red), "red": red,
               "n_warnings": len(warnings), "warnings": warnings,
               "n_warn": len(warnings),
               "n_unjudged": sum(1 for x in teeth if x["status"] == "UNJUDGED"),
               "n_n_a": sum(1 for x in teeth if x["status"] == "N_A"),
               "ok": not red,
               "schema": "d_minimal_common_check_schema_v1（裁定 78.2）+ C2 扩展字段 name/authority/note/applies_when/blocking",
               "n_teeth_blocking": sum(1 for x in teeth if x["blocking"]),
               "hard_held_out_teeth": hard,
               "near_constant_dims": nc,
               "near_constant_dims_unprotected": unprotected,
               "near_constant_dims_floor_immaterial": immaterial,
               "report": rep,
               "thresholds": {"clip_ratio_cap": th.clip_ratio_cap,
                              "min_bins_occupied": th.min_bins_occupied,
                              "start_pose_oob_dims_cap": th.start_pose_oob_dims_cap,
                              "near_constant_rel_tol": th.near_constant_rel_tol,
                              "ctrlrange_coverage_report_below": th.ctrlrange_coverage_report_below,
                              "floor_materiality_fraction": th.floor_materiality_fraction,
                              "min_bins_occupied_non_near_constant": th.min_bins_occupied_non_near_constant,
                              "min_bins_occupied_near_constant": th.min_bins_occupied_near_constant,
                              "warn_bins_occupied_near_constant": th.warn_bins_occupied_near_constant,
                              "provenance": th.provenance},
               "verdict": "PASS" if not red else "RED"}
    if red:
        raise NormContractViolation(RED_MESSAGE_SEPARATOR.join(red), payload=payload)
    return payload


def stats_payload(*, stats: Mapping[str, np.ndarray], case: str, source: str, floors: np.ndarray,
                  family: FloorFamily, representation_version: str,
                  provenance: Mapping[str, Any],
                  stats_provenance: str | None = None,
                  consumer: str | None = None,
                  coverage_target: str | None = None,
                  coverage: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """落盘格式。**源名进 `representation_version`**（裁定 52：不许静默替换）。"""
    # `denom_raw` / `denom_effective` / `physical_range` **必须落盘**：
    # 前者是近常量维判据的输入（`near_constant_dims`），后者是下限公式的输入，
    # 少一个，下游就无法从文件复算本闸的判定（= 缓存冒充表示，附录 02:274）。
    keys = ("q01", "q99", "mean", "std", "min", "max", "median", "q10", "q90",
            "span_q99_q01", "noise_mad_step", "step_abs_median",
            "denom_raw", "denom_effective", "physical_range")
    arr = {k: np.asarray(stats[k]).tolist() for k in keys if k in stats}
    if case == CASE_IDENTITY_EXPLICIT:
        # **落盘 = 被评估的那一份**（23:4x 修的缺陷）：此前这里用 `median` 与
        # `maximum(span_q99_q01, floors)` **重算** center/gain，而 `build_case()` 为了满足
        # 起态覆盖（牙 Tc）已经改写过 `stats["center"] / ["gain"] / ["denom_effective"]`
        # ⇒ 闸判的是覆盖后的值、文件里存的是覆盖前的值 ⇒ **拿着文件复现会得到越界的归一化**
        # （起态落 [-1,1] 外 ⇒ `processor_pi05.py:77` 给 bin -1）。
        denom = np.asarray(stats["denom_effective"] if "denom_effective" in stats
                           else np.maximum(np.asarray(stats["span_q99_q01"], dtype=np.float64),
                                           np.asarray(floors, dtype=np.float64)), dtype=np.float64)
        center = np.asarray(stats["center"] if "center" in stats else stats["median"],
                            dtype=np.float64)
        arr["center"] = center.tolist()
        arr["gain"] = (2.0 / denom).tolist()
        arr["denom_effective"] = denom.tolist()
    arr["floor"] = np.asarray(floors, dtype=np.float64).tolist()
    mainline = source in MAINLINE_ALLOWED_SOURCES
    prov = normalize_provenance(stats_provenance)
    return {"contract": "c2_norm_contract_v1", "case": case, "stats_source": source,
            # **顶层**落溯源标签与 BC 准入判定：下游（BC 配置 / `registry/`）不必读 `provenance`
            # 里的散文就能机器判"这份 stats 能不能进 BC"（裁定 85.4-3 的硬闸要能被人用上才算闸）。
            "stats_provenance": prov,
            "consumer_at_build": consumer,
            "bc_admission": bc_admission(prov),
            # 覆盖目标（裁定 87.3-1）必须**落盘**：牙 `Tcov`/`Tiv` 的 `applies_when` 依赖它，
            # 少了它，下游从文件复算就会把 ① 档判成 N_A（= 静默降级，附录 02:274 同族）。
            "coverage_target": coverage_target,
            "coverage": (None if coverage is None else dict(coverage)),
            "state_dtype_source": (provenance.get("state_dtype_source")
                                   if isinstance(provenance, Mapping) else None),
            "not_for_mainline_normalizer": (not mainline),
            "mainline_allowed": mainline,
            "floor_family": {"name": family.name, "coef": family.coef, "formula": family.formula,
                             "rationale": family.rationale, "coef_status": "proposed_pending_s1"},
            "n_dims": int(np.asarray(stats["q01"]).size),
            "representation_version": representation_version,
            "lerobot_eps": LEROBOT_EPS, "n_bins": N_BINS, "bin_width": BIN_WIDTH,
            "max_state_dim": MAX_STATE_DIM,
            "implementation_facts": {
                "normalize_processor": "lerobot/processor/normalize_processor.py:305-307,:335,:354,:369-377,:390,:94",
                "pi05_tokenizer": "lerobot/policies/pi05/processor_pi05.py:55,:72,:77,:81-84",
                "floor_baked_into": "q01/q99（处理器内部只算 q99-q01，无法外部注入下限）",
            "persisted_equals_evaluated": ("arrays.center/gain/q01/q99 = `evaluate_contract()` 实际"
                                           "使用的那一份（IDENTITY 档不再重算）；下游可用 "
                                           "`roundtrip_from_payload()` 从本文件复算判定")},
            "provenance": dict(provenance), "arrays": arr}


def roundtrip_from_payload(payload: Mapping[str, Any]) -> dict[str, np.ndarray]:
    """从**落盘的 stats 文件**重建 `evaluate_contract()` 需要的 stats 映射（round-trip 用）。

    为什么必须有这一步（本轮实测到的缺陷，不是理论洁癖）：IDENTITY 档的 `center/gain` 曾被
    `stats_payload()` 用 `median` + `maximum(span_q99_q01, floors)` **重算**，而 `build_case()`
    为满足起态覆盖（牙 Tc）已经改写过它们 ⇒ **闸判的是覆盖后的值、文件里存的是覆盖前的值**
    ⇒ 下游照文件复现会拿到越界的归一化（起态落 [-1,1] 外 ⇒ `processor_pi05.py:77` 出 bin -1）。
    这正是附录 02:274「缓存不得冒充新表示」的具体形态：**判定必须能在交付物上复算**。
    """
    arr = payload["arrays"]
    st = {k: np.asarray(v, dtype=np.float64) for k, v in arr.items()}
    st.setdefault("span_q99_q01", st["q99"] - st["q01"])
    if "denom_raw" not in st:
        st["denom_raw"] = st["span_q99_q01"]
    return st


def admission_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """从**落盘的 stats 文件**取回 BC 准入判定，并用当前契约层的口径**重判一次**。

    为什么必须重判而不是直接读文件里的 `bc_admission`：文件里的判定是**生成当时**那版契约层写的；
    若口径后来改了（例如 D 追加了可进 BC 的档），照抄旧字段就是"缓存冒充表示"（附录 02:274）。
    返回 `file_says` 与 `recomputed` 两份 + `agree`，不一致 ⇒ 调用方必须报，不许静默取其一。
    """
    file_says = dict(payload.get("bc_admission") or {})
    prov = normalize_provenance(payload.get("stats_provenance"))
    recomputed = bc_admission(prov)
    return {"stats_provenance": prov,
            "consumer_at_build": payload.get("consumer_at_build"),
            "file_says": file_says,
            "recomputed": recomputed,
            "agree": (file_says.get("admissible_for_bc") == recomputed["admissible_for_bc"]
                      if file_says else None),
            "file_had_bc_admission": bool(file_says)}


def coverage_target_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """从**落盘文件**取回覆盖目标，并用当前契约层的口径核它是否仍属已知集合。

    为什么要重核而不是直接用：`Tcov`/`Tiv` 的 `applies_when` 全靠这个字段。若文件里写着一个
    已作废的目标名（或压根没有），照抄就会让两把牙静默变 N_A ⇒ 那是"没测到"被读成"测到了没有"
    （红线 `absence_of_measurement_is_not_measurement_of_absence`，裁定 88.3-1）。
    """
    tgt = payload.get("coverage_target")
    return {"coverage_target": tgt,
            "known": tgt in KNOWN_COVERAGE_TARGETS,
            "file_had_coverage_target": tgt is not None,
            "coverage_block_present": payload.get("coverage") is not None}


def payload_sha12(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     default=str).encode("utf-8")).hexdigest()[:12]
