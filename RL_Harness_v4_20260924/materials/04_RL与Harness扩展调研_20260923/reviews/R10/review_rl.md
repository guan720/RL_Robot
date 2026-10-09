# R10 独立 RL／异步审查

**结论：PASS。恰好 12 项反例质询，必要修改 0 项。** 通过仅指本次冻结文稿在下列问题上未发现必须修订的逻辑／事实错误，不表示算法、代码或真机已验收。

边界：2026-09-23 已读科学家指定入口与科研 SKILL；科学输入仅 R10/input 九份 Markdown。未读其他审查报告、继承旧 PASS、启动 UPDATE／goal、写知识库、安装框架或运行训练。

定位简称：S=03目录《01_RL_Harness真机自主学习技术方案》；I=《02_接口契约与开发验收》；A=《06_异步动作时间轴与学习目标》；R=README。D=04目录《01_RL与Harness开源基线深度调研报告》；V、U、H、P 分别为 research 下 01_VLA、02_自主学习与复位、03_Harness、04_训练平台专项。下列行号均属冻结输入，历史报告链接未打开。

技术点先枚举：弱起点、共享θ／goal、标签与真实TD、C/E/D、队列折扣、终局、抢占删失、BC/Q信息集、native hold／V／latent、RT-EXPO窗口／新观察／更新、平台fork、本体边界。随后独立读原始材料并选12问，未扩新候选。

原始来源与实际读到的位置：

| 代号 | 实际打开及阅读位置 |
|---|---|
| E1 | [Thinking While Moving 原文](https://arxiv.org/html/2004.06089)：§3.4–3.6，式8–9、previous action／延迟条件；支持并发状态需显式建模，不替本项目证明视觉 Markov 性。 |
| E2 | [RAPolicy v1](https://arxiv.org/html/2609.22888v1)：§III-B–D 式1–7，§IV-A、Table I；区分行为 Q、expectile V、条件似然与有人工接管的弱起点实验。 |
| E3 | [RAPolicy 固定 worker](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py)：forward_awac_critic（1611附近）、_v2_replay_likelihood_forward／forward_v2_awac_actor（2595–2673附近）；另读同提交 awac_actor_loss.py 的默认 likelihood／flow 消融。 |
| E4 | [同提交 offline 数据代码](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py)：resample_offline_latent、materialize_awac_offline_buffer；[真机配置](https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml)：fixed_chunk、hold_during_inference。经 launcher 追到此配置，并读 README 的资产及 namespace 边界。 |
| E5 | [RT-EXPO v1](https://arxiv.org/html/2609.18207v1)：§IV-A–C、§V-C、§VII-E.3–4；确认新观察编辑、SFT 起点、延迟两种条件与更新节奏。 |
| E6 | [RT-EXPO 固定 learner](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)：sample_batch_actions（722附近）、update_edit_actor（875）、update_actor（910）、update_critic（954），含窗口、两类梯度与 discount**replan_steps。 |
| E7 | [RLinf 主线固定 worker](https://github.com/RLinf/RLinf/blob/7b3d874945454acfd0785c7c4837a0ad795c391d/rlinf/workers/actor/fsdp_sac_policy_worker.py)：forward_critic（329–405）、forward_actor（448–498），核默认 reward 聚合、熵备份及 actor loss。 |

仅正文及选定源码静态阅读，非全仓审计；作者实验与本报告推导分开。

## 12 项反例质询

**Q01 弱起点若只有失败，完整头是否保证启动？**  
定位 S29、39、223–225、266–279；V338–340。反例是全零奖励、纠正也无效，动作维度再大仍无改进方向。文稿已要求有效示范／纠正或探索，并先比较可学性和编辑覆盖。E2 的零成功起点仍有十示范及人工接管，文稿未借此保证无人冷启动。**通过；学习可达性待测。**

**Q02 同一画面正反目标冲突，会否只让 actor 看语言？**  
定位 S88–109；I219–225、333–340。反例是物体在 B：对 g=B 终局，对 g=A 是起态。输入要求 actor/Q/target、奖励及 replay 同目标版本，同 θ 双向更新和整体发布；不跨目标 bootstrap，也不把两个边际成功率相乘。E2 的共享任务只支持可行方向。**通过；双向退化需实测。**

**Q03 未执行好建议能否套用原 policy 的后继？**  
定位 A63–95、165–180；I207–217、255。反例是候选 A 入队、候选 B 更好，却让二者共用真实后继。文稿拒绝 B 的 TD，保留其可信 BC；A 入队形成真实队列变化，不因尚未物理激活误删。request 必须事前存在，不能事后补造。此处按定义核对。**通过。**

**Q04 当前奖励由旧 C 产生，是否错误归给新 U？**  
定位 A38–61、77–85、105–148。以 n=6：R 覆盖100–105，X'在106且 C'=U，U 的物理回报在下一转移。于是 y=R+γ⁶Q(X',π(X'))具有相邻决策语义；挪入106–111回报却保留同 X'才会错位。E1支持增广原理；输入明确区别 SmoothRL 2n 目标，未称直接复现。**通过。**

**Q05 C 在槽中成功而 U 没激活，是否丢失正奖或制造虚构动作？**  
定位 A192–231、294–298。仅原冻结请求实际结果可配 R_L／吸收终局；取消后拿不到 U 就不伪造。终局行更新 critic，前驱仍用统一一步链，不按未来成功额外回填。γ=.9、n=6、下一槽第三步奖1时，前驱传播为 .9⁸。actor 筛除该行的存活加权影响也已承认。**通过；此为手算，未运行。**

**Q06 先抢占后成功，会否追认旧槽为成功 TD？**  
定位 A245–257、261–270及231；S217、247。反例是108帧改写106起的 C，随后 Harness 成功。输入隔离受破坏槽；100–105前驱仅在106快照可靠时保留；不把抢占、超时变 done=1。记录删失比例且承认选择偏差，没有保证得到无偏纯 policy 价值。**通过；覆盖与偏差影响待测。**

**Q07 一套 executed mask 能否兼管 BC、Q 和未来纠正？**  
定位 A150–190；I243–257、329–332。反例是107才见滑落的纠正倒填100，或 flow 未知 token 先污染已知位置再在 loss 末端屏蔽。输入分开物理 mask、TD资格、监督权重、Q路径；C 是固定状态，Q动作梯度只经 E，D 不进入动作；部分 flow 标签须验证输入／交互。**通过，相关计算图检查仍待执行。**

**Q08 RAPolicy 的 async 是否已经满足连续动作队列？**  
定位 A339；V352–355、368–370；S270、291–293。E4 的选定真机配置明确 fixed_action_chunk 与 hold_during_inference；其 async 不能据此换成 C/E/D。输入把原生 hold 当学习预检，队列版须另推目标和数据资格，也禁止把吸收态填充当真实执行。**通过；尚未实施的改造不是新缺陷。**

**Q09 expectile V 能否当作当前 policy 无辅助价值，或用动作 Q 梯度训练原生头？**  
定位 S293、297；V340、353、356、370。E2/E3实际为 replay动作 Q、V备份和停止梯度的优势权重回归；V偏向行为分布较优部分。输入正确区分这些目标与完整头的−Q梯度，且要求关闭辅助的双向评估。高 V 与低独立成功的反例已被约束。**通过。**

**Q10 无 rollout latent 的真实 demo 是否必须丢掉 Q/V？**  
定位 S295；V357、364；I384。E4只为离线行重采噪声，目标是条件 log-density 的期望，非恢复专家噪声／边缘 flow 密度；E3 的价值路径读取真实行为与后继，不依赖该噪声。文稿已将 actor监督模式与真实 demo 的TD资格分开；纯建议仍无后果。**通过。**

**Q11 RT-EXPO 的新观察和执行窗，能否直接塞进冻结 X 的 learner？**  
定位 V135–167；A329–337；S275–277。E6按延迟输入生成候选并取对应窗口，编辑／Q可读较新观察，backup用 γ^replan_steps；base update与编辑器 Q／熵路径不同。E5还区分wall-clock与chunk-delay。输入要求独立协议、信息时间和视图，未把新观察隐藏于旧 X，也未宣称base被直接Q反传。**通过；覆盖及自然时延待测。**

**Q12 同名 RLinf、SAC、RTC 或已有 AgileX adapter 是否足以宣布融合？**  
定位 P35、94–100、118；I398、390；D23、171–175。E7 默认 reward求和／一次discount及含log_pi目标均非本项目公式；E3又是独立fork。输入要求分别锁定、替换loss／schema，禁止确定性actor填假概率。通用性先核可替换接口和学习协议，品牌只算部署成本。**通过；未核全依赖不被包装为可直接运行。**

## 必要、待测、可选的分界

必要修改：**0**。12问未发现必须改稿的逻辑或事实问题。

待测门槛：固定槽延迟与合法TD密度；有效纠正和冷启动；终局／抢占日志及mask计算图；原生协议适配；同预算、同信息条件下双向独立能力。输入已分别列入P0–P4与T10–T18、T34、T36、T39，不能因尚未实施重复计作文稿问题。

可选：动态延迟／中途观察、特权BC、actor终局筛除权重消融。当前不作为首版必要模块；本报告不证明部署成功或候选最优。

