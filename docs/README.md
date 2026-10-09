# 文档导航

阅读顺序：**[项目总览](../README.md) → [项目演变](PROJECT_HISTORY.md) → [当前路线](ROADMAP.md) → [最小实验台账](../min_grasp_pi05/STAGE_PLAN.md)**。不需要从日报或智能体交接单开始。

## 当前维护的入口

| 文档 | 只负责什么 |
| --- | --- |
| [根 README](../README.md) | 项目定位、主线与目录入口 |
| [PROJECT_HISTORY](PROJECT_HISTORY.md) | 过去为什么转向、哪些结果改变了判断 |
| [ROADMAP](ROADMAP.md) | 下一步顺序、范围与验收出口 |
| [最小路线 README](../min_grasp_pi05/README.md) | 当前任务、关键结果、代码和运行环境 |
| [STAGE_PLAN](../min_grasp_pi05/STAGE_PLAN.md) | 实验批次、最终结论和证据索引 |
| [进展简报](../daily_report.md) | 当前快照；不再承担调度或逐条审计 |

## 历史证据：按需要读，不按文件数量推进

| 主题 | 关键入口 | 定位 |
| --- | --- | --- |
| 二维 Reach / 搬运 / 自学习调度 | [stage1](notes_stage1.md)、[stage2](notes_stage2.md)、[stage3](notes_stage3.md) | 历史 RL 基础 |
| 三维 RL 与残差 | [notes_vision](notes_vision.md)、[最终三臂审计](residual_three_arm_audit_20260924.md) | 失败、真值和天花板问题 |
| ACT 探索 | [模仿基线](act_imitation_report_20260924.md)、[history 消融](act_imitation_history_ablation_20260924.md)、[官方 ACT](lerobot_act_env_setup_20260928.md) | 辅助实验，不是当前主线 |
| 方向纠偏 | [09-29 复盘](lead_report_and_asks_20260929.md) | 当时的自查；资源请求不是当前待审批清单 |
| 复杂 VLA 接口 | [π₀.₅ 就绪](a2_pi05_sim_readiness_20260929.md)、[runtime](a2_s4_vla_runtime_interface_20260929.md)、[数据桥](ledger_data_bridge_20260928.md) | 可复用契约，不等于策略学习成功 |
| GPU 渲染 | [infra-gpu-render](infra-gpu-render.md) | 历史服务器环境，使用前核验 |
| 原始设计 | [v4 交付包](../RL_Harness_v4_20260924/README.md) | 设计证据，不等于实现或真机能力 |
| 交接与裁定 | [监管索引](../rl_harness_supervision/README.md)、[第一轮归档](archive/20261009/INDEX.md) | 历史追溯 |
| 精简前的全文 | [本轮归档](archive/20261009-route-review/INDEX.md) | 旧 README、路线、完整 STAGE_PLAN 等 |

以上带日期的专题和 notes 保留历史上下文；其中“当前、待办、在跑、禁止晋级”仅描述当时。若同一实验先有中途状态、后有最终审计，优先读最终结果；有口径修订时保留版本条件，不能挑最高数字。

## 文档维护边界

- 日报只写完成、结果、阻塞、下一步，引用实验台账，不复制整份报告。
- 实验台账只记结论变化；PID、ETA、逐条 ack、哈希串和重复广播不进入日常入口。
- 失败实验、改变结论的反例、数据/动作/成功契约与最终对照继续保留。
- 历史文件仍有被代码按路径或正文读取的情况，因此不批量删除带日期 Markdown。复杂路线旧调度/审计脚本依赖原日报章节、声明行号或身份串；精简后的日报不与这些机器输入兼容。复用时需显式迁移输入协议，不能把历史归档当作今天的资源授权。
