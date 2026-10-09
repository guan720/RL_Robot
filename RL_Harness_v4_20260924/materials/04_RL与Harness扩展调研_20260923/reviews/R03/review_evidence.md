# R03 独立审查：覆盖、证据、选型与可读性

审查日：2026-09-23。对象仅为本轮 `input/` 中的技术四文、调研总报告与四份专题；未读取历史审查结论来决定本轮结果，未修改冻结输入。本文为静态文档与第一方来源交叉审查，没有安装上游框架、运行训练或验证真机。

**结论：PASS。审查问题 16 项；必要修订 0 项；可选阅读改善 2 项。** 本结论只表示本审查范围内未发现需要阻止该版通过的证据、选型或理解问题，不表示拟议系统已运行、全部上游代码已审完或算法组合已被实验验证。

## 1. 先列技术点

1. 任务是同一目标条件 policy 的正反向学习；复位辅助、系统救场和 policy 参数进步需分别计证据。
2. 动作参数化、RL 更新对象、数据条件和执行时序是四个不同比较轴；完整头、原生头、编辑器及 latent 方法不能只按论文名称排序。
3. RT-EXPO 要分别核普通 SFT／RTC-SFT 基线、人工与数据预算、初始化条件、两种延迟条件，以及 base BC 与 edit/Q 更新。
4. 原生头候选要核 TD3＋BC 的数据池与仿真规模，并单独核十示范 RECAP 的弱起点、选择偏差和标签版本。
5. RLinf／LeRobot 的 worker、mixer、RTC 等组件存在，不等于同一配置已满足共享 VLA＋纠正 BC＋队列 TD。
6. Show-Harness 的语义动作解释、RPent 的认知工具、Strands 的设备与训练接口处在不同层；复用时必须保留唯一执行权与真实数据记录。
7. 框架通用性优先于首台机器品牌匹配；跨本体接口测试不等于共享权重直接迁移。
8. 原始来源、固定版本、公开代码、权重／数据及许可证应分别核查；关注度不替代独立复现。
9. 开发者应能从一个具体失败流程追到数据资格、目标函数、接口验收和选型切换条件。

## 2. 本轮独立浏览与学习记录

以下均为本审查实际打开并阅读的第一方资料；不是仅复述冻结稿的参考文献。读取日期均为 2026-09-23。

| 编号 | 第一方来源与实际阅读位置 | 本轮核查用途 |
|---|---|---|
| S1 | [RT-EXPO 原论文 v1](https://arxiv.org/html/2609.18207v1)，§IV-C、§V-C／Table I、§VI、附录 VII-D／VII-E | 比较基线、人工边界、启动条件、延迟及更新对象 |
| S2 | [verl-vla π₀.₅ TD3＋BC 官方配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html)，配置与逐 checkpoint 结果 | 直接更新对象、仿真资源、BC/CQL、评测分母 |
| S3 | [verl-vla 十示范 RECAP 官方配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html)，初始数据、结果、plain-SFT control、Published artifacts | 少数据起点、续跑选点、最终数据和历史标签区别 |
| S4 | [TD3＋BC 初始模型卡](https://huggingface.co/Miical/pi05-libero-spatial-sft-step-100)，Lineage／Training configuration／License | 100 步 SFT 与 432 episodes 数据池、模型许可标签 |
| S5 | [RLinf-USER 官方资料](https://rlinf.readthedocs.io/en/latest/rst_source/resources/publications/rlinf_user.html)，Algorithms／Results／Hardware | CNN/Flow RL 与 π₀ HG-DAgger 的边界 |
| S6 | [RLinf Piper 官方文档](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/piper.html)，Overview；[RTC 官方文档](https://rlinf.readthedocs.io/en/latest/rst_source/guides/rtc.html)，概述及真机启动 | 硬件检查与受支持训练流程、RTC 评估与训练的区别 |
| S7 | [LeRobot 固定 mixer 源码](https://raw.githubusercontent.com/huggingface/lerobot/fbb811fca92504439792b97d216f0d00c2268382/src/lerobot/rl/data_sources/data_mixer.py)，`sample`／`get_iterator` | transition 混采和至少一个 online 样本的实际实现 |
| S8 | [Show-Harness 固定 real runner](https://raw.githubusercontent.com/showlab/Show-Harness/137d571/core/runners/real.py)，文件说明、`run`、DAgger／DONE 分支 | 启动 RELEASE、键盘干预、完成信号与执行循环 |
| S9 | [RPent 6ee7069 提交](https://github.com/RLinf/RPent/commit/6ee7069)，父提交、变化清单与 RoboCasa／RoboTwin 新增文档 diff | 旧审计版本关系、普通 reset 与成功命令导出范围 |
| S10 | [Strands 固定 RL 文档](https://raw.githubusercontent.com/strands-labs/robots/4d0203161a587e29d7912c99da74878e8f989544/docs/training/rl.md)，SimEnv／PPO／FastSAC；[固定机械臂文档](https://raw.githubusercontent.com/strands-labs/robots/4d0203161a587e29d7912c99da74878e8f989544/docs/robots/arms.md)，Compatibility notes | 从零仿真 RL、无示范路径和真实／模拟设备边界 |
| S11 | [UniIntervene 固定 README](https://raw.githubusercontent.com/Denghaoyuan123/UniIntervene/40f461f97573383c9cc8fdba43df56f9eb5bbea1/README.md)，发布范围、Pipeline、smoke test | 已开放离线算法与未包含部署、权重、轨迹的边界 |

访问限制：Strands 渲染站点的 RL 页面两次返回内部错误，随后成功读到同固定 SHA 的原始文档；没有据此判定项目不存在或缺文档。没有逐个重新抓取所有候选的 stars／下载数，也没有把本轮静态访问称为完整 clone 或复现。

## 3. 逐项审查问题与充分性

定位均相对于 `input/`。简称：技术主文＝`03_…/01_RL_Harness真机自主学习技术方案.md`，接口＝同目录 `02_接口契约与开发验收.md`，异步＝同目录 `06_异步动作时间轴与学习目标.md`；总报告＝`04_…/01_RL与Harness开源基线深度调研报告.md`；VLA／自主／Harness／平台＝该目录 `research/01`～`04` 对应专题。

### Q01：RT-EXPO 的 42% 起点是否误写为 RTC-SFT，平均分母是否明确？

定位：总报告 §4.2 第 76 行；VLA §4.1 第 111 行。

核查：S1 Table I 支持普通 SFT 约 42%、RTC-SFT 60%、RT-EXPO 约 97%；每任务评测 30 次。稿件明确指出跨任务均值不是单任务样本率，没有把不同起点混在一起。**充分：通过。**

### Q02：自然推理时延、100 ms 注入和 d 步旧观测是否被合并成一种实验？

定位：总报告第 78 行；VLA §4.4.1 第 152～154 行；技术主文第 275 行。

核查：S1 附录区分 wall-clock 与 chunk-delay；Dynamic Picking 不额外 sleep。稿件同时保留自然推理、注入及离散步预算的区别，要求本地分别测量。没有声称四任务统一承受同一额外延迟。**充分：通过。**

### Q03：“十分钟、无干预”是否隐去了 SFT、人工复位及成功启动条件？

定位：VLA 第 113～115 行；总报告第 76 行；技术主文 §13。

核查：S1 的交互上限不含全部工程／训练墙钟；存在人工复位，训练前以任务示范获得约 30% 或以上成功率。稿件如实限定，还把值守、示范、复位、标奖分开计成本，没有外推为零成功、全天无人闭环。**充分：通过。**

### Q04：base 通过成功数据 BC 改进，是否被写成 Q 直接训练整个原生动作头？

定位：VLA §4.3 第 123～132 行；总报告第 80～84 行；异步 §11。

核查：S1 区分基础 VLA 的 prefix-conditioned BC 和有界编辑策略的价值改进。冻结稿区分三条更新路径，且把动作支持诊断、新增可靠 BC 与独立协议比较写进路线。没有将其降格为永久冻结 base，也未宣称其突破能力已证。**充分：通过。**

### Q05：verl-vla TD3＋BC 是否真是原生 policy 更新，是否夸大少数据与实体可达性？

定位：平台 §4 第 43～47 行；总报告第 90 行；技术主文第 270 行。

核查：S2 明确不启用 DSRL noise actor，提供 32/50→40/50、8 GPU／32 并行仿真的参考运行；S4 显示初始模型数据池为 432 episodes。稿件全部保留这些限制，没有把 100 个 SFT optimizer steps 当 100 条或几条示范，也不据此给用户承诺卡数。**充分：通过。**

### Q06：十示范 RECAP 是否纠正了对整个平台的数据偏见，又避免用 best-of-run 冒充稳定提升？

定位：总报告第 91、98 行；平台 §11 第 105～109 行。

核查：S3 给出 10 条示范、三轮各 32 条 rollout、最终 106 条、最好 23/50，并说明续跑选点及显著回退；最终 indicator 由最后 value 模型重算。稿件准确记录，并将其列为第三方开放实现、仿真与发布级证据。**充分：通过。** 不需要为这一轮继续审完全部 RECAP 源码才允许将它列入候选。

### Q07：RLinf 是否因同时有 VLA、SAC、RTC 就被当作现成组合？

定位：平台 §2、第 96 行；总报告第 37、159～163 行；技术主文第 258、271 行。

核查：S5 的 π₀ 改进属于 HG-DAgger，S6 的 RTC 当前是评估路径，Piper 文档也仅保证硬件检查。稿件逐项分开，明确要新增 goal／queue、BC 标签支路与目标函数，并以 P0 联调决定。**充分：通过。** 当前优先验证有组件证据支持，但并未宣称无改造可达。

### Q08：LeRobot 示范混采是否被误当成显式 BC，确定性完整头是否暗套 SAC 概率？

定位：平台第 29～35、100 行；接口 T36 及第 395 行。

核查：S7 的 mixer 混真实 transition，`online_ratio=0` 仍至少取一个 online 样本；没有纯建议自动转 TD 的逻辑。稿件指出此限制，另设 BC 采样，并明确确定性头不能伪造 `log_pi` 套 SAC。**充分：通过。** 对运行时复用和算法替换的责任已有具体接口与测试。

### Q09：Show-Harness 的功能是否被拔高为独立奖励、设备停止或自动 DAgger＋RL？

定位：Harness §5.2；技术主文第 159～169 行；接口 T32／T33／T38。

核查：S8 默认启动执行 RELEASE，以最终 DONE 完成任务，DAgger 为人工键盘覆盖。稿件分别识别并禁止直接沿用；语义解释器只产提案，反馈决策不倒拼成起点 chunk。**充分：通过。** 这已成为验收条件，而不只停留在相关工作警告。

### Q10：RPent 新提交是否被历史审计无条件背书？

定位：总报告第 126、133 行；Harness 第 64、74、242 行；接口 §1.3。

核查：S9 的父提交与稿件一致，新增探索文档确实沿用环境 reset 并导出最终获胜命令。总报告只宣称读变化清单与新增文档，未宣称完整审完 28 个文件；技术接口仍以固定旧代码定位观察锁与工具边界。**充分：通过。** 专题措辞可进一步统一，见 O2，但未形成“新 HEAD 已全量通过”的错误结论。

### Q11：Strands 的通用接口是否被低估为缺品牌驱动，或被高估为真机 VLA RL？

定位：Harness §7.1、第 205 行；总报告第 141 行；技术主文第 273 行；接口 T37／T38。

核查：S10 的 RL 为 SimEnv 下的 PPO／FastSAC 从零训练；设备文档也明确真实与仿真路径。稿件把缺特定硬件驱动只计部署成本，把 BC／VLA／真机数据协议作为核心差距；同时允许底座以更低改造成本通过同一测试后取代 RPent。**充分：通过。** 没有按 AWS 品牌或 AgileX 支持表直接裁决。

### Q12：UniIntervene 是否仍因项目页占位被判无代码，或因算法开放就判完整系统开放？

定位：自主 §4.4 第 110～114 行；总报告第 115 行。

核查：S11 已发布离线七阶段，明确排除机器人部署、HIL-SERL 集成、轨迹、checkpoint 和记忆库，并将 smoke test 定义为组件测试。稿件按相同边界表述，恢复模块仍需先积累有质量数据。**充分：通过。**

### Q13：覆盖是否仍围绕旧完整头选型，缺少可能推翻它的主要路线？

定位：总报告 §§2、4、7、9；VLA §§3、5；自主 §§3、5；Harness §4。

核查：材料涵盖原生梯度／价值条件化、实时编辑、latent／残差、成熟 HIL、复位循环、自动纠正与训练平台；RT-EXPO、verl 原生头和通用 Harness 已进入具体比较门槛。Q-VGM／OTQL／LWD 的代码与资源限制有区分，不以“未找到”断言不存在。**充分：通过。** 当前没有必要无限扩大候选数量；优先实验主要分界更合理。

### Q14：开源、许可、热度和版本能否被读者分清？

定位：总报告 §7.2；VLA §7；自主 §8；Harness §§3.2、11；平台 §§7、10；接口第 385 行。

核查：稿件将论文、代码、权重／数据、依赖许可分开；S4 的 `other` 与底模限制没有被框架 Apache 覆盖。网页统计均带访问日与缓存边界，缺引用数不写零，第三方复现记未核验。固定 SHA 与移动网页也明确区别。**充分：通过。** 此处通过的是证据口径及已抽查关键资产，不是所有数字实时复核或完整许可证合规审计。

### Q15：默认完整头的选择是否变成无法推翻的结论，或用强 Harness 掩盖学习失败？

定位：技术主文第 19、225、264～277、311～324 行；总报告 §§8、9；接口 §6.2、T28／T34／T38。

核查：默认被定义为待验证工程起点；原生头先做同预算 BC／动作覆盖，方法和平台分轴比较，独立 policy、辅助系统、人工成本三套结果分开。评测集用途、试次预算与版本选择历史也有约束。**充分：通过。** 没有借跨论文分数认定优胜，也没有要求本次静态审查替代 P0／P1 测量。

### Q16：普通开发者能否从流程理解职责和训练意义，而不是只能记论文清单？

定位：README 第 7～31 行；技术主文 §§3、4、9、12；接口 §§1、7、8；异步 §§9～11；总报告 §§2、10。

核查：入口给阅读顺序；抓空流程连接观察、接管、记录、BC／RL 和双向发布；接口明确五桥职责，异步有六个可手算例子；证据集中到研究报告，技术文档明确拟议与待执行。**充分：通过。** 专题 shortlist 导航还可精简，见 O1，但现有读法足以获得正确总体理解。

## 4. 可选阅读改善（不计必要修订）

**O1：让 VLA 专题 shortlist 与总报告的新增对照互相可见。** 定位：VLA §8.1 第 263～269 行；平台 §11。VLA 的推荐表没有显式列出已在总报告和技术主文纳入的 verl-vla TD3＋BC／十示范 RECAP。可增加一条指向平台专题的短链接，避免只读专题的读者误以为原生头仍仅有“等代码”的 Q-VGM／OTQL。总报告和技术主文已明确最新选择，因此不构成当前选型遗漏。

**O2：统一 RPent 差异审核完成程度的措辞。** 定位：Harness 第 64、242 行，对照总报告第 133 行。建议把“需另做差异审查／必须读 diff 后判断”收窄为“已核父提交、变更清单及新增文档；其余关键实现仍需差异审计”。现稿没有错误承诺已完整审完，只是两处阅读时态容易让人多核对一次。

## 5. 结果边界

本轮没有必要修订项，故在证据、覆盖、选型及可读性范围判 **PASS**。未实测的接口、动作可达性、纠正质量、延迟预算、有效 TD 密度和双向提升仍是实施阶段的真实未知；稿件已将其明示为门槛，不能因这次文档通过而改写为已验证结果。算法／系统时序的其他独立审查结论不由本文替代。
