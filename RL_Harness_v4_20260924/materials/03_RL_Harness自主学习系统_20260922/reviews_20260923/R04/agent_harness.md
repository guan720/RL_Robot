# R04 独立审查：RPent／GPT Harness 运行闭环

审查日期：2026-09-23。结论：**PASS（设计审查）**。实际审查 **16 个反例问题，发现必须修改项 0 项**。这不表示 RPent 已接入、本工位试验已通过或无人在线 RL 已实现。

只以本轮 `input/` 的 01、02、06、07、09、README 六份冻结稿为审阅对象，重点核验 01／02／09；未读取其他轮或其他审查员结论。原始依据独立打开 RPent 论文 v4、官方文档及固定源码，并读取指定本地固定快照。未安装 RPent、调用机器人或测试模型。本次只写本报告。

## 先枚举决定闭环是否成立的技术点

1. GPT 的图像／工具接口能力，与工位上成功判断、异常识别和纠正能力分开。
2. 长 motion、同步预测或卡死期间仍有新鲜只读观察流；不能被同一 Toolkit 活动锁阻塞。
3. 设备唯一 Gateway、跨 session／进程的独占控制代际，与进程内工具互斥分开。
4. 取消请求、工具返回和设备达到可交接保持状态分开；未知执行不能授权新 owner。
5. 历史评分、历史纠正标签、当前控制候选分别校验；缓存包含目标与证据身份。
6. unknown／超时不转成零分或旧成功分；成功事件去重，评分要独立校准。
7. 生成程序从候选到 TRIAL、回归、发布有明确权限边界，记忆 verified 不能授予运动能力。
8. Flywheel 的实际动作、提案与成功 SFT 导出有用，但失败 RL、查询纠正、双目标和断电持久化需扩充。
9. 目标要进入真实 VLA 输入和 Q／replay，而非只改 planner 日志。
10. 人工 verdict／scene reset 要被可审计的自动判断和物理流程替换；不以自动返回成功代替。
11. Harness 动作必须按真实时间及信息集进入 BC／RL；局部反馈动作不能伪造整段预先决策。
12. 完整抓放 policy、Harness 辅助系统、自主学习成本分别评估；RPent 优先级依据适配度而非机构、时间或星数。

## 本轮独立证据与逐行源码核对

RPent 固定代码统一为 `eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1`。下列行号是源码行号，非网页排版行号。前三条即已满足三个关键路径逐行核查，本轮实际核查更多。

| 编号 | 独立打开／逐行核查的来源 | 直接观察 |
|---|---|---|
| S1 | [Toolkit 固定源码][toolkit]，L198–199、257–326、351–365 | 实例内 `threading.Lock`；检查 active operation 先于 readonly 分支；取消发 event 后无期限等 done，不含驱动停稳证明 |
| S2 | [API planner 固定源码][api]，L719–738、763–781、820–855 | 图像转 BinaryContent；工具注册 `sequential=True`；调用最终进入同一 Toolkit |
| S3 | [Flywheel export 固定源码][export]，L49–86、112–142 | 筛 successful finalized episode；多种 task_language 直接报错；输出到首次成功前缀；重载检查帧数 |
| S4 | [EpisodeWriter 固定源码][episode]，L47–52、82–93、106–145、147–214 | 内存列表保存动作／观测／标签；提案另存；finalize 才写 NPZ、校验和改名；action_source 按 VLA ID 二分 |
| S5 | [双 Franka Toolkit 固定源码][dual-toolkit]，L270–346、348–367、426–433 | 人工恢复确认、人工 verdict、finish guard、solved 的真实判断链；不是仅存在工具名称 |
| S6 | [双 Franka tools 固定源码][dual-tools]，L465–540 | requested_prompt 留存而 effective_prompt 来自固定指令；赋 task_descriptions 后同步 predict，再逐动作检查取消及调用 chunk_step。本地缺该文件，本轮独立从固定 raw URL 获取到内存逐行核查，未新增快照 |
| S7 | [双 Franka env_server 固定源码][dual-env]，L1134–1160 | 循环读取 `_reward`，返回只含 observation、terminal／truncated 与最后 info；不能把该返回当逐帧奖励记录 |
| S8 | [Codex planner 固定源码][codex]，L112–123、192–198；[MemoryManager 固定源码][memory]，L96–119 | 主运行设置 full_access／deny_all；超时路径也会等待工具取消；记忆 verified 由 cell／task 数量条件生成 |
| S9 | [RPent 论文 v4][paper]，§2.1–2.3、§5 | 冻结 VLA、固定原语、回合式工具反馈和记忆学习；局部接触之外的运输等由 planner 组织；没有环境奖励联合微调的现成闭环 |
| S10 | [官方架构][architecture]、[Planner 文档][planner-doc]、[Flywheel 文档][flywheel-doc]、[双 Franka 文档][dual-doc] | 可换 planner、Responses 路径、LIBERO evaluation 采集及外部 SFT、特定工位 checkpoint 泛化限制。文档是访问时的 latest，源码结论以固定 SHA 为准 |
| S11 | [OpenAI Docs：GPT-6 Astra][astra]、[Function calling][function] | 图像输入、工具调用、结构化输出可用；不支持原生视频输入；Astra 工具调用要求 Responses。应用负责实际执行工具，模型接口不赋予设备停止或场景判断保证 |
| S12 | [ENPIRE 固定奖励源码][enpire]，`_cached_reward`、缺图像／限频／异常返回分支 | 缓存是全局旧 reward；确实存在跨目标复用风险，不是仅靠框架名称推断 |
| S13 | [RoboRSI 固定 RL 入口][roborsi-code]及[官方博客][roborsi-blog] §03.D | 该 RL 入口 run 抛 NotImplementedError；博客同时有纠正轨迹微调实例。因此只能说特定入口未实现，不能说项目不存在参数学习 |

## 16 个反例问答

### Q1：将 GPT-6 换进 planner，是否就证明它能持续看视频并准确判定抓放？

**证据：**S2、S10、S11。Astra 支持图像输入，工具要用 Responses；RPent 的图像接入代码可复用，但模型能力页不提供本工位判定结果。

**冻结位置：**01 L112–116；02 L54、152–163、185–191；09 L30。

**反例：**请求通过了 schema 检查，模型却把夹爪遮挡下的物体误判为已在 B 稳定释放；或把原生视频接口当作已有能力。

**判断：**稿件采用有时间信息的多图，并要求留出片段校准和独立审核；接入实测尚未声称完成。**不必须修改。** 实现时明确选 Responses 路由，图像不得用 `--no-images` 静默替代。

### Q2：一个长 motion 持续运行甚至卡死时，GPT 是否还能看新观测？

**证据：**S1 的互斥覆盖 readonly；S2 顺序工具注册；S6 同步 predict。原版工具后观察不能满足持续监控。

**冻结位置：**02 L47–58；01 L257；09 L28、50–54。

**反例：**observe 虽声明 readonly，却排在长运动后；图像一直重复旧帧，而上层误以为监控线程仍健康。

**判断：**02 L58 已明确观察服务订阅 Gateway 的独立只读图像／遥测流，并要求长工具和卡死注入时多批新时间戳观察仍可送达。这里已给出结构性解决办法及验证条件，并非只写“异步待测”。**不必须修改。** 该条件涵盖实际传感读取也不能随 motion 被阻塞。

### Q3：两个 RPent 进程分别有 Toolkit 锁，能否同时写同一机器人？

**证据：**S1 仅是实例内锁；S10 的多进程架构不自动提供设备级租约。

**冻结位置：**02 L29–37、115–117、144–146；01 L263；09 L50、54。

**反例：**主进程心跳丢失后启动新 controller，旧进程仍通过自己的连接发送动作；两个实例内锁都认为自己独占。

**判断：**稿件明确唯一驱动连接、robot_id 设备级独占、不同 session 不得并持，以及递增控制代际、旧代际失效和重启先确认连接。逻辑作用域已跨进程，而非靠锁名称代替。T04／T09 可检验。**不必须修改。** 具体 lease 存储及 fencing 实现属于下一阶段交付。

### Q4：cancel 已发出或工具已返回，是否可以马上交给 Harness？

**证据：**S1 L351–365；S6 L505–540；S7。取消只有合作式边界，阻塞 predict／RPC 时未保证及时返回；工具返回也不是物理停稳传感证明。

**冻结位置：**02 L117–140，T07／T08；01 L44、263；06 L243–257。

**反例：**远端推理被取消，但一条驱动命令已经生效且还在运动；新纠正立即发出，控制来源重叠。

**判断：**稿件要求先撤销队列、处理在途动作、取得当前代际 quiesce receipt、确认保持再给新 lease；无法确认时不交接。本地保护不等待云端。持物时保持策略也不简化为断电。**不必须修改。** stop 时间与设备回执误差仍须实测，不因未实测判设计失败。

### Q5：A→B 的成功评分迟到，能否污染已经开始的 B→A？

**证据：**S12 证实旧 reward 缓存的具体危险；S1／S2 不自带本项目目标身份。

**冻结位置：**01 L140–148；02 L165–183、263，T18／T20／T21。

**反例：**旧请求返回成功，覆盖反向当前裁决；或复用上一方向 success=1 并重复结算成功。

**判断：**请求绑定 episode、goal、观察和执行区间、控制代际及版本；历史评分、历史动作标签、当前控制资格独立判断；缓存键与终局事件去重已定义。历史标签可补全，旧回复没有当前运动权限。**不必须修改。**

### Q6：遮挡、超时或模型不确定能否被吞成 0，维持看似连续的 RL？

**证据：**S11 不保证事实正确；S12 将非 YES／异常收敛为数值或旧缓存，说明不能直接复用其评分语义。

**冻结位置：**01 L114、158–164、267、285–292；02 L179、187、304；06 L268。

**反例：**物体已成功但暂被遮挡，unknown 被当失败；或者 reward 不齐仍发布完整 TD，后续才修改标签。

**判断：**unknown 非失败、非零分；pending 等齐或隔离，暂停依赖它的换向与训练视图；独立评测仍保留失败和未知试次，避免拒答后删分母。误报／漏报／拒答及标签撤销均被记录。**不必须修改。**

### Q7：候选代码通过语法检查或 memory 变成 verified，是否就能控制设备？

**证据：**S8 的 full_access 是真实默认值，memory verified 也确实不是物理回归结果。

**冻结位置：**01 L150–154；02 L34、56、193–201，T23；09 L70–76。

**反例：**生成程序从环境变量取到设备凭据，绕过 Gateway；或积累几个成功 cell 后修改 rubric、预算，使自己“发布成功”。

**判断：**稿件明确要求生成进程、固定评分、设备凭据、工具权限实际分离；所有 motion 走同一 Gateway；TRIAL 有范围和预算，固定核验／回归后发布，memory 不授予权限。它没有把 prompt 约束或目录 profile 误当执行隔离，也没有逐次人工审批阻断自主试验。**不必须修改。** 真实隔离配置与绕过测试是必须实施的已有门槛。

### Q8：Flywheel 原样接 RLinf，就能保留失败与纠正并训练在线 RL 吗？

**证据：**S3／S4／S10：原始记录有实际动作和提案；默认导出只选成功前缀，外部训练是 SFT；二值 action_source 无法区分全部来源。

**冻结位置：**02 L51、60、205–217、245–257；09 L38–46、104、113；07 L121–131。

**反例：**弱策略全失败，成功 exporter 无数据；把未执行 Harness 建议插进 transition 队列，借用下一条 policy 的后果。

**判断：**失败事实、纠正标签和版本化训练视图长期分开；主 RL 绕过成功 exporter 读持久事实；纯建议不造后继状态；候选和反馈动作按资格解锁。**不必须修改。** 原版 Flywheel 只是结构起点，不被叫作完成的 RL buffer。

### Q9：将正反两个任务一起导出，goal 会不会消失？

**证据：**S3 L83–86 明确拒绝多 task_language；L121 使用同一 language 写所有帧。

**冻结位置：**02 L60、91–93、225；09 L60、103。

**反例：**为让 exporter 通过，把两方向语言都改成“搬运物体”，重载时丢了目标身份；同一状态被监督为两种互斥动作。

**判断：**02 L60 已给两条明确接法：正反分别导出，由保留 goal 的版本化 loader 合并；或改造逐 episode 目标格式，并要求双样本导出／重载核验语言、规范目标和奖励。**不必须修改。**

### Q10：episode 目录存在且 finalize 使用原子改名，是否就能抗断电？

**证据：**S4：step 数据先在列表，直到 finalize 才写磁盘；目录存在不是每帧已持久化，原子改名也不证明未 finalise 内容能恢复。

**冻结位置：**09 L44、104；02 L144–146、205–215、307，T09／T30。

**反例：**运行半小时后进程或电源故障，内存动作丢失；ACK 丢失后重启又重放一条相对增量命令。

**判断：**稿件已要求追加事实 journal、增量落盘、断电恢复、意图与回执分别持久化；未知执行不重放，相同 ID 查询原结果；存储故障暂停新学习采集。**不必须修改。** 应在实现验收中具体覆盖强制断电与尾记录损坏，不能只做优雅退出；这是已声明耐久性要求的测试细化。

### Q11：planner 日志显示 g=A，真实 VLA 就一定执行反向目标吗？

**证据：**S6 L475–479、514–516 清楚区分 requested_prompt 和有效固定指令；双 Franka 还固定要求 20 维动作。

**冻结位置：**02 L50、56、77、91、225，T17；09 L58–64、103。

**反例：**更新 prompt 和日志，但 observation.task_descriptions 仍是固定清桌任务，Q／reward 已切向反向目标。

**判断：**稿件明确沿 goal→实际模型 conditioning→Q／target→replay→GPT rubric→评测贯通，并要求行为和梯度测试，不能只改字符串或查维度。松灵单臂适配也明确不能照搬 Franka 常量。**不必须修改。**

### Q12：删去人工 verdict／reset 的等待代码，是否就满足无人循环？

**证据：**S5 实际阻塞点、finish guard 与 solved 依赖 operator；S10 不能证明物体自主复位。

**冻结位置：**01 L28、91；02 L56、187–199、261–265；09 L64–68、121。

**反例：**直接把 request_operator_verdict 改成 success，把 scene_reset 改成 reset joints；物体仍在地上，循环却继续记成功。

**判断：**日常结果由固定 GPT 观察判据替代，反向 policy 处理正常搬运，Harness 异常恢复负责其他起态；必须核下一方向 init_set，不可恢复就记中断。人工复位、点选、标奖和值守均计入成本。**不必须修改。** 这些是待实施的实体替换，不被表述成原版已有无人能力。

### Q13：Harness 永远代做运输，只让 VLA 抓一下，能否声称完整 policy 学会抓放？

**证据：**S9 明确 planner／解析原语和局部接触 VLA 的分工；该论文系统成绩不能推出完整 policy 成绩。

**冻结位置：**01 L232、259、283–298；02 L279–291，T28；09 L109–113。

**反例：**固定 policy 完全不更新，仅增加解析 transport 原语，系统成功率上升；评测又只测接触阶段。

**判断：**稿件显式改变 RPent 原评价口径，要求完整抓放、同 checkpoint 双向无动作纠正评测，并区分系统辅助与在线学习成绩，安排自主重试和纠正退出。**不必须修改。** 是否提高仍是实验问题，不预先保证。

### Q14：真实执行的反馈纠正，能否直接拼成过去状态的整段动作标签？

**证据：**S6／S7 的逐动作调用和返回结构不能自动提供本项目事前整槽决策；S4 记录提案与实际动作的区分只解决部分问题。

**冻结位置：**01 L122–138；02 L217、229–257；06 L165–190、237–257；09 L113。

**反例：**GPT 在帧 107 看到滑落后重抓，把事后微步拼成帧 100 已确定的 U；或把一帧优质纠正重复 n 次以喂固定头。

**判断：**冻结稿保留事实，但普通 BC 需同信息集和相容动作窗口；反馈／特权标签单列；单步不重复填充；影子建议无真实 TD；接管破坏槽时隔离宏 TD 并记录比例。**不必须修改。** 本报告只审 Harness 数据边界，完整 Bellman 推导不据此宣称已验证。

### Q15：推荐 RPent 高于 RoboRSI，依据是否变成“新、同属 RLinf、有真机视频”？

**证据：**S1–S10 给出可复用资产与实际缺口；S13 同时验证 RoboRSI 的特定 RL skeleton 和已有纠正微调示例。

**冻结位置：**01 L251–259；09 L5–7、22、78–94、126–132；README L9。

**反例：**因 RoboRSI 某一个 run 未实现而宣称它没有任何参数学习；因 RPent 有 SFT 数据出口就声称 RL 已兼容。

**判断：**09 L94 已将 skeleton 结论限制在固定入口，并没有否认其他学习路径。RPent 优先是本项目认知／工具／动作与提案记录的工程适配判断；没有同条件工位对照，不能解释为已证明整体优于 RoboRSI。论文冻结 VLA 与本项目在线 RL 的距离也已明示。**不必须修改。** 可补一句 RoboRSI 官方已有纠正微调实例，使比较更直观，但不改变当前有限推荐。

### Q16：GPT、learner 或存储中断后，系统是否用持续动作伪装“持续自学习”？

**证据：**S1 的取消等待、S4 的持久化时点、S11 的应用侧执行职责共同说明服务故障需本地路由，模型回复不能充当运行保障。

**冻结位置：**01 L267、289–294；02 L273–277、293–307、350，T26／T27／T30。

**反例：**learner 死掉但仍报告有效学习小时；观察故障仍盲目换向；撤销错误标签仅重标 replay 却继续发布受污染 checkpoint。

**判断：**稿件区分参数更新暂停、语义判断暂停、自主运动停止和存储失效，具有预算边界；发布版本包在交接边界切换，污染沿 manifest 追到权重与后继版本。**不必须修改。** 工位数值预检尚未完成但需填写的项目已枚举，不是关键逻辑空缺。

## 必要项、非阻断建议与最终判定

**必须修改项：0。** 本轮未发现需要先修正文稿才能进行下一步实现的 Harness 关键设计缺失。冻结稿已识别本次逐行源码揭示的风险，并给出控制、数据与评测上的处理路径。

三个可选文字细化：在 API 预检处直写 Astra 工具必须用 Responses；将断电／损坏 journal 尾记录恢复写成独立验收编号；在 RoboRSI 比较旁补充其官方纠正轨迹微调实例。这些不改变已有架构与范围，不能为了产生修改项而升级成 FAIL。

仍必须实施的既有门槛包括：长工具／卡死下的新鲜观察、跨进程独占与 fencing、驱动 quiesce 确认、迟到评分换向隔离、候选权限绕过测试、失败与双目标数据重载、断电恢复、自动 verdict／实物复位、同 checkpoint 的完整双向无动作辅助评测。文稿明确未实施这些门槛，因此本报告的 PASS 只对应**冻结设计能覆盖所审 16 个反例且没有新增必要修订**，不对应运行或学习效果通过。

[toolkit]: https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/tools/toolkit.py
[api]: https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/api_loop.py
[export]: https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/export.py
[episode]: https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/episode.py
[dual-toolkit]: https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/toolkit.py
[dual-tools]: https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/tools.py
[dual-env]: https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/env_server.py
[codex]: https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/codex.py
[memory]: https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/memory/manager.py
[paper]: https://arxiv.org/html/2607.08448v4
[architecture]: https://rpent.readthedocs.io/en/latest/rst_source/development/architecture.html
[planner-doc]: https://rpent.readthedocs.io/en/latest/rst_source/usage/configure_planner.html
[flywheel-doc]: https://rpent.readthedocs.io/en/latest/rst_source/usage/flywheel.html
[dual-doc]: https://rpent.readthedocs.io/en/latest/rst_source/usage/dual_franka.html
[astra]: https://developers.openai.com/api/docs/models/gpt-6-astra
[function]: https://developers.openai.com/api/docs/guides/function-calling
[enpire]: https://github.com/NVlabs/ENPIRE/blob/99ee90acf65b5b18957c8382ad580db999528be3/enpire/env/forge/cap/reward/gemini_reward.py
[roborsi-code]: https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/roborsi/embodied/skills/_lib/rl/pi0_posttrain/policy.py
[roborsi-blog]: https://lab.noematrix.ai/blog/2-roborsi/
