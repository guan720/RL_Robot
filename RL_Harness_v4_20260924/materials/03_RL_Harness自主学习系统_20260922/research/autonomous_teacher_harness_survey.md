# 自动教师与具身 Harness 的补充审核：优先检查 Zetta 的可复用骨架

核验日期：2026-09-22。范围：单臂抓放、基础 VLA 可能几乎不会当前任务、少量示范与人工接管可用，目标是逐步减少观察、纠正与复位劳动。仅访问论文、官方项目与公开源代码，未安装依赖、运行训练或操作机器人。所有迁移设计与验收门槛均为本文建议，不是原论文已完成的实验。

## 1. 本轮改变的判断

**不应再直接把“从零做轻量 runtime”列为首选。Zetta 已公开了与需求高度重合的运行时监督、恢复裁决、失败分析、候选版本与评测晋级代码，应先做技术预检。** 它能够替代先前拟议自建工作中的相当一部分；如果许可与真机接口预检通过，建议围绕一个 Zetta 派生 Harness 接入一个 VLA 学习器，而不是同时运行 RoboRSI、ENPIRE、Zetta 三套主控。

这一调整不意味着已经找到完整的“真机自动 DAgger + VLA RL + 自复位”产品。Zetta 的公开论文实验是冻结 VLA 的仿真 Harness 改进；其现成运行时不能直接视为松灵机器人驱动，也没有证据表明自动恢复轨迹已回流训练 VLA。**技术上优先审核 Zetta，真实站点与转移协议参考 ENPIRE，教师能力与学习回流另设验收，**是当前更有依据的组合选择。[Zetta 论文](https://arxiv.org/html/2608.16590v1)、[官方代码](https://github.com/air-embodied-brain/Zetta-Embodiment)、[ENPIRE 官方代码](https://github.com/NVlabs/ENPIRE)

还需纠正一个评价口径：冻结弱 VLA 后，依靠外部恢复代码把任务做成，证明的是“系统能力提升”；只有在撤去教师后学生自身成功率提高，才能证明“教师帮助策略学会了”。两者都有价值，但应分开报告。

## 2. 六项有原始来源的覆盖审核

| 方案与可信度线索 | 已有的相关能力 | 实际实现／接口边界 | 对本任务的结论 |
|---|---|---|---|
| **Zetta ζ，2026-08；清华 AIR、Z-TransAI 等；论文、项目与源码均可访问** | 快速 Critic、Orchestrator 裁决、恢复程序、慢速诊断与代码迭代、候选评测晋级 | 公开 adapter 是仿真；VLA 在论文中冻结；没有展示恢复数据训练学生的闭环；项目自身许可证正文本次未找到 | **Harness 骨架优先预检对象**，比单凭 RoboRSI 概念自建更完整；不是已经验证的真机自动教师 |
| **ENPIRE，2026-06；NVIDIA 官方仓库及真实机器人研究** | 站点建立、执行、验证、记录、改进；代码技能与 RL actor 接口；人工接管数据交换 | `learn_skill()` 对接外部 policy server；公开 RL 设计采用单步动作，接管标签是 `human`；需任务 reset/verifier 与站点标定 | 真实站点和数据接口的重要参照；不能把“有人接管”改名为“自动教师已完成” |
| **ASPIRE，2026-06/07；NVIDIA、UMich、UIUC、Berkeley、CMU 等** | 程序技能发现与复用，有仿真及 YAM 真机目录，含退避／恢复相关技能说明 | 官方明确仍依赖成功检测、可靠复位、监控与标定；受现成 primitive API 约束；学习主要发生在程序与技能库 | 可复用恢复程序组织方法；没有消除本任务最关键的站点与教师依赖 |
| **RoboRSI；Noematrix 官方博客与 nssmd/RoboRSI** | 多角色失败分析、技能代码更新、技能版本与模型微调入口 | 固定版本的 `pi0_posttrain/policy.py` 是 `NotImplementedError` 骨架；工具中途逐步采样 hook 默认无实现 | 可参考离线技能改进与记录流程；不能作为现成在线 VLA RL 栈 |
| **AutoSERL，2026-07；论文、项目与代码公开** | 从示范与局部引导构建自动干预，减少部分训练中人工操作；有真机任务证据 | 自动引导仍有示范路径和恢复点等前提；不是面对任意学生失败状态生成正确抓放动作的通用教师；原生栈也不是 VLA | 比笼统“LLM 接管”具体，可借鉴自动干预机制；不直接替代 VLA Harness 主框架 |
| **Code as Policies，2022/2023；Google 官方论文、项目与代码** | 将感知输出与机器人 primitive 组合成可执行代码；提供真实机器人展示 | 公开 README 主要引导至示例 notebook；没有 RL actor–learner、版本晋级或教师回流全链路 | 说明代码策略可以担当教师能力来源；不能由“生成代码”推导出“能纠正未知物理失败” |

来源：[Zetta 项目](https://air-embodied-brain.github.io/zetta/)、[ENPIRE 任务契约](https://github.com/NVlabs/ENPIRE/blob/main/enpire/env/docs/NEW_TASK.md)、[ASPIRE 项目与局限](https://research.nvidia.com/labs/gear/aspire/)、[ASPIRE 代码](https://github.com/NVlabs/ASPIRE)、[RoboRSI 博客](https://lab.noematrix.ai/blog/2-roborsi/)、[AutoSERL 论文](https://arxiv.org/abs/2607.01651)、[AutoSERL 代码](https://github.com/autoserl/AutoSERL)、[Code as Policies 项目](https://code-as-policies.github.io/)、[Google 官方代码说明](https://github.com/google-research/google-research/blob/master/code_as_policies/README.md)。

机构与代码公开提高可检查性，不等于独立复现已充分。Zetta、ASPIRE、ENPIRE 均为新近工作，本轮不以星标或演示视频推断已经被大量第三方验证。GENESIS／AutoRobot 名称还可能指向仿真平台或其他同名工程；在本次限定检索内，没有找到比上述候选更贴近且原始证据更完整的同名真机自动教师系统。不能据此断言所有同名研究都不存在。RHO 与 UniIntervene 的进一步审核由本次会话其他专项报告覆盖，本文件不重复结论。

## 3. Zetta：固定版本和现成模块

本次解析 `main.patch` 并访问到的固定版本为：

`1fee179644d52c32fa5a7728751cf0853a29b9c0`

以下采用该 SHA 的永久链接，避免把仓库后续更新与本次判断混在一起。[固定提交](https://github.com/air-embodied-brain/Zetta-Embodiment/commit/1fee179644d52c32fa5a7728751cf0853a29b9c0)

### 3.1 不是仅有 README 的空壳

已有清晰的软件分层：`zetta/evolution/` 管候选与改进生命周期，`rollout_runtime/` 管会话、环境执行与推理，`robots/` 下接各环境的 critic、工具与恢复语义。CLI 已有分析、诊断、提案、评测和晋级调用路径。[固定版 README](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/README.md)、[evolution CLI](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/zetta/evolution/cli.py)

`models.py` 里能看到冻结 campaign、内容哈希、结构化 critic 与 recovery、候选 bundle 的校验。critic 有触发条件、持续步数和冷却；recovery 有工具步骤、停止条件与回退；候选要求 critic 与恢复路径对应。它比“把一段自由文本交给 agent 自行执行”更适合受控迁移。**但 schema 校验只能检查结构，不能证明恢复程序在物理上有效。**[结构化版本与候选契约](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/zetta/evolution/models.py)

### 3.2 控制权：有真实软件约束，但约束对象仍是环境会话

`RuntimeEnvWorker.handle_command()` 在执行前核验 binding、episode、operation sequence；改变环境的命令检查 active operation，并在 session lock 内调用 handler。该实现证明“只有一个有效执行序列”不是单纯架构口号。它可以复用来拒绝过期推理结果与重复执行。[执行分发代码](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/rollout_runtime/workers/env_worker.py#L1409)

**迁移推论：**会话互斥不自动等于“一台真实机器人永远只有一个写入者”。仿真可以按不同 env spec 创建多个 pool；物理设备必须在驱动边界以固定 `robot_id` 互斥，并确保所有恢复、RL、遥操命令都经同一个执行入口。禁止通过另一个进程绕过 owner lease 直接发关节目标。这是新增真机 adapter 的验收条件，不是已发现 Zetta 在仿真中存在并发 bug。

### 3.3 取消动作：不能把取消推理等同于急停

代码对取消阶段有明确区分：排队或等待推理时可以取消并丢弃晚到动作；已开始的 env step 要等待执行完成。`cancel_request()` 对不可取消阶段返回 false。[取消实现](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/rollout_runtime/workers/env_worker.py#L2789)

因此，松灵真机 adapter 不能把一个长动作块或整个恢复脚本作为不可中断的单个 env step。需要控制器可确认的停止／保持协议，或者在满足最大停止延迟的短执行粒度内切分；接管确认后清空旧 action chunk，并使旧推理失效。最大允许延迟应由实际控制周期、速度和工作区决定，不能凭论文设一个通用数值。

### 3.4 接口有逐步信息，但不等于完整教师训练数据

公开接口包含 `policy_infer` 与 `action_step` 的分离，能先取 VLA 动作再执行；`StepResult` 包含执行长度、奖励、终止标志及可选逐步记录。`PerStepRecord` 的显式字段没有统一的实际动作和来源字段，可通过扩展记录，但不能假定天然具有；RoboTwin 路径明确不提供逐步观察。[消息与执行结果契约](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/rollout_runtime/api/messages.py#L331)

本项目要新增的最小记录应包含：观察时间戳、学生提议动作、实际执行动作、动作坐标与单位、来源、teacher/bundle/checkpoint 版本、当前目标、奖励版本、截断原因、实际执行长度与动作有效掩码。恢复期间同样记录，不能只存“调用 grasp() 成功”这一条高层日志。

这也意味着现成的 `EpisodeRecord.success` 不是 RL replay transition。动作轨迹 artifact 和 transition sink 是可利用的连接位置，但仍需把它们变为指定 VLA 学习器接受且时间对齐的数据。

### 3.5 真机、物理监督与许可的已核实边界

当前注册的环境 backend 为 `fake/libero/maniskill/robocasa/robotwin/geniesim`，未见松灵或其他实体机器人驱动。名字中的 Robot、RoboTwin 或 runtime 的 real backend，并不足以说明物理机器人已经接通。[环境 backend 注册表](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/rollout_runtime/backends/__init__.py#L37)

`SafetyLayerConfig` 注释限定于接口与仿真完整性，且关节限制 shield 标记为未实现。这是现有发布边界，不宜把配置名理解为真机保护已完成。[配置定义](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/zetta/evolution/models.py#L16)

项目元数据引用根 `LICENSE`，但本次根目录检查与 raw 地址访问未获得许可正文。`THIRD_PARTY_NOTICES.md` 又明确区分 RPent 来源和 Apache-2.0 的 RLinf 来源，并回指项目 `LICENSE`。**因此本轮只能标“源码公开、整体许可待核”，不能标成项目统一 Apache/MIT。** 这不妨碍阅读、技术预检和独立实现接口思想；若要正式 fork、修改或再分发代码，许可确认是单独的可复用性门槛。[项目元数据](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/pyproject.toml)、[第三方来源说明](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/THIRD_PARTY_NOTICES.md)

### 3.6 评测晋级可以复用；不能原样搬运仿真重置身份

`gating.py` 有实际配对检验、bundle 绑定与初始状态身份比较，并区分不同 held-out 协议。代码中的 `physical_reset` 表述包含仿真状态／关节摘要；名称不能证明执行了真实场景复位。[评测实现](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/zetta/evolution/gating.py)

迁移时应保留证据与版本约束，替换初态比较和抽样协议：真实抓放的摆放误差、物体姿态、相机变化与磨损不能靠相同 seed 抹去。候选和旧版需要在事先冻结的初态分层上比较，并记录复位失败；不能因候选难复位便排除这些试次。gate 参数与任何 override 也必须纳入 manifest。

同时开始训练 VLA 后，应把“只改恢复代码”的评测与“只改学生 checkpoint”的评测分开。若 critic、教师代码、奖励和学生权重同时变化，即便整体成功率提高，也无法知道哪一项有效。原论文的冻结 VLA 假设正好使它避开了这个混淆；用户的目标比该设定多一个学习闭环。

## 4. “自动 DAgger 教师”需要三个概念分开

下面是学习接口的分析定义，不把它们冒充上述工程的已有能力。

| 数据来源 | 能合理主张什么 | 不能直接主张什么 |
|---|---|---|
| **实际学生状态上的动作纠正**：学生到达状态后，教师给出当下可执行纠正动作；观察、目标与动作同一时刻对齐 | 最接近 DAgger 的关键需求：为学生诱导出的状态分布补标签 | 不能因为 LLM 输出了一串 waypoint，就认定标签具备专家质量 |
| **从失败状态开始的真实教师接管轨迹**：教师取得控制权，闭环纠正并成功后交回 | 能提供有价值的 intervention imitation / RL 数据；接管首步对应学生失败状态 | 后续状态由教师动作诱导，不能声称每一步都来自未接管学生的状态分布；整条轨迹也不能贴在接管前同一观察上 |
| **恢复初态后教师完成一次任务**：先退回或重置，再从新状态做成 | 是可用示范，或复位策略训练样本，可能改善冷启动 | 不是原失败状态上的动作标签；不能用最终成功倒推先前所有动作都正确 |

对正反任务尤为重要：把 B→A 的复位动作塞进 A→B 的专家动作集合，会产生目标冲突。两者应带明确 goal／task conditioning，或进入不同策略的数据流。对 RL 而言可记录所有实际执行转移，但 reward、termination、goal 与 actor source 必须保真；对 BC/DAgger 而言，需要额外挑选质量合格的教师动作，不能把“不是学生发出的动作”一律视为专家。

有一个可行但仍需验证的自动教师：经过标定的物体定位、抓取位姿生成、IK／运动规划、闭环夹爪与抬升验证，加上有限恢复技能。它可能在本任务的限定工作区内远强于弱 VLA，因此提供冷启动信号。其强项来自已验证的操作能力与场景约束，而不是“Harness”或“LLM”这个名字。物体不可见、落到工作区外、被压住或抓取几何不成立时，程序生成本身不能消除能力缺口。

## 5. 仍需完成的五个桥层，而非再拼一套完整框架

以下工作量分级表示接口改动深度，不是工期承诺；机器人型号、驱动能力与 GPU 尚不足以给可信周数。

| 桥层交付件 | 复用部分 | 新增／适配部分 | 最小验收与阻断条件 |
|---|---|---|---|
| **B1：松灵实体环境与动作契约**，高 | Zetta env registration、observation、policy inference、action execution 结构 | 实体 driver；单臂动作映射、相机同步、夹爪与 proprio、任务 reset 与独立成功判定 | 对录制数据检查单位、轴序、时间戳；实体验证前不能把 sim adapter 当驱动。实际型号／驱动动作语义不明即阻断 |
| **B2：设备级唯一执行者和可确认接管**，高 | session lease、binding/epoch、迟到动作拒绝、执行串行化 | 跨 session 的 robot_id 独占；控制器保持／停止；取消剩余 chunk；遥操与恢复统一入口 | 用假的驱动验证竞争写入、迟到推理和中断；必须能证明旧 owner 失效后不再写入。无法限制停止延迟则不得做自动接管 |
| **B3：有限域自动教师与微步数据记录**，高 | CriticRule／RecoveryRule、候选冻结、artifact 与 sink | 已验证 primitive；教师接管协议；逐步实际动作、来源、目标、成功与置信标签 | 对学生产生的失败状态逐类测试教师，报告可覆盖范围。只会从整齐初态演示、不懂失败态纠正时，不能称自动 DAgger |
| **B4：VLA 学习器与数据质量桥**，中高 | policy backend 与模型版本接口、运行日志 | replay 导出、teacher buffer、目标掩码、chunk 截断与行为动作对齐、训练 checkpoint 登记 | 固定小数据离线检查可读性、维度和目标；必须能从单个训练样本追溯真实执行动作。未执行动作被当真实 TD 转移即阻断训练；可信动作标签可进入独立 actor 监督 |
| **B5：真机评测、版本发布与回滚**，中高 | bundle hash、campaign、评测记录与晋级逻辑 | 初态分层；教师与学生分开评测；奖励冻结；检查点加载及原子版本切换；回滚一致性 | 先只更新一个变量，并以不带教师的学生评估检验是否学会。恢复成功率、学生成功率与人工分钟必须分开统计 |

这些桥层的核心是把“代码做出了纠正”变成“同一真实机器人执行了、观察与动作被正确记录、学习器确实使用了、学生由此变好”的证据链。只加一个 gym 包装器或把 LLM 接到 action API 上，均不足以完成该链条。

ENPIRE 对 B1/B3/B4 提供了比一般 agent 论文更具体的参照：其 RL 文档给出实际动作及来源回传，`reset(obs)`／`step(transition)` 的 policy server 契约，并明确当前不做 action chunk。其人工接管还对夹爪指令与硬件反馈差异、接管步频作了专门处理，说明这些不是“更换 teacher 名称”就自然解决的问题。本文只复用接口思路，不建议把 ENPIRE 的控制主循环再并排运行在 Zetta 主循环旁边。[ENPIRE RL 管线](https://github.com/NVlabs/ENPIRE/blob/main/enpire/env/docs/RL_PIPELINE_DESIGN.md)

ASPIRE 的真机 agent 指令也显式列出恢复技能，并对无法自主复位的状态保留求助路径。它支持构造 B3 的技能目录，但不能证明教师对所有失败状态都有正确动作。[ASPIRE 真机技能入口](https://github.com/NVlabs/ASPIRE/blob/main/aspire/real/AGENTS.md)

## 6. 最小可验证推进顺序与反证

1. **先做无机器人预检**：确认 Zetta 许可与依赖；用固定 SHA 检查执行接口；模拟两种 owner 竞争、取消中动作、晚到 chunk、断连与重新绑定。现有测试文件可作为后续运行对象，本次没有运行测试。[已有协议测试](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/tests/test_evolution_protocol.py)
2. **冻结 VLA，只验证限定域教师**：从真实学生导致的失败状态采样，例如抓空、未夹稳、目标旁掉落、夹着物体停住，逐类验证短恢复和接管数据。先证明教师在这些状态上比学生可靠，不要求它一开始解决任意失败。
3. **先完成数据回流，再扩大自动化**：用少量高质量接管轨迹做一次可审计的学生更新；检查无教师评估是否提升，同时保留教师辅助系统成绩。只有系统成绩提高时，优先解释为 Harness 改善，而不是 RL 已成功。
4. **再接连续正反练习**：复位／正向任务的目标与数据分流；复位失败明确计入人工预算。逐轮减轻接管而非预设教师从第一天就无人值守。
5. **最后开放离线代码进化**：对已经可测的恢复技能提出候选，离线审查与受控评测通过后才更新；奖励与最终成功判定保持独立，避免用修改判分掩盖失败。

应当接受以下反证并调整路线：

- 如果教师只能在人工整理好的场景成功，学生失败状态上的覆盖很低，则应继续补示范、改善感知或缩小工作区，不能靠增加 agent 角色解决。
- 如果恢复接管很好，但学生独立成功率长期不升，应检查目标冲突、动作对齐与训练方法；有必要把其定位为可靠执行 Harness，而非自动学习教师。
- 如果迁移 Zetta 的 backend、停止协议及许可成本高于保留现有真机控制栈，则退回“现有单一真机 runtime + 独立实现 Zetta 的版本／诊断协议”。这应当由预检结果决定，不提前把全部核心重写当结论。
- 如果直接接两套成熟框架造成双控制循环、重复 reset、动作来源不清、奖励时间错位，其总体可行性反而下降，应保留一个 owner 和一套事实记录。

## 7. 结论口径

**本轮最值得优先进一步验证的是 Zetta 的 Harness 骨架，而不是继续泛列 agent 论文。** 它已实现了不少此前拟议自建的模块；ENPIRE 与 ASPIRE 则分别补充真实站点协议和具体技能组织的参照。

但截至本次原始来源核验，六项中没有哪项已经完整证明“弱或零成功率 VLA，在松灵单臂抓放上，通过通用自动教师、真实 RL 回流及自复位实现无需人工值守”。剩余工作可收敛为上述五个桥层，其中实体教师能力和真实动作数据链路最关键。源码公开程度、机构信誉、仿真分数，都不能替代这两个验收。

本文件更新前一轮 [RoboRSI 审核](harness_roborsi_audit.md) 中关于主 Harness 选择的优先次序；前文对 RoboRSI 的已核实代码缺口仍成立，不因新候选出现而删除。
