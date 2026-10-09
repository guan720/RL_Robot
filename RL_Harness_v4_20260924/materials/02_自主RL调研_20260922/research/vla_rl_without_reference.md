# 不依赖固定 VLA 参考动作的 RL：SAC Flow / 两个 FPO 的有界核验

核验日期：2026-09-22。用户边界：VLA-only；松灵双臂平台、首任务只用单臂；当前抓放策略成功率偏低，包括零成功率，可经过少量 SFT；可提供少量成功示范和人工接管。目标为自学习达到任务可用要求。此文件是候选排查，不是复现结论。

## 结论

**本次没有找到可以凭现有证据直接取代 RLT、同时满足“π0.5 真机、少量示范近零启动、无需固定初始动作锚、开放可复现”的 SAC Flow/FPO 方案。** 它们提供了有用的优化方法，但不应把“能训练 flow 策略”扩大成“已能低成本训练松灵双臂上的 VLA”。

用户对错误初始参考动作的担忧合理，但应分别审查：固定参考动作正则、上一次策略的信赖域、示范/回放动作正则、冻结动作解码器的表达范围。这四者不是同一种约束。去掉固定初始参考动作，不等于删除所有稳定学习的约束，也不保证解决无成功信号。

## 候选结果表

| 候选 | 确认的模型/训练对象 | 真机与冷启动证据 | 开放/机构与发表 | 对当前任务的判断 |
|---|---|---|---|---|
| SAC Flow | 小型 Flow-G/Flow-T；直接离策略训练该 flow actor | 本文实验为 MuJoCo、OGBench、Robomimic 仿真；没有 π0.5 真机实证 | 官方代码可访问；清华、CMU、理想、上海 AI Lab；ICLR 2026，预印本 2025-09 | 可作为未来可训练 flow 头的算法参考，不能直接升为主基线 |
| FPO：Flow Matching Policy Gradients | 通用 flow policy 的 on-policy 策略梯度 | 官方公开实验是通用控制/人形仿真，不是 VLA 抓放 | Berkeley/Max Planck；ICLR 2026；官方代码，2025-07 起公开 | 方法可信，但 π0.5 真机接管/数据复用工程证据不匹配 |
| FPO：Reinforcement Fine-Tuning of Flow-Matching Policies for VLA | **冻结 π0 decoder，只更新 flow latent actor 与 critic** | LIBERO/ALOHA-sim；ALOHA 初始成功约 40%，不是近零 | 中科院作者团队；arXiv v2 标注 ICRA 2026 accepted；此次未定位官方训练仓库 | 仍受冻结 decoder 可达行为影响，不是解冻 VLA 动作头方案 |
| ARFM，补充核查 | 直接对 VLA flow 模型做优势加权离线后训练 | 有 UR5 抓放真机评价；在线交互学习被列为未来工作 | 西湖、浙大、UCLA、西交；AAAI 2026；未定位完整官方训练仓库 | 更适合经验回流更新，不能充当当前在线学习/接管框架 |

表中“未定位”仅表示此次原论文、作者项目和定向检索未找到，不能据此宣称永远不开源。

## 1. SAC Flow：确实直训 flow，但不等于直训现有 VLA

其核心是改造速度网络，使跨 flow 积分步骤反传更稳定，再使用 SAC。原实验的 Flow-T 使用小规模 Transformer，不是 π0.5 的动作专家。官方项目也明确指出稀疏奖励从零学习失败，离线数据启动很重要；Robomimic 使用约 300 条多操作者轨迹。论文离线到在线版本仍保留向回放动作靠拢的正则，且线上权重不为零。因此，“无固定 VLA 参考动作”成立的程度，与“完全无 BC 锚”必须区分。[作者项目](https://sac-flow.github.io/)、[论文附录 C/D](https://arxiv.org/html/2509.25756v1)

源码进一步确认：`online_actor_loss` 包含实际 batch action 的均方误差和 Q/熵项；没有把该项自动变成对 π0.5 的训练。公开运行入口是仿真脚本。[官方 README](https://raw.githubusercontent.com/Elessar123/SAC-FLOW/master/README.md)、[actor 实现](https://raw.githubusercontent.com/Elessar123/SAC-FLOW/master/offline-to-online/agents/acfql_transformer_ablation_online_sac.py)

**工程推断：** 若将 VLA token 接到新建 Flow-T actor，可以得到 VLA 表征驱动的 flow RL policy；若直接修改 π0.5 原动作专家，又涉及结构、权重兼容和梯度稳定性的重新验证。两者都不是当前论文已经交付的 VLA 真机训练流程。

## 2. 两个 FPO 必须分开

### 2.1 Berkeley 的 Flow Matching Policy Gradients

此 FPO 已在 ICLR 2026 官方论文集出现；它用 flow-matching 损失构造 PPO 类更新。约束主要针对每次更新相对于上一版行为策略的幅度，不是永远复制初始 VLA 的动作。官方代码目录覆盖 Gridworld、MuJoCo Playground 与 PHC。没有在这些入口中找到 π0.5、松灵双臂或真机接管训练配方。[正式论文集](https://proceedings.iclr.cc/paper_files/paper/2026/hash/3d43cc5692bf68944ee7cd31b97d0c11-Abstract-Conference.html)、[官方代码说明](https://raw.githubusercontent.com/akanazawa/fpo/main/README.md)

**工程推断：** 该优化思想可以研究，但 on-policy 更新通常不能直接把任意旧示范/人类接管塞进策略梯度项；需要额外 BC 或明确的 off-policy 修正。以少量真机交互启动时，算法的表达自由度不是唯一问题，成功轨迹来源和数据复用更重要。

### 2.2 面向 π0 的同名 FPO

最新 v2 的 §III-A、Algorithm 1 和实验设置明确写出：base decoder 冻结，更新 flow latent actor 与 ensemble critic。不能因为标题写“VLA fine-tuning”，就把它归类为直接更新 VLA 原动作头。ALOHA-sim 学习曲线从约 40% 开始，该数值仅说明作者仿真条件，不能据此判断与用户不同任务的适配性。此次未找到其官方源码；冻结 decoder 的动作覆盖、仿真到真机迁移和实现透明度才是这里需要核查的限制。[最新论文](https://arxiv.org/html/2510.09976v2)

作者于 2026-06-25 更新 arXiv，页面标注已接收 ICRA 2026；本次确认的是作者原始提交声明，未另查 IEEE proceedings。[arXiv 元数据](https://arxiv.org/abs/2510.09976)

**判断：** 它没有通过本次“原 VLA 头可更新、真机弱先验”的筛选，不能用来消除用户对基础动作可达范围的担心。

## 3. ARFM：更像经验回流备选

AAAI 正式页面确认 2026-03-14 发表及作者机构。它对 flow 训练数据按优势加权并控制梯度方差，有 UR5 三类抓放任务评价。但方法是离线 RL；原文结论把在线交互后训练列为未来方向。少样本表格主要是 LIBERO 的 10/20/30-shot，不能当成松灵真机“20 条示范后无人在线训练”的证据。[AAAI 正式出版页](https://ojs.aaai.org/index.php/AAAI/article/view/38944)、[原论文](https://arxiv.org/html/2509.04063v1)

**判断：** 可用于收集到成功/失败/纠正数据后直接更新 VLA 的对照，不替代成功判定、在线探索、接管和正反恢复调度。

## 4. 开放与影响力的实际边界

- 2026-09-22 页面快照：SAC Flow 官方仓库约 **69 stars / 8 forks**；Berkeley FPO 约 **470 stars / 24 forks**。这是代码关注度，不是论文引用量，更不是独立真机复现。[SAC Flow 仓库](https://github.com/Elessar123/SAC-FLOW)、[FPO 仓库](https://github.com/akanazawa/fpo)
- 这两个页面此次未显示明确根 LICENSE 条目，故只确认公开代码可读，许可应在采用时单独核实，不把“公开”直接写成“明确许可的完整开放交付”。
- 没有审计到上述方法在松灵双臂近零抓放上的独立复现。本次也未获取稳定可信的引用计数；不填估计数字。
- ReinFlow 虽是另一个可参考的 flow-RL 实现，官方 README 当前宣称支持 π0/π0.5，但明确表示不适合从零训练、面向微调；不能仅凭支持列表替代真机证据。它不是此次提出的新主推荐。[官方说明](https://github.com/ReinFlow/ReinFlow)

## 5. 对主方案的具体含义

这里更值得做的是清楚定义学习目标，而不是更换一个“更无约束”的新算法名字：

1. **若目标是组合系统迅速学会任务：** 保留 VLA token、小 actor/critic 和可靠人类数据；在实验中取消固定初始 VLA 动作正则，但保留示范/可靠纠正的 BC，允许权重随有效在线数据增多而下降。这已超出原版 RLT，需要与原版对照，不应宣称无条件更稳。
2. **若目标是基础 VLA 自己获得新技能：** 必须加入 VLA 权重更新。可以先让轻量 actor 学会，再将可靠经验回流 VLA，或选择有真机证据的直接 VLA 后训练路线。其代价是每次更新和评估周期更长，且需要确认旧表征缓存的版本一致性。
3. **若完全不想受初始动作先验束缚：** 最应保留的是成功示范及实际纠正，而不是弱基础策略的输出。真实任务没有成功或接近成功的经验时，去掉约束只会扩大搜索空间，不会制造有效学习信号。

这三个设计决定应先于“是否改用 SAC Flow/FPO”。就已核实证据而言，它们没有形成一条比 RLT/HIL 数据流程组合更完整的松灵 VLA 弱先验真机交付路线。
