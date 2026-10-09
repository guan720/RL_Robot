# F 停点单 · 裁定 95/96 接单 + 本轮登记（不追改历史件）

- **线**：F（监管分析 / 进度核算，用户 2026-09-30 11:3x 指派，裁定 96 已核准）
- **权威**：裁定 95（方向重排 + 治理冻结令 + 六步关键路径）· 裁定 96（F 四条请示逐条答）· `daily_report.md` §D95.8 停点指令
- **as_of**：2026-09-30 12:2x（本文书内每一处身份/数字都带各自的 as_of；均为工具取值，F 未手算）
- **F 产物分诊**：一律 **Ⅱ 类**（登记不阻塞）。本文书**不设任何阻塞判据、不定标、不改极性**（裁定 96 对 F 的硬约束）。
- **能力声明禁令（裁定 46）不变**：`capability_claim = null` · `policy_executed = false` · `gpu_used = false`。BC 未出结果前，任何"能搬运"的表述都无效。

## 1 裁定 96 对 F 四条请示的答复 —— F 逐条确认与动作

| 请示 | D 的裁定 | F 的确认与本轮动作 |
|---|---|---|
| F① 活件行号锚漂移 | 准：活件引用一律「名字锚点 + `sha256[:12]` + `n_lines` + `as_of`」，行号只作辅助；不落码、不新增牙 | 接受。本轮所有引用已按此形态写。**新证据**：`Tb_scale_floor_effective` 的锚点第 4 次位移 = `harness/norm_contract.py:1233`（as_of 12:26:03，台账 F-19 实测），序列 `:977 → :1195 → :1218 → :1233` |
| F② 预登记条件消费方覆盖率 11.3% | 只补六步第 1–3 步相关的，其余 78 处永不补；覆盖率降为 F 的常设登记指标（必带 as_of + 作用域） | 接受。本轮已重测：**6 / 53 = 11.32%**（as_of 12:26:04，作用域 = `work/project_parameters.json` 内命中 `可推翻条件/trigger_to_promote/falsifiable/rebuttal/overturn` 的键）。**分母需按六步 1–3 重算**，见 §4 |
| F③ `card_busy()` 两档被文本误触发 | Ⅰ 类、P0.5，E 主责，必须在 A2 第一次真上卡之前修完；窄档改「真实执行形态 ∧ GPU 关键字」+ 排除 `pcpu≈0`；93.8 探针两向都装 | 接受。F 的探针 `scripts/f_probe_card_busy.py` 与三件读数（`runs/vla/f_oversight_20260930/probe_card_busy_20260930_11*.json`）可直接复用；`EXEC_FORM_RE` 已在其中。F 不代修（非 F 写入面） |
| F④ 同名双件 `mainline_status.json` 的 BC 消费口径 | Ⅰ 类：**= 最新一次 PASS 闸跑的臂内件**；顶层件须与臂内件字节一致或显式 `superseded_by`，否则 Ⅰ 类红；A2 只对 C2 声明的完整路径对账，不许 glob 后挑一份 | 接受，并已按此口径**实测定位**当前指向件，见 §3-F |

## 2 本轮交付（§D95.8 要求 F 每轮出的两件）

1. **进度台账**：`runs/vla/f_oversight_20260930/PROGRESS_LEDGER.json`，as_of **12:26:03**，21 项 = **16 delivered / 4 not_delivered / 0 not_measured / 1 not_applicable**，`verdict = ok`，93.8 对照探针全检出。
   - 与 11:54 那轮相比 **delivered 14 → 16**（T-B2-20 等已落地）⇒ 印证缺陷类 ㉒「台账时点读数不得当永久事实」，故本轮重取。
2. **预登记条件覆盖率**：`runs/vla/f_oversight_20260930/TRIGGER_REGISTRY.json`，as_of **12:26:04**，`n_entries = 53 / n_has_consumer = 6 / coverage = 0.1132`（口径与空集规则写在件内）。
3. 本文书 + `daily_report.md` §F2（只追加）。

## 3 登记（**依 §D95.8「历史件不追改（原字节保留）」⇒ 以下一律不改原文，只登记**）

- **A｜F 自报缺陷 #4（Ⅲ 类，红线 92.3 同族）**：`daily_report.md` §F1.9 里前像身份串是 **F 手写**的 `8c2f7c1c9c56`；工具实测该前像 `runs/vla/f_oversight_20260930/before_images/daily_report.md.beforeF1_boldfix` = **8116 ln `d82e9dff0387`**（sha1[:12] `90dca573db3f`，as_of 12:1x）。**处置 = 保留原字节 + 本条登记**（不就地改字）：裁定 96 明令历史件不追改，且 Ⅲ 类冻结扩张。**根因**：身份串未经工具生成即落笔。**已装的自查器**见 §3-D。
- **B｜F 自报缺陷 #5（Ⅲ 类，"引用未复测"）**：F 在 `docs/f_handoff_to_d_20260930.md`:14 与 `daily_report.md`:8085 把 `harness/prompt_bin_guard.py` 写成 `678 ln ab5bbc4768ba`，而该件自 **11:53:21** 起已是 **686 ln `a42674ef1e8a`**（as_of 12:2x 实测），F 落笔时刻分别是 **12:01:58 / 12:06:29** ⇒ **不是"引用后他线改件"，是 F 拿了旧读数当现值**。同一串 `ab5bbc4768ba` 也出现在 D §94.0（D 引用于 11:53:21 之前 ⇒ D 无过错，但**该引用现已过期**）⇒ 这是 F① 的活实例，D 已准 F①，无需再裁。
- **C｜他线活件 as_of 复测（Ⅲ 类，登记不阻塞；判据 = 工具取值，非推断）**：
  | 件 | D 文书里的值 | as_of 12:2x 实测 | 结论 |
  |---|---|---|---|
  | `harness/norm_contract.py` | 1784 ln `a030e951787e`（§D95.7-F①） | **1858 ln `1f0911041311`**，mtime 12:19:35 | 已过期（C2 在制，属 Ⅰ 类最小集） |
  | `registry/verdict_identity.py` | 1527 ln `33c7a0fedfac`（§D95.9，T-B2-20） | **1602 ln `4291be1b7bf8`**，mtime 12:22:58 | 已过期（B2 续写 +75 ln） |
  | `harness/prompt_bin_guard.py` | 678 ln `ab5bbc4768ba`（§94.0） | **686 ln `a42674ef1e8a`**，mtime 11:53:21 | 已过期（A2 续做，Ⅰ 类） |
  | `scripts/c2_build_norm_stats.py` | 3318 ln `996c031fc109`（§D95.1） | 3318 ln `996c031fc109`，mtime 11:52:15 | **相符** |
  | `scripts/c2_gate_norm_contract.py` | 3221 ln `0cc856c89951`（§D95.1） | 3221 ln `0cc856c89951`，mtime 12:02:29 | **相符** |
  | `scripts/f_progress_ledger.py` | 768 ln `786093aba075`（§D95.9） | 768 ln `786093aba075`，mtime 12:04:37 | **相符** |
  | 闸产物 `gate_verdict.json` | 69440530 B / 1534409 ln / `ae4e16c33743`（§D95.1） | 同值，实体 = `…/gate/run_20260930_073852/gate_verdict.json`，mtime 07:40:23 | **相符**（但见 §3-F：它已不是最新一次闸跑） |
- **D｜F 的第三件工具按裁定 96 重新归类（Ⅱ 类，不作牙）**：`scripts/f_verify_prose_identities.py`（**223 ln `301e761d5dff`**，12:08 落盘，早于 §D95 广播）原设计带 `exit 6 = mismatch` 的**阻塞语义**。裁定 96 明令「F 的产物一律 Ⅱ 类、不得设阻塞判据」，§D95.2 明令 Ⅲ 类「冻结扩张、不得新增牙」⇒ **重新归类为 F 自查用的只读登记器：它的任何退出码都不得用于阻塞他线，F 也不据它去改历史件**。**原计划的 v2（深层路径索引 + 漂移/陈旧判别 + 裁决台账）取消，不落码**；前像 `runs/vla/f_oversight_20260930/before_images/f_verify_prose_identities.py.beforeV2`（223 ln `301e761d5dff`）保留原字节。
  - 同时登记它的 **v1 已知窄化（缺陷类 ⑲，审计器模式比对象空间窄）**：首轮真实扫描（as_of 12:10:46，`prose_identity_audit_20260930_121046.json`，368 ln `af8386ac0370`）报 6 mismatch + 8 not_measured，其中经 F 手工逐个复算：**3 个 mismatch 是假警**（`778528624698` / `1d7be4d1b7c4` / `59fca05a6f68` 三串与实物逐字相符，只是路径深两级解析不到）、**4 个 not_measured 的串也全部正确**（`388f6c4edb16` = C2 的 `probe_monotonicity_20260930/verdict.json` 2623 ln；`fc3f049753bf` / `82fc52f60782` = 两份 `mainline_status.json`；`59fca05a6f68`）；**真缺陷只有 2 处**（§3-A、§3-B）。**此窄化按冻结令不修，只登记**；使用它时必须人工复核，不得直接采信其 mismatch。
- **E｜D §D95.10 声明"真落盘"的两件：一真一未落（三值 = `not_yet_on_disk`，**不判定为同型错误 #22**）**：
  - `rl_harness_supervision/d_context_checkpoint_20260930_1205.md`：as_of **12:22 缺失** → as_of **12:24:44 存在**（12746 B / 65 ln / `0a2d0ace85d4`，mtime 12:24:08）⇒ **F 的第一次读数是时点读数，F 自我更正**（这正是缺陷类 ㉒ 的反向实例：F 差点把"12:22 不在盘"写成"D 引用了从未落盘的件"）。
  - `runs/vla/d_ruling_round_20260930_1205/D_IDENTITY_TABLE_20260930_1205.json`：as_of **12:24:44 仍不在盘**（该目录只有 `params_rev21_write_result.json` / `write_params_rev21.py` / `before_images/`）。扫描作用域 = `runs/vla/d_ruling_round_*/`、`rl_harness_supervision/`、`docs/`、`work/`（`find -maxdepth 3`，限定前缀，未做 `find /`）。**D 线活跃 ⇒ 判 `not_yet_on_disk`（在制），F 下一轮复测**；若届时仍缺，才构成 §D95.10 新纪律「散文不得把计划写成事实」的实例。
- **F｜闸状态与 F④ 口径的当前指向（Ⅱ 类登记，供 A2/C2 对账用；F 不判对错）**：
  - **最新一次闸跑 = `…/gate/run_20260930_113655`（11:37:14）= `verdict RED / ok False`**，`n_checks 48 / n_red 6 / n_warn 0 / n_n_a 9`；6 颗红**全是 `blocking=True` 的 run 级元牙**（`G21_baseline_invariants` · `G14_Tr3_bites_on_mainline_only` · `G46_tooth_name_citation_integrity` · `G27_mainline_red_fully_explained` · `G51_mutant_anchors_match_exactly_once` · `G24_every_check_mutant_proven`，`arm = None`）⇒ **不是"变异体本该红"的那类红**。红的根因 F **未测**（`not_measured`）；两种候选读法并列登记：① C2 11:37 正在改 93.1 极性/最小集，元牙与新码不同步；② `G14_Tr3_bites_on_mainline_only` 的语义在 `Tr3` 降为 `blocking=False` 后需要改写。**不判**，交 C2/D 里程碑审查。
  - **最新一次 PASS 闸跑 = `…/gate/run_20260930_073852`（07:40:21）= `verdict PASS / ok True / n_red 0`**，`gate_verdict.json` = 69440530 B / 1534409 ln / `ae4e16c33743`。
  - ⇒ **按 D 的 F④ 口径，当前 BC 消费件 = `…/gate/run_20260930_073852/arm_mainline/mainline_status.json`（198907 B / 6445 ln / `82fc52f60782`，mtime 07:38:57）**；同目录树的顶层件 `…/c2_norm_contract_20260929/mainline_status.json`（198907 B / 6445 ln / `fc3f049753bf`，mtime 06:04:23）**字节数与行数全同、sha 不同**，且**未见 `superseded_by` 字段**（F 未逐键核，`not_measured`）⇒ 按 F④ 属 Ⅰ 类红的候选，**F 只登记不判**。
  - **进度含义（核算，不定标）**：该 PASS 件产于 **07:40**，**早于** 93.1 极性改动与 T-C2-8 最小集 ⇒ **第 1 步（小量示范过拟合 + 闭环执行）在"C2 重跑全量闸 + 重生成 stats"落地前拿不到一份与之同代的 PASS 闸产物**，与 §D95.8「第 1 步开跑前只等两件：C2 的新 stats 身份 + E 修完 ③」**一致**。

## 4 F 的下一轮交付（都不阻塞第 1 步）

1. **覆盖率分母按六步 1–3 重算**（F②）：需给出「53 条预登记条件 ↔ 六步」的映射草案，F 出草案并标 `not_measured` 的条目，**不定标**；其余 78 处按裁定**永不补**。
2. **复测 §3-E 的身份表**是否落盘（三值）。
3. **到期确认 F③/E 的 ③ 修复**（P0.5，A2 上卡前必须完成）：F 用 `scripts/f_probe_card_busy.py` 复跑两档，报"文本误触发是否归零"，`as_of` + 作用域齐备。
4. **台账每轮重取**（缺陷类 ㉒ 的常态化解法）：F 的台账/覆盖率一律带 as_of，且**下一轮不得沿用上一轮读数**。

## 5 请 B2 在 commit-4 带上的 F 件（更新 D §D95.11 的清单：原写"三份文书 + 两件工具"）

- 文书 **4** 份：`docs/f_task_selfintake_20260930.md` · `docs/f_handoff_to_d_20260930.md` · **`docs/f_stop_point_20260930.md`（本件，新增）** · `daily_report.md`（§F1 / §F1.9 / **§F2**）
- 工具 **3** 件：`scripts/f_progress_ledger.py`（768 ln `786093aba075`）· `scripts/f_probe_card_busy.py` · **`scripts/f_verify_prose_identities.py`（223 ln `301e761d5dff`，按 §3-D 归 Ⅱ 类只读登记器，非牙）**
- 提交信息请点名：**`runs/` 被 `.gitignore:12` 排除 ⇒ F 的台账 / 触发条件台账 / 探针读数 / 前像只在 NFS**（T-E-12 白名单已准，交 E 落地）。
- **F 不提交、不改他线文件、不写 `work/project_parameters.json`**（裁定 49.6 / 69.1 / 81.2：B2 单写者；params D 单写者）。
