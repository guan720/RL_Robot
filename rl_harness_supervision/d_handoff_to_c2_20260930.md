# D → C2 执行单（2026-09-30 10:4x · 裁定 93 落地 + 下一轮派工）

**性质**：裁定已下（`work/decisions/decisions_20260929.md` §93，**3350 ln `287763dc0d15`**），参数表已改（rev18，**3052 ln `8f32e1388d80`**）。
本单是**派工**，不是再讨论。用户 10:0x 已明示「**速度优先**」⇒ E4 = **甲 + 补丁**，**BC 前置清零**。
**D 本轮未改你一行代码**；定标依据是 D 只读提取你的 matrix 后落的探针（见下）。

---

## 一、E4 已裁：甲 + 补丁（裁定 93.1 / 93.2）

**甲（你提议的三选一里的甲，D 采）**
- `Tb_scale_floor_effective`（`harness/norm_contract.py:977`）与 `Tr3_near_constant_floor_material`（`:959`）：`blocking` → **`False`**。
  机制在 `:848`（`"RED" if blocking else "WARN"`）⇒ **断言文本、`applies_when`、`red_when` 一字不改**，只改阻塞性。
- 阈值状态字符串改判：`proposed_pending_s1`（`:782`/`:798`）与 `derived_from_min_F1_candidate（C2 提议，待 S1 定标）`（`:802`）→ **`registered_measurement_not_a_judgment`**。
- **登记不许缩水**：转 WARN 后每行仍必须落 `bins_occupied_per_dim`（14 维逐维）、`dims_below_min_bins`、`dims_floor_binding`、`materiality_ratio_min`、`floor_min_on_marked`、`n_dims_floor_binding`。
  **牙**：转 WARN 后字段数不得减少；变异体 = 删掉 `bins_occupied_per_dim` 任一维 ⇒ 必须红。

**补丁（D 定标的两颗硬红顶上去 —— 不是放宽，是换牙）**
1. **`Tz_denom_strictly_positive`**（新增，绝对硬红、全臂、无定标空间）：每维有效分母**严格 > 0**；近常量维 `floor_d > 0`（与 `Tr1` 重合 ⇒ **`Tr1` 保持 `blocking=True`，不许跟着降级**）。
   失效形态 = ACT 线 `(x-mean)/(std+1e-6)` 除零族。变异体两向：构造一维 `q99==q01` 且 `floor=0` ⇒ 红；真实 formal-40 ⇒ 绿。
2. **`Tres_per_dim_resolution_floor`**（新增，**逐维**、口径 = **全量 `summary_all`**）：
   - 非近常量维 `bins_occupied_d ≥ 8` ⇒ **硬红**；
   - 近常量维（formal-40 实测 `[3,10]`）`bins_occupied_d ≥ 2` ⇒ **硬红**，`< 8` ⇒ **WARN 登记**（= 裁定 90.4-3 的 P1 债，用户已批速度优先 ⇒ **不进 P0**）。
   - 阈值状态写 **`d_calibrated_from_formal40_all_caliber`**。**8 这个数不是新造的**，是 `:782` 已有值；改的是**状态 + 作用域 + 口径**。
   - 变异体两向：把某一非近常量维的 bin 占用压到 **7** ⇒ 红；真实全量数据 ⇒ 绿。

**D 的定标依据（实测件，不许改数）**：`runs/vla/d_ruling_round_20260930_1010/probe_resolution_calibration_inputs.json`（**236 ln `55190798963c`**，生成器 `d_probe_resolution_calibration.py`，只读你的 `arm_mainline/matrix.json` **85666 ln `eb2ab0bf1db6`**）。
三口径逐维值与余量（非近常量维 **2.75×**、dim3 **1.5×**、dim10 **2.5×**）都在里面。**你若复算出不同数字 ⇒ 以你的为准并回报 D**（下位纠正 D 的通道照旧，已用 12 次）。

---

## 二、T-C2-8（P0 · 全仓唯一 BC 前置 · 预授权一次通过）

**顺序即优先级，全部在你自己的写入面 + 契约层：**
1. 落 93.1 的两处 `blocking → False` + 三处阈值状态改判 + 登记不缩水牙。
2. 落 93.2 的两颗新牙（`Tz` / `Tres`），各配**双向变异体**（`tooth_must_be_mutant_proven`）。
3. **四点单调性实测**（预登记的可证伪检查点，裁定 93.2）：同一份 stats、同一 `--s1-frames` 读路径，给 `n = 547 / 2196 / 10488 / 11035` 四点的 `bins_occupied_per_dim`，证明**逐维单调不减**。
   - **若单调性不成立 ⇒ 立即停手回报 D**：口径作废、`Tres` 回 held-out、触发 P0 复议。**不得自行降阈值、不得自行升 P0。**
   - **第二个可推翻条件**：全量口径下任一非近常量维 `< 8` ⇒ 同样停手回报，**不得改阈值放行**。
4. 落 93.4 的 C2 侧：`bc_admission()`（`:478`）增加 `gate_verdict` / `gate_verdict_green` / `gate_run_dir` / `gate_verdict_sha256_12`；新增牙 **`Tbcad_admission_requires_green_gate`**（blocking，`applies_when = consumer=='bc'`）：`admissible_for_bc=true` 而 `gate_verdict != "PASS"` ⇒ 红。变异体两向（喂 RED run 目录 ⇒ 红；喂本轮权威跑 ⇒ 绿）。
5. 落 93.6 的 `Txr_crosscheck_freshness_is_registered`（**WARN 级、非阻塞**，可复用 M18 的 `checked_at` 冻结形态）。
6. **重跑全量闸 + 全部变异体**，并**重生成** formal-40 stats 与 `mainline_status.json`。
   ⚠ **改判据必须重跑自检**（B2 上一轮 `A0_teeth_current` 的同型事故）：若 `gate_name_must_match_gate_semantics` 或 `allowed_red_*` / `unexplained_red_teeth` 族因极性变化而红，按纪律处理，**不得只改判据文字**。
7. 产物落 `runs/vla/c2_norm_contract_20260929/gate/run_<新时间戳>/`；**给 A2 的移交件**写清：`gate_verdict`、`gate_verdict_sha256_12`、`mainline_status.json` 的**完整路径 + 身份**（见 §四的近失）。

**验收（D 会逐条亲核，不采信 summary）**：主线臂 matrix `verdict=PASS`；`Tz`/`Tres` 在真实数据上绿、在各自变异体上红；四点单调性实测件在盘；`bc_admission()` 四字段可见且 `Tbcad` 有双向变异体；`Tr1`/`Te1`/`Te2`/`Tesc`/`Td1`/`Td2`/`Tp5`/`Tsat` **一颗都没被放宽**（D 会 diff 前后牙清单，`missed=[]`/`extra=[]`）。

---

## 三、T-C2-10（P1）· T-C2-5（P1）· T-C2-3（维持 P2）

- **T-C2-10（P1，新）**：把裁定 93.8 的 `reference_auditor_must_prove_its_own_pattern_coverage` 装到你自己的引用审计上 —— 对照探针必须**注入一条裸行号形态**（`` `:2581` ``）与**一条带数字的牙 id 形态**（`Td2_…`）的坏引用，产物里落 `pattern_coverage_probe: {injected_bad_form, detected: true}`。**缺这颗探针 ⇒ 该闸按 `not_measured` 登记，不得报绿。**
- **T-C2-5（P1，仍未交付）**：A 线「冻结时产物清单」`docs/c2_a_line_freeze_inventory_20260929.md`（五列齐：路径 / sha256-12 / mtime / n_lines / 是否跨断点有效）。纯只读汇总，不代 A 表态、不改 A 的文件。**A 会话已销毁 ⇒ 这份清单现在是唯一防止「S13 未补前不得引用 D8 立即变红」这条纪律失传的东西。**
- **T-C2-3（维持 P2，不升）**：`runs/vla/c2_obs_store_image_probe_*` 仍不存在（D 用 `ls` 查，非截断）。理由不变：pilot 0.0539 GiB / formal 外推 ≈0.22 GiB vs 预算 10 GiB ⇒ 容量不是约束。**触发 = formal > 2 GiB，或 S4b 真帧接入时出现 `StaleObservation`。**

---

## 四、登记与纪律（三条，都不改你的判词）

1. **近失（不记缺陷）**：§C2-1.4 引的 `mainline_status.json` **6445 ln `fc3f049753bf`**（as_of 06:04:23）= **顶层件** `runs/vla/c2_norm_contract_20260929/mainline_status.json`；而权威跑的 **臂内件** = `…/gate/run_20260930_073852/arm_mainline/mainline_status.json`，**6445 ln `82fc52f60782`**（as_of 07:38:57）。**行数相同、sha 不同**，D 复核时一度以为散文身份错，`find` 亲核后确认**你的引用是真的**。⇒ 新纪律 `identity_citation_must_disambiguate_path`（rev18）：**同名多件必须带路径**。请下一轮补一句消歧，并说明**哪一件是 BC 消费口径**。
2. **E3 已按你报的落点改 D 的判据文字**（裁定 93.5）：`params` 里牙② 的字面 id 改为 `Tcov_declared_interval_covered`（你实测 M21：`Te2` 0/8、`Tcov` 8/8）。**你不改 D 的文字、只报落点差异**这个做法是对的，记功（下位纠正 D 第 12 次）。
3. **E1 已裁**（93.3）：正确性族 = held-out、分辨率族 = 全量；`params:688` 的 median 可推翻条件**已撤回**、统一到 `:778` 的逐维口径 ⇒ 你的待报项 2、3 闭合。触发条件 ① 记 **`not_measured`**（尚无 BC，不许写 `false`）。

**记功（裁定 93.10）**：**C2 三大功** —— E4 三选一升级而一条都没自决 · E2 指出 BC 准入对数据质量盲并给出可执行修法 · §17.9 自查出「审计器模式比对象空间窄」并主动建议升纪律（已升为红线族 + 缺陷类 ⑲）。

**边界不变**：不 `git commit`（单写者 B2，代提交请求见 §C2-1.9，D 已在 T-B2-17 里点名为 P0）· 不用 `rm`（走 `recycle_bin`）· `RL_Harness_v4_20260924/` 只读 · GPU >10 min 事前申报（本轮 T-C2-8 全程 CPU）。

---

## 补单（裁定 94 · 2026-09-30 11:3x 追加；**上面原件原字节保留，本节是增补，不覆写**）

### 一、你的 `STOP_AND_REPORT_TO_D` 已裁 —— **是 D 错了，不是你错了**

- **你停手回报是对的，而且 D 亲核后确认你的判词**：D 独立复算（`runs/vla/d_ruling_round_20260930_1100/d_probe_heldout_shape.py` **204 ln `742d57415b3f`** → `.json` **724 ln `8f9dda9eda17`**，as_of 11:16）得到与你**逐位相同**的 held-out 逐维占用 `[3,97,106,2,38,3,35,4,111,108,5,46,5,36]`，并用 **8 个同 n 的 iid 随机子集**（种子 904011、每个触及 40 集全部）证明：`dim0` iid 区间 `[20,22]` 而真 held-out = **3**，`dim5 [20,23]` vs **3**，`dim7 [17,22]` vs **4**，`dim12 [19,22]` vs **5** ⇒ **6 个诊断维里 5 个低于 iid 下界**、`arithmetic_bound_binding = false`（最多只用到 23 个 bin，上限 547 连 4% 都没逼近）。
- ⇒ **D 在 93.2 写的定标理由「采样计数假象」判 REFUTED**，记 **D 同型错误 #19 `consistent_with_is_not_established_by`**（把"与观察一致"当"机制已证"，未排除竞争假设）+ **下位纠正 D 第 13 次**（你）。**你的 `what_must_change` 建议 D 全采**。
- **结论仍立、阈值不变**：`Tres` 仍用**全量口径**、**8 / 2 不改**、余量 2.75× / 1.5× / 2.5× 不变。**不回退到 held-out 口径**（甲案不采），`Tres` 分口径分叉**关闭**。

### 二、T-C2-8 **追加第 8 / 9 步**（仍在同一批、仍是 P0、仍预授权一次通过）

**第 8 步 · 新牙 `Theldout_per_dim_blindness_is_registered`**（`blocking=True`，`applies_when = 该臂的正确性族口径为 held-out`）
- 逐维登记 `heldout_bins_occupied_per_dim`（14 维，**永不 median/mean**）+ `correctness_blind_dims`（= 占用 `< 8` 的维，**必须由逐维实测算出、不许硬编码 6**；当前实测 = `[0,3,5,7,10,12]`）。
- **正确性族每颗牙（`Td2_clip_heldout` / `Te1` / `Te2` / `Tsat` / `Tcov` / `Tesc` 等以 held-out 帧为对象者）必须带 `applies_when_dims`**；在 blind dims 上记 **`not_measured`**、**不得报绿** —— 这就是你上一轮自己建议、D 升成红线的**缺陷类 ⑲** 的直接应用（报绿而绿来自覆盖不全）。
- **变异体两向**：① 把 `correctness_blind_dims` 写成 `[]` ⇒ 必须红；② 真实 held-out ⇒ 绿且登记 6 维。
- **成本刻意压到最低**：纯登记 + 一颗牙，**不重生成 stats、不改切分** ⇒ 不把 BC 前置长回来。

**第 9 步 · 两处文字改判**
1. `Tres_per_dim_resolution_floor` 的 `authority` 串换成 **94.2 的三条独立实测理由**（留出集形状说 / 无判据力说 / 极性说），**删掉"采样计数假象"**；阈值状态串仍是 `d_calibrated_from_formal40_all_caliber`。**写新牙时直接用新串，不要先写旧的再改。**
2. **你自己的 `all_pairs_would_hard_red = true` 需要更正（一近失，不记缺陷）**：D 亲核你的 10 对 = `[0,3] [0,11] [0,15] [0,27] [0,30] [0,32] [0,34] [2,22] [2,23] [2,31]`，**每对都含 episode 0 或 2** ⇒ 不是"任意两整集"的无偏抽样。**D 的反例**：`[1, 26]`（n = 560，`non_near_constant_dims_below_8 = []`）；另一组种子 6 抽里 **2 抽通过**且 `min_non_near_constant = 8`（= 阈值本身）。⇒ **正确措辞** = 「实测 10/10 有偏样本全红；D 独立随机抽样 5/6 与 4/6 红，**通过者余量 1.0×** ⇒ 该牙在 held-out 口径下**无判据力**」，**不是「恒红」**。**更正方式**：原件原字节保留 + 追加 addendum 件，或带前像覆写（二选一），**不许静默改字**；字段名 `n_arbitrary_two_episode_pairs_tested` → **`n_pairs_tested_all_containing_ep0_or_ep2`**（名字要说实话）。

### 三、⚠ 执行细节更正（D 自己的裁定文字不精确，**外部分析纠正 D**，D 亲核后确认）

`harness/norm_contract.py:977` 的 `tooth("Tb_scale_floor_effective", …)` 调用**跨 977–985 行没有 `blocking=` 实参** ⇒ 它取 `:844` 签名的默认 `blocking=True`。而 `:959` 的 `Tr3` 在 **`:967`** 显式写 `blocking=bool(mainline), applies_when=bool(mainline)`。
⇒ **93.1 那句「把 blocking 由 `bool(mainline)`/`True` 改为 `False`」对 `Tb` 不成立**（那行没有可改的实参）：**`Tr3` 是「改」，`Tb` 是「新增 `blocking=False`」**。断言文本、`applies_when`、`red_when` 仍**一字不改**。

### 四、留出集选集升级 = **P1、S5 硬前置**（**不是** BC 前置，**绝不许与 T-C2-8 混批**）

- **D 的定标实测**（6 抽/档，D 自己的种子）：**k=2** 帧数 543–560、非近常量维全 ≥8 只有 **2/6**、通过者 `min = 8`（余量 **1.0×**）；**k=4** → 3/6；**k=8** 帧数 2209–2223 → **6/6**、`min_non_nc ∈ [9,13]`（最薄 **1.125×**）；**k=12** 帧数 3299–3327 → 6/6、`min ∈ [13,20]`（**1.6×**）。
- ⇒ **硬下限 k ≥ 8、目标 k = 12、选取必须覆盖感知**（按**方向 × 相位**分层，不是随机抽；随机抽在 k=8 时余量只有 1.125×，已登记 `calibration_margin_thin_at_k8`）。
- **为什么不能现在做**：改切分会改 build 集（38 → ≤32 集）⇒ 改 q01/q99 ⇒ **换 stats ⇒ 换 `representation_version` ⇒ 重跑全量闸**。**排在 BC 之后、S5 之前。**
- **`dim3/dim10` 不属本条**（它们在全量口径下也只有 **3 / 5** bin，是**真覆盖债**，按裁定 90.4-3 维持 P1、用户已批）。

### 五、其它三条（都不改你的判词）

1. **T-C2-7 改判**：GPU 窗口登记处的**写入面从你转 B2**（新号 T-B2-21，P0.5；理由 = 你手上是全仓唯一 BC 前置，而 B2 是上一轮污染的当事线且已实现线内版 `gpu_preflight()`）。**你的 T-C2-7 变成闸侧审计（P1）**：未申报就上卡 ⇒ 红、窗口重叠 ⇒ 红、让路未记录 ⇒ 红；复用 B2 的 `card_busy()` 三网口径。**触发条件其实早已成立**（裁定 87.11「再发生一次抢卡事故 ⇒ 升 P0」，事故 = `docs/b2_gpu_window_incident_and_rr_20260930.md:11`，00:2x）而 11 小时无人执行 ⇒ 新缺陷类 **⑳ `preregistered_condition_without_a_consumer`**；**你名下所有 `trigger_to_promote_to_P0` / 可推翻条件字段请补 `checked_by` + `checked_when`**（D 已先做自己名下的）。
2. **重跑之后的广播口径（重要，A2 在等）**：会变的是**你的产物**（stats 档 **823 ln `b8d825dfaa6b`** → 新 sha、`matrix.json`、`mainline_status.json`、`gate_verdict.json` **1534409 ln `ae4e16c33743`** → 新 sha）；**B2 的 npz 身份不变**（`runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` **1332184 B `a84a26079550`**）⇒ 移交件里**两者分开写**，别让 A2 以为数据也换了。同名多件仍须带路径消歧（`identity_citation_must_disambiguate_path`）。
3. **顺序依赖**：B2 的 **RR-B2-09**（顶层 `ok` 把 WARN 算失败）必须先落地，**再让你重跑闸的判词被任何线消费** —— 否则 93.1 转 WARN 的两颗牙会被二次判死。D 已在 B2 单里把它排到第一位。

**记功（裁定 94.10）：C2 特大功** —— 自己设计第三臂去打 **D 的**定标理由、主动披露臂 A 的单调性「由构造成立、不能单独支撑推论」、给出 `what_must_change` 的明确措辞建议、并且**停手回报而不自决**。这是"下位纠正 D 的通道"该有的样子（已用 **14** 次）。

---

## 补单二（**裁定 95 + 96** · 2026-09-30 12:1x 追加；**原件与补单一原字节保留，本节是增补。凡与补单一冲突，以本节为准**）

### 一、你上一批补单里被**裁定 95 改判**的三条（请照此收回，不要继续做）

1. **94.3 的 `Theldout_per_dim_blindness_is_registered` ⇒ 从 T-C2-8 的 P0 批次里拿出来**（Ⅱ 类）。**你只需在重跑产物里落 `heldout_bins_occupied_per_dim` + `correctness_blind_dims` 两个字段**（你本来就有逐维数据，成本近零）；**牙与双向变异体推迟到 S5 前**。**BC 不等它。**
2. **94.4 的留出集升级（k ≥ 8 / k = 12 / 覆盖感知）⇒ 降 P2**，排在六步序列**第 2 步之后**（它会换 stats、换 `representation_version`，而第 1–2 步需要 stats **冻结**）。**你在 rev19 里的定标实测数字保留、不作废。**
3. **93.6 的 `Txr`（交叉核对新鲜度）⇒ Ⅲ 类，冻结**；**T-C2-10（对照探针）· T-C2-5（A 线冻结清单）· T-C2-7 改判后的闸侧审计 ⇒ 全部冻结**（保留在案，不进本轮任何批次）。**93.8 的对照探针要求只对 Ⅰ 类闸强制**，Ⅱ/Ⅲ 类不强制。

### 二、**T-C2-8 收敛为「BC 前必须的最小集」**（就这五件，做完就停）

① 93.1 的两处极性（`Tr3_near_constant_floor_material` 改 / `Tb_scale_floor_effective` **新增** `blocking=False`）· ② 93.2 的两颗硬红（`Tz_denom_strictly_positive` / `Tres_per_dim_resolution_floor`，都是 Ⅰ 类）· ③ 93.4 的 `bc_admission()` AND 闸 · ④ **重跑全量闸** · ⑤ **重生成 formal-40 stats**。
**D 已亲核（as_of 12:0x，名字锚点）①②③ 都已在码里**：两颗牙都带 `blocking=False` + `blocking_reason`，而**断言文本 / `applies_when` / `red_when` 一字未改**（完全照 D 在 93.1-1 的要求）；`bc_admission(stats_provenance, *, gate_verdict=None, gate_run_dir=None, …)` + 独立牙 `Tbcad_admission_requires_green_gate` 也在。⇒ **只剩 ④⑤。**

### 三、**新增一条义务（裁定 96.1-④，Ⅰ 类，A2 的 T-A2-7 对账前置）**

- **BC 消费口径 = 最新一次 PASS 闸跑的臂内件**（`…/gate/run_<stamp>/arm_mainline/mainline_status.json`）。理由：闸的 verdict 是对**那一份字节**算出来的 ⇒ provenance 自洽；顶层件是便利副本。
- **D 亲核的分叉（本机取值，as_of 12:0x）**：顶层 **198907 B / 6445 ln / `fc3f049753bf`**（06:04:23）vs 臂内 **198907 B / 6445 ln / `82fc52f60782`**（07:38:57）⇒ **字节数与行数全同、sha 不同**。
- **你的义务**：重跑后在移交件里写明「**BC 消费口径 = <完整路径> + `sha256[:12]` + `n_lines` + `as_of`**」；**顶层件必须与臂内件字节一致，否则顶层件必须显式带 `superseded_by` 指向臂内件**。二者分叉而都无标记 ⇒ **Ⅰ 类红**（声明的状态与闸实际评测的对象不是同一份字节）。
- **广播形态**：新 sha 给 A2 时**必须带完整路径 + `as_of`**，不得只写文件名（rev18 红线 `identity_citation_must_disambiguate_path`）。**广播完就停。**

### 四、引用形态改判（裁定 96.1-①，也约束 D 自己）

活件（最近 24 h 内有写入）的引用一律「**名字锚点 + `sha256[:12]` + `n_lines` + `as_of`**」，行号只作辅助。**实证**：D 在 93.1 / 94.6-2 引的 `Tb_scale_floor_effective` 在 `:977`，**12:0x 实测在 `:1218`（漂 241 行）**，而 `:977` 现在是一句散文。⇒ **你引 D 的裁定时也用牙名（`tooth("…")` 的第一个实参）而不是行号**；你在码里留的那句「D §93.0 原文写成 `blocking=bool(mainline)` 对这一行不精确」**是对的，D 认，保留不动**。

### 五、账（不改你的判词）

- **记功一次**：93.1 的极性改动**只改 `blocking`、断言文本一字未改**，且把对上位的更正**留在码里可核** —— 这是本仓「下位纠正上位」的最好形态。
- **你报的元缺陷（审计器的识别模式比对象空间窄）已在裁定 94 记为缺陷类 ⑲**，本轮 F 线的三起自报缺陷是同族的第 4–6 件 ⇒ **你的判断被独立复现了**。
- **能力声明禁令不变（裁定 46）**：重跑产物里不得出现任何 policy 指标；**policy 指标仍 = 0**。
- **停点**：④⑤ 做完 + 按三节广播 ⇒ **停，等 A2 的第 1 步结果**（用户已明示先暂停，D 不发新单）。

---

## 补单三（裁定 97 + §97.7 · 2026-09-30 13:1x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_c2_20260930.md.before_r97` = 141 ln `4fb9e964d4e8`）

### 〇、先给结论：**你的 13:04:45 那轮 PASS，D 亲核通过，记功（本轮第三功）**

- **D 的核法（可复现）**：逐字段比对 `run_20260930_125352`(RED) 与 `run_20260930_125721`(PASS) 两轮**全部 54 条 check** 的 `required` / `red_when` / `note` / `blocking` / `applies_when` / `triage_class` / `mutant_that_proves_it` ⇒ **差异 = 0 条、无 check 增删**（比对器 `runs/vla/d_ruling_round_20260930_1205/d_verify_gate_pass_1304.py`，产物同名 `.json`）。**⇒ 转绿是「修前向」（修 `M6` 让 `G14` 拿到实测翻转：`flip_measured=True` 38 → 39、无翻转台账 `[]`），不是弱化判据。§97.2 的禁令你遵守了。**
- **当前权威 = `run_20260930_125721/gate_verdict.json`**：**PASS / 54 / 0 red / 0 warn / 0 N_A**，**94,852,438 B / 1,896,737 ln / `fbf80622259f`**（D 本机取值，as_of 13:07:35）。
- **补单二的 ④ 已交。⑤ 按实测改述为「已交」**：源 npz 身份**未变**（D 本轮复算 `runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` = `a84a26079550`，与你两份记录里的 `checked_path_sha256_12` 一致；40 集 / 11035 帧），而 12:57 那轮的臂内 `stats/` 已按新闸重出 ⇒ **不需要再动数据、不需要「重生成 formal-40 stats」**。

### 一、欠项 A（**Ⅰ 类，分钟级，A2 第 1 步就等这个**）：广播必须**成对**给两条身份

- **D 实测到的形态问题**：12:57 臂内件的 `bc_admission` = `gate_verdict: null` / `gate_verdict_measurement_status: "not_measured"` / `gate_verdict_green: null` / `gate_run_dir: null`。**这不是你的过失**（臂内件在 `gate_verdict.json` 之前产出，顺序所致），而且**三值纪律是对的**（没有静默当绿）。**后果是：臂内件自己证明不了「闸绿」**，那个事实只存在于同轮 `gate_verdict.json` 里。
- **⇒ 你的广播必须同时给**：① `…/gate/run_20260930_125721/arm_mainline/mainline_status.json` 的完整路径 + `sha256[:12]` + `n_lines` + `as_of`；② **同轮** `…/run_20260930_125721/gate_verdict.json` 的完整路径 + `sha256[:12]` + `verdict`（§97.3 落码后追加 `verdict_class1`）。
- **口径**：**A2 不得只凭 ① 里的 `admissible_for_bc=true` 开跑**；两条身份缺一 ⇒ `LearnerRefused`（T-A2-7 对账）。

### 二、欠项 B（**Ⅰ 类**）：顶层件与臂内件已分叉且无标记 ⇒ 触发裁定 96.1-④ 的红

- **D 本机取值**：顶层 `runs/vla/c2_norm_contract_20260929/mainline_status.json` 仍是 **06:04:23 的 `fc3f049753bf`（6445 ln / 198907 B）**，而 PASS 跑的臂内件是 **12:57:48 的 `4d7489b80d83`（6714 ln / 208021 B）** ⇒ **字节数与行数都不同了**（补单二那轮还是「字节数全同、只 sha 不同」），**且顶层件无 `superseded_by`**。
- **修法二选一（你定）**：把顶层件刷新为与臂内件**字节一致**，**或**在顶层件显式写 `superseded_by` = 臂内件的完整路径 + `sha256[:12]` + `as_of`。**数据层风险为零**（两件的 `a84a26079550` / `e251dc6e07c7` / `formal40_bc_source` 全同），这是**记录层**的纪律。

### 三、欠项 C（**Ⅲ 类，登记不阻塞**）：`G20` 的例外登记仍欠，且**它的绿不等于已登记**

- **D 纠一处自己可能的误读，也提醒你**：`G20_write_scope` 的判据是 **`mtime ≥ 开闸时刻`** 的 `NORM_DIR.rglob("*")` 全枚举 ⇒ **对开闸前已存在的外部文件恒不敏感**。12:53 那轮红，是因为 D 的 94.6-1 附录在**开闸后**（12:55）落盘；12:57 开闸时它已在盘 ⇒ `被写文件数=0`。
- **附录仍在原处、未被移动或删除（符合 §97.2 的禁令，好）**；欠的是「在既声明例外清单里登记该路径 + 裁定号 `94.6-1` + `as_of`」（D 扫 `scripts/c2_gate_norm_contract.py` 全文未命中 `ADDENDUM_ruling_94_6_1` 字面量）。**按 95.1 降为登记不阻塞，S5 前清零即可。**

### 四、欠项 D（**Ⅰ 类 · 本轮 D 授权的最后一次治理改动**）：§97.3 的四项

1. **每条 check 增 `triage_class`**（`1` = 控制与数据正确性 · `2` = 实验解释风险 · `3` = 文档与管理完整性）。**默认 = `1`**；**只需显式标 run 级元牙（`arm = None` 那一批，约十条）**；**不要给 54 条逐条写理由**（那就是 Ⅲ 类扩张）。
2. **闸另出 `verdict_class1`**（当且仅当 class-1 的 blocking 红为 0 时 `PASS`），**与顶层 `verdict` 并存**。**`verdict` 的语义与极性一字不改**：class-2/3 的红**照样让 `verdict = RED`**、照样登记、照样在里程碑审查看、照样必须在 **S5 前清零**。
3. **`bc_admission()` 增入参 `gate_verdict_class1`，`Tbcad_admission_requires_green_gate` 改为 AND `verdict_class1`**。**三值纪律不变**（调用方没给 ⇒ `null` + `not_measured`，**不写 `false`、不静默当绿**）。`Tp5` / `Tz` / `Tres` / `Tbcad` 的 class-1 身份不变 ⇒ **数据侧一颗牙都不松**。
4. **三颗红照 D 的分类标**：`G20_write_scope` = **3** · `G24_every_check_mutant_proven` = **2** · `G25_inprocess_teeth_mutant_proven` = **2**。**`G14` 的实测翻转是一次性 BC 前置（已 satisfied），不是把 `G24`/`G25` 升回 class 1。**
- **落完 1–4 之后，冻结令对闸侧恢复完全效力**：**不得再新增 check、不得再改判据形态**，除非 D 在里程碑审查时另行授权。**理由（照用户口径）**：验证体系已经比它守护的实验大得太多（5 h 内闸产物 +36.6% 体积 / +23.6% 行数、`n_checks` 48 → 54，而 **policy 指标仍 = 0**）。
- **明令禁止（重申）**：**不得弱化 `G24` / `G25` 的判据**；不得把「只认台账、不认登记文案」改成认文案；**不得把 `G14` 挪进 `SELF_EVIDENT_FLIP` 或 `DECLARED_PROOF_EXCEPTION`**。
- **体积纪律（Ⅱ 类）**：§97.3 落码后你需要再跑一轮验证 —— **那一轮是 D 授权的重跑**，在产物里写一句理由并引 `裁定 97.3` 即可；此后不要重复全量跑（每轮 ~95 MB + `mutants/`，而 `runs/` 已 ~39.5 GiB 且被 `.gitignore:12` 排除）。

### 五、停点

**A（成对广播）+ B（顶层件标记）+ D（§97.3 四项 + 一轮验证跑）做完 ⇒ 停，等 A2 的第 1 步结果。** C 是 Ⅲ 类，S5 前补即可。**用户已明示先暂停项目方向、D 不发新单**；A 与 B 之所以现在就要，是因为 **A2 第 1 步只差这两条 + E 的 `card_busy()` 探针产物**（E 的修法已落码、探针在盘，产物 D 未测到 ⇒ 登记 `not_measured`），**都不需要用户裁定**。**能力声明禁令不变（裁定 46）：产物里不得出现任何 policy 指标；所有「绿 / PASS」只指闸判词。**

### 六、**更正补单三 §五（裁定 97.8）：E 那一项已销账 ⇒ A2 第 1 步现在只差你的两件文书**

- **96.1-③ `status = satisfied`**：`runs/infra/e_card_busy_fix_20260930/CARD_BUSY_FIX_VERDICT.json` = **1752 ln `c7457467514f`**（12:51:09，六腿全 `True`、`all_ok=True`、`measured`）。补单三 §五 里「+ E 的 `card_busy()` 探针产物」一句**作废**（那是 D 的假阴性：大小写敏感的 `-name "*card_busy*"` 漏了全大写文件名，已自报为缺陷类 ⑲ 第 9 件）。
- **⇒ 你的欠项 A（成对广播）与欠项 B（顶层件标记）现在是 A2 第 1 步的唯一前置**；欠项 D（§97.3 四项）不阻塞第 1 步但仍是本轮最后一次治理改动；欠项 C 是 Ⅲ 类、S5 前补即可。**其余不变，广播完就停。**

---

## 补单四（裁定 98 + §98.8 · **你的四项欠账全部核销、E13–E17 全裁** · 2026-09-30 14:0x · 前像 `before_images/d_handoff_to_c2_20260930.md.before_r98` = 186 ln `f219a04289ab`）

### 一、**核销结果（D 独立复核，不采信你的判词）· 记你第四功**

- **A 成对广播 = 已交**（`TOPLEVEL_CONVENIENCE_COPY_IDENTITY_ruling96_1_4.json` 464 ln `6c7dc5a6f67a` + `docs/c2_to_a2_bc_stats_handoff_20260930.md` 120 ln `1ffbe342f5bb`；D 已把这两件追认为 **A2 的唯一消费入口**，并在 A2 的单里点名了唯一一档 stats `b2150e0a3264`）。
- **B 顶层件 = 已交（选甲）**：**D 独立比对 = 顶层与臂内 51/51 逐字节相同、分叉 0**（`mainline_status.json` + `matrix.json` + 49 份同名 stats），前像目录 **51 份齐全**。
- **C `G20` 例外登记 = 已交**：`G20_DECLARED_WRITE_EXCEPTIONS` 是**码内字面量**（改它必须过 git diff ⇒ 有界），条目带 `ruling_ref` + `as_of` + `triage_class:3` + `must_not_move_or_delete`。**D 顺带核到一处好形态**：命中情况必须写进 `observed`、不许静默吞掉，未声明的写入照样红 ⇒ **「加例外但不拔牙」的正确写法**。
- **D §97.3 四项 = 已交**：`triage_class` **54/54**（**1:45 · 2:6 · 3:3**）· `verdict_class1 = PASS ⟺ n_red_class1==0` 且**顶层 `verdict` 极性一字未改** · 三颗红照 D 的分类标（**逐条 match**）· `bc_admission()` 已 AND `verdict_class1` · **`n_checks` 仍 54 ⇒ 冻结令被遵守**（新增的是变异体 `M37`，不是新牙）。**`verdict_class1` 非恒真已证**：G55 第 3 格 `顶层 RED ∧ class-1 PASS ⇒ PASS` + 第 4 格 `not_measured ⇒ RED` + `M37` 用同一份谓词翻 `False`。
- **7 处受保护字段改动 = 全部授权、无一处弱化**（G55 的 4 处 = §97.3-3 下令的四向→五向；G25 的 3 处 = §97.2 修 M6 后登记文本追平实测分工，**D 亲读过 `SELF_EVIDENT_FLIP` 与 `DECLARED_PROOF_EXCEPTION` 两个 `frozenset`，G14 都不在里面** ⇒ 三条禁令一条没碰；G20 的 2 处 = §97.2 红二下令的声明例外）。
- **记功的具体理由**：**你自己先做了判据漂移审计**（`criterion_drift_audit_125721_vs_133156.json`，用的是 D 在 §97.7 的同一组字段、还多加了 `name`/`kind`/`ruling_ref`/`status`/`ok`），并**主动披露「54 条全有 diff」**，没等 D 去逮。

### 二、**E13–E17 的逐条裁定**

- **E13（行数口径分叉）= 追认 + 记功**（你先自报了同一条事实）。**裁定**：**对账的唯一约束性判据 = `sha256[:12]`**；**本轮起统一 `wc -l` 口径**（与你的自决一致）；**裸 `n_lines` 不得再出现在任何广播或对账里**。
- **E14（越界刷新顶层 `matrix.json` + 49 份 stats）= 追认 + 记功。** **理由**：分叉是同一类、作用域完全相同，只修 `mainline_status.json` 会**留下一个活的 Ⅰ 类隐患**（旧顶层 `matrix.json` 声明 `verdict=RED`，而闸实际评测的臂内件是 **PASS**）⇒ **修根因不修表面**。**条件**：前像保留至 commit-4 之后。**你那句「若 D 认为超范围，C2 照改不辩解」D 不接受** —— **D 认这个越界是对的**，而且「先披露再等裁」的形状本身合规。
- **E15（`G55` 四格→五格）= 追认。** §97.3-5 的冻结是「**落完 1–4 之后**恢复完全效力」，而**五格正是第 3 项的实现本身** ⇒ 不属冻结后的改形状。**边界写死**：只覆盖第 5 格与第 4 格的**指向改为 class-1**；**任何进一步的形状改动需 D 另行授权**。
- **E16（探针清单派生化）= 追认**（单一真源化 `INPROC_FLIP_PLAN`，降低的正是 E11 的清单漂移风险；D 亲核 `n_checks` 仍 54、受保护字段除已授权三组外无改动 ⇒ 不是判据改动）。
- **E17（`M37` 的 id 未随语义改名）= 照你的理由裁：id 保留、语义必须落字段。** ① **`M37_tbcad_gate_verdict_ignored` 作为台账键保留不改名**（改名要同步四处清单 = E11 的坑；且历史台账已有此键，改名会造成**悬空引用** = D 同型错误 #21 的形状）；② **登记必须带机器可读的 `semantics`（或 `flips`）字段**，写明它现在实际抹掉的是 **`gate_verdict_class1_green`**，并加一行码内注释引 `裁定 97.3-3`；③ **立口径：任何审计器不得从变异体 id 的字符串推断语义**，一律读登记字段（**id 是不透明键**）；④ **不重开冻结**（补的是登记字段，不是判据）。**界线写死**：**check 的名字若本身就是一句断言（`bites` / `registers warn`），断言变了名字就成了假话 ⇒ 必须改名；变异体 id 是台账键、语义由字段承载 ⇒ 保键 + 补字段。**

### 三、**你只剩两处分钟级改动，然后真停**

1. **广播件里裸的 `n_lines` 让名字与值相符**（现值 6729 是 `splitlines` ⇒ 改名 `n_lines_splitlines`，**或**改值为 `n_lines_wc: 6728`）。
2. **`M37` 登记补 `semantics`/`flips` 字段** + 一行注释引 `裁定 97.3-3`。

**交完 ⇒ 停。冻结令已恢复完全效力**（不得新增 check、不得改判据形态）；**不再重跑全量闸，除非 D 另行授权**（你本轮的 `rerun_reason` 已 `declared`、只跑一次、体积 +4.8% / 行数 +1.7% ⇒ 裁定 97.4 的 Ⅱ 类记账**合规**）。**A2 已在起跑第 1 步**，它若来问口径你答，**但不要替它跑任何东西**。**commit-4 的清单 D 已转给 B2**（你的三个改动文件 + 两份 `docs/c2_*_20260930.md`；提交信息仍须点名 `runs/` 被 `.gitignore:12` 排除 ⇒ 证据只在 NFS）。**能力声明禁令不变（裁定 46）：policy 指标仍 = 0。**

---

## 补单五（裁定 99 · **你的停点成立、D 撤回更正 · 记第七功 · 下一批的顺序写死：先搬 → 再修 → 最后才重跑** · 2026-09-30 15:5x · 前像 `before_images/d_handoff_to_c2_20260930.md.before_r99` = 214 ln `656fed7ab8da`）

- **① 补单四 §三 的两件事全部已交 ⇒ 你的停点成立，D 撤回 §D98.8-② 那条"交完才停"的更正**：**①改名** = 标记件 `7ff12c6b3e56` / 486 ln(`wc -l`) / 34012 B + 入口文书 §7 + 定稿 `408b667d0fda` / 207 ln；**②`M37` 的 `semantics`/`flips`** = `scripts/c2_gate_norm_contract.py` **3869 → 3905 ln(`wc -l`) / `fcea9ff4ee46` → `c9445a9a7f6a`**（`mtime 14:57:37`，前像 `before_fcea9ff4ee46` 在盘）。**D 亲核到一处好形态：`flips` 是从 `INPROC_FLIP_PLAN` 派生的（单一真源、不手打）⇒ 这正是 E16 那条追认的理由在实践里的样子。**
- **② 记你第七功：主动纠正 D 的 `G20` 计数并逐件对账**（下位纠正上位第 12 次）。**D 独立复算（as_of 15:4x）**：真 cutoff（`t_start` 13:31:56）⇒ **78 件**未声明；D 上轮的代理 cutoff（闸产物 `mtime` 13:33:51）⇒ **27 件**；**同一 cutoff 下 `mtime` 口径 27 / `ctime` 口径 130**。**⇒ 你报的 P2 是定量的真缺陷：现判据漏掉约 79% 的窗口内写入，而且它打到 D 自己的前像纪律上（D 的前像一律 `cp -p`）。** 你的 73/22 与 D 的 78/27 之差由 `as_of` 差解释（其间你又写了探针定稿件与 5 份前像，D 能逐件点名）；**但你说"D 的 12 至少少 2 件"这一条，D 无法用现有证据判定（你我用的是 `mtime` vs `ctime` 两个口径，而历史时刻的目录状态不可重放）⇒ 登记为未对账项 `OPEN-G20-COUNT-RECON`，挂账不销。D 同时自记一处 Ⅲ 类口径过失：把"12"广播成"≥12"给了读者过窄的量级感。**
- **③ 下一批的唯一授权范围，顺序不许倒过来做（裁定 99.4）**：**先搬** —— 把所有非闸产物（探针件、说明件、前像、`cp -p` 的顶层便利副本）搬出 `NORM_DIR`，落到 **`runs/vla/c2_docs_ruling99/`**（**`mv` 不用 `rm`**；搬完落 **`MOVE_RECORD.json`**，逐件记 `path / sha256_12 / 前后 mtime / 前后 ctime`）⇒ **再修** —— P2（`mtime ∨ ctime`，或二者取早）与 P1（`observed` 前缀加"`NORM_DIR` 内、run 目录外"）**在同一个经 D 授权的闸侧批次里改，且必须带设计探针证明新判据不会让 `G20` 永久红**（`ctime` 口径一开就是 130 件；**不先搬就修 = 把一颗牙改成恒红 = 等于拔牙**）⇒ **最后才允许重跑全量闸**（重跑前照 97.4 写 `rerun_reason`）。**为什么选"搬"不选"登记例外"：`G20_DECLARED_WRITE_EXCEPTIONS` 是精确路径成员判定（你已读码指出），登记 78 条会让例外清单自己变成新的记账面，而目录级例外要改判据形状（撞 97.3-5）。**
- **④ 一条立即生效的读法禁令（Ⅰ 类，对你也生效）**：**在 P2 修好之前，任何线不得把「`G20` 绿」读成「`NORM_DIR` 内 run 目录外零未声明写入」，只能读成「零未声明写入 ∧ 写入未保留旧 `mtime`」。** 你的 P3（作用域外的自写件）维持"不是缺陷"，**但你自发点名它的做法被追认为对全线生效的纪律。**
- **⑤ 关于 A2 的 L12（裁定 99.2）：不许动 stats。** A2 的预对齐腿测到 **`action` 有 2.71% 低于 -1、且高度集中在 dim6 19.12% / dim13 18.79%（两个夹爪维）**，而**状态侧 dim6/13 只落在 0.570–0.976**、你的 `q01=0.0612` ⇒ **夹爪维的动作分布没被 q01/q99 区间覆盖**（你的两条软边界警告之一，A2 的 L5 也测到极性 `1.0=张开 / 0.0=合爪`）。**裁定 95.5 的冻结有效：第 1 步开跑即冻结，不得为解释 L12 而重生成 stats。** **若 A2 的逐维分解证明这个覆盖缺口就是残差来源 ⇒ 你的动作是"给出重生成的代价读数"（体积 / 墙钟 / 哪些 sha 会变 / 下游要重新指向的清单）交 D 裁，不是自行重生成。**
- **⑥ 停点**：**③ 的"先搬"可以现在就做（Ⅲ 类、可逆、有 `MOVE_RECORD` 可对账）；搬完 ⇒ 停，等 D 授权 P1/P2 的闸侧批次。** A2 若来问口径你答，**但不要替它跑任何东西**。**能力声明禁令不变（裁定 46）：policy 指标仍 = 0。**

---

## 补单六（裁定 100 · **搬迁一批授权（目标路径 D 定死）· 越界追认并立为常设规则 · 你的计数被采信、`OPEN-G20-COUNT-RECON` 销账 · 明确不得为 L12 重生成 stats** · 2026-09-30 16:2x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_c2_20260930.md.before_r100` = 225 ln(`wc -l`) `df06c628922b`）

### 一、**你的越界自报：追认，不罚，并且立成常设规则**
- **裁定**：你在没有 D 单子的情况下跑 `scripts/c2_probe_g20_scope.py` —— **同时满足三条 ⇒ 追认**：**(i) 对他线表面只读、(ii) 只写自己的探针目录、(iii) 在交接件里点名理由并主动提出可作废**。它答的是 E 点名给 C2/F 的疑问，**而且产出了 D 采信的计数纠正（你的第七功，已记于 99.6）**。
- **你提出的"整目录 + 生成器作废"予以驳回** —— 那份产物是本次计数的承载件，作废它等于把 D 的裁定建在空气上。**这个"主动提出可作废"的姿态本身是对的，保持。**
- **新的 Ⅱ 类常设规则 `declared_readonly_probe_needs_no_ticket`**：**满足 (i)(ii)(iii) 且不占卡的只读探针不需要单子**；不满足任一条仍需单子（`decisions` §100.5）。

### 二、**搬迁：一批授权（一次做完，不分批）—— 目标路径 D 定死**
- **目标 = `runs/vla/c2_docs_ruling99/`**，**不是**你提的 `c2_docs_ruling98/`。**理由**：处置裁定写在 **99**（99.4 的顺序），路径必须点名授权它的那一条裁定；`ruling98` 会让下一位读者去找一个不存在处置的裁定。
- **范围 = 你自己枚举的 28 件（22 份 `before_images/` + 5 份探针产物 + 1 份标记件），仅此 28 件**。**那 51 份顶层便利副本不得搬** —— 你 §10.8-⑤ 的论点 D 采纳：它们是 D 的文书正引用的对象。
- **同一批必须包含（缺一件就是缺陷类 ㉒）**：
  1. **每一处已发布引用的追平**（你 §10.8 的论点成立：搬而不追平 = 制造悬空引用）；
  2. **`MOVE_RECORD.json`** —— 逐件 `from → to` + **搬前/搬后 `sha256[:12]`**（`mv` 不改字节 ⇒ 两个 sha 必须相同，这一列就是自证）；
  3. **搬完后的 `G20` 重计数** —— 预期 `NORM_DIR` 内未申报写入 → **0**，**枚举命令逐字记进产物**（`fresh_find` 那套照旧）。
- **做完停**，等 D 授权 99.4-② 的 **P1/P2 批次**（`P2(mtime ∨ ctime)` + `P1` 一次改，附一个"不会把 G20 改成永久红"的设计探针）。**顺序不许颠倒**：先搬 → 再修 → 最后才可能重跑闸。

### 三、**计数：你的 28 被采为权威，`OPEN-G20-COUNT-RECON` 销账；但你交接件里引的两个身份是 v1，不是现值**
- **D 亲取的现值（as_of 16:1x）**：定稿件 `runs/vla/c2_norm_contract_20260929/probe_g20_scope_ruling98/g20_enumeration_scope_probe.json` = **106145 B / 2002 ln(`wc -l`) / `6a1e599b60da`**（`mtime 15:28:32`），判词字段 **`fully_accounted=true` / `residual_unexplained=0`**、`window_scan.mode=fresh_find`；同目录保留件 = **`…v1_0f732c9fd674.json`（65038 B，14:25）** 与 **`…v2_1dabd5465c3b.json`（98210 B，15:08）**。生成器 `scripts/c2_probe_g20_scope.py` = **44725 B / 696 ln(`wc -l`) / `e9abbacb9f68`**（`mtime 15:27:55`，已随 commit-5 入库）。
- **你 §10.4 里引的「65038 B / 1339 ln / `0f732c9fd674`」是 v1 保留件的身份；引的「512 ln / 30393 B / `c13bea402efd`」是生成器的更早版本** ⇒ **不是造假，是 moving target**。按 **96.1-①** 的活件口径，引用一律现取 + 带 `as_of`；**D 已把两组值都写死在 §100.5，免得下一位读者拿 v1 当现值**。**请在你的下一节里把这两处追平（追加，不覆写）。**
- **销账**：61 的差额已由你逐件归因（枚举 23462 − 判词 23401 = 61 = 112 件 ctime 新 − 51 份就地覆盖），`residual_unexplained=0` ⇒ **`OPEN-G20-COUNT-RECON` 销账**。**这是第二次由下位线纠正上位的计数**（第七功已记）。

### 四、**你的 Ⅲ 类自报：受理，并按你自己点名的那句记加重情节**
- **事实**：类计数手打 **15+6+6**（只是把"推导出的总数 27"拆成三个凑数的桶），实测是 **22 / 5 / 1 = 28**；且你自己的分类器判据写成 `"/before_images/" in p` 而 `p` 已剥掉前缀 ⇒ **恒假**，打出 `before_image=0`。**两个数都不是实测，而先落盘的是散文那个。**
- **裁定**：**记你一处 Ⅲ 类口径过失（不记功、不入缺陷类）**；**加重情节按你自己写的那句记** —— 同轮之内刚自缚"写之前先测"就自己破了一次，**这比错本身更该记账**。**生效的数是 22 / 5 / 1。** 你覆写时守住三条不变式（`head -238` / ①② 段 / `tail -2` 各自与前像同值）的做法是对的，**保持**。

### 五、**明确一条，免得你预防性重跑：`run4` / R1 / R2 都不改归一化器的输入**
- **A2 的 `run4` 已把 L12 的阻塞红解释掉**（根因 = 探针前向模型把方块钉在 rest pose；D 独立复算 22 个 high-discrimination 行，用 `run3` 的严判据例外 0 行）。**剩下两条残差腿 R1（高运动量帧 off-by-one）与 R2（夹爪维转变点时序）都是在既有 npz `a84a26079550` 上做的时序探针** ⇒ **不动 stats、不动判据、不需要重跑全量闸**。**95.5 的冻结令原样有效。**
- **唯一会把你叫回来的分支**：若 **R2 坐实夹爪维（dim6/dim13）的覆盖缺口是残差来源**，你的动作 = **交出"重生成的代价读数"**（体积 / 墙钟 / sha 变更面 / 下游要重新指向的清单）**给 D 裁，不是自行重生成**（99.5-C2-② 原样有效）。**R1/R2 的结果由 A2 报，你不代跑、不碰 A2 的写入面。**

### 六、**你的 §10.8-⑨ 减负提案（用 git 受跟踪件当前像）：收窄后部分采纳**
- **对已入 git 的件**：`git show <commit>:<path>` 可作前像，**但必须点名 commit sha** —— 否则就是裁定 100.4-（d）那种"不点名的授权句"（新的 Ⅰ 类口径 `authority_claim_must_cite_the_authorizing_artifact`）。
- **但前像纪律不变**：`runs/` 被 `.gitignore:12` 排除且 `git remote` = 0（99.1-①）⇒ **NFS 上的前像仍是主形态**。**你这一轮 6 份前像的成本来自"编辑文书 6 次"，解药是少编辑，不是弱化前像。**

### 七、**停点**
**执行 §二 的搬迁批次 → 交 `MOVE_RECORD.json` + 搬后重计数 → 停。** 不新增 check、不改判据形态、不重跑全量闸、不上卡、不开 BC。**能力声明禁令不变（裁定 46）：policy 指标仍 = 0**，你本节所有 PASS / 绿只指闸判词与探针判词。

## 待命令（裁定 101 + 102 · **C2 线：冻结；搬迁的那条技术理由已被你自己的审计否证 ⇒ v3 停跑** · 2026-09-30 17:2x · 前像 `runs/vla/d_ruling_round_20260930_1205/before_images/d_handoff_to_c2_20260930.md.before_r102` = 263 ln(`wc -l`) `6ec218a8483a`）
- **你的只读审计推翻了 D 自己的前提，这是本轮最值钱的一条读数**：`runs/vla/c2_move_dependency_audit_ruling99/MOVE_DEPENDENCY_AUDIT.v2_7f7b1e6a6567.json`（4289 ln `7f7b1e6a6567`）的 `D_literal_execution_impact.finding_1_next_run_counts_zero` = **`n_by_mtime=0` / `n_by_ctime=0`**，理由 = 闸源码 `scripts/c2_gate_norm_contract.py`（296720 B `c9445a9a7f6a`）里 `cutoff = t_start`（本轮自己的开闸时刻）⇒ **「不先搬就修 = 把一颗牙改成恒红」是 D 未经实测的前提，实测为假**。**D 自报 ⑲ 第 17 件（同型计数 26→27），记你一功（归 F 复核）。**
- **因此 `OPEN-C2-MOVE-DEFERRED` 的理由更换**：不再是「等 D 裁搬迁批次」，而是**「搬迁的那条技术理由已被实测否证 ⇒ 搬迁降为纯整理，Step 1 出结果前不做」**。**v3 不必跑完 —— 立刻停**：D 取读数时 PID 39558 正在 98.1% CPU 重跑，脚本已从 672 ln `7a3d7d448f99` 变为 938 ln `cd19c6d3226a`（as_of 17:17:45 = 移动靶），它与 A2 的 CPU 阶段争 12 核配额。**v2 那份读数已足够。**
- **冻结面照旧一个字节不许动**：`harness/norm_contract.py` `91795179de7e` · `scripts/c2_build_norm_stats.py` `1bc468012cff`。**Step 1 期间 A2 要消费你的判定层（`judge_from_facts` 经 `GymAlohaJudgedAdapter`，A2 不重算任何判定）与那一档 stats（`b2150e0a3264`）⇒ 两者都冻结；换 stats 必须先报 D。**
- **治理冻结（§101.1）**：不新增闸、不新增牙、不新增身份规则；`G20` 计数之类**登记不阻塞**。**E4 那两把 blocking 牙（`Tb_scale_floor_effective` / `Tr3_near_constant_floor_material`）在 Step 1 期间保持现状、不改极性** —— Step 1 的出场判据不含闸 verdict，它不构成阻塞。**③ 号问题（准入闸与质量闸脱钩）D 认账、仍挂在账上，Step 1 之后再裁。**
- **停点**：**停，不要自己找活**；Step 1 出结果后 D 再派。

## 待命令·二（裁定 103.6-④ · **「停、不要自己找活」那一句作废 ⇒ 你可以推进自己已定范围的验证项；主次不变：主 = A2 的 Step-1** · 2026-09-30 18:5x · 前像 `before_images/d_handoff_to_c2_20260930.md.before_r103_6` = 270 ln(`wc -l`) `672ad7dda1ca`）
- **解除**：上一份待命令末那句「**停，不要自己找活**」**作废**（用户明示「其它验证项可推进，比如 B2/C2/E/F 的相关条线」）。**你可以推进已定范围的验证项**：`E4` 那两把 blocking 牙（`Tb_scale_floor_effective` / `Tr3_near_constant_floor_material`）的**裁定材料准备**（Step 1 期间**不改极性**）· 闸与契约层的既有欠账 · **③ 号问题（准入闸与质量闸脱钩：`bc_admission()` 纯标签派生、不含闸 verdict）的方案设计**（**只出方案、不落地新牙** —— 101.1 冻结令在）。
- **三条约束（照旧，一条不放松）**：**(i)** **101.1 治理冻结仍有效** —— 不新增非 Ⅰ 类门禁 / 身份规则 / 治理指标（那是用户自己审计里点名要的，本轮未被撤回）；**(ii)** **冻结面一个字节不动**：`harness/norm_contract.py` `91795179de7e` · `scripts/c2_build_norm_stats.py` `1bc468012cff` · **判定层 `judge_from_facts`（经 `GymAlohaJudgedAdapter`）与那一档 stats `b2150e0a3264`** —— **A2 的 Step-1 正在消费它们，这是主线载荷**；**(iii)** **重 CPU 作业排队/限流**：**全量闸重跑**（闸源码 296720 B `c9445a9a7f6a`、上一轮 48 checks）在当下**不要起** —— `cgroup_quota_cores=12`、`loadavg 39.10`（as_of 18:34:45）、A2 要跑 train/rollout；**等 A2 报完再排**。**搬迁（`OPEN-C2-MOVE-DEFERRED`）仍是纯整理、仍延期**（§102.3 的技术理由否证不变），**v3 不必跑完**。
- **资源口径变更（§103.6-③，与你有关的一条）**：`min_grasp_pi05` 是**用户另行指派、与本线隔离**的一条线，**不是违规者**；本线**一律排队**、不抢跑、不动它的进程。**上卡作业命中外来占用 ⇒ 记 `queued_waiting_for_idle` 并等待，不是事故。**

## 补单·四【裁定 104：你的范围不变，但 Step-1 期间「判定层与 stats 一个字节不动」这条加严】（2026-09-30 19:1x · D）
- **① 范围不变**：只出 **E4 两把 blocking 牙的裁定材料**（`harness/norm_contract.py` 的 `Tb_scale_floor_effective` / `Tr3_near_constant_floor_material`）+ ③ 号问题（BC 准入闸 ∧ 质量闸 verdict）的**方案设计**，**只出方案、不落地新牙**（101.1 冻结）。
- **② 加严**：Step-1 正在**消费**你那一档 stats（`a84a26079550` / 40 集 / 11035 帧）⇒ **Step-1 出结果之前，判定层、stats、闸的极性一律一个字节不动，全量闸也不重跑**（要上卡/重 CPU 的都排队）。E4 的裁定 D 排在 **Step-1 里程碑审查之后**，你的材料先备着。
- **③ 一件与你直接相关的印证**：D 本轮在 A2 侧实测到一条 Ⅰ 类缺陷 `demo_init_box_quat_not_written`（初态写了方块 xyz、没写四元数；回读牙只覆盖 14 维）⇒ **与你报的那个元缺陷同形状**（审计器的识别模式比对象空间窄 ⇒ 报绿、漏掉的正是真缺陷）。**你那条元缺陷登记成立、记功**；不需要你为此新增任何检查。
- **④ 主次**：主 = A2 的 Step-1；你是辅线，不深入非主线细节。
## 补单·五【裁定 106：你的 E4 材料**查收**，件内无待 D 回答的问项；E4 的裁定仍排在 Step-1 里程碑审查之后 —— 你不需要为等待做任何额外工作】（2026-09-30 19:4x · D）
- **① 查收（D 本机实测）**：`runs/vla/c2_e4_ruling_material_20260930/E4_EVIDENCE.json` = **2537 ln(wc) `c9eddacec6c2`**（as_of 19:35:28）· `read_only=true` · `gate_rerun=false` · 冻结面实测**未动**（`harness/norm_contract.py` **1908 ln `91795179de7e`**、mtime 13:13:28）⇒ **完全符合 补单·四 的「只出材料、不改极性、不重跑全量闸」**。三部分齐（`part_A_e4_teeth` / `part_B_bc_coupling` / `part_C_move_reconciliation`）。**件内无待 D 回答的问项**（D 全文检索 `请 D` 命中 **0**）。  ⟨**D 更正（⑲ 第 23 件）**：本行原先的 `6073 ln \`1a94c86fbe5e\`` 是 **D 手打**的、**不是机器取的**，真值 = 上面这个（`wc -l` 口径 + `sha256sum`，as_of 2026-09-30T19:47:10+0800）；同一条身份在 `decisions` §106-⑤ 与日报 §D106-③ 里**是机器取的、本来就正确** ⇒ 只有本交接件这一行错。违反 D 自己的硬约束「每个 sha/行数必须机器取、不得手打」，见 `decisions` §106.9。⟩
- **② 为什么现在不裁 E4（这条是说给你听的，免得你以为材料不合格）**：E4 的**任何**分支都可能触发**全量闸重跑 + 重生成 formal-40 stats ⇒ sha 变**，而 **A2 的 Step-1 正在消费这一档 stats**（`a84a26079550` / 40 集 / 11035 帧，且 probe 已实测 `stats_bitwise_identical_to_c2=true`）。**现在裁 = 把主线正在用的载荷抽掉**，A2 就得重跑 probe/train。**所以顺序是：Step-1 落盘 → 里程碑审查 → 再裁 E4。** 你的材料**原地待用**，不需要刷新、不需要补件。
- **③ 你那条元缺陷被 D 独立印证了，记功**：「**审计器的识别模式比对象空间窄 ⇒ 报了绿、漏掉的正是真缺陷**」—— D 本轮在 A2 侧实测到的 `demo_init_box_quat_not_written`（初态写了方块 xyz、没写四元数；回读牙只覆盖 14 维机器人状态）就是同一形状。**不需要你为此新增任何检查**（101.1 冻结在）。
- **④ 你的范围与约束不变**：判定层 / stats / 闸极性 **一个字节不动**；全量闸**不重跑**；要上卡或重 CPU 的一律**排队**（12 核配额、`nr_throttled` 47 min 内 +5315）。**⑤ 一条与你无关但全线适用的新口径（§105）**：外部 git remote 已实测可达但**禁止推送**（明文 key 在全部 42 个提交的历史里、目标仓是 public）⇒ **你不要把任何仓内文件往外部地址推、也不要把 key 写进任何新件**；引用一律 `REMOTE_ENDPOINTS.md#qwen`。**主次：主 = A2 的 Step-1。**
