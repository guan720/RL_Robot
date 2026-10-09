# 更新基线核查：RLinf / verl-vla 的真机与松灵支持

核查日期：2026-09-22。仅查阅原始论文、项目、官方仓库与文档；未安装、未训练、未操作机器人。GitHub `main` 及 `latest` 文档是动态快照。

## 对当前选型最重要的结论

1. **RLinf 的 RLT 实现值得列入比 DSRL 更新的候选。** 原方法是 PI 的 2026 年 RLT，RLinf 在 2026 年 7 月宣布支持，目前有 π0.5 + Franka 真机两阶段配置和训练流程。这是 RLinf 团队的实现，不应说成 PI 原作者完整代码已开放，也不能把“有代码配置”称为我们完成了复现。
2. **RLinf-USER 与 verl-vla 是基础设施，不是取代 DSRL 的单一学习算法。** 选择它们之后仍须选择 RLT、DSRL、RECAP 等优化方式。
3. **没有发现这两套框架提供已验证的松灵双臂 π0.5 自主 RL 闭环。** RLinf 的 Piper 文档反而明确说明当前只提供硬件检查、尚无受支持的真机任务或训练工作流。verl-vla 宣称的 Piper 支持集中在键盘遥操作和数据录制；公开 RL 参考结果均在仿真。
4. 两者均不能自动解决正反任务循环。任务方向条件、成功/失败判定、恢复范围、双臂接口、终止与切换规则仍需实现并验证。

## RLinf-USER：原论文与当前工程能力应分开

原论文 2026-02-08，作者单位包括清华大学、中关村学院、无问芯穹、北京理工大学、浙江大学、上海人工智能实验室。项目文档标记 RSS 2026。代码仓库采用 Apache-2.0，机构和公开工程积累可作为可持续维护的积极信号，不代表无需平台适配。

原论文的 VLA 真机实验是 π0 + HG-DAgger；CNN / 小型 flow 模型才分别运行 SAC、RLPD、SAC-Flow。瓶盖与抓取放置任务仍用人工奖励及人工复位，固定插孔任务可自动复位。因此不能将论文里的 π0 成功率提高说成“π0 已通过自主 RL 免人工学习”。

- [论文及附录](https://arxiv.org/html/2602.07837v1)
- [项目文档](https://rlinf.readthedocs.io/en/latest/rst_source/resources/publications/rlinf_user.html)
- [官方仓库](https://github.com/RLinf/RLinf)
- [仓库许可](https://github.com/RLinf/RLinf/blob/main/LICENSE)

### 当前 RLT + π0.5 路线

流程是：首先以示范联合训练 VLA 与 RLT token 特征模块；然后冻结这一特征模型，在线训练轻量 actor/critic。第二阶段观察包括紧凑特征、本体状态、VLA 参考动作块。RLinf 文档明确说明当前第二阶段不是标准最大熵 SAC，其 actor 目标结合 Q 优化与 BC 约束，普通步参考 VLA 动作，人工接管步参考人类动作。

已核查实际文件而非只看支持列表：

- [RLT 官方框架文档](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/rlt.html)
- [Franka 第二阶段配置](https://raw.githubusercontent.com/RLinf/RLinf/main/examples/embodiment/config/realworld_rlt_stage2_ac_mlp.yaml)：`type: Franka`、`pi05_franka_state`、7D action、`rlt_mlp_policy`，包含实际 learner / rollout / replay 配置。
- [阶段切换实现](https://raw.githubusercontent.com/RLinf/RLinf/main/rlinf/envs/real/wrappers/episode/policy_switch.py)：每回合起始回到参考策略，人工按 `b` 切入 RL actor。提供的真机例程仍保留人为阶段切换。

对松灵双臂的推断：可以作为较新的研究实现起点，但必须改 14D 或具体双臂动作定义、相机输入、归一化、数据契约和任务 env，并以状态判定替代人工阶段切换。切换逻辑不等于物体复位；需要单独建立正反循环。与 DSRL 相似，第二阶段并不直接更新 VLA 基座，因此不能宣称在线 RL 已让 π0.5 基座学到双向任务知识；若此为研究目标，后续还需回流蒸馏/再训练及消融。

### SAC-Flow 不等于 π0.5 真机微调

当前真机例程为小型 `flow_policy`，Franka 插孔、6D 末端动作。文档配置列出的示例是宽度 256、2 层 transformer。它提供另一种从示范进行在线 RL 的可行学习器，但“同属 flow matching”不能推导为现成 π0.5 RL 支持。

- [SAC-Flow 配置与范围](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/sac_flow.html)

### Piper 的准确边界

RLinf Piper 官方说明当前仅做通信、关节和夹爪硬件检查；需要用户另行定义 reset、observation、action、reward、success 后才能训练。没有现成双臂任务配置的证据。

- [明确边界原文](https://raw.githubusercontent.com/RLinf/RLinf/main/docs/source-en/rst_source/examples/embodied/piper.rst)

## verl-vla：较新的统一后训练框架

v0.1.0 首发 2026-08-19；官方介绍文章显示 2026-09-09（URL 中的 09-02 不应直接当发表日期）。文档归属 ByteDance，仓库 Apache-2.0。浏览器遥操作、动作块中断、恢复轨迹插入、DAgger 数据记录与训练编排都与用户现有条件相关。

支持列表包含 ACT、Gaussian Actor、π0.5、GR00T；训练模块覆盖 SAC 风格 off-policy、TD3+BC、FPO、DSRL、RECAP。论文/算法年份不可用框架的 2026 首发年份替代。这里没有核实到对应框架的独立论文，按工程项目评价。

关键限制：官方列出的可复现 RL 例程均为 LIBERO / Isaac Lab Arena，Piper 仅列为遥操作与示范录制。官方博客把物理机器人训练继续集成为未来重点之一；当前 Piper 键盘文档页面只有标题，资料成熟度仍需评估。不能把 ACT 模型支持、Piper 硬件支持与 RL 算法支持简单相乘为“ACT/Pi0.5 + Piper 真机 RL 已验证”。

- [仓库及参考配方](https://github.com/verl-project/verl-vla)
- [v0.1.0 发布](https://github.com/verl-project/verl-vla/releases)
- [官方博客与结果范围](https://verl-project.github.io/posts/2026-09-02-verl-vla-v0-1-0/)
- [Piper 文档当前页面](https://verl-vla.readthedocs.io/en/latest/data-collection/piper/keyboard.html)

## 工程选择判断

若研究目标为“尽快把较新的 π0.5 在线 RL 接到真实机器人”，当前证据更支持先评估 **RLinf 的 RLT 实现**，因为它提供了具体真机训练配置；其阶段切换和恢复机制要改为任务条件的自动流程。

若研究目标为“统一现有 ACT / π0.5 / DAgger，长期更换多种算法”，verl-vla 的模型覆盖与后训练工作流有吸引力，但应把它作为系统备选而非更强、已验证的免人工 RL 基线。尤其用户已有遥操作与 DAgger，重建云边系统不一定是首阶段收益最大的工作。

正反循环方向的科学对照仍应保留：固定恢复器 + 正向 RL、分离正反学习器、共享目标条件双向学习器。在相同真实机器人时间与人工分钟数下比较，才能区分“多采了数据”与“共享学习带来正向迁移”。

## 补充核查：RECAP 与 STEAM

本节补查使“优先 RLT”的适用条件更明确：它适合轻量在线控制精修；若要求把双向经验直接写入 VLA 权重，下面的离线/迭代后训练路线更贴近目标。

| 项目 | 真机与模型证据 | 更新内容 | 对当前项目的判断 |
|---|---|---|---|
| RLinf RECAP 实现 | 提供 LeRobot 数据的离线四阶段管线，默认 π0.5 LIBERO 配置，文档另给 Franka 数据变换；不能称现成松灵在线训练闭环 | 计算回报、训练价值模型、产生优势标签、CFG 训练 π0.5，本身更新 VLA 策略参数 | 可直接利用真机成功/失败/接管数据，适合批次迭代；奖励/成功标签与物理循环仍需另建 |
| STEAM + CFGRL | 2026-06-29 论文在 ARX 双臂的叠毛巾、薯片扫码装袋、可乐补货及单 Franka 抓放上有实验；论文写 π0，而当前 RLinf 管线为 π0.5 | 以专家轨迹时序训练进度预测器 ensemble，离线评价混合数据，再经 CFG 训练 VLA | 比纯冻结基座的 RLT 更直接检验双向经验更新 VLA；但不是在线 actor-critic，也未证明自动物理复位 |

### RECAP 的实际开放范围

[官方文档源码](https://raw.githubusercontent.com/RLinf/RLinf/main/docs/source-en/rst_source/examples/embodied/recap.rst)明确为离线管线：当前批次不需要新的环境采样，可读真实机器人数据。原 PI 论文及其 π0.6 结果与 RLinf 的 π0.5 实现要分开评价，不能把前者的实验指标直接移植到后者。默认训练配置是 [cfg_rl_openpi.yaml](https://raw.githubusercontent.com/RLinf/RLinf/main/examples/offline_rl/config/cfg_rl_openpi.yaml)，包含 `cfg_model`、π0.5 checkpoint 与策略 optimizer，`train_expert_only: False`，不是只训练外置控制头。

### STEAM 的新颖性、可信度与边界

[STEAM 论文](https://arxiv.org/html/2606.29834v1)作者单位包括清华、中科院自动化所、中关村学院、鹏城实验室及无问芯穹等；本次只核实预印本，不宣称已经会议录用。其主张是免额外人工优势标注，仍依赖专家示范和收集到的机器人/接管数据。逆序帧对用于学习退步信号，与机器人真正学会反向恢复是两回事。

对正反循环尤其要注意：如果把“拆开/取出/恢复”数据仍交给“装入/完成”方向的进度评分器，很可能被标成退步。应明确方向指令、按方向切段并提供该方向的成功示范；验证每个方向的评分器能识别有效恢复，而不能拿视频倒放充当可执行的反向动作数据。论文也承认单纯时序进度不能充分表示不同任务阶段价值，视觉还可能遗漏关键物理状态。

[当前完整开放管线](https://raw.githubusercontent.com/RLinf/RLinf/main/docs/source-en/rst_source/examples/embodied/steam.rst)支持 π0.5，通过复用 CFG 阶段更新策略参数。它未包含松灵双臂控制或自主复位配方，因此“论文有 ARX 真机”与“仓库支持 π0.5 离线训练”不能合并成“π0.5 松灵完整真机复现”。

配置审查发现一个实际复现注意点：[steam_value_model_sft.yaml](https://raw.githubusercontent.com/RLinf/RLinf/main/examples/offline_rl/config/steam_value_model_sft.yaml)默认 `ensemble_size: 1`，数据占位示例含 rollout 且 `only_success: false`；论文则用专家数据训练优势预测器，默认 ensemble 为 3。该文件属于通用模板，复现实验时需明确覆盖，而非直接启动即等同论文方案。

**补充选择意见：** 若重心是“正反共同学习如何改善 VLA 本身”，将 **STEAM + CFGRL** 列为较新的研究候选、RECAP 列为有回报/优势标注的对照是合理的；若重心是“低计算在线精修局部接触动作”，RLT 仍更直接。两类路线都需要独立的自动任务切换与恢复闭环，现有证据不足以断言任一方案已替用户解决减人工复位。
