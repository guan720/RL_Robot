# UniSteer、EXPO-FT 与 SOP：原理和交付审查

2026-09-22。本文件区分论文实验、当前官方实现和本项目判断；未安装、训练或操作机器人。全部本地产物位于会话目录。

## UniSteer：新加入的条件性候选

2026-05-11 预印本；Microsoft Research、清华、UTS。真实实验为松灵 Piper 单臂、π0 架构、每任务 30 条示范 warm-up，再进行人类接管噪声空间 RL；初始成功 10–35%，不是未适配模型直接从零起步。四任务平均 20→90%，每任务最终 20 次评估；不据此断言优于不同协议下的 ConRFT。[论文](https://arxiv.org/html/2605.10821v1)

核心是把人类动作 a_h 通过冻结 flow 的近似反演变成噪声目标 z_h，监督噪声 actor，并用奖励更新其 actor/critic。监督目标来自人的纠正，区别于要求输出始终接近 VLA 默认动作。基础 VLA 仍冻结，不能宣称其权重已经学到新任务。[论文 §3–4](https://arxiv.org/html/2605.10821v1)

**理论边界。** 在一定连续性／Lipschitz 条件下，连续 flow 的映射可逆，论文给出动作存在对应噪声的命题。故“冻结 decoder 必然无法生成任何新动作”过于绝对。但实际有限步 Euler、压缩噪声布局、有限迭代、数值误差和训练可达性不由该存在性命题保证。先检验人类动作反演后能否在真实控制单位中重建，再决定是否用它。

**公开实现。** 官方 [microsoft/UniSteer](https://github.com/microsoft/UniSteer) 为 MIT，提供 π0 与 π0.5 warm-up／在线配置、反演、actor SFT、SAC、回放、checkpoint 和服务接口。论文 π0 结果不能改称已经证明 π0.5 同性能。[π0.5 配置](https://raw.githubusercontent.com/microsoft/UniSteer/main/config/online/pi05_spoon.yaml)、[学习器](https://raw.githubusercontent.com/microsoft/UniSteer/main/src/trainer/UniSteerTrainer.py)

交付缺口在官方 README 写得很明确：robot executor 未发布，用户需自行实现硬件 I/O、接管与日志。当前样例为单臂 7D，不是现成双臂。episode success 来自外部提供的元数据，二元 reward 的生成不等于自动成功识别。warm-up π0.5 配置面向 80GB 显存，线上参考使用两块 RTX 5080；这是作者配置，不是本机资源测量或最低需求。[官方说明](https://raw.githubusercontent.com/microsoft/UniSteer/main/README.md)

**代码补核。** 默认 `mean_time` 对执行窗口的噪声做投影得到 32D，再扩展回 50×32 布局，actor 还有输出限幅；必须测这条实际路径，不能仅用完整 flow 可逆作为覆盖保证。小 actor/Q 的状态含 2048D 图像语言 prefix 特征＋7D 本体，存在语言条件；当前仍为单任务训练例程。接管反演数据可进入 RL buffer 的代码分支已存在，但默认关闭，论文协议与默认配置要分开。[独立短审](unisteer_code_review.md)

**判断。** 对松灵用户比从 Franka 移植更有针对性，但硬件控制仍缺一块；可在同批数据上进行条件性预检。适合比较“完整动作头重学”和“人类动作引导噪声学习”，不能预先承诺后者更稳、更省人工或彻底摆脱基础先验。

## EXPO-FT：基础策略会更新，不能简单归为冻结底座残差

Stanford，2026-05；作者 IRIS 实验室当前列为 CoRL 2026。采用 π0.5、动作块 Q、有限幅度 edit、候选 Q 选择和人类接管。重要区别是 VLA 本身通过数据上的原生成式训练目标持续更新，Q 梯度直接优化 edit；不应描述为 Q 端到端穿过整个 VLA，也不应描述为一直冻结初始 VLA。[项目](https://pd-perry.github.io/expo-ft/)、[作者发表页](https://irislab.stanford.edu/publications.html)

默认流程先用 10–40 条任务示范将策略 SFT 到约 40% 或以上，再在线 RL。论文附录存在随机初始化消融，但不足以替代主协议、证明双臂零成功率启动成本。部分任务仍人工复位。作者约 40% 的工作点不是本项目准入门槛，也不能直接称为可用水平；应审查示范适配后的行为覆盖和持续更新机制，不因 30/30 评估而保证新任务表现。[原文 §4.2、附录 B/C](https://arxiv.org/html/2605.25477v2)

官方代码 MIT，提供训练、采集、同步／异步和 DROID/Franka 客户端入口。核心 `update_actor` 调用 π0.5 `train_step` 并更新 actor 参数，另有 `update_edit_actor` 与 Q 更新。可选 success-only actor 数据；实际修改应审核样本选择而非只读算法名称。[核心学习器](https://raw.githubusercontent.com/pd-perry/expo-ft/main/expo_ft/agents/alg/expo_ft.py)、[使用说明](https://raw.githubusercontent.com/pd-perry/expo-ft/main/README.md)

**判断。** 对“原生 π0.5 需要持续获得能力”比永冻底座更合适；对“少量示范后仍完全没有可用行为”证据不足。保留为示范适配通过后的工程备选。Real-Time EXPO-FT 解决推理时延，首个静态抓放无需同时引入这部分复杂度。

## SOP：系统扩展参照，非新的低样本优化器

AgiBot／上海创智学院，2026-01。算法无关的在线机群系统，分别实例化 HG-DAgger 与 RECAP；10 台 G1 双臂共享学习。指标明确排除人工复位／场景设置时间，因此不能据吞吐提升推断本用户一台机器人少人化成本。官方研究页本次未找到完整系统代码入口。[论文](https://arxiv.org/html/2601.03044v1)、[官方研究页](https://finch.agibot.com/research/sop)

## 可审查快照

GitHub API 实际核验日期 2026-09-22；stars/forks 是关注度，不是真机复现次数。

| 仓库 | 许可 | Stars／Forks | 核验 HEAD |
|---|---|---|---|
| microsoft/UniSteer | MIT | 12／0 | cd87d240f5ec646e7590476593c3e95eb765b473 |
| pd-perry/expo-ft | MIT | 122／15 | 803381fc3b4c91a0c47904f1b688fc5e35904f50 |

元数据与树：[UniSteer](../evidence/deep_repo_audit/microsoft_UniSteer/metadata.json)、[EXPO-FT](../evidence/deep_repo_audit/pd-perry_expo-ft/metadata.json)。原文代码通过浏览工具读取；另尝试保存固定 SHA 源文件的本地 HTTP 下载无返回而中止，未把下载成功或本地运行作为结论依据。未获取可靠统一口径的新论文引用与模型下载数。
