# ConRFT 之后：离线到在线 flow RL 的原理审核

核验日期：2026-09-22。范围：松灵 ALOHA 类双臂、抓放、任务初始成功率可能近零、少量遥操作成功示范与接管、VLA-only。本文是原理与来源审核，没有运行训练或机器人实验。

## 结论

本次重点审核 FQL/QC-FQL、DEAS、OTQL、Q-VGM 四组方法，辅查 DQC。**没有发现足以凭现成公开证据无条件替代 HIL-ConRFT 的弱先验真机在线方案。** 最有用的新方向不是删除所有约束，而是将约束来源从固定初始 VLA 输出，变为持续增长的示范、有效纠正与机器人经验；同时处理动作块价值高估。

- **FQL/QC-FQL** 是最清楚的“可更新行为先验＋可输出完整动作的 actor”方法参照。它很适合成为 ConRFT 动作头的研究对照，但原官方交付主要是仿真，不是即插即用的 π0.5 真机训练包。
- **DEAS** 最值得借鉴价值学习机制；官方 VLA 实验主要是 BC 更新行为模型之后用 critic 选动作，不能宣传成已证明端到端 RL 更新原 VLA 的在线框架。
- **OTQL** 有少量示范、真机 VLA 动作头更新的证据，值得追踪；代码待发布，真机分批离线更新，仍人工复位和标注。
- **Q-VGM** 虽更新 π0.5 动作专家，但明确依赖冻结 base velocity 与局部 Q 改善，不能当作解除基础先验依赖的答案。

以下“作者结果”均不等于独立复现，仓库 stars 只是关注度。

## 1. 先审 ConRFT 自身，避免把它当作已经解决全部问题

**已核事实：** ConRFT 的 Algorithm 1 随机初始化动作头与 critic，以 20–30 条示范进行离线预训练，再混合示范与在线数据，接管动作进入示范池。其核心监督来自实际动作，未要求复刻冻结 VLA 的错误动作。原论文的 Cal-QL-only 消融在这些少数据任务上失败；BC 是必要的启动来源。在线初始策略已经经过离线学习，不能将基础模型近零成功与在线阶段从零成功混为一谈。[论文 §IV、Algorithm 1、表 I](https://arxiv.org/html/2502.05450v2)

**由此得到的工程判断：**

1. 最大优点是可以重新学习完整动作，而非只能对坏动作做受限修补；并非 consistency 参数化本身保证成功。
2. 少示范会导致状态覆盖窄，BC 初始成功不代表 critic 已校准。需检查策略更新后是否明显退化、Q 预测与实际回报是否一致。
3. 扩展成双臂长动作块后，动作空间增大，原单步实验的稳定性不能直接继承；单纯将输出维度乘以 chunk 长度不够。
4. 冻结表征会限制新对象、视角或双臂交互的可辨识性；必要时需先做任务示范适配，再保持一轮在线训练内表征版本稳定。
5. 原实验存在人工复位和脚本复位，随机化通常只有数厘米。反向恢复、异常恢复和更广的初始状态覆盖是新增工程工作。

这些是复现风险及设计推断，不是声称原方法存在已证实的算法错误。

## 2. FQL／QC-FQL：先验会随经验更新，值得做动作头对照

**来源与开放：** FQL 为 UC Berkeley 团队，ICML 2025；Q-chunking 为同校团队，NeurIPS 2025。官方 MIT 代码分别是 [FQL](https://github.com/seohongpark/fql) 和 [QC](https://github.com/ColinQiyangLi/qc)。2026-09-22 页面快照约为 FQL 335 stars／44 forks，QC 409／48；未取得可比且稳定的论文引用计数。[FQL 正式论文集](https://proceedings.mlr.press/v267/park25f.html)

**机制：** FQL 同时学习一个以数据为目标的 flow 行为模型和一个快速一步 actor；actor 优化 Q，同时保持与该行为模型输出的适度接近。官方 `actor_loss` 包含三项：数据 flow matching、actor 与 flow 的蒸馏距离、负 Q。这里的行为模型持续训练，不是永远冻结的零样本 VLA。在线经验进入训练分布后，行为先验也能改变。[官方 actor 源码](https://raw.githubusercontent.com/seohongpark/fql/master/agents/fql.py)

**QC 增量：** 将 Q 的输入从单动作改为实际执行的动作块，使多步奖励对应整块动作；行为约束保留示范中的时间连贯性，从而改善探索。原实验为 OGBench／Robomimic 仿真；在线调优可以接续离线训练。[Q-chunking 论文](https://arxiv.org/html/2507.07969v2)

**对用户问题的意义（推断）：** 可以保留 VLA 视觉语言表征，接 QC-FQL 完整动作头，让示范、接管和经验驱动先验更新。这比锚定固定坏 VLA 更符合当前前提，但属于新组合；其传感器、动作映射、奖励、HIL 数据、双臂及 chunk 中断均需实现。它并不让原 π0.5 动作专家自动获得新能力。

**不能忽略的风险：** 数据先验仍可能被大量失败行为稀释；BC／蒸馏权重仍需调节，不能宣称“没有约束”。FQL 作者也指出没有内置在线探索机制；QC 的探索优势不等于少量真机示范即可达到相同结果。[FQL 局限](https://arxiv.org/html/2502.02538v2)、[官方调参说明](https://raw.githubusercontent.com/seohongpark/fql/master/README.md)

**建议级别：B，机制研究对照。** 适合检验“轻量完整动作头＋动态行为先验”是否优于原 ConRFT；不足以直接取代已具真机接管流程的基线。

## 3. DEAS：价值学习更稳，但 VLA 实现主要是候选动作选择

**来源与开放：** KAIST、UC Berkeley、UT Austin、NVIDIA，ICLR 2026。项目页链接官方 [DEAS-Isaac-GR00T](https://github.com/csmile-1006/DEAS-Isaac-GR00T) 和 [DEAS-FQL](https://github.com/csmile-1006/DEAS-FQL)。前者 Apache-2.0，页面约 20 stars／2 forks，公开入口主要围绕 RoboCasa。[作者项目](https://changyeon.site/deas/)、[UT Austin 实验室发表页](https://rpl.cs.utexas.edu/publications/2026/04/01/kim-iclr26-deas/)

**机制：** 动作块会扩大 critic 查询空间；actor 可能选择数据外动作而利用 Q 误差。DEAS 将价值学习从 actor 中解耦，以数据内动作块训练 Q／V，配合分布式价值与不同层次的折扣。策略提取可以另选，算法层面支持 AWR、FQL、候选筛选等，不等于每种选择都做过真机实验。[项目机制说明](https://changyeon.site/deas/)

**真实实验需准确描述：** 真机为 Franka 抓放三类物体，每任务 5 条示范、SFT 后 25 条 rollout；报告平均 **部分完成评分** 64.0→78.4，而非完整任务成功率。VLA 实现先以示范与 rollout 做 BC，再采多个候选、由 critic 选择，默认 N=10。不能把 OGBench 上 FQL actor 的训练方式写成真机 VLA 的训练方式。论文报告 VLA 实验使用 A100 80GB，学习阶段耗时以小时计。[论文 §5.2、附录 A.2](https://arxiv.org/html/2510.07730v1)

**源码交叉核验：** 官方 README 的评估显式同时要求 `CKPT_PATH` 与 `CRITIC_CKPT_PATH`，训练包括独立 critic 步骤，符合上述判断。[官方 README](https://raw.githubusercontent.com/csmile-1006/DEAS-Isaac-GR00T/main/README.md)

**建议级别：B，价值学习与分批经验回流参照。** 从原理上更适合稳定小数据 chunk critic，但最终候选采样仍依赖行为模型支持。如果基础策略从不提出有效抓取，选择器无法凭空生成它。采用“DEAS critic＋优势加权 flow 更新”需要另行验证，是提议而非已复现结论。

## 4. OTQL：真机更新 flow 头，当前开源与闭环不完整

**来源：** University of Edinburgh／Honda Research Institute Europe，2026-07 预印本。作者项目当前标注 Code Coming Soon；本次未找到已发布完整训练仓库。[作者项目](https://ansocho.github.io/otql-flow/)

**机制与约束：** 依据优势重新分配回放动作的权重，用条件最优传输配对噪声与动作，再训练 flow。理论表达是 KL 正则的策略改善，但实际 Algorithm 1 的监督目标来自可增长 buffer 的动作，并非逐点 L2 复制固定 VLA 输出。不能把任何“base policy”字样一概归成 RLT 式固定参考；也不能声称完全摆脱数据支持。VLM 冻结，flow 动作头更新。[论文 §3、§4.3](https://arxiv.org/html/2607.06262v1)

**真机 VLA 数据：** 原始 SmolVLA 两任务零样本失败；每任务 10 条示范 SFT 后达到 14/30 与 9/30，再使用 30 条 rollout 后为 24/30 与 22/30。它验证的是“零样本评测失败→少量示范形成部分任务行为→RL 改善”，不能把中间成功率自动称为已可用，也不能扩大成 RL 阶段零成功起步。真机使用分批离线学习；人工成功标签及逐回合复位仍存在。总预算不能直接套摘要的 50–60 episodes：附录将 VLA 设置写为 10 demos＋30 rollouts。[论文 §4.3、§5、附录 D.3](https://arxiv.org/html/2607.06262v1)

**建议级别：B−，发布代码后值得试的原生 flow 更新候选。** 与当前弱零样本、少示范场景有交集，但尚无现成松灵双臂、HIL 或正反自主闭环交付。高维条件 OT、critic 精度和计算延迟仍需审计。

## 5. Q-VGM：不能误列为摆脱固定先验的方案

**来源：** 上海交大、密歇根大学、电子科大作者，2026-06 预印本。本次论文与定向搜索未找到官方完整训练代码。

**关键事实：** 冻结 VLM／RLT 特征，训练 Cal-QL critic 后冻结 critic；更新 π0.5 flow 动作专家。每次把中间 denoising state 用冻结 base velocity 外推成干净动作，再做局部 Q 梯度改善，训练 `vθ−vbase` 拟合改善量。去掉冻结 base anchor 的消融表现变差。这里没有简单输出动作 L2，但固定基础动力学仍是方法核心。[论文 §3、§4](https://arxiv.org/html/2606.08015v1)

**证据边界：** 实验明确使用固定 rollout buffer 的完全离线设置。真机 7-DoF 单臂，30 demos／task 做 SFT，100 rollouts／task 学 critic；两任务初始 45%／35%，结果 75%／60%，各评估 20 次。不能扩大成近零成功、持续接管在线或双臂真机证据。[论文 §5.4、§5.5](https://arxiv.org/html/2606.08015v1)

**建议级别：C，已有可用 π0.5 后的精修备选。** 它解决 flow 梯度训练问题，却没有消除当前最关心的弱基础行为问题。

## 6. 两个值得保留的设计原则

**长价值视野与短反馈控制分开。** DQC（Berkeley，ICLR 2026）允许 critic 看较长动作块，而 actor 执行较短块，回应长开环执行影响纠偏的问题。原实验主要离线 goal-conditioned 仿真，可借鉴其反应性原则，不能说已有 VLA HIL 真机配方。[作者说明](https://colinqiyangli.github.io/dqc/)、[正式论文 PDF](https://openreview.net/pdf?id=aqGNdZQL9l)、[代码](https://github.com/ColinQiyangLi/dqc)

**近零成功不等于零信息。** 成功示范包含抓取、搬运、松夹爪的有效轨迹；RL 可以在此基础上处理分布偏移。但若奖励错误、示范控制映射不一致、编码器区分不了物体位置，更换 flow 优化器不会解决根因。应先验证示范回放与 BC 能稳定执行可识别子阶段，再评估 RL 增益。

## 7. 可审查的实验路线（提议）

1. 原版 HIL-ConRFT 保留为方法与工程基准；将原硬件适配和新算法改动分开做。
2. 用相同演示及纠正数据、相同 VLA 表征对照：BC／DAgger；ConRFT；QC-FQL 完整动作头。三组都保留人类示范监督，统一成功判定和人工分钟预算。
3. 若出现 critic 高估或离线到在线初期退化，再以 DEAS 式数据内价值学习作为针对性消融，避免同时堆叠多种新机制。
4. 若必须原生 VLA 动作专家获得能力，另设分批回流路径，等待 OTQL 完整源码或采用其他已有直接 flow 更新实现；明确它与轻量动作头路径的模型更新对象不同。
5. 初期单方向训练，成功判定可靠后扩展目标条件 A→B／B→A。共享表征是否带来正迁移需与独立策略对照；不要因行为可逆就预设共享全部参数必然更好。

评估至少报告：未接管成功率、连续无干预往返次数、掉物／卡住率、人工复位数、接管秒数、演示与标注分钟、实际墙钟时间、critic 误差与更新退化次数。没有这些指标，较高最终成功率不足以证明更少人工。
