# R07 独立证据、覆盖与联合选型审查

**结论：PASS。12 个具体问题已核查；必要修订 0 项，可选补漏 1 项。** 本结论仅针对冻结文档的证据与选型合理性，不证明系统已运行、算法优胜或真机复现。

审查日：2026-09-23。只读加载科学家 START_HERE、ROLE、state/status、knowledge/INDEX、科研 SKILL；未读旧审查结论。输入为 R07/input 九文件：总报告、四专题、方案 01、接口 02、异步 06 和 README。下文用“总／VLA／自主／Harness／平台”简称报告及专题。

先列技术点再查原文：论文／资产、弱起点／预算、更新模块、执行／训练异步、信息时效、平台 loss、观察／停止／数据桥、共享目标／复位、通用性、机构／独立复现。

实际打开 RT-EXPO 原文及固定学习器、verl-vla 两份配方、RLinf-USER／固定 worker、LeRobot 固定 mixer、Show 固定 runner、RPent 提交、OpenETA 固定文件；未安装运行。LeRobot blob 失败后以固定 raw 核对；RAPolicy 项目页访问失败不等于未开源。

## 逐题判定

1. **RT-EXPO 的 42%→97% 是否被误写成弱 RTC 起点或十分钟总成本？** PASS。总 §4.2、VLA §4.1 区分 SFT／RTC-SFT 与在线数据预算；约 30% 启动条件、人工复位及独立验成功均已写明。核对 [原文 §IV-C、V-C、VI](https://arxiv.org/html/2609.18207v1)。

2. **自然延迟、注入延迟及额外状态是否混为公平算法增益？** PASS。VLA §4.4–4.4.1 分开 wall-clock 与 chunk-delay，列明检测器派生状态和图像历史；方案 §10.2、接口 T34 已将信息来源、可用时间及成本变成对照条件。核对同一 [原文附录 VII-D.3–4、VII-E.3](https://arxiv.org/html/2609.18207v1)。未用统一相机数替代统一信息条件。

3. **RT-EXPO 是否被误当成 Q 直接训练整套原生 flow？** PASS。总 §4.2、VLA §4.3 区分 Q、编辑器与 base；固定源码有独立 update_actor／update_edit_actor，方案保留候选覆盖及完整头冷启动的比较。来源：[固定学习器](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)。

4. **verl-vla 原生头配方是否直接证明少示范真机可行？** PASS。平台 §4、总 §4.3 限定为仿真；[配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html)确有 32/50→40/50、32 并行环境。八卡未写成用户硬性配置，训练 100 步未等同少量数据。

5. **十示范 RECAP 是否被 best-of-run 或最终重标掩盖？** PASS。平台 §11、总 §4.3 写清 8/50→最好 23/50、8＋2 GPU、续跑选点、强制正示范及最终重标。与[官方实验和资产说明](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html)相符。该配方强化弱起点候选资格，尚不证明无人真机稳定提升。

6. **RLinf 同时支持 VLA、SAC、RTC，是否被拼成已完成队列 RL？** PASS。平台 §2、§10 和接口 T36 明确需改 target／goal／queue／BC；[USER 页](https://rlinf.readthedocs.io/en/latest/rst_source/resources/publications/rlinf_user.html)的 π₀ 结果是 HG-DAgger。[固定 worker](https://github.com/RLinf/RLinf/blob/7b3d874945454acfd0785c7c4837a0ad795c391d/rlinf/workers/actor/fsdp_sac_policy_worker.py)的非 DSRL 分支聚合 reward 后乘一次 discount，并含可选 entropy backup；不能原样充当项目微步折扣目标。

7. **LeRobot 双池是否已解决纯建议 BC 和纯离线预热？** PASS。平台 §3、§10 限定 mixer 混合 transition；[固定源码](https://raw.githubusercontent.com/huggingface/lerobot/fbb811fca92504439792b97d216f0d00c2268382/src/lerobot/rl/data_sources/data_mixer.py)确有 max(1, int(batch_size * online_ratio))。接口 §5／T36 保留标签分支，防止继承默认 SAC 概率接口。

8. **RPent 新版本能否沿用旧证据认定已完成真机复位与全量 RL 数据？** PASS。总 §6.1、Harness §12 只声称选定差异复核。[6ee7069 提交](https://github.com/RLinf/RPent/commit/6ee7069)明确普通环境 reset、仅导出最后获胜命令。方案仍要求独立观察、唯一 Gateway 和事实日志；同组织的 RLinf 不是现成接通证明。

9. **Show-Harness 是否被高估成自动 DAgger／奖励真值？** PASS。Harness §5.2、方案 §6.6、接口 T32–33 明确只复用解释器和记录思想。[固定 runner](https://github.com/showlab/Show-Harness/blob/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/real.py)的最终 DONE 完成语义和人工意图路径印证这些边界。反馈生成的多步轨迹不能倒填为最早状态的一个动作块，原稿已有对应限制。

10. **OpenETA 是否因为没有现成在线 RL 被不对称淘汰？** PASS。总 §6.2、§9.2 与接口 T38 已给与 RPent 相同的骨架预检资格。[固定 README](https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/README.md)区分已适配与未适配 policy adapter；逐工具新观察不能自动证明持续观察和实体停止。原稿要求补独立观察、Gateway、数据桥，未按功能口号直接选胜者。

11. **恢复、自主与共享正反是否越过证据边界？** PASS。自主 §2、§4.4–4.5、§7 和方案 §5 分开正常反向、异常恢复、辅助及参数更新；接口 §6.2 要求同一 checkpoint 双向评估。UniIntervene 离线包、LWD 数据条件未被抹去。本题核文档一致性，未重读全部历史论文。

12. **最终组合是否依赖品牌／热度，或把接口审阅当复现？** PASS。总 §7–9、方案 §10、接口 T37–38 分层比较 learner／骨架／辅助系统，以两个动作 schema 验通用边界。机构／stars 不替代复现；许可分层，未运行已声明。异步 §10–11 区分自定义队列目标与原论文。

## 有界补漏与可选项

检索限于 robot VLA online RL real time September 2026 weak policy 和 OpenETA Harness policy adapter 两主题，追加 RAPolicy 名称／代码查询。排除同名网络工具和软件开发 Harness，不递归追索。

**O1，可选：补入 RAPolicy 跟踪卡。** [2026-09-19 原文 §III–IV](https://arxiv.org/html/2609.22888v1)采用 replay 价值学习与单步 flow 优势加权更新；单任务十示范、含 0/20 起点，联合任务每任务三十示范。使用八张 3090，保留人工介入；异步指 rollout／learner 并发，不能推为 C/E/D 已解决。项目页访问失败，未确认完整官方训练资产。它补强原生头弱起点依据，尚不足以推翻工程路线，无需新增完整移植。定位：VLA §3.1／§8.1。

必要修订为空。最终优先级仍由同预算、同信息条件及正确时间协议的实验决定；未运行已明示，不自动阻断本次文档审查。
