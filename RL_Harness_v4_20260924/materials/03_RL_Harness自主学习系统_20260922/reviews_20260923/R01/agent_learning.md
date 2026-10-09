# R01 独立审查：共享正反策略、Harness 纠正与在线 RL

审查日期：2026-09-23。冻结输入：本轮 `input/` 中主文、接口、证据表和 README（v1）。本报告不读取其他审查员报告，不修改主文；原始源码为静态阅读，未运行训练或机器人。

**本轮结论：FAIL。** 不是因为尚未完成真机验证，而是冻结稿存在必要设计缺口：首版仍是两个独立策略；goal 没有落实到候选算法的 critic/edit；正常异步部分执行被简化成接管时的前缀截断；算法选择尚未用新约束重新评估。已有“真实数据与未执行标签分流”的处理应保留，不应因这轮修改丢失。

## 1. 学习前枚举的技术要点

1. 同一架构、同一参数、两个任务条件是否被区分；policy、Q、replay 是否具有一致 goal。
2. 正反均接受 RL 和 Harness 纠正；物理循环如何划分逻辑任务终局。
3. DAgger 的纠正来源是否必须是人，以及动作标签如何与 RL 共存。
4. 长期纠正库、真实 replay、有效动作标签的采样和梯度流。
5. 异步调度造成的 committed / execution / discarded 区域与普通 chunk 前缀执行的差别。
6. 延迟状态、已承诺队列和中途观测是否进入 learner，而不只是写入日志。
7. 共享训练的数据失衡、负迁移与发布验收。
8. 更新 base VLA 时，动作空间、latent 动作、表征缓存、target 和历史 replay 的兼容性。
9. EXPO、ConRFT、ARLI、SmoothRL 的原始实现究竟支持什么；改造是否被冒充成原论文能力。
10. 少量正确纠正、低成功甚至零成功起点下，哪一条路线在方法上更直接、在工程上更可审。

## 2. 本轮实际独立学习

### 2.1 原始方法和本轮新认识

- [DAgger 原始论文](https://proceedings.mlr.press/v15/ross11a/ross11a.pdf)：纠正机制的核心是聚合当前策略访问状态上的动作标签。标签生成者不必是人；标签也不必在本次 rollout 被执行。仅在少量触发点标注属于选择性聚合，不能直接继承原始全状态查询分析。**本系统应写“由 Harness 生成纠正并聚合”，不是额外假设一套强教师 policy。**
- [UVFA 原始论文](https://proceedings.mlr.press/v37/schaul15.pdf)：共享目标条件价值函数是有明确方法基础的设计；同一状态在不同目标下具有不同价值。对本项目，两方向可以共享网络，但每条目标、奖励、终止和 bootstrap 都应一致。
- [ConRFT 原始论文](https://arxiv.org/html/2502.05450v2)及固定源码：有真正的 consistency BC＋Q actor 目标，但已审公开实例是单步动作；不能把“已有 BC＋RL”直接推成“已有共享双目标异步 chunk RL”。
- [SmoothRL 原始论文](https://arxiv.org/html/2608.29768v1)：其关键是训练时表达和部署相同的执行窗口，对新策略的 value gradient 只作用于执行区。论文实例仍是冻结 base＋RLT 类附加头和有界修正，因此不能宣称它天然解决弱 base 的能力边界。本文是方法参考；本轮没有取得可核验的官方完整训练源码。[官方项目地址](https://www.astribot.com/research/SmoothRL)抓取失败，不据此断言“绝对未开源”。
- [ARLI 原始论文 v2](https://arxiv.org/html/2608.23831v2)：增强状态包含已承诺动作，较新的中途观测提升反应性；其 RL 动作是冻结 VLA 的去噪输入。因此 BC 持续改 base 时，历史 latent action 的含义可能变，不能原封不动复用 latent replay。论文原则值得采用，不代表应整套采用 latent steering。

### 2.2 本轮直接读取的源码，而非只复述旧笔记

| 固定源文件 | 本轮确认的实现事实 | 对修订的作用 |
|---|---|---|
| [EXPO `expo_ft.py`](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/expo_ft.py) | `compute_q`、edit 主要接图像编码、proprio 和动作；`sample_actions` 取 `:replan_steps`；TD 使用 `discount ** replan_steps` | 共享多目标和异步中段不是修改 runtime 名字就可得到，Q/edit/target/采样均须改 |
| [EXPO `batch_utils.py`](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/batch_utils.py) | VLA 采样保留 tokenized prompt；critic 字段只抽相机和状态；动作仍截前缀 | “VLA 收到语言”不等于 critic 已知道方向 |
| [EXPO `replay_buffer.py`](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/replay_buffer.py) | 顺序记录回填 action chunk，从后续记录取得后果；dataset 导入默认 HIL/success | goal/source/episode 边界需要阻断跨界回填；不能把孤立纠正标签塞入这条真实序列 |
| [EXPO `batch_processor.py`](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/batch_processor.py) | 真实回放与 success-only actor 调度有实现 | BC 纠正必须有自己的采样资格，不能仅等待完整成功或自动标记成功 |
| [ConRFT `conrft_single_octo_cp.py`](https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/agents/continuous/conrft_single_octo_cp.py) | `forward_policy` 接 tasks；`forward_critic` 的 `action_embeddings` 形参没有传入 critic，实际仅 observation/action；actor 明确为 BC 权重×重建＋Q 权重×价值项；动作检查为 7D | 不能看到函数形参/任务 embedding 就认为 critic 已 goal-aware；ConRFT 可借鉴完整头和 BC，但 chunk 化是新增工程 |

代码中的命名与协议必须以实际下游消费为准。例如保存在 buffer 的 `goal_id`，如果没有进入 Q 网络，不能修复目标混叠。

## 3. 独立审查问题、证据、判定与修法

### Q1：首版是否是同一个共享参数 policy，在两个 goal 下进行 RL？——FAIL

冻结稿主文 §12 明确“首版分别维护双向 policy／head”；H6、P6 又把共享留到后续。这与最新明确要求不一致。修订应选定一个共享参数的 `πθ(obs/history, goal, execution_context)`，两方向使用同一优化器和发布包；保留 per-goal 数据配额与指标，并非保留两套独立主策略。独立策略只作为可选消融。

### Q2：actor、critic、edit、target 和样本的 goal 是否贯通？——FAIL

现有文档仅把合并 goal-conditioned 模型作为将来注意项。上表源码证实 EXPO/ConRFT critic 都不能默认从现成输入辨识方向。须在所有训练/推理通路显式引入 goal；batch 每条携带任务条件，bootstrap 使用同一目标；执行队列保留 goal epoch。相同观测下交换 A→B/B→A 的测试必须检查张量真正进入 actor/Q，不能以两个输出“应该不同”作唯一神经网络正确性测试。

### Q3：正向成功后直接反向，是否把反向回报并入正向价值？——局部 PASS，需落实接口

旧稿已区分目标边界、任务成功和下方向合法起态，这一原则正确。共享权重不等于共享 episode：A→B 的任务终局关闭该目标回报，B→A 新建逻辑 episode，物理场景可连续。如果某次中止只是行政截断，不应伪造终止；但也不能从后继的另一目标 bootstrap。同方向 Harness 接管应保留真实命令和转移，不把其成功冒充无辅助策略成功。

### Q4：是否仍假设 DAgger 的教师是人或上游强 policy？——FAIL（概念与表达）

旧稿实际上已允许代码/规划器供给，但高频“任务教师/学生/teacher”叙事仍造成不必要模型假设。应统一成“共享任务 policy”和“Harness 观察、纠正、执行模块”。引用原论文时保留 expert/teacher 并说明那是文献角色。本项目的核心损失是“可信 Harness 纠正的 BC/FМ＋真实交互的 online RL”，DAgger 描述数据获取机制，不是独立备选模型架构。

### Q5：未执行纠正能否长期参与 BC＋RL，且不伪 TD？——PASS，需改名

旧稿 §11 和接口已明确分型，方向正确。可以统一底层存储，但训练视图必须分开：执行过的命令和真实后果可供 TD；历史状态上的未执行标签可以供 actor 的 BC/flow。保护初始数据，按 goal/质量/source 分层；“长期存储”不等于永久等权训练。不要为改术语将两类数据重新混成 transition。

### Q6：一次预测是否只会执行前缀？——FAIL

旧稿 §11.3 以“20 步执行前 6 步，剩余未执行”为主解释，不覆盖常态异步。必须按全局帧索引表达：新 chunk 的前段在推理等待期间已由旧 chunk 承诺；新 chunk 只贡献中段；尾段被下一次替换。实际贡献 mask 与最终执行命令需要对应，不能只存 `executed_length=6`。SmoothRL 的执行区 value gradient 和 ARLI 的 delay-state 要进入损失和数据契约。

### Q7：只记录队列、实际动作和 gamma^k，是否足以使 RL 正确？——FAIL

不够。队列会改变未来状态，即使观测完全相同也可能有不同在途动作。必须说明 learner 的状态如何带 committed queue/时间和相关观测、Q 学哪个控制边界，以及 target 如何重建同样执行调度。`Q(s, executed_actions)` 加可变折扣但 bootstrap 假设立即同步动作，仍会错配。延迟字段仅作日志不构成近 Markov 化。实际部分步不兼容样本的隔离处理应保留。

### Q8：共享训练是否控制反向/易任务垄断样本及梯度？——FAIL

旧稿有“独立双向预算”，但独立策略时期的预算不足以约束一个共享优化器。修订至少需要：每目标最低采样配额、分别记有效 TD/BC 数和质量，目标内归一化损失统计；报告两方向无辅助能力，发布禁止用一个方向的提高掩盖另一个方向的关键退化。先不自动引入复杂梯度手术，失衡与负迁移出现后再消融。平衡不是永远强制 50:50：可按覆盖调整，但不能让任一目标饿死。

### Q9：执行区 mask 是否也等于 BC 标签 mask？——FAIL（须明确区分）

value-gradient 的 execution mask 来源于这次调度的真实贡献；BC label mask 来源于标签本身何处可信。一个完整可信的未执行 Harness chunk 可以提供比当次实际执行区更长的监督，但没有 TD 后果；一个真实执行却不正确的 policy 动作也不因此成为 BC 正例。必须分开 `execution/contribution mask`、`label validity/quality mask`、`terminal/discount mask`，不能共用一个 `valid`。

### Q10：持续 BC 改 base，是否与 ARLI latent replay 直接兼容？——FAIL（新候选必须补）

ARLI 的 latent action 通过冻结 base 变成真实动作。改 base 后，相同 latent 不一定生成原动作。因此如果整套采用 ARLI，要分 base 冻结的学习 epoch、记录 decoder 版本，并禁止把旧 latent—后果直接当新 decoder 的数据。可改用原始动作 critic，但那已是另一种学习设计。对于 EXPO/完整动作头路线，旧的真实物理命令可在动作/任务语义一致时继续用于离策略 Q；更新编码器仍需重算缓存。

### Q11：共享模型更新/发布会不会让旧推理、旧 goal、旧表征混进新任务？——部分 PASS，须扩展

旧稿有发布包、缓存清除和 chunk 版本冻结，基础正确。共享任务后还需为 goal 切换触发队列失效、等待取消确认、重观测；旧方向晚到结果不能入新方向队列。policy 参数、编码器、normalizer、调度/queue 语义绑定；同一 rollout 决策记录实际使用版本。离策略不等于任意语义过期 replay 都有效。

### Q12：BC＋RL 是否一定比纯 RL 或 SFT 稳妥？——条件 PASS

这是合理主策略，不是定理。可信纠正通常给弱策略新增行为支撑，Q 利用失败后果；但错误 Harness 标签、强 BC 锚定和过量重复采样仍可限制探索。质量拒答、来源追踪、BC 权重调整及同预算“仅纠正聚合”和“BC＋RL”对照仍必要。应明确这些是对用户想法的原理约束，而非转回要求人类教师。

### Q13：改成完整动作头后，就一定比残差路线可达吗？——FAIL（若如此表述）

完整头消除了紧贴弱参考动作的结构限制，但损失了一部分预训练运动先验，少量数据可能学不稳。冻结 VLA 表征也可能缺少精细抓取信息。需要先用双向可信数据验证头的条件动作拟合和闭环可执行性，再验证 RL 增益；必要时初始化为现有策略蒸馏的头，或保留可退火的参考正则。不能因形式自由就声称更高可行性已被证实。

### Q14：正反样本能否直接倒放或自动交换目标增加数据？——PASS（旧稿已有正确边界），建议接口明示

动作倒放不等于可逆动力学。共享模型可以从两类真实数据学习共享抓取表征，但不能把 A→B 轨迹时间倒序当作 B→A 真实转移。若以后引入目标重标记，须重新计算该目标的奖励/终止，确认目标变化不影响动作产生和转移条件；第一版不需引入 HER 才能满足共享要求。

## 4. 重新联合选型：建议的实现形态及反证条件

### 4.1 首选方法形态

我建议最终目标采用 **共享目标条件 VLA 表征＋可学习完整动作头＋原始动作空间异步 actor–critic＋Harness BC**。两方向共用参数；用 SmoothRL 的执行区 credit 原则和 ARLI 的 committed/mid-observation 原则定义训练与部署契约；Harness 是纠正数据源，不能把弱 base 的参考动作当作永久唯一锚点。

这个形态与需求最匹配的理由是：它直接消费真实动作纠正，无须为 Harness 动作反演 latent；两方向各自的失败与成功都能进入 goal-aware Q；完整头允许偏离弱初始动作；BC 和 Q 都可明确定位到可训练动作模块。

**但这是一项拟议改造，不是名为 SmoothRL/ConRFT 的现成开源成品。** SmoothRL 原实例仍有界残差，ConRFT 已审公开头是单步。将两者扩成 shared-goal、queue-conditioned 完整 chunk 头与相应 Q，需要新的网络输入、target、replay builder 和梯度测试。不能写“拼起来即可”“B 比 EXPO 少改”或以机构声誉证明改造有效。

### 4.2 各路线具体取舍

| 路线 | 匹配处 | 必要新改动/缺口 | 建议位置 |
|---|---|---|---|
| SmoothRL 原则＋完整动作头＋Harness BC | 原始动作监督和异步执行区最直接，可解除弱参考动作硬边界 | 不是原论文实例；完整 chunk 头冷启动、共享 goal/Q、代码实现与表征可用性需验证 | 主拟议方法形态；先通过最小数据/梯度预检 |
| EXPO-FT 改造 | 现有 π 推理/监督链可复用，真实动作 replay 与 base FM 有代码落点 | Q/edit/target 的 goal 和 committed context；非前缀执行目标；独立纠正池；局部标签的 FM 语义 | 最重要的可运行参考/条件回退；不能未经改造视为最终异步算法 |
| ConRFT 改造 | 已有完整动作头、BC＋Q 和离线到在线训练实现 | 单步到 chunk、goal-aware Q、延迟状态/队列、纠正采样；骨干迁移与动作转换 | 头部/损失工程参考，或低延迟单步路径的条件候选 |
| ARLI 原算法 | 异步状态建模明确，已有 π0.5 真机证据 | latent 对纠正动作难直接回归；base 改版使 latent replay 语义变；冻结 base 能力边界 | 必读机制和对照；不作为本项目 BC＋持续能力扩展的首选整套 learner |
| 原 HIL-SERL | 真实混合控制和回放框架可信 | 已审默认 actor 无显式 BC，非 VLA、非上述异步 chunk learner | 工程基础设施参考，不以有 demo buffer 等同目标方案 |

### 4.3 哪些证据会推翻首选

1. 如果完整头在同一双向示范预算下不能拟合可信动作或无法保留已有可用运动，而原 π FM 可稳定做到，应优先 EXPO/原生 π 路线，不能强行坚持重学完整头。
2. 如果 Harness 只给短动作，而原生 π 的部分 flow 标签训练无法证明对齐，完整头的直接局部 BC 优势更大；仍需验证闭环，不只看 loss。
3. 如果延迟/队列机制无法稳定重建，应先固定执行节拍、明确推理失败处置再开始在线学习，不能靠更大的模型或增加数据遮掩 Bellman 错配。
4. 如果共享模型造成任一方向关键退化，先调整 goal 表达、覆盖和采样；独立策略可作诊断对照，但正式方案不能未经用户知情悄悄退回两套主策略。

## 5. 下一轮必须可审查的交付变化

- 一张明确显示“同一 policy，目标 A→B/B→A；两方向 BC＋RL；Harness 观察/纠正”的图和一次完整往返例子。
- 学习契约写清 goal、committed queue、动作全局帧索引、实际命令、贡献 mask、BC label mask、policy/goal/scheduler 版本。
- 选定一种首版异步决策与 Q 的时间约定；给出包含推理等待、实际中段、替换尾段、Harness 中途接管、目标切换的例子；不能只罗列候选公式。
- 把论文原生支持、确定工程适配、尚待验证的新算法改动分开；不要把 SmoothRL 的执行区规则与 ARLI 状态增强的拼接写成已验证算法。
- 共享采样和双向发布门槛落实到接口验收；纠正数据与真实 TD 分流机制完整保留。

本轮针对 v1 的总体判定为 **FAIL**。以上必要缺口消除后，应再独立学习并审查新冻结版本；本文不预判后续 PASS。
