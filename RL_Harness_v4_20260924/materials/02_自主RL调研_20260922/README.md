# 自主具身 RL 调研

> **当前联合方案（2026-09-23 v2）：[RL＋Harness 真机自主学习技术方案](../03_RL_Harness自主学习系统_20260922/01_RL_Harness真机自主学习技术方案.md)。同一共享目标条件 VLA 完成正反任务，GPT-6 Harness 自动观察与纠正，采用 BC＋队列增广在线 RL；RPent 纳入主骨架比较。已重新核查 SmoothRL／ARLI 的真实异步语义。当前选择与实施边界以新主文、07 和 09 为准；下文保留此前调研，不把旧排序或旧术语当现行方案。**

2026-09-22｜机械臂与移动操作｜重点降低复位、接管和现场值守。

此前 RL 单独选型先读 [低成功率策略再评估与自主练习路线](12_低成功率策略的RL再评估与自主练习路线.md)。[调研报告](01_调研报告与选型建议.md)与[交互筛选器](02_方案筛选器.html)保留最初 41 项全域目录；后续新增专题由当前报告承载。筛选器可直接用浏览器打开，无需启动服务或安装依赖；导出 CSV 后可用 Excel/WPS 打开。

| 文件 | 用途 |
|---|---|
| [前轮选型：低成功率策略再评估](12_低成功率策略的RL再评估与自主练习路线.md) | ConRFT／EXPO 按适配成本竞争；恢复分布与接管数据质量；STEAM、最新平台与实施路线 |
| [前轮：固定代码与正反自主学习](11_工程可达性与正反自主学习验证方案.md) | ConRFT／EXPO／UniSteer 固定版本深审；循环与人力验收；当前优先级按 12 |
| [前轮：ConRFT 之后的深入筛选](10_ConRFT之后的深入筛选与实施决策.md) | UniSteer／POCO／EXPO-FT／QC-FQL 原理与来源；工程优先级按 12 修订 |
| [调研报告](01_调研报告与选型建议.md) | 技术分类、主要判断、四条路线、首轮候选和验证设计 |
| [前轮审核：参考动作约束与替代基线](09_参考动作约束改进与VLA替代基线.md) | ConRFT、RLT 改造、FRS／ALOE／VLA-Precision；可信度与实施顺序 |
| [VLA＋RLT 与 HIL 组合设计](08_VLA_RLT与HIL机制组合方案.md) | token、接管回放、动作块与工程接口，按最新选型使用 |
| [弱策略下的抓放冷启动审查](07_弱基础策略下的PickPlace选型与冷启动路线.md) | 少量示范、先验依赖、人工成本；原独立小策略排序按最新 VLA 范围修订 |
| [方案筛选器](02_方案筛选器.html) | 41 项候选的筛选、勾选、备注和导出 |
| [候选 CSV](02_候选总表.csv) / [JSON](02_候选总表.json) | 全部字段与原始来源入口 |
| [影响力快照](03_影响力与开放性快照.md) / [CSV](03_影响力快照.csv) | Stars、Forks、选定条目引用与月下载，保留日期与统计范围 |
| [审核记录](04_审核记录.md) | 实质勘误、交叉审查、交付验证及边界 |
| [双向练习动机与实现路线](05_双向练习动机审查与松灵双臂实现路线.md) | 针对现有松灵双臂、π0/ACT、DAgger 的方案；区分自主性收益与共享学习假设 |
| [较新基线与 π0.5 选型补充](06_较新基线与π05选型补充.md) | RLT、STEAM/CFGRL、PLD、RL-100、ZPRL；更新实现可达性与当前推荐 |
| [真机 RL 专项](research/real_rl_stacks.md) | SERL/HIL-SERL/AutoSERL/RLPD/DSRL/ResFiT/RLT/DayDreamer/TD-MPC2/FLaRe |
| [复位与自主运行专项](research/reset_autonomy.md) | 正反任务、恢复、移动操作、非 RL 相邻方法等 14 项 |
| [VLA 与奖励专项](research/vla_self_learning.md) | RECAP/PLD/RLinf-USER/ConRFT 等与自动奖励，共 12 项 |
| [新系统补充](research/root_additions.md) | ENPIRE/FARL/UniIntervene/CRONOS/REVERSAL-BENCH |
| [本轮算法补漏](research/reassessment_algorithms.md) | HABC／RedFlow／UniIntervene；AutoSERL 复核与近期候选边界 |
| [本轮工程平台与 STEAM](research/reassessment_platforms.md) | RLinf／verl-vla／LeRobot／VLARLKit 固定提交、许可、真实 Piper 训练缺口 |
| [本轮恢复机制](research/reassessment_reset.md) | MEDAL++ 恢复分布、SERL 切换条件、PAINT 的可迁移边界 |
| [本轮直接适配](research/reassessment_direct_adaptation.md) | Real-Time EXPO-FT／InSight，时延、人工复位与监督回流 |
| [来源 URL 索引](evidence/来源URL索引.md) | 去重来源导航；具体主张以报告就近引用为准 |

浏览器只在本地保存选择和备注；不会上传。默认不预选，报告中的建议用途不代表用户已经选定。若浏览器不允许本地存储，请在关闭前导出。

科学家知识库 `../../embodied-scientist/`（位于工作区根目录下）只读。准确绝对路径见主报告；本目录不是科学家知识库更新结果。所有研究材料、元数据、脚本和验证产物均保存在本会话目录下。未执行任何 RL 训练或真实机器人操作。
