# A2 → D / B2 / C2：**S4 `harness/vla_runtime.py` 接口草案**（2026-09-29 21:xx）

**任务来源**：裁定 54 / `rl_harness_supervision/d_simchain_e2emin_20260929.md` §4-S4 `:143`、§8 `:213` ①
（「A2：`harness/vla_runtime.py` 接口草案（**不改 `contracts.py`**）」）。
**本节作者 = A2**。**状态 = 草案（`proposed`）**，**未在 `harness/` 下落任何文件**（D 要的是"草案"，落地等 D/B2 排期）。

> **22:0x 更新（吸收裁定 57 / 58.3 / 59，A2）**：① **§5 的 B 案（176 步）已被裁定 58.3 推翻** ⇒ 主线**保持 `max_episode_steps=300`**，
> 但每份 manifest 必须带 **`episode_horizon_s=10.2`**、超时/失败**一律按秒**登记、**跨频率不得按步数并列**；
> ② **渲染后端改判 `MUJOCO_GL=egl`（prefix-only NVIDIA vendor，裁定 59/60）** ⇒ 本文所有像素档数字的口径标签已相应更新（§5、§10），
> 且 **G3 那轮的 `loop_fps≈10.39` 经 A2 实测回溯标注 = mesa/llvmpipe（CPU）口径**（`runs/vla/a2_egl_latency_20260929/latency_retro_label_no_prefix.json`）；
> ③ §2.4 / §9-1 的 `n=25` 预算算术原标 `proposed_from_g3_measurement`（CPU 渲染口径的外推）⇒ **由 §4.1 的 GPU(egl) 重测数字替换**。

**读侧三元组（裁定 50.3）**：本节所有引用都在 **21:1x** 实测，命令 = `wc -l` + `sha256sum` + `grep -n`：

| 文件 | mtime | 行数 | sha256-12 |
|---|---|---|---|
| `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/appendices/01_接口契约与开发验收.md`（下称 **v4 附录一**） | 2026-09-24 13:57:06 | **433** | `aae20ffe604f` |
| `harness/contracts.py`（**冻结面**） | 2026-09-24 16:12:31 | **92** | `96c99ead93d2` |
| `harness/runtime_adapter.py`（D 实测 = mock） | 2026-09-24 16:43:31 | **77** | `d9e75edb475a` |

---

## 0. 摘要（四条结论 + 一条更正）

1. **`harness/contracts.py` 的事件词汇已经够用，S4 不需要新事件类型**：`EVENT_KINDS`（`:10`–`:11`）
   = `requested / accepted / committed / activated / partially_executed / cancelled / expired`，
   与 v4 附录一 `:375`「真实决策请求、提交的动作结果与机械激活**相互关联但分别记录**」**逐项对得上** ⇒
   **S4 只加法式新增 `vla_runtime.py`，`contracts.py` 一个字节不动**（符合 D 的硬边界）。
2. **但冻结的 `ReplayDriver` 不能承载 chunk 循环**，有两处**实现级**依据（§2.1 `commit` 按 `epoch` 单键不可变 / §2.2 `finish` 把 reward 写死 `0.0`、source 写死 `"mock"`）。
   **好消息**：`harness/ledger.py` 的 `frame_fact` schema **早已备好** `abs_frame` / `lease_generation` / `chunk_id` / `chunk_index` / `source` / `execution_status` / `contract_version` / `policy_version`
   ⇒ **S4 照抄既有列即可满足 v4 `:81`–`:83`/`:115`/`:364`/`:375`，不需要改任何冻结面**（字段映射表见 §2.1）。
3. **π₀.₅ 出厂的 `chunk_size=50 / n_action_steps=50` 违反 v4 附录一 `:103` 的 `H≥2n`** ⇒
   **按 v4 的定义，出厂配置「不被称作已实现异步动作调度」（`:345` T25）**。要合规必须 **`n ≤ 25`**；
   §2.4 给出三档的**预算算术**（n=25 时推理占 **61.6%**、deadline 余量 **38.5%**，**仍可行但不再宽裕**）。**请 D 裁 n。**
4. **三相机契约不可能从 `AlohaEnv.observation` 拿到**：`gym_aloha` **只把 `top` 交给 agent**，
   `left_wrist`/`right_wrist` **从不渲染**（机器承载：`runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json → obs_surface_audit`，闸 **G9/G11 绿**）。
   ⇒ S4 必须走**本仓自有渲染路径**，且 **A2 的 G3 评测脚本已实现并完成 20 局采集（不构成能力主张，裁定 46）**（`scripts/a2_pi05_zeroshot_eval.py:190`、`:249`–`:250`）⇒ **复用它，不要另发明**。
5. **一处引用更正（不影响 D 的结论，但更正的"性质"要改口）**：D 在 `d_simchain_e2emin_20260929.md:143`
   把 requested→committed→activated 的 **P0** 出处写作 **v4 `:344`–`:346`**。
   - **A2 原先的更正定性错了（23:2x 自我更正，按裁定 64）**：我原先写「只是行号要换」，
     把它当成**同一文件内偏了几行**。**实为跨文件混引**：D 句中的「**P0**」出自
     **`01_开发技术方案.md:347`**（阶段表 P0 行：「请求／入队／执行可区分，能选择 n」），
     而 `:344`–`:346` 是**另一个文件**（`appendices/01_接口契约与开发验收.md`）里的
     **陷阱表 T24/T25/T26**（`:344` T24 双向占比、**`:345` T25 并发**、`:346` T26 版本冲突）——
     两处讲的是不同的事，行号再怎么挪也对不上。
   - **裁定 64 的权威出处是"双文件"**：三阶段「相互关联但**分别记录**」= `appendices/01_接口契约与开发验收.md:375`；
     P0 阶段要求 = `01_开发技术方案.md:347`（另配 `:350` P3「用可手算短轨迹核对 target、mask、goal 和来源」，
     正是本文件 §11 与 `scripts/a2_s4a_vla_runtime_verify.py` 的 HAND_TABLE 依据）。
     字段清单另见附录一 `:364`（`ActionPlan`）、`:366`（`DecisionRequest`）。
   - **另一处 A2 自己的行号错**：本文 §2.4 与 §2.4.1 原先把 **T25 写作 `:346`，实为 `:345`**（`:346` 是 T26）。已就地改。
   - **D 的实质要求不变**（三阶段分别记录 + 能选择 n），只是出处要按 (相对路径, sha256-12, 行号) 三元组重写 —— 见 §0.6。

### 0.6 v4 引用身份三元组表（裁定 64：**只有行号的引用不可核验**）

本轮起，A2 对 v4 的每一条引用都带 **(相对路径, sha256-12, 行号)**；下表是本文件用到的全部出处，
sha256-12 为 23:2x 实测（`sha256sum` 前 12 位），行数一并给出以便发现文件被改：

| 文件（相对 `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/`） | sha256-12 | 行数 | 本文引用的行 | 用来支撑 |
|---|---|---|---|---|
| `appendices/01_接口契约与开发验收.md` | **`aae20ffe604f`** | 433 | `:103`（`H≥2n`）、`:105`–`:107`（C/E/D 三槽）、`:111`（迟到规则）、`:115`（每帧单一来源）、**`:345`（T25）**、`:364`/`:366`（字段清单）、**`:375`（三阶段分别记录）** | §0-2/§0-3、§2.4、§3.3、§3.4 |
| `appendices/02_异步动作时间轴与学习目标.md` | **`a6ab42165ab3`** | 354 | `:11`（§1 先看一次真实执行）、`:36`（§2 首版 RL 的状态与动作）、`:38`（§2.1 固定时间槽）、`:63`（§2.2 request/commit/activate 三事件） | §2.1、§3.3（C 槽必须读**已承诺**队列） |
| `01_开发技术方案.md` | **`0a9a2092e18a`** | 418 | **`:347`（P0：请求／入队／执行可区分，能选择 n）**、`:350`（P3：可手算短轨迹核对 target/mask/goal/来源） | §0-5 的更正、§11 的 HAND_TABLE 依据 |

- 同一份三元组也**写进了产物**（`runs/vla/a2_s4a_vla_runtime_20260929/s4a_verification.json → citations_file_identity_triple`），
  由脚本常量 `CITATIONS` 承载，不是文档里的一句话。
- **`:344`–`:346` 与 P0 无关**（那是附录一的陷阱表 T24/T25/T26）⇒ 见 §0-5 的跨文件更正。
- **§12 新增 6 条出处**（`timeout_isolation_scope` 的 v4 依据）：附录一 `:241` / `:332`(T12) / `:388`(T35)、
  附录二 `:215` / `:228` / `:235`、开发技术方案 `:239` / `:241`。**三个文件的 sha256-12 与行数与上表逐字相同**
  （`aae20ffe604f`/433、`a6ab42165ab3`/354、`0a9a2092e18a`/418，A2 于 **00:3x 重新 `sha256sum` 复核**，
  不采信本文早先的落笔值 —— 裁定 83§7「引用 sha 由引用方重算」）。完整三元组表见 **§12.2**。

---

## 1. 冻结契约里**可以直接复用**的面（只 import，不改）

| 冻结类型 | 位置 | S4 怎么用 |
|---|---|---|
| `EVENT_KINDS` | `contracts.py:10`–`:11` | 七个 kind **够用**，S4 **不新增** kind（新增 = 改冻结面，需 D 批） |
| `DecisionRequest(request_id, epoch, goal_id, observation, policy, version, slot, frame, deadline)` | `:13`–`:16` | **一个 chunk 请求 = 一个 `DecisionRequest`**；`frame` = **绝对控制帧**（v4 `:364` 的"绝对帧映射"）、`deadline` = **绝对帧**（不是秒；见 §3.4） |
| `QueueState(c, e, d, c_frame, e_frame, d_frame)` | `:18`–`:21` | **c/e/d 与 v4 附录一 `:105`–`:107` 的 C/E/D 三槽逐字对应**（C=已承诺由旧计划执行、E=本次预测 `[n,2n)`、D=`[2n,H)` 本次不执行）⇒ **不要另立命名** |
| `ActionEvent(..., requested/accepted/committed/activated/partially_executed, cancelled, expired, reason)` | `:23`–`:30` | `__post_init__` 会**拒绝未知 kind**（`:30`）⇒ 这是**现成的牙**，S4 直接受益 |
| `OutcomeEvent(..., reward, terminal, terminal_kind, source, policy, version, phase, grasp_verified, max_rise, failure_phase)` | `:32`–`:37` | **真实 reward / terminal 由 S4 直接构造它**（**不走** `ReplayDriver.finish`，理由见 §2.2）；`grasp_verified` / `max_rise` 正好接 A2 G3 的 `grasp_truth` 口径 |
| `TrainingView(..., td_eligible, bc_eligible, execution_mask, bc_mask, terminal_kind, isolation_reasons, gamma_slot)` | `:39`–`:44` | **`execution_mask` 就是 v4 `:83` 要的 `executed_indices`**（"块级保存 `executed_indices`／区间列表，**而非只有 `executed_length`**"）⇒ 逐索引采纳记录**已有位置**，S4 只需填满 |
| `ReplayDriver` | `:53`–`:92` | **仅作事件语义参照**；chunk 循环**不复用** `commit`/`finish`（§2.1/§2.2）。`activate` 的 `:77`「uncommitted action cannot activate」是**好牙**，S4 自己实现时**照抄这条不变式** |

**`runtime_adapter.py` 为什么不能扩展**（D 已实测 = mock，A2 复核同意，补三条实现级依据）：
`:20`–`:21` 构造签名写死 `policy="mock", version="v1"`、driver 缺省返回 `{"activated": True, "reward": 0.0}`；
`:19` 自述「**单 request、单 slot** 增量执行器」；`:58` / `:72` 把 `OutcomeEvent.source` **写死 `"mock"`**。
⇒ 它**没有 chunk 概念、没有 C/E/D 三槽推进、没有真实 reward 通路**。**S4 新建文件，不改它**（它在 C 的回归套里）。

---

## 2. 四条**实现级**硬事实（都读了原文；每条都会改变 S4 的写法）

### 2.1 `ReplayDriver.commit` 按 **epoch** 单键且不可变 ⇒ **不复用它**；chunk 代际走 ledger 的 `lease_generation`

`contracts.py:65`–`:72`：
```python
def commit(self, request_id, actions, frame):
    r = self.requests[request_id]
    key = r.epoch                                     # :68
    if key in self.committed: raise ValueError("committed queue is immutable")   # :69
```
⇒ **同一 `epoch` 只能 commit 一次**，而 π₀.₅ 在一个回合里会**反复**要新 chunk（每 `n` 步一次）
⇒ **`ReplayDriver` 承载不了 chunk 循环**（这与 §2.2 是同一条结论的两面：**S4 不复用 `ReplayDriver`**）。

> **A2 本节自纠（写草案时先猜错、读 schema 后改对，留档以免下一个人重犯）**：
> 本节初稿曾建议「把 `epoch` 重定义为 chunk 代际」。**读了 `harness/ledger.py` 的 schema 后该建议作废** ——
> **ledger 早就把三者分开了**，`frame_fact`（`ledger.py:46`–`:56`）**同时**有 `epoch INTEGER NOT NULL`、
> **`lease_generation INTEGER NOT NULL`**、**`chunk_id TEXT` / `chunk_index INTEGER`**、`abs_frame`、`request_id`。
> ⇒ **正确映射是：`epoch` 保持原语义不动，chunk 代际走 `lease_generation`（= v4 `:115` 的「递增**控制代际**」），chunk 身份走 `chunk_id`/`chunk_index`。**
> **重定义 `epoch` 反而会撞 ledger 的既有列**（`ledger.py:18` 处 `epoch` 命中 **18** 次）。

**S4 → `ledger.frame_fact` 的字段映射（照抄既有列，不新增）**：

| v4 附录一的要求 | `ledger.frame_fact` 的现成列（`ledger.py:46`–`:56`） | S4 填什么 |
|---|---|---|
| 绝对帧映射（`:364`） | **`abs_frame`** + `abs_time_ns` | 绝对控制帧号 + 墙钟 ns |
| 递增控制代际（`:115`） | **`lease_generation`** | **= chunk 代际**（每换一次 chunk +1） |
| 原始 chunk / 原始索引（`:81`–`:83`） | **`chunk_id`** + **`chunk_index`** | chunk 标识 + **该帧用的是 chunk 内第几个索引** |
| 每帧唯一来源（`:20`/`:115`） | **`source`** ∈ `FRAME_SOURCES`（`ledger.py:39`）= `("policy","harness","teleop","hold","recovery","script","mock")` | 旧计划执行 = **`policy`**（靠 `chunk_id` 区分是哪一个 chunk）；保持 = **`hold`**；接管 = **`harness`** |
| 逐索引采纳、不许只记长度（`:83`） | **`execution_status`** ∈ `EXECUTION_STATUS`（`ledger.py:40`）= `("activated","partially_executed","not_activated","unknown")` | 每帧一条；未执行的索引写 **`not_activated`**（**不伪装已执行**，`:325` T05） |
| 版本三件套（S4 `:145`） | **`contract_version`** + **`policy_version`**（+ `payload` 里放 `stats_version`/`shim_sha256_12`/`representation_version`） | 见 §3.5 |
| 真实动作 / 驱动命令 / 实测状态 | `proposed_action` / `a_rl` / `driver_command` / `measured_state` | 提案与实际下发**分列**（v4 `:375`「相互关联但**分别记录**」） |

**现成的牙（不用 A2 另造）**：`ledger.py:160`–`:163` 的 `append_frame` 对 `source ∉ FRAME_SOURCES` 与
`execution_status ∉ EXECUTION_STATUS` **直接 `raise ValueError`** ⇒ **词汇表是硬的**。
**⇒ S4 的 E4 判据（§4）必须用这套既有词汇，不许自造 `prev_chunk`/`this_chunk` 这类新 source 值**（本节初稿犯过，已改）。
**读侧三元组**：`harness/ledger.py` mtime **2026-09-29 16:40:32**、**485 行**、命令 `grep -n "epoch" harness/ledger.py`（**18 命中**）；
`harness/loop.py` mtime 2026-09-24 00:22:35、620 行、`grep -c epoch` = **0**；
`harness/runtime_adapter.py` 77 行、**8 命中**（全为透传）；
**`harness/queue_td_learner.py` mtime 2026-09-29 21:28:51（= C2 正在改，裁定 49.2）、661 行、`grep -c epoch` = 0** ⇒ 降级线，S4 不复用（D 已裁）。

### 2.2 `ReplayDriver.finish` 把 **reward 写死 0.0、source 写死 "mock"** ⇒ 不能承载真实 outcome

`contracts.py:81`–`:88`，其中 `:86`–`:87`：
```python
self.events.append(OutcomeEvent(request_id, r.epoch, r.goal_id, frame, r.observation,
                                0.0, True, terminal_kind, "mock", r.policy, r.version))
```
⇒ **reward 恒 `0.0`、`terminal` 恒 `True`、`source` 恒 `"mock"`**。
**这是典型的"恒真/恒定值"出口**：任何"跑通了、拿到 reward 了"的说法若基于 `finish()`，**都是假的**（同族实例见 C2 20:5x §3 的三条恒真闸）。
- **A2 的处置（草案）**：S4 **不调用 `finish()`**；真实 `OutcomeEvent` 由 S4 **直接构造**（dataclass 是 `frozen=True` 但**可构造**），
  reward / terminal / terminal_kind / grasp_verified / max_rise **全部来自 C2 的 `harness/env_gym_aloha.py` + `harness/ledger.py`**。
- **判定必须独立于 env 的 `reward==4`**（D 在 S4 `:144` 已要求）：A2 的 G3 已实证必要性 ——
  **随机臂靠"弹射"把 env reward 刷到 2.0**（方块被弹到 `(−68.69, +71.16, −134.76) m`、另一局 `box_z_max=27.96 m`），
  而 A2 自建的 `grasp_truth`（持续 ≥10 步）**把这 5 个假抬起全部拦掉**（`max_hold_run=0`）⇒ **`grasp_verified` 字段有现成口径可填**。

### 2.3 **相机面**：`AlohaEnv` 只交 `top`，腕部相机**从不渲染**（S4 的相机注入必须自建）

机器承载：`runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json → obs_surface_audit`（**只读审计 site-packages 源码 + XML**，闸 G9 绿）。

| 事实 | 数值 / 出处 |
|---|---|
| XML 相机总数 | **`ncam=7`**：`left_pillar, right_pillar, top, angle, front_close, left_wrist, right_wrist`（`MjModel.from_xml_path`，`MUJOCO_GL=disable`，未渲染） |
| task 实际渲染 | **3 个**：`top`(`tasks/sim.py:92`)、`angle`(`:93`)、`vis`←`front_close`(`:94`)，均 **480×640** |
| **交给 agent** | **1 个**：`obs_type="pixels"` ⇒ `{"top": …}`（`env.py:142`）；`"pixels_agent_pos"` ⇒ `{"pixels":{"top":…},"agent_pos":…}`（`env.py:145`）；`"state"` ⇒ `raise NotImplementedError()` |
| **渲染后被丢弃** | `angle`、`front_close` ⇒ **每控制步白渲染 2 张 480×640** |
| **从不渲染** | `left_pillar`、`right_pillar`、**`left_wrist`**、**`right_wrist`** |
| 运行时实测 | `obs_keys_top_level = ["top"]`、图像 `480×640×3 uint8`、luma mean **46.296**（闸 **G11** = 「只暴露 top」绿） |

**⇒ D 在 S4 `:143` 要求的相机键注入（`top`/`left_wrist`/`right_wrist`）不可能从 env 的 observation 拿到。**
**A2 已有可用实现**（G3 已完成 20 局采集；成功率主张另见裁定 46，不在此处）：`scripts/a2_pi05_zeroshot_eval.py:190` = `physics.render(height=h, width=w, camera_id=cam)`；
`:249`–`:250` = π₀.₅ 键映射 `observation.images.left_wrist_0_rgb → left_wrist`、`observation.images.right_wrist_0_rgb → right_wrist`。
**附带一个白送的吞吐收益**：绕开 `_format_raw_obs` 可省掉 **2 次无用渲染/控制步**
（A2 G3 实测：3 相机 224² = **14.83** ctrl-steps/s、单相机 224² = **34.58** ⇒ 渲染是主要成本）。
**注意**：`nmocap=0`（关节空间版 XML）⇒ **S1 的 EE/weld 通道必须用 `bimanual_viperx_end_effector_transfer_cube.xml`**（该文件有 mocap + weld），见 §7 对 S1 的点名。

### 2.4 **`H≥2n` 冲突**：π₀.₅ 出厂配置**不满足** v4 的异步调度定义（**本节最需要 D 裁的一条**）

**v4 附录一 `:103`–`:107` 原文**：「默认验证固定调度间隔 `n`、动作长度 **`H≥2n`** 和 deadline 的模式。在时刻 `t` 请求新预测：
**C** 是 `[t,t+n)` 已承诺由旧计划执行的真实命令上下文，**不是新预测的前 `n` 个动作**；
**E** 是当前预测索引 `[n,2n)`，在 `[t+n,t+2n)` 执行；**D** 是当前预测索引 `[2n,H)`，本次不执行；
**当前预测的前 `n` 项也不产生本次物理动作**。」

**π₀.₅ 出厂实测**（`env_manifest.json → semantic_probe.pi05_config_defaults`，`PI05Config()` 默认值）：
**`chunk_size = 50`（= H）、`n_action_steps = 50`（= n）、`num_inference_steps = 10`、`n_obs_steps = 1`**。
⇒ **`H ≥ 2n` = `50 ≥ 100` = 假**；且 `n = H` 时 **E = `[50,100)` 为空、D = `[50,50)` 为空** ⇒
**C/E/D 三槽退化**，变成"整块执行完再重规划"的**同步**模式。
**而 v4 `:345`（T25）明写**：「仅开启训练并发或仅开启执行并发 ⇒ …**前者不被称作已实现异步动作调度**。」

**要合规必须 `n ≤ H/2 = 25`。** 三档的预算算术（**频率 = 29.4118 Hz / `dt=0.034`，裁定 53**；
**每 chunk 推理墙钟 = 0.5233 s**，取自 G3 实测 `ctrl_hz_alignment_a2.json → latency_budget_claim.per_chunk_wall_s_from_g3_log`，**fp32**）：

| 档 | `n`（重规划间隔） | `H` | `H≥2n` | 重规划周期 = `n×dt` | 推理占比 | deadline 余量 | 判定 |
|---|---|---|---|---|---|---|---|
| **出厂** | **50** | 50 | ✗ **违反** | 1.700 s | **30.8%** | 1.177 s | 时间上宽裕，但**不满足 v4 的异步定义** ⇒ 不能声称"已实现异步动作调度" |
| **A2 推荐** | **25** | 50 | ✓（取等） | **0.850 s** | **61.6%** | **0.327 s（38.5%）** | **合规且仍可行**；代价 = 推理调用**翻倍** |
| 更激进 | 17 | 50 | ✓ | 0.578 s | **90.5%** | 0.055 s（9.5%） | 余量太薄，**一次抖动就 miss deadline** ⇒ 不推荐 |

**为什么不能靠加大 `H` 解决**：`chunk_size` 是 **action expert 的时间维**，π₀.₅ base 是**按 50 训的** ⇒
改 `H` 属于**改模型契约**，要先过 S3（小规模 BC/SFT）才谈得上，**S4 阶段不许动**。
**A2 推荐 `n=25`（`H=50`，取 `H≥2n` 的等号）**，理由：合规、余量 38.5%、且不改模型契约。**但 n 由 D 裁**（它是 `representation_version` 的一部分，S1/S3/S5/S6 必须同值）。

**必须同时声明的测量边界**（防止又一次口径搬运，裁定 53.3）：上表的 0.5233 s 是在
**(venv `pi05_sim`, `MUJOCO_GL=egl` 但渲染器实测 = mesa/llvmpipe（CPU）, mujoco 3.8.1, viperx 双臂, 3 相机 224², `loadavg 33–49`, fp32, chunk=50, `DT=0.02`/50 Hz)** 下测的
⇒ 上表三行现在统一标 **`prior_from_g3_cpu_render_caliber`（外推，已被下面的实测取代）**。

---

#### 2.4.1 **22:2x 更新（裁定 59-②）：egl(GPU, prefix-only) + 主线 29.4118 Hz 下的实测，两档 `n` 各 3 局**

**产物**：`runs/vla/a2_egl_latency_20260929/latency_mainline_egl_gpu_pi05.json`（run2，**闸 8/8 全绿**）
与归档对照 `gpu_run1_two_a2_defects/`（run1，延迟数据有效、两道附加闸假红，原因见该目录 `WHY_ARCHIVED.md`）。
**五元标注**：`(venv pi05_sim, MUJOCO_GL=egl + __EGL_VENDOR_LIBRARY_FILENAMES→.codex-persist/egl-libs/590.48.01/10_nvidia.json,
GL_RENDERER="NVIDIA A800-SXM4-80GB/PCIe/SSE2", GL_VERSION="4.6.0 NVIDIA 590.48.01", mujoco 3.8.1, viperx300s 双臂, 3 cam 224², DT=0.034)`；
**活对象复核** `control_timestep=0.034 / n_sub_steps=17 / control_hz=29.411765 ∈ QC`；显存峰值 **14,105.2 MiB**（reserved 14,392）。

| 档 | run | `mean_loop_fps` | **每控制步墙钟** | 占 34.0 ms 预算 | **每 chunk 推理** | 摊薄推理 ms/步 | 推理占比 | 实时比 | 负载对（`loadavg` / `nr_throttled`Δ） |
|---|---|---|---|---|---|---|---|---|---|
| **n=50**（出厂，**违反 `H≥2n`**） | run1 | 59.176 | 16.917 ms | **0.498** | 0.4972 s | 9.944 | 29.3% | 2.012× | 56.5/54.9/46.9 → 52.0/54.0/46.8，**Δ0** |
| **n=50** | **run2** | **52.187** | **19.562 ms** | **0.575** | **0.5574 s** | **11.148** | **32.8%** | **1.774×** | 39.5/45.6/45.3 → 40.1/45.5/45.3，**Δ45** |
| **n=25**（合规，A2 推荐） | run1 | 38.055 | 26.278 ms | **0.773** | 0.4817 s | 19.268 | 56.7% | 1.294× | 52.0/54.0/46.8 → 45.9/52.4/46.4，**Δ0** |
| **n=25** | **run2** | **24.295** | **41.404 ms** | **1.218 ⚠ 超预算** | **0.6832 s** | **27.330** | **80.4%** | **0.826×** | 40.1/45.5/45.3 → 42.5/45.1/45.1，**Δ344** |

**四条结论（每条都带口径）**
1. **瓶颈确实移到了推理**（D 的预判成立）：GPU 渲染下纯 `env.step` = **75–149 steps/s**（run2/run1），
   而每 chunk 推理 **0.48–0.68 s** ⇒ 一次推理 ≈ **36–170 个控制步**的 env 成本。
2. **`n=50` 在同步口径下舒适**（预算占比 0.50/0.58、实时比 1.77–2.01×），**但它违反 v4 `H≥2n`** ⇒ 不能声称"已实现异步动作调度"（v4 `:345` T25）。
3. **`n=25`（合规档）在同步口径下裕度很薄**：轻载 0.773、**CPU 节流时 1.218（超 34 ms 预算 22%）**、实时比 0.826×（慢于实时）。
   ⇒ **原外推的"余量 38.5%"在同步口径下不成立**；成立的是**推理占比 56.7%–80.4%**（即 deadline 余量 43.3%–19.6%）。
4. **本次是「同步阻塞」口径 = 保守上界**：循环是 render→infer→step 串行；v4 的异步语义（`H≥2n`）本就要求
   **下一 chunk 的推理与当前 chunk 的执行重叠** ⇒ 异步口径下的约束是 `推理墙钟 ≤ n×dt`（0.48–0.68 s ≤ 0.85 s，**成立**），
   而不是本表的"两者相加"。**异步口径本轮未测**（要等 `harness/vla_runtime.py` 落地才有承载体）⇒ 标 **`not_measured_async`**。

**给 D 的 `n_replan` 裁定输入（§9-1）**：
- 若 S4 **先做同步版**：`n=25` 会以 **0.83–1.29× 实时**跑（离线评测无正确性问题，只是墙钟），且节流时超 34 ms 预算 ⇒ **必须把预算判定写成"按秒登记的软约束 + 超载标记"**，不能当成硬失败；
- 若 S4 **直接做异步版**：`n=25` 的推理占比 56.7%–80.4% ⇒ **可行但重载时余量只有 19.6%**，建议同时把 `num_inference_steps`（现为 10）与 **bf16** 列为降延迟手段（**均未测**，bf16 会改数值口径 ⇒ 需另开一档 `representation_version`）。
- **`n=17` 档不推荐**（外推占比 90.5%，实测口径下必然超预算）。

**测量方差的诚实登记**：同一档两次采样的 `mean_loop_fps` 差 **12%（n=50）/ 36%（n=25）**，
主因 = **cgroup 12 核配额下的 CPU 节流**（`nr_throttled` Δ0 vs Δ344；全机 22:0x→22:2x 从 3,819 涨到 9,477）
+ `from_pretrained` 墙钟本身在 **60.17 s（G3, 19:2x）/ 82.65 s（run1）/ 184.97 s（run2）** 之间波动（NFS + CPU 争抢）。
⇒ **任何单次数字都不得当作常数引用**；S4 的闸应判"区间 + 负载对"，不判单点。

---

## 3. 接口草案（**代码级签名**；落地文件 = `harness/vla_runtime.py`，**新增**，不改冻结面）

### 3.1 策略侧协议（π₀.₅ / 未来任何 VLA 都按这个接）

```python
class VlaChunkPolicy(Protocol):                      # 只声明，不实现
    policy_version: str                              # 例："pi05_base@b211f3d4" / SFT 后 "pi05_sft_s3@<sha12>"
    stats_version: str                               # 归一化 stats 版本（C2 造；缺 stats 时必须是 "NONE"，不许空串）
    chunk_size: int                                  # H
    def reset(self, seed: int) -> None: ...
    def select_chunk(self, obs: ObsBundle) -> "ActionChunk": ...
```
**牙**：`stats_version == "NONE"` 时 runtime **必须拒绝进入评测/训练**并写 `isolation_reasons`
——这正是 G3 `0/20` 的根因（`features={}` ⇒ 静默 pass-through，`normalize_processor.py:305`–`:307`），**不许再让它静默通过**。

### 3.2 观测束（相机注入在这里，**不碰 env 的 observation**）

```python
@dataclass(frozen=True)
class ObsBundle:
    frame: int                                       # **绝对控制帧**（v4 :364）
    images: Mapping[str, np.ndarray]                 # 键 = "top" | "left_wrist" | "right_wrist"
    state: np.ndarray                                # 14 维 qpos（**原始 rad，未归一化**）
    state_raw_14d: np.ndarray                        # 与 state 同源，留给 C2 的"起态覆盖闸"（S2 :122）
    goal_id: str
    dt_s: float; control_hz: float                   # 必须 == 0.034 / 29.411765（裁定 53）
    representation_version: str                      # 见 §3.5
    render_backend: tuple[str, ...]                  # **五元标注**：(venv, MUJOCO_GL, mujoco 版本, 模型, 相机数/分辨率)
```
**相机来源**：`top`/`left_wrist`/`right_wrist` **一律走 `physics.render(camera_id=…)`**（§2.3），
**不用** `AlohaEnv._format_raw_obs`（它丢相机、还白渲染 2 张）。
**π₀.₅ 键映射**（已在 G3 的 20 局采集中实际使用，`a2_pi05_zeroshot_eval.py:249`–`:250`）：
`observation.images.top_0_rgb → top`、`…left_wrist_0_rgb → left_wrist`、`…right_wrist_0_rgb → right_wrist`。

### 3.3 chunk 与事件

```python
@dataclass(frozen=True)
class ActionChunk:
    request_id: str
    chunk_index: int                                 # 第几个 chunk（→ ledger `chunk_index`）
    chunk_id: str                                    # chunk 唯一标识（→ ledger `chunk_id`）
    lease_generation: int                            # **= 控制代际**（→ ledger `lease_generation`，v4 :115）
    epoch: int                                       # **保持 ledger 既有语义**，S4 只透传（§2.1 自纠）
    actions: np.ndarray                              # shape (H, 14)，**原始索引 0..H-1 全部保留**
    created_at_frame: int                            # = 请求时刻 t 的绝对帧
    planned_frames: tuple[int, int]                  # [t, t+H) 的绝对帧区间（v4 :364 "绝对帧映射"）
    slot_c: tuple[int, ...]; slot_e: tuple[int, ...]; slot_d: tuple[int, ...]
                                                     # **索引区间**，对应 v4 :105–:107 的 C/E/D
    dt_s: float; control_hz: float; n_replan: int; chunk_size: int
    inference_wall_s: float | None                   # 实测；None = 未测（**不许填 0**）
    deadline_frame: int                              # = created_at_frame + n_replan（**绝对帧**）
    policy_version: str; stats_version: str; shim_sha256_12: str
    representation_version: str

class ChunkedVlaRuntime:
    def __init__(self, policy: VlaChunkPolicy, env_adapter, *, n_replan: int = 25,
                 dt_s: float = 0.034, on_event: Callable[[ActionEvent | OutcomeEvent], None] = ...,
                 late_policy: str = "hold"): ...      # "hold" | "extend" | "terminate"（**冻结的迟到规则**，v4 :111）
    def reset(self, seed: int) -> ObsBundle: ...
    def step(self) -> "StepResult": ...               # **逐步下发**；只有跨越 n_replan 边界才请求新 chunk
    def finalize(self, terminal_kind: str, *, reward: float, observation: ObsBundle,
                 grasp_verified: bool | None, max_rise: float | None) -> TrainingView: ...
```

**事件时序（一个 chunk 的生命周期 → 冻结 `EVENT_KINDS`）**：

| 时刻 | 发生什么 | 发什么事件 | 载荷 |
|---|---|---|---|
| `t`（= `created_at_frame`） | 组 `ObsBundle`、发起推理 | **`requested`** | `DecisionRequest(frame=t, deadline=t+n, slot=…)`；`requested=True` |
| `t` | 推理返回、chunk 入队（**此刻还不产生任何物理动作**，v4 `:107`） | **`committed`** | `QueueState(c=C区间, e=E区间, d=D区间, *_frame=…)`；`committed=actions` |
| `t`（同帧，仅记录） | 承认"前 `n` 项本次不执行" | **`accepted`** | `accepted=(n_replan, chunk_size)`；**不写 activated** |
| `t … t+n-1` | 执行 **C**（**旧**计划的动作） | 每帧一条 **`activated`** + 一条 `frame_fact` | `source="policy"`（**词汇表见 `ledger.py:39`，不新造值**）、`chunk_id=<旧 chunk>`、`chunk_index=k∈[0,n)`、`abs_frame=f`、`lease_generation=g-1` |
| `t+n … t+2n-1` | 执行 **E**（本预测的 `[n,2n)`） | 每帧一条 **`activated`** + 一条 `frame_fact` | `source="policy"`、`chunk_id=<本 chunk>`、`chunk_index=k∈[n,2n)`、`abs_frame=f`、`lease_generation=g` |
| 中途被新预测/接管覆盖 | 未执行的索引**不伪装成已执行**（v4 `:325` T05、`:81`） | **`partially_executed`** + `frame_fact.execution_status` | 已执行的写 `activated`、**未执行的写 `not_activated`**（词汇表 `ledger.py:40`）；`TrainingView.execution_mask` 存**逐索引**（v4 `:83`：「而非只有 `executed_length`」） |
| 迟到（推理没在 deadline 前回来） | **不塞进过期索引**（v4 `:111`） | **`expired`** | `expired=True`、`reason="deadline_miss"`；按 `late_policy` 继续 hold / 结束 |
| 取消 / 接管 | 唯一控制权交接（v4 `:115`、`:20`） | **`cancelled`** | `cancelled=True`、`reason="takeover"` |

**不变式（照抄冻结实现里已有的牙，S4 自己实现时必须保留）**：
`activate` 前必须已 `commit`（`contracts.py:77`「uncommitted action cannot activate」）；
**每个绝对帧只采纳一个来源**（v4 `:115`、`:20`）；
**不得在一个正在执行的 chunk 内悄悄换模型或 normalizer**（v4 `:279`）⇒ `policy_version`/`stats_version` 在 chunk 内**恒定**，换版本必须换 `chunk_index` 并记 `representation_version`。

### 3.4 `deadline` 的单位必须写死（**这是一个会静默错的地方**）

`DecisionRequest.deadline: int`（`contracts.py:16`）是 **`int`** ⇒ **单位是"绝对控制帧"，不是秒**。
**若误填秒**（例如 `0.85`→`int()`→`0`）⇒ **每一帧都判 deadline miss、全部 `expired`**，而**日志看起来"跑通了"**。
⇒ S4 必须：`deadline_frame = created_at_frame + n_replan`，并在产物里**同时**记 `deadline_frame` 与 `deadline_s = n_replan*dt_s`，
**两者都要能被独立复核**（`deadline_s` 期望 = 0.850 s @ n=25）。**建议 B2 把这个做成一颗牙**（§6-M4）。

### 3.5 版本三件套（B2 在 S4 `:145` 要求"每条轨迹都要有"）

```
representation_version = f"gym_aloha_dt{dt}_29.4118hz_shim_v1|n{n_replan}|H{chunk_size}|cam3@224|{mujoco_gl}"
policy_version         = "pi05_base@b211f3d4" | "pi05_sft_s3@<sha12>"
stats_version          = "NONE" | "<c2 stats id>@<sha12>"
shim_sha256_12         = envs/gym_aloha_shim.py 的 sha256 前 12 位（本轮实测 = dc14466fcdcf）
```
**四者任一不同 ⇒ 数据不可混用**（v4 `:277`：「改变执行 `n`、deadline 或队列输入也改变学习条件，**不因 action shape 一样就继续混用旧数据**」；`:347` T26 同旨）。
⇒ **建议 B2 的闸按"四元组逐字相等"判，不按 shape 判**（shape 一致正是 T26 点名的陷阱）。

---

## 4. S4 的**出口判据**（A2 提议，D/B2 裁）

| # | 判据 | 怎么算绿 | 牙在哪 |
|---|---|---|---|
| E1 | **频率** | 活对象 `control_timestep == 0.034`、`n_sub_steps == 17`、折算 **29.4118 Hz** ∈ QC [29,31]；物理 `timestep == 0.002` **未被动** | 已实测 **11/11 绿**（`hz_shim_verification.json`，含"只改 constants 会静默留 50 Hz"的变异证明） |
| E2 | **`H≥2n`** | `chunk_size >= 2*n_replan` | n=50 出厂配置**必须红**（§2.4） |
| E3 | **三相机真的进 policy** | `ObsBundle.images` 三键齐、**逐帧非全零**、且三帧互不相同 | 缺任一相机 / 全零 / 三帧相同 ⇒ 红（G3 已有 `render_selfcert.json` 的同型判据可复用） |
| E4 | **每绝对帧唯一来源** | 逐帧 `frame_fact.source ∈ FRAME_SOURCES`（`ledger.py:39`：`policy/harness/teleop/hold/recovery/script/mock`）**且每个 `abs_frame` 恰好一条**；"用的是哪个 chunk" 由 `chunk_id`+`chunk_index` 区分，**不新造 source 值** | 一帧两条、零条、或 source 不在词汇表 ⇒ 红（`ledger.py:160`–`:163` **已经会 raise**） |
| E5 | **迟到不回填** | 注入一次人为超时 ⇒ 过期索引**必须**标 `expired`，**不得**出现在 `execution_mask` 的已执行位 | 若过期索引被标成已执行 ⇒ 红（v4 `:111`/`:325`） |
| E6 | **版本四元组** | 每条轨迹都带 §3.5 四元组；**混用即红** | 四元组不同却进了同一训练视图 ⇒ 红（v4 `:277`/`:347` T26） |
| E7 | **reward 通路非 mock** | `OutcomeEvent.source != "mock"` 且 reward 来自 ledger | 若沿用 `ReplayDriver.finish` ⇒ `source=="mock"`、`reward==0.0` **恒定** ⇒ 红（§2.2） |

**建议 B2 的变异体（至少 5 条）**：M1 `dt=1/30`（必须被 shim 拒，已实测**会抛**）；M2 只 patch `constants.DT`（必须仍 50 Hz ⇒ 红，已实测）；
M3 `n_replan=50`（E2 必须红）；M4 `deadline` 误填秒（E4/E5 必须红）；M5 拔掉一个相机键（E3 必须红）；M6 用 `ReplayDriver.finish` 出 reward（E7 必须红）。
**M1/M2 已由 A2 实测过（`refusal_proof` / `patch_mechanism_proof`），B2 可直接抄成断言，不必重跑。**

---

## 5. 频率与回合时长（接裁定 53；**两案并列，A2 不静默选**）

**已实测**（`hz_shim_verification.json`，`(venv pi05_sim, osmesa, mujoco 3.8.1, viperx 双臂, 1 相机 top@480×640)`，
`loadavg 47.6/48.9/47.9`、`nr_throttled Δ13`、**CPU-only、未跑 policy**）：
`control_timestep=0.034`、`n_sub_steps=17`、`physics timestep=0.002`（未动）、**实测 Hz = 29.411765 ∈ QC**、
`measured_hz_matches_contract=true`；零动作 20 步墙钟 **97.66 ms/控制步**（**10.24 ctrl-steps/s**、`realtime_factor=0.3482`）。
**这个吞吐数字只描述上面那个五元组**，**不得**与 G3 的 (egl, 3 相机 224², 10.39 loop_fps) 或 D 的 (osmesa, mujoco 3.9.0, Piper 单臂) 互搬（裁定 46.4/53.3）。

**回合时长后果（改 DT 的隐藏账，必须给 S1/S3/S5）**：`max_episode_steps` 是**步数**不是秒（`gym_aloha/__init__.py:16` = 300）。

| 案 | `max_episode_steps` | 覆盖仿真时长 | 影响 |
|---|---|---|---|
| **A：保持 300** | 300 | **10.2 s**（原 6.0 s，**1.7×**） | 任务变**更容易**（时间更宽裕）；与已发表的 300 步/6 s 口径**不可并列** |
| ~~**B：缩到 176**（A2 原推荐）~~ **已被裁定 58.3 推翻，本行只留痕** | 176 | **5.984 s ≈ 6.0 s** | 保持**任务时长**不变 ⇒ S1 示范 / S5 评测的"成功率"在不同 horizon 下**才可比**；但步数与 ALOHA 生态的 300 不同值，跨论文数字要带口径 |

**~~A2 推荐 B~~ ⇒ 已被裁定 58.3 推翻（见下）**。另：π₀.₅ `chunk_size=50` ⇒ 在 29.4118 Hz 下覆盖 **1.700 s**（与裁定 53-2 一致）。

**裁定 58.3（21:3x，D）已裁 —— 采 A 案**：`max_episode_steps` **保持 300、不缩放**；但
**① `episode_horizon_s=10.2` 必须写进每份 manifest；② 超时/失败一律按秒登记；③ 跨频率对比不得按步数并列；
④ 与 50 Hz 生态数字对比时必须显式换算并标注。**
上表**保留为决策留痕**（A2 不删自己被判翻的推荐，也不让别人再引它）。

**按 A 案（300 步 / 10.2 s）重算的 chunk 预算（给 S3 的集数估算用，别再用 176 步那版）**：

| `n_action_steps` | 每回合 chunk 数 | 每 chunk 覆盖 | 是否满足 v4 `H≥2n`（附录一 `:103`） |
|---|---|---|---|
| **50**（出厂） | **6.0** | 1.700 s | **否**（`H=50 < 2n=100`） |
| **25**（A2 提议） | **12.0** | 0.850 s | **是**（取等号） |
| 12 | 25.0 | 0.408 s | 是（但推理摊薄开销翻倍，见 §2.4） |

⇒ **S3 的小规模 BC/SFT 估算请按「每回合 6 或 12 次决策请求」算**（取决于 D 对 §9-1 `n_replan` 的裁定），
**回合时长一律写 10.2 s**（裁定 58.3），不要写「300 步」当时长。

---

## 6. 与 C2 / B2 的接口面（点名不代做）

| 谁 | A2 需要它给什么 | A2 给它什么 |
|---|---|---|
| **C2**（`harness/env_gym_aloha.py`，含频率 shim 消费 + 四类判定接 `ledger`） | ① `step()` 返回**真实** reward/terminal/terminal_kind + **几何真值**判定（独立于 `reward==4`）；② `state_raw_14d` 的**起态覆盖闸**结果（S2 `:122`）；③ 消费 `envs/gym_aloha_shim.py` 而**不是**自己再 patch 一次 DT（**两处 patch 会互相覆盖**） | ① `envs/gym_aloha_shim.py`（**已落地**，sha256-12 `dc14466fcdcf`）+ `make_env()`/`read_live_timing()`/`episode_horizon()`；② 相机渲染路径（`a2_pi05_zeroshot_eval.py:190`）；③ §2.3 的 `obs_surface_audit`（省得 C2 再踩"只有 top"） |
| **B2**（S4 全部闸 + 三版本记录） | ① 闸的**极性**由 B2 定稿（A2 只提议 §4 的 E1–E7 + M1–M6）；② `V-pi05-*` 系列里凡引用 transformers 的，按裁定 48 换成 **commit 判据**（A2 已把它固化成 `env_manifest.json` 的 **V10**，可直接抄断言） | ① §4 的判据表 + 已实测的 M1/M2；② `weights_receipt_channel_sidecar.json`（裁定 49.5 的 `mixed` 顶层，**receipt 未重写**，sha256 `11267d5b…` 前后一致）；③ **新 manifest 10/10 绿**（B2 手上那份 `a2_snapshot_1913_dist_drift_false_red` 是 `env_usable=false` 的旧快照，**请用新的重过闸**） |
| **B2**（S1 示范） | —— | **点名两条会挡住 S1 的实现事实**（见 §7），A2 不做 S1 |

---

## 7. 对 **S1**（B2 主责）的两条点名 —— D 的"免写 IK 通道"**在 `AlohaEnv` 里走不通**

D 在 `d_simchain_e2emin_20260929.md:100` 写：「`env.py:120`–`:124` 支持 `task="end_effector_transfer_cube"`（未注册但**可直接构造**）」。
**A2 实读原文，这条不成立**（**读侧三元组**：`gym_aloha/env.py`，21:1x，`grep -n`）：

```
120:        elif task_name == "end_effector_transfer_cube":
121:            raise NotImplementedError()          # ← **无条件抛，在 122–124 之前**
122:            xml_path = ASSETS_DIR / "bimanual_viperx_end_effector_transfer_cube.xml"
123:            physics = mujoco.Physics.from_xml_path(str(xml_path))
124:            task = TransferCubeEndEffectorTask()
```
⇒ **`:122`–`:124` 是死代码**；`AlohaEnv(task="end_effector_transfer_cube")` **在 `:121` 就抛**。
**还有第二道独立的墙**：`env.py:159`–`:164` 的 `reset()` 对非 `{transfer_cube, insertion}` **`else: raise ValueError(self.task)`** ⇒ 即使绕过 `:121`，`reset()` 也会抛。
**（D 在 `:104` 已点到 `reset()` 这道，但 `:121` 这道更早、且 D 的表述是"可直接构造"⇒ 两道都要写清。）**

**可行的替代路径（A2 只指路，不代做 S1）**：**不要走 `AlohaEnv`**，在本仓自有 shim 里**复刻** `env.py:133`–`:135` 那三行：
```python
physics = mujoco.Physics.from_xml_path(ASSETS_DIR / "bimanual_viperx_end_effector_transfer_cube.xml")
env = control.Environment(physics, TransferCubeEndEffectorTask(), float("inf"),
                          control_timestep=0.034, n_sub_steps=None, flat_observation=False)
```
**这条路一举两得**：既拿到 **weld/mocap**（该 XML **1 个 `<equality>` 块、内含 2 个 `<weld>`**：`mocap_left→vx300s_left/gripper_link`、`mocap_right→…right…`，`:5`–`:8`；
关节空间版 XML **0 个**、且 **`nmocap=0`**），又**顺带把 DT 改成 0.034**（`envs/gym_aloha_shim.py` 的口径）。
**一处计数精度**（不影响 D 的结论）：D 写「含 **2 处** `<equality>`」，实测是 **1 个 `<equality>` 元素 / 2 个 `<weld>` 子约束**（`grep -c "<equality>"` = 1、`grep -c "<weld"` = 2）。
**另**：`TransferCubeEndEffectorTask.before_step`（`tasks/sim_end_effector.py:38`–`:54`）的动作是 **每臂 8 维**（`[:3]` pos + `[3:7]` quat + `[7]` gripper）⇒ **EE 空间是 16 维，不是 14 维**；
录示范时要记的是 **`qpos` 的 14 维关节**（D 的 `:100` 说法正确），**别把 16 维 EE 动作当示范存**。

---

## 8. **S6 前置探针计划**（D 等待项 ④；**只是计划，本轮未跑，不占 GPU**）

D 的要求（`d_simchain_e2emin_20260929.md:158`）：①梯度能否到达待更新参数；②一次更新的显存峰值与耗时；③更新后导出/部署一致性；④对照必须是**同预算的动态 Harness-DAgger/BC**。

| 探针 | 判据（**能红**） | 成本 | 何时跑 |
|---|---|---|---|
| **P1 梯度可达性** | 只解冻 **action expert**（`action_expert_variant=gemma_300m`）⇒ `sum(p.requires_grad)` 的参数数 **> 0** 且 **< 全量**；对一个假 loss 反传后，**被冻结参数的 `.grad` 必须为 `None`**、可训练参数的 `.grad` **必须非 None 且范数 > 0** | CPU 可先做形状/标志位，**反传需 GPU** | S3 之后 |
| **P2 显存峰值 + 单步耗时** | `torch.cuda.max_memory_allocated()` 实测；**已知基线**：fp32 纯权重 **13,812.5 MiB**、G3 推理峰值 **14,105.2 MiB** ⇒ **反传要 optimizer state + 激活**，fp32 全量微调**几乎肯定爆 80 GB** ⇒ **必须先给出"只解冻 300M expert + gradient checkpointing + bf16"的实测数**，**不许外推** | GPU，**>10 min 事前在日报申报**（S3 `:130` 的要求） | S3 之后 |
| **P3 导出/部署一致性** | 更新后**同一 obs** 下，`导出产物.forward` 与 `内存中 policy.select_chunk` 的动作 **逐元素 `allclose(atol=0)`**（**不用容差**，因为同 dtype 同实现应当逐位相同；若有差 ⇒ 红）；并复核 **tied 别名**（`embed_tokens`↔`lm_head`）在导出后仍 `same_storage_data_ptr` | CPU/GPU 皆可 | 每次导出 |
| **P4 对照设计** | **同预算**（同 GPU 秒 / 同样本数）的 **动态 Harness-DAgger 或 BC** vs **一次 RL 更新**；**不许**拿 RL 比"冻结 SFT" | 依赖 P1–P3 | S6 正式跑时 |
| **P5（A2 追加）normalizer 联动** | 更新前后 `stats_version` **必须相同**（否则 v4 `:279`「不能在正在执行的 chunk 内悄悄换 normalizer」被违反）；且 **`stats_version != "NONE"`** | 纯只读 | 每次 |

**申报纪律**：P1/P2 要占 GPU ⇒ **跑之前先在 `daily_report.md` 申报**（预计时长 / 显存 / 可否 kill），**跑完销账**（`nvidia-smi` 实测 0 MiB）。
**本轮未跑任何一条**（S3 还没开始，且裁定 46.6 禁止用 zero-shot 成功率做路线判断）。

---

## 9. 待 D 裁（**A2 不自决**）

| # | 事项 | A2 的推荐 | 为什么不能自决 |
|---|---|---|---|
| 1 | ~~**`n_replan`（重规划间隔）**~~ **已裁（裁定 65-1）= 25** | **25**（`H=50`，取 `H≥2n` 等号）。**原 61.6%/38.5% 是 CPU 渲染口径的外推，已由 §2.4.1 的 GPU(egl) 实测取代（同步口径 `n=25` = 预算占比 0.773/1.218，重载超预算；异步口径未测）** | 它是 `representation_version` 的一部分，**S1/S3/S5/S6 必须同值**（裁定 53-4） |
| 2 | ~~**`max_episode_steps`**~~ **已裁（裁定 58.3）** | ~~B：缩到 176~~ ⇒ **A：保持 300**，并强制 `episode_horizon_s=10.2` 进 manifest、超时按秒登记 | **本行不再是待裁项**；保留为决策留痕 |
| 3 | ~~**确认 chunk 代际走 `lease_generation`、`epoch` 不动**~~ **已裁（裁定 65-4）** | **`lease_generation` = 控制代际 = chunk 代际**；`epoch` **保持 ledger 既有语义**（A2 初稿曾建议重定义 `epoch`，读 schema 后**自行作废**，见 §2.1 自纠框） | 跨线共用字段（`ledger.py` 里 `epoch` 命中 **18** 处）⇒ 语义定调归 D，并建议进参数表 |
| 4 | ~~**v4 行号更正**~~ **已裁（裁定 64）+ A2 的更正定性自我更正** | 权威出处是**双文件**：附录一 `:375`（三阶段分别记录）+ `01_开发技术方案.md:347`（P0）。**A2 原先把它定性为"同文件偏行"是错的，实为跨文件混引**（见 §0-5 / §0.6）；另 A2 自己把 **T25 写成 `:346`，实为 `:345`**，已改 | D 的文书 A2 不改；但 A2 的更正必须准确 |
| 5 | ~~**`late_policy`（迟到规则）**~~ **已裁（裁定 65-3）** | **`hold`**；迟到帧**不得**重标 `activated`、`late_policy` 进 `representation_version`、必记实际选择三态 —— **三条都已在 `harness/vla_runtime.py` 实现并由 G7 闸 + 变异自检验证** | v4 `:111` 要求"冻结的迟到规则"⇒ 冻结面语义 |
| 6 | ~~**S4 落地时点**~~ **已裁（裁定 65-5）** | **S4 立即开工，拆 S4a/S4b** ⇒ **S4a 本轮已落地并验证**（见 §11）；S4b（outcome 四类判定）blocked on C2 的 `harness/env_gym_aloha.py`（裁定 62） | 排期归 D |
| 7 | ~~**`prime_mode`（t=0 的 C 槽怎么 priming）**~~ **已裁（裁定 83§5①）= `hold`** | **`hold`**（帧 0..n-1 保持初始 qpos），`first_chunk` 保留为对照开关；**G13 闸已证明两案行为不同**（不是装饰品）。**已进 `representation_version`（`:prime=` token）**；可推翻条件 = S4b 实测首帧 hold 系统性错过抓取窗口 ⇒ 改 `first_chunk` 并**另立版本** | 附录二未指定 priming ⇒ A2 不自决。**产物 `status` 已由 `proposed` 改为 `ruled_83_5_1`** |
| 8 | ~~**`timeout_isolation_scope`（300 步/10.2 s 截断要不要隔离学习资格）**~~ **已裁（裁定 83§5②）= `td_only`** | **`TIMEOUT_ISOLATES_TD=True`、`TIMEOUT_ISOLATES_BC=False`**（**D 改 A2 的保守默认 `both_isolated`**）：TD 侧截断本该 bootstrap ⇒ 隔离保留；BC 侧截断轨迹仍是合法经验 ⇒ **保留但打标 `truncated_by_timelimit=true`**。**三条硬约束已做成机器强制（G18 闸 + 7 条红牙 + 绿见证），详见 §12** | 它直接决定 S4 能留下多少可学习数据，属学习语义 ⇒ 归 D。**A2 未自行放宽**；D 自确认执行、标 `d_selfconfirmed_pending_user_ratification`（本轮唯一需用户事后追认的口径放宽） |

---

## 10. 产物索引与复现

| 产物 | 内容 |
|---|---|
| `envs/gym_aloha_shim.py` | **本轮新落地**：29.4118 Hz shim（`apply_dt` / `make_env` / `read_live_timing` / `episode_horizon` / `shim_sha256_12`），sha256-12 = **`dc14466fcdcf`**，`representation_version = gym_aloha_dt0.034_29.4118hz_shim_v1` |
| `scripts/a2_hz_shim_verify.py` | 验证探针（DT 档位扫描 / patch 机制变异 / 拒绝非整数倍 / 真 env 实测 / obs 面审计 / 延迟预算） |
| `runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json` | **闸 11/11 PASS**（G1–G11）；含 `obs_surface_audit`（S4/S1 的相机与 mocap 硬事实） |

```bash
# CPU-only，不占 GPU，不跑 policy
MUJOCO_GL=osmesa /root/venvs/pi05_sim/bin/python scripts/a2_hz_shim_verify.py --n-steps 20
# 只想看判据有没有牙（不构造 env）：
MUJOCO_GL=osmesa /root/venvs/pi05_sim/bin/python scripts/a2_hz_shim_verify.py --skip-live
```

**本节不声称**：不声称 π₀.₅ 有任何能力（裁定 46）；
不声称 `n=25` 的 61.6% / 38.5% 在 S4 的真实配置下成立（那是 **G3 配置下的外推，标 `proposed_from_g3_measurement`，S4 必须重测**）。

> **23:2x 更正（本节原文已过期，append 式留痕）**：原文写「不声称 S4 已接线（`harness/vla_runtime.py` **尚未创建**）」——
> 该文件**本轮已创建并验证**（见 §11）。原句保留不删，在此更正。

---

## 11. **S4a 落地与验证结果**（2026-09-29 23:2x；裁定 65-5「S4 立即开工，拆 S4a/S4b」）

### 11.1 落地物（两个新文件，**冻结面一字未动**）

| 文件 | 行数 | sha256-12 | 内容 |
|---|---|---|---|
| `harness/vla_runtime.py` | **772** | **`a42a3dd17c47`** | `ObsBundle`/`ActionChunk`/`StepResult` + `VlaChunkPolicy`/`EnvAdapter` 协议 + `ChunkedVlaRuntime`（固定槽 `n=25`、C/E/D 三槽、`late_policy=hold`、版本三件套、`manifest_caliber()`、**`timing_report()`**、**视觉通道守卫**） |
| `scripts/a2_s4a_vla_runtime_verify.py` | **1282** | **`6f4ed1228a4c`** | **17 条闸** + **变异自检（19 个变异体）** + stub 逐格人写手算表 + 真实 `gym_aloha` 臂 + **运行时 cotenant 采样器** |

> **sha 的 `as_of`（裁定 78.11 `citation_sha_as_of_discipline`）**：上表两个 sha 是 **23:50:29** 落笔时刻重读的实测值
> （`harness/vla_runtime.py` mtime **23:40:06**、验证脚本 mtime **23:50:29**）。本节早先的版本曾写
> `630 ln / 809e097b1fd9` 与 `1077 ln / c8c15c8effa3`——那是**当天仍在编辑中的中间态**，已过期，在此更正（原文不删）。

> **sha 的第二次 `as_of`（2026-09-30 00:4x，裁定 83§5 落地后）**：上表的 `772 ln / a42a3dd17c47` 与
> `1282 ln / 6f4ed1228a4c` 是 **23:5x 的值，现已过期**（原文不删）。裁定 83§5 落地后的实测值为
> **`harness/vla_runtime.py` = 932 ln / `1a75f6181a36`**、**`scripts/a2_s4a_vla_runtime_verify.py` = 1394 ln / `a1959aaf97a4`**
> （两者均由 A2 于 **00:48:59** 那次验证运行时重算并写进产物 `target_sha256_12` / `generator_sha256_12`，
> **与磁盘逐字一致**）。**闸数 17 → 18、变异体 19 → 23**（新增 G18 与它的 4 个产物级变异体，见 §12.3）。

> **sha 的第三次 `as_of`（2026-09-30 01:05，落地裁定 84§4 的 `top_level_aggregate_must_declare_semantics` 之后）**：
> **`harness/vla_runtime.py` = 932 ln / `1a75f6181a36`（未再改）**、
> **`scripts/a2_s4a_vla_runtime_verify.py` = 1443 ln / `d708cbc6773f`**（上一条的 1394 ln / `a1959aaf97a4` 已过期，原文不删）。
> 复验产物 `generated_at=2026-09-30T01:05:17+08:00`：**18/18 闸 PASS、23/23 条闸有牙、`exit 0`**、
> `target_sha256_12=1a75f6181a36`（与磁盘逐字一致）、`frozen_surface_touched=[]`、`gpu_used=false`、
> `loadavg_1m 24.23→24.13`、Δ`nr_throttled` 6。
> **前一份（00:48:59、18/18、`73c25b3eec0f`）改名留档不覆写**：`s4a_verification_20260930_0048_18of18_pre_aggsem.json`。
> **被引用过的三份生成器源码已逐字节留档**在 `runs/vla/a2_egl_latency_20260929/generator_archive/`
> （附 `WHY_ARCHIVED.md`、`8c6585b5a512`）⇒ **裁定 84§0 引用的 `7e53558498ab` 在磁盘上仍可取**，
> 不会变成裁定 83.5 点名的首起「被引用字节串灭失」。

- **`contracts_py_modified = false`**（产物字段，实测 `harness/contracts.py` sha256-12 = `96c99ead93d2`，`git status` 对该文件、`harness/runtime_adapter.py`、`configs/` **均无输出**）；
  `harness/ledger.py` sha256-12 = `2a33c3f5516e`，同样只 import 不改。
- **不新造词表**：契约事件只用 `contracts.EVENT_KINDS` 的 7 类；账本事件/来源/执行状态只用 `ledger.py:31`–`:40` 的既有值。G4 闸专查这件事，变异体（塞 `teleported`）已证明会红。

### 11.2 验证结果（产物 `runs/vla/a2_s4a_vla_runtime_20260929/s4a_verification.json`）

| 臂 | 结果 | 关键数字（**成对带负载**） |
|---|---|---|
| **stub 人写手算表**（`n=2`/`H=4`/8 帧） | **G1 逐字段吻合**（含动作数值 `[2,-2]…[203,-203]`、请求数 4、`activated` 8 行 / `not_activated` 8 行） | 不占 GPU、秒级 |
| **真实 `gym_aloha`**（主线 `n=25`/`H=50`，55 帧） | **G15 绿**：`diffs_vs_hand_computation = []`、请求发生在 **f=0/25/50 ⇒ 3 次**、帧 0–24 = prime hold、25–49 = gen0 的 E（idx 25–49）、50–54 = gen1 的 E | `wall 6.8 s`、`123.6 ms/控制步`、`budget_fraction 3.64`；`loadavg_1m 39.81→39.74`、`nr_throttled Δ28` |
| **全部闸** | **17/17 PASS**，`exit 0` | `loadavg_1m 39.81→39.74`、`nr_throttled Δ33` |
| **变异自检** | **19/19 条闸"有牙"**（每条都被一处具体篡改打红，`all_have_teeth=true`） | 例：G12 把 `max_episode_steps` 改成 **176**（裁定 65-2 已作废的那个数）⇒ 红；G15 把 `control_hz` 改成 **50.0**（跨口径污染）⇒ 红；**G17a** 把 `realtime_closed_loop_claim` 改成 `true` ⇒ 红 |

- **`as_of 00:48:59` 的复验（裁定 83§5 落地后重跑，同一份命令行、同为 CPU 臂）**：**18/18 闸 PASS、23/23 条闸有牙、`exit 0`**；
  `gpu_used=false`、`policy_executed=false`、`capability_claim=false`、`success_metrics_collected=false`、
  `frozen_surface_touched=[]`、`contracts_py_sha256_12=96c99ead93d2`（`modified=false`）、`ledger_py_sha256_12=2a33c3f5516e`；
  `loadavg_1m 29.71→34.37`、`nr_throttled Δ4`。**上表的 `17/17`、`19/19` 与其中的负载对是 23:51:03 那次的值，两者不互搬。**
  旧产物**改名留档不覆写**：`s4a_verification.json`（23:51:03 / `45a1850fdde8`）→ **`s4a_verification_20260929_2351_pre83s5.json`**。
- **`budget_fraction 3.64` 不是主线口径，不得这样读**：本臂 `GL_RENDERER` 事实 = **`llvmpipe (LLVM 15.0.7, 256 bits)`**，
  且**取数路径 = `inside_real_render`**（在 `physics.render()` 刚返回、上下文仍 current 时读，裁定 71/72）⇒ 这是 **CPU 软渲染口径**。
  产物里已就地写明这一点，并与 GPU 口径交叉引用（`env_step_fps`：egl/NVIDIA run2 **65.865** / run1 **30.522**；mesa/llvmpipe **9.577**），
  **跨口径不得互搬**（裁定 46.4/53.6）。
- **一个新发现的效率事实**：55 个控制帧只发生 **4 次**三相机渲染（3 次请求 + 1 次 reset）——
  runtime **只在槽边界取观测**，A2 侧渲染成本被 1:`n` 摊薄；每控制步墙钟由 `env.step()` 主导
  （`gym_aloha` 在 `pixels_agent_pos` 下自己还会渲染，见 §2.3）。⇒ **S4a 的墙钟不能用来推"渲染是瓶颈"**。

### 11.3 本轮修掉的 5 个真 bug（都是"代码刚写完没跑过"的账；**另有 2 个在延迟脚本里，见 §11.3b**）

| # | 症状 | 根因 | 处置 |
|---|---|---|---|
| 1 | `NameError: _V` | 常量名写成 `_V`（实为 `_V4`） | 改 3 处引用 |
| 2 | `AttributeError: 'OutcomeEvent' object has no attribute 'kind'` | 契约事件流是 `ActionEvent｜OutcomeEvent` 混合，`OutcomeEvent` **没有** `kind` 字段（`harness/contracts.py:33`–`:40`） | 沿用仓内既有读法 `getattr(ev,"kind","")`（**rule_source: `harness/ledger.py:457`**）把两类分流，避免把 OutcomeEvent 混进词表闸 |
| 3 | G14 假红（账本 48 行 vs 内存 16 行 = **3×**） | SQLite 是追加的，同一文件被多次运行复用；`KeyError: schedule_events` 也是同族（产物里只有 `schedule_event_kinds`） | 旧账本**改名留档**（不用 `rm`，裁定 35.1）；计数改走 1:1 派生字段并记 `memory_event_count_source` |
| 4 | **G10 假绿（最危险的一个）** | 版本检查只比 `chunk.policy_version` vs `self.policy.policy_version`；若 policy 在 `select_chunk` 内部**先改自己的版本号再返回 chunk**，两者仍相等 ⇒ 检查形同虚设 | 改成**双比对**：还比「当前 policy vs reset 时快照」（`policy_version_at_reset`/`stats_version_at_reset`），任一侧漂移即报错并引附录一 `:279` |
| 5 | G8 假红 | 参照案例选了会被 stub 截断的那一局 ⇒ `terminal_kind=timeout` ⇒ 保守隔离把 `bc_eligible` 也压成 False，**红的原因与 stats 无关** | 把「循环帧数」与「env 截断长度」解耦（新增 `env_horizon`），另起一个不截断的干净参照案例 |

### 11.3b 顺带修掉的 2 个 bug（在 `scripts/a2_egl_latency_remeasure.py`，`294ceb53218a` → **`ded5ffa39660`**，1071 ln）

| # | 症状 | 根因 | 处置 |
|---|---|---|---|
| ⑥ | **`KeyError: 'load_after'`（任何模式都跑不完）** | `rep["load_after"]` 在**下面 ~70 行**才写、cotenant 块**先读**它。该 cotenant 块是上一轮新加的、**加完从未端到端跑过** —— 证据：既有 env_only 产物（21:59 / 22:16）里**根本没有 `cotenant_evidence` 字段** | 把**臂终点快照**移到真正"臂结束"那一刻（与 `load_before` 成对；语义也更准：不再把 gates 汇总与写盘耗时算进窗口），并记 `load_pair_semantics` |
| ⑦ | cotenant 结论**自相矛盾** | 判据输入只看 `procs_before/after` 是否为**空列表**，而"空"有两种含义（①采到了、卡上确实没别人 ②压根没采）⇒ 明明有 11 个运行时样本，结论却是 `unknown_not_collected` | 判据输入改成**周期样本 ∪ 前后两点**（`evidence_basis` 记录依据）；`classify_cotenant` 那条牙（**没有证据时不许输出 `false`**）**保持不变** |

- 修完 `--selftest` **9/9** 仍绿；CPU 冒烟臂实测 `cotenant_samples` **11 个**（1 s 间隔）、`collected_at_run_time=true`、`classification.contaminated=false`（**有证据的 false，不是"不许自称干净"那个 false**）。

### 11.4 本轮**新增的一道机器强制**（不是文档承诺）：视觉通道守卫

- **缺口**：`harness/vla_runtime.py` 原先**不校验 `obs.images` 是否为空** ⇒ `--no-render` 会静默退化成状态输入。
  **这正是 G3 `0/20` 的同型根因**（`normalizer_processor.config.features={}` 静默 pass-through），
  而任务书明令 A2 **不得自行退化成状态输入**。
- **处置**：新增 `REQUIRED_IMAGE_KEYS = ("top","left_wrist","right_wrist")` 与 `_guard_vision_channels()`，
  与 `_guard_stats_version()` 对称：**不抛异常**（S4a 仍要能采结构证据），而是**硬隔离**
  （`td_eligible=bc_eligible=False` + 写 `isolation_reasons` + 发**既有词表**事件 `verdict_identity_absent`，不新造 kind）。
  在 `reset()` 与**真正喂给 policy 的那份 obs**（`_request_and_commit`）两处都调用。
- **配套**：`--no-render` 时 `render_backend()` 的相机数按**实际会不会渲染**报 `0cam@224`（不再恒报 `3cam@224`）——
  否则 `representation_version` 会给状态-only 口径盖上视觉口径的章。
- **闸**：**G16**（缺键 ⇒ 硬隔离；键齐全 ⇒ 不因视觉被隔离；且不新造事件 kind），变异自检已证明有牙。

### 11.4b 裁定 75.4 / 75.5 / 76.1 / 76.2 / 76.3 / 82.5 的机器承载（**D 在 §10 点名"S4a 骨架必须含"**）

| 裁定 | 要求 | 承载（`harness/vla_runtime.py` / 验证脚本） | 牙 |
|---|---|---|---|
| **75.5** | 异步最小证据四项；**异步实测前禁止声称"实时闭环"** | `timing_report()`：`wall_ms_per_ctrl_step` 与 `amortized_inference_ms_per_ctrl_step` **分列**、`queue_drain_events[]`（**priming 的 hold 不计入枯竭**）、负载对、运行时 cotenant 采样；`realtime_closed_loop_claim` **恒 `false`** + `async_evidence_still_missing[]` | **G17a**（声称实时闭环 ⇒ 红）、**G17b**（删掉摊薄推理字段 ⇒ 红） |
| **75.4** | 34 ms/步是**软约束**，`budget_fraction>1` **不得判硬失败** | `overload_flag` + `budget_verdict="soft_constraint_not_a_hard_failure（…P4 真机不适用）"` + `episode_sim_seconds_covered` | **G17 故意不拿 `budget_fraction` 当判据**：真实 env 臂 `budget_fraction=3.32`、`overload_flag=true`，**G17 仍绿** |
| **76.3** | cotenant 必须**运行时**周期采 | `RuntimeCotenantSampler`（后台线程、默认 2 s、`nvidia-smi --query-compute-apps` + `ps` + `loadavg` + `nr_throttled`）⇒ `cotenant_samples[]`；**采样开销自己记账**（1 s 间隔实测占窗口 **12.0%** ⇒ 主线用 2 s）；`collected_at_run_time` **只在真有周期样本时才 `true`** | **G17c**（清空周期样本 = 退回事后重建 ⇒ 红） |
| **76.2** | **每个** GPU 批次开跑前重查卡 | 延迟脚本 `per_batch_gpu_yield_gate`：发现非本线 compute 进程**直接 `return 4` 拒绝开跑** | 冒烟臂实测 `non_self_gpu_procs_at_batch_start=[]` ⇒ 放行 |
| **76.1** | 归因强度**不得**写 `confirmed` | 每个样本硬写 `attribution_strength="inferred_from_pid_and_timeline"` + 容器 PID 命名空间的说明 | **G17 断言 `attribution_never_claimed_confirmed`** |
| **82.5** | 渲染速率带 caveat；像素判据要重定范围 | `ruling_82_5_render_rate_caveat`，**适用性按实测 `renderer_class` 判、不按 `MUJOCO_GL` 判**（裁定 71）。本轮 S4a 臂 = **`applies_to_this_arm: false`**（`GL_RENDERER` 事实是 llvmpipe，而 E 实测 mesa 路径三相机**全部逐位一致**），但 `must_follow_any_future_egl_arm=true` | 产物落 **`pixel_bitwise_criteria_used=false`** + 实查依据（**17 条闸无一比对像素**，`grep` 只命中 `obs_type="pixels_agent_pos"` 与一处文档叙述）⇒ D 那条条件指令对 S4a **不生效** |

- **实测的 `timing_report()`（真实 env 臂，CPU/llvmpipe 口径）**：`wall 112.97 ms/步`、`env_step 85.91`、`observe_render 3.88`、
  `cotenant_sampling 1.78`、**`unitemized_other 21.37`（≈19%，如实单列不摊进任何一项**：账本 SQLite 写入 + dataclass 构造 + `_resolve_frame` + `hold_action` + reset/finalize 一次性成本；
  继续拆需要给这些点也上计时器，**S4a 未做**）；`amortized_inference 0.032 ms`（stub 策略，**不是真模型**）；`queue_drain_count=0`。

### 11.5 **本节不声称**

- **`policy_executed = false`**：S4a **没有跑过真模型**（`--policy pi05` 未实现，属 S4b；usage 里原先那行是**文档谎报**，已改口）。
  真模型臂要跑时必须先 `eval "$(bash scripts/e_activate_gpu_render.sh --print)"`（裁定 70）、事前申报、并确认没有生效中的静默窗口（裁定 73）。
- **`success_metrics_collected = false`、`capability_claim = false`**，成功率栏 = `not_an_exit_criterion`（裁定 46 / 65-6③）。
- **`gpu_used = false`**：本轮全部为 CPU 臂，起止 `nvidia-smi` 均 **0 MiB**（无需申报，也无需销账）。
- **异步口径未实现**：`async_overlap = false`，S4a 是**同步阻塞**口径；迟到由实测墙钟 vs `deadline_s = n·dt` 判定。
- **`s4b_not_done`**：outcome 四类判定（成功/失败/超时/未知，且必须独立于 `reward==4`）**blocked on C2 的 `harness/env_gym_aloha.py`**（裁定 62）。

---

## 12. 裁定 83§5 的落地（2026-09-30 00:3x–00:4x）：`timeout_isolation_scope=td_only`、5 个设计点台账化、`policy_executed` 定义

### 12.1 A2 报上去的 5 个设计点，D 在裁定 83§5 **全部裁完** ⇒ `design_points_open_to_d()` 由「待裁清单」改为「裁定台账」

| 设计点 | 裁定 | 落地值 | `status`（产物字段） | 可推翻条件 |
|---|---|---|---|---|
| `prime_mode` | **83§5①** | `hold`（**进 `representation_version` 的 `:prime=` token**） | `ruled_83_5_1` | S4b 实测首帧 hold 系统性错过抓取窗口 ⇒ 改 `first_chunk` 并**另立版本** |
| `timeout_isolation_scope` | **83§5②**（**D 改 A2 的保守默认**） | **`td_only`** = `TIMEOUT_ISOLATES_TD=True` / `TIMEOUT_ISOLATES_BC=False` | `ruled_83_5_2__d_selfconfirmed_pending_user_ratification` | v4 原文明确禁止（须给三元组 + 行号）⇒ D 立即回退 `both_isolated` |
| `late_policy` | **65-3 + 83§5③ 维持** | `hold`（冻结面语义、进版本串） | `ruled_65_3__reaffirmed_83_5_3` | —— |
| `async_overlap` | **83§5④** | **`false`**；76.4 权威重测 + G17 异步字段跑过真推理之前**不得声称任何重叠／实时闭环** | `ruled_83_5_4__false` | 异步版实测过后另立版本 |
| `s4b_outcome_judging` | **83§5⑤** | `deferred`；**S4b 前置正式挂到 C2 线**（排在 T-C2-1 主线 stats 之后，不插队到 B2 的 npz 之前） | `ruled_83_5_5__deferred` | —— |

- 方法名 `design_points_open_to_d()` **保留不改**（验证脚本 `:532` / `:1259` 按这个名字读；改名会让既有引用扑空）。
- **`async_overlap` 的一条重要澄清（A2 不趁机改口）**：裁定 76.4 的权威重测 A2 已于 00:2x 完成
  （**4 次 clean 重复**，见 `daily_report.md` §13 与 `docs/a2_pi05_sim_readiness_20260929.md` §13），
  实测 n=25 档 `mean_realtime_ratio = 1.2491–1.2982`（均值 **1.2770**）。
  **但 `async_overlap` 仍是 `false`** ⇒ 这个比值是「**同步串行环**的 `control_timestep ÷ wall`」，
  **不构成实时闭环主张**；`timing_report().realtime_closed_loop_claim` 仍**恒 `false`**，G17a 的牙（把它改成 `true` ⇒ 红）保留。
  **裁定 84§6 的口径变更（A2 照办，且只照办被解除的那一半）**：D 已**解除裁定 75 对「实时闭环」措辞的禁令**，
  但**严格限定范围** —— **可以写**「主线 `n_replan=25` 的**同步闭环在预算内**」（须带完整口径 + `loadavg` 三点 + `nr_throttled` 对，
  A2 采用的那一句见 **§12.7**）；**仍然禁止写**任何「**异步重叠 / 线程并发 / async 实时闭环**」的声明。
  ⇒ `realtime_closed_loop_claim` **仍恒 `false`**，因为它承载的是**异步**语义、而异步未实现；G17a 的牙保留。
  **84§6 的可推翻条件一并登记**：若后续任一干净窗实测 `budget_fraction > 1`（换 `num_inference_steps`、换 bf16、
  加相机、加物体、或真机 P4 口径）⇒ 该条自动失效、回到裁定 75 的禁令状态并重测。

### 12.2 `td_only` 的 v4 依据（**A2 已按 D 给的可推翻条件逐条查过原文：未找到明文禁止**）

| # | 文件（相对 `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/`） | sha256-12 | 行数 | 行号 | 原文要点 |
|---|---|---|---|---|---|
| 1 | `appendices/01_接口契约与开发验收.md` | `aae20ffe604f` | 433 | **`:241`** | 「隔离该宏 **TD** 并保留逐帧事实、**可用监督**…**非终局超时不冒充 `done=1`**」 |
| 2 | 同上 | `aae20ffe604f` | 433 | **`:332`**（T12） | 「当前窗口**非终局超时**或接管 ⇒ **不用 `done=1` 伪终止**；不兼容宏样本隔离，**原始帧保留**」 |
| 3 | 同上 | `aae20ffe604f` | 433 | **`:388`**（T35） | 「…**BC质量与TD资格分开**」 |
| 4 | `01_开发技术方案.md` | `0a9a2092e18a` | 418 | **`:241`** | 「**BC 可信标签 mask、实际执行 mask、TD 资格是三种不同条件**」 |
| 5 | 同上 | `0a9a2092e18a` | 418 | **`:239`** | 「受影响宏样本隔离，**逐帧事实保留**；不伪造 done、零动作或整块执行」 |
| 6 | `appendices/02_异步动作时间轴与学习目标.md` | `a6ab42165ab3` | 354 | **`:228`** | 「Harness 抢占、**超时**、云服务掉线、日志缺失：属于**中断／删失**，**不因此把后续价值设为零**」⇒ TD 侧该 bootstrap |
| 7 | 同上 | `a6ab42165ab3` | 354 | **`:215`** | 「超时、接管、来源或边界不明的宏过程仍按既有协议隔离；本规则**不自动恢复其 actor／TD 资格**」⇒ TD 隔离保留 |
| 8 | 同上 | `a6ab42165ab3` | 354 | **`:235`** | 「如果先超时…**不能因为后来拿到成功标签，就追认成合法 terminal 样本**」⇒ 支撑硬约束③ |

- **结论**：D 给的可推翻条件（「v4 原文明确禁止」）**未触发**；上表 8 处**正面支撑** `td_only`。
  ⇒ **A2 按裁定执行 `td_only`，不请求回退。**
- **但 A2 如实登记一条口径差（不替 D 放大成"v4 逐字允许"）**：上表里的「超时」在 v4 原文中主要指
  **槽级**的推理超时 / deadline miss / 失联 / 接管，而 `timeout_isolation_scope` 管的是
  **回合级**的 gym TimeLimit 截断（`max_episode_steps=300` / `episode_horizon_s=10.2`，裁定 58.3 / 65-2）。
  **两者不是同一机制** ⇒ 上表属**原则迁移**（"非终局超时不冒充终止" + "BC 资格与 TD 资格分开"这两条原则的迁移），
  不是逐字同一。**若 D 认为该迁移不成立，回退成本 = 翻 `TIMEOUT_ISOLATES_BC=True` 一行**，
  `representation_version` 的 `timeout_bc=` token 由常量派生 ⇒ 会自动变成 `isolated`，**不需要人去改版本串**。

### 12.3 三条硬约束的**机器承载**（裁定 83§5②；不是文书承诺）

| 硬约束 | 承载物（`harness/vla_runtime.py`） | 谁看守 | 变异体（裁定 83.1 `tooth_must_be_mutant_proven`） |
|---|---|---|---|
| ① BC 记录须带 `truncated_by_timelimit=true` | `bc_record_extras()` 产出这组字段；`finalize()` 挂到 `self.last_bc_record_extras`，并写进账本 `episode_end` 事件 | `validate_bc_timeout_record()`（缺标／`False`／`None` ⇒ **抛**）；`finalize()` 内**就地自检**（`bc_eligible` 为真时立即调两个 validator，不等下游） | G18 内 3 条红牙：`flag_missing` / `flag_false` / `flag_none` 全部 `raised` |
| ② `representation_version` 须含 `timeout_bc=kept_flagged` | `TIMEOUT_BC_TOKEN` / `TIMEOUT_TD_TOKEN` **由常量派生**（`TIMEOUT_ISOLATES_BC=False ⇒ kept_flagged`）⇒ **版本串不可能与常量脱节** | **G12**（`need_rv` 里加了 `timeout_td=isolated`、`timeout_bc=kept_flagged`）+ **G18** 的 `rep_version_*` 两项 | G18b：把版本串的 `timeout_bc=kept_flagged` 改成 `isolated` ⇒ **红** |
| ③ 不得把 truncated 末帧当「成功／终止」标签 | `bc_record_extras()["must_not_be_labelled_as"] = ("success","terminated")` | `validate_truncation_not_terminal()`（`terminated` / `success_label` / `done` / `is_terminal` 任一为 `True`，或 `terminal_kind ∈ {success, terminated}` ⇒ **抛**） | G18 内 4 条红牙：`truncated_as_terminated` / `truncated_as_success_kind` / `truncated_as_done` / `truncated_as_is_terminal` 全部 `raised` |
| ④ 须有变异体证明「把 truncated 当 terminal」会红 | —— | **G18**（新闸） | 上三行合计 **7 条红牙**；另有 **4 个产物级变异体** G18a–G18d（见下） |

- **G18 的 10 项 `checks` 全绿**（`s4a_verification.json → gates.G18_timeout_scope_td_only_83_5_2`）：
  `timeout_terminal_kind` / `td_isolated` / `bc_kept` / `flag_present` / `bc_kept_flagged` / `scope_is_td_only` /
  `rep_version_timeout_bc` / `rep_version_timeout_td` / `clean_not_flagged` / `clean_both_eligible`。
- **G18 的 4 个产物级变异体**（`mutation_self_test`，篡改真实产物深拷贝、跑真实闸函数）：
  | 变异体 | 篡改 | 为什么这是最该防的 |
  |---|---|---|
  | **G18a** | `bc_record_extras.truncated_by_timelimit → False` | 「保留但**无痕**」⇒ 下游把 10.2 s 处被剪断的局当完整经验 |
  | **G18b** | 版本串 `timeout_bc=kept_flagged → isolated` | 版本串对下游**撒谎**（下游据此判断"这批 BC 含不含被剪断的局"） |
  | **G18c** | timeout 局 `td_eligible → True` | 滑向 `neither`：截断被当正常收尾、target 不再 bootstrap |
  | **G18d** | **干净参照**（`terminal_kind=none`）也被打 `truncated_by_timelimit=True` | 标记失去区分力 ⇒ 字段沦为装饰品（这条防的是"恒真牙"，与裁定 83.1 的 `Tr1` 同型） |
- **绿见证（裁定 83.2 `green_witness_required`）**：`validator_teeth.green_witness_valid_records = "passed"` ——
  合规的 timeout 记录、合规的非 timeout 记录**都不许抛**。**否则这两个 validator 只是"凡记录必抛"的单向装饰品。**
- **`stub_main` 臂的实测证据**（`terminal_kind=timeout`）：`td_eligible=false`、**`bc_eligible=true`**、
  `bc_record_extras = {truncated_by_timelimit: true, timeout_isolation_scope: "td_only", bc_kept_flagged: true,
  td_isolated_by_timeout: true, must_not_be_labelled_as: ["success","terminated"]}`；
  账本 `episode_end` 事件同步带 `truncated_by_timelimit=true` / `bc_kept_flagged=true` /
  `timeout_isolation_scope="td_only"` / `td_isolation_reasons=[timeout…]` / **`bc_isolation_reasons=[]`**。

### 12.4 **一个下游必须知道的读法陷阱**：`TrainingView.isolation_reasons` 是**并集**

`TrainingView`（`harness/contracts.py:40`，**冻结面**）只有一个 `isolation_reasons` 元组，而 `td_only` 之后
**td 与 bc 的资格会分叉** ⇒ `finalize()` 返回的 `isolation_reasons = td_isolated ∪ bc_isolated`。
**实测形态**（`stub_main`）：`bc_eligible=true` 但 `isolation_reasons=["terminal_kind=timeout（超时按秒登记，裁定 58.3）"]`。

- **这不是矛盾，但会被误读成矛盾**：只看 `isolation_reasons` 非空就判"这局被隔离了"是**错的**。
- **正确读法**：资格看 `td_eligible` / `bc_eligible` **两个布尔**；原因看**分开的**两列 ——
  账本 `episode_end` 事件的 `td_isolation_reasons` 与 `bc_isolation_reasons`。
- **为什么不改 `TrainingView` 加分列**：它是冻结面（`96c99ead93d2`，一个字节不动）⇒ A2 不改，
  改为**在 runtime 侧产出 `bc_record_extras()`**，并在本节把读法写死。
- **给 B2/C2 的点名（不代做）**：`harness/data_bridge.py` 的 `SAMPLE_COLUMNS`（`:657`–`:663`）目前**没有**
  `truncated_by_timelimit` / `bc_kept_flagged` / `timeout_isolation_scope` 三列。**那不是 A2 的文件，A2 不动它**；
  但 `td_only` 一旦生效、BC 侧开始收 timeout 局，这三列**必须**在数据桥侧补上，否则硬约束① 在跨文件处断链
  （runtime 侧有标、落盘侧没列 ⇒ 标丢失）。**接入时用 `validate_bc_timeout_record()` 兜底，缺字段当场抛。**

### 12.5 `policy_executed` 的定义（裁定 83§5 的 A2 澄清项；承载在延迟脚本，不在本文件）

- **定义（读法 A）**：`policy_executed` = 「本产物中是否发生了**由策略权重驱动的前向推理，且其输出被用于 `env.step()`**」。
  **不**采读法 B「以产出任务结果为目的执行策略」—— 读法 B 归 `capability_claim` / `success_metrics_collected`（恒 `false`，裁定 46）。
- **顶层语义**：= 各模式级同名值的 **OR**（等价 `policy_executed_any_arm`），**臂跑完后重算**；由 `gates.policy_executed_consistency` 看守。
- **本文件（S4a 验证）的取值**：**`policy_executed=false`** —— S4a 用的是 stub 策略与真实 env 的**接线验证**，
  **没有跑过真模型**（`--policy pi05` 未实现，属 S4b）⇒ 与延迟脚本的 `closed_loop` 臂（`true`）**不是同一回事，不得互搬**。
- 完整定义、事故复盘与牙／变异体见 **`daily_report.md` §13.6** 与 `scripts/a2_egl_latency_remeasure.py` 的 `POLICY_EXECUTED_DEFINITION`。

### 12.6 **本节不声称**

- **不声称 `td_only` 已被用户追认**：它是 `d_selfconfirmed_pending_user_ratification`（D 自确认执行、待用户事后追认的**口径放宽**）。
- **不声称 v4 逐字允许 `td_only`**：只声称「**未找到明文禁止** + 8 处原则支撑 + 一条如实登记的口径差（槽级 vs 回合级）」（§12.2）。
- **不声称 BC 数据因此可用**：`bc_eligible=true` 只是**资格**，不是质量判定；主线 stats 仍缺（`stats_version='NONE'` ⇒ 真实 env 臂仍被硬隔离），
  且 S4b 的四类 outcome 判定尚未接（裁定 83§5⑤ `deferred`，前置挂 C2 线）。
- **不声称「异步实时闭环」**（§12.1 末条；裁定 83§5④ + 84§6 的**保留**部分）。
  **按裁定 84§6 精确化**：**禁止的是**「异步重叠 / 线程并发 / async 实时闭环」（`async_overlap=false`、未实现）；
  **允许的是**「主线 `n_replan=25` 的**同步闭环在预算内**」，但**必须带完整口径**（A2 采用的那一句见 §12.7）。
- **不采成功率**：本节所有产物 `success_metrics_collected=false`、`capability_claim=false`（裁定 46）。

### 12.7 裁定 84§4 的两条新全线规则：A2 自己的产物**先合规**

裁定 84§4 把 A2 的 `policy_executed` 字段拆法升为两条全线规则：
**① `boolean_field_reading_must_be_declared`**（可能被读成两义的布尔字段必须写明所采读法、未采读法归谁、为何不可合并）；
**② `top_level_aggregate_must_declare_semantics`**（任何顶层汇总布尔/数值必须写明聚合语义 OR/AND/mean/worst/diff/count、
由闸或就地重算看守、**不得留初值**）。

| 规则 | A2 的承载物 | 落地方式 | 验证 |
|---|---|---|---|
| ① 读法申报 | `POLICY_EXECUTED_DEFINITION`（`scripts/a2_egl_latency_remeasure.py`） | 逐字进**每份**产物（含 `--selftest`） | `gates.policy_executed_consistency` + 自检 M4a–M4d（**13/13**） |
| ② 聚合语义 | `AGGREGATE_FIELD_SEMANTICS`（**两个脚本各一份**） | 逐字进产物顶层（延迟族 **13** 键、S4a 验证 **10** 键） | S4a：**18/18 + 23/23**、`exit 0`（`generated_at=01:05:17`）；延迟族：CPU `env_only` **代码路径核查**、`exit 0`、**7/7 闸绿** |

- **② 覆盖到的 A2 顶层汇总字段**（逐条写了 `aggregate` / `over` / `guard`）：
  **延迟族** = `gates_all_ok`(AND)、`policy_executed`(OR)、`nr_throttled_delta_total`(diff)、
  `non_a2_gpu_procs_in_window`(OR：两点快照 ∪ **全部周期样本**)、`collected_at_run_time`(count>0)、
  `contaminated`(OR：他线进程 ∪ `loadavg_1m` 漂移 ≥5)、`all_episodes_within_per_step_budget`(**AND = 每一集都达标**)、
  `mean_*`(mean，**不得单独引用**)、`loadavg_before/after`(point_sample，**不是均值也不是极值**)；
  **S4a** = `all_ok`(AND)、`n_gates/n_ok`(count)、`all_have_teeth`(AND，且 **`teeth = baseline_ok AND NOT mutant_ok`**)、
  `G18.ok`(AND：10 项 checks + 7 条红牙 + 绿见证)、`td_eligible/bc_eligible`(NOT-OR，**分列判空**)、
  `realtime_closed_loop_claim`(**constant_false，不是任何测量的汇总**)、`contracts_py_modified`(constant + 运行时实算 sha 双证)。
- **顺带把两个读法陷阱写进产物**（不只写在文档里）：
  ① **`TrainingView.isolation_reasons` 是 td ∪ bc 的并集**（§12.4）⇒ `bc_eligible=true` 与 `isolation_reasons` 非空**可以同时成立**；
  ② **`cases.real_env.budget_fraction=3.64` 是 CPU 软渲染口径**（实测 `GL_RENDERER=llvmpipe`）⇒ **不得与 GPU 干净窗的 `0.7703–0.8009` 互搬**（裁定 46.4/53.6/71）。
- **A2 采用的「同步闭环在预算内」那一句（按裁定 84§6 的完整口径要求写）**：
  「主线 `n_replan=25` 的**同步闭环在预算内**：`budget_fraction` **0.7766–0.8009**（rep5/rep4，**权威**）、
  余量 **19.91%–22.34%**、`all_episodes_within_per_step_budget=true`（**每一集**，不是均值）、
  **4 个独立干净窗一致**（旁证 rep2 `0.7703` / rep3 `0.7857`，散布 3.9%）、
  `GL_RENDERER=nvidia_gpu`、`MUJOCO_GL=egl` + prefix-only（`.codex-persist/egl-libs/590.48.01/`）、
  `DT=0.034` / `control_hz=29.411765` / `n_sub_steps=17`、`--max-steps 300`、3 集/臂、π₀.₅ 真权重（14,900 MiB）；
  负载对：rep4 `25.17/24.66/28.48 → 27.62/25.63/28.40`、Δ`nr_throttled` **4**；
  rep5 `27.62/25.63/28.40 → 26.88/25.89/28.17`、Δ`nr_throttled` **102（全在模型加载段，两臂内 Δ=0）**」
  —— **这句话里没有「异步」、没有「线程并发」、没有「async 实时闭环」**；`realtime_closed_loop_claim` 仍恒 `false`。
- **一条 A2 主动登记的、与裁定 84§3 同型的风险**：`AGGREGATE_FIELD_SEMANTICS` 里
  `cases.real_env.budget_fraction` 的 `aggregate` 写的是 **`worst（单臂单值）`** —— 严格说它**不是聚合值**，
  是单臂的 `wall ÷ 34 ms`。**A2 没有把它包装成「多集取最差」**（`mean_*` 那一族才是 3 集/臂的 `mean`）。
  这正是裁定 84§3 那类错误的入口（**把不同口径/不同粒度的量塞进同一个"汇总"名义下**）⇒ 所以在产物里逐字段写明粒度。

---

## 13. 裁定 95.3-④ / 95.3-① 的落地（2026-09-30 12:4x–13:5x）：**标准同步执行通路** + 四字段 + A2 自报两处缺陷

> 本节是 §1–§12 的**增量**（前文原字节保留）。派工原文 = `rl_harness_supervision/d_handoff_to_a2_20260930.md` 补单二-§二：
> 「把 S4b 的准备收到**『标准同步执行通路能跑』**这一件 —— 它是第 1–3 步的**共同前置**，也是本轮唯一必须新增的运行时能力。」

### 13.1 运行时新增的开关与互锁（`harness/vla_runtime.py` 2136 ln `3ff4e3b88c28`）

| 项 | `harness_second_half`（**默认**，S4a/S4b 现状） | `standard_sync`（裁定 95.3-④，第 1–2 步一律用它） |
|---|---|---|
| 执行的索引段 | `[n, 2n)`（= `slot_e`） | **`[0, n)`**（由**运行时**重盖章） |
| priming | 帧 `0..n-1` = prime hold（`t=0` 无源） | **无**（帧 `0..n-1` 由第 0 代直接供给） |
| `prime_mode` 合法值 | `hold` / `first_chunk` | **只** `none` |
| `H` 与 `n` 的约束 | `H ≥ 2n`（v4 附录一 :103） | **`1 ≤ n ≤ H`**（`n=H` 合法） |
| 超预算（推理 > 槽预算）的处置 | 本代 E 段作废 ⇒ `late_records` + 发 `expired` + 按 `late_policy` | **零丢帧、不发 `expired`** ⇒ 单列进 `sync_overload_records`（裁定 75.4 软约束） |
| 状态对齐风险 | **已登记的最高优先算法风险**：`f=n` 的真实状态是「保持了 n 步」，而 `idx n..2n-1` 是对「执行了 idx 0..n-1」的状态预测的 | **无**：`idx 0` 对应的观测就是发起推理那一刻的观测（推理阻塞 ⇒ 仿真时间不推进） |

- **互锁在构造期**（不是混搭后告警）：`standard_sync` + `prime≠none` ⇒ 抛；`harness` + `prime=none` ⇒ 抛。
- **槽位归属是运行时的语义**：策略给的 `slot_c/slot_e/slot_d` 在 `standard_sync` 下被**重盖**，
  并置 `ActionChunk.slots_restamped_by_runtime=True` ⇒ 「策略谎报槽位」不可能改变执行行为（G8 用一个
  故意报 `slot_e=(1,2,3)` 的策略验过：执行序列与诚实策略**逐帧全同**）。
- **缺 chunk 不许静默退化成 hold**：`standard_sync` 下 `_resolve_frame` 找不到本代 chunk ⇒ **抛**
  （hold 正是裁定 95.3-④ 要绕开的那个状态对齐问题的来源）。对照：`harness` 的 `f=0` 返回 `hold/prime` 是既定语义。

### 13.2 **A2 自报缺陷 ①（文书/码内假声明）**：`exec=` token 让**默认路径的版本串也变了**

- 落地时 `representation_version()` 的 docstring 写「默认值 = `harness_second_half` ⇒ **既有产物的版本串一字节不变**」
  ⇒ **实测为假**：该 token 是**无条件**拼接的，默认路径也多了 `:exec=harness_second_half` 一段。**已在同一处更正**（原句删除、换成实测对照）。
- **影响面三条（全部实测，`as_of` 12:5x–13:0x）**：
  1. **权威延迟带不受影响**：`runs/vla/a2_egl_latency_20260929/latency_quiet_window_rep{4,5}.json`
     **不含任何 `vla_runtime_v1:` 串**（只带 env shim 版本 `gym_aloha_dt0.034_29.4118hz_shim_v1`）
     ⇒ rep4 `0.8009`/`27.230 ms`、rep5 `0.7766`/`26.405 ms` 的身份不变。
     **但那条带的执行语义 = `harness_second_half`**；`standard_sync` 的延迟**必须另测、不得沿用**。
  2. **行为零回归**：S4a **17/17 + 21/21**、S4b **15/15 + 22/22** 全绿（osmesa、`gpu_used=false`）；
     改前/改后产物对照 = `runs/vla/a2_s4b_outcome_ledger_20260930_dbg7/` vs `…_execmode_reg2/`，
     两条版本串**只差这一个 token**、其余逐字相同。
  3. **历史 runtime 产物的版本串不可再按字节相等比较** ⇒ 见 13.3 的归一函数。

### 13.3 归一规则（机器可读，不是散文约定）

- `EXEC_TOKEN_ABSENT_MEANS = "harness_second_half"`：**缺 `exec=` token ⇒ 读作后半段调度**。
  理由（不是"猜默认值"）：`exec_mode` 这个开关是**本轮才引入**的，引入之前运行时**只存在**这一种执行语义。
- `exec_caliber_of_representation_version(rep)` → `{measurement_status, token_present, exec_mode, normalized_from_absent_token}`；
  **三值纪律**：串缺失 ⇒ `not_measured`；token 存在但不在词表 ⇒ **`not_measured`**（不许猜成默认值）。
- `cross_mode_transplant_allowed(a, b)` → `{same_exec_caliber, transplant_allowed, paired_comparison_allowed}`：
  语义不同 ⇒ `transplant_allowed=False`、`paired_comparison_allowed=True`（**只能报配对差值 + 每种子散布**，裁定 95.3-④ / 46.4 / 53.6 / 71）。

### 13.4 **A2 自报缺陷 ②（Ⅰ 类极性缺陷，已被自己的闸抓住并修）**：`ood_ratio` 恒 = 1.0

- 原写法 `out_of_distribution = … _tri([not x for x in ood_signals_status]) …`：`_tri` 的语义是「只会更严」
  （全 True ⇒ True），而喂进去的是 `not x`（= 「不在分布外」）⇒ 五个 OOD 信号**全为 False**（完全在分布内）时
  返回 `True`。**后果具体**：每一局都被标 OOD ⇒ `ood_ratio` 恒 = 1.0 ⇒ 裁定 95.3-① 要求的「单独报 OOD 比例」
  退化成恒等于 1 的常量（信息量为零）；偏差方向是"多标 OOD"、**不会**剔除样本 ⇒ 产物层看不出异常（静默）。
- **抓住它的不是复核，是手算期望**：`scripts/a2_standard_sync_exec_verify.py` G10 的 `ood_ratio == round(1/3,4)`
  在第一次跑就报红。修法 = 显式四分支（有 reason ⇒ True / 无信号 ⇒ None / 有信号未采 ⇒ None / 全采且全 False ⇒ False），
  前像 `tmp/vla_runtime_pre_oodpolarity_8f35376ba2bb.py`。
- **锚已留在脚本里**（G10 的 `polarity_anchor_in_distribution_is_false` + `tri_anchor_partially_measured_is_none`，
  配变异体 **G10d/G10e**）⇒ 这个缺陷类回不来。缺陷类归 **⑲ 同族**（判据的**极性**与对象空间不一致）。

### 13.5 验证与身份（全部本机取值，`as_of` 2026-09-30 13:5x）

| 件 | 身份 | 结论 |
|---|---|---|
| `harness/vla_runtime.py` | 2136 ln `3ff4e3b88c28` | 前像 `tmp/vla_runtime_pre_execnorm_78de1211df94.py` · `tmp/vla_runtime_pre_oodpolarity_8f35376ba2bb.py` |
| `scripts/a2_standard_sync_exec_verify.py`（**新**） | 1302 ln `65091484db7c` | **12/12 闸 + 20/20 变异体有牙**，`exit 0` |
| 其产物 | `runs/vla/a2_standard_sync_exec_20260930_run2/standard_sync_exec_verification.json` 5725 ln `a8763f060a31` | 真实 env 臂：30 帧 / **hold 帧 0** / chunk 2 / `outcome_class=failure` / ledger round-trip `measured` |
| `scripts/a2_s4a_vla_runtime_verify.py`（未改） | 1443 ln `d708cbc6773f` | **17/17 + 21/21**（回归产物 `runs/vla/a2_s4a_vla_runtime_20260930_execmode_reg3/`） |
| `scripts/a2_s4b_outcome_ledger_verify.py`（未改） | 1652 ln `7a232c54b6bf` | **15/15 + 22/22**（`runs/vla/a2_s4b_outcome_ledger_20260930_execmode_reg3/`） |
| `harness/bc_admission_gate.py`（**新**，T-A2-7） | 761 ln `37106c232891` | **17/17（2 正 / 15 反）**，`exit 0` |
| `runs/vla/a2_s3_bc_20260930/CRITERIA_PREREGISTERED.json`（**新**，T-A2-8） | 536 ln `22882a642b92`，`criteria_block_sha256_12=6153323126c1` | 生成器同目录 `3df80a2616f5`；**已存在 ⇒ 拒绝覆写（`exit 4`）** |

- 全部臂 `gpu_used=false`（osmesa 软渲染）⇒ 本节的任何 wall/budget 数字**不得**与 GPU 干净窗互搬。
- `renderer_class` 三点在 osmesa 下恒 `not_measured_no_gl_context`（EGL 权威读数仍只能由 S4b 的 GPU 臂提供，本轮**未上卡**）。

### 13.6 T-A2-7 的准入口径（裁定 93.4 / 96.1-④ / 97.3-3 / 97.5 / 85.4-3）

- **BC 被禁的判据只有三个**：`verdict_class1 = RED` **或** `admissible_for_bc = false` **或** `Tp5` 同源不成立。
  **顶层 `verdict = RED` 本身不再等于「BC 被禁」**（裁定 97.5）；但 class-2/3 的红照样登记、照样 S5 前清零。
- **不许 glob 挑份**：模块里**没有任何 glob 逻辑**；声明里没有的路径一律不读（`no_globbing_by_construction`）。
  且声明的臂内件与闸产物**必须在声明的 run 目录内**（NEG12 用「顶层同名件」这一具体形状验过 ⇒ 拒）。
- **存量标签 vs 重算值必须一致**：只重算会漏掉"臂内件自己写的标签是错的"，只读标签会漏掉"标签对数据质量盲"
  ⇒ 两边都取，**不一致就拒**（NEG4）。判定函数本身 = **C2 的 `norm_contract.bc_admission()`**，A2 只 import 调用。
- **`G14` 的语义判断归 F**（裁定 97.3-4 `checked_by=F`）：本闸只核「被引为证据的那一件存在、且 sha 与声明相等」，
  **不重判语义**。证据件可以是 F 的每轮台账，也可以就是同轮 `gate_verdict.json` 本身。
  ⇒ 这条预登记条件因此**有了消费方**（缺陷类 ⑳ 的解法）。
- **当前实测结论（`as_of` 13:47）**：`--probe-real`（无声明）⇒ `admitted=False`、
  `codes=['declaration_absent_or_incomplete', 'npz_identity_not_declared', 'control_hz_not_declared']`
  —— **C2 尚未按裁定 96.1-④ 广播 ⇒ BC 不开跑**。
  `--probe-real --trial-from-latest-run`（**A2 自拼的试算声明，不是 C2 的广播**）对
  `run_20260930_133156`（`verdict=PASS` / `verdict_class1=PASS` / `n_red_class1=0` / `fa59b263c5fa`）
  得到 `admitted=True`、`not_measured=[]`，其中 **npz 同源已核**：臂内件声明的 `checked_path_sha256_12=a84a26079550`
  与 A2 对 `runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` 的**独立复算相符**。
  **该试算结论只证明管路通，不得被引用成「BC 可以开跑」**（缺 C2 的成对广播 + F 的 `G14` 判定）。

### 13.7 本节**不声称**

- **不含任何 policy 指标**；`capability_claim=false`、`success_rate_column="not_an_exit_criterion"`、
  禁词「跑通 / 学会 / 达标」不用（裁定 46 禁令不变，**policy 指标仍 = 0**）。
- 「标准同步执行通路能跑」= **接线与执行语义**已被 12 道闸 + 20 个变异体证明（真实 env 臂的策略是
  **确定性 hold**，不是模型）⇒ **不是**任何能力结论。
- 真实 π₀.₅ 权重的 `standard_sync` 臂**本轮未跑**（按停点指令：不为旧关键路径上卡跑长作业；
  上卡前须按裁定 94.9-1 申报 + `GPU_WINDOW.json`，脚本 `scripts/a2_s4b_pi05_gpu_run.py` 1402 ln `cd5bca7371e2` 已备）。
