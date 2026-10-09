# RAPolicy：公开资产与原生 VLA 挑战基线补核

核查日期：2026-09-23。本文为 R07 的独立补核，只查 RAPolicy，不改冻结科学输入。未安装、运行训练或连接机器人。

## 结论

**RAPolicy 已公开可阅读的算法与真机训练代码，不能再写成“官方代码未核实”。** 官方项目页在网页工具中访问失败，但通过 Python 标准库读取成功，页面直接链接 `flyfaerss/RAPolicy`。仓库包含 RLinf 派生实现、算法、真实环境、SFT/在线训练/消融/评估配置；主许可证为 Apache-2.0。作者明确没有发布任务 SFT 权重和收集的示范数据。固定审读版本为 **`ef4b1044f0cc78c0f6143180a2d78ae267ab03ea`**；完整 SHA 由 GitHub 固定 README 页标题核得。[官方仓库与发布说明](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/README.md)、[项目页](https://flyfaerss.github.io/RAPolicy/)、[许可证](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/LICENSE)。

**建议将它纳入优先的真机原生 VLA 动作头挑战者，优先级可高于仅有当前仿真弱起点证据的 verl-vla TD3+BC。** 理由是任务、少量 SFT 后弱起点、真实干预数据、共享语言条件多任务和训练运行时都更接近本项目；与已有 RLinf 路线还共用工程基础。这个判断是选型推断，不是复现结论，也不意味着替代本项目的执行账本、Gateway、Harness 或异步动作契约。

最重要的限制：**其异步主要是 rollout 与 learner 并行；官方配置明确在推理期间 hold，固定 chunk 执行。** 它没有直接解决本项目 C/E/D 中间段执行与新 chunk 替换问题。因此可提升挑战资格，不能不经改造就宣称是现成的完整 RL+Harness 方案。

## 1. 时间、机构、影响力与资产边界

- 论文 v1 为 2026-09-19；作者来自复旦可信具身智能研究院、上海多模态具身智能重点实验室、新加坡管理大学。是新预印本，本次没有核实会议正式接收或独立复现。[论文](https://arxiv.org/html/2609.22888v1)
- 2026-09-23 仓库页面显示 10 commits、1 star、0 fork。这是即时仓库热度，不是有效训练用户数；不以机构名气或刚发布的下载量证明稳健性。
- 可见源码、真机运行脚本、任务配置、演示视频。README 说明公开发布准备只做语法/配置/网页资源等检查，**不是重新完成论文 GPU 与真机实验**。
- 任务权重、原始演示/在线数据没有随发行版提供；HF 搜索未找到可确认的官方对应资产，HF API 请求失败，不能推出不存在其他发布。
- GitHub API 遭遇 403，commit patch 抓取超时；仍通过固定 blob 标题和 raw 文件完成版本绑定。提交实际时间未独立核得，不把论文日期冒充仓库发布日期。
- 外部 OpenPI、驱动及模型权重仍遵守各自许可证，主仓库 Apache-2.0 不覆盖所有依赖。

## 2. 论文证据与可比较边界

论文采用 π0.5；单任务先用每任务 10 条示范 SFT，在线阶段不以这些数据预填 buffer。四任务初始成功分别为 1/20、3/20、0/20、2/20，RAPolicy 最终为 20/20、19/20、14/20、16/20。这里的零是有限 20 次评估中的零，不能证明真实成功概率为零。共享五任务采用每任务 30 条示范，并预填离线 buffer，整体 52%→88%。实验用 8 张 RTX 3090，1 张 rollout、7 张 learner；训练仍有人的纠正。论文的 1–2 小时预算不是无示范、无复位、无操作员、单 GPU 的结果。[实验设定及表 I](https://arxiv.org/html/2609.22888v1)

HIL-SERL 只在插充电器任务给表格结果；其他任务缺测不能写成在所有任务胜过 HIL-SERL。论文实现的 EXPO-FT 也不能自动代表 Stanford 新增 Real-Time EXPO-FT 的严格同条件结果。共同任务、控制周期、信息输入、GPU、人类纠正和 reset 成本需另做公平比较。

## 3. 算法与训练入口：实际代码能确认什么

| 证据入口 | 已核事实 | 对本项目的含义 |
|---|---|---|
| `run_rapolicy.sh` → `run_realworld_ablation.sh` | `awac` 选择真实任务配置并启动 `train_async.py`；不是只有论文说明 | 有可审阅的端到端训练入口，仍需本地部署验证 |
| Pick Banana 基础配置 | `actor_objective: v2_awac`，π0.5 原生动作专家可训练，VLM 冻结；不是只训练残差或噪声 modulator | 避免固定弱 VLA 参考动作的强限制 |
| `forward_awac_critic` | 双 Q 的行为动作回归，目标用 target V；expectile V；无当前 actor 次状态动作采样 | 减少原生 VLA 重复推理与 replay 覆盖外 Q 查询 |
| `forward_v2_awac_actor` | detached 的优势权重乘条件对数似然；没有通过 Q 对动作求梯度 | BC 类目标与价值学习结合，不能称作 TD3 的确定性 actor loss |
| `awac_replay.py` | 默认 `last_step_state` 仅允许一步 flow；另有 `initial_latent` 多步消融 | 一步时字段对应初始噪声；禁止把任意多步中间态当独立初始 latent |
| `async_fsdp_sac_policy_worker.py` | 后台线程收轨迹、更新组边界入库、critic warmup 后 actor 更新 | 证实训练与采集并发，未证实 C/E/D 控制并发 |

固定源码：[运行入口](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/run_realworld_ablation.sh)、[Pick Banana 配置](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml)、[critic/actor worker](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py)、[latent 契约](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/awac_replay.py)、[异步 worker](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/async_fsdp_sac_policy_worker.py)。

配置中虽然保留 SAC 命名、熵对象及 trust-region 字段，RAPolicy 的默认 `v2_awac` 分支不能按名字理解为标准 SAC；该配置 `backup_entropy=false`、固定 α=0。独立动作头方案与 RAPolicy 分支应各自验证损失路由，不能混用确定性动作与 SAC entropy/log-prob 接口。

## 4. Replay、纠正数据与 latent

`TransitionReplayBuffer.add_realworld_demo_episode` 保存所有接管 transition，加上最快 20 条成功轨迹；成功轨迹被 top-K 淘汰时，其中接管条目仍被保护。在线 replay 保留真实成功和失败；demo sampling 可反复使用干预数据。**这支持长期保留已经执行的纠正数据，不支持给未执行建议虚构 reward/next_obs。**[buffer 实现](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/replay_buffer.py)

在线 latent 取自原 policy 推理请求；人类纠正动作映射到同一归一化动作坐标。离线专家没有真实 policy latent，`awac_offline.py` 在 actor 更新时仅对离线条目重新采样 Gaussian，明确不是反演专家噪声，也不是估计完整边缘 flow 似然。共享多任务配置实际启用了 offline materialization/resampling、任务 prompt 和 language-conditioned V/Q。[离线适配器](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py)、[多任务配置](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_multitask_five_tasks_sac_pi05_franka2.yaml)

本项目若引入 Harness 标签，仍须区别：原观察下可用的动作建议、得到新观察后的纠正、真实执行 transition、纯离线监督条目。原 actor 的整 chunk 条件似然不能自动解决 Harness 使用未来信息后的标签因果错配。不同来源需由已有事实账本和监督可用性 mask 控制，而非仅将 `intervene_flags` 置为真。

## 5. 动作时序兼容性：不能照搬的三个地方

1. **推理 hold。** 官方 Pick Banana 配置设 `fixed_action_chunk=true`、`hold_during_inference=true`、10Hz、chunk=10；插充电器 chunk=5。当前环境逐步执行给定 chunk，到边界后等待新推理。其效率提升不是对本项目“推理延迟未执行段、执行段、替换丢弃段”的现成解决。
2. **接管后尾部。** `realworld_env.py::chunk_step` 接管后停止使用旧 policy 尾部，将真实遥操作/hold 执行到固定边界，并把替换尾部标作 intervention。终止后不再物理执行的余位则填 canonical absorbing hold，duration=NaN，固定 chunk 的 mask 仍设有效。该吸收态补齐可以是算法内部表示，但不能被本项目记录为真实物理动作、真实监督或真实用时。
3. **整 chunk actor。** 模型 `align_hil_actions_to_model_space` 把上述纠正/hold/吸收尾部变为统一行为动作；`v2_replay_forward` 对整段 active 维度取条件 log-prob 均值，没有独立 C/E/D execution/BC mask 参数。迁入本项目必须另外定义 masked 条件目标及输入因果性，不能只改变 tensor 长度。

源码：[实际执行和补齐](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/envs/realworld/realworld_env.py)、[动作对齐与条件似然](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/models/embodiment/openpi/openpi_action_model_v2.py)。

另一个可复现细节：`prepare_chunk_transition` 在 `fixed_chunk=true` 时要求所有位置有效，否则报错；`chunk_aware=true` 时 γ 是每控制步折扣，chunk 内 reward 逐步折扣、bootstrap 用 γ 的有效步数次幂。论文将公式 γ 记为 chunk 间折扣，两者需明确换算。已有 queue-MDP 的固定 slot/首断点/terminal 处理不能被原实现的 fixed chunk 默认悄悄覆盖。[折扣代码](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py)

上面是代码语义和与本项目的差异，**不是已实测证明原算法有错误**。尤其 absorbing padding 的数学表达与事实日志是否造假是两件事，应通过类型和训练资格区分。

## 6. Harness 与通用化迁移的具体工作

- 用 GPT/Harness 的独立已校准 reward 通路替换键盘打分；原配置是 `keyboard_reward_wrapper: single_stage`、二值奖励，不能称原实现已有自动 judge。
- 用具备 lease/epoch/stop receipt 的 Gateway 取代直接环境控制，将人的 SpaceMouse 纠正改为 Harness 的已验证动作/程序，同时保留相同的执行真值来源。
- 双向共用一组 θ 和 goal-conditioned Q/V；原共享五任务支持架构方向，但不等于已经实现 A↔B 恢复循环、goal 边界和异常恢复治理。
- 保留源请求 latent、模型和归一化版本、实际执行与观察时间戳；不要只继承训练便捷字段。当前 learner ingestion 会清除部分 versions，不能据此替代本项目不可变 journal。
- 自主动作完整 slot 的 queue V/Q 目标、masked likelihood、terminal-before-activation、mid-slot takeover 应分别验算和用故障重放测试。将 IQL/AWAC 原理移到 queue 状态是本项目的新适配，而非原论文结论。
- 纯未执行建议保留独立监督库；有模型预测时也必须标 synthetic 并隔离验证，不能混入 physical replay。
- checkpoint 要区分 evaluation export 与可恢复训练快照。单任务配置默认 `save_training_state=false`，多任务另配完整 resume；本项目仍需完整 bundle 与数据来源审计。
- 通用性审核看动作/状态、任务接口、反馈契约和驱动边界，不因源码演示 Franka 或用户有 AgileX 直接加减算法排名；品牌改造量只记录初期成本。

## 7. 推荐的验证位置与尚未完成的核查

建议保留两条清晰不同的评测：

1. **RAPolicy 原生对照**：沿用 fixed chunk + inference hold，在自有少量示范和公平资源下核实弱起点改善；用于检验公开方法可达性。
2. **RAPolicy queue 适配挑战者**：相同 Gateway、观察权限、GPT/Harness 预算、正反目标与物理账本，加入本项目的 queue 状态、监督 mask、事件边界后再与确定性全动作头方案比较。改造前后的结果分开报告。

不必为了新增候选废弃确定性动作头主线；但新证据足以把“原生 VLA 挑战者首选只能来自仿真代码”的排序改正。若资源有限，RAPolicy 与 Real-Time EXPO-FT 分别代表“真机弱起点原生头”和“真实异步执行”两个不同问题，优先验这两个互补挑战者，verl-vla 保留为原生头框架备选。

尚未完成：所有文件逐行审计、依赖许可全链核验、完整配置运行、GPU 显存缩减实验、任意驱动适配、独立论文结果复现、C/E/D 新适配的理论和实测验证。上述工作未做不得写成通过。没有主流独立验证记录的刚发布方法，仍应保留成熟基线作为回退。
