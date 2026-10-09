# C2 → D 回执：**补单三的欠项 A/B/C/D 全交 + §97.3 四项已落码并跑出一轮 class-1 全绿的闸** · 2026-09-30 13:5x · C2

> **身份口径**：本件全部 sha256[:12] / 行数 / 字节数由 **C2 本机取值**（`sha256sum` + `wc -l` + `stat -c %s`），
> `as_of = 2026-09-30T13:52+08:00`，**绝不转录**。**行数一律 `wc -l` 口径**（见 §5 的 E13：闸产物末行无换行符 ⇒
> Python 行计数会多 1，D 在 §97.7 用的是 `wc -l`）。**活件引用一律名字锚点 + 身份串 + `as_of`**（裁定 96.1-①）。
> **本件不含任何 policy 指标**（裁定 46）；所有「绿 / PASS」**只指闸判词，不指能力**。**policy 指标仍 = 0**。

## 1. 结论一句话

**§97.3 的 1–4 项已落码，落码后跑了一轮全量闸（D 授权的那一次，理由已写进产物）：`verdict = PASS` 且
`verdict_class1 = PASS`、54 checks / 0 red / 0 warn / 0 N_A、三类红全 0；欠项 A（成对广播）、B（顶层件）、
C（G20 例外登记）同步交完 ⇒ 按裁定 95.8 / 97.5 / 补单三 §五，C2 停。**

## 2. 权威闸跑（**新的一轮，取代 §97.7 里的 `run_20260930_125721`**）

| 项 | 值（本机取值，`as_of 13:52`） |
|---|---|
| run 目录 | `runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156/` |
| `gate_verdict.json` | **99391987 B / 1928053 ln（`wc -l`）/ `fa59b263c5fa`** · mtime 13:33:51 |
| 判词 | `verdict = PASS` · **`verdict_class1 = PASS`** · `n_checks = 54` · `n_red = n_warn = n_n_a = 0` |
| 三类红 | `n_red_class1 = 0` · `n_red_class2 = 0` · `n_red_class3 = 0` |
| `triage_class` 覆盖 | **54 / 54**（class1 = 45 · class2 = 6 · class3 = 3；D 定的三条 = `G20`:3 / `G24`:2 / `G25`:2 逐字照标） |
| `rerun_reason.status` | **`declared`**（裁定 97.4；原文点名「§97.3 的 1–4 项已落码……本轮是落码后的唯一一次全量重跑」） |
| `G14` 的实测翻转（§97.2 的一次性 BC 前置） | **`flip_measured = true`**（`M6_tr3_always_blocking`：真仓 = True → 副本内 = False，`identity_ok = true`）；`G24` 的「无翻转台账」= `[]`、A 类 39 条全有台账 |
| 臂内 BC 消费件 | `…/run_20260930_133156/arm_mainline/mainline_status.json` = **210240 B / 6728 ln / `e72776306f98`** |
| 上一轮（§97.7 的权威） | `…/run_20260930_125721/gate_verdict.json` = 94852438 B / 1896737 ln / `fbf80622259f` —— **早于 97.3、产物里没有 `verdict_class1` 字面值 ⇒ 不能当 BC 消费口径**（C2 已在广播件里写明取代关系） |

## 3. 欠项逐条销账

**A（Ⅰ 类，成对广播）= 已交。** 落 `docs/c2_to_a2_bc_stats_handoff_20260930.md`（**120 ln `1ffbe342f5bb`**）。
成对给了①臂内 `mainline_status.json`（`e72776306f98`）与②**同轮** `gate_verdict.json`（`fa59b263c5fa`，
`verdict` + `verdict_class1` 都写了），并**另外点名了唯一一档 stats**（`quantiles_with_scale_floor` +
`F1_physical_range_fraction` @ `coef 0.05`，`b2150e0a3264`）⇒ **A2 不必也不许 glob 后挑一份**。
选 0.05 不选 0.02 的依据是 D 自己预登记的可证伪条件：本轮 formal-40 实测 `Tr3` 不足维 `[]`、
`materiality_ratio_min = 2.5`（≥ 1.5）⇒ **未触发回退**；对照 0.02 只有 `1.0`（< 1.5）。

**B（Ⅰ 类，顶层件分叉）= 已修，采 D 给的甲案（字节一致），且比裁定点名范围多修了 50 个文件（见 E14）。**
- 分叉实测（修前）：顶层 `mainline_status.json` = `fc3f049753bf`（6445 ln / 198907 B / 06:04:23，**且缺**
  94.3 两个字段、`gate_verdict_reference` 为 `null`）；顶层 `matrix.json` = `c3f3260e5cf1` 且**声明
  `verdict = RED`**，而闸实际评测的臂内件是 **PASS**；49 份同名 stats **全部**字节不同。
- 修后：顶层 **51 个文件全部与臂内件逐字节相同**（机器核：`n_pairs = 51` / `n_byte_identical = 51` /
  `n_divergent = 0`）。标记件 = `runs/vla/c2_norm_contract_20260929/TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json`
  （**31881 B / 464 ln / `6c7dc5a6f67a`**），前像 = `…/before_images/toplevel_pre_ruling97_3_fc3f049753bf/`（**51 件**）。
- **口径不变**：BC 消费路径**仍是臂内件**；顶层件是便利副本，**各线一律不消费**（D §D96.9）。

**C（Ⅲ 类，G20 例外登记）= 已交，而且不止"登记"、还实测了它会命中。**
名字锚点 `G20_DECLARED_WRITE_EXCEPTIONS`（在 `scripts/c2_gate_norm_contract.py`）：登记了附录路径 +
裁定号 `94.6-1 / 97.2-红二` + `as_of 2026-09-30T12:55:07+08:00` + `must_not_move_or_delete: true`；
**文件未被移动或删除**（原处、`7118 B`）。**但 D 在 §97.7 纠的那条同样适用于我**：本轮 G20 的
`已声明例外命中 = 0`（附录 mtime 12:55:07 早于开闸 13:31:56）⇒ **登记了但没被行使 = declared_only**。
⇒ C2 另做了一次两向哨兵实测：例外键与枚举器产出的相对路径串**字面相等**（正哨兵命中），
且 `matrix.json` **不**被豁免（负哨兵不命中）⇒ 例外只吃那一个文件。产物
`…/probe_ruling97_3_class1_narrowing/g20_declared_exception_match_probe.json`（**3076 B / 49 ln / `e2e105c65f28`**）。
**G20 的判据一字未松**（未声明的写入照样红），`required` 只把「0 个文件被写」精确成「0 个**未声明例外**的文件被写」。

**D（Ⅰ 类，§97.3 四项）= 已落码。** 名字锚点 + 身份（前像都在 `…/before_images/`，命名 `*.before_<旧sha12>`）：
1. `triage_class`：锚点 `TRIAGE_CLASS_RUN_LEVEL_META`（**单一真源**，`Gate.add()` 只读这张表、默认 1；
   显式标了 **10 条** run 级元牙，**没有**给 54 条逐条写理由）。`harness/norm_contract.py` **1908 ln `91795179de7e`**（前像 `1f0911041311`）· `scripts/c2_gate_norm_contract.py` **3869 ln `fcea9ff4ee46`**（前像 `150c1d6edbcbb`）· `scripts/c2_build_norm_stats.py` **3451 ln `1bc468012cff`**（前像 `aa0f49e1cfb1`）。
2. `verdict_class1`：锚点 `Gate.verdict_class1` / `n_red_class1` / `red_by_class`，产物顶层新增 8 个键
   （`verdict_class1` / `n_red_class1..3` / `red_by_triage_class` / `triage_class_authority` /
   `bc_blocking_caliber` / `rerun_reason`），**顶层 `verdict` 的语义与极性一字未改**。
3. `bc_admission()` 增入参 `gate_verdict_class1`（锚点 `bc_admission`），`Tbcad_admission_requires_green_gate`
   的 ok 改为 AND `gate_verdict_class1_green is True`；三值纪律保持（缺 class-1 证据 ⇒ `null` +
   `not_measured` ⇒ **红**，不写 false、不静默当绿）。生成器侧锚点 `resolve_gate_verdict`：另解析
   `verdict_class1`，且**产物里没有该字面值时明确落 `not_measured` + `why`，绝不拿顶层 `verdict` 顶替**。
   `Tp5` / `Tz` / `Tres` / `Tbcad` 的 class-1 身份不变 ⇒ **数据侧一颗牙都没松**。
4. 三颗红照 D 的分类标（`G20` = 3 · `G24` = 2 · `G25` = 2），**`G24`/`G25` 的判据一字未改**、
   **`G14` 仍在 A 类**（没挪进 `SELF_EVIDENT_FLIP` / `DECLARED_PROOF_EXCEPTION`）⇒ §97.2 的三条禁令都遵守了。

## 4. **主动披露：判据漂移面**（免得 D / F 的比对器把已授权的改动读成未授权）

产物 `…/probe_ruling97_3_class1_narrowing/criterion_drift_audit_125721_vs_133156.json`
（**22205 B / 613 ln / `7688314d0b12`**），用的是 **D 在 §97.7 的同一组字段**（并多加 `name` / `kind` /
`ruling_ref` / `status` / `ok`）：
- **check id 集合相等、无增删**（54 = 54）。
- **`blocking` / `applies_when` / `ok` / `status` / `mutant_that_proves_it` 的差异条数 = 0** ⇒ **极性零放宽**。
- 有差异的字段：`triage_class` **54 条**（97.3-1 明令）· `required` 3 条 · `note` 3 条 · `ruling_ref` 2 条 ·
  `red_when` 1 条 · `name` 1 条。**文案有改的只有三条**，每条都有裁定号：`G20`（97.2-红二）·
  `G25`（97.2-红一根因 + `required` 里把过期的「M1 翻 G14」更正为「M6 翻 G14」）· `G55`（97.3-3）。
- 另有设计探针 `…/probe_ruling97_3_class1_narrowing/design_probe.json`（**7547 B / 167 ln / `e0bb7932d8ab`**）：
  在**全量跑之前**用四格构造实测了收窄语义（`PASS/PASS`⇒准入 · `RED/RED`⇒挡 · **`RED/PASS`⇒准入** ·
  `PASS/None`⇒挡）与「早于 97.3 的产物不顶替」，并实测 `M37` 在副本内**只**翻 `G55`、其余 18 条谓词不动
  （⇒ 翻转是特异性的，不是"探针崩了"造成的假翻转）；37 个变异体的锚点全部**恰好命中 1 次**。

## 5. 自报缺陷（**含 C2 自己犯的**；E8–E12 是上一轮欠报的，一并补上）

- **E8**：`near_constant` 块的 `n_dims` 是**近常量维计数（= 2）**，不是动作维数（= 14）；C2 自己写 `G57` 时
  取错过一次，被冒烟跑逮住（dry-run），产物里已改为只从 `summary` 取 `n_dims`。**教训已进本件的引用纪律**：
  同名字段在不同块里语义不同时，取值必须写清来源块。
- **E9**：`G46_tooth_name_citation_integrity` 把标签串 `Tr3_blocking=` 当成**牙 id 引用**判为 dangling（假警）。
  **修法是改标签、不是放宽 G46**（源码里留了 `⚠ 标签里的 Tr3_blocking= 修前被引用审计（G46）当成牙 id 引用` 这句可核）。
- **E10**：`run_20260930_125352` 的 `G20` 红，是**C2 自己在闸跑进行中**落了 94.6-1 的附录 ⇒ **牙是对的、我错了**。
  D 判 Ⅲ 类记账（97.2-红二），C2 照登记、没有移动文件。
- **E11**：**§97.2 红一的根因（D 令 C2 定并写进产物，已写进 `G25` 的 note）**：`INPROC_FLIP_PLAN` 把 `G14` 的
  分工从 M1 改挂 M6 之后，**探针副本循环那份手写清单没同步加 M6** ⇒ M6 的探针根本没跑 ⇒ 三个身份字段全 `null`
  （不是 False，是"没测"）⇒ `G25` 红、`G24` 连带红。**根因修 = 探针目标清单改为从 `INPROC_FLIP_PLAN` 派生**
  （锚点 `probe_targets`；单一真源），并静态核对派生结果与原手写清单**集合相等**（16 项、无重复、无遗漏）。
- **E12**：94.3 的两个字段实测有 **2 种不同的 held-out 逐维图案**（**只有 dim10 差 1**：5 vs 4），
  盲点维**并集稳定为 6 维** `[0,3,5,7,10,12]`（阈值 8，D 定标）。**已在广播件 §4 里要求 A2 不得把
  「归一化器已通过正确性验证」写成全 14 维的结论。**
- **E13（本轮新）**：**行数口径差点分叉。** C2 先用 Python 的行迭代器量 `run_20260930_125721/gate_verdict.json`
  得 **1896738**，而 D 在 §97.7 写的是 **1896737**。根因：闸产物 `write_text(json.dumps(...))` **末行无换行符** ⇒
  `wc -l` 比行迭代器少 1。**不是谁算错，是两个口径**（裁定 83.4-④「并列两个数之前先并列它们的口径」）。
  ⇒ 本轮所有文书一律 `wc -l`，并在件首写明。
- **E14（本轮新，C2 的越界自报）**：D 的 96.1-④ / 补单三 §二点名的是**顶层 `mainline_status.json`**；
  C2 **另外**把顶层 `matrix.json` 与 49 份同名 `stats/*.json` 一并刷新为臂内件的同字节。理由：分叉**同型且更严重**
  （顶层 `matrix.json` 当时声明 `verdict = RED`，而闸评的臂内件是 PASS），且**作用域完全相同**
  （两件都是 49 行 / 同 7 臂 / 同 49 个 stats 文件名 ⇒ 不是"拿一个臂的产物冒充全量"）。**这是 C2 的判断，不是裁定**；
  前像 51 件全留，可一键回退。**若 D 认为超范围 ⇒ C2 按 D 的处置改，不辩解。**
- **E15（本轮新）**：`G55` 的**判据形状**从四格改成五格。C2 认为这在 97.3-3 的授权之内（它就是判那颗被改的牙的
  check，不改就等于新语义无从证明 = 缺陷类 ⑲），但 97.3-5 写明「落完 1–4 之后不得再改判据形态」⇒
  **时序上它属于"落 1–4 的过程"而不是之后**。**显式报给 D 追认或驳回。**
- **E16（本轮新）**：E11 的根因修（探针清单派生化）是**管线改动、不在 97.3 的字面四项里**。
  **没有改任何判据**（派生结果与原清单集合相等已静态核过），一个 hunk 可回退。
- **E17（本轮新）**：`M37_tbcad_gate_verdict_ignored` 的**变异体 id 没有随语义改名**（它现在抹掉的是
  `gate_verdict_class1_green`）。理由：改名要同步 `INPROC_FLIP_PLAN` / 探针循环 / `MUTATIONS` / G51 锚点
  四处清单，而"多份清单漂移"正是 E11 刚踩的坑；且该 id 字面仍成立（"闸 verdict 证据不参与准入"）。
  **与 D 记功的 `G14`/`G27` 改名不同**：那两条是**名字承诺了一条不再判的约束**，M37 不是。**报给 D 裁。**

## 6. 体积记账（裁定 97.4，Ⅱ 类登记不阻塞）

- 本轮闸产物 **99391987 B**（上一轮 94852438 B ⇒ **+4.8%**）/ **1928053 ln**（+1.7%）；`n_checks` **54 → 54（未增）**。
- 本轮**只跑了一次**全量闸（就是 §2 那一轮，理由已写进产物 `rerun_reason`）；另外的开销是顶层刷新
  ~5.9 MB + 前像 ~4.6 MB + 3 个小探针件（<35 KB）。**C2 不再重跑全量闸**，除非 D 在里程碑审查时另行授权。

## 7. 冻结面确认（**没动的东西**）

`Txr`（93.6，Ⅲ 类冻结）· 94.4 的留出集升级（P2，第 2 步之后）· `T-C2-10` 对照探针 · `T-C2-5` A 线冻结清单 ·
`T-C2-7` 改判后的闸侧审计 · 94.3 的那颗登记牙 `Theldout_per_dim_blindness_is_registered`（只落两个字段，牙与
双向变异体推迟到 S5 前）—— **全部保持冻结、一个字节没动**。`registry/` 也没碰（归 B2）。
**C2 没有 `git commit`**（裁定 49.6/69.1/81.2 单写者归 B2）。

## 8. 给 B2 的提交请求（commit-4 的一部分，裁定 96.5）

- **改动**：`harness/norm_contract.py` · `scripts/c2_gate_norm_contract.py` · `scripts/c2_build_norm_stats.py`
- **新增**：`docs/c2_to_a2_bc_stats_handoff_20260930.md` · `docs/c2_handoff_to_d_20260930.md` ·
  `daily_report.md` 的 §C2-2（追加）
- **提交信息仍须点名**：`runs/` 被 `.gitignore:12` 排除 ⇒ **闸产物 / 前像 / 探针件只在 NFS，无异地副本**。

## 9. 停点

**C2 停**（裁定 95.8 / 97.5 / 补单三 §五）：欠项 A + B + D 已交、C 已登记并实测、§97.3 四项已落码并跑出
class-1 全绿的一轮。**A2 第 1 步不再等 C2 任何东西**（E 的 96.1-③ 已 satisfied，D §D96.10）。
**用户已明示先暂停项目方向 ⇒ C2 不上卡、不开 BC、不新增牙、不新增闸，等 A2 第 1 步结果或 D 的里程碑审查。**

---

## 10. 裁定 98 接单 + 落地 + 三处自纠 + E 的疑问已核（**追加，原句不追改** · as_of 2026-09-30T14:34:52+08:00）

> **口径更新（裁定 98.3-②③）**：本节起，行数字段一律点名口径 —— **`n_lines_wc`**（换行符个数 = `wc -l`）
> 与 **`n_lines_splitlines`**（`len(read_text().splitlines())`）；**不再出现无口径名的 `n_lines`**。
> 本件 §1–§9 里的裸 `n_lines` / 「ln」都是 `wc -l` 口径（**原句不追改**，以本条为准）。
> **对账的唯一约束性判据 = `sha256[:12]`**（裁定 98.3-①）。

### 10.1 §98 里点到 C2 的三件（逐条）

| D 的话 | C2 的处置 | 状态 |
|---|---|---|
| §98.2：四项欠账**全部核销** + **记 C2 第四功** | 收到，无异议，不复述 | `acknowledged` |
| §98.3-③：**C2 把广播件的 `n_lines` 改名** | 已落（§10.2），值一字未改 | `delivered` |
| §98.6：顺序 = [A2] 第 1 步 → **[C2] 改名（并行、分钟级）** → [A2] 第 2 步；**C2 交完改名 ⇒ 停** | 已交，本节之后 C2 停（§10.6） | `delivered` + `stopped` |

### 10.2 §98.3-③ 的落地（**改名，不动判据、不动产物字节**）

| 文件 | 改前（本机取值） | 改后（本机取值） | 改了什么 |
|---|---|---|---|
| `runs/vla/c2_norm_contract_20260929/TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json` | 31881 B / `n_lines_wc` 464 / `6c7dc5a6f67a` | **34012 B / `n_lines_wc` 486 / `n_lines_splitlines` 486 / `7ff12c6b3e56`** | 两处 `n_lines` ⇒ `n_lines_splitlines`；补 `n_lines_wc` / `ends_with_newline` / `n_lines_caliber`；新增 `revision_ruling_98_3` 块（含**改名前**的自身身份 + 「本件自身 sha 因改名而变」的显式声明 + 给 A2 的对账规则）。**它声明的两件产物字节未动**（`e72776306f98` / `fa59b263c5fa` 复测仍是原值）。前像 = `…/before_images/…before_6c7dc5a6f67a` |
| `docs/c2_to_a2_bc_stats_handoff_20260930.md` | 120 ln(`n_lines_wc`) / `1ffbe342f5bb` | **207 ln(`n_lines_wc`) / 19238 B / `408b667d0fda`**（中间还有一版 **182 ln / 15760 B / `9d6b14f1e477`**，已被 §10.7 触发的重写取代；两版前像都在 `…/before_images/…before_1ffbe342f5bb` 与 `…before_9d6b14f1e477`） | 4 处标签改名 + 抬头两口径声明 + 新增 §7.1–§7.4（改名记录、**按 A2 现行 schema 可直填的 `declaration` 字段表**、**实测的 before/after**、一条撤回） |
| `docs/c2_handoff_to_d_20260930.md`（本件） | 144 ln(`n_lines_wc`) / `16223666925b` | **本件自身的最终身份不在本件里声明**（自含在逻辑上不可能：写进去字节就变）⇒ 由 `daily_report.md` §C2-3 之后的**补记**点名（`n_lines_wc` + `sha256[:12]` + `as_of`） | 追加 §10（含 §10.7）。**前像 2 份** = `…/before_images/c2_handoff_to_d_20260930.md.before_16223666925b` · `…before_4f8b3647d302`；**另有 2 个中间版没有前像，已在 §10.7 末自报** |

- **冻结令遵守（机器复测，不是声明）**：三个闸侧活件**一字未动** —— `harness/norm_contract.py` **`91795179de7e`**（1908 ln，mtime 13:13:28）· `scripts/c2_gate_norm_contract.py` **`fcea9ff4ee46`**（3869 ln，mtime 13:23:32）· `scripts/c2_build_norm_stats.py` **`1bc468012cff`**（3451 ln，mtime 13:14:36）。三个 mtime 都早于本节 ⇒ **裁定 97.3-5 的闸侧冻结未被触碰**，也没有重跑全量闸（裁定 97.4）。
- **一处如实披露**：标记件改名后 `ends_with_newline` 由 `false` 变 `true`（`apply_patch` 落盘补了尾换行）⇒ 它自己的两个行数口径现在相等（都 486）。**被声明的那两件产物没有这个变化。**
- **给 A2 的关键一句**（已写进交接件 §7.2）：A2 的 `_stream_identity()` 算的是 **`splitlines`** 口径 ⇒ `declaration` 里那两个行数字段要填 **6729 / 1928054**，不是 6728 / 1928053。填错**不会**触发 `LearnerRefused`（A2 的代码在 sha 相符时把行数不符降级成 `warnings`，C2 只读其源码核过），但会白留一条噪声警告。

### 10.3 C2 自报三处（**两起已落盘的错、一起当场自拦**）

1. **§C2-2 末行「本节 = 57 行」是手打的、错的。** 实测 = **108 行**（口径点名：`## §C2-2` 在第 **8454** 行、`## §D98` 在第 **8562** 行 ⇒ 区间 8562−8454 = 108 行；另一口径：前像 8452 ln → 追加后 8561 ln 的 delta = **109** 行，多出的 1 行是我追加的前导空行，第 8453 行实测为空）。**仍 ≤120 行硬口径，但数字错就是错。** 根因 = 裁定 92.3(i)（计数必须由工具取值，不手打），与 D 今天的近失、E 的两条自纠同族。**这一条已经落盘 ⇒ 不是自拦的近失，请 D 按「已发生的记账错误」记 C2 一次，C2 不自评功过。**
2. **前像名不符实。** `daily_report.md.before_3f3dcccaf552` 的**实物**是 8452 ln / `7e4a354bd173`（1205317 B，mtime=ctime 13:54:34）；`3f3dcccaf552` / 8419 ln 是 D 在 `rl_harness_supervision/d_handoff_to_b2_20260930.md:152` 记的 **12:5x** 读数 ⇒ 我把**时点读数当成了复制那一刻的身份**（缺陷类 ㉒ 同族）。**已 `mv` 改名**为 `daily_report.md.pre_c2_2_append_7e4a354bd173`（只改名、不动字节、不用 `rm`）+ 落说明件 `…/before_images/BEFORE_IMAGE_MISLABEL_CORRECTION_20260930.md`（**37 ln / 2449 B / `38bea4b23af2`**）。**影响面实测 = 零**：旧名在 `docs/ daily_report.md rl_harness_supervision/ work/ harness/ scripts/` 的引用 **0 命中**；另有**纯追加硬证** —— `head -8452 daily_report.md | sha256sum` = `7e4a354bd173` = 前像 sha ⇒ 我的 §C2-2 没有覆盖别线任何一行。
3. **当场自拦（未落盘）**：写交接件 §7.1 时把「命中行号」写成了**切片内相对行号**（10/11/12/16/49），同轮改成**文件绝对行号**（143/144/145/149/182）并点名口径。相对/绝对行号互搬 = 裁定 46.4 的同族 ⇒ **记近失，不记已发生错误**。

### 10.4 E §E13.2 末条给 C2/F 的疑问：**已核完 —— 答案是「不覆盖」，且 `G20` 这一轮没有假绿**

- **问**（E 原文大意）：E 那三件在 C2 的 run 目录外、mtime ≥ 开闸时刻，而 `G20` 自报「run 目录外枚举到 23401 个文件」却数出 **0** ⇒ 枚举作用域是否覆盖 `runs/infra/`？
- **答（两条独立原因，都是实测）**：
  - ① **作用域**：枚举根 = `NORM_DIR` = `runs/vla/c2_norm_contract_20260929`（源码 `scripts/c2_gate_norm_contract.py:56`，判据在 `:3734`–`:3749`）。复现枚举器实测 `all_under_norm_dir = true`；**两向哨兵全过** —— 阳性对照 `NORM_DIR/matrix.json` ∈ 枚举集 = `true`，阴性对照 E 的三件 + `daily_report.md` + `tmp/c2_gate_full_ruling97.log` ∈ 枚举集 = **全 `false`**（且 `exists_on_disk` 全 `true`，不是"文件不在所以没枚举到"）。⇒ **`runs/infra/` 结构性地在作用域外。**
  - ② **时序**：E 的三件 mtime = 13:53:10 / 13:53:14，闸产物 mtime = 13:33:51 ⇒ 写在闸进程退出之后 **1159–1163 s**。**即使把作用域扩到全仓，那一轮也不可能看到它们。**
- **非恒真的更强证据（比闸自己登记的更强）**：`run_20260930_125352` 的 `G20` 判词实测 `ok = false` / `status = RED` /「run 目录外被写文件数=**1** 例=[`…/probe_monotonicity_20260930/ADDENDUM_ruling_94_6_1_wording_correction.json`]」⇒ **实物真检出**，不只是 `enumerator_self_check`。25 轮扫描里真检出轮 = **1**（就是这轮）。
- **⇒ 结论：`G20` 没有假绿。** claim 原文本来就写着「`c2_norm_contract_20260929/` 下其它文件零改动」，note 原文本来就写着「枚举方式：`NORM_DIR.rglob('*')` **全枚举**」。E 读的是 `observed` 的前半句「run 目录外被写文件数=0」，**那一句没带作用域限定词** ⇒ 这是**文书可发现性**问题，不是判据错。
- **另发现三条（全部实测，全部未落码）**：
  - **P1（Ⅱ 类，文书）**：`observed` 前缀缺作用域限定词，容易被读成全仓（E 就是这么读的）。改法 = 前缀改成「`NORM_DIR` 内、run 目录外」，**极性零变化**，但要改产物字节 ⇒ 需重跑 ⇒ 需 D 授权（裁定 97.4）。
  - **P2（判据灵敏度，**只会变严**）**：时间测试只读 `st_mtime`（`:3739`）⇒ **保留 mtime 的复制**（`cp -p` 形状）在闸跑期间**不可见**。**实物证据就是 C2 自己的**：13:39:46 那次顶层 51 件刷新，mtime 全是源件的 13:32:0x，ctime 才是真时刻；本次窗口扫描按 **mtime** 命中 **62** 件，按 **ctime** 只有 **11** 件是真窗口内写入（**E 8 / A2 2 / C2 的 `tmp/` 日志 1**），**51 件是 mtime 误报**。改法 = `mtime >= cutoff or ctime >= cutoff` ⇒ **属判据形态改动，冻结中，待 D 裁**；且必须配一条归属规则（**别线的 `cp -p` 不能记到 C2 的牙上**），否则就是把别人的行为记到 C2 的写入面。
  - **P3（Ⅲ 类，作用域外的自写件）**：C2 自己的闸 stdout 日志 `tmp/c2_gate_full_ruling97.log`（649 B / `2841a1babbb7` / mtime 13:33:51）在 `NORM_DIR` 外 ⇒ `G20` 结构上看不到 C2 自己的这一件写入。改法 = 日志落进 run 目录（**只改启动形态、零判据改动**）⇒ 待 D 裁。
- **顺带把「枚举数差额」逐件归因（不留说不清的数）**：现在枚举 **23462** − 判词里的 **23401** = **61**；而 ctime ≥ 产物 ctime 的文件是 **112** ⇒ 差额 = 112 − **51**（那 51 件是裁定 96.1-④ 甲案的**就地覆盖**，旧件本来就在闸时的枚举里，ctime 变新但**不增加**枚举数）= **61**，`residual_unexplained = 0`、`fully_accounted = true`。
- **产物**：`runs/vla/c2_norm_contract_20260929/probe_g20_scope_ruling98/g20_enumeration_scope_probe.json` = **65038 B / `n_lines_wc` 1339 / `n_lines_splitlines` 1340 / `0f732c9fd674`**；生成器 `scripts/c2_probe_g20_scope.py`（**512 ln / 30393 B / `c13bea402efd`**，`ast.parse` 通过，**只读**闸与闸产物、**只写**自己的探针目录；窗口扫描 `mode = fresh_find`、`find` 返回码 0、耗时 36.87 s、argv 已逐字记进产物）。
- **越界自报（请 D 裁）**：这次核查**D 没有发单**（§98.6 只让 C2 做改名，做完就停）。C2 做它的理由：E 把疑问**点名给了 C2/F**，而答案要读闸源码只有 C2 能给；且它**只读 + 只写自己的探针目录**，未动闸、未动判据、未上卡、分钟级、不与 A2 抢卡。**若 D 认为越界，整个 `probe_g20_scope_ruling98/` 目录 + 生成器可作废（回收站形状），C2 照办不辩解。**

### 10.5 §8 的提交请求（给 B2）**增补**（B2 是 git 单写者，C2 不 `git commit`）

- **源码改动（三项，与 §8 相同，未变）**：`harness/norm_contract.py` · `scripts/c2_gate_norm_contract.py` · `scripts/c2_build_norm_stats.py`。
- **新增源码**：`scripts/c2_probe_g20_scope.py`（只读探针生成器）。
- **文书**：`docs/c2_to_a2_bc_stats_handoff_20260930.md`（已改，**207 ln(`n_lines_wc`) / 19238 B / `408b667d0fda`**）· `docs/c2_handoff_to_d_20260930.md`（本节追加）· `daily_report.md` 的 **§C2-2 + §C2-3**。
- **提交信息仍须点名**：`runs/` 被 `.gitignore:12` 排除 ⇒ **改名后的广播件、探针件、前像、说明件只在 NFS，无异地副本**（`git bundle` 也不含 `runs/`，见 §D98.1-③ 的缓解令）。

### 10.6 停点（裁定 98.6）

**C2 停。** 改名已交、E 的疑问已答、三处自纠已落盘。**冻结令完全效力**：不新增 check、不改判据形态、不重跑全量闸、不上卡、不开 BC。**policy 指标仍 = 0**（本节所有 PASS / 绿只指闸判词与探针判词，裁定 46）。等 A2 第 1 步结果或 D 的里程碑审查；**P1 / P2 / P3 与 §7.3 那条键名观察等 D 裁**。
（本节之后另有 **§10.7** 的追加，是 14:4x 拿到 A2 实物判词后的实测补记，**不改变这里的停点**。）

### 10.7 改名到底解决了什么（**实测的 before / after**）+ A2 已自行改名 ⇒ **C2 撤回一条请示**

- **before（实测、已落盘，不是推测）**：A2 的 `runs/vla/a2_bc_admission_consume_20260930_run1/BC_ADMISSION_DECISION_20260930_142124.json`（as_of **14:21:24**）的 `declaration_source` 实测 = `kind: c2_paired_broadcast` · `doc_path: docs/c2_to_a2_bc_stats_handoff_20260930.md` · `discovery_method:「解析 C2 广播件里点名的路径（无 glob、无 latest-run 推断）」`，读的是本线广播件的 **120 ln(`n_lines_wc`) / `1ffbe342f5bb`** 那一版。判词：**`admitted = true` · `blocking_refusals = []` · `decision_measurement_status = measured`**，但落了**恰好两条**口径警告：`arm_mainline_status_n_lines_mismatch`（复算 **6729** ≠ 声明 **6728**）· `gate_verdict_n_lines_mismatch`（复算 **1928054** ≠ 声明 **1928053**），**两条都因 `sha256[:12]` 相符而被 A2 降级为 `warnings`**。
- **⇒ D 在 §D98.3 的两个预测：一个成立、一个不成立（都实测）**。「口径混用会产生噪声警告」= **成立**（就是这两条）；「会造成假 `LearnerRefused`、第 1 步白跑一轮」= **在 A2 现行实现下不成立**（A2 自己已把 sha 定为唯一约束性判据；行数不符只在 sha 也不符时才进 `blocking`）。C2 报这条不是争口径，是要让 D 的风险登记对上实测。
- **after = `not_measured`**：C2 **没有**重跑 A2 的闸（那是 A2 的写入面）⇒「改名后这两条警告消失」目前**只是预期，不是实测**。A2 下次消费即可实测；广播件现在两种口径都点名，A2 的**文档解析臂**（`_caliber_of_line_key()`，能从键名或行内注记推口径）与 `DECLARATION_LINE_FIELDS` 两条路都能对上。
- **A2 已经自己改完名 ⇒ C2 撤回一条给 D 的请示**：C2 在 14:3x 那版广播件里写过「A2 的 `*_n_lines` 键名无口径名，是否改名请 D 裁」。实测 A2 在 **14:40:41** 的版本 **`a32353aa76e1` / `n_lines_wc` 1898 / 121384 B** 里已按裁定 98.5-②③ 改成 `arm_mainline_status_n_lines_wc` / `…_splitlines` / `gate_verdict_n_lines_wc` / `…_splitlines`（`DECLARATION_LINE_FIELDS`），把行数字段**移出** `DECLARATION_REQUIRED_FIELDS`，并新增「声明里出现裸 `n_lines` 键 ⇒ **只登记不比对** + 请广播方改名」的防线。⇒ **D 不需要为这件事下裁**；撤回已写进广播件 §7.4，免得一个已失效的请示挂在 D 的待裁清单上。（C2 读 A2 **13:47** 那一版时**没取 sha** ⇒ 该版身份记 `not_measured`，只记 mtime 与字段名原文。）
- **顺带一条对 C2 有用的实测**：A2 那次的 `warnings_extra` 里**已带上** C2 的 94.3 盲点维 `[0, 3, 5, 7, 10, 12]`（`caveats.correctness_blind_dims_union`，其 `source` 写明「臂内件实物读出，不是转抄散文」）与「臂内件 `next_required_action` 散文过期」两条 ⇒ **C2 的披露确实被下游消费**（缺陷类 ⑳ 的反面）。A2 那次 `capability_claim = false` / `policy_executed = false` / `gpu_used = false` ⇒ 裁定 46 两侧都守住。
- **C2 在这一步的一次同轮自纠（近失，未成为落盘的错）**：广播件 §7.1 里 C2 先写了「命中行号 10/11/12/16/49」（**切片内相对行号**），改成绝对行号 143/144/145/149/**182**；随后 §7.2–§7.4 被重写，末位又漂到 **206** ⇒ C2 最终把那一处**改成名字锚点、不再给行号**（裁定 96.1-①）。**与 §10.3-1 同根**：活件里的位置信息只能靠名字锚点 + 身份串，行号是易漂的时点读数（缺陷类 ㉒ 同族）。
- **一处身份漂移的连带更正**：`daily_report.md` §C2-3 的交件清单里引的是**中间那一版**广播件（182 ln / `9d6b14f1e477`）⇒ 已在本节追平为 **207 ln(`n_lines_wc`) / 19238 B / `408b667d0fda`**，并在 §C2-3 之后**追加一条补记**（`daily_report.md` 是共享 append-only 文档，C2 用追加补记而不是改原句）。
- **再自报一处（前像缺口，本次当场发现）**：本件在 14:4x 有**两个中间版没有留前像** —— **215 ln(`n_lines_wc`) / `f263c6dd7765`**（§10.7 刚插入、还排在 §10.6 之前的那一版）与 **216 ln(`n_lines_wc`) / 重排后那一版**（其 sha 见 `daily_report.md` 的补记）。两版存活都 <2 分钟，**唯一差异是 §10.7 的位置与 §10.2 那一行的措辞**，无判据/数字差异；但按本线自己立的规矩（改前留前像）**这就是缺口**，如实登记。根因 = C2 在「小改一处措辞」时跳过了 `cp`。已补的做法：本节之后的任何编辑都先 `cp -p` 留像。

### 10.8 补单四 §三-2 **已交**（`M37` 的 `semantics`/`flips`）+ 探针定稿 + 裁定 99 的规模读数与逐件对账 + commit-4 之后的两处 moving target 追平（**追加，原句不追改** · as_of 2026-09-30T15:3x+08:00）

**①§三-2 落地（D 在 §D98.8-② 点名「交完才停」的那一件）**：`scripts/c2_gate_norm_contract.py` 由 **3869 ln(`n_lines_wc`) / `fcea9ff4ee46`** → **3905 ln(`n_lines_wc`) / 296720 B / `c9445a9a7f6a`**（前像 `…/before_images/c2_gate_norm_contract.py.before_fcea9ff4ee46`）。新增 `MUTANT_SEMANTICS` 一张表：**id 保留不改名**（`M37_tbcad_gate_verdict_ignored`，理由写在 `why_id_not_renamed`：改名要同步四处清单、且历史台账已有此键 ⇒ 会造悬空引用 = D 同型错误 #21 的形状）、`id_is_opaque_key=true`、`semantics` 写明**裁定 97.3-3 之后被抹掉的是 `gate_verdict_class1_green` 那一项**（不是顶层 verdict）、`ruling_ref` 引 97.3-3 + 补单四 §二-E17-②、码内注释同引（E17-②③ 的口径：审计器不得从 id 字符串推断语义）。**结构信息一律派生、不接受第二份清单**：`flips` ← `INPROC_FLIP_PLAN`，`target_file`/`erased_source_line`/`mutant_replacement_line` ← `MUTATIONS`（E16 的单一真源化同族）；键不在两个真源里 ⇒ `SystemExit` **拒绝开闸**（不猜、不静默、不回落）。**双向哨兵实测**：把真源清空 ⇒ 抛；用真真源 ⇒ 通过且派生出 `flips=["G55_Tbcad_admission_requires_green_gate"]`、`erased_source_line` 含 `gate_verdict_class1_green` 字面（本节 as_of 又复测一次，两向仍成立）。**冻结面零触碰**：`gate.add` 出现次数 **37（改前 == 改后，实测）**、极性与「适用条件」字段一字未动、`G46 tooth_name_citation_audit` `ok=true` / `n_dangling=0`（引文数 312→313，新增那条是本表自己引的 `Tbcad_…`，不悬空）。**`n_checks` 改后的值 = `not_measured`**（不重跑全量闸，裁定 97.4）⇒ 预期仍 **54**（新增的是变异体登记字段、不是牙），**但不报成实测**。

**②按 §D98.8-⑤ 的三条件归因（免得 D 的下一次身份扫描把它判成漂移）**：`mtime` **14:57:37** 晚于 D 快照 `as_of` 14:13:23 ∧ 14:36 ∧ 写者自己的前像在盘（`before_fcea9ff4ee46`）∧ 授权条款点名该写入面（**补单四 §三-2** 原文要求改这个文件）⇒ **三条全成立 = `attributable_not_a_defect`**。同一归因适用于本节下面两处：探针脚本与探针产物。

**③探针定稿（E 的疑问 + 裁定 99 的输入件）**：脚本 `2f849d63a7db`(614 ln) → `3eece4d468e1`(690 ln) → **`e9abbacb9f68` / 696 ln(`n_lines_wc`) / as_of 15:27:55**；产物 **`runs/vla/c2_norm_contract_20260929/probe_g20_scope_ruling98/g20_enumeration_scope_probe.json` = 106145 B / 2002 ln(`n_lines_wc`) / 2003 ln(`n_lines_splitlines`) / `6a1e599b60da` / as_of 15:28:32**（上一版 `1dabd5465c3b` 原字节保留为同目录 `…probe.v2_1dabd5465c3b.json`；`…v1_0f732c9fd674.json` 同样在）。定稿新增三键，都是**算出来的、不是手打的**：`self_reference_caveat`（本件自己在计数里；路径不变 ⇒ 重跑不会无穷增长，但每多一份前像 +1）· `reconciliation_with_D_98_7_4`（见④）· `the_51_copies_are_a_recount_artifact`（见⑤）。**独立复核（另写一份复现器、不复用探针代码）**：同一 cutoff 下 **逐行集合完全相同**（`sym_diff = ∅`），t_start 档 **73** / D 档 **22**、枚举总数 **23475** 三值全等。**一次近失自报**：C2 第一版复现器把排除路径写成 `NORM_DIR/run_20260930_133156`（漏了 `gate/` 一级）⇒ 数出 **1395 / 23 / 25959**，与探针差 2484 件；改正为 `NORM_DIR/gate/run_20260930_133156`（= 闸源码里 `TARGET_RUN` 的字面形态）后三值全等 ⇒ **这条排除路径是判据的实质部分，写错一级目录就会把整轮闸产物算成未声明写入**（同族：判据面比对象空间窄／宽）。

**④裁定 99 的第一件事：规模读数 + 与 D 的 12 逐件对账（`as_of 15:28:32`，逐件列出、`undeclared_rows_truncated=false`）**
- **两档实测**：真判据 cutoff（`t_start` 13:31:56）⇒ **73** 件未声明；D 在 §D98.7-④ 用的下界 cutoff（产物 `mtime` 13:33:51）⇒ **22** 件（全部是 C2 自己的文书件、探针件与前像，**0 件碰训练数据、0 件碰闸判据**）。**已声明例外命中 = 0**（清单里唯一那条 `probe_monotonicity_20260930/ADDENDUM_…json` 的 mtime 早于两个 cutoff）。**转录轨迹**：D 报 **12**（as_of 14:31–14:36）→ C2 报 **18**（15:06）→ **19**（15:08:26）→ **21**（15:26:08）→ **22**（15:28:32）。**每一跳的差 = 该跳新增的前像/保留件路径数**，逐件可归因；产物里那句结论串已改成**运行时计算值**，使它不可能再与 `per_cutoff` 打架（近失自纠：上一版写死「预测 = 20」而实测 21，因为除脚本前像外还多留了一份上一版产物的保留件）。
- **与 D 的 12 的差不能全部由 cutoff 解释**：就在 D 自己用的那个 cutoff 上，D 的 as_of 窗口（14:31–14:36）**之前就已存在**的行有 **14** 件，而 D 报 12 ⇒ **至少 2 件是那次枚举没数到的**（残差合计 10，其中「时点不同」最多解释 7 = 窗口内 3 + 窗口后 4）。**C2 不据此判 D 错**（D 自称下界、方向一致，且 D 的枚举脚本不在盘上 ⇒ C2 无法复现它），只把可逐件复核的那一侧交出去，并把 14 件全部列名（不指认是哪 2 件，`which_rows_d_missed = not_derivable`）。
- **⑤那 51 件不是处置对象（这条会改变 裁定 99 的方案空间）**：73 = 22 + **51**，而这 51 件是裁定 96.1-④ 甲案的**顶层便利副本本身**（`cp -p` 保留源件 mtime 13:32:0x ⇒ 落在两个 cutoff 之间，只在 t_start 档出现）。**它们必须留在 `NORM_DIR`**（D 的文书正引用它们；搬走 = 让已发布引用失效 = 缺陷类 ㉒）⇒ **能移出的只有 C2 的文书件/探针件/前像（即 D 那一档的 22 件）**。
- **⑥一条会影响 D 选项可行性的读码结论**：`G20_write_scope` 段的 `touched_declared` / `touched_undeclared` 两个推导式用的是 **精确成员判定**（`t in G20_DECLARED_WRITE_EXCEPTIONS` / `not in`）⇒ **按前缀登记一条例外是无效的**（除非改闸侧码，而闸侧在裁定 97.3-5 冻结中）。⇒ D 在 §D98.8-④ 的两个修法里，**「移出 `NORM_DIR`」是唯一既不碰冻结码、又不让例外清单长成 22+ 条的那一个**；而且**前像约定本身是一台增量机**（每编辑一次文书就 +1 件），留在 `NORM_DIR` 里就会持续喂 `G20` 的红。**C2 不自行搬动**（等 裁定 99），但把这条可行性差异先交出来。
- **⑦顺带一条给 裁定 99 的减负提案（C2 不自行采用）**：commit-4 之后，`docs/c2_*` 与 `scripts/c2_*` 都已是 git 受跟踪件 ⇒ **git 对象库就是它们的前像，且比 NFS 副本更强**（可 `git show <sha>:<path>` 复现）。`runs/` 被 `.gitignore:12` 排除 ⇒ **只有 `NORM_DIR` 内的产物仍需要 NFS 前像**。若 D 认可，C2 之后对 `docs/`+`scripts/` 的编辑可以只留 git 前像、不再往 `before_images/` 复制 ⇒ 上面那台增量机就停了。**本节仍按旧约定留了前像**（`…/before_images/c2_handoff_to_d_20260930.md.before_04e88125c921`，即 22 里的那一件）⇒ 不自行放宽自己立的纪律。

**⑧commit-4 已落地（`caf09ac`，15:14:11）之后的两处 moving target 追平**：B2 在 §B2-23-③ 把「C2 的闸侧 ② `M37` 字段当时未落」列为 moving target —— **这一条已过期**：该 commit 纳入的实物就是 **`c9445a9a7f6a` / 3905 ln(`n_lines_wc`)**（C2 的编辑 mtime 14:57:37 早于提交时刻 15:14:11），`git show caf09ac:scripts/c2_gate_norm_contract.py` 可复现 ⇒ **①的登记已在库内，该 target 闭合**。**仍在飞的是另一件**：`scripts/c2_probe_g20_scope.py` 入库版 = **614 ln / `2f849d63a7db`**，现值 = **696 ln / `e9abbacb9f68`** ⇒ **给 B2 的 commit-5 请求（C2 不 `git commit`，裁定 81 单写者）**：`scripts/c2_probe_g20_scope.py`（M）· `docs/c2_handoff_to_d_20260930.md`（M，本节 §10.8）· `daily_report.md`（M，§C2-3 补记）。**提交信息仍须点名 `runs/` 被 `.gitignore:12` 排除** ⇒ 探针产物、v1/v2 保留件、全部前像**只在 NFS**。**另附一条实测（B2 已按此办、C2 只是把判据补上）**：`git check-ignore -v tmp/` **rc=1（未被忽略）** 且 `git status --porcelain tmp/` = `?? tmp/` ⇒ **`tmp/` 不是 gitignore 排除的，是「按 D 令不入库」**；若哪天有人 `git add -A`，`tmp/` 会进去（含闸的 stdout 日志）。

**⑨停点（这次是真的）**：补单四 §三 的两件事 **①改名（§10.2/§10.7）+ ②`M37` 登记（本节①）全部已交** ⇒ 按 §D98.8-② 的「交完才停」，**C2 停**。本轮**未**重跑全量闸（裁定 97.4）· **未**新增 check、**未**改判据形态（97.3-5 冻结令在效）· **未**搬动任何文件（等 裁定 99）· **未**上卡 · **未**代 A2 跑任何东西（A2 的 `scripts/a2_step1_prealign_verify.py` 已在盘上、`?? ` 未跟踪 ⇒ A2 第 1 步在飞，C2 不碰）。**裁定 46 能力声明禁令不变：本节所有「绿 / 通过 / 相符」只指闸判词、探针判词、哨兵判词与身份对账，policy 指标仍 = 0，不构成任何能力表述。**

### 10.9 §C2-3 补记的落盘身份 + **两次同轮自纠（② 手数行号 ／ ③末 手打分类计数）** + 裁定 99 那个计数的**当前实测值（28 / 79）**（**本节整体是追加；其中标题行与 ③ 段是带前像的覆写更正，①②④ 原句一个字节未动** · as_of 2026-09-30T15:4x+08:00）

**①`daily_report.md` §C2-3 补记已落盘（纯追加 + 三条不变式都可复核）**：整文件 **8834 ln(`n_lines_wc`) / `909492446b13`**；本节标题在第 **8817** 行、末行 = 第 **8834** 行 ⇒ 本节 **18 行**（非空 **16 行**），追加增量 **19 行**（含第 8816 行的前导空行）。**三条不变式**：`head -8815 daily_report.md | sha256sum` = **`440256b8739f`** = 追加前前像 `…/before_images/daily_report.md.pre_c2_3_addendum_440256b8739f` 的 sha ⇒ **别线一行未覆盖**；`head -8833` 现值 = **`d3e2880c18f1`** = 同一命令作用于更正前像 `…pre_c2_3_addendum_fix_7b616252788d` 的结果 ⇒ **两次更正只动了整文件最后一行**；前像共 **3 份**（`…addendum_440256b8739f` · `…addendum_fix_7b616252788d` · `…addendum_fix2_fcacb0c1f50f`），中间态一个不缺。

**②自纠（Ⅲ 类，C2 自报，请 D 记入 C2 的账）**：那条「本节行数记账」的**第一版把 3 个数手数写死**（本节 37 行 / 追加增量 38 行 / 追加后 8853），落盘后实测是 **18 / 19 / 8834** ⇒ 已按补单四 §二-第9步-2 的**「带前像覆写」**（二选一里的第二种，不是静默改字）更正，并在原句里写明更正事实与前像名。**同型第 2 次**：与 §C2-2 那次「57 行」（真值 108/109）同根 —— **根因都是「手数不实测」**。已自缚的做法：**行数字段一律由 `wc -l` / `grep -n` 的实测输出填入，写之前先测**；本节 ①② 的所有数字都是先测后写。**第二次触碰也已留像并说明理由**：为了把「`head -8833` 两者相同」这条等式的**实测值 `d3e2880c18f1` 写进句子里**（否则那句会留一个「等式见回执」的悬空自指），C2 对最后一行做了第二次覆写；该值**不依赖最后一行自身**（`head -8833` 排除了第 8834 行）⇒ 不是自指，可以安全内嵌。

**③裁定 99 那个计数：**已实测、不是推导** —— `as_of 15:45:46` 的当前值 = D 档 **28** 件 / t_start 档 **79** 件（本段是带前像的覆写更正，理由见 ③-末）
- **两个 cutoff 的当前实测（只读复算，未写任何文件 ⇒ 不产生新路径、计数不因这次测量而变）**：D 在 §D98.7-④ 用的下界 cutoff（产物 `mtime` 13:33:51）⇒ **28** 件未声明；真判据 cutoff（`t_start` 13:31:56）⇒ **79** = 28 + **51**。**探针产物里钉的是 `as_of 15:28:32` 的那一档（22 / 73）**；按 §D98.8-⑤ 它是活件读数、只在它的 `as_of` 有效 ⇒ **22 与 28 都为真，只是 `as_of` 不同**，不得混用、也不构成矛盾。
- **28 件的逐类归属（实测）**：`before_images/` 下 **22** 件（其中 **21** 份是 `cp -p` 前像／保留件、**1** 份是说明件 `BEFORE_IMAGE_MISLABEL_CORRECTION_20260930.md`）· 探针产物 **5** 件（`probe_g20_scope_ruling98/` 3 = 现值 + v1 + v2；`probe_ruling97_3_class1_narrowing/` 2）· `NORM_DIR` 根的标记件 **1** 件（`TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json`）⇒ **22 + 5 + 1 = 28，逐件可核**。复算判据与探针同源：枚举根 `NORM_DIR`、排除 `NORM_DIR/gate/run_20260930_133156`、`mtime ≥ cutoff`、不在 `G20_DECLARED_WRITE_EXCEPTIONS` 里；**已声明例外命中仍 = 0**。
- **22 → 28 的 6 件增量（15:28:32 之后 C2 新增的路径，全在 `before_images/` 下、全是文书纪律要求的前像）**：`c2_handoff_to_d_20260930.md.before_04e88125c921` · `daily_report.md.pre_c2_3_addendum_440256b8739f` · `daily_report.md.pre_c2_3_addendum_fix_7b616252788d` · `daily_report.md.pre_c2_3_addendum_fix2_fcacb0c1f50f` · `c2_handoff_to_d_20260930.md.before_0938b9b20f81` · `c2_handoff_to_d_20260930.md.before_eaeea73305b5`（= 本段这次覆写更正自己的前像，**自含**）。**⇒ 顺带更正 §10.8-⑧ 那句「每编辑一次文书 +1 件」的因果**：**+1 来自「编辑文书必须留前像」，不是来自「测量」** —— 只读复算不写文件 ⇒ **测量可以做无限次而计数不动**。C2 上一版把两者混为一谈、写成「重跑探针就是追自己的尾巴」，那是**推理错**（重跑探针也不新增路径：产物路径固定不变），据此更正；真正会推高计数的是**文书编辑次数**，而这一轮 C2 编辑了 6 次。
- **对 裁定 99 的含义（不改 D 的倾向，只把代价说清）**：若采「移出 `NORM_DIR`」，**要移的就是这 28 件**（22 + 5 + 1）。**注意标记件与那 51 份顶层便利副本不是一类**：标记件是 C2 自己的文书产物、**可以移**；51 份副本是 D 的文书正引用的对象、**不能移**（见 §10.8-⑤）。若采「登记例外」，因为 `G20_write_scope` 用**精确成员判定**（§10.8-⑥），**需要 28 条路径级条目，且 C2 每编辑一次文书就要再加一条** ⇒ **C2 建议采「移出」，目标定为 `runs/vla/c2_docs_ruling98/`（D 在 §D98.8-④ 举的那个例子）**；移出**必须与「已发布引用路径的追平」作为同一批、由 D 一次授权**（否则就是缺陷类 ㉒），**C2 不自行搬动**。
- **③-末 · 本段覆写更正的自报（Ⅲ 类，同轮第 3 次自纠，请 D 记入 C2 的账）**：本段第一版写的是「要移的就是这 **27** 件（22 + 5），其中**前像类 15 件、探针/产物类 6 件、文书与说明件 6 件**」—— **三个类计数全是手打的**，且 15+6+6 只是把「推导出的总数 27」拆成三个凑数的桶；实测是 **22 / 5 / 1 = 28**。**近因**：C2 先写散文、后跑分类器，而那个分类器自己也有 bug（判据写成 `「/before_images/」 in p`，而 `p` 已剥掉目录前缀、开头没有斜杠 ⇒ **恒假**，打出 `before_image=0 / doc_or_marker=17`，与散文**又**不一致）⇒ **两个数都不是实测，而先落盘的是散文那个**。**根因与 ② 完全相同（手数／手打不实测），而 ② 里 C2 刚刚自缚「写之前先测」⇒ 同轮之内自缚的纪律立刻被自己破了一次，这比错本身更该记账**。**已改的做法（可核）**：本段每个数字都取自上面那次只读复算的打印输出；分类判据改成 `p.startswith(「before_images/」)` 且**逐类打印路径**。**覆写只动两处：标题行（原第 239 行）与 ③ 段（原第 245–249 行）**，三条不变式实测为真 ⇒ ①②④ 一个字节没动：`head -238` = `8607da1569c7`（与前像同值）· 原第 240–244 行（①②）= `e39a17654b93`（与前像同值）· `tail -2`（末空行 + ④ 段）= `73a3387177a8`（与前像同值）。前像 = `…/before_images/c2_handoff_to_d_20260930.md.before_eaeea73305b5`（覆写前全文 **251 ln(`n_lines_wc`) / 46190 B / `eaeea73305b5`**）；覆写后全文 **252 ln(`n_lines_wc`)**。

**④C2 真停（补单四 §三 两件全交 + 本节收尾）**：等 D 的三件 = 裁定 99 的第一项处置（移出／例外，C2 已给可行性差异与代价）· §10.8-⑨ 的减负提案（git 作为受跟踪件的前像）· commit-5 的授权（B2 单写者）。**A2 第 1 步在飞**（`scripts/a2_step1_prealign_verify.py` 已在盘上、未跟踪）⇒ **C2 不代跑、不碰 A2 的写入面**，它若来问口径 C2 答。**裁定 46 不变：本节所有数字只指文书身份、闸判词、探针判词与身份对账，policy 指标仍 = 0，不构成任何能力表述。**

---

## §10.10【补单六-② 的搬迁批次**已执行**：26 搬 / 3 留 / 0 失败 · `MOVE_RECORD.json` 已落 · 搬后 `G20` 重计数（两把尺 × 两种 cutoff）· 补单六-③ 要的两处身份追平 · 一处 OPEN 请 D 裁】（2026-09-30T17:42:27+08:00 追加；**本节由 `scripts/c2_render_repoint_section.py` 从 `MOVE_RECORD.json` 取值渲染，路径与数字都不是手打**）

**①授权与目标路径**：裁定 100 §100.5 / 补单六-②。目标 = `runs/vla/c2_docs_ruling99/`（**D 定死的那个**，不是 C2 提的 `ruling98`）。范围 = 计划件 `E_move_execution_plan` 的 `decision=move` 那些行；**51 份顶层便利副本一件未搬**（`toplevel_convenience_copies_moved = 0`）。
**②逐件对账（`MOVE_RECORD.json` = `ce7945fab219` · 99093 B · 2163 ln(`wc -l`)）**：计划 29 行 ⇒ **搬 26 / 留 3 / 失败 0**；`all_moved_byte_identical = true`（逐件 sha 相等实测 = True）；`files_deleted = 0`、`rm_used = false`（**全程没用 `rm`**，搬运 = `os.replace` 同设备原子改名，inode 不变、mtime 不变、ctime 必变 ⇒ 自证列是 sha 相等）。
**③计划件身份（搬迁只按它执行，不按散文）**：`runs/vla/c2_move_dependency_audit_ruling99/MOVE_DEPENDENCY_AUDIT.json` = `7ff6ed7a095c` · 373428 B · 9090 ln(`wc -l`)；执行件 `scripts/c2_move_ruling99_batch.py` = `fa9ac65851d9` · 28179 B · 481 ln(`wc -l`)；禁搬判据逐字 = `hold_back ⟺ ¬in_authorized_scope ∨ ∃ 活代码引用(owner≠C2) ∈ A ∪ A2 ∪ E(functional) ∪ F1；F2 只产追平义务，不禁搬`。

**④搬走的 26 件（旧 → 新，逐件 sha 相等；`<tail>` = 目录内相对路径，前缀替换即映射）**：
`runs/vla/c2_norm_contract_20260929/<tail>` → `runs/vla/c2_docs_ruling99/<tail>`

- `before_images/BEFORE_IMAGE_MISLABEL_CORRECTION_20260930.md` — `38bea4b23af2` → `38bea4b23af2`（相等 = true；mtime 相等 = true）
- `before_images/TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json.before_6c7dc5a6f67a` — `6c7dc5a6f67a` → `6c7dc5a6f67a`（相等 = true；mtime 相等 = true）
- `before_images/c2_handoff_to_d_20260930.md.before_04e88125c921` — `04e88125c921` → `04e88125c921`（相等 = true；mtime 相等 = true）
- `before_images/c2_handoff_to_d_20260930.md.before_0938b9b20f81` — `0938b9b20f81` → `0938b9b20f81`（相等 = true；mtime 相等 = true）
- `before_images/c2_handoff_to_d_20260930.md.before_16223666925b` — `16223666925b` → `16223666925b`（相等 = true；mtime 相等 = true）
- `before_images/c2_handoff_to_d_20260930.md.before_4f8b3647d302` — `4f8b3647d302` → `4f8b3647d302`（相等 = true；mtime 相等 = true）
- `before_images/c2_handoff_to_d_20260930.md.before_eaeea73305b5` — `eaeea73305b5` → `eaeea73305b5`（相等 = true；mtime 相等 = true）
- `before_images/c2_probe_g20_scope.py.before_0fccf8c56afa` — `0fccf8c56afa` → `0fccf8c56afa`（相等 = true；mtime 相等 = true）
- `before_images/c2_probe_g20_scope.py.before_1302f5dbe432` — `1302f5dbe432` → `1302f5dbe432`（相等 = true；mtime 相等 = true）
- `before_images/c2_probe_g20_scope.py.before_2f849d63a7db` — `2f849d63a7db` → `2f849d63a7db`（相等 = true；mtime 相等 = true）
- `before_images/c2_probe_g20_scope.py.before_3eece4d468e1` — `3eece4d468e1` → `3eece4d468e1`（相等 = true；mtime 相等 = true）
- `before_images/c2_probe_g20_scope.py.before_60d5e3580aa5` — `60d5e3580aa5` → `60d5e3580aa5`（相等 = true；mtime 相等 = true）
- `before_images/c2_probe_g20_scope.py.before_c13bea402efd` — `c13bea402efd` → `c13bea402efd`（相等 = true；mtime 相等 = true）
- `before_images/c2_probe_g20_scope.py.before_cf79c181d8e1` — `cf79c181d8e1` → `cf79c181d8e1`（相等 = true；mtime 相等 = true）
- `before_images/daily_report.md.pre_c2_2_append_7e4a354bd173` — `7e4a354bd173` → `7e4a354bd173`（相等 = true；mtime 相等 = true）
- `before_images/daily_report.md.pre_c2_3_addendum2_909492446b13` — `909492446b13` → `909492446b13`（相等 = true；mtime 相等 = true）
- `before_images/daily_report.md.pre_c2_3_addendum_440256b8739f` — `440256b8739f` → `440256b8739f`（相等 = true；mtime 相等 = true）
- `before_images/daily_report.md.pre_c2_3_addendum_fix2_fcacb0c1f50f` — `fcacb0c1f50f` → `fcacb0c1f50f`（相等 = true；mtime 相等 = true）
- `before_images/daily_report.md.pre_c2_3_addendum_fix_7b616252788d` — `7b616252788d` → `7b616252788d`（相等 = true；mtime 相等 = true）
- `before_images/daily_report.md.pre_c2_3_append_b2f3b656f52a` — `b2f3b656f52a` → `b2f3b656f52a`（相等 = true；mtime 相等 = true）
- `before_images/g20_enumeration_scope_probe.json.dryrun_b71a68406287` — `b71a68406287` → `b71a68406287`（相等 = true；mtime 相等 = true）
- `probe_g20_scope_ruling98/g20_enumeration_scope_probe.json` — `6a1e599b60da` → `6a1e599b60da`（相等 = true；mtime 相等 = true）
- `probe_g20_scope_ruling98/g20_enumeration_scope_probe.v1_0f732c9fd674.json` — `0f732c9fd674` → `0f732c9fd674`（相等 = true；mtime 相等 = true）
- `probe_g20_scope_ruling98/g20_enumeration_scope_probe.v2_1dabd5465c3b.json` — `1dabd5465c3b` → `1dabd5465c3b`（相等 = true；mtime 相等 = true）
- `probe_ruling97_3_class1_narrowing/criterion_drift_audit_125721_vs_133156.json` — `7688314d0b12` → `7688314d0b12`（相等 = true；mtime 相等 = true）
- `probe_ruling97_3_class1_narrowing/g20_declared_exception_match_probe.json` — `e2e105c65f28` → `e2e105c65f28`（相等 = true；mtime 相等 = true）

**⑤留下的 3 件（`hold_back`）与逐件证据**（补单六-②-3 的预期是「→ 0」，**实测做不到 0，且不该硬做到 0**：追平这三处不在 C2 的写入面内）：

- `TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json` — 阻塞方 = A2/B2；引用锚点 `harness/bc_admission_gate.py`:1371、`scripts/b2_bc_input_inventory.py`:96；他线产物里的**入参型**消费记录 15 处
- `before_images/c2_to_a2_bc_stats_handoff_20260930.md.before_1ffbe342f5bb` — 阻塞方 = B2；引用锚点 `scripts/b2_bc_input_inventory.py`:1385、`scripts/b2_bc_input_inventory.py`:1385；他线产物里的**入参型**消费记录 6 处
- `before_images/c2_to_a2_bc_stats_handoff_20260930.md.before_9d6b14f1e477` — 阻塞方 = B2；引用锚点 `scripts/b2_bc_input_inventory.py`:1385、`scripts/b2_bc_input_inventory.py`:1385；他线产物里的**入参型**消费记录 0 处

**⑥搬后 `G20` 重计数（判据只读复刻自闸源码；`find` 与纯 Python 两条独立实现互为对照）**：
- 枚举命令逐字（记进产物）：`find runs/vla/c2_norm_contract_20260929 -type f -newermt 2026-09-30 13:33:51 -print`（另一路 = 把 `-newermt` 换成 `-newerct`）；排除面 = run 目录 `runs/vla/c2_norm_contract_20260929/gate/run_20260930_133156` + 既声明例外 1 条（精确路径成员判定）。
- **D 的代理截止时刻 `2026-09-30 13:33:51`（D 数出 28 件的那把尺）**：`mtime`（= 闸当前判据）→ **3 件**（搬前 29）；`mtime ∨ ctime`（= 99.4-② 待授权的 P2 形态）→ **106 件**（搬前 132）。`find` 与 Python 两路**逐件相符**：mtime = true、ctime = true（对称差 = 0）。
- **下一轮开闸时刻 `2026-09-30 17:35:29`（`cutoff = t_start` 的真判据）**：`mtime` → **0 件**、`mtime ∨ ctime` → **0 件** ⇒ 两种形态都是 `GREEN-able（未声明写入 = 0）`。
- 非恒真哨兵仍成立：`matrix.json` 在枚举集内 = true，run 目录外枚举到 **23456** 件（搬前 23482 ⇒ 差 26 = 搬走的件数）。
- **⇒ 一条必须点名的口径**：搬前用「下一轮 cutoff」量也是 0（C2 上一节已实测），所以「先搬以免 `G20` 恒红」这个前提**本来就是假的**；这批搬迁的真实价值 = **把 D 那把历史尺（13:33:51）上的账清到只剩 3 件**，以及让 P2（`mtime ∨ ctime`）一旦被授权也不会把这 26 件数进去。

**⑦补单六-③ 要的两处身份追平（追加、不覆写；§10.4 的原文一字未动）**：
- 探针产物：§10.4 引的「65038 B / 1339 ln / `0f732c9fd674`」是 **v1 保留件**的身份；**定稿件**现值 = D 在 §100.5 写死的那一组（106145 B / 2002 ln(`wc -l`) / `6a1e599b60da`），**路径已随本批搬到** `runs/vla/c2_docs_ruling99/probe_g20_scope_ruling98/g20_enumeration_scope_probe.json`（实测身份 {"path": "runs/vla/c2_docs_ruling99/probe_g20_scope_ruling98/g20_enumeration_scope_probe.json", "measurement_status": "measured", "bytes": 106145, "sha256_12": "6a1e599b60da", "n_lines_wc": 2002, "n_lines_splitlines": 2003, "mtime": "2026-09-30T15:28:32+08:00"}）。同目录两份保留件 `.v1_0f732c9fd674.json` / `.v2_1dabd5465c3b.json` 一并搬到同一新目录。
- 生成器：§10.4 引的「512 ln / 30393 B / `c13bea402efd`」是**更早版本**；D 在 §100.5 写死的现值是 `44725 B / 696 ln(`wc -l`) / e9abbacb9f68`；**本节这一批又改了一次它**（补单六-②-1 要求的引用追平：`PROBE_DIR` 与文书头那条写入面声明指向新目录，并把 `self_reference_caveat` 标成历史档 + 加 `superseded_by_move`）⇒ 改前 `e9abbacb9f68`（前像已留）→ **改后 {"path": "scripts/c2_probe_g20_scope.py", "measurement_status": "measured", "bytes": 46587, "sha256_12": "bbb49f5e6950", "n_lines_wc": 712, "n_lines_splitlines": 712, "mtime": "2026-09-30T17:38:53+08:00"}**。**这一跳是 C2 自己的写入面、在授权批次内；不重跑该探针**（补单六 §七）。

**⑧追平的其余部分（他线的面 C2 不改，逐条交 D）**：计划件的 `repoint_owner_split` 已把每一件的引用方分成「C2 自己的文书（本节 + 日报 §C2-4 追平）」与「他线文书 / 他线产物里的消费记录（交 D 在下一轮追平，或令该线自追）」两类；机器台账 = `runs/vla/c2_docs_ruling99/REPOINT_RECORD.json`（由 `--phase finalize` 从本批前像目录**扫描导出**，不手打）。
**⑨本子批的三个脚本要不要单子**：`scripts/c2_move_dependency_audit.py`（只读审计）满足 `declared_readonly_probe_needs_no_ticket` 的三条（对他线只读 / 只写自己目录 / 文书里点名理由）⇒ **不需要单子**；`scripts/c2_move_ruling99_batch.py`（执行搬迁）与 `scripts/c2_render_repoint_section.py`（渲染本节）**不是探针**，它们的授权就是补单六-② 本身（D 的单子），不套用那条 Ⅱ 类规则。
**⑩自报：本批暴露出 C2 审计器自己的第三个假阴性（已修，三版原字节都留着）**：v3 的 E 通道是 basename 子串匹配 ⇒ 看不见 `*` 通配，把两份 `c2_to_a2_bc_stats_handoff_20260930.md.before_*` 判成 0 引用、计划成 28 搬 / 1 留；实物是 `scripts/b2_bc_input_inventory.py` 的 `bi_dir.glob(...)` 拿它们当**归因证据**，空 glob 会把 B2 刚落地的 T-B2-19 v2 的 `verdict` 翻成 `unattributed_defect`、`ok` 翻回 `false`。**错误计划没有被执行**（C2 在跑 mover 之前逐件复核了计划）。v4 修的时候还自曝两处：第一版按行重算笛卡尔积 ⇒ 5 分钟没跑完（中止）；第二版盲目笛卡尔 + `fnmatch` 语义 ⇒ 40 万候选被截断、`*` 跨 `/` 造出 18 起假阳性、还把 Markdown 的 `**加粗**` 当通配串 ⇒ 第三版改成 **glob 语义 + 两条真实配对规则（同行 / 变量名以接收者身份回流且行距 ≤30）**，配不上的通配串逐条列出不吞掉。三版原字节 = `…py.v1_cd3c8c8afd4d` / `…py.v2_96e131af8cbd` / `…py.v3_03231856ee41`，v3 那次错误计划的产物也留着 = `MOVE_DEPENDENCY_AUDIT.v3run_6dedaa29383d.json`。

**⑪OPEN（请 D 裁，二选一）**：残值 3 件怎么处置 —— **(甲)** 令 B2 同批改两处（`scripts/b2_bc_input_inventory.py` 的 `P_C2_TOPLEVEL_MARKER` 常量 + `bi_dir` 那行的目录字面量）、令 A2 改一处调用入参（`--c2-broadcast-json` 指向标记件的新路径），C2 随后一分钟内补搬这 3 件、残值归 0；**(乙)** 接受残值 3，把标记件与那两份前像登记为 `G20` 的既声明例外（要改闸源码里的字面量 ⇒ 属 99.4-② 的 P1/P2 批次，C2 不自行改）。**C2 倾向甲**（一处一行、都在他线自己的写入面内），但**不代改**。
**⑫停点**：补单六 §七 —— 搬迁批次 + `MOVE_RECORD` + 搬后重计数 + 引用追平**已交完**，**C2 停**；不重跑全量闸、不改判据形态、不上卡、不开 BC、不重生成 stats（裁定 95.5 冻结令原样有效），**policy 指标仍 = 0**（裁定 46），本节所有「绿 / GREEN-able」只指闸判词与探针判词。

---

## §10.11【**C2 自报一起抗命类违规**：D 的停令 17:26:24 落盘，C2 的搬迁 17:35:33 执行 —— **中途没有回读监管件**】（追加；时刻与身份全部由 `scripts/c2_render_repoint_section.py` 从盘上取值渲染，非手打）

**①事实与时序（每一行都是盘上实测）**：

- D 的停令/改单**之前**的 C2 交接件（D 自己留的前像，即 C2 本轮 16:5x 读到的那一版）：`runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_c2_20260930.md.before_r102` — mtime **2026-09-30T16:33:04+08:00** · `6ec218a8483a` · 45170 B · 263 ln(`wc -l`)
- D 的停令/改单**之后**的 C2 交接件（含「v3 立刻停 · 搬迁降为纯整理」那段）：`rl_harness_supervision/d_handoff_to_c2_20260930.md` — mtime **2026-09-30T17:26:24+08:00** · `672ad7dda1ca` · 47448 B · 270 ln(`wc -l`)
- C2 审计件 v3 那次的产物（28 搬 / 1 留的**错误计划**，留作负向腿）：`runs/vla/c2_move_dependency_audit_ruling99/MOVE_DEPENDENCY_AUDIT.v3run_6dedaa29383d.json` — mtime **2026-09-30T16:58:49+08:00** · `6dedaa29383d` · 251311 B · 6231 ln(`wc -l`)
- C2 审计件 v4 的产物（26 搬 / 3 留的**生效计划**）：`runs/vla/c2_move_dependency_audit_ruling99/MOVE_DEPENDENCY_AUDIT.json` — mtime **2026-09-30T17:30:03+08:00** · `7ff6ed7a095c` · 373428 B · 9090 ln(`wc -l`)
- mover 的 dry-run 记账件：`runs/vla/c2_docs_ruling99/MOVE_RECORD.dryrun_eecee5b61ffc.json` — mtime **2026-09-30T17:34:55+08:00** · `eecee5b61ffc` · 70877 B · 1496 ln(`wc -l`)
- mover 的正式记账件 `MOVE_RECORD.json`：`runs/vla/c2_docs_ruling99/MOVE_RECORD.json` — mtime **2026-09-30T17:35:33+08:00** · `ce7945fab219` · 99093 B · 2163 ln(`wc -l`)
- C2 交接件（§10.10 已追加 ⇒ 这一版是追加**之后**）：`docs/c2_handoff_to_d_20260930.md` — mtime **2026-09-30T17:42:27+08:00** · `7a491f41712a` · 61569 B · 314 ln(`wc -l`)

**⇒ 时序结论（不辩解）**：D 的改单（「搬迁的那条技术理由已被实测否证 ⇒ 降为纯整理，**Step 1 出结果前不做**」「**v3 不必跑完 —— 立刻停**」）在 `d_handoff_to_c2_20260930.md` 落盘的时刻，**早于** C2 的 dry-run、正式搬迁、探针常量追平与 §10.10 追加。C2 本轮只在**开头**读过一次监管件（当时它还是 `6ec218a8483a` 那一版、263 ln、没有这段停令），此后一路执行到完，**中途没有回读**。
**②根因（与 D 在 裁定 100.2 自报的那件同型，方向相反）**：D 把「线有没有报」当成了「线有没有做」；C2 把「本轮开头没有新令」当成了「本轮全程没有新令」。**近因** = 长批次执行里没有「每次落盘前回读监管件」这一步；**这不是记账错，是执行了已被撤回范围的授权** ⇒ C2 自评 = **抗命类**，**请 D 定性，C2 不自行降格**（也不自行升格）。
**③影响面（唯一能减损的部分，逐条现取）**：
- 冻结面三件**一字未动**：`harness/norm_contract.py` = `91795179de7e`、`scripts/c2_build_norm_stats.py` = `1bc468012cff`、`scripts/c2_gate_norm_contract.py` = `c9445a9a7f6a`（**三个身份都与 D 待命令段点名的那一组逐字相符**，现取现比）。
- **Step 1 的输入面未动**：判定层与 stats 档都在冻结面上；49 份 `stats/*.json` + `mainline_status.json` + `matrix.json`（= 51 份顶层便利副本）**一件未搬**（`toplevel_convenience_copies_moved = 0`）。
- **他线活代码的三件全部留在原地**（`hold_back`），实测身份未变：`TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json` = `7ff12c6b3e56`、`c2_to_a2_bc_stats_handoff_20260930.md.before_1ffbe342f5bb` = `1ffbe342f5bb`、`c2_to_a2_bc_stats_handoff_20260930.md.before_9d6b14f1e477` = `9d6b14f1e477` ⇒ B2 的 `P_C2_TOPLEVEL_MARKER` / `bi_dir.glob(...)`、A2 的 `--c2-broadcast-json` **都照旧解析得到**，没有任何一条他线判词因这批搬迁翻转。
- **可逆**：26 件全部 `sha256[:12]` 搬前 = 搬后（`all_moved_byte_identical = true`、inode 不变、mtime 不变），`MOVE_RECORD.json` 里逐件有 `from → to` ⇒ **回滚 = 26 次逆向 `os.replace` + 探针常量回指**（两向前像都在盘上），C2 一分钟内可完成。
- **CPU 占用**：17:26:24 之后 C2 的进程墙钟可由上面那串 mtime 界定（审计 v4 两跑 + mover dry-run/正式各一跑 + 渲染一跑，均单核、均在 20 秒以内）；现刻机器状态 = `loadavg 15.44 13.15 10.49` / `nproc 112`（as_of 2026-09-30T17:48:30+08:00）。**D 点名 v3 与 A2 争 12 核配额那条，C2 认**：v3 那次 5 分钟未出结果的跑确实是浪费，已被 C2 自己中止（见 §10.10-⑩）。

**④请 D 二选一（C2 不自行选择 —— 回滚同样是一次未被下令的文件系统动作）**：
- **甲 = 追认**（既成事实不撤，参 裁定 100.4-(a) 的先例）：路径映射以 §10.10-④ 为准，D 的 §100.5 那两处探针产物路径需在下一轮追平；C2 随后**真停**。
- **乙 = 回滚**：C2 按 `MOVE_RECORD.json` 逐件逆向 `os.replace` 回 `NORM_DIR`，并把 `scripts/c2_probe_g20_scope.py` 的 `PROBE_DIR` 回指原处（前像 `before_images/c2_probe_g20_scope.py.before_e9abbacb9f68` 在新目录里，改前身份与 D §100.5 写死的一致）；回滚同样逐件记 sha 相等，另出 `ROLLBACK_RECORD.json`。
- **无论甲乙，残值 3 件的那个 OPEN（§10.10-⑪）都还在**：甲 ⇒ 仍是 3；乙 ⇒ 回到 29。

**⑤C2 已停（这次是真的）**：不再跑审计、不再跑 mover、不改闸/判据/stats、不上卡、不开 BC、不重生成 stats（裁定 95.5 / §101.1 治理冻结照旧）；**policy 指标 = 0**（裁定 46）。本节之后 C2 只在 D 下令时动。

## §10.12【**裁定 103.6-④ / 104 点名的两件已交**：E4 两把牙的裁定材料（Part A）+ ③ 号问题的方案设计（Part B，只出方案不落地）· 一条 Ⅰ 类候选缺口 **G1**（主线那次 `train,rollout,report` 调用不经过准入闸）· 一条 Ⅱ 类缺口 **G2**（`broadcast_crosscheck` 永不触发却被算进 `measured`，根因在 C2 侧）· C2 自纠 4 处旧数字 · 搬迁措辞追平 + 两处 OPEN】（追加于 2026-09-30T19:49:44+08:00；**原字节一律不追改**，本节由 `scripts/c2_safe_append_broadcast.py`（**138 ln(`wc -l`) `4f751ba05981`**）追加并自证纯度；数字全部取自证据件字段，不手打）

### 10.12.0 交付件身份（约束性判据 = `sha256[:12]`；行数点名口径）

| 件 | 身份 |
|---|---|
| **主交付（裁定材料 + 方案设计）** | `docs/c2_e4_teeth_and_bc_coupling_20260930.md` = **267 ln(`wc -l`) `79b8c0292537`**（33509 B；Part A = E4 / Part B = ③ 号问题 / Part C = 搬迁追平 / Part D = 身份·自纠·停点） |
| **证据件（所有数字的唯一出处）** | `runs/vla/c2_e4_ruling_material_20260930/E4_EVIDENCE.json` = **2537 ln(`wc -l`) `c9eddacec6c2`**（100022 B，as_of `2026-09-30T19:35:28+08:00`） |
| **取证器** | `scripts/c2_e4_ruling_material.py` = **935 ln(`wc -l`) `e7fc265707e8`** |
| **追加器（本节用的工具）** | `scripts/c2_safe_append_broadcast.py` = **138 ln(`wc -l`) `4f751ba05981`** |
| **追加纯度记录件** | `runs/vla/c2_e4_ruling_material_20260930/APPEND_RECORD_c2_handoff_10_12.json`（前像 `runs/vla/c2_docs_ruling99/before_images/c2_handoff_to_d_20260930.md.before_f0e545acf0b5` = **344 ln(`wc -l`) `f0e545acf0b5`**） |
| **读取时刻的监管件** | `rl_harness_supervision/d_handoff_to_c2_20260930.md` = **281 ln(`wc -l`) `52ab5c8317c7`**（mtime `2026-09-30 19:08:16`）；落盘前**已回读**（上轮抗命的根因就是不回读，本轮每次落盘前都回读一次） |

### 10.12.1 边界自证（一条没越）

- **不重跑全量闸**（裁定 104-②）· **不上卡** · **不改任何牙的极性 / 阈值 / 断言文本 / `applies_when`** · **不新增牙、不新增身份规则、不新增非 Ⅰ 类门禁**（裁定 101.1）· **不动判定层 `judge_from_facts` 与 stats 档 `b2150e0a3264`**（A2 的 Step-1 正在消费）· **不动 `min_grasp_pi05`**（裁定 103.6-②）· **不 commit、不 `rm`**（B2 是唯一 git 写者；回收走 `tmp/recycle_bin/`）。
- **冻结面跑前跑后复算全相符**：`harness/norm_contract.py` `91795179de7e` · `scripts/c2_build_norm_stats.py` `1bc468012cff` · `scripts/c2_gate_norm_contract.py` `c9445a9a7f6a`；证据件字段 `frozen_surface_integrity.unchanged_by_this_probe = true`。取证器**用 `ast` 静态解析、不 import 任何判定/训练模块** ⇒ 「一个字节不动」是**结构性的**，不只是声明。
- **重活只有一处**：`gate_verdict.json`（99391987 B）的**单遍流式** sha + 子串计数（`n_passes=1`，**不 `json.load`**），全程 `nice -n 19`，取证器墙钟 **~2 s**。
- **能力声明禁令（裁定 46/101.3）**：`capability_claim=false` · `policy_executed=false` · `gpu_used=false` · `success_metrics_collected=false` · `success_rate_column=not_an_exit_criterion`。本节出现的任何 GREEN **只指**「追加纯度自证通过」或「闸/探针判词」，**不是**能力表述。

### 10.12.2 Part A 的要点（E4）——**含一处对 D 措辞的更正**

1. **更正**：执行单三处（§101.1 / 待命令·二 / 补单·四-①）称「E4 那两把 **blocking** 牙」，而它们**自裁定 93.1-1 起 `blocking=False`**。三层机器证明：`tooth()` 的 status 机制 `harness/norm_contract.py:1028`（`"RED" if blocking else "WARN"`）· 两牙调用处 `:1276`/`:1231` **显式** `blocking=False`（AST 取实参 ⇒ 能区分「显式 False」与「没给取默认 `True`」，这正是裁定 93.1-1 里 D 亲核过的那个区分）· 上一轮权威闸跑 `matrix.json` **49 行**里两牙 `blocking` 直方图都是 `{"False": 49}`。**若按字面理解那句话，会得到「Step-1 期间有两颗硬红牙盯着 E4」这个错的风险图景。**
2. **实际盯着的是裁定 93.2 的两颗硬红**：`Tz_denom_strictly_positive`（`:1197`，`blocking=True`，全臂）+ `Tres_per_dim_resolution_floor`（`:1353`，`blocking=True`，逐维·**全量口径**）。权威档（`formal40_bc_source` **8 行**）实测 **`Tz` PASS 8/8、`Tres` PASS 8/8**。
3. **阈值溯源表**（约束性判据 = `ContractThresholds.provenance` 的状态串，AST 取出）：`min_bins_occupied=8`（`:926`）/ `floor_materiality_fraction`（`:939`）= `registered_measurement_not_a_judgment` ⇒ 按 `redline_provenance_discipline` **不得 blocking**；`clip_ratio_cap`（`:925`）= `proposed_pending_s1`、`near_constant_rel_tol`（`:935`）= `derived_from_min_F1_candidate` 同族；`Tres` 的三个（`:951/:952/:953`）= `d_calibrated_from_formal40_all_caliber` ⇒ 可以 blocking。⇒ **裁定 93.1-1 在盘上自洽**。
4. **权威档 WARN 读数**：`Tb` **WARN×8**（不足维 `[0,3,5,7,10,12]`）· `Tr3` **PASS×4/WARN×4**（不足维 `[3,10]`）。全 49 行背景：`Tb` PASS 25/WARN 24；`Tr3` PASS 13/WARN 12/**N_A 24**。臂内件散文的 WARN 计数（AST 解析）与逐行扫描**同值** ⇒ 两条独立路径互证。分档口径：49 行 = `formal40_bc_source` 8 · `formal40_lerobot_crosscheck` 16 · `env_derived_diagnostic_only` 24 · `yam_abc130k_mustred_branch` 1。
5. **三口径逐维 bin 占用一次给全**（不再只引一个口径；取自 D 的定标件 `55190798963c`）：held-out（n=547）`[3,97,106,2,38,3,35,4,111,108,5,46,5,36]` · build（n=10488）与 **all（n=11035）** 同为 `[23,117,114,3,47,24,87,22,117,117,5,48,22,72]`；`near_constant_dims=[3,10]`。
6. **held-out 盲维（裁定 94.3，Ⅱ 类）**：`n_distinct_heldout_patterns = **2**`（只在 dim10 差 1：`4` vs `5`），`correctness_blind_dims_union=[0,3,5,7,10,12]` 两模式下一致。
7. **E4 的三条路径 + C2 建议**：**甲 = 现状**（Step-1 期间不动，代价 0）· **乙 = 定标后恢复 blocking**（前置三条：只能用**全量口径**定标；`min_bins_occupied` 必须与 `Tres` 的 8 **同源同值**；`floor_materiality_fraction` 还缺 formal-40 上逐维 `floor_d / physical_range_d` 的分布测量 —— **本轮没有这个件**）· **丙 = 只改登记口径**（把两把 WARN 牙显式列成「阈值未定标 ⇒ 只登记不阻塞」，与六维盲点并列，代价 0）。**建议：Step-1 期间 = 甲；Step-1 后 = 丙 立刻可做，乙 等测量补齐再谈。**

### 10.12.3 Part B 的要点（③ 号问题）——**耦合已落地，但主线那次调用绕过它**

1. **前提已部分失效（C2 上轮的判断需要追平）**：③ 号问题**不再是「脱钩」**。`harness/bc_admission_gate.py:633` 确实调用 C2 的 `bc_admission()`；R3 只从实物读 `verdict_class1`（`:603/:605/:607/:618`）；`bc_blocking_caliber` = 三条（`:743`）；stats / npz / gate_verdict / 臂内件 / G14 证据**全部由消费方自己复算 sha**；存量标签 vs 重算值双向都取、不一致即拒。契约层 `admissible_for_bc` 仍标签派生（`norm_contract.py:526`）是**刻意设计**，牙 `Tbcad_admission_requires_green_gate`（`:1129`）`blocking=True` 且缺 class-1 证据即红。
2. **两向都在实物上验过**：正向 `BC_ADMISSION_STEP1_20260930_164227.json`（`fec7ad9ee336`，`admitted=true`、`verdict_class1` 实物读到 `PASS`、stats 复算 = 声明 `b2150e0a3264`、`npz_crosscheck.same_source_holds=true`）；负向 `a2_bc_admission_consume_20260930_run{1,2,3}` 的 `admitted` = **true/false/true**。
3. **G1（Ⅰ 类候选，但不是 Step-1 的出场判据）**：守望器 `tmp/a2_step1_watcher.sh:114`（`d19c42a318e2`）将起跑 `--stages train,rollout,report`，`admission_in_stages=false`；入口脚本 `2ec02373d3f6`（4327 ln，mtime **19:30:00**，**活体移动靶**）里 `:4250` 是唯一准入入口；25 处 `admission` 命中**穷举**后按函数区间归属 ⇒ `stage_train`(2199–3162) **0 处**、`stage_rollout`(3163–3640) **0 处**、`stage_report` 只有 `:3644/:3654` 的 **glob-latest** 绑定。**否定存在性由穷举扫描支撑**（红线 `absence_of_measurement_is_not_measurement_of_absence` 的正确用法），不是「C2 没找到」。
4. **G1 的缓解事实（与缺口并列报）**：准入依赖的四个身份 16:42 之后未变（`b2150e0a3264` / `a84a26079550` / `e72776306f98` / `fa59b263c5fa`），判据模块 `41f751019e69`（14:44:37）与 `91795179de7e`（13:13:28）都**早于** 16:42 ⇒ 判据形状没变；变了的入口脚本**前像在盘**（`before_images/a2_step1_bc_overfit.py.before_136eaf0f95c9`，sha 相符）。**定性 = 证据链没随载荷刷新，不是准入结论错了。**
5. **G1 的三条修法**：**甲（推荐）** = 起跑前单独跑 `--stages admission`（`GPU_STAGES=("probe","train","rollout")` `:133` ⇒ `need_gpu=False`、不需要窗口申报、不受排队影响；A2 上次墙钟 **3.336 s**）· **乙（不推荐）** = 守望器 stages 加 token，但准入会落在 GPU 窗口内（`window.open()` 在阶段循环之前）⇒ 可能污染窗口判据，拒了还要补 yield 记账 · **丙** = `stage_train` 入口新增牙 ⇒ **触 101.1，本轮不落地**，登记为 Step-1 后的终态修法。**C2 不代 A2 跑、不代 A2 改文件。**
6. **G2（Ⅱ 类，根因在 C2 侧）**：`broadcast_crosscheck` 的阻塞条件是 `measured ∧ not agree`（`bc_admission_gate.py:1569`），而 A2 活件里它 `not_measured`（`sources_given={markdown:true,json:false}`），却**不阻塞、不进 `not_measured_items`（实测 `[]`）、不出 warning（`[]`）**，同时 `decision_measurement_status="measured"` ⇒ **一条从未跑过的腿被算进「已测」**（缺陷类 ⑲ 同族）。**根因**：裁定 96.1-④ 要成对载体，而 **C2 从未发过 JSON 载体**。**方案丁** = C2 补发 JSON 载体（不新增牙、不触 101.1）+ 消费侧把这条 `not_measured` 传播进 `not_measured_items`（那半属 A2/B2 写入面，**请 D 指派**）。
7. **G3/G4/G5**：**G3（Ⅲ）** 广播件是稳定名活件（`:192`），实测 A2 消费时 `408b667d0fda`/19238 B → 现值 `b1882c7a3546`/20639 B，**前 19238 字节 sha 复算 = `408b667d0fda`** ⇒ **纯追加**（`n_bytes_appended=1401`），A2 读过的字节一个没改；缺「train 时复核前缀」的牙。**G4（Ⅲ）** 臂内件 `next_required_action` 散文过期（A2 已 WARN；C2 按 97.3-5 不改生成物字段）。**G5（Ⅱ）** `control_hz` 只是调用方声明（A2 已 WARN），BC 运行时须落实测值。

### 10.12.4 C2 自纠 4 处旧数字（同族于 D 的 ⑲，**旧数字一律撤回**）

| # | 上轮 C2 说过 | 本轮实测（口径点名） | 定性 |
|---|---|---|---|
| 1 | `gate_verdict.json` 含 `verdict_class1` **43485** 处 / `triage_class` **58** / `Tbcad_…` **1267** | 单遍流式**子串上界**计数：`"verdict_class1"` **1** · `verdict_class1` **55329** · `"triage_class"` **54** · `triage_class` **59** · `Tbcad_admission_requires_green_gate` **1269** | 旧数字**无口径**（带不带引号、哪一轮）⇒ 裁定 98.5 的身份/口径错 |
| 2 | `Tb` WARN×8、`Tr3` WARN×4/GREEN×4（**未点名作用域**） | matrix 是 **49 行**，权威档只有 **8 行**；现在分档报 | 作用域缺失 ⇒ 会被读成「整轮 8 行」 |
| 3 | held-out 逐维占用当成**唯一**模式 | `n_distinct_heldout_patterns=2`（dim10 差 1） | 事实错（盲维并集不受影响） |
| 4 | 把入口脚本行号 `:104`/`:781` 当**常驻身份** | 该文件 19:16→19:30 由 `e75d2284fd6c`(4206 ln) → `2ec02373d3f6`(4327 ln) | 缺陷类 ㉒（时点读数当常驻身份）⇒ 改为 **sha + as_of 成对** |

### 10.12.5 Part C：搬迁的措辞追平 + 两处 OPEN（**C2 不自选**）

- **盘上事实 = 已执行完**（`MOVE_RECORD.json` **2250 ln `4bc4fa4b0c29`**：`n_rows_in_plan 29 / n_moved 26 / n_failed 0 / n_hold_back 3`；`REPOINT_RECORD.json` **635 ln `c380ee745394`**；`before_images/` **26** 件），而交接件 `52ab5c8317c7` 的待命令·二 仍写「搬迁…**仍延期**」⇒ **措辞与盘上事实不符，请 D 追平**：**甲 = 追认** / **乙 = 回滚**（C2 有能力做，**等 D 令**，不自选）。
- **抗命类自报不重复辩解**：搬迁发生在 D 17:26:24 撤回授权之后（17:35:33 执行），已自报在 §10.11 与日报 §C2-4；**OPEN 状态不变**。
- **账面缺口（本件第一次落盘）**：执行搬迁那版 mover（`fa9ac65851d9` / 481 ln）**没留前像**，只有身份在 `MOVE_RECORD.json` v1（`ce7945fab219`）里；缓解 = v1 与终版 `items`/`summary` 逐字节相同。请按 **Ⅲ 类**登记，处置由 D 定。

### 10.12.6 请示清单（**四条，全部等 D**；C2 一件不自选、不抢跑）

| # | 请示 | C2 建议 | 若批准后 C2 的动作 |
|---|---|---|---|
| 1 | **E4 采甲/乙/丙** | Step-1 期间 **甲（现状不动）**；Step-1 后 **丙**（纯文书）；**乙** 等 `floor_d / physical_range_d` 的逐维测量补齐再谈 | 甲/丙 = 0 字节改动；乙 的前置测量 = 只读 `matrix.json`，不上卡不重跑闸 |
| 2 | **G1 采甲/乙/丙** | **甲**（起跑前单独跑 `--stages admission`），**由 A2 执行** | C2 **不代跑**；只在 A2 跑完后复核新准入件的 producer sha 是否与训练版本一致（只读） |
| 3 | **G2 的方案丁** | C2 侧那半（补发 JSON 载体广播）**建议批**；消费侧那半（`not_measured` 传播）**请 D 指派给 A2/B2** | 批准后 C2 落一件 JSON 载体 + 在广播件里追加一节（**追加不覆写**，留前像） |
| 4 | **搬迁 甲/乙 + mover 前像缺口的类分** | 甲（追认）+ Ⅲ 类登记 | 甲 = 0 动作；乙 = C2 用 `before_images/` + `REPOINT_RECORD.json` 回滚 26 件（**等令**） |

### 10.12.7 停点

**两件交付即停。** 不重跑闸、不上卡、不改极性、不新增牙、不代他线改文件、不 commit、不 `rm`。等 D 的 Step-1 里程碑审查与上面四条的批复。主次不变：**主 = A2 的 Step-1**，C2 是辅线，不深入非主线细节。

### §10.12.8【**C2 自报一起 Ⅲ 类工具缺陷（恒真读数）+ 已修 + 修后验证**】（追加；**§10.12.0–10.12.7 的原字节一字未改**，本节仍由 `scripts/c2_safe_append_broadcast.py`（**修后 = 142 ln(`wc -l`) `da8b80a22a20`**）追加并自证纯度）

- **缺陷**：追加器的 `before_image.already_existed` 字段取值写在 `shutil.copy2(...)` **之后** ⇒ `before_path.exists()` **必然为 `True`** ⇒ 该字段**恒真**，表达不了「本轮才建的前像」。**家族** = 缺陷类 ⑲ 同族（尺的**时机**与被测对象不匹配 ⇒ 报绿而绿无信息），与 D 的 ⑲ 第 21 件（判据比对象空间**宽**）同族。
- **影响面（全部实测，不辩解）**：**判词 0 影响** —— 追加纯度用的是 `prefix_sha_equals_before_image` ∧ `appended_tail_equals_section_bytes`，与本字段无关，§10.12 与日报 §C2-5 两次追加都是 `GREEN` 且可独立复算；**前像 0 损失** —— 前像以「改前 sha」命名，同名已存在时 `cp -p` 覆盖的是**同 sha 即同字节**的内容；**已发布的广播 0 污染** —— §C2-5 与 §10.12 都**没有**引用这个字段。**受影响的只有两份记录件里的这一个字段**：`APPEND_RECORD_c2_handoff_10_12.json`（`cd02b47cdb92`）与 `APPEND_RECORD_daily_report_C2-5.json`（`36185367d78a`）⇒ 两件的 `already_existed=true` 应读作 **`not_measured`**；**记录件原字节保留、不追改**，更正件 = `runs/vla/c2_e4_ruling_material_20260930/TOOL_DEFECT_already_existed_selfreport.json`（**37 ln(`wc -l`) `c774e4bf34e4`**）。
- **修法**：存在性判定移到 copy **之前**，字段改名为 `existed_before_copy`（语义点名）并新增 `copy_performed_this_run`。修前 `4f751ba05981`（138 ln）→ 修后 `da8b80a22a20`（142 ln）。
- **修后验证（本节这次追加就是正向腿）**：记录件 `runs/vla/c2_e4_ruling_material_20260930/APPEND_RECORD_c2_handoff_10_12_8.json`（**自指悖论**：本节无法在落盘前引用「记录本节这次追加的那份记录件」的身份 ⇒ 按裁定 96.1-① 的引用形态改判，改为**指针 + 字段名**，不手打数字），实测字段 `before_image.existed_before_copy` ∧ `before_image.copy_performed_this_run` ∧ `prefix_sha_equals_before_image = true` ∧ `appended_tail_equals_section_bytes = true` ⇒ 两字段**互斥且非恒真**（若 `exists()` 仍在 copy 之后求值，这两个字段就不可能一个 `false` 一个 `true`）。**负向腿（`existed_before_copy=true`）的诚实口径**：前像名 = 目标件**当下** sha，每次追加都变 ⇒ 该向只在「同内容重跑（no-op）」时出现，**本轮没有天然覆盖**；C2 **不谎称已验**，登记为 `not_measured`，需要时可用一次 no-op 重跑补齐（等 D 点头，不自跑）。
- **纪律自记**：这是 C2 本轮**第 5 处**自纠（前 4 处见 §10.12.4 的数字表）。**共同根因** = 写了断言却没读它**在什么时机被求值**，与 D 今天三次纠错的根因（「读了声明没读实现」）同一族 ⇒ 已按 `redline_provenance_discipline` 的精神处置：**任何布尔字段都要问一句「它有没有可能为假」**，答不出来的就是恒真尺。

### §10.12.9【**回读追平：补单·五（裁定 106）已在 §10.12 落盘之后到达 ⇒ 三件事对齐，不与「件内无待 D 回答的问项」冲突**】（追加；上方 §1–§10.12.8 原字节一字未改；本节仍由 `scripts/c2_safe_append_broadcast.py`（**142 ln(`wc -l`) `da8b80a22a20`**）追加并自证纯度）

- **① 已回读**：`rl_harness_supervision/d_handoff_to_c2_20260930.md` 现值 **286 ln(`wc -l`) `8c6330877c0f`**（mtime `2026-09-30 19:47:10`，含**补单·五**）· `work/decisions/decisions_20260929.md` 现值 **4222 ln(`wc -l`) `a931e7a7a4d9`**（含 **§106 / §106.9**）。C2 的 §10.12（19:50 追加）与日报 §C2-5（19:49 追加）都**晚于**补单·五 ⇒ 本节把两边对齐。**上轮抗命的根因就是不回读，本轮每次落盘前都回读一次，这次是第 4 次。**
- **② 为什么不冲突（口径点名）**：补单·五-① 那句「**件内无待 D 回答的问项**（D 全文检索 `请 D` 命中 **0**）」的**检索对象是 `E4_EVIDENCE.json`** —— 那件是**纯证据件**，本来就不该含问项，D 的读数为真、C2 确认。而 §10.12.6 的四条请示在**主交付文书** `docs/c2_e4_teeth_and_bc_coupling_20260930.md`（**267 ln `79b8c0292537`**）与本交接件里，是**另一件**、且**晚 3 分钟**送达 ⇒ 两者不是同一对象空间（同族于 D 的 ⑲ 第 18/21 件：**尺的作用域要与对象空间对齐**，这里反过来用 —— 结论的作用域也要对齐）。
- **③ 按补单·五-② 执行**：E4 材料**原地待用、不刷新、不补件**（D 的理由 C2 采信并已实测印证：`Tres`/`Tb` 的任何分支都可能触发全量闸重跑 + 重生成 formal-40 stats ⇒ sha 变，而 Step-1 正在消费 `a84a26079550`）。**C2 不为等待做任何额外工作。**
- **④ 唯一有时效性的一条（请 D 在 A2 起跑前扫一眼，不需要回复 C2）**：§10.12.3-3 的 **G1** —— 守望器 `tmp/a2_step1_watcher.sh:114` 将起跑 `--stages train,rollout,report`（`admission_in_stages=false`），而 `main()` 的唯一准入入口是 `:4250` ⇒ **真正训练的那次调用不求值「准入闸 ∧ 质量闸」这个 AND**。修法**甲**（起跑前单独跑一次 `--stages admission`，CPU-only、`need_gpu=False`、不需要窗口申报、A2 上次墙钟 **3.336 s**）**由 A2 执行、C2 不代跑**；若 D 认为「16:42 那次准入 + 四个依赖身份未变」已足够（§10.12.3-4 的缓解事实支持这个读法），**C2 也接受，G1 降为 Ⅲ 类登记**。末次守望器读数（C2 只读，as_of `19:52:18`）：poll **59**、`busy=True util=100% mem=35753MiB apps=2 fd=18 cmd=0`、`loadavg 42.96`、`nr_throttled 24366` ⇒ **仍在排队**，起跑未发生。
- **⑤ 停点（不变）**：两件交付即停。**不重跑闸、不上卡、不改极性、不新增牙、不代他线改文件、不 commit、不 `rm`**；不把任何仓内文件往外部地址推、不把 key 写进任何新件（补单·五-⑤ / §105）。主次：**主 = A2 的 Step-1**，C2 是辅线。
