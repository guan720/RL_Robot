# RL_Robot 研究资料与路线分析（2026-09-23）

检索日期：2026-09-23。结合 `ROADMAP.md`、`notes_stage2.md`、`notes_stage3.md` 和当前扰动环境分析。下文的实验数字属于论文作者报告，本项目没有复现这些外部结果。

检索方式：arXiv 主题/标题搜索、原始摘要页、ENPIRE/RoboClaw 的 HTML 正文、Physical Intelligence 官方研究正文、HIL-SERL 官方 README，以及本项目已有的 RoboRSI 源码核对记录。部分 GitHub、Hugging Face 页面超时；列出入口不代表已经验证其最新版本能安装。近期条目如果只核对摘要，会注明证据范围。本次不是穷尽性综述，也不把预印本视为已独立验证的结论。

同日补充：核对 RPent / Harness VLA 论文 v4 正文、官方仓库及架构、记忆、性能、成本、flywheel 文档，见 §2.6。代码核对版本为 `6ee706935d28646828f70372ef0099c769cfe0c2`；未安装或复现实验。

## 1. 针对本项目的结论

最值得投入的组合是：**可复用的基础技能 + 失败恢复/复位调度 + 小规模在线 RL + 冻结评测与发布门禁**。对照阅读优先级：RoboClaw、ENPIRE、MEDAL/MEDAL++、HIL-SERL、RL Tokens、Q-Planning；再扩展到 ASPIRE、DPPO、FQL 和 Genie Sim。

项目已证明 SAC 能学会简化 Reach、正反向交替能节省人为设定的复位成本，且搭出了自学习 harness。最新文档也明确：理想环境中 SAC 与比例控制接近打平，默认 Reach 的 uniform/diagnosed 两组约 2.2 万步都饱和。这说明当前瓶颈是**研究任务的分辨力和真实约束**。单纯更换大模型或训练算法，难以证明新方法的价值。

研究应逐步加入真实抓取接触、失败后状态偏移、部分可观测性和不可恢复状态，并同时测任务能力与系统运行成本。当前延迟、漂移、滑落扰动适合做机理实验，但尚不能代替真实刚体接触和真机验证。

| 层级 | 回答的问题 | 本项目接口 | 优先参考 |
| --- | --- | --- | --- |
| Policy | 看到观测后怎样行动？ | `skills/` | ACT、Diffusion Policy、SmolVLA；后续 π 系列/GR00T |
| Learning | 怎样用数据与结果改进能力？ | `harness/trainer.py` | HIL-SERL、RLPD、RL Tokens、Q-Planning、DPPO、FQL |
| Harness | 何时执行、恢复、训练、验证、发布？ | `harness/`、`registry/` | RoboClaw、ENPIRE、ASPIRE、RoboRSI、RPent |
| Environment / transfer | 动作怎样落地，仿真与真机怎样对齐？ | `envs/`、G2 IK 接口 | Genie Sim、ManiSkill3、Isaac Lab、FORGE |

VLA 是视觉—语言—动作模型；BC 是模仿示范动作；RL 用任务回报优化策略；harness 是组织执行与学习的外层系统。这几者能够组合，不是同一层的替代品。

## 2. Harness：最接近项目研究目标的框架

### 2.1 RoboClaw：正向操作与逆向恢复成对组织

- 论文：[RoboClaw: An Agentic Framework for Scalable Long-Horizon Robotic Tasks](https://arxiv.org/abs/2603.11558)，2026-03，4 月修订。
- 代码入口：[RoboClaw-Robotics/RoboClaw](https://github.com/RoboClaw-Robotics/RoboClaw)。本次读到论文方法正文，代码仓库未安装验证。

核心是 Entangled Action Pairs（EAP）：将正向操作与逆向恢复配对，形成能够反复采集数据的自复位循环；同一个高层 VLM 负责采集阶段与部署阶段的技能调度。正文使用 π0.5 的 flow-matching 策略建模动作块，不能把这一训练过程直接称为 SAC 式在线 RL。

**对项目的价值**：你们已有 A→B/B→A 和规则救场，可以进一步为每个技能定义前置条件、完成条件、逆向技能和失败恢复。真正需要研究的是：逆向执行结束后，状态是否落在下一次正向策略可靠工作的区域内。任务方向翻转本身并不保证这一点。

论文摘要报告长任务成功率和人工时间改善；这些收益来自其特定系统与比较基线，不等于在你们 G2 上能直接获得同样比例。正向任务完成后的逆向行为，也不必然能处理抓空、掉落等失败状态。

### 2.2 ENPIRE：让 coding agent 在可验证的物理环境中做实验

- 论文：[ENPIRE: Agentic Robot Policy Self-Improvement in the Real World](https://arxiv.org/abs/2606.19980)，2026-06 首发，检索结果显示 2026-09-20 修订。
- [官方项目页](https://research.nvidia.com/labs/gear/enpire/)；[代码入口](https://github.com/NVlabs/ENPIRE)。本次核对了正文方法、实验口径及官网。

四个模块：Environment 提供复位与验证；Policy Improvement 启动策略改进；Rollout 在机器人上执行；Evolution 根据日志修改代码和训练方案。

这里最值得学习的是**两阶段边界**：先在人类反馈下构建并验证环境、约束、奖励和复位 API；之后固定这些 API，让 agent 优化策略与训练程序。论文不是声称完全无需前期人工工程。

另一个关键细节是评测口径：官网展示的 **99% 为 pass@8**，每个子任务可在同一 rollout 中根据之前的失败重试最多 8 次；它不是冻结策略一次尝试的 99%，也不是 8 次相互独立采样。你们应分别报主策略单次成功率、含恢复的系统成功率、重试次数与总耗时。

**可借鉴实现**：为 harness 增加受约束的实验提案，记录候选配置、假设、代码差异、预算、失败证据和复评结果；固定最终测试集和 verifier。初期只开放一个变量，例如恢复目标分布，不同时修改奖励、算法和评测条件。多机器人团队可以缩短墙钟时间，但官方也指出 token 成本增加、机器人利用率可能下降。

### 2.3 ASPIRE：让失败修复成为持久技能

- [ASPIRE: Agentic /Skills Discovery for Robotics](https://arxiv.org/abs/2607.00272)，2026-06-30 提交、7 月编号；[官方项目](https://research.nvidia.com/labs/gear/aspire/)。本次核对摘要和官方执行引擎说明。

三部分是细粒度执行日志、不断积累的技能库、探索多种程序与任务序列的进化搜索。重点是代码技能自改进：修好一次失败后，保存成未来可以检索和复用的能力。

适合学习怎样扩展 `EpisodeRecord`：记录感知输入、物体/TCP 位姿、抓取判断、动作调用与局部轨迹，使诊断能定位到具体阶段，而非只有一个 `timeout`。技能入库除成功率外，还应注明前置条件、适用机器人、控制坐标系与失败边界。

与 RL 的区别：生成更好的控制程序不要求神经网络权重更新。应分开做“代码变化、权重固定”与“代码固定、权重变化”的消融。跨机器人复用也仍需要底层 API 适配。

### 2.4 RoboRSI：优先复用已经核对过的本地资产

- [官方仓库](https://github.com/nssmd/RoboRSI)；本项目资料：[源码笔记](notes_roborsi.md)、[调用链](roborsi-callchain.md)、[试跑记录](roborsi-trial-log.md)。

已有材料核对了 Manager/Planner/Engineer/Reviewer、技能 taxonomy、`reset_success`/`reset_failure`、内嵌 LeRobot 训练入口以及 evolve/eval 分离。无需为阅读新论文废弃这套已有工作。

本次 arXiv 按 RoboRSI 名称检索无结果；因此按开源框架和研究资料讨论，不替它补写未核实的论文或会议归属。网络仓库访问超时，本节实现判断基于项目记录的 commit `9b644d2`。

建议借 ENPIRE 完善实验与验证边界，借 RoboClaw 完善自复位技能契约，借 ASPIRE 完善失败证据和技能复用。先维持本项目轻量 harness，确定缺少哪一项能力后再引入完整框架。

### 2.5 Continual Harness：概念参考，不当作真机成绩

[Continual Harness: Online Adaptation for Self-Improving Foundation Agents](https://arxiv.org/abs/2605.09998)，2026-05。其主要实验是 Pokémon 等持续交互环境，研究单次不重置运行中的 prompt、技能和记忆更新。

适合理解“更改上下文/记忆”与“更新模型权重”的不同层次；游戏中的 reset-free 不等于机械臂的物理恢复，不能由其结果推断接触控制能力。

### 2.6 RPent / Harness VLA：冻结技能，改善调用条件与失败恢复

- 框架：[RLinf/RPent](https://github.com/RLinf/RPent)；论文：[Harness VLA](https://arxiv.org/abs/2607.08448)（v4：[HTML 正文](https://arxiv.org/html/2607.08448v4)）；实现参考：[架构与记忆文档](https://rpent.readthedocs.io/en/latest/development/architecture.html)。本次核对 commit `6ee7069`，未安装复现。

**定位与方法。** RPent 将冻结 VLA 作为局部接触技能，由带记忆的 planner 组织接近、搬运、导航、释放等解析 primitives，并在抓取、受约束放置、按钮/抽屉操作时调用 VLA。planner 根据 RGB-D 和执行反馈重新绑定目标、调整 staging 并重试。

核心是 **staging / re-staging：把机器人带回已有策略容易成功的状态**，而非原地盲目重试；planner 发出结构化 primitive 调用，不等同于在线 RL 或生成新技能。

**记忆与评测协议。** Task Specific Memory 保存成功过程，Global Memory 保存通用经验与失败规则；探索可 reset，评测冻结记忆且单次不 reset，但允许 episode 内重试。因此：

- “VLA 不微调”不等于没有任务经验；探索 reset、评测重试及其成本需分开记账，主要改善来自记忆与技能编排，而非在线 RL 权重更新。

**作者报告的证据。** 以下优先比较同一冻结底座；不同 planner 和记忆快照的结果不能直接混用。

| 评测（论文 v4） | 直接冻结 VLA | Harness VLA | 解释与边界 |
| --- | --- | --- | --- |
| LIBERO-Pro | 50.0% | 82.4% | 指令重定向、位置交换下提升 32.4 个百分点 |
| RoboCasa，Table 4 口径 | 30.0% | 57.1% | 导航、接近与长任务组合受益；不是所有 365 个任务的统一成绩 |
| RoboTwin C2R | 50.4% | 58.4% | clean→randomized；不是 sim-to-real 证据 |

LIBERO-Pro Goal 的记忆对照为 Task-T 79.0%→87.0%、Goal-S 31.0%→87.0%，但两类记忆未被单独消融。官方排行榜另报 92.63%，其 planner、记忆快照和分组不同，不能替代论文数字；论文成本页显示 LIBERO-Pro 约 412 秒/episode，说明该高层系统不适合高频控制。

官方 flywheel 主要是评测轨迹采集、成功数据导出和独立 SFT，不是已验证的自动在线 RL 闭环。仓库当前为 Pre-Alpha，MuJoCo 依赖与本项目不同，也未核实 G2 adapter。

**本项目借鉴路线：** 在 robosuite 比较 base-only、固定 staging/recovery、自适应 staging/recovery，固定策略与环境步数，报告主策略/系统成功率、重试、恢复耗时和覆盖；再做“记忆开关 × 参数更新开关”对照，最终冻结记忆与权重评测。保留现有 `skills/`、`harness/`、`registry/` 分层及独立 verifier。

## 3. Policy：从可复现基线到 2026 年新方向

### 3.1 ACT、Diffusion Policy：仍值得先做的基线

- [ACT / Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware](https://arxiv.org/abs/2304.13705)，2023。
- [Diffusion Policy: Visuomotor Policy Learning via Action Diffusion](https://arxiv.org/abs/2303.04137)，2023，2024 journal 扩展；[代码](https://github.com/real-stanford/diffusion_policy)。

两者都预测一段动作，减少逐步预测的误差积累。Diffusion Policy 能表示“从左绕”和“从右绕”这类多模态动作分布。它们不是最新发布，却是判断复杂 VLA 是否真正带来收益的重要对照。

对当前状态观测任务，SAC 与控制器更直接；转到 RGB 抓取后，可用固定数量的示范比较 ACT/DP。完整保存失败与恢复轨迹，以免后续 RL 只有成功数据。

### 3.2 SmolVLA：先跑通视觉语言策略的务实选择

[SmolVLA: A Vision-Language-Action Model for Affordable and Efficient Robotics](https://arxiv.org/abs/2506.01844)，2025-06；[LeRobot 文档入口](https://huggingface.co/docs/lerobot/en/index)。

重点是较小的模型、社区数据，以及把感知/动作预测与动作执行解耦的异步推理。论文明确面向单 GPU 训练和消费级硬件部署。它适合先跑通数据格式、相机输入、动作归一化和部署延迟这一整条工程链。

现有 A800 可以作为尝试轻量模型的资源，但本次没有跑显存基准；能否微调某配置仍取决于图像数量、分辨率、动作长度、batch 和优化器。模型能运行也不等于已适配 G2。

### 3.3 π 系列：看清三个不同研究问题

1. **[π*0.6 / RECAP](https://www.physicalintelligence.company/blog/pistar06)，2025-11-17**：结合示范、人工纠正和自主 rollout，训练价值函数，并通过 advantage-conditioned policy 利用好坏经验。要学的是从失败中提取信用分配信号，而非只保留成功轨迹做 BC。
2. **[RL Tokens（RLT）](https://www.physicalintelligence.company/research/rlt)，2026-03-19**：先把 VLA 表示压缩成 RL token，再训练小 actor/critic 改进精细动作阶段。下一节展开。
3. **[π0.7](https://www.physicalintelligence.company/blog/pi07)，2026-04-16**：通过语言、视觉子目标、执行质量/速度等多种条件组织异质数据，研究组合泛化和跨本体能力。对项目的启发是日志不仅存轨迹，还存“怎样完成、是否接管、速度与质量”等元数据。

以上官方页面已读取；附有技术 PDF。不由论文发布推断相应最新权重、完整训练数据或训练 recipe 已公开。部署优先查看 [openpi](https://github.com/Physical-Intelligence/openpi) 实际可用版本，本次该 README 请求超时，未核实最新发布清单。

### 3.4 记忆和实时反馈：比继续增大模型更贴近当前问题

- [Multi-Scale Embodied Memory（MEM）](https://www.physicalintelligence.company/research/memory)，2026-03-03：短期视觉历史处理运动与遮挡，长期文字事件记录任务进度；官方展示失败后改变尝试方式。
- [Real-Time Action Chunking](https://www.physicalintelligence.company/research/real_time_chunking)，2025-06-09：关注大模型推理延迟下连续动作块的实时执行。
- [VLA-Feedback / Catch Me If You Can](https://arxiv.org/abs/2609.21022)，2026-09-17：最新预印本/作者标注 CoRL 2026；本次核对摘要。把低频 diffusion 规划与高频视觉反馈结合，在执行时利用最新观测修正动作。

项目扰动环境存在执行延迟。当前状态相同但尚未执行的命令队列不同，未来状态也会不同；只给一帧状态的 MLP 往往面对部分可观测问题。因此，先比较当前帧、状态历史、状态+动作历史，再评价新算法。单独增加速度通常不能恢复完整延迟队列信息；队列可作为仿真 oracle 对照，部署时应使用可获得的命令历史。

### 3.5 GR00T：人形生态参考，需要明确版本

[GR00T N1: An Open Foundation Model for Generalist Humanoid Robots](https://arxiv.org/abs/2503.14734)，2025-03；[官方代码入口](https://github.com/NVIDIA/Isaac-GR00T)。原论文是 VLM 与动作生成模块组成的双系统结构，混合真实机器人、人类视频和合成数据。

适合研究人形/双臂策略与 NVIDIA 仿真生态的连接。本次直接核实的是 N1 原论文；近期文章提及后续版本，但没有完成最新官方 release 核验，所以不把 N1 称作截至今日的最新型号，也不承诺对 G2 开箱即用。

## 4. RL：哪些算法适合接到当前系统

| 路线 | 已有数据/能力前提 | 主要优点 | 主要成本或限制 | 本项目优先级 |
| --- | --- | --- | --- | --- |
| SAC 基线 | 可交互状态环境 | 现有实现可复用、便于控制变量 | 难探索任务需示范/课程；视觉输入另有成本 | 立即保留 |
| RLPD / HIL-SERL | 少量示范、可验证 reward，可能需人工纠正 | 有效复用离线与在线数据 | 真机接管、复位与奖励识别仍需工程 | 高 |
| Residual RL / RLT | 已有较可靠基础控制器或 VLA | 聚焦误差与困难阶段 | 基础策略限制探索；表示与动作空间须对齐 | 高 |
| Q-Planning | 可采样动作的 BC 策略 | 冻结大策略，仅训练价值模型 | Q 误差与候选覆盖；需重新核验代码成熟度 | 值得小规模验证 |
| DPPO | 已预训练 diffusion policy、足够交互吞吐 | 用 RL 改进动作块策略 | 不能直接当作 SB3 SAC 替换开关 | 视觉基线之后 |
| FQL | 离线成功/失败数据 | 表达复杂动作分布、支持 offline-to-online | critic 的分布外外推；任务证据范围 | 离线数据成形后 |

### 4.1 HIL-SERL 与 RLPD：最贴近真机样本效率

- [HIL-SERL](https://arxiv.org/abs/2410.21845)，2024-10，2025-03 修订；[官方代码](https://github.com/rail-berkeley/hil-serl)。摘要报告其任务上约 1–2.5 小时训练实现高成功率；不能据此预算任意 G2 任务。
- [RLPD / Efficient Online Reinforcement Learning with Offline Data](https://arxiv.org/abs/2302.02948)，ICML 2023；[代码](https://github.com/ikostrikov/rlpd)。

RLPD 研究如何用合适的数据混合和训练设计，让 off-policy RL 有效利用既有数据。HIL-SERL 将示范、人工纠正、样本高效视觉 RL 和异步 actor/learner 组织成真实系统。

建议先在物理仿真里固定一小批示范，比较 SAC-from-scratch 与示范+在线 RL，再决定是否接入真机人工纠正。记录干预前后状态、实际执行动作、控制来源和策略版本；接管轨迹可以用于学习，但评测必须标记接管，不能算作自主成功。人机切换处的 transition 和 bootstrap 处理需按方法定义，不能把未执行的自主动作写成真实 action。

本项目内嵌 LeRobot 分支有相关教学入口，但它不等同于原版 HIL-SERL 的 JAX 实现；依赖、奖励分类器、动作接口及默认机器人不同。不要把官方 Franka controller 直接套在 G2 上。

### 4.2 Residual RL / RL Tokens：学习最难的那一段

直观形式为 `action = base_action + bounded_correction`；实际大模型方法可能在动作块、潜在表示或带约束的策略空间中进行修正，不能一概视为简单向量相加。

RLT 官方方法先学习一个压缩 VLA 内部表示的 encoder-decoder bottleneck；随后冻结表示，训练小 actor/critic。actor 接收 VLA 参考动作，预测动作块，用正则限制偏离，并可纳入人工纠正。它不是拿一个任意图像 embedding 接 SAC 就自动得到相同效果。

官方在四个精细任务中报告改善，其中 Ethernet insertion 使用 **15 分钟机器人数据，但总训练时间 2 小时**，其余包括复位与系统开销。这正说明 reset-free harness 可能与 RL 算法同等重要。

项目可先做低成本版本：P/IK/轨迹控制负责接近与搬运，小 SAC 修正对齐、接触或滑落后的重抓。比较基础策略、从零 RL、残差 RL；动作界限、观测和交互预算保持一致。残差策略仍可能过拟合动力学或沿用基础策略的错误，必须测未见参数。

### 4.3 Q-Planning：冻结大策略，用失败训练小 critic

[Beyond Imitation: Self-Improving Robot Policies via Off-Policy Q-Planning](https://arxiv.org/abs/2608.21204)，2026-08-21；[项目入口](https://varungiridhar.github.io/qplanning/)。本次核对原始摘要，未复现。

冻结 BC 策略，对其采样动作使用 Q 值引导选择；论文描述的是 Q-weighted action aggregation，不应笼统当作普通 best-of-N。只更新小 Q-function，利用成功和失败 rollout 改进执行。作者报告两项双臂真机任务五轮改进，以及 LIBERO/RoboTwin 结果。

适合单卡资源和已训练策略复用，但有两个边界：候选动作不覆盖正确行为时，critic 很难凭空创造能力；Q 误差会误导执行。对多模态动作，平均后的动作是否仍可行也需要验证。因此它是一个值得独立实验的近期方向，不是已有成熟替代方案。

### 4.4 DPPO 与 FQL：在生成式策略之上做 RL

- [Diffusion Policy Policy Optimization](https://arxiv.org/abs/2409.00588)，2024；[项目](https://diffusion-ppo.github.io/)。将 policy gradient 用于 diffusion policy 微调，利用其动作生成结构探索。论文包含仿真训练后真机部署的操作任务证据；不代表任意任务都可零样本迁移。
- [Flow Q-Learning](https://arxiv.org/abs/2502.02538)，ICML 2025；[项目](https://seohong.me/projects/fql/)。用 flow policy 描述数据分布，再训练一步策略进行价值优化，避免对多步生成过程反复递归求导。原论文主要证据是 OGBench/D4RL 上 73 个任务的 offline/offline-to-online 实验。

建议按数据条件选：已有 DP 基线并有仿真交互，读 DPPO；积累了大量离线轨迹并希望在线继续改进，读 FQL。不要同时切换数据、环境、策略表示和 RL 算法后再把收益归因给其中一项。

## 5. Reset-free：最值得形成项目独立研究问题的部分

### 5.1 MEDAL / MEDAL++：恢复到什么分布，比恢复一次更重要

- [MEDAL: A State-Distribution Matching Approach to Non-Episodic Reinforcement Learning](https://arxiv.org/abs/2205.05212)，2022。
- [MEDAL++: Self-Improving Robots: End-to-End Autonomous Visuomotor Reinforcement Learning](https://arxiv.org/abs/2303.01488)，2023；[项目](https://architsharma97.github.io/self-improving-robots/)。

MEDAL 让 backward policy 匹配示范中的状态分布，使 forward policy 从与任务相关、难度有变化的状态继续学习。MEDAL++ 将视觉输入、正反向学习与从示范推断 reward 进一步整合。

这直接对应你们已观察到的 `home` 与 `resample` 救场差异。固定回 home 可能制造窄分布；均匀覆盖也不等于有效学习，可能把预算花在无关或无法完成的状态上。应比较恢复成本、可恢复性与学习价值的联合选择。

还需区分：本项目 A→B 与 B→A 都可能是业务任务，而文献 backward policy 可能仅为正向任务创造起点。比较吞吐时要写清哪些算生产性任务、哪些算恢复开销。

### 5.2 REVERSAL-BENCH：把不可逆失败纳入实验

[REVERSAL-BENCH: A Reversibility Axis and Reset Oracle for Measuring the Reset-Free RL Cliff](https://arxiv.org/abs/2609.17745)，2026-09-15 新预印本。本次核对原始摘要；代码释放和全部实验尚未逐项审计。

它研究环境可逆性下降后 reset-free agent 陷入不可恢复状态的现象，例如物体掉出可达区域。与固定周期 reset 的训练不同，无外部复位时一次不可恢复失败可能结束后续学习。

项目可以加“掉落仍可抓回”和“掉落到工作区外”两类状态，并报告连续自主运行长度、人工接管频率、恢复成功率和恢复时间。不能把所有失败直接传送回 home，再宣称系统已经 reset-free。

### 5.3 可做的研究假设

**假设 A：带可恢复性约束的恢复目标选择，比固定 home 或单纯均匀复位，在相同总成本下学得更快。**

比较 fixed reset、交替+home、交替+uniform、交替+失败分布采样、交替+可恢复性/学习进展采样。后三者尽量保持底层策略和 reward 相同，单独衡量调度贡献。

**假设 B：在带延迟和接触不确定性的任务上，历史观测+有界残差策略，比只改目标采样更有效。**

先在当前扰动环境拆分“信息不够”和“学习不够”；用当前帧、状态历史、状态+命令历史和仿真 oracle 对照，再上 robosuite 接触任务。

**假设 C：把重复失败归并成带前置条件的恢复技能，能降低新场景中的恢复成本。**

比较不记忆、事件摘要、可执行技能库三种 harness。冻结策略权重，统一重试上限与验证器，避免代码改进与参数改进混算。

RPent（§2.6）提供另一项更细的对照：保持技能词表不变，只改善调用前的 staging 与执行记忆。可先验证这一层的收益，再判断是否需要生成新恢复技能；探索中使用 reset 的成本必须与部署期的恢复成本分开记账。

这些都是待验证的项目提案，不是本次检索已经证实的新颖性声明。准备投稿前需要围绕具体方法再查相关工作。

## 6. Sim-to-real：三条路径与本项目取舍

### 6.1 状态策略 + 参数识别 + 动力学随机化 + 小量真机适应

先固定 G2 动作语义与底层控制：TCP/base/world 坐标、米/弧度、绝对位姿或增量、控制周期、夹爪状态、动作饱和及时间戳。再用真实测量确定延迟、增益、负载和摩擦范围，在仿真中随机化，最后用少量真机数据做 residual/HIL 适应。

对项目现有 IK 和相对 SE(3) 重定向资产，这是最直接的起步路径。注意当前每步独立增益噪声不等于真实机器一次运行内近似固定的标定偏差：应分开模拟逐步噪声、每回合参数变化和慢漂移。

参考 [FORGE: Force-Guided Exploration for Robust Contact-Rich Manipulation under Uncertainty](https://arxiv.org/abs/2408.04587)，2024，2025 修订；[项目](https://noseworm.github.io/forge/)。它结合力阈值、动力学随机化与成功预测，研究位姿不确定时的插入、螺纹和齿轮啮合。

最新跟踪项：[Stability-aware Residual Reinforcement Learning Framework for Robotic Manipulator Disturbance Compensation](https://arxiv.org/abs/2609.21307)，2026-09-18，摘要报告从 ISS 分析推导状态相关残差界限。值得学习怎样约束 residual；本文未审查其完整证明，不能将其稳定性结论直接移植到 G2。

### 6.2 真实场景重建 → 仿真数据 → 视觉策略 → 真机校正

[Genie Sim 3.0](https://arxiv.org/abs/2601.02078) 是本项目最相关的平台资料：2026-01 首发，本次摘要页显示 2026-08-14 v4；[代码入口](https://github.com/AgibotTech/genie_sim)。论文标题 3.0 与本地源码版本 3.2.0 是不同对象，引用时不要混用。

它提供场景生成、合成数据与评测，适合承接 G2。论文摘要声称的 zero-shot 迁移明确带有 controlled conditions；不能理解为只要仿真够逼真就能免除真机标定。

另一个新方向是 [DEXTERA](https://arxiv.org/abs/2609.21045)，2026-09-17 预印本：从单图场景重建到几何对齐、数据合成和策略训练。摘要同时报告纯仿真与混合 sim-real 的差异，后者平均真实成功率从 29.2% 提升至 61.9%。这更支持“仿真扩大数据、少量真实数据补差距”的工程路线；本次未验证其代码与模型可获得性。

### 6.3 仿真规划轨迹 → 真机配对采集 → 微调策略

[A Sim-to-Real Integration Pipeline for Training and Deployment of Chunk-Based VLA Manipulation Policies](https://arxiv.org/abs/2609.21817)，2026-09-18，作者标注 IROS 2026 Workshop。

该工作在仿真生成专家轨迹，再在真实 Franka FR3 上回放，采集对应的真实视觉与本体观测，供 VLA 训练；配对数据也用于测量 sim-real gap。它降低遥操作依赖，但仍有真实机器人采集成本，且其开放环回放只适合已经验证可行的任务与控制设置。

你们已有 IK/轨迹生成，值得优先读这种接口一致性方案。迁到 G2 后，先验证轨迹和观测对齐，再考虑接触阶段闭环纠正；不能把 Franka 回放结论直接当作 G2 接口保证。

### 6.4 仿真框架怎样选

| 框架 | 用途 | 本项目建议 |
| --- | --- | --- |
| robosuite/MuJoCo | 真实抓取接触、小规模可控实验 | 近期主力；先从 Lift/PickPlace 接上现有评测 |
| [ManiSkill3](https://arxiv.org/abs/2410.00425) | GPU 并行物理、渲染、视觉策略与操作任务 | 需要大量采样后考虑；论文吞吐数字取决于任务与配置 |
| [Isaac Lab](https://github.com/isaac-sim/IsaacLab) | Isaac 生态机器人学习与并行训练 | 需要专门核对 GPU/驱动/渲染部署，不能凭 CUDA 可用判断 |
| Genie Sim | 团队 G2 场景、数据、接口与 benchmark | 面向目标机器人集成；按本地版本与节点条件推进 |

本项目已有渲染探测显示 CUDA 计算可用，但离屏渲染可能走 Mesa 软件路径；ROADMAP 的部分早期 EGL=GPU 文案已过时。MuJoCo 状态实验仍可继续，GPU 渲染和 Isaac/Genie Sim 扩展需按 `infra-gpu-render.md` 单独验收。

## 7. 怎样让实验结论站得住

1. **冻结最终测试**：训练/诊断集、发布验证集、最终保留测试集分开。反复看同一 seed 的评测来挑版本，会逐渐对验证集过拟合；一次训练 seed 改变也不等于 OOD 测试。
2. **同时报能力与成本**：主策略单次成功率、含恢复的系统成功率、重试次数、人工复位次数、恢复时间、有效任务/小时。跨方法同时记录环境交互步数、墙钟时间、训练计算和人工时间。
3. **物理连续轨迹的统计相关性**：同一条 reset-free 长轨迹中的相邻任务不是独立样本。按独立训练 seed/长 rollout 汇总，使用合适的区间估计，不把几千个相邻任务当几千次独立实验。
4. **覆盖指标要任务相关**：起始格子熵用于检查塌缩，但最大熵并非目标。再看任务区域覆盖、不可达区域比例、成功率与恢复成本。
5. **控制复杂度**：先改变 reset/采样，后改变策略算法，最后加 agent 代码优化；每一步留固定规则基线和资源相同的对照。
6. **真机上线前对齐评测**：仿真真值与真机传感器/视觉 verifier 不是同一信号。用标注样本测假阳性与假阴性；评估策略时固定判定器版本。

补充统计纠正：项目阶段 3 笔记将“50 局标准误约 ±7%”写成固定值并不严谨；二项标准误为 `sqrt(p(1-p)/n)`，n=50 时最大约 7.1 个百分点，不是普适 95% 区间。50/50 成功也不能推断真实成功概率恰为 100%。固定 `min_gain=0.02` 只是工程门禁，不能独立证明统计显著性。本次只在研究笔记指出，未修改其他智能体文件。

## 8. 建议阅读顺序与第一轮产出

| 顺序 | 阅读 | 要回答的问题 | 推荐产出 |
| --- | --- | --- | --- |
| 1 | RoboClaw + MEDAL/MEDAL++ | 正反向循环怎样维持有用的起始分布？ | 技能前置/后置/恢复契约；3–5 种 reset 策略对照 |
| 2 | ENPIRE + ASPIRE | agent 可以改什么，哪些验证接口固定？ | 不可变 verifier、实验日志 schema、主策略/系统指标分离 |
| 2a | RPent / Harness VLA（§2.6） | 冻结技能后，重新接近与记忆能改善多少可靠性？ | 固定/自适应 staging 对照；冻结记忆评测；探索与重试成本记账 |
| 3 | HIL-SERL + RLPD | 如何利用示范和失败，减少真机交互？ | 少量示范+在线训练的受控基线 |
| 4 | RLT + Q-Planning | 能否冻结已有大技能，只学习小模块？ | base-only / residual / critic-guided 对照提案 |
| 5 | ACT/DP/SmolVLA + DPPO/FQL | 什么时候值得切换策略表示？ | RGB 任务基线、数据格式和延迟测量 |
| 6 | FORGE + Genie Sim + sim-real 配对采集 | G2 迁移中误差来自哪里？ | 坐标/时间/动作契约、系统辨识与 held-out 参数评测 |

综述入口：[Weights or Skills? A Survey of Robot-Learning Techniques: from Action-Predicting Weights to Robots that Write their Own Skills](https://arxiv.org/abs/2608.01851)，2026-08-03，聚焦权重策略与可执行技能两条路线。本次核对摘要，可先用它建立术语地图，再以各原论文验证细节。

建议近期项目题目围绕：**“在含接触失败与不可恢复状态的正反向操作中，如何用失败诊断选择恢复目标，在维持泛化的同时降低人工复位成本？”** 先用当前抽象环境排除机制错误，再到 robosuite 物理任务验证，最后才把结论迁移到 Genie G2。
