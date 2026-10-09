# RL-Harness 项目监管复核（2026-09-24）

## 裁决

本次复核以工作区根目录 `RL_Robot/` 的真实代码、`runs/` 产物和最新诊断为准；`RL_Harness_v4_20260924/` 内原有交付资料保持只读。本项目已经形成可复现实验平台和分层 harness 原型，不能再描述为“只有一个 SAC 脚本”。但它仍未达到“稳定抓取、自动发现恢复策略、策略自主提升”的完整系统标准。

当前可信状态：

- 阶段 0/1：环境、训练、独立评测、曲线/轨迹/视频链路已建立；Reach 的 SAC 100% 只证明管线可用，不能证明算法优势。
- 阶段 2：理想与扰动 reset-free/正反向机制已验证；扰动环境才显示出 RL 与脚本基线差距，理想环境已触及手写控制器天花板。
- 阶段 2.5：robosuite Lift/PickPlace 的 state/pixels、SAC、示范、BC、DAgger、诊断和冻结评测已具备，但策略尚未稳定完成接触任务。
- 最新诊断已修正物体 RNG、PickPlace 几何/真值标签、`max_rise` 标定和三态发布判定；历史结果必须降级或按新口径重算。
- residual smoke 已出现，但不能把 smoke 或 `result.json` 当作 residual 学习有效性的证据；必须完成 base-only / from-scratch / bounded-residual 的同预算对照。
- harness、skills、registry 在工程上存在；其对接触任务学习收益尚未被独立 A/B 证明。

## 监管优先级

### P0：冻结事实与基准

所有后续实验必须记录：代码版本、配置、seed、环境参数、观测/动作接口、评测口径、固定测试集和运行资源。PickPlace 脚本基准使用修正后的 `CARRY_HEIGHT=0.22` 结果（32/32），旧的 23/32 只能作为历史缺陷记录。Lift/PickPlace 成功必须同时报告 `success_raw`、`grasp_verified`、`max_rise`、`ever_in_bin`、`failure_phase`、`flick_frac` 等字段。

若评测仍使用旧随机物体、宽度启发式抓取判据、旧 `calibrate_rise` 或 legacy 单态 gate，实验不得进入研究结论表。

### P1：只攻 Lift 的真实抓取能力

暂停扩大 PickPlace、视觉、VLA、LLM planner 和完整 RoboRSI 接入。先完成 Lift 的最小矩阵：

1. state + history：SAC from scratch；
2. state + history：demo + BC + RL；
3. state + history + phase：demo + BC + RL；
4. scripted/PD base + bounded residual SAC；
5. DAgger + BC。

统一 20–50 个固定 seed、同一出生分布、horizon、预算和独立测试集。主要判据是 `grasp_verified`、真实 rise 和失败阶段，不能用 shaped reward 的上升代替任务成功。

### P2：把接触技能做成可验证阶段

将 Lift 拆为 Approach、Grasp、Lift、Hold。每阶段必须有 precondition、动作接口、成功 verifier、failure label、timeout 和 recovery。高层状态机只切换已验证阶段；低层 RL 先只修正接触、对准和滑落。单一 MLP 同时学习接近到释放，暂不作为默认路线。

### P3：再做 residual RL 的科学对照

三臂必须同配置、同 seed 集、同训练/评测预算：

- base-only；
- from-scratch SAC；
- base + bounded residual SAC。

主指标为 `grasp_verified_success`，辅以 `max_rise`、保持时间、失败阶段和动作幅度。若 residual 没有相对 base-only 的稳定增益，暂停引入 RLT、Q-Planning 或更大模型。

### P4：最后验证 harness 的独立贡献

分两层：

- **执行编排 A/B**：同一冻结 base policy，比较 fixed staging、rule recovery、adaptive recovery、memory staging；统一 retry budget，测成功、恢复次数、覆盖和成本。
- **学习 A/B**：固定 verifier、训练器、seed、预算和评测集，只改变 harness 的采样/恢复策略；发布只看冻结独立评测。

Harness 救场成功不能计作 policy 独立成功；诊断采样提高吞吐也不能自动证明提高了 policy 能力。

## 必须阻止的路线偏差

- 不得因已有行为树、registry 或版本门禁，就宣称“自学习已完成”。
- 不得把抽象 2D 环境的 reset-free 收益外推到接触物理或真机。
- 不得继续增加示范数量来替代数据结构修复；20k 示范劣于 5k 已说明“更多示范”不是充分方向。
- 不得继续使用每步强 BC anchor；已有结果显示其与 SAC 梯度冲突并导致退化。
- 不得在 state 接触技能未稳定前转向 pixels、双相机、Genie Sim 或 VLA；视觉应单独测量帧率、样本效率和成功损失。
- 不得把历史 `plan_alignment` 数字覆盖 `notes_stage3.md`、`notes_vision.md` 和脚本缺陷交接单中的最新结论。

## 当前晋级条件

只有同时满足以下条件，才允许回到 PickPlace 长时程 harness：

1. Lift 在冻结测试集上达到可重复的非零 `grasp_verified` 成功，且不是 flick；
2. phase/verifier 能稳定区分 reach、grasp、lift、hold 失败；
3. residual 三臂对照完成并保留完整失败记录；
4. 修正后的 PickPlace 脚本上界、环境 RNG 和真值字段在跨进程重评中一致；
5. harness A/B 预先登记主要指标、试次数、停止规则和 inconclusive 处理。

## 对两个智能体的直接监管要求

下一次汇报必须分别提交：变更文件清单、可运行命令、固定 seed 结果、逐局指标、失败标签、资源成本、未解决风险，以及“未实施/已实现未验证/回放通过/真机通过”状态。只报告 reward、最后 checkpoint 或单次 success rate 不予通过。

当前运行中的训练任务不主动终止；但其结果在通过上述口径检查前只能标记为候选实验产物，不能写入正式研究结论或发布版本。
