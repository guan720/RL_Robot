# R11 独立审查：RL、异步执行与纠正学习

结论：**PASS；必要修改数 0。** 十二问未发现必须修正的事实、逻辑或缺失契约；不代表实现、复现或真机验证。

范围：先读指定科学家入口五文件，科学输入仅为 `R11/input` 九份md；未读旧轮或他人报告，未执行UPDATE、创建goal或修改科学输入，未安装、训练或操作真机。

先枚举关键点：弱起点/少示范；共享goal；RAPolicy Q/V、latent、hold；RT-EXPO BC/edit-Q/延迟；C/E/D；队列Bellman；终局/删失；BC/TD/执行/梯度资格；反馈信息差；平台loss和版本。区分必须修正、已明示待测与可选研究。

冻结定位简称：D=`input/03_RL_Harness自主学习系统_20260922/01_RL_Harness真机自主学习技术方案.md`；I=同目录 `02_接口契约与开发验收.md`；A=同目录 `06_异步动作时间轴与学习目标.md`；V=`input/04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md`；P=同目录 `04_训练平台与开源生态核查.md`。行号均指冻结文件。

## Q1：零成功是否意味着无需启动信息、双向共享必然收益？

反例：全失败、全零奖励且纠正也错误，换向不会凭空产生抓取行为。定位 D:35–41、90–109、266–279；V:338–340。原证 S1 §IV-A：十示范单任务含0/20，共享五任务使用150示范，不能互换证据。结论：通过。稿件保留有限评测与人工接管条件，要求双向同checkpoint评估；冷启动、共享迁移属待测。

## Q2：RAPolicy 是否被误写成对整个 flow 输出做 Q 动作梯度或普通 SAC？

反例：优势回归器改接 `−Q(X,π(X))`，类名仍含SAC但算法已更换。定位 V:340、350–370；D:291–297；A:339。原证 S1 §III-C/D、S2 `forward_awac_critic`、`_score_awac_actor`：replay Q、expectile V和行为优势；默认状态价值备份另有可选分支。结论：通过。原方法与队列改造分开，未借上游分数证明改造。

## Q3：没有 rollout latent 的示范，是否因此不能监督或被伪配在线噪声？

反例：给专家动作随便填z冒充原噪声；或因无z删除真实转移Q/V资格。定位 V:354–357；D:295；I:T39。原证 S3 `resample_offline_latent` 仅重采offline行，在线latent保留，估计条件密度期望而非反演或边缘密度。结论：通过。监督模式与真实后果资格分开，纯建议不能进TD；Harness原生头监督属于适配门槛。

## Q4：RAPolicy 的 async 与 fixed chunk 能否直接证明连续 C/E/D 已实现？

反例：推理hold也可与learner并发；补齐张量不代表实际执行尾段。定位 V:352–355、364；A:339。原证 S4 train/eval均有 `fixed_action_chunk`、`hold_during_inference`；S5 `prepare_chunk_transition` 要求fixed位置完整，区分逐步折扣与整块聚合。结论：通过。稿件分开hold、吸收填充、真实有效区间和连续队列，没有以补mask代替推导。

## Q5：RT-EXPO 的 base 与 edit 学习是否被混为同一条 RL 梯度？

反例：base 从不闭爪且编辑范围无法覆盖所需命令，单纯增加失败 TD 不保证原生头立刻学会新抓取。定位 V:124–133、163–173；D:268–270。原证 S6 `update_actor` 调 prefix 训练，`update_edit_actor` 计算带 Q/熵的编辑损失；`_update_jit` 有成功 actor batch 分支。S7 §IV-C 另有约30%基础成功的实验启动条件。结论：通过。文稿区分更新路径，允许 Harness BC 扩大支持范围，也未把作者启动条件强加给本项目；覆盖诊断属于待测。

## Q6：RT-EXPO 的延迟证据能否直接替代队列协议？

反例：用旧观测生成的候选和新观测编辑器，却把整次决策标在旧观测时刻；再把100 ms sleep与d步旧帧累计成一种天然时延。定位 V:135–159；A:331–337；I:T34。原证 S6 `sample_actions`、`sample_batch_actions` 核到 `[delay:delay+r]`、当前编辑观测、delayed next输入和prefix；S7 VII-E.3分列两种延迟。结论：通过。稿件要求独立数据视图与信息消融，未把最新图像无条件称为充分 Markov 状态。

## Q7：当前回报主要由旧 C 产生，配新 U 的一槽 TD 是否错位？

反例：因 U 在下一槽才物理生效，就搬入下一槽奖励，同时仍使用当前槽尾 next state，会重复或错配回报。定位 A:42–85、107–148；D:199–209。原证 S8 §3.4–3.6说明并发动作和延迟必须进入价值条件；具体一槽式仍是本项目推导。手推：环境执行 C 得 R，队列变化为 `C'=U`，故 `R+γ^n Q(X',π(X'))`闭合，U的物理价值经 X' 传播。结论：通过；状态充分性与固定预算可行性仍待测，不借S8宣称本项目已验证。

## Q8：C/E/D 的梯度限制是否混同执行 mask 或照抄 SmoothRL？

反例：优化当前预测的前n项代替真实 C，或给 D 的虚构高Q反传；另一极端是禁止未执行但可信标签参与BC。定位 A:154–190、322；I:243–257。原证 S9 §3.3、式5和算法1限定E价值梯度，同时其备份跨2n。冻结定义改为一决策队列，而非只改γ。结论：通过。固定C、扰动C预测/D不改变Q动作路径是有效反例检查；共享参数可能联动其他输出这一限制也已说明。

## Q9：C 提前终局而 U 未激活，会不会丢正奖或伪造行为？

反例：终局后重新观察并随便查询一个动作配成功；或只在未来成功时给前驱回填较长回报，失败时保留无条件bootstrap。定位 A:194–231、294–298；I:T11。原始依据为冻结的事前admission及其确定输入，独立手推：原请求结果可构成延迟决策终局，`y=Σγ^j r_j`且无后继；n=6、下一槽第3步成功时前驱传播为γ^8。结论：通过。终局时间按证据成立时刻，先抢占后成功不得追认；取消计算导致U未知也不伪填。这里是协议推导，不是实测。

## Q10：终局筛选与抢占隔离能否消除偏差？

反例：同一X/C一半提前终止，删去该半的actor行会改变状态权重；每逢危险状态都抢占，则对应继续执行价值缺少支持。定位 A:211、245–255；D:217、247。原始依据为采样条件：筛选分布正比于原分布乘存活概率；后槽抢占不改变已观测的前槽转移，但可使其bootstrap估计缺乏训练支持。结论：通过。两种选择/覆盖问题均明示，边界快照不确定时连依赖前驱隔离。扩大安全独立尝试及消融属于待测，不要求现在虚构无偏校正。

## Q11：反馈纠正、纯建议及部分标签有没有合理的 BC/TD 分流？

反例：帧107看到滑落后重抓，倒填为帧100已选完整U；或将一帧标签重复n次；或建议B借已执行A的后继。定位 A:165–190；I:253–257；D:133–141。原证 S10 §5.3/算法1允许更丰富信息教师，但讨论同一延迟状态对应不同真实状态及模仿分布；这不保证错误率未知Harness可无损蒸馏。结论：通过。稿件允许特权监督研究而首版分流，保留反馈事实和纯BC池；flow未知位置需同时核加噪/交互，不能只乘末端loss mask。

## Q12：平台复用会否悄悄改变学习目标？

反例：确定性完整头向默认SAC接口填假logπ；IK后的测得位移倒写为actor命令；换normalizer但复用同shape replay。定位 D:227–247、291–297；I:64–93、273–277、398；P:94–100。原证 S6的edit熵路径与S2默认V-backup已经展示同名actor/critic接口不代表同目标；项目契约进一步明确动作边界、goal/queue和版本隔离。结论：通过。显式loss适配、同一θ双向发布及原始观测/特征视图要求齐全；框架是否省工程、AgileX部署成本和新头可学性必须由预检决定。

必要修改为零。纠正内化、deadline、TD密度、双向覆盖与无辅助增益仍待测；动态延迟、微步RL、特权BC、自适应BC为可选扩展。

原始访问记录（2026-09-23）：

- S1：[RAPolicy v1](https://arxiv.org/html/2609.22888v1)，§III-B–D、§IV-A–C、表I/II。
- S2：[固定worker](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py)，`forward_awac_critic`、`_score_awac_actor`、`_v2_replay_likelihood_forward`，核termination/truncation合并、V备份及离线重采调用。
- S3：[固定离线latent](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py)，`resample_offline_latent`、`materialize_awac_offline_buffer`。
- S4：[固定Stack配置](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_stack_blocks_sac_pi05_franka2.yaml)，train/eval override；实际沿 `run_rapolicy.sh → run_realworld_ablation.sh → server_a配置 → 本配置` 读取。
- S5：[固定chunk处理](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py)，`prepare_chunk_transition`及接管尾部说明。
- S6：[固定RT-EXPO learner](https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)，Q5/Q6所列函数及 `update_critic`（`discount**replan_steps`）、`_update_jit`。
- S7：[RT-EXPO v1](https://arxiv.org/html/2609.18207v1)，§III、IV-B/C、V-C、VII-E.2/3，核BC、编辑与延迟条件。
- S8：[Thinking While Moving v3](https://arxiv.org/html/2004.06089v3)，§3.4–3.6、A.3，仅作并发状态依据。
- S9：[SmoothRL v1](https://arxiv.org/html/2608.29768v1)，§3.1–3.4、式4/5、算法1，核E梯度及2n target。
- S10：[DIDA原论文](https://proceedings.mlr.press/v162/liotet22a/liotet22a.pdf)，PDF第4–5页§5.2/5.3、算法1与式3；也读PMLR摘要入口。

访问限制：指定HTML、固定raw和DIDA正文可读；长输出截断已按函数/章节补读。未clone、安装或运行，不覆盖全仓；S4仅核配置与入口，不代表hold时延实测。未访问资产不推断为不存在。
