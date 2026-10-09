# 视觉观测路线：探针、红线与最小闭环（2026-09-23）

阶段 2 的加难度停在「抽象 2D + 真值观测」。视觉观测是下一档难度：策略不再拿到
坐标向量，而是拿相机像素。这份笔记记录三件事：**本机做视觉 RL 的真实成本**、
**一个进程级红线（segfault）及其绕法**、**已经搭好的最小闭环与三步走计划**。

## 0. 结论先行

- 本机视觉 RL 的瓶颈是**渲染**，不是训练：state-only 10.6 ms/步（94 fps），
  单相机 64² 117 ms/步（8.5 fps），双相机 84² 175 ms/步（5.7 fps）。
  A800 的 CUDA 计算完全正常（策略训练可以用），但渲染只有 CPU 软渲染
  （Mesa llvmpipe，见 [`infra-gpu-render.md`](infra-gpu-render.md)）。
- **红线：TensorFlow 与 MuJoCo 离屏渲染同进程必 segfault**（两种加载顺序都崩）。
  TF 是被 SB3 → `torch.utils.tensorboard` 拉进来的；SB3 对该 import 有 try/except 保护，
  所以在 import SB3 之前 `sys.modules["torch.utils.tensorboard"] = None` 即可共存
  （`scripts/train_pickplace_sac.py:20-27`，代价是本脚本没有 TB 日志，我们用 json/npz 记账）。
- 路线分三步：**V0 状态观测学 PickPlaceCan**（把「接触物理」和「视觉」两个变量分开）→
  **V1 像素观测同预算对照**（量「视觉的代价」）→ **V2 示范预填 + 像素 BC/RL**
  （复用阶段 2 的示范预填技巧；脚本式 pick-place 控制器待写）。

## 1. 探针数据（`scripts/probe_pickplace_can.py`）

| 观测配置 | ms/步 | fps | 说明 |
| --- | --- | --- | --- |
| state-only（不渲染） | 10.6 | 94.0 | 物理 + OSC_POSE 控制器本身的成本 |
| agentview 64² × 1 | 117.2 | 8.5 | 渲染边际成本 ≈ 107 ms/步 |
| agentview + robot0_eye_in_hand 84² × 2 | 174.7 | 5.7 | 每多一路相机 ≈ +80 ms/步 |

相机帧样本在 `runs/infra/pickplace_probe/`：agentview 能看见 can（红）、目标篮、机械臂；
腕部相机看见夹爪与桌面。**策略将来能看到什么，先用肉眼看一遍**，别只看数字。

接口事实（全是实际踩出来的）：

- robosuite 1.5 是**旧 API**：`reset() -> obs`、`step() -> (obs, r, done, info)`；SB3 2.x 要五元组，必须包装。
- 相机名白名单：`frontview / birdview / agentview / robot0_robotview / robot0_eye_in_hand`
  （写 `robotview` 直接报 `observable invalid`）。
- 相机尺寸参数是 `camera_heights / camera_widths`（没有 `camera_obs_size`）。
- `env.action_spec` 是 `(low, high)` 二元组，7 维 OSC_POSE，范围 [-1, 1]；没有 `action_space` 属性。
- 没有 `env.seed()`：随机性是构造期的 `self.rng = np.random.default_rng(seed)`，换 seed = 换 rng。
- 成功判定用 `info["success"]`：robosuite 用 can 的真实位姿对比目标区域算出的物理事实。
- **夹爪动作语义实测：`+1` = 闭合、`-1` = 张开**（2026-09-23 在 Lift 上踩出）。写反的症状非常阴间：
  approach 段夹爪自己合拢、grasp 段反而张开 → 开口宽度检查假阳性 → 状态机「以为抓到了」进 lift，
  cube 却一步都不动（maxdz=+0.000）。排查靠单局轨迹打印（eef/cube/width/action 每 10 步一行）。
  `scripts/demo_scripted_pickplace.py:161` 的写法是对的，`demo_scripted_lift_rs.py` 初版抄反了。

## 2. 成本账：为什么不能直接开 1M 步

像素单环境 8.5 fps → 100k 步 ≈ 3.3 小时纯环境时间（加 CNN 训练与冻结评测约 4–5 小时）；
1M 步单环境 ≈ 两周。robosuite PickPlace 从像素从零学通常需要 500k–1M 步量级，
**在本机这个配置下「从像素从零训满」不是可行选项**。可行的杠杆按代价排序：

1. **示范预填**：阶段 2 已证明 10k 步示范 ≈ 3× 样本效率；像素档更需要点火器。
   示范来源 = 脚本式 pick-place 控制器 `scripts/demo_scripted_pickplace.py`（七段状态机 + 抓空重试 +
   掉落重抓，5/6 成功），**已写好并接进 `train_pickplace_sac.py --demo-steps N`**。
2. **并行环境**：每个子进程自带渲染器、只 import 环境模块（**子进程里不能 import SB3/TF**，
   否则红线复现）；父进程持模型、不建渲染器。SB3 的 SubprocVecEnv 或手写 pipe 包装都行，未实测。
3. **换 GPU 渲染节点**：`REMOTE_ENDPOINTS.md` 里找带 graphics capability 的机器，未核对。

state 档 94 fps → 100k 步 ≈ 25 分钟，所以先跑 V0：回答「接触物理 + OSC + 分段稠密奖励下
SAC 能不能学会」，把物理难度和视觉难度两个变量分开量。

## 3. 已搭好的最小闭环

| 文件 | 作用 |
| --- | --- |
| `envs/robosuite_pickplace.py` | gymnasium 包装：state/pixels 两种观测；任务计数口径向阶段 2 看齐（can 进区域记 1 个 task，掉出再放进再记）；成功只用 `info["success"]` |
| `scripts/train_pickplace_sac.py` | SAC 入口：`--obs state` 走 MlpPolicy、`--obs pixels` 走 CnnPolicy；`--reward-shaping` 切稀疏/分段稠密；`--demo-steps N` 用脚本控制器预填回放池（RLPD 式最小闭环）；训练中确定性冻结评测（episode 成功率 + tasks）；`result.json` / `eval_curve.json` |
| `scripts/probe_pickplace_can.py` | 成本探针 + 相机帧存 PNG；`--cams` / `--size` / `--no-state` 可调 |
| `scripts/demo_scripted_pickplace.py` | 脚本式 pick-place 控制器（七段状态机 + 抓空重试 + 掉落重抓恢复）：**5/6 成功**，含成功视频 `runs/20260923_151341_scripted_pickplace/scripted_pickplace_success.mp4`；示范预填的示范源与残差 RL 的 base 策略 |
| `scripts/eval_pickplace_ckpt.py` | 用修复后的成功口径重评任意 ckpt |
| `envs/robosuite_lift.py` | 课程阶梯低一级：Lift（移动-抓-提起，**无放置段**）；逻辑全继承父类，只换 suite 任务与默认 horizon=300 |
| `scripts/plot_pickplace.py` | 各臂对比图：`--latest` 自动挑非冒烟臂；左图成功率 / 右图 mean_reward 并排（**两图必须一起读**），另出各臂冻结评测柱状图；存 `runs/infra/pickplace_figures/` |

在跑 / 已跑：

- `runs/20260923_135619_sac_pickplace_state/`：V0 稀疏奖励臂，100k 步完成；修复口径重评仍 0%（`reeval_fixed_success.json`）——稀疏 + 接触物理下随机探索无信号，结论为真。
- `runs/20260923_143354_sac_pickplace_state_shaped/`：V0 shaped 臂，100k 步完成；冻结评测成功率 **0%**，但 mean_reward 1.09→9.19 单调上升，重评 mean_reward **12.28**——学到了 reach/grasp/lift/hover，**没学会 place**。按 §4 决策点（shaped 仍 <10%）直接上示范预填，不再调 SAC 超参。
- `runs/20260923_152519_sac_pickplace_state_shaped_demo/`：示范预填正式臂**已完成**：冻结成功 0%；重评（shaped 口径）成功 0% / mean_reward **7.54**。示范把部分进度提前（30k 点 6.25 vs 无示范 0.04），但**没改变 100k 终点，且终点低于无示范臂的 12.28**。三臂（稀疏 / shaped / shaped+demo）成功率全 0 → PickPlaceCan 超出当前预算能力上界，拐杖无效，下课程阶梯。
- `runs/20260923_162317_sac_lift_state_shaped/`：**课程阶梯第一臂已完成**：Lift shaped 60k 从零学，
  训练中曲线 [0, 20, 0, 0, 0, 0]%；终冻结评测 5 局给 40%（2/5），**20 局重评只有 5%（1/20）**——
  40% 是小样本错觉，以 20 局为准。mean_reward 107.5 说明它会接近/贴住 cube 但几乎不提起。
  结论：课程阶梯方向对（栈由脚本 6/6 证明没问题），但 **60k 从零 SAC 在 Lift 上也还没学会**，
  接触任务的样本效率问题比任务难度更根本 → 下一杠杆是示范预填/BC 锚定（对照臂在跑）。
  Lift 的 shaped 档有稠密 reach 信号
  （`1-tanh(10*dist)` + grasp 0.25），与 PickPlaceCan 的「稀疏=完全无信号」不同，两任务成功率不可互比。
- `runs/20260923_164831_sac_lift_state_shaped_demo5k/`：**预填对照臂已完成**（5k 预填 + 60k）：
   冻结 20%（1/5）、20 局重评 **10%（2/20）/ reward 70.4**。从零臂 5%、纯 BC 5%、预填 10%——
   三个单杠杆都在噪声级低位：**预填在接触物理里点火能力有限**（抽象环境 +27 点不外推第二次确认）。
   Lift 20 局归因表（截至 2026-09-23 20:35）：从零 5% / BC-only 5% / 预填+RL 10% /
   **预填+BC+RL 15%（tasks 7，当前最好）** / 预填+BC+锚定+RL 在跑。
  bc 臂训练中曲线 [0,0,20,40,0,40]%：能力出现过（40k 点 40%/reward 149.5）但**反复塌回 0**——
  热启动给得了起点、保不住终点；稳定性是下一个要解的问题（anchor 臂正在检验）。
- **加示范量的假设被否证（2026-09-24）**：BC-only 5k 示范 = 5%/21.3，**20k 示范（4×，240 局、
  初始位姿多样性本来就在）= 0%/35.6**——示范越多，MSE 平均策略越保守（hover 更多、lift 更少）。
  瓶颈不在示范数量/初始位姿覆盖，在 obs→action 的相位歧义 + 分布偏移 + RL 遗忘。
  「加构成」的可检验版本 = `--demo-lift-focus`（grasp->lift 快照重放 lift 段过采样，总量不变），
  臂在跑；「加视角」对 state 观测臂无意义（不看相机），留到像素档当增强用。
- PickPlaceCan 组合臂（预填10k+BC3k+RL100k）终判：冻结 0%、20 局重评 **0%/reward 1.70**
  （从零 shaped 臂重评 12.28）→ 组合在难任务上**负迁移**；示范杠杆只在 Lift 这种够得着的任务上为正。
- **反应式（纯观测）控制器尝试失败（0/6）但给出关键诊断**：夹爪执行器过渡区（开口宽度
  0.012~0.035 之间）让单帧纯观测策略在「夹/放」间 chatter，永远完不成开合动作——相位信息
  真实存在于**时间维**。据此实现 `--hist N`：state 观测堆叠最近 N 帧（wrapper 层，示范与策略
  同口径），把时序信息显式给策略。判决臂：hist=4 / 5k 示范 / BC-only / 20 局（对照 hist=1 的 5%）。
  反应式控制器留作备份（`scripts/demo_reactive_lift_rs.py`，含执行器 chatter 的教训）。
- `runs/*_smoke_lift_bc/`：BC 热启动冒烟（2k 示范 + 300 步梯度 + 500 训练步）：BC loss 2.67→0.08，
  500 步评测 mean_reward **7.48**（无 BC 的同点冒烟 0.35）→ 热启动的 actor 从第 0 步就在
  「接近/抓握」regime。实现 = `train_pickplace_sac.py --bc-steps N`：拿示范 (obs, action) 对
  actor 均值头做 MSE（目标 `atanh(clip(a,±0.999))`，因为输出要过 tanh；入口是 SB3 的
  `get_action_dist_params`，`Actor.forward` 返回的是采样动作不能直接用）。
- `runs/20260923_174333_bc_only_lift/`：**纯 BC 对照（已完成）**：5k 示范 + 3000 步梯度、不开 RL，
  20 局冻结 **5%（3 个 task）/ mean_reward 21.3**。与从零 SAC 60k（5% / 107.5）成功率同档但
  **失败模式不同**：BC 偶尔真提起、其余局游走（MSE 对多模态示范做平均的经典病）；RL 贴住 cube
  不提起（shaped reach 的局部最优）。两者都不够，组合臂（BC 热启动 + RL）才是检验点。
- `runs/20260923_171636_sac_lift_state_shaped_demo5k_bc3k/`：**BC 臂在跑**（5k 预填 + 3000 步 BC +
  60k RL，与 demo5k 臂同预算同示范量，只多 BC 一个变量）。三臂对照表 = 从零 / 预填 / 预填+BC。
- **BC 锚定回调已实现待命**：`--bc-anchor-lr >0` 时在线 RL 每步插一步 BC 梯度（独立 optimizer 与
  SB3 actor optimizer 交替更新同一组参数，等价 actor loss 加 λ·MSE(mu, atanh(a_demo))；不复制
  SB3 `SAC.train()` 以免版本耦合）。冒烟 `runs/*_smoke_lift_anchor/` 通过（anchor_loss 随评测打印）。
  **锚定臂负结论（2026-09-23 20:40，已停）**：`runs/*_sac_lift_demo5k_bc3k_anchor/` 每步锚定
  （lr 3e-4）下 10k/20k/30k = 0.49/0.09/0.06 单调塌缩、anchor_loss 0.38→7.0→33.1（actor 被推离
  示范又追不回，RL 的接近行为也被每步 BC 梯度抵消）——**比不加锚定更差**。机制判断：锚定压力与
  RL 梯度同量级时两者互删。若重试：`every>=32` 且 lr<=1e-4（锚定当弱正则，不当主损失）。
  bc 臂 15% > 单杠杆 → 按决策树把 **预填+BC 搬回 PickPlaceCan**：
  `runs/*_sac_pickplace_state_shaped_demo10k_bc3k/`（10k 预填+3k BC+100k RL）在跑。
- `runs/*_scripted_lift_rs/`：脚本式 Lift 控制器判别实验。初版 0/6（夹爪语义写反）；修正后 **6/6 成功、约第 48 步提起** → **栈（包装层+OSC+夹爪）没问题，Lift SAC 臂的 0% 是学习侧问题**。它同时是 lift 示范预填的示范源。
- 记账补强：`config.json` 现记录 `demo_steps` / `demo_episodes`（混合比扫描要能追溯每臂预了多少示范）。
- `runs/*_smoke_pickplace_pixels/`：V1 冒烟 5k 步（验证像素全链路 + 实测像素档步速）。
- `runs/20260923_135418_smoke_pickplace_state/`：state 冒烟 2k 步。

### 3.1 2026-09-24 午间：Lift 突破、口径修正、抓取监护

- **Lift 第一次真的学会（钉死口径 20 局 90%）**：`runs/20260924_095928_sac_lift_demo5k_bc3k_savebest/`
  （5k 脚本示范预填 + 3k 步 BC 热启动 + 60k SAC + save-best）。未钉死口径 20 局重评 **95%（19 task）**，
  钉死口径（`env_factory` 出题）**90%（18 task）**；训练曲线 [0,0,0,40,0,40]%。
  对照 `runs/20260924_101049_..._dagger2/`（多两轮 DAgger）：钉死口径 20 局 **50%**，
  曲线 [0,0,20,0,20,60]% → **DAgger 这一轮没帮上，反而不如不加**（与 09-24 早间 DAgger 负结论一致）。
- **save-best 的选点口径太吵**：同一臂按「5 局评测的 (tasks, success)」挑出来的 `model_best.zip`
  钉死口径只有 **50%**，比 `model_final.zip` 的 90% 差 40 点。**5 局挑不出最好的 ckpt**，
  下一步要么把选点评测提到 ≥20 局，要么按曲线上多点平均挑（别让"选点噪声"当成"能力"）。
- **重大口径修正：此前每条臂评的都是不同的物体**。`runs/20260923_171636_*`（20 局 15%）与
  `runs/20260924_095928_*`（20 局 95%）的 `config.json` 逐项相同（同 task/obs/steps/demo/bc/horizon/**同 seed**），
  差别只在 robosuite **构造期用未播种 RNG 抽的物体尺寸**（`harness/README.md` 早就写了这个坑，训练脚本没用上）。
  修法：`scripts/train_pickplace_sac.py` 的环境构造与评测出题统一走 `harness/env_factory`
  （新增 `_make_env` / `_reset`，`--pin-object` 默认 1），`config.json` 记 `object_geom`
  （cube 0.0220×0.0210×0.0217 m、80.3 g）供跨臂核对。**09-24 之前的跨臂数字不严格可比，从今天起才可比。**
- **单种子单次不能当配方能力**：seed-1 复现臂（未钉死，`runs/20260924_110746_*`）**终判 0%**
  （曲线 [0,0,0,0,0,0]、冻结 0%、60k 步 1535 s），与 seed-0 的 90% **同配方同预算**。
  所以那个 90% 是一次**种子依赖的偶发**，不能说"配方学会了 Lift"。已排队钉死口径的
  seed0 / seed1 复现臂 + 一条监护干预臂（`/tmp/pin_chain.log`），
  以后 Lift 的结论一律报「≥2 seed，每个 seed 20 局重评，均值 + 极差」。
- **抓取监护上线：`harness/grasp_guard.py`**（用户提的"上层 harness 直接下发抓取指令"）。
  触发有两种模式：`window`（末端已在物体上方 0.5–4.5cm、水平误差 ≤1.4cm，却连续 8 步不合爪）
  与 `stall`（放宽到水平 ≤6cm、高度 −1~12cm，且末端在最近 20 步几乎没动 = 真的停住了）。
  接管原语 = 对齐 → 合爪 25 步 → 提到 z0+5cm → 交还控制权（每局 ≤2 次、20 步冷却）。
  **纪律**：成功只认环境真值；配对评测同 seed 先跑裸策略再跑带监护，输出 `rescue_delta` /
  `held_delta` / `intervention_rate`，绝不只报带监护的成绩。
- **监护实测（钉死口径 20 局，`--guard`）**：

  | ckpt | 裸策略 | 带监护 | rescue | 干预率 |
  | --- | --- | --- | --- | --- |
  | `20260924_095928` final（强） | **90%** | 95% | +5pp | 10% |
  | `20260924_095928` best | 50% | 50% | 0 | 0%（没出手） |
  | `20260924_101049` final / best | 50% | 50% | 0 | 0%（没出手） |
  | `20260923_171636`（弱，同配方另一次抽样） | 20% | 25% | +5pp | 10% |
  | `20260924_095648_bc_only_lift_hist4`（弱） | 0% | 0% | 0 | 0%（没出手） |
  | `20260924_100042_bc_only_lift_dagger3`（hover 型，4 局冒烟） | 0% | **50%** | +50pp | 50% |

  读法：**强策略几乎不需要监护（干预率 10%）——这正是 HIL-SERL 里"干预率随训练下降"的形态**；
  hover 型弱策略（会停在物体上方不合爪）能被救回一半；而"根本不到抓取位"的弱策略监护一次都不出手。
  所以监护**不是**万能拐杖：它只补"最后一厘米的合爪时机"，出手次数本身就是失败模式的判别器。
- **PickPlace 的瓶颈在抓取上游（两条独立证据）**：
  漏斗 `runs/infra/funnel_pp_203643.json`：`held 0/12`、6 局 `no_reach`、最近离篮心 0.502 m；
  停留诊断 `runs/infra/diag_pp_grasp_ready.json`（6 局 × 400 步）：落在 6cm 捕获区的步数占比
  **0–4.3%**，最长连续停留 **0–17 步**（stall 触发要 20 步）；水平最近的那一帧高度差是 **+6~+10cm**
  （在物体上方太高），高度对的时候水平差 2–8cm；seed 5005 有 **98.5%** 的步在发合爪指令（空中乱合）。
  → PickPlace 缺的是**接近与下降的协同**（对齐 + 降高），不是"合爪时机"；
  因此"针对抓取动作加示范/加监护"在这个任务上不会有效，必须先过 Lift 这一级课程。
- **干预数据变能力（`--guard-rounds` / `--guard-episodes` / `--guard-inject`）**：只保留"策略卡住那一小段"
  的出手记录，聚合进 BC 集并（可选）注入 SAC 回放池——比 DAgger 少一到两个量级的数据，
  口径与 HIL-SERL 的干预学习一致。臂已排队（钉死口径，Lift，seed0，`/tmp/pin_chain.log` 第 2 条）。
- 顺手修的两个坑：① `scripts/eval_pickplace_ckpt.py --ckpt` 单独给时 task 落回默认 `pickplace`，
  把 Lift 模型套进 PickPlace 环境 → 观测 60 vs 64 维 `ValueError`（现在从 ckpt 目录反查 `config.json`；
  另加 `--tag` 防 final/best 产物互相覆盖）。② 纯 RL 档（`--demo-steps 0`）走到 `_run_dagger` 调用处
  会 `NameError`（`demo_obs` 只在有示范时赋值），现在给空数组默认值。

## 4. 三步走各自回答什么问题

| 阶段 | 问题 | 判据 |
| --- | --- | --- |
| V0-Lift | 这套栈（OSC+SAC+包装层）能否把**接触任务**成功率从 0 训上去？ | shaped 60k 冻结成功曲线：>0 且上升 → 回 PickPlaceCan 加 BC 锚定/拐杖；仍 0 → 先查栈（控制器带宽/观测/奖励尺度），不是查任务 |
| V0 state | 接触物理下 SAC 能否学会 pick-place-can？相变在哪？ | 冻结评测 episode 成功率曲线；**稀疏 vs shaped 两臂对照**（稀疏=探索信号问题，shaped=学习能力问题） |
| V1 pixels | 同预算下把 state 换成 64² 像素，掉多少点？ | V0/V1 同 seed 同步数的冻结评测差值 = 「视觉的代价」 |
| V2 demo+pixels | 示范预填能否把像素档拉起来？BC 先行的收益？ | 预填 vs 不预填同预算对照；必要时先 BC 再 RL |

V2 之后才把阶段 2 的三张表（复位模式 / 覆盖 / 救场）搬到 robosuite 上重跑——
**指标口径不变**（`info["success"]` + 任务计数 + 覆盖统计换成 can 放置位置网格）。

## 5. 坑清单（现象 → 原因 → 修法）

| 现象 | 原因 | 修法 |
| --- | --- | --- |
| `TypeError: camera_obs_size` | 1.5.2 参数改名 | `camera_heights / camera_widths` |
| `ValueError: observable robotview_image is invalid` | 相机名不在白名单 | 用 `robot0_robotview` / `robot0_eye_in_hand` |
| `ValueError: too many values to unpack` | 旧 API | `obs = env.reset()`、四元组 step |
| `AttributeError: action_space` | robosuite 用 action_spec | `lo, hi = env.action_spec` |
| `TypeError: 'NoneType' object is not callable`（env.seed） | 1.5 无 seed() | 换 `env.rng = np.random.default_rng(seed)` |
| **segfault（core dumped）** | TF × llvmpipe 同进程 | import SB3 前屏蔽 `torch.utils.tensorboard` |
| state 100k 到 70k 步仍 0%、mean_reward 恒 0.00 | robosuite `reward_shaping` 默认 False → PickPlaceCan 是**纯稀疏奖励**（成功才 +1），随机探索永远拿不到信号（与阶段 2「随机探索 0% → 相变推迟」同一机理的更极端版本） | `--reward-shaping 1` 打开 reach/grasp/lift/hover 分段稠密奖励；稀疏臂保留作基线（`runs/20260923_135619_sac_pickplace_state`），shaped 臂 `runs/20260923_143354_sac_pickplace_state_shaped`；成功率永远以 `info["success"]` 为准 |
| `info["success"]` 恒 False（所有早期评测列不可信） | robosuite 1.5 的 `info` 是**空 dict**；成功真值在 `env._check_success()` | 包装层改读 `_check_success()`；`scripts/eval_pickplace_ckpt.py` 重评旧 ckpt（稀疏 100k 重评仍 0% → 探索信号问题为真，非口径假象） |
| 放置目标坐在篮墙交点上 | 目标「篮子」是 2x2 篮格的一个象限；`bin2_pos` 是四格交点；`_check_success` 用 objects 列表下标（can=3）选象限 | 目标取 `env.target_bin_placements[env.object_to_id["can"]]`；staged reward 的 hover 与 success 用同一 id，但**不要**用 `bin2_pos` |
