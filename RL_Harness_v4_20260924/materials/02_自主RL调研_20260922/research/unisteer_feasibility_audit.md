# UniSteer 可达性与工程闭环深审

日期：2026-09-22。适用条件：先做松灵单臂 pick-and-place，允许少量正反成功示范与人工接管，GPU 尚未确定。只阅读官方源码及依赖，运行了纯 Python 标量代数检查；未安装库、加载 VLA、训练模型或操作机器人。

固定 UniSteer 提交：`cd87d240f5ec646e7590476593c3e95eb765b473`。其 `pyproject.toml` 锁定 LeRobot：`c8ce413d738da15a2eed2d0832315779ea28cbf9`。相关源码只读副本保存在本目录 `unisteer_source_cd87d240/`，该目录是研究缓存，不是安装或可运行环境。以下更新此前短审，并不把当前发布实现等同于论文实验实现。

## 结论与投入建议

**当前固定版本不应直接用于第一次真实在线 RL。** 比低维噪声表达力更前置的问题是：反演例程与锁定 π0.5 decoder 的时间、符号约定不一致；常量速度场检查已能构造反例。可以研究性修复并做模型 roundtrip 验收，但这意味着现在的 UniSteer 属于“需要主动维护的候选”，而非比 ConRFT 更省集成成本的即用替代品。

单臂硬件贴近、冻结大模型降低优化器开销，是它继续保留的理由；双卡在线、任务暖启动、反演、执行器以及奖励都仍有成本。GPU 未确定时，不宜因为“小 actor”就先假设普通单卡足够。若团队优先尽快得到稳定的正反练习原型，当前更合理的是保留 ConRFT 路线，让 UniSteer 通过下述廉价门槛后再竞争。这里的比较是当前候选的研发风险判断，未声称已完成两套系统的同机性能实测。

## 1. 前置阻断：发布反演与依赖 decoder 约定不一致

锁定 LeRobot 的 π0.5 decoder 从噪声时间 `t=1` 开始，以 `dt=-1/N` 做 `x ← x + dt*v(x,t)`，最后到动作时间 `t=0`。UniSteer adapter 直接调用该 velocity，没有把 `t` 替换为 `1-t` 或翻转 velocity 符号。[锁定依赖声明](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/pyproject.toml)、[锁定 decoder](https://github.com/huggingface/lerobot/blob/c8ce413d738da15a2eed2d0832315779ea28cbf9/src/lerobot/policies/pi05/modeling_pi05.py)、[π0.5 adapter](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/model/openpi/pi05_original.py)

但当前 `_infer_noise_target_batch_fixed_point_core` 从人工动作开始，按 `t=.9,.8,…,0` 迭代，使用 `x = x_next - Δt*v(x,t)`。与上述 decoder 一致的逐步反演，应先逆最后一次解码更新，即从 `t=.1,.2,…,1`、使用 `x = x_prev + Δt*v(x,t)` 的固定点方程。当前代码的时间和符号两者均不一致。[反演源码](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/tool/unisteer_actor_supervision.py)

独立标量复现已保存：`unisteer_inverse_algebra_check.py` 与 `unisteer_inverse_algebra_check.json`。它不导入任何模型或机器人库，只复现循环公式：

| 速度场、目标动作 0.25 | 发布反演接锁定 decoder 的动作误差 | 与 decoder 一致的逆公式误差 |
|---|---:|---:|
| 常量 `v=1` | 2.0 | 约 2.8e-17 |
| 时变 `v=t` | 1.0 | 约 5.6e-17 |
| 状态相关 `v=x` | 0.21639 | 0 |

常量例中，发布逆得到噪声 -0.75，decoder 再得到 -1.75；目标是 0.25。发布逆的“局部固定点残差”仍可近零，说明只看该残差不能证明与真实 decoder 闭环一致。

**证据边界：这证明发布循环与锁定依赖的通用离散逆关系不一致，不是实测 π0.5 的误差，更不能据此否定论文实验结果。** 修复之后仍须验收数值收敛、BF16 精度、实际模型完整反演及动作单位；增加固定点迭代数本身不能修复符号和时间约定。

另一个容易误读的字段：在当前固定点路径里 `actor_prior_loss` 被设为零，`lambda_norm` 只是最终统计 loss 的组成，固定点计算在 `no_grad` 下没有按该 loss 优化噪声。不能因配置中有这两个系数，就称当前反演实施了相应的优化约束。

## 2. 压缩到底限制什么：应看实际执行窗口

默认 π0.5 配置是生成 horizon 50、返回 chunk 50、`control_replan_interval=10`、真实 action 7D、内部 noise 每步 32D。`mean_time` 对完整反演噪声**前 10 步**取均值，得到一个 32D 向量；`repeat_last` 再将其重复到全部 50 步。actor 输出是 `2.5*tanh(u)`，每维范围为 (-2.5,2.5)。配置中的 `latent_dim=50` 是 actor/critic 编码瓶颈参数，不能误认成最终噪声 actor 的维数。[配置](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/config/online/pi05_spoon.yaml)、[投影/展开](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/model/openpi/openpi_noise.py)、[actor](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/trainer/RLTrainer.py)

不过执行器未发布，服务只返回动作块，无法据配置证明实际机器人一定执行恰好 10 帧。对接时必须让 executor 的真实执行长度、投影窗口、discount 时间单位一致。

对固定观测与任务，记冻结 decoder 为 F，重复展开为 E，执行前 K 步选择为 P。实际可控动作是 `P_K F(E(z))`：

- 默认 K=10 时，是 32D 噪声映射到最多 70D 动作序列，其局部 Jacobian 秩至多 32；因此不能声称可以表达任意十步人工动作序列。
- 这不证明 pick-and-place 必然失败。有效轨迹通常平滑且高度相关，任务需要的动作集合可能远低于 70D。必须实际测关键抓放片段覆盖率。
- 若每次只执行 K=1，则输出只有 7D，32D 输入不存在上述维数不足结论；但局部 Jacobian 是否满秩、有效噪声是否落在边界内、冻结 decoder 是否覆盖所需动作仍需检验。
- 单步重规划把默认约 3 Hz 的决策需求推到约 30 Hz（按 30 Hz 控制流计算），可用延迟预算从约 333 ms 降至约 33 ms；这些是目标预算，**不是测得的推理速度**。不能仅改执行长度便宣称可部署。
- 50 步生成长度不是“必然导致不可达”的直接证据。只应比较执行前缀；但 action token 在 decoder 内有耦合，未来 token 不是天然无关。直接把生成长度也改为 1，会改变冻结模型的运行分布，需单独验收。

配置扩维也有实现边界：`project_full_noise_to_actor_torch` 目前支持 1 步 compact，或全部 horizon 步的完整噪声。设置 `predicted_noise_steps=5/10` 虽可能通过 layout 构造，后续 compact 投影会报错，不能当成已支持的多块噪声方案。全 50 步对应 1600D actor/Q 动作，计算与 RL 样本复杂度显著改变；这是新方案，需要验证，而非无成本参数调整。

## 3. 接管数据与 Bellman credit：默认冷启动仍可能缺少成功信号

混合轨迹按 `is_human` 控制权切段，仅最后一段继承整条轨迹的 success；每个片段都作为独立 terminal episode，最后 transition 的 mask=0。默认 `add_human_inverse_to_rl_buffer=false`，人工段仅用于 actor inverse-SFT。RL critic 的 target 是 `r + mask*γ^10*min Q_target`，没有 entropy backup。[分段实现](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/tool/inference_server.py)、[模型 replay 构造](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/tool/unisteer_rl_server.py)、[人工 replay 构造](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/trainer/UniSteerTrainer.py)

具体后果：

| 真实执行过程 | 默认 RL 接收什么 | 对低起点策略的含义 |
|---|---|---|
| 自主 M → 人工 H 完成成功 | M 全零奖励且终止；H 仅 SFT | 整次最终成功不会给 M 提供正回报；要靠纠正监督先让自主策略出现成功 |
| M → H → M 完成成功 | 末 M 有奖励，首 M 仍终止零奖励 | 后段可学；跨人工段的显式 TD 传播被截断，参数泛化可能转移信息但无保证 |
| 开启 human-RL，M → H 成功 | H 可有成功奖励，M 仍单独终止 | 打开 flag 并不会自动恢复 M→H 的 credit 链 |

将接管视为本次自主尝试失败可以是有意的“降低接管需求”目标，不能一概判错；但它不同于用完整混合成功轨迹强化所有有用前缀。全部自主片段没有正奖励时，零 Q 是 Bellman 方程的一个固定点；探索仍可发生，但没有任务成功梯度凭空产生。因此不能把默认版本描述为天然解决零成功 RL 冷启动。

**人工 RL 可选分支还有时间尺度问题。** 人工 inverse targets 按每一帧滑窗建立，排序后 transition 接下一条记录（通常 t+1），却仍使用固定 `γ^10`；而自主动作按执行窗口，默认意图为 t→t+10。人工噪声目标又对应多步动作窗。启用之前须统一 transition 的决策步长、真实 next state 和 discount；不要只打开开关就认为已经复现论文的人机 replay。[人工采样源码](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/tool/unisteer_actor_supervision.py)

更根本地，如果 `decode(project(inverse(human_action)))` 并不接近实际人工执行动作，那么给 Q 的 `(state, latent_action, observed_next_state)` 也不符合当前 decoder 动力学；这不是单纯监督标签有一点噪声。故完整、压缩、bounded 闭环应先于 human-RL 开关。跨接管边界是否保留 bootstrap，需依据真正执行的控制流与目标定义设计，不能机械把所有 mask 改成 1。

## 4. 正反任务与夹爪：具体对接陷阱

**反向成功任务不能标为 `is_reset=true`。** 两类 replay 构造都会将该字段对应的 success 强制变为 false。应将“把 B 中物体放回 A”当作有效 reverse 任务，记录独立 task/goal 和成功条件；事故处理、人工摆场等系统 reset 才用工程复位标签。否则可能出现回场成功但训练奖励始终为零，或已有奖励 sidecar 验证失败。

当前小 actor/Q 并非没有语言条件：π0.5 adapter 将图像、语言 token 的 PaliGemma prefix 表示（2048D）与本体状态（7D）拼成 2055D state。自主 replay 保存服务返回的 state；人工 replay 根据任务文本重建 state。但任务文本元数据是**每条轨迹级**，没有完整公开的正反目标调度器。建议每次目标切换新建轨迹和任务文本，成功检测器同时按 goal 路由；勿在同一条 sidecar 只改首尾文本而混入两个任务。[状态提取](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/model/openpi/pi05_original.py)、[推理入口](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/agent/inference_agent.py)

夹爪不是独立 HIL-SERL 离散控制器：默认是 7D flow action 的最后一维，一起参与 inverse、压缩和噪声 steering。dataset 可能用 `gripper_ctrl_smooth.npy` 覆盖 `action.npy` 最后一维，缺失时可退回关节状态；6D proprio 也会补夹爪，甚至用前一帧命令估计。这要求确认保存的是**实际发送的夹爪命令**，不是期望状态混入动作标签；抓紧/放开时序必须单独验收，不能被平均 pose MSE 掩盖。[数据装载](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/src/dataset/dataset.py)

## 5. 无需训练的离线验收协议

以下为待执行协议，不代表已在用户模型或示范上测出结果。仅第 0 项已完成标量代数检查。真实 VLA 检查可用现有冻结 checkpoint 和录制数据，不需要先训练新 actor。

| 层次 | 输入与操作 | 报告项与通过条件 |
|---|---|---|
| 0. 离散约定 | 零场、常量非零场、时变场、收缩场；与锁定 decoder 循环闭环 | 除可解释数值误差外回到原动作；当前发布逆未通过。修正公式先过此关 |
| 1. 完整 inverse | 保存观测/goal、正常化后的人工动作窗；反演完整噪声并完整解码 | 实际执行前 K 帧逐轴误差、姿态角误差、夹爪开关误差、P50/P95/max、残差。确认完整反演数值可用 |
| 2. compact | 同一完整 inverse，经官方前 K 帧均值＋repeat 展开再解码 | 量化纯投影造成的动作变化，分别看接近、闭合、提升、搬移、释放以及 reverse，而非只有全数据均值 |
| 3. bounded | compact 噪声投影到 actor 的允许范围，再解码 | 统计超界坐标/样本比例、饱和程度、限幅新增动作偏差；噪声范数大不直接等同实机危险，仍看解码动作 |
| 4. supervised actor | 若已有相容 actor checkpoint，仅运行其确定性均值与随机采样 | 对比 bounded oracle 与 actor 输出，分离表示瓶颈和拟合/泛化误差。没有 checkpoint 则标未测，不能以随机 actor 代替监督拟合能力 |
| 5. 数据/奖励合同 | 合成 M→H、M→H→M、成功/失败、reverse、episode截断；不接机器人 | 核对每条 transition 的 goal、实际 action、decision index、next state、elapsed frames、mask、reward、discount 与预期一致 |

为防止误差相消，建议保存四组解码动作及差向量：`e_full=a_full−a_human`、`e_compact=a_compact−a_full`、`e_bound=a_bound−a_compact`、`e_actor=a_actor−a_bound`。差向量能相加还原总误差，MSE 标量不能按此简单相加。阈值由物体尺寸、夹爪裕量、放置区域和控制重复精度决定，不能给所有硬件武断套用统一毫米数。

当前官方反演函数已输出 `action_loss`、`post_projection_action_loss`、固定点残差；这些可复用，但默认是整段归一化动作平均误差。必须增加**执行前缀、反归一化物理量、姿态与夹爪分项**，否则未执行尾部可能主导分数，单位不同的维度也会混淆。

低成本补充：对 compact decoder 做有限差分局部扰动，查看执行前缀 Jacobian 的奇异值与噪声边界，比较 K=1、5、10 的局部覆盖；这仍不是全局可达性证明。若均值投影失败，并不能推出所有 compact 噪声都失败——均值只是廉价投影，并非动作重建最优解；可另行设计固定模型下的 bounded latent 优化作为 oracle，上界验证不等于已经拥有可泛化的 actor。此轮没有运行该优化。

## 6. 哪些必须真机检查，以及投入止损线

离线通过之后，还须检查执行器端的端到端时延与抖动、相机/本体/命令对时、实发控制模式、夹爪实际响应、接管时剩余 chunk 的取消、恢复时新观测重新推理、goal 切换时成功检测可靠性，以及动作限幅后是否正确记录实际控制权。README 明确硬件 executor 未提供，并要求修改/覆盖模型动作时标为 human；接口可记录的是命令，不等于已经证明执行器物理跟踪误差足够小。[官方部署合同](https://github.com/microsoft/UniSteer/blob/cd87d240f5ec646e7590476593c3e95eb765b473/README.md)

同 README 给出的参考资源是：30 条示范的 full-VLA warmup 使用 A100，发布 π0.5 暖启动配置面向 80GB；在线为两张 RTX 5080，一张推理，一张执行反演、SFT、SAC。反演每个样本的默认核心包含 10 个 flow step ×16 次固定点迭代，另有残差与完整/压缩解码，不能把它当成仅训练小 MLP 的开销。没有实际 GPU 不报虚构的训练耗时或最低显存。

建议投入顺序为：**先解决固定版本离散逆不一致 → 冻结模型离线覆盖检查 → 统一人工/自主 transition 与 reverse 奖励 → 最小单臂 executor → 小规模有接管在线比较**。如果完整 inverse 尚不能稳定闭环，或 compact 在抓放关键状态无法覆盖人工动作，停止继续投入 RL 超参调优。若为补救需要扩到全噪声 actor、重写 replay 时间尺度和执行系统，当前资源收益已未必优于直接推进可更新动作头的 ConRFT 路线。
