# RL 与 Harness 开源基线深度调研报告

2026-09-23｜与技术方案 v3 配套｜论文、公开资产和选定源码审核；未安装候选框架、运行训练或进行真机实验。

本文回答“哪些方案值得选、为什么、还缺哪些证据”。具体开发流程见 [技术方案](../03_RL_Harness自主学习系统_20260922/01_RL_Harness真机自主学习技术方案.md)，时间和数据定义见 [异步附录](../03_RL_Harness自主学习系统_20260922/06_异步动作时间轴与学习目标.md)。读者可以先读第 1、8、9 节了解结论，再按兴趣进入方法和源码材料。

## 1. 本轮结论：保留总体闭环，扩大真正有竞争力的候选

**继续采用“共享目标条件 policy＋可信 BC＋真实经验 RL＋GPT Harness 自动观察与纠正”的总体方案，但不再把完整动作头或 RPent 当作已经证明最优的唯一选择。** 本轮找到的可用资产足以改变对照和工程路线，尚不足以证明某个现成仓库可以直接交付全部系统。

最重要的修正如下。

| 本轮发现 | 对方案的实际影响 |
|---|---|
| Real-Time EXPO-FT 已有异步执行、动作回填、RTC 和在线训练代码 | 升为首要异步 RL 工程挑战者；纠正此前只看普通 EXPO 分支造成的遗漏。它就在此前固定提交中，不是刚刚补开源 |
| verl-vla 提供 π₀.₅ TD3＋BC 原生动作头配方 | 增加保留原生 VLA 头的直接更新对照；不能只在旧 ConRFT 和自定义完整头之间选择 |
| RLinf 已有真机 worker、replay、VLA 与在线学习入口；LeRobot 更新了 RL 接口 | 明确训练运行时候选，减少从零重建；两者默认 target 都不等于本项目队列 RL |
| Show-Harness 提供具体的语义小步、本体解释器和统一记录接口 | 把 GPT 的“纠正建议”落实为可执行工具链；不要求 RL policy 改成语义 token policy |
| Strands、DimOS、OpenRAL、VoLoAgent 提供不同层的可用系统 | 将它们纳入通用接口和辅助执行对照；RPent 仍是暂定认知骨架，须通过同一接口预检 |
| UniIntervene 真正算法仓库已发布；SiLRI／GAINS 等有明确代码边界 | 修正“有无开源”和“可直接融合”的判断；离线恢复组件、单步 SAC 不能直接当异步 VLA RL |

**通用性是主标准，AgileX 适配不是核心筛选项。** 优先看组件可替换性、跨本体接口、RL／执行／数据语义、代码完整度和复现证据。现成机械臂适配只影响首次部署成本。通用框架也不意味着同一权重、坐标、动作维度和标定可以免修改迁移。

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
- **历史沿用**：此前已研究，本轮用于完整地图与交叉检查，不包装成新增深审。

开源要分别看论文、训练代码、部署代码、权重、数据、依赖和许可证。GitHub 有地址、HF 有论文页、演示视频可看，都不是完整开放训练系统的充分条件。下面的效果数字均为作者条件下报告，不进行跨任务成功率排行榜。

## 4. RL 候选：按技术路线学习

### 4.1 成熟的示范＋真机离策略学习

HIL-SERL、ConRFT／HIL-ConRFT、RLPD、AWAC、Cal-QL 构成此前路线的基础：真实经验和示范可以混合，离线数据可改善启动，在线交互提供新的后果，BC 或一致性项帮助维持可用行为。它们仍值得保留，理由是机制和真机证据，而不是发布时间。

其中 HIL-SERL 不能直接等同原生 VLA；ConRFT 的模型和训练假设也不能无改造搬到 π₀.₅ 与真实异步 chunk。本轮没有把旧基线“淘汰”，而是把它们从整套方案名称拆为可复用的训练机制。前期原理和固定代码详见 [历史 RL 源码审计](../03_RL_Harness自主学习系统_20260922/07_共享策略与异步RL联合选型证据.md)。

对不完美纠正，新补查的 SiLRI、GAINS、PACT、E2HiL 分别研究状态相关模仿权重、接管收益分布、次优片段归因和样本筛选。**它们解决的是纠正如何用得更好，不是 GPT 如何可靠地产生纠正。** SiLRI 固定源码的 chunk 接口仍未实现；接管熵低不代表动作正确。GAINS／PACT 的接管负奖还必须避开“主动观察、超时、目标切换也触发接管”的误归因。[SiLRI 代码](https://github.com/nuomizai/HIL-RL)、[PACT 论文](https://arxiv.org/abs/2606.03949)、[E2HiL 项目](https://e2hil.github.io/)

### 4.2 Real-Time EXPO-FT：最值得新增实测的异步方案

Stanford 的 Real-Time EXPO-FT 于 2026-09-16 发布，关键价值是把慢 VLA、RTC 前缀、快速编辑、实际执行窗口和在线数据放在同一个实现里。作者在四项动态真机任务报告平均成功率约 42%→97%、在线交互约十分钟量级；已有 RTC-SFT、自动检测、任务设置和 DROID 依赖都必须同时保留，不能外推为本任务的预期指标。[论文](https://arxiv.org/abs/2609.18207)、[项目](https://pd-perry.github.io/real-time-expo-ft/)

这次读到了固定提交 `803381fc3b4c91a0c47904f1b688fc5e35904f50` 下真正的实时学习器、采样器和 replay。**此前“EXPO 缺少异步实现”的概括不成立。** 原生 VLA、编辑器与 critic 分开更新：失败帮助 Q 和编辑；原生 VLA 主要通过成功数据的 RTC-BC 改变；编辑仍有界。因此，它不是永久冻结的 base，但也不是 Q 直接训练整个 flow 头。[固定学习器](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)

对我们最关键的测试是：可靠 Harness 纠正是否落在 base 候选＋允许编辑的可达范围，新增 BC 是否能扩展后续基础分布。若覆盖充足，保留运动先验可能比重学完整头省样本；若抓取／释放等必要动作一直无法产生，有界编辑就可能成为瓶颈。不能仅凭初始成功率低决定胜负。

它与当前队列 RL 仍有协议差异：较新观测编辑、候选缓存、filtered backup 和固定窗口各有条件。**不能把其 replay 数据直接喂给本文另一套 Bellman 目标。** 应先各自实现完整时间契约，再在同等真机、示范、Harness 和算力预算下比较。细节见 [VLA 专项 §4](research/01_VLA_RL扩展调研.md)。

### 4.3 原生 flow 直接改进：确实有更丰富的新路线

| 路线 | 为什么值得关注 | 当前不能直接升级主线的原因 |
|---|---|---|
| [verl-vla π₀.₅ TD3＋BC](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html) | 已有直接更新原生动作头的开放配方 | 示例是 8 GPU、32 并行仿真；起始模型虽然只 SFT 100 步，数据池仍有 432 episodes；实体相同配置未验证 |
| [Q-VGM](https://arxiv.org/html/2606.08015v5) | 用 Q 引导 flow 速度目标，直接改 action expert | 本轮未核到官方完整训练仓库；最新版真实提升的离线条件不能改写成无人在线 |
| [OTQL](https://ansocho.github.io/otql-flow/) | 用最优传输构造 flow 的价值改进目标 | 作者 Code 仍标 Coming Soon；方法适合度高不等于工程可达性已高 |
| [LWD](https://finch.agibot.com/research/lwd) | 共享 VLA、DIVL/QAM、混合成功失败及 failure play | 16 台机器人、652.5 小时离线数据，完整训练包未核到；整块执行不同于本项目异步中段 |
| [PA-RL](https://policyagnosticrl.github.io/) | 先用 Q 优化动作再蒸馏，可兼容多种 policy | 是成熟重要思路；共享目标、真实队列和 Harness 数据仍需具体集成 |
| [RedFlow](https://arxiv.org/abs/2607.27782) | 失败轨迹参与 flow 行为调整 | 不能把检索得到的替代动作伪配真实后继；尚不是完整在线闭环 |

RECAP／π*₀.₆、RLT、DSRL、ZPRL、PLD、Robo-ValueRL、RL²-VLA 也在本轮地图中，分别涉及价值条件化、特征／latent、残差、蒸馏与在线适配。对它们统一追问：**谁真的被 RL 更新，约束指向什么分布，是否依赖大量离线行为，失败怎样进入学习？** 不能因为标题含 VLA RL 就认为动作自由度与数据用法相同。[完整候选地图及分层](research/01_VLA_RL扩展调研.md)

### 4.4 世界模型和大规模仿真：保留后续路线

RISE、VLA-MBPO、WMPO、VLAW、World-Gymnast、WCM，以及新近 Imagine-RL、Prioritized Rollouts，覆盖模型内训练、历史价值表征和想象数据分配。FPO／FPO++、RIPT-VLA、π-StepNFT、Z-1 等扩大了 flow 与 VLA 的 RL 工具箱。它们可帮助后续提高样本效率，但必须另计模型数据、误差、算力和仿真复位条件；不把想象轨迹混成真机事实。[VLA 专项 §3、§5–7](research/01_VLA_RL扩展调研.md)

其中 WCM 当前更适合价值模型部件参考；FlashRT 更接近推理／条件化推理工程。推理快能改善控制，不能单独替代 reward、replay 和更新器。

## 5. 自主循环：哪些老问题被新方案改善了

Leave No Trace、R3L、MTRF、MEDAL++、ARIEL、ReLMM、RoboFuME、RISC、MoReFree、RM-RL 等说明：持续学习需要把起始状态、可恢复区域和任务调度一起考虑。“反向恢复”不必是把正向动作倒放，也不保证共享参数必然正迁移。对于 A↔B，两个方向可以共享 θ；每个方向的目标、奖励、Q 和数据标签仍必须明确。[历史与新增复位路线表](research/02_自主学习与复位扩展调研.md)

本轮有三项值得具体吸收。

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

RPent 最新提交 `6ee7069` 的父提交正是前次审计的 `eb269c8…`。本轮检查变更清单与新增文档：主要增加 RoboCasa／RoboTwin 探索、记忆和测试，探索仍用环境普通 reset，并导出最终成功命令。它提升了探索覆盖，但不是本项目真机自动复位与全来源 RL 日志的完成证明。本轮未宣称对 28 个变化文件做了完整源码审计。[提交与差异](https://github.com/RLinf/RPent/commit/6ee7069)

Show-Harness 的新增价值是让“GPT 纠正”变得具体：语义小步经本体解释器变为低层动作，并保存变换与反馈。**选择它不是因为碰巧使用 AgileX。** 同一接口可以接不同本体；上层仍需明确坐标、夹爪、时效和前置条件。它的默认初始化／RELEASE 不可照搬到中途持物接管，DONE 也不能直接给成功 reward。[论文](https://arxiv.org/abs/2609.10522)、[固定 runner](https://github.com/showlab/Show-Harness/blob/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/real.py)

VoLoAgent 来自 NVIDIA，有真机 FR3 实验和开放代码，但每方法仅 42 次试验，完整组合并不在所有消融上最好。这支持增加严格系统对照，不支持“加大模型一定更好”的判断。[原文](https://arxiv.org/abs/2606.07723)

### 6.2 通用工程底座的竞争者

**Strands Robots** 提供工具代理、统一设备／policy、RTC、记录、训练和远程编排，是值得认真比较的工程挑战者。官方硬件目录区分 real 与 sim，RL 文档当前主要是 SimEnv 的从零学习；这些限制必须看清，但不能因为 Piper 尚是 sim-only 就否定它的通用性。[官方架构](https://strands-labs.github.io/robots/architecture/)、[Amazon 发布](https://huggingface.co/blog/amazon/strands-lerobot-hub-to-hardware)

**DimOS** 的数据流和 ControlCoordinator 可研究为运行层组件；**OpenRAL** 的类型化技能、HAL、世界状态和独立控制边界可研究为接口范本。二者都不是拿来就能满足本项目 TD／DAgger 的完整训练系统；也不因某个厂商适配欠缺而淘汰。[DimOS](https://github.com/dimensionalOS/dimos)、[OpenRAL](https://github.com/OpenRAL/openral)

**Open-RAIL** 是另一项目，来自中国移动团队，重点是异步推理、机器人接入和数据记录。它可补动作执行工程，与 OpenRAL 不同，也不是认知 Harness。[项目](https://cmcc-tao.github.io/open-rail/)

### 6.3 不同层的 RL 和“自主”必须分开

REAL 的 MCP 高层工具 agent 经 SFT／RL，HARBOR 自动搭建仿真、奖励和训练流程；它们分别学习工具选择、自动化开发劳动，不能误当真机 VLA 动作 learner。HoloAgent、ENPIRE、Zetta、EmbodiSkill、AgentSpec、HiRobot 等保留在完整地图中，按空间记忆、失败恢复、技能组合或兼容性研究取用。[REAL](https://github.com/InternRobotics/REAL)、[HARBOR](https://github.com/supersglzc/harbor-rl)、[Harness 专项](research/03_Harness扩展调研.md)

NVIDIA GR00T、Google Gemini Robotics 2／ER2、PI 等公司发布提高了可用模型和工具的上限，但 API、开放底模、早期合作与完整训练代码必须分别计证据。本轮保持用户指定 GPT-6 主观察器；奖励模型和其他 VLM 作为校准、成本或延迟对照，不自动更换。[机构与奖励核查](research/04_训练平台与开源生态核查.md)

## 7. 开源资产、影响力与复现可信度

### 7.1 训练平台：更适合用“能复用什么”比较

| 平台 | 已核的可复用资产 | 必须新增／验证 | 当前定位 |
|---|---|---|---|
| RLinf／RLinf-USER | 真机 actor/learner、replay/demo、VLA、在线学习入口、RTC 评估 | goal/queue、BC 纯标签支路、目标函数、单设备 owner、模型与协议组合 | 首先验证的运行时 |
| LeRobot 0.6 | 设备／数据生态、拆分的算法接口、online/offline mixer、HIL-SERL 示例 | VLA 表征与目标头、显式 BC、队列 TD、事实和标签版本 | 单机轻量备选 |
| verl-vla | π₀.₅ 直接 RL 配方、工作流、trainer、分布式训练 | 同配置真机证据、异步物理协议、自动纠正与共享双向 | 原生动作头直接更新对照 |

具体源码已经读到：RLinf 默认 critic 分支的 reward 聚合／discount 不等于本文队列目标；LeRobot mixer 混 transition，不替纯建议补后继；verl-vla episode trainer 的有效段也不能代替物理接管协议。这些是需要开发 adapter/loss 的证据，不是说上游自己的环境定义错误。[固定源码与差别](research/04_训练平台与开源生态核查.md)

另外，LeRobot issue 中引用的 ConRFT PR 链接实际指向视频编码修改，QC-FQL PR 仍为 Draft。路线图、PR 标题和计划不是已合并功能；这种检查比只读 README 更能避免选到不存在的组合。[路线 issue](https://github.com/huggingface/lerobot/issues/3076)、[QC-FQL PR](https://github.com/huggingface/lerobot/pull/1818)

### 7.2 影响力不伪精确，也不替代适配性

本轮网页快照中 LeRobot 约 27.7k stars／5.7k forks，RLinf 约 5.4k／744，verl-vla 99／20；缓存页会稍有差异。它们说明社区关注，不是独立真机复现数量，且不能用母项目 verl 的热度替子项目背书。[LeRobot](https://github.com/huggingface/lerobot)、[RLinf](https://github.com/RLinf/RLinf)、[verl-vla](https://github.com/verl-project/verl-vla)

HF 下载按具体权重统计，不能混成方法下载量。某 RLinf Pick_Red 模型没有 model card、下载未追踪，就应写未知；π₀.₅ TD3＋BC 起点模型约 36 月下载、RPent BEHAVIOR 权重约 34 月下载，都只是当日页面值。框架 Apache、主仓 MIT 不能覆盖底模、数据与机器人驱动的许可。[平台开放性细节](research/04_训练平台与开源生态核查.md)

本轮没有取得全部候选可靠且同步的引用计数，故不编造统一引用榜。Stanford、Berkeley、NVIDIA、HF、ByteDance、AGIBOT 等机构及同行评审是可信度的一部分；完整源码、透明实验条件和第三方复现才使“我们可达”更可信。尚未找到的第三方复现记未核验，不以论文视频或 stars 代替。

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

RoboReward、Robo-Dopamine 2.0、PRM-as-a-Judge、Large-Reward-Models 等扩展了自动评分选择，但不消除共享模型自我误判、奖励投机和未来信息问题。先在同一份包含双向、失败、遮挡和恢复的留出记录上比较错误与 unknown，再试因果势函数；不能凭视频评分相关性直接改成逐步 reward。[奖励候选与边界](research/02_自主学习与复位扩展调研.md)

## 9. 最终建议与可推翻条件

### 9.1 目前优先实施的组合

采用 **通用接口＋单 Gateway＋不可变事实日志** 作为项目自有核心；暂用 RPent 组织 GPT 认知／工具；借鉴 Show-Harness 落实语义纠正到本体 adapter；训练运行时先验证 RLinf，复杂度不合算则用 LeRobot；方法从共享完整头的 BC＋队列 RL 开始验证。

这不是把四个仓库原封不动叠在一起：语义动作工具和训练 env 不各自保留设备写循环，飞轮格式不覆盖事实账本，原框架 reward/reset 不自动成为本项目定义。必要适配项已进入技术接口文档。

### 9.2 三条竞争轴分别验证，避免一次比较一大堆变化

| 竞争轴 | 对照 | 能推翻当前暂定选择的证据 |
|---|---|---|
| 学习方法 | 完整头；RT-EXPO；原生 π₀.₅ TD3＋BC | 相同双向数据与纠正预算下，独立 policy 改进、可用 TD、总成本更好，且各自时间协议自洽 |
| 认知／工具骨架 | RPent；Strands；可复用 DimOS／OpenRAL 层 | 同一 GPT、工具、模拟 adapter 与故障回放中，观察、接管、数据完整性和替换成本更好 |
| 辅助系统收益 | 无动作辅助；受限 Harness；VoLoAgent 风格辅助 | 在相同 policy、传感器和调用预算下证明恢复／纠正收益，而非用更多代做掩盖 policy 没学会 |

先用接口回放、离线 BC 与动作可达性检查淘汰明显不合适者，再做少量同预算真机验证。**不要求同时完整移植所有候选。** 若两种框架兼容性相当，优先开发与维护成本低的一种；若证据不足，则保持“待验证”而非虚构性能最优。

### 9.3 首版不加入的复杂度

暂不把世界模型、分布式风险 critic、自适应 BC 权重、语义高层 RL、自动代码无限演化、稠密奖励同时堆入主线。先证明两个方向都能从纠正与真实后果学习，再分别评估新增模块。短时无人窗口是可以实验验证的目标；所有故障和不可恢复状态下永久零人工，当前没有证据可承诺。

## 10. 如何继续学习与复核

建议顺序：先读本报告 §2 和技术方案的一次抓空流程；再读 HIL-SERL／ConRFT 的数据与损失；然后读 RT-EXPO 的实际时间窗及上游代码；再看 Show-Harness 的动作解释器与 RPent 工具层；最后读平台 worker 和本项目接口附录。这样每个论文名都对应一个清楚的工程问题。

| 资料 | 内容 |
|---|---|
| [VLA RL 专项](research/01_VLA_RL扩展调研.md) | 原生更新、残差／latent、实时 RL、世界模型与代码阅读记录 |
| [自主学习与复位专项](research/02_自主学习与复位扩展调研.md) | 历史循环方法、自动纠正、次优干预、奖励与冷启动 |
| [Harness 专项](research/03_Harness扩展调研.md) | 认知／执行／代码演化、开源边界、关键运行源码 |
| [平台与开源生态专项](research/04_训练平台与开源生态核查.md) | RLinf、LeRobot、verl-vla、HF、PR 和机构发布 |
| [前期综合调研](../02_自主RL调研_20260922/01_调研报告与选型建议.md) | 早期问题展开和旧候选；排序以本报告与当前技术方案为准 |
| [本轮审查记录](02_连续审查与修订记录.md) | 独立学习、问题、修正及连续通过版本 |

## 11. 覆盖、版本与剩余证据缺口

本轮从两方向机制总结出发，按算法族和系统层宽搜，再对可能改变选择者深读。论文、GitHub 固定代码／release／issue／PR、HF 模型与数据卡／官方博客、机构发布和社区索引均有实际检索记录，见四份专项末尾。旧调研中已经出现的 AutoSERL、SiLRI、GAINS、LWD 等明确标作重核；新增深审与浅筛也分开。

网络限制包括 GitHub 未认证 API 限流、部分 git/raw 超时；可访问网页、固定 blob 和部分本地下载用于交叉核验。未登录的私有论坛、未开放训练资产和无法访问的依赖不计作已审核。不把没有找到代码解释成代码必不存在，不声称穷尽全球所有方案。

当前最重要的未知是 **少量双向示范＋可靠 Harness 纠正，能否让某条动作参数化路线更快达到可用；以及真实异步下能保留多少合格训练数据。** 接口审查可以缩小风险，不能代替这个实验。本文对可行性的判断和主线选择均受上述实测门槛约束。
