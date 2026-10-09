# R06 Harness／纠正／接口独立审查

结论：**PASS**。12 个具体问题全部通过；必须修订项 0，可选实施项 2。仅覆盖冻结设计与所核来源，不代表集成、训练或真机验收完成。

2026-09-23。已只读科学家 START_HERE、ROLE、status、knowledge/INDEX及科研技能。审查 R06/input 的9文件，重点为技术01／02／06、总报告与 Harness 专题。未读旧轮结论；允许的补核资料仅用于定位 URL，随后独立打开原始来源。

先枚举：骨架比较、观察／停止／执行入口、GPT与DAgger、未知评分、反向与恢复、事实与训练资格、反馈时间、代码发布、开放资产。下文技术01／02／06对应技术方案、接口契约、异步附录；H为 Harness 专题。行号指冻结文件。

1. **OpenETA 是否因缺在线 RL 被淘汰，RPent 是否预设胜出？——通过。** 总报告143、209–215及技术01:273要求相同 GPT、工具、双模拟 adapter 和故障回放比较，允许更低改造成本者替换 RPent。H:254–256未把契约或自演化宣传当成收益；OpenETA 论文确实没有候选通过晋级门槛。[原论文][S1]

2. **动作后再观察，是否足以称为持续独立观察？——通过。** 实读 OpenETA planner 的 host observation obligation；RPent 当前固定 API 仍注册 sequential=True，Toolkit 在 handler 前检查唯一活动操作。技术02:58与393明确另订阅只读遥测，并用长工具卡死测试验证，未把上游串行工具循环当成所需监测链。[OpenETA][S2]、[RPent][S3]

3. **取消工具请求是否误当成机器人已停止？——通过。** OpenETA registry 的取消路径抛出 abandoned，后台 daemon handler 可继续运行。技术02:115–146要求封新命令、处理在途动作、取得 quiesce 回执后交接，未知增量不重放；T09覆盖重启与 ACK 丢失。源代码支持必须新增实体确认的判断。[取消实现][S4]

4. **Strands 的广泛功能是否被当成当前所有入口都已具备 RTC／真实训练？——通过。** 固定 run_policy 确实读取磁盘 episode 数，而不是信任代理叙述；这只证明所读入口的记录核对。H:142–148区分仿真 RL、设备范围与修复，技术02:395要求固定入口、provider、fast mode和真实消费索引。没有借单一路径替整库作担保。[固定执行工具][S5]

5. **GPT 是主观察和持续纠正来源，还是只做复位；Show 是否被误称为现成自动 DAgger？——通过。** 技术01:115–139保留 GPT 评分、纠正与访问状态聚合，并承认教师质量未知。Show 插件实际捕获人工键盘意图与 generation 变化；H:110明确这只是可替换意图生产者的参考，未宣称自动 DAgger＋RL 已实现。[插件][S6]

6. **DONE、unknown、旧缓存能否直接变成成功或失败奖励？——通过。** Show runner 用最终 DONE 作为完成信号；Zero2Skill lenient 允许未知视觉判定，其规则更新还保留旧 manifest。H:112、270准确指出差别；技术02:167–191与T20–T21要求证据绑定、去重、pending／unknown及独立校准，未复制这些上游默认值。[runner][S7]、[整理脚本][S8]

7. **常态 B→A 是否仍共享学习，异常恢复是否污染正向结果？——通过。** 技术01:90–109与技术02:259–265要求目标进入 actor／Q／标签，同一 checkpoint 双向发布，换向清队列并检查 init_set；掉落恢复独立记账，不能补成正向成功。

8. **事实账本是否把提议、驱动命令或测量混成动作真值？——通过。** 技术02:64–85分开 proposed_action、a_rl、driver_command、measured_state，并规定限幅位于接口哪一侧；执行索引绑定绝对帧、来源和部分生效。技术01:262及T31把解释器、平台 env、reset全部收口到同一 Gateway，纠正工具没有独立设备写权。

9. **未执行建议是否伪造 TD，真实延迟决策是否又被误删？——通过。** 技术06:65–95、136–180严格区分 request／commit／activation。纯建议可长期 BC；实际已接纳请求在本槽 C 终止时，可保存原在途 U 做 terminal critic，未声称 U 已物理执行；动作未知不造 U，终局不重写前驱 target。技术02:T11、T15分别覆盖两类边界。

10. **语义动作解释器逐步反馈后，是否倒填成起点已经决定的整块标签？——通过。** 技术01:163–169、技术06:184–190及239–255把冻结信息下展开与新观测反馈分开。慢 GPT 可先保持再重新起步；中途改 C 的宏 TD 隔离，微步事实仍保存；一步标签不能重复填满 n 步，flow 部分标签不只在 loss 末端乘 mask。

11. **生成代码能否改评分、直接写设备或在 chunk 中途发布？——通过。** 技术01:155–157允许预授权范围自动 TRIAL，未强加逐次人批；技术02:T23及271–297固定权限、双向版本包、边界发布与标签污染追踪。软件回滚后仍需重新观察物理状态。此设计满足自主试验要求，也未把静态检查等同物理验证。

12. **通用性与可取得代码是否被品牌适配或论文宣传替代？——通过。** H:206及技术02:T37按能力／schema／adapter评价，硬件适配只影响部署成本；更换本体不默认复用权重与 replay。实际打开 HALTER 仓库仍仅见 README，Guava 标 Code coming soon；H:263–266将其留作机制参考，未计为可集成完整底座。[HALTER][S9]、[Guava][S10]

必须修订项：无。GPT 准确率、停止延迟、纠正可学性、TD 密度、迁移及成本均已列为实测门槛，没有“已完成”误述，不据尚无实验判文档失败。

可选实施项：①T38用同一表记录入口配置、改造清单与工时；②按方向、接管原因报告 TD 隔离率和 BC 准入率。均为已有验收的展示建议，不新增通过条件。

以下原始论文和固定源码均已打开；未运行或操控机器人。

[S1]: https://arxiv.org/html/2608.03924v1#S6
[S2]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/planner.py#L373
[S3]: https://github.com/RLinf/RPent/blob/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/planner/api_loop.py#L670
[S4]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py#L1116
[S5]: https://github.com/strands-labs/robots/blob/4d0203161a587e29d7912c99da74878e8f989544/strands_robots/tools/run_policy.py#L643
[S6]: https://github.com/showlab/Show-Harness/blob/137d5718c3b7af0150764d8f9beeb252c9f2794a/plugins/dagger/plugin.py#L1
[S7]: https://github.com/showlab/Show-Harness/blob/137d5718c3b7af0150764d8f9beeb252c9f2794a/core/runners/real.py#L8
[S8]: https://github.com/open-gigaai/Zero2Skill/blob/6ea772566939d9c235dda771fe14f5fafa2bc6ad/grasp-tools/collect/prepare_training_set.py#L77
[S9]: https://github.com/YY-GX/HALTER
[S10]: https://guava-harness.github.io/
