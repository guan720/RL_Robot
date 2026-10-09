# B → A 交接单（2026-09-28 晚）

发出方：B（门禁与可复现性线）。接收方：A（policy/ACT + LeRobot 全线）。

**边界声明**：本单只列 A 命名空间里需要改的东西。B 不会去改
`scripts/train_act_lift.py`、`scripts/eval_act_lift_truth.py`、`scripts/audit_residual_lift.py`、
`scripts/demo_scripted_lift_rs.py`、`scripts/export_lift_to_lerobot.py` 或 LeRobot 侧任何文件。
B 已落地的部分见 §5，A 不需要重做。

优先级：**交接单 1 > 交接单 2 > 交接单 3**。1 和 2 都阻塞监管 P1 门禁。

---

## 交接单 1（阻塞）：按归一化事故重训，三项一起改

根因与完整证据链见 `docs/b_normalization_incident_20260928.md`（§2 肇事维、§3 单变量因果、§6 修复建议）。
这里只给「改哪一行」和「B 怎么验收」。

### 1.1 三处改动

| # | 文件:行 | 现状 | 要改成 |
|---|---|---|---|
| a | `scripts/train_act_lift.py:36` | `std=x.std(0)+1e-6` | `std = np.maximum(x.std(0), 1e-2*np.maximum(np.abs(x).max(0),1e-3))`，**并且训练时对 `(x-mean)/std` 施加与推理同一个 C 的截断** |
| b | `scripts/demo_scripted_lift_rs.py:99` | `target = eef + np.array([0.0,0.0,0.3])` | 温和固定上升量（如 `+0.01` → dz≈+0.2），使 lift 段 dz 不再恒等于 +1 |
| c | `scripts/export_lift_to_lerobot.py:30` | `observation_std=arr.std(0)+1e-6` | 同 (a) 的相对下限；LeRobot 侧另见 §1.3 |

为什么 (a) 必须「训练时也截断」：只在推理截断会造成 train/inference 分布不一致。
本轮 clip3 之所以能把 raw success 从 3/20 抬到 15/20，是因为截断把输入压回网络见过的范围；
但网络是在**未截断**分布上训的，所以仍留下 hold 段 dz 正偏 +0.052（离线测 +0.111/+0.143），
= +2.6 mm/控制步，260 帧积分 ≈ +0.68 m 指令量；闭环实测表现为 max_rise 0.156–0.393
（上限 0.15）—— 这正是 clip3 有 12/20 局 over_lift 的原因。

为什么 (b) 是成本最低的一击：`:99` 的 `+0.3` 经 `:111` 的 `np.clip(delta/0.05,-1,1)` 后 dz 恒为 +1
（0.3/0.05=6 → 截到 1），而 `hold` 段（`:103`）dz=0。同一批近邻观测对应两个截然不同的 dz 目标，
确定性回归只能输出条件均值 → 系统性正偏。去掉饱和后这个多峰冲突直接消失。

### 1.1bis 重要：(a) 的 std 下限**只修得了一半**，(b) 不是可选项

B 的协变量漂移探针重跑后（`runs/infra/b_covariate_shift/covariate_shift.json`，`probe_build=a98dfce9b4e2`）
把闭环输入爆炸分成两种**不同机制**，它们需要不同的修复：

| 机制 | 维（60 维 state obs 布局见事故文档 §2） | teacher std | 闭环 \|x\| 峰值 | 相对下限 `1e-2·max\|x\|` 能修吗 |
|---|---|---|---|---|
| ① 平坦特征放大 | 9 `joint_pos_cos[2]`、11 `[4]`、7 `[0]`、38 `eef_quat[0]` | 9.7e-05 ~ 1.7e-03 | 19320 / 2125 / 1348 / 1138 | **能**，正好命中这 4 维（放大倍数降 6~103 倍） |
| ② 真实闭环发散 | 32 / 28 / 34 / 30 = `joint_acc[4/0/6/2]` | 3.8e-02 ~ 1.13（本来就设定了 23.7 这个训练上界） | 1787 / 1314 / 1130 / 529 | **不能，也不该** |

含义：

- 60 维里只有 **4 维**会被 (a) 的相对下限抬升。`joint_acc` 的 std 本来就大，不会被抬升，
  所以 (a) 做完之后，闭环输入在 dim 28/30/32/34 上**仍然**是训练上界的 22~75 倍。
- 机制 ② 不是归一化问题，是策略真的离开了数据分布：它是 §1.1(b) 那条 dz 正偏把 `eef_z`
  从 0.83 积分漂到 1.44 的**下游后果**。任何归一化改动都治不了它。
- 因此 **(b) teacher 去饱和是唯一针对机制 ② 的修复**，不是「成本最低的可选优化」；
  (a) 的训练时同截断则是把机制 ② 对网络的影响**限幅**的兜底。三项要一起做，
  只做 (a) 会留下 dim 28–34 这条通路。
- 若 (b) 之后仍想进一步压制机制 ②，优先考虑**从 obs 里去掉 `joint_acc`**（二阶导、数值噪声大，
  且与 `joint_vel` 冗余），而不是继续调下限常数。这属于 obs 契约变更，需 A/B 共同确认后登记。

> 附带更正：该探针前两轮的「OOD 99.3%、首次越界帧 = 2」属**度量伪影，不得引用**
> （距离被少数维主导，探针现已自检并输出 `ood_numbers_citable=false`）。
> 唯一可引用的是不经度量的直接测量：平均 **93.3%** 的帧超出训练归一化上界，`|x|max = 19320`（上界 23.7）。
> 详见 `docs/b_agent_review_20260928.md` §7.6。
### 1.2 不要做的事

- **不要把某个 clip 值当成调好的超参**。实测 raw success 对 C 非单调：
  C=1.0→2、1.5→8、2.0→8、3→15、4→7、5→9、10→2、24→4（`runs/infra/b_normclip2/gate_all.json`）。
  截断是**探针**，不是交付能力；按 v4「复合 policy ≠ 底模变强」，任何带截断的结果都必须整体报告为复合 policy。
- **不要用 `success_raw` 选臂**。见 §4：raw 最优的 clip3 在受控口径下只有 1/20，
  受控最优是 clip1.5 的 4/20。用 raw 选臂会选错。
- 不要只补示范条数或加训练步数。已排除欠拟合（梯度越多 dz 越差）、信息不足
  （lift-vs-rest 在夹爪闭合子集 recall_lift=1.000 / AUC 0.996）、执行侧动作过大
  （slew/deadband 7 臂全 0/20）、样本配比（dz 加权/丢空转帧/hist4 全变差）。

### 1.3 LeRobot 侧不会自动修好

`/root/venvs/lerobot_act/.../lerobot/processor/normalize_processor.py:335` 的 MEAN_STD 分支是
`denom = std + self.eps`，`eps` 默认 `1e-8`（同文件 `:94`），**没有下限保护**；
只有 MIN_MAX 分支在 `denom == 0`（恰好为零，不是近零）时才替换成 eps（`:350-354`）。

实测 `runs/infra/lerobot_act_lift_state_overfit/normalization.npz` 里 dim 9 的 std = **9.696e-05**
（放大倍数 1.03e4），与本地训练侧同源。所以迁移到官方 LeRobot ACT **不会**绕过这个缺陷。
**可选修复只有两条**（第三条已被监管作废，见下）：
在 dataset 统计里对低 std 维设**相对**下限（A 已实现：`scripts/a_patch_dataset_std_floor.py`），
或从 obs 里去掉 `joint_pos_cos`、`joint_pos_sin` 这类二阶平坦且与 `joint_pos` 冗余的特征。
`eps` 是 `NormalizerProcessorStep.from_lerobot_dataset(..., eps=...)` 的显式入参（`:419`），可直接调，
但 eps 是**绝对**常数、不随各维量级缩放，所以它不是相对下限的替代品。

> **更正（本单初稿的错误，已按监管 增补二 §0 作废）**：初稿把「改用 MIN_MAX 归一化」列为可选修复之一。
> **不成立**：MIN_MAX 分支只在 `denom == 0`（恰好为零）时才替换成 eps（`:350-354`），
> 而近常量维的 `max − min` 不为零、只是极小，同样会被放大 —— MIN_MAX **不免疫** L1。
> 且实测 A 的全部官方臂（含 `trimdone0_minmax_*` 与 `trimdone0_minmax_k2_*`）的
> `normalization_mapping` 都是 `STATE=MEAN_STD / ENV=MEAN_STD / 仅 ACTION=MIN_MAX`，
> 而 L1 肇事维在 **STATE 侧**（dim 7/9/11），因此这些臂对 L1 同样暴露。
> MIN_MAX 的增益应归因于 **ACTION 侧退化解的消除**，与 L1 无关。
> 依据：`rl_harness_supervision/supervisor_memo_20260928.md` 增补二 §0。

低 std 维完整清单（std<1e-2，共 11 维；中位数 std=0.0256，所以要用**相对**下限而不是绝对常数）：

| dim | std | 1/std | | dim | std | 1/std |
|---|---|---|---|---|---|---|
| 9 | 9.696e-05 | 1.03e4 | | 41 | 4.221e-03 | 237 |
| 7 | 6.209e-04 | 1.61e3 | | 46 | 4.642e-03 | 215 |
| 11 | 9.293e-04 | 1.08e3 | | 47 | 4.707e-03 | 212 |
| 38 | 1.675e-03 | 597 | | 48 | 8.983e-03 | 111 |
| 58 | 2.076e-03 | 482 | | 49 | 9.033e-03 | 111 |
| 23 | 9.680e-03 | 103 | | | | |

### 1.4 B 的验收方式

重训后把评测产物路径给 B，B 用 `scripts/b_gate_controlled_success.py`（v1.1）出裁定。
主指标是 **controlled_success**（policy_independent 账），不是 success_raw。
产物若带 `norm_input_blown_frames_frac` 且超界帧 >5%，门禁判 **INVALID / measurement_invalid**
（测量无效 ≠ 策略失败），这种产物不进任何能力主张。
建议重训时用 `scripts/b_eval_act_lift_v1.py --record-input-blowup` 记录该字段，好让门禁能自动判有效性。

---

## 交接单 2（阻塞）：补 2 个门禁字段，恢复 residual 臂裁定

v1.1 门禁要求每局输出 `final_rise` / `held_at_end`（外加 `phase_at_end` / `terminal_kind` 更好）。
缺字段时门禁**不会**假阳性否决（v1.0.1 已修），但会降为 `provisional_pass` 且 gate FAIL ——
即「无法证明局末仍夹持」，不能计入 P1 主张。

| 文件 | 现状 | 需要 |
|---|---|---|
| `scripts/audit_residual_lift.py` → `runs/20260924_142702_sac_lift_residual_grasp_lift/audit_truth20.json` | row 字段为 `failure_phase/grasp_verified/max_rise/phase_trace/phases/residual_*/seed/steps/success_*`，**无** `final_rise`/`held_at_end` | 补 2 字段即可恢复裁定；当前被判 20 局 `provisional_pass`、gate FAIL |
| `scripts/eval_act_lift_truth.py:38` | 只有 `max_rise`、`grasp_verified`（= held_ever）、`phase_trace`、`failure_phase` | 补 `final_rise`/`held_at_end`/`phase_at_end`/`terminal_kind` |
| `scripts/eval_lerobot_act_runtime.py:334-337` | **已补齐**（`final_rise`/`held_at_end`/`terminal_kind`；docstring `:23` 已声明门禁字段契约） | 无需改动，可作为参考实现 |

**参考实现**：`scripts/b_eval_act_lift_v1.py:182-192`（B 自己的评测器，字段语义与门禁一一对应）：

```python
held_at_end = bool(truth())                       # 末帧真值，不是 ever-or
final_rise  = float(raw["cube_pos"][2]) - z0      # 末帧相对初始高度
"phase_at_end": (phases[-1] if phases else "unknown"),
"terminal_kind": terminal_kind,                   # truncated_horizon / terminated_success /
                                                  # terminated_failure / preempted / unknown
```

两个坑：

1. `grasp_verified` 现在是 **held_ever**（任一帧夹住过），语义上**不等于** `held_at_end`。
   两者都要保留为独立字段，不能用后者覆盖前者 —— 门禁两个都读
   （`held_ever` 用于 C2 抓取真实性，`held_at_end` 用于 C4 局末夹持）。
2. `terminal_kind` 不要把「跑满 horizon 的截断」标成 `terminated_failure`。
   门禁会自检这一条（`terminal_semantics.suspect_truncation_labeled_as_failure`）并报 warn。
   按 v4：unknown / preempted 既不是成功也不是失败，一律移出分母单独报告。

---

## 交接单 3：T17 goal 贯通，A 侧 2 项阻塞

完整 7 项清单（含 4 项阻塞）在 `runs/infra/b_t17/t17_precheck.json` 的 `to_wire_goal_for_real`。
A 侧两项：

1. `scripts/run_act_lift_runtime_failure_audit.py:36,39` —— `goal_id` 硬编码 `'lift'`。
   真贯通时它必须来自任务定义并随 A↔B 换向而变，且换向要与 epoch 一起进账本
   （黄金值 E6 要求 goal/epoch 不相容与「晚到」作为**两个独立**拒绝理由分别记录）。
2. `scripts/train_act_lift.py` —— policy 目前不接收 goal。共享 πθ 要支持 A↔B，
   必须把 goal 加进输入，**并且 BC 采集时就要按 goal 分组**；
   否则事后加 goal 输入也没有可学的差异（同一段示范里两个 goal 的动作完全一样）。

B 侧已给出 T17 的正确断言形态与「有牙」证明：`scripts/b_selfcheck_goal_conditioning_t17.py`
（1 个参考实现 + 6 个故意写坏的实现，5 个能过常规维度检查但全被 T17 抓住，
第 6 个因单 goal 词表连测试都构造不出来、被 T17 明确挡下）。
该裁定自身经变异测试验证非恒真：`scripts/b_selfcheck_t17_mutation.py`（6/6 通过）。
C 侧另有 3 项（`harness/queue_td_learner.py:65,135,290`），B 会单独同步给 C。

---

## 4. clip 扫描的重判总表（v1.2 判据；A 的实验结论需要据此修正，且必须连 §4.1 一起读）

20 局 pinned seeds 5000–5019，来源 `runs/infra/b_normclip2/gate_all.json`。
**构建指纹以该产物内的 `gate_build` / `gate_spec_sha256` 字段为准**，本文不写死哈希
（教训：门禁每改一次，写死在文档里的指纹就过期一次，本轮就同时存在过
`800e1d08a174` / `28290b9c1b25` / `22a7d92bec0a` 三个值，没人能判断哪份裁定算数）。
重判由 `scripts/b_regate_all.py` 一键完成；本表数字与产物逐臂核对一致。

| 臂 | raw | **ctrl** | over_lift | flick | insuff | gate | 备注 |
|---|---|---|---|---|---|---|---|
| noclip | 3 | 0 | 2 | 1 | 0 | INVALID | 输入契约违例（94% 帧超界），测的是数值事故 |
| clip1.0 | 2 | 1 | 1 | 0 | 0 | PASS | |
| **clip1.5** | 8 | **4** | 2 | 2 | 0 | PASS | **受控口径最优** |
| clip2.0 | 8 | 2 | 5 | 1 | 0 | PASS | |
| clip3 | **15** | 1 | 12 | 1 | 1 | PASS | **raw 最优，但 12/20 是 over_lift** |
| clip4.0 | 7 | 0 | 7 | 0 | 0 | FAIL | no_controlled_success |
| clip5 | 9 | 0 | 9 | 0 | 0 | FAIL | no_controlled_success |
| clip10 | 2 | 0 | 2 | 0 | 0 | FAIL | v1.2 前误记为 1 over_lift + 1 flick |
| clip24 | 4 | 0 | 4 | 0 | 0 | INVALID | 输入契约违例 |
| clip3+dzdb0.1 | 14 | 3 | 10 | 1 | 0 | PASS | dz 死区 0.1 把 ctrl 从 1 抬到 3 |
| clip3+dzdb0.2 | 14 | 1 | 12 | 1 | 0 | PASS | 死区 0.2 反而更差 |

`insuff` = `insufficient_lift`（v1.2 从 `flick` 里分出来的「夹住了但没抬够」）。
**A 请注意这一列的读法**：它与 `over_lift` 是同一个变量 dz 的相反方向，
指向的修复动作完全不同 —— `flick` 才是真脱手，`insuff` 不是。

### 4.1 v1.2.1 的重要更正：这张表里**没有一个**干净的 base policy 测量

门禁 v1.2.1 修掉了一个标注缺陷：推理期对归一化输入截断（`--clip-norm-input`）
也是执行侧介入，必须计入 `composite_policy`。此前只读 `execution_constraints`，
而 B 的评测器把这个开关写在 `input_constraints.clip_norm_input`，于是**上表 10 个 clip 臂
全部被标成 `composite_policy=false`**，门禁那句「裁定对象是 policy+约束，不是底模」
一次都没打印过。修正后逐臂核对（`runs/infra/b_normclip2/gate_all.build_cd96d1cd94c0.json`
→ `gate_all.json`）：标注字段变化 **18 处**，`gate_pass` 与四类失效计数变化 **0 处**。

由此得到一条必须写进结论的话：

> 上表 11 个臂里，10 个是复合 policy（`input:clip_norm_input`，其中 2 个另加 `exec:dz_deadband`），
> 剩下 1 个 `noclip` 是 `INVALID`（输入契约违例）。
> **既非复合、又测量有效的臂 = 0 个。**

所以这次 clip 扫描回答的问题是「**加了输入截断之后，哪个截断幅度最好**」，
不是「base policy 有多好」。特别是 `clip1.5` 的「受控口径最优 4/20」——
它是 `policy + 截断` 的成绩，**不得**作为底模能力引用。
干净的 base policy 闭环测量目前只存在于 A 的官方臂
（`execution_constraints` 为空、`input_contract.status=verified_ok`）。

规格依据：`docs/b_controlled_success_v1_20260928.md` §2.8。

### 4.2 顺带量到的一个 A 侧事实：动作侧饱和率接近 100%

A 的官方产物已经在记 `clip_events`（动作反归一化后 clip 到 `[-1,1]` 的次数）。
按 `Σclip_events / Σsteps` 汇总 7 个 gatefields 臂：

| 臂 | clip_rate | 逐维输入越界率 | 全局越界率 |
|---|---|---|---|
| `train24_lr1e-4_actionminmax_s20k` | 0.928 | 0.934 | 0.000 |
| `train24_lr1e-4_s20k` | 1.000 | 0.980 | 0.000 |
| `train24_lr1e-5_actionminmax_s20k` | 0.998 | 0.217 | 0.000 |
| `train24_lr1e-5_actionminmax_s20k_seed1` | 0.996 | 0.276 | 0.000 |
| `train24_lr1e-5_actionminmax_s20k_seed2` | 0.997 | 0.221 | 0.000 |
| `train24_lr1e-5_actionminmax_s40k` | 0.996 | 0.345 | 0.000 |
| `train24_lr1e-5_s20k` | 0.403 | 0.397 | 0.000 |

两点值得 A 自己判断（B 不改 A 的文件，也不替 A 定性）：

1. `[-1,1]` 是 robosuite 动作空间的固有边界，clip 本身属于环境接口、不算「额外加的约束」；
   但**每帧都触发**意味着策略在持续命令越界动作，实际执行的轨迹被饱和强烈塑形
   （幅度上 `max_preclip_abs_action≈1.19`，超界约 19%，不算剧烈）。
   这与「抬起高度不够」是否同源，A 比 B 更有条件判断。
2. **全局越界率 0.000 与逐维越界率 0.22~0.98 并存**：门禁现在只强制全局规则
   （`max|x| > 23.85` 才算 blown），所以这批臂全部 `verified_ok`。
   但 23.85 是「训练期所有维度的全局最大归一化值」，是个**很松**的尺子；
   逐维口径下这批臂其实大面积超出自己的训练范围。
   要不要把逐维口径也纳入门禁，属监管裁决（改判据会动所有历史臂），B 只报事实。

三条可直接用的结论：

- **raw 与 ctrl 的最优臂不是同一个**（clip3 vs clip1.5）。任何以 success_raw 为主指标的选臂结论都要重判。
- clip3 的失效模式是 **over_lift（方块全程在爪里、只是抬太高）**，不是 flick。
  这与 §1.1(b) 的 teacher dz 饱和诊断一致：修 (b) 应当直接把 over_lift 转成受控成功。
- dz 死区也是非单调的（0.1 有效、0.2 变差），同样不得当超参固化。

---

## 5. B 侧已落地（A 不需要重做，但需要知道）

- **门禁 v1.1**：`scripts/b_gate_controlled_success.py` —— 拆分 over_lift / flick、
  `phase_trace` 双语义分流、输入契约检查（INVALID ≠ FAIL）、terminal_kind 截断/失败混淆自检、
  三套账分母分离。规格：`docs/b_controlled_success_v1_20260928.md`。
- **门禁构建指纹**：每份裁定 JSON 带 `gate_build` / `gate_spec_sha256`。
  留档裁定若 build 不同必须重判（实测旧 `gate_v11.json` 的 clip24 条目出自加入输入契约检查之前的构建，
  重判后从 FAIL 翻成 INVALID）。旧产物已备份为 `runs/infra/b_normclip2/gate_all.prev_build.json`。
- **可复现性自检 12/12 全绿**：`scripts/b_selfcheck_reproducibility.py`
  （`runs/infra/b_reproducibility/selfcheck.json`）。本轮修掉三个门禁自身缺陷：
  环境缺失时不再抛 IndexError 而是给可读裁定；L0-c 从恒真断言改成真比对 size/mass/hash；
  L0-h 增加作废确认清单 `configs/b_obs_dim_mismatch_ack.json`（4 个 53 维 ckpt 作废，
  **A 的 hist4=240 兼容、不在作废名单**，新失配照样 FAIL）。
- **`requirements.lock.txt` 已生成**（`robosuite==1.5.2`，与 pin 一致，L0-g 转 PASS）。
  `scripts/setup_env.sh` 现在写 lock 而**不覆写** pin 文件。
- **黄金值**：`docs/b_golden/async_td_golden_v1.json`（附录 02 §9 六算例手算 + 8 条跨例不变量），
  自校验 `scripts/b_selfcheck_golden_values.py` 47/47 通过。这是给 C 自证用的规格，A 不需要看。

---

## 6. 需要用户决策的两项 —— **均已由用户裁定，本节仅作历史留档**

1. ~~**`work/decisions/` 的写入位置**~~ → **已解决**：用户裁定 **DR-001** 允许在仓库根建镜像目录
   `work/decisions/` 并写入（最小写入：只放路线变更 / 口径裁定 / 作废与 ack 登记）。
   B 的工程扩展已登记为 **DR-005「继续停车」**，但停车理由已从「无登记入口」变成「**证据反转**」
   （v1.3 重判后 `flick` 可引用只有 2 局，主失效模式是 `insufficient_lift` 235 局，
   连续性正则 / slew limit 打的不是现在的靶）。详见 `docs/b_agent_review_20260928.md` §9.7。
2. ~~**是否 `git init`**~~ → **已解决**：用户裁定 **DR-002**（许可 + 4 条护栏）与 **DR-003**
   （B 登记的 `.gitignore` 纳管范围，8 条决定）。已 `git init` 并完成首次提交
   `0137b33ab1a490f590d97305fd0619de270b213a`（228 文件）。
   **A 需要知道的两条纪律**：(a) `runs/` **不纳管**，所以被引用的裁定产物要在受版控文本里登记
   `sha256 + gate_build + gate_spec_sha256 + git_commit`；(b) **单写者**：只有 B 执行 git 写操作，
   A 只读 `git log` / `git status`，不要并发跑任何 git 写命令（避免 `index.lock` 竞争与提交归属混乱）。
   pre-commit 有体积闸（`scripts/b_git_size_guard.py`，>2 MB 的 tracked 文件会被拒），
   A 若要纳管大产物请先找 B。

---

## 7. v1.3 交接：A 的下一个靶是 `insufficient_lift`，数字已备齐

门禁已升 **v1.3**（`gate_build=4f20b3ec9130`、`spec=c9303525112a`、裁定带 `git_commit`）。
§4 那张 clip 表是 **v1.2 判据**下的，仍可按 §4.1 的限定引用；**权威口径请一律取
`runs/infra/b_official_arms/reclassification.json`（v1.3 / 48 臂）**。

### 7.1 v1.3 对 A 的三条实际影响

| 变化 | 对 A 的影响 |
|---|---|
| phase 词表矛盾 → 行 `unjudged` + 文件 `INVALID`（裁定 1，规格 §2.9） | 评测器输出 `phase_at_end` 时，词表必须与 `phase_trace` 自洽。实测 48 臂官方集 **0 例**矛盾，所以 A 现有产物不受影响；新评测器要注意 |
| `not_applicable` 必须走带牙声明路径（裁定 2，§2.10） | 无归一化策略要声明 `not_applicable` 时，**规格 / 训练范围 / 闭环**三项缺一不可，否则 `INVALID` 而不是「通过」 |
| `blown_metric_impl` 指纹缺失 → **拒判**（§2.12 / DR-006） | 新评测产物必须回显 `blown_metric_impl` + `blowup_threshold` + `threshold_provenance`。祖父条款只覆盖 cutoff `2026-09-28T21:27:24+08:00` 之前的 69 条历史臂，**不覆盖新产物** |

### 7.2 主靶量化：235 局 `insufficient_lift`，中位只差 16 mm

v1.3 起每份产物带 `insuff_diagnostic`（「差多少」，不再只有计数），池化结果：

| 量 | 值 | 量 | 值 |
|---|---|---|---|
| 局数 / 臂数 | **235 / 34** | `final_rise` 中位数 | **0.0236 m** |
| p10 / p90 | 0.01024 / 0.0367 | 与门槛 `C5=0.04` 的中位差 | **0.0164 m** |
| min / max | 0.0087 / 0.0399 | 最好一局只差 | **0.0001 m** |
| 差 <5 mm | **41 局（17.4%）** | 差 <10 mm | 75 局（31.9%） |

**读法（这条最重要）**：82.6% 的 insuff 局差得**比 5 mm 多**，中位差 16 mm ≈ 方块全高（43.4 mm）的 38%。
所以主靶是**能力**（抬不够高），不是阈值。A 的 B-3 靶子应该盯「把 `final_rise` 的中位数从 0.0236 抬过 0.04」，
而不是盯 C5。

C5 杠杆表（改阈值能翻多少局；**B 不改 C5**，此表是给 D 裁决用的，A 引用时须带敏感带）：

| C5 | 依据 | 翻成受控成功 | 占比 |
|---|---|---|---|
| **0.04**（现行） | `0.92 ×` 方块全高 `0.04341` | 0 | 0% |
| 0.035 | 现行 −0.005（敏感带下沿） | 41 | 17.4% |
| 0.03 | `0.69 ×` 全高 | 75 | 31.9% |
| 0.0217 | `0.50 ×` 全高 | 134 | 57.0% |
| 0.0085 | robosuite `_check_success` 的相对高度等效阈 | 235 | 100% |

insuff 最多的 6 个臂（各 12–13 局）：`train24_minmax_k2_lr1e-5_s20k_seed1`、
`trimdone0_minmax_lr1e-5_s20k_seed0`（及其 `_replan1` / `_replan2`）、
`trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed1`、`trimdone0_minmax_kl1_s20k_seed0`。

### 7.3 一个**即将**影响 A 的预登记（现在不动手）：teacher 去饱和

`docs/b_teacher_desaturation_prereg_20260928.md` + **DR-004** 已在 A 重采数据**之前**把门框钉死
（15 条判据，仪器 `scripts/b_teacher_dz_audit.py`）。要点：

- 改动是**单变量**：只准动 `scripts/demo_scripted_lift_rs.py:99` 的 `0.3 → 0.01`
  （**A 的文件，A 动手**）。`LIFT_TARGET = 0.05`、夹爪语义行、其余五个相位逻辑**不许同时改** ——
  判据 T4/T5 会用机器比对挡住夹带（`hold` 段 `dz` 仍恒 0；非 `lift` 相位逐维统计与帧数 `1e-6` 内不变）。
- **锚点**：`RISE_CAP` 要按 `floor_to_0.01(2 × 新 base-only mean_max_rise)` 重算
  （判据 A0 要求该规则套旧数据必须精确复现任值 `0.15`）；`FINAL_RISE_MIN = 0.04` **不动**
  （几何锚，不是 teacher 锚）。
- **A 要多跑一次评测**：同一冻结 ckpt 跑 `--horizon 300` 与 `--horizon 600`（两个评测器都已有该参数，
  零代码改动）。判据 B3 用它区分「因为停住了所以有界」和「因为 horizon 用完所以还没漂出去」——
  命令幅度缩 5× 后，一个**不停**的策略也可能在 300 步内不越 `RISE_CAP`，从而被现有 C3 判成受控成功。
  这是本次最可能的假阳性通道。
- **排序**：DR-004 现在**不生效**，与 A 自己的 `docs/a_bimodal_divergence_preregistration_20260928.md` §9
  一致（双峰有答案前不做 L2 修复）。放行条件：R1/R2 结论出炉 + D/用户放行 + A 线 in-flight 评测收尾。

### 7.4 B 侧本轮新增（A 不需要重做）

- `scripts/b_teacher_dz_audit.py`（teacher/锚点验收仪器；已锁旧 teacher 基线并跑通负控制：
  用未修改的旧 teacher 跑 check → 退出码 1，FAIL 的恰好是本次应当改变的 T1/T2/A4 三条）
- `scripts/b_archive_historical_rulings.py`（63 份历史裁定 / 114 条臂级记录归档，一律 `citable=false`；
  并修掉「8 个孤臂」假信号 → 实为 4 条 blindfix 改名 + 4 条 clip 探针，**真孤臂 0**）
- `scripts/b_blown_impl_registry.py` + `configs/b_blown_impl_grandfathered.json`（69 条，`--verify` 69/69）
- `scripts/b_selfcheck_gate_mutation.py`（5/5 变异被抓，防「门禁自检恒绿」）
- `scripts/b_git_size_guard.py`（pre-commit 体积闸，7/7）
- `docs/b_handoff_to_c_20260928.md`（T17 的 C 侧 3 项；其中 A 侧 2 项阻塞仍在本文件交接单 3）

---

## 8. 回复 A 的移交：裁定 14 已在门禁 **v1.4** 落地（含一处 B 主动收窄，已升级 D）

回应 `docs/a_handoff_to_b_gate_vocabulary_20260928.md`。新指纹：**v1.4 / `gate_build=b9379fdb1089` /
`spec=132fceb89f68` / `git=3615c8e`**。规格 §2.16 与 §2.16.1，登记 **DR-007**。

### 8.1 你的 12 份算例逐条对齐，回归违例 0

| 方向 | 你的期望 | v1.4 实测 |
|---|---|---|
| §4.1 partial 5 臂 | `flick=0`、`unjudged=11 / 3 / 2`、`insuff=0`；`train24_lr1e-4_s20k` 与 `..._seed1` 全 0 **不得新增** | ✅ `n_labels_abstained = 11 / 3 / 2 / 0 / 0`，合计 **16 局**，与 DR-D09 的独立复算一致 |
| §4.1 `seed2` 的 `provisional_pass` | 通道**不动** | ✅ `prov=1` 保留 |
| §4.2 strict 5 臂 | `insuff 11 / 3 / 2`、`seed2` 的 `ctrl=1`、`gate_pass=True` | ✅ 逐臂一致，`n_labels_abstained=0` |
| §4.3 residual 两臂 | `pre_phase_trace` → `unjudged=20`；`with_phase_trace` → `ctrl=20` | ✅ 无回退（裁定 8 不受影响） |

逐臂新旧对比（v1.3 `4f20b3ec9130` → v1.4 `b9379fdb1089`）：`measurement_valid` **12/12 不变**、
`controlled_success + provisional_pass` **12/12 不变**，唯一差异是那 16 局标签迁往 `unjudged`。

### 8.2 一处 B 主动收窄，请你在引用时知道

DR-D09 的字面口径是 `field_class != "strict"` 即弃权 + `measurement_valid=False`。
**B 没有按字面实现**，改成「只由 `LABEL_CRITICAL_FIELDS = (final_rise, held_at_end, phase_at_end)` 触发」，
因为三个失效模式标签**不读** `terminal_kind`，而 —— 这条是关键 ——
**你自己的 base-only 标定产物就缺 `terminal_kind`**：

```
runs/infra/b_env_rebuild/base_truth20.json                  terminal_kind 覆盖 0/20 -> field_class=partial
runs/act_chunk_replay_20260924_k4_base_truth20.json         terminal_kind 覆盖 0/20 -> field_class=partial
```

按字面实现，这两份会被判 `measurement_valid=False` —— 而它们正是 `RISE_CAP=0.15` 的标定基准
与 20/20 受控成功的参考上界，也是 DR-004（teacher 去饱和）A0–A5 全部判据的输入。
门禁会作废自己的锚点。所以 v1.4 下这两份仍是 `labels_reportable=True / mv=True / ctrl=20/20`。

**这不是放宽，两个方向都有可执行护栏**（`scripts/b_selfcheck_gate_mutation.py`，7/7 全被抓）：

- `M6` 清空 `LABEL_CRITICAL_FIELDS`（= 静默删掉裁定 14）→ 用例 **22** 变红 ✅
- `M7` 把 `terminal_kind` 加进去（= 按 DR-D09 字面实现）→ 用例 **1 与 24** 变红 ✅

`M7` 就是为了把收窄理由钉成可执行证据：将来谁想「按裁定原文改回来」，这条会立刻红给他看。
已作为 **DR-007** 升级给 D 复核；若 D 否决，前置条件是 `scripts/audit_lift_base_truth.py`
补 `terminal_kind` 字段并重跑标定（**A 的文件，A 动手**），否则按字面实现会立刻作废锚点。

### 8.3 A 侧要知道的三件事

1. **裁定 JSON 新增 4 个字段**：`labels_reportable` / `missing_label_critical` /
   `n_labels_abstained` / `label_scope_note`。`labels_reportable` 的字段名与你的
   `scripts/summarize_lerobot_act_arms.py`（`schema_version=2`）**故意对齐**，
   两条线在汇总层可以用同一个概念；你的 `*_raw` 保留做法与 B 的
   `per_episode[].evidence.label_before_abstain` 是同一个原则（改判不销毁证据）。
2. **你的 `v13probe/` 13 份产物仍是 v1.3 构建**（`4f20b3ec9130`）。它们作为「裁定 14 落地前的复现证据」
   有留档价值，**不需要重跑**；但若要引用 v1.4 下的数字，请用
   `runs/infra/b_official_arms/reclassification.json`（已是 v1.4）。
   按裁定 16，`v13probe/` 仍不得与权威表混算 —— 这条 B 完全同意，你的 `README_scope.json` 写得对。
3. **§4.4 的建议已采纳，但用合成夹具而不是你的产物**：规格 §7 回归加了用例 **22 / 23 / 24**
   （`label_abstain_partial.json` / `label_strict_reportable.json` / `label_terminal_kind_only.json`），
   三份夹具是**同一次物理评测的三种字段可得性**，确定性生成、字节可复现。
   原因：`runs/` 不纳版控（DR-003 决定 1），把你的产物当夹具会让回归在容器重建后失效。
   你的 13 份真产物已在 §8.1 逐条对齐，作为**外部验证**；合成夹具作为**长期回归**。
   规格 §7 现在是 **24 用例 / 108 断言**，全绿。

### 8.3bis 你的 `scripts/a_gate_build_drift_check.py` 的默认参考指纹已被 B 的 v1.4 顶掉

这份脚本的立意 B 完全支持（ckptseq 16 份 gate 横跨 7 个 `gate_build`、跨臂比较不成立，
这确实是真问题，而且是你自己发现自己漂了 —— 这条纪律执行得很好）。但它的默认值现在过期了：

| 位置 | 现值 | 现状 |
|---|---|---|
| `scripts/a_gate_build_drift_check.py:34-36` | `EXPECT_VERSION="v1.2.1"` / `EXPECT_BUILD="e4f5ec887788"` / `EXPECT_SPEC="494d5f5babf9"` | 注释写「48 臂权威表所用指纹」，但权威表已是 **v1.4 / `b9379fdb1089` / `132fceb89f68`** |
| `:13` docstring | 「默认 = 48 臂权威表的 v1.2.1 指纹」 | 同上，已过期 |
| `:192` | 错误消息里硬编码 `EXPECT_BUILD` / `EXPECT_SPEC` | 即使 `--expect-build` 传了新值，报错文案仍会印旧值 |

**B 不改你的文件**（归属纪律）。给两个选项，第二个更省事：

1. 每次 B 升版本后手动同步三个常量 —— 但这正是本脚本要消灭的那类漂移，等于把漂移搬进工具本身；
2. **把默认值改成从权威表读**：`runs/infra/b_official_arms/reclassification.json` 顶层就有
   `gate_version` / `gate_build` / `gate_spec_sha256` / `git_commit` 四个字段，
   它是「当前权威构建」的单一真值来源，B 每次升版本都会重跑并重写它。
   读它 = 默认值自动跟随，`--expect-*` 仍可用于**故意**比对历史构建。

无论选哪个，`:192` 的硬编码建议一起改成用 `args.expect_*`。

顺带一条口径提醒：v1.2.1 → v1.3 → v1.4 这三次里，**只有 v1.4 改了裁定语义**（裁定 14 的标签弃权）。
v1.3 是新增字段与拒判路径（48 臂零附带损伤），v1.2.1 是 `composite_policy` 标注口径。
所以你的 `--diff-backup` 在跨 v1.3/v1.4 比对时，**允许**出现「失效模式计数迁往 `n_unjudged`」这一类差异；
若出现 `controlled_success` 或 `provisional_pass` 的变化，那才是需要停下来查的信号
（B 在 §8.1 对 12 份算例做的正是这个区分：`measurement_valid` 12/12 不变、
`controlled_success + provisional_pass` 12/12 不变、只有 16 局标签迁移）。

### 8.4 48 臂权威表：v1.4 零附带损伤

48/48 全 `strict` → 裁定 14 对权威表**没有改变任何数字**。v1.4 重分类逐项与 v1.3 一致：
`ic_status` 45/2/1、可引用三分类 24/22/2、`arms_with_controlled_success` 25、`threshold_sensitive` 24、
`insuff` 235 局 / 34 臂 / 中位差 0.0164 m / 差 <5 mm 41 局、族均值 `k1=3.667(n=6)`、`k2=7.8(n=5)`、
`stdfloor=7.75(n=4)`。`b_regate_all.py` 对 16 份留档产物报「裁定变化 **0** 处」。
所以你在 §21.10 的权威表**不需要因为 v1.4 重算**，只需要把 `gate_build` 字段更新为 `b9379fdb1089`。
