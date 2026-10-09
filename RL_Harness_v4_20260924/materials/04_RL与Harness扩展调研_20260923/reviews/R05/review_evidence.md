# R05 独立证据、覆盖与选型审查

## 关键技术点

1. 原生 VLA 的 BC／优势条件更新、Q 直接优化、残差编辑与完整动作头是不同路线。
2. 训练通信异步、RTC 执行和队列 Bellman 目标须分别成立；上游 replay 不能直接混用。
3. 自主采集、自动复位、在线参数学习与辅助系统成功率须分别举证。
4. 选型依据通用接口、可替换性与可验证实现；品牌适配、机构声誉与热度不代替这些证据。

**结论：PASS。12 个具体问题已审；阻塞问题 0，可选补充 3。** 通过仅指冻结材料的证据与选型表述，不表示候选已安装、训练或真机验收。

范围：R05/input 的9份冻结文件，重点总报告与四专题，联查技术01/02/06及README。已先读科学家五份入口与技能，只读使用，未更新知识或读取旧轮审查。

## 具体审查问题与判定

| 编号与问题 | 独立核对结果及冻结材料定位 |
|---|---|
| Q1 RT-EXPO 是否真有实时学习实现，是否误称永久冻结 base？ | 通过。固定学习器存在，`update_actor` 与 `update_edit_actor` 分开；原文区分成功数据的基础策略微调与 Q 驱动编辑。总报§4.2、专题1§4没有混称全 flow 的直接 Q 更新。[S1][S2] |
| Q2 42%→97% 是否冒充 RTC 基线或无人全流程？ | 通过。Table I 的 RTC-SFT 为60%；总报保留人工复位、人工验成功及十分钟仅在线数据的限制。专题1还保留约30%基础成功率启动条件。[S1] |
| Q3 延迟和信息输入是否使比较失真？ | 通过。附录区分 wall-clock 与 chunk-delay；专题1与总报均保留人为延迟及检测器派生信息。技术01§10.2、02/T34 要求按模块对齐视图、历史、来源时刻及成本，足以防止误实现。[S1] |
| Q4 verl-vla 是否真正提供原生头更新，却被432条数据池遮蔽低数据配方？ | 通过。TD3+BC 文档给出32/50→40/50；另有十示范 RECAP，存在回退与选点。总报§4.3、专题4§11分别记录两者，未把最好46%包装成稳定真机提升。[S3][S4] |
| Q5 RLinf 的 π₀ 真机提升是否误归因于 SAC？ | 通过。官方 USER Results 明确 π₀ 使用 HG-DAgger，CNN/Flow 另列 RL。专题4§2与总报§7保留该区别，技术02/T36要求替换不相容默认目标。[S5] |
| Q6 固定 SHA 是否被误当完整可复现环境？ | 通过。专题4§10区分源码锚点与依赖锁；技术02§9要求模型、依赖、驱动固定。总报明确未运行。 |
| Q7 RPent 新 HEAD 是否使旧结论失效，或已被宣布唯一优选？ | 通过。提交页确有父提交 eb269c8、28文件变更及 RoboCasa/RoboTwin 扩展；总报§6.1只声称选定差异检查。技术01§10.2与02/T38允许其他底座以更少改造通过契约后替换 RPent。[S6] |
| Q8 Show-Harness 是否被当成自动奖励和物理停止系统？ | 通过。固定 runner 以最终 DONE 作完成信号，DAgger 入口消费人工意图。总报§6.1、专题3§5及技术02/T31–T33明确要求独立判据和实体回执，没有将语义动作接口等同完整 RL。[S7] |
| Q9 自主恢复开源是否混淆算法与部署资产？ | 通过。UniIntervene README 明确仅发布离线流水线，部署/HIL-SERL集成及轨迹权重不含其中。专题2§4.4准确保留；技术01§5也区分正常反向 RL 与异常恢复。[S8] |
| Q10 是否把论文效果跨任务排名，或用 Harness 代做证明 policy 进步？ | 通过。总报§9三条竞争轴、技术01§13与02§6分别检验独立策略、辅助系统及学习成本；保留同预算动态 BC/DAgger 对照和独立审计集。 |
| Q11 权威、热度、许可与部署可达性是否混写？ | 通过。总报§7及专题4§7将机构、stars、下载、源码、权重许可分列，未知不填零，不以母项目热度推定子项目成熟。 |
| Q12 最新框架、原生更新、复位、通用 Harness 是否存在改变结论的遗漏？ | 未发现必要遗漏。独立补搜发现 OpenETA、HALTER、AcceRL、Nautilus；其边界如下，均未构成现有组合已被完整替代的证据。可补候选地图，不要求把每篇新论文加入总报。[S9–S12] |

## 独立浏览与定位

2026-09-23实际打开以下原始来源；代码仅静态检查。

- [S1 RT-EXPO 原文](https://arxiv.org/html/2609.18207v1)：Table I、§V-C、§VI、附录VII-D.3–4及VII-E.3–5。
- [S2 固定实时学习器](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)：`update_edit_actor`、`update_actor`；网页后段截断，未据此声称逐行读完。
- [S3 verl-vla TD3+BC](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html)：Reference configuration、Evaluation results、Training losses。
- [S4 十示范 RECAP](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html)：Prepare initial dataset、Evaluation results、Published artifacts。
- [S5 RLinf-USER](https://rlinf.readthedocs.io/en/latest/rst_source/resources/publications/rlinf_user.html)：Algorithms、Hardware setup、Results。
- [S6 RPent 提交](https://github.com/RLinf/RPent/commit/6ee7069)：提交父子关系、变更文件清单及新增探索文档。
- [S7 Show runner](https://github.com/showlab/Show-Harness/blob/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/real.py)：模块说明、`_human_intent`、`_decide_interruptible`。
- [S8 UniIntervene](https://github.com/Denghaoyuan123/UniIntervene)：README 发布范围、Pipeline、Reproducibility。

## 必要修改与可选补充

**必要修改：无。** 部署锁、同预算预检和数据资格已明确为实施条件。

可选补充，不改变本轮 PASS：

1. **OpenETA** 可加入通用 Harness 浅筛。[官方仓库](https://github.com/OpenMOSS/OpenETA)（S9，Core Features、Feature Matrix）有工具契约、观测义务及UR5e路径；策略适配器未全部完成，未展示队列RL。可比较接口，无需立即改换骨架。
2. **HALTER** 可补 AutoEval 之后的组合复位线索。[原文](https://arxiv.org/html/2609.19413v1)（S10，Abstract、方法与实验）通过场景图和已学原子复位技能进行评测恢复；它没有替代同一policy的反向RL，也未消除技能准备与复位失败。
3. **AcceRL／Nautilus** 可补覆盖说明。[AcceRL](https://arxiv.org/abs/2603.18464)（S11，Abstract）偏分布式异步及世界模型仿真；[Nautilus](https://arxiv.org/abs/2605.11665)（S12，Abstract）偏复现适配工作流；均非已验证物理自主训练。

实际补搜：`robot native VLA reinforcement learning open source framework September 2026 asynchronous`、`robot autonomous reset free reinforcement learning September 2026 open source`、`general robot harness framework September 2026`、`Q-VGM github`。摘要仅作线索，回到上述第一方来源；未找到不等于不存在，不宣称穷尽。
