# 真机 RL 分支对 VLA 与 reset 候选的独立交叉审查

审查日期：2026-09-22。只读审查 `vla_candidates.json` 与 `reset_candidates.json`，没有修改原文件。逐行阅读两份候选表，并重点回到 PLD/ENPIRE、Robometer、ReLMM、MEDAL++、DenseReward 的论文、仓库和许可原文核查。本文件不声称对全部 26 项重新独立复现或逐文件审计。

当前表格已较好地保留训练自主性、人工复位、部署演示与代码范围的差别。没有发现需要推翻整体 shortlist 的新重大错误；存在两项开源许可范围应细化，以及三项最终摘要必须保留的数字口径。以下为发现和确认结果。

| 事项 | 审查结果与建议 | 对选型的影响 |
|---|---|---|
| Robometer 两个仓库的许可 | `robometer-policy-learning/main/LICENSE` 已直接打开，是 MIT。`robometer/robometer/main/LICENSE` 仍返回 404。原行“README MIT 徽章但根 LICENSE 404”容易让读者误以为两仓都没有许可正文，应拆开描述。 | policy-learning 可按已核实 MIT 记分；奖励主仓许可正文缺口独立保留，不能把 HF 模型 Apache-2.0 自动套到代码。 |
| ReLMM 许可待精读项 | `master/LICENSE` 与 `real_robot/LICENSE` 已分别读到 MIT，包含 Softlearning 各贡献者版权说明。机器人依赖仍分别遵循其条款。 | 可消除这两个分支根许可“未知”，但不会自动改善旧机器人栈的可运行性。 |
| ReLMM 评估分母 | Table 1 每环境训练一次、评估三次；指标为 15 分钟拾取对象比例。AutoCurr 只报告两个真实环境，StatCurr 报四个环境。现表未误报分母，最终矩阵需保留此差别。 | 不能拿 StatCurr 四环境分数来证明 AutoCurr 在四环境均已验证；不能与机械臂单回合成功率直接排名。 |
| Robometer 评估与倍数 | 两任务均为 20 次评估，单任务 85/55、双阶段 70/20 的对照数准确。论文“平均约 2.5×”是按任务比值平均；先合并任务再计算比值约为 2.07×，不是同一量。 | 建议最终只列原始成功率和 n=20，不用宣传倍数排行。 |
| MEDAL++ 检查点选择 | 原文明确评多个中间 checkpoint，报告最优 checkpoint 的 50 次评估。当前 JSON 已写 best checkpoint，数字匹配。 | 保留此词，不将数值包装成最后一个 checkpoint 的稳定成功率或独立多种子均值。 |

许可证据：[Robometer policy-learning MIT](https://raw.githubusercontent.com/robometer/robometer-policy-learning/main/LICENSE)、[奖励主仓 LICENSE 路径（本轮 404）](https://raw.githubusercontent.com/robometer/robometer/main/LICENSE)、[ReLMM master MIT](https://raw.githubusercontent.com/charlesjsun/ReLMM/master/LICENSE)、[ReLMM real_robot MIT](https://raw.githubusercontent.com/charlesjsun/ReLMM/real_robot/LICENSE)。数字证据：[Robometer §IV-Q3、Appendix E](https://arxiv.org/html/2603.02115v1)、[ReLMM §6 与 Table 1](https://proceedings.mlr.press/v164/sun22a/sun22a.pdf)、[MEDAL++ p.7 Training and Evaluation](https://proceedings.mlr.press/v229/sharma23b/sharma23b.pdf)。

## PLD / ENPIRE 的重点确认

当前 PLD 行已正确补充相关官方实现，因此不要再改回“PLD 没有开源代码”。ENPIRE README 明确支持真实 actor/learner，所链接 runtime README 指明从 `minimal_policy@81988f0` 迁入，并给出 `enpire rl learner --task pin_insertion` 和 actor 命令。它是可核验的相关官方 PLD 真机训练实现；这不自动证明 PLD 原论文所有任务、原始数据、权重和 SFT 蒸馏飞轮均已一比一发布。[ENPIRE 官方仓库](https://github.com/NVlabs/ENPIRE)、[PLD runtime 原文](https://raw.githubusercontent.com/NVlabs/ENPIRE/main/enpire/policy/pld/runtime/README.md)

ENPIRE 的自主研究依赖已准备的物理实验站。官方要求每个新环境先提供并验证 reset 与 reward/verification 函数，后续研究迭代保持这些边界固定。应把它放在“可组合的具身 harness + 学习实现”位置，不能直接称任意新环境自动获得物理复位和可靠奖励。[ENPIRE custom environment setup](https://github.com/NVlabs/ENPIRE#set-up-a-custom-real-world-environment-for-auto-research)

PLD 的两个真机自主性层次应分开：Franka 开始前有 200 条遥操；cube 借助 3D 打印桌面，可自动复位、RL、SFT；peg 为增加多样性仍需人移动孔位。YAM GPU 循环的“至少 1 小时无人帮助”对应分阶段 RL 后蒸馏出的 BC 策略持续执行；每子任务训练预算最多 8 小时。不能改写成“所有任务训练全程无人、从零无人、训练 1 小时”。当前表格这些限制均已保留。[PLD §4.4 与 Appendix D.1](https://arxiv.org/html/2511.00091v1)

## 自主性与结果归属的确认

- **Robometer**：原文明确自动化的是奖励、终止和阶段推进，物理场景仍人工复位。10k 环境步约 40 分钟的记录准确；该时长不能认定为连续无人学习时长。当前表分类正确。[原论文 Figure 6、Appendix E.2](https://arxiv.org/html/2603.02115v1)
- **ReLMM**：Stationary curriculum 的约 5% 人工推回物体只属于该课程；AutoCurr 避开此步骤，但整个实机流程仍约每 5 小时换电，期间可能归还卡边角物体。累计 25–50 小时不能改写成同等时长连续无人；当前表正确保留这些边界。[原论文 §4.3、§6](https://proceedings.mlr.press/v164/sun22a/sun22a.pdf)
- **MEDAL++**：每任务 50 正向与 50 反向演示、最初 30 分钟人工增加复位多样性、之后平均约每小时人工复位与 30 小时总训练相符。它适合作为可学习恢复的参考，不能因标题 Self-Improving 就升级为无需现场帮助。[原论文实验设置](https://proceedings.mlr.press/v229/sharma23b/sharma23b.pdf)
- **DenseReward**：20k/10k steps 对应约 20/10 条 rollout 是论文原文，不是调研者换算；代码未公开且时步语义没有完整说明时，应按作者口径记载，不推算墙钟或数据效率。40→80 与 30→70 是有无该奖励的 DSRL 对照，各只有 10 次评估。现表处理正确。[原论文 §4.4](https://arxiv.org/html/2607.13033v1)
- **表级检查**：RECAP、RLinf-USER、ConRFT、SimpleVLA-RL、GR-RL、GigaBrain-RAMP、GRAPE、RL-100、RoboReward 以及其余 reset 行，文本都已明确相应人工/仿真/部署与发布范围限制；本次没有逐篇再次独立验证全部数值，因此保留原调研置信度，不提升为“已复现”。SOAR、REVOLVE 当前明确是 BC/监督学习或 harness 参照，未错误归为 RL 优化算法；RISC、MoReFree 当前明确以仿真证据为主。

## 给汇总文件的直接修改建议

1. 将 Robometer `open_source` 的许可句改为：“policy-learning 仓 MIT LICENSE 已核实；奖励主仓 README 标 MIT，但根 LICENSE 路径本轮 404，需独立澄清；HF 4B 模型 Apache-2.0。”
2. ReLMM 主仓许可从“待精读”升级为“master 与 real_robot 分支根 MIT 已分别核实”，各依赖单列。
3. 对 PLD / ENPIRE 保留“相关官方 runtime 已开放，但全部原论文资产完整性未证实”；对 Robometer 的 n=20、ReLMM 的单训练/三评估及课程分母、MEDAL++ 的最优检查点做脚注。
4. `reset_candidates.json` 中部分文本含字面 `\\u003e` / `\\u003c`，JSON 本身合法，但渲染表格时宜显示为 `>` / `<`，避免用户阅读到转义串。这是呈现问题，不改变研究结论。

审查未克隆或运行机器人控制代码、未下载大型模型/数据，所有许可结论仅覆盖具体已访问文件。未更改知识库或其他调研分支文件。
