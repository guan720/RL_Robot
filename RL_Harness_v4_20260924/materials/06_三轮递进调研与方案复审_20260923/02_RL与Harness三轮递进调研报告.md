# RL 与 Harness：三轮递进调研与联合选型报告

**v4｜研究截止 2026-09-23｜论文、开放资产和固定源码研究；未安装候选系统、运行训练或进行真机实验。**

本文是学习与选型依据，配套 [开发技术方案](01_开发技术方案.md) 和 [专家汇报](03_技术专家汇报.md)。先读 §1、§11–14了解本次新增结论，再按 §2–8学习机制和既有核心候选。详细源码与检索记录放在专题报告，避免把全部研究过程塞进开发流程。

## 1. 联合结论：保留总体闭环，新增强对照并修正学习与数据边界

**最终产物是能稳定独立执行的部署 policy；Harness 程序积累服务这一目标。** 部署 policy 可以包含所选算法必要的学习动作头、editor、latent steering 或 Q 选择器，必须整体冻结并计成本；独立评估撤去 GPT Harness 临场动作帮助。复合包变强不等于底模参数已经内化全部能力。

当前没有足够证据将一个新仓库直接替换为整套系统，但有足够证据改进选型与实现：

| 决定 | 本次三轮后的结论 | 最关键的未决条件 |
|---|---|---|
| 原生 VLA RL | **RAPolicy 优先预检**，不是最终胜者 | 少示范可学性、共享双向、将 hold 配置改为自洽连续执行的成本 |
| 实时学习对照 | **RT-EXPO 首要异步挑战者** | 弱起点候选／编辑支持、Q 排序、局部可靠纠正 BC、全包 goal 条件 |
| 明确定义的参考实现 | **完整动作头＋BC＋队列增广 off-policy RL** | 自由度和可达性优势能否抵消少数据冷启动、Q 外推和实现成本 |
| 动态监督基线 | **加强 Harness-DAgger／BC，借鉴 ABC**；FlowDAgger、SDP 作有条件纠正吸收对照 | 不借助额外未计费信息；监督可学、动作可表达，不能把它们称作已具备在线 TD |
| Harness | **RPent 首先联调**；OpenETA、PhyAgentOS-core 等按同契约预检 | 观察独立性、设备排他、未知回执、学习日志与替换成本 |
| 运行时与自有核心 | RLinf 首先验证，LeRobot 轻量备选；统一 Gateway 与事实／标签账本不可省 | 固定版本及依赖环境、实际执行时间、发布包一致性 |

新发现的 FluxVLA、FutureRTC、ForceRFT、AGP、SAGE、Harness-Zero 等提供机制或代码片段；S2 发现它们的动作记录、奖励、公开数据或实际运行边界不足以支撑直接全套替换。S3 又引入 ABC、FlowDAgger、SynthDemo-RL、TORL-VLA、CritiQ/ReTRy 等联合反例，强化了纠正到学习的条件。机构名、发布时间、演示分数和仓库热度不代替这些条件。

本版还有一项方法修订：actor 从全部合格的事前决策状态采样，不再因当前旧动作后来提前终止而额外筛掉该行，避免重复施加存活概率。真实终局仍使用无 bootstrap 的 critic target；接管删失仍是未消除的偏差，需要覆盖统计和独立实验。[异步定义](appendices/02_异步动作时间轴与学习目标.md)

§2–10融合了此前02–04的机制和源码研究，文中“此前扩展调研”指04阶段；本次 S1/S2/S3 的更新以 §11–14及其原始专题为准。旧知识被重新组织，不冒充每篇都在本次重新完整审计。

## 2. 先理解我们在比较什么

### 2.1 RL：更新什么，比算法名称更重要

真机 RL 至少包含四个独立选择。

| 选择 | 常见路线 | 对低成功率起点的影响 |
|---|---|---|
| 动作参数化 | 原生 flow／diffusion 头；VLA 表征后的完整头；残差；latent；候选选择 | 完整头动作自由度大，但损失已有运动先验；残差容易保留基本行为，但可能覆盖不到必要动作 |
| 改进目标 | off-policy Q、策略梯度、优势加权回归、Q 优化后蒸馏 | 是否有效利用失败、是否要求成功轨迹、是否需动作概率，各不相同 |
| 辅助数据 | 示范、执行纠正、未执行动作标签、失败转移 | 都可长期保存；只有有真实后果或明确模型后果的样本才能构成相应 TD |
| 运行系统 | 采集、replay、训练、权重发布、真实执行 | 异步 actor/learner 只是训练通信，不能自动解决慢推理动作块的延迟归因 |

因此，“支持 π₀.₅”“支持 SAC”“支持 RTC”三个功能标签不能相乘成一条已验证的真机训练链。应审核具体 **模型—算法—环境—执行协议** 的组合。

当前首版方法可以准确称为：**保留 VLA 表征、训练目标条件完整动作头，以可靠 BC 冷启动和持续吸收 Harness 纠正，再用离策略 twin-Q 更新；用队列增广状态处理异步执行。** 这是基于成熟机制的项目组合设计，不应冠以某篇论文的名字后宣称完整复现，也不应把其未经实测的优势当结论。

几个贯穿全文的术语：BC 是模仿可靠动作；critic/Q 估计动作之后的回报；TD 用当前回报与后继价值构造学习目标；off-policy 允许用旧策略或纠正来源的真实经验学习当前策略；flow/action expert 是生成连续动作的原生模型部分；RTC 用在途动作前缀约束下一块动作；adapter 负责组件或本体之间的显式接口转换。这些都是机制，不代表已有完整无人系统。

### 2.2 Harness：观察、执行、学习并不是同一件事

GPT 能判断抓空、规划重抓、生成程序，但这些能力只有接上物理事实才能帮助 RL。一个完整 Harness 需要：持续观察与评分、动作工具和本体 adapter、控制权与停止确认、事实日志与标签版本、纠正数据回流、程序发布与回滚。

尤其要区分三种进步：**系统更会救场、policy 参数更强、人工工时更少。** 三者可能同时发生，也可能完全不同。RoboRSI、SHAPER 的代码／上下文演化，Show-Harness 的工具操作，HARBOR 的训练工程自动化，都有价值，但不是同一种低层 policy RL。

本系统的 Harness 可以直接生成动作、执行纠正并参与 DAgger 式数据聚合；无需假设另有一个强 policy。当它的动作次优或错误时，真实后果仍可训练 Q，是否适合模仿则另判。**BC＋RL 既吸收可靠行为，也利用失败的后果；长期 demo buffer 本身不等于默认损失已经包含 BC。**

## 3. 任务条件与证据标准

目标是单策略练习 A→B 与 B→A，双向均 RL，正常反向不是固定 reset 脚本；GPT-6 是主要语义观察和纠正模型。允许少量遥操作示范与 SFT，基础成功率偏低，包括零；不以 ACT 为基线；算力未定；首个场景单臂抓放。算法不需要等待高成功率 base，但仍需要可用动作支持、可识别奖励或可靠纠正中的启动信息。

本文采用以下证据层次，避免把机构权威与工程成熟度混为一谈。

- **源码深读**：已读关键 loss、replay、运行或接管代码，可讨论该版本实现，但没有运行证明。
- **论文＋发布核查**：已读第一方论文和仓库／模型卡，能说明机制与开放范围，不能保证每条路径能跑通。
- **预筛线索**：原始项目或摘要支持候选存在及大方向，尚不足以决定主线。
- **历史沿用**：此前已研究，此前扩展调研用于完整地图与交叉检查，不包装成新增深审。

开源要分别看论文、训练代码、部署代码、权重、数据、依赖和许可证。GitHub 有地址、HF 有论文页、演示视频可看，都不是完整开放训练系统的充分条件。下面的效果数字均为作者条件下报告，不进行跨任务成功率排行榜。

## 4. RL 候选：按技术路线学习

### 4.1 成熟的示范＋真机离策略学习

HIL-SERL、ConRFT／HIL-ConRFT、RLPD、AWAC、Cal-QL 构成此前路线的基础：真实经验和示范可以混合，离线数据可改善启动，在线交互提供新的后果，BC 或一致性项帮助维持可用行为。它们仍值得保留，理由是机制和真机证据，而不是发布时间。

其中 HIL-SERL 不能直接等同原生 VLA；ConRFT 的模型和训练假设也不能无改造搬到 π₀.₅ 与真实异步 chunk。此前扩展调研没有把旧基线“淘汰”，而是把它们从整套方案名称拆为可复用的训练机制。前期原理和固定代码详见 [历史 RL 源码审计](../03_RL_Harness自主学习系统_20260922/07_共享策略与异步RL联合选型证据.md)。

对不完美纠正，新补查的 SiLRI、GAINS、PACT、E2HiL 分别研究状态相关模仿权重、接管收益分布、次优片段归因和样本筛选。**它们解决的是纠正如何用得更好，不是 GPT 如何可靠地产生纠正。** SiLRI 固定源码的 chunk 接口仍未实现；接管熵低不代表动作正确。GAINS／PACT 的接管负奖还必须避开“主动观察、超时、目标切换也触发接管”的误归因。[SiLRI 代码](https://github.com/nuomizai/HIL-RL)、[PACT 论文](https://arxiv.org/abs/2606.03949)、[E2HiL 项目](https://e2hil.github.io/)

### 4.2 Real-Time EXPO-FT：值得优先实测的异步方案

Stanford 的 Real-Time EXPO-FT 于 2026-09-16 发布，关键价值是把慢 VLA、RTC 前缀、快速编辑、实际执行窗口和在线数据放在同一个实现里。原文 Table I 的普通 SFT 均值约42%，RTC-SFT为60%，RT-EXPO约97%；摘要42%→97%的参照是普通SFT，不能说RTC起点只有42%。每任务每方法评测30次，在线预算至多十分钟机器人数据，并非训练、复位和评测总耗时。作者明确存在人工复位，评测还由人独立验成功；“rollout无动作干预”不等于全天候无人学习。已有RTC-SFT、任务检测器和DROID依赖仍须保留。[论文](https://arxiv.org/abs/2609.18207)、[项目](https://pd-perry.github.io/real-time-expo-ft/)

RT-EXPO 的部分任务还给 Q、候选筛选和编辑器提供检测器派生的位置／速度，并改变图像历史；这些来自自身传感器，基础 VLA 的 state 并未同样扩展。比较时须按模块核对实际信息、可用时间与预处理成本，不能只对齐相机数量。[输入条件与原文定位](../04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md)

论文的延迟证据还须区分两种条件：wall-clock 实验给三个任务的采样调用额外加 100 ms，Dynamic Picking 不加这项延迟；chunk-delay 实验使用旧观测／在途前缀，后者 d=3、其他任务 d=5。不能把两种条件相加，也不能把成功率汇总描述成四任务统一自然硬件时延下的结果。真实部署的观测龄期、推理、网络、排队和人为注入须分别测量。[原文附录 VII-E.3](https://arxiv.org/html/2609.18207v1)

这次读到了固定提交 `803381fc3b4c91a0c47904f1b688fc5e35904f50` 下真正的实时学习器、采样器和 replay。**此前“EXPO 缺少异步实现”的概括不成立。** 原生 VLA、编辑器与 critic 分开更新：失败帮助 Q 和编辑；原生 VLA 主要通过成功数据的 RTC-BC 改变；编辑仍有界。因此，它不是永久冻结的 base，但也不是 Q 直接训练整个 flow 头。[固定学习器](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)

对我们最关键的测试是：可靠 Harness 纠正是否落在 base 候选＋允许编辑的可达范围，新增 BC 是否能扩展后续基础分布。若覆盖充足，保留运动先验可能比重学完整头省样本；若抓取／释放等必要动作一直无法产生，有界编辑就可能成为瓶颈。不能仅凭初始成功率低决定胜负。

它与当前队列 RL 仍有协议差异：较新观测编辑、候选缓存、filtered backup 和固定窗口各有条件。**不能把其 replay 数据直接喂给本文另一套 Bellman 目标。** 应先各自实现完整时间契约，再在同等真机、示范、Harness 和算力预算下比较。细节见 [VLA 专项 §4](../04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md)。

### 4.3 原生 flow 直接改进：确实有更丰富的新路线

| 路线 | 为什么值得关注 | 当前不能直接升级主线的原因 |
|---|---|---|
| [RAPolicy](https://github.com/flyfaerss/RAPolicy) | 真实弱初始策略、原生动作专家在线更新、共享多任务；公开 RLinf fork | 无配套 SFT 权重／示范数据；示例推理期间 hold；接管、吸收填充、版本和混合数据语义须按本项目改造 |
| [verl-vla π₀.₅ TD3＋BC](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html) | 已有直接更新原生动作头的开放配方 | 示例是 8 GPU、32 并行仿真；起始模型虽然只 SFT 100 步，数据池仍有 432 episodes；实体相同配置未验证 |
| [verl-vla 10-demo RECAP](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html) | 仅十条初始示范的公开弱起点配方和数据，价值／优势标签条件化训练原生 VLA | 仍为仿真；16%→最好 46%，中途续跑与挑选 checkpoint、8+2 GPU；不是稳定无人真机结果 |
| [Q-VGM](https://arxiv.org/html/2606.08015v5) | 用 Q 引导 flow 速度目标，直接改 action expert | 此前扩展调研未核到官方完整训练仓库；最新版真实提升的离线条件不能改写成无人在线 |
| [OTQL](https://ansocho.github.io/otql-flow/) | 用最优传输构造 flow 的价值改进目标 | 作者 Code 仍标 Coming Soon；方法适合度高不等于工程可达性已高 |
| [LWD](https://finch.agibot.com/research/lwd) | 共享 VLA、DIVL/QAM、混合成功失败及 failure play | 16 台机器人、652.5 小时离线数据，完整训练包未核到；整块执行不同于本项目异步中段 |
| [PA-RL](https://policyagnosticrl.github.io/) | 先用 Q 优化动作再蒸馏，可兼容多种 policy | 是成熟重要思路；共享目标、真实队列和 Harness 数据仍需具体集成 |
| [RedFlow](https://arxiv.org/abs/2607.27782) | 失败轨迹参与 flow 行为调整 | 不能把检索得到的替代动作伪配真实后继；尚不是完整在线闭环 |

**RAPolicy 是此前扩展调研后续补核中最影响原生头优先级的发现。** 它用 replay 动作训练 Q／状态价值，以优势加权回归更新原生一步 flow，并复用在线采样噪声；不必用 Q 对新动作反向求导，也不将动作限制在弱 base 的小残差内。作者单任务十示范的起点包含零成功，另有共享五任务实验；仍保留人工接管，使用八张 RTX 3090。详细条件、固定代码与不能直接拼接的部分见 [VLA 专项 §11](../04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md)。[原论文](https://arxiv.org/abs/2609.22888)

因此，优先核查 RAPolicy 的原生头适配，比只把原生路线寄托在仿真 TD3＋BC 上更有依据；这不证明它在本工位或连续动作协议下已优于完整头／RT-EXPO。IQL 式状态价值对应 replay 内较优行为，不能把 Harness 帮助下的高价值直接当作 policy 无辅助能力。

补查 RECAP 配方的价值在于避免把“verl-vla 示例数据池 432 条”误推广到整个框架：该十示范实验最终累计 106 条，含失败 rollout；原始示范标签强制为正，发布数据又由最终 value 模型重新标注，不能当历史在线标签快照。多次选点与明显回退提示必须冻结评测和标签版本。它由 verl-vla 提供，是第三方开放实现，不是 PI 官方完整训练栈。[配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html)

RECAP／π*₀.₆、RLT、DSRL、ZPRL、PLD、Robo-ValueRL、RL²-VLA 也在此前扩展调研地图中，分别涉及价值条件化、特征／latent、残差、蒸馏与在线适配。对它们统一追问：**谁真的被 RL 更新，约束指向什么分布，是否依赖大量离线行为，失败怎样进入学习？** 不能因为标题含 VLA RL 就认为动作自由度与数据用法相同。[完整候选地图及分层](../04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md)

### 4.4 世界模型和大规模仿真：保留后续路线

RISE、VLA-MBPO、WMPO、VLAW、World-Gymnast、WCM，以及新近 Imagine-RL、Prioritized Rollouts，覆盖模型内训练、历史价值表征和想象数据分配。FPO／FPO++、RIPT-VLA、π-StepNFT、Z-1 等扩大了 flow 与 VLA 的 RL 工具箱。它们可帮助后续提高样本效率，但必须另计模型数据、误差、算力和仿真复位条件；不把想象轨迹混成真机事实。[VLA 专项 §3、§5–7](../04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md)

其中 WCM 当前更适合价值模型部件参考；FlashRT 更接近推理／条件化推理工程。推理快能改善控制，不能单独替代 reward、replay 和更新器。

## 5. 自主循环：哪些老问题被新方案改善了

Leave No Trace、R3L、MTRF、MEDAL++、ARIEL、ReLMM、RoboFuME、RISC、MoReFree、RM-RL 等说明：持续学习需要把起始状态、可恢复区域和任务调度一起考虑。“反向恢复”不必是把正向动作倒放，也不保证共享参数必然正迁移。对于 A↔B，两个方向可以共享 θ；每个方向的目标、奖励、Q 和数据标签仍必须明确。[历史与新增复位路线表](../04_RL与Harness扩展调研_20260923/research/02_自主学习与复位扩展调研.md)

此前扩展调研有三项值得具体吸收。

1. **AutoSERL 的局部引导与退出机制。** 对物体关系已确认的局部动作，示范轨迹可以降低人工操作量；但其主要实验从手持物体、固定目标出发，仍有人工二值奖励，不能直接代替完整抓取—搬运—释放与自动评分。[论文](https://arxiv.org/abs/2607.01651)
2. **UniIntervene 的恢复记忆。** 真正的 MIT 算法仓库已经开放，不能继续依据项目页占位说“没有代码”；公开包是离线七阶段，不含真机部署、HIL-SERL 在线集成或轨迹权重。适合积累 GPT 纠正后研究快速复用。[固定 README](https://github.com/Denghaoyuan123/UniIntervene/blob/40f461f97573383c9cc8fdba43df56f9eb5bbea1/README.md)
3. **AutoEval 的任务队列、评分与复位基础设施。** 自动评估值得复用，但复位能力仍需准备；不能将独立 reset policy 偷换成用户要求的共享反向 RL。[项目](https://auto-eval.github.io/)

FARL、CRONOS、PlayWorld、Q2RL 进一步补充风险控制、课程、自动 play 和 BC→Q 初始化的视角。它们不是首版全部必装模块。先有双向基本覆盖与可验证纠正，再逐项比较收益，能避免用一个复杂新模块掩盖数据和动作接口问题。

## 6. Harness 候选：按层比较，而不是选一个名字包办全部

### 6.1 认知、工具与能力演化

| 候选 | 可借的主要能力 | 与本项目的差距和定位 |
|---|---|---|
| [RPent](https://github.com/RLinf/RPent) | 认知编排、工具、本体注册、记忆、数据飞轮 | 暂定认知骨架；需独立观察、自动 verdict、单 Gateway 和 RL 出口；旧源码审计不自动覆盖新 HEAD |
| [RoboRSI](https://lab.noematrix.ai/blog/2-roborsi/) | 代码能力演化与策略数据回流 | 仍是动机和机制参考；成功 SFT 与本项目 BC＋失败 TD 更新不同 |
| [Show-Harness](https://github.com/showlab/Show-Harness) | 语义原子动作→本体解释器、人／代理统一记录 | 新增纠正模块候选；默认 DAgger 是人工键盘，DONE 和 Pause 不足以充当独立奖励及设备停止 |
| [VoLoAgent](https://github.com/NVlabs/VoLoAgent) | VLM 进展／失败监测、VLA 与几何抓放工具 | 新增“冻结 policy＋代理辅助”对照；不是在线学习底座，必须重接真实步数与控制权 |
| [RoboClaw](https://github.com/RoboClaw-Robotics/RoboClaw) | 正反技能、异常恢复、自主采集 | 物理循环参考；部分部署资产需请求，不冒充完整开放训练包 |
| [SHAPER](https://arxiv.org/abs/2608.11350)、[CaP-X](https://github.com/capgym/cap-x) | 上下文／技能代码演化及代码学习 | 用于代码候选生成和测试；代码进化不是低层 policy 已经过 RL |

RPent 最新提交 `6ee7069` 的父提交正是前次审计的 `eb269c8…`。此前扩展调研检查变更清单与新增文档：主要增加 RoboCasa／RoboTwin 探索、记忆和测试，探索仍用环境普通 reset，并导出最终成功命令。它提升了探索覆盖，但不是本项目真机自动复位与全来源 RL 日志的完成证明。此前扩展调研未宣称对 28 个变化文件做了完整源码审计。[提交与差异](https://github.com/RLinf/RPent/commit/6ee7069)

Show-Harness 的新增价值是让“GPT 纠正”变得具体：语义小步经本体解释器变为低层动作，并保存变换与反馈。**选择它不是因为碰巧使用 AgileX。** 同一接口可以接不同本体；上层仍需明确坐标、夹爪、时效和前置条件。它的默认初始化／RELEASE 不可照搬到中途持物接管，DONE 也不能直接给成功 reward。[论文](https://arxiv.org/abs/2609.10522)、[固定 runner](https://github.com/showlab/Show-Harness/blob/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/real.py)

VoLoAgent 来自 NVIDIA，有真机 FR3 实验和开放代码，但每方法仅 42 次试验，完整组合并不在所有消融上最好。这支持增加严格系统对照，不支持“加大模型一定更好”的判断。[原文](https://arxiv.org/abs/2606.07723)

### 6.2 通用工程底座的竞争者

**OpenETA** 应进入同预算骨架对照，而不是因缺少现成在线 RL 被排除：RPent 同样需要补学习链。它提供工具、观测、证据与候选经验的契约，固定版本仍需改造持续观察、实体停止和 RL 数据桥；策略适配与自演化收益也不能按路线图当成已完成。RPent 仍是暂定先验证者，选择由相同接口验收与改造成本决定。[官方实现](https://github.com/OpenMOSS/OpenETA)、[固定源码核查与边界](../04_RL与Harness扩展调研_20260923/research/03_Harness扩展调研.md)

**Strands Robots** 提供工具代理、统一设备／policy、RTC、记录、训练和远程编排，是值得认真比较的工程挑战者。官方硬件目录区分 real 与 sim，RL 文档当前主要是 SimEnv 的从零学习；这些限制必须看清，但不能因为 Piper 尚是 sim-only 就否定它的通用性。[官方架构](https://strands-labs.github.io/robots/architecture/)、[Amazon 发布](https://huggingface.co/blog/amazon/strands-lerobot-hub-to-hardware)

**DimOS** 的数据流和 ControlCoordinator 可研究为运行层组件；**OpenRAL** 的类型化技能、HAL、世界状态和独立控制边界可研究为接口范本。二者都不是拿来就能满足本项目 TD／DAgger 的完整训练系统；也不因某个厂商适配欠缺而淘汰。[DimOS](https://github.com/dimensionalOS/dimos)、[OpenRAL](https://github.com/OpenRAL/openral)

**Open-RAIL** 是另一项目，来自中国移动团队，重点是异步推理、机器人接入和数据记录。它可补动作执行工程，与 OpenRAL 不同，也不是认知 Harness。[项目](https://cmcc-tao.github.io/open-rail/)

### 6.3 不同层的 RL 和“自主”必须分开

REAL 的 MCP 高层工具 agent 经 SFT／RL，HARBOR 自动搭建仿真、奖励和训练流程；它们分别学习工具选择、自动化开发劳动，不能误当真机 VLA 动作 learner。HoloAgent、ENPIRE、Zetta、EmbodiSkill、AgentSpec、HiRobot 等保留在完整地图中，按空间记忆、失败恢复、技能组合或兼容性研究取用。[REAL](https://github.com/InternRobotics/REAL)、[HARBOR](https://github.com/supersglzc/harbor-rl)、[Harness 专项](../04_RL与Harness扩展调研_20260923/research/03_Harness扩展调研.md)

NVIDIA GR00T、Google Gemini Robotics 2／ER2、PI 等公司发布提高了可用模型和工具的上限，但 API、开放底模、早期合作与完整训练代码必须分别计证据。此前扩展调研保持用户指定 GPT-6 主观察器；奖励模型和其他 VLM 作为校准、成本或延迟对照，不自动更换。[机构与奖励核查](../04_RL与Harness扩展调研_20260923/research/04_训练平台与开源生态核查.md)

补漏还区分了容易混同的名称与开放层次：Harness VLA 新版代码指向 RPent；HALTER 是已学原子技能的评测复位研究，公开代码仍在发布中；Nautilus 主 Harness 与采集子库开放范围不同；Zero2Skill、Guava 的具体定位及资产边界见 [Harness 专题补充](../04_RL与Harness扩展调研_20260923/research/03_Harness扩展调研.md)。这些线索扩展阅读范围，不自动成为整套替代框架。

## 7. 开源资产、影响力与复现可信度

### 7.1 训练平台：更适合用“能复用什么”比较

| 平台 | 已核的可复用资产 | 必须新增／验证 | 当前定位 |
|---|---|---|---|
| RLinf／RLinf-USER | 真机 actor/learner、replay/demo、VLA、在线学习入口、RTC 评估 | goal/queue、BC 纯标签支路、目标函数、单设备 owner、模型与协议组合 | 首先验证的运行时 |
| LeRobot 0.6 | 设备／数据生态、拆分的算法接口、online/offline mixer、HIL-SERL 示例 | VLA 表征与目标头、显式 BC、队列 TD、事实和标签版本 | 单机轻量备选 |
| verl-vla | π₀.₅ 直接 RL 配方、工作流、trainer、分布式训练 | 同配置真机证据、异步物理协议、自动纠正与共享双向 | 原生动作头直接更新对照 |

具体源码已经读到：RLinf 默认 critic 分支的 reward 聚合／discount 不等于本文队列目标；LeRobot mixer 混 transition，不替纯建议补后继；verl-vla episode trainer 的有效段也不能代替物理接管协议。这些是需要开发 adapter/loss 的证据，不是说上游自己的环境定义错误。[固定源码与差别](../04_RL与Harness扩展调研_20260923/research/04_训练平台与开源生态核查.md)

另外，LeRobot issue 中引用的 ConRFT PR 链接实际指向视频编码修改，QC-FQL PR 仍为 Draft。路线图、PR 标题和计划不是已合并功能；这种检查比只读 README 更能避免选到不存在的组合。[路线 issue](https://github.com/huggingface/lerobot/issues/3076)、[QC-FQL PR](https://github.com/huggingface/lerobot/pull/1818)

### 7.2 影响力不伪精确，也不替代适配性

此前扩展调研网页快照中 LeRobot 约 27.7k stars／5.7k forks，RLinf 约 5.4k／744，verl-vla 99／20；缓存页会稍有差异。它们说明社区关注，不是独立真机复现数量，且不能用母项目 verl 的热度替子项目背书。[LeRobot](https://github.com/huggingface/lerobot)、[RLinf](https://github.com/RLinf/RLinf)、[verl-vla](https://github.com/verl-project/verl-vla)

HF 下载按具体权重统计，不能混成方法下载量。某 RLinf Pick_Red 模型没有 model card、下载未追踪，就应写未知；π₀.₅ TD3＋BC 起点模型约 36 月下载、RPent BEHAVIOR 权重约 34 月下载，都只是当日页面值。框架 Apache、主仓 MIT 不能覆盖底模、数据与机器人驱动的许可。[平台开放性细节](../04_RL与Harness扩展调研_20260923/research/04_训练平台与开源生态核查.md)

此前扩展调研没有取得全部候选可靠且同步的引用计数，故不编造统一引用榜。Stanford、Berkeley、NVIDIA、HF、ByteDance、AGIBOT 等机构及同行评审是可信度的一部分；完整源码、透明实验条件和第三方复现才使“我们可达”更可信。尚未找到的第三方复现记未核验，不以论文视频或 stars 代替。

## 8. 联合兼容性：为什么不能各选一个最高分框架再拼起来

| 融合处 | 容易出现的假兼容 | 本方案要求 |
|---|---|---|
| 控制权 | RPent 工具、语义解释器、平台 env 都能直接写设备 | 单 Gateway；其他模块仅提交候选／请求；reset 同样受控 |
| 状态与 goal | actor 读语言，Q／replay／恢复检索漏传目标 | 同一目标版本贯穿 policy、critic、评分、标签与双向调度 |
| chunk 与反馈 | 只给未执行区乘 mask；或把反馈轨迹倒填为起点动作 | 明确决策时刻、旧承诺队列、真实执行窗、回报区间；各协议独立训练视图 |
| 纠正数据 | 所有接管都当专家，所有建议都当 transition | 真实性、BC 质量、时间合法性分别判；真实失败保留，纯标签长期单独采样 |
| 评分 | DONE、无进展、unknown 或接管直接变成 reward | 冻结任务判据、证据时间和奖励版本；延迟评分只回标相应历史 |
| 发布 | 更新了 actor，Q、normalizer、goal、运行队列还沿用旧定义 | 版本包和边界发布；旧事实可追溯，污染标签可撤销 |
| 通用性 | 上层写死维度、hold 数组或启动时放开夹爪 | capability/schema/adapter 声明；更换本体隔离旧 replay，显式转换后才复用 |

这也是保留当前队列方法设计的理由：项目必须有一套闭合的物理—数据—学习定义。但自定义方法的风险同样明确：实现量大、冷启动可能差、有效 TD 可能因接管和超时变少。**与已有实时训练代码比较，是必要的反证手段，而不是为已定结论安排形式对照。**

RoboReward、Robo-Dopamine 2.0、PRM-as-a-Judge、Large-Reward-Models 等扩展了自动评分选择，但不消除共享模型自我误判、奖励投机和未来信息问题。先在同一份包含双向、失败、遮挡和恢复的留出记录上比较错误与 unknown，再试因果势函数；不能凭视频评分相关性直接改成逐步 reward。[奖励候选与边界](../04_RL与Harness扩展调研_20260923/research/02_自主学习与复位扩展调研.md)

## 9. 最终建议与可推翻条件

### 9.1 目前优先实施的组合

采用 **通用接口＋单 Gateway＋不可变事实日志** 作为项目自有核心；暂用 RPent 组织 GPT 认知／工具；借鉴 Show-Harness 落实语义纠正到本体 adapter；训练运行时先验证 RLinf，复杂度不合算则用 LeRobot。完整头 BC＋队列 RL 保留为已明确写出契约的参考；RAPolicy 优先进入原生头的 P0/P1 预检，不要求先完成完整头的长时间训练才能切换。

这不是把四个仓库原封不动叠在一起：语义动作工具和训练 env 不各自保留设备写循环，飞轮格式不覆盖事实账本，原框架 reward/reset 不自动成为本项目定义。必要适配项已进入技术接口文档。

算法对照同时锁定信息条件：分别声明每个模块的视图、历史长度、派生状态、可获得时间和特征生成成本。可以使用不同编码器，但先共享可获得的信息，或用输入消融区分信息增益与算法增益；训练专用信息不得未经声明进入部署 actor。

### 9.2 三条竞争轴分别验证，避免一次比较一大堆变化

| 竞争轴 | 对照 | 能推翻当前暂定选择的证据 |
|---|---|---|
| 学习方法 | 完整头队列参考；RT-EXPO 实时路线；RAPolicy 原生头；TD3＋BC 补充对照 | 相同双向数据与纠正预算下，独立 policy 改进、可用 TD、总成本更好，且各自时间协议自洽；优先预检，不同时完整移植 |
| 认知／工具骨架 | RPent；OpenETA；Strands；可复用 DimOS／OpenRAL／PhyAgentOS 层 | 同一 GPT、工具、模拟 adapter 与故障回放中，观察、接管、数据完整性和替换成本更好 |
| 辅助系统收益 | 无动作辅助；受限 Harness；VoLoAgent 风格辅助 | 在相同 policy、传感器和调用预算下证明恢复／纠正收益，而非用更多代做掩盖 policy 没学会 |

先用接口回放、离线 BC 与动作可达性检查淘汰明显不合适者，再做少量同预算真机验证。**不要求同时完整移植所有候选。** 若两种框架兼容性相当，优先开发与维护成本低的一种；若证据不足，则保持“待验证”而非虚构性能最优。

### 9.3 首版不加入的复杂度

暂不把世界模型、分布式风险 critic、自适应 BC 权重、语义高层 RL、自动代码无限演化、稠密奖励同时堆入主线。先证明两个方向都能从纠正与真实后果学习，再分别评估新增模块。短时无人窗口是可以实验验证的目标；所有故障和不可恢复状态下永久零人工，当前没有证据可承诺。

## 10. 如何继续学习与复核

建议顺序：先读本报告 §2 和技术方案的一次抓空流程；再读 HIL-SERL／ConRFT 的数据与损失；然后读 RT-EXPO 的实际时间窗及上游代码；再看 Show-Harness 的动作解释器与 RPent 工具层；最后读平台 worker 和本项目接口附录。这样每个论文名都对应一个清楚的工程问题。

| 资料 | 内容 |
|---|---|
| [VLA RL 专项](../04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md) | 原生更新、残差／latent、实时 RL、世界模型与代码阅读记录 |
| [自主学习与复位专项](../04_RL与Harness扩展调研_20260923/research/02_自主学习与复位扩展调研.md) | 历史循环方法、自动纠正、次优干预、奖励与冷启动 |
| [Harness 专项](../04_RL与Harness扩展调研_20260923/research/03_Harness扩展调研.md) | 认知／执行／代码演化、开源边界、关键运行源码 |
| [平台与开源生态专项](../04_RL与Harness扩展调研_20260923/research/04_训练平台与开源生态核查.md) | RLinf、LeRobot、verl-vla、HF、PR 和机构发布 |
| [前期综合调研](../02_自主RL调研_20260922/01_调研报告与选型建议.md) | 早期问题展开和旧候选；排序以本报告与当前技术方案为准 |
| [前轮历史审查记录](../04_RL与Harness扩展调研_20260923/02_连续审查与修订记录.md) | 独立学习、问题、修正及连续通过版本 |

## 11. 三轮如何递进：不是同一轮搜索做三遍

| 轮次 | 先学习与枚举 | 实际深入的方向 | 改变了什么 |
|---|---|---|---|
| **S1 广域补漏** | RL 更新方式／数据／时序；Harness 认知／执行／评分／学习桥，先和旧地图去重 | 论文、官方 GitHub、HF、机构发布与社区索引发现候选，查别名和开放范围 | 补 Flux、FutureRTC、ForceRFT、AGP、SAGE、Harness-Zero 等；Phy 与 REMAC 属旧浅筛深化，不算全新发现 |
| **S2 资产与源码** | 将 S1 宣称拆成采集→buffer/loss→导出→服务、工具→设备→事实链 | 固定 commit 读 Flux／FutureRTC、Phy／AGP／Harness-Zero、LeRobot／OpenPI、SDP 的关键路径 | 修正“有数据即可训练”“有取消即可停止”“PR 未合并就无修复”等表面判断 |
| **S3 联合反证** | 枚举低起点、可学性、动作支持、介入删失、共享目标、独立部署及因果评估反例 | 补 ABC／FlowDAgger／SynthDemo-RL／TORL-VLA；读教师信息差、资源租约、统计原论文及固定代码 | 增加强动态 BC、纠正依赖审计、actor 存活采样修订；将三项验证假设具体化为对照框架 |

三轮均同时覆盖 RL 与 Harness，S2/S3 可以回访同方法，但回答不同问题。检索失败、只能读取摘要／页面、未下载数据等都留在日志；私有论坛与未开放资产不计已审。开源搜索不能证明绝对没有遗漏，也不宣称全球最优。

### 11.1 S1 补漏地图及进入深审的理由

| 方向 | 新增或深化的方法族 | 本次判断 |
|---|---|---|
| 原生／世界模型 RL | ProphRL、Prism-GRPO、SC-VLA、CO-RFT；既有 π0.5／RECAP、RAPolicy、verl-vla 等继续对照 | 想象后果、全失败组质量排序、残差和原生 TD 各有前提；不因支持 VLA 就假定满足真机异步 |
| 纠正与监督 | FluxVLA／FluxDAgger、FineVLA、lehome_solution、SDP | 语言、进度、集合、动作标签各异；人工核验和部署资产范围不可省略 |
| 延迟补偿 | FutureRTC、REMAC；既有 SmoothRL、ARLI、RT-EXPO 等 | 预测未来状态、修正动作和改写 TD 是不同路线；监督延迟适配不等于在线 RL |
| 认知与程序 | AGP、GPT-Policy、SAGE、Harness-Zero、DGAC、VLCP、RHO／HELIX | 从代码生成到 policy 内化有距离；软件任务／特权仿真不能当真机闭环结果 |
| 运行与监控 | PhyAgentOS、RAI、dora、ROSClaw、StageGuard、ARMOR | 运行总线、监控蒸馏、工具权限不替代低层动作策略训练；同名项目、许可与代码阶段要核 |

详见 [S1 RL](research/S1/rl_frontier.md)、[S1 Harness](research/S1/harness_frontier.md)、[S1 生态](research/S1/ecosystem_frontier.md)、[根审补漏](research/S1/root_policy_objective.md)。上述为地图而非已全部源码复现名单。

### 11.2 S2 源码把哪些可用性判断改写了

| 深读对象 | 关键证据 | 本项目吸收／不直接沿用的部分 |
|---|---|---|
| FluxVLA／FluxDAgger | 默认人工控制话题与采集来源可能错位；缺命令补零、保存时模式标签不足以重建 owner；ARM 是进度加权 BC，常量失败进度可走线性 ramp 兜底 | 借数据桥思路；先修真实动作和来源，进度不能直接作为 TD reward。两仓 Apache-2.0 已核 |
| FutureRTC | 真机分支是冻结 π0.5 的 latent predictor MSE；仿真有额外模式；窗口尾仍可等待，未见完整跨 reset 请求屏障 | 可选延迟消融；冻结 base 仍可学习部署组件，但不当作原生在线 RL或完整执行 Gateway |
| PhyAgentOS-core | 执行前持久 intent、调用身份和 GET 对账较明确；所读 core 没有完整硬件 Gateway；unknown、乱序及源时间仍需补 | 进入骨架预检，借持久对账；HTTP 终账不是物理停止／排他 |
| AGP | 工具轨迹与标签有来源差异；数据 schema 明确移除了连续关节、alignment 和 action parquet；源码存在 logger 不使撤下资产重新可用 | 用于工具行为／审计学习；不接成低层 BC／TD。HF正文是访问时main，未声称固定文件字节全部核验 |
| Harness-Zero／SAGE | 前者默认成功阈值筛 SFT，接受建议早于实际后果；后者所查树仅 LICENSE | 可借局部纠正思想；无成功时的默认导出和缺代码均不解决本项目启动 |
| LeRobot | 当前 main 有观测／epoch 同义恢复修复，v0.6.1未含；已出队索引仍非设备执行 | 固定入口与版本；保留出队、下发、生效三层，状态 reset 另测屏障 |
| OpenPI／GR00T | JAX→Torch转换、LoRA未合并PR、normalizer路径、服务dtype各有独立边界；N1.7固定权重LICENSE与卡片宣传有差异 | 逐资产许可核验，模型包数值／配置一致性测试；隔离不兼容依赖环境，不假定品牌权威已排除风险 |
| SDP | 正负动作集合进入监督去噪目标，无真实 TD；集合几何有效不等于物理有效 | 可靠 BC 优先，集合／偏好作为扩展；被替换动作不自动标负 |

这是静态读取范围内的事实或反例，不是已复现的运行故障。固定 SHA、函数和下载失败边界见 [S2 RL](research/S2/rl_code.md)、[S2 Harness](research/S2/harness_code.md)、[S2 生态](research/S2/ecosystem_code.md)、[SDP 源码](research/S2/root_correction_code.md)。

### 11.3 S3 哪些新证据真正影响联合方案

| 方法／机构与原始入口 | 新学习与开放边界 | 联合取舍 |
|---|---|---|
| **ABC，Amazon FAR，2026**：[论文](https://arxiv.org/html/2606.27375)、[代码](https://github.com/amazon-far/abc) | 持续 DAgger与混合数据；24→85为平均任务进度，不是成功率。固定代码默认只导出介入段／可用同训练集验证，不等于论文配方。PR23修复目标时间线且原址更新数据hash；权重／数据另有条件 | 加强动态BC及数据身份检查，不用其大预训练预算替换本项目少示范约束 |
| **FlowDAgger，Microsoft Research／UW**：[代码与透明度](https://github.com/microsoft/FlowDAgger) | 冻结base，纠正反演latent后BC训练steering；π0.5／MetaWorld与GR00T／LIBERO有不同backend。反演有可达域和信息条件，部分模式默认全专家采集或成功回合筛选 | 条件性纠正吸收对照；不是已有在线TD栈，不因base冻结否定复合policy学习 |
| **SynthDemo-RL，2026**：[论文](https://arxiv.org/html/2609.21650v1) | 特权仿真程序经LLM修订产出成功示范后SFT＋PPO；作者真实视觉闭环初试失败，硬件成功展示为名义摆位后的开环轨迹回放；未核完整官方训练资产 | 支持首批成功覆盖诊断，也反证“程序能执行所以policy已可学”；不当作真机自动闭环基线 |
| **TORL-VLA，2026**：[论文](https://arxiv.org/html/2606.09337v1)、[项目](https://torl-vla.github.io/) | task Q与intervention-censored Q分开；依赖介入指示失败，另有参考动作约束；主要代码仍待发布 | 辅助风险目标参照，不把unknown／主动观察接管写成任务负奖励；不替换当前主目标 |
| **CritiQ/ReTRy，Cornell；SITT，UZH RPG**：[前者](https://arxiv.org/abs/2505.09546)、[后者](https://arxiv.org/abs/2412.09149) | 教师额外信息可使纠正不可辨识；SITT所核开放实现只覆盖maze，机器人实验不能因此视为可复现 | 程序候选考虑学生可见性，标签记录依赖观察；不要求另建强教师policy |
| **RLDG、Scaling Up、AnyTask**：[RLDG](https://generalist-distillation.github.io/)、[Scaling Up](https://github.com/real-stanford/scalingup)、[AnyTask](https://anytask.rai-inst.com/) | 数据质量／状态覆盖、程序→policy有机制依据；仿真真值、已有专家、频率差和开放范围各有限制 | 把可靠监督、真实探索、恢复机会三条贡献分开验证，不强制每个恢复动作都被policy模仿 |
| **SafeEvolve／HASE**：[前者](https://arxiv.org/abs/2609.02786)、[后者](https://arxiv.org/abs/2607.03935) | 软件agent的辅助退出只部分内化；SafeEvolve默认奖励权重随路径改变；HASE的可变评价依赖外部锚点 | 作为归因反例，不外推机器人性能；本项目固定rubric并单独验证辅助退出 |
| **STEP／N-SCORE／Rliable**：[STEP](https://arxiv.org/abs/2503.10966)、[N-SCORE](https://arxiv.org/abs/2603.13616)、[Rliable](https://arxiv.org/abs/2108.13264) | 统计工具与代码可查；相关循环、共享起态及重复版本选择需要适合的抽样／停止规则 | 首版预注册固定样本；需要顺序停止时再选匹配方法，不用普通区间反复试到过线 |

这些工作有不同论文／代码／部署范围，不能横排成功率。S3实际新读与旧回访、公式、固定源码和资产缺口见 [RL联合反证](research/S3/rl_joint.md)、[Harness联合反证](research/S3/harness_joint.md)、[证据与验证](research/S3/evidence_validation.md)、[根审验证设计](research/S3/root_validation.md)。

## 12. 联合选择为什么仍需要预检，而不是宣布唯一最优

首批只联调少数入围者。RAPolicy 的已有运动先验和弱起点真机证据使它值得先检验；RT-EXPO提供更接近连续执行的实代码，但其起点、编辑域和成功BC有边界；完整头拥有更大的动作表达自由度，却要承担探索与冷启动成本。三者都不能免测。

预检顺序是：可靠纠正在部署输入下是否可学 → base有限候选是否覆盖 → 编辑或latent是否可达 → Q是否选对 → 纠正能否迁移为无GPT闭环 → 时序与总成本。少量示范下完整头难学时优先保留原生先验；编辑覆盖反复缺关键动作时优先原生更新或完整头。零成功率本身既不能证明编辑不可行，也不能证明RL可以自动启动。

Harness比较固定同一GPT、工具schema、故障记录和模拟adapter；RPent、OpenETA、Phy各按替换控制通道、独立观察、日志缺口与开发工时比较。自有Gateway、goal与数据契约不可被任何候选默认值覆盖。ROS2资源claim／Spot lease只作执行机制参考，不冒充通用认知Harness。

程序库首先通过物理有效性、版本、记录和预算门禁；周期性再测它是否带来policy增益或等能力的成本降低。四格“旧新policy×旧新Harness”只能定位冻结运行贡献，训练收益需要从同一初始policy分叉的固定库／扩展库实验。开发方案和专家汇报已经用H1/H2/H3的图及执行说明明确这些区别。

## 13. 开放性、影响力与可信度怎样使用

§7保留前轮可复核的stars／HF下载快照，**不是本次统一重抓的实时排行榜**。本次没有获得所有候选同步可信的引用量或下载量，不补造缺失值。Microsoft、Amazon、Stanford、Berkeley、HF等机构提高来源可追溯性，不能代替代码范围、实验条件和独立复现。

| 维度 | 本次如何审核 | 对选择的含义 |
|---|---|---|
| 方法证据 | 原论文目标、初始能力、示范／人工、评估分母与动作协议 | 判断是否回答本项目问题，不按摘要分数排序 |
| 开放资产 | 训练／部署／权重／数据／依赖分别核查 | README或HF论文页不能当完整实现；gated和未得文件明确标注 |
| 源码可信度 | 固定commit、实际函数、默认模式、PR最终diff与当前代码对照 | 静态路径只证明有该逻辑，不等于运行缺陷已复现 |
| 维护与社区 | 官方issue／PR、版本及公开讨论作线索 | 修复活跃有价值，但stars不是第三方真机复现数量 |
| 许可 | 代码、底模、数据和驱动分别记录 | 根仓许可不覆盖全部资产；冲突未澄清前不作为已可部署依赖 |
| 本项目可达性 | 通用接口、动作与时间契约、小预算可学性、工程成本 | 品牌支持只影响部署成本，不作为核心方法优劣 |

本次未完成候选的独立运行复现；未接受数据gate、下载大模型或执行第三方机器人程序。合法但不完整的开放资产仍可提供设计启发，不能写成已集成。所有量化作者结果均限定在原实验条件。

## 14. 推荐阅读路径与剩余问题

1. 先读开发方案的一次“抓空—纠正—学习”和本报告§2，理解共享policy、Harness、Gateway及BC/TD各自责任。
2. 再读既有HIL-SERL／ConRFT机制、RAPolicy与RT-EXPO，结合S3动作覆盖和时间目标反例；不把名称当可互换配置。
3. 读ABC／FlowDAgger／SDP与S2数据链，理解永久buffer、可靠标签、真实后果与模型发布的区别。
4. 读RPent／OpenETA／Phy及S3信息差和资源排他，理解GPT观察生成代码怎样变成可执行、可学习行为。
5. 用专家汇报H1/H2/H3图讨论实验，再查开发§13与接口附录逐项实施。

三轮专题均附查询／读取日志；[S1根审](research/S1/00_根审总结与S2入口.md)、[S2根审](research/S2/00_根审总结与S3入口.md)、[S3根审](research/S3/00_根审总结与选型裁决.md)记录递进。正式文档的独立审查另见 [交付与审查记录](04_交付与连续审查记录.md)，三轮研究不抵充五轮审查。

剩余决定性问题是：当前少量双向示范与GPT纠正能否被部署policy学习；哪条路线有足够动作支持与合法TD；真实时延、介入删失、共享迁移和总成本能否过门槛。本文将未知转成了可执行实验，没有把未知改写成效果保证。
