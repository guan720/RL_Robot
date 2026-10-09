# 智能体 A 对话上下文接续

2026-09-24，用户授权当前会话承接阶段 2 / ACT 相关实验智能体 A。

## 身份核对

- 原会话：`01a0d160-ebd1-74d3-b97e-a9933ed7afa7`。
- 原进程：PID `63978`，终端 `pts/45`；通过 `/proc/63978/fd` 持有的 rollout 与 writer lock 核对。
- 当前承接会话：`01a0d23a-7e16-7702-94ac-fbe5ac3485b5`。
- 已读取原会话的 ACT 架构讨论、实施记录、最后回复与现存实验产物。这里接续的是角色和工作上下文，没有切换当前会话 ID、接管原进程或恢复旧终端界面。原进程仍存活，未停止或向其发送指令。
- `01a0d161-5f14-77c3-9d8c-6402b34b0b2e` 为另一实施支线，负责 harness 接口与 residual 独立审计，不混为 A。

## 已恢复的工作状态

1. 用户要求逐步实施分层接触实验并提供关键结果。原 A 已实现脚本 base + bounded residual SAC，当前 residual 只在 `grasp/lift` 启用。
2. ACT 是后续动作段 base 的路线，原会话明确尚未接入 ACT，不能将当前训练称为 ACT 训练。
3. 主要文件：`envs/residual_lift.py`、`scripts/train_residual_lift.py`、`scripts/eval_lift_base.py`、`docs/notes_residual_architecture.md`。
4. 正式实验：`runs/20260924_142702_sac_lift_residual_grasp_lift/`。60k steps、seed 0、horizon 300、residual scale 0.25；接续检查时训练 PID `459677` 已不存在，`model_final.zip`、`eval_curve.json`、`result.json` 已保存。
5. 训练自带最终评测报告 20/20；训练中每 10k 的 5 局成功率为 0%、80%、100%、100%、100%、100%。这是原训练产物报告，尚未独立复核，不是 residual 学习增益的证据。
6. base-only 同样报告 20/20。必须完成固定 seed 真值审计和受控三臂对照；不能把 smoke 或相同成功率解释成 residual 有收益。

## 继续遵循的监管与协作边界

- 以 `rl_harness_supervision/supervisor_review_20260924.md` 为监管依据，并参考监管者接续记录。
- `RL_Harness_v4_20260924/` 保持只读。遵循全局数据保护与回收站规则。
- 优先 Lift 的真实抓取、阶段 verifier、base-only / from-scratch SAC / bounded residual 对照。暂停扩大 PickPlace、视觉、VLA 和真机范围。
- 成功需审查 grasp 真值、rise、失败阶段；harness 救场成功与 policy 独立成功分开统计。
- B 支线已提供 `scripts/audit_residual_lift.py`，独立审计属于其已有工作，避免重复运行或覆盖其输出。
- 后续 A 实施前先检查原进程是否启动新任务及 B 的最新审计产物，以免同一训练重复启动或并发修改相同文件。

## 下一步入口

先核对 B 对正式 checkpoint 的独立审计，再确定三臂对照缺口及 ACT base 的实施时机。本次只完成对话上下文接续，未启动新训练或改动实验代码。

如需在终端打开原会话，先从原终端正常退出 Codex 后执行（勿同时写入同一会话）：

```bash
codex resume 01a0d160-ebd1-74d3-b97e-a9933ed7afa7
```
