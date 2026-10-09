# C 线 P0-3 第一层：裁定的「身份与有效性」绑定（`registry/verdict_identity.py`）

时间：2026-09-28 21:10–21:35（C 线，CPU-only，不占 A 的卡）
产物：`runs/infra/c_verdict_identity_inventory.json`（全量清单，快照 21:33:13）、
`runs/infra/c_verdict_selfcheck.json`（84/84 PASS）、
`runs/infra/c_gate_build_observed.jsonl`（门禁构建观测流水，append-only）

一句话结论：**照现状 ingest 会把已作废的数字当物理事实写进 append-only 账本**。最后一次扫描的
123 份裁定文件 / 127 条逐臂裁定里，出自当前门禁构建且测量有效的是 **0 条**；94 条出自旧构建、
24 条连判据身份都没有、8 条被上游判为测量无效、1 条根本不是逐臂裁定。

「0 条」不是解析失败，而是**B 正在改判据**：21:15–21:33 的 18 分钟里当前 `gate_build` 变了
4 次，每变一次，此前所有裁定就集体降级为「待重判」。同一份代码在 21:23 那次扫描里还读到过
1 条 `physical_fact`（见 §10），10 分钟后它就变成旧口径了 —— 这正是要先绑身份再谈数字的原因。

---

## 1. 为什么需要这一层

D 清单 P0-3 点名的现状，本轮逐条复核成立：

- `registry/release_bundle.py:102` 的 `DirectionScore` 只有 `success_rate` /
  `success_rate_grasp_verified` / `flick_frac` / `controlled_success_rate`，
  **没有**任何判据身份字段；
- `harness/ledger.py`、`harness/data_bridge.py`、`registry/release_bundle.py` 里
  grep 不到 `measurement_valid` / `gate_build` / `gate_spec_sha256` / `superseded`；
- 上游裁定里这些字段**全都有**（`gate_version` / `gate_build` / `gate_spec_sha256` /
  `measurement_valid` / `accounts` 三套账 / 五档 bucket / `input_contract` /
  `terminal_semantics`）。

也就是说：信息在上游已经齐了，缺的只是 C 侧「读进来时把身份一起带上」的那一层。
账本是 append-only 的 —— 作废数字一旦写进去就出不来，只能靠撤销记录打补丁。所以这一层
必须在 ingest **之前**，而不是之后。

## 2. 实扫快照（21:23，A/B 仍在并发写入）

当前门禁构建（快照时刻）：`gate_version=v1.3`、`gate_build=4f20b3ec9130`、
`gate_spec_sha256=494d5f5babf9`（`gate_build` 是上游门禁脚本自身内容的 sha12，B 一改判据它就变）。

| 目录（`provenance`） | physical_fact | stale_build | unidentified | invalid_measurement | not_a_verdict |
| --- | --- | --- | --- | --- | --- |
| `<top-level>`（原始留档裁定） | 0 | 31 | 18 | 1 | 1 |
| `regate_current/`（A 重判到当时构建） | 0 | 41 | — | 7 | — |
| `blindfix/regate_current/` | 0 | 5 | — | — | — |
| `clipprobe/` + `clipprobe/regate_current/` | 0 | 4 + 4 | — | — | — |
| `reblown/regate_current/` | 0 | 1 | — | — | — |
| `ckptseq/`（A 21:16 起新建，检查点序列） | 0 | 8 | — | — | — |
| `superseded_gate_v1.0/`（归档） | 0 | — | 6 | — | — |
| 合计 | **0** | 94 | 24 | 8 | 1 |

同目录里并存 **13 个不同的 `gate_build`**，43 个臂存在跨构建的裁定冲突。
（21:23 那次扫描是 121 文件 / 125 裁定 / 11 个构建 / 1 条 `physical_fact`；
数字随上游写入与判据升级而变，所以每份清单都带 `generated_at` 与 `gate_current`。）

关键读法：**D 清单点名的 ingest 目标（顶层 `gate_strict_*.json`）里，可当物理事实的是 0 条**。
顶层 51 条全部是旧构建 / 无身份 / 无效测量。若按原计划直接把它们喂给
`ingest_runtime_result` → `DirectionScore`，账本里会多出一批 v1.1～v1.2.1 口径的数字，
而 `DirectionScore` 没有任何字段能说明它们是旧口径 —— 这正是 P0-3 要拦的事故。

## 3. 本轮**实测到**门禁构建在 C 脚下移动

`runs/infra/c_gate_build_observed.jsonl` 记下了四次扫描看到的当前构建：

| 时刻 | gate_version | gate_build | 裁定数 | physical_fact |
| --- | --- | --- | --- | --- |
| ~21:15 | v1.2.1 | `e4f5ec887788` | 119 | 55 |
| 21:20:29 | v1.3 | `5d20e5a2dffe` | 123 | 1 |
| 21:21:21 | v1.3 | `5d20e5a2dffe` | 123 | 1 |
| 21:22:44 | v1.3 | `7d5b62d243a2` | 125 | 1 |
| 21:23:20 | v1.3 | `7d5b62d243a2` | 125 | 1 |
| 21:28:36 | v1.3 | `a95ce5fc60ba` | 127 | 0 |
| 21:33:00 | v1.3 | `4f20b3ec9130` | 127 | 0 |
| 21:33:13 | v1.3 | `4f20b3ec9130` | 127 | 0 |

**18 分钟内当前构建变了 4 次**（v1.2.1 一次 + v1.3 三次），`physical_fact` 从 55 条一路掉到 0 条 ——
不是数据变差了，是「当前判据」这个参照系在移动。两个直接后果，都已落进设计：

1. C 侧**绝不硬编码**版本号。当前构建一律 `import` 上游模块读 `GATE_BUILD`，
   自检里还有一条断言专门查「C 的文件里不自定义 `GATE_VERSION/GATE_BUILD/GATE_SPEC_SHA`」。
   顺带说明：docstring 里写「一天内连升 v1.1 → v1.2.1」是叙述事实，不算硬编码 ——
   第一版自检把「源码里出现字面量 v1.2.1」当违规，逼人会删掉有用的记录，已改成查赋值语句。
2. **清单必须记「此刻当前构建是什么」**，否则事后无法解释某份清单为什么是那个分布。
   这就是观测流水的用途；每条记录也各自带一份 `gate_current`。

## 4. 五档分级与优先级

`classify()` 是纯函数，优先级从高到低：

| 档 | 触发条件 | 允许用途 |
| --- | --- | --- |
| `not_a_verdict` | 带 `arms`/`thresholds`、无 `accounts`（聚合/敏感度报告） | 只当报告读，**不得**当成一次测量 |
| `unidentified_build` | `gate_build` 缺失，或 `measurement_valid` 字段**根本不存在** | 留档；不得当事实，也**不得**说它 INVALID |
| `invalid_measurement` | 上游明确 `measurement_valid=False`，或怀疑把截断标成失败 | 留档 + 归因；不得当事实 |
| `stale_build_evidence` | 构建 ≠ 当前构建 | 旧口径证据、跨版本比对；重判后才可用 |
| `physical_fact` | 当前构建 + `measurement_valid is True` + 不怀疑截断 | 可进账本 / 发布包 |

顺序不是随意的：

- 聚合报告排在最前，因为它**根本不是「一次测量」**。本轮真抓到一例：
  `gate_threshold_sensitivity_A.json` 是敏感度报告（有 `arms`/`thresholds`、无 `accounts`），
  第一版解析器把它当成一个臂、又因为它没有 `measurement_valid` 字段而判成
  `invalid_measurement` —— 那是**凭空造出一个不存在的臂，还替上游宣布它测量无效**。
- 「字段缺失」与「字段为假值」是两种不同事实：`measurement_valid` 键不存在（旧判据没这个字段）
  ⇒ `unidentified_build`，不能读成 `False`。把 `None` 当 `False` 就是替上游下它没下过的结论。
- 身份先于有效性：连出自哪一版判据都不知道，讨论「这次测量有没有效」没有意义。

## 5. 取代关系（`superseded_by`）怎么推

规则：**同一被判决的评测文件**（`eval_file`）如果同时存在旧构建与当前构建的裁定，
当前构建那份取代旧的那份；没有当前构建版本的，旧裁定只标 `stale_build_evidence`，
`superseded_by` 保持 `None` —— 含义是「还没有用新判据重判过它」，**不是**「它仍然有效」。

本轮真目录的 `superseded = 0`，这是**合法结果**而不是漏检：当前构建 `7d5b62d243a2` 下只有
1 条裁定（`ckptseq/` 里 21:22 刚生成的那份），A 的 `regate_current/` 停在上一构建。
第一版自检在这里写了「取代关系必须 > 0」，B 一升级判据它就炸 —— 已改成用合成夹具验关系
（同臂旧构建 + 当前构建 + 另一个只有旧构建的臂，三种情形各自断言），真目录只做结构自洽核对。
同类定时炸弹还有一颗：`physical_fact` 的断言在「当前构建下 0 条可用」时是空过，
所以「physical_fact 可达」这件事由合成夹具证明，真目录只证明「不越级」。

## 6. 三条纪律（都在自检里被反向钉住）

1. **只读上游**。自检对本次读过的每一份裁定取 `(size, mtime_ns)` 指纹，扫描前后逐一比对。
   指纹只覆盖「本次读了的文件」而不是整棵目录树：上游此刻正被 A/B 并发写入
   （A 在 21:16–21:23 连续生成 `ckptseq/`，B 在改门禁脚本），拿整树比会把别人的正常写入
   算成 C 的锅。上游在扫描期间被改写时这条记 SKIP 而不是 FAIL（见 §7.1），另有一条与时间无关的
   结构证据兜底：身份层源码里不许出现任何写 API。
2. **不重算判据**。`controlled_success` / `flick` / `over_lift` / `insufficient_lift` /
   `measurement_valid` / `gate_pass` 一律取上游落盘值。自检把 125 条记录逐条与源文件比对
   （含多臂文件按出现顺序对齐），一条不符就红。第一版这里就有 bug：一律拿 `rows[0]` 比，
   把 5 臂的 `gate_controlled_success_minmax_arms.json` 判成「数字不符」——**是检查写错了，
   不是数据错了**，已按文件分组对齐修掉，并补一条「多臂文件确实被逐臂拆开核对」防空过。
3. **内容寻址**。每条记录带裁定文件自身 sha256 与被判决评测文件 sha256。
   *更正*：本文第一版写「仓库不是 git repo」，当晚 21:0x B 已按 DR-002 执行 `git init`
   （基线 commit `0137b33`，tracked 228）。但 DR-002 护栏 1 要求 `.gitignore` 排除 `runs/`，
   所以**裁定产物本身仍不进版控** —— 逐文件 sha256 依旧是产物身份的唯一指纹，
   代码文件则是「git + sha256」双重身份（与 D 的 §9-C⑤ run manifest 互为交叉校验）。
   自检用副本证明：改一个无关字节 ⇒ sha 变、分级不变；
   把 `gate_build` 改成当前值 ⇒ 分级从 `stale` 翻成 `physical_fact`（说明分级读的是内容，
   不是文件名）。

## 7. 自检与变异（84 项全绿）

`scripts/c_selfcheck_verdict_identity.py`，10 个 case、84 条断言。五个变异体：

| 变异 | 坏实现 | 被哪条抓住 |
| --- | --- | --- |
| M1 | `classify` 一律返回 `physical_fact` | 8 份合成裁定全塌成一档；INVALID / 缺身份 / 旧构建 / 聚合报告全部越级 |
| M2 | 只看 `measurement_valid`、忽略 `gate_build` | 旧构建裁定被抬成 `physical_fact` ⇒ 构建核对非冗余 |
| M3 | `is_arm_verdict` 恒 True（不辨聚合报告） | 自带 `measurement_valid=True` 的聚合报告被抬成 `physical_fact` ⇒ 凭空造臂 |
| M4 | `_lookup_arm` 恒返回 `None`（join 失效） | 全部记录 `validity_class` 变 `absent` ⇒ 「接上权威表」断言转红 |
| M5 | `_lookup_arm` 恒返回 `{"validity_class": "valid"}` | 与 A 权威表逐条比对不符 ⇒ 「不自己推导 validity」断言转红 |

每个变异都先断言「变异确实改变了被测量」再断言后果，`finally` 还原并复核还原成功 ——
这是 P0-1 那轮 M8/M11 假绿（`apply` 返回 lambda 而不是 undo，patch 从未生效）之后立的规矩。
为此专门多造了一份**带** `measurement_valid=True` 的聚合报告：真实的敏感度报告没有该字段，
只拿它做变异会被分到 `unidentified_build`，看不出 M3 的真正危害。

分级还做了一遍**独立复算**：自检里重写一次规则，对全部记录逐条比对 `classify` 的输出
（同 `manual_bc_loss` 的双路径做法）。这比「都在枚举内」强得多 —— 后者对任何常量实现都成立。

### 7.1 上游并发写入造成的**假红**，以及第三态 SKIP

第一次全量回归里这个自检红了 2 条，都在「当前构建身份」那一节：`gate_build == 脚本内容 sha12`、
`读到的属性与上游模块逐项相同`。查下来不是实现错，是**B 正在改那个脚本** —— 这两条核对要读
同一份文件三四次，中间被重写就必然不自洽。

处理办法不是放宽容差，而是把两种情况分开：

- 取快照时要求「连续多次读到的内容指纹相同」才算稳定（最多重试 6 次，每次隔 1 s）；
- 稳定 ⇒ 正常断言；始终不稳定 ⇒ 这几条记 **SKIP**（`ok=None`，既不算通过也不算失败），
  并把看到的多个指纹写进产物。自检因此有了第三态，汇总行变成 `n_pass/n_checks（m SKIP）`。

同理，「只读上游」那条实测证据也改成三态，并**额外**加了一条与时间无关的结构证据：
身份层源码里不得出现任何写 API（`write_text` / `mkdir` / `shutil` / `unlink` / `rename` …），
只允许 `read_text` 与 `open(path, "rb")`。上游在扫描期间被改写时，实测那条记 SKIP 并要求重跑，
结构那条仍然给出「C 没写上游」的硬证据 —— 不会因为别人在干活就随机转红。

**这条经验适用于全线**：凡是断言里含「读同一个正在被别人写的文件两次并要求相等」，
都必须显式处理竞态，否则自检会在别人正常工作时假红，久了就没人信它的红。

全量回归入口（含本自检）：`scripts/c_run_all_selfchecks.sh`。

## 7.2 三键与 A 的唯一权威表（监管备忘 增补五 §9-C②／增补六）

D 要求裁定身份必须含三键：`field_class`（裁定 14 的前提量）、`validity_class`、
`blowup_threshold_source`。三键的**取值来源**分工如下，C 一律不自己推导：

| 键 | 来源 | C 做什么 |
| --- | --- | --- |
| `field_class` | 被解析的那一份裁定文件 | 原样带上；另存 A 权威表的 `arm_field_class` 分列 |
| `validity_class` | A 的 `arms_summary.json`（`summarize_lerobot_act_arms.py` 是**唯一**生产者，免罪资格由它的 `probe_exoneration()` 在代码里断言 5 项准入） | 只 join、只核对；匹配不上就记 `absent_from_arms_summary` |
| `blowup_threshold_source` | 同上（裁定 11 的阈值溯源） | 只 join |
| `labels_reportable` | 同上（裁定 14） | 只 join，并据此判断失效模式标签可不可报 |

实扫结果：127 条里 **110 条**接到权威表（48 臂），17 条 `absent`（`ckptseq/` 新臂与聚合报告，
权威表还没覆盖）。`validity_class` 分布 `valid=106 / VALID_probe_exonerated=2 / invalid=2 / None=17`
—— 免罪**没有**被简写成 `valid`，这是裁定 10 明令禁止的。

**两种 `superseded_by` 必须分列**（第一版差点混掉）：

- C 的 `superseded_by`：**判据构建**层面的取代（同一评测文件，旧 `gate_build` 的裁定 → 当前构建的裁定）；
- A 的 `upstream_superseded_by`：**评测产物**层面的取代（留档原件 → `blindfix/` 重测件）。

同理 `field_class` 也有两份：本地这一份裁定的，与 A 权威行的（`arm_field_class`）。
5 条记录两者不同（留档 `partial` 原件 join 到 `strict` 的重测行）—— 这不是矛盾，
正是 A 的 `superseded_by` 设计要表达的情形。自检据此加了一条硬约束：
**两份 `field_class` 不一致的记录一律不得是 `physical_fact`**（非权威裁定不得冒充权威数字）。

第一版在这里判过一次假红：拿**本地** `field_class != strict` 去卡 **A 的** `labels_reportable`，
把「原件 partial + 重测 strict」当成违规。裁定 14 的前提量必须取权威行的那一份。

## 7.3 n 必须等于该臂的 `n_action_steps`（增补五 §9-C④，D 点名的主线阻塞项）

D 的裁定原文：真实帧路径的 `n` 必须等于 `n_action_steps`（K=2 臂为 **2**），
不得沿用规格算例的 `n=6` 去解读真实臂 —— 否则 C 的账本语义与 A 的臂**不在同一个时间尺度上对话**。

落地为一个纯函数守卫 `assert_n_matches_arm(n, arm_timing)`，不一致就抛、**不静默换算**；
`read_arm_timing(eval_json)` 从臂的评测产物里实测读 `chunk_size / n_action_steps / replan_every /
temporal_ensemble_coeff`（不在全量扫描里做：评测 JSON 每份 2–3 MB，127 份全读要几十秒，
而 `n` 只在「用账本语义解读某条真实臂」时才需要）。

自检用真臂跑了正反两侧（实测 K=2 族 `n_action_steps=2`、K=4 族 `=4`）：

| 组合 | 结果 |
| --- | --- |
| K=2 臂 + n=2 / K=4 臂 + n=4 | 放行 |
| K=2 臂 + n=4 | 拒绝 |
| K=2 臂 + n=6（规格算例） | 拒绝 |
| K=4 臂 + n=6（规格算例） | 拒绝 |
| K=4 臂 + n=2 | 拒绝 |
| 臂缺 `n_action_steps` | 拒绝（`VerdictIdentityError`，不许拿假设的 n 解读真实臂） |

C 的真帧 smoke 用 `n=4`，与 K=4 族同尺度；`γ=0.99` 仍是假设值（§8.1 的立项未变）。
要解读 K=2 族，必须以 `--n 2` 重建视图，不能拿现有产物换算。

## 8. 本轮**没有**做（P0-3 第二层的接口提案）

- **没有**接 `ingest_runtime_result`（`harness/ledger.py:360`）。它现在吃的是
  `harness/runtime_adapter.py` 的运行时结果，不是门禁裁定；接裁定需要先定「裁定是不是事实」。
  提案：账本只接受 `usable_for == physical_fact` 的裁定，其余各档写成**带身份的事件**
  （留档、可查、不进事实表），并记 `gate_version/gate_build/gate_spec_sha256/source_sha256`。
- **没有**改 `DirectionScore`。提案是加**可选**字段（保持向后兼容）：
  `gate_version` / `gate_build` / `gate_spec_sha256` / `verdict_sha256` / `measurement_valid` /
  `usable_for` / `superseded_by` / `accounts`（三套账）/ `buckets`（五档）。
  缺任一身份字段的 `DirectionScore` 不许进 `build_bundle`（与现有「双向同 checkpoint」红线同级）。
- **没有**做重判的 append-only 撤销记录。可复用 C 已有的 `record_contamination` +
  `case_append_only_and_revocation` 范式：重判 = 追加新裁定 + 给旧裁定写撤销事件，
  **不覆盖、不移动、不删除**旧产物（与 A 的 `a_regate_gate_current.py` 纪律一致）。
- **没有**动 A/B 的任何文件，也没有重判任何裁定。

## 9. 与 A/B 的边界

- **B** 拥有判据与 `GATE_BUILD`/`GATE_VERSION`/`GATE_SPEC_SHA`；C 只 import、只读、不复制。
- **A** 拥有重判（`a_regate_gate_current.py`：把留档裁定重判到当前构建，产物落
  `regate_current/`，不覆盖旧产物）；C 不重判，只给已有裁定绑定身份并分级。
- **C** 拥有账本 / 训练视图 / 发布包这一侧：谁有资格被当成事实写进去。
  这一层是三者之间的闸，不产生任何新的能力主张。

## 10. 顺带观测：一条数字的「有效期」只有 10 分钟（快照，非 C 的结论）

21:23 那次扫描里，当前构建（`7d5b62d243a2`）下唯一的 `physical_fact` 是
`ckptseq/actlog_trimdone0_minmax_k2_lr1e-5_s20k_seed4__step020000`：
`policy_independent` 分母 20、`controlled_success=19`、五档里 `flick=0`、
`insufficient_lift=0`、`over_lift=0`，`input_contract=verified_ok`，`gate_pass=true`
（`autonomous_learning` 一套账仍为空，上游注明需另跑关闭动作辅助的评测）。

到 21:33 的快照里，这条已经变成 `stale_build_evidence` —— **数字一个都没变**，
变的是判据构建。这就是「引用任何门禁数字都必须同时写 `gate_build`」的实证：
不写构建的 `19/20` 在十分钟后就无从判断还是不是当前口径。

归因与解释属 A/B 的主线（抓到但未抬升 lift），C 不下结论；`ckptseq/` 在扫描期间仍在被 A 写入，
任何跨臂比较都必须重新扫一次再取数，并同时报告 `gate_current`。
