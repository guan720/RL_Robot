# S1 Harness 广域补漏：从程序能力到独立 policy 的学习桥

调研日期：2026-09-23。范围为本次三轮研究的第一轮广域补漏；本文件不构成方案评审，不计连续五轮评审成绩。旧报告作为已有地图，新增候选与已有候选的证据升级分开记录。

已按本会话 AGENTS.md 读取科学家 START_HERE、ROLE、state/status、knowledge/INDEX、科研 SKILL 与研究流程；科学家知识库保持只读，未运行其更新流程。已读本轮任务契约、04 轮 Harness 扩展研究及总报告。实际工作为网页、论文章节、官方仓库说明、数据说明和 PR 的静态核查，未安装、训练、跑通软件或做真机实验。访问记录见 [harness_search_log.json](harness_search_log.json)；其中保留查询词及工具返回，未将检索摘要当作源码阅读。

## 1. 先总结已有地图，再枚举本轮问题

最终目标是同一个目标条件 VLA θ 在少示范、低成功率乃至零成功起点下，通过可靠 BC 加真实在线 RL，独立稳定完成任务。正反向 A↔B 服务同一目标条件策略；异步连续 chunk 的事实时钟和干预边界必须保留。GPT-6 的观察、纠正和程序积累是实现这一目标的手段。

旧地图已经涵盖 RoboRSI、RPent、OpenETA、Show-Harness、VoLoAgent、Strands、DimOS、OpenRAL、RoboClaw、REAL、HoloAgent、HARBOR、SHAPER、CaP-X、AgentSpec、EmbodiSkill、ER2、HiRobot、HALTER、Guava、Zero2Skill、Nautilus，以及 SOAR/AutoEval 等自动运行与复位路线。本轮不因再搜到这些名称就计作新增。PhyAgentOS 已在 04/reviews/R06 中浅筛，本轮属于升级核查。

| 功能层 | 已有认识与本轮新问题 | S1 枚举并访问的候选 |
|---|---|---|
| 认知、观察、任务分解 | 语言与代码能力能否产生本体可执行、可追溯的纠正动作？ | GPT-Policy、Agent as Policy、VLCP；StageGuard/ARMOR 的观察辅助 |
| 物理执行与连续运行 | 局部工具成功是否足以证明同一机械臂只有一个控制者？取消、队列、感知时间戳与数据回放是否有证据？ | RAI、dora、ROSClaw；PhyAgentOS 升级核查 |
| 自动纠正 | 改 prompt、改程序、改动作、训练参数分别发生在哪一层？ | SAGE、Harness-Zero、DGAC；GPT-Policy/AGP 教师动作 |
| 数据回流与参数学习 | 教师建议和实际执行的动作能否被区分？哪些数据进入 BC，哪些能够进入真实 RL？ | SAGE 的教师/学生损失划分；Harness-Zero 原生动作蒸馏；AGP 轨迹和标签 |
| 监控与评分 | “任务完成”的自述、监控器预测与独立真值是否混用？ | AGP 标签审计、StageGuard、ARMOR |
| 程序进化与知识持久化 | 获得新程序是否已经意味着学生 policy 学会了？ | RHO/HELIX、VLCP、AGP、Harness-Zero |
| 自动复位和长时间采集 | 任务成功、复位成功、救场成功与冻结策略成功率是否分别计量？ | SOAR、AutoEval 重核；AGP 的 reset 单列数据 |

本轮没有发现已经公开验证、可直接替代全部组件的完整方案。新增证据把两个缺口变得更具体：第一，程序/agent 教师转成学生参数已有可借鉴的学习机制，但具身 VLA 的动作与时序桥接仍需实现；第二，公开 Harness 和数据往往尚不提供可直接用于 TD 学习的独立物理真值与完整因果轨迹。这是对已访问候选的判断，不是对全领域的穷尽证明。

## 2. 新候选：学习桥与可执行教师

### N1. SAGE：最贴近“纠正可退出”的机制证据，机器人实现尚缺

**日期/机构/所读粒度。** 2026-09-01，FBK NLP、都灵大学；读取论文方法、消融和限制，以及作者仓库和 LICENSE。论文把教师调用限制于高不确定状态，训练时执行教师动作，并把这些动作蒸馏给学生；评估时不再查询教师。PPO actor 损失只用于学生动作，BC/AWBC 用于教师动作，价值学习可使用双方真实环境回报。消融显示仅执行教师动作而不做 BC 效果很差；AWBC 相对普通 BC **没有稳定优势**，不能把它描述成已解决错误教师过滤。实验主要是 FrozenLake、MiniGrid 等离散环境和初步 ALFWorld，不是机械臂 VLA。[论文方法与消融](https://arxiv.org/html/2609.01567v1)

**资产。** [作者仓库](https://github.com/giobin/SAGE) 实际可见仅一个提交及 LICENSE；[MIT 许可证](https://github.com/giobin/SAGE/blob/main/LICENSE) 已读。论文前文“代码可用”和后文计划发布的表述不能替代实际训练文件。未核到官方权重/数据，未确认社区独立复现；星数未记录。

**适合度与 S2 问题。** 作为 BC+RL 教师介入时的数据分流依据很合适，不能直接声称其 PPO 适用连续异步、离策略 VLA。S2 先核是否补发源码，再核 teacher mask、执行记录、BC 取样与价值目标；若仍只有许可证，保留方法证据，不列作可复用训练栈。

### N2. Harness-Zero：将强 Harness 的纠正变成学生原生动作

**日期/机构/所读粒度。** 2026-09-21，论文/HF 元数据指向北京大学团队；读取论文、官方 README、HF 模型卡。教师在训练时依靠更强 Harness 审阅学生原生动作，选择 PASS 或 REPLACE，接受后的动作进入执行与 SFT 数据；部署学生不依赖教师 Harness。教师内部推理/工具包装不是直接模仿目标。实验是软件工具任务，不能转述为机器人验证。[论文](https://arxiv.org/html/2609.24974v1)

**资产。** [官方仓库](https://github.com/metaevo-ai/harness-zero) 为 Apache-2.0，访问时 13 stars、3 forks、12 commits。README 给出 rollout→构建 SFT→训练流程，存在按成功回报过滤数据的步骤。公开 [AppWorld 模型卡](https://huggingface.co/metaevo-ai/ahd-9b-appworld) 为 Qwen3.5-9B 微调产物，Apache-2.0、Safetensors，访问时显示月下载 23；同页链接的其他任务权重未逐个核。未运行训练，未确认完整审阅轨迹均已发布。

**适合度与 S2 问题。** 可借鉴“教师返回学生动作接口能表示的纠正”及“教师退出后测学生”的设计；不能把 Bash SFT 等同于低层 action chunk 学习。S2 需核数据 mask、只保留成功轨迹导致的零成功瓶颈，以及修改动作后真实执行回执与监督条目的对应关系。

### N3. DGAC：动态模型生成纠正 chunk，尚不能视作无人评分闭环

**日期/机构/所读粒度。** 2026-06-19，Robot Self-Improvement via Human-Video Dynamics Models；访问论文引言、方法与限制，作者项目页本次直接打开失败，未据此声称读过其代码。机构线索涉及 ETH Zurich 等团队，完整单位与资产需 S2 再核。方法用人类视频训练的模型，结合机器人 rollout 适配与成功轨迹检索，生成/排序候选纠正 chunk，并训练机器人策略；论文有真实机器人结果，但限制节明确仍需人工标注 rollout 结局。[论文](https://arxiv.org/html/2606.21406v1)

**资产。** 本轮未核到可用官方完整代码、权重、数据或相应许可证，热度和独立复现未知；[作者项目入口](https://ethz-mrl.github.io/robot-self-improvement-website/) 保留作待重试线索。

**适合度与 S2 问题。** 相比只写技能程序，它确实触及纠正动作到 policy 更新。未执行的想象动作及其预测后继不能伪装成真实 TD transition；零成功时可检索成功参考从何而来、人工结局如何替换、生成动作是否需要真实执行验证，均未解决。适合作为动作纠正/模型辅助监督的分支，不是现成无人训练后端。

### N4. GPT-Policy：原生机器人动作教师候选，公开预览不等于开源训练栈

**日期/机构/所读粒度。** 仓库记录 2026-09-11 demo、09-16 论文与代码；实际访问 README 和论文，完整作者单位未核。模型冻结，利用示范、动作历史、当前观察等上下文调用结构化机器人动作接口，提供 ARX X5/YAM 适配。这里的“学会新任务”主要是上下文/工具控制，不是 VLA 参数更新。[论文](https://arxiv.org/html/2609.19138v1)

**资产。** [作者仓库](https://github.com/cheng-haha/GPT-Policy) 访问时 267 stars、4 forks、23 commits。README 明确 license pending，公开预览未授予通常的再分发/商业复用许可；私有提示、标定、demo 原始记录和完整评估史不随仓库提供，RoboDojo 仍列 TODO。未验证独立策略权重或可训练动作数据集；本轮未读具体驱动源码。

**适合度与 S2 问题。** 可作为 GPT-6 生成可执行纠正动作和上下文组织的参考。S2 应先核许可与资产，再读动作单位/坐标系/IK/时间戳、真正执行的轨迹记录。不能把冻结基础模型的成功率归为学生 θ 的 BC/RL 收益。

### N5. Agent as Policy（AGP）：有公开机器人运行记录，但标签须分级重核

**日期/机构/所读粒度。** 2026-09-11 首稿、09-14 v2，Notre Dame、UCSD、SDSU；实际访问论文、项目、仓库、HF 数据卡与 LABELS.md。冻结模型通过机器人工具与保存程序执行操作；保存的程序可成为后续教师/controller，但不是低层策略训练。[论文记录](https://arxiv.org/abs/2609.12541)；[项目方法](https://agent-as-policy-2026.github.io/)

**资产。** [官方代码](https://github.com/agent-as-policy-2026/agent-as-policy) 为 Apache-2.0，部分 i2rt 组件 MIT，访问时 14 stars、2 forks、8 commits。[官方 HF 数据](https://huggingface.co/datasets/Agent-as-Policy/agent-as-policy) 为 CC-BY-4.0，包含 162 条 scored trial、另列 27 次 reset，以及 30,130 条 agent event；23,657 次机器人请求中有 352 次无对应 transcript response。它是 agent/tool 运行资料，尚未证成统一频率、统一动作空间的 VLA 训练集。

**必须保留的证据冲突。** 项目页概括称成功按物理标准事后评分；实际 [LABELS.md](https://huggingface.co/datasets/Agent-as-Policy/agent-as-policy/blob/main/docs/LABELS.md) 允许 GPT-6 的 astra_self：162 条 scored trial 中 66 条属于此来源，其他 96 条具有不同外部来源，但多为单评者/静态图像；其中仅 10 条 operator_review 为更强独立复核。各模型的标签来源并不一致。说明文件还公开记录过正则误读带否定语气的任务结论，后经照片重判。不能因此断言数据不可用，但不能把所有标签叫作独立物理真值。

**适合度与 S2 问题。** 很适合核查“代码教师→实际动作→训练数据”这条桥。S2 必须读数据字段、缺响应如何处理、成功标签来源、轨迹与图像时间绑定，先产生可复查的 BC 子集。只有真实执行且前后状态对齐的片段才有资格进入真实 RL replay；agent 自述不能直接当冻结评分器的 reward。

### N6. VLCP：程序内高频控制与模型外低频重规划，尚属仿真教师

**日期/机构/所读粒度。** 2026-08-17，多机构作者包括 University of Monastir、Cornell、CMU 等；读论文方法和限制。冻结 VLM 每隔控制块生成/修改控制函数，块内函数根据新数值状态闭环执行。实验依赖仿真器物体位姿与解析 Jacobian，不能称为仅视觉真机通用控制；主要评测每个 trial 重置技能库，不能把技能库存在本身当成已验证跨 episode 改进。[论文](https://arxiv.org/html/2608.16978v1)

**资产/适合度。** 本轮未核到官方完整代码、机器人权重或动作数据，代码许可和复现未知；论文样例代码不是可部署软件包。用于程序教师和低频/高频接口的设计参考。S2 如找到源码，再核特权观察、函数资源边界与实际 action 数据记录，不优先承担真实 VLA 学习闭环。

## 3. 新候选：运行时、监控与程序进化

### N7. RAI：可复用 ROS2 agent 工程，低层学习链尚未建立

RobotecAI 的 [官方仓库](https://github.com/RobotecAI/rai) 与 [文档](https://robotecai.github.io/rai/) 已读；README 引用 2025 年论文。提供多 agent、感知/机器人工具、ROS2 接口和基于本体文档/URDF 的身份配置。rai_finetune 面向 LLM 能力，不能据名称视作 VLA BC+RL。Apache-2.0；访问时 592 stars、76 forks、481 commits；未核到本任务可直接用的低层权重/训练数据，未运行。实际访问仍开放的 [timestamped messages PR #645](https://github.com/RobotecAI/rai/pull/645)，不把提议当已合并功能。

**S2。** 适合核通用本体/工具适配与感知时间戳，不替代已有 learner。需固定 release/commit 读取消、急停、消息对齐与动作回执；先查与 RPent/OpenETA 已有接口的重叠成本。

### N8. dora：数据流基础设施，记录/回放语义需逐项验证

[dora 官方仓库](https://github.com/dora-rs/dora) 实际 README 与 PR 已读；dora-rs 开源组织，Apache-2.0，访问时约 4.0k stars、444 forks、5,929 commits。支持多语言节点、分布式数据流、记录和回放；这些能力不自动等于 RL 的真实因果 replay。没有独立 policy 权重可评，不需把基础设施下载量当机器人学习复现。

[PR #3466](https://github.com/dora-rs/dora/pull/3466) 在访问时仍 Open，2026-09-09 提出接收方未完整拿到 full-speed replay 时应报错；它是当前工程风险线索，不是我们复现出的 bug，也不能当已修复。评论中的自动化 Claude review 不是独立人工复现。

**S2。** 固定版本核消息顺序、丢弃/背压、取消、退出状态和回放完整性。当前 dora README 与 PhyAgentOS 所固定的 dora CLI 0.4.1/dora-message 0.7.0 不同，不能以最新文档代替实际依赖语义，更不能无验证升级。

### N9. ROSClaw（ros-claw/rosclaw）：把物理执行凭据做成显式对象，但仍是 alpha

实际读 [仓库](https://github.com/ros-claw/rosclaw)、[daemon 文档](https://github.com/ros-claw/rosclaw/blob/main/docs/ROSCLAWD.md)、[架构](https://github.com/ros-claw/rosclaw/blob/main/ARCHITECTURE.md)。维护方 ROSClaw Team；与 rosclaw 组织及 PlaiPin 同名项目区分。其设计通过本地 daemon 分隔 agent 与物理体，暴露 body、permit、lease、feedback、receipt 及记忆/练习接口。MIT，访问时 203 stars、32 forks；文档定位 experimental alpha，一般化取消/抢占与真实硬件验收仍有后续工作。可选 RL 依赖或 roadmap 不证明已交付 VLA learner。

**S2。** 合同层值得研究，尤其控制权和执行凭据；必须读 daemon 到驱动的可达路径，确认“声明 lease”是否真覆盖所有工具与停止路径。代码公开但无低层策略权重/训练数据或独立复现被本轮验证。不要直接替换已实现组件。

### N10. StageGuard：阶段监控蒸馏，而非动作策略蒸馏

2026-09-17，Huawei Noah、UBC、Toronto、McGill；实际读 [论文](https://arxiv.org/html/2609.20791v1) 方法/实验。大模型教师训练小模型产生 continue/advance/skip，属于任务监控参数更新。底层为规划器或 π0.5；论文真机策略仍有每子任务数十条示范，不能转述成零示范自主改进。论文为 CC-BY-NC-SA-4.0；未核到官方机器人代码/权重/数据，具体代码许可、热度、独立复现未知。同名睡眠分期仓库已排除。

**S2。** 作为评分/阶段监督辅助，核标注来源、时序、误跳阶段和校准；本任务 GPT-6 主观察约束不因此自动更换。监控器变强不能代替独立策略变强。

### N11. ARMOR：机器人失败识别与解释，训练对象仍是监控模型

2026-02-12 预印本，UT Austin、Amazon Robotics、CMU；访问 [论文](https://arxiv.org/html/2602.12405v1) 与 [作者项目](https://sites.google.com/utexas.edu/armor)，机构发表页作为发现线索。结合二分类失败检测与生成解释，利用不同粒度的人工标注及自我精炼；“online imitation”在此不能自动解释成真实机器人 RL 更新。论文提到后续开放，项目未读到可用官方发布入口；代码、权重、数据、许可证与社区复现本轮均未确认。

**S2。** 可用于监控器候选池与失败类别定义；需核错误分布、帧/事件对齐和评分器冻结版本。多次生成的一致性是模型信号，不是物理真值。

### N12. RHO / HELIX：让代码 agent 优化控制程序，产物未必是神经策略

2026-06-15，UC Berkeley、AMD、Embodied Science；实际读 [RHO 论文](https://arxiv.org/html/2606.16458v1)、[HELIX 仓库](https://github.com/KE7/HELIX)。将机器人控制仓库作为可进化对象：隔离工作树、程序修改、评估与选择。Robosuite 的控制程序可在评估时冻结；另一些 RAI 实验优化的是仍有模型参与的运行时 Harness，二者不能混称“无模型独立 policy”。HELIX BSD-3-Clause，访问时 279 commits、4 forks，stars 未记录；未核机器人训练数据、神经权重或完整真机复现。

**S2。** 适合离线生成/改进可执行教师或复位程序。把其轨迹收集后蒸馏到 VLA 是我们的迁移假设，论文未替我们验证。需核评估门、特权输入、部署模型调用和程序修改对数据版本的影响。

## 4. 升级核查与旧候选重核：不计新增

### R1. PhyAgentOS：从浅筛提升到官方运行时边界核实

2026-07 论文；当前仓库 2026-08 后转向 Forge，旧 PhyAgentOS-Dev 链接重定向当前 core。本轮读 [当前仓库](https://github.com/PhyAgentOS/PhyAgentOS-core)、[框架官方说明](https://github.com/PhyAgentOS/PhyAgentOS-core/blob/main/docs/en/01-framework-introduction.md)、[论文](https://arxiv.org/html/2607.16636v1)。SYSU HCP、鹏城实验室、X-Era；MIT，访问时约 2.5k stars、119 forks、276 commits。19 本体等论文覆盖混合仿真与真机，不等于每一本体都完成学习闭环。

当前 Forge 文档明确分开 execution、evidence、verdict，支持绑定快照、异步调用协调、SQLite 状态与观察者 websocket；但同时明确**不提供跨 tool 的资源 lease**。endpoint max_concurrency 不能代表同一机械臂全局排他。观察采集为 best effort，前后观察也不是连续 TD 数据承诺。技能、节点、模型与仿真资产分开发行，核心运行时存在不等于整套模型资产已经可得。[官方语义边界](https://github.com/PhyAgentOS/PhyAgentOS-core/blob/main/docs/en/01-framework-introduction.md)

**S2。** 是下一轮运行时重点，而非已选替代品。固定当前实现读取 RPC→dispatch→异步 terminal→观察→SQLite/receipt，验证取消、资源所有权与去重；与 RPent/OpenETA 按同一调用链比较。2026-07 论文的 Markdown Session-Centered Runtime 不可拼接成当前 Forge 的已实现功能。未建立其低层 VLA learner/replay 完整证据。

### R2. SOAR 与 AutoEval：已有自动采集/复位路线，维持边界

实际重开 [SOAR 项目](https://auto-improvement.github.io/) 与 [代码](https://github.com/rail-berkeley/soar)：可用来研究真实机器人长期采集、任务与复位组织，其更新路线不应被改称已具备本任务所需 actor-critic RL。此处没有新增源码层结论。

实际重开 [AutoEval 项目](https://auto-eval.github.io/) 与 [代码](https://github.com/zhouzypaul/auto_eval)：官方公开服务说明写到 2026-01-01 之后 TBD，因此不能在 2026-09-23 宣称现成远程真机服务正在开放。其阻塞动作接口和策略服务端维护 chunk/history，也不能直接证明满足本任务原生异步连续控制要求。S2 仅在计划复用对应组件时进一步确认服务与接口；不重复旧报告性能排名。

## 5. 多渠道覆盖、排除项与证据限度

| 渠道 | 实际访问/核查 | 本轮作用与限度 |
|---|---|---|
| 学术论文 | SAGE、Harness-Zero、RHO、DGAC、GPT-Policy、AGP、VLCP、PhyAgentOS、StageGuard、ARMOR 的论文页/相关章节 | 核方法对象、训练/部署区别、作者限制；并非逐行全文审稿 |
| 作者 GitHub | 上述公开仓库及 RAI/dora/ROSClaw；访问 LICENSE/README/指定文档 | “读过仓库说明”与“读过执行/训练源码”分开；本轮大部分尚未读调用链 |
| 官方 HF | Harness-Zero AppWorld 权重；AGP 数据卡及 LABELS.md | 实際核到资产及标签来源；对 SAGE/Phy 等检索无对应结果不等于全网不存在 |
| 官方发布与 PR | RAI #645、dora #3466、Phy issue 页；Anthropic 机构评估文章 | Open PR 不算合并实现，自动审查评论不算独立复现；机构展示不能替代学习接口 |
| 社区线索 | 实际打开 awesome-embodied-rsi；Reddit 等只作检索线索 | 从社区寻找漏项，然后回原论文/作者库；不借社区热度证明工程成熟 |

[Anthropic 机器人评估文章](https://www.anthropic.com/research/claude-plays-robotics) 覆盖直接控制、代码工具、预训练技能与训练 RL 等不同抽象层，有助于避免把它们混成一种“policy 能力”；文中承诺的后续代码发布没有被本轮核为已可用。[社区 RSI 索引](https://github.com/cocacola-lab/awesome-embodied-rsi) 仅用于发现线索。

排除与去重：StageGuard 的睡眠分期同名仓库不属于本候选；多个 ROSClaw 身份不混合；PhyAgentOS 新旧仓库别名合并；SOAR、AutoEval 与 PhyAgentOS 不算新发现；RoboRSI/RPent/OpenETA 等旧结论没有重新包装成 S1 增量。stars/forks/downloads 是访问快照，只表示关注度，所有候选均未由本轮完成独立复现。未看到的权重、数据和许可证统一记为“未核到/未知”，不是断言不存在。

## 6. 交给 S2 的递进问题与拟用证据

| S2 核查对象 | 需实际到达的证据 | 决策影响 |
|---|---|---|
| PhyAgentOS 对照 RPent/OpenETA | 固定版本执行/取消/terminal 链、跨工具所有权、观察回执、依赖发行资产 | 是否复用整个运行时、只借鉴局部机制，或保留已有执行底座 |
| AGP 数据→学生学习 | 真实 schema、动作/图像时间戳、缺 response、LABELS 来源、可回放最小样本 | 是否能获得可信 BC 子集；是否有资格产生真实 RL transition |
| GPT-Policy 教师→动作 | 许可状态、adapter 实际路径、单位/坐标系、IK、执行后记账、必要私有依赖 | 能否复用代码，或仅借鉴公开方法；是否能输出学生可表达动作 |
| SAGE | 发布资产是否补齐、学生/教师 mask 与损失、失败教师场景 | 将其作为机制依据还是实现基础；不得把 AWBC 当已验证万能过滤器 |
| Harness-Zero | 审阅轨迹与 mask、失败轨迹处理、动作替换后执行事实 | 原生动作蒸馏可迁移部分；零成功与纯 SFT 的局限 |
| ROSClaw / RAI / dora | 真实资源控制/抢占、时间戳、背压/丢弃、版本固定、回放退出条件 | 哪些模块可独立复用，哪些只是声明或开放 PR |
| DGAC / StageGuard / ARMOR | 官方代码与权重是否发布；人工/模型标签边界与监督时钟 | 纠正/评分辅助能否落地；不把监控参数收益计入控制 policy |

以下是待 S2/S3 反证的设计推断，不是任何单篇论文已经验证的系统：GPT-6 观察后输出纠正意图，经本体适配与约束成为学生动作空间可表示的动作；运行时执行并记录实际动作和后继；可信教师样本回流 BC，所有真实执行且时序成立的 transition 按 learner 的实际算法进入 RL；程序/复位知识可积累，但以去掉在线教师后冻结 policy 的独立任务能力评估学习收益。合成动作、未执行 chunk、代码文本、任务自述、复位成功和救场成功分别保留来源，不能偷换为同一种监督或收益。

