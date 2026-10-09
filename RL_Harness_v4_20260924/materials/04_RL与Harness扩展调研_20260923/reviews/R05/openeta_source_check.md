# R05 补漏：OpenETA 的骨架候选资格

2026-09-23｜只读科学家入口、技能及研究流程已加载；仅静态源码核查。

**结论：本轮应将 OpenETA 加入与 RPent、Strands 的同预算通用骨架短名单，不能只作机制引用。** 它已有可换 Planner、具身工具门禁、事实记录与评测代码，满足候选资格；无需先证明胜过 RPent。缺少本项目在线队列 RL 不构成差别淘汰理由。最终采用谁仍取决于共同接口预检和改造成本，当前证据不支持“最优”或直接替换。

固定版本为 [`7d4a0a1522ba8ebbd362bde880bad81d2a98f15e`](https://github.com/OpenMOSS/OpenETA/commit/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e)，提交时间 2026-09-06；通过 commit/main、固定 README 和 GitHub API 交叉定位。下文代码行号取 API 原文件，非网页抽取行号。

## 源码已经支持什么

| 核查点 | 实现证据与边界 |
|---|---|
| 观察义务 | `planner.py` L182–211 在模型调用前执行 `_invariant_obligation_decision`；L386 起遇缺新观测或运动结果未知，且 observe 可执行时，由 Host 直接派 observe。`episode.py` 的 `ToolFeedbackEpisodeEnvironment.step` L886 起检查可信 receipt；连续 3 次刷新失败截断。故不只是提示词要求，但也不能外推到任意自定义 Planner/工具路径。[Planner][p]、[Episode][e] |
| 阻塞与顺序 | `runtime.act` 的实例锁覆盖 plan→compile；Episode 每轮等待线程完成再更新观测，是逐工具闭环，未证明独立高频观察。`pipeline._compile_tool_batch` L1223 起拒绝不可批处理工具，但以 for 循环同步调用 handler。README 的“只读可并行”不能当作该路径已实现并行的证明。[Runtime][r]、[Pipeline][a] |
| 取消与控制权 | `registry._invoke_tool_handler` L1152 起用线程执行，取消抛 abandoned，不杀正在运行的 handler；`episode.interrupt` L712 起发 cancel 并请求 close，清理可返回 pending。UR5e 的 moveJ/moveL 未使用声明的 blocking 参数。已有软件边界仍不等于跨进程唯一设备 owner、队列排空或 stop_ack。[Registry][t]、[Episode][e]、[UR5e][u] |
| 失败与纠正记录 | Registry 保存工具起止事件并将异常结构化；Rollout 分存模型校验尝试、工具结果、逐 runner turn 转移、回合初态和结果。失败经验可触发 Skill review。但 recorder 捕获持久化异常后继续执行；“immutable”不等于完整、事务性逐控制帧账本，也没有由此证明纠正已进入 BC/RL。[Registry][t]、[Rollout][d]、[Review][s] |
| GPT-6 替换 | `OpenAICompatiblePlannerBackend` 有真实 chat/completions transport、model/base 配置、多图及主备端点；另有 Callable backend。可作为 GPT-6 接入基础，具体模型 ID、参数、XML输出、多图及迟到取消仍需测；未运行 GPT-6。不要将文件内另一个 placeholder 商业后端误当成唯一实现。[Backend][b] |
| Eval / replay / evolution | 有独立 episode、调用/时间/token预算与训练/验证流程。`validation_has_no_regression` L740 起核查配对成功、失败和求助数。现 `logger/replay.py` 读 episode.json/steps.jsonl 并生成时间线/视频，不是在线 RL replay，也不能默认直接消费新 rollout/。[实验代码][x]、[评测文档][v]、[Replay][q] |

## 不能跨越的证据边界

[论文 v1 正文 §5–8](https://arxiv.org/html/2608.03924v1)区分全栈与 Codex 轻量配置：后者的 130 任务 Pass@5 不能贴给当前 main 全栈或当真机成功率。§6 明说没有候选通过全部晋级门禁，尚无可复现的自进化成功率提升；门禁的存在与学习有效分开。UR5e 是接口实现及定性演示证据，不能迁移成其他本体的控制性能证明。

[固定 README][readme] 将 OpenVLA、openpi 等 policy adapters 标为尚未适配；35 个“验证工具契约”也不能解释为35种策略、本体或训练器。开放资产包含 Host/Planner、工具接口、仿真与 UR5e 路径、评测配置和日志代码；[根许可][license]为 Apache-2.0，外部感知模型、权重、数据、SDK各自另核。未据目录存在声称全部依赖和实验产物完整可用。

## 与 RPent 比较必须计入的改造

RPent 的固定旧审计已有 VLA/解析原语及真实动作与预测 chunk 分存；OpenETA 当前长处是显式 fresh-observation、工具结果契约、失败/模型尝试记录和配对验证。两者优势不同。RPent 默认成功 SFT 导出需扩展，OpenETA 的原始 rollout 同样需要 learner exporter；二者都不能直接承载本项目异步队列 RL。RPent 依据为本项目既有 `09_RPent与Harness联合选型.md` 的 eb269c8 审计与本轮 6ee7069 选定差异，未重新全审其 HEAD。

共同预检应固定同一 GPT-6、工具、模拟 adapter、任务/seed及调用和动作预算，分别测：观测龄期与尾延迟、迟到命令拒绝、接管到 stop_ack、失败/纠正事实完整率、模型及本体替换改动量。两条路线均必须补独立观察时钟、唯一 Gateway及owner epoch、request→commit→activation与实际逐帧账本、版本化rubric和BC/Q资格、共享正反向policy/learner。OpenETA额外计入policy adapter缺口；RPent计入Flywheel真机/失败出口改造。硬件品牌只影响adapter工时，不决定短名单。

本次打开论文正文、上述文档及固定代码关键段；未安装依赖、跑测试、接模型或机器人，未全库审计。命令行直连 raw 曾超时，后以网页原文和 GitHub Contents API 补读；未冒称本地完整快照。候选资格已获支持，运行可靠性、端到端成本与学习收益仍待共同预检。

[p]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/planner.py#L386
[e]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/episode.py#L712
[r]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/runtime.py#L173
[a]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/pipeline.py#L1223
[t]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py#L1152
[u]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/real/robots/ur5e.py#L166
[d]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/rollout.py#L214
[s]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/self_improvement.py#L528
[b]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/backends/planner.py#L337
[x]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/experiments.py#L740
[v]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/docs/parallel-simulator-evaluation.md
[q]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/logger/replay.py#L14
[readme]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/README.md
[license]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/LICENSE
