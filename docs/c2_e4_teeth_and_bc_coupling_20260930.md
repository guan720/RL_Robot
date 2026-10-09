# C2 → D · E4 两把牙的裁定材料 + ③ 号问题（准入闸 ∧ 质量闸）的方案设计

| 项 | 值 |
|---|---|
| 线 | **C2**（归一化契约线，辅线；主 = A2 的 Step-1） |
| 任务来源 | `rl_harness_supervision/d_handoff_to_c2_20260930.md` 的「待命令·二（裁定 103.6-④）」+「补单·四（裁定 104）」 |
| 交接件身份（读取时刻） | `d_handoff_to_c2_20260930.md` = **281 ln(`wc -l`) `52ab5c8317c7`**（mtime `2026-09-30 19:08:16`） |
| 本件 as_of | **2026-09-30T19:3x+08:00**（本件落盘时刻；件内所有读数的 `as_of` 见证据件） |
| 证据件（**所有数字的唯一出处**） | `runs/vla/c2_e4_ruling_material_20260930/E4_EVIDENCE.json` = **2537 ln(`wc -l`) `c9eddacec6c2`**（100022 B，as_of `2026-09-30T19:35:28+08:00`） |
| 取证器 | `scripts/c2_e4_ruling_material.py` = **935 ln(`wc -l`) `e7fc265707e8`**（只读；`ast` 静态解析 + 字节哈希，**不 import** 任何判定/训练模块） |
| 边界 | 只读他线、只写 `runs/vla/c2_e4_ruling_material_20260930/`；**不重跑全量闸、不上卡、不改任何牙的极性、不落地新牙**（裁定 101.1 治理冻结 + 104-②） |
| 能力声明禁令 | 裁定 46 / 101.3：`capability_claim=false`、`policy_executed=false`、`gpu_used=false`、`success_metrics_collected=false`；本件任何计数**都不是** policy 能力指标，`success_rate_column=not_an_exit_criterion` |
| 口径纪律 | 裁定 98.5：约束性对账只用 `sha256[:12]`；行数一律点名口径（`n_lines_wc` / `n_lines_splitlines`）；代码行号只作 `line_no_as_of`（**不是**常驻身份）；缺测写 `not_measured`，不写 `false`、不猜 |

**本件的数字一律是「取自 `E4_EVIDENCE.json` 的某字段」**，字段路径在每条后面用 `⟨…⟩` 标出。凡我上一轮口头/散文里说过、与本件实测不符的数字，**以本件为准并在 §D.2 逐条撤回**。

---

## Part A · E4 两把牙（`Tb_scale_floor_effective` / `Tr3_near_constant_floor_material`）的裁定材料

### A.0 一句话结论

**这两把牙自裁定 93.1-1 起就不是 blocking 牙**（`blocking=False`，`ok=False` 时出 `WARN`，结构上不可能出 `RED`）；D 的 §104.6 / 待命令·二 / 补单·四 里「**E4 那两把 blocking 牙**」这个措辞是**过期说法**，需要追平。硬红已由裁定 93.2 的两颗牙承担（`Tz_denom_strictly_positive` 全臂 + `Tres_per_dim_resolution_floor` 逐维·全量口径），且在权威档上实测 **8/8 PASS**。⇒ Step-1 期间**不动极性**（甲 = 现状）是正确的；本件给出的是「若要在 Step-1 之后恢复 blocking，必须先拿到什么测量」的定标路径与代价。

### A.1 措辞追平：两牙的极性（机器证明，不靠散文）

| 事实 | 值 | 出处 |
|---|---|---|
| `tooth()` 的 `blocking` 默认值 | `True` | `⟨part_A_e4_teeth.static_parse.tooth_helper.defaults.blocking⟩`（`harness/norm_contract.py:1024`） |
| status 机制（唯一出处） | `status = "N_A" if not applies_when else ("PASS" if ok else ("RED" if blocking else "WARN"))` | `⟨…tooth_helper.status_mechanism⟩`（`harness/norm_contract.py:1028`） |
| `Tb_scale_floor_effective` | 调用处 `:1276`，**显式** `blocking=False`，`applies_when` 未给（取默认 `True`）⇒ `ok=False` 出 **WARN** | `⟨…static_parse.teeth.Tb_scale_floor_effective⟩` |
| `Tr3_near_constant_floor_material` | 调用处 `:1231`，**显式** `blocking=False`，`applies_when=bool(mainline)` ⇒ 主线臂 `ok=False` 出 **WARN**、非主线臂出 **N_A** | `⟨…static_parse.teeth.Tr3_near_constant_floor_material⟩` |
| 上一轮权威闸跑的**全 49 行**实测 | 两牙的 `blocking` 直方图都是 `{"False": 49}` ⇒ **本轮任何一行、任何一臂都不可能因它们出 RED** | `⟨…authoritative_gate_run.matrix_teeth_scan.per_tooth.*.blocking_histogram⟩` |
| 替代硬红 | `Tz_denom_strictly_positive`（`:1197`，`blocking=True`，`applies_when=True`）· `Tres_per_dim_resolution_floor`（`:1353`，`blocking=True`，`applies_when=True`） | `⟨…static_parse.teeth.Tz_*/Tres_*⟩` |

> **为什么这条要单独点出来**：D 的执行单里连续三处（§101.1、待命令·二、补单·四-①）把它们称作「blocking 牙」。若按字面理解，会得出「Step-1 期间有两颗硬红牙盯着 E4 的两个失效形态」这个**错的**风险图景；实际盯着的是 `Tz` + `Tres`。这不是判词分歧，是**措辞与码层不一致**，按 `redline_provenance_discipline`（读了声明没读实现）的同族纪律，必须由 C2 追平。

### A.2 阈值溯源状态（`redline_provenance_discipline` 的判据表）

约束性判据 = `ContractThresholds.provenance` 里的**状态串**（源码同行注释是散文，不作判据）。全部由 AST 从 `harness/norm_contract.py`（`91795179de7e`）取出：`⟨part_A_e4_teeth.thresholds.fields⟩`

| 阈值 | 值 | `line_no_as_of` | provenance 状态串 | 定标类 | 按红线**可否** blocking |
|---|---|---|---|---|---|
| `min_bins_occupied`（`Tb` 用） | `8` | 926 | `registered_measurement_not_a_judgment` | 未定标/仅测量 | **否** |
| `floor_materiality_fraction`（`Tr3` 用） | `FLOOR_MATERIALITY_FRACTION` | 939 | `registered_measurement_not_a_judgment` | 未定标/仅测量 | **否** |
| `clip_ratio_cap` | `0.01` | 925 | `proposed_pending_s1` | 未定标/仅测量 | **否** |
| `near_constant_rel_tol` | `NEAR_CONSTANT_REL_TOL` | 935 | `derived_from_min_F1_candidate（原 c2_proposal 1e-3 已实测为恒真，作废）` | 未定标/仅测量 | **否** |
| `start_pose_oob_dims_cap` | `0` | 927 | `ruling_51_1_c_hard` | 已定标 | 是 |
| `min_bins_occupied_non_near_constant`（`Tres` 用） | `8` | 951 | `d_calibrated_from_formal40_all_caliber` | 已定标 | 是 |
| `min_bins_occupied_near_constant`（`Tres` 用） | `2` | 952 | `d_calibrated_from_formal40_all_caliber` | 已定标 | 是 |
| `warn_bins_occupied_near_constant` | `8` | 953 | `d_calibrated_from_formal40_all_caliber` | 已定标 | 是 |

⇒ **裁定 93.1-1 把 `Tb`/`Tr3` 转 WARN 的理由在盘上是自洽的**：它们吃的两个阈值状态串都写着「已登记的测量、不是判据」。同一张表也说明：**`Tres` 的三个阈值是本轮唯一被 D 定标过的分辨率判据**，所以硬红落在它身上不是放宽，是把阻塞性搬到有定标的尺上。

### A.3 `Tres` 的定标件（身份 + 余量，全部机器取值）

`⟨part_A_e4_teeth.calibration_source⟩`

- 件：`runs/vla/d_ruling_round_20260930_1010/probe_resolution_calibration_inputs.json` = **236 ln(`wc -l`) `55190798963c`**（6069 B，`generated_at 2026-09-30T10:37:08+08:00`，`read_only=true`，生成器 `d_probe_resolution_calibration.py` `b5306071c5c6`）
- `near_constant_dims = [3, 10]`，`near_constant_rel_tol = 0.02`
- **三个口径的逐维 bin 占用**（这是 E4 争议的核心读数，一次给全，不再只引一个口径）：

| 口径 | `n_frames` | `bins_occupied_per_dim` | `dims_below_min_bins` |
|---|---|---|---|
| `summary`（held-out，= `Tb` 的测量口径） | 547 | `[3,97,106,2,38,3,35,4,111,108,5,46,5,36]` | `[0,3,5,7,10,12]` |
| `summary_build` | 10488 | `[23,117,114,3,47,24,87,22,117,117,5,48,22,72]` | `[3,10]` |
| `summary_all`（**全量 = `Tres` 的判据口径**） | 11035 | `[23,117,114,3,47,24,87,22,117,117,5,48,22,72]` | `[3,10]` |

- 定标件里同时记着 `arm_mainline_matrix_verdict = "RED"` 而 `gate_verdict_top_level = {"verdict":"PASS","n_checks":48,"n_red":0,...}`（那是 `run_20260930_073852` 那一轮）⇒ 这正是裁定 97.3-3 把 AND 的对象从顶层 `verdict` 收窄到 `verdict_class1` 的**实测起因**，与 Part B 直接相关。

### A.4 上一轮权威闸跑（A2 正在消费的那一轮）的实测判词

轮次：`runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156`
`⟨part_A_e4_teeth.authoritative_gate_run⟩`

- 臂内件 `arm_mainline/mainline_status.json` = **6728 ln(`wc -l`) `e72776306f98`**（210240 B）
- 同轮 `gate_verdict.json` = **1928053 ln(`wc -l`) `fa59b263c5fa`**（99391987 B）；单遍流式复算 sha **相符**，顶层 `verdict` 首个命中 = `PASS`
- `matrix.json` = **99131 ln(`wc -l`) `46f63721ff73`**（4415778 B），**49 行**，按 `stats_provenance` 分档：`formal40_bc_source` **8** · `formal40_lerobot_crosscheck` **16** · `env_derived_diagnostic_only` **24** · `yam_abc130k_mustred_branch` **1**

**权威档（= BC 真正要吃的 `formal40_bc_source` 8 行）**：

| 牙 | 8 行状态直方图 | `blocking` | 不足维（并集） |
|---|---|---|---|
| `Tb_scale_floor_effective` | **WARN × 8** | `False` | `[0,3,5,7,10,12]` |
| `Tr3_near_constant_floor_material` | **PASS × 4 / WARN × 4** | `False` | `[3,10]` |
| `Tz_denom_strictly_positive` | **PASS × 8** | `True` | — |
| `Tres_per_dim_resolution_floor` | **PASS × 8** | `True` | — |

**全 49 行（含诊断/stress/必红分支臂，只作背景，不与权威档混算）**：`Tb` = PASS 25 / WARN 24；`Tr3` = PASS 13 / WARN 12 / **N_A 24**（非主线臂出 N_A 而不是红，裁定 72-2 的极性要求）；`Tz` = PASS 49；`Tres` = PASS 49。

臂内件散文里那份 WARN 计数（AST 从 `mainline_finding.finding` 解析，不手抄）：`{"Tb_scale_floor_effective": 8, "Tresw_near_constant_low_resolution_is_warned": 8, "Tovr_out_of_interval_overflow_is_warned": 8, "Tr3_near_constant_floor_material": 4}` ⇒ **与逐行扫描一致**，两条独立路径同值。

### A.5 held-out 盲维登记（裁定 94.3 的两字段，Ⅱ 类不阻塞）

`⟨…authoritative_gate_run.heldout_blindness_ruling_94_3⟩`

- `measurement_status = measured`，`n_rows = 8`，`n_rows_measured = 8`，`n_dims = 14`，`blind_dim_threshold = 8`（状态 `d_calibrated_from_formal40_all_caliber`，复用 `Tres` 已定标的 8、不新造数）
- `n_distinct_heldout_patterns = **2**`（**不是 1**）：两种模式只在 **dim10** 上差 1（`4` vs `5`），其余 13 维逐字相同
  - `[3,97,106,2,38,3,35,4,111,108,**4**,46,5,36]`
  - `[3,97,106,2,38,3,35,4,111,108,**5**,46,5,36]`
- `correctness_blind_dims_union = [0,3,5,7,10,12]`（两种模式下都是这六维 ⇒ 并集稳定）
- **纪律提醒（写给任何引用本件的人）**：这六维上正确性族（`Td2`/`Te1`/`Te2`/`Tsat`/`Tcov`/`Tesc`）是 `not_measured`；偿清之前不得写「归一化器已通过正确性验证」。A2 的准入件已把这条 WARN 带上了（`correctness_family_blind_on_some_dims`），**C2 确认它仍在**。

### A.6 E4 的三条处置路径（供 D 裁；**Step-1 期间一律不动**）

| 选项 | 内容 | 代价 | 触不触冻结/治理 |
|---|---|---|---|
| **甲（= 现状，C2 建议 Step-1 期间采此）** | 两牙保持 `blocking=False`（WARN）；硬红由 `Tz`（全臂）+ `Tres`（逐维·全量口径）承担 | 0（不动任何字节）。残余风险 = E4 的两个失效形态在主线**不阻塞**，只登记 | 不触 |
| **乙（Step-1 之后再谈）** | 给 `min_bins_occupied` / `floor_materiality_fraction` 定标，然后恢复 blocking | 一次**全量闸重跑**（须排队，裁定 104-②）+ D 定标；`floor_materiality_fraction` 还缺一个**本轮没有的测量**（见下） | 触冻结面（`harness/norm_contract.py`）⇒ 必须 D 显式解冻 |
| **丙（纯文书，随时可做）** | 不改牙，改**登记口径**：里程碑审查里把这两把 WARN 牙显式列成「阈值未定标 ⇒ 只登记、不阻塞」，与六维盲点并列，避免 WARN 被读成「已通过的检查」 | 0（只写文书） | 不触 |

**乙的前置（必须先拿到，否则按红线不得 blocking）**：

1. **口径**：只能用**全量**（`summary_all`，n=11035）。held-out 口径已被裁定 94.2 的三条独立实测判为「**无判据力**」（不是「恒红」）：留出集形状说 / 无判据力说 / 极性说。若拿 held-out 定标 `min_bins_occupied`，等于把 `Tb` 恢复成一把在权威档上 **8/8 WARN** 的牙 —— 那不是定标，是恒红。
2. **同源**：`min_bins_occupied` 若恢复为判据，必须与 `Tres` 的 `min_bins_occupied_non_near_constant = 8` **同源同值**，否则「每维分辨率够不够」这件事在本仓会有两把尺（`Tb` 用 held-out、`Tres` 用全量），而它们的不足维集合不同（`[0,3,5,7,10,12]` vs `[3,10]`）⇒ 消费方无法判断该信哪一把。
3. **`floor_materiality_fraction` 缺的测量**：现值 = `FLOOR_MATERIALITY_FRACTION`（源码散文写 0.02），它判的是「近常量维的下限值本身是否 ≥ 系数 × 物理行程」。要定标它，需要 formal-40 上**逐维**的 `floor_d / physical_range_d` 分布（尤其是 F1/F2 两族、hold 相），本轮**没有这个测量件** ⇒ 按 `redline_provenance_discipline`，它现在只能是 `registered_measurement_not_a_judgment`，**不得**作为 blocking 判据。C2 可在 Step-1 之后用只读探针把这个分布量出来（不上卡、不重跑闸：读既有 `matrix.json` 的 `floor` 与 `physical_range` 字段即可），**但本轮不做**（101.1 + 104-②）。

### A.7 C2 明确不做的事（Part A）

- 不改 `Tb`/`Tr3`/`Tz`/`Tres` 的 `blocking`、`applies_when`、断言文本、阈值、口径 —— **一个字节不动**（冻结面 `harness/norm_contract.py` `91795179de7e`，取证器跑前跑后 sha 复算相符：`⟨frozen_surface_integrity.unchanged_by_this_probe⟩ = true`）
- 不重跑全量闸、不上卡、不动 stats 档（`b2150e0a3264`）与 npz（`a84a26079550`）
- 不新增牙、不新增身份规则（裁定 101.1）

---

## Part B · ③ 号问题（准入闸 ∧ 质量闸）：耦合**已落地**，但主线即将起跑的那次调用**不经过它**

### B.0 一句话结论

③ 号问题**不再是「脱钩」**：`harness/bc_admission_gate.py:633` 确实 import 并调用 C2 契约层的 `bc_admission()`，R3 只从实物读 `verdict_class1`、缺失即拒，`bc_blocking_caliber` 已按裁定 97.5 收窄成三条，stats / npz / gate_verdict / 臂内件 / G14 证据**全部由消费方自己复算 sha** 对账，负向腿在盘（3 腿里 1 腿 `admitted=false`）。**但**：Step-1 的守望器将起跑的命令是 `--stages train,rollout,report`，**不含 `admission`**，而 `main()` 里唯一的准入入口是 `if "admission" in stages:`，`stage_train` / `stage_rollout` 内部**没有任何准入复检** ⇒ **真正训练的那次调用不会求值这个 AND**；`stage_report` 随后用 `sorted(glob(...))[-1]` 绑到 16:42 的旧准入件，而那份件的 producer 与将训练的入口脚本**不是同一版本**。这是**证据链缺口**，不是实质准入失效（下面 B.3-G1 给了「为什么实质结论仍然有效」的四个身份实测）。

### B.1 已落地的耦合（码层事实，行号 = `line_no_as_of`）

身份（as_of `2026-09-30T19:35:28+08:00`）：`⟨part_B_bc_coupling.code_facts.identities⟩`
- `harness/bc_admission_gate.py` = **1925 ln(`wc -l`) `41f751019e69`**（mtime 14:44:37）
- `harness/norm_contract.py` = **1908 ln(`wc -l`) `91795179de7e`**（mtime 13:13:28，冻结面）
- `scripts/a2_step1_bc_overfit.py` = **4327 ln(`wc -l`) `2ec02373d3f6`**（mtime **19:30:00** ⇒ **活体移动靶**，见 §D.2）
- `tmp/a2_step1_watcher.sh` = **130 ln(`wc -l`) `d19c42a318e2`**（mtime 18:52:35）

| # | 事实 | 位置 |
|---|---|---|
| 1 | 消费方**调用 C2 的函数**、不重造判据：`c2_admission = bc_admission(prov, gate_verdict=v_top, gate_verdict_class1=vc1_file, …)` | `harness/bc_admission_gate.py:633` |
| 2 | R3：`verdict_class1` **只从实物读**（`checks["verdict_class1_from_artifact"]`），缺失 ⇒ `refuse("verdict_class1_not_measured")`；不等于声明 ⇒ `refuse("verdict_class1_declaration_mismatch")`；≠ PASS ⇒ `refuse("verdict_class1_not_pass")`；并显式钉「不许拿顶层 verdict 顶替」 | `:603 / :605 / :607 / :613 / :618` |
| 3 | 禁训判据 = **只有三个**（`verdict_class1=RED` ∨ `admissible_for_bc=false` ∨ `Tp5` 同源不成立） | `:743` |
| 4 | 存量标签 vs 重算值**双向都取**，不一致 ⇒ 拒（`arm_admission_label_disagrees_with_recomputation`） | `:640–660` 区间 |
| 5 | **stats 档自己复算 sha** 对账（`stats_sha256_mismatch` / `stats_unreadable` / `stats_not_inside_declared_run_dir` / `stats_provenance_declaration_mismatch` / `stats_representation_version_mismatch`） | `⟨…gate_stats_recompute.hits⟩` |
| 6 | **npz 自己复算 sha** + 广播声明 vs 臂内件 `checked_path` 必须同一份（`npz_sha256_mismatch` / `npz_declaration_disagrees_with_arm` / `npz_identity_not_declared`） | `⟨…gate_npz_recompute.hits⟩` |
| 7 | 契约层 `admissible_for_bc` **仍是纯标签派生**（`prov in BC_ADMISSIBLE_PROVENANCES`）—— 这是**刻意设计**（不合并「标签错」与「闸红」两种失效）；闸证据走独立字段 + 独立牙 `Tbcad_admission_requires_green_gate`（`blocking=True`、`applies_when=consumer=='bc'`，缺 class-1 证据 ⇒ `None` ⇒ 牙红） | `harness/norm_contract.py:526`（标签）· `:1129`（牙） |
| 8 | `control_hz` 同频纪律（29.4118 Hz）缺失即拒 | `⟨…gate_npz_recompute⟩` 同段的 `control_hz_not_declared` |

### B.2 已验证的腿（正向 + 负向，全在盘）

`⟨part_B_bc_coupling.admission_artifact⟩` · `⟨part_B_bc_coupling.negative_legs⟩`

- **正向（主线在用的那份）**：`runs/vla/a2_s3_bc_overfit_20260930/BC_ADMISSION_STEP1_20260930_164227.json` = **1301 ln(`wc -l`) `fec7ad9ee336`**（63709 B，as_of `2026-09-30T16:42:24+08:00`）
  - `admitted = true`，规则 = 「C2 的 `consume_c2_broadcast().admitted` **∧** A2 自己的先落腿牙（AND，不是 OR）」
  - `blocking_refusals = []`、`not_measured_items = []`、`warnings = []`（A2 顶层）；消费层 `warnings_extra` 有 **3** 条（盲维 / 臂内件散文过期 / `control_hz` 只是调用方声明）
  - 复算相符的身份：`verdict_class1` 从实物读到 **`PASS`**；`gate_verdict.json` 扫到 `{"verdict":"PASS","verdict_class1":"PASS"}`；stats 复算 `b2150e0a3264` = 声明值；`npz_crosscheck.same_source_holds = **true**`（broadcast 与臂内件 `checked_path` 同路径同 sha `a84a26079550`）
  - `authorization_to_start_bc = false`，且件内自注「本件是**准入判定**，不是开跑授权」⇒ **准入 ≠ 开跑授权**这条语义在盘上是清楚的
- **负向腿 3 条**：`runs/vla/a2_bc_admission_consume_20260930_run{1,2,3}` 的 `admitted` = **true / false / true**（`705845f8d421` / `e104ea4c2f66` / `3f5749d95801`）⇒ 「必须放行」与「必须拒」两向都在实物上验过，不是只有正向。

### B.3 残差缺口清单（**只登记 + 只提方案，一条都不落地**）

| ID | 缺口 | 证据（字段/行号） | 建议类分 | 是否阻塞 Step-1 | 归属 |
|---|---|---|---|---|---|
| **G1** | **主线即将起跑的调用不经过准入闸**：守望器 `tmp/a2_step1_watcher.sh:114` 的命令是 `--stages train,rollout,report`（`admission_in_stages = false`）；`scripts/a2_step1_bc_overfit.py:4250` 的 `if "admission" in stages:` 是**唯一**入口；全文 25 处 `admission` 命中里没有一处在 `stage_train`/`stage_rollout` 内（穷举在案）；`stage_report:3644-3645` 用 `sorted(glob)[-1]` 绑**glob-latest**，会绑到 16:42 那份，而它的 producer 是 `136eaf0f95c9`（184821 B / 2881 ln）≠ 将训练的 `2ec02373d3f6`（292687 B / 4327 ln） | `⟨…code_facts.watcher_launch_command⟩`、`⟨…entry_stage_gate⟩`、`⟨…entry_admission_references_by_region⟩`、`⟨…admission_artifact.producer_version_drift⟩` | **Ⅰ 类候选**（控制与数据正确性）——但**不是** Step-1 的出场判据（D 已裁 Step-1 出场判据不含闸 verdict） | **否** | 修法在 **A2 侧**（不改 C2 冻结面、不新增牙即可闭合，见 B.4-甲） |
| **G2** | **`broadcast_crosscheck` 这条腿在单载体稳态下永不触发，且不进 `not_measured_items`、不出 warning，而判定件自称 `measured`**：阻塞条件是 `measured ∧ not agree`（`bc_admission_gate.py:1569`）；A2 活件里 `sources_given={"markdown":true,"json":false}`、`measurement_status="not_measured"`、而 `decision_measurement_status="measured"`、`not_measured_items=[]`、`warnings=[]` | `⟨…code_facts.gate_crosscheck_leg.blocking_condition_verbatim⟩`、`⟨…admission_artifact.consume_level.broadcast_crosscheck⟩`、`⟨…decision_level.decision_measurement_status⟩` | **Ⅱ 类**（实验解释风险）+ 与红线 `absence_of_measurement_is_not_measurement_of_absence` / 缺陷类 ⑲ 同族 | 否 | **C2 侧为主**（我是广播发布者，从未发过 JSON 载体）+ 消费侧的 `not_measured` 传播 |
| **G3** | **广播件是稳定名活件**（`BROADCAST_DOC_DEFAULT`，`bc_admission_gate.py:192`），消费方读「当下这份」。实测：A2 消费时 `408b667d0fda` / 19238 B，现值 `b1882c7a3546` / 20639 B；**前 19238 字节 sha 复算 = `408b667d0fda`** ⇒ **纯追加**，A2 读过的字节一个都没被改（`n_bytes_appended = 1401`）。缺口是：**没有牙在 train 时复核「广播件仍是那次准入读过那份的前缀」** | `⟨…admission_artifact.broadcast_doc_drift⟩`（`prefix_sha_equals_consumed_sha = true`） | **Ⅲ 类**（文档完整性）——本次实测**无损** | 否 | C2（发布纪律：追加不覆写，已守）+ 可选的消费侧复核 |
| **G4** | 臂内件 `next_required_action` 散文过期（仍写「闸侧重跑 ⇒ 0 红后本档 stats 才是 S3 BC 的输入」，而该前置已满足）。A2 已自己 WARN 登记为 `arm_next_required_action_prose_is_stale`；C2 按裁定 97.3-5（闸侧冻结）**不改生成物字段** ⇒ 只登记 | `⟨…admission_artifact.consume_level.warnings_extra_reason_codes⟩`、`⟨…authoritative_gate_run.arm_next_required_action_verbatim⟩` | **Ⅲ 类** | 否 | C2（Step-1 后随下一轮闸跑自然刷新） |
| **G5** | `control_hz`（29.4118 Hz 同频）是**调用方声明**、不是从实物读出（臂内件没有这个字段）。A2 已自己 WARN 登记 `control_hz_is_caller_declaration`，并要求 BC 运行时把实际用的 `control_hz` 落进 run 产物 | 同上 | **Ⅱ 类** | 否 | **A2 侧**（train 产物里落 `control_hz` 实测值） |

**G1 的缓解事实（必须与缺口并列报，否则会读成「准入失效」）**：那次准入结论依赖的四个身份，在 16:42 之后**都没有变**，且判据模块本身**早于**准入时刻：

| 依赖 | 身份 | 16:42 之后是否变化 |
|---|---|---|
| stats 档 | `b2150e0a3264` | 未变（冻结面，裁定 104-②） |
| 源数据 npz | `a84a26079550`（mtime `2026-09-30T05:52:57+08:00`） | 未变 |
| 臂内件 / 同轮 gate_verdict | `e72776306f98` / `fa59b263c5fa` | 未变（只读历史件） |
| 判据模块 | `bc_admission_gate.py` `41f751019e69`（mtime 14:44:37）· `norm_contract.py` `91795179de7e`（mtime 13:13:28） | 未变，且都**早于** 16:42 ⇒ 判据形状没变 |
| 变化的只有 | `scripts/a2_step1_bc_overfit.py`：`136eaf0f95c9` → `2ec02373d3f6` | 前像在盘（`before_images/a2_step1_bc_overfit.py.before_136eaf0f95c9`，sha 复算相符）⇒ **可追溯，但不是同版本自证** |

⇒ **C2 的定性**：G1 是「**证据链没有随载荷一起刷新**」，不是「准入结论错了」。修法应当是**让证据链刷新一次**（B.4-甲），而不是重判准入。

### B.3.1 G1 的**穷举**证明（不是抽样，也不是「我没看见」）

对 `scripts/a2_step1_bc_overfit.py`（`2ec02373d3f6`，4327 ln，as_of `2026-09-30T19:35:28+08:00`）全文小写不敏感搜 `admission`，**25 处命中全部列出**在 `⟨part_B_bc_coupling.code_facts.entry_admission_references_by_region.hits⟩`。把它们与函数区间对照（`grep -n "^def stage_"` 实测）：

| 函数 | 行区间 | 区间内 `admission` 命中数 |
|---|---|---|
| `stage_admission` | 787–887 | 8（`:787/:792/:872/:878/:880/:882` 等，本阶段自身） |
| `stage_prereg` / `stage_cache` / `stage_probe` | 888–2198 | 0 |
| **`stage_train`** | **2199–3162** | **0** |
| **`stage_rollout`** | **3163–3640** | **0** |
| `stage_report` | 3641–4127 | 2（`:3644` glob-latest、`:3654` 把 `admitted` 抄进报告） |
| `main` | 4128–末 | 5（`:4250/:4251/:4252/:4254/:4255`，**唯一**的准入入口） |

⇒ 「`stage_train` / `stage_rollout` 内部没有任何准入复检」这句话的依据是**穷举命中 + 区间归属**，不是「C2 没找到」。红线 `absence_of_measurement_is_not_measurement_of_absence` 在这里的用法是：**否定存在性必须由穷举扫描支撑**，本件给了。

**同一条口径也用在了 `--stages` 上**：守望器全文只有 `train,rollout,report` 这一个 stages token（`⟨…watcher_launch_command.stages_tokens_found⟩`），`admission_in_stages = false` 是**按逗号分割后逐 token 判**的，不是子串匹配。

### B.4 方案选项（**只出方案，不落地**；裁定 101.1 治理冻结在）

| 选项 | 内容 | 代价 | 触不触 101.1 / 冻结面 | C2 建议 |
|---|---|---|---|---|
| **甲** | 起跑前**单独**跑一次 CPU-only 准入：`--stages admission`。依据：`GPU_STAGES = ("probe","train","rollout")`（`:133`）⇒ `need_gpu=False`、**不需要**窗口申报、不受排队影响；A2 上一次实测墙钟 **3.336 s**。产出一份 producer sha == 将训练版本的新准入件，`stage_report` 的 glob-latest 自然绑到新件 | ~3.4 s CPU；一次落盘 | **不触**（不新增牙、不改判据、不碰 C2 冻结面；只是把已有阶段跑一次） | **推荐**（若 D 要在 Step-1 起跑前闭合 G1） |
| **乙** | 守望器 `:114` 的 stages 改一个 token → `admission,train,rollout,report` | 准入会跑在 **GPU 窗口内**（`window.open()` 在阶段循环之前）⇒ 3.4 s CPU 摆动可能进窗口污染判据（loadavg swing）；且准入若拒，窗口已开 ⇒ 还要补一次 yield 记账 | 不触 101.1，但与裁定 102.2-③ 的窗口口径有摩擦 | **不推荐** |
| **丙** | 在 `stage_train` 入口新增一颗牙：「新鲜准入件必须存在 ∧ 其 `producer.sha256_12` == 自身 ∧ 其 stats/npz 身份 == 本次装载的」 | 新增牙 ⇒ **触 101.1 治理冻结**；且要两向变异体自检 | **触** ⇒ 本轮**不落地** | 登记为 **Step-1 之后的候选**（这也是 ③ 号问题的**终态**修法：把「准入与训练同版本」变成有牙的事实，而不是靠调用顺序） |
| **丁（G2 专用）** | C2 补发**第二件载体**（JSON 版广播），让 `crosscheck_broadcast_sources` 真正有对象；并把「单载体 ⇒ crosscheck `not_measured`」显式写进广播件的 §5，同时建议消费侧把这条 `not_measured` 传播进 `not_measured_items` | C2 侧一次落盘（不新增牙）；消费侧的传播改动属 A2/B2 的写入面 | 发布 JSON 载体**不触** 101.1（不是新门禁、不是新牙）；消费侧改记账**需 D 裁** | **推荐 C2 侧那半**；消费侧那半请 D 指派 |

> **甲 vs 丙 的关系**：甲是**本轮可做的证据刷新**，丙是**Step-1 后的结构性修法**。两者不冲突。C2 的建议是：**Step-1 之前只做甲（且只在 D 批准后由 A2 执行，C2 不代跑）**，丙留到 Step-1 里程碑审查之后与 ③ 号问题一起裁。

### B.5 C2 明确不做的事（Part B）

- **不代 A2 跑 `--stages admission`**（那是 A2 的写入面，会往 `runs/vla/a2_s3_bc_overfit_20260930/` 落件）；C2 只给方案与证据
- 不改 `harness/bc_admission_gate.py`（不是 C2 的写入面）、不改 `scripts/a2_step1_bc_overfit.py`（A2 的活体移动靶）、不改守望器
- 不新增牙、不新增身份规则、不改 `bc_blocking_caliber` 的三条判据
- 不改 `admissible_for_bc` 的标签语义（它是刻意设计，合并两种失效会让「标签错」与「闸红」无法区分）

---

## Part C · 搬迁的盘上事实追平 + 两处 OPEN（不自选）

### C.1 盘上事实 vs 待命令·二 的措辞

`⟨part_C_move_reconciliation⟩`

- **盘上事实**：补单六-② 的搬迁**已执行完**。`runs/vla/c2_docs_ruling99/MOVE_RECORD.json` = **2250 ln(`wc -l`) `4bc4fa4b0c29`**（102891 B，mtime 17:55:05）；`summary` = `n_rows_in_plan 29 / n_moved 26 / n_failed 0 / n_hold_back 3`；`REPOINT_RECORD.json` = **635 ln(`wc -l`) `c380ee745394`**；`before_images/` 有 **26** 件
- **监管件措辞**：`d_handoff_to_c2_20260930.md`（`52ab5c8317c7`）的「待命令·二」仍写「**搬迁（`OPEN-C2-MOVE-DEFERRED`）仍是纯整理、仍延期**」
- ⇒ **措辞与盘上事实不符**，需要 D 追平。C2 **不自选**处置：
  - **甲 = 追认**（承认搬迁已在 17:35 批次执行完，`OPEN-C2-MOVE-DEFERRED` 改为「已执行、待 D 复核」）
  - **乙 = 回滚**（用 `before_images/` + `REPOINT_RECORD.json` 把 26 件搬回原位；C2 有能力做，但**等 D 令**）
- **背景（C2 已自报，不重复辩解）**：这次搬迁发生在 D 17:26:24 撤回授权**之后**，已按**抗命类**自报在 `docs/c2_handoff_to_d_20260930.md` §10.11（`f0e545acf0b5` 那一版）与日报 §C2-4。

### C.2 账面缺口（未落盘过，本件第一次落盘）

- 执行搬迁那版 mover（`fa9ac65851d9` / 481 ln）**没有留前像**，只有身份记在 `MOVE_RECORD.json` 的 v1 里（v1 = `ce7945fab219`，保留为版本件）。
- **缓解**：v1 与终版的 `items` / `summary` 段逐字节相同 ⇒ 台账内容可交叉验证；缺的只是「执行那一刻的脚本字节」。
- 请求：按缺陷类登记（**Ⅲ 类**，登记不阻塞），处置由 D 定。

---

## Part D · 身份、纪律与停点

### D.1 本件与证据件的身份

| 件 | 身份 |
|---|---|
| 证据件 | `runs/vla/c2_e4_ruling_material_20260930/E4_EVIDENCE.json` = **2537 ln(`wc -l`) `c9eddacec6c2`**（100022 B，as_of `2026-09-30T19:35:28+08:00`） |
| 取证器 | `scripts/c2_e4_ruling_material.py` = **935 ln(`wc -l`) `e7fc265707e8`**（`c2_` 前缀；只读他线、只写自己目录 ⇒ 属 `declared_readonly_probe_needs_no_ticket`） |
| 冻结面完整性 | 取证器跑前跑后复算：`harness/norm_contract.py` `91795179de7e` · `scripts/c2_build_norm_stats.py` `1bc468012cff` · `scripts/c2_gate_norm_contract.py` `c9445a9a7f6a` —— **三件全相符**，`unchanged_by_this_probe = true` |
| 资源 | 取证器全程 `nice -n 19`，实测墙钟 **~2 s**（含 `gate_verdict.json` 95 MB 的**单遍**流式哈希）；未上卡、未重跑闸。落盘时 `loadavg` 见 `⟨resource_readings.loadavg⟩`（41 量级，cgroup 配额 12 核，A2 在排队） |

### D.2 C2 撤回/更正自己上一轮的三个数字（同族于 D 的 ⑲，C2 记在自己名下）

| # | 上一轮 C2 说过 | 本轮实测 | 处置 |
|---|---|---|---|
| 1 | 「`gate_verdict.json` 含 `verdict_class1` **43485** 处、`triage_class` **58** 处、`Tbcad_…` **1267** 处」 | 单遍流式子串计数（**上界**口径，64 B 跨块重叠可能重复计一次）：`"verdict_class1"`（带引号）= **1**、`verdict_class1`（不带引号）= **55329**、`"triage_class"` = **54**、`triage_class` = **59**、`Tbcad_admission_requires_green_gate` = **1269** | **撤回旧数字**。旧数字没有口径（带不带引号、哪一轮）⇒ 按裁定 98.5 属**身份/口径错**。新数字只用于「存在性/量级」，不用于精确对账 |
| 2 | 「`Tb` WARN×8、`Tr3` WARN×4/GREEN×4」（未点名是 49 行里的哪 8 行） | 权威档（`formal40_bc_source` **8 行**）：`Tb` WARN×8、`Tr3` PASS×4/WARN×4；**全 49 行**：`Tb` PASS 25/WARN 24、`Tr3` PASS 13/WARN 12/**N_A 24** | **补口径**。旧说法数字对、但**作用域没点名** ⇒ 会被读成「整轮只有 8 行」。现在分档报 |
| 3 | 「held-out 逐维占用 `[3,97,106,2,38,3,35,4,111,108,5,46,5,36]`」（当成唯一模式） | `n_distinct_heldout_patterns = **2**`，两模式在 **dim10** 上差 1（`4` vs `5`） | **更正**。盲维并集不受影响（两种模式都是 `[0,3,5,7,10,12]`） |
| 4 | 交接摘要里把 `scripts/a2_step1_bc_overfit.py` 的行号（`:104` import / `:781` 落件）当常驻身份 | 该文件在 19:16→19:30 之间从 `e75d2284fd6c`（4206 ln）变为 `2ec02373d3f6`（4327 ln）⇒ **活体移动靶** | **改为「sha + as_of」成对引用**（缺陷类 ㉒：把时点读数当常驻身份）。本件所有该文件的行号都带 `as_of 19:35:28` 与 sha |

### D.3 停点

- **本件交付即停**：E4 裁定材料（Part A）+ ③ 号问题方案（Part B）+ 搬迁追平（Part C）都已落盘，**不落地任何新牙、不改任何极性、不重跑闸、不上卡**。
- **等 D 裁的三件**（C2 不自选）：① E4 采甲/乙/丙（C2 建议 Step-1 期间 = 甲，Step-1 后 = 丙，乙需先补 `floor_d / physical_range_d` 的逐维测量）；② G1 采甲/乙/丙（C2 建议 = 甲，且**由 A2 执行**）；③ 搬迁甲（追认）/ 乙（回滚）。
- **C2 可立刻做、但等 D 点头才做的两件**：丁（补发 JSON 载体广播，闭合 G2 的 C2 那一半）· `floor_d / physical_range_d` 的只读逐维测量（乙 的前置，读既有 `matrix.json` 即可，不上卡、不重跑闸）。
- 主次不变：**主 = A2 的 Step-1**；C2 是辅线，不深入非主线细节。
