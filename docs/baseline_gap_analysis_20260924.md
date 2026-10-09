# 基线 v4 与当前实现的差距分析

日期：2026-09-24

本文只读取 `RL_Harness_v4_20260924/`，没有修改该文件夹内容。基线包是设计与验收契约，不是可运行实现；当前仓库的阶段 3 自检通过，不能等同于基线 P0–P6 已完成。

## 结论

当前最快的推进路径不是继续在 `harness/loop.py` 上增加采样策略，而是先补一层“事件与时间契约”。目前代码可以回答“这一局成功了吗”，还不能回答基线要求的“哪个 request 在什么时刻被接纳、提交、激活、部分执行、被抢占，以及这条记录是否有资格进入 BC 或 TD”。在这个缺口补齐前，任何 ACT/RL、DAgger 或 Harness 增益实验都可能把动作错位或未来信息泄漏误当成学习收益。

## 基线包自身的状态

`tools/verify_package.py` 在当前副本上返回 `ok: false`，主要是 MANIFEST 与实际目录不一致，以及历史上游摘录中的大量相对链接失效。这是交付包的封装/审计问题，不代表 v4 科学设计错误，也不应修改基线文件来“修绿”。后续引用以主方案和两个 appendices 的正文为准，并在项目记录中保留这次校验结果。

另一个需要显式记录的设计分歧是：基线接手说明暂不采用 ACT 路线，而当前工作已经由另一条工作线推进分层 ACT-RL。应把 ACT 作为项目的独立实现变更记录，沿用基线的 request/queue/BC/TD/发布契约，不能把“使用 ACT”写成 v4 原方案已经实现。

## 当前代码的主要缺口

| 优先级 | 当前证据 | 与基线契约的差距 | 影响 |
|---|---|---|---|
| P0 | `harness/tree.py::RunSkill` 在一个 tick 内调用 `run_episode` 跑完整局 | 基线要求固定时间槽、异步请求和跨 tick 的 Runtime/Gateway | 无法测 deadline、观测龄期、排队延迟和抢占；ACT chunk 只能被当成普通 action |
| P0 | `skills/base.py::run_episode` 只保存 episode 汇总和距离轨迹 | 缺 `request_id`、`epoch`、`goal_id`、观测快照、C/E/D、提交/激活回执、绝对时间和来源版本 | 不能重建真实 TD，也不能证明 BC 标签与输入同信息集 |
| P0 | 当前 `Skill` 主要是 `act(obs)`；新增的 `act_with_context` 仍是同步单步适配 | 基线动作是“下一时间槽接纳的请求”，不是任意时刻返回的动作 | 只能作为兼容层，不能替代队列环境 |
| P0 | `harness/tree.py` 的恢复路径调用独立比例技能，失败后继续流程 | 基线要求控制权交接、恢复/接管原因和物理事实分别记录 | `task_success_rate` 可用于系统可用性，但不能进入 policy TD/BC；目前没有统一资格分流 |
| P1 | `harness/env_factory.py` 虽有接触环境入口，但 `HarnessLoop` 仍硬编码 `make_reach_env` | 基线首任务应能通过统一 adapter/runtime 使用真实任务或可回放 mock | 接触任务无法直接进入同一 Harness 闭环，Reach 结果容易被误认为通用能力 |
| P1 | `harness/diagnose.py` 主要按初始距离/失败标签采样 | 基线要求 goal、错误类型、来源会话和时间线绑定 | 诊断采样不能替代 Harness 纠正；可能把同一回合片段泄漏到训练/评测 |
| P1 | `scripts/train_pickplace_sac.py` 以 SB3 SAC、demo buffer、BC/DAgger 为主 | 缺共享双向 policy、动态 BC 对照、真实 TD 资格和独立 TrainingView | 不能直接回答 H1“RL 相对持续纠正 BC 的增益” |
| P1 | `registry/publish.py` 主要接受 score bundle 和 env hash | 基线需要完整 ReleaseBundle/DeploymentManifest：模型、动作头、normalizer、调度协议、依赖和回滚身份 | 只发布 checkpoint 可能出现模型能加载但部署协议不一致 |
| P2 | 接触评测已有 grasp verified、配对 seed 和 guard delta | 还缺成本、接管删失比例、未知/待定样本、观测龄期和双向同 checkpoint 评测 | 指标能诊断仿真接触失败，但尚不足以评估连续自主窗口 |

## 最快且安全的实施顺序

### 1. 先做 P0 mock/replay，不等待真机

新增项目侧契约模块（不要放进基线目录），至少包含：

- `DecisionRequest`：冻结的观测快照、goal、policy/version、request_id、epoch、目标槽位和 deadline；
- `QueueState`：当前实际承诺的 C、当前候选的 E、预测/未承诺的 D，以及绝对控制帧；
- `ActionEvent`：requested、accepted、committed、activated、partially_executed、cancelled、expired；
- `OutcomeEvent`：观测、奖励/终局时间、驱动回执、来源和版本；
- `TrainingView`：`td_eligible`、`bc_eligible`、`bc_mask`、`execution_mask`、`terminal_kind` 和隔离原因。

用一个确定性 mock driver 回放基线附录的六个手算例子，重点检查：旧队列不被新 proposal 覆盖、未提交建议不能伪造 TD、提前终止保留原 request、抢占槽与普通 TD 隔离、`gamma_slot` 只折扣一次。

### 2. 把当前 `RunSkill` 改成可增量 tick 的 Runtime adapter

保留现有同步 `run_episode` 作为 legacy evaluator；新增 `start/step/finalize` 路径。行为树每次只推进一个固定槽，直到收到真实终局或显式 timeout。这样可以同时支持当前 Reach、robosuite Lift 和以后真机 Gateway，且不破坏已有阶段 3 回归。

### 3. 接通接触任务，但先只用 Lift

让 `HarnessLoop` 根据 `env_factory` 配置调用 `make_contact_env`，并将 `phase`、`grasp_verified`、`rise`、`failure_phase` 纳入事件日志。PickPlace 继续作为后续任务；它的脚本 ceiling 已修正为 carry height 0.22 后 32/32，不能再使用旧 0.719 上限。

### 4. 分离三类数据视图

- **普通 TD**：只接纳有实际 request、队列边界、执行结果和 next queue 的样本；
- **普通 BC**：同信息集、质量合格、动作时刻对齐的示范/纠正；
- **隔离视图**：未提交建议、事后读取未来反馈、被抢占槽、来源不明或 deadline miss。

不要让 `success`、`held` 或 Harness 自评直接授予 TD/BC 资格。失败样本仍可能是有效 TD，未执行的好建议也只能是 BC 或辅助监督。

### 5. 再做 ACT-RL 与基线 H1 对照

ACT 分层策略应实现一个 adapter：输入 `DecisionRequest + QueueState`，输出固定槽 action chunk，并回传 chunk 内每个控制帧的实际激活 mask。至少保留三臂：

1. 持续动态 BC/Harness 纠正；
2. 同一 BC 起点 + RL/Q 更新；
3. 分层 ACT-RL + 同一 Harness。

三臂必须共享初始示范、goal 集、纠正规则、预算和冻结双向评测；否则不能把收益归因于 RL 或 ACT。

### 6. 最后扩展发布和连续循环

将 registry 的发布对象从“checkpoint + score”扩展为部署 manifest，并检查动作维度、normalizer、chunk 长度、队列协议、环境/资产 hash、依赖版本和回滚版本。接触技能有稳定非零成功率后，再做 H2 reset-free/H3 程序积累；目前不要用 Reach 的发布结果声称 Harness 已改善接触学习。

## 不建议现在做的事情

- 不要先把 GPT 评分接入每个控制步；基线明确要求按决策状态和区间异步评分。
- 不要把 `act_with_context` 当成异步协议的完成版；它只是策略兼容接口。
- 不要把 guard/recovery 的成功混入策略训练成功率，也不要把救场动作自动写进前一动作的 TD。
- 不要在 action mask 上直接实现 C/E/D；基线要求按绝对帧号、队列事件和设备回执重建。
- 不要在没有真实设备参数时填写固定频率、deadline、chunk 长度或成功率；先用 mock/replay，未知值保持 null。

## 建议的首批验收清单

1. mock 回放能逐条复算异步附录六个例子；
2. 同一 request 的 request/commit/activate/terminal 事件可按 ID 重建；
3. late response、cancel、deadline miss、takeover 不会进入普通 TD；
4. 同一状态下，改变 C/D 预测不会改变 actor 的 E 之外 Q 梯度；
5. BC 标签能追溯到冻结观测和 action 时刻，未来反馈会被标为 privileged/isolated；
6. 同一 checkpoint 在 A→B/B→A、相同 seed 和相同资产 hash 上完成独立评测；
7. ReleaseBundle 缺动作协议或 normalizer 时拒绝发布；
8. 旧阶段 3 `selfcheck_stage3.py` 仍保持 16/16 PASS。
