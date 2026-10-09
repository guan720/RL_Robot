# 教师建议能否长期进入 RL buffer：ConRFT / HIL-SERL / EXPO 源码核查

核查时间：2026-09-22。只读既有快照及官方固定源码，没有安装依赖、运行训练或操作机器人。本文区分“方法上可行”“当前代码实际支持”“需新增的训练路径”。

固定版本：

| 仓库 | 审核 SHA | 核查方式 |
|---|---|---|
| ConRFT | `a779fde7fa5db5a469960a8490c100f35b41b49e` | 读取 02 目录已有源码快照 |
| HIL-SERL | `c32939bccb65f3b8c43a9f9add3d322d4ab0264a` | GitHub commits/main API 取得 SHA，再读该版本官方文件 |
| EXPO-FT | `803381fc3b4c91a0c47904f1b688fc5e35904f50` | 固定官方源码；OpenPI 依赖另需锁定，不把主库 SHA 当整环境锁定 |

## 1. 直接结论

**用户提出的“未执行教师建议也能长期放在数据 buffer 中补充 RL”在方法上成立，不能简单否定。** 它可以长期作为专家动作监督，参与 RL 系统中的 BC/flow-matching 辅助目标、DAgger 更新或其它明确设计的监督目标，不要求每条建议先在真机执行。

但三种实现的 **demo buffer 不能都理解成任意 `(s,a_teacher)` 的专家标签库**：

- ConRFT 原版 demo buffer 和在线 buffer 都是 transition replay；同一混合 batch 进入 critic 和 actor 的 BC+Q。
- HIL-SERL 的原版 demo 数据通过 critic 学习其动作后果，已审 SAC 与单臂 hybrid actor **没有显式模仿 demo 动作的 BC 项**。
- EXPO 的 base 本来就有原生监督训练入口，因此接独立教师标签池很自然；但其默认在线数据入口仍从 transition replay 构造 actor batch，且 success-only 不会自动接受任意未执行建议。

正确实现是让**实际转移与教师标签拥有不同的有效字段和训练资格**。物理上可用两个库，也可同一底层存储加类型字段和独立 sampler；关键不是文件数量，而是禁止无后果标签误入 TD 目标。

## 2. 三类“当前没有执行”的数据，需要分别判断

| 数据类别 | 已知什么 | 能否直接进入真实 TD replay | 可长期用于什么 |
|---|---|---|---|
| ① 历史遥操作/脚本轨迹；本轮没有再执行 | 当时的真实 obs、执行动作、真实后继、奖励/终止 | 可以，在任务/动作/奖励语义兼容时进行 off-policy 学习 | critic、适用的 BC/SFT、数据复用 |
| ② 当前或历史状态上的未执行教师建议 | obs、目标、教师动作/片段及其质量依据；没有该动作的真实后果 | 不可直接冒充真实 transition | 专家动作库、DAgger/SFT、RL 的辅助模仿目标；其它监督目标需明确设计 |
| ③ 世界模型生成的想象转移 | 模型预测的后继与奖励，不是真实后果 | 不能不加区分地当成真实数据 | 经过动力学验证、风险控制与单独采样设计的 model-based RL；三者默认没有因此自动获得该能力 |

**不是“旧数据不能用于 RL”，也不是“未执行动作对 RL 完全无用”。** 限制的是数据的因果语义与当前损失函数是否实际消费它。

例：在状态 s，学生执行向左得到 s_left；教师建议向右但未执行。可以存真实 `(s,left,r,s_left)`，另存标签 `(s,right)`。不能把动作替换成 right，却沿用 s_left 和原奖励训练 Bellman target。把 `done=1` 或 `mask=0` 填上也不能自动补足未知结果；那只是在伪造另一种任务语义。

## 3. ConRFT：已有 BC 通路，但原版 demo 库是完整转移库

### 3.1 数据入口

`examples/train_conrft_octo.py::actor` 先调用 `env.step(actions)`；若环境返回 `intervene_action`，再把记录动作覆盖为**实际接管动作**。构造字段包括：

`observations, actions, next_observations, rewards, masks, dones, intervened, embeddings`。

回合结束追加 MC returns 与 next embeddings；所有记录进入在线库，仅接管记录另入 demo 库。这是在记录真实执行，不是把未执行教师建议直接换进历史转移。[actor，L186–235](https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/train_conrft_octo.py#L186)

`ReplayBuffer.__init__` 为 obs/next_obs/action/reward/mask/done 分配数组，可选 embedding/next_embedding/MC return；`_insert_recursively` 按已分配字段读取输入，纯 `(s,a)` 并不满足这个插入契约。[ReplayBuffer，L26–104](https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/data/replay_buffer.py#L26)

### 3.2 长期保留、采样和更新

| 路径 | 固定代码事实 | 对本次问题的含义 |
|---|---|---|
| 初始导入 | `main` 从 demo pkl 逐条插入 `demo_buffer`，L557–574 | 历史真实遥操作不必重新执行，可直接用于之后学习 |
| 在线采样 | `learner` L390–434：demo 与 online 各半，拼成一个 batch | 50:50 是两个池的比例；随着新接管加入，不能理解成永远 50% 是最初几条 demo |
| critic | `critic_loss_fn` L235–285 使用 reward、mask、next_obs/next_embedding 和实际 action 形成 TD 误差 | 缺失或错配后果不能进这条损失 |
| actor | `policy_loss_fn` L310–365：consistency 重建监督实际 batch action，同时用 Q 优化新动作 | 有可复用的教师动作监督机制，但默认与 transition batch 耦合 |
| 存档/恢复 | actor 周期写 buffer/demo_buffer pkl；main 重新读取 | 有磁盘长期存档能力，不等于内存无限保留 |
| 容量 | `ReplayBuffer.insert` 插入指针按 capacity 取模 | demo 库也会环形覆盖；初始示范若需保护，要明确保留策略 |

来源：[learner 与导入](https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/examples/train_conrft_octo.py#L390)、[critic/actor 损失](https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/agents/continuous/conrft_single_octo_cp.py#L235)、[环形插入](https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/data/replay_buffer.py#L103)。

### 3.3 如何接纯教师建议

可把现有 actor 的 BC 部分改为从独立 `teacher_action_batch` 读取 obs/task/embedding/action/validity/quality，真实 TD batch 仍供 critic 和 Q 引导项使用。数学上 BC 不需要教师动作的后继或奖励；当前函数用 `batch["rewards"].shape[0]` 获取 batch size 只是代码耦合，可改为从 action/obs 获取。

这属于**新增 actor 数据入口与采样契约**，可复用原损失结构，并非另造整套 RL；但不能声称原版 demo_buffer 已原生接受纯标签。不得为了复用接口填假 `next_obs/reward/done` 后让同一 batch 再进入 critic。

此前发现的间断接管点与 memory-efficient 图像历史拼接风险仍需检查。纯标签库应保存完整观测/历史，不能用不连续建议在数组中的相邻位置拼出伪时间序列。[图像回放](https://github.com/cccedric/conrft/blob/a779fde7fa5db5a469960a8490c100f35b41b49e/serl_launcher/serl_launcher/data/memory_efficient_replay_buffer.py#L61)

## 4. HIL-SERL：demo 主要通过价值学习起作用，原版 actor 没有 BC

### 4.1 入口和 replay

`examples/train_rlpd.py::actor` L156–185 在 `env.step` 后保存真实 `next_obs/reward/done`，用 `intervene_action` 修正记录动作；全量进入在线库，实际接管再进入 demo 库。`main` L410–447 读取历史 demo 和存档；`learner` L261–304 对 demo/online 各半采样。[固定训练入口](https://github.com/rail-berkeley/hil-serl/blob/c32939bccb65f3b8c43a9f9add3d322d4ab0264a/examples/train_rlpd.py#L156)

`ReplayBuffer` 存完整 transition 字段并环形覆盖；其字段要求和“有存档但非永久 pin 住初始样本”的结论与上节相同。[固定 ReplayBuffer](https://github.com/rail-berkeley/hil-serl/blob/c32939bccb65f3b8c43a9f9add3d322d4ab0264a/serl_launcher/serl_launcher/data/replay_buffer.py#L32)

### 4.2 直接点读 loss 的发现

`SACAgent.policy_loss_fn` 从当前策略在 batch observation 上重新采样动作，优化 `Q(s,a_pi) - alpha*log_pi(a_pi|s)`；没有比较 `a_pi` 与 replay 教师动作的模仿项。其 critic 才用 replay 中真实动作与真实后果学习。[sac.py，L137–216](https://github.com/rail-berkeley/hil-serl/blob/c32939bccb65f3b8c43a9f9add3d322d4ab0264a/serl_launcher/serl_launcher/agents/continuous/sac.py#L137)

单臂可学习夹爪的 `SACAgentHybridSingleArm.policy_loss_fn` 也是 Q/熵目标；夹爪动作另用于 `grasp_critic_loss_fn` 的 DQN 式 TD 更新，同样需要奖励与后继。[hybrid single，L157–293](https://github.com/rail-berkeley/hil-serl/blob/c32939bccb65f3b8c43a9f9add3d322d4ab0264a/serl_launcher/serl_launcher/agents/continuous/sac_hybrid_single.py#L157)

**结论：**在已审默认 SAC 与单臂 hybrid 路径里，纯 `(s,a_teacher)` 即使能被保存，也没有自动把 teacher action 用作监督标签的 actor loss。要利用未执行建议，需要新增 BC/偏好等辅助目标，且 VLA 还需独立模型适配。不能因为它叫 demo buffer，就把 HIL-SERL 描述为原生 DAgger/BC+RL。

历史真实 demo 当然仍有作用：它们给 critic 提供有信息的实际动作后果，并让 actor 在相应状态上按价值改进。没有 BC 不代表不使用示范。

## 5. EXPO-FT：监督入口最直接，但默认数据管线仍基于真实序列

### 5.1 actor 和 critic 已分开，但 actor batch 仍来自 transition replay

`BatchProcessor.__init__/next_batch/_sample_success_actor_batch`：

- `offline_ratio=0`：初始 demo 注入在线 replay；长期可能被覆盖。
- `offline_ratio>0`：可以独立保留 offline replay；critic 按配置混合，base actor 可混合两边成功数据，在线成功不足时退回 offline 成功数据。
- `actor_success_only=True`：单独采 actor batch；不是每个 actor 更新都必须与 critic 同一批。
- `use_dagger_hil_sampling` 是 RTC/DAgger 分支，不能误说 EXPO 默认已用所有 HIL 标签。

[固定 BatchProcessor](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/batch_processor.py#L15)

这不是固定 50:50 配方。具体比例要报告实际 `offline_ratio`；独立 offline 库若不继续写入，能减少初始 demo 被在线数据覆盖的风险，但仍受容量、导入规模和恢复流程限制。

### 5.2 特别容易误判：insert 不直接读 next_obs，也不是允许无后果标签

`PiReplayBuffer.insert` L282–318 读取 `observations/actions/rewards/masks/dones`，逐步回填动作 chunk；`sample_jax` L405 起再从**后续顺序记录**构造 next observation，并累计 n-step 奖励。因此它不是每条记录显式携带 `next_observations`，而是依赖真实时间顺序隐式提供后果。[固定 replay](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/data/replay_buffer.py#L282)

将孤立教师建议插进这个序列，会把之后另一条记录当成其物理后继，并回填混合 chunk。即使通过填假 reward/done 让 schema 通过，也不代表数据语义正确。

`insert_dataset` L320–327 默认将导入数据设为 `is_hil=True/is_success=True`。这是历史成功示范入口的约定，**不是代码验证了任意输入建议成功**。不能利用默认值把未执行建议洗成成功 transition。

### 5.3 纯教师动作可接到哪里

- `expo_ft.py::update_actor` L665–686 调 `actor.prepare_batch_for_actor` 后执行 base train_step。
- `Pi05Agent.prepare_batch_for_actor` L530–534 只需构造 observation 和 `full_actions`。
- `pi05.py::train_step` L141–194 调模型监督 `compute_loss(observation,actions)`，本身不需要该教师动作的 reward/next_obs。
- 相比之下，`update_critic` L702–786 明确需要实际动作、next_obs、累计 reward、mask/valids 构造 TD。
- 当前 `_update_jit` 即使使用专用 actor batch，L841 仍先经过 `prepare_critic_batch`，所以**现成顶层接口还要求不必要的 next 字段**；要抽出纯 actor batch 转换路径，而不是虚构后继。

[actor/critic/update 调度](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/expo_ft.py#L665)、[VLA train_step](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/vla/pi05.py#L141)、[actor batch 入口](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/vla/pi05.py#L530)、[batch 字段变换](https://github.com/pd-perry/expo-ft/blob/803381fc3b4c91a0c47904f1b688fc5e35904f50/expo_ft/agents/alg/batch_utils.py#L16)

**建议改造：**保留真实 replay 专供 Q/edit 与成功经验；另采可信 teacher labels 到 base 监督更新。教师标签无需标成 episode success。只有单步建议时增加有效动作 mask 或构造真正受支持的部分动作监督，不能把该动作复制成完整 H 步当答案。完整可信 teacher chunk 则按已有动作坐标和归一化输入。

这改变的是监督数据来源、采样及 batch 管线，并非改成“Q 直接穿过整个 VLA”。它可与真实 RL 并行构成复合训练。

## 6. 建议的长期数据结构与损失路由

| 逻辑库 | 最少信息 | 允许的训练路径 | 不允许自动推断的字段 |
|---|---|---|---|
| 真实交互库 | obs、实际 action、真实后继或连续序列、reward、终止/截断、goal、来源/版本 | TD critic、适用的监督、策略评价 | 不能把反事实教师动作替换真实 action |
| 教师动作库 | obs/必要历史、goal、teacher action/chunk、有效 mask、质量/来源/版本、是否执行 | VLA SFT/BC、DAgger；经设计的动作偏好/约束 | 不填“默认成功”、虚构 reward 或 next_obs |
| 想象经验库（首版可不做） | 模型预测后果、动力学模型/奖励模型版本、不确定性与生成范围 | 另行设计的 model-based 更新 | 不自动获得真实 transition 的可信度 |

可将 actor 总目标设计成：

`L_actor = L_RL(real_replay) + lambda_teacher * L_supervised(teacher_labels)`。

这是概念表达：ConRFT 的 Q+consistency BC 可按此分源；EXPO 的 base FM 和 edit RL 是不同网络的目标，不能误写成同一个 actor 梯度；HIL-SERL 要新增监督损失与模型接口。

长期保留建议应实行：

1. 原始初始示范与高价值纠正持久化，不依赖 GPU/内存环形 replay 保存全部历史。
2. 独立采样份额保护初始技能，同时按场景覆盖、难度、质量、时间和 teacher 版本控制新标签比例。
3. 教师升级或奖励/坐标语义改变后，对旧标签重新验证或失效；“长期保留”不意味着永久等权使用。
4. 保留实际物理动作和原始观测；归一化/encoder 缓存变化时可重算，避免训练到不一致表征。
5. 记录是否执行及证据；未执行建议可以有效，但必须有可信 teacher 或验证依据，不因进入库就自动成为 expert。

已有真实状态也可只作为 actor 更新时的状态样本。未执行建议还可用于 candidate scoring/有依据的排序约束；这些并非 Bellman 后果监督。不能通过 critic 对建议打高分，再把自身高分当成建议正确的独立证据。

## 7. 对 ConRFT / EXPO / HIL-SERL 排序的实际影响

**应修正此前过于偏向完整成功供给的 EXPO 门槛。** 若 Harness 能提供大量可信、与学生输入/动作相容的 shadow 标签，即便没有频繁完整成功，EXPO 的 base 也有直接可复用的监督更新机制；补上独立 teacher-label sampler 后，不必等待其原版 success-only 池增长。此条件下，现有 π 系链路成熟会进一步提高 EXPO 作为整体框架的吸引力。

**ConRFT 仍可行，但不因“有 demo buffer”就天然比 EXPO 更能利用未执行建议。** 它有完整动作头与 BC 机制优势，同时需要把 BC 从完整 transition batch 中分离；若必须迁到 Octo，迁移成本仍需计入。

**HIL-SERL 不应凭 demo buffer 名字获得同等适配评价。** 原版没有这一类 actor 模仿目标，VLA-only 条件又需要新模型适配；适合作真机基础设施/价值学习参考，不是本轮未执行教师标签的最直接承载方案。

最终建议：先跑通 **可信教师动作库 + 原生 VLA DAgger/SFT**；再让真实交互库驱动 EXPO/ConRFT 的 RL 更新，测量其相对同预算交互模仿的增益。若无法保证 teacher 动作质量，长期保留只会长期放大错误，需先改善筛选与反馈，不能期待换一个 buffer 名称解决。

## 8. 实施前的最小代码验收

以下是待实现方案的必要验证项，不是本轮已运行结果：

- 插入仅有教师标签的样本后，确认它能被 actor sampler 读取，而 critic sampler 永远不读取其不存在的后果。
- 造一个学生向左、教师向右的可追踪样本，确认真实 next_obs 只与真实 action 配对。
- 单步教师建议的 action mask 确实影响监督 loss，不能由 padding 尾部贡献伪梯度。
- 一次 teacher-only 更新能改变计划训练的 actor 参数，但不会对 critic 产生伪 TD 更新；EXPO 还要刷新推理缓存。
- buffer 环回与重启后检查初始示范保护、质量标记、success 标记与 goal 不变。
- 在历史真实 demo、当前未执行建议、实际自动接管三种输入上分别回放，核对动作、图像历史、时间戳、chunk 与 loss 路由。

**本轮未实现上述改造，因此只能确认其代码落点与所需修改，不能宣称已经跑通。**
