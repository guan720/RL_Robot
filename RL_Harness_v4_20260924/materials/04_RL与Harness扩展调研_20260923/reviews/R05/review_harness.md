# R05 独立审查：Harness 与 RL 融合

日期：2026-09-23。结论：**PASS**。审查问题 10 个；必要错误／遗漏 0 项；可选整理建议 2 项。

## 关键点与范围

检查候选选择能否被证据推翻、GPT 自动观察纠正是否代替常态人工、观察是否受长工具阻塞、唯一执行权与物理停止、双向共享学习、纠正时间因果性、通用 adapter、评分及发布边界。PASS 仅表示本轮未发现必须修改的文档问题，不表示软件或真机验收通过。

已只读 START_HERE、ROLE、status、知识索引及 embodied-research-scientist 技能；未启动知识更新，未读取旧轮审查结论。输入限于 R05/input。以下定位简称：A＝技术01，B＝接口02，C＝异步06，R＝研究总报告，H＝research/03_Harness扩展调研；均指冻结副本。五份已阅读全文，其余冻结文件不作为本次独立判断依据。

## 本轮独立来源学习

- [Show-Harness 固定 preemption.py](https://raw.githubusercontent.com/showlab/Show-Harness/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/preemption.py)：线程中的旧决定继续计算，结果按 stale／generation 丢弃；这是模型结果处理，不能提供设备停止证明。H§5.2 对该边界的描述成立。
- [RPent 固定 api_loop.py](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/planner/api_loop.py) 与 [toolkit.py](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/tools/toolkit.py)：当前提交仍注册 sequential 工具；execute_tool 先检查 active operation，之后才区分 readonly；取消等待依赖工具返回。独立观察与本地停止不能只靠原工具循环。
- [Strands 固定 run_policy.py](https://raw.githubusercontent.com/strands-labs/robots/4d0203161a587e29d7912c99da74878e8f989544/strands_robots/tools/run_policy.py)：存在确定性的多 episode 循环和读取记录元数据的计数核验；该入口明确实际消费长度及 fast_mode 参数。不能由某条 RTC 路径推定所有入口同义，B:T38 已要求逐入口核对。
- [DAgger 原始论文页](https://proceedings.mlr.press/v15/ross11a.html)：理论陈述具有额外归约假设。A§2 将访问状态上的标签聚合作为借鉴、没有向未知质量的 GPT 标注直接移植保证，表述适当。
- [DimOS 官方操控文档](https://github.com/dimensionalOS/dimos/blob/main/docs/capabilities/manipulation/index.md)：可见 mock／real adapter、协调器、轨迹与规划接口；这些支持把它列作运行层候选，不能证明本项目 RL 数据契约已完成。此链接为本轮访问状态，未冒充固定源码快照。

以上为实际新开原始页面与选定函数阅读；没有安装、运行或做全库审计。

## 具体问题及裁定

1. **RPent 是否因先用而不可替换，Show 是否因 AgileX 获胜？——通过。** A:264–279、R:193–211、H:203–205 规定同 GPT／工具、模拟 adapter 与故障回放比较；其他底座更少改造即可切换。Show 仅为动作解释模块候选，通用性优先于现成硬件适配。不存在已证明全栈冠军的宣称。

2. **GPT 是否真正提供纠正，而非仍要求人工 DAgger 或强上游 policy？——通过。** A:121–169、B:54–60 明确替换人工 verdict，GPT 可给轨迹、参数或受限程序；纯标签持续聚合，不要求另有强 policy。独立离线校准计入人工成本，未被偷换成每回合在线人工批准；错误纠正不自动成为专家标签。

3. **长 motion／卡死工具能否阻断主观察？——通过。** 固定 RPent 源码确有互斥限制；B:58 明确订阅 Gateway 的只读图像／遥测事件，不把 observe 排在活动工具之后，并要求长工具与卡死场景中仍送达新时间戳观测。B:391–393 又纳入候选统一验收；“异步开关”不算通过证据。

4. **取消是否被误当物理停止，是否存在第二条设备写路径？——通过。** B:113–146、T31/T33 区分 ticket、quiesce receipt 和新代际租约；在途动作、部分生效和未知执行另记。RPent、解释器、训练 env、reset、TRIAL 均走唯一 Gateway，本地保护不等云端。持物保持依控制模式决定，没有统一断电或默认 RELEASE 的要求。

5. **正常反向是否退化为脚本复位，异常成功是否污染正向回报？——通过。** A:88–109、B:259–265 要求同 θ、双向 RL、目标贯穿 Q／target／采样；成功后先验下一 init_set。掉落恢复独立记账，换目标切 episode、不跨目标 bootstrap，恢复完成不能追认原失败任务成功。

6. **Show 式反馈动作、未执行建议和真实纠正能否正确进入 BC＋RL？——通过。** A:159–169、B:205–217、C:165–190/233–257 区分冻结起点的完整 U 与后来读图的反馈微步；后者不能倒填成早先 chunk。纯查询可长期 BC，不能配他者后继做 TD；实际同协议纠正能兼有两种资格，失败 TD 与 BC 质量分开。

7. **迟到／unknown 评分是否串目标、伪奖励或奖励行动者自证？——通过。** B:165–191、C:229–231 将历史评分、标签、当前控制分开，缓存绑定证据及版本，unknown／pending 不填零或旧 reward。DONE 不直接判成功；终局使用证据充分时刻，不能按回复时间或首次接触随意回溯。独立留出审计与发布前阈值已明示。

8. **比较是否只对齐相机数量，却给某方法额外状态或未来帧？——通过。** A:275–277、R:201、B:T34 要求逐模块记录视图、历史、派生状态、可用时间及成本；统一可获得信息或输入消融。RT-EXPO 与队列方案各建时间协议，不混 replay／Bellman；训练专用信息须声明。

9. **通用接口是否实质写死 Piper／固定动作维度？——通过。** B:387–393 要求能力、schema、坐标、控制模式、反馈与停止声明；两个不同 schema 的模拟 adapter 检查上层依赖。更换本体隔离旧 replay，显式验证转换后才复用；这被准确限定为软件边界检查，没有包装成跨机器人实测。

10. **系统更会救场是否被当作 policy 学会，错误标签撤销是否只改 buffer？——通过。** A:311–328、B:269–307 分开独立 policy、辅助系统和自主学习成本；同一 checkpoint 双向评估，困难与未知试次保留。版本包在控制边界切换，污染沿 manifest 追到后继权重，必要时回退重训。未把“未运行”说成证据，也未据此自动判文档缺陷。

## 必要修改与可选实施细节

**必要错误／遗漏：无。** 当前设计所需的控制、数据、证据和可推翻边界已能定位，尚待实测事项有明确声明。

两项可选整理不影响 PASS：①把 B:T38 已要求的观察延迟、日志缺口、替换路径和适配工时集中成候选对照表；②在发布验收表引用 B§6.2 的未知试次和独立审计规则。无需另增实施范围或预填实测阈值。
