# RoboRSI 可复用性审阅与 RL Harness 设计

核验：2026-09-22。仅联网阅读和固定版本源码留档，未安装依赖、启动服务、训练或运行机器人。首任务按单臂抓放设计，另一臂不参与；策略为 VLA，初始任务能力可能很弱，GPU 尚未确定。

## 1. 结论：采用轻量确定性运行时，吸收两种 Harness 的成熟部分

**当前最合适的实现不是原样 fork RoboRSI 并把四个 Agent 放入每次动作循环，而是一个确定性 RL 运行时，加 ENPIRE 式环境契约，再加 RoboRSI 式慢速诊断、技能修订和版本管理。**

理由是当前核心目标为持续 RL：可靠地产生训练数据、自动判断结果、恢复场景、管理动作与模型更新。它需要可测量的时序和状态语义。自由推理的 Agent 更适合跨回合归因、编写恢复候选和安排实验，不能承担必须及时响应的机器人监督循环。

| 选择 | 适合之处 | 当前不满足的依赖 | 判断 |
|---|---|---|---|
| 直接 fork RoboRSI 全栈 | 技能树、角色分工、代码候选、执行证据、冻结仿真评测均有实现 | RL 后训练入口仍为 skeleton；真机原语要重写；真机自动验证和动作块取消不能由现有仿真 gate 保证 | 适合作为慢速技能迭代层的来源，暂不作为唯一在线核心 |
| 直接采用 ENPIRE 站点栈 | reset→execute→verify→record→refine 更直接围绕物理实验；已有 RL 桥接、暂停和记录约定 | YAM 站点迁移、人工标定、task-specific reset/verifier；原生 PLD 非 VLA，部分机器人端 launcher 未公开；动作块需改 | 生命周期最贴近需求，完整迁入前仍需站点和 VLA 适配预检 |
| 轻量 runtime＋选择性复用 | 保留现有松灵驱动和 VLA/RL 训练器，只建立必需监督、恢复、验证和发布接口 | 要实现控制权、取消、版本与日志契约；不是零开发成本 | **首选实施路线**；先证明闭环可运行，再决定是否扩大采用上游框架 |

这里“轻量”指功能范围明确，不是省略监控或验证。完整研究系统仍可以有多 Agent，但机器人始终只接受一个运行时下发的命令。

## 2. 固定版本与许可核验

RoboRSI 当前 `main` 经 GitHub 页面 `currentOid` 核实为：

`9b644d270560c440d760965cf1b859df674459de`

[固定源码树](https://github.com/nssmd/RoboRSI/tree/9b644d270560c440d760965cf1b859df674459de)。本节之后 RoboRSI 源码链接均固定此 SHA。关键文件另存于本目录的 `roborsi_snapshot_9b644d270560/`，manifest 逐文件记录下载结果及 SHA-256；10 个目标文件中 6 个下载成功，4 个因网络超时未留档，在线核验见固定链接。这些是静态材料，不是已通过运行验证的安装包。

许可存在元数据不一致：根 [LICENSE](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/LICENSE) 为 Apache License 2.0，而 [pyproject.toml](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/pyproject.toml) 的 license 和 classifier 仍标 MIT。不能只按 README 的开源徽章写成“统一 MIT”。本文不对其重新分发条件作法律结论。

官方博客明确区分真机和仿真：真机仍保留必要的人类安全监管和方向调整。博客的累计任务通过率也不等于某个冻结版本的单次成功率。[RoboRSI 官方博客](https://lab.noematrix.ai/blog/2-roborsi/)

## 3. 源码中现成的部分与缺口

### 3.1 技能与动作执行接口：可以复用抽象，不能直接承诺松灵能力

架构文档将能力组织为任务、原子技能和基础原语；基础技能提供 `policy.run(env, **params)`，原子技能按 `active_executor` 在零样本代码执行和策略检查点间切换，另分成功复位与失败恢复。文档中的文件树和接口是设计契约，具体可运行程度仍需逐任务验证。[架构文档](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/docs/architecture.md)

真机移植规范直接列出控制、相机、标定、抓握确认和规划接口需要适配；例如运动接口必须返回执行后实际末端位姿，夹爪接口要能查询实际状态。仿真接触查询、夹持锁定和网格常量不能照搬。虽然文档提到 aloha-agilex 和 `execute_with_pi05`，这不证明当前用户的机器人已有完整可运行适配。[真机工具规范](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/docs/real-robot-tool-spec.md)

对当前任务的含义：Agent 可以编写“重新定位→接近→抓取→放回”的流程，但必须已经有经过实机验证的定位、规划、夹持和运动工具。只有弱 VLA 时，多写一层代码未必能生成一次成功恢复；代码能组合既有能力，不能替代缺失的物理能力。

### 3.2 RL 入口确实未实现，SFT 封装已有实现

| 精确文件 | 静态核验结果 | 可得出的结论 |
|---|---|---|
| [`roborsi/embodied/skills/_lib/rl/pi0_posttrain/policy.py`](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/roborsi/embodied/skills/_lib/rl/pi0_posttrain/policy.py) | 文件说明为 skeleton；`run()` 直接抛出 `NotImplementedError` | 不能把 RoboRSI 视为现成 VLA 在线 RL 训练器 |
| [`roborsi/embodied/skills/_lib/training/pi0_finetune/policy.py`](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/roborsi/embodied/skills/_lib/training/pi0_finetune/policy.py) | 组装 `lerobot-train` 命令、检查本地数据集、启动进程、返回输出位置；含 π0.5 模型路径 | 存在训练进程接入点，但不等于新的 RL 算法，也未验证当前 LeRobot/检查点组合 |
| [`roborsi/embodied/executor.py`](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/roborsi/embodied/executor.py) | 进程启动、输出、超时和后台作业状态；超时时 kill 子进程 | 进程管理可借鉴；kill 进程不等于机器人取消在途命令或受控停止 |

因此接入方式应为：Harness 调用既有 VLA/RL 训练器的标准任务接口，收集其状态与检查点；不把 `pi0_posttrain` 当成已存在的学习闭环。

### 3.3 代码候选 gate 与自动应用：有实现，但真机发布要加强

[`roborsi/agents/validator.py`](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/roborsi/agents/validator.py) 检查候选只组合公开工具，并临时放入候选代码运行功能 gate 后恢复文件。**自动功能 gate 的已配置范围为 RoboTwin 的 base proposal**；其他类别返回缺少自动功能验证，要求另做匹配任务验证。它不能直接为松灵抓放候选提供真机合格证明。

[`roborsi/learning/auto_apply.py`](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/roborsi/learning/auto_apply.py) 已有 pre/post benchmark、`git apply`、比较成功率后提交或恢复文件的逻辑，默认 `bench_seeds=5`。静态可见其验收依据为点估计比较，且在工作树暂存补丁；不应等同于隔离部署、统计充分的实机验收、异常时完整事务恢复或物理场景回滚。

该文件证明“自主提案与版本保留”的机制存在；真正使用时应在独立候选目录验证，运行机器人始终引用不可变发布包，不能直接 import 正在被 Agent 修改的工作树。

### 3.4 冻结评测和审计：最值得直接借鉴

评测文档区分 `evolve` 和 `eval`；后者禁用技能注册、提案应用、持久计划/技能历史更新及训练数据回写，保存 campaign manifest、append-only episode journal，并提供独立 audit。仿真成功判定来自环境；基础设施和实现错误另外记录。[冻结评测说明](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/docs/EVALUATION.md)

迁入真机时必须补自己的独立 verifier 和实际初态记录。可沿用分离错误原因的做法，但系统可用率与每小时有效任务数仍应计入基础设施故障造成的停机；不能通过剔除故障回合掩盖低自主性。

## 4. ENPIRE 对照：生命周期更贴合，但站点建设不是自动完成的

ENPIRE 的官方任务契约为 `reset→policy.act→step→verify`；CaP 代码策略与 PLD 神经策略为不同模式。公开说明中 PLD 使用 JAX SERL/HIL-SERL，并明确部分神经任务的机器人端 `rl_gear.sh` 未随该发布提供，需自行提供 supervisor。[官方新任务说明](https://github.com/NVlabs/ENPIRE/blob/main/enpire/env/docs/NEW_TASK.md)

RL 接口文档提供 robot-side `learn_skill()` 与 policy server 的转移交换、实际执行动作与 `action_source`、暂停监控等设计；文档明确该循环按单步动作工作。因此原生 VLA 的 action chunk、取消和对齐奖励还需适配，不是只替换网络。[RL pipeline 说明](https://github.com/NVlabs/ENPIRE/blob/main/enpire/env/docs/RL_PIPELINE_DESIGN.md)

其站点流程还包括设备注册、标定板布置、校准和物理检查；官方明确标定需要人工参与。自动策略改进是在这些前提建成之后发生，不能将前置人力计为零。[真实站点流程](https://github.com/NVlabs/ENPIRE/blob/main/enpire/env/docs/REAL_WORLD_WORKFLOWS.md)

值得采用的是环境所有权：策略研究 Agent 可以修改 policy/training，但正常实验中不能改 reset、verifier、评测种子或成功定义。该约束确保优化成绩有可比性。[Auto-Research Contract](https://github.com/NVlabs/ENPIRE/blob/main/enpire/policy/autoresearch_instruction.md)

用户希望恢复代码本身也可改进，因此需要**独立的环境/恢复候选发布通道**。并非永久不许改，而是该变更必须形成新环境版本，用独立恢复测试和旧业务目标复测；不能一边放宽成功判定或简化初态，一边声称原任务 RL 进步。

## 5. 融合兼容性硬门槛：不是接上两个成熟仓库就能训练

RoboRSI 的 [`agent_loop/env.py`](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/roborsi/embodied/agent_loop/env.py) 是工具循环环境契约：`reset(seed)→Observation`，`step→Step` 只有 `done`；`step` 默认未实现，`check_success` 默认 `None`。其中 `hook_physics_step` 默认不采样，注释明确没有可步进物理循环的真机可能不记录工具执行中途的数据。因此，“代码技能能执行”与“能产生逐步 RL 数据”是两个独立验收项。

RoboRSI [`policy_runner/policy.py`](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/roborsi/embodied/skills/_lib/orchestrate/policy_runner/policy.py) 使用 `policy.select_action`，默认动作类型 `qpos`，并在该 rollout helper 中将环境成功判断或 `done` 计作成功。这可能符合某些仿真 backend 的约定；若直接接入把失败和超时也标为 `done` 的 RL 环境，就会误计成功。因此必须建立明确映射，不能把这个静态风险写成所有 RoboRSI 路径都存在的已运行 bug。

ENPIRE [`Policy.reset()`](https://github.com/NVlabs/ENPIRE/blob/main/enpire/policy/interface.py) 只清策略内部状态；其 RL policy server 的 `reset(obs)` 用于开始策略 episode，而机器人环境 reset 才负责移动物体。三者同名但含义不同，必须分别实现。

| 必须自建或适配的桥层 | 可复用来源 | 必须额外落实的契约 | 硬门槛 |
|---|---|---|---|
| `AgileXRobotGateway` | 现有松灵驱动；借鉴 ENPIRE 单一 CAP 运动入口 | 单 owner、租约 generation、实际动作确认、取消和停止状态 | 无法证明确实停止旧动作，就不允许切到恢复或新模型 |
| `TaskLifecycleAdapter` | ENPIRE reset/execute/verify 分离；RoboRSI 成功复位/失败恢复分类 | `reset_scene`、`reset_policy_state`、`reset_episode_record` 分别命名；返回真实起态和失败码 | 不允许把网络重连或 policy.reset 当成物体已复位 |
| `TransitionBridge` | ENPIRE action_source 与实际动作字段；既有 RL learner 数据格式 | obs/next_obs、已执行动作、方向、目标条件、reward版本、terminated/truncated、时间间隔；明确 bootstrap | done 不等于 success；一个正向Q不能无标记承接反向目标 |
| `VLAActionAdapter` | RoboRSI 模型加载可作参考；保留选定 VLA actor | 图像键/尺寸/归一化、语言、proprio顺序、单臂自由度、单位、绝对/增量动作；动作块逐步执行和取消 | 不因维度相同就认为动作语义相同；未执行子步不入 replay |
| `SkillTelemetryBridge` | RoboRSI 工具调用trace；ENPIRE逐步记录设计 | 结构化代码执行时，驱动按采样时钟记录观测和实际命令；高层tool_span关联各步 | 只有调用前后两帧和“抓取成功”文本，不能伪造成完整RL轨迹 |
| `LearnerControlAdapter` | 所选训练器原生 actor/learner、RoboRSI 进程管理 | 健康检查、数据路径与schema确认、更新节奏、检查点版本、故障恢复 | learner消费旧目录或旧schema时不继续无效收集 |
| `EvaluationReleaseBridge` | RoboRSI frozen eval/journal/audit、候选提案结构 | eval禁止训练回写；候选隔离；停机边界发布；模型/代码/环境/reward整包版本 | 改恢复、奖励或初态不能继续沿用旧成绩和未标记replay |

这些桥层可以很薄，但每个都要有实际数据或故障注入证据。先让一个冻结 VLA、一个恢复技能和一个 verifier 穿过全链路，再接 RL learner；最后才开放 Agent 修改候选。这样“轻量运行时”才是有明确实现范围的选择。

## 6. 拟议系统：快监督、连续学习、慢改进分离

```text
机器人驱动 / 摄像头
        │ 时间戳、状态、实际执行动作
        ▼
确定性 Supervisor + RobotGateway  ← 唯一机器人命令入口
   │          │          │
   │          │          └─ 已发布恢复技能 / 受控停止 / 人工接管入口
   │          └─ VLA actor（一个固定发布版本）
   └─ 独立 Reward/Verifier → replay → RL learner → 模型候选
        │
        └─ 不可变事件与视频 → 慢速诊断/Engineer → 代码候选
                                       │
                              隔离验证 / 冻结实机试验
                                       │
                          ReleaseController → 候选发布 / 回滚
```

“慢速”不是离线才能使用：Agent 可异步读取正在发生的日志、提出计划，但不能成为急停、命令仲裁、动作过期检查或相机失联判断的唯一执行者。快监督频率、动作中断延迟和时限以实际驱动测量为准，不在 GPU 未知时假定能做到特定 Hz。

### 6.1 单机器人控制权租约

新增 `RobotGateway`，驱动端只接受其命令。RL actor、恢复执行器、评测器和人工接管不能各自持有独立直连运动入口。

最小协议：`acquire(owner, ttl) → lease_id, generation`；命令携带租约、递增序号、有效期、控制模式和模型/技能版本；驱动拒绝旧 generation、过期和重复命令。TTL 超时进入已定义的受控停止或保持状态，不由语言模型临时决定。

人工紧急接管应能打断租约；普通策略/恢复切换必须先收到旧动作取消确认。这里的租约是本项目新增设计，不能从 RoboRSI 的多 worker 调度或进程锁推断已具备。

### 6.2 暂停与动作块取消必须在驱动侧闭环

`pause` 必须区分停止接收新动作、清空尚未执行的队列、停止当前轨迹、机械臂实际已停四个状态。对于 VLA 动作块：

1. 使用 `chunk_id` 和子步序号，记录每步计划与实际执行。
2. 取消时驱动返回最后执行序号与实测机器人状态。
3. 收到确认后才允许恢复策略或新模型接管；超时转驱动侧停止。
4. 把实际动作、取消原因、执行时长、`terminated/truncated` 和动作来源写入 replay；未执行的动作不能作为已执行 transition。

取消接口若只在 Python 进程中删列表、底层控制器仍执行旧轨迹，不能通过验证。这是首个硬阻断条件。

### 6.3 恢复技能候选与能力 API

推荐每个技能具有：`name/version`、允许起态、动作模式、最大时长、可用工具、预期后态、失败码、验证结果和适用场景覆盖。其运行接口返回 `completed / failed / cancelled / needs_help`，以及 `postcondition_evidence`，不能只返回文本“成功”。

首批 API 限于 `observe`、`estimate_object_pose`、`verify_holding`、`move_bounded`、`gripper`、`execute_policy`、`request_stop`、`verify_region`。其内部若需深度、手眼标定、IK 或抓取模型，都必须作为显式依赖。允许 Agent 组合已发布 API，候选先不获得任意 SDK/网络/文件写入权限。

恢复能力可以来自已学反向 VLA、独立恢复策略、经过验证的规划抓放代码或少量人工示范形成的新策略。**这些都是可选能力来源，Harness 不能自动保证它们存在。** 若只具备一个不会抓取的 VLA，恢复代码可能仍需要前置建站和示范。

需要分别记录 `action_source=rl / recovery_policy / recovery_code / human`。自动代码成功恢复不是人类专家接管，不能无标签地进入专家 BC 缓冲；是否用于 RL 或成功轨迹蒸馏，应由所选算法和质量检查决定。

### 6.4 自动奖励与独立成功判定

将训练奖励 `r_train` 和独立业务 verifier 分离。抓放至少判断物体进入目标区域、夹爪释放及稳定保持；仅凭动作命令结束或 Agent 自述不够。多帧检测、夹爪状态和位姿证据可减少偶然误判，但具体可用传感器需先核实。

Agent 可以提出奖励分类器或 shaping 的候选，但先在保留的人工标注片段上审查漏判、误判和容易欺骗的场景。修改奖励需新 `reward_version`，保留原始观测与标签版本；需要时重标 replay 和重新校验 critic。冻结测试的业务成功定义不随训练奖励一同改变。

不确定状态进入复核或保守失败分类，不强迫 VLM 给出二元答案。降低标注劳动与完全消除标注是不同目标。

### 6.5 日志要能重建一次物理决策

每条事件至少有 `robot_id, run_id, episode_id, direction, monotonic_timestamp, observation_id, lease_generation, command/chunk_id, action_source, policy_hash, skill_commit, reward_version, env_version`，并关联视频、传感器状态、实际动作、终止原因与人工工作记录。

记录 Agent 的假设、候选 diff、依赖、测试配置、失败和保留/回退决定。视频可分层保留，不能只存成功案例。时钟同步、缺帧和观测陈旧程度也是证据的一部分。

## 7. 自动发布和回滚：代码、模型、环境分别版本化

拟议发布对象是一个不可变 manifest，绑定：机器人标定与配置、代码 commit、模型权重 hash、动作规范、reward/verifier、恢复技能集合、环境版本及验证结果。

推荐管线：

1. **候选生成**：慢 Agent 在隔离分支修改代码，learner 输出模型检查点；均不覆盖在线发布包。
2. **无动作检查**：接口、日志回放、离线数据和命令边界；证明无动作测试通过不等于具备实机能力。
3. **受预算约束的试验**：在已定义起态和恢复故障集上测量，固定业务判据；失败与人工干预如实保留。
4. **冻结对照**：对比当前发布版本与候选，报告完整任务、恢复覆盖、人工分钟和自主持续时长，而不只比较训练奖励。
5. **自动晋级**：符合预先设定门槛的候选，由发布服务在机器人已停止、队列清空的边界原子切换；Agent 自己的评价不构成放行条件。
6. **运行回退**：出现性能、时延或故障异常，先受控停止，再回退到已验证兼容版本。若现场状态不在旧版本恢复覆盖内，不能强行重新开始。

Git 回退只还原软件；物体位置、抓持状态、碰撞后姿态不会随代码恢复。模型回退也不应把新数据静默删除。环境/恢复代码更新另设验证通道，评测需要标明环境版本，避免将更容易的起态误计为算法收益。

## 8. 最小可验证里程碑和选型翻转条件

| 里程碑 | 最少证据 | 不通过时的决定 |
|---|---|---|
| M0 控制权与取消 | 注入超时、旧租约、重复动作、取消中途和网络中断；驱动给出实际停止/保持状态 | 暂不允许运行自动恢复或在线版本切换 |
| M1 稳定事件与评分 | 同一录像/传感器重放得到一致评分；完整记录失败；检测到观测过期 | 先修接口与 verifier，不启动自动改进 |
| M2 基础物理恢复 | 对 A、B、中间落点、空抓、持物等已定义状态有实际恢复测量 | 补恢复能力/示范或限制场景，不能以代码生成代替验证 |
| M3 无 Agent 连续 RL | 固定代码版本完成正反训练、超时处理、replay归属、checkpoint评测 | 表明问题在执行/学习底座，暂不增加多角色复杂度 |
| M4 慢 Agent 单变量改进 | 候选以固定业务判据改善完整任务或人工成本；能自动拒绝退化方案 | 保留分析建议，暂不自动发布 |
| M5 扩大自主时段 | 有持续运行分布、报警误报/漏报、人工总分钟与物理不可恢复事件 | 调整能力覆盖；不宣称已替代现场接管 |

如果 ENPIRE 对当前松灵驱动、VLA 单步/动作块桥接、恢复 supervisor 的预检明显少于自建改造成本，可以把确定性运行时落在 ENPIRE 上；如果 RoboRSI 后续补齐所需 RL、实机 gate 和动作取消，也可扩大 fork 范围。决定应来自接口预检结果，而非项目名称。

当前的自主性目标应按工作种类拆分衡量：日志观察和失败整理最容易自动化；成功评分依赖可靠 verifier；物理接管的替代依赖恢复动作能力；极端不可恢复状态仍需要外部处理。这样才能判断 Harness 实际减少的是哪一部分人工，而不是把人工转移到未计费的标定、标注和恢复开发阶段。
