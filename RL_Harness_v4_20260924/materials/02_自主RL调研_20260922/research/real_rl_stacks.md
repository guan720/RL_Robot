# 真机 RL 基础系统与模型更新路线专项审计

访问日期：2026-09-22。范围：机械臂操作、移动操作；目标是减少真机持续学习中的复位、接管、现场值守。仅只读访问了 `embodied-scientist` 的角色入口、状态、索引和 D10/D11/D12 章节，未改知识库。以下是原始文献和公开代码审阅，不是本地训练或实机复现。

## 选型结论

工程基座优先比较 **HIL-SERL/SERL 生态**；已有扩散/流策略时比较 **DSRL**，已有 ACT 或其它黑盒 BC 时比较 **ResFiT**。但这些学习器均不能单独解决无人值守。**AutoSERL** 最直接针对自动接管，仍有人工奖励、有限恢复范围和源码问题，适合研究性候选。**DayDreamer** 对持续在线学习有真实证据，但依赖受控工位和动作约束。**FLaRe** 应放在移动操作的仿真训练路线中；**TD-MPC2/RLPD** 是可复用学习算法，不是已经交付的自主真机训练工厂。

评级是本次工程判断：A=优先作为基座试验；B=按已有模型选择；C=研究备选；D=不直接解决本次主目标。不同方法的成功率、训练时间因任务、初值、人工预算不同不能横向排序。

| 候选 | 更新对象 | 主要减少什么 | 尚存关键人类工作 | 本次定位 |
|---|---|---|---|---|
| SERL | 小型视觉 actor/critic，可另学反向策略 | 样本数；特定搬运任务的复位 | 初始示范、奖励设计/样本、工位设置、异常处理 | A：生态与反向策略参考 |
| HIL-SERL | 小型视觉 actor/critic | 复杂接触任务的训练样本和后期接管率 | 训练期间接管；多项任务人工复位 | A：成熟基座/有人上限 |
| AutoSERL | actor/critic + 示范导出的自动纠正器 | 在线动作接管 | 一条示范、两个恢复点、人工成功标注、部分重抓取 | C：贴题但须补工程 |
| RLPD | SAC 类 actor/critic | 用历史数据减少在线样本 | 所有机器人环境、奖励、复位、监督需要外加 | A：算法基线；非完整系统 |
| DSRL | 冻结扩散/流策略，学习初始噪声策略 | 额外演示、全模型更新成本 | 官方 π0 真机代码仍逐回合人工标奖与复位等待 | B：扩散/流策略优先 |
| ResFiT | 冻结 BC，学习逐步动作残差 | 大模型微调成本、探索难度 | 初始大量 BC 数据、人工复位与标奖 | B：黑盒 ACT/BC 候选 |
| RLT | 冻结 VLA/token，在线训练小 actor/critic | VLA 真机在线优化成本 | 奖励标注、阶段交接、可选接管、复位未自动闭环 | B/C：方法参考，官方代码未找到 |
| DayDreamer | 世界模型 + 想象中的 actor/critic | 从零演示需求、真实试错 | 工位与动作约束、维修/边界处理 | C：世界模型持续学习基线 |
| TD-MPC2 | 潜动力学、奖励、Q、策略；MPC | 算法调参和学习效率 | 真机接口/自动奖励/复位/恢复都需搭建 | C：MBRL 研究基线 |
| FLaRe | 在仿真里 RL 微调 BC Transformer | 真机训练期间的人类劳动 | 仿真与任务设计、真实抓取启发式、部署 | D：移动操作 sim-to-real 支线 |

## 1. SERL（2024，ICRA 2024）

**机制。** RLPD/SAC 系离策略学习，演示/先验回放与在线回放对半采样；用高更新数据比和 critic LayerNorm 支持有限真机数据上的多次梯度更新。成功、失败及次优转移都可用于 TD 学习，并非成功轨迹行为克隆。奖励可来自手工状态判据、二分类器或在线更新负样本的 VICE。特定搬运设置训练独立的正向/反向两套策略，各有奖励和 Q。每任务 20 条初始遥操作示范。[论文 §4–5](https://arxiv.org/html/2401.16013v1)

**真实证据。** Franka 的 PCB 插入、线缆卡入、箱间搬运；作者报告 25–50 分钟量级，论文将 PCB/线缆的计算、复位和计划停顿计入墙钟。搬运涉及两套策略，不能把单策略时间当完整循环总时间。单 RTX 4090。作者合作团队在华盛顿大学复现插销任务，19 分钟、100/100；属于跨机构作者体系内复现，不能当无关联第三方验证。[项目](https://serl-robot.github.io/)、[论文](https://arxiv.org/html/2401.16013v1)

**开源和影响力。** Berkeley、Washington、Stanford、Intrinsic；训练、回放、奖励、Franka 环境有公开代码，控制器另库 `rail-berkeley/serl_franka_controllers`，主库 Apache-2.0。官方 README 已明确旧库弃用并指向 HIL-SERL；新项目可从后者基座吸收前者的正反任务设计。未把公开训练代码等同所有任务权重、数据一并齐全。[仓库](https://github.com/rail-berkeley/serl)

**适配。** 可逆、工位内、对象不易丢失的任务最值得先做。正反策略仍可能共同失败；需要外层状态判定、异常恢复和人类工时日志。

## 2. HIL-SERL（2024 预印本；Science Robotics 2025 出版信息需区分访问深度）

**机制与数据。** 从少量演示启动，离策略 RL 混入人类纠正；视觉奖励分类器由正负图像训练，早期频繁接管、后期减少。连续机械臂动作和离散夹爪动作使用相应策略/价值处理。示范、在线失败及接管转移均进入学习，不能用“训练后自主执行”替代“训练过程自主”。[项目方法](https://hil-serl.github.io/)、[论文](https://arxiv.org/html/2410.21845v1)

**真机与人力。** 一/双 Franka，多种插入、装配、动态操作；论文报告多数任务 1–2.5 小时达到高成功率。附录明确：线缆卡入、汽车面板、物体交接、同步带、Jenga 等用 **Human reset**；其它若干任务为 **Scripted reset**。Jenga 的奖励也由回合末人工标注。故不能统一说奖励、复位全自动。[附录 A 的任务配置表](https://arxiv.org/html/2410.21845v1)

**开源。** Apache-2.0，JAX；actor/learner 异步，经 agentlace 通信。示范采集、奖励分类器训练、策略训练和实机部署 walkthrough 均有入口，Franka 阻抗控制器有独立库。应逐项核对任务专用配置和硬件，不将主库视为所有论文任务的数据权重全集。[README](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/README.md)

**影响力。** Berkeley 团队，SERL 直接后继，多项新工作以其为底座。Science Robotics DOI 为 `10.1126/scirobotics.ads5033`，本次打开出版商页面返回 403，故机制和数字均引用实际打开的 arXiv 正文，不假称已读期刊版。[出版商入口](https://www.science.org/doi/10.1126/scirobotics.ads5033)

**适配。** 最适合作为有人监督可达性能基线和软件骨架；若以无人化为主指标，必须另配自动 reset/recovery，不能因成功率高直接中选。

## 3. AutoSERL（2026；项目/仓库声明 ECCV 2026 接收）

**机制。** 用一条演示和人工指定的安全恢复点、接触恢复点建立滑动窗口纠偏；停滞时退回恢复点并重放局部示范；达到低干预且成功的条件后终止后续自动干预。离策略缓冲区使用自主和自动纠正经验。它是以规则和示范重放替代在线动作接管的 harness，不是让 RL 凭空学会全部恢复技能。[项目](https://autoserl.github.io/)、[README](https://github.com/autoserl/AutoSERL/blob/main/README.md)

**真机。** Franka+D405、UR5+Inspire+D435，两平台六任务，6D 末端增量动作。作者表格报告插入约 8 分钟，悬挂 25–35 分钟，抽屉 45 分钟；各任务无干预评测 50 次。主对照无场景随机化，另测插头初始平面 ±3 cm；不是大范围开放环境泛化。论文明确奖励仍是 **人工标注二值稀疏奖励**。复杂失败模式和更高维动作被列为局限。[正文 §3–5](https://arxiv.org/html/2607.01651v1)

**源码抽查发现三项实质边界。**

- `auto_intervention_wrapper.step` 仍读取 SpaceMouse 左/右按钮；左键作成功奖励，右键终止。`plug_insert/config.py` 也套用了人工动作/奖励 wrapper；不能称官方流程无人工值守。[wrapper](https://raw.githubusercontent.com/autoserl/AutoSERL/main/serl_robot_infra/franka_env/envs/wrappers.py)、[配置](https://raw.githubusercontent.com/autoserl/AutoSERL/main/examples/experiments/plug_insert/config.py)
- 插入环境有脚本回到初始位姿；异常重抓取 `regrasp()` 需要键盘触发，并等待用户放回物体。恢复机械臂姿态不等于恢复整个物体场景。[任务环境](https://raw.githubusercontent.com/autoserl/AutoSERL/main/examples/experiments/plug_insert/wrapper.py)
- 当前 main 的恢复分支把一个初始化为列表的字典元素直接与整数 1 相加后作为切片上界；按所读代码，这个分支触发时存在 `TypeError` 风险。没有运行实机证明发生频率；只认定静态源码阻断疑点，不替作者静默修复。[源码约 L338、L439、L457](https://raw.githubusercontent.com/autoserl/AutoSERL/main/serl_robot_infra/franka_env/envs/wrappers.py)

**开源/机构。** CAS 自动化所、BAAI、PKU-PsiBot、国科大、北大；训练/机器人框架公开，直接继承 HIL-SERL。根目录未见许可证文件，不能仅因基于 Apache 项目便宣布整个新增代码许可明确；示范路径仍硬编码为作者本机绝对路径，尚未核实其任务演示与权重完整可下载。[仓库](https://github.com/autoserl/AutoSERL)

**适配。** 对固定目标、6D 接触操作十分贴题，列研究 shortlist；中选前先确认奖励自动化、异常重抓取、恢复分支和授权范围。

## 4. RLPD（2023，ICML 2023）

**机制。** 将已有离线数据和实时交互混合训练 SAC 类 actor/critic，以 LayerNorm、critic ensemble、高 UTD 等减少样本浪费；不要求先离线预训练。失败和次优数据仍有 Bellman 学习价值，不需把数据筛成成功集合。它本身不提供自动成功识别和复位策略。[论文和会议信息](https://proceedings.mlr.press/v202/ball23a.html)、[正文](https://proceedings.mlr.press/v202/ball23a/ball23a.pdf)

**代码证据。** `train_finetuning.py` 的离线混合比例默认 0.5；每步真实执行的转移写回 replay，回合末直接调用 `env.reset()`。原库的示例是 D4RL、Adroit、V-D4RL 等仿真/离线基准；不能据这些代码声称原论文已完成无人真机机械臂训练。SERL 是其工程后继证据，应分开记账。[训练入口](https://raw.githubusercontent.com/ikostrikov/rlpd/main/train_finetuning.py)

**开源/影响力。** 主库 MIT（文件叫 `LICENCE`），算法、像素/状态训练入口和数据下载指引公开；不含通用机械臂控制或训练工位。Berkeley 系作者及 ICML 正式论文，影响力更适合看 SERL/HIL-SERL 等方法继承，而非拿旧库维护频次判断算法失效。[仓库](https://github.com/ikostrikov/rlpd)、[许可](https://raw.githubusercontent.com/ikostrikov/rlpd/main/LICENCE)

**适配。** 必须保留的简单离策略基线；实际真机工程建议用成熟机器人封装，勿从 Gym 示例误推设备已即插即用。

## 5. DSRL（2025，CoRL 2025）

**机制。** 冻结扩散/流动作模型，把去噪初始噪声视为 RL 动作，学习噪声分布以选择高价值行为。只需可注入噪声的黑盒模型接口；DSRL-SAC 直接在噪声空间做 SAC，DSRL-NA 另外从物理动作价值蒸馏噪声价值。成功失败交互均进回放；并不只是成功样本微调基础模型。[项目](https://diffusion-steering.github.io/)、[算法 README](https://raw.githubusercontent.com/ajwagen/dsrl/main/README.md)

**实证。** Franka 单任务由 10 条示范训练基础扩散策略，再 3,500 在线步约 40 回合；作者报告评测 2/10→9/10，样本数小，应保留二项不确定性。另有 Bridge V2 预训练的 WidowX 多任务适应；2025 v2 正文核实这些实验，不把所有后续 π0 代码结果反填到早版论文。[论文 §5.3、附录 C](https://arxiv.org/html/2506.15799v2)

**开源与关键人工依赖。** 两个官方仓库：`ajwagen/dsrl`（通用实现，根许可证未找到）与 `nakamotoo/dsrl_pi0`（MIT，Franka+DROID+远程 openpi 推理）。后者明确有真机启动脚本；但 `train_utils_real.py` 每回合等待键盘 1/0 标奖，复位后进入 `pdb` 等待继续；这直接否定“现成无人值守版本”。发布的通用权重下载指引存在，本文未下载验证权重，不能宣称所有任务权重齐全。[真机说明](https://raw.githubusercontent.com/nakamotoo/dsrl_pi0/main/README.md)、[交互循环](https://raw.githubusercontent.com/nakamotoo/dsrl_pi0/main/examples/train_utils_real.py)、[许可](https://raw.githubusercontent.com/nakamotoo/dsrl_pi0/main/LICENSE)

**机构/适配。** Berkeley、Washington、Amazon；已有较好扩散/流策略时优先。受基础策略覆盖限制；选择已有行为模式通常比发明全新技能容易。需另接奖励和 reset/recovery harness。

## 6. ResFiT（2025；已发现 ICLR 2026 Lifelong Agent Workshop 版本）

**机制。** 固定 ACT/扩散等黑盒 BC 策略，在物理动作上叠加逐步残差；以 TD3 风格离策略方法、critic 预热、示范回放、n-step 和适度 UTD 学习。冻结先验支持稳定探索，但限制全新策略发现。成功示范先训练 BC，后续自主成功和失败均用于 RL。[项目](https://residual-offpolicy-rl.github.io/)、[训练入口与参数](https://raw.githubusercontent.com/amazon-far/residual-offpolicy-rl/main/README.md)

**真机与人力。** 29 DoF 轮式双臂、双五指手；毛球搬运基础 ACT 约 1,000 示范，134 次 RL rollout/15 分钟执行数据使 14%→64%；包裹交接约 900 示范，343 回合/76 分钟执行数据使 23%→64%。这些是执行数据时间，不能当含重置的人力墙钟。论文结论明确仍需要人类复位与奖励标注。[论文 §V–VI](https://arxiv.org/html/2509.19301v1)

**开源。** 官方 BC 训练和 residual RL 代码公开，README 的主要可复现例子是 DexMimicGen/Robosuite。尚未确认论文轮式人形真机控制栈完整发布；不能从训练源码公开推为整机可复现。许可证为 **CC BY-NC 4.0**，应标“非商业许可源码公开”，不要标宽松商用开源。[仓库](https://github.com/amazon-far/residual-offpolicy-rl)、[LICENSE](https://raw.githubusercontent.com/amazon-far/residual-offpolicy-rl/main/LICENSE)

**影响力。** Amazon FAR、Stanford、CMU、Berkeley；较强作者/机构背景不改变人工环节和授权限制。Workshop PDF 搜索返回正式抬头，但 OpenReview 页面遇验证；不将 workshop 写成 ICLR 主会。[Workshop PDF](https://openreview.net/pdf?id=I8rNl70C3C)

**适配。** 已有 ACT/黑盒动作块策略且能搭好环境的团队可试；用户目标是减少人工，先比较恢复和奖励的工程成本。

## 7. RLT / RL Token（2026）

**机制。** 将 VLA 末层信息压成重建训练的 RL token；在线冻结 VLA 和 token 模块，小 actor/critic 输入 token、本体状态和参考动作块，直接预测并锚定动作块。它不是简单动作残差，也不是 DSRL 噪声策略。回放包含基础策略、自主 RL、人工接管的真实执行动作。关键动作阶段集中进行 RL。[论文 §III–V](https://arxiv.org/html/2604.23073v1)

**实证和边界。** Physical Intelligence 的四种精细操作：螺钉、扎带、充电器、网线；作者报告分钟到数小时、关键阶段最高约 3 倍提速。人工选阶段交接并标终止成功/失败，可接管；作者明确把完全自主 pipeline 列为未来工作。交互有效时间和实际运营墙钟须分栏。[官方报告](https://www.pi.website/research/rlt)

**开源。** 本次在原论文、官方页面未找到 PI 官方完整 RLT 训练仓库或任务权重。发现独立复现 `Yyshadow/openpi-RLT`，以 openpi/π0.5 为底座，有 token、服务端、回放、actor/critic、机器人桥接和网线插入演示；这不是 PI 官方发布，也不是原 π0.6 原样复现。该库 Apache-2.0，另有 Gemma 条款；读取的是复现团队自述，没有本地重跑。[社区仓库](https://github.com/Yyshadow/openpi-RLT)

**适配。** 若 harness 中已有可暴露内部表征的 VLA，值得研究；以“减少现场监督”为首指标时优先级低于直接解决 reset/recovery 的路线。

## 8. DayDreamer（2022，CoRL 2022 / PMLR 2023）

**机制。** 在线经验训练离散潜状态循环世界模型，预测观测、奖励、结束；在模型想象中训练 actor/critic，真实世界只采集必要交互。使用包括失败在内的经验，而非只学习成功演示。两个异步进程分别采集与学习，TensorFlow 2 官方代码提供 A1、xArm、UR5 启动指引。[仓库](https://github.com/danijar/daydreamer)

**机械臂实证。** UR5 两箱搬运约 8 小时、xArm 约 10 小时；xArm 日照改变后继续训练恢复性能。奖励来自夹爪开合状态和已知目标箱规则，动作离散且有限制：只有持物才允许竖直移动、到目标箱上方自动开夹。倾斜箱、边界约束，xArm 物体还系绳防丢。不能把这种受控连续练习等同开放场景精细操作。[论文 §3、附录 A/E](https://proceedings.mlr.press/v205/wu23c/wu23c.pdf)

**其它本体边界。** A1 从仰躺恢复可自己学，但走到场地边缘仍由人处理位置；“无姿态复位”不等于无人工。Sphero 以随机动作重新采样位置，有外部视觉几何奖励。四足 1 小时结果不可套用为机械臂 1 小时。[项目摘要](https://danijar.com/project/daydreamer/)、[正文](https://proceedings.mlr.press/v205/wu23c/wu23c.pdf)

**开源/机构。** Berkeley 为主，Dreamer 作者共同参与；官方代码和实机启动命令公开，根目录本次未找到 LICENSE，不推断许可；依赖老版 TensorFlow/DreamerV2+，不是把最新 DreamerV3/V4 换入就已经复现。权重/全量真实数据公开状态未核实。[代码](https://github.com/danijar/daydreamer)

**适配。** 受控工位持续学习与世界模型研究基线；样本效率、感知变化适应值得借鉴，当前精细接触操作工程优先级低于 SERL 家族。

## 9. TD-MPC2（2023 预印本，ICLR 2024）

**机制。** 学习任务相关的潜状态转移、奖励和价值，不要求像素重建；用潜空间短滚动+终端价值进行 MPC。离线/在线回放都能更新模型；失败也是动力学和价值证据。公开代码将模型、reward、Q、终止头与 policy 分开更新，并在推理中优化动作序列。[论文](https://arxiv.org/html/2310.16828v1)、[实现](https://raw.githubusercontent.com/nicklashansen/tdmpc2/main/tdmpc2/tdmpc2.py)

**证据范围。** 原工作 104 连续控制任务来自 DMControl、Meta-World、ManiSkill2、MyoSuite，不能写成 104 项真机任务。未在原论文找到机械臂持续无人 RL 实验；MoDem-V2 等相关真机工作需作为独立方法审计，不可借用其结果。[项目](https://www.tdmpc2.com/)

**开源/影响力。** UC San Diego；MIT，训练/评测、300+ checkpoint、30/80 任务离线数据下载资源公开。主库说明单任务建议 ≥8GB 显存、≥12GB RAM，80 任务数据需约 128GB RAM；这些是算法资源要求，不含机器人栈。2025 年添加 episodic 支持，默认关闭以兼容旧结果，实机接入终止状态必须设置并核验。[仓库](https://github.com/nicklashansen/tdmpc2)

**适配。** 有可靠状态/模型接口、想做规划型 RL 时保留；不能用它取代重置、成功判定、恢复和运行监控。

## 10. FLaRe（2024，ICRA 2025）

**机制。** 对大量 BC 数据预训练的 Transformer 策略在仿真中做 PPO 微调：降低更新步长、关闭熵奖励、分开 actor/critic 特征网络以减少基础策略退化；训练依赖程序化环境奖励和 reset。机构为 Ai2、UT Austin、Washington、Sony AI，项目称 CoRL OXE Workshop 2024 Best Paper Finalist，主发表为 ICRA 2025。[项目](https://robot-flare.github.io/)、[正文 §IV-C](https://arxiv.org/html/2409.16578v2)

**关键辨别。** 原论文明确真实公寓中的 Stretch RE-1 是直接部署，没有任何真实 RL 微调；抓取还使用 SPOC 式启发式模块。46 个真实试验，Fetch 的 policy proximity success 与完整抓取成功不同，后者 55.6%；PickUp 完整成功 66.7%。不能把摘要总体 80.7% 直接解释为端到端移动操作全部成功率。作者将依赖仿真列为主要局限。[论文 §V、Table III、结论](https://arxiv.org/html/2409.16578v2)

**开源。** 主分支是 `master`，有 BC/在线训练、评估、仿真数据/资产下载和 checkpoint 指引；本次抽查 `training/online/base.py` 是 AllenAct/仿真任务的基础训练配置，不是现场真机 actor/learner。许可证区分 Llama 2 部分（Llama 2 Community License）和其余代码（Apache-2.0）。[仓库](https://github.com/JiahengHu/FLaRe)、[训练基础类](https://raw.githubusercontent.com/JiahengHu/FLaRe/master/training/online/base.py)、[LICENSE](https://raw.githubusercontent.com/JiahengHu/FLaRe/master/LICENSE)

**适配。** 用户移动操作方向的有意义支线：先把导航/找物/任务级策略用仿真 RL 学好，再另接真机低层 RL。它减少真机训练劳动的方式是将训练放在仿真，不能作为在现场持续自学习的直接证据。

## 共同审查意见

1. **需要一个系统组合，而非只选算法名。** `学习器 + 初始策略/示范 + 自动奖励 + 正反任务/恢复 + 环境约束 + 发布评测` 才接近可连续运行的 harness。
2. **失败必须留日志。** 至少记录实际执行动作、策略版本、自动纠正/人工接管来源、奖励生成器、终止与截断、reset/recovery 是否成功；只留下成功轨迹会隐藏人工救援负担，也浪费失败的价值学习信息。
3. **用人工分钟/机器人小时和无值守连续时长选型。** 还需事件计数：接管、人工复位、奖励标注、不可恢复失败、物体补给、急停、相机/控制器故障。降低动作接管率不能抵消逐回合人工标奖。
4. **公开代码≠完整开源复现。** 要分算法、训练入口、真实控制、数据、权重、自动奖励/复位实现及许可；本次未下载权重、未实际接机器人，不给复现通过结论。
5. **影响力指标另表统一。** Stars/引用/下载量需要抓取日期和提供商；GitHub stars 不等于复现数，下载量未公开就记未知。机构和 venue 是证据可靠性的一个维度，不能掩盖论文未解决的人工环节。

## 补查线索（不列为本专项已完整审计候选）

- AutoSERL 局限引用 FARL、UniIntervene：更强恢复/自动接管策略，交由自主恢复专项核验。
- MoDem-V2：TD-MPC 家族真正的真机视觉控制方向，不能与 TD-MPC2 的大规模仿真结果混合。
- RL-100、ConRFT、RECAP、GR-RL、PLD：策略后训练或系统级闭环，由其它专项覆盖。
- DPPO、Policy Decorator、EXPO：算法相关，但若以原工作主要仿真证据充作真机无值守方案会偏离用户目标。

## 访问限制

Science 期刊页返回 403；OpenReview 部分页面要求验证。GitHub 无认证 API 报限额，故本分支以官方 HTML 和 raw 文件核验，未冒充 API 指标。若文件访问 404，先排查分支/文件名：FLaRe 为 master，RLPD 的许可文件为 LICENCE；AutoSERL、DayDreamer、ajwagen/dsrl 仅在所读根列表未见许可证，未做全仓许可证穷尽审计。


## 2026-09-22：RLT 开放实现补充核验

RLinf 已开放 π0.5 RLT 两阶段训练及 Franka 真机配置。因此前文 PI 原作者未完整开源的结论不变，但社区实现不应只列 Yyshadow/openpi-RLT。现成 RLinf 真机配置仍是 7D 单臂，Piper 文档只提供硬件检查。详见[较新基线选型补充](../06_较新基线与π05选型补充.md)与[工程专项核验](new_real_vla_stacks.md)。[框架原始文档](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/rlt.html)
