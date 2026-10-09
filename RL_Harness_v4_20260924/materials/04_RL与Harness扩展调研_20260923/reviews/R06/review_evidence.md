# R06 独立证据、覆盖与联合选型审查

结论：**PASS**。审查问题12项；必要修订0项；可选补充1项。2026-09-23。

范围为R06/input冻结九文件，重点综合报告与四专题，联查技术文档。只读加载科学家入口、角色、状态、索引与科研skill；未读旧审查结论，未更新科学家。通过仅指文献和设计证据；未实验为已声明边界，不计缺陷。

检索前关键点：完整头选型；RT-EXPO起点／成功BC／时延／人工；verl数据条件；RLinf具体组合；OpenETA自演化；RPent归并；HALTER／Zero2Skill开放边界；实质遗漏；热度与代码完整度。

## 逐项问题与结论

**Q1：完整头是否因“零成功”被预设为胜者？通过。** 综合§2、§9与技术§10.2限定为优先验证设计，要求同数据BC、编辑可达性及独立双向能力比较。自主专题§7区分零自主成功与没有示范／纠正／有效奖励，符合用户条件。

**Q2：RT-EXPO 的成功率与启动条件是否支持所述定位？通过。** 独立核 Table I：普通SFT均值12.5/30、RTC-SFT为18/30、RT为29/30；§IV-C先示范SFT到约30%或以上。VLA专题§4.1保留了这些条件，支持“优先挑战者”，不证明零成功冷启动。[原文§IV-C、Table I](https://arxiv.org/html/2609.18207v1)

**Q3：异步成功和十分钟预算是否被写成无人自然时延实证？通过。** 原文§V-C、§VI及VII-E.2–4保留人工复位／验成功、三任务加100ms、Picking不加该sleep、chunk-delay、episode边界更新。综合§4.2和VLA§4.4.1已拆开；成功BC与编辑器Q更新也未混淆。[原文附录](https://arxiv.org/html/2609.18207v1)

**Q4：verl-vla 是否只是latent RL，或虚构少示范证据？通过。** 官方TD3+BC配方明确更新π₀.₅本身、禁用DSRL noise actor，使用8GPU／32仿真环境，32/50→40/50。HF起点卡明确432 episodes、100步SFT；综合§4.3和平台§4未将undertrained误读为几条示范。[配方 Reference configuration](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/td3-bc/pi05/libero-spatial.html)、[模型卡 Training configuration](https://huggingface.co/Miical/pi05-libero-spatial-sft-step-100)

**Q5：十示范RECAP是否真的构成弱起点开放对照？通过。** 实际打开官方配方：十条起始示范、初始8/50、最好23/50；停止续跑和checkpoint选择、累计106条、最终value重标数据均有明确说明。综合§4.3和平台§11已记录，既没有漏掉此反例，也未包装成稳定真机无人改进。[官方 Evaluation results／Published artifacts](https://verl-vla.readthedocs.io/en/latest/reinforcement-learning/recap/pi05/libero10-task8.html)

**Q6：RLinf 的VLA、SAC和RTC是否被功能表相乘？通过。** USER官方结果将π₀归于HG-DAgger；CNN／Flow RL另列。独立打开固定worker的 `forward_critic`：DSRL分支为 `gamma**num_action_chunks` 与首列reward，其余为reward求和加一次discount。平台§2、§10准确限定为需改target／goal／queue的运行时，不能仅换YAML。[USER Results](https://rlinf.readthedocs.io/en/latest/rst_source/resources/publications/rlinf_user.html)、[固定worker](https://github.com/RLinf/RLinf/blob/7b3d874945454acfd0785c7c4837a0ad795c391d/rlinf/workers/actor/fsdp_sac_policy_worker.py)

**Q7：OpenETA是否被漏排，或把门禁当成已证自演化？通过。** 原文§6.4明确没有候选通过全部晋级门禁；README可核模块化planner／tools／sim-real契约。综合§6.2及Harness§13.1将其列入与RPent同预算预检，并保留持续观察、实体停止、学习桥缺口。没有因缺现成RL或AgileX驱动而单独淘汰。[论文§6.4](https://arxiv.org/html/2608.03924v1)、[固定README](https://github.com/OpenMOSS/OpenETA/blob/7d4a0a1522ba8ebbd362bde880bad81d2a98f15e/README.md)

**Q8：Harness VLA与RPent是否被重复计数？通过。** 官方RPent仓库Citation直接指向Harness VLA论文2607.08448。综合§6.3、Harness§13.2已归并；冻结VLA的系统辅助提升未计作参数RL证据。[官方Citation](https://github.com/RLinf/RPent#citation-and-acknowledgement)

**Q9：HALTER是否被误当免费恢复、完整开放底座？通过。** 独立打开原文§IV-B及Table II：原子技能需要示范，100回合有25次人工介入；仓库仅README且状态为发布中。Harness§13.2准确限制为评测恢复参考。它还有任务相关参考案例，但现文已明确“无成功分类器不等于无准备成本”，无需因此重复判失败。[原文](https://arxiv.org/html/2609.19413v1)、[仓库Status](https://github.com/YY-GX/HALTER)

**Q10：Zero2Skill是否被公开GitHub掩盖动作／依赖缺口？通过。** 固定README明确不分发AnyGrasp专有运行库，recorder外置；整理脚本 `merge_episode` 将正action_shift的未来qpos写为action，`main`保留已冻结条目的旧资格规则。Harness§13.2逐项记录，限于纠正记忆／整理部件，不要求采用ACT或据此生成真实TD。[固定README](https://github.com/open-gigaai/Zero2Skill/blob/6ea772566939d9c235dda771fe14f5fafa2bc6ad/README.md)、[固定整理脚本](https://github.com/open-gigaai/Zero2Skill/blob/6ea772566939d9c235dda771fe14f5fafa2bc6ad/grasp-tools/collect/prepare_training_set.py)

**Q11：热度或通用性口号是否替代工程证据？通过。** 综合§7–9分列论文、代码、权重、依赖、许可，stars／下载仅作动态快照。技术接口区分Gateway、命令／反馈、goal及BC／TD；异步附录不宣称队列使图像充分Markov。通用性优先，AgileX只计部署成本。

**Q12：补漏是否发现必须替换主线的遗漏？未找到；可选1项。** 实际打开REMAC与PhyAgentOS官方仓库。REMAC为Kinetix异步执行／LoRA研究代码，未见共享双向真机RL＋Harness交付，不要求新增主线。[REMAC Overview／Usage](https://github.com/hatchetProject/REMAC)

PhyAgentOS可在工程邻近表补一行：Forge Tool API、异步观察与SQLite任务记录值得复用。但官方§2／§8／§12明确**没有跨Tool资源lease，Skills／节点／模型／仿真资产另供**，采集为best-effort。只建议同接口预检，不据README宣称已有单设备owner或RL数据桥。[官方实现范围](https://github.com/PhyAgentOS/PhyAgentOS-core/blob/main/docs/en/01-framework-introduction.md)

## 检索边界与必要性裁决

实际查询：`robot reinforcement learning real-time 2026 github asynchronous`、`robot harness 2026 OpenETA Zero2Skill`、`Harness VLA RPent`、`HALTER robot github reset`、`real world VLA online reinforcement learning 2026 open source`，再定向查PhyAgentOS／REMAC。索引仅用于发现。PhyAgentOS目录页一次内部错误，采用可打开的官方范围文档，标为浅筛。

没有发现改变正确性、可实现性或必要竞争路线的阻断问题。可选项为PhyAgentOS记录；不要求穷尽论文或重复证明“未运行”。实施仍按既定跨协议训练视图、独立双向评估与总成本门槛决定取舍。
