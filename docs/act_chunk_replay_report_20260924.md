# ACT-style Action Chunk Replay 基线

本实验只验证固定长度动作块的执行适配，不包含 ACT 模型训练、RL、视觉输入、真机或 residual。

实现脚本：`scripts/act_chunk_replay_lift.py`  
参数：state observation、K=4、horizon=300、pinned seeds `5000–5019`、pinned object seed `20260923`。旧 scripted Lift controller 生成 teacher trajectory，replay adapter 每次请求 4 个动作，再逐帧实际激活。

## 结果

| 指标 | scripted base-only | K=4 chunk replay |
|---|---:|---:|
| raw success | 20/20 | 20/20 |
| grasp_verified | 20/20 | 20/20 |
| success_grasp_verified | 20/20 | 20/20 |
| mean max_rise | 0.07633000 m | 0.07632102 m |
| failure phase | 无 | 无 |
| harness/recovery 救场 | 0 | 0 |

逐局 raw/grasp 结果完全一致；逐局 `max_rise` 平均差为 `-8.98e-06 m`。chunk replay 每局执行 300 帧、75 个 request，所有 `actual_activation_mask` 均为 `[true,true,true,true]`。没有把未激活动作填充为已执行动作。

ACT replay 逐局 wall-clock 平均约 2.973 秒；该时间包含 replay 运行和真值检查，不能解释为真实机器人控制延迟。base-only 同口径逐局延迟已写入 `act_chunk_replay_20260924_k4_base_truth20.json`，如需延迟研究应在同一进程和相同计时边界下重复测量。

## 产物

- `runs/act_chunk_replay_20260924_k4.json`：ACT-style replay 的逐局、逐帧、逐 chunk 记录。
- `runs/act_chunk_replay_20260924_k4_base_truth20.json`：base-only 真值对照。

每个 replay row 记录 `request_id`、chunk 长度、实际激活 mask、phase、`grasp_verified`、raw success、`max_rise` 和 failure phase；没有启用 harness recovery。

## 判定

K=4 的动作块执行没有改变 scripted base 的 20/20 真值成功率、抓取率或上升高度，可作为后续 ACT base adapter 的工程基线。该结果不能称为 ACT 策略结果，也不能证明 ACT 学习能力。下一步若继续，必须先把真实 ACT/监督策略输出接到同一 adapter，再单独评测；通过后才考虑 `ACT base + bounded residual SAC`。
