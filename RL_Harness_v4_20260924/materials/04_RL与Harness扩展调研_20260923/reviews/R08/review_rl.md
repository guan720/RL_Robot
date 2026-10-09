# R08 独立 RL／异步方法审查

**结论：PASS。具体问题 24 项；必要文稿修订 0 项。** 这是冻结稿的定义、推导、证据与融合边界审查通过，不是实现通过、算法优越性证明或真机复现。

审查日期：2026-09-23。审查员：本轮新启动的独立 RL 审查代理。先只读 `embodied-scientist/START_HERE.md`、`ROLE.md`、`state/status.json`、`knowledge/INDEX.md`，以及实际位于 `embodied-scientist/.agents/skills/embodied-research-scientist/SKILL.md` 的技能；未执行 UPDATE／goal、未写知识库。科学输入限于 R08/input 的九份冻结 Markdown。没有打开同轮其他报告，也没有读取输入链接指向的历史评审或继承历史 PASS。

## 1. 审查前枚举的关键点及文档定位

九份输入简称如下；本文行号均指冻结文件，行号区间用于定位而非运行证据。

| 简称 | R08/input 内文件 |
|---|---|
| A | `03_RL_Harness自主学习系统_20260922/01_RL_Harness真机自主学习技术方案.md` |
| I | `03_RL_Harness自主学习系统_20260922/02_接口契约与开发验收.md` |
| T | `03_RL_Harness自主学习系统_20260922/06_异步动作时间轴与学习目标.md` |
| E | `03_RL_Harness自主学习系统_20260922/README.md` |
| R | `04_RL与Harness扩展调研_20260923/01_RL与Harness开源基线深度调研报告.md` |
| V | `04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md` |
| U | `04_RL与Harness扩展调研_20260923/research/02_自主学习与复位扩展调研.md` |
| H | `04_RL与Harness扩展调研_20260923/research/03_Harness扩展调研.md` |
| P | `04_RL与Harness扩展调研_20260923/research/04_训练平台与开源生态核查.md` |

审查覆盖十个关键点：①同一 θ 与全链路 goal；②弱起点的信息来源与双向覆盖；③Harness-DAgger 的质量和信息条件；④真实 transition 与纯标签分流；⑤C/E/D、请求／提交／激活；⑥一槽 TD、终局和抢占；⑦完整头、RAPolicy、RT-EXPO 的学习对象与独立协议；⑧offline latent、部分／反馈监督和 expectile V；⑨版本、缓存、数据保护及发布；⑩通用接口、同预算实验与独立 policy 评估。重点逐段核读 A/I/T/V，并交叉检查其余五份的结论与边界。

## 2. 本轮实际打开的一手资料

以下是本轮重新打开并阅读的主要来源，不是从输入复制阅读声明。访问均成功；没有以检索摘要代替下面的源码／正文。网页阅读未运行源码。

| ID | 实际 URL 与阅读位置 | 本轮用于判断什么 |
|---|---|---|
| S1 | [RAPolicy 论文 v1](https://arxiv.org/html/2609.22888v1)，§III-B/C/D、§IV-A 与实验表 | replay 行为、expectile V、条件 likelihood；十示范单任务与共享五任务的实验条件 |
| S2 | [RAPolicy 固定 worker](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/workers/actor/fsdp_sac_policy_worker.py)，`forward_awac_critic`、`_v2_replay_likelihood_forward`、`_score_awac_actor`，约 L1514–1524、1611–1676、2595–2642 | done 合并、默认 V backup、离线标记消费、部分版本字段清除 |
| S3 | [RAPolicy 固定 sac.py](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/sac.py)，`compute_expectile_value_loss`、`merge_hil_actions_in_model_space`、`prepare_chunk_transition` | HIL 尾部模型空间替换；fixed chunk、有效步和折扣分支 |
| S4 | [RAPolicy 固定 offline 模块](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/data/awac_offline.py)，`resample_offline_latent`、`restore_offline_prompts`、`materialize_awac_offline_buffer` | 在线 latent 保留，离线行重采；占位噪声不是专家噪声反演；离线目标恢复 |
| S5 | [RAPolicy 固定 actor loss](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/rlinf/algorithms/awac_actor_loss.py)，`awac_actor_loss_mode`、`validate_awac_actor_loss_resume`、`forward_awac_flow_actor` | 默认 likelihood 与可选 flow-matching 分开；loss 切换不静默续训 |
| S6 | [RAPolicy 固定 README](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/README.md)；[入口](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/run_rapolicy.sh) → [实际 launcher](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/run_realworld_ablation.sh) | 发布包含训练源码但缺实验权重／示范；`awac` 路由到实际配置 |
| S7 | [Pick Banana 主配置](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_franka2.yaml)及[server_a 覆盖](https://raw.githubusercontent.com/flyfaerss/RAPolicy/ef4b1044f0cc78c0f6143180a2d78ae267ab03ea/examples/embodiment/config/realworld_pick_banana_sac_pi05_server_a_franka2.yaml) | `actor_objective: v2_awac`、fixed chunk、推理 hold、一步采样、checkpoint 保存配置 |
| S8 | [RT-EXPO 论文 v1](https://arxiv.org/html/2609.18207v1)，§III、§IV-B/C、§VII-E.3 | 延迟候选与新观测编辑；启动条件；两种延迟实验分别解释 |
| S9 | [RT-EXPO 固定实时学习器](https://raw.githubusercontent.com/pd-perry/expo-ft/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/realtime_expo_ft.py)，`_jitted_fast_select`、`update_actor`、`update_edit_actor`、`update_critic` | `[delay:delay+replan_steps]`、基础／编辑器分开更新及 `discount**replan_steps` |
| S10 | [DAgger 一手全文](https://proceedings.mlr.press/v15/ross11a/ross11a.pdf)，§2–3、Algorithm 3.1、Theorem 3.1/3.2；同时打开[PMLR 页面](https://proceedings.mlr.press/v15/ross11a.html) | 访问状态上的标注与聚合；原理论中的专家／损失条件不能自动转给不完美 Harness |

另实际打开过 S4、S5 对应固定 GitHub blob 页面，并回到上表 raw 正文定位。没有访问不可公开的训练资产，没有安装、训练、benchmark、自动微分或真机运行。S7 是选定公开配置的静态事实，不把它推广成仓库所有分支都只有一种执行方式。

## 3. 24 个具体问题与逐项判定

“通过”表示文稿在当前设计阶段已给出正确区分；“通过／实测门槛”表示缺的是已明确承认的实现或证据，不据此人为制造文稿阻断项。

| # | 具体问题 | 文档定位 | 独立依据与回答 | 判定 |
|---|---|---|---|---|
| 01 | 是同一 θ 学正反，还是语言不同、背后两套策略？Q、target、BC 与奖励也条件化吗？ | A §5 L88–109；I §5.2 L219–225；E L5–9 | 两向共享表征／actor／发布版本，goal 贯穿所有训练与评分路径；T17/T24 要查计算图和双向行为。多任务能力不等于自动正迁移，文稿没有作此推断。 | 通过 |
| 02 | 反向真在学习，还是 reset 脚本换名？正向成功后能直接切反向吗？ | A L92–109；I §5.5；U L26–34 | 文稿明确正常反向由共享 policy 学习，异常恢复另记；必须检查反向 init-set，并关闭旧 episode、清队列。两边缘成功率相乘也被明确禁止作为循环可靠性估计。 | 通过 |
| 03 | 初始零成功是否被误说成无需示范、纠正或有效探索也能启动？ | A L29、39、223–225、266–279；R L54；V §11.1 | S1 的弱初始实验仍有示范与接管。稿件允许零自主成功，同时要求基本可控行为或可信局部纠正，并用 BC／覆盖预检决定动作头；没有从“完整动作空间”推出必然能探索成功。 | 通过／实测门槛 |
| 04 | Harness-DAgger 是否偷换成完美强 teacher，或不当继承 DAgger 保证？ | A L41、131–141；I L7、195–201；V L289–300 | S10 要在访问状态查询标注并聚合，理论还涉及损失与专家条件。稿件只借聚合思想，明确 GPT 纠正未知质量；动作标签受时效、可表达性、可观察性及质量约束。 | 通过 |
| 05 | 失败、次优接管与未执行建议分别进什么 loss？长期 buffer 是否被误当成 TD 资格？ | A §9 表；I §5.1、§5.4；U L169–184 | 失败可有真实 TD，BC 另筛质量；影子建议可长期保留但不能配别人动作的后继。即便收到成功评分，也不能给未采用候选补真实后果。与 S2/S3 的行为动作训练边界一致。 | 通过 |
| 06 | 为什么当前回报由旧 C 产生，却配本次 U？是否奖励错位？ | T §2.1–3.3，尤其 L79–85、107–148；A §8.2 | 按稿件定义，环境包括队列：X=(h,g,C,ξ)，当前槽执行 C，U 改变 next queue。故 `R_k+γ^n Q_target(X_next,π_target(X_next))` 的作用通过下一状态传播。是自洽的一决策延迟模型；没有把下一槽 reward 偷挪到当前。 | 通过 |
| 07 | C/E/D 是否仅是一个执行前缀 mask？当前 proposal 的 C 可否当真实 C？ | T L15–34、48–61、154–163；I T05/T13 | 旧 C 来自实际承诺；本次决策是 E，D 被丢弃。Q 动作导数只经 E，但共享参数可间接改变其他输出，稿件已经说明。数值算例为索引6–11，未把执行长度6误写成索引0–5。 | 通过 |
| 08 | 未激活的新 U 遇到旧 C 终止时，terminal 数据有依据吗？ | T §5.1 L194–211；I T11 | 事前真实 request 冻结输入／权重／随机性，其原计算结果仍可构成此延迟决策的终局动作；终局前物理转移不依赖 U。文稿禁止终局后重算候选、补 request 或制造 next queue，结果缺失就不训练该动作。 | 通过 |
| 09 | 成功的正奖怎样回到真正负责执行的前一 U？是否选择性回填产生偏差？ | T §5.2、例3 L294–298；A L215 | terminal critic 使用当前槽真实回报，前驱通过正常 Bellman 链传播；没有按后一槽是否成功选择长／短 target。`0.9^6×0.9^2` 的手算对应奖励时间。例子仍标待实现，未伪称测试通过。 | 通过／实测门槛 |
| 10 | terminal 行不更新 actor 是否被说成完全无偏？ | T L211 | 稿件明确这是采样选择，并承认随机终止会给 actor 状态分布乘存活权重，共享参数折中可能改变。要求按方向／状态类记筛除率；没有篡改 critic 后果来补 actor。 | 通过／实测门槛 |
| 11 | 超时、抢占、日志缺失与真实终止是否混成 done？ | T §5.3、§6.2、§7；I T07/T12 | 文稿明确中断／删失不设零未来值；先发生改队列再成功不能追认为合法 terminal。此前完整边界的一步转移可留，边界本身不可信则一起隔离。S2 恰合并 termination/truncation，稿件已点名不能原样移植。 | 通过 |
| 12 | 隔离干预窗口会不会仍学到选择偏差或覆盖不足？ | A L217、247；T L249–255；R L199、246 | 会。删失不是无偏校正，稿件已经要求报告隔离比例、保留可恢复范围的独立尝试和分别评估无辅助策略；没有声称仅删异常就恢复正确的完整动力学估计。 | 通过／实测门槛 |
| 13 | Harness 新反馈生成的多步纠正能否倒填早先 open-loop chunk？ | A L137、165；T §4.3、§6.2；H L124；I T32 | 不能作为首版同信息集 U／普通 BC。稿件保留逐时刻事实，允许另设反馈或特权监督分支；普通队列标签需重建当前决策点。S3 的混合行为数组只是上游记录，不能自动证明它在项目槽起点已选定。 | 通过 |
| 14 | 部分动作标签与 flow 训练是否只在最后 loss 乘 mask 就够？ | T L188–190；I L255–257、T14/T39；V L369 | 稿件已要求完整可信窗口或验证未知输入、attention、目标与推理处理，禁止单步复制成 n 步。S5 的 padding/inactive-dimension mask 不能自动等于任意缺失时间标签；项目没有作此兼容承诺。 | 通过／实测门槛 |
| 15 | RAPolicy 的 async 是否已经满足连续 C/E/D 执行？ | V L351；A L270、291–293；T L339 | S6 launcher 追到 S7：该公开配置 train/eval 均设置推理 hold。论文 S1 的并发重点是 rollout/learner。稿件据此允许原生 hold 预检，但明确不能作为最终连续执行通过证据，队列原生路线另推导。 | 通过 |
| 16 | RAPolicy 学的究竟是什么？会不会误用本项目 actor-Q 梯度公式？ | V L339、352、355、369；A §10.4；T L339 | S1/S2/S3 支持 replay Q、expectile V、下一状态 V backup；S5 默认 likelihood，flow 为显式消融。稿件准确区分优势加权行为回归与对当前动作求 Q 导数，要求 actor/Q/V 全部适配 goal/C。 | 通过 |
| 17 | 没有 rollout latent 的离线真实 demo 被错误排除，或伪造为在线采样吗？ | V L356；A L295；I T39 | S4 明确离线行重采、在线行保留；S2 读取 `is_offline_demo`。稿件没有否定真实 demo 的 Q/V 资格，也没有声称恢复了专家 latent；actor 监督模式与真实后果资格分开。纯建议仍不可做 TD。 | 通过 |
| 18 | 重采 latent 得到的是边缘 flow likelihood 吗？优势权重或高 V 可证明无辅助能力吗？ | V L356、369；A L297；R L104 | S4 目标是条件 log-density 的期望，S1 的 V 是 replay Q 的上 expectile。稿件明确两者均不是这些更强结论；持续要求关闭辅助评估。离线重采对多模态动作先验的影响留给预检。 | 通过／实测门槛 |
| 19 | fixed chunk 的接管／终局尾部和有效步折扣，会被当作物理实录吗？ | V L353–354、363；T L339；I T39 | S3 明确 fixed chunk 要求填满，另有有效步折扣分支；S7 开启 chunk-aware discount。稿件区分上游张量约定与实际执行，禁止填充变物理事实，且没有机械替换论文 chunk γ 与项目微步 γ。 | 通过 |
| 20 | RT-EXPO 是否被误说成 Q 直接更新原生 flow，或仅冻结 base 的残差？ | V §4.3；R L83；A L269–270 | S9 分开 `update_actor` 与 `update_edit_actor`；前者走基础训练接口，后者由 Q／熵更新编辑。稿件保留 base 随 BC 改变的事实，也保留候选／编辑覆盖限制。S8 启动要求与弱起点条件分开，未强加给项目。 | 通过 |
| 21 | RT-EXPO `[d:d+C]` 和 `γ^C` 能直接换成当前队列 target 吗？实验的延迟单位一致吗？ | V §4.4–4.4.1；T §11；R L79–87 | S9 的窗口切片与 `discount**replan_steps` 可核；其新观测编辑与项目冻结 X 的时刻不同。S8 又区分 wall-clock sleep 与旧帧 chunk delay。稿件逐一分开，未把注入时延当设备自然 deadline。 | 通过 |
| 22 | 异步版本、normalizer、cached feature 与 replay 能只靠同 shape 复用吗？ | A §11；I §6.1、T26/T27/T39；T L267–270；P §10/13 | 不能。S2 的输入处理确会清除部分 versions，S4 缓存要求冻结特征。稿件要求自有事实版本、重算或隔离、协议迁移和边界发布，不声称 RAPolicy fork 等于 RLinf 主线。 | 通过 |
| 23 | 训练平台有 SAC 和 π0.5 标签，就能承载确定性完整头目标吗？ | P L35、94–100；I L398；R L38、175 | 稿件要求替换具体 target/动作／数据接口，并明确不把假 `log_pi` 或熵温度塞给确定性 actor。与 S7 同仓名称含 SAC、实际 AWAC 的例子相符；功能表不是组合兼容性证据。 | 通过 |
| 24 | 框架选择是否仍由 AgileX 适配或单一成功率主导？新原生候选是否只是形式对照？ | A L11、266–279、291；I §9.1；R §9.2；H L194–206；E L9 | 通用 schema、可替换模型／本体／learner、数据和时间契约优先；RAPolicy 可在完整头长训之前胜出。对照分学习器、骨架、系统辅助三轴，固定信息来源与预算，另报独立双向能力和人工成本。没有以仓库热度、品牌或跨论文分数定冠军。 | 通过／实测门槛 |

## 4. 必要缺陷、现有实测门槛与可选优化

**必要文稿缺陷：未发现。** 本轮没有发现需要改变 PASS 的来源反证、目标不闭合、未来信息偷用、伪 TD、强 teacher 偷换或必需候选被错误排除。没有把“尚未写实现”变成所有拟议设计必然不通过的理由。

**文稿已经列出的实施／实测门槛，仍需执行：**

1. 固定槽的真实 request、commit、activation、next queue、奖励时域和 C/E/D 梯度测试，尤其终局、并发抢占与 deadline 边界；对应 I T05–T16、T 的六个算例。
2. 同一 checkpoint 双向 BC、动作覆盖和目标依赖预检，确认弱起点至少获得可信局部行为／纠正；对应 A P0/P1、I T17/T24。
3. Harness 判定与动作质量校准，分别测同信息集纠正、反馈纠正和部分标签的数据资格；对应 A P2、I T14/T32/T35。
4. RAPolicy 的 goal/C/Q/V、原生 actor 监督与 latent、终止和折扣需独立推导及实现；当前 hold 对照不满足连续执行验收。RT-EXPO 也必须保持自己的观测与执行窗口协议；对应 I T34/T39、T §11。
5. 记录终局 actor 筛除、干预隔离、unknown 奖励及双向覆盖，检查可用 TD 密度与状态选择偏差；现有门槛不是无偏性证明。
6. 锁模型与依赖、恢复完整版本包，再在等任务／信息／示范／纠正预算下比较独立 policy、辅助系统和人工工时；通用 adapter 回放不能替代跨本体真机结果。

**可选优化，不阻断本轮：**

- 将 I T39 的版本验收补成“评测导出与可续训快照分开”的显式子例。S7 L453–456 指定 `save_training_state: False`，其周期性产物是评测权重；项目 I L273 已要求优化器／回放等完整包，实施者宜在恢复测试中直接验证这项差异，避免把有 `.pt` 文件当可续训。无需本轮为此改科学结论。
- RAPolicy 预检可单列在线原 latent、离线重采、可靠纠正三个 actor 数据来源的损失与行为覆盖统计，并观察离线重采是否压缩多模态。当前已经声明监督模式与质量门槛，不必在尚未决定采用前扩展成新算法。

最终判定维持 **PASS：24 问，必要修订 0 项**。本审查仅支持当前冻结稿在以上问题上的逻辑与证据边界；所有训练、时序测试、框架安装和真机收益均未执行。
