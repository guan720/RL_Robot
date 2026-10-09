# B 线登记（2026-09-28）：版控纳管范围 / teacher 锚点重置预登记 / 工程扩展停车

登记方：智能体 B（验收门禁与可复现性线）。
依据：`work/decisions/decisions_20260928.md` DR-001（`work/decisions/` 可写，**最小写入**：
只放路线变更 / 口径裁定 / 作废与 ack 登记；实验结果、产物、日志不写入本目录）与 DR-002
（`git init` 许可 + 4 条实施护栏）。
本文件是 B 线自己的登记，不修改 D 已写的 DR-001/DR-002，也不修改 A 的 `decisions_20260928_A.md`。
DR 编号续接 D 的全局序列（DR-003 起）。所有被引用的产物路径都在 `runs/`（不纳版控），
本文件只写路径与判定，不抄结果表。

---

## DR-003 `.gitignore` 纳管范围与 `runs/` 决定（DR-002 护栏 4 的前置登记）

- 时间：2026-09-28 深夜；登记人 B；裁定人 用户（DR-002 护栏 4 要求本条先于首次提交）
- 性质：纯治理。**不改任何判据、不改任何数据、不构成 baseline 重置。**

### 决定（逐条，附实测依据）

| # | 决定 | 实测依据 |
|---|---|---|
| 1 | `runs/` **不纳管**（沿用旧 `.gitignore`） | 37 GB / 22596 文件；单文件最大 307 MB（`optimizer_state.safetensors`）、154 MB（`model.safetensors`）；23 MB 级 JSON 产物多份 |
| 2 | `work/` **纳管**（用户明示确认） | `work/decisions/` 是 DR-001 指定的唯一登记处，必须受版控才可追溯「谁在何时改口径」 |
| 3 | 补排除二进制/媒体/大产物：`*.mp4 *.avi *.gif *.pkl *.safetensors *.ckpt *.pth *.pt *.npz *.npy *.h5 *.hdf5 *.zip *.tar *.tar.gz *.log` | 实测仓库内（除 `runs/`、`RL_Harness_v4_20260924/`）此类文件只有 `registry/*/v*/model.zip` 共 120 个；扩展名分布：json 272 / py 136 / zip 120 / pyc 91 / md 57 / sh 9 / yaml 8 / txt 2 |
| 4 | `registry/*/` **排除**（发布包载荷=产物），但 `registry/*.py` 与 `registry/README.md` **纳管**（工具与说明） | `registry/` 共 32 MB / 387 文件，其中 120 个 `model.zip` 是权重载荷 |
| 5 | `RL_Harness_v4_20260924/` **排除** | 三条理由：(a) DR-002 护栏 3 要求它「不得因任何 git 操作被改写」，纳管即存在 `git checkout` 改写路径；(b) 它自带完整性机制 —— `MANIFEST.json` 逐文件 sha256 + `tools/verify_package.py`；(c) 上游 provenance 已单独锁定（RPent commit `eb269c8a278b`）。34 MB / 932 文件 |
| 6 | 排除 `__pycache__/` `*.py[cod]` `*.egg-info/` `.venv/` `venv/` | 实测 91 个 `.pyc` |
| 7 | **带牙护栏**：装 pre-commit 体积闸 `scripts/b_git_size_guard.py`，拒绝新增 > 2 MB 的 tracked 文件（白名单可显式放行） | 光靠扩展名规则挡不住「大 JSON」——git 无法按体积忽略；实测当前 tracked 候选中无 >1 MB 文件，闸门是给未来的 |
| 8 | **单写者纪律**：只有 B 执行 git 写操作（`init`/`add`/`commit`/`tag`）；A、C 不并发跑任何 git 写命令 | 避免 `index.lock` 竞争与提交归属混乱；A/C 需要版控信息时向 B 索取或只读 `git log`/`git status` |

### 禁用命令（DR-002 护栏 2，B 自我约束并写进 hook 前置检查）

`git clean -fd` / `git clean -fdx` / `git reset --hard` / `git checkout -- .` /
`git checkout <branch> -- .` / `git restore .` / `git stash drop` / `git gc --prune=now`
—— 全部会不可逆删除未跟踪或已修改文件，与 AGENTS.md「禁 `rm`、清除走回收站」同源。
误删一律 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`。

### 影响面

- **解锁**：监管 P0 第一项「实验记录的『代码版本』字段」首次可填（此前 B 只用 `gate_build`
  内容哈希做局部替代，覆盖不了 A/C 的实现文件，见 `docs/b_reproducibility_incident_20260928.md`）。
- **作废的历史结论清单**：无。此前所有 `gate_build=e4f5ec887788` 的裁定继续有效；
  自本条起，裁定 JSON 除 `gate_build`/`gate_spec_sha256` 外**可另附** `git_commit`，
  缺 `git_commit` 的旧裁定不因此作废（只有 `blown_metric_impl` 缺指纹才拒判，见 DR-006）。
- **不影响的**：A 的 48 臂评测产物、C 的 ledger/data_bridge 实现、任何 `runs/` 内容。

### 回归验收方式（本条自身的验收）

1. `git status --porcelain` 为空（全部应纳管文件已进首次提交）；
2. `git ls-files | wc -l` 与「实测非排除文件数」一致，且 `git ls-files runs/ RL_Harness_v4_20260924/ registry/*/` 为空；
3. 仓库体积 < 100 MB。**原文写的是 `git count-objects -vH` 的 `size-pack` < 100 MB，
   这条是恒真的，已更正**：仓库尚未 `git gc` 时对象全是 loose，`size-pack` 恒为 `0 bytes`
   （实测就是 0），检查它等于没检查 —— 与 `docs/b_reproducibility_incident_20260928.md` §2
   缺陷 3 那个恒真的「版本一致」断言同一类型。改为同时看 `size`（loose）与 `size-pack`，
   或直接看 `.git` 目录总大小；
4. 体积闸有牙：临时造一个 3 MB 文件 `git add` 必须被 pre-commit 拒绝（验证后 `mv` 进回收站，不用 `rm`）；
5. 容器重建后 `scripts/b_selfcheck_reproducibility.py` 仍 12/12（本条不得破坏既有可复现性门禁）。

---

## DR-004 teacher 去饱和的验收标准与锚点重算规则（**预登记，不动手**）

- 时间：2026-09-28 深夜；登记人 B；裁定人 待 D/用户放行（本条只钉门框，不授权改动）
- 触发来源：DR-001「解锁的事项」第 3 项 —— B 的 teacher 去饱和
  （`scripts/demo_scripted_lift_rs.py:99`）= baseline 重置，须先登记再动手。
- 正文：`docs/b_teacher_desaturation_prereg_20260928.md`（判据 T1–T5 / A0–A5 / B1–B4 与逐条数值依据）。
  本条只登记裁定与生效条件，不抄判据表（DR-001 最小写入）。

### 决定

| # | 决定 |
|---|---|
| 1 | 验收标准**在重采数据之前**冻结，共 15 条（teacher 侧 5 + 锚点侧 6 + 闭环侧 4），仪器 `scripts/b_teacher_dz_audit.py`，`not_measured` 一律不算通过 |
| 2 | 补 `RISE_CAP` 的可复现规则：`floor_to_0.01(2 × base-only mean_max_rise)`。门禁源码此前只有「取约 2 倍」，**不可复现**（`ceil_to_0.01` 会给 0.16 ≠ 任值 0.15）。判据 A0 要求规则套旧数据必须精确复现 `0.15`，防「悄悄换锚」 |
| 3 | `FINAL_RISE_MIN = 0.04` **不在重算范围**：它是几何锚（`0.92 ×` 方块全高 `0.04341`），不是 teacher 锚。只用 A3 验「新 teacher 下门禁仍可满足且裕度 ≥ 0.010」。**A3 FAIL 时禁止下调该常量**（属监管裁决范围，且下调会放大所有历史臂成功率），允许的响应是把 `LIFT_TARGET` 作为另一次单变量改动 + 另一条 DR |
| 4 | 新增 **B3 漂移有界性探针**：同一冻结 ckpt 跑 `--horizon 300` 与 `600`，要求 `median[max_rise(600) − max_rise(300)] ≤ 0.010 m` 且尾 100 步速率 `≤ 5e-5 m/step`。理由：去饱和把上升速率降约 5×，「不停」的策略也可能在 300 步内不越 `RISE_CAP`，被现有 C3 判成受控成功 —— 这是本次最可能的假阳性通道 |
| 5 | 去饱和是**幅度修复不是可辨识性修复**（T2 `recall_lift 1.000 / precision_lift 0.30`，`z0` 不在 obs）。B3 FAIL 而 B1/B2 PASS 时，唯一允许措辞是「上升速率降低，停止条件仍未恢复」，下一步转 `docs/b_normalization_incident_20260928.md` §6.3 obs 契约变更（另开 DR），**禁止第三轮 teacher 微调** |
| 6 | 单变量：只准改 `lift` 段的 `0.3`。T4/T5 用机器比对挡住夹带（`hold` 段 `dz` 仍恒 0；非 `lift` 相位逐维统计与帧数 `1e-6` 内不变） |
| 7 | **排序**：本条现在**不生效**。放行条件三者同时满足 —— (a) A 的 `ckptseq/divergence_verdict.json` 出 R1/R2 结论；(b) D/用户对本条「生效」段放行；(c) A 线 in-flight 评测收尾。依据 `docs/a_bimodal_divergence_preregistration_20260928.md` §9（双峰有答案前不做 L2 修复），B 同意该排序 |

### 影响的基线 / 作废与降级清单（详表见预登记 §6.2）

- **作废**：48 臂官方比较集的**跨 teacher 可比性**（各臂裁定 JSON 本身不作废，`measurement_valid` 不受影响）。
- **降级为「旧 teacher 口径」，引用须带 teacher 指纹**：`insuff_diagnostic` 汇总（235 局 / 34 臂、median `0.0236`）
  与 C5 杠杆表；族均值 `k1/k2/stdfloor`；`docs/lerobot_act_env_setup_20260928.md` 中所有「= base-only 0.0764 的 X%」。
- **结论保留但机制解释须重述**：slew cap / dz deadband 共 7 臂全 0/20 的负结果 ——
  原机制「命令本身已饱和 ±1」在 teacher 去饱和后不再适用于 teacher 侧（policy 的 tanh 输出仍饱和）。
- **不作废**：离线探针 `b_bc_underfit_probe` / `b_probe_dz_identifiability` 的结论；checkpoint 本身（但失去可比性）。

### 回归验收方式

预登记 §6.3 七条：`--mode check` 退出码 0；负控制仍 FAIL（已跑，见下）；
`b_selfcheck_gate_regression` 21 用例 / 85 断言；`b_selfcheck_gate_mutation` 5/5；
`b_selfcheck_reproducibility` 12/12；`b_regate_all` 新旧裁定并列留档不覆盖；
门禁规格升 **v1.5** 并在 §6 记为「锚点重置」而非「判据收紧」
（v1.4 已被裁定 14 / DR-D09 占用，见 DR-007）。

### 已落盘证据（`runs/` 不纳版控，故登记 sha256 前 16 位）

- `9288e63f6a5e1ca0` `runs/infra/b_teacher_desat/baseline_teacher_dz.json`（旧 teacher 基线，已锁）
- `ab874f09c2cc25b0` `runs/infra/b_teacher_desat/negative_control_old_teacher.json`
  （**负控制**：用未修改的旧 teacher 跑 check → `verdict=FAIL`、退出码 1，FAIL 的恰好是
  T1 `sat_frac=1.0`、T2 `mean_dz_lift=1.0`、A4 `mean_max_rise=0.07633` 三条本次应当改变的判据，
  其余 PASS → 判据非恒真非恒假）
- `40a2028e182e6f17` `runs/act_chunk_replay_20260924_k4_base_truth20.json`（锚点来源）
- `ace4d12869074129` `scripts/b_teacher_dz_audit.py`（仪器）

---

## DR-005 工程扩展停车：连续性正则 / slew limit（B-7）

- 时间：2026-09-28 深夜；登记人 B；性质：**撤销停车的原因登记 + 重启条件**
- 背景：DR-001 解锁了 B 的工程扩展（`λ_cont` 连续性正则 / 执行侧 slew limit），
  此前因无登记入口而停车。现登记为**继续停车**，理由已从「无入口」变成「证据反转」。

### 决定

1. **不引入** `λ_cont` 连续性正则与执行侧 slew limit 到 BC/ACT 阶段。
   口径依据：v4 的 `λ_cont L_continuity` 出现在 **RL 的 actor loss**
   （`RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/01_开发技术方案.md:253`），
   **不是** BC/ACT 阶段的既定项；B 若在 BC 阶段用它，属工程扩展，须按 v4「复合 policy ≠ 底模变强」
   整体冻结并计入时延与成本报告。
2. **实证依据（负结果已在手）**：slew cap ∈ {0.5, 0.25, 0.1} 与 dz deadband ∈ {0.15, 0.2, 0.3} 共 7 臂，
   受控成功**全部 0/20**（`runs/infra/b_flick_sweep/`、`runs/infra/b_dzdeadband/`）；
   机制是「命令本身已饱和 ±1，问题在网络**输入**不在输出」。
3. **v1.3 重判后的补充依据**：有效臂的 `flick` 几乎全为 0（权威值 `flick = 7`，其中 5 局在 2 个 INVALID 臂上
   → 可引用 **2 局 / 920 局**，见 DR-D09）。当前主失效模式是 `insufficient_lift`（**235 局**），
   连续性正则与 slew limit 打的是 `flick`/`over_lift`，**打的不是现在的靶**。
4. **重启条件**（任一成立且有产物支撑才可重启，重启须在本目录追加记录）：
   (a) teacher 去饱和后 `over_lift` 重新成为主失效模式；
   (b) 出现 `flick` 可引用局数 > 20 且集中在同一配置族；
   (c) 进入 RL 阶段并需要按 v4 原文实现 actor loss 的 `λ_cont`（那是实现既定项，不属本条扩展）。

### 影响面

- 不作废任何历史结论；第 2 条引用的 7 臂负结果按 DR-004 §6.2 保留结论、重述机制。
- 不改变任何判据、阈值、数据。

---

## DR-006 `blown_metric_impl` 指纹拒判与祖父登记（补 DR-003 与 DR-D10 的前向引用）

- 时间：2026-09-28 深夜；登记人 B；裁定人 D（监管 §12 分派）+ 用户
- 背景：DR-003 与 D 的 DR-D10 都前向引用了「DR-006『缺指纹才拒判』」，本条把该引用补齐，
  避免悬空编号。落地代码已在门禁 v1.3（`docs/b_controlled_success_v1_20260928.md` §2.12）。

### 决定

1. 每份裁定 JSON 必须回显 `blown_metric_impl` 与 `blowup_threshold` 及其 `threshold_provenance`；
   **新产物缺指纹 → 拒判（`INVALID`）**，不是「按通过处理」。
2. 已知违例实现登记为常量 `KNOWN_BLOWN_IMPLS = ("52eae25ee2d7",)`（`std + 1e-6` 无下限归一化）。
3. **祖父条款**：门禁加此检查**之前**产出的历史臂，凭 `configs/b_blown_impl_grandfathered.json`
   （69 条，cutoff `2026-09-28T21:27:24+08:00`）继续可判，但 `measurement_valid=False` 的照旧无效；
   登记簿由 `scripts/b_blown_impl_registry.py --verify` 自检（实测 69/69）。
4. 祖父条款**不覆盖新产物**：cutoff 之后生成的任何评测产物缺指纹一律拒判。
5. `probe_exonerated`（争议带保留解除）只接受带内证据 + sha256 可校验；带外一律 `out_of_band_refused`；
   `scope=arm` 的免罪要求 impl 已知，防连带洗白。

### 影响面

- 作废清单：无新增。缺 `git_commit` 的旧裁定**不**因此作废（只有缺 `blown_metric_impl` 指纹才拒判）。
- 实测零附带损伤：48 臂官方集 phase 词表矛盾 0 例、指纹齐备。

---

## DR-007 裁定 14（DR-D09）的落地口径：B 对字面裁定做了**收窄**，请 D 复核

- 时间：2026-09-28 深夜；登记人 B；裁定人 D（DR-D09 原裁定人）—— **本条是 B 主动申报的偏离**
- 触发来源：A 的移交 `docs/a_handoff_to_b_gate_vocabulary_20260928.md`（裁定 14 最小复现 + 12 份算例）
- 落地：门禁 **v1.4**（规格 `docs/b_controlled_success_v1_20260928.md` §2.16 / §2.16.1）

### 裁定原文与 B 的实现差别

| | DR-D09 字面 | B 的 v1.4 实现 |
|---|---|---|
| 弃权触发条件 | `field_class != "strict"` | `missing ∩ LABEL_CRITICAL_FIELDS ≠ ∅`，其中 `LABEL_CRITICAL_FIELDS = (final_rise, held_at_end, phase_at_end)` |
| 差别落在哪 | 只缺 `terminal_kind` 的产物也弃权 + `measurement_valid=False` | 只缺 `terminal_kind` 的产物**标签照常输出**、`measurement_valid=True` |

### 收窄理由（可测，不是措辞偏好）

1. 三个失效模式标签（`flick` / `insufficient_lift` / `over_lift`）**不读** `terminal_kind`；
   `terminal_kind` 走的是规格 §2.4 终局语义那条**独立**弃权路径。用它触发标签弃权，
   修的不是 DR-D09 指出的那个通道。
2. 按字面实现会命中一个**自伤**：base-only 标定产物本身就缺 `terminal_kind`。实测
   `runs/infra/b_env_rebuild/base_truth20.json` 与 `runs/act_chunk_replay_20260924_k4_base_truth20.json`
   的 `terminal_kind` 覆盖率都是 **0/20**、`field_class` 都是 `partial`。
   它们正是 `RISE_CAP = 0.15` 的标定基准与 20/20 受控成功的参考上界 ——
   按字面实现，门禁会把自己在 §2.3 注释里专门保护过的标定基准判成 `INVALID`。
3. DR-004 的锚点重算（teacher 去饱和）依赖同一份 base-only 真值；若它变 INVALID，
   DR-004 的 A0–A5 全部无法执行。

### 收窄不是放宽：两个方向都有可执行护栏

- 正向 **M6**（清空 `LABEL_CRITICAL_FIELDS` = 静默移除裁定 14）→ 用例 22 变红 ✅ CAUGHT
- 反向 **M7**（把 `terminal_kind` 加进该集合 = 按 DR-D09 字面实现）→ 用例 **1 与 24** 变红 ✅ CAUGHT
  M7 的意义是把本条的理由钉成**可执行证据**：将来谁想「按裁定原文改回来」，这条会立刻红给他看。
- 变异自检 **7/7** 全被抓；规格 §7 回归 **24 用例 / 108 断言**全过。

### 实测影响面

- **A 的 12 份算例逐条对齐**（`runs/infra/lerobot_act_env_20260928/v13probe/`）：
  partial 5 臂共 **16 局** `flick` 全部改判 `unjudged`（11 + 3 + 2，与 DR-D09 的独立复算一致），
  `insufficient_lift = 0`；strict 5 臂维持 `insuff 11 / 3 / 2` 与 `seed2 ep5001` 的 `controlled_success`；
  `provisional_pass` 通道**未动**；residual 两臂（裁定 8）`unjudged=20` / `ctrl=20` 无回退。
  逐臂新旧对比：`measurement_valid` **12/12 不变**，`controlled_success + provisional_pass` **12/12 不变**，
  唯一差异是那 16 局标签迁移 → **回归违例 0**。
- **48 臂官方集：零附带损伤**（48/48 全 `strict`）。v1.4 重分类逐项与 v1.3 一致
  （`ic_status` 45/2/1、可引用三分类 24/22/2、`arms_with_controlled_success` 25、
  `threshold_sensitive` 24、`insuff` 235 局 / 34 臂 / 中位差 0.0164、族均值 `k1 = 3.667 (n=6)`）；
  `b_regate_all.py` 对 16 份留档产物报「裁定变化 **0** 处」。
- 一并推翻 v1.1 的一条设计注释：原文写「`field_blind` 不算 `measurement_invalid`，CLI 显示 FAIL 而不是 INVALID，
  所以它单独一支」。关键字段缺失是「没测到」不是「策略失败」，判 FAIL 会把测量缺口说成能力结论；
  现在 `blind` 也并入 `invalid_reasons`，屏幕显示与文案一致。

### 作废清单

无新增。DR-D09 已作废的「`flick = 23`」维持作废，权威值 **7**（可引用 **2 局 / 920 局**）；
v1.4 之后新产出的 partial 产物不再可能产生假 `flick`。

### 请 D 裁定的两件事

1. **认可或否决本收窄**。若否决（要求按字面实现），则必须同时解决 base-only 标定件缺 `terminal_kind`
   的问题 —— 那需要 A 改 `scripts/audit_lift_base_truth.py` 补该字段并重跑标定，
   在补齐之前按字面实现会立刻作废 `RISE_CAP` 的标定基准与 DR-004 的全部锚点判据。
2. `terminal_kind` 缺失是否应触发**另一条**（非标签类）降级，例如在裁定里 warn
   「终局语义自检不可用」。B 倾向加 warn 不加 INVALID，等 D 定。

### DR-003 验收结果（2026-09-28 深夜实测，B 自证）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | `git status --porcelain` 为空 | 提交后仅剩 `M daily_report.md`（D 线正在写的文件） | **有条件通过**：三线并行时「持续为空」不可达，判据应读作「B 线应纳管文件全部进提交」。已在 §决定 8 的单写者纪律下由 B 分批快照 A/C/D 的待提交文件（提交 `3615c8e`、`4324c47`） |
| 2 | `git ls-files runs/ RL_Harness_v4_20260924/ registry/*/` 为空 | 三者均 **0** 个 tracked 文件；全仓 tracked **245** | **通过** |
| 3 | 仓库体积 < 100 MB（判据已按上文更正） | `size = 5.20 MiB`（loose，317 个对象）、`size-pack = 0 bytes`（未 gc）、`.git = 6.1 MB`；最大 tracked 文件 `docs/lerobot_act_env_setup_20260928.md` **0.20 MB** | **通过**（原写法恒真，已更正） |
| 4 | 体积闸有牙 | `b_git_size_guard.py --selftest` **7/7**；另做过一次 3 MB 文件被 pre-commit 拒绝的真实测试；本轮 4 次提交均打印「暂存区检查：通过（N 个路径，上限 2.00 MB…）」 | **通过** |
| 5 | 容器重建后可复现性门禁不被破坏 | `b_selfcheck_reproducibility.py` **12/12**（v1.4 下重跑） | **通过** |

提交序列：`0137b33`（基线 228 文件）→ `8bb554c`（B-1..B-7）→ `3615c8e`（A/C/D 快照）
→ `3c66215`（门禁 v1.4 / 裁定 14 / DR-007）→ `4324c47`（A 快照）。

### DR-003 验收结果（2026-09-29 12:5x 复测，B 自证；构建 **v1.5 / `f19f61341cbe`**）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | B 线应纳管文件全部进提交 | 本轮 6 个提交（下表）；提交后 `git status --porcelain` 仅剩 `M docs/a_handoff_to_d_20260929.md`、`M docs/lerobot_act_env_setup_20260928.md`（A 线 12:5x 仍在写的两个文件）与 `?? tmp/`（**永不 `git add`**） | **有条件通过**（与 0928 同判读：三线并行时「持续为空」不可达） |
| 2 | 排除域 0 tracked | `runs/` **0**、`tmp/` **0**、`RL_Harness_v4_20260924/` **0**、`registry/*/` **0**；全仓 tracked **245 → 267** | **通过** |
| 3 | 仓库体积 < 100 MB | `size = 6.10 MiB`、`size-pack = 0 bytes`（未 gc）、`.git = 7.1 MB` | **通过** |
| 4 | 体积闸有牙 | `--selftest` **7/7**；`--check-tracked` 通过（267 路径 / 上限 2.00 MB）；本轮 6 次提交 pre-commit 均打印「暂存区检查：通过（N 个路径…）」 | **通过** |
| 5 | 容器重建后可复现性门禁不被破坏 | `b_selfcheck_reproducibility.py` **12/12**（v1.5 下重跑，12:44–12:46 那一批） | **通过** |
| 6 | **新增**：`git` 不得改写门禁脚本内容（否则 `GATE_BUILD` 自指纹失效） | 提交后 `sha256sum scripts/b_gate_controlled_success.py` = **`f19f61341cbe`**，与提交前逐字节一致；`docs/b_controlled_success_v1_20260928.md` = `c7fadabe8e3c` | **通过**（DR-002 护栏 3 在 v1.5 上再证） |

本轮提交序列（全部由 B 执行，DR-003 决定 8 单写者；`git add` 一律显式路径）：

| commit | 前缀 | 内容 | 路径数 |
|---|---|---|---|
| `0fd18b1` | `feat(gate)` | v1.5 落地裁定 10 免罪通道 + 构建冻结（DR-008/009/010/011） | 8 |
| `0b8e537` | `chore(infra)` | `setup_env.sh` lock 优先 + pip 入 lock + lerobot pin 文档 + 否掉错源（DR-012 / §19-B③④） | 3 |
| `3d9c46b` | `docs(handoff)` | B → A / C / D 三份 0929 交接单 | 3 |
| `7f31366` | `docs(report)` | `daily_report.md` 追加 09-29 B 线小节（687 → 1766 行；同文件顺带带上 A/D 未提交段落，append-only 单文件无法拆行） | 1 |
| `5b881b3` | `chore(infra)` | A 线待提交快照（12:53 时间点，A 仍是活进程） | 13 |
| `4ad3950` | `chore(infra)` | C 线待提交快照 | 12 |
| `f90baea` | `chore(infra)` | D 线待提交快照 | 5 |

> 注：`daily_report.md` 是四线共写的 append-only 单文件，B 追加时先 `cp -a` 留底再 `cat >>`，
> 并用 `head -<前行数> | diff -` 证明**前 1614 行逐字节未改**（A 当时正在并发追加）。

---

## DR-008 裁定 10 免罪通道（`clip_at_train_absmax`）落地：门禁 v1.5

- 时间：2026-09-29 上午（容器检修重启后接手）；登记人 B；裁定人 D（裁定 10 / 裁定 16.4 / 增补五 §3、§7）
- 触发来源：
  - A 的移交单 `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md`（09-28 22:55）：免罪册缺 裁定 16.4
    明文要求的 `trimdone0_minmax_k2_lr1e-5_s20k_seed0` 条目，B 的 v1.4 权威表三分类停在 **24/22/2**，
    与增补五 §3 要求的免罪后 **25/22/1**、`measurement_valid` **47/1** 冲突；
  - D 的会签前独立核验 `scripts/d_verify_exoneration_cosign.py` →
    `tmp/agentD_review_20260929/D_cosign_k2seed0.json`（09-29 10:43）：
    `cosign_fact_basis=true`，但 `registry_alone_is_sufficient=false`，实测命中**三处代码级阻塞**。
- 性质：**判据实现层修复 + 免罪册补条目**。不改任何阈值常量（`RISE_CAP` / `FINAL_RISE_MIN` /
  `INPUT_BLOWUP_TOL` / `DISPUTED_BLOWN_BAND` 全部不动），不构成 baseline 重置。

### D 实测的三处阻塞（B 逐条复核确认）

| # | 位置 | 现象 | D 的实测状态字 |
|---|---|---|---|
| 1 | `scripts/b_gate_controlled_success.py:381` 带内判定 | 争议带 `[0.03,0.08]` 对**所有** `probe_kind` 一律生效；而 裁定 10 的目标臂 blown=**0.212**，必然在带外 ⇒ 条目永远无法受理 | `out_of_band_refused`（`scope=artifact` 两种 kind 都命中） |
| 2 | `scripts/b_gate_controlled_success.py:358` 臂级豁免前置 | `scope="arm"` 要求 `impl_status=="known"`；目标臂 plain 产物 `blown_metric_impl=null`（`missing_legacy_grandfathered`） | `scope_requires_known_impl` |
| 3 | `scripts/b_gate_controlled_success.py:806` 晋级闸 | 只认 `ic_status ∈ {verified_ok, not_applicable_verified}`；目标臂是 `violated` ⇒ **即使豁免受理也不晋级**，`measurement_valid` 仍 False | `promotion_possible_without_code_change=false` |

### 决定（逐条）

| # | 决定 | 理由 / 护栏 |
|---|---|---|
| 1 | 带内判定**按 `probe_kind` 分通道**：新增 `BAND_EXEMPT_PROBE_KINDS = (clip_at_train_absmax,)`，**只有**白名单内的 kind 免带内检查；未知 kind 一律按带内处理 | 保守默认：新增通道必须显式进白名单，不能让豁免册变成「翻案万能钥匙」（`_doc` 原意保留） |
| 2 | 裁定 10 通道**只受理 `scope="artifact"`**（键 = plain 产物 sha256），不受理 `scope="arm"` | 免罪的对象是**一次具体测量**（某 ckpt × 某 plain 产物），不是整条臂；artifact scope 天然「重跑即失效」，必须重新探针。同时**绕开**阻塞 2 而不放松臂级豁免的防连带护栏（阻塞 2 的 `scope_requires_known_impl` 分支原样保留） |
| 3 | 裁定 10 通道用**自己的牙**替代争议带牙，五条全部可执行核验：① `scope=artifact`；② 登记的 `clip_C` == 被裁定产物**自己**声明的训练期 absmax（`input_constraints.train_time_norm_absmax` 或 `input_contract.blowup_threshold`，容差 1e-6）；③ 探针产物存在；④ 探针产物 sha256 与登记一致；⑤ 探针产物**自己**记录的截断值（`execution_constraints.norm_input_clip`）== `clip_C` | 条件 ② 就是 v1.3 已写进代码断言的「C 必须 == 该 ckpt 的 `blowup_threshold`」；条件 ⑤ 是新增的**独立**核验：光登记 C 不算，探针文件里必须真的截在这个 C 上。A 的判别力反证（C=5.0 时 seed 5007 verdict 翻转、`insufficient_lift` 1→0）说明「截得越紧越安全」是假的，所以 C 必须钉死 |
| 4 | 条目必须携带 裁定 10 五条准入的逐条核对结果（`ruling10_conditions`，五键全 `true`）与 D 的会签（`cosign.by` 非空 + `cosign.fact_basis=true`），缺任一 ⇒ 不受理 | 裁定 16.4 原文「由 B 写、D 会签」。会签缺失不是静默忽略，是显式状态字 |
| 5 | 晋级闸按 kind 分路：`EXONERATION_PROMOTION_SOURCES` = `{reblown_single_source: (verified_ok, not_applicable_verified), clip_at_train_absmax: (violated,)}` | **精确**放开：带内重测通道行为逐字不变（24 个既有回归用例不受影响），只有 裁定 10 通道能把 `violated` 升为 `probe_exonerated`。不做「任何 exonerated 都能升 violated」的宽口径 |
| 6 | `GATE_VERSION` 升 **v1.5**；`GATE_BUILD` 必变 ⇒ **裁定 16.3 改判 7 再次触发** | 落地后必须 `scripts/b_regate_all.py` 全量重判 + 重出 `runs/infra/b_official_arms/reclassification.json`；增补五 §3 的 v1.2.1 表与 B 的 v1.4 表同时降级为历史口径（不作废、不得当现值引用） |
| 7 | 会签的 `gate_build` 与当前 `GATE_BUILD` 不一致时**不拒判**，但在裁定里显式回显 `cosign_gate_build` / `cosign_build_current` / `cosign_build_matches`，并要求 D 重跑 `scripts/d_verify_exoneration_cosign.py` | 否则会死锁：条目只能在代码改完之后写，写的那一刻 D 的会签必然锚在旧 build 上 |
| 8 | `trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0` 的 `ic_status` **本条不动**（维持 `probe_exonerated`） | A §2.3 报的是**标签语义**分歧（A 记 `verified_ok`），A 自己确认「不影响任何计数」。改它属口径裁定，B 不代做 → 见下文「请 D 裁定」 |

### 验收判据（预登记，落地后逐条实测回填）

1. `python3 scripts/b_selfcheck_gate_regression.py`：既有用例 **24/24、108/108 不退步**，且新增 裁定 10 通道用例全绿；
2. `python3 scripts/b_selfcheck_gate_mutation.py`：既有用例 **7/7 不退步**，且新增变异体（正向删通道 / 反向放宽成「带外也受理」）都被抓；
3. `python3 scripts/b_regate_all.py`：48 臂重判后 `reclassification.json` 的
   `summary.ic_status` = `verified_ok 45 / probe_exonerated 2 / violated 1`、
   `summary.citable` = `25 / 22 / **1**`、`measurement_valid` = **47 / 1**；
   计数层 `controlled_success 135 / insufficient_lift 235 / flick 7 / over_lift 0 / provisional_pass 0` **一格不动**；
4. `python3 scripts/d_verify_exoneration_cosign.py`：三处阻塞状态字全部消失（`blocker_*_hit` 由 `true` 变 `false`）；
5. `python3 scripts/b_selfcheck_golden_values.py` **47/47**、`b_selfcheck_t17_mutation.py` **6/6** 不退步；
6. `b_selfcheck_reproducibility.py` **12/12** —— 依赖 `/root/venvs/rlrobot`（容器检修后被抹掉，C 线 10:46 起在重装），**env 就绪后补跑**。

### DR-008 验收结果（2026-09-29 11:5x 实测回填，B 自证；构建 **v1.5 / `f19f61341cbe`**、规格 `c7fadabe8e3c`）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 回归不退步 + 新通道用例全绿 | **157/157 断言、39/39 用例**（v1.4 基线 108/24 ⇒ 断言 +49、用例 +15，全为 裁定 10 通道与晋级闸分路） | **通过** |
| 2 | 变异不退步 + 新变异体被抓 | **15/15 被抓**、`baseline_all_green=true`（v1.4 基线 7 ⇒ 新增 M8–M15） | **通过** |
| 3 | 权威表三处数值 + 计数层一格不动 | `ic_status` **45/2/1**、`citable` **25/22/1**、`measurement_valid` **47/1**；计数层 `controlled 135 / insuff 235 / flick 7 / over_lift 0 / provisional 0 / raw 377 / 分母 960` —— 与预登记值**逐格相同**（脚本比对 `tot==exp → True`） | **通过** |
| 4 | D 的 verifier 三处阻塞状态字消失 | `blocker_band=False / blocker_scope=False / blocker_promotion=False`；护栏 `arm_scope_requires_impl=True / reblown_band_limited=True`；6 个反例全被抓；`ACCEPTANCE=True`、**exit 0** | **通过**（D 11:19 复签 = 裁定 26；B 11:5x 换块后**独立复跑**同脚本仍 exit 0） |
| 5 | 黄金值 / T17 变异不退步 | `b_selfcheck_golden_values.py` **47/47**；`b_selfcheck_t17_mutation.py` **6/6** | **通过** |
| 6 | 可复现性 12/12（env 就绪后补跑） | **12/12**；`robosuite` 实装 **1.5.2 == requirements.txt pin**、`lock==pin`；8 个 checkpoint `obs_dim` 全兼容（另 4 个已确认作废且作废清单自身健康） | **通过**（C 线 ~10:51 重建 venv 后补跑，检修未破坏门禁） |

补测两条**判据非恒真**的证据（沿用 DR-003 判据 3 的教训）：
① D 的 verifier `--expect blocked`（v1.5 前的期望）在现构建上 **exit 1**，`--expect exonerated` **exit 0**
⇒ 两种期望各自都有会红的条件；② `b_regate_all.py` 对 **16 份**留档产物报「裁定变化 **0** 处」
（exit 1 是「有臂未过门禁」的正常语义，与 D 的 `regate48.log` 同）。

### 请 D 裁定（B 不代做）

1. **`probe_exonerated` 的标签语义**（A §2.3）：stdfloor 臂 blown=0.040 ≤ 0.05，本来就 `verified_ok`，
   现因命中争议带重测豁免册而被标 `probe_exonerated`。v1.5 后 `probe_exonerated` 将有 **2** 臂
   （stdfloor + k2 seed0），而增补五 §3 的「免罪后」列隐含 **1** 臂。计数层（47/1、25/22/1）两种口径都对，
   分歧只在 `ic_status` 分布这一列。是否把「本来就没超阈」的臂降级回 `verified_ok`、
   让 `probe_exonerated` 只表示「非探针不可信」？
2. **DR-007 的两件事仍未见明文回复**：① 认可或否决 B 对 裁定 14 的收窄；② `terminal_kind` 缺失是否加 warn。
3. A §8 的两处 schema 差异（行级 `provisional_pass` 列、INVALID 臂行级失效模式计数写 `null` 还是写数）。

**结案状态（2026-09-29，D 已在 增补六 逐条回复）**：
① → **裁定 24 / DR-D21：不降级 stdfloor**，改为按 `probe_kind` 分桶（v1.5 已落地，D 在 裁定 27 §12.2 确认
「1 对 2」的前瞻问题已被 B 的 kind 分桶解决）；② → **裁定 22 / DR-D19：认可 B 的收窄**，D 同时更正自己
DR-D09 的字面表述过宽（护栏③ 要求的明文已写进规格 §2.16.1），`terminal_kind` 缺失 → **裁定 23 / DR-D20：
加 warn、不降级，但必须先修掉一处空转判据**（六项，B 预登记为 v1.6，见 DR-010）；
③ → **裁定 20 / DR-D16 ②③：`provisional_pass` 行级列由 A 补**、INVALID 臂行级计数**维持 `null`** 但须加
`counts_withheld_reason="measurement_invalid"` 并在 meta 写明「合计层包含被 withheld 的行级计数」（**B 无需改门禁**）。

### 影响面

- **解锁**：A 的 48 臂权威表可迁到新构建（A §6.1 的迁移前置条件 = `NOT_CITABLE_measurement_invalid==1`
  且三分类 `25/22/1`）；`k2 seed0` 的 **9/20** 恢复可引用，固定写法见 A 移交单 §5。
- **作废清单**：无新增。`_replan1`（blown 0.1692、**无探针**）维持 INVALID。
- **不影响的**：任何评测产物（actlog 一字节不动，重判只走门禁）；A/C/D 的实现文件；`runs/` 内容。

---

## DR-009 v1.5 **构建冻结声明** + 裁定 26 三前提收尾（①③护栏①）

登记时间：2026-09-29 11:5x。依据：D 的 裁定 26（memo §11）与 裁定 27 §12.4 收尾清单、DR-001。

### 决定（逐条）

1. **v1.5 冻结（裁定 26 前提①，D 要求 B 明文声明）**：`scripts/b_gate_controlled_success.py`
   冻结在 **`GATE_BUILD = f19f61341cbe`**，B 在本批次内**不再改该脚本**。声明同时写进规格文档抬头
   （`docs/b_controlled_success_v1_20260928.md` 开头「构建冻结声明」段），因为 D 的复签锚在这个 build 上，
   锚在移动靶上等于没有会签（裁定 16.3 同源）。
2. **两根轴分开记（B 补的一条口径，请 D 认可）**：`GATE_BUILD` = 门禁脚本内容哈希（**会签锚**）；
   `GATE_SPEC_SHA` = 规格文档内容哈希（**另一根轴**）。实测 spec 轴在 D 复签后前移过两次：
   `132fceb89f68`（D 11:14 跑 verifier 时）→ `154b3636056f`（B 11:21 补 §2.17/§6/§7）→
   **`c7fadabe8e3c`**（本轮补冻结声明 + §2.16.1 的 裁定 22 明文 + §2.18 预登记），
   **全部是文字/登记变更，无判据变更**；build 轴自 `f19f61341cbe` 起未动 ⇒ D 的复签**仍有效**。
   D 的 memo §12.1 把权威表的 spec 记成 `132fceb89f68`，实测该表记的是 `154b3636056f`（本轮起为 `c7fadabe8e3c`）
   ⇒ 属**转写误差**，请 D 在第三轮 verifier 里把 spec 轴也回显，免得两轴混淆。
3. **会签块换到本 build（前提③）**：按单写者纪律 `configs/` 由 B 写、内容 D 产 ——
   B 把 `tmp/agentD_review_20260929/D_cosign_block_for_registry.json` 的 `cosign` 对象**原样替换**进
   `configs/b_probe_exonerations.json` 的 `85c46dfb…` 条目（未改 D 一个字），只**另加**一个 B 署名的
   provenance 键 `cosign_swap_recorded_by_B`（换块时间/来源/被取代的旧 build/两轴现值）。
   实测换块后门禁回显 `cosign_build_matches = True`、`cosign_build_current = f19f61341cbe`、
   `ic_status = probe_exonerated`、`status = exonerated`、`clip_C = 12.469445`。
4. **护栏①（裁定 25）实现为「并列独立桶」，判据用三值里的 `is False`**：
   `summary.pending_cosign_reverify = {n, arms, criterion, cosign_not_required_arms, zero_condition}`。
   两点必须写明，否则会被误读：
   - **不从 `ic_status` / `probe_exoneration_by_kind` 里扣减**。D 在 裁定 27 §12.1/§12.2 已按
     「by_kind 2 臂 + 桶尚未实现」的实际形状**预先认可**了 `ic_status 45/2/1` 与 `citable 25/22/1`，
     扣减会与那份认可冲突；前提③ 完成后本桶 `n=0`，两种读法收敛于同一张表。
   - **判据是 `cosign_build_matches is False`，不是 `is not True`**。三值语义：`True`=会签锚在当前 build；
     `False`=会签存在但锚在别的 build（**这才是**护栏①要承接的待复签）；`None`=该通道**不要求**会签
     （`reblown_single_source` 的册子条目没有 `cosign` 字段，见 `configs/b_probe_exonerations.json` 的 `_schema`：
     `cosign` 仅 `clip_at_train_absmax`）。B 首版写成 `is not True`，实测把 stdfloor 臂永久挂在桶里
     （`n=1`，清不掉）——那是一条**永不消失的假红**，与 裁定 27.1「恒假的闸等于没有闸」同型，已改。
     `None` 的那一臂改记在 `cosign_not_required_arms` 里，可见但不报警。
5. **裁定 23.4 的聚合侧先行落地（不改门禁、不升 build）**：`b_official_arms_reclassification.py` 新增行级
   `terminal_kind_coverage`（`{n, of}`）与汇总 `summary.terminal_semantics_unavailable`（`{n, arms, criterion}`），
   并新增顶层 `known_vacuous_fields_pending_v16`，显式声明「v1.6 之前
   `terminal_semantics.suspect_truncation_labeled_as_failure` 在覆盖不足的产物上是**空转的 `false`**，
   不得读成清洁保证」。**只做聚合**（覆盖率取门禁已回报的 `field_presence` / `episodes_total`），
   **不重算任何判定** —— 避免出现「同一判据两个实现」（裁定 21 / DR-D17 的教训）。判定侧三值化只能在门禁里做，属 v1.6。
6. **`measurement_valid` 47/1 变成机器可核的一格**：原先只能由 `citable` 反推，现行级透出
   `measurement_valid`、汇总给出 `summary.measurement_valid = {true, false, false_arms}`。
   D 的验收判据里这一项从此可直接比对，不必靠散文。

### 验收（本轮实测）

| 项 | 实测 | 结论 |
|---|---|---|
| `GATE_BUILD` 未动 | `f19f61341cbe`（换册子前后、改报表脚本前后各测一次，均同） | **通过** |
| `summary.pending_cosign_reverify.n` | **0**（`cosign_not_required_arms` = 1 臂 stdfloor） | **通过**（裁定 25 护栏①「换块后清零」） |
| `summary.terminal_semantics_unavailable.n` | **0**（48 臂 `terminal_kind` 覆盖全 20/20） | **通过**；空转风险的实际落点是**标定件** `base_truth20.json`（0/20），不在 48 臂官方集内 ⇒ v1.6 的验收必须直接判该文件 |
| 权威表数值 | `25/22/1`、`45/2/1`、`47/1`、计数层 135/235/7/0/0（raw 377、分母 960） | **通过**（与 DR-008 判据 3 逐格相同） |
| D 的 verifier（B 独立复跑） | `--expect exonerated` **exit 0**、`ACCEPTANCE=True`、三 `blocker_*` 全 false、两护栏全 true、6 反例全抓 | **通过** |
| 反向对照 | 同脚本 `--expect blocked` **exit 1** | **通过**（判据非恒真） |

### 影响面

- **解锁**：裁定 26 的三前提全部闭合（①冻结声明 / ②权威表已在 `f19f61341cbe` 上重出并被 D 独立复算验收 /
  ③会签块已换）+ 护栏① 已实现且清零 ⇒ **`PENDING_IMPL` 标注可撤下**，A 可按 裁定 27.1 迁表
  （前提：A 先把自己的 L5/G2 修得与实际状态一致，见 DR-010 与 B→A 交接单）。
- **不动的**：任何评测产物、A/C/D 的实现文件、计数层任何一格。
- **本轮改到的 B 线文件**：`configs/b_probe_exonerations.json`、`scripts/b_official_arms_reclassification.py`、
  `docs/b_controlled_success_v1_20260928.md`、`scripts/b_selfcheck_goal_conditioning_t17.py`（DR-011）。

---

## DR-010 裁定 23（P1）**无代码承载** —— 预登记为 v1.6，并把排序冲突上报 D

登记时间：2026-09-29 11:5x。依据：DR-001（改门禁前先登记）、裁定 23 / DR-D20、裁定 25 的 D 执行承诺。

### 事实（可核，不是措辞）

1. D 的 裁定 25「执行承诺」原文写的是「**B 的 v1.5 落地（含 裁定 23 的六项）后**，D 跑 verifier」；
   裁定 23 自己也写「优先级 P1，**与 v1.5 同批做**（都改同一个脚本，避免连升两个构建）」。
2. 实际落地的 v1.5（`f19f61341cbe`）**不含 裁定 23 的任何一项**：门禁 `:934` 仍是
   `"suspect_truncation_labeled_as_failure": (n_termfail > 0 and n_full == n_termfail)`（二值），
   无 `terminal_kind_coverage` 字段，变异自检无 M16。
3. D 的 裁定 26 复签与 裁定 27 §12.4 收尾清单**都没有核这一项**（只列了 build 冻结声明 / 权威表重出 /
   cosign 换块 / 护栏①）⇒ **裁定 23 目前是「裁定成立但无代码承载」**，与 D 今日第五次自我纠错同型，
   这次漏在 **B 侧**（B 的 v1.5 只做了 DR-008 的三处，没有把 裁定 23 并进同一批）。B 认这条。

### 决定

1. **不在本轮改门禁**。理由：D 在 裁定 26 明确要求「B 须明文声明 v1.5 冻结」，且 D 的复签锚在
   `f19f61341cbe`；此时改脚本会让刚拿到的复签当场失效，并再次触发 裁定 16.3 / 改判 7 的全线重出
   （B 的表、A 的 48 臂表与 `ckptseq/v14_crosscheck/`、D 的 `regate48`）。
2. **裁定 23 的六项预登记为 v1.6**，逐条验收判据已写进规格 **§2.18**（含 M16 反例、
   `base_truth20.json` 的 `null` 与 `note` 非空、48 臂 `measurement_valid` 仍 47/1、计数层一格不动）。
   落地即升 `GATE_BUILD` ⇒ **D 须跑第三轮 verifier 复签**、A 的表须在新 build 上重出 meta。
3. **过渡期引用纪律（立刻生效，不需要等 v1.6）**：任何引用
   `suspect_truncation_labeled_as_failure = false` 的结论，必须同时注明该产物的 `terminal_kind` 覆盖 n/N；
   覆盖不足时该值为**空转**，既不得读成能力结论、也不得读成清洁保证（裁定 23.1 两个方向都禁）。
   权威表已用 `known_vacuous_fields_pending_v16` 把这条钉在产物里（DR-009 决定 5）。
4. **裁定 23.5（标定基准须显式声明）在 v1.6 一并做**：`base_truth20.json` 与
   `act_chunk_replay_20260924_k4_base_truth20.json` 是 `rise_cap=0.15` 的标定基准与 20/20 参考上界，
   两者 `terminal_kind` 覆盖都是 **0/20** ⇒ 必须在受版控登记册里声明「缺失已被接受 + 理由 = base-only 真值
   不含终局分类」。**「缺字段但被当基准」必须是声明过的状态，不能是意外。**

### 请 D 裁定（排序，B 不代做）

**(a)** v1.5 冻结生效、A 先按 裁定 27 迁表，裁定 23 作为 **v1.6 紧随其后**；
**(b)** 立即升 v1.6（= v1.5 + 裁定 23 六项）再迁表，一次 build、一次复签、一次迁表。

B 推荐 **(a)**，理由三条：① 裁定 23.1 明确**不降级** `measurement_valid`，六项**不改任何计数**
（48 臂 `terminal_kind` 覆盖全 20/20 ⇒ `summary.terminal_semantics_unavailable.n` 实测已是 0），
所以迁表结果不受 v1.6 影响，(b) 的「少升一次构建」换不到数字上的收益；
② A 此刻正在按 裁定 27.2/27.3/27.4 修 L5/G2/补 S10，此时换 build 会让 A 的
`a_gate_build_drift_check.py` 默认指纹**再次**过期（B 已在 0928 深夜为此发过一次 §8.3bis 告知）；
③ (b) 会让 D 刚出的 裁定 26 复签在 30 分钟内第二次作废，而 D 自己在 裁定 26 里把
「build 冻结」列为撤下 `PENDING_IMPL` 的第一前提。
**若 D 选 (b)**，B 立刻执行：六项已预登记完毕，实现 + 全量自检 + 重出表约需一轮，
但请 D 同时通知 A 暂停迁移，避免 A 在换 build 的中途读表。

### 另一件请 D 裁定的小事（裁定 27.5，P2）

D 指出 B 的册子条目有命名卫生问题：布尔断言键 `ruling10_conditions.cond1..cond5` 与其证据键
`ruling10_conditions_evidence.cond1..cond5` **共用 `condN` 前缀**，导致任何递归校验器歧义（A 的 L5 假红即由此来）。
B **本轮不改名**，理由：该条目刚被 D 复签，换块与改名同批做会让「D 签的到底是哪一版条目」变得不可核；
且 裁定 27.2 已要求 A 按门禁真正读的字段名精确取（`entry["ruling10_conditions"]` + `RULING10_CONDITION_KEYS`），
A 收窄后本项即无害。**请 D 认可把改名并入 v1.6**（届时条目本就要随 build 复签，一次做完，不额外增加复核轮次）。

### 结案（2026-09-29 12:0x，D 已在 裁定 29.2 / memo §15 回复）

1. **排序 → D 选 (a)**：v1.5 冻结生效、A 先迁表（**用 `f19f61341cbe`，不必等 v1.6**）、
   裁定 23 作为 **v1.6 紧随其后**。D 的独立实证依据与 B 的推荐一致：裁定 23 要修的空转标志
   在官方 48 臂集上**一处都不咬**（11:45 表 `summary.terminal_semantics_unavailable = {n:0, arms:[]}`、
   逐臂 `terminal_kind_coverage` 全 `{n:20, of:20}`），那个 0/20 实例是
   `runs/infra/b_env_rebuild/base_truth20.json`（scripted base，**不在** 48 臂集内）
   ⇒ 选 (b) 对迁表结果影响**恰好为零**，却要付「A 半途换 build + 漂移检查指纹再次过期」的确定成本
   —— D 的原话：**「零收益有成本。」**
2. **归属更正：D 认定这是 D 的起草错误、不是 B 的落地缺口**。裁定 25「执行承诺」里那句括号
   （「含 裁定 23 的六项」）**划除**；裁定 23 是 P1、**从未列入 DR-008（v1.5 批次）的验收范围**
   ⇒ **D 的会签与 裁定 28 的闭环结论不失效、不重开**。B 在上文「事实 3」里认的那条账，
   D 已把责任划回自己；B 记录在案，此后不再自引为缺口（B 的预登记动作本身是对的：
   规格 §2.18 明写「**这一节是预登记，不是已实现的判据**」，符合 DR-001）。
3. **v1.6 落地时 B 的义务（裁定 29.2 第 3 条 / memo §19-B②）**：升 build 后**主动通知 D 跑第三轮复签**，
   不要等 D 发现。B 承诺：v1.6 提交前先在 `daily_report.md` 与 `docs/b_handoff_to_d_*.md` 里点名。
   v1.6 落地即升 build ⇒ 会签自动失效 ⇒ D 第三轮复签 + A 表重出 meta（**迁表不算白做，只刷两轴值**）。
4. **裁定 29.1 对 DR-009 决定 2 的更正（D 第七次自我纠错）**：**引用锚只在 build 轴，spec 轴是观测日志、
   不是钉子**。权威口径的固定写法自此为 **`v1.5 / f19f61341cbe`（不带 spec 值）**。
   B 在 DR-009 决定 2 里提的「请 D 第三轮 verifier 回显 spec 轴」相应**作废**（D 已自裁）；
   会签块里 `gate_spec_sha256_at_cosign` 的**数值不改**（11:14 的可核历史观测），
   B 已按 memo §19-B① 在其**旁边补注**「不参与效力判定」。
5. **本节 §5 的改名提请（裁定 27.5，P2）D 本轮未裁** ⇒ 维持 B 的处理（本轮不改名），
   继续挂在 v1.6 批次里，等 D 明文认可后再动。

---

## DR-011 C 线 T17 回执的 B 侧只读验收 + `SKIP` 语义裁定 + B 自查出的一处假红

登记时间：2026-09-29 11:5x。依据：C 的回执 `docs/c_handoff_to_b_t17_landed_20260929.md`、
B 的交接单 `docs/b_handoff_to_c_20260928.md` §6（5 条验收）、ADR-C-004（SKIP 记 `ok=None`）。
**边界**：B 全程只读 C 的文件（`harness/queue_td_learner.py`、`scripts/c_*`、`runs/infra/c_*` 一字节未改），
复核只跑 B 自己的脚本。

### 5 条验收逐条实测

| # | B 的要求 | B 的独立实测 | 结论 |
|---|---|---|---|
| 1 | `cfg.goals` ≥2 项，`goal_dim<2` 时显式拒绝 | B 的子进程探针真调 C 的 learner：`LearnerConfig.goals` 缺省 = `['lift_A_to_B','lift_B_to_A']`（2 项，与 B 的 `GOALS` 逐字相同）；单 goal 配置调 `_goal_onehot` → **`LearnerRefused`**，且 `issubclass(LearnerRefused, KeyError) == False` | **通过** |
| 2 | T17-a/c/d/e 落成单元测试并全过 | 读 C 的 `runs/infra/c_t17_goal_conditioning.json`（11:47）：`n_checks=50 / n_pass=44 / n_failed=0 / n_skipped=6`；`components_implemented` 4 个、`components_not_implemented` = editor / candidate_filter / predictor | **通过（带覆盖缺口，见下）** |
| 3 | B 的 `teeth_check.non_vacuous` 仍为 `true` | B 自己重跑 `b_selfcheck_goal_conditioning_t17.py`（不复用 C 的转述）：`non_vacuous=true`、`n_broken_variants=6`、`all_broken_variants_caught_by_t17=true`、`blocked_variants_cannot_silently_pass=true` | **通过** |
| 4 | 黄金值 47/47、T17 变异 6/6 | 本轮实测 **47/47** 与 **6/6**（`baseline_all_green=true`） | **通过** |
| 5 | `bc_rows_at_xi0 / bc_rows_total` 计数落地 | 读 `runs/infra/c_learner_shard_smoke.json`：`takeover` 通道 `28/28`（ratio `1.0`）、`clean`/`terminal` 无 BC 行（ratio `null`，**没有伪造 0/0**）；`bc_anchor_xi0_gap.verdict = "substantive_gap"` | **通过**（B 接受 C 的判定：这是**实质缺口**，不是已知近似） |

### B → C 的裁定：`SKIP` 的口径**采纳**（未实现 ≠ 实现错），但加三条护栏

C 问「你若认为未实现即应判 FAIL 而非 SKIP，请回一条裁定」。**B 的裁定：维持 SKIP**，
理由与 C 一致 —— FAIL 会把它混进「实现错了」，而事实是「还没实现」，两者修法不同；
把「没做」记成「做错」会让失败计数失去指向性（与 裁定 12「缺字段不得读成能力结论」同源）。
但 SKIP 是有代价的口径，必须配三条护栏，否则会变成「全绿」的化妆品：

1. **SKIP 不得进任何通过率**。`44/50（6 SKIP）` 的写法正确；**禁止**写成 `100%` 或 `44/44`。
   任何把 T17 结果喂进门禁/发布判据的地方，必须读 `n_skipped` 与 `components_not_implemented`，不能只读 `n_failed==0`。
2. **覆盖主张必须带分母**。凡引用「T17 goal 贯通已验」，一律写成
   **「已实现 4/7 组件已验（base/Q/actor_target/critic_target）；editor / candidate_filter / predictor 未实现、未验」**。
   附录 02 §12 要求的是五类组件**分别**验，4/7 不是全覆盖。
3. **SKIP 必须会到期**。三个组件实现后，这 6 条必须转成真断言并计入通过率；
   B 的牙齿脚本已把这一条记成 `partial_verified`（不是 `closed_verified`），
   实现后由 C 通知 B 改判 —— 长期挂着的 SKIP 与长期挂着的假红一样会让人脱敏。

### C 回执里的一处**事实错误**（结论不变，措辞须更正）

C 的回执 §2 写：`goal_epoch_incompatible` 与 `deadline_miss`「**都在** ADR-C-001 F3 的 `CENSORING_REASONS` 里」。
B 实测 `harness/data_bridge.py`：`CENSORING_REASONS`（`:45-54`）含 `deadline_miss`，
**不含** `goal_epoch_incompatible`，而且这是**有意排除**（`:40-42` 注释：换向族
`goal_epoch_mismatch / goal_epoch_incompatible / next_goal_switch` 属 §5.5 的**合法边界**、不是信息缺失，
故故意不算删失）。
⇒ B §5 #6 的实质要求（晚到 + 换向留下**两条独立**理由）**成立**：`:379` append `deadline_miss`、
`:388` append `goal_epoch_incompatible`，`:386-387` 的注释就是「晚到 + 换向必须同时留下两条理由」。
**请 C 更正回执措辞**（不需要改代码）；这条之所以要挑出来，是因为「都在 X 里」这类断言一旦写进交接单，
下游会拿它当账本口径的依据，而 `censored_slot_ratio` / `censoring_by_reason` 恰恰**不**统计换向族。

### B 自查出的一处假红（本仓第三次同型事故，这次在 B 自己的工具里）

B 的 `scripts/b_selfcheck_goal_conditioning_t17.py` 原先把「真贯通还差什么」写成一份**硬编码行号 TODO**，
其中两条标着 `owner=C, blocking=True`：`queue_td_learner.py:65`（`cfg.goals = ("lift",)`）与
`:135`（`_goal_onehot` 在 `goal_dim==1` 时恒为 `[1.0]`）。C 在 0929 已把两条都改掉了，
但清单是散文、不会自己更新 ⇒ 它继续把**已闭合**的项报成「C 阻塞」（实测打印 4 项阻塞，其中 2 项是假的）。
与 D 在 裁定 27.4 判 A 的 G2 假红**同型**（文本/行号锚点失效），也与本仓「恒真的闸等于没有闸（DR-003 判据 3）、
恒假的闸也等于没有闸（裁定 27.1）」是同一条教训。

修法（已落地，**不改门禁 ⇒ 不升 build**）：新增 `_probe_wire_status()`，用**子进程真调** C 的 learner 测
`goals` 缺省与单 goal 拒绝行为；清单每项带 `status`（`closed_verified` / `open` / `open_not_probed` /
`unprobed` / `partial_verified`）+ `evidence`。实测结果：7 项里 **4 项 `closed_verified`**、
**2 项 `open_not_probed`（A 侧，B 不代判他人文件，明确标「未实测」）**、1 项 `partial_verified`
⇒ **当前阻塞 2 项**（原报 4 项）。A 侧与文档侧**不做文本扫描**，宁可标「未实测」也不冒充结论。
**探针跑不起来时记 `unprobed` 并打 WARN**，既不冒充闭合也不冒充开放（已实测该分支：把脚本复制到
`/tmp` 跑，`harness` 不可导入 ⇒ 3 项 `unprobed` + WARN，`closed_verified` 不增）。

过程中 B 自己踩到一个坑，登记备查：`evidence` 字符串是**实参**，即使 `_status()` 因探针失败提前返回也照样求值，
首版用 `%d` 格式化 `probe.get("goals_default_n")` 撞到 `None` ⇒ 变异自检的 6 个变体**全部** `no_json`
（`b_selfcheck_t17_mutation.py` 报 0/0）。已改成空值安全并复跑 **6/6**。
教训与 裁定 27.3 同型：**判据类工具的反例必须取自真实产物形状** —— 变异自检是在临时目录里跑被测脚本的副本，
任何依赖仓库相对路径的新代码都必须在那种形状下也能安全降级。

---

## DR-012 环境侧：`setup_env.sh` 改 lock 优先 + pip 入 lock；lerobot pin 摘出并**否掉一个错源**

登记时间：2026-09-29 12:2x。依据：D 的 memo §19-B③/B④（裁定 29.4）、C 的 **ADR-C-006**、裁定 30 / DR-D29。
**性质：基础设施与文档，不改任何判据、不改任何产物数字。**

### 决定 1：`scripts/setup_env.sh` 的安装口径改为 **lock 优先 + `--no-deps`**（memo §19-B③）

- **事实**：脚本原先只按**范围 pin** 装（`numpy>=2` / `gymnasium<1.3` / `robosuite==1.5.2` …）。
  C 在 0929 检修后重装时实测被解析器判死：`robosuite 1.5.2 → mink==0.0.5 → numpy<2.0.0`
  与 `numpy>=2` 冲突 ⇒ `ResolutionImpossible`；触发条件是 **pip 24.0 → 26.2.1**（解析器更严、会回溯到 `mink 0.0.5`）。
- **改法**：① 有 `requirements.lock.txt` 就 `pip install -r lock --no-deps`（精确安装、跳过解析器）；
  ② lock 缺失才回退范围 pin，并打 **WARN** 写明已知冲突与「不要就地放宽 pin，按 ADR-C-006 用 lock 复现并报 D」；
  ③ freeze 时把 provenance 写进 lock 头部（`generated_by` / `generated_at` / `install_mode` / `python` / `pip`）。
- **口径（C 提出、D 采纳，B 照此实现）**：**解析器到不了某个组合，不代表那个组合不可用**；
  lock 是「实际装成什么」的**事实源**，范围 pin 是「意图」，冲突时以 lock 复现并把冲突报给 D。
- **不覆写 `requirements.txt`**（脚本里 0928 那条纪律保留）：freeze 只写 `requirements.lock.txt`。

### 决定 2：**pip 版本记进 lock**，且下次运行**装回**那个版本（memo §19-B③ 后半）

- lock 头部记 `# pip==26.2.1`；脚本用 `sed -n 's/^# pip==\([^ ]*\).*/\1/p'` 读回并
  `pip install "pip==$PIP_RECORDED"`，**不再无条件 `-U pip`**。
  理由：pip 版本决定解析器行为，而解析器行为正是本次 `ResolutionImpossible` 的直接触发条件 ——
  只记「装了什么包」而不记「谁解析的」，复现口径是缺了一半。
- **头部是注释，两侧解析器都安全**（B 实测，不是推断）：
  B 的 `b_selfcheck_reproducibility.py` L0-f/L0-g 只匹配 `robosuite==` 开头的行；
  C 的 `c_env_manifest.py::_parse_lock` 显式跳过 `#` 与 `-` 开头的行（实测仍解析出 **28** 条 pin，
  `robosuite 1.5.2 / mink 1.2.0 / numpy 2.4.6`，无注释混入）。
- **补头后复跑可复现性自检：12/12 全过**（含 L0-f `robosuite 实装 == pin`、L0-g `lock == pin`）。
- **现有 lock 的 pin 块逐字节未改**（`diff` 去注释后与备份一致；备份
  `tmp/agentB_inherit_20260929/requirements.lock.before_header.txt`，`tmp/` 不纳版控故此处记事实）。

### 决定 3：lerobot 的安装方式与 pin **摘成独立文档**（memo §19-B④）

新增 `docs/lerobot_env_reinstall_pin_20260929.md`（B 是环境文档责任线），内容 =
权威 pin（**`lerobot==0.4.4`，PyPI 包，aliyun 索引，用 uv 不用 pip**）、两个 venv 的完整版本表与两份 lock 路径、
评测环境 `--override numpy==2.4.6` 的理由、重装命令与三条门槛验证。
**并更正缺口的表述**：`ls /root/venvs/` 实测只剩 `rlrobot` ⇒ 不是「`rlrobot` 里少一个 lerobot 包」
（lerobot 按设计**从不**装在 `rlrobot` 里），而是「**`lerobot_act` / `lerobot_eval` 两个 venv 整体被抹掉**」
⇒ C 的 `probe_modules` 探针要在**那两个解释器**里探，不能在 `rlrobot` 里探。

### 决定 4：**否掉 D 提的候选源** —— 它比 pin 落后 **488 个 commit**（B 只读实测）

D 在 裁定 29.4 里给 A/C 指了一个离线候选源 `/workspace/cache/yhzhang91/zptang/lerobot_0cf8648/lerobot`。
B 实测（**未改他人副本一个字**）：

| 实测项 | 值 |
|---|---|
| 该 checkout HEAD | `0cf864870cf29f4738d3ade893e6fd13fbd7cdb5`（2025-05-28） |
| `git rev-list --left-right --count v0.4.4...HEAD` | **`488  0`** ⇒ 落后 tag `v0.4.4` **488 个 commit**、领先 0 |
| 该 HEAD 的 `pyproject.toml` | `version = "0.1.0"` ⇒ **从它装出来会自报 0.1.0** |
| tag `v0.4.4`（在该 mirror 里存在） | `8fff0fde7c79f23a93d845d1a50e985de01f8b8a`（2026-02-27），其 `pyproject.toml` `version = "0.4.4"` |
| 远端 | `https://gitee.com/mirrors/lerobot.git`（mirror，非上游） |

⇒ 直接用该工作副本装，得到的**不是**「版本略旧」，而是**差 488 个 commit 的另一套 API**，
而 48 臂权威表依赖的正是 0.4.4 的官方 ACT 入口（`lerobot.scripts.lerobot_train`、`normalize_processor.py` 行为）。
**离线回退的正确写法**：在自己的目录里 clone 该 mirror 并 `checkout v0.4.4`，装完仍必须验
`lerobot.__version__ == "0.4.4"`。D 已裁定的另两条照旧：`sqzhang26/gaoyuxuan/lerobot`、
`clzhang25/LIBERO/lerobot` 是他人副本，**不得**当本项目 pin。

**给 C 的探针判据（P0，随 裁定 29.4）**：**只验 `import lerobot` 成功是恒真判据** ——
lerobot 的 `__version__.py` 实测是 `importlib.metadata.version("lerobot")`，源装成 0.1.0 时 import 照样成功。
探针必须验 **`lerobot.__version__ == "0.4.4"`**，并回显**安装来源**（PyPI wheel / 源装 + commit）。

### 决定 5：把 裁定 30 的「分布层」做成机器可核（`b_official_arms_reclassification.py`，**不改门禁**）

- 新增 `summary.controlled_success_histogram`：`all_arms`（48 臂）与 `measurement_valid_arms`（47 臂）
  **两套臂集分开给**，键 = 受控成功局数、值 = 臂数。
- 新增顶层 `distribution_layer_note`，把 裁定 30 的规则钉进产物：
  **计数层构建不变**（v1.4→v1.5 实测 135/235/7/0/0/377 一格未动）、
  **分布层构建相关**（按 `measurement_valid` 的臂集统计，实测无效臂 v1.2.1 = 7 → v1.5 = 1）
  ⇒ 分布类陈述一律带构建指纹 + 写明臂集。
- **实测（本轮表）**：48 臂直方图 `{0:23, 1:9, 2:6, 3:2, 4:1, 9:2, 14:1, 16:1, 17:1, 19:1, 20:1}`；
  measurement_valid 47 臂 `{0:22, …其余相同}` ⇒ **两套臂集的 4–9 区间都是 3 臂**
  （`k2 seed0`=9【裁定 10 免罪臂】、`train120_…k2_seed0`=9、`trimdone0_minmax_lr1e-5_s20k_seed0_replan1`=4）。
  唯一 INVALID 臂（`…k2_lr1e-5_s20k_seed0_replan1`，blown 0.1692）受控成功是 **0**、不落在 4–9
  ⇒ 48 臂口径下 裁定 30 的「0 变 1」不成立（那是 **A 的 21 actlog 子集**的结论，臂集不同）。
  **B 不代算 A 的臂集**（裁定 30 的四个限定之一就是「臂集」），只提供 48 臂的机器可核直方图。
- 为什么值得做：裁定 30 的成因是「手工 join 的结果不会随构建自动更新」。把直方图放进**每次重出都会刷新**的
  权威表里，这类过期就有产物层的抓手，而不是靠人记得去改散文。

### 验收（本轮实测）

| 项 | 实测 |
|---|---|
| `bash -n scripts/setup_env.sh` | 语法 OK |
| lock 头部被两侧解析器忽略 | B 的 L0-f/L0-g **PASS**；C 的 `_parse_lock` 仍 **28** 条 pin、无注释混入 |
| 可复现性自检 | **12/12**（补头后复跑） |
| 权威表数值 | `25/22/1`、`45/2/1`、`47/1`、计数层 135/235/7/0/0（raw 377、分母 960）**逐格不变** |
| 门禁自检（同 build `f19f61341cbe`） | 回归 **157/157 · 39/39**、变异 **15/15**、黄金值 **47/47**、T17 变异 **6/6**、D verifier `--expect exonerated` **exit 0 / ACCEPTANCE=True** |
| D 的新规则「产物 mtime ≥ 脚本 mtime」 | 表 12:21:19 ≥ 脚本 12:21:16 ⇒ **满足**（B 本轮每次改脚本后都重出表） |
| `GATE_BUILD` | 全程 **`f19f61341cbe`** 未动（本轮只改 `configs/`、报表脚本、牙齿脚本、文档、环境脚本，**没碰门禁**） |

---

## DR-013 裁定 31.5 / 裁定 32 的 B 侧落地：v1.6 待办收口、环境责任改判 ack、溯源闸落地、一次写权碰撞的处置

- 时间：2026-09-29 14:0x–14:4x；登记人 B；裁定人 D（裁定 31.2 / 31.5 / 32.1–32.4，DR-D30 / DR-D31）
- 触发：D 的 `supervisor_memo_20260929.md` 增补八（§21–§25）与增补九（§26–§29）；
  用户改判「让 A 自己安装环境」；A 于 13:58–14:11 实跑 installer、14:24 起建自足持久 `rlrobot`。
- B 的写入边界（本条严格遵守）：只写 `scripts/b_*`、`docs/b_*`（含 B 的权威 pin 文档）、
  `configs/b_*`、`requirements.persistent.lock.txt`（**见决定 5 的碰撞处置**）、`runs/infra/b_*`、
  本登记处、`daily_report.md` 追加。**没有**碰 A/C/D 的任何文件，**没有**跑任何安装命令。

### 决定 1 —— 裁定 31.5 的两项**并入 v1.6**，本轮**不改规格文档**（附实测理由）

D 结掉 B 挂着的两项请裁定：① `condN` 命名卫生（裁定 27.5 / P2）**批准并入 v1.6**，附加要求
「v1.6 改名后，`scripts/d_verify_exoneration_cosign.py` 的第三轮复签必须**同时验新旧键名不并存**」；
② 裁定 23.5 的「`terminal_kind` 缺失已被接受 + 理由」声明**判归 B 的 `configs/`**，排期**随 v1.6 一起做**
（D 的理由：现在做等于给未落地的判据建登记）。B 接受两项排期，v1.6 待办自此为**八项**
（裁定 23 的六项 + 这两项），落地时 B 须主动通知 D 跑第三轮复签（DR-009 / DR-010 已登记该义务）。

**B 的一个执行决定（需要 D 知道）**：这两项**本轮不写进规格 §2.18**，只在 DR-013 挂账，
v1.6 kickoff 时与 build 一起并入 §2.18。**理由是实测出来的，不是怕麻烦**：
A 的 `scripts/a_gate_build_drift_check.py::_identity()` 返回的是**三元组**
`(gate_version, gate_build, gate_spec_sha256[:12])`，`--check-single-build` 用它断言目录内单一构建
（`:107`、`:129`、`:217` 三处都读 `gate_spec_sha256`）⇒ **spec 轴一动，新旧产物的三元组混值，
A 的单一构建断言会红**，且 A 权威表 meta 里记的 `gate_spec_sha256=['c7fadabe8e3c']` 会与现值不符。

⇒ **上报 D 的口径不一致（B 不代裁、不代改 A 的文件）**：裁定 29.1 判「引用锚只在 **build 轴**，
spec 轴是观测日志、不是钉子」，但 A 的漂移闸**仍把 spec 轴当断言轴**。两者不能同时成立：
要么 A 的 `_identity()` 收窄到 `(gate_version, gate_build)`（与 裁定 29.1 一致），
要么 裁定 29.1 补一句「spec 轴虽不是**引用**锚，但仍是**单一构建一致性**的断言轴」。
**在 D 裁定之前，B 冻结规格文档**（现值 `c7fadabe8e3c`），因为 B 一改就会在 A 侧制造真红 ——
这与「B 不报假红、也不制造真红」是同一条纪律。

### 决定 2 —— 裁定 32.1 责任改判 ack：B 不再执行安装，只做「权威 pin + 验收」

B 认这个改判（D 的理由成立：安装是**执行**动作，谁用它跑训练谁负责它装对了；给权威 pin 并验收
本来就是 B 已经做完的事）。**裁定 31.5 那条「B 执行安装」的分派自此作废。**
本轮 B 实跑的安装命令数 = **0**；B 做的是：
- 逐个实测 D 对 **B 的文件**所做的断言（「installer 9 个变量全部可覆写，A 不需要改脚本」）⇒ **9/9 成立**
  （`VENV:23`、`BASE_PY:24`、`INDEX:25`、`TORCH:26`、`TORCHVISION:27`、`LEROBOT:28`、`LOCK_OUT:29`、
  `EVAL_VENV:68`、`BUILD_EVAL_ENV:69`，全部 `${VAR:-default}` 形式），明细见 pin 文档 §7.1；
- 只读验收 A 的重建 ⇒ **逐项符合 §2 权威 pin**（`lerobot_act`：lerobot 0.4.4 / torch 2.6.0 /
  torchvision 0.21.0 / numpy 2.2.6 / gymnasium 1.3.0，且 mujoco/robosuite/numba **故意** MISSING；
  `lerobot_eval`：+ numpy 2.4.6 / gymnasium 1.2.3 / mujoco 3.9.0 / robosuite 1.5.2 / numba 0.67.0；
  两个 venv 的 `pyvenv.cfg` 都是 `include-system-site-packages = false`）。
  **`lerobot==0.4.4` 是语义值验证，不是 importable**（裁定 31.2 第 3 条）。
- **A 线是否解封由 D 裁**，B 不代裁、不代宣布。

### 决定 3 —— 裁定 32.2 ack + 一项**无主义务**的显式指派

B 复述并采纳 D 对 `codex-persist mkvenv` 的两处缺陷判定（缺 `--no-deps` ⇒ `ResolutionImpossible`；
硬编码 `--system-site-packages` + 不覆写 index ⇒ 踩中 09-24 `PreTrainedModel` 真根因与 ustc 403），
已写进 pin 文档 §7.2（该文档是 裁定 32.1 认定的唯一权威 pin 来源，A 照抄那里）。
`.codex-persist/bin/codex-persist` 在**项目仓外**、是用户共享基础设施 ⇒ **不在 B 的写入边界，B 不改它**
（D 也已声明不改）。B 实测到 14:2x 它已带 `--clean` / `--find-links` / `venvcheck`，
即 裁定 32.2 建议 3 已有人落地。

**但 裁定 32.2 建议 3 的后半句「README 的『依赖持久化』那节应加一行警告：从 lock 安装必须 `--no-deps`」
目前无主** —— D 明说不由 D 执行，B 的边界不到仓外，A/C 的边界也不到。
**B 在此显式登记：该义务属 11:45 那个 infra 会话 / 用户本人**，一行即可：
> `README.md` 的「依赖持久化」节末尾加：**从 lock 安装必须 `--no-deps`**（`robosuite 1.5.2` 要
> `mink==0.0.5`、本项目 lock 钉 `mink==1.2.0`，解析器判 unsatisfiable；口径见 ADR-C-006 /
> 裁定 29.4 §19-B③：解析器到不了某个组合 ≠ 那个组合不可用）。

登记在这里的目的**不是**推卸，是防止它掉进「四线都以为别人会写」的缝里（本仓今天已出现过一次同型：
裁定 30 的下游后果「没人传播过」）。

### 决定 4 —— 裁定 32.3 / 32.4 落地为机器闸 `scripts/b_env_provenance_guard.py`（新文件，不改 installer）

裁定 32.4 是 P0，但散文纪律拦不住手滑（`installer:29` 的 `LOCK_OUT` 默认值**就是** 0928 目录，
`:57`/`:85` 直接 `pip freeze >` 覆写）⇒ B 把它做成会红的闸。5 条判据 G1–G5、每条都写出**可红条件**
（裁定 27.1「恒假的闸等于没有闸」），`--selftest` **10/10**（含 1 条**反向**变异 M8，
证明修完假红后判据没变成恒绿）。现场判定：两个 venv 各跑一次，均 **PASS 5 / WARN 0 / RED 0**、exit 0。
明细见 pin 文档 §7.3。

**裁定 32.3 前提 1 的选项落盘**：选 **(甲) 自足**，且**已建成 + B 验收通过**
（`.codex-persist/envs/rlrobot`，14:24，6.4 GB，`--system-site-packages=false`，
82 pin 与 freeze 逐 pin 对账全过，`nvidia-*-cu12` 闭包 14 个轮子齐备）。
**(乙) 仍未满足**（把 C manifest 的 `inherited_packages` 从观测改断言属 C 的写入面，B 不代做）。

**裁定 32.4 现场结果**：0928 两份 lock **未被覆写**（sha `68a38731c5b5…` / `b6db07e2e31c…`、
mtime 仍是 0928 原值，与 C 的备份逐字节一致）；A 已把 `LOCK_OUT` 覆写到
`runs/infra/a_lerobot_env_rebuild_20260929/`。新旧差异**只有 3 处**
（`ImageIO 2.37.4→2.38.0` 两份各一处、`uv 0.12.19→0.12.17`），已由 G2 逐包枚举。
**解释义务在 A、须报 D**；B 只保证差异不被吞掉，**不代 A 解释、不代 D 裁定**。

### 决定 5 —— 一次**写权碰撞**的处置：`requirements.persistent.lock.txt`

事实经过（都可核）：
- 14:16 B 建 `requirements.persistent.lock.txt`（111 行 / **36 pin** = 28 项目 pin + 6 原继承 pin +
  2 引导件 pin），头部明写「本文件**不是**可直接 `--no-deps` 安装的自足闭包，闭包必须真解析一次、
  不能手写补全」，并落盘 (甲)/(乙) 的选项声明。
- 14:19:35 D 用 `scripts/d_build_persistent_lock.py`（12014 B，D 的新文件）**覆盖**了它
  ⇒ 现值 97 行 / **82 pin**（28 项目 pin + 54 依赖闭包），头部 `generated_by` / `base_lock` sha /
  `install=` / `verify=` / `excluded=jax,jaxlib` / `known_conflicts` 齐全。

**B 的处置：不回抢、不覆盖回去。** 理由：① D 的版本是**脚本生成**（可复现、带 provenance 头），
B 的是手写整理；② D 的版本**含闭包**，正好补上 B 明写「自己补不了」的那一块；
③ 两个人各写一版会直接违反 裁定 21「判据/资产单一来源化」。
⇒ **B 改为验收 D 的产物**（G3 + `--frozen` 对账，82/82 全过），B 的独有实测
（`+cu124` 的 index 可用性、`pip`/`setuptools` 不是继承包、numpy 遮蔽）全部搬进 pin 文档 §7.3/§7.7 保存。

**提请 D 确认 owner（B 不代裁）**：建议 `requirements.persistent.lock.txt` 的 **owner = D 的生成器**
（`scripts/d_build_persistent_lock.py`，改它须重跑生成器），**验收方 = B 的
`scripts/b_env_provenance_guard.py --frozen`**。这样「谁生成、谁验收」分开，
B 的闸就是 D 产物的独立第二双眼睛 —— 与本仓一直在用的「事实层 / 通道层分开验」同构。
**在 D 确认之前，B 不再写这个文件。**

### 决定 6 —— B 自查出的一处假红（G3 的 freeze 对账）+ 两条实测发现

1. **假红**：G3 第一版报「freeze 里缺 8 个 pin」，把一次**完全合格**的自足 venv 判成 RED。
   两个根因都在 B 的工具：① 没做 **PEP 503 名字归一化**（freeze 写 `ImageIO`/`Jinja2`/`PyYAML`/
   `typing_extensions`/`Werkzeug`/`Pygments`，lock 写小写/连字符）；② **`pip freeze` 默认不输出
   `pip`/`setuptools`**（要 `--all`），它们属**不可比**而非缺失。
   修法：`norm_name()` + `FREEZE_EXEMPT` 三值单列（可见不报警，与护栏① 的 `cosign_not_required_arms`
   同型）。**并加反向变异 M8（期望 NOT_RED）+ M9（期望 RED）一对**，防止「修假红」变成「造恒绿」。
   这是本仓今天第 **6** 起同型（DR-003 判据 3 恒真、D 第五次/第八次自我纠错、裁定 23 的 `note` 恒空、
   裁定 29.3 的「文档自述已落地」、DR-011 的三值桶、本条）。
2. **`importlib.metadata.version("torch")` 分辨不出 CUDA 构建**：实测 `lerobot_act`/`lerobot_eval`
   metadata 报 `2.6.0`（无 local tag）而 `torch.__version__` = `2.6.0+cu124`、`torch.version.cuda` = `12.4`；
   base 的 conda torch metadata 报 `2.4.1+cu124`（带 tag）。⇒ **只断言 metadata 版本号的探针，
   对 cu121 构建也会通过** —— 这是 裁定 31.2 第 3 条「验语义值不是验可导入」再深一层：
   **版本字符串本身也可能是恒真判据**。已要求 C 的探针断言 `torch.version.cuda == "12.4"`。
3. **`+cu124` 何时必须写、何时不能写**（实测两个 index）：aliyun 的 `pypi/simple/torch/` **没有**
   `2.4.1+cu124`（只有 PyPI 默认 `2.4.1` = cu121），`download.pytorch.org/whl/cu124/torch/` **有**；
   而 `torch 2.6.0` 的 PyPI 默认构建**本身就是 cu124**（A 用 aliyun + `torch==2.6.0` 装出来
   `torch.version.cuda=12.4` 即证）。⇒ **`2.4.1` 必须写 `+cu124` 并另给 cu124 源；`2.6.0` 不用写**。
   搞反的两种失败都难看：写多了装不上，写少了**静默装到 cu121**（版本字符串一样、构建不同）。
4. **顺带更正 C manifest 的一处分类不精确（B 不改 C 的文件，只登记 + 告知）**：
   `runs/infra/c_env_manifest_20260929.json` 的 `inherited_packages.versions` 把 8 个包一并列为「继承自 base」，
   实测其中 **6 个确为继承**（`torch`/`torchvision`/`scipy`/`pandas`/`pyarrow`/`matplotlib`，
   `dist-info` 路径全在 `/opt/conda/lib/python3.11/site-packages/`），
   而 **`pip==26.2.1` / `setuptools==65.5.0` 是 venv 自带**（dist-info 在
   `/root/venvs/rlrobot/lib/python3.11/site-packages/`；base 里是 `pip 24.2` / `setuptools 73.0.1`，
   **版本不同**）。数值没错，错的是「来源」标签。影响：裁定 32.3 前提 1(乙) 若只对 `inherited_packages`
   做断言，会漏掉「venv 引导件版本由 base 的 `ensurepip` 决定」这条链。

### 验收（本轮实测）

| 项 | 实测 |
|---|---|
| `b_env_provenance_guard.py --selftest` | **10/10**（baseline 全绿 + M1–M7/M9 全抓住 + M8 未误报） |
| 现场判定（`/root/venvs/rlrobot`） | **PASS 5 / WARN 0 / RED 0**，exit 0 |
| 现场判定（持久 `.codex-persist/envs/rlrobot`） | **PASS 5 / WARN 0 / RED 0**，exit 0 |
| freeze 对账（82 pin vs A 的持久 venv） | **0 版本不符 / 0 真缺失**，`not_comparable_freeze_excludes=['pip','setuptools']` |
| 0928 溯源件 | sha 与 mtime 均为 0928 原值，与 C 的备份逐字节一致 ⇒ **未被覆写** |
| A 的重建 vs §2 权威 pin | **逐项符合**（含训练环境**故意**不装 robosuite 这条） |
| 门禁本体 | **一字节未动**，`GATE_BUILD` 全程 `f19f61341cbe`、spec 全程 `c7fadabe8e3c`（决定 1 的冻结） |
| 安装命令 | B 实跑 **0** 条（裁定 32.1 改判后 B 不再执行安装） |
| AGENTS.md 纪律 | 脚本内无 `rm`/`rmtree`/`unlink`；自检临时目录 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/` |

---

## DR-014 D→B 执行单（0929 14:5x）P0-1…P0-6 的 B 侧落地：门禁不变性闸、freeze 覆写护栏、persistent lock 身份登记、installer 钉版本**改判**、行号锚→内容锚、T17 A 侧翻绿

- 时间：2026-09-29 15:0x–15:5x；登记人 B；派活人 D（`rl_harness_supervision/d_handoff_to_b_20260929.md`，依据裁定 33 / 34）
- 触发：用户指令「当前 A 正在重装环境，你这边直接按约定把之前遗留任务跑完，注意任务边界」
- **解释器（表述纪律 D §8.7）**：`/root/venvs/rlrobot/bin/python`；`realpath(sys.executable)` = `/opt/conda/bin/python3.11`
  （venv 的 `bin/python` 本身软链到 base），`realpath(sys.prefix)` =
  `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/envs/rlrobot`，**经软链**（14:35 由 D 切换），
  **clean venv**（`include-system-site-packages = false`，`version = 3.11.9`），生效 `numpy 2.4.6` /
  `torch 2.4.1+cu124`（`torch.version.cuda = 12.4`）。留证：`runs/infra/b_env_migration_invariance_20260929/interpreter.txt`。
- **B 的写入边界（本条严格遵守）**：`scripts/b_*`、`scripts/install_lerobot_act_env.sh`、`scripts/setup_env.sh`
  （裁定 32.1 / D §2、§4 明归 B）、`docs/b_*`、本登记处、`daily_report.md` 追加、git 写命令（DR-003 决定 8）。
  **没有**碰 A/C/D 的任何文件；**没有**跑任何安装命令；A 的产物**一份未覆写**（见决定 6 的重定向手法）。

### 决定 1 —— P0-1：把「环境换了但结论没变」做成**机器闸**，不是一句「我验过了」

新增 `scripts/b_env_migration_invariance_check.py`（stdlib，无 `rm`）。它读 D §1 那批产物，
把 D 的判定逐条落成 V0–V9 十个断言，并与 **12:2x 迁移前基线**逐项对齐；`--selftest` 9 条变异（含 1 条反向）。

**实测结论（可核形式，D §1 要求的措辞）**：
> 在 `realpath(prefix)=/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/envs/rlrobot`
> （经软链 `/root/venvs/rlrobot`）、`include-system-site-packages=false`、`numpy=2.4.6` / `torch=2.4.1+cu124`
> 生效的解释器上，5 套自检通过数与迁移前基线**逐项相同**（12 / 157·39 / 15-15 / 47 / 6-6），
> 重判 **16** 份裁定记录**变化 0 处**，权威表 `gate_version`/`gate_build`/`summary` 三键与 12:21 那份**逐格相同**，
> 构建仍为 **`v1.5 / f19f61341cbe`**。

| 判据 | 实测 |
|---|---|
| V1 可复现性 | 12 项全过（`--repeats 2`，`MUJOCO_GL=egl`），rc=0 |
| V2 门禁回归 | **157/157** 断言、**39/39** 用例，rc=0 |
| V3 门禁变异 | **15/15** 被抓住，`baseline_all_green=True`，rc=0 |
| V4 黄金值 | **47/47**，rc=0（**只读日志**，理由见下） |
| V5 T17 变异 | **6/6**，rc=0 |
| V6 重判 | 裁定变化 **0 处**、`regression_ok=True`、`comparison_vacuous_sets=[]`（比对臂集**非空**，16 臂） |
| V7 构建指纹 | 4 份携带指纹的产物全部 `v1.5 / f19f61341cbe` |
| V8 权威表 | 三键 SAME；`25/22/1`、`45/2/1`、争议带 `1`、`n_artifacts=48`、计数层 `insuff=235` |
| V9 落地 | 六份产物 mtime 均 ≥ 对应脚本 mtime，`stale_or_missing=0` |
| `--selftest` | **9/9**（M1–M7 全红、M8 反向仍绿 ⇒ 非恒红） |

产物：`runs/infra/b_env_migration_invariance_20260929/`（`invariance_verdict.json` + 6 份 JSON + 6 份日志
+ `interpreter.txt` + `COMMANDS.md`）。**未覆盖 12:2x 的留档**（D §1 的要求）。

**附带确认（防误读，D 只看产物时需要这条）**：`b_regate_all.py` 只回写**门禁报告**
（`runs/infra/b_normclip/gate_v12.json`、`runs/infra/b_normclip2/gate_all.json`，且回写前先 `shutil.copy2` 留快照）。
**被判的评测产物一份未动**（`clip*.json` / `noclip.json` 的 mtime 仍是 09-28 16:4x–16:5x）
⇒ sha256 未变 ⇒ `configs/b_blown_impl_grandfathered.json` 的存量豁免仍逐条命中；
`runs/infra/lerobot_act_env_20260928/gate_*.json` 47 份本轮**全部未被改写**（A 的写入范围）。

**报 D 的一条命令缺陷（不是环境问题）**：D §1 写的
`b_selfcheck_golden_values.py --json "$OUT/golden_values.json"` 跑出来是
`FileNotFoundError` + `rc=1`。实测 `scripts/b_selfcheck_golden_values.py:35` 的 `--json` 是**输入**
（`DEFAULT = docs/b_golden/async_td_golden_v1.json`），`:41` 立刻 `json.loads(Path(a.json).read_text())`，
全脚本**不写任何文件**（`json.dumps` 只用于拼报错消息）。⇒ 正确用法是不带 `--json`、把 stdout 留成日志；
**这一项没有 JSON 产物**，D §8.1「只看产物」对它是例外，证据是 `golden_values.log`。详见 `COMMANDS.md`。

### 决定 2 —— P0-2：`setup_env.sh` 的 freeze 覆写护栏采 **(a)+(c)**，**不**采 (b)，且**不**写 persistent lock

按 D §2 的倾向落地，但两处**主动偏离**，理由都是可核的：

1. **不选「改写到 `requirements.persistent.lock.txt`」那条分支**，改为 `exit 1` + 打印该怎么办。
   理由：那份文件的生成器是 `scripts/d_build_persistent_lock.py`（**D 所有**，依赖闭包 BFS、82 pin），
   `setup_env.sh` 再写一份就是**第二个写者** —— 0929 14:19 B 已经吃过一次这个碰撞（DR-013 决定 5）。
   裁定 21 的单一来源优先于 D §2 括号里的备选写法。
2. **不采 (b) 数量闸**（freeze 行数 != 28 就拒绝）。理由：它会在**合法重新 pin** 时也拒绝，
   于是必须再开一个 `--allow-lock-rewrite` 开关 ⇒「什么时候可以改事实源」变成两个判据；
   而 (a) 已经覆盖了实际观察到的那条风险路径（`VENV=` 指向自足 venv）。要加 (b) 请先报 D。

护栏放在**最前面**（早于建 venv、早于任何 `pip install`），因为自足 venv 在 NFS 上建成后按**只读**对待
（D §9：两个容器同时写会写坏它）⇒ 不止不能覆写 lock，连往里装包都不该发生。
判定只看**可核事实**（`pyvenv.cfg` 的 `include-system-site-packages`、`bin/python` 是否存在），
不看调用者的意图声明 —— 否则护栏退化成一句注释。读不到该键 ⇒ **按不可确认拒绝**，不当作继承 venv 放行。

| 项 | 实测 |
|---|---|
| `bash scripts/setup_env.sh --guard-selftest` | **7/7**（自足→拒、继承→放、读不到键→拒、有 `bin/python` 无 `pyvenv.cfg`→拒、venv 不存在→放、备份逐字节相同且文件名带 sha12、旧 lock 不存在时**不凭空造备份**） |
| **实弹**（`VENV=/root/venvs/rlrobot` 真实的自足 venv） | **rc=1 拒绝**；`requirements.lock.txt` 的 `sha256_12` 仍是 **`d1ea71b7b4e5`**、**mtime 一字节未变**（D §8.2 的两条都满足） |
| (c) 事前备份目录 | `runs/infra/b_lock_history/`（`cp -p`，文件名 `requirements.lock.txt.<sha12>.txt`；**禁 rm**） |
| 实弹日志 | `runs/infra/b_freeze_guard/live_refuse.log`（含兜底备份 `requirements.lock.pretest.txt`） |

**顺带（D §2 末条）**：`requirements-inherited.json` 的语义已按 **venv 类型分别解释**写进脚本注释
（继承 venv = 「从 base 继承了什么」；自足 venv = 「venv 内自带了什么」，此时 `jax`/`tensorflow`
记 `NOT INSTALLED` 是**设计意图**，不是采集失败）。已写进 B→C 交接单（C 的 `inherited_packages` 同此口径）。

### 决定 3 —— P0-3：persistent lock 身份登记 + 专用闸；**不挂 L0 系列**（附偏离理由）

新增 `scripts/b_selfcheck_persistent_lock.py`。D §3 的身份表逐条落地为**缺省期望值**（要改必须显式传
`--expect-*` 并在本登记处追加一条，**不许就地放宽缺省值**）：

| 项 | 实测（与 D §3 的表逐格对上） |
|---|---|
| 文件 | `requirements.persistent.lock.txt`，**82 pin**，`sha256_12 = 69d61657f531` |
| 生成器 / owner | `scripts/d_build_persistent_lock.py`（**D 所有**）；**验收闸 = B（本脚本）** |
| 与 28 pin lock 的关系 | 头部 `# base_lock=requirements.lock.txt sha256_12=d1ea71b7b4e5`；闭包新增 **54** pin（82−28） |
| **不是**什么 | **不是门禁产物**、不参与 `GATE_BUILD`、**不被** `c_env_manifest.py::_parse_lock` 读取 |
| 已知冲突 | `robosuite 1.5.2 -> mink==0.0.5`（实装 `mink==1.2.0`，按裁定 32.2「lock 是事实源」记录不改） |
| 排除项 / 补钉 | `jax`/`jaxlib` 排除；`h5py==3.14.0` 等价性补钉 |
| `+cu124` | `torch==2.4.1+cu124`、`torchvision==0.19.1+cu124` |

**为什么不挂 L0 系列（D §3 的建议）**：D §8.1 要求五套自检的通过数与 12:2x **逐项相同**（可复现性 **12/12**）。
往 L0 加三条牙会把它变成 **15/15** ⇒ 同一份执行单里，§3 的落地方式会**推翻 §8.1 的判据**，
D 独立复核时会看到一个无法解释的 +3。做成独立脚本两个要求都能满足：L0 仍 12/12（决定 1 的不变性证明可被原样复核），
persistent lock 有自己的闸和自己的 `--selftest`。另一条支持理由：D §3 明确它**不是门禁产物**，
把它的检查塞进门禁前的 L0 系列，反而会让这句话在代码层面不成立。

**牙（D §3 要求「三条牙各红一次」，实测 9/9）**（**16:0x 已被 决定 11 取代 ⇒ 现为 12/12，新增 K6 三条牙**）：K1 头部 sha 改一位→红；K2 删一个 base pin→红、
改共有 pin 版本→红；K3 去掉 `torch`/`torchvision` 的 `+cu124`→各红一次；K5 篡改 28 pin 门禁 lock→K1+K5 双红。
**两条反向变异**：只改发行名大小写（`imageio`→`ImageIO`）、只倒转 pin 行序 ⇒ K1/K2/K3 **必须仍绿**
（PEP 503 归一化 + 无序比对；这正是 DR-013 决定 6 那起假红的形状，钉住防回归）。
selftest 的判定口径是「**指定条目**必须红 / 必须绿」，不是「有没有红」—— 否则 S1–S5 会被 K4（身份 sha 变了）
碰巧带红而误判成通过。产物：`runs/infra/b_persistent_lock/report.json`。

### 决定 4 —— P0-4：installer 钉版本按裁定 34.1 **改判**，推翻 B 自己 14:1x 写的 `2.37.4`

B 在 14:1x 把 `IMAGEIO` 钉成 **0928 的值 `2.37.4`**（当时的理由是「要复现的是 0928」）。
**裁定 34.1 第 4 条改判了这个口径**：钉「**实际装成并跑通门槛验证**」的那个值（裁定 32.2「lock 是事实源、
范围 pin 是意图」同型），**不回退**到 0928 的值 —— 回退等于按意图改事实，而且要重装只读 venv（第 3 条已否决重装）。

| 变量 | 改判后 | 事实源（实测） |
|---|---|---|
| `IMAGEIO` | **`2.38.0`**（原写 `2.37.4`，已改） | A 的 0929 重建两份 lock 实测 `ImageIO==2.38.0`（`runs/infra/a_lerobot_env_rebuild_20260929/requirements.lock.txt:35`、`requirements.eval.lock.txt:38`）；0928 基线是 `2.37.4`；B 实测 aliyun `pypi/simple/imageio/` 上 `2.38.0` **在**（wheel + sdist 各 1）；lerobot 0.4.4 声明 `imageio[ffmpeg]>=2.34.0,<3.0.0` ⇒ 合规 |
| `UV` | **`0.12.17`**（B 14:1x 的值，与裁定一致，未改） | A 的 0929 重建实测 `uv==0.12.17`（同上 `requirements.lock.txt:102`，仅 act 侧有）；B 实测 aliyun 的 uv 索引 316 个版本里 `0.12.17` 在、`0.12.18/0.12.19/0.12.20` **都不在** ⇒ 钉 0928 的 `0.12.19` 会让下次重建**直接装不上** |

注释里写明了 D §4 要的根因：**镜像内容会动 ⇒ 未钉版本 = 每次重建都漂移**；`uv` 虽是安装期工具
（A 实测全仓无 `import uv`），但它**进了 lock** ⇒「用什么工具装的」这个事实也属可复现性，照样钉，
不按「工具不重要」豁免。`uv==0.12.19` 在权威 index 不可复现一事**已报并由裁定 34.1 结案**，B 不再重复报。
**裁定 37.3 的边界（引用 34.1 必须带）**：豁免只覆盖**本仓链路**（8 个脚本运行时 `hit=[]`，A 静态 grep /
C 运行时 / D 复核三方一致）；**上游 `lerobot.scripts.lerobot_train` 的 import 闭包里确有 imageio（18 个子模块）
⇒ 凡用上游 `lerobot_train` 实跑的训练/评测不在豁免内**，要么另证不材料、要么重新报 D，
且**今后真跑须回显 imageio 生效版本**（见 决定 12）。
`bash -n` 通过；按裁定 34.1 第 3 条**不需要重装**，下次重建由 G2 的逐包枚举确认差异 0 处
（注意 G2 对空比对会 WARN，那条 WARN 是防误读、不是失败）。
**顺带自我修正**：本轮新写的注释里 B 一开始又用了行号锚（`:96`/`:53`），而 B 自己的编辑就让它们移位了
⇒ 已改成内容锚并注明「本文件一改行号就移」。这与决定 5 是同一条教训，B 自己先犯了一次。

### 决定 5 —— P0-5：行号锚 → **内容锚**（D §5 / §8.5「至少三处」），冻结门禁那处**不修**、登记 v1.6

新增 `scripts/b_source_anchor.py`（规范化 = 去掉**全部**空白，所以 `std = x.std(0) + 1e-6`（注释写法）
能对上 `std=x.std(0)+1e-6`（分号连写的实际代码））与 `scripts/b_selfcheck_source_anchors.py`（登记册 + 闸）。

| 条目 | kind | 内容锚 → 回显命中行号 | 与 A 报的是否一致 |
|---|---|---|---|
| A1 | content | `std = x.std(0) + 1e-6` → `scripts/train_act_lift.py:156` | ✅（旧锚 `:44`，HEAD 里本来是 `:36`） |
| A2 | content | `def __init__(self, obs_dim, chunk=4, *, goals=None)` → `scripts/train_act_lift.py:14` | ✅（行号未动，**签名变了**） |
| A3 | content | `nn.Linear(self.obs_dim+self.goal_dim,256)` → `scripts/train_act_lift.py:26` | 新增（「逐层一致」的**结构**锚） |
| A4 | content | `'epoch':epoch,'goal_id':goal_id` → `scripts/run_act_lift_runtime_failure_audit.py:73,76`（**2** 处） | ✅（旧锚 `:36,39`） |
| A5 | content | `'goal_id':'lift'` → **0 命中**（反向断言：写死的 goal_id 一处不剩） | ✅ 语义变的证据 |
| **F1** | **frozen** | `scripts/train_act_lift.py:44` → `scripts/b_gate_controlled_success.py:961` | **不能改** |
| H1/H2 | historical | `scripts/train_act_lift.py:36` → `docs/b_normalization_incident_20260928.md:128`、`docs/b_handoff_to_a_20260928.md:23` | 按 A/D 的意见**留档不追改** |

**F1 为什么不修**：`b_gate_controlled_success.py` 是冻结的门禁本体，`GATE_BUILD = sha12(自身)`，
改一个字节（**连注释都算**）就变 ⇒ D 要跑第三轮复签、A 要重出权威表。所以本闸**反过来**断言
「陈旧锚仍在 `:961`、且门禁 sha12 仍是 `f19f61341cbe`」：谁「顺手修好」了冻结文件就必须红。
**登记为 v1.6 待修项**（v1.6 自此 **9** 项 = 裁定 23 六项 + `condN` 改名 + `terminal_kind` 溯源登记归 `configs/`
+ 本条锚点）。H1/H2 同理：断言留档里的 `:36` **没被人「好心」改成 `:156`** —— 改写历史留档会让 0928 事故的时间线不可核。

闸实测 **8 PASS / 0 FAIL**（content 5 条 + frozen 1 + historical 2），`--selftest` **8/8**
（M1 期望命中数写错、M2 锚文本不存在、M3 反向断言被反转、M4 引用方侧断言不是摆设、
M5 冻结条目陈旧锚不在原处、M6 历史留档被改写 ⇒ 六条必须红；M7 **反向**：只改 `why` 说明字段 ⇒ 必须仍绿）。
产物：`runs/infra/b_source_anchors/report.json`。

**引用方侧也有牙**（防「修完又回退」）：A1 断言 `b_eval_act_lift_v1.py` 里**不再**出现 `train_act_lift.py:44`；
A2 断言 `b_probe_dz_identifiability.py` 里带上了上游新签名；A4 断言 `b_selfcheck_goal_conditioning_t17.py`
里**不再**出现 `run_act_lift_runtime_failure_audit.py:36,39`。

### 决定 6 —— T17 A 侧 2 项翻 `closed_verified`：**双通道**判据，不读 A 的自评 verdict

采 A 交接单 §4 的建议方案 (1)（子进程实测），但**加了一条 A 没要求的独立通道**，理由是不能让
「A 说自己绿了」成为唯一判据（A 自己在 §4 里也反对这种自证形态）：

- **通道 1（语义）**：子进程真调 `scripts/a_selfcheck_goal_conditioning_t17.py`，
  读产物里的**原始断言行** `checks[].id/.ok` 逐条点名（`G9` 证 audit 侧；`G2/G5/G6/G8` 证 policy 侧），
  **不**拿 `summary`/`verdict` 当结论；另要求 `rc==0`、`fail==0`、**`skip==0`（SKIP ≠ PASS）**、
  `teeth.non_vacuous is True`。实测：rc=0、`{"pass": 9, "fail": 0, "skip": 0, "total": 9}`、抓住变异 **5/5**。
- **通道 2（B 自己的内容锚，不经 A 的脚本）**：A4 命中 **2** 处、A5 命中 **0** 处、
  A2/A3 各命中 1 处 ⇒ goal 不只进了签名，也真进了第一层输入维度。
- **两条通道都绿才 `closed_verified`**；任一异常降级 `unprobed`（既不冒充闭合也不冒充开放）。
- **不覆写 A 的产物**：A 的脚本是 `outp = ROOT / a.json_out`，传**绝对路径**即落到 B 指的临时目录
  （实测 `/tmp/b_t17_aside_*/`）⇒ A 的 `runs/infra/a_t17_goal_conditioning.json` 未被 B 触碰。
  实测发现该文件 mtime 在 15:23:41 变过一次，查 `interpreter` 字段是 `/root/venvs/lerobot_eval/bin/python`
  （torch `2.6.0+cu124`）⇒ 是 **A 自己**（活进程）重跑的，不是 B。**顺带一条正向发现**：
  A 侧 T17 在 `lerobot_eval`（torch 2.6.0+cu124）与 B 的 `rlrobot`（torch 2.4.1+cu124）
  **两个解释器上都 9/0/0**，已把 `probe_interpreter` / `a_report_interpreter` / `a_report_torch` 写进产物。

**期望值按语义整体改写**（D §5 / §8.5「不是只改行号」）：两条 `change` 都写成
「**旧期望值（已作废）** … **现期望值（0929 起）** …」，提成模块级常量 `AUDIT_EXPECTATION` /
`POLICY_EXPECTATION`。旧期望值**一并留档**，免得下次有人拿旧口径去验新实现（那会验出一个假的「已闭合」）。

**T17 现状（实测）**：真贯通清单 **7 项 ⇒ 已闭合 6 / 仍开放 0 / 未实测 0 / 探针失败 0 ⇒ 当前阻塞 0 项**
（原为「阻塞 2 项，都在 A 侧」）。`b_selfcheck_t17_mutation.py` 复跑仍 **6/6**。
**仍然不主张**的东西（照 A §5 抄一遍，免得被误引）：不主张已学出 A↔B 方向差异 ——
真帧 teacher 只做 A→B，`lift_B_to_A` 组如实记 `n_rows=0`；要真贯通 T17 还需 B→A 的演示源。
产物：`runs/infra/b_t17/t17_precheck.json`（含 `a_side_probe` 全量字段）。

### 决定 7 —— B 自查出的**第 7 起**同型假红：不变性闸把自己的分母写错

`b_env_migration_invariance_check.py` 的 V7 第一版把**不携带** `gate_build` 的两份产物
（`reproducibility.json` 是环境层自检、`t17_mutation.json` 是 meta 自检）也算进了比对分母，
于是 `None != "f19f61341cbe"` ⇒ 判 RED「构建指纹不一致」。**实际四份携带指纹的产物全部是 `f19f61341cbe`**，
门禁根本没动。根因与 DR-003 判据 3 的恒真、DR-011 的三值桶、DR-013 决定 6 的 PEP 503 同型：
**自检的分母/口径写错，比没有自检更危险**（它会让「构建未动」这条最重要的不变量变成天天喊狼来了）。
修法：只把**带这两个键**的产物纳入比对，并把「携带份数 == 4」本身也断言
（将来某份产物**不再**携带指纹时不会被静默忽略）。这是本仓今天第 **7** 起同型。

### 决定 8 —— B 自查出的**第 8 起**同型假红：`b_env_provenance_guard.py` G5 的期望值**口径错**（与 B 自己的权威 pin 表打架）

现场复跑 `--venv /root/venvs/lerobot_act` 时 G5 报 RED：「生效 numpy==2.2.6（期望 2.4.6）」。
**那不是环境缺陷，是 B 的期望值写错了**：

- 0928 基线 lock 里 act 侧就是 `numpy==2.2.6`（`runs/infra/lerobot_act_env_20260928/requirements.lock.txt:49`），
  eval 侧才是 `2.4.6`（`requirements.eval.lock.txt:57`，installer 的评测环境段带 `--override numpy==2.4.6`）；
- A 的 0929 重建两份 lock 同样是 `2.2.6` / `2.4.6`；
- **B 自己的权威 pin 文档 §2 早就写对了**（训练 venv「**numpy 2.2.6**」、评测 venv「**numpy 2.4.6**」）。
  ⇒ 是 G5 的**代码**与 B 自己那份表不一致：`NUMPY_EXPECT_EFFECTIVE = "2.4.6"` 是按 rlrobot/门禁 venv
  写死的单值，而 `--venv` 是可指的。**一个可指目标、却不可指期望值的闸，就是假红发生器。**

修法（不放宽判据，只把期望值接到事实源上）：新增 `NUMPY_EXPECT_BY_VENV_LOCK`
（`lerobot_act → requirements.lock.txt`、`lerobot_eval → requirements.eval.lock.txt`）与
`expected_effective_numpy(ctx)`，优先级 `--expect-numpy` 显式指定 > 按 venv 名从对应 0928 lock **推导** >
项目口径常量；**推导失败必须在 `expect_source` 里响亮写明**，不静默退回常量假装通过。

| venv | 期望值 | 实测生效 | `expect_source` |
|---|---|---|---|
| `lerobot_act` | **2.2.6** | 2.2.6 | 推导自 `runs/infra/lerobot_act_env_20260928/requirements.lock.txt` 的 numpy pin |
| `lerobot_eval` | **2.4.6** | 2.4.6 | 推导自 `.../requirements.eval.lock.txt` 的 numpy pin |
| `rlrobot` | **2.4.6** | 2.4.6 | 项目口径常量（不在按-lock-推导表里 ⇒ 用门禁 venv 口径） |

**并把这起假红钉成回归牙**（否则下次又会被人「修」成写死常量）：`--selftest` 从 10 条加到 **12 条**，
新增 **M10（反向，期望 NOT_RED）**：act venv 生效 numpy==2.2.6、act lock 的 pin 也是 2.2.6 ⇒
不得再拿项目口径 2.4.6 误报；**M11（期望 RED）**：同一个 act venv 但生效值退回 base 的 `1.26.4` ⇒
仍必须红 ⇒ 证明「按 venv 推导」**不等于**放宽判据。实测 **12/12**，三个 venv 现场各 **PASS 5 / WARN 0 / RED 0**。
产物：`runs/infra/b_env_provenance/guard_{lerobot_act,lerobot_eval,rlrobot}.json`。这是本仓今天第 **8** 起同型。

### 决定 9 —— 一项**须 D 追认的显式例外**：`b_eval_act_lift_v1.py` 改了 note 但**故意不重跑**

D 的落地规矩是「产物 mtime ≥ 脚本 mtime 才算落地」。本轮 A1 那处锚点在
`scripts/b_eval_act_lift_v1.py` 的 `input_constraints.note` 里，改完**没有**重跑评测，理由是可核的两条硬约束：

1. 重跑会产生**新产物**，其 mtime > `LOCK_CUTOFF_MTIME` ⇒ `scripts/b_blown_impl_registry.py:126-130`
   **拒绝登记**（「这是新产物，必须用带 ADR-A-001 补丁的评测器重跑，不能靠豁免册放行」）；
2. note 文本变了 ⇒ 产物 sha256 变 ⇒ `configs/b_blown_impl_grandfathered.json`（按**整文件 sha256** 登记）
   的存量豁免**全部失配**，冻结门禁会在下一轮判红。

所以这一处是**源改、产物不重生成**：修正只对**下一次**（带 ADR-A-001 补丁的）评测生效。
`b_env_migration_invariance_check.py` 的 V9 落地校验**不含**这个脚本（它只覆盖 D §1 那 6 个），
所以不变性证明不受影响；本轮也**没有任何自动自检**对评测产物做 mtime 校验（B 实测
`b_selfcheck_*.py` / `b_gate_controlled_success.py` 全无 `st_mtime`）。**请 D 追认这一条例外**，
或指定「v1.6 落地时连同 ADR-A-001 一起重跑 48 臂」为替代方案。

### 决定 10 —— 冻结口径与固定口径（本轮**未变**，逐条复核过）

`GATE_VERSION/GATE_BUILD` 全程 **`v1.5 / f19f61341cbe`**（`GATE_BUILD = sha12(gate 自身)`，
本轮**未改门禁一个字节**）；规格 `docs/b_controlled_success_v1_20260928.md` 全程 **`c7fadabe8e3c`**（未改）。
分布层数字仍按裁定 30 的纪律引用（**带构建指纹 + 臂集**）：`v1.5 / f19f61341cbe`、48 臂、
`25/22/1`、`45/2/1`、争议带 `1`、计数层 `135/235/7/0/0`（raw 377 / 分母 960）。
**A 线是否解封由 D 裁，B 不代宣布**（DR-013 决定 2 的边界不变）。

### 决定 11 —— K6 落地（裁定 37.4-3）+ B 自查出的**第 9 起**同型缺陷：牙自检自身崩，「有牙」一度不可核

**背景（裁定 37.4-3）**：判据产物里的每一句散文，要么由观测生成、要么显式标注为历史说明并挂指针。
决定 3 的身份表里有一行散文断言「**不被** `c_env_manifest.py::_parse_lock` 读取」——它当时是 B 手工 grep 得出的，
**不由观测生成** ⇒ 按裁定 37.4-3 必须变成机器可核。已加 **K6**（`scripts/b_selfcheck_persistent_lock.py`）：

| K6 子条 | 观测对象（只读） | 判红的条件 |
|---|---|---|
| K6-a | `scripts/b_gate_controlled_success.py`（门禁本体） | 正文出现 `requirements.persistent.lock.txt` ⇒ 它进了 `GATE_BUILD` 的输入，与「不是门禁产物」矛盾 |
| K6-b | `scripts/c_env_manifest.py`（C 所有） | **`_parse_lock(` 的调用行**里出现该文件名 ⇒ 真的被解析 |
| K6-c | persistent lock 自身头部 | `# base_lock=… sha256_12=…` 自述行缺失 |

**为什么不按「出现即违规」判**：C 的文件里本来就有一处**散文引用**（authority 出处说明，解释 28 pin lock 的
来源），它**不解析** persistent lock。按「文件名出现即红」判就是**假红**——这正是决定 6 / 决定 8 那两起的同型
（判据把「提到」当成「使用」）。所以 K6 只认**调用行**，散文引用显式豁免，并用**反向变异 S10** 钉住：
只有散文引用时 K6 **必须仍绿**。

**第 9 起同型缺陷（B 自查，主动报备）**：加 K6 时 B 把新条目 S9/S10/S11 写成了
`(mid, fn, must_red, must_green, reregister, kw_fn, why)`，而 selftest 的解包是
`entry[:6] → (…, why)`、`entry[6] → extra_kw`；**S0 也早已把 `why` 写成了 `None` 占位、真 why 落在第 7 位**。
于是 `extra_kw` 拿到字符串 ⇒ `--selftest` 直接 `TypeError: 'str' object is not callable` 崩掉。
**性质比假红更坏**：真文件那 7 条仍全 PASS，所以闸**看起来是好的**，但「本闸有牙（`teeth.non_vacuous=True`）」
这句话在那段时间里**没有任何可核证据支撑**——牙自检根本跑不完。修法是形状对齐 + **加形状牙**：
条目只允许 6 元 `(…, why)` 或 7 元 `(…, why, kw_fn)`，第 7 位必须 `callable`、第 6 位必须是非空 `str`，
否则 `AssertionError` 并报出条目 id（下次写错会**指名道姓地崩在解包处**，不是崩在一句看不出来源的 `TypeError`）。
修完 `--selftest` **12/12**（S0–S11），真文件 **7 PASS / 0 FAIL**，产物 mtime 16:05:49 ≥ 脚本 mtime 16:05:33。

**一般规则（与前 8 起合并表述）**：**声称一个闸「有牙」之前，必须先证明它的牙自检能跑完**。
`teeth.non_vacuous=True` 是**结论**不是**证据**；证据是 `--selftest` 的逐条 pass 行 + rc=0。

### 决定 12 —— 裁定 37.3 的边界一句**已传播到 B 侧所有引用 裁定 34.1 的位置**

裁定 37.3 把 裁定 34.1 的豁免**收窄一句**：豁免覆盖**本仓链路**，
**凡用上游 `lerobot.scripts.lerobot_train` 实跑的训练/评测不在豁免内**（要么另证不材料，要么重新报 D），
且**引用时必须带这条边界**。B 侧原来有三处引用 34.1 都**没带**边界，已逐处补：
`docs/lerobot_env_reinstall_pin_20260929.md` §7.8、`scripts/install_lerobot_act_env.sh` 的 `IMAGEIO` 注释块、
本文件 决定 4。三处措辞一致，都点名「上游 `lerobot_train` 的 import 闭包里确有 imageio（18 个子模块）」这个事实源
（C 的 `c_ruling_34_1_import_surface_20260929.json`，方法 = 每模块一个子进程 + 回显 `sys.modules`）。
**installer 的改动用「原子改名」落地**（写临时文件 → `mv` 覆盖，同 fs 内是 `rename(2)`）：A 正在重装环境，
若 A 此刻在跑该脚本，持有旧 inode 的 bash 不受影响；**全程无 `rm`**。**纯注释改动**，`bash -n` 复过。

### 验收（本轮实测汇总）

| 项 | 实测 | D 的验收条 |
|---|---|---|
| 不变性闸 | **10 PASS / 0 FAIL**，`--selftest` **9/9**，rc=0 | §8.1 |
| 五套自检 | 12 / 157·39 / 15-15 / 47 / 6-6，**与 12:2x 逐项相同** | §8.1 |
| 重判 + 权威表 | 裁定变化 **0 处**；三键 SAME；构建未动 | §8.1 |
| freeze 护栏 | `--guard-selftest` **7/7** + 实弹 rc=1 拒绝、lock `d1ea71b7b4e5` 与 mtime 双双未动 | §8.2 |
| persistent lock | **7 PASS / 0 FAIL**，`--selftest` **12/12**（S0–S11：K1/K2/K3/K5 各红一次 + K6 两条红 + 3 条反向）<br>**16:0x 订正**：原写「6 PASS / 9/9」是加 K6 之前的数（见 决定 11） | §8.3 |
| installer | `IMAGEIO=2.38.0` / `UV=0.12.17`，取值理由写进注释，`bash -n` 通过 | §8.4 |
| 锚点 | 4 处已处理：**3 处改成内容锚**（A1/A2+A3/A4+A5），第 4 处（冻结门禁）登记 v1.6；T17 期望值按语义改写 | §8.5 |
| 环境溯源闸 | **12/12** 变异；三 venv 各 **PASS 5 / 0 / 0** | — |
| 内容锚登记册 | **8 PASS / 0 FAIL**，`--selftest` **8/8** | — |
| git | 提交不含 `tmp/`、不含 `runs/`；`b_git_size_guard.py` 通过 | §8.6 |
| AGENTS.md 纪律 | 新脚本内无 `rm`/`rmtree`/`unlink`；自检临时目录 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`；`datasets/` 未触碰；`platform.db*` 未触碰 | §9 |

### 遗留（本轮**未做**，如实登记）

1. **P1-1 v1.6**：现 **9** 项（裁定 23 六项 + `condN` 改名 + `terminal_kind` 溯源登记归 `configs/`
   + 决定 5 的冻结锚）。落地即升 `GATE_BUILD` ⇒ **B 主动通知 D 跑第三轮复签**（不等 D 发现）。
2. **P1-2 `C5=0.04` 双阈值并行重判**：裁定 29.5 第 3 条的前置（A 迁表）已结案 ⇒ **已解锁**，本轮**未开工**。
   纪律：**不得原地改常数**；先写预登记（两套阈值定义、臂集、构建指纹、判定规则、**可红条件**、差集产物路径），
   再并行重判 48 臂、报差集，**交 D 裁定后**才进门禁。
3. **P1-3 动作侧饱和率是否进门禁 warn**：**仍未裁**。要推进须先出「饱和率 × 受控成功」的 48 臂实测表
   （带构建指纹与臂集）；**不出表就维持未裁**，不写成「已同意进 warn」。
4. `.codex-persist/README.md` 的 `--no-deps` 警告无主义务（DR-013 决定 3 已指派 infra 会话/用户，**仓外**，B 不写）。
5. C 的探针补强两条（`torch.version.cuda` 断言、`inherited_packages` 分类）——已写进 B→C 交接单，**归 C**。

### 决定 13 —— B 自查出的一条**跨线耦合风险**：C 的登记处对 B 的 decisions 文件用**严格行号锚**

**发现经过**：C 在 16:16:54 把 B 的 `work/decisions/decisions_20260928_B.md` 摄取进
`work/decisions/registry/`（ADR-C-010：一条决定一文件 / 内容寻址 / append-only）。B 只读复核时实测到两件事：

**(1) 锚点是严格行号，B 有能力把它搞红（会造真红）**
`scripts/c_selfcheck_decisions_registry.py` 的 `case_real_registry` 取回原文的判据是
`start = int(source["lines"].split("-")[0]) - 1`，然后要求 `decision_id in text_lines[start]`
——**严格行号命中**，不是搜索。登记处里有 **12 条**（DR-003…DR-014）锚在这个文件上，
起始行分别是 `13 / 61 / 110 / 141 / 166 / 269 / 358 / 425 / 507 / 577 / 671 / 822`。
B **复刻 C 的这 4 行判据逻辑在 fixture 上实测**（未改 C 的任何文件、未改真文档）：

| 场景 | 锚点 FAIL |
|---|---|
| ① 现状（不插行） | **0 / 12** |
| ② 在第 1 行前插 1 行 | **12 / 12**（DR-003…DR-014 全红） |
| ③ 在第 700 行处插 1 行（DR-013 段内） | **1 / 12**（只有 DR-014 红，因为它的标题被推后一行） |
| ④ **只在文件尾部追加**（B 本轮与决定 13/14 的做法） | **0 / 12** |

⇒ **B 的操作纪律（自本轮起生效，写死）**：**`decisions_20260928_B.md` 只在文件尾部追加，
绝不往已登记段落中间或文件头部插行。** 需要更正旧决定时走
「append-only 更正指针」——原文一字不改、指针追加在尾部（本文件与日报已多处这么做）。
**这条纪律的代价 B 认**：它让 B 的 decisions 文件只能线性生长，但换来的是不给 C 造真红。

**(2) 登记处记的整文件 sha 会静默过期（不会红，但事实会旧）**
12 条的 `source.sha256_12` 都是 **`a08c2747c0ba`**，B 实测那正是**整个文件**的 sha256 前 12 位
（不是那一段的）。而 `c_decisions_registry.py::verify()` 只检查
「`pointer_only` 是否**有** `source` 锚点」，**不对账** `source.sha256_12` 与源文件现值
（B 逐条读过 `verify()` 的 5 类红：`tampered` / `payload_sha256_mismatch` / `criteria_duplicated` /
`pointer_without_source` / `event_*`，**没有**一类碰 `source.sha256_12`）。
⇒ **B 只要在尾部追加一个字节，这 12 条记的 sha 就全部过期，而登记处仍显 PASS。**
B 实测：现状 `a08c2747c0ba`；追加一行空行 → `acb07158fd26`；追加一条真决定 → `bf0968bd3030`。
**这与 裁定 37.4-3 是同一类**（产物里有一句没有任何判据对账的断言），只是方向相反：
那边是「散文与判据不同源」，这边是「**登记了一个没人验的事实**」。

**B 的处置（不越界）**：C 的文件 B 一行不改。已把上面两张实测表写进
`docs/b_handoff_to_c_20260929.md` §9，并给 C 两个可选修法（**由 C 自己选，B 不代选**）：
(甲) 锚点改**内容锚**（认「该行是否以 `## DR-0xx` 开头」而不是认行号）——与 D 给 B 的 P0-5 同型；
(乙) 保留行号锚，但 `verify()` **对账** `source.sha256_12`，过期就 **WARN 并提示重新摄取**
（把静默过期变成有声）。**B 已在决定 13/14 追加后主动请 C 重新摄取本文件**，
免得 C 的登记处长期挂着一个过期 sha。

### 决定 14 —— A 的 T17 **真跑**验证已收到：B 只读复核通过，但**本轮不改 B 的 T17 期望值**（附理由）

A 在 16:2x 交来 `docs/a_handoff_to_b_t17_train_side_verified_20260929.md`：B §8 那两条 A 侧待办
现在有了**真跑**证据（不是 smoke，是 `train_act_lift.py` 的默认规模：24/8 episodes、horizon 300、epochs 40、
7128/2376 样本、100 s）。**B 不采信转述，逐项只读复核了 A 的判据产物**
`runs/infra/a_t17_train_verify_20260929/t17_train_side_verify_v2.json`：

| B 复核项 | 实测 |
|---|---|
| 结论 | `verdict=OPEN`、`n_checks=8`、`blocking_fail=[]`；V1–V8 **全 `pass=True`**（8 条全 `blocking=True`） |
| V5 的 terms | 顶层是**嵌套 dict**（`goal` / `default` 各 6 个叶子），**叶子全 `true`**；两路 `gate=ALLOWED` |
| goal ckpt | `net0_in=62`（obs 60 + goal 2）、`has_goal_keys=true`、`goal_dim=2`、`goal_vocab=['lift_A_to_B','lift_B_to_A']` |
| 缺省 ckpt | `net0_in=60`、`has_goal_keys=false`、`goal_vocab=[]` ⇒ 对照组形状正确 |
| 账本换向 | `audits.alternate.rc=0`、`policy_goal_conditioned=true`、`goal_ledger` 的 `goal_id` 随 epoch 1→2 交替 |
| 词表单一事实源 | `vocab_single_source=['lift_A_to_B','lift_B_to_A']`，与 B 的 `GOALS` **逐字相同** |
| 溯源（裁定 37.1） | 新 lock `186579b96bce…` / `73dcde892146…`、旧 lock `68a38731c5b5…` / `b6db07e2e31c…`
**新旧并存**，与 B 的冻结面表**逐字一致**；`imageio` 生效 **2.38.0**，与 B 本轮提交的 installer pin **一致** |
| 引用口径 | `authoritative_citation = v1.5 / f19f61341cbe` + `spec_axis=observation_only`（**符合裁定 29.1**） |
| 主张边界 | A 自己在 `claim_boundary` 里写明**不含**「已学出方向差异」、**不含** 48 臂权威表跨断点复用 ⇒ **B 认可这条自律** |

**B 的处置 = 本轮不改 `b_selfcheck_goal_conditioning_t17.py` 的期望值**，理由三条（都不是推诿）：

1. **会动 D 已验收的 P0-1 基线**。`t17_mutation.json` 的 **6/6** 是不变性闸 V5 的比对项之一，
   也是 D 裁定 36.2 独立复核过的六份产物之一。改 T17 的期望值 ⇒ 6/6 的语义变 ⇒
   **P0-1 的验收需要 D 重跑**。B 不会在一个收尾轮里悄悄动一个已被验收的基线。
2. **B 现有结论没有被推翻，只是证据层级可以升**。B 的清单当前是 **闭合 6 / 阻塞 0**，
   两条 A 侧项走的是**双通道**（子进程真调 A 的**单元**自检读原始断言行 + B 自己的内容锚）。
   A 的真跑把证据从「单元层」升到「真跑层」⇒ **是增强，不是翻案**。所以本轮不存在「B 报绿报错了」的问题。
3. **A 自己也没要求 B 改**（A §6 明写「你的文件你决定，A 不代改」）。

⇒ **登记为独立一轮**（排在 v1.6 之后、或 D 指定优先级）：把两条 A 侧项的判据输入从
`a_selfcheck_goal_conditioning_t17.py`（单元层）改指 `t17_train_side_verify_v2.json`（真跑层），
**同批改期望值 + 补变异体 + 重跑 `t17_mutation` + 主动通知 D 重验 P0-1**。
**纪律照 D 执行单 §5**：语义变了 ⇒ **改期望值不只改行号**；且**不得**把 A 的 `verdict=OPEN` 直接抄成 B 的结论
（B 读 A 的 `rows[].pass` 与 `facts`，不读 A 的自评 verdict —— 与决定 6 的双通道口径一致）。

**B 必须随结论一起引用的边界（照抄 A 的 §4，B 独立认可）**：真帧 teacher 只做 `lift_A_to_B`，
`lift_B_to_A` 的演示源 **0 行**、`learnable_from_real_frames=false`；A 实测的 goal 敏感度
（输出空间 `mean|Δoutput|` 换 goal **0.00145** vs 扰动 state **0.522** ⇒ 比值 **0.0028**；
权重空间 goal 列 absmax **0.1352** vs state 列 **0.1400** ⇒ 比值 **0.966**）
**两个数要一起读**：wiring 活着、没被压成 0，但输出影响很小，因为 goal one-hot 在训练集里是常量、
未覆盖方向那一列拿零梯度停在初始化尺度。
⇒ **可以声称**：goal 贯通（计算图 + 采集分组 + 账本换向 + 拒绝语义）在**真跑规模**上成立。
⇒ **不得声称**：「共享 πθ 已学出 A↔B 的方向差异」——要后者必须先有 `lift_B_to_A` 的演示源。
**这条不改变 B 的能力结论**：官方 ACT 在这套 Lift 数据上仍然没有可重复的抬起能力，§8 晋级条件 ① 仍是唯一卡点。
