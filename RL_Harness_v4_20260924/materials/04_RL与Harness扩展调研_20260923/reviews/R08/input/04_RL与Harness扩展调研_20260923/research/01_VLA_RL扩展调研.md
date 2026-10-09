# VLA 强化学习扩展调研：原生动作模型、完整动作头与异步执行

调研截止：2026-09-23。本文是扩展研究记录，不是正式审查轮的结论，也不代表完成了真机复现。所有性能数字均注明其出处和适用条件；没有自行运行论文训练代码。

## 1. 先明确我们实际上在选什么

本项目不是寻找一个在仿真排行榜上最高分的 VLA，而是寻找能嵌入如下真实训练闭环的学习器：

> 少量正反向示范 → 低成功率的共享策略 → 真机执行 → GPT + Harness 观察、判断和必要纠正 → 真实执行数据与可靠纠正标签进入训练 → 正反任务持续循环。

第一项任务为单臂抓放，另一臂暂不参与。正反向使用同一个有目标条件的策略；两方向都训练，反向不是外接的固定复位脚本。初始成功率可以很低，包括观测到零成功。可以采少量示范，但不能假设已有可靠上游策略。本文不把 ACT 列为候选。按用户最新澄清，选型优先比较框架通用性、兼容性与代码完整度；松灵硬件适配属于部署成本，不作为排除高质量通用框架的核心理由。

因此要分别审查五件事：

1. **动作改进的自由度。** 新动作是任意物理动作、原生 flow 动作头的新输出，还是只能对原策略作有界残差、换噪声或候选重排？它决定弱基础策略能否走出原有动作覆盖范围。
2. **数据的使用方式。** 失败经历能否进入 TD；可靠纠正能否长期保留并用于 BC；是否必须先获得完整成功轨迹才更新原生 VLA？
3. **时间语义。** RL 学习的是提交的动作、实际执行的中间片段，还是包含推理延迟与待执行队列的决策？这三者不能混为一谈。
4. **资源与工程入口。** 有论文、有 GitHub、有模型权重，与有完整在线训练、数据和执行接口，是不同成熟度。特定机器人的驱动适配成本单列，不与算法通用性混为一项。
5. **与 Harness 的接口。** 能否标记目标、动作所有者、纠正来源、奖励版本、时间戳及真实后继状态？是否允许两个方向共用训练器而不混淆奖励？

“保留 VLA 表征、学习完整动作头”最容易把动作自由度、BC 与 off-policy RL 接起来，但它是一个需要实现和验证的组合路线，不能因为结构契合就宣称已经优于有真机代码的原生 VLA 方法。反过来，原生 VLA 方法保留了动作先验，往往有更好的初始行为，但也可能受候选覆盖、成功样本门槛或旧动作正则化限制。

## 2. 本轮最重要的结论与修正

**应把 Real-Time EXPO-FT 升为优先实测的开源挑战者，并撤回“EXPO 缺少异步执行实现”这一概括。** 本轮读到了先前遗漏的 `realtime_expo_ft.py`、执行采样器、replay 和训练入口。它们就在之前记录过的仓库提交中，不能把这次发现包装成代码最近才发布。[官方仓库](https://github.com/pd-perry/expo-ft/tree/803381fc3b4c91a0c47904f1b688fc5e35904f50)

但它还不足以直接替代当前完整动作头路线：原生 VLA 主要通过成功数据的 RTC-BC 更新，Q 主要训练候选选择和有界编辑；论文没有证明少量示范且几乎没有成功的条件下，能够自动获得足够的新动作。其原版运行器也没有实现“同一策略、正反目标、均由 RL 训练”的自主复位循环。

**直接改原生 flow 动作头的方案比之前覆盖的更丰富。** Q-VGM、OTQL、LWD 等值得进入研究视野；其技术方向比“固定 VLA + 很小残差”更接近本项目。不过，最新论文、机构背书、完整开源、可复现的弱基础策略实验，当前没有在同一个候选上同时满足，暂不宜仅凭论文效果把它们升级为工程主线。

**还有一些值得借用的部件，而不是整套基线。** WCM 是历史条件价值模型和辅助预测的参考；Robo-ValueRL 展示了价值估计、离线改进和部署适配的组合；FlashRT 是推理和 RECAP 条件化推理的工程线索。这些都不能按名字直接当成成熟的在线 actor–critic 真机训练系统。

建议技术方案保留一个可替换的 learner 接口，进行两条有明确预算上限的比较：完整动作头 BC + off-policy RL，以及经过目标条件与纠正数据改造的 Real-Time EXPO-FT。前者不是预设胜者，后者也不因发布时间新而自动胜出。实际选择应看两方向的独立完成率、纠正次数、复位人工时间，以及单位真机小时的改进。

## 3. 检索范围与证据分层

检索覆盖 arXiv、作者项目页、官方 GitHub、实际 Hugging Face 模型卡与数据集、科研机构发布页；社区帖子和汇总仓库只作发现线索，结论尽量回到第一方材料。既查 2025 年成熟工作，也查到 2026 年 9 月新稿，避免只搜已知算法名。

下表的证据层级不表示论文质量高低：

| 标记 | 本轮实际完成的工作 | 可以据此说什么 |
|---|---|---|
| A | 阅读原始论文/项目，并读关键学习代码、数据路径或运行器 | 可以讨论特定实现；仍不能声称已运行或在本机可复现 |
| B | 阅读原始论文/项目，并核仓库 README、开放资产或训练入口 | 可以判断开放范围与研究条件；不能保证代码每个分支与论文一致 |
| C | 第一方摘要、项目页或局部源码筛查 | 足以排入候选和识别显著限制，不足以作最终代码选型 |
| H | 继承前期调研，本轮不重复深审 | 应结合前期原始证据，不把它计为本轮新增深读 |

GitHub 未认证 API 在本环境遇到限流，部分 raw 请求超时。成功保存的代码及 SHA256 见 [抓取清单](vla_evidence/raw_manifest.json)。固定提交可核对的重点代码使用固定链接；未核全长提交哈希的仓库明确列为版本锁定未完成，不伪造完整可复现清单。

### 3.1 候选地图：原生 VLA、完整动作头及数据驱动改进

| 候选 | 日期或版本 | 主要机制与本项目相关性 | 本轮层级及关键限制 |
|---|---|---|---|
| [Real-Time EXPO-FT](https://arxiv.org/html/2609.18207v1) | 2026-09-16 | 原生 π0.5 RTC + 候选选择 + 快速残差；在线更新 | A；最值得新增实测，但原生 VLA 不是直接用 Q 更新；有界编辑与成功 BC 的冷启动门槛仍在 |
| [EXPO-FT](https://github.com/pd-perry/expo-ft) | 本轮核同仓 RT 分支 | 通过筛选和编辑扩展基础策略 | H + A 扩展；不得再用普通分支的认识概括 RT 分支 |
| [Q-VGM](https://arxiv.org/html/2606.08015v5) | 首版 2026-06，v5 09-17 | Q 引导 flow 速度目标，直接改动作 expert | B；最新版真实实验是离线提升；未核到官方完整训练仓库 |
| [OTQL](https://ansocho.github.io/otql-flow/) | 2026-07-07 | 最优传输目标与 Q 结合，直接训练 flow policy | B；官方 Code 标记 Coming Soon，不按开源可运行方案计 |
| [Learning while Deploying / LWD](https://finch.agibot.com/research/lwd) | 2026-04-30 发布，05-01 论文 | 分布式 IQL 与 Q 引导 adjoint matching，部署中收集数据 | B；16 台真机与任务数据条件强，未核到完整公开训练资产 |
| [PA-RL](https://policyagnosticrl.github.io/) | 2024-12 | Q 优化动作，再蒸馏到任意 policy | B；是直接改原生策略的重要成熟思想，异步与共享正反任务需另作改造 |
| [ConRFT / HIL-ConRFT](https://github.com/cccedric/conrft) | 前期候选 | BC/一致性训练与 Q 学习结合 | H；保留为成熟机制参考，具体 π0.5 移植和异步语义不能默认已有 |
| [HIL-SERL](https://hil-serl.github.io/) | 前期候选 | 示范回放、干预与 off-policy RL | H；可借训练和运行模式，不等于原生 VLA 已适配 |
| [Robo-ValueRL](https://arxiv.org/abs/2607.09866) | 2026-07-10 | 历史价值估计、质量条件化策略、在线残差适配 | A 局部代码；开源资产较丰富，数据量和训练算力远超“少量示范” |
| [IG-RFT](https://arxiv.org/abs/2602.20715) | 2026-02-24 | 干预状态加权回归、分层进度奖励、离线到在线 | C；真机线索相关，未核到完整官方训练代码 |
| [RedFlow](https://arxiv.org/html/2607.27782v1) | 2026-07-30 | 正负轨迹对 flow 的吸引、排斥和动作重定向 | B；可借鉴失败数据监督，不可把检索得到的动作伪造成真实 TD 转移 |
| [RECAP / π*0.6](https://www.pi.website/blog/pistar06) | 前期候选 | 价值/优势条件化改进，结合部署经验与纠正 | H；官方方法影响力强，社区实现和完整官方训练栈需分开审查 |
| [STEAM](https://arxiv.org/abs/2606.29834) | 2026-06 | 专家集成产生学习信号，RLinf 路径 | C，平台方向另审；“无手工奖励”不等于不依赖高质量专家 |
| [Q2RL](https://github.com/rai-opensource/q2rl) | 2026，RSS | 从 BC 提取 Q 初值并门控改进 | B 浅筛；GMM/可计算 BC 密度条件不能直接搬到 π0.5 flow likelihood |

### 3.2 候选地图：残差、隐空间、推理时选择与仿真规模化

| 候选 | 机制 | 筛查结论 |
|---|---|---|
| RLT、DSRL | VLA 特征或隐空间上的 RL | H；继续区分参考动作约束、latent 生成器覆盖和完整物理动作自由度，不能统一叫“VLA RL”后忽略这些差别 |
| [ZPRL](https://manutdmoon.github.io/ZPRL/) | 信息瓶颈 latent，再冻结动作生成器作局部隐空间 RL | B；真实任务证据有价值，但不会天然消除原生成器的动作覆盖限制 |
| [RL²-VLA](https://arxiv.org/abs/2607.26991) | 失败预测触发的 flow 速度组合修正 | C；先核冻结部分和离线数据条件，尚不足替代主线 |
| [PLD](https://wenlixiao.com/self-improve-VLA-PLD) | 残差专家生成经验，再自蒸馏回 generalist | B；有借鉴价值，但多阶段循环与单共享 policy 连续 RL 不同 |
| [Object-Centric Residual RL](https://www.microsoft.com/en-us/research/articles/object-centric-residual-rl/) | 物体状态条件残差，仿真训练并迁移真机 | B；需要仿真与物体状态获取，非现成的真机自主在线学习入口 |
| [OmniTacTune](https://colinyu1.github.io/omnitactune-site/) | 触觉参与的残差 VLA 改进 | C；对接触任务有价值，新增触觉硬件与标定条件，不是当前抓放的优先依赖 |
| [Guided Action Flow](https://arxiv.org/abs/2607.02092) | 离线 IQL 价值引导冻结 π0.5 | C；动作引导与永久 policy 更新是两件事 |
| [FM-Steer](https://openaccess.thecvf.com/content/CVPR2026/papers/Song_FM-Steer_Enhance_Generalist_Policies_with_Value-Guided_Cascaded_Denoising_CVPR_2026_paper.pdf) | 价值引导与级联去噪，提高反应频率 | B；异步执行值得参考，不是完整在线 RL + 自复位训练器 |
| [FPO / FPO++](https://github.com/akanazawa/fpo) | flow 策略的直接策略梯度 | B；应区分仿真训练与足式真机迁移，不能据此宣称单臂在线小数据优势 |
| [RIPT-VLA](https://github.com/Ariostgx/ript-vla) | 稀疏奖励的 rollout 分组优化 | B；公开训练入口与 HF 模型，主要是仿真；低起点提升不是实体自动复位证据 |
| [π-StepNFT](https://github.com/wangst0181/pi-StepNFT) | 逐步、含负样本的无 critic fine-tuning | B；公开 RLinf 派生代码，当前核到 LIBERO/ManiSkill 路径 |
| [Z-1](https://arxiv.org/abs/2606.31846) | π0.5、GRPO 与分支 rollout | C；RoboCasa 仿真为主，样本与复位成本结构不同 |
| [ALOE](https://arxiv.org/abs/2602.12691) | action chunk、个体动作估值与干预经验 | C；异步与纠正数据有参考价值，本轮未确认完整开源训练栈 |
| [ForesightFlow](https://arxiv.org/abs/2606.04968) | 联合动作与前瞻信息，辅助学习改进 | C；检索时出现同名金融项目，已排除，不能拿同名 GitHub 当官方代码 |

### 3.3 模型化 RL、价值模型与软件栈：不和算法混排

| 候选 | 类型 | 对本项目的定位 |
|---|---|---|
| [WCM](https://arxiv.org/html/2607.29613v1) | 历史条件 value + 辅助未来表征预测 | B；价值学习部件，当前公开范围不等于整套在线 RL |
| [RISE](https://github.com/OpenDriveLab/RISE) | π0.5 + 视频动力学/进度预测 + 想象中 RL | B；有 Piper 部署路径，值得后续模型化分支；世界模型数据与误差验证额外增加工作 |
| [VLA-MBPO](https://github.com/LAMDA-RL/VLA-MBPO) | 模型化分支 rollout | B；可减少真机交互，但引入模型误差和模型训练开销 |
| [WMPO](https://arxiv.org/abs/2511.09515) | 世界模型内策略优化 | C；不能把想象轨迹当无条件真实经验 |
| [VLAW](https://openreview.net/pdf?id=Ro0eQ0ly3q) | VLA 与世界模型联合改进 | C；先作为后续扩展研究 |
| [Imagine-RL](https://arxiv.org/abs/2609.24033) | 2026-09 新的未来表征/模型化改进 | C；过新，完整代码与真机训练条件待核 |
| [Prioritized Rollouts](https://arxiv.org/abs/2609.22879) | 世界模型不确定性决定 rollout 分配 | C；可借采样思想，非当前真机闭环主基线 |
| [FlashRT](https://github.com/flashrt-project/FlashRT) | VLA 推理与训练/RECAP 工程 | A 局部文档；推理加速和优势条件推理不能替代在线学习器 |
| [VLARLKit](https://github.com/VLARLKit/VLARLKit) | 多模型、多算法训练平台 | B；支持表与 TODO 必须逐项核，不以 README 全表等同已复现 |
| [RLinf](https://github.com/RLinf/RLinf)、[verl-vla](https://github.com/verl-project/verl-vla)、[LeRobot](https://github.com/huggingface/lerobot) | 软件平台 | 平台专项另行深审；不能用“支持 π0.5”替代对 loss、真机环境与异步 replay 的检查 |

这里已经覆盖原生直接优化、策略提取、残差/隐空间、价值引导、模型化、推理加速与分布式平台几类机制。不是每篇论文都值得等量深读：缺代码、仅仿真、大规模专家数据、需要额外硬件等，会在本项目条件下提前降低优先级。

## 4. 深审 Real-Time EXPO-FT：本轮可能改变选型的主要发现

### 4.1 为什么它比“再找一个 residual RL”更重要

这项工作直接处理慢 VLA 推理和较快执行之间的错位：提前计算基础候选，用较新观测选择/编辑将要执行的动作段，再从真实执行窗口构造训练数据。它不是只给一个 SAC 方程而让使用者自行解决异步训练语义。论文来自 Stanford 的 Perry Dong、Kuo-Han Hung、Dorsa Sadigh、Chelsea Finn；机构与作者连续研究积累提升了可信度，但不能代替任务条件匹配。[论文](https://arxiv.org/html/2609.18207v1)

原文 Table I 的四任务均值分别是：普通 SFT 为 12.5/30（约 42%），SFT with RTC 为 18/30（60%），Real-Time EXPO-FT 为 29/30（约 97%）。摘要的 42%→97% 比较普通 SFT，不是从 RTC-SFT 的 42% 起步；以 RTC-SFT 为参照则是 60%→约97%。每任务每方法评测30次，不能把跨任务均值当单一任务样本率。已有任务相关 RTC-SFT、检测器与 DROID 依赖均需保留；任务也不是本项目共享正反循环。

原文 §V-C 明写复位按任务由自动流程或人工完成，§VI 进一步将人工复位列为限制；评测成功由人工观察员独立核验。因此 rollout 无人工动作干预不等于无人工复位、无人工评测或无人值守。在线预算至多十分钟机器人数据，部分任务按任一方法达到30/30提前停止；它不包括示范、复位、训练与评测全部墙钟成本。附录还写明更新在 episode 边界集中执行，完成十个 episode 后才开始训练。以上是真机交互效率证据，不能写成本项目全闭环只需十分钟。[项目页](https://pd-perry.github.io/real-time-expo-ft/)

论文 Training Procedure 还明确先以示范／RTC-SFT 获得约 30% 或以上的基础成功率再在线训练。这是作者的实验启动条件，不能改成本项目的统一准入门槛；它进一步限定了该研究对包括零成功起点的直接证据。[原文](https://arxiv.org/html/2609.18207v1)

### 4.2 可运行入口与版本

主仓库固定提交：`803381fc3b4c91a0c47904f1b688fc5e35904f50`，MIT。核到了 `train_offline_rtc.py`、`train_pi_robo.py`、`train_pi_robo_async.py`，以及 `scripts/dynamic_pick/` 下离线训练、policy/server/异步 server 等脚本。依赖作者修改过的 OpenPI 与 DROID 分支；这两个依赖的完整锁定与安装验证尚未完成。因此本文使用“有真实训练入口”，不使用“已在我们的机器人上可运行”。[固定仓库](https://github.com/pd-perry/expo-ft/tree/803381fc3b4c91a0c47904f1b688fc5e35904f50)

### 4.3 更新的到底是哪几个模型

| 模块 | 本轮读到的更新路径 | 对我们意味着什么 |
|---|---|---|
| Q / critic | 真实执行的短窗口回报 + bootstrap，集成 Q / target Q | 失败也可用于价值学习 |
| 编辑 actor | 有界动作编辑，按 Q 与熵目标更新 | RL 探索范围受编辑幅度和基础候选覆盖共同限制 |
| 原生 π0.5 | RTC prefix 条件下的 flow/BC 更新；actor batch 默认倾向成功数据 | 并非 Q 直接反传到整个原生 flow expert |
| 候选选择 | 从基础候选及编辑候选中按 Q 选择 | 可利用先验，亦可能放大不准的 Q 排序 |

`update_actor` 与 `update_edit_actor` 是不同学习路径。把两者都称为“VLA 经过 RL 更新”容易隐藏关键差别。原生 VLA 可以随着新可靠数据的 BC 改变，因此这也不是永久冻结的旧策略残差。但在新数据产生之前，它仍可能受候选覆盖限制。[学习器代码](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)

对弱基础策略，正确的问题不是“残差一定不行”，而是：当前候选与编辑是否能完成抓取、搬运、释放这些必要子动作？Harness 是否能提供覆盖缺口的可靠执行轨迹？如果能，加入这些数据的 BC 能改变后续基础分布；如果不能，单纯加候选数或 residual 步数不保证突破。

### 4.4 时间语义：与当前 queue-MDP 方案相同在哪里，不同在哪里

**输入条件也影响可比性。** 附录 VII-D.3–4 说明：Ball Balancing 的盘中心、球位置／速度，以及 Soccer Kicking 的守门物位置／速度，来自机器人自身观测中的成功检测器；它们进入 critic、noise-Q filter 和 edit policy，基础 VLA 的 state 与归一化不变。Ball Balancing 还移除 critic 的垂直 z 输入以免利用随时间漂移，并将 policy 图像改为外部相机的三帧历史，去掉腕部视图（critic 为九通道）；其余三任务使用外部＋腕部视图。DSRL/RLPD 的 critic 获得相同附加状态。这里不是外部真值，但“同一相机硬件”仍不等于“同一模块信息”。[原文 VII-D.3–4](https://arxiv.org/html/2609.18207v1)

迁移比较须列出 actor、Q、候选筛选器、编辑器及 Harness 各自可见的原始视图、历史、派生特征和可用时间；统一可获得的信息来源，或另做有／无派生特征消融。特征提取的计算、标定与时延应计成本。不能把输入改进全部归因于 RL 损失，也不能把离线未来信息偷偷交给在线决策。

符号提醒：本节沿用 RT-EXPO 的 C 表示执行窗口长度；技术附录的 C 则表示旧承诺动作序列，二者不同。

设动作预测长度为 H、推理延迟 d 个控制步、每次计划实际执行 C 步。RT-EXPO 从预测中取 `[d:d+C]` 作为该窗口，前面的延迟段不执行，后面的尾段留待新计划替换。它还用已执行前缀约束 RTC 的新采样，并在 critic backup 中使用与延迟对应的观测与前缀。`update_critic` 使用 `γ^C`，并非给每个预测 chunk 都算一个一步转移。[学习器固定代码](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)

| 方面 | RT-EXPO 原实现 | 当前系统应保留的额外约束 |
|---|---|---|
| Actor 的采样条件 | 延迟观测与 RTC 前缀，近实时编辑使用较新观测 | 保存因果观测版本，不让未来信息进入待部署 actor 输入 |
| Critic 的时间对齐 | 执行窗口、n-step reward、对应下一窗口 | 所有者切换、任务切换和真实执行长度都必须可追溯 |
| 队列语义 | 固定 delay/replan 配置和缓存前缀 | 实机取消确认、late result 丢弃、epoch/lease 与控制权仲裁 |
| Markov 假设 | 作者依赖新观测编辑来恢复反应性 | 基础候选还依赖旧观测/队列，不能无条件认为仅最新图像已充分 Markov |
| 超时与变长 | 存在等待 pending inference 的路径 | deadline overrun 必须定义安全行为与训练掩码，不能继续假定固定 C |

因此不能把 RT-EXPO 的 Q 输入直接塞进当前“显式队列状态”的 Bellman 目标里。两种实现必须各自做到数据、状态和目标自洽，然后在统一任务预算下比较。借用它的执行片段回填和 RTC prefix 很有价值；借用其公式但丢失相应采样过程，会制造新的错配。

### 4.4.1 延迟实验的两个条件：不能合成一个自然时延结论

复审重新读取原文附录 VII-E.3 后补充：论文区分 **wall-clock 注入**与 **chunk-delay** 两种条件。前者在 30 Hz 下令显式 chunk delay 为 0，对踢球、平衡和递物的每次 sample-actions 调用加入 100 ms sleep；Dynamic Picking 不额外注入这种 wall-clock 延迟。后者取 d 步前观测，将在途前缀填入 chunk 的 `[0,d)`，执行 `[d,d+C)`；Dynamic Picking 用 d=3，其他用 d=5。不能把两个条件相加成统一延迟，也不能将注入实验称为所有部署设备上自然测得的端到端时延。[原文附录](https://arxiv.org/html/2609.18207v1)

正文所列 `[d:d+C]` 描述的是 chunk-delay 机制，不覆盖全部实验配置。原文 §V-C 报告服务器自然推理约 67 ms，三个任务额外加 100 ms 后约 167 ms，Dynamic Picking 保留约 67 ms；d=3 对应控制步预算约 100 ms，不应把离散步预算与自然推理耗时强行写成相同数值。四任务成功率汇总不能据此解释为四任务都在同一种额外 100 ms 设置下获得。项目评估应分别记录观测龄期、实际推理/传输/排队耗时、额外 sleep 和人为旧帧，先测目标部署自然时延，再做可控注入消融；不能把上游协议支持当成本项目 deadline 已可满足。

### 4.5 回放与接管：原代码已经做了什么，还缺什么

训练入口记录的是 `real_action`，而不是原始预测动作。回放以逐步真实动作回填较长窗口；n-step 回报按时间折扣累加，终止/截断窗口具有有效性掩码。这个机制比直接存整段未执行预测更接近我们的需求。离线 demo 插入时被标记为 HIL/成功；这对已有可靠示范合理，但不能照搬为“所有 Harness 建议都是专家成功数据”。[执行入口](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/train_pi_robo.py)、[回放代码](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/replay_buffer.py)

采样器在人工接管时清除旧计划和 pending inference。它解决了程序内的计划更新问题，但 Python future 的取消不是物理控制器的停止确认。接到本项目时还需要将来源扩展为 Harness，并接入 gateway 的所有权版本。[采样器代码](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/utils/loop_utils.py)

`batch_processor` 也有需要避免的误读：`use_dagger_hil_sampling` 的专门说明针对 RTC learner；并不能据此宣称 Real-Time EXPO 默认已经让所有失败局部纠正进入 actor。若 `offline_ratio=0`，demo 可以只是播种到在线环形池；只有采用独立池与采样配额，才具有我们需要的长期保留语义。[batch processor](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/batch_processor.py)

建议改造时明确增加三个入口，而不是复用一个 `is_hil=True`：

- **真实经验入口**：策略或 Harness 已执行动作与观测到的后继，可参与 off-policy TD；失败不自动剔除。
- **可靠纠正入口**：经过可行性与结果验证的局部标签，可在整回合失败时仍参与 BC；保留来源和失效条件。
- **未执行候选入口**：存储建议、置信度和当时状态，可用于后续查询、监督筛选或模型化验证；没有真实后继就不能伪装成实体 TD 转移。

### 4.6 是否适合正反共享策略

原版证明了单任务动态控制，不等于证明了目标条件正反共享。修改至少覆盖：VLA prompt/goal、critic/edit 的 goal 输入、每条 replay 的 goal、分方向 reward、任务切换边界和 demo 采样配额。原训练入口在 episode 末尾调用 `env.reset()`；我们的反向 policy 必须替代这个“外部场景复位假设”，而不只是把 reset 函数换个名称。

两方向不是两份松散的训练脚本：应共享参数、目标条件和同一控制 gateway，同时保留分方向指标。双向可降低复位劳动，但不会数学上保证正向改进；梯度冲突、逆向更易学以及两端状态覆盖不均，仍需单独检查。

### 4.7 RT-EXPO 的最终定位

**推荐进入首轮实体对照，而不是立即替换全部设计。** 它是目前本轮发现的、最能同时触及 π0.5、真实在线学习、异步 middle-chunk 与实际训练代码的候选。应先验证三个关口：少量 demo 后双向动作覆盖、加入 Harness 可靠纠正后的 base 更新、与通用 gateway 的时序和回放契约兼容。具体硬件驱动另计部署工作；不能因为原论文用 DROID 而降低算法层面的优先级，也不能用论文平均成功率代替本项目验证。

## 5. 原生 flow 直接优化：哪些方案可能最终超过完整动作头

### 5.1 Q-VGM：机制最相关，但版本和开放状态容易读错

最新版用 Q 引导局部 flow 速度目标，减少穿过完整去噪链反传的开销；冻结部分 VLA 特征，并在 action expert 上产生实质更新。离线价值学习和在线 TD 分阶段结合，理论上比固定小残差更有能力改变基础动作分布。[v5 论文](https://arxiv.org/html/2606.08015v5)

必须按版本引用：v5 在 2026-09-17 更新。该版本的真实双臂三任务结果为**离线**改进，不能把早期版本或仿真在线结果拼成“真机在线从零成功学会”。其 LIBERO SFT 起点也已较高，不是本项目冷启动证据。论文中的参考速度/局部正则并非完全没有约束，但在线参考可以更新，不应等同永远贴着初始错误动作。

本轮没有核到与论文对应的官方完整训练仓库。结论是列为优先跟踪的算法，而非已具备低移植成本的开源主线。未来若代码发布，应重点检查 Q 输入是否真正区分 chunk、在线参考何时更新、Harness 局部 BC 与速度匹配梯度如何共存，以及执行片段目标如何定义。

### 5.2 OTQL：BC 友好的策略提取方向，尚缺现成代码

OTQL 用价值加权的最优传输构造 flow 学习目标，同时考虑采样步数。作者展示 VLA 与真实机器人改进，对保留原生动作头很有吸引力；然而官方项目页在本轮核查时仍写 **Code (Coming Soon)**。其论文实验预算也不能直接推广成无需准备示范和复位的在线系统。[项目页](https://ansocho.github.io/otql-flow/)、[论文](https://arxiv.org/abs/2607.06262)

它可作为未来替换 actor loss 的研究路线，而不是先花工程时间自行重写论文、再称之为更可行的基线。若需要自行实现，风险可能高于在成熟 off-policy 框架上使用完整头。

### 5.3 LWD：部署学习的重要证据，资源条件不匹配

LWD 将分布式 IQL 与 Q 引导 adjoint matching 结合，在多机器人部署数据中迭代策略，证明“原生 flow 的持续改进”不只存在于仿真。机构包括上海创智学院、AGIBOT Finch 与 Columbia，官方资料展示了 16 台机器人、8 类任务的部署规模。[官方发布](https://finch.agibot.com/research/lwd)、[论文](https://arxiv.org/html/2605.00416v1)

这类证据值得重视，但其人类介入、已有数据和集群条件远强于首台单臂少量 demo。未核到完整官方代码、权重与训练数据的公开交付，不宜仅因机构和真机规模而指定为本项目最可行基线。可以借鉴它把部署经验纳入反复策略提取的组织方式。

### 5.4 PA-RL：不要因年份较早而忽略策略提取这条路

PA-RL 的关键不是某个特定 VLA，而是先用 critic 改善动作候选，再通过监督学习把改善吸收到 policy 中。它解释了为什么“有 BC”不等于“只是成功样本 SFT”：监督目标可以由价值优化构造，失败经验也可以训练价值模型。[作者项目页](https://policyagnosticrl.github.io/)、[论文](https://arxiv.org/abs/2412.06685)

对本项目，这也是一条不必对整个 flow 采样链求梯度的思路。不过，动作优化结果必须经过可行性筛选；Q 对分布外动作过估计，可能让 BC 高效学到错误。Harness 的物理执行验证能补这一环，但会消耗真机预算，不能认为候选动作优化免费产生可靠监督。

## 6. 价值与推理部件：可借用，但不能混淆边界

### 6.1 WCM：公开的是价值学习的重要部分，不是已经交付整套 RL

WCM 把历史、语言与机器人观测用于价值估计，并通过动作条件的未来表征预测辅助训练。官方公开了 value 训练、returns 处理与评估入口，Hugging Face 有真实模型/数据资产。其 README 同时说明对应 RL 代码将逐步开放，因此不能把公开 value 模型直接认定为完整离线到在线复现。[论文](https://arxiv.org/html/2607.29613v1)、[README](https://github.com/sylvestf/WCM/blob/main/README.md)、[HF 集合](https://huggingface.co/collections/Sylvest/wcm)

与当前设计的关键区别是：WCM 的 value 主头不等于我们需要的 action-conditioned Q。辅助预测头使用动作，不意味着主头已能区分同一状态的两段候选动作。加入 queue、goal、action 后重建 Q，是新适配工作。历史可缓解部分可观测性，但错误奖励标签仍会训练出错误价值；它不能替代外部成功判定。

论文真实实验使用每任务约百条遥操作轨迹量级，不应作为“少量示范且基础策略零成功”的已证结论。建议作为 critic 表征或辅助损失的后续消融，首期不要再新增一套复杂价值预训练栈。

### 6.2 Robo-ValueRL：开放资产较完整，但“online RL”名称不足以判定学习方式

该项目公开了价值估计、离线策略训练、在线适配与 RTC 部署相关入口，HF 也有模型和数据链接。它用历史进度/剩余时间价值估计动作质量，结合质量条件策略与在线适配，真实精细操作展示具有参考价值。[仓库](https://github.com/Open-X-Humanoid/Robo-ValueRL)、[HF 模型卡](https://huggingface.co/X-Humanoid/Robo-ValueRL/blob/main/README.md)

但当前核到的在线训练入口使用 `FilteredBCPIAlgorithmConfig` 与 `adaptive_layer_only`，先处理采集 rollout 再训练适配层；不能因为文件叫 `online_rl` 就称为并发 SAC 式 actor–critic。README 的训练条件包括大量示范/在线数据和多 A100，和本项目少量数据、未知算力差异明显。[在线适配代码](https://github.com/Open-X-Humanoid/Robo-ValueRL/blob/main/robo_valuerl/train_robo_value_rl_online_rl.py)

许可也要拆开：HF 模型卡标 MIT，但仓库 README 的 License and Citation 段没有自动证明每份代码的许可范围。本轮未完成代码许可证独立核验，不能笼统写“全栈 MIT”。该项目适合作为历史价值、数据转化和部署适配参考，暂不提升为首选弱基础策略训练器。

### 6.3 FlashRT：检查当前仓库，不能沿用旧社区帖的状态

旧社区讨论提到过仿真和 RECAP 实验，但当前仓库已经更名/重定向，支持范围也有更新。本轮读到的 `docs/rl_inference.md` 是 advantage-conditioned π0.5 的 CFG 推理路径，提供 PyTorch/JAX、RTX/Thor 接口与性能测量。它还明确区分条件/无条件双分支融合和通用 rollout batch。[当前仓库](https://github.com/flashrt-project/FlashRT)、[RL 推理文档](https://github.com/flashrt-project/FlashRT/blob/main/docs/rl_inference.md)

它能降低推理延迟，从而缩短队列和 stale observation 问题，但不能自行生成 reward、可靠 TD、正反复位、控制权仲裁或持续学习数据。RECAP 训练支持应在平台专项进一步检查，不能把 `set_rl_mode` 这个推理开关当成在线 RL trainer。

## 7. 开放程度、权威性和影响力审核

### 7.1 重点候选的开放状态

| 项目 | 版本固定与许可 | 权重/数据 | 审核后的开放程度 |
|---|---|---|---|
| RT-EXPO | 主仓全 SHA 已固定；MIT；依赖 fork 未全锁定 | 依赖 π0.5 和任务 RTC-SFT；未核完整任务资产清单 | 有真机训练/执行代码；共享目标和 Harness 数据接口仍需扩展 |
| WCM | GitHub 短提交 `d028ebb`；MIT；全长 SHA 未锁 | HF 有 `WCM_LIBEROplus`、`pick-place-wcm-ckpt` 与数据集 | value 组件公开；对应完整 RL 发布仍不齐 |
| Q-VGM | 论文 v5 固定；未核官方训练仓库 | 未核官方完整训练资产 | 论文级候选 |
| OTQL | 项目 Code Coming Soon | 未核 | 论文/项目级候选 |
| LWD | 未核完整官方代码 | 未核 | 机构研究结果，不能当开源基线 |
| Robo-ValueRL | 短提交 `1618bcb`；代码许可未完全核；HF 卡 MIT | 有模型与数据链接 | 开放资产较多，训练条件重；全 SHA 与许可待完成 |
| RISE | 官方仓库；代码 Apache-2.0 | 官方声明数据/权重 CC-BY-NC-SA-4.0 | 代码与资产许可不同，需按使用范围分别审核 |
| π-StepNFT | 官方仓库 Apache-2.0 | 配合已有 VLA/RLinf | 可研究的仿真训练实现，非既成真机自主系统 |
| Q2RL | 官方仓库 MIT | README 指向 HF BC policy/数据 | 有开放资产，但不是原生 π0.5 插件 |
| FlashRT | 当前仓库及局部代码/文档已读；未全锁依赖 | 依赖相应模型权重 | 推理/训练工程候选，在线闭环不由本轮证实 |

HF 的 **paper 页面不是模型开放证明**。模型卡也是声明，需要检查实际文件。检索中还遇到 `NS-VLA` 模型卡标明权重待论文接收、论文编号占位，因此未把它纳入可用基线。RLT 的编码器/解码器权重也不能直接当成训练好的完整机器人 RL policy。

### 7.2 如何看影响力

本轮没有取得可稳定复核的统一引用计数，不填“0 引用”，也不把搜不到当没有影响力。2026 年 7—9 月新作的引用天然滞后；作者机构、真实实验设计、源代码和后续复现比单一引用数字更重要。

截至本次检索的 GitHub 页面快照，EXPO 主仓约 128 stars，Robo-ValueRL 约 38，RIPT-VLA 约 170，π-StepNFT 约 58。网页缓存时间和当前 API 口径可能不同，这些只说明社区关注量级，**不说明有多少机器人成功复现**。没有把 star 数代入算法排名。[EXPO](https://github.com/pd-perry/expo-ft)、[Robo-ValueRL](https://github.com/Open-X-Humanoid/Robo-ValueRL)、[RIPT-VLA](https://github.com/Ariostgx/ript-vla)、[π-StepNFT](https://github.com/wangst0181/pi-StepNFT)

机构判断也采用相同标准：Stanford 的 RT-EXPO 有对应训练实现，因此当前可审计性高；LWD 的机构和机器人规模有分量，但缺公开交付时其直接可达性仍较低；社区 FlashRT 的优化代码可以实际检查，不能仅因作者机构小就忽略，也不能因性能表漂亮就视为完整机器人系统。

## 8. 结合最终 RL + Harness 框架重新选型

### 8.1 推荐顺序与不确定性

| 定位 | 推荐 | 保留条件 |
|---|---|---|
| 首期默认工程候选 | 完整动作头 + BC + off-policy RL，借成熟 HIL 训练框架 | 明确这是待实现/待比较的组合，不声称已优于原生 VLA；验证新头冷启动与表示信息充分性 |
| 首个必须认真对照的开源候选 | **Real-Time EXPO-FT** | 加共享 goal、可靠纠正 BC、数据来源和 gateway；对弱先验做动作覆盖诊断 |
| 优先评估的原生头真机候选 | **RAPolicy**；verl-vla TD3＋BC 为补充 | 弱起点／共享任务证据更近；先验动作与数据接口，再处理 hold、接管、latent 和队列契约；详见 §11 |
| 原生 flow 下一轮优先跟踪 | Q-VGM、OTQL；另以 PA-RL 策略提取作机制参考 | 等官方代码/资产成熟，或明确接受自行复现成本 |
| 可借部件 | WCM 历史价值辅助、FlashRT 推理优化、Robo-ValueRL 的数据/价值结构 | 不同时堆叠；只有当前瓶颈明确时加入 |
| 后续降低实体交互的路线 | RISE、VLA-MBPO、WMPO/VLAW | 先证明真实数据闭环和奖励可靠，再承担模型误差验证 |

不能在未测之前把 RT-EXPO 写成绝对次优。完整动作头丢弃原生动作先验可能需要更多数据；RT-EXPO 只要候选覆盖已经包含有用行为，就可能更快进入有效学习。相反，当抓取/释放等必要动作根本不在候选和编辑范围内，完整头的自由度更有价值。这个分界只能通过实际覆盖与等预算实验判断。

### 8.2 第一个比较实验应如何设计

先把环境、真实执行日志、成功判定、双向目标切换和少量 demo 固定，再换 learner。不要一条路线给更多 Harness 纠正或更容易的起始场景，然后比较成功率。

1. **固定初始数据。** 正反各有少量真实示范；分离训练与评估起始状态。记录 base 在两方向的独立成功率，但不把某个跨任务通用百分数作为方法证明。
2. **检查行为覆盖。** 对 RT-EXPO 统计候选/编辑能否生成有效接近、抓取、抬升、搬运、释放；对完整头检查 BC 后是否具备基本闭环动作。不能只有平均末端误差。
3. **先验证数据正确。** 对齐观测、提交、执行、取消、接管与任务切换；检查 TD 只使用合法后继，BC 只用通过审核的纠正。没有这一关，不进入长时间自学习。
4. **按相同真机预算训练。** 统一实体小时、demo 数量、Harness 调用与执行纠正预算；记录 GPU 开销和停机等推理时间。
5. **分开测 policy 与系统。** 一项评估关闭 Harness 动作纠正，仅保留保护停机；另一项评估整个自主系统。否则强 Harness 可能掩盖 policy 没有学会。
6. **按实际瓶颈选路线。** 若 native 分布覆盖不足且 BC 也没有新可靠数据，就减少无效候选采样；若完整头始终学不出已有 VLA 的基本技能，则应考虑 native 路线，而不是继续坚持结构偏好。

### 8.3 Harness 融合对算法的实质要求

Harness 不是默认完美的教师 policy，而是观察、规划、调用技能、执行纠正与验证组成的系统。它可以通过执行产生真实 off-policy 数据，也可以产生未执行标签；这两类资料都值得保存，但训练资格不同。

| Harness 输出 | 可长期保存 | 能否直接进 TD | 能否进 BC |
|---|---|---|---|
| 实际执行且有后继的纠正动作 | 是 | 还须满足所选 MDP 的时序／动作契约，再按真实奖励和终止使用 | 通过质量与信息条件筛选后可以 |
| 未执行动作建议 | 是 | 不可以伪配 policy 执行后的后继 | 可作为候选，需可行性/质量验证 |
| 模型模拟的动作和后继 | 是，单独来源 | 只在明确模型化 RL 分支中使用，不混作真机事实 | 取决于模型和标签验证 |
| 成功/进度判定 | 是，带证据与版本 | 可生成奖励，但需隔离误判和回标版本 | 不能自动证明整段动作都适合模仿 |

因此“长期保留遥操作 buffer”的做法支持永久 demo 池，但不推出“未执行建议可作为真机 RL 转移”。这点与是否使用 DAgger 的命名无关，是 Bellman 学习依赖真实或明确建模的状态转移这一基本要求。

## 9. 可复核的代码阅读记录

以下是静态检查记录，不是执行通过声明。

| 文件 | 本轮确认的内容 | 尚不能据此声称 |
|---|---|---|
| EXPO `realtime_expo_ft.py` | 延迟片段采样、RTC prefix、Q/edit/base 分开更新、n-step 折扣 | 任意异步调度都满足 Markov；任意弱 base 均能学会 |
| EXPO `loop_utils.py` | pending chunk、执行历史、接管清理 | 物理控制器已确认取消；崩溃恢复账本完整 |
| EXPO `batch_processor.py` | offline/online 混采、成功 actor 池、特定 DAgger 采样分支 | 所有 demo 永久保护；所有局部纠正默认入 base actor |
| EXPO `replay_buffer.py` | 真实动作回填窗口、n-step 累积、终止/截断掩码 | 已具备我们全部目标/所有者/奖励版本字段 |
| EXPO `train_pi_robo.py` | `real_action` 入池、接管计划清理、episode 后 `env.reset()` | 已实现共享 policy 的正反自主复位 |
| Robo-ValueRL 在线入口 | filtered BC 与 adapter-only 配置 | 等同并发在线 SAC 或完全原生动作头 RL |
| FlashRT `rl_inference.md` | CFG 推理接口、条件化分支、硬件性能范围 | 有完整 reward、replay、optimizer 的真机持续学习器 |

本地成功下载的三份 EXPO 代码和 FlashRT 文档来自抓取时 `main`，其内容摘要与失败请求均保存在 `raw_manifest.json`；论文关键结论使用固定提交网页交叉核对。下一步工程复现应把依赖 fork、数据格式、模型权重和 Python/CUDA 环境一并锁定，而不是只锁一个主仓 SHA。

## 10. 检索词与遗漏控制

主要检索词按以下组使用；搜索结果不直接作为证据：

- 广搜：`2026 VLA online reinforcement learning real robot github flow matching low success`；`VLA off-policy 2026 github`；`robot VLA reinforcement learning Hugging Face September`。
- 新近论文：`site:arxiv.org/abs/2609 reinforcement vision-language-action`；`site:arxiv.org/abs/2608 off-policy robot`；`site:arxiv.org/abs/2606 flow off-policy robot`。
- 原生 flow：`Q-VGM github code`；`Optimal Transport Q-Learning github`；`Learning while Deploying github Agibot`；`VLA QAM github`；`Policy-Agnostic RL github robot`。
- 可能遗漏的局部改进：`Beyond Action Residuals github`；`RedFlow github VLA`；`Robo-ValueRL github`；`ForesightFlow github`；`pi-stepNFT github`。
- 工程入口：`Real-Time EXPO-FT github code`；`RISE OpenDriveLab reinforcement learning`；`RIPT VLA reinforcement learning github`；`site:huggingface.co VLA online RL 2026`。
- 机构和社区线索：官方 PI/AGIBOT/Microsoft/OpenDriveLab 发布，HF paper 页与模型页交叉核查，FlashRT 社区线索回到当前仓库；awesome 列表仅帮助发现名称。

此次检索拓宽了候选范围，但“未找到代码”只表示在本轮第一方材料及检索范围内未确认，并不证明世界上不存在代码。对非常新的工作保留跟踪条目；对会改变主线选择的候选，优先核训练入口、数据生成路径和损失，而不是不断增加摘要数量。

当前最需要被实验消除的未知数仍是：**在同样少量示范和可控 Harness 纠正预算下，原生头更新、实时编辑还是重学完整头，能更快把两个方向都训练到可用。** 本轮证据支持把这些路线加入分阶段比较，尚不支持提前宣布某一方获胜。

## 11. RAPolicy：新增优先原生头候选

### 11.1 为什么改变候选优先级

[RAPolicy](https://arxiv.org/html/2609.22888v1)于 2026-09-19 发布，来自复旦大学与新加坡管理大学相关团队。它同时提供弱起点真机、原生 π₀.₅ 更新和共享多任务证据，较仅在仿真验证的原生 TD3＋BC 更贴近当前条件。单任务每项十示范，四项初始／最终分别为 1/20→20/20、3/20→19/20、0/20→14/20、2/20→16/20；联合任务使用150条示范，整体26/50→44/50。这是作者有限试次，不是跨方法通用排行榜。实验仍有人类接管、二值奖励，八张3090，不能解读成零示范或无人闭环。

方法用 replay 行为训练 twin-Q 和 expectile 状态价值，下一状态用 V 备份；原生一步 flow 以优势加权条件似然学习，复用在线初始噪声。失败参与价值学习，actor 不对新动作求 Q 梯度，也不固定在弱 base 的小残差周围。约束转为 replay 行为覆盖：没有有用探索或纠正，仍不能保证从零成功起步。这里是机制与作者实验的解读，不是本项目实测。

### 11.2 已公开什么，哪些尚缺

官方项目网站实际链接到 [作者仓库](https://github.com/flyfaerss/RAPolicy)，不是同名第三方复现。固定提交为 `ef4b1044f0cc78c0f6143180a2d78ae267ab03ea`。仓库公开 RLinf fork、OpenPI 相关训练路径、真机配置、SFT／评测入口及 Apache-2.0 许可；明确未提供实验 SFT 权重和示范数据，依赖许可另算。发布检查不等于重新运行论文实验。当日仅约1 star／0 fork；机构与公开实现增加可审计性，独立复现和广泛验证仍未核得。[固定 README](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/README.md)

先前仅凭项目页抓取失败未确认代码；根审经官方入口和固定源码补核后修正为“代码公开、数据／权重未随包提供”。具体学习与资产证据见 [独立资产核查](../reviews/R07/rapolicy_asset_check.md)、[独立融合评估](../reviews/R07/rapolicy_joint_fit.md)。这两项不是额外正式审查轮次。

### 11.3 关键源码与融合边界

| 已核实现 | 对本项目的意义 |
|---|---|
| 真机示例采用 fixed action chunk、推理期间 hold | async 指采集／学习并发；不能据此认为已解决连续 C/E/D 替换 |
| `forward_awac_critic` 使用 replay 动作、冻结特征、Q／V，合并 termination 和 truncation | 契合失败数据复用；本项目 timeout／抢占不等于真终止，不能复制其 done 和 target |
| 在线接管动作对齐回模型空间，并保留原 rollout latent | 是实际行为记录路径；Harness 额外反馈不能倒填为旧观测的一次完整监督 |
| 固定 chunk 对终局后的尾部作吸收态 hold 填充 | 是上游训练张量约定，不代表这些步实际执行；本项目必须保留真实有效区间，不能把填充当物理事实 |
| actor 默认优势加权 likelihood，另有 flow-matching 消融 | 内部类名含 SAC 不代表默认最大熵 SAC，也不能将消融误作主方法 |
| 离线数据显式 `is_offline_demo`，actor 更新时重采噪声 | 支持无原始 latent 的真实示范；该目标是条件 log-density 的期望，不是反演专家噪声或真实边缘 flow 密度 |
| 接管＋快速成功池与普通 replay 混采，保留源接口但部分版本字段被清除 | 本项目另保永久种子示范、双向采样及完整事实版本，不能依赖上游字段默认齐全 |

上游并非让最快成功榜覆盖全部纠正：`add_realworld_demo_episode` 在淘汰较慢成功回合时仍保护其中接管条目。这与本项目保护可靠纠正的方向一致；新增的要求是双向／来源分层、初始种子和事实账本，而不是声称原版完全不保护干预数据。

代码入口：[launcher](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/run_rapolicy.sh)、[actor／critic worker](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py)、[异步 worker](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/async_fsdp_sac_policy_worker.py)、[chunk／接管处理](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py)、[离线 latent](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py)、[actor 消融](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/awac_actor_loss.py)。只做静态学习，未安装或执行。

折扣也须按实际配置读：`prepare_chunk_transition` 支持按有效步累计折扣，另有整块聚合分支；论文的 chunk 间 γ 与项目微步 γ 不可机械互换。纯建议没有真实后继，无论上游怎样保存 demo，都不能变成真实 TD。

### 11.4 联合选择结论

**将 RAPolicy 升为首要原生头预检候选；不直接替换已定义的队列契约。** 比较顺序是接口和双向 BC／覆盖预检，再比较连续执行改造成本、合法数据密度，最后同预算实测。RT-EXPO 保留实时执行证据的独立价值，完整头方案保留清楚的队列参考，verl-vla TD3＋BC 作为补充。无需同时移植全部方案。

如果采用 RAPolicy，须单独规定 goal／队列状态、回报和终止、部分监督与噪声资格、发布边界；不能把整块 V-backup 直接塞进 06 的 actor-Q 梯度公式。状态价值偏向 replay 中较优行为，其提高不证明当前 policy 已能独立完成 Harness 曾代做的动作。须继续测两方向关闭辅助后的成功率、Harness 依赖、恢复与人工工时。以上是融合推断及待实现门槛，不声称原论文已经完成。
