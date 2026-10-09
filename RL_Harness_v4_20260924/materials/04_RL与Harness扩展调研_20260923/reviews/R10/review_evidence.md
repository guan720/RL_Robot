# R10 独立证据与联合选型审查

结论：**PASS**。恰 12 项关键问题全部通过；必须修正 0 项，可选编辑 1 项。结论只覆盖本次冻结输入、下列问题与实际访问证据，不代表实现通过或真机复现。

2026-09-23。只读加载科学家入口、ROLE、status、INDEX和科研SKILL。未启动UPDATE/goal、写库或读历史/他人报告，未承接旧PASS。

审查前枚举：官方资产身份；弱起点与共享任务；Q/V 语义；hold 与吸收尾部；latent/示范资格；原生 BC 与 edit-Q；模块输入公平性；两类延迟；复位及预算；TD3＋BC/RECAP 仿真边界；Harness 公平竞争与通用接口；摘要、地图和技术优先级及复现分级。

输入定位约定：S 为 `input/03_RL_Harness自主学习系统_20260922/`，E 为 `input/04_RL与Harness扩展调研_20260923/`。本文引用行号均针对冻结输入。

| 简称 | 文件与实际阅读范围 |
|---|---|
| 入口 | S/README.md，全文 |
| 方案 | S/01_RL_Harness真机自主学习技术方案.md，§1、§9–14及选型段 |
| 接口 | S/02_接口契约与开发验收.md，§1、§7–9及T31–T39 |
| 时间轴 | S/06_异步动作时间轴与学习目标.md，开篇、§10–11及目录 |
| 总报告 | E/01_RL与Harness开源基线深度调研报告.md，全文 |
| VLA | E/research/01_VLA_RL扩展调研.md，§1–4、§11及目录 |
| 自主 | E/research/02_自主学习与复位扩展调研.md，全文 |
| Harness | E/research/03_Harness扩展调研.md，候选、兼容性、资产、§13等段；输出中个别中段被截断 |
| 平台 | E/research/04_训练平台与开源生态核查.md，全文 |

实际学习：RAPolicy与RT-EXPO原文方法/实验/附录及下引固定源码；两份verl-vla官方配方和模型卡；RPent提交差异；OpenETA的README/Planner观测义务；Strands的README/架构/训练文档。RT文件页截断、Strands网站/树页报Internal Error后，改读固定raw成功。未安装、运行测试/训练、下载全仓或逐一重审其余候选。

## 12 项关键问题

### Q01：RAPolicy 是否真为官方开放实现，资产是否足够支持当前措辞？

**PASS。** VLA344–346行、平台118行区分作者fork、上游平台及缺失权重/示范。作者Code链接指向flyfaerss/RAPolicy，固定README确有训练/SFT/评测入口并声明资产缺口；未称完整实验包或已跑通。[作者入口][RA-site]、[固定README][RA-readme]。

### Q02：弱起点和共享多任务证据是否被放大为本项目零示范自主循环？

**PASS。** VLA 338–340行给出单任务十示范、有限评测试次、联合150示范及人工接管/算力条件；总报告102–104行保持同样边界。原文 Table I、§IV-A/C 确有弱起点与共享五任务证据，但未证明共享正反自主复位。升为原生头预检候选有依据。[原论文][RA-paper]。

### Q03：Q/V 和 actor 的含义是否与完整头目标混用？

**PASS。** 固定 worker 的 `forward_awac_critic` 使用行为动作、expectile V 与 V-backup；`forward_v2_awac_actor` 使用停止梯度的优势权重。方案291–297行、接口384行及VLA370行另立融合验收，并指出混合行为高价值不等于当前 policy 独立能力；没有把它写成对新动作直接求 Q 梯度。[固定 worker][RA-worker]。

### Q04：异步、hold、终局吸收尾部与真实执行是否分清？

**PASS。** Pick Banana 固定配置确有 `fixed_action_chunk`、`hold_during_inference`；环境终局后追加 hold 张量，未继续执行旧动作。VLA352–355、364行与时间轴339行明确这些是上游协议，队列版另推导；没有把填充记成物理动作，也未称采集/学习并发已经解决连续 C/E/D。[配置][RA-config]、[环境实现][RA-env]。

### Q05：无原始 latent 的示范、接管与纯建议能否合法进入学习？

**PASS。** `resample_offline_latent` 明确只刷新离线行，估计条件密度期望，不反演专家噪声。VLA354、357行及方案295行保留在线噪声、离线监督和真实 TD 的不同资格；新反馈不倒填旧起点。接口T39还要求永久示范、双向采样和版本，属于已明确的实施门槛。[离线处理][RA-offline]。

### Q06：RT-EXPO 是否误称原生 VLA 直接通过 Q 更新？

**PASS。** VLA124–131行和总报告83行区分原生 RTC-BC、edit-Q/熵与候选选择。固定 learner 的两个 update 分支支持这一拆分；原生头可随新监督改变，但有界编辑仍受行为覆盖制约。方案268–270行要求实测 BC 与编辑可达性，没有仅凭零成功起点淘汰它。[固定 learner][RT-code]。

### Q07：额外输入是否会污染算法公平比较？

**PASS。** 原文附录 VII-D.3–4 确有检测器派生状态与任务特定图像历史。VLA137–139行准确限定模块可见性，方案275行和接口T34要求按模块登记来源、时刻及成本，并统一信息或消融。这里已有实质门槛，不能再以“未统一相机”判作文稿缺陷。[原文附录][RT-paper]。

### Q08：两类延迟是否合并为一种自然硬件时延？

**PASS。** VLA155–159行、总报告81行区分 wall-clock 注入与旧观测/chunk-delay，也保留 Dynamic Picking 的不同条件。方案277行要求实测自然时延和分开记录注入，未将不同条件相加或把上游成绩当本机 deadline 保证；与附录 VII-E.3 一致。[原文][RT-paper]。

### Q09：RT 成功率、冷启动、复位和十分钟预算是否被偷换？

**PASS。** VLA112–116行分别限定普通SFT/RTC-SFT参照、作者启动条件、人工复位/验成功、机器人数据预算及episode边界更新。总报告77行没有宣称十分钟完成全闭环。作者条件也未变成本项目准入门槛；自主34、169–175行继续区分共享反向学习与救援代做。[原文§IV-C、V-C、VI及附录][RT-paper]。

### Q10：TD3＋BC 和十示范 RECAP 是否被写成真机少数据证明？

**PASS。** 平台43–47、105–109行及总报告94–106行保留仿真、数据与资源条件。官方TD3配方直接更新π₀.₅，模型卡确为432 episodes池；RECAP则另有十示范配方，披露续跑选点、明显回退和最终value重标数据。两者未被混成一种数据门槛或PI官方完整训练栈。[TD3配方][TD3]、[模型卡][TD3-model]、[RECAP配方][RECAP]。

### Q11：RPent 是否因既有投入或机器人品牌而免除公平门槛？

**PASS。** 方案273行、接口390–396行要求同GPT/工具、两种模拟本体与故障回放，RPent可被替换。新提交仅补仿真探索等内容；OpenETA尚缺policy适配，Strands通用接口也不证明在线RL闭环。总报告149–153行对各方保留学习桥要求。[RPent差异][RP]、[OpenETA][OE]、[Strands架构][ST]。

### Q12：摘要、候选地图、技术实施优先级与证据等级是否一致？

**PASS。** 入口第9行、总报告15–20/207–221行、VLA54/368行与方案270/291行一致：RAPolicy优先原生预检，RT作实时对照，完整头作参考，TD3补充。总报告58–63/179–185行区分源码、发布和实测，关注度不算复现。模型卡下载35与快照36符合已声明时点边界。[模型卡][TD3-model]。

## 必要修改与可选项

无必须修改项。上述PASS针对证据与选型论证，不取消P0/P1、T34/T38/T39和真机验证。未实施这些明确门槛不构成本轮文稿错误。

可选编辑：总报告§10学习导航可加入RAPolicy的Q/V与latent路径；正文优先级已清楚，不据此判NEEDS_REVISION。

[RA-site]: https://flyfaerss.github.io/RAPolicy/
[RA-readme]: https://github.com/flyfaerss/RAPolicy/blob/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/README.md
[RA-paper]: https://arxiv.org/html/2609.22888v1
[RA-worker]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py
[RA-config]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml
[RA-env]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/envs/realworld/realworld_env.py
[RA-offline]: https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py
[RT-code]: https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py
[RT-paper]: https://arxiv.org/html/2609.18207v1
[TD3]: https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html
[TD3-model]: https://huggingface.co/Miical/pi05-libero-spatial-sft-step-100
[RECAP]: https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html
[RP]: https://github.com/RLinf/RPent/commit/6ee706935d28646828f70372ef0099c769cfe0c2
[OE]: https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/README.md
[ST]: https://raw.githubusercontent.com/strands-labs/robots/4d0203161a587e29d7912c99da74878e8f989544/docs/architecture.md
