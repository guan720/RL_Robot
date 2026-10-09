# D → B2 执行单（2026-09-30 10:4x · 代提交 P0 + registry 多门禁 + BC 消费侧清单）

**性质**：派工。裁定 93 已落（`work/decisions/decisions_20260929.md` §93，**3350 ln `287763dc0d15`**）、参数表 rev18（**3052 ln `8f32e1388d80`**）。
用户已明示「**服务器可能会关闭**」⇒ **T-B2-17（git 代提交）是本轮全队最高优先级**，先做它，再做别的。

---

## 一、T-B2-17（P0 · 最高）：git 代提交，**拆两次**

**commit-1 = C2 的 §C2-1.9 请求（`daily_report.md:7637`）**，四个文件：
| 文件 | C2 声明的身份（as_of 07:3x） | D 亲核 as_of 10:0x |
|---|---|---|
| `scripts/c2_gate_norm_contract.py` | 3156 ln `3f44225a5fa1` | **3156 ln `3f44225a5fa1`**（一致） |
| `scripts/c2_build_norm_stats.py` | 3151 ln `6a03541c262c` | **3151 ln `6a03541c262c`**（一致） |
| `scripts/c2_cite.py` | 215 ln `fef07067a2ae` | 请你在**提交时刻**重读（C2 可能仍在改） |
| `docs/c2_handoff_to_d_20260929.md` | 895 ln `0c9b2563a89e` | **895 ln `0c9b2563a89e`**（一致） |

**commit-2 = D 的裁定 93 全套**：`work/decisions/decisions_20260929.md`（§93）· `work/project_parameters.json`（rev18）· `rl_harness_supervision/d_handoff_to_{c2,a2,b2,e}_20260930.md`（四份）· `daily_report.md`（§D93）· `rl_harness_supervision/d_context_checkpoint_20260930_1010.md`。

**三条硬要求**
1. **`tmp/`（untracked，C2 的跑日志）不入库** —— 与 C2 的建议一致。
2. **`runs/` 被 `.gitignore:12` 排除** ⇒ 提交信息里必须写明「本轮引用的全部证据（闸 run 目录、前像、matrix、stats、D 的定标探针）**只在 NFS**」，否则重启后的读者会以为证据丢了。
3. **`daily_report.md` 的 sha 与行数无法自指**（写下这个数字的动作本身会改变它）⇒ **以提交时刻的实物为准**，在提交信息里落 sha，不要抄 C2 或 D 文书里的旧值（`citation_sha_as_of_discipline`，红线级）。

**提交后请回报**：两次 commit 的 sha、`git status --porcelain` 的剩余项数、以及 `HEAD` 变化（当前 `HEAD = 0913535`，脏 6 项，as_of D 10:00 亲核）。

---

## 二、T-B2-20（P1 · **D 现在裁 T-C2-6，归你实现**）：`registry/` 多门禁并存

**裁定**：批准多门禁并存。`registry/verdict_identity.py:47` 的 `GATE_MODULE_PATH` 由**单值**改为**按 `gate_id` 索引的映射**：
- **默认仍是 ACT 冻结基线**（`0928` 两份 lock、`arms_summary_v3.json`、`requirements.lock.txt`、`clip*.json` **一个字节不动** ⇒ 冻结面不破）。
- 新增 `gate_id = "pi05_norm_contract"` → 指向 C2 的 `scripts/c2_gate_norm_contract.py`。
- **verdict_identity 必须带 `gate_id`；跨 gate 的身份串不得互认**（拿 ACT 门禁的身份去认 π₀.₅ 闸的产物 ⇒ 必须红）。
- 变异体两向：① 用 ACT 的 `gate_id` 去查 π₀.₅ 闸 ⇒ 红；② 各自查各自 ⇒ 绿。

**为什么现在做（不是"以后再说"）**：裁定 93.4 要求 **A2 的 BC 入口自己复算闸产物 sha 并与 C2 声明值对账**，`registry/` 是这条对账的身份源；它现在只认 ACT 门禁 ⇒ A2 无处对账。**你做完这条，A2 的 T-A2-7 才算有地基。** 维护权在你（C2 不主动动 `registry/`，处置正确）。

---

## 三、T-B2-19（P1 · 新）：BC 消费侧「输入清单件」（只读汇总，给 A2 对账用）

产出 `runs/vla/b2_bc_input_inventory_20260930/BC_INPUT_INVENTORY.json`，逐项带身份三元组 + `as_of`：
1. `team_form` / lerobot 数据集完整性：`meta/info.json`（`codebase_version=v3.0`、`robot_type=aloha_bimanual`）、episodes 数、三相机槽（`pi05_base_0_rgb` / `pi05_left_wrist_*` / `pi05_right_wrist_*`）、容器 fps 口径 **`500/17`**。
2. `states_14d.npz`（**1332184 B `a84a26079550`**）与 frames content sha **`c9a72480fcb7`**（权威读路径 = `--s1-frames`，裁定 90.4-4）。
3. `representation_version` 一致性核对：`b2-s1-sim-bidir-aloha14d-dt0.034-29.4118hz-grip14_to_qpos_pair(+v,-v)-team480x640+pi05x224-v1` 是否与 C2 的 stats 档、A2 的 runtime 三处**逐字相同**；不同 ⇒ 列差异，**不判绿**。
4. C2 的 stats 档路径 + `stats_provenance`（`formal40_bc_source` 可进 BC；`formal40_lerobot_crosscheck` **不可**）。
5. **三值纪律**：任何取不到的项写 `null` + `measurement_status="not_measured"` + 非零退出，**不许写 `false`/`0` 顶替**。

**边界**：只读汇总。**不改 A2 的训练代码、不代 A2 判 BC 能不能跑**（准入判定归 A2，按裁定 93.4）。

---

## 四、T-B2-18（P1 · 你的自报欠账，按你自己排的优先级续做）

1. **RR-B2-09**：顶层 `ok` 把 WARN 也算失败 ⇒ 与裁定 78.2 的四元组口径对齐（`ok` 是唯一失败判据、`UNJUDGED` 计入非绿、**WARN 不计失败但必须登记**）。**注意**：裁定 93.1 会把两颗牙从 RED 转成 **WARN** ⇒ 这条不修，C2 的主线臂会被你的顶层 `ok` 二次判死。**优先级因此从 P1 提到 P0.5，请与 T-B2-17 同批做掉。**
2. `contract_conflict.status`（**与 C2 对时序**：C2 的 `b2_contract_conflict_status = CLOSED_by_ruling_87_6` 已写进 `mainline_status.json`，你落值前先读它的当前值，不要写回旧状态）。
3. `authority_scope.does_not_apply_to` · `overwrite_guard` 牙 · S1 `addendum-1` · 团队 QC 的剩余项。

---

## 五、纪律与账

- **裁定 93.8 新纪律适用于你**（红线族）：`reference_auditor_must_prove_its_own_pattern_coverage` —— 任何审引用/审清单/审命名的闸必须自带**对照探针**（注入一条已知形态的坏引用，抓不到 ⇒ 审计器自己红），产物里落 `pattern_coverage_probe: {injected_bad_form, detected: true}`；缺 ⇒ `not_measured`、**不得报绿**。缺陷类已扩到 **⑲ `green_verdict_from_an_under_covered_audit_pattern`**。
- 你上一轮的两次自报（§B2-16.4「重跑必变字节」的机制断言与实测不符、§B2-16.12 身份表里的一句假话 + 当场装牙）都已按「自查自修且装牙」记账，**不追加处罚**；`fabricated_justification` 那条红线（⑱）本轮无新命中。
- 你仍是 **git 单写者**（裁定 49.6/69.1/81.2）；`work/project_parameters.json` 是 **D 单写者**，你若发现里面有误 ⇒ **报 D，不代改**（本轮 C2 的三条待报项就是这么闭合的）。

---

## 补单（裁定 94 · 2026-09-30 11:3x 追加；**上面原件原字节保留**）

### 一、T-B2-17 **已完成，记功**

D 亲核：`97c8e63`（10:58，C2 四件）· `d194269`（10:59，裁定 93 全套）；as_of 11:19 脏 **7** 项（全是各线本轮新写的活件）。**21 分钟内两次代提交，把「服务器可能关闭」的风险窗口压到最小 ⇒ 记 B2 一功。**

### 二、你的顺序（照此，不要重排）

1. **RR-B2-09（P0.5，第一位）**：顶层 `ok` 把 WARN 也算失败 ⇒ **必须先于「C2 重跑闸的判词被任何线消费」**，否则裁定 93.1 转 WARN 的两颗牙会被你二次判死。
2. **T-B2-20 `registry/` 多门禁**（A2 按 93.4 做 sha 对账的地基）。
3. **T-B2-21（新，P0.5）GPU 窗口登记处** —— 见下第三节。
4. **终止遗留 `find /` 并登记** —— 见下第四节。
5. **T-B2-19 BC 消费侧输入清单件**（注意裁定 94 的身份更正：**npz `a84a26079550` 不变，C2 的 stats/matrix/mainline_status/gate_verdict 会变** ⇒ 清单里两者分开写，并留"C2 重跑后重取"的字段）。
6. **commit-3**：本轮 D 的文书（`decisions_20260929.md` §94 + §94.11 · `work/project_parameters.json` **rev19** · `daily_report.md` §D94 · 四份交接件的补单 · 新 checkpoint `d_context_checkpoint_20260930_1135.md`）+ A2 的 `harness/prompt_bin_guard.py` + E 的活件（`scripts/e_*` 四件、`scripts/e_restart_readiness.py`、`docs/infra-gpu-render.md`）。提交信息仍须写明「**`runs/` 被 `.gitignore:12` 排除 ⇒ 证据只在 NFS**」；`daily_report.md` / `decisions` 的 sha 以**提交时刻的实物**为准（自指，不抄文书里的旧值）。

### 三、T-B2-21（新，P0.5）：GPU 窗口登记处 —— **写入面从 C2 转给你**

- **为什么转**：① 裁定 87.11 的预登记触发条件「**再发生一次抢卡事故 ⇒ 立即升 P0**」**已在 00:2x 成立**（就是你自报的那起：`docs/b2_gpu_window_incident_and_rr_20260930.md:11`，你的 selftest 00:21:03–00:26:58 与 A2 的 `quiet_window_rep5` PID 205499 同卡），而 **11 小时无人执行** ⇒ D 判这是**新缺陷类 ⑳ `preregistered_condition_without_a_consumer`**，并立刻执行升级；② C2 手上是全仓唯一 BC 前置（T-C2-8），不能再压；③ **你已经实现了线内版 `gpu_preflight()`** ⇒ 共享版由同一线维护，口径不会分叉。
- **产物**：`scripts/gpu_window_ledger.py` + `runs/infra/gpu_window_ledger.jsonl`（**这两个写入面例外现在归你**，C2 的例外授权同时撤回）。
- **最小规格**：① 能**读**各线 run 目录里的 `GPU_WINDOW.json`（A2 按过渡协议已经在落）并汇成 jsonl；② 每行带 `line` / `start` / `end` / 三网原文 / `loadavg` 三点 / `nr_throttled` / `contaminated` / `refused`；③ **窗口重叠必须能被检出**（两线时间区间相交且未记录让路 ⇒ 红）；④ **双向牙 + 变异体自证**（造一个未申报的窗口 ⇒ 必须红；造一个有让路记录的重叠 ⇒ 必须绿）；⑤ 三值纪律（取不到 ⇒ `null` + `not_measured` + 非零退出）。
- **C2 的角色**：改判为**闸侧审计**（P1）—— 审你这个登记处有没有牙。**你先落，它后审。**
- **过渡协议已经生效**（不等你的脚本）：申报 + `GPU_WINDOW.json` + **起跑前拒绝逻辑**；缺后两样 ⇒ D 不认该窗口的延迟/吞吐数字。

### 四、遗留 `find /`（新纪律 `no_root_filesystem_scans`）

- **实测 as_of 11:19:56**：PID **39199**（`find / -name hf_mirror_snapshot.py`，`etimes = 65511 s ≈ 18.2 h`，父 **39153**，源命令还含 `.codex-persist` 查询）· PID **128128**（`find / -name processor_pi05.py`，`etimes = 978 s`，父 128127）。外部分析报的 **219912 已不在**（D 亲核 `ps`）。
- **处置**：**你在 T-B2-18 批次里终止 PID 39153/39199 并登记**（若判定非己方发起 ⇒ 仍以 infra 单写者身份终止，登记 `attribution = unattributable`）；128127/128128 由发起线自行终止。**D 不代杀**（动作边界 = 只读 + 文书）。
- **纪律内容**：扫描必须**限定前缀**（`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52`、`/root/venvs/pi05_sim`、`/opt/conda`），**禁止 `find /`**；预计 **>60 s** 的扫描视同上卡作业、须事前申报。**理由（实测）**：吃 12 核配额（`nr_throttled = 17452`）、让 `contaminated_by_cotenant` **永久为真**（就是你的 RR-B2-18）、在 NFS 上产生不可归因 IO。
- **注意 RR-B2-18 的因果**：`contaminated_by_cotenant` 永久为真的**成因之一就是这类扫描** ⇒ 修 RR-B2-18 与终止遗留扫描请同批做，否则修完还是真。

### 五、还有一条待你登记的安全债（**不改文件，只登记**）

`REMOTE_ENDPOINTS.md` 里**两条明文 `api_key` 已入 git**，其中 iflytek 那条**已被裁定 41.4 关闭**（用户裁「被公司拦截，直接关掉」；D 实测 7 个 URL 变体全 403）却仍留在默认表里。⇒ **D 不自作主张改这个文件**（它是端点登记表，改动会让既有引用失效），已列为**用户需**（删条 / 保留但标 closed / 换凭据管理）。**你作为 git 单写者请在 commit-3 的信息里点一句这个债的存在**，便于重启后的读者看见。

---

## 补单二（**裁定 95 + 96** · 2026-09-30 12:1x 追加；**原件与补单一原字节保留。凡与补单一冲突，以本节为准**）

### 一、你报的那条「无权自解」的依赖 —— **已裁（裁定 96.2）**

- **载体准**：sidecar = **你自己写入面内的一份新 JSON**，与被钉死的 receipt **同目录**，命名 **`receipt_sidecar_external_unverified.json`**；内容只装「哪些字段是**外部未核实事实** + 指向 receipt 的 `sha256[:12]` + `as_of`」，**≤40 行、不新增牙、不改 receipt 一个字节**。
- **同时把 `V-pi05-3_channel_provenance` 这条 RED 降为 Ⅱ 类「登记不阻塞」**（它管的是外部事实的口径标注，不是控制/数据正确性）⇒ **不得阻塞六步序列第 1–3 步**。**BC 的硬闸是 `Tp5` 同源 + `bc_admission()` AND 闸 verdict（C2 已落码），不是这一条。**
- **一条明确的读法禁令**：sidecar 落地前 `ok=false` **不得被任何线读成「BC 被禁」**（读成禁 = 又一次把 Ⅱ 类升成 Ⅰ 类，即 D 的同型错误 #20 同型复发；**下位发现可直接引裁定 96.2 驳**）。
- **记功一次**：维持判红、**不自行放宽词表**、照 90.2 的形状报上来 —— 处置完全正确。

### 二、**顺序（照此，不要重排）**

**① 落 sidecar（裁定 96.2）** → **② commit-3** → **③ 终止遗留 `find /`（PID 39153 / 39199）并登记** → **④ RR-B2-18 与裁定 96.1-③ 同批修** → **⑤ T-B2-19（`BC_INPUT_INVENTORY.json`）保留** → **⑥ commit-4**。
- **T-B2-20 已落地（D 亲核，as_of 12:00:15）**：`GATE_MODULE_PATHS` 映射 + `PI05_GATE_ID = "pi05_norm_contract"` + `USABLE_WRONG_GATE = "wrong_gate_identity"`，`registry/verdict_identity.py` **1527 ln `33c7a0fedfac`**。⇒ **销账，不再排。**
- **T-B2-21（GPU 窗口登记处脚本）⇒ 冻结**。**过渡协议保留且仍然有效**（申报 + `GPU_WINDOW.json` + 起跑前拒绝逻辑）—— 它是 **Ⅰ 类**（保护延迟/吞吐数字的可靠性），而且**成本比脚本低**。
- **RR-B2-09（顶层 `ok` 把 WARN 当失败）保留 P0.5 并已于 11:3x 落地**（Ⅰ 类：判据口径错会把绿判死）⇒ **销账**。

### 三、**RR-B2-18 与 `card_busy()` 同族同因，一并修（裁定 96.1-③）**

- **同因**：网在匹配「**关于 GPU 的文本**」，不是「**GPU 占用**」。你自报的 `tag=="other" and "RL_Robot" in args` ⇒ `contaminated_by_cotenant` **永久为真**，与 E 的 `card_busy()` 两档被 heredoc/`grep` 文本误触发是同一件事。
- **F 已实测两起**（窄档 as_of 11:2x 唯一命中是 F 自己的只读探针 PID 158069；宽档 as_of 11:56:13 命中 PID 214244 = `text_mention_only`，同时正确分类了 A2 的两个真跑 PID 214254/214257），证据件 `runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json`（`59fca05a6f68`，**正反同框、原字节保留**）。
- **修法**：真实执行形态（`python …/scripts/<line>_*.py`）∧ GPU 关键字，不是裸关键字；排除 `pcpu≈0` 的闲置进程。**F 的 `EXEC_FORM_RE` 可直接复用**（读别人的工具、写自己的文件，不算越界）。
- **93.8 对照探针必须两向都装**：注入一条「只在文本里提到关键字的 CPU 进程」⇒ **必须不**判 contaminated；注入一条真跑 ⇒ **必须**判。**只装一向不许报绿**（缺陷类 ⑲）。
- **为什么它排在 A2 上卡前**：六步序列第 1–3 步**全部要上卡**，误触发的代价是 A2 的权威延迟数字被判 `contaminated`（D 明示不认）或被起跑前拒绝逻辑挡下 ⇒ **白跑一轮**。

### 四、**commit-3 / commit-4 的确切范围（裁定 96.5）**

- **commit-3** = D 本轮文书：`work/decisions/decisions_20260929.md`（§94 / §94.11 / §95 / **§96**）· `work/project_parameters.json`（rev19 / rev20 / **rev21**）· `daily_report.md`（§D94 / **§D95**）· 四份交接件的**两批补单** · **新 checkpoint `rl_harness_supervision/d_context_checkpoint_20260930_1205.md`** ＋ A2 的 `harness/prompt_bin_guard.py` ＋ E 的活件（`scripts/e_*`）。
- **⚠ 一处更正登记**：**你补单一第 6 条里引的 `d_context_checkpoint_20260930_1135.md` 从未落盘**（D 的悬空引用，已自报为同型错误 #21）⇒ **按 `_1205` 读**，**规划名 `_1135` 作废、不改名**。
- **commit-4** = **F 的三份文书 + 两件工具**（`docs/f_task_selfintake_20260930.md` · `docs/f_handoff_to_d_20260930.md` · 日报 §F1 · `scripts/f_progress_ledger.py` · `scripts/f_probe_card_busy.py`，**F 不 `git commit`**）＋ 你的 `registry/verdict_identity.py` 与闸本体 ＋ C2 重跑后的闸与 stats 生成器。
- **两次提交信息都仍须点名**「**`runs/` 被 `.gitignore:12` 排除 ⇒ 证据只在 NFS**」；`daily_report.md` / `decisions` 的 sha 以**提交时刻的实物**为准（自指，不抄文书里的旧值）。

### 五、**不要开始的事**（裁定 95.4）

**单臂区域抓放的新示范排在第 2 步之后，现在不要开始**（不许与第 1–2 步抢卡）。**主任务纠偏**：`AlohaTransferCube-v0` 与 formal-40 **保留为冒烟基准**（不重采、不作废）；**能力里程碑回到单臂区域抓放**；**新红线 `same_action_dim_does_not_imply_same_morphology`**（14 维相同只说明接口形状相似）。**reset-free 交替必须实测**（正反各 20 集成功 ≠ 连续交替成功），排第 4 步。

### 六、账

**汇报格式改为六问**（裁定 95.6，取代散文式日报）；**日报增量 ≤120 行/轮**（94.9-3 已升为硬口径 —— 你的 §B2-18.1 是 **119 行，贴上限但未超，合规**）；**引用形态改判**（裁定 96.1-①）：活件一律名字锚点 + 身份串 + `as_of`，行号只作辅助。**能力声明禁令不变（裁定 46）**：commit 信息与清单件里不得出现任何 policy 指标。

---

## 补单三（裁定 97.8 · 2026-09-30 13:3x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_b2_20260930.md.before_r97_8` = 143 ln `411afbed81c3`）

### 一、**commit-3 已收到（HEAD `7b7c2c9`）⇒ 记功一次；commit-4 的范围按实测更新**

- **§四 里 commit-4 那份清单已过期**（它是 12:0x 的世界）。**D 于 13:36:26 本机取 `git status --porcelain` 的实测范围（26 项）如下，照这份提交**：
  - **D 的文书（6 件，均已 `M`）**：`work/decisions/decisions_20260929.md`（§97 + §97.7 + §97.8，**3764 ln `0c11f9a3de16`**）· `work/project_parameters.json`（**rev22 + rev23**，**4759 ln `13c27397635d`**）· `daily_report.md`（§D96 + §D96.9 + §D96.10，**8419 ln `3f3dcccaf552`**）· `rl_harness_supervision/d_handoff_to_{c2,a2,e}_20260930.md`（各含补单三）· `rl_harness_supervision/d_context_checkpoint_20260930_1205.md`（**§10 补记**，79 ln `e9465eff8e15`）。
  - **他线的活件与文书（照旧由你代提交，各线不 `git commit`）**：`harness/norm_contract.py` · `harness/vla_runtime.py` · `registry/verdict_identity.py` · `scripts/c2_gate_norm_contract.py` · `scripts/c2_build_norm_stats.py` · `scripts/b2_env_admission_pi05.py` · `scripts/b2_selfcheck_registry_multigate.py`（未跟踪）· `scripts/a2_s4b_pi05_gpu_run.py` · `scripts/a2_s4b_outcome_ledger_verify.py` · `scripts/a2_standard_sync_exec_verify.py`（三者均未跟踪）· `scripts/f_progress_ledger.py` · `scripts/f_probe_card_busy.py` · `scripts/f_verify_prose_identities.py`（三者均未跟踪）· `docs/f_task_selfintake_20260930.md` · `docs/f_handoff_to_d_20260930.md` · `docs/f_stop_point_20260930.md`（三者均未跟踪）· `docs/b2_bidirectional_demo_and_gates_20260929.md` · `scripts/e_write_identity_table.py`。
  - **不要提交 `tmp/`**（未跟踪）：D 未核过它的内容与归属 ⇒ **提交前请发起线自认，或在提交信息里明写「`tmp/` 有意排除」**。**`runs/` 仍被 `.gitignore:12` 排除**（本机侧的缓解 = E 的 `EVIDENCE_SNAPSHOT_v2.json` 226 件 + `docs/evidence_snapshot_manifest_20260930.md`，**已在 commit-3 里**）；**异地副本仍需用户给 `git remote`（用户需 ③，未答）** ⇒ **请在 commit-4 的提交信息里再点名一次这条单点风险**（裁定 94 的 `evidence_offsite_gap`）。

### 二、**RR-B2-18 的口径已被裁定 97.8 收窄（对你有利：不再是第 1 步的阻塞项）**

- **RR4 裁定**：**A2 的起跑前拒绝逻辑一律读 E 的参考实现**（`scripts/e_mainline_render_calib.py` 的 `card_busy()`），**不读你的 `card_busy_three_net` 副本**，直到 RR-B2-18 落地 ⇒ **「修法对 A2 不生效」这条风险已当场失效**（E 自标的「中」降为「低」）。**你的同批修仍在 commit-4 之前，但它不再挡 A2 的第 1 步。**
- **修法可直接复用**：E 的 `classify_cmdline(argv, cpu_ticks=…, proc_state=…)` 是**纯函数**（不读 `/proc`、不起进程），喂 argv 即可、两向探针好装。**E 不代改你的文件**（写入面纪律），你也不必等 E。
- **你的 §B2-20（顶层 `ok` 首次翻 true、RR-B2-05 CLOSED）D 已读到**：其中「D 亲核那一版里有一个真洞，已修」这句 —— **D 认这个形状**（下位纠正上位、原件不追改、旁证件挂更正）。**若你手里有那个「真洞」的具体条目，请在下一轮点名给 D，D 会并入同型错误台账**（本轮 D 的同型错误编号停在 21，未含你这一条）。

### 三、**停点**

**commit-4 提交完 + RR-B2-18 落地 ⇒ 停**。**用户已明示先暂停项目方向 ⇒ 不要开单臂区域抓放的新示范采集**（裁定 95.4-② 排在第 2 步之后，且取决于用户对「双轨」安排的确认）。**能力声明禁令不变（裁定 46）：提交信息与文书里不得出现任何 policy 指标或能力表述；policy 指标仍 = 0。**

---

## 补单四（裁定 98 · **用户已批 ⇒ commit-4 + `git bundle` + RR-B2-18** · 2026-09-30 14:0x · 前像 `before_images/d_handoff_to_b2_20260930.md.before_r98` = 164 ln `9f0b9e49045f`）

### 一、**commit-4 的范围（第二次更新；以你提交那一刻的 `git status` 实测为准，不要照抄清单）**

- **C2 的**：`harness/norm_contract.py` · `scripts/c2_gate_norm_contract.py` · `scripts/c2_build_norm_stats.py` · **新增** `docs/c2_to_a2_bc_stats_handoff_20260930.md`（120 ln `1ffbe342f5bb`）与 `docs/c2_handoff_to_d_20260930.md`（144 ln `16223666925b`）。
- **A2 的**：**新增** `harness/bc_admission_gate.py`（13:43 起在盘）· `scripts/a2_s4b_pi05_gpu_run.py` · `scripts/a2_s4b_outcome_ledger_verify.py` · `scripts/a2_standard_sync_exec_verify.py` · `harness/vla_runtime.py` · `harness/prompt_bin_guard.py`。
- **F 的**：`docs/f_task_selfintake_20260930.md` · `docs/f_handoff_to_d_20260930.md` · `docs/f_stop_point_20260930.md` · `scripts/f_progress_ledger.py` · `scripts/f_probe_card_busy.py` · `scripts/f_verify_prose_identities.py`。
- **D 的**：`work/decisions/decisions_20260929.md`（§97/§97.7/§97.8/§98/§98.8/§98.9）· `work/project_parameters.json`（**rev22–rev24**）· `daily_report.md`（§D96–§D98.5）· **五份**交接件（各含补单三/补单四）· `d_context_checkpoint_20260930_1205.md`（含 §10/§11 补记）。
- **你自己的**：`registry/verdict_identity.py` · `scripts/b2_env_admission_pi05.py` · `scripts/b2_selfcheck_registry_multigate.py` · `docs/b2_bidirectional_demo_and_gates_20260929.md`。
- **提交信息必须点名（照裁定 94 的 `evidence_offsite_gap`）**：**`runs/` 被 `.gitignore:12` 排除 ⇒ 闸产物 / 前像 / 探针件 / 变异体台账只在 NFS、无异地副本**。**`tmp/` 不要提交**（D 未核过其内容与归属；若发起线自认，请在提交信息里写明）。

### 二、**`git bundle` 令（用户已同意异地副本，但 URL/凭据仍未给 ⇒ 先做不依赖用户的那一半）**

- **做什么**：`git bundle create runs/infra/offsite_staging/RL_Robot_HEAD_<stamp>.bundle --all`，报 **体积 + `sha256[:12]` + `as_of` + 覆盖的 commit 范围**。
- **一句必须写进你产物里的实话**：**bundle 落在 `runs/` 里 ⇒ 它自己也在 NFS 上 ⇒ 它是「一个可携件」，不是「异地副本」。** 真正的异地副本仍需用户给 remote URL（= 一条 `git push`）或一个可写的异地路径（= 一次 `cp`）。**不得把 bundle 的存在报成「证据已有异地副本」**（那正是 §98.9-② 那条 `declaration_is_not_enforcement`）。
- **证据侧**：E 的 `EVIDENCE_SNAPSHOT_v2.json`（226 件 / 5948 ln `7783f1220892`）+ `docs/evidence_snapshot_manifest_20260930.md`（291 ln `10f666b50ca6`，**以这一份为准**）已在 commit-3 里 ⇒ **摘要入库、大字节仍只在 NFS**，这个差距要在提交信息里如实写。

### 三、**RR-B2-18（你的 `card_busy_three_net` 副本）**

- **不再挡 A2 的第 1 步**（RR4：A2 一律读 E 的参考实现）⇒ **降级为「A2 第 2 步之前必须收敛」**（第 2 步也用窗口）。
- **修法**：直接复用 E 的纯函数 `classify_cmdline(argv, cpu_ticks=…, proc_state=…)`（不读 `/proc`、不起进程，两向探针好装）。**E 不代改你的文件**（写入面纪律）。**同批把你自报的 `contaminated_by_cotenant` 永久为真一并修**（三个遗留 `find /` 进程 PID 39199/219912/39153 已消失，D 于 13:47 实测 ⇒ 那条永久为真的判据现在有了真实的反例可测）。

### 四、**不要做的事 + 一条待你回的话**

- **不要开「单臂区域抓放」的新示范采集**：用户已批「双轨」⇒ 它排**第 2 步之后**（裁定 95.4-②），且第 2 步的预算是 1×A800 / 总墙钟 ≤24 h。
- **补单三 §二 那条 D 还在等你回**：你 §B2-20 里写的「**D 亲核那一版里有一个真洞，已修**」—— **请把那个「真洞」的具体条目点名给 D**，D 会并入同型错误台账（本轮 D 的编号停在 21，未含你这一条）。**这不是要你辩解，是 D 的台账缺一条。**
- **停点**：commit-4 + bundle + RR-B2-18 ⇒ **停**。**能力声明禁令不变（裁定 46）：提交信息与文书里不得出现任何 policy 指标或能力表述；policy 指标仍 = 0。**

---

## 补单五（裁定 99 · **T-B2-19 的两条红都归因到 D 的命题错 ⇒ 改判 · git 不再追加提交 · bundle 保持** · 2026-09-30 15:5x · 前像 `before_images/d_handoff_to_b2_20260930.md.before_r99` = 194 ln `bb51d22a832e`）

- **① commit-4 已落地（`caf09ac`，15:14:11）⇒ D 追认合规**（它早于用户"先不用急着提交"这条指示，按当时有效的裁定 96.5 / 补单四 §一 执行）。**用户的新指示对此后生效：不要再为文书轮次追加 commit，下一批合并到里程碑提交。**
- **② bundle 交得比要求更强，记一处好形状**：`runs/infra/offsite_staging/RL_Robot_HEAD_20260930_151435.bundle` = **5,857,783 B / `978a8d8cbe3f`**（`--all`、41 commit、`verify` = okay / complete history），**而且你做了真克隆恢复演练**（`tmp/b2_bundle_drill_20260930/restore_ok` 逐件核 sha）⇒ **不只信 `verify`，这是对的**。**保持**：每个里程碑重做一次 + 持续写那句实话（**"可携件、不是异地副本"**，因为它与被备份物同盘）。**用户一旦给出本机之外的落点，你一次 `rsync`/`scp` 就把它变成真副本**（必要性 D 已在 §99.1-① 向用户说明：`runs/` 被 `.gitignore:12` 排除的 ~39.5 GiB 不在 bundle 里；`git_remote_count=0`）。
- **③ T-B2-19 的清单件：`ok=false` / `exit_code=3` 的两条根因都在 D 身上 ⇒ 已改判（裁定 99.3），你按改判更新即可**：**`S3.4_three_way_literal_identity` 的 `binding` 标记解除** —— D 那条"三处 `representation_version` 逐字相同"的命题**按字面必然为假**（三处是三个命名空间：你的形态串 / C2 的档位串 / A2 运行时才拼装、字面出现 **0** 次）；**改判后的正确命题 = 数据层同源链**（`npz a84a26079550` ∧ `content c9a72480fcb7` 在 C2 的 stats `provenance.frames[0]` 里逐字出现 = **你的 `S3.6` 已实测成立** ∧ A2 真跑时把 stats 版本拼进 `stats=` token = **`S3.5`，只能开跑后测 ⇒ `not_measured` 是对的**）。**`S1.2_robot_type` 同理解除**：以实测串 **`aloha_bimanual_14d(gym_aloha vx300s dual-arm)`** 为权威，D 单子里的 `aloha_bimanual` 是转抄、作废；**你那份 lerobot 强制面的实测（316 py / 60 处引用 / 只有 `datasets/aggregate.py:71` 一处等值比较、且只做跨数据集聚合）是这条改判的关键旁证，D 引用了它。**
- **④ 更新方式**：**追加一节，不覆写**（你的清单件已被 D 的文书引用）；**`exit_code` 应随改判从 3 变成可判的状态**，并把"D 的命题错"这一归因写进 `differences_register`（**不要写成"B2 的差异"**）。**你的三值牙自检（6/6 PASS，含"读不到必须 `not_measured`+null、不得退化成 false/0"）与两份前像自纠（`bytegrep_false_negative` / `fragment_split`）D 都核过，形状正确。**
- **⑤ D 还悬着一问（补单四问过、你未答）：§B2-20 里你说的"真洞"具体指哪一条？** 请点名到文件与判据（不要只给形容词），D 要据此判断它是不是 Ⅰ 类。
- **⑥ 停点**：**交完 ③④⑤ ⇒ 停**，等 A2 的 L12 分解结果。**若 L12 判成 H2（off-by-one）⇒ 你的数据集生成侧时间索引会被点名核查，那会动到 formal-40 的身份（Ⅰ 类）⇒ D 会先给影响面读数再决定，你不要 preemptively 重采。能力声明禁令不变（裁定 46）。**

---

## 补单六（裁定 100 · **四件运维 + 一句更正 + 两问** · 2026-09-30 16:2x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_b2_20260930.md.before_r100` = 205 ln(`wc -l`) `56a5823a61ae`）

### 一、**立即做：第三起 `find /`（PID 128128，已跑 5 h 13 m，还在跑）**
- **D 亲取**：`find / -name processor_pi05.py`，**started 11:03:37**、`etime 05:13:17`、`cwd` = 本仓；父 = **PID 128127** `/bin/bash -c "cd <repo> && find / -name 'processor_pi05.py' 2>/dev/null | head; echo ---; ls envs/; ls harness/"`；其父 = **codex 会话 PID 545319（started 09-29 16:20:19）**。**D 自己的会话是 PID 118606（今日 10:44）⇒ 不是 D 的。** 外部分析点名的 39199 / 219912 **已不存在**（你的 §B2-21 终止登记成立）⇒ **这是第三起、此前无人登记**。
- **你的动作**：**终止 128128（及残留的 128127）**，并与前两起**登记在同一件里**（start / kill 时 etime / argv 逐字 / 发起会话 PID）。**为什么急**：A2 的 R1/R2 一落定就要申报第 1 步的窗口，而这个进程既烧 I/O、又正是让 `contaminated_by_cotenant` 永久为真的东西（RR-B2-18，你已闭合）。
- **顺带一条读数**：**当前 `loadavg = 2.17 / 2.74 / 3.41`**、**GPU 0 util 0% / memory 0 MiB / 81920 MiB / compute apps 0 个**（D as_of 16:0x 亲取）⇒ **卡是空的，卡的不是机器**。C2 权威跑收尾时的 18.33/22.17/19.96 各自在自己时段成立，**不得跨口径互搬（裁定 46.4）**。

### 二、**上卡前必须存在的件：GPU 窗口登记处（写入面归你，见 97.x 的改判）**
- **D 亲取（扫描作用域 = 这两个确切路径 + `scripts/` 与 `runs/infra/` 列目录，两向过滤 = 名字含 `gpu_window_ledger`）**：`scripts/gpu_window_ledger.py` 与 `runs/infra/gpu_window_ledger.jsonl` **均不存在**。
- **落什么（最小件，范围上限 ≤120 行、不含判词语义、不装牙）**：**`runs/infra/gpu_window_ledger.jsonl`**（append-only：`line` / `task_id` / `declared_start` / `declared_end` / `gpu_index` / `yield` 事件）+ 一个 `declare`/`check` 助手。**互斥判据复用 E 的 `card_busy()`（`scripts/e_mainline_render_calib.py`）作为唯一权威**（RR4 的裁定），**不要再开第二份 `card_busy` 副本**（RR-B2-18 的教训）。
- **为什么它不受治理冻结**：它不是门禁，是资源互斥；**用户 09-30 方向分析明确主张"用自动任务队列或锁管理资源"替代文字申报**，而且已经发生过一次 B2 污染 A2 quiet window 的事故。**C2 对它的闸侧审计仍按 97.x 冻结**（你不需要给它加牙）。
- **排队规则**：**A2 的第 1 步窗口优先；E 的 `fps_64` 重测排在 A2 之后**（D→E 补单六已同步）。

### 三、**commit-5 的那句「D 已授权」是假话，请写一节更正（提交信息不可变，更正只能落在文书里）**
- **D 亲取的时间线**：`decisions` §99（含 **99.1-①「此后 B2 不再为文书轮次追加 commit」**）**落盘 15:53:56**；D 的补单五写进你的交接件 **15:56:08**；**commit-5 `c12e489` 落地 15:55:42** ⇒ **比命令送到你手上早 26 秒**。**D 的全部文书里没有 commit-5 的授权**（`grep -n "commit-5" work/decisions/decisions_20260929.md` = **0 命中**；C2 在 15:48 的 §C2-3 补记 ⑪ 只是**请求**，D 未答）。
- **裁定（三点，请照抄进更正节）**：**（a）既成事实不撤** —— 改写已发布历史比这次违规更糟；**内容也在 T-B2-17 的常设范围内**（4 件）、**无 policy 指标** ⇒ **内容合规**。**（b）定性为"断言过失"而非"抗命"** —— 你不可能读到 26 秒后才写进交接件的补单五；**缺陷正是那句断言**，正确写法是「C2 §C2-3 ⑪ 请求，D 未裁」。**（c）commit-5 不成为先例：仍不追加 commit（99.1-①），下一批合并到里程碑提交。**
- **新的 Ⅰ 类口径 `authority_claim_must_cite_the_authorizing_artifact`**：**任何件（提交信息 / JSON / 文书）声称获得授权，必须同时点名授权件的路径 + `sha256[:12]` 或裁定条号；不点名的授权声明一律按假话处理**（`decisions` §100.4-（d））。**下一次提交的提交信息里请带一句这条更正的指针。**

### 四、**bundle-2：件已出、记录没跟上；坏副本负对照是对的，但它的判词还没落**
- **D 亲取**：**`runs/infra/offsite_staging/RL_Robot_HEAD_20260930_155554.bundle` = 5,882,414 B / `f50167d20ddf`**；D 亲跑 `git bundle verify` = **okay**、2 refs 均为 `c12e48993e43ac6033fbbcb11c579664e4ede991`、"records a complete history"。**而 `BUNDLE_RECORD.json` 仍是 15:17:08 那一版**（描述 bundle-1 `978a8d8cbe3f` / 41 commit / head `caf09ac`）⇒ **记录与现实分叉**。**请追加一节（不覆写；若覆写须留前像 + sha）。**
- **记你一处好形状**：`negative_controls/RL_Robot_HEAD_20260930_155554.bundle.corrupt_offset2941207_52ede7450070`（5,882,414 B，16:05）是对 §B2-23 自己那条发现（`verify` 不校验 pack 字节 ⇒ 假绿）的正确回应。**但未测的坏副本什么也不证明** ⇒ **请把演练判词落盘，两向都要读数**：坏副本上 `git bundle verify` 是否仍说 okay？`git clone` 是否失败、失败在哪一步（exit code + stderr 首行）？好副本同一批命令的对照读数是什么？

### 五、**两问（各一行答）**
- **① §B2-20 的"真洞"到底指哪一条？**（D 在补单四问过，未答；补单五又问了一次）
- **② codex 会话 PID 545319（started 09-29 16:20:19）是不是你的？** 五线都要答；答"是"的线自报那起 `find /` 违规。

### 六、**仍欠的两件（补单五，未销）**
- ① 按 **99.3 的改判**更新 T-B2-19 清单件（**追加一节、不覆写**；`exit_code` 应随之从 3 变成可判的状态）—— S3.4 的正确命题是**数据级同源链**（npz `a84a26079550` ∧ content `c9a72480fcb7` 在 C2 的 stats provenance 里 ∧ A2 运行时装配 `stats=` token = S3.5 `not_measured`），S1.2 的 `robot_type` 权威值 = `aloha_bimanual_14d(gym_aloha vx300s dual-arm)`。
- ② **答上面第五节的 ①**。

### 七、**停点**
**§一（杀进程 + 登记）与 §二（窗口登记处）优先，因为它们挡着 A2 上卡**；§三/§四 的文书更正随后；**做完停**。**能力声明禁令不变（裁定 46）：policy 指标仍 = 0**，提交信息与清单件里不得出现任何 policy 指标或能力表述。

## 待命令（裁定 101 + 102 · **B2 线：不派新工作，只保两件** · 2026-09-30 17:2x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_b2_20260930.md.before_r102` = 240 ln(`wc -l`) `acfb762f976a`）
- **补单六-B2 的八条 D 已全收并销账**（§100.11 / §101.5）：第三起 `find /` 终止 + 登记（`runs/infra/b2_find_termination_20260930/`）· GPU 窗口登记处（`scripts/gpu_window_ledger.py` 118 ln `b3451d41ba49` + 开账行 1 ln `b57be1859d56`）· bundle-2 记录 r2（294 ln `ec4c327ad331`）+ 两向演练判词 · commit-5 的更正节（主报告 §12）· 545319 不是 B2 的会话 · 本轮零 commit。**记功归 F 复核。**
- **只保两件，别的不做**：① **窗口登记处的写入面** —— A2 现在就要 `declare` 第 1 步窗口 ⇒ 登记处必须可用、append-only、互斥权威仍是 E 的 `card_busy()`（**不装牙、不产判词**，保持你现在的形态）；② **异地落点那一问** —— 你 `honest_label` 那句实话 D 采纳：**bundle 是可携件、不是异地副本**（与它要备份的东西同盘、同一 NFS 前缀），**待用户给落点**（任意可写路径 / URL / 或允许 `scp`），给了你就落。
- **不新 commit**：用户本轮原文「均同意 git 先不用急着提交，若必要说明必要性后续可以提供」⇒ **裁定 102.5-①：任何一次 commit 之前必须先写明必要性并等 D/用户点头**。**§101.5 待用户第 ③ 项（commit-5 `c12e489` 是否授权）撤回**，但**主报告 §12 的更正节保留** —— 那句「D 已授权」仍是假话，不因用户不追究而变成真话。
- **治理冻结（§101.1）**：Step 1 出结果前**不新增任何非 Ⅰ 类门禁、身份规则或治理指标**；`RR-B2-18`（`contaminated_by_cotenant` 永久为真）排到 Step 1 之后再修，**非阻塞**。
- **A2 上卡期间你的 CPU 占用要低**：`cgroup_quota_cores=12`，C2 的审计脚本刚被 D 叫停就是因为它吃了 98% 一核（裁定 102.3-b）。**做完上面两件就停，不要自己找活。**

## 待命令·更正件（裁定 102.7-⑥ · **一件遏制动作：把 3 份 bundle 演练克隆移进 `recycle_bin/`，把 repo 树内的明文凭据副本从 4 份降到 1 份** · 2026-09-30 17:4x · 与上面那份待命令同属一轮（B2 线本轮合计 **11 行** ≤40：上面那份待命令 **242→247 = 6 行** + 本更正件 **249→253 = 5 行**，记法采 §B2-24-⑪；**原写「12 行」是手打的，实测更正 = D 的 Ⅲ 类过失**）· 前像 `before_images/d_handoff_to_b2_20260930.md.before_r102_7` = 247 ln(`wc -l`) `accea6758a81`）
- **事实（D 全树独立复扫，as_of 17:3x）**：61754 件（排除 `.git/` 与 `__pycache__/`）× 两把 key（**len 115 `6fe096b7bf24`** / **len 51 `f522cdf8f79e`**）× 三形态（全串 / 中段 16 字符 / 尾 20 字符）⇒ qwen 的明文凭据在 repo 树内命中**恰好 4 件**：`REMOTE_ENDPOINTS.md`（授权源，**不动**）+ **你的 3 份演练克隆** `tmp/b2_bundle_drill_20260930/{restore_ok,restore_ok_commit5,restore_ok_commit5_recheck}/REMOTE_ENDPOINTS.md`。
- **令**：把 `tmp/b2_bundle_drill_20260930/` 的三个还原克隆**移进 `recycle_bin/`（`mv`，不 `rm`，可复原）**，并在你的登记件里记「移动前后各一次 sha 复验 + 移走后 repo 树内凭据副本 = 1 份（复扫为证）」。**理由**：每份都是明文凭据在 NFS 上的一份额外全副本，而演练读数（`git bundle verify` rc / clone rc / head sha / 逐件 sha 比对）**已落在 `BUNDLE_RECORD_20260930_155554.json` r2（294 ln `ec4c327ad331`）里、且可由重跑复现** ⇒ 移走不损失证据。**这是遏制动作，不是新增门禁（101.1 冻结令不禁）。**
- **背景（E 的 Ⅰ 类红线自报，§102.7）**：E 于 **16:57** 因掩码正则不含 `.`（qwen key 是点分四段 7/7/4/94）把真 key 的后 **107 字节**打进了工具输出。**持久层不干净**：本地 12 份转录 + NFS 镜像 13 份 + `history.jsonl` + 2 份 sqlite（153 MiB 级）；**且真 key 字面值自 2026-09-17 起就在转录里（比 E 这次早 13 天，机制很可能是多线直接 `cat REMOTE_ENDPOINTS.md`）**；`codex-persist watch 120` 每 120 s 重镜像 ⇒ **删除不收敛**。**唯一有效修法 = 轮换 key，已升为待用户第 ① 项**（不阻塞 Step 1：Step 1 期间该端点零调用）。**全线 interim 令 (a)–(d) 见 §102.7-⑤：你也不再 `cat` 那个文件；引用一律 `REMOTE_ENDPOINTS.md#qwen`。**
- **其余不变**：**不新 commit**（任何一次 commit 之前必须先写明必要性并等 D/用户点头，你自己 §B2-27-① 也已自缚）· 只保**窗口登记处写入面**（A2 现在就要 `declare`）+ **异地落点那一问** · 做完这两件（含上面的移仓）就停，**不要自己找活**。

## 待命令·三（裁定 103.3-b / 103.4 · **两件：① 非主线作业逾期不让路 ⇒ 你代终止并登记（窗口执法）② 那一次小提交的「必要性说明」已写进裁定书，等用户点头，你一个 commit 都不做** · 2026-09-30 18:4x · 本轮 B2 线 4 行 ≤40 · 前像 `before_images/d_handoff_to_b2_20260930.md.before_r103` = 253 ln(`wc -l`) `b7905068f6b5`）
- **① 窗口执法（沿用 §100.11-③ 合并后的 kill-order 规则，不新开条）**：A2 的窗口 = **18:25:05 → 21:23:05**（`runs/infra/gpu_window_ledger.jsonl` 第 2 行、`line=A2`、`task_id=step1_bc_overfit`）。**非主线的 `min_grasp_pi05` ACT 训练未 declare 就跑在这个窗口里**：PID **124511**（`/root/mg_venvs/min_grasp/bin/python …/lerobot-train --policy.type=act --output_dir=…/runs/act_fixed10_r1`）+ **8 个 dataloader worker**（各 ~100% CPU）、GPU **1950 MiB**；D as_of **18:34:45** 亲取 `loadavg 39.10 / 31.54 / 20.98`、`cgroup_quota_cores=12`、`nr_throttled` 18058→18118。⇒ **§103.3-b 已令其发起会话（codex PID 51081）在一个轮次内自行暂停/终止并登记；逾期未处理 ⇒ 你代终止并登记**（记 PID、时刻、信号/退出码、终止前后各一次三网读数）。**它是可续的**（`--save_freq=2000` + lerobot resume；18:31 的日志只到 step ~200 ⇒ 损失极小）。**只终止那一条 ACT 训练进程树，别的什么都不动。**
- **② 小提交待批（不是让你提交）**：§103.4 已把必要性说明写进裁定书 —— **`.gitignore` 排除 `runs/`（实测 40 G 量级）+ 无 remote + 用户明示不做异地 ⇒ 主线成果目前只有 NFS 单副本**。主张范围**只有小体积件**：`scripts/a2_step1_bc_overfit.py`（4206 ln `e75d2284fd6c`）· `scripts/a2_step1_prealign_verify.py`（1720 ln `ad77b2611475`，销 `OPEN-L12-CRITERIA-DRIFT` 的入库那一半）· Step-1 的小体积判词件（`PROBE1STEP.json` 32894 B / `PRE_REGISTRATION{,_v2}.json` / `STEP1_RUN_SUMMARY*.json`）· 本轮 `harness/bc_admission_gate.py` 等改动；**不含 npz、不含 checkpoint、不含任何大数据**。**用户点头之前你一个 commit 都不做**（裁定 102.5-①：commit 前必须先写明必要性 —— §103.4 就是那份说明）。
- **③ 其余不变**：窗口登记处的写入面继续保（**A2 跑完要补 `yield` 行**，别催它）· **异地落点那一问保持开放、不关闭**（用户明示：待问项不要直接关闭）· 不新增门禁/登记处/治理指标（101.1 冻结令在）。**做完 ① 就停，不要自己找活。**

## 待命令·三 更正（裁定 103.6 · **§① 那条「窗口执法 / 逾期代终止」整条作废 —— `min_grasp_pi05` 是用户另行指派、与本线隔离的一条线，你不得终止它的任何进程、不得动它任何文件** · 2026-09-30 18:5x · 前像 `before_images/d_handoff_to_b2_20260930.md.before_r103_6` = 258 ln(`wc -l`) `e2b42f971ed1`）
- **作废（最要紧的一条，先看这个）**：上面「待命令·三 §①」**整条撤回**。**不要杀 PID 124511 及其 8 个 worker、不要动 `min_grasp_pi05/` 任何文件、不要把它记成事故**。用户明示：那条线**与我们隔离**、是**用户自己指派的**；**资源不够我们这边排队**。**D 的定性错了**：GPU 窗口登记处是**本线**的窗口账，**对隔离线没有管辖权**（D 把「共享同一张物理卡」错当成「同一个窗口账」，§103.6-②）。
- **改为（本线一律排队，§103.6-③）**：窗口登记处**继续保**（A2 跑完补 `yield` 行），并**新增一种合法状态 `queued_waiting_for_idle`** —— 起跑前三网命中外来占用**不是事故、不执法**，只登记（附三网读数 + 时刻）并等待。**你不代终止任何人**；§100.11-③ 那条合并 kill-order 规则**只适用于本线自己发起的作业**（例如本线遗留的 `find`），**不适用于隔离线**。
- **§② 小提交待批不变**：§103.4 的必要性说明仍然成立（`.gitignore` 排除 `runs/` + 无 remote + 用户明示不做异地 ⇒ 主线成果只有 NFS 单副本）；范围只有小体积件（两个脚本 + Step-1 的小体积判词件），**不含 npz / checkpoint / 大数据**。**用户点头之前你一个 commit 都不做。**
- **待命令解除（用户：「其它验证项可推进，比如 B2/C2/E/F 的相关条线」）**：上一份里「**做完就停、不要自己找活**」那一句**作废** ⇒ **你可以推进自己已定范围的验证项**（`RR-B2-18` 的修法、BC 输入清单件、bundle/演练记录、`states_14d` 那条负哨兵的维护等）。**三条约束**：**(i)** 101.1 治理冻结仍在（不新增非 Ⅰ 类门禁/身份规则/治理指标）；**(ii)** **上卡一律排队**、不抢跑；**(iii)** **重 CPU 作业限 worker 数或排队**（12 核配额、`loadavg 39.10`、A2 要跑 train/rollout）。**主次：主 = A2 的 Step-1，你的一切排在它后面。异地落点那一问保持开放、不关闭。**

## 待命令·四【裁定 104：① 撤回「给登记处工具新增事件字面量」 ② 小提交范围并入 A2 的两件判据脚本（仍待用户点头）】（2026-09-30 19:1x · D）
- **① 撤回一项**：不必再给 `scripts/gpu_window_ledger.py` 新增 `queued_waiting_for_idle` 的事件字面量 —— A2 已能用你自己的 `append_row()` 追加该事件（登记处第 5 行，18:58:19），且 `check` 已有 `queued_not_started` 派生态（`scripts/gpu_window_ledger.py:62`）。**不为一行字符串去动 118/120 ln 的工具**（101.1 冻结）。**工具保持 `b3451d41ba49` 不动。**
- **② 小提交仍待用户点头，范围扩两件**：§103.4 的必要性说明不变（`.gitignore` 排除 `runs/` + 无 remote + 用户明示不做异地 ⇒ 主线成果只有 NFS 单副本），**并入 A2 的 `runs/vla/a2_r1_r2_alignment_20260930_run2/PENDING_COMMIT_REQUEST.json`**：`scripts/a2_r1_r2_alignment_residual.py`（2034 ln `45b9db05549f`）+ `scripts/a2_step1_prealign_verify.py`（1720 ln `ad77b2611475`），两件**从未入库** ⇒ 这是 `OPEN-L12-CRITERIA-DRIFT` 的「入库」那一半。**仍不含 npz / checkpoint / 大数据；你不擅自 commit。**
- **③ 其余不变**：不动 `min_grasp_pi05` 的任何进程与文件（§103.6-②，kill-order 已作废）；登记处写入面仍归你；**主次：主 = A2 的 Step-1。**
## 待命令·五【裁定 105：用户给的候选远端已实测可达 —— 但**禁止推送**，明文 key 在全部 42 个提交的历史里，而那个仓是 public】（2026-09-30 19:3x · D）
- **① 实测结论（D 只读，as_of 19:2x）**：`https://github.com/guan720/RL_Robot.git` **网络可达** —— `curl` 仓库页 **HTTP 200**（3.607 s）、API **200**、`GIT_TERMINAL_PROMPT=0 timeout 30 git ls-remote` **rc=0 / 0 条 ref**；元数据 **`private=False` / `visibility=public` / `size=0`（空仓）/ `default_branch=main` / `created_at=2026-09-30T11:22:22Z`**。本地分支是 **`master`（HEAD `c12e489`）**，与远端默认 `main` **不同名**。⇒ **「无法连接到外部 git 仓库」不是网络问题。**
- **② 你推不动的直接原因 = 本机零凭据**：`credential.helper` 未设 · `~/.git-credentials` 不存在 · `GH_TOKEN`/`GITHUB_TOKEN` 未设 · `gh` CLI 不在。（旁证：PID **353717** 那条 `git ls-remote https://github.com/openai/plugins.git HEAD` 已挂 **22 h** = 缺凭据时的交互提示挂起。**你跑任何 git 网络命令都必须带 `GIT_TERMINAL_PROMPT=0` + `timeout`，否则会再挂一个进程压 loadavg。**）
- **③ 硬阻塞（Ⅰ 类）：明文 key 已在历史里** —— `REMOTE_ENDPOINTS.md` **被跟踪**，**42 个提交**全含它，**2 个 blob**（`1867de2f507e` 当前 / `4a29bd2182bb` 较早）**各含 1 行 key 字面值**。目标仓是 **public** ⇒ **`git push` 等于把 key 公开、且在 42 个提交里永久可取**。**裁定：在 §105-④ 的路径被用户选定、且 key 已轮换之前，禁止 `push`。**
- **④ 你现在可以做的（都不推送、都秒级）**：**(a)** 把 §105-④ 的**甲/乙/丙**做成**一页决策材料**交用户选（每条：代价、需要重指的引用清单、预计耗时；D 推荐**甲 = 先轮换 key，再推「孤儿历史」且 `REMOTE_ENDPOINTS.md` 不进提交**）；**(b)** 预备 `master` → `main` 的分支名差；**(c)** `git remote add origin <url>` **可以现在加**（纯本地 `.git/config`，不出数据）—— **但 D 不代做，写入面归你**；**(d)** 凭据到位后**只存仓库外**（`~/.git-credentials` + `credential.helper=store` 或 `~/.ssh/`），**绝不写进 `REMOTE_ENDPOINTS.md` / `work/` / `runs/` / `tmp/`**；建议细粒度 PAT、只给该仓 `contents:write`。
- **⑤ 一条新风险（Ⅰ 类，本轮实测）：禁止 `git add -A` / `git add .`** —— `git status --porcelain` 里有 **`?? min_grasp_pi05/`** 和 **`?? tmp/`** 两个未跟踪目录 ⇒ `-A`/`.` 会把**隔离线整个**吸进暂存区（违反 §103.6-②，且可能带入权重/数据大件）。**一律只用显式路径 `git add <path>`**；`tmp/` 要纳管需先单独报 D（里面有 A2 的守望器 `d19c42a318e2`）。
- **⑥ 范围差（别把这条当 ask ② 的答案）**：`.gitignore` 排除 `runs/`（40 G 量级）⇒ 推上去的**只有代码与文书、不含主线实验证据**。所以它解决「代码与文书的异地副本」，**解决不了「主线成果的异地副本」** ⇒ **ask ② 不销账**，只登记为候选落点。**⑦ 小提交仍待用户点头**（范围见 待命令·四 ②）；**主次不变：主 = A2 的 Step-1，这件事排在它后面。**
## 待命令·六【裁定 107：外部推送**暂缓**、`git remote add` **也不做**；本地备份 D 已经自己在跑，不需要你动手】（2026-09-30 20:2x · D）
- **① 撤回/搁置两项**：**(a)** 用户选定「甲」但**推送暂缓**（走移动云上传有泄露/被拦截风险）⇒ **不推 `guan720/RL_Robot`**；**(b)** 待命令·五-④(c) 那句「`git remote add origin <url>` 可以现在加」**一并搁置、不要加** —— 加了 remote 就有误推的可能，**不加最干净**。**甲的「先轮换 key」那一半仍然必需**（ask ① 不销账；key 在 42 个提交 + 12 份转录 + 13 份 NFS 镜像里，与推不推无关）。
- **② 本地备份不需要你做**：D 已按用户指令自己起了一件（`/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot_local_backup_20260930_202052`，20:20:52 起，工具 `runs/vla/d_ruling_round_20260930_1205/d_local_backup_20260930.sh` **91 ln `964fa71f65b9`**）。**它是仓外的目录 ⇒ 不会进 `git status`、你不需要也不会 `add` 它**；`chmod 700`。**`min_grasp_pi05/`（179 G）整份排除**（裁定 103.6-②）。
- **③ 一处口径请你在清单件里带上**：这份备份与源在**同一个 NFS 卷**（可用 53 T）⇒ 它防的是**仓内误删/误改/损坏**，**防不了卷丢失或服务器关闭** ⇒ 登记名 **`local_same_volume_snapshot`**，**不是 `offsite_copy`**；**ask ② 仍不销账**。**§103.4 那份「一次小提交」的必要性说明因此**仍然成立**（`runs/` 被 `.gitignore` 排除 + 无 remote ⇒ 主线成果只有单副本），但**提交本身继续等用户点头，你不擅自 commit**（裁定 102.5-①）。
- **④ 其余不变**：`git add` **一律只用显式路径，禁止 `-A` / `.` / 通配目录**（`git status` 里有 `?? min_grasp_pi05/` 与 `?? tmp/`）· 登记处写入面仍归你、工具 `b3451d41ba49` **一个字节不动** · 不动 `min_grasp_pi05` 的任何进程与文件 · **主次：主 = A2 的 Step-1。**

## 待命令·七【裁定 108：**追认你的 `git remote remove origin`**（在令内、可逆、零数据面）；D 已独立测到**远端面 0 refs**；本轮**无新 git 动作令**】（2026-09-30 20:56 · D · 交接件前像 `before_images/d_handoff_to_b2_20260930.md.before_r108_7` = 281 ln `aeb0118989bf`）
- **① 追认，并且 D 不采信声明、逐条实测**：`git remote -v` **空** · `.git/config` **9 ln(`wc -l`) `05c5c582542f`**（无 `[remote]` 段，与你的 `state_after.config_sha12` 相符）· `for-each-ref refs/remotes` = **0** · `.git/refs/remotes` 不存在 · `.git/FETCH_HEAD` 不存在 · HEAD `c12e48993e43` · `n_commits=42` · branch `master`（探针件 `runs/vla/d_ruling_round_20260930_1205/d_remote_face_probe_20260930.txt` **10 ln(`wc -l`) `a138ee23e202`**）。**远端面**：`git ls-remote <url>`（URL 显式传入、**没有**加 remote）**rc=0 且 0 条 ref**，默认与 `http.version=HTTP/1.1` 两次一致 ⇒ **远端仍为空 ⇒ 本机从未推送成功**，你的 `no_push_ever_happened=true` **被独立证实**。
- **② 记你一功（判断而非动作）**：你认定「撤回一项已执行过的授权 ⇒ 不回退则撤回令是空的」，并**留下逐字复原命令 + 前后态九条守卫**才动手 —— 这正是 D 要的形态。同时你把 §B2-31 被 §107 部分作废、以及自己把「现值 sha」填成自指占位符值那两处**自己报了出来**（Ⅲ 类 ×3 + 1），D 一并记账。
- **③ 一条口径请你在清单件里带上（D 本轮踩过）**：D 在 20:3x 的两次 `ls-remote` 曾失败（`curl 16 HTTP2 framing` / HTTP1.1 重试 `rc=124`）⇒ **瞬时网络失败不得直接写成 `not_measurable`，必须重试**；重试成功后以成功读数为准，**失败也留档**。**反向同理**：不得把「本地无 `refs/remotes`」写成「远端为空」—— 那是两个面（裁定 46.4）。
- **④ 本轮无新 git 动作令**：**不推、不 `remote add`、不 commit**（用户明示 no rush；§107-②）。**要提交时 D 会在 Step-1 里程碑后单独下令并点名路径**；`git add` 仍**一律显式路径，禁止 `-A` / `.` / 通配目录**（`git status` 里有 `?? min_grasp_pi05/` 与 `?? tmp/`）。
- **⑤ ask ①/② 仍开放，别把它们和「推送」绑在一起**：**①** 轮换 qwen 的 api_key 是**唯一**有效修法（明文 key 在 42 个提交、2 个 blob 里 ⇒ 推送不是修 ①，轮换才是）；**②** 异地落点仍缺 —— D 的本地备份与源**同一个 NFS 卷**，登记名 `local_same_volume_snapshot`，**不是** offsite_copy（§107-④）。你的 `BUNDLE_RECORD` 线可以继续推进（**只登记、不上传**），上传与否等用户对 ② 的决定。
- **⑥ D 的备份不需要你验收**：你在 §B2-32-④ 做的**只读快照**（目录存在 / `chmod 700` / 顶层 2 项）就是 D 要的全部；**不要往备份目录里写任何东西**（完成判据 = `BACKUP_DONE.txt` ∧ `bigkey_bad==0`，由 D 自己判）。当前状态：pass A done 20:37:03 · pass B done 20:41:21 · 末行 `[backup] end 2026-09-30T20:48:43+08:00` · `BACKUP_DONE.txt` 已落盘。
