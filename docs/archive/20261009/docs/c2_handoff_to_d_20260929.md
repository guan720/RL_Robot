# C2 → D 回流单（覆盖 2026-09-29 20:3x – 2026-09-30 01:1x；落盘 01:1x）

> **交这份的理由**：裁定 79.5 / D 执行单 §12-5 / §13-4① —— C2 是四条线里唯一欠交回流单者。
> **写入面**：`docs/c2_*.md` + `runs/vla/c2_*` / `runs/infra/c2_*`（本文书在自己的写入面内，未改他人文件）。
> **引用规则**：本文所有 sha256-12 **由 `scripts/c2_cite.py` 在落笔时刻重读**（回应 §13-3 的"做成函数、不要靠自觉"），
> 每条带 `as_of` mtime；身份表见文末附表。**本线已两起同型事故，不再靠自觉。**
> **状态词**：本文不使用裁定 54.1 禁用的那三个词（见 `work/decisions/decisions_20260929.md:1170`），只用 v4 五档：未实施 / 已实现未验证 / 回放通过 / 仿真通过 / 真机通过。
> **负载口径**：每个吞吐/耗时数字都成对带 `loadavg` + `nr_throttled`（分母 = cgroup 12 核）。

---

## §0 一句话状态

T-C2-1 的**工具面**（生成器 + 契约层 + 闸 + 9 个变异体）= **仿真通过**（CPU/osmesa，无 GPU）；
T-C2-1 的**交付物**（主线 stats）= **未实施**，阻塞在 B2 的 S1 先导 5 集 `states_14d.npz`（裁定 52/69），
**C2 三次拒绝用 `env_derived_diagnostic` / `yam_abc130k` 顶替**（`mainline_status.json` 的 `refused_to_substitute`）。
本轮新查出 **8 个缺陷**（契约层/生成器 5 + 采集器 3）并全部修正；闸从 25 checks 扩到 **27 checks、0 red**，
且**每条 check 都有"哪个变异体让它红"的实测翻转台账**（19 条记录）。

---

## §1 对 D §14-8 欠账表的逐条回应（七项）

| # | D 的欠账项 | C2 的现状 | 证据 |
|---|---|---|---|
| ① | `docs/c2_handoff_to_d_20260929.md` | **本文书 = 交付** | 本文件 |
| ② | 审计勘误行（裁定 78.11，`387f78e2c49f` → `6c4d71eb732e`） | **已交，D 的表过期**：勘误 §9 于 **23:37:30** 落盘（早于 §14 的 00:0x） | `docs/c2_gate_polarity_audit_20260929.md:264`（285 ln / `768d49409d76`）；详见 §4 |
| ③ | `matrix.json` 的 generator sha 勘误（裁定 82.6） | **以重生成方式闭合**（D 已销账）；本文点名以免后人误读 23:25 那份 | 详见 §4.2 |
| ④ | T-C2-1 主线 stats | **未实施**，阻塞在 B2 的 npz；处置口径按 §14-6 已接受 | `mainline_status.json`（`705eb071b54e`） |
| ⑤ | T-C2-3 / T-C2-5 | **两项都未落盘**，状态见 §3；**并且 C2 主动报一条债**：78.9 D3 引的 KB/帧数字目前只活在散文里（见 §13.2） | §3 / §13.2 |
| ⑥ | `env_gym_aloha.py` 三条硬约束（裁定 62） | **未实施**，按 §14-7 排在 ④ 之后，**不插队** | §15 |
| ⑦ | T-C2-6 | **未实施**（裁定 49.4 暂缓）；已按 D 要求写成「待触发」记录，不变沉默缺口 | §11 |

---

## §2 覆写账本：**`n_events=4`，不是 D §12-5 记的 2**（D 的表写在 23:0x，账本 23:13:18 又加了两条）

**指针**：`runs/infra/c2_overwritten_c_artifacts_20260929/index.json`（85 ln / `586613978a33` / as_of 23:13:18），
逐事件 registry 在 `events/<label>/registry.json`；守卫自检在 `selfcheck/`。

| 事件 | 分类 | 守卫 | n_files | 根因（账本原文摘） |
|---|---|---|---|---|
| `event1_20260929_2142` | `violation_unguarded_overwrite` | **未接** | 16 | 驱动只改指 `c_env_manifest` 一处，其余自检脚本写死 `runs/infra` 固定路径（裁定 68 §10.2 的根因） |
| `event2_20260929_2233` | `violation_unguarded_overwrite` | **未接** | 16 | C2 写 `WHY_BEFORE_IMAGE.md` 用了**未加引号的 heredoc**（`<<EOF`），正文里的反引号被 bash 当命令替换执行 ⇒ 意外把驱动脚本本体又跑了一遍 |
| `event3_20260929_2244` | `guarded_regression_no_net_change` | 已接（v1） | 0 | 守卫 v1 已复原 16 个声明路径，但扫描面只有 `maxdepth=2` ⇒ 漏掉 depth≥3 的 730 个新文件；搬迁规则过宽 |
| `event4_20260929_2300` | `guarded_regression_no_net_change` | 已接（v2） | 16（**净零**） | 守卫 v2 = 全深度 stat 索引 + 只搬"直接命中"路径 ⇒ 16 个文件被写但逐个复原，净变更 0 |

**整改状态**：守卫版驱动 `scripts/c2_driver_output_guard.py`（417 ln）+ 自检 4/4 ⇒ **D 已于裁定 79 判定「闭合」**；
根因升为红线级纪律 `regression_driver_output_enumeration`（裁定 79）。
**C2 侧的补充事实（诚实登记）**：event3 的 `verdict_set_crosscheck=RED` —— 守卫 v1 那次**交叉核验是红的**，
不是全绿；event1/2/4 为 `PASS`。这条不影响 D 的闭合判定（闭合的对象是"未申报覆写"这个形态），
但账本里它红着，C2 不把它抹成绿。

---

## §3 T-C2-1 … T-C2-6 逐条状态（v4 五档状态词）

| 任务 | 状态词 | 依据（产物 / 裁定） | 未完成的部分 |
|---|---|---|---|
| **T-C2-1** 归一化契约层 | **工具面 = 仿真通过**；**主线 stats = 未实施** | 生成器 `scripts/c2_build_norm_stats.py`（637 ln / `90d6254ba7af`）+ 契约层 `harness/norm_contract.py`（667 ln / `2f34a9344441`）+ 闸 27 checks 0 red（§7）；裁定 69 的两份提案并行、两族四档下限、`coef_status=proposed_pending_s1` 全部在 `matrix.json` 里 | 主线 stats 等 B2 的 `states_14d.npz`；`clip_ratio_cap` / `coef` 的**最终值**待 S1 定标（现为提案） |
| **T-C2-2** obs 键白名单 | **仿真通过**（D 已验收，裁定 68） | +17/−1 additive、`contracts.py` 未触、14 checks 0 red、4 变异体极性正确、C 线回归 17/17 | `late_policy=hold` 那颗牙**未实施**（见 §13.1） |
| **T-C2-3** 重复帧 + `obs_store` 图像容量 | **未实施（无产物）** | —— | 全部。**并且：78.9 D3 引的 `1765.19 / 2701.04 KB/帧` 是 C2 的口述实测，C2 写入面内无任何产物支撑 ⇒ 按 D 的口径它现在是 `declared_only`**（§13.2） |
| **T-C2-4** 闸极性审计 | **仿真通过**（D 已接受，裁定 78；§12-1 认定"自审是本轮最有价值的部分"） | `docs/c2_gate_polarity_audit_20260929.md`（285 ln / `768d49409d76`）：两起假红独立复核成立（B2 的 `G2_rebuild_lockout_not_default[a2env]`、torch `2.6.0+cu124` local tag）+ 裁定 72-2 的三个新审点 | 审计是**文书**，不含可重跑的闸；三个新审点已并入本线闸的判据（§7） |
| **T-C2-5** A 线冻结时产物清单 | **未实施** | —— | 全部（被 T-C2-1 挤占；纯只读汇总，随时可做，等 D 排） |
| **T-C2-6** `registry/` 多门禁并存 | **未实施**（裁定 49.4 暂缓，C2 不主动动） | 「待触发」记录见 §11 | 全部 |

**附：`harness/env_gym_aloha.py`（579 ln / `6c4d71eb732e` / as_of 22:09:11）= 仿真通过**
（offline 15 checks / online 13 checks，`verdict=PASS`、`red=[]`；**D 于 22:52:32 独立复跑并接受**，§12-2）。
裁定 62 的**三条硬约束尚未实现**，按 §14-7 排在主线 stats 之后。

---

## §4 两处勘误的自证（§12-4 / §13-3）

### 4.1 裁定 78.11（D §12-4）：审计文末勘误行 —— **已交**

`docs/c2_gate_polarity_audit_20260929.md:264` 起为 **§9 勘误（append-only）**，原文 1–260 行一字未改
（追加前 260 ln / `8ea4fb4ad518`；追加后 **285 ln / `768d49409d76`** / as_of 23:37:30）。D 要求的四项逐条落到：

| D 的要求 | 勘误里的位置 | 内容 |
|---|---|---|
| `387f78e2c49f → 6c4d71eb732e, as_of mtime 22:09:11` | `:268`（E1 行） | 并写明"落笔 22:07:14、写完 2 min 后文件被改 ⇒ 所引 sha 已不在磁盘" |
| `n_checks: offline 15 / online 13` | `:269`–`:270`（E2/E3 行） | 原文 `14/14`、`9/9` 一并标为过期计数 |
| `D 复跑时刻 22:52:32 / verdict=PASS / red=[]` | `:271`（E4 行） | 并注明 D 用的是当前 sha `6c4d71eb732e` |
| 纪律接受 | `:279`–`:285` | 接受 `citation_sha_as_of_discipline` 为红线级；并写明 C2 侧对策：**凡引用 B2 的 S1 产物做 stats 源，一律在读取时刻重算 sha 并写进 `provenance`，不抄旧值** |

**⇒ 请 D 把 §14-8② 从「未交」改为「已交」**（C2 不代改 D 的文书）。

### 4.2 裁定 82.6（D §13-3）：`matrix.json` 的 generator sha —— **以重生成方式闭合**

D 记的过期链 `99159100eb59 → faf7cfc6ccd4`（as_of 23:25:16）**没有被 C2 用勘误行修**，而是**重跑生成器**：
23:55:00 版记 `fcfb72a88c92`，00:34:47 版（当前）记 **`90d6254ba7af`** —— 每一版都与当时的磁盘逐字一致
（D 于 §14-1 已实测确认 23:55 那版一致并销账）。
**C2 在此点名**：`runs/vla/c2_norm_contract_20260929/matrix.json` 的 **23:25:00 版**（generator `99159100eb59`）
**已灭失不可追**（该文件是被重生成覆盖的，C2 当时未留前像）⇒ **后人不得引用 23:25 那份的任何数字**；
可引的最早版本 = 23:55:00，当前版本 = **00:34:47 / `c10541f9f532`**（见 §8 的 superseded 旗标）。
**教训已落地为工具**：`scripts/c2_cite.py`（§12.2）。

---

## §5 自审 4 次缺陷（3 假红 + 1 假绿）的留档指针

D §12-1 认定的"本轮最有价值的部分"，逐条在 `docs/c2_gate_polarity_audit_20260929.md`：

| 编号 | 形态 | 位置 | 结论 |
|---|---|---|---|
| C2-1 | **假红** | §3 | B2 的 `G2_rebuild_lockout_not_default[a2env]`：期望条件已满足（`same_as_0928=false`、`lock_diff` 已逐包枚举）却报 WARN |
| C2-2 | **假红** | §4 | torch 红线值本来就是 `2.6.0+cu124`，把 `+cu124` 这个 local tag 差当"漂移"⇒ 假红 |
| C2-3 | **假红** | §5 | 本线 env 闸自己的 J14（边界语义）/ J15（秒口径）判据错位 |
| C2-4 | **假绿** | §6 | `harness/queue_td_learner.py:134` 图像键被**静默跳过**、而宽度检查照样通过 ⇒ 观测缺失却不红（T-C2-2 的直接来源） |

**两起假红已独立复核成立并被 D 采纳（裁定 78）；假绿已由 T-C2-2 的补丁闭合（裁定 68 验收）。**

---

## §6 本轮（23:0x–01:1x）新查出的 8 个缺陷与修正

> **方法**：全部由**变异体**逼出来，不是读代码读出来的。每个缺陷都先造一个"缺陷形态"的变异体，
> 确认闸**不红**（= 牙是恒真的），再修，再确认闸**红**。

### 6.1 契约层 / 生成器（5 个）

| # | 缺陷 | 后果（若不修） | 修法 | 证明它的变异体 |
|---|---|---|---|---|
| 1 | `build_case()` 的 IDENTITY 分支 `np.clip(center, lo+need/2, hi-need/2)` 在 `need > hi-lo` 时**界反转**（`a_min > a_max`，numpy 取 `a_max`） | `Tc_start_pose_coverage` 恒红 ⇒ **假红**，而且红得看起来像数据问题 | 界反转时改用覆盖区间中点 `(lo+hi)/2`；界不反转时逐字不变（既有 PASS 行不漂移） | `mutation_no_widen`（25 行全 RED） |
| 2 | `near_constant_dims()` 读 `span_q99_q01`，而 build 侧在 `widen_to_cover()` 之后**把展宽后的 span 写回同名键** | 覆盖头寸混进"这一维几乎不动"的判据 ⇒ hold 相 10 个下限绑定维**一个都不被判为近常量** ⇒ `Tr1` 的 `unprotected=[]` **恒成立** | 改读 `denom_raw`（下限烘入前、展宽前的原始分位距），缺失时回落 `span_q99_q01` | `M2_near_constant_always_empty` + `--floor-coef-scale 0` 臂 |
| 3 | 近常量标记阈值 `1e-3` **低于数据最小值** `1.648e-3` | 标不出任何维 ⇒ 同一颗牙第二种恒真形态 | 单一来源 `NEAR_CONSTANT_REL_TOL = 0.02 = min(F1_CANDIDATES)` + 载入期 assert（与下限公式同源，不许两处各写一个数） | 同上 |
| 4 | `stats_payload()` 对 IDENTITY 档**重算** center/gain | **落盘 ≠ 被判**：交付物可以和被验的东西不是同一份 | 新增 `roundtrip_from_payload()` + 逐行 round-trip 复算（25/25 一致） | `M3_payload_recompute_identity` |
| 5 | `physical_range` 采集器三处（见 6.2） | F1 下限与近常量标记的**分母**错 | `scripts/c2_fix_physical_range.py`（Tp1–Tp4）+ 采集器根因修正 | `M4_collector_inline_qpos_formula` |

**缺陷 2 与 ACT 线的致命事故同族**（`(x-mean)/(std+1e-6)` 对近常量维无下限保护 ⇒ 闭环输入冲到 20402、
94% 帧越界、离线 MSE 全程看不见）。那次是事后花一整天定位；这次在 P1 BC 开跑之前变成了一把有牙的闸。
**D 已认定这是本轮全线最高价值发现（裁定 83），并据此新立红线 `tooth_must_be_mutant_proven`。**

### 6.2 `physical_range` 采集器（3 个，`correction.json` 1137 ln / `03df905d880a`）

| # | 缺陷 | 实测 | 牙 |
|---|---|---|---|
| 6 | 右臂 qpos **off-by-one**：实现用 `state_dim + 2`，声明映射 `ARM_QPOS_IDX` 要求 `state_dim + 1` | `per_dim[12]`：`qpos_idx_old=14` → `qpos_idx_new=13`（`vx300s_right/wrist_rotate`）；dim12 旧行程取到**手指滑动关节 0.036**、新值 6.28316 ⇒ **差 ~175×** | `Tp1_declared_mapping_equals_implemented`（AST 读实现，不读注释） |
| 7 | 夹爪行程**假设为 1.0**，未过 upstream 归一化 | 实测 `state_travel = 0.910010`（dim6 / dim13，旧值 1.0 ⇒ **−9.00%**） | `Tp2_gripper_travel_through_upstream_normalizer` |
| 8 | 把 `jnt_range` 当**硬边界** | 手指 qpos 实测 **0.07333 > jnt_hi 0.057（+28.6%）**；`dims_where_observed_exceeds_declared=[2,6,11,13]`；最严重实例 = random 档 dim6 实测 `[-5.8266, 6.9431]` vs 声明 `[0.0647, 0.9747]` | `Tp4_declared_range_is_soft_bound` |

**修正规则**：`physical_range_effective = max(jnt_travel_through_upstream_normalizer, observed_travel)`
（`physical_range.json` / `ef50e89c88ef`）。**帧数据不受影响、无需重采**（`impact` 原文）。
**近常量维集合因此从 7 维改为 10 维**：`[0,1,2,5,6,7,8,9,12,13]`；下限绑定维 = 12 个 `[0,1,2,3,5,6,7,8,9,10,12,13]`。

**Tp3 的极性说明（防误读）**：`correction.json` 里 `Tp3_collected_frames_inside_declared_interval = RED`
而整体 `verdict = PASS` —— 这**不是**极性缺陷：Tp3 带 `counts_toward_ok=false`，
`ok_rule` 原文写明「Tp3 是**关于 env 的实测事实**（软限位），不是本产物的缺陷」。
四颗牙的 `id/ok/status/required/observed/red_when` 六字段齐（裁定 78.2 最小公共 schema 合规）。

### 6.3 floor 家族结论 + **需 D 裁的三个阈值**

`matrix.json` 的 `floor_family_finding`（实测基 = hold 相 300 帧，osmesa CPU 采集）：

| 家族 | coef | 近常量维 | 下限实质无效维 | 下限绑定维 | materiality_ratio 最小 | bins 中位 |
|---|---|---|---|---|---|---|
| F1（coef × 物理行程） | 0.05 | 10 | **0** | **12** | **2.5** | 12.0 |
| F1 | 0.02 | 10 | **0** | 10 | **1.0** | 12.0 |
| F2（coef × 逐步差分 MAD） | 4.0 | 10 | **10** | **0** | **1.1e-05** | 13.5 |
| F2 | 2.0 | 10 | **10** | **0** | **6e-06** | 13.5 |

- **F1 实质有效**（`materiality_ratio = coef/0.02 ≥ 1`）；**F2 实质无效**：hold 相 MAD 最小 `1.881e-07`
  ⇒ coef=2.0 的下限 = `3.76e-07`，比 `0.02×行程` 小约 **5 个数量级** ⇒ `floor>0` 成立（`Tr1` 绿）
  但**实质上没有保护**，且 bins 中位数与"关下限"完全相同（13.5）。
- **C2 的建议**：主线用 **F1**；若要同时防噪声放大，取 `floor = max(F1(coef), F2(coef))` 而**不是**二选一
  （F2 单独用在真正不动的维上退化为 0）。
- **⚠ 需 D 裁①**：`coef` 取 **0.05** 还是 **0.02**？（0.05 多绑 2 维、分辨率代价 = bins 中位 12.0 vs 13.5）
  C2 倾向 **0.05**，但仍标 `proposed_pending_s1`，等 S1 真数据定标。
- **⚠ 需 D 裁②**：`near_constant_rel_tol = 0.02` 由 `min(F1_CANDIDATES)` 单源导出（缺陷 3 的修法）。
  若 D 改 coef 候选集，这个容差**会自动跟着变** —— 这是有意的（不许两处各写一个数），但请 D 确认接受这个耦合。
- **⚠ 需 D 裁③**：`clip_ratio_cap` 维持 **0.01**？结构事实：q01/q99 天然甩掉两端各 1%
  （本线实测 in-distribution `clip_max = 0.0208 ≈ 2×1%`）⇒ **0.01 只有在 `widen_to_cover` 生效后才是可达的**；
  **C2 反对放宽到 0.02 以上**，否则等于把"展宽没做"这件事合法化。修后基线的 must-red 实测：
  `Td2_clip_heldout` 最差维 = **7**、`clip_ratio = 0.356667`、`n_eval = 600`。

---

## §7 闸的当前身份与结果

**身份**：`scripts/c2_gate_norm_contract.py` **1051 ln / `c17b30bae3e8` / as_of 01:09:05**
**结果**：`runs/vla/c2_norm_contract_20260929/gate/run_20260930_010948/gate_verdict.json`
（1572 ln / `4443e4aea7b8` / as_of 01:09:57）：**`verdict=PASS`、`n_checks=27`、`n_red=0`、`n_warn=0`、`n_n_a=0`**，
收尾 `load_pair = {loadavg 26.78 26.05 26.50, nr_throttled 14734, cgroup_quota_cores 12}`。

**9 个文件级变异体全部构造成功并被抓住**（`mutant_construction_isolation`，裁定 78.1：目录已存在 ⇒ 响亮拒绝）：
`M1_non_raising` / `M2_near_constant_always_empty` / `M3_payload_recompute_identity` /
`M4_collector_inline_qpos_formula` / `M5_schema_field_dropped` / `M6_tr3_always_blocking` /
**`M7_stats_source_gate_vacuous`（本轮新增）** / **`M8_heldout_teeth_vacuous`（本轮新增）** /
**`M9_missing_detection_vacuous`（本轮新增）**。每个都带**活对象自证**（子进程写回 `nc.__file__` +
`nc.__c2_mutant_id__` + sha，不是读文件比对）。

**翻转台账（`proof_ledger`）= 19 条记录，14 条 A 类 check 全部有 `flip_measured=True`**：

| 被证明非恒真的 check | 由哪个变异体翻 | form |
|---|---|---|
| G1 / G2 / G5 | `M3_payload_recompute_identity`（G1/G2 另被 M6 翻） | `matrix_predicate` |
| G3 | `M1_non_raising` + **`M8_heldout_teeth_vacuous`** | `matrix_predicate` |
| G4 | `M1_non_raising` + **`M7_stats_source_gate_vacuous`** | `matrix_predicate` |
| G6 | `M5_schema_field_dropped` + `M6_tr3_always_blocking` | `matrix_predicate` |
| G21 | `M1_non_raising` | `matrix_predicate` |
| G9 | `M2_near_constant_always_empty` | `necessary_clause`（M2 只跑 floor_off 臂 ⇒ 只比必要子句，不套整条谓词） |
| G12 / G13 / G14 | `M1_non_raising` | `inprocess_predicate_in_mutant_copy` |
| **G10 / G11** | **`M9_missing_detection_vacuous`** | `inprocess_predicate_in_mutant_copy` |
| G15 | `M3_payload_recompute_identity` | `inprocess_predicate_in_mutant_copy` |

`matrix_predicate` 的实现口径：**闸的判定与"翻转实测"共用同一个谓词函数**（`pred_G1`…`pred_G21`，模块级），
不存在"判定一份、证明另一份"的漂移空间；`main()` 里还留了一条 assert 防止牙清单两处不一致。

### 7.1 **本轮最重要的方法学发现：M1 翻不动 G10/G11 —— "登记文案"果然不等于"有牙"**

C2 原先给 G10（清空 stats ⇒ `Ts` 必须红）/ G11（删 q01/q99 键 ⇒ `Ts` 必须红）登记的变异体是
**`M1_non_raising`**（理由是"M1 删掉 raise，那所有牙都不抛"）。
**01:05 那一跑实测把这个登记证伪了**（`runs/vla/c2_norm_contract_20260929/gate/run_20260930_010545/`，
`verdict=RED`、`n_red=2`、红的是 `G25` 与 `G24`）：M1 副本内 G12/G13/G14 全部翻 False，
而 **G10/G11 仍为 True**。

**根因（读了实现原文才知道）**：`Ts` 有**自己的提前抛**路径 —— `harness/norm_contract.py:424`
`if missing or nonfinite:` → `:427` `raise NormContractViolation(...)`，
**不在** M1 删掉的末尾 `if red: raise` 里。所以拔掉末尾 raise 对 `Ts` 毫无影响。

**处置**：新造 **`M9_missing_detection_vacuous`**（把 `missing = [k for k in need_keys if k not in stats or
np.asarray(stats[k]).size == 0]` 改成 `missing = []`，即 `normalize_processor.py:305-307` 的静默 IDENTITY 形态），
并把探针的 `call()` 扩成也认 **`CRASH`** 这种形态（M9 之下 G10/G11 的实测结果 = `verdict=CRASH red=[]`
⇒ 谓词 False）。**独立预演已确认 M9 精确地只翻 G10/G11、不动 G12–G15**（scratch 副本 `/tmp/c2m9_010935/probe.json`，
`nc_sha256_12=dd3c903eb15e`）。

**为什么这条对 D 有用**：它是 D 的红线 `tooth_must_be_mutant_proven` 与 `redline_provenance_discipline`
（"读了声明没读实现"）**在 C2 自己身上的第一起实例** —— 而且**是被 D 逼出来的机制抓到的**，不是 C2 自查到的。
C2 当天纠错的第 4 次，同型（前三次：31.25 Hz 当契约值、后端钉死 osmesa、transformers 下界）。
**⇒ 若没有 G24 这条元判据，"M1 证明 G10/G11" 会以文书形态活下来，成为一颗看起来有牙、其实恒真的闸。**

### 7.2 M7 / M8 为什么也要新增

同一轮审计发现：G3（8 个 stress 行必须由 `Td2`/`Te2` 咬红）与 G4（YAM 必红行必须含 `Tr2`）
原先也只登记了 `M1_non_raising`，而 **M1 只删 raise、不改变行级 red 集合** ⇒ 这两条同样**没有被任何变异体证明过**。
新增 `M7`（源分级失效 ⇒ `Tr2` 不咬）与 `M8`（`Td2`/`Te2` 恒真 ⇒ held-out 两颗牙被拔）后，
台账里出现了 G3←M8、G4←M7 的实测翻转。**这两颗牙正是 held-out 帧与"主线禁用源"的守门牙**，
恒真了不会有人发现（离线指标看不见，与 ACT 线事故同族）。

---

## §8 superseded sha 旗标（**D §14-5 引的两个 sha 已被取代，请更新引用**）

| D §14-5 / §14-1 引的 | as_of | 现值 | as_of | 状态 |
|---|---|---|---|---|
| generator `scripts/c2_build_norm_stats.py` = `fcfb72a88c92` | 23:49:55 | **`90d6254ba7af`（637 ln）** | **00:25:21** | **superseded** |
| contract `harness/norm_contract.py` = `9e69ee487a9f`（566 ln） | 23:54:47 | **`2f34a9344441`（667 ln）** | **00:25:21** | **superseded** |
| `matrix.json` 23:55:00 版 | 23:55:00 | **`c10541f9f532`（00:34:47）** | 00:34:47 | **superseded** |

**取代它们的原因**：00:0x–00:3x 落地了 §6.1 的缺陷 4（round-trip）与 §6.2 的采集器修正
⇒ 契约层 566→667 ln、生成器 509→637 ln、matrix 重生成。
**D 在 §14-1 独立验证的那两条结论（`mutation_floor_off` 前 8 行 PASS / 后 17 行 RED、`mutation_no_widen` 25 行全 RED）
在现行版本下仍然成立**，且现行 gate run 的 `arm_no_widen` / `arm_floor_off` 两臂已重跑（27 checks 0 red 里含 G7/G8）。
**⇒ 引用修后基线数字时请用 `c10541f9f532`（00:34:47）这一版，不要用 23:55 那版。**

---

## §9 §14-5 的口径限定：逐条接受，并在此复述（防跨口径搬用）

1. **接受**：基线 `matrix.json` 的 `verdict=PASS`（16 PASS / 9 RED，其中 8 stress + 1 YAM 必红，
   `must_red_branches_all_red=true`，round-trip 25/25）**数据源是 `env_derived_diagnostic`，不是主线 S1**
   ⇒ **不得被任何文书引用为「归一化契约已通过」或「可以开始 BC」**（裁定 71 `caliber_transplant_ban`）。
   主线 stats 仍等 B2 的先导 5 集。
2. **接受**：修前的具体数字**一律作废**（越界维 `[8,9]`、`clip_ratio=0.526667`、`dims=[7,8,9,10]`）。
   引用必须引修后版本 ⇒ 本文所有数字取自 `c10541f9f532`（00:34:47）。
3. **接受**：`eval_frames_are_held_out=true`（600 build / 600 eval）与每分支独立 `representation_version` 继续保留。
4. **接受并继续带注记**：`start_pose` 取自 A2 的 `approach_baseline.json`（sha `8159d6049f37`）的
   `hold_action_14d`，该文件 `control_dt=0.02`；**起态位姿是几何量、不随控制频率变化 ⇒ 不构成裁定 71
   禁止的跨口径移植，但每次引用都带这条注记，不省略。**
5. **§14-6 接受**：若 B2 交来先导版 npz，C2 跑出的 stats **标 `stats_provenance=pre_pilot5_path_check`，
   不进 BC、不作主线 stats**；拿到真 pilot-5 后**必须重算一次并登记两次的分布差**。
   **若 npz 与契约不符 ⇒ 报 D，不自行修补 B2 的产物。**
6. **§14-7 接受**：顺序 = ① B2 的 npz → ② C2 的主线 stats → ③ `harness/env_gym_aloha.py` 三条硬约束
   （解锁 A2 的 S4b）。**C2 不为 A2 插队。** 另接受 `timeout_isolation_scope=td_only`：
   实现四类判定（成功/失败/超时/未知，且**独立于 `reward==4`**）时**不得把 TimeLimit 截断当环境终止**，
   并**必须有一个变异体证明"把 truncated 当 terminal 会被判红"**（`tooth_must_be_mutant_proven`）。

---

## §10 §13-5 的自查回答（裁定 82.5：像素逐位不得作 egl 下的验收判据）

**回答：C2 的判定层不含任何像素逐位断言 ⇒ 无需改动。**
自查方式 = 对 `harness/env_gym_aloha.py`（579 ln / `6c4d71eb732e`）与 `scripts/c2_gate_env_gym_aloha.py`
全文 grep `pixel|像素|bitwise|逐位|image.*sha`，**命中 3 处，全部是 `obs_type="pixels_agent_pos"` 这个
枚举字符串本身**（`env_gym_aloha.py:20`、`:367`、`c2_gate_env_gym_aloha.py:424`），无一处是断言。
J1–J15 判的是**状态量**（qpos/控制频率/步数/边界语义/秒口径），与 D 的复核结论一致。
**⇒ C2 不写死任何 wrist 容差值，等 E 的 N≥5 量化落地。**

---

## §11 T-C2-6「待触发」记录（裁定 49.4 暂缓；D 要求不许变沉默缺口）

- **事实**：`registry/verdict_identity.py:47` 的原文 =
  `GATE_MODULE_PATH = ROOT / "scripts" / "b_gate_controlled_success.py"`
  （该文件 1243 ln / `98139ba9961f` / as_of 16:56:40）⇒ **门禁路径被钉死在 ACT 线的单一门禁**。
- **待触发条件**：π₀.₅ 线开始产出**需要发布边界**的版本（`registry/release_bundle.py` 的
  `ReleaseBundle` / `DeploymentManifest`）时，单一 `GATE_MODULE_PATH` 无法同时表达 ACT 与 VLA 两套门禁
  ⇒ 届时需要"多门禁并存"的口径。
- **风险不对称（D 的判断，C2 同意）**：`registry/` 归 B2、主线暂不需要 ⇒ **C2 不主动动它**。
- **维护权**：裁定 49.6 之后 `registry/` 与 git 单写者同源归 **B2**；裁定 78.2 的最小公共 schema
  会影响它 ⇒ **D 会在 B2 落地后再裁多门禁并存口径**。C2 在此登记，**不作为缺口留着不说**。

---

## §12 纪律接受

### 12.1 逐条接受（含本轮新立的三条）

| 纪律 | 裁定 | C2 的实现口径 |
|---|---|---|
| `citation_sha_as_of_discipline` | 78.11 / 82.6 | **已做成函数**（§12.2）。本文所有 sha 由它生成；引 B2 的 S1 产物时在**读取时刻**重算并写进 `provenance` |
| `redline_provenance_discipline` | 84（参数表 `operations.*`） | 任何版本/阈值/下界类红线，第一次入文书前**读实现原文**并留 `文件:行号`；只有声明值支撑的标 `declared_only`、不作 blocking。**§7.1 就是 C2 自己违反它的实例** |
| `tooth_must_be_mutant_proven` | 83.2 | 已升级为**元判据 G24**：只认台账、不认登记文案（登记了变异体但没有 `flip_measured=True` 记录，一样红） |
| `regression_driver_output_enumeration` | 79 | 守卫版驱动 `scripts/c2_driver_output_guard.py`（417 ln）+ 自检 4/4；本线闸另有 **G20 写入面自查**（全枚举 + 枚举器自检） |
| `mutant_construction_isolation` | 78.1 | 变异体目录已存在 ⇒ **响亮拒绝**，不改名、不复用（`build_mutant()` 的第一件事） |
| 负载条件量 | 73 | 每个吞吐/耗时数字成对带 `loadavg` + `nr_throttled`；**GPU 档不用 `11.82×`**（裁定 71 更正） |
| 静默窗口 | 73 | CPU 重作业也走申报；本轮全部为 **CPU-only / osmesa / 无 GPU**（`CUDA_VISIBLE_DEVICES=""` 由 `run_py()` 强制） |

### 12.2 对 §13-3 那句"做成函数、不要靠自觉"的直接回应

**`scripts/c2_cite.py`（95 ln / `9f02a03c9e98` / as_of 01:14:14）**：输入 `path[:line]`，
**在调用时刻**重算 sha256-12 / 行数 / 字节数 / mtime，并可回显该行原文
（⇒ 行号与"那一行写了什么"同时被固定，**行号漂移会当场露馅**）；路径不存在 ⇒ **非 0 退出**，不静默跳过；
`--out` 只准写 C2 自己的写入面。**本文文末的身份表就是它的输出**，不是手抄的。

---

## §13 诚实的未做清单

### 13.1 C2 自己欠的

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | T-C2-3（重复帧检测 + `obs_store` 图像容量实测） | **未实施** | 被 T-C2-1 挤占；`video-backed` 属**接口变更 ⇒ 只报不改**（维持原判断，78.9 的两个口径分开登记不换算） |
| 2 | T-C2-5（A 线冻结时产物清单，五列齐 + 每 sha 带 `as_of`） | **未实施** | 纯只读汇总、不代 A 表态、不改 A 的文件；等 D 排 |
| 3 | T-C2-2 的 `late_policy=hold` 牙 | **未实施** | 主体已验收（裁定 68），这颗牙是附加项 |
| 4 | `harness/env_gym_aloha.py` 三条硬约束（裁定 62） | **未实施** | 按 §14-7 排在主线 stats 之后，**不插队** |
| 5 | T-C2-6 | **未实施**（暂缓） | 已写「待触发」记录（§11） |

### 13.2 **C2 主动报的一条债：78.9 D3 引的图像体积数字，C2 侧无产物**

`daily_report.md:4736`（裁定 78.9 D3）记：*「C 线 `147 KB/帧` = PNG 压缩推算；C2 实测 `np.savez` 未压缩 =
**1765.19 KB/帧**（策略层）/ **2701.04 KB/帧**（env 相机）」*。
**这两个数字来自 C2 的口述实测，C2 的写入面内没有任何产物支撑它们**（`grep -rl` 于 `runs/` + `docs/`：
除 `daily_report.md` 与 D 的执行单外 **0 命中**）。
⇒ **按 D 自己的口径（"D 无法核对没有落盘的任务"、`declared_only` 不得作 blocking），
这两个数字现在是 `declared_only`，不应被任何容量/排期计算当实测值用。**
**C2 的整改提议**：把 T-C2-3 的容量实测做成产物（`runs/vla/c2_obs_store_capacity_*/`，
带 `load_pair` + 两个口径分开登记 + 每档帧数），**在 D 排给它之前不占主线**。
**这也正是 C 线绕路的成因形态（口述 → 被反复引用 → 变既成门），C2 自己踩了一次，主动报。**

---

## §14 需 D 裁的 4 件事（C2 不自决）

1. **`coef` 取 0.05 还是 0.02**（§6.3）—— C2 倾向 0.05，标 `proposed_pending_s1`。
2. **`near_constant_rel_tol = min(F1_CANDIDATES)` 这个单源耦合是否接受**（§6.3）—— 改 coef 候选集会自动改容差。
3. **`clip_ratio_cap` 是否维持 0.01**（§6.3）—— C2 反对放宽到 0.02 以上，理由是会把"展宽没做"合法化。
4. **`floor` 家族取 F1 还是 `max(F1,F2)`**（§6.3）—— 实测 F2 单独用等于没有保护（10/10 维实质无效、绑定 0 维）。

---

## §15 下一步（按 §14-7 的顺序，不插队）

1. **等 B2 的 `states_14d.npz`**（接口已成绑定契约，裁定 82.2）。拿到后：
   先导版 ⇒ 标 `stats_provenance=pre_pilot5_path_check`、只验通路；真 pilot-5 ⇒ 出主线 stats，
   并登记两次的分布差。**若与契约不符 ⇒ 报 D，不改 B2 的产物。**
2. **主线 stats 之后**做 `harness/env_gym_aloha.py` 的三条硬约束（裁定 62），解锁 A2 的 S4b；
   四类判定独立于 `reward==4`，且**TimeLimit 截断 ≠ 环境终止**，配一个变异体证明。
3. **等待期**（CPU-only、只读或自有目录）：T-C2-3（含 §13.2 的整改产物）→ T-C2-5 → T-C2-2 的 `late_policy=hold` 牙。
4. **git**：C2 不提交（单写者 = B2，裁定 49.6）。**本文书与 `scripts/c2_cite.py`、
   `scripts/c2_gate_norm_contract.py`（1051 ln / `c17b30bae3e8`）、`harness/norm_contract.py`、
   `scripts/c2_build_norm_stats.py`、`scripts/c2_fix_physical_range.py` 请转 B2 代提交**；
   **注意 `runs/` 被 `.gitignore:12` 排除 ⇒ 上表所有 `runs/**` 证据只在 NFS，不进 git**，请在提交信息里写明。

---

## 附：本文书引用的文件身份（`scripts/c2_cite.py` 于落笔时刻生成，非手抄）
| 路径 | sha256-12 | 行数 | 字节 | as_of mtime | 行号 | 该行原文（截断 160） |
|---|---|---|---|---|---|---|
| `harness/norm_contract.py` | `2f34a9344441` | 667 | 44377 | 2026-09-30T00:25:21+08:00 | — | — |
| `harness/norm_contract.py` | `2f34a9344441` | 667 | 44377 | 2026-09-30T00:25:21+08:00 | 424 | `if missing or nonfinite:` |
| `harness/norm_contract.py` | `2f34a9344441` | 667 | 44377 | 2026-09-30T00:25:21+08:00 | 427 | `raise NormContractViolation(` |
| `scripts/c2_build_norm_stats.py` | `90d6254ba7af` | 637 | 44016 | 2026-09-30T00:25:21+08:00 | — | — |
| `scripts/c2_gate_norm_contract.py` | `c17b30bae3e8` | 1051 | 71662 | 2026-09-30T01:09:05+08:00 | — | — |
| `scripts/c2_fix_physical_range.py` | `8c58e8271166` | 334 | 23089 | 2026-09-30T00:31:57+08:00 | — | — |
| `scripts/c2_collect_env_states.py` | `461775d48b69` | 250 | 14338 | 2026-09-30T00:15:25+08:00 | — | — |
| `scripts/c2_cite.py` | `9f02a03c9e98` | 95 | 4551 | 2026-09-30T01:14:14+08:00 | — | — |
| `scripts/c2_driver_output_guard.py` | `6cc7b148295b` | 690 | 40588 | 2026-09-29T23:11:07+08:00 | — | — |
| `harness/env_gym_aloha.py` | `6c4d71eb732e` | 579 | 32569 | 2026-09-29T22:09:11+08:00 | — | — |
| `scripts/c2_gate_env_gym_aloha.py` | `c9100b3811cd` | 549 | 31098 | 2026-09-29T22:09:11+08:00 | — | — |
| `harness/queue_td_learner.py` | `afc9ebb92621` | 661 | 36314 | 2026-09-29T21:28:51+08:00 | 134 | `raise LearnerRefused(f"{kind}: 分片行缺 x_ref，无法反查观测")` |
| `registry/verdict_identity.py` | `98139ba9961f` | 1243 | 77956 | 2026-09-29T16:56:40+08:00 | 47 | `GATE_MODULE_PATH = ROOT / "scripts" / "b_gate_controlled_success.py"` |
| `daily_report.md` | `2f2051e177d5` | 5679 | 742124 | 2026-09-30T01:13:16+08:00 | 4736 | `- **78.9 D3 图像体积：两个口径分开登记、不换算**（C 线 `147 KB/帧` = PNG 压缩推算；C2 实测 `np.savez` 未压缩 = **1765.19 KB/帧**（策略层）/ **2701.04 KB/帧**（env 相机））。**任何容量/排期计算必须声明用哪个口径。**` |
| `runs/vla/c2_norm_contract_20260929/matrix.json` | `c10541f9f532` | 8168 | 369452 | 2026-09-30T00:34:47+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/mainline_status.json` | `705eb071b54e` | 13 | 936 | 2026-09-30T00:34:47+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/physical_range_correction/correction.json` | `03df905d880a` | 1137 | 32208 | 2026-09-30T00:16:18+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/physical_range_correction/physical_range.json` | `ef50e89c88ef` | 287 | 6532 | 2026-09-30T00:16:18+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/gate/run_20260930_010948/gate_verdict.json` | `4443e4aea7b8` | 1572 | 85051 | 2026-09-30T01:09:57+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/gate/run_20260930_010545/gate_verdict.json` | `b37b62178a8d` | 1496 | 79552 | 2026-09-30T01:05:52+08:00 | — | — |
| `runs/infra/c2_overwritten_c_artifacts_20260929/index.json` | `586613978a33` | 85 | 4717 | 2026-09-29T23:13:18+08:00 | — | — |
| `docs/c2_gate_polarity_audit_20260929.md` | `768d49409d76` | 285 | 28642 | 2026-09-29T23:37:30+08:00 | — | — |
| `docs/c2_gate_polarity_audit_20260929.md` | `768d49409d76` | 285 | 28642 | 2026-09-29T23:37:30+08:00 | 264 | `## §9 勘误（append-only，2026-09-29 23:3x；应 D 执行单 §12-4 / 裁定 78.11 要求补）` |
| `docs/c2_task_selfintake_20260929.md` | `e1c99b50d45a` | 184 | 26375 | 2026-09-29T20:33:44+08:00 | — | — |


---

# 【01:3x 追加】§16 B2 的先导 5 集已落地 ⇒ 主线通路已验证，并且**查出一个会影响 VLA 主线的问题**

> **append-only**：本节追加前本文书 = **406 ln / sha256-12 `10e5a1338525`**（01:2x 落盘）；§1–§15 一字未改。
> 追加理由：B2 的 npz 已落地，跑出来的结果**改变了 §6.3 与 §14 的一部分结论**
> ⇒ 按 `citation_sha_as_of_discipline` 必须追加、不能改原文。

> **⚠ 本节自身的一处更正（C2 主动报，同 `redline_provenance_discipline` 的形态）**：
> 本节初稿写的是「§15 的"等 B2 的 npz"在本文书落盘后 35 分钟就发生了」——**这句是错的**。
> 实测时序：B2 的 npz 落盘于 **01:08:09**，而 C2 的 §1–§15 写于 **01:2x** ⇒ **npz 在 C2 动笔时就已经在了**。
> **真正的缺陷是：C2 在写"等待 B2"之前没有去查那个接口路径**（`ls` 一次就能发现），
> 而是在追加 daily_report 时从 B2 的段落里偶然读到才发现。
> ⇒ **这与 C2 当天前三次纠错同族**（读了声明没读实现 / 写了等待没查落地）。
> **整改（已落进代码，不只是写进文书）**：任何"阻塞在他人产物"的状态，落笔前必须真去查一次该路径。
> `mainline_status.json` 里本来就有 `checked_path` 字段，但**等待分支只记路径、不记时刻，built 分支根本不记**
> ⇒ 01:33:24 那版产物里它是 `null`（**C2 不把它说成已填**）。
> 已改：`built` 分支现在写 `checked_path` + `checked_at` + `checked_path_sha256_12`；
> 等待分支补 `checked_at` + `checked_path_exists`（generator `3f09555d8eef` → **`b52b31245140`**）。
> **因为 generator 变了，01:33 那份产物按裁定 82.6 必须以重生成方式闭合** ⇒
> 前像留 `runs/vla/c2_norm_contract_20260929/before_images/mainline_s1_pilot5_gen_3f09555d8eef/`
> （`matrix.json.before_6715519ea670` + `mainline_status.json.before_5f398cd57990` + `WHY_BEFORE_IMAGE.md`）。
> **预期差异只在 `mainline_status` 的三个新字段**；33 行判定、F1/F2 的 `Tr3` 结论、
> held-out 划分（留出集 `[4,9]`、2196/550）都不应变 —— 若变了就说明改动有副作用，C2 会查并报。

## 16.1 B2 的交付（C2 只读，未改 B2 任何文件）

`runs/vla/b2_states_14d_20260930/pilot5/`：`states_14d.npz`（333664 B / as_of 01:08:09）+
`manifest.json`（52933 B / as_of 01:08:10）。`frames=[2746,14] float64`（全有限）、`start_poses=[10,14]`、
`episode_index=[2746]`、`episode_boundaries=[11]`、`direction_code=[10]`（集 0–4 = forward，5–9 = reverse）。
manifest 自报：`verdict=PASS`、`n_checks=16`、`n_red=0`、`is_pilot5=true`、`tier=mainline_candidate`、
`formal_collection_pending=true`、`gpu_nonusage` 前后各一次 `nvidia-smi`（0 外部 compute app）、
`load_pair={loadavg 26.44 25.78 26.49, nr_throttled 14732, cgroup 12}`。
**B2 还主动做了 `c2_consumer_drycheck`（read-only import），引用的 C2 生成器 sha = `90d6254ba7af`，与当时磁盘一致。**

## 16.2 C2 的处置：**不采信 B2 的数组，逐维复算**（新增 `s1_npz_crosscheck()`）

| 复算项 | 结果 |
|---|---|
| npz 的 `observed_travel` 是否等于 frames 逐维 `max-min` | **一致**（`max_rel_diff ≤ 1e-9`） |
| `physical_range_effective` 是否等于 `max(declared_c2_caliber, observed_travel)`（= C2 §6.2 的规则） | **一致** |
| C2 **实际拿去用的**分母是否就是上面那一份（防"登记一份、用另一份"） | **一致** |
| ⇒ `contract_conformant` | **true** |

**一个口径裁定请求（C2 不自决）**：`resolve_physical_range()` 原本的优先级 ① 是 C2 的勘误件
（`physical_range_correction/physical_range.json`）。**那份里的"实测行程"是 C2 从 env 诊断档
（random/sweep/hold）量出来的**；把它当主线帧的分母 = **裁定 71 禁止的跨口径移植**。
⇒ C2 给主线档加了 `prefer="npz"`：**规则可以搬（`max(声明, 同源实测)`），实测值不能搬**。
主线档的分母 = B2 npz 自带的 `physical_range_effective`（与 frames 同源）。**请 D 追认这条口径。**

## 16.3 本轮在 C2 自己生成器里查出的 3 个缺陷（都已修，修前形态各留一个证据目录）

| # | 缺陷 | 修前证据目录（含 `WHY_KEPT.md`） | 修法 |
|---|---|---|---|
| 9 | `--s1-frames` 传**相对路径**时崩在 `resolve_physical_range()` 的 `relative_to(ROOT)` | ——（直接崩，无产物） | 相对路径先经 ROOT absolutize |
| 10 | **主线档根本没有 held-out**：`eval_frames` 没传 ⇒ `eval_frames_are_held_out=false`、`2746 build / 2746 eval` ⇒ `Td2_clip_heldout` / `Te2_no_illegal_bin_heldout` **名义叫 held-out、实质是 build 帧的重测**（与 `Td1`/`Te1` 重复计量） | `mainline_s1_pilot5_pre_heldout_split_EVIDENCE/`（matrix `61bde7dbc0e3`） | 新增 `split_heldout_by_episode()`：**按集切**，留出每个 `direction_code` 的最后一整集；无 `episode_index` 就显式登记 `held_out=false`，**不假装切过** |
| 11 | `direction_code` 是**按集**给的（长 10）、`episode_index` 是**按帧**给的（长 2746），首版把两者直接 `zip` ⇒ 分组全错 ⇒ 误报"每个方向的集数 < 2" | `mainline_s1_pilot5_pre_direction_grouping_fix_EVIDENCE/`（generator `bc576ba65fb0`） | 按 `episode_boundaries` 的顺序把集号映到方向码，**长度不符就响亮拒绝、不猜** |

**缺陷 10 是本轮第二重要的发现**：如果没修，主线档会交出一份"全绿"的 stats，
而 `Td2/Te2` 那两颗牙**根本不是在测它们名字里说的东西** —— 与 §6.1 缺陷 2（`Tr1` 恒真）同族：
**牙的名字与实际咬的方向不一致**。缺陷 11 值得单独说一句：它**没有伪装成成功**，
产物里如实写了 `held_out=false` 和原因 ⇒ 是"响亮的错"而不是"沉默的绿"，这正是 C2 想要的失败形态。

## 16.4 **修好 held-out 之后，主线档在真数据上红了 —— 这是实质发现，不是缺陷**

划分：留出集 **[4, 9]**（每个方向最后一整集），`n_build=2196 / n_eval=550`，`held_out=true`。
产物：`runs/vla/c2_norm_contract_20260929/mainline_s1_pilot5/matrix.json`（33 行，`must_red_all_red=true`）。

| 牙 | build 帧 | **held-out 帧** |
|---|---|---|
| `Td1_clip_build_frames` / `Td2_clip_heldout` | PASS，最差维 0、`clip_ratio=0` | **RED，最差维 = 12、`clip_ratio=0.0927273`（n_eval=550）** |
| `Te1_no_illegal_bin_build` / `Te2_no_illegal_bin_heldout` | PASS，`dims=[]` | **RED，`dims=[7, 12]`（非法 bin `-1` 会被拼进文本 prompt：`processor_pi05.py:77`、`:81-84`）** |
| `Tsat_saturation_dims_zero` | —— | **RED，3 个饱和维 = [5, 7, 12]，`above_1=33`、`below_-1=100`、`abs_max_normalized=1.0849`** |
| `Tc_start_pose_coverage` | PASS（越界维 []，原始越界维 [2,9]、`max|state|=1.16`） | 同（起态是几何量） |
| `Tr1` / `Tr3`（F1） | PASS（`unprotected=[]`、近常量维 = **[3, 10]** 两维、`materiality_ratio_min=2.5`） | 同 |

**根因（实测，不是推测）**：`widen_to_cover()` 的 `must_cover = (start_pose, build_frames)`
⇒ **它按构造只能保证 build 帧不裁**，对**没见过的集**结构性地无保护。而受影响的三维恰好是
**两个 wrist_rotate + 一个 waist**，它们在 build 集与 held-out 集上的取值区间**几乎不相交**：

| 维 | 名称 / 关节 | build 区间 | held-out 区间 |
|---|---|---|---|
| 5 | `left_arm_joint_5` / `vx300s_left/wrist_rotate` | `[-0.2735, +0.0354]` | `[-0.0062, +0.1579]` |
| 7 | `right_arm_joint_0` / `vx300s_right/waist` | `[-0.0370, +0.1891]` | `[-0.1703, +0.0365]` |
| 12 | `right_arm_joint_5` / `vx300s_right/wrist_rotate` | `[-0.0396, +0.1911]` | `[-0.1714, +0.0113]` |

held-out 的 550 帧里，落在 build 的 q01–q99 之外的帧数：dim0=97、dim5=96、dim7=96、**dim12=97**（≈17.6%）。

**⇒ 这条对 VLA 主线意味着什么**：`Td2` 实测 **0.0927**，是 §6.3 提案 `clip_ratio_cap=0.01` 的 **9.3×**。
**这与 ACT 线的致命事故、以及 A2 的 π₀.₅ zero-shot 0/20 是同一族现象**（状态通道越界 / 饱和，
而离线指标全程看不见）。**区别是：这次它在 P1 BC 开跑之前、被一颗真的 held-out 牙量出来了。**

## 16.5 §6.3 的"下限家族之争"在主线同源数据上的判决（**修正 §6.3 的表述**）

- **`Tr3` 在主线数据上把 F1 与 F2 分开了**：F1（coef 0.05 / 0.02，两个 case）**`Tr3=PASS`、不足维 []**；
  F2（coef 4.0 / 2.0，两个 case）**`Tr3=RED`、不足维 = [3, 10]**。
  ⇒ **§6.3 的建议不变、且现在是主线同源数据上的实测**：主线用 **F1**（或 `max(F1,F2)`），**F2 单独用等于没有保护**。
- **但 §6.3 里"F1 全绿"的说法必须作废**：那是 held-out 还没修时的结果（16.3 缺陷 10）。
  修好切分后 **8 个主线行全 RED**，其中 F1 的 4 行红在 **覆盖类牙（Td2/Te2/Tsat）**、
  F2 的 4 行**额外**红在 **Tr3**。⇒ **两个问题要分开裁**：下限家族（Tr3，已有答案）与
  覆盖不足（Td2/Te2/Tsat，16.4，**尚未有答案**）。
- **另一条口径事实（支持 D 一直坚持的那条）**：主线数据的近常量维只有 **2 个（[3,10]，两个 forearm_roll）**，
  而 env 诊断档 hold 相是 **10 个** ⇒ **env 诊断档在"哪些维几乎不动"这件事上完全不代表示范数据**
  ⇒ 裁定 52/69「env/YAM 不得顶替主线 stats」有了量化依据。

## 16.6 追加给 D 的裁定请求（**§14 的 4 条之外，新增 4 条**）

5. **`widen_to_cover` 的覆盖目标要不要改**？现状 = 只覆盖 `start_pose + build_frames`（按构造保护不了新集）。
   候选：① 覆盖到**声明物理区间**（`physical_interval`，模型级几何量、口径无关）；
   ② 覆盖到 build 帧的 q01/q99 **再加一个余量**（余量按物理行程的比例给，与 F1 同源）；
   ③ 不改规则，改**数据量**（正式采集更多集）。**C2 倾向 ①+③ 并用**，但**不自决**：
   ① 会牺牲分辨率（bins 中位数会掉），需要 D 认这个代价。
6. **先导 5 集（每方向 5 集）够不够建主线 stats**？16.4 的实测答案是**不够**（held-out clip 9.27%）。
   ⇒ 请 D 明确：`pre_pilot5_path_check` 这个降档标签**继续保持**，还是等正式采集。
   **C2 侧已按最保守口径执行**：`stats_provenance=pre_pilot5_path_check`、`not_for_bc=true`。
7. **契约文本冲突（B2 已登记 `OPEN_needs_d_ruling`，C2 不代改）**：裁定 82.2 的契约文本里
   「夹爪维 = 1.0」与「同 `scripts/c2_collect_env_states.py` 口径」两个半句互相矛盾
   （该文件现行口径实测 **0.91001**，差 **9.889%**）。**请 D 改契约文本**；
   本次运行对 `physical_range`（契约字面、夹爪 1.0）**只登记不使用**。
8. **`clip_ratio_cap=0.01` 是否维持**：16.4 实测主线 held-out 是 **0.0927（9.3×）**。
   **C2 认为这恰恰证明 0.01 是对的**（它把一个真问题量出来了），**反对因为"红得难看"而放宽**。

## 16.7 §15 的下一步（更新）

1. ~~等 B2 的 npz~~ ⇒ **已到（01:08:09，早于本文书 §1–§15 的落笔时刻），通路已验证**。
2. **等 D 裁 16.6-5/6** ⇒ 然后出主线 stats（若 D 选 ①，C2 改 `widen_to_cover` 的 `must_cover`，
   并**必须配一个变异体**证明"改成覆盖声明区间后，held-out clip 不红"这件事是真的、
   而不是把牙拔了 —— `tooth_must_be_mutant_proven`）。
3. `harness/env_gym_aloha.py` 三条硬约束（裁定 62）仍排在主线 stats 之后，不插队。
4. **新增债务（诚实登记）**：**本线的闸（27 checks）目前只覆盖诊断档矩阵，尚未覆盖主线档（S1）行**。
   `NORMAL_ROW_COUNT=16` / `STRESS_ROW_COUNT=8` / 25 行这些常量都是诊断档的
   ⇒ 主线档要进闸，需要先把行数常量按档参数化。**C2 下一轮做，不在本轮声称已做。**

### 附 16：§16 引用的文件身份（同样由 `scripts/c2_cite.py` 于落笔时刻生成）
| 路径 | sha256-12 | 行数 | 字节 | as_of mtime | 行号 | 该行原文（截断 160） |
|---|---|---|---|---|---|---|
| `runs/vla/b2_states_14d_20260930/pilot5/states_14d.npz` | `5c4710426db2` | 2361 | 333664 | 2026-09-30T01:08:09+08:00 | — | — |
| `runs/vla/b2_states_14d_20260930/pilot5/manifest.json` | `236089f59170` | 1661 | 52933 | 2026-09-30T01:08:10+08:00 | — | — |
| `scripts/c2_build_norm_stats.py` | `3f09555d8eef` | 811 | 56890 | 2026-09-30T01:33:14+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/mainline_s1_pilot5/matrix.json` | `6715519ea670` | 10768 | 490751 | 2026-09-30T01:33:24+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/mainline_s1_pilot5/mainline_status.json` | `5f398cd57990` | 38 | 1261 | 2026-09-30T01:33:24+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/mainline_s1_pilot5_pre_heldout_split_EVIDENCE/matrix.json` | `61bde7dbc0e3` | 10629 | 480596 | 2026-09-30T01:27:34+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/mainline_s1_pilot5_pre_heldout_split_EVIDENCE/WHY_KEPT.md` | `8529b06a4b0b` | 22 | 1603 | 2026-09-30T01:31:05+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/mainline_s1_pilot5_pre_direction_grouping_fix_EVIDENCE/WHY_KEPT.md` | `4860092dc802` | 16 | 1127 | 2026-09-30T01:33:14+08:00 | — | — |
| `runs/vla/c2_norm_contract_20260929/physical_range_correction/physical_range.json` | `ef50e89c88ef` | 287 | 6532 | 2026-09-30T00:16:18+08:00 | — | — |
| `harness/norm_contract.py` | `2f34a9344441` | 667 | 44377 | 2026-09-30T00:25:21+08:00 | — | — |
| `docs/c2_handoff_to_d_20260929.md` | `a03cfd91db71` | 524 | 45716 | 2026-09-30T01:37:49+08:00 | — | — |


---

# 【07:2x 追加】§17 裁定 90.4 的 P0 闸已到 PASS · D 预登记的可证伪检查点三条全过 · **并查出一条 C2 自己的过严牙（它是主线臂 RED 的唯一驱动）**

> 前像：本节追加前 `docs/c2_handoff_to_d_20260929.md` = **555 ln `5867798f76b3`**（as_of 2026-09-30T01:40:05+08:00），
> 影像 = `runs/vla/c2_norm_contract_20260929/before_images/c2_handoff_to_d_20260929.md.before_5867798f76b3`。
> 本节所有数字均为**本轮实测**（非沿用早先 run 的值，裁定 82.6）；负载口径随数字给出。

## 17.1 一句话

**闸到 PASS（48 checks / 0 red / 0 warn / 0 N_A），formal-40 主线 stats 已产出且标签为 `formal40_bc_source`；
D 在裁定 87.3-2 条件 c 预登记的可证伪检查点（`Td2`=0 / `Te2`=`dims=[]` / `Tsat`=0）在三条 formal-40 臂 24 行上全过
⇒ ① 的可证伪预测被证实。但主线臂 matrix 仍是 RED，唯一驱动是 C2 自己设的 `Tb`（+`Tr3`）两把 blocking 牙，
而它们的阈值状态分别是 `proposed_pending_s1` 与 `derived_from_min_F1_candidate（C2 提议，待 S1 定标）`
⇒ 与裁定 87.3-2 条件 b「超限走升级路径（报 D）**而不是自动判红**」及红线 `redline_provenance_discipline`
「只有声明值支撑的一律标 `declared_only`，**不得作为 blocking**」直接张力。C2 不自决降级（降 blocking = 放宽闸，属 D 裁量），只报。**

## 17.2 闸的终值（run `run_20260930_073852` —— **权威跑**；`run_20260930_071824` 已被 17.12 的两次编辑取代，见该节）

产物 = `runs/vla/c2_norm_contract_20260929/gate/run_20260930_073852/gate_verdict.json`
（**1534409 ln / 69440530 B / `ae4e16c33743`**，`generated_at = 2026-09-30T07:40:21+08:00`，文件 mtime 07:40:23）。

| 项 | 实测值 |
|---|---|
| verdict / n_checks | **PASS** / **48** |
| n_red / n_warn / n_n_a | **0 / 0 / 0** |
| 四臂 | `baseline` **PASS**（25 行、`n_red_non_mustred=8`、`must_red_all_red=true`、exit 0、0.583 s、matrix `4f60635515f6`）· `no_widen` **RED**（24、`e172e7ec69e1`）· `floor_off` **RED**（16、`38176b8dd0b9`）· `mainline` **RED**（49 行、`n_red_non_mustred=24`、exit 0、3.599 s、matrix `eb2ab0bf1db6`、`mainline_status=built_from_npz_authority_interface`）——**四臂 exit 全 0** |
| 文件级变异体 | **26** 个，`identity_self_proof_ok` **26/26 = True** |
| 翻转台账 | **48** 条，`flip_measured=True` **48/48** |
| 进程内探针 | **11/11** `ok=True` 且 `gate_copy_identical_to_real=True`；11 份副本 sha **全部** = `3f44225a5fa1` = 实物闸 sha（逐一核过，不是抽样） |
| G51 锚点预检 | `n_mutants=32 n_anchors=37 n_bad=0 bad=[] control_ok=True control_counts=[0]`（**在 17.6 的 builder 改动之后重测，仍零漂移**） |
| G48 三牙台账 | `PASS`、`all_caught=true`、`guard_fired_first_attempt=true` |
| G42 / G46 / G50 | 全 `PASS` |
| 负载（收尾） | `loadavg 18.33 22.17 19.96`、`nr_throttled 17437`、`cgroup_quota_cores 12`（**超配额，读数含争用**） |

**为什么"主线臂 RED"与"闸 PASS"不矛盾（口径必须写清，否则会被读成假绿）**：
闸侧已删除 `MAINLINE_ALLOWED_RED_F1` / `_F2` 两份白名单（它们在修前的闸里就是**死代码**，而 D 在 §D90.1
正是把「`Tiv` 不在 `MAINLINE_ALLOWED_RED_F1` 里」当作阻塞 BC 的理由之一 ⇒ 一个没人读的常量被当判据引用；
理由写在 `scripts/c2_gate_norm_contract.py:90`–:99）。现行口径 = **允许红的牙由生成器逐行从测量派生**
（`derive_allowed_red_from_measurement`），闸只核「红是否**逐条被授权事实解释**」（`pred_G27` 的
`unexplained_red_teeth == []`）。本轮该谓词为真 ⇒ 主线臂的每一条红都有授权事实，**不是实现缺陷**；
但"有解释"≠"可进 BC"，见 17.5。

## 17.3 **D 预登记的可证伪检查点：三条全过**（这是 ① 的验收证据，不是 C2 自定义的判据）

判据出处（D 自己写的、写在采 ① **之前**）：`work/decisions/decisions_20260929.md:2506`（条件 c 小标题 `:2504`）
（裁定 87.3-2 **条件 c** 的「预登记的可证伪预测」）与 `:2670`（§87.13 的可证伪检查点）。
原文要求：采 ① 后 formal-40 的 `Td2_clip_heldout` 应为 **0**、`Te2` 应为 **`dims=[]`**、`Tsat` 应为 **`n_dims_saturated=0`**；
「若三者任一非零 ⇒ 数据里存在超出声明物理区间的状态 ⇒ 判红、不许再展宽、转查采集器与契约」。

本轮在 **三条 formal-40 臂（`s1_mainline_path_check` / `s1_lerobot_crosscheck` / `s1_bc_admission_mustred`，各 8 行 = 24 行）** 上实测：

| 牙 | 实测 | 状态 | pilot-5 时的同项读数（对照） |
|---|---|---|---|
| `Td2_clip_heldout` | 最差维 = **0**、`clip_ratio = 0`（`n_eval=547`） | **PASS** | **0.0927273**（cap 0.01 的 **9.3×**） |
| `Te2_no_illegal_bin_heldout` | `dims = []` | **PASS** | 非法 bin dims = **[7,12]** |
| `Tsat_saturation_dims_zero` | `n_dims_saturated = 0`、`above_1=0`、`below_-1=0`、`abs_max = 0.9929220786 / 0.9981801636`（两 case，均 < 1） | **PASS** | 饱和 **3 维 [5,7,12]**、`above_1=33`、`below_-1=100`、`abs_max=1.0849166207043792` |

对照列出处：`work/project_parameters.json:1986`（**`5a80462e1b12`**，as_of 04:08:28）登记的 pilot-5 红线读数。
⇒ **三条全部由非零/非法转为零**，且 `abs_max < 1`（不再越出 `[-1,1]`）。
**含义**：①（`must_cover` → 声明物理区间，裁定 87.3-1）确实解决了它声称要解决的问题；
pilot-5 上那条 9.3× 的 clip 不是"数据坏"，而是"覆盖目标只保 build 帧"这个**实现口径**造成的（与 16.4 的根因判断一致）。

**① 的可推翻条件未被触发**：`decisions_20260929.md:2502` / `work/project_parameters.json:688` 写的是
「若 ① 把任何主线维的 `bins_occupied_median` 压到 **< 8** ⇒ D 改采逐维覆盖策略」。
实测 formal-40：held-out 口径 `bins_occupied_median = 35.5`、全量口径 `= 47.5`，**两口径都 ≥ 8** ⇒ 不触发。
（**但该条件用的是 median**，与 D 本轮新立的 `a_per_dim_failure_mode_must_be_gated_by_a_per_dim_statistic`
（`work/project_parameters.json:1126`，即 D 同型错误 #16 的纠正）相冲突 —— 见 17.9-2。）

## 17.4 formal-40 主线档的身份与 BC 准入（实测）

`runs/vla/c2_norm_contract_20260929/mainline_status.json`（**6445 ln / 198907 B / `fc3f049753bf`**，as_of 06:04:23）：

- `status = built_from_npz_authority_interface`、`reader_role = authority（裁定 90.4-4）`
- 源 = `runs/vla/b2_states_14d_20260930/formal40/states_14d.npz`，sha **`a84a26079550`**（与 B2 §11 通知值逐字相符）、
  `frames` content sha **`c9a72480fcb7`**（与 D 亲测值逐字相符）、manifest **`e251dc6e07c7`**、**40 集 / 11035 帧**
- `stats_provenance = formal40_bc_source`（8 项机器判据全过，逐条落在 `stats_provenance_why` 里）、
  `bc_admission.admissible_for_bc = true`、`not_for_bc = false`
- `b2_contract_conflict_status = CLOSED_by_ruling_87_6`（**B2 已改状态串且 sha 未变 ⇒ 时序问题不存在**，见 B2 §11）
- 切分：`held_out_episodes = [19,39]`、`n_build = 10488`、`n_eval = 547`（按集切，同集帧不跨 build/eval）
- 窗口：`headroom_consumption_max = 0.7652`（above 0.7652 / below 0）、`window_escape = False`
  ⇒ `Tesc` 不红；`WINDOW_ESCAPE_RATIO = 1.0` 未放宽
- 越界测量：`dims_out = [6,10,13]`，**全为上侧**、`dims_below = []`、`excess_above_max = 0.0187818`（= 行程的 **0.2989%**）
  ⇒ 按裁定 90.4-1 只**登记 + warning**，不因越界本身出红
- 交叉核对臂标签 = `formal40_lerobot_crosscheck`，已入 `nc.KNOWN_STATS_PROVENANCES`（`harness/norm_contract.py:128`）
  但**故意不在** `nc.BC_ADMISSIBLE_PROVENANCES`（`harness/norm_contract.py:134`，只含 `formal40_bc_source`）
  ⇒ 牙 `Tp4` 不红（它是合法登记的档）而 `Tp5` 对 `consumer=bc` 必红 —— **裁定 90.4-4 的两件事被结构性分开**，
  既不假红也不放宽准入。

## 17.5 **本轮最重要的自审发现：`Tb` / `Tr3` 是 C2 自己设的过严 blocking 牙**（请 D 裁，C2 不自决）

**实测形态**（取自本轮 `arm_mainline/matrix.json` 的逐牙记录，非散文转述）：

| 牙 | `blocking` | `required` 原文里的阈值状态 | 本轮 observed |
|---|---|---|---|
| `Tb_scale_floor_effective` | **true** | `min bins/dim ≥ 8（阈值状态 **proposed_pending_s1**）` | 不足维 = `[0,3,5,7,10,12]` |
| `Tr3_near_constant_floor_material` | **true** | `… floor_d ≥ 0.02 × physical_range_d（阈值状态 **derived_from_min_F1_candidate（C2 提议，待 S1 定标）**）` | 不足维 = `[3,10]` |

**红的覆盖面**：`Tb` 在 **24/24** 条 formal-40 行上红（三条臂各 8 行），`Tr3` 在 **12** 行上红（quantiles 家族 4 行 × 3 臂）。
**这两把牙是主线臂 matrix verdict = RED 的唯一驱动**（其余红行都在 must-red / stress 臂，属设计要求）。

**与现行文书的张力（逐条给出处，都是读原文不是读声明）**：

1. `work/decisions/decisions_20260929.md:2501`（裁定 87.3-2 **条件 b**）原文：
   「**D 本轮不设分辨率下限。** 理由 = D 自己在裁定 86.6-2 立的 `derived_threshold_must_have_single_source`…
   D 将在下一轮从 C2 的登记值定标，并**预登记下限的形状**：主线行 `bins_occupied_median` 的最小值，
   **超限走升级路径（报 D）而不是自动判红**。」
2. `work/project_parameters.json:684` —— 该条的**键名本身**就是
   `b_resolution_cost_measure_only_no_threshold_this_round`（只测量、本轮不设阈值）。
3. `work/project_parameters.json:894`（红线 `redline_provenance_discipline`）原文：
   「任何『版本 / 阈值 / 下界』类红线…**只有声明值…支撑的红线，一律标注 `declared_only`，且不得作为 blocking**。」
4. 本线自己在 `mainline_status.json:escalations_to_d[0].why_escalate_not_relax` 里也已引过条件 b 的同一句。

⇒ **`Tb`（阈值 8，状态 `proposed_pending_s1`）与 `Tr3`（阈值 0.02，状态 `C2 提议待 S1 定标`）都是"阈值类判据 + 未经 D 定标 + `blocking=true` + 自动判红"的组合**，
与 1/2/3 三条同时张力。按 3 的字面，它们应当标 `declared_only` 且**不得 blocking**；按 1/2 的字面，超限应当**报 D 而不是自动红**。

**C2 的处置（不自决）**：把 `blocking` 降为 WARN = **放宽闸**，属 D 的裁量；C2 本轮**没有动**这两把牙的极性，
也**没有**把它们降为 warning。现状 = 主线行 verdict 因 `Tb` 保持 RED，红是逐条可解释的、**不影响 stats 的数值本身**。

**请 D 裁的三选一**（C2 不选）：
- **(甲)** 认 1/2/3 适用 ⇒ `Tb`/`Tr3` 转 **WARN + 强制登记**（阈值仍写 `proposed_pending_s1` / `derived_from_min_F1_candidate`），
  主线臂 matrix 转 PASS，`next_required_action` 的「0 红」条件字面满足 ⇒ BC 无前置。
- **(乙)** 认为条件 b 的「不自动判红」只约束"新设下限"、不约束这两把既有牙 ⇒ **维持现状**，
  并把该解释写进参数表（否则下一位读者会按 1/2/3 的字面判 C2 违规）。
- **(丙)** 按条件 b 的预登记形状**现在定标**（从本轮登记值派生，逐维、不用 median，符合 `:1126`）⇒ C2 落地并配变异体自证。

**⚠ 无论 D 选哪个，都请注意 17.8-E2**：下游若只读 `admissible_for_bc` / `not_for_bc` 这两个字段，
**现在就会读到 `true` / `false`（= 可进 BC）**，而同一份产物的主线臂 matrix 是 RED。

## 17.6 before-image 债务的处置（**一笔已复原、一笔已补登记、一条沉默缺口显式披露**）

**(a) 闸侧（`scripts/c2_gate_norm_contract.py`）：3 份中间态已复原登记。**
上一轮交接自述"本会话编辑了闸却没有开工前像"。实测发现**闸会把自己逐字复制进每个变异体目录**
（证据：`run_20260930_070355` 的闸副本 sha = `d4ea7043ca94` = 当时实物；且本轮 11/11 探针的
`gate_copy_identical_to_real=True`、11 份副本 sha 全等于实物）⇒ 这些副本是**结构性时间戳快照**，可作复原源。
已 `cp -p` 登记为 `before_images/c2_gate_norm_contract.py.recovered_<sha12>`：

| 复原影像 | 行数 | 副本 mtime | 来源 |
|---|---|---|---|
| `recovered_4ab69bf005c0` | 3052 | 06:43:55 | `gate/run_20260930_064656/mutants/M1_non_raising/scripts/…` |
| `recovered_bc6d10df293b` | 3104 | 06:55:20 | `gate/run_20260930_065527/mutants/M19_arm_prefix_mislabel/scripts/…` |
| `recovered_a1661d37e33e` | 3117 | 06:59:03 | `gate/run_20260930_065915/mutants/M19_arm_prefix_mislabel/scripts/…` |
| （**当时**实物）`d4ea7043ca94` | 3156 | 07:03:43 | `scripts/c2_gate_norm_contract.py`（现值见 17.12） |

三份影像的 sha256-12 已**回读复验**（`sha256sum` 与文件名后缀逐字相符）。
**残留缺口（不掩盖）**：05:32:51 的 `before_bf14fff13882`（2084 ln）→ 06:43:55 的 `recovered_4ab69bf005c0`（3052 ln）
之间**只有区间括号、没有中间态**（该区间 `diff` 计 1064 行变更）。06:43:55 之后每一步都有精确前像。

**(b) 副本机制的一条重要限定（防止后人误用）**：上述复原法**只对闸有效，对生成器无效**。
实测：变异体目录里的 `scripts/c2_build_norm_stats.py` = 实物 **+ 11 行**注入的 `__c2_mutant_identity_hook__`
（在实物第 42 行后插入）⇒ 副本 sha `f35dbcd4fd3a` / 3143 ln **≠** 实物 `10689fdc0c68` / 3132 ln。
**顺带证实一处引用是对的**：闸 `:2173` 写「`scripts/c2_build_norm_stats.py:61` 的卫语句 `assert HEADROOM_BINS == 1.0` 仍在位」——
实物里该卫语句在 **:50**，+11 行 hook 偏移 = **:61** ⇒ 该引用**指的是副本行号，逐字正确**；
本轮已实测 `proto_teeth_20260930_0545/mutants/M32_headroom_bins_halved/`：副本 `:61` = 该 assert、
`harness/norm_contract.py:68` = `HEADROOM_BINS_DEFAULT = 0.5`、**无 `out/`** ⇒ `guard_fired_first_attempt=true` 有据。

**(c) 生成器侧：补登记一轮 + 新留一份前像。**
- **更正上一轮交接的一处自述错误**：交接件写「builder 本会话未改」。**实测为假** —— builder mtime 06:03:05，
  与 05:32:51 的影像 `before_e295544b5431`（3102 ln）相比有 **38 行**实测差异，内容为 5 项
  （红标签权威口径改读结构化 `payload["red"]`、`expected_red_teeth` 由不存在的 id 改为实测真红的两个 id、
  行级补 `eval_scope`/`eval_frames_are_held_out`、变异体副本里 `resolve()`→`absolute()`、显示路径改走不抛的 `rel()`）。
  该影像**当时已落盘但没写进 `BEFORE_IMAGE` 字典** ⇒ 块的最新一层停在 `e0f9ca34ffc1`/2789 ln（名实不符）。
- 本轮已把该轮**补登记**进 `BEFORE_IMAGE`（新头 = `e295544b5431`/3102 ln，旧头降为 `previous_before_image`），
  并为 06:03:05 的状态新留 `before_images/c2_build_norm_stats.py.before_10689fdc0c68`（3132 ln）。
- **链已机器复验**：`BEFORE_IMAGE` 现深 **6** 层，6 份影像**全部在盘**，且每层声明的 `sha256_12` 与 `n_lines`
  与实物**逐条相符**（不是只比 sha）。改后 `ast.parse` 通过、卫语句仍在 **:50**（⇒ (b) 的 `:61` 引用继续成立）、
  G51 重测 `n_bad=0`、全量闸重跑 **PASS 48/0/0/0**（`run_20260930_071824`；17.12 的引用修正后再跑一次仍 **PASS 48/0/0/0** = `run_20260930_073852`）⇒ 补登记未造成任何漂移。
  builder 身份：改前 **3132 ln `10689fdc0c68`** → 改后 **3151 ln `6a03541c262c`**。

**(d) 一条沉默缺口，显式登记（按 D 对 T-C2-6 的同一要求：不许变沉默缺口）**
实测：`BEFORE_IMAGE` / `before_image` / `generator_before_image` 三个词在
`scripts/c2_gate_norm_contract.py` 与 `harness/norm_contract.py` 里的命中数**都是 0**
（只在 builder 里出现：2 / 10 / 1）⇒ **闸侧没有任何 check 审前像块的新鲜度**，
(c) 那名实不符**结构上不可能被闸发现**，只能靠人读。C2 **不自行扩权补牙**（补牙 = 新增 blocking 判据，属 D 裁量），
在此登记为**待触发**：触发条件 = 下一次任何人改 builder；届时应先补一条"前像块最新层的 sha 必须等于实物改前 sha"的牙。

## 17.7 本轮查出并修掉的缺陷（**含 C2 自己犯的**，逐条给检出面）

| # | 缺陷 | 检出面 | 处置 |
|---|---|---|---|
| 1 | 闸里 `red_tags_of` 未定义（NameError） | 实跑 | 已定义；8 个极性构造与 `POLARITY_EXPECT` 逐条相符 |
| 2 | 锚点 **M1** 漂移（分隔符抽成 `nc.RED_MESSAGE_SEPARATOR`） | 本轮全锚点扫描 | 已改锚点 |
| 3 | 锚点 **M5** 漂移（`tooth()` 缩进变化） | 同上 | 已改锚点 |
| 4 | 锚点 **M13** 漂移（allowed 清单由常量改为测量派生） | 同上 | 已改锚点（并去掉 `Tb_scale_floor_effective` 的授权项） |
| 5 | 锚点 **M18** **语义**漂移（文本仍唯一命中，指向的对象已换成 npz 权威臂） | **翻转台账**（25 个 plans 变异体只有 M18 零翻转） | 已重指到 npz 权威块；教训写进闸 `:1300`–:1307 |
| 6 | **G42 分臂缺陷**：baseline 臂合法地有 0 条 measurement clause，却被按"必须有"判 | 实跑 | 改由 3 条**实测 not-applicable** clause 判 |
| 7 | **M28 / M30 臂类别错**（G42 只活在 `MATRIX_PREDS_MAINLINE`） | 实跑 | 已移到 mainline kind |
| 8 | **`tooth2_divergence` 口径错（C2 本轮在自己新代码里先犯一次缺陷类 ⑰）**：首版用**全 matrix 并集**，`Te2` 因 stress/YAM 行**源不匹配**而红 ⇒ 并集里"在"，把「主线 8 行命中 0 行」读成「咬到了」 | 自查 | 改为主线口径（`red_scopes()`）；两个口径**都落盘**并写明为什么 |
| 9 | **G48 一次 KeyError 废掉一整轮全量跑** | 实跑 | 重构为模块级 `ruling_90_4_1_teeth_ledger()`，先用 5 个合成用例单测再接回 |
| 10 | `BEFORE_IMAGE` 块落后一层（名实不符）+ 闸侧无审计方 | 本轮读盘对账 | 见 17.6(c)/(d) |
| — | 3 次 `ast.parse` 未遂（f-string 花括号转义 / 嵌套 ASCII 引号 / 尾逗号变元组） | 写前 `ast.parse` 纪律 | 均在落盘前拦下，未产生坏文件 |

**方法学结论（与 D 本轮立的纪律同源）**：第 5 项证明 **G51（锚点唯一）拦不住语义漂移**——
文本还在、指向的对象已换；**语义漂移的唯一可靠检出面是翻转台账**（每个变异体至少翻一条 check）。
第 8 项证明**报告口径**也会犯缺陷类 ⑰（聚合量掩盖逐臂失效），不只是判据会。

## 17.8 升级项（5 条；标注 existing / new）

- **E1【existing】触发判据的帧口径**：`ruling_90_4_3_trigger.governing_caliber = OPEN_question_to_d`、`triggered = null`。
  实测两口径**结论相反**：held-out（n=547）`dims_below_min_bins=[0,3,5,7,10,12]`、其中**非**近常量 = `[0,5,7,12]` ⇒ 触发；
  全量（n=11035）`dims_below=[3,10]` = 恰好是近常量维 ⇒ 不触发。**C2 不据此升 P0**（升 P0 = 改关键路径，属 D 裁量）。
- **E2【existing，本轮精确到 文件:行号】**：**BC 准入字段是纯标签派生，对数据质量盲**。
  `harness/norm_contract.py:478`–:484 的 `bc_admission()` 判据只有 `prov in BC_ADMISSIBLE_PROVENANCES`；
  `scripts/c2_build_norm_stats.py:2612` 与 `:2857` 的 `"not_for_bc"` 同样只看标签。
  ⇒ **当前实物**：`mainline_status.json` 写着 `admissible_for_bc=true` / `not_for_bc=false`，
  而同一批数据的 `arm_mainline` matrix verdict = **RED**（17.5）。
  **给 A2 的可执行提醒（S3 BC 侧）**：BC 准入必须 **AND 上闸的 verdict / matrix 状态**，
  **不得只读 `admissible_for_bc` 或 `not_for_bc`**，否则会在主线臂 RED 的情况下把 stats 吃进 BC。
  C2 不自决改 `bc_admission()` 的语义（它是裁定 85.4-3 的同源硬闸，改判据 = 改 D 的闸）。
- **E3【本轮由"定性"变"定量"】**：裁定 90.4-1 **牙②** 的字面 id 在真数据主线口径下**不成立**。
  D 的判据文字（`work/project_parameters.json:772` 的 `required_teeth_three` ②）要求
  「把下侧覆盖缩回 `build_only` 的变异体必须让 `Te2_no_illegal_bin_heldout` 红」。
  实测（M21，主线口径 8 行）：`Te2` 命中 **0/8**、`Tcov_declared_interval_covered` 命中 **8/8**。
  根因：formal-40 的 held-out 帧（每方向最后一整集 = `[19,39]`）恰好都落在 build 帧范围内 ⇒ 覆盖集退回 build 帧**不会**产出非法 bin。
  **牙②的字面形式另有证明**：G50 的 `heldout_below_lo` 构造（held-out 下侧越出声明区间 0.005 < 该维 1 bin 头寸 0.015625；
  ① 档 `Te2=PASS`、`build_only` 档 `Te2=RED`，两臂 build/held-out 帧**逐位相同** ⇒ 唯一变量是覆盖目标）。
  **C2 不改 D 的判据文字，只报落点差异。**
- **E4【new】`Tb`/`Tr3` 的 blocking 与阈值状态冲突** —— 见 17.5，甲/乙/丙三选一请 D 裁。**这是主线臂 RED 的唯一驱动，也是 BC 是否还有前置的唯一实质问题。**
- **E5【new，沉默缺口披露】**：`crosscheck_status.checked_at`（生成器 `:2581`）**在闸里没有任何消费方**
  （`crosscheck_status` 只被 `pred_G40` 读 `ruling_90_4_4_compliance` 一项）⇒ 交叉核对臂的
  「落笔时刻真去看过」这条纪律**目前没有牙**。已在闸 `:1308`–:1313 就地登记；
  C2 不自行扩权补牙（交叉核对臂不是 BC 输入，风险不对称，与 D 对 T-C2-6 的处置同理）。

## 17.9 待报项（**只报不改**：都不在 C2 的写入面）

1. **`work/project_parameters.json:768`**（`new_gate_polarity_Tiv.gate`）写的是
   `Tiv_no_state_outside_declared_interval（harness/norm_contract.py:800-825）`。
   实测：该 id 是**已撤回**的旧名（`harness/norm_contract.py:1086` 的 note 与 `:637` 明写撤回），
   活牙 id = **`Tiv_out_of_declared_interval_is_measured`**，位置 = **`harness/norm_contract.py:1072`**。
   ⇒ 该行**id 与行号双过期**。（同块 `:772` 的牙② 见 E3。）
2. **`work/project_parameters.json:688` / `decisions_20260929.md:2502`** 的可推翻条件用 `bins_occupied_median`，
   与 D 本轮新立的 `a_per_dim_failure_mode_must_be_gated_by_a_per_dim_statistic`（`:1126`，= D 同型错误 #16 的纠正）冲突。
   本轮实测两口径给出**相反**答案（median 35.5 ≥ 8 ⇒ 不推翻；逐维 min = 2、不足维含非近常量 `[0,5,7,12]`）。
   与 E1 同源，请一并裁。
3. **`work/project_parameters.json:778`** 的 `trigger_to_promote_to_P0` ② 用的是 `bins_occupied_min`（**逐维，口径正确**），
   与 `:688` 的 median 口径并存 ⇒ 同一份参数表里两个口径守同一件事，建议统一到逐维。

## 17.10 给 B2 的提交请求（**C2 不 `git commit`**，裁定 49.6/69.1/81.2 单写者归 B2）

实测 as_of 07:2x：HEAD = **`0913535`**，工作区脏 **4** 项（B2 本轮已代提交过：`harness/norm_contract.py` 已进 `9c524e4`）。
待提交的 C2 面：

| 文件 | 身份（改后） | 说明 |
|---|---|---|
| `scripts/c2_gate_norm_contract.py` | **3156 ln `3f44225a5fa1`** as_of 07:38:41 | 本轮全部闸侧工作（含 17.12 的两处引用修正） |
| `scripts/c2_build_norm_stats.py` | **3151 ln `6a03541c262c`** as_of 07:17:14 | 含 17.6(c) 的 `BEFORE_IMAGE` 补登记 |
| `scripts/c2_cite.py` | **215 ln `fef07067a2ae`** as_of 06:50:16 | 升级到裁定 92.3 的全仓最低 schema |
| 第 4 项 | `tmp/`（untracked） | C2 的跑日志，**建议不入库** |

提交信息请写明：**`runs/` 被 `.gitignore:12` 排除 ⇒ 本节引用的全部证据（闸 run 目录、前像、matrix、stats）只在 NFS**。

## 17.11 C2 下一步（不插队，等 D 对 17.5 的甲/乙/丙）

1. 若 D 选 **(甲)** 或 **(丙)** ⇒ 改 `Tb`/`Tr3` 的 blocking 或阈值，**必须各配一个变异体**自证
   （`tooth_must_be_mutant_proven`），并重跑全量闸 + 重生成 formal-40 stats（数值不变、`representation_version` 视改动而定）。
2. 若 D 选 **(乙)** ⇒ C2 只把该解释写进闸侧散文与 `mainline_status.json` 的 escalation，不改极性。
3. **T-C2-2（obs 键白名单，含改 `harness/queue_td_learner.py`）** 与 **T-C2-4（闸极性审计）剩余项**不受 17.5 影响，可并行推进。
4. 17.6(d) 的前像审计牙 = **待触发**，不主动扩权。

### 附 17：§17 引用的文件身份（由 `scripts/c2_cite.py` 口径于落笔时刻重读，非手抄；`citation_algo = sha256[:12]`）

| 路径 | sha256-12 | 行数 | 字节 | as_of mtime |
|---|---|---|---|---|
| `runs/vla/c2_norm_contract_20260929/gate/run_20260930_073852/gate_verdict.json` | `ae4e16c33743` | 1534409 | 69440530 | 2026-09-30T07:40:23+08:00 |
| `runs/vla/c2_norm_contract_20260929/mainline_status.json` | `fc3f049753bf` | 6445 | 198907 | 2026-09-30T06:04:23+08:00 |
| `scripts/c2_gate_norm_contract.py` | `3f44225a5fa1` | 3156 | 232798 | 2026-09-30T07:38:41+08:00 |
| `scripts/c2_build_norm_stats.py` | `6a03541c262c` | 3151 | 237751 | 2026-09-30T07:17:14+08:00 |
| `scripts/c2_cite.py` | `fef07067a2ae` | 215 | 12212 | 2026-09-30T06:50:16+08:00 |
| `harness/norm_contract.py` | `43d19a876af1` | 1413 | 103116 | 2026-09-30T06:03:05+08:00 |
| `work/project_parameters.json` | `5a80462e1b12` | 2770 | 412864 | 2026-09-30T04:08:28+08:00 |
| `docs/c2_handoff_to_d_20260929.md`（**追加前**） | `5867798f76b3` | 555 | 49144 | 2026-09-30T01:40:05+08:00 |
| `runs/vla/c2_norm_contract_20260929/before_images/c2_build_norm_stats.py.before_e295544b5431` | `e295544b5431` | 3102 | 232159 | 2026-09-30T05:32:51+08:00 |
| `runs/vla/c2_norm_contract_20260929/before_images/c2_build_norm_stats.py.before_10689fdc0c68` | `10689fdc0c68` | 3132 | 235361 | 2026-09-30T06:03:05+08:00 |
| `runs/vla/c2_norm_contract_20260929/before_images/c2_gate_norm_contract.py.recovered_a1661d37e33e` | `a1661d37e33e` | 3117 | 229760 | 2026-09-30T06:59:03+08:00 |
| `runs/vla/b2_states_14d_20260930/formal40/states_14d.npz` | `a84a26079550` | — | 1332184 | 2026-09-30T05:52:57+08:00 |

## 17.12 【更正框】17.2 的终值已被本轮两次编辑推进 ⇒ 权威跑 = `run_20260930_073852`；**并查出一条元缺陷（审计器模式过窄 ⇒ 报绿而真缺陷不可见）**

> 按 B2 在 §B2-16 立、D 采纳的口径写：「**终值**这种断言只能在『本件已无任何待改项』之后落笔；
> 只要还有可能在同一轮里改它，就写『截至 <时刻> 的值』」。17.2 落笔时本节的两处编辑尚未发生 ⇒ 就地更正并写明理由。

**(1) 时间线（每一步都留了前像，每一次编辑都重跑了全量闸）**

| 时刻 | 动作 | 闸身份 | builder 身份 | 全量闸结果 |
|---|---|---|---|---|
| 07:03:43 | 上一会话最后一次改闸 | `d4ea7043ca94` / 3156 ln | `10689fdc0c68` / 3132 ln（06:03:05） | `run_20260930_070355` **PASS 48/0/0/0** |
| 07:17:14 | **本轮编辑 ①**：builder 的 `BEFORE_IMAGE` 补登记（17.6(c)），+19 行 @ 第 51 行起 | 未动 | `6a03541c262c` / **3151 ln** | `run_20260930_071824` **PASS 48/0/0/0**（`f521b77a58fe`） |
| 07:38:41 | **本轮编辑 ②**：闸里两处**行号引用改名字锚点**（见 (2)），**行数严格不变 = 3156** | `3f44225a5fa1` / 3156 ln / 232798 B | 未动 | **`run_20260930_073852` PASS 48/0/0/0**（`ae4e16c33743`）← **权威跑** |

前像：编辑 ① 前 = `before_images/c2_build_norm_stats.py.before_10689fdc0c68`（3132 ln）；
编辑 ② 前 = `before_images/c2_gate_norm_contract.py.before_d4ea7043ca94`（3156 ln，232575 B）。
两次编辑后 `ast.parse` 均通过；G51 两次重测均 `n_anchors=37 n_bad=0 control_counts=[0]`；
权威跑的全部自证与 17.2 表逐条相同（26/26 变异体自证、48/48 翻转、11/11 探针 `gate_copy_identical_to_real=True`
且副本 sha 全 = `3f44225a5fa1` = 实物）。**⇒ P0 交付物未被本轮编辑损伤。**

**(2) 编辑 ② 的根因：散文里的绝对行号引用会被兄弟文件的任何一次编辑静默推走 —— 本轮实测到两起**

| 位置 | 修前引用 | 实测真值 | 谁推走的 |
|---|---|---|---|
| 闸 `:1309` | `crosscheck_status.checked_at`（生成器 **`:2581`**） | builder **`:2600`**（在 `crosscheck_status = {` 块内，块首 `:2592`） | **本轮编辑 ①**（+19 行 @ :51 ⇒ ≥51 的行全体 +19）。**即：这是我这次补登记自己造成的漂移。** |
| 闸 `:484` | 生成器 **`:2179`** 曾写 `["Td_clip_ratio_cap"]` | 该赋值行现在 **`:2216`**（06:03 那轮之后已在 `:2197`） | **06:03 那轮编辑**（早于本轮，属既有陈旧） |

修法 = **把绝对行号换成 grep 可得的名字锚点**（`crosscheck_status = {` 块内那处 / 行级 `expected_red_teeth` 赋值行），
并**严格保持行数不变**（3156 → 3156）⇒ 编辑 ② 本身**零位移**，可证不会再造新的漂移。
两处都在原行内写明了"为什么不写行号"。

**顺带核清一条容易误判的引用（它是对的，别改）**：闸 `:2173` 写「该副本里 `scripts/c2_build_norm_stats.py:61`
的卫语句 `assert HEADROOM_BINS == 1.0` 仍在位」—— 这是**副本行号**（实物 `:50` + 11 行 `__c2_mutant_identity_hook__`）。
本轮编辑 ① 的插入点在实物第 51 行**之后**，卫语句仍在 `:50` ⇒ 副本仍在 `:61`。
**已实测权威跑的副本**：3162 ln（= 3151 + 11）、`grep -n` 命中 **`:61`** ⇒ 引用继续成立。
但它**脆弱**（依赖 hook 恰好 11 行、恰好插在第 42 行后，且依赖没人改实物第 50 行之前）⇒ 登记为待触发，不在本轮改。

**(3) 元缺陷（本节最有价值的一条）：审计器的模式过窄 ⇒ 它报"干净"，而真缺陷恰好在它看不见的形态里**

本轮先用「完整形态」正则 `(harness|scripts)/…\.py:NNN` 扫四个 C2 文件，结果 =
**4 条引用、越界 0 条**，看起来干净。但上表两起缺陷**一条都没被它抓到** —— 因为它们的形态是
**裸行号** `` `:2581` ``（路径由前文"生成器"二字暗示），完整形态的正则**匹配不到**。
换成裸形态正则 `` `:\d{2,5}` `` 重扫，才命中：harness 13 条（全是 site-packages / `normalize_processor.py` 的外部引用，不在 C2 写入面）+ 闸 2 条（**就是上表那两起**）。

**这与闸自己已经记录在案的一条缺陷同型**：`scripts/c2_gate_norm_contract.py:625`–:628 写明
`TOOTH_ID_RE` 修前是 `\bT(?:[a-z]{1,4})_[A-Za-z0-9_]+`，**匹配不到带数字的牙 id**
（`Td2_…` / `Te2_…` / `Tp5_…`），而"本轮真缺陷恰好就在这些 id 上"。
⇒ **同一个形状犯了两次：审计器的识别模式比它要审的对象空间窄，于是它给出"通过"的形状，而漏掉的正是真缺陷。**
这与红线 `absence_of_measurement_is_not_measurement_of_absence` 同族，但更隐蔽：**它不是"没测"，是"测了、报了绿、而绿是模式窄造成的"**。

**给 D 的建议（C2 不自决，因为这要新增 blocking 判据）**：把「散文引用身份可核」这条红线（裁定 92.3）
**扩一句到"引用形态完备性"**：任何审引用的闸，必须先证明**自己的模式覆盖对象空间的全部形态**
（做法 = 对照探针：故意注入一条已知形态的坏引用，看审计器抓不抓得到；抓不到 ⇒ 审计器自己红）。
本线的 `tooth_name_citation_audit` 已有对照探针思路（`ROW_TAG_IDS` 的源码锚点自证），
但**没有覆盖"裸行号"这一形态** ⇒ 按上述口径，它现在应当对自己报一条"形态不完备"。

**(4) 17.9 待报项的行号，本节已复核**（避免重犯同一类错）：
`work/project_parameters.json` 的 `required_teeth_three` 实际在 **`:772`**（17.8-E3 里写的 `:771` 是 `why_blocking_now`，**已更正为 :772**）；
`BC_ADMISSIBLE_PROVENANCES` 实际在 `harness/norm_contract.py:134`（17.4 里写的 `:133` 已就地更正）；
裁定 87.3-2 的**可推翻条件**在 `decisions_20260929.md:2502`（17.3 里写的 `:2503` 是空行，已就地更正）；
**条件 c 的预登记可证伪预测**在 `:2506`（条件 c 小标题 `:2504`；17.3 里写的 `:2508`–`:2509` 已就地更正，`:2508` 实为 §87.3-3 的小标题）。
`work/project_parameters.json:684` / `:688` / `:778` / `:894` / `:1126` / `:1986` / `:768`
与 `decisions_20260929.md:2501` / `:2670`、`harness/norm_contract.py:478` / `:1072` / `:1086` / `:128`、
`scripts/c2_build_norm_stats.py:2612` / `:2857` 均已逐条 `awk` 取原文核过，无误。
