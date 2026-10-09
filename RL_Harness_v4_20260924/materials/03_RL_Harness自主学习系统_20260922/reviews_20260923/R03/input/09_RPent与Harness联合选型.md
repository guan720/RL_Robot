# RPent 与 Harness 联合选型

2026-09-23｜原论文、官方文档与固定源码审查｜本项目未安装、训练或运行 RPent。

**结论：RPent 应提升为本项目首选的 Harness 工程骨架，优先级高于直接以 RoboRSI 为主框架，也比完整迁移 Zetta 更贴近当前需求。** 理由是它已有大模型主导的观察—工具—反馈流程、VLA 与解析动作的统一接口、明确许可、Franka 真机扩展，以及区分实际动作和 VLA 预测的数据记录。但它目前不是开箱可用的“GPT-6＋自主在线 RL”：真机仍有人工复位／结果确认，公开数据闭环主要导向 SFT，异步执行和本项目 RL 数据契约需要新增。

这个推荐来自模块与源码适配度，不能由“与 RLinf 同属一个项目组织”推出所有 RL 接口已经兼容。推荐组合是：**RPent 的观察／工具／记忆结构＋本项目唯一实体 Gateway＋共享双向 BC＋RL learner**；借鉴 Zetta 的候选门禁和 RoboRSI 的技能修订组织，不同时部署四套控制主循环。

## 1. 先确认 RPent 指什么

| 项目 | 核验结果 |
|---|---|
| 全称 | Recursive Physical Agent，仓库标题为 Agentic Infrastructure for the Physical World |
| 官方仓库 | [RLinf/RPent](https://github.com/RLinf/RPent) |
| 对应首篇论文 | [Harness VLA: Steering Frozen VLAs into Reliable Manipulation Primitives via Memory-Guided Agents](https://arxiv.org/abs/2607.08448)，2026-07-09 的 v1 |
| 作者机构 | 以清华大学为主，作者另有 Striding AI、Purdue、CASIA、Infinigence AI、中关村学院、HKUST 等；来自论文署名，不把组织名等同独立复现 |
| 固定代码 | [`eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1`](https://github.com/RLinf/RPent/tree/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1)，提交时间 2026-09-22 |
| 许可 | 根 LICENSE 为 Apache-2.0；不同外部模型、数据和机器人依赖另核许可 |
| 影响力快照 | 2026-09-23 GitHub API 查询为 931 stars、97 forks；网页缓存同时显示 930 stars，取数时间不同，不把一星差异解释为实验差异 |
| 引用／下载 | 本轮未得到可比、可靠的独立引用量或 RPent 本体下载统计，不能把未知写成零；`rpent-rlinf` 包也不等于 RPent 本体全部使用量 |

论文与当前代码要分开看。初读 v1 后，本轮复审另外核对了 2026-09-02 的最新 v4 方法与局限：仍研究**冻结 VLA＋固定动作原语＋任务／全局记忆**，主要实验为仿真；当前仓库已经增加真机扩展与数据记录。论文的系统成功提升不是底层 VLA 经在线 RL 变强的证据。[v1](https://arxiv.org/html/2607.08448v1)、[v4](https://arxiv.org/html/2607.08448v4)。本报告不混用不同版本的实验增益数字。

## 2. RPent 为什么更贴近我们的 Harness

RPent 把 VLA 封装为可调用、可重试的动作能力，与移动、旋转、夹爪、视觉定位等工具放在同一接口。大模型读取工具执行后的图像和状态，决定下一步。API、Codex、Claude Code 等 planner 复用工具和 prompt，可以直接承接“GPT-6 观察和纠正”的主角色，而不必先另建一套小模型裁判。[官方架构](https://rpent.readthedocs.io/en/latest/rst_source/development/architecture.html)

本项目应保留这一认知和工具边界，同时改变控制组织：共享 policy 在本地异步运行，GPT-6 异步观察；GPT 提出接管时，由唯一 Runtime 和 Gateway 完成受确认的控制交接。不能把原版轮流执行完整工具、工具结束后再观察的节奏，直接称作持续异步 VLA 监控。

工程上优先预检默认 API planner。官方说明支持 OpenAI Responses，`api_loop.py` 使用 Pydantic AI 接收模型配置并注册 Toolkit 工具；它便于把 GPT-6 限定在本系统提供的观察和动作接口。模型 ID、provider 路由、多图和工具响应仍需接入实测，不能以文档支持替代运行验证。Codex planner 可作为另一条路径，但不继承其默认广泛文件权限作为本项目的控制授权。[Planner 配置](https://rpent.readthedocs.io/en/latest/rst_source/usage/configure_planner.html)、[API 实现](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/api_loop.py)

成功经验可以形成任务卡和分层记忆，减少下次重复推理。Flash planner 重放提前确定的工具程序，并按实时感知重新定位参数；这是复用执行经验的有用能力，但不是参数学习，也不是任意新代码已经通过回归的证明。[Flash 实现](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/flash.py)

## 3. 源码揭示的已有能力与缺口

### 3.1 有真实数据记录，不只是视频和聊天日志

`rpent/flywheel/episode.py` 的 `EpisodeWriter` 保存 N 个动作及 N+1 个观测，还记录 reward、terminated、truncated、primitive ID、VLA chunk ID 和预测索引；完整 VLA 提案另存。这个结构已经体现“建议动作与实际动作不同”，比只记录工具起终截图更接近本项目 B4 的需求。[EpisodeWriter](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/episode.py)

但不能直接称为现成 RL buffer：

- 官方 Flywheel 当前只支持 LIBERO evaluation 模式，导出器筛选成功回合到首次成功的前缀，输出 LeRobot 数据，训练由外部 RLinf SFT 完成。失败原始数据保留，但默认不进入这个监督导出。[官方 Flywheel](https://rpent.readthedocs.io/en/latest/rst_source/usage/flywheel.html)、[导出器](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/export.py)
- 本项目要另加失败转移的 RL 视图、未执行 Harness 纠正标签池、goal／评分版本、request→commit→activation、绝对帧时间，以及独立 BC/Q mask。已有 `action_source` 仅由是否有 VLA ID 推导，不够表达纠正、异常恢复、保持和候选试验。
- 原记录器先在 Python 列表积累，再在 finalize 写 NPZ 并原子改名。真机长时运行需增加追加式事实 journal、增量落盘和断电恢复；目录存在并不等于每一步已持久化。

历史遥操、Harness 实际纠正、未执行建议都可长期保存；视图按算法需求使用，不能为了适配成功导出接口丢掉失败，或把未执行建议编成真实机械转移。

### 3.2 有合作式取消，但不是本项目所需的实体控制交接

通用 Toolkit 通过锁限制同一实例的一次 active operation，`cancel_active_and_wait()` 发取消信号并等工具返回。这提供了有用的软件串行化；它不等于设备级唯一 owner、跨进程租约或驱动已经保持。[Toolkit 实现](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/tools/toolkit.py)

双 Franka VLA 路径是先同步 `predict`，再逐动作调用环境并检查取消；因此并非整块完全不可切断，但推理和执行没有本项目需要的重叠调度。在途 RPC／推理仍可能需要等待。相应环境的 `chunk_step` 返回观测、终止标记和最后 info，读取的 `_reward` 未返回；需在真实动作层补逐步数据。[双臂工具](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/tools.py)、[环境执行](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/env_server.py)

迁移要求是：RPent 的工具提交意图，Gateway 掌握设备；policy 与 Harness 的 motion 均经过相同 request、执行和 quiesce 协议。不能再让 RPent env server 与现有 policy 控制器各开一条机器人连接。

### 3.3 一个很容易漏掉的正反任务条件问题

当前双 Franka `_run_named_vla_skill` 记录 planner 给出的 `prompt`，但真正传给 VLA 的是固定 `_vla_instruction`。这符合其特定 checkpoint 的部署需求，却不满足本项目“共享 policy、正反目标不同”的条件。日志看起来换了指令，模型可能仍执行旧指令。

因此需贯通结构化 goal→VLA conditioning→Q/target→replay→GPT rubric→评测，不能仅在 Harness prompt 增加“A→B/B→A”字样。这一修改还要求用目标条件数据训练和验证，改字符串不是能力证明。[条件化代码](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/tools.py#L452)

### 3.4 真机模块存在，但人工尚未退出闭环

官方有单 Franka、双 Franka 部署接口和真机演示页；双臂发布了特定清桌任务的 π0.5 checkpoint，文档明确它对不同工位可能泛化差，部署者需适配数据、控制与标定。用户的松灵 ALOHA 类平台不能直接继承 Franka 的动作维度、rot6d 约定和双节点控制配置。[Franka 文档](https://rpent.readthedocs.io/en/latest/rst_source/usage/franka.html)、[双 Franka 文档](https://rpent.readthedocs.io/en/latest/rst_source/usage/dual_franka.html)

尤其是双 Franka exploration 中的 `request_scene_reset` 要人恢复场景，`request_operator_verdict` 要人给结果，当前 `solved()` 依赖这个结果。源码也记录 `success_source=operator`。这是明确的人在环实施，不是少数注释里的可选建议。[真机 Toolkit](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/toolkit.py)

本项目需要用 GPT-6 的版本化观察判据替换日常结果判断，由共享反向 policy 和 Harness 异常恢复替换物体复位，并记录仍无法自动处理的状态。官方演示可支持“真机组合和观察可行”的判断，不能当作无人持续在线 RL 的统计证据。[官方真机演示页](https://rpent.readthedocs.io/en/latest/rst_source/usage/real_world_demos_franka.html)

### 3.5 记忆合并不是程序安全与能力晋级门禁

MemoryManager 有来源、适用域、冲突处理与证据合并，值得复用。但其 `verified` 状态可由证据 cell／task 数量规则生成，不能据此认定恢复代码已通过工位回归。它是记忆证据等级，不是本项目动作权限。[记忆管理](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/memory/manager.py)

此外 Codex planner 代码设置 `Sandbox.full_access` 和 `ApprovalMode.deny_all`；专用 profile 的目录隔离不是代码执行沙箱。不能把模型不需要逐次人批理解为代码可绕过 Gateway。候选生成进程、固定评分、设备凭据和执行工具权限必须实际分离。[Planner 实现](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/codex.py)

本项目仍需 `CANDIDATE→TRIAL→固定核验/回归→RELEASE`，限定调用能力、预算与版本。合法候选可自动真机试验，不把人工审批重新塞回每轮循环；越界或证据不足时回退／中断。

## 4. 与 RoboRSI、Zetta、ENPIRE 的联合比较

| 比较项 | RPent | RoboRSI | Zetta | ENPIRE |
|---|---|---|---|---|
| GPT 主观察与工具调用 | 明确主流程，API/Codex 等后端可换 | 多角色诊断与技能执行组织清楚 | 运行监控／恢复与候选进化清楚 | 工位工具与自动实验接口丰富 |
| VLA 与解析动作组合 | 统一 primitive/tool，最贴本项目 | 技能树封装，抽象更广 | 冻结 VLA 与恢复程序组合 | 现有 RL 路线侧重其 PLD/SERL 接口 |
| 真机可复用入口 | Franka／双 Franka 有源码与部署文档 | 博客真机流程；需要按硬件核具体接口 | 已审固定版后端为仿真 | 有真机工位与 RL 生命周期 |
| 真实动作／提案数据 | Flywheel 已明确区分，真机需移植扩充 | 不能将视频/工具日志等同逐帧 RL 数据 | 需补本项目动作与学习来源数据 | 有真实 action_source 转移，但当前单步路线不能直接承载异步 chunk |
| 现成自主在线 RL | 无；默认 Flywheel 接 SFT | 已审 RL 接口为 skeleton | 无；已审论文冻结 VLA | 有特定 RL 实施，仍依赖已建工位和人工环节 |
| 新代码候选与晋级 | 记忆／任务卡好用，需补严格程序门禁 | 技能修订方法值得借鉴 | 候选、影子检查、回归门禁更完整 | 固定实验契约有价值，但不能直接允许 Agent 随意改 reset/verifier |
| 本项目角色 | **首选认知和工具骨架** | 技能职责与修订方法参考 | 候选管理与晋级协议参考 | 真实环境／转移生命周期参考 |

比较依据分别为 [RPent 固定代码](https://github.com/RLinf/RPent/tree/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1)、[RoboRSI 博客](https://lab.noematrix.ai/blog/2-roborsi/)、[Zetta 固定 README](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/README.md)、[ENPIRE 实验契约](https://github.com/NVlabs/ENPIRE/blob/99ee90acf65b5b18957c8382ad580db999528be3/enpire/policy/autoresearch_instruction.md)。具体细节以各专项审核为准，表中“没有现成完整能力”不等于框架无法扩展。

RPent 当前更合适，并不让 RL 算法自动变成 RLinf 原生某条路线。先按共享目标、完整动作头、Harness BC 和异步因果数据定义所需 learner，再比较复用成本；框架同源只是减少部分接口工作，不是算法有效性证据。

RoboRSI 的“RL 接口仍为 skeleton”只指本次核到的特定入口：固定 SHA `9b644d270560c440d760965cf1b859df674459de` 的 `roborsi/embodied/skills/_lib/rl/pi0_posttrain/policy.py` 中 `run` 抛出 `NotImplementedError`，不外推为整个项目不存在任何学习路径。[固定入口源码](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/roborsi/embodied/skills/_lib/rl/pi0_posttrain/policy.py)

## 5. 如何接入本项目，避免重建所有东西

| RPent 资产 | 本项目接法 | 首轮必须补什么 |
|---|---|---|
| Planner / GPT 图文输入 | 作为主观察和纠正决策服务 | 时序观察包、请求身份、三种迟到用途、固定 rubric |
| Toolkit / tools schema | 暴露 observe、correct、recover、trial 等能力 | 工具发意图；所有 motion 指向唯一 Gateway，不能私开驱动 |
| RobotSpec / env client | 新建松灵平台适配 | 型号、相机、主动臂、单位、标定和真实回执，不拷 Franka 常量 |
| VLA client/server | 服务共享双向 policy | goal 真正进网络；与 Q/target 一致；推理执行异步，旧队列与缓存失效 |
| Flywheel recorder | 作为动作／提案存储结构起点 | 真机逐帧日志、持久 journal、request/commit/activate、失败与查询标签分流 |
| Memory / task cards | 记录可复用抓空、偏位等处理经验 | 版本及适用域，禁止用 memory confidence 直接赋运动或监督资格 |
| Flash | 对成熟重复恢复减少 GPT 调用 | 同样受限、可中断、记录完整，恢复结束重新核验实物状态 |
| Result / evaluation | 保存运行结果 | 独立 policy、系统辅助、自主学习三套账；双向同一 checkpoint 验收 |

前期只需完成一个反复抓放闭环：共享 policy 尝试→GPT 判断抓空→Harness 纠正／建议→记录 BC 与真实 RL 数据→目标换向→共享更新→关闭动作纠正评测。通过后才让 Harness 自动生成新恢复程序。成熟代码降低开销，但 GPT 仍是语义观察主体；减少调用不是更换研究出发点。

首版必须改变 RPent 原来“解析动作完成运输、VLA 只负责局部接触”的默认评价口径。用户要学的是完整目标条件 pick-and-place policy；如果 Harness 永远代做运输或抓取，系统可以变好但模型未学完整任务。应聚合这些有效动作、安排自主重试，并保留完整任务的无动作辅助评测。

聚合表示长期保留，训练仍服从 02／06 的资格：同信息集下的完整下一槽 U 可做首版 BC，反馈式单步纠正不能重复填成 n 步。无法满足普通 BC 定义的片段保留为候选或其他明确监督分支，不因最终回合成功自动解锁。

## 6. 最终选型仍需回答的八个问题

1. 松灵驱动是否能让 RPent 和 VLA 统一经过同一个 Gateway？
2. 正反目标是否确实进入同一模型和 Q，而不是只写进 planner 日志？
3. 一个迟到 GPT 回复能否保留历史标签，同时完全失去当前运动权限？
4. 请求、结果提交、激活和逐帧动作能否重建同一条真实时间轴？
5. 人工 verdict 和 scene reset 是否已被可审计的自动流程替换，而非自动返回“成功”？
6. Flywheel 是否补齐真机失败、纠正和查询数据，且损失使用正确？
7. 代码候选能否自动试验，但不能改固定评分或绕设备网关？
8. 共享 policy 的双向无动作辅助能力是否提高，而不仅是 Harness 更会代做？

前七项是工程和数据门槛，第八项必须靠实际实验回答。当前可下的结论是“值得优先复用并进行适配”，不是已经证明本工位会无人自学习。

## 7. 本轮证据与核查范围

已读原论文、官方架构／Franka／双 Franka／Flywheel 文档及所列关键源码。固定文件快照和下载失败记录见 [manifest](research/rpent_snapshot_eb269c8a278b/manifest.json)。部分文件下载遇网络超时，关键 `dual_franka/tools.py`、`pyproject.toml` 已另经网页工具读取固定版本，未假称全部本地归档成功；未安装依赖、跑仓库测试或操作机器人。

需特别保留三个区别：官方仿真 benchmark 不等于本工位真机；框架代码开源不等于外部 checkpoint 对松灵可用；有真实反馈日志和 RLinf 依赖不等于 Harness＋在线 RL 已经接好。补齐这些接口后，RPent 才能成为本文完整方案的工程承载，而不仅是另一套表现很好的演示。
