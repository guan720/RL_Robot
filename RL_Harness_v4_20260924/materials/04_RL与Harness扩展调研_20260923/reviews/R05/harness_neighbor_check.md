# R05：HALTER 三项邻近工作的限定补漏

核查日：2026-09-23。按科学家入口、ROLE、skill 和研究流程只读开展；仅核查指定三项，未扩展引用链，未安装、训练或实机复现。结论是：**不新增独立通用骨架；Harness VLA 应归并 RPent；Zero2Skill 应加入纠正记忆与数据整理的模块候选；Guava 暂作方法参考。** 以下“未找到”仅指本次官方论文、项目页、仓库及权重检索范围。

## Guava：工具调用模型训练，公开实现尚不足

机构：UMD、UIUC、Waterloo、MBZUAI、UPenn、Amazon FAR；arXiv v1 首发 2026-06-16。[论文](https://arxiv.org/abs/2606.18363)

机制是多模态观察→ReAct→语义工具：`grasp(object)`、`move(x,y,z)`、`home_pose()` 等。以不足 2K 条仿真成功及恢复轨迹对 Qwen3.5-4B 做 SFT，再用成功奖励做 GRPO；训练的是高层推理和工具选择，非本项目低层共享动作策略的真机在线 RL。论文有 FR3＋D435 真机评测，但恢复行为不等于真实纠正轨迹已回流训练，也未展示正反共享策略学习。[正文 §3–4](https://arxiv.org/html/2606.18363v1)

官方项目页仍为 **Code (coming soon)**；本轮未核验到作者发布的实现、Guava-Agent-4B checkpoint、训练数据或其许可证。开放 Qwen 底座不能代替这些资产的公开证明。故**不进可用骨架短名单**；保留“语义工具＋失败恢复数据蒸馏”对照方向。[项目页](https://guava-harness.github.io/)

## Harness VLA：就是 RPent 的论文，不重复计算候选

清华牵头，联合 Striding AI、Purdue、中科院自动化所、Infinigence AI、HKUST、中关村学院；首发 2026-07-09，最新 v4 为 2026-09-02。[论文](https://arxiv.org/abs/2607.08448)

冻结 VLA 作为 `vla_act` 接触操作原语，与 `move_to/rotate/set_gripper` 等解析工具组合；任务记忆记录参考种子成功调用，全局记忆总结成功规则和失败模型。新增记忆并非 VLA 参数更新。论文主要证据来自 LIBERO-Pro、RoboCasa365、RoboTwin 仿真，不能把其提升记为真机纠正训练收益。[正文](https://arxiv.org/html/2607.08448v4)

官方代码明确指向 **RLinf/RPent**，Apache-2.0；当前仓库已有单/双 Franka 扩展、机器人服务与多种模型后端。官方链接的 [LIBERO π0.5 SFT 权重](https://huggingface.co/RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT/tree/main)含实际模型文件，但该卡未显示独立许可证，不能从主仓库许可外推。**保留在既有 RPent 条目，补全论文身份和冻结边界**，不新增“更优替代者”。当前硬件扩展也不自动证明论文已经验证共享正反 RL 或纠正动作回流。[仓库](https://github.com/RLinf/RPent)

## Zero2Skill：纠正与数据链值得补入，未达到完整骨架条件

GigaAI、国科大、HKUST 等联合；首发 2026-07-15，v3 为 2026-07-22。OpenClaw 编排 collect→verify→reset；语言纠正修改判据、分割提示、抓取深度或选臂规则，并保留到 Corrective Memory。会话内主要改记忆；采集数据随后微调 π0.5。双 Piper 桌面清理实验用 50 条示范，作者报告无 Harness 辅助的 20 次部署试验成功率 80%，与遥操作数据组相同；只验证一轮，非持续多轮飞轮。自主 reset 是工具程序，不是同一 policy 的反向 RL。[论文 §3–4及附录](https://arxiv.org/html/2607.14047v3)、[官方项目](https://open-gigaai.github.io/Zero2Skill/)

公开仓库为 Apache-2.0，本轮 API 锁定 `6ea772566939d9c235dda771fe14f5fafa2bc6ad`。有 agent skills、抓放脚本、离线判定与数据整理；接口包括物体提示、选臂、放置坐标、深度偏移，ROS topic/URDF/标定可配置。[仓库](https://github.com/open-gigaai/Zero2Skill)、[配置](https://github.com/open-gigaai/Zero2Skill/blob/6ea772566939d9c235dda771fe14f5fafa2bc6ad/configs/paths.env.example)

源码证据有三项限制：

- [NOTICE](https://github.com/open-gigaai/Zero2Skill/blob/6ea772566939d9c235dda771fe14f5fafa2bc6ad/NOTICE)明确 AnyGrasp 二进制、权重与许可另备，HDF5 recorder 外置；未找到本文微调权重及完整 π0.5 训练入口。
- [prepare_training_set.py](https://github.com/open-gigaai/Zero2Skill/blob/6ea772566939d9c235dda771fe14f5fafa2bc6ad/grasp-tools/collect/prepare_training_set.py)生成 ACT 风格 HDF5；默认 strict，但可选 lenient 接受缺失/unknown 视觉判定。规则改变保留旧 manifest、仅新样本用新规则，与论文重判旧数据的描述有差距；可选 `action_shift` 以未来 qpos 构造标签，不能直接当真实执行动作送入 RL。
- [IK helper](https://github.com/open-gigaai/Zero2Skill/blob/6ea772566939d9c235dda771fe14f5fafa2bc6ad/grasp-tools/piper_pose_ik.py)仍含 Piper TCP/法兰几何常量；配置化不等于跨本体已验证。

**加入模块短名单，不升格主骨架。** 有价值的是持久纠正、复位单独验收和真实采集→独立策略评估；优先级不来自 Piper 适配。接入现方案仍须补唯一 Gateway、实际动作与标签分离、判据版本重审和双向共享 BC＋RL。
