# R01 根审查：额外学习与反例核对

冻结输入不修改；这是根审查补充，不替代三个独立 agent 的报告。

本轮独立重新读取：

1. [RT-EXPO 原文](https://arxiv.org/html/2609.18207v1)：附录明确区分仿真全部 rollout BC 与真机成功 episode BC；真机 sparse detector、额外 critic 状态与 base 初始化条件支持报告中的限定。不能把仿真 BC 数据选择套到真机，也不能把原生 base 和编辑器的更新合并叙述。
2. [RLinf 固定 SAC worker](https://github.com/RLinf/RLinf/blob/7b3d874945454acfd0785c7c4837a0ad795c391d/rlinf/workers/actor/fsdp_sac_policy_worker.py)：核对 `forward_critic` 的分支折扣和 reward sum。报告明确其时间单位不同，要求新增队列 target，没有声称上游算法本身错误。
3. [verl-vla 固定 trainer](https://github.com/verl-project/verl-vla/blob/c1de826c7c9256e4d9b6900091e4b0e243d16f5e/src/verl_vla/trainer/sac/sac_ray_trainer.py)：`prepare_sac_actor_input` 按首次 done 裁有效 substep，并求和；episode 完整收集不同于固定槽接管。技术方案以独立协议和训练视图区分。
4. [RPent 新提交](https://github.com/RLinf/RPent/commit/6ee7069)：父版本就是旧审计版本；新增 RoboCasa/RoboTwin 探索、环境 reset、最终 winning command 导出。通过 [固定 blob](https://github.com/RLinf/RPent/blob/6ee7069/robots/robocasa/toolkit.py) 进一步核出完整 SHA `6ee706935d28646828f70372ef0099c769cfe0c2`。只读改动清单、选定文件与文档，不冒充全量差异审计。
5. [Strands 固定 run_policy](https://github.com/strands-labs/robots/blob/4d0203161a587e29d7912c99da74878e8f989544/strands_robots/tools/run_policy.py)：固定源码存在；不可因猜错 `src/` 路径出现读取错误就判断未开源。

反例核对：同一 GPT 在槽内读新图两次，其第二次纠正不能倒填第一时刻完整标签；两个不同本体更换维度不能复用旧 normalizer/replay；启动解释器不能自动 RELEASE 持物夹爪；未来 terminal 不能选择性修改前驱 target；工具 DONE 不能直接作为独立成功。现版 01/02/06 均有对应边界。

根审查暂未发现必要新修订，最终轮次判定等待三个独立报告。未执行软件安装、训练或真机。


## 汇总后的重新学习与修正

证据审查员发现 RT-EXPO VII-E.3 的必要条件遗漏。根审查再次实际打开附录，确认 wall-clock 注入三任务 100 ms、Dynamic Picking 不额外注入，以及 chunk-delay 的 d=3/5 分支。已在 VLA 专题、总报告和技术方案比较门槛补正；R01 最终 NEEDS_REVISION，连续通过为 0。

同时实际阅读 [verl-vla 十示范 RECAP 完整配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html)，新增弱起点、106 episodes、续跑选点、8+2 GPU、标签重算边界；采纳原生启动条件、actor terminal mask 的状态权重说明及 T38 具体入口记录。这些均在下一轮重新冻结，不冒称原冻结版已经包含。没有运行训练。
