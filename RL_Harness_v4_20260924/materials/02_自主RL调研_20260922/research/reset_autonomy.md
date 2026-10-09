具身自主 RL：物理复位、持续运行和人工作业审计
检索及访问日期：2026-09-22。范围：真实机械臂、移动操作；以少复位、少接管、少现场值守为主。对应结构化数据见同目录 reset_candidates.json。全部结论来自原论文、作者项目或官方实现；未做真机复现实验，未下载大型模型/数据。此专题主候选14项，其中SOAR、REVOLVE作为非RL边界参照，另补充DIAL；GEAR底层也采用目标条件监督学习，应单独看。

**先用于筛选的判断**

减少人的现场干预，主要取决于任务能否组成可循环的物理过程，以及奖励、故障检测和恢复是否可靠。SAC、DrQ、CalQL、Dreamer等优化器本身都不能保证掉到地上的物体回来、耗尽的电池恢复，或故障后继续运行。适合本次目标的配置应分为“策略更新算法”和“自主运行软件/装置”两层选择。

在本专题已审对象中，固定臂优先把MEDAL++作为可运行研究起点，借鉴MTRF的多技能互相复位；移动操作优先审ReLMM的完整任务循环，但须预算较大的旧代码迁移工作。SOAR更适合作为自主采集和任务编排层的参考，它的底层训练是GCBC监督学习。RISC与MoReFree有真实算法实现，但缺真机自主运行证据，适合加到仿真对照，不能直接排为无人值守真机的首选。以上是本专题内部排序，还需与总调研的现代RL底座候选合并。

这里不把“累计训练了40小时”解读为“连续40小时没人碰机器人”，也不把“手臂回到初始姿态”解读为“物体恢复到初始分布”。训练时低频人为恢复、评测时人工摆场、初始示范与标定、维修与换电，都应分别记账。

**真实人工作业快速对照**

| 系统 | 真机自主性证据 | 仍存在的人/装置约束 | 本次筛选用途 |
|---|---|---|---|
| Leave No Trace / ICLR2018 | 主要仿真 | 定义复位奖励与判据；hard reset仍保留 | 可恢复性门控思想 |
| R3L / ICLR2020 | 阀门/串珠过夜学习，约5–20h口径 | 受限三指手装置、成功图像、评测摆场；独立完整代码未核实 | 无演示探索与扰动策略 |
| MTRF / ICRA2021 | 手内操作约60h；插管约25h | 动捕、手写任务图/奖励、部分动作脚本；专用D’Hand+Sawyer | 多技能循环复位结构 |
| ReLMM / CoRL2021 | 办公室移动拾物累计约25–50h | 每约5h换电，可能归还卡角落物；特定初始课程有人协助 | 移动操作闭环代码参考 |
| ARIEL / 2022 | 三个真机下游任务在线适应 | 每20–30回合≈20–30min人工复位 | 离线迁移/在线适应思路 |
| MEDAL++ / CoRL2023 | 每任务30h，部分连续数小时无人看管 | 50正向+50反向demo；先30min人工reset，后平均每小时reset | 固定臂自主RL基线 |
| RoboFuME / ICRA2024 | 五任务在线2–4h | 布料每15–25回合、其他每30–35回合人工reset；目标demo/VLM标定 | CalQL+VLM奖励思路，代码待开放 |
| GEAR / CoRL2023 | TurtleBot8h、Franka推碗1h | 分别453/200比较标签；每任务10示范，感知调校 | 远程异步指导，不是无人类反馈 |
| RISC / ICLR2024 | 无真机，EARL等仿真 | goal判据、感知、故障恢复待接入 | SAC上层切换组件 |
| MoReFree / TMLR2025 | 八类仿真 | 低维状态；真机与高维视觉为未来工作 | 世界模型方案研究候选 |
| Continual Mobile Manipulation / CoRL2024 | 四类任务8–10h，项目平均80% | 围栏内预建图/固定相机；扫物任务第二台机器人复位 | 复杂移动操作体系参考 |
| OWMM / 2024 | 八个新对象约25rollout后改善 | 主要结果人工奖励；自动CLIP只测两扇门；脚本关门 | 特定门/柜对象适应 |
| SOAR / CoRL2024 | 五台WidowX数周采集30582轨迹 | workspace/任务列表/模型服务；README承认可能扶回掉落物 | 自主采集harness，非RL更新器 |
| REVOLVE / 2026-09预印本 | 四任务、复位196/200 | LLM复位代码需人验证；错标签需人审；原始demo | 前沿自动复位参考，非RL |
| DIAL / RSS2023 | 1300+真机评测、60新指令 | 8万遥操作demo，2800轨迹人工标注 | 离线数据标注参考，非RL |

数字分别来自各自实验协议，任务、示范数量、硬件和评测分母不同，表格不能用成功率直接横向排名。具体来源及未核实项见下文与JSON。

**各方案的技术机制与重要边界（DIAL为补查项，不进入主候选表）**

1. **Leave No Trace（LNT）**：在正向策略外包一层可恢复性判断，学习反向策略与复位价值；如果继续执行可能离开可恢复区间，就提前切到复位。这个设计可给现代RL增加“先确认还能回来”的门控，但价值估计不是形式化安全保证。官方明确限定可逆环境，破坏/切割等不可逆变化不能由该机制消除。公开库仅实现离散动作，连续动作相关承诺多年未完成，且已归档，故不作当前真机底座。[论文](https://arxiv.org/abs/1711.06782)、[官方库及限制](https://github.com/brain-research/LeaveNoTrace)。

2. **R3L**：组合SAC任务策略、从目标成功图像学习的VICE奖励、RND新奇性扰动策略及视觉表示。任务与扰动交替，让机器人既能完成目标，也能离开成功状态重新获得训练分布。与“反向到固定起点”相比，它偏向覆盖有用状态。真实任务的机械约束很强；原文Figure8和附录图13/15对5/17小时的任务对应关系不一致，附录另有约20小时评估，所以本报告不强行给某一任务绑定单一时长。[论文具体实验](https://arxiv.org/html/2004.12570v1)、[BAIR官方说明](https://bair.berkeley.edu/blog/2020/04/27/ingredients/)。

3. **MTRF**：把大任务拆成能互相产生初始状态的子任务，如移回中心→拾起→翻转→手内重定向，或拾起→插入→取出。每个技能分别训练SAC，人工任务图选择下一阶段。真实系统用动捕追踪对象，部分自由度由脚本控制，因此“自主”不等于无需仪器或无需任务工程。论文的100小时指硬件可连续不损坏，2000小时是累计使用，不能当成单次无人学习证据。适合可逆、多技能循环任务；D’Hand/Sawyer适配和旧代码维护成本高。[论文](https://arxiv.org/html/2104.11203v1)、[官方代码](https://github.com/facebookresearch/MTRF)。

4. **ReLMM**：移动底盘用SAC找物，抓取由带不确定性的抓取模型评估；抓到物体后，训练时移动并放下，使抓取和导航能继续学习。抓取成功还能提供导航奖励，无需每回合人重新摆物。实际每约5小时换电，且可能顺手处理墙边/角落的物体。论文给了两种启动课程，不能把stationary课程约5%的人工帮助漏掉，也不能把它错误套到完全自主课程。StatCurr报告四环境，AutoCurr仅两环境；每环境只训练一次、评测三次，不能借StatCurr结果扩大完全自主课程的验证范围。环境主要是平地办公室、轻小可抓物，未解决开放世界的完整故障恢复。[论文第4–6节](https://proceedings.mlr.press/v164/sun22a/sun22a.pdf)、[官方库](https://github.com/charlesjsun/ReLMM)。

5. **ARIEL**：用AWAC先吸收离线多任务数据，再通过任务表示与在线经验适应新任务，配合正/反向循环减少复位。这篇更值得看“如何从已有多任务数据启动在线RL”。真机仍每20–30分钟人工恢复；部分样本效率实验采用每回合复位，不应与少复位结果混为一谈。目标示范是可选设置，实验需要检测器给稀疏奖励；官方完整实现未核实。[论文实验设置](https://openreview.net/pdf?id=_xln96AicXY)、[项目](https://sites.google.com/view/ariel-berkeley)。

6. **MEDAL++**：正向策略完成任务，反向策略把状态拉回专家数据覆盖区域；DrQ-v2配合演示过采样、BC约束、增强的critic训练，VICE分类器把成功图像变成奖励。它是真实像素输入机械臂自主RL中较清楚的可审实现。示范和每小时人工恢复仍是明确成本；30小时/任务、最优checkpoint评测，不能理解成30小时无人值守。四任务包括cube、cloth hanging、bowl cover、peg；任务差异很大。仿真实验使用的真值奖励与reset频率也不能套到真机。[CoRL论文](https://proceedings.mlr.press/v229/sharma23b/sharma23b.pdf)、[官方库](https://github.com/rehaanahmad2013/self-improving-robots)。

7. **RoboFuME**：语言条件CalQL用相关BridgeV2数据和少量目标示范启动，MiniGPT-4经成功/失败数据校准后给奖励，正/反向任务自动交替。这减少了逐条人工在线奖励和回合复位，但不是无示范/无物理恢复：布料15–25回合、其他30–35回合就需人介入。成功演示约30分钟和失败演示约10分钟是项目给出的前期数据采集量，不包含全部装置开发、失败处理和评测劳动。官方Code仍Coming Soon。[最终论文](https://yjy0625.github.io/publications/robofume_icra2024.pdf)、[项目](https://robofume.github.io/)。

8. **GEAR**：人远程回答“两个状态哪个更接近目标”，学习距离模型；根据状态密度筛掉不易达到的目标，配合目标条件监督学习/事后重标。它把现场操作移成异步反馈，适合“可有人远程指导，不能现场守着”的场景。453和200是反馈条数，40和22是参与人数，不能按这些数推导人类总分钟。状态估计器调校及准静态可达性近似仍是局限，低层不是常见actor-critic。公开README的示例多为use_oracle仿真，完整真机服务链尚未证实。[论文](https://arxiv.org/html/2310.20608v1)、[官方代码README](https://raw.githubusercontent.com/guided-exploration-autonomous-rl/gear-code/main/README.md)。

9. **RISC**：针对reset-free下长期停留容易区域或过早终止的问题，改进目标切换和bootstrap，使用策略能力估计决定是否提前换目标。代码有SAC/DQN及切换器，可作为现有训练引擎的对照模块。作者提醒success critic的数值不能直接视为校准后的成功概率；只有仿真实验，没有真实安全、奖励感知和维修系统。[论文](https://arxiv.org/html/2405.01684v1)、[代码](https://github.com/chandar-lab/RISC)。

10. **MoReFree**：基于PEG/DreamerV2，用世界模型做目标导向探索，在初始状态目标、评测目标及新奇目标间分配探索，并在想象学习中加大任务相关状态比例。八个仿真环境说明机制的样本效率价值，未说明能在真机长时运行。SawyerDoor暴露了“学动力学比学策略难”的失败情形；官方README的宣传范围应服从论文结果，不能写所有任务无例外提升。作者机构为Leiden和UPenn GRASP。[TMLR版本论文](https://arxiv.org/html/2408.09807v3)、[官方代码](https://github.com/yangzhao-666/MoReFree)。

11. **Continuously Improving Mobile Manipulation**：在现有感知、规划和行为先验上做自主反复练习，比较顺序、分离、残差等方式把先验与DrQ/RLPD系RL结合。论文的真机基础设施包括6×5m有围栏、预建图空间及固定外部相机；扫物任务用第二台机器人做脚本复位。其提升支持“有用的自主任务循环+合适先验”的组合，不能归因于RL优化器单独解决了自学习。完整代码与人类维护分钟未核实。[论文](https://arxiv.org/html/2409.20568v1)、[项目](https://continual-mobile-manip.github.io/)。

12. **OWMM**：学习抓握、旋转/解锁、开门等primitive的参数化序列，BC后通过REINFORCE加BC约束做新对象适应；自动回初始位置并脚本关门。主结果从50%到95%采用人给奖励，CLIP自动奖励另在两扇门得到80%，同设置人工真值为90%。因此主结果不能用来证明VLM无人工奖励已达到95%。这是受约束primitive序列优化，并非任意门柜上的通用高频端到端策略。[论文III-B/IV/V](https://arxiv.org/html/2401.14403v2)、[项目](https://open-world-mobilemanip.github.io/)。

13. **SOAR**：CogVLM在事先允许的任务集合中挑可行任务，SuSIE生成图像子目标，GCBC执行；循环数据用hindsight重标改善GCBC。UCB任务平衡不意味着底层是RL，政策更新应归为监督学习。官方发布了采集、模型服务、训练、数据与checkpoint下载指引；大规模经验30582轨迹可作离线RL素材，但原论文没有对它做在线critic学习。README承认可能周期性扶回掉落物；代码有物体缺失检测和电机重启上限，意味着停机/人工处置仍可能发生。[论文](https://arxiv.org/html/2407.20635v2)、[采集部署说明](https://raw.githubusercontent.com/rail-berkeley/soar/main/data_collection/README.md)、[训练说明](https://raw.githubusercontent.com/rail-berkeley/soar/main/model_training/README.md)。

14. **REVOLVE**：2026年9月新预印本。自动复位模块通过点云聚类、IK和确定性控制恢复场景；代码由LLM提出再经人验证。策略从成功/纠正数据做监督更新，VLM错判通过人工验证的记忆检索纠正，没有得到RL训练证据。四任务复位196/200值得关注，但100%无人维护和完整开源未获证实；所报人工节约比例不能替代包括设置、审核、故障在内的全生命周期成本。[原文方法与实验](https://arxiv.org/html/2609.14633v2)、[版本日期](https://arxiv.org/abs/2609.14633)。

补查项. **DIAL**：这里特指RSS2023的Data-driven Instruction Augmentation for Language-conditioned control，不是2026同名VLA/驾驶方法。它微调CLIP重标离线专家轨迹，再做BC，减少语言标注，未减少遥操作数据来源或真机物理复位。项目与Google作者页均归为模仿学习；并非持续在线RL。[RSS记录](https://roboticsproceedings.org/rss19/p029.html)、[官方项目](https://instructionaugmentation.github.io/)、[Google论文页](https://research.google/pubs/robotic-skill-acquisition-via-instruction-augmentation-with-vision-language-models/)。

**SOAR对RoboFuME/DIAL的负面证据，应该怎样使用**

SOAR Table2中，两项任务SOAR为0.8/0.7、两个基线为0/0。作者明确把原方法的专家目标数据替换成SOAR自主采集的次优数据，且调整策略架构/预训练数据到自己的实验条件。这能支持“这些改造版本在该自主数据设置下不适用”，不能写“独立复现RoboFuME原论文失败，原方法没有效用”。AppendixF对语言Q函数与CLIP标签质量的解释属于作者假设，尚不是普遍因果结论。[SOAR最终CoRL论文Table2及AppendixF](https://raw.githubusercontent.com/mlresearch/v270/main/assets/zhou25b/zhou25b.pdf)。

**开源审核：读到了什么，未验证什么**

| 项目 | 本轮实际触及的实现 | 许可证/状态 | 主要剩余缺口 |
|---|---|---|---|
| LNT | [lnt.py](https://raw.githubusercontent.com/brain-research/LeaveNoTrace/master/lnt.py) | Apache-2.0，归档 | 连续动作完整实现缺失 |
| MTRF | [phased_sac.py](https://raw.githubusercontent.com/facebookresearch/MTRF/main/MTRF/algorithms/softlearning/algorithms/phased_sac.py)：每goal独立policy/Q/replay/sampler，set_goal接口 | Apache-2.0，2023归档 | 旧TF、硬件/子模块依赖及可迁移权重 |
| ReLMM | master/real_robot分支与目录确认；[real_robot LICENSE](https://raw.githubusercontent.com/charlesjsun/ReLMM/real_robot/LICENSE) | master与real_robot根LICENSE均MIT，Softlearning署名 | 分支各具体机器人模块尚未逐个精读；不能据目录认定一键复现 |
| MEDAL++ | [medal_franka.py](https://raw.githubusercontent.com/rehaanahmad2013/self-improving-robots/main/franka/medal_franka.py)：manual reset等待stdin分支 | 主库Apache-2.0，子模块另核 | 每平台任务demo、驱动及现场复位 |
| GEAR | [gear/algo/gear.py](https://raw.githubusercontent.com/guided-exploration-autonomous-rl/gear-code/main/gear/algo/gear.py)，2881行算法实现可读 | 许可证未成功确认 | 真机部署/远程标注服务发布完整性 |
| RISC | [gc_rf_agent.py](https://github.com/chandar-lab/RISC/blob/main/risc/agents/gc_rf_agent.py)、SAC、reset_free_envs、runner；解压包内存检查 | MIT | 无真机控制系统 |
| MoReFree | [goal_picker_wrapper.py](https://raw.githubusercontent.com/yangzhao-666/MoReFree/main/resetfree/goal_picker_wrapper.py)、resetfree/env.py分段逻辑 | MIT | 无高维真机实验；环境done不一定是物理复位 |
| SOAR | [robot/main.py](https://raw.githubusercontent.com/rail-berkeley/soar/main/data_collection/orchestrator/robot/main.py)、[gc_bc.py](https://raw.githubusercontent.com/rail-berkeley/soar/main/model_training/jaxrl_m/agents/continuous/gc_bc.py) | 主库MIT，模型/数据另核 | 需多服务部署、校准及偶发人工处置；大文件未下载验证 |
| RoboFuME | 官方Code仍Coming Soon | 完整方法许可未知 | 不能借MEDAL++/CalQL开源状态替代 |
| R3L/ARIEL/Continual Mobile/OWMM/REVOLVE/DIAL | 论文+项目/作者记录 | 完整官方实现未核实 | 未找到不是断言不存在；不标“开源可复现” |

SOAR的robot/main.py会排除缺失物体所需任务，对电机故障最多尝试重启10次再exit(1)；这是明确的工程边界。其每trajectory回初始关节位置只是机械臂位姿复原。MEDAL++的manual-reset输入分支也直观说明：“代码含reset”不能证明“环境由机器人自动reset”。

影响力元数据已经在JSON分开记录机构、venue和论文标识。star、fork、引用、下载量需由总表用统一日期和接口抓取。较高引用或机构声誉不能抵消缺代码、改协议比较、缺人类工时统计这些复现风险。此次GitHub API遇共享IP限流；不能用0填不可访问数据，也不能把模型仓库downloads当作本方法实际用户数。

**建议的试验筛选方式**

可先保留三个组合，按用户资源和任务可逆性筛：

- 固定机械臂：现代像素RL底座 + MEDAL++式正反向学习 + MTRF式多技能图；单独检查奖励误判与物体越界。若任务本身不可逆，预算自动供料/收料等物理装置，不应只靠学习reset。
- 移动操作：适配ReLMM式抓取—放置—导航循环，先解决充电/换电、角落物体与定位丢失，再比较RL更新方法；复杂任务可参考Continual Mobile的先验组合，但记入围栏、相机和第二台机器人的成本。
- VLA/通用技能：复用SOAR的任务选择、采集、异常检测、数据管理，把策略更新器作为可替换组件；先以GCBC/SFT做真实对照，再加RL，证明收益确实来自奖励优化。

同预算至少同时固定机器人小时、初始示范分钟、目标物体/场景数、奖励标签预算、算力预算；报告成功率时保留全部checkpoint和评测协议，避免只挑最好模型。另记录：
自主动作总数、最长连续无介入时长、每小时介入次数、每1000动作人类主动分钟、自动复位成功率与耗时、耗材/换电/维修时间、任务覆盖率、学习前后独立测试和安全停机次数。在线示范、奖励标注、故障接管、环境复位四类介入分开，否则“自主性”提升无法定位。

优先试验应主动加入几类真实失败：物体跌落/移出工作区、目标检测错误、抓取失败后不可达、电机保护中断、底盘定位漂移。这不是额外算法排行榜，而是判断方案能否减少用户最在意的现场值守。当前论文多数缺完整全生命周期人类分钟账，因此没有足够证据认定任何单一系统可直接达成开放环境长期零人干预。

**检索、排除与访问状态**

检索按“论文名+reset/autonomous/human intervention/code”组合，以及“reset-free RL real world manipulation”“autonomous RL mobile manipulation continuous learning”“SOAR DIAL RoboFuME baseline”等补充关键词展开。优先追到arXiv版本正文、CoRL/PMLR/RSS原始会议文件、作者项目页、GitHub实际文件；追读实验附录里的频率/时长，不用二手摘要的autonomous字样定级。

已排除同名干扰：ARIEL的ci-group演化机器人项目、材料科学ReLMM、非本领域R3L以及2026多种DIAL；没有以同名开源库充作算法代码。R3L独立旧链接404但MTRF含r3l目录，保留这种区别。ARIEL、OWMM等未找到官方code入口，标“未核实”，不是证明世界上不存在实现。

网页工具对部分GitHub/Google Sites/PDF返回内部错误时，用raw官方链接、出版方镜像或curl补查；GitHub API共享IP限流，git代理127.0.0.1:7890不可用；部分codeload返回非zip，未据失败输出作负面开源定论。RISC源码zip只在内存解析，没有把大仓库、模型或视频落到根目录。上述网络问题属于本次审计可访问性限制，不属于论文可复现性实验结果。

后续需补齐的核查项：ReLMM真实分支具体模块逐文件审计；GEAR许可证和真机服务链；无代码项目是否后续新发布；各方法一致口径影响力数据；在用户选定机器人上的复位成功率/人类分钟实测。此处最终候选分组是可审阅的研究判断，不是已经完成硬件验证的采购结论。
