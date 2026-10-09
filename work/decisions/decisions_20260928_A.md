# A 线登记（2026-09-28）：口径追加 / 留档作废与补测 / L1 路径只登记不动手

登记方：智能体 A（官方 LeRobot ACT 闭环训练+评测线）。
依据：`work/decisions/decisions_20260928.md` DR-001（`work/decisions/` 可写，**最小写入**：
只放路线变更 / 口径裁定 / 作废与 ack 登记；实验结果、产物、日志不写入本目录）。
本文件是 A 线自己的登记，不修改 C/D 已写的 DR-001、DR-002。
所有被引用的产物路径都在 `runs/`（不纳版控），本文件只写路径与判定，不抄结果表。

---

## ADR-A-001 blown 指标单一来源化 + 实现指纹（口径追加，已实施，恒等回归已验收）

- 时间：2026-09-28 19:50 实施，20:00 登记
- 依据：监管备忘 2026-09-28 增补三 §12（分派给 A：blown 口径单一来源化 + 重测 + 记差异原因）
- 变更内容（`scripts/eval_lerobot_act_runtime.py`）：
  1. blown / oor 帧判定收敛到**单一函数** `blown_frame_stats()`，plain 路径与 clip 探针路径共用；
  2. 该函数与 `normalized_input_vector()` 的源码指纹 `BLOWN_METRIC_IMPL` 写入产物
     `input_contract.blown_metric_impl`（附 `blown_metric_source` 指回源码位置）；
  3. clip 探针模式**新增**逐局 `norm_input_clamped_frames` / `norm_input_first_clamped_frame`，
     块级 `input_contract.clip_probe.trajectory_note` / `n_episodes_input_clamped` /
     `total_clamped_frames` / `first_clamped_frames`。
- 性质：**只追加键**。不改任何既有键的语义、单位、数值；不改评测协议（题集 seeds 5000-5019、
  horizon 300、无 guard、pinned object seed 20260923）；不改门禁判据。因此**不构成 baseline 重置**。
- 验收（A 线纪律「改评测器必须回归」）：全键递归比对 PASS ——
  同一 checkpoint（`trimdone0_minmax_k2_lr1e-5_s20k_seed3`）重跑 20 局与留档产物相比，
  仅 `rows[].elapsed_sec` 20 处不同 + 2 个新增键；逐局 `max_rise / final_rise / phase_trace /
  phase_at_end / held_at_end / norm_input_*` 全等，顶层汇总键全等。
  证据：`runs/infra/lerobot_act_env_20260928/evaluator_patch_regression_k2_seed3.json`
  （比对器 `scripts/a_eval_idempotence_check.py`，可复跑）。
- 影响面与引用规则：
  - 新产物带指纹；**留档产物不带**（早于本变更），引用留档的 blown 数字时须写明
    「留档早于 `blown_metric_impl` 字段」，不得把新指纹回填给留档。
  - 引用任何 blown 数字仍须写明产出路径（plain / clip_probe）与 `gate_build`（增补三 §12）。
- 已裁定的口径问题（本条同时结案）：留档 plain 的 `norm_input_blown_frames_frac`（k2 seed0 = 0.2120）
  与 clip 探针的 `norm_input_preclip_blown_frames_frac`（= 0.1180）**不是同一条闭环轨迹上的统计量**，
  两者各自正确但不可互换。H1（分母不同）/ H2（参与维或阈值不同源）已被逐局数据**否证**
  （截断从未生效的 52 局上 absmax 与 blown_frac 逐位相等），H3（轨迹分岔）成立且因果干净
  （没有任何一局在截断未生效时分岔）。证据：`runs/infra/lerobot_act_env_20260928/blown_metric_reconcile.json`
  （`scripts/a_blown_metric_reconcile.py`）。

## ADR-A-002 5 份盲臂留档产物：门禁可判资格作废，改为补测替代（原件保留）

- 时间：2026-09-28 20:05 登记
- 依据：监管备忘 增补三 §3 修正 A（「40/40 带字段」不成立，实测 44 份、5 份缺 `input_contract`）
  + §9.A②（补测或登记 superseded，不得静默留空）
- 涉及臂（留档路径均在 `runs/infra/lerobot_act_env_20260928/official_act_truth20_<arm>.json`）：
  1. `train24_lr1e-4_s20k`
  2. `train24_lr1e-5_actionminmax_s20k`
  3. `train24_lr1e-5_actionminmax_s20k_seed1`
  4. `train24_lr1e-5_actionminmax_s20k_seed2`
  5. `train24_lr1e-5_s20k`
- 实测缺陷（不止缺 `input_contract`）：这 5 份出自**旧评测器**，还缺 10 个逐局门禁字段
  （`final_rise / held_at_end / phase_at_end / terminal_kind / norm_input_frames_measured /
  norm_input_blown_frames_frac / norm_input_out_of_range_frames_frac / norm_input_absmax /
  norm_input_top_dim / norm_input_blown_dims`）与 7 个顶层键
  （`replan_every / replan_every_note / log_actions / input_contract / mean_final_rise /
  held_at_end_count / terminal_kind_counts`）。门禁只能判 `field_class=partial` + `measurement_invalid`。
- 作废范围（**精确界定，不扩大**）：
  - 作废：这 5 份文件作为「门禁可判产物」的资格 —— 不得进入任何跨臂比较、失效模式归因、
    晋级判据的分子分母。
  - **不作废**：其中已有的 `success_raw / success_rise / mean_max_rise` 数字，前提是补测在
    共有字段上逐位相同（见下）。
- 处置：选「补测」而非「作废重训」。5 个 checkpoint（`checkpoints/020000/pretrained_model`）都在，
  协议一致（20 局 / seeds 5000-5019 / horizon 300 / K=R=4），用当前评测器重跑即可变成 strict 可判臂。
- 纪律：留档原件**一字节不动、不覆盖、不删除**；补测产物写 `runs/infra/lerobot_act_env_20260928/blindfix/`
  子目录（避免被主目录的汇总/重判 glob 重复计数），门禁重判写 `blindfix/regate_current/`。
- 验收：`scripts/a_blindfix_compare.py` 把补测产物按留档键集裁剪后做全键递归比对，
  允许差异只有 `rows[].elapsed_sec`；交集全等才允许把留档标为 superseded。
  证据：`runs/infra/lerobot_act_env_20260928/blindfix/blindfix_vs_archived.json`。
- 状态：补测在跑（链在 K=1 seed2-5 评测之后，避免抢 GPU）。

## ADR-A-003 A 线两条 L1 修复路径：**只登记，不动手**

- 时间：2026-09-28 20:05 登记
- 依据：DR-001「生效条件」（三项各自动手前须在本目录追加独立记录）+ 增补三 §9.A⑥
  （L1 修复臂暂停至 (a)/(b) 登记）+ 增补二 §1（截断永久只作因果探针，不得作修复或交付能力）
- 路径 (a)：obs 契约变更 —— 去掉或重定义 `observation.environment_state[3]/[4]`
  （近常量维，MEAN_STD 下 std 低至 1e-2~1e-4 量级，是 L1 炸穿的源头）。
  - 性质：**baseline 重置**。obs 维度定义变了，题集与 teacher 导出都要重做。
  - 影响面：`base-only raw 20/20、mean_max_rise 0.0764` 的基线必须重测；
    现有 44 臂（含受控成功合计 132）作为「同一 obs 契约下」的比较基准**整体失效**，
    只能作为旧契约下的历史记录引用。
  - 作废清单（动手时须逐条列出并登记）：`docs/lerobot_act_env_setup_20260928.md` §16/§17/§18
    的所有跨臂归因结论、`arms_summary.json`、`gate_threshold_sensitivity_A.json`。
  - 验收方式（动手时）：scripted teacher 20/20 重跑 + base-only 重测 + 至少 3 seed 重训重评 + 门禁重判。
- 路径 (b)：自定义 processor 做训练+推理一致的输入截断。
  - 性质：**越出官方入口纪律**。一旦引入自定义 processor，产物就不再是「官方 LeRobot ACT」，
    `controller=official_lerobot_act` 这个 claim 标签必须改，且与官方基线不再可比。
  - 影响面：A 线「官方 ACT 跑通」这条 claim 的口径要重写；已交付的 44 臂仍是官方口径，
    新臂属另一条 claim，两者不得混在同一张表里。
  - 验收方式（动手时）：训练期与推理期截断实现同源 + 恒等回归（关闭截断时必须与官方产物逐位相同）。
- A 线立场：两条都**不动手**。当前继续按增补二 §1，截断只作因果探针；
  L1 的处置等 D/用户裁定后再按 DR-001 生效条件追加独立记录。

## ADR-A-004 ack：增补三对 A 的六条（§9.A①–⑥）

| 条 | 要求 | A 的 ack | 交付路径 |
| --- | --- | --- | --- |
| ① | 44 臂全量重判到唯一可采信 build v1.2.1 | 已完成 | `runs/infra/lerobot_act_env_20260928/regate_current/`、`regate_diff_current.json`（`scripts/a_regate_gate_current.py`，只读、旧裁定一字节不改） |
| ② | 5 份缺契约臂补测或登记 superseded | 已登记（ADR-A-002），补测在跑 | `runs/infra/lerobot_act_env_20260928/blindfix/` |
| ③ | 阈值敏感性重跑（单一构建） | 已完成 | `runs/infra/lerobot_act_env_20260928/gate_threshold_sensitivity_A.json`（`scripts/a_gate_threshold_sensitivity.py`） |
| ④ | K=1 seed2-5 训练+评测 | 训练已完成（4 臂 exit 0），评测在跑 | `runs/infra/lerobot_act_lift_v30/trimdone0_minmax_k1_lr1e-5_s20k_seed{2,3,4,5}/` |
| ⑤ | k1 seed1 的 actlog | 已存在，直接引用（§18 表内 `dz_tail=-0.0009`） | `runs/infra/lerobot_act_env_20260928/actlog/actlog_trimdone0_minmax_k1_lr1e-5_s20k_seed1.json` |
| ⑥ | L1 修复臂暂停至 (a)/(b) 登记 | 已登记（ADR-A-003），A 不动手 | 本文件 |

## ADR-A-005 提请裁定（A 不代做，等 B/D）

1. **门禁 phase 词表自检**：产物只有 `phase_at_end ∈ CONTROLLER_LOG_VOCAB` 而缺 `phase_trace` 时，
   门禁当前**静默判 flick**（已在 residual 臂上造成一次假阴性：20 局全被判 flick，补字段后 20/20 受控）。
   建议改为「报字段不匹配 / INVALID」而不是给出失效模式标签。属 B 的门禁代码，A 不修改。
2. **无归一化策略的输入契约口径**（residual/SAC 臂）：需要在
   (i) 训练时落盘 obs absmax 以定义契约、(ii) 显式 `not_applicable` 声明路径 之间裁定一个。
   现状是该臂 raw 20/20、受控 20/20（v1.2.1）但因缺 `norm_input_blown_frames_frac` 仍判 INVALID。
3. **增补三 §8 上调条件第 4 条（burst 贡献可复现 >50%）在现有数据上不可达**：
   实测最高 burst 占比为 k2 seed3 ≈ 23%，17 臂均值 ≈ 8%。A 的意见是该条把「有没有能力」与
   「是否复现 teacher 的动作形态」混同了 —— 一个用非 burst 方式稳定抬起的策略会被这条永久挡在门外。
   提请 D 复核该条是否应改为「burst 占比须逐臂报告」而非「须 >50%」。

## ADR-A-006 口径裁定：A-2 钉扎 v1.2.1、48 臂表**暂不迁** v1.4（2026-09-28 22:55，A 自裁，报 D 备案）

按 DR-001 最小写入：本条只登记**口径裁定**，证据与数字在 `docs/` 与 `runs/infra/`，不写入本目录。

### 裁定 1：A-2（双峰分岔定位）钉扎在 **v1.2.1 / `e4f5ec887788` / spec `494d5f5babf9`**，不随门禁前进改锚点

- 触发：`ckptseq/` 的 16 份 gate 实测横跨 **7 个 `gate_build`**（`GATE_BUILD` = 门禁脚本内容哈希，
  B 在 A-2 跑动期间实时升级），而预登记 §6 要求单一构建 ⇒ 跨臂 / 跨时间点比较缺前提。
- 裁定：**改锚点等于在看到结果后换判据**，故不改；改为把 16 份统一到预登记冻结时的 v1.2.1。
  手段 = `git archive 0137b33` 建钉扎快照（复刻 `scripts/`+`docs/` 相对布局，否则 spec 哈希会变）+ **只重判不重跑评测**。
- 作废登记：处置前产出的 16 份混合构建 gate **作废为引用依据**（原件 `mv` 进 `ckptseq/gate_build_drift_backup/`，
  未删）；处置前生成的两份 verdict 备份在 `ckptseq/verdict_predrift_backup/`。
- 边界：门禁后续版本（v1.3 / v1.4）的结果只作**交叉核验**、写独立子目录，**不与 v1.2.1 混表**（裁定 16 第 2 条）。

### 裁定 2：48 臂权威表**暂不迁** v1.4，并给 A 自设的迁移闸

- 事实前提：v1.4 已落地（裁定 14）、两个登记册已存在 ⇒ 裁定 16 第 1 条的前置已解除，**技术上可迁**。
- 但 `configs/b_probe_exonerations.json` **缺 裁定 16 第 4 条明文要求的 `k2 seed0` 条目**
  （该册 `_doc` 的「带外 >0.08 一律不受理」把 裁定 10 的 clip-at-train-absmax 通道一起挡掉了），
  导致 v1.4 权威表的可引用三分类停在**免罪前**，与增补五 §3 / §7 要求的**免罪后**口径冲突。
- 裁定：**迁移会把 A 的表从免罪后口径拉回免罪前口径 ⇒ 不迁**。这不是保守，是避免与监管权威表冲突。
- **迁移闸（写死，A 不自免）**：B 补齐条目 + D 会签后，A 重跑
  `scripts/a_regate_gate_current.py` + `scripts/summarize_lerobot_act_arms.py` 迁移；
  **迁移前必须核**新表 `NOT_CITABLE_measurement_invalid == 1` 且三分类 `== 25 / 22 / 1`，否则不迁并报回 D。
- 过渡期引用纪律：**两构建并存时计数可互换、分类不可互换**。引 A 的表带 `v1.2.1 / e4f5ec887788` + 免罪后三分类；
  引 B 的 `reclassification.json` 带 `v1.4 / b9379fdb1089` + 免罪前三分类；
  **不得**把 B 的免罪前数字当免罪后现值引用，也不得把两表的分类数字混在同一行。

### 裁定 3：工具卫生 —— 采纳 B §8.3bis 选项 2，检查器**不再硬编码**期望指纹

- B 指出 `scripts/a_gate_build_drift_check.py` 硬编码 v1.2.1 指纹已过期。**B 的批评成立**：
  硬编码正是这份工具要消灭的漂移，等于把漂移搬进工具本身。
- 裁定：期望指纹默认从 `--authoritative-table`（当前权威构建的单一真值来源）读；
  `--pin-a2-prereg` 才是钉历史锚点的显式开关；差异分类引入 `stop_signal`
  （`controlled_success` / `provisional_pass` 变化必须停下查）与 `label_migration`（裁定 14 的预期效果，允许）。

### 移交（A 不代做）

- → **B**：改豁免册「带外不受理」为按 `probe_kind` 分通道 + 新增 `k2 seed0` 条目（内容 A 已备齐，
  含五条准入逐条与 C=5.0 的判别力反证）。见 `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md`。
- → **D**：会签该条目（裁定 16.4 要求 D 会签；事实基础 D 已在增补四 §3 核可）；
  并裁定 ADR-A-007 第 2 项（INVALID 臂的行级失效模式计数该给数还是该写 `null`）。

## ADR-A-007 提请裁定（A 不代做）

1. **免罪册缺条目**（同上，主责 B、会签 D）：现状使增补五 §3 的「免罪后 47 / 1、25 / 22 / 1」
   在 B 的 v1.4 权威表里**达不到**。A 已给最小修复面与全部证据路径。
2. **INVALID 臂的行级失效模式计数口径**（A/B 两表现状不同，需统一）：
   `measurement_valid=false` 的臂，行级 `flick` / `over_lift` / `insufficient_lift` 该**给数**（B 现状）
   还是该**写 `null`**（A 现状，理由：裁定 12 规定 blown 超阈只作测量有效性门禁，
   在行级给失效模式标签容易被当成能力主张）。**两边合计层完全一致**，纯呈现口径问题；
   若 D 判给数，A 改 `scripts/summarize_lerobot_act_arms.py` 一处即可，**无需重跑任何评测**。
3. **A 行级 schema 缺 `provisional_pass` 列**（合计层有、值恒 0）：是否补齐由 D 定；
   A 倾向补齐（成本一行），但**不在本轮单方面改**，以免与迁移撞车。
