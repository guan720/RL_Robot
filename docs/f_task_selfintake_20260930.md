# F 线接单件（2026-09-30 11:5x · 监管分析 / 进度核算 · 配合 D）

**发件线**：F（新开线，用户 2026-09-30 11:3x 指派）。**收件**：D（监管 / 口径裁定），抄送 A2 / B2 / C2 / E。
**性质**：① 自我接单与边界申报（照 C2 的 `docs/c2_task_selfintake_20260929.md` 形态）；
② F 的两件工具与首轮台账；③ **F 自己的三起自报缺陷**（都在落盘前被自己的自检拦下）。
**三值纪律**：本件所有数字都由工具在落笔时刻取值，凡未实测的一律写 `not_measured`，不拿 `0`/`false` 填充。

---

## 1. F 是什么、不是什么

| 项 | 内容 |
|---|---|
| **职责** | ① 分析监管文书（裁定 / 派工单 / checkpoint）与实物的一致性；② **执行进度核算**：把"任务书说要做的"与"盘上实际有的"对成机器可读台账；③ 做**预登记条件的常设消费方**（缺陷类 ⑳）；④ 独立复核各线声明的身份串与判词落点。 |
| **F 存在的理由（不是加一层官僚）** | 缺陷类 **⑳ `preregistered_condition_without_a_consumer`** 的实证：T-C2-7 的「再发生一次抢卡事故 ⇒ 立即升 P0」在 **00:2x 触发后 11 小时无人执行**，而且是外部分析而不是 D 自己发现的（裁定 94.9-5）。预登记条件没有常设消费方 = 等于没写。F 就是那个消费方。 |
| **不做的** | 不裁口径（归 D）· 不写他线实现代码 · 不定标阈值 · 不改极性 · 不 `git commit`（单写者 B2）· 不写 `work/project_parameters.json`（D 单写者）· 不上卡 · 不用 `rm`（走 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`）· 不碰 `RL_Harness_v4_20260924/`（只读）与 `/workspace/mnt/sppro/yhzhang91/datasets`。 |
| **发现判据本身有问题时** | **只报 D、不自决**（照 C2 的 E4 处置，裁定 90.2 记功的形状）。 |
| **写入面（超出即违规）** | `scripts/f_*.py` · `docs/f_*.md` · `runs/vla/f_oversight_*/**` · `daily_report.md`（**只追加**，且受裁定 94.9-3 的 ≤120 行上限）。 |

## 2. F 采纳的既有纪律（逐条，不新设）

- **只读优先**：F 的全部探测都是读；唯一的写是自己 run 目录下的台账。
- **三值**（裁定 88.5-4 / `absence_of_measurement_three_state_rev15`）：`delivered` / `not_delivered` / `not_measured`；另按**裁定 72-2** 增 `not_applicable`（到期条件未触发 ⇒ 不适用不出红）。
- **限定前缀扫描**（裁定 94.9-2 `no_root_filesystem_scans`）：只扫 `runs/vla`、`runs/infra`、`scripts`、`harness`、`docs`、`registry`、`work` 与 `/proc`（只读），一律带 `maxdepth`；**禁止 `find /`**。
- **否定性断言必须写扫描作用域**（裁定 94.9-4）：本件与台账里所有"不存在"都写成「在 <路径集> 扫过 <模式集> 未命中 + 时刻」。
- **身份串由工具生成、人不碰**（裁定 92.3 红线级）：两算法都给（`sha256_12` 为唯一可引用口径、`sha1_12` 只为让算法错配一眼可见）+ `n_lines`(`wc -l`) + `n_lines_splitlines` + `ends_with_newline` + `why_it_matters` + `citable`。
- **对照探针**（裁定 93.8 / 缺陷类 ⑲）：F 的两件工具都自带 `pattern_coverage_probe`，缺 ⇒ `not_measured`、**不得报绿**。
- **覆写自己的产物 ⇒ 前像 + `sha256[:12]`**：台账重跑前自动落 `before_images/<name>.before_<stamp>`。
- **heredoc 引用型**（红线）：写含反引号/`$()` 的内容一律 `<<'EOF'`。
- **能力声明禁令**（裁定 46）：F 的产物一律 `capability_claim = null`、`policy_executed = false`；BC 出结果前不出现任何能力表述。
- **数字成对给口径**（裁定 46.4）：凡引 `loadavg` / `nr_throttled` 必带 cgroup 口径（v1，`quota=1200000us`/`period=100000us` ⇒ **12 核**，`nproc=112` 是假象）。

## 3. F 的两件工具（都在盘、都可复跑）

| 件 | 作用 | 复跑 |
|---|---|---|
| `scripts/f_progress_ledger.py` | 21 条判据的进度台账 + 预登记条件消费方台账。**判据全部来自 D 已写下的裁定/派工单**，F 不新设。 | `python3 scripts/f_progress_ledger.py`（`--selftest` 只跑 93.8 对照探针） |
| `scripts/f_probe_card_busy.py` | 只读探针：共用占卡判定 `card_busy()` 的两档是否会**被文本误触发**。判据用 `ast` 从 `scripts/e_mainline_render_calib.py` **运行时取出**，本件源码不含那些字面量。 | `python3 scripts/f_probe_card_busy.py` |

**退出码语义**（两件都遵守）：`0` = 测到且无异常；`3` = 对照探针失败；`4` = 存在 `not_measured`（作用域为空/解析失败）；`5` = 假阳性风险成立（仅 `f_probe_card_busy.py`）。`not_delivered` **不**影响退出码——台账的作用是让"还欠什么"可见，不是拦人。

## 4. F 的三起自报缺陷（都在落盘前被自己的自检拦下，无一进入任何台账）

| # | 缺陷 | 怎么被抓到 | 根因修 |
|---|---|---|---|
| 1 | 93.8 对照探针的"必然零命中"哨兵串**写死在工具自己源码里** ⇒ 被自己命中，`detected=false` | `--selftest` **exit 3** | 改为直接验三值映射的两向（零命中 ⇒ `not_delivered`、非零 ⇒ `delivered`）+ 哨兵**运行时拼接**；并在产物里留 `self_caught_defect` 字段说明 |
| 2 | `GPU_WINDOW.json` 那条判据**无条件**判 `not_delivered`，而 A2 当时的 dbg1–dbg6 全是 osmesa/CPU 臂（`gpu_used=false`）⇒ 会是一次"狼来了"（B2 的 RR-B2-18 同族） | F 自己复核 A2 产物字段时发现 | 判据改为**条件式**：`gpu_used` 为权威字段、存在即决定性；未上卡 ⇒ `not_applicable`（裁定 72-2），并登记到期条件 |
| 3 | 判"上卡与否"时曾用**全 JSON 文本**匹配 `nvidia_gpu` ⇒ 命中的是 A2 闸里的 **check 名**（`classify_nvidia_gpu`），不是实测值；同时 verdict **只看窄档**，漏掉宽档的一个真命中 | 同一轮里两次自相矛盾（`gpu_used=false` 却判"上卡证据=有"） | 只认「同时带 `renderer_class` 与 `measurement_kind` 的实测记录」；verdict 改为**两档并判**并落 `verdict_caliber` |

**三起同族**：都是**判据的作用域/形态比对象空间窄或偏**（缺陷类 ⑲）。第 2、3 起尤其值得记：它们的方向都是**让结论过绿或过红**，而抓住它们的都不是"更努力地看"，是**把断言的两向都装上**。

## 5. 首轮台账（as_of `2026-09-30T11:54:07+0800`，纯 CPU、未触卡）

- `runs/vla/f_oversight_20260930/PROGRESS_LEDGER.json`：**21 条判据 = 14 `delivered` / 6 `not_delivered` / 0 `not_measured` / 1 `not_applicable`**，`pattern_coverage_probe.all_detected = true`。
- `runs/vla/f_oversight_20260930/TRIGGER_REGISTRY.json`：参数表内预登记条件 **53** 处，带机器可读消费方（`checked_by` + `checked_when`）的 **6** 处 ⇒ 覆盖率 **11.3%**；裁定件侧 **32** 个含预条件的小节里只有 **1** 个提到 `checked_by`。
- `runs/vla/f_oversight_20260930/probe_card_busy_20260930_115613.json`（`59fca05a6f68`）：宽档 **1 个 `text_mention_only` 假阳性**（PID 214244）与 **2 个被正确分类的 A2 真跑**（PID 214254/214257）同框 ⇒ 分类器有效、而旧 verdict 过绿（缺陷 3 的实证件，**原字节保留不改**）。

**逐条发现与请 D 裁的 4 条在 `docs/f_handoff_to_d_20260930.md`。**

## 6. F 的下一步（不插队、不上卡）

1. 每轮重跑两件工具，把台账增量（**新增/转态**的判据，不是全量复述）追加进 `daily_report.md`（≤120 行）。
2. 把 47 处无消费方的预登记条件按**是否挂在关键路径上**排序，交 D 定优先级（F 不自定）。
3. 给 `card_busy()` 的修法建议交 E（F 不代改），并按 93.8 附对照探针的形状。
4. 等 A2 的 S4b **真上卡**那一轮，核 `GPU_WINDOW.json` 与起跑前拒绝逻辑是否齐（裁定 94.9-1③④）；同时核 E 的 T-E-10 搭车证据是否拿到 `renderer_class=nvidia_gpu`。
