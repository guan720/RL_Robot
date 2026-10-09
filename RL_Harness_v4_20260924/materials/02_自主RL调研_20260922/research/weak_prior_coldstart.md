# 弱基础策略的冷启动核验：HIL-SERL、SERL、RLPD、ConRFT

核验日期：2026-09-22。用户条件：松灵 ALOHA 类双臂，已有遥操作和人工接管 DAgger；基础策略在当前任务上可能极低成功率或未经任务训练。这里没有把“降低后续人工干预”误解为“禁止初期示范”。本次仅审核原始论文、作者项目和公开代码，没有运行真机。知识库未修改。

## 判断

**若第一目标是从没有可用任务策略启动、建立一个可信的真机 RL 实验，我建议将 HIL-SERL/RLPD 系的“示范回放＋在线接管”升为第一工程基线，把 VLA 后训练作为并行分支。** 这个判断不等于它在所有任务上优于 VLA；它的优势在于不需要先获得一个成功率较高的 BC/VLA，再用残差或潜变量去修补。

更准确的入口是“少量双向示范＋可接管在线 RL”，而不是强制先用 BC/DAgger 练到某个高成功率。若现成 VLA 经少量数据适配即可产生有效任务进展，则可继续用它降低探索成本；若一直输出无关动作，不应为了保留 VLA 架构而让在线 RL 长时间在无效行为附近搜索。

## 1. HIL-SERL：直接 demo-seeded RL 的主要证据

**论文事实。** HIL-SERL 使用预训练视觉编码器、任务专用小策略和离策略 RL；通常提供 20–30 条初始示范，并在训练早期接管纠正。论文有单臂及双臂操作实证。三个代表任务的“无示范、无纠正”消融全为 0%；增到 200 条示范但去掉在线纠正，双臂仪表板装配仍为 0%。因此它支持“没有现成任务策略”，并不支持“没有任务数据和探索引导”。作者还明确指出长时程与大范围泛化未充分验证。[原论文 §3、§4.5、§6](https://arxiv.org/html/2410.21845v1)

**训练入口的独立代码核验。** `train_rlpd.py` 直接创建 SAC agent，读取 `demo_path`；learner 等在线 buffer 达到启动量后训练，示范和在线回放按 50/50 采样。没有必须先载入 BC/VLA 策略的步骤；已有 checkpoint 仅用于恢复训练。接管时把实际执行的人类动作写入 transition，接管数据同时进入示范 buffer。这是与用户现成接管工具兼容的具体证据。[训练代码](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/examples/train_rlpd.py)

**人工预算不能隐藏。** 官方教程的初期建议是每回合或隔回合进行纠正，指导策略接近任务相关区域，并使一定比例回合能得到奖励；随后再减少接管。教程还要求采集奖励分类器正负样本。该流程降低后期干预，并没有消除启动阶段的人力。[官方 walkthrough](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/docs/franka_walkthrough.md)

**双臂开源范围。** 已核实 `object_handover/config.py` 使用左右相机、本体信息、双臂夹爪 agent、`DualFrankaEnv` 和 `DualSpacemouseIntervention`；其 actor/learner 启动脚本存在。但是 walkthrough 的 Object Handover 章节仍未补完整，所以应写“有双臂代码和配置入口”，不能写“完整双臂部署教程已齐备”。[双臂配置](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/examples/experiments/object_handover/config.py)、[learner 脚本](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/examples/experiments/object_handover/run_learner.sh)

**可信度与许可。** UC Berkeley 团队；2024 预印本，作者主页确认 2025 年 8 月发表于 Science Robotics。主库 Apache-2.0；没有将项目声望等同于松灵复现保证。[作者主页](https://jianlanluo.github.io/)、[主库](https://github.com/rail-berkeley/hil-serl)、[许可证](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/LICENSE)

## 2. SERL：正反循环的直接参考，但新项目不从废弃主库开始

SERL 的物体跨箱搬运实验使用两个独立 RL agent：各有策略、Q 和奖励，正向搬过去、反向搬回来。训练由遥操作示范启动，不要求先有优秀 BC；论文表中该双向搬运任务总训练时间为 105 分钟，不能拿单策略平均时间代替完整循环成本。其证据来自受控单臂工位，不是松灵双臂或任意失败状态恢复。[论文 §4.3、表 2](https://arxiv.org/html/2401.16013v1)

旧 SERL 仓库明确标注正在废弃并指向 HIL-SERL。因此建议**取 SERL 的正反任务设计，使用 HIL-SERL 的现行学习器、接管和双臂结构**。这是待实现的组合，不应说官方已有现成“松灵双臂自主正反循环”产品。[SERL README](https://raw.githubusercontent.com/rail-berkeley/serl/main/README.md)

## 3. RLPD：算法内核，不是独立真机交付栈

RLPD 是 ICML 2023 工作，核心是把离线先验数据与在线回放一起用于离策略学习，允许少量专家数据或次优历史轨迹。它不把训练好的基础策略作为必要输入。官方示例主要是 D4RL、Adroit 和视觉基准；真机双臂控制、接管、奖励和物理恢复应采用 SERL/HIL-SERL 层来实现。[会议原始入口](https://proceedings.mlr.press/v202/ball23a.html)、[官方 README](https://raw.githubusercontent.com/ikostrikov/rlpd/main/README.md)

因此本次不把“RLPD”与“HIL-SERL”作为两个互斥候选：前者提供算法内核，后者提供用户更需要的真机训练结构。

## 4. ConRFT：弱 VLA 的有力对照，但没有核实 π0.5 即插即用

ConRFT 是中科院自动化所/国科大团队的 RSS 2025 工作。方法先用约 20–30 条任务示范进行离线 BC＋Q 联合初始化，再用在线 RL 和接管改进。原始主要实证是 Octo-small、Franka 单臂；离线初始化后的任务成功率约 20%–55%，不是直接拿零样本策略就在线训练。其同预算对照显示 VLA 预训练与离线初始化能减少在线探索成本，但这是该实验设置的结论，不能推成全部平台更优。[论文 §IV、表 II](https://arxiv.org/html/2502.05450v2)

公开仓库明确提供 Octo 的改造版、HIL-SERL 环境和 Franka 操作教程，许可证 Apache-2.0；RSS 官方 proceedings 可独立确认发表信息。当前已核验的工程入口不是 π0.5 原生训练器，也不是松灵双臂。把一致性动作头训练方法移植至 π0.5 仍需要模型、动作块与梯度路径适配，不能只更改模型名。[官方库](https://github.com/cccedric/conrft)、[walkthrough](https://raw.githubusercontent.com/cccedric/conrft/main/docs/franka_walkthrough.md)、[许可证](https://raw.githubusercontent.com/cccedric/conrft/main/LICENSE)、[RSS 官方入口](https://roboticsconference.org/2025/program/papers/19/)

## 5. 松灵双臂实现上的关键边界

以下是依据现有代码接口提出的工程判断，并非已验证硬件能力：

- **控制空间先对齐。** HIL-SERL 双臂例程绑定 Franka 环境与阻抗控制参数。松灵 ALOHA 类平台具体型号未知，不能假定具有同等笛卡尔阻抗/力矩控制能力。可移植 Gym 接口和 replay，但要独立验证关节动作或末端增量控制、两臂时序、夹爪语义和限幅。不要照抄 Franka 增益。
- **接管数据记录真实动作。** 原有 DAgger 若只保留观测与专家标签，应补齐下一观测、奖励、终止/超时、动作来源及策略版本，才能作为 RL transition。人工“给建议动作”与实际执行动作必须区分。
- **正反策略先分开。** 第一版使用两个独立 actor/critic 和方向明确的奖励/replay；这样可先确认恢复减少多少人工劳动。共享表征、统一 VLA 或反向辅助正向学习是后续变量。
- **双向冷启动不等于从第一分钟闭环。** 采集正向、正常反向和部分失败恢复示范；先在有人值守下训练。两边都很弱时，立即强行交替只会扩大失败状态分布。先完成至少一侧稳定恢复，再逐步延长自主运行，是可行性判断。
- **恢复覆盖决定是否减人。** 从成功终点返回初始区，不能处理全部正向失败；夹空、掉落、半插入、双臂僵持应按实际任务列入恢复测试。

## 6. 建议的第一轮实验

1. 选短时程、可逆、物体不易离开工作区的双向任务，先验证执行和奖励接口。
2. 每个方向用一批少量遥操作成功示范启动；20–30 条只作已有文献的起步预算参考，不作用户任务充足性的保证。
3. A 组：独立双向 HIL-SERL，直接示范 replay＋在线接管。B 组：同等人力预算的双向 BC/DAgger；C 组（有资源时）：任务适配 VLA＋在线 RL。
4. 初期各方向单独评估，只有恢复覆盖实际失败状态后才把它接进自动循环；所有辅助完成与纯自主完成分开统计。
5. 主要指标用单位人工分钟获得的自主成功数、每百次尝试的人工复位/接管次数、无接管连续循环数；同时记录机器人交互时间及初始化数据工时。

最重要的对照结论应是：**HIL-SERL 能否用更少总人力让任务起步，以及正反循环能否进一步降低后续人工复位；不要只比较训练终点的单回合成功率。**

本报告没有声称引用量/下载量新增长；机构、发表和许可依据如上。跨平台成功率与训练时长尚未知。
