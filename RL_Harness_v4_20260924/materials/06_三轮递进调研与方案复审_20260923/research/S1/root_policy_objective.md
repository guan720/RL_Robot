# S1：从最终 policy 目标检查研究盲区

日期：2026-09-23。范围为资料学习；没有训练或机器人试验。

## 先总结，再枚举

既有方案已经区分系统救场成功与 policy 无动作辅助能力，但还需把 Harness 的改进放在明确的因果链中：更可靠的观察／更多可恢复练习 → 合格的行为与后果数据 → 参数学习 → policy 独立能力。程序数量不是这条链的终点。

本轮补查三类机制：纠正是否能被策略学会；观察／阶段切换能力是否被误计为低层策略提升；Harness 与 policy 同时变化是否反而破坏配合。来源间的数字不做横向排行榜。

## 新增原始资料

| 方案 | 已读取的证据与边界 | 下一轮的问题 |
|---|---|---|
| Set-Supervised Diffusion Policy，RSS 2026，Delft／Stuttgart | 项目页、论文摘要、官方仓库页；用成对正负动作块构造监督集合，有真机纠正实验；是纠正学习，不是现成 VLA 在线 RL | 源码如何建立正负对及纠正时刻？能否避免把异步旧动作／未知接管原因误标为负例？ |
| StageGuard，2026-09-17，Huawei／UBC／Toronto 等 | 正文方法和实现；把阶段判断蒸馏到较小监控模型，仍调用其他动作技能；本文读取未定位作者训练代码入口，不宣称无仓库 | 是否仅帮助监督吞吐？任务完成判据与切换判断不能混用；不据此替换用户指定 GPT 主观察者 |
| Co-Evolving Harnesses and Models，2026-09-08，Salesforce AI | 正文与实验；企业 agent 上整轨迹模仿可能破坏已演化 Harness 的配合，局部访问状态纠正是其改进方向；并非机器人实验 | 如何分别冻结 Harness 和 policy 做交叉评估，识别程序提升与参数提升？不能把该文当机器人提升保证 |

原始链接：[SDP 项目](https://set-supervised-diffusion-policy.github.io/)、[论文](https://arxiv.org/abs/2606.01865)、[代码](https://github.com/ZhaotingLi/Set_Supervised_DP)；[StageGuard 正文](https://arxiv.org/html/2609.20791v1)；[Co-Evolving 正文](https://arxiv.org/html/2609.09134v1)。以上新增项经旧02／04文本检索未命中；PhyAgentOS／REMAC已在旧审查中浅筛，不能另计全新发现。

## 本项目推断，等待 S2／S3 反证

1. 纠正不是越强越好，而要能转为 policy 可用信息下的动作或有意义的探索。事后知道答案不等于当时可预测。
2. 程序可以只增加有效练习机会，不必每次运行都产生 BC 标签；应分别记录直接监督、有效交互、避免人工复位三条贡献。
3. 早期允许 Harness 大量帮助，最终需要固定任务分布下的独立 policy 验证；不能通过降低任务难度或不停接管制造能力提升。
4. 固定旧／新 policy 与旧／新 Harness 做交叉比较，另做无动作辅助评估；奖励、输入信息与起态分布保持可比。
5. 纠正退出不能只按接管次数下降：任务机会减少、监控漏报或不可恢复失败也会让次数变少。

## 实际检索轨迹与排除

使用 web 搜索论文、官方项目／GitHub、机构发布及社区发现线索。主要查询：`robot harness policy learning September 2026 open source`；`robot agent policy distillation autonomous learning 2026 code`；`real world vision language action online reinforcement learning open source September 2026`；`robot reset free reinforcement learning autonomous intervention 2026 github`；`robot harness correction policy distillation 2026 learning`；`policy Harness-Zero robotics SAGE`。随后打开上述三项原始资料，并用 rg 对照旧02／04。

发现并交给对应研究员：GPT-Policy、Agent as Policy、UniSteer、HITL-DP、RAPID。UniSteer／VLAC／VLA-Precision 已在旧02覆盖，重核不计新增。Agent-R1、EDGE、OmniHarness 为非物理机器人任务，只可提供机制线索；同名 SOAR 搜索返回认知架构／ARC／仓储多种不同工作，不能混为机器人自主学习证据。论坛演示不代替论文和训练资产核查。
