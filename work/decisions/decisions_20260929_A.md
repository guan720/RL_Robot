# A 线登记（2026-09-29）：48 臂表迁到 v1.5 / 迁移闸判据修复 / 分布层引用闸（裁定 30）

登记方：智能体 A（官方 LeRobot ACT 闭环评测·汇总线）。
依据：`work/decisions/decisions_20260928.md` DR-001（`work/decisions/` 可写，**最小写入**：只放
路线变更 / 口径裁定 / 作废与 ack 登记；实验结果、产物、日志不写入本目录）、
DR-003 决定 8（单写者纪律 ⇒ **A 不执行任何 git 写命令**，本线只读 `git log` / `git status`）。
编号续用 `ADR-A-*`（裁定 29.5 给的并号规则：`DR-D<n>` = D 线、`DR-00<n>` = B 线、
`ADR-A-<n>` / `ADR-C-<n>` = A/C 线）。本文件**不修改** D 的 `decisions_20260929.md`、
B 的 `decisions_20260928_B.md`、C 的 `decisions_20260929_C.md`，也**不修改**昨天的
`decisions_20260928_A.md`（append-only：结案在新文件里登记，旧文件一字节未改）。

**上下文来源声明（必须写清）**：09-28 四线的 rollout（`/root/.codex/sessions/2026/09/28/`）已被
服务器检修一并清掉，`.codex-persist` 备份是 09-29 12:00 才 bootstrap 的 ⇒ **只捞到 09-21 及更早、
以及 09-29 当天**（实测 `backup/sessions/2026/09/` 有 09/10/11/14/15/16/17/20/21/29，**无 22–28**）。
本轮 A 的上下文是从**盘上产物**重建的：`work/decisions/decisions_20260929.md`（裁定 17–30）、
`rl_harness_supervision/supervisor_memo_20260929.md`（增补六 / 增补七 §19–§20）、
`docs/b_handoff_to_a_20260929.md`、`docs/lerobot_act_env_setup_20260928.md`、`daily_report.md`、
`runs/infra/lerobot_act_env_20260928/**`、`runs/infra/b_official_arms/**`、`tmp/agentD_review_20260929/`、
`git log`（7 commits）。凡本轮引用的数字都注明了产物路径，且**A 现场重算**而非采信他线转述。

---

## ADR-A-008 48 臂权威表迁到 **v1.5 / `f19f61341cbe`**（裁定 27 五项 + 增补七 §19-A①，已实施已验收）

- 时间：2026-09-29 11:3x 修闸、11:5x 钉旧、12:01 迁表并登记
- 依据：裁定 27（D 认定 A 迁移闸 2 项 blocking **全是假红**，要求「先把红绿灯修得与实际状态一致，
  再跑迁移 + `--mode postcheck`」）、裁定 28（`PENDING_IMPL` 全部撤下、权威口径改 v1.5）、
  裁定 29.2（DR-010 排序**选 (a)**：A 先迁表、裁定 23 作为 v1.6 紧随其后）、
  `docs/b_handoff_to_a_20260929.md` §3（迁移前置）与 §7（迁移步骤）
- **迁移闸判据修复（19 → 24 项，自检 31/31）**：
  1. **G2 改实测**（裁定 27④）：`importlib` 加载 B 的门禁本尊、对目标臂 **plain** 产物调 `judge_file`
     （`json_out=None` ⇒ 不写文件），blocking 判 5 前提：`ic_status=probe_exonerated`、
     `measurement_valid is True`、`gate_pass is True`、`probe_kind=clip_at_train_absmax`、
     `band_checked is False`。**不再文本扫描源码找锚点** —— v1.5 的实现锚点是
     `BAND_EXEMPT_PROBE_KINDS` / `EXONERATION_PROMOTION_SOURCES`，文本扫描认不出来（这正是假红的根因）。
  2. **L5 收窄**（裁定 27②／裁定 21）：只读 `entry["ruling10_conditions"]` 里门禁源码
     `RULING10_CONDITION_KEYS` 的五个键、要求 `is True`；**不读**`ruling10_conditions_evidence` 的
     5 条证据散文（旧写法把散文当断言 ⇒ 恒红）。
  3. **L6 收窄**：照抄门禁读法（`cosign.by` 非空 + `cosign.fact_basis is True`），不认 A 自造的 legacy 键。
  4. **G1 / G3 降级为非 blocking 诊断**，并把锚点更新到认得 v1.5 的两种新形状；**与 G2 冲突时一律以 G2 为准**。
  5. **新增 B7 / B7b / B8 / L6b**（B 侧回显，A 不代改 B 的文件）与 **P7**（postcheck，blocking）：
     A 表按 `probe_kind` **分组**对账，`VALID_probe_exonerated` 只对应 clip 通道（裁定 24⑤）。
- **钉旧（禁 `rm`，一律 `cp -a` 留档）**：54 份 v1.2.1 裁定钉进
  `runs/infra/lerobot_act_env_20260928/regate_v121_pinned/{main,blindfix,reblown}`（48 主 + 5 blindfix + 1 reblown），
  附 `PINNED_WHY.md`。该目录**不在** `summarize_lerobot_act_arms.py::load_gate_index` 的扫描范围内 ⇒ 不污染现值表。
- **迁移**：三个目录全量重判（`a_regate_gate_current.py`）⇒ 54 份全部 `v1.5 / f19f61341cbe`；
  重出表 + 构建迁移回归断言 **PASS，预期差异 201 / 非预期 0**
  （`attribution/migration_regression_v121_to_v15.json`）。201 处全是判据构建的函数；
  **计数层 / 分母 / 合计即使 `--allow-build-change` 也永远不许动**（DR-008 验收判据 3 的可执行形式）。
- **迁移后表值**：`single_build_only=true`；免罪前 24/22/2、免罪后 **25/22/1**；
  validity = valid 46 / `VALID_probe_exonerated` 1 / invalid 1（唯一 INVALID = `…_replan1`）；
  `probe_kind` 列 = clip 1 / reblown 1 / null 46；48 臂合计 960 局 / raw **377** / 受控 **135** /
  insuff **235** / flick **7** / over **0** / prov **0**（与迁移前**逐格相同**）。
- **验收**：迁移闸 `MIGRATION_GATE=OPEN / blocking_fail=0 / warn=0 / total_checks=24`；
  迁移后闸 `POST_MIGRATION_CHECK=OPEN / 0 / 0 / 17`；自检 **31/31**
  （含裁定 27③ 补的 S18/S24 真条目形状、S19「G2 实测的牙」、S29「无证据不放行」）。
  D 在 11:49 独立复跑留档 `tmp/agentD_review_20260929/D_A_gate_preflight_20260929_1149.json`。
- **性质**：**只读后处理**。actlog 一字节未动，不跑任何训练 / 评测，不依赖 `rlrobot` venv
  （裁定 29.4：A 线新训练 / 新评测仍阻，本轮工作不在受阻范围）。
- **能力结论一字未变**：目标臂在 v1.2.1 与 v1.5 下逐格相同；免罪只解除**测量有效性**保留。

## ADR-A-009 拔除 spec 轴地雷（裁定 29.1）+ 补写被引用的移交单（裁定 29.3），已实施

- **裁定 29.1 ②（spec 不是钉子）**：`scripts/a_migration_gate_preflight.py` 两处 fixture 的 spec 值
  换成 `SELFTEST_SPEC_NOT_A_NAIL`（现 `:122` 常量、`:1201` / `:1307` 引用），
  **不再硬编码** D 实测已过期的 `132fceb89f68`。`scripts/a_gate_build_drift_check.py` 的 build 轴判
  PASS/FAIL、**spec 轴只回显 `observation_only`**（`:262`），并在报告里明写
  「权威口径的固定写法 = `v1.5 / f19f61341cbe`（**不带 spec 值**）」（`:284`）。
  `scripts/a_exoneration_path_probe.py` 加历史封条。
- **裁定 29.3（不得引用不存在的文档）**：A 的 B7b note 引用的
  `docs/a_handoff_to_b_pending_bucket_tristate_20260929.md` **已补写**（此前只存在于 A 的对话上下文里，
  盘上没有 ⇒ D 实测无此文件，判 A 违规成立）。该缺陷 B 已于 11:48 自行修掉（收成 `is False` +
  单列 `cosign_not_required_arms`），D 在裁定 29.3 改判 CLOSED；A 的 B7b **保留**作三值感知护栏。
- **教训（A 认）**：把「三值语义」写进 note 却把证据留在对话里，等于**没有证据**。
  盘上没有的东西不得被引用 —— 与裁定 27⑤ 抓的「散文替代布尔断言」同型。

## ADR-A-010 分布层引用闸：**双峰改述为「强间隙分离」**（裁定 30 / DR-D29 六条，已实施已验收）

- 时间：2026-09-29 12:2x–12:4x 实施并登记
- 依据：裁定 30（DR-D29）六条、增补七 §20、B 表 `distribution_layer_note` 末句
  「A 的 21 actlog 子集是**另一个臂集**，须由 A 侧 join 本表算」
- **裁定（A 自裁，报 D 备案）**：A 的双峰预登记 §1 第 3 条「21 臂里受控成功落在 **4–9 的臂数 = 0**
  （中间是空的）」是**分布层**陈述，在 v1.2.1 口径下成立、在 **v1.5 / `f19f61341cbe`** 下被**恰好 1 臂**
  证伪（就是裁定 10 的免罪臂本尊，9/20）。⇒ 该写法**自此禁用**，准确定性改为
  「**强间隙分离（gap-separated）**：低簇 0–3（15 臂）／高簇 14–20（5 臂）／孤立 1 臂 = 9，
  **空带是 4–8 与 10–13**」。**双峰结论本身不倒**（§2 阈值、§4 臂清单、§5 判定规则、§12/§13 全部结论
  一字未改）—— 被推翻的只是「中间全空」这一种**写法**。
- **A 独立复算，与裁定 30 §20.1 逐格吻合**（不采信转述）：21 臂排序
  `[0×7,1×4,2×3,3,**9**,14,16,17,19,20]`，4–9 = **1**、低簇 **15**、高簇 **5**、4–8 = **0**、10–13 = **0**；
  48 臂直方图 `{0:23,1:9,2:6,3:2,4:1,9:2,14:1,16:1,17:1,19:1,20:1}`，4–9 = **3** 臂；
  valid 47 臂在 4–9 同为 **3**（唯一 INVALID 臂受控 = 0，不落该区间）。
  成因侧亦复核：v1.2.1 历史表该臂 `NOT_CITABLE_measurement_invalid` / `violated` / blown **0.212**，
  无效臂 **v1.2.1 = 7 → v1.5 = 1**。
- **变更内容**：
  1. `scripts/summarize_lerobot_act_arms.py`：新增 `distribution_arm_set()` / `distribution_layer()`，
     产出 `meta.distribution_layer`（三套臂集 `official_all`(48) / `measurement_valid`(47) /
     `actlog_subset`(21) 的直方图、区间计数、`characterization`、中间带臂名单；计数层
     `build_invariant` 与分布层 `build_dependent` 的显式声明；四限定清单；禁用写法表；
     历史口径须报 `n_artifacts` 的规则）。**所有数字从行里算，一个都不写死**；
     `build_fingerprint` **只锚 build 轴**，spec 写 `observation_only`（裁定 29.1）。
     新增只读参数 `--actlog-diag`（默认在 `--dir` 下找 `closed_loop_dz_diag_A.json`，读不到就跳过该臂集，不阻断）。
  2. **新脚本 `scripts/a_distribution_layer_check.py`**（10 判据 D1–D10 + `--selftest` 12 档）：
     D1 分布层块与构建指纹／D2「4–9 = 0」已为假且孤立臂 = 免罪臂／D3 强间隙分离定性／
     D4 A↔B↔live 三处 build 同一 + 21 臂计数逐格相同／D5 48 臂 4–9 = 3 且两套臂集同结果／
     **D6 禁用写法扫描（扫 A 自己的文档 + `daily_report.md`，A 不自免）**／D7 四限定齐备／
     D8 两层构建敏感性的双向实测证据／D9 历史口径须报 `n_artifacts`（warn）／D10 单构建纪律。
  3. `docs/a_bimodal_divergence_preregistration_20260928.md`：`:17`/`:181`/`:288` 三处**原文一字未动**，
     各在下方插入更正指针（现位于 `:18`/`:192`/`:309`）；新增 **§14**（事实复算表、可引用写法、
     一般规则、代码承载与非恒真对照表）。
  4. `daily_report.md:461`（09-28 19:40 A 线段「分布**双峰且中间是空的**……受控 4–9 的有效臂 0 个」）
     一并挂更正指针 —— 该句在 v1.2.1 口径下**当时是对的**（它明写「有效臂」「唯一的 9/20 是 INVALID 那个」），
     失效原因是免罪改了臂集，不是当时算错。
- **验收**：`DISTRIBUTION_LAYER_CHECK=OPEN / blocking_fail=0 / warn=0 / total_checks=10`（exit 0）；
  自检 **12/12**；重出表的构建迁移回归断言仍 **PASS，预期差异 201 / 非预期 0**
  （`attribution/dist_layer_regression_v15.json`）⇒ 分布层块是**纯附加**，计数层 / 分母 / 合计一格未动；
  既有两道闸未受扰动（迁移闸 24 / 迁移后闸 17，均 0 blocking 0 warn）。
  留档 `runs/infra/lerobot_act_env_20260928/distribution_layer/ruling30_check_20260929.json`。
- **非恒真（裁定 30.6 的双向自检）**：可红条件 =「21 臂 join 权威表后 4–9 计数 == 0」，现场实测 == **1** ⇒ 绿。
  自检覆盖**两个方向**：S2/S3 让 4–9 变 0 ⇒ D2/D3(/D5) 必须红；**S9** 同一句禁用写法但**带**更正指针 ⇒
  D6 必须**放行**（证明 D6 不是恒假）。若该臂将来重测（`scope=artifact` ⇒ 豁免随 sha256 失效）且新值落到
  ≤3 或 ≥14，D2/D3 自动变红并要求按新数据改写定性 —— 这是设计意图，不是回归。
- **A 补充一条 D 没写的观察**：48 臂全集的定性**不是** gap-separated 而是 `mixed`
  （`trimdone0_minmax_lr1e-5_s20k_seed0_replan1` 受控 **4** 占住 4–8 带）⇒「强间隙分离」
  **只对 21 actlog 臂集成立**，不得跨臂集挪用。这正是裁定 30.3 把「臂集」列为第一限定的原因；
  产物按臂集分别回显 `characterization`。

## ADR-A-011 增补七 §19-A⑤ **不照字面执行**，改为旁挂说明 + 机器护栏（提请 D 改判）

- §19-A⑤ 要求把 `attribution/arms_summary_v3.json` 的 meta 从 `v1.2.1 / e4f5ec887788 / 494d5f5babf9`
  刷成 `v1.5 / f19f61341cbe`。**D 的实测事实成立**（A 复核该文件 meta 确为该三值，mtime 11:08，48 臂）。
- **A 判定：照字面执行会导致退步，故不执行**，理由三条（全文见 `docs/a_handoff_to_d_20260929.md` §2）：
  1. 该文件是 `migration_regression_v121_to_v15.json` 的 **`baseline`**（实测字段可核）。刷它的 meta
     等于把迁移断言的**左操作数改成右操作数** ⇒ 断言退化为「v1.5 与 v1.5 比、差异 0」的**恒真判据**，
     DR-008 验收判据 3 失去机器担保。
  2. 刷了之后 A 侧**再无一份 v1.2.1 的 48 臂汇总表**（`regate_v121_pinned/` 留的是**逐臂裁定**，不是汇总表），
     与裁定 16.3 / 改判 7「旧表降级为历史口径（**不作废、必须仍可核**）」冲突。
  3. 形状与 D 自己在裁定 18②（DR-D15）驳回 A 的 B5 判据时一致 ——「照它『修』……属会导致退步的建议」。
- **替代落地（履行 §19-A⑤ 的实质意图：别把它当迁移后的权威表）**：
  ① `arms_summary_v3.json` **一字节未动**（mtime 仍 11:08）；
  ② 旁挂 `attribution/README_BASELINE.md`（三个文件各是什么 / 为什么 meta 停在 v1.2.1 是对的 /
  现值权威表在哪）；③ 机器护栏 **D8**（判 v1.2.1 历史表可读、`n_artifacts == 44`、无效臂 7、
  目标臂当时确为 `NOT_CITABLE_measurement_invalid`）—— 若有人真去刷了基线 meta，D8 立即变红。
  > **更正指针（append-only，原文不改；裁定 35.2 / DR-D34，memo 增补十二 §41）**：上句「D8 立即变红」
  > 在写下时是**过度声称** —— 当时 D8 对 `h_doc` 只读可读性 / `n_artifacts` / 臂行，**meta 三值一次都没读**，
  > 只刷 meta 时 D8 保持 GREEN。**补齐前不得引用该句**；已于 15:3x 补齐（term `historical_meta_is_v121`
  > 逐值比、覆盖两处操作数；变异 S13/S14/S15 各自单独判红；自检 15/15）⇒ 详见 **ADR-A-017**。
- **提请 D 二选一**：(a) 认可替代落地，§19-A⑤ 改判 CLOSED；(b) 仍要求刷 meta，则请同时指定
  **迁移断言的新基线从何而来**（A 无法在刷掉唯一 v1.2.1 汇总表后重建它：重判只会得到 v1.5 裁定）。
- A **不代判** D 的裁定；在 D 回复前，A 维持现状（不刷），并按 (a) 的口径引用。

## ADR-A-012 自查登记：A 新闸首版的**两个判据缺口** + 一处假红（恒真/恒假同型，第 4–6 次）

新闸首版自检 **10/12**，两档未被预期判据抓住；A 当场补牙后 **12/12**。按本仓「判据类工具一律自带反证」
的纪律主动登记（不藏）：

1. **D1 的 spec 判据是恒真形态**。原写法 =「`spec_axis` 不含 `spec` 字样 **或** 含 `observation_only`」。
   变异 `spec_axis = "must_match_c7fadabe8e3c"` 不含 `spec` 字样 ⇒ 第一个析取支直接放行，
   **裁定 29.1 的地雷复活而闸不响**。已改为**正向**要求：必须自称 `observation_only`
   **且**不得出现任何 `\b[0-9a-f]{12}\b` 指纹。
   **教训（与 DR-003 判据 3 同型）**：用「不含某字样」表达禁令，换个措辞就绕过去了；
   禁令要写成**正向的可核形状**，不要写成「缺少某个字符串」。
2. **D2 只核现场重算值、没核产物回显值**。把表里 `forbidden_window_4_9` 改成 0（= 把禁用写法当事实
   写进产物）时 D2 仍绿（它自己重算得 1），只有 D3/D5 抓住。已给 D2 补 `reported_equals_recomputed`。
   **教训（与裁定 29.3 立的规则同源）**：「产物声明」必须与「现场重算」**双向**比对，只信一边都会漏。
3. **D4 首版假红**（A 在放行前自己抓到，未流出）：按**同名键**比 A/B 两表，而 A 用 `success_raw`、
   B 用 `raw_success`（语义同、值同为 11）⇒ 21 臂全红。已改为**显式字段映射**
   `CROSS_TABLE_COUNT_FIELDS`，并保留「任一侧缺字段仍算红」（不静默跳过）。
   **与裁定 27 抓的 A 侧 L5/G2 假红完全同型**（照字面比键名 / 照文本扫锚点），本仓第 4 次。
   已把这句写成注释钉在 D4 上方，免得下一个人再踩。

**A 线自我纪律（即日生效）**：新判据落盘前必须**先跑变异自检**再报绿；自检档必须**同时**包含
「该红的红」与「该绿的绿」两个方向（只做前者会得到恒假闸，只做后者会得到恒真闸）。
自检没到 100% 不得声称判据可用。

## ADR-A-013 ack B 的 DR-012（lerobot 权威 pin）+ 给 A 自己的行为约束补代码承载（已实施）

- **ack**：`docs/lerobot_env_reinstall_pin_20260929.md`（B 线，DR-012，12:18）已履行增补七 §19-B④
  （把 lerobot 的安装方式与 commit pin 摘出来交给 C/A）。A 采纳其 §2 的 pin 表**原样**，
  **A 不自己定 pin**。三条对 A 有直接影响的实测，A 复核认可：
  1. `/root/venvs/` 下**只剩 `rlrobot`** ⇒ 缺口的准确表述不是「rlrobot 少一个 lerobot 包」，
     而是「**A 的训练/评测环境整体需按 installer 重建**」（A 实测：`ls /root/venvs/` = `rlrobot`；
     系统 `python3` 与 `rlrobot` 解释器里 `lerobot` 均 MISSING，`rlrobot` 里 robosuite/mujoco OK）。
  2. **只验 `import lerobot` 成功是恒真判据**（B §4/§5.2）：D 在裁定 29.4 提的离线候选源
     `lerobot_0cf8648` 的 HEAD 比 tag `v0.4.4` **落后 488 commit**、`pyproject.toml` 写 `version = "0.1.0"`
     ⇒ 从它装出来 import 照样成功，而 48 臂权威表依赖的官方 ACT 入口是 **0.4.4** 的。
  3. 离线回退必须先 `checkout v0.4.4`（= `8fff0fde7c79f23a93d845d1a50e985de01f8b8a`），
     且**不得动他人的工作副本**；`sqzhang26/gaoyuxuan/lerobot` 与 `clzhang25/LIBERO/lerobot` 仍不得当 pin。
- **A 自裁（报 D 备案）**：增补七 §19-A④「lerobot 未装好前不要声称任何新训练 / 评测复现」是一条
  **只写在备忘里的行为约束，没有代码承载**。按本仓已立的纪律（裁定 29 附带登记：任何裁定落盘前必须回答
  「**哪一行代码执行它**」；答不出的只能落 `PENDING_IMPL`），A 给它补上承载：
  **新脚本 `scripts/a_env_readiness_gate.py`**（7 判据 E1–E7 + `--selftest` 10 档），
  判 `A_NEW_REPRO_CLAIMS = ALLOWED / BLOCKED`，CLOSED 时 exit 1 并打印「此刻允许声称什么 / 不得声称什么」。
  - **E1** 训练 venv 解释器存在（pin 路径，**不是** rlrobot）／**E2** `lerobot.__version__ == 0.4.4`
    （**不是**只验 importable，直接对应 B §5.2 的恒真判据警告）／**E3** 官方 ACT 入口真能 import
    + `lerobot_train --help` 真能跑／**E4** 评测 venv 齐备（robosuite 1.5.2 / numpy 2.4.6 / mujoco / lerobot
    同解释器）／**E5** 安装来源可核（wheel 还是源装；源装必须能追到 commit）／
    **E6** C 的 manifest 已把 lerobot 探通且不再声明 A 被阻／**E7**（warn）两份 lock 在位。
  - **现场实测 = `BLOCKED`，blocking_fail=6（E1–E6）、warn=0、total_checks=7、exit 1**；
    E7 PASS（两份 lock 在位）。留档
    `runs/infra/lerobot_act_env_20260928/env_readiness/a_env_readiness_20260929.json`。
  - **非恒真**：自检 10 档覆盖两个方向 —— **S2**（从落后 488 commit 的源装成 **0.1.0**、import 仍成功）
    ⇒ E2 必须红（这就是 B §4 的真实反例，也是本闸存在的主要理由）；**S5**（版本对但入口 import 不了）
    ⇒ E3 必须红（证明 E2 绿不等于能用）；**S1**（合规 fixture）⇒ 必须 ALLOWED（证明不是恒假）。
    另有 S3 全缺 / S4 训练 venv 不存在（= 0929 检修真实现场）/ S6 eval numpy 装成 train 的值 /
    S7 源装不回显 commit / S8 manifest 仍声明被阻（= 当前真实状态）/ S9 manifest 不可读 / S10 lock 缺失只 WARN。
  - **一处 fixture 自相矛盾被自检抓出并修掉**（S3 首版只覆盖版本 blob、留着 `act_entrypoints ok=True`）：
    那不是判据缺口，是 fixture 不自洽 ⇒ 已改成 lerobot 全缺时入口/来源探针一并失败。
    教训：**fixture 内部必须自洽**，否则自检档会对着一个不可能存在的现场判绿/判红。
- **A 的处置**：`bash scripts/install_lerobot_act_env.sh` 属**环境重建**，按裁定 29.4 的分工是 **C 的 P0**
  （C 已把 lerobot 加进 `probe_modules` 并写了专门的 `lerobot` 块，12:14 manifest）；
  **A 不代跑**，以免与 C 同时建同一份 venv 造成半成品。A 只在本闸变 ALLOWED 后才声称新复现。
- **B §8 那两条 A 侧 T17 待办的排序更正**（`docs/b_handoff_to_a_20260929.md` §8）：
  `run_act_lift_runtime_failure_audit.py:36,39` 的 `goal_id` 硬编码 `'lift'`、`train_act_lift.py` policy 不接收 goal
  —— 这两条**要动训练侧代码**，属「新训练」范畴 ⇒ **在 E1–E6 变绿之前 A 不做**（做了也无法验证）。
  已写进 `docs/a_handoff_to_d_20260929.md` §6 请 D 确认这个排序理解。

## ADR-A-014 执行裁定 32 / DR-D31：A 接手 lerobot 环境重建（**并作废本文件 ADR-A-013 末尾的两条排序判断**）

**依据**：`rl_harness_supervision/d_handoff_to_a_20260929.md`（D 执行单，8 节）、
`supervisor_memo_20260929.md` 增补九 §26–§29（裁定 32）、`work/decisions/decisions_20260929.md` DR-D31。
用户指令：「让 A 自己安装环境」。

### 1. 作废登记（**本文件自己的两条旧判断**，不是别人的）

ADR-A-013 末尾写过两条，现按裁定 32 **作废**（append-only：不改上文，在此显式点名）：

| 旧判断（ADR-A-013 原文摘） | 现状 |
|---|---|
| 「`bash scripts/install_lerobot_act_env.sh` 属环境重建，按裁定 29.4 的分工是 **C 的 P0**…**A 不代跑**，以免与 C 同时建同一份 venv 造成半成品」 | **作废**。裁定 31.5 附条的「B 执行安装 → A 验证 → C 探针」分派已被 D 改判：**A 执行安装 + 门槛验证 + smoke + 重出 manifest + 登记断点**；B 只提供权威 pin 并验收；C 只出探针。D 给的理由：安装是**执行动作**不是判据动作，谁用这个环境跑训练谁负责它装对了 |
| 「B §8 那两条 A 侧 T17 待办**要动训练侧代码**，属『新训练』范畴 ⇒ **在 E1–E6 变绿之前 A 不做**（做了也无法验证）」 | **部分作废**。D 执行单 §7.4 与用户指令明确：这 2 项**不需要 GPU**，可与装环境**并行**做。A 照做并已闭合。**仍然成立的那一半**：它们的**训练侧验证**（真跑一臂带 goal 的训练）确实要等就绪闸 ALLOWED，A 未做、也未主张 |

### 2. 路线变更（口径，不是实验结果 ⇒ 属本目录）

- **`LOCK_OUT` 必须覆写**已升级为 A 线的 P0 前置动作：installer `:57`/`:85` 会 `pip freeze > "$LOCK_OUT/…"`，
  而 `LOCK_OUT` 默认值就是 `runs/infra/lerobot_act_env_20260928` ⇒ **照默认跑一次就就地覆写 48 臂的唯一溯源证据**。
  A 的处置：覆写到 `runs/infra/a_lerobot_env_rebuild_20260929`。
  **可核证据**（两条独立）：0928 两份原件 mtime 仍是 `09-28 14:56:45` / `15:24:06`（**早于** 0929 断点 10:45:56），
  且 sha256（`68a38731c5b5` / `b6db07e2e31c`）与 C 的逐字节备份相同。
- **不改路径、用软链**：仓里 73 个文件硬编码 `/root/venvs` ⇒ `ln -sfn` 到 NFS 上的
  `.codex-persist/envs/lerobot_{act,eval}`，并**实测经软链的调用**（`sys.executable` 回显软链路径）。
- **验收判据是版本、不是 importable**：`lerobot.__version__ == "0.4.4"` + 回显安装来源（dist-info ⇒ wheel 装）
  + 两条门槛（`lerobot_train --help` = 2414 行、ACTConfig/ACTPolicy 导入）。
- **断点单列**：`BP-20260929-lerobot-env-rebuild`，**不与 C 的 `BP-20260929-venv-rebuild` 合并**
  （`invalidates` 范围不同：C 废 rlrobot/robosuite 侧复现，A 废官方 ACT 训练与真值评测）。
- **T17 A 侧的兼容纪律**：goal 相关参数一律**关键字、缺省关闭**；`collect()` 签名与返回契约**未变**；
  缺省路径**不写** `goal_vocab`/`goal_dim` 两个 ckpt 键。兼容性由**动态载入 git HEAD 做对照**来证明（G5/G6），
  不由「我觉得没破坏」证明。

### 3. A 现在能声称什么 / 不能声称什么（裁定 29.4 的行为约束仍生效）

- ✅ 环境**可用**：smoke 三步全 0（数据集 v3.0 写 API / 官方 ACT 训练 + CUDA / 评测 venv 闭环真值）。
- ❌ 任何**新训练/新评测复现**主张：`reproduction_claims_blocked=true`，两条独立原因 ——
  ① 就绪闸仍 `BLOCKED`，唯一红项 **E6**（它判的是「**C 的** manifest 已把 lerobot 探通」，A 不改 C 的文件，
  解除动作在 C 手里）；② 新 lock 与 0928 有 **3 处差异**（`ImageIO` 2.37.4→2.38.0 ×2、`uv` 0.12.19→0.12.17），
  按 D §6.3「在 D 裁定前不得声称任何跨断点复现」。两个包都**不是 pin 项**、都**不在 48 臂链路上**，
  但 **A 不自行判定「可忽略」**，已逐条报 D。
- ❌ 「已学出 A↔B 方向差异」：真帧 teacher 只做 A→B，`lift_B_to_A` 组**如实记 `n_rows=0`**
  （不伪造 0/0、不拿 A→B 的帧冒充）⇒ 只能说「goal 已接进 policy 输入与账本」。

**证据与逐条差异解释不在本目录**（DR-001：实验结果/产物/日志不写入 `work/decisions/`）：
见 `docs/a_env_rebuild_acceptance_20260929.md`、`docs/a_handoff_to_b_anchor_shift_20260929.md`、
`runs/infra/a_env_manifest_20260929.json`、`runs/infra/a_t17_goal_conditioning.json`。

## ADR-A-015 自查登记：本轮 A 自己的 **4 起「判据/脚本错、产物对」**（恒真/恒假同型，本仓今日第 7–10 起）

B 在日报 §6 记了「本仓今天第 6 起同型」。A 本轮又贡献 **4 起**，全部是**A 自己的工具错**、
**没有一起是产物或环境错**。逐条登记（不隐藏，因为这类缺陷的危险在于它会**指向错误的结论**）：

| # | 现场 | 错在哪 | 若不发现会怎样 | 处置 |
|---|---|---|---|---|
| 1 | 第一轮 env smoke 的 S2 | 脚本写 `R=$PWD/$B`，而 `$B` 已是**绝对**路径 ⇒ `--dataset.root` 变成 `/repo//repo/…` | lerobot 找不到本地数据集会**回落去 `huggingface.co` 查 refs**，撞本机代理 503 ⇒ 报错长得像**网络/环境故障**。差点被登记成「新环境跑不了官方训练」 | 已修（`R=$B`）；并单独用探针证明 **root 正确时全程离线可训**（`probe_train.log`，2 步 `PROBE_EXIT=0`）。这条**操作事实**已写进 `docs/lerobot_act_env_setup_20260928.md` 的 09-29 附记第 2 条，防止下一个人再误判 |
| 2 | T17 自检 **G8** | 断言写 `fake_calls == ((1,2,3),)`，而 `fake_calls` 是 **list** ⇒ 恒不等 | 把**正确**的分组行为判成 FAIL（假红），进而把「A 侧 T17 贯通」判成不成立 | 已修为 `== [(1,2,3)]`；现 9/9 PASS |
| 3 | T17 自检 **M3 变异体** | `caught` 语义写反：变异体「静默映射」**不抛**异常才是被抓，A 写成 `caught = 抛了异常` | `teeth.non_vacuous` 变 **false** ⇒ 会得出「G3 是恒真判据」的**错误自我否定**，逼着去修一个本来正确的断言 | 已修为 `caught = not m3_refused`，并额外回显 `mutant_still_refused`（用于识别「变异体本身写废了」这种情况）；现 teeth **5/5** |
| 4 | T17 端到端 smoke 的 **T3** | 校验代码读 `goal_coverage[...]["n_rows"]`，而 `config.json` 里那个键叫 **`train_rows`**（`n_rows` 是 `collect_by_goal` **返回值**的键名） | `KeyError` ⇒ T3 假红，会把**正确的产物**（B→A 组如实 0 行）判成不合格 | 已修并重跑（`T3_OK=True`）。**产物当时就是对的**，A 在回执 §8.2 单独登记了这一点 |

### 共同根因与本线纪律（即日生效，续 裁定 30 的 A 线自我纪律）

4 起的共同形态：**判据/脚本与被判物同名不同物**（绝对 vs 相对路径、list vs tuple、
「被抓」的方向、`n_rows` vs `train_rows`）。它们的危险**不在报错**，而在于报错**指向错误对象** ——
第 1 起会把脚本 bug 说成环境坏，第 3 起会把正确断言说成恒真。

⇒ A 线新增两条自我要求：
1. **自检报红时，先证明「红的是判据还是产物」**：用第二个独立途径复核同一事实
   （本轮做法：把 git HEAD 动态载入做对照 / 单独跑最小探针 / 直接 dump 产物键名），**不得**只改判据让它变绿。
2. **断言里的字面量必须有出处**：容器类型（list/tuple）、键名（`train_rows`）一律**从产物或实现里取**，
   不凭记忆写。这与「goal 词表只读 `LearnerConfig.goals` 不抄字面量」是同一条纪律的两个面。

**未受影响的部分**（已独立复核）：0928 两份溯源 lock（sha256 + mtime 双证据）、
`attribution/arms_summary_v3.json`、`attribution/dist_layer_regression_v15.json`、迁移闸/分布层闸的既有自检档
—— 本轮 4 起缺陷**都在新增的 A 侧工具里**，未触及任何既有判据或产物。

## ADR-A-016 ack 裁定 33 / 34（DR-D32 / DR-D33）：3 处 lock 差异**放行**，A 侧 4 项动作已落地

**依据**：`supervisor_memo_20260929.md` 增补十 §30–§35（裁定 33）/ 增补十一 §36–§39（裁定 34）、
`work/decisions/decisions_20260929.md` DR-D32 / DR-D33、`rl_harness_supervision/d_handoff_to_a_20260929.md` **§9 附记**（14:5x）。
附记明写「上文与本附记冲突处，**以本附记为准**」⇒ 本条同时作废 A 前面的两处判断。

### 1. ack 与作废登记

| D 的裁定 | A 的处置 |
|---|---|
| **34.1**：3 处 lock 差异**放行**（`ImageIO 2.37.4→2.38.0` 两份、`uv 0.12.19→0.12.17` 仅 act），但豁免**按包按链路**授 | **ack**。引用纪律逐字抄进机器承载（`a_env_manifest.py` 的 `lock_diff_waiver` 段 + `a_env_provenance.py` 的 `LOCK_DIFF_WAIVER`）：引用必须**点名包与版本**、**不得**写成「lock 差异已裁定可忽略」；任何新增差异**重新报 D**；**可红条件**（若发现二者在 48 臂 import 面上）⇒ 自动作废 |
| **34.1**：A 提议的 `--override imageio==2.37.4` 重装**不批准** | **ack，A 不重建**。ADR-A-014 §3 与回执 §3.3 里 A 自己列的「若 D 判定要对齐 imageio 就重建到新目录再原子切换」那条路径**作废** |
| **34.1**：根因归 B 修，钉**实际装成**的 `imageio==2.38.0` / `uv==0.12.17`（事实源口径，**不回退**） | **ack，A 不改 installer**（B 的写入边界）。但 A 实测发现 **B 14:49 钉的是 `IMAGEIO=2.37.4`，与裁定相反** ⇒ 已在 `docs/a_handoff_to_b_anchor_shift_20260929.md` §2.1 与回执 §9.1 告知 B（不改 B 的文件） |
| **34.1 末**：「本裁定不解除 E6」⇒ A 仍不得声称新训练/新评测复现 | **ack**。就绪闸现值仍 `BLOCKED`（`blocking_fail` 6 → **1**，唯一红项 E6）；A 未开任何新训练/新评测 |
| **33**：(甲) 自足已裁；`/root/venvs/rlrobot` 14:35 已切软链、`ssp=false`；三条软链登记 `symlinks.json`、`bootstrap` 自动重放 | **ack**。回执 §4 的 rlrobot 行由 `true` +「甲/乙尚未裁定，A 不代判」更正为 **`false` + realpath**；回执 §9 里「下次检修要手工 `ln -sfn`」那段**作废**（`bootstrap` 会做）。A 现场复核实测：三个 venv 现在**全是软链**、`ssp` **全为 false** |
| **33**：§2「不要用 `mkvenv`」已被 D 的修复取代，但**两个 lerobot venv 仍走 installer**（裁定 32.2 第 1 条不变） | **ack**。A §3 的做法（走 installer + 三个路径类覆写）**本来就是对的**，无需返工 |
| **附记 §9.5**：A 的锚点移位单做法正确，D 认可；A **不需要再做任何事** | **ack**。A 不再动作，除非 B 回来问语义（D 已指出 `b_selfcheck_goal_conditioning_t17.py:452` 那条**语义变了**，B 要改的是期望值不只是行号） |

### 2. D 附记 §9.4 派给 A 的两项：**已落地**

1. **回执 §4 两行刷新**：`rlrobot` 行 `ssp` `true → **false**`，并回显 `realpath`
   （`readlink -f /root/venvs/<name>`；**不是** `bin/python` 的 realpath —— 后者会再解一层落到
   `/opt/conda/bin/python3.11`，那是 base 解释器、不是 venv 路径。A 的旁挂件首版正栽在这里，见 §3）。
2. **lerobot 两个 venv 的冷/热导入基线**（对齐 D 的 rlrobot 对照口径）：
   `lerobot_act` 复合 **冷 15.74 s / 热 5.38 s**；`lerobot_eval` 复合 **冷 7.71 s / 热 3.03 s**；
   `import torch` 冷 **4.68 / 4.55 s**、热 **1.86 / 1.82 s**。产物
   `runs/infra/a_lerobot_env_rebuild_20260929/cold_import_baseline{,_v2}.json`（两轮都留档）。
   **口径更正（如实记）**：① `import lerobot` 只有 0.05–0.07 s（其 `__init__` 仅读 `importlib.metadata`、
   **不拉 torch**）⇒ **不能当冷导入探针**；② 首版只逐出 4 个目录 ⇒ 其冷值是**下界**，
   第二轮改为逐出**整份 site-packages**（act 31617 文件 / 6.7 GB；eval 40084 文件 / 7.7 GB）；
   ③ D 附记给的命令用 `/usr/bin/time -f`，**本机没有这个文件** ⇒ A 用 Python 子进程计时替代；
   ④ 逐出用 `posix_fadvise(DONTNEED)` **定点**做，**不用** `drop_caches`（会清整机缓存、影响同机 B/C）。
   **结论与 D 同向**：冷比热慢 2.5–3 倍，import 在训练循环里只发生一次（一臂 20k 步是小时级）
   ⇒ **NFS venv 不是吞吐瓶颈**，A 侧**不需要**首轮预热。A **不**把「A 的 torch 冷值 4.6 s < D 的 rlrobot 14.51 s」
   读成「A 比 D 快」：两者不是同一口径（torch 版本/文件布局不同，D 的冷值可能来自整机 drop_caches）。

### 3. 新增义务的承载 + A 自查出的第 5 起同型缺陷

- **D 附记 §9.1 末的新硬义务**：「今后的新训练/新评测产物**必须回显新 lock 的 sha256**」。
  承载 = 新模块 **`scripts/a_env_provenance.py`**，在产物目录写 **`env_provenance.json`** 旁挂件
  （含新旧两份 lock 的 sha256、`venv_realpath`、torch/lerobot/robosuite/mujoco/numpy 语义值、cuda、
  断点 id、就绪闸现值、**裁定 34.1 的放行范围与引用纪律**、`claim_discipline`）。
  **为什么旁挂而不是加键**：加键会改动既有产物 schema，而缺省路径必须与改动前逐项相同（G5/G6 的硬前提）。
  已接进 `train_act_lift.py` 与 `run_act_lift_runtime_failure_audit.py`，两处 **`try/except` 非致命**
  （溯源写不出来**不得**让训练失败，但必须大声 `[WARN]` —— 静默没有溯源正是本模块要治的病）。
  实测：`config.json` 与 ckpt 的键集**未变**（`NO_PROVENANCE_KEYS=True`），旁挂件正常落地。
- **第 5 起同型（接 ADR-A-015）**：旁挂件首版把 `venv_realpath` 写成 `exe.resolve().parents[1]`，
  而 venv 的 `bin/python` 本身是指向 base 的软链 ⇒ resolve 一路解到 `/opt/conda/bin/python3.11`，
  `parents[1]` 变成 **`/opt/conda`**，等于**把 A 的 NFS venv 说成了 conda**。
  这正是 D 附记 §9.4 特意要求「回显 realpath」要防的那类错。已修（先按**未解析**路径取 venv 根、再对**目录** realpath），
  并分成三个字段：`venv_as_invoked` / `venv_realpath` / `python_binary_realpath`（后者 = base 解释器，与 `pyvenv.cfg` 的 `executable` 同源）。
  **一般规则（与 D 的「判据的每一个输入都必须与被描述的对象同源」同族）**：
  **软链上的 `resolve()` 会穿透多层，取「哪一层的真身」必须显式声明**，不能默认「解到底就是我要的」。

## ADR-A-017 执行裁定 35 / 36（DR-D34 / DR-D35）：D8 补牙（P0）+ 断言产物自带护栏（P1）+ E6 散文同源化（P2）+ **A 线解封**

依据：`rl_harness_supervision/supervisor_memo_20260929.md` 增补十二 §40–§43、增补十三 §44–§49；
`rl_harness_supervision/d_handoff_to_a_20260929.md` §9.6 / **§9.7**。全程只读 D/B/C 的产物，未改任何他人文件。

### 1. ack 裁定 35.1（选 (a)）：基线 meta **不刷**，一般规则采纳

`§19-A⑤` 改判 CLOSED；`attribution/arms_summary_v3.json` 继续**一字节不动**（本轮复核 sha256
`3f23215a7ed3…`、mtime **11:08:55** 未变）。D 的一般规则已采纳为 A 的引用纪律：
**「把口径刷新到当前值」这类要求，先问「这个文件是不是某个断言的操作数」** ——
基线/历史口径文件的价值恰恰在于它**停在旧值**。

### 2. P0 已落地：D8 补 term `historical_meta_is_v121` + 变异 S13/S14/S15（**第 6 起同型自查**）

- **缺陷本体（D 代码级实证，A 复核成立）**：A 在 `docs/a_handoff_to_d_20260929.md:51` 写
  「若有人真去刷了基线 meta，**D8 立即变红**」，而当时 D8 的七个 term 对 `h_doc` 只读
  **可读性 / `n_artifacts` / 臂行**，`meta` 三值**一次都没读** ⇒ 只刷 meta 时 D8 保持 GREEN。
  按裁定 27.1，那是**恒真闸 = 没有闸**；那句话是**过度声称**，补齐前不得被引用
  （三处引用点已挂 append-only 更正指针：`docs/a_handoff_to_d_20260929.md`、本文件 ADR-A-011、`daily_report.md`）。
- **修法**：`scripts/a_distribution_layer_check.py` 新增 term **`historical_meta_is_v121`**，
  **逐值**比 `v1.2.1 / e4f5ec887788 / 494d5f5babf9`（不是比「非空」），并覆盖**两处**操作数 ——
  ① v1.2.1 历史表 `runs/infra/b_official_arms/reclassification.build_e4f5ec887788.json`（三值在**顶层、字符串**）；
  ② `attribution/arms_summary_v3.json`（三值在 **`meta` 下、单元素列表**，= §43-1 可红条件点名的那份）。
  三值常量在本脚本**独立写死一份**，不与 summarizer / 迁移闸共用（生产者与被检者同源 = 恒真，
  与本文件 `FORBIDDEN` 那条注释同一规矩）。形态不符（空列表 / 多元素列表 / 键缺失）一律判**不符**。
- **牙（声称「会红」的护栏必须演示一次红）**：**S13**（两处一起刷成 `v1.5 / f19f61341cbe / c7fadabe8e3c`）、
  **S14**（**只**刷 ②，即 A 当初点名的那处）、**S15**（**只**刷 ①）——三者各自**单独**把 D8 判红
  （`gate=CLOSED(D8)`，无误伤其它判据），真实现场仍 **OPEN**，自检 **12/12 → 15/15**。
  **S14/S15 是 A 自行加的**：D 只要求 S13，但「两处一起刷」红了并不能证明**每一处**都被覆盖，
  单操作数变异才排除「term 只读了其中一处」。编号按 D 的自我更正（增补十三 §44-1）用 `S13`（`S11`/`S12` 已占用）。
  **全程只在 fixture 的内存深拷贝里刷，未碰任何真文件**（动真文件本身就是裁定 35.1 禁止的事）。
- **留档**：`runs/infra/lerobot_act_env_20260928/distribution_layer/ruling35_check_20260929_d8meta.json`
  （**新文件**，未覆盖 12:38 的 `ruling30_check_20260929.json`）：`verdict=OPEN`、`blocking_fail=[]`、
  `n_checks=10`、D8 八项全真，并回显两处操作数的三值**与各自来源路径**。
- **第 6 起同型（接 ADR-A-015 的 5 起）**：**把「我加了判据」当成「判据覆盖了这件事」**。
  与前 5 起的区别：前 5 起是「判据/脚本错、产物对」，这一起是**判据对、但被声称覆盖了它没覆盖的场景**。
  **纪律**：声称某个闸「会红」时，必须**当场指出它读的是哪个字段**；读不到的字段 = 覆盖不到。

### 3. P1 已落地：迁移断言产物**自带护栏**（写新文件，不覆盖 12:01 那份）

`scripts/summarize_lerobot_act_arms.py` 的 `regression_check()` 报告新增两键：
`baseline_meta = {gate_version, gate_build, gate_spec_sha256}`（实测 `["v1.2.1"] / ["e4f5ec887788"] /
["494d5f5babf9"]`）+ `baseline_meta_must_not_be_refreshed`（指向 DR-D34 / 裁定 35.1，写明「刷它 =
把断言的左操作数改成右操作数」）。产物：
`runs/infra/lerobot_act_env_20260928/attribution/migration_regression_v121_to_v15_ruling34.json`。
- **重跑不带 `--json-out`** ⇒ **冻结的 48 臂权威表未被改写**：`arms_summary.json` sha256 `cac7588a4e86…`、
  mtime **12:33:23** 前后逐字未变；`arms_summary_v3.json` 同上（11:08:55）；12:01 那份断言产物
  sha256 `daf914bee131…`、mtime **12:01:15** 亦未变。
- **断言结论未漂**：`verdict=PASS`、预期差异 **201** 处 / 非预期 **0** 处、新增行级键 5 个，与 12:01 逐项相同；
  新旧两份产物**只差 `generated_at` + 那两个新键**（结构对比可核）。

### 4. P2 已落地：E6 的旁挂散文改为**由观测生成**（判据一字未动）

D §9.7-5 撞到的自相矛盾（E6=PASS 而 `note` 硬写「现值 `importable=false` ⇒ 本条现在**应当红**」）已修：
`scripts/a_env_readiness_gate.py` 的 E6 `note` 现在**从 manifest 取值生成**（回显
`probe_modules.lerobot.version` / `reproduction_claims_blocked.blocked` / `env_fully_restored` /
`generated_at` + 「本条=绿/红」），历史那段**显式标注「12:14–15:30 期间，已过期，勿当现值引用」**；
自测 S8 的标签去掉「当前真实状态」改为「12:14–15:30 的**历史**状态」。**五个 term 与变异期望未动**
（D 已核它们有牙），自检 **10/10**。一般规则采纳：**并列两个陈述之前，先确认它们同源**（裁定 36.4）。

### 5. **A 线解封**（C 15:30 重出 manifest ⇒ E6 转绿），但「解封」有边界

A 只读复核：C 的 `runs/infra/c_env_manifest_20260929.json` `generated_at=15:30:12`、
`env_fully_restored=true`、`probe_modules.lerobot.version=0.4.4`（`probe_kind=semantic`、
`probed_in=lerobot_act` + `also_probed_in=lerobot_eval`）⇒ A 的就绪闸
**`A_NEW_REPRO_CLAIMS=ALLOWED`、`blocking_fail=0 / warn=0 / total_checks=7`**（E1–E7 全 PASS）。
留档 `runs/infra/a_lerobot_env_rebuild_20260929/readiness_gate_post_e6_20260929.json`。
- **现在可以声称**：新的训练/评测**复现**主张（含 B §8 两条 T17 的**训练侧验证**、§8 晋级条件①的推进）。
  **每条主张必须自带**：① 构建指纹 **`v1.5 / f19f61341cbe`**（不带 spec 值）② 口径名
  ③ **新 lock 的 sha256** —— 即 `scripts/a_env_provenance.py` 的 `env_provenance.json`，
  它已从「P1 接线」**升为「第一次真跑就必须有」**（D §9.7-1）。
- **解封 ≠ 旧产物自动跨断点有效**：`BP-20260929-lerobot-envs-wiped.invalidates` 明写依赖这两个 venv 的
  训练/评测产物（含 48 臂权威表所依据的那批评测）跨断点、**必须在新环境上重跑才继续有效**。
  旧表仍**可作历史口径引用**（裁定 16.3 / 改判 7：不作废、必须仍可核），但**不得**当作「已在当前环境复现」。
- **仍不做**：不改 C 的 manifest、不执行 git 写（B 的单写者职责）、不覆写 0928 任何溯源件、
  **不动** `attribution/arms_summary_v3.json`。
- **引用纪律不变**：3 处 lock 差异放行必须**点名包与版本**（`ImageIO 2.37.4→2.38.0` 两份、
  `uv 0.12.19→0.12.17` 仅 act），不得写成「lock 差异已裁定可忽略」；新增差异**重新报 D**。
  A §9.1 提请的那条已闭合：裁定 34.1 把 `imageio==2.38.0` / `uv==0.12.17` 定为**事实源口径**，
  B 已在 `scripts/install_lerobot_act_env.sh:52-53` 钉上（15:07）。

### 6. T17 端到端 smoke 重跑完成（产物与最终代码同源）

`runs/infra/a_t17_goal_smoke_20260929/smoke_t17.log`（15:17:00 起、15:18:36 收尾）：
**T1**（缺省路径，ckpt/config 无 goal 键）exit 0｜**T2**（`--goals default`，BC 按 goal 分组 + 词表回显）exit 0｜
**T3** 键集对照 `T3_OK=True`（缺省 `default_has_goal_keys=false`、goal 侧 `goal_dim=2` /
词表 `["lift_A_to_B","lift_B_to_A"]`、net0 权重 60 → 62、`goal_coverage` 如实记
`lift_B_to_A` 真帧 **0 行**、`learnable_from_real_frames=false`）｜**T4**（带词表 ckpt + `--goal-plan alternate`，
换向与 epoch 一起进账本）exit 0｜**T5**（goal-blind ckpt 要求 alternate）**exit 1 + `LearnerRefused` +
未产出任何产物**（= 正确拒绝，不伪造贯通证据）｜**T6**（缺省路径）exit 0，账本
`goal_id="lift"` / `epoch=1` / `goal_source="task_name_fallback(ckpt 无 goal_vocab ⇒ 非 goal 条件)"` /
`policy_goal_conditioned=false`。旁挂件 `env_provenance.json` 正常落地（当时 `gate=BLOCKED`、
`new_lock_sha12=186579b96bce` —— 那是**当时**的真值，按 append-only 不改写）。
单元自检同批复跑 **9/9 + teeth 5/5**。

---

## ADR-A-018 执行 (甲)：B §8 两条训练侧验证**完成**（真跑规模，非 smoke）+ A 自查**第 7 / 8 起**同型（判据错、产物对）

**时间**：2026-09-29 16:16–16:38（真跑 16:16:49–16:20:08｜闸 16:20–16:25｜终验 16:35–16:38）
**触发**：用户「你这边开始跑训练测验证吧」+ B→A 交接单 §8 两条 A 侧待办（B 已实测：当前 2 项阻塞**都在 A 侧**，且**不需 GPU**，可与装环境并行）
**解释器**：`/root/venvs/lerobot_eval/bin/python`（realpath `/opt/conda/bin/python3.11`；venv realpath 在 NFS `.codex-persist/envs/lerobot_eval`）
**产物根**：`runs/infra/a_t17_train_verify_20260929/`（全在 A 自己目录）

### 1. 真跑规模（**不是 smoke**；两路各自独立真跑）

| 路 | 目录 | episodes | horizon | epochs | seed | train / val 行 | `net.0` 入维 | `best_val_mse` | 耗时 |
|---|---|---|---|---|---|---|---|---|---|
| goal 路（`--goals default`） | `goal_path/` | 24 / 8 | 300 | 40 | 0 | **7128 / 2376** | **62** = obs 60 + goal 2 | **0.02650517039000988** | 100 s |
| 缺省对照（goal-blind） | `default_path/` | 24 / 8 | 300 | 40 | 0 | 7128 / 2376 | **60** | 0.025898998603224754 | 99 s |

两路 `state_dict` 键集**完全相同**（`net.{0,2,4}.{weight,bias}`，实测 `==` 为 `True`）⇒ goal 只**加宽第一层输入**、
**不新增任何键**（V1 `no_extra_state_dict_keys=true`；向后兼容是硬要求不是风格）。
`driver.log`：`R1_EXIT=0`（16:16:49→16:18:29）、`R2_EXIT=0`（16:18:29→16:20:08）。

### 2. 新验证闸 `scripts/a_verify_t17_train_side.py`：**OPEN 8/8**，变异自检 **9/9**

**V1** 词表读 `LearnerConfig.goals` 单一事实源（不抄字面量）+ goal 进第一层｜**V2** **训练后**的 policy 仍对 goal 敏感（不是初始化假象）｜
**V3** BC 按 goal 分组、缺方向如实记 0 行不冒充｜**V4** 缺省路径真跑产物**无 goal 键**（0924 基线仍可原样复算）｜
**V5** 两路都带 `env_provenance.json` 且新旧 lock sha256 逐字相同｜**V6** 真跑 ckpt + `--goal-plan alternate`：换向与 epoch **一起**进账本｜
**V7** goal-blind ckpt 要求 alternate ⇒ **拒绝且不伪造产物**｜**V8** 缺省路径退回任务名占位并**标注来源**。
8 条全 `blocking=true`；`verdict=OPEN`、`blocking_fail=[]`、`warn=0`（`t17_train_side_verify_v2.json`，`generated_at=2026-09-29T16:25:28+0800`）。
9 个变异体（T1 真实现场 + M1 / **M1b** / M2 / M3 / M3b / M4 / M5 / M6）**全被抓** ⇒ 判据非恒真。

### 3. 定量边界（**这一段决定能说什么**）

训练后 goal 敏感度（在 **ckpt 上测，不是初始化**，`n_states=8`）：
- **输出空间**：`mean|Δgoal| = 0.00145` vs `mean|Δstate| = 0.52208` ⇒ 比 **0.0028**
  （`max|Δgoal| = 0.01120`、跨 state 的 Δ 标准差 `0.00369` ⇒ **不是常量偏置**）
- **权重空间**：goal 列 absmax **0.13520** vs state 列 absmax **0.13995** ⇒ 比 **0.966**

**可声称**：goal 贯通成立 —— 计算图已 goal 条件化、真跑规模下通路**没被压成 0**、账本随 A↔B 换向且 epoch 同步递增、
拒绝语义与 C 的 `LearnerRefused` 同一套（A 不另造第二种异常类型）。
**不得声称「已学出方向差异」**：真帧 teacher 只做 `lift_A_to_B`（**7128 行**），`lift_B_to_A` **0 行**、
`teacher_available=false` ⇒ one-hot 在数据上是常量 ⇒ `learnable_from_real_frames=false`（`directions_with_real_frames=1/2`）。
输出空间比 0.0028 **低于** G2 的 0.05 是**数据必然，不是缺陷**。
**不得声称** 48 臂权威表跨断点复用（那是 (乙)，需真重跑，小时级）。
**新前置（报 D 排期）**：要有 `lift_B_to_A` 的**演示源**，才谈得上「goal-conditioned 已学成」。

### 4. 溯源（裁定 37.1）+ import 面运行时证据（裁定 34.1 / 37.3）

V5 两路 6 个 term 全真：`sidecar_present` / `gate_allowed` / `new_lock_sha_matches_files` / `old_lock_sha_matches_files` /
`imageio_matches_new_lock` / `run_kind_is_train`。新 lock `186579b96bce…`（act）/ `73dcde892146…`（eval）；
0928 旧 lock **并存未被覆盖** `68a38731c5b5…` / `b6db07e2e31c…`；imageio 生效版本 **2.38.0**；
断点 `BP-20260929-lerobot-env-rebuild`（`occurred_at=2026-09-29T10:45:56+08:00`）。
**A 不跑 C 的 `--measure-import-surface`**：其产物路径是 C 的 `runs/infra/c_ruling_34_1_import_surface_20260929.json`，
跑一次就覆写 C 唯一的 before 证据 ⇒ A 改为**只读引用 + 自己出同方法探针**
（`probe_import_surface.{py,json}`，每模块一子进程、回显 `sys.modules` 里 imageio/uv 前缀键、`no_cache_eviction=true`）：
`scripts.train_act_lift` 与 `scripts.run_act_lift_runtime_failure_audit` 两条 **`hit=[]`**，与 C 15:21:29 实测一致
⇒ 本次真跑走的是**本仓链路**，在裁定 34.1 豁免内（引用须**点名包与版本**：`ImageIO 2.37.4→2.38.0` 两份、`uv 0.12.19→0.12.17` 仅 act）。
上游 `lerobot_train` **不在**豁免内（裁定 37.3 边界；C 实测其 imageio 引用 17 处）。

### 5. A 自查**第 7 起**同型：**跨口径搬阈值**（判据错、产物对）

V2 首版把**单元自检 G2** 的输出空间阈值 `0.05` **无条件**搬到「**训练后 + 单方向真帧**」这个 regime ⇒
在完全正确的产物上判 `CLOSED(V2)`（假红，首跑日志留档 `tmp/agentA_inherit_20260929/verify_v1_closed_by_bad_criterion.log`，
改动前脚本留档 `…/a_verify_t17_train_side.before_v2regime.py`）。
根因：G2 的 0.05 是在「**初始化 + 人为构造两个不同 goal**」的口径下立的，那时 one-hot 非常量；
真帧只有一个方向时 one-hot 是常量，**要求输出比过阈值 = 要求产物撒谎**。
**修法**：阈值**分空间** —— 权重空间**无条件**判（goal 通路没被压成 0，`goal_col_weight_ratio ≥ 0.05`）；
输出空间**只在** `learnable_from_real_frames=true` 时判。并补变异 **M1b**（产物谎称真帧覆盖两个方向 ⇒ 输出阈值**必须**生效）
钉住这条条件分支本身，否则「分空间」会退化成**恒绿**（把输出判据永久关掉）。
**一般规则（写进 A 的判据卫生）**：搬任何阈值前先问「**它是在什么数据 / 什么训练状态下立的**」；
换 regime 必须重新论证或分空间，并**为新分支补一个专属变异体**。

### 6. A 自查**第 8 起**同型：**进程级证据没留档**（判据错、产物对）

`--skip-audit` 复跑时，rc / `LearnerRefused` / 「有没有写出产物」这三项**只存在于上一轮进程里**，
闸读不到就当成缺失 ⇒ V7 假红。根因：把「**进程行为**」当「**文件事实**」判，却没给进程行为落盘。
**修法**：三次 audit 各落 `*.meta.json`（`rc` / `out_exists` / `refused` / `elapsed_s` / `cmd`），
缺就**如实记 `None` 不猜**（`reused_existing: null`）。实测三次：alternate `rc=0` / 26.2 s、
legacy `rc=0` / 22.2 s、refuse **`rc=1` + `refused=true` + `out_exists=false`** / 3.9 s（零产物 = 正确拒绝）。
留档后 16:35 用 `--skip-audit` 复跑，T1 仍 `OPEN` ⇒ 判据不再依赖进程在世。
**一般规则**：凡判据依赖 rc / 异常类型 / 「没写出文件」这类**负证据**，必须同批落 meta，否则该判据在复跑时必然假红。

### 7. 终验（16:35–16:38，**全部复跑**，不是引用旧日志；留档 `runs/infra/a_t17_train_verify_20260929/final/`）

| 项 | 命令 | 结果 |
|---|---|---|
| 验证闸变异自检 | `a_verify_t17_train_side.py --skip-audit --selftest` | **9/9** |
| 就绪闸 | `a_env_readiness_gate.py` | **`ALLOWED` 7/7**、`blocking_fail=0`、`warn=0` |
| 分布层闸自检 | `a_distribution_layer_check.py --selftest` | **15/15** |
| 溯源闸 | `b_env_provenance_guard.py` | **PASS 5 / WARN 0 / RED 0** |
| T17 单元自检 | `a_selfcheck_goal_conditioning_t17.py` | **7 PASS / 0 FAIL / 2 SKIP** + teeth **5/5** |

**2 项 SKIP 仍是 SKIP（`SKIP ≠ PASS`）**：G5（缺省路径键集/形状与**改动前**相同）、G6（0924 ckpt `strict=True` 加载且输出逐元素相同）。
V1/V4 在真跑规模上证了「**不新增键** + 两路键集相同 + 缺省路径无 goal 键」，但那是**改动后两路互比**，
**不等于**与「改动前 / 0924 ckpt」比 ⇒ A **不声称** G5/G6 已闭合，这两条仍挂在 A 的待办上。

**冻结面逐个 sha256 + mtime 复核（无一处被破）**：
`68a38731c5b5` / 09-28 **14:56:45**（0928 act lock）｜`b6db07e2e31c` / 09-28 **15:24:06**（0928 eval lock）｜
`3f23215a7ed3` / **11:08:55**（`attribution/arms_summary_v3.json`）｜`cac7588a4e86` / **12:33:23**（`arms_summary.json`）｜
`daf914bee131` / **12:01:15**（12:01 断言原件 `migration_regression_v121_to_v15.json`）｜
`23fe2d3bb08a` / **15:13:42**（A 的 15:13 manifest，未被 15:49 那份覆盖）。
C 的备份 `runs/infra/c_lerobot_env_locks_backup_20260928/` 两份与 0928 原件**逐字节相同**（同 sha、同 mtime 值）。
**一处需登记的现值变化（不是 A 动的）**：C 的 `runs/infra/c_env_manifest_20260929.json` 现为
`8c6a4ec366fc` / **15:47:04**（`generated_at=2026-09-29T15:47:03+08:00`），C 自己已把上一版留档为
`c_env_rebuild_20260929/c_env_manifest_20260929.pre_20260929_154704.json`（`c68906b31bb0` / 15:41:58）。
A 的就绪闸 E6 note 里的 manifest 时间戳是**运行时插值**（`a_env_readiness_gate.py:289`），不是硬写 ⇒ 现值自动跟随。

### 8. 卫生（照本仓纪律逐条自查）

只写 A 自己的目录与文档；**未碰** `harness/` `configs/` 与 B/C/D 的产物；**未执行任何 git 写**（HEAD 由 B 单写者推进：
`e076031` 16:25 快照已含 `scripts/a_verify_t17_train_side.py`、`4f5d378` 16:28）；**全程无 `rm`**（改动前版本一律 `cp` 到
`tmp/agentA_inherit_20260929/`）；长跑一律 `setsid nohup … < /dev/null &`（本轮教训：`nohup &` 在 6.5 min 时被会话回收杀掉，
日志只剩 warning、零产物）；两轮留档纪律 —— 首跑那份 `t17_train_side_verify.json`（被缺陷判据判 `CLOSED`）
**保留不删**，`_v2` 为现行。已写 `docs/a_handoff_to_b_t17_train_side_verified_20260929.md` 告知 B §8 两条闭合 + 边界 +
请 B 更新其自检期望（B 侧原记「2 项阻塞在 A 侧」现应改为「A 侧已闭合，剩 G5/G6 两条 SKIP」）。
