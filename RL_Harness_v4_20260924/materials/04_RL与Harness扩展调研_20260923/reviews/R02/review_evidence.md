# R02 独立证据与工程可达性审查

**结论：NEEDS_REVISION。** 冻结版的覆盖、平台分层、通用接口和开发者阅读路径总体成立；有 **2 项必要修订**，均涉及 Real-Time EXPO-FT 的实验口径。另有 2 项可选改进，不阻断通过。

审查日：2026-09-23。审查对象仅为本轮 `input/` 内的技术方案、接口、异步附录、README、调研总报告及四份专题，共 9 文。没有读取旧轮审查结论，没有修改冻结输入、主文或知识库，没有安装候选框架、运行训练或操作机器人。最终判定针对冻结版；工作稿即使已修正，也不回改本轮结论。

## 1. 先枚举检查点

本轮按以下 14 个问题逐项检查，再进入第一方原文与源码回读：

1. 覆盖是否包含会改变选型的实时 RL、原生头更新和新 Harness，而非只重复旧候选？
2. RT-EXPO 的 42%→97% 究竟比较哪两种策略，分母是什么？
3. “无人干预”是否同时覆盖 rollout、复位和最终评测？
4. 十分钟是在线数据预算还是整体墙钟训练成本？
5. 实时 EXPO 是否确有学习代码，更新原生 VLA 与编辑器的方式是否区分？
6. 自然时延、人工 sleep 和旧帧注入是否混为一个条件？
7. RLinf 的模型—算法—环境—执行协议组合是否有具体证据？
8. verl-vla TD3+BC 的弱起点是否被误写成少示范？
9. 十示范 RECAP 是否公开、是否稳定提升，标签和 checkpoint 选择是否可追溯？
10. Show-Harness 的 DONE、语义动作和真实控制能力是否被过度推广？
11. RPent 与 Strands 等是否按相同职责公平比较，是否限定实际入口？
12. 新提交是否使旧审计自动失效或自动证明问题已修复？
13. 代码、权重许可、下载和影响力统计是否分别计证据？
14. 框架通用性是否优先于品牌适配，开发者是否能顺着材料实施？

## 2. 本轮实际独立学习的来源

实际使用浏览工具打开并回读了下列 **11 个独立第一方页面／文件**，不是仅根据待审文档的转述判断：

| 来源 | 回读位置与独立发现 |
|---|---|
| [RT-EXPO 原文 v1](https://arxiv.org/html/2609.18207v1) | Table I、§IV-C、§V-C、§VI、附录 VII-E。直接核对基线、人工复位／评测、预算和延迟条件；发现必要问题 M1、M2。 |
| [RT-EXPO 固定学习器](https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py) | `update_actor`、`update_edit_actor`、`update_critic`、`actor_success_only`。确认训练路径确实分开，critic 使用 `discount ** replan_steps`；不是网页项目壳。 |
| [verl-vla 十示范 RECAP 官方配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html) | 初始数据、Reference configuration、Evaluation results、Published artifacts。核到十示范、续跑选点、明显回退和最终标签重算。 |
| [verl-vla TD3+BC 官方配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html) | 模型更新、拓扑、actor/critic loss、50 次评测及 64%→80%；明确直接更新 PI0.5，未启用 DSRL noise actor。 |
| [RLinf-USER 官方文档](https://rlinf.readthedocs.io/en/latest/rst_source/resources/publications/rlinf_user.html) | Results 和硬件表。π₀ 真机提升列为 HG-DAgger，CNN+SAC 单列；平台统一本身不证明组合可乘。 |
| [RLinf RTC 官方文档](https://rlinf.readthedocs.io/en/latest/rst_source/guides/rtc.html) | Overview/How RTC Works。支持范围明写 OpenPI π₀.₅、LIBERO/Franka evaluation，不是本项目队列 TD 的实现证明。 |
| [Show-Harness 固定 real runner](https://github.com/showlab/Show-Harness/blob/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/real.py) | 文件说明及 `subgoal_done` 分支。末子目标 DONE 被上游当成功，足以支持本文独立核验任务判据的改造要求。 |
| [Strands 固定 run_policy](https://raw.githubusercontent.com/strands-labs/robots/4d02031/strands_robots/tools/run_policy.py) | episode recorder、`action_horizon`、`fast_mode`。该仿真 rollout 入口消费完整 chunk、默认可跳过实时 sleep；不能用其他 RTC 能力代替此入口审核。 |
| [RPent 6ee7069 提交](https://github.com/RLinf/RPent/commit/6ee7069) | 父提交、28 文件变更清单和新增探索文档。父提交为 eb269c8，文档明确沿用环境 reset、仅导出最终获胜命令；总报告对新旧范围的判断有依据。 |
| [TD3+BC 起点模型卡](https://huggingface.co/Miical/pi05-libero-spatial-sft-step-100) | Dataset size、License and attribution、downloads。432 episodes、100 optimizer steps、许可 `other`；本次页面月下载为 35。 |
| [RLinf Pick_Red 模型页](https://huggingface.co/RLinf/RLinf-Pi05-Pick_Red) | No model card，downloads not tracked；没有将未知记零的依据。 |

一次定向补漏搜索：`site:github.com/RLinf/RPent "6ee7069"`，无结果；随后直接打开冻结材料给出的官方提交 URL 成功。搜索无结果不被解释为提交不存在。Strands architecture 页面本次浏览返回 Internal Error，改读已给出的固定源码；未因此否定该框架。没有继续扩展候选集合。

## 3. 具体问题、回答与冻结版定位

下表中的简称：主文＝技术方案 `01`；接口＝技术文 `02`；异步＝技术文 `06`；总报告＝扩展调研 `01`；VLA／自主／Harness／平台＝四份 `research/` 专题。

| 问题 | 冻结版位置 | 定位回答与判定 |
|---|---|---|
| Q01：是否遗漏会改变选型的主要路线？ | 总报告 §4–7；VLA §3；自主 §3–6 | 已覆盖原生直接更新、残差／latent、实时执行、模型化、自主恢复、奖励、认知与运行层。RT-EXPO、verl-vla、Show、Strands 实际进入对照。覆盖通过；无需为追求名单更长继续宽搜。 |
| Q02：42% 是 RTC-SFT 起点吗？ | 总报告第 74 行；VLA 第 111 行 | 不是。论文 Table I 普通 SFT 均值 12.5/30≈42%，SFT w/ RTC 为 18/30=60%，RT-EXPO 为 29/30≈97%。每任务每方法评测 30 次。冻结文把 headline 与 RTC-SFT 前提放在一起但未标清基线，见 M1。[原表](https://arxiv.org/html/2609.18207v1) |
| Q03：训练无需人是否等于全流程无需人？ | 总报告 §4.2；VLA 第 111、168 行 | 不等于。原文 §V-C 明写依任务自动或人工 reset、结果由人独立验收，§VI 还将人工复位列为限制。冻结文只泛说不能外推全天候无人，缺少这项已知实验事实，见 M2。[原文](https://arxiv.org/html/2609.18207v1) |
| Q04：十分钟是否是总墙钟成本？ | 总报告第 74 行；VLA 第 111 行 | 是每任务在线机器人交互数据上限，不是总训练／复位／评测墙钟。附录另记 episode 边界集中更新及完成十回合后才开始训练。当前“十分钟量级”需更明确限定成本分母，合并 M2。[原文 §V-C、VII-E.4](https://arxiv.org/html/2609.18207v1) |
| Q05：实时代码是否实际存在、原生头是否由 Q 直接更新？ | VLA §4.2–4.5、§9；异步 §11 | 确有固定学习器；原生 actor 的 prefix BC 与 edit 的 Q 路径独立，critic 的窗口折扣可核。冻结文没有再称实时实现缺失，也没有称整个原生 flow 头直接接 Q，回答通过。[固定学习器](https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py) |
| Q06：注入时延是否被写成自然设备时延？ | 总报告第 76 行；VLA §4.4.1；主文 §10.2 | 已区分 wall-clock 与 chunk-delay，保留 Dynamic Picking 例外，并要求实测自然耗时。回答通过，不再要求同一内容重复增补。[原文 VII-E.3](https://arxiv.org/html/2609.18207v1) |
| Q07：RLinf 具备 π₀+SAC+真机队列训练的现成组合吗？ | 平台 §2、§10；总报告 §7.1 | 现有 USER 的 VLA 提升是 HG-DAgger，RTC 文档是 π₀.₅ 评估。冻结版准确拆分，并把 goal/queue/BC 标签支路列为新增。优先“验证运行时”的结论有边界，回答通过。[USER](https://rlinf.readthedocs.io/en/latest/rst_source/resources/publications/rlinf_user.html)、[RTC](https://rlinf.readthedocs.io/en/latest/rst_source/guides/rtc.html) |
| Q08：TD3+BC 100 步起点是否只有少量示范？ | 平台 §4；总报告 §4.3 | 不是；模型卡数据池 432 episodes。冻结版已经揭示这一点，并标注 8 GPU、32 并行仿真与真机未证。回答通过。[配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html)、[模型卡](https://huggingface.co/Miical/pi05-libero-spatial-sft-step-100) |
| Q09：十示范 RECAP 能否证明稳定低数据自主提升？ | 平台 §11；总报告 §4.3 | 公开弱起点参照成立：10 条／4,033 帧，三轮各 32 条，最终 106 条；8/50 到最好 23/50。8+2 GPU、16 环境、续跑选 checkpoint、退化到 1/50、示范强制 positive、最终 value 重标均已记录。不是稳定无人真机证明。回答通过，源码全链未审也已明示。[官方配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html) |
| Q10：Show-Harness 是否可原样接入 reward 和接管？ | Harness §5；主文 §6.6；接口 T31–T33 | 不能。独立源码确认上游以最终 DONE 判完成。冻结版要求独立任务判据、真实停止回执、反馈动作不冒充开放环标签，正好处理该差距。回答通过。[固定 runner](https://github.com/showlab/Show-Harness/blob/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/real.py) |
| Q11：Harness 新框架是否公平参加比较？ | 主文 §10.2 第 5 点；接口 T38；总报告 §9.2 | 同 GPT、工具、两种模拟 adapter、故障回放及成本比较已明确。接口第 393 行又限定 provider、fast mode、horizon 与真实消费索引；这与 Strands 固定入口的完整 chunk/fast-mode 事实一致。RPent 只是首先验证者，回答通过。[Strands 源码](https://raw.githubusercontent.com/strands-labs/robots/4d02031/strands_robots/tools/run_policy.py) |
| Q12：新 RPent 提交能否覆盖旧审计全部结论？ | 总报告第 131 行；Harness §3.2、§12；接口 §1.3 | 不能。总报告已经核父提交与变更范围，说明未完整审计 28 文件。官方 diff 支持探索/reset/获胜命令的具体结论，未把新 HEAD 当现成自动真机 RL。通过；专题末尾措辞可同步，见 O2。[提交](https://github.com/RLinf/RPent/commit/6ee7069) |
| Q13：许可和统计是否过度推断？ | 平台 §4、§7；总报告 §7.2 | 正确分离根代码许可与模型约束；Pick_Red 没卡且下载未追踪确实属实。起点模型本次 35 月下载与冻结版 36 略异，已有网页快照说明，不构成造假或必要修订，见 O1。[起点卡](https://huggingface.co/Miical/pi05-libero-spatial-sft-step-100)、[Pick_Red](https://huggingface.co/RLinf/RLinf-Pi05-Pick_Red) |
| Q14：通用性和可读性是否落到工程？ | README；主文 §3、§10、§12；接口 §9.1；异步 §1、§9 | 已有抓空全流程、五接口、阶段交付物、手算例和不同 schema 的 T37；写明品牌只影响移植成本、跨本体 replay 默认隔离。读者不必先读全部论文才知道下一步。通用优先和开发可读性通过；没有将拟议验收写成已测试。 |

## 4. 必要修订

### M1：明确 RT-EXPO 的比较基线与评测试次数

**定位：** 总报告第 74 行；VLA 专题第 111 行。两处“42%→97%”后紧接 RTC-SFT 前提，读者容易理解成同一 RTC 基础策略从 42% 被 RL 提升到 97%。

**修订要求：** 至少并列普通 SFT≈42%、RTC-SFT=60%、RT-EXPO≈97%，注明四任务均值、每任务每方法 30 次。不能将 RTC 带来的改善全部归为后续 RL，也不将这些小样本报告写成本项目预期成功率。[论文 Table I](https://arxiv.org/html/2609.18207v1)

### M2：将 RT-EXPO 的 rollout 无干预、人工复位／验收及数据预算分开

**定位：** 总报告 §4.2；VLA 专题 §4.1。第 168 行虽说外部 reset 假设，但不能替代实验段明示人工实际参与。

**修订要求：** 在效果数字附近直接写出：rollout 不用人工动作纠正；复位存在人工参与，最终成功由人独立验收；十分钟限定在线交互数据，不包含全部墙钟与人工成本。依据 §V-C、§VI 和附录训练安排，不扩大成“全部复位都人工”或“十分钟总计训练完成”。这不否定其算法效果，但决定它能否作为本项目无人循环的实证。[原文实验与讨论](https://arxiv.org/html/2609.18207v1)

两项均为证据表述修订，不要求重新设计算法、移植所有候选或实施真机实验。修订后须重新冻结，再由下一轮独立确认。

## 5. 可选改进，不阻断通过

- **O1：统计快照保留时间／版本。** 本次起点模型页为 35 月下载，冻结版为 36，说明同日缓存／滚动计数可能有差异。现文已把下载限制为特定资产关注度，处理合理。可保存更明确的抓取时间或只写“数十次”，不必为刷新计数反复重审。[模型页](https://huggingface.co/Miical/pi05-libero-spatial-sft-step-100)
- **O2：同步 RPent 专题与总报告的审计深度。** Harness 第 242 行仍说新 diff 待读，总报告第 131 行已经说明读了变更清单和新增文档。可统一成“已审变更清单及文档，尚未完整审计全部源码”，避免读者误解为完全没看或已全审。[新提交](https://github.com/RLinf/RPent/commit/6ee7069)

## 6. 审查计数与边界

枚举并回答 **14 个具体问题**；成功独立打开 **11 个第一方页面／文件**；定向补漏搜索 **1 次**；必要修订 **2 项**；可选改进 **2 项**。本轮没有发现需要推翻总体架构、恢复品牌优先排序、或继续无限扩大候选表的证据。

**最终状态：NEEDS_REVISION。** 通过的维度是覆盖、平台组合边界、十示范 RECAP 限制、Harness 公平比较、开放资产统计口径、通用接口和开发者阅读路径；未通过的是 RT-EXPO 效果比较和自主／成本条件的精确转述。
