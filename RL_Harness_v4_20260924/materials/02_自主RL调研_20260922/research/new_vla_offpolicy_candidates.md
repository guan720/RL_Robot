# 弱初始 VLA 下的较新 off-policy 候选专项审核

核验日期：2026-09-22。范围限定 GR-RL、ALOE、VLA-Precision；只读原论文、作者项目、官方训练仓库。未执行机器人实验，也未复现性能。适用条件：松灵 ALOHA 类双臂，pick-and-place，当前任务初始成功可能近零，可采成功示范并在线接管，不考虑 ACT。

## 审核判断

三项工作都不足以证明存在一条“比 HIL-SERL 更成熟、无需任务能力、直接支持松灵 π0.5”的替代路线。**ALOE 在学习目标上更接近需求；VLA-Precision 在现成 π0.5 工程实现上更具体；GR-RL 不适合作为当前冷启动主基线。** 新论文与强机构不能代替独立复现证据。

| 候选 | 更新对象 | 与错误参考动作的关系 | 当前建议 |
|---|---|---|---|
| GR-RL，2025-12 | 冻结基础 VLA，训练潜空间噪声预测器与 critic | 不直接做参考动作 L2，但限制噪声偏离原高斯先验；依赖已有动作分布 | 排除当前主基线 |
| ALOE，2026-02 | 端到端后训练 π0.5，优势加权 flow matching | 约束到持续增长的混合回放数据分布，并非冻结旧 VLA 的单个动作 | 优先方法参照，但缺公开训练代码证据 |
| VLA-Precision，2026-09 | Stage I 全参 SFT；Stage II 更新 π0.5 action expert 内的 LoRA | 明确存在对冻结 Stage-I 参考动作的 L2 | 工程候选，须修改/检验参考约束，不能直接解决本轮疑虑 |

## GR-RL：强机构，前提不匹配

ByteDance Seed 技术报告。在线训练前，过滤示范和对称增强已把离线成功率提高到 72.7%；随后用 673 条策略 rollout 预热。在线更新的是噪声预测器，带噪声范数阈值惩罚；作者特意不把遥操作数据混入在线回放。它不是从近零任务能力启动的证据，也不是靠随时接管补足动作覆盖的 HIL 路线。官方页面未发现完整训练代码入口。方法事实见[论文 §3.3、§5](https://arxiv.org/html/2512.01801v3)，机构及发布见[Seed 官方页](https://research.doubao.com/en/gr_rl)。

## ALOE：参考对象是回放数据，而非固定坏动作

2026-02-13 预印本，AgiBot、复旦、HKUST 等合作。方法使用动作块 TD critic，按优势给回放中的实际动作加权，端到端更新 π0.5。理论中仍有对隐式行为分布的 KL 约束，所以不能称为“无约束”。但这个行为分布由成功、失败和人类纠正共同构成，能随新增有效数据改变；与始终贴近冻结旧 VLA 动作有实质区别。真机包括双臂分拣；该任务初始 50 条成功示范，论文明确人工复位。见[论文算法 1、式 13–15、附录表 III](https://arxiv.org/html/2602.12691v1)。

作者项目展示早期接管比例 81.2%，随后下降。这说明少量初始化并不免除早期人工成本。本次核验项目页的全部 GitHub/arXiv 链接，只找到论文，未找到完整官方训练仓库；不把“项目主页公开”写成“算法已开源”。见[作者项目页](https://rooshy-yang.github.io/aloe/)。

判断：适合指导“π0.5＋接管回放＋直接 VLA 更新”的设计，但目前不能比有完整代码的 HIL-SERL 更快落地。缺少有效成功/纠正片段时，优势加权也不能凭空创造缺失技能。

## VLA-Precision：代码较完整，但仍有 reference L2

首发 2026-09-03，最新核验 v3 为 2026-09-18；中科大、精密与智能化学国家重点实验室、北航等合作，当前核验为预印本。在线只训练 π0.5 action expert 的 LoRA，冻结前缀与原 action expert 权重；不是额外的 residual actor 或替换掉 VLA 的小策略。Stage I 使用每任务 60–120 条示范。式 14 明确约束当前身体动作接近冻结 Stage-I 参考，式 15 再合并行为克隆和相对优势 RL。见[论文 v3 §III-A/B/D、表 II](https://arxiv.org/html/2609.04355v3)。

不能把独立 SFT 对照的 67.8% 平均成功率说成该方法精确初始成功率：二者示范数量和 SFT 步数不同。其 98.3% 结果也不能直接推导对当前松灵抓放优于 HIL-SERL。低终局成功可能仍有较完整的接近、抓取与操作行为，不能与完全没有当前任务动作覆盖混为一谈。

**开源核查：**[官方仓库](https://github.com/scy-v/VLA-Precision)采用 Apache-2.0，README 公布 2026-09-06 释放代码。核验 GitHub API 快照为 80 stars、8 forks，创建 2026-09-02，最近 push 2026-09-18。stars/forks 不是独立真机复现次数；本次未发现可靠独立复现报告。

仓库提供 Stage-I 训练与 Stage-II actor/learner/机器人服务入口：`main.py --stage stage2 --mode train --role learner`；实际更新实现为 `ACoBAgent.policy_loss_fn` 与 `_update_impl`。当前机器人注册为 UR5e、dual UR、Franka，仍需松灵适配。[配置文档](https://raw.githubusercontent.com/scy-v/VLA-Precision/main/docs/CONFIGURATION.md)。

**代码确认的约束：**`acob/agent.py` 的约 688–703 行计算当前动作与冻结参考动作的平方误差，`ref_weights` 为全 1，随后加到 actor loss；不是只在参考可靠时约束。[核心代码](https://raw.githubusercontent.com/scy-v/VLA-Precision/main/src/vla_precision/acob/agent.py)。示例配置为 flow 0.25、improvement 0.50、reference 0.25，且成功判定是 manual。[任务配置](https://raw.githubusercontent.com/scy-v/VLA-Precision/main/configs/stage2/tasks/insert_two_bottles_diagonal_rack.yaml)。

## 可借鉴的改进方向（本次提出，尚无本机验证）

1. 先用有效示范/纠正建立任务动作覆盖；无需等待高成功率，但至少区分“偶尔抓取后放置失败”和“从不接近正确物体”。
2. 保留人类成功/纠正动作上的监督，不对失败状态无条件贴近旧 VLA 参考动作。
3. 比较参考项关闭、减弱、按独立验证的可靠性开启三种形式。不要只把早期不可靠 Q 值作为唯一开关；否则错误 critic 可能同时控制目标和约束。
4. 若采用 VLA-Precision，可单独调整 `actor_reference_weight`，仍保留 flow 数据监督和 critic 校准；这属于改进实验，不能沿用原论文成功率保证。
5. 若采用 RLT token＋HIL-SERL 机制，应明确这是自建组合。可以共享 VLA 表征并让 actor 输出完整动作，使用成功/接管回放提供行为依据；免除固定错误动作锚定不代表免除示范需求。

研究结论：目前更合理的是保留 HIL-SERL 的接管/回放/异步学习机制作为可靠工程基础，按 VLA 的动作块与更新对象适配。ALOE 提供更贴合的学习目标参考，VLA-Precision 提供较新的 π0.5 代码参考；两者都尚不足以把既有工程路线直接替换成“已验证更优”的方案。
