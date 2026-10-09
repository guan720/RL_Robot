# S1：RL 算法广域补漏与进入 S2 的问题

研究截止：2026-09-23。实际完成 27 条机制不同的检索，20 次含检索、原始来源打开及定点查找的 web 调用。实际查询、返回 URL、正文阅读粒度和未查明项见 [search_log.json](search_log.json)。这是广域补漏，不声称穷尽，也不声称任何代码已安装、训练或真机复现。

## 1. 先总结方法族与成立条件，再查候选

唯一最终能力目标是稳定、独立执行的目标条件 VLA policy。Harness 观察、纠正、评分、复位和知识积累是训练手段。用接管率、运行时长或系统整体成功率代替独立 policy 成功率，会改变任务。首任务仍是同一 θ 的单臂 A↔B；少示范和低起始成功率包括零；不能默认双向分别训练两个策略，也不能默认原地停留就是合法反向进展。

本轮先按机制列出问题，随后沿论文→作者项目/仓库→官方 HF 追溯。旧 04 的候选名单不是重新搜索的边界；去重同时查了会话内 02、03 的当前正文。旧文件和 embodied-scientist 知识库均未写入。

| 方法族 | 可以提供什么 | 必须先成立的条件／本轮搜索问题 |
|---|---|---|
| 原生 flow actor RL | 最终直接更新 VLA 动作生成参数 | 加权 flow matching、直接策略梯度、Q 引导蒸馏不是同一实现；是否保持原生头、在线真实回放、动作分布支持？ |
| Offline→online actor-critic | 少量示范初始化，并利用自主失败 | 示范覆盖、critic 外推误差、执行动作与候选动作区分；零成功是否有可用 reward／恢复桥？ |
| 冻结基座＋残差／潜变量／候选排序 | 较小更新成本、限制探索幅度 | 若最后依赖另一 actor、Q 排序器或残差，须明确最终 policy 包含它；不能称基座已学会。残差可达域有限。 |
| GRPO／RLOO 与奖励塑形 | 无 critic 的策略更新、组内相对信号 | 全失败组是否有梯度？质量差异与真正任务进展是否同向？不能从“有梯度”推出“能从零成功启动”。 |
| 纠正→BC／DAgger／优势加权训练 | 把教师到访分布和纠正行为迁移进 policy | 自然语言说明不等于可执行动作标签；人类/模型建议不等于实际执行 transition；可信标签、执行事实及奖励来源需分开。 |
| 真异步 chunk 与延迟补偿 | 消除推理阻塞并缓解过时观测 | actor-learner 并行、chunking、RTC、未来状态预测和延迟感知 TD 是不同层；提交前缀、队列、实际动作、变长生效时长必须对应。 |
| 世界模型／教师蒸馏 | 低成本想象 rollout、部署压缩 | 模型误差、教师能否处理失败分布、奖励幻觉；最终独立策略需要独立闭环验证。 |

## 2. 新增候选与旧浅筛深化地图：按作用层分列，不跨任务排榜

“新增”是对会话内当前材料进行关键词去重并接受根代理跨审查记录校正后的新增；不是宣称论文首次发布。REMAC 在 04/reviews/R06/review_evidence.md Q12 已浅筛官方 Kinetix 仓库，本轮归为机制／资产深化，不能计为全会话新增。日期区分论文版本与代码动态。影响力字段只用机构、公开资产和验证范围：本轮未系统核验引用量、下载量或第三方复现，不以 GitHub 星数代替有效性。

### 2.1 训练与数据桥：最可能改变工程接入范围

| 候选、日期与来源 | 方法和公开资产 | 对本目标的适合度与边界 | 进入 S2 的问题 |
|---|---|---|---|
| **FluxVLA Engine／FluxDAgger**；论文 2026-09-15；LimX Dynamics、南开、港大、电子科大等。[论文](https://arxiv.org/html/2609.17210v1)、[作者平台](https://github.com/FluxVLA/FluxVLA)、[纠正采集仓库](https://github.com/FluxVLA/FluxDAgger) | 多 VLA 训练/评估/部署；平台已列 RA-BC/AW-BC、RTC、远程推理和 ROS 纠正采集。FluxVLA 根许可证为 Apache-2.0；FluxDAgger 单独许可未核。读了论文系统设计关键段与两仓 README。 | **训练数据桥候选**，不是已证实的通用在线 TD 栈。多个模型“支持”不保证指定模型＋异步＋奖励学习组合全贯通。公开组织资产增强可查性，没有独立复现结论。 | 追 ARM loss、纠正 ownership/标签、动作平滑后的实际执行量、统计量版本、训练数据装载与发布；确认是否只有离线优势加权。 |
| **Learning to Fold／lehome_solution**；2026-06-25；Ilia Larchenko 独立研究者。[论文](https://arxiv.org/html/2606.27163v1)、[代码](https://github.com/IliaLarchenko/lehome_solution)、[real HF](https://huggingface.co/IliaLarchenko/lehome_real) | π0.5；模拟 AWR/RECAP、进度/value/关键点辅助头；真实数据混合示范、teleop/DAgger 和模拟回放。作者仓库与真实权重可访问。README 有 SPACE 切换纠正、逐帧 task_is_policy 标签。 | 有价值的轻量纠正数据实现线索。**真实统一 RL 管线仍属作者未来工作**；模拟特权关键点奖励不能直接移植。HF actor-learner 消息总线不证明真机 chunk TD。作者明确是工程案例，消融有限。 | 检查标签保留与采样权重、真实训练混合配方、任务目标条件、归一化和时间来源；不把竞赛成绩跨任务用于 RL 排名。 |
| **FineVLA**；2026-05-26，后续模型发布在 6 月；港大 XLANG、阿里 Qwen。[论文](https://arxiv.org/html/2605.27284v1)、[仓库](https://github.com/xlang-ai/FineVLA)、[RoboFine VLM](https://huggingface.co/xlangai/RoboFine-VLM-397B-A17B)、[数据](https://huggingface.co/datasets/xlangai/RoboFine-bench) | 十维细粒度过程语言，Qwen 草拟、人工复核；StarVLA OFT 和 GR00T flow 做语言标签相关 SFT。代码、标注工具和基准开放，policy checkpoint 在所读 README 仍 Coming soon。 | 可启发 GPT 纠正的结构化语言 schema。**论文策略实验使用工具生成后人工核验标签，不是 RoboFineVLM 自动输出**；它不证明 GPT 指令自动成为低层 BC 动作，也不证明在线 RL。 | 检查标签到样本接口、人工验证成本、实际动作标签来源。论文 v1 10,816 与新版 README 11,631 atomic facts 分属版本，禁止拼成同一实验。 |

### 2.2 异步与纠正边界：可借鉴组件，不预设替换核心 RL

| 候选、日期与来源 | 已读机制与公开状态 | 与目标的关系／S2 问题 |
|---|---|---|
| **FutureRTC**；2026-07-27；四川大学、电子科大、阿尔伯塔大学。[论文](https://arxiv.org/html/2607.24008v1)、[作者仓库 README](https://github.com/JianghaiSCU/FutureRTC/blob/main/README.md) | 冻结 VLA；以旧观测和已承诺动作预测执行时 proprioception 与视觉 latent，学习状态修正和运动相关特征迁移。README 声称 sim/libero、sim/Kinetix、dev/realworld 分支，涉及 π0.5、SmolVLA 和 Cobot Magic；本轮未逐分支审计。 | 新的延迟适配组件；**预测执行时上下文不等于更新基座，更不等于延迟感知 off-policy TD**。S2 查分支是否实存、队列中已承诺动作如何进入模型、预测监督如何生成及未见接触的外推误差；论文延迟扫参不可横比真实在线 RL。 |
| **REMAC**；2026-01-27，作者项目列 ICLR 2026；UIC、UCF、Cisco Research。[论文](https://arxiv.org/html/2601.20130v1)、[项目](https://remac-async.github.io/)、[代码](https://github.com/hatchetProject/REMAC) | 执行前缀 mask、LoRA 修正；训练混合 GT 与自己预测的 chunk，逐步降低 GT 比例以减轻 exposure bias。代码可访问但 README 实验路径为 Kinetix：专家 RL→采集→flow BC→LoRA；存在 yourusername clone 占位文本。 | 适合作为异步监督修正对照。它的前置专家 RL 不能算部署 policy 在线 RL，Kinetix 发布也不能冒充真实 VLA 完整实现。S2 仅在需要异步 BC 对照时查 mask/前缀、数据生成和基座接入成本。 |
| **ForceRFT**；2026-09-19；已核实作者单位含宁波东方理工、江南大学。[论文](https://arxiv.org/html/2609.22840v1) | 冻结 force-conditioned SmolVLA，逐控制步力反馈残差；自主真实 transitions 用于 critic，人工动作仅作投影后的残差 actor BC。本轮定向查询未定位官方训练仓库，不能据此称未开源。 | 最有用的是**接管与 critic 回报边界的明确选择**，但新增腕力传感与残差可达域限制。S2 查接管切段是否符合任务目标；S3 反证“接管后成功”如何避免变成前段自主策略虚假收益。 |
| **SC-VLA**；2026-02-25；同济、UTS、电子科大等。[论文](https://arxiv.org/html/2602.21633v1)、[作者仓库线索](https://github.com/Kisaragi0/SC-VLA) | flow 预训练联合预测进度和状态变化，再用 SAC 残差以及内部进度/一致性奖励；基座冻结。论文方法正文已读；作者仓库仅搜索返回 README 级信息，出现 gr00t、sac_residual、ManiSkill 训练及 ARX5 部署脚本，未打开源码。 | “Self-correcting”不等于外部教师纠正被蒸馏进基座。最终部署若包含残差必须明确；内部奖励也需要外部真实成功验证。S2 先核真实训练入口与 simulation-only 边界，不因存在部署脚本便声称真实在线 RL 开源。 |

ForceRFT 的特别证据：论文 IV-D 排除人工 transition 的 critic 更新；接管/重置将自主段视为终止，后续人工完成不向接管前传播成功；非段终点若缺真实下一观测则丢弃，不能伪造 terminal。作者称这对应自主片段的 return surrogate。此选择解决一种归因污染，却也改变了价值目标：如果本项目要优化完整物理 episode 的自主可恢复性，需要明确“接管结束一段”的语义和最终独立评估，不能只复制过滤规则。这里是目标取舍，不是论文 bug。

### 2.3 算法与弱起点补充

| 候选、日期与来源 | 机制、资产、影响力可观察证据 | 适合度与下一轮边界 |
|---|---|---|
| **ProphRL**；首版 2025-11，本轮读 v2；复旦、上海创智学院、Logos Robotics。[论文](https://arxiv.org/html/2511.20633v2)、[作者代码](https://github.com/LogosRoboticsGroup/ProphRL)、[Prophet 世界模型](https://huggingface.co/Fleurrr/Prophet-World-Model)、[π0.5 RL 权重](https://huggingface.co/Fleurrr/OpenPI05-Bridge-RL)、[Bridge 数据](https://huggingface.co/datasets/Fleurrr/Bridge-RL-Data) | 动作条件视频模型闭环想象 rollout，冻结 VLM 奖励，FA-GRPO/FlowScale 更新 flow VLA。仓库有 world_model、rl 和多 actor/world-model 配置，根 Apache-2.0。HF 可见模型与 optimizer/metadata，数据是初始图像/提示和 manifests，**不是完整真实 transition 回放**。 | 新增资产较完整的 model-based 分支；不能替代真实少示范启动证据。S2 若保留此支线，查入口可运行性、世界模型训练域、VLM 奖励校准与权重单独许可。没有执行 DRY_RUN，更未训练。 |
| **CO-RFT**；2025-08-04；北航、清华深圳、京东 Explore。[论文](https://arxiv.org/html/2508.02219v1) | RoboVLMs/Kosmos2 BC 后做 chunked TD3/CalQL，因果 Transformer 多 horizon critic；实验 30–60 示范、成功帧扩采，六个 Realman/Inspire 真实任务。定向查询未定位官方训练仓库。 | 有价值的“chunk 级 critic”早期漏项，但不是 π0.5 原生 flow，也不是在线真异步队列方案。少示范条件不能写成零成功启动；不作为已可直接接入的平台。 |
| **Prism-GRPO**；2026-08-18；Purdue、AWS AI。[论文](https://arxiv.org/html/2608.17423v1) | 用有界质量 q 打破同成败组平局，奖励 success＋λq、λ<1 保持成功高于失败；RLOO 避免组内标准化抹平尺度。正文方法、四个 RoboTwin 任务及补充段已读；真实部署为迁移验证。未找到官方代码；排除同名 LMM PRISM 的 HF 资产。 | **全失败组可有信号，不代表全局零成功必能学会任务**；文中仍需质量与成功梯度对齐条件。碰撞/平滑奖励可能奖励停留。S2 先明确质量信号是否在单臂 A↔B 真任务可观测，S3 用无动作/错物体/反向目标构造反证；不把作者“最多56% rollout节省”跨任务排序。 |

### 2.4 纠正为什么必须落到最终独立 policy：新增反证与邻域线索

- **Anatomy of a Closed-Loop Collapse**，2026-09-19，Fengze Jia，机构未在本轮核实。[正文](https://arxiv.org/html/2609.23048v1)：Octo 压缩案例中离线指标接近教师，但 WidowX 模拟闭环学生 0/72、教师 40/72；加入部署分布教师轨迹后另一次 held-out 结果为 18/36、教师 17/36。它支持“离线拟合与独立闭环必须分别测”，不证明任何蒸馏都坍塌，也不证明零成功无教师 RL。作者训练仓库本轮未定位。S3 用作需要困难状态纠正覆盖和教师退出评估的反证。
- **HITL-DP**：[Columbia ROAM 作者项目](https://roamlab.github.io/hitl-dp/)，Zhanpeng He、Yifeng Cao、Matei Ciocarlie；项目称 ICRA 2026 HRI 最佳论文 finalist。本轮仅读项目页，未将论文摘要当全文。它可提供不确定性触发人类帮助的线索；“更会请求接管”本身不是最终 policy 能力证据。
- **RAPID-Policy-Distillation**：仅作为根代理提供的线索，未在本轮建立作者论文→仓库链和 VLA 适用性，故不纳入已验证候选；不能把名字相似当领域一致。

## 3. 去重重核：以下均不是本轮新发现

旧 04 覆盖 RAPolicy、RT EXPO、Q-VGM、OTQL、LWD、PA-RL、ConRFT、HIL-SERL、RECAP、RLT、DSRL、ZPRL、PLD、WCM、Robo-ValueRL、RedFlow、Q2RL、ALOE、FPO、RIPT、π-StepNFT、Z-1、RISE、VLA-MBPO、WMPO、ImagineRL、Prioritized rollouts、FlashRT、RLinf、LeRobot、verl-vla 等。进一步检索当前 02/03 后，把首次在本轮搜索中遇到但旧文已有的条目重新标为复核：

| 旧覆盖 | 本轮真正新增的核查／限制 |
|---|---|
| SmoothRL／ARLI；03 已详述 | 重读 [SmoothRL v1](https://arxiv.org/html/2608.29768v1) 固定延迟、C/E/D 拆分与 critic 条件。异步执行建模需要单列，不把其残差实例默认扩展成所有 VLA 原生头。 |
| Q-Planning；02 reassessment_algorithms 已有 | 重读 [方法正文](https://arxiv.org/html/2608.21204v1)：冻结 BC，失败数据更新 Q，改进来自 Q 选择与规划；若最终移除 Q，论文不保证 BC 变强。旧项目已迁至 [新作者页](https://q-planning.github.io/)。 |
| POCO；02 深筛与 ConRFT 后续已有 | [正文](https://arxiv.org/html/2604.01860v1) 真实 VLA 起始成功约53–77%，使用50示范；四个小 flow 任务96.7%不能混写为 VLA 全局成绩。[作者项目](https://cccedric.github.io/poco/) 未在已读页面提供可验证训练仓库。 |
| ARFM；02 vla_rl_without_reference 已有 | [正文](https://arxiv.org/html/2509.04063v1) 是离线自适应能量加权 flow；不因“RL fine-tuning”名称推断已有在线真实纠正链。 |
| VLA-Precision、UniSteer、VLAC；02/生态线已有 | VLA-Precision 本轮仅补读 [v1](https://arxiv.org/html/2609.04355v1)，已知旧文核过 v3，所以不能用本轮 v1覆盖较新结论。要核 executed transitions、proposal rank、参考 SFT L2 和动作专家 LoRA；资产深核交生态线。 |
| ReinFlow、TEMPO | 02 已有。查到标题不计新增，不重复摘要。 |

这些重核改变的是适用边界或证据清晰度；本轮不据此重新宣布主算法胜出。RAPolicy/EXPO 的共同预算及原生 flow 路线比较留给 S2，而非从不同任务的成功率表推断胜负。

## 4. 进入 S2：只提出能改变接入或取舍的具体问题

### A. 优先核训练数据链：FluxVLA／FluxDAgger

1. 从人类/模型建议到实际执行：ownership、时间戳、目标、policy 版本、动作平滑和控制器覆盖在什么位置记录？建议动作不能冒充已执行动作。
2. ARM 的 reward/advantage 来自谁、在哪计算；actor loss 是 RA-BC/AW-BC 还是包含真实 critic TD；失败样本是否进入真实 replay？
3. 纠正 BC 与自主 RL 能否共享同一目标条件 θ、同一归一化协议；A→B 和 B→A 必须是显式目标条件，不能只用数据集名字隐式区分。
4. 发布/推理 artifact 是否包含 processor、统计量、目标语义和异步参数；“支持多个模型”须落成当前要用的一个可核组合。

### B. 优先核异步执行：FutureRTC，参照旧 SmoothRL／RAPolicy／EXPO

1. 训练 loss 与实际运行分支是否一致？看过去观测预测未来上下文时，已提交动作前缀来自哪个事实源？
2. 正常延迟、迟到 chunk、临时接管、环境复位后缓存和预测是否作废？未来状态 predictor 训练不能假设已被取消的动作仍发生。
3. 是否存在为执行时 delay/state 建模的 replay/TD？若仅监督 adapter，明确其与主 RL 的接口，不合并宣传为一个算法。

### C. 优先核目标偏移：ForceRFT

1. 自动/人工分段的 β、真实 next observation、gripper 与 base action 等 critic 条件是否保留。
2. 接管切段将终止概率混入价值：它提高“自主一段不被接管”的分数，是否同时提高完整任务的独立成功？哪些状态会被错误放弃？
3. 力传感和残差限制是额外资源；无法普遍具备时保留其数据语义经验，不强行把整条方法定为通用基线。

### D. 有条件保留的支线

ProphRL：只在可承担世界模型与奖励校准时核资产链；FineVLA/LeHome：作为纠正→SFT 的轻量参考；Prism-GRPO：作为全失败组信号机制的反证候选；REMAC/SC-VLA：需要异步 BC 或残差对照时再查。CO-RFT/HITL-DP 暂留地图。这里是调查顺序与组件定位，不是算法排行榜。

## 5. S1 对方案假设的修正

1. **新增一个值得源码核实的训练/纠正平台 FluxVLA，不把其离线优势学习自动升级为真实在线 RL。**
2. **新增 FutureRTC，并深化旧审查浅筛的 REMAC；两者提示必须区分上下文修正、监督修正和真实异步 TD。**
3. **ForceRFT 给出有用而不免费的接管切段选择；“所有人工数据都进入 critic”并非通用正确规则，“全部切断”也不自动等于本项目完整任务目标。**
4. **自动纠正蒸馏仍有证据缺口。** FineVLA 的动作学习标签经过人工核验，LeHome 真机 RL 尚未统一，SC-VLA 的自纠正依赖冻结基座外残差；这些不支持“GPT 纠正已自动闭环成稳定独立 policy”的结论。
5. **本轮没有找到可直接证明少示范、全局零成功、同 θ 双向、通用单臂、真实 off-policy 与真异步全部同时满足的新开源基线。** 这是当前检索结果，不是不存在证明。下一轮必须拆成调用链和反例，不能用另一个大名单代替验证。

## 6. 证据边界与检索失败

- 正文阅读均为原始 arXiv HTML 的方法/关键实验段落及部分附录，不声称逐字读完所有论文；作者项目/README、HF 卡片和文件列表不等于源码审计。
- 原始来源成功可访问时优先使用原始来源；搜索中出现的代理镜像、聚合站与 Awesome 清单只作发现线索。
- CO-RFT、Prism-GRPO、ForceRFT 和闭环坍塌论文的定向搜索未定位官方训练仓库；这是“未查明”，并非 HTTP 404或断言未开放。SC-VLA 仓库只见搜索返回的 README；HITL-DP 只读项目。
- PRISM 同名 LMM 资产、非 manipulation 的驾驶/UAV 和不能建立作者关联的 RAPID 不混入本名单。HF prompts/initial frames 不称作完整 RL transition 数据。
- 本轮不核 citation count，也不宣称作者项目展示等价于第三方复现。极新论文尤其需要 S2 固定 commit、版本和许可证，再做 S3 的任务反例。
