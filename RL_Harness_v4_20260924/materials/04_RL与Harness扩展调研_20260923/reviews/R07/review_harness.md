# R07 独立 Harness 融合审查

结论：**PASS（设计／证据边界）**。12 问通过，实质错误或遗漏 0 项；未安装、运行或验证真机学习效果。

范围：R07/input 的 9 文件，重点为技术01／02／06、综合报告和 Harness 专题，另三专项及 README 核查融合论断。已只读加载科学家 START_HERE、ROLE、state/status、knowledge/INDEX、科研 SKILL／RESEARCH；未读旧审查，未继承 PASS，未修改输入或科学家库。

先枚举再查原始证据：GPT／DAgger、底座反证、Gateway／epoch／停止、独立观察、双向共享／恢复、迟到／未知、代码晋升、事实／BC／TD、反馈时间条件、跨本体、独立能力、实测边界。

2026-09-23 实际阅读 DAgger 算法3.1／定理3.1–3.2、Show-Harness §3.2 和下列固定源码；blob 不全时继续读 raw。下文编号均指冻结文件，报告／专题指综合报告／Harness专题。

## 逐项问题、判断与依据

1. **GPT 主观察和 DAgger 是否暗含完美教师？PASS。** 技术01:35–41、113–139；接口02:150–191。原 DAgger 聚合访问状态的专家动作且有理论条件 [S1]；文本仅借聚合思想，明确 GPT 错误率待测，需要可靠动作和同预算 BC 对照，没有继承专家保证。

2. **RPent 是否不可替换？PASS。** 技术01:264–275；报告:197–215；接口02:387–395。OpenETA／Strands 等以同 GPT、工具、adapter 和故障记录比较，较少改造且通过契约即可切换。OpenETA 在模型调用前派发 observe [S2]，支持候选资格，不证明持续观察。

3. **观察会不会排在长 motion 后面？PASS。** 接口02:54–58、393。RPent 新 SHA 的 active operation 检查先于 readonly 分支 [S3]。方案要求独立订阅观测，并以长工具卡死验收；没有用异步工具开关代替观察证明。

4. **取消、epoch 更新是否被误当成物理停止？PASS。** 接口02:113–146、T07–T09／T31／T33。OpenETA handler 在后台线程运行，取消只抛 abandoned [S4]；Show 丢弃过期模型结果 [S5]。方案另要求处理在途动作、当前代际 quiesce 凭证、新鲜观察、唯一驱动与去重，不接受自填 stopped。实际停止时间和持物保持仍须设备测量。

5. **反向是否退化成 reset，恢复是否污染任务？PASS。** 技术01:88–109；接口02:259–267；异步06:245–257。actor／Q／target 接目标且共享参数，两向学习、整体发布；异常复位另记成本和边界。验证下一方向 init_set，不能盲目换向或将放回 A 记作正向成功。

6. **迟到和 unknown 会不会错写当前奖励？PASS。** 技术01:143–179；接口02:165–183；异步06:229–231。ENPIRE 原码缺图、限频、异常均返回全局旧值 [S6]。方案绑定证据、goal、episode 和评分版本，分开历史评分／历史标签／当前控制资格，pending 不充零；终局时间按证据成立时间，不能任意回溯。

7. **候选程序能否自动试验，又不能自证晋升？PASS。** 技术01:153–157；接口02:193–201、T23、271–297。TRIAL 有动作域、前置条件、预算和固定核验；禁止修改 rubric、事实及保护，回归后发布。无需逐次人批；软件回滚与物理恢复分开。

8. **建议、失败动作和调度是否混成 transition？PASS。** 接口02:64–85、205–217；异步06:63–95、165–180。四层动作、事实、标签与训练视图分开；纯建议仅监督，真实失败可为 TD。终局未激活 U 须来自事前真实请求及冻结计算，不能给影子建议补 admission。此为拟议模型，未声称 recorder 已实现。

9. **逐图反馈纠正是否被倒填为起点完整动作块？PASS。** 技术01:159–169；异步06:182–190、233–255；T32。Show 的语义动作以本体解释器落地并循环读反馈 [S7]。方案保留逐步事实，普通队列 U 只接受相同起点信息；新图改轨迹需独立监督／微步协议，不重复单帧填满 n 步。BC、执行 mask 和 Q 梯度范围亦分开。

10. **“通用”是否仍按 AgileX 排名或隐藏维度？PASS。** 技术01:11、161–167；接口02:T37–T38；专题 §9。能力、坐标、维度、保持和初始化由 adapter 声明；两个不同 schema 回放检验上层边界。Show 也分开语义和本体解释器 [S7]。接口通用不承诺权重通用。

11. **Strands 的 RTC 名称是否被扩大到所有入口？PASS。** 接口02:395；专题 §7.1。本轮固定 run_policy 明确默认 mock、fast_mode，实际执行间隔受 max(action_horizon, execution_horizon) 约束 [S8]。T38 已要求锁入口、provider、模式、horizon 和消费索引；没有把该路径冒称本项目真实异步 RL。

12. **系统代做、代码变化是否被算成 policy 学会？PASS。** 技术01:311–328；接口02:279–307；报告:207–219。独立 policy、辅助系统、持续学习分开评估；双向共同发布，人工分钟、纠正动作和停机单列；冻结权重只采集不算持续学习。净学习增益仍待实测。

## 处理级别

**必须修订：无。** 风险已有约束和验收，尚无实现不构成设计错误。

**可选细化：** T38 的延迟、工时、日志缺口统一成表；stop receipt 写成 schema。本版已有语义，不重复列为遗漏。

**实测门槛：** 驱动停止／保持、独立观察、GPT 质量、双向覆盖、TD 保留率、试验恢复、关闭辅助后的增益。PASS 不替代这些验证。

## 本轮直接阅读的原始来源

- [S1 DAgger 正文](https://proceedings.mlr.press/v15/ross11a/ross11a.pdf)：算法3.1、专家标签与界的条件。
- [S2 OpenETA planner](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/planner.py)：plan、_invariant_obligation_decision。
- [S3 RPent Toolkit](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/tools/toolkit.py)：execute_tool、cancel_active_and_wait。
- [S4 OpenETA registry](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py)：_invoke_tool_handler、_execution_cancelled。
- [S5 Show preemption](https://raw.githubusercontent.com/showlab/Show-Harness/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/preemption.py)：InterruptibleDecider；同提交 plugins/dagger/plugin.py 核得人工键盘意图。
- [S6 ENPIRE reward](https://raw.githubusercontent.com/NVlabs/ENPIRE/99ee90acf65b5b18957c8382ad580db999528be3/enpire/env/forge/cap/reward/gemini_reward.py)：vlm_reward 的缓存返回分支。
- [S7 Show-Harness 论文](https://arxiv.org/html/2609.10522v1)：§3.2 语义动作、本体解释器和反馈循环。
- [S8 Strands run_policy](https://raw.githubusercontent.com/strands-labs/robots/4d0203161a587e29d7912c99da74878e8f989544/strands_robots/tools/run_policy.py)：入口默认值、执行 horizon、simulation.run_policy 转发。
