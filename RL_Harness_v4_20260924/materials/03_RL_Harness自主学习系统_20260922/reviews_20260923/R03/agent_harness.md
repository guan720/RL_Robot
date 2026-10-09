# R03 独立审查：RPent 与 Harness 兼容性

结论：**PASS（冻结稿的设计／来源／接口兼容性审查）**。本轮未发现必须阻断该稿的未定义关键契约；不代表 RPent 已完成移植，也不代表 GPT-6 工位能力、学习收益或无人运行已经实测通过。判据未因连续通过计数调整。

审查日期：2026-09-23。只读本轮 `input/README.md`、`01`、`02`、`06`、`07`、`09`，未读取其他轮次 review，未修改知识库；只写本文件。以下冻结稿位置均相对 **R03/input/**，行号按 UTF-8 实际文本计数。上游源码统一固定为 `eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1`；官方 `latest` 文档作为当日说明，不冒充固定提交的一部分。

## 先枚举的关键点

1. “优先 RPent”能否限定为认知／工具工程适配判断，而非学习效果或最低改造成本结论。
2. 长 motion 未结束甚至卡死时，GPT 观察是否仍能收到新事实。
3. 只读遥测是否绕开 Toolkit 活动锁，同时不新增设备写入口。
4. 多进程／多 session 唯一 owner、控制代际、在途取消和驱动保持回执是否可区分。
5. 正反换向后的旧评分、旧控制建议和缓存是否分别处理。
6. 人工 verdict／scene reset 是否真正替换，且未把困难状态自动判成功。
7. TRIAL 的生成、评分、预算和设备权限是否分离；记忆 verified 是否被误用为发布资格。
8. Flywheel 的真机持久事实、失败 RL、未执行 BC 和双 task 出口是否补齐。
9. 真正送入 VLA 的目标能否改变，并贯穿 Q／target／replay。
10. 完整抓取—运输—释放是否由同一 policy 独立评测，而非让 Harness 永久代做。
11. GPT-6 的图像／工具 API 路由是否有原始依据，机器人可靠性是否仍需校准。
12. 反馈式微步纠正是否错误拼成过去已承诺的宏动作；实测 gate 与设计缺陷是否分开。

## 本轮实际打开的一手来源

不是复用冻结稿的引用摘要：本轮通过网页工具实际打开并定位以下内容，另用只读、内存式网络请求交叉取得部分固定源码。

| 类别 | 实际访问来源与核到的内容 |
|---|---|
| 原始论文 | [Harness VLA v4](https://arxiv.org/html/2607.08448v4)，2026-09-02；§2 的冻结 VLA、固定原语与轮次式调用；§5 明示缺少环境奖励／人类偏好的联合微调。其系统收益不能推出完整 policy 在线变强。 |
| 固定代码 | [Toolkit](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/tools/toolkit.py)、[API planner](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/api_loop.py)、[双 Franka 工具](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/tools.py)、[真机 Toolkit](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/toolkit.py)、[环境服务器](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/robots/dual_franka/env_server.py)。 |
| 固定数据／权限代码 | [EpisodeWriter](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/episode.py)、[export](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/flywheel/export.py)、[MemoryManager](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/memory/manager.py)、[Codex planner](https://raw.githubusercontent.com/RLinf/RPent/eb269c8a278b0ef717d61a3f55891c9ce2ec7eb1/rpent/planner/codex.py)。 |
| 项目官方文档 | [Architecture](https://rpent.readthedocs.io/en/latest/rst_source/development/architecture.html)、[Planner](https://rpent.readthedocs.io/en/latest/rst_source/usage/configure_planner.html)、[Flywheel](https://rpent.readthedocs.io/en/latest/rst_source/usage/flywheel.html)、[Dual Franka](https://rpent.readthedocs.io/en/latest/rst_source/usage/dual_franka.html)。前三页分别核认知／工具边界、Responses 支持及 LIBERO evaluation／成功导出限制。 |
| 比较与模型官方来源 | [RoboRSI 官方博客](https://lab.noematrix.ai/blog/2-roborsi/)，及其 [固定 pi0_posttrain 入口](https://raw.githubusercontent.com/nssmd/RoboRSI/9b644d270560c440d760965cf1b859df674459de/roborsi/embodied/skills/_lib/rl/pi0_posttrain/policy.py)；[GPT-6 Astra 模型页](https://developers.openai.com/api/docs/models/gpt-6-astra)与[函数调用文档](https://developers.openai.com/api/docs/guides/function-calling)。 |

已覆盖论文、固定官方代码、官方文档三类 primary，另外访问比较对象和模型官方来源。Shell 对部分 raw URL 超时，关键文件已经由网页工具实际读取；未安装 RPent、未执行其测试、未训练或操纵真机，也未把下载尝试当作运行证据。

## 独立问题与回答

### Q1：把 RPent 排在 RoboRSI 前面，是否过度声称？

**PASS。** 冻结稿位置：`09:5–7、22、80–94、126`；`01:249–259`。推荐对象被限定为认知／工具骨架，明确没有现成无人在线 RL，也未声称最低工程成本。RoboRSI 博客强调技能树、诊断和修订；固定 `pi0_posttrain.run` 确实抛出 `NotImplementedError`，但 `09:94` 把判断限定在该入口，没有外推全仓。

反例：以 RPEnt 仿真系统分数或与 RLinf 同组织为由，直接声称其 learner 优于 RoboRSI。现稿 `09:7、92、126` 已禁止这种推断。修法／落实：保留该限定，后续以共享目标、数据桥、异步控制的实际适配结果重新决定选型；不能把工程优先级改写成已验证的效果排序。依据见上述 v4、Architecture、RoboRSI 原始来源。

### Q2：一个长 motion 尚未返回，GPT 能否持续看见机器人？

**PASS（契约已定义，尚未实测）。** 位置：`02:47–58`、`01:257`。固定 `api_loop._build_tools` 把工具设为 `sequential=True`；`Toolkit.execute_tool` 先检查 active operation，再判断 readonly。因此仅把 observe 标只读或打开模型并行工具，不能解决活动工具占用。

反例：运动 RPC 卡死，观察调用仍排在同一工具通道；系统只在结束后得到最后一帧。现稿明确订阅 Gateway 的只读图像／遥测事件，并要求长工具运行及模拟卡死时仍送达多批新时间戳观测，还能发起取消／本地保持。修法／落实：按该测试证明采集、发布、消费都不依赖活动工具完成；不能仅证明另建了一个线程。没有证据前不得宣称持续监控已完成。

### Q3：Toolkit 的锁和 cancel 是否足以避免两个进程同时写设备？

**PASS。** 位置：`02:115–146、320、323–325`、`09:48–54`。上游锁是 Toolkit 实例内的 `threading.Lock`；`cancel_active_and_wait` 设置取消事件并等待工具返回，未提供设备级租约或物理保持证明。双 Franka 工具在同步 predict 前后、逐动作边界检查取消，也不能保证在途 RPC 立刻结束。

反例：进程 A 的 cancel 回来前，进程 B 直接创建另一机器人连接开始纠正。现稿把实体连接收敛到按 robot_id 独占且有递增代际的 Gateway；新 owner 需要当前代际 quiesce receipt，调用方自报 stopped 无效。修法／落实：T04/T07/T09 必须覆盖跨进程竞争、在途部分生效、ACK 丢失和重启；未知执行不得重放，未确认保持不得交接。这是足够明确的契约，数值停止时限待工位预检不构成文档 FAIL。

### Q4：正向旧评分晚到，能否错误终止反向或污染评分缓存？

**PASS。** 位置：`02:165–183、334–337`、`01:140–148`、`06:229–231、263–268`。历史评分、历史动作标签与当前控制资格分开；缓存绑定 goal、episode／证据区间及评分版本，unknown／pending 不回退为上一奖励。

反例：B→A 已开始，旧 A→B 请求返回 success，覆盖“最近分数”；重复轮询又重复发终局奖励。现稿禁止旧裁决覆盖新状态，历史标签只归原 episode，成功事件去重，当前建议另核 goal／epoch／新鲜度。修法／落实：执行 T18/T20/T21，核对缓存键、历史标签账本和控制队列三处结果；晚到终局按证据充分时刻归属，不能任意回溯到首次接触。

### Q5：移除人工 verdict/reset 是否只是把人类输入替换成常量 true？

**PASS。** 位置：`09:62–68、121`、`02:56、185–201、263–265、289–291`。固定真机 Toolkit 的 motion／finish 与操作员判断相关，审计写 `success_source=operator`。现稿要求用固定 rubric 的 GPT 观察判断替换日常 verdict，普通反向 policy 负责反向任务，异常恢复另记；反向起态仍须满足 init_set。

反例：原 `_scene_ready` 或 `_operator_verdict` 直接置真，B 区边缘不可抓物体仍被强行启动；人工在后台不断复位却称无人。修法／落实：替换判断与状态路由而非跳过检查，保留 unknown／拒绝／恢复失败及人工成本，实测 T19/T29。小的文字补强见文末：上游 evaluation 路径同样有人工 verdict，不能只改 exploration。

### Q6：TRIAL 候选能否改自身评分、预算，或绕 Gateway 运动？

**PASS。** 位置：`09:70–76`、`01:150–154`、`02:29–37、197、339`。固定 Codex planner 默认 `Sandbox.full_access`、`ApprovalMode.deny_all`，确实不能视为隔离沙箱。冻结稿要求生成进程、固定评分、设备凭据和执行工具权限实际分离；候选只走受限 API，检查后在预设预算内自动试验。

反例：同一候选可写 rubric 文件、改预算，或直接 import 设备驱动，随后自行写“回归通过”。修法／落实：落实 T23，并验证即使候选进程失控仍无法取得这些权限；验收主体／配置不能由候选改写。契约不要求每次人批，也没有把提示词约束当作权限边界。

### Q7：Memory 的 verified 能否直接授予动作或 BC 资格？

**PASS。** 位置：`09:72、76、105–106`、`02:52、195–201`。固定 `_merge_evidence` 的 verified 是按 evidence cells／tasks 数量产生的记忆等级；不是工位覆盖、程序回归或标签质量证明。

反例：两任务三个记忆条目就让一个新恢复程序自动绕过 TRIAL；整回合成功后全部动作自动进入 BC。现稿明确记忆置信度不授予运动或监督资格，Flash 也须受限、可中断并重新核验实物。修法／落实：权限与发布引用独立版本包，质量依据来自可追溯行为与标签审核；memory 合并只更新经验内容。

### Q8：Flywheel 能否直接承担真机失败 RL 与长期纠正池？

**PASS。** 位置：`09:36–46、104`、`02:51、205–217`。官方说明只支持 LIBERO evaluation 的采集／成功导出；固定 EpisodeWriter 用列表累积，finalize 才写 NPZ 并改名，`action_source` 由 VLA ID 是否存在推导。记录形状与 VLA proposal 是有用起点，但不等于真机持久 RL replay。

反例：将成功导出器作为唯一数据源，丢失全部失败；回合未 finalize 就断电丢失事实；把脚本、纠正、保持和候选都压成一个来源值。现稿要求真机逐帧事实 journal、增量落盘／恢复、失败 RL 视图、独立纠正池及 request/commit/activation。修法／落实：RL 直接读取持久事实视图，成功出口仅用于符合条件的 BC；对断电、重载和多来源索引做证据核验。

### Q9：正反两任务会不会在 Flywheel 导出时被合成一种任务？

**PASS。** 位置：`02:60`、`07:95–105`。固定 `export_lerobot` 收集所有 episode 的 `task_language`，数量不为一就抛错，导出各帧统一使用该 language。

反例：把正反成功 episode 一次传入原导出器；为了避错把两者语言改成相同句子，导致 goal／奖励串线。现稿已经明确正反分开导出、版本化 loader 保留目标后合并，或改造逐 episode 目标格式；至少各一条样本做导出／重载往返。修法／落实：该往返检查同时核规范 goal 和奖励归属，不能只看文本或张量形状。失败 RL 不得借此成功出口进入训练。

### Q10：日志中的反向 prompt 是否真的改变 VLA 动作条件？

**PASS。** 位置：`09:56–60、103`、`02:91–93、225、333、348`。固定 `_run_named_vla_skill` 记录 requested_prompt，但赋给 observation.task_descriptions 的是 `_vla_instruction`，所以仅改 planner 日志不足。

反例：同一 checkpoint 的日志写 B→A，模型实际上持续接收清桌固定指令；Q 又没有目标输入。现稿要求结构化 goal 贯穿 actor、Q、target、replay、rubric 和评测，T17 先查计算图再以已知小样本任务验证条件化行为。修法／落实：记录并核对实际 model input；随机初始模型暂时动作相似不是失败证据，但字段存在也不是目标已被消费的证据。

### Q11：独立评估能否证明完整 policy 学会抓放？

**PASS。** 位置：`09:109–113`、`01:259、283–300`、`02:279–291、344–345`。v4 把冻结 VLA 主要用作局部接触原语，运输／姿态／释放等交给解析原语；这与本项目完整抓放学习的目标有实质差别。冻结稿主动指出了差别，要求关闭 Harness 动作辅助后覆盖完整任务。

反例：Harness 总是完成抓取或运输，最后只让 policy 释放，却把辅助系统成功率称作 policy 成绩。修法／落实：同一 checkpoint 从预定义合法起态完成正反全部阶段；独立 policy、系统辅助、自主学习成本分账，保留困难起态、中止、拒绝和人工成本。无辅助评估仍可保留统一底层保护、事实记录和固定评分，这不等于允许任务动作代做。

### Q12：GPT-6 接入是否建立在真实官方能力上？

**PASS（预检前不能声称接通）。** 位置：`01:112–116`、`02:54、152–163、187–189`、`09:30`。当日官方 Astra 模型页列图像输入，不列视频支持；函数调用文档明确 GPT-6 Astra 的工具调用需 Responses API。RPent 官方 Planner 文档明确 API 路径支持 Responses，故多图观察＋自定义工具路线有依据。

反例：用 OpenAI-compatible Chat Completions 路由配置 Astra 工具循环，或把实时视频直接传入而无需抽帧；结构化输出正确就视作抓放判断可靠。现稿保留模型／provider／多图／工具格式实测，按抽帧观察包处理，并保留工位校准与独立审计。修法／落实：预检显式选择 Responses 路由，做多图往返、工具结果及时间身份核验；官方通用模型能力不能替代工位准确率、反应时间和动作可达性。

### Q13：反馈式纠正能否伪装成过去已经选好的下一槽动作？

**PASS。** 位置：`06:165–190、237–257`、`09:113`、`02:247–257`。这点与 Harness 数据桥直接相关：一个真实的低层微步序列，不自动是槽起点固定信息集下选定的完整 U；纯影子标签也没有实际控制请求的环境后果。

反例：帧 107 看见滑落后逐步重抓，再把这些微步拼成帧 100 决策；或者复制一个正确单步填满 n 步，配 policy 原动作的后继状态。现稿禁止两者，要求同信息集／同队列协议的完整下一槽标签，反馈微步事实长期保留、按另行定义的监督资格处理，抢占宏 TD 隔离。修法／落实：T14/T15/T16 与 06 的手算例检验信息时刻、独立 mask 和 loss 路由；不能因最终纠正成功就解锁所有数据。

## 非阻断补强与实施 gate

1. **文字精度：`09:66` 可将“尤其是双 Franka exploration”补成“exploration 及 evaluation 路径仍有人工判定”。** 固定 `DualFrankaToolkit._register_tools` 在非 exploration 下将同名工具映射到 `_evaluation_verdict`，`_evaluation_finish` 仍要求 operator。现稿 `02:56` 和 `09:68、121` 的替换要求已涵盖日常判定，因此不构成逻辑缺口；补字可避免实现者只修一条路径。
2. **预检明确性：`02:54`／`09:30` 可直接写入“GPT-6 Astra 工具调用选择 Responses 路由”。** 目前保留 provider 路由预检已足够区分未知与已实现；加入官方必要条件可减少错误尝试。
3. **必须执行但本轮不自动判 FAIL 的 gate：**长工具卡死时新观测仍更新；跨进程竞争／失联／重启后唯一 owner 和保持回执；正反各一条导出重载；人工判定／复位替换后的 unknown 与 init_set；TRIAL 越权拒绝；同一完整 policy 双向无动作辅助评估。`02:313、350` 明示全部待实现／待执行，相关数值须由实际硬件和任务需求确定。

若后续实现不满足这些 gate，应阻断部署或对应结论。当前审查的是契约是否定义且与原始证据相容，不以“还没做真机实验”推翻一份明确声明尚未实施的设计。上述核心运行场景都已有可判定要求；本轮没有把本应定义的契约缺口降格成实测未知。
