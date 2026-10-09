# EXPO-FT 实现审计：弱初始 π0.5、少量示范和人工接管

审计日期：2026-09-22。用户最新条件：松灵双臂平台首先只使用一条臂完成 pick-and-place；可采集少量成功遥操作示范，可人工接管；GPU 尚未确定。这里只读审查官方代码及论文，未安装依赖、加载权重、执行训练或连接机器人。

**判断：EXPO-FT 值得升为“原生 π0.5 路线的首个工程预检候选”。初始任务成功率近零本身不足以淘汰它，因为它有成功示范播种和 SFT 路径，而且 base VLA 会继续更新。是否正式采用，应取决于少量示范之后的行为覆盖、真实监督数据回流以及算力实测。它并不是一个已经证明可在任意近零任务上低成本成功的算法。**

本审计主仓库固定为 `pd-perry/expo-ft@803381fc3b4c91a0c47904f1b688fc5e35904f50`。官方要求使用的 `pd-perry/openpi` 的 `expo_ft` 分支此次能够读取源码，但其提交查询受 GitHub API 限流及 Git 网络代理影响，未取得固定 SHA；因此涉及跨仓库冻结参数集合的结论标为静态审计疑点，不宣称已经复现作者实验。

## 1. 真正的训练机制：三个不同目标

| 组件 | 实际目标 | 对“坏初始策略”的意义 |
|---|---|---|
| 原生 π0.5 base VLA | 对回放中的动作做原有 flow-matching 监督学习 | 成功示范和之后成功轨迹可以改变动作生成器，参考分布会移动 |
| edit policy | 在回放动作附近产生有界增量，使 Q 增大，同时保留熵项 | 单次只能局部修正，但不是永远围绕初始 checkpoint 修正 |
| Q ensemble | 根据真实执行动作、累计奖励和下一状态候选动作训练 TD 目标 | 利用成功、失败和人工接管经验，为候选动作排序 |

`update_actor → prepare_batch_for_actor → train_step → compute_loss` 的调用链没有把 Q 梯度直接反传给 π0.5。π0.5 获得的目标是记录动作的监督损失；策略改善来自“候选选择/编辑/HIL 改变采集数据，再把选中的监督数据训练回 base”。因而应称为**原生 VLA 持续监督更新与 off-policy RL 联合运行**，不能表述成“原生 π0.5 的全部参数直接接受 actor-critic 的 Q 梯度”。[EXPO learner](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/expo_ft.py#L694)、[π0.5 wrapper](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/vla/pi05.py#L154)

默认 `N=8`、`n_edit_samples=8`，从 8 个 base 动作及 8 个编辑动作中按 Q 选取；默认 edit scale 为 0.2。这里的幅度定义在归一化动作空间，不能直接解释成 0.2 米、0.2 弧度或者 20% 的物理工作空间。编辑策略的训练输入可以是回放中的人类动作，不只是当前 base 的动作，但部署时编辑仍围绕 base 候选进行。[默认配置](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/configs/model/expo_ft_pi_config.py)、[候选及编辑实现](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/expo_ft.py#L608)

**由代码推断的能力边界：**Q 排序不能把候选集合中不存在的正确动作“选出来”；有界编辑也不能保证一次跨越严重错误的抓取位置、朝向或夹爪动作。另一方面，只要成功示范或成功接管轨迹持续改变 base，新一轮候选的中心也会改变，所以不能把它归入“永远锚定坏初始动作”的方法。

## 2. 成功样本池：少量成功 demo 可以启动，在线 HIL 的利用有条件

实际提供的 `expo_ft_pi_config.py` 设置 `actor_success_only=True`。虽然 learner 构造函数的缺省值为 False，判断官方运行路径应以传入配置为准。

数据路径核对如下。

1. `offline_ratio=0` 时，成功 demo 通过 `insert_dataset` 播种进在线 replay；该入口默认标记 `is_hil=True`、`is_success=True`。因此即使在线还没有自主成功，VLA 的成功监督池也可以非空。
2. `offline_ratio>0` 时，可以保留独立离线示范池；若在线成功 batch 不足，actor 采样会退回离线成功数据。它并不要求“必须先在线成功才允许 VLA 学习”。
3. 在线 episode 完成且 `success=True` 时，整条 episode 被标成功，并进入 base 的监督池。人接管后完成的 episode 也能走这条路径。
4. 在线 episode 最终失败时，其中有效的局部 HIL 纠正仍然属于 Q/edit 的回放经验，但在默认 `actor_success_only=True` 下，不会仅凭 `is_hil=True` 自动进入 base 监督池。
5. 代码中的独立 `hil_only` actor 数据分支属于 DAgger/RTC learner 采样路径，不能当作 EXPO 默认已经拥有“成功数据 ∪ 所有 HIL”采样机制。

[BatchProcessor](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/batch_processor.py#L29)、[demo 插入与成功标记](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/replay_buffer.py#L238)

官方 Cube Pick 启动脚本确实使用 10 条成功 demo、一个第 2000 步 SFT checkpoint，并设置 `offline_ratio=0`。这表明“少量 demo 播种 + 已做任务 SFT”是可直接审查的实际启动方式，不是我们额外想象出来的补丁。[官方启动脚本](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/scripts/pick/run_server.sh)

**对用户的结论：**不能从 success-only 推导“你的近零策略无法逃离坏先验”。现有成功 demo 已经提供突破口。真正要监测的是：新采集的数据是否持续扩展 base 的能力，还是在线长期失败、base 一直反复拟合最初几条 demo。

**建议的实现改进，非论文已验证组件：**先保留可信成功 demo；若观测到大量有用但未完成整回合的 HIL，可增加带质量标记的局部 HIL 监督池，与完整成功轨迹混合，并仅训练实际有效的动作 token。不要直接将 `actor_success_only=False` 当作修复，它会把所有失败经验也作为无差别 BC 目标。长期循环时还应明确保护最初的示范，避免有限在线 replay 最终覆盖它们。

采样代码在成功池为空时可返回 None，而 learner 的 success-only 更新路径会直接访问 `actor_batch.copy()`；因此启动预检应断言成功池非空、标记与恢复逻辑正确。这是接口健壮性问题；在本用户已有合格 demo 的前提下，不构成原则性冷启动阻断。

## 3. 原生 π0.5 更新了哪些参数：不要被 `freeze_pi05_encoder` 名字误导

当前默认 OpenPI 配置为 `expo_pi05_droid_lora_finetune_sft_cartesian_state`：`pi05=True`、动作维度填充至 32、horizon 16，VLM 和 action expert 都使用 LoRA 变体；base 学习率在该配置中为 `2.5e-5`，不是把 edit/Q 的 `3e-4` 自动沿用给全部 VLA 权重。[OpenPI 配置](https://github.com/pd-perry/openpi/blob/expo_ft/src/openpi/training/config.py#L874)

静态调用链显示：

- 实际参数更新依据 `config.trainable_filter = Param AND NOT freeze_filter`。
- 当前默认 `get_freeze_filter()` 组合的是匹配 `.*llm.*` 且不是 `.*lora.*` 的参数。因此 LLM 的非 LoRA 主干被冻结，LoRA 参数可以更新。
- `PaliGemma.img`、动作输入/输出投影及 π0.5 时间 MLP 不属于上述 `llm` 匹配范围；按读到的过滤器，它们没有被这个规则冻结。
- `freeze_pi05_encoder=True` 在 wrapper 中控制多候选采样时是否复用/展开 encoder 输入与 noise samples；它没有在读到的初始化和训练调用链里自动修改 `freeze_filter`。
- `embed_prefix` 调用视觉 encoder 时的 `train=False` 不能等同于参数停止求导；这里未看到图像 token 的 `stop_gradient`。

[参数过滤器](https://github.com/pd-perry/openpi/blob/expo_ft/src/openpi/models/pi0_config.py#L88)、[训练过滤器](https://github.com/pd-perry/openpi/blob/expo_ft/src/openpi/training/config.py#L562)、[采样开关](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/vla/pi05.py#L618)、[视觉前缀](https://github.com/pd-perry/openpi/blob/expo_ft/src/openpi/models/pi0.py#L105)

**这是需要运行时核实的论文/默认代码差异：**论文 D.1 声称 RL 期间冻结 base 的图像 encoder；当前可读默认配置尚未证明做到这一点。没有执行参数枚举或梯度检查，且 OpenPI 依赖分支没有固定 SHA，所以不宣布作者实验实现错误。采用时应首先固定两个仓库提交，打印实际可训练参数集合，核对单步前后各模块的参数差异和显存。若按论文冻结图像 encoder，应通过显式参数过滤器实施，不依赖变量名猜测。

另一个必须区分的事实：这里保留并训练 π0.5 原生 flow action expert 结构；它既不是替换成 ConRFT 的轻量 consistency 动作头，也不是 UniSteer 的完全冻结解码器加 noise policy。

## 4. 接管、动作 chunk 与奖励归因

执行器将 `env.step` 返回的 `real_action` 写入回放，并保存 human/action type；发生接管会清空未执行动作计划。因此代码的主要路径不是把未执行的模型计划冒充成人实际执行动作。[训练入口](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/train_pi_robo.py)

Replay 插入时，先重复当前动作填充 horizon，然后用后续实际执行动作回填前面的 chunk，遇到 episode 结束停止回填。这样一个 chunk 可同时包含自主动作与人类纠正。Q 使用前 C 个执行动作及 C 步奖励；base 使用完整 horizon 的 `full_actions`。这使“接管后整段真实轨迹学习”在结构上成立。[chunk 回填](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/replay_buffer.py#L305)、[batch 组装](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/batch_utils.py#L20)

发现两个需要实测而不能忽略的边界。

- **终止附近的动作填充：**replay 的 `valids` 用于屏蔽没有完整执行 C 步的 Q 窗口；但当前 actor 的 flow loss 对完整 H 步求均值，未看到对应实际执行长度的 token mask。短 episode 结束附近，base 可能学习到重复填充的动作尾部。它不是接管必然导致错误归因的证明，但值得检查实际样本、截断策略或增加有效动作掩码。
- **成功回合不是全段动作最优的证明：**人类最终救回的 episode 会整体进入 BC，包括此前的自主绕路。这样做可以有用，但应单独统计 HIL token、成功自主 token 和失败前缀的占比；评估时必须关闭人接管，才能知道提升来自策略还是人持续救场。

不建议为了“纯净归因”丢弃所有接管 chunk：它们记录的是真实执行序列，是有效 off-policy 经验。建议的改进是准确保存接管边界、动作有效长度与行为来源，在监督抽样时控制质量，在无接管评估中核对结果。

## 5. 单臂先行，以及之后双臂迁移的具体工作量

官方默认是 DROID/Franka 的单臂 Cartesian 控制路径，输出 7 维。用户先用一条松灵机械臂，消除了第一阶段必须联调 14 维双臂策略的负担，但仍需要适配机械臂状态、末端控制、夹爪尺度、相机与图像映射、动作归一化、接管事件和停止接口，不能仅更改机器人名称。

尤其应核对：松灵遥操作数据若记录的是关节角目标，必须先确定继续使用关节空间还是稳定转换到笛卡尔动作；不能直接套用 DROID Cartesian 的 7 维归一化统计。夹爪的绝对开度、速度命令、正负开合方向也必须统一。[OpenPI 数据配置](https://github.com/pd-perry/openpi/blob/expo_ft/src/openpi/training/config.py#L883)

之后扩展双臂时，`edit_action_xyzg` 的 mask 只把维度 3、4、5 置零，注释假设单臂 xyz/rotation/gripper 排列。直接改 `action_dim=14` 不会自动得到每臂正确的旋转 mask；需显式处理第二臂的旋转和两个夹爪。单臂阶段不用提前承担该工作量。[编辑 mask](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/expo_ft.py#L468)

官方 Cube Pick 检查的是抓起，而用户要的是抓取、搬运、放下并稳定留在目标区；奖励、成功判断和反向任务都要重做。正反循环应在两方向分别完成行为预检后接入，并按实际物体状态选下一目标，不能只按奇偶 episode 切换方向。该监督器是本用户方案的工程扩展，不是 EXPO 已开源的自主恢复保证。

## 6. 低起点与随机初始化证据应如何使用

论文主流程对不具备足够零样本能力的任务先收集示范并做 SFT，约 40% 是作者使用的工作点，不是数学必要条件。附录另报告去掉预训练初始化后仍可收敛的消融，但公开文字未充分交代该分支保留哪些 demo/SFT、随机化了哪些模块以及总训练成本；不能据此承诺“任意全随机 VLA 可以便宜地从零学会”。[论文方法与附录 B.2](https://arxiv.org/html/2605.25477v2)

因此本项目应测量 SFT 后的状态，而不是以 SFT 前接近零来永久淘汰方法。建议行为预检细分“到达物体、正确夹爪时机、稳定抓持、搬到目标、释放成功”，并记录 8 个 base 候选及编辑候选中是否出现可用动作。成功率低但关键阶段已有覆盖，与所有候选始终无关，是不同的工程起点。

## 7. 资源与工程成本：尚不能替用户确定 GPU

论文实机实验使用两张 H200；报告的平均 19.1 分钟是在线机器人交互数据口径，不是包含示范采集、SFT、更新等待、人工复位和调试的总墙钟时间。[论文实验设置](https://arxiv.org/html/2605.25477v2#S5.SS1)

代码结构自身就说明资源不应只按“小 edit 网络”估计：它仍有原生 π0.5 多候选推理与监督反向传播，另有 ResNet-50 critic 视觉支路、Q ensemble、replay 和优化器状态。官方 pick 启动脚本暴露 4 张 CUDA 卡，但 `fsdp_devices=1`；这不能解释成“四卡为最低要求”，也不能据此证明“一张消费卡足够”。

对于静态 pick-and-place，可先使用同步、按 episode 更新的标准 EXPO，而无需一开始就引入实时异步分支。用户未选 GPU 时，应准备离线样本上的一次更新、一次 8+8 候选推理和显存/延迟测量，再据此选硬件。冻结集合未核清前，不给显存下限。[官方工程说明](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/README.md)

## 8. 与 ConRFT / UniSteer 的实际取舍

| 比较项 | EXPO-FT | ConRFT / HIL-ConRFT 路线 | UniSteer 路线 |
|---|---|---|---|
| VLA 动作生成器 | 保留 π0.5 原生 flow，持续监督更新 | 现成路线需区分 VLA 特征与另建 consistency 动作头；接 π0.5 要自适配 | 保留原生 flow，但冻结生成器，训练 noise policy |
| 坏先验能否改变 | 可以通过 demo/成功轨迹监督改变，编辑本身仍局部 | 完整可训练动作头可以学习偏离初始动作；仍依赖数据/Q质量 | 理论全维可逆不代表实际压缩 noise 参数化无损；先验证反演与重建 |
| 少 demo + HIL | 有直接播种路径；失败回合局部HIL默认不进base BC | demo/接管驱动的完整动作头学习更直接，但需核具体实现 | HIL 动作需要可靠变换成可训练 noise 目标 |
| 工程优势 | 原生 π0.5 + real-robot HIL + chunk 已有统一实现 | 若接受换头，小策略在线更新较容易控制成本 | base 无在线梯度，更新开销可能更低 |
| 不能省掉的代价 | 大VLA更新、多候选推理、DROID适配和数据质量 | π0.5特征接口、动作头接入、校准与训练整合 | 反演费用、压缩误差、noise可达性及实机接口 |

后两项依据本会话已审计的 [深读机制报告](deep_offline_online.md) 与 [UniSteer/EXPO/SOP 审计](unisteer_expo_sop_audit.md)，不是本轮重新运行的实测。没有公平同硬件对比，因此不列虚构的速度/显存倍率。

## 9. 建议的采用顺序与停损条件

**第一步，先验证原生 π0.5 能否利用现有成功示范。**固定控制语义和数据统计，做有限 SFT，评价上述任务分阶段能力。不要把评估阶段人接管后的成功算作自主成功。

**第二步，代码预检先于真机 RL。**固定 EXPO 与 OpenPI 的提交；核可训练参数集合、demo 池非空、真实动作记录、chunk 有效长度和夹爪；用保存的观察与动作检查候选分布、推理延迟和单次更新资源。这里不要求预先达到固定 40% 才能继续，而要求出现可解释、可扩展的任务行为。

**第三步，有限预算在线对比。**在相同 demo、同任务初始分布、同人工时间口径下，比较 SFT/HG-DAgger 式持续监督与完整 EXPO；记录无接管成功率、每成功周期人工秒数、有效新监督比例、机器人交互时间和墙钟时间。这样才知道 Q/edit 是否值得额外工程和算力。

采用 EXPO 的条件是：SFT 后已有可用关键动作；新的成功/接管成功数据确实进入 base；无接管效果在同预算下继续改善；硬件能满足所选控制周期。**这时，优先部署官方原生 π0.5 路线，比先自移植 ConRFT 动作头更合理。**

暂缓或切换的条件是：反复排除数据/控制错误后，少量 demo 仍不能带来可用行为；候选和有界编辑长期覆盖不到纠正方向；绝大部分新 HIL 无法贡献有效监督且数据改进后仍无提升；或大模型更新成本明显超出预算。此时若允许换完整动作头，考虑 ConRFT 类路线；若想冻结原生 VLA 且 noise 反演重建通过验证，考虑 UniSteer。不要仅凭“更轻”或“更新”决定切换。

**最后接入正反循环。**单方向任务、反方向任务分别验证后，再以物体当前状态决定下一任务；对跌落、越界和失败中间态保留恢复分支。衡量是否减少人工复位，应统计完整往返周期的人工时间，不能只看 forward policy 成功率。
