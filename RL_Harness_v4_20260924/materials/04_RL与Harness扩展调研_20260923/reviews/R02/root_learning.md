# R02 根审查补充学习

本轮继续独立核对不同组件组合是否改变事实含义，尚未以任何文档 PASS 代替实验。

- 重新读 [Show-Harness 固定 preemption](https://github.com/showlab/Show-Harness/blob/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/preemption.py)：旧模型调用可能继续在后台，只丢弃其结果；generation 防止旧动作再次采用，但不是物理停止。技术02的设备 quiesce 与独立 owner 协议仍必要，不能删。
- 重新读 [SiLRI 固定 policy](https://github.com/nuomizai/lerobot/blob/bd4b1356f95f0c7df4e49e16e9652bc57cd0567d/src/lerobot/policies/silri/modeling_silri.py)：chunk 明确 NotImplementedError；optimizer 参数相加疑点可定位。专题正确区分单步 HIL 学习与 VLA 异步，不因这条静态疑点否定作者真机实验。没有运行该代码。
- 读取 [十示范 RECAP 初始模型卡](https://huggingface.co/Miical/pi05-libero10-task8-sft-10demos) 并与 [官方配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html) 交叉核对。模型页存在不等于自动生成的通用 Diffusers 载入示例就是正确机器人推理入口；实际部署以仓库模型 adapter 和配方为准。数据集页面本次访问失败，不将失败视为未开放，也不新增未经核验的下载／许可数值。

复核 R01 修订：总报告、VLA 专题和技术比较门槛现在分别陈述 wall-clock 与 chunk-delay；未叠加两种延迟。actor 取消终局行的状态采样权重被明确列为工程偏置，不声称无偏；critic terminal 仍按真实后果。RECAP 十示范属于独立配方，未混成 TD3＋BC 的 432 条数据条件。

本轮根审查未发现新的必要文档改动，等待三个独立报告合并决定。现有待实测门槛包括纠正覆盖、有效 TD 密度、动作头可学性和实体停止能力，均未被自动视为通过。

## 汇总后的再次学习与修正

证据审查员指出 RT-EXPO Table I 参照与人工劳动边界仍需明确。根审查重新打开原文 Table I、§V-C、§VI、附录 VII-E 全段：普通 SFT 均值12.5/30、RTC-SFT18/30、RT-EXPO29/30；复位为自动或人工，讨论部分承认人工复位负担，评测成功由人独立核验；十分钟是在线机器人数据上限，不是全部墙钟时间。已修正总报告和VLA专项，补更新在episode边界与启动数据条件，并解释自然67 ms和离散d=3预算不是同一量。R02因此判NEEDS_REVISION，连续通过仍为0。

采纳可选建议：补核心术语和跨论文C符号区别；T36显式核对确定性actor与SAC log_pi/entropy路径；专题概览表补所选MDP时序资格。其他关于实现目录覆盖、缺传感反馈的测试细化已受事实账本/unknown规则约束，保留为实施建议，不改核心方案。新输入再冻结审查。
