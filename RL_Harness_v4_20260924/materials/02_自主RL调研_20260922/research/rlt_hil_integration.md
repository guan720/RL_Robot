# RLT 与 HIL-SERL 的组合可行性审查

核验日期：2026-09-22。范围：松灵 ALOHA 类双臂、pick-and-place、任务基础 VLA 可能接近零成功、有少量遥操作示范与接管。仅研究设计，未实施训练。用户明确排除 ACT。

## 判断

**组合成立，但更准确的方向是“VLA/RLT 表征与动作头 + HIL-SERL 的示范/接管学习机制”，不是把两个完整训练系统叠起来。** 原始 RLT 已经包含接管与离策略回放。新增价值应聚焦弱策略启动、示范保障、错误动作先验去束缚及正反循环，而不能把已有接管机制当作新创新。

推荐以 RLinf 的 π0.5/RLT 实现为一个工程母体，适配松灵的数据和控制接口，吸收 HIL-SERL 的数据组织与奖励采集。原版 HIL-SERL 的像素 agent 并非现成 VLA agent；其 RL 系统思想与 VLA 表征没有根本冲突，但“配置换个模型名即可训练 π0.5”没有代码依据。

## 已核实的原始事实

- RLT actor 输出完整动作 chunk，以 token、本体状态、VLA reference 为条件，并有趋近 reference 的约束；它不是强制 `VLA 动作 + 有界残差`。论文原型是 π0.6，先进行每任务 1–10 小时遥操作适配，在线训练主要集中于困难阶段。论文已有 reference dropout、接管回放和稀疏人工成功标签。因此，它没有验证“几乎不会当前任务、只有极少示范”也能直接快速自学。[RLT 原文](https://arxiv.org/html/2604.23073v1)
- RLinf 已提供 π0.5 的 token/SFT 阶段与冻结特征的小 actor-critic 阶段，现成真机入口面向 Franka；在线阶段不更新大 VLA。[实现文档](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/rlt.html)
- HIL-SERL 的采集端将接管后实际动作写入 transition；接管数据也进入示范池，训练批次有示范/在线各半的采样。这个机制可复用，但比例只是基线配置，不是任何任务都最优。[训练入口](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/examples/train_rlpd.py)
- HIL-SERL 默认 launcher 使用 ResNet 编码器；双臂 hybrid agent 的连续臂动作与离散夹爪动作分开学习。它与 VLA 的关节位置/连续夹爪序列必须显式对齐。[launcher](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/serl_launcher/serl_launcher/utils/launcher.py)、[双臂 agent](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/serl_launcher/serl_launcher/agents/continuous/sac_hybrid_dual.py)

## 可复用与需改动之处

| 模块 | 可复用内容 | 必须处理的接口 |
|---|---|---|
| 表征 | VLA 编码与 RLT token，保留语言/机器人先验 | 当前任务低成功不等于表征无用，也不证明表征充分；必须检查抓取状态、物体位置、目标区是否可辨 |
| 在线学习 | 小 actor/critic、目标网络、异步 actor/learner、off-policy replay | 一套训练框架内实现，避免 PyTorch RLinf 与 JAX HIL-SERL 双框架互相管理状态 |
| 人工学习 | 成功示范、接管轨迹、单独示范池、持续回放 | 普通 DAgger 的 observation-action 对未必带 reward/next_obs/done，不能无加工当 RL transition |
| 奖励 | HIL-SERL 的奖励分类器采集/校验流程 | pick-and-place 成功需区分“夹爪经过目标区”与“物体已释放且留在目标区”；反向有独立目标 |
| 动作 | RLT 的完整 chunk 输出 | 松灵关节顺序、单位、绝对/增量动作、归一化、控制频率与人类接管须同一语义 |
| 夹爪 | 示范提供开闭时机；可选混合动作学习思想 | 不直接把 HIL-SERL 夹爪 DQN 插入连续 VLA chunk；需统一执行语义或单独设计并消融 |
| 正反目标 | 同一 VLA 提取表征，分别学习方向 | 目标必须进入 actor 与 critic。原 RLT 固定任务可省语言的做法，不能照搬为无目标双向头 |

## 弱 VLA 的主要问题及拟议改动

下面是本会话的工程/研究建议，不是已经由 RLT/HIL-SERL 在松灵证明的结果。

**保留知识先验，不强制模仿错误动作先验。** VLA 的图像语言表征可以继续使用；失败动作 reference 的约束强度应独立可调。仅把 actor 输入中的 reference dropout 设大仍不够，因为 BC loss 可能仍拉向原 reference。

第一版建议：先用少量成功示范做任务 SFT 与 token 训练，同时用这些示范预热小动作头；以示范/接管动作作为可信 BC 目标。对自主样本的 VLA reference BC 权重设置为单独参数，从零或较低权重开始比较，不能把监督人类动作的权重一起降掉。初始化 critic 不可靠时，不用它自行判断哪一条人类示范“值得学习”；先保留明确采集的成功示范，再检验是否需要价值筛选。

这会把任务技能的主要冷启动来源从“原 VLA 已经会做”改为“预训练表征 + 当前任务成功示范 + 接管补充”。它是合理但需要验证的泛化设计，不能保证原论文的数据效率或保留全部 VLA 泛化。

如果原 VLA 连到达抓取附近都做不到，不能保留“基础 VLA 完成前段、小头只练最后一段”的默认流程；应让示范预热后的头覆盖完整抓放，或明确记录前段由人工辅助的训练分布。后者不算无人自主成功。

## 重要代码细节：reference 与人类动作目前并未完全分离

RLinf 的 `fsdp_rlt_ac_policy_worker.py` 已有接管动作 BC、示范池入库以及 BC/Q 权重调度。其 `_bc_metrics` 根据 human mask 在实际动作和 reference 之间选择目标。[actor worker](https://raw.githubusercontent.com/RLinf/RLinf/main/rlinf/workers/actor/fsdp_rlt_ac_policy_worker.py)

但不能据此声称 actor 的 reference 输入始终是原 VLA 输出：

1. `transition.py` 的 `apply_rlt_interventions()` 会将 observation 中的 `ref_chunk` 覆写为实际接管动作。[transition](https://raw.githubusercontent.com/RLinf/RLinf/main/rlinf/algorithms/rlt/transition.py)
2. `embodied_types.py` 的 RLT transition 提取分支调用该函数，输入环境的 `intervene_actions` 和 `intervene_flags`。[trajectory schema](https://raw.githubusercontent.com/RLinf/RLinf/main/rlinf/data/schema/embodied_types.py)
3. 仿真专家接管的 `SimulatorRLTRoute` 也覆写 `forward_inputs['ref_chunk']`。[route](https://raw.githubusercontent.com/RLinf/RLinf/main/rlinf/algorithms/rlt/route.py)

这遵循原论文的人类 reference 替代机制，并有 reference dropout；不能未经实验定性为 bug。但对于弱 VLA 的启动，训练时借人类 reference、部署时借弱 VLA reference 的差异值得审查。

拟议实现把 `vla_ref_chunk`、`executed_chunk`、`human_target`、逐步 `human_mask` 分开：actor 的条件输入来自部署时可获得的信息；BC target 可使用人类动作。将它与原实现作对照，而不是无说明改写后仍称为原版 RLT。

## 不能直接混合的训练语义

**动作 chunk 与接管。** HIL-SERL 默认单步 transition 不能直接填入 RLT chunk critic。以真正执行的 K 步计算累计折扣奖励，并使用 `gamma**K` bootstrap；终止、超时与中途接管必须有明确语义。接管可在 chunk 内抢占，不能为了凑满固定序列而延迟接管。第一版可保留固定短 chunk、逐步控制来源/实际动作和有效长度 mask；若切成变长序列，需要 critic 也显式支持长度与 padding mask。不能将被中断后未执行的原动作序列配给真实 next_obs。

**SAC 与 RLT 目标。** HIL-SERL SAC 的 actor 有熵/温度项；当前 RLinf RLT 明确关闭 alpha 学习，使用固定噪声、Q 与 BC 目标。第一版保留 RLT 目标即可吸收 HIL 数据机制，不必引入第二套目标。若要改成 SAC，需连同分布 log-prob、tanh Jacobian、动作维度对应的熵尺度和 chunk 时间尺度一起处理，不能仅把 alpha 打开。[HIL-SERL SAC](https://raw.githubusercontent.com/rail-berkeley/hil-serl/main/serl_launcher/serl_launcher/agents/continuous/sac.py)、[RLT 动作头](https://raw.githubusercontent.com/RLinf/RLinf/main/rlinf/models/embodiment/mlp_policy/rlt_mlp_policy.py)

**表征更新与历史 replay。** 一个在线轮次先冻结 VLA/token，保证缓存的 token 有固定含义；若之后用新示范更新 VLA，应保留原始图像/语言/状态并重算历史表征，或明确隔离版本。只保留旧 token、同时在线更换 encoder 会制造不可见的状态分布变化。

## 建议最小对照与交付顺序

1. 同一数据预算下跑任务适配的 VLA SFT/DAgger，作为 VLA 内部基线；不用 ACT。
2. 原版 RLT 加相同示范/接管数据，评估实际能否启动。
3. RLT 表征 + 示范预热的小头 + 独立人类 BC / 弱 reference 约束，保持其他条件相同。
4. 比较原 reference 替代机制与“部署可得 reference、监督目标分离”机制；若后者没有收益，不增加复杂度。
5. 两方向分别达到可用水平后接入往返；失败恢复单独统计。先比较独立头，再检验共享头的正迁移。

评价需同时报自主成功率、每成功任务累计人工秒数、接管率、复位次数、训练机器人时间及 SFT/标注成本。若只有 token 头提升、原 VLA 冻结，就报告“VLA 支持的系统能力提升”；后续再蒸馏回 VLA 才能报告基础模型权重获得任务增益。

所有开源文件均以 2026-09-22 检视的公开 main 为准，main 会变化；正式实施应固定提交版本。本文未声称现成松灵双臂复现，也未将组合方案作为已发表新方法。
