# R01 独立审查：证据覆盖、开源可达性与可读性

审查日期：2026-09-23。审查员：独立 evidence reviewer。结论：**NEEDS_REVISION**。

只审查本轮 `input/` 中冻结的技术四文、研究总报告和四份专项；只写本审查文件，未修改冻结输入、主文或知识库。以下是文档和第一方网页审查，**未 clone 完整仓库、未安装依赖、未运行训练或真机实验**。本结论不是对算法效果的复现实证。必要修改只有 E1；可选建议不阻断本轮通过。

## 1. 先枚举关键点

本轮首先列出以下审查对象，再按这些问题独立读取来源：

1. RT-EXPO 是否确有实时训练实现，是否把此次补读说成最近才开放。
2. RT-EXPO 的 base、编辑器和 Q 各自如何更新；效果、延迟和数据条件是否足够完整。
3. RLinf 的 VLA 在线提升是否属于 RL；训练异步是否被混成动作延迟处理。
4. verl-vla 是否直接更新原生 π₀.₅，参考实验是否真的属于少数据、低成功起点。
5. LeRobot 的 release、main、PR 和算法兼容性是否分开。
6. 新 Harness 是否覆盖语义动作、持续观察、停止和学习接口；是否把软件取消等同物理停止。
7. 正反学习、异常恢复、人工成本与 policy 独立能力是否区分。
8. 代码、模型、数据、依赖的开放与许可证是否分开。
9. 首选路线是否可推翻，通用性是否真正优先于某品牌适配。
10. 读者能否从流程、原理和具体代码进入实现，而不必先理解所有缩写。

## 2. 本轮实际访问的一手来源与独立学习

所有下列来源均于本轮实际通过网页工具打开，并非仅转引冻结稿：

| 来源 | 本轮读取内容 | 独立核查结果 |
|---|---|---|
| [RT-EXPO 原论文 v1](https://arxiv.org/html/2609.18207v1)及[作者项目](https://pd-perry.github.io/real-time-expo-ft/) | 方法、真机条件、附录 VII-D/E | base 的成功 BC 与编辑器的 Q 更新已被文档正确区分；补发现延迟实验条件缺项，见 E1 |
| [RT-EXPO 固定实时学习器](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py) | 固定 SHA 下文件可达性 | 该实时文件确实存在；此次仅作可达性核验，不冒称逐行完成整个 learner 审计 |
| [RLinf-USER 官方文档](https://rlinf.readthedocs.io/en/latest/rst_source/resources/publications/rlinf_user.html) | 算法、VLA 结果、异步流水线 | π₀ 真机提升明确标为 HG-DAgger；CNN/Flow 的 RL 与 π₀ 的模仿学习不能合并为同一配方，现稿处理正确 |
| [LeRobot 0.6 官方发布](https://huggingface.co/blog/lerobot-release-v060) | 日期、rollout、DAgger、奖励接口 | 官方页为 2026-07-07，新增部署/纠正和奖励 API 不自动证明任意 VLA＋SAC 兼容；现稿未作这种外推 |
| [verl-vla 官方仓库](https://github.com/verl-project/verl-vla)及[π₀.₅ TD3＋BC 配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html) | 具体 launcher、更新对象、资源、结果 | 文档明示直接更新 PI0.5、关闭 DSRL noise actor；8 GPU/32 仿真环境及 32/50→40/50 与冻结稿一致 |
| [Show-Harness 官方仓库](https://github.com/showlab/Show-Harness)及[固定 preemption 源码](https://raw.githubusercontent.com/showlab/Show-Harness/137d571/core/runners/preemption.py) | 本体解释器、数据/训练目录、取消接口 | 语义动作和解释器分层确有第一方支撑；preemption 不构成设备停止证明，现稿边界合理 |
| [Strands Robots 官方仓库](https://github.com/strands-labs/robots) | 统一机器人/策略接口、记录、训练功能 | 值得作为通用底座候选；支持列表仍不能取代具体硬件和训练组合审查 |
| [verl-vla 十条示范 RECAP 配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html) | 初始数据、资源、评估和恢复运行说明 | 作为一次有针对性的补漏检索，发现较贴近少示范/弱起点的开放实验；仍是仿真，且有选 checkpoint 与中断续跑边界，见 O1 |

没有继续扩张候选名单。RPent 新 HEAD、平台各固定 loss 文件和全部权重许可未在本审查重复深读，因此有关它们的“已正确覆盖”判断指冻结稿是否明确陈述证据边界，不代表本审查补做了完整源码认证。

## 3. 十二个具体问题及判断

定位均为 `input/` 下对应冻结文件的章节；技术主文简称“技术01”，接口简称“技术02”，异步附录简称“技术06”。

| 编号 | 具体问题 | 定位与判断 |
|---|---|---|
| Q1 | 能否找到 RT-EXPO 真正的实时训练文件，而非普通 EXPO 的同步分支或项目网站？ | 总报告 §4.2、VLA 专项 §4.2/§9：**覆盖充分**。给出固定 SHA 和实际文件，明确此前遗漏发生在已有提交中。独立访问确认文件可达。 |
| Q2 | “VLA 经过 RL 改进”是否掩盖 base 成功 BC、编辑 Q 更新和有界动作覆盖的区别？ | VLA 专项 §4.3：**覆盖充分**。没有把 base 永久冻结，也没有说 Q 直接优化整套 flow expert。 |
| Q3 | 实时效果是否明确区分实际推理耗时、人工注入 sleep、旧观测构造的 chunk-delay？ | 总报告 §4.2、VLA 专项 §4.1/§4.4：**必要补充 E1**。当前只有抽象 d/C、十分钟和 RTC-SFT 边界，缺少原论文延迟实验条件。 |
| Q4 | RLinf 的 π₀ 提升是否被误报为 SAC 效果，RTC 评估是否被当作本项目 queue-TD 已实现？ | 平台专项 §2/§10、总报告 §7.1：**覆盖充分**。明确 HG-DAgger 与 CNN/Flow RL，默认 reward/discount 与本方案不等价。第一方 USER 页面支持这种区分。 |
| Q5 | verl-vla 的“undertrained”是否被当作只有几条示范，Piper 采集是否被当作受验证真机 RL？ | 平台专项 §4、总报告 §4.3：**覆盖充分**。明确 432 episodes、仿真资源、直接更新与实体训练证据边界。可再补 O1，但不要求新增移植。 |
| Q6 | LeRobot 的 main 源码、release 和未合并 PR 是否被混为已交付功能？ | 平台专项 §3/§7/§10：**覆盖充分**。release 与当前源码分开，Draft/错误 PR 引用单列，固定 SHA 与安装未验证也披露。尚可按 O2 更直观标版本。 |
| Q7 | Show-Harness 能否真正落地纠正，而不是只给语言建议；解释器会不会绕过唯一控制权？ | Harness 专项 §5、技术01 §6.6、技术02 接入契约：**覆盖充分**。候选/编译/执行分层，处理默认 RELEASE、反馈动作和停止差异，没有强制把 VLA 离散化。 |
| Q8 | 新 Harness 是否只因机构或机器人品牌而进入主线，RPent 是否被预定为赢家？ | Harness 专项 §7/§9、技术01 §10.2、总报告 §9.2：**覆盖充分**。Strands/DimOS/OpenRAL 可参与统一接口预检；同 GPT、工具和模拟 adapter 比较；AgileX 仅部署成本。 |
| Q9 | 正反策略学习、外部 reset、异常恢复和系统代做成功是否混淆？ | 自主专项 §2/§3、技术01 §5/§13、README 末尾：**覆盖充分**。共享 θ、分方向评估、系统成功和 policy 独立成功、人工成本均区分。 |
| Q10 | 公开 GitHub 是否被等价成完整可复现、可商用的模型和数据？ | VLA 专项 §7、Harness 专项 §3.2/§4、平台专项 §7：**覆盖充分**。原论文/代码/权重/数据/依赖分别讨论，缺许可与不可访问不冒充允许或不存在。 |
| Q11 | stars、下载和机构影响力是否被混成引用数或第三方复现次数？ | 总报告 §7.2、各专项影响力段落：**覆盖充分**。访问日快照、未追踪下载与未知引用清楚，不强行造榜。 |
| Q12 | 完整动作头是否只是“结构上方便”就被断言优于原生方案；读者是否能理解切换依据？ | 总报告 §2/§9、技术01 §1/§3/§10：**覆盖充分**。先有抓空实例和模块机制，再有同预算/动作覆盖比较；暂定选择可被推翻。少量术语可按 O3 辅助阅读。 |

## 4. 必要文档修改

### E1 — 补齐 RT-EXPO 实时实验的延迟条件（中等）

**定位：**总报告 §4.2（约第 74 行）；VLA 专项 §4.1（约第 111 行）和 §4.4（约第 130 行）。

**问题：**RT-EXPO 是首要异步工程挑战者，现稿已记录成功率、RTC-SFT、检测器和 DROID，但未记录论文附录 VII-E.3 对实时延迟的实验构造。这样读者容易把整组结果理解为在目标硬件上自然出现的推理/网络延迟下测得的表现。

**来源与修法：**按[论文附录 VII-E.3](https://arxiv.org/html/2609.18207v1#S7.SS5.SSS3)补一小段：区分 wall-clock 条件（d=0，部分任务每次采样加入 100 ms sleep）与 chunk-delay 条件（旧观测、在途前缀及延迟后动作段）；注明 Dynamic Picking 不加入额外 wall-clock 延迟。解释这些是论文报告的延迟实验设置，不能替代本项目硬件的实际时延分布、抖动和超预算测试。无需撤回其“已有真实训练代码”的结论，也不据此降低成纯仿真研究。

**验收：**总报告的一句话边界和专项中的具体设置相互一致；把作者实验设置与项目待测要求分开，不擅自把两种模式写成同一次实验同时叠加的延迟。

## 5. 可选改进，不阻断通过

### O1 — 补一项同平台的少示范 RECAP 实验

**定位：**平台专项 §4/§6；VLA 专项 §3.1 中 RECAP 行。

官方 [LIBERO-10 task 8 配方](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html)提供 10 条示范起点、3 轮自主采集，报告 8/50→最佳 23/50，并有同最终 106-episode 数据池的 plain-SFT 对照。它比 TD3＋BC 的 432-episode 起点更贴近“少示范、弱策略”问题。建议作为一小段补漏，不升级为首版必跑路线。必须同时写明：仿真、非零起点、8 个 policy GPU＋2 个 value GPU 的参考拓扑、评估选点，以及作者明确披露多次停止/恢复、单次连续运行未必复现相同结果。该实现属于 verl-vla 的 RECAP 配方，不应写成 PI 官方完整训练栈。

### O2 — 将移动来源和固定版本标在表格同一行

**定位：**平台专项 §2/§3/§4/§10；Harness 专项 §3.2。

现稿已有必要版本边界，但散落在正文和末尾。建议给每个首选候选加“release/固定源码/访问日 latest/实际运行”四列，LeRobot release 可补[官方 2026-07-07 日期](https://huggingface.co/blog/lerobot-release-v060)。RPent 旧 SHA 与新短 SHA 可同时保留，并明确短 SHA 只用于发现新版本，P0 再锁完整依赖。此项是阅读改进，不要求当前立即安装所有依赖。

### O3 — 为核心缩写加极短词汇表

**定位：**总报告 §2 和技术06 开头。

建议解释 flow/action expert、RTC、TD、off-policy、critic、adapter 各一句，并提示两个文档中的 C 不是同一物理对象：项目 C 是承诺动作段，RT-EXPO C 是执行窗口长度。现有章节已分别定义，不构成数学错误；加别名或符号脚注能减少跳读误解。

## 6. 审查边界与通过条件

本轮证据覆盖足以支持继续开发预检；没有发现依据品牌适配预定最优路线，也没有发现将网页可读伪装成本机运行成功的问题。主线仍是待验证组合，应继续保持同预算竞争与独立 policy 指标。

本轮判为 NEEDS_REVISION 仅因为 E1 与首要异步候选的实验可解释性直接相关。补齐 E1 后即可进入下一轮独立审查；O1—O3 可选择采纳。不得把本文件计为模型、数据桥或机器人已运行通过。
