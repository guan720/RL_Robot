# R10 独立 Harness／融合审查

结论：**PASS；必要修订 0 项；恰好完成 12 项反例质询。** 此结论仅针对冻结文稿的定义、证据边界和融合逻辑，不表示软件验收或真机通过。

2026-09-23。先只读科学家 START_HERE、ROLE、status、INDEX、科研 SKILL 及普通研究流程，不继承暂停审查的成绩。仅以 R10/input 九份 md 为科学输入，按职责定位阅读；未读任何其他审查报告，未写知识库、启动 UPDATE／goal。未安装、运行代码、训练或操作机器人。

文稿简称：S＝主方案；I＝接口契约；A＝异步附录；E＝调研总报告；V／R／H／P＝VLA／复位／Harness／平台专项；README＝开发入口。行号均指 R10/input 冻结文件。

## 先枚举技术点

先枚举：GPT 观察／评分；DAgger；长工具观察；lease／epoch／停止；唯一执行与初始化；双向／恢复；unknown／迟到；TRIAL／发布；建议／真实请求；反馈微步；不同学习目标；多 schema／能力成本。随后打开原论文与固定源码，再形成 12 问，未增候选。

## 实际独立学习的原始证据

- **O1**：[DAgger 原论文](https://proceedings.mlr.press/v15/ross11a/ross11a.pdf)，§2–3、Algorithm 3.1、Theorem 3.1–3.2，印刷页 628–630。
- **O2**：[RPent Toolkit](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/tools/toolkit.py)，`execute_tool`、`cancel_active_and_wait`、`raise_if_cancelled`，L234–335；[API loop](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/planner/api_loop.py)，`solve`、`_build_tools`，L93–135、670–689。
- **O3**：[OpenETA Planner](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/planner.py)，`ToolCallingPlanner.plan`、`_invariant_obligation_decision`，L171–234、373–423；[Registry](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py)，`call`、provenance、`_invoke_tool_handler`，L258–310、1043–1149。
- **O4**：[Show 抢占](https://raw.githubusercontent.com/showlab/Show-Harness/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/preemption.py)，全文 74 行，`InterruptibleDecider.decide`；[Piper 解释器](https://raw.githubusercontent.com/showlab/Show-Harness/137d5718c3b7af0150764d8f9beeb252c9f2794a/interpreters/piper_atomic_controller.py)，L1–92 后端、反馈及初始化说明。
- **O5**：[Strands run_policy](https://raw.githubusercontent.com/strands-labs/robots/4d0203161a587e29d7912c99da74878e8f989544/strands_robots/tools/run_policy.py)，L1–90，记录约束及 `_read_parquet_truth` 开头；未审全部 RTC／设备路径。
- **O6**：[RAPolicy actor 模式](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/awac_actor_loss.py)，全文，默认 likelihood、flow 消融与恢复模式校验；[RT-EXPO learner](https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)，`_jitted_fast_select`、`update_edit_actor`、`update_actor`、`update_critic`，约 L168–227、875–1036。实见窗口切片、Q／熵编辑更新、前缀条件训练及按 replan_steps 折扣。

以上均为选定正文／函数静态阅读。

## 12 项关键反例质询

### Q01 GPT 同时行动与评分，会不会把自己说的 DONE 当成功？

定位 S:113–119、169–179；I:185–201、291。反例为抓空后工具返回成功，模型仅复述动作文本。文稿要求有序图像、本体事实、冻结 rubric 和独立留出审计，unknown 不判失败；未强制换成小模型，也未声称 GPT 已校准。O5 支持区分执行产物和代理自报的必要性。**通过；工位误报／漏报及延迟待测。**

### Q02 把 GPT 换成 DAgger 标注者，是否偷带完美专家保证？

定位 S:41、131–141、283；A:165–190。O1 的聚合机制不证明未知错误率标注者正确。文稿明确只借访问状态聚合，标签另核质量、目标和信息集；晚观察的事后监督首版不混普通 BC。也要求同预算动态 BC 对照。**通过；有用纠正覆盖和可模仿性待测。**

### Q03 长 motion 卡死，打开异步工具开关能否继续看到新观测？

定位 I:43–60、394；H:199、254。O2 显示串行注册与活动操作互斥；O3 的动作后补观察也不是工具执行中的观察。I:58 已规定从 Gateway 只读事件独立订阅，并以长工具／卡死下多批新时间戳验证。**通过；独立观察链及其时延仍须实现验收。**

### Q04 取消云请求、撤销 lease 后立即授予新 epoch，旧命令是否仍会运动？

定位 I:113–146、T07–T09；S:301。O2 的协作取消、O3 的弃等、O4 的弃旧结果都不足以提供物理保持凭证。文稿先封提交、处理队列及在途命令，再核驱动保持、新鲜状态后交接；ACK 丢失不重放增量，重启提高代际。**通过；停止耗时和设备回执待测。**

### Q05 RPent、Show、Strands 和训练 env 各留自己的设备入口会怎样？

定位 S:161–169、253–262；I:T31–T33、T38；H:204。O4 确有具体机器人运动后端，不能仅复制解释器名称便视为无副作用工具。文稿只准一个实体主循环，各组件提交 Gateway；初始化禁隐式双臂 home／RELEASE，DONE／Pause 分别核任务与停止。**通过；旁路写通道排查待测。**

### Q06 A→B 成功但 B 不可抓，恢复放回 A 能否算正常反向成功？

定位 S:88–109；I:259–265、T17–T19；R:22–34、169–175。文稿用同一 θ、目标条件 actor/Q/数据，换向切 episode、flush/reprime，并另验下一方向 init_set；异常恢复单列，不能挽回旧任务成功奖，也不由固定 reset 替代反向学习。**通过；双向迁移和循环可靠性待测。**

### Q07 正向评分在反向开始后返回，unknown 能否先用旧成功分占位？

定位 S:143–151；I:165–183、T18、T20–T21。文稿按历史评分、历史动作标签、当前控制分别授予资格；缓存含 goal／episode／证据／版本，pending 不广播最近 reward，终局按事件去重，旧结果不得回退当前裁决。**通过；乱序、重复回调、缺图回放待测。**

### Q08 新代码通过静态检查后自行改 rubric，或回滚软件就宣称现场恢复？

定位 S:153–157；I:193–201、269–297、T23、T27。候选先在预算内 TRIAL，物理效果及回归核验后发布；候选数据先隔离，不得改评分、权限或预算。版本包依赖和污染标签追到后继权重，软件回退后重新观察现场。**通过；门禁与发布中断测试待执行。**

### Q09 未执行建议配上 policy 的后继状态，是否只是合法离策略数据？

定位 I:205–217、255、369；A:63–93、192–231。不是：行为动作身份错误。文稿将纯建议长期留作合格 BC；真实终局请求例外有事前 admission、冻结输入和原计算结果，不能事后补 ID，也不声称其物理激活。**通过；该例外与影子查询必须分别测。**

### Q10 微步反馈成功，能否把整条轨迹倒填成早先一次 U 和普通 BC？

定位 S:165；I:201、257、T32；A:182–190、233–255。不能：晚图像改变信息集。文稿保留逐微步事实，同协议完整 U 才进主宏 TD；反馈轨迹的监督需满足明示定义，微步 RL 另建目标，flow 缺标签还检查输入／注意力污染。**通过；可用 BC／TD 密度待测。**

### Q11 RAPolicy／RT-EXPO 接入后能否只换 mask，继续共用原 target？

定位 S:289–297；A:329–339；V:122–153、334–370；P:6–9、35。O6 实见默认 likelihood 与 flow 消融分离，RT 编辑 Q／熵和原生前缀训练分离。文稿要求原生 Q/V、噪声、回报与队列另行定义；RT 采用独立协议，不能复用参考队列 Bellman。**通过；尚未完成改造已明示，无现成兼容承诺。**

### Q12 两个 schema 跑通且系统成功率提高，是否就能宣称跨本体自学习？

定位 I:279–291、388–398；S:11、271–279、323–336；E:207–221；README:25–31。不能：软件通用、policy 提升与人工减少是不同证据。文稿用两种模拟 adapter 验边界，不承诺权重通用；同 checkpoint 双向独立评估、系统辅助及自主学习成本分账，含值守、示范、恢复、GPU／GPT和审核。AgileX 仅计部署成本。**通过；实际增益与完整成本待测。**

## 必要、待测与可选

必要修订：**0**；反例均已有明确约束或阻断条件。

待测：GPT 校准／纠正覆盖、持续观察、设备停止、schema 回放、数据资格、双向增益及成本。均已列为实施门槛，不将尚未实验重复判作文稿缺陷。

可选：实施时建立 T31–T39 测试产物与反例索引。

最终计数：12 问，12 项文稿级通过，0 项必要问题；PASS 不外推至实现、性能或物理安全保证。
