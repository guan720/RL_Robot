# R09 独立审查：Harness 与融合

**结论：PASS（限定文稿契约审查）。必要修改 0 项；12 项反例质询均未发现尚未被当前输入处理的阻断矛盾。** 不代表候选代码集成、真机安全、纠正质量或学习收益已通过。本次没有安装框架、运行训练／验收或操作机器人。

范围：已读科学家指定入口及科研 SKILL、R09/input 九份 md；未读其他轮或同轮审查，未写知识库或创建 goal，不继承既有资格。行号均指本次 input 冻结文件。

定位缩写：input/03_RL_Harness自主学习系统_20260922 下，M＝01 技术方案，I＝02 接口契约，T＝06 时间轴，E＝README；input/04_RL与Harness扩展调研_20260923 下，R＝01 总报告，V／A／H／P＝research 下编号 01–04 的四个专项。

**覆盖要点。** 认知纠正、持续观察、控制权、反向／恢复、评分、代码发布、反馈与数据分流、原生／实时学习融合、多本体、独立学习分账。AgileX 只计首站成本。

**本次实际打开的第一方材料与学习结果（2026-09-23）**

- [S1 Show-Harness 原论文 v1](https://arxiv.org/html/2609.10522v1)，§3.1–3.4、§4：语义动作经本体解释器落地；反馈决策与语义监督不等于本项目队列 RL。
- [S2 Show 固定 DAgger 源码](https://raw.githubusercontent.com/showlab/Show-Harness/137d5718c3b7af0150764d8f9beeb252c9f2794a/plugins/dagger/plugin.py)，`DaggerPlugin.on_key/has_intent/drain`：generation 和每臂最新意图负责输入，runner 决定执行。
- [S3 OpenETA 固定 registry](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py)，`ToolRegistry.call/_invoke_tool_handler/_execution_cancelled`：取消等待不停止后台 handler。
- [S4 RPent 当前固定 API loop](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/planner/api_loop.py)，`_build_tools/_make_tool_function/read_image`：包括图像读取的工具仍串行注册。
- [S5 RT-EXPO 固定采样器](https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/utils/loop_utils.py)，`AsyncChunkSampler.launch/_sample_pre_cached/on_human_takeover/_cancel_pending`：有后台预计算；`replan_steps<delay` 走同步分支，取消无设备回执。
- [S6 RAPolicy 固定 SAC 工具](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py)，`compute_expectile_value_loss/merge_hil_actions_in_model_space`：拟合 replay Q 的 expectile；从首次干预起替换尾段。

以上为选定部分静态阅读，非全库审计。RAPolicy hold、Strands 路径未另做源码全链核验，仍依输入契约待验收。

**12 项具体反例质询与判定**

**1．GPT 主观察和 DAgger 是否暗含完美教师？** 反例：GPT 每次都建议同一个错误抓点，动作格式合法、分布低熵，仍持续被克隆。M:117–139、I:187–201、A:84–90 将评分校准、局部动作质量和信息可模仿性分开，也否认原始 DAgger 保证自动适用。S2 的人工键盘接口只提供意图入口，未被写成自动教师已实现。**PASS；待测**抓空／偏移状态的纠正净收益和错标率。

**2．长工具卡死后是否仍能观察？** 反例：运动占用工具锁 30 秒，observe 排队，模型异步开关却开启。S4 确认当前版本仍串行注册。I:58／394 要求订阅 Gateway 只读事件，独立于活动工具锁，以卡死时多批新时间戳和本地保持验证。**PASS；待测**观察传送不能与阻塞驱动共用不可抢占路径。

**3．取消旧 owner 是否真的交出机器人？** 反例：OpenETA handler 被取消后仍继续，RLinf reset 和 Show 解释器又分别直写设备。S3 证实取消等待不足；I:115–146、T31／T33 和 M:262 要求唯一驱动连接、代际、quiesce 凭证、拒绝未知重放，reset／初始化／TRIAL 同样仲裁。**PASS；待测**旧线程恢复后提交命令、ACK 丢失及 Gateway 重启的实际 fencing。

**4．正常反向是否被恢复脚本替代？** 反例：物体落在 B 边缘却无法再次抓取，Harness 搬回 A 后记为共享 policy 的 B→A 成功。M:90–109、I:261–265 规定共享 θ、目标 episode、反向 init_set 与恢复成本；异常恢复不是普通反向任务。**PASS；待测**不适合反抓起态必须留在记录中，不能以奇偶轮自动换向或删除困难样本。

**5．unknown 和迟到成功是否污染当前奖励？** 反例：A→B 的旧成功回复在 B→A 启动后到达；同一画面重复查询又发两次奖励。I:167–183、T18／T20／T21 绑定原区间、目标、版本和终局事件；M:175 明确 unknown 不是零或失败。T:229–231 还规定证据充分时刻和无法定位帧时保持 pending。**PASS；待测**乱序、缺图、重复回调和先接管后成功的联合事件。

**6．生成代码能否改标准让自己晋级？** 反例：恢复代码返回 DONE，同时改 rubric 或直接接 ROS；静态检查通过后立即成为正式技能。M:155–157、I:195–199、T23 将候选隔离于 TRIAL，限制 API／预算，真实试验、固定核验及回归后发布，禁改保护和评分。**PASS；待测**权限拒绝和物理失败处置；不增加逐次人工批准这一未要求的流程。

**7．反馈轨迹是否被倒填为早先 chunk？** 反例：帧 107 新图触发重抓，却把 107–112 的真实路径贴成帧 100 已选 U；末端未达目标又以实测位移替换命令。M:161–169、I:68–85、T:184–190／255 区分动作层、信息时刻和监督粒度，T32 明确反馈路径不能冒充槽起点完整 U。**PASS；待测**解释器记录原意图、转换版本和逐步反馈，孤立标签不重复补齐 n 步。

**8．纯建议与真实数据是否借后果混池？** 反例：policy 执行 a，GPT 仅建议 b，却给 b 配 a 的后继；或反过来把当前 C 终局前已有真实 request 的 U 全删成影子建议。I:209–217／255、T:65–95／198–211 分开事实、标签和 request/commit/activation；真实 terminal request 例外限原冻结计算。**PASS；待测**建议仅进合格监督，失败事实保留，永久示范不被环形池覆盖。

**9．RAPolicy 是否仅换名字就融合？** 反例：把干预尾部替换、吸收填充和原 rollout latent 一起塞进 06 的 actor-Q 梯度训练。S6 说明尾部确有替换机制；M:291–297、T:339、V:352–370、T39 已要求独立 Q/V/actor、goal/queue、噪声资格和终止定义，hold 对照不冒充连续执行。**PASS；待测**完整原生队列改造；真实示范缺 latent 不等于没有 TD，纯建议仍无真实后果。

**10．RT-EXPO 是否继承同一时钟和停止语义？** 反例：快编辑器读新观测，却用槽起点 X 训练；取名 async 后忽略同步回退，future cancel 后立即交接。S5 与 T:329–337、V:145–179 一致，要求独立决策时间、回报和训练视图；I:T34／T38 固定入口和实际消费索引。**PASS；待测**自然耗时与人为注入分别计账，较新信息／派生特征做对齐或消融，不跨协议混 replay。

**11．通用接口是否只是品牌替换？** 反例：换成 7 维另一夹爪，认知层仍发送 Piper 6 维零 hold，或启动默认 RELEASE 掉落持物。I:390–396、M:161–167 明确 capability/schema/normalizer、坐标及停止能力，两个不同 schema 的模拟 adapter 回放，旧 replay 默认隔离；H:204–206 只保留一个设备主循环。**PASS；待测**真实新本体标定；不以 AgileX 现成驱动淘汰 OpenETA／Strands 等通用骨架。

**12．系统代做是否被计成 policy 学会？** 反例：checkpoint 不变，仅升级 Harness 便提高成功率；自动恢复隐藏人工复位、审计和值守成本。I:279–291、T28／T29、M:323–336、R:213–225 分开独立 policy、辅助系统、自主学习成本，同 checkpoint 双向评估并保留拒绝起态。**PASS；待测**同预算动态 BC/DAgger 与 BC＋RL、关闭动作辅助的留出评估；Q/V 上升不能替代独立表现。

**必要／待测／可选的分界**

- **必要文稿修改：无。** 明示尚未实施的门槛不构成文稿阻断缺陷。
- **实施前必须完成：** T31–T39 联合回放、长工具独立观察、未知停止不交接、双 schema、终局／乱序评分与纠正分流；随后用少量真机验证动作质量、有效 TD 密度和双向独立增益。未通过时阻断相应部署／发布，不能引用本 PASS 放行。
- **可选改进：** 实现时维护上游初始化、reset、设备连接、recorder、发布入口的“保留／替换／禁用”清单，便于交接。
