# 新近系统与恢复模块补充审查

访问日期：2026-09-22。本文覆盖 ENPIRE、FARL、UniIntervene，以及两个评测方向。结论依据作者原始来源和公开入口，不代表完成安装、训练或实机复现。

## ENPIRE：将代码演化与真实策略改进接到同一个环境

**定位。** ENPIRE 是 NVIDIA、CMU、Berkeley 相关团队的代理式机器人自改进系统。Environment 提供可重复任务环境；Policy Improvement 容纳不同策略更新方法；Rollout 管理真实采样；Evolution 根据结果修改实验和代码。既可以改 Python code-as-policy，也可以调用神经策略训练，因此应作为 harness 考察，不能和 SAC/PPO 当同层优化器比较。[官方项目](https://research.nvidia.com/labs/gear/enpire/)。

**人工的边界。** 论文先由人参与构建和验证机器人站，再让编码代理在既定约束中自改进。环境已具备 reset 与 success verification 是核心前提。真实 YAM 双臂 fleet 包括 1/4/8 台规模；并行缩短墙钟也消耗更多机器人资源。其 pass@8 允许每个子任务内最多 8 次带上下文的重试，后续试验会利用前次失败信息，不能视为独立同分布 best-of-8 或单次 99% 成功。[论文](https://arxiv.org/html/2606.19980v1)。

**开放范围。** 官方 NVlabs/ENPIRE 为 Apache-2.0。主 README 给出 station、CaP 和真实 RL 文档入口；RL 子项目说明 PLD actor/learner 从 `minimal_policy@81988f0` 迁移。runtime 依赖项目实际存在，要求 Python 3.11、Linux x86_64，含 JAX 与 vendored SERL/agentlace 依赖。README 同时明确数据、模型权重、站点地址不属于 runtime 内容。本次点读的是主说明、runtime 说明和依赖清单，未逐行验证整套训练实现或安装所有依赖。[仓库](https://github.com/NVlabs/ENPIRE)、[runtime说明](https://raw.githubusercontent.com/NVlabs/ENPIRE/main/enpire/policy/pld/runtime/README.md)、[依赖清单](https://raw.githubusercontent.com/NVlabs/ENPIRE/main/enpire/policy/pld/runtime/pyproject.toml)。

**选型判断。** 与本会话 harness + RSI + RL 主线最接近的开放集成候选之一。应单独核验任务复位函数、感知误判、物体离开可达区和故障恢复；不从特定已验证工位外推为任意新工位自动准备。不因继承 PLD 就认为原 PLD 全部任务数据和权重已经发布。

## FARL：失败预测与恢复的离线到在线 RL

**机制。** FARL 在离线阶段获得任务策略、恢复策略与世界模型/安全价值估计；在线阶段任务策略继续改进，检测到约束风险时切换到已有恢复策略。在线安全和恢复部分冻结，因此稳定性依赖离线覆盖。初始三类轨迹包括任务、恢复和失败示范，不是从无人工数据出发。[论文](https://arxiv.org/html/2601.07821v1)。

**实验口径。** 三种 Franka 操作，5 Hz 控制，基于 YOLOv8/颜色的状态估计；每类初始数据约 10–20 分钟。作者报告不可恢复失败减少 73.1%、回报增加 11.3%。这些是任务协议下的结果，不能改写为人工工时或普通场景 reset 同比例减少。人为制造失败、设置动态障碍等劳动要算入准备。[项目](https://failure-aware-rl.github.io/)、[工作坊论文](https://rl4il-icra.github.io/assets/papers/L4_failure.pdf)。

**开源与地位。** 本次可读取论文和官方项目，但未核到可用官方训练仓库；不因为页面显示 Code 字样就判定已开源。机构包括上海期智、上海交大、清华、NTU Singapore、A*STAR、Maryland 等作者单位。工作坊版本可找到，不把它升格为已核验 ICRA 主会论文。

**选型判断。** 有充分失败与恢复数据时，是风险门控的参考。它不保证可逆性，也没有替任意任务解决普通回合复位；现阶段更适合方法研究而非首个可直接复现基座。

## UniIntervene：学习何时接管、从记忆选择怎样纠正

**机制。** 利用价值变化识别停滞，借助未来表征与价值/风险模型选择可恢复目标，检索过去有效的恢复片段，再用目标条件 FAST 策略生成纠正动作。降低反复由人执行类似纠正的需要，但先前示范与人类纠正经验仍是来源。[论文](https://arxiv.org/html/2606.12372v1)。

**数字。** 五个 UR7e 任务，每个任务 20 次评测；平均成功率 81%→88%，即 7 个百分点；人工干预率 34.3%→14.6%，其定义是人执行的动作步占全部交互步的比例，相对降约 57.4%。不能据此声称人工接管事件、复位次数、工作时长也减少同样比例。[项目](https://denghaoyuan123.github.io/UniIntervene-project/)。

**代码实查。** MIT 官方仓库公开 NTTG 标签、proxy value、介入挖掘、VQ1、memory、VQ2 的离线流水线。真实机器人部署/HIL-SERL 集成明确在发布包之外；不含轨迹、checkpoint 或 memory bank。`run.py` 的用途说明也明确不启动机器人或在线 RL；其各阶段调度的是离线数据与训练步骤。因此不能把“官方实现”误解为“完整上线脚本”。仓库提供的 FAST smoke test 是组件拟合测试，不是留出任务上的机器人策略评估。[README](https://github.com/Denghaoyuan123/UniIntervene)、[run.py](https://raw.githubusercontent.com/Denghaoyuan123/UniIntervene/main/run.py)。

**选型判断。** 对反复出现、可记忆的失败有吸引力，与 AutoSERL 的示范/规则式纠正构成有意义的研究比较。新异常、失败后物体不可达和每回合重摆场景仍需要另一个闭环。项目和仓库声明 CoRL 2026 接收；小社区体量主要反映新近发布，不能单独据此判方法差。

## CRONOS 与 REVERSAL-BENCH：借鉴评价条件

CRONOS 把共享场景中的持续多任务操作与 reset budget 放进同一评测问题。这个方向有助于避免用无限仿真 reset 支撑真机自主性主张。本次项目代码仍标 Coming Soon，主要证据是仿真，故不列为可立即运行的真机基座。[项目](https://embodiedai-ntu.github.io/cronos/index.html)。

REVERSAL-BENCH 用多个物理环境的不可逆陷阱研究失败识别和恢复边界。识别到了危险不表示尚有可用控制动作能够挽回；仿真 oracle 状态还原也不是现实机器人能力。可用于设计“不可恢复状态”和失败类型的压力测试，不能据其基准分数声明真实硬安全保证。本次只核验论文，仓库开放范围未做代码级审核。[论文](https://arxiv.org/html/2609.17745v1)。

## 接入本会话 harness 的设计推断

下列接口是根据调研作出的设计建议，不是这些项目已有的共同标准：

- `observe / execute`：明确真实执行动作和基础策略版本，避免只记录被替换前的建议动作。
- `score / verify`：区分学习用奖励与独立评测成功判据，记录模型版本和不确定性。
- `reset / recover`：普通复位与异常恢复分别返回是否成功、耗时和是否请求了人。
- `update`：接受成功与失败回放，根据学习器类型更新基础模型、残差、噪声策略或价值模型。
- `evaluate / promote / rollback`：在固定任务协议上判断改进，避免代码代理同时修改策略和验收标准后自报成功。

学习型恢复、自动奖励与编码代理可以组合，但组合后的稳定性需要新实验。不能把多个各有边界的论文结果拼接成一条已经验证过的无人系统能力。
