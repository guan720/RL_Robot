# S3 Harness 联合反证：纠正可学、实体可对账与 GPT 退出

2026-09-23｜第三轮递进研究，**不计作五轮文档审查**。科学家库保持只读；未执行 UPDATE、创建 goal、安装或运行上游代码、训练模型及操作机器人。只在本 S3 目录保存报告、访问日志和原文证据。

**收束结论：保留一个认知骨架、一个实体 Gateway、一个事实账本和共享双向 learner。RPent、OpenETA、PhyAgentOS 进入同契约的有限预检，不凭框架名字直接换底座。新增的关键门槛是：纠正既要可信，又要在部署 policy 的可用信息及可表达动作范围内。闭环程序产生的路径不能自动倒填为旧时刻的普通 chunk 标签；程序收益最终用关闭 GPT 现场动作帮助后的部署 policy 检验。**

这里的部署 policy 可以包含预先声明并训练的 editor、latent steering 或 Q 筛选模块；底模冻结不能推出没有 policy 学习。相反，程序数量增加、工具成功率提高、评分器改变或恢复更勤，都不能直接证明该 policy 提高。

## 1. 先总结 S1/S2，再枚举联合问题

已读项目 AGENTS、科学家 START_HERE／ROLE／status／INDEX／科研 SKILL 与 RESEARCH；已读 S2 根审入口、S1 Harness、S2 Harness 源码报告、当前开发方案及接口附录。旧轮已经确认：语义编排、实体执行、任务评分和 learner 分属不同责任；Phy 的持久 intent 与绑定有用但审计止于客户端；AGP 当前缺连续动作资产；Harness-Zero 的成功整回合 SFT 不保证零成功启动。这些不是 S3 新发现。

| 联合机制 | 本轮问题 | 新学习与反证入口 |
|---|---|---|
| 教师信息 → 学生输入 | 相同学生观察是否对应互相冲突的正确纠正？ | CritiQ/ReTRy、Student-Informed Teacher Training |
| 语义动作 → 部署可表达动作 | 标签在动作 schema 内，是否仍超出所选编辑/latent 路线的可达集合？ | FlowDAgger 官方实现与透明度文档；完整方法核查交 RL 组 |
| 程序闭环 → chunk | 后续图像改变的动作能否作为最初决策的监督？ | 信息条件推导；DIDA 的适用前提复核 |
| 工具状态 → 实体状态 | unknown 终账、迟到终态、取消接纳能否释放机械臂？ | Phy 固定源码重访；ROS 2 Actions |
| 工具 ID → 物理资源 | 同一关节的两个接口／两个服务能否同时写？ | ros2_control 固定 resource manager；Spot lease 合同与 proto |
| 程序演化 → policy 学习 | 运行时强上下文和奖励变化是否冒充参数内化？ | SafeEvolve 论文、奖励配置、发布边界；HASE 方法 |
| 程序收益 → 纠正退出 | 退出后是否保留同样困难状态与信息条件？ | 本项目可否证设计；不以介入下降代替独立评估 |

实际查询、版本、失败和读取范围见 [harness_joint_log.json](harness_joint_log.json)。官方论文、作者代码、机构文档与 HF 检索分别记录；未找到资产不等于断言资产不存在。

## 2. 新学习：最相关的是信息不对称，而非又一套强教师假设

### 2.1 CritiQ／ReTRy：教师正确也可能给出不可实现的监督

Cornell 的论文将多个教师完整状态映射为同一个学生状态；CritiQ 选择性查询纠正，ReTRy 从学生访问状态启动教师，再扩展恢复起态分布。实际真机部分是 **sim 训练后迁移到 Stretch 的抽屉搜索，每方法 12 个试次**；不能称为少示范 VLA 真机在线 RL。论文依赖可调用教师和恢复能力，本项目没有因此获得强教师。论文对别名误差增长和 RL 作用的表述也不能升格为任意 POMDP、噪声 GPT 下的普遍保证。[论文 §II–IV](https://arxiv.org/html/2505.09546v1)

**本项目推断：**可借“减少不可辨识的纠正冲突”和“恢复为学生创造练习机会”，不照搬查询判别器或假定 GPT 近最优。先实测 GPT 对某类错误的纠正质量；本项目仍以可靠 BC 为起点，真实交互提供 RL。项目页已访问，但本轮未核到官方完整训练代码、权重、数据和对应代码许可；只列机制证据。[作者项目](https://portal-cornell.github.io/CritiQ_ReTRy/)

### 2.2 Student-Informed Teacher Training：纠正程序也要照顾学生的感知条件

UZH RPG 的 SITT 联合训练教师和学生，用动作分布差异约束教师，并做对齐；仿真 Franka 抽屉任务强调教师不要遮挡学生需要看的把手。其条件是教师可训练，不能套成“直接训练 GPT-6”或已验证 GPT 自动纠正。[论文 §3–5、A.1.3](https://arxiv.org/html/2412.09149v2)

**开放范围与静态差异。** 固定提交 `13b7eca69aefea5e9e1e2076e214c04775ffb1bd` 的 README 明确只提供 color maze，未包含飞行与机械臂训练实现；LICENSE 是 GPL-3.0。实读 `collect_rollouts`、`align_policy` 与 PPO 更新：学生经掩码观察对齐教师，存在真实参数更新；但 maze 路径在 KL 上使用正向 reward 加项，而论文概述为惩罚，更新路径又有额外对齐项。未运行及核清此差异，不能把该脚本直接当论文机器人配方。[固定 README](https://github.com/uzh-rpg/sitt/blob/13b7eca69aefea5e9e1e2076e214c04775ffb1bd/README.md)、[采集及对齐](https://github.com/uzh-rpg/sitt/blob/13b7eca69aefea5e9e1e2076e214c04775ffb1bd/color_maze/rl_scripts/on_policy_algorithm_toy.py)、[PPO](https://github.com/uzh-rpg/sitt/blob/13b7eca69aefea5e9e1e2076e214c04775ffb1bd/color_maze/rl_scripts/ppo_toy.py)、[LICENSE](https://github.com/uzh-rpg/sitt/blob/13b7eca69aefea5e9e1e2076e214c04775ffb1bd/LICENSE)

**本项目迁移：**在程序候选选择中增加“是否持续保留 policy 所需视觉证据”和“是否把关键反馈留给 policy”。例如纠正程序从物体背面抓住后全程遮挡，虽能成功，却可能产生难学数据。可先用相同机器人动作预算比较可见性保留程序和原程序，不新增教师网络作为首版前提。

### 2.3 FlowDAgger：可表达性有了直接的开放对照

Microsoft Research／UW 的官方仓库说明：冻结生成 base，反演专家纠正 chunk 得到初始 latent，再以 BC 训练观察条件 steering 网络；这是真实的复合 policy 学习，**这条损失链本身不是环境 TD RL**。访问时 README 已列 π0.5/MetaWorld 和 GR00T N1.7/LIBERO 两条 backend；TRANSPARENCY 仍只描述 π0.5，故不能依据该旧段落说仓库只有一个 backend。透明度文档特别限定纠正反演的有效范围，并提醒远离 base 可达行为时可能仅恢复近似动作。[官方代码入口](https://github.com/microsoft/FlowDAgger)、[官方透明度文档](https://github.com/microsoft/FlowDAgger/blob/main/TRANSPARENCY.md)

**取舍：**加入纠正吸收／编辑覆盖的预检，优先检验同一观察下“纠正 → 反演 → 再生成”的行为误差，而不只比较 latent MSE。是否适合低至零成功起点取决于有效纠正是否可达，不能单凭零成功判断。这里不重复 RL 组的固定版本、双 backend 和损失核查；未下载权重、未跑其示例、未把论文真机范围当成公开代码全部可复现。

### 2.4 SafeEvolve／HASE：联合提高不代表辅助已经退出

SafeEvolve（上海 AI Lab、SJTU、Fudan、HKUST、ZJU）在软件 agent 上联合进化提示／SkillBank 和 policy。附录专门比较去掉运行时 Harness 的 OPSD 变体，结果是部分能力内化且有效性仍有损失；在线扩展库也可能在另一些任务指标退化。**这支持部署辅助必须单列的实验设计，不支持机器人性能外推。**[论文，附录 B](https://arxiv.org/html/2609.02786v1)

固定 `94dc3693475a707a1a1fa34f0f09ec1dfcd0c87e` 的 README 与 `reward_profiles.py` 还显示：baseline/pure RL 与 prompt/skill 路径默认使用不同 reward profile，分别为 `0.50U+0.25S+0.25US` 与 `0.25U+0.50S+0.25US`。因此该默认差异不能全部归因于 Harness。公开发行还依赖外部 Slime／Megatron／LLaMA-Factory，环境 catalog 与原始 rollout 未完整随仓库提供；不当成可即刻复现的机器人后端。[固定 README](https://github.com/MaoPopovich/SafeEvolve/blob/94dc3693475a707a1a1fa34f0f09ec1dfcd0c87e/README.md)、[奖励源码](https://github.com/MaoPopovich/SafeEvolve/blob/94dc3693475a707a1a1fa34f0f09ec1dfcd0c87e/core/skillrl/reward_profiles.py)、[复现范围](https://github.com/MaoPopovich/SafeEvolve/blob/94dc3693475a707a1a1fa34f0f09ec1dfcd0c87e/docs/reproduction.md)

HASE（HKU、China Mobile、Grace Investment Machine）允许模型共同修改解法和白名单 Harness；可变 evaluator 依赖独立外部 evaluator 的偏差反馈，阶段边界才晋级。任务是分类、几何算法与因子挖掘，不是机器人。它说明“可编辑评分器”必须另有稳定锚点；本项目首版维持固定任务 rubric，不引入在线自改成功定义。[论文 §3、§6](https://arxiv.org/html/2607.03935v1)

OLAF 与 ARCHITECT 亦被定向检索：前者确实以自然语言纠正更新视觉动作 policy，后者以人类纠正积累程序库；本轮只读官方项目页，不冒称重审其实现，不因程序持续积累就自动满足无 GPT 的 VLA 部署目标。它们补足路线地图，但不替换本项目首版。[OLAF](https://ut-austin-rpl.github.io/olaf/)、[ARCHITECT](https://robo-architect.github.io/)

## 3. 联合反例：同一个动作合法，不等于同一个学生能学

以下为本项目推导，非作者已证明本系统可用。

令 `I_t` 是完整部署 policy 在决策 t 真正获得的输入：goal、图像／状态历史、承诺队列、允许的派生特征及其可用时间。若部署含 learned editor／Q，其输入也纳入 `I_t`；不能只列 base 的相机。令教师额外信息为 `Z_t`，纠正为 `a*=f(I_t,Z_t)`。普通动作 schema 一致只解决了动作编码，没有证明：

1. **信息可辨识：**纠正是否可由部署信息预测，或能通过 policy 的合法主动观察取得必要信息？
2. **动作可表达：**该 policy 家族、动作时域、编辑范围与实际解码器能否实现它？
3. **监督可信：**该纠正在本状态、目标与时效下是否有足够质量依据？

这三项与“是否执行”和“TD 是否成立”分别保存，不能让某个总分统一放行。

**反例 A，遮挡别名。** 固定 `I_t`，物体发生不可见的左右偏移 `Z=±d`；GPT 多一张侧视图，分别给 `a*=±d`。确定性平方误差回归的最优预测是条件均值，最小误差为 `E[Var(a*|I_t)]`；均值 0 可能两边都抓空。多模态 flow 可以表达两种动作分布，但在没有辨别信息时仍不能凭空知道本次隐藏分支。更多相反标签、mask 或更大网络不会自动消除信息缺口。若历史或部署可用侧视能识别，增加这些因果输入是合理补救；并须计延迟、成本、缺失处理和公平输入消融。

**反例 B，未来反馈拼 chunk。** 程序先移动；随后外部扰动使物体左／右滑，程序读取新帧后分别修正。保存完整路径是正确的，标成初始 `I_t` 下普通同信息 chunk 却改变了监督定义。若需要闭环，可在各实际决策点记录短标签，或训练显式因果历史 policy；如果主 learner 只支持固定 n 槽，应急微步仍先隔离，不能因为保存了逐步反馈就冒称已完成新协议。重放时固定 `I_t`、改变其后的反馈，若所谓同信息标签变化，即证明生成器读取了额外信息。

**不是禁止所有特权 BC。** DIDA 原论文明确研究从无延迟的有效教师学习延迟策略，并有其平滑性等前提；它支持独立建模这种数据，而非给任意后看轨迹免责。本项目未预设有效教师，故普通 BC 首先绑定可重放的当时信息；特权监督另建视图、测不可约歧义和迁移效果。[DIDA 原论文入口](https://proceedings.mlr.press/v162/liotet22a.html)

**反例 C，正确动作在部署可达范围外。** GPT 给大范围绕行，末端坐标合法，然而选定 residual 上界／latent 反演器／短 action horizon 无法生成。投影成附近小动作后仍将原纠正标“已吸收”，会伪造学习完成。应分别记录原纠正、投影／反演后的部署动作、重建误差、执行后果与被排除类型。扩大范围属于方法变更，不能还声称是原配置效果。

**最小接口补强：**在已有 `CorrectionLabel` 上补 `decision_snapshot_id`、`dependency_observation_ids`、`latest_dependency_available_at`、`feedback_used`、`supervision_mode`、`deployability_scope`、`action_reconstruction_error`。这些是派生审计信息，原始因果事件仍留账本；不能凭教师自行填写“同信息”通过。

## 4. unknown、迟到与排他：至少分成三本账

### 4.1 工具结束、实体停稳、任务评分是不同状态

Phy 固定源码的 `observe_action` 只挡 task terminal，未挡记录终态被旧状态覆盖；`reconcile_nonterminal` 跳过包括 unknown 的 terminal record。S2 已发现这一点，本轮重新打开原文确认，并据此推导合并规则；**未运行上游及复现故障**。其 HTTP client 正确区分取消接受与停止，但不能替外部硬件建立停止证据。[固定 task](https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/PhyAgentOS/forge/task.py)、[固定 client](https://github.com/PhyAgentOS/PhyAgentOS-core/blob/90ac3f22b20aa25dbcc4e3a4333df8c1747af95c/PhyAgentOS/forge/tool_client.py)

ROS 2 官方 Actions 也把 CANCELING 列为活动状态；取消响应列出尝试取消的 goal，最终 CANCELED 需看后续 result。协议允许多个 clients，具体并发由 server 决定；仅使用 action UUID 不代表独占同一实体。[ROS 2 Actions，Goal States／Cancel Goal](https://design.ros2.org/articles/actions.html)

本项目应该分开：

| 账本 | 单调性的准确含义 | 不允许的捷径 |
|---|---|---|
| 原始证据 | receipt、超时、冲突、后续纠错均追加；身份不被重写 | 删除旧 running／unknown 以制造一直确定的历史 |
| 物理权限 | 新 generation 失效旧命令；未解决实体状态时不授予冲突资源的新运动权 | task failed、TTL 到期、cancel HTTP 202 后直接放行 |
| 学习标签 | 新证据可完善或撤销历史标签，产生新视图版本 | “标签单调”解释成错误成功永远不能纠正 |

`unknown` 是知识不足，不能与 success/failure 当作简单大小顺序。unknown 可以在新证据下变为已确认的历史结果；但旧 task 得到晚回执不能恢复其动作权限。已确认完成后收到更旧 running，只能记作旧证据；互相冲突的终态不能按“最后到达”任意选一个，需保留冲突、隔离相关学习视图并对账。若还不能知道已执行到哪里，幂等重发也不能承诺“刚好一次物理运动”。

### 4.2 跨工具排他必须落在规范物理资源

新读的 ros2_control `b0c14b5…` 在 `claim_command_interface` 内对接口 key 加锁，重复 claim 抛错，LoanedCommandInterface 释放时清除 claim。这是可复用的本地 controller 资源管理机制；锁与 map 属于该 ResourceManager 实例，不能约束独立驱动进程，也不能单凭不同接口 key 推出实际关节没有冲突。[固定源码 1771 起](https://github.com/ros-controls/ros2_control/blob/b0c14b5edca8d17fc2996be1909815e8fcb587c6/hardware_interface/src/resource_manager.cpp#L1771)

Spot 官方 lease 文档与固定 `04537dda…` 的 proto 提供资源树、epoch 和序列；命令服务检查租约是否有相应资源、属于当前 epoch、相对服务所见租约是否足够新。它是设备端排他的具体参照，不是本项目现成通用 Gateway；本次没有核到服务器固件实现，SDK 还有自己的许可，不能把它叫作可任意复制的通用 MIT 底座。[官方 Lease Service](https://dev.bostondynamics.com/docs/concepts/lease_service.html)、[固定 lease.proto](https://github.com/boston-dynamics/spot-sdk/blob/04537ddafe0641d1751af3eb9e76cb785fc18594/protos/bosdyn/api/lease.proto)

**本项目设计推断：**

- `move_ee`、`move_joints`、夹爪、reset、主动观察和 trial 映射到同一套规范资源及其依赖闭包；不能按 ToolId 各锁各的。
- 权限身份至少绑定 robot、gateway/driver boot epoch、owner generation、command ID／attempt；设备写端核对代际，其他模块不持有可绕过它的写连接。
- 多资源要么原子取得，要么固定顺序且未齐备前不动；读取遥测无需因动作锁而暂停。
- 驱动本身没有代际校验时，由唯一进程持有连接并隔离其他写路径。进程重启必须排空／对账、确认当前物理状态；本地整数加一不足以撤销旧进程已送出的运动。
- 一个错误或未知回执不立即造成“永久锁死”；允许独立本地停止／保持与状态核查恢复，但恢复权限来自新实体证据，不来自超时猜测。

## 5. 候选取舍：统一契约下比较可替换成本

本轮 GitHub commit API 重核得到 RPent `6ee706935d28646828f70372ef0099c769cfe0c2`、OpenETA `7d4a0a1522ba8ebbd362bde880bad81d2a98f15e`、Phy core `90ac3f22b20aa25dbcc4e3a4333df8c1747af95c`，与已有研究版本一致；取得递归 tree。重新取得身份不等于重新审完全部源码。

| 候选 | 保留价值 | 联合缺口与取舍 |
|---|---|---|
| RPent | VLA／本体工具及动作记录入口较贴近现有学习桥 | 独立观察、真机失败出口和统一实体回执需补；保持首先联调者，不封为最优 |
| OpenETA | fresh-observation 义务、工具结果合同、实验／技能验证 | 逐工具闭环不等于固定槽 action chunk；policy adapter 与低层数据桥计入适配成本；保留同预算对照 |
| PhyAgentOS | durable intent、冻结 binding、调用身份与 GET 对账 | unknown 跨 task、状态合并、实体资源/驱动和连续 learner 证据仍需本项目实现；**进入候选骨架预检**，不能只因命名新或模块多排除 |
| ros2_control | 若本体已有正确 adapter，可复用控制接口 claim 与读写循环 | 不替代跨进程物理 owner、学习时序或语义 Harness；不是另一认知候选 |
| Spot lease | epoch／资源树／服务端校验的机制参照 | 专用 SDK／设备服务，不作为通用本体接入实现 |
| FlowDAgger | 有监督纠正进入小型可部署模块的开放比较 | 测信息与可达性后决定，不承担全系统 RL／未知回执功能 |
| SITT、CritiQ/ReTRy | 反证普通 DAgger 的信息条件，启发程序选择与恢复起态 | 缺强教师和匹配实现时仅借机制，不新增首版训练依赖 |
| SafeEvolve、HASE | 版本门禁与参数内化实验的参照 | 软件证据不作机器人实证；不引入在线改 rubric |

旧骨架具体字段比较继承 [S2 源码报告](../S2/harness_code.md) 与 [OpenETA 固定审计](../../../04_RL与Harness扩展调研_20260923/reviews/R05/openeta_source_check.md)，本轮没有把同一缺口再次包装成新发现。比较应固定 GPT、工具和本体 schema、故障流、任务和调用预算；共同自有 Gateway／账本不重复计作某个候选已具备。若某骨架能以更少改造完整传递合同，即可选择，不必保留 RPent 的名义优先级。

## 6. 最小修订与可否证实验

当前方案已经有单 Gateway、同信息 BC、部署组件声明和程序退出原则；下面主要把原则变成可检查字段。根审已将部分时序反例写入新 T40–49，本报告不再重造同名验收。

| 最小补强 | 可执行实验／故障序列 | 否证条件与决定 |
|---|---|---|
| 把纠正资格拆成质量、信息和可表达性 | 以抓空、偏移、释放不彻底三类状态分层；同一冻结输入分别生成纠正并记录额外观察；比较普通 BC、显式历史／新增部署视图及独立特权视图 | 同信息纠正仍冲突、只能靠额外图像成功，则不能宣布普通 BC 已覆盖；调整输入或缩小适用域 |
| 对代码教师加依赖追踪 | 冻结一个决策快照，分别重放两种后续反馈；检验代码是否读取 live sensor、未来 transcript 或全回合结果 | 同信息模式的标签随未来反馈变，必须拒绝该分类，按实际决策点分段；不把最终路径倒填 |
| 单独测部署可达集合 | 同一可靠纠正集、固定 goal／normalizer／采样预算，执行“纠正→候选编辑/latent反演→实际部署生成” | 关键动作维度／阶段偏差超预设容差，或只平均 L2 低但局部失败，不能依赖此路线吸收该纠正；考虑原生更新/完整头 |
| unknown 与权限分开 | POST 生效但 ACK 丢失→任务终账→新 task 相同／别名 tool 再请求→旧 succeeded 晚到 | 出现重复增量运动、新任务夺取未决资源或旧 goal 复活即失败；历史可以补账而权限不得回退 |
| 状态合并有身份与因果序列 | succeeded(v8)→running(v7)；unknown→新确认完成；success 与 failure 冲突；旧 boot 回执进入新 boot | 用到达时间覆盖终态、将 unknown 永久禁止修复、用冲突终态直接授奖，任一均失败 |
| 工具资源映射闭包 | 同时请求 move_ee／move_joints／reset；分别模拟同实例、不同进程、不同 workspace | 同一实体写区间重叠即失败；仅一个 Toolkit 报 busy 不算通过 |
| 程序收益对应训练产物 | 固定库与扩展库分别在相同总采集／纠正预算训练共享双向 policy；留出起态做无 GPT 现场动作帮助评测 | 只有辅助系统改善，独立 policy 无益，则仅能称运行／恢复收益；不能报告参数内化 |
| 退出后任务分布不变 | 按方向×错误类型逐步撤除任务内纠正；保留部署声明模块、保护和事实记录；所有失败、unknown、停止仍计分母 | 接管下降伴随任务机会、难起态或监控召回下降，不能作为退出依据 |

这些实验是**待执行设计**。预算、容差、发布阈值按工位 P0 实测和任务要求预注册，不借别人的成功率填值；episode／任务实例是统计单位，不能用控制帧数扩大样本量。实验需统一 reward/rubric 与可用信息，否则 SafeEvolve 式同时改变奖励配置的比较无法隔离 Harness 效应。旧／新 policy × 旧／新 Harness 的四格适合定位运行时贡献，程序对训练的因果作用仍需上述独立训练分支；完整设计由根审 H1–H3 统一。

程序可以仅提供可靠局部标签、合格真实交互或更多合法练习机会，不要求每个程序单独先取得显著 policy 增益。持续只解决超出任务范围的维护问题可以保留，但不能计为 policy 学习收益。若同类状态的独立 policy 已达到预定义稳定性标准，应退出该类 GPT 现场动作帮助；不以继续增长程序库拖延当前任务验收。

## 7. 收束边界

本轮新证据加强了四个判断：可执行纠正仍可能不可学；闭环后看信息必须显式建模；工具账务终结不能释放未知物理控制；联合系统提高不证明辅助已退出。它们支持现有总体结构，并要求可重放输入、可表达性预检和独立部署评估。

仍未知的是本工位 GPT 的纠正质量、完整部署输入能否识别关键错误、哪种动作路线覆盖有效纠正、驱动能否提供足够停止与执行证据，以及同预算 BC＋RL 是否优于可靠动态 BC。文献与静态代码没有回答这些真机问题。本轮没有发现可直接替代所有责任、同时满足共享双向低起点学习与独立 policy 交付的完整开放系统；此结论严格限于日志列明的搜索和实读范围。
