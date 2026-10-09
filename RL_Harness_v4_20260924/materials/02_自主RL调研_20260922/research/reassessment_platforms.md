# 工程框架与 STEAM 路线重新评估

核验时间：2026-09-22。只读审查官方文档、论文、固定版本源码和 GitHub API；未安装环境、加载模型、训练或操作机器人。科学家知识库未修改。

用户条件：松灵 ALOHA 类双臂硬件，第一项任务仅用单臂完成 pick-and-place；已有 VLA、遥操作与接管能力；可做少量 SFT，基础成功率偏低，包括零成功率；不限定全模型更新或重学完整动作头，不考虑 ACT；目标是通过正反练习降低人工，让策略达到任务可用要求。不同任务的论文初始成功率不作为横向排序依据。

## 1. 本轮结论

**没有查到一个已公开验证的“Piper + 原生 VLA + 少示范 HIL off-policy RL + 自动正反复位”现成组合，可以直接替代 ConRFT。** 但这个结论不意味着必须迁到 Octo：若已有 π0/π0.5 数据、推理与机器人接口可用，保留现有体系的 EXPO-FT 或回合式离线改进，可能比重建 ConRFT 全链条更省工程。选择要比较迁移成本和数据利用机制，而不是按机构声望、仓库星数或不同论文的起点百分比排列。

本轮真正有价值的新分支是 **STEAM + CFGRL**：有真机论文、有 RLinf 中的策略训练代码，能从成功示范的时间结构学习数据质量信号，减少逐帧优势/奖励标注。它适合在已有混合质量数据后做批量改进；现有证据不支持把它当作少量示范、零自主成功时优于 ConRFT 的首轮在线学习器。

RLinf、verl-vla 和 LeRobot 属于工程承载层，必须与具体学习器组合来评价。不能把“支持 Piper”“支持 SAC”“支持 π0.5”三个独立勾选，合并成经过验证的 Piper π0.5 SAC 配方。

## 2. 版本、开放性与影响力快照

以下星数/派生数是 2026-09-22 直接读取 GitHub API 的仓库关注度，不是独立成功复现次数，也不是算法性能证据。下载量、论文可靠引用量、与用户硬件一致的独立性能复现数量，本轮未核验，记为未知。

| 仓库 | 固定 SHA | 许可 | stars / forks | 可用于判断的证据 |
|---|---|---|---|---|
| RLinf/RLinf | `b023deb7e90ceadfe18e0a528e862e3c630f7e0a` | Apache-2.0 | 5342 / 745 | 大型持续维护工程；USER 论文作者来自清华、无问芯穹、北理工、浙大、中关村学院、上海 AI Lab 等；这不单独证明某条算法组合可用 |
| verl-project/verl-vla | `c1de826c7c9256e4d9b6900091e4b0e243d16f5e` | Apache-2.0 | 97 / 20 | verl 官方组织下独立仓库；文档和源码版权为 ByteDance；2026-08-19 首版，较新，不能继承 verl 主仓的全部成熟度 |
| huggingface/lerobot | `7af6936589215ea0d2457de43530bc6322c7cea6` | Apache-2.0 | 27704 / 5712 | Hugging Face 工程生态与 HIL 教程；星数覆盖全部模仿学习、硬件、VLA 功能，不能当 HIL 性能验证数量 |
| VLARLKit/VLARLKit | `901ca4e9ff3fdc849170d2a65b177ccb6d919293` | MIT；部分派生源码保留 Apache-2.0 标识 | 311 / 43 | 清晰的研究型 VLA-RL 工程；当前公开配方集中于仿真，无本次目标真机组合证据 |

来源：[RLinf API](https://api.github.com/repos/RLinf/RLinf)、[verl-vla API](https://api.github.com/repos/verl-project/verl-vla)、[LeRobot API](https://api.github.com/repos/huggingface/lerobot)、[VLARLKit API](https://api.github.com/repos/VLARLKit/VLARLKit)、[RLinf-USER 作者与项目页](https://rlinf-user.github.io/)、[verl-vla 发布说明](https://github.com/verl-project/verl-vla/blob/c1de826c7c9256e4d9b6900091e4b0e243d16f5e/CHANGELOG.md)。许可表只描述代码仓库；所选模型权重、数据集和硬件 SDK 仍有各自条款。

## 3. RLinf：基础设施可靠候选，Piper 训练路径仍需接通

### 官方文档实际支持的层次

RLinf 最新真机索引明确写明：Piper 和 SO101 当前没有受支持的真机任务或训练工作流，提供的是硬件连接与测试。Piper 页的主要内容是 CAN 配置和关节/夹爪控制测试。源码树中确有 `piper/reach.py` 与 `piper_mock_sac_mlp_reach.yaml`，但 mock reach 测试不构成视觉抓放或真机 VLA RL 结果。

同时，RLinf 的 Franka 真机示例覆盖 CNN/RLPD/SAC、Flow Matching + SAC，以及 VLA 的 HG-DAgger。必须分清：RLinf-USER 报告的 π0 真机在线增益属于 **HG-DAgger**，不是同一张图里 CNN/SAC 的算法；SAC-Flow 页面中的网络是 `flow_policy`，并非 π0/π0.5 动作专家。

来源：[真机索引](https://rlinf.readthedocs.io/en/latest/rst_source/examples/real_world_index.html)、[Piper 文档](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/piper.html)、[USER 结果与算法](https://rlinf.readthedocs.io/en/latest/rst_source/resources/publications/rlinf_user.html)、[SAC-Flow 配方](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/sac_flow.html)、[固定版本 Piper mock 测试](https://github.com/RLinf/RLinf/blob/b023deb7e90ceadfe18e0a528e862e3c630f7e0a/tests/e2e_tests/embodied/piper_mock_sac_mlp_reach.yaml)。

### 对本项目的价值与代价

- 可以复用机器人资源管理、actor/learner 异步通信、回放、数据记录、VLA SFT/DAgger、奖励模型和部署接口。
- 接入现有松灵控制栈后，还要提供真实任务观测、动作转换、奖励/完成判定、接管、复位/反向调度；“同属松灵”不足以确认具体机器人就是 Piper。
- 若用原生 VLA，现有可直接识别的 off-policy 方向包括 DSRL/RLT 以及离线 RECAP/STEAM；前两者依然要审核冻结策略/参考动作约束，后两者要审核离线数据覆盖。不能因为框架同时支持 SAC 和 VLA，就断言其原生 VLA 直接接受 SAC 全动作梯度。
- 固定版本 `openpi_rlinf/tasks/rl.py` 明确是 PPO/GRPO/NFT；`tasks/dsrl.py` 是噪声转向分支。另接“冻结 VLA 表征 + 新完整动作头 + RLPD”在原理上可行，但那是需实现和验证的新模型适配，不是已发布真机结果。

来源：[原生 VLA RL 分支](https://github.com/RLinf/RLinf/blob/b023deb7e90ceadfe18e0a528e862e3c630f7e0a/rlinf/models/embodiment/openpi_rlinf/tasks/rl.py)、[DSRL 分支](https://github.com/RLinf/RLinf/blob/b023deb7e90ceadfe18e0a528e862e3c630f7e0a/rlinf/models/embodiment/openpi_rlinf/tasks/dsrl.py)。

**排序建议：** 把 RLinf 升为长期工程底座候选，不把它列为独立替代 ConRFT 的算法。若团队希望持续维护多机器人/多模型体系，其适配投入可能值得；若第一目标是尽快验证单臂正反自主训练，框架规模本身不减少首项任务集成工作。

## 4. verl-vla：原生 π0.5 TD3+BC 值得跟踪，Piper 仍缺任务学习闭环

这是与 `verl` 主仓分开的官方项目。其发布内容有实质代码：统一环境契约、浏览器遥操作/接管、π0.5 自身更新、回放、TD3+BC/CQL、DSRL、RECAP。**不能简单把它当成只有宣传页面的候选。**

但固定 SHA 的具体审查发现两条边界：

1. `src/verl_vla/envs/piper/piper_env.py` 中 `env_step()` 执行机械臂动作后，返回的 reward 恒为 0，success、terminated、truncated 恒为 False。它可以服务遥操作与记录，尚未实现抓放完成判定。未另配真实奖励与回合结束逻辑时，不能据此启动有意义的稀疏成功奖励学习。这是代码现状，不是在说用户不能补齐。
2. π0 adapter 的现有 embodiment 注册为 LIBERO、Arena、LeRobot；Piper 专用现成策略文件出现在 ACT 下。LeRobot 通用适配可能帮助迁移 π0.5，但需要验证图像键、关节动作/末端动作、夹爪归一化、任务文本和 executed chunk，不是改一行机器人名即可完成。

来源：[PiperEnv 代码](https://github.com/verl-project/verl-vla/blob/c1de826c7c9256e4d9b6900091e4b0e243d16f5e/src/verl_vla/envs/piper/piper_env.py#L78)、[π0 embodiment 注册](https://github.com/verl-project/verl-vla/blob/c1de826c7c9256e4d9b6900091e4b0e243d16f5e/src/verl_vla/models/pi0_torch/embodiments/__init__.py)。

### 它的 π0.5 TD3+BC 到底是什么

官方 LIBERO 抓放配方直接更新 π0.5，自述不启用 DSRL。策略目标结合 Q 和数据 BC，critic 加 CQL；这与“固定初始 VLA 输出 + 有界残差”不同。其公开配方给出了 critic warmup、成功/失败经验采样、训练曲线和 checkpoint 评测。参考环境是 32 个并行、自动 reset 的 LIBERO，资源示例为 8 GPU，不能当成单台真机最小显卡需求。

来源：[官方配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html)、[固定 YAML](https://github.com/verl-project/verl-vla/blob/c1de826c7c9256e4d9b6900091e4b0e243d16f5e/examples/rl/td3_bc/pi05/libero_spatial_task2_online_from_sft_step100/td3_bc.yaml)、[π0 可训练模型](https://github.com/verl-project/verl-vla/blob/c1de826c7c9256e4d9b6900091e4b0e243d16f5e/src/verl_vla/models/pi0_torch/trainable_model.py)。

**适合的采用方式：** 作为原生 VLA off-policy 工程对照，先用离线回放核对更新链，再接已验证机器人驱动、真实奖励和接管数据，不从仿真曲线推断真机样本效率。当前未见公开的 Piper π0.5 TD3+BC 真机对照结果、自动正反循环或长期无人值守结果，因此不应压过已经有真机学习证据的 ConRFT/EXPO-FT。

## 5. LeRobot HIL 与 VLARLKit：各有价值，不能自动完成 VLA 组合

LeRobot 最新 HIL 教程已经将 policy 与算法拆开：`policy.type=gaussian_actor`，`algorithm.type=sac`，actor/learner、示范池、接管、奖励分类器有官方路径。冻结视觉编码器选项存在，但当前 HIL 默认视觉配置是 ResNet10 一类编码器，不是直接复用任意 VLA 的语言条件表征。

固定审查时算法 factory 显式提供 SAC；README 将 QC-FQL 标为 coming soon。**不把未来 QC-FQL 支持记成当前可运行方案。** 若选“LeRobot HIL 基础设施 + VLA 表征 + 新完整动作头”，应标为自研适配：还须接入语言/本体状态表征、让 critic 获得任务条件、定义动作 chunk 的 TD 语义，并检验接管动作如何监督 actor。该路线不是现成的 HIL-ConRFT 复现。

来源：[HIL 教程](https://huggingface.co/docs/lerobot/main/hilserl)、[GaussianActor 配置](https://github.com/huggingface/lerobot/blob/7af6936589215ea0d2457de43530bc6322c7cea6/src/lerobot/policies/gaussian_actor/configuration_gaussian_actor.py)、[算法 factory](https://github.com/huggingface/lerobot/blob/7af6936589215ea0d2457de43530bc6322c7cea6/src/lerobot/rl/algorithms/factory.py)、[README](https://github.com/huggingface/lerobot/blob/7af6936589215ea0d2457de43530bc6322c7cea6/README.md)。

VLARLKit 的公开 README 支持 π0.5/OpenVLA-OFT、PPO/GRPO、DSRL/RLT 和仿真环境；本轮没找到具备任务奖励、人工接管及正反复位的 Piper 真机训练配方。它适合研究算法与做仿真对照，本次优先级低于已有真机数据闭环的候选。[官方 README](https://github.com/VLARLKit/VLARLKit/blob/901ca4e9ff3fdc849170d2a65b177ccb6d919293/README.md)

## 6. STEAM + CFGRL：新增的批量自学习竞争路线

### 论文事实与代码事实必须分开

原论文于 2026-06-29 发布，作者包括清华、中科院自动化所/国科大、跨维智能、鹏城实验室等。其 VLA backbone 为 π0；真机任务覆盖 ARX 双臂和 Franka 单臂。单臂抓放的数据是 **50 条成功示范 + 594 条自主 rollout**。论文还报告：抓放只用专家数据时，STEAM 筛选会缩小原本干净且有限的数据池，效果略低于 BC；加 rollout 后才改善。该证据非常直接地限制了“少量 demo 立即替代 ConRFT”的推断。[论文与数据附录](https://arxiv.org/html/2606.29834v1)

RLinf 当前开源配方的 policy 则是 π0.5：三个阶段分别是训练进度 ensemble、对已有数据标优势、用这些标签做 CFG flow matching 策略训练。代码、配置、数据处理、推理标注和策略训练入口均存在，Apache-2.0；不只有 critic 推理代码。[官方流程](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/steam.html)、[策略训练入口](https://github.com/RLinf/RLinf/blob/b023deb7e90ceadfe18e0a528e862e3c630f7e0a/examples/offline_rl/policy_optimization/cfg_rl/train_cfg.py)

### 为什么与“自学习”有关

进度模型用成功示范中两帧的时间关系自监督，不要求人工逐帧标奖励/优势；逆序帧对提供负的时间方向信号。训练后的 ensemble 给成功、失败、接管混合数据打局部质量分。策略在高质量条件下学习正确动作分布，再通过 CFG 推理。这条路线不把新动作的距离限制在某个被冻结的坏参考动作附近。

但以下劳动没有自动消失：成功示范采集与质量确认、rollout 的现场采集、接管、场景复位、正式评测。其帧顺序反转也不是训练机器人执行反向恢复任务；不能把 STEAM 的 reversed pair 当成用户需要的物理正反循环。

来源：[优势与 CFG 工作流](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/steam.html)、[CFG 数据标签接口](https://github.com/RLinf/RLinf/blob/b023deb7e90ceadfe18e0a528e862e3c630f7e0a/rlinf/data/datasets/recap/cfg_model.py)。

### 更新对象和实现限制

当前 `cfg_rl_openpi.yaml` 为 `model_type=cfg_model`、`train_expert_only=False`；模型有 `train_expert_only=True` 时冻结 VLM 的路径。因此它能更新策略本身的 flow 模型，并可选冻结表征，不是仅训练 reward 或一个噪声转向器。默认完整更新不代表本任务必须全参数训练，也不能据此承诺某张消费显卡足够。[策略配置](https://github.com/RLinf/RLinf/blob/b023deb7e90ceadfe18e0a528e862e3c630f7e0a/examples/offline_rl/config/cfg_rl_openpi.yaml)、[CFG action model](https://github.com/RLinf/RLinf/blob/b023deb7e90ceadfe18e0a528e862e3c630f7e0a/rlinf/models/embodiment/openpi_cfg/openpi_cfg_action_model.py)

开源样板有需要显式修订的参数：路径为占位符、相机键和 config_name 要换成用户配置；`steam_value_model_sft.yaml` 的 `ensemble_size=1`，不能直接当论文主要实验的 ensemble=3；优势 threshold/quantile 应按数据质量验证，不能把纯失败数据中的 top 某比例自动解释为真正有用动作。默认 CFG 把高优势样本路由到条件分支、低优势样本到无优势条件分支，并非简单把失败数据删除。[进度模型样板](https://github.com/RLinf/RLinf/blob/b023deb7e90ceadfe18e0a528e862e3c630f7e0a/examples/offline_rl/config/steam_value_model_sft.yaml)、[条件路由实现](https://github.com/RLinf/RLinf/blob/b023deb7e90ceadfe18e0a528e862e3c630f7e0a/rlinf/models/embodiment/openpi_cfg/openpi_cfg_action_model.py#L98)

### 对本用户的判断：第二阶段值得试，第一阶段不取代主线

适合接入的节点是：已经能收集覆盖抓取、搬运、放置、失败恢复的混合数据，且现有 VLA SFT/部署可靠。此时可做小规模离线 A/B：同一数据集、同一 VLA、同一训练预算，对比普通继续 SFT、只用可信示范/接管的 SFT、STEAM-CFGRL。先检验它能否正确区分局部有效纠正与失败摆动，再上新策略。

不适合直接承诺的情形是：只有几条示范，自主数据几乎全是空抓且没进入关键状态。STEAM 可以重新筛选已有证据，不能凭数据评分生成从未得到的成功控制经验。正反两个方向必须分别提供正确目标条件与覆盖，避免将相同画面变化的“进步”混用。

## 7. 对 ConRFT 排序的具体反对意见与最终决策规则

反对“ConRFT/Octo 必须第一”的理由不是论文太旧，而是 **用户现在不限定更新形式，且已有 VLA 与遥操栈**。换到自定义 Octo/JAX、单步动作、新 Q/奖励接口，可能丢掉现有 SFT 与部署成果。若 EXPO-FT 能复用已有 π0/π0.5 checkpoint 和真实动作定义，它可能拥有更短的集成路径。应先比较一个示范 batch 和一个接管回合能否正确经过各自训练链，不能只凭方法图选择。

保持 ConRFT 优先实验资格的理由是：示范/HIL/完整动作头/Q 更新已有同一真机方法链，不需要先证明固定坏参考附近能探索到成功。保持 EXPO-FT 竞争资格的理由是：基础模型会继续吸收数据，非永久固定参考；但其低起点采样效率与成功数据回流仍需同任务检验。STEAM 则提供第三种可达路径：已有混合数据后以批量模型更新换取较低的在线耦合成本。

建议使用以下顺序，而不是做跨任务“胜率排行榜”：

1. **数据和执行兼容门槛：** 同一批用户示范，各候选能否正确训练、加载和输出本体可执行动作；动作/夹爪/接管被截断的 chunk 必须保真。
2. **学习门槛：** 在同任务同人工预算下，比继续 SFT/DAgger 多出来的自主改进是否可复现；若没有，先修数据、奖励、critic，而非换更大框架。
3. **正反循环门槛：** 正反策略真实终态是否落入对方训练起态分布；失败恢复和正常反向任务分开调度，不能只比较单向成功率。
4. **可用门槛：** 每小时成功完成量、人工复位/接管分钟、必须待命时长、连续自主运行长度。由任务定义可用性，50% 以下只是用户项目的粗略低成功率参考，不是论文准入门槛。

因此，本轮工程调研没有把 RLinf 或 verl-vla 误升为“更好算法”，也没有发现能无条件推翻 ConRFT/EXPO 主竞争关系的开箱路径；它新增了 **STEAM-CFGRL 的批量自学习支线**，并将 **RLinf/verl-vla 的适配范围和缺口**具体化，供选型时核算真实工程量。
