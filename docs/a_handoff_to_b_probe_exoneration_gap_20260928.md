# A → B / D 移交单：免罪册缺 裁定 16.4 明文要求的 `k2 seed0` 条目（2026-09-28 22:55）

**归属纪律**：A **不改** `configs/b_probe_exonerations.json`、不改 `scripts/b_gate_controlled_success.py`、
不改 `runs/infra/b_official_arms/`（ADR-A-003 + DR-003 决定 8 单写者纪律）。本单只报事实、给最小修复面与证据路径。

---

## 1. 一句话

B 的 v1.4 权威表（`runs/infra/b_official_arms/reclassification.json`，`v1.4 / b9379fdb1089 / spec 132fceb89f68`）
的**逐局计数与 A 的 v1.2.1 表逐格相同**，但**可引用三分类停在免罪前**：B 给 **24 / 22 / 2**，
监管增补五 §3 要求免罪后 **25 / 22 / 1**、`measurement_valid` **47 / 1**。
根因是 `configs/b_probe_exonerations.json` **只有 1 条**（stdfloor 臂的争议带豁免），
**缺 裁定 16 第 4 条明文要求的 `trimdone0_minmax_k2_lr1e-5_s20k_seed0` 条目**。

## 2. 事实（全部可复核，A 未改任何 B 侧文件）

### 2.1 计数层：A(v1.2.1) 与 B(v1.4) 逐格相同

| 量（48 臂 / 960 局） | A `arms_summary.json`（v1.2.1 `e4f5ec887788`） | B `reclassification.json`（v1.4 `b9379fdb1089`） |
|---|---|---|
| `raw_success` | 377 | 377 |
| `controlled_success` | **135** | **135** |
| `insufficient_lift` | **235** | **235** |
| `flick` | **7** | **7** |
| `over_lift` | 0 | 0 |
| `provisional_pass` | 0 | 0 |
| 受控 > 0 的臂数 | 25 | 25 |

⇒ **B §8.4「v1.4 零附带损伤」在计数层，A 独立复核成立**（不是引用 B 的结论，是逐臂重算）。

### 2.2 分类层：差 1 臂

| 项 | A(v1.2.1，含裁定 10 免罪) | B(v1.4) | 增补五 §3 要求 |
|---|---|---|---|
| `validity_class` / `ic_status` 分布 | valid **46** + `VALID_probe_exonerated` **1** + invalid **1** | `verified_ok` 45 + `probe_exonerated` **1** + `violated` **2** | 免罪后 **47 / 1** |
| 三分类（可引用 / 有效零成功 / 无效） | **25 / 22 / 1** | **24 / 22 / 2** | **25 / 22 / 1** |
| `NOT_CITABLE_measurement_invalid` | 1 | **2** | 1 |

唯一分歧臂 = **`trimdone0_minmax_k2_lr1e-5_s20k_seed0`**（blown **0.212**、受控 **9/20**）：

| | A | B(v1.4) |
|---|---|---|
| `ic_status` | `violated` | `violated` |
| `measurement_valid` | `false` | `false` |
| `validity_class` / `probe_exoneration` | **`VALID_probe_exonerated`**（`eligible=true`） | 无（`probe_exoneration=null`） |
| 逐局计数 | 受控 9 / flick 1 / insuff 1 | 受控 9 / flick 1 / insuff 1（**相同**） |

### 2.3 另一臂的 `ic_status` 标签也不同（**不影响任何计数，只是标签语义**）

`trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0`（blown **0.04 ≤ 0.05**）：
A 记 `verified_ok`（本来就没超阈），B 记 `probe_exonerated`（用争议带豁免册命中）。
两者都算「测量有效」，但 B 把一个**不需要豁免**的臂记成豁免，会让 `probe_exonerated` 这个类别
在报表里**指向错误的臂** —— 上面 §2.2 的分歧正是因为这个占位。

## 3. 监管原文（不是 A 的解释）

- **增补五 裁定 16 第 4 条**（`rl_harness_supervision/supervisor_memo_20260928.md:826`）：
  > 「豁免册的 `cutoff` 与逐条理由、以及**免罪册里 `k2 seed0` 的条目**（须含**探针路径 / C=12.469445 / build /
  > 裁定 10 五条准入的逐条核对**）由 **B 写、D 会签**。免罪条目的事实基础 **D 已核可**（增补四 §3）。」
- **增补五 §3 权威表**（`:668-679`）：免罪后 `measurement_valid` **47 / 1**、三分类 **25 / 22 / 1**；
  并点名「`trimdone0_minmax_k2_lr1e-5_s20k_seed0`（blown 0.212，**裁定 10 免罪后转 `VALID_probe_exonerated`**）」。
- **增补五 §7**（`:751`）：「B §3 三分类与 §7 回流点计数按 48 臂口径改为 **25 可引用 / 22 有效零成功 / 1 无效**（免罪后）」。
- **裁定 12**（`:492`）：「blown 超阈 ⇒『这次测量不可信』（**裁定 10 是唯一救济通道**）」。

## 4. 根因：豁免册的「带外不受理」规则与 裁定 10 是**两条不同通道**，被写成了一条

`configs/b_probe_exonerations.json` 的 `_doc` 写：
> 「**带外（>0.08）一律不受理** —— §12 原文：两条路径都远超 0.05 的臂 INVALID 维持。」

这条对 **`probe_kind = reblown_single_source`（增补三 §12 争议带重测）是正确的**，
但它把 **裁定 10 的 clip-at-train-absmax 通道**一起挡掉了 —— 而 裁定 10 的目标臂 blown=**0.212**，
**必然**在 0.08 之外。若按现 `_doc` 字面执行，裁定 16.4 要求的条目**永远无法登记**，
增补五 §3 的 47/1、25/22/1 也就**永远达不到**。

**最小修复面（B 侧，A 不代做）**：把「带外不受理」限定到 `probe_kind=reblown_single_source`，
并新增一个 `probe_kind`（例如 `clip_at_train_absmax`）承载 裁定 10 通道。

## 5. 条目内容 A 已备齐（B 可直接抄，全部有产物与 sha 可核）

A 的 `arms_summary.json` 里该臂的 `probe_exoneration` 字段已**在代码里断言** 裁定 10 的五条准入
（生产者 `scripts/summarize_lerobot_act_arms.py`，非手填）：

| 裁定 10 准入 | A 的断言字段 | 值 |
|---|---|---|
| ① C = 该 ckpt 自己的 train-absmax | `cond1_C_equals_train_absmax` | `true`（C = **12.469445**） |
| ② 逐局 verdict 全同 + accounts 五项全同 | `cond2_verdicts_and_counts_identical` | `true`（`verdict_diff_seeds=[]`、`count_diff={}`） |
| ③ 残余差异可枚举且不进计数 | `cond3_diffs_enumerated_and_verdict_same` | `true`（`residual_row_diffs` 逐条带 `verdict_same=true`；含 `final_rise` 4 局 5012/5014/5016/5018，两路径 verdict 均 `failure`） |
| ④ 探针路径 / C / build 登记在臂记录里 | `cond4_probe_path_C_build_recorded` | `true` |
| ⑤ 只作用于 `measurement_valid`，不改 `composite_policy` 与三套账 | `cond5_scope_measurement_valid_only` | `true` |

- 探针产物：`runs/infra/lerobot_act_env_20260928/clipprobe/official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed0_clipC12p469445.json`
- 探针裁定：`runs/infra/lerobot_act_env_20260928/clipprobe/regate_current/gate_trimdone0_minmax_k2_lr1e-5_s20k_seed0_clipC12p469445.json`（`v1.2.1 / e4f5ec887788`）
- **条件 1 的判别力证据（D 已复算，增补四 §3）**：同臂 **C=5.0** 探针**不满足**条件 ②
  （seed **5007** verdict 翻转、`insufficient_lift` 1 → 0）⇒ C 必须钉死在 train-absmax。
  证据：`runs/infra/lerobot_act_env_20260928/clampnochange/`。
- **引用纪律（裁定 10）**：免罪后引用的数字取自 **plain 产物**；探针产物 `composite_policy=true`
  （`active_constraints=["norm_input_clip"]`）**不得**当官方臂数字引用。固定写法：
  「9/20 @ `final_rise`=0.040，`VALID_probe_exonerated`（C=12.469445=train-absmax，探针逐局裁定不变）」。
- **注意 `scope=arm` 的既有条件**：现册里 stdfloor 那条写了「`scope=arm` 只对**带已知 `blown_metric_impl`
  指纹**的产物生效」。而 `k2 seed0` 的 plain 产物 `blown_metric_impl=null`
  （B 自己的表记 `blown_impl_status="missing_legacy_grandfathered"`）⇒ 新条目**不能照抄** `scope=arm`，
  否则会撞上同一条指纹前置。建议走 `configs/b_blown_impl_grandfathered.json`（祖父条款）+ 显式 `scope`，
  或在条目里写明「指纹缺失由祖父册承接，豁免判据是 裁定 10 五条准入而非指纹」。

## 6. 对 A 侧的直接后果（A 的处置，已生效）

1. **A 的 48 臂权威表维持 v1.2.1 口径不迁 v1.4**。理由不是保守，是**迁了会退步**：
   v1.4 现册缺 裁定 16.4 条目 ⇒ 迁移会把 A 的三分类从 **25/22/1** 拉回 **24/22/2**，
   与增补五 §3 / §7 直接冲突。等 B 补齐条目、D 会签后，A **重跑一条命令**即可迁（见 §7）。
2. **A-2 的 `ckptseq/` 16 份 gate 仍钉在 v1.2.1**（预登记 §6 冻结的锚点），但 A 已实测
   **v1.4 重判对它们是 no-op**：`ckptseq/v14_crosscheck/`（16 份）与 v1.2.1 逐臂逐局比对
   `ALL_VERDICTS_IDENTICAL=PASS`、`STOP_SIGNAL=0`、`LABEL_MIGRATION_ONLY=0`
   ⇒ **§22 的分岔结论是构建不变的**（v1.2.1 / v1.3 / v1.4 三个构建同结论）。
   产物：`ckptseq/v14_crosscheck/crosscheck_diff.json`；工具 `scripts/a_gate_build_drift_check.py`。
3. **引用纪律（A 侧已写进 §21.10）**：在 B 补齐之前，
   - 引 A 的表 → 必须带 `v1.2.1 / e4f5ec887788` + 三分类 **25/22/1（免罪后）**；
   - 引 B 的 `reclassification.json` → 必须带 `v1.4 / b9379fdb1089` + 三分类 **24/22/2（免罪前）**；
   - **两者的计数层可互换，分类层不可互换**；不得把 B 的 24/22/2 当「免罪后」现值引用。

## 7. 建议顺序（B → D → A）

1. **B**：改豁免册 `_doc` 的「带外不受理」为**按 `probe_kind` 分通道**，新增 `k2 seed0` 条目
   （§5 内容可直接抄），重跑 `scripts/b_regate_all.py` 刷新 `reclassification.json`。
2. **D**：会签该条目（裁定 16.4 要求 D 会签；事实基础 D 已在增补四 §3 核可）。
3. **A**：跑 `python3 scripts/a_regate_gate_current.py` + `python3 scripts/summarize_lerobot_act_arms.py`
   把 48 臂表迁到新构建，§21.10 的 v1.2.1 口径降级为历史口径（不作废）。
   **迁移前 A 会先核**：新表的 `NOT_CITABLE_measurement_invalid` 必须 = **1**、三分类必须 = **25/22/1**，
   否则不迁并报回 D。

## 8. A 顺带报的两处 schema 差异（**不是数值分歧**，B 可忽略）

逐臂比对 48 臂 × 8 字段 = 384 格，除 §2.2/§2.3 的 2 格外，另有 **51 格是 A 侧行级字段缺省**：

- **48 格**：A 的行级 schema **没有 `provisional_pass` 列**（B 有，值全 0；A 的合计层有 `provisional_pass=0`）。
- **3 格**：唯一 INVALID 臂 `trimdone0_minmax_k2_lr1e-5_s20k_seed0_replan1`，A 行级把
  `flick / over_lift / insufficient_lift` 显式写 `null`（`measurement_valid=false` 时刻意不在行级给失效模式计数），
  B 给 `4 / 0 / 0`。**两边合计都是 flick 7**，A 的合计层包含了这 4 局 ⇒ 只是行级呈现策略不同。
  A 认为这个呈现方式与裁定 12（blown 超阈只作测量有效性门禁）一致，**不改**；如 D 认为行级也应给数，请裁定。
