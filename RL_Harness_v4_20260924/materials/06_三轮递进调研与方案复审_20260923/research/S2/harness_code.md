# S2 Harness 源码与数据链：从执行事实到可学监督

2026-09-23。仅进行官方文本、固定源码与少量公开日志的静态审计；没有安装第三方、运行候选测试、训练模型或操作机器人。已读取会话 AGENTS、科学家 START_HERE／ROLE／status／INDEX、本轮契约、S1 根审入口与 Harness 报告；科学家库及旧 02–05 只读。本报告不构成五轮方案评审中的一轮。访问、失败与阅读范围见 [harness_code_log.json](harness_code_log.json)，原文快照见 [evidence/harness](evidence/harness)。

**结论：目前最有价值的是把 PhyAgentOS 的持久化 intent／绑定／对账机制和 Harness-Zero 的原生动作监督边界纳入统一 Gateway 路线；没有足够证据要求立即替换 RPent。AGP 当前公开数据不能作为本项目低层异步 VLA BC／TD 的现成数据源——连续关节、动作日志和帧时钟对齐已经撤下。** 程序、记忆和运行可靠性仅是产生有效练习与可信监督的手段，最终收益仍须用关闭 GPT Harness 临场辅助后的同一双向 deployment policy 检验。该 policy 可以包含预先声明、已训练的 learned editor／Q；base 冻结不等于没有 policy 学习。

## 1. 从 S1 待核机制出发

S1 已把认知工具、物理运行、评分、程序积累和参数学习分开，发现 Forge 的 execution/evidence/verdict 边界、AGP 的混合标签来源、SAGE 与 Harness-Zero 的教师退出机制。本轮不重复候选排名，提出以下新问题：

1. Forge 的 agent 工具究竟调用哪些函数和 HTTP 路由？intent 在运动前还是后落盘？取消请求何时成为终态？未知执行是否能跨 task 被重复派发？
2. 一任务槽、endpoint 并发和资源独占是否同一件事？before/after 的“新”按采集时间还是接收时间判定？SQLite 是否同时承诺物理动作和图像的事务性？
3. AGP 的标签、bridge 请求、stdout 响应、图像与关节数据实际如何连接？当前发布了哪些字段，哪些旧资产已经撤下？是否存在可以立即投入低层 BC／TD 的连续动作窗口？
4. Harness-Zero 的 REPLACE 是否真的进入执行，再成为学生 loss？是否只训练纠正步、是否保留失败、预算耗尽和教师私有信息如何处理？
5. SAGE 是否已有训练文件，GPT-Policy 是否已有许可？如果没有，就停止把它们当现成实现基座。

## 2. 版本和实际读取范围

| 对象 | 固定身份 | 本轮实际读取，不等于全库审计 |
|---|---|---|
| PhyAgentOS-core | `90ac3f22b20aa25dbcc4e3a4333df8c1747af95c`；commit API 与递归 tree 同 SHA，tree 未截断 | agent Forge 工具、HTTP client；task 的派发／取消／对账／终结／SQLite；binding 校验；observation 新鲜度；evidence 文件写入；框架与接口文档、pyproject、LICENSE |
| AGP GitHub | `c6875d0457358dd54dd23f61355d21149d63ca64`；commit 与 tree 同 SHA | `build_trials_table.py` 的 codex_steps／claude_steps／assemble／schema；`export_actions.py`；agent server 的 frames／move；硬件 server 的 dispatch 和 motion 的日志／feedback；许可证、依赖声明 |
| AGP HF | 当前分支头页面为 `c7ec31dd37b206cb2fa0e3952346c67f77aad41d` | LABELS 正文、SCHEMA 相关字段与 known issues；两个真实 trace 的指定片段。直连下载与 API 失败；固定 revision 文件页也失败，因此正文保留为访问时 `main` 的网页证据，**未声称已取得与该 SHA 逐字节核对的完整数据快照** |
| Harness-Zero | `aa63a7751997969c2880896f9df3098c7f650fe2`；commit 与完整 tree 同 SHA | rollout 构造、harness build_graph、student review／execute、ReviewSubmission、TrialStore、dataset_utils、sft、train；README／LICENSE。Harbor 后端、pyproject 与 data README 补读下载失败，因此实际执行链止于 backend.aexecute 调用边界，依赖只确认已读 imports／README，详见日志 |
| SAGE | `d0888cf2cf789b18dbba718509928f198680a9b7` | 完整 tree 只有 LICENSE，MIT 正文；没有可读训练文件 |
| GPT-Policy | `ab970d88bc5570d80a7b4f3e8d3ad97ebe65a007` | 固定 README，仍写 license pending；不继续作代码复用审计 |

固定源码链接：[Phy][phy]、[AGP][agp]、[Harness-Zero][hz]、[SAGE][sage]、[GPT-Policy][gpt]；HF 身份入口：[commit 页面][hfhead]。下载成功只表示取得文件；日志逐项列出实际阅读函数，没有把 tree 中的全部文件算作已读。

## 3. PhyAgentOS：可审到 HTTP 边界，不能跨越独立节点资产

### 3.1 可读调用链

```text
ForgeToolStartActionTool.execute(task_id, tool_id, arguments)
  → AgentTaskCoordinator.start_action
    → _require_executable + _require_binding_tool
    → _capture_before（错误记账，非硬阻断）
    → _append_execution → SQLite intent + caller_id
    → ForgeToolClient.invoke_action → POST /tools/{tool_id}:invoke
       [此处进入独立发布 Gateway；core 不含其 Endpoint/Dora/机器人实现]
    ← HTTP 202 + invocation_id + attempt_id
    → action_accepted + runtime identity tracking

status/result 工具 → GET /invocations/{id}[/result]
  → observe_action → ToolExecutionRecord + SQLite event
cancel 工具 → POST /invocations/{id}/cancel
  → record_cancel_response（不改成 cancelled）
finalize_task → 核 owned invocation 已到 accounting terminal
  → _capture_after → 文件证据 bundle → SQLite 引用
  → off/audit/enforce/recovery → task verdict
```

Query 先检查 `semantics=query` 并解析 endpoint／operation，再走 `/tools/{endpoint}/{operation}:invoke`，同步要求 HTTP 200。Action 要求 202；Session 使用相同 admission，停止走 `/invocations/{id}/stop`。这里所谓 RPC 是 HTTP 工具调用；没有将旧论文的 Markdown Session Runtime 拼进当前 Forge。[工具入口][phytools]、[HTTP client][phyclient]、[协调器][phytask]

core 的递归文件树没有 Gateway server、ToolEndpoint、Dora 执行节点或具体硬件驱动实现；官方文档也明确具体 skills、nodes、models、simulator assets 分开发行。所以本轮**实际源码链到 HTTP 客户端及其本地返回处理为止**。Gateway 路由、endpoint `max_concurrency` 和机器人终止报告在这里是外部接口合同，不能宣称已经查到驱动 stop_ack、硬件实际停止或其并发实现。[发布边界][phycontract]

### 3.2 派发、未知状态与取消

- `_append_execution` 先经 `store.update` 写 intent、`record_id`、独立 `caller_id` 和冻结 ToolSpec hash；然后才 POST。返回的 invocation／attempt 另存，不与 task／revision ID 混用。异常中能找到远端身份时也保留它。对 RPent 数据桥有直接参考价值。
- `start_action` 在**同一个 task** 内发现相同 tool＋arguments 已是 unknown 时拒绝重发；`reconcile_nonterminal` 用 GET 修复没有终结的 invocation，不重新 POST。没有 invocation ID 的遗留 intent 被记为 unknown，不能推断它没动过。
- `cancel_invocation` 接受 HTTP 200／202；`record_cancel_response` 只改 response 和 updated_at。`cancel_task` 请求取消 Action、停止 task-owned Session，再进入 CANCELLING；shared/runtime Session 不自动成为该任务可停止的对象。只有后续终态对账才能完成取消。[task 575–711、827–985、1015–1063][phytask]

**必须保留的静态边界：**`unknown` 本身在 `TERMINAL_TOOL_STATUSES` 中，是账务终结而非物理静止；自动 `reconcile_nonterminal` 会跳过该记录。任务终结后 `observe_action` 直接返回；已读路径不是永久恢复 unknown 的总账服务。相同请求防重规则也不是跨 task、跨进程、跨不同 tool 的硬件幂等。接入后应保留未知物理效果并由全局 Gateway 对账，不能因局部 task 已失败就恢复运动权限。这是源码推断，未注入崩溃或丢 ACK 验证。

还有一个应进入 S3 的具体反例：`observe_action` 检查 task.terminal，却没有检查已有 **record.terminal**；随后把 `_tool_status(response)` 直接写回。若 task 尚活跃，晚到 running 响应可能覆盖已记录 succeeded。官方“终态执行事实不被改写”的说明因此不能只凭当前函数接受为已实现的本地单调性保证；需核网关是否排除此序列，或补本地版本／状态守卫。**本轮没有运行并复现该问题。**[状态更新函数][phytask]

### 3.3 跨工具 lease：确实不是 core 已实现能力

`AgentTaskStore.create` 通过 WAL＋`BEGIN IMMEDIATE` 在该 workspace SQLite 中只允许一个非终态任务。`binding.py` 冻结并检查 runtime 实例、skill／manifest、ToolSpec hash、readiness 与成员关系。这些能避免错误版本调用，不能阻止同一 task 的两个不同工具争用同一机械臂，更不能约束另一个 workspace 或直连驱动程序。[SQLite／绑定][phytask]、[binding][phybinding]

官方明确未增加跨 Tool Resource／Control lease；已读 `start_action` 没有资源集合、owner epoch、全局 acquire/release 或同资源冲突检查。endpoint 的 `max_concurrency` 只属于被选 operation 的约束。结论限定于 core 与该合同：**没有证据表明整体外部节点系统已拥有跨工具独占；也不能从未取得的 Gateway 源码断言所有外部节点均不存在任何锁。** 对本项目仍需唯一物理 Gateway、资源 owner／epoch、全路径 reset／恢复／trial 统一仲裁。[官方合同 §1][phycontract]

### 3.4 observations／SQLite／“receipt”的准确含义

`_capture_before` 捕获异常并将错误入账，`start_action` 继续；before 引用仍空时下一动作可再次尝试。`_capture_after` 在 finalize 时执行，围绕整个 bound task 收集前后证据，**不是每个控制帧的连续 recorder**。当前 latest buffer 只保留每个图源的最新消息。[协调器 capture 方法][phytask]

`ForgeObservationCollector._ready` 对 after 图像要求 seq 大于 before 且本机 `received_at ≥ terminal_observed_at`；state 也用 received_at。图像原 `timestamp` 可为空，只检查有限值；不以跨设备采集时钟校正或图像／关节最大偏差作为 ready 条件。迟到的旧采集帧在本机较晚到达，不能单凭这两个条件证明它展示的是动作后的实体状态。sequence 回退、传感器重启和跨源同步也需单独定义。[observation.py 120–230、261–313][phyobs]

`ForgeEvidenceWriter` 原子写图像／状态文件、snapshot manifest，再写 bundle；artifact 带内容摘要、大小、路径、源和时间信息。SQLite 保存 task JSON 与 event 在同一事务内；**文件写入与 SQLite 引用是分步完成，远端动作更不在该事务中**。这比无来源截图更可审，但不是动作、图像、控制帧和 learner replay 的分布式原子提交。[evidence.py][phyevidence]、[store 184–281][phytask]

在此链中可确认的是 Gateway response／invocation reference 与 `ToolExecutionRecord`，不是本项目要求的逐帧物理 receipt（admission、commit、activation、真实索引、owner epoch、部分生效、实测反馈）。任务 succeeded 在 `off` 与 `audit` 可由执行状态决定；不得直接映射为抓放 success reward。`enforce/recovery` 增加语义裁决，也没有自动建立独立真值。

## 4. 与 RPent／OpenETA 按同一责任比较

下表旧两列继承旧固定源码审计，不冒充本轮重审它们的全部 HEAD。RPent 原详审为 `eb269c8…`，04 已补读 `6ee706935d28646828f70372ef0099c769cfe0c2` 的选定变化；OpenETA 为 `7d4a0a1522ba8ebbd362bde880bad81d2a98f15e`。[RPent 历史审计](../../../03_RL_Harness自主学习系统_20260922/09_RPent与Harness联合选型.md)、[OpenETA 固定源码审计](../../../04_RL与Harness扩展调研_20260923/reviews/R05/openeta_source_check.md)

| 同功能责任 | RPent 历史固定路径 | OpenETA 固定路径 | 本轮 Phy Forge | 本项目必须保留的责任 |
|---|---|---|---|---|
| 工具接纳／上下文 | API Toolkit 工具注册；实例 active-operation | Host 检查新观测义务、compile tool | 冻结 binding；POST 前持久 intent | 最新 goal、观测和版本；动作只提交到一个物理 owner |
| 长动作期间观察 | sequential／活动工具锁会影响只读观察 | 每轮等待工具线程后更新；不是独立高频 observer | 独立 WS collector，但实际 task capture 是前后快照 | 持续只读观察服务，不被动作锁堵塞 |
| 取消 | 合作式取消并等工具返回 | abandoned 不会杀执行线程 | 取消请求与终态分开，GET 对账 | quiesce、清队列、驱动保持／停止回执；取消 Python 不算停机 |
| 资源控制 | 同一 Toolkit 实例锁 | runtime／handler 软件边界 | 单 task SQLite 与单 operation 并发合同 | 资源集合／owner epoch／跨进程与跨 tool 排他 |
| 崩溃与派发 | 需追加式事实 journal | rollout 尽力记录 | intent、remote ID 和 task event 持久化更明确 | 未知执行不盲重发；账务失败不释放未知物理控制 |
| 动作学习数据 | EpisodeWriter 有 N 动作＋N+1 观察，提案另存；默认成功前缀 SFT、真机待扩展 | 工具级 rollout／timeline replay | 调用级 execution 与 task before/after | 真正执行动作、异步 request/commit/activation、goal、奖励、BC/TD资格和不同 mask |
| 程序与经验 | 任务卡／Flash／memory | skills／失败记录／候选晋级 | 绑定版本的 lesson／skill evolution | 程序收益必须转为学生可表示的纠正与有效练习，再测独立 policy |

Phy 的持久意图和版本绑定可以改善 RPent／统一 Gateway 方案；其前后观测并不比 RPent 原生逐步 EpisodeWriter 更接近低层 learner。现阶段适合**借机制或做同预算骨架预检**，不足以凭“Gateway”名称整体换底座。三个骨架都需本项目的数据、控制和学习契约，不能让新框架引入第二硬件写通道。

## 5. AGP：公开执行资料与低层训练数据是两类资产

### 5.1 当前字段与标签

HF 当前表是一行一次 trial；`labeling.source` 与 `labeling.agent_self_report` 分列；`timing` 是会话级秒数；`traces[]` 的每步含 item_id／kind／command／output／exit_code／calls，call 中有 arm／cmd_id／cmd／args_json／ok／capture_index／pose_json。`ok` 表示桥接命令报告，并不等于任务成功。

LABELS 的 162 条 scored trial 中，66 条 source 为 astra_self，57 paper_code、16 results_csv、10 claude_review、10 operator_review、3 timed_out。非自述来源也不全是盲评真值：超时是规则，其他多为单评者事后静态照片；operator_review 是最清楚的独立再判来源，不应只因命名就视作完美标签。抛掷批次曾把否定表达正则误判成成功，后用照片纠正；保留 self_report 与 outcome 的冲突。**我们没有重判这些图像、复算全量 parquet 或验证作者成功率。**[LABELS][labels]

### 5.2 导出链实际做了什么

```text
agent stdout／原始 transcript + bridge 请求记录 + capture metadata
  → build_trials_table.codex_steps：从顶层桥接 JSON 回复取 id 对请求
  或 claude_steps：按 wall-clock 窗口把请求归入 Bash 步
  → assemble：附加 pose_json／depth_url、截断 command/output
  → nested traces[] + trial outcome/labeling
```

`codex_steps` 不靠命令里是否出现 robot_client 来识别调用，避免漏掉包装脚本；双臂有 arm 与 positional／capture-path／id consistency 的归属规则。`claude_steps` 用工具结果结束时间，缺失时退到下一工具开始甚至无穷上界，把请求逐一归属；这是重建，不是严格因果 request ID 链。`assemble` 把 command/output 截到 2,000 字符并保留首尾，仅 output 有专用截断标志；完整 transcript 另放 JSONL。[固定 builder][agpbuilder]

官方说明 23,657 个记录请求中 352 个未附着到 transcript 步；不能称其“没有物理执行”。双臂的右桥完整记录未发布，部分 call 只有真实 stdout 回答、没有对应 cmd_id／cmd。未知及推断关联必须单独标志，不能用相邻 index 补齐后把它当完整动作窗口。[SCHEMA][schema]

### 5.3 实读两个样本，不推成全量验证

1. `20260905_000316_scatter_tools1_02`（reset 类日志）：读 item_3 status、item_4 state、item_5 frames、item_7 校准文件及后续几何检查。`frames` 返回 capture=1/id=3；校准原文同时出现 wrist／top 的 `frame_wall_time_ns` 与 age_s、机器人 `_meta.wall_time_ns`／sequence／joints。两相机帧时间相差约 12.3 ms，所以注释“ONE observation”不等于传感器严格同一曝光时刻。该样本是读场景／核对已有布局的资料，不假装它提供了运动示范。[真实 reset trace][sample_reset]
2. `20260904_150034_paper_pyramid_01`：读 item_35 frames/capture=3/id=24 → item_36 gripper close/id=25 → item_37 frames/capture=4/id=26 → item_38 move_delta/id=27，以及 item_43 的 move_ee/id=31。最后一项目标位置 `(0.300, 0.070, -0.009)`，回复 achieved pose 约 `(0.29575, 0.06934, -0.01155)`、target_error_mm=5.0、duration_s=8.4、bridge_status=completed。这说明**请求目标与实测落点确实不同且可分别读出**；不能将目标轨迹直接当真实执行数组。[真实 scored trace][sample_trial]

这些样本是网页正文中的 JSONL 片段；没有下载视频、解码图像、完整重放 episode。它们足以核字段和不等价关系，不足以判断动作质量或自动批准为专家 BC。

### 5.4 S1→S2 的重要修正：连续动作资产已经撤下

当前官方 SCHEMA 的 known issue 15 明确：2026-09-15 已撤下原 `sessions/<session_id>/{joints,alignment,actions}.parquet` 和 `actions/actions_<arm>-b01.parquet`，不再发布 50 Hz 关节轨迹、视频帧时钟对齐和原始 action events。保留的是采图时稀疏 pose_json。**旧卡片或论文草稿的连续样本数量不能再写作当前可下载资产。**[当前 SCHEMA，issue 15][schema]

这与代码并不矛盾：`MotionController._execute_joint_trajectory` 会写 command＋feedback 事件，`_log` 写 wall_time_ns 和 monotonic_ns；仓库也仍有 `export_actions.py`。但“有记录／导出代码”不证明相应数据当前已发布。且该 export 只选 arm、event、request_id、两个时间和 action_json；反馈事件中的 command／feedback 不自动成为这份导出的完整固定维数组。[motion 411、473 起][agpmotion]、[export_actions][agpactions]

`server_real.cmd_frames` 保存每相机时间／校准以及机器人状态；`_move_common` 把目标从 world 变到本臂 base，检查约束后执行，读取结果与 achieved pose，SETTLE_MISS 作为失败返回。读到的是当前软件机制，不能自动视作每条历史日志都由该固定版本产生；历史采集版本还需单独绑定。[当前动作与采图实现][agpserver]

### 5.5 BC／TD 资格判断

| 用途 | 当前可支持什么 | 仍缺什么 |
|---|---|---|
| agent／工具级监督 | 原生命令、上下文、部分响应和程序材料可形成候选；筛掉缺响应与推断关联，单独标注质量 | 学生输入必须只含当时可见观测；teacher 的后看反馈／外部目标信息须可追踪 |
| 本项目低层 VLA BC | 可参考格式和数据生成工具；**不能直接宣称可导出完整控制 chunk** | 已撤下的低层动作／反馈及时间对齐；本体、动作模式、频率、校准与原始图像映射；纠正质量审核 |
| 本项目异步 TD | **当前发布不能直接满足** | 事前请求状态、队列、commit／activation、逐步真实动作和后继、终止／奖励版本、目标与来源；末态成功标签不能补造它们 |

尤其不能拿 move_ee 目标配 achieved pose 倒推一条假控制轨迹，不能拿一个拍照时的关节状态向前／向后填满 50 Hz，更不能把缺响应当动作未执行。GitHub 工具可作为未来重新采集的参考；复用时还要经过统一 Gateway，不能与 learner 的硬件通道并存。

## 6. Harness-Zero：REPLACE→execute→正例 SFT 已有具体链

```text
rollout.build_rollout_command → Harbor Docker / HarnessZeroMinisweAgent
  → build_graph → create_supervised_miniswe
  → HarnessReviewMiddleware.awrap_model_call
    保存真实 model request + original candidate
    → Reviewer 返回 PASS 或完整 REPLACE（candidate_id 校验）
    → accepted AssistantResponse → append_review
    → LangChain agent 接受该 message → execute_tool → backend.aexecute
    → 工具输出/exit_code 回到下一轮 context
  → trial result 的 verifier reward
  → build_sft_file：reward≥阈值且无异常
  → conversation_messages：学生上下文 + accepted response
  → prepare_datums：assistant token weights／显式 masks
  → Tinker forward_backward(cross_entropy) + optim_step
```

`ReviewSubmission` 强制 PASS 不含 replacement、REPLACE 必含完整可用 response；`ExecuteCall` 只允许学生原生 `execute(command)`。`student.py` 接受 original 或 replacement 后才把它返回到 agent 工具执行路径；`execute_tool` 调 backend 并返回 stdout＋exit_code。因此不是仅向学生展示教师点评。[review][hzreview]、[student][hzstudent]、[harness][hzharness]

`TrialStore.append_review` 保存 original／review／accepted；注意它发生在执行前，**accepted 记录本身不是执行回执**。后续上下文、工具结果与环境 verifier 才补上执行信息。这一边界迁移到机器人时尤其重要：必须另接物理 receipt。[store][hzstore]

`build_sft_file` 默认 reward_threshold=1.0，跳过缺结果、低 reward、exception 或空轨迹；用最后一条 event 的完整学生上下文加最后 accepted response 构建一次 session。它训练的不只是 REPLACE 动作，而是成功轨迹中的助手消息；失败轨迹不会因为有局部优质纠正自动进入默认 SFT。[sft][hzsft]、[dataset_utils][hzdata]

`prepare_datums` 默认 `ALL_ASSISTANT_MESSAGES`，可传整条助手消息 mask；REPLACE 推理中若匹配审阅泄漏措辞，就把该 reasoning span 的 loss weight 置零，保持动作／其他目标可训练。它检查 token／mask 长度与 scoped target 一致，并记录内容／mask 摘要；超长整条会跳过。**loss mask 不等于把泄漏 reasoning 从后续上下文删除**：该 token 仍留在输入／历史；PRIVATE_MARKERS 只是指定字符串／正则检查，不是通用无泄漏证明。这是具身迁移前需要额外验证的条件。[train.py 28–176][hztrain]、[dataset_utils][hzdata]

`train_positive_sft` 用 Tinker 服务创建 LoRA client，cross_entropy＋Adam，保存训练 state 与 sampler weights；需要 `TM_API_KEY` 与服务可用性。它没有此链上的机器人 TD／Q replay，不能把保存 state 命名成已满足本项目的完整双向发布包。[训练入口][hztrain]

两个会影响弱起点的限制来自当前源码而非抽象猜测：①纠正预算耗尽时直接 PASS，reason 明写未经 review；故 PASS 不总表示教师认可。②无任何成功轨迹达到阈值时，默认构建器没有训练样本。教师可以帮助产生成功，但代码不保证从零成功起点必然得到它。机器人方案需要保留经局部资格检查的 BC 标签与真实失败 TD，不能照搬整回合成功过滤。[student.py 173 起][hzstudent]、[sft][hzsft]

**迁移结论：**可借鉴“教师只返回学生动作接口可表达的纠正”“原提案与 accepted 分存”“部署时教师退出”；软件 execute 字符串的 CE、Harbor reward、whole-session filtering 不直接适用于连续动作、异步队列、flow mask 或真实物理奖励。这里没有机器人实验，本项目也没有复现论文指标。

## 7. 开放资产与未采用支线

| 候选 | 开放代码 | 权重 | 数据 | 依赖与许可 | 本轮作用 |
|---|---|---|---|---|---|
| Phy core | 上述固定 Python 源码可读；Gateway／具体 node 不在 core | 未取得所需具体策略权重 | 没有核到本任务训练集 | core MIT；Python≥3.11，HTTP/WS 等多项范围依赖；官方 Dora CLI 0.4.1＋dora-message 0.7.0；外部 artifact 逐包核许可 | intent、版本绑定、对账和证据机制候选；不是 learner |
| AGP | agent、硬件 bridge、导出与分析代码 | 冻结外部模型服务，不是所需 VLA 权重发行 | HF CC-BY-4.0；当前 sparse trace／image／video，连续动作／对齐已撤下 | 主仓 Apache-2.0；NOTICE 区分 graph-as-policy 与 i2rt MIT；NumPy/SciPy/OpenCV/RealSense 等外部依赖另核 | 工具教师、记录机制和监督边界参考 |
| Harness-Zero | 审阅／执行／SFT／训练代码可读 | README 链接 3 个 Qwen3.5-9B 蒸馏权重；S1 已读 AppWorld Apache-2.0 卡；本轮卡页重试失败，未下载权重 | 仓库 benchmark task 集存在；没有据此断言完整审阅 rollout 数据均已公开 | 主仓 Apache-2.0；Harbor Docker、LangChain／DeepAgents、Tinker recipe／服务；依赖及任务数据不因主仓许可自动统一 | 学习桥机制与静态实现参考 |
| SAGE | 当前递归 tree **只有 LICENSE** | 未核到 | 未核到 | MIT 文件不等于训练资产齐备 | 只保留 S1 论文机制依据，不能当现成 PPO／BC 栈 |
| GPT-Policy | 公开预览 | 未核到独立训练权重 | README 明示部分私有资产不提供 | 固定 README 仍 license pending，并明确预览未授予再分发／商业使用；许可未解决前不纳入代码复用 | 只保留方法与接口参考 |

许可证是项目公开文件的记录，不是对组合部署的法律结论。[Phy pyproject][phydep]、[AGP NOTICE][agpnotice]、[AGP bridge pyproject][agpdep]、[Harness-Zero README][hzreadme]、[SAGE tree][sage]、[GPT 固定 README][gpt]

ROSClaw／RAI／dora 本轮不展开新底座：Forge 的物理节点断点不能用另一仓库的 lease 或最新 dora 文档填补，RAI 的时间戳 PR 也不能冒充已装依赖语义。它们保留 S1 角色与待核范围；如果 S3 发现唯一 Gateway 的必要机制仍无实现候选，再定向读其一个调用链。未重新核 stars、下载量或引用量，不拿关注度决定可靠性。

## 8. 交给 S3 的反例与决策问题

1. **跨工具同资源：**同 task 向两个 ToolId 下发同一机械臂动作；另开 workspace／外部 SDK 同时写。endpoint 并发＋单 task SQLite 能否阻止？若不能，只有统一物理 owner 才能补齐。
2. **unknown 跨 task：**POST 已生效但 ACK 丢失，task 被 unknown 终结后新 task 以同参数重发。如何持续保留未决物理身份，何时才允许复位／重试？
3. **乱序终态：**succeeded 后收到旧 running；晚到 cancel 接纳不得改变实体事实，晚到 verdict 不得恢复旧 goal 动作权限。比较上游约束与本地单调更新责任。
4. **接收新、采集旧：**after WS 帧 seq 递增但曝光在动作前，或传感器重启导致 seq 回退。哪些 capture 时间、时钟误差、控制索引使它可评分／可学？
5. **持久化分叉：**intent 已写／图像文件已写而 SQLite 引用未写，或物理动作已生效而 response 未到；不能因仓库写“crash-safe”直接通过本项目因果账本门禁。
6. **成功轨迹误授监督：**AGP 自述成功、某个桥接 ok、Harness-Zero 整回合成功都不能统一解锁每个动作的 BC。什么局部证据、输入资格和反事实检查决定监督 mask？
7. **纠正后看信息：**教师逐帧改动作，或 reasoning 虽 mask 但仍作为后续输入；不能拼成学生在初始观察下可生成的完整 chunk。应如何筛窗口／分步监督／保留特权信息来源？
8. **零成功与干预退出：**正例过滤没有样本时如何积累有效练习；程序越来越强却 policy 独立能力不增时如何暴露？比较独立 policy、辅助系统、加纠正 BC/RL 三种条件，并记录干预动作占比、来源分层和完整任务双向成功。

当前取舍保持：**一套认知骨架＋只提交意图的纠正工具＋唯一物理 Gateway＋独立事实账本／学习视图＋共享双向 learner**。Phy 增加可复用运行机制，Harness-Zero 增加具体监督链，AGP 则揭示当前资产不足；三者都不能替代“完整 deployment policy 的参数确实学会且 GPT 教师退出后仍稳定”的实证。若学习只发生在已声明 editor／Q，也属于 policy 学习，应报告其参数、输入与推理预算，并与未学习版本同条件比较。

[phy]: https://github.com/PhyAgentOS/PhyAgentOS-core/tree/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c
[phytools]: https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/PhyAgentOS/agent/tools/forge_tool_api.py
[phyclient]: https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/PhyAgentOS/forge/tool_client.py
[phytask]: https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/PhyAgentOS/forge/task.py
[phybinding]: https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/PhyAgentOS/forge/binding.py
[phyobs]: https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/PhyAgentOS/forge/observation.py
[phyevidence]: https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/PhyAgentOS/forge/evidence.py
[phycontract]: https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/docs/forge/README.md
[phydep]: https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/pyproject.toml
[agp]: https://github.com/agent-as-policy-2026/agent-as-policy/tree/c6875d0457358dd54dd23f61355d21149d63ca64
[agpbuilder]: https://github.com/agent-as-policy-2026/agent-as-policy/blob/c6875d0457358dd54dd23f61355d21149d63ca64/scripts/build_trials_table.py
[agpactions]: https://github.com/agent-as-policy-2026/agent-as-policy/blob/c6875d0457358dd54dd23f61355d21149d63ca64/scripts/export_actions.py
[agpmotion]: https://github.com/agent-as-policy-2026/agent-as-policy/blob/c6875d0457358dd54dd23f61355d21149d63ca64/hardware-bridge/src/agp_yam_bridge/motion.py
[agpserver]: https://github.com/agent-as-policy-2026/agent-as-policy/blob/c6875d0457358dd54dd23f61355d21149d63ca64/agp/server_real.py
[agpnotice]: https://github.com/agent-as-policy-2026/agent-as-policy/blob/c6875d0457358dd54dd23f61355d21149d63ca64/NOTICE
[agpdep]: https://github.com/agent-as-policy-2026/agent-as-policy/blob/c6875d0457358dd54dd23f61355d21149d63ca64/hardware-bridge/pyproject.toml
[hfhead]: https://huggingface.co/datasets/Agent-as-Policy/agent-as-policy/commit/c7ec31dd37b206cb2fa0e3952346c67f77aad41d
[labels]: https://huggingface.co/datasets/Agent-as-Policy/agent-as-policy/blob/main/docs/LABELS.md
[schema]: https://huggingface.co/datasets/Agent-as-Policy/agent-as-policy/blob/main/docs/SCHEMA.md
[sample_reset]: https://huggingface.co/datasets/Agent-as-Policy/agent-as-policy/blob/main/traces/20260905_000316_scatter_tools1_02.jsonl
[sample_trial]: https://huggingface.co/datasets/Agent-as-Policy/agent-as-policy/blob/main/traces/20260904_150034_paper_pyramid_01.jsonl
[hz]: https://github.com/metaevo-ai/harness-zero/tree/aa63a7751997969c2880896f9df3098c7f650fe2
[hzreadme]: https://github.com/metaevo-ai/harness-zero/blob/aa63a7751997969c2880896f9df3098c7f650fe2/README.md
[hzharness]: https://github.com/metaevo-ai/harness-zero/blob/aa63a7751997969c2880896f9df3098c7f650fe2/src/harness_zero/harness.py
[hzreview]: https://github.com/metaevo-ai/harness-zero/blob/aa63a7751997969c2880896f9df3098c7f650fe2/src/harness_zero/review.py
[hzstudent]: https://github.com/metaevo-ai/harness-zero/blob/aa63a7751997969c2880896f9df3098c7f650fe2/src/harness_zero/student.py
[hzstore]: https://github.com/metaevo-ai/harness-zero/blob/aa63a7751997969c2880896f9df3098c7f650fe2/src/harness_zero/store.py
[hzdata]: https://github.com/metaevo-ai/harness-zero/blob/aa63a7751997969c2880896f9df3098c7f650fe2/src/harness_zero/dataset_utils.py
[hzsft]: https://github.com/metaevo-ai/harness-zero/blob/aa63a7751997969c2880896f9df3098c7f650fe2/src/harness_zero/sft.py
[hztrain]: https://github.com/metaevo-ai/harness-zero/blob/aa63a7751997969c2880896f9df3098c7f650fe2/src/harness_zero/train.py
[sage]: https://github.com/giobin/SAGE/tree/d0888cf2cf789b18dbba718509928f198680a9b7
[gpt]: https://github.com/cheng-haha/GPT-Policy/blob/ab970d88bc5570d80a7b4f3e8d3ad97ebe65a007/README.md
