# ACT imitation baseline 结果

本实验是 state-based ACT imitation，使用 scripted Lift teacher 轨迹监督训练连续 `K=4`、每步 7 维的动作 chunk。没有使用 RL、residual、guard 或 recovery。

## 配置与产物

- 训练脚本：`scripts/train_act_lift.py`
- 真值审计脚本：`scripts/eval_act_lift_truth.py`
- 训练目录：`runs/infra/act_lift_k4_state_seed0/`
- train seeds：`1000–1023`；validation seeds：`2000–2007`
- 测试 seeds：`5000–5019`
- horizon：`300`；chunk length：`4`；state observation；pinned object seed：`20260923`
- 训练样本：7,128 chunks；验证样本：2,376 chunks；最佳验证 MSE：0.025899
- 保存：`model_best.pt`、`model_final.pt`、`config.json`、`train_result.json`、`audit_truth20.json`

## 真实评测

| 指标 | ACT imitation | scripted base / K=4 teacher replay |
|---|---:|---:|
| success_raw | 1/20 | 20/20 |
| grasp_verified（曾观测到） | 3/20 | 20/20 |
| success_grasp_verified | 0/20 | 20/20 |
| success_rise | 1/20 | 20/20 |
| mean_max_rise | 0.00345035 m | 约 0.0763 m |
| failure phase | 19 局 approach；1 局无失败标签 | 无 |

ACT policy 每局都提交 75 个 K=4 chunk，实际激活 300 帧；`partial_events=0`、`deadline_events=0`。`cancel_events=1` 是环境 episode 结束时的终止记录，不是 harness 救场；没有启用任何 recovery。

逐局结果在 `runs/infra/act_lift_k4_state_seed0/audit_truth20.json`，其中包含 `request_id`、chunk 长度、实际激活 mask、phase、`grasp_verified`、失败阶段、rise 和事件字段。

## 判定

该 ACT imitation baseline 未通过“稳定真实抓取”验收。teacher replay 的 20/20 成功没有迁移为 learned chunk policy 的成功；主要失败集中在 approach，说明当前状态归一化、单帧状态到动作段的监督、以及 chunk 边界的闭环误差仍需分析。当前不得接入 residual SAC，也不能把 teacher replay 或 scripted base 称为 ACT 学习结果。
