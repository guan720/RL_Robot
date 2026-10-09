# R08 Harness／融合独立审查

**结论：PASS（限定文稿与所核原始来源）；具体问题 20 项，必要修订 0 项。**

审查日期：2026-09-23。审查对象仅为本轮 `input/` 内九份冻结 Markdown。未读取同轮其他审查或历史审查结论；冻结稿内指向历史审查的链接未打开，也不以其自报通过作为证据。先只读科学家 START_HERE、ROLE、status、INDEX 与技能入口；技能实际位于 `embodied-scientist/.agents/skills/embodied-research-scientist/SKILL.md`。公共库处于暂停更新状态，本次未调用 UPDATE／goal，未写知识库或修改科学输入。

本次完成文本与选定原始源码／论文核查，**没有安装或运行候选框架，没有执行 T01–T39，没有训练模型或控制真机**。PASS 不表示系统集成、停止机制、学习收益或无人运行验收通过。

## 1. 技术要点枚举

先按以下机制拆解审查，而不按框架名称判断兼容性：

1. GPT-6 主语义观察、评分和动作纠正；DAgger 数据聚合与教师质量条件。
2. 长动作期间的独立新观测；观察锁、源时间戳和本地保护。
3. 唯一 Gateway、设备级 lease／epoch、实体 quiesce、在途动作与崩溃去重。
4. 同一参数正反 goal；normal reverse、局部纠正和异常 recovery 的边界。
5. unknown／pending、迟到评分、当前动作资格、终局去重及 rubric 版本。
6. 自动代码 TRIAL、预算、独立核验、发布与回滚。
7. 提议、学习边界命令、驱动命令、测量状态及投影所在层。
8. 最新反馈产生的新决策、普通 BC 信息集、部分标签与真实 TD 的分别资格。
9. C／E／D、request／commit／activate 与接管删失，不用一个 mask 包办。
10. RAPolicy 的 replay Q／V 与优势回归、RT-EXPO 的编辑／RTC-BC、完整头 Q 梯度的不同目标。
11. 通用 capability／schema／adapter、可替换骨架、首次 AgileX 移植成本。
12. policy 独立能力、系统辅助能力、自主学习与人工成本的分开评估。

## 2. 冻结输入定位

下文行号均指 R08 冻结稿；简称只用于压缩定位。

| 简称 | 文件 |
|---|---|
| M | [01 技术方案](input/03_RL_Harness自主学习系统_20260922/01_RL_Harness真机自主学习技术方案.md) |
| I | [02 接口契约](input/03_RL_Harness自主学习系统_20260922/02_接口契约与开发验收.md) |
| A | [06 异步目标](input/03_RL_Harness自主学习系统_20260922/06_异步动作时间轴与学习目标.md) |
| E | [README](input/03_RL_Harness自主学习系统_20260922/README.md) |
| R | [综合调研报告](input/04_RL与Harness扩展调研_20260923/01_RL与Harness开源基线深度调研报告.md) |
| V | [VLA RL 专项](input/04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md) |
| U | [自主学习与复位专项](input/04_RL与Harness扩展调研_20260923/research/02_自主学习与复位扩展调研.md) |
| H | [Harness 专项](input/04_RL与Harness扩展调研_20260923/research/03_Harness扩展调研.md) |
| P | [训练平台专项](input/04_RL与Harness扩展调研_20260923/research/04_训练平台与开源生态核查.md) |

主方案、接口和异步目标逐段检查；四个专项及综合稿重点检查 Harness、动作／学习协议和融合结论。没有把未逐一复核的全候选资产、热度、API 能力宣称为本次独立验证结果。

## 3. 独立实际打开的原始来源

均为本次重新访问，不依赖输入文稿的“已核”声明。以下共六份关键正文／固定源码，另核一份原论文官方摘要页。固定源码入口均成功；OpenETA 先打开 GitHub blob，再切同 SHA 的 raw 便于读函数，没有以打不开为由跳过关键机制。网页 `find` 对带下划线标识偶有未命中，已用正文定位补读；未命中不视作代码不存在。

| ID | 原始入口及实际阅读位置 | 独立所得与适用边界 |
|---|---|---|
| S1 | [Show-Harness preemption.py，137d5718c3b7af0150764d8f9beeb252c9f2794a](https://raw.githubusercontent.com/showlab/Show-Harness/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/preemption.py)，`InterruptibleDecider.decide` | 线程可继续运行，stale／generation 用于丢旧模型结果。此文件没有实体停止回执，支持必须外接 Gateway 的判断；不外推全仓不存在其他停止能力。 |
| S2 | [OpenETA registry.py，7d4a0a1522ba8ebbd362bde880bad81d2a98f15e](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py)，`_invoke_tool_handler`、`_cancelled_tool_result` | cancel 触发放弃等候结果的异常，daemon handler 不因此被终止；代码保留 abandoned 诊断。工具取消与实体停止必须分开。 |
| S3 | [RPent toolkit.py，eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/tools/toolkit.py)，`execute_tool`、`readonly`、`cancel_active_and_wait` | active-operation 检查先于只读判别，长工具会阻挡该入口的观察；cancel 等待 handler 返回。这里只确认指定旧 SHA 的机制，不声称已复核新 HEAD 全路径。 |
| S4 | [RAPolicy 原论文 v1](https://arxiv.org/html/2609.22888v1)，§III-B–D，式 1–7 | Q 以 replay chunk 和 V 备份；actor 复用 rollout latent 做优势加权条件回归，不是新动作上的 Q 梯度。支持其与本项目完整头目标分开；本次未独立核其全部 fork 代码。 |
| S5 | [RT-EXPO 固定学习器，803381fc3b4c91a0c47904f1b688fc5e35904f50](https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)，`update_edit_actor`、`update_actor`、`update_critic` | edit actor 有 Q／熵目标；base actor 调用训练／prefix 训练；critic 使用 `discount ** replan_steps`。不能把三者换名后接入另一队列 target。 |
| S6 | [RT-EXPO 原论文 v1](https://arxiv.org/html/2609.18207v1)，§IV、附录 VII-D.3–4、VII-E.2 | 快编辑看较新观测；部分 critic／filter／edit 输入有派生位置速度；base VLA 用成功数据 RTC-BC，熵不进入其 Bellman backup。支持信息条件清单及独立协议要求。 |
| S7 | [DAgger 原论文官方页](https://proceedings.mlr.press/v15/ross11a.html)，官方摘要 | 结论依赖 no-regret 与附加 reduction 假设；只能支持“不能自动给错误率未知 GPT 套保证”的有限判断。本次未读其 PDF，不把摘要当完整算法审计。 |

S1–S3 说明取消和观察隔离缺口确有源码依据；S4–S6 说明算法差异不是仅接口命名不同。本报告不从这六处选读推导任何仓库完整可用或完整不可用。

## 4. 二十项具体问题、定位与判定

每项“已处理”表示冻结稿有明确设计／限制；其附带测试仍未执行。

| 编号／具体问题 | 文稿定位与实际处理证据 | 判定 |
|---|---|---|
| Q01 GPT-6 是否真承担主要观察与动作纠正，还是只剩被小模型触发后做文本解释？ | M L115–139；I L148–163、187；U L153。主语义观察、数值／程序动作和状态访问标签明确属于 GPT；本地限位与 watchdog 只负责事实和保护。模型调用及工位质量仍需 P2 预检。 | 已处理 |
| Q02 没有外部强 policy 时，是否仍能 DAgger；又是否把 GPT 建议当完美专家？ | M L39–41、133–139、281–285；I L193–201。以访问状态的标注与聚合定义，单列质量／可观察性；保留动态 BC 同预算对照。S7 只支持条件性理论，文稿没有直接套保证。 | 已处理 |
| Q03 长 motion 持锁或卡死时，能否继续观察？ | I L58、392–396；M L255、273。指定只读图像／遥测订阅不排在 Toolkit 后，长工具卡死故障验证明确。S3 的只读工具也受 active-operation 限制，独立读取的源码支持该改造必要性。 | 已处理，观察并发待测 |
| Q04 policy、纠正、恢复、TRIAL 和平台 env 同时请求时，是否只有一个物理写入口？ | I L115–132、378；M L262、301。设备级独占、递增代际、quiesce 凭证和 handoff；receipt 不接受调用方自填 stopped。S1、S2 的取消均不替代此凭证。 | 已处理，T04／T08／T31 待测 |
| Q05 ACK 丢失、重启或旧模型回复晚到，能否重复执行增量或复活旧 lease？ | I L142–146、325；A L261–268。意图／回执分别持久化，同命令 ID 查询原结果；重启升 epoch，未知不重放，旧结果失去写权限。 | 已处理，T06／T09 待测 |
| Q06 normal reverse 是否被恢复脚本取代；正向成功是否足够直接开反向？ | M L88–109；I L259–265、335；U L34。同一 θ 双向训练；掉物恢复独立记录；换 goal 切 episode、flush／reprime；反向前还验 init_set，不按奇偶盲切。 | 已处理 |
| Q07 正向迟到评分到达反向期间，或当前分数 unknown，是否串奖／误控？ | I L165–183、334、336–337；M L143–151、175；A L229–231。历史评分、历史标签、当前控制三类资格；缓存含 goal／episode／证据／版本；unknown 不作零／失败；终局按证据充分时刻与事件 ID。 | 已处理，T18／T20／T21 待测 |
| Q08 同一 GPT 生成动作又宣称 DONE，能否自证成功或修改 rubric？ | I L185–191、291、339；M L167–179；H L112、215。冻结任务谓词与独立留出审计，生成者不得改目标／评测分母；DONE 只为工具结束。 | 已处理，评分可靠性待实测 |
| Q09 新代码是否能自动 TRIAL，且试验成功是否直接等于正式 release？ | M L153–157、317；I L195–201、273–277、339。受限 API、静态检查、范围／次数／预算内自动试验，不要求逐次人批；固定核验和回归后发布，候选不能修改自身门禁。 | 已处理，T23／T30 待测 |
| Q10 语义工具、连续 VLA、关节驱动与投影不同空间，Q 究竟用哪个动作？ | I L64–77、319；M L161–165；A L101、163。四层分别记；a_rl 与 actor／Q 边界一致。投影前后选择均需固定定义；不可用测量位移倒填命令，不能可靠转换则隔离。 | 已处理 |
| Q11 用最新反馈逐步纠正后，能否把最终路径拼成最早状态的完整 BC chunk？ | M L137–141、165；I L172、255–257、379；A L182–190、255。明确不允许倒填；可保存微步／合时监督，特权 BC 另建定义；孤立一步不能复制成 n 步。 | 已处理，T14／T32 待测 |
| Q12 未执行建议与“事前 admission 后 C 提前终局”的样本是否被错误混为一类？ | I L217、229–255；A L63–95、194–211。前者仅监督，后者须真实事前冻结请求与原在途结果；只记录 delayed-decision terminal，不伪称物理激活，不补造动作。 | 已处理；终局完整性由 T11 待测 |
| Q13 Harness 频繁抢占／期限错过后，是否只乘 executed mask 就继续训练原宏 TD？ | I L136–140、239–257；A L245–268。当前受破坏槽隔离，准确的前驱边界保留；C 是状态、E 是决策、D 不入价值动作；另报删失／覆盖偏差。 | 已处理，T07／T10–T16 待测 |
| Q14 RAPolicy、RT-EXPO 与完整头是否共用一套动作和 loss 的空壳接口，暗中混 target？ | M L289–297；I L381、384、398；A L329–339；V L339、347–369；P §13。独立 Q／V／actor 状态、折扣、噪声、终止与接管协议；确定性头不得填假 log_pi。S4–S6 独立支持这些方法确有不同目标。 | 已处理，T34／T36／T39 待测 |
| Q15 失败局部纠正、无原始 latent 示范、部分 flow 标签和长久 demo 保护是否分别处理？ | I L211–217、253–257；M L283–295；V L353–363。TD 真实性不等于 BC 质量；无原噪声 actor 监督单列，真实示范 Q／V 资格另判；部分标签检查输入／attention；永久种子与双向采样不被快成功榜淘汰。 | 已处理 |
| Q16 选择依据是否仍被 AgileX/Piper 现成支持主导，通用接口是否仅口号？ | M L11、271–275；I L388–396；R L23、207–221；H L204–206。两个不同 schema 的模拟 adapter 回放、维度／单位／频率／stop capability 与 normalizer 版本明确；换本体默认隔离 replay。 | 已处理，T37 仅软件边界测试 |
| Q17 RPent／OpenETA／Strands／Show 能力是否被拼成“现成完整融合系统”？ | R L134–159、207–221；H L11、192–218、250–256；I L394–396；P L7–9。只先试 RPent，可因同门槛成本切换；一个认知调度器、无独立写权插件、Gateway、数据入口、learner。S1–S3 支持尚需改造的边界。 | 已处理 |
| Q18 框架隐式 home／RELEASE 或不参与机械臂的零向量，会不会破坏持物接管？ | I L77、392；M L167；H L109。非活动臂禁用／保持；初始化必须显式请求，禁默认放夹爪或双臂归位；T38 检查真实 adapter 行为。 | 已处理，不能仅靠配置名字验收 |
| Q19 发布权重、normalizer、工具和 rubric 的组合是否一致，撤销误标能否追踪已污染权重？ | I L271–297、342–346；M L301–305。相容包原子边界切换；原始观测可重算；manifest 追踪训练及后继版本；重标 replay 不等于权重已纠偏，软件回滚不撤销物理动作。 | 已处理 |
| Q20 强 Harness 代做、额外状态输入或丢弃困难起态，会不会被算成 policy／自主学习改善？ | I L279–291、344–345、381；M L275、323–336；R L211–221。三套结果、分方向同 θ、固定预算及信息清单；人工值守／审核成本、拒绝和 unknown 保留；测试污染后转开发集。S6 支持“同相机仍可能不同信息”。 | 已处理，T28／T29／T34 待测 |

## 5. 必要缺陷、待实测门槛与可选项

### 必要修订：0 项

在本次限定 Harness／融合范围及选定原始证据中，没有发现足以阻止文稿通过的缺失、互相矛盾的强制接口或将未运行写成运行成功的结论。RAPolicy 原生头、RT-EXPO 实时路线、完整头参考并存有明确入口和切换条件，不构成未决的整套框架堆叠。

### 文稿已列出的待实测门槛：不计为新缺陷

- **持续观察与实体控制：** 长工具卡死、图像时间戳、唯一写通道、lease 失效、驱动停止回执、在途／重复命令和重启对账，见 I §1.3、§3、T04／T06–T09／T31／T38。
- **GPT 有效纠正与评分：** 双向失败／遮挡留出片段的误报、漏报、unknown、调用时延；局部纠正成功、动作可表达性及 policy 可观察性，见 M P2、I §4。
- **训练数据和目标：** C/E/D、终局原请求、迟到核验、部分反馈与监督 mask、纠正噪声和独立协议的手算／计算图测试，见 I T10–T16／T34／T36／T39 与 A §9。
- **有限代码演化：** 限定权限的真实 TRIAL、失败恢复、回归与发布／回滚，见 I T23／T30。自动执行资格仍受预设范围约束。
- **实际学习收益：** 同预算动态 BC 对照、同一 checkpoint 双向无动作辅助评估、系统辅助产出和自主学习人工成本，见 M §13、I §6.2。仅工具能动、数据能保存或一次优化器更新均不足。
- **通用框架选择：** 两种动作 schema、固定具体入口／模式／horizon 的故障回放与实际 adapter 验证，再比较改造工时；尚不能宣布任一骨架成本最低，见 T37／T38。

### 可选改进：2 项，不阻塞本轮

1. V §2 的“两条比较”摘要可同步补上 §11 新增 RAPolicy 的快捷入口；当前 M §10.4、R §1／§9、E 与 V §11 已给出明确最新优先级，因此不影响实际选择结论。
2. 实现阶段可把 I T01–T39 转成可追踪测试登记表，逐项记录固定版本、日志 URI、执行日期和结果；当前表已清楚标为待执行，无须为了文稿审查创建空实现或伪验收记录。

**最终记录：20 问已核；PASS；必要修订 0；可选项 2；未执行任何框架／训练／真机验收。**
