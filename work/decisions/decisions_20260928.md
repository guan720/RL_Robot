# 路线变更 / 口径裁定登记（2026-09-28）

登记方：智能体 D（监管/分析线）。依据：用户 2026-09-28 晚裁定。
本目录**只放裁定与登记**，实验结果、产物、日志一律不得写入（用户明示「最小写入」）。
格式为过渡版：C 线将建内容寻址、append-only、可撤销/ack 的正式登记处（监管备忘 增补三 §9-C④），
届时本文件由 C 迁移/摄取为 DR-001、DR-002 两条记录，迁移后本文件保留为只读历史。

---

## DR-001 `work/decisions/` 镜像目录

- 时间：2026-09-28 晚（用户裁定）；登记时间 19:40
- 裁定人：用户
- 内容：允许在仓库根建 `work/decisions/` 镜像目录并写入。外部已备份。
- 约束：**最小写入**——只放路线变更 / 口径裁定 / 作废与 ack 登记；
  实验结果与产物不得写入本目录。
- 背景：v4 要求路线变更先登记，但原目录在只读交付包 `RL_Harness_v4_20260924/` 内，
  B 无法写入（`docs/b_handoff_to_a_20260928.md` §6.1）。
- 解锁的事项：
  - B 的工程扩展（连续性正则 / slew limit）此前因无登记入口而停车；
  - A 的两条 L1 修复路径（`docs/lerobot_act_env_setup_20260928.md` §17.12 末）：
    (a) obs 契约变更（去掉或重定义 `observation.environment_state[3]/[4]`）= baseline 重置；
    (b) 自定义 processor 做训练+推理一致截断 = 越出官方入口纪律；
  - B 的 teacher 去饱和（`scripts/demo_scripted_lift_rs.py:99`）= baseline 重置，
    按监管备忘 增补二 §4 须先登记再动手。
- 生效条件：以上三项各自动手前，须在本目录追加一条独立记录（含变更内容、影响的基线、
  作废的历史结论清单、回归验收方式），不得以本条 DR-001 作为动手依据。

## DR-002 `git init`

- 时间：2026-09-28 晚（用户裁定）；登记时间 19:40
- 裁定人：用户
- 内容：允许对本仓库执行 `git init`。
- 背景：仓库非 git repo → 实验记录的「代码版本」字段无法填写，监管 P0 第一项不满足；
  B 此前只用 `gate_build` 内容哈希做局部替代，覆盖不了 A/C 的实现文件
  （`docs/b_handoff_to_a_20260928.md` §6.2）。
- 实施护栏（D 依 AGENTS.md 禁 `rm` 的同源风险附加，属本裁定的生效条件）：
  1. `.gitignore` 必须排除 `runs/`、`__pycache__/`、venv、视频与大 JSON 产物；
     被引用的裁定产物改为在受版控的文本文件里登记 `sha256 + gate_build + gate_spec_sha256`。
  2. 禁止 `git clean -fd`、`git reset --hard`、`git checkout -- .` 等会不可逆删除
     未跟踪 / 已修改文件的命令。
  3. `RL_Harness_v4_20260924/` 保持只读，不得因任何 git 操作被改写；
     `/workspace/mnt/sppro/yhzhang91/datasets` 在仓库外，不得纳管。
  4. 首次提交前，`.gitignore` 内容与「`runs/` 是否纳管」的决定先在本目录登记为独立记录。
- 执行人：B（提出方）。C 的逐臂内容哈希 run manifest（增补三 §9-C⑤）作为交叉校验，
  在 git 之外先满足 P0「代码版本」的实质要求。

---

## 增补登记（2026-09-28 20:58，D）：裁定 8–13

编号说明：纯 `DR-003` **预留给 B** 的 `.gitignore` / `runs/` 纳管登记（DR-002 护栏 4），
D 的本批条目用 `DR-D03…DR-D08`，避免撞号；C 建正式登记处后由 C 统一并号。
权威正文在 `rl_harness_supervision/supervisor_memo_20260928.md` 增补四，本处只登记裁定与生效条件（最小写入）。

- **DR-D03 门禁 phase 词表缺陷**（增补四 §1，回应 ADR-A-005.1）
  `phase_at_end ∈ CONTROLLER_LOG_VOCAB` 而缺 `phase_trace` 时，门禁**禁止**输出失效模式标签，
  只能判「字段不匹配 → INVALID / unjudged」。已造成一次实际假阴性：residual 臂 20 局被记 `flick=20`、受控 0，
  补字段后为受控 20 / `flick=0` → 该臂 `flick=20` 历史记录**作废**。执行人 B；`measurement_valid=False` 不受影响。

- **DR-D04 无归一化学习策略的输入契约**（增补四 §2，回应 ADR-A-005.2）
  新增状态 `not_applicable_unnormalized`，准入须同时具备：`normalization="none"` 声明 +
  **训练期 raw obs 逐维 absmax**（可追溯产物）+ **闭环 raw obs 逐维 absmax**（越界帧 ≤ 0.05）+ 阈值溯源。
  只有声明不放行。D 实测 `model_final.zip` **无 replay buffer** → 训练期范围不可恢复，
  故 residual 臂**维持 INVALID**；其 20/20 另受 `composite / system_assisted` 限制，不得与官方 ACT 臂同表。

- **DR-D05 探针免罪 `VALID_probe_exonerated`**（增补四 §3）
  准入 5 条，核心两条：C **必须等于**该 ckpt 的 `blowup_threshold`（train-absmax）；逐局 `verdict` 与
  `accounts` 五项计数**全部相同**，残余字段差异须枚举且不进入计数。
  D 自我纠错：原拟「字段逐位相同」过严，实测目标臂 `final_rise` 有 4 局不同（5012/5014/5016/5018，两路均 `failure`）。
  判别力取证：同臂 C=5.0 探针使 seed 5007 裁定翻转 → **不满足**准入，故 C 不可任意收紧。
  生效：`k2 seed0` 9/20 恢复；K=2 族 = 9/2/0/17/19/1（n=6，均值 8.0/20）；§8 条件① 仍 2/6 → **改判 1 不上调**。

- **DR-D06 `blown` 阈值溯源**（增补四 §4）
  门禁裁定 JSON 必须记 `blowup_threshold` + `threshold_semantics` + 来源 ckpt/stats；
  引用 blown 数字必须带阈值来源、产出路径（plain / clip_probe）、`gate_build`。
  依据：B 常量 23.85 vs A 按 ckpt 现算（train24 族 23.8450、trimdone0 族 12.469445）——同族数值一致、规则不同，
  跨族共用 0.05 容差**不是同一把尺子**。执行人 B。

- **DR-D07 `blown` 语义边界 + 解除 [0.03,0.08] 保留**（增补四 §5、§7）
  `blown` 只作**测量有效性**门禁，不得当失败原因（取证 `clampnochange/k2_seed0_ep5011_explained.json`：
  截断生效 144 帧、抬起峰值 tick 154 早于首个动作差异 tick 156，真值不变）。
  §12 裁定 1 的「暂不可采信」保留**即日解除**：单一来源化完成（`blown_metric_impl=52eae25ee2d7`）、
  恒等回归 `verdict=PASS`（唯一差异 `rows[].elapsed_sec`）、重测数字不变（0.0400 / 16/20 / gate_pass=true）；
  D 独立核出带内人口**只有 1 个臂**。带规则改为前瞻性。

- **DR-D08 §8 上调条件第 4 条重写**（增补四 §8，回应 ADR-A-005.3）
  原条「burst 贡献占比可复现 > 50%」**撤回**：实测最高 23.2%（k2 seed3）、次高 19.6%（k1 seed0）、
  21 臂合计 7.2%，无一达标；该条把「有没有能力」与「是否复现 teacher 动作形态」混同。
  新条：dz 归因**逐臂报告即满足，不设占比门槛**；burst > 50% 时另作诊断说明。
  D 自我纠错：该条入册前未核可达性。重写后 §8 现状 = ①不满足（K=1 1/6、K=2 2/6）②③④满足 → **仍不上调**。

- **附带登记（非裁定）**：增补三 §12 的两处断言由 D 撤回（「轨迹完全一致」只在 `max_rise` 投影上成立；
  「分母/参与维不一致」被 H1/H2 否证，真因是 H3 闭环轨迹分岔，80 局中 23 局）。
  48 臂权威汇总：受控合计 134（41 个有效臂 125）；实质 INVALID 由 7 → 2 →（DR-D05 后）**1**；
  三分类「可引用」23 → **24**。C 黄金值对账回流：`conformant=true`，PASS **171** / FAIL 0 / NOT_ASSERTABLE 1。

---

## 增补登记（2026-09-28 21:20，D）：裁定 14–15 与权威汇总刷新

权威正文见 `rl_harness_supervision/supervisor_memo_20260928.md` 增补五。编号续 D 的 `DR-D` 序列
（纯 `DR-003…` 序列归 B，见 `decisions_20260928_B.md`，两套不混用）。

- **DR-D09 `field_class != strict` 禁止输出失效模式标签**（增补五 §1，裁定 14，裁定 8 的推广）
  实测：blindfix 补测使 **16 局** `flick → insufficient_lift`、**1 局** `provisional_pass → controlled_success`，
  而 `blindfix_vs_archived.json` 证明 5/5 臂共有字段**逐位相同**（`n_differing=0`）→ 变的是门禁的证据分支，不是数据。
  根因：`held_at_end`/`final_rise` 双缺时走 `b_gate_controlled_success.py:153`（`HOLD_PHASES_STRICT={"hold"}`），
  字段齐时走 `:145`（`HOLD_PHASES_WITH_EVIDENCE={"hold","grasp"}`）——**同一个 `"grasp"` 标签**
  是否算 C4 证据，取决于一个不相关字段在不在；且同一份裁定里已写明 `field_class="partial"` 与 `missing_fields`。
  裁定：失效模式标签（`flick`/`insufficient_lift`/`over_lift`）**只允许在 `field_class=="strict"` 下输出**，
  否则判 `unjudged_evidence_missing` + `measurement_valid=False`。`:198` 的 `provisional_pass` 是按设计的待补测档，**不动**。
  连带作废：`flick=23` 不得引用，权威值 **7**（其中 5 局在 2 个 INVALID 臂上 → 可引用 **2 局 / 920**）。执行人 B。

- **DR-D10 门禁必须回显阈值与实现指纹**（增补五 §4，裁定 15，裁定 11 的落地缺口）
  门禁 `:284` 只从顶层 `input_constraints.train_time_norm_absmax` 读阈值，而官方 ACT 产物把阈值写在
  `input_contract.blowup_threshold`（=12.469445）→ 裁定 JSON 里恒为 `null`，
  并导致 `:311` 的 INVALID 理由字符串打印成「|x|>**0.0**」。
  裁定：v1.3 必须回显 `blowup_threshold` + `threshold_semantics` + `blown_metric_impl`（B 自己 DR-003 预告的
  DR-006「缺指纹才拒判」的前提），并修 `ic_note` 打印。A 侧产物已合规，缺的是 B 侧回显。执行人 B。

- **DR-D11 权威汇总刷新（48 臂 / 960 局，v1.2.1 / `e4f5ec887788`）**（增补五 §3）
  blindfix 合并后：受控 **135**、`insufficient_lift` **235**、`flick` **7**、`over_lift` 0、`provisional_pass` 0；
  `measurement_valid` **46 / 无效 2**（免罪后 **47 / 1**）；三分类 **24/22/2**（免罪后 **25/22/1**）；48/48 全 `strict`。
  A §21.10 的 **134 / 219 / 23** 为 blindfix 前口径，**已过期**，引用须标注。
  分母纪律：A §21.9 的 23/19/2 是 **44 臂**口径，与本条 48 臂口径都对，引用必须写分母。
  执行人 A（A-1：合并权威表 + `superseded_by` + `validity_class` + `blowup_threshold_source`）。

- **DR-D12 A-2 预登记复核结论：批准冻结，§2 一处事实错误须更正，不改阈值**（增补五 §5、§6）
  `docs/a_bimodal_divergence_preregistration_20260928.md`（21:15 冻结、21:16 开跑）四条约束全覆盖且有超出
  （R5 先行对账门槛、R4 输入契约、排除免罪臂、不进主目录 glob）→ **作为范式**。
  但 §2「`dz_pos_frac_tail` 0.9465+ 对 0.2430−，中间空 0.7」**只在 K=1 六 seed 上成立**：
  K=2 六 seed 有三个落在所谓空档（seed0 0.5677、seed5 0.6690、seed2 0.8670）；
  21 臂最大空隙是 0.2430→0.5677（**0.3247**），`0.9` 切点落在 `[0.80,0.95]` 的 **8 臂密集簇**内部
  （切点两侧最近点 0.8670 / 0.9400，间距 0.073）。
  处置：A 已冻结并开跑，**事后改阈值等于预登记失效，D 不要求改**；改为追加 **R7 报告义务**
  （`dz_pos_frac_tail ∈ [0.85,0.95]` 须同时报告 0.90/0.85/0.95 三种切法的级别，结论降级为「级别归属对阈值敏感」），
  并追加一节登记 21 臂全谱 + 补全 §4 表（K=2 对漏给第一判据 `dz_pos_frac_tail` = 1.0 / 0.8670，
  所给 0.0280 / 0.0082 是 `dz_mean_tail` 且未标名）。K=1 家族结论稳健，K=2 家族必须带敏感标注。
  首个结果（D 独立读取）：`k1 seed0 @010000` = ctrl **0/20**、`raw_success=0`、`mean_max_rise=0.0`、
  blown **0.0**、`strict`、`measurement_valid=True` → R4 不触发；实验问题被改写为
  「**行为上同为 0/20 时 dz 判别量是否已分开**」。

- **附带登记**：D 核验 B 的 `git init` **无违规并予确认** —— commit `0137b33`、tracked 228、
  `git ls-files runs/ RL_Harness_v4_20260924/ registry/*/` = 0、体积闸就位，DR-002 四条护栏逐条满足。
  D 遵守 DR-003 决定 8 单写者纪律，**不执行任何 git 写命令**；D 的两个写入文件已在 tracked 集合内，
  由 B 的下次提交自然带上。
  D 线第四次自我纠错已登记（增补五 §2）：D 曾把裁定 14 的根因误述为「per-frame 词表永不产出 `hold`」，
  实测 `actionminmax_s20k_seed2` ep5001 的 per-frame `end_phase` 就是 `"hold"`；正确根因是 `:145`/`:153` 分支不对称。

- **DR-D13 v1.3 顺序纪律（裁定 16）**（增补五 §11）
  B 已把 `GATE_VERSION` 升到 **v1.3** 并实现裁定 9 / 10 / 11 / 15（`IC_VALID_STATUSES` 含
  `not_applicable_verified` 与 `probe_exonerated`；`KNOWN_BLOWN_IMPLS=("52eae25ee2d7",)` 已含 A 的指纹，
  **D 无需另行会签该指纹**）；**裁定 14 尚未实现**（`:466` strict-only-hold 分支与 `:561` partial 分类原样保留，
  新增的 `blind` 类只覆盖「关键字段全缺」，覆盖不到 `partial` + per-frame `"grasp"` 这条通道）。
  **P0 风险**：`configs/b_blown_impl_grandfathered.json` 与 `configs/b_probe_exonerations.json`
  **均不存在**，而门禁读不到豁免册时「一律不豁免」→ D 实测主目录 43 份带 blown 字段的产物里
  **39 份缺指纹**，现状下 v1.3 全量重判会把它们判 `missing_new_reject`，**48 臂权威表整体不可裁定**。
  裁定：① 两个登记册填好前**不得**用 v1.3 全量重判；② v1.3 局部结果**不得**与 v1.2.1 混表；
  ③ `GATE_BUILD` 已不等于 `e4f5ec887788` → **改判 7 触发**，DR-D11 的表标注为 **v1.2.1 口径**，
  v1.3 全量重判后须重出一次；④ 豁免册 cutoff / 逐条理由与免罪册条目由 **B 写、D 会签**。
  连带修正 DR-D11 的执行顺序：A-1 的合并权威表**等 v1.3 落地后一次性建在 v1.3 上**，
  现在只先做结构性部分（`superseded_by` / `validity_class` / 分母标注 / 把 134-219-23 标为 blindfix 前口径）。
