# S1 生态与开放资产补漏：从项目名到可复用学习链

核查日：2026-09-23。范围为论文／官方仓库页面、release、PR／issue、HF 模型／数据／Space／博客与机构发布；没有安装、完整 clone、训练或真机实验。本文件只列资产层判断与 S2 核查链，不重复 RL／Harness 专项的机制审查。

## 1. 先总结框架生态与成熟度维度

最终验收对象是**关闭外部动作纠正后仍能稳定完成双向任务的共享目标条件 policy**。生态组件的价值，是使可信 BC、真实经验 RL 和从 Harness 纠正到策略参数的转换可实施。任务通过次数、自动复位次数、程序库大小与平台支持模型数均不是这个目标的替代指标。

| 层次 | 典型资产 | 本项目必须追问 |
|---|---|---|
| 模型与预训练先验 | OpenPI、GR00T、LingBot、OpenDM | 具体开放权重／动作定义／训练参数；能否学会弱先验欠缺的动作 |
| 学习方法实现 | RAPolicy、RT-EXPO、VLA-Precision、UniSteer 等 | 哪个参数更新、纠正怎样进入 BC、失败怎样进入 RL、原实验和当前发布是否一致 |
| 训练运行时 | RLinf、LeRobot、verl-vla、Dexbotic→RLinf | 具体模型—算法—环境组合的入口；不是功能标签相乘 |
| 认知与动作桥 | RPent、Show-Harness、PhyAgentOS 等 | 工具／纠正／程序积累能否产生有状态、目标、时间与质量证据的监督 |
| 数据与发布 | LeRobot 格式、HF 模型／数据／Space | 记录事实、质量标签、模型包、归一化和依赖版本是否能一起冻结 |
| 运行与评估 | RTC、设备 adapter、独立评测 | 延迟估计与真实消费、接管后新观测、同步／异步维度顺序；是否退出 Harness 验 policy |

资产成熟度不得压成一个“开源”勾。S2 对每一条候选至少填写八项：

1. **代码**：作者官方／平台集成／第三方 fork；commit 与 branch；代码树可见不等于所有路径可执行。
2. **权重**：底模、任务 SFT、RL 后、value／reward 权重分别有无；不拿其他任务权重补空。
3. **数据**：示范、失败、自主、纠正、评测集及标签 lineage；公开规模不代表当前实验所需集合已可取。
4. **训练入口**：命令必须落到对应模型、算法和真实环境；仿真 SFT 不写成真机 RL。
5. **许可**：代码、权重、数据、底模和驱动分别读；模型卡 metadata 与正文矛盾保留待核。
6. **依赖**：锁文件、CUDA／PyTorch／JAX、加速后端和子模块；“Docker 可用”不代表镜像不可变。
7. **维护**：release、修复链和维护者回应；Closed、Merged、Draft 分开；不按 stars 排序。
8. **复现**：作者报告、第三方问题复现、第三方完整任务复现、本次静态核查分别记录。

## 2. 去重：04 的遗漏与整个会话的新增不是同一件事

基线读了 04 总报告及生态专项，并通过本地 `rg` 补查 02、03。**VLA-Precision 和 UniSteer 虽未在 04 总表展开，但 02 已详细审查；不能算本轮新方法。** UniSteer 的微软官方仓库、loopback 服务、共享绝对路径和自供 executor 也已出现在既存固定 README／审计中，重访不构成状态升级。

| 条目 | 本轮分类 | 对旧判断的影响 |
|---|---|---|
| VLA-Precision／UniSteer | 已覆盖候选的发布与维护重核 | 保留既存机制／源码问题，不因本次重新发现上调 |
| RAPolicy、RT-EXPO、verl-vla、RLinf-USER、Open-RAIL | 已覆盖 | 本组不重做排名和源码审计 |
| LeRobot v0.6.1 与 RTC／DAgger 修复链 | 新资产／维护证据 | 增加版本选取和接管恢复测试；不能只标“LeRobot 0.6” |
| OpenPI LoRA 转换 issue／PR | 新互操作性反例 | 模型发布必须测训练端与服务端同输入／同噪声一致性 |
| Dexbotic→RLinf、OpenDM、LingBot-VLA v2 | 新补的生态资产分层 | 可借模型注册／训练入口／数据规范；没有证据直接换成完整无人真机 RL |
| GR00T N1.7 具体权重许可差异 | 新资产约束证据 | 官方博客不能替代具体模型卡和仓库许可证 |
| OpenNeoData／LeRobot Space | 数据与诊断资产补漏 | 可辅助格式／数据审计，不构成本任务少示范训练证据 |

## 3. LeRobot：release 与真实动作修复必须沿链核对

官方 release 显示稳定版 **v0.6.1 于 8 月 3 日发布，短提交 7e241bd**；补丁版也有 `lerobot.types → lerobot.lerobot_types` 的破坏性更名，对应已合并 PR #4232。main 文档与 pip release 是不同的冻结对象。[v0.6.1](https://github.com/huggingface/lerobot/releases/tag/v0.6.1)、[PR #4232](https://github.com/huggingface/lerobot/pull/4232)

新查到的社区／维护者原始记录如下。它们证明报告者遇到具体问题、存在修复提案或合并记录；不宣称本组重现，也不把旧报告作用域扩大到所有模型与版本。

| 原始记录与访问时状态 | 事实和作用域 | S2 必须回答 |
|---|---|---|
| [#4223](https://github.com/huggingface/lerobot/pull/4223)，Open | 报告 SO-101＋MolmoAct2 在 RTC 冷启动／chunk 合并发生跳变，关联估计延迟与实际消费不一致；有独立回归检查评论 | 当前选定 commit 的队列截断、延迟窗口和冷启动分别走哪条实现 |
| [#4122](https://github.com/huggingface/lerobot/pull/4122)，Closed | 原动作排序／chunk 修复提案，明确因 #4452 替代关闭 | Closed 不能当作这份提案被合并 |
| [#4452](https://github.com/huggingface/lerobot/pull/4452)，9 月 22 日 Merged | 新分析指出同步路径的额外重排导致动作维度错配；修复动作／状态顺序并与 RTC 对齐；明确旧 #4122 对排序方向的判断相反 | 固定最终 merge，检查 checkpoint 次序、schema 与本体驱动顺序；不要直接照抄旧 PR |
| [#4454](https://github.com/huggingface/lerobot/pull/4454)，9 月 22 日 Merged，merge 短 SHA 7af6936 | 包含队列跳步 clamp、用最后真实动作填前缀、排除首次推理延迟；测试数字是上游报告 | 8 月 release 与 9 月 main 包含哪些修复；不能因 #4223 仍 Open 就认定相同问题均未修 |
| [issue #3747](https://github.com/huggingface/lerobot/issues/3747) → [PR #4398](https://github.com/huggingface/lerobot/pull/4398)，均 Open | 原报告固定在 main 49755a3d、SO-101、RTC；接管恢复读取旧观测。PR 提出 reset→发布新观测→resume，PR 作者只有 mock 回归、未自行真机测试 | 当前实际路径是否已有等价修复；恢复时同时作废旧 chunk 与观测，否则“有 DAgger”仍不够 |

这里最有价值的不是给 LeRobot 降分，而是增加三个通用反例：**同一动作向量可能按错关节发送；延迟估计不等于已执行动作数；清空动作队列不等于清空旧观测。** 本项目 Gateway 和 learner 都应以实发命令、时间、版本为准。

HF 官方 v0.6 博客已公开 DAgger 标记、语言纠正注释、reward API 和统一 rollout；这些是已有功能的重新访问，不能再计为新发现。语言注释可以承载 Harness 监督，但仍需新增来源／可信度／可撤销标签与真实转移分流语义。[官方博客](https://huggingface.co/blog/lerobot-release-v060)

## 4. OpenPI：训练成功与部署权重相同并非自动成立

[issue #958](https://github.com/Physical-Intelligence/openpi/issues/958) 的报告者在 `c23745b` 观察到官方 JAX→PyTorch 转换忽略 LoRA 张量：模型可加载，训练增量却可能丢失；他提供同输入数值对照与自己的修复。相应 [PR #960](https://github.com/Physical-Intelligence/openpi/pull/960) 本次页面仍为 **Open**。这是有可检验细节的第三方反例，不是我们已确认所有 OpenPI 版本都存在缺陷。

**新增工程判断：**如果 Harness 数据进入了 LoRA BC／RL，训练损失改善并不能证明已部署 policy 吸收了纠正。S2 除核发布事务，还应检查 adapter merge、missing／unexpected keys、normalizer、同 prompt／观测／噪声／精度下的输出差异。该问题也不能反过来否定 RLinf 自己的 PyTorch 重实现；必须分别核对所选调用链。

## 5. 补齐国内模型与平台资产，避免品牌列表代替学习能力

| 候选／一手入口 | 已到达的资产 | 限制与本轮定位 |
|---|---|---|
| [Dexbotic→RLinf 文档](https://github.com/dexmal/dexbotic/blob/main/docs/RLinfAsRLBackend.md) | Dexbotic 作为入口；模型注册桥、RLinf cluster／worker／runner；示例 `python -m dexbotic.rl.model_rl_libero_pi0 --suite=libero_goal`，列 `dexbotic_pi0`／`dexbotic_dm0` | 具体公开入口为 LIBERO，不能等同真机联合闭环；价值在减少“自有模型必须 fork 全平台”的集成成本。S2 可借注册接口，不必换运行时 |
| [OpenDM](https://github.com/dexmal/opendm) | DM0.5 底模、SFT／LoRA、服务接口、任务权重入口；9 月 23 日列出 XPolicyLab 的 DM05-MEM 数据转换／SFT／仿真评估 | 与旧 DM0／Dexbotic／RLinf 桥是不同资产，不能由“DM0 支持 RL”推出“DM0.5 真机在线 RL 已接通”；训练推荐 8 GPU 是上游配方，不是本项目硬需求 |
| [LingBot-VLA v2](https://github.com/Robbyant/lingbot-vla-v2)、[HF 6B 权重](https://huggingface.co/robbyant/lingbot-vla-v2-6b) | 真正的 v2 仓库和底模／RoboTwin 任务权重；SFT 与真机部署入口；9 月 22 日新 Distributed Muon；PyTorch 2.8、Python 3.12；额外教师权重要求可见 | 不是只读旧 LingBot 仓库即可代表当前生态。已见 SFT／推理，未核到该仓同配置真机在线 RL。HF YAML metadata 缺失但正文写 Apache；须检查具体文件和底模链 |
| [VLA-Precision](https://github.com/scy-v/VLA-Precision)、[releases](https://github.com/scy-v/VLA-Precision/releases) | 官方 Apache-2.0、`uv.lock`、分 stage 依赖；Stage II 四进程：控制服务／通信桥／learner／actor | 已在 02 审过，不计新候选。release 页确无 release；目录与入口不等于配套权重／数据／独立复现已齐。少示范与固定 reference 的旧问题仍在 |
| [UniSteer](https://github.com/microsoft/UniSteer)、[releases](https://github.com/microsoft/UniSteer/releases) | MIT、锁文件与测试树；demo-v1 指向 cd87d24，描述是 beads 演示视频 | demo release 不是完整论文复现包；与 02 已固定 cd87d240…一致，不能宣布新版修复。公开 PR 列表唯一 open 是依赖更新，不是反演修复证据 |

LingBot v2 官方 README 还提示发布基准用 FP32、BF16 可能显著改变成功率。此项可转成 S2 的部署数值一致性检查，但不能把别人的基准值搬成本项目效果。模型卡把 VeOmni 参考论文自动挂为该模型论文，也提醒我们不要让 HF 的自动关联替代作者实际技术报告。

## 6. HF 模型、数据与 Space：看具体对象和边界

- **GR00T N1.7。** [NVIDIA 7 月技术博客](https://developer.nvidia.com/blog/develop-humanoid-robot-policies-end-to-end-with-nvidia-isaac-gr00t/) 正文称 Apache-2.0；本次打开的[具体 HF 权重卡](https://huggingface.co/nvidia/GR00T-N1.7-3B) License 小节却指向 NVIDIA Open Model License Agreement。[产品页](https://developer.nvidia.com/isaac/gr00t) 仍保留 Early Access 和无产品级支持边界。这里只记录来源冲突：S2 必须核模型仓 LICENSE／revision，不能从代码／博客的一句话外推整个资产包的许可和支持等级。
- **OpenNeoData。** [发布者数据卡](https://huggingface.co/datasets/NeoteAIEmbodied/OpenNeoData) 声称 LeRobot v3 格式、200k+ 轨迹、5,000+ 小时，并有 CC-BY-NC-SA-4.0 和须共享联系方式才能取数据的 gate。本轮只读卡片，没有接受条件、下载或核文件内容；不能作为“公开即能无条件使用”的例子，也不把大数据预训练替代用户少示范约束。
- **LeRobot 官方可视化 Space。** [Space 页面](https://huggingface.co/spaces/lerobot/visualize_dataset) 可访问但正文主要 iframe，本轮没有实际交互验证；[本地数据路径 PR 讨论](https://huggingface.co/spaces/lerobot/visualize_dataset/discussions/4) 搜索结果显示 open 且有冲突。因此可作为诊断入口，不声称已经能在离线工位显示本地事实账本。
- **第三方 OpenPIE-0.6。** [exla-ai 模型卡](https://huggingface.co/exla-ai/openpie-0.6) 是第三方自称 RECAP 重实现，不是 PI 官方 π*0.6 资产。卡内训练指标、吞吐、对“原模型”的比較不构成独立真机 policy 复现；本轮不据此上调 RECAP 工程成熟度。

没有把 HF 下载量、模型树里的 finetune 数或 Space like 数当复现次数。VLA-Precision／UniSteer 的 HF 定向检索未返回足以确认配套任务权重和实验数据的结果，记**未核验**，不写成不存在。

## 7. 机构及社区覆盖结果

| 渠道 | 实际到达或检索到的一手入口 | 处理 |
|---|---|---|
| PI | [官方博客目录](https://www.pi.website/blog)、OpenPI issue／PR | RECAP／RLT／π0.7 旧覆盖；新增转换发布问题。第三方实现不冠 PI 官方 |
| NVIDIA | 官方技术博客、产品页、HF 模型卡 | 已有 GR00T 生态，新增具体许可差异；未发现能替代全部真机闭环的证据 |
| HF | v0.6 博客、v0.6.1 release、PR／issue、模型／数据／Space | 本轮最直接的新工程证据；区分 release 与 main |
| Google DeepMind | [Gemini Robotics 2 发布](https://deepmind.google/blog/gemini-robotics-2-brings-whole-body-intelligence-to-robots/)、[模型卡目录](https://deepmind.google/models/model-cards/) | 发布／API 层重新核对；未核完整开放在线 learner，不替换用户指定 GPT 主观察器 |
| 清华／RLinf | [官方中文 README](https://github.com/RLinf/RLinf/blob/main/README.zh-CN.md)、[新本体接入 issue](https://github.com/RLinf/RLinf/issues/1370)、Dexbotic 桥 | 主平台旧覆盖；组织采用名单是维护生态信号，不是独立完整复现证据 |
| 中科大／北航 | VLA-Precision 官方项目／代码 | 已由 02 覆盖，重核资产，不记新方法 |
| 中科院相关 | 中文／英文机构机制检索；旧 AutoSERL 原始链由专项覆盖 | 本轮搜索未得到可改变选型的新一手完整训练资产，不能说不存在 |
| 蚂蚁灵波／Dexmal | [Robbyant 组织页](https://github.com/Robbyant)、LingBot v2、OpenDM／Dexbotic | 实际查新到新仓／9 月更新；归到模型与集成，不擅升无人 RL |
| Stanford／Berkeley | Stanford 2026 BEHAVIOR 页面、BAIR blog 定向检索；RT-EXPO 旧来源 | 检索主要返回评估或既有工作；不把被搜索引擎重新抓取的旧文写成新成果 |

社区信息只作发现和反例线索。OpenPI #958、LeRobot #3747／#4223 有报告者环境、触发条件或对照，能够生成复核问题；尚无本轮查明的新增候选完整第三方真机训练复现。Reddit 的 FlashRT 贴称只有仿真且无机器人，不能以“VLA RL”标题计作真机复现；未据社交贴生成性能结论。

## 8. S2 核查清单：每次重访都必须比 S1 更深

| 优先级 | 资产／调用链 | 要产出的可审查证据 |
|---|---|---|
| P0 | LeRobot v0.6.1 ↔ #4452／#4454 merge ↔ 选定 main；#4398 当前实际代码 | 完整 SHA、相应文件 diff；动作维度排序、首次空队列、队列饥饿、推理中接管、恢复新观测的静态因果链；确认修复是否在候选构建中 |
| P0 | OpenPI 训练 checkpoint → converter → 推理加载器 | LoRA 是否合并、未加载参数、配置／normalizer、精度／同噪声差异；PR 未合并时不默认采用 |
| P0 | 已候选 RLinf／RAPolicy／RT-EXPO 与 Harness 数据桥 | 同一份事实与标签如何分流、共享 goal、行为版本和动作生效区间；本组不重做算法排名 |
| P1 | VLA-Precision Stage II 入口与依赖组 | 官方任务／部署 YAML→actor／learner／bridge；底模／SFT／RL权重及数据是否可取，人工接管与执行窗口的实际语义；读取02旧问题后只补缺项 |
| P1 | UniSteer 现 HEAD／demo-v1 ↔ 02固定 cd87d240… | 反演／依赖 decoder／压缩噪声问题是否真的变更；无差异就沿用旧限制，不重新评为“可直接用” |
| P1 | Dexbotic registry→RLinf worker builder→模型调用 | 检查可复用注册机制及固定依赖；是否能承载我们的方法，而非套用 LIBERO PPO 默认目标 |
| P2 | LingBot v2／OpenDM／GR00T N1.7 具体权重包 | 文件列表与revision、LICENSE链、预处理／动作schema／额外教师、SFT→服务的差异；只在要替换底模时推进 |
| P2 | HF数据／Space | 是否具备必要字段、可离线部署与许可；不为首版引入大规模数据依赖 |

独立 policy 收益是这些检查的共同出口：纠正后同样的失败状态再次出现时，冻结 policy 是否能自己处理；正反两个目标是否都学到；停止给动作帮助后是否保持改进。资产可用性只能决定实验能否公平开展，不能替代这个实验结论。

## 9. 访问记录与未访问说明

完整真实检索词、请求、结果 URL 与页面读取记录存于 [ecosystem_search_log.json](ecosystem_search_log.json)。搜索命中与打开正文分别标记；工具未暴露搜索引擎请求 URL，未伪造为某个 Google/Bing 链接。日期是本次访问日，页面抓取有缓存，因此 merge 时间等优先用具体 PR 正文交叉确认。

一次 `https://huggingface.co/Robbyant/lingbot-vla-v2-6b` 返回工具 Internal Error；改读官方 README 所列小写地址后成功，不能当权重不存在。未登录 HF gate、微信／Discord／私有论坛，没有假称访问封闭讨论；未下载大模型／9 TB 数据，也未测试 Space iframe。没有重新尝试旧报告里的 GitHub API／git 失败，因此不把历史网络失败当成本轮实测。本轮能确认的是公开页面和入口，不是“全球开源生态已穷尽”。

