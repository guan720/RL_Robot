# RL_Robot：VLA 抓放与 Harness 辅助学习

**当前主线是 `min_grasp_pi05/`：先在 Panda 单臂仿真中验证 π₀.₅ 的抓放、纠正数据学习，再推进残差 RL、RLinf-VLA 与 PIPER 真机。**

截至本地阶段文档 2026-10-07，已得到纠正数据 BC 的冻结评测结果；π₀.₅ 主线的 RL 尚未启动。PIPER 正在调试是用户提供的当前状态，本仓尚无对应真机成功率证据。整理日期：2026-10-09。

## 先读这四处

| 想了解什么 | 文档 |
| --- | --- |
| 项目为什么多次转向，哪些探索留下了价值 | [项目演变](docs/PROJECT_HISTORY.md) |
| 现在做什么，下一步怎么进入 RL 和真机 | [当前路线](docs/ROADMAP.md) |
| 最小验证做到哪里，每项结论的依据 | [最小路线说明](min_grasp_pi05/README.md) → [实验台账](min_grasp_pi05/STAGE_PLAN.md) |
| 最新摘要或某个技术专题 | [进展简报](daily_report.md) · [文档导航](docs/README.md) |

## 路线演变

二维 Reach/SAC → 二维搬运与扰动 → 三维 Lift/PickPlace 的 RL 探索 → ACT 与评测诊断 → 复杂 VLA 系统路线 → **π₀.₅ 单臂最小验证** → 残差 RL / 平台与真机接入（待推进）。

这不是一条连续成功升级的训练流水线。ACT 和复杂 VLA 阶段包含方向偏移与收缩；早期确实做过 RL，但不能据此把当前 π₀.₅ 的 BC 结果称为 RL。

## 当前成果怎么读

- 纠正数据 BC：匹配控制组 **48/80 → 65/80（+21.25 个百分点）**；关闭接管后评测。三训练 seed 的纠正模型为 65/80、65/80、64/80。
- 当场 Harness 接管：表面 39/60 → 46/60，但接管局配对救回 6、做坏 6，**未证明净成功率增益**。
- 两者回答不同问题：一个是纠正数据能否改善策略，一个是运行时接管能否立即救场。当前 Harness 是规则检测器与脚本专家。
- 上述主结果使用反向放宽判据；每组 80 次执行来自 20 个初态各重复 4 次。数字来自阶段文档，尚未重算原始 runs。

## 目录与定位

| 目录 | 定位 |
| --- | --- |
| `min_grasp_pi05/` | 当前学习主线；代码、数据与其运行环境独立 |
| `envs/`、`scripts/`、`eval/` | 早期 RL/ACT、复杂 VLA 与诊断工具的混合历史资产，按具体文档选用 |
| `harness/`、`registry/`、`skills/` | 调度、执行、数据契约与版本管理资产；可按需复用 |
| `RL_Harness_v4_20260924/` | 历史设计基线；设计内容不代表全部实现 |
| `rl_harness_supervision/`、`work/decisions/` | 历史分工、审查与决策记录；不是当前待办 |
| `docs/archive/` | 完整旧日志及被精简文档的原件 |

## 运行入口

当前最小路线从 [min_grasp_pi05/README.md](min_grasp_pi05/README.md) 和 [code/env.sh](min_grasp_pi05/code/env.sh) 开始。脚本面向原 Linux 服务器；本地 Windows 是下载副本，数据与 runs 尚未齐全，不直接执行旧排队脚本。

早期 Reach/SAC 的命令、依赖和结果保留在 [notes_stage1](docs/notes_stage1.md)、[notes_stage2](docs/notes_stage2.md)。旧服务器环境、旧 G2 目标和历史“进行中”不再作为当前项目默认配置。
