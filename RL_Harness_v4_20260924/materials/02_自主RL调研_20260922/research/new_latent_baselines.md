# 比 DSRL 更新的潜空间 / VLA RL 基线补核：ZPRL 与 RLT

核验日期：2026-09-22。场景：松灵 ALOHA 类双臂，已有 π0、ACT、遥操作及接管 DAgger；目标为正向、反向和失败恢复共同练习。本文仅做来源与接口审查，未训练、未实机复现。

## 结论

**两者都更新，但没有证据支持“直接换上就更少人工”。** RLT 更贴近现有 π 系列模型的接口；ZPRL 对紧凑潜空间探索和双臂动作的研究价值更直接，但把其小型流策略实现迁移到 π0/ACT 需要额外研究。两者原论文均没有验证正反共享训练或自主复位闭环。

## ZPRL

- **时间、机构：** 预印本 2026-05-19；HKU、上海期智、上海交大、中科院自动化所、清华 IIIS。当前核验未确认正式会议录用。[论文元数据](https://arxiv.org/abs/2605.19919)、[作者项目页](https://manutdmoon.github.io/ZPRL/)
- **机制：** 离线学习观察表征的变分信息瓶颈；在线冻结基础策略，由 SAC 学习瓶颈潜变量的残差，解码后再条件化动作生成器。潜变量通常 16/32 维。实际基础模型是 ResNet18 + 1D U-Net 的 flow policy。论文明确将向复杂交叉注意力架构扩展列为未解决方向，不能把它写成现成 π0/ACT 插件。[论文 §IV、§V-E、附录](https://arxiv.org/html/2605.19919v1)
- **真机边界：** 四任务包括双臂开箱、插纸币；插纸币没有同预算在线竞争基线。论文 §V-D2 明确人工监控、逐回合复位、给最终奖励。不是自主运行系统。[论文](https://arxiv.org/html/2605.19919v1)
- **开放性：** 原作者仓库确有训练源文件、在线配置，MIT；网页显示 51 stars / 2 forks，关注度尚早期。公开说明聚焦 Robomimic 仿真复现，所链接数据和模型也是 Robomimic；本次未核得完整真机部署入口。[官方仓库](https://github.com/ManUtdMoon/ZPRL)、[许可证](https://raw.githubusercontent.com/ManUtdMoon/ZPRL/main/LICENSE)、[在线配置](https://raw.githubusercontent.com/ManUtdMoon/ZPRL/main/zprl/config/train_online_vib_robomimic_workspace.yaml)

**选型推断：** 如果愿意另建小型目标条件 flow policy，ZPRL 是适合“共享瓶颈是否促进正反经验迁移”的研究基线。如果主要诉求是保留已有 π0/ACT、尽快真机闭环，它不比 DSRL 的现有 π0 路径更省工程。应先保证正向与恢复数据都进入基础策略；局部潜变量调整不能替代从未覆盖的恢复技能。

## RLT

- **时间与出处：** Physical Intelligence 技术博客发布于 2026-03-19；arXiv 初版 2026-04-24，v2 04-30。不是第三方仓库引用中出现的 2025 年。[官方博客](https://www.pi.website/research/rlt)、[论文元数据](https://arxiv.org/abs/2604.23073)
- **机制与证据：** 原论文以 π0.6 为基础，用编码器—解码器压缩 VLA 内部表征为 RL token，再冻结表征，小型 actor/critic 基于 token、本体状态、参考动作块在线学习；actor 输出动作块并向 VLA 参考动作正则化，不等同“直接加一个动作残差”。四项真机精细操作中有双臂扎带，14 维动作；训练仍需人工奖励、接管和选择关键阶段。原实验 15 分钟到 5 小时机器人有效数据不包含复位及其他开销。[论文](https://arxiv.org/html/2604.23073v1)
- **原作者开放性：** 本次未找到 PI 原作者发布的完整 RLT 训练仓库；不能将 openpi 基础仓库当作 RLT 已官方开放，也不能说“没有任何开源实现”。
- **框架实现：** RLinf 已有 π0.5 两阶段 RLT 训练及 Franka 真机、ManiSkill 配置；这是 RLinf 团队实现，非 PI 原作者代码。真机示例 7 维单臂，手动按 `b` 切入 RL 阶段。文档明确 Stage 2 不是标准最大熵 SAC；损失为 Q 改进加参考动作 / 人工接管 BC。RLinf 为 Apache-2.0。[框架文档](https://rlinf.readthedocs.io/en/latest/rst_source/examples/embodied/rlt.html)、[许可证](https://raw.githubusercontent.com/RLinf/RLinf/main/LICENSE)
- **松灵相关第三方实现：** `Yyshadow/openpi-RLT` 提供 `agilex_ethernet`、π0.5、ROS 接口及作者演示；当前公开默认仍是 7 维单臂动作，需人工开回合、切阶段、成功失败标注。根 LICENSE 为 Apache-2.0，另有 Gemma 条款。其现成接口具有适配参考价值，不能将 PI 的机构信誉与结果转嫁给该第三方实现。[仓库](https://github.com/Yyshadow/openpi-RLT)、[运行说明](https://raw.githubusercontent.com/Yyshadow/openpi-RLT/main/rlt_online_rl/README.md)、[许可](https://raw.githubusercontent.com/Yyshadow/openpi-RLT/main/LICENSE)

**选型推断：** 若保留 π 系列模型且可承担 token 训练，RLT + RLinf 是比“从头移植 ZPRL 到 π0”更直接的候选。迁移 ACT 仍需自定义特征接口；两者都没有 ACT 官方结果。双向研究中应把目标显式送入 token、actor、critic，并与独立双策略比较；人工奖励、阶段切换、物理复位必须另建自动检测与恢复机制，不会因引入 RL token 自动消失。

## 与用户双向目标的共同缺口

1. 先有可用的正向、正常反向、失败恢复基础动作；只含成功正向数据不足。
2. 明确定义“可继续练习”状态集合，不把精确回到原摆放当成唯一恢复目标。
3. 第一阶段冻结恢复器，仅训练正向，建立人工分钟数、有效循环数与成功率基线；再共同更新两个方向，才能检验共享收益。
4. 真机动作维度、单位、双臂同步、动作块中断和接管数据归属需要逐项适配，不能从机构名、论文新旧或配置名推出已兼容。
