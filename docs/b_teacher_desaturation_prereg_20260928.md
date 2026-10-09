# B-4 预登记：teacher `lift` 段去饱和的验收标准与锚点重算规则

登记人：智能体 B（验收门禁与可复现性线）。时间：2026-09-28 深夜。
性质：**预登记（pre-registration）**。本文档在任何人动手改 teacher、重采数据之前落盘，
用来把门框钉死。它**不是**动手依据 —— 动手依据是 `work/decisions/decisions_20260928_B.md`
的 **DR-004**，而 DR-004 本身也只在 D/用户放行后才生效（见 §7 触发条件）。

配套可执行部分：`scripts/b_teacher_dz_audit.py`（baseline 与 check 共用同一把尺）。
已锁基线：`runs/infra/b_teacher_desat/baseline_teacher_dz.json`。
已跑负控制：`runs/infra/b_teacher_desat/negative_control_old_teacher.json`（见 §8）。

---

## 0. 一句话

去饱和是**幅度修复**，不是**可辨识性修复**；所以本预登记除了 D 列的四条验收，
另加一条 **B3 漂移有界性探针**，用来挡住「上升变慢了、300 步内还没漂出 `RISE_CAP`，
于是 over_lift 假性归零」这条最容易被误读成成功的通道。

---

## 1. 变更规格（单变量）

| 项 | 内容 |
|---|---|
| 改哪一行 | `scripts/demo_scripted_lift_rs.py:99`，`lift` 相位内 `target = eef + np.array([0.0, 0.0, 0.3])` |
| 改成什么 | `0.3` → `0.01`（经同一行下方 `np.clip(delta / 0.05, -1, 1)` 后 `dz = +0.2`，不再饱和） |
| 归属 | **A 线**（`scripts/demo_scripted_lift_rs.py` 不在 B 的写权限内；B 只出规格与验收仪器） |
| 明确**不许**同时改 | `LIFT_TARGET = 0.05`、`PRE_HEIGHT`、`GRASP_OFFSET_Z`、`HOLD_STEPS`、`MAX_GRASP_TRIES`、夹爪语义行、`approach/descend/grasp/hold/done` 五个相位的任何逻辑 |
| 单变量的机器验证 | 判据 **T5**：非 `lift` 相位的逐维 `mean/std/min/max` 与帧数必须与基线在 `1e-6` 内一致；**T4**：`hold` 段 teacher `dz` 必须仍恒为 0 |

为什么盯单变量：这次改动会**作废整个 48 臂比较集**（§6）。如果同一次改动里夹带了
第二处修改，作废之后就再也没法把效果归因到任何一处，等于白扔一轮数据。

---

## 2. 三个必须在重采数据之前说清的事实

### 2.1 去饱和修的是幅度，不是可辨识性

`docs/b_normalization_incident_20260928.md` §5 的原始诊断有两半：

1. teacher `lift` 段 `dz` 恒 `+1`（饱和），`hold/done` 段恒 `0`；
2. 两者的可观测差异**只在 `cube_z` 绝对值**，而 `hold` 的触发条件是 `cube_z > z0 + 0.05`，
   `z0` 不在观测里 → 策略**没有停止条件**。

探针实测（`runs/infra/b_observability/identifiability_hist1_seed0.json`）：`lift` vs 非 `lift`
只用夹爪已闭合帧，**recall = 1.000 但 precision = 0.30**。也就是说「该不该开始抬」几乎完全可分，
「该在哪一帧停」不可分。把 `dz` 从 `+1` 降到 `+0.2` **只缩小条件均值的幅度**，
不会把 `z0` 放进观测，因此不会恢复停止条件。

推论（本预登记的核心）：**去饱和后 over_lift 可能仍然非零，只是涨得更慢。**
这是可接受的中间结果，但必须按 §4-B3 区分「慢」和「停」，不得直接宣布修复。
若 B3 FAIL，下一步是 `docs/b_normalization_incident_20260928.md` §6.3（把 `cube_z − z0` 放进 obs），
那是 obs 契约变更 = **另一次独立 baseline 重置**，须另开 DR，**禁止**再做第三轮 teacher 微调。

### 2.2 「300 步内没漂出 0.15」会被现有门禁误读成受控成功

现门禁 C3 是 `max_rise <= RISE_CAP = 0.15`，逐局在 `horizon = 300` 上测。
旧 teacher 的实证轨迹（`runs/infra/b_normclip/clip3.json`，seed 5002）：
`rise +0.099(f60) → +0.128(f200) → +0.154(f299)`，即尾段速率 ≈ `1.9e-4 m/step`，
**在 horizon 末端仍在上升**。命令幅度缩小 5× 后，同样「不停」的策略尾段速率约 `4e-5`，
300 步内总漂移可能只有 `0.05 → 0.06`，**稳稳落在 0.15 以内**，于是 C3 通过、
`insufficient_lift` 也通过，门禁给出 `controlled_success`。

这不是门禁的 bug（门禁按定义正确执行），而是**判据对「有界」的定义不完整**：
它只检查了「这一段时间内没超上限」，没检查「它是否会停」。B3 就是补这一刀，
且它**不需要改门禁**，只需要同一冻结 ckpt 多跑一个 `--horizon 600`
（`scripts/eval_act_lift_truth.py:29` 与 `scripts/eval_lerobot_act_runtime.py:219` 都已有 `--horizon`）。

### 2.3 `RISE_CAP = 0.15` 从来没有可复现规则（本次补上）

门禁源码只写了「scripted base 实测 mean 0.0764 / max 0.078，取约 2 倍为上限」
（`scripts/b_gate_controlled_success.py:27`）。「约 2 倍」不是规则：

| 候选规则 | 套在旧 base-only `mean_max_rise = 0.07633` 上 | 是否复现任值 0.15 |
|---|---|---|
| `ceil_to_0.01(2 × x)` | 0.16 | ✗ |
| `round_to_0.05(2 × x)` | 0.15 | ✓ |
| **`floor_to_0.01(2 × x)`** | **0.15** | **✓（采纳）** |

采纳 `floor_to_0.01`：`RISE_CAP` 是**上限**，向下取整是保守方向（更早抓到 flick）。
判据 **A0** 把这条钉死：规则套在**旧** base-only 上必须精确等于 `0.15`，否则 check 直接 FAIL。
A0 的意义是防「悄悄换锚」—— 任何未来的锚点重算，都必须先用旧数据复现旧值，才有资格推新值。

对照：`FINAL_RISE_MIN = 0.04` **不是** teacher 锚，是几何锚（`0.92 ×` 方块全高 `0.04341`，
见门禁 `:33` 勘误），且比 robosuite 自身 `_check_success` 的等效阈严约 4.7 倍。
**它不随 teacher 改变**，因此不在本次重算范围内（§5）。

---

## 3. 验收判据总表

仪器：`scripts/b_teacher_dz_audit.py`（T/A 组）、门禁裁定 JSON（B1/B2）、
`scripts/eval_*` 双 horizon（B3）、逐帧 actlog（B4）。
`status = not_measured` 时**一律不算通过**（仪器已按此实现）。

| ID | 判据 | 指标 | 阈值 | 基线实测（旧 teacher） | 仪器 / 归属 |
|---|---|---|---|---|---|
| **T1** | `lift` 段 `dz` 不再恒 ±1 | `dz_lift_sat_frac` | `≤ 0.05` | **1.000** | 数据集审计 / B 跑，A 提供数据 |
| **T2** | 仍保留明确上升命令（不是把 lift 也压成 0） | `dz_lift_mean` | `∈ [0.10, 0.50]` | **1.000** | 同上 |
| **T3** | `lift` 与 `hold` 命令幅度仍可区分 | `abs(mean_dz_lift − mean_dz_hold)` | `≥ 0.10` | 1.000 | 同上 |
| **T4** | `hold` 段 teacher 未被顺手改 | `dz_hold_absmax` | `≤ 1e-6` | 0.0 | 同上 |
| **T5** | 单变量：非 `lift` 相位逐位不变 | 逐维统计 + 帧数 diff 数 | `= 0` | 0 | 同上（需 `--baseline`） |
| **A0** | 锚点规则能复现任值 | `floor_to_0.01(2 × 旧 mean_max_rise)` | `== 0.15` | **0.15 ✓** | 同上 |
| **A1** | base-only 参考上界自身仍成立 | `success_grasp_verified` / `phase_at_end` / `held` | `20/20`、全 `done`、全 `True` | 20/20 ✓ | `scripts/audit_lift_base_truth.py` / A 跑 |
| **A2** | 过冲变小但不为负 | `mean_final_rise` | `∈ [0.050, 0.065]` | **0.06365** | 同上 |
| **A3** | 门禁仍可满足且有裕度 | `min(final_rise) − 0.04` | `≥ 0.010` | **0.0220** | 同上 |
| **A4** | 改动确实改变了参考轨迹 | `mean_max_rise` | `∈ [0.052, 0.072]` | **0.07633** | 同上 |
| **A5** | 新 `RISE_CAP` 候选落在预测带 | `floor_to_0.01(2 × 新 mean_max_rise)` | `∈ [0.10, 0.15]` | 0.15 | 同上 |
| **B1** | `over_lift` 归零 | 20 局 pinned 5000–5019 的 `over_lift` 计数 | `= 0` | 主失效模式 | 门禁裁定 / A 跑评测，B 判 |
| **B2** | `insufficient_lift` 归零且转成受控成功 | 同上的 `insufficient_lift` 计数 | `= 0` | 235 局 / 34 臂（v1.3 汇总） | 同上 |
| **B3** | **漂移有界性**（本文档新增，见 §2.2） | `median[max_rise(h600) − max_rise(h300)]`；尾 100 步速率 | `≤ 0.010 m`；`≤ 5e-5 m/step` | 外推 ≈ `+0.06 m` / `1.9e-4` | 同一冻结 ckpt 双 horizon / A 跑，B 判 |
| **B4** | `held` 期间命令正偏消失 | `mean(dz_cmd \| held)` | `abs ≤ 0.02` | `+0.052`（clip3 逐帧） | actlog / A 跑，B 判 |

**通过定义**：T1–T5 + A0–A5 **全过**才允许把新数据集用于训练；
B1–B4 **全过**才允许主张「over_lift 已修复」；B3 单独 FAIL 而 B1/B2 通过时，
唯一允许的措辞是「上升速率降低，停止条件仍未恢复」。

---

## 4. 数值依据（逐条，可复核）

基线来源：teacher 数据集 `runs/infra/lerobot_act_lift_state_overfit/data`（`split=train`，
**帧级** `action` 口径 24 集 × 300 帧 = 7200 帧；文档里常引的 7128 是 **chunk 级**
24 × 297 口径，同一批数据，不是漂移）；base-only 真值
`runs/act_chunk_replay_20260924_k4_base_truth20.json`（20 局，`phase_at_end` 全 `done`，`held` 全 `True`）。

- **T1/T2**：`dz_lift_mean = 1.000`、`sat_frac = 1.000` —— `lift` 段每一帧都撞在 `clip` 边界上，
  与 §2.1 的诊断一致。`+0.01/0.05 = 0.2`，落在 `[0.10, 0.50]` 中央；带宽放宽到 `[0.10, 0.50]`
  是为了允许 A 在 `0.1~0.5` 内选点（例如 `0.02 → dz=0.4`）而不必重新登记，
  但**任何**取值都必须同时满足 T3。
- **T3**：`hold` 段 `dz ≡ 0`，所以分离度就是 `mean_dz_lift` 本身；`≥ 0.10` 与 T2 下界同值，
  作用是防止「为了去饱和把 lift 也压到接近 0」——那会让 `lift` 与 `hold` 在命令上不可分，
  把幅度问题换成更严重的可辨识性问题。
- **A2 预测带**：`final_rise = LIFT_TARGET + 过冲`。旧 teacher 过冲实测 `mean 0.01365 / min 0.0120 / max 0.0169`。
  命令幅度缩 5× → 线性外推过冲 `≈ 0.0027`；带 `[0.050, 0.065]` = `0.05 +` 过冲 `[0.000, 0.015]`，
  即**允许过冲完全不缩放**（保守上界）也允许缩到 0（下界）。
- **A3**：`FINAL_RISE_MIN = 0.04` 不动，所以只需验裕度。旧 `min(final_rise) = 0.0620` → 裕度 `0.0220`。
  新预测 `min(final_rise) ≈ 0.0524` → 裕度 `≈ 0.0124`，仍 `≥ 0.010` 但明显变薄。
  **若 A3 FAIL，禁止的响应是下调 `FINAL_RISE_MIN`**（那是几何锚 + 监管裁决范围，
  且下调会放大所有历史臂成功率）；允许的响应是把 `LIFT_TARGET` 从 `0.05` 提到 `0.06`，
  作为**另一次单变量改动 + 另一条 DR**，并在本文档追加一节。
- **A4**：上界 `0.072 < 0.07633` 是刻意的。A4 不是精度带，是**「改动确实生效」的存在性检查**：
  若新 base-only 的 `mean_max_rise` 仍 `≥ 0.072`，说明过冲不由命令幅度主导
  （改动没落地，或上升由控制器动力学/接触决定）→ **停下来诊断，不要接着改门禁阈值**。
  下界 `0.052 = LIFT_TARGET + 0.002`：低于它意味着连 `hold` 的触发高度都没稳定达到。
- **A5**：`floor_to_0.01(2 × [0.052, 0.072]) = [0.10, 0.14] ⊂ [0.10, 0.15]`。
  注意新 cap **必然比 0.15 更紧**（更敏感的 flick 检测），这正是 48 臂比较集不可比的直接原因（§6）。
- **B3 标定**：见 `scripts/b_teacher_dz_audit.py` 内 PREREG 注释。旧行为外推漂移 `≈ +0.06 m`、
  尾速 `1.9e-4` → 对 `0.010 / 5e-5` 分别 FAIL **6×** 与 **3.8×**；真停住的策略漂移 `≈ 0` → PASS。
  阈值取在靠「停住」一侧，保证这条判据两边都有区分力，不是只挡极端。
- **B4**：`+0.052` 来自 `docs/b_normalization_incident_20260928.md` §5 的逐帧取证
  （`held` 273 帧、`55%` 帧 `dz>0.05`、`|dz|>0.9` 的帧 `0%`）。阈值 `0.02` ≈ 旧值的 `38%`，
  与命令幅度缩 5× 的方向一致但不要求同比缩放（条件均值的收缩通常小于命令幅度的收缩）。

---

## 5. 锚点重算与生效流程

| 常量 | 现值 | 是否 teacher 锚 | 本次处置 |
|---|---|---|---|
| `RISE_CAP` | `0.15` | **是**（`≈2 ×` 旧 base-only `0.0764`） | 重算：`floor_to_0.01(2 × 新 mean_max_rise)`，A5 验带；**生效须写进 DR-004 的「生效」段并由 D/用户放行** |
| `FINAL_RISE_MIN` | `0.04` | 否（几何锚 `0.92 × 0.04341`） | **不动**。只用 A3 验「门禁在新 teacher 下仍可满足且有 ≥0.010 裕度」 |
| `LIFT_TARGET` | `0.05` | 是（teacher 内部常数，非门禁） | **本次不动**（§1 单变量）。只有 A3 FAIL 时才作为独立后续改动 |
| `INPUT_BLOWUP_TOL` | `0.05` | 否（归一化事故防线） | 不动，但新数据集须重算 blowup 阈值来源（`threshold_provenance`，门禁 v1.3 §2.13） |
| C5 敏感性带 | `±0.005` | 否 | 须在**新**数据上重跑 `scripts/b_gate_threshold_sensitivity.py`，旧敏感带（12 臂 0 robust / 5 sensitive）随 teacher 作废 |

流程（顺序不可换）：

1. A 改 `demo_scripted_lift_rs.py:99`（单变量），B 跑 `--mode check` 的 **T 组**（只需数据集，最便宜，先挡）。
2. A 跑 `scripts/audit_lift_base_truth.py --episodes 20 --seed0 5000 --horizon 300`，B 跑 **A 组**（含 A0）。
3. A0–A5 全过 → 由 B 把 `RISE_CAP` 新值写进 DR-004 的「生效」段，附新 base-only 产物 sha256；
   D/用户放行后才改 `scripts/b_gate_controlled_success.py:27`，并在
   `docs/b_controlled_success_v1_20260928.md` §6 版本登记里记 **v1.5**
   （v1.4 已被裁定 14 / DR-D09 占用，见 DR-007；锚点重置顺延一版，避免两种性质的变更共用一个版本号）。
4. A 重训 + 评测（`h=300` 与 `h=600` 各一次，同一冻结 ckpt、同一 pinned seeds），B 判 **B 组**。
5. B3 FAIL → 按 §2.1 转 obs 契约变更路线（另开 DR），**不得**再调 teacher。

---

## 6. baseline 重置登记要求（DR-001 生效条件四要素）

DR-001 要求「变更内容、影响的基线、作废的历史结论清单、回归验收方式」四项齐备才可动手。
前三项见 §1 / §6.1 / §6.2，第四项见 §6.3。DR-004 只登记**许可与门框**，不预先宣布结果。

### 6.1 影响的基线

- teacher 数据集（所有 `runs/infra/lerobot_act_lift_state_overfit/` 及其派生）；
- base-only 参考上界 `mean_max_rise 0.07633 / mean_final_rise 0.06365`；
- 门禁锚 `RISE_CAP`；
- 所有以「`mean_max_rise` = base-only 的 X%」表述的结论（该百分比分母变了）。

### 6.2 作废 / 降级清单

| 结论 | 处置 | 理由 |
|---|---|---|
| 48 臂官方比较集的**跨 teacher 可比性** | **作废**（各臂裁定 JSON 本身不作废，`measurement_valid` 不受影响） | 数据集与 `RISE_CAP` 同时变 |
| `insuff_diagnostic` 汇总：235 局 / 34 臂、median `0.0236`、C5 杠杆表（→0.035 翻 41、→0.0217 翻 134、→0.0085 翻 235） | **降级为「旧 teacher 专用」**，引用时必须带 teacher 指纹 | C5 带的位置相对于新 `final_rise` 分布会移动 |
| 族均值 `k1 = 3.667/20(n=6)`、`k2 = 7.8/20(n=5)`、`stdfloor = 7.75/20(n=4)` | **降级为旧 teacher 口径**，不得与新臂混算 | 同上 |
| `docs/lerobot_act_env_setup_20260928.md` 里所有「= base-only 0.0764 的 X%」 | **降级**，须按新 base-only 重算才可引用 | 分母变 |
| slew cap `{0.5,0.25,0.1}` / dz deadband `{0.15,0.2,0.3}` 全 0/20 的**负结果** | **结论保留，机制解释须重述** | 原文机制是「命令本身已饱和 ±1，所以执行侧约束无效」；去饱和后 teacher 命令不再饱和（但 policy 的 tanh 输出仍饱和），引用时必须带这条限定 |
| `b_bc_underfit_probe` / `b_probe_dz_identifiability` 的离线结论 | **不作废** | 开环、teacher 分布内评测；但 T2 `precision_lift = 0.30` 是 §2.1 论证的支柱，重采后须重跑确认 |
| checkpoint 本身 | **不作废但失去可比性** | 训练数据变了 |

### 6.3 回归验收方式

1. `scripts/b_teacher_dz_audit.py --mode check` 退出码 0（T+A 全过）；
2. 负控制仍 FAIL（§8）—— 证明判据没有因为改动而变松；
3. `scripts/b_selfcheck_gate_regression.py` 21 用例 / 85 断言全过（门禁逻辑未因换锚而回归）；
4. `scripts/b_selfcheck_gate_mutation.py` 5/5 仍被抓到；
5. `scripts/b_selfcheck_reproducibility.py` 12/12；
6. `scripts/b_regate_all.py` 在新锚下重跑，**新旧裁定并列留档**（旧构建自动快照为
   `*.build_<oldbuild>.json`），不得覆盖；
7. `docs/b_controlled_success_v1_20260928.md` 升到 **v1.5**，§6 版本登记写清「锚点重置」而非「判据收紧」
   （v1.4 已用于裁定 14，属判据变更；两种性质不得共用版本号）。

---

## 7. 触发条件与排序（现在**不**动手）

- A 的预登记 `docs/a_bimodal_divergence_preregistration_20260928.md` §9 明确写了：
  在双峰分岔有答案前不做任何 L2 修复（含 teacher 去饱和），理由正是
  「`RISE_CAP` / `FINAL_RISE_MIN` 绑在旧 teacher 上，提前重置会连做两次重置并废掉 48 臂比较集」。
  **B 同意这个排序**，本文档因此是预登记而非执行单。
- 放行条件（三者同时满足）：
  1. A 的 `ckptseq/divergence_verdict.json` 给出 R1/R2 结论（分岔时间窗已确定）；
  2. D/用户对 DR-004 的「生效」段放行；
  3. A 线当前 in-flight 评测收尾，避免半批数据跨 teacher。
- 提前动手的后果：48 臂比较集作废但**换不到**任何新结论，因为双峰问题与 teacher 幅度问题
  会混在同一批数据里，两者都无法归因。

---

## 8. 负控制（已跑，证明判据有牙）

用**未修改的旧 teacher** 数据集 + 旧 base-only 真值跑 `--mode check`：

```
verdict=FAIL   (exit code 1)
  T1 FAIL  dz_lift_sat_frac=1.0        (<= 0.05)
  T2 FAIL  dz_lift_mean=1.0            (in [0.1, 0.5])
  T3 PASS  separability=1.0            (>= 0.1)
  T4 PASS  dz_hold_absmax=0.0          (<= 1e-06)
  T5 PASS  single_variable diff=0
  A0 PASS  rule(0.07633) = 0.15 == incumbent 0.15
  A1 PASS  20/20, done, held
  A2 PASS  mean_final_rise=0.06365     (in [0.05, 0.065])
  A3 PASS  margin=0.022                (>= 0.01)
  A4 FAIL  mean_max_rise=0.07633       (in [0.052, 0.072])
  A5 PASS  rise_cap_candidate=0.15
  B1–B4    not_measured（未提供闭环产物，如实标未测，不算通过）
```

三条 FAIL 恰好就是这次改动应当改变的三件事（`lift` 段饱和、`lift` 段幅度、参考轨迹的 `max_rise`），
其余判据在旧数据上 PASS —— 说明判据既非恒真也非恒假。
产物：`runs/infra/b_teacher_desat/negative_control_old_teacher.json`。

---

## 9. 产物与引用

| 项 | 路径 |
|---|---|
| 测量仪器 | `scripts/b_teacher_dz_audit.py` |
| 基线（旧 teacher，已锁） | `runs/infra/b_teacher_desat/baseline_teacher_dz.json` |
| 负控制 | `runs/infra/b_teacher_desat/negative_control_old_teacher.json` |
| base-only 真值（锚点来源） | `runs/act_chunk_replay_20260924_k4_base_truth20.json` |
| teacher 数据集（基线口径） | `runs/infra/lerobot_act_lift_state_overfit/data`（`split=train`，帧级 7200 帧） |
| 根因诊断 | `docs/b_normalization_incident_20260928.md` §4–§6 |
| 可辨识性证据 | `runs/infra/b_observability/identifiability_hist1_seed0.json`（T2 recall 1.000 / precision 0.30） |
| 登记 | `work/decisions/decisions_20260928_B.md` DR-004 |
| 排序约束来源 | `docs/a_bimodal_divergence_preregistration_20260928.md` §9 |

`runs/` 不纳版控（DR-003 决定 1），所以本文件把上述产物的**关键数字直接写进正文**，
并在 DR-004 里登记 sha256，保证容器重建后仍可核对。
