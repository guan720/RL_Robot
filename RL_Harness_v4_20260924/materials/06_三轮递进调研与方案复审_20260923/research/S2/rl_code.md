# S2 RL 源码链：纠正标签、未来状态与真实在线回报

核查日期：2026-09-23。本轮先读会话约束、科学家只读入口、06任务契约、S1根审和RL报告，再枚举问题、固定版本并读源码。只做静态研究；未安装依赖、执行第三方训练/测试、下载模型或运行真机。下载成功不等于逐行读完；实际阅读函数和失败请求见 [rl_code_log.json](rl_code_log.json)。

**结论：主算法预检顺序暂不改。** RAPolicy仍优先检验原生头学习可达性，RT-EXPO仍优先检验实时执行；完整头＋BC＋队列RL保留作明确参考。FluxVLA可借训练与部署组件，FluxDAgger可借采集结构，但本轮发现默认动作/标签链的具体缺口；ARM不能直接充当主TD。FutureRTC升为有条件的延迟补偿消融，不能据其真机发布宣称连续C/E/D和在线RL已解决。ForceRFT保留为接管数据语义及接触残差参考，不把其片段价值目标混入当前队列目标。

这里的部署policy可包含VLA、必要的learned predictor/editor/动作头/Q选择器；共同冻结、共同计成本、共同评估。底模冻结不是排除理由；复合policy变强与底模参数变强分开报告。独立评估关闭GPT Harness临场动作辅助，保留算法自身必要部件。

## 1. S1之后实际问了什么

| S2问题 | 相对S1的新证据 | 取舍变化 |
|---|---|---|
| Flux纠正能否直接成为可信动作标签？ | 默认collector命令topic与human执行topic不同；SDK前还有限步插值、夹爪截断；缺命令补零；mode在保存时读取 | 不能照搬`/action`或`/data_flag`进入BC/TD，采集适配先于奖励加权 |
| ARM advantage是否来自在线critic？ | 已追到有GT progress的奖励模型分类训练、离线progress重建、样本权重、原生flow MSE；无此链的Bellman备份 | 是加权BC链，不替代真实在线RL；发现常量失败轨迹也可被重建为上升进展 |
| FutureRTC宣称分支是否可达？ | 三个分支均存在，真机client/server/predictor训练源码可读 | 不再写“只见README”，但各分支损失、资产和时序必须分别列 |
| 真机FutureRTC在学什么？ | 真机仅latent MSE；corrector返回末个承诺目标；LIBERO有冻结policy的consistency分支 | 是可学习的上下文补偿，不是低层TD；不能把仿真loss笼统套到真机 |
| 其reset/late结果满足C/E/D吗？ | 固定25步窗口/10步提前；窗口尾阻塞等结果；停止时不取消已发后台请求；server reset仅清z_init | 加代际、失效、物理回执并处理deadline前，不能替换当前运行协议 |
| ForceRFT接管截断能否直接复制？ | §IV-D明确自主片段surrogate，拒绝缺失后继伪terminal；人工gripper/base条件不同 | 吸收记录资格经验；保留本项目“前驱事实完整则保留、当前破坏槽隔离” |

最终仍需同一目标条件policy从低成功起点双向学习；Harness只提供纠正和练习机会。以下证据不证明本项目已满足该联合目标。

## 2. 固定版本及读取边界

| 项目/分支 | 本轮固定commit | 确认方式及范围 |
|---|---|---|
| FluxVLA main | `3fe5d10cf56ae33787baf58efaf12bfbce2393d0` | Git refs＋tree；2026-09-23提交；ARM、π0.5继承的flow loss、train/export/ROS serve关键段 |
| FluxDAgger main | `b3bf6175d865c41605c00f01aa3b5b0a5deda1e9` | Git refs＋tree；2026-05-29提交；launch、controller、Piper callback、collector、schema、导出及reward node |
| FutureRTC dev/realworld | `8ea9abc9e26fabc1ec585cc1fe027e65fc67b517` | Git refs＋tree；2026-07-29提交；真实client/server、协议、corrector、predictor trainer及batch loader |
| FutureRTC sim/libero | `57310be57b13cb2284d25c9ab7f636e9cf77fa90` | Git refs＋tree；2026-07-29提交；README、predictor trainer、π0.5 policy-loss冻结边界 |
| FutureRTC sim/Kinetix | `c7381095d4aff16f121625500d377bc199ceb090` | Git refs＋tree；2026-07-29提交；README与资产/依赖路径筛查，不声称完整执行链深读 |
| FutureRTC main | `67cb0b0e46cf66a800cfd4a78a5bcbcf3d360794` | refs确认；main只是分支入口，本轮不以它代表三条实现 |

GitHub未认证API三次均403限流。Git默认代理127.0.0.1:7890不可达，仅对单次命令清空proxy后取得refs与无blob的partial clone；未改全局配置。后续选定文本从固定SHA raw下载。git按路径取blob/checkout遇到连接重置及读对象失败，**报告引用的是成功保存的`text/`快照，不把失败checkout说成可运行工程**。raw下载清单保留所有失败；无完整依赖锁定或独立复现证明。源码许可在各仓LICENSE实际读取，权重和数据另论。

## 3. FluxVLA／FluxDAgger：数据桥有用，默认事实链不够

### 3.1 从入口追到控制、采集、标签

`src/dagger/launch/dagger.launch` L50–100启动controller、四个arm node和同步观测节点；其后启动collector。该包依赖外部VLA发布约定topic，不是内部自带在线learner。[固定launch](https://github.com/FluxVLA/FluxDAgger/blob/b3bf6175d865c41605c00f01aa3b5b0a5deda1e9/src/dagger/launch/dagger.launch)

`handle_human_mode`先广播`is_human_mode=True`、发collector命令，再将后臂切master、等待并改前臂订阅；`handle_inference_mode`逆向切换。它提供模式开关和状态发布，**未见本项目要求的owner代际、旧请求失效与驱动物理取消回执**。不能把全局bool等同于原子控制权交接。[controller L333–385](https://github.com/FluxVLA/FluxDAgger/blob/b3bf6175d865c41605c00f01aa3b5b0a5deda1e9/src/dagger/scripts/dagger_controller_node.py#L333)

四个值得进入S3的静态反例：

1. **默认human标签与动作topic不一致。** Collector初始化L124–145默认固定订阅`/master/joint_left/right`。配置L95–127与controller `_set_front_arms_subscribe_human` L183–189却把human执行改为`/master/joint/left_human/right_human`；已读collector没有随模式切换动作订阅。由此推断，默认`/action`可能仍是模型命令，或模型停止发布后缺失；不能自动视为人工纠正。可通过配置/外部统一命令topic适配，但本轮没有该适配证据。[collector](https://github.com/FluxVLA/FluxDAgger/blob/b3bf6175d865c41605c00f01aa3b5b0a5deda1e9/src/dagger/scripts/dagger_collector_node.py#L124)、[配置](https://github.com/FluxVLA/FluxDAgger/blob/b3bf6175d865c41605c00f01aa3b5b0a5deda1e9/src/dagger/config/default.yaml#L95)
2. **保存的命令不等于最终SDK命令。** `PiperArm.joint_slave_callback` L314–385按上次命令对大跳变限步插值，之后将夹爪约束到0..80000，才调用`JointCtrl/GripperCtrl`。Collector从输入topic构建action，没有在这条函数后收到对应`actual_pos`回执。实测qpos另存，但不能用它倒推每条命令已接受/生效。[硬件callback](https://github.com/FluxVLA/FluxDAgger/blob/b3bf6175d865c41605c00f01aa3b5b0a5deda1e9/src/dagger/dagger/hardware/piper_arm.py#L314)
3. **缺动作不能解释成真实零动作。** `_pop_up_to` L716–721每帧消费`stamp≤frame_time`的新消息；该次没有新消息则返回None，`_build_action` L742–750为缺失一侧填七维零。即使物理端仍保持旧命令，记录也可能变成零。应保留last accepted command、年龄与validity，禁止以补零张量冒充执行事实。[动作构造](https://github.com/FluxVLA/FluxDAgger/blob/b3bf6175d865c41605c00f01aa3b5b0a5deda1e9/src/dagger/scripts/dagger_collector_node.py#L716)
4. **积压观测的owner可被保存时mode覆盖。** `save_frame_from_synced` L259按当时`self.is_human_mode`填`data_flag`，不是按命令/传感时间的owner事件回放；切换前积压观测可能被标成human。`GlobalState.msg`只有三个bool与字符串，无切换时间/epoch。此为可构造的静态风险，未声称实机已出现。[帧存储](https://github.com/FluxVLA/FluxDAgger/blob/b3bf6175d865c41605c00f01aa3b5b0a5deda1e9/src/dagger/dagger/collectors/sync_frame_collector.py#L254)

已确认有价值的基础：真实qpos/qvel/effort/eepose、多视角图像、传感时间、human标记、原始chunk另存；raw chunk还有最大时间差过滤。`_save_data_parquet`保存`/action,/data_flag,/success,/score`；`parquet_to_mp4_npy.py` L162–175分别直接导出qpos/action，没有在此修复动作语义。终局成功由collector向操作员询问，成功后再询问1–5评分（L413–442），不是自动可信任务判定。

在线Qwen reward node有episode/step/stamp/value/done/confidence/source，异步发布（`_run_inference`、`_publish_reward` L129–162）；这不等于其输出已经进入actor–critic。其模型实现文件本轮raw失败，未核提示词质量/校准。`task_id`、checkpoint目录名和reward prompt有入口，但已读采集结构不足以证明每条transition含显式A→B/B→A goal、模型内容哈希和独立奖励版本。

### 3.2 ARM reward/advantage是谁产生的，actor究竟优化什么

已核到的链是：**带GT progress的数据 → ARM分类模型 → 离线预测/重建progress sidecar → RA/AW-BC权重 → policy flow-MSE → checkpoint**。它没有在已读入口产生`r+γQ`或`r+γV`。

| 环节与实际函数 | 源码事实 |
|---|---|
| `ARMDataset._compute_interval_targets_from_progress` L98–105；`__getitem__` L156–167 | 从已有每帧progress差分产生−1/0/+1标签；缺progress报错 |
| `ARMRewardModel._build_success_targets` L198–200；`forward` L271–304 | progress接近1作为成功标签；损失为interval CE＋success focal loss，非Bellman TD |
| `predict_advantage` L312–378 | 输出success概率与interval分类预测；函数名advantage不表示Q−V |
| `compute_arm_awbc_progress._build_output_rows/_write_progress_parquet` L90–145 | 分episode离线运行模型；保存global index、episode、长度、重建progress以及reward_model_path元数据 |
| `ArmRABCWeighter._future_progress/_compute_weights` L140–149、203–216 | `Δp=p[min(t+H,T−1)]−p[t]`；负值0、大于κ取1、小正值软权重，缺失默认1 |
| `ArmAWBCWeighter._duration_weight/compute_weight` L292–299、341–346 | 再乘episode长度/平均长度；是样本重权，不是训练出来的动作价值 |
| `AttachRABCWeight.__call__` L55–63；π0.5继承`PI0FlowMatching.forward` L649–760 | 权重进入样本；flow目标`noise−actions`，逐元素MSE后传`reduce_action_bc_loss`与action mask |

固定来源：[ARM dataset](https://github.com/FluxVLA/FluxVLA/blob/3fe5d10cf56ae33787baf58efaf12bfbce2393d0/fluxvla/datasets/arm_dataset.py)、[奖励模型](https://github.com/FluxVLA/FluxVLA/blob/3fe5d10cf56ae33787baf58efaf12bfbce2393d0/fluxvla/models/vlas/arm_reward_model.py)、[weighter](https://github.com/FluxVLA/FluxVLA/blob/3fe5d10cf56ae33787baf58efaf12bfbce2393d0/fluxvla/weighters/arm_rabc.py)、[flow loss](https://github.com/FluxVLA/FluxVLA/blob/3fe5d10cf56ae33787baf58efaf12bfbce2393d0/fluxvla/models/vlas/pi0_flowmatching.py#L649)。最末reduction helper的raw抓取失败；已确认调用及加权BC性质，不声称独立深核了其所有mask/分母边界。

**新反例：零进展失败也可能被赋予正进展。** `build_cumulative_progress`在没有success预测时用本episode累计interval最小/最大值归一化；累计值全相同时L101–102改用`np.linspace(0,1,...)`。两个以上全零interval关键帧、success全假，会得到上升曲线，随后chunk差分可以为正。这是源码可推出的结果，未执行第三方函数。即便不是常量，单轨迹min-max也不校准跨轨迹真实成功。它可以作为待验证的BC采样启发，**不能直接变成主TD奖励、可靠成功概率或“从全局零成功可启动”的证据**。[progress重建 L34–109](https://github.com/FluxVLA/FluxVLA/blob/3fe5d10cf56ae33787baf58efaf12bfbce2393d0/tools/arm_awbc/progress_reconstruction.py#L34)

此外，sidecar用global index对齐，重排/追加/聚合数据后必须重建映射并版本化；仅保存reward模型路径不等于内容哈希。失败数据可被加权BC使用，不意味着它已进入真实online replay/critic。人类整回合success也不能替代ARM训练所需逐帧GT progress。

### 3.3 train→checkpoint→服务与资产门槛

`scripts/train.py` L431–470构建配置的数据集、保存统计量与resolved config、可用时保存tokenizer、build runner再`runner.run`；DDP `save_checkpoint` L328–494保存模型/步数/epoch、可选优化器/EMA、safetensors和latest链接。ROS `build_ros_policy_from_config` L749–821加载指定checkpoint、统计量、transform/dataset；非环境空间输出且缺统计量会报错。这是可借的部署链，**未在已读路径看到learner新权重原子激活、在途chunk与policy版本绑定、双向晋级回滚契约**。[train](https://github.com/FluxVLA/FluxVLA/blob/3fe5d10cf56ae33787baf58efaf12bfbce2393d0/scripts/train.py#L431)、[export](https://github.com/FluxVLA/FluxVLA/blob/3fe5d10cf56ae33787baf58efaf12bfbce2393d0/fluxvla/engines/runners/ddp_train_runner.py#L328)、[serve](https://github.com/FluxVLA/FluxVLA/blob/3fe5d10cf56ae33787baf58efaf12bfbce2393d0/fluxvla/engines/runners/serving/ros_server.py#L749)

## 4. FutureRTC：三个实现不同，真机不是低层RL

### 4.1 哪个分支更新什么

| 分支 | 实际训练/资产证据 | 本项目含义 |
|---|---|---|
| realworld | `train/ours_pi05/train_predictor.py` L135–174：AdamW只含predictor参数，normalized latent MSE；L190–201保存predictor＋latent_norm＋action_quantiles。`fast_loader._fill_one` L113–126由bank取`z[t]→z[t+d]`，动作`[t:t+d]`及corrector状态 | 有学习的复合执行包，未见在线reward/TD；换policy/归一化/纠正分布后预测器兼容性须再验 |
| sim/libero | `predictor/train.py` L244–259可启用policy-loss；L300–318在重建loss上叠加consistency，optimizer仍只更新predictor。`policy_loss/pi05.py` L71–73显式冻结policy；README给phase2权重10 | 不可照抄真机注释中“LIBERO权重可能0”的未证实说法；源码确有可启用分支，但未下载权重验证其训练历史 |
| sim/Kinetix | README：精确仿真推进robot状态＋每关卡latent predictor；目录有12份predictor文件名，外部RTC/Kinetix与bc31另取；作者特别要求on-policy predictor数据 | 仅资产和分支机制筛查；精确仿真状态推进不能当真机能力，作者on-policy要求提示更新policy后的分布漂移 |

固定来源：[真机trainer](https://github.com/JianghaiSCU/FutureRTC/blob/8ea9abc9e26fabc1ec585cc1fe027e65fc67b517/train/ours_pi05/train_predictor.py#L135)、[真实batch loader](https://github.com/JianghaiSCU/FutureRTC/blob/8ea9abc9e26fabc1ec585cc1fe027e65fc67b517/train/ours_pi05/fast_loader.py#L113)、[LIBERO trainer](https://github.com/JianghaiSCU/FutureRTC/blob/57310be57b13cb2284d25c9ab7f636e9cf77fa90/predictor/train.py#L244)、[policy冻结](https://github.com/JianghaiSCU/FutureRTC/blob/57310be57b13cb2284d25c9ab7f636e9cf77fa90/predictor/policy_loss/pi05.py#L71)、[Kinetix分支说明](https://github.com/JianghaiSCU/FutureRTC/blob/c7381095d4aff16f121625500d377bc199ceb090/README.md)。

真机`Corrector.__call__` L74直接返回`committed[delay−1]`，`residual_ckpt`非空则NotImplementedError。注释所说`action_t=qpos_{t+1}`是作者对采集数据的报告；不是物理执行必然等于目标。本轮未取得该原始HDF5。注释也承认部署存在跟踪误差、需要新配对数据；已读主client未调用协议文件的`save_gap_log`，因此不能说该误差日志已贯通。[corrector](https://github.com/JianghaiSCU/FutureRTC/blob/8ea9abc9e26fabc1ec585cc1fe027e65fc67b517/infer/ours_pi05/models/corrector.py)

### 4.2 真实调用链和承诺队列

client `run_one_episode` → `send_reset` → 首块同步`query_server(delay=0)` → `executed_slice(C)[0:25]` → 插值到控制点 → 第15个raw动作边界启动`AsyncChunkFetcher.submit` → HTTP发送旧观测和`action_slice[15:25]`十步承诺 → server `infer_ours`预测交接latent/state → 冻结π0.5采样 → 下一窗口。协议明确`S=25,d=10,H=50`；动作是14维绝对关节角。[共享协议 L38–91](https://github.com/JianghaiSCU/FutureRTC/blob/8ea9abc9e26fabc1ec585cc1fe027e65fc67b517/infer/ours_pi05/deploy_protocol.py#L38)

server执行：旧图像编码、缓存首帧`z_init`、末个承诺目标作`s_hat`、相对旧状态的动作归一化并左对齐pad、预测latent、用`s_hat`重建包括离散state token的观测、注入bf16 latent、通过policy输出变换返回动作。不能只改已经tokenize后的`.state`；这条实现细节值得借鉴。[server L241–312](https://github.com/JianghaiSCU/FutureRTC/blob/8ea9abc9e26fabc1ec585cc1fe027e65fc67b517/infer/openpi/deploy_policy_server_ours_local.py#L241)

**正常重叠不等于本项目全套连续C/E/D。**

- client L597在窗口尾`fetcher.get(timeout=50)`，结果迟到则执行线程等待，未见按deadline拒收/持续替补协议。对固定提前10步的预测而言，额外等待不在该动作步数中；是否仍稳定是未知，不能以async线程存在代替连续性证明。
- 接管在这里是用户Enter停止episode（L570–589），不是Harness接管后带新owner继续。已发daemon worker没有取消/epoch；新episode新fetcher避免直接复用旧结果，但server只有单一`z_init`，reset L230–232仅清缓存。旧请求延迟到reset之后的顺序未被代际契约封住；这是待注入的竞态反例，不宣称已观察到串局。
- 承诺十步来自raw计划，不含之后的夹爪阈值化/控制点插值及驱动接受结果。client L551先`clip_grippers`再control；保存L585却保存raw端点，且中途停止只记录完成raw边界，部分插值段的物理命令不在该数组。这是作者用于评测计步的记录，不足作本项目逐帧执行账本。
- server L363固定使用启动参数`model.prompt`；client观测不带任务指令。当前真机配置每任务单独训练，未证同一θ显式goal在线切换的双向学习。

这些事实均来自 [client L344–405、503–629](https://github.com/JianghaiSCU/FutureRTC/blob/8ea9abc9e26fabc1ec585cc1fe027e65fc67b517/infer/cobot-magic-real/deploy_policy_local_ours_batch_test.py#L503) 和 [server reset/请求](https://github.com/JianghaiSCU/FutureRTC/blob/8ea9abc9e26fabc1ec585cc1fe027e65fc67b517/infer/openpi/deploy_policy_server_ours_local.py#L331)。适配顺序应为执行事实/代际/延迟测量→正确预测监督→双向goal→测是否值得引入predictor，不能逆序。

## 5. ForceRFT：片段价值与当前队列目标的区别

[ForceRFT v1 §IV-C/IV-D](https://arxiv.org/html/2609.22840v1#S4.SS4)明确：控制器接受的自主决策才产生transition；critic以**处理前residual proposal**为动作，控制器修改进入环境动力学。context另含base gripper，人工固定base/独立gripper的执行条件不同，故人工只提供投影到残差域的BC。Eq.(7)为`y=r+γβ Q̄min(ξ′,π̄(z′))`：真实同段后继β=1，真实task/takeover/reset边界β=0；非边界缺后继丢弃，不伪造terminal。接管后的成功不回传早先自主段；它是作者明示的自主片段return surrogate。仅残差actor/critic在线更新，原生VLA冻结；这仍是学习的复合policy。以上是论文规定，未定位可核训练代码，不声称实现验证。

与本项目的比较是**目标/动作定义**，不是谁更“严格”：

| 项目 | ForceRFT §IV-D | 当前06队列设计 |
|---|---|---|
| 决策单位 | 每次被接受的residual proposal，控制处理属于环境 | 槽起点状态X含已承诺C，新请求U决定后续队列；当前槽回报对应当前C |
| 接管影响 | 对实际自主段边界设β=0，限制本段TD信用 | 接管破坏当前槽C/E/D则隔离该宏TD；保留微步事实/可用BC，不自动done |
| 完整前驱 | 本段信用在接管边界截止 | 前驱已有准确next state/next queue则保留原一步target；边界本身不确定才一起隔离 |
| 人工经验 | 由于自主/人工动作条件不同，不用于该critic | 同协议、同动作定义、真实后继合格的Harness决策可进主TD；反馈式临时动作不硬拼宏转移 |

对照依据为 [06异步附录§6](../../appendices/02_异步动作时间轴与学习目标.md)。本项目不应偷偷把“被接管”改为失败奖励；ForceRFT也不能证明在我们的任务中截断surrogate等价于完整独立成功。两者都有干预选择偏差：只保留未接管窗口，或在操作员/检测一致后纳入episode，会改变训练分布。保留前驱并不能自动消除这种偏差；须记录隔离率、接管原因、困难状态覆盖并安排受保护的自主复尝试。

ForceRFT还限制TCP残差、自主gripper沿用base；错误释放时刻未必可由残差直接修复。首任务若不具腕力传感，不为本轮选型强加硬件；其可借价值主要是proposal/accepted/observed区分、真实后继资格和监督投影不篡改事实。论文的独立评估仍保留残差policy，这与本项目复合policy边界一致。

## 6. 代码、权重、数据、依赖分别计

| 对象 | 本轮确认 | 仍缺/不能推断 |
|---|---|---|
| FluxVLA代码、FluxDAgger代码 | 两仓LICENSE均Apache-2.0，S1的FluxDAgger许可未知已补齐 | 非所有衍生模型/数据自动Apache |
| FluxVLA训练权重 | 官方HF [FluxVLAEngine](https://huggingface.co/limxdynamics/FluxVLAEngine)可访问，列基座与任务checkpoint；模型卡明确第三方权重仍受各自许可 | 未下载/验证指定ARM奖励权重和本项目单臂双向权重；不能把普通LIBERO权重当ARM/DAgger在线链完成 |
| FluxVLA数据 | 官方 [FluxVLAData](https://huggingface.co/datasets/limxdynamics/FluxVLAData)卡标Apache-2.0；ARM工具README指向10-episode带progress示例 | 未下载数据，也未独立核每个来源子集的授权和标签质量；不是本项目示范或完整真实TD replay |
| FluxDAgger依赖 | README给Ubuntu20.04/ROS Noetic/Python3.10、Piper SDK、CAN/相机；Qwen奖励须本地GPU/checkpoint | ROS/驱动/外部policy/reward资产非本仓全锁；默认路径含ACT历史项不代表本项目采用ACT |
| FutureRTC代码 | 三实现分支LICENSE为MIT；realworld有独立vendored OpenPI LICENSE/GEMMA文件路径 | 不把MIT覆盖OpenPI/模型或Piper SDK；未全核这些依赖的锁文件内容 |
| FutureRTC权重/数据 | LIBERO树有predictor_pi05.pt、predictor_smolvla.pt、corrector.pt；Kinetix树有12 predictor；不下载。realworld树没有这些模型/数据文件，README需要自行提供policy/predictor/data路径 | 仿真模型文件名存在不代表可复现真机；真实任务基座、预测器和数据未随已核分支交付 |
| FutureRTC环境/维护 | 真机JAX/Flax policy＋PyTorch predictor共用GPU，train/infer两份契约须手动同步；Kinetix外部RTC repo/bc31 | predictor与新RL policy的表示兼容性、持续更新成本及实机deadline未测 |
| ForceRFT | 固定论文v1正文、公式和边界 | 官方训练代码、权重、数据、代码/权重许可仍未查明；本轮不强找不存在证据的全树 |

社区页面仅作状态交叉检查：[FutureRTC issue #1](https://github.com/JianghaiSCU/FutureRTC/issues/1)的代码发布询问仍在缓存页面，不能推翻当前实际分支存在；FluxDAgger issues页只取到demo条目，没有独立复现结论。没有用stars或不同任务成功率排算法名次。

## 7. 和旧RAPolicy／RT-EXPO的责任对照

旧固定源与细读记录继承自 [04研究§11](../../../04_RL与Harness扩展调研_20260923/research/01_VLA_RL扩展调研.md)，本轮不伪装重复全树审计：RAPolicy `ef4b1044f0cc78c0f6143180a2d78ae267ab03ea`，RT-EXPO `803381fc3b4c91a0c47904f1b688fc5e35904f50`。

| 候选 | 对部署policy的学习贡献 | 连续时序责任/本轮结论 |
|---|---|---|
| RAPolicy | replay Q/V＋优势加权原生flow；失败参与价值学习，可靠行为覆盖仍必要 | 固定chunk推理hold，非当前连续队列；actor/Q/V共同加goal/C及真实时长是适配工作；仍优先原生预检 |
| RT-EXPO | Q筛选/快速编辑＋原生RTC-BC；完整部署包包含editor/Q | 已有实时pending/history与接管清理证据，候选/编辑支持及成功BC门槛仍需测；保留实时优先候选 |
| Flux/ARM | 可直接训练原生flow的加权BC桥 | 本轮未见在线TD；先修采集资格，不能挤掉上述RL候选 |
| FutureRTC | 学习预测输入后由冻结VLA行动 | 可改善整个policy，但真机例程窗口尾等待、无代际接管；作为延迟消融，不替换RL/队列 |
| ForceRFT | 腕力条件残差＋自主TD＋人工BC | 有清楚论文时序/归因选择；不同状态/动作/目标、硬件与资产不足使其暂为方法参考 |

资源有限时不同时移植全部S1候选：ProphRL/世界模型分支须先有额外模型与奖励校准预算；FineVLA/LeHome留作标签或采集结构参考；Prism-GRPO留作全失败信号反例；本轮没有新资产证明它们应抢在真实记录与双向RL之前。此为预算决策，不是其方法已被否定。

## 8. 给S3的联合反证与最小决策门槛

| 编号 | 可构造输入/事件 | 应观察什么，失败时如何改取舍 |
|---|---|---|
| RL-C01 | 全关键帧interval=0、success=False，含多个关键帧 | ARM重建回退不能当真实进展；保留GT/独立成功判定，拒绝未经校准的主奖励接入 |
| RL-C02 | human切换时让模型继续发布，再让模型停止发布 | 记录的owner、提案、SDK接受量和BC标签必须一致；否则Flux采集仅作参考，先建独立gateway账本 |
| RL-C03 | collector积压100帧后切mode；一侧command暂时停更 | 不把旧观测改标human、不把缺测填零当动作；应按事件时间归属并标unknown |
| RL-C04 | 预测承诺10步，中途强制接管/改夹爪/限位 | predictor输入必须对应实际有效承诺；失效预测不得进入执行或作为真实未来监督 |
| RL-C05 | FutureRTC结果晚于窗口；旧请求跨reset后到达 | 连续执行与deadline要有定义，epoch拒收；不能单靠`get(timeout=50)`或清z_init |
| RL-C06 | 同图像/状态下A→B与B→A，切goal时旧结果在途 | 同一θ及所有learned组件必须显式条件化/绑定goal版本；server启动固定prompt不合格 |
| RL-C07 | 同状态被“安全风险”“评分未知”“主动观察”三种原因接管 | 不统一赋失败/terminal；比较ForceRFT片段目标与保留前驱方案，记录删失偏差和有效TD密度 |
| RL-C08 | 救场使系统成功，而关闭GPT后policy仍失败 | 固定完整policy包独立评估，保留必要editor/predictor；辅助成功不能代替双向policy收益 |
| RL-C09 | policy完成一次RL更新但predictor沿用旧latent bank/统计量 | 对同一输入审计表示/动作分布；若预测误差与闭环增益退化，先停用predictor或重训，不让其拖慢主RL |
| RL-C10 | base从不张爪或张爪过早，TCP残差却很准确 | ForceRFT/受限编辑动作支持诊断；若必要动作不可达，转原生头或完整头，不靠继续采样掩盖支持缺口 |

门槛顺序建议：**真实采集与控制代际 → 同θ双向BC/动作覆盖 → 各learner独立时间协议与合法TD → 等真机/纠正预算比较 → 必要时预测补偿消融**。不把运行时问题都归为算法差，也不靠Harness长期救场绕过policy独立能力。以上都是待实现/待实测的验收设计，S2源码核查不是验收已通过。
