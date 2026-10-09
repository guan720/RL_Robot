"""**S4a** —— harness ↔ VLA 运行时接线（chunk 循环 + C/E/D 三槽 + 事件/事实写入 + 版本三件套）。

**落地依据（裁定 65-6 / `rl_harness_supervision/d_handoff_to_a2_20260929.md` §15.5）**：
「S4a（现在就能做）：`harness/vla_runtime.py` 新文件 + §3 的接口签名 + chunk 循环 + 三槽推进 +
事件写入 + 版本三件套；对着真实 env 跑一条可手算的短轨迹，逐字段手核」。
接口签名的出处 = `docs/a2_s4_vla_runtime_interface_20260929.md` §3.1–§3.5（A2 草案，D 裁定 65 逐条裁过）。

## 硬边界（违反即事故）

- **`harness/contracts.py` 一个字节不动**（裁定 65-6 重申；本文件只 **import** 它的 7 个 `EVENT_KINDS` 与四个 dataclass）。
- **不复用 `ReplayDriver.commit/finish`**：`contracts.py:69` 的 `commit` 按 **epoch** 单键且不可变
  （chunk 代际需要逐代提交），`contracts.py:87` 的 `finish` 把 **reward 写死 `0.0`、source 写死 `"mock"`**
  ⇒ 真实 outcome 由本文件自己发 `OutcomeEvent`（构造 dataclass 不算改契约）。
- **词表不新造值**：`source` ∈ `ledger.FRAME_SOURCES`、`execution_status` ∈ `ledger.EXECUTION_STATUS`、
  账本事件 kind ∈ `ledger.EVENT_KINDS`（`harness/ledger.py:31`–`:41`）。
- **冻结面语义**：`late_policy="hold"`（裁定 65-3；依据 v4 附录一 `:111`「错过 deadline 不把晚到结果塞进过期索引…
  继续已有合法动作…**异常事实保留，不重标成"准时"**」）⇒ **迟到帧永不被写成 `activated`**（`_record_late_frame`）。

## 时间轴语义（v4 附录二 `02_异步动作时间轴与学习目标.md`，`sha256-12 a6ab42165ab3`）

固定时间槽 `n = n_replan`，chunk 长度 `H = chunk_size`，**`H ≥ 2n`**（附录一 `:103`）。
第 `g` 代 chunk 在绝对帧 `t_g = g·n` 发起请求，三段索引（附录二 §1 的表）：

| 段 | 索引区间 | 对应绝对帧 | 谁执行 | 本 chunk 的这些索引 |
|---|---|---|---|---|
| **C** | `[0, n)` | `[t_g, t_g+n)` | **上一代**（`g-1`）的 E | **不产生物理动作** ⇒ 记 `not_activated` |
| **E** | `[n, 2n)` | `[t_g+n, t_g+2n)` | 本代 | **`activated`**，`chunk_index = f - t_g` |
| **D** | `[2n, H)` | —— | 被下一代替换 | **不产生物理动作** ⇒ 记 `not_activated` |

⇒ **每个绝对帧只采纳一个来源**（附录一 `:115`）；`lease_generation` = **chunk 代际**（裁定 65-3）。

**frame_fact 的两类行（读账本的人必须知道，否则会重复计数）**：
- **权威行 = `execution_status='activated'`**：每个绝对帧**最多一行**（这条由验证脚本做成闸）；
  它的 `chunk_id/chunk_index/source` 就是"这一帧的命令来自哪次推理"（附录二 §1 末句的要求）。
- **提案记账行 = `execution_status='not_activated'`**：C 段与 D 段索引**不产生物理动作**，
  但仍逐索引留档（附录一 `:81`/`:83`：不许只有 `executed_length`）⇒ **同一 `abs_frame` 可以有多行
  `not_activated`**（来自不同代的提案），**这不是重复计数，是逐提案记账**。
**priming**：`t=0` 时不存在「已承诺的真实命令队列」⇒ C 槽无源。本文件默认 `prime_mode="hold"`
（前 `n` 帧 `source="hold"`、发 `prime` 事件；chunk 0 的 `[0,n)` 记 `not_activated`），
另留 `prime_mode="first_chunk"`（把 chunk 0 的 `[0,n)` 直接执行）作对照。
**裁定 83§5① 已裁 `prime_mode="hold"`**（进 `representation_version`；可推翻条件：若 S4b 实测首帧 hold
系统性错过抓取窗口，则改 `first_chunk` 并**另立版本**）。`first_chunk` 仍保留为对照臂，
验证脚本 G13 证明两案**行为不同**（不是装饰品）。

## 学习资格的 timeout 口径（**裁定 83§5②：`timeout_isolation_scope = td_only`**）

主线 `max_episode_steps=300` / `episode_horizon_s=10.2`（裁定 58.3 / 65-2）下，**绝大多数 zero-shot 局以
`terminal_kind="timeout"` 收尾** ⇒ 这个开关直接决定 S4 能留下多少可学习数据。

- **TD 侧：隔离**（`TIMEOUT_ISOLATES_TD=True`）。截断本该 **bootstrap**、不是终止 ——
  v4 附录二 `a6ab42165ab3` / 354 ln / `:228`「Harness 抢占、**超时**、云服务掉线、日志缺失：属于中断／删失，
  **不因此把后续价值设为零**」；`:215`「超时、接管、来源或边界不明的宏过程仍按既有协议隔离；
  本规则**不自动恢复其 actor／TD 资格**」。
- **BC 侧：保留但打标**（`TIMEOUT_ISOLATES_BC=False` ⇒ `representation_version` 含 `timeout_bc=kept_flagged`）。
  **A2 已按 D 给的可推翻条件逐条查过 v4 原文，未找到任何明文禁止**，反而找到 4 处正面支撑
  （三元组 = 文件 / sha256-12 / 行号）：

  | # | 出处 | 原文要点 |
  |---|---|---|
  | 1 | 附录一 `aae20ffe604f` / 433 ln / `:241` | 「隔离该宏 **TD** 并保留逐帧事实、**可用监督**…**非终局超时不冒充 `done=1`**」 |
  | 2 | 附录一 `aae20ffe604f` / `:332`（T12） | 「当前窗口**非终局超时**或接管 ⇒ **不用 `done=1` 伪终止**；不兼容宏样本隔离，**原始帧保留**」 |
  | 3 | 附录一 `aae20ffe604f` / `:388`（T35） | 「**BC质量与TD资格分开**」 |
  | 4 | 开发技术方案 `0a9a2092e18a` / 418 ln / `:241` | 「**BC 可信标签 mask、实际执行 mask、TD 资格是三种不同条件**」 |

- **口径边界（A2 自己划，不替 D 放大）**：上表里的「超时」在 v4 原文中主要指**槽级**的推理超时 /
  deadline miss / 失联，而本开关管的是**回合级**的 gym TimeLimit 截断（300 步 / 10.2 s）。
  两者**不是同一机制** ⇒ 上表是**原则迁移**，不是逐字同一。**若 D 认为该迁移不成立，回退
  `both_isolated` 只需翻一个常量**（`TIMEOUT_ISOLATES_BC=True`），`representation_version` 的
  `timeout_bc=` token 由常量派生 ⇒ 会自动变成 `isolated`，**不需要人去改版本串**。
- **三条硬约束（裁定 83§5②；做成机器强制，不是文书）**：
  ① BC 记录必须带 `truncated_by_timelimit=True` —— `bc_record_extras()` 产出、`validate_bc_timeout_record()` 看守；
  ② `representation_version` 必须含 `timeout_bc=kept_flagged` —— token 由常量派生（不能手写撒谎）；
  ③ 截断末帧**不得**被当成「成功／终止」标签 —— `validate_truncation_not_terminal()` 看守，
     验证脚本 G18 的**输入级变异体**证明它会红（裁定 83.1 `tooth_must_be_mutant_proven`）。
- **状态**：`d_selfconfirmed_pending_user_ratification`（D 自确认执行、待用户事后追认的**口径放宽**）。

## 本文件**不声称**的事

- **不声称已实现异步重叠**：`async_overlap=False`（默认）⇒ 推理是**同步阻塞**的，
  "迟到"由**实测推理墙钟 > 槽预算**判定（`inference_wall_s > n·dt_s`）。真正的线程重叠是 S4 的下一步，
  产物里必须带 `async_overlap` 字段，**不许把同步口径的余量说成异步余量**（§2.4.1 的教训）。
- **不声称任何能力**：本文件不计算成功率；`finalize()` 只发 outcome 与训练视图资格（裁定 46）。
- **不声称 S4b 已完成**：四类判定（成功/失败/超时/未知）接 `ledger` 属 **S4b**，等 C2 的 `harness/env_gym_aloha.py`。
"""

from __future__ import annotations

import os
import time

import numpy as np
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from harness.contracts import (ActionEvent, DecisionRequest, EVENT_KINDS as CONTRACT_EVENT_KINDS,
                               OutcomeEvent, QueueState, TrainingView)
from harness.ledger import EXECUTION_STATUS, FRAME_SOURCES, FactLedger

# ── 主线口径（裁定 53 / 58.3 / 65；改这里 = 换 representation_version，不许就地改）──
MAINLINE_DT_S = 0.034
MAINLINE_CONTROL_HZ = 29.411764705882355
MAINLINE_N_REPLAN = 25                # 裁定 65-1（H=50，取 H≥2n 等号）
MAINLINE_CHUNK_SIZE = 50
MAINLINE_MAX_EPISODE_STEPS = 300      # 裁定 65-2：**维持 300，驳回 176**
MAINLINE_EPISODE_HORIZON_S = 10.2     # 裁定 58.3：必须进每份 manifest
PUBLISHED_GYM_ALOHA_CALIBER = "DT=0.02, 300 steps, 6.0 s, 50 Hz"   # 裁定 65-2 强制附带
MAINLINE_LATE_POLICY = "hold"         # 裁定 65-3（附录一 :111）
MORPHOLOGY = "aloha_bimanual_14d"
ENV_ID = "gym_aloha/AlohaTransferCube-v0"
CONTRACT_VERSION = "v4-appendix01"    # 与 ledger.CONTRACT_VERSION 同值（不另造）
STATS_VERSION_ABSENT = "NONE"         # 缺 stats 时的**唯一**合法写法（不许空串，§3.1）
# 视觉通道的必需键（ObsBundle:95 的注释 + G3 已验证的相机映射
# `scripts/a2_pi05_zeroshot_eval.py:190`、`:249`–`:250`）。
# **为什么要有这张表**：G3 的 0/20 根因是 `normalizer_processor.config.features={}` 静默 pass-through；
# 同一族事故在 S4 的形式是「`obs.images={}` 静默退化成状态输入」。任务书明令 A2 不得自行退化，
# 所以这里做成**机器强制**：缺键 ⇒ 硬隔离 + 账本事件，绝不静默通过。
REQUIRED_IMAGE_KEYS = ("top", "left_wrist", "right_wrist")
# `terminal_kind=timeout`（gym 的 TimeLimit 截断，主线 = 300 步 / 10.2 s，裁定 58.3/65-2）要不要隔离学习资格？
# **裁定 83§5② 已裁：`timeout_isolation_scope = td_only`**（D 改 A2 的保守默认 `both_isolated`），
# 标 `d_selfconfirmed_pending_user_ratification`。依据、可推翻条件与三条硬约束见文件头
# 「学习资格的 timeout 口径」。**翻这两个常量 = 改学习语义 = 换 representation_version**
# （`timeout_td=` / `timeout_bc=` 两个 token 由常量派生 ⇒ 版本串不会与常量脱节）。
TIMEOUT_ISOLATES_TD = True
TIMEOUT_ISOLATES_BC = False           # ← 裁定 83§5②（原 True = A2 的保守默认，D 已改）
TIMEOUT_ISOLATION_SCOPE = ("both_isolated" if (TIMEOUT_ISOLATES_TD and TIMEOUT_ISOLATES_BC)
                           else "td_only" if TIMEOUT_ISOLATES_TD else "neither")
TIMEOUT_TD_TOKEN = "isolated" if TIMEOUT_ISOLATES_TD else "kept"
TIMEOUT_BC_TOKEN = "isolated" if TIMEOUT_ISOLATES_BC else "kept_flagged"
TIMEOUT_RULING = ("裁定 83§5②（td_only；D 自确认执行、待用户事后追认的口径放宽）")
# v4 依据（三元组 = 文件 / sha256-12 / 行数 / 行号）。**A2 自行重算 sha，不采信交接值**（裁定 83§7）。
TIMEOUT_V4_BASIS = (
    "附录一 RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/appendices/"
    "01_接口契约与开发验收.md（aae20ffe604f / 433 ln）:241「隔离该宏 TD 并保留逐帧事实、可用监督…"
    "非终局超时不冒充 done=1」、:332(T12)「不用 done=1 伪终止；不兼容宏样本隔离，原始帧保留」、"
    ":388(T35)「BC质量与TD资格分开」；开发技术方案 01_开发技术方案.md（0a9a2092e18a / 418 ln）:241"
    "「BC 可信标签 mask、实际执行 mask、TD 资格是三种不同条件」；异步附录 02_异步动作时间轴与学习目标.md"
    "（a6ab42165ab3 / 354 ln）:228「超时…属于中断／删失，不因此把后续价值设为零」、:215「不自动恢复其 "
    "actor／TD 资格」。**口径差如实登记**：v4 的「超时」多为槽级（推理超时/deadline miss/失联），"
    "本开关管回合级 gym TimeLimit ⇒ 属原则迁移，非逐字同一。")


# ══════════ 裁定 95.3-④：两种**动作块执行语义**（第 1–2 步一律用 `standard_sync`）══════════
# 判据原文（`work/project_parameters.json` rev20 `ruling95_technical_corrections_rev20` →
# `correction_4_execute_second_half_of_chunk`，**不重新解释**）：
#   「现运行时 `execution_mask = bc_mask = [0,0,1,1]`，模型输出 50 步而**只执行 idx 25–49**、
#     帧 0–24 是 prime hold。**问题不在时间对齐、在状态对齐**：f=25 时的真实状态是「保持了 25 步」
#     的状态，不是「执行了 idx 0–24」的状态，而 idx 25–49 是对后者预测的。⇒ `H ≥ 2n`、索引正确、
#     账本一致只证明调度符合自己定义的规格，**不证明策略预测与实际轨迹一致**。」
#   裁定：「**第 1–2 步一律用标准同步动作块执行**；第 3 步才做『标准执行 vs 后半段调度』的配对比较
#     （同 ckpt / 同初态 / 同 seed 序列）…**两种执行的数字不得互搬**。」
#   另：`prerequisite_before_step_1` = 「**标准同步执行通路**必须能在仿真里跑起来（绕开
#     `execution_mask=[0,0,1,1]` 的后半段调度）⇒ 本轮唯一必须新增的运行时能力，属 **Ⅰ 类**」。
EXEC_MODE_HARNESS_SECOND_HALF = "harness_second_half"   # v4 附录二的 C/E/D 调度（S4a/S4b 现状、默认）
EXEC_MODE_STANDARD_SYNC = "standard_sync"               # 裁定 95.3-④：执行 idx [0,n)，**无** prime hold
EXEC_MODES = (EXEC_MODE_HARNESS_SECOND_HALF, EXEC_MODE_STANDARD_SYNC)
PRIME_MODE_NONE = "none"          # **只**与 `standard_sync` 合法搭配（两个开关互锁，不许静默混搭）
PRIME_MODES = ("hold", "first_chunk", PRIME_MODE_NONE)
EXEC_MODE_CALIBER = {
    EXEC_MODE_HARNESS_SECOND_HALF: {
        "executed_indices": "[n, 2n)（= slot_e）", "priming": "帧 0..n-1 = prime hold（无源）",
        "requires_h_ge_2n": True, "owner": "v4 附录二 02_异步动作时间轴与学习目标.md（a6ab42165ab3）",
        "state_alignment_risk": ("**已登记的最高优先算法风险**（裁定 95.3-④）：f=n 的真实状态是"
                                 "「保持了 n 步」的状态，而 idx n..2n-1 是对「执行了 idx 0..n-1」"
                                 "的状态预测的 ⇒ 两者不必然一致"),
    },
    EXEC_MODE_STANDARD_SYNC: {
        "executed_indices": "[0, n)（= slot_e，由**运行时**重盖章，不信策略给的槽位）",
        "priming": "**无**（帧 0..n-1 由第 0 代直接供给 ⇒ `prime_mode` 必须 = 'none'）",
        "requires_h_ge_2n": False,
        "h_constraint": "1 ≤ n_replan ≤ H（执行的是 chunk 的**前** n 项）",
        "owner": "裁定 95.3-④（第 1–2 步一律用它）；= G3 评测脚本 `--action-mode queue` 的语义",
        "state_alignment_risk": ("**无**：idx 0 对应的观测就是发起推理那一刻的观测（仿真时间在推理期间"
                                 "不推进）⇒ 预测条件与实际轨迹一致"),
        "blocking_note": ("推理**阻塞**控制环（`async_overlap=false`）⇒ 墙钟里推理与执行相加；"
                          "这与 harness_second_half 的墙钟**同口径**（都是同步串行），但**执行的索引段不同** "
                          "⇒ 两者的成功率/推进度**不得互搬**（裁定 95.3-④）"),
    },
    "cross_mode_transplant_ban": ("两种执行语义的任何指标（成功率 / 推进度 / 延迟带 / execution_mask）"
                                  "**不得互搬**；`representation_version` 里的 `exec=` token 是机器判据，"
                                  "版本串不同即不可并列（裁定 46.4 / 53.6 / 71 / 95.3-④）"),
    "ruling": "裁定 95.3-④ + `params` rev20 `prerequisite_before_step_1`",
}


# ══════════════════════ S4b（T-A2-6 · 裁定 93）：四类判定的口径常量 ══════════════════════
# **判定层不归 A2**（`d_handoff_to_a2_20260930.md` §一：「必须复用、不得自造」）。
# 四类结论（成功/失败/超时/未知）一律取自 C2 的 `harness/env_gym_aloha.py`
# （579 ln `6c4d71eb732e`，`MODULE_REPRESENTATION_VERSION='c2-env-gym-aloha-v1'`）的
# `judge_from_facts()`；本文件只做「判定 → runtime → ledger」的**接线**，不重算判定。
# 自造判定层 = 与 C2 闸 `scripts/c2_gate_env_gym_aloha.py`（`c9100b3811cd`）的 J1–J15 分叉。
S4B_JUDGMENT_MODULE = "harness/env_gym_aloha.py"
S4B_JUDGMENT_AUTHORITY = "c2_env_gym_aloha.judge_from_facts"
S4B_JUDGMENT_GATE = "scripts/c2_gate_env_gym_aloha.py"
# `outcome_class` 的**唯一**合法来源。第二个常量是"被禁的那个来源"，
# 它存在的意义是**让耦合不可表达**：调用方若把它传进 `finalize_from_env_judgment(outcome_source=…)`，
# 运行时当场抛 `OutcomeCouplingError`（验证脚本的变异体就靠这条判红）。
OUTCOME_SOURCE_GEOMETRIC = "c2_geometric_judgment"
OUTCOME_SOURCE_REWARD4_FORBIDDEN = "env_reward_eq_4__FORBIDDEN_as_outcome_source"
# 判据原文（`work/project_parameters.json:1047`，不重新解释）：
#   「S4b（等 C2 的 env）= 四类判定接 `ledger`，独立于 `reward==4`，不一致即红。」
S4B_CRITERION_VERBATIM = ("S4b（等 C2 的 env）= 四类判定接 ledger，独立于 reward==4，不一致即红"
                          "（work/project_parameters.json:1047 `vla_runtime_gap`）")
# env 侧 `reward==4` 的语义出处（C2 读到的实现原文，A2 只转引、不重读）：
#   `gym_aloha/env.py:178-180`：`terminated = is_success = reward == 4`
#   `gym_aloha/tasks/sim.py:125-149`：reward=4 ⇔ ("red_box","vx300s_left/10_left_gripper_finger")
#                                     有接触 且 red_box 不接触 table
# ⇒ 两条**代码可推**的缺陷（kind=code_read_semantics，非能力主张）：
#   ① 方向写死右→左：反向任务里左爪夹起离桌的瞬间就满足 reward==4（那是反向任务的**起点**）；
#   ② 只要求接触、不要求持稳：一次弹射（flick）擦到左指即可判成功。
S4B_REWARD4_SEMANTICS_SOURCE = ("gym_aloha/env.py:178-180 + gym_aloha/tasks/sim.py:125-149"
                                "（经 harness/env_gym_aloha.py 的文件头转引，A2 未重读 site-packages）")
# ledger 入账的准入声明：env 判定**不是**被门禁分级的裁定 ⇒ 只能走 `observation_only=True`
# （`harness/ledger.py:377` 起的 fail-closed 准入闸；C2 的 env 文件头同一条要求）。
# A2 **不改** `harness/ledger.py`，只调它的既有公开 API 并显式登记这件事。
S4B_LEDGER_ADMISSION = "observation_only"
# C2 的 obs 键名（π₀.₅ 策略层命名，出处 = A2 自己的 `scripts/a2_pi05_contract_probe.py:91-105`）
# → runtime 侧 `REQUIRED_IMAGE_KEYS`（`top/left_wrist/right_wrist`）的映射。
# **为什么要显式映射**：`_guard_vision_channels()` 认的是 runtime 键名；C2 的 env 产出的是策略层键名。
# 映射写在 A2 的适配器里（不动 C2 的文件），并把映射本身落进产物 ⇒ 两侧键名口径可被逐字复核。
PI05_TO_RUNTIME_IMAGE_KEYS = {
    "observation.images.base_0_rgb": "top",
    "observation.images.left_wrist_0_rgb": "left_wrist",
    "observation.images.right_wrist_0_rgb": "right_wrist",
}
GOAL_ID_BY_DIRECTION = {"right_to_left": "transfer_cube_right_to_left",
                        "left_to_right": "transfer_cube_left_to_right"}


class OutcomeCouplingError(RuntimeError):
    """四类判定被**耦合到 `reward==4`** ⇒ 当场抛（不是 warn、不是继续）。

    判据原文见 `S4B_CRITERION_VERBATIM`。这颗牙的形状是「让耦合不可表达」：
    `outcome_source` 只接受 `OUTCOME_SOURCE_GEOMETRIC`，传别的值（尤其是
    `OUTCOME_SOURCE_REWARD4_FORBIDDEN`）⇒ 抛。验证脚本的变异体 M-S4B-1 就是传它。
    """


class OutcomeDisagreementRed(RuntimeError):
    """几何真值与 env 的 `reward==4` 判定不一致 ⇒ **红**（裁定 54 / `params:1047`）。

    只在 `raise_on_disagreement=True` 时抛；默认**不抛**，而是把 RED 记进产物与 ledger payload
    —— 因为反向任务里这个不一致是**预期形态**（env 的 reward 写死右→左），
    抛出来会把"env 的缺陷"误读成"A2 的运行时崩了"。两种处置都必须留 RED 记录，区别只是抛不抛。
    """


def load_env_gym_aloha() -> Any:
    """**惰性** import C2 的判定层。

    为什么惰性：`harness/env_gym_aloha.py` 在模块级 import `envs/gym_aloha_shim.py`，
    后者的 `make_env()` 才 import `gym_aloha`；但 `harness/vla_runtime.py` 的 stub 手算臂
    （验证脚本 G1–G18）**不需要**真 env ⇒ 模块级 import 会让 CPU-only 的闸也背上 GL/gym 依赖。
    """
    from harness import env_gym_aloha as ega
    return ega


def env_gym_aloha_identity() -> dict[str, Any]:
    """C2 判定层的**身份三元组**（路径 / sha256-12 / 行数），由 A2 侧**自己重算**，不采信交接值。"""
    import hashlib
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[1] / S4B_JUDGMENT_MODULE
    g = pathlib.Path(__file__).resolve().parents[1] / S4B_JUDGMENT_GATE
    def ident(q: pathlib.Path) -> dict[str, Any]:
        if not q.exists():
            return {"path": str(q.relative_to(q.parents[1])), "exists": False,
                    "sha256_12": None, "lines": None}
        b = q.read_bytes()
        return {"path": str(q.relative_to(q.parents[1])), "exists": True,
                "sha256_12": hashlib.sha256(b).hexdigest()[:12],
                "lines": len(b.decode("utf-8", "replace").splitlines())}
    return {"judgment_module": ident(p), "judgment_gate": ident(g),
            "authority": S4B_JUDGMENT_AUTHORITY,
            "recomputed_by": "harness/vla_runtime.py::env_gym_aloha_identity（A2 侧重算，裁定 83§7）",
            "handoff_declared_values_for_comparison": {"judgment_module_sha256_12": "6c4d71eb732e",
                                                       "judgment_module_lines": 579,
                                                       "judgment_gate_sha256_12": "c9100b3811cd",
                                                       "source": "rl_harness_supervision/d_handoff_to_a2_20260930.md §一"}}



def representation_version(*, dt_s: float, n_replan: int, chunk_size: int, late_policy: str,
                           prime_mode: str, policy_version: str, stats_version: str,
                           shim_sha256_12: str, render_backend: Sequence[str],
                           async_overlap: bool,
                           exec_mode: str = EXEC_MODE_HARNESS_SECOND_HALF) -> str:
    """版本三件套的第三件（B2 在 S4 `:145` 要求"每条轨迹都要有"）。

    **`late_policy` 必须进这个串**（裁定 65-3②：它是冻结面语义，改了就是换契约）。
    **`timeout_bc=` 也必须进这个串**（裁定 83§5② 硬约束②：BC 侧保留 timeout 轨迹时，
    版本串必须显式写 `timeout_bc=kept_flagged`，否则下游无法从版本判断"这批 BC 数据含被剪断的局"）。
    两个 token 都由模块常量派生 ⇒ **翻常量自动换版本，不需要人去改字符串**。

    **`exec=` 也必须进这个串**（裁定 95.3-④：「两种执行的数字不得互搬」⇒ 版本串必须能机器区分
    「标准同步执行」与「后半段调度」，否则第 3 步的配对比较无从证明两边只差执行语义）。
    默认值 = `harness_second_half`。**⚠ 实测更正（A2，as_of 2026-09-30 12:5x）**：本 token 是
    **无条件**拼进去的 ⇒ 默认路径的版本串**也多了一段** `:exec=harness_second_half`，
    「既有产物一字节不变」这句**曾写在本文里、是假的**（已更正）。实测对照：
    `runs/vla/a2_s4b_outcome_ledger_20260930_dbg7/s4b_verification.json`（改前）vs
    `…_execmode_reg2/…`（改后），两条 `vla_runtime_v1:…` 串**只差这一个 token**、其余逐字相同。
    **影响面已实测（不是推断）**：① 权威延迟带产物 `runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep{4,5}.json`
    **不含任何 `vla_runtime_v1:` 串**（只带 env shim 版本 `gym_aloha_dt0.034_29.4118hz_shim_v1`）
    ⇒ **rep4 0.8009 / rep5 0.7766 那条带的身份不受影响**；② S4a 17/17 + S4b 15/15 全绿（含变异自检
    21/21 + 22/22）⇒ 默认路径**行为**零回归；③ 历史 runtime 产物的版本串与新产物**不可按字节相等比较**，
    必须走下面的 `exec_caliber_of_representation_version()` 归一。
    """
    rb = "|".join(str(x) for x in render_backend)
    return (f"vla_runtime_v1:dt={dt_s}:n_replan={n_replan}:H={chunk_size}:late={late_policy}"
            f":prime={prime_mode}:exec={exec_mode}:async={int(async_overlap)}"
            f":timeout_td={TIMEOUT_TD_TOKEN}:timeout_bc={TIMEOUT_BC_TOKEN}"
            f":policy={policy_version}"
            f":stats={stats_version}:shim={shim_sha256_12}:render={rb}")


EXEC_TOKEN_ABSENT_MEANS = EXEC_MODE_HARNESS_SECOND_HALF
"""**历史产物的归一规则（机器可读，不是散文约定）**：版本串里**没有** `exec=` token ⇒ 一律读作
`harness_second_half`。

为什么这不是"猜测默认值"：`exec_mode` 这个开关是**本轮（裁定 95.3-④）才引入**的，引入之前运行时
**只存在**后半段调度这一种执行语义 ⇒ "缺 token" 与 "token=harness_second_half" 指的是同一件事。
这条规则存在的唯一目的是让**跨代比较**能做（第 3 步的配对比较要把新产物与历史带对齐口径），
而**不是**为了让两种执行语义的数字互搬 —— 归一之后仍然必须按 `EXEC_MODE_CALIBER`
`cross_mode_transplant_ban` 拒绝把 `standard_sync` 的任何指标写进 `harness_second_half` 的结论里。
"""


def exec_caliber_of_representation_version(rep_version: str | None) -> dict[str, Any]:
    """从版本串里**读出**执行语义（`exec=` token）；读不到 token 按 `EXEC_TOKEN_ABSENT_MEANS` 归一。

    返回一个可落盘的判定块（含 `token_present` / `exec_mode` / `normalized_from_absent_token`），
    这样"这条数字属哪种执行语义"在产物里是**显式字段**，不需要读者去解析字符串。
    **三值纪律**：`rep_version` 为空/非串 ⇒ `exec_mode=None` + `measurement_status='not_measured'`
    （读不到 ≠ 读到 harness）。
    """
    if not isinstance(rep_version, str) or not rep_version:
        return {"measurement_status": "not_measured", "token_present": None, "exec_mode": None,
                "normalized_from_absent_token": False,
                "why": "rep_version 缺失或非字符串 ⇒ 读不到（`absence_of_measurement_is_not_"
                       "measurement_of_absence`，裁定 88.3-1）"}
    tok = None
    for part in rep_version.split(":"):
        if part.startswith("exec="):
            tok = part[len("exec="):]
            break
    if tok is None:
        return {"measurement_status": "measured", "token_present": False,
                "exec_mode": EXEC_TOKEN_ABSENT_MEANS, "normalized_from_absent_token": True,
                "rule": "缺 token ⇒ harness_second_half（`EXEC_TOKEN_ABSENT_MEANS` 的 docstring 给了理由）"}
    known = tok in EXEC_MODES
    return {"measurement_status": ("measured" if known else "not_measured"), "token_present": True,
            "exec_mode": (tok if known else None), "normalized_from_absent_token": False,
            "token_in_vocabulary": known,
            "why": (None if known else f"token={tok!r} 不在 {EXEC_MODES} ⇒ 读到了但读不懂 ⇒ "
                                       "not_measured（三值纪律：不许猜成默认值）")}


def cross_mode_transplant_allowed(rep_a: str | None, rep_b: str | None) -> dict[str, Any]:
    """**牙**：两条版本串的执行语义不同 ⇒ 任何指标都不得互搬（裁定 95.3-④ / 46.4 / 53.6 / 71）。

    只做一件事：把"能不能并列"变成**可落盘的布尔**，供第 3 步的配对比较脚本与任何闸消费。
    `same_caliber=False` 时**不是**"比较失败"，而是"这两个数字属两种执行语义 ⇒ 只能作为
    **配对差值**报（同 ckpt / 同初态 / 同 seed 序列），不得把任一侧的率搬进另一侧的结论"。
    """
    ca = exec_caliber_of_representation_version(rep_a)
    cb = exec_caliber_of_representation_version(rep_b)
    both = (ca.get("exec_mode") is not None and cb.get("exec_mode") is not None)
    same = bool(both and ca["exec_mode"] == cb["exec_mode"])
    return {"same_exec_caliber": same, "measurable": both, "a": ca, "b": cb,
            "transplant_allowed": same,
            "paired_comparison_allowed": bool(both),
            "ban": EXEC_MODE_CALIBER["cross_mode_transplant_ban"],
            "ruling": "裁定 95.3-④"}


# ─────────────────────────── 数据类（§3.2 / §3.3）───────────────────────────
@dataclass(frozen=True)
class ObsBundle:
    frame: int                                   # **绝对控制帧**（v4 附录一 :364）
    images: Mapping[str, Any]                    # 键 = top | left_wrist | right_wrist
    state: Any                                   # 14 维 qpos（**原始 rad，未归一化**）
    state_raw_14d: Any                           # 与 state 同源，留给 C2 的起态覆盖闸（S2 :122）
    goal_id: str
    dt_s: float
    control_hz: float
    representation_version: str
    render_backend: tuple[str, ...]              # 五元标注（裁定 46.4 / 53.6 / 72）


@dataclass(frozen=True)
class ActionChunk:
    request_id: str
    chunk_index: int                             # 第几个 chunk（= 代际 g）
    chunk_id: str
    lease_generation: int                        # = 控制代际（裁定 65-3）
    epoch: int                                   # **透传 ledger 既有语义**，S4 不重定义
    actions: Any                                 # shape (H, d_a)，**0..H-1 全部保留**
    created_at_frame: int
    planned_frames: tuple[int, int]              # [t, t+H)
    slot_c: tuple[int, ...]                      # 索引区间 [0, n)      —— 不执行
    slot_e: tuple[int, ...]                      # 索引区间 [n, 2n)     —— 执行
    slot_d: tuple[int, ...]                      # 索引区间 [2n, H)     —— 被替换
    dt_s: float
    control_hz: float
    n_replan: int
    chunk_size: int
    inference_wall_s: float | None               # 实测；None = 未测（**不许填 0**）
    deadline_frame: int                          # **绝对帧**（contracts.DecisionRequest.deadline 是 int）
    deadline_s: float                            # = n_replan * dt_s（两者都要能独立复核，§3.4）
    policy_version: str
    stats_version: str
    shim_sha256_12: str
    representation_version: str
    # ── 裁定 95.3-④：执行语义必须由**运行时**盖章，不由策略自述 ──────────────────────
    # 两个字段都有默认值 ⇒ 既有构造点（S4a/S4b 验证脚本、GPU 臂）一字节不改也不报错。
    exec_mode: str = EXEC_MODE_HARNESS_SECOND_HALF
    slots_restamped_by_runtime: bool = False


@dataclass(frozen=True)
class StepResult:
    abs_frame: int
    action: Any
    source: str                                  # ∈ FRAME_SOURCES
    execution_status: str                        # ∈ EXECUTION_STATUS
    chunk_id: str | None
    chunk_index: int | None
    lease_generation: int
    request_id: str | None
    late_choice: str | None                      # "hold" | "keep" | "terminate"（裁定 65-3①：必须记"实际选择"）
    reward: float
    terminated: bool
    truncated: bool
    info: Mapping[str, Any] = field(default_factory=dict)


class VlaChunkPolicy(Protocol):
    """策略侧协议（§3.1）。π₀.₅ / 未来任何 VLA 都按这个接。"""
    policy_version: str
    stats_version: str
    chunk_size: int

    def reset(self, seed: int) -> None: ...
    def select_chunk(self, obs: ObsBundle) -> ActionChunk: ...


class EnvAdapter(Protocol):
    """env 侧协议。**S4a 自带两个实现**：`GymAlohaAdapter`（真实 env，A2 自己的渲染路径）
    与 `StubEnvAdapter`（可手算，CPU-only，用于逐字段手核）。S4b 由 C2 的 `harness/env_gym_aloha.py` 替换。"""
    dt_s: float
    control_hz: float
    max_episode_steps: int

    def reset(self, seed: int) -> ObsBundle: ...
    def observe(self, frame: int) -> ObsBundle: ...
    def apply(self, action: Any) -> tuple[float, bool, bool, Mapping[str, Any]]: ...
    def render_backend(self) -> tuple[str, ...]: ...


# ─────────────────────────── 运行时 ────────────────────────────────────────
class VlaRuntimeError(RuntimeError):
    pass


def bc_record_extras(*, terminal_kind: str, truncated_by_timelimit: bool, bc_eligible: bool,
                     representation_version: str) -> dict[str, Any]:
    """裁定 83§5② 硬约束①：BC 侧**必须**随记录附带的 timeout 溯源字段。

    **为什么不直接加在 `TrainingView` 上**：`TrainingView` 定义在 `harness/contracts.py:40`（**冻结面**，
    sha `96c99ead93d2`，一个字节不动）⇒ A2 不改它，改由 runtime 侧产出这组字段，
    下游（`harness/data_bridge.py` 的 `SAMPLE_COLUMNS`，**不是 A2 的文件**）接入时必须带上；
    缺字段由 `validate_bc_timeout_record()` 判死，不靠人自觉。
    """
    return {
        "truncated_by_timelimit": bool(truncated_by_timelimit),
        "timeout_isolation_scope": TIMEOUT_ISOLATION_SCOPE,
        "bc_kept_flagged": bool(truncated_by_timelimit and bc_eligible and not TIMEOUT_ISOLATES_BC),
        "td_isolated_by_timeout": bool(truncated_by_timelimit and TIMEOUT_ISOLATES_TD),
        "terminal_kind": terminal_kind,
        "must_not_be_labelled_as": (("success", "terminated") if truncated_by_timelimit else ()),
        "representation_version": representation_version,
        "ruling": TIMEOUT_RULING,
        "v4_basis": TIMEOUT_V4_BASIS,
    }


def validate_bc_timeout_record(record: Mapping[str, Any]) -> None:
    """裁定 83§5② 硬约束①的牙：`terminal_kind="timeout"` 的 BC 记录**必须**带 `truncated_by_timelimit=True`。

    `TIMEOUT_ISOLATES_BC=False` 之后，timeout 局的 BC 资格是**「保留但打标」**，不是「保留且无痕」。
    没有这个标，下游就分不清"环境真终止"与"到 300 步 / 10.2 s 被 TimeLimit 剪断"
    ⇒ 等于把删失当完整经验，正是 v4 附录一 `:241`「非终局超时不冒充 `done=1`」要防的事。
    """
    if record.get("terminal_kind") != "timeout":
        return
    if record.get("truncated_by_timelimit") is not True:
        raise VlaRuntimeError(
            f"BC 记录 terminal_kind=timeout 但 truncated_by_timelimit="
            f"{record.get('truncated_by_timelimit')!r}（裁定 83§5② 硬约束①：保留 timeout 轨迹必须打标；"
            "v4 附录一 aae20ffe604f/433ln/:241「非终局超时不冒充 done=1」）")


def validate_truncation_not_terminal(record: Mapping[str, Any]) -> None:
    """裁定 83§5② 硬约束③的牙：截断末帧**不得**被当成「成功」或「终止」标签。

    输入级变异体（验证脚本 G18）= 把 `truncated_by_timelimit=True` 的记录同时写上
    `terminated=True` / `success_label=True` / `done=True`，或把 `terminal_kind` 改成
    `"success"`/`"terminated"` ⇒ **必须抛**。这条牙存在的理由：`td_only` 把 BC 数据放回来了，
    放回来的数据若被下游当"完整成功局"用，就等于用删失轨迹教策略"任务在 10.2 s 处会成功"。
    """
    if record.get("truncated_by_timelimit") is not True:
        return
    bad = [k for k in ("terminated", "success_label", "done", "is_terminal") if record.get(k) is True]
    if record.get("terminal_kind") in ("success", "terminated"):
        bad.append(f"terminal_kind={record.get('terminal_kind')}")
    if bad:
        raise VlaRuntimeError(
            f"truncated_by_timelimit=True 的记录被当成终止/成功：{bad}（裁定 83§5② 硬约束③；"
            "v4 附录一 aae20ffe604f/:332(T12)「不用 done=1 伪终止」、异步附录 a6ab42165ab3/:235"
            "「不能因为后来拿到成功标签，就追认成合法 terminal 样本」）")


class ChunkedVlaRuntime:
    """固定时间槽 + 显式动作队列的 chunk 循环（附录二 §2.1）。

    **每个绝对帧只采纳一个来源**；`activate` 前必须已 `commit`（沿用 `contracts.py:77` 的牙）。
    """

    def __init__(self, policy: VlaChunkPolicy, env: EnvAdapter, *,
                 episode_id: str, goal_id: str, epoch: int = 0,
                 n_replan: int = MAINLINE_N_REPLAN, dt_s: float = MAINLINE_DT_S,
                 late_policy: str = MAINLINE_LATE_POLICY, prime_mode: str = "hold",
                 ledger: FactLedger | None = None, shim_sha256_12: str = "unspecified",
                 async_overlap: bool = False,
                 exec_mode: str = EXEC_MODE_HARNESS_SECOND_HALF,
                 on_event: Callable[[ActionEvent | OutcomeEvent], None] | None = None,
                 cotenant_sampler: Callable[[], dict[str, Any]] | None = None,
                 cotenant_sample_interval_s: float = 2.0,
                 max_episode_steps: int = MAINLINE_MAX_EPISODE_STEPS):
        if late_policy not in ("hold", "extend", "terminate"):
            raise VlaRuntimeError(f"unknown late_policy: {late_policy}（裁定 65-3 只允许这三态）")
        if exec_mode not in EXEC_MODES:
            raise VlaRuntimeError(f"unknown exec_mode: {exec_mode!r}，合法集合 {EXEC_MODES}（裁定 95.3-④）")
        if prime_mode not in PRIME_MODES:
            raise VlaRuntimeError(f"unknown prime_mode: {prime_mode}（合法 {PRIME_MODES}）")
        # ── 裁定 95.3-④ 的**互锁**：两种执行语义不许静默混搭（让混搭不可表达，不是混搭后告警）──
        if exec_mode == EXEC_MODE_STANDARD_SYNC:
            if prime_mode != PRIME_MODE_NONE:
                raise VlaRuntimeError(
                    f"exec_mode='standard_sync' 与 prime_mode={prime_mode!r} **不可共存**：标准同步执行的"
                    "定义就是「推理完立刻执行 idx 0」⇒ 帧 0..n-1 有源、不存在 priming。给它配 prime hold "
                    "= 把裁定 95.3-④ 要绕开的**状态对齐**问题又装回来")
            if not (1 <= n_replan <= policy.chunk_size):
                raise VlaRuntimeError(
                    f"standard_sync 要求 1 ≤ n_replan({n_replan}) ≤ H({policy.chunk_size})："
                    "执行的是 chunk 的**前** n_replan 项，n>H 就是无源可执行（不许静默截断）")
        else:
            if prime_mode == PRIME_MODE_NONE:
                raise VlaRuntimeError(
                    "prime_mode='none' **只**与 exec_mode='standard_sync' 合法搭配："
                    "harness_second_half 的帧 0..n-1 由上一代供给、t=0 无源 ⇒ 必须有 priming 语义")
            if policy.chunk_size < 2 * n_replan:
                # v4 附录一 :103 的 H≥2n；不满足就不是"已实现异步动作调度"（:345 T25）
                raise VlaRuntimeError(
                    f"H≥2n 不成立：chunk_size={policy.chunk_size} < 2*n_replan={2 * n_replan}"
                    " ⇒ 出厂 n=H 的配置必须降 n（裁定 65-1）")
        self.policy, self.env = policy, env
        self.episode_id, self.goal_id, self.epoch = episode_id, goal_id, epoch
        self.n_replan, self.dt_s, self.late_policy, self.prime_mode = n_replan, dt_s, late_policy, prime_mode
        self.exec_mode = exec_mode
        self.ledger, self.shim_sha256_12, self.async_overlap = ledger, shim_sha256_12, async_overlap
        # 裁定 83§5②：`finalize()` 产出的 BC 溯源字段挂在这里（`TrainingView` 是冻结面、加不了字段）
        self.last_bc_record_extras: dict[str, Any] = {}
        # S4b（T-A2-6 · 裁定 93）：四类判定的**待写入** payload 与**已写入**结论。
        # `_pending_s4b_payload` 只在 `finalize_from_env_judgment()` 内部短暂存在，
        # 目的是让 `finalize()` 发的那**唯一一条** `episode_end` 带上四类结论（不发第二条，避免重复计数）。
        self._pending_s4b_payload: dict[str, Any] | None = None
        self.last_s4b_outcome: Any = None
        self.on_event = on_event or (lambda ev: None)
        self.max_episode_steps = max_episode_steps
        self.frame = 0
        self._in_hold = False
        self._hold_run = 0
        self.generation = -1                 # 已 committed 的最新代际；-1 = 尚无
        self.chunks: dict[int, ActionChunk] = {}
        self.committed_generations: set[int] = set()
        self.contract_events: list[ActionEvent | OutcomeEvent] = []
        self.frame_facts: list[dict[str, Any]] = []
        self.schedule_events: list[dict[str, Any]] = []
        self.late_records: list[dict[str, Any]] = []
        # 标准同步执行**不会**因迟到而丢帧（推理阻塞控制环、仿真时间不推进）⇒ 超预算只是
        # 「墙钟超载」这一条软约束事实（裁定 75.4），单列记账，**不进 `late_records`**
        # （进了就会触发 `_resolve_frame` 的迟到处置 = 把动作丢掉，那是另一种执行语义）。
        self.sync_overload_records: list[dict[str, Any]] = []
        self.isolation_reasons: list[str] = []
        self._rep_version: str | None = None
        self.stats_version_at_reset: str | None = None
        self.policy_version_at_reset: str | None = None
        self._vision_guard_fired = False
        # ---- 裁定 75.5 的「异步最小证据」承载槽（S4a 骨架**必须含**）----
        self.queue_drain_events: list[dict[str, Any]] = []
        self.cotenant_samples: list[dict[str, Any]] = []
        self.cotenant_sampler = cotenant_sampler
        self.cotenant_sample_interval_s = float(cotenant_sample_interval_s)
        self.n_control_frames = 0
        self._wall_env_s = 0.0            # env.apply() 累计（物理 + env 自己的渲染）
        self._wall_observe_s = 0.0        # env.observe() 累计（A2 侧三相机渲染）
        self._wall_infer_s = 0.0          # policy.select_chunk() 累计（= Σ chunk.inference_wall_s）
        self._wall_cotenant_s = 0.0       # 采样器自身开销（**单列**，否则它会藏进 other 里）
        self._t_start: float | None = None
        self._t_last: float | None = None
        self._t_last_cotenant: float | None = None
        self._guard_stats_version()

    # ---------- 版本三件套 ----------
    @property
    def representation_version(self) -> str:
        if self._rep_version is None:
            self._rep_version = representation_version(
                dt_s=self.dt_s, n_replan=self.n_replan, chunk_size=self.policy.chunk_size,
                late_policy=self.late_policy, prime_mode=self.prime_mode,
                policy_version=self.policy.policy_version, stats_version=self.policy.stats_version,
                shim_sha256_12=self.shim_sha256_12, render_backend=self.env.render_backend(),
                async_overlap=self.async_overlap, exec_mode=self.exec_mode)
        return self._rep_version

    def manifest_caliber(self) -> dict[str, Any]:
        """裁定 65-2 的四条强制字段（缺一即红）+ 跨口径并列标记。"""
        return {
            "control_hz": round(self.env.control_hz, 6),
            "control_dt_s": self.dt_s,
            "max_episode_steps": self.max_episode_steps,
            "episode_horizon_s": round(self.max_episode_steps * self.dt_s, 4),
            "published_gym_aloha_caliber": PUBLISHED_GYM_ALOHA_CALIBER,
            "not_comparable_horizon": ("与 50 Hz 生态的 300 步/6.0 s 数字**不得按步数并列**"
                                       "（裁定 58.3 / 65-2）；并列时必须标 `not_comparable_horizon`"),
            "morphology": MORPHOLOGY,
            "env_id": ENV_ID,
            "n_replan": self.n_replan,
            "chunk_size": self.policy.chunk_size,
            "h_ge_2n": self.policy.chunk_size >= 2 * self.n_replan,
            "late_policy": self.late_policy,
            "prime_mode": self.prime_mode,
            "exec_mode": self.exec_mode,
            "exec_mode_caliber": EXEC_MODE_CALIBER.get(self.exec_mode),
            "executed_index_segment": ("[0,n)" if self.exec_mode == EXEC_MODE_STANDARD_SYNC else "[n,2n)"),
            "h_ge_2n_required_by_this_exec_mode": bool(
                EXEC_MODE_CALIBER.get(self.exec_mode, {}).get("requires_h_ge_2n")),
            "cross_mode_transplant_ban": EXEC_MODE_CALIBER["cross_mode_transplant_ban"],
            "timeout_isolation_scope": TIMEOUT_ISOLATION_SCOPE,
            "timeout_bc_token": TIMEOUT_BC_TOKEN,
            "async_overlap": self.async_overlap,
            "representation_version": self.representation_version,
            "contract_version": CONTRACT_VERSION,
            "render_backend": list(self.env.render_backend()),
        }

    def _guard_stats_version(self) -> None:
        """§3.1 的牙：`stats_version == "NONE"` ⇒ **拒绝进入评测/训练**并写 `isolation_reasons`。

        这正是 G3 `0/20` 的根因（`normalizer_processor.config.features={}` ⇒ 静默 pass-through）
        ⇒ **不许再让它静默通过**。注意：这里**不抛异常**（S4a 仍要能采结构证据），
        而是**硬隔离**：`td_eligible=bc_eligible=False` + 记原因 + 发账本事件。
        """
        sv = getattr(self.policy, "stats_version", None)
        if sv in (None, "", STATS_VERSION_ABSENT):
            reason = f"stats_version={sv!r}（缺 normalizer stats ⇒ 状态通道饱和，动作量纲不可信）"
            if reason not in self.isolation_reasons:
                self.isolation_reasons.append(reason)
            self._event("verdict_identity_absent", payload={"guard": "stats_version", "value": sv,
                                                             "effect": "td_eligible=bc_eligible=False"})
        self.stats_version_at_reset = sv
        # 版本快照：`representation_version` 是**首次访问时**用当时的 policy 版本算出并缓存的，
        # 若 policy 在 episode 中途换版本，缓存就成了谎报 ⇒ 必须在 commit 处对快照比对（附录一 :279）。
        self.policy_version_at_reset = getattr(self.policy, "policy_version", None)

    def _guard_vision_channels(self, obs: "ObsBundle", *, where: str) -> None:
        """视觉通道守卫：`obs.images` 缺键 ⇒ **硬隔离**，绝不静默退化成状态输入。

        与 `_guard_stats_version` 对称：**不抛异常**（S4a 仍要能采结构证据），
        而是记 `isolation_reasons` + 发**既有词表**事件 `verdict_identity_absent`
        （不新造 kind，裁定 65-6），并把 `td_eligible=bc_eligible` 压成 False。
        每 episode 只发一次事件（去重），但原因串会写清缺了哪些键。
        """
        keys = tuple(sorted((obs.images or {}).keys()))
        missing = tuple(k for k in REQUIRED_IMAGE_KEYS if k not in keys)
        if not missing:
            return
        reason = (f"vision_channel_absent: 缺必需图像键 {list(missing)}（实到 {list(keys)}，"
                  f"来源 {where}）⇒ 拒绝把状态输入冒充视觉输入（G3 0/20 的同型根因）")
        if reason not in self.isolation_reasons:
            self.isolation_reasons.append(reason)
        if not self._vision_guard_fired:
            self._vision_guard_fired = True
            self._event("verdict_identity_absent",
                        payload={"guard": "image_keys", "missing": list(missing), "present": list(keys),
                                 "observed_at": where, "required": list(REQUIRED_IMAGE_KEYS),
                                 "effect": "td_eligible=bc_eligible=False"})

    # ---------- 写入面（两套词表，都不新造值）----------
    def _emit_contract(self, ev: ActionEvent | OutcomeEvent) -> None:
        if isinstance(ev, ActionEvent) and ev.kind not in CONTRACT_EVENT_KINDS:
            raise VlaRuntimeError(f"unknown contract event kind: {ev.kind}")
        self.contract_events.append(ev)
        self.on_event(ev)

    def _event(self, kind: str, *, request_id: str | None = None, abs_frame: int | None = None,
               deadline: int | None = None, lease_generation: int | None = None,
               payload: Any = None) -> None:
        rec = {"kind": kind, "request_id": request_id, "abs_frame": abs_frame, "epoch": self.epoch,
               "goal_id": self.goal_id, "deadline": deadline, "lease_generation": lease_generation,
               "payload": payload}
        self.schedule_events.append(rec)
        if self.ledger is not None:
            self.ledger.append_event(episode_id=self.episode_id, kind=kind, request_id=request_id,
                                     abs_frame=abs_frame, epoch=self.epoch, goal_id=self.goal_id,
                                     deadline=deadline, lease_generation=lease_generation, payload=payload)

    def _frame(self, *, abs_frame: int, source: str, execution_status: str, request_id: str | None,
               chunk_id: str | None, chunk_index: int | None, lease_generation: int,
               proposed_action: Any, a_rl: Any, driver_command: Any, measured_state: Any,
               obs_ref: str | None = None, payload: Any = None) -> int | None:
        if source not in FRAME_SOURCES:
            raise VlaRuntimeError(f"unknown frame source: {source}（词表 ledger.py:39）")
        if execution_status not in EXECUTION_STATUS:
            raise VlaRuntimeError(f"unknown execution status: {execution_status}（词表 ledger.py:40）")
        rec = {"abs_frame": abs_frame, "source": source, "execution_status": execution_status,
               "request_id": request_id, "chunk_id": chunk_id, "chunk_index": chunk_index,
               "lease_generation": lease_generation, "policy_version": self.policy.policy_version,
               "obs_ref": obs_ref, "payload": payload}
        self.frame_facts.append(rec)
        if self.ledger is not None:
            return self.ledger.append_frame(
                episode_id=self.episode_id, abs_frame=abs_frame, goal_id=self.goal_id, epoch=self.epoch,
                lease_generation=lease_generation, source=source, execution_status=execution_status,
                abs_time_ns=time.time_ns(), request_id=request_id, chunk_id=chunk_id,
                chunk_index=chunk_index, proposed_action=proposed_action, a_rl=a_rl,
                driver_command=driver_command, measured_state=measured_state,
                policy_version=self.policy.policy_version, obs_ref=obs_ref, payload=payload)
        return None

    # ---------- 生命周期 ----------
    def reset(self, seed: int) -> ObsBundle:
        self.policy.reset(seed)
        obs = self.env.reset(seed)
        self.frame = obs.frame
        self.generation = -1
        self.chunks, self.committed_generations = {}, set()
        self._guard_stats_version()
        self._vision_guard_fired = False
        self._guard_vision_channels(obs, where="env.reset")
        self.queue_drain_events, self.cotenant_samples = [], []
        self.sync_overload_records = []          # 与 `late_records` 的处置**刻意不同**：见字段注释
        self.n_control_frames = 0
        self._wall_env_s = self._wall_observe_s = self._wall_infer_s = self._wall_cotenant_s = 0.0
        self._t_start = self._t_last = time.perf_counter()
        self._t_last_cotenant = None
        self._event("prime", abs_frame=self.frame, lease_generation=None,
                    payload={"prime_mode": self.prime_mode, "seed": seed, "exec_mode": self.exec_mode,
                             "note": ("t=0 无「已承诺的真实命令队列」⇒ C 槽无源（附录二 §1）"
                                      if self.exec_mode == EXEC_MODE_HARNESS_SECOND_HALF else
                                      "**标准同步执行无 priming**（裁定 95.3-④）：帧 0..n-1 由第 0 代"
                                      "直接供给 ⇒ 本事件只登记 seed 与执行语义，不产生任何 hold 帧")})
        return obs

    def _request_and_commit(self, obs: ObsBundle, generation: int) -> ActionChunk:
        """一个 chunk 的完整生命周期：requested → accepted → committed（附录一 :375 的三阶段分别记录）。"""
        self._guard_vision_channels(obs, where=f"policy_input@g{generation}")
        t = obs.frame
        request_id = f"{self.episode_id}:g{generation}:t{t}"
        deadline_frame = t + self.n_replan                 # **绝对帧**（§3.4：单位写死）
        deadline_s = self.n_replan * self.dt_s
        req = DecisionRequest(request_id=request_id, epoch=self.epoch, goal_id=self.goal_id,
                              observation={"frame": t, "goal_id": obs.goal_id,
                                           "image_keys": sorted(obs.images.keys()),
                                           "state_dim": int(len(obs.state))},
                              policy=self.policy.policy_version, version=self.representation_version,
                              slot=generation, frame=t, deadline=deadline_frame)
        self._emit_contract(ActionEvent(request_id, "requested", self.epoch, self.goal_id, t,
                                        QueueState(), requested=req))
        self._event("request_received", request_id=request_id, abs_frame=t, deadline=deadline_frame,
                    lease_generation=generation, payload={"slot": generation})
        # accepted：承认"前 n 项本次不执行"（附录一 :107），**此刻不写 activated**
        self._emit_contract(ActionEvent(request_id, "accepted", self.epoch, self.goal_id, t, QueueState(),
                                        accepted=(self.n_replan, self.policy.chunk_size)))
        self._event("request_admitted", request_id=request_id, abs_frame=t, deadline=deadline_frame,
                    lease_generation=generation,
                    payload={"accepted": [self.n_replan, self.policy.chunk_size]})

        t0 = time.perf_counter()
        chunk = self.policy.select_chunk(obs)
        wall = time.perf_counter() - t0
        overrides: dict[str, Any] = {
            "inference_wall_s": (chunk.inference_wall_s if chunk.inference_wall_s is not None else wall),
            "request_id": request_id, "deadline_frame": deadline_frame,
            "deadline_s": deadline_s, "chunk_index": generation,
            "lease_generation": generation, "created_at_frame": t,
            "epoch": self.epoch, "representation_version": self.representation_version,
            # ── 裁定 95.3-④：**执行语义由运行时盖章**，不由策略自述 ──
            "exec_mode": self.exec_mode, "slots_restamped_by_runtime": False,
        }
        if self.exec_mode == EXEC_MODE_STANDARD_SYNC:
            # 为什么要重盖槽位：既有策略侧实现（S4a 的 stub、S4b 的 π₀.₅ 包装）都按 v4 附录二给
            # `slot_e=[n,2n)`；标准同步执行的是 idx **[0,n)** ⇒ 不重盖就会「idx 不在 slot_e」而误判无源。
            # **策略只提议动作，槽位归属是运行时的语义**：这也让「策略谎报槽位」不可能改变执行行为。
            n_, h_ = self.n_replan, self.policy.chunk_size
            overrides.update({"slot_c": (), "slot_e": tuple(range(0, n_)),
                              "slot_d": tuple(range(n_, h_)), "slots_restamped_by_runtime": True})
        chunk = ActionChunk(**{**chunk.__dict__, **overrides})
        # 版本在 chunk 内必须恒定（附录一 :279「不能在一个正在执行的 chunk 内悄悄换模型或 normalizer」）。
        # **双比对**：只比 chunk vs 当前 policy 是不够的——若 policy 在 select_chunk 内部先改自己的
        # 版本号再返回 chunk，两者仍然相等、检查形同虚设（S4a 闸 G10 就是这样假绿的）。
        # 因此还要比「当前 policy vs reset 时快照」，任何一侧漂移都报错。
        live_pv, live_sv = self.policy.policy_version, self.policy.stats_version
        if live_pv != self.policy_version_at_reset or live_sv != self.stats_version_at_reset:
            raise VlaRuntimeError(
                f"episode 中途换版本（附录一 :279 禁止）：policy_version {self.policy_version_at_reset!r}"
                f"→{live_pv!r}、stats_version {self.stats_version_at_reset!r}→{live_sv!r}"
                " ⇒ 已缓存的 representation_version 会谎报口径，必须新开 episode")
        if chunk.policy_version != live_pv or chunk.stats_version != live_sv:
            raise VlaRuntimeError(
                f"chunk 内 policy_version/stats_version 与 policy 不一致（附录一 :279 禁止）："
                f"chunk=({chunk.policy_version!r},{chunk.stats_version!r}) vs policy=({live_pv!r},{live_sv!r})")
        if chunk.actions.shape[0] != self.policy.chunk_size:
            raise VlaRuntimeError(f"chunk 长度 {chunk.actions.shape[0]} != H {self.policy.chunk_size}")
        if chunk.inference_wall_s is not None:
            self._wall_infer_s += float(chunk.inference_wall_s)
        self.chunks[generation] = chunk
        self.committed_generations.add(generation)
        q = QueueState(c=tuple(f"C{i}" for i in chunk.slot_c), e=tuple(f"E{i}" for i in chunk.slot_e),
                       d=tuple(f"D{i}" for i in chunk.slot_d),
                       c_frame=t, e_frame=t + self.n_replan, d_frame=t + 2 * self.n_replan)
        self._emit_contract(ActionEvent(request_id, "committed", self.epoch, self.goal_id, t, q,
                                        committed={"chunk_id": chunk.chunk_id, "H": self.policy.chunk_size,
                                                   "slot_c": list(chunk.slot_c)[:3],
                                                   "slot_e": list(chunk.slot_e)[:3],
                                                   "slot_d_len": len(chunk.slot_d)}))
        self._event("result_committed", request_id=request_id, abs_frame=t, deadline=deadline_frame,
                    lease_generation=generation,
                    payload={"chunk_id": chunk.chunk_id, "inference_wall_s": chunk.inference_wall_s,
                             "slot_budget_s": deadline_s,
                             "late": bool(chunk.inference_wall_s > deadline_s)})
        self.generation = generation
        # C/D 两段索引**不产生物理动作** ⇒ 立刻记 not_activated（不许伪装成已执行，附录一 :81/:83）
        for idx in tuple(chunk.slot_c) + tuple(chunk.slot_d):
            seg = "C" if idx in chunk.slot_c else "D"
            self._frame(abs_frame=t + idx, source="policy", execution_status="not_activated",
                        request_id=request_id, chunk_id=chunk.chunk_id, chunk_index=idx,
                        lease_generation=generation,
                        proposed_action=self._row(chunk, idx), a_rl=None, driver_command=None,
                        measured_state=None,
                        payload={"segment": seg, "why": ("C：这些绝对帧由上一代执行（附录二 §1）" if seg == "C"
                                                         else "D：被下一代替换")})
        return chunk

    def _row(self, chunk: ActionChunk, idx: int):
        try:
            return [float(x) for x in chunk.actions[idx]]
        except Exception:
            return None

    def _record_late_frame(self, abs_frame: int, chunk: ActionChunk | None, hold_action: Any,
                           measured_state: Any, choice: str) -> None:
        """裁定 65-3③：**迟到帧不得被重标为 `activated`**；异常事实保留。"""
        self._frame(abs_frame=abs_frame, source="hold", execution_status="not_activated",
                    request_id=(chunk.request_id if chunk else None),
                    chunk_id=(chunk.chunk_id if chunk else None),
                    chunk_index=(abs_frame - chunk.created_at_frame if chunk else None),
                    lease_generation=(chunk.lease_generation if chunk else self.generation),
                    proposed_action=None, a_rl=None, driver_command=hold_action,
                    measured_state=measured_state,
                    payload={"late_policy": self.late_policy, "late_choice": choice,
                             "reason": "deadline_miss",
                             "rule": "异常事实保留，不重标成\"准时\"（附录一 :111 / 裁定 65-3③）"})

    def step(self) -> StepResult:
        """推进**一个绝对控制帧**。只有跨越 `n_replan` 边界才发起新请求（附录二 §2.1）。"""
        f = self.frame
        # 1) 槽边界：发起第 g 代请求（g = f // n）
        g = f // self.n_replan
        if g not in self.committed_generations:
            _to = time.perf_counter()
            obs = self.env.observe(f)
            self._wall_observe_s += time.perf_counter() - _to
            chunk = self._request_and_commit(obs, g)
            if chunk.inference_wall_s is not None and chunk.inference_wall_s > chunk.deadline_s:
                if self.exec_mode == EXEC_MODE_STANDARD_SYNC:
                    # **标准同步执行不因超预算丢帧**：推理阻塞控制环、仿真时间在推理期间不推进
                    # ⇒ 没有"过期的槽"可作废。超预算只是墙钟软约束事实（裁定 75.4：不判硬失败）。
                    # 刻意**不进 `late_records`**：进了就会让 `_resolve_frame` 走迟到处置 = 换执行语义。
                    self.sync_overload_records.append({
                        "generation": g, "frame": f, "exec_mode": self.exec_mode,
                        "inference_wall_s": chunk.inference_wall_s, "deadline_s": chunk.deadline_s,
                        "over_budget_fraction": round(float(chunk.inference_wall_s)
                                                      / max(1e-9, float(chunk.deadline_s)), 4),
                        "frames_discarded": 0,
                        "contract_event_emitted": None,
                        "why_no_expired_event": ("`expired` 的语义是「结果没赶上它所属的槽」；同步阻塞下"
                                                 "不存在这个事实 ⇒ 不发（不新造 kind，裁定 65-6）"),
                        "ruling": "裁定 75.4（软约束）+ 95.3-④（标准同步执行）"})
                else:
                    # 迟到：本代 E 段整体作废，按 late_policy 处置
                    self.late_records.append({"generation": g, "frame": f,
                                              "inference_wall_s": chunk.inference_wall_s,
                                              "deadline_s": chunk.deadline_s,
                                              "late_policy": self.late_policy})
                    self._emit_contract(ActionEvent(chunk.request_id, "expired", self.epoch, self.goal_id, f,
                                                    QueueState(), expired=True, reason="deadline_miss"))
                    self._event("expired", request_id=chunk.request_id, abs_frame=f,
                                deadline=chunk.deadline_frame, lease_generation=g,
                                payload={"inference_wall_s": chunk.inference_wall_s,
                                         "deadline_s": chunk.deadline_s, "late_policy": self.late_policy})
        # 2) 决定这一帧的命令来源
        owner_g, idx, source, status, late_choice, hold_reason = self._resolve_frame(f)
        chunk = self.chunks.get(owner_g) if owner_g is not None else None
        # **队列枯竭**：这一帧本该由已承诺队列供给命令、却没有 ⇒ 记一条 drain。
        # priming 期间的 hold **不算枯竭**（那是 t=0 无源的既定语义，`prime_mode` 管的事），
        # 否则每集开头 n 帧都会污染这个指标、让它失去"队列够不够吃"的含义。
        if source == "hold" and hold_reason != "prime":
            self.queue_drain_events.append({
                "abs_frame": f, "generation": owner_g, "reason": hold_reason,
                "chunk_index": idx, "late_policy": self.late_policy, "late_choice": late_choice,
                "committed_generations_at_that_moment": sorted(self.committed_generations),
                "ledger_event_kind_used": ("expired" if hold_reason == "late" and chunk is not None
                                           and any(r["generation"] == owner_g for r in self.late_records)
                                           else "hold_start"),
                "vocabulary_note": "**不新造 kind**：枯竭事实由既有 `hold_start`/`expired` 承载（ledger.py:31-40）",
            })
        if source == "policy" and chunk is not None:
            action = self._row(chunk, idx)
            proposed = action
        else:
            action = self.env.hold_action() if hasattr(self.env, "hold_action") else None
            proposed = None
        if action is None:
            raise VlaRuntimeError(f"frame {f}: 无可执行命令（source={source}）—— 不许静默填 0")
        _ta = time.perf_counter()
        reward, terminated, truncated, info = self.env.apply(action)
        self._wall_env_s += time.perf_counter() - _ta
        self.n_control_frames += 1
        self._t_last = time.perf_counter()
        self._maybe_sample_cotenant(f)
        self._frame(abs_frame=f, source=source, execution_status=status,
                    request_id=(chunk.request_id if chunk else None),
                    chunk_id=(chunk.chunk_id if chunk else None), chunk_index=idx,
                    lease_generation=(chunk.lease_generation if chunk else (owner_g if owner_g is not None else -1)),
                    proposed_action=proposed, a_rl=(proposed if source == "policy" else None),
                    driver_command=action, measured_state=info.get("qpos"),
                    obs_ref=info.get("obs_ref"),
                    payload={"late_choice": late_choice, "hold_reason": hold_reason,
                             "slot": ("E" if source == "policy" else source)})
        self._emit_contract(ActionEvent((chunk.request_id if chunk else f"{self.episode_id}:frame{f}"),
                                        "activated", self.epoch, self.goal_id, f,
                                        QueueState(c=(), e=(str(idx),), d=(), e_frame=f),
                                        activated=True))
        self._event("physical_activated", request_id=(chunk.request_id if chunk else None),
                    abs_frame=f, lease_generation=(chunk.lease_generation if chunk else None),
                    payload={"source": source, "chunk_index": idx, "late_choice": late_choice})
        in_hold = (source == "hold")
        if in_hold and not self._in_hold:
            self._event("hold_start", abs_frame=f, lease_generation=(chunk.lease_generation if chunk else None),
                        payload={"hold_reason": hold_reason, "late_choice": late_choice,
                                 "late_policy": self.late_policy})
        elif (not in_hold) and self._in_hold:
            self._event("hold_end", abs_frame=f, lease_generation=(chunk.lease_generation if chunk else None),
                        payload={"hold_reason": "returned_to_policy", "held_frames": self._hold_run})
        self._in_hold = in_hold
        self._hold_run = (self._hold_run + 1) if in_hold else 0
        if late_choice == "terminate":
            self._event("recovery", abs_frame=f, lease_generation=(chunk.lease_generation if chunk else None),
                        payload={"late_choice": "terminate", "late_policy": self.late_policy})
        self.frame = f + 1
        return StepResult(abs_frame=f, action=action, source=source, execution_status=status,
                          chunk_id=(chunk.chunk_id if chunk else None), chunk_index=idx,
                          lease_generation=(chunk.lease_generation if chunk else -1),
                          request_id=(chunk.request_id if chunk else None), late_choice=late_choice,
                          reward=float(reward), terminated=bool(terminated), truncated=bool(truncated),
                          info=dict(info))

    def _resolve_frame(self, f: int) -> tuple[int | None, int | None, str, str, str | None, str | None]:
        """返回 `(owner_generation, chunk_index, source, execution_status, late_choice, hold_reason)`。
        `hold_reason ∈ {"prime","late",None}` —— **priming 与迟到必须分开记**（两者的异常语义不同）。

        **每个绝对帧只采纳一个来源**（附录一 :115）。规则：
        - 帧 `f` 属于第 `g = f//n` 槽；能执行的是**上一代** `g-1` 的 E 段，索引 `idx = f - (g-1)·n`，
          条件 `idx ∈ [n, 2n)`（等价于 `f ∈ [(g-1)·n + n, (g-1)·n + 2n)`）。
        - `g-1` 未 committed、或它已判迟到 ⇒ 按 `late_policy` 处置（`hold` = 保持合法动作，**不回填过期索引**）。
        - `g == 0`（priming）⇒ 按 `prime_mode`。
        """
        n = self.n_replan
        g = f // n
        if self.exec_mode == EXEC_MODE_STANDARD_SYNC:
            # ── 裁定 95.3-④：标准同步执行 = 「在 f=t_g 推理，立刻执行本代 idx 0..n-1」──
            # 与 harness_second_half 的三处**语义差**（每一处都是可核的机器事实）：
            #   ① 供给者 = **本代 g**（不是上一代 g-1）⇒ 不存在 priming，帧 0 就有源；
            #   ② 执行的索引 = `idx = f - t_g ∈ [0, n)`（不是 [n, 2n)）；
            #   ③ 没有"迟到作废"这条路径（推理阻塞 ⇒ 见 `step()` 的 `sync_overload_records`）。
            chunk = self.chunks.get(g)
            if chunk is None:
                raise VlaRuntimeError(
                    f"frame {f}: standard_sync 下第 {g} 代 chunk 缺失 ⇒ 这是结构性 bug"
                    "（`step()` 在同一帧先请求再执行）。**不许静默退化成 hold**：hold 就是"
                    "裁定 95.3-④ 要绕开的那个状态对齐问题的来源")
            idx = f - chunk.created_at_frame
            if idx not in chunk.slot_e:
                raise VlaRuntimeError(
                    f"frame {f}: idx={idx} 不在本代 slot_e={tuple(chunk.slot_e)[:4]}… ⇒ 槽位盖章与"
                    f"n_replan 不一致（exec_mode={self.exec_mode}）；不许静默换源")
            return g, idx, "policy", "activated", "keep", None
        if g == 0:
            if self.prime_mode == "first_chunk" and 0 in self.committed_generations:
                return 0, f, "policy", "activated", None, None
            return None, None, "hold", "activated", "hold", "prime"
        prev = g - 1
        chunk = self.chunks.get(prev)
        idx = f - chunk.created_at_frame if chunk is not None else None
        late = any(r["generation"] == prev for r in self.late_records)
        if chunk is None or late or idx is None or idx not in chunk.slot_e:
            if self.late_policy == "terminate":
                return prev if chunk else None, idx, "hold", "not_activated", "terminate", "late"
            return prev if chunk else None, idx, "hold", "activated", "hold", "late"
        return prev, idx, "policy", "activated", "keep", None

    def _maybe_sample_cotenant(self, abs_frame: int) -> None:
        """**运行时**采共租证据（裁定 76.3 红线 `cotenant_evidence_must_be_runtime`）。

        事后重建的 `cotenant_evidence` 只能标 `collected_at_run_time=false`（A2 上一轮就是这样被记纪律缺口的）。
        采样按墙钟节流（默认 ≥2 s 一次），并且**把采样器自身的开销单列**——
        否则 `nvidia-smi` 的 ~0.1 s 会藏进 `other` 里，让分解表说谎。
        """
        if self.cotenant_sampler is None:
            return
        now = time.perf_counter()
        if (self._t_last_cotenant is not None
                and (now - self._t_last_cotenant) < self.cotenant_sample_interval_s):
            return
        t0 = time.perf_counter()
        try:
            sample = self.cotenant_sampler() or {}
        except Exception as exc:                      # 采样失败不得打断控制环
            sample = {"sampler_error": f"{type(exc).__name__}: {exc}"}
        self._wall_cotenant_s += time.perf_counter() - t0
        self._t_last_cotenant = time.perf_counter()
        sample = dict(sample)
        sample.setdefault("abs_frame", abs_frame)
        sample.setdefault("sampled_at_wall_s_since_reset",
                          round(self._t_last - self._t_start, 4) if self._t_start else None)
        self.cotenant_samples.append(sample)

    def timing_report(self) -> dict[str, Any]:
        """裁定 75.4 / 75.5 的机器承载：**墙钟分解 + 摊薄推理 + 枯竭 + 软约束标记**。

        三条硬规定（都是 D 的裁定，不是 A2 的措辞选择）：
        - **75.5**：`wall_ms_per_ctrl_step` 与 `amortized_inference_ms` **必须分列**；
          且**异步版未被实测之前，不得声称"实时闭环"** ⇒ `realtime_closed_loop_claim` 恒为 `false`。
        - **75.4**：仿真/离线里 34 ms/步是**软约束** ⇒ `budget_fraction > 1` **不判硬失败**，
          只置 `overload_flag=true` 并按秒登记 `episode_sim_seconds_covered`。
        - **口径**：本实现是**同步阻塞串行环**（推理在关键路径上、与队列消费零重叠）
          ⇒ 关键路径 = 各项**相加**；异步下的关键路径是 `max(env_step, 摊薄推理)`，
          这两个口径**不得互搬**（裁定 46.4 / 53.6 / 71）。
        """
        n = max(1, self.n_control_frames)
        total_s = ((self._t_last - self._t_start) if (self._t_start and self._t_last) else 0.0)
        itemized_s = self._wall_env_s + self._wall_observe_s + self._wall_infer_s + self._wall_cotenant_s
        budget_ms = self.dt_s * 1000.0
        wall_ms = total_s / n * 1000.0
        amort_ms = self._wall_infer_s / n * 1000.0
        frac = wall_ms / budget_ms if budget_ms else None
        drained = len(self.queue_drain_events)
        return {
            "caliber": "synchronous_blocking_serial（推理在关键路径上、与队列消费**零重叠**）",
            "async_overlap": self.async_overlap,
            "exec_mode": self.exec_mode,
            "executed_index_segment": ("[0,n)" if self.exec_mode == EXEC_MODE_STANDARD_SYNC else "[n,2n)"),
            "n_control_frames": self.n_control_frames,
            "n_chunks_committed": len(self.committed_generations),
            "n_replan": self.n_replan, "chunk_size": self.policy.chunk_size,
            # ---- 75.5：**分列** ----
            "wall_ms_per_ctrl_step": round(wall_ms, 3),
            "amortized_inference_ms_per_ctrl_step": round(amort_ms, 3),
            "env_step_ms_per_ctrl_step": round(self._wall_env_s / n * 1000.0, 3),
            "observe_render_ms_per_ctrl_step": round(self._wall_observe_s / n * 1000.0, 3),
            "cotenant_sampling_ms_per_ctrl_step": round(self._wall_cotenant_s / n * 1000.0, 3),
            "unitemized_other_ms_per_ctrl_step": round(max(0.0, total_s - itemized_s) / n * 1000.0, 3),
            "unitemized_other_note": ("**这张分解表不完整，剩项如实单列而不摊进任何一项**：未分解部分 = "
                                      "`_frame()` 的账本写入（SQLite on NFS）+ 契约 dataclass 构造 + "
                                      "`_resolve_frame` + `hold_action()` + reset/finalize 的一次性成本。"
                                      "要把它继续拆需要给这些点也上计时器，**S4a 未做**"),
            "wall_s_total": round(total_s, 4),
            "itemization_sums_to_total": round(itemized_s, 4),
            "per_step_budget_ms": round(budget_ms, 4),
            # ---- 75.4：**软约束**，不判硬失败 ----
            "budget_fraction": (round(frac, 4) if frac is not None else None),
            "overload_flag": bool(frac is not None and frac > 1.0),
            "budget_verdict": ("soft_constraint_not_a_hard_failure（裁定 75.4：S4/S5 仿真离线口径；"
                               "**P4 真机不适用**，真机必须实测达标）"),
            "episode_sim_seconds_covered": round(self.n_control_frames * self.dt_s, 4),
            "episode_horizon_s_mainline": MAINLINE_EPISODE_HORIZON_S,
            # ---- 75.5：队列不枯竭 ----
            "queue_drain_count": drained,
            "queue_never_drained": drained == 0,
            "queue_drain_events": list(self.queue_drain_events),
            "queue_drain_note": ("priming 期间的 hold **不计入枯竭**（那是 t=0 无源的既定语义）；"
                                 "计入的是「本该由已承诺队列供给命令却没有」的帧"),
            # ── 裁定 95.3-④ / 75.4：标准同步执行的超预算事实（**不丢帧**，只登记）──
            "n_sync_overload_chunks": len(self.sync_overload_records),
            "sync_overload_records": list(self.sync_overload_records)[:8],
            "sync_overload_note": ("标准同步执行下推理超 `n×dt` **不作废任何帧**（仿真时间在推理期间"
                                   "不推进）⇒ 这是墙钟软约束事实（裁定 75.4），不是 `expired`"),
            "n_late_records": len(self.late_records),
            # ---- 75.5：运行时 cotenant 采样 ----
            "cotenant_samples": list(self.cotenant_samples),
            "cotenant_collected_at_run_time": bool(self.cotenant_samples),
            "cotenant_sampler_attached": self.cotenant_sampler is not None,
            "cotenant_sampling_interval_s": self.cotenant_sample_interval_s,
            # ---- 75.5：**禁止**在异步实测前声称实时闭环 ----
            "realtime_closed_loop_claim": False,
            "realtime_closed_loop_claim_blocked_because": (
                "异步版尚未实测（`async_overlap=false`）。裁定 75.5：异步最小证据 = 队列不枯竭 + "
                "`wall_ms_per_ctrl_step` 与 `amortized_inference_ms` 分列 + 负载对 + 运行时 cotenant 采样；"
                "本表已具备**同步口径**下的后三项，但"
                "**"
                "同步环的墙钟不能用来声称实时闭环**"),
            "async_evidence_still_missing": [
                "线程/进程重叠执行（推理与队列消费并行）",
                "异步口径下的 `queue_drain_events`（同步环里枯竭只可能由迟到引起）",
                "异步口径下的关键路径 = max(env_step, 摊薄推理)，而非本表的相加",
            ],
            "cross_caliber_transplant_ban": ("本表数字**不得**与 GPU 渲染口径或异步口径互搬"
                                             "（裁定 46.4/53.6/71）；**也不得与另一种 `exec_mode` 互搬**"
                                             "（裁定 95.3-④：「两种执行的数字不得互搬」）"),
            "exec_mode_transplant_ban": EXEC_MODE_CALIBER["cross_mode_transplant_ban"],
        }

    def finalize(self, terminal_kind: str, *, reward: float, observation: ObsBundle | None = None,
                 grasp_verified: bool | None = None, max_rise: float | None = None,
                 failure_phase: str = "") -> TrainingView:
        """真实 outcome（**不复用 `ReplayDriver.finish`**：它把 reward 写死 0.0、source 写死 "mock"）。"""
        if terminal_kind not in ("success", "failure", "timeout", "unknown", "cancel", "takeover",
                                 "deadline_miss", "none", "terminated", "truncated"):
            raise VlaRuntimeError(f"unknown terminal_kind: {terminal_kind}")
        request_id = f"{self.episode_id}:finalize"
        # execution_mask 逐索引（附录一 :83：「而非只有 executed_length」）
        H = self.policy.chunk_size
        mask = [0] * H
        bc_mask = [0] * H
        for rec in self.frame_facts:
            if rec["execution_status"] == "activated" and rec["chunk_index"] is not None:
                mask[rec["chunk_index"] % H] = 1
                if rec["source"] == "policy":
                    bc_mask[rec["chunk_index"] % H] = 1
        base_isolated = list(self.isolation_reasons)
        if terminal_kind in ("cancel", "takeover", "deadline_miss"):
            base_isolated.append(f"terminal_kind={terminal_kind}")
        # timeout 的处置按 td/bc **分别**判：原先把 timeout 塞进 `terminal_kind in (...)` 白名单、
        # 同时又把它写进 `isolated`，两句互相抵消 ⇒ timeout 永远不 TD-eligible，白名单是死字面量。
        # 现在改成两个显式开关，语义只写一次、可被 D 裁定翻转。**裁定 83§5② 已裁 `td_only`**
        # ⇒ `TIMEOUT_ISOLATES_TD=True` / `TIMEOUT_ISOLATES_BC=False`（原 A2 保守默认是两者都 True）。
        to_reason = "terminal_kind=timeout（超时按秒登记，裁定 58.3）"
        is_to = (terminal_kind == "timeout")
        td_isolated = base_isolated + ([to_reason] if (is_to and TIMEOUT_ISOLATES_TD) else [])
        bc_isolated = base_isolated + ([to_reason] if (is_to and TIMEOUT_ISOLATES_BC) else [])
        td_eligible = not td_isolated and terminal_kind in ("success", "failure", "timeout", "none",
                                                            "terminated", "truncated", "unknown")
        bc_eligible = not bc_isolated
        # ── 裁定 83§5② 硬约束①③：BC 侧「保留但打标」，并在 runtime 内部就地自检 ──────────
        # `TrainingView`（contracts.py:40，冻结面）没有这些字段的位置 ⇒ 溯源字段挂在
        # `self.last_bc_record_extras`，下游接数据桥时**必须**带上；缺字段/错标签当场抛，不留给下游。
        truncated_by_timelimit = bool(is_to)
        self.last_bc_record_extras = bc_record_extras(
            terminal_kind=terminal_kind, truncated_by_timelimit=truncated_by_timelimit,
            bc_eligible=bc_eligible, representation_version=self.representation_version)
        if bc_eligible:
            validate_bc_timeout_record(self.last_bc_record_extras)
            validate_truncation_not_terminal(self.last_bc_record_extras)
        isolated = td_isolated + [r for r in bc_isolated if r not in td_isolated]
        self._emit_contract(OutcomeEvent(request_id, self.epoch, self.goal_id, self.frame,
                                         (observation.__dict__ if observation is not None else {}),
                                         float(reward), True, terminal_kind, "env",
                                         self.policy.policy_version, self.representation_version,
                                         "s4a", grasp_verified, max_rise, failure_phase))
        self._event("episode_end", request_id=request_id, abs_frame=self.frame,
                    lease_generation=self.generation,
                    payload={"terminal_kind": terminal_kind, "reward": float(reward),
                             "episode_seconds": round(self.frame * self.dt_s, 4),
                             "grasp_verified": grasp_verified, "max_rise": max_rise,
                             "td_eligible": td_eligible, "bc_eligible": bc_eligible,
                             "truncated_by_timelimit": truncated_by_timelimit,
                             "bc_kept_flagged": bool(self.last_bc_record_extras.get("bc_kept_flagged")),
                             "timeout_isolation_scope": TIMEOUT_ISOLATION_SCOPE,
                             "isolation_reasons": isolated,
                             "td_isolation_reasons": td_isolated, "bc_isolation_reasons": bc_isolated,
                             # S4b（T-A2-6）：四类判定必须能在 `episode_end` 的 payload 里被读到，
                             # 否则"接 ledger"就只是内存里的一句话。非 S4b 路径下这里是 None。
                             "s4b": (dict(self._pending_s4b_payload)
                                     if getattr(self, "_pending_s4b_payload", None) else None)})
        return TrainingView(request_id, self.epoch, self.goal_id, td_eligible, bc_eligible,
                            tuple(mask), tuple(bc_mask), terminal_kind, tuple(isolated), 0.99)

    def design_points_open_to_d(self) -> dict[str, Any]:
        """设计点的**裁定台账**（方法名保留：验证脚本 `:532` / `:1259` 按这个名字读）。

        裁定 83§5 把 A2 报上去的 5 个点**全部裁完** ⇒ 这里不再是「待裁清单」，而是
        「已裁值 + 谁裁的 + 可推翻条件」的台账。**A2 不自决**这条纪律不变：翻任何一项都要 D 的裁定号。
        """
        return {
            "prime_mode": {"value": self.prime_mode, "options": ["hold", "first_chunk"],
                           "status": "ruled_83_5_1",
                           "ruling": ("裁定 83§5① 裁 `hold`，并要求进 `representation_version`"
                                      "（已进：`:prime=` token，见 `representation_version()`）"),
                           "overturnable_if": "S4b 实测首帧 hold 系统性错过抓取窗口 ⇒ 改 `first_chunk` 并**另立版本**",
                           "not_decorative_because": "验证脚本 G13 两案喂同一份产物，行为不同才判绿"},
            "timeout_isolation_scope": {
                "value": TIMEOUT_ISOLATION_SCOPE,
                "constants": {"TIMEOUT_ISOLATES_TD": TIMEOUT_ISOLATES_TD,
                              "TIMEOUT_ISOLATES_BC": TIMEOUT_ISOLATES_BC},
                "rep_version_tokens": {"timeout_td": TIMEOUT_TD_TOKEN, "timeout_bc": TIMEOUT_BC_TOKEN},
                "options": ["both_isolated（A2 原保守默认）", "td_only（**现值**）",
                            "neither（把 TimeLimit 截断当正常收尾）"],
                "status": "ruled_83_5_2__d_selfconfirmed_pending_user_ratification",
                "ruling": ("裁定 83§5② 裁 `td_only`（**D 改 A2 的保守默认**）：TD 侧截断本该 bootstrap ⇒ 隔离保留；"
                           "BC 侧截断轨迹仍是合法经验 ⇒ **保留但打标**"),
                "hard_constraints": [
                    "① BC 记录须带 `truncated_by_timelimit=true`（`validate_bc_timeout_record` 看守）",
                    "② `representation_version` 须含 `timeout_bc=kept_flagged`（token 由常量派生，不能手写）",
                    "③ 不得把 truncated 末帧当「成功／终止」标签（`validate_truncation_not_terminal` 看守）",
                    "④ 须有变异体证明「把 truncated 当 terminal」会红（验证脚本 G18，裁定 83.1）",
                ],
                "overturnable_if": ("v4 原文明确禁止（须给文件-身份三元组 + 行号）⇒ D 立即回退 `both_isolated`。"
                                    "**A2 已按此条件逐条查过 v4：未找到明文禁止**，反找到 4 处正面支撑"
                                    "（见 `v4_basis` 与文件头的表）。**但如实登记一条口径差**：v4 的「超时」"
                                    "多指**槽级**（推理超时／deadline miss／失联），本开关管**回合级** gym "
                                    "TimeLimit ⇒ 属**原则迁移**，A2 不把它放大成「v4 逐字允许」"),
                "v4_basis": TIMEOUT_V4_BASIS,
                "revert_cost": "翻 `TIMEOUT_ISOLATES_BC=True` 一行；`representation_version` 自动变 `timeout_bc=isolated`"},
            "late_policy": {"value": self.late_policy, "options": ["hold", "extend", "terminate"],
                            "status": "ruled_65_3__reaffirmed_83_5_3",
                            "ruling": ("裁定 65-3 裁 `hold`、裁定 83§5③ 维持；它是冻结面语义、进 "
                                       "`representation_version`（依据 v4 附录一 :111）")},
            "async_overlap": {"value": self.async_overlap,
                              "status": "ruled_83_5_4__false",
                              "ruling": ("裁定 83§5④：在 76.4 权威重测 + G17 异步字段跑过真推理之前，"
                                         "**不得声称任何重叠／实时闭环** ⇒ `realtime_closed_loop_claim` 恒 false"),
                              "note": ("76.4 的权威重测 A2 已于 00:2x 完成（4 次 clean 重复，`daily_report.md` §13）；"
                                       "**但 `async_overlap` 仍是 false** ⇒ 实测到的 `realtime_ratio` 是"
                                       "「同步串行环的 control_timestep ÷ wall」，**不构成实时闭环主张**，"
                                       "A2 不因为拿到 1.277× 就改口")},
            "s4b_outcome_judging": {
                "value": ("landed_by_a2__judgment_layer_owned_by_c2"
                          if self.last_s4b_outcome is not None else "wired_awaiting_run"),
                "status": "ruled_93__T_A2_6_landed",
                "ruling": ("裁定 83§5⑤ 曾 `deferred`（前置挂 C2 线）；**裁定 93 / T-A2-6 已解锁并落地**："
                           "前置三步（B2 的 npz、C2 的主线 stats、C2 的 env 判定层）均经 D 亲跑复验。"
                           "接线 = 本文件 `finalize_from_env_judgment()` + `GymAlohaJudgedAdapter`；"
                           "判定层 = C2 的 `harness/env_gym_aloha.py`（A2 **不重算判定**）"),
                "criterion_verbatim": S4B_CRITERION_VERBATIM,
                "judgment_layer_identity": env_gym_aloha_identity(),
                "coupling_tooth": ("`outcome_source` 只接受 `c2_geometric_judgment`；传 `reward==4` 那一档"
                                   "⇒ `OutcomeCouplingError`（让耦合**不可表达**，不是耦合后告警）"),
                "disagreement_tooth": ("`cross_check_verdict` 为 RED、或 `reward4_vs_outcome_agreement is False`"
                                       " ⇒ `S4bOutcome.red=True`；反向任务里 RED 是**预期形态**"
                                       "（env 的 reward 写死右→左），`red_subject` 记 "
                                       "`env_reward_direction_hardcoded`，**RED 不降级**、只写清归因"),
                "not_a_capability_claim": ("裁定 46.6 / 65-6③：S4b 是**契约层**证据，成功率一栏写 "
                                           "`not_an_exit_criterion`；四类分布不构成能力结论"),
                "overturnable_if": ("C2 的判定层 sha256-12 变了（现值见 `judgment_layer_identity`）"
                                    "⇒ 本接线必须重核，不许沿用旧产物"),
            },
        }

    # ══════════════════ S4b（T-A2-6 · 裁定 93）：四类判定接 ledger ══════════════════
    def finalize_from_env_judgment(self, judged_env: Any, *, reward: float | None = None,
                                   observation: "ObsBundle | None" = None,
                                   grasp_verified: bool | None = None,
                                   failure_phase: str = "",
                                   outcome_source: str = OUTCOME_SOURCE_GEOMETRIC,
                                   ledger: Any = None, request_id: str | None = None,
                                   raise_on_disagreement: bool = False) -> "S4bOutcome":
        """**S4b 本体**：四类判定（成功/失败/超时/未知）→ `ledger`，**独立于 `reward==4`**，不一致即红。

        判据原文（不重新解释）：`work/project_parameters.json:1047`
        「S4b（等 C2 的 env）= 四类判定接 `ledger`，独立于 `reward==4`，不一致即红」。

        三件事在这里同时成立，缺一即红：

        1. **独立**：`terminal_kind` / `outcome_class` **只**取自 C2 的 `Judgment.outcome_class`
           （几何真值：目标侧夹住 + 离桌高度 + 连续持稳 k 步 + 速度上限）。`reward` 只作为
           **交叉核验的另一侧**被记录下来，**从不**参与结论的产生。`outcome_source` 参数是牙：
           传 `OUTCOME_SOURCE_REWARD4_FORBIDDEN`（或任何非几何值）⇒ `OutcomeCouplingError`。
        2. **接 ledger**：走 `harness/ledger.py` 的**既有公开 API**（`append_label` / `append_event`），
           四类映射到既有词表（`success`→`label_kind="success",value=1.0`；`failure`/`timeout`→
           `label_kind="success",value=0.0`，细分进 `value_json.outcome_class`；`unknown`→
           `label_kind="unknown",value=None`）—— 这张映射表是 **C2 的 `ledger_label_kwargs()` 拥有的**，
           A2 直接调它，不另写一份（两个位置各写一份口径 = 本仓已发生四次的事故形状）。
        3. **不一致即红**：调 C2 的 `cross_check()`（几何真值 vs `env_is_success`=`reward==4`），
           它在不一致时抛 `JudgmentDisagreement` ⇒ 本方法捕获后记 `cross_check_verdict="RED"`，
           并**同时**独立比一次 `reward==4` vs `outcome_class`（两个来源都留痕，避免只信一条路径）。

        **反向任务的 RED 是预期形态**：`direction="left_to_right"` 时 env 的 `reward==4` 写死右→左，
        左爪夹起离桌（= 反向任务的**起点**）就满足它 ⇒ 必然不一致。这种情况 `red_subject` 记
        `env_reward_direction_hardcoded`、`red_class` 记 `expected_env_defect__not_policy_capability`，
        **RED 照记不降级**（`params:1047` 说的是"不一致即红"，没说"预期的不一致可以不红"），
        但归因写清红在 env 的判据上、不在 A2 的运行时上，也不在 policy 能力上。

        `ledger=None` 时只做内存侧（供 CPU-only 的手算臂用），产物里 `ledger_writes` 记 `not_measured`
        —— **不写 0**（三值纪律）。
        """
        if outcome_source != OUTCOME_SOURCE_GEOMETRIC:
            raise OutcomeCouplingError(
                f"outcome_source={outcome_source!r} 不是 {OUTCOME_SOURCE_GEOMETRIC!r} ⇒ 拒绝执行。"
                f"四类判定的**唯一**合法来源是 C2 的几何真值（{S4B_JUDGMENT_AUTHORITY}）；"
                f"`reward==4` 只能作交叉核验的一侧（{S4B_CRITERION_VERBATIM}）。"
                "这条牙的形状是「让耦合不可表达」，不是"
                "「耦合了以后告警」。")
        judgment = judged_env.last_judgment_object()
        if judgment is None:
            raise VlaRuntimeError("judged_env 还没有任何判定（先 step 至少一次）⇒ 不许拿 None 当 unknown 入账")
        outcome_class = str(getattr(judgment, "outcome_class"))
        if outcome_class not in S4B_OUTCOME_CLASSES:
            raise VlaRuntimeError(f"判定层给出未知 outcome_class={outcome_class!r}，"
                                  f"合法集合 {S4B_OUTCOME_CLASSES}（词表由 C2 拥有，A2 不扩）")
        direction = str(getattr(judgment, "direction"))
        # ── reward 只作交叉核验的一侧；拿不到就写 None，**不许填 0.0**（0.0 会被读成"有 reward 且为 0"）──
        if reward is None:
            reward = judged_env.last_env_reward()
        if reward is None:
            # **不许填 0.0 冒充**：`OutcomeEvent.reward` 是 float（冻结面，改不了），
            # 拿不到 env reward 时填 0.0 会被下游读成"有 reward 且为 0" ⇒ 当场抛，不静默降级。
            raise VlaRuntimeError(
                "拿不到 env 的 reward（judged_env.last_env_reward() is None）⇒ 拒绝 finalize。"
                "`contracts.OutcomeEvent.reward` 是 float 且属冻结面，A2 不改它，"
                "也**不用 0.0 顶替未知值**（三值纪律：没读到就是没读到）")
        reward4_success = bool(float(reward) == 4.0)
        # ── ③ 不一致即红：两个来源都查 ────────────────────────────────────────────────
        try:
            cc = dict(judged_env.cross_check(judgment))
            cc_verdict = str(cc.get("verdict"))
            cc_error = None
        except Exception as exc:                                      # noqa: BLE001
            # C2 的 `cross_check()` 在 agreement is False 时抛 `JudgmentDisagreement`（消息是 JSON）
            import json as _json
            cc = {"verdict": "RED"}
            try:
                cc = _json.loads(str(exc))
            except Exception:                                         # noqa: BLE001
                cc = {"verdict": "RED", "raw": str(exc)[:900]}
            cc_verdict = "RED"
            cc_error = f"{type(exc).__name__}"
        geometric_success = bool(getattr(judgment, "geometric_success"))
        env_success = getattr(judgment, "env_success", None)
        agreement = getattr(judgment, "agreement", None)
        # A2 侧**独立**再比一次（不只信 cross_check 的返回）：`reward==4` vs 四类结论
        reward4_vs_outcome = (None if reward4_success is None
                              else (None if outcome_class == "unknown"
                                    else bool(reward4_success == (outcome_class == "success"))))
        red = bool(cc_verdict == "RED") or (reward4_vs_outcome is False)
        if red:
            if direction == "left_to_right" and agreement is False:
                red_subject = "env_reward_direction_hardcoded"
                red_class = "expected_env_defect__not_policy_capability"
            elif geometric_success is False and (env_success is True or reward4_success is True):
                red_subject = "env_reward_contact_not_hold_or_flick"
                red_class = "suspected_pseudo_success__flick_or_graze"
            else:
                red_subject = "geometric_vs_reward4_mismatch"
                red_class = "unattributed_mismatch"
        else:
            red_subject = red_class = None
        if red and raise_on_disagreement:
            raise OutcomeDisagreementRed(
                f"几何真值与 reward==4 不一致（direction={direction}、geometric={geometric_success}、"
                f"env_is_success={env_success}、reward={reward}、outcome_class={outcome_class}）⇒ 红")
        # ── ② 接 ledger：只用既有公开 API；准入声明显式登记（不改 ledger.py）──────────────
        rid = request_id or f"{self.episode_id}:s4b_outcome"
        _lp = getattr(ledger, "path", None)
        writes: dict[str, Any] = {"ledger_path": (str(_lp) if _lp is not None else None),
                                  "admission_declared": S4B_LEDGER_ADMISSION}
        if ledger is None:
            writes.update({"measurement_status": "not_measured", "label_seq": None,
                           "admission_event_seq": None, "episode_end_event_seq": None,
                           "why": ("本轮未提供 ledger（CPU-only 手算臂）⇒ 入账事实是 `not_measured`，"
                                   "**不写 0 行**（三值纪律）")})
        else:
            # env 判定不是被门禁分级的裁定 ⇒ 显式写一条 `verdict_identity_absent` 把准入依据留在账上，
            # 与 `harness/ledger.py:377` 起 `ingest_runtime_result(observation_only=True)` 的语义同形。
            adm_seq = ledger.append_event(
                episode_id=self.episode_id, kind="verdict_identity_absent", request_id=rid,
                abs_frame=self.frame, epoch=self.epoch, goal_id=self.goal_id,
                lease_generation=self.generation,
                payload={"declared": S4B_LEDGER_ADMISSION,
                         "meaning": ("S4b 的四类判定由 env 几何真值产出，**不是**被门禁分级的裁定 ⇒ "
                                     "没有 gate_build，不得被翻成 DirectionScore 进发布包"),
                         "judgment_authority": S4B_JUDGMENT_AUTHORITY,
                         "judgment_module": S4B_JUDGMENT_MODULE,
                         "source": "env_geometric_truth"})
            kwargs = judged_env.ledger_label_kwargs(judgment, episode_id=self.episode_id,
                                                    target_request_id=rid)
            label_seq = ledger.append_label(**kwargs)
            writes.update({"measurement_status": "measured", "label_seq": int(label_seq),
                           "admission_event_seq": int(adm_seq),
                           "label_kwargs_keys": sorted(kwargs),
                           "label_kind": kwargs.get("label_kind"), "value": kwargs.get("value"),
                           "rubric_version": kwargs.get("rubric_version"),
                           "source_field": kwargs.get("source")})
        # `episode_end` 的 payload 里必须能看到四类结论 ⇒ 由 `finalize()` 统一发（**只发一次**）
        self._pending_s4b_payload = {
            "outcome_class": outcome_class,
            "outcome_source": OUTCOME_SOURCE_GEOMETRIC,
            "outcome_authority": S4B_JUDGMENT_AUTHORITY,
            "criterion_verbatim": S4B_CRITERION_VERBATIM,
            "independent_of_reward_eq_4": True,
            "reward_observed": reward, "reward4_success": reward4_success,
            "reward4_vs_outcome_agreement": reward4_vs_outcome,
            "geometric_success": geometric_success, "env_is_success": env_success,
            "cross_check_verdict": cc_verdict, "cross_check": cc,
            "s4b_red": red, "red_subject": red_subject, "red_class": red_class,
            "direction": direction, "ledger_writes": writes,
        }
        tv = self.finalize(outcome_class, reward=float(reward), observation=observation,
                           grasp_verified=grasp_verified, failure_phase=failure_phase)
        ee = [e for e in self.schedule_events if e.get("kind") == "episode_end"]
        if ledger is not None:
            writes["episode_end_event_seq"] = ("written_via_finalize（seq 见 ledger.schedule_event 表，"
                                              f"本进程内 episode_end 计数={len(ee)}）")
        self._pending_s4b_payload = None
        outcome = S4bOutcome(
            episode_id=self.episode_id, goal_id=self.goal_id, direction=direction,
            outcome_class=outcome_class, terminal_kind=outcome_class,
            outcome_source=OUTCOME_SOURCE_GEOMETRIC, label_kind=str(getattr(judgment, "label_kind")),
            value=getattr(judgment, "value", None), reward=reward,
            reward4_success=reward4_success, reward4_vs_outcome_agreement=reward4_vs_outcome,
            geometric_success=geometric_success, env_is_success=env_success, agreement=agreement,
            cross_check_verdict=cc_verdict, cross_check=cc, cross_check_error=cc_error,
            red=red, red_subject=red_subject, red_class=red_class,
            hold_steps=int(getattr(judgment, "hold_steps", 0) or 0),
            elapsed_s=getattr(judgment, "elapsed_s", None), horizon_s=getattr(judgment, "horizon_s", None),
            reasons=tuple(getattr(judgment, "reasons", ()) or ()),
            rubric_version=str(getattr(getattr(judgment, "thresholds", None), "rubric_version", "")),
            judgment=judgment.as_dict() if hasattr(judgment, "as_dict") else {},
            ledger_writes=writes, training_view=tv,
            n_episode_end_events=len(ee),
            representation_version=self.representation_version)
        self.last_s4b_outcome = outcome
        return outcome


# ══════════════════════════ S4b：产物数据类 ══════════════════════════
S4B_OUTCOME_CLASSES = ("success", "failure", "timeout", "unknown")


@dataclass(frozen=True)
class S4bOutcome:
    """S4b 的一局结论。**`outcome_class` 与 `reward` 分列**，读的人不可能把两者混成一个。"""

    episode_id: str
    goal_id: str
    direction: str
    outcome_class: str                       # ∈ S4B_OUTCOME_CLASSES（词表由 C2 拥有）
    terminal_kind: str                       # = outcome_class（**不是**从 reward 推的）
    outcome_source: str                      # 恒 = OUTCOME_SOURCE_GEOMETRIC
    label_kind: str                          # "success" / "unknown"（ledger 既有词表）
    value: float | None                      # 1.0 / 0.0 / None（unknown）
    reward: float | None                     # env 的 reward（**只作交叉核验**；None = 没读到，不填 0）
    reward4_success: bool | None
    reward4_vs_outcome_agreement: bool | None
    geometric_success: bool
    env_is_success: bool | None
    agreement: bool | None                   # None = 不可比（不是"一致"）
    cross_check_verdict: str                 # GREEN / RED / NOT_COMPARABLE
    cross_check: dict[str, Any]
    cross_check_error: str | None
    red: bool
    red_subject: str | None
    red_class: str | None
    hold_steps: int
    elapsed_s: float | None
    horizon_s: float | None
    reasons: tuple[str, ...]
    rubric_version: str
    judgment: dict[str, Any]
    ledger_writes: dict[str, Any]
    training_view: Any
    n_episode_end_events: int
    representation_version: str

    def as_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k not in ("training_view", "judgment")}
        d["reasons"] = list(self.reasons)
        d["judgment"] = dict(self.judgment)
        d["training_view"] = {"td_eligible": getattr(self.training_view, "td_eligible", None),
                              "bc_eligible": getattr(self.training_view, "bc_eligible", None),
                              "terminal_kind": getattr(self.training_view, "terminal_kind", None),
                              "isolation_reasons": list(getattr(self.training_view, "isolation_reasons", ()) or ())}
        d["time_unit"] = "s（裁定 62-③：跨频率对比不得按步数并列）"
        d["capability_claim"] = False
        d["success_rate_column"] = "not_an_exit_criterion（裁定 65-6③ / 46.6）"
        return d


def s4b_outcome_from_ledger(ledger: Any, *, episode_id: str) -> dict[str, Any]:
    """从 ledger **读回**四类判定，证明"接 ledger"不是只在内存里说说（round-trip 闸用）。

    读的是 `label_record`（`value_json.outcome_class`）与 `schedule_event`（`episode_end` 的 payload）。
    **一条都没读到 ⇒ `measurement_status="not_measured"` + `verdict=null`**，不写 0、不写 GREEN。
    """
    labels = [r.to_dict() for r in ledger.labels()]
    events = [r.to_dict() for r in ledger.events(episode_id=episode_id)]
    ep_labels = [r for r in labels if r.get("episode_id") == episode_id]
    outcome_labels = []
    for r in ep_labels:
        vj = r.get("value_json")
        if isinstance(vj, str):
            import json as _json
            try:
                vj = _json.loads(vj)
            except Exception:                                         # noqa: BLE001
                vj = None
        if isinstance(vj, dict) and vj.get("outcome_class") in S4B_OUTCOME_CLASSES:
            outcome_labels.append({"seq": r.get("seq"), "label_kind": r.get("label_kind"),
                                   "value": r.get("value"), "outcome_class": vj.get("outcome_class"),
                                   "rubric_version": r.get("rubric_version"),
                                   "source": r.get("source"),
                                   "geometric_success": vj.get("geometric_success"),
                                   "env_success": vj.get("env_success"),
                                   "agreement": vj.get("agreement"),
                                   "target_request_id": r.get("target_request_id")})
    ep_ends = []
    for e in events:
        if e.get("kind") != "episode_end":
            continue
        pl = e.get("payload")
        if isinstance(pl, str):
            import json as _json
            try:
                pl = _json.loads(pl)
            except Exception:                                         # noqa: BLE001
                pl = {}
        pl = pl or {}
        ep_ends.append({"seq": e.get("seq"), "terminal_kind": pl.get("terminal_kind"),
                        "s4b_outcome_class": (pl.get("s4b") or {}).get("outcome_class"),
                        "s4b_outcome_source": (pl.get("s4b") or {}).get("outcome_source"),
                        "s4b_red": (pl.get("s4b") or {}).get("s4b_red"),
                        "cross_check_verdict": (pl.get("s4b") or {}).get("cross_check_verdict"),
                        "reward4_success": (pl.get("s4b") or {}).get("reward4_success")})
    verdict_adm = [e for e in events if e.get("kind") == "verdict_identity_absent"]
    if not outcome_labels and not ep_ends:
        return {"artifact": "s4b_ledger_roundtrip", "episode_id": episode_id,
                "measurement_status": "not_measured", "verdict": None,
                "nonzero_exit_required": True,
                "n_outcome_labels": 0, "n_episode_end_events": 0,
                "why": ("ledger 里读不到任何四类判定行 ⇒ `not_measured`（不是 0 行、不是 GREEN）；"
                       "`absence_of_measurement_is_not_measurement_of_absence`")}
    return {"artifact": "s4b_ledger_roundtrip", "episode_id": episode_id,
            "measurement_status": "measured",
            "n_outcome_labels": len(outcome_labels), "outcome_labels": outcome_labels,
            "n_episode_end_events": len(ep_ends), "episode_end_events": ep_ends,
            "n_verdict_identity_absent_events": len(verdict_adm),
            "verdict_identity_absent_payloads": [
                (v.get("payload") if not isinstance(v.get("payload"), str) else v.get("payload"))
                for v in verdict_adm][:4],
            "outcome_classes_observed": sorted({o["outcome_class"] for o in outcome_labels}),
            "terminal_kinds_observed": sorted({str(e["terminal_kind"]) for e in ep_ends}),
            "outcome_source_observed": sorted({str(e["s4b_outcome_source"]) for e in ep_ends
                                               if e.get("s4b_outcome_source")})}


# ══════════════════════════ S4b：C2 env → runtime 的适配器 ══════════════════════════
class GymAlohaJudgedAdapter:
    """把 **C2 的** `harness/env_gym_aloha.GymAlohaSimEnv` 接到本文件的 `EnvAdapter` 协议上。

    **判定层不归 A2**：四类结论一律取自 C2 的 `judge_from_facts()`（经 `GymAlohaSimEnv.step()`）。
    本适配器只做三件搬运，**不重算任何判定**：
      ① C2 的扁平 obs（π₀.₅ 策略层键名）→ `ObsBundle`（runtime 键名，映射见
         `PI05_TO_RUNTIME_IMAGE_KEYS`，**映射本身落进产物**）；
      ② runtime 的 action → `GymAlohaSimEnv.step()`；
      ③ C2 的 `Judgment` → runtime 的 `last_judgment_object()` / `cross_check()` /
         `ledger_label_kwargs()`（后两者**直接透传 C2 的方法**，A2 不另写映射表）。

    `renderer_class` 三点读数（起点 / 运行内 / 终点）挂在 `self.renderer_ledger` 上：
    终点值**只能**由 `probe_renderer(point="at_end")` 显式写入，拿不到就是 `null` +
    `measurement_kind`，**不许**由起点值顶替（`harness/prompt_bin_guard.RendererClassLedger` 看守）。
    """

    def __init__(self, *, direction: str = "right_to_left", image_size: int = 224,
                 render: bool = True, horizon_option: str = "registered_300",
                 spec: Any = None, env: Any = None, apply_record: dict | None = None,
                 cam_map: Mapping[str, str] | None = None, thresholds: Any = None,
                 seed: int | None = None, renderer_ledger: Any = None):
        from harness import prompt_bin_guard as pbg
        ega = load_env_gym_aloha()
        self._ega = ega
        self.pbg = pbg
        kw: dict[str, Any] = {}
        if cam_map is not None:
            kw["cam_map"] = dict(cam_map)
        if thresholds is not None:
            kw["thresholds"] = thresholds
        self.spec = spec or ega.EnvSpec(direction=direction, image_size=int(image_size),
                                        render_images=bool(render),
                                        horizon_option=horizon_option, seed=seed, **kw)
        self.jenv = ega.GymAlohaSimEnv(self.spec, env=env, apply_record=apply_record)
        self.dt_s = float(self.spec.dt)
        self.control_hz = float(self.jenv.timing.get("control_hz") or (1.0 / self.dt_s))
        self.max_episode_steps = int(self.jenv.horizon)
        self.direction = str(self.spec.direction)
        self.goal_id = GOAL_ID_BY_DIRECTION.get(self.direction, self.direction)
        self.image_key_map = dict(PI05_TO_RUNTIME_IMAGE_KEYS)
        self.render = bool(self.spec.render_images)
        self.image_size = int(self.spec.image_size)
        self.renderer_ledger = renderer_ledger if renderer_ledger is not None else pbg.RendererClassLedger()
        from envs import gym_aloha_shim as _shim
        self.shim = _shim                      # 频率 shim 的单一事实源（A2 拥有；C2 的 env 也只 import 它）
        self._frame = 0
        self._hold: list[float] | None = None
        self._last_reward: float | None = None
        self._last_info: dict[str, Any] = {}
        self._last_judgment: Any = None
        self.n_renders_in_run = 0
        self.in_run_renderer_measurement: dict[str, Any] | None = None
        self.end_renderer_measurement: dict[str, Any] | None = None
        self.apply_record = dict(self.jenv.apply_record or {})
        self.env_identity = {"module": S4B_JUDGMENT_MODULE,
                             "module_sha256_12": ega.module_sha256_12(),
                             "module_representation_version": ega.MODULE_REPRESENTATION_VERSION,
                             **env_gym_aloha_identity()["judgment_module"]}
        # 起点读数（**只**在这一处写 at_start；终点另写，不回填）—— 走真实取数路径
        self.start_renderer_measurement = self.measure_renderer_at("at_start")

    @property
    def hold(self) -> list[float]:
        """当前 hold 动作（= reset 后的 qpos，夹爪维夹到 [0,1]）。

        与 `scripts/a2_s4a_vla_runtime_verify.py:225` 的 `GymAlohaAdapter.hold` **同名同义**
        ⇒ 既有的 `RealEnvStubPolicy` 可以直接吃这个适配器，不需要再抄一份 stub policy。
        """
        if self._hold is None:
            raise VlaRuntimeError("hold 在 reset 之前被读取（不许静默填 0）")
        return list(self._hold)

    # ---------- renderer_class 三点 ----------
    def probe_renderer(self, point: str, *, inside_real_render: bool = False) -> dict[str, Any]:
        """裸调读数（**不可信**路径）：没有真实渲染兜底时读到 NULL 就登记 NULL，不猜。"""
        return self.renderer_ledger.probe_gl_renderer(point=point, inside_real_render=inside_real_render)

    def measure_renderer_at(self, point: str, *, probe_px: int = 8) -> dict[str, Any]:
        """**真实取数路径**（裁定 72）：先让 env 真渲染一发，紧接着在**同一调用栈**里读 `GL_RENDERER`。

        为什么必须先渲染：`glGetString` 在没有 current context 时返回 NULL。dm_control 的渲染
        可能跑在 `RenderExecutor` 的工作线程上 ⇒ 只有"刚 `physics.render()` 返回"这一刻，
        本线程的上下文状态才是可读的事实。修前 A2 在 `step()` **返回之后**才读，实测全是
        `null_context`（osmesa 臂三点全 null）⇒ 那是取数时机错，不是"没有渲染器"。
        `probe_px` 用小图（8×8）：只为拿到上下文，不产生有意义的像素，也不进任何延迟数字。
        """
        rec: dict[str, Any] = {"point": point, "mechanism": "explicit_small_render_then_glGetString"}
        if self.render:
            try:
                cam = next(iter(self.spec.cam_map.values()))
                self.jenv.physics.render(height=int(probe_px), width=int(probe_px), camera_id=cam)
                rec["probe_render"] = {"camera_id": cam, "px": int(probe_px), "ok": True}
                out = self.renderer_ledger.probe_gl_renderer(point=point, inside_real_render=True)
            except Exception as exc:                                  # noqa: BLE001
                rec["probe_render"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}
                out = self.renderer_ledger.probe_gl_renderer(point=point, inside_real_render=False)
        else:
            rec["probe_render"] = {"ok": False, "why": "render_images=False ⇒ 没有真实渲染可兜底"}
            out = self.renderer_ledger.probe_gl_renderer(point=point, inside_real_render=False)
        rec.update(out)
        return rec

    def render_backend(self) -> tuple[str, ...]:
        import sys as _sys
        try:
            import mujoco
            mv = getattr(mujoco, "__version__", "unknown")
        except Exception:                                             # noqa: BLE001
            mv = "unreadable"
        snap = self.renderer_ledger.snapshot()
        rend = (snap["points"]["in_run"]["gl_renderer_raw"]
                or snap["points"]["at_start"]["gl_renderer_raw"] or "not_read")
        n_cam = len(self.spec.cam_map) if self.render else 0
        return (_sys.executable.split("/")[-2], f"MUJOCO_GL={os.environ.get('MUJOCO_GL')}",
                f"GL_RENDERER={rend}|class={snap['in_run'] or snap['at_start']}",
                f"mujoco={mv}", "viperx300s_bimanual", f"{n_cam}cam@{self.image_size}",
                f"dt={self.dt_s}", f"hz={round(self.control_hz, 6)}")

    # ---------- EnvAdapter 协议 ----------
    def _obs(self, frame: int) -> "ObsBundle":
        raw = self.jenv.observation()
        st = raw[self._ega.STATE_KEY]
        images = {}
        for k, v in raw.items():
            if k == self._ega.STATE_KEY:
                continue
            images[self.image_key_map.get(k, k)] = v
        return ObsBundle(frame=int(frame), images=images, state=st,
                         state_raw_14d=np.asarray(st, dtype=np.float64).copy(),
                         goal_id=self.goal_id, dt_s=self.dt_s, control_hz=self.control_hz,
                         representation_version="see_runtime",
                         render_backend=self.render_backend())

    def reset(self, seed: int) -> "ObsBundle":
        self.jenv.reset(seed=seed)
        self._frame = 0
        self._last_reward = None
        self._last_info = {}
        self._last_judgment = None
        st = np.asarray(self.jenv._state(), dtype=np.float64).reshape(-1)
        hold = [float(x) for x in st[:14]]
        for gi in (6, 13):
            if gi < len(hold):
                hold[gi] = min(max(hold[gi], 0.0), 1.0)
        self._hold = hold
        return self._obs(0)

    def observe(self, frame: int) -> "ObsBundle":
        return self._obs(frame)

    def hold_action(self) -> list[float]:
        if self._hold is None:
            raise VlaRuntimeError("hold_action 在 reset 之前被调用（不许静默填 0）")
        return list(self._hold)

    def apply(self, action: Any) -> tuple[float, bool, bool, Mapping[str, Any]]:
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        if a.shape[0] != self._ega.STATE_DIM:
            raise VlaRuntimeError(f"动作维度 {a.shape[0]} != {self._ega.STATE_DIM}"
                                  "（gym_aloha 的 action_space；π₀.₅ 的 32 维输出必须先适配）")
        _obs, si = self.jenv.step(a)
        self._frame = int(si.get("step_index", self._frame + 1))
        facts = si.get("facts") or {}
        r = facts.get("env_reward")
        self._last_reward = (None if r is None else float(r))
        self._last_judgment = self.jenv._last_judgment
        jud = si.get("judgment") or {}
        self.n_renders_in_run += 1 if self.render else 0
        # **运行内**读数：只在第一次 apply 时测一发（走真实取数路径，见 measure_renderer_at）
        if self.render and self.renderer_ledger.snapshot()["points"]["in_run"]["renderer_class"] is None \
                and self.renderer_ledger.snapshot()["points"]["in_run"]["measurement_kind"].startswith("not_measured"):
            self.in_run_renderer_measurement = self.measure_renderer_at("in_run")
        info = {"qpos": [float(x) for x in np.asarray(self.jenv._state(), dtype=np.float64).reshape(-1)[:14]],
                "judgment": jud, "facts": facts,
                "outcome_class": jud.get("outcome_class"),
                "geometric_success": jud.get("geometric_success"),
                "env_is_success": jud.get("env_success"),
                "env_reward": r, "step_index": si.get("step_index"),
                "env_terminated": bool(si.get("env_terminated")),
                "env_truncated": bool(si.get("env_truncated")),
                "hold_steps": jud.get("hold_steps"),
                "elapsed_s": jud.get("elapsed_s"), "horizon_s": jud.get("horizon_s")}
        self._last_info = info
        return (self._last_reward if self._last_reward is not None else float("nan")), \
            bool(si.get("env_terminated")), bool(si.get("env_truncated")), info

    # ---------- 判定层透传（**不重算**）----------
    def last_judgment_object(self) -> Any:
        return self._last_judgment

    def last_env_reward(self) -> float | None:
        return self._last_reward

    def cross_check(self, judgment: Any = None) -> dict[str, Any]:
        return self.jenv.cross_check(judgment)

    def ledger_label_kwargs(self, judgment: Any, **kw: Any) -> dict[str, Any]:
        return self.jenv.ledger_label_kwargs(judgment, **kw)

    def measure_renderer_at_end(self) -> dict[str, Any]:
        """终点读数。**只能**由本方法（或显式 `probe_renderer("at_end")`）写；
        `RendererClassLedger` 里没有任何从 at_start 回填 at_end 的代码路径（D 的派工原文）。"""
        self.end_renderer_measurement = self.measure_renderer_at("at_end")
        return self.end_renderer_measurement

    def manifest(self) -> dict[str, Any]:
        m = dict(self.jenv.manifest())
        m.update({"adapter": "harness/vla_runtime.py::GymAlohaJudgedAdapter",
                  "adapter_role": "obs/action/judgment 的**搬运**，不重算判定（判定层归 C2）",
                  "image_key_map_pi05_to_runtime": dict(self.image_key_map),
                  "renderer_class_three_points": self.renderer_ledger.snapshot(),
                  "renderer_probe_mechanism": {
                      "at_start": self.start_renderer_measurement,
                      "in_run": self.in_run_renderer_measurement,
                      "at_end": self.end_renderer_measurement,
                      "rule": ("三点各自独立测；读到 NULL 一律 `not_measured_no_gl_context`，"
                               "**不许**把 NULL 记成 measured、也**不许**拿起点值顶替终点")},
                  "n_renders_in_run": self.n_renders_in_run,
                  "shim_apply_record": self.apply_record})
        return m

    def close(self) -> None:
        try:
            self.jenv.env.close()
        except Exception:                                             # noqa: BLE001
            pass


# ══════════════ 裁定 95.3-①：四个字段**分开记**（不许再合并成一个 VALID/INVALID）══════════════
# 判据原文（`work/project_parameters.json` rev20 `ruling95_technical_corrections_rev20` →
# `correction_1_out_of_distribution_is_not_invalid_measurement`；派工原文
# `rl_harness_supervision/d_handoff_to_a2_20260930.md` 补单二-§四，**不重新解释**）：
#   「**『输入越界 ⇒ 测量无效』是错的口径（选择偏差）**：混淆了 (a) 输入预处理错/动作单位错配
#     （= 实验不代表预期方法，**这才该判无效**）与 (b) 策略闭环跑到训练分布之外（= **可能正是策略的
#     真实失败机制，不得从能力统计里剔除**）。**新口径（π₀.₅ 主线与 S5 一律适用）**：四个字段分开记，
#     不许合并成一个 VALID/INVALID —— `measurement_reliable` · `interface_conformant` ·
#     `out_of_distribution`（**只标注、不剔除**）· `task_success`；能力统计**必须包含 (b) 类样本**
#     并单独报 OOD 比例。」
RULING_95_3_1 = "裁定 95.3-①（params rev20 `correction_1_out_of_distribution_is_not_invalid_measurement`）"
FOUR_FIELDS = ("measurement_reliable", "interface_conformant", "out_of_distribution", "task_success")
FOUR_FIELD_MEANINGS = {
    "measurement_reliable": "记录/计时/判定是否可信（账本读得回、时序测到、判定层给了结论）",
    "interface_conformant": "接口是否符合**预期方法**（= (a) 类：输入预处理错 / 动作单位错配 / 视觉通道缺失）",
    "out_of_distribution": "= (b) 类：闭环跑到了训练分布之外。**只标注、不剔除**",
    "task_success": "任务是否成功（**只**取自 C2 的几何判定，不由本文件重算）",
}
# 合并字段的名字词表：出现任一个 ⇒ `MergedValidityError`（让"合并"这件事在产物层也过不去）
FORBIDDEN_MERGED_VALIDITY_KEYS = frozenset({
    "valid", "invalid", "is_valid", "validity", "measurement_valid", "measurement_validity",
    "episode_valid", "episode_validity", "VALID", "INVALID", "valid_flag", "invalid_reason_only",
})


class MergedValidityError(VlaRuntimeError):
    """四个字段被**合并**成一个 VALID/INVALID ⇒ 当场抛（裁定 95.3-①）。

    为什么做成异常而不是告警：合并口径造成的**选择偏差**是静默的 —— 表现差、越界多的策略被剔除，
    留下的统计更好看，产物上看不出任何异常。只有让合并**不可表达**才守得住。
    """


@dataclass(frozen=True)
class EpisodeFourFields:
    """一局的四字段记录。**没有**任何合并字段的位置（`frozen` + 字段表固定）。"""

    measurement_reliable: bool | None
    interface_conformant: bool | None
    out_of_distribution: bool | None
    task_success: bool | None
    measurement_defect_reasons: tuple[str, ...] = ()
    interface_defect_reasons: tuple[str, ...] = ()
    ood_reasons: tuple[str, ...] = ()
    task_success_source: str | None = None
    excluded_from_capability_stats: bool = False     # **恒 False**：OOD 只标注不剔除
    seed: int | None = None
    direction: str | None = None
    autonomous_success: bool | None = None           # 三分开统计之一（第 4 步起才有救场）
    final_completion_with_recovery: bool | None = None
    intervention_count: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}
        d["artifact"] = "episode_four_fields"
        d["ruling"] = RULING_95_3_1
        d["field_meanings"] = dict(FOUR_FIELD_MEANINGS)
        d["merged_field_present"] = False
        d["ood_is_annotated_not_excluded"] = True
        d["three_valued_discipline"] = ("任一字段读不到 ⇒ `None`（= `not_measured`），"
                                        "**不许**填 `False` 冒充（`absence_of_measurement_is_not_"
                                        "measurement_of_absence`）")
        return d


def _tri(values: Sequence[bool | None]) -> bool | None:
    """三值聚合：**只会更严、不会更松**。有 False ⇒ False；无 False 但有 None ⇒ None；全 True ⇒ True。

    空集 ⇒ `None`（不是 True）—— 空集判 True 就是"没测到当作没问题"。
    """
    vs = list(values)
    if not vs:
        return None
    if any(v is False for v in vs):
        return False
    if any(v is None for v in vs):
        return None
    return True


def four_fields_from_episode(*, outcome_class: str | None = None,
                             ledger_roundtrip_status: str | None = None,
                             timing_measured: bool | None = None,
                             isolation_reasons: Sequence[str] | None = None,
                             prompt_audit: Mapping[str, Any] | None = None,
                             ood_signals: Mapping[str, Any] | None = None,
                             seed: int | None = None, direction: str | None = None,
                             autonomous_success: bool | None = None,
                             final_completion_with_recovery: bool | None = None,
                             intervention_count: int | None = None,
                             evidence: Mapping[str, Any] | None = None) -> EpisodeFourFields:
    """把一局的事实翻成四字段。**判定层不归 A2**：`task_success` 只由 `outcome_class` 派生
    （`outcome_class` 本身只来自 C2 的 `judge_from_facts()`）。

    (a) 与 (b) 的分界（照裁定原文，不重新解释）：
      * **(a) 判 `interface_conformant=False`**：`stats_version=NONE` 的 pass-through、视觉通道缺键、
        prompt 里出现**非法 bin `-1`**（= 输入预处理错，实验不代表预期方法）。
      * **(b) 判 `out_of_distribution=True`**：运行时观测/动作**越出**合法区间、bin 顶到 255 饱和、
        动作被 `actuator_ctrlrange` 裁剪 —— 这些**可能正是策略的真实失败机制** ⇒ 只标注、不剔除。
      * 同一条证据可以**同时**落进 (a) 与 (b)（例如"没有 stats ⇒ 原始 rad 直接进 digitize ⇒ 既属接口
        缺陷、又使取值越界"）⇒ 两个字段各自记，**不许互相抵消、也不许合并**。
    """
    m_reasons: list[str] = []
    i_reasons: list[str] = []
    o_reasons: list[str] = []

    # ---- ① measurement_reliable ----
    if ledger_roundtrip_status is None:
        m_reasons.append("ledger_roundtrip_status=None（没读到 ⇒ not_measured，不是"
                         "「读到了且可靠」）")
    elif str(ledger_roundtrip_status) != "measured":
        m_reasons.append(f"ledger_roundtrip_status={ledger_roundtrip_status!r}（账本读不回 ⇒ 记录不可信）")
    if timing_measured is None:
        m_reasons.append("timing_measured=None（墙钟分解未测 ⇒ 计时不可信）")
    elif timing_measured is False:
        m_reasons.append("timing_measured=False")
    measurement_reliable = (None if (ledger_roundtrip_status is None or timing_measured is None)
                            else (not m_reasons))

    # ---- ② interface_conformant ----
    iface_signals: list[bool | None] = []
    for r in (isolation_reasons or ()):
        rs = str(r)
        if "stats_version" in rs:
            i_reasons.append(f"stats 缺失（pass-through）：{rs[:160]}")
            iface_signals.append(False)
        elif "vision_channel_absent" in rs:
            i_reasons.append(f"视觉通道缺键：{rs[:160]}")
            iface_signals.append(False)
    pa = dict(prompt_audit or {})
    if pa:
        pv, prc = pa.get("verdict"), set(str(x) for x in (pa.get("red_classes") or []))
        if pa.get("measurement_status") != "measured":
            i_reasons.append(f"prompt 牙未测（measurement_status={pa.get('measurement_status')!r}）")
            iface_signals.append(None)
        elif pv == "RED" and ("illegal_bin_minus1_in_prompt" in prc
                              or "token_outside_legal_bin_range" in prc):
            i_reasons.append("(a) 输入预处理错：非法 bin `-1` 静默进 prompt"
                             f"（dims={pa.get('illegal_bin_dims_union')}）")
            iface_signals.append(False)
        elif pv == "RED":
            i_reasons.append(f"prompt 牙判红（red_classes={sorted(prc)}）")
            iface_signals.append(False)
        else:
            iface_signals.append(True)
    else:
        iface_signals.append(None)
    interface_conformant = (False if i_reasons and any(s is False for s in iface_signals)
                            else _tri(iface_signals))

    # ---- ③ out_of_distribution（只标注、不剔除）----
    sig = dict(ood_signals or {})
    ood_signals_status: list[bool | None] = []
    for key in ("state_out_of_normalizer_range", "action_clipped_at_ctrlrange",
                "prompt_bins_saturated_255", "prompt_bins_illegal_minus1",
                "action_unit_mismatch_suspected"):
        v = sig.get(key)
        if v is None:
            ood_signals_status.append(None)
            continue
        ood_signals_status.append(bool(v))
        if v:
            o_reasons.append(f"{key}={sig.get(key)}"
                             + (f"（{sig.get(key + '_detail')}）" if sig.get(key + "_detail") else ""))
    # ── 极性（**A2 自报缺陷 · 已修**，as_of 2026-09-30 13:0x）────────────────────────────
    # 原写法 `_tri([not x for x in ood_signals_status])` 是**反的**：`_tri` 的语义是「只会更严」
    # （全 True ⇒ True），而喂进去的是 `not x`（= 「不在分布外」）⇒ 五个信号**全为 False**
    # （= 完全在分布内）时 `_tri` 返回 True，被直接当成 `out_of_distribution=True`。
    # **后果具体**：每一局都被标 OOD ⇒ `ood_ratio` 恒 = 1.0 ⇒ 裁定 95.3-① 要求的「单独报 OOD
    # 比例」退化成恒等于 1 的常量（信息量为零）；而且偏差方向是"多标 OOD"、**不会**剔除样本
    # ⇒ 产物层看不出任何异常（静默）。抓住它的不是复核，是
    # `scripts/a2_standard_sync_exec_verify.py` G10 的**手算期望**（`ood_ratio == round(1/3,4)`）。
    # 前像 `tmp/vla_runtime_pre_oodpolarity_8f35376ba2bb.py`；缺陷类 = ⑲ 的同族
    # （判据的**极性**与对象空间不一致）。
    out_of_distribution: bool | None
    if o_reasons:
        out_of_distribution = True
    elif not ood_signals_status:
        out_of_distribution = None
    elif any(x is None for x in ood_signals_status):
        out_of_distribution = None      # 有信号没采到 ⇒ not_measured（**不是**「在分布内」）
    else:
        out_of_distribution = False     # 信号全部采到且全部为 False ⇒ 在分布内
    if out_of_distribution is None:
        n_missing = len(ood_signals_status) - sum(1 for x in ood_signals_status if x is not None)
        o_reasons.append(
            "没有任何 OOD 信号被采到 ⇒ not_measured（**不是**「在分布内」）"
            if not ood_signals_status else
            f"OOD 信号 {n_missing}/{len(ood_signals_status)} 项未采到 ⇒ not_measured"
            "（**不是**「在分布内」）")

    # ---- ④ task_success（只由 C2 的 outcome_class 派生）----
    task_success, ts_source = None, None
    if outcome_class is None:
        ts_source = "outcome_class=None（判定层没给结论 ⇒ not_measured，不许填 False）"
    elif str(outcome_class) == "unknown":
        ts_source = "outcome_class='unknown'（C2 判定层给的是 unknown ⇒ 三值里是 not_measured）"
    elif str(outcome_class) in S4B_OUTCOME_CLASSES:
        task_success = (str(outcome_class) == "success")
        ts_source = f"c2_geometric_judgment:outcome_class={outcome_class}"
    else:
        ts_source = f"outcome_class={outcome_class!r} 不在词表 {S4B_OUTCOME_CLASSES} ⇒ not_measured"

    return EpisodeFourFields(
        measurement_reliable=measurement_reliable, interface_conformant=interface_conformant,
        out_of_distribution=out_of_distribution, task_success=task_success,
        measurement_defect_reasons=tuple(m_reasons), interface_defect_reasons=tuple(i_reasons),
        ood_reasons=tuple(o_reasons), task_success_source=ts_source,
        excluded_from_capability_stats=False, seed=seed, direction=direction,
        autonomous_success=autonomous_success,
        final_completion_with_recovery=final_completion_with_recovery,
        intervention_count=intervention_count, evidence=dict(evidence or {}))


def assert_no_merged_validity(record: Any, *, where: str = "") -> None:
    """牙：产物里出现**合并**的 VALID/INVALID 字段 ⇒ 抛（裁定 95.3-①）。

    扫两层（顶层 + 一层子 dict），因为四字段常被塞进 `episode`/`verdict` 这类子块里。
    **只认键名**：不猜语义，避免把无关字段误判成合并（缺陷类 ⑲：判据作用域不得比对象空间窄 ⇒
    词表 `FORBIDDEN_MERGED_VALIDITY_KEYS` 是显式枚举，扩词表要改这里、留痕）。
    """
    hits: list[str] = []

    def scan(obj: Any, prefix: str, depth: int) -> None:
        if depth > 2 or not isinstance(obj, Mapping):
            return
        for k, v in obj.items():
            ks = str(k)
            if ks in FORBIDDEN_MERGED_VALIDITY_KEYS:
                hits.append(f"{prefix}{ks}")
            if isinstance(v, Mapping):
                scan(v, f"{prefix}{ks}.", depth + 1)

    scan(record, where, 0)
    if hits:
        raise MergedValidityError(
            f"检出**合并**的有效性字段 {hits}（位置 {where or '<root>'}）⇒ 违反裁定 95.3-①："
            f"必须分开记 {list(FOUR_FIELDS)}。合并口径会造成选择偏差（表现差、越界多的策略被剔除，"
            "留下的统计更好看），所以这里**抛**，不是告警")


def aggregate_capability_stats(records: Sequence[Mapping[str, Any] | EpisodeFourFields]) -> dict[str, Any]:
    """能力统计聚合：**必须包含 (b) 类 OOD 样本**并单独报比例（裁定 95.3-①）+ 每种子单独报数（95.5）。

    三条硬规定：
      * **空集 ⇒ `null` + `nonzero_exit_required=True`**（裁定 88.3-1；不许写 0、不许写 GREEN）；
      * `n_excluded_from_capability_stats` **恒为 0**：本函数不做任何剔除，剔除就是选择偏差；
      * **每种子单独报数**（`by_seed`），不许只报均值、不许挑最高（裁定 95.5 / 补单二-§七）。
    """
    rs = [(r.as_dict() if isinstance(r, EpisodeFourFields) else dict(r)) for r in (records or [])]
    for r in rs:
        assert_no_merged_validity(r, where="aggregate_capability_stats.input")
    if not rs:
        return {"artifact": "capability_stats_aggregate", "measurement_status": "not_measured",
                "verdict": None, "n_episodes": 0, "nonzero_exit_required": True,
                "task_success_count": None, "ood_ratio": None,
                "why": ("空集 ⇒ `null` + 非零退出（裁定 88.3-1）；**不许**写 0、不许写 GREEN。"
                        "`absence_of_measurement_is_not_measurement_of_absence`"),
                "ruling": RULING_95_3_1, "capability_claim": False,
                "success_rate_column": "not_an_exit_criterion"}

    def cnt(key: str, val: Any) -> int:
        return sum(1 for r in rs if r.get(key) is val)

    n = len(rs)
    n_succ = cnt("task_success", True)
    n_succ_nm = sum(1 for r in rs if r.get("task_success") is None)
    n_ood = cnt("out_of_distribution", True)
    by_seed: dict[str, dict[str, Any]] = {}
    for r in rs:
        k = str(r.get("seed"))
        b = by_seed.setdefault(k, {"seed": r.get("seed"), "n_episodes": 0, "task_success_count": 0,
                                   "task_success_not_measured": 0, "ood_count": 0,
                                   "interface_non_conformant": 0, "measurement_unreliable": 0,
                                   "directions": sorted({str(x) for x in [r.get("direction")] if x})})
        b["n_episodes"] += 1
        b["task_success_count"] += int(r.get("task_success") is True)
        b["task_success_not_measured"] += int(r.get("task_success") is None)
        b["ood_count"] += int(r.get("out_of_distribution") is True)
        b["interface_non_conformant"] += int(r.get("interface_conformant") is False)
        b["measurement_unreliable"] += int(r.get("measurement_reliable") is False)
    by_direction: dict[str, dict[str, Any]] = {}
    for r in rs:
        k = str(r.get("direction"))
        b = by_direction.setdefault(k, {"direction": r.get("direction"), "n_episodes": 0,
                                        "task_success_count": 0, "ood_count": 0})
        b["n_episodes"] += 1
        b["task_success_count"] += int(r.get("task_success") is True)
        b["ood_count"] += int(r.get("out_of_distribution") is True)
    # 三分开统计（v4 要求；第 4 步起才有"救场"，之前一律 not_measured，**不写 0**）
    three_way = {
        "policy_autonomous_success": {
            "count": (sum(1 for r in rs if r.get("autonomous_success") is True)
                      if any(r.get("autonomous_success") is not None for r in rs) else None),
            "measurement_status": ("measured" if any(r.get("autonomous_success") is not None for r in rs)
                                   else "not_measured"),
            "definition": "不计任何接管/救场的自主成功",
        },
        "system_final_completion": {
            "count": (sum(1 for r in rs if r.get("final_completion_with_recovery") is True)
                      if any(r.get("final_completion_with_recovery") is not None for r in rs) else None),
            "measurement_status": ("measured" if any(r.get("final_completion_with_recovery") is not None
                                                     for r in rs) else "not_measured"),
            "definition": "允许恢复与接管之后的系统最终完成率",
        },
        "intervention_rate": {
            "count": (sum(int(r.get("intervention_count") or 0) for r in rs)
                      if any(r.get("intervention_count") is not None for r in rs) else None),
            "measurement_status": ("measured" if any(r.get("intervention_count") is not None for r in rs)
                                   else "not_measured"),
            "definition": "每任务需要多少次外部帮助（第 4 步起才可测）",
        },
        "ruling": "裁定 95.5 / v4：三分开统计，缺一个都不算完成；未测的一律 not_measured，不写 0",
    }
    return {
        "artifact": "capability_stats_aggregate", "measurement_status": "measured",
        "n_episodes": n,
        "task_success_count": n_succ, "task_success_not_measured_count": n_succ_nm,
        "task_success_rate_including_ood": round(n_succ / n, 4),
        "ood_count": n_ood, "ood_ratio": round(n_ood / n, 4),
        "ood_is_annotated_not_excluded": True,
        "n_excluded_from_capability_stats": 0,
        "exclusion_policy": ("**恒为 0**：本聚合不做任何剔除。裁定 95.3-① 明写 (b) 类样本"
                             "「不得从能力统计里剔除」，剔除就是选择偏差"),
        "interface_non_conformant_count": cnt("interface_conformant", False),
        "interface_non_conformant_ratio": round(cnt("interface_conformant", False) / n, 4),
        "measurement_unreliable_count": cnt("measurement_reliable", False),
        "measurement_reliable_not_measured_count": sum(1 for r in rs
                                                       if r.get("measurement_reliable") is None),
        "by_seed": dict(sorted(by_seed.items(), key=lambda kv: kv[0])),
        "by_seed_rule": "每种子单独报数；**不许只报均值、不许挑最高**（裁定 95.5 / 补单二-§七）",
        "by_direction": by_direction,
        "directions_reported_separately": True,
        "three_way_statistics": three_way,
        "capability_claim": False,
        "capability_claim_gate": ("裁定 46：本聚合只是**计数**。任何「能搬运 / 学会了」的表述在"
                                  "里程碑审查（裁定 95.6：D 的角色 = 里程碑审查 + Ⅰ 类判据守门）"
                                  "之前无效"),
        "success_rate_column": "not_an_exit_criterion",
        "ruling": RULING_95_3_1,
    }
