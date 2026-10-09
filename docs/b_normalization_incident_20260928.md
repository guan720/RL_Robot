# 归一化事故：近常量维被 std 归一化放大 10²~10³ 倍（B 线，2026-09-28）

状态：**已定位根因、已给出因果证据、修复动作在 A 线**。
影响面：所有用 `scripts/train_act_lift.py` / `scripts/export_lift_to_lerobot.py` 归一化
训练出来的 state-obs 策略，包括 A 的 baseline ACT、B 的全部 minibatch 臂。
这份文档解释「learned ACT 0/20」这个悬了很久的问题——**它主要不是能力问题，是数值事故**。

---

## 1. 一句话

`(x - mean) / (std + 1e-6)` 对**近常量维没有下限保护**。Lift 的 state obs 里有几维在
teacher 数据里几乎是常数（std 低至 9.67e-05），闭环一旦偏离 teacher 轨迹，这几维就被
放大到 10³~10⁴ 量级喂进网络，第一层激活炸穿、末层 tanh 饱和，策略退化成 ±1 抖动。
**开环指标完全看不到这件事**，所以离线 val MSE 一路变好、闭环成功率却不动。

## 2. 肇事维（实测，`runs/infra/b_normclip/train_input_range.json`）

| obs 维 | 语义 | teacher 训练集 std | 归一化后训练范围 | 闭环实测 \|x\| 峰值 |
|---|---|---|---|---|
| 9 | `joint_pos_cos[2]` | **9.67e-05** | −5.30 ~ +0.57 | **20402.6**（seed 5007） |
| 11 | `joint_pos_cos[4]` | **9.29e-04** | −4.77 ~ +0.85 | 数千 |
| 7 | `joint_pos_cos[0]` | **6.21e-04** | −3.11 ~ +0.96 | 数千 |
| 28–34 | `joint_acc[0..6]` | 3.8e-02 ~ 1.13 | ±17 ~ ±23.7 | 数千 |

`joint_pos_cos` 对关节角在 0 附近是**二阶平坦**的（cos θ ≈ 1 − θ²/2），所以关节只要基本
不动，这一维的 std 就趋近 0；但闭环里关节稍微一动，cos 的变化被除以 1e-4，直接放大一万倍。
这是「用 std 归一化 + 二阶平坦特征」的必然结果，不是数据脏。

state obs 布局（60 维，2026-09-28 实测，此前仓库里没有成文契约）：

```
[ 0:50] robot0_proprio-state = joint_pos(7) joint_pos_cos(7) joint_pos_sin(7)
                               joint_vel(7) joint_acc(7) eef_pos(3) eef_quat(4)
                               gripper_qpos(2) gripper_qvel(2) + 4 维待确认
[50:60] object-state         = cube_pos(3) cube_quat(4) gripper_to_cube_pos(3)
```

`gripper_to_cube_pos` **在观测里**（末 3 维），对齐所需信息不缺——这一点由 §4 的可辨识性
探针独立证实。

## 3. 因果证据：单变量输入截断

同一个 checkpoint（`runs/infra/b_act_lift_mb_hist1_pinned_seed0/model_final.pt`）、
同一 pinned 题集（seeds 5000–5019）、同一评测器，**唯一变量 = 推理时把归一化输入逐维截到 ±C**：

| C | `success_raw` | 受控成功 | over_lift | flick | 超训练输入范围的帧 | 门禁 |
|---|---|---|---|---|---|---|
| 无截断 | 3/20 | 0/20 | 2 | 1 | **94%**（\|x\|max 20403） | **INVALID** |
| 1.0 | 2/20 | 1/20 | 1 | 0 | 0% | pass |
| **1.5** | 8/20 | **4/20** | 2 | 2 | 0% | **pass** |
| 2.0 | 8/20 | 2/20 | 5 | 1 | 0% | pass |
| **3.0** | **15/20** | 1/20 | 12 | 2 | 0% | pass |
| 4.0 | 7/20 | 0/20 | 7 | 0 | 0% | fail |
| 5.0 | 9/20 | 0/20 | 9 | 0 | 0% | fail |
| 10 | 2/20 | 0/20 | 1 | 1 | 0% | fail |
| 3.0 + dz deadband 0.1 | 14/20 | 3/20 | 10 | 1 | 0% | pass |

产物：`runs/infra/b_normclip/`、`runs/infra/b_normclip2/`，裁定：
`runs/infra/b_normclip2/gate_all.json`。

三个可以从这张表安全读出的结论：

1. **raw success 从 3/20 升到 8~15/20**，方向在所有 C ≤ 3 上一致，不是单点运气。
2. **失效模式整体换类**：无截断时是「漏抓 + 弹射」（15/20 局 `phase_at_end=approach`、
   `max_rise≈0`）；截断后 12/15 变成 `over_lift`——**方块全程在爪里**（`held_at_end=True`、
   `end_phase=hold`），只是抬得停不下来。抓的能力一直都在，是输入炸穿把它盖住了。
3. **C 不是单调的**（1.0→2 局、3.0→15 局、4.0→7 局），所以**不许**把「C=1.5 受控 4/20」
   当成调好的超参报出去。20 局里差 1~4 局本身就在噪声内。推理截断在这里只是**因果探针**，
   不是修复方案。

## 4. 为什么之前三个方向都没打中

在花掉闭环算力之前先做了两个离线探针，它们排除了三种看起来更像的解释：

**(a) 不是欠拟合。** `runs/infra/b_bc_retrain/bc_underfit_probe_hist1_seed0.json`：
minibatch 把梯度步数从 40 提到 5600，`val_mse_all` 从 0.02590 降到 0.00700（好 3.7 倍），
teacher 开爪帧符号正确率 30.9% → 99.8%。**但 dz 的 r² 反而从 0.542 掉到 0.158**。
训练更充分却让某一维变差，这本身就不是欠拟合的形状。

**(b) 不是信息不足（部分可观测）。** `runs/infra/b_observability/identifiability_hist1_seed0.json`：

| 测试 | 结果 |
|---|---|
| T2 `lift` vs 非 `lift`，**只用夹爪已闭合的帧**（最难的别名场景） | recall_lift = **1.000**（56/56），approx AUC = **0.996** |
| T3 `descend` vs 非 `descend`，只用夹爪张开的帧 | recall = **0.993**，acc 0.975 |
| T1 六类 phase 复原 | approach 0.978 / descend 0.986 / lift 0.964 / hold 1.000 |

「该不该抬升」这个决定 dz 的模式，在观测里**几乎完全可分**。所以「ACT 拿到的信息不足」
不成立。（T1 的 `grasp` 召回 0.450、`done` 召回 0.413 是平衡采样改变了先验的结果，
不能读成「不可辨识」；T2/T3 用的是自然先验，才是有效证据。）

**(c) 不是执行侧动作过大。** slew cap ∈ {0.5, 0.25, 0.1}（`runs/infra/b_flick_sweep/`）
与 dz deadband ∈ {0.15, 0.2, 0.3}（`runs/infra/b_dzdeadband/`）共 7 个臂，
**受控成功全部 0/20**。命令幅度不是瓶颈——因为命令本身已经是饱和的 ±1，
问题在网络的**输入**，不在输出。

**(d) 不是样本配比。** 逐维损失加权扫描（T4）把 dz 权重从 1 提到 30，
dz 的 r² 单调变差（+0.238 → −0.839）、正偏单调变大（+0.143 → +0.246）。
丢空转帧（A3/A4）更糟：dz r² 掉到 −5.01。加历史（hist=4）也更糟：dz r² −2.517。

## 5. 剩下的唯一缺陷：hold 段的 dz 正偏 → 无界上升

截断输入之后，失效几乎全是 `over_lift`。逐帧取证
（`runs/infra/b_normclip/clip3.json`，seed 5002）：

```
帧 0-17   dz=-1 正确下降，eef_z 1.018 → 0.840
帧 18-27  在正确高度闭爪，held=True，grip_w=0.0226（夹住 4.4cm 方块）
帧 27-299 held=True 持续 273 帧，方块全程在爪里
          held 期间 dz_cmd 均值 = +0.052，55% 的帧 >0.05，|dz|>0.9 的帧 = 0%
          rise: +0.012(f30) → +0.060(f40) → +0.099(f60) → +0.128(f200) → +0.154(f299)
```

teacher 的 `LIFT_TARGET = 0.05`，到 0.05 就该转入 `hold` 输出 dz=0。策略**没有停止条件**。
算术对得上：+0.052 的动作单位 = +2.6 mm/控制步，260 帧积分 ≈ +0.68 m 指令量，
实际上升 0.14 m（其余被控制器动力学吸收）。这就是离线测到的 dz 正偏
（全帧 +0.111、done 帧 +0.143、任务相关帧 +0.219）在闭环里的样子。

**为什么会有正偏**：teacher 的 `lift` 段 dz 恒为 **+1（饱和）**，而 `hold`/`done` 段 dz 恒为 0，
两者的可观测差异只在 `cube_z` 绝对值（hold 的触发条件是 `cube_z > z0 + 0.05`，
而 z0 不在观测里）。T2 测到 lift 的 precision 只有 0.30 —— 边界确实薄。
MSE 回归在有歧义的区域输出**条件均值**，lift 的 +1 把均值往上拉，于是 hold 段
得到一个小的正 dz。这不是 bug，是「用确定性回归去拟合一个多峰目标」的必然结果。

## 6. 修复建议（按优先级，前两条在 A 线）

1. **训练侧给 std 加下限，并且训练时同样截断。** `scripts/train_act_lift.py:36`
   ```python
   std = np.maximum(x.std(0), 1e-2 * np.maximum(np.abs(x).max(0), 1e-3))   # 相对下限，不是绝对常数
   x = np.clip((x - mean) / std, -C, C)                                    # 训练与推理必须同一 C
   ```
   关键是**训练时也截断**——只在推理截断会造成 train/inference 分布不一致
   （本次 clip3 之所以有效，恰恰是因为它把输入压回网络见过的范围，但网络是在
   未截断分布上训的，所以仍留 +0.052 的 dz 偏置）。
2. **拆掉 lift 段的动作饱和。** teacher `demo_scripted_lift_rs.py:99` 的
   `target = eef + [0,0,0.3]` 让 dz 恒为 +1；改成一个温和的固定上升量
   （例如 `+0.01` → dz≈+0.2），lift 与 hold 的命令幅度就可区分，
   歧义区的条件均值不再是灾难。这是**示范侧**修复，成本最低、最可能直接消掉 over_lift。
3. **把 rise 相对量放进观测**（`cube_z − z0`，或直接给一个 z 目标），
   从根上消掉 lift↔hold 的歧义。属于 obs 契约变更，要和 A 一起定。
4. 推理侧截断**只作为探针保留**（`scripts/b_eval_act_lift_v1.py --clip-norm-input`），
   不得作为交付能力。它是复合 policy 的一部分，按 v4「复合 policy ≠ 底模变强」必须整体报告。

## 7. 外溢：LeRobot 线不会自动修掉这个缺陷

`scripts/export_lift_to_lerobot.py:30` 用的是同一个 `std + 1e-6`；导出的
`runs/infra/lerobot_act_lift_state_overfit/normalization.npz` 里 dim 9 的 std 实测
**9.696e-05**，与本文一致。

LeRobot 官方 `processor/normalize_processor.py:335` 的 MEAN_STD 分支同样是
`denom = std + self.eps`（`eps = 1e-8`，见同文件 :94），**没有下限保护**；
只有 MIN_MAX 分支在 `denom == 0` 时才替换成 eps（:350-354）。

所以「迁移到官方 LeRobot ACT」不会自动解决这个问题。A 线在 LeRobot 侧要么改用
MIN_MAX 归一化，要么在 dataset 统计里对这几维手工设下限，要么在 obs 里去掉
`joint_pos_cos/sin` 这类二阶平坦特征（它们与 `joint_pos` 冗余）。

## 8. 门禁侧已落地的防线

`scripts/b_gate_controlled_success.py` v1.1 新增**策略输入契约**检查：
评测产物若带 `norm_input_blown_frames_frac`（由
`scripts/b_eval_act_lift_v1.py --record-input-blowup` 写出），
超过 `INPUT_BLOWUP_TOL = 0.05` 时门禁直接判 **`INVALID`（measurement_invalid）**
而不是 `FAIL`——**测量无效与策略失败必须分开**，否则会把数值事故当成能力上限，
这正是过去几天发生的事。实测无截断臂 94% 超界 → INVALID；clip3 臂 0% → 正常裁定。

## 9. 作废清单

以下产物的「成功率」是在输入契约违例下测得的，**不得用于任何能力主张**：

- `runs/infra/act_lift_k4_state_hist1_seed0/`、`act_lift_k4_state_hist4_seed0/`、
  `act_lift_k4_state_seed0/`（A 的 baseline ACT 闭环评测）
- `runs/infra/b_act_lift_mb_hist1_seed0/`（另受 robosuite 1.5.1 影响，见
  `docs/b_reproducibility_incident_20260928.md`）、`b_act_lift_mb_hist4_seed0/`
- `runs/infra/b_act_lift_mb_hist1_pinned_seed0/` 的**无截断**闭环评测
  （`runs/infra/b_flick_sweep/mb_*.json`、`runs/infra/b_dzdeadband/*.json`）
  —— 这些是有效的**负结果**（证明执行侧约束无效），但不是能力测量
- checkpoint 本身**不作废**：同一 ckpt 加输入截断即可产生有效测量，
  但按 §6.1 重训之后必须重新标定

离线探针（`b_bc_underfit_probe.py`、`b_probe_dz_identifiability.py`）的结论**不受影响**：
它们在开环 teacher 分布内评测，输入本来就没有越界。
