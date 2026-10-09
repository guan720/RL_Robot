# 具身 Harness 扩展调研：从机器人代理到真机自主学习运行系统

调研日期：2026-09-23。本文是独立扩展调研材料，供总报告融合，不代替最终技术方案，也不是三轮评审的完成证明。研究对象是同一 goal-conditioned policy 的正反向 BC＋在线 RL，以及 GPT6＋Harness 的观察、纠正和恢复。松灵 ALOHA 类平台上的单臂抓放是首个部署实例。按用户最新澄清，**通用性、跨本体接口、模块可替换性、代码完整度和 RL 融合优先于现成 AgileX 适配**；具体型号未确认只影响部署工作量，不能据此淘汰通用方案或判定赢家。

## 1. 本轮结论

本轮发现了此前选型不应遗漏的新候选，其中 **Show-Harness 为通用的“语义纠正→本体动作解释器”提供了具体参考**：它将视觉语言模型输出的小步动作与本体控制实现分开，并公开人和代理共用的操作、记录与训练接口。它应进入纠正模块的实现候选，而不是仅列入相关工作。AgileX 真机实例有助于首站验证，但不是优先选择它的决定性理由。

**VoLoAgent 是值得增加的独立系统对照组**，有 NVIDIA 的真实机械臂实验和开源代码；**Strands Robots、DimOS、OpenRAL 都应作为通用工程底座候选比较**。它们的统一接口与跨本体组织可能优于直接修补研究代码。评价时应继续审核真实执行、停止和数据语义，而不是仅凭硬件数量、机构或功能列表排序。Piper 是否现成可用只计入首次部署成本。

因此，我的建议是：**先确定通用 Harness 接口和唯一 Gateway/数据契约，再比较 RPent、Strands、DimOS/OpenRAL 各层的复用成本；将 Show-Harness 的动作解释器作为纠正实现候选，并增加 VoLoAgent 对照。** RPent 可暂保留认知骨架，但不能仅因已经使用就预先宣布最终胜出。没有发现公开证据足以支持“某一个仓库已经完整解决本项目的正反共享策略、GPT6 自动接管、真实异步 chunk、BC＋真机在线 RL、无人工持续运行”。这是证据判断，不是断言不存在尚未公开或本轮未检索到的实现。

## 2. 先把 Harness 的问题分清楚

机器人 Harness 至少包含以下不同工作。一个框架只覆盖其中一部分时，不能用同一个“自学习”标签掩盖差别。

| 层次 | 要解决的问题 | 对本项目的意义 |
|---|---|---|
| 认知与观察 | 从图像、状态、历史中判断进展、失败、下一步 | GPT6 可作为主观察者和纠正决策者；不要求预先有强 policy |
| 动作落地 | 语义意图如何变成机器人可执行且有界的命令 | 需要坐标、标定、运动学、抓手语义和执行反馈；语言能力不能取代这些接口 |
| 运行与接管 | 谁拥有机器人、何时能抢占、何时确实停止 | 不能把取消模型请求、清空 Python 队列当成硬件已停止 |
| 数据与学习 | 纠正建议、实际动作、失败、下一状态怎样回流 | 支持保存数据不等于满足 RL 因果数据与异步训练目标 |
| 能力演化 | 更新技能代码、记忆、上下文、模型参数 | 代码改进、代理辅助成功率提高、policy 参数学习是三条不同证据链 |
| 训练工程代理 | 自动写仿真、reward、训练脚本、调超参数 | 可降低开发劳动，但不是运行时替代真机观察员 |

当前系统的主体不是“用大模型不断替 policy 做任务”，而是让 Harness 的有限纠正逐步进入同一正反向 policy 的 BC＋RL 学习。评估时必须同时记录独立 policy 成功率、系统辅助成功率和每小时人工/自动接管次数；否则可能只证明 Harness 更擅长救场，没有证明 policy 在变强。

## 3. 检索方法、覆盖范围和证据强度

### 3.1 本轮检索路径

检索同时覆盖 arXiv/论文站点、作者及机构主页、官方 GitHub、官方 Hugging Face 模型与数据页、公司发布和社区索引。社区榜单与 PR 用于发现，关键结论回到论文、官方文档或源码核验。下列是本轮实际使用的检索方向与发现路径，不意味着穷尽所有同义检索。

| 检索方向/关键词族 | 主要发现 | 后续核验 |
|---|---|---|
| embodied robot harness / robot agent framework / agentic robotics 2026 | Show-Harness、VoLoAgent、OpenRAL、RoboClaw | 论文＋仓库＋关键代码 |
| robot-use、AgileX、Piper、VLM atomic action、DAgger | Show-Harness/GUMI | 真机配置、控制器、抢占、记录、HF |
| NVIDIA robot VLM failure recovery open source | VoLoAgent、ENPIRE | 论文、代理服务器与监控接口 |
| AWS Strands robotics LeRobot、robot natural language runtime | Strands Robots | 官方 Amazon HF 博文、硬件目录、RL/RTC 文档、执行代码 |
| dimensionalOS agent harness control coordinator Piper | DimOS | 仓库、发布记录、操控文档、讨论区 |
| OpenRAL typed robot layer HAL safety kernel | OpenRAL | 官方机器人表、路线图、代码结构 |
| robot autonomous data collection inverse reset agent | RoboClaw | 原始论文、代码与发布边界 |
| embodied agent MCP SFT RL InternRobotics | REAL | 论文、训练环境与真机实验口径 |
| robot RL agentic harness reward generation | HARBOR | 论文、官方仓库与安装入口 |
| self-evolving embodied skill harness | SHAPER、EmbodiSkill | 论文、机构页、可用代码情况 |
| code as policies RL benchmark / embodied agent composition | CaP-X、AgentSpec | 作者仓库与基准任务范围 |
| Google Gemini Robotics 2 / PI hierarchical robot / HF robot agents | ER2、HiRobot、Reachy Mini | 公司/机构官方发布与开放层级 |
| awesome agentic robotics / multimodal embodied agent | 追加线索与交叉检查 | 不将收录或点赞当成实证 |

检索时排除了与机器人执行无关的同名软件开发 Harness；将只提供仿真代理或设计稿的项目留作方法参考。原有 RoboRSI、RPent、ENPIRE、Zetta 等结论结合上一轮材料，不以重复阅读代替扩展搜索。

### 3.2 阅读深度及可复核性

本轮对 Show-Harness、VoLoAgent 和 Strands 的关键路径做了源码阅读；OpenRAL、DimOS、REAL、RoboClaw、HARBOR、SHAPER 等主要依据论文、官方文档及部分代码，不能称为完整源码审计。没有安装这些框架、运行训练或实际控制机器人。

GitHub API 本轮出现 403 限流，直接 git/raw 网络也遇到代理/超时；后续通过网页工具读取原始代码、提交页及固定提交文件页，取得以下完整 SHA。`harness_evidence/repo_snapshot.json` 留存的是失败记录，不能当作成功抓取的元数据快照；成功核验的版本另存于 `harness_evidence/pinned_sources.json`。本轮完成在线源码阅读，未保存和运行完整源码树。

| 项目 | 本轮确认提交 | 核验内容 |
|---|---|---|
| Show-Harness | `137d5718c3b7af0150764d8f9beeb252c9f2794a` | 固定提交下回读 real runner、Piper 控制器、DAgger、preemption、GUMI 文档 |
| VoLoAgent | `b4e623079ca8498a16bcd5016920d71f76c44d30` | 固定提交下回读 proxy；此公开仓库为单次初始发布，不代表内部只开发过一次 |
| Strands Robots | `4d0203161a587e29d7912c99da74878e8f989544` | 固定提交下回读 run_policy；当前提交还修正多项 Isaac 实际行为与文档不符问题 |
| OpenRAL | `02506411bb6007beb5e36a3b72183f494235ea46` | 提交及固定文件页确认；机器人验证范围以官方路线图为准，未完成内核关键路径源码审计 |
| RPent | `6ee7069`（main） | 旧审计 `eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1` 已非 HEAD；根审已补读当前提交的选定差异／文档，未做全库运行审计 |

提交入口：[Show-Harness](https://github.com/showlab/Show-Harness/commit/137d571)、[VoLoAgent](https://github.com/NVlabs/VoLoAgent/commit/b4e6230)、[Strands](https://github.com/strands-labs/robots/commit/4d02031)、[OpenRAL](https://github.com/OpenRAL/openral/commit/0250641)、[RPent](https://github.com/RLinf/RPent/commit/6ee7069)。未拿到固定提交的项目，其链接代表访问时页面状态，不冒充不可变快照。

## 4. 候选全景

“开放”按可访问层次描述；许可证未核验写未核验，不从公开 GitHub 页面推定所有权重、依赖和资产也可商用。

| 候选 | 主要能力与证据 | 开放情况 | 对当前任务的判断 |
|---|---|---|---|
| [OpenETA](https://github.com/OpenMOSS/OpenETA) | 工具契约、新观测义务、证据与经验候选；通用 Harness | Apache-2.0 主仓；固定源码选读，policy adapter 未全部完成 | **新增骨架对照**，与 RPent 同门槛比较，仍需独立观察／实体停止／RL 数据桥 |
| [RPent](https://github.com/RLinf/RPent) | 认知、工具、记忆、数据飞轮；原审计发现真机/数据控制仍需改造 | Apache-2.0；新 HEAD 已补核选定差异，非全路径复核 | 可保留为认知骨架，不能直接当完整 RL runtime |
| [RoboRSI](https://lab.noematrix.ai/blog/2-roborsi/) | 代码能力演化＋策略数据改进，是当前动机来源 | 结合此前固定源码审计；不同训练入口开放程度不一 | 学习能力演化机制；不把某个未实现入口扩大成整个项目无训练 |
| [Show-Harness](https://github.com/showlab/Show-Harness) | 视觉语义小动作→真机；AgileX/Franka、GUMI、纠正、数据、SFT | Apache-2.0 代码；HF 数据和 LoRA；部分底座另有条款 | **新增优先：纠正动作编译与数据接口** |
| [VoLoAgent](https://github.com/NVlabs/VoLoAgent) | VLA 调度、VLM 监测、感知/抓取/放置工具；真实 FR3 实验 | Apache-2.0 主仓库，感知/运动依赖另核验 | **新增独立辅助执行基线**；不是在线 RL |
| [Strands Robots](https://github.com/strands-labs/robots) | 工具代理、机器人统一接口、RTC、记录、训练编排、mesh | Apache-2.0；完整软件面较广 | **工程挑战者**；Piper sim-only、RL 为仿真路径 |
| [DimOS](https://github.com/dimensionalOS/dimos) | 传感器流、代理、MCP、运动/控制协调、Piper beta | Apache-2.0；beta | 若要替换硬件运行层，可列入短名单 |
| [OpenRAL](https://github.com/OpenRAL/openral) | 类型化技能、HAL、世界状态、独立安全层、追踪 | Apache-2.0 社区层＋Pro 能力边界 | 接口设计参考；内核关键路径尚未完整审计 |
| [RoboClaw](https://github.com/RoboClaw-Robotics/RoboClaw) | 正反技能循环、异常恢复、代理数据采集 | 公开主仓库；完整 VLA wheel 需请求，许可证需继续核验 | 场景循环重要参考；完整复现有额外门槛 |
| [REAL](https://github.com/InternRobotics/REAL) | MCP 高层具身代理，经 SFT＋GSPO；真机部署实验 | 代码/环境与数据线索公开；全依赖许可未逐项核验 | 高层工具选择 RL；不同于本项目低层 policy 在线 RL |
| [HoloAgent](https://github.com/HorizonRobotics/HoloAgent) | 空间记忆、移动操作、探索和工具调用 | Apache-2.0；公开代码存在，部分发布仍在计划中 | 移动操作后续参考，首个单臂任务优势不明确 |
| [HARBOR](https://github.com/supersglzc/harbor-rl) | 自动搭仿真/任务/reward/训练并检查产物 | Apache-2.0；Claude Code 插件 | 训练开发助手；不是实时真机值守系统 |
| [SHAPER](https://arxiv.org/html/2608.11350v2) | 冻结模型，演化技能与上下文构造代码 | 论文/提示可读；本轮未核验官方完整代码发布 | 代码能力演化候选门禁参考 |
| [CaP-X](https://github.com/capgym/cap-x) | 程序化机器人任务、代码代理、代码生成 RL | MIT；CaPGym/CaPAgent/CaPRL | 代码测试/学习研究，非真机 action RL 基座 |
| [AgentSpec（2026）](https://agentspec-embodied.github.io/) | 模块化具身代理组合与兼容性研究 | 作者代码公开；许可未核验 | 强调模块组合验证，非真机运动运行层 |
| [EmbodiSkill](https://github.com/air-embodied-brain/EmbodiSkill) | 技能感知反思与演化 | MIT；小型研究仓库 | 方法参考，未找到本项目真机闭环证据 |
| [Gemini Robotics 2 / ER2](https://deepmind.google/blog/gemini-robotics-2-brings-whole-body-intelligence-to-robots/) | 头部公司的具身模型、推理与部署系统 | API/合作伙伴/早期访问层次不同 | 可作观察模型竞品，非全套可改造开源基线 |
| [HiRobot](https://www.physicalintelligence.company/download/hirobot.pdf) | VLM 高层推理＋低层策略的层级控制 | 论文为主，本轮未核验完整 runtime 开放 | 原理参考，不能因 PI 品牌假定在线学习开放 |

已在原调研中的 ENPIRE、Zetta 和复位学习方法由总报告融合；Open-RAIL、RLinf、LeRobot 在本轮其他专项材料中检查，本文不重复下结论。

## 5. Show-Harness：最值得落实的新发现

### 5.1 为什么与本项目更接近

2026 年 9 月的 Show-Harness 来自 NUS Show Lab。它将末端平移、旋转、夹取、释放等小步语义动作交给机器人解释器，模型可用视觉反馈反复修正，公开实验包括 AgileX 双 6 自由度平台。这种方式给“GPT6 不只观察，还能代替人修正动作”提供了比抽象工具调用更具体的实现。论文有真实抓放任务实验，但没有证明同一策略的真机在线 RL 或长期无人运行。[论文](https://arxiv.org/html/2609.10522v1)

HF 数据页提供真实与仿真示范，真实部分为 164 条 episode、7,933 个训练对。模型页提供六个 LoRA 适配器，覆盖不同小型 VLM；它们是替代观察/控制模型的实验资产，不需要本项目放弃 GPT6。模型页整体许可标签不能覆盖所有底座：Gemma 适配器仍须遵守相应底座条款。[数据页](https://huggingface.co/datasets/showlab/Show-Harness-Data)、[模型页](https://huggingface.co/showlab/Show-Harness-VLMs)

### 5.2 源码读到的能力和缺口

| 检查点 | 本轮观察 | 对本项目的影响 |
|---|---|---|
| 动作解释 | Piper 控制器支持 Cartesian 语义到 joint stream；校验 FK 与反馈，超出运动能力会限制目标，检测设定值与反馈偏离 | 是可研究的落地模块；必须记录原提议、编译命令、实际执行三层 |
| 机械臂适配 | 文档支持选择单臂，但依赖 ROS/cobot_magic/Piper 工作空间 | 用户的“松灵”具体型号仍需确认；不能直接宣称开箱即用 |
| 默认启动动作 | 参考启动流程涉及双臂夹爪/初始位姿，runner 开始还会发 RELEASE | 与“另一臂不参与”、中途持物接管都可能冲突；接入只允许显式初始化契约 |
| DAgger | 默认实现是键盘意图覆盖，消费时丢弃旧的语义 chunk | 可将意图生产者换成 Harness；这不是已实现全自动 DAgger＋RL |
| 抢占 | preemption 主要丢弃在途模型结果 | 仍须 Gateway 对物理执行停止做确认 |
| 成功信号 | 真机 runner 把最终 DONE 当任务完成 | 不能直接作为本项目独立 success/reward 真值 |
| GUMI | 人和代理可走相同操作 API，记录图像/动作；Pause 不能撤回已经发送的动作 | 有利于统一纠正来源；不能绕过 Gateway 直接开放驱动接口 |
| 连续运行 | 小步控制/分段开环；本轮未看到本项目所需 C/E/D 对齐训练 | 可复用局部动作编译，不复用其数据就假定 RL 正确 |

源码：[Piper 控制器](https://raw.githubusercontent.com/showlab/Show-Harness/137d571/interpreters/piper_atomic_controller.py)、[Piper 接入](https://raw.githubusercontent.com/showlab/Show-Harness/137d571/docs/piper.md)、[DAgger 插件](https://raw.githubusercontent.com/showlab/Show-Harness/137d571/plugins/dagger/plugin.py)、[抢占实现](https://raw.githubusercontent.com/showlab/Show-Harness/137d571/core/runners/preemption.py)、[真机 runner](https://raw.githubusercontent.com/showlab/Show-Harness/137d571/core/runners/real.py)、[GUMI](https://raw.githubusercontent.com/showlab/Show-Harness/137d571/gumi/README.md)。

还有一个不容易从摘要看出的兼容问题：部分 co-trained 模型采用 Franka 的图像方向约定，AgileX 部署在执行边界交换前后方向。由此必须保存原始模型输出及明确的坐标变换版本；不能将模型语义与机器人坐标混为一谈。[适配说明](https://github.com/showlab/Show-Harness/blob/main/docs/finetuned.md)

### 5.3 应吸收什么，不应强行改变什么

建议新增 Harness 纠正执行的两种等价入口：一是小步语义动作，经标定的解释器转成 VLA 动作域；二是已经有可靠几何/控制支持的连续动作或短轨迹。两种入口最终都服从同一所有权、接管与数据规则。**不把正在训练的连续 VLA policy 强行离散化成语义 token policy。** Show-Harness 的价值是给 GPT6 的纠正提供可执行工具，不是规定 RL 的动作表达。

GPT6 每次看新图后产生的新语义动作，是新的反馈决策。多个这种决策实际执行后，可以作为真实轨迹和分时刻监督数据；不能事后拼成一条“在最早观测时已经知道后续所有修正”的 BC chunk。只有同一合法决策时刻产生、条件一致的动作提议，才能作为该时刻的监督候选；TD 则仍须使用实际执行与真实下一状态。

## 6. VoLoAgent：有价值的外部对照，不能直接变成学习基座

VoLoAgent 在 VLA 外加入 VLM 子目标、进展监测、抓放与几何工具。公开项目支持不依赖 GT 的 VLM 失败监测；仓库也有使用仿真 GT 的旧实验路径，不能据此说整个方案都依赖真值。真实 FR3 实验是 14 个任务、每方法每任务 3 次，即每方法 42 次。完整系统报告 42.9%，基础 π0.5 为 14.3%；但去掉 VLA 的变体为 45.2%、只保留 VLA 工具的变体为 40.5%，区间较宽。证据支持“代理/工具能改善某些部署”，不足以证明完整组合普遍优于其他组件配置。[论文](https://arxiv.org/html/2606.07723v1)

其公开代码是可用的代理中间层，但有几项对本项目很关键的差别：proxy 收到观测后等待策略处理，`asyncio.to_thread` 主要保持服务响应，不能自动推导出独立高频物理观察；若客户端不提供真实步数，代码可用推理次数估算步数；示例 hold chunk 也带有特定机器人维度。客户端 flush 标志不等于设备停止回执。这些差异都要求重接 Gateway 和实际执行日志，而不是把返回数组直接放入 replay。[固定版本 proxy](https://raw.githubusercontent.com/NVlabs/VoLoAgent/b4e6230/vlm_orchestrator/proxy.py)

仓库还提醒部分环境的逐步分数不能按预期提供；本项目不能照搬成稠密 reward。项目记录与转换工具值得参考，但没有看到其默认训练闭环已满足当前 BC＋在线真机 RL。[仓库及使用说明](https://github.com/NVlabs/VoLoAgent)

建议将其作为“冻结 policy＋代理辅助”的对照：相同任务、传感器、动作工具、调用预算，比较 RPent 风格认知调度与 VoLoAgent 风格监测/恢复。这样能判断复杂 Harness 是否带来收益，同时将 policy 学习收益单独计算。跨本体时，机器人维度和 hold/stop 等具体行为应由 capability descriptor 与 adapter 声明，禁止藏在认知层的固定数组里。

## 7. 工程底座候选：Strands、DimOS、OpenRAL

### 7.1 Strands Robots：不能因为 AWS 就跳过硬件和 RL 路径审核

Strands Robots 来自 Amazon/Strands 开源生态，提供统一机器人/策略接口、记录、训练编排与远端调用。其 recorder、部署、RTC 和真实设备任务管理是比通用 LLM 框架更接近本项目的工程资产。官方 Amazon 博文也介绍了从 HF 数据到机器人执行的路径。[官方介绍](https://huggingface.co/blog/amazon/strands-lerobot-hub-to-hardware)、[架构](https://strands-labs.github.io/robots/architecture/)

但硬件目录明确区分 real/sim：例如 **Piper 当前为 sim-only**。这只是部署成本，不能据此否定通用框架；同时也不能从七十余机器人注册项推导出七十余硬件已联调。其 PPO/FastSAC 文档描述从 SimEnv 训练，RL 路径不使用示范 dataset_root；这与 VLA 表征＋示范保留＋BC＋真机在线 RL 有明显距离，是比单一硬件适配更核心的融合缺口。[机械臂目录](https://strands-labs.github.io/robots/robots/arms/)、[RL 文档](https://strands-labs.github.io/robots/training/rl/)

`run_policy` 的一个有用实践是：代理说“已执行若干 episode”不算完成，必须读取实际记录与 episode 数核对。此原则适用于本项目对纠正次数、恢复完成、训练样本数的所有承诺。[固定版本执行代码](https://raw.githubusercontent.com/strands-labs/robots/4d02031/strands_robots/tools/run_policy.py)

默认物理动作 HITL 门禁是可配置的，不能仅凭默认需要确认而直接淘汰；本项目可配置限定权限的自动执行，但本地 stop 必须独立可用。[命令门禁](https://strands-labs.github.io/robots/security/commands/)、[配置](https://strands-labs.github.io/robots/reference/configuration/)

必须同时看到其不成熟处：本轮最新提交披露并修复了一批 Isaac 后端之前“返回成功但没有真正构建/驱动物理实体”的问题。这不等于所有功能都不可信，但说明复杂文档、活跃提交和测试数量不能替代真实执行产物。接入时应验证具体路径，而不是全库宣传范围。[对应修复提交](https://github.com/strands-labs/robots/commit/4d02031)

### 7.2 DimOS：Piper 运行层有潜力，迁移要按必要性决定

DimOS 提供模块化传感器/代理/控制流和 Piper beta，公开关注控制所有权、统一轨迹任务和抢占。对于尚没有可靠硬件运行层的团队，其价值可能高于重新写全部中间件。但本项目已经有遥操作和策略部署，迁移成本不应忽略。[仓库](https://github.com/dimensionalOS/dimos)、[发布记录](https://github.com/dimensionalOS/dimos/releases)

官方 manipulation 文档中，若干示例默认 mock；局部 IK 的关节限制不等于全场景避障；部分 Cartesian 路径还没有对应 MCP/skill 接口。讨论区中的“Closed-Loop Robot Agent Harness”“Replayable Mission Trace”等是进一步方向，不能将 Ideas 视为已发布实现。[操控文档](https://github.com/dimensionalOS/dimos/blob/main/docs/capabilities/manipulation/index.md)、[讨论区](https://github.com/dimensionalOS/dimos/discussions)

建议把它列为 **Gateway 下方运行层的候选**，先单独验证用户设备的状态读取、单臂命令、停止、恢复、日志，再决定是否替换现有 SDK。即使选用 DimOS，本项目的异步 C/E/D、RL 数据资格、reward 版本和 learner 发布契约仍需实现。

### 7.3 OpenRAL：最应该尊重其自身公开的验证边界

OpenRAL 描述了 HAL、类型化技能、世界状态、reasoner、C++ 安全层和追踪等结构，社区层 Apache-2.0，另有 Pro 能力边界。其机器人表中的 ALOHA 硬件对应 Interbotix，`aloha_agilex` 则是 RoboTwin2 的评测仿真路径。[机器人支持表](https://docs.openral.com/reference/robots/)

更重要的是，详细路线图明确说若干真实适配器已写但尚未接触对应物理设备；已验证的 Galaxea 路径也有具体动作和人工 HIL 测试范围。OpenArm 的只读 CAN 检查与实际 command→motion gate 是分开的。技能 provenance 签名和一些 replan 功能仍有待实现。应按这些细节评估，而不是把表格中的“支持”当作真机验收。[官方路线图](https://docs.openral.com/roadmap/)

按通用性要求，OpenRAL 应保留在候选中，重点验证类型化命令、单独运行的 watchdog、能力清单和执行追踪是否真正组成可替换且可维护的实现。其未验证路径和 RL 数据缺口目前使整套迁移的收益仍不确定。C++ 或“安全内核”的命名不等于本项目已经获得物理安全保证。

## 8. 其余高质量方向如何参与，而不是被误选

### 8.1 RoboClaw：与正反循环动机高度相关，但不要遗漏人工和发布门槛

RoboClaw 用正向/逆向技能组织连续收集，并通过代理处理恢复与调用工具。论文降低了人工时间与介入量，但仍包含初始示范、人类兜底，且技能池不等于当前同一共享参数 policy。完整 VLA 部件的发布存在请求获取路径，公开硬件主要不是本项目松灵平台。它适合作为循环组织和恢复的比较项，不能当成已经证明零人工且可直接复现的替代品。[论文](https://arxiv.org/html/2603.11558v1)、[发布说明](https://github.com/RoboClaw-Robotics/RoboClaw)

### 8.2 REAL：高层代理也用 RL，但学习对象不同

REAL 来自 InternRobotics/上海人工智能实验室等团队，使用 MCP 工具，高层视觉语言代理先 SFT 再 GSPO。论文的训练环境是 InternUtopia，reward 可利用仿真 world graph；真机 60 个 episode 是部署评估，不是 60 次在线真机低层 RL。模型不看 oracle perception 与训练 reward 使用仿真真值并不矛盾。其 ask 功能面向交互任务，也不等于不需现场人员。[论文](https://arxiv.org/html/2607.13653v1)、[仓库](https://github.com/InternRobotics/REAL)

对于后续移动操作，REAL 的高层工具调用训练值得考虑；当前单臂正反向动作学习不应为了名称中有 RL 而换成它。

### 8.3 HARBOR、SHAPER、CaP-X：分别服务训练开发、上下文演化、代码能力

HARBOR 来自 TU Darmstadt、Honda Research、Columbia 等合作，按可检查阶段自动搭仿真、任务、reward 和训练。公开实现是 Claude Code 插件，适合辅助开发与离线验证；不能据其 RL 工程自动化能力推导出它能实时替代真机观察员。其 reward 搜索也不应直接覆盖线上固定任务评分契约。[论文](https://arxiv.org/html/2606.08610v1)、[开源实现](https://github.com/supersglzc/harbor-rl)

SHAPER 来自东北大学、微软亚洲研究院等团队，冻结模型后演化技能文本与有限的上下文构造代码。它把执行器保持在固定边界内，并通过候选验证再提升；实验主要为仿真基准。本轮未核实其完整公开代码。对本项目有价值的是“代码/记忆变更也要有独立验证”，不是又叠加一个实时机器人控制器。[论文 v2](https://arxiv.org/html/2608.11350v2)、[微软研究院页面](https://www.microsoft.com/en-us/research/publication/self-evolving-embodied-agents-via-skill-harness-evolution/)

CaP-X 提供代码驱动任务基准、代码代理和代码生成 RL；它帮助检查生成代码是否实际可用，但 CaPRL 优化的是代码生成模型，不能和低层动作 critic 的真机 RL 混为一类。[仓库](https://github.com/capgym/cap-x)

AgentSpec 的 2026 具身代理组合研究提醒：强模块的简单叠加不保证整体更强，训练与部署的 scaffold 不同也可能产生问题。需注意它与 2025 年同名 runtime enforcement 项目不是同一工作。[2026 项目](https://agentspec-embodied.github.io/)、[2025 同名项目](https://github.com/haoyuwang99/AgentSpec)

### 8.4 头部公司与新平台

Google Robotics 2/ER2 展示了头部系统能力，但不同模型的开放方式为 API、合作或早期访问，不能假定能下载完整参数与运行/训练栈。HoloAgent 公开代码值得跟进，但部分 roadmap 是未来发布，当前不能拿未来版本的能力计入可行性。Reachy Mini 的代理应用生态能说明工具和代码生成的落地趋势，不过其桌面机器人任务不是当前机械臂接触操作与 RL 的直接证据。[Google 官方发布](https://deepmind.google/blog/gemini-robotics-2-brings-whole-body-intelligence-to-robots/)、[HoloAgent](https://github.com/HorizonRobotics/HoloAgent)、[HF 官方介绍](https://huggingface.co/blog/clem/reachymini-appstore)

## 9. 从整体框架重新比较兼容性

| 兼容问题 | RPent | OpenETA | Show-Harness | VoLoAgent | Strands Robots | DimOS/OpenRAL |
|---|---|---|---|---|---|---|
| GPT 主观察／纠正 | planner／toolkit 可改造 | 可替换 planner；具体 provider 须测 | API VLM 动作接口 | VLM 中间层 | Agent provider 与工具 | 模型／代理接口，能力另验 |
| 本体通用边界 | 机器人注册与工具桥 | sim／real 观测和工具契约 | 语义词汇＋本体解释器 | proxy 仍有特定动作／hold 假设 | 设备／policy 注册，real/sim 分明 | 数据流协调／类型化 HAL |
| 共享 θ＋BC/RL | 外接／改造 learner | policy adapter 与 learner 仍需补 | 默认语义 SFT，需外接 | 未见完整学习回路 | 仿真 RL 与本项目不同 | 主要运行层，需外接 |
| 观察与实体接管 | 长工具锁需独立观察；取消不等于停止 | 逐动作新观察不等于持续观察；timeout须核实体 | 丢旧模型结果不等于停止 | flush 不等于停止 | RTC/stop 须逐入口验证 | 控制机制须核设备语义 |
| 纠正回流 | 飞轮不能代替全事实 replay | 日志／候选经验不能代替逐步 TD | GUMI 需真实执行账本 | 日志须接 causal replay | recorder／mixer需分流标签 | 不默认已有学习 buffer |
| 成功与奖励 | 冻结判据／证据 | 可信结果契约仍需本任务评分 | 不接受 DONE 自证 | 不照搬仿真分数 | evaluator 需校准 | 类型／事件不等于语义正确 |
| 主要改造成本 | 观察／控制／学习桥 | 持续观察／控制／policy桥 | 解释器接唯一网关 | 感知／规划／服务 | 平台入口与学习目标改造 | 中间件与学习层集成 |

本表是设计适配判断，不是跑分。最有意义的组合是 **一个认知调度器＋若干无独立控制权的工具插件＋一个 Gateway＋一个数据入口＋一个 learner**。不应并排运行 RPent、Show、VoLoAgent 四套各自抢占机器人和写 buffer 的主循环。

通用性重排后的框架选择顺序是：①跨模型/策略/本体的接口与能力声明；②异步执行、停止、所有权、观测时钟的明确语义；③成功/失败/纠正数据回流及在线 learner 可插拔性；④关键代码与依赖完整度、可测试性和维护；⑤首个硬件的移植成本。上述第⑤项不能反过来主导前四项。研究框架模块较小便于复用，通用平台接口较完整但迁移较重，应按需要修改的关键路径比较，而不是按机器人品牌匹配程度比较。

## 10. 对主方案应作的具体增补

1. **将“纠正动作落地”从抽象能力细化为可替换插件。** 优先研究 Show-Harness 语义动作解释器，保留几何/连续动作入口。插件输入包括最新观测、goal、相机/机器人坐标版本、有效 epoch 与可用动作范围；输出是提议，物理执行权仍归 Gateway。
2. **明确三种不同记录。** 原始语义意图/连续动作提议、编译后合法命令、实际发出且有反馈的动作分开保留。当解释器位于 learner 动作接口之前，TD 应记录转换后的接口动作；若固定投影明确属于环境内部动力学，Q 可以使用进入环境的投影前接口动作。两种边界都合法，但不能混用；以技术接口 §2.1 的动作定义为准。
3. **保留严格的时间条件。** 在途 GPT 输出到达时若观测/goal/控制 epoch 已过期，应作废或重新推理。模型请求取消与机器人停止是两条链；先确认执行归属和停止状态，再运行纠正。
4. **纠正示范并不要求整条任务成功。** 局部高质量动作可进入有来源与资格的 BC 数据；实际失败片段也可进入合法 RL replay。未执行建议可以长期保存，但不能虚构该动作的真实后果；有模型预测后果时另设合成数据通道并标注模型/不确定性。
5. **将开始/结束/复位动作也纳入控制和数据契约。** 不能复用默认 RELEASE、双臂 home 等初始化就无条件运动。正反向目标切换时，同一 policy 在相应目标下继续学习，Harness 恢复不自动成为第三个无需验证的 reset 入口。
6. **成功判定不接受行动方的 DONE 自证。** 可以仍由 GPT6 评分，但评分输入、固定任务规则、证据和版本需独立管理；对行动文本中的“成功”不直接采信。语义完成、物体位置稳定、夹爪释放等证据按任务定义核验。
7. **新增系统对照和组件消融。** 在同等任务/调用/执行预算下比较：policy 独立、RPent 风格辅助、VoLoAgent 风格辅助、加入 Show 纠正工具、再加入纠正 BC/RL。检查系统收益是否转化为 policy 独立能力，避免工具替代遮蔽学习失败。
8. **代码演化先在开发通道。** 借鉴 SHAPER/HARBOR/CaP-X 的产物测试与候选晋升，但线上评分规则、控制所有权和 buffer 构造不得被生成代码直接改写。先支持有限、可验证的工具组合，再逐步开放代码能力。

## 11. 机构、传播与成熟度的审核口径

机构可信度影响我们愿意投入复现成本的优先级，不替代源码、设备和任务验证。NVIDIA、Amazon、微软/Google/PI、NUS、上海人工智能实验室等均有较强研究或工程背景，但各候选的开放范围与本项目适配差别很大。

以下为本轮访问页面的近似快照；动态页面可能在同一天已变化。GitHub stars/forks 是关注/派生仓库数，不是复现次数；HF 下载是平台统计，不是成功部署数；HF paper votes 不是引用量。

| 项目 | 本轮可核查传播/维护信号 | 应如何理解 |
|---|---|---|
| Strands Robots | 仓库访问时约 163 stars、37 forks，随后提交页已显示 38 forks；约 3,061 commits | 活跃，但 commit 数可含自动化工作；当前具体后端仍有大量修复 |
| DimOS | 仓库页面约 4.6k stars、813 forks；beta 标识 | 社区更大，有真实硬件工程价值，仍非本项目闭环复现证据 |
| Show-Harness | Sep 2026 新发布；HF 数据页约 5,779 月下载，模型页下载项未给数值 | 有可用资产与早期关注，尚缺长周期维护证据 |
| VoLoAgent | 初始公开仓库约 7 forks、单次公开 release commit | NVIDIA 原始实现可读；不要将公开提交少等同于方法弱，也不能推断成熟部署 |
| HARBOR | 仓库访问约 3 commits、1 fork | 新研究实现；主用途是训练工程，不是机器人实时控制 |
| RPent | 旧审计有固定版本，本次 HEAD 已变化 | 本轮补读选定差异；旧审计不能无条件覆盖新能力 |

上述数量来源分别为各官方仓库与 HF 页。论文普遍发表于 2026，本轮没有获得统一口径的可靠引用统计，故未将“未知”填成 0，也没有伪造引用排名。比较时更应关注公开真机实验的任务、试验次数、失败处理和 artifact 可用性。

## 12. 尚未消除的不确定性

- 用户松灵机械臂具体型号、固件、控制模式、ROS/SDK 和可用停止反馈未确定。Show/Piper、DimOS/Piper 的适配优势是条件性的。
- 关键新仓库取得固定完整提交标识并在线阅读关键源码，尚未保存完整固定源码树并运行。OpenRAL/DimOS 等没有完成全路径代码审计。
- 真实“持续观察＋抢占确认＋async chunk 数据对齐＋BC/RL”在候选中没有被本轮端到端验证。公开演示不能替代本项目验收。
- GPT6 在用户部署条件下的延迟、图像同步、观察/纠正质量、调用预算需要实测；模型强弱不能消除通讯和物理反馈缺口。
- 机构 PR 和论文方法与可下载实现可能不完全一致。RoboClaw 部件获取、Show ROS 工作空间、各模型权重许可仍需实现前逐项核验。
- RPent 当前完整提交为 `6ee706935d28646828f70372ef0099c769cfe0c2`。根审已补读所选差异与文档，主要是 RoboCasa/RoboTwin、探索／记忆／测试扩展；未取得观察锁、物理停止和本项目学习链已通过的证据。这个结论不冒充全库审计；接入时仍须验证 T31–T38，详见配套总报告。

最终选择应由项目级最小验证决定：同一设备、同一目标、同一执行与数据契约，先证明观察—纠正—回流—独立 policy 改善这一链条，再扩展自动恢复范围和无人运行时长。


## 13. 补漏研究：名称归并、恢复与工程资产

### 13.1 OpenETA：新增通用骨架对照

详见 [固定源码补核](../reviews/R05/openeta_source_check.md)。本项只升级为值得同预算比较的候选，没有宣称优于 RPent 或已经满足本项目。学习算法、动作解释工具和 Harness 骨架分别选；无在线 RL 不是单独淘汰它的理由。

固定提交 `7d4a0a1522ba8ebbd362bde880bad81d2a98f15e` 下，Host 在调用模型前检查新观测义务并可强制派 observe，有工具失败、模型校验尝试及候选晋级记录。但 episode 是逐工具闭环；只读 batch 的实际路径仍逐项调用。handler 取消是放弃等待，线程可能继续；关闭会话不是实体 stop_ack。rollout 采用尽力保存，`logger/replay.py` 是时间线回放，不是 RL buffer。以上均须接统一 Gateway、独立观察和事实账本；不能把已有契约误当所需实现全已完成。[固定 Planner](https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/planner.py)、[工具执行](https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py)

OpenAI-compatible 多图后端是 GPT 接入基础，实际模型参数和输出还须预检。主仓 Apache-2.0 不覆盖外部依赖；README 的 openpi 等 policy adapters 尚未全部适配。论文区分全栈与轻量配置，且明确未得到通过全部门禁的自演化提升。因此采纳的是骨架候选资格，不是其训练能力或成功率承诺。[论文 §5–8](https://arxiv.org/html/2608.03924v1)、[固定 README](https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/README.md)

### 13.2 邻近方案与发布范围

| 候选 | 已核资料和定位 | 与本项目的关系 |
|---|---|---|
| Harness VLA | 新版论文的官方代码指向 RPent，详见 [名称与资产核查](../reviews/R05/harness_neighbor_check.md) | 属于已有骨架的论文身份，不重复计数；冻结 VLA 的辅助增益不等于参数在线更新 |
| HALTER，KIT／UNC，2026-09 | [论文](https://arxiv.org/html/2609.19413v1) 用场景图串起评分、原子恢复技能及核验；[仓库](https://github.com/YY-GX/HALTER) 当前仅 README，发布中 | 学习分步恢复与核验；已有恢复技能需准备，仍有人工介入，不替代共享反向 RL，不作可用开源底座 |
| Guava | 高层工具调用模型的 SFT／GRPO；[官方项目](https://guava-harness.github.io/)代码仍待发布 | 真机部署不是本项目在线动作 RL；目前保留方法参考 |
| Zero2Skill | [官方仓库](https://github.com/open-gigaai/Zero2Skill) Apache-2.0，固定提交 `6ea772566939d9c235dda771fe14f5fafa2bc6ad`；持久纠正与采集／整理工具 | 加入纠正记忆与数据整理模块候选，不替换整个骨架；具体源码边界见下文及[专项补核](../reviews/R05/harness_neighbor_check.md) |
| Nautilus | [项目页](https://yufengjin.github.io/nautilus/) 主 Harness 标 Coming Soon；采集入口链接 [role-ros2](https://github.com/YufengJin/role-ros2) | 合同验证、适配与隔离运行的工程参考；采集子库不代表全 Harness 已发布 |

上述为论文／页面及选定代码检查，没有安装运行；移动分支链接记录的是访问时状态。HALTER 的主任务100个episode仍有25次人工介入、原子技能另需示范，不能把“无需每任务成功分类器”读成无准备成本。[根审原始材料记录](../reviews/R05/root_neighbor_check.md)

Zero2Skill 的公开 `prepare_training_set.py` 整理 ACT 风格 HDF5，不是 π0.5 训练器，也不要求本项目采用 ACT。可选 lenient 会接受未知视觉判定，规则改变后保留旧 manifest、只给新样本用新规则；`action_shift` 的未来 qpos 标签不能直接冒充实际动作。外部 recorder、AnyGrasp 二进制／权重另备，IK 仍有本体几何常量。因此借鉴纠正持久化，但保留本项目未知评分、版本重审和真实动作契约，不原样搬入 learner。[固定整理脚本](https://github.com/open-gigaai/Zero2Skill/blob/6ea772566939d9c235dda771fe14f5fafa2bc6ad/grasp-tools/collect/prepare_training_set.py)
