# UniSteer 官方代码短审

审查日期：2026-09-22。范围：官方 main 分支静态阅读；未安装、训练或执行机器人。GitHub main 可能变动，以下仅对应本次快照。

## 结论

UniSteer 是条件性技术候选，当前实施优先级以 [后续深审](unisteer_feasibility_audit.md) 为准。论文使用松灵 Piper 单臂，30 条任务示范微调后报告 10%–35% 初始成功率；该数值仅描述作者任务与评测协议，不能按不同论文的百分比邻近程度判断适合性。在线冻结 flow VLA，通过小噪声 actor 和 critic 学习操控其输出，并不更新原 VLA 动作头。论文的可逆 flow 理论并不自动保证当前压缩噪声实现能够表达任意人工纠正动作，因此不能直接认定其已消除坏初始 VLA 的限制。[论文](https://arxiv.org/html/2605.10821v1)

## 1. 人工接管数据：论文与默认配置有差异，但能力已实现

论文将人工动作反演成噪声，将对应 transition 同时加入 RL replay 和示范集合；当前官方 `pi05_spoon.yaml` 的 `add_human_inverse_to_rl_buffer` 默认是 `false`，默认行为是人工片段提供逆向噪声监督，自主片段提供 RL transition。训练服务确实实现了将人工 inverse target 转成 episode payload 后 `ingest_episode` 的可选分支；开启上述配置才启用。因此应描述为“论文与发布默认配置不同”，不能说“代码不支持人工数据进入 RL”。[训练服务](https://github.com/microsoft/UniSteer/blob/main/src/tool/unisteer_train_service.py)、[默认配置](https://github.com/microsoft/UniSteer/blob/main/config/online/pi05_spoon.yaml)

## 2. 小 actor/critic 实际具有语言条件表示

不能仅因 RL observation 字典名是 `pixels` 和 `state` 就判定 critic 不包含目标信息。`InferenceAgent.build_unisteer_observation` 把任务文本传入 VLA adapter；`Pi05OriginalAdapter.extract_unisteer_state` 将图像和语言 token 一起经过 PaliGemma，取末个有效 prefix token 表示，再与原始本体状态拼接。配置中的 2055D state 即 7D 本体状态＋2048D VLA prefix 表示，故小 actor/Q 可接收语言条件特征。[推理入口](https://github.com/microsoft/UniSteer/blob/main/src/agent/inference_agent.py)、[π0.5 adapter](https://github.com/microsoft/UniSteer/blob/main/src/model/openpi/pi05_original.py)

这不等于官方已经验证正反双任务共享训练。仍需确认不同方向任务文本、state 特征缓存、replay 标签、成功判定和奖励路由的一致性；也可以先分开两个 learner 做可达性验证。无需先假设必须新增一个目标编码器。

## 3. 真机闭环的公开范围

- 官方已发布推理服务器与训练服务，但 README 把机器人控制客户端标为 coming soon。执行动作、限幅、相机排列、接管和急停的硬件 executor 需要自行接入。
- 默认数据合同和配置为 7D action/proprio，实验是 Piper 单臂。配置可扩展不等于已发布双臂即插即用执行系统。
- 成功奖励来自外部 executor 写入的 `meta.json.success`，`binary_reward.py` 仅把成功的最后一个 transition 设为 1，其余为 0。没有据此核实到自带的自主成功检测器。不能进一步断言“必须人工打奖励”：该 success 字段也可由用户的自动检测器生成。

来源：[README](https://github.com/microsoft/UniSteer)、[二值奖励实现](https://github.com/microsoft/UniSteer/blob/main/src/tool/binary_reward.py)、[配置](https://github.com/microsoft/UniSteer/blob/main/config/online/pi05_spoon.yaml)。

## 4. 必须先做的离线可达性门槛

当前 π0.5 配置为 horizon 50、内部每步噪声维度 32，但 actor 只预测一个 compact noise step；`mean_time` 使用执行窗口投影，随后扩展到完整 flow noise。噪声 actor 还有 2.5 的输出限幅。把完整反演噪声压缩再扩展，通常不保持原始动作解码结果；全维可逆性不能直接证明这一低维可达性。[噪声布局](https://github.com/microsoft/UniSteer/blob/main/src/model/openpi/openpi_noise.py)、[配置](https://github.com/microsoft/UniSteer/blob/main/config/online/pi05_spoon.yaml)

建议先用同一批人工抓取、移动、放置及反向示范，比较：

1. 人工动作 → 完整噪声反演 → 冻结 VLA 解码，测实际执行窗口的动作重建误差。
2. 完整噪声 → 官方 compact 投影/扩展 → 解码，测额外误差及抓放关键时刻偏移。
3. 加入 actor 限幅后重测，统计超界比例，检查单位、归一化、夹爪以及绝对/相对动作语义。
4. 相同观测切换正反任务文本，验证 actor/Q 使用的 state 特征确实改变，且 replay 和奖励按对应目标计算。

只有该门槛通过，才值得投入真实在线 RL。若完整反演可重建、压缩后不可重建，可以试更高维噪声 actor；若在任务关键状态仍无法稳定覆盖人工动作，优先保留 ConRFT 类可更新动作生成头方案，而不是继续依赖冻结 decoder。
