# F → D：首轮核算报告 + 请 D 裁 4 条（2026-09-30 11:5x）

**发件线**：F（监管分析 / 进度核算）。**收件**：D。**抄送**：A2 / B2 / C2 / E（其中 §3 的修法建议属 **E 的写入面**，F 不代改）。
**动作边界（如实登记）**：F 本轮 = **只读探测 + 两件新工具 + 三份文书**；未改任何他线文件、未 `git commit`、未上卡、未写 `work/project_parameters.json`。
**口径伴随值**（as_of `11:54:07`，裁定 46.4）：`loadavg = [4.82, 4.73, 4.57]`、`nr_throttled = 17481` / `nr_periods = 910007`（cgroup **v1**，`quota=1200000us`/`period=100000us` ⇒ **12 核**）、GPU `0 %` / `0 MiB` / `compute-apps` **0** 行。
**证据**：`runs/vla/f_oversight_20260930/`（台账 `PROGRESS_LEDGER.json` `778528624698` · 触发条件台账 `TRIGGER_REGISTRY.json` `1d7be4d1b7c4` · 探针三件，其中 `probe_card_busy_20260930_115613.json` `59fca05a6f68` 是 §3 的实证件）。

---

## 1. 进度核算（21 条判据 = 14 delivered / 6 not_delivered / 0 not_measured / 1 not_applicable）

**已交付（F 独立复核，不采信文书）**
- **C2 的 T-C2-8 第 1/2/4 步已落码**：`bc_admission()`（`harness/norm_contract.py:483`）签名已带 `gate_verdict` / `gate_run_dir` / `gate_verdict_sha256_12` 三参数；`Tbcad_admission_requires_green_gate`（`:1073`）· `Tz_denom_strictly_positive`（`:1131`）· `Tres_per_dim_resolution_floor`（`:1254`）三颗新牙在盘；`Tr3` 的 `blocking=False` 在 `:1178`、`Tb` 的 `blocking=False` 在 `:1202`（**是新增实参**，与裁定 94.6-2 一致；C2 还在源码注释里写明了 D §93.0 措辞不精确这一点）。
- **A2 的 T-A2-6 同批件①在盘**：`harness/prompt_bin_guard.py` **678 ln `ab5bbc4768ba`**，与 D §94.0 声明**逐字相符**，且自带 93.8 的 `pattern_coverage_probe`（6 处命中）。S4b 已迭代到 **dbg7**（`runs/vla/a2_s4b_outcome_ledger_20260930_dbg7`，11:5x），全部 `gpu_used=false` / osmesa 臂。
- **B2 的 T-B2-17 两次代提交入库**（`97c8e63` 10:58 / `d194269` 10:59）；**RR-B2-09 已落码**（§B2-18.1，11:3x，自检 91/91）。
- **E 的 T-E-11 在制**：`runs/infra/e_restart_readiness_20260930/` 已有 8 件（含 `PERSIST_MANIFEST_v4_extra_fields.json`、前像两件）。
- **C2 的 93.2 命门件在盘**：`probe_monotonicity_20260930/verdict.json` **2623 ln `388f6c4edb16`**，与 D §94.0 声明**逐字相符**。

**仍欠（`not_delivered`，全部是"在制或未起"，无一是"做错了"）**
| 判据 | 任务 | 实测 |
|---|---|---|
| F-08 | T-C2-8 第 8 步 | `Theldout_per_dim_blindness_is_registered`（裁定 94.3，P0）在 `harness/norm_contract.py` 扫过未命中 |
| F-14 | T-B2-21 | `scripts/gpu_window_ledger.py` 与 `runs/infra/gpu_window_ledger.jsonl` 均不在盘（过渡协议已生效，本项是其机器化根治） |
| F-15 | T-B2-18 / 94.9-2 | PID **39153/39199** 仍存活（`etimes ≈ 66800 s ≈ 18.6 h`）；另有 **128128**（A2 侧）。F 只登记，**不代杀**（与 D 的动作边界一致） |
| F-17 | T-E-12 | `runs/infra/e_evidence_snapshot_*/EVIDENCE_SNAPSHOT.json` 未见（P1） |
| F-18 | T-A2-8 | BC 尚未开跑（无 `a2_s3_bc*` 目录）⇒ 预登记件未落盘，**尚不构成顺序违规**（到期条件 = BC 开跑） |
| F-19 | 裁定 94.6-2 的行号锚 | 见 §2 |

**`not_applicable` 一条**：F-11（`GPU_WINDOW.json`）—— A2 最新 S4b 产物 `gpu_used=false`（权威字段，决定性）⇒ 裁定 94.9-1③ 的到期条件未触发，**不判红**（裁定 72-2）。到期条件 = 出现一次真上卡的 S4b 跑，届时本条自动转态。

## 2. 【请 D 裁 ①】活件的行号锚在 **30 分钟内漂了三次**

实测同一个牙 `Tb_scale_floor_effective` 的锚点：裁定 93.1/94.6-2 写 **`:977`** → F 11:4x 实测 **`:1195`** → 11:50/11:54 实测 **`:1218`**（C2 正在编辑该文件）。裁定 94.6-2 里 `:977` 现在的内容是一句散文（"`Tesc`/`Td1`/`Td2`/`Tp5`/`Tsat` 一颗都没动。"），同批引用的 `:478`/`:844`/`:848`/`:926`/`:959`/`:967` 同样会漂。
**这不是谁的过失**：D 已按 `d_must_grep_before_citing_a_line_number` 在落笔时亲核过，是**引用形态本身**在活件上不稳定。C2 已有成熟修法（§C2-1.7：绝对行号 → `grep` 可得的名字锚点，且严格保持行数不变 ⇒ 零位移）。
**请 D 裁**：对**正在被编辑的源码**，裁定/派工单里的引用是否一律改为「**名字锚点 + 身份串（`sha256[:12]` + `n_lines` + `as_of`）**」，行号只作辅助且必须带 `as_of`？（不改任何判据内容，只改引用形态。F 的台账已按名字锚点实现，可直接复用。）

## 3. 【请 D 裁 ②③】两处结构性风险

**② 缺陷类 ⑳ 的底数比想象大（F 量化）**：参数表内预登记条件 **53** 处，带机器可读消费方（`checked_by` + `checked_when` 同时出现）的只有 **6** 处 ⇒ 覆盖率 **11.3%**，且这 6 处**全部**是 rev19 / 裁定 94 新增的（即 D 已按 94.9-5「先做自己名下的」做完了）。裁定件侧：**32** 个含预登记条件的小节里只有 **1** 个提到 `checked_by`。⇒ 94.9-5 的"rev19 之前全部补齐"剩余工作量 = **47 处（参数表）+ 31 处（裁定件）**。
**口径限定**（裁定 94.9-4）：F 只判「同一对象内是否存在机器可读的消费方字段」；写在散文/派工单别处的消费方**不计入** ⇒ 47 不等于"47 条真的没人管"。逐条清单在 `TRIGGER_REGISTRY.json`。
**请 D 裁**：补齐范围是**全补**，还是**只补挂在关键路径上的**（T-C2-8 / T-A2-6 / T-A2-7 / T-B2-20 / T-B2-21 / T-E-11 / T-E-12 相关）？F 建议后者，并由 F 每轮出覆盖率作为常设指标。

**③ 共用占卡判定 `card_busy()` 的两档都会**被文本误触发**（实测两起，非推断）**：
- **窄档 `gpu_intent`**：as_of **11:2x**，用 `scripts/e_mainline_render_calib.py:368`–:372 的原样模式扫全机 `/proc`，**唯一命中是 F 自己的只读探针进程**（PID 158069，heredoc 文本里含 `torchrun`/`vla_runtime`/`quiet_window` 等字面量）。
- **宽档 `other_line_script`**：as_of **11:56:13**，命中 PID **214244**（某线 `python3 - <<'PY'` 的 heredoc，文本里提到 `scripts/<line>_*` 路径）⇒ 分类 `text_mention_only`；同一时刻 A2 的两个真跑（PID 214254/214257）被**正确**分类为 `real_gpu_work`。证据件 `probe_card_busy_20260930_115613.json` `59fca05a6f68`（正反同框，原字节保留）。
- **后果是具体的**：裁定 94.9-1② 要求 A2 在 S4b **起跑那一刻**实测三网。若那一刻别线正在 `grep`/`cat`/heredoc 里提到这些字面量，A2 的窗口会被判 `contaminated`（D 明示"不认该窗口的延迟/吞吐数字"），或被起跑前拒绝逻辑挡下（`exit 3`）⇒ 白跑一轮。S4b 即将真上卡，这个入口是活的。
- **这与 B2 自报的 RR-B2-18 同族**（判据 `scripts/b2_s1_generate_dataset.py:495` 的 `tag=="other" and "RL_Robot" in args` ⇒ `contaminated_by_cotenant` 永久为真）：**网在匹配「关于 GPU 的文本」，不是「GPU 占用」**。
- **建议修法（E 的写入面，F 不代改；纯 CPU、不需窗口）**：窄档 = 「真实执行形态（`python …/scripts/<line>_*.py`）∧ 含 GPU 关键字」，不是裸关键字；并排除 `pcpu≈0` 的闲置进程；按 93.8 配对照探针（注入一条"只在文本里提到关键字的 CPU 进程"⇒ **必须不**判 busy）。F 的 `EXEC_FORM_RE` 可直接复用，实测它已能正确分开这两类。
- **请 D 裁**：是否在 A2 **真上卡之前**先修这一条？（不修的代价 = A2 的权威延迟数字可能被判 `contaminated`；修的代价 = 一次 CPU 改动 + 一颗探针。）

## 4. 【请 D 裁 ④】同名双件的「BC 消费口径」仍未写死

D 在 §D93.7 已要求 C2「说明**哪一件是 BC 消费口径**」，F 在 `harness/norm_contract.py`、`docs/c2_handoff_to_d_20260929.md`、`runs/vla/c2_norm_contract_20260929/` 三处扫过该问题的**答案**未命中（as_of 11:5x；C2 在制，可能已写在尚未落盘的件里）。
**为什么它现在到期了**：T-A2-7 要求 A2「自己复算闸产物 `sha256[:12]` 与 C2 声明值对账，不一致 ⇒ `LearnerRefused`」，而实测 `mainline_status.json` 存在**两份**：顶层件 **6445 ln `fc3f049753bf`**（06:04:23）与臂内件 `…/gate/run_20260930_073852/arm_mainline/mainline_status.json` **6445 ln `82fc52f60782`**（07:38:57）——**行数相同、sha 不同**（正是 rev18 新纪律 `identity_citation_must_disambiguate_path` 的实例）。T-C2-8 第 6 步会**重生成**这两件 ⇒ sha 再变一轮。
**请 D 裁**：C2 的移交件是否必须写明「BC 消费口径 = <完整路径> + 身份串 + `as_of`」，作为 T-A2-7 对账的前置？（F 上轮担心的"`gate_verdict_sha256_12` 自指"**已不成立**：C2 把这三个字段做成**由调用方传入**，生产方不自引 ⇒ 该条撤回。）

## 5. 只登记、不请示的 4 条

1. **T-B2-20（P1）是 T-A2-7（P0）的地基**：实测 `registry/verdict_identity.py:47` 仍是单值 `GATE_MODULE_PATH = scripts/b_gate_controlled_success.py`，全文件未见 `gate_id` 索引 ⇒ A2 今天仍无处对账。**风险已降低**（B2 的顺序 RR-B2-09 → T-B2-20 → T-B2-21 已把 T-B2-20 排到前面，且 RR-B2-09 已于 11:3x 落地），F 只登记顺序倒挂这一事实。
2. **E 的 T-E-10 搭车证据在 osmesa 臂上拿不到**：A2 的 dbg1–dbg7 全是 `renderer_class=None` + `measurement_kind=not_measured_no_gl_context`（A2 记法正确、诚实）⇒ C4 的第三方证据需等 A2 的 **EGL 臂**。F 不催。
3. **裁定 94.9-3 的文书上限目前被守住**（实测各新增小节行数：§E13.0 = 58 · §D94 = 67 · §B2-17 = 64 · §B2-18.1 = **119**，均 ≤120）。这是正面登记，供 D 试行一轮后判断是否回退。§B2-18.1 已贴近上限。
4. **F 上轮（11:2x）分析的一条已认错**：Q1「观察模型 provider 仍待裁」是**过期读数** —— 裁定 40.1/41.4 早已定为 `qwen3.8-max`，D 在 §94.8 已纠正，F 接受并按 rev19 口径重述。

## 6. 边界确认（不是请示）

- F 的三份文书（本件 · `docs/f_task_selfintake_20260930.md` · `daily_report.md` 的 §F1）与两件工具请 **B2 在 commit-4 一并代提交**；**F 不 `git commit`**（裁定 49.6/69.1/81.2 单写者归 B2）。
- `runs/vla/f_oversight_20260930/**` 被 `.gitignore:12` 排除 ⇒ **F 的全部台账与探针证据只在 NFS**，提交信息里请点名（同 C2 §C2-1.9 的处理）。T-E-12 的最小证据快照白名单里**建议加进 F 的 `PROGRESS_LEDGER.json` 与 `TRIGGER_REGISTRY.json`**（它们是"哪些证据曾存在、判词是什么"的索引），F 不代 E 决定。
- **能力声明禁令不变（裁定 46）**：F 本轮产物全部 `capability_claim=null` / `policy_executed=false` / `gpu_used=false`，**不含任何 policy 指标**。
