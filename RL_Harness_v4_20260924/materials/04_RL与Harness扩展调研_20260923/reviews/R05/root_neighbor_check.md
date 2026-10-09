# R05 根审补漏：恢复、训练系统与研究 Harness

2026-09-23。本记录是实际补充学习，不是运行验证。

| 候选 | 原始资料与已核内容 | 定位 |
|---|---|---|
| HALTER，KIT／UNC，2026-09-16 | [原文](https://arxiv.org/html/2609.19413v1) §III–IV：场景图组织评分、原子恢复技能组合及核验；100个主任务评测episode仍需25次人工介入，失败核验转人工，原子技能须示范训练。官方 [仓库](https://github.com/YY-GX/HALTER) 当前仅README、Code release is in progress；[项目](https://yy-gx.github.io/HALTER/) 不代替代码 | 恢复模块研究参考；不是共享双向在线RL。状态记忆和分步核验有借鉴价值，但不因论文新就晋升可用底座 |
| AcceRL，2026-03 | [官方仓库](https://github.com/distanceLu/AcceRL) 实际公开 minimal_modelfree_GIPO／minimal_WM_GIPO，README说明使用FakeEnv/FakeModel，需替换为真实VLA／环境／世界模型 | 分布式训练拓扑参考；公开最小示例不等于论文规模复现链，进程异步不等于物理chunk语义。本轮未运行或核完整算法源码，未确认仓库许可证 |
| Nautilus，TU Darmstadt／KIT／Honda Research Institute Europe等，2026-05／07修订 | [项目](https://yufengjin.github.io/nautilus/) 主Harness标Coming Soon，采集入口链接[role-ros2](https://github.com/YufengJin/role-ros2)。研究适配、合同验证和隔离运行环境为主，采集含人工遥操作与标记 | 开发工程参考；不能以采集子库开放推定整个自主学习Harness开放。未完成子库源码审计 |

上述不同层次的参考可以增加读者的学习途径，不构成改变RL主方法的证据。OpenETA另由独立子任务核对固定源码；若采纳新的骨架对照，仍须重新冻结科学输入并重启连续审查。
