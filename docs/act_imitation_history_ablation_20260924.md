# Learned ACT history 消融

本轮仅比较 state-based ACT imitation 的 `history=1` 与 `history=4`。两者均使用相同 scripted teacher、K=4、训练 seed 0、train seeds `1000–1023`、validation seeds `2000–2007`、test seeds `5000–5019`、horizon 300 和 pinned object。没有使用 residual SAC、guard、recovery 或 RL，也没有读取未来反馈或 teacher phase；history 仅由当前及过去已观测 state 组成，首帧用当前观测复制填充。

## 训练

| 模型 | train chunks | val chunks | best val MSE |
|---|---:|---:|---:|
| history=1 | 7,128 | 2,376 | 0.0258990 |
| history=4 | 7,128 | 2,376 | 0.0107799 |

checkpoint：

- `runs/infra/act_lift_k4_state_hist1_seed0/model_final.pt`
- `runs/infra/act_lift_k4_state_hist4_seed0/model_final.pt`

## 20 局真值评测

| 指标 | history=1 | history=4 |
|---|---:|---:|
| success_raw | 1/20 | 1/20 |
| grasp_verified（曾观测到） | 3/20 | 3/20 |
| success_grasp_verified | 0/20 | 0/20 |
| success_rise | 1/20 | 0/20 |
| mean_max_rise | 0.00345035 m | 0.00239830 m |
| approach failures | 19 | 19 |
| descend/grasp/lift failures | 0 | 0 |
| chunks per episode | 75 | 75 |
| actual activated frames | 300 | 300 |
| partial events | 0 | 0 |
| deadline events | 0 | 0 |

逐局 JSON：

- `runs/infra/act_lift_k4_state_hist1_seed0/audit_truth20.json`
- `runs/infra/act_lift_k4_state_hist4_seed0/audit_truth20.json`

两模型均在 19 个相同 seed 上于 approach 阶段失败；唯一 raw success seed 分别为 history=1 的 `5012` 和 history=4 的 `5017`，且两者都没有 `success_grasp_verified`。每局都完整执行 75 个 chunk / 300 帧，因此失败不是 partial activation 或 deadline 截断。

## 判断

history=4 显著降低了 teacher action 的验证误差，但没有改善真实抓取成功，说明当前问题不能归结为单帧相位歧义。结合两种 history 都在完整 300 帧中稳定停留于 approach 失败，当前更像是 chunk policy 的开环执行误差、动作块边界误差或行为克隆分布偏移；不能通过继续堆叠 history 解决。

按监管要求，停止继续扩大模型，也不启动 residual SAC。下一步应转向 chunk 开环长度 / 重规划频率诊断，例如保持同一模型和预算，仅比较 K=1、K=2、K=4 的重新规划频率；该诊断完成前不宣称 ACT imitation 已具备稳定抓取能力。
