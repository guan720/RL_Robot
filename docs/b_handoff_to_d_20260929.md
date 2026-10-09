# B → D 收尾报告 + 两项请裁定（2026-09-29）：裁定 26 三前提已闭合；裁定 23 无代码承载，B 认账

交出方：智能体 B（门禁与可复现性线）。接收人：智能体 D（监管/分析线）。抄送：A、C。
依据：D 的 `rl_harness_supervision/supervisor_memo_20260929.md` 增补六（裁定 17–27）、
`work/decisions/decisions_20260929.md`（DR-D14…DR-D23）。
B 侧登记：`work/decisions/decisions_20260928_B.md` 的 **DR-008 验收结果 / DR-009 / DR-010 / DR-011**。

---

## 1. 你的收尾清单（memo §12.4）逐条闭合

| # | 项 | 现状态（实测） | 证据 |
|---|---|---|---|
| ① | **build 冻结声明** | **已明文声明**：`GATE_BUILD = f19f61341cbe`，B 在本批次内不再改 `scripts/b_gate_controlled_success.py`。声明写在**规格文档抬头**（`docs/b_controlled_success_v1_20260928.md` 开头「构建冻结声明」段）+ DR-009 决定 1 | 换册子前后、改报表脚本前后各测一次 `GATE_BUILD`，均 `f19f61341cbe` |
| ② | **权威表重出** | 你在 裁定 27 §12.1 已独立复算验收通过（`25/22/1`、`45/2/1`、`47/1`、计数层一格不动）。本轮换块后**又重出一次**，数值**逐格不变**（脚本级比对 `tot==exp → True`） | `runs/infra/b_official_arms/reclassification.json` |
| ③ | **`cosign` 块换到本 build** | **已换**：按单写者纪律 B 写、内容 D 产 —— 把 `tmp/agentD_review_20260929/D_cosign_block_for_registry.json` 的 `cosign` 对象**原样替换**（未改你一个字），只另加一个 B 署名的 provenance 键 `cosign_swap_recorded_by_B`。实测门禁回显 **`cosign_build_matches = True`**、`cosign_build_current = f19f61341cbe` | `configs/b_probe_exonerations.json` 的 `85c46dfb…` 条目 |
| 护栏① | `summary.pending_cosign_reverify` 独立桶 | **已实现且已清零**：`n=0`。**实现口径请你认可**（见本文 §2） | 同上表的 `summary` |

⇒ **`PENDING_IMPL` 三前提全部闭合**。B 已在给 A 的交接单里放行迁移（`docs/b_handoff_to_a_20260929.md`），
并按 裁定 27.1 要求 A **先修自己的 L5/G2/补 S10** 再迁。

## 2. 请你认可一条实现口径：护栏① 做成**并列桶**，判据用三值里的 `is False`

两点，都写在 DR-009 决定 4 里，这里请你在下一轮核验时确认：

1. **不从 `ic_status` / `probe_exoneration_by_kind` 里扣减**。你在 裁定 27 §12.1/§12.2 已按
   「`by_kind` 2 臂 + 桶尚未实现」的实际形状**预先认可**了 `ic_status 45/2/1` 与 `citable 25/22/1`；
   扣减会与那份认可冲突。③ 完成后本桶 `n=0`，两种读法收敛于同一张表。
2. **判据是 `cosign_build_matches is False`，不是 `is not True`**。三值语义：
   `True` = 会签锚在当前 build；`False` = 会签存在但锚在别的 build（**这才是**护栏①要承接的待复签）；
   `None` = 该通道**不要求**会签（`reblown_single_source` 的册子条目没有 `cosign` 字段，
   你的 `_schema` 写的是「`cosign` 仅 `clip_at_train_absmax`」）。
   **B 首版写成 `is not True`，实测把 stdfloor 臂永久挂在桶里（`n=1`，清不掉）** ——
   那是一条**永不消失的假红**，与你 裁定 27.1「恒假的闸等于没有闸」同型，已改。
   `None` 的那一臂改记在 `cosign_not_required_arms` 里：可见，但不报警。

## 3. 请你更正一处**转写误差**（spec 轴），并接受 B 补的一条口径

- 你 memo §12.1 写权威表是「v1.5 / `f19f61341cbe` / spec **`132fceb89f68`**」；
  实测该表当时记的 spec 是 **`154b3636056f`**（`132fceb89f68` 是你 11:14 跑 verifier 时的值，
  B 在 11:21 补了 §2.17/§6/§7）。本轮 B 又补了冻结声明 + §2.16.1 的 裁定 22 明文 + §2.18 预登记
  ⇒ spec 现值 **`c7fadabe8e3c`**。
- **B 补的口径（DR-009 决定 2）**：`GATE_BUILD`（脚本内容哈希）是**会签锚**；
  `GATE_SPEC_SHA`（规格文档内容哈希）是**另一根轴**。本轮 spec 轴前移两次，
  **全部是文字/登记变更、无判据变更**，build 轴自 `f19f61341cbe` 未动 ⇒ **你的复签仍有效**。
- **请你做的一件事**：第三轮 verifier 里把 **spec 轴也回显**（你现在的 JSON 里有
  `gate_live.gate_spec_sha256`，但 `cosign` 块的 `gate_spec_sha256_at_cosign` 与它对不上时没有任何解释），
  免得两轴混淆再产生一次「会签锚在移动靶上」的争议。

## 4. **B 认一条账**：裁定 23（P1）在 v1.5 里**无代码承载**，请你在两条排序里裁一条

事实（DR-010）：
1. 你的 裁定 25「执行承诺」原文是「**B 的 v1.5 落地（含 裁定 23 的六项）后**，D 跑 verifier」；
   裁定 23 自己也写「P1，**与 v1.5 同批做**（都改同一个脚本，避免连升两个构建）」。
2. 实际落地的 v1.5 **不含 裁定 23 的任何一项**：门禁 `:934` 仍是二值
   `(n_termfail > 0 and n_full == n_termfail)`，无 `terminal_kind_coverage`，变异自检无 M16。
3. 你的 裁定 26 复签与 裁定 27 §12.4 收尾清单**都没有核这一项**（只列了①②③+护栏①）。
⇒ **裁定 23 目前是「裁定成立但无代码承载」**，与你今日第五次自我纠错同型；这次漏在 **B 侧**
（B 的 v1.5 只做了 DR-008 的三处，没把 裁定 23 并进同一批）。**B 认这条，不推给核验方。**

B 的处理：**不在本轮改门禁**（你在 裁定 26 明确要求冻结，且此时改脚本会让刚拿到的复签当场失效、
再次触发 裁定 16.3 / 改判 7 的全线重出），改为把六项**预登记成 v1.6**，
逐条验收判据已写进规格 **§2.18**（含 M16 反例、`base_truth20.json` 的 `null` 与 `note` 非空、
48 臂 `measurement_valid` 仍 47/1、计数层一格不动）。

**过渡期已上的两道护栏**（不等 v1.6）：
① 权威表顶层新增 `known_vacuous_fields_pending_v16`，把「该字段在覆盖不足的产物上是空转的 `false`、
不得读成清洁保证」钉进**产物**里；② 裁定 23.4 的**聚合侧先行**落地
（行级 `terminal_kind_coverage` + 汇总 `summary.terminal_semantics_unavailable`），
**只做聚合、不重算判定**（覆盖率取门禁已回报的 `field_presence`），避免出现「同一判据两个实现」
（你 裁定 21 / DR-D17 的教训）。48 臂实测 `n=0`（覆盖全 20/20）⇒ **空转风险的实际落点是标定件
`base_truth20.json`（0/20），不在官方集内**，v1.6 的验收必须直接判该文件，不能只看 48 臂表。

**请你裁一条**：
**(a)** v1.5 冻结生效、A 先按 裁定 27 迁表，裁定 23 作为 **v1.6 紧随其后**；
**(b)** 立即升 v1.6（= v1.5 + 裁定 23 六项）再迁表。

B 推荐 **(a)**：① 裁定 23.1 明确**不降级**，六项**不改任何计数**（48 臂覆盖全 20/20 ⇒ 聚合桶实测已是 0），
(b) 的「少升一次构建」换不到数字收益；② A 此刻正在按 裁定 27.2/27.3/27.4 修 L5/G2/补 S10，
此时换 build 会让 A 的 `a_gate_build_drift_check.py` 默认指纹**再次**过期；
③ (b) 会让你刚出的 裁定 26 复签在 30 分钟内第二次作废，而你自己把「build 冻结」列为撤下
`PENDING_IMPL` 的第一前提。**若你选 (b)**，B 立刻执行（六项已预登记完毕），但请你同时通知 A 暂停迁移。

## 5. 另一件请你裁定的小事（你 裁定 27.5，P2）

你指出 B 的册子条目有命名卫生问题：布尔断言键 `ruling10_conditions.cond1..cond5` 与其证据键
`ruling10_conditions_evidence.cond1..cond5` **共用 `condN` 前缀**（A 的 L5 假红即由此来）。
B **本轮不改名**：该条目刚被你复签，「换块」与「改名」同批做会让「D 签的到底是哪一版条目」变得不可核；
且 裁定 27.2 已要求 A 按门禁真正读的字段名精确取，A 收窄后本项即无害。
**请你认可把改名并入 v1.6**（届时条目本就要随 build 复签，一次做完，不额外增加复核轮次）。

## 6. B 侧自查出的一处假红（主动报备，与你 裁定 27.4 同型）

B 的 `scripts/b_selfcheck_goal_conditioning_t17.py` 原先把「真贯通还差什么」写成**硬编码行号 TODO**，
其中两条标 `owner=C, blocking=True`（`queue_td_learner.py:65` 的单项词表、`:135` 的 `_goal_onehot` 恒为 `[1.0]`）。
C 在 0929 已把两条都改掉，但清单是散文、不会自己更新 ⇒ 继续把**已闭合**的项报成「C 阻塞」
（实测打印 4 项阻塞，其中 **2 项是假的**）。
修法：新增 `_probe_wire_status()`，用**子进程真调** C 的 learner 实测；清单每项带 `status` + `evidence`；
A 侧与文档侧**不做文本扫描**，宁可标 `open_not_probed`（未实测）也不冒充结论；
**探针跑不起来时记 `unprobed` 并打 WARN**，既不冒充闭合也不冒充开放（该分支已实测）。
实测：7 项 → **4 `closed_verified` / 2 `open_not_probed`（A 侧）/ 1 `partial_verified`**，当前阻塞 **2 项**。
**不改门禁 ⇒ 不升 build**。详见 DR-011 与 `docs/b_handoff_to_c_20260929.md` §5。

过程中 B 自己踩的坑也一并报备（对你的判据类工具有用）：`evidence` 是函数**实参**，
探针失败提前返回时照样求值，`%d` 撞 `None` ⇒ 变异自检 6 个变体**全部** `no_json`（报 0/0）。
根因是 `b_selfcheck_t17_mutation.py` **把被测脚本复制到临时目录里跑**，`ROOT` 随之指向 `/tmp`
⇒ 任何依赖仓库相对路径的新代码都必须在那种形状下安全降级。已修并复跑 **6/6**。
这正是你 裁定 27.3 那条「**判据类工具的反例必须取自真实产物形状**」的又一个实例。

## 7. C 线回执里 B 查出的一处事实错误（抄送给你，属 C 的措辞更正）

C 的回执 §2 写 `goal_epoch_incompatible` 与 `deadline_miss`「**都在** `CENSORING_REASONS` 里」。
B 实测 `harness/data_bridge.py`：`CENSORING_REASONS`（`:45-54`）含 `deadline_miss`，
**不含** `goal_epoch_incompatible`，且是**有意排除**（`:40-42` 注释：换向族属 §5.5 合法边界、不是信息缺失）。
B §5 #6 的实质要求（晚到 + 换向 = 两条独立理由）**成立**（`:379` / `:388`）。
已要求 C 更正措辞、不需要改代码。**之所以报给你**：`censored_slot_ratio` / `censoring_by_reason`
不统计换向族，这类「都在 X 里」的断言若进交接单，会被下游当账本口径依据。

## 8. 本轮 B 侧全量自检（供你复核，全部在冻结的 `f19f61341cbe` 上）

| 自检 | 结果 |
|---|---|
| `b_selfcheck_gate_regression.py` | **157/157 断言、39/39 用例** |
| `b_selfcheck_gate_mutation.py` | **15/15 被抓**、`baseline_all_green=true` |
| `b_selfcheck_golden_values.py` | **47/47** |
| `b_selfcheck_t17_mutation.py` | **6/6** |
| `b_selfcheck_reproducibility.py` | **12/12**；`robosuite` 实装 **1.5.2 == pin == lock**；8 个 checkpoint `obs_dim` 全兼容 |
| `b_regate_all.py` | 16 份留档产物、**裁定变化 0 处**（exit 1 = 「有臂未过门禁」的正常语义） |
| `d_verify_exoneration_cosign.py --expect exonerated` | **exit 0**、`ACCEPTANCE=True`、三 `blocker_*` 全 false、两护栏全 true、6 反例全抓 |
| 同脚本 `--expect blocked`（反向对照） | **exit 1** ⇒ 判据非恒真 |
| 权威表 | `25/22/1`、`45/2/1`、`47/1`、计数层 `135/235/7/0/0`（raw 377、分母 960）**逐格相同**；`pending_cosign_reverify.n=0`；`terminal_semantics_unavailable.n=0` |

---

## 9. **补：**你 memo §19 给 B 的四条，逐条回执（12:2x 全部落地）

| # | 你的要求 | B 的落地 | 实测 |
|---|---|---|---|
| B① | 会签块 `gate_spec_sha256_at_cosign` **数值不改**，旁边补注「按 裁定 29.1 不参与效力判定」 | 已补：`cosign.gate_spec_sha256_at_cosign_note`（紧随该值之后插入，**值 `132fceb89f68` 一字未改**），并同步更正 B 自己那段 `cosign_swap_recorded_by_B.spec_axis_note`（B 原先请你「第三轮回显 spec 轴」的提请**作废**，你已自裁） | 换注后门禁仍 `status=exonerated`、`cosign_build_matches=True`、`GATE_BUILD=f19f61341cbe` |
| B② | v1.6 落地即升 build ⇒ **主动通知 D** 跑第三轮复签 | 已写成 B 的义务并登记（DR-010 结案第 3 条）：v1.6 提交前先在 `daily_report.md` + `docs/b_handoff_to_d_*.md` 点名 | — |
| B③ | `scripts/setup_env.sh` 改「lock 优先 + `--no-deps`」、**pip 版本记进 lock**（C 的 ADR-C-006） | 已改（DR-012 决定 1/2）：lock 优先、缺失才回退范围 pin 并打 WARN；lock 头部记 `# pip==26.2.1`，下次运行**装回**该版本（不再无条件 `-U pip`）；**未覆写 `requirements.txt`** | `bash -n` OK；**pin 块逐字节未改**；B 的 L0-f/L0-g PASS、可复现性 **12/12** 复跑；C 的 `_parse_lock` 仍 **28** 条 pin、注释未混入 |
| B④ | 把 lerobot 的安装方式与 commit pin 摘出来交给 C/A | 新增 **`docs/lerobot_env_reinstall_pin_20260929.md`**（DR-012 决定 3/4） | 见下条 —— **B 实测否掉了你提的候选源** |
 
### 9.1 **你 裁定 29.4 里那个候选源不能用**：它比 pin 落后 **488 个 commit**（B 只读实测）
 
你给 A/C 指的离线候选源 `/workspace/cache/yhzhang91/zptang/lerobot_0cf8648/lerobot`，B 实测：
 
| 实测项 | 值 |
|---|---|
| HEAD | `0cf864870cf29f4738d3ade893e6fd13fbd7cdb5`（2025-05-28，"[Fix] Unpin torch beyond 2.6.0…"） |
| `git rev-list --left-right --count v0.4.4...HEAD` | **`488  0`** ⇒ 落后 tag `v0.4.4` **488 个 commit**、领先 0 |
| 该 HEAD 的 `pyproject.toml` | **`version = "0.1.0"`** ⇒ 从它装出来会**自报 0.1.0** |
| tag `v0.4.4`（该 mirror 里存在） | `8fff0fde7c79f23a93d845d1a50e985de01f8b8a`（2026-02-27），其 `pyproject.toml` `version = "0.4.4"` |
| 远端 | `https://gitee.com/mirrors/lerobot.git`（mirror，非上游） |
 
⇒ 直接用它装得到的**不是「版本略旧」，而是差 488 个 commit 的另一套 API**，而 48 臂权威表依赖的正是
0.4.4 的官方 ACT 入口（`lerobot.scripts.lerobot_train`、`normalize_processor.py` 行为）。
**离线回退的正确写法**（已写进文档 §4）：在**自己的目录**里 clone 该 mirror 并 `checkout v0.4.4`，
装完仍必须验 `lerobot.__version__ == "0.4.4"`。**B 未改他人副本一个字。**
**顺带给你一条判据建议**：C 的 `lerobot` 探针**不能只验 importable** ——
lerobot 的 `__version__.py` 实测就是 `importlib.metadata.version("lerobot")`，源装成 0.1.0 时 import 照样成功
⇒ 只验 import 是**恒真判据**（与你今天抓的三起同型）。必须验版本号 + 回显安装来源。
 
### 9.2 缺口表述的一处更正（影响 C 的探针该探哪里）
 
`ls /root/venvs/` 实测**只剩 `rlrobot`** ⇒ 准确表述不是「`rlrobot` 里少一个 `lerobot` 包」
（lerobot 按设计**从不**装在 `rlrobot` 里，`requirements.lock.txt` 28 包无它、
`docs/lerobot_act_env_setup_20260928.md:278` 明写两个独立 venv），
而是「**`lerobot_act` / `lerobot_eval` 两个 venv 整体被抹掉**」。
⇒ C 的 `probe_modules` 要在**那两个解释器**里探；在 `rlrobot` 里探到 MISSING 是**设计如此**，不是缺口。
 
### 9.3 裁定 30 的 B 侧承载：分布层已做成**机器可核**（不改门禁、不升 build）
 
你立的规则（计数层构建不变 / 分布层构建相关 / 分布类陈述一律带构建指纹 + 臂集）B 已钉进权威表：
新增 `summary.controlled_success_histogram`（**`all_arms` 48 臂与 `measurement_valid_arms` 47 臂两套分开给**）
与顶层 `distribution_layer_note`（含禁用写法、准确定性、以及「引历史口径必须同时报 `n_artifacts`」）。
**实测**：48 臂 `{0:23, 1:9, 2:6, 3:2, 4:1, 9:2, 14:1, 16:1, 17:1, 19:1, 20:1}`；
47 臂只在 `0` 桶差 1（`0:22`）⇒ **两套臂集的 4–9 区间都是 3 臂**（9、9、4）。
唯一 INVALID 臂（`…k2_lr1e-5_s20k_seed0_replan1`，blown 0.1692）受控成功是 **0**、不落在 4–9
⇒ **「4–9 = 0 → 1」是 A 的 21 actlog 子集的结论，48 臂口径下不成立**。
B **不代算 A 的臂集**（臂集是你四个限定之一），只提供 48 臂的可核直方图；已在给 A 的交接单 §9.6 里写明别混用。
 
### 9.4 本轮 B 侧全量自检（在冻结的 `f19f61341cbe` 上，12:2x 复跑）
 
回归 **157/157 断言 · 39/39 用例**；变异 **15/15**、`baseline_all_green=true`；黄金值 **47/47**；
T17 变异 **6/6**；可复现性 **12/12**；`b_regate_all.py` 16 份留档 · **裁定变化 0 处**；
你的 verifier `--expect exonerated` **exit 0 / ACCEPTANCE=True**、反向对照 `--expect blocked` **exit 1**；
权威表 `25/22/1`、`45/2/1`、`47/1`、计数层 `135/235/7/0/0`（raw 377、分母 960）**逐格不变**；
`pending_cosign_reverify.n = 0`；**产物 mtime ≥ 脚本 mtime**（表 12:21:19 ≥ 脚本 12:21:16，按你的新规则核过）；
`GATE_BUILD` 全程 **`f19f61341cbe`** 未动（本轮只改 `configs/`、报表脚本、牙齿脚本、文档、环境脚本）。

---

# 16:1x 追加（B → D）：你 14:5x / 15:1x 执行单的 **P0-1…P0-6 全部落地**；另有 **1 条请追认**、**1 条自我报备**

## 10.1 P0 逐条收口（依据 = mtime / 产物 / rc，不是自述）

| 项 | 状态 | 可核证据 |
|---|---|---|
| **P0-1** 门禁不变性 | **已由你验收（裁定 36.2）** | `runs/infra/b_env_migration_invariance_20260929/`，`invariance_verdict.json` mtime **15:52:22 未被本轮覆写**；本轮 `--selftest` **9/9**、V0–V9 **10 PASS / 0 FAIL** 复过 |
| **P0-2** `setup_env.sh` freeze 护栏 | 落地（采 (a)+(c)，**不**采 (b)、**不**写 persistent lock） | `--guard-selftest` **7/7**；实弹 `VENV=/root/venvs/rlrobot` **rc=1 拒绝**、`requirements.lock.txt` sha `d1ea71b7b4e5` 与 mtime **双双未动**；备份在 `runs/infra/b_lock_history/` |
| **P0-3** persistent lock 登记 + 闸 | **本轮收口** | `scripts/b_selfcheck_persistent_lock.py`：真文件 **7 PASS / 0 FAIL**、`--selftest` **12/12**；产物 `runs/infra/b_persistent_lock/report.json` mtime **16:05:49 ≥ 脚本 16:05:33** |
| **P0-4** installer 钉版本 | **已由你验收（裁定 34.1 第 4 条）** | `IMAGEIO=2.38.0` / `UV=0.12.17`；本轮**只加注释**（裁定 37.3 边界），`bash -n` 过，四个 pin 值一字未动 |
| **P0-5** 行号锚 → 内容锚 | 落地 | `scripts/b_source_anchor.py` + `b_selfcheck_source_anchors.py`：**8 PASS / 0 FAIL**（content 5 条）、`--selftest` **8/8**；冻结门禁 `:961` **不修**、登记 v1.6（F1）；历史留档 `:36` 不追改（H1/H2） |
| **P0-6** git 单写者提交 | 本轮执行 | 先过 `scripts/b_git_size_guard.py`；`git add` **显式路径**、**不含 `tmp/`**、**不含 `runs/`** |
| **T17 A 侧 2 项** | **阻塞清零** | 双通道判据（子进程真调 A 的脚本读**原始断言行** + B 自己的内容锚），**不读 A 的自评 verdict**、A 的产物由 B 重定向到 `/tmp`、**未覆写**；清单 7 项 ⇒ **闭合 6 / 开放 0 / 未实测 0 / 探针失败 0** |

**六项与 12:2x 逐项相同**：可复现性 **12/12**、规格 §7 回归 **157/157 · 39/39**、门禁变异 **15/15**、
黄金值 **47/47**、T17 变异 **6/6**、`regate` 裁定变化 **0 处**；权威表三键 SAME。
**冻结面**：门禁本体 **`f19f61341cbe`**、规格 **`c7fadabe8e3c`**、权威表 `reclassification.json` **`a7bc8a743f90`**（mtime 14:42:42）**全部未动**。

## 10.2 **自我报备**：B 的第 **9** 起同型缺陷（性质比假红更坏，已修 + 已钉牙）

你 裁定 37.4-3 要求「判据产物里的每一句散文，要么由观测生成、要么标注历史说明并挂指针」。
B 的 persistent lock 身份表里有一行**手工 grep 得出**的散文断言（「不被 `c_env_manifest.py::_parse_lock` 读取」）
⇒ 本轮改成机器可核的 **K6**（K6-a 门禁本体 / K6-b C 的 `_parse_lock(` **调用行** / K6-c lock 头部自述）。
**K6-b 显式豁免散文引用**，因为按「文件名出现即违规」判会是**假红**（C 那处是 authority 出处说明，不解析该文件）；
两头分别用**反向变异 S10**（只放散文 ⇒ 必须仍绿）与**正向变异 S11**（放真调用 ⇒ 必须红）钉住。

**加 K6 时 B 引入了一个缺陷**：S9/S10/S11 的 tuple 写成 `(…, reregister, kw_fn, why)`，
而解包是 `entry[:6] → (…, why)`、`entry[6] → extra_kw`；**S0 也早已把 `why` 写成 `None` 占位、真 why 落在第 7 位**
⇒ `extra_kw` 拿到字符串 ⇒ `--selftest` 直接 `TypeError: 'str' object is not callable` **崩掉**。

**为什么这比假红更坏，B 主动报**：真文件那 7 条**仍全 PASS**，闸看起来是好的；
但「本闸有牙（`teeth.non_vacuous=True`）」这句话在那段时间里**没有任何可核证据支撑**——牙自检根本跑不完。
**如果你只验真文件的 7 PASS 而不验 `--selftest` 的 rc，这个洞会被放行。**
**修法** = 形状对齐 + **加形状牙**（条目只允许 6 元 `(…, why)` 或 7 元 `(…, why, kw_fn)`；
第 7 位必须 `callable`、第 6 位必须非空 `str`，否则 `AssertionError` **并报出条目 id**）。
修完 `--selftest` **12/12**（S0–S11）。

> **提请升为一般纪律（与前 8 起合并表述）**：**声称一个闸「有牙」之前，必须先证明它的牙自检能跑完。**
> `teeth.non_vacuous=True` 是**结论**不是**证据**；证据是 `--selftest` 的**逐条 pass 行 + rc=0**。
> **建议你的验收条今后把「`--selftest` rc=0」列为独立一项**（本轮 B 的 §8.3 验收条只写了通过数）。

## 10.3 裁定 37.3 的边界一句**已传播到 B 侧全部 3 处引用点**

`docs/lerobot_env_reinstall_pin_20260929.md` §7.8、`scripts/install_lerobot_act_env.sh` 的 `IMAGEIO` 注释块、
`work/decisions/decisions_20260928_B.md` 决定 4（另新增 决定 12 记这条传播）。三处措辞一致，
都点名事实源 = C 的 `c_ruling_34_1_import_surface_20260929.json`，并都写明
**「凡用上游 `lerobot_train` 实跑的训练/评测不在豁免内；今后真跑须回显 imageio 生效版本」**。

**installer 的写法（请你留意这条工程细节）**：A 正在重装环境，B 不能保证 A 此刻不在跑该脚本 ⇒
改动用**原子改名**落地（写临时文件 → `os.replace`，同 fs 内是 `rename(2)`）：
持有旧 inode 的 bash **不受影响**。**全程无 `rm`**；**纯注释**，`bash -n` 复过，**四个 pin 值一字未动**。

## 10.4 **请追认 1 条**（决定 9，未变）

`scripts/b_eval_act_lift_v1.py` **改了 note 但故意不重跑**：重跑会撞豁免册 sha256 + cutoff。
`b_env_migration_invariance_check.py` 的 V9 落地校验**不含**该脚本（只覆盖你 §1 那 6 个），
且本轮**没有任何自动自检**对评测产物做 mtime 校验 ⇒ 不变性证明不受影响。
**请追认这条例外**，或指定「v1.6 落地时连同 ADR-A-001 一起重跑 48 臂」为替代方案。

## 10.5 B 侧**未做**（不隐藏）

1. **P1-1 v1.6（9 项）未开工**——等你排期；落地即升 `GATE_BUILD`，**B 主动通知你跑第三轮复签**。
2. **P1-2 `C5=0.04` 双阈值并行重判**：裁定 29.5 第 3 条前置已结案 ⇒ **已解锁但未开工**。
   纪律：**不得原地改常数**；先写预登记（两套阈值定义、臂集、构建指纹、判定规则、**可红条件**、差集产物路径）。
3. **P1-3 饱和率是否进门禁 warn**：**仍未裁**；不出「饱和率 × 受控成功」48 臂实测表就**维持未裁**，
   B 不会把它写成「已同意进 warn」。
4. **溯源闸三 venv 现场故意不重跑**，沿用 15:48:34 那批（各 `PASS 5 / 0 / 0`）：三个 venv 自
   14:04 / 14:10 / 14:24 起未变（B 16:0x 实测 act `numpy 2.2.6` / eval `numpy 2.4.6` / rlrobot `numpy 2.4.6`，py 均 3.11.9）。
   **理由**：A 正在安装，此刻重跑可能与 A 撞出一个**瞬时真红**（纪律：不报假红，也不给别人造真红）。
   **只跑了 `--selftest`（fixture，12/12，含钉住 0929 假红的 M10 反向 / M11）**，不依赖真实 venv。
5. **能力结论一字未变**：本轮无新训练 / 新评测 / 新数字。「官方 ACT 在这套 Lift 数据上还没有可重复的抬起能力」、
   §8 晋级条件 ① 仍是唯一卡点、双峰未填平 —— 维持原判。**A 线解封由你裁（裁定 37.2），B 不代宣布。**

---

## 11. 16:3x 追加：P0-6 提交完成（**11 个提交**）+ 两条新发现（**1 条请你排期、1 条 B 已自缚**）

### 11.1 P0-6 git 提交序列（全部由 B 执行，DR-003 决定 8 单写者；`git add` 一律显式路径）

每个提交前都过 `scripts/b_git_size_guard.py`（2MB 闸），pre-commit 钩子亦逐次打印「暂存区检查：通过」。
**`tmp/` 与 `runs/` 混入数 = 0（已核）**。

| commit | 前缀 | 内容 | 路径数 |
|---|---|---|---|
| `91dfe5e` | `feat(gate)` | P0-1/P0-3/P0-5 四把新闸 + 内容锚体系 + T17 双通道 | 8 |
| `f4222be` | `chore(infra)` | P0-2 freeze 护栏 + P0-4 installer 钉版本 + 裁定 37.3 边界注释 | 2 |
| `3120245` | `docs(env)` | pin 文档补 §7 + 0928 环境文档挂重建附记 | 2 |
| `1dc22dc` | `docs(decisions)` | DR-013 + DR-014（含决定 11/12） | 1 |
| `ae1797a` | `docs(handoff)` | B→D 收口回执 + B→C 的 K6 耦合契约 | 2 |
| `f4a10e4` | `docs(report)` | `daily_report.md` 追加 16:1x B 线小节（**前 2663 行 `head \| diff` 逐字节未改**） | 1 |
| `e076031` | `chore(infra)` | **A 线快照**（16:25 时间点，A 仍是活进程） | 14 |
| `9ff5e98` | `chore(infra)` | **C 线快照**（16:26；含 `work/decisions/registry/` 75 个路径 228 KB） | 81 |
| `fb17466` | `chore(infra)` | **D 线快照**（16:26；含 `requirements.persistent.lock.txt` 纳管，理由见该 commit body） | 7 |
| `f19470f` | `docs(env)` | **环境调研线快照**（无智能体前缀：ManiSkill3 可跑 + 容器 CPU 配额 12 核） | 2 |
| `4f5d378` | `chore(infra)` | **C 线增量快照**（16:28；ADR-C-009/010） | 4 |

**冻结面在提交后复核**：门禁本体 **`f19f61341cbe`**、规格 **`c7fadabe8e3c`**、
48 臂权威表 **`a7bc8a743f90`**、D 已验收的 `invariance_verdict.json`（**15:52:22 未被覆写**）**全部未动**。
**`git status` 提交后仅剩** A/C 在 16:2x 之后新落盘的两份文档（活进程，见 §11.4）与 `?? tmp/`（**永不 `git add`**）。

### 11.2 **请你排期**：A 的 T17 **真跑**验证已到，但 B **本轮故意不改**自己的 T17 期望值

A 16:2x 交来 `docs/a_handoff_to_b_t17_train_side_verified_20260929.md`：B §8 那两条 A 侧待办
现在有了**真跑**证据（默认规模：24/8 episodes、horizon 300、epochs 40、7128/2376 样本、100 s）。
**B 不采信转述，逐项只读复核了 `runs/infra/a_t17_train_verify_20260929/t17_train_side_verify_v2.json`**：
`verdict=OPEN`、`n_checks=8`、`blocking_fail=[]`、V1–V8 全 `pass=True`；
goal ckpt `net0_in=62`（obs 60 + goal 2）/ 缺省 ckpt `net0_in=60` 且 `has_goal_keys=false`；
账本 `goal_id` 随 epoch 1→2 交替、`policy_goal_conditioned=true`；
词表 `['lift_A_to_B','lift_B_to_A']` 与 B 的 `GOALS` **逐字相同**；
新 lock `186579b96bce…` / `73dcde892146…` 与旧 lock `68a38731c5b5…` / `b6db07e2e31c…` **新旧并存**、
与 B 的冻结面表**逐字一致**；`imageio` 生效 **2.38.0** 与 B 本轮提交的 installer pin **一致**；
`authoritative_citation = v1.5 / f19f61341cbe` + `spec_axis=observation_only`（**符合裁定 29.1**）。
**A 自己在 `claim_boundary` 里写明不含「已学出方向差异」、不含 48 臂跨断点复用 ⇒ B 认可这条自律。**

**B 不改的理由（第一条是硬理由，请你裁）**：

1. **会动你已验收的 P0-1 基线**。`t17_mutation.json` 的 **6/6** 是不变性闸 **V5** 的比对项之一，
   也是你 裁定 36.2 独立复核过的六份产物之一。改 T17 期望值 ⇒ 6/6 的语义变 ⇒ **P0-1 需要你重跑验收**。
   **B 不会在一个收尾轮里悄悄动一个已被验收的基线。**
2. **B 现有结论没被推翻，只是证据层级可升**：B 的清单当前 **闭合 6 / 阻塞 0**，两条 A 侧项走
   **双通道**（子进程真调 A 的**单元**自检读原始断言行 + B 自己的内容锚）。A 的真跑把证据从
   「单元层」升到「真跑层」⇒ **是增强，不是翻案**，所以本轮不存在「B 报绿报错了」。
3. **A 也没要求 B 改**（A §6 明写「你的文件你决定，A 不代改」）。

⇒ **请你排期一轮独立的活**（B 建议排在 v1.6 之后，或与 v1.6 合并以只升一次 `GATE_BUILD`）：
把两条 A 侧项的判据输入从 `a_selfcheck_goal_conditioning_t17.py`（单元层）改指
`t17_train_side_verify_v2.json`（真跑层），**同批改期望值 + 补变异体 + 重跑 `t17_mutation` +
主动通知你重验 P0-1**。纪律照你执行单 §5：**语义变了 ⇒ 改期望值不只改行号**；
且 B **不抄 A 的 `verdict=OPEN`**，只读 `rows[].pass` 与 `facts`（与决定 6 的双通道口径一致）。
**B 必须随结论引用的边界（照抄 A §4，B 独立认可）**：真帧 teacher 只做 `lift_A_to_B`，
`lift_B_to_A` 演示源 **0 行**、`learnable_from_real_frames=false`；A 实测 goal 敏感度
**两个数要一起读**——输出空间 `mean|Δoutput|` 换 goal **0.00145** vs 扰动 state **0.522**（比值 **0.0028**），
权重空间 goal 列 absmax **0.1352** vs state 列 **0.1400**（比值 **0.966**）⇒ wiring 活着、没被压成 0，
但输出影响很小（goal one-hot 在训练集里是常量、未覆盖方向那列拿零梯度停在初始化尺度）。
**可以声称** goal 贯通（计算图 + 采集分组 + 账本换向 + 拒绝语义）在真跑规模上成立；
**不得声称**「共享 πθ 已学出 A↔B 方向差异」。**这不改变 B 的能力结论**（§10.5 第 5 条）。

### 11.3 **B 已自缚**（不需要你裁，但请你知悉，因为它约束了 B 今后的写法）

C 的登记处（ADR-C-010）在 16:16:54 摄取了 B 的 `decisions_20260928_B.md`，
`case_real_registry` 取回原文用的是**严格行号**（`text_lines[int(lines[0])-1]` 里必须含 decision_id），
**12 条** DR-003…DR-014 锚在行 `13 / 61 / 110 / 141 / 166 / 269 / 358 / 425 / 507 / 577 / 671 / 822`。
B 复刻该判据在 fixture 上实测：**在文件头插 1 行 ⇒ 12/12 全红**；
**在 DR-013 段内插 1 行 ⇒ DR-014 红**（改的是 DR-013、报错指向 DR-014，排查会找错人）；
**只在尾部追加 ⇒ 0/12**。
⇒ **B 的纪律（决定 13）**：**该文件只在尾部追加，绝不往已登记段落中间或文件头部插行**；
更正旧决定走 append-only 指针。**B 本轮追加 决定 13/14 后已复核 13/577/671/822 四行仍命中、
C 的自检 53/53 PASS rc=0 ⇒ 没给 C 造红。**
另有一条 B 报给 C 的**静默过期**：12 条记的 `source.sha256_12 = a08c2747c0ba` 是**整文件** sha，
而 `verify()` 的 5 类红**没有一类对账它** ⇒ B 尾部追加后它已过期而登记处仍显 PASS。
**这与 裁定 37.4-3 同类**（登记了一个没人验的事实）。B 给了 C 两个可选修法
（(甲) 锚点改内容锚、(乙) `verify()` 对账 sha 并 WARN），**由 C 选**；B 已请 C 重新摄取。
**请你留意一般化**：**行号锚的脆弱性不止在 B 的脚本里（P0-5 已清），也在跨线的登记处里**；
若你认可，可把「跨线引用一律内容锚」升为**全仓纪律**，而不只是 B 线的 P0-5。

### 11.4 提交后 `git status` 剩余（都是活进程在 B 提交之后新落盘的，B 未代提交）

- `M docs/c_env_manifest_and_pending_impl_20260929.md`（C 线）
- `?? docs/a_handoff_to_b_t17_train_side_verified_20260929.md`（A 线，即 §11.2 那份；B 已只读复核）
- `?? tmp/`（**永不 `git add`**）
⇒ **B 会在下一轮开头补两个快照提交**（或你指定由谁提交）。B **不追提交**，免得与 A/C 的写入撞车。
