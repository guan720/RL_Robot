# R08 独立证据与联合选型审查

**结论：PASS。** 完成 22 个具体问题的有界核查；必要修订 0 项。此结论仅表示下述冻结文稿的证据表述、竞争条件和选型边界通过本次静态审查，不表示系统已实现、论文已复现或真机训练有效。

审查日期：2026-09-23。先只读加载科学家的 START_HERE、ROLE、status、INDEX 及本地 embodied-research-scientist 技能；其更新状态仍为暂停／审查中，不作为本轮通过依据。科学输入限于 R08/input 的 9 份 Markdown；未读同轮其他审查员报告，也未读输入链接到的 R05/R07 补核报告或借用历史 PASS。补核链接只用于定位，关键判断直接打开原论文、固定源码或官方文档。未安装候选、运行训练、执行真机或修改输入／知识库。

## 1. 要点枚举与范围

核查要点：① RAPolicy 官方资产及缺件；② 单任务弱起点与共享五任务的数据、评测及人工条件；③ 原生 actor、Q/V、在线／离线 latent 的区别；④ hold、接管、吸收尾部和折扣的物理含义；⑤ RT-EXPO 的参照、两种延迟、额外输入和人工成本；⑥ OpenETA／RPent 的观察与取消接口；⑦ 学习器、平台、骨架分别竞争的可推翻门槛；⑧ 通用性、开源和影响力能支持到哪一层。

冻结文件定位简称如下；本次审查其与上述要点相关的段落，不宣称逐篇复核候选地图中的所有方法。

| 简称 | R08/input 内文件 |
|---|---|
| 入 | [README](input/03_RL_Harness自主学习系统_20260922/README.md) |
| 技 | [01 技术方案](input/03_RL_Harness自主学习系统_20260922/01_RL_Harness真机自主学习技术方案.md) |
| 接 | [02 接口契约](input/03_RL_Harness自主学习系统_20260922/02_接口契约与开发验收.md) |
| 时 | [06 异步附录](input/03_RL_Harness自主学习系统_20260922/06_异步动作时间轴与学习目标.md) |
| 总 | [总调研报告](input/04_RL与Harness扩展调研_20260923/01_RL与Harness开源基线深度调研报告.md) |
| V | [VLA 专项](input/04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md) |
| 自 | [自主学习专项](input/04_RL与Harness扩展调研_20260923/research/02_自主学习与复位扩展调研.md) |
| H | [Harness 专项](input/04_RL与Harness扩展调研_20260923/research/03_Harness扩展调研.md) |
| 平 | [训练平台专项](input/04_RL与Harness扩展调研_20260923/research/04_训练平台与开源生态核查.md) |

独立学习首先打开 RAPolicy v1 的方法与实验、RT-EXPO v1 的实验与附录，再追具体代码。源码主锚点为 RAPolicy `ef4b1044f0cc78c0f6143180a2d78ae267ab03ea`、RT-EXPO `803381fc3b4c91a0c47904f1b688fc5e35904f50`、OpenETA `7d4a0a1522ba8ebbd362bde880bad81d2a98f15e`、RPent `6ee706935d28646828f70372ef0099c769cfe0c2`。下表逐项写真实读到的内容；“通过”指文稿已正确陈述／设门槛。

## 2. 逐问核查

| 问题 | 冻结文稿定位 | 本轮直接证据与判断 |
|---|---|---|
| Q01 RAPolicy 是否真的有作者训练实现，而非仅项目网页？资产缺口是否保留？ | V §11.2，L341–345；总 §4.3；平 §13 | **通过。** [固定 README](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/README.md) 的 layout、安装、launcher 与 release validation 段确有 RLinf 派生实现，明确不附实验 checkpoint／示范数据，并说发布检查不是重跑论文。文稿没有把代码公开升级为完整复现资产。 |
| Q02 “弱起点含零成功”是否误写成无示范可自主启动？ | V L337–339；总 L102–104；自 §7 | **通过。** [RAPolicy 原文 Table I、§IV-A.3](https://arxiv.org/html/2609.22888v1) 给出十示范 SFT 后四项初始 5%、15%、0%、10%，每项最终评测 20 次；不是零示范。文稿同时保留探索／纠正覆盖条件、人工接管及八张3090的作者条件。 |
| Q03 共享五任务能否直接证明十示范共享 A↔B 无人复位？ | V L337、367–369；技 §10.4 | **通过。** [原文 §IV-A.1/3、Table II](https://arxiv.org/html/2609.22888v1) 是同场景一个共享语言策略，150 条示范并初始化 replay，每任务评测10次；总计26/50→44/50。文稿区分单任务与联合数据条件，也没有将其等同本项目正常反向 RL 和自主复位。 |
| Q04 类名含 SAC 是否误判为默认最大熵 SAC，或 Q 直接反传原生头？ | V §11.1/3；技 L293；接 T39 | **通过。** [配置](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml) 选 `actor_objective: v2_awac`、关闭 entropy backup；[actor loss 选择器](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/awac_actor_loss.py) 默认 likelihood，flow-matching 是独立消融。文稿未混入06的 actor-Q 梯度公式。 |
| Q05 异步采集／学习是否被当成已解决连续 C/E/D？ | V L351；技 L270、291–293；时 L339 | **通过。** 上述[固定配置](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml) 同时设 fixed chunk、hold_during_inference；[RealWorldEnv.chunk_step](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/envs/realworld/realworld_env.py) 在最后控制步走 hold_after。多任务配置继承该设置。文稿明确 hold 对照只能先检验学习可达性。 |
| Q06 人工接管后还用旧提案动作吗？原 latent 是否被换成虚构专家噪声？ | V L353；技 L295；接 T39 | **通过。** [worker.ingest_rollout_trajectories](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py) 调用模型空间对齐并保留 rollout latent；[merge_hil_actions_in_model_space](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py) 用累积 intervention mask 替换接管后的旧尾段。文稿仍要求 Harness 新反馈按实际决策时刻分流。 |
| Q07 无原始 latent 的离线专家轨迹是否不能学，或可冒称精确边缘密度？ | V L356；技 L295；接 T39 | **通过。** [awac_offline.py](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py) 的 `resample_offline_latent` 只重采 offline 行，materialize 保存零占位及标志；函数说明明确不是反演专家噪声／边缘 flow 密度。[worker 的 likelihood 调用](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py) 实际调用此函数。文稿也将 actor 监督资格与真实 TD 资格分开。 |
| Q08 终局尾部填充是否被记成实际执行，或被误称原版完全丢弃尾部？ | V L354；时 L227、339 | **通过。** [RealWorldEnv](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/envs/realworld/realworld_env.py) 终局分支只追加重复观测、零奖励与 hold 数组，控制 duration/period 填 NaN 后 break；fixed chunk 的有效标志仍为真。文稿正确将其称为吸收态张量约定，要求另存物理有效区间。 |
| Q09 上游 done／γ 能否直接复制成本项目截断与逐微步目标？ | V L352、363；技 L293；时 §5.3 | **通过。** [forward_awac_critic](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py) 合并 termination/truncation，并以 target V 备份；[prepare_chunk_transition](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py) 区分 chunk-aware 与整块 γ。文稿明确需要重定回报、终止与队列协议，未归咎上游自己的 MDP。 |
| Q10 最快成功池是否会淘汰全部旧纠正？来源和版本是否已经完备？ | V L357–359；技 L295–297 | **通过。** [replay.add_realworld_demo_episode](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/replay_buffer.py) 淘汰集合会减去 `_protected_intervention_ids`；[worker](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py) 又确实清除 `trajectory.versions`。文稿既承认上游保护接管，也要求另保种子示范、双向分层和完整事实版本。 |
| Q11 算法 fork 能否与训练平台混排，因同名 import 就当上游兼容？ | 平 §13；总 §7/9；技 L297 | **通过。** [RAPolicy README](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/README.md) 说明保留 `rlinf` namespace 是兼容底层设施；[公开 launcher](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/run_rapolicy.sh) 转入专门 AWAC 配置。文稿单锁 fork／依赖，不把它写成 RLinf HEAD 已合并功能。 |
| Q12 RT-EXPO 的42%参照是否其实是 RTC-SFT？ | 总 L77；V L111 | **通过。** [原文 Table I](https://arxiv.org/html/2609.18207v1) 分别列普通 SFT 12.5/30、RTC-SFT 18/30、RT-EXPO 29/30的四任务均值。文稿保留分母与60%的 RTC 参照，没有制造42%的 RTC 起点。 |
| Q13 延迟是否把自然硬件耗时、sleep、旧帧预算相加或统一四任务？ | 总 L81；V §4.4.1；技 L277 | **通过。** [RT-EXPO §VII-E.3](https://arxiv.org/html/2609.18207v1) 分 wall-clock 与 chunk-delay；前三项可额外100ms，Dynamic Picking 不额外 sleep；chunk-delay 后者d=3、其他d=5。文稿没有把离散预算当同一自然端到端时延，并要求分别测量。 |
| Q14 同相机是否被误当同信息，从而把额外检测状态增益都归给算法？ | V L136–138；技 L275；接 T34 | **通过。** [原文 §VII-D.3–4](https://arxiv.org/html/2609.18207v1) 的检测器派生状态进入 Q/filter/edit；base state 不变，Ball Balancing 使用三帧外部视图。文稿按模块列来源、历史、可用时刻及成本，要求统一信息或输入消融。 |
| Q15 “十分钟、无人工干预”是否掩盖 SFT、复位和评测劳动？ | V L113–115；总 L77；技 §13 | **通过。** [原文 §V-C、§VI](https://arxiv.org/html/2609.18207v1) 限的是在线机器人数据，明确人工复位和人工独立验成功。文稿将前期示范、训练／复位／评测及值守分别计成本，不等同无人总墙钟十分钟。 |
| Q16 RT-EXPO 更新 base 和编辑器，能否被当作永久冻结残差或直接原生 Q 更新？ | V §4.3/4.4；时 §11 | **通过。** [固定 realtime_expo_ft.py](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py) 的 `update_edit_actor` 用 Q／entropy，`update_actor` 另走 RTC-prefix train step。文稿区分两路更新，保留行为覆盖诊断和独立 replay/target，不只改一个 mask。 |
| Q17 OpenETA 的新观测义务、线程取消能否充当持续观察及实体停机？ | H §13.1；接 L394 | **通过。** [固定 planner](https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/planner.py) 在 backend.decide 前检查 host obligation，并可返回 observe；[registry](https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py) 启 daemon handler thread，取消时抛 abandoned 放弃结果。文稿不将逐工具观察升级为长动作期间连续观察，也不以关闭会话代替 stop_ack。 |
| Q18 RPent 的旧审计边界是否被新 HEAD 偷换？新版本真的已消除观察锁吗？ | H L243；总 L141；接 L54–58 | **通过。** 本轮直接读新 SHA 的 [api_loop](https://github.com/RLinf/RPent/blob/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/planner/api_loop.py) 仍注册 `sequential=True`；[Toolkit.execute_tool](https://github.com/RLinf/RPent/blob/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/tools/toolkit.py) 先检查 active operation，随后才区别 readonly 记录。独立观察改造仍有依据。文稿没有声称完整新版本已审计或 RPC cancel 已完成设备停止。 |
| Q19 是否对竞争骨架双重标准：OpenETA缺RL就排除，RPent却可外接？ | 总 L149、213–221；技 L273；接 T38 | **通过。** 文稿明确 OpenETA 与 RPent 同门槛；同 GPT、工具、模拟本体、故障记录比较，并允许低改造成本候选胜出。上两问的原始代码已显示两者都有需补的执行边界，支持条件性竞争，不能支持预先排定赢家。Strands／DimOS／OpenRAL 在这里是分层候选，不被宣称已跑通。 |
| Q20 原生对照是否公平、选型是否可推翻，而非必须先完成完整头长训练？ | 总 §9.2；技 §10.2/10.4；平 §4 | **通过。** [verl-vla 官方 TD3＋BC 配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html) 是更新 π₀.₅ 原生策略的 8-GPU、32 仿真环境参考，32/50→40/50，非本工位证明。文稿将其作补充，RAPolicy 优先预检；允许原生路线少改造过门槛即采用，比较独立双向能力、合法数据密度和总成本，不同时完整移植全部候选。 |
| Q21 组件复用是否意味着把数个仓库的主循环、reset和buffer叠加？通用性是否仅靠AgileX排名？ | 总 §8/9.1；技 L262、271；接 T31、T37–38；入 L9 | **通过。** 文稿逐项要求唯一 Gateway、工具只提交意图、独立事实日志；用两个不同动作 schema 的模拟 adapter 核软件边界，明确不等于跨机器人实测。此为可检查设计约束，不是来源性能主张。平台、learner、认知骨架分别验收，品牌适配只计部署工时。 |
| Q22 机构、stars、开放性或强Harness是否替代复现／policy学习证据？ | 总 §3、7.2；H §11/12；平 §7；自 §7/8；入 L3、29；技 §13 | **通过。** 文稿把网页量级快照、模型下载、论文结果和运行验证分开；无引用／复现统计写未核验。RAPolicy README 自述发布校验非重跑亦支持这一界限。验收分别测无动作辅助 policy、辅助系统、人工控制／复位／标奖及值守成本；没有把演示或自动审查写成独立真机复现。 |

## 3. 必要缺陷、待实测与可选优化

**必要缺陷：无。** 当前证据支持“优先预检 RAPolicy、保留 RT-EXPO 实时路线、保留完整头队列参考、骨架可替换”的条件结论，不能支持其中任一方案已经胜出。

**文稿已列、尚未完成的实测门槛：**

1. RAPolicy 的连续队列改造尚未定义完并实现：actor/Q/V 条件、有效区间、接管、噪声资格、回报和发布规则须按 T39 分别核验；原生 hold 的成功不算连续要求通过。
2. 原生头／完整头／编辑路线用同一双向示范、信息条件、交互及纠正预算比较；测关闭辅助后的双向结果、合法 TD 密度和总人力／算力，不能凭论文间成功率选冠军。
3. RPent／OpenETA 等通过 T38 先核长动作下持续观察、实体停止、事实日志，再比较替换成本；骨架没有在线 RL 本身不是独立淘汰理由。
4. P0 仍须锁依赖、模型、驱动及入口；GPU 配置、自然延迟、动作覆盖与适配成本没有本项目运行结果。
5. 评分／纠正质量、共享负迁移、恢复和人工依赖须保留独立评估；文稿审查不能代替这些结论。

**可选优化：1 项，非阻塞。** V 专项 §2（L25–33）的早期摘要仍主要介绍“完整头与 RT-EXPO 两条比较”，新增 RAPolicy 在 §8 和 §11 已经正确升级；可把 §2 更新为当前三条主要学习路线并指向 §11，减少只读摘要时的版本落差。总报告、技术方案和 README 已经采用新顺序，因此不构成必要修订。

访问边界：本轮成功打开两篇原论文、上述固定代码及 verl-vla 官方配方；GitHub tree 与两个试探性 OpenETA host 路径返回访问错误，已改用实际 planner/registry 原文；Strands RL 文档本轮访问失败，因此没有将其RL实现细节记成本轮新核实结果。未以访问失败推断项目无代码，未扩展新候选以凑数。

审查输出只写本文件。**问题数：22；必要修订：0；可选优化：1；最终判定：PASS（限定本次静态证据与联合选型范围）。**
