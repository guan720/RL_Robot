# VLA 自学习 RL 与自动奖励专项审查

核验日期：2026-09-22。范围：机械臂/双臂/移动操作，特别关注真机复位、接管与值守。背景库仅只读，未回写。没有在本地运行任何机器人训练或验证性能；下文数字均为作者报告或所打开仓库的发布状态。详细统一候选卡保存在 [vla_candidates.json](vla_candidates.json)。

## 结论与条件优先级

对本次选型，最有用的组合是“可执行真机 RL + 可恢复任务循环 + 可信自动奖励 + 运维/验证 harness”。更新 VLA 参数、能持续自主执行、能无需人工继续训练，是三个不同的结论。

|优先层|候选|适合解决什么|必须补齐什么|
|---|---|---|---|
|工程重点|PLD + ENPIRE 的相关 PLD runtime|残差策略自主发现失败恢复，再蒸馏回 VLA；ENPIRE 提供 actor/learner 入口|逐任务工装/复位/奖励验收；原 PLD 论文全任务复现仍有缺口|
|基础设施重点|RLinf-USER|多机器人异步训练、资源调度、断点恢复|实体复位、少接管策略、自动奖励；论文 VLA 实验不要误认成 RL|
|奖励重点|Robometer + policy-learning|自动奖励、成功检测、阶段切换，已有真实 DSRL 代码接口|物理场景复位仍需人；全数据和奖励主仓许可需明确，policy-learning 已核 MIT|
|真实 RL 基线|RL-100 / ConRFT|可靠动作技能、离线到在线改进；代码可读|RL-100 复位仍是未来工作；ConRFT 六任务人工复位、线上接管|
|自动奖励基线|RoboReward|避免每回合人工打成功标签|误奖励、复位、目标任务校准|
|方法参照|RECAP / GR-RL / GigaBrain-RAMP|大 VLA 价值条件更新、噪声空间 RL、世界模型条件策略|对应版本完整开源、现场干预记录与运行成本|
|仿真筛选|SimpleVLA-RL|GRPO VLA 仿真后训练和 sim2real|真实持续学习的复位/安全/系统接入|
|可选组件/观察|GRAPE / DenseReward|自动偏好对齐、失败合成奖励|前者非完整无人闭环；后者代码链接实为空仓|

这里的优先级是针对“少复位、少接管、少值守”的工程判断，不是论文排名。高被引或大机构只提高值得阅读的优先级，不能补足缺失的训练时人工统计。

## 核心审计发现

### 1. RECAP：真实 VLA RL 强证据，但作者明确承认系统并非完全自主

RECAP 把自主试验、示范与人类纠正放进同一个价值/优势条件策略提取循环。衣物折叠的一组消融不使用动作纠正，每轮在四台机器人采 300 条轨迹；盒子装配每轮混合 600 条自主试验和 360 条带干预试验。它证明自主经验可以提高策略，不能证明全过程无需人。报告结论明确仍需人工 reward feedback、interventions 和 episode resets，并说明当前采用批量采集—重训练的迭代离线更新。[论文方法与局限](https://www.physicalintelligence.company/download/pistar06.pdf)

官方 [openpi](https://github.com/Physical-Intelligence/openpi) 是基座公开来源；打开的 README 未给完整 π*0.6/RECAP 发布。网上有第三方复现，但不能把第三方声明、openpi 总 stars 或 π0.5 权重当成本方案官方开源证据。连续数小时咖啡/折衣执行视频也不是连续数小时无人训练证明。[官方博客](https://www.pi.website/blog/pistar06)

### 2. RLinf-USER：适合当运行底座，不负责消除物理人工

论文实测包括 CNN SAC/RLPD、flow 策略 SAC-Flow、π0 HG-DAgger。最后一项是交互模仿，不能笼统称“π0 真机 RL”。附录直接写明旋盖和搬物的奖励与复位由人提供；插销/插充电器利用狭小工作范围与已知目标位姿构造规则奖励。它把设备、网络、异步训练与持久回放管理做成可复用系统，但没有从科学上解决任意物体掉落后的复位问题。[论文表1与附录B](https://arxiv.org/html/2602.07837v2)

[官方仓库](https://github.com/RLinf/RLinf) 提供真实机器人在线学习接口，适合多台/异构机械臂。接入自动复位与验证器后才可能成为用户所需闭环。

### 3. PLD：最贴近自学习目标的 VLA 机制之一，自动化证据随任务变化

PLD 冻结 VLA 学轻量残差专家，让基座先访问其自身容易失败的状态，再由专家补救并采数据；最终以 SFT 蒸馏回基座。Franka 实验先有 200 条人工轨迹，后续在线训练无动作接管；cube 使用 3D 打印桌保证可恢复，peg 的孔位随机化仍由人完成。双 YAM GPU 插拔把任务做成四阶段循环，每子任务最多 8 小时训练，蒸馏后至少连续 1 小时无需帮助，过程允许失败后再恢复。[论文§4.4、附录D](https://arxiv.org/html/2511.00091v1)

原 [项目页](https://wenlixiao.com/self-improve-VLA-PLD) 未找到独立完整代码链接。不过本次进一步核验 [NVlabs/ENPIRE 的 PLD runtime](https://raw.githubusercontent.com/NVlabs/ENPIRE/main/enpire/policy/pld/runtime/README.md)，已经公开从 `minimal_policy@81988f0` 迁入的真实 actor/learner，给出 `uv run enpire rl learner/actor --task pin_insertion`。因此应记为“原论文复现包不完整，但后续官方相关实现可用”，不能简单判不开源。

### 4. ConRFT：有效的人类在环 VLA RL 基线

一致性策略将离线 BC/Q 更新与在线改进连接起来，官方基于 Octo、HIL-SERL、异步 actor/learner。作者报告八任务平均成功率 96.3%，在线 45–90 分钟，每任务最终 20 次评估。但训练期间有纠正接管，八任务中六项 Human reset，只有 Open Drawer、Open Toaster 两项 Script reset。因此高成功率并非低人工劳动的直接证据。[论文及附录](https://arxiv.org/html/2502.05450v2)

[Apache-2.0 仓库](https://github.com/cccedric/conrft) 含训练、采示范、奖励分类器与 Franka 控制接口。对已有 Octo/Franka 用户值得跑通；若一开始就要求无需人在现场，应先补齐任务复位方案。

### 5. SimpleVLA-RL：把“真机评估”与“真机训练”分开

核心是基于 veRL 的 VLA GRPO、二值终局奖励与探索增强。论文真实实验是 sim2real：1000 条仿真示范后在 1000 仿真场景做 RL，最后双 Piper 四任务各 50 次真机评估；表6均值从17.5%提升到38.5%。正文部分任务名和数值与表格不一致，因此不进一步引用单任务细节。[论文§5.3与表6](https://arxiv.org/html/2509.09674v1)

[MIT 仓库](https://github.com/PRIME-RL/SimpleVLA-RL) 2026-01-01 新闻另称有真机 RL 和自动恢复，但仍标 Blog coming soon；这不是可核查的整套免复位协议。其大规模同初始状态多次采样尤其适合仿真。优先级应在仿真筛选，而非直接替换少值守真机系统。

### 6. GR-RL：灵巧专精能力与自主训练能力需分别看

分布型 critic 从成功/失败轨迹学进度，过滤示范次优片段，加入双臂镜像增强，再用 51.5M 参数噪声预测器做线上 RL，引导 flow 动作生成。报告的 ByteMini-v2 真机穿鞋带整体成功率为 83.3%；线上回放刻意排除遥操动作以降低执行分布差异。不过失败样本构造仍标注 retry 关键帧，论文没有完整复位、奖励人工与无值守小时统计。[论文§3](https://arxiv.org/html/2512.01801v1)

未核到 [官方项目](https://seed.bytedance.com/gr_rl) 对应的训练/权重/数据完整公开包。机器人的底盘可移动，也不能据此推出已完成移动操作在线 RL 实验。

### 7. GigaBrain-0.5M* / RAMP：自改进包含人类纠正，开源要冻结版本

RAMP 以世界模型预测未来状态和价值，作为 VLA 更新条件，随后实际运行、专家纠正并更新世界模型/策略。正文多处明确 HIL rollout，而非无人闭环。公开大规模先验数据也意味着其训练资源与小实验室部署条件明显不同。[论文](https://arxiv.org/html/2602.12099v1)

[giga-brain-0 仓库](https://github.com/open-gigaai/giga-brain-0) 本次打开已经演进到 0.7，确有模型训练/推理代码与部分权重，但历史 0.5M* 新闻仅宣告 technical report。不能用 0.1 排行榜、0/0.7 代码与仓库总 stars 来替代 0.5M* 完整 RAMP 发布的证据。

### 8. GRAPE：适合自动偏好构造，不是复位算法

VLM 分解阶段和关键点、生成约束成本，为轨迹对建立偏好，TPO 更新 OpenVLA。真实实验是 Franka+Robotiq，共30任务、每任务10次；真实偏好数据从15任务各5条采样形成75条轨迹，再筛选为30条。它能减少偏好标注，但采样状态一致性、成本阈值和实机复位仍是工程工作。[论文§3.3与附录B/C](https://arxiv.org/html/2411.19309v2)

[MIT 仓库](https://github.com/aiming-lab/GRAPE) 有 TPO-LoRA、HF权重和仿真采样；README仍写真实环境 guided-cost 支持 later，当前单GPU/batch=1轨迹对。目录存在与可复现完整真机闭环不是同一个判断。

### 9. RL-100：真实部署可靠性有价值，复位仍在 future work

BC初始化、迭代离线RL扩充真实数据、最后小预算在线更新及单步蒸馏，既适用于diffusion也扩展flow。arXiv v2统计七任务：平均每任务115条人工示范/1.8h、566条迭代离线rollout/6.5h、434条在线rollout/5.6h。商场7h连续榨汁是部署表现；论文局限仍明确将自主复位与恢复列为后续工作。[论文表7与局限](https://arxiv.org/html/2510.14830v2)

[Apache-2.0官方仓库](https://github.com/Lei-Kun/RL-100) 含训练和数据处理，但真实任务配置仍有reserved/planned段落。可作生成策略真机RL强基线，不能把近100%执行成功直接当作免值守学习证据。

### 10. RoboReward：自动终局评分的强基线，仍有误差上限

4B/8B Qwen3-VL奖励模型给任务视频打1–5分。WidowX下游采用DSRL-SAC，先20条基座rollout热启动、再6000步训练，每任务20次评估。搬猴子5%→50%、开抽屉10%→80%；人工奖励75%/90%，表明自动奖励仍损失学习效果。[论文§5.2与附录B.4](https://arxiv.org/html/2601.00675v1)

[8B模型](https://huggingface.co/teetone/RoboReward-8B)、[4B模型](https://huggingface.co/teetone/RoboReward-4B)、[数据](https://huggingface.co/datasets/teetone/RoboReward)可访问；模型卡标CC-BY-4.0。HELM是评测入口，不应把其总体影响力计到该奖励模型；旧匿名3B/7B稿与当前4B/8B不能混报。

### 11. Robometer：最接近即用自动奖励，但 physical reset 仍人工

帧进度/成功监督与轨迹偏好联合学习，支持真实失败。真实DSRL+π0在10000环境步、约40分钟实验中，单阶段成功率从20%到85%，两阶段从20%到70%；作者明确 automatic 指成功与阶段切换自动化，实体场景仍人工复位。[论文§IV及附录在线实验](https://arxiv.org/html/2603.02115v1)

[奖励仓库](https://github.com/robometer/robometer)与[policy-learning仓库](https://github.com/robometer/robometer-policy-learning)已经有真实DROID/Franka、WidowX、DSRL、异步奖励重标与训练入口；[4B权重](https://huggingface.co/robometer/Robometer-4B)标Apache-2.0。奖励主仓 README 挂 MIT 徽章，但其根 LICENSE 链接返回404，需澄清；policy-learning 仓库的 [LICENSE](https://raw.githubusercontent.com/robometer/robometer-policy-learning/main/LICENSE)已核实为 MIT（Copyright 2026 Robometer），两仓不能合并标许可未知。项目RBM-1M下载仍Coming Soon，不能称完整训练数据已经发布。[真实机器人指南](https://raw.githubusercontent.com/robometer/robometer-policy-learning/main/docs/REAL_ROBOT_README.md)

### 12. DenseReward：有实际权重/数据，Code链接目前为空

通过仿真物理扰动合成失败与阶段进度标签训练dense奖励，真机DSRL冻结π0并调噪声策略。论文两任务只各10次评估；加入DenseReward后叠杯40%→80%、球入篮30%→70%。这是DSRL有无该奖励对比，而非简单的π0基座前后对比。论文仍保留终局任务完成二值锚点，没有明确其自动化来源。[论文§4.4](https://arxiv.org/html/2607.13033v1)

本次实际打开[官网Code仓库](https://github.com/dense-reward/dense-reward)，页面明确为空；[数据集](https://huggingface.co/datasets/densereward/DenseReward)和[模型组织](https://huggingface.co/densereward/models)则真实存在。因此记“权重/数据部分公开，训练代码未发布”，不能照抄abstract的release句子。

## 支持组件与未纳入的相近名字

- **Eureka / DrEureka**：Eureka通过LLM写奖励代码和训练反馈迭代奖励，DrEureka进一步自动设计域随机化用于sim2real。它们有[MIT代码Eureka](https://github.com/eureka-research/Eureka)、[MIT代码DrEureka](https://github.com/eureka-research/DrEureka)，ICLR2024/RSS2024，机构包括UPenn/NVIDIA/UT Austin等。它们减少奖励/仿真调参劳动，不解决真实机械臂每轮物体复位；DrEureka公开环境重点是足式任务，不可直接算移动操作无人在线学习栈。[DrEureka原论文](https://arxiv.org/abs/2406.01967)
- **REBOOT**：2023 CoRL的真实灵巧操作系统包含模仿拾取复位和学习奖励，可重用跨任务数据，是持续自主训练重要先驱。其“无需人工复位”依赖学得拾取和任务装置；不能与同名2026故障恢复数据集混淆。本分支将详细卡留给复位专门分支。[正式论文](https://proceedings.mlr.press/v229/hu23a.html)
- **GenRM**：本次组合检索主要命中通用LLM生成式奖励/推理验证器，而非一个已核实、专门消除机械臂复位和值守的独立方案。没有可靠原始工作映射前不把该泛称塞进候选表。
- **Physical Intelligence RLT**：知识库已有方法卡，根的其他分支负责原文和当前开源状态，本文件不重复将它列为第13项。
- **ENPIRE**：在追查PLD作者页时发现，已交根代理深入核查；这里仅引用其PLD实现入口。全harness与自进化评价以根报告为准。

## 审查口径和建议验证

1. 公开程度分开记录：方法、训练代码、奖励训练、机器人控制、复位、权重、数据、许可证；出现任意一个GitHub链接都不自动判全开源。
2. 影响力分别记录论文引用、精确仓库stars/forks/更新日期、HF近30天下载。下载不是独立用户数，stars不是复现数，基座仓库热度不归给未发布RL版本。量化由根统一批量抓取，当前分支不采用缓存搜索里不同时点的数字。
3. 无接管执行不等于无人训练。至少要分开记：初始示范分钟、奖励标注分钟、人工reset次数/小时、接管动作占比、必须在场分钟、异常不可恢复次数和训练期间最长无人连续时长。
4. 初轮工程筛选建议相同硬件、任务、先验模型和物理交互预算，对比固定脚本/BC基线、RL、RL+自动奖励、RL+自动复位。冻结评估策略，不允许带人接管成功计入最终成功率。该建议尚未执行。

## 检索与来源访问日志

- 背景只读：`embodied-scientist/START_HERE.md`、`ROLE.md`、`state/status.json`、`knowledge/INDEX.md`、`B_D10_online_rl.md`、`B_D11_offline_interactive_rl.md`。首次PowerShell默认编码显示乱码，随后以UTF-8读取关键RL章节；没有修改知识库。
- 全文路径：12项均访问原始arXiv/报告或正式论文；代码通过项目页追到官方GitHub/HF，再读README/许可和运行指南。可读取的9份arXiv HTML纯文本保存于`vla_sources/`，供复查关键附录，URL见`vla_sources/urls.json`。
- 初轮关键词组：`RECAP pi0.6 reinforcement learning`、`RLinf USER real-world robot`、`SimpleVLA-RL ConRFT GR-RL GigaBrain`、`robot VLA autonomous PLD GRAPE REBOOT`；第二轮按方法定向检索official github、reset/human/intervention、paper appendices、license。
- 奖励关键词组：`RoboReward github arxiv`、`Robometer reward`、`DenseReward real-world`、`GenRM robot reward`、`Eureka DrEureka`。普通survey、个人笔记仅用于发现关键词，没有用其总结替代原论文。
- 失败/歧义记录：PLD v2/v3 HTML不存在，改读v1；GRAPE v3不存在，后读v2；SimpleVLA v2不存在，改读v1；本地requests下载RL-100/RECAP超时，改由web打开v2/原始PDF核验；RoboReward猜测个人项目网址失败，改由arXiv跳转到Stanford HELM；Robometer根LICENSE链接404；DenseReward Code真实空仓。
- 当前阶段没有任何安装或硬件命令被执行，没有把README成功加载说成训练复现。所有方案保留实机训练劳动/公开缺口，供用户筛选。
