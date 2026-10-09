# R11 独立 Harness／控制／融合审查

结论：**PASS；必要修订问题数 0／12。** 仅为冻结文档审查，未作软件、学习收益或真机验收。2026-09-23。

先枚举关键技术点：①长工具期间观察独立性；②取消与实体保持；③设备唯一写权；④初始化副作用；⑤入口实际执行语义；⑥DAgger 标签的状态分布与质量；⑦反馈纠正的信息时刻；⑧真实轨迹与纯建议分流；⑨迟到评分／终局时间；⑩共享双向及异常恢复；⑪TRIAL 与发布；⑫候选联合接入及通用性。

只读指定科学家五份入口；未更新知识库、创建 goal、安装、训练或操作机器人，未读旧轮及他人审查。科学输入仅本轮九份 Markdown：A/B/C 深读，其余读相关章节。下列路径相对 `input/`，行号对应冻结文件。

| 代号 | 冻结输入 |
|---|---|
| A | `03_RL_Harness自主学习系统_20260922/01_RL_Harness真机自主学习技术方案.md` |
| B | `03_RL_Harness自主学习系统_20260922/02_接口契约与开发验收.md` |
| C | `03_RL_Harness自主学习系统_20260922/06_异步动作时间轴与学习目标.md` |
| E | `03_RL_Harness自主学习系统_20260922/README.md` |
| D | `04_RL与Harness扩展调研_20260923/01_RL与Harness开源基线深度调研报告.md` |
| R/U/H/P | 同目录 `research/01_VLA_RL扩展调研.md`、`02_自主学习与复位扩展调研.md`、`03_Harness扩展调研.md`、`04_训练平台与开源生态核查.md` |

## 本轮实际访问的一手证据

以下均为本轮新打开的正文；只列实际读取范围，源码采用网页零基行号。

| 编号 | 固定 URL 与实际范围 |
|---|---|
| S1 | [RPent Toolkit](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/tools/toolkit.py)：`execute_tool` 234–299、`cancel_active_and_wait`／`raise_if_cancelled` 322–335；另打开输入所引 `eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1` 同文件相同函数。 |
| S2 | [RPent API loop](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/planner/api_loop.py)：`_build_tools` 670–689、`_make_tool_function` 765–775。 |
| S3 | [OpenETA registry](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py)：`ToolSpec` 22–60、`ToolRegistry.call` 258–350、`_invoke_tool_handler` 1116–1149、取消结果 1154–1180。 |
| S4 | [Show preemption](https://raw.githubusercontent.com/showlab/Show-Harness/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/preemption.py)：全文 0–73，重点 `InterruptibleDecider.decide`。 |
| S5 | [Show DAgger](https://raw.githubusercontent.com/showlab/Show-Harness/137d5718c3b7af0150764d8f9beeb252c9f2794a/plugins/dagger/plugin.py)：0–147，`DaggerPlugin.on_key`、`has_intent` 和 `drain` 开头。 |
| S6 | [Show real runner](https://raw.githubusercontent.com/showlab/Show-Harness/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/real.py)：0–24、`RealEpisodeRunner.run` 128–254，含初始 RELEASE；未读成全部 Piper 路径。 |
| S7 | [Strands run_policy](https://raw.githubusercontent.com/strands-labs/robots/4d0203161a587e29d7912c99da74878e8f989544/strands_robots/tools/run_policy.py)：`_read_parquet_truth` 74–153、`run_policy` 参数及语义 156–295、结果／落盘检查 521–665、`_finalize_episode` 703–742。 |
| S8 | [Strands Robot](https://raw.githubusercontent.com/strands-labs/robots/4d0203161a587e29d7912c99da74878e8f989544/strands_robots/robot.py)：模式／mesh 分支 559–650、`_run_device_connect_foreground` 924–1013。未追完驱动 stop，不声称证明其实体停止能力。 |
| S9 | [DAgger 原论文](https://proceedings.mlr.press/v15/ross11a/ross11a.pdf)：§2 专家代理损失、§3 Algorithm 3.1 与 Theorem 3.1–3.4，PDF 第 2–4 页。 |

另读 OpenETA 同提交 `agent/runtime/planner.py` 工具前置约束，未核出持续观察实现。

## 恰 12 个反例问题及判断

### Q01 长 motion 卡死时，RPent 的只读 observe 会不会一起失效？

定位：B:43–58、115–140。证据：S1 在检查只读属性前已经拒绝重叠工具，取消等待工具返回；S2 把工具注册为 sequential。判断：**通过，待实施门槛。** B:58 已要求观察订阅 Gateway 的独立事件通道，并用长工具卡死检验新观测、取消与本地保持。必须实际实现该通道；开启模型并行工具不能代替它。

### Q02 OpenETA 已返回取消，旧 handler 却继续发运动，新 owner 能直接接手吗？

定位：H:250–256，B:117–146、394。证据：S3 的取消路径抛弃等待中的结果，daemon worker 并未被强制终止；工具新观测义务也不是硬件停止。判断：**通过，待实施门槛。** 文档要求旧代际失效、在途状态对账及 quiesce 凭证；不能以会话关闭完成交接。线程仍活着时拒绝其后续旧租约命令，是既有 Gateway 契约的实现责任。

### Q03 Show 丢弃旧 VLM 结果后，是否可能仍放开正在持物的夹爪？

定位：A:159–169，H:103–124，B:T32/T33/T38。证据：S4 只管理推理结果；S5 是键盘意图覆盖；S6 的 runner 启动调用 RELEASE，最终 DONE 充当上游成功信号。判断：**通过，待实施门槛。** 当前设计明确禁用隐式启动运动，解释器只产提案，DONE 不写任务奖励。不能把上游 runner 整体挂成新的设备控制循环。

### Q04 Strands 写着支持 RTC，调用 run_policy 就能证明异步执行和可靠停止吗？

定位：H:138–148，B:392–396。证据：S7 该入口默认 fast mode，并说明 chunk 消费规则；实际 episode 数从记录元数据核对。S8 区分 real/sim、mesh 和关闭资源结果。判断：**通过，待实施门槛。** T38 已要求固定入口、模式、provider、horizon 和消费索引。记录计数并不证明逐步动作与 stop_ack，本审也未替全部 Strands 路径作保证。

### Q05 learner env、恢复器与评测进程同时 reset，是否会出现第二条设备写通道？

定位：A:251–262，B:113–146、297、378。证据：三者提交统一 Gateway；设备级独占、代际、命令 ID 去重覆盖 reset。判断：**通过，待实施门槛。** ACK 丢失不得重放未知增量，重启先对账再运动。T04/T08/T09/T31 覆盖该反例。

### Q06 零成功 policy 收到有误 GPT 标签，称为 DAgger 就能保证改善吗？

定位：A:29–41、131–141、281–285，U:169–184。证据：S9 是访问状态上的专家标注与聚合，并带学习假设；S5 的人工意图入口也不是自动教师质量保证。判断：**通过，待验证效果。** 文档没有借理论保证 GPT 正确，要求局部纠正可靠性与同预算动态 BC 对照。保持基础示范、分离 BC 质量和 TD 资格；零成功仍须有启动信息。

### Q07 GPT 看帧 107 后重抓，能把整个成功轨迹贴为帧 100 的动作 chunk 吗？

定位：A:133–165，C:165–190、237–255。证据：冻结输入区分同信息集 U、事后监督和逐步反馈；孤立标签不得重复成 n 步，flow 的未知输入也不能只靠 loss mask 隐藏。判断：**通过，待实施门槛。** 首版确会隔离部分纠正，须测有效 BC/TD 密度；如密度不足，应触发协议或路线比较，不可倒填历史。

### Q08 建议 A 未执行，policy 执行 B，能将 A 配 B 的后继给 replay 吗？

定位：B:205–217、243–257、369，C:63–95；R:290–301、P:27–35。证据：原始事实、调度请求、纯标签和训练 manifest 分离；只有真实事前 admission 的原请求才适用 terminal 例外。判断：**通过。** A 可持久用于合格 BC；不能借 B 的后果。请求已成立但终局取消激活，与离线影子查询不是一类，接口已写清。

### Q09 正向迟到“成功”覆盖反向缓存，或用回复时间定位终局，会怎样？

定位：B:165–183、T18/T20/T21，C:223–231。证据：历史评分、历史动作标签、当前控制资格三分；缓存绑定目标、episode、证据及版本。终局事件时间与返回时间分开，稳定性须证据充分才成立。判断：**通过，待实施门槛。** 重复回调去重，未知帧保持 pending；已提交 U 的事实不因晚评分被抹掉，也不能使旧目标复活。

### Q10 正向放到 B 边缘后难以反抓，恢复程序回 A 能算反向共享 RL 成功吗？

定位：A:88–109，B:219–225、259–265、T17/T19/T24。证据：同一 θ、Q/target/采样均接目标；切换前检查 init_set，异常恢复另记，正常反向仍是学习任务。判断：**通过。** 困难起态、整理和中断计成本；不能以两个方向各自最佳模型冒充共享 checkpoint，亦不能让正向价值跨目标 bootstrap。

### Q11 TRIAL 代码改了 rubric 后自报成功，是否会自动晋级并污染 BC？

定位：A:153–157，B:185–201、271–297、T23/T27。证据：候选不得改保护、评分、预算；受限真实试验后固定核验与回归，数据先隔离，标签撤销追到后继权重。判断：**通过，待实施门槛。** 同模型换角色不当独立真值；版本回滚不当物理回滚。既定范围内自动试验符合用户需求，不追加逐次人工审批。

### Q12 换原生 learner 或更通用 Harness 后，是否把品牌适配和功能列表当成联合通过？

定位：E:9，A:264–297，D:187–221，B:T34/T36/T37/T38/T39，R:366–370。证据：选择轴分为学习、骨架、辅助收益；不同本体 schema 回放，目标／队列／噪声／loss 单独接入；RAPolicy hold 不冒充连续执行。判断：**通过，待比较。** RPent 仅先验证，其他已有候选可按同门槛替换；AgileX 只算首次部署成本。未扩充候选池。

## 判定边界

12 问未发现必要文稿修订。观察独立性、实体交接、教师质量、数据密度、代码隔离及双向独立收益仍须实施验证。自适应 BC、特权监督、微步 RL 属可选优化。进入真机阶段须按 B 验收，本报告未执行这些测试。
