# 训练内部机制：SAC 网络长什么样、目标函数是什么、状态机怎么落到关节上

> 2026-09-22 · 所有网络结构和损失数值都是**从本机的模型文件 / 训练日志里实测 dump 出来的**，
> 行号对应本机安装的 stable-baselines3 2.7.1 与 robosuite 1.5.2 源码，可逐条复核。
> 配套：[`notes_stage1.md`](notes_stage1.md)（结果）、[`notes_stage1_visual.md`](notes_stage1_visual.md)（可视化）。

---

## 1. 训练循环：一步到底发生了什么

入口在 `scripts/train_reach.py`：

| 行 | 代码 | 作用 |
| --- | --- | --- |
| `train_reach.py:143` | `DummyVecEnv([lambda: Monitor(make_reach_env(**env_kwargs))])` | 训练环境（1 个并行实例，Monitor 负责记 episode 奖励） |
| `train_reach.py:147` | `model = algo_cls(policy="MlpPolicy", env=vec_env, seed=..., **algo_kwargs)` | 建 SAC：actor + 2×critic + critic_target + 熵系数 + 3 个 Adam 优化器 + ReplayBuffer |
| `train_reach.py:163-170` | 独立 `eval_env` + `EvalCallback(log_path=...)` | 评测与训练隔离；`evaluations.npz` 就是它写的 |
| `train_reach.py:175` | `model.learn(total_timesteps=50000, callback=eval_cb)` | 主循环 |

`learn()` 内部是 SB3 的 off-policy 主循环
（`stable_baselines3/common/off_policy_algorithm.py:514 collect_rollouts`）。
**每一个环境步**做四件事：

```
obs ──actor 采样──▶ action ──env.step──▶ (reward, next_obs, done)
  │                                            │
  └────────── 存进 ReplayBuffer ◀──────────────┘
                    │
                    └─ 因为 train_freq=1, gradient_steps=1：
                       每步从 buffer 抽 256 条，做一次 sac.py:202 train()
```

`train()`（`stable_baselines3/sac/sac.py:202`）一次调用里按顺序更新三组参数：
熵系数 α → critic → actor，最后用 `polyak_update(..., tau=0.005)` 软更新 critic_target。
**这就是"训练"的全部**：没有别的神秘步骤。

配置在 `configs/reach_sac.yaml`：`buffer_size=100000`、`batch_size=256`、`gamma=0.99`、
`tau=0.005`、`train_freq=1`、`gradient_steps=1`、`net_arch=[64,64]`、`lr=3e-4`。

---

## 2. SAC 的网络构造（从 `model_final.zip` 实测 dump）

```bash
python -c "from stable_baselines3 import SAC; m=SAC.load('runs/20260922_170720_sac_reach/model_final.zip'); \
  [print(n, [(k, tuple(p.shape)) for k, p in getattr(m, n).named_parameters()]) for n in ('actor', 'critic')]"
```

### actor（策略网络）—— 4998 个参数

```
obs (6) ──Linear(6,64)+ReLU──▶ (64) ──Linear(64,64)+ReLU──▶ (64)
                                    ├─▶ mu     : Linear(64,3)   均值
                                    └─▶ log_std: Linear(64,3)    log 标准差
action = tanh( mu + exp(log_std) * N(0,1) )        # SquashedDiagGaussian
```

- 它输出的**不是一个动作，而是一个分布**（对角高斯），采样后过 `tanh` 压到 [-1,1]。
  源码：`sac/policies.py:167 Actor.forward` → `common/distributions.py` 的
  `SquashedDiagGaussianDistribution`（tanh 保证动作不越界，log_prob 里带 tanh 的修正项）。
- **训练时采样**（探索），**评测时取均值**（`deterministic=True`）。
  这就是 `fig_curve.png` 里「中途评测是负的」的原因：没成形的高熵分布，均值动作很差。
- 两个头（mu / log_std）意味着策略能学会「哪个方向该确定、哪个方向该随机」。

### critic（价值网络）—— 2 个 Q 网络，各 4865 参数，共 9730

```
[obs(6) ⊕ action(3)] = (9) ──Linear(9,64)+ReLU──▶ (64) ──Linear(64,64)+ReLU──▶ (64) ──Linear(64,1)──▶ Q(s,a)
```

- **输入是 obs 拼 action**：critic 回答的是「在这个状态做这个动作，未来累计能拿多少奖励」。
- 为什么两个（qf0 / qf1）：取 `min` 抑制 Q 值高估（clipped double-Q，TD3 的思想）。
- `critic_target`：和 critic 同结构的**副本**，不接受梯度，只被
  `polyak_update(critic → critic_target, tau=0.005)` 慢慢拖着走。
  作用是给 Bellman 目标提供一个稳定的靶子，否则自己追自己会发散。

### 熵系数 α —— 1 个可学习标量

- `log_ent_coef` 是一个标量参数，`α = exp(log_ent_coef)`，`target_entropy = -dim(action) = -3`
  （`sac/sac.py:169-171`）。
- 实测轨迹：`α = 0.916`（292 次更新）→ `0.0125`（16990）→ `0.0091`（49876）。
  **这条曲线就是「探索 → 收敛」的旋钮**：前期 α 大，鼓励随机探索；学会后 α 自动降到 ~0.01，
  策略变得几乎确定。它和 `fig_curve.png` 的相变（10000→15000 步）是同一件事的两面。

### 参数量合计

actor 4998 + critic 9730 + critic_target 9730 + α 1 ≈ **24459 个浮点数**。
训练 50000 步改的就是这 2.4 万个数字（critic_target 不算学习，只算跟随）。
这就是「机器人学会了任务」在物理上的全部含义。

---

## 3. 奖励与目标函数：两层，别混

### 第一层：环境奖励（任务定义）

`envs/reach_env.py:86-94`，一共 6 行：

```python
success = dist <= self.goal_radius        # :86   进入 3cm 成功圈
reward = -dist                            # :89   每步奖励 = 负距离（密集、连续）
if success:
    reward += self.success_bonus          # :92   +10
    terminated = True                     # :93   成功即结束
truncated = self.step_idx >= self.max_steps  # :94  超时即结束
```

设计要点：
- `-dist` 是**密集奖励**：哪怕没成功，靠近一点就多拿一点。这让梯度有方向，
  是 Reach 能在 1.5 万步内学会的关键。纯稀疏奖励（只有成功才 +1）在这个尺度下会慢得多。
- `terminated`（成功）和 `truncated`（超时）必须分开：Bellman 目标里
  `(1 - done)` 只在真终止时截断未来价值；超时不代表任务失败到底。

### 第二层：SAC 的目标函数（最大熵 RL）

SAC 优化的**不是**单纯的累计奖励，而是「累计奖励 + 策略熵」：

```
J(π) = E[ Σ_t γ^t ( r_t + α · H(π(·|s_t)) ) ]
```

多出来的 `α·H` 项鼓励策略保持随机（探索），α 自动调节。它落地成三个损失
（`stable_baselines3/sac/sac.py`）：

**① 熵温度损失**（`:237`）——调 α，让策略熵贴近 target_entropy：

```python
ent_coef_loss = -(self.log_ent_coef * (log_prob + self.target_entropy).detach()).mean()
```

**② critic 损失**（`:251-267`）——Bellman 回归，带熵修正的目标 Q：

```python
next_q  = min_over_two( Q_target(s', a') )  -  α * log π(a'|s')     # :253-258
target_q = r + (1 - done) * γ * next_q                              # :260
critic_loss = 0.5 * Σ_i MSE( Q_i(s, a), target_q )                  # :267
```

**③ actor 损失**（`:276-279`）——让策略朝「Q 值高、且不小」的方向移：

```python
actor_loss = ( α * log π(a|s)  -  min_over_two Q(s, a) ).mean()      # a ~ π(·|s)
```

注意 actor 的梯度是**穿过 critic 传回去的**：actor 自己没有「对错」标签，
它全靠 critic 给的 Q 值当指南针。所以 critic 先学好、actor 才学得动——
这也解释了为什么 `critic_loss` 先降（0.065→0.001），成功率后涨。

### 实测的三个损失（从 `/tmp/train_full.log` 抓的 3580 个日志块抽样）

| n_updates | actor_loss | critic_loss | ent_coef α |
| --- | --- | --- | --- |
| 292 | -4.55 | 0.0653 | 0.9160 |
| 16990 | -9.44 | 0.0107 | 0.0125 |
| 32083 | -9.70 | 0.0015 | 0.0088 |
| 49876 | -9.75 | 0.0011 | 0.0091 |

怎么读：
- `actor_loss ≈ -9.7` 不是「负损失=坏了」：它约等于 `-min Q(s,a)` 的均值，
  而一局奖励 ≈ +9.9，量级对得上。**actor_loss 越负 = 策略认为未来奖励越高。**
- `critic_loss` 从 0.065 降到 0.001：Q 网络的 Bellman 残差收敛了。
- `α` 从 0.92 降到 0.009：探索自动关掉。这三条一起看，就是「学习发生了」的内部证据。

---

## 4. 状态机指令是怎么一路落到关节和画面上的

`scripts/demo_scripted_lift.py` 的 `LiftStateMachine`（`:68`）是一个**人写的 policy**：
`__call__(obs) -> action`（`:82`）。它和 SAC 的 actor **接口完全相同**——
都是「给观测，返回动作」。区别只在一个是人写的规则、一个是学出来的网络。
这条同构性很重要：阶段 3 把两者都封装成 skill 时，上层 harness 看不出差别。

一个 control step（20 Hz，即每秒 20 步）里的完整链路：

```
MuJoCo 积分出当前状态
        │  obs: robot0_eef_pos / cube_pos / gripper_to_cube_pos ...
        ▼
LiftStateMachine.__call__(obs)            demo_scripted_lift.py:82
        │  按相位算目标点 target；delta = target - eef
        │  action[:3] = clip(delta / 0.05, -1, 1)      :110   （每步最多 5cm）
        │  action[6]  = +1 闭合 / -1 张开               :112-114
        ▼
robosuite OSC 控制器 set_goal(action)      controllers/parts/arm/osc.py:225
        │  把「末端增量」换算成目标位姿（世界系）
        ▼
run_controller()                           controllers/parts/arm/osc.py:403
        │  操作空间控制（Khatib 1987）：把目标位姿误差 → 7 个关节力矩
        ▼
MuJoCo 用这些力矩做物理积分（接触/摩擦/重力都在这一步生效）
        ▼
渲染一帧（离屏 EGL）→ 写进 mp4
```

所以你在视频里看到的每一个动作，都是「状态机的一条 if/else → 一个 7 维向量 →
一次 OSC 求解 → 一组关节力矩 → 一次物理积分」的结果。**视频就是这条链的可视化。**

### 三个产物，三种看法

| 产物 | 看什么 |
| --- | --- |
| `lift_scripted.mp4` | 物理结果：方块真的离桌悬空 |
| `action_trace_ep0.png` | **指令与响应的同步图**：第 1 行 action[0:3] 指令曲线、第 2 行夹爪指令、第 3 行 eef_z/cube_z 与成功线、第 4 行相位色带。色带切换的瞬间 = 指令曲线跳变的瞬间 = 视频里行为改变的那一刻 |
| `keyframes_ep0.png` | 九宫格关键帧，每格标题就是状态机在那一步的完整状态（相位 / 7 维指令 / eef_z / cube_z / lifted），标题颜色 = 相位 |

`action_trace_ep0.png` 上能直接读出的因果：
- `approach` 段：dz=-1.00 打满（全速下降前先抬到预抓取高度时是 +1），dx/dy 先大后小 → 水平对准；
- `descend` 段：dz 变负且幅度收敛 → 慢速接近，防止撞飞方块；
- `grasp` 段：action[6] 从 -1 跳 +1，位移指令趋近 0 → 原地闭合夹爪；
- `lift` 段：dz=+1 打满，cube_z 曲线开始跟着 eef_z 一起涨 → **方块被带走了**；
- cube_z 穿过 `table_z+0.04` 绿虚线的那一步，就是 `info["success"]` 变 True 的那一步。

### 和 RL 的对照（本页的落点）

| | 状态机 | SAC actor |
| --- | --- | --- |
| policy 形式 | 5 个 if/else + 比例控制 | 6→64→64→(mu,log_std) 的 MLP |
| 谁决定动作 | 人写的规则 | 2.4 万个学出来的权重 |
| 能否泛化 | 换任务就要重写 | 换任务要重训，但**写法不用变** |
| 验收方式 | 同一行 `cube_z > table_z + 0.04` | 同一行 |
| 输出接口 | `action: np.ndarray(7)` | `action: np.ndarray(3)`（Reach） |

阶段 2/3 要做的事，就是让「学出来的 policy」逐步替换「人写的 policy」，
而**判定、记录、版本发布这套外壳完全不变**。

---

## 5. 概念 → 代码位置 速查表

| 概念 | 位置 |
| --- | --- |
| 环境奖励 / 终止条件 | `envs/reach_env.py:86-94` |
| 训练入口 / SAC 构造 | `scripts/train_reach.py:143-175` |
| 超参 | `configs/reach_sac.yaml` |
| 独立评测 | `eval/reach_eval.py`、`scripts/eval_policy.py` |
| 采集循环（obs→action→buffer） | `stable_baselines3/common/off_policy_algorithm.py:514` |
| SAC 三个损失 + target 更新 | `stable_baselines3/sac/sac.py:202-290`（α:237 / critic:267 / actor:279） |
| actor 网络与 tanh 压缩 | `stable_baselines3/sac/policies.py:25,167` + `common/distributions.py` SquashedDiagGaussian |
| target_entropy = -dim(action) | `stable_baselines3/sac/sac.py:169-171` |
| 手写状态机 policy | `scripts/demo_scripted_lift.py:68-115` |
| 增量→目标位姿 | `robosuite/controllers/parts/arm/osc.py:225` |
| 目标位姿→关节力矩 | `robosuite/controllers/parts/arm/osc.py:403` |
| 成功判定 | `robosuite/environments/manipulation/lift.py:433-444` |
| 指令-响应同步图 / 关键帧表 | `scripts/demo_scripted_lift.py` 的 `plot_action_trace` / `plot_keyframe_sheet` |
