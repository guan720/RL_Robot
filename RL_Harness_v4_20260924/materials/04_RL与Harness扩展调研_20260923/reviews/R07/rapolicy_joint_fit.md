# RAPolicy 与本项目的联合适配独立评估

2026-09-23｜审查者：`/root/rapolicy_joint_fit`｜定向补充研究；不是正式整轮通过报告。未安装、运行或复现实验。

## 1. 判断

**建议将 RAPolicy 提升为首要原生 VLA 动作头挑战者，优先于当前仅有仿真条件对应证据的 verl-vla π₀.₅ TD3＋BC；不据此宣布它胜过本项目完整头方案，也不取代 Real-Time EXPO-FT 的实时执行对照。**

这个排序依据的是条件匹配：少量示范后的弱初始真机策略、原生动作头更新、接管回放、共享语言条件多任务以及可读的 RLinf 实现同时出现。它没有证明正反自动循环、GPT Harness 纠正或 C/E/D 连续执行。这些缺口恰好位于本项目的核心，必须另行解决。

“原生头有现成弱起点真机证据”比“重学完整头自由度大”更值得优先做小预算验证；但重学头能否更简单地处理本项目时间协议、标签粒度和算力限制，仍是独立工程问题。最终选择应来自同任务、同信息、同纠正预算的验证，不预设任何路线获胜。AgileX 品牌适配不影响此判断。

## 2. 独立阅读范围与证据

本次先独立阅读论文方法与实验，再读官方关键代码；没有读取其他专项代理尚未完成的结论。对照了技术文档 01、02、06。代码 URL 固定到本次读到的提交短前缀 `ef4b104`，完整 SHA 由总资产审计记录进一步锁定；以下只描述实际读到的函数，未声称全库审计。

| 来源 | 实际核对内容 |
|---|---|
| [论文 v1](https://arxiv.org/html/2609.22888v1) | §III 回放、expectile V、一步 flow 条件似然；§IV 数据、干预、算力与对照 |
| [官方 README](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/README.md) | RLinf fork、启动入口、复现依赖；不提供实验 SFT 权重或示范数据 |
| [actor worker](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/rlinf/workers/actor/fsdp_sac_policy_worker.py) | `ingest_rollout_trajectories`、`forward_awac_critic`、`_v2_replay_likelihood_forward`、`forward_v2_awac_actor` |
| [数学工具](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/rlinf/algorithms/sac.py) | `prepare_chunk_transition`、`merge_hil_actions_in_model_space`、expectile 与指数优势权重 |
| [latent 契约](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/rlinf/algorithms/awac_replay.py) | `last_step_state`／`initial_latent`、步数限制与恢复训练校验 |
| [离线数据](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/rlinf/data/awac_offline.py) | `is_offline_demo`、离线 latent 重采样、语言任务恢复、特征持久化 |
| [异步 worker](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/rlinf/workers/actor/async_fsdp_sac_policy_worker.py) | 接收线程、数据就绪、critic warmup、更新组 |
| [actor 消融](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/rlinf/algorithms/awac_actor_loss.py) | likelihood 与另行 flow-matching 配方；不是默认目标可随意互换 |
| [启动映射](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/examples/embodiment/run_realworld_ablation.sh) | 真机任务与共享多任务的配置入口 |

直接 API 目录查询遭遇 403；一次猜测的 `openpi_policy.py` 路径返回 404，不作为缺代码证据。本次不依赖该猜测路径。

## 3. 作者展示了什么，尚未展示什么

作者报告单任务先用 10 条示范 SFT；其中堆叠初始为 0/20，在线后 14/20。共享五任务使用每任务 30 条示范，汇总从 26/50 到 44/50；实验有人工接管，分布式设备为 8 张 RTX 3090。单任务在线不以离线数据初始化 buffer，共享多任务则使用离线初始化。它支持“弱初始＋少量示范＋纠正的原生 VLA 在线改进”这一可行性论据，不支持“无纠正的零成功策略必然自启动”。[论文实验](https://arxiv.org/html/2609.22888v1)

机构与新近发表可以增加关注优先级，但当前仍以作者结果为证据；未核实独立复现、可靠引用量或部署规模。论文比较的是其中定义的 EXPO-FT，不应写成已战胜新 Real-Time EXPO-FT。共享五任务也不是自动 A↔B 复位循环。小样本最终评估与部分任务不足满分，不能外推任意任务可靠性。

官方公开代码是实质训练实现，而非只有项目网页。README 对权重、数据、驱动配置和发布检查范围给出明确限制；因此评级应是“代码可审查、复现资产不齐、尚待实测”，不能说开箱复现完成。[发布说明](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/README.md)

## 4. 与本项目的兼容性：逐项判断

| 要点 | 已有事实／原理 | 本项目要求及判断 |
|---|---|---|
| 动作头与弱起点 | 一步 flow 直接更新原生动作映射；不是固定 VLA 周围的小残差 | 对弱初始有吸引力；无需先把模型限定为很强的 base |
| 共享双向 θ | 已有共享语言条件多任务；离线工具恢复准确 task prompt | A→B/B→A 可复用同一模型结构；仍须目标进入 actor、Q、V、奖励及回放，方向分层采样、同 checkpoint 双向发布 |
| BC＋RL | 价值学习加优势加权动作回归；不是纯成功轨迹 SFT，也不是本项目确定性 `−Q＋BC` | 同属可信行为监督与 RL 结合，具体优化目标不同；不得改名后静默共享 target |
| latent 对齐 | 在线保留本次生成所用 latent；一步模式下该随机变量不是随参数变化的中间 flow 状态 | request 绑定输入、权重与随机性；禁止重采在线 latent 冒充原行为配对 |
| 无 latent 示范 | 官方离线函数为有真实后果的离线示范每次重采高斯，并明确不是重建专家 latent 或边缘密度 | 原理上可处理无原生 latent 数据；不等于未执行建议有了 TD 后果 |
| 接管回放 | 上游把首次接管及后续尾部映射进 model action | 对同信息、同协议完整纠正可参考；晚观察的反馈尾部不能直接当作本项目起点 U |
| 动作切片 | 上游 fixed chunk 与有效 mask／折扣有自己的约定 | 本项目 C/E/D 的 E 不一定是前缀；必须记录绝对帧、start index、queue 与 proposal 关系 |
| 连续执行 | 已证明采集与训练并发；这不足以证明推理期间执行旧 C、新 E 替换 D | 保持原协议先作对照；移植到 06 的队列协议必须独立推导与验收 |
| 终止与截断 | 原 worker 合并 `terminations OR truncations` 清 bootstrap | 不能将 Harness 抢占、超时和云失联都当吸收终止；必须重写资格判定 |
| 权重与缓存 | learner 有更新组；冻结 VLM 特征用于回放 | 原 ingest 清除部分 `versions`；本项目保留外部不可变事实、request 权重 ID、normalizer 与 feature 版本，边界发布 |

代码层事实主要来自上述固定提交的 worker、`sac.py`、`awac_replay.py` 与 `awac_offline.py`；右列是本次独立适配推论，不是作者声明。

## 5. 最容易误接的四个地方

### 5.1 Expectile V 不是当前部署策略的成功率

RAPolicy 的 V 对回放中行为的 Q 做偏上分位的 expectile 拟合，再用于下一状态 bootstrap；actor 从这些行为中提取策略。**因此 V 不是当前 π 单独执行的 Vπ。** Harness 数据越强，回放可支持的较好延续越可能高于当前 policy 已能完成的延续。这不是“混入 Harness 数据就无效”，而是价值目标和策略提取误差的边界。

迁移时保留来源、目标和人工／Harness 依赖标记；评估 policy-alone 与 system-assisted 两种成功率、纠正时长和每方向表现。不能把 V 上升、加权 loss 下降或系统成功率上升当作 policy 自学习已完成。也不应直接把同一个正在优化的 V 变成成功裁判或新增稠密奖励，否则训练与验收相互佐证。技术方案已有独立成功判据，应保留。

纯动作标签不应因为能计算 `Q(X,U)` 就自动进入优势加权 RL 分支：Q 对缺少实证支持的动作可能不可靠。可信未执行建议可进入独立 BC；如果探索使用估计优势加权，应单列其假设与消融，不伪造 TD。

### 5.2 Noise replay 不排斥纠正，但也不会替纠正制造因果性

同一请求中被可靠纠正的动作可在保存的 z 条件下作为回归目标；这是把对应随机分支往更好的动作移动，并不要求纠正来自另一 VLA。离线数据没有 z 时，官方采用新的监督期望，这与保存在线生成配对是不同的数据模式。[离线模式代码](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/rlinf/data/awac_offline.py)

但 z、完整 chunk、next observation 都存在，不足以证明“起点一次选定了整个动作”。如果 Harness 在 chunk 中读到新图像才调整尾部，它产生的是反馈控制。把最终路径拼成起点开放环动作，依然不满足本项目 06 的 U 定义。此类事实先存微步、相容监督或专门反馈策略分支；不能用上游混合尾部实现绕开此问题。

### 5.3 队列版可以设计，但它是另一个待验证适配

若采用 RAPolicy 目标而保留 06 的队列环境，可以研究以下独立版本：状态仍为 `X=(h,g,C,ξ)`，动作仍为真实请求的下一槽 U，Q／V 都接收 X；普通 TD 使用 `R_n＋γ^n V_target(X_next)`，V 从合格回放的 `Q_target(X,U)` 拟合，actor 对 U 做优势加权条件回归。终局、删失、迟到和版本资格继续遵守 06。

这与 06 当前确定性头的 `Q_target(X_next,π_target(X_next))` 不同，不能只切换配置名。必须验证原生头如何接收 C、如何只产生／选取 E、真实 z 与归一化如何对应、是否满足固定预算。一步条件高斯可使部分输出监督比一般 flow matching 更直接，但仍要核对协方差结构、token 交互、输入条件和标签维度，不能仅在最终 loss 乘 mask 就宣布完成。

C 内真终局取消下一槽激活时，只保留实际请求结果与 terminal 事实；是否将该行送入 actor 的提取目标需沿用或重新说明现有采样选择，不能让没有生效的任意 U 成为成功 BC。此处是本项目推导与工程研究，非原版论文贡献。

### 5.4 Replay 选样本会影响正反学习与“可用”的定义

上游 demo pool 吸收接管及较快成功回合，是提高有效数据密度的选择。迁移不能把两个方向混在一个全局最快榜里，导致容易方向挤掉另一方向；也不能让长时纠正、恢复困难状态消失。保留不可变完整事实，再构造按目标与来源分层的训练视图；记录采样配比、失效标签撤回和行为覆盖。

官方 `prepare_chunk_transition` 有逐微步折扣和每 chunk 一次折扣两种分支，固定 chunk 分支要求有效位齐全。新队列版不能把 terminal padding、接管 hold 或被丢弃 D 当成实际已执行 E；同样不能把 `γ_slot` 再提升到 n 次幂。[折扣与尾部逻辑](https://github.com/flyfaerss/RAPolicy/blob/ef4b104/rlinf/algorithms/sac.py)

## 6. 上线前的有界验证顺序

1. **原版协议可复现性预检。** 使用相同少量 SFT 起点核对一步动作行为、动作坐标、奖励、demo 模式与算力；先确认原生头没有因一步化或归一化发生明显退化。不上来同时改实时协议、奖励和网络。
2. **同预算学习对照。** 原生 RAPolicy、可信 BC／DAgger、完整头参考和 RT EXPO 各遵守自身协议；公平统计有效物理交互、纠正和等待时间、算力与信息输入。只在成本可承受时保留全部支路。
3. **双向 Harness 接口。** 把合格同协议 Harness 纠正替换人工数据来源，保留部分／晚到纠正独立分支；同一个 θ、goal-conditioned Q/V、每方向门禁和 policy-alone 评估。
4. **连续执行适配。** 只有原生路线显示净收益，才实施队列版 RAPolicy；其 replay／target 与原版分别命名、单独测试。用事件重放验证 C/E/D、首次接管、提前终局、推理超时与热更新边界，之后才真机小预算试验。

以上顺序减少同时改多项导致的归因困难，不表示本项目可放弃最终连续执行要求。

## 7. 根审应逐项确认的 12 个问题

1. 是否把 RAPolicy 列为实质开源原生头候选，而非网页／未开源条目？
2. 是否只把它提升为优先验证候选，未宣称最终优于完整头或 RT EXPO？
3. 是否保留少量 SFT、人工干预、算力和实验样本量边界？
4. 是否明确共享多任务不等于已验证 A↔B 自主循环？
5. 是否将每方向目标传入 actor、Q、V、奖励与 replay？
6. 是否区分在线保存 latent 与离线重采 latent，未给纯建议发明物理后果？
7. 是否把反馈式中途接管从起点开放环 U 中分离？
8. 是否区分采集／学习并发与 C/E/D 连续执行？
9. 是否独立定义队列版 V-target、actor 目标和折扣，而非拼接两个公式？
10. 是否改造合并 truncation、tail fill 与权重版本清除这些不相容实现？
11. 是否用 policy-alone 双向表现与纠正依赖审核 V 的提取误差？
12. 是否保持通用接口优先，未用现成 Franka／AgileX 适配决定算法价值？

**最终结论：实质纳入调研及技术候选排序有必要。** 这属于本轮新增证据后的科学输入修订；应由根审重新冻结并按既定规则重新累计连续无问题轮次。本补充不能替代该程序，也没有证明任何待开发适配已经正确或在真机有效。
