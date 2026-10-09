# 预登记：训练侧种子双峰分岔定位（A-2，2026-09-28 21:15 写就，**跑之前**）

登记方：智能体 A。批准来源：用户 2026-09-28 晚 A-2「P0，主线，批准开跑」+ 四条约束。
监管依据：`rl_harness_supervision/supervisor_memo_20260928.md` 增补三 §6（种子双峰升格为 P0 第一未解问题）、
增补四 §11-A④（`dz_pos_frac_tail ≥ 0.9` 作为 L2 预登记判据的扩写，**必须在跑新臂之前写进预登记文档**，
首批新臂要报告样本外表现，**不得事后调整**）。
本文档在**任何新评测启动之前**落盘；落盘时间即冻结时间，判据、臂清单、判定规则一律不再改动。

---

## 1. 问题

同一配方、同一数据集、同一评测协议下，训练 seed 单独决定成败，且分布**双峰**：

- K=2（口径 2/2/2）6 seed 受控成功 = 9(免罪) / 2 / 0 / 17 / 19 / 1，均值 8.0/20，极差 0~19；
- K=1（口径 1/1/1）6 seed 受控成功 = 20 / 0 / 0 / 2 / 0 / 0，均值 3.67/20，极差 0~20；
- 两族合并 21 个有 actlog 的臂里，**受控成功落在 4–9 的臂数 = 0**（中间是空的）。
  > **更正指针（裁定 30 / DR-D29，2026-09-29 由 A 追加；原文按 append-only 一字未改）**：上句是**分布层**陈述，
  > 只在 **v1.2.1 / `e4f5ec887788`** 口径下成立 —— 那时 `trimdone0_minmax_k2_lr1e-5_s20k_seed0`（9/20）是
  > `NOT_CITABLE_measurement_invalid`、**不在**有效臂分布里。裁定 10 的探针免罪在 **v1.5 / `f19f61341cbe`**
  > 落地（裁定 26/27/28，D 已复签）后它 `measurement_valid=True`、**重回分布** ⇒ 21 actlog 臂集里落在
  > 4–9 的臂数实测 **= 1**（就是免罪臂本尊），「= 0」**自此禁用**，「中间是空的」也禁用。
  > 准确定性 =「**强间隙分离（gap-separated）**」：低簇 0–3（**15** 臂）／高簇 14–20（**5** 臂）／
  > **孤立 1 臂 = 9**（`VALID_probe_exonerated`、`probe_kind=clip_at_train_absmax`），
  > **空带是 4–8 与 10–13**，不是「4–9」。引用双峰必须带四限定：**臂集 / 20k 快照 / 构建指纹 /
  > 显式点出中间带孤立臂**。全文见 `rl_harness_supervision/supervisor_memo_20260929.md` 增补七 §20
  > 与本文档 §14；机器判据 = `scripts/a_distribution_layer_check.py`（D2 / D3 / D6，A 不自免）。

这不是「能力高低」问题，是「**可重复性**」问题：晋级条件第 1 条的强口径卡在这里
（增补四 §8：四条里唯一不满足的就是 ①「≥3 个 seed 受控 ≥ 半数」，K=1 只有 1/6、K=2 只有 2/6）。

**本实验只回答一个问题**：双峰的分岔在训练过程里**什么时候**已经可观测。
不修任何东西、不动 teacher、不动 obs 契约、不改门禁（ADR-A-003 立场不变，A-4 明确暂缓）。

## 2. 判别量与簇归属（冻结）

每臂每 checkpoint 跑 20 局闭环（pinned seeds 5000–5019、horizon 300、无 guard、`--log-actions`），
用 `scripts/a_closed_loop_dz_diag.py` 的既有口径算尾段（`tail_window_start = 100`）dz 统计：

| 记号 | 定义 |
|---|---|
| `dz_pos_frac_tail` | 尾段帧里 dz 命令 > 0 的占比 |
| `dz_mean_tail` | 尾段帧 dz 命令的均值 |

三级序数归属（**判据来自增补四 §11-A④ 与 §18/§21.8，不得事后调整**）：

| 级别 | 判据 | 含义 |
|---|---|---|
| `HIGH` | `dz_pos_frac_tail ≥ 0.9` **且** `dz_mean_tail ∈ [0.024, 0.034]` | 已落在高分簇（= L2 修复的预登记成功判据） |
| `POS_BIAS` | `dz_pos_frac_tail ≥ 0.9` **且** `dz_mean_tail ∉ [0.024, 0.034]` | 正偏置方向已建立、幅度未到带 |
| `NONPOS` | `dz_pos_frac_tail < 0.9` | 正偏置未建立（低分簇特征） |

**样本内声明（必须随结果一起引用）**：上述两个阈值（`0.9` 与 `[0.024, 0.034]`）来自当前
**6 个 K=1 seed + 6 个 K=2 seed 的样本内分离**——`dz_pos_frac_tail` 实测 0.9465+ 对 0.2430−（中间空 0.7），
`dz_mean_tail` 高分 5 臂 0.0248–0.0336、其余 15 臂 −0.0138–0.0184。
本实验的 `010000` 时间点是这套阈值的**首次样本外使用**，结果无论是否符合都必须原样报告；
若样本外表现差，只能**新写一份预登记**，不得回填调整本文档的阈值。

## 3. 分辨率上限（**结论强度的硬约束**）

- `checkpoints/last -> 020000` 是**符号链接**，`save_freq=10000` → 每臂只有 **2 个互异 checkpoint**：
  `010000` 与 `020000`。已实测确认（4 臂的 `checkpoints/` 目录列表均为 `010000 / 020000 / last -> 020000`）。
- ⇒ 本实验能给出的**最强**结论只有两种措辞：
  1. 「分岔**不晚于 10k**」（`010000` 上两臂已分属不同级别）；
  2. 「分岔**发生在 10k–20k 之间**」（`010000` 同级、`020000` 分开）。
- **禁止**写「分岔发生在第 X 步」「在第 N 步附近」或任何更细的时间定位。要更细必须重训并加密 `save_freq`，
  那是新臂、需要新的预登记与登记记录（且属 A-4 暂缓范围之外的一次算力申请）。

## 4. 首批臂清单（极端对，省算力；4 臂 × 2 ckpt = **8 次评测 / 160 局**）

| 族（口径） | 高分臂 | 低分臂 | 选择理由 |
|---|---|---|---|
| K=1（1/1/1） | `trimdone0_minmax_k1_lr1e-5_s20k_seed0`（受控 20/20、`dz_pos_frac_tail` 0.99925、`dz_mean_tail` +0.03114） | `trimdone0_minmax_k1_lr1e-5_s20k_seed4`（受控 0/20、0.07375、**−0.01384**） | seed4 是全部 21 臂里 `dz_mean_tail` **最负**的一个；两端拉满，信号最强 |
| K=2（2/2/2） | `trimdone0_minmax_k2_lr1e-5_s20k_seed4`（受控 19/20、0.0280） | `trimdone0_minmax_k2_lr1e-5_s20k_seed2`（受控 0/20、0.0082） | seed4 是门槛稳健臂（19/19/19/19/18）；seed2 是**测量有效**的 0/20（不是 INVALID，避免把测量问题混进来） |

两族各取一对，是为了区分「双峰是 K 相关的现象」还是「跨口径的共同现象」。
`k2 seed0` 不入选：它是 `VALID_probe_exonerated`（裁定 10），带免罪标注的臂不进本实验的判据样本。

## 5. 判定规则（**跑之前写死**）

对每一族，比较高分臂 H 与低分臂 L 在 `010000` / `020000` 两个时间点的级别：

| 规则 | 条件 | 允许的结论措辞 |
|---|---|---|
| **R1** | `010000` 上 H 与 L 已分属不同级别 | 「分岔**不晚于 10k**」 |
| **R2** | `010000` 同级，`020000` 分开 | 「分岔**发生在 10k–20k 之间**」 |
| **R3** | 两个时间点都同级（未分开） | 「**本分辨率下未能定位分岔**」；同时必须报告 `020000` 的 dz 值与留档 actlog 是否一致 |
| **R4** | 任一臂任一 ckpt 的 `input_contract` 判 INVALID（`mean_blown_frames_frac > 0.05`） | 该**时间点**不得用于分岔主张，只能报「该时间点测量无效」；若该族因此缺一侧，该族结论降级为 R3 并登记原因 |
| **R5**（一致性自检，先行门槛） | `020000` 重跑的 `dz_pos_frac_tail` / `dz_mean_tail` / 逐局 `max_rise` 必须与**留档 actlog** 一致 | 不一致 ⇒ **整批作废重查**（说明评测器或环境有漂移），不得先解释分岔 |
| **R6** | 两族结论矛盾（一族 R1、另一族 R3） | 只报「族内结论」，**不得**合并成跨口径主张；并触发 §7 的扩围 |

R5 先于 R1–R4 判定：`020000` 是已知答案的时间点，它不过关就说明测的不是同一件事。

## 6. 输入契约要求（每个 checkpoint 都要记）

- 每个 (臂, ckpt) 的产物都必须带完整 `input_contract`：`blowup_threshold`、`threshold_semantics`、
  `min_std`、`blown_metric_impl`、逐局 `norm_input_frames_measured / norm_input_blown_frames_frac /
  norm_input_out_of_range_frames_frac / norm_input_absmax / norm_input_top_dim`。
- **早期 checkpoint 更可能 OOD**（normalizer stats 来自数据集、但策略还没收敛，闭环偏离 teacher 更远），
  所以 `010000` 的 blown 有可能超阈。按 R4：超阈 ⇒ 该时间点 INVALID ⇒ **不得**用于分岔主张。
- 引用任何 blown 数字必须带**阈值来源 + 产出路径 + `gate_build`**（裁定 11 / 裁定 12）。
- **禁止**把 blown 超阈写成「炸穿导致该 ckpt 失败」；只能写「该时间点测量无效，能力未知」（裁定 12）。

## 7. 扩围条件（只在信号不清时才花算力）

首批 8 次评测后，**仅当**出现下列情况之一才扩围：

1. 两族都判 R3（未分开）；
2. 两族结论矛盾（R6）；
3. 任一臂任一 ckpt 因 R4 失效，导致该族只剩单侧。

扩围清单（**再 8 臂的 `010000` 时间点**，各 20 局）：K=1 `seed1 / seed2 / seed3 / seed5`、
K=2 `seed1 / seed3 / seed5` 与 `trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0`。
扩围不改判据、不改判定规则，只增加样本；扩围前须在本文档**追加**一节说明触发的是哪一条（1/2/3），
不得删改 §2–§6 的任何内容。

## 8. 产物路径与命名（独立子目录，留档一字节不动）

| 项 | 路径 |
|---|---|
| 闭环 actlog 产物 | `runs/infra/lerobot_act_env_20260928/ckptseq/actlog_<arm>__step<NNNNNN>.json` |
| 门禁裁定（v1.2.1 单一构建） | `runs/infra/lerobot_act_env_20260928/ckptseq/gate_<arm>__step<NNNNNN>.json` |
| dz 归因 | `runs/infra/lerobot_act_env_20260928/ckptseq/dz_diag_ckptseq.json` |
| 汇总判定 | `runs/infra/lerobot_act_env_20260928/ckptseq/divergence_verdict.json` |

刻意**不进**主目录 glob：`arms_summary.json` 与 `gate_threshold_sensitivity_A.json` 的臂集是
「20k 步交付臂」，中间 checkpoint 不是交付臂，混进去会污染 48 臂权威表（A-1）。

## 9. 不做什么（边界）

- 不做任何 L2 修复（teacher 去饱和 / obs 加 `cube_z − z0` / 相位重加权采样）——A-4 明确暂缓，
  且 `RISE_CAP=0.15` / `FINAL_RISE_MIN=0.04` 都绑在旧 teacher 的 base-only 0.0764 m 上，
  在双峰有答案前重置会连做两次重置并废掉 48 臂比较集。
- 不改门禁、不改 B 的文件（裁定 8 的落地归 B）。
- 不声称因果：本实验只能给出「分岔**何时可观测**」，不能给出「什么训练动力学**导致**分岔」。
  后者需要加密 checkpoint + 训练侧探针，是另一份预登记。
- 不做跨口径排序：K=1 的推理次数是 K=4 的 4 倍（增补四 §9），两族结论只能族内陈述。

---

## 10. 扩围追加（2026-09-28 21:42:35 落盘，**在扩围评测启动之前**；§2–§6 一字未改）

### 10.1 触发的是哪一条

**§7 条件 2：两族结论矛盾（R6）**。首批 4 臂 × 2 ckpt = 8 次评测（160 局）跑完，
`ckptseq/divergence_verdict.json`（判定器 `scripts/a_ckptseq_verdict.py`，只读）给出：

| 族 | `010000` 高分臂 / 低分臂 | `020000` 高分臂 / 低分臂 | 判定 | 允许措辞 |
|---|---|---|---|---|
| K=1（1/1/1） | `NONPOS`(ctrl 0/20) / `NONPOS`(ctrl 1/20) ⇒ 同级 | `HIGH`(20/20) / `NONPOS`(0/20) ⇒ 分开 | **R2** | 分岔**发生在 10k–20k 之间** |
| K=2（2/2/2） | `NONPOS`(5/20) / **`HIGH`**(15/20) ⇒ **已分开** | `HIGH`(19/20) / `NONPOS`(0/20) ⇒ 分开 | **R1** | 分岔**不晚于 10k** |

两族时间窗不一致（R2 vs R1）⇒ 按 R6 **只报族内结论，不得合并成跨口径主张**，并按 §7 扩围。

### 10.2 先行门槛 R5 的结果（必须先过，已过）

4 臂的 `020000` 重跑与留档**逐局** `max_rise` / `final_rise` 一致，
`dz_pos_frac_tail` / `dz_mean_tail` 与 `closed_loop_dz_diag_A.json` 一致，
聚合量（`success_raw` / `success_rise` / `mean_max_rise` / `mean_final_rise`）一致 ⇒ **R5 PASS（4/4 IDENTICAL）**。
所以本批不是评测器/环境漂移，可以继续解释分岔。

### 10.3 R4 未触发（输入契约全部有效）

8 个 (臂, ckpt) 的 `input_contract.status` 全为 `verified_ok`，`mean_blown_frames_frac` 最大
**0.0082**（`k1 seed4@010000`）< 容差 0.05；阈值来源 `train24_trimdone0` 族 **12.469445**
（`policy_preprocessor_step_3_normalizer_processor.safetensors`，按各 ckpt 自己的 normalizer stats 现算），
门禁构建 `v1.2.1 / e4f5ec887788 / spec 494d5f5babf9`。⇒ **没有任何时间点因 blown 超阈被判 INVALID**，
R1/R2 的判定不依赖被排除的时间点。

### 10.4 样本外表现（增补四 §11-A④：原样报告，**不回调阈值**）

`010000` 是 §2 阈值（`dz_pos_frac_tail ≥ 0.9` 且 `dz_mean_tail ∈ [0.024, 0.034]`）的**首次样本外使用**：

| 臂（`010000`） | `dz_pos_frac_tail` | `dz_mean_tail` | 级别 | 受控 | `mean_max_rise` |
|---|---|---|---|---|---|
| `k1 seed0` | 0.00000 | −0.02750 | `NONPOS` | 0/20 | 0.00000 |
| `k1 seed4` | 0.15800 | −0.00830 | `NONPOS` | 1/20 | 0.00313 |
| `k2 seed2` | 1.00000 | +0.02887 | **`HIGH`** | **15/20** | 0.06412 |
| `k2 seed4` | 0.74575 | +0.01504 | `NONPOS` | 5/20 | 0.02136 |

判据在样本外**仍然把「抬得起来」和「抬不起来」分开了**（`k2 seed2@10k` 判 `HIGH`，实测 15/20、
`mean_max_rise` 0.0641 m，已越过 `FINAL_RISE_MIN=0.04`），没有出现「判 `HIGH` 却 0/20」的假阳性。
但**方向与 20k 的成败相反**：`k2 seed2` 在 10k 是 `HIGH`（15/20），到 20k 变 `NONPOS`（0/20）；
`k2 seed4` 在 10k 是 `NONPOS`（5/20），到 20k 变 `HIGH`（19/20）。
`level_at_10k_predicts_20k_outcome = False`（两族都是 False）。

**这条改变问题的性质，必须写明**：20k 快照上的「种子双峰」**不是**一个稳定的 seed 属性——
至少 `k2 seed2` 在 10k 已经具备受控抬起能力、在 20k 失去了它。因此：
1. 「seed 单独决定成败」只能限定为「**seed × checkpoint** 共同决定」；
2. 把 `checkpoints/last`（=020000）当唯一交付点，是一个**未被验证的选择**：同一臂在 10k 可能更好；
3. §1 引用的「21 臂里受控 4–9 的臂数 = 0」是 20k 快照的性质，**不能**外推成训练全程的性质。
> **更正指针（裁定 30 / DR-D29，2026-09-29 由 A 追加；原文按 append-only 一字未改）**：上句是**分布层**陈述，
> 只在 **v1.2.1 / `e4f5ec887788`** 口径下成立 —— 那时 `trimdone0_minmax_k2_lr1e-5_s20k_seed0`（9/20）是
> `NOT_CITABLE_measurement_invalid`、**不在**有效臂分布里。裁定 10 的探针免罪在 **v1.5 / `f19f61341cbe`**
> 落地（裁定 26/27/28，D 已复签）后它 `measurement_valid=True`、**重回分布** ⇒ 21 actlog 臂集里落在
> 4–9 的臂数实测 **= 1**（就是免罪臂本尊），「= 0」**自此禁用**，「中间是空的」也禁用。
> 准确定性 =「**强间隙分离（gap-separated）**」：低簇 0–3（**15** 臂）／高簇 14–20（**5** 臂）／
> **孤立 1 臂 = 9**（`VALID_probe_exonerated`、`probe_kind=clip_at_train_absmax`），
> **空带是 4–8 与 10–13**，不是「4–9」。引用双峰必须带四限定：**臂集 / 20k 快照 / 构建指纹 /
> 显式点出中间带孤立臂**。全文见 `rl_harness_supervision/supervisor_memo_20260929.md` 增补七 §20
> 与本文档 §14；机器判据 = `scripts/a_distribution_layer_check.py`（D2 / D3 / D6，A 不自免）。

以上 3 条只改**陈述口径**，不改 §2 的判据、不改 §5 的判定规则、不改 §4 的臂清单。

### 10.5 扩围清单（= §7 原文，不增不减）

再 **8 臂的 `010000` 时间点**，各 20 局（pinned seeds 5000–5019、horizon 300、`--log-actions`）：
K=1 `seed1 / seed2 / seed3 / seed5`、K=2 `seed1 / seed3 / seed5`、`trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0`。
8 臂的 `checkpoints/` 已确认都存在互异的 `010000`（`010000 / 020000 / last -> 020000`）。

扩围要回答的两个问题（都在原判据内，不新增判据）：
- **Q1**：`010000` 快照上，K=1 / K=2 各有几个 seed 判 `HIGH`、各有几个受控 ≥ 半数（10/20）？
  —— 直接对应晋级条件 ①（增补四 §8：K=1 只有 1/6、K=2 只有 2/6 满足）在 10k 上是否成立。
- **Q2**：`HIGH@10k` 与 `HIGH@20k` 的臂集合重叠多少？重叠少 ⇒ 「20k 交付点」这个选择本身就是
  双峰的一个来源（而非 seed 本身）。

### 10.6 扩围产物路径（append-only，首批留档一字节不动）

| 项 | 路径 |
|---|---|
| 8 臂 actlog | `ckptseq/actlog_<arm>__step010000.json` |
| 8 臂门禁（v1.2.1 单一构建） | `ckptseq/gate_<arm>__step010000.json` |
| 12 臂 dz 归因（新文件） | `ckptseq/dz_diag_ckptseq_all.json` |
| 扩围后判定（新文件） | `ckptseq/divergence_verdict_all.json` |
| 首批 dz 归因副本 | `ckptseq/dz_diag_ckptseq_batch1.json`（原件 `dz_diag_ckptseq.json` 保留不动） |
| 首批判定（**已落盘，不再改**） | `ckptseq/divergence_verdict.json` |

首批的 `dz_diag_ckptseq.json` 只含 4 臂 × 2 ckpt；扩围后**另写** `dz_diag_ckptseq_all.json`，
不覆盖首批文件，判定器用 `--dz` 指定读哪一份，两批各自可复核。

---

## 11. 增补五 §5 要求的更正节与 R7 落地（2026-09-28 21:49 追加；§2–§6 原文与阈值**一字未改**）

监管依据：`rl_harness_supervision/supervisor_memo_20260928.md` 增补五 §5（批准冻结，但 §2 有一处
**事实错误**必须更正，不改阈值，只加报告义务）、§6（首个结果改写了本实验要回答的问题）、
§8 A-2（按 §5 追加 R7 与更正节；K=2 家族结论必须带阈值敏感标注）。

### 11.1 §2 样本内声明的事实更正（A 独立复算确认）

§2 原文写「`dz_pos_frac_tail` 实测 0.9465+ 对 0.2430−（**中间空 0.7**）」。A 用
`closed_loop_dz_diag_A.json`（21 臂）独立复算，**确认 D 的更正**：

- 升序全谱：`0.0737 / 0.1885 / 0.2077 / 0.2430 / 0.5677 / 0.6690 / 0.7780 / 0.8330 / 0.8670 /
  0.9400 / 0.9417 / 0.9455 / 0.9465 / 0.9493 / 0.9500 / 0.9525 / 0.9575 / 0.9692 / 0.9992 / 1.0000 / 1.0000`
- 全 21 臂**最大空隙 = 0.3247**（`0.2430 → 0.56775`），不是 0.7；「中间空 0.7」**只在 K=1 六 seed 内成立**
  （K=1：0.0737 / 0.1885 / 0.2077 / 0.2430 vs 0.9465 / 0.9992）。
- `0.9` 这个切点落在**密集簇内部**：`[0.85, 0.95]` 有 **7 臂**、`[0.80, 0.95]` 有 **8 臂**；
  切点两侧最近点是 `0.8670`（`k2 seed2`）与 `0.9400`，间距仅 **0.073**。
- K=2 六 seed 有三个落在所谓空档里：`seed0 0.5677`、`seed5 0.6690`、`seed2 0.8670`。

⇒ 表述纪律：**不得**再写「`dz_pos_frac_tail` 把臂一刀两断、中间空 0.7」；该说法只在 K=1 六 seed 内成立。
阈值 `0.9` 与带 `[0.024, 0.034]` **不改**（21:14:53 已冻结，事后改等于预登记失效）。

### 11.2 §4 臂清单表补全（D 指出的漏项）

§4 对 K=2 那一对只给了 `dz_mean_tail`（0.0280 / 0.0082，且未标名），漏给了级别归属的**第一判据**
`dz_pos_frac_tail`。补全如下（20k 留档 actlog 口径）：

| 族 | 角色 | 臂 | `dz_pos_frac_tail` | `dz_mean_tail` | 20k 级别 | 20k 受控 |
|---|---|---|---|---|---|---|
| K=1 | 高分 | `trimdone0_minmax_k1_lr1e-5_s20k_seed0` | **0.99925** | +0.03114 | `HIGH` | 20/20 |
| K=1 | 低分 | `trimdone0_minmax_k1_lr1e-5_s20k_seed4` | **0.07375** | −0.01384 | `NONPOS` | 0/20 |
| K=2 | 高分 | `trimdone0_minmax_k2_lr1e-5_s20k_seed4` | **1.00000** | +0.02803 | `HIGH` | 19/20 |
| K=2 | 低分 | `trimdone0_minmax_k2_lr1e-5_s20k_seed2` | **0.86700** | +0.00823 | `NONPOS`（距 0.9 仅 **0.033**） | 0/20 |

即：K=2 低分臂的 `NONPOS` 归属**本来就贴着切点**，这是 D 预警的敏感点，也是 R7 存在的原因。

### 11.3 R7 的实现与首批结果（判定器机器算，不手填）

R7 已实现进 `scripts/a_ckptseq_verdict.py`（只读判定器）：对每个 (臂, ckpt) 报
`dz_pos_frac_tail ∈ [0.85, 0.95]` 的敏感标记 + 按 `0.85 / 0.90 / 0.95` 三种切法的级别归属，
并把整条判定规则（R1/R2/R3）在三种切法下各重跑一遍，输出 `verdict_by_cut` 与
`verdict_stable_across_cuts`。产物字段：`families.<族>.r7_sensitive_cells` / `r7_threshold_sensitive` /
`verdict_by_cut` / `verdict_stable_across_cuts`。

首批 4 臂 × 2 ckpt 的 R7 结果（`ckptseq/divergence_verdict.json`）：

| 族 | 敏感格 | 三切法下的判定 | 结论措辞 |
|---|---|---|---|
| K=1 | **无**（0.0000 / 0.1580 / 0.99925 / 0.07375 都远离 0.9） | `0.85→R2`、`0.90→R2`、`0.95→R2`，稳定 | 「分岔**发生在 10k–20k 之间**」，**可独立陈述** |
| K=2 | **1 个**：`k2 seed2@020000`，`dz_pos_frac_tail=0.867`（`0.85` 切法判 `POS_BIAS`；`0.90/0.95` 切法判 `NONPOS`） | `0.85→R1`、`0.90→R1`、`0.95→R1`，稳定 | 「分岔**不晚于 10k**」，**必须带「级别归属对阈值敏感」标注** |

**K=2 家族结论（带 R7 标注，引用时必须整条带上）**：分岔**不晚于 10k**；
**级别归属对阈值敏感**（`k2 seed2@020000` 的 `dz_pos_frac_tail=0.867` 落在 `[0.85,0.95]`，
换 `0.85` 切法会从 `NONPOS` 变 `POS_BIAS`）。但 **R1 这个判定本身在 0.85 / 0.90 / 0.95 三种切法下都成立**，
因为 `010000` 上的分离是 `1.00000`（seed2）对 `0.74575`（seed4），两侧都离 0.9 切点很远
（敏感只出现在 `020000` 的 seed2 上，而 R1 的判据用的是 `010000` 已分开）。
⇒ D 预警的「K=2 侧 R1 可能是切点造成的」在首批数据上**未被证实**：分离由 `010000` 提供，与切点无关。

### 11.4 §6 的问题改写与首批答案

增补五 §6：首个结果（`k1 seed0@010000` 是 ctrl 0/20、`raw=0`、`mean_max_rise=0.0`）把本实验的问题
从「成功臂何时开始成功」改写成「**行为上同为 0/20 时，dz 判别量是否已经分开**」。A 确认这一改写，
并按首批 8 次评测作答：

- **K=1：答案是否定的。** `010000` 上两臂行为都近乎 0（ctrl 0/20 与 1/20、`mean_max_rise` 0.00000 与 0.00313），
  dz 判别量也**没有**分开（`dz_pos_frac_tail` 0.0000 与 0.1580，同判 `NONPOS`）。
  ⇒ D 期望的「判别量先于行为成功」这个**更强结果在 K=1 上不成立**；K=1 的分岔只能定位到 10k–20k 之间（R2）。
- **K=2：判别量与行为同向，不存在「先于」关系。** `010000` 上 seed2 已是 ctrl **15/20**、
  `mean_max_rise` **0.06412 m**（越过 `FINAL_RISE_MIN=0.04`）、判 `HIGH`；seed4 是 ctrl 5/20、判 `NONPOS`。
  ⇒ 判别量在 K=2 上是**跟随**行为、不是**领先**行为。

**这条改写了 20k 双峰的定性（必须随结果一起引用）**：`k2 seed2` 在 10k **已经具备**受控抬起能力（15/20），
到 20k **失去**了它（0/20、`dz_pos_frac_tail` 0.867、`mean_max_rise` 0.00198）。所以
「同一配方下 seed 单独决定成败」只能限定为「**seed × checkpoint 共同决定**」；
把 `checkpoints/last`（=020000）当唯一交付点是一个**未被验证的选择**；
§1 的「21 臂里受控 4–9 的臂数 = 0」是 **20k 快照**的性质，不能外推到训练全程。
> **更正指针（裁定 30 / DR-D29，2026-09-29 由 A 追加；原文按 append-only 一字未改）**：上句是**分布层**陈述，
> 只在 **v1.2.1 / `e4f5ec887788`** 口径下成立 —— 那时 `trimdone0_minmax_k2_lr1e-5_s20k_seed0`（9/20）是
> `NOT_CITABLE_measurement_invalid`、**不在**有效臂分布里。裁定 10 的探针免罪在 **v1.5 / `f19f61341cbe`**
> 落地（裁定 26/27/28，D 已复签）后它 `measurement_valid=True`、**重回分布** ⇒ 21 actlog 臂集里落在
> 4–9 的臂数实测 **= 1**（就是免罪臂本尊），「= 0」**自此禁用**，「中间是空的」也禁用。
> 准确定性 =「**强间隙分离（gap-separated）**」：低簇 0–3（**15** 臂）／高簇 14–20（**5** 臂）／
> **孤立 1 臂 = 9**（`VALID_probe_exonerated`、`probe_kind=clip_at_train_absmax`），
> **空带是 4–8 与 10–13**，不是「4–9」。引用双峰必须带四限定：**臂集 / 20k 快照 / 构建指纹 /
> 显式点出中间带孤立臂**。全文见 `rl_harness_supervision/supervisor_memo_20260929.md` 增补七 §20
> 与本文档 §14；机器判据 = `scripts/a_distribution_layer_check.py`（D2 / D3 / D6，A 不自免）。

### 11.5 措辞白名单 / 黑名单（本实验所有产物与文档一律适用）

| 允许 | 禁止 |
|---|---|
| 「分岔**不晚于 10k**」（R1） | 「分岔发生在第 X 步」「在第 N 步附近」 |
| 「分岔**发生在 10k–20k 之间**」（R2） | 「10k 时模型已经学会/还没学会」这类超出分辨率的表述 |
| 「本分辨率下**未能定位**分岔」（R3） | 「炸穿导致该 ckpt 失败」（裁定 12；blown 超阈只能写「该时间点测量无效，能力未知」） |
| K=2 结论 + 「**级别归属对阈值敏感**」标注 | 把 `HIGH/POS_BIAS/NONPOS` 说成「一刀两断、中间空 0.7」（只在 K=1 六 seed 内成立） |
| 「seed × checkpoint 共同决定」 | 「seed 单独决定成败」（20k 快照性质，已被 §11.4 限定） |
| 族内陈述（K=1 / K=2 各自） | 跨口径合并主张（R6：两族结论不一致；且 K=1 推理次数是 K=4 的 4 倍） |

---

## 12. 扩围结果（2026-09-28 22:03 落盘）：判据不变，结论按 §5 规则给出

产物：`ckptseq/divergence_verdict_all.json`（判定器 `scripts/a_ckptseq_verdict.py --dz dz_diag_ckptseq_all.json`，只读）。
扩围实跑 **8 臂 × 20 局 = 160 局**（`010000` 时间点），加首批共 **12 臂 × 10k + 4 臂 × 20k = 320 局**。
20k 侧**不重跑**：留档 actlog + `closed_loop_dz_diag_A.json` 就是 `020000` 的权威产物，R5 已证 4 臂重跑逐局一致。
`k2 seed0` 按 §4 排除（`VALID_probe_exonerated` 臂不进判据样本）；stdfloor 是**另一数据配方**，单列不并入 K=2 族。

### 12.1 R4 首次触发：一个时间点测量无效

| (臂, ckpt) | `mean_blown_frames_frac` | 容差 | 阈值来源 | `input_contract.status` | 处置 |
|---|---|---|---|---|---|
| `k1 seed1 @ 010000` | **0.0532** | 0.05 | **12.469445**（该 ckpt 自己的 normalizer stats，`train24_trimdone0` 族） | `violated` | **该时间点测量无效、能力未知**；其 `6/20` **不得引用**，也不进 §12.3 的 Q1 计数（R4 / 裁定 12） |
| `k1 seed3 @ 010000` | 0.0473 | 0.05 | 12.469445 | `verified_ok` | 未超阈，但已达容差的 **94.6%** → 登记为**近阈**，引用时须带 blown 值 |

其余 10 个 (臂, ckpt) 全 `verified_ok`，blown ≤ 0.0210。**首批 8 个时间点无一超阈**（最大 0.0082），
所以 §11.3 的 R1 / R2 判定不依赖任何被排除的时间点。
按裁定 12：`k1 seed1@010000` **不得**写成「炸穿导致它失败」，只能写「该时间点测量无效，能力未知」。

### 12.2 12 臂 `010000` vs `020000`（留档）全表

| 臂 | 族 | 10k `dz_pos_frac_tail` | 10k `dz_mean_tail` | 10k 级别 | 10k 受控 | 20k `dz_pos_frac_tail` | 20k `dz_mean_tail` | 20k 级别 | 20k 受控 |
|---|---|---|---|---|---|---|---|---|---|
| `k1 seed0` | K=1 | 0.00000 | −0.02750 | `NONPOS` | 0/20 | 0.99925 | +0.03114 | `HIGH` | **20/20** |
| `k1 seed1` | K=1 | 0.62950 | +0.01554 | `NONPOS` | ~~6/20~~ **INVALID** | 0.24300 | −0.00087 | `NONPOS` | 0/20 |
| `k1 seed2` | K=1 | 0.08550 | −0.00752 | `NONPOS` | 1/20 | 0.18850 | −0.00165 | `NONPOS` | 0/20 |
| `k1 seed3` | K=1 | 0.04800 | −0.00980 | `NONPOS` | 0/20 | 0.94650 | +0.01719 | `POS_BIAS` | 2/20 |
| `k1 seed4` | K=1 | 0.15800 | −0.00830 | `NONPOS` | 1/20 | 0.07375 | −0.01384 | `NONPOS` | 0/20 |
| `k1 seed5` | K=1 | 0.94125 ⚠ | +0.03517 | `POS_BIAS` | 2/20 | 0.20775 | −0.00299 | `NONPOS` | 0/20 |
| `k2 seed1` | K=2 | 0.20825 | +0.00027 | `NONPOS` | 0/20 | 0.94175 | +0.01549 | `POS_BIAS` | 2/20 |
| `k2 seed2` | K=2 | 1.00000 | +0.02887 | **`HIGH`** | **15/20** | 0.86700 ⚠ | +0.00823 | `NONPOS` | 0/20 |
| `k2 seed3` | K=2 | 1.00000 | +0.04372 | `POS_BIAS` | 5/20 | 0.94925 | +0.03358 | `HIGH` | **17/20** |
| `k2 seed4` | K=2 | 0.74575 | +0.01504 | `NONPOS` | 5/20 | 1.00000 | +0.02803 | `HIGH` | **19/20** |
| `k2 seed5` | K=2 | 0.94875 ⚠ | +0.02686 | **`HIGH`** | **15/20** | 0.66900 | +0.00882 | `NONPOS` | 1/20 |
| `stdfloor k2 seed0` | stdfloor | 1.00000 | +0.03787 | `POS_BIAS` | **18/20** | 0.95250 | +0.02496 | `HIGH` | 16/20 |

⚠ = R7 敏感格（`dz_pos_frac_tail ∈ [0.85, 0.95]`，级别归属随切点变）：
`k1 seed5@10k`(0.94125：`0.85/0.90` 切法 `POS_BIAS`、`0.95` 切法 `NONPOS`)、
`k2 seed5@10k`(0.94875：`0.85/0.90` 切法 `HIGH`、`0.95` 切法 `NONPOS`)、
`k2 seed2@20k`(0.86700：`0.85` 切法 `POS_BIAS`、`0.90/0.95` 切法 `NONPOS`)。
引用这三格必须带「级别归属对阈值敏感」标注。

### 12.3 Q1 / Q2 的答案（§10.5 预登记的两个问题）

**Q1：晋级条件①（同族 ≥3 个 seed 受控 ≥ 半数 = 10/20）在 `010000` 上成立吗？→ 不成立。**

| 族 | n | 10k 级别分布 | 10k ≥半数 | 20k ≥半数 | 条件① @10k | 条件① @20k |
|---|---|---|---|---|---|---|
| K=1（1/1/1） | 6 | `NONPOS`×5、`POS_BIAS`×1 | **0**（且 `seed1` 时间点 INVALID 不计） | 1（`seed0`） | **不满足** | 不满足 |
| K=2（2/2/2） | 5 | `NONPOS`×2、`POS_BIAS`×1、`HIGH`×2 | **2**（`seed2`、`seed5`） | 2（`seed3`、`seed4`） | **不满足** | 不满足 |
| stdfloor（另一配方） | 1 | `POS_BIAS`×1 | 1（`seed0` 18/20） | 1（`seed0` 16/20） | n=1 无法判 | n=1 无法判 |

⇒ **换 checkpoint 不能满足晋级条件①**：10k 与 20k 两个时间点上都只有 ≤2 个 seed 过线。
§8 的「部分满足」维持不变，且现在有了**两个时间点**的证据（不是只有 20k 快照）。

**Q2：`HIGH@10k` 与 `HIGH@20k` 的臂集合重叠多少？→ 0（两族都不重叠）。**

| 族 | `HIGH@10k` | `HIGH@20k` | 重叠 | 「≥半数」集合 10k vs 20k | 重叠 |
|---|---|---|---|---|---|
| K=1 | ∅ | `{seed0}` | **0** | ∅ vs `{seed0}` | **0** |
| K=2 | `{seed2, seed5}` | `{seed3, seed4}` | **0** | `{seed2, seed5}` vs `{seed3, seed4}` | **0** |
| stdfloor | ∅（`POS_BIAS`） | `{seed0}` | **0** | `{seed0}` vs `{seed0}` | 1 |

⇒ **「哪些 seed 是好 seed」在 10k 与 20k 上是两个不相交的集合**（K=2：`{2,5}` → `{3,4}`）。
这是对 §1「seed 单独决定成败」的**直接否证**：好坏不是 seed 的稳定属性，而是
**seed × checkpoint** 的属性；`checkpoints/last`（=020000）作为唯一交付点是一个**未被验证的选择**。

### 12.4 样本外表现（增补四 §11-A④ 的报告义务，**阈值未改**）

只用第一判据 `dz_pos_frac_tail ≥ 0.9` 切两半（描述统计，不是新判据；INVALID 时间点不参与）：

| 时间点 | `≥0.9` 半区 | `<0.9` 半区 |
|---|---|---|
| `010000`（样本外） | n=5、受控均值 **11.0/20**、区间 [2, 18] | n=6、受控均值 **1.167/20**、区间 [0, 5] |
| `020000`（留档，样本内来源） | n=6、受控均值 **12.667/20**、区间 [2, 20] | n=6、受控均值 **0.167/20**、区间 [0, 1] |

- **成立的部分**：`dz_pos_frac_tail ≥ 0.9` 在样本外（10k）仍然把两半的受控成功均值分开
  （11.0 对 1.167，约 **9.5 倍**）；没有出现「判 `HIGH` 却 0/20」的假阳性
  （`HIGH@10k` 的两臂实测 15/20 与 15/20）。
- **不成立的部分（必须一起报）**：`dz_mean_tail ∈ [0.024, 0.034]` 这个**带上界在样本外低估能力** ——
  `stdfloor k2 seed0@10k`（`dz_mean_tail` 0.03787、实测 **18/20**）与 `k2 seed3@10k`（0.04372、5/20）
  都因超出上界被判 `POS_BIAS` 而非 `HIGH`。⇒ 带内判据是**样本内拟合**的产物，
  10k 上「抬得起来」的臂可以落在带的**上方**；`dz_pos_frac_tail` 比 `dz_mean_tail` 带更稳。
- **处置**：不改阈值（21:14:53 已冻结）。若要改，必须**新写一份预登记**，且新预登记只能在
  下一批新臂上生效，不得回填本批。

### 12.5 本实验允许写的结论（措辞白名单，逐条对应 §5 / §11.5）

1. **K=1 族（可独立陈述，三切点稳定，无 R7 敏感格）**：分岔**发生在 10k–20k 之间**（R2）。
   依据：`010000` 上两臂同判 `NONPOS`（0.00000 / 0.15800），`020000` 上分开（`HIGH` 0.99925 对 `NONPOS` 0.07375）。
2. **K=2 族（必须带敏感标注）**：分岔**不晚于 10k**（R1）；**级别归属对阈值敏感**
   （`k2 seed2@020000` 的 0.86700 落在 `[0.85,0.95]`）。但 **R1 这个判定在 0.85/0.90/0.95 三种切法下都成立**，
   因为分离由 `010000` 提供（1.00000 对 0.74575，两侧都远离切点）。
3. **R6：两族结论不一致（R2 对 R1）⇒ 只报族内结论，不得合并成跨口径主张**；
   且 K=1 的推理次数是 K=4 的 4 倍，两族本就不可排序。
4. **扩围新增（Q1/Q2）**：晋级条件① 在 10k 与 20k **都不满足**；`HIGH` 集合与「≥半数」集合
   在两个时间点**完全不重叠** ⇒ 「seed 单独决定成败」改判为「**seed × checkpoint 共同决定**」。
5. **R5 先行门槛 PASS**（4/4 臂 `020000` 重跑与留档逐局一致）⇒ 以上都不是评测器/环境漂移。
6. **`k1 seed1@010000` 测量无效**（blown 0.0532 > 0.05，阈值 12.469445 来自该 ckpt 自己的 stats）：
   能力未知，不得当 0 分用，也不得写「炸穿导致失败」。

**本实验不回答的**：什么训练动力学**导致**分岔（需要加密 `save_freq` + 训练侧探针，属新预登记）；
分岔发生在第几步（分辨率上限只有 2 个互异 ckpt）；哪个 checkpoint「更好」（需要新的选择准则与新的比较集）。

---

## 13. gate_build 漂移的处置（2026-09-28 22:40 追加；**§2–§6 原文与阈值一字未改**）

本节只处理一件事：**§6 要求「在 v1.2.1 单一构建上判」，但落盘的 16 份 gate 横跨 7 个 `gate_build`**。
这是产物卫生问题，不是判据问题；处置全程**不重跑任何评测、不改任何阈值、不动任何 actlog**。

### 13.1 漂移是怎么发生的（事实）

`GATE_BUILD = sha256(门禁脚本自身内容)[:12]`。B 线在 A-2 跑动期间（21:16–21:52）实时升级门禁，
于是同一批产物被判在 7 个构建上：

| gate_version | gate_build | spec | 份数 |
|---|---|---|---|
| v1.2.1 | `e4f5ec887788` | `494d5f5babf9` | 2 |
| v1.3 | `4f20b3ec9130` | `c9303525112a` | 8 |
| v1.3 | `5d20e5a2dffe` | `494d5f5babf9` | 2 |
| v1.3 | `6999e8ac8526` / `85e63f7c7b0f` / `934d456e6cd6` / `7d5b62d243a2` | `494d5f5babf9` | 各 1 |

后果：同一张表里的数字出自不同判据构建，跨臂、跨时间点（10k vs 20k）的比较不成立 ——
这正是 `scripts/a_regate_gate_current.py` docstring 与 `docs/b_handoff_to_a_20260928.md` §4 点名的产物漂移，
只不过这次漂在 A 自己的新产物里。**§12 的所有结论在处置前都缺这个前提。**

### 13.2 处置：钉扎 v1.2.1，只重判

- **钉扎快照**：`runs/infra/lerobot_act_env_20260928/gate_v121_pinned/`
  = `git archive 0137b33`（基线提交）取出的 `scripts/b_gate_controlled_success.py` + `docs/b_controlled_success_v1_20260928.md`，
  **刻意复刻 `<root>/scripts` + `<root>/docs` 相对布局**（门禁用 `_ROOT=Path(__file__).resolve().parents[1]`
  定位 `GATE_SPEC_DOC`，布局不同则 spec 哈希变）。自报身份 `v1.2.1 / e4f5ec887788 / 494d5f5babf9`
  = 48 臂权威表（`arms_summary.json`，21:45:54）所用指纹，逐项相符。
- **为什么是 v1.2.1 而不是 v1.3**：可比性锚点是 48 臂权威表与 §6 冻结时的工作树，两者都是 v1.2.1。
  裁定 16 的两个登记册（`configs/b_blown_impl_grandfathered.json`、`configs/b_probe_exonerations.json`）
  B 已于 21:27/21:29 落地，但**那不构成换构建的理由**；且 v1.2.1 不读 `configs/`（grep 确认：
  只读 `_ROOT/GATE_SPEC_DOC` 与命令行传入的 actlog），所以在快照目录内运行与在仓库根运行等价。
- **为什么可以不重跑评测**：blown 阈值是**评测器**按 ckpt 自己的 normalizer stats 现算、写进 actlog 每行的
  `norm_input_blown_frames_frac`；门禁只比 `INPUT_BLOWUP_TOL = 0.05`。所以换构建不会让 R4 翻案。
- **旧 gate 一律 `mv` 进 `ckptseq/gate_build_drift_backup/`**（工作区禁 `rm`），16 份完整保留。

### 13.3 结果：裁定零变化（`scripts/a_gate_build_drift_check.py` 机器判，不手填）

产物 `ckptseq/build_drift_remediate_diff.json` + `ckptseq/build_drift_remediation_record.json`。

- **单一构建断言 PASS**：16/16 份 gate = `v1.2.1 / e4f5ec887788 / 494d5f5babf9`，1 个不同指纹。
- **实体裁定 16/16 完全一致**（`ALL_VERDICTS_IDENTICAL=PASS`）：比的是三套账五计数 + 三个 denominator、
  `measurement_valid`、`gate_pass`、`field_class`、`n_unjudged`、`raw_success`、`input_contract` 的 9 个裁定键、
  `gate_reason` **语义类别**，以及 **`per_episode` 逐局 verdict（20 局 × 16 臂 = 320 局）**。
- 其中 14 份「仅指纹变化」，2 份（`k1 seed0` 的 10k/20k）本来就是 v1.2.1、指纹也没变。
- **表述/溯源差异 10 份，不计入裁定差异**：`gate_reason` 文案（v1.2.1 短句 vs v1.3 附数值长句，类别同为
  `measurement_invalid`；唯一一例 = `k1 seed1@010000`）；v1.3 独有溯源键
  `threshold_provenance`/`blown_metric_impl`/`blown_metric_impl_status`/`artifact_gate_tolerance`/
  `gate_tolerance_matches`/`in_disputed_band`/`probe_exonerated`；`train_time_norm_absmax`
  （v1.2.1 从 actlog 的 `input_constraints` 取，本项目 actlog 把它放在顶层 `input_contract.blowup_threshold`，故报 null）。
  **溯源没丢**：`a_ckptseq_verdict.py::collect` 读的正是 actlog 顶层那份
  （`blowup_threshold`/`threshold_semantics`/`blown_metric_impl`/`stats_file` 均取自 `ic_eval`）。

### 13.4 免罪与争议带（换构建的两个真实风险点，都已排除/标注）

- **探针免罪**：16 份里 `probe_exonerated` 全为 `False`/缺省，**0 份被免罪** ⇒ 换回 v1.2.1 不会产生
  `VALID_probe_exonerated` 的类别差异（本批也没有任何臂因此改变 validity class）。
- **争议带**：v1.3 有 `DISPUTED_BLOWN_BAND = (0.03, 0.08)`，v1.2.1 没有。本批落在带内的有 2 个时间点：
  - `k1 seed1@010000`，blown **0.0532** —— 两个构建都判 `measurement_valid=False`，**R4 成立**；
  - `k1 seed3@010000`，blown **0.0473** —— v1.2.1 下 `measurement_valid=True`（0.0473 ≤ 0.05），
    但距容差仅 **0.0027**。**caveat（新增报告义务）**：任何依赖 `k1 seed3@010000` 的主张必须带
    「blown 0.0473 距 0.05 容差 0.0027，落在 v1.3 争议带 (0.03,0.08) 内」的标注。
    该时间点在 §12 里只作为 `NONPOS`（`dz_pos_frac_tail` 0.048）出现，不参与任何分离主张，故 §12 结论不受影响。

### 13.5 四份 verdict 视图的一致性（族判定全部不变）

| 视图 | tag 数 | gate 指纹 | K1 | K2 | R5 | R6 一致 |
|---|---|---|---|---|---|---|
| 留档 21:46（batch-1 dz） | 11 | **7 个**（漂移） | R2 | R1 | PASS | False |
| 重判后 batch-1 dz | 16 | 1 个（v1.2.1） | R2 | R1 | PASS | False |
| **首批干净视图**（8 tag 影子目录） | 8 | 1 个（v1.2.1） | R2 | R1 | PASS（4/4，diffs 全 0） | False |
| **权威**：`divergence_verdict_all.json` | 16 | 1 个（v1.2.1） | R2 | R1 | PASS | False |

- **权威视图 `ckptseq/divergence_verdict_all.json` 只有 29 处字段变化 = 14 `gate_build` + 14 `gate_version` + 1 `generated_at`，实体零变化。**
- 首批 8 个 tag 的记录：非指纹变化 **0**（`k1 seed0` 的两个 tag 连指纹都没变）。
- 重判后 batch-1 视图的 Q1/Q2/样本外分离度**描述统计**被 5 个扩围 tag 污染
  （`dz_diag_ckptseq.json` 早于它们落盘 ⇒ `dz=None` ⇒ `level=UNKNOWN`）；族判定与 R5 不受影响。
  干净的首批视图 = `ckptseq_batch1_pinned/`（**全 symlink 影子目录，判定器逻辑零改动**），
  产物 `ckptseq_batch1_pinned/ckptseq/divergence_verdict_batch1_pinned.json`。
- **§12.5 的 6 条允许结论逐条维持原文**，不新增、不改写、不放宽。

### 13.6 48 臂权威表回归（未被本次处置扰动）

`python3 scripts/summarize_lerobot_act_arms.py --dir runs/infra/lerobot_act_env_20260928 --json-out /tmp/arms_summary_regression.json`
→ 与留档 `arms_summary.json` **逐字节相同（除 `generated_at`）**，48 臂、`v1.2.1/e4f5ec887788/494d5f5babf9`。
原因：生产者只扫父目录的 `official_act_truth20_*.json` 与 `gate_*.json`，**不扫 `ckptseq/`**。

### 13.7 遗留（不属于本预登记，需新预登记才能做）

- `save_freq` 加密 + 训练侧探针，用来回答「分岔发生在第几步」——§3 的分辨率上限（每臂 2 个互异 ckpt）
  决定了本实验**永远**只能给「不晚于 10k」/「10k–20k 之间」，更细的定位必须重训。
- `dz_mean_tail` 上界在样本外低估能力（§12.4）：要改判据只能新写预登记、只对下一批新臂生效，**不得回填本批**。

### 13.8 v1.4 落地后的交叉核验（22:55 追加；**§2–§6 与 §13.1–§13.7 一字未改**）

B 于 22:44 落地 **v1.4**（`b9379fdb1089` / spec `132fceb89f68`，实现裁定 14）。A-2 的锚点**不变**：

- **仍钉 v1.2.1**：§6 冻结的是「单一构建」这个要求与其时的权威指纹；门禁前进**不构成**回填改锚点的理由
  （改锚点等于在看到结果后换判据）。v1.4 结果只作**交叉核验**，写独立子目录 `ckptseq/v14_crosscheck/`，
  **不与 v1.2.1 混表**（裁定 16 第 2 条）。
- **交叉核验结果**：v1.4 重判同样 16 份 actlog（actlog 仍一字节未动）→ 与 v1.2.1 逐臂逐局比对
  `ALL_VERDICTS_IDENTICAL=PASS`、**`STOP_SIGNAL=0`**、**`LABEL_MIGRATION_ONLY=0`**
  （16 份全 `field_class=strict` ⇒ 裁定 14 的弃权路径不触发）。
  ⇒ **§12.5 / §22.8 的 6 条结论在 v1.2.1 / v1.3 / v1.4 三个构建上同结论**：分岔定位不是判据构建的产物。
- **工具卫生（采纳 B `docs/b_handoff_to_a_20260928.md` §8.3bis 的选项 2）**：
  `scripts/a_gate_build_drift_check.py` 的期望指纹**不再硬编码**，默认从
  `runs/infra/b_official_arms/reclassification.json` 顶层读（当前权威构建的单一真值来源），
  `--pin-a2-prereg` 才是钉 v1.2.1 历史锚点的显式开关 ⇒ 工具本身不会成为新的漂移源。
  并按 B 的口径把差异分成 `label_migration`（允许）与 `stop_signal`
  （`controlled_success` / `provisional_pass` 变化必须停下查）。
- **顺带核出的 blocker（不属本预登记，已移交）**：B 的 v1.4 权威表**计数层**与 A 的 48 臂表逐格相同
  （377 / 135 / 235 / 7 / 0 / 0），但**三分类停在 24/22/2（免罪前）**，因为
  `configs/b_probe_exonerations.json` 缺 裁定 16 第 4 条明文要求的 `k2 seed0` 条目。
  ⇒ A 的 48 臂表**暂不迁 v1.4**（迁了会与增补五 §3 的 25/22/1 冲突）。
  详见 `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md`。

---

## 14. 裁定 30（DR-D29）落地：双峰的**可引用写法**改为「强间隙分离」（2026-09-29 追加；§1–§13 原文一字未改）

依据：`work/decisions/decisions_20260929.md` 裁定 30 / DR-D29，全文见
`rl_harness_supervision/supervisor_memo_20260929.md` 增补七 §20。
**§1 第 3 条、§10.4 第 3 条、§11.4 末段的原文按 append-only 一律未改**，只在原句下方挂更正指针。

### 14.1 事实：A 独立复算（不采信 D 的转述），与裁定 30 §20.1 逐格吻合

臂集 = `runs/infra/lerobot_act_env_20260928/closed_loop_dz_diag_A.json` 的 **21 个 actlog 臂**，
join 到 v1.5 权威表（A 侧 `arms_summary.json` 与 B 侧 `reclassification.json` **逐格相同**，
两表 `gate_build` 同为 `f19f61341cbe`、与 live 门禁 `sha256[:12]` 亦同）：

| 量 | 21 actlog 臂 | 48 臂全集 | `measurement_valid` 47 臂 |
|---|---:|---:|---:|
| 低簇 0–3 | **15** | 40 | 39 |
| 空带 4–8 | **0** | 1 | 1 |
| 空带 10–13 | **0** | 0 | 0 |
| 高簇 14–20 | **5** | 5 | 5 |
| **4–9（禁用窗口）** | **1** | **3** | **3** |
| 定性 | **gap_separated** | mixed（4–8 被占 1 臂） | mixed |

21 臂排序后 = `[0×7, 1×4, 2×3, 3, **9**, 14, 16, 17, 19, 20]`；落在 4–9 的那 **1** 臂
= `trimdone0_minmax_k2_lr1e-5_s20k_seed0`（受控 **9/20**、`final_rise` 0.040）
= **裁定 10 的免罪臂本尊**（`validity_class=VALID_probe_exonerated`、`probe_kind=clip_at_train_absmax`、
`band_checked=false`、`cosign_build_matches=true`）。
48 臂全集落在 4–9 的 **3** 臂 = `k2 seed0`(9)、`train120_trimdone0_minmax_k2_lr1e-5_s20k_seed0`(9)、
`trimdone0_minmax_lr1e-5_s20k_seed0_replan1`(4)；**48 臂与 valid 47 臂两套臂集在该区间结果相同**，
因为唯一 INVALID 臂（`…k2_lr1e-5_s20k_seed0_replan1`，blown 0.1692）受控成功是 **0**、不落 4–9。

**成因（与裁定 30 §20.2 一致，A 复核认可）**：v1.2.1 历史表
`runs/infra/b_official_arms/reclassification.build_e4f5ec887788.json` 实测该臂当时
`citable = NOT_CITABLE_measurement_invalid`、`ic_status = violated`、`mean_blown_frames_frac = 0.212`
⇒ **写 §1 的那一刻它是无效臂**，按「有效臂」统计 4–9 = 0 **成立**（§1 第 1 条也已明写「9(免罪)」，
是 §1 自身前后矛盾，裁定 30 §20.2 末段指出，A 认）。免罪落地 ⇒ 它重回分布 ⇒ 计数 0→1，**此前无人传播**。

### 14.2 可引用写法（四限定缺一不可，裁定 30.3）

> **在 21 个 actlog 臂、20k 快照（`checkpoints/last` = 020000）、构建 `v1.5 / f19f61341cbe` 下，
> 受控成功呈强间隙分离（gap-separated）：低簇 0–3 共 15 臂、高簇 14–20 共 5 臂、
> 中间带只有孤立 1 臂 = 9/20（`trimdone0_minmax_k2_lr1e-5_s20k_seed0`，`VALID_probe_exonerated`，
> 裁定 10 免罪臂）；空带是 4–8 与 10–13。**

四限定 = ① 臂集（21 actlog / 48 官方 / valid 47）② 快照（20k）③ 构建（`v1.5 / f19f61341cbe`，
**不带 spec 值**，裁定 29.1）④ 显式点出中间带孤立臂。**禁用**：「受控成功落在 4–9 的臂数 = 0」、
「中间是空的」、「严格双峰、中间全空」。
**双峰结论本身不倒**（§5 判定规则、§2 阈值、§4 臂清单、§12/§13 全部结论一字未改）——
被推翻的只是「中间全空」这一种**写法**。

### 14.3 一般规则（裁定 30.4，本条真正要立的东西）

- **计数层（逐局 verdict 计数）= 构建不变**：48 臂合计 raw **377** / 受控 **135** / insuff **235** /
  flick **7** / over **0** / prov **0**，v1.4→v1.5 实测一格未动（裁定 28 ③）。
  **限定在同一臂集（48 臂）内**：v1.2.1 历史表是 `n_artifacts = **44**`、计数 `132/208/23/0/1/364`
  的**不同臂集**（多出 4 臂是 blindfix / reblown 重测世代），**不可直接相减**（裁定 30.5）；
  引历史口径必须同时报 `n_artifacts`。
- **分布层（直方图 / 区间计数 / 极差 / 族均值的 n）= 构建相关**：它按 `measurement_valid` 的臂集统计，
  而臂集会被免罪 / 降级改变 —— 实测无效臂 **v1.2.1 = 7 → v1.5 = 1**。
  ⇒ **任何分布类陈述一律带构建指纹**。这是裁定 29.1「引用锚只在 build 轴」的**第二个独立理由**。
- 本预登记的 §1 第 3 条 / §10.4 / §11.4 引用的都是**分布层**量 ⇒ 全部适用本规则。
  相比之下 §13.8「分岔定位在 v1.2.1 / v1.3 / v1.4 三个构建上同结论」是**判别量层**的交叉核验，不受影响。

### 14.4 代码承载与非恒真（回答裁定 29 立的纪律：「哪一行代码执行它」）

| 裁定 30 条目 | 承载 | 判据 |
|---|---|---|
| 30.1 改述为强间隙分离 | `scripts/summarize_lerobot_act_arms.py::distribution_arm_set` 的 `characterization` + `intervals`（**从行里算，不写死**） | `a_distribution_layer_check.py` **D3**（blocking） |
| 30.2 禁用写法 + 三处指针 | `FORBIDDEN_DISTRIBUTION_PHRASINGS` + 本文档 `:17`/`:191`/`:308` 的更正指针 | **D6**（blocking，扫 A 自己的文档，**A 不自免**） |
| 30.3 四限定 | `meta.distribution_layer.citation_requires_four_qualifiers` + 每个臂集回显 `arm_set`/`snapshot`/`middle_band_arms` | **D7**（blocking） |
| 30.4 计数层不变 / 分布层相关 | `meta.distribution_layer.counting_layer` / `.distribution_layer`（含 `n_invalid_arms_this_build`） | **D1**、**D8**（blocking） |
| 30.5 历史口径须报 `n_artifacts` | `meta.distribution_layer.historical_citation_rule` | **D9**（warn） |
| — 跨表同源性 | A 表 ↔ B 表 ↔ live 门禁三处 `gate_build` 同一 + 21 臂计数逐格相同 | **D4**（blocking） |
| — 单构建纪律 | `meta.build_discipline.single_build_only` | **D10**（blocking） |

**非恒真（裁定 30.6 的双向自检）**：可红条件 = 「21 臂 join 权威表后 4–9 计数 == 0」。
现场实测 == **1** ⇒ D2 绿。`--selftest` 12 档变异覆盖两个方向：
**S2**（把免罪臂受控改成 0，孤立臂消失）⇒ D2/D3 必须红；**S3**（把产物里的 4–9 计数写成 0，
即把禁用写法当事实写进表）⇒ D2/D3/D5 必须红；**S9**（同一句禁用写法但**带**更正指针）⇒ D6 必须**放行**，
证明 D6 不是恒假。另有 S4（删掉分布层块 = 裁定无承载）、S5（spec 轴被当生效条件 = 裁定 29.1 地雷复活）、
S6（A/B 两表分叉）、S7（表 build 与 live 不一致）、S8（无指针的禁用写法）、S10（历史表不可读）、
S11（缺臂集）、S12（跨 build 混引）。

**若该臂将来被重新评测**（免罪册 `scope=artifact` ⇒ 豁免随产物 sha256 失效）且新产物受控落到 ≤3 或 ≥14，
D2/D3 会自动变红并要求按新数据改写定性 —— 这是设计意图，不是回归。

复现命令见 `docs/lerobot_act_env_setup_20260928.md` 复现命令区 **36–37**。
