# R02 独立审查：Harness / RPent

审查日期：2026-09-23。审查对象是设计、来源与接口契约，不是已经实现的软件。本报告未安装 RPent、调用付费模型、训练模型或操作机器人。

输入仅为本轮 `input/` 中冻结的 README、01、02、06、07、09 六文件；未读取其他轮次或其他审查员的报告，未修改正式材料和科学家知识库。下文位置均指冻结文件的行号。OpenAI 部分按 OpenAI Docs 技能独立检索、打开官方页面核验。

## 一、先枚举关键技术点

1. RPent 的优先级依据应是本项目的模块适配度，不能偷换为整体学习效果已经优于 RoboRSI。
2. 原论文是冻结 VLA 与固定原语的组合；记忆改进、程序复用、参数学习三者有不同证据。
3. GPT-6 主观察需要实际接收图像和时间证据；结构化输出不能保证物理判断正确。
4. 长时间 motion 工具运行时仍要持续获得观察；模型异步工具、应用并发和动作 chunk 异步不能混同。
5. 唯一设备 owner、软件取消、驱动保持凭证与控制交接必须分开。
6. 同一个 policy 的两种 goal 要实际进入网络、Q、target、数据和评分，不能只换 planner 日志。
7. 自动 DAgger 要有可学习的纠正标签来源、质量和信息集，而非默认存在一个强专家。
8. 迟到回复的历史评分、历史 BC、当前动作三种资格必须独立；评分缓存不得跨目标复用。
9. TRIAL 的动作权限、评分权限、试验预算和候选发布须有明确边界。
10. Flywheel 现有成功 SFT 出口与本项目失败 RL、查询 BC、持久事实桥不能混称。
11. 人工 verdict、物体复位、标定及必要值守要分别核实，替换方案要有失败出口。
12. policy 独立能力、系统辅助成功、自主学习成本与评测分母要分开，双向使用同一 checkpoint。

## 二、本轮独立打开的一手证据

以下链接均在本轮实际打开，结论不是只从冻结稿的引用列表转述。RPent 源码统一固定到 `eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1`。

| 证据 | 本轮主要核查内容 |
|---|---|
| [Harness VLA 原论文 v1](https://arxiv.org/html/2607.08448v1)、[arXiv 元数据](https://arxiv.org/abs/2607.08448) | 冻结 VLA、固定原语、轮流执行、仿真评测；v1 为 2026-07-09，当前元数据另列 v4 |
| [RPent 官方架构](https://rpent.readthedocs.io/en/latest/rst_source/development/architecture.html) | planner、工具、观察与记忆的组织 |
| [Planner 文档](https://rpent.readthedocs.io/en/latest/rst_source/usage/configure_planner.html)、[api_loop.py](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/api_loop.py) | API provider、图像转换、工具包装与串行执行 |
| [Toolkit](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/tools/toolkit.py) | active-operation 锁、合作取消、工具结束后采集状态 |
| [双 Franka tools](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/tools.py)、[toolkit](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/toolkit.py)、[env_server](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/env_server.py) | 固定指令、逐动作取消边界、人工判定、环境返回数据 |
| [双 Franka 官方部署](https://rpent.readthedocs.io/en/latest/rst_source/usage/dual_franka.html) | 标定、机器人依赖、特定工位 checkpoint、人工流程 |
| [Flywheel 文档](https://rpent.readthedocs.io/en/latest/rst_source/usage/flywheel.html)、[episode.py](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/episode.py)、[export.py](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/export.py) | 动作与提案分离、成功前缀导出、内存积累及 finalize |
| [MemoryManager](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/memory/manager.py)、[Flash](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/flash.py)、[Codex planner](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/codex.py)、[LICENSE](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/LICENSE) | 记忆证据等级、程序复用、实际权限与根代码许可 |
| [RoboRSI 官方博客](https://lab.noematrix.ai/blog/2-roborsi/)、[独立固定的官方 README](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/README.md) | 多角色技能修订、纠正学习案例和累计覆盖口径 |
| [Zetta 固定 README](https://github.com/air-embodied-brain/Zetta-Embodiment/blob/1fee179644d52c32fa5a7728751cf0853a29b9c0/README.md)、[ENPIRE 实验契约](https://github.com/NVlabs/ENPIRE/blob/99ee90acf65b5b18957c8382ad580db999528be3/enpire/policy/autoresearch_instruction.md)、[ENPIRE 奖励缓存](https://github.com/NVlabs/ENPIRE/blob/99ee90acf65b5b18957c8382ad580db999528be3/enpire/env/forge/cap/reward/gemini_reward.py) | 候选／评测职责与奖励迁移边界 |
| [GPT-6 Astra 模型](https://developers.openai.com/api/docs/models/gpt-6-astra)、[Function calling](https://developers.openai.com/api/docs/guides/function-calling)、[Async tool calling](https://developers.openai.com/api/docs/guides/async-tool-calling) | 图像能力、Responses 路由、后台任务职责 |
| [DAgger 原始出版页](https://proceedings.mlr.press/v15/ross11a.html) | 访问状态上的纠正聚合与专家条件边界 |

取证限制：GitHub API 返回限流，RoboRSI 全库归档读取未完成，已结束该读取；通过只读 `git ls-remote` 固定其 HEAD 并另读该 SHA 的 README。因此本报告不把“RoboRSI RL skeleton”当作本轮已经独立复验的源码事实，也不重新背书 09 的瞬时 stars/forks 数。上述限制不影响本轮已经读到的 RPent 固定文件。

## 三、独立审查问答

### Q1：RPent 高于 RoboRSI 的推荐，是否已有足够依据？

**答：作为优先适配候选，依据足够；作为无人学习效果的优越性证明，不足。PASS。**

位置：09 行 5–7、80–92、113–122；01 行 251–259。RPent 的 VLA／解析动作统一入口、真实机器人扩展和动作／提案记录，能直接对应本项目的认知层、工具层和数据起点。RoboRSI 官方材料则着重多角色技能树及修订闭环；其 README 也主动区分累计任务覆盖和冻结评测。二者不存在本工位同预算直接对照，不能从不同论文成绩排名。稿件明确把推荐限定为源码适配度，并把最终能力交给预检和实验，没有越过这一证据边界。[RPent 架构](https://rpent.readthedocs.io/en/latest/rst_source/development/architecture.html)、[RoboRSI README](https://github.com/nssmd/RoboRSI/blob/9b644d270560c440d760965cf1b859df674459de/README.md)

### Q2：是否误把原论文中的 Harness 进步说成底层 policy 已学会？

**答：没有。PASS。**

位置：09 行 22、109；01 行 259、285–298。原论文把冻结 VLA 当作局部接触原语，由 planner 组合固定工具，任务记忆支持重用。稿件据此要求完整 pick-and-place 的无动作辅助评测，没有将解析动作代做运输计为 policy 能力。反例是冻结 checkpoint，仅改进运输脚本而系统成功率上升；02 T28 明确禁止将此记作模型学习。[原论文 §2–3](https://arxiv.org/html/2607.08448v1)

### Q3：GPT-6 主观察和动作纠正的 API 判断是否准确？

**答：准确，并保留了必要接入门槛。PASS。**

位置：01 行 110–128；02 行 146–159；09 行 30。本轮官方页列出 Astra 图像输入、函数调用及结构化输出，视频输入不受支持；函数调用要求 Responses。稿件采用有序多图而未假定原生视频。RPent 文档声明 Responses 支持，但稿件仍要求实际核对 model ID、provider、多图和工具结果，未宣称改一个名称就已兼容。[模型页](https://developers.openai.com/api/docs/models/gpt-6-astra)、[函数调用](https://developers.openai.com/api/docs/guides/function-calling)、[Planner 文档](https://rpent.readthedocs.io/en/latest/rst_source/usage/configure_planner.html)

### Q4：长期工具执行中持续观察，是否被错误地交给原版 RPent？

**答：没有；该功能明确列为须新增的运行时职责。PASS，实施时必须验证。**

位置：01 行 257；02 行 29–35、47；09 行 28、50–54。独立源码核查发现，API 工具注册显式 `sequential=True`，Toolkit 的 active-operation 检查也覆盖只读工具。因此把一个长 motion 原样放进 Toolkit，再在同一锁后排队 observe，不能实现持续监控。稿件已经要求独立事件驱动观察及外置本地 Runtime，没有把这个缺口说成已有能力。[api_loop.py](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/api_loop.py#L670)、[Toolkit](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/tools/toolkit.py#L234)

实现可以用独立观察请求，或将长任务提交成 handle 后由应用管理；无论选哪种，都须在 motion 未结束时继续送达新观察，并能由本地保护处理失联。GPT-6 的 `async: true` 只允许模型继续工作，后台任务仍由应用运行和管理，不能替代这一改造。[官方异步工具说明](https://developers.openai.com/api/docs/guides/async-tool-calling)

### Q5：取消工具是否被当成机器人已经停止？

**答：没有，交接顺序和未知分支已定义。PASS。**

位置：02 行 109–142、T04/T07–T09；01 行 263。RPent 的取消是发 event 并等待合作边界；双 Franka 的推理及在途 RPC 可能还未返回。稿件要求封新命令、撤未生效队列、处理在途、取得保持凭证、新观察后再 handoff；不能确认时不能交接，也不等云端批准本地保护。ACK 丢失不重放增量动作，重启提升代际。这个契约足以排除“旧 owner RPC 晚返回后再次运动”的反例；具体驱动能否满足仍属 P0 实测 gate。[Toolkit](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/tools/toolkit.py#L322)、[双臂执行](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/tools.py#L490)

### Q6：同一个 policy 的两个 goal 能否只是日志上不同？

**答：稿件已识别并明确禁止这一情况。PASS。**

位置：09 行 58–60；02 行 87–89、221、259、T17/T18；01 行 87–106。固定双 Franka 代码把 `effective_prompt` 设为 `_vla_instruction`，再送到预测输入，planner 的 prompt 不决定真实 conditioning。稿件要求规范 goal 贯通 actor、Q、target、BC、reward 和评测；目标切换清队列并 reprime。T17 还区分结构接入与训练后正确语义，不要求随机初始模型立刻会双向任务。[固定 tools.py](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/tools.py#L452)

### Q7：自动 DAgger 是否暗含一个不存在的强专家，或给建议伪造后果？

**答：没有。PASS。**

位置：01 行 26、38、118–138；02 行 197、203–213、251–253；06 行 165–190、237–255。稿件承认 GPT 纠正能力需验证，初始零成功也不保证 RL 能启动。未执行查询有独立 BC 标签池，普通 TD 要真实 admission 及相应时序证据；新图像下的反馈纠正不能回填旧决策。短标签也不能复制成完整 n 步。接受“同信息集的可信标签”与“同协议的真实纠正”两条路径，不把整回合成功当每个动作的质量证明。DAgger 的专家假设未被无条件转移给 GPT。[DAgger](https://proceedings.mlr.press/v15/ross11a.html)

### Q8：迟到评分、goal 切换和 cache 是否有确定性处置？

**答：有。PASS。**

位置：02 行 161–179、259、T18/T20/T21；06 行 229–231。正向成功的旧回复可以完善正向历史，不能结束已经启动的反向任务。缓存绑定证据和评分版本，缺失分数保持 pending／unknown；事件去重防重复终奖。迟到确认也不改写已经发生的 commit，无法确定终局帧就不发布该 target，终局先后按证据实际成立时刻裁定。ENPIRE 固定奖励文件的无 goal 全局旧值复用确实不适合直接移植；稿件已明示要改造。[ENPIRE 固定奖励实现](https://github.com/NVlabs/ENPIRE/blob/99ee90acf65b5b18957c8382ad580db999528be3/enpire/env/forge/cap/reward/gemini_reward.py)

### Q9：candidate→TRIAL 是否仍允许候选自改评分或直连驱动？

**答：设计不允许，且没有把记忆等级当权限。PASS。**

位置：01 行 150–154；02 行 191–197、T08/T23；09 行 70–76。固定源码的 Codex planner 有全文件权限，memory 的 verified 可由累计证据数量产生；二者都不是执行隔离或任务回归证明。稿件要求生成进程、评分、凭据及执行权限实际分离，候选仅经受限 API，在范围及预算内自动试验，核验后发布，试验数据先隔离。允许自动 TRIAL 与禁止候选修改自身门槛并不矛盾。若实现只靠 prompt 禁令或沿用全权限进程，应判实现不通过；稿件没有授权这种实现。[Codex planner](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/codex.py#L102)、[MemoryManager](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/memory/manager.py#L88)

### Q10：Flywheel 是否已经被当作真机在线 RL buffer？

**答：没有。PASS。**

位置：09 行 36–46；02 行 51、201–213。原记录器区分实际动作与 VLA 提案，且在 finalize 才写主要数组；官方导出选择成功回合的首次成功前缀，供外部 SFT。稿件要求另建失败 TD、查询 BC、真实调度事件、版本化标签和持久 journal，因此没有丢弃失败、用建议配他者后继或用内存列表冒充断电持久性的问题。[Flywheel](https://rpent.readthedocs.io/en/latest/rst_source/usage/flywheel.html)、[EpisodeWriter](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/episode.py)、[导出器](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/export.py)

补充实现细节：原导出器还要求单次导出的 `task_language` 唯一。双向学习应独立导出后由版本化 loader 汇合，或明确扩展导出格式；不能假定默认导出能直接混合两个 goal。这与稿件已要求的 goal 数据桥一致，不构成设计矛盾。

### Q11：人工依赖的替换是否只是把 operator verdict 自动填 true？

**答：不是；替换链可作为工程假设，但能力尚须实测。PASS。**

位置：09 行 64–68；01 行 26–28、51、267；02 行 181–197、261、300–303。源码和官方文档证实人工 verdict 存在，且 evaluation 也要求结果确认；scene reset 的人工恢复属于 exploration。稿件用固定 rubric 的 GPT 证据判断、共享反向任务和异常恢复替代这些职责，同时保留合法 init-set、未知、预算耗尽和无法恢复时终止窗口。它没有保证掉出可达区的物体一定能自动取回。判据准确率、有效局部纠正和无人窗口范围属于合理 gate，不能仅因未实测判文档 FAIL。[双 Franka 官方部署](https://rpent.readthedocs.io/en/latest/rst_source/usage/dual_franka.html)、[固定 Toolkit](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/toolkit.py)

### Q12：两套学习信号是否与评估口径闭合？

**答：闭合，未宣称 RL 必然优于同数据 BC。PASS。**

位置：01 行 36–38、232、283–300；02 行 275–293；07 行 143–151。动态 Harness-DAgger／BC 与 BC＋RL 用同预算比较；任务动作辅助关闭后评同一 checkpoint 两个方向，系统吞吐与人工分钟另记。难起态、未知、拒绝和中止不任意删分母，最终留出与反复晋级资料区分。该口径能揭示“系统一直救回，但 policy 未提升”和“困难窗口全部被隔离”的反例；未把原论文冻结 VLA 的成绩当作项目在线 RL 增益。

### Q13：许可与事实准确性是否足以支持复用承诺？

**答：根代码许可和主要实现判断准确；复用承诺已有边界。PASS。**

位置：09 行 15–22、64、126–128。固定根 LICENSE 为 Apache-2.0；这不覆盖外部 checkpoint、数据和机器人依赖，稿件明确另核。特定 Franka checkpoint 的工位泛化限制有官方文档支持，未声称能直接迁移松灵。v1 日期正确；论文元数据已有 v4，不使明确引用的 v1 无效，但未来更新实验数字须绑定所用版本。动态 stars/forks 与外部依赖可用性未被用于推导控制或学习有效性。[固定 LICENSE](https://github.com/RLinf/RPent/blob/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/LICENSE)、[arXiv 版本记录](https://arxiv.org/abs/2607.08448)

## 四、问题与后续验收边界

**本轮未发现需要否定 Harness 主路线或重定义已有关键契约的阻断问题。** 以下是可定位的补强，均不以“尚未运行 gate”冒充逻辑失败：

| 级别 | 精确位置与反例 | 建议修法／验收 |
|---|---|---|
| 非阻断：实施验收补强 | 01 行 257、02 行 47/T08：motion 占住原 Toolkit，observe 排在同一锁后，实际直到动作结束才送图 | 给既定“独立事件监控”补一个明确用例：长工具未结束时连续送达多批有时间戳的新观察；卡死工具时观察与本地保持仍可运行。不得把模型 `async` 开关作为通过证据 |
| 非阻断：来源可追溯性 | 09 行 86/90：`RL 接口为 skeleton` 只接博客，冻结六文件未给具体 RoboRSI 文件和 SHA；本轮未独立核到该文件 | 补原审查时的固定源码直链与符号；在补齐前仅把它写为既有核查记录，不作为优先级的唯一决定依据。本轮支持的是 RPent 模块适配理由 |
| 非阻断：导出实现细节 | 09 行 43、02 行 51：直接用原 `export_lerobot` 混两个 task_language 会被拒绝 | 在 B4 实现说明中写明双目标分别导出并合并加载，或修改导出器支持逐回合 goal；加入正反各一条的最小导出／重载用例 |
| 低优先级：符号准确 | 09 行 38 的链接文字写 `EpisodeRecorder`，实际类名为 `EpisodeWriter` | 改链接文字，防止开发者查找不存在的类；不影响正文对记录结构的判断 |

仍需实测的 gate 包括驱动保持／取消延迟、GPT 工位判断和局部纠正、目标条件实际消费、固定槽有效 TD 密度、代码权限隔离、双向 policy 独立提升。文档已将它们列为进入后续阶段的条件，本审查不将它们标成已完成，也不因缺少实验结果自动判 FAIL。

**最终结论：PASS（R02 Harness/RPent 设计与证据审查；不代表实现、部署或无人学习实验已通过）。**
