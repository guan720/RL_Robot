# LeRobot ACT state/proprio-only 迁移验证

本轮停止修改现有 MLP ACT，也没有接入 residual SAC、视觉、guard 或 recovery。当前 Python 环境没有安装 `lerobot` 包，因此先生成 LeRobot Dataset v3 风格的可迁移交换数据和接口验证产物；未声称完成官方 LeRobot ACT 训练。

## 数据导出

脚本：`scripts/export_lift_to_lerobot.py`  
目录：`runs/infra/lerobot_act_lift_state_overfit/`

- train seeds：`1000–1023`，24 episodes
- validation seeds：`2000–2007`，8 episodes
- test seeds：`5000–5019`，20 episodes
- 每局：300 帧，20 Hz，时间步 0.05 s
- observation：`observation_state`，60 维 float32
- action：7 维 float32，OSC_POSE `xyz/rpy delta + gripper`；`+1=close`、`-1=open`
- action chunk：连续 `4×7`，297 个有效 chunk/局
- pinned object seed：`20260923`，几何写入 `meta/info.json`
- normalization：训练集逐维 mean/std，写入 `normalization.npz`
- receding horizon：4 帧
- temporal aggregation：`None`

数据目录包含 `meta/info.json`、`meta/episodes.jsonl`、逐 episode NPZ 和 normalizer，可作为后续安装 LeRobot 后转换为正式 Dataset 对象的输入。

## 单 episode overfit / 对齐检查

脚本：`scripts/check_lerobot_act_overfit.py`

episode 0 检查结果：

- 300 帧、7 维 action、`297×4×7` chunk
- chunk 首动作与 teacher action 最大误差：`0.0`
- `teacher_action_reproduced=true`
- 时间间隔：`0.05 s`
- phase：`approach → descend → grasp → lift → hold → done`
- normalization 文件存在

这验证了数据对齐和 action chunk 语义；它是 teacher replay overfit 检查，不是 learned policy 的性能结果。

## 20 局真实执行验证

使用导出的 test episodes、pinned seeds `5000–5019`、horizon 300，按 4 帧 chunk 逐帧执行：

| 指标 | 结果 |
|---|---:|
| success_raw | 20/20 |
| grasp_verified | 20/20 |
| success_grasp_verified | 20/20 |
| success_rise | 20/20 |
| mean_max_rise | 0.07632102 m |
| chunk 数/局 | 75 |
| 实际激活帧/局 | 300 |
| partial events | 0 |
| deadline events | 0 |
| recovery/guard | 0 |

逐局结果：`runs/infra/lerobot_act_lift_state_overfit/audit_truth20.json`。

## 判定

当前已完成数据格式、字段语义、归一化、时间对齐、teacher action chunk 和 runtime adapter 的最小验证；20 局 teacher trajectory replay 通过真实抓取真值。由于环境没有安装成熟 LeRobot runtime，尚未完成官方 ACT 模型的 learned overfit 或 learned 20 局验证。后续应先安装并锁定兼容 LeRobot 版本，再把该数据目录接入官方 ACT policy；在此之前不启动 residual SAC，也不把 teacher replay 称为 ACT 学习成功。
