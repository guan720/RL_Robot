# R09 独立证据与联合选型审查

结论：**PASS，12/12；无必须修改项。** 这是冻结输入的文献、静态代码与选型逻辑审查，不是安装、训练或真机复现通过。

范围：只读科学家 START_HERE、ROLE、state/status、knowledge/INDEX、科研 SKILL 及其 RESEARCH/PAPER_REVIEW；状态仍为暂停中的 review_in_progress，不承接任何旧成绩。仅检查 R09/input 九份文件的相关章节，未打开旧轮或同轮其他报告、未写知识库或启动更新。

先枚举的关键点为：开放资产与实验条件；原生更新对象；信息与时序；数据资格及价值含义；学习器和 Harness 的公平竞争；传播指标与结论一致性。随后独立打开 RAPolicy、RT-EXPO 正文，再沿固定代码和官方配方学习，选定以下 12 问，不扩候选凑数。

定位缩写：技＝03/01 技术方案，接＝03/02 接口，时＝03/06 时间轴，入＝03/README；总＝04/01 总报告，V＝04/research/01，循＝02，H＝03，台＝04。均指本轮 input 内文件；数字为行号。

1. **RAPolicy 是否真有官方代码，资产缺口是否如实？PASS。** V:342–346、总:93、台:118区分 RLinf fork 与上游、训练入口与缺失的 SFT 权重/示范。固定 [README](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/README.md) 的 Installation、Release validation 支持这些边界；Apache 不覆盖依赖许可。不能再写成“仅项目页”或“已复现”。

2. **弱起点与共享证据是否足以改变顺序？PASS。** V:338–340、总:102–104保留十示范、人工接管和共享多任务条件。[原文 IV-A/B/C](https://arxiv.org/html/2609.22888v1)确有初始零成功试次及一个共享五任务策略；共享实验用150示范，不能移植成十示范共享正反循环。将其提升为原生头预检者合理，未承诺全零奖励也能启动。

3. **hold 与终局 tail 是否被当作连续队列/实际执行？PASS。** V:352–355、时:339明确两者不同。[配置](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml)启用 fixed_action_chunk、hold_during_inference；[RealWorldEnv](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/envs/realworld/realworld_env.py)在终局后只补张量，不再 step。吸收填充有效位不等于物理执行证据；现文保留真实区间并要求独立队列推导，足够。

4. **latent、V 与 actor 目标是否准确？PASS。** V:340、353、357、370，技:293–297，接:T39互相一致。[resample_offline_latent](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py)只刷新离线行，不反演专家噪声；[worker](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py)的 forward_awac_critic/_score_awac_actor 使用 replay Q、expectile V 和 detached 权重。V 不等于当前独立策略回报；缺 latent 不剥夺真实示范 TD 资格，纯建议仍无真实后继。

5. **RT-EXPO 原生 BC 与编辑 RL 是否混淆？PASS。** V:124–133、总:83–87清楚分开。[固定学习器](https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)中 update_actor 走 prefix train step，update_edit_actor 对缩放编辑作 Q/熵优化；_jitted_fast_select 取延迟后窗口。新增 BC 能改变 base，故不能称永久冻结残差，也不能称 Q 直接更新原生 flow；现有覆盖预检恰当。

6. **额外信息是否被误算为纯算法收益？PASS。** V:137–139、总:79、技:275、接:T34已按模块分视图、历史、派生状态与可用时间。[原文 VII-D.3–4](https://arxiv.org/html/2609.18207v1)确认检测器位置/速度给 critic/filter/edit，基础 VLA state 不同；Balance 更改图像历史。文中要求统一可获得信息或输入消融，并计提取延迟，已形成必要门槛。

7. **两种延迟条件与自然时延是否分开？PASS。** V:155–159、总:81、技:277与[原文 VII-E.3](https://arxiv.org/html/2609.18207v1)一致：wall-clock 的三个任务额外 sleep 100ms、Dynamic Picking 不加；chunk-delay 用旧帧/前缀，d 分别3和5。不能相加成一个自然端到端延迟。现文同时区分67ms自然耗时与离散步预算，未用论文分数证明本地 deadline。

8. **RT-EXPO 复位与预算是否夸大自主性？PASS。** V:112–116、175–179，总:77已披露人工复位/验成功及约30%以上的实验启动条件。[原文 V-C、VI、VII-E.4](https://arxiv.org/html/2609.18207v1)支持交互预算上限和 episode 边界更新。十分钟不包含全部示范、复位、训练、评测工时；循:169–175和技:31、321–338另核自主窗口及人工成本，不将 rollout 无接管等同无人闭环。

9. **原生 TD3＋BC 是否越过仿真边界？PASS。** 台:39–47、总:94正确定位补充对照。[官方 recipe](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html)确实更新 PI0.5，关闭 DSRL noise actor；参考为8 GPU/32 LIBERO环境、32/50到40/50，过程有回退。短 SFT 不是少量示范证明；实体采集入口亦不等于同配置真机 RL。输入没有将资源数硬套给用户。

10. **OpenETA 是否获得与 RPent 同等骨架资格？PASS。** H:250–256、总:149/218、技:273、接:392–396已同 GPT/工具/adapter/故障回放比较。[OpenETA planner](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/runtime/planner.py)有 _invariant_obligation_decision；[registry](https://raw.githubusercontent.com/OpenMOSS/OpenETA/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/agent/tools/registry.py)的 _invoke_tool_handler 取消等待不终止 daemon 线程。[RPent _build_tools](https://raw.githubusercontent.com/RLinf/RPent/6ee706935d28646828f70372ef0099c769cfe0c2/rpent/planner/api_loop.py)仍设 sequential=True。两者都需独立观察、实体停止和学习数据桥；无原生在线 RL 未被单独用于淘汰 OpenETA。

11. **机构影响力是否替代复现与兼容性？PASS。** 总:179–185、H:219–234、台:68–76明确 stars/forks、HF下载、引用未知与第三方复现不同。RAPolicy README 也将发布检查与实验重跑分开。此处审查统计口径，未重新认证全部动态数量；不把未知填0、不把母项目热度给子项目，且通用接口优先于 AgileX 适配，排序依据成立。

12. **摘要、地图、专项和技术优先级是否一致？PASS。** 入:9；总:15–23、93–104、207–221；V:54–55、270–272、368；技:270–279、291；接:T34/T38/T39与时:339均指向：完整头保留队列参考，RAPolicy优先原生预检，RT-EXPO保留实时竞争价值，TD3＋BC补充，RPent可被同门槛骨架替换。总/技要求先预检、无需同时完整移植；没有把“首先验证”写成性能胜出，也没有仅因已有实现便锁死结论。

实际阅读与限制：上述链接均本次独立打开；另读同 RAPolicy 提交的 run_rapolicy.sh、run_realworld_ablation.sh、sac.py（merge_hil_actions_in_model_space、prepare_chunk_transition）、awac_actor_loss.py（默认 likelihood 与 flow 消融）、server_a 配置继承。论文读取方法、实验及相关附录；代码只读所列路径/函数，不作全仓结论。Python直连部分 raw 出现 TLS/读取超时，改由网页工具读到固定 worker、launcher、OpenETA registry；awac_offline 直连读取成功。未 clone、安装、执行算法、调用机器人或验证第三方复现。未把网页 find 的未命中当作能力不存在。

已有必要实测门槛仍是：同信息/同数据/同纠正与交互预算，独立时间协议，双向 BC/覆盖，合法 TD，关闭辅助后的双向能力，以及停止/观察/数据/替换成本。它们已进入 P0/P1、T34/T38/T39，应实施后判断；“尚未实施”不是本次文档新增缺陷。

可选细化：将候选预算、弃选规则与协议配置整理为一张实验登记表；将摘要的“主线”统一称“队列参考设计”。这能降低交接阅读成本，不改变现有明确门槛，不作为阻断项。
