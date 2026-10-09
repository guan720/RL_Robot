# C2 → A2 交接：**BC 消费口径的成对广播**（裁定 96.1-④ / 97.5-① / 补单三 §一）· 2026-09-30 13:4x · C2

> **本件是 A2 第 1 步（六步序列，裁定 95.2）开跑前等的那件文书。**
> **所有 sha256[:12] / 行数 / 字节数都是 C2 本机取值**（`sha256sum` + `wc -l` + `stat -c %s`），
> `as_of = 2026-09-30T13:45:57+08:00`，**绝不转录**。**行数口径 = `wc -l`**（产物末行无换行符 ⇒
> 比 Python 的行计数少 1；D 在 §97.7 用的是同一口径）。
> **裁定 98.3 追加（as_of 2026-09-30T14:29+08:00）：本件已不再出现无口径名的行数字段**（裁定 98.3-② 禁的就是它）。行数字段一律点名口径：
> **`n_lines_wc` = 换行符个数（`wc -l`）**、**`n_lines_splitlines` = `len(read_text().splitlines())`**；
> 两件产物末行都**无换行符** ⇒ 两口径**差 1**（6728/6729、1928053/1928054）。
> **对账的唯一约束性判据 = `sha256[:12]`（裁定 98.3-①④）；行数只作旁证，且必须带口径名。**
> A2 的 `harness/bc_admission_gate.py` 实测口径 = `splitlines`（其 `N_LINES_CALIBER` 常量原文）⇒
> 与本件的 `n_lines_splitlines` 同口径；本件两个都给，A2 不必猜。
> **本件不含任何 policy 指标**（裁定 46 能力声明禁令）；所有「绿 / PASS」**只指闸判词，不指能力**。

## 1. 成对身份（**两条必须一起用，缺一 ⇒ `LearnerRefused`**）

**① BC 消费口径 = 最新一次 class-1 绿的闸跑的臂内件**

| 项 | 值 |
|---|---|
| 完整路径 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/arm_mainline/mainline_status.json` |
| `sha256[:12]` | `e72776306f98` |
| `n_lines_wc`（`wc -l`） | 6728 |
| `n_lines_splitlines` | **6729**（= A2 的 `_stream_identity()` 会算出的那个数） |
| `ends_with_newline` | `false`（⇒ 两口径差 1，裁定 98.3 的实测原点） |
| `bytes` | 210240 |
| `mtime` | 2026-09-30 13:32:02 +08:00 |

**② 同轮闸判词（①自己证明不了「闸绿」，那个事实只在这份里）**

| 项 | 值 |
|---|---|
| 完整路径 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/gate_verdict.json` |
| `sha256[:12]` | `fa59b263c5fa` |
| `n_lines_wc`（`wc -l`） | 1928053 |
| `n_lines_splitlines` | **1928054** |
| `ends_with_newline` | `false` |
| `bytes` | 99391987 |
| `mtime` | 2026-09-30 13:33:51 +08:00 |
| `verdict` | **PASS** |
| `verdict_class1` | **PASS**（裁定 97.3-2 新增；**这才是 BC 准入 AND 的那一个**） |
| `n_checks` / `n_red` / `n_warn` / `n_n_a` | 54 / **0** / 0 / 0 |
| `n_red_class1` / `n_red_class2` / `n_red_class3` | **0** / 0 / 0 |
| `rerun_reason.status` | `declared`（裁定 97.4：本轮是 97.3 落码后 D 授权的那一次重跑，理由原文在产物里） |

**为什么必须成对（D 在 §97.7 亲核的形态，C2 复测成立）**：①里的 `bc_admission` 实测 =
`gate_verdict: null` / `gate_verdict_class1: null` / `*_measurement_status: "not_measured"`。
**这不是缺陷、也不是"闸没绿"**：臂内件在 `gate_verdict.json` **之前**产出，生产方不自引
（裁定 96.1-④ 追认 F 的撤回：三个字段由**调用方**传入）。三值纪律在这里是**对的** ——
它写 `not_measured` 而**没有**静默当绿。⇒ **「闸绿」这个事实只能从②读。**

## 2. A2 的义务（T-A2-7 对账，裁定 96.1-④ / 97.5）

1. **只对 §1-① 那一条完整路径**复算对账。**不许自己 `glob` 后挑一份**（这是"谁先写 BC 谁就把
   RED 的 stats 合法吃进去"的第二道锁；第一道 = C2 已落码的 `Tbcad_admission_requires_green_gate`）。
2. **自己复算** `sha256[:12]` 与 §1-① 的 `e72776306f98` 比对；不一致 ⇒ `LearnerRefused`。
3. **AND** §1-② 的 `verdict_class1`（必须 = `PASS`），并**自己复算**②的 `sha256[:12]` 与
   `fa59b263c5fa` 比对；不一致 ⇒ `LearnerRefused`。
4. **不得只凭** `admissible_for_bc=true` 开跑；**两条身份缺一 ⇒ `LearnerRefused`**。
5. **裁定 97.5 的口径**：BC 被禁的判据 = `verdict_class1 = RED` **或** `admissible_for_bc = false`
   **或** `Tp5` 同源不成立。**闸顶层 `verdict = RED` 本身不再等于「BC 被禁」**，任何线（含 D）
   不得再拿顶层 RED 当停训理由。（本轮两个判词都是 PASS，所以这条现在是空的；写下来是因为
   它在下一轮**可能不空**：Ⅱ/Ⅲ 类的 run 级元牙红会让顶层 RED 而 class-1 仍绿。）

## 3. 归一化 stats：**唯一一档**，A2 不必也不许挑

| 项 | 值 |
|---|---|
| 完整路径 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/arm_mainline/stats/s1_sim_demo_bidir__quantiles_with_scale_floor__F1_physical_range_fraction_0.05__mainline_path_check.json` |
| `sha256[:12]` | `b2150e0a3264` · `bytes` 26416 · `n_lines_wc`（`wc -l`）845 · `n_lines_splitlines` 846 · `ends_with_newline` false |
| `case` / `family` / `coef` | `quantiles_with_scale_floor` / `F1_physical_range_fraction` / `0.05` |
| `representation_version` | `s1-sim-demo-bidir-quantiles-with-scale-floor-F1-physical-range-fraction-coef0.05-ruling87-3-1-cover-declared-interval-hb1-cap9946e1d0-srcef50e89c-v2` |
| `stats_provenance` | `formal40_bc_source`（裁定 85.4-3 同源硬闸：**BC 只认这一档标签**） |
| `consumer_at_build` | `path_check`（该臂的**用途**是通路验证；标签是 `formal40_bc_source` ⇒ `admissible_for_bc=true`） |
| `n_dims` | 14 |
| 源数据 | `runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` = `a84a26079550`（40 集 / 11035 帧）· `npz_manifest_sha256_12 = e251dc6e07c7` |

**为什么是 quantiles 档而不是 identity 档**（裁定 69 要求两份提案并行，两档都在臂内、都 PASS）：
π₀.₅ 的 `normalize_processor` **内部只算 `q99 - q01`**，下限无法从外部注入 ⇒ 下限只能**烘进
`q01/q99`**（契约层 `implementation_facts.floor_baked_into` 原文）。identity 档（`center`/`gain`）
进不了这条运行时通路。**若 A2 的运行时改用 center/gain 通路 ⇒ 必须先回报 D**（`representation_version`
会变，等于换 stats，而裁定 95.5 规定「stats 与阈值一经第 1 步开跑即冻结」）。

**为什么是 coef 0.05 而不是 0.02**：裁定 87.3 预登记的可证伪条件原文 =「formal-40 上若 F1@0.05 的
『下限实质无效维』> 0，或 `materiality_ratio` 最小值 < 1.5，则回退到 0.02 并重报」。
**本轮 formal-40 实测（`arm_mainline/matrix.json` 的主线行，本机读数）**：F1@0.05 ⇒
`Tr3_near_constant_floor_material = PASS`（不足维 `[]`）、`materiality_ratio_min = 2.5`（≥ 1.5）
⇒ **回退条件未触发，0.05 站得住**。对照：F1@0.02 的 `materiality_ratio_min = 1.0`（< 1.5）
⇒ 若回退到 0.02 反而会踩自己预登记的条件。**`coef_status` 字面仍是 `proposed_pending_s1`**
（生成物里的状态串，C2 未改；裁定 93.1-2 已把这类串改判为 `registered_measurement_not_a_judgment`）。

## 4. **必须随结果一起报的盲点**（裁定 94.3 两个字段，Ⅱ 类登记不阻塞，但不得被读成"已验证"）

- `heldout_bins_occupied_per_dim`（真 held-out = episodes `[19, 39]`，n = 547）实测有 **2 种不同图案**：
  `[3, 97, 106, 2, 38, 3, 35, 4, 111, 108, 5, 46, 5, 36]` 与 `[…, 4, …]`（**只有 dim10 差 1**：5 vs 4）。
- `correctness_blind_dims`（阈值 = 8 个 bin，D 定标）**并集 = `[0, 3, 5, 7, 10, 12]`**，8 行逐行都是这 6 维。
- **含义**：正确性族（held-out 家族的 `Td2` / `Te2` / `Tsat` 与 `Te1` / `Tcov` / `Tesc`）在这 **6 维上
  根本无从触发** ⇒ 它们的 PASS **不是**"这 6 维已被正确性验证"。**A2 报 BC 结果时不得把
  「归一化器已通过正确性验证」写成全 14 维的结论**（缺陷类 ⑲：报绿而绿来自覆盖不全）。
- 与 D 的独立复算**逐位相同**（裁定 94.1：D 自己的种子 `904011`、8 个 iid 547 帧子集）；
  D 的「采样计数假象」理由已被 **REFUTED**（`arithmetic_bound_binding = false`），真因是
  **留出集只有两条轨迹弧线** ⇒ 该修的是留出集的覆盖形状（裁定 94.4，**P2、排第 2 步之后**，
  因为它会换 stats、而第 1–2 步需要 stats 冻结）。**本轮不动。**

## 5. 两处**记录层**的坑，先说清楚（免得 A2 撞上）

1. **顶层件与臂内件曾分叉**（裁定 96.1-④ 的 Ⅰ 类红）：顶层 `mainline_status.json` 曾是 06:04:23 的
   `fc3f049753bf`（6445 ln / 198907 B，且**缺** 94.3 两个字段、`gate_verdict_reference` 为 `null`），
   顶层 `matrix.json` 曾是 `c3f3260e5cf1` 且**声明 `verdict = RED`**，而闸实际评测的臂内件是 PASS；
   49 份同名 stats **全部**字节不同。**已修（采 D 给的甲案）**：顶层 51 个文件已刷新为与臂内件
   **逐字节相同**（机器核过：51/51 `byte_identical = true`，0 分叉），前像在
   `runs/vla/c2_norm_contract_20260929/before_images/toplevel_pre_ruling97_3_fc3f049753bf/`（51 件），
   标记件 = `runs/vla/c2_norm_contract_20260929/TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json`
   （**改名后 = `7ff12c6b3e56` / `n_lines_wc` 486 / 34012 B**；原 `6c7dc5a6f67a` / 464 ln(`wc -l`) / 31881 B
   已被裁定 98.3-③ 的改名取代，前像 = `…/before_images/TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json.before_6c7dc5a6f67a`）。
   **但声明的 BC 消费路径仍是§1-① 的臂内件**，
   **各线一律不消费顶层件**（D §D96.9 的口径）。
2. **产物里有一句过期散文**：`mainline_status.json` 的 `next_required_action` 仍写着「闸侧……重跑 ⇒
   0 红后，本档 stats 才是 S3 BC 的输入」。**那个前置现已满足**（§1-② = PASS / `verdict_class1` = PASS /
   0 red）。C2 **没有**去改它：它是生成物字段，改它要么手改产物、要么改生成器文案，而裁定 97.3-5
   已对闸侧恢复冻结（不得再改判据形态）。⇒ **该字段的散文不是当前口径，以本件为准。**

## 6. 冻结与停点

- **裁定 95.5**：stats 与阈值**一经第 1 步开跑即冻结**；checkpoint 选择规则必须**开跑前预登记**
  （T-A2-8 同批）；模型选择用验证集、最终报告用另一份测试集；整条 episode 划分；
  **bin 占用数只描述覆盖、不得当能力判据**。
- **裁定 97.3-5**：§97.3 的四项已落码 ⇒ **闸侧冻结令恢复完全效力**（不得再新增 check、不得再改
  判据形态）。**C2 本轮不再重跑全量闸**（每轮 ~95 MB，`runs/` 已 ~39.5 GiB 且被 `.gitignore:12` 排除）。
- **C2 停点（裁定 95.8 / 97.5 / 补单三 §五）**：欠项 A（本件）+ B（顶层件）+ C（G20 例外登记）
  + D（§97.3 四项 + 一轮验证跑）**已全部交完 ⇒ C2 停，等 A2 第 1 步结果**。
  **用户已明示先暂停项目方向 ⇒ 各线停在 `ready`，不上卡、不开 BC。**

## 7. 裁定 98.3-③ 落地追加（C2 · as_of 2026-09-30T14:30:46+08:00）· **A2 直接可用的一段**

**本节是 §D98.3 点名的那件「分钟级改名」的落地记录，值一字未改，只改口径名。**

### 7.1 本件正文改了什么（就地改动全部列出，不藏）

| 位置 | 原 | 改后 |
|---|---|---|
| 抬头口径声明（第 4–6 行那块） | 「行数口径 = `wc -l`」 | 追加裁定 98.3 的**两口径并列**声明 + 「sha 是唯一约束性判据」 |
| §1-① 表 | `n_lines`（`wc -l`）= 6728 | `n_lines_wc` = 6728 **+ `n_lines_splitlines` = 6729 + `ends_with_newline` = false** |
| §1-② 表 | `n_lines`（`wc -l`）= 1928053 | `n_lines_wc` = 1928053 **+ `n_lines_splitlines` = 1928054 + `ends_with_newline` = false** |
| §3 表 stats 行 | `n_lines`（`wc -l`）845 | `n_lines_wc` 845 **+ `n_lines_splitlines` 846 + `ends_with_newline` false** |
| §5-1 标记件身份 | `6c7dc5a6f67a` / 464 ln / 31881 B | **`7ff12c6b3e56` / `n_lines_wc` 486 / 34012 B**（改名所致；前像留在 `…/before_images/…before_6c7dc5a6f67a`） |

- **机器自证（口径点名，as_of 2026-09-30T14:46+08:00）**：用 `re` 扫「无口径名的行数字段」（排除 `_wc` / `_splitlines` / `_caliber` 后缀）—— **正文 §1–§6 命中 = 0**；**§7 命中 = 5 处**，全部是更正/撤回记录里对**旧标签的引用**，按名字锚点逐条点名：§7.1 表格「原」列的三行（= §1-① 表 / §1-② 表 / §3 的 stats 行）· §7.1「标记件同步改名」那一条 · §7.4 引用 A2 `FORBIDDEN_BARE_LINE_KEYS` 防线原文的那一句。**记录一次改名必须点名被改的那个名字** ⇒ 这 5 处不是广播里的行数字段。**本条刻意不给行号**（裁定 96.1-①：活件引用用名字锚点 + 身份串）—— 理由是本件在 14:4x 被重写过一次，行号当场就漂了（那 5 处的末位由 **182** 变 **206**）；C2 先把行号写进去又改回来，属**同轮自纠**，并按裁定 46.4 记一次「跨口径/跨版本数字互搬」的近失。
- **标记件（`TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json`）同步改名**：两处 `n_lines` ⇒ `n_lines_splitlines`，
  并补 `n_lines_wc` / `ends_with_newline` / `n_lines_caliber` + 一块 `revision_ruling_98_3`（含**改名前**的自身身份与
  「本件自身 sha 因改名而变」的显式声明）。**它声明的两件产物字节未动**（`e72776306f98` / `fa59b263c5fa` 仍是原值）
  ⇒ **不触碰裁定 97.3-5 的闸侧冻结**（改的是文书，不是判据）。
- **一处如实披露**：标记件改名后 `ends_with_newline` 由 `false` 变 `true`（`apply_patch` 落盘时补了尾换行）⇒
  它自己的 `n_lines_wc` 与 `n_lines_splitlines` 现在**相等**（都是 486）。**被声明的那两件产物没有这个变化。**

### 7.2 A2 的对账：把哪几个数填进 `bc_admission_check(declaration=…)`

> 依据 = **A2 现行的** `harness/bc_admission_gate.py`（**`a32353aa76e1` / `n_lines_wc` 1898 / 121384 B / mtime 2026-09-30 14:40:41**，C2 只读、未改一字）。
> **本节在 14:4x 被 C2 重写过一次**：原先它是对着 A2 **13:47** 那一版写的（当时 `DECLARATION_REQUIRED_FIELDS` 里含
> `arm_mainline_status_n_lines` / `gate_verdict_n_lines` 两个**无口径名**的键）。**A2 已在 14:40:41 按裁定 98.5-②③ 改名**
> ⇒ 下表已换成 A2 现行的键名。（13:47 那一版的 sha C2 当时没取 ⇒ 记 **`not_measured`**，只记 mtime 与字段名原文。）
> **约束性判据只有 sha**：A2 现行 `DECLARATION_REQUIRED_FIELDS` = `declared_by` / `as_of` / `gate_run_dir` /
> 两条 `*_path` / 两条 `*_sha256_12` / `verdict_class1`；四个行数字段属 `DECLARATION_LINE_FIELDS`
> （**可选，但给了就按口径名逐个比对**；一个都不给 ⇒ A2 会落 `{tag}_n_lines_not_declared_with_caliber` 警告）
> ⇒ **C2 建议四个都给**，两种口径都点名。

| A2 现行的字段名（`a32353aa76e1`） | 填什么 | 口径 |
|---|---|---|
| `declared_by` | `C2` | — |
| `as_of` | `2026-09-30T13:40:38+08:00`（**身份测量时刻**；14:1x–14:3x 只改了文书口径名，**未重测任何产物**） | — |
| `gate_run_dir` | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156` | — |
| `arm_mainline_status_path` | §1-① 的完整路径 | — |
| `arm_mainline_status_sha256_12` | **`e72776306f98`** | **身份（唯一约束性）** |
| `arm_mainline_status_n_lines_wc` | **6728** | `wc -l` |
| `arm_mainline_status_n_lines_splitlines` | **6729** | `splitlines` |
| `gate_verdict_path` | §1-② 的完整路径 | — |
| `gate_verdict_sha256_12` | **`fa59b263c5fa`** | **身份（唯一约束性）** |
| `gate_verdict_n_lines_wc` | **1928053** | `wc -l` |
| `gate_verdict_n_lines_splitlines` | **1928054** | `splitlines` |
| `verdict_class1` | **`PASS`** | 只从实物读（A2 的 R3 已强制） |
| `g14_flip_evidence_*` | **C2 不代填**：裁定 97.3-4 明写 `checked_by = F`，语义判断归 F；A2 的模块注释也说明该路径可用 F 的台账**或**同轮 `gate_verdict.json` 本身（A2 14:21 那次实测用的就是同轮 `gate_verdict.json`，`n_lines_splitlines` 1928054） | — |

- **A2 还有一条文档解析臂**：`_caliber_of_line_key()` 能从**键名或行内注记**推口径（命中 `splitlines` / `_wc` / `wc -l` 字样）
  ⇒ 本件 §1 的两张表现在**两种口径都点名**，A2 直接解析本件也拿得到正确口径（它 14:21 那次就是解析本件拿到 `wc -l` 的 6728/1928053）。

### 7.3 **实测的 before / after**（改名到底解决了什么，不靠推测）

- **before（实测，已落盘）**：A2 的 `runs/vla/a2_bc_admission_consume_20260930_run1/BC_ADMISSION_DECISION_20260930_142124.json`
  （as_of **14:21:24**）的 `declaration_source` 实测 = `kind: c2_paired_broadcast` / `doc_path: docs/c2_to_a2_bc_stats_handoff_20260930.md` /
  `discovery_method:「解析 C2 广播件里点名的路径（无 glob、无 latest-run 推断）」`，读的是本件 **120 ln(`n_lines_wc`) / `1ffbe342f5bb`** 那一版。
  结果：**`admitted = true`、`blocking_refusals = []`**，但落了**恰好两条**口径警告 ——
  `arm_mainline_status_n_lines_mismatch`（复算 6729 ≠ 声明 6728）与 `gate_verdict_n_lines_mismatch`（复算 1928054 ≠ 声明 1928053），
  **两条都因 sha 相符而被 A2 降级为 `warnings`**。
- **⇒ D 在 §D98.3 的两个预测，一个成立一个不成立（都实测）**：**「口径混用会产生噪声警告」= 成立（就是这两条）**；
  **「会造成假 `LearnerRefused`、第 1 步白跑一轮」= 在 A2 现行实现下不成立**（A2 自己已把 sha 定为唯一约束性判据，
  行数不符只在 sha 也不符时才 `blocking`）。**C2 报这条不是为了争口径，是为了让 D 的风险登记对上实测。**
- **after = `not_measured`**：**C2 没有重跑 A2 的闸**（那是 A2 的写入面）⇒ 「改名后这两条警告消失」目前**只是预期，不是实测**。
  A2 下次消费本件时即可实测；本件已把两种口径都点名，A2 的解析臂与 `DECLARATION_LINE_FIELDS` 两条路都能对上。
- **顺带确认（对 C2 有用）**：A2 那次的 `warnings_extra` 里**已经带上了** C2 的 94.3 盲点维 `[0, 3, 5, 7, 10, 12]`
  与「臂内件 `next_required_action` 散文过期」两条 ⇒ **C2 的披露确实被下游消费了**，不是写了没人读（缺陷类 ⑳ 的反面）。

### 7.4 **撤回**一条原先给 D 的请示（不需要 D 裁了）

- C2 在 14:3x 那版写过「A2 的 `*_n_lines` 键名无口径名，是否改名请 D 裁」——**该观察已失效，C2 撤回**：
  A2 在 **14:40:41** 的版本 `a32353aa76e1` 里已经把行数字段改成 `*_n_lines_wc` / `*_n_lines_splitlines`（`DECLARATION_LINE_FIELDS`），
  并新增了「声明里出现裸 `n_lines` 键 ⇒ **只登记不比对**，并请广播方改名」的防线（`FORBIDDEN_BARE_LINE_KEYS` 分支）。
  ⇒ **D 不需要为这件事下裁**；C2 保留这条记录只是为了不让一个已失效的请示挂在 D 的待裁清单上。

---

## 追平注（裁定 100 / 补单六-②-1 · 2026-09-30T17:52:39+08:00 追加；**本件正文一字未改**，纯度自证 = 追加前 `head -N` 的 sha 与前像相同，读数见 C2 的 `MOVE_RECORD`/渲染件输出）
- **本件第 115 行**（`line_no_as_of`，时点读数）引的那份前像`before_images/TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json.before_6c7dc5a6f67a`**已随搬迁批次换了目录**：
  - 旧：`runs/vla/c2_norm_contract_20260929/` + `<tail>` ⇒ 新：`runs/vla/c2_docs_ruling99/` + `<tail>`（**tail 不变**）
  - **字节未变**：`sha256[:12]` 搬前 = 搬后（`6c7dc5a6f67a` = `6c7dc5a6f67a`，mtime 亦相同）
  - 逐件对账 = `runs/vla/c2_docs_ruling99/MOVE_RECORD.json`；全量映射规则与 26 件清单 = `docs/c2_handoff_to_d_20260930.md` §10.10-④。
- **A2 读这一件时请注意**：本件正文里其余的 `runs/vla/c2_norm_contract_20260929/…` 路径**都没有搬**（`stats/`、`gate/run_20260930_133156/…`、顶层 51 份便利副本、标记件、以及本件自己的两份前像 `…md.before_1ffbe342f5bb` / `…md.before_9d6b14f1e477` 全部原地未动 —— 后三件正是 B2/A2 活代码在读的，C2 特意留下）。
- **能力声明禁令不变（裁定 46）**：本件不含任何 policy 指标；Step 1 要消费的判定层与那一档 stats（`b2150e0a3264`）在冻结面上、一字未动。
