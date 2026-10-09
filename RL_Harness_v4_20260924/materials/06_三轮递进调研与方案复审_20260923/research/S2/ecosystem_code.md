# S2 生态源码链：发布到真实动作之间的证据

核查日期：2026-09-23。仅作官方文本、源码和资产元数据静态核查；不执行上游代码，不下载权重，不安装或训练。先阅读会话 AGENTS、06 契约、S1 根审总结、S1 生态报告及科学家只读入口。

## 1. 从 S1 剩余缺口先列本轮问题

1. LeRobot v0.6.1、#4452、#4454 和当前固定 main 的真实文件/函数分别是什么？已合并修复是否进入冻结对象，最终 diff 是否与旧 #4122 相反？
2. #4398 尚未合并时，当前 main 是否在其他路径完成 reset→新观测→resume？若未完成，旧观测怎样进入首个恢复 chunk？
3. OpenPI #958 报告针对哪个转换脚本版本、#960 实际在哪个 head 提供何种合并？训练 checkpoint→模型转换→normalizer→服务加载的链上有哪些不会被“可加载”自动检查的条件？
4. 如何将这些证据转成独立 policy 发布/评测条件，而不把运行系统救场计成策略收益？
5. 若 P0 链足够清楚，再核具体 GR00T 权重 LICENSE/revision 和 Dexbotic→RLinf registry 是否新增设计约束；不重复生态摘要。

## 2. 新结论先行与冻结对象

相对 S1，本轮改变了四个判断：**LeRobot 当前源码已以另一种方式覆盖 #4398 的旧观测恢复问题；RTC 的消费计数仍不是驱动物理生效回执；OpenPI 所查当前转换器与 #958 报告版本逐字节相同，尚不合并 LoRA；GR00T 具体权重仓的 LICENSE 比模型卡声明更严格且互相冲突。** 这些结果决定版本、接口和发布检查，不能当作独立 policy 已提高成功率。

| 对象 | 完整固定版本 | 访问时状态／证据 |
|---|---|---|
| LeRobot v0.6.1 | `7e241bd630a3719a56157a497ce5d08f244784f1` | GitHub tag 对应提交；8 月 release，不含以下 9 月合并补丁 |
| LeRobot 所查 main | `bed246ed34b0cb6ee1abbfd3285eed94cf8767bc` | API 于 2026-09-23 13:36 UTC 返回；随后均按 SHA 读取 |
| LeRobot #4452 | merge `0120909ed1e1df860217fefa78755015b0315744`；最终 head `22a9e6a3cfc7140b8d606f70c40156e16798d96c` | `merged=true`，2026-09-22 09:55:09 UTC |
| LeRobot #4454 | merge `7af6936589215ea0d2457de43530bc6322c7cea6`；head `c743a6fc4a2dabbdf87d331fe3d2ac40caf6e6e8` | `merged=true`，2026-09-22 10:19:45 UTC |
| LeRobot #4398 | head `ef5d517c1cee046ae1fdd907abbf431c49d3220e` | `state=open, merged=false`；所提策略层补丁未合并，不代表引擎没有同义修复 |
| LeRobot #4122 | head `6399803b660c34190bc08c4e437411fe401e2d20` | `state=closed, merged=false`，被替代，不是已合并 |
| OpenPI #958 所报版本 | `c23745b5ad24e98f66967ea795a07b2588ed6c79` | 报告者指定版本，issue 仍 open |
| OpenPI 所查 main | `215abfb217dbac7d5f1273282331b9b1866c0479` | 当前转换脚本与上述版本 SHA256 同为 `62980fda1a1b1a09167d413232a2a9295db8370e52b58a70cfba52ef5d88c440` |
| OpenPI #960 | head `46fe49901bfee3b6d8c768a755e86699d5006b48`；base 为上述 c23745b… | `state=open, merged=false`；读取最终 head 源码及 PR diff |
| GR00T-N1.7-3B 权重仓 | `2fc962b973bccdd5d8ce4f67cc63b264d6886495` | 由 HF 文件树的 commit 链固定；读该 revision 的 LICENSE，不下载模型 |

官方状态入口：[LeRobot #4452](https://github.com/huggingface/lerobot/pull/4452)、[#4454](https://github.com/huggingface/lerobot/pull/4454)、[#4398](https://github.com/huggingface/lerobot/pull/4398)、[#4122](https://github.com/huggingface/lerobot/pull/4122)、[OpenPI #958](https://github.com/Physical-Intelligence/openpi/issues/958)、[#960](https://github.com/Physical-Intelligence/openpi/pull/960)。API JSON 与 diff 均在自有证据目录。特别注意：两个 open PR 的 API 也返回非空 `merge_commit_sha`，这是待合并测试对象等 API 语义下可能存在的值，**不能据该字段非空宣称合并**；这里同时核 `merged`、`merged_at` 和网页状态。

## 3. LeRobot：源码中的动作、队列与恢复链

### 3.1 #4452 最终实现与旧提案并不相同

人类可读链为：checkpoint 的动作名称顺序 → `build_rollout_context()` 对动作／观测标量特征排序 → `build_dataset_frame()` 构建状态向量 → preprocessor → policy → postprocessor → `SyncInferenceEngine.get_action()` 或 RTC 出队 → `send_next_action()` 按同一名称序列把张量转成命令字典 → robot action processor → 驱动。

实际核过的最终 diff 与固定 main 有以下变化：

- `rollout/context.py::_align_to_checkpoint_order` 是最终合并后的统一函数名；S1 所读 PR 说明中的两个单独 alignment helper 已被重构。它只在标量名称集合相同而次序不同的情况下重排；额外速度通道／不同动作集合不会被强行按另一集合重排。
- 同文件 `_assert_state_matches_action_order` 拒绝“同集合、不同顺序”的 state/action 排列；不同集合可合法通过。因此它不是普适本体 schema 验证器，坐标、单位、通道含义仍须 adapter 验证。
- `inference/sync.py::get_action` 直接返回 policy 维度顺序，删除 v0.6.1 中 `make_robot_action` 后重新索引的往返。RTC 改用处理后的 `dataset_features` 构建观测，避免注入非恒等 observation processor 后与同步路径分离。

固定源码：[context.py](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/context.py#L142)、[sync.py](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/inference/sync.py#L86)、[v0.6.1 同步路径](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/rollout/inference/sync.py)、[#4452 最终 diff](https://github.com/huggingface/lerobot/pull/4452/files)。

上游新测试把双臂硬件顺序与 checkpoint 顺序故意反转，区分“哪个关节的观测锚点”和“哪个 policy 输出维度”，并对历史错误接线作参数化反例；这比仅看张量 shape 或夹爪能开合更有识别力。PR 中 857 passed／14 skipped 及 OpenArm 真机确认均为上游报告，本轮只读了 diff，未运行。旧 #4122 把 RTC 改成同步重排方向的提案不可直接照搬。

### 3.2 #4454 解决的是三个明确的 RTC 边界

| 函数／触发 | v0.6.1／旧路径 | 固定 main／最终 #4454 |
|---|---|---|
| `ActionQueue._check_and_resolve_delays`，空队列或推理期间取出很少动作 | 不一致时仍按测量延迟丢掉完整前缀 | 按 `min(real_delay, indexes_diff)` 限制丢弃，避免新 chunk 无根据地前跳 |
| `_normalize_prev_actions_length`，前缀短于执行窗口 | 补零 | 用最后一条已有动作补齐；空前缀直接调用会报错，循环识别空 tensor 后改走 `None` 无前缀路径 |
| `_rtc_loop` 首次推理且不开 compile | 首次延迟进入 tracker | 至少首轮从 tracker 排除；保留 compile warmup 与 trained RTC 的额外条件 |

证据：[action_queue.py](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/policies/rtc/action_queue.py#L252)、[当前 rtc.py](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/inference/rtc.py#L93)、[v0.6.1 rtc.py](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/rollout/inference/rtc.py)、[#4454 diff](https://github.com/huggingface/lerobot/pull/4454/files)。归一化动作零值可能代表数据均值，不能把补零解释为物理保持。

**本项目仍必须补物理执行事实。** `indexes_diff` 来自 `get_with_task()` 递增的 `last_index`，严格说是队列取出数量。`send_next_action()` 随后才经过插值、`robot_action_processor`、`robot_wrapper.send_action`；它返回处理前 `action_dict`，该函数也没有消费 driver 的回执。因而 clamp 修复不能证明“取出的每条动作已等时、等值作用到机器人”。特别是插值倍数大于 1、限幅、发送拒绝或中断时，RL transition 必须连接实际下发／确认／观测区间，不能直接拿 queue 索引当环境步。[队列取出](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/policies/rtc/action_queue.py#L80)、[发送链](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/strategies/core.py#L329)。这是代码语义判断，不是已观测的硬件故障。

### 3.3 #4398 未合并，但当前 main 已存在引擎级同义修复

PR head 在 `DAggerStrategy._apply_transition()` 添加 reset 后、resume 前重新读机器人并 notify 的步骤。当前 main 的该策略分支依然是 interpolator reset → engine reset → resume，**并没有合并这份策略层补丁**。但实际引擎已经改变：

1. `RTCInferenceEngine.reset()` 重置 policy／processor 后，在 `_obs_lock` 临界区清队列、把 `_obs_holder['obs']` 置空并递增 `_reset_epoch`。
2. `_rtc_loop()` 同时读取观测和 epoch；没有观测就等待，不能重新取出接管前的 holder 内容。
3. 预测结束后，在同一锁内检查 epoch 再 merge；reset 在推理期间发生时，旧结果不再进入新队列。清除与检查合并两边都按 observation lock → queue lock 顺序进行。
4. 策略返回自主状态时重置 interpolator，使下一控制 tick 的 `_process_observation_and_notify()` 刷新缓存并发布新的处理后观测。

固定源码：[恢复分支](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/strategies/dagger.py#L751)、[引擎 reset](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/inference/rtc.py#L325)、[loop 的检查与合并](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/inference/rtc.py#L421)、[观测缓存刷新](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/src/lerobot/rollout/strategies/core.py#L111)。

因此旧 holder 导致恢复首块回到接管前状态的因果路径，在所查当前实现已经被切断；另外也保护了跨 reset 的在途 chunk。这个结论限于静态代码机制，不是全部接管时序／所有 policy 状态均已验证。`pause()` 仅清 Event，不是等待推理线程静止的屏障；policy／processor 的 reset 是否对每种有状态模型都可与在途 forward 安全并行，仍需定向验证。

版本证据进一步收紧：#4454 merge SHA 的 `rtc.py` 与本次 main 的该文件 SHA256 **相同**（`32eff14e99f4adc54de1d9bb3f4d4bea97ee696d57c7c9b08d8b449e9b738b34`），说明该同义机制至少已在 9 月 22 日这个合并快照中；#4454 的最终 diff 不含该 reset 改动，不能把修复归功于 #4454 本身。v0.6.1 的 `reset()` 只清 policy／processors／queue，没有 holder 清空与 epoch 检查。本轮未定位首次引入该 reset 机制的独立 commit，不能臆造归属。

### 3.4 资产与依赖边界

LeRobot 是这里的运行／数据组件；没有由这些 PR 获得本任务的 SFT、RL、critic 或奖励权重，亦未得到少示范双向任务的数据包。所查 `pyproject.toml` 声明 Python ≥3.12、torch ≥2.7 且 <2.12，`transformers-dep` 额外组为 ≥5.4 且 <5.6；代码 LICENSE 为 Apache-2.0，包含的第三方资产仍须单独核。[固定 pyproject](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/pyproject.toml)、[LICENSE](https://github.com/huggingface/lerobot/blob/bed246ed34b0cb6ee1abbfd3285eed94cf8767bc/LICENSE)。本轮没有运行依赖解析器，声明范围不等于锁定环境已安装兼容。

## 4. OpenPI：训练增量如何真正到达服务 policy

### 4.1 读取的调用链

```text
training/checkpoints.save_state
  → _split_params：有 EMA 时选 EMA，否则训练参数
  → 同一个 checkpoint step 保存 params、train_state、assets/asset_id 下的 norm stats
  → converter.main(config_name)
  → slice_initial_orbax_checkpoint(checkpoint_dir/params，恢复为 FP32)
  → PaliGemma / action expert 切片与投影映射
  → PI0Pytorch(model_config) → load_state_dict(strict=False)
  → 保存 model.safetensors、参考 config.json；有条件复制 assets
  → create_trained_policy(train_config, checkpoint_dir)
  → 由是否存在 model.safetensors 选择 PyTorch / JAX 路径
  → load_pytorch + 默认 BF16 转换 / JAX BF16 restore
  → 配置生成 transforms，加载 checkpoint/assets/asset_id
  → Policy.infer：输入 transforms → sample_actions → 反归一化／动作变换
```

固定入口：[checkpoint 保存](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/training/checkpoints.py#L68)、[转换器](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/examples/convert_jax_model_to_pytorch.py#L422)、[服务工厂](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/policies/policy_config.py#L16)、[Policy.infer](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/policies/policy.py#L69)。

### 4.2 当前脚本仍缺 LoRA merge，#960 是候选修复

**报告者现象：**#958 在 c23745b…、Ubuntu 24.04、JAX 与 PyTorch 对照中报告 20 个 LoRA unexpected keys 被忽略，并给出逐步改进数值。那些数值与“可能解释 #840／#729／#810”的关系属于报告者证据，不能外推成我们复现，亦不能证明这些 issue 的共同根因均已查明。

**本轮直接代码证据：**c23745b… 与 215abfb… 的转换器逐字节相同；源码没有 LoRA merge，`load_state_dict` 使用非严格模式且不检查返回值。切片映射保留未消费项时，LoRA 张量不会因此自动写入普通 PyTorch 权重。这足以否定“当前官方脚本必然保留 LoRA 训练增量”的发布假设，但没有亲自装载具体 checkpoint，故不声明本轮验证了上述 20 项或数值误差。

**#960 实际 head：**在切片前按 config 检测 adapter 并调用 `merge_lora_into_base()`；模型变体从 config 获取；先用目标 dtype 初始化模型再 load；默认 LoRA 输出为 FP32；仅当 `unexpected_keys` 中仍有包含 `lora` 的键时抛错。它没有通用拒绝所有 missing keys／其他 unexpected keys，因此不能把这个补丁视为完整发布验收。[固定 PR 源码](https://github.com/Physical-Intelligence/openpi/blob/46fe49901bfee3b6d8c768a755e86699d5006b48/examples/convert_jax_model_to_pytorch.py#L163)。

对 merge 公式，本轮还读取了 [lora.py](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/models/lora.py) 与 [gemma.Attention](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/models/gemma.py#L238)：输出投影的 LoRA 两步 einsum 会在第二步对 head 维求和，候选补丁使用相应跨 head 合并；MLP `_dot` 不乘 alpha/rank，而 `Einsum` 乘配置缩放。不能对所有层照搬同一标准 LoRA 公式。这里确认代码语义与补丁意图吻合，没有运行数值等价测试。

### 4.3 比“能加载”更强的四个发布条件

| 条件 | 本轮新增静态证据 | 对当前设计的要求 |
|---|---|---|
| 参数与配置一致 | converter 的 `config.json` 只是参考；服务用传入的 `TrainConfig` 构造模型，并不由该 JSON 还原完整训练配置 | 发布 manifest 固定 model variant、pi0/pi05、action horizon/dim、训练 config、checkpoint step、EMA/raw、adapter 合并方式及参数清单；完整 missing/unexpected allowlist 必须可审查 |
| normalizer 与变换一致 | `save_state` 把 norm stats 与参数作为同一 step 的不同 item；converter 却检查 `checkpoint_dir.parent / assets`，服务默认读取 `checkpoint_dir / assets / asset_id`；#960 未修改该段 | 若 step 内有 stats、父目录没有，复制会被静默跳过；父目录若残留别的 stats 又可能复制错误。此为有条件静态反例，必须逐包比对源/目标资产路径与 hash；不声称所有目录布局必失败 |
| 保存精度与运行精度分别固定 | 老转换器先用默认 dtype 初始化再 load，最后 `.to(float32)` 不能恢复加载时已丢失的位；#960 改了初始化。服务工厂随后仍强制 `to_bfloat16_for_selected_params('bfloat16')` | FP32 文件不是 FP32 服务。分别记录 restore、merge、目标张量、保存、服务实际参数／激活的 dtype；测目标服务路径，不能只测转换脚本 |
| 同输入、同噪声、同输出语义 | `Policy.infer(obs, noise=...)` 支持显式同噪声；normalization、图像／prompt、动作转换在模型调用之外 | 保存相同 obs/prompt/noise、step 数与处理配置，对照归一化张量、模型动作、最终物理单位动作；容差与任务安全／成功需求预先关联，不能直接照用 issue 的误差阈值 |

支撑细节：[模型加载](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/models/model.py#L243)、[转换 assets 和参考配置](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/examples/convert_jax_model_to_pytorch.py#L535)、[BF16 参数选择](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/models_pytorch/gemma_pytorch.py#L56)、[Normalize／Unnormalize](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/transforms.py#L115)。模型内部部分 norm／embedding 参数保持 FP32，其余转换 BF16，不能用单一 dtype 标签替代实际清单。

实现边界：这些问题针对官方 OpenPI JAX→PyTorch 链，不能自动推到 RLinf 原生 PyTorch learner，也不能自动证明 RAPolicy／RT-EXPO 的发布器存在相同缺陷。若最终选择全程同一 PyTorch 实现，可绕开这条转换链，但仍需要 normalizer、模型包和输出语义的一致性验收。

### 4.4 依赖／权重／数据／复现边界

固定 OpenPI [pyproject.toml](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/pyproject.toml) 声明 Python ≥3.11、JAX CUDA12 0.5.3、Flax 0.10.2、Orbax 0.11.13、torch 2.7.1、transformers 4.53.2；并把 LeRobot 指向旧 SHA `0cf864870cf29f4738d3ade893e6fd13fbd7cdb5`。官方 PyTorch 说明还有替换 transformers 文件的步骤。因而不能把本轮新版 LeRobot rollout 与 OpenPI 原环境直接视为一个经验证的 pip 组合；尤其采用新版 LeRobot 的 transformers 额外组时版本范围不相交。工程上可通过进程／环境边界与明确消息 schema 集成，仍须用选定锁文件验证，而不是本轮执行安装。[官方 PyTorch 说明](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/README.md#pytorch-support)。

OpenPI 官方 README 提供 pi0／pi05 等底模和特定平台任务 checkpoint 的 GCS 入口，代码 LICENSE 为 Apache-2.0；这些入口没有在本轮下载、逐对象固定内容 hash，也没有作为本任务双向 RL 后权重。具体底模／任务权重及数据的许可、配套 normalizer、动作语义还须按最终资产包确认。本轮没有训练、仿真或真机复现，没有用 stars、下载量或 PR 测试计数代替独立复现。

## 5. GR00T 权重许可：已从模型卡冲突推进到具体文件

HF 文件树固定至 `2fc962b973bccdd5d8ce4f67cc63b264d6886495`，列出两个 safetensors 分片、模型 config、processor config、statistics 等资产；本轮仅查看树与许可证文本，未下载约 6.93 GB 模型。[固定 revision](https://huggingface.co/nvidia/GR00T-N1.7-3B/commit/2fc962b973bccdd5d8ce4f67cc63b264d6886495)、[文件树](https://huggingface.co/nvidia/GR00T-N1.7-3B/tree/main)。

该 revision 的 [LICENSE](https://huggingface.co/nvidia/GR00T-N1.7-3B/blob/2fc962b973bccdd5d8ce4f67cc63b264d6886495/LICENSE) 是 **NVIDIA License**，第 3.3 节把非 NVIDIA 方的 Work 及派生作品用途限定为非商业研究／评估；第 3.1、3.2 节也保留再分发与派生条款。它不是 Apache-2.0，也不同于 S1 模型卡正文所指 NVIDIA Open Model License。7 月 [官方博客正文](https://developer.nvidia.com/blog/develop-humanoid-robot-policies-end-to-end-with-nvidia-isaac-gr00t/) 宣称 Apache-2.0 的冲突仍存在，不能由我们自行宣布哪个文本已被撤销。

对当前设计只作资产决策：**不能把这份具体权重包标成“许可已明确、可直接商用”**；若作为研究备选，保留 revision 与全部随包条款，商业发布须先澄清对应权重授权。本项目首版无需因博客生态规模而替换底模。Dexbotic→RLinf 只复访了官方 registry 文档，API 限流及 git 网络失败使本轮未固定其源码 SHA；未把该文档重复计为 S2 新实现证据，也不宣称其 LIBERO PPO 接口已满足当前真机任务。

## 6. S3 联合反证清单与最终 policy 目标

以下是**待实施／待证伪的验证设计**，本轮均未执行；基础成功率允许为零，不能先以成功样本存在作为启动条件。

| 反例 | 要击中的假设 | 应保存的可审查结果 |
|---|---|---|
| 两个关节调换 checkpoint 名称；另加合法速度状态通道 | shape 正确／现有顺序断言足以验证本体语义 | 每一 policy 维度、观测锚点、最终驱动关节与物理单位的映射；错误置换应被拒绝，合法额外状态不得误杀 |
| 冷启动、空队列、推理时间远长于可执行剩余块；插值倍数变化及 driver 拒绝一次发送 | 出队消费等于动作已生效 | 预测／出队／插值／实际下发／驱动确认／观测区间分列；拒绝发送不能变成正常 RL transition |
| 接管恰好落在 snapshot、forward、postprocess、check-and-merge 的不同位置 | 清 holder 和 epoch 足以保护所有有状态 policy | 首块 obs 时间戳晚于恢复屏障；旧 epoch chunk 无法 dispatch；processor 缓存和 policy hidden state 不被在途计算污染；无新观测时明确等待 |
| 对同一物理状态从 A→B 改为 B→A，在旧块在途时切换 | live goal 标签可代表已生成动作的目标 | 旧／新 chunk 的行为 goal 与 supervisor 目标分别可追溯；动态目标不能重标旧动作；方向切换策略须进入冻结评测定义 |
| 转换时去掉一个 adapter／更换 normalizer／FP32 保存后用默认服务加载 | 转换成功、键 shape 一致或 FP32 文件足以证明学到的策略上线 | 预期拒绝或定量暴露差异；记录全键清单、stats hash、服务实际 dtype、同噪声端到端动作偏差，不只记录 loss |
| Harness 在评测中救回失败，或恢复程序反复成功而 policy 仍不会 | 系统任务通过率可充当 policy 能力 | 冻结同一模型与服务包，停止动作纠正，在固定双向初始分布评估；独立策略成功率、接管率、复位成本分别计量 |

这些组件可以让“可信 BC＋真实经验 RL”更容易正确实施，但不能替代学习结论。尤其从 Harness 纠正到训练参数、从训练参数到部署包、从部署包到机器人动作是三段独立的可失败链。最终必须观察退出动作帮助后，同一个冻结目标条件 policy 能否在两个方向稳定处理先前失败状态。

## 7. 证据保全与核查边界

- [ecosystem_code_log.json](ecosystem_code_log.json) 保存本轮问题、固定版本、实际 web 查询／打开、失败回退、读取对象与未执行项。
- [evidence/ecosystem/retrieval_log.json](evidence/ecosystem/retrieval_log.json) 逐次记录 urllib 请求 URL、UTC 时间、状态、字节数和 SHA256；错误不伪装为已读。PR diff、关键源码与 API 元数据均在同目录。下载器仅使用标准库读取有限文本，不执行下载的第三方代码。
- GitHub API 在第一批元数据之后返回 403 rate limit；转读 GitHub PR diff 与固定 raw 源码。部分 raw／HF 下载 timeout，浏览器工具能打开的正文另记成功；v0.6.1 RTC 与 PyTorch Gemma 的 web 回退正文存为 `web_raw_fallbacks.txt`，不冒称 urllib 文件下载成功。
- `git ls-remote` 首次因现有代理端口不可用失败，单次禁用代理的只读重试仍网络失败；没有 clone、没有改全局 git 配置。错误路径 `rollout/control.py` 返回 404 后，根据实际 import 改读 `rollout/strategies/core.py`；不是据猜测路径下结论。
- 没有安装、接受 gated 资产条款、下载大权重、执行上游测试／训练或真机实验。科学家库和旧 02–05 全程只读，未运行 UPDATE／goal。
