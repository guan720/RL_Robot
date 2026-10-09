# R04 根审查补充学习

本轮重新实际读取 [Strands 固定 RL 文档](https://raw.githubusercontent.com/strands-labs/robots/4d0203161a587e29d7912c99da74878e8f989544/docs/training/rl.md) 和 [UniIntervene 固定 README](https://raw.githubusercontent.com/Denghaoyuan123/UniIntervene/40f461f97573383c9cc8fdba43df56f9eb5bbea1/README.md)，继续检查“通用框架”与“现成学习链”的区别。

Strands 的 SimEnv、PPO/FastSAC、单 MuJoCo 环境和 reward-driven from-scratch 路径，支持研究报告将它列为工程挑战者，但不能由此声称已有本项目 VLA＋demo／纠正＋队列 RL。其部署接口按 action keys 而非关节数量绑定，说明跨本体能力描述需要动作语义而不只是维度；本项目 T01/T37 已有对应要求。

UniIntervene 公开七阶段离线算法，明确排除部署和 HIL-SERL 集成，恢复记忆来自训练集，不使用验证／测试 episode 建记忆。当前方案的经验复用与独立审计集分离相容，未把算法开放当成无人持续学习完整栈。

输入与R03相同，没有修改冻结科学文档。文档／链检查器修正了“未结束轮次应显示pending而不是清零既有通过数”的元数据处理，并检查每轮三名不同新agent、报告存在及问题数下限；这些检查不自动判论文或算法通过。根审目前无新必要问题，待独立审查完整合并。


## 合并判断与再学习

最终判定 NEEDS_REVISION，连续通过归零。RL 12问、Harness 13问通过，证据12问提出必要问题：RT-EXPO 的附加状态及历史布局未充分反映在效果条件与公平比较协议。根审重新读取原文 VII-D.3–4，确认信息提供给 critic、noise-Q filter 和编辑器，基础 VLA state 不变，Ball Balancing 图像布局另有变化。这不是外部仪器真值，却会影响样本效率与算法归因。

已修订 VLA 专题、总报告和技术方案／T34：按模块记录因果可见信息、来源／可用时间和生成成本，做共同信息对照或输入消融。另统一确定性 actor 措辞，澄清 RPent 新差异仅做选定范围复核。均属新版本，R03通过不能累计到新版本；将重新冻结后开始三轮连续独立审查。
