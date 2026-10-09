# R11 独立证据、选型覆盖与通用融合审查

结论：**PASS；必须修订 0 项。** 仅适用冻结输入及十二问，不表示训练或实机通过。

2026-09-23。已读科学家五份入口并使用指定技能；科学输入仅本轮 `input/` 九份 Markdown。未读旧审查／历史报告／知识正文，未改输入、写库、建 goal、执行 UPDATE、安装、训练或操作机器人。

先枚举关键点再访问原始来源：资产；弱起点；共享正反 RL；Q/V/actor；hold 与 C/E/D；RT-EXPO 数据／延迟／输入；TD3BC/RECAP 分级；Harness 公平竞争；实施顺序；通用性与影响力。不扩候选池。

定位简称均相对 `input/`：T＝`03_RL_Harness自主学习系统_20260922/01_RL_Harness真机自主学习技术方案.md`；I＝同目录 `02_接口契约与开发验收.md`；A＝同目录 `06_异步动作时间轴与学习目标.md`；R＝同目录 `README.md`。D＝`04_RL与Harness扩展调研_20260923/01_RL与Harness开源基线深度调研报告.md`；V/U/H/P＝该目录 `research/01_VLA_RL扩展调研.md`、`02_自主学习与复位扩展调研.md`、`03_Harness扩展调研.md`、`04_训练平台与开源生态核查.md`。以下行号是冻结文件行号。

## 十二个反例式问题

### Q1　假如 RAPolicy 仓库只有代码、没有论文起点资产，能否称开箱复现？

定位：V:342–346，D:93。实读 [S2] 的 Configure your setup／Release validation，要求用户提供 checkpoint、normalizer 与数据，并说明发布检查不是重跑实验。冻结稿明确资产缺口及 fork 身份，没有将主仓 Apache 外推到依赖。**通过；明确待测：**选定后补齐模型／数据版本与依赖锁；资产未随包提供本身不是稿件缺陷。

### Q2　若“零成功”只发生于十示范 SFT 后，能否推广成零信息自主启动及共享反向复位已证？

定位：V:338–340，D:102–106，U:169–175。原文 [S1] §IV-A/B/C 区分单任务十示范、共享五任务更多示范，并保留人工介入；共享多任务不等于 A↔B 自主复位。稿件同时保留启动信息、双向独立评估与人工成本约束。**通过；明确待测：**GPT 纠正能否填补两方向行为覆盖，不能拿论文单任务结果替代。

### Q3　若实现类名含 SAC，直接把完整头 Q 梯度塞进原生 flow，是否仍是 RAPolicy？

定位：T:289–297，V:350–364，I:T39。[S3] `forward_awac_critic` 使用 replay 行为和状态价值，且合并 termination/truncation；[S4] `awac_actor_loss_mode` 默认 likelihood，flow 分支为消融。稿件已分开 Q/V、优势回归、噪声资格和项目终止规则。**通过；明确待测：**原生 learner 的目标条件、BC 标签支路与双向发布；不能只换配置名。

### Q4　若 actor/learner 并发但机器人每块等待推理，能否通过最终连续动作要求？

定位：T:270、293，A:339。沿 [S5][S6][S7] 追到 [S8]，训练和评测配置均有 `fixed_action_chunk`、`hold_during_inference`。A 明确 hold 仅检验学习可达性，队列版须另推导 actor/Q/V、折扣及接管，填充不算执行。**通过；明确待测：**连续 C/E/D 的原生改造成本和合法数据密度；上游并发不能直接验收该项。

### Q5　若 RT-EXPO 先把 RTC-SFT 练到约 30%，十分钟能否算零起点全流程预算？

定位：V:112–116，D:77。[S9] §IV-C、V-C、VI、VII-E.4 给出启动条件、在线数据预算、人工核验及复位限制。冻结稿分别记普通 SFT 和 RTC-SFT 基线，也未把交互分钟当总墙钟。**通过；明确待测：**本项目低起点覆盖与完整人力成本；不将上游门槛强加给所有候选。

### Q6　若把 100 ms sleep 与旧帧 d 步相加，会不会制造不存在的统一延迟实验？

定位：V:155–159，D:81，T:277。[S9] VII-E.3 分列 wall-clock 与 chunk-delay；Dynamic Picking 的额外注入也不同。稿件已经区分两条件，并指出自然推理时间不等于离散预算。**通过；明确待测：**实际观测龄期、网络、排队与 deadline；无需因这些数值尚未实测重复报缺陷。

### Q7　若相机相同但 critic 多拿物体速度，比较所得收益能否全归因 RL？

定位：V:137–139，D:79、211，T:275，I:T34。[S9] VII-D.3–4 给 critic/filter/edit 附加检测器状态，基础 VLA 状态不变，平衡任务图像历史也不同。冻结稿要求逐模块信息、时间及提取成本对齐或消融。**通过；明确待测：**输入清单落到运行配置；硬件相同不免除信息审计。

### Q8　若 TD3BC 起点仅训练 100 步，却来自数百回合，能否作为少示范零成功证据？

定位：P:43–47，D:94。[S10] Reference configuration／Evaluation results 是仿真原生 policy 更新；[S11] Training configuration 标记 432 episodes、0.49 epoch，并单列底模许可。稿件已排除“undertrained＝少示范”的推断，8 GPU 也未变成本项目硬要求。**通过；明确待测：**单机／实体资源和连续协议，不取消其原生头对照资格。

### Q9　若十示范 RECAP 只展示挑选后最好点，能否称稳定自主提升或历史标签重现？

定位：P:103–109，D:95、106。[S12] Evaluation results／Published artifacts 明示多次续跑、波动、选点和最终模型重标。冻结稿已记这些限制并降为文档＋发布级；没宣称读完 value/advantage/policy 全链。**通过；明确待测：**冻结标签 lineage 和独立最终评估；不能因已有移动配方就升为真机主线。

### Q10　若 RPent、OpenETA 都缺持续观察与 RL 桥，只因后者没现成训练器就排除是否公平？

定位：D:149、218，H:194–206、250–256，I:392–396。[S13] `_build_tools` 设置串行工具；[S14] `plan` 先处理观测义务；[S15] `_invoke_tool_handler` 取消时放弃线程结果，不能证明设备停止。冻结稿对两者均要求同 GPT、工具、故障回放、唯一 Gateway 与学习桥。**通过；明确待测：**T38 的观察延迟、停止确认、日志缺口和改造工时决定替换。

### Q11　若摘要优先 RAPolicy，开发者却被要求先长训完整头，竞争是否只是形式？

定位：R:9，D:207–221，T:266–279、291、311–315。冻结稿明确原生头在 P0/P1 预检，允许更低改造成本路线先采用；完整头保存为已写明的队列参考，未要求先长训才能切换。依据 [S1][S8][S9] 的不同协议，分开验证有理由。**通过；可选编辑：**T:19、259 的“主设计／首先实现”与 §10.4 统一称“详细参考设计”，减少读者误解；现有明确顺序已消除实质冲突。

### Q12　若 HF 下载变动或换成另一维度机械臂，开放性与机构声望是否仍能保证可用？

定位：D:23、179–185，P:68–76，H:206，I:386–390。[S11] 本次读取下载为 35，而冻结稿为约 36；这是动态快照差异，不构成虚构证据。卡片许可仍须独立于框架。稿件把引用未知、开放资产、关注度和第三方复现分开，并把 AgileX 限于部署成本、跨本体旧 replay 默认隔离。**通过；明确待测：**两个 schema 的契约回放不等于跨本体实机泛化。

## 本次实际访问与阅读范围

以下均本轮独立打开，代码仅静态选读；未下载权重／数据或验证完整依赖。`latest` 与 HF 页面是访问证据，不是部署锁；未以旧结论代替访问。

- [S1] RAPolicy v1：§III-B–D、§IV-A–C、表 I/II。
- [S2] 固定 README：Configure your setup、Reproducing、License、Release validation。
- [S3] 固定 worker：`_get_data_actions`、`forward_awac_critic`；未审整个 worker。
- [S4] actor loss 文件：默认模式和 flow 消融分支。
- [S5][S6][S7][S8] launcher→task/profile→继承配置，核动作模式和资源字段；未运行 Hydra 合成。
- [S9] RT-EXPO v1：§IV-C、V-C、VI、VII-D.3–4、VII-E.1–5、表 I；非全仓审计。
- [S10][S11] TD3BC 配方、起点卡的数据／训练／评估／许可。
- [S12] RECAP 配方配置、评估选择、SFT 对照、资产及重标说明；未验证资产二进制。
- [S13][S14][S15] RPent 工具注册、OpenETA 规划入口与 handler 取消；未审全部 provider 或驱动。

[S1]: https://arxiv.org/html/2609.22888v1
[S2]: https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/README.md
[S3]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py
[S4]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/awac_actor_loss.py
[S5]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/run_rapolicy.sh
[S6]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/run_realworld_ablation.sh
[S7]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_server_a_franka2.yaml
[S8]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml
[S9]: https://arxiv.org/html/2609.18207v1
[S10]: https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html
[S11]: https://huggingface.co/Miical/pi05-libero-spatial-sft-step-100
[S12]: https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html
[S13]: https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/api_loop.py
[S14]: https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/planner.py
[S15]: https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py

必须修订：0；可选编辑：Q11。待测项已有边界，不重复报缺陷；实验可推翻当前选型。
