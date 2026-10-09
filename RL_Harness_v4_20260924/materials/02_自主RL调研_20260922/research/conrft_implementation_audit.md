# ConRFT 官方实现审计：可复现性、VLA 接口与单臂正反部署

核验日期：2026-09-22。对象为官方仓库固定版本的静态审计，不安装依赖、不运行训练、不控制机器人。原始知识库未作任何修改。

当前用户约束：松灵 ALOHA 类双臂硬件，**首项抓放先用单臂，另一臂不参与**；已有遥操作与接管能力，可以采少量成功示范；初始任务策略可能很弱；VLA 路线，不考虑 ACT；GPU 尚未确定。本文重点审核 ConRFT 工程是否足以支撑选型，不再扩展论文名单。

## 1. 应修改的推荐口径

**ConRFT 仍适合作为优先验证的“冻结 VLA 表征 + 新动作头 + 离策略 HIL”方法基线；当前证据不足以称它为“π0.5 原生、开箱可用、工程最稳或已有大量独立性能复现的框架”。**

它解决弱参考动作问题的方式很直接：训练自己的完整动作头，不把新动作限制在已有 VLA 动作附近。但是，官方实现保留的是 Octo 的预训练表征，重新学习动作头；它没有继续微调 Octo 原来的动作生成头，更没有现成 π0.5 接口。若最终目标是保留 π0.5 动作专家与原有广泛技能，这个取舍必须明确，不能用“VLA 微调”一词掩盖。[官方 README][readme] [动作头创建与权重加载][agent-create]

作者论文可信、方法合适、仓库可复用、已在用户平台可复现，是四个不同判断。本次审计增强了前两项的理解，同时明确了后两项尚需通过的门槛。

## 2. 审计版本与可回溯性

| 仓库 | 本次固定 SHA | 作用 |
|---|---|---|
| cccedric/conrft | a779fde7fa5db5a469960a8490c100f35b41b49e | 官方算法、示范、接管、在线与 Franka 基础设施 |
| cccedric/octo | e454c7a1939163a7e1c70670d34dc504c4825247 | 作者自定义 Octo，包含 sample_transformer |

ConRFT README 标注 Apache-2.0；定制 Octo 仓库标注 MIT。README 的安装步骤没有固定 Octo SHA；本文固定这两个 SHA 便于讨论，**这不是经运行验证的兼容版本锁**。[ConRFT 固定版本][conrft-sha] [Octo 固定版本][octo-sha]

本地源文件快照位于本文件旁的 `conrft_code_snapshot/`；这里只下载源文件做审计，没有建立训练环境。完整项目的外部依赖、模型权重、任务数据仍未具备，因此本报告不能等价于完成复现。

## 3. 训练链条确实公开了什么

官方主链条完整到“可开始工程验证”，不是只有推理演示：

1. `record_demos_octo.py` 采集成功示范，为每条轨迹计算 MC return 和 Octo embedding，只把成功轨迹写入示范文件。
2. `train_conrft_octo.py` 的 learner 分支先用示范做 CalQL 离线训练，保存 checkpoint 后退出。
3. 第二次以在线脚本启动，加载参数和 target 参数，接收 actor 经验与接管片段。
4. 在线每批一半 demo buffer、一半 online buffer；接管转移同时进入两个 buffer。
5. actor、learner 经 Agentlace 传输经验和网络参数。当前示例是单一香蕉抓放任务与固定一句语言目标。[示范入口][record] [离线/在线入口][train-learner] [接管入库][train-intervention]

当前示例脚本采用 30 条 demo 文件、20,000 次离线迭代；示范脚本默认采集 20 次成功。两者是不同入口默认值，不是论文或用户任务的充分数据量保证。离线脚本 BC/Q 权重为 1.0/0.1，在线为 0.1/1.0。[离线脚本][offline-sh] [在线脚本][online-sh]

**尚缺复现材料**：当前 README/教程提供的是自行采示范、训练 reward classifier、配置 Franka 的路线；未找到随示例交付的任务级示范 pkl、训练后的香蕉策略、配套 reward classifier checkpoint、完整锁定依赖环境及可直接重放的论文实验包。通用 Octo/ResNet 权重来源不等于这些任务级材料。[教程][walkthrough] [模型路径与 classifier 路径][task-config]

## 4. 实际模型是什么、梯度到哪里

实际执行关系可写为：

```text
两帧侧视/腕视图 + 固定任务文本
        → 冻结 Octo transformer → 最后时刻 readout_action token 均值（384维）
两帧 proprio → 可训练投影 ──────────────────────────────┘
        → 新的 consistency 动作头 → 单步完整 7D 动作

图像最后一帧 → 冻结 ResNet10 主干 + 可训练空间池化/投影
proprio + 待评分动作 ─────────────────────────────────┘
        → 两个 Q 网络
```

| 组件 | 固定 SHA 中可确认的行为 | 选型含义 |
|---|---|---|
| Octo transformer | actor 默认 stop_octo_gradient=True；学习批次直接使用缓存 embedding | 不以在线 RL 更新 VLA 主干；表征失效不能靠当前 RL 自动修好 |
| Octo 原动作头 | agent 只复制 octo_transformer 参数，另建 ConsistencyPolicy_octo | 没有继承原动作头；弱原策略不构成残差上限，但要从示范学新动作映射 |
| consistency head | 输入噪声、时间编码与表征，输出完整 7D；clip 到 [-1,1] | 不是 RLT 式参考动作增量；仍受 BC 数据与动作范围约束 |
| proprio 投影 | actor/critic 的 factory 都打开 use_proprio=True | 不能误写为只用视觉与语言 |
| critic | 独立 ResNet10 编码图像，再接 proprio/action；无任务文本输入 | 正反任务不能直接无条件混入同一个 Q |
| gripper | 当前 learned-gripper 路径和手臂一起由同一 7D actor/critic 学习 | 不能照搬 HIL-SERL 的某些“独立夹爪 DQN”叙述来解释本实现 |

证据：[actor/critic 调用][agent-forward]、[encoder 梯度与拼接][encoding]、[factory use_proprio][factory]、[网络构造与权重复制][agent-create]、[consistency 单步输出][networks]、[ResNet 冻结主干][resnet]。

“冻结”是由静态计算图推导的预期；正式复现仍应检查一次更新前后的参数差分，验证主干不变、头部与 Q 的预期参数改变。这个检查还可以发现参数加载、优化器分组与环境版本造成的实现偏差。

Q 并没有从 VLA 继承任务价值知识：图像主干加载 ImageNet 预训练 ResNet10，但 Q 的新层从初始化开始学习。离线使用 TD loss 加 CalQL 保守项；对采样动作的 Q 以示范 MC return 作校准下界，在线切换为普通 Q-learning target。当前 create 默认 cql_alpha=0.1，factory 未覆盖它，不能直接把别处论文表格中的系数当成本 SHA 的实际配置。少示范使离线 Q 比随机初始更有依据，但没有保证其在分布外动作上可靠。[CalQL 与 Q target 源码][agent-calql]

自定义 Octo 的关键接口是 sample_transformer：执行 transformer 后取 readout_action token 的均值，并返回时序表征；数据预处理取最后时刻写入 replay。原 Octo sample_actions/action head 仍在定制仓库内，但不代表 ConRFT 使用了它。迁移或升级 Octo 时，必须核对这个定制接口而非只核对模型名称。[定制 Octo 接口][octo-transformer]

## 5. 动作 chunk、实时性与硬件接口

### 5.1 没有原生 chunk RL

当前配置 `ChunkingWrapper(..., obs_horizon=2, act_exec_horizon=None)` 只堆叠两帧观察；执行端每次只发一个动作。agent 的批动作形状明确断言 `(batch_size, 7)`。网络里的 `repeat` 是 CalQL 候选动作采样数量，不是动作时序长度。[任务包装][task-config] [ChunkingWrapper][chunking] [动作形状断言][agent-update] [候选动作输出][networks]

因此，换成输出 16/32/50 步 chunk 的 VLA 后，不能原封不动地复用一步 TD 数据格式。若保留本基线，则以新头输出单步 7D；若保留 VLA 原 chunk，则须重新定义执行长度、奖励累计、折扣、终止、接管发生在 chunk 内部时的实际执行动作，属于另一项算法/系统改造。

### 5.2 10 Hz 是环境设置，不是端到端保证

FrankaEnv 默认 `hz=10`，step 以 sleep 补齐本步控制开销；actor 的 VLA 前向、通信、reward classifier、相机读取等仍影响真实频率。夹爪默认 `GRIPPER_SLEEP=1.0`，开闭事件会阻塞 sleep；不能承诺所有步骤都在 100 ms 完成。[Franka 控制及夹爪实现][franka]

应分别测量：正常运动步延迟、夹爪事件延迟、模型同步时延、接管生效时延；目标控制频率由松灵控制器能力和抓放需求决定。GPU 未确定之前，不应依据论文模型大小或某条 issue 承诺显存、吞吐或卡型。

### 5.3 单臂迁移仍须改的接口

当前 API 是归一化的 `Δxyz + ΔEuler + gripper`，以 Franka 的尺度映射到末端相对动作，底层依赖 Flask/ROS impedance controller。proprio 包含 tcp_pose、tcp_vel、tcp_force、tcp_torque、gripper_pose；RelativeFrame、四元数转 Euler、相机裁剪、坐标系和夹爪阈值均影响数值语义。香蕉奖励同时检查视觉概率、夹爪开度和末端高度。[任务配置][task-config] [FrankaEnv][franka]

对用户首任务：单臂大幅降低动作维数与同步难度，但若松灵只有关节位置/速度接口，需要末端增量到可执行控制指令的适配与可达性限制；没有实测力矩数据时，不能直接把零值伪装成同等 proprio 传感能力。应配置自己的输入集合，并重新采集同一动作定义下的示范。

## 6. 人工接管到底如何变成学习信号

- 执行时若有人接管，transition.actions 被替换成真实执行的人工动作；原策略建议动作没有同时保存在当前 transition 中。
- 该转移进入 online buffer；intervened=True 的转移再进入 demo buffer，因此接管样本可从两种渠道被抽到。
- Q 的 TD target 为当前 reward 加下一状态 target Q，接管本身不是额外正奖励，也没有接管优劣的专门校正。
- **actor 的 denoising/BC loss 用整批 batch.actions**；在线混批中包括自主执行的失败动作，并非只拟合成功示范/优质人工修正。
- 当前代码未按接管质量、advantage 或成功标签筛除 BC 样本。配置虽定义 bc_weight_rate/min，但已审训练链没有执行逐步衰减；脚本是离线、在线分别设置固定权重。[接管覆盖与入库][train-intervention] [混合采样][train-learner] [actor loss][agent-loss]

这不是“ConRFT 又被弱 VLA 参考动作绑死”：约束对象是经验数据，不是 VLA 参考动作。但是，弱策略的大量失败经验可能通过 BC 对改进形成阻力；这需通过数据比例与损失诊断验证。首轮不宜立刻增加多个新算法；先对比原样 loss 与“BC 仅对成功示范/可信接管，Q 仍用全部经验”的单一改动，并明确后者是自研变体。

## 7. 正反两策略能不能先做：可以，但要分清支持层次

### 作者表态与代码证据分开

作者在 [Issue #10][issue10] 回复目前代码不支持多任务，需要改数据组织、任务条件等部分。这个回复不能替代代码审计，代码本身还有更具体的限制：

1. `task_desc` 是单条固定文本，main 创建一份 tasks。
2. learner 把同一 tasks 平铺到整批，ReplayBuffer 不为每条转移存 task_id。
3. critic 不接收 tasks；形参 action_embeddings 未在 forward_critic 内使用。
4. actor 每个 episode 结束执行 `env.reset()`；banana reset 会把机器人移回预定姿态、打开夹爪。
5. TrainerConfig 默认端口为 3333/3334；原样起两个 learner 会争用端口。[任务文本][task-config] [批任务生成][train-learner] [Q 输入][agent-forward] [episode reset][train-intervention] [端口配置][factory] [物理 reset][banana-wrapper]

所以“一个 actor 改两条指令、把正反经验混在一起”不是小改动。尤其同一个视觉状态与动作，在正向/恢复任务中可能拥有不同价值；无目标条件的共享 Q 会混淆它们。

### 最小的可行工程推断

首版可用**两套独立动作头 + 两套 Q/奖励/经验池/checkpoint**，由一个机器人交互进程按当前任务选择策略。它们可以共享只读 Octo 权重，但语言不同则缓存表征也须按 task/encoder 版本分开。两 learner 可分端口，或顺序训练；不能两个控制进程同时直接发机器人指令。

更稳妥的资源路线是先分别验证前向与恢复的离线训练，再顺序启动对应 learner，确认每个数据流与模型更新都正确，最后接入单控制进程的交替执行。此处是**工程设计推断，不是官方已经测试的模式**。它允许先验证降低复位劳动，不要求第一版就验证共享学习是否正迁移。

另一个容易误判之处：继承的基础设施中**确实存在** `FWBWFrontCameraBinaryRewardClassifierWrapper`，以两个 classifier 和 task_graph 选择下一任务；当前 ConRFT 主入口和 banana 配置没有接入它。故不能说仓库完全没有正反元素，也不能说它已经给出了完整的 ConRFT 正反训练方案。[现存 FW/BW wrapper][fwbw]

## 8. 已证实缺口、静态疑点、运行后才知道的事项

| 级别 | 发现 | 对选型的实际影响 |
|---|---|---|
| 已证实接口缺口 | Octo readout_action、两固定相机键、384 维 replay embedding、Octo 参数树路径均写死 | π0.5 不是替换一个 encoder 路径；需新特征接口、维度/缓存/任务结构适配，再评估能否保留动作专家 |
| 已证实能力缺口 | 原入口单任务，Q 无 goal 条件，单步 7D | 独立正反策略可先做；共享多目标 Q、双臂、chunk 要单独设计 |
| 已证实材料缺口 | 没有随示例提供任务数据、reward 权重、已训练策略和完整环境锁 | 从零复现含数据与环境建设成本 |
| 已证实恢复语义 | checkpoint 恢复只拷贝 params/target_params，忽略 optimizer states | 离线转在线可以有意这样做；不能把任意中断恢复称为逐步等价续训 |
| 静态高优先级疑点 | 离散接管样本进入依赖连续图像序列的 memory-efficient demo buffer | 须验证接管片段间图像历史是否错误衔接，见下文 |
| 静态高优先级疑点 | 普通训练关闭 save_video，但 get_im 仍无条件追加全分辨率 recording_frames，reset 仅在 save_video 为真时保存/清空 | 可能在常规训练中持续积累视频图像；长时间试验前核查并改为按需缓存 |
| 静态待核 | GripperPenaltyWrapper 将 penalty 写到 info，agent 的损失未读取 grasp_penalty | 配置里有 -0.2 不代表它真的作为 Q reward 使用；用最小数值 trace 核查 |
| 静态待核 | 在线 MC return 默认 gamma=.95，示范与 TD discount 配置为 .98 | 当前 online update_ql 不使用 mc_returns，不能夸大成当前在线 TD 已错误；但数据重用/后续 CalQL 必须统一语义 |
| 静态待核 | launcher.py 有 serl_launcher.serl_launcher.agents 导入，主入口用 serl_launcher.agents | 与安装路径相关；须干净环境 import smoke test，未运行不能称必现导入 bug |
| 需实验 | 少量示范能否训练出可探索的完整动作头；冻结表征够不够 | 以本任务闭环成功、动作误差、场景扰动结果判定，不由论文最佳值外推 |
| 需实验 | 实际延迟、显存、host RAM、连续运行内存增长 | 必须用最终模型、图像、批量和经验池配置实测 |

固定证据：[embedding 384 维][replay] [encoder 绑定][encoding] [checkpoint 恢复][train-resume] [gripper wrapper][banana-wrapper] [loss 实现][agent-loss] [在线 gamma][train-top] [示范 discount][record] [launcher 导入][factory]。

### 接管片段与图像历史：值得比换论文更早验证

当前 actor 在 episode 末尾遍历所有转移，只有 intervened=True 的点被放入 demo buffer；两次接管之间的自主步骤被跳过。而 MemoryEfficientReplayBuffer 只在 `dones` 后开启新序列，依靠相邻存储位置重建两帧图像历史。[接管过滤][train-intervention] [存储与图像重建][memory-replay]

例如真实时间顺序为“接管 t=3,4 → 自主 t=5…20 → 接管 t=21,22”，demo buffer 可能把 4 与 21 相邻保存。若没有显式片段边界，重建图像历史可能与保存的 proprio、Octo embedding 不属于同一个时间窗。**这是由控制流发现的静态风险，尚未运行复现，不应直接下结论为已确诊 bug。**

验收应使用带唯一帧序号的记录，检查回放抽样的 obs、next_obs、proprio、actions、embedding 的时间索引完全一致；覆盖完整示范、单个接管点、分段接管、episode 末无接管和 buffer 环回。若不一致，优先修复储存语义；在它之上调 loss 不可靠。

### 内存：host RAM 不能与显存混为一谈

默认 batch_size=256、两个容量各 200,000 的 buffer。MemoryEfficientReplayBuffer 对政策图像减少重复保存；仅 256×256×3 的侧视和 128×128×3 的腕视 uint8 帧，满容量每个 buffer 就约：

`200000 × (256² + 128²) × 3 / 2³⁰ ≈ 45.8 GiB`。

这只是图像有效容量的下界，不含状态、embedding、采样批次等。当前 observation 还保留 classifier/demo 图像键；这些不属于 image_keys 的图像不会走相同的去重路径，按当前 shape 推导其附加数组可更大。**这是形状与 dtype 的容量估算，不是进程启动后立刻占用的 RSS，也不是最低硬件要求。** 实际 demo buffer 无须装满，初期可缩小容量、剔除不用的 replay 图像、分离视频与训练经验。[默认容量][default-config] [所有图像键保留][obs-wrapper] [buffer 分配][memory-replay] [基础数组分配][replay]

另有独立于 replay 的内存风险：主入口令 save_video=eval_checkpoint_step，普通训练默认 0；FrankaEnv.get_im 每次仍把全分辨率裁剪帧追加到 recording_frames。reset 只有 save_video 为真时才调用保存/清空函数。因此当前默认控制流存在列表长期积累的静态风险。应在短时采集 profile 时明确测量该列表长度与 RSS，而不是直接增加内存掩盖它。此处未运行复现，也没有证据把某条第三方 issue 的内存问题归因于它。[保存视频入口参数][train-env] [无条件追加帧][franka-video]

## 9. 官方 issues 能说明什么，不能说明什么

| 线索 | 一手页面中的问题/回复 | 证据边界 |
|---|---|---|
| 多任务 | 作者明确现代码不支持多任务 | 与当前单任务/Q 接口证据一致；不否定两实例方案 |
| 环境依赖 | 用户报告 JAX/CUDA/TF 安装组合困难 | 说明默认安装值得锁版本；不是证明所有环境都装不上 |
| GPU/RAM | 用户报告 4080/5090、显存或 32GB host RAM 遇到问题 | 工作负载与代码修改不统一，不能当实测最低配置 |
| 在线性能 | 用户报告某任务离线后在线退化，作者讨论 reward 与 Q 曲线 | 不代表原论文失败；也不支持“别人都已稳定复现” |
| 在线 BC | 用户询问为何对 online 样本也做 BC | 当前代码可直接证实这一行为，算法动机仍需区分 |
| 非 Franka 迁移 | 用户询问动作归一化 | 支持存在接口工作，不是已成功迁移的证明 |

来源：[Issue #10][issue10]、[Issue #16][issue16]、[Issue #8][issue8]、[Issue #6][issue6]、[Issue #11][issue11]、[Issue #14][issue14]。Issue 被关闭并不自动表示完成独立性能复现；提问者、作者与固定 SHA 的证据应分别归类。本文不使用 stars、forks、issue 数推断成功复现实验的团队数量。

## 10. 最小可验证路线与停止条件

以下是下一阶段实施建议，不是本次已执行的实验。

| 里程碑 | 交付物/验收 | 触发暂停的实质条件 |
|---|---|---|
| M0 版本可装可载 | 固定 ConRFT/Octo SHA、依赖 lock、权重 hash；无机器人 import/加载/假数据前向；保留完整失败日志 | 不能稳定加载或参数树不匹配，先修环境，不采真机 RL 数据 |
| M1 数据语义正确 | 单臂 7D 动作定义、坐标系、夹爪正负、两帧时间戳；接管片段 trace 与 buffer 环回检查 | 实际执行动作与训练动作不同，或图像/表征/状态错位，停止训练 |
| M2 离线更新可信 | 一批真实示范的一次更新参数差分、有限 loss、Q/MC 数值检查；只训练头的行为与文档一致 | 主干意外变化、头不更新、奖励/discount/终止定义冲突 |
| M3 少示范能闭环 | 正向与恢复分别训练；固定场景、预先定义的试验次数评估，记录接管与失败类型 | 在简单可逆抓放上仍无可用探索能力，应先补任务覆盖/适配表征，而不是加大在线 Q 权重 |
| M4 小规模 HIL | 分别开启一条任务；比较纯离线头与原版在线更新，检查 reward 假阳性、Q 发散、BC/Q 量级 | 在线明显退化、reward 被利用、真实控制频率不足 |
| M5 两独立任务交替 | 单控制进程调度；独立 Q/reward/replay/checkpoint；明确 episode 边界与真实起始状态 | 独立任务尚未达标，或切换数据归属错误，不进入共享多任务学习 |

选择 GPU 的时间点应在 M0 的可加载模型与 M1 的实际输入格式明确后；采购前可做一小批离线/profile，测峰值而不是照抄 issue 数字。先采用 Octo 官方路径最能缩小变量；若产品目标必须使用 π0.5，应该把“π0.5 新特征/头接口验证”列为 M0–M2 的新增工作包，并与原生 π0.5 方案做成本对比。

最终适合对用户说的是：**ConRFT 的原理仍合适，工程成熟度要降低半档；先以单臂、两独立任务、官方 Octo 路线通过数据与离线头的验收，再决定是否值得移植 π0.5 或做共享正反学习。**

[readme]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/README.md
[conrft-sha]: https://github.com/cccedric/conrft/tree/a779fde7fa5db5a469960a8490c100f35b41b49e
[octo-sha]: https://github.com/cccedric/octo/tree/e454c7a1939163a7e1c70670d34dc504c4825247
[walkthrough]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/docs/franka_walkthrough.md
[record]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/record_demos_octo.py#L68
[train-top]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/train_conrft_octo.py#L52
[train-learner]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/train_conrft_octo.py#L309
[train-intervention]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/train_conrft_octo.py#L195
[train-resume]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/train_conrft_octo.py#L515
[train-env]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/train_conrft_octo.py#L463
[offline-sh]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/experiments/task1_pick_banana/run_learner_conrft_pretrain.sh
[online-sh]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/experiments/task1_pick_banana/run_learner_conrft.sh
[task-config]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/experiments/task1_pick_banana/config.py#L102
[default-config]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/experiments/config.py#L9
[banana-wrapper]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/experiments/task1_pick_banana/wrapper.py#L94
[agent-forward]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/agents/continuous/conrft_single_octo_cp.py#L29
[agent-loss]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/agents/continuous/conrft_single_octo_cp.py#L310
[agent-calql]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/agents/continuous/conrft_single_octo_cp.py#L203
[octo-transformer]: https://github.com/cccedric/octo/blob/e454c7a1939163a7e1c70670d34dc504c4825247/octo/model/octo_model.py#L263
[agent-update]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/agents/continuous/conrft_single_octo_cp.py#L405
[agent-create]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/agents/continuous/conrft_single_octo_cp.py#L724
[encoding]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/common/encoding.py#L97
[factory]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/utils/launcher.py
[networks]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/networks/actor_critic_nets.py#L294
[resnet]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/vision/resnet_v1.py#L269
[replay]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/data/replay_buffer.py#L66
[memory-replay]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/data/memory_efficient_replay_buffer.py#L61
[obs-wrapper]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/wrappers/serl_obs_wrappers.py#L19
[chunking]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/wrappers/chunking.py#L54
[franka]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_robot_infra/franka_env/envs/franka_env.py#L196
[franka-video]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_robot_infra/franka_env/envs/franka_env.py#L245
[fwbw]: https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_robot_infra/franka_env/envs/wrappers.py#L35
[issue6]: https://github.com/cccedric/conrft/issues/6
[issue8]: https://github.com/cccedric/conrft/issues/8
[issue10]: https://github.com/cccedric/conrft/issues/10
[issue11]: https://github.com/cccedric/conrft/issues/11
[issue14]: https://github.com/cccedric/conrft/issues/14
[issue16]: https://github.com/cccedric/conrft/issues/16
