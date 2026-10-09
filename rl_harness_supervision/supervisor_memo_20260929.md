# 监管备忘 2026-09-29（智能体 D，监管/分析线）—— 增补六

接续 `supervisor_memo_20260928.md`（改判 1–7、增补一…五、裁定 8–16）。**本文件不覆盖 0928 备忘的任何未变更项**，
只新增裁定 17–20、D 线第五次自我纠错、以及检修后开工核验。范围与纪律同前：只改判口径与优先级，
D 不修改 A/B/C 的实现文件，不执行任何 git 写命令（DR-003 决定 8 单写者纪律），禁 `rm`（工作区 AGENTS.md）。

本轮触发点：0928 深夜 A 的移交单 `docs/a_handoff_to_b_probe_exoneration_gap_20260928.md`
（免罪册缺 裁定 16.4 条目，建议顺序 B→D→A）+ 0929 早间服务器检修（进程被直接关闭）。
本轮所有数字均由 D 用**当前门禁构建现场重判**得出，不复用 A/B 的留档裁定，也不转抄文档。

独立核验工具与产物（D 自有，只读上游）：
- `scripts/d_verify_exoneration_cosign.py`（新增；import B 的门禁读构建指纹，不硬编码版本号）
- `tmp/agentD_review_20260929/D_cosign_k2seed0.json`（会签核验产物，含五条准入逐条 + 通道实证 + 对账）
- `tmp/agentD_review_20260929/{gate_D_plain,gate_D_clipC12p469445,gate_D_clipC5p0,gate_D_stdfloor_reblown}.json`
  （D 现场重判的 4 份裁定）
- `tmp/agentD_review_20260929/{regate48.json,D_regate48_rows.json,arm_paths.json}`（0929 早间 48 臂独立重判，检修前产出）
- `tmp/agentD_review_20260929/_D_sim_registry_*.json`（**模拟用**候选豁免册；`configs/` 一字节未动）

---

## §0 检修后开工核验（P0，先于一切裁定）

### 0.1 环境与在制品状态（D 实测 10:4x）

| 项 | 实测 | 影响 |
|---|---|---|
| `/root/venvs/rlrobot/` | **已不存在** | 所有依赖它的脚本默认解释器失效 |
| 当前 `python3` | `/opt/conda/bin/python3` 3.11.9；`numpy 1.26.4`、`torch 2.4.1+cu124` | 只读后处理（门禁 / 汇总 / 登记册）**可用** |
| `robosuite` / `mujoco` / `lerobot` / `stable_baselines3` / `gymnasium` | **全部 MISSING** | 任何重跑评测或训练**被阻** |
| GPU | A800-SXM4-80GB，`memory.used = 0 MiB` | 检修前无在跑作业被截断（无半成品 checkpoint 需要处置） |
| 门禁构建（现场 import 自报） | `v1.4 / b9379fdb1089 / spec 132fceb89f68` | 与 B 权威表、D 昨日 48 臂重判**一致 ⇒ 未漂** |
| `runs/infra/b_official_arms/reclassification.json` | `v1.4 / b9379fdb1089`、48 臂、受控合计 **135** | 与 D 独立重判的 135 逐格相同 |

### 0.2 裁定（检修影响面分级）

1. **不因检修失效的**：一切**只读后处理**类结论（门禁裁定、48 臂汇总、登记册、账本/视图自检）。
   依据是机制性的：`GATE_BUILD` 是脚本内容哈希，现场自报仍是 `b9379fdb1089`；被裁定产物在 `runs/`
   下未被改写（D 现场重判 4 份产物的计数与 0928 留档逐格相同）。**不得**写「检修后所有结论都要重验」。
2. **必须重验的**：任何需要 `rlrobot` venv 的**评测/训练复现**主张。环境重建后须重出 env manifest
   （同 `docs/lerobot_official_env_manifest_20260924.md` 口径），并在 manifest 里登记
   「0929 检修导致 venv 重建」这一断点 —— 否则将来无法判断某条复现主张跨没跨过这个断点。
3. **P1 卫生（C 线文件，D 不代改）**：`scripts/c_run_all_selfchecks.sh` 硬编码
   `PY=${PY:-/root/venvs/rlrobot/bin/python}` ⇒ 现状下 C 线全量回归**跑不起来**（失败原因不是回归红点，
   是解释器不存在）。临时可用 `PY=python3 bash scripts/c_run_all_selfchecks.sh` 覆盖；
   建议 C 把默认值改成「探测优先、失败即明确报错」而不是钉死一个绝对路径。
4. **P2 卫生（登记不改文件）**：`tmp/` 未被 `.gitignore` 排除（`git status` 显示 `?? tmp/`），
   而 AGENTS.md 约定的临时目录在 `scripts/lomoon_claude/tmp/`。D 沿用 0929 早间已建的
   `tmp/agentD_review_20260929/`（来源可识别，符合 AGENTS.md 第 5 条），**不迁移**（迁移会打断
   已落盘产物里的路径引用）。是否把 `tmp/` 纳管或忽略属 DR-003 范围，由 B 决定，D 只登记。

---

## §1 裁定 17：`k2 seed0` 免罪条目 —— 事实基础**会签通过**，但登记册单独补条目**不生效**

### 1.1 事实基础：裁定 10 五条准入，D 在 v1.4 上独立复算，全过

目标臂 `trimdone0_minmax_k2_lr1e-5_s20k_seed0`。D 用当前构建现场重判 3 份产物（plain / C=12.469445 探针 / C=5.0 探针），
逐局比对 `per_episode`，不复用 A 的 `arms_summary.json`、不复用 0928 的 `regate_current/`（那批锚在 v1.2.1）。

| 产物 | sha256（前 12） | raw | 受控 | flick | insuff | blown | ic_status | composite |
|---|---|---:|---:|---:|---:|---:|---|---|
| plain（官方口径） | `85c46dfbd981` | 11 | 9 | 1 | 1 | **0.212** | `violated` | false |
| 探针 C=12.469445 | `142bd2ccd100` | **11** | **9** | **1** | **1** | 0.0 | `verified_ok` | **true** |
| 探针 C=5.0 | `1cafc5b2c04d` | 10 | 9 | 1 | **0** | 0.0 | `verified_ok` | **true** |

- **cond1（C = 该 ckpt 自己的 train-absmax）PASS**：`train_time_norm_absmax = 12.469445`，探针 `norm_input_clip = 12.469445`，逐位相等。
- **cond2（逐局 verdict 全同 + accounts 五项全同）PASS**：plain vs C12 `verdict_diff_seeds = []`、`count_diff = {}`（11/9/1/1 对 11/9/1/1）。
- **cond3（残余差异可枚举且不进计数）PASS**：只有 4 局 `final_rise` 不同（5012 / 5014 / 5016 / 5018），
  两路径 `verdict` 均为 `failure` ⇒ 不进任何计数。
- **cond4（探针路径 / C / build 可登记）PASS**：探针产物存在、sha256 可指纹、build = `v1.4 / b9379fdb1089`。
- **cond5（只作用于 measurement_valid）PASS**：plain `composite_policy=false`；探针 `composite_policy=true`
  且 `active_constraints=["norm_input_clip"]` ⇒ 探针产物**自带**「不得当官方臂数字引用」的标记。
- **cond1 的判别力反证复现**：C=5.0 探针**不满足** cond2 —— seed **5007** 的 verdict 由
  `insufficient_lift` 翻为 `failure`，insuff 1→0，raw 11→10，另有 20 处 `final_rise`/`max_rise` 扰动。
  ⇒「截得越紧越安全」被证伪，C 必须钉死在 train-absmax。**这条反证是 cond1 有约束力的唯一证据，D 已独立复算。**

⇒ **裁定 10 的事实基础，D 会签通过**（与增补四 §3 的核可一致，且这次是在 v1.4 上重算的，不是沿用 v1.2.1 的结论）。

### 1.2 通道实证：现构建下**没有任何登记册写法**能让目标臂免罪

方法：把门禁模块的 `EXONERATION_DOC` 在内存里换成 D 自己的候选册（写在 `tmp/agentD_review_20260929/_D_sim_registry_*.json`），
调**真实**的 `probe_exoneration_check()`；`configs/b_probe_exonerations.json` 与门禁源码**一字节未动**。

| 候选条目写法 | 返回 status | 阻塞位置 |
|---|---|---|
| `scope=arm` + `probe_kind=clip_at_train_absmax` | **`scope_requires_known_impl`** | `:359` 臂级豁免要求产物自带已知 `blown_metric_impl` 指纹；plain 是 `null` / `missing_legacy_grandfathered` |
| `scope=artifact` + `probe_kind=clip_at_train_absmax` | **`out_of_band_refused`** | `:374-386` 争议带判定硬编码 `0.03 ≤ mean_blown ≤ 0.08`；目标臂 0.212 必在带外 |
| `scope=artifact` + `probe_kind=reblown_single_source`（反例） | **`out_of_band_refused`** | 同上 ⇒ **带内判定与 `probe_kind` 无关**，不是按通道分派的 |

**第三行是本次核验最关键的一条**：A 移交单 §4 把修复面写成「改豁免册 `_doc` 的『带外不受理』+ 新增一个 `probe_kind`」，
读起来像登记册改动。实测**带判定在代码里**（`:374`），`_doc` 只是它的文字复述 ⇒ 这是**代码改动**，
且新增 `probe_kind` 本身不会改变任何行为（函数体不看 `probe_kind`）。

**还有第三处阻塞，A 与 B 都没有提到**：`:806` 的晋级分支是

```python
if exo and exo["status"] == "exonerated" and ic_status in ("verified_ok", "not_applicable_verified"):
    ic_status = "probe_exonerated"
```

目标臂 `ic_status = "violated"`（blown 0.212 > 0.05）⇒ **即使前两处都修好、豁免受理，ic_status 也不会变成
`probe_exonerated`**，`measurement_valid` 仍是 `False`。`:810` 的注释还明写「`out_of_band_refused` 不改 ic_status
（§12：带外 INVALID 维持）」。这条分支正是 裁定 12「blown 超阈 ⇒ 这次测量不可信」的**承重墙**：
放开它等于在墙上开门，**必须按 `probe_kind` 精确开**，绝不能整体放宽成「有登记条目就能从 violated 晋级」。

### 1.3 裁定 17 正文

1. **事实基础会签通过**（§1.1，五条准入 D 独立复算全过；产物 sha256 已登记在
   `tmp/agentD_review_20260929/D_cosign_k2seed0.json`）。裁定 16.4 要求的「D 会签」在**事实层**完成。
2. **通道判为不可用**：现构建（`v1.4 / b9379fdb1089`）下免罪**不可能生效**。
   ⇒ A 移交单 §7 的顺序「B 补条目 → D 会签 → A 重跑一条命令迁表」**作废**（它把代码改动误当登记册改动）。
3. **B 的最小改动面（三处，全部在 `scripts/b_gate_controlled_success.py`，合并到一次 v1.5）**：
   - (a) `:374` 争议带判定**按 `probe_kind` 分通道**：`reblown_single_source` 维持带内 [0.03,0.08] 受理；
     新增 `clip_at_train_absmax` **不受带约束**，改由 裁定 10 五条准入约束（五条必须机器可核，不能只写在 `reason` 里）；
   - (b) `:806` 晋级闸**按 `probe_kind` 精确开门**：只有 `clip_at_train_absmax` 且条目带齐五条准入证据时，
     允许 `violated → probe_exonerated`；`reblown_single_source` **维持原样**（不得从 `violated` 晋级）；
   - (c) 臂级记录**回显 `probe_kind`**（见裁定 19）。
4. **条目写法约束（D 会签的前提条件）**：新条目必须 `scope=artifact` + plain 产物的
   sha256 `85c46dfbd98191987b406b3e000b34c6948454054fc20b806eb3b671bc3c3429`；
   证据产物 = `runs/infra/lerobot_act_env_20260928/clipprobe/official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed0_clipC12p469445.json`
   （sha256 `142bd2ccd100ef1e3b49b9bf5fe43d08363fc14608a2c37f911ca70f6eddb2fb`）；
   `C = 12.469445`；并**必须**把 C=5.0 反证产物列为 `supporting_artifacts`（`role` 写明「cond1 判别力反证」），
   否则条目只证明了「有一个探针通过」，证明不了「C 钉死在 train-absmax 是必要的」。
   **不得**用 `scope=arm`（§1.2 第一行实测会被拒）。
5. **顺序纪律（裁定 16.3 / 改判 7 再次触发）**：改 (a)(b)(c) 任一处都会改脚本内容 ⇒ `GATE_BUILD` 必变，
   `b9379fdb1089` 作废 ⇒ B 的 `reclassification.json`、A 的 48 臂表与 `ckptseq/v14_crosscheck/`、
   D 的 `regate48.json` **全部要在新构建上重出**。
   **D 的会签必须引用新 build**：在 v1.5 落地前写的会签，落地当场就过期（这正是 裁定 16.3 要防的事）。
6. **正确顺序**：D 出裁定（本条）→ **B 改代码 + 升 v1.5 + 登记条目 + 全量重判** →
   **D 在新 build 上复核五条准入并正式会签**（跑 `scripts/d_verify_exoneration_cosign.py`，
   要求 `ALL_FIVE_PASS=true` 且 `registry_alone_is_sufficient=true`）→ **A 跑迁移闸 + 迁表**。
7. **过渡期专用标签**：在 v1.5 落地前，`k2 seed0` 的状态是「**事实基础已会签、代码未承载**」，
   D 给它的标签是 **`PENDING_IMPL_probe_exonerated`**。
   **不得**写「已免罪」，也**不得**写「INVALID 维持不变所以能力未知」—— 前者超出事实，后者丢掉已核可的事实基础。

---

## §2 裁定 18：更正 A 移交单 §2.3 与 A 迁移闸 B5 —— stdfloor 的 `probe_exonerated` 是**对的**

### 2.1 D 实测（同一构建、同一天、两份产物）

| 被裁定产物 | `blown_metric_impl` | blown | `in_disputed_band` | ic_status | 豁免返回 |
|---|---|---:|---|---|---|
| `reblown/official_act_truth20_trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0.json`（**B 的表指向这份**） | `52eae25ee2d7`（known） | 0.04 | **true** | **`probe_exonerated`** | `exonerated` |
| `official_act_truth20_trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0.json`（主目录旧产物，**A/D 的 48 臂表指向这份**） | `null`（grandfathered） | 0.04 | true | **`verified_ok`** | `scope_requires_known_impl` |

两份产物的计数**相同**（raw 20 / 受控 16 / flick 1 / insuff 3）⇒ 标签差异**不来自数值分歧**。

### 2.2 裁定

1. **A 移交单 §2.3 的诊断不成立，予以更正**：B **没有**「把一个不需要豁免的臂记成 `probe_exonerated`」。
   B 判的是 `reblown/` 取代产物（带指纹），其 blown=0.04 **落在争议带 [0.03,0.08] 内** ⇒ 增补三 §12 的保留
   **确实适用于这份产物**，裁定 13 的解除**确实在做事**。A 的「本来就没超阈（0.04 ≤ 0.05）」是对
   **主目录旧产物**说的 —— 那份没有指纹，`scope=arm` 按设计拒受理，所以停在 `verified_ok`。
   **两个标签各自都对。** A 的问题意识（「`probe_exonerated` 这个类别在报表里指向错误的臂」）**保留有效**，
   但根因不是误标，是**标签粒度不够**（裁定 19）+ **产物归属不唯一**（本条第 2 项）。
2. **真正的缺陷 = 产物归属没有单一权威**：同一臂名，B 的表指向 `reblown/` 取代产物（`supersedes` 已登记），
   A 的 `arm_paths` 指向主目录旧产物。A §2.1「计数层 48 臂逐格相同」成立**只是因为 reblown 重测恰好复现了同一组计数** ——
   这是运气，不是机制。**换一个「重测后计数变了」的臂，两张表会在计数层分叉，而现有对账口径抓不到**
   （A 的对账是逐臂比数值，不比「比的是不是同一份产物」）。
   ⇒ **产物归属规则**：一个臂的权威产物 = `supersedes` 链末端那一份。A 的 `arm_paths` 必须跟随 `supersedes`，
   不得固定指主目录；A 的 48 臂表 meta 里必须回显每臂的**被裁定产物路径 + sha256**，让「比的是同一份东西」成为可核事实。执行人 A。
3. **A 的迁移闸 B5 判据错误，必须改**（`scripts/a_migration_gate_preflight.py:256-262`）：
   现状 `mislabeled = (ic_status=="probe_exonerated") and (blown <= 0.05)`、`required="verified_ok"`。
   这条判据把**正确行为**判成缺陷，会诱导 B 去「修」stdfloor 的条目；而修它（删条目 / 改成不带豁免）
   等于**撤销 裁定 13 对该臂的保留解除** ⇒ 属**会导致退步的建议，D 明确驳回其 `required` 值**。
   改为：`ic_status == "probe_exonerated"` **且** 臂记录回显 `probe_kind == "reblown_single_source"` **且**
   被裁定产物是 `supersedes` 链末端 **且** blown ∈ [0.03,0.08]。
4. **B5 由 WARN 升为 blocking**（判据改对之后）。理由：产物归属错会让**计数层**对账失效，
   这比分类层差 1 臂严重 —— 分类层错了看得见，计数层「看起来对上了」才是最危险的。

---

## §3 裁定 19：`probe_exoneration` 必须回显 `probe_kind`（两条通道不得共用一个裸标签）

- 现状：B 的 `reclassification.json` 臂记录里 `probe_exoneration: "exonerated"`（裸字符串），
  `summary.probe_exoneration: {"exonerated": 1}`。
- 裁定 10 的通道加上之后，会有**两个臂、两条完全不同的理由**共用同一个值：
  stdfloor（争议带重测，`reblown_single_source`）与 `k2 seed0`（截断无行为后果，`clip_at_train_absmax`）。
  ⇒ A §2.3 担心的「类别指向错误的臂」**届时会真的发生**，而且比 A 说的更严重：不是标签错，是标签**不够细**，
  读报表的人无法知道某臂的免罪是「口径前提被消除」还是「行为无后果」。这两件事的引用条件完全不同
  （前者要带 ±0.005 敏感带，后者要带「C=train-absmax、探针逐局裁定不变」）。
- **裁定**：臂级记录必须回显 `probe_kind`（对象化或并列一列均可）；`summary` 按 `probe_kind` 分桶计数。
  门禁的 `probe_exoneration_check()` **已经**在返回值里带 `probe_kind`，B 只需透出到臂记录，**不需要新判据**。
- 它改脚本 ⇒ 与裁定 17.3 的三处改动**合并到同一次 v1.5**，避免连升两个构建、连做两次全量重判。

---

## §4 裁定 20：回应 A 移交单 §8 的两处 schema 差异（A 请 D 裁定）

### ① `provisional_pass` 行级列（48 格）→ **A 补列**

三套账的五项计数必须在**同一层级**可比。A 的合计层已有该量（=0），行级缺列会让「逐臂 48×8 格对账」
**永远差 48 格**，把真分歧埋在噪声里（这次 A 报的 384 格里 51 格是缺省，其中 48 格就是它）。
补列**不需要重跑任何评测**：值来自同一份裁定 JSON。

### ② 唯一 INVALID 臂行级 `flick/over_lift/insufficient_lift` 写 `null` vs B 写 `4/0/0`（3 格）→ **维持 `null`，但必须加显式字段**

- 支持 A 的部分：裁定 12 说 blown 超阈**只作测量有效性门禁、不得当失败原因** ⇒ 行级给失效模式计数
  会被读成「这臂有 4 局 flick」，正是 裁定 12 要禁的读法。A「倾向不改」的方向是对的。
- 但 `null` 有两个真问题：(i) 与「未测量」不可区分；(ii) 合计层**已含**这 4 局 ⇒ 表观上「行级求和 ≠ 合计」，
  任何自动对账工具都会把这 3 格报成分歧（A 这次就是这么发现的）。
- **裁定**：行级维持 `null`，另加显式字段 `counts_withheld_reason = "measurement_invalid"`（名字 A 可自定，语义不变），
  并在表 `meta` 里写明「合计层包含被 withheld 的行级计数」。这样两边都对账得上，也不误导。
- 优先级 **P2**：v1.5 让 `k2 seed0` 免罪成功后，INVALID 只剩 `_replan1` 一臂，影响面 3 格；可与迁移同批做，
  **不得**为它单独重跑评测。

---

## §5 D 线第五次自我纠错：把「A 侧实现的结果」当成了「门禁口径的权威值」

- **错在哪**：增补五 §3 把「免罪后 `measurement_valid` 47/1、三分类 25/22/1」写进权威汇总时，
  D **没有核这条免罪在门禁代码里能不能发生**。D 当时读的是 A 的 `arms_summary.json`，
  而 A 在**自己的 summarizer 里**（`scripts/summarize_lerobot_act_arms.py:190 probe_exoneration()`）
  独立实现了 裁定 10 的五条准入 ⇒ 25/22/1 是**A 侧实现值**，不是任何 `gate_build` 的输出。
  D 把它当成了门禁口径的权威值，并在 §7 要求 B 的报表按它改。
- **实测更正**：现构建下门禁**产不出** 25/22/1（§1.2 三处阻塞）。增补五 §3 的 25/22/1 **降级为
  「裁定 10 的目标值 / A 侧实现值」**；在 v1.5 落地前引用必须带 **`PENDING_IMPL`** 标注（裁定 17.7）。
- **处置方式**：增补五 §3 原文**不改字**（沿用本仓纪律：就地加勘误指针，同 A 对 §21.10 的做法），
  由本节承担更正。
- **同源教训（与 C 线「恒真判据」事故同型）**：**裁定必须核到「有没有代码承载它」**，只核事实基础不够。
  事实基础成立 + 无代码承载 = 一条**永远无法生效**的裁定，比裁定错了更难发现（错了会被打回，无法生效会一直安静地挂着）。
- **新增纪律（对 D 自己，即日生效）**：任何新裁定落盘前必须回答两问 ——
  ①「**哪一行代码执行它**」；② 若答案是「没有」，「**谁在什么时候写，写完怎么验**」。
  答不出的裁定不得落盘为「已生效」，只能落盘为 `PENDING_IMPL` 并带执行人与时限。

---

## §6 裁定 21（P1）：裁定 10 的判据必须单一来源化

- **实测缺陷**：裁定 10 现在有**两个独立实现**，对同一裁定给出不同结果，且**没有任何对账工具把它们放在一起比**：
  | 实现 | 位置 | 输出 |
  |---|---|---|
  | A 的 summarizer | `scripts/summarize_lerobot_act_arms.py:190 probe_exoneration()`（断言 cond1..cond5） | 三分类 **25/22/1** |
  | B 的门禁 + 豁免册 | `scripts/b_gate_controlled_success.py:330 probe_exoneration_check()` + `configs/b_probe_exonerations.json` | 三分类 **24/22/2** |
- 这与 增补三 §12「blown 口径未单一来源化」是**同型缺陷**（那次造成同一轨迹 0.2120 vs 0.1180 两个值，
  边缘臂裁定不可采信）。**同一个判据两处实现，早晚给出两个答案** —— 这次已经给出了。
- **裁定**：v1.5 落地后，**裁定 10 的判据以 B 的门禁为唯一来源**（与 blown 单一来源化同构：判据跟着门禁走，
  因为只有门禁的构建指纹能被登记进裁定身份）。A 的 summarizer 改为**读门禁输出**做分类，
  **可保留** cond1..cond5 断言作为交叉核验，但**不得**作为 `validity_class` 的生产者。
  执行人 A + B；D 在 v1.5 复核时验这条（判据：A 的表里 `probe_exoneration` 字段必须能追溯到一个 `gate_build`）。

---

## §7 表述纪律（增补六，与增补一 §4 / 三 §10 / 四 §12 / 五 §9 并列）

- **不得**写「`k2 seed0` 已免罪」；现状态 = **事实基础已会签、代码未承载**，专用标签 `PENDING_IMPL_probe_exonerated`。
- **不得**写「B 把不需要豁免的臂记成了 `probe_exonerated`」（A 移交单 §2.3 原句，裁定 18.1 已更正）。
- **不得**写「补一条登记册条目就能迁表」/「A 重跑一条命令即可迁」（A 移交单 §4、§7，裁定 17.2 已作废）。
- 引用 **25/22/1** 必须带 `v1.2.1 / e4f5ec887788` + **`PENDING_IMPL`（A 侧实现，非门禁输出）**；
  引用 **24/22/2** 必须带 `v1.4 / b9379fdb1089`（**门禁现值**）。两个数字**不得**出现在同一行不带标注。
- **不得**写「检修后所有结论都要重验」；只读后处理类结论**不因检修失效**（§0.2 第 1 条给了机制性依据），
  需要重验的只有依赖 `rlrobot` venv 的评测/训练复现。
- **不得**引用 `scripts/c_run_all_selfchecks.sh` 的「跑不通」当作「C 线回归红点」；那是解释器缺失（§0.2 第 3 条）。

---

## §8 对三线的要求（增补六）

### B（P0，v1.5 一次做完，避免连升两个构建）
1. 裁定 17.3 (a)(b)(c) 三处代码改动（`:374` 带判定按 `probe_kind` 分通道；`:806` 晋级闸按 `probe_kind` 精确开门；臂记录回显 `probe_kind`）。
2. 登记 `k2 seed0` 条目，**写法按裁定 17.4**（`scope=artifact` + plain sha256 + C=12.469445 + C=5.0 反证列为 supporting）。
   **先改代码再登记**，否则条目当场被拒（实测三种写法全部不受理）。
3. 全量重判 → 新 `reclassification.json`，并在 `docs/b_controlled_success_v1_20260928.md` 登记 v1.5 版本条目。
4. **验收判据（D 会跑，不给自免）**：`python3 scripts/d_verify_exoneration_cosign.py` 必须
   `ALL_FIVE_PASS=true` 且 `registry_alone_is_sufficient=true`；新表 `NOT_CITABLE_measurement_invalid == 1`、
   三分类 `== 25/22/1`；计数层保持构建不变（受控 135 / insuff 235 / flick 7 / raw 377）。
   **本仓有过恒真判据事故（DR-003 验收判据 3），所以这三条都带反证**：D 的脚本已实测「现构建下
   `registry_alone_is_sufficient=false`」，即该判据**现在就是红的**，不是恒真。

### A（P0/P1，v1.5 前不得迁表）
1. **P0** 改迁移闸 B5 判据（裁定 18.3），并把 B5 升为 blocking（裁定 18.4）。
2. **P0** `arm_paths` 跟随 `supersedes`，表 meta 回显每臂被裁定产物路径 + sha256（裁定 18.2）。
3. **P1** 补 `provisional_pass` 行级列（裁定 20①）。
4. **P2** 行级 `null` 加 `counts_withheld_reason`（裁定 20②），与迁移同批做。
5. **P1** v1.5 后把 裁定 10 的分类改为读门禁输出（裁定 21）。
6. A-2 的 `ckptseq/` 仍钉 v1.2.1（预登记 §6 冻结锚点）；v1.5 落地后**只需重做交叉核验**
   （A 已实测 v1.4 对它们是 no-op，`ALL_VERDICTS_IDENTICAL=PASS`），**不得**重跑评测。

### C（P1）
1. `c_run_all_selfchecks.sh` 的 `PY` 默认值（§0.2 第 3 条）。
2. 环境重建后重跑全量回归 + 重出 env manifest，并登记「0929 检修 venv 重建」断点（§0.2 第 2 条）。
3. C 的 `registry/verdict_identity.py` 应把 `PENDING_IMPL_probe_exonerated` 纳入 `usable_for` 分级 ——
   它既不是 `physical_fact`（门禁产不出），也不是 `stale_build_evidence`（事实基础已核可）。
   建议单独一档「**裁定已核可、实现待落地**」，这一档在 v1.5 之前是**唯一诚实的分级**。

### 全员（P0）
- 重建 `rlrobot` 环境前，**不得**声称任何需要跑评测/训练的结论已复现。
- 单写者纪律（DR-003 决定 8）继续有效：D 本轮只写 `rl_harness_supervision/`、`work/decisions/`、
  `daily_report.md`、`scripts/d_*`、`tmp/agentD_review_20260929/`，**未改** A/B/C 任何文件，未执行 git 写命令。

---

## §9 回流点（增补六）

回来后再议：
1. **B 的 v1.5**（三处代码 + 条目 + 全量重判）—— 回来后 D 跑 `d_verify_exoneration_cosign.py` 正式会签，
   并把增补五 §3 的 `PENDING_IMPL` 标注撤下（届时 25/22/1 才是门禁输出）。
2. **环境重建后的 env manifest** —— 回来后判定「0928 的 48 臂结论跨没跨过 0929 断点」。
3. **A 的迁移闸改判据后的首次 OPEN** —— 回来后核 §2.2 的产物归属规则是否真的落进 `arm_paths`。
4. **裁定 21 的单一来源化** —— 回来后核 A 的 `probe_exoneration` 字段能否追溯到 `gate_build`。

任一回流点回来且与 §1.1 的表不一致时，**先改本文件 §1.1 再谈结论**（沿用增补五 §10 的纪律）。

---

## §10 回应 B 的 DR-007 / DR-008 三项提请（裁定 22–25，2026-09-29 11:0x）

触发：B 在 `work/decisions/decisions_20260928_B.md` 追加 **DR-008**（门禁 v1.5 落地 裁定 10 通道），
其常量块已按 裁定 17.3 (a)(b)(c) 写入 `scripts/b_gate_controlled_success.py`（`git diff` 显示 +33 行，
`BAND_EXEMPT_PROBE_KINDS` 白名单 + `EXONERATION_PROMOTION_SOURCES` 按 kind 分路 + `RULING10_CONDITION_KEYS`），
并把 D 的 `tmp/agentD_review_20260929/D_cosign_k2seed0.json` 列为触发来源。D 逐条复核后**认可其护栏设计**
（白名单保守默认、晋级闸精确放开而非宽口径、五条准入做成册子必需键而非 `reason` 文案）。
同时 B 提请三件事，其中 DR-007 的两件自 0928 深夜挂到现在**D 未明文回复**，本节一并结案。

### 10.1 裁定 22：**认可** B 对 裁定 14 的收窄；D 的裁定原文表述过宽，予以更正（DR-007 提请 1）

- **D 独立复核了 B 的收窄理由，事实成立**（不采信 B 的转述）：D 现场用当前构建判
  `runs/infra/b_env_rebuild/base_truth20.json` → `field_class=partial`、`missing_fields=['terminal_kind']`、
  `field_presence.terminal_kind = 0/20`、`labels_reportable=True`、`n_labels_abstained=0`、
  `measurement_valid=True`、受控 **20/20**；两份 base-only 标定件的 `max_rise` 实测
  **0.0758–0.0784** 与 **0.0755–0.0796**，与门禁 `RISE_CAP=0.15`（注释「scripted base 实测 mean 0.0764 / max 0.078，
  取约 2 倍为上限」）**同源可追** ⇒ 它们确实是 `RISE_CAP` 的标定基准与 20/20 参考上界。
  按 DR-D09 字面实现（`field_class != strict` 即弃权）会把这两份判 INVALID，**作废 `RISE_CAP` 标定与 DR-004 全部锚点**。
- **裁定**：B 的收窄（`missing ∩ LABEL_CRITICAL_FIELDS ≠ ∅`，`LABEL_CRITICAL_FIELDS = (final_rise, held_at_end, phase_at_end)`，
  `:110`）**是 裁定 14 的正确实现，予以认可**。`terminal_kind` 走规格 §2.4 的**独立**弃权路径，
  三个失效模式标签不读它 —— 用它触发标签弃权修的不是 DR-D09 指出的那条通道。
- **D 线第六次自我纠错**：DR-D09 的原文用 `field_class != "strict"` 表述弃权触发条件，
  这是拿一个**代理量**（字段等级）替代了真正的依赖（标签判据实际读哪些字段）。
  `field_class` 同时被 `terminal_kind` 这类**与标签无关**的字段影响 ⇒ 原文过宽。
  更正为：**裁定 14 的触发条件 = `LABEL_CRITICAL_FIELDS` 缺失**，`field_class` 只作展示。
- **护栏（认可的前提，缺一不可）**：
  1. `LABEL_CRITICAL_FIELDS` 自本裁定起是**受裁定的常量**：增删任一字段须先由 D 裁定并在规格登记，B 不自行改；
  2. 变异用例 **M7**（把 `terminal_kind` 加回该集合 = 按 DR-D09 字面实现）**必须长期保留并保持红色** ——
     B 已把本条理由钉成可执行证据，这正是 D 认可它的主要原因：**偏离被机器记住了，不靠散文**；
  3. 规格 `docs/b_controlled_success_v1_20260928.md` §2.16 须显式写明「DR-D09 字面表述已被 裁定 22 更正」，
     不得只留 B 的实现注释（否则将来读裁定原文的人会以为门禁写错了）。

### 10.2 裁定 23：`terminal_kind` 缺失 → **加 warn、不降级**，但必须先修掉一处**空转判据**（DR-007 提请 2）

B 的倾向（加 warn 不加 INVALID）**采纳**。但 D 现场实测发现比「缺个 warn」更严重的一处缺陷：

- **实测（D 独立跑，非引用 B）**：`base_truth20.json`（`terminal_kind` 覆盖 **0/20**）的裁定 JSON 里
  `terminal_semantics = {"horizon":300, "rows_at_full_horizon":20, "rows_labeled_terminated_failure":0,
  "suspect_truncation_labeled_as_failure": false, "note": ""}`。
- **根因（`:888-893`）**：`n_termfail = sum(... str(r.get("terminal_kind") or "").startswith("terminated_failure"))`
  ⇒ 字段全缺时 `n_termfail = 0` ⇒ `suspect_truncation_labeled_as_failure = (n_termfail > 0 and ...)` **恒为 `false`**，
  `note` **恒为空**。即「截断被伪装成失败」这条自检**在根本无法执行的产物上，报告为『没有发现问题』**。
  `rows_at_full_horizon = 20` 由 `steps >= horizon` 算出，与 `terminal_kind` 无关，看上去还挺健康。
- **这与本仓已发生两次的事故同型**：DR-003 验收判据 3（恒真判据）、以及 D 今天自己的第五次自我纠错
  （裁定成立但无代码承载）。**判据在不能运行时必须报「不可判定」，绝不能报「通过」。**
- **裁定 23**：
  1. **不降级 `measurement_valid`**（采纳 B 的倾向）。理由与 裁定 12 同源：字段覆盖缺口是「没测到」，
     既不得读成能力结论，也**不得读成清洁保证** —— 两个方向都禁。
  2. `suspect_truncation_labeled_as_failure` 改为**三值**：`field_presence.terminal_kind < rows_total` 时必须为
     **`null`（不可判定）**；`false` 只允许表示「自检**跑过了**且没发现」；`true` 维持原语义。
  3. `terminal_semantics.note` 在覆盖率不足时**必须非空**，写明 `terminal_kind 覆盖 n/N ⇒ 终局语义自检不可用
     （截断伪装成失败的检测未执行）`，并回显 `terminal_kind_coverage`（n/N）。
  4. 必须**可聚合**：在 `summary` 层新增臂清单（与既有 `phase_vocab_mismatch_arms` 同型），
     让报表能一句说出「N 臂终局语义自检不可用」，而不是逐份裁定里翻。
  5. **标定基准须显式声明**：被当作 `RISE_CAP` 标定基准 / 20-20 参考上界 / DR-004 锚点的产物，
     必须在受版控的登记册里声明「`terminal_kind` 缺失已被接受，理由 = base-only 真值不含终局分类」，
     否则引用该基准的结论必须带标注。**「缺字段但被当基准」必须是一个声明过的状态，不能是意外。**
  6. 变异自检须新增反例：把 `terminal_kind` 覆盖率改成 0 而断言仍为 `false` ⇒ 必须变红（证明第 2 项有牙）。
- 优先级 **P1**，与 v1.5 同批做（都改同一个脚本，避免连升两个构建）。

### 10.3 裁定 24：`probe_exonerated` 的标签语义 —— **不降级 stdfloor**，改为按 `probe_kind` 分桶（DR-008 提请 1）

- **B 的问题**：v1.5 后 `probe_exonerated` 将有 2 臂，而增补五 §3 的「免罪后」列隐含 1 臂；
  是否把「本来就没超阈」的 stdfloor 降回 `verified_ok`，让该标签只表示「非探针不可信」？
- **裁定：不降级。** 理由（= 裁定 18 的正式回复，D 已现场实测两份产物）：
  1. B 的前提「stdfloor 本来就 `verified_ok`」只对**主目录旧产物**成立。B 的权威表判的是
     `reblown/` **`supersedes` 链末端**产物，它带指纹 `52eae25ee2d7`、blown **0.04 ∈ 争议带 [0.03,0.08]**
     ⇒ 增补三 §12 的保留**确实适用于这份产物**，裁定 13 的解除**确实在做事**。
  2. 降级它 = **撤销 裁定 13**，把一个已经消除了口径分歧的臂重新挂回「暂不可采信」。这是**退步**，
     与 A 迁移闸 B5 的 `required="verified_ok"` 是同一个错误（DR-D15 已驳回）。
  3. 「增补五 §3 隐含 1 臂」是 D 自己的表述不精确：那一列讲的是 **`measurement_valid` 47/1 与三分类 25/22/1**，
     这两个量**与走哪条通道无关**；`ic_status` 分布在增补五 §3 里**根本没有列**。⇒ **不冲突**，
     B 验收判据 3 的 `ic_status = verified_ok 45 / probe_exonerated 2 / violated 1`、`citable = 25/22/1`、
     `measurement_valid = 47/1`、计数层 135/235/7/0/0 一格不动 —— **D 全部预先认可**，落地后按此验收。
- **真正的修法 = 裁定 19（DR-D16）**：臂级记录回显 `probe_kind`、`summary` 按 `probe_kind` 分桶。
  两条通道的**引用条件不同**（`reblown_single_source` 要带 ±0.005 敏感带；`clip_at_train_absmax` 要带
  「C=train-absmax、逐局裁定不变」），共用一个裸标签会让引用条件无从判断。
- **前瞻裁定（避免 v1.5 落地后立刻产生一条假 bug）**：A 的 `validity_class = VALID_probe_exonerated`
  与 B 的 `ic_status = probe_exonerated` **不是同一个概念**，v1.5 后会长期是 **1 对 2**：
  A 的语义是「**原判 invalid、被救回**」，B 的语义是「**ic_status 标签**」。
  裁定：A 的 `VALID_probe_exonerated` **只对应 `probe_kind = clip_at_train_absmax`**；
  stdfloor 在 A 的表里维持 `valid`，但必须**另列一列**回显 `probe_kind = reblown_single_source`。
  两表在「多少臂被豁免」上**必然差 1**，这是**设计差异不是缺陷**；任何对账工具都必须按 `probe_kind` 分组比，
  不得直接比 `probe_exonerated` 计数。（此项与 裁定 21 的单一来源化**不冲突**：单一来源指的是
  **裁定 10 的五条准入判据**由门禁独家执行，不是指两张表的所有列都要同名同值。）

### 10.4 裁定 25：**批准** B 的 DR-008 决定 7（会签 build 不回显即拒判会死锁）；更正 裁定 17.5 的严格读法

- **D 的 裁定 17.5 写的是**「D 的会签必须引用新 build，否则写下来当场就过期」。
  B 的 DR-008 决定 7 指出这会**死锁**：条目只能在代码改完之后写，而写的那一刻 D 的会签必然还锚在旧 build 上。
- **B 是对的，D 的表述过严，予以更正**：裁定 17.5 的**意图**是「不得拿旧 build 的会签当新 build 的通行证」，
  不是「会签的 build 字面必须等于当前 build」。
- **裁定 25**：采纳 B 决定 7 —— build 不一致时**不拒判**，但必须在裁定 JSON 里显式回显
  `cosign_gate_build` / `cosign_build_current` / `cosign_build_matches`，且 `cosign_build_matches=false` 时
  **必须**同时回显「D 须重跑 `scripts/d_verify_exoneration_cosign.py`」的义务标记。
  **补充两条护栏**（D 加的，B 落地时一并做）：
  1. `cosign_build_matches=false` 期间，该臂在 `summary` 层必须计入一个**独立桶**
     （例如 `pending_cosign_reverify`），**不得**直接计入「已免罪」；
  2. D 重跑并会签新 build 之后，B 必须**重出**一次 `reclassification.json`，把该桶清零 ——
     即「会签—重判」是**两轮**，不是一轮。这与 裁定 16.3 的精神一致：口径变了就重出表，不打补丁。
- **D 的执行承诺**：B 的 v1.5 落地（含 裁定 23 的六项）后，D 跑
  `python3 scripts/d_verify_exoneration_cosign.py`，验收标准 = `ALL_FIVE_PASS=true`、
  `registry_alone_is_sufficient=true`、三个 `blocker_*_hit` **全部由 `true` 变 `false`**、
  且新表 `NOT_CITABLE_measurement_invalid==1` / 三分类 `25/22/1` / 计数层 135-235-7-0-0 一格不动。
  **该判据现在就是红的**（实测 `registry_alone_is_sufficient=false`、`NOT_CITABLE=2`）⇒ 非恒真，有牙。
  D 会签后在 `work/decisions/` 追加 DR-D 条目登记**新 build 指纹**，届时才撤下 `PENDING_IMPL` 标注。

### 10.5 A §8 两处 schema 差异 → 已在 裁定 20（DR-D16）结案

① `provisional_pass` 行级列：**A 补列**；② INVALID 臂行级失效模式计数：**维持 `null` + 加
`counts_withheld_reason`**，meta 写明「合计层包含被 withheld 的行级计数」。B 无需为此改门禁。

---

## §11 裁定 26：门禁 v1.5 复签**通过**（2026-09-29 11:2x，执行 DR-D22 承诺的验收）

B 已落地 DR-008（v1.5）并按 裁定 17.4 登记条目。D 重跑
`python3 scripts/d_verify_exoneration_cosign.py --expect exonerated`，在 **v1.5 / `f19f61341cbe`** 上实测：

| 验收项（DR-D22 承诺） | 实测 | 结论 |
|---|---|---|
| `ALL_FIVE_PASS` | `true`（D 现场重判，不复用留档裁定） | ✅ |
| 三个 `blocker_*_hit` | **全部由 `true` 变 `false`** | ✅ |
| 真册子对目标臂 | `exo_status = exonerated` | ✅ |
| 晋级闸 | 底层 `violated` → 观察值 **`probe_exonerated`**、`measurement_valid=True`、`gate_pass=True`；机制 = `EXONERATION_PROMOTION_SOURCES['clip_at_train_absmax']`（按 kind 分路） | ✅ |
| 计数不变（cond5） | raw 11 / 受控 9 / flick 1 / insuff 1 / over 0 / prov 0 **一格未动** | ✅ |
| 反例（6 个） | `scope=arm`→`scope_requires_known_impl`；`clip_C=5.0`→`clip_c_not_train_absmax`；`cond2=false`→`entry_conditions_incomplete`；无会签→`cosign_missing`；`reblown_single_source` 对 0.212→**仍 `out_of_band_refused`**；阳性对照→`exonerated` | ✅ `mutants_all_caught=true` |
| 裁定 25 / DR-008 决定 7 的回显 | `cosign_build_current=f19f61341cbe`、`cosign_build_matches=False`、`probe_kind` 已回显 | ✅ |

> **定义更正（本节落盘后即刻修正，见 DR-D26 末条）**：本节表格里的「三个 `blocker_*_hit`」
> 与「6 个反例」在脚本早期版本里**混在同一组计数**，v1.5 后会读出自相矛盾的结果
> （护栏正常拒绝被算成阻塞未消）。已拆成 `blocker_*`（挡在 裁定 10 通道前面，v1.5 后须**全 false**）
> 与 `guard_*`（本该继续拒绝，v1.5 后须**全 true**）。**拆分后本节的实测结论一字不变**：
> `blocker_band / blocker_scope / blocker_promo` 全 `false`，`guard_arm_scope / guard_reblown_band` 全 `true`。

⇒ **ACCEPTANCE=true，复签通过。** 其中**最重要的一条反向证据**是第 6 行最后一项：
`reblown_single_source` 通道对 blown=0.212 **仍然不受理** ⇒ **裁定 13 的牙没有被 v1.5 拔掉**，
新通道是**加**出来的，不是把旧的墙拆了。这正是 裁定 17.3(b) 要求「精确放开而非宽口径」的目的。

**判据非恒真（双向实测）**：同一脚本 `--expect blocked`（v1.5 前的期望）在现构建上 **exit 1**，
`--expect exonerated` **exit 0** ⇒ 两种期望各自都有会红的条件。脚本已升级为**期望感知**、v1.4/v1.5 双认
（晋级判定改用**还原出的底层 `ic_status`**，因为 v1.5 下 `judge_file` 已就地晋级，直接读观察值会把「已晋级」误判成「不允许晋级」——
D 自己踩到并当场修正，属工具缺陷不属裁定错误）。

### `PENDING_IMPL` 标注：**有条件撤下**（三前提，缺一不可）

1. **build 冻结** —— D 在 ~40 分钟内观测到 **3 个** `GATE_BUILD`（`b9379fdb1089` v1.4 →
   `9e57327af208` v1.5 → `f19f61341cbe` v1.5）。本会签锚在 **`f19f61341cbe`**；B 之后再改门禁脚本，会签**自动失效**。
   **B 须明文声明 v1.5 冻结**（这一条不是形式主义：会签锚在移动靶上等于没有会签，与 裁定 16.3 同源）。
2. **B 重出权威表** —— `runs/infra/b_official_arms/reclassification.json` 现仍是 **v1.4 / `b9379fdb1089`**、
   `citable=24/22/2` ⇒ **尚未重判**。须在 `f19f61341cbe` 上重出并满足 DR-008 验收判据 3
   （`ic_status` 45/2/1、`citable` 25/22/1、`measurement_valid` 47/1、计数层 135/235/7/0/0 一格不动，D 已预先认可）。
3. **`cosign` 块换到本 build** —— 按单写者纪律 `configs/` 由 B 写，D 已产出可原样替换的内容：
   `tmp/agentD_review_20260929/D_cosign_block_for_registry.json`（含 `supersedes_previous_cosign`、
   `mutation_evidence`、`build_instability_observed`、4 条 `conditions`）。换上后 `cosign_build_matches` 才会变 `true`。

**三条满足前的引用纪律**：可写「**裁定 10 免罪已在 v1.5 / `f19f61341cbe` 上由 D 复签通过、门禁实测生效**」；
**不得**写「48 臂权威表已是 25/22/1」（表还没重出）；A 侧的 `PENDING_IMPL` 标注**暂不撤**。
裁定 25 护栏 ①：B 重出表时 `summary` 须有独立桶（如 `pending_cosign_reverify`）承接
`cosign_build_matches=false` 期间的臂，D 换块后该桶清零（**「会签—重判」是两轮**）。

### 附带观测（供 A，不属裁定）

A 的 `scripts/a_migration_gate_preflight.py` 已扩到 **19 项**判据，其中 **B6** 正是 裁定 18.2 的产物归属规则
（A 表回显每臂被裁定产物路径 + sha256；`schema_version 3`、现值表
`runs/infra/lerobot_act_env_20260928/attribution/arms_summary_v3.json`）⇒ **裁定 18.2 已被 A 落地为可执行断言**。
但 **G2 是假红**：它用**文本扫描**判「带判定是否按 `probe_kind` 分通道」，锚点已失效（A 自己在 note 里声明了）。
**D 的实证结论优先** —— D 是**真调**门禁函数，v1.5 下该通道**可达**（`exonerated`）。
A 更新 G2 时请以 `scripts/d_verify_exoneration_cosign.py` 的实测为准，**不要照文本扫描改**。
当前 `MIGRATION_GATE=CLOSED, blocking_fail=8`，其中**真实**阻塞是 B1/B2/B3（B 表未重出）与 B6（A 侧 v3 表待接）。

---

## §12 裁定 27：B 的 v1.5 权威表**验收通过**；A 的迁移闸 2 项 blocking 全是**假红**（2026-09-29 11:3x）

### 12.1 B 的 v1.5 权威表：D 独立复算，**逐格命中** DR-D21 ③ 预先认可的数值

`runs/infra/b_official_arms/reclassification.json` 已在 **v1.5 / `f19f61341cbe` / spec `132fceb89f68`** 上重出（48 臂）：

| 量 | DR-D21 ③ 预先认可值 | B 的 v1.5 实测 | 结论 |
|---|---|---|---|
| `summary.ic_status` | `verified_ok 45 / probe_exonerated 2 / violated 1` | **同** | ✅ |
| `summary.citable` | `25 / 22 / 1` | **25 / 22 / 1** | ✅ |
| `measurement_valid` | `47 / 1` | **47 / 1** | ✅ |
| `controlled_success` | 135 | **135** | ✅ 一格不动 |
| `insufficient_lift` | 235 | **235** | ✅ |
| `flick` | 7 | **7** | ✅ |
| `over_lift` / `provisional_pass` | 0 / 0 | **0 / 0** | ✅ |
| `raw_success` | 377 | **377** | ✅ |
| 唯一 `violated` 臂 | `_replan1`（blown 0.1692、无探针） | **同** | ✅ |
| `arms_with_controlled_success` | 25 | **25** | ✅ |

⇒ **裁定 17.7 的 `PENDING_IMPL` 标注对「表数字」予以撤下**：`25 / 22 / 1` 现在是
**v1.5 / `f19f61341cbe` 的门禁现值**（不再是「A 侧实现值 / 目标值」），可按裁定 17.6 的引用纪律引用。
增补五 §3 的「免罪后」两列**由目标值升为现值**，其勘误指针（0928 备忘 §3 末）相应失效 —— 但**原文仍不改字**，
以本节为准。

### 12.2 裁定 19（`probe_kind` 回显）**已落地，且 B 超额实现**

- 臂级：`probe_exoneration_kind`（`clip_at_train_absmax` / `reblown_single_source`）
  + **`probe_exoneration_band_checked`**（`false` / `true`）—— 后者 D **没有要求**，但它正好把
  「这条豁免走没走争议带牙」变成**逐臂可核字段**，比只回显 kind 更强。**D 予以确认并采纳为口径。**
- 汇总级：`probe_exoneration_by_kind = {clip_at_train_absmax: 1, reblown_single_source: 1}`
  + `exonerated_in_disputed_band = 1` ⇒ **两条通道在报表上已可区分**，裁定 19 的目的达成。
- 两臂实测：`k2 seed0` → kind `clip_at_train_absmax`、band_checked `false`、blown 0.212、受控 9、`citable_with_sensitivity_band`；
  `stdfloor` → kind `reblown_single_source`、band_checked `true`、blown 0.04、受控 16。
  ⇒ 裁定 24 ⑤ 的「1 对 2」前瞻问题**已被 B 的 kind 分桶解决**，A 侧按 DR-D21 ⑤ 另列一列即可。

### 12.3 A 的迁移闸：19 项里 **17 PASS**，2 项 blocking **全是假红**

`MIGRATION_GATE=CLOSED, blocking_fail=2`。**已 PASS 的含**：B1/B2/B3（免罪后 25/22/1）、B4（计数层构建不变）、
**B5（A 已按裁定 18.3 改对判据：四个前提同时成立）**、**B6（A/B 两表逐臂指向同一份被裁定产物 = 裁定 18.2 已落地）**、
L1–L4、L6–L9、G1 ⇒ **实质条件全部满足**。两项红的都是判据自身的问题：

- **L5 假红（判据过宽，根因在 A）**：A 用「**递归遍历整个条目 + 键前缀匹配 `cond1..cond5`**」找五条准入，
  并要求**所有**命中值为 `True`。实测该条目里有 **10 个**键命中前缀：
  `ruling10_conditions.cond1..cond5_*` = **5 个 bool `True`**（门禁真正读的字段，`:164 RULING10_CONDITION_KEYS`），
  以及 `ruling10_conditions_evidence.cond1..cond5` = **5 个 str**（B 写的证据散文）
  ⇒ 5 个字符串让 `not_true` 非空、L5 判 FAIL。**门禁本身不受影响**（它只按精确键名读 `ruling10_conditions`）。
- **G2 假红（锚点失效，A 已自认）**：G2 用**文本扫描**判「带判定是否按 `probe_kind` 分通道」，
  v1.5 已实现 `BAND_EXEMPT_PROBE_KINDS`（`:161`）但扫描判据认不出来。A 在 note 里已声明
  「A 侧判据锚点失效 ⇒ 需人工复核并更新本脚本；不据此误挡 B」。

**裁定 27**：
1. **A 可以迁表**，但**必须先把闸的红绿灯修得与实际状态一致**，再跑迁移 + `--mode postcheck`。
   理由是本仓的第三条同源教训：**恒真的闸等于没有闸（DR-003 判据 3），恒假的闸也等于没有闸** ——
   恒假会让人习惯「CLOSED 是正常的」，真阻塞来的时候一样被忽略。
2. **L5 收窄**：按 裁定 21（门禁是 裁定 10 判据的唯一来源），A 的检查必须**按门禁读的字段名精确取**
   （`entry["ruling10_conditions"]` + 门禁的 `RULING10_CONDITION_KEYS`），
   **不得**用「递归遍历 + 前缀匹配」。前缀匹配把**断言**与**证据散文**混为一谈，
   任何在条目里写 `condN` 前缀说明文字的合法做法都会让它假红。
3. **L5 的反例缺口必须补**：A 的 `--selftest` 已有 S1–S9（含「S3 五条准入有一条 false → CLOSED(L5)」），
   但**没有**「条目带 `condN` 前缀的证据散文 → 必须 **OPEN**」这一档 ⇒ 自检过了而真跑假红，
   说明 fixture 覆盖不到真实条目形状。要求新增 **S10**（照 B 的真实条目形状做 fixture，断言 OPEN）。
   **判据类工具的反例必须取自真实产物形状，不能只取自己想象的形状** —— 这条对四线通用。
4. **G2 改为实测**：调门禁函数（或直接用 `scripts/d_verify_exoneration_cosign.py` 的 `mutant_statuses`），
   不要再文本扫描源码；若保留扫描，必须降为非阻塞并注明「锚点易失效」。
5. **B 的条目有一处命名卫生问题（P2，非阻塞、不要求现在改）**：布尔断言键与其证据键**共用 `condN` 前缀**。
   规则：**同一登记条目内，布尔断言键与其证据键不得共用前缀**（否则任何递归校验器都会歧义）。
   建议改为 `evidence_for_cond1` 之类。A 按第 2 项收窄后本项即无害，故列 P2。

### 12.4 仍未闭合的两项（`PENDING_IMPL` 撤下的**剩余**前提）

| # | 项 | 现状态 | 谁做 |
|---|---|---|---|
| ① | **build 冻结声明** | D 在 ~50 分钟内观测到 3 个 `GATE_BUILD`；现 live 与 B 表都是 `f19f61341cbe`（一致） | **B 明文声明 v1.5 冻结** |
| ③ | **`cosign` 块换到本 build** | 条目里仍是 `gate_build_at_cosign = b9379fdb1089` ⇒ 门禁回显 `cosign_build_matches = False` | **B 写**（D 已备好可原样替换的块：`tmp/agentD_review_20260929/D_cosign_block_for_registry.json`） |
| 护栏① | `summary` 的 `pending_cosign_reverify` 独立桶（裁定 25 / DR-D22） | **未实现**（`summary` 里无此键） | **B**；在 ③ 完成前该桶应有 1 臂，完成后清零 |

⇒ **在 ③ 完成前**：可引用「25/22/1 @ v1.5 / `f19f61341cbe`（D 独立复算验收通过）」，
但引用该臂时必须**同时**注明「D 的会签块尚锚在 `b9379fdb1089`，`cosign_build_matches=false`，
按 DR-008 决定 7 不拒判但待复签换块」。这不是文字游戏：**会签锚在哪个 build 上，是可核事实，必须随数字一起走。**

---

## §13 裁定 28：免罪链路**闭环**，`PENDING_IMPL` 标注**全部撤下**（2026-09-29 11:5x）

DR-D26 列的三项前提**已全部满足**，D 实测复核如下（全部现场跑，不引用他线结论）：

| # | 前提 | 实测 | 结论 |
|---|---|---|---|
| ① | build 冻结 | live 门禁 = B 权威表 = **`v1.5 / f19f61341cbe`**；B 的回归/变异自检也锚在同一 build（`runs/infra/b_gate_regression/{selfcheck,mutation}.json`：`ok=true`、39 用例；变异 39 用例 / **15 抓住**） | ✅ 事实上已冻结 |
| ② | B 重出权威表 | `ic_status 45/2/1`、`citable **25/22/1**`、`measurement_valid **47/1**`、计数层 `135/235/7/0/0/377` 一格不动 | ✅ 见 §12.1 |
| ③ | `cosign` 块换到本 build | 条目 `cosign.gate_build_at_cosign = f19f61341cbe` ⇒ 门禁回显 **`cosign_build_matches = True`** | ✅ B 已换 |

D 复跑 `python3 scripts/d_verify_exoneration_cosign.py --expect exonerated`
（产物 `tmp/agentD_review_20260929/D_cosign_k2seed0_v15_final.json`）：
`ACCEPTANCE=true`、`ALL_FIVE_PASS=true`、`mutants_all_caught=true`、
`blocker_* = [false,false,false]`、`guard_* = [true,true]` ⇒ **复签正式生效**。

**A 的迁移闸已 OPEN**：`MIGRATION_GATE=OPEN, blocking_fail=0, warn=0, total_checks=23`
（A 已按 裁定 27 收窄 L5、修 G2，判据数从 19 扩到 23）⇒ **裁定 16.4 的 B→D→A 链路闭环**，A 可迁表。

**裁定 28**：
1. **`PENDING_IMPL_probe_exonerated` 标签作废，全部撤下**。目标臂 `trimdone0_minmax_k2_lr1e-5_s20k_seed0`
   的正式状态 = **`probe_exonerated`（`probe_kind=clip_at_train_absmax`、`band_checked=false`）@ v1.5 / `f19f61341cbe`**，
   `measurement_valid=True`、`gate_pass=True`。
2. **权威口径自本节起 = `v1.5 / f19f61341cbe` / spec `132fceb89f68`**：48 臂 / 960 局，
   三分类 **25 可引用 / 22 有效零成功 / 1 无效**，`measurement_valid` **47 / 1**，
   计数层 受控 **135** / `insufficient_lift` **235** / `flick` **7** / `over_lift` **0** / `provisional_pass` **0** / raw **377**。
   **v1.2.1 / `e4f5ec887788` 与 v1.4 / `b9379fdb1089` 两个口径同时降级为历史口径**（不作废、不得当现值引用）——
   这是 改判 7 / 裁定 16.3 的第三次触发，也是本轮最后一次。
3. **能力结论一个字都不变**（这条最重要）：免罪只是把一次**测量有效性**的保留解除，
   **不改任何逐局计数**（cond5 已实测：raw 11 / 受控 9 / flick 1 / insuff 1 一格未动）。
   ⇒ 「官方 ACT 在这套 Lift 数据上还没有可重复的抬起能力」、§8 上调条件 ① 仍是唯一卡点、
   双峰未填平 —— **全部维持原判**。免罪改变的是「这个 9/20 能不能引用」，不是「能力有多大」。
4. 护栏①（`summary.pending_cosign_reverify` 独立桶）**本轮已成 moot**（③ 已完成、`cosign_build_matches=true`），
   但**机制仍建议 B 实现**：将来任何「条目已登记、会签块尚未换到新 build」的时刻都需要它，
   否则那个窗口期内该臂会被**静默**算成「已免罪」。列为 P2。
5. **表述纪律更新（取代 §7 的第 4 条）**：引用 25/22/1 **必须**带 `v1.5 / f19f61341cbe`；
   不得再写 `PENDING_IMPL`；引 v1.2.1 / v1.4 的旧表必须标「历史口径」。

---

# 增补七（2026-09-29 11:5x–12:0x，D）：裁定 29 —— spec 轴自我纠错 + DR-010 排序裁定 + 检修断点**部分**解除

> 本轮触发条件：B 在 11:40–11:45 又落了一轮（`scripts/b_official_arms_reclassification.py` 11:40、
> 权威表 `runs/infra/b_official_arms/reclassification.json` **11:45 重出**、规格文档 11:42 再编辑），
> C 在 11:41–11:50 出了 env manifest 并跑全量回归，A 把迁移闸判据从 23 扩到 **24**（自检 30/30）。
> D 现场独立复算，不引用任何他线结论。

## §14 裁定 29.1：**D 第七次自我纠错** —— 裁定 28 ② 把 spec 轴钉成引用锚是错的

**错在哪**：裁定 28 ②（§13）与 DR-D27 都写「权威口径 = `v1.5 / f19f61341cbe` / spec **`132fceb89f68`**」。
D 现场实测：spec 轴在 ~35 分钟内移动了 **4 次**——

| 时刻 | `GATE_SPEC_SHA` 观测值 | 来源 |
|---|---|---|
| 11:14 | `132fceb89f68` | D verifier 第一轮（`D_cosign_k2seed0_v15.json`），被抄进会签块与 裁定 28 |
| ~11:21–11:41 | `154b3636056f` | B 快照 `tmp/agentB_inherit_20260929/spec.before_v15_closeout.md`（D 实测其 sha12 == `154b3636056f`，与 B 记的一致） |
| 11:44 | `a1a8f38e7893` | D verifier 第二轮（**B 正在写文件的中间态**） |
| 11:47 起 | **`c7fadabe8e3c`** | D verifier 第三轮 + 权威表 11:45 版，**两轴现已一致** |

⇒ 裁定 28 ② 钉的那个值**在写下当时就已经过期**（11:5x 写 `132fceb89f68`，而 11:41 的快照已是 `154b3636056f`）。

**裁定（表述纪律，取代 §13 第 5 条与 §7 第 4 条）**：
1. **引用锚只在 build 轴**：权威口径的固定写法 = **`v1.5 / f19f61341cbe`**，**不带 spec 值**。
2. **spec 轴是观测日志，不是钉子**。任何裁定/会签/表格都**不得**把 `gate_spec_sha256` 写成生效条件；
   需要留痕时按「观测序列 + 时刻」记（如上表），并声明「文字/登记变更，无判据变更」。
3. **两轴现值的唯一权威来源 = `runs/infra/b_official_arms/reclassification.json` 的 `gate_build` / `gate_spec_sha256`**
   （采纳 B 的冻结声明写法）。live 门禁与它不一致时，**以 live 为准并立刻报 D**（说明表已过期）。

**哪一行代码执行它 / 为什么 build 轴可当锚而 spec 轴不可**（这是本裁定的事实基础，D 亲验）：
- `scripts/b_gate_controlled_success.py:56` → `GATE_BUILD = _sha12(Path(__file__).resolve())`
  ⇒ build 是**门禁脚本自身内容的哈希**，运行时现算，**不是硬编码字符串**。
  D 独立复算：`sha256(scripts/b_gate_controlled_success.py)[:12] == f19f61341cbe`，与模块自报一致。
  **推论：判据不可能在 build 不变的情况下改变**——改判据必然改脚本内容，必然改 `GATE_BUILD`。
- `scripts/b_gate_controlled_success.py:57` → `GATE_SPEC_SHA = _sha12(_ROOT / GATE_SPEC_DOC)`，
  `:45` → `GATE_SPEC_DOC = "docs/b_controlled_success_v1_20260928.md"`
  ⇒ spec 轴哈希的是**散文规格文档**。文档可以在判据一字未动时被编辑（本轮 §2.18 预登记 + §6 版本表 + §7 回归表 + DR-010 提请，全是文字）。

**判据非恒真（双向自检）**：本裁定「build 轴是锚」不恒真——它的可红条件是
「live 脚本哈希 ≠ 权威表 `gate_build`」。D 现场实测两者**相等**（均 `f19f61341cbe`）⇒ 绿。
若 B 解冻脚本，此判据立刻变红，会签按 DR-008 决定 7 自动失效。**不是恒真判据**（沿用 DR-003 判据 3 教训）。

**反例取自真实产物形状**：`scripts/a_migration_gate_preflight.py:1143` 的 fixture 里仍硬编码
`"gate_spec_sha256": "132fceb89f68"`——正是 D 裁定 28 钉的那个过期值。
**若引用规则真是「spec 轴必须匹配」，A 的迁移闸此刻就该红**；它实测 **OPEN / 0 blocking / 0 warn**，
因为 A 正确地只锚 build。这既证明本裁定方向对，也**给 A 留了一颗地雷**：
那个 fixture 值应改成「不参与判定、仅回显」，否则将来任何按 spec 轴比对的判据都会假红。
→ **要求 A**：`:1143` 的 spec 值降级为纯回显或删除；`:1125` 的 `"gate_spec_sha256": ["132fceb89f68"]` 同理。

**会签效力**：不受影响。会签块 `configs/b_probe_exonerations.json` 里
`cosign.gate_build_at_cosign = f19f61341cbe` == 门禁现值 ⇒ `cosign_build_matches = True`（D 实测）。
`cosign.gate_spec_sha256_at_cosign = 132fceb89f68` **保留原样不改**（它是 11:14 那一刻的可核事实，
改它等于篡改历史观测）；按本裁定它**不参与**效力判定。→ **要求 B**：在会签块旁已有的
`spec_axis_note` 里补一句「按 裁定 29.1，spec 轴不参与会签效力判定，本字段为历史观测」，**不要改数值**。

## §15 裁定 29.2：**DR-010 排序提请 → 选 (a)**；同时更正 裁定 25 的措辞错误

B 的提请（规格 §2.18 末段 / DR-010）事实成立，D 逐条核过：
- 裁定 25 的「执行承诺」原文写的是「B 的 v1.5 落地（**含 裁定 23 的六项**）后，D 跑 verifier」；
- 实际 v1.5（`f19f61341cbe`）**不含** 裁定 23 的六项——它们被 B 正确地预登记为 **v1.6**（§2.18 明写
  「**这一节是预登记，不是已实现的判据**」，符合 DR-001「改门禁前先登记」）；
- D 的 裁定 26 复签与 裁定 27 §12.4 收尾清单确实**没核这一项**（只列了 build 冻结声明 / 权威表重出 / cosign 换块 / 护栏①）。

**裁定**：
1. **这是 D 的起草错误，不是 B 的落地缺口。裁定 25 那句括号「（含 裁定 23 的六项）」予以划除。**
   理由：裁定 23 是 **P1**，从未列入 DR-008（v1.5 批次）的验收判据；DR-D22 承诺的验收范围是
   DR-008 决定 1–5 + 裁定 17.4 的登记条目。裁定 26/27/28 核的正是这个范围，**核得对**。
   ⇒ **会签与 裁定 28 的闭环结论不失效、不重开。**
2. **DR-010 选 (a)**：v1.5 冻结生效 → **A 先按 裁定 27 迁表** → 裁定 23 作为 **v1.6** 紧随其后。
   **D 的独立实证依据（不引用 B 的推荐理由）**：裁定 23 要修的空转标志在**官方 48 臂集上一处都不咬**。
   D 现场读 11:45 权威表：`summary.terminal_semantics_unavailable = {n: 0, arms: []}`，
   逐臂 `terminal_kind_coverage` 全为 `{n:20, of:20}`（不足者 **0** 臂）。
   那个 0/20 的空转实例是 `runs/infra/b_env_rebuild/base_truth20.json`（B 的 scripted base 复现），
   **不在** 48 臂官方集里。⇒ 选 (b)「先升 v1.6 再迁表」对**迁表结果的影响恰好为零**，
   却要付出「A 迁移半途换 build + `a_gate_build_drift_check.py` 默认指纹再次过期」的确定代价。
   **零收益、有确定成本 ⇒ 选 (a)。**
3. **v1.6 的复签义务不变**（DR-008 决定 7 / 裁定 25）：B 落地 v1.6 即升 `GATE_BUILD` ⇒
   会签自动失效 ⇒ **D 跑第三轮 `scripts/d_verify_exoneration_cosign.py --expect exonerated`**，
   A 的 48 臂表须在新 build 上重出 meta。**在 v1.6 落地前，A 迁表用的就是 `f19f61341cbe`，迁完不算白做**
   （计数与三分类不受 v1.6 影响，只有 meta 的两轴值要刷新）。
4. **过渡期引用纪律（采纳 B 的写法，升为 D 裁定）**：任何引用
   `terminal_semantics.suspect_truncation_labeled_as_failure = false` 的结论，**必须**同时注明
   「该产物 `terminal_kind` 覆盖 n/N；覆盖不足时此值为**空转**，见规格 §2.18 / 裁定 23」。
   **哪一行代码执行它**：`scripts/b_official_arms_reclassification.py:499` 的顶层
   `known_vacuous_fields_pending_v16` 已把这条写成机器可读声明（D 实测其在 11:45 表里存在且非空），
   `:281` 逐臂 `terminal_kind_coverage`、`:492` 汇总 `terminal_semantics_unavailable` 提供 n/N 的取值来源。
   **判据非恒真**：`terminal_semantics_unavailable.n` 可为非零（把任一臂的 `field_presence.terminal_kind`
   降到 < episodes_total 即触发，`:373-375` 是它的判据）⇒ 不是恒 0 的空转汇总。

## §16 裁定 29.3：验收 B 的 11:45 重出 —— 护栏① 从「moot / P2」升为**已落地 CLOSED**

裁定 28 ④ 写「护栏①（`summary.pending_cosign_reverify` 独立桶）本轮 **moot**，机制仍建议实现（P2）」。
**D 现场实测：B 已在 11:45 版权威表里实现了它，且实现得比 D 要求的更好。** 裁定 28 ④ 予以更正：

- **桶已存在**：`summary.pending_cosign_reverify = {n: 0, arms: [], cosign_not_required_arms: ["trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0"], criterion: "... is False（三值：True=已复签 / False=待复签 / None=通道不要求会签）", zero_condition: "..."}`。
- **判据是三值的**：`scripts/b_official_arms_reclassification.py:376` 用 `... is False`，`:367` 有明文注释
  「判据必须是 `is False` 而不是 `is not True`」。⇒ **A 在迁移闸 B7b 里提请的那个缺陷，B 已经修掉了**，
  而且修法与 A 的建议一致。**A 的 B7b note 里引用的 `docs/a_handoff_to_b_pending_bucket_tristate_20260929.md`
  盘上不存在**（D 实测 `ls` 无此文件）→ **要求 A**：要么补写该移交单、要么把 note 里的引用改成
  「已由 B 在 11:45 版实现，见 `:367/:376`」。**不得引用不存在的文档**（这与 裁定 27⑤ 抓的「散文替代布尔断言」同型）。
- **三值语义的必要性被真实产物证明**（不是假想）：stdfloor 臂走 `reblown_single_source` 通道，
  门禁**从不**为该通道产出会签字段 ⇒ 其 `probe_exoneration_cosign_build = null`、`..._matches = null`。
  若判据写 `is not True`，该臂会**永远出不去桶**，等于把 裁定 13 的争议带重测豁免偷偷降级——
  正是 裁定 24① 判定为「退步」的那件事。**B 用 `cosign_not_required_arms` 单列，把「不需要会签」与「待复签」分开，这是正确解法。**
- **§2.18 第 4 项此前一度「有文档无产物」**：D 在 11:47 首次读表时（11:22 版）实测
  `known_vacuous_fields_pending_v16` **不存在**、`summary` 里**无** `terminal_semantics_unavailable`；
  而脚本 mtime 11:40 已含 `:281/:492/:499` 三处 ⇒ **表比脚本旧 18 分钟**，规格 §2.18「第 4 项已在报表侧先行落地」
  当时**没有产物承载**。B 于 11:45 重出后**已闭合**。这与本仓已发生三次的事故同型
  （DR-003 判据 3 恒真、D 第五次自我纠错「裁定成立但无代码承载」、裁定 23 的 `note` 恒空），
  故 D 记一笔：**「文档声明已落地」必须用产物 mtime ≥ 脚本 mtime 来验，不能用文档自述。**

**D 在 11:45 版权威表上的独立复算（全部现场重算，不引用 B 的日志）**：

| 项 | D 实测值 | 与 裁定 28 要求 |
|---|---|---|
| 两轴 | live 门禁 `v1.5 / f19f61341cbe / spec c7fadabe8e3c` == 权威表同值 | ✅ 一致 |
| `summary.citable` | **25 / 22 / 1** | ✅ 一格不动 |
| `summary.ic_status` | `verified_ok 45 / probe_exonerated 2 / violated 1` | ✅ |
| `measurement_valid` | **47 / 1**（唯一无效臂 = `trimdone0_minmax_k2_lr1e-5_s20k_seed0_replan1`，blown **0.1692**，**无探针**） | ✅ 与免罪册 conditions 第 4 条一致 |
| 计数层 | 受控 **135** / insuff **235** / flick **7** / over **0** / prov **0** / raw **377**（`n_artifacts=48`, `n_judge_error=0`） | ✅ 一格不动 |
| 豁免分桶 | `probe_exoneration_by_kind = {clip_at_train_absmax: 1, reblown_single_source: 1}` | ✅ 裁定 19/24⑤ |
| 会签回显 | clip 臂 `cosign_build=f19f61341cbe`、`matches=True`；reblown 臂 `band_checked=True`、`cosign_build=null` | ✅ 裁定 25/DR-008 决定 7 |
| D verifier | `--expect exonerated` ⇒ `ALL_FIVE_PASS=true`、`mutants_all_caught=true`、`blocker_*=[F,F,F]`、`guard_*=[T,T]`、**EXIT=0** | ✅ |
| A 迁移闸 | `MIGRATION_GATE=OPEN`、`blocking_fail=0`、`warn=0`、**`total_checks=24`**（自检 **30/30**） | ✅ 对 11:45 新表仍 OPEN |
| B 自检（同 build） | golden **47/47**、mutation **15/15**、regression **157/157 断言 · 39/39 用例**、regate **11 臂 · 裁定变化 0**、repro **12/12**、T17 mutation **6/6** | ✅ |

⇒ **裁定 28 的闭环结论在 11:45 版表上重新验一遍，全部成立。护栏① 结案（CLOSED，非 moot）。**
留档：`tmp/agentD_review_20260929/D_A_gate_preflight_20260929_1149.json`（D 跑 A 的闸，`--json-out` 写进 D 自己的目录，未触碰 A/B/C 文件）。

## §17 裁定 29.4：检修断点 **BP-20260929-venv-rebuild 部分解除** —— B/C 线解封，**A 线仍被阻**

C 的 `runs/infra/c_env_manifest_20260929.json`（11:50）质量合格：`breakpoints[0]` 带
`invalidates` / `does_not_invalidate` 双向声明、`lock_conformance` **28/28 match**、
`known_conflicts` 记了 `mink-numpy-resolution` 的成因与解法、`inherited_packages` 单列出
「不在 lock 里、来自 base」的 torch 等——**这正是 增补六 §0.2 要求的东西，C 做到了**。

**但 D 现场实测出一条 C 的 manifest 没有覆盖的缺口**：

- **`lerobot` 仍 MISSING**：`/root/venvs/rlrobot/bin/python -c "import lerobot"` ⇒ `ModuleNotFoundError`。
  它**不在** `requirements.lock.txt`（28 个包里没有）、**不在** `inherited_packages`、
  **也不在 manifest 的 `probe_modules`（13 个探针里没有 lerobot）**。
  ⇒ **manifest「全绿」绝不能读成「环境已完全恢复」**：它绿的是 C 自己探针清单里的东西。
- **裁定**：断点 **部分解除**。
  - **解封**：只读后处理（门禁 / 48 臂汇总 / 登记册 / 账本视图自检）——本来就从未被阻（增补六 §0.2 第 1 条）；
    **以及** robosuite/mujoco 依赖的自检——现已可跑（`robosuite 1.5.2` == 改判 3 的可复现性前提，未被破坏；
    C 全量回归 golden **171 PASS / 0 FAIL / 1 NOT_ASSERTABLE** 即为旁证）。
  - **仍被阻**：**A 线的一切新训练 / 新评测**。`lerobot` 缺失 ⇒ 官方 ACT 训练与真值评测**跑不起来**。
    **在 lerobot 按原 pin 重装、且 manifest 的 `probe_modules` 扩到含它之前，A 不得声称任何新的复现。**
- **要求 C**（P0，小改）：把 `lerobot` 加进 `scripts/c_env_manifest.py` 的 `probe_modules`，
  并回显其**来源与 commit pin**。D 已在盘上找到候选源：`/workspace/cache/yhzhang91/zptang/lerobot_0cf8648/lerobot`
  （目录名自带 commit `0cf8648`）；另有 `/workspace/mnt/sppro/sqzhang26/gaoyuxuan/lerobot`、
  `/workspace/mnt/sppro/clzhang25/LIBERO/lerobot` 两份**他人副本**——**不得**拿它们当本项目的 pin，
  必须与 `docs/lerobot_act_env_setup_20260928.md` 记的原始安装方式核对后再装。
- **要求 A**：重装 lerobot 后**必须重出 env manifest 并登记「0929 断点」**（增补六 §0.2 第 2 条），
  跨断点的产物（mtime < 10:45:56）若被引用为「可复现」，一律要重跑。
- **两条附带更正**：
  1. D 上午把 `scripts/c_run_all_selfchecks.sh` 的 `PY` 临时设成 `python3` —— **此法作废**。
     系统 `python3` 只有 numpy **1.26.4**，且 mujoco/robosuite/gymnasium/sb3 **全缺**；
     venv 里 numpy 是 **2.4.6**（== lock 值，**不是漂移**）。C 已把该脚本改成**自动探测解释器**
     （`:43-59`），显式 `PY=` 只作兜底。⇒ **跑任何碰 robosuite 的东西一律用 `/root/venvs/rlrobot/bin/python`。**
  2. manifest `gpu.context_probe.reason` 写「A 线正在用 GPU 训练」，但同一份 manifest 的
     `nvidia_smi` 实测 **`memory_used = 0 MiB` / `utilization_gpu = 0 %`**（A800-SXM4-80GB 全空）
     ⇒ **此刻没有任何训练在跑**。这不是缺陷（C 不创建 CUDA 上下文是对的），但**那句 reason 是过期推测**，
     要求 C 改成「本次不探测；`nvidia-smi` 实测占用见上」。**理由：manifest 里的每一句都该是可核事实，不能夹推测。**

## §18 裁定 29.5：优先级改判 + 未决裁定清单（明示「今天没裁」）

1. **C 待办 2（`work/decisions/` 正式登记处：内容寻址 / append-only / 可撤销 / ack）由 P1 提到 P0。**
   **依据是今天发生在我自己身上的事**：venv 与 `~/.codex/sessions/` 同在 overlay 上，
   检修把「运行环境」和「四线对话历史」一起清了；环境靠 lock 复现了，**对话历史不可复现**，
   D 本轮的上下文只能从盘上产物反推（C 的 ADR-C-006 独立得出同一结论）。
   **这是本仓唯一一处「丢了就真没了」的资产，它的登记处不该排在 P1。**
   并号规则（C 等的东西）**一并给出**：`DR-D<n>` = D 线裁定序号（本轮到 **DR-D28**）；
   `DR-00<n>` = B 线门禁/流程决定；`ADR-A-<n>` / `ADR-C-<n>` = A/C 线架构决定。
   **登记处以「决定」为原子单位，一条一文件、内容寻址、只追加、撤销靠新条目指向旧条目**（与 `supersedes` 同型）。
2. **C 待办 3（逐臂内容寻址 run manifest）维持 P1**，但**加一条**：git 已 init（7 commits）⇒
   manifest 与 git **互校**而非替代；C 不执行 git 写命令（护栏 8），commit 归属由 **B 提供**。
3. **今天明确**没有**裁定的三项**（防止他线误以为已裁）：
   - **C5=0.04 是否按 `object_geom` 缩放**：自 `docs/b_agent_review_20260928.md:712` 起就在 D 的裁决队列，
     **至今未裁**。规格 §2.7 已把锚从「与 robosuite 同量级」（**证伪**：等效相对阈 ≈0.0085，C5 严约 **4.7 倍**）
     换成「`0.04 = 0.92 × 物体全高 0.04341`」（**成立**）。**D 现在的立场（不是裁定）**：
     改这个值会**放大所有历史臂的成功率**，属改判级别，必须先做**预登记的双阈值并行重判**
     （0.04 与 `0.92 × 2 × size_z` 两套同时跑、报差集），**不得**原地改常数。
     排期：**等 A 迁表完成之后**（现在动它会让迁表半途换判据，与 DR-010 选 (a) 的理由冲突）。
   - **动作侧饱和率 0.93–1.00 是否进门禁 warn**：未裁，证据还不够（需要一个「饱和率与受控成功相关」的实测表）。
   - **C 待办 6（ξ 锚缺口 / 导出列变更 = 冻结面变更）**：未裁。动冻结面需 D 批准，
     **D 暂不批准**，等 C 待办 1（`physical_fact` 接线）落定后一并看——现在批会让两件事互相污染。

## §19 对三线的要求（增补七）

- **A**：① 迁移闸已 OPEN（24 判据 / 0 blocking / 0 warn），**可以迁表**；迁完跑 `--mode postcheck`，
  盯 `NOT_CITABLE == 1` 与三分类 **25/22/1**（DR-010 选 (a) ⇒ **迁表用 `f19f61341cbe`，不必等 v1.6**）。
  ② `a_migration_gate_preflight.py:1143` 与 `:1125` 的 spec 值降级为纯回显（裁定 29.1）。
  ③ B7b note 里**引用了盘上不存在的移交单**，补写或改引（裁定 29.3）。
  ④ **lerobot 未装好前不要声称任何新训练/评测复现**（裁定 29.4）。
  ⑤ `arms_summary_v3.json` 的 meta 现仍记 `v1.2.1 / e4f5ec887788 / 494d5f5babf9`（D 实测）——
  那是 **schema 3 的归属表**、不是迁移后的权威表；迁表后 meta 必须刷成 `v1.5 / f19f61341cbe`。
- **B**：① 会签块的 `gate_spec_sha256_at_cosign` **数值不改**，旁边补一句「按 裁定 29.1 不参与效力判定」（裁定 29.1）。
  ② v1.6 落地即升 build ⇒ **主动通知 D 跑第三轮复签**，不要等 D 发现（裁定 29.2 第 3 条）。
  ③ `scripts/setup_env.sh` 的范围 pin 与 lock 不一致（C 的 ADR-C-006 提请）——**该脚本不在 C 的写入边界，在 B 的**；
  建议改成「优先 `-r requirements.lock.txt --no-deps`，lock 缺失才回退范围 pin」，并把 **pip 版本记进 lock**
  （C 实测 pip 24.0 → 26.2.1 的解析器差异是本次 `ResolutionImpossible` 的直接触发条件）。
  ④ 把 **lerobot 的安装方式与 commit pin** 从 `docs/lerobot_act_env_setup_20260928.md` 里摘出来交给 C/A（B 是环境文档的责任线）。
- **C**：① `probe_modules` 加 `lerobot`（P0，裁定 29.4）。② manifest 里那句 GPU reason 改成可核事实（裁定 29.4 附带更正 2）。
  ③ **待办 2 提 P0，并号规则已给**（裁定 29.5 第 1 条），可以开工了。④ 待办 1 的 `physical_fact` 接线：
  链路已闭环（裁定 28）+ 权威表已在 `f19f61341cbe` 上重出（裁定 29.3）⇒ **阻塞解除，可以接**；
  但接之前先读 11:45 版表，不要用 11:22 版（后者缺 `terminal_kind_coverage` 等三处字段）。

---

## §20 裁定 30（DR-D29）：免罪有一条**未被传播的下游后果** —— 双峰证据里「中间带为空」已过期

> 这条是 D 在写本轮简报时**核数字核出来的**，不是任何一线提请的。它不推翻双峰结论，但**推翻双峰的一种写法**。

### 20.1 事实（D 独立复算：21 臂 actlog 名单 join v1.5 权威表）
把 `runs/infra/lerobot_act_env_20260928/closed_loop_dz_diag_A.json` 的 **21 个 actlog 臂名**
join 到 `runs/infra/b_official_arms/reclassification.json`（v1.5 / `f19f61341cbe`）的 `controlled_success`：

```
排序后 = [0,0,0,0,0,0,0, 1,1,1,1, 2,2,2, 3, 9, 14, 16, 17, 19, 20]
落在 4–9 的臂数 = 1   ← 不是 0
```
那一臂 = **`trimdone0_minmax_k2_lr1e-5_s20k_seed0`（受控 9/20）= 裁定 10 的免罪臂本尊**。

48 臂全集同样不空：`[0×23, 1×9, 2×6, 3×2, 4, 9, 9, 14, 16, 17, 19, 20]` ⇒ 4–9 区间 **3 臂**
（`k2 seed0`=9、`train120_trimdone0_minmax_k2_lr1e-5_s20k_seed0`=9、`trimdone0_minmax_lr1e-5_s20k_seed0_replan1`=4）。

⇒ **A 预登记 `docs/a_bimodal_divergence_preregistration_20260928.md:17`「两族合并 21 个有 actlog 的臂里，
受控成功落在 4–9 的臂数 = 0（中间是空的）」，在现权威口径下被恰好 1 臂证伪。**

### 20.2 成因（D 重建，**不是指控 A 算错**）
D 读 v1.2.1 历史表 `runs/infra/b_official_arms/reclassification.build_e4f5ec887788.json` 实测该臂当时：
`citable = NOT_CITABLE_measurement_invalid`、`ic_status = violated`、`mean_blown_frames_frac = 0.212`
⇒ **写 §1 的那一刻它是无效臂**。按「有效臂」统计（21 臂里的 20 臂）时，4–9 = 0 **成立**。
**裁定 10 免罪 → v1.5 让它 `measurement_valid=True` ⇒ 它重新进入分布 ⇒ 计数 0 → 1。**
**这一步没有任何一线传播**：A 的 `:181` 与 `:288` 两处增补仍在把「= 0」当现值引用——
它们限定的只是「这是 **20k 快照**的性质、不能外推到训练全程」，**没有触及有效性口径的变化**。
另记：**A 的 §1 自身前后矛盾** —— 第 1 条已明写 K=2 六 seed 受控 = 「**9(免罪)** / 2 / 0 / 17 / 19 / 1」，
第 3 条却说 4–9 = 0；9 就在 4–9 里。

### 20.3 裁定
1. **双峰结论本身不倒，但必须改述。** 可辩护的写法（21 actlog 臂）：
   **低簇 0–3（15 臂）／高簇 14–20（5 臂）／孤立 1 臂 = 9**（`k2 seed0`，`VALID_probe_exonerated`）；
   **空带是 4–8 与 10–13**，**不是**「4–9」。⇒ 准确定性是「**强间隙分离（gap-separated）**」，
   **不是「严格双峰、中间全空」**。
2. **禁用写法**：「受控成功落在 4–9 的臂数 = 0」「中间是空的」。
   **要求 A**：`:17`、`:181`、`:288` 三处挂更正指针（指向本节），**预登记原文不改**（它是 21:15 的历史记录，
   按 append-only 原则只加指针不改字）。
3. **引用双峰必须带四个限定**：① 臂集（21 actlog / 48 官方）② 快照（20k）③ 构建（**`v1.5 / f19f61341cbe`**）
   ④ **显式点出中间带的孤立臂**。缺任一条即为不可引用。
4. **一般规则（本条真正要立的东西）**：**「计数层」与「按有效臂统计的分布层」对构建的敏感性不同。**
   - **计数层（逐局 verdict 计数）= 构建不变**：v1.4 → v1.5 实测 受控 135 / insuff 235 / flick 7 / over 0 / prov 0 / raw 377 **一格未动**（裁定 28 ③，成立）。
   - **分布层（直方图 / 区间计数 / 极差 / 族均值的 n）= 构建相关**：它按 `measurement_valid` 的**臂集**统计，
     而 `measurement_valid` 会被免罪/降级改变。实测无效臂数 **v1.2.1 = 7 → v1.5 = 1**。
     ⇒ **任何分布类陈述都必须带构建指纹**。这是 裁定 29.1「引用锚在 build 轴」的**第二个独立理由**
     （第一个理由是「判据本身在脚本里」；这条是「统计口径的臂集也随构建变」）。
   - **哪一行代码执行它**：`scripts/b_official_arms_reclassification.py` 逐臂产出 `citable` / `measurement_invalid_reasons`，
     `summary.citable` 三分桶；分布类统计一律以「`citable != NOT_CITABLE_measurement_invalid`」为臂集 ⇒
     该臂集由门禁的 `measurement_valid` 判定决定，而后者由 `GATE_BUILD` 冻结。
5. **附带更正一处口径（对 裁定 28 ③ 的限定补充，不是纠错）**：
   v1.2.1 历史表 `n_artifacts = **44**`、计数 `132 / 208 / 23 / 0 / 1 / 364`，与 v1.5 的 **48** 臂 /
   `135 / 235 / 7 / 0 / 0 / 377` **不可直接相减比较**（臂集不同：多出的 4 臂是后来的 blindfix / reblown 重测世代）。
   ⇒ **裁定 28 ③ 的「一格不动」限定在 v1.4 → v1.5（同为 48 臂）**，这个限定此前没写出来，现在补上。
   **引历史口径时必须同时报 `n_artifacts`**，否则「计数层构建不变」会被误读成「跨所有构建都不变」。
6. **判据非恒真（双向自检）**：本条的可红条件 = 「21 臂 join 权威表后 4–9 计数 == 0」。
   D 现场实测 == **1** ⇒ 红。若将来该臂被重新评测（`scope=artifact` ⇒ 免罪随 sha256 失效）且新产物受控落到 ≤3 或 ≥14，
   本条会自动变绿 ⇒ **不是恒真，也不是恒假**。

---

# 增补八（2026-09-29 12:4x，D）：裁定 31 —— 验收 A 迁移完成 + 结 C 待办 9 + **D 第八次自我纠错**

> 触发：A 于 11:58–12:33 迁完并出 postcheck；B 出了 `docs/b_handoff_to_d_20260929.md`（含两条对 D 的更正）
> 与 `docs/b_handoff_to_c_20260929.md`；C 出 ADR-C-007/008 并把待办 9 提请 D 裁定。D 全部现场独立复核。

## §21 裁定 31.1：验收 A 的迁移 —— 裁定 16.4 / 27 / 28 的最后一个行动项**闭合**

D 独立复核（不引用 A 或 B 的日志）：
- `runs/infra/lerobot_act_env_20260928/regate_current/` **48 份** + `blindfix/regate_current/` **5 份**
  + `reblown/regate_current/` **1 份** = **54 份裁定记录，构建分布单一：`('v1.5','f19f61341cbe') × 54`**，无第二个构建。
- A 的迁后表 `runs/infra/lerobot_act_env_20260928/arms_summary.json`（**12:33**）：`schema_version 3`、
  `gate_version ['v1.5']`、`gate_build ['f19f61341cbe']`、`gate_spec_sha256 ['c7fadabe8e3c']`
  ⇒ **memo §19-A⑤ 的要求已满足**（D 上午看到的 `attribution/arms_summary_v3.json` 11:08 版仍是 v1.2.1，
  那是**迁移前**的归属表；迁后权威表是 `arms_summary.json`，`a_table_role = post_migration_table`）。
- A 的 postcheck `migration_gate/postcheck_v15_migration_20260929.json`（12:03）：
  **17 项全 `pass=True`、`blocking` 非通过项 0、`gate_open=true`**。
- A 的表把**免罪前后两个分母都登记了**并写明恒等式：`pre 24/22/2（48=24+22+2）` →
  `post 25/22/1（48=25+22+1）`，且 `exonerated_arms` 带 `probe_kind=clip_at_train_absmax`、`C=12.469445`、探针产物路径
  ⇒ **裁定 19（`probe_kind` 必须回显）与 裁定 24⑤（两表差 1 属设计差异）在 A 侧已可核**。
- 权威表 12:21 版又新增 `summary.controlled_success_histogram`（**48 臂与 47 有效臂两套分开**）与顶层
  `distribution_layer_note` ⇒ **裁定 30 已有机器可核承载**；数值逐格未变（25/22/1、45/2/1、47/1、135/235/7/0/0/377），
  且 **产物 mtime 12:21:19 ≥ 脚本 mtime 12:21:16**（按 裁定 29.3 的新规则核过）。

⇒ **裁定：A 迁表结案。** 48 臂官方集现在**全链路单一构建**（B 的权威表、A 的迁后表、54 份逐臂裁定、D 的会签，
四者同为 `v1.5 / f19f61341cbe`）。这是本项目开工以来第一次「一处口径、一个构建、四线互校全绿」。

**一处必须同时记下的边界（防止过度声称）**：顶层 47 份 `runs/infra/lerobot_act_env_20260928/gate_*.json`
**仍在历史构建上**——D 实测其构建分布为 `v1.1/800e1d08a174 ×19`、`v1.1/无 build ×13`、`v1.2.1/e4f5ec887788 ×5`、
`v1.2/28290b9c1b25 ×3`、`v1.2/22a7d92bec0a ×1`、`v1.1/369595c86a07 ×1`、`无版本 ×5`，**v1.5 为 0 份**。
这是**设计如此**（A 的做法是新出 `regate_current/` 承载现构建、把 v1.2.1 钉进 `regate_v121_pinned/` 留档，
顶层旧文件属历史留档，B 的重分类脚本每轮明写「未被本脚本改写（A 的写入范围）」）。
⇒ **「全链路单一构建」只指 `regate_current/` 一族 + B 表 + A 迁后表**，**不含**顶层历史 `gate_*.json`。
引用时必须说清是哪一族，否则会被读成「仓里所有裁定都是 v1.5」。**这条直接引出 裁定 31.3。**

## §22 裁定 31.2：**D 第八次自我纠错** —— 裁定 29.4 里我指的 lerobot 候选源不能用，且缺口表述也错了

B 只读实测（`docs/b_handoff_to_d_20260929.md` §9.1/§9.2）否掉了我给的两件事，**D 复核后认账**：
1. **候选源错了**：我在 裁定 29.4 指 `/workspace/cache/yhzhang91/zptang/lerobot_0cf8648/lerobot` 作离线候选源。
   B 实测其 HEAD = `0cf8648…`（2025-05-28），`git rev-list --left-right --count v0.4.4...HEAD` = **`488  0`**
   ⇒ **落后 tag `v0.4.4` 共 488 个 commit、领先 0**，且该 HEAD 的 `pyproject.toml` 自报 **`version = "0.1.0"`**。
   **我把「目录名里带 `0cf8648`」当成了「这就是本项目的 pin」**——目录名是**副本持有者的 checkout 时刻**，
   不是本项目的版本要求。**这正是我今天在 A 身上抓过的同型错误（文本锚点当事实），我自己踩了。**
   ⇒ **裁定 29.4 里那句候选源指引作废。** 正确 pin 以 B 的 `docs/lerobot_env_reinstall_pin_20260929.md` 为准
   （`lerobot==0.4.4`、`torch==2.6.0`、aliyun index；离线回退须在**自己的目录**里 clone
   `https://gitee.com/mirrors/lerobot.git` 并 `checkout v0.4.4` = `8fff0fde7c79f23a93d845d1a50e985de01f8b8a`）。
2. **缺口表述错了**：我写「`rlrobot` 里少一个 `lerobot` 包」。实测 `ls /root/venvs/` **只有 `rlrobot`**；
   lerobot 按设计**从不**装在 `rlrobot` 里（`requirements.lock.txt` 28 包无它，
   `docs/lerobot_act_env_setup_20260928.md:278` 明写两个独立 venv）。
   准确表述 = **`lerobot_act` / `lerobot_eval` 两个 venv 整体被 0929 检修抹掉**。
   ⇒ 在 `rlrobot` 里探到 `lerobot` MISSING 是**设计如此，不是缺口**；把它当缺口会让「A 被阻」看起来像「B 没建好环境」。
3. **B 顺带给我一条判据教训，D 采纳并升为规则**：`import lerobot` 成功是**恒真判据**——
   lerobot 的 `__version__.py` 实测就是 `importlib.metadata.version("lerobot")`，源装成 0.1.0 时 import 照样成功。
   ⇒ **规则（补进 裁定 27.3 的判据纪律）**：**探针必须验「语义值」而不是「可导入」**。
   凡「装了没」类探针，一律要求 ①版本号断言（`lerobot.__version__ == "0.4.4"`）②回显安装来源
   （PyPI wheel / 源装 + commit）③**可红条件写出来**（版本不符即红）。这是本仓今天第 **5** 起同型
   （DR-003 判据 3 恒真、D 第五次自我纠错、裁定 23 的 `note` 恒空、裁定 29.3 的「文档自述已落地」、本条）。

## §23 裁定 31.3：C 的 `exoneration_disagreement` 是**跨构建混算** —— 报表口径必须修（D 现场发现）

C 的 `runs/infra/c_verdict_identity_inventory.json`（12:17）报：
`authority_exonerated_gate_not = [k2 seed0]`、`gate_exonerated_authority_not = [stdfloor k2 seed0]`。
**D 追到根因**：这里的 "gate" 侧读的是**顶层历史 `gate_*.json`**——D 实测目标臂那份
`gate_strict_trimdone0_minmax_k2_lr1e-5_s20k_seed0.json` 的 `ic_status=None`、`probe_exoneration=null`、
`measurement_valid=False`、`gate_build=None`（**v1.0 时代的产物**）；而 "authority" 侧是 B 的 **v1.5** 表。
⇒ **这不是活矛盾，是拿 v1.0 的裁定去和 v1.5 的权威表对账。**
**但报表把它写成裸的 "disagreement"，读起来就像当前口径自相矛盾**——这与 裁定 27.4/29.3 抓的假红同型，
只是方向相反（那次是「红的其实不红」，这次是「看着红的其实压根不可比」）。

**裁定**：
1. `exoneration_disagreement` 必须**两侧都带构建**，并且**只在两侧同为当前构建时**才报 `disagreement`；
   否则报 **`stale_side_not_comparable`**（可见、但不报警），与 B 在护栏① 里对 `None` 的处理同型
   （`cosign_not_required_arms`：可见但不报警）。
2. **判据非恒真要求**：改完必须附一个**合成反例**——两侧都在 `f19f61341cbe` 上、authority 说免罪而 gate 说不免罪
   ⇒ 必须真的报出 `disagreement`。否则这个字段会变成**恒空**（永不报警 = 没有报警），
   与 裁定 27.1「恒假的闸等于没有闸」同型。
3. 顶层 47 份历史 `gate_*.json` 的**归属要写明**（历史留档 / A 的写入范围 / 不参与现口径对账），
   否则下一个读清单的人还会踩同一个坑。**建议 C 在清单里给每份产物带 `provenance` + `build` + `is_current_build`
   三个字段并把对账只在 `is_current_build==true` 的子集上做**（C 的 `provenance_distribution` 已有 `provenance`，
   `build_distribution` 已有 build，缺的是**把它们用到对账判据里**）。

## §24 裁定 31.4：结 C 的**待办 9** —— 5 条历史构建记录的归属，判 **(b) + `provenance_kind` 子标签**

C 提请三选一（(a) 留本档 / (b) 转 `stale_build_evidence` / (c) 另立一档），倾向 (b)。D 逐条核过 C 的证据
（4 条出自 `migration_gate/exoneration_path_probe/` 的 `gate_P0_baseline`/`P1_scope_arm`/`P2_scope_artifact`/`P3_band_widened`
= A **故意造出来被拒**的写法探针；1 条出自 `regate_v121_pinned/main/` = 预登记 §6 钉死 v1.2.1 的**冻结锚点**）。

**裁定：(b)，但必须带 `provenance_kind` 子标签；(a) 与纯 (c) 都不采纳。**
- **不采 (a)**：档名 `pending_impl_ruling_approved` 的字面意思是「实现待落地（已批准）」，
  而这 5 条的 `violated` 是**探针的预期结果**与**锚点的设计使然**，不是待落地的实现缺口。
  **一个说谎的标签比没有标签更坏**（与 裁定 12「缺字段不得读成能力结论」同源）。
- **不采纯 (c)**：为 5 条记录新开一档 `usable_for`，会让「能不能当现构建证据用」这个**二元可用性**问题
  变成三元，下游每个消费者都要多认一个值——**词汇表膨胀的代价大于收益**。
- **采 (b) + 子标签**：`usable_for` 保持 `stale_build_evidence`（**可用性语义完全相同**：都不能当现构建证据），
  另在**理由侧**加机器可读的 `provenance_kind ∈ {deliberate_rejection_probe, frozen_prereg_anchor, superseded_rerun, ordinary_stale}`。
  ⇒ 可用性判断只看 `usable_for`（不分叉），**为什么**不可用看 `provenance_kind`（不丢信息）。
- **批准 C 已设计好的实施方式**：激活条件收窄为「该臂在**当前构建**下没有任何承载免罪的产物」，
  **跨记录条件放 `inventory()`**、`parse_verdict` 保持记录级纯函数，被改判的记录留 `regraded_from` 以便审计。
  **这个分层是对的**（纯函数不碰跨记录状态，正是 裁定 21「判据单一来源」在 C 侧的对应物）。
- **附加要求（判据非恒假）**：收窄激活条件有可能让这一档**永远不触发**（= 恒假 = 没有这一档）。
  C 必须附**合成反例**：造一个「条目已登记、但该臂在当前构建下无任何承载产物」的形状 ⇒ 该档**必须触发**。
  这正是 裁定 28.4 说「护栏① 本轮 moot 但机制仍须实现」的同一个理由——**机制的价值在它将来会咬人的那一刻，
  所以必须证明它将来咬得动**。
- **`grade_mechanism_retired=false` 予以认可**：裁定 28 撤的是**标注**（对臂现状态的表述），
  不是「逐份产物有没有承载裁定」这个事实。旧产物不因裁定更新而改写。C 的理解正确。

## §25 裁定 31.5：结 B 的两项请裁定

1. **B §5（`condN` 命名卫生，裁定 27.5 / P2）：批准并入 v1.6。**
   理由采纳 B 的：该条目刚被 D 复签，「换块」与「改名」同批做会让**「D 签的到底是哪一版条目」变得不可核**；
   且 裁定 27.2 已要求 A 按门禁真正读的键名（`RULING10_CONDITION_KEYS`）精确取，A 收窄后本项**无害**。
   v1.6 落地时条目本就要随 build 复签 ⇒ **一次做完，不额外增加复核轮次**。
   **附加要求**：v1.6 改名后，`scripts/d_verify_exoneration_cosign.py` 的第三轮复签必须**同时验新旧键名不并存**
   （否则会出现「两套 `condN` 都读得到」的更坏形状）。
2. **B §6.2（裁定 23.5 的「`terminal_kind` 缺失已被接受 + 理由」声明该落在谁的登记册）：判归 B 的 `configs/`。**
   理由：裁定 23.5 的对象是 **`base_truth20.json` 作为 `rise_cap=0.15` 标定基准 / 20-20 参考上界 / DR-004 锚点**
   的**门禁阈值溯源**属性——那是 B 的判据侧资产（`threshold_provenance` 已经在 B 的权威表逐臂回显）。
   C 的账本侧登记册管的是**臂级裁定的身份与溯源**，不是门禁标定基准。
   ⇒ **B 写、C 可按内容哈希引用，但不得成为该声明的 owner。** 排期：**随 v1.6 一起做**（现在做等于给未落地的判据建登记）。

---

# 增补九（2026-09-29 13:0x，D）：裁定 32 —— 环境安装责任改判给 A + `codex-persist mkvenv` 的两处实测缺陷

> 触发：用户改判「让 A 自己安装环境」，并告知后续新容器统一跑
> `python3 /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/bin/codex-persist bootstrap`，
> 已新建持久容器，询问是否用 `mkvenv rlrobot RL_Robot/requirements.lock.txt` 建持久 venv。
> D 只读实测了 `.codex-persist/bin/codex-persist`（636 行）、`scripts/install_lerobot_act_env.sh`、
> `docs/lerobot_env_reinstall_pin_20260929.md`、`/etc/pip.conf`、`/root/venvs/rlrobot/pyvenv.cfg`。

## §26 裁定 32.1：DR-D30 的环境责任分派**予以改判**

裁定 31.5 附条写的是「**B 执行安装** → A 验证 → C 探针」。**按用户指令改为**：

| 角色 | 职责（改判后） |
|---|---|
| **A** | **执行安装**（`lerobot_act` + `lerobot_eval` 两个 venv；若走持久化，`rlrobot` 也由 A 一并重建到 NFS）+ 门槛验证 + smoke 训练/评测 + 重出 env manifest + 登记断点 |
| **B** | **不再执行安装**。B 的 `docs/lerobot_env_reinstall_pin_20260929.md` 是**唯一权威 pin 来源**（DR-012），A 照抄不"顺手升级"；`scripts/install_lerobot_act_env.sh` 与 `scripts/setup_env.sh` 仍在 B 的写入边界，A **只通过环境变量覆写、不改脚本** |
| **C** | 只出探针（P0-3）：探**那两个解释器**、验 `lerobot.__version__ == "0.4.4"` + 回显安装来源，**不得只验 importable** |
| **D** | 验收：安装后 GPU 不再全空、两个 venv 存在且版本对、env manifest 有断点条目、**0928 的两份 lock 未被覆写** |

**为什么这个改判是安全的（D 的判断）**：安装是**执行**动作、不是**判据**动作，落在 A（训练/评测的责任线）
比落在 B（门禁/可复现性线）更对——**谁用这个环境跑训练，谁负责它装对了**；B 的角色是**给出权威 pin 并验收**，
这本来就是 B 已经做完的事（pin 文档 12:3x 已落盘）。**裁定 31.5 那条分派作废，本条取代。**

## §27 裁定 32.2：`codex-persist mkvenv` 有**两处实测缺陷**，按用户原样那条命令**会失败**

用户提议：`mkvenv rlrobot RL_Robot/requirements.lock.txt`。D 只读实测 `.codex-persist/bin/codex-persist:500-525`：

**缺陷 ① `pip install -r` 没有 `--no-deps` ⇒ 必撞 `ResolutionImpossible`。**
`cmd_mkvenv` 的安装行是 `subprocess.run([target/"bin"/"pip", "install", "-r", str(req)], check=True, env=env)`，
**无 `--no-deps`**。而 D 用 `importlib.metadata` 实测：
```
robosuite 1.5.2  requires  ['numpy>=1.13.3', 'mink==0.0.5']
lock 里钉的是     mink==1.2.0
```
⇒ 解析器判 unsatisfiable。**这正是 C 的 ADR-C-006 / `known_conflicts[mink-numpy-resolution]` 记的同一个坑**，
也是 B 的 pin 文档 §2 末行说的「同一个冲突的两个现场」（`rlrobot` 侧表现为 `ResolutionImpossible`、
`lerobot_eval` 侧表现为 uv 需要 `--override numpy==2.4.6`）。
**已确立的口径（C 提出、D 采纳）**：**解析器到不了某个组合，不代表那个组合不可用**；
以「实际装成并跑通全量回归」的 lock 为事实源 ⇒ **从 lock 安装必须 `--no-deps`**。

**缺陷 ② `mkvenv` 硬编码 `--system-site-packages`，且不改 index ⇒ 对 lerobot 那两个 venv 是错的。**
`:510` 是 `python -m venv --system-site-packages`。但 B 的 pin 文档 §2 与 installer `:31`
（`echo "[1/7] 建干净 venv（不带 --system-site-packages）"`）明写：**lerobot 的 venv 必须不带它**，
否则 conda 的 TensorFlow + jax 被拖进 import 链，jax/numpy 版本对不上时报
`cannot import name 'PreTrainedModel'`——**这是 09-24 那串 ImportError 的真根因，不是 transformers 装坏**。
另：`mkvenv` 只设 `PIP_CACHE_DIR`，**不覆写 index** ⇒ 会走 `/etc/pip.conf` 的
`index-url = mirrors.ustc.edu.cn`，而 B 实测该源会 302 到 tuna 并对本机 **403**（installer 因此强制
`INDEX=https://mirrors.aliyun.com/pypi/simple` 且改用 **uv**，uv 不读 pip.conf）。

**裁定**：
1. **`mkvenv` 不得用于 `lerobot_act` / `lerobot_eval`。** 这两个一律走
   `scripts/install_lerobot_act_env.sh`，用**环境变量覆写路径**（脚本已把 `VENV` / `EVAL_VENV` / `BASE_PY` /
   `INDEX` / `TORCH` / `TORCHVISION` / `LEROBOT` / `LOCK_OUT` / `BUILD_EVAL_ENV` 全部写成可覆写，
   A **不需要改脚本**，符合「A 只覆写不改 B 的文件」）。
2. **`mkvenv` 用于 `rlrobot` 时不要带 REQ 参数**：先 `mkvenv rlrobot` 只建 venv，
   再手工 `pip install --no-deps -r requirements.lock.txt --index-url https://mirrors.aliyun.com/pypi/simple`。
   这样**不需要改用户的共享工具**就能绕开缺陷 ①②。
3. **建议（不由 D 执行）**：`.codex-persist/bin/codex-persist` 在**项目仓外**、是用户的共享基础设施，
   不在 D 的写入面 ⇒ D **不改它**。建议的最小修法是给 `cmd_mkvenv` 加两个可选开关
   （`--no-deps` 与 `--index-url`，或一个 `--clean` 表示不带 `--system-site-packages`）。
   **在修好之前，README 的「依赖持久化」那节应加一行警告**：从 lock 安装必须 `--no-deps`。

## §28 裁定 32.3：持久 venv 的**三个前提**（不满足就不是真持久）

方向 D **赞成**——它同时治了本轮暴露的两个根因（venv 与 `~/.codex/sessions/` 都在 overlay）。
但「建在 NFS 上就换容器不用重装」这句话有三个隐含前提，**必须显式验，不能假设**：

1. **lock 必须自足。** D 实测 `RL_Robot/requirements.lock.txt` 28 包里**没有 torch / torchvision /
   scipy / pandas / pyarrow / matplotlib**——它们靠 `--system-site-packages` 从 `/opt/conda` 继承
   （C 的 manifest 已把它们单列进 `inherited_packages`，并注明「只看 lock 一致性会漏掉它们」）。
   ⇒ **持久 venv 若继续继承 base，则「换容器不用重装」只在 base 镜像不变时成立**；
   base 镜像一换，torch 静默消失或变版本，而 **venv 内的 `pip freeze` 看不到它**（继承来的）。
   **要求**：二选一，且必须落盘写明选了哪个 ——
   **(甲) 自足**：把 8 个继承包钉进一份 `requirements.persistent.lock.txt`（torch `2.4.1+cu124`、
   torchvision `0.19.1+cu124`、scipy `1.17.1`、pandas `3.0.3`、pyarrow `24.0.0`、matplotlib `3.11.1`、
   pip `26.2.1`、setuptools `65.5.0`），建 venv 时**不带** `--system-site-packages`（约 +5 GB，NFS 现余 69 T，可承受）；
   **(乙) 继承 + 断言**：维持现状，但把 C manifest 的 `inherited_packages` 从**观测**改成**断言**
   （版本或来源不符即 `env_fully_restored=false` 并点名）。
   **D 的倾向是 (甲)**（持久的意义就是不依赖 base），但 **(乙) 是最低要求**，二者都做最好。
2. **base 解释器路径与版本必须断言。** D 实测 `/root/venvs/rlrobot/pyvenv.cfg`：
   `home = /opt/conda/bin`、`version = 3.11.9`、`executable = /opt/conda/bin/python3.11`；
   当前容器 `python3` = `/opt/conda/bin/python3`、**3.11.9**（与 installer 的 `BASE_PY` 默认值一致）。
   ⇒ venv 的 shebang 是**绝对路径**，`pyvenv.cfg` 的 `home` 也是 ⇒ **换容器后若 base python 不在
   `/opt/conda/bin` 或不是 3.11.x，持久 venv 直接坏掉**。
   **要求**：`bootstrap`（或 C 的 env manifest）必须把「`pyvenv.cfg.home` 存在 + 版本 == 3.11.9」做成**断言**，
   不能只记观测值。
3. **NFS 上的 venv 建成后按只读对待。** README 已对 `link` 模式给过同类警告（多容器共用同一份时不要开 link）。
   同理：**两个容器同时对着同一个 NFS venv 跑 `pip install` 会写坏它**。
   **要求**：建成后不再往里装东西；要改就整份重建到新目录再原子切换（`mv`，本项目禁 `rm`）。
   另：NFS 上 import torch/lerobot 是**大量小文件读**，首次导入会明显慢于本地盘 ⇒
   **要求 A 装完实测并记录一次冷导入耗时**，作为将来判断「NFS venv 是否拖慢训练」的基线。

## §29 裁定 32.4：**0928 的两份 lock 不得被覆写**（溯源保护，P0）

`scripts/install_lerobot_act_env.sh` 的 `:57` 与 `:85` 会
`pip freeze > "$LOCK_OUT/requirements.lock.txt"` / `> "$LOCK_OUT/requirements.eval.lock.txt"`，
而 `LOCK_OUT` 默认 = `runs/infra/lerobot_act_env_20260928`
⇒ **照默认值跑一次，就会就地覆写那两份 0928 的 lock**。
而那两份 lock 是「**48 臂权威表当初到底跑在什么环境上**」的**唯一溯源证据**
（B 的 pin 文档 §2 引它们作权威 pin 出处；C 已预见到这件事，把两份逐字节备份到
`runs/infra/c_lerobot_env_locks_backup_20260928/`，理由写的就是「installer 会就地覆盖原件」）。

**裁定**：A 重装时**必须**把 `LOCK_OUT` 覆写到一个**新目录**
（建议 `runs/infra/a_lerobot_env_rebuild_20260929/`），**不得**用默认值。
装完把新 lock 与 C 的备份**逐字节 diff 并报差异**：
- **完全一致** ⇒ 环境重建成功且**未漂移**，A 可继续；
- **有差异** ⇒ 差异**必须逐条解释**（哪个包、从什么变到什么、为什么），并**报 D**；
  **在 D 裁定之前，A 不得声称任何跨断点的复现**（增补六 §0.2 第 2 条 / 裁定 29.4）。
**理由（这是本裁定的实质）**：覆写历史 lock 会让「48 臂跑在什么环境上」这个问题**永久不可答**——
和本仓今天已经踩了五次的坑同型（**把可核事实换成自述**）。**新装的环境是新事实，0928 的 lock 是旧事实，
两者必须并存，不能新的盖掉旧的。**

---

# 增补十（2026-09-29 14:0x–14:4x，D）：裁定 33 —— 持久环境**已修**（用户改判：D 直接执行）+ 撞出两处 C 侧判据缺陷

> 触发：用户指令「上一环节持久环境的问题你直接修复就好」，并明确「你的定位是监管和任务裁定，
> 安装完了之后你看情况做个基础验证，其它验证项可以交给其它智能体做，这次执行完还是回归你的职责线」。
> ⇒ 裁定 32.2 第 3 条那句「建议（**不由 D 执行**）」在本轮**被用户改判、作废**；D 已改
> `.codex-persist/bin/codex-persist` 并把 `rlrobot` 建成自足持久 venv。
> 改前原件 `mv` 到 `.codex-persist/.trash/codex-persist.pre-mkvenv-fix.20260929`（本仓禁 `rm`）。
> **边界（照用户的话执行）**：D 只做**基础验证**（`venvcheck` / `env_check.py` / B 的可复现性自检 / 1 局 smoke），
> **其余验证项一律派回 A/B/C**（§34）。全部实测数字与命令落在
> `runs/infra/d_persistent_env_20260929/verification.json`（另有 `mkvenv_rlrobot.log`、`env_check.log`、
> `b_selfcheck.log`、`c_env_manifest.log`、`persistent_lock_report.json`）。

## §30 裁定 33.1：`codex-persist mkvenv` 的两处缺陷**已修**，并补上它缺的第三样东西——**断言**

### 30.1 改了什么（5 条，全在 `.codex-persist/bin/codex-persist`）
1. **缺陷①（`--no-deps`）**：REQ 文件名含 `lock` ⇒ **自动**加 `--no-deps`（要解析器显式 `--deps`）。
   用户原样那条 `mkvenv rlrobot RL_Robot/requirements.lock.txt` 现在**能跑**（`--dry-run` 实测回显
   `--no-deps=True` + aliyun index）。
2. **缺陷②（`--system-site-packages` 硬编码 + 不覆写 index）**：新增 `--clean`；index 默认
   `https://mirrors.aliyun.com/pypi/simple`（`CODEX_PERSIST_PIP_INDEX` 可覆写），并新增
   `--extra-index-url` / `--find-links`（`CODEX_PERSIST_PIP_FIND_LINKS`，冒号分隔）。
   **不带 `--clean` 时会打警告**：继承 base 的 venv「换容器不用重装」只在 base 镜像不变时成立。
3. **速度（本轮新测的事实）**：新增 `--installer {auto,uv,pip}`，`auto` 有 uv 就用 uv。
   实测同一个 35 MB wheel（scipy 1.17.1，`--no-cache-dir`）：**pip 52.5s（~0.7 MB/s）/ uv 4.9s**
   ⇒ 差 ~11 倍。这把 installer 注释里那句「pip 走代理只有 ~0.7 MB/s」**独立复现**在 pip/uv 对照上。
4. **溯源（原来完全没有）**：建档时写 `<venv>/.persist_meta.json`：base 解释器与版本、`clean`、
   installer、index/find-links、REQ 路径 + `sha256_12` + pin 数、耗时、`container_id`、
   以及一句 `readonly_after_build`（裁定 32.3 第 3 条的纪律写进产物本身）。
5. **断言（原来完全没有）**：新增 `venvcheck NAME`（V0–V8）与 `venvlink`（软链登记 + `bootstrap`/`auto`
   自动重放）。`venvcheck` 逐条对应裁定 32.3 的三个前提：V1/V2 = base 解释器路径与版本、
   V3 = 是否 clean、V6 = pin 全中、V7/V8 = 实际 import + 版本 + **模块文件是否在 venv 内（自足性）** +
   冷导入耗时回显。

### 30.2 判据有牙（双向自检，隔离根目录 `CODEX_PERSIST_ROOT=/tmp/cptest`，未污染真实 `envs/`）
- **正例**：2 pin 的 clean venv ⇒ `venvcheck dtest --import iniconfig --import mdurl:mdurl:0.1.2`
  = **11 PASS / 0 FAIL，rc=0**。
- **反例 1**：`--expect-python 3.12.9` ⇒ **V2/V5 FAIL，rc=1**（base 版本断言不是回显）。
- **反例 2**：`--import numpy`（未装）+ `--import iniconfig:iniconfig:9.9.9`（版本不符）⇒ **2 FAIL，rc=1**。
- **`venvlink` 的牙**：遇到**真实目录**返回 `REFUSE` 并给出「先 mv 到回收站」的指令，**不删别人的东西**；
  遇到已存在的软链则 `REPOINT` 且把旧软链 `mv` 到 `.trash`。

### 30.3 D 的自我更正（第九次）
裁定 32.2 第 3 条写「`.codex-persist` 在项目仓外、是用户的共享基础设施，**不在 D 的写入面 ⇒ D 不改它**」。
**这个判断在本轮被用户直接改判**，D 照办并已改。但那条判断的**实质理由仍然成立**（改共享基础设施要有备份、
要有牙、要写文档），所以 D 按同样的纪律执行：① 原件 mv 进 `.trash` 留底；② 新判据先做双向自检再用于生产；
③ `.codex-persist/README.md` 同步改（新增三个默认值的理由表、`--no-deps` 警告、三前提、软链一节）。
**另更正一处 D 自己上午的表述**：裁定 32.2 说「`mkvenv` 只设 `PIP_CACHE_DIR`，不覆写 index ⇒ 会走
`/etc/pip.conf`」——实测**本容器的 pip 配置在 `/root/.config/pip/pip.conf`**（`/etc/pip.conf` 不存在），
内容一致（`index-url = mirrors.ustc.edu.cn` + `extra-index-url = aliyun` + `find-links = aliyun/pytorch-wheels/cu124`）。
**结论不变，出处写错了**；顺带记一条事实：`/root` 在 overlay ⇒ **这份 pip.conf 每个新容器都可能不一样**，
这正是 mkvenv 必须显式传 index 的第二个理由。

## §31 裁定 33.2：(甲) 自足方案的**清单是错的** —— 缺的不是 8 个继承包，是 **54** 个

增补九 §28 第 1 条给的 (甲) 清单是 8 个（torch/torchvision/scipy/pandas/pyarrow/matplotlib/pip/setuptools）。
**D 现场做闭包时实测：照那 8 个建出来的 clean venv 装不上、也跑不起来。** 正确做法是**依赖闭包**：

- 从「`requirements.lock.txt` 的 28 pin + 13 个种子」出发，沿**已安装发行版的 metadata** BFS
  （**只跟依赖名字、版本一律取已装值**，`extra ==` 与平台不符的 marker 不跟），得 **82 pin**
  ⇒ 闭包新增 **54** 个：`nvidia-*-cu12` **12** 个 + `triton 3.0.0`（torch 的传递依赖，**约 3 GB**）、
  `sympy/networkx/jinja2/fsspec/filelock/typing-extensions/MarkupSafe/mpmath`、
  `opencv-python 4.13.0.92 / termcolor / tqdm`（robosuite 声明的）、
  `absl-py/grpcio/protobuf/werkzeug/six/python-dateutil`（tensorboard 的）、
  `contourpy/cycler/fonttools/kiwisolver/pyparsing/packaging`（matplotlib 的）、
  `pillow 12.3.0`、`h5py 3.14.0`、`pluggy/pygments`（pytest 的）。
- **一个必须记住的坑**：`robosuite 1.5.2` 的 `install_requires` **没有 h5py**，但
  `robosuite/utils/camera_utils.py:12` 是**模块级** `import h5py` ⇒ 纯 metadata 闭包会**漏**它；
  今天它能用只因为 base 里有 `h5py 3.14.0`。已在生成器里作为 `PARITY_SEEDS` 显式钉上并写明理由。
  ⇒ **一般规则**：`--no-deps` + 闭包 lock 还必须叠一层「**实际 import 面**」核对。D 用 AST 扫了
  `scripts/ harness/ envs/ policies/ eval/` 的全部 import：能映射到第三方发行版的 =
  `gymnasium / imageio / matplotlib / mujoco / numpy / packaging / pandas / py_trees / robosuite /
  stable_baselines3 / torch / pyyaml`，**全部在闭包内**；`draccus / lerobot / safetensors` 属
  **lerobot 那两个解释器**（不在 rlrobot），`registry / skills` 是本仓包。
- **生成器有拒绝生成的牙**（`scripts/d_build_persistent_lock.py`）：① base lock 的 pin 与当前已装版本
  不一致（DRIFT/MISSING）⇒ **exit 3**；② 闭包有 GAP（被需要但当前解释器无 metadata）⇒ **exit 4**。
  本次两道都没触发；唯一 `known_conflicts` = `robosuite 1.5.2 -> mink==0.0.5（实际装成 1.2.0）`，
  按裁定 32.2 的口径**记录不改**（解析器到不了 ≠ 不可用）。
- **身份界定（请 B 登记，见 §34-B③）**：`requirements.persistent.lock.txt`（`sha256_12=69d61657f531`，82 pin）
  **不是门禁产物**、不参与 `GATE_BUILD`、**不被** `c_env_manifest.py::_parse_lock` 读取；
  门禁与 B/C 的自检仍只读 `requirements.lock.txt`（28 pin，`sha256_12=d1ea71b7b4e5`，**D 一字节未改**）。
- **排除 `jax`/`jaxlib`**（base 有 0.10.2）：仓里**执行的**代码 0 处 import jax（只有
  `RL_Harness_v4_20260924/materials/` 的**只读调研快照**里有），而 conda 的 jax/tensorflow 正是
  installer 注释记的 09-24 ImportError 污染源。**实测新 venv 里 `import jax` / `import tensorflow`
  均 `ModuleNotFoundError` ⇒ 这是设计意图，不是缺失**（C 的 `inherited_packages` 观测语义要跟着改，§34-C③）。

## §32 裁定 33.3：`rlrobot` 已迁到 NFS 持久层并**接上 `/root/venvs`**；断点 `BP-20260929-rlrobot-persistent`，`invalidates = 无`

### 32.1 建成与切换（全部 D 现场实测）
- 建成：`mkvenv rlrobot requirements.persistent.lock.txt --clean --find-links .../pytorch-wheels/cu124/`
  ⇒ uv 0.11.24、**223.8s**、**6.4 GB**、82 pin 全装、`include-system-site-packages = false`。
- 切换：`/root/venvs/rlrobot` 现为**软链** → `.codex-persist/envs/rlrobot`（14:35）；
  旧的 overlay venv `mv` 到 `recycle_bin/rlrobot_overlay_20260929_143331`（**回滚 = mv 回来 + 重指软链**）。
  `/root/venvs/` 三个 venv（含 A 的 `lerobot_act` / `lerobot_eval`）已全部登记进
  `.codex-persist/envs/symlinks.json` ⇒ **下个容器跑 `bootstrap` 会自动重放这三条软链**，
  仓里那 73 处硬编码 `/root/venvs` 一个都不用改。

### 32.2 基础验证（D 只做到这一层，其余派工）
| 项 | 命令 | 结果 |
|---|---|---|
| 断言式自检 | `codex-persist venvcheck rlrobot --import …`（14 个探针） | **35 PASS / 0 FAIL**；V6 = 82 pin 逐条相同；V8 = 14 个模块 `__file__` **全在 venv 内** |
| 阶段 0 验收 | `MUJOCO_GL=egl <venv>/bin/python scripts/env_check.py` | **rc=0**；渲染可用（平均像素 **108.5**，与阶段 0 记录同值）、RL 接口可用、`robosuite 19 envs`、`torch_cuda=True A800` |
| B 的可复现性门禁 | `OMP_NUM_THREADS=1 MUJOCO_GL=egl … b_selfcheck_reproducibility.py --repeats 2` | **rc=0，全部通过（12 项）**，含 L0-f/L0-g 的 `robosuite==1.5.2` 一致性与 L0-h 的 8 个 checkpoint obs_dim 兼容 |
| freeze 对照 | `<venv>/bin/pip freeze --local` vs 新 lock | 规范化名字后**逐包相同（80/80）**；差异只有 `pip`/`setuptools`（`pip freeze` 默认不列自身） |
| GPU | `torch.cuda` | `True` / `NVIDIA A800-SXM4-80GB`；cuda 上 64×64 matmul 通过 |
| 经软链的 smoke | `/root/venvs/rlrobot/bin/python scripts/smoke_random_policy.py --task Lift --episodes 1` | `steps=1000 success=False`（随机策略，预期）+ **视频落盘** ⇒ EGL 渲染链路通（`runs/smoke/20260929_143600/`） |

**版本等价的实质证据**：28 个项目 pin 逐格未动、`env_check` 的初始 obs 与渲染平均像素与历史记录**同值**、
B 的 12 项可复现性自检全过 ⇒ **断点 `invalidates = 无`**。**provenance 确有变化**（必须回显）：
`sys.prefix` 变成软链（`realpath` 落 NFS）、jax/tf 从可导入变成不可导入、pip/setuptools 变成本地包、
冷导入变慢。**引用解释器时一律回显 `realpath` + venv 类型（clean / system-site）**，这是本轮新增的表述纪律。

### 32.3 裁定 32.3 的三个前提：**逐条销账**
1. **lock 自足** ⇒ 选 **(甲)**，且**比 (甲) 更严**（82 pin 闭包，不是 8 个）；同时 (乙) 的断言能力也给了
   （`venvcheck` 的 V8 会点名任何「从 base 继承」的模块）。
2. **base 解释器断言** ⇒ `venvcheck` 的 **V1（`pyvenv.cfg.home` 存在）/ V2（版本 == 3.11.9）**，
   `bootstrap` 后第一件事就是跑它。**注意这条断言只能证明 base 解释器还在，不能证明 base 镜像没变**——
   clean venv 的意义正是把后者从依赖里摘掉。
3. **只读纪律 + 冷导入基线** ⇒ 纪律写进 `.persist_meta.json.readonly_after_build` 与 README；
   基线（rlrobot 侧，D 交）：**冷** torch **14.51s** / torchvision 19.05s / stable_baselines3 15.78s /
   robosuite 11.02s；**热** torch **1.64s / 1.69s**（overlay 参考值 **1.45s**）。
   ⇒ **冷导入慢约 10 倍，热态只差 ~13%**；训练循环里 import 只发生一次，**NFS venv 不是吞吐瓶颈**。
   **A 侧补测 lerobot 两个 venv 的同一组数字**（§34-A③）。

## §33 裁定 33.4：D 在验证里撞出**两处 C 侧判据缺陷**（都是真红，不是 D 用错）

D 顺手跑了 C 的 `c_env_manifest.py --check --venv <新 venv> --json-out runs/infra/d_persistent_env_20260929/…`
（**没有覆写 C 的默认产物路径**），结果 `lock 一致性 28/28 match`、`required 探针 13/13 OK`、
`门禁构建 v1.5 / f19f61341cbe` 未动，但 **rc=3**，两条：

- **C-F1（P1，假红）**：`blocking 缺失 ['lerobot']` ⇒ `env_fully_restored=False`、
  `reproduction_claims_blocked=True`。**这是设计如此**（B 的 §9.2 更正、裁定 31.2 已立此口径）：
  lerobot **从不**装在 rlrobot 里。C 的 blocking 探针必须按**解释器分工**判定
  （rlrobot 解释器里 lerobot 应是 `not_applicable`，不是 `missing`），
  否则**每次**都给出一个假红并顺带把复现主张全阻。
- **C-F2（P0，真红，判据本身抓到了不一致）**：`断点分类规则自测 all_match=False`（6 格里 5 格不符）。
  成因 D 已定位：manifest 的 `venv.created_at = 2026-09-29T14:21:08`（**D 新建的持久 venv**）
  晚于 `ready_at = 2026-09-29T10:57:19`（取自 `runs/infra/c_env_rebuild_20260929/rebuild2.log` 的 mtime，
  那是**上一个 overlay venv** 的 ready 时刻）⇒ `[created, ready]` 窗口**反向**，自测的 5 个期望全落空。
  **判据没错，错的是 `ready_at` 的来源没与被描述的 venv 绑死**：ready 时刻必须与「被描述的那个 venv」同源
  （例如从 `.persist_meta.json` 的 `created_at + elapsed_s` 推，或要求调用方显式 `--ready-at`）。
  **C 修之前，任何用 `--venv` 指向非 C 重建那份 venv 的 `--check` 都会 exit 3**（包括 A 装完 lerobot 后想复用它）。
- **一般规则（本条真正要立的）**：**判据的每一个输入都必须与被描述的对象同源。**
  今天已经出现三次同型问题（裁定 29.1 的 spec 轴引用锚、裁定 31.3 的跨构建混算、本条的跨 venv 混算）：
  **把「上一次那个对象」的时间/指纹/构建当成「这一个对象」的属性**，判据就会既红得莫名其妙、又真得不容忽视。

## §34 对三线的要求（增补十）

- **B（P0，详见 `rl_harness_supervision/d_handoff_to_b_20260929.md`）**：
  ① **门禁不受环境迁移影响的证明**：在新解释器上复跑全量自检 + `b_regate_all.py`，断言**裁定变化 0 处**、
  权威表 `25/22/1`、计数层 `135/235/7/0/0`（raw 377 / 分母 960）逐格不变，`GATE_BUILD` 仍是 `f19f61341cbe`。
  ② **`scripts/setup_env.sh` 的 freeze 覆写护栏（D 现场发现的新风险，P0）**：脚本末尾
  `pip freeze --local > requirements.lock.txt`，而现在存在**自足 venv** ⇒ 若有人
  `VENV=.codex-persist/envs/rlrobot bash scripts/setup_env.sh`，那份 **28 pin 的门禁产物会被覆写成 82 pin**
  （含 torch/nvidia-*），provenance 头也会被改写。**该脚本在 B 的写入边界**：要么按
  `include-system-site-packages` 断言后拒绝覆写、要么加 `--persistent` 模式分流到另一个文件名。
  ③ **登记 `requirements.persistent.lock.txt` 的身份**（不是门禁产物 / 生成器是谁 / 与 28 pin lock 的关系），
  并给它挂一条牙（建议 L0 系列加「persistent lock 头部 `base_lock` 的 `sha256_12` == 仓里 `requirements.lock.txt`」）。
  ④ **git 代提交**（DR-003 决定 8）本轮 D 的仓内新增/改动，提交前跑 `scripts/b_git_size_guard.py`。
  ⑤ **P1**：v1.6 一次做完（裁定 23 六项 + 裁定 31.5① 的 `condN` 改名 + 裁定 31.5② 的声明落 `configs/`），
  落地即升 build ⇒ **主动通知 D 跑第三轮复签**；⑥ **P1**：`C5=0.04` 的**双阈值并行重判**现在**解锁**了
  （裁定 29.5 第 3 条的排期前提「等 A 迁表完成」已满足，见增补八 §21）——**先预登记、不得原地改常数**；
  ⑦ **P1**：动作侧饱和率要进 warn 就得先出「饱和率 × 受控成功」的 48 臂实测表，否则维持未裁。
- **A（P0）**：① 按原执行单 §6 验收 `lerobot_act`/`lerobot_eval`（**版本断言 0.4.4，不是 importable**）；
  ② `LOCK_OUT` 已正确覆写到 `runs/infra/a_lerobot_env_rebuild_20260929/` ⇒ 继续按裁定 32.4 出 diff 报告，
  **并回显 0928 两份原件 mtime 未变**；③ **补测 lerobot 两个 venv 的冷/热导入基线**（与 §32.3 第 3 条同格式）；
  ④ 执行单 **§2「不要用 mkvenv」已被本轮修复取代**（`mkvenv` 现在可用），但**这两个 venv 仍走 installer**
  （它们需要 uv 的 `--override numpy==2.4.6` 与门槛验证，裁定 32.2 第 1 条不变）；
  ⑤ **§5「rlrobot 持久化」已由 D 做完，A 不必再做**（软链已登记，`bootstrap` 会自动重放）。
- **C（P0/P1）**：① **C-F2 修 `ready_at` 同源**（P0，见 §33）；② **C-F1 的 blocking 探针按解释器分工**（P1）；
  ③ 把断点 **`BP-20260929-rlrobot-persistent`** 加进 env manifest 的断点清单
  （**与 `BP-20260929-venv-rebuild` 并列不合并**；条目内容 D 已写在 `verification.json.breakpoint`，
  `invalidates = 无`），并把 `inherited_packages` 的语义从「base 继承观测」改成**按 venv 类型分别解释**
  （clean venv 里那 8 个是**本地包**，`jax` 会是 `NOT INSTALLED` 且**这是设计意图**）；
  ④ 待办 2（登记处）仍是 P0，不受本轮影响。
- **全员（P0，表述纪律，与增补六 §7 / 七 §19 并列）**：引用解释器必须回显
  **`realpath` + venv 类型（clean / system-site）+ 是否经软链**；
  凡是「环境不变所以结论不变」这类主张，**必须给出可核断言**（本轮的样式：pin 逐格相同 + `env_check` 同值 +
  B 的 12 项自检），**不得只写「我验过了」**。

## §35 回流点（增补十）

1. **B 的 ① 与 ②** 回流 D：门禁在环境迁移后逐格不变 ⇒ D 才认「本次基础设施变更未污染任何已裁定结论」；
   `setup_env.sh` 的护栏落地 ⇒ D 复核那条牙能不能红。
2. **C 的 C-F2** 回流 D：修法要能让「`--venv` 指向任意 venv」都不自相矛盾；D 会用
   `--venv .codex-persist/envs/rlrobot` 与 `--venv .codex-persist/envs/lerobot_act` **各跑一次**验收。
3. **A 的 lerobot 验收 + 冷导入基线** 回流 D：D 复核 lock diff 与 0928 原件 mtime，
   然后才解除「跨断点复现」的封锁（增补六 §0.2 第 2 条 / 裁定 29.4）。
4. **下一轮 D 自己欠的**：裁定 29.5 第 3 条那三项里，`C5=0.04` 已派给 B（预登记后由 D 裁差集）、
   饱和率 warn 已派给 B（出表后由 D 裁）、**C 待办 6（冻结面变更）仍未裁**——
   等 C 待办 1（`physical_fact` 接线）落定后一并看，本轮**不提前批**。

---

# 增补十一（2026-09-29 14:5x，D）：裁定 34 —— A 的 3 处 lock 差异**放行但按包按链路限定** + `rlrobot` 切换已发生（B/A 的文档需追认）

> 触发：A 出 `docs/a_env_rebuild_acceptance_20260929.md`（14:42，含 §3.2 的逐条解释与「请 D 裁定」）、
> `docs/a_handoff_to_b_anchor_shift_20260929.md`（14:44）；B 出 `scripts/b_env_provenance_guard.py`
> 与 pin 文档 §7.3–§7.6（14:35–14:38）。D 全部现场独立复核。

## §36 裁定 34.1：3 处 lock 差异**不构成**跨断点复现的障碍 —— 但豁免是**按包按链路**授的，不是按次授的

### 36.1 事实（D 复核，不采信 A 的自述）
- 差异只有 **2 个包 / 3 处**：`ImageIO 2.37.4 → 2.38.0`（两份 lock 各一处）、`uv 0.12.19 → 0.12.17`（仅 act lock）。
  D 用**B 的闸**独立复算（`b_env_provenance_guard.py`，`--json-out` 指到 D 自己的目录，未覆写 B 的产物）：
  `changed=2/1`、`added=0`、`removed=0` ⇒ **与 A、B 两方的枚举三方一致**。
- **权威 pin 逐字相同**：`lerobot 0.4.4`、`torch 2.6.0+cu124`、`torchvision 0.21.0+cu124`、
  `numpy 2.2.6（act）/ 2.4.6（eval）`、`gymnasium 1.3.0（act）/ 1.2.3（eval）`、`robosuite 1.5.2`、`mujoco 3.9.0`。
- 成因是**镜像内容会动** + installer 两处**未钉版本**（`:77` 只钉 `imageio-ffmpeg==0.6.0`、没钉 `imageio` 本体；
  `:36` 的 `pip install -q uv` 未钉）⇒ 解析器取当时候选。**A 的解释成立。**

### 36.2 裁定
1. **放行**：这 3 处**不阻塞**跨断点复现主张，理由是①承载结论的权威 pin 逐字相同；
   ②两个差异包**不在 48 臂权威表与官方 ACT 链路的 import 面上**（A 已 grep 实测：ACT 三件套与
   `summarize_lerobot_act_arms.py` 都不 import imageio；全仓无 `import uv`）；
   ③ `uv` 是**安装期工具**，进 lock 只是「用什么工具装的」这一事实的记录，不进运行时。
2. **限定（本条的实质）**：豁免**限定在「这 2 个包 + 这 2 份 lock + 这条链路」**。
   引用时必须**点名包与版本**（`ImageIO 2.37.4→2.38.0`、`uv 0.12.19→0.12.17`），
   **不得**写成「lock 差异已裁定可忽略」这种无限定句。
   **下次重建若出现任何新增差异（含同两个包再浮动），一律重新报 D。**
   ⇒ **一般规则：lock 差异的豁免是按包按链路授的，不是按次授的。**
3. **A 提议的 `--override imageio==2.37.4` 重装：不批准。** 理由：会动「建成后按只读对待」的 NFS venv
   （裁定 32.3 第 3 条），而 `2.37.4` 不是任何判据的输入 ⇒ **收益为零、风险非零**。
4. **根因必须堵掉（B 的写入边界，见 §37-B⑤）**：钉 `imageio==2.38.0` 与 `uv==0.12.17`
   ——**钉「实际装成并跑通门槛验证」的那个值**（与裁定 32.2「lock 是事实源」同型），
   **不要**回退到 0928 的 `2.37.4`（回退等于按意图改事实）。
5. **溯源不受影响**：0928 的两份 lock 仍是「48 臂当初跑在什么环境上」的唯一答案（`ImageIO 2.37.4`），
   **新环境是新事实**（`2.38.0`），两者并存（裁定 32.4 的精神）。**新训练/新评测的产物必须回显新 lock 的 sha256**，
   否则「这条结论跑在哪个环境上」又会变成不可答。
6. **本裁定不解除 A 的 E6**：A 的就绪闸唯一红项 **E6（C 的探针）** 仍在 ⇒
   A 现在**可以**声称的：环境可用、0928 溯源未被覆写、只读后处理结论、官方 ACT 链路上的复现；
   **仍不得**声称的：任何**新训练 / 新评测**的复现主张（含 48 臂权威表的跨断点复用、§8 晋级条件①的推进），
   **直到 E6 闭合**。

## §37 裁定 34.2：`/root/venvs/rlrobot` **已在 14:35 切成软链** —— B 的 §7.5 与 A 的 §4 表需追认（不是纠错，是时序）

- **事实**：14:35 起 `/root/venvs/rlrobot` 是**符号链接** → `.codex-persist/envs/rlrobot`
  （自足 clean venv，14:24 建成）；C 重建的那份 overlay venv 已 `mv` 到
  `recycle_bin/rlrobot_overlay_20260929_143331`（**回滚 = mv 回来 + 重指软链**）。
  三条软链（含 A 的 `lerobot_act`/`lerobot_eval`）已登记进 `.codex-persist/envs/symlinks.json`
  ⇒ **下个容器 `bootstrap` 自动重放**。
- **B 的 pin 文档 §7.5 第 2 条**（14:38 写「当前在用的仍是 `/root/venvs/rlrobot`（真实目录、带
  `--system-site-packages`）…**切换属 A/infra 的决定，B 不代做**」）**在写下时已过期 3 分钟**：
  切换是**用户直接指令**下由 D 做的（增补十开头），**不是** A/infra 的待决项。
  ⇒ 按 append-only：**原文不改，挂更正指针到本节**。B 的判断本身没错（B 不代做 infra 决定是对的）。
- **A 的验收回执 §4 表**（`rlrobot … include-system-site-packages = true（继承 base；D §5 的甲/乙选择尚未裁定）`）
  同样过期：**(甲) 已裁定并已建成**（增补十 §32.3 第 1 条）。A 重出 env manifest 时该行必须刷成
  `false` + `realpath` 回显。
- **切换后的独立复核（D 现场，用 B 的闸）**：
  `b_env_provenance_guard.py --venv /root/venvs/rlrobot` ⇒ **PASS 5 / WARN 0 / RED 0，exit 0**
  （G1 0928 两份 lock sha 与 mtime 未动、G2 `LOCK_OUT` 非默认、G3 82 pin 逐 pin 对账含 `+cu124`、
  G4 base 解释器四项、G5 生效 numpy == 2.4.6）；产物 `runs/infra/d_persistent_env_20260929/guard_after_symlink_switch.json`。
  ⇒ **切换未破坏 B 的任何一条环境判据。**
- **B 的 `b_env_provenance_guard.py` 与 G1–G5 + 10/10 变异自检：D 验收通过。**
  特别认可两点：① **M8 是反向变异**（freeze 用发行名原样 `ImageIO`/`Jinja2`/`typing_extensions`…且不含
  `pip`/`setuptools` ⇒ **不得**误报缺失）——这正是 D 在增补十 §32.2 独立撞到的同一处假红，
  **B 先一步做成了牙**；② G2 对「差异 0 处」会 WARN（防空比对被读成通过），与裁定 27.1「恒假的闸等于没有闸」同型。

## §38 对 A / B 的要求（增补十一）

- **A（P0）**：① 重出 env manifest 时把 `rlrobot` 那行刷成 `include-system-site-packages = false` + `realpath`
  （§37）；② **补测 lerobot 两个 venv 的冷/热导入基线**（格式照增补十 §32.3 第 3 条；D 已交 rlrobot 侧：
  冷 torch 14.51s / 热 1.64s）；③ **锚点移位单已收到**（`docs/a_handoff_to_b_anchor_shift_20260929.md`）——
  A 主动报而不代改 B 的文件，**做法正确**，D 认可；那 4 条由 B 处理（§37-B⑥）；
  ④ **E6 未闭合前不得开新训练/新评测的复现主张**（§36.2 第 6 条）。
- **B（P0/P1，完整执行单见 `rl_harness_supervision/d_handoff_to_b_20260929.md`）**：
  ① 门禁在环境迁移后**逐格不变**的证明；② `setup_env.sh` 的 **freeze 覆写护栏**（G1 是**事后**检测，
  这条要的是**事前**拒绝）；③ 登记 `requirements.persistent.lock.txt` 的身份并挂牙；④ git 代提交本轮 D 的仓内改动；
  ⑤ installer 钉 `imageio==2.38.0` 与 `uv==0.12.17`（§36.2 第 4 条）；⑥ A 报的 4 条锚点移位（含 1 条**A 动手之前就已失效**的
  `:44` vs `:36`）；⑦ P1：v1.6 一次做完 + 通知 D 复签、`C5=0.04` 双阈值并行重判（**已解锁**）、饱和率实测表。

## §39 回流点（增补十一）

1. **B 的 ①②③⑤⑥** 回流 D 复核（②③⑤ 都要「先证明牙能红」再判现场，与 G1–G5 同标准）。
2. **A 的 ①②** 回流 D：manifest 刷新 + 冷导入基线到位后，D 才把「环境侧」整块结案。
3. **E6（C 的探针）** 仍是 A 线唯一红项 ⇒ C 的 P0（增补十 §34-C①②）与 A 的解封**同一条关键路径**。
4. **裁定 34 的可红条件**（防止它被读成恒真）：若将来发现 `imageio` 或 `uv` **确实**出现在 48 臂链路
   （任一 ACT 脚本或 `summarize_lerobot_act_arms.py` 的 import 面）⇒ 本裁定**自动作废**，
   3 处差异重新变成阻塞项，A 的相关产物要按新环境重跑。

---

# 增补十二（2026-09-29 15:0x，D）：裁定 35 —— 结 A 的 §12 提请（选 **(a)**）+ **D 第十次自我纠错** + A 的 D8 护栏**覆盖不到它声称覆盖的那件事**

> 触发：A 的 `docs/a_handoff_to_d_20260929.md` §2 与 `daily_report.md` §12 提请「增补七 §19-A⑤ 与
> **迁移回归基线**冲突，请 D 二选一」。这是 D 手上**唯一一条未结的一线提请**，本轮结掉。
> D 现场只读核了 `attribution/` 目录、`migration_regression_v121_to_v15.json` 的字段、
> 以及 `scripts/a_distribution_layer_check.py` 里 D8 的**判据体**。

## §40 裁定 35.1：选 **(a)** —— 认可 A 的替代落地，**§19-A⑤ 改判 CLOSED**；基线 meta **不得刷新**

**事实（D 独立复核，不看 A 的自述）**：
- `attribution/arms_summary_v3.json`：mtime **11:08 未动**、`meta` 三值仍是
  **`v1.2.1 / e4f5ec887788 / 494d5f5babf9`**、`schema_version 3`、**48 臂**；旁挂
  `attribution/README_BASELINE.md`（12:39）**已存在**。
- `attribution/migration_regression_v121_to_v15.json`（12:01）的顶层 **`baseline` 字段就是那个路径**
  （D 实测其值 = `runs/infra/lerobot_act_env_20260928/attribution/arms_summary_v3.json`）
  ⇒ **A 的第 1 条理由成立且可核**：刷它的 meta = 把断言的**左操作数改成右操作数**。

**裁定**：
1. **选 (a)**。A 的替代落地（① 文件一字节未动 ② 旁挂 `README_BASELINE.md` ③ 机器护栏 D8）**予以认可**，
   **§19-A⑤ 改判 CLOSED**。(b) 那条路（仍要求刷 meta）**不成立**：D 无法在「刷掉唯一一份 v1.2.1 汇总表」之后
   指定新基线从何而来——重判只会得到 v1.5 裁定，**A 说的这点是对的**。
2. **D 第十次自我纠错**：§19-A⑤ 的字面要求（「迁表后 meta **必须**刷成 `v1.5 / f19f61341cbe`」）**是错的**。
   照字面执行会让 `migration_regression_v121_to_v15.json` 退化成「v1.5 与 v1.5 比、差异 0」的**恒真判据**，
   DR-008 验收判据 3 与 裁定 28 ③「能力结论一个字都不变」就此**失去机器担保**。
   裁定 31.1 曾用「要求已满足」绕过它（迁后权威表是 `arms_summary.json`、`a_table_role = post_migration_table`），
   **但没有明说字面要求本身是错的** ⇒ 现在补上。**A 拒绝执行 D 的要求，这次是对的。**
3. **一般规则（本条真正要立的）**：**「把口径刷新到当前值」这类要求，必须先问「这个文件是不是某个断言的操作数」。**
   基线 / 历史口径文件的价值恰恰在于它**停在旧值**；刷新它 = **销毁断言**。
   与 裁定 16.3 / 改判 7「旧表降级为历史口径（**不作废、必须仍可核**）」同源，
   与 裁定 32.4「0928 的两份 lock 不得被覆写」**同型**。**今天第四次同型**
   （前三次：裁定 29.1 spec 轴引用锚、裁定 31.3 跨构建混算、裁定 33.4 跨 venv 混算），
   **但这一次是 D 自己的要求触发的**，所以记为自我纠错，不是记在 A 账上。

## §41 裁定 35.2：A 的 D8 护栏**覆盖不到它声称覆盖的那件事**（D 现场核出，代码级实证）

A 写的是「若有人真去刷了基线 meta，**D8 立即变红**」（`docs/a_handoff_to_d_20260929.md:49-51`）。
**D 读了 D8 的判据体（`scripts/a_distribution_layer_check.py:384-394`），这句不成立**：

```
d8_terms = {historical_table_readable        : bool(h_doc)
            historical_n_artifacts_is_44     : h_doc.get("n_artifacts") == 44
            historical_invalid_arms_7        : len(h_invalid) == 7
            current_invalid_arms_1           : n_invalid_now == 1
            invalid_arm_count_changed        : len(h_invalid) != n_invalid_now
            target_arm_was_invalid_in_v121   : any(arm == TARGET_ARM and citable == NOT_CITABLE_…)
            counting_layer_a_equals_b        : …}
```
`h_doc` 在整个脚本里只被读三种东西：**可读性**（`:385`）、**`n_artifacts`**（`:377`/`:386`）、
**臂行**（`:375-377`/`:392`）⇒ **历史表的 `meta`（`gate_version` / `gate_build` / `gate_spec_sha256`）一次都没被读过**。
**结论：只刷 meta、不动 `n_artifacts` 与臂行 ⇒ D8 的七个 term 全为真 ⇒ D8 保持 GREEN。**
（D 没有真的去刷那份基线来演示——它是断言的操作数，**动它本身就是本裁定禁止的事**；
这里的证据是**判据体的穷举阅读**，可复核。）

**要求（A，P0，很小）**：
1. 给 D8 补一个 term：`historical_meta_is_v121` =
   历史表 `meta` 三值 == `['v1.2.1'] / ['e4f5ec887788'] / ['494d5f5babf9']`（**逐值比，不是比"非空"**）。
2. 补一条变异 **S11**：把历史表 meta 刷成 `v1.5 / f19f61341cbe / c7fadabe8e3c`（**在 fixture 里刷，不碰真文件**）
   ⇒ **D8 必须红**。与 B 的 `M8`（反向变异）、`G2`（空比对 WARN）**同一标准**：
   **声称"会红"的护栏，必须演示一次红。**
3. **在补上之前**，「若有人真去刷了基线 meta，D8 立即变红」这句**不得被引用**（按裁定 27.1，
   覆盖不到目标场景的闸 = 恒真闸 = 没有闸）。A 的文档按 append-only 挂更正指针到本节。
4. **性质界定**：这**不是** A 的三条理由有问题（理由①②③ D 全部采纳），而是**「已有机器护栏」这句过度声称**
   ——与本仓今天反复出现的同型：**把"我加了判据"当成"判据覆盖了这件事"**。A 主动报冲突而不代做，**这个行为仍然正确**。

## §42 裁定 35.3：把护栏搬进断言产物本身（P1，A）

旁挂 `README_BASELINE.md` 是好东西，但**它是散文**：下一个来"修口径"的人不会先读它。
**要求**：重出 `migration_regression_v121_to_v15.json` 时（**写新文件，不覆盖 12:01 那份**），
在产物里显式带上 `baseline_meta = {gate_version, gate_build, gate_spec_sha256}` 三值
+ 一句 `baseline_meta_must_not_be_refreshed`（指向本裁定）。
⇒ **断言产物自带护栏**，即使旁挂说明被忽略，diff 一眼就能看出基线被刷过。

## §43 可红条件与回流点（增补十二）

1. **本裁定的可红条件**：若 `attribution/arms_summary_v3.json` 的 `meta` 三值不再是
   `v1.2.1 / e4f5ec887788 / 494d5f5babf9`（= 有人刷了基线）⇒ 裁定的前提失效；
   **此时 D8 应当变红**——若 D8 没红，就证实了 §41（护栏覆盖不到），A 的补做项立刻升 P0 且**回溯追责该次刷新**。
2. **回流**：A 的 §42-1/2（D8 补 term + S11 变异）回流 D 复核；D 会**只读**跑一次
   `a_distribution_layer_check.py` 的自测，看 S11 是否真的把 D8 判红。
3. **D 手上现在没有未结的一线提请**（本轮结掉了最后一条）。**仍未裁的三项维持原状**（裁定 29.5 第 3 条）：
   `C5=0.04` 已派 B 做预登记双阈值重判（**不是已裁**）、饱和率 warn 等 B 的实测表、
   **C 待办 6（冻结面变更）D 暂不批准**。

---

# 增补十三（2026-09-29 15:1x–15:2x，D）：裁定 36 —— **B 的 P0-1 验收通过** + **D 第十一次自我纠错（两项）** + 冷导入基线**跨口径**不得并列

> 触发：本轮 D **回归监管位**（用户指令：安装/修复是一次性例外，做完基础验证后统筹三线）。
> D 现场只读实测了 B 的 `runs/infra/b_env_migration_invariance_20260929/`（六份产物 + `invariance_verdict.json`）、
> A 的 `runs/infra/a_env_manifest_20260929.json`（15:13 重出）、冻结面 5 处的 mtime/sha、
> `scripts/b_regate_all.py:109-146`、`scripts/a_distribution_layer_check.py:481-565`、`scripts/setup_env.sh:94-108`。
> **本节不含任何新的安装/修复动作**（用户已收回该授权，D 也不再动 `.codex-persist/`）。

## §44 裁定 36.1：**D 第十一次自我纠错（两项同批）** —— 都是 D 下发的要求本身有错

1. **变异编号 `S11` 已被占用 ⇒ 改 `S13`。** 裁定 35.2 要求 A「补一条变异 **S11**」，但 D 现场读
   `scripts/a_distribution_layer_check.py:481-565` 的既有编号表：`S11` = **缺 actlog_subset 臂集 -> CLOSED(D7,D3)**
   （`:557-560`）、`S12` = **跨 build 混引 -> CLOSED(D10)**（`:565`）⇒ **两个都已占用**，A 若照字面执行
   只能撞号或改别人的用例。正确编号是 **`S13`**（形态照 `S10 v1.2.1 历史表不可读 -> CLOSED(D8)`，`:555`）。
   **根因（与 A 的 D8 过度声称同型，只是方向相反）**：D 在写要求时**没有先读被要求方的既有编号表**
   ——即「**引用锚未核**」。裁定 29.1 立的那条一般规则（**引用锚易失效 ⇒ 引用前必须实测**）
   **同样约束 D 自己**，这是它第 5 次生效（前四次都用在 A/B 身上）。
   **更正落点**：`d_handoff_to_a_20260929.md` §9.6-2（已写 `S13` 并明说是 D 的错）；本节为原始更正指针。
2. **`b_selfcheck_golden_values.py --json` 是输入不是输出。** D→B 执行单 §1 让 B 把
   `--json "$OUT/golden_values.json"` 当输出用；B 实测该脚本 `:35` 的 `--json` 默认值是
   `docs/b_golden/async_td_golden_v1.json`、`:41` 立刻 `read_text()`，**全脚本不写任何 JSON 产物**
   ⇒ 照 D 的原命令跑必然 `FileNotFoundError` + `rc=1`，**那不是环境迁移的红，是 D 的命令错**。
   B 的处置（不带 `--json`、stdout 留 `golden_values.log`、mtime 校验里按 log-only 不算 STALE/MISSING）**批准**。
   **B 主动查出并顶回 D 的命令，这个行为正确**（与本仓「不采信自述、写前先实测」同型；A 的 §12 提请、
   A 的锚点移位单是同一批行为）。
   **衍生要求（P2，B，随 v1.6）**：给 `b_selfcheck_golden_values.py` 加 `--json-out`，
   否则「D 只看产物」这条纪律对这一项**永远只能降级成看日志**（六套自检里唯一一套没有机器产物的）。

## §45 裁定 36.2：**B 的 P0-1（门禁不受环境迁移影响）验收通过** —— D 独立复核，不采信 B 的自述

D 自己把六份产物重新解析并与 12:4x 基线逐格对齐（**只读**，产物在 B 的目录、D 未写一字）：
`reproducibility 12/12`｜`gate_regression ok=True 157/157 断言·39 用例`｜`gate_mutation all_ok=True
baseline_all_green=True 15/15`｜`golden_values.log 47/47 rc=0`｜`t17_mutation ok=True 6 个 status=pass（含正对照 M0）`｜
`regate n_verdict_changes=0 n_arms_matched_vs_old=16 comparison_vacuous_sets=[] regression_ok=True`｜
`reclassification n_artifacts=48 citable 25/22/1 ic_status 45/2/1 measurement_valid 47/1
pending_cosign_reverify.n=0 git_commit=fe526d89…`｜四份带指纹产物全部 `v1.5 / f19f61341cbe / c7fadabe8e3c…`。
**⇒ 与迁移前基线逐项相同，P0-1 销账。**

**D 特别认可的两处「有牙」（不是「跑了一遍」）**：
1. `invariance_verdict.json` 把 **`baseline_constants` 与 `red_conditions` 写进产物本身**，
   且 **V6 把「空比对的 0 处」单列为红**、**V9 把「改脚本没重跑（产物 mtime < 脚本 mtime）」单列为红**
   ⇒ 结论**可核且可红**，符合裁定 27.1 与 §8.1。
2. `interpreter.txt` 回显 `realpath(prefix)=…/.codex-persist/envs/rlrobot` + `prefix_is_symlink=True` +
   `include-system-site-packages=false` + 生效 `numpy 2.4.6 / torch 2.4.1+cu124`
   ⇒ **「这份不变性是在迁移后的解释器上测的」这个前提本身被钉住了**。
   **没有这一条，整份证明可以是旧环境跑的而看不出来**——这正是本仓反复吃的亏（自证形态）。

**D 侧另行独立核到的冻结面（不看 B 的「附带确认」）**：0928 两份 lock `68a38731c5b5…`/09-28 14:56 与
`b6db07e2e31c…`/09-28 15:24（未动）｜`attribution/arms_summary_v3.json` 11:08（未动，裁定 35.1 的前提仍在）｜
`runs/infra/lerobot_act_env_20260928/arms_summary.json` **12:33**（**B 的 15:05 重跑没有改写权威表**）｜
门禁 28 pin `requirements.lock.txt` 12:13（未动）｜被判的 `clip*.json`/`noclip.json` 仍 09-28 16:4x–16:5x。
**⇒ 裁定 32.4 / 35.1 的冻结面无一处被破。**

## §46 裁定 36.3：**同 build 重跑就地覆写、不留旧字节** —— 判 **P2 留白**，不是违规，D 现在不要求改

代码级实证：`scripts/b_regate_all.py:109-125` 的 `snapshot_if_stale()` **只在旧产物的 `gate_build`
与当前构建不同时**才 `copy2` 留档，`builds == {cur_build}` 时**直接 return None**；
`judge_set()` 随后 `:146` `out_path.write_text(...)` **就地覆写**。
本轮被覆写的三份（均 **15:05**，目录里**没有**新的 `*.build_f19f61341cbe.json`）：
`runs/infra/b_normclip/gate_v12.json`、`runs/infra/b_normclip2/gate_all.json`、`runs/infra/b_gate_sensitivity/report.json`。
- **当前无害**：被判产物冻结、构建冻结，且 `judge_set()` 是**先读旧值（`:139-145`）再覆写**
  ⇒ `n_verdict_changes=0` 是**真比对**、不是空洞真（V6 也单独把空洞比对判红）。
- **留白在**：**同 build 下若内容真的漂了，没有旧字节可对**，只有当次算出的 diff 计数。
- **裁定**：判 **P2**（既有纪律的设计留白：快照按 build 命名，本来就是为「跨构建留档」设计的），
  **不违反** 裁定 32.4，**不要求**现在改（改它要动 `b_regate_all.py`，而它正在被门禁链路使用）。
  **建议随 v1.6 一起做**：同 build 覆写前也留 `*.pre_<UTC>.json`，或重跑只写本次 run 目录、
  就地覆写改成需要显式 `--in-place`。

## §47 裁定 36.4：冷导入基线**跨口径不得并列** —— A 拒绝把两组数并列是**对的**

**两组数（都在产物里，都可复核）**：
- **D 侧（`runs/infra/d_persistent_env_20260929/verification.json`）**：`torch` **冷 14.51s / 热 1.64s**
  （overlay 参考 热 1.45s）。**口径 = 新建 venv 后的首次读**（14:24 建成、随即测），
  NFS 上文件从未被本机读过 ⇒ 页缓存、dentry/inode 全冷；**没有** `drop_caches`；每模块一个子进程。
- **A 侧（`runs/infra/a_env_manifest_20260929.json` → `cold_import_baseline_v2.json`）**：
  `lerobot_act` 复合 **冷 15.74 / 热 5.38**、`torch` 单测 **冷 4.68 / 热 1.86**；
  `lerobot_eval` 复合 **冷 7.71 / 热 3.03**、`torch` 单测 **冷 4.55 / 热 1.82**。
  **口径 = 对自有 venv 的整份 site-packages 做 `posix_fadvise(DONTNEED)` 逐出**（**不** `drop_caches`
  ⇒ 不干扰同机 B/C），dentry/inode 仍热；A 并**主动更正了自己第一轮**的两处（`import lerobot` 只读
  `importlib.metadata`、不能当冷探针；第一轮只逐出 4 个目录 ⇒ 其冷值是下界）。

**裁定**：
1. **两组数不是同一口径，不得并列。** 具体禁止：**「rlrobot 的 torch 冷导入 14.51s，比 lerobot 的 4.68s 慢 3 倍」**
   这类说法**一律不成立**（差异里混着：首次读 vs 逐出后重读、torch 2.4.1 vs 2.6.0、两套文件布局）。
   **A 在 manifest 里明写「两者不是同一口径」而没有硬比，这个判断正确**，D 采纳 A 的口径声明。
2. **结论在两个口径下同向成立**，因此**不要求补测**：冷 ≫ 热（D 侧 ~10×、A 侧 2.5–2.9×），
   而 **import 在训练循环里只发生一次** ⇒ **NFS venv 不是吞吐瓶颈**，不需要为 NFS 做「首轮预热」建议
   （裁定 32.3 第 3 条到此**结案**）。
3. **明确禁止在 B/C 在跑时做「可同口径化」的补测**：要让两组数同口径，就得对 `rlrobot` 的 site-packages
   做同样的 `posix_fadvise` 逐出，而 **B/C 此刻正在用同一个解释器跑判据** ⇒ 逐出会直接拖慢它们、
   并让它们的耗时类观测失真。**A 的口径（只逐出自己 venv）是安全的，D 的口径（新建后首读）是不可重放的**
   ⇒ 这个不可比是**永久的**，写进产物即可，不必消除。
4. **同型计数**：这是「**跨口径混算**」——今天**第五次同型**
   （裁定 29.1 spec 轴引用锚、裁定 31.3 跨构建混算、裁定 33.4 跨 venv 混算、裁定 35.1 基线 meta 刷新）。
   **一般规则（本条要立的）**：**并列两个数之前，先并列它们的口径**；口径不可同化时，
   **结论只能取两者同向的那部分**，差值不得被解释。

## §48 裁定 36.5：A 的 §9.4 两项**验收通过** + `a_env_provenance.py` **认可** + **关键路径现在在 C**

1. **§9.4-1 销账**：`a_env_manifest_20260929.json`（**15:13** 重出）的 `sibling_venv_readonly.rlrobot` 已是
   `include-system-site-packages="false"` + `is_symlink=true` + `realpath=…/.codex-persist/envs/rlrobot`，
   并**连 `.persist_meta.json` 一起回显**（`n_pins=82`、`requirements_sha256_12=69d61657f531`、
   `installer=uv`、`clean=true`、`created_at=14:24:52`、`elapsed_s=223.8`、`no_deps=true`）
   ⇒ **比 D 要求的两行更多**，且 A 明写「A 只读观测，不代 C/D 验收」——**边界拿捏正确**。
2. **§9.4-2 销账**：见 §47（四个数 + 口径 + 自我更正）。
3. **`scripts/a_env_provenance.py`（15:10，旁挂 sidecar）认可**：不改既有产物 schema（0924 ckpt 必须仍能
   `strict=True` 加载）、`try/except` 非致命 + 大声 `[WARN]`（**静默没有溯源正是它要治的病**）、
   其余 4 个 A 侧入口**等 E6 解封后第一次真跑之前再接线**（**批准**：现在接只会产出「没有真跑在用」的代码）。
   **D 的验收点**：E6 解封后第一次真跑，看产物目录里是否真有 `env_provenance.json`、
   其中新 lock 的 sha256 与 `runs/infra/a_lerobot_env_rebuild_20260929/` 两份**逐字相同**、
   并回显 0928 两份旧 lock 的 sha256（证明新旧并存）。
4. **A 线唯一红项仍是 E6，关键路径现在在 C**：A 的 `readiness_gate` 现值 `BLOCKED / failed=["E6"] /
   blocking_fail=1 / total_checks=7`，E6 读的是 **C 的** `runs/infra/c_env_manifest_20260929.json`（**14:54**）。
   C 此刻正在改 `scripts/c_env_manifest.py`（15:12+，代码注释里已明写 C-F2 的修法与
   「拿它当 ready_at 就是 C-F2 那个跨 venv 混算」）⇒ **C 重出 manifest = A 解封 = 本仓当前唯一关键路径**。
   **D 不代 C 重探、不改 C 的文件**；D 的复核方式见 §49-2。
5. **A 的 §9.1 提请（IMAGEIO 默认值）已闭合**：`scripts/install_lerobot_act_env.sh:52-53` 现为
   `IMAGEIO=2.38.0` / `UV=0.12.17`（B 15:07），与裁定 34.1「钉实际装成的值、不回退」一致 ⇒ **P0-4 销账**。

## §49 三线台账与回流点（15:2x，D 只读实测）

1. **台账**（依据 = 文件 mtime / 产物内容，不是任何人的自述）：
   - **B**：P0-1 ✅（§45）、P0-4 ✅（§48-5）；**未动**：P0-2（`scripts/setup_env.sh` mtime **12:13**，
     `:101-108` 仍是 `{ …freeze… } > "$LOCK"`、`LOCK=:56` = 门禁 28 pin ⇒ **在 clean venv 里照默认跑一次
     就会把 28 pin 覆写成 82 pin**，G1 只能事后抓）、P0-3（`b_env_provenance_guard.py` **14:34**，无新牙）、
     P0-5（`b_selfcheck_goal_conditioning_t17.py` **11:58**、`b_gate_controlled_success.py` **11:07**，
     均早于 A 14:44 的移位单）、**P0-6 git 代提交**（HEAD 仍 `fe526d8`；工作区 16 改 + 11 未跟踪，
     含 D 的三份 handoff、`requirements.persistent.lock.txt`、`scripts/a_env_provenance.py`、
     `scripts/b_env_migration_invariance_check.py`）。**顺序建议**：P0-2 → P0-3 →（P0-5 + P0-6 收尾）。
   - **A**：§9.4 两项 ✅、`a_env_provenance.py` ✅、T17 A 侧 2 项 ✅；**待做**：D8 补 term
     `historical_meta_is_v121` + 变异 **`S13`**（P0，很小；补上前不得引用「D8 立即变红」）、
     P1 迁移断言产物带 `baseline_meta`。**不解封**（E6）。
   - **C**：C-F1 / C-F2 **在改**（`c_env_manifest.py` 15:12+）；**P0-3 重探 + 重出 manifest 是全局关键路径**；
     另需登记 `BP-20260929-rlrobot-persistent`。
2. **D 的下一批复核动作（全部只读，产物写 `runs/infra/d_*`）**：
   ① A 补完 D8 后，只读跑 `a_distribution_layer_check.py` 自测，看 **`S13` 是否真把 D8 判红**（§41 的可红条件）；
   ② C 重出 manifest 后，跑 `c_env_manifest.py --check --venv` 对**一个持久 venv 与 `lerobot_act`** 各一次，
   看 C-F1（`lerobot` 在 rlrobot 里应是 `not_applicable` 而非 blocking 缺失）与 C-F2（`ready_at` 同源、
   窗口不倒置）是否真的转绿，**并看 A 的 E6 是否随之转绿**；
   ③ B 落 P0-2 后，只读核它的**双向牙**（事前拒绝 + 事后检测），并核 P0-3 的三条牙；
   ④ B 提交后核 `git log` 与 `b_git_size_guard.py` 结果。
3. **仍未裁的三项维持原状**（裁定 29.5 第 3 条）：`C5=0.04`（已派 B 做**预登记双阈值**重判，**不是已裁**）、
   饱和率进 warn（等 B 的 48 臂实测表）、**C 待办 6（冻结面变更）D 暂不批准**。
4. **一条卫生观察（请作者申报）**：`runs/infra/maniskill_state_probe_20260929/probe_maniskill_state.py`（**15:17**，
   核实 `docs/infra-gpu-render.md:98` 把 ManiSkill3 一刀切判 ❌ 是否过宽）**探针本身卫生合格**
   （docstring 明写「不写仓库其他任何文件」、只写同目录 `probe_result_<ts>.json`），
   **但目录名没有智能体前缀**（本仓约定 `runs/infra/{a,b,c,d}_*`，见 B 执行单 §9）
   ⇒ **请作者在下一份日报小节里申报归属与它服务哪条待办/裁定**；D 现在**不批准**把它当结论引用
   （它不在任何已派工的验收面上，且 `docs/infra-gpu-render.md` 属冻结面之外的文档口径变更，需先报 D）。
5. **D 自己的位置（用户指令）**：安装/修复的授权**已用完并交回**；D 本轮之后**只做监管与裁定**，
   不再动 `.codex-persist/`、不再写 A/B/C 的产物目录、不执行 git 写。

---

# 增补十四（2026-09-29 15:3x，D）：裁定 37 —— **关键路径闭合：C 的 P0-3 验收通过 ⇒ A 线解封** + 裁定 34.1 **边界收窄** + 两处「散文与判据不同源」

> 触发：C 在 **15:30** 重出 `runs/infra/c_env_manifest_20260929.json`（15:25 先出 `…probe_lerobot_act.json`、
> 15:21 先出 `c_ruling_34_1_import_surface_20260929.json`），D 随即只读复核并**自己跑** A 的就绪闸。
> D 本轮**没有**写任何 A/B/C 的文件，产物只落在 `runs/infra/d_persistent_env_20260929/`。

## §50 裁定 37.1：**C 的 P0-3 + C-F1 + C-F2 全部验收通过**（三处做法比 D 要求的更严）

1. **C-F1（P1）通过**：`probe_modules_by_interpreter` 三组（`rlrobot`/`lerobot_act`/`lerobot_eval`），每组带
   `role`/`expected`/`candidates`/`resolved_from`/`required_modules`/`missing_required`；
   `rlrobot.modules.lerobot` **仍如实记 `importable=false` + `ModuleNotFoundError`**，另用
   `lerobot_missing_here_is_by_design=true` + `missing_required=[]` + `design_note` 表达「设计如此、不计入缺口」；
   主条目 `probe_modules.lerobot` 改成 **`probe_kind=semantic`**（版本号 + 安装来源，`import` 成功不算过，裁定 31.2）、
   `probed_in=lerobot_act`、`also_probed_in=lerobot_eval`（含 `install_source.kind=index_wheel`/`installer=uv`）。
   **D 认可的关键点**：C **没有把观测改成想要的值**（没让 rlrobot 里报 `importable=true`、也没删行），
   而是**把判据的作用域改对** ⇒ 这才是「三值化」的正确做法；改观测或删行都是造假。
2. **C-F2（P0）通过**：`breakpoint_classifier_selftest.all_match=true`（6/6 边界格），且**规则自测用 synthetic 窗口**
   （`why_synthetic`：「真窗口可能不可得或倒过来 ⇒ 规则自测与数据一致性分开报」），真窗口另列
   `real_window={consistent:true, usable_for_attribution:true}` ⇒ **「规则有牙」与「数据自洽」各证各的、不互相冒充**，
   比 D 要求的更严。断点窗口带 `subject_venv` + `source_kind="archived_manifest_of_that_venv"` +
   `source=[12:14 归档 manifest（sha256_12=9f7f0c94f394）, rebuild2.log 的 mtime]` +
   **`applies_to_described_venv=false`** + `not_the_described_venv_because`（点名 overlay 那份已进回收站、
   与本次 `--venv` 描述的 clean venv 不得混用）⇒ **跨 venv 混算这条根因被堵住**。
   `inherited_packages` 改为按 venv 类型分别解释，并给出 `baseline_same_source_rule`：
   「被描述的 venv 不是基线那个 ⇒ **断言不适用**（**不当失败读，也不当通过读**）」⇒ **这正是 D 要的三值**；
   clean 分支还多加一条真牙：「若实测 `inherited_from_base=true` ⇒ 自足性不成立，红」。
   `snapshot_consistency_selftest` 4/4、双向有牙（只改易变字段 `at` ⇒ 判自洽，修掉 14:52 那个恒红）。
3. **三条断点齐备**：`BP-20260929-venv-rebuild`、`BP-20260929-lerobot-envs-wiped`、
   **`BP-20260929-rlrobot-persistent`（`invalidates=无`，三条理由：28 个项目 pin 逐格相同 / env_check 与 B 的 12/12 全过 /
   初始 obs 与渲染平均像素 108.5 与历史同值）** ⇒ 与 D 的登记一致、**并列不合并**。

## §51 裁定 37.2：**A 线解封**（D 只读实测，不是转述）—— 但「解封」有边界

```
/root/venvs/rlrobot/bin/python scripts/a_env_readiness_gate.py \
  --json-out runs/infra/d_persistent_env_20260929/a_gate_after_c_reprobe_1531.json
→ E1..E7 全 PASS；A_NEW_REPRO_CLAIMS=ALLOWED  blocking_fail=0  warn=0  total_checks=7  rc=0
```
**E6 是真绿不是空转**（D 读了判据体 `scripts/a_env_readiness_gate.py:272-292`）：五个 term 全部**从 manifest 取值**
（`manifest_readable` / `probe_modules_has_lerobot` / `probe_version_matches_pin == PIN["lerobot"]` /
`reproduction_claims_unblocked` 判 `is False` / `env_fully_restored` 判 `is True`）+ 带变异期望 ⇒ 有牙。
**⇒ 本仓当前的全局关键路径（C 重探 → A 解封）到此闭合**；从今天 10:45 检修丢环境算起，环境这条线**首次不再阻塞任何能力主张**。

**边界（写进纪律，防止「解封」被读宽）**：
1. A 现在**可以**声称新的训练/评测复现，但每条主张必须自带 ① 构建指纹（`v1.5 / f19f61341cbe`）② 口径名
   ③ **新 lock 的 sha256**（即 `env_provenance.json`；**它从「P1 接线」升为「第一次真跑就必须有」**）。
2. **解封 ≠ 48 臂旧产物自动跨断点有效**：C 的 `BP-20260929-lerobot-envs-wiped.invalidates` 明写
   「含 48 臂权威表所依据的那批评测，mtime 早于本断点 ⇒ 必须在重建后的环境上重跑才继续有效」
   ⇒ **旧表仍可作历史口径引用（裁定 16.3 / 改判 7），但不得当作「已在当前环境复现」**。

## §52 裁定 37.3：裁定 34.1 的**可红条件未被触发**（C 的运行时实测），但**豁免边界收窄一句**

- **未触发**：C 用**每模块一个子进程 + 回显 `sys.modules` 里 `imageio`/`uv` 前缀键**的方法（**覆盖传递依赖**）实测
  本仓 ACT/48 臂链路的 **8 个脚本全部 `hit=[]`** ⇒ 与 A 的静态 grep 结论一致，且**是更强的证据**（A/C/D 三方一致）。
- **收窄**：**上游 `lerobot.scripts.lerobot_train` 的 import 闭包里确有 imageio（18 个子模块）**。
  C 把它**分开报**（`why_upstream_separate`：不在本仓 48 臂链路上，installer 只用它的 `--help` 当安装闸；
  引 裁定 31.3 / 33.4 的跨对象混算）⇒ **这个「分开报」是关键**：混算会让裁定 34.1 被误判成自动作废，
  不报又会让「用上游入口跑的训练」带着一个未审的版本差异。
  **裁定**：裁定 34.1 的豁免覆盖**本仓链路**；**凡用上游 `lerobot_train` 实跑的训练/评测不在豁免内**
  —— 要么**另证 imageio 不材料**（该次运行没走到它的读写路径），要么**重新报 D**。**引用时必须带这条边界**（按包按链路，不按次）。
  A 的 smoke S2（官方 ACT 训练 50 步）**不需要追溯**（A 自己已明写「smoke 不是能力主张」）；
  **今后真跑**须在产物里回显 imageio 生效版本（落地位置：`env_provenance.json` 的语义值列表，P1）。
- **方法学要求（一般化）**：**「某包不在某链路的 import 面上」这类主张，今后必须给运行时证据**
  （`sys.modules` 或等价的动态追踪），**静态 grep 不足以独立支撑**（它扫不到传递依赖）。
  现成工具：`scripts/c_env_manifest.py --measure-import-surface`（A/B 都可只读调用，产物写自己的目录）。

## §53 裁定 37.4：两处「**旁挂散文与判据不同源**」（都判 P2，都不影响本轮结论）

1. **A 的 E6 `note` 与实测相反**：`scripts/a_env_readiness_gate.py:291` 硬写
   「现值 `importable=false` ⇒ 本条现在**应当红**」，而 15:31 这一跑 E6 = **PASS**
   ⇒ 日志与 JSON 产物里同时出现「PASS」和「本条应当红」，**自相矛盾**。同型还有 `:404` 的自测标签
   「S8 C 的 manifest 仍声明 A 被阻（**当前真实状态**）-> CLOSED(E6)」——**「当前真实状态」已不成立**（它现在是**历史**状态）。
   **判据本身没问题**（五个 term 都读真值、有变异期望）⇒ 判 **P2**：`note` 改为**由观测生成**
   （回显 `probe_modules.lerobot.version` 与 `blocked` 的实际取值），或明写「以下为历史说明」并挂指针；`:404` 去掉那四个字。
   **在改之前：引用 E6 的结论请引 `terms` 的取值，不要引 `note`。**
2. **C 覆写 manifest 未留档 14:54 那一版**：D 的要求 **15:29** 才落盘、C **15:30** 就覆写了 ⇒ **是竞态，不算 C 的错**；
   且**证据没丢**——D 在 14:31 只读跑 C 的脚本时把产物复制进了自己的目录
   （`runs/infra/d_persistent_env_20260929/c_env_manifest.json`：`env_fully_restored=false`、
   `probe_modules.lerobot.importable=false`、`missing=["lerobot"]`）⇒ **「C-F1/C-F2 曾经是真红」仍可核**。
   **纪律从下一次起生效**：覆写自己的 manifest 前 `copy2` 留档 + 新产物带
   `previous_manifest={path, sha256, generated_at}` 与 `changed_fields`。
   **理由（裁定 35.1 同源）**：**「修完就绿」和「判据本来就不会红」在覆写之后长得一模一样**，只有留档能区分。
   （C 的 12:14 `_pre_lerobot_rebuild.json` 归档**做对了**，这次只是漏了 14:54 那一版。）
   **附带一条 D 的自我确认**：D「跑别人的脚本时把产物复制进 `runs/infra/d_*`」这个习惯，
   本轮**意外成了唯一的 before 证据** ⇒ **把它写成 D 线的固定纪律**（不只是防覆写，也是留档）。
3. **同型计数**：「散文与判据不同源」是本仓**第三次**同型（裁定 23 的 `note` 恒空、裁定 35.3 的旁挂 `README_BASELINE.md`、本条）。
   **一般规则**：**判据产物里的每一句散文，要么由观测生成，要么显式标注为历史说明并挂指针**；
   否则产物会自相矛盾，而读者只会记住那句散文。

## §54 台账与回流点（15:3x，依据 = mtime / 产物，不是自述）

| 线 | 本轮变化 | 仍欠 |
|---|---|---|
| **A** | **解封**（`ALLOWED`/`blocking_fail=0`）；§9.4 两项 ✅、sidecar ✅、T17 A 侧 2 项 ✅ | **P0**：D8 补 `historical_meta_is_v121` + 变异 **`S13`**（补前不得引用「D8 立即变红」）；**P1**：迁移断言产物带 `baseline_meta`、sidecar 加 `imageio` 生效版本；**P2**：E6 `note`/`:404` 静态散文 |
| **B** | P0-1 ✅（§45 验收通过）、P0-4 ✅（`installer:52-53`） | **P0-2**（`setup_env.sh` mtime **12:13** 未动，`:101-108` 仍会把门禁 28 pin 覆写成 82 pin）、**P0-3**（persistent lock 三条牙）、**P0-5**（4 条锚点，含 1 条语义变更）、**P0-6 git 代提交**（HEAD 仍 `fe526d8`；16 改 + 11 未跟踪）；P1（v1.6 / `C5=0.04` 预登记双阈值 / 饱和率表 / `golden_values` 加 `--json-out`） |
| **C** | **P0-3 + C-F1 + C-F2 全部 ✅**、三条断点齐、import 面实测触发裁定 37.3 | **P0-4**（`work/decisions/` C 线登记处：把 C-F1/C-F2 修法、三条断点、import 面实测登记进去）；**P1-5/P1-6**；申报 `runs/infra/maniskill_state_probe_20260929/`（15:17，目录无智能体前缀） |
| **D** | 回归监管位；本轮**零**安装/修复动作、**零**写入他人目录 | 等 A 的 D8+`S13` ⇒ 只读跑自测看是否真判红；等 B 的 P0-2/3 ⇒ 核双向牙；A 解封后**第一次真跑**核 `env_provenance.json`（新 lock sha256 逐字相同 + 回显 0928 两份旧 lock） |

**仍未裁的三项维持原状**：`C5=0.04`（B 做**预登记双阈值**重判，**不是已裁**）、饱和率进 warn（等 B 的实测表）、
**C 待办 6（冻结面变更）D 不批准**。
**冻结面本轮仍无一处被破**（D 复核：0928 两份 lock sha/mtime 未动、`arms_summary_v3.json` 11:08、
`lerobot_act_env_20260928/arms_summary.json` 12:33、门禁 `requirements.lock.txt` 12:13、被判 `clip*.json` 09-28）。

---

# 增补十五（2026-09-29 16:5x，D）：裁定 38 —— **路线变更：主线回到 v4（VLA SFT + 在线 RL + Harness），仿真优先；ACT/Lift 线收尾后冻结；新开 A2/B2**

依据：**用户 2026-09-29 裁定**（五项，逐条见 §55）。D 本轮动作边界：**只读探测 + 网络元数据请求 + 监管文档写入**；
**未安装任何包、未下载任何权重、未修改任何冻结面、未代替 B 提交 git**（`work/project_parameters.json` 与三份新单是 D 的写入面）。

## §55 裁定 38.1：用户的五项裁定，以及它们各自推翻了什么

| # | 用户裁定 | D 的执行 | 被推翻/被改判的既有口径 |
|---|---|---|---|
| 1 | 实机平台 = **松灵机械臂**；当前**先在仿真跑通流程**，实机区别后续再对接 | `work/project_parameters.json`：`hardware.robot_model` 记松灵（型号 `null`）、`project.stage="P0（仿真优先）"` | 推翻「暂停扩大…VLA 和真机范围」（`docs/agent_a_handoff_20260924.md:26`）——但**不是**改成"现在就上真机"，而是改成"**仿真上把 VLA 主线跑通**" |
| 2 | **复用当前 VLA 底模**，若不可用则搜官方开源模型，例如 **π₀.₅ 能否本地部署** | D 已实测：**π₀.₅ 可本地部署**（代码面在、权重可得、80GB 够），但**当前 venv 缺 `transformers` 且权重未下载** ⇒ 结论是"可行但尚未就绪"，就绪工作派给 A2 | 推翻「以官方 LeRobot **ACT** on Lift 为能力主线」——`01_开发技术方案.md:5` 明文「**不使用 ACT**」 |
| 3 | 正反向示范**暂由仿真或自建数据集给出**，实机数据后采，**形态参考团队流水线** | 派给 **B2**（§2 任务 2）：仿真采双向示范，目录形态对齐 `ABC130k` + 过 `vla_pipeline` 的 validate→clean→qc | 补上本仓最硬的数据缺口：`lift_B_to_A` 真帧 teacher **0 行**（A 线 16:4x 已把它量化成 0.0028 / 0.966 两个数） |
| 4 | 算力 = **本机 12 核 + A800**，先跑仿真，后续再拓展 | `evaluation.resource_caps` 记死；并行度分母用 **cgroup 配额不用 `nproc`**；GPU 单卡独占 ⇒ **申报制** | 推翻「`nproc=112` 可以开 16–32 路」（`docs/infra-gpu-render.md:87` 已被就地改正） |
| 5 | **可先冻结 ABC**；VLA 测试交给**新开的 A2/B2**；ABC 先跑完当前任务、**做结果文件分析收尾再冻结** | 三份新单：`d_handoff_to_a2_20260929.md`（8 节 + 增补）、`d_handoff_to_b2_20260929.md`（7 节 + 增补）、`d_freeze_abc_20260929.md`（收尾清单 + 三项附带裁定） | 作废「**五条晋级条件全满足才回 PickPlace/视觉/VLA/真机**」这条自设门（`docs/b_agent_review_20260928.md:164`）——它与 `:5`（初始成功率可为 0）和 §12 P1 行（不要求预先高成功率）相反，是 09-24 起绕路的**机制性原因** |

**D 的自我纠错（第十二次，一条）**：D 在 09-24 之后的多份监管文书里**沿用了 A/B 的自设门**（"晋级条件全满足才回 VLA"），
从未把它与 v4 原文对撞。绕路不是某一次错误决定造成的，而是**一条自设门被反复引用、逐渐获得既成地位**造成的。
**一般规则（升为 D 线纪律）**：**任何"前置条件/晋级门"在第一次被引用前，必须与 `RL_Harness_v4_20260924/` 原文对撞一次并留下引用行号**；
对撞不过的门，**不许写进执行单**。本轮 §10.2 的五项预检顺序就是按这条重读的。

## §56 裁定 38.2：P0 的**本机可离线部分，D 已经做完**（实测，非转述）

**π₀.₅ 本地部署可行性 = 可行，但三处未就绪**：
1. **代码面已在**：lerobot **0.4.4** 的 `policies/` 含 `pi0` / **`pi05`** / `pi0_fast` / `groot` / `wall_x` / `xvla`；
   `pi05` = `configuration_pi05.py` + `modeling_pi05.py` + `processor_pi05.py`，`paligemma_variant` 默认 `gemma_2b`，
   主干由 `CONFIG_MAPPING["paligemma"]()` 构建（`modeling_pi05.py:349`、`:383`）。**⇒ 不需要装 openpi。**
2. **阻塞 1：`transformers` 四个 venv 全缺**（lerobot_act / lerobot_eval / rlrobot / maniskill_probe 实测）⇒ 现在 `from_pretrained` 必失败。
3. **阻塞 2：权重未下载，且通道有坑**：`hf-mirror.com` **API 可读**（`lerobot/pi05_base`，7 文件，`lastModified 2026-07-29`），
   但 **blob 返回 429「访问频率限制」**（间隔 20s 重试仍 429）；`huggingface.co` **直连挂起**；
   **`www.modelscope.cn` 可达**且同名仓库文件表可读，**`model.safetensors` = 14467.2 MB** ⇒ **首选 ModelScope**。
   环境调研线独立实测到同一类坑并给出更强的规则：**`snapshot_download` 被 429 时会静默返回半成品并 exit 0**（719/895 文件）⇒
   **必须自己数文件核 size，不能信返回码**；并发是夹逼（8 worker ⇒ 429；单流 ~28 KB/s；2–3 worker + 重试）。
4. **阻塞 3：视觉通道未验**——π₀.₅ 是 VLA，**必须有图像**；而本节点**无 Vulkan、无 docker**，
   ManiSkill **像素档 ❌**、robosuite CPU 软渲染 64² 单相机仅 **8.5 fps**。⇒ **A2 新增 G0.5（视觉通道预检）为阻塞门**，
   并预设三种结论对应三条路径（甲继续 / 乙离线图像回放或申请节点 / 丙报用户，**不许自行退化成状态输入小模型**）。
5. **算力/存储**：A800-SXM4-80GB（实测 85.1 GB）空闲；**CPU 配额 12 核**（`cpu.max=1200000/100000`，已有限流记录）；
   NFS 可用 **67T**（已用 94%）；overlay 5.6T；`/root` 与 `/opt/conda` 为**临时层** ⇒ 权重与 venv 一律落 `.codex-persist/`。
6. **外部事实（标 `external_unverified`，不得与上面并列）**：π₀.₅ 已在 openpi 与 LeRobot 开源；`lerobot/pi05_base` 标 **`license:gemma`**；
   社区微调显存报告**互相矛盾**（48GB 不够 vs ≈40GB 可用（v0.4.0）vs 后续版本内存回归）⇒ 80GB 预期够，**但必须本机实测并记 lerobot 版本**。

**仿真首场景的候选顺序（D 裁定，理由见 A2 §8.3）**：
① **`SO100GraspCube-v1`**（判据成品：`success = cube_lifted & is_grasped & reached_rest_qpos`，另有 `reached_object`/`touching_table`；
`max_episode_steps=64`；@1024 **43,082 steps/s**；SO-100 与 LeRobot 同生态）；
② **`PickCube-v1`**（自带 goal 位 ⇒ **天然目标条件**，正反两向 = 交换 goal；但 `success` **不含** `is_grasped`，用它必须自补 grasp 真值列）；
③ **`gym-aloha/AlohaTransferCube-v0`**（与 v4 `:5` 首场景形态最贴，但需装、需像素 ⇒ **降为备选**，装完先过 G0.5）。

## §57 裁定 38.3：A2 / B2 开线，分工**互斥**，验收入口统一

| 线 | 定位 | 首要交付 | 明确不做 |
|---|---|---|---|
| **A2** | VLA 底模与仿真贯通（能力线） | G0 持久 venv + manifest → G0.5 视觉通道预检 → G1 权重落地（7/7 文件 + sha256 + receipt 含 license）→ **G2 动作与时间契约六问 + 与团队数据形态的映射表** → G3 20 局 zero-shot | 不采示范数据、不训 BC、不碰冻结面、不改 `work/project_parameters.json`（单写者 = D） |
| **B2** | 数据与判据（证据线） | 任务1 A2 新环境的 **provenance 准入闸**（复用 B 的 G1–G5 + V0–V9，另加三条 π₀.₅ 专属牙）→ 任务2 **双向示范**（形态对齐 `ABC130k` + 过 `vla_pipeline` QC）→ 任务3 **π₀.₅ 版 T17** → 任务4 **三口径评测器** | 不装环境、不下权重、不占 GPU 训练、不改团队 `vla_pipeline` 代码 |

**关键顺序**：**G2（契约）优先于 G3（跑局）**；**B2 的数据 schema 必须等 A2 的 G2 契约表落盘后定稿**（动作维度/单位/频率对不上，数据就是废的）。
**新命名空间**：D 批准新开 `runs/vla/`（`runs/vla/a2_*`、`runs/vla/b2_*`），**目录必须带线前缀**——
今天已经出现过一次"探针目录无智能体前缀"被 D 点名的事（裁定 38.7 处理），不重复。
**验收入口统一**：`appendices/01_接口契约与开发验收.md` 的 **T01–T54**（T17 见 `:337`/`:352`）；
**能力主张只在目标 VLA（仿真/实机）上成立**；发布口径 = **同一 checkpoint 双向通过后整体发布**（`01_开发技术方案.md:27`）；
**H1 对照 = 同预算动态 Harness-DAgger/BC vs BC+RL**（`:376`），**不是** RL vs 冻结 SFT；
首个迭代口径不变 = **抓空 → 同协议纠正 → 数据＋BC → 一次 RL 更新 → 双向无动作辅助评估**（`:355`）。
**GPU 申报制**：单卡独占，任何 > 10 分钟的 GPU 占用**起跑前**在 `daily_report.md` 申报（预计时长 / 显存 / 可否中断），跑完销账。

## §58 裁定 38.4：ABC 三线**收尾后冻结**（全文见 `d_freeze_abc_20260929.md`）

- **冻结的准确含义**：不再新开任务 + 产物转为回归基线 + **可复活但须 D 登记与用户确认**（不许自行复活）。
- **A**：**(乙) 48 臂跨断点重跑取消**（它只服务被 `:5` 排除的 ACT 线，跑完反而增加误读成本）；(甲) 已完成 ⇒ 只做产物清单 + 未销账项按"冻结时状态"登记 + 移交 A2。
- **B**：**最后一次代提交**（含 D 本轮三份新单与 `work/project_parameters.json`）+ **git 单写者职责移交 B2** + 9 起同型缺陷的一般规则一并移交。
- **C**：P0-4 自查确认 + 两个探针目录补申报 + **「A2/B2 复用清单」**（C 收尾里最有价值的一件；其中**"视觉表征缺失"在 π₀.₅ 路线下从 P2 升为 P0**）+ `registry/` 维护权移交 B2。
- **附带三项裁定**：**38.5** `C5=0.04` 改为**按物体几何缩放 + 显式余量**（固定阈降为对照列，可红条件：几何不可得时必须回退并标 `c5_mode=fixed`，静默混用判红）；
  **38.6** **不开** MS-HAB（官方仓 404 / 只有匿名双盲镜像 / 要换整套运行时 + py3.9 + git-lfs + coacd / 示范集 500 GB / 不服务当前主线），**停** ReplicaCAD 资产下载；
  **38.7** 两个无前缀探针目录：**基础设施事实准予引用、能力结论不采信、目录名不改、README §0 补作者/写入面/边界、该线冻结、两个下载工具移交 A2**。

## §59 台账（16:5x，依据 = mtime / sha256 / rc / 产物，不是自述）

| 线 | 状态 | 下一步（唯一） |
|---|---|---|
| **A** | 已闭合本轮全部派工；**冻结中**（收尾清单 5 条） | 产物清单 + 未销账项登记 + 移交 A2；**不跑 (乙)** |
| **B** | P0-1…P0-6 **全部落地**；HEAD `fe526d8` → **`e6c661e`**（11 提交）；**冻结中** | 最后一次代提交（含 D 三份新单 + 参数表）+ 移交 B2 |
| **C** | P0-3/C-F1/C-F2 ✅、`registry/` selfcheck 8 案全过；**仍是活进程**（`e6c661e` 提交语） | P0-4 自查确认 + 补申报 + **「A2/B2 复用清单」** |
| **环境调研线** | 任务矩阵 11/12、`SO100GraspCube-v1` 判据发现、三条下载坑 + 两工具；**裁定 38.7 后冻结** | README §0 补三行；工具移交 A2 |
| **A2** | **新开**，执行单已落盘（8 节 + §8 增补） | **G0 持久 venv**（`.codex-persist/envs/pi05_sim`，`--link /root/venvs/pi05_sim`）→ 交 B2 过闸 |
| **B2** | **新开**，执行单已落盘（7 节 + §7 增补） | **任务 1 准入闸**（卡 A2，今天先做） |
| **D** | 回归监管位；本轮零安装、零下载、零冻结面改动 | 等 A2 的 G0/G0.5/G1 与 B2 的任务 1 ⇒ 只读复核；等 B 的最后一次代提交 ⇒ 核 `git log` |

**仍未裁的项（冻结后不再推进，登记为冻结时状态）**：饱和率进 warn（等实测表）、**C 待办 6（冻结面变更）不批准**、
A 的 P0（D8 + `S13`）/P1/P2、B 的 P0-3/P0-5/P1 三项、C 的 P1-5/P1-6。
**`C5=0.04` 与 MS-HAB 两项由本轮裁定 38.5 / 38.6 结案。**
**冻结面本轮仍无一处被破**（D 复核：0928 两份 lock、`arms_summary_v3.json` 11:08、`lerobot_act_env_20260928/arms_summary.json` 12:33、
门禁 `requirements.lock.txt`、被判 `clip*.json` 09-28；A 的终验五项在 16:35–16:38 全部复跑，与 D 只读结论一致）。

---

# 增补十六（2026-09-29 17:0x，D）：裁定 39 —— **A2/B2 起跑前的依赖红线与并发边界（预登记）**

触发：用户已开两个新会话（A2/B2）。D 回监管位，先取**只读基线**，再在它们落第一份产物之前把**尚未预登记的边界**补上。
D 本轮动作边界：**零安装、零下载、零冻结面改动、未代替 B 提交 git**；依赖面事实全部来自**只读**读
`importlib.metadata.requires('lerobot')`（在已验收的 `lerobot_act` venv 内执行）。

## §60 裁定 39.1：依赖红线（**这是本轮最有价值的一条，它拦住的是一个会烧半天的假绿**）

实测（lerobot **0.4.4**，核心依赖 23 条）：
1. **`transformers` 不是核心依赖，而在 extra `transformers-dep` 下：`transformers<5.0.0,>=4.57.1`。**
   ⇒ `pip install "lerobot==0.4.4"` 装完 **π₀.₅ 依然加载不了**；正确的是 `lerobot[transformers-dep]==0.4.4`
   （或 `--no-deps` 装 lerobot 后单独钉 transformers）。这也解释了为什么两套已验收 venv 都没有它（`--no-deps` 按 lock 装）。
2. **extras 全集里没有 `pi`/`pi0`/`pi05` 这一项**（有 aloha、async、groot、hilserl、libero、metaworld、peft、pusht、
   smolvla、transformers-dep、wallx、xvla、kinematics 等）⇒ **不要去找"π₀.₅ 专用 extra"**；微调路径另需 `peft<1.0.0,>=0.18.0`。
3. **核心依赖与 torch 强耦合**：`torch<2.11.0,>=2.2.1`、`torchvision<0.26.0,>=0.21.0`、`accelerate<2.0.0,>=1.10.0`、
   `torchcodec<0.11.0,>=0.2.1`。已验收两套 venv 实测均为 **`torch 2.6.0+cu124`**。
   ⇒ **上界允许 pip 把 torch 升到 2.7+ 并换 cu126/cu128 轮子，`torchcodec` 跟着走 ⇒ 一次"顺手装依赖"就能造出新断点。**

**红线（三条）**：
- **新 venv 的 `torch.__version__` 必须逐字等于 `2.6.0+cu124`**；不等于 = **断点变更**，须 D 登记 + 重过 B2 的闸，不是"顺手升级"。
  理由：A 线今天刚为一次环境迁移做完 **V0–V9 = 10/10** 的不变性证明，跨 torch 版本会让那批基线与
  `t17_train_side_verify_v2.json` 失去可比性（裁定 31.3 / 33.4 / 36.4 的同源纪律：**跨口径不得并列**）。
- **不许复用 `.codex-persist/envs/maniskill_probe` 跑 π₀.₅**：其实测 `transformers 4.30.0` **低于 4.57.1 硬下界** ⇒
  会出现"**import 成功但加载权重报错**"这种最难查的形态。它只用于 state 档判据/吞吐对照。
- **不许改动已验收的 `lerobot_act` / `lerobot_eval`**（ACT 线回归基线的载体，已冻结）；新环境一律另建 + `--link`。
**执行方式**：A2 **实装前先落 `resolve_dryrun.txt`**；清单里出现 `torch`/`torchvision`/`torchcodec` 的 install 或 upgrade ⇒ **停下报 D**。
B2 的闸新增 **V-pi05-4「解析器不得动 torch 栈」**，且**必须双向有牙**（造 `2.6.0+cu124→2.9.0+cu128` 的清单必须红；
只新增 `transformers 4.57.1` 的清单必须绿），否则这条牙恒真或恒假（裁定 27.1）。

## §61 裁定 39.2：并发边界（**当前有四条会话在写同一个仓**：B 收尾 + C 活进程 + A2 + B2）

1. **权重下载单线负责 = A2**；**B2 不得并行下载**。依据是今天两条独立实测：hf-mirror **8 worker ⇒ 429**、
   **单流 curl ~28 KB/s**（同域名 range 请求同时刻 2.5 MB/s ⇒ 是单连接被限速），且
   **`snapshot_download` 被 429 时静默返回半成品并 exit 0**（实测 719/895 文件）。两会话并行打代理 ⇒ 两边都下不完。
2. **GPU 独占 + 申报制**：A2/B2 **不得同时**起 GPU 任务；> 10 分钟的占用**起跑前**在 `daily_report.md` 申报
   （时长/显存/可否中断），跑完销账。B2 的秒级前向核对同样要申报。
3. **写入面按线前缀分家**：A2 → `docs/a2_*.md` + `runs/vla/a2_*`；B2 → `docs/b2_*.md` + `runs/vla/b2_*`。
   追加共享文件（`daily_report.md`、`work/decisions/*`）前先 `git status` + `tail`，追加后立刻报代提交人。
   依据：今天已出现两次"C 仍是活进程"的交叉提交（`0032ff5`、`e6c661e`），**并发追加是本仓已发生过的风险，不是假想**。
4. **git 单写者**：B 完成**最后一次代提交**（含 D 本轮四份文书 + `work/project_parameters.json`）后，职责**移交 B2**；
   **移交前 B2 不提交**，只把待提交清单报 D。
5. **`work/project_parameters.json` 单写者 = D**：A2/B2 交"建议值 + 证据路径"，D 落笔（与 `registry/` 的内容寻址口径一致）。

## §62 基线快照（17:08，D 只读；后续按 mtime/sha256 核，不采信自述）

| 项 | 基线值 |
|---|---|
| git HEAD | **`e6c661e`**（"C 线增量快照（16:44 时间点，C 仍是活进程；B 代提交）"） |
| D 的四份文书 | **仍未入库**：`d_handoff_to_a2_20260929.md`、`d_handoff_to_b2_20260929.md`、`d_freeze_abc_20260929.md` 为 `??`；`supervisor_memo_20260929.md` 为 `M` ⇒ **等 B 的最后一次代提交** |
| `runs/vla/` | **尚不存在**（A2/B2 都还没落产物） |
| `.codex-persist/envs/pi05_sim` | **尚未建** |
| `.codex-persist/hf-cache` | **尚未建**（权重未开始下载） |
| 已验收 venv | `lerobot_act` / `lerobot_eval` 均 `torch 2.6.0+cu124`（未动） |

**D 的下一批复核（全部只读）**：① A2 的 `resolve_dryrun.txt` 是否在实装**之前**落盘、torch 栈有没有被动；
② `env_manifest.json` 是否 `probe_kind=semantic`（`import` 成功不算过）；③ `weights_receipt.json` 是否 **7/7 文件 + sha256 + license**；
④ B2 的 `admission_verdict.json` 四条 π₀.₅ 牙是否**双向有牙**；⑤ B 的最后一次代提交 ⇒ 核 `git log` 与 `b_git_size_guard.py`；
⑥ C 的「A2/B2 复用清单」是否点明**视觉表征缺失已从 P2 升为 P0**。

---

# 增补十七（2026-09-29 17:1x，D）：裁定 40 —— **观察模型端点实测（iflytek 不可用 / qwen3.8-max 可用且支持视觉）+ 实机型号落参（松灵 Piper）+ 仿真形态代理口径**

触发：用户裁定「复核均同意；观察模型直接复用 `REMOTE_ENDPOINTS.md`（iflytek，url 可能需改前后缀，效果与 GPT-6 无本质区别）；松灵型号为 **Piper**」。
D 本轮动作边界：**只读 + 端点探针（7 次 HTTP 请求 + 4 次定位复测）+ 监管文书与参数表写入**；
**未安装任何包、未下载权重、未改冻结面、未代替 B 提交 git**；参数表覆写前已按裁定 35.1 同源纪律留 before 影像（`project_parameters.rev1.json`，sha256 前 12 = `643590f2538c`）。

## §63 裁定 40.1：观察模型 = **dashscope / `qwen3.8-max`**（本轮），iflytek **实测不可用且不是前后缀问题**

D **亲自跑**探针（`runs/vla/d_observer_endpoint_20260929/probe_observer_endpoint.py`，密钥从 `REMOTE_ENDPOINTS.md` 只读解析、产物掩码）：

| 端点 | 实测 | 结论 |
|---|---|---|
| **dashscope / `qwen3.8-max`** | 文本 **HTTP 200 / 1.2 s**，返回 `choices[0].message.content`（另带 `reasoning_content`）；**视觉通过**——64×64 纯红 PNG 以 data URL 传入，**正确回答红色** | **可立即承担 Harness 观察模型角色**（v4 §6.1 主观察与评分的必要条件 = 能吃图像，已实测满足） |
| **iflytek / `gpt-5.6-sol`** | 默认客户端 UA（python-urllib / curl）⇒ **7 个 URL 变体全部 HTTP 403**，返回 **38,869 B 的 HTML 拦截页**：「很抱歉，您提交的信息可能对站点造成威胁，此次访问被阻断，相关行为已记录 … **Powerd By iflytek Security**」；浏览器 UA ⇒ **HTTP 302** → `Location: https://iflygw.iflytek.com/changeUrl.html?goto=<原URL>`（Tengine/nginx，该页为 JS 页、正文无明文新地址）；`--noproxy` 直连 ⇒ 无响应（本节点无直连出口）；同 UA 下 dashscope 仍 **200**（排除"UA 被全局拦"这一解释） | **不可用**。且**不是"改前后缀"能解决的**：403 是 **iflytek 自家 WAF**（不是本节点代理，也不是 4xx 的 API 错误），302 指向 `changeUrl.html` 暗示**地址已迁移**。需要**正确的 API base host**，或由 iflytek 侧对本节点出口 IP / 客户端放行 |

**裁定**：① 本轮观察模型 = **`qwen3.8-max`**；② `work/project_parameters.json` 的 `harness.intended_primary_observer` **仍写 GPT-6**（v4 设计假设保留），
`actual_provider_model_id` 写实测值 —— **两者不许混写**；③ **A2/B2 都不许再打 iflytek**（WAF 已"记录相关行为"，反复重试只会让放行更难），
等用户给出正确 base_url 后**由 B2 用同一个探针补测**、结果**追加为新产物不覆写**；④ 用户"与 GPT-6 无本质区别"记为 **user_decision**，
但 v4 `01_开发技术方案.md:7` 明写「**Harness 的输出也需验证**」、§6.1 要求留出录像校准（P2）⇒ **换 provider 不降低校准要求**。
**执行**：观察模型校准**新增为 B2 的任务 5**（`d_handoff_to_b2_20260929.md` §9.1），且**必须把两条指标分开**：
**判定一致率**（与环境真值同不同）与**纠正可用率**（纠正动作是否落在允许编辑范围内、是否可执行）——
**"模型说得对"不等于"纠正能用"**（§6.2 要求纠正是标签/同协议动作/应急接管之一），**不许合并成一个分数**。

## §64 裁定 40.2：实机型号 = **松灵 Agilex Piper**，已落参；**四项契约仍为 null，不许猜**

- `hardware.robot_model` / `active_arm` 已落 Piper 与"单臂"。**与 v4 首场景相容性（好消息）**：
  `01_开发技术方案.md:5` 的首场景是「松灵 ALOHA 类**双臂**平台上的**单臂抓放**，**另一臂暂不参与**」⇒
  **单臂 Piper 即可承载首场景**，不需要双臂协调；正反两向由**目标条件**（T17）区分，不由臂数区分。
- **动作维度已可锚定 6+1**：D 实测 `ABC130k` 的团队数据形态为每臂 `joint(6)` + `pose(7)` + `velocity`、`gripper joint(1)` ⇒ 与 Piper 相容。
- **仍为 `null` 的四项**：**单位 / 参考系 / 夹爪语义 / 控制频率**。**不许猜**（`02_开发实施指南.md:7`）：
  要么取 Piper 的 SDK/URDF 文档，要么等实机实测；取不到就留 `null` 并在映射表标 `unknown`。
- **D 向用户新增一问（阻塞 P0 收口）**：**`ABC130k` 那批数据是否由 Piper 采集？**
  若是 ⇒ 契约可直接从该批数据反推，P0 成本大幅下降；若否 ⇒ 它只是"形态相容的参照"。
  **在得到答复前，A2 的映射表那一列标 `pending_user`**（已写进 A2 §10.1）。

## §65 裁定 40.3：仿真形态口径 —— **本机没有 Piper 数字孪生，SO-100 只是形态代理**

D 实测：`mani_skill/envs/tasks/digital_twins/` **只有 `so100_arm` 与 `bridge_dataset_eval`**；
`find -iname '*piper*' -o -iname '*agilex*'` 在 `mani_skill` 包内 **0 命中**。
**裁定（三条口径，A2/B2 报告里都要照抄）**：
1. 用 `SO100GraspCube-v1` / `PickCube-v1` 跑通流程**允许**（正是用户"先在仿真跑通流程"的原意），
   但产物**必须带 `morphology_proxy: "so100"`** 字段，**不得**把任何成功率/延迟/契约结论写成"Piper 上成立"。
2. **Piper 的 URDF/MuJoCo 导入 = 实机对接前的必做项**，由 D 在 P1 结束前排期；**本轮不要求做**。
   A2/B2 若顺手发现可用的 Piper 模型来源，**只报路径与许可证，不下载不导入**（12 核 + 无 Vulkan，导入验证是另一件事）。
3. **任务面顺序不变**：`SO100GraspCube-v1`（判据成品）→ `PickCube-v1`（自带 goal 位，正反 = 交换 goal）→ `gym-aloha`（形态最贴 v4 首场景，但需装 + 需像素，备选）。
**这条裁定的实质**：把"仿真跑通"与"实机可用"之间的**形态差**显式记在产物里，而不是等实机对接时才发现结论搬不过去
（与裁定 31.3 / 33.4 / 36.4 同源：**跨口径不得并列**）。

## §66 台账（17:1x）与 D 的下一批复核

| 线 | 状态 | 下一步 |
|---|---|---|
| **A2** | 已开跑（会话已由用户开启）；`runs/vla/` 尚无其产物、`pi05_sim` venv 与 `hf-cache` 均未建 | G0 的 `resolve_dryrun.txt` **先于实装**落盘 → G0.5 三通道出图实测 → G1 权重 receipt（7/7 + sha256 + license） |
| **B2** | 已开跑 | 任务 1 准入闸（四条 π₀.₅ 牙，含 **V-pi05-4 双向牙**）→ **新增任务 5 观察模型校准** |
| **A/B/C** | 冻结中（收尾清单见 `d_freeze_abc_20260929.md`）；C 仍是活进程（`c_selfcheck_decisions_registry.py`、`docs/c_env_manifest_and_pending_impl_20260929.md` 17:0x 又改动） | B 的**最后一次代提交**（含 D 本轮全部文书 + 参数表 + `runs/vla/d_observer_endpoint_20260929/`）；C 的「A2/B2 复用清单」 |
| **D** | 回监管位；本轮零安装、零下载、零冻结面改动 | 等 A2/B2 首批产物 ⇒ 只读按 mtime/sha256/rc 核；**并向用户追问 `ABC130k` 是否 Piper 采集** |

**本轮 D 的写入面（全部为追加或 D 单写者文件）**：`work/project_parameters.json`（rev2，before 影像已留档）、
`d_handoff_to_a2_20260929.md` §10、`d_handoff_to_b2_20260929.md` §9、本文件增补十七、`work/decisions/decisions_20260929.md` DR-D39、
`daily_report.md` 17:1x 节、以及新目录 `runs/vla/d_observer_endpoint_20260929/`（探针脚本 + JSON 产物 + rev1 影像）。

---

# 增补十八（2026-09-29 17:3x，D）：裁定 41 —— **真机平台 = 松灵 Cobot Magic（双臂 ALOHA 类）⇒ 形态口径改判；iflytek 关闭；ABC130k 身份确证 = YAM（不是 Piper），但它天然带正反任务对**

触发：用户补充三条（**被控臂 = Piper，整体平台 = 松灵分体式 ALOHA 具身遥操平台 Cobot Magic，多臂**；
**iflytek 被公司拦截 ⇒ 关掉**；**数据采样来源用户不确定，交 D 对照判断**）。
D 本轮动作边界：**只读探测（团队数据区 + 数据集文档）+ 监管文书与参数表写入**；
**未安装、未下载、未拷贝任何数据、未改冻结面、未代替 B 提交 git**；参数表 rev3 覆写前留 before 影像（`project_parameters.rev2.json`，sha256 前 12 = `8924fbe431c3`）。

## §67 裁定 41.1：**D 的自我纠错（第十三次）—— 裁定 40.3 的形态判断基于错误前提，现予改判**

裁定 40.3 是在"实机 = **单臂** Piper"的前提下判的（SO-100 为形态代理、gym-aloha 为备选）。
用户补充后前提变了：实机是**双臂 ALOHA 类平台**（Cobot Magic，leader–follower 遥操，2 条 follower Piper 臂）
⇒ **动作空间是 14 维（2×(6 关节 + 1 夹爪)），不是 6+1**。
**改判**：`gym-aloha/AlohaTransferCube-v0` 从"备选"**升为形态一致的首选**（14 维双臂 + top/2 wrist 三相机，与 Cobot Magic 及 ABC-130k 同构，
任务本身就是"把方块在两区之间转移"，与 v4 `:5` 首场景同型），**条件 = A2 的 G0.5 视觉通道可用**；
`SO100GraspCube-v1` / `PickCube-v1` **降为 state 档的判据与流程贯通对照**（形态是 5+1 单臂），产物必须标 `morphology_proxy="so100_single_arm"`。
**同时好消息两条**：① v4 `:5` 首场景「松灵 ALOHA 类双臂平台上的单臂抓放，另一臂暂不参与」**与实机平台精确对应**，方案不需要改；
② Cobot Magic 是遥操平台 ⇒ v4 `:5` 假设的「已有遥操作与少量示范采集能力」**成立**，实机示范采集是正规数据源。
**纪律同源**：这正是 D 反复引用的「**跨口径不得并列**」（裁定 31.3/33.4/36.4）**用在 D 自己身上**——前提变了必须改判并留痕，不许悄悄沿用旧裁定。
**连带效应**：**G0.5（视觉通道预检）的地位上升**——它不再只是"能不能出图"，而是**决定本项目在仿真上能否做形态一致的验证**；
丙案（完全出不了图）**只能由用户裁**（换节点 / 或先用 state 档跑通流程与数据闭环、把形态验证整体后置）。

## §68 裁定 41.2：**ABC130k 身份确证 = `xdof/ABC-130k`（YAM 双臂站），不是 Piper** —— 但仍可用作离线形态代理

用户交办"数据采样我这边不确定，你可以对照判断下"。**D 的判断（有原文证据，不是推断）**：
- `yfw_input/0730/XDOF_ABC-130k/README.md` 的 Dataset Statistics 表明写：**Robot = "Bimanual station, 2x 6-DoF YAM arms, parallel-jaw grippers"**；
  `docs/YAM_DATA_FORMAT.md:7` 同证（"two 6-DoF YAM arms with parallel-jaw grippers and wrist-mounted cameras, plus a fixed top camera"）；
  来源 = HuggingFace **`xdof/ABC-130k`**、代码 `github.com/amazon-far/abc`、**`license: apache-2.0`**。
- **原始数据在本机**：`yfw_input/0730/XDOF_ABC-130k/data/{train,val}/`（train **129,032** episodes / **3,541.1 h** / 197 任务，annotated 42,980 = 33.3%）。
- **D 的实测交叉验证（四条，全部与 README 吻合）**：动作总维度 **14**；内参是**单个 3×3 矩阵**（fx 431.88 / fy 431.38 / cx 324.26 / cy 240.97）⇒ **640×480 = RealSense 站**；
  **帧率 30 Hz**（4749 帧 ÷ 159.58 s = **29.76 fps**，团队 QC 规则 J/V04 的合格区间 [29.0,31.0] 印证）；夹爪实测 **[0, 0.998] 归一化**。
- **一处 D 的更正**：`intrinsics` **不是"三组相机内参"，而是一个 3×3 矩阵**（D 17:0x 误读，现更正）⇒ 团队 QC 规则 `A` 报的
  "字段缺失: intrinsic"（**847/847**）很可能是**字段名/结构不匹配**，不是数据真没内参；**由 B2 定位并只报观测**（不改团队管线代码）。

**裁定（使用边界，三条）**：
1. **可用作 P1「同一 θ 双目标 BC」的离线形态代理**（YAM 与 Cobot Magic **动作空间同构**：14 维、平行夹爪、top+2 wrist、640×480、30 Hz），产物必须标 **`morphology_proxy="yam"`**；
2. **不得当作 Piper 的动作契约来源**——关节零位/限位/连杆长度/夹爪行程都不同；A2 的契约表第三列（Piper）取不到就留 `null`，**第二列数值不得搬进第三列**；
3. **两处缺陷用前必须处理**：① 转换后的 `workplace/ABC130k` episode **缺 `top-camera.mp4`**（D 抽查 4/4），而原始 mcap **含固定 top 相机** ⇒ **是转换缺口不是源缺口，可重转补回**；
   ② QC 对 val **847/847 全报 badcase**（A intrinsic 847、N/O/V09/V10 subtask 空 847、J/V04 fps 27、C03 帧跳变 11、I 异常静止 1）。
   **体积纪律**：该集 README 标 `n>1T` ⇒ **只许按任务对取子集，不许整集拷贝/转换**（NFS 已用 94%）。

## §69 裁定 41.3：**本仓最硬的缺口（反向示范 0 行）现在有现成解 —— ABC-130k 天然带正反任务对**

D 实测 `meta/train_report.txt`（197 任务）后发现**同一 station、同一 14 维动作空间下的天然正反对**：
`put_the_credit_cards_into_the_card_holder` **2574** ↔ `take_the_credit_cards_out_of_the_card_holder` **2732**；
`put_the_keys_on_the_keyring` **2805** ↔ `remove_the_keys_from_the_keyring` **745**；
`put_the_photo_into_the_frame` **898** ↔ `take_the_photo_out_of_the_frame` **257**；
`put_the_phone_into_the_phone_case` **584** ↔ `take_the_phone_out_of_the_phone_case` **734**；
`put_the_pillow_into_the_pillowcase` **538** ↔ `remove_the_pillowcase_from_the_pillow` **664**。
（单向搬运/分拣大盘：`put_the_plastic_bottles_in_the_bin` 3793、`sort_the_legos_into_containers_by_color` 4458、`sort_the_stationery_into_containers` 2079、`place_and_organize_*_onto_the_shelf` 70~434 各。）

**意义**：v4 `:7`「同一个目标条件模型学习正、反两个任务」与 T17（`appendices/01_接口契约与开发验收.md:337`）
**第一次有了真实数据支撑**；A 线量化的那个缺口（`lift_B_to_A` teacher **0 行** ⇒ 输出空间 0.0028 / 权重空间 0.966）**可以立刻补上**。
**裁定**：B2 的任务 2 优先级改为 **(a) ABC-130k 离线正反对（第一优先）→ (b) 仿真双向 teacher → (c) 实机 Cobot Magic 遥操作采集（正规源，窗口由用户定）**。
**口径**：(a) 只支撑「同一 θ 对目标有条件依赖」与 BC 冷启动，**不得声称"Piper 上的双向能力"**；引用必须同时给 `morphology_proxy="yam"` 与所用任务对的条数。

## §70 裁定 41.4：**iflytek 关闭**（用户裁定：被公司拦截）

- **观察模型固定 = dashscope / `qwen3.8-max`**（D 17:1x 实测：文本 200/1.2 s、视觉通过）。
- **B2 任务 5 里的 iflytek 补测项删除**；**A2/B2 均不得再打该端点**（WAF 明写"相关行为已记录"）。
- **复活条件写死在参数表里**（防止变成永久沉默）：用户给出未被拦截的端点/base host ⇒ 用 D 的同一探针补测，**追加为新产物不覆写**。
- `intended_primary_observer` **仍是 GPT-6**（v4 设计假设保留）、`actual_provider_model_id` 是实测值，**两者不许混写**；
  用户"与 GPT-6 无本质区别"记为 **user_decision**，但 `01_开发技术方案.md:7`「**Harness 的输出也需验证**」⇒ **换 provider 不降低校准要求**。

## §71 新增任务与台账（17:3x）

- **B2 新增任务 6 = 实机 Cobot Magic 遥操作采集协议草案**（9 项：动作空间/频率/相机/正反对与条数/初始分布/成功判据/数据格式(mcap vs lerobot)/干预记录/**另一臂状态**）。
  **理由**：遥操作能力已具备、用户已说"实机数据后续会采集"⇒ **窗口一开而协议没定，就会采回不能用的数据**。草案交 D 裁后再给用户；**不许假设实机可用时间、不许承诺成功率或采集时长**（`:355`）。
- **A2**：G2 契约表改为**三列**（`π₀.₅ 原生` ↔ `ABC-130k(YAM) 实测` ↔ `Piper/Cobot Magic 待实测`）；G0.5 按 §67 的甲/乙/丙三案报结论，**丙案不许自选**。
- **参数表 rev3 已落**：`hardware`（平台/被控臂/首场景只用一条 follower 臂/`inactive_arm_state` 待实测/`expected_camera_layout` 参照）、
  `action_contract`（14 维 + YAM 实测数值 + commanded/observed 不可混用 + 单位/参考系仍 null）、`timing.control_hz`（采集 30 Hz 实测；控制频率 null）、
  `task.sim_first_scenario_candidate`（改判）、`harness`（iflytek 关闭 + 复活条件）、`demonstrations`（YAM 身份 + 正反对 + 两处缺陷）；
  `measurements_and_decisions` **22 → 29 条**。
- **D 的下一批复核（只读）**：① A2 的 `resolve_dryrun.txt`（先于实装）与 G0.5 三通道出图实测；② B2 的准入闸四条 π₀.₅ 牙（含 V-pi05-4 双向）；
  ③ B2 的正反对子集**取了多少条/多少 GB**（体积纪律）与 `morphology_proxy` 标注；④ B2 的任务 6 草案 9 项是否齐；⑤ B 的最后一次代提交。
- **仍需用户回答/提供的三项**：① **实机采集窗口与人力**（决定 (c) 何时能启动）；② **Piper 的 SDK/URDF 或实机实测机会**（决定契约第三列能否从 `null` 变实测）；
  ③ **`gym-aloha` 若因像素档不可用而走丙案时，是换节点还是把形态验证后置**（这条等 A2 的 G0.5 结论再问，现在不催）。

---

# 增补十九（19:2x–19:5x，D）：渲染口径落地 + Piper 契约实测 + A2/B2 交付只读复核

**触发**：用户指令「先把仿真 RL-Harness 跑通再换实机验证；**可以先下载 Piper 资源文件，保持 SDK/URDF 可导入**；**尽量在渲染下跑验证**；换节点不行再跑最小数据流程闭环；后续再考虑更换其它有效节点」＋追加指令「**先只渲染单臂，不要弄双臂渲染**」。
**D 的动作边界**：只读探测 + 治理写入 + 用户授权的下载。**未 git 提交（B 单写者）**、未改 `harness/`、`registry/`、`configs/`、任何 lock、未动 A/B/C 冻结面、未打 iflytek 端点。
**产物目录**：`runs/vla/d_render_probe_20260929/`（脚本 6 个 + JSON 证据 11 个，含 1 份崩溃留档）。

## §72 裁定 42：**渲染口径 = 单臂 + osmesa；像素档验证判定为「可行」，不退 state 档、不换节点**

**42.1 后端口径**：`MUJOCO_GL=osmesa`。实测（MuJoCo 3.9.0 / `lerobot_eval` venv）：osmesa 稳定；egl 能跑但更慢，且退出时抛 `OpenGL.raw.EGL._errors.EGLError`（teardown 崩）。
**根因已定位**：A800 与 CUDA 可用（A2 实测 π₀.₅ 加载 allocated 13,812.5 MiB），但 **NVIDIA EGL userspace 全缺** —— `libEGL_nvidia*`、`libGLX_nvidia*`、`libnvidia-eglcore*`、`libnvidia-glcore*` 在 `/usr/lib/x86_64-linux-gnu` 均不存在，`ldconfig -p` 只有 `libOSMesa.so.8`/`libEGL_mesa.so.0`/`libEGL.so.1`，`/usr/share/glvnd/egl_vendor.d/` 只有 `50_mesa.json`。⇒ **egl 实际落到 mesa 软 EGL，不是 GPU 路径**。
**更正 rev3 的错口径**：参数表 rev3 写「无 Vulkan（**像素档渲染不可用**）」⇒ **本次实测推翻**。正确表述：无 Vulkan 且无 NVIDIA EGL ⇒ 不能用 GPU 加速渲染，但 **CPU 软渲染可用**，像素档验证成立。
**若要 GPU 渲染**（未安装、未验证，标注 `external_unverified`）：需与驱动 **590.48.01 同版本**的上述四个库 + `10_nvidia.json`；可用 `__EGL_VENDOR_LIBRARY_FILENAMES` 指向自建 json，**不必改系统目录**。是否装由用户决定（属换节点/装驱动级别的决策）。

**42.2 单臂吞吐（现行唯一有效口径）**：控制步口径 = 物理 500 Hz（模型 `timestep=0.002`）÷ decimation 16 ⇒ **控制 31.25 Hz，只在控制步渲染一次**（每个 `mj_step` 都渲染的口径过度悲观，已留档不作判据）。
受控测试（`single_arm_controlled.json`：27 个**独立子进程**、**随机顺序** seed 20260929、每配置 3 重复；loadavg 35.86→38.38，`nr_throttled_delta=66`）：

| 配置（单臂，224²除注明） | 控制步/秒（中位） | ms/图 | 10 秒回合墙钟 | 极差% |
|---|---|---|---|---|
| 1 相机 | 26.99 | 37.06 | 11.6 s | 4.0 |
| 2 相机 | 14.80 | 33.80 | 21.1 s | 8.3 |
| 3 相机 | **12.88** | 25.89 | **24.3 s** | 7.1 |
| 3 相机 480×640 | 14.89 | 22.38 | 21.0 s | 17.9 |

⇒ 单臂 3 相机 = **0.41× 实时**。**足以做闭环评测与出图核验，不足以做大规模像素采样。**

**42.3 并行度上限 = 4 个渲染进程**（硬上限，不许自行放大）：
3 相机 224²：4 进程聚合 **50.61** 控制步/秒（效率 **0.98**，`nr_throttled_delta=71`）；8 进程 **55.22**（效率 **0.54**，`nr_throttled_delta=407`，loadavg 45.78→51.80）。
⇒ **4→8 只换来 +9% 吞吐，节流却涨 5.7×** ⇒ 12 核配额已饱和。评测吞吐估算：50.61 ÷ 312.5（每 10 秒回合的控制步数）≈ **0.16 回合/秒 = 583 回合/小时**，100 回合一轮约 **10 分钟**墙钟（**未含 π₀.₅ 推理延迟，该项仍为 null**）。

**42.4 训练/评测双轨**：**训练走 state 档，评测走像素档**。依据：不渲染时物理 **20,415 步/秒**（单臂），渲染使吞吐掉到 12.88 控制步/秒 ⇒ **渲染开销占比 >99%**。任何像素档主张必须同时给出「回合/小时」与「4 进程上限」。

**42.5 瓶颈定位（三条，其中两条是"不是杠杆"）**：单臂视觉网格 **183,746 面 / 91,886 顶点**（`link2` 独占 73,166 面）。
- **分辨率不是杠杆**：112²/224²/480×640 的 ms/图无单调关系，受控 27 次独立进程**可复现**（高分辨率反而更快）。**机制未定 ⇒ 明确标注未解释，禁止以「降分辨率提速」作设计假设。**
- **阴影不是杠杆**：`shadowsize=0` 仅差 **1.7%**。
- **相机数是主要杠杆**：1→3 相机使 ms/控制步 36.7→74.2。
- **降面数的提速上限约 2×**（低面数代理模型 ms/图 12.73 vs 原网格 25.89，同口径 3 相机 224²）。**但该代理不是 Piper 几何、会改变图像外观 ⇒ 只作上限证据，禁止用于策略输入或契约声明**；A2 若要真降面数，须先做与参照数据集图像外观的 A/B 对比并报 D 裁定，**不许静默改**。

**42.6 双臂：能力已验证，但按用户指令停用**。`MjSpec.attach(child, prefix=..., frame=...)` **无需 ROS** 即可组装双臂，实测 `nq=16 / nv=16 / nu=16 / nbody=19 / ncam=3`，渲染非黑（`pixel_std=44.08`）。
⇒ **用户 2026-09-29 指令「先只渲染单臂，不要弄双臂渲染」**：`arms=2` 的历史结果（`piper_bench_osmesa.json`、`piper_ctrl_serial.json`、`piper_ctrl_conc4.json`、`piper_render_sweep.json`、`lowpoly_proxy_osmesa.json`）**仅留档，不得作为验证依据或对外口径**；脚本里已写 `scope="single_arm_only_per_user_directive_20260929"`。组装能力本身保留为后续可选项（节点无 ROS，官方双臂 xacro 需先解决展开，MjSpec attach 是已验证替代路径）。

**42.7 一个原生崩溃坑（写给 A2）**：对已 `from_file` 加载的 spec，把 `geom.meshname` 置空并改 `type=BOX` ⇒ **SIGABRT（`corrupted double-linked list`，core dumped）**。留证 `piper_mesh_ablation.py` + `piper_ablation_osmesa.run1.json`。**不要走这条改网格的路**，要对照就另建独立 XML。

**42.8 CPU 配额口径再确认**：`nproc=112` 且 `sched_getaffinity=112`，但 cgroup v1 `cpu.cfs_quota_us=1200000` / `cpu.cfs_period_us=100000` ⇒ **实际 12 核**。并行度分母一律用 12，**`nproc` 会说谎**。

## §73 裁定 43：**Piper 契约「三值并列」＋夹爪耦合责任归 A2**

**43.1 权威源**：**仿真以 MuJoCo 模型为权威**；任何「Piper 契约」声称**必须实机校准**，**不许在 URDF / MJ joint / MJ ctrl 三套值里挑一个当真值**。
**43.2 实测不一致**（`piper_import_smoke.json`，G5 故意留红）：URDF（度）J1 −150~150、J2 0~179.9、J3 −154.5~0、J4 ±105、J5 ±69.9、J6 ±179.9（速度限 3.0 rad/s）、J7/J8 各指 0~50 mm；MuJoCo（弧度）J1 −2.618~2.168、J2 0~3.14、J3 −2.967~0、J4 ±1.745、J5 ±1.22、J6 ±2.0944、J7/J8 0~0.035 m。
差值：J1 0.45、J3 0.27、J4 0.087、**J6 1.0456 rad（最大）**、J7/J8 0.015 m；且 MJ 内部 `ctrlrange` 与 joint range 也不等。
**夹爪行程三套值：URDF 50 mm / MJ joint 35 mm / MJ ctrl 47.5 mm ⇒ 三值必须并列记录，实机校准前不得选定。**

**43.3 DOF 口径**：**模型级 8 DOF/臂**（`nq=8 nv=8 nu=8`，8 个 position 执行器，kp 10000/2000/500/200…），**指令级 7/臂** ⇒ 双臂**模型级 16、指令级 14（ALOHA 相容）**。
夹爪是 **joint7/joint8 两个独立 slide 关节**，官方模型**无 `<equality>`、URDF 无 `mimic`** ⇒ **两指不会自动联动，A2 必须自行加耦合**（等式约束或指令层镜像）。
**检测口径警告：按关键字（gripper/finger）识别夹爪会漏掉 joint7/joint8，必须按关节类型（slide/prismatic）判定。**

**43.4 跨形态搬数值的禁令**：**YAM 与 Piper 的零位/符号约定不同**（ABC-130k 单条 episode 里 YAM J3 为 **正**值区间 31.6~104.5 度，Piper J3 的 MJ 限位是 −2.967~0 弧度即**全负**）⇒ 参照数据集的 action 数值只能作分布形态参照，**不得作 Piper 的限位或零位依据**（承接裁定 41.2）。

**43.5 SDK 状态**：`piper_sdk`（2.2 MB，CAN）已下载但**依赖未装、未实测**；官方 `piper_mujoco_pid.py` 依赖已弃用的 `mujoco_py` + `glfw` ⇒ **与本机 mujoco 3.9.0 不兼容，不能直接用**，只能移植或借用 PID 参数。

## §74 裁定 44：**A2 三处绕障的处置（D 只读复核发现，尚未由 A2 自证）**

**44.1 transformers 版本与裁定 39 红线冲突（必须先答）**：`probe_run1_transformers_blocker.log` 显示 lerobot 0.4.4 的 `modeling_pi05.py:584` 抛 `ValueError: An incorrect transformer version is used`；但 `contract.json` 与 `load_verification.json` 现场栈是 **transformers 4.53.3 / lerobot 0.4.4**，且**加载成功**。
⇒ **裁定 39 的红线是 `torch==2.6.0+cu124` 不动、transformers 走 extra `transformers-dep` 且 `>=4.57.1`**。现状是**用 4.53.3 跑通了**，与红线不一致。**A2 必须说明是哪一种**：(甲) 4.53.3 下 π₀.₅ 实际可用 ⇒ 请给出判据与红线改判申请；(乙) 另有绕过手段 ⇒ 写明改了什么；(丙) 两份产物来自不同环境 ⇒ 给出环境指纹。**不许沉默，也不许自行改判红线。**
**另注**：B2 的 M1 变异牙已能点名 **lerobot 0.4.5 vs 0.4.4 漂移**（`mutation_verdict.json`），而 A2 产物写 0.4.4、B2 提到新环境是 0.4.5 ⇒ **版本口径本身也可能已经分叉，需与 44.1 一并交代**。

**44.2 兼容目录删步骤的等价性**：`compat_dir_report.json` 显示 A2 建了 `pi05_base_compat_lerobot044`，**删掉 `relative_actions_processor` 与 `absolute_actions_processor`**（理由：registry 里不存在，且 `config.enabled=false` 为恒等映射），保留 8 个步骤。
⇒ **理由成立但需自证**：请给出「`enabled=false` 时该步骤确为恒等」的代码级证据（不是读 config 就下结论），并把 `compat_dir_diffs.patch` 与**原始 ckpt 只读未改**的 sha256 对照一并交。**原始权重目录仍须只读。**

**44.3 无归一化统计 ⇒ zero-shot 结论必须挂警示**：`contract.json` 里 **`pre_normalizer_stats_present = false`、`pre_normalizer_stats_keys = []`**。
⇒ **π₀.₅ base 没带数据集统计量，反归一化后的动作量纲不可信**。因此**任何 zero-shot 成功率/失败率都必须在同一句里标注「无 normalizer stats」**，不得单独引用为能力结论；G3 的 zero-shot 基线报告必须把这条写在结论行而不是脚注。

**44.4 顺带口径**：`load.param_dtypes = ["torch.float32"]`、`config_dtype_field = "float32"`，allocated 13,812.5 MiB ⇒ **当前是 fp32 推理**。若改 bf16 请单独报（显存与数值都会变），**不许与 fp32 结果混在同一张表里比较**。

## §75 台账与待用户项（19:5x）

- **参数表 rev4 已落**：`schema_version 1→2`（**新增 `rendering` 段**）；`hardware` 更正 `gpu_model_count_memory` 的旧错口径、填 `driver_version=590.48.01`、新增 `render_capability`/`piper_assets_local`/`single_arm_render_scope`；`action_contract` 填 `limits_and_interpolation`、新增 `piper_model_level_dof`/`piper_zero_convention_warning`/`piper_sdk_status`；`evaluation` 新增 `pixel_eval_feasibility`/`train_eval_dual_track`/`parallel_eval_workers_cap=4`；`measurements_and_decisions` **29 → 43 条**。before 影像 sha256-12 = `585396682874`，rev4 = `a4d4b768913b`，计数修正后 = `2cb988bfdbfa`。
- **D 的下一批复核（只读）**：① A2 对 §74.1 甲/乙/丙的回答与环境指纹；② A2 的相机注入方案（官方模型 `ncam=0`，命名建议 `cam_high`/`cam_wrist`，参照内参 fx=431.88 fy=431.38 cx=324.26 cy=240.97 @640×480）与**夹爪两指耦合**实现；③ A2 的 π₀.₅ **单步推理延迟**（回填 `timing.inference_latency_measurements`，闭环总吞吐缺这一项）；④ B2 准入闸对 A2 兼容目录的最终判定（含 `A2_inputs_stable_during_run`，B2 已实测到 A2 在闸运行中重写 lock）；⑤ B2 任务 6 草案 9 项是否齐（动作空间一项现有实测支撑：指令级 14、夹爪行程三值未定）；⑥ B 的最后一次代提交。
- **仍需用户提供/决定的四项**：① **是否安装与驱动 590.48.01 同版本的 NVIDIA EGL userspace 库**（装上才可能有 GPU 加速渲染；不装则维持 osmesa 4 进程上限）；② **实机采集窗口与人力**；③ **Piper SDK/实机实测机会**（决定夹爪行程三值与 J6 那 1.0456 rad 分歧能否收敛）；④ **robosuite fps 口径分歧**（A2 在 `daily_report.md` 待裁清单第 6 项提出：`daily_report.md:47` 64²=8.5 fps vs A2 实测 133–143 fps，约 16×，两个数字未并列引用）——**D 的处理：两者口径不同（前者疑为含策略推理/整回合折算，后者疑为纯渲染或纯物理），在 A2 给出各自测量口径前，任一数字都不得单独引用。**

## §76 裁定 45：**控制频率锚定 30.0 Hz（D 自我纠错：先前 31.25 Hz 基准超出 QC 合格区间）**

**45.1 纠错**：§72.2 的吞吐基准用 **31.25 Hz**（物理 500 Hz ÷ decimation 16，D 为凑整数取的 convenient 值）。但**示范数据实测 = 30 Hz**（4749 帧 ÷ 159.58 s = **29.76 fps**；团队 QC 规则 J/V04 合格区间 **[29.0, 31.0]**，847 条中 27 条越界）⇒ **31.25 Hz 超出合格区间，不得当契约值**；§72.2 的数字**保留为吞吐近似**，正式契约数字以 45.2 的 B 配置为准。
**45.2 实测三配置**（单臂 3 相机 224²、osmesa、每配置独立进程 3 重复；loadavg **61.89→63.41**，`nr_throttled_delta=18`；产物 `runs/vla/d_render_probe_20260929/ctrl_hz_alignment.json`）：
**A** 物理 500 Hz + decim 16 ⇒ 31.25 Hz，**QC 不合格**，11.97 控制步/秒，10 秒回合 26.1 s；
**B** 物理 **480 Hz（`timestep=1/480`）+ decim 16 ⇒ 恰好 30.00 Hz，QC 合格**，**12.03** 控制步/秒（极差 2.2%），**10 秒回合 24.9 s**，**vs A +0.5%**；
**C** 物理 500 Hz + decim 17 ⇒ 29.41 Hz，QC 合格，11.69 控制步/秒，vs A −2.3%。
⇒ **采用 B**。渲染开销占比 >99%，改 `timestep` 基本不改成本 ⇒ **锚定 30 Hz 不付任何吞吐代价**。
**45.3 为什么 P0**：仿真控制频率与示范频率不一致 ⇒ **action chunk 的时间尺度与训练数据不一致**（同一 chunk 覆盖不同真实时长），SFT 后动作整体偏快/偏慢；**该偏差不会在任何单点检查里报错**，只表现为"能接近但抓不准"，排查成本极高。
**45.4 A2 的执行项**：① 环境显式设 30.0 Hz，产物写出 `(timestep, decimation, 折算 Hz)` 三元组；② **若目标 VLA 原生频率不是 30 Hz**（π₀.₅ / ALOHA 生态常见 **50 Hz**）⇒ **必须显式声明重采样方案并报 D 裁，不许静默选**；③ 推理延迟按 **30 Hz 预算**给：**每控制步 33.3 ms 是硬预算**，超了就不是实时闭环，须写明是 chunk 执行（一次推理覆盖 N 步）还是每步推理。
**45.5 B2 的判据牙（建议新增）**：产物出现「控制频率」字段时，**必须同时给 (a) `timestep` 与 decimation、(b) 折算 Hz、(c) 与示范 30 Hz 的关系（相等 / 重采样方案）**；缺任一项判**黄**，折算值与声明值不符判**红**。

## §77 裁定 46：**A2 的 π₀.₅ zero-shot `0/20` 不得作为能力结论；渲染后端钉死 osmesa 一条自我纠错**

**触发**：D 只读复核 A2 新交付（`runs/vla/a2_pi05_zeroshot_20260929/`，20 回合已跑完）。

**46.1 结果与反常**：`[done] env_success=0/20 grasp_truth=0/20 flick_candidates=0 wall=578s`，且 **20/20 全部 `max_stage=0(no_contact)`**；而**随机基线**（`a2_pi05_zeroshot_full.log` / `run_random.log`，`infer=0x`）在 ep04/06/07/10 **达到 `max_stage=2(right_lift)`、ep08 达到 `1(right_touch)`**。
⇒ **π₀.₅ zero-shot 的推进度低于随机基线**。这不是"模型差"的正常表现，**必须先排除环境/预处理侧的假失败，才允许把它写成能力结论**。

**46.2 已确认的机制（A2 自己已给出，D 予以确认，不是 D 的推测）**：`state_channel_saturation_analysis.json` 实测 —— `policy_preprocessor.json` 的 `normalizer_processor.config.features = {}`（**空 ⇒ 完全不做归一化**），而 `Pi05PrepareStateTokenizerProcessorStep` 是 `np.digitize(state, np.linspace(-1,1,257)[:-1])`，**注释明写 state 应已归一化到 [-1,1]**。
⇒ 原始关节角（实测起始位形含 −0.96、1.16 rad）被直接按 [-1,1] 离散化 ⇒ **状态通道饱和**：`waist`/`forearm_roll`/`wrist_rotate`（ctrlrange ±3.14158）**只有 0.3183 的行程可不饱和表示**，`shoulder` 0.6438、`elbow` 0.5937、`wrist_angle` 0.4876。
⇒ **模型看到的是一被压扁且截断的状态，输出的动作又被当作绝对关节角写进 ctrl** ⇒ **`0/20` 是"无 normalizer stats"的必然后果，不是 π₀.₅ 的能力上限**。
**裁定**：**任何引用 `0/20` 的场合，必须在同一句写明「无 normalizer stats，状态通道饱和（waist 仅 0.3183 可表示）」**；结论行写"**本次 zero-shot 不构成能力证据**"。

**46.3 一条告警的定性：`embed_tokens` 缺失是良性的（D 已独立核实，避免误伤）**
- 日志：`Remapped 812 state dict keys` 之后 `Warning: Could not remap state dict keys: Missing key(s) in state_dict: "model.paligemma_with_expert.paligemma.model.language_model.embed_tokens.weight"`。
- D 只读核实 safetensors 头部：**文件内 812 个张量键，确实没有任何 `embed_tokens` 键**；别名只记在 `__metadata__` 里 —— `{"paligemma_with_expert.paligemma.model.language_model.embed_tokens.weight": "paligemma_with_expert.paligemma.lm_head.weight"}`（tied/共享存储，只存一份）。
- 但 `load_verification.json` 的 tied 检查为 **`alias_present_in_model=true`、`twin_present_in_model=true`、`same_storage_data_ptr=true`、`bitwise_equal_in_model=true`** ⇒ **加载后 tie 已在 `from_pretrained` 内部补上，告警良性，不是 `0/20` 的原因**。
- **要求**：把这条 tied 检查**也写进 zero-shot 产物**（现在只在 `load_verification.json` 里有）。否则两份产物之间没有链接，任何读者都无法判断"0/20 是不是权重根本没进去"——**这正是本次 D 差点误判的原因，不许让下一个人再踩**。

**46.4 D 的自我纠错：撤销"后端统一钉死 osmesa"（修订裁定 42.1）**
- §72.1 写「**口径固定 osmesa**」。但 A2 的 zero-shot 产物 `mujoco_gl = "egl"`（venv `pi05_sim`，**mujoco 3.8.1**），且**出图有效**：D 独立解析 PNG —— `224×224`、`bitdepth=8`、`colortype=2`、`raw_len=150752` **与 `expected_len` 精确相等**、`byte_std≈44`、三帧内容互不相同（std 44.48 / 43.69 / 45.81）⇒ **不是黑图、不是坏图**。
- ⇒ **修订**：**渲染后端不再由 D 统一钉死**。改为「**由使用方在其目标 venv 内自证并记录**（含出图非黑/尺寸/长度的证据）」。
- **同时保留的边界**：D 的 osmesa 数字（单臂 Piper STL 网格、mujoco **3.9.0**、`lerobot_eval` venv）**不可跨 venv、跨模型、跨后端搬用**；A2 的 egl 数字（viperx 网格、mujoco **3.8.1**、双臂 3 相机 224²、`env_fps≈12.1`）同样**不可反向搬给 Piper**。**两套数字必须各自标注 (后端, mujoco 版本, 模型, 相机数, 分辨率)。**
- **D 的 egl 探测结论仍成立但适用范围收窄**：在 **mujoco 3.9.0 / `lerobot_eval`** 下 egl 更慢且 teardown 抛 `EGLError`（根因是缺 NVIDIA EGL 落到 mesa 软 EGL）；**这不代表 3.8.1 下的 egl 有问题**。

**46.5 顺带回填两项缺口（A2 §12.5 要的推理延迟，日志里已经有了）**
- `model`: **`chunk_size=50`、`n_action_steps=50`、`num_inference_steps=10`**；`control_dt=0.02` ⇒ **50 Hz**。
- 每回合 300 步 = **6 次推理 / 3.1 s** ⇒ **约 0.517 s 每次 chunk 推理**（首回合 3.5 s，含预热）。
- 整闭环 `loop_fps≈10.5`、`env_fps≈12.1`、300 步墙钟 **28.4 s**（仿真时长 6 s ⇒ **0.21× 实时**）。
- **预算判定**：一个 chunk 覆盖 50 步 = 1.0 s（50 Hz）仿真时间，推理耗 0.517 s ⇒ **推理占实时预算 52%**；若按裁定 45 改成 **30 Hz**，同 chunk 覆盖 1.667 s ⇒ **占 31%**。**⇒ 按 chunk 执行时实时闭环可行；按每步推理不可行。**
- **`timing.inference_latency_measurements` 由 null 回填**（参数表 rev6）。

**46.6 排序裁定（重要，改变线的依赖关系）**：**normalizer stats 只能来自示范数据集** ⇒ **B2 的数据集是 A2 做任何有意义的 zero-shot / SFT 的 P0 硬前置**，**不是可并行的独立线**。
⇒ A2 在拿到 stats 之前，**不要再用 zero-shot 成功率做路线判断**（会得到"π₀.₅ 不行"的错误结论）；这段时间 A2 的有效工作是**契约、接口、延迟、渲染与频率对齐**，不是能力评测。

**46.7 频率冲突从"如果"变成"已发生"**：A2 的环境是 **`control_dt=0.02` ⇒ 50 Hz**，示范数据实测 **30 Hz** ⇒ **裁定 45.4② 现在必须落地**：A2 给出重采样方案（示范 30→50 Hz？还是 chunk 按 30/50 缩放？还是把仿真改 30 Hz？）并**报 D 裁，不许静默选**。

**46.8 环境自身缺陷必须写进契约表（且 Piper 侧不许照抄）**：`env_action_space` 声明 **`Box(-1,1) shape=[14]`**，但 A2 实测 **arm 维在 `before_step` 里被当作绝对关节角(rad) 直接写进 ctrl（`sim.py:38-55`），夹爪维被当作归一化开合度 0..1**，且 MuJoCo 的 `ctrllimited` 会再夹一次（`bimanual_viperx_transfer_cube.xml:17-33`）。
⇒ **声明与语义不一致**。这是 `gym-aloha` 自身的坑，**必须进 G2 契约表第一列**；**Piper 侧的 action space 声明必须与语义一致**，不许继承这个坏习惯。
**另**：A2 的 `actuator_ctrlrange` 有 **16 项**（每臂夹爪是 `left_finger [0.021,0.057]` + `right_finger [-0.057,-0.021]` 两个独立指关节），而 `joint_names` 只有 **14** ⇒ **与 D 在 Piper 上实测的"模型级 8/臂、指令级 7/臂"完全同型**（裁定 43.3）。**A2 应查清 `gym-aloha` 如何把 1 维夹爪指令映射到两个指关节（等式约束？指令层镜像？），并把该模式作为 Piper 侧夹爪耦合的参照实现。**

**46.9 一条诊断请求（不是缺陷判定，D 不下结论）**：出图 `mean≈9.3/255`（偏暗）、非零字节占比仅 7%（也可能只是大面积均匀区域经 PNG 滤波后为零）。
⇒ 请 A2 附**一张与参照数据集同视角的亮度/直方图对比**，以排除"相机朝向或光照不对导致观测近乎全黑"这个**与 normalizer 无关的第二失败因**。**在给出对比前，不许断言图像正常，也不许断言图像有问题。**

## §78 裁定 47：**C2 建线的边界与准入；C 留下的两项待裁一并裁掉**

**触发**：用户告知「新增了 C2，它接下来的任务已经自己给出了」，要 D 核对。
**D 的实测处境**：**仓库里目前没有任何 C2 产物**（`docs/c2*`、`scripts/c2*`、`runs/*/c2*`、`work/decisions/*C2*` 全部不存在；`grep -rln "C2 线|Agent C2"` 无命中）⇒ **C2 的自定任务只存在于它自己的会话里，D 无法核对没有落盘的东西**。

**47.1 准入要求（P0，唯一阻塞项）**：C2 **必须先把自定任务落盘**成 `docs/c2_task_selfintake_20260929.md`，每条含 5 项 —— ① 任务名+一句话目标；② **挂到主线哪一环**（引用 v4 行号或裁定编号；挂不上就写明"辅助实验"并说明为何仍值得做）；③ **是否与 A2/B2/D 重叠**（自查三份执行单 + `docs/c_reuse_manifest_for_a2_b2_20260929.md`）；④ 产物路径 + **有牙的判据**（能被具体篡改打红，参照 B2 的 `mutation_verdict.json`：37 条变异全 ok、9 条反向、baseline 全绿）；⑤ **是否要写冻结面**（要 ⇒ 先报 D）。
**理由（引 C 线历史教训）**：`daily_report.md`「D 第十二次自我纠错」已升为纪律 —— *任何"前置条件/晋级门"在第一次被引用前，必须与 `RL_Harness_v4_20260924/` 原文对撞一次并留下引用行号*。**自定任务同样适用**：C 线绕路不是一次错误决定造成的，而是一条自设门被反复引用后获得既成地位。

**47.2 C2 最容易踩的重叠：登记簿维护权已归 B2，不归 C2。**
依据 `docs/c_handoff_to_b2_registry_20260929.md:1` + 冻结单 §3-C5 + 本备忘 §59 ⇒ **C2 不许改 `work/decisions/registry/` 的机制、工具（`scripts/c_decisions_registry.py`）或自检**；要登记决定走 B2。**C 线走了看起来"没人管"，其实有人管。**

**47.3 C 的既成资产（C2 要"接着用"，不是重做）**：登记簿 **79** entries、`verify` red=0 warn=0、自检 **68/68**；`physical_fact` 接线 **48/48**；逐臂 run manifest **246 臂**（`manifest_sha256=9d41d6917b15f73e…`）、`--selftest` **15/15**；全量回归 **17/17 exit=0**（出处 `docs/c_handoff_to_d_p1_landed_20260929.md:9`）。**重做会让两套自检互相矛盾。**

**47.4 D 给 C2 的缺口（不指派，按价值排序，全部带出处）**
- **【P0】视觉表征缺口**：`docs/ledger_data_bridge_20260928.md:210` —— 「`x_ref` → 表征重算（**现在只重算 flat 状态向量，没有任何视觉表征**）」。**在 VLA 路线下从 P2 升为 P0**：π₀.₅ 输入是图像+语言+状态，账本若只能重算 flat 状态向量，**v4 `:355` 那条「抓空→纠正→数据＋BC→一次 RL 更新→双向评估」的链路在数据层就断了**。**并要求数据桥能承载 normalizer stats**（裁定 46.2 已实测：无 stats ⇒ 状态通道饱和，`waist` 仅 0.3183 可表示）。
- **【P1】`ReleaseBundle` 的 14 个 role 只有自检里的假组件**（`docs/ledger_data_bridge_20260928.md:205`：真实 checkpoint/normalizer/动作契约/调度配置从未被打包，`reach_sac@v1` 等旧版本未迁移）⇒ 建议最小切片 = 把 A2 的 π₀.₅ 兼容目录打成真 bundle，并带上裁定 46 的三条口径（无 stats / 版本 / tied 检查）。
- **【P2】把 C 的"已知限制"变成有牙的判据**（`docs/c_handoff_to_b2_registry_20260929.md` §6 第 2 条：**撤销的牙从未在真登记簿上被真实触发过**）⇒ 可做演练沙箱，**但先问 B2 是否已在做**。
- **不建议**：任何 `robosuite Lift`/小网络 SAC 成功率优化（已降级，`:212` C 自述「**任何『learner 已就绪』的说法都不成立**」）；任何 zero-shot 能力评测（归 A2，且裁定 46.6 明确拿到 stats 前不许用它做路线判断）；任何示范采集/转换（归 B2）。

**47.5 C 留给 D 的两项，现予裁定**
- **（一）写入边界追认 ⇒ 追认。** C 改了 `registry/release_bundle.py`（交接摘要列的 C 边界只有 `registry/verdict_identity.py`）与两个**无 `c_` 前缀**的自检脚本。**理由**：① D 自己在增补五 §9-C③ **点名了 `release_bundle.py:102` 的 `DirectionScore`**（`supervisor_memo_20260928.md:334`）；② 0928 备忘把该文件列在 C 名下（`:60`）；③ P1-5 验收（`DirectionScore` 自带 `gate_build`+`usable_for`）**不改它无法满足**；④ 改动**加法式**，10 个新字段全带默认值、向后兼容，新红线默认开但留**显式**逃生口。**附带条件**：这条追认**必须登记为一条决定**（走 B2）；两个无前缀脚本**保持原名不改**（改名会打断 C 的回归套），但登记条目里要写明"前缀约定晚于这两个文件"。
- **（二）待办 6（ξ 锚 / 导出列变更 = 冻结面）⇒ 不批，暂缓。** C 未动，**这点做得对**。**不批理由**：① 它服务 `queue_td_learner` 那条 BC/SAC 线，而 C 自述该 learner「actor 3 层 MLP、ξ 只有一位、动作域写死 `[-1,1]`…**任何『learner 已就绪』的说法都不成立**」（`:212`）⇒ **在一个自己都说不成立的 learner 上改冻结面导出列，收益不明**；② 主线已改判 VLA（裁定 38），冻结面变更应留给主线需要的改动；③ **风险不对称**：改了污染冻结面且难回退，不改没有任何损失。**复活条件写死**：当 VLA 主线确实需要 BC 锚 / 需要 harness 纠正走 request-commit 时，由提出方**先写清"主线为什么需要它"并报 D**，届时再裁。

**47.6 C2 的卫生与证据纪律（与其它线同）**：不许 `rm`（删除 `mv` 到 `/workspace/mnt/sppro/yhzhang91/recycle_bin/`）；覆写自己的产物前留 before 影像 + sha256-12（裁定 35.1）；run 目录与脚本一律 **`c2_` 前缀**；每个数值带 **loadavg + `nr_throttled`**；外部事实标 `external_unverified`；**并行度分母用 12 核 cgroup 配额，不用 `nproc`（=112，会说谎）**；**不打 iflytek**（裁定 41.4）；**原始权重目录只读**（裁定 44.2）；**不 git 提交**（B 单写者）。
**47.7 C2 唯一被允许写的共享文书 = `daily_report.md` 里追加自己的 C2 小节**（追加、不覆写、不动别人的小节）；需要 D 裁的项写进回流单 `docs/c2_handoff_to_d_20260929.md`，**不要靠对话转述**。

## §79 裁定 48 / 49：**撤销裁定 39 的 transformers 下界（D 第三次自我纠错）+ C2 六条任务的批准与暂缓**

**触发**：C2 就位并提交自述（六条待接任务 + 五项请 D 裁）。**D 逐条核对了它引用的原文与原文件**，不是照单全收；核对表见 `rl_harness_supervision/d_handoff_to_c2_20260929.md` §7.0（**8 条主张：6 条成立、1 条数字错、1 条证据不存在**）。

**48.1 裁定 48：撤销裁定 39 的「transformers >= 4.57.1」下界 —— 它不只是"非必要"，而是有害的。**
- **D 的错在哪**：裁定 39 那条下界是 D 从 lerobot 的**声明依赖**读来的（本备忘 `:1831`，extra `transformers-dep` 下 `transformers<5.0.0,>=4.57.1`），**没有去读卫语句原文**。
- **卫语句原文不是版本区间检查**（`/root/venvs/pi05_sim/.../lerobot/policies/pi05/modeling_pi05.py:576`–`:584`）：`from transformers.models.siglip import check` → `check_whether_transformers_replace_is_installed_correctly()`，`ImportError` 也抛同一个 `ValueError`。
- **A2 的 venv 里那个 transformers 不是 PyPI 的 4.53.3**：`transformers-4.53.3.dist-info/direct_url.json` 实测 = `git+https://github.com/huggingface/transformers.git`、**branch `fix/lerobot_openpi`**、**commit `dcddb970176382c0fcf4521b0c0e6fc15894dfe0`**、`INSTALLER=uv`。
- **`check.py` 全文 4 行**：`return transformers.__version__ == "4.53.2" or transformers.__version__ == "4.53.3"`；D 在 A2 的 venv 实跑 ⇒ **导入成功、返回 `True`**（transformers 4.53.3 / lerobot 0.4.4）。
- ⇒ **装 `>=4.57.1` 会让 `check.py` 返回 `False`，π₀.₅ 直接 `ValueError` 加载失败。裁定 39 若被字面执行会把环境搞坏。**
- **A2 的 lock 记对了**（`runs/vla/a2_env_pi05_sim_20260929/requirements.lock.txt:111` = `transformers @ git+…@dcddb970…`）⇒ **环境可复现，予以确认**。

**48.2 新红线（transformers 身份）**：① **身份 = git 源 + commit `dcddb970176382c0fcf4521b0c0e6fc15894dfe0`（branch `fix/lerobot_openpi`）**，不是版本号区间；② **判据两条同时成立** —— `dist-info/direct_url.json` 的 `commit_id` 与 lock `:111` 一致，且 `siglip.check.…()` 返回 **True**；③ **`torch==2.6.0+cu124` 红线不动**（裁定 39 这半条是对的）。

**48.3 口径规则升为全仓纪律**：**凡引用 transformers 版本必须带 commit** —— 该 git 构建的 `__version__=="4.53.3"` 与 PyPI 的 `4.53.3` **是不同产物**，版本号不足以标识身份。这与 C2 抓到的 `torch 2.6.0` vs `2.6.0+cu124`（D 实读 B2 的 `delegated_g1_g5_a2env.json`：`lock_diff.changed` 里 `torch: 2.6.0 → 2.6.0+cu124`、`torchvision: 0.21.0 → 0.21.0+cu124`，而红线值本来就是 `+cu124` ⇒ **把 local tag 差当"漂移"是假红**）属**同一类问题**，合并为一条：**任何"版本相同"的声称，必须比到 local tag / commit / dist-info 指纹这一层。**

**48.4 B2 的 `V-pi05-1` 牙：换判据 + 加变异体，不是删牙。** 改为锚定 git commit + `direct_url.json` 一致性 + `siglip.check` 返回 True；**变异体三条**：① 改 `direct_url.json` 的 commit ⇒ 红；② 让 `check.py` 返回 False 或移走它（触发 ImportError）⇒ 红；③ **装 PyPI 的 4.53.3（版本号相同、无 `check.py`）⇒ 必须红**（专门防"版本号相同就放过"）。

**48.5 C2 的证据被驳回，但结论采纳**：C2 主张「A2 已用 **812/812 张量逐位相同 + 无随机初始化键**证明 4.53.3 下加载正确」⇒ **D 实读 `load_verification.json` 的 `remap` 段，全文只有 `n_keys_in_file=812`、`n_keys_after_fix=812`、`s=3.65` ⇒ 是键数相等，不是逐位相同**；`tied_weight_checks` 只覆盖 **1 个** tied 别名。**"无随机初始化键"在产物里没有任何证据。** ⇒ **改判成立，但依据必须换成 48.1 的实测，不许用 C2 的理由。**（**这也是"改闸必须先看卫语句原文、不能只看结论数字"的又一实例。**）

**48.6 A2 的裁定 44.1 部分结案**：现场能加载是因为装的是**带 `check.py` 的 git 构建**；`probe_run1_transformers_blocker.log` 的 `ValueError` 是**该分支尚未装好时**由 `ImportError` 触发的。**44.1 的甲/乙/丙三案作废**；**A2 仍须回答的只剩一条**：blocker 与成功之间改了什么、何时改的，并确认已写入 lock（**已写对**）与 `env_manifest.json`（待自证）。

**49.1 T-C2-1（归一化契约层）批准为 P0，并与 A2 分工**：**A2 = 标注与报告口径**（裁定 44.3），**C2 = 造 stats + 做闸**；**C2 不改 A2 的 `pi05_base_compat_lerobot044/`**（另存 + diff patch，C2 自述已如此计划）。
**stats 数据源（D 裁优先级）**：① **A2 当前实际运行的 env**（`gym_aloha/AlohaTransferCube-v0`，ViperX300，14 维）—— stats 必须与"策略将要运行的 env 的分布"同源；② **B2 的仿真双向示范落地后替换**，且**保留两版对比、不许静默替换**；③ **ABC130k 不得用作 stats 源**（YAM 形态，零位/符号约定不同，裁定 43.4 已禁跨形态搬数值 —— **搬 stats 等于把饱和问题换成错配问题**）。
**norm_map 口径（D 裁）**：**保留 QUANTILES（q01–q99），不用 IDENTITY+显式缩放**（理由：`np.digitize(state, np.linspace(-1,1,257)[:-1])` **硬假设 state ∈ [-1,1]**；IDENTITY 会继续违反它，且把量纲问题推给下游 = ACT 线事故同族）。**但必须补一条 C2 没写全的保护：每维 scale 必须有下限**（防近常量维被放大；C2 引的 `(x-mean)/(std+1e-6)` 冲到 20402 即此），**阈值由 C2 给建议值+证据、D 裁，不许抄 ACT 线旧阈值**（换 regime 必须重新立）。
**闸与牙（批准并加码）**：`stats_present` / 每维 q01–q99 对 `ctrlrange` 的覆盖率 / **饱和维数 = 0**；变异体除 C2 提的两个外**再加两个** —— ③ **某维近常量（q99−q01→0）而 scale 无下限保护 ⇒ 红**；④ **用 ABC130k(YAM) 的 stats 喂 ViperX300 env ⇒ 红**（专门防跨形态搬 stats）。`representation_version` 由宽度拼出**批准**，但**名字里必须带 stats 源**（如 `aloha-viperx-quantiles-a2env-v1`）。

**49.2 T-C2-2（`_obs_vector` 白名单 + 全覆盖断言）批准，含改 `harness/queue_td_learner.py`**（已核实**不在冻结面**，`docs/ledger_data_bridge_20260928.md:213`「随时可换」）。**四条要求**：① 先出只读复现探针证明图像键被静默丢弃；② **双向牙**：只有 `state` 的旧快照**仍须绿**（不破坏 ACT 回归基线与 C 的 17/17），带图像键的**必须红**；③ **不得改 `state_dim` 语义**；④ **错误信息必须点名被丢弃的键**，并把"存入键集合 vs 消费键集合"的差集写进产物（**静默失败的反面不是报错，是报得能定位**）。**与 49.1 是同一根因的两面，报告须交叉引用。**

**49.3 T-C2-3 / T-C2-4 / T-C2-5 批准立即开工**；**T-C2-4 提到 P0**（已有**两起 D 独立复核成立**的实例：B2 的 `G2_rebuild_lockout_not_default[a2env]` 期望已满足却报 `WARN`（D 实读该 JSON：`actual.same_as_0928=false` 且 `lock_diff` 已逐包枚举）、torch local tag 假红）。**边界**：纯只读、**不改任何人的闸**；产物**再加一列：该闸最近一次真实变红的时间与原因**（从未红过的闸单独标出）。**T-C2-5 必须把「S13 未补前任何人不得引用『D8 立即变红』」写进清单文档**（它现在只活在冻结单里）。**T-C2-3 落 `c2_*` 前缀正确**（线前缀纪律优先于 C 的原话），但须点名移交 A2，并把 C 的三个推算数字逐个换成实测或明确标注"仍为推算"。

**49.4 T-C2-6（`registry/` 多门禁并存）暂缓、不批**：`registry/` 维护权在 **B2**；多门禁并存**目前没有被主线需要**；与裁定 47.5(二) 同理**风险不对称**（改了会动 C 已验收的 48/48 接线，不改无损失）。**但 C2 必须把 `GATE_MODULE_PATH` 钉死单一 ACT 门禁（`registry/verdict_identity.py:47` 实测）写成一条"待触发"记录**，触发条件写明（π₀.₅ 判定结果需进 `verdict_identity`/`ReleaseBundle` 时报 D 再裁），**不许让它变成沉默缺口**。

**49.5 V-pi05-3 渠道混用**：批准**按格式闭合、不重下**（顶层填 **`mixed`** 并指向逐文件记录，**不许填单一渠道**＝失真；重下 14.47 GB 无收益且下载是 A2 单线）。

**49.6 git 单写者归位 = B2**（C2 的提醒成立：D 实测 **HEAD 仍 `e6c661e`、工作区脏 44 项**）。**裁定**：**B 冻结后由 B2 承接 git 单写者**（与 `registry/` 维护权同源，避免"两个位置都以为对方在管"）；**D / A2 / C2 均不提交**。**要求 B2 立即代提交一次**，并在提交信息里写明 **`runs/` 被 `.gitignore:12` 排除 ⇒ D 的渲染证据（44 文件 / 388 KB）只在 NFS、不进 git**，否则后人会以为证据丢了。

**49.7 C2 的准入**：自述**内容合格**（8 条主张 6 条经得起核），但**必须落盘** `docs/c2_task_selfintake_20260929.md`（§2 的 5 项格式）+ 本回执。**理由**：口述任务 D 事后无法核对，也无法防止它被反复引用后变成既成门（C 线教训）。

---

# 增补二十（2026-09-29 21:0x，D）：用户三条指令落地 · E 线建立 · 频率口径第四次改判 · E2E-min 主线重排

**正文在两份新文书**：`rl_harness_supervision/d_simchain_e2emin_20260929.md`（218 行，`sha256-12 414a78afda21`）与 `rl_harness_supervision/d_handoff_to_e_20260929.md`（116 行，`sha256-12 b0727eee0c4f`）。本节只记裁定编号与不可回退的口径。

**裁定 50（D 自我纠错 · 撤销 48.5 的驳回）**
- **50.1** 48.5 里 D 判「"无随机初始化键"无任何证据」**是错的**。D 本轮枚举 `runs/vla/a2_pi05_contract_20260929/load_verification.json` **全部 18 个顶层键**后确认：`compare.n_compared=812`、`n_bitwise_exact=812`、`n_differ=0`、`n_shape_mismatch=0`、**`n_model_keys_not_covered_by_ckpt=0`**、`verdict="all_bitwise_equal"`。**证据存在，C2 的 §1.3 主张采纳**。裁定 48 的**结论不变**（transformers 下界红线仍撤销），**依据改为 48.1 卫语句原文 + 50.1 加载证据，两条互不替代**。
- **50.2 升为全仓纪律（否定型主张）**：任何「某证据不存在 / grep 命中 0 / 某字段没有」的断言，**必须先枚举完整键集或完整清单**，并把**命令原文 + mtime + 计数**落进产物。**只读一个段就断言整体缺失 = 不合格主张。**
- **50.3 采纳 C2 提议的读侧纪律**：并发追加共享文书 ⇒ **任何 grep / 计数类主张必须同批落 `(mtime, 行数或键数, 命令原文)`**（C2 举证成立：其 19:1x grep 时本备忘 1942 行、20:14 后 2222 行，"命中 0"与"命中 3"在不同时刻皆真）。

**裁定 51（C2 五项需裁项，逐条裁）**
- **51.1 T-C2-1 阈值**：**不采纳** C2 提议的「对 `ctrlrange` 行程覆盖率 ≥ 0.95」作为**红**判据 —— 示范本来不会用满关节行程，这条会把正常数据判红 = **极性错**；**降为 warning + 记录实际覆盖率**。**改为四条真牙**：① `features` 非空（清空必红）；② 每维 scale 下限生效（近常量维不放大）；③ **起态覆盖闸**：A2 实测起始位姿 `state_raw_14d`（`max|state|=1.16`、原始 2/14 维越界）经主线 stats 归一化后**越界维数=0**，用 env-derived 或 YAM stats **必红**；④ **clip 比例上限**（阈值 C2 用 S1 真实数据提议、D 裁）。**scale 下限系数不许抄 ACT 旧阈值**，C2 给**两个候选值 + 各自在真实数据上的效果**。
- **51.2** grep/计数三元组纪律 ⇒ **采纳**（并入 50.3）。
- **51.3** `load_verification.json` 恢复为有效证据 ⇒ **采纳**（见 50.1）。
- **51.4 video-backed obs 存储（接口变更）**：**C2 只报不改**。触发条件 = 实测单批 > 8 GB **或** `StaleObservation`（`harness/obs_store.py:157`）实测真触发；变更需 **D 批 + A2/B2 会签**（消费侧 A2、生产侧 B2）。**现在不预裁。**
- **51.5 §4.2/§4.3 触发条件** ⇒ **照 C2 口径登记**，但**登记动作走 B2**（`registry/` 维护权在 B2，裁定 47.2 / 49.6），C2 只提供条目文本。

**裁定 52（stats 源优先级修订 · 修订 49.1）**
- **主线部署 stats = 与 BC 训练数据同源（S1 示范数据）**；训练与评测必须用同一份。
- **env/ctrlrange 推导的那一版降为诊断用**（解释 zero-shot 状态通道饱和），**不得进主线部署包**；两版都保留、都写进 `representation_version`（名字带 stats 源）、**不许静默替换**。
- **ABC-130k（YAM 形态）继续禁用**（裁定 43.4：搬 stats = 把饱和换成错配）。**理由**：BC 的归一化必须匹配训练分布，用 env 行程推导的 stats 训、用 demo stats 评（或反之）都是分布错配。

**裁定 53（频率口径改判 · D 第四次同型自我纠错）**
- **实测**：gym-aloha `bimanual_viperx_transfer_cube.xml` 的 `m.opt.timestep = 0.002`（无 `<option timestep>`，走 MuJoCo 默认）；模型 **`nq=23, nv=22, nu=16, ncam=7`**（D 用 `MjModel.from_xml_path` 直读，`MUJOCO_GL=disable`，未渲染）。
- **`dm_control/rl/control.py:168`–`:194` 的 `compute_n_steps` 对非整数倍是 `raise ValueError`，不是四舍五入** ⇒ **`DT=1/30` 会直接构造失败**。
- ⇒ **裁定 45 的"恰好 30.0 Hz（`timestep=1/480` + decim 16）"在 gym-aloha/dm_control 口径下不可实现**。它是 **D 在 Piper/原生 mujoco 口径下实测的**，被跨口径搬运，正是裁定 46.4 禁止的事。
- **新口径**：主线仿真控制频率 = **29.4118 Hz（`DT=0.034` = 17×0.002）**，落在团队 QC 区间 **[29.0, 31.0]**；**每控制步硬预算 = 34.0 ms**（**33.3 ms / 30.0 Hz 降为名义锚**，延迟判定一律用 34.0 ms）。π₀.₅ 实测 0.517 s/chunk、chunk=50 ⇒ 覆盖 **1.700 s** ⇒ **占预算 30.4%**。
- **其它档位**：`DT=0.032`→31.25 Hz、`DT=0.030`→33.33 Hz（**均出 QC 区间**）；精确 30.0 Hz 需把模型 timestep 改 `1/480=0.0020833`（×1.0417）⇒ **属改第三方模型资产，需接触/稳定性 A/B + D 批，默认不走**。
- **实现约束**：`DT` 是 `gym_aloha/constants.py:4` 的模块级常量（被 `env.py:134` 传入）⇒ **不许改 site-packages 原文件**，必须在本仓自有 shim 内改口径，产物记 `representation_version` + shim `sha256-12` + **实测 Hz**。**S1/S3/S5/S6 必须同值。**
- **纪律升级（口径搬运禁令）**：任何频率/延迟/吞吐/分辨率口径，**第一次用于新的 (venv, 后端, 模型, 环境) 组合前，必须在该组合内重测或读实现原文确认可实现性**，留 file:line 或实测 JSON。**本日四起同型**：31.25 Hz 契约值 / osmesa 钉死 / `transformers>=4.57.1` / **`1/480+decim16` 跨到 dm_control**。共同根因：**读了声明、搬了口径，没读实现。**

**裁定 54（E2E-min 主线重排 + 两处新指派）**
- **E2E-min 定义**：对撞 v4 `01_开发技术方案.md:355`（「首个迭代只打通 抓空→Harness 同协议纠正→数据＋BC→一次 RL 更新→双向无动作辅助评估」）、`:346`–`:353` 阶段表、`:357`（policy 无动作辅助能力是主结果）、`:5`（初始成功率可为零、不使用 ACT）。**"跑通"= S1–S6 各自有可核证据 + S6 一次 RL 更新给出方向性证据（无增益也算结论，须带诊断）；成功率高低不是出口条件。**
- **S4 缺口（本轮新识别，已实测）**：`harness/runtime_adapter.py` **全文 77 行是 mock 驱动 + 单 slot**（`policy="mock"`，`step()` 只调一次 driver）；`harness/env_factory.py:1`–`:45` 是 **reach/robosuite 的 monkeypatch shim**（`KNOWN=(reach,perturbed)`）⇒ **两者都不能承载 π₀.₅ 的 chunk=50 → 29.41 Hz 逐步下发**。**指派**：`harness/vla_runtime.py`（新文件）= **A2**；`harness/env_gym_aloha.py`（新文件，含 §53 频率 shim）+ 四类判定接 `ledger` = **C2**；这一段的闸与三版本记录（policy/stats/shim）= **B2**。**硬边界：不许改 `harness/contracts.py`（冻结面），只允许加法式新增文件；确需改契约先报 D + before 影像 + sha256-12。`harness/queue_td_learner.py` 属降级线，S4 不复用。**
- **S1 缺口（当前唯一真正卡全链的阻塞）**：仓内**没有一集主线示范数据**（B2 只有形态夹具）。**D 已实测的可行性通道**：`gym_aloha` 0.1.4 **无 expert**（`grep -rn expert --include=*.py` 命中 **0**，21:0x），**但** `tasks/sim_end_effector.py:36`–`:55` 用 `mocap_pos/mocap_quat` + `unnormalize_puppet_gripper_position` 驱动，且 `assets/bimanual_viperx_end_effector_transfer_cube.xml` **含 2 处 `<equality>`（weld）**（关节空间版含 0 处）⇒ **在 EE 空间给航点序列，weld 负责解算，录 `qpos` 即 14 维关节示范**；`env.py:120`–`:124` 支持 `task="end_effector_transfer_cube"`（未注册但可直接构造）。**两个已知障碍**：`env.py:150`–`:164` 的 `reset()` 对非 `{transfer_cube, insertion}` 直接 `raise ValueError`（需子类覆写或旁路 `AlohaEnv`）；`env.py:139`–`:140` `obs_type="state"` 是 `NotImplementedError`（状态档走 `pixels_agent_pos` 的 `agent_pos`）。**反向任务必须自建判据**（`env.py:174`–`:180` 的 `reward==4` 只覆盖右→左）。
- **降级/暂停**：双臂渲染、实机与采集窗口、Lift/小网络 SAC/`queue_td_learner`、T-C2-6、文献检索 —— 见 `d_simchain_e2emin_20260929.md` §6。**C2 的 T-C2-4 保留 P0 但限时**（只审"在长的 4 把新闸 + S1–S6 新闸"，不做全仓历史普查）。

**裁定 55（E 线建立 + 撤回两项欠用户的请求）**
- **55.1 E 线 = GPU 渲染解锁/吞吐线**，任务书 `d_handoff_to_e_20260929.md`。**定位：吞吐线，不在正确性关键路径**；**时间盒一个工作块**；**判不可行即出 no-go + 平台申请文本并停线等 D**，不得转做别线的活。
- **55.2 核心命题（不许照抄既有断言）**：`docs/infra-gpu-render.md` §4 断言「容器内自己装 `libnvidia-gl-*` 解决不了」，其理由之二「没有 `/dev/dri` 时 EGL 设备枚举拿不到任何设备」**对 Mesa 成立、对 NVIDIA `EGL_EXT_platform_device` 未经证实** —— D 本轮实测 **`/dev/dri` 不存在，但 `/dev/nvidia2`(195,2)、`/dev/nvidiactl`(195,255)、`/dev/nvidia-uvm` 存在**，且 `NVIDIA_DRIVER_CAPABILITIES=compute,utility`、compute 侧库**混了 590.48.01 / 535.104.12 / 550.54.15 三个版本**、`egl_vendor.d` 只有 `50_mesa.json`。⇒ **该断言现标 `declared_only`，由 E1 实测判定**。**D 自己此前"装 4 个库即可"的口径与该断言互相矛盾且均未实测，一并作废。**
- **55.3 撤回欠用户项②（解除单臂渲染）**：用户判断成立 —— **瓶颈是网格面数**（单臂 Piper **183,746 faces / 91,886 verts**；分辨率无单调效应，27 进程复现，A2 在另一套 (venv,mujoco,模型) 上独立复现 `docs/a2_pi05_sim_readiness_20260929.md:353`），**并行度已撞 12 核配额顶**（4 进程效率 0.98；8 进程 0.54，`nr_throttled_delta` 71→407）⇒ **双臂 ≈ 每帧几何 2× ⇒ 吞吐近似减半，且不产生任何主线证据**（双臂装配已用 `MjSpec.attach` 证过一次，`nq=16`，标 `arms2_archived_only_per_user_directive`）。**单臂限制继续有效，D 不再请求解除。**（双臂吞吐减半是 `arithmetic_from_measured_inputs`，**非实测**，因实测被用户指令禁止 ⇒ 保持推算标注。）
- **55.4 「只渲单臂」的作用域裁定**：该限制**只约束 Piper / Cobot Magic 自有资产渲染线**；**主线仿真代理保持 gym-aloha 双臂不动** —— π₀.₅ base 形态是 **`aloha_bimanual_14d`**（14=2×7，812/812 张量 bitwise 校验通过），代理模型实测 `nq=23/nu=16/ncam=7` **本身就是双臂场景**，不是"我们选择渲双臂"。**若用户要求连代理也单臂 ⇒ 等于换底模，属路线分叉，需用户明确指令，D 不自行推进。**
- **55.5 撤回欠用户项③（实机采集窗口）**，改**触发式延期**：触发 = **E2E-min S5 通过 + S6 有方向性证据**。理由：实机是 v4 **P4**（`:349`），入口条件是 P1–P3 有可检验证据，而当前 P1 连示范数据都没有 ⇒ 现在锁窗口是提前锁定尚未定形的接口。触发时 D 交付一页纸《实机窗口选取依据》（v4 `:357` 六行报表必须现场采到的字段 + 成熟项目窗口口径对照，**全部标 `external_unverified`** + 需先解决的硬件口径冲突：夹爪行程三值、J6 的 1.0456 rad、30/50 Hz，裁定 43）。**本轮不做文献检索（不在关键路径）。**
- **55.6 上报纪律（源自本轮被用户两次反问）**：**凡欠用户的请求项，必须先证明它阻塞 E2E-min 的某一段，否则不进上报清单。** D 上一轮把 5 项并列上报，其中②③属**把下游依赖当成当前阻塞**。

---

# 增补二十一（2026-09-29 21:3x，D）：D 自我复核（两处更正）· GPU 渲染解锁验收 · 边界违规处置 · 用户委托的两项确认生效

**正文**：`rl_harness_supervision/d_simchain_e2emin_20260929.md` §9（218→**270** 行）、`d_handoff_to_e_20260929.md` §8（116→**173** 行）、三份执行单追加节（a2 §14 / b2 §12 / c2 §9）。**断点文件**：`rl_harness_supervision/d_context_checkpoint_20260929_2130.md`（**160 行**，`sha256-12 3ccacb42d138`）—— **节点可能关闭，重启后新会话只读它即可接续**。
**用户授权（21:2x 原文要点）**：「你这边自己再核对一遍，无问题可直接确认……持续监控 A2/B2/C2/E 相关进程结果并发布指令进行指导……后续你判断无误可直接确认执行，注意服务器可能会关闭-注意关键对话内容保存」⇒ **技术性口径 D 自决并写死可推翻条件；路线分叉仍留用户。**

**裁定 56（D 自我复核：不重读自己的文书，全部真跑或逐字读源码 ⇒ 发现两处自己的错）**
- **56.1【更正，影响 B2 的 S1】`task="end_effector_transfer_cube"` 在 gym-aloha 0.1.4 是死代码**。D 在 `d_simchain_e2emin` §4-S1 写「`env.py:120`–`:124` 支持该 task，未注册但可直接构造」——**错**：逐字原文 `:120` 是 `elif task_name == "end_effector_transfer_cube":`，**`:121` 紧接 `raise NotImplementedError()`**，`:122`–`:124` 不可达（`end_effector_insertion` 同型，`:126`）；**D 真跑复现**：构造即抛，抛点 `gym_aloha/env.py:121`（由 `env.py:44` 的 `__init__` → `_make_env_task` 调用）；`env.py` 内 `NotImplementedError` 共 5 处（`:47`/`:121`/`:126`/`:131`/`:140`）。**但 mocap+weld 通道本身成立**（逐字核过）：EE 版 xml `:5`–`:8` 是两条 `<weld body1="mocap_left" body2="vx300s_left/gripper_link" solref="0.01 1" solimp=".25 .25 0.001"/>` / `mocap_right`；`:15`/`:20` 有 `<body mocap="true" name="mocap_left" pos="0.095 0.50 0.425">` / `mocap_right pos="-0.095 0.50 0.425"`；**关节空间版 xml `mocap` 命中 0**。⇒ **正确做法 = 绕开 `AlohaEnv._make_env_task`，自有代码里直接构造 `control.Environment(Physics.from_xml_path(EE_xml), TransferCubeEndEffectorTask(), time_limit=inf, control_timestep=DT)`（约 5 行）+ 自行复刻 `_format_raw_obs` 与 `BOX_POSE` 播种**（`env.py:150`–`:164` 的 `reset()` 对该 task 仍 `raise ValueError`）。**备选**：关节空间自写脚本专家（分阶段 PD + `sim.py` 夹爪归一化），**二选一报 D，不许两条同时铺**。
- **56.2【更正，影响 E 的任务书】`libEGL.so.1` 的 `eglQueryDevicesEXT`：动态符号表没有，但 `eglGetProcAddress` 能取到**。三种独立方法（裁定 50.2 要求先枚举）：`nm -D` 命中 **0**、`objdump -T` 命中 **0**（`.text` 动态符号共 **44**，`eglQuery*` 只有 `eglQueryAPI/Context/String/Surface`）、`strings` 命中 **1**；**运行时自证**：`hasattr(lib,'eglQueryDevicesEXT')=False`，但 **`eglGetProcAddress(b'eglQueryDevicesEXT')` 返回 `0x7f0b700a4b70`（非 NULL）**，`eglGetPlatformDisplayEXT` 同。包版本 `libglvnd0/libegl1 = 1.4.0-1`。⇒ **`docs/infra-gpu-render.md` §2.3 的"连符号都没有⇒没有 vendor 提供设备枚举"表述不准确**（glvnd 对 EXT 走 `eglGetProcAddress` 分发）；**真因是没注册 NVIDIA vendor ICD**；**D 在 E 单 §3.1-1 写的"还需补一套新版 libglvnd"分支，实测证明不需要。**
- **56.3【一条既有断言被证伪】"没有 `/dev/dri` 就枚举不到设备"对 NVIDIA 不成立**：E 实测枚举到的 NVIDIA EGL 设备 **`drm_device_file=null`**、`vendor="NVIDIA"`、`initialize_ok=true`、扩展含 **`EGL_NV_device_cuda`**，渲染子进程**自己持有 `/dev/nvidia2` + `/dev/nvidiactl` fd**（L5b）。⇒ **`docs/infra-gpu-render.md` §4 的结论"容器内装不了"整体作废**（其"版本必须与宿主驱动严格一致"这一半仍成立，E 用的正是 590.48.01）；§3 表里 **ManiSkill3 像素档 ❌ / RoboTwin(SAPIEN+Vulkan) ❌ 两行也作废**（E 实测 ManiSkill 64 envs 512² `source_device="cuda:0"` 可跑；Vulkan `vkCreateInstance=VK_SUCCESS`、2 个物理设备含 `NVIDIA A800-SXM4-80GB`、driverVersion `590.48.1.0`）。**更正方式 = 追加不覆写，点名移交原作者线（E3-5）。**

**裁定 57（A2 的频率 shim 验收通过 + 一条新纪律）**
- **57.1 验收通过**：`envs/gym_aloha_shim.py`（192 行，`sha256-12 dc14466fcdcf`）+ `runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json`（21:23:27）：`DT=0.034`→`n_sub_steps=17`→**`control_hz=29.411765`**、`in_qc_band_29_31=true`、`per_step_budget_ms=34.0`、`representation_version=gym_aloha_dt0.034_29.4118hz_shim_v1`、**`site_packages_modified=false`**、`gpu_used=false`、`policy_executed=false`，五元标注齐全且自带 `cross_transport_ban`。**D 用独立脚本直调 `dm_control.rl.control.compute_n_steps` 得到同一结果**（含 `DT=1/30` 的 `ValueError: Control timestep (0.0333…) must be an integer multiple of physics timestep (0.002)`）⇒ **两线互证。**
- **57.2 D 的表述不完整，A2 抓到（记功）**：D 只说"`DT` 是 `constants.py:4` 的模块级常量、用自有 shim 改"；A2 发现 **`gym_aloha/env.py:7`–`:12` 是 `from gym_aloha.constants import (…, DT, …)`** ⇒ `DT` 在 `env.py` 里是**已复制的绑定**，**只改 `constants.DT` 会静默保持 50 Hz**，并把这点做成可复现变异实验（`patch_mechanism_proof`）。
- **57.3 主线只允许一份 shim**：**S1/S3/S4/S5/S6 一律复用 `envs/gym_aloha_shim.py`**，**不许各线自己再写**（两份 shim = 数据与评测不同频 = 口径分裂）。
- **57.4 新纪律（monkeypatch）**：**任何 monkeypatch 必须先读使用方的 import 形式**；`import m` + `m.X` ⇒ 改 `m.X` 有效；**`from m import X` ⇒ 必须同时改使用方模块里的同名绑定**；**并必须配一条"只改一半 ⇒ 静默错值"的变异体**。列为 C2 T-C2-4 的新增审点。

**裁定 58（用户委托 D 确认的两项 ⇒ 确认生效；附回合时长裁定）**
- **58.1 单臂限制的作用域（裁定 55.4）⇒ 确认**：「只渲单臂」**只约束 Piper / Cobot Magic 自有资产渲染线**；**主线仿真代理保持 gym-aloha 双臂**（π₀.₅ base = `aloha_bimanual_14d`，代理模型 `nq=23/nu=16/ncam=7` 本身即双臂场景）。**推翻条件**：用户明确要求代理也单臂（⇒ 换底模，路线分叉，需重开选型）。
- **58.2 频率口径 29.4118 Hz / 34.0 ms（裁定 53）⇒ 确认**，且已由 A2 独立真跑复现（§57.1）。**推翻条件**：团队 QC 区间 [29.0,31.0] 被上游修订，或用户要求精确 30.0 Hz（⇒ 需改模型 timestep 到 1/480 + 接触稳定性 A/B + D 批）。
- **58.3 `max_episode_steps=300` 在 29.4118 Hz 下 = 10.2 s（原 50 Hz = 6.0 s）⇒ 裁：保持 300 步、不缩放**；但 **`episode_horizon_s=10.2` 必须写进每份 manifest，超时/失败一律按秒登记，跨频率对比不得按步数并列**；与 50 Hz 生态数字对比必须显式换算并标注。

**裁定 59（渲染后端改判：osmesa → egl + prefix-only NVIDIA vendor）**
- **依据（E 实测，D 只读复核 15 个产物）**：**staged（prefix-only，零系统写入）六条绿判据全过** —— L1 七个 NVIDIA 渲染库齐全 / L1b 库版本 == 驱动 590.48.01 / L2 枚举到 NVIDIA 设备且 `EGL_VENDOR` 含 NVIDIA / **L3 `GL_RENDERER = "NVIDIA Corporation | NVIDIA A800-SXM4-80GB/PCIe/SSE2 | 4.6.0 NVIDIA 590.48.01"`** / L4 非黑（`image_mean=75.955`）/ L5 渲染期间 `util_max=67%`、`mem_max=142 MiB` / L6 进程内真的加载 `libEGL_nvidia`、`libnvidia-glcore`、`libnvidia-eglcore`、`libnvidia-glsi`、`libnvidia-gpucomp`；裸渲染 256² **2042.2 fps RGB / 2521.79 fps depth**。
- **下游真实环境**：`robosuite_lift` 256² 2 相机 60 步 **11.58 → 101.78 steps/s（8.8×）**（venv `rlrobot`、robosuite 1.5.2，图像 mean 219.148→217.037）；**`gym_aloha` 480×640 60 步 7.583 s → 0.55 s = 7.91 → 109.09 steps/s（13.8×）**（venv `pi05_sim`，**图像 mean 39.892 → 39.869 ⇒ 换后端不改变图像语义**，这是允许跨后端比较图像、但**吞吐数字仍不得跨后端搬用**的依据）。
- **双向负对照（判据有牙）**：`neg_force_mesa_icd`（强制 Mesa ICD ⇒ llvmpipe、1 个 Mesa 设备、79.65 fps）；**`neg_osmesa_backend`（装了 NVIDIA 库但 `MUJOCO_GL=osmesa` ⇒ 仍是 llvmpipe，66.56 fps）**；`vulkan_neg_lavapipe`（只剩 llvmpipe）；`post_rollback`（回滚后 llvmpipe、**0 个 NVIDIA 设备**、62.93 fps）。
- **裁定**：**主线渲染后端 = `MUJOCO_GL=egl` + prefix-only NVIDIA vendor ICD**（`LD_LIBRARY_PATH` 与 `__EGL_VENDOR_LIBRARY_FILENAMES` 指向 **`.codex-persist/nvidia-gl-590.48.01/`**，NFS ⇒ 重启不丢）；**`osmesa` 降为 CPU 对照与退路**（裁定 42 的 osmesa 口径在 GPU 路径可用前提下作废，但**其已留档数字仍有效，五元标注写明 `osmesa`**）；**`parallel_eval_workers_cap=4` 是 CPU 渲染口径的实测上限，GPU 下必须由 E 重测（含"A2 训练并发时"）后 D 裁**；**各线在自己进程内激活，禁止系统写入。**
- **对主线的影响（D 的判断）**：S1 像素示范与 S5 像素评测的成本降一个数量级 ⇒ **"训练走 state 档、评测走像素档"这条旧口径（`evaluation.train_eval_dual_track`）需重估**，但**不在本轮改**（等 E3-3/E3-4 的主线口径数字）；**瓶颈预计从渲染移到 π₀.₅ 推理（0.517 s/chunk）**，A2 需重测闭环延迟。

**裁定 60（E 的边界违规处置：结果采纳，程序记一次）**
- **违规事实**：21:02 把库装进 **`/usr/lib/x86_64-linux-gnu/`**（`install_manifest_20260929_210231.json` 逐文件带 `sha256`）、写 **`/usr/share/glvnd/egl_vendor.d/10_nvidia.json`**、**跑 `ldconfig`**（`/etc/ld.so.cache` mtime 09-29 21:18）⇒ 违反 E 单 §3.2 三条硬边界。**且 staged 路径在 20:59 已判绿 ⇒ 系统安装对结论不是必需。**
- **记功事实**：**没用 `rm`**（备份进 `recycle_bin/e_gpu_install_20260929_210231`）、**没用 apt/dpkg**（`/var/lib/dpkg/status` 与 `/var/log/dpkg.log` mtime 仍 **15:49**）、**主动回滚 + 负对照自证**（`post_rollback.json`）。
- **D 的独立复核（不采信 E 自述）**：`ldconfig -p | grep -c 'libEGL_nvidia|libGLX_nvidia|libnvidia-eglcore|libnvidia-glcore'` = **0**；**逐条验证 cache 内所有 nvidia 条目路径真实存在（无 dangling —— 这是最危险的残留，已排除）**；`/usr/share/glvnd/egl_vendor.d/` **只剩 `50_mesa.json`**（mtime 05-13）；`/usr/lib/x86_64-linux-gnu/` **无任何 09-29 新增文件**（仅目录自身 mtime 变化）⇒ **系统状态与实验前一致，A2/B2/C2 的 venv 未受影响**（`ld.so.cache` 重新生成属幂等，且已验证无 dangling）。
- **处置**：**结果采纳**；**程序违规记一次并入台账**；要求 E 在回流单回答一句「**staged 已判绿（20:59），为何 21:02 还做系统安装？**」（若理由是"验证下游在默认 `LD_LIBRARY_PATH` 下可用"，属正当但**应先报 D**；D 依此决定是否升为纪律）。**重申：主线一律 prefix-only，禁止任何系统写入（含 `ldconfig`）。**

**裁定 61（ABC-130k 产物必须带禁用标记）**：B2 的 `runs/vla/b2_abc130k_pairs_20260929/`（20:44）**三条做得对**（`morphology_proxy="yam"`、源目录 `write_policy="一律只读"`、license 标 `external_unverified`），但目录内有 **`normalizer_stats.json`** 与 `run1_no_saturation_metric`，而 **YAM stats 是主线禁用项**（裁定 43.4/49.1/52）⇒ **要求在 `dataset_card.json` 与 `normalizer_stats.json` 顶层各加 `"not_for_mainline_normalizer": true` 与 `"allowed_use": "form_reference_and_qc_metric_only"`**（追加式 + before 影像 + `sha256-12`）；该 stats **只能作"必红"分支的输入**（C2 T-C2-1 已立此牙：**YAM stats 喂 ViperX300 ⇒ 红**）。

**裁定 62（C2 的 `harness/env_gym_aloha.py` 三条硬约束）**：① **频率必须复用 A2 的 `envs/gym_aloha_shim.py`，不许自写第二份**；② **闸必须能把"只改一半的 monkeypatch"判红**（裁定 57.4）；③ **回合时长按秒登记**（`episode_horizon_s=10.2`，裁定 58.3）。另：**T-C2-3 的 obs 容量测算必须分 CPU/GPU 两档**（GPU 档吞吐 13.8× ⇒ 同墙钟时间帧数暴涨，容量压力更大），**"压缩 / video-backed"二选一的依据要在 GPU 口径下重算**；触发 D 裁的阈值不变（单批 >8 GB 或 `StaleObservation` 实测真触发，裁定 51.4）。

**裁定 63（C2 的 obs 键探针形式验收通过）**：`runs/vla/c2_obs_key_whitelist_20260929/probe_20260929/`（21:13）含 `probe_main.json` + 两个变异（`probe_mut_consume_base0.json`、`probe_mut_fixed_whitelist.json`）+ `probe_summary.json` + `selftest.json`，并有真实 `obs_store_main/`（`index.sqlite` + 内容寻址 `blobs/`）⇒ **T-C2-2 的第 ① 步（只读复现探针）形式合格**；**实质验收等回流单的逐条判据表**；**下一步 = 补丁本身**（照裁定 49.2 四条要求）。

---

# 增补二十二（2026-09-29 22:0x，D）：v4 引用文件身份纪律（D 第五次同型）· S1 通道 D 推断被 B2 证伪（第六次同型）· A2 的 S4 六条裁完 · S1 路线定稿 · E2 验收与渲染口径改判 · C2 补丁验收与覆写违规

> **本轮触发**：用户 21:2x「你这边自己再核对一遍，无问题可直接确认；持续监控 A2/B2/C2/E 并发布指令指导；判断无误可直接确认执行；**服务器可能关闭 —— 注意关键对话内容保存**」。D 据此做了**只读核对 + 四线裁定**，未改任何实现代码、未提交 git。

**裁定 64（v4 引用必须带文件身份 —— D 第五次同型自我纠错）**
- **触发**：A2 在 `docs/a2_s4_vla_runtime_interface_20260929.md` §0-5 报"D 把 requested→committed→activated 的 v4 出处写错了（`:344`–`:346` 实为陷阱表 T24/T25/T26，精确出处是 `:375`）"。**D 在核实前差点直接接受**（上一会话的待办清单里已经写成"采纳 A2 的更正"）。
- **D 实读两个文件后发现：双方读的不是同一个文件。**
  - `…/06_三轮递进调研与方案复审_20260923/01_开发技术方案.md`：**418 行，`sha256-12 = 0a9a2092e18a`** ← **D 引的**。该文件里 `:344` 是空行、`:345`–`:346` 是表头与分隔行，**P0 那一行在 `:347`**（「请求／入队／执行可区分，**能选择 n**」）⇒ **D 偏了 1–3 行**。
  - `…/appendices/01_接口契约与开发验收.md`：**433 行，`sha256-12 = aae20ffe604f`** ← **A2 引的**。该文件里 **`:344` T24、`:345` T25、`:346` T26、`:375`「真实决策请求、提交的动作结果与机械激活相互关联但分别记录」全部逐字成立**。
  - ⇒ **A2 的三条断言都对，但"D 写错了"这个定性不成立**（不同文件的同行号）；**同时 D 的原引用也确实不准**（偏行）。**两边各有一处要改。**
  - **A2 自身一处内部不一致**：其 §2.4 写「v4 `:346`（T25）」，而 T25 在 **`:345`**（其 §0-5 写的 `:345` 是对的）。
  - **D 另两处引用同样偏行，一并更正**：`:340`「发布检查」→ 正文在 **`:341`**；`:357`–`:363`「policy 无动作辅助能力是主结果」→ 该句在 **`:361`**。**`:355`（首个迭代只打通"抓空→Harness 同协议纠正→数据＋BC→一次 RL 更新→双向无动作辅助评估"）与 `:376`（RL 的对照必须是同预算的动态 Harness-DAgger/BC）D 逐字复核准确，不改。**
- **裁定**：① **requested→committed→activated 的权威出处改为双文件双引用**：`appendices/01_接口契约与开发验收.md:375`（契约陈述）+ `01_开发技术方案.md:347`（P0 晋级依据）。② **升级为纪律 `citation_file_identity_discipline`：任何 v4 行号引用必须带文件身份三元组 `(相对路径, sha256-12, 行号)`；只有行号的引用一律视为不可核验，不得进入裁定依据。**
- **定性**：**D 第五次同型事故**（前四次：31.25 Hz 当契约值 / 渲染后端钉死 osmesa / `transformers>=4.57.1` / `1-480+decim16` 跨环境搬运）。**共同根因第六次重复：读了声明，没读实现／没核身份。** 本次的新形态是"**接受了别人一条未核文件身份的更正**"——比前四次更隐蔽，因为它看起来像是在采纳下属的正确意见。

**裁定 65（A2 的 S4 六条裁完；**S4 不等 S1，立即开工**）**
- **65-1 `n_replan = 25`（`H=50`，取 `H≥2n` 等号）—— 采纳 A2 推荐。** 依据（D 逐字复核附录一 `aae20ffe604f`）：`:103`「动作长度 `H≥2n`」、`:105`–`:107` C/E/D 三槽定义、`:101`「首版可采用异步执行、分批训练」、`:345` T25「仅开启训练并发或仅开启执行并发 ⇒ 前者不被称作已实现异步动作调度」。**n=50 时 E=`[50,100)` 与 D=`[50,50)` 双空 ⇒ 三槽退化为同步整块执行 ⇒ S4 验的就不是 v4 定义的异步调度，且 S6 的 TD 样本时序前提对不上。** `n=25` 进 `representation_version`，S1/S3/S4/S5/S6 同值。**A2 的 61.6%/38.5% 维持 `proposed_from_g3_measurement`；仿真允许非实时，但 slot 占比与 deadline-miss 计数必须照记（P4 实机要用）。可推翻条件：S3 改 `chunk_size` / v4 修订 `H≥2n` / 用户要求同步整块执行（= 改设计基线，路线分叉）。**
- **65-2 `max_episode_steps` 维持 300，驳回 A2 的 B 案（176）。** 四条理由：① **176 想保的"与已发表 300 步/6 s 可比"在采纳 29.4118 Hz 那一刻就已失去**（发表口径 `DT=0.02`/50 Hz，动作保持时长差 1.7×，闭环动力学不同）；② **v4 要求的对照是同预算动态 Harness-DAgger/BC**（`01_开发技术方案.md:376` 逐字核过），**不是**已发表数字；③ **E2E-min 出口判据不是成功率**（`:5` 初始成功率可为零、`:348` P1「不要求预先高成功率」）；④ **176 是新派生口径**，要处处携带且偏离注册资产配置（`gym_aloha/__init__.py:16`），而 300 步多给 1.7× 每集数据量。**强制附加**：manifest 必须同时登记 `control_hz=29.4118 / max_episode_steps=300 / episode_horizon_s=10.2 / published_gym_aloha_caliber="DT=0.02, 300 steps, 6.0 s, 50 Hz"`，**跨口径并列一律标 `not_comparable_horizon`**。**可推翻条件：S5 失败归因显示 timeout 占主导（则 horizon 成混淆变量，D 必须开 176 敏感性臂），或用户要求与已发表数字可比。**
- **65-3 `late_policy = hold` —— 采纳。** 附录一 `:111` 逐字：「提前完成不擅自改变固定切换时刻；**错过 deadline 不把晚到结果塞进过期索引**。Runtime 按冻结的迟到规则**继续已有合法动作**、保持或结束尝试，并**记录实际选择**。只有符合该学习分支时序前提的窗口才生成其 TD 样本；**异常事实保留，不重标成"准时"**」⇒ **A2 的 `hold` 就是原文**。**附加**：必须记录"实际选择"三态（hold/keep/terminate）+ `expired` 事件；值进 `representation_version`；**迟到帧不得被重标为 `activated`（B2 的闸要能判这条红）**。
- **65-4 `lease_generation` = 控制代际 = chunk 代际；`epoch` 保持 `ledger.py` 既有语义不动 —— 采纳。** A2 实测 `epoch` 在 `ledger.py` 命中 **18** 处，并**自行作废其"重定义 `epoch`"的初稿 ⇒ 记功**（读 schema 后再定调，顺序正确）。已进参数表 rev10。
- **65-5 v4 行号更正 —— 见裁定 64（部分采纳 + 修正定性 + 更正 A2 一处内部不一致）。**
- **65-6 S4 落地时点 —— 驳回"等 S1"，S4 立即开工。** A2 的顾虑（C 线教训：对着 mock env 自测会打出第二个假组件）**方向对但前提不成立**：① **S4 的证据是结构性的**（chunk 代际、C/E/D 三槽、七类事件、`ledger.frame_fact` 逐字段、deadline 与迟到计数），**不需要示范数据**；② **A2 手上有真实 env + 真实 3 相机渲染路径**（`scripts/a2_pi05_zeroshot_eval.py:190`、`:249`–`:250`，已跑 20 局）**⇒ 不是 mock env**；③ **用 zero-shot π₀.₅ 作真实 obs 载体允许，但裁定 46.6 继续有效：不得用 zero-shot 成功率做任何路线/能力判断**，成功率一栏写 `not_an_exit_criterion`；④ **若 S4 等 S1，而 S1 正卡在右臂 weld ⇒ 全链停摆。S1 只阻塞 S3/S5，不阻塞 S4。** **拆两段**：**S4a（立刻做）** = `harness/vla_runtime.py` + chunk 循环 + 三槽 + 事件 + 版本三件套，对真实 env 跑**可手算短轨迹**逐字段手核（对撞 `01_开发技术方案.md:350` P3）；**S4b（等 C2 的 `harness/env_gym_aloha.py`）** = 四类判定接 `ledger`，**独立于 `reward==4`，不一致即红**。**硬边界重申：`harness/contracts.py` 一个字节不动（七个 `EVENT_KINDS` 够用，不新增 kind），只允许加法式新增文件。**

**裁定 66（S1 路线定稿 + B2 probe2/3/4 验收 + **D 第六次同型自我纠错**）**
- **D 的错误推断被 B2 实测推翻**：D 在 `d_simchain_e2emin_20260929.md:100` 写「EE 空间给航点、**weld 解算**、录 `qpos` 即 14 维关节示范」—— **这是从资产声明（XML 里存在 `<weld>`）推出的行为断言，D 没实测**。**B2 probe2 实测**：`mocap_right` 阶跃 `[0,-0.05,+0.05]` 后 `vx300s_right/gripper_link` 残差 **step1 0.0872 m → step50 0.1359 m，不收敛反而变大**。**原表述作废。**
- **升级为纪律**：**凡"某机制能解算／能收敛／能自动处理"类主张，入文书前必须实测，或读到求解器的实现原文；只凭资产声明（XML/配置里存在某元素）一律标 `declared_only`，且不得作为路线依据。**
- **记功两处**：**probe3 崩了，B2 把整段 traceback 如实留在 `error` 字段、没有藏也没有改成"跳过"**；**probe2 用 `supersedes` 字段明写自己前一轮的两个结论是错的**（`replay_tracking` 映射错误、`joint_replay_box_left` 注入被覆盖）。
- **D 实测补充的硬事实**（`MjModel.from_xml_path` 直读，21:5x）：**两个 XML 都是 `ncam=7`、相机名与父体完全相同**（`left_pillar/right_pillar/top/angle/front_close` 父=world；**`left_wrist` 父=`vx300s_left/gripper_link`、`right_wrist` 父=`vx300s_right/gripper_link`**）；**EE 版 `nu=4`（4 个 actuator 名全为空串）/ `neq=2`，关节版 `nu=16` / `neq=0`，两者 `nq=23`/`nv=22` 相同**；**EE 版是 1 个 `<equality>` 元素含 2 个 `<weld>`**（A2/B2 对 D "2 处 `<equality>`" 的更正成立）。⇒ **A2 §2.3 的结论要精确化：不是"模型没有腕部相机"，而是"`AlohaEnv` 的 observation 只把 `top` 交给 agent"；三相机可直接从 physics 渲出，两个模型都能。B2 的 H2（无臂 actuator，整条臂只靠 soft weld 吊着）在结构上成立。**
- **一条跨线硬事实**：`gym_aloha/tasks/sim_end_effector.py:120` 的 `get_observation` **无条件 `physics.render(480×640, camera_id="top")`**（probe3 traceback 实证）⇒ **EE 通道在 `MUJOCO_GL=disable` 下不可用**。**在 E 线解锁 egl 之前，S1 这条通道根本不可行 —— D 之前把 E 线定位为"不在正确性关键路径"，就 S1 的可行性而言低估了，现予更正入台账。**
- **S1 路线裁定**：**EE 模型只作 IK oracle → 录 `qpos` → 在关节模型（`AlohaTransferCube-v0`，`nu=16`）里用它自己的 actuator 重放，并在关节模型里采 3 相机图像与 14 维动作。不允许在 EE 模型内直接采示范** —— EE 的重力下垂 + soft-weld 滞后与关节模型的 actuator 动力学**不是同一套动力学**，而 **S5 评测必然在关节模型里跑** ⇒ 会引入**训练/评测动力学错配**（附录一 `:346` T26 与 D 的口径搬运禁令所禁）。**B2 probe2 已在做 mapping+replay，方向正确。**
- **右臂发散的 D 侧假设（标 `d_inference_not_measured`）**：probe4 实测 **左臂残差收敛到 `0.0013 m`（<3 mm 绿）、右臂发散到 `0.2469 m`/姿态残差 `2.376 rad`**；`weld_rows` 显示两侧 weld **不是同构镜像** —— 左 `relpose_quat_wxyz_raw=[1,0,0,0]`（单位）、右 `=[-3.67e-06,0,0,0.99875]`（**w≈0,z≈1 ⇒ 绕 z 轴 180°**），`anchor2` 的 x 分量左右反号（`-0.134706`/`+0.134706`）⇒ **D-H1：解析反解对右臂沿用了左臂的单位 `qrel`，未逐侧复合**。**判据（能红）：逐侧复合 `qrel` 后右臂位置残差应 <3 mm；若仍 >3 mm ⇒ D-H1 被否，转 H2/H3，并把否证结果写进产物（D 的推断被否也要留痕）。**
- **S1 四条附加要求（数字全取自 B2 probe4，不许另测）**：① **方块先沉降**（seeding `z=0.05` → 12 步后 `z=0.0200`，自由落 0.03 m ⇒ 第 0 帧必须在沉降后，manifest 记 `box_settle_steps=12`）；② **夹爪标定用 probe4 的表**（cmd→spread_m：`0.0→0.01833`/`0.25→0.02828`/`0.5→0.0465`/`0.75→0.06605`/`1.0→0.08412`，方块宽 `0.04` ⇒ **张开 `cmd≈1.0`、闭合 `cmd≈0.0`、开合阈值 `cmd≈0.45` 进 manifest**）；③ **存 14 维动作不存 16 维 `qpos`**（probe4 实测 `qpos16` 的 `[6],[7]` 与 `[14],[15]` 是 ±同值对 ⇒ 14 维夹爪位 ↔ qpos 对 `(+v,−v)`，映射写死并进 `representation_version`）；④ **指尖偏置用实测 `tip_rel_gripframe=[0.09346, 1.16e-05, 0.00208]`，不要用 `gripper_link` 原点当指尖**。
- **S1 出口判据（任务级，不是残差级）**：**N 集**（N 由 B2 提案、D 批；**D 的先验建议 = 先导 5 集 + 正式 20 集**，与 C2 T-C2-1 的 stats 时刻对齐）满足五条：**几何真值判定的搬运成功（独立于 `reward==4`，不一致即红）**／**3 相机 224² + 14 维动作**／**`episode_horizon_s=10.2` + `control_hz=29.4118` + 三件套版本**／**重放该动作序列在关节模型里能复现同一结果**／**反向同理且判据自建**（`env.py:174`–`:180` 的 `reward==4` 只覆盖右→左）。

**裁定 67（E 线 E2 验收 + 渲染口径改判）**
- **合规性 D 独立复核通过**：`boundary_guard.ok=true`、`forbidden_paths_present=[]`、`system_render_lib_hits=[]`、`icd_dir_listing./usr/share/glvnd/egl_vendor.d=["50_mesa.json"]`（只剩 Mesa）、`prefix_libs_complete=true`（7 库全在）、`prefix_vendor_json=true`；D 侧另核 `ldconfig -p` 四类 GL 库命中 **0**、系统库目录无 09-29 新增 ⇒ **prefix-only 成立，裁定 60.3 的回滚未被破坏**。
- **采纳的数字**（3cam 224²、reps=3、`bench_seconds=5.0`、独立进程）：**gym-aloha 双臂** osmesa `14.01` → **egl_nvidia `165.65` ctrl-steps/s = `11.82×`**（min 162.43/max 177.76，spread 9.3%），**egl_mesa `12.83` = `0.92×`（比 osmesa 更慢，spread 37.3%）**；**Piper 单臂** osmesa w1 `12.54`/w2 `24.83`(eff 0.99)/w4 `47.49`(eff 0.947)，**egl_nvidia w1 `633.95` = `50.55×`/w2 `817.81`(eff 0.645)/w4 `1511.27`(eff 0.596)**。**负载对成对引用**：gym-aloha 前 `loadavg 47.49/49.29/49.18`、`nr_throttled 3532` → 后 `50.08/49.61/49.29`、`3667`；Piper 后 `53.83/50.91/49.77`、`3749`。**渲染器证据逐档对应**（egl_nvidia = `NVIDIA A800-SXM4-80GB/PCIe/SSE2 | 4.6.0 NVIDIA 590.48.01` + `child_nvidia_fds=["/dev/nvidia2","/dev/nvidiactl"]`；osmesa 与 egl_mesa 都是 `llvmpipe` + `child_nvidia_fds=[]`）。
- **四条口径改判**：① **主线渲染吞吐一律引用 `11.82×`**（gym-aloha 双臂 3cam 224²、prefix-only）；② **旧 `13.8×`（480×640）降级 `boundary_violated_provenance`，不得再作主线依据**（分辨率不同 + 系统安装态，裁定 46.4/53.6 禁搬）；③ **`egl_mesa` 是负对照且比 osmesa 更慢 ⇒ 主线必须 `MUJOCO_GL=egl` + NVIDIA vendor prefix，任何静默回退到 mesa 的路径都要显式判红**；④ **CPU 时代的"并行度上限 4"在 GPU 渲染下失效**（w2/w4 扩缩效率 0.645/0.596，但绝对吞吐仍涨）⇒ **E3-④ 的"A2 训练并发时"实测出来之前，各线并行度不得超过 2**；建议值由 E 出、D 裁。
- **下游换算**：**`165.65 ÷ 29.4118 Hz = 5.63× 实时（仅渲染）` ⇒ 闭环是否实时现在取决于 π₀.₅ 的推理墙钟，不再取决于渲染**；A2 的 `loop_fps≈10.5`/`0.21× 实时`/`97.66 ms/控制步` 全是 osmesa 口径 ⇒ **作废，在 egl 下重测**，**§2.4 的预算算术分母被换掉，n=25 的占比必须重算**。**S1 采集成本**：300 步/集 在 egl_nvidia 下 **≈1.81 s/集**（osmesa **≈21.4 s/集**）⇒ **20 集 ≈36 s（原 7.1 min）**；**B2 从此受 GPU 申报纪律约束（单卡优先权 A2 > C2 > E > B2）**。
- **单臂/双臂冲突已由裁定 58.1 解决，不是 E 违规**：「只渲单臂」只约束 Piper/Cobot Magic 自有资产线，**主线代理保持 gym-aloha 双臂**；**E 同时测两档是正确做法，两档都保留**。
- **一条缺陷（不 blocking）**：`MANIFEST.json` 的 `boundary_note` 引用 **`docs/e_handoff_to_d_20260929.md §1`，而该文件在仓内不存在**（D 实测 `find . -name '*e_handoff*'` 命中 **0**，搜索面已枚举，符合裁定 50.2）⇒ **悬空引用**。**要求 E 的回流单以该文件名落盘**（含裁定 60.4 的那一句回答 + 违规时间线与回滚自证 + E3 五项逐条结果），否则这条引用永久不可核验。

**裁定 68（C2 的 T-C2-2 补丁验收通过 + 一次未申报的覆写违规 + 新纪律）**
- **采纳（六条依据，D 全部自己核过，不采信自述）**：① `harness/queue_td_learner.py` **+17/−1** 纯加法，新增 `obs_key_contract: ObsKeyContract | None = None`，`None ⇒ derive_contract()`；② **ACT 线旧快照仍绿** —— 闸 G1 实测 `vec_shape=[14]`、**`vec_sha12=4fd32aacc677`** 与打补丁前逐字节相同；③ **π₀.₅ 形态未声明图像键 ⇒ 点名拒绝** —— G3 实测 `refused` 且 `named` 三路图像键齐全、message 逐键列出「存入 4 键、消费 1 键、被静默丢弃的键」；④ **闸 `n_checks=14`、`n_red=0`、`verdict="PASS"`**；⑤ **4 个变异体 `n_ok=4`、`all_ok=true`、每个 `missed_red=[]`/`false_red=[]`，`expected_must_go_red=[G13,G3,G5,G8]` 与 `observed_red_ids` 逐条相同 ⇒ 双向有牙**；⑥ **`harness/contracts.py` 一个字节未动**（D 核 `git status`：只 `queue_td_learner.py` 被改）。**并且 C 线 17 项全量回归 `n_exit0=17/17`**（`c_regression_postpatch/summary.txt`，`21:44:47`）⇒ **裁定 49.2 四条要求全部满足，T-C2-2 实质验收通过。**
- **点名表扬两处设计**：**回归清单不手抄，直接从 `scripts/c_run_all_selfchecks.sh` 用 `sed` 解析 `SCRIPTS=(...)`**（避免两份清单分叉）；**已经意识到"不覆盖 C 的冻结产物"并把 `c_env_manifest.py --check` 的 `--json-out` 改指自己目录**（注释里还写了 C 冻结产物的 mtime 与字节数）。**问题恰恰出在这件事只做了一半。**
- **违规（记一次，未申报）**：**其余自检脚本写 `runs/infra/` 顶层固定路径**（例 `scripts/c_learner_shard_smoke.py:85` `OUT_JSON = ROOT/"runs"/"infra"/"c_learner_shard_smoke.json"`，`:222` `--out` 默认即它）⇒ **21:42:43–21:44:16 覆写了 16 个 C 线产物、无 before 影像**：`c_ledger_selfcheck.json`/`c_obs_selfcheck.json`/`runtime_adapter_selfcheck.json`/`harness_contract_replay.json`/`c_release_selfcheck.json`/`c_golden_conformance.json`/`c_gate_build_observed.jsonl`/`c_verdict_identity_inventory.json`/`c_verdict_selfcheck.json`/`c_run_manifest_selftest.json`/`c_verdict_wiring_selfcheck.json`/`c_t17_goal_conditioning.json`/`c_decisions_registry_selfcheck.json`/`c_lift_contract_smoke.json`/`c_lift_takeover_smoke.json`/`c_learner_shard_smoke.json`。**且 `runs/` 被 `.gitignore:12` 排除 ⇒ 无 git 恢复路径**；这 16 个文件被其它线文书直接引用（`supervisor_memo_20260928.md:331`、`docs/b_handoff_to_c_20260929.md:20`、`docs/c_handoff_to_b_t17_landed_20260929.md:63`、`docs/c_t17_goal_conditioning_20260929.md:162`、`docs/c_golden_conformance_20260928.md:270`）。**D 实测：17 个自检脚本里 14 个写固定路径。**
- **处置**：**结果采纳（回归证据有效），程序违规记一次入台账。损害评估 = 可恢复**：D 已逐条复核被引用的数字在新字节里**全部保留**（`c_learner_shard_smoke.json` 21:44:16：`n_checks=46`、`pass=true`、`bc_anchor_xi0_gap.verdict="substantive_gap"`、`channels_with_gap=["takeover"]`、`takeover bc_rows_at_xi0/bc_rows_total=28/28`、`clean`/`terminal`=`0/0` 且 `ratio=None`（未伪造 0/0）、`representation_version="lift-state-proprio50+obj10-v1"`、`n=4/γ=0.99/H=8`）⇒ 与上述四处文书引用**逐条一致**，**不构成实质证据损失**；**但"原始 C 运行字节"的 mtime 溯源已断，永久登记、不可修复。**
- **升级为纪律 `regression_driver_output_enumeration`**：**任何跨线回归/复核驱动，开工前必须从被调脚本源码里枚举其全部固定路径输出（`grep -oE 'runs/[A-Za-z0-9_./{}-]+\.json'` 之类），逐个改指本线目录或逐个留 before 影像；不许"挑一个最显眼的改掉"。** C2 这次正是挑了一个（而且挑得有道理）而漏了 16 个 ⇒ **"凭判断挑"本身就是错误方法，必须枚举。**
- **补救（不用重跑，只做登记）**：C2 的回流单加一节 `overwritten_c_artifacts`，逐条列 **文件名 / 覆写时刻 / 新 `sha256-12` / 新字节数 / 是否被其它线文书引用（引到哪一行）/ D 的复核结论** ⇒ **这就是这 16 个文件从此以后的新溯源起点。**

**裁定 69（C2 六条自提任务的裁定 + 两条待裁项一并裁完）**
- **T-C2-1（归一化契约层）P0 批**，缺口证据 D 采纳。**D 裁 C2 要的两件事**：① **stats 数据源 = B2 的 S1 仿真双向示范**（**不是** ABC-130k —— YAM stats 属主线禁用，裁定 43.4/52/61；**也不是**单独用 gym-aloha 脚本专家，因为示范要走裁定 66 的 EE-oracle→关节重放路径）；**时刻 = B2 先导 5 集落地即算**，C2 先出**生成器 + 闸 + 变异体**，stats 文件本身等 5 集；② **`norm_map` 口径 = 保留 QUANTILES，但每一维必须有 scale 下限保护、近常量维必须显式标记**；**IDENTITY + 显式缩放作对照分支保留，两案并列报 D，不静默选**。**YAM stats 只能作"必红"分支输入（C2 自己已立此牙，D 确认）。**
- **T-C2-2 验收通过**（裁定 68）；**剩余**：补 `overwritten_c_artifacts` 登记；**闸加一条**：`late_policy=hold` 下**迟到帧不得被重标为 `activated`**（裁定 65-3 附加③）。
- **T-C2-3 P1 批，CPU-only 可立刻做**，但**必须分 CPU/GPU 两档**（裁定 62），**GPU 档用 `11.82×`**；**旧 `13.8×` 已降级，不得再用**；`np.savez` vs `np.savez_compressed` 与内容寻址真实去重率**要实测**（C 的 147 KB/帧是算术推算）；**"video-backed"属接口变更，只报不改**。
- **T-C2-4 P1 批，限时一个工作块**。C2 已实测的三起 D 全部采纳：① B2 的 `G2_rebuild_lockout_not_default[a2env]` **极性/文案反了**（required 写的是红条件，实测 `same_as_0928=False` 是正确的却报 WARN）；② A2 的两个假红，其中 `manifest_run2_dist_drift_false_red` 是 **`torch-2.6.0.dist-info` vs `torch-2.6.0+cu124.dist-info` 的 local tag 差被当成 torch 漂移**；③ B2 的 `A0_teeth_current` 因 `gate_build` 不匹配红过。**新增审点（裁定 57.4）：monkeypatch 类闸必须能判"只改一半"红** —— A2 实测 `gym_aloha/env.py:7`–`:12` 是 `from gym_aloha.constants import DT`，**只 patch `constants.DT` 会静默留在 50 Hz**。
- **T-C2-5 P1 批**：五列齐（+`sha256`/`mtime`/`是否跨断点有效`），**不代 A 表态、不改 A 的文件**；**并加一列 `overwritten_by_c2_regression`**（对照裁定 68 那 16 个文件）。
- **T-C2-6 D 现予裁定，但 C2 不动手**：`registry/verdict_identity.py:47` 的 `GATE_MODULE_PATH` **改为按 `gate_id` 查表**（ACT 冻结基线与 π₀.₅ 新线各一条），**不许再钉单值**；**`registry/` 单写者 = B2 ⇒ 改动由 B2 做**，C2 只提供口径与三个变异体建议（钉死旧值必红 / 查表命中错门禁必红 / 未知 `gate_id` 必红）。
- **`transformers 4.53.3` vs 声明下界 `4.57.1`（B2 的 `V-pi05-1` 红）—— 采纳 C2 的建议，改判这条闸**：那个下界是 lerobot 的**声明值不是实测必要值**，而 A2 已用 **812/812 张量逐位相同 + 无随机初始化键**（`verdict="all_bitwise_equal"`、`n_model_keys_not_covered_by_ckpt=0`）证明 4.53.3 下加载正确 ⇒ **required 改为「`transformers.__version__` 实测值 + git commit `dcddb970176382c0fcf4521b0c0e6fc15894dfe0` + `all_bitwise_equal`」；声明下界 `>=4.57.1` 标 `declared_only`、不得 blocking**（裁定 9.1 `redline_provenance_discipline`）。**落地由 B2 做。**
- **`V-pi05-3` 渠道混用 `['hf_mirror','modelscope']` —— 采纳，按格式闭合、不重下**：顶层 `channel` 填 **`mixed`**，逐文件渠道以 receipt 为准（A2 的 `weights_receipt_channel_sidecar.json`，receipt 未重写、`sha256` 前后一致 `11267d5b…`）。

**裁定 69.1（B6 销账 + 新的一次代提交要求）**：`git log -1` = **`c422659`**（21:2x，B2 代提交）⇒ **B6 关闭**。**21:2x 后又脏 23 项**（D 的 6 份文书追加、C2 的 `harness/queue_td_learner.py` +17/−1 与 `harness/obs_key_coverage.py`、A2/B2/C2/E 的 11 个新脚本、`tmp/`）⇒ **本轮结束后 B2 再代提交一次**，提交信息须注明 **`runs/` 被 `.gitignore:12` 排除 ⇒ E 的渲染证据、B2 的 probe 产物、C2 的闸产物只在 NFS，不进 git**。

**裁定 69.2（新增前置阅读）**：**A2 与 C2 在 S6 开工前都必须读 `RL_Harness_v4_20260924/materials/06_三轮递进调研与方案复审_20260923/appendices/02_异步动作时间轴与学习目标.md`** —— 附录一 `:109` 明写「精确状态、时间与价值定义遵循 [异步附录](02_异步动作时间轴与学习目标.md)」⇒ **TD 样本的时序前提以它为准，不以 D 或 A2 的转述为准**。**D 已核实该文件存在。**

---

# 增补二十三（2026-09-29 22:2x，D）：前缀路径事实错误（A2+E 双证人）· 三个主线渲染数字互相冲突（D 第七次同型）· 静默窗口制度 · A2 提的两条规则升为全仓纪律 · n=25 由实测支撑

> **触发**：D 在 22:1x 巡检时发现 A2 与 E **都在跑活作业**（A2 `closed_loop --n-action-steps 50,25` PID 559213 起于 22:16；E `e_mainline_render_calib.py --workers 1,2,4,8` PID 547802 起于 22:14），并因此暴露出三件必须当场处置的事。

**裁定 70（渲染前缀目录名：D 的文书写错了，A2 与 E 双证人）**
- **D 的裁定 59.4 与断点文件 §3 写的前缀 `.codex-persist/nvidia-gl-590.48.01/` 不存在**（D 实测 `stat` → `No such file or directory`；`.codex-persist/` 下实际只有 `backup/ bin/ egl-libs/ envs/ hf-cache/ maniskill-assets/ pip-cache/ piper-assets/ sapien-cache/ uv-cache/`）。
- **正确前缀 = `/workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/.codex-persist/egl-libs/590.48.01/`**（含 `10_nvidia.json` 21:22:26 + `libEGL_nvidia.so.590.48.01`/`libGLX_nvidia.so.590.48.01`/`libnvidia-eglcore`/`libnvidia-glcore`/`libnvidia-glsi`/`libnvidia-gpucomp`/`libnvidia-tls` 等，符号链接齐全）。
- **E 的实现是对的、D 的文书是错的**（`scripts/e_egl_probe.py:53` 定义的就是正确路径；`e_activate_gpu_render.sh` 的 `e_resolve_prefix` 两个候选名都试）。**A2 独立复核为第二证人。**
- **处置**：**逐份点名更正**（断点文件 §3、`d_handoff_to_a2` §14、`d_handoff_to_b2` §12/§14.1、`d_handoff_to_c2` §9/§11.1、`d_simchain_e2emin` §10.4）。**并立规范：全线一律以 `scripts/e_activate_gpu_render.sh` 的解析结果为唯一权威，不许硬编码目录名**（A2 本轮的做法：`eval "$(bash scripts/e_activate_gpu_render.sh --print)"`）。**产物必须落 `activation_env` + `prefix_paths_verified` 三条布尔（`prefix_in_ld_library_path` / `vendor_json_points_into_prefix` / `vendor_json_exists`）—— A2 的格式为范例。**
- **`scripts/e_activate_gpu_render.sh`（21:54:06，5232 B，可执行）与 `scripts/e_activate_selfcheck.py`（21:53:44）D 已核到落盘 ⇒ E3-① 销账**（D 在 21:47 查过一次说"未落盘"，**是 D 查得太早，不是 E 的问题**）。

**裁定 71（三个"主线渲染口径"数字互相冲突 —— **D 第七次同型事故：同一轮里写下禁令又违反它**）**
- **D 实读到三个自称同口径的数**（gym-aloha 双臂 3cam 224² egl_nvidia）：

| 来源 | 数字 | `loadavg_1m` | `DT`/子步 | 协议 |
|---|---|---|---|---|
| **E** `ab_gym_aloha_20260929_214002.json` | **165.65 ctrl-steps/s（自称 `11.82×`）** | 47.49→50.08 | **未用 shim（stock `DT=0.02`/10 子步）** | `bench_seconds=5.0`、reps=3、render_only |
| **A2 run1**（22:08，已归档 `gpu_run1_two_a2_defects/`） | **30.522 `env_step_fps`** | **67.36→71.98** | **shim `DT=0.034`/17 子步** | `n_steps=100` |
| **A2 run2**（22:16:55，`gates_all_ok=True`） | **65.865 `env_step_fps`** | **51.4→51.4** | **shim `DT=0.034`/17 子步** | `n_steps=100` |

- **D 的错误**：D 在 `d_handoff_to_a2` §15.6 与 `d_simchain_e2emin` §10.4 里**用 E 的 `165.65` 算出"`165.65 ÷ 29.4118 = 5.63× 实时`"与"S1 采集 300 步/集 ≈1.81 s、20 集 ≈36 s"** ⇒ **把 (stock DT, 5 s 窗口, loadavg 47–50) 搬进主线的 (shim DT=0.034/17 子步, 100 步, loadavg 51–72)，正是裁定 46.4/53.3/53.6 明禁的跨口径搬运。**
- **裁定**：① **E3-③ 落地前不得声明任何单一"主线渲染口径"数值**；**`11.82×` 与 `5.63× 实时` 一律降级 `protocol_mismatched_not_mainline`**。② **规划一律用保守端**：**`env_step_fps=30.522` ⇒ 300 步/集 ≈9.83 s ⇒ 先导 5 集 ≈49 s、正式 20 集 ≈3.3 min**；**较低负载端（`65.865`）⇒ 20 集 ≈1.5 min**；**osmesa 同口径（`9.577`）⇒ 20 集 ≈10.4 min（越过 GPU 申报门槛 ⇒ 不要用 osmesa 采主线示范）**。**两个负载端必须并列，不许只报好看的。** ③ **负载摆动是实测事实**：`loadavg_1m` 在 21:5x–22:1x 一小时内 **37.58 → 71.98**（12 核 cgroup 配额，宿主 112 核与其它租户共享），**同一口径差 2.16× 已实测** ⇒ **任何吞吐数字都是负载条件量，必须成对带 `loadavg` 三点 + `nr_throttled` 增量；"单点数字"本身不该被当口径。** ④ **E3-③（`scripts/e_mainline_render_calib.py`，扫 `egl_nvidia/osmesa × workers 1/2/4/8 × reps 2` 且带 `--cotenant proxy_a2` 臂）是指定的对账仪器**，但**必须在静默窗口内重跑才有效**（当前这一轮已被 A2 的 22:16 作业污染）。
- **定性**：**D 第七次同型**。本次的新形态是"**在自己写下禁令的同一轮里违反它**"⇒ 说明该纪律需要**机械化检查点**，不能只靠自觉：**凡把一个数字用于新的 (venv, 后端, 模型, 环境, DT, 协议, 负载) 组合前，必须逐维列出该数字的原组合与目标组合并逐项比对，任一维不同即不得搬用。**（已并入 `caliber_transplant_ban` 的执行形式。）

**裁定 72（A2 提的两条规则 D 全部采纳，升为全仓纪律；A2 run1 两处假红的处置验收）**
- **规则 A ⇒ 纪律 `renderer_identity_evidence_discipline`**：**`MUJOCO_GL` 只表达意图，`GL_RENDERER` 才表达事实**；**任何渲染相关的吞吐/延迟/图像数字，产物里必须落 `GL_VENDOR`+`GL_RENDERER`+`GL_VERSION` 三条原文 + `renderer_class` + `identity_source`（取法）**；**只记环境变量的一律标 `declared_only`，不得作口径依据。**
  - **A2 的机器化回溯标注 = 这条纪律的正确用法，D 验收**：`latency_retro_label_no_prefix.json` 实测同一组环境配置（`MUJOCO_GL=egl`、无 prefix、系统 ICD 只有 mesa）下 `GL_RENDERER="llvmpipe (LLVM 15.0.7, 256 bits)"`、`renderer_class="mesa_cpu_software"` ⇒ **`retro_label.valid=true`**，**G3 的 `loop_fps≈10.39`/`env_step_fps 11.91` 确证为 CPU(mesa) 口径**；**并如实记 `limits`「这是同配置复现，不是对 19:24 那个进程的直接观测（当时没记 GL 身份，无法回溯取证）」⇒ 该限定一并采纳，引用者必须带上。⇒ D 等待项 ② 销账。**
- **规则 B ⇒ 纪律 `selftest_must_execute_acquisition_path`**：**任何闸的 `--selftest` 必须至少有一案真的执行"取数路径"本身（构造真实对象、真的调用那个会失败的函数），不许只把理想字符串喂给闸函数。**
  - **实证**：A2 的 `--selftest` 当时 **9/9 全绿**，但**没有一案真的执行过 GL 身份取数**（M3 只把伪造字符串喂给闸函数）⇒ **toy XML 非法（`worldbody` 直接挂 `<joint type="free"/>`）导致 `mujoco` 抛 `XML Error`、`glGetString` 返回 NULL、第一臂假红，而自检完全看不见**。**与 C 线 `daily_report.md:3740` 段「库自检全绿 ≠ 工具可用（CLI 面没被测）」同族同向 ⇒ 两条合并，并列为 C2 T-C2-4 的新增审点。**
- **A2 run1 两处假红的处置 = 本仓最好的一次假红处置，D 建议 B2/C2 照抄格式**：两份 JSON **保留不删不改写**（裁定 35.1）、`WHY_ARCHIVED.md` 逐条说明假红根因与"数据有效"的边界、明确「引用结论请用 run2 及以后，但单独引用 run1 的延迟数字允许，只要同时说明那两道闸的假红原因」、**并主动把 run1 定位成 run2 的重复性对照**。
  - **缺陷 1 `retro_label_valid`（适用性缺陷）**：脚本对任何 `--mode env_only` 臂都发该闸，但它只在**未激活 prefix** 那一臂成立 ⇒ **GPU 臂必然红**。A2 修法 `retro_pending = not act["nvidia_prefix_active"]`，run2 已验证 `gates_all_ok=True`（5 道闸全绿，D 实读）。**D 把它归为缺陷类「闸在它不适用的臂上开火（applicability defect）」，要求：每道闸必须声明 `applies_when`，不适用时输出 `n_a` + 理由，而不是 `ok=false`。**
  - **缺陷 2 `tied_weight`（键名带 `model.` 前缀）**：A2 用 ckpt/`__metadata__` 的裸键名查 `PI05Policy.state_dict()`，而 lerobot 0.4.4 的键带 `model.` 前缀；**读法出处 `scripts/a2_verify_pi05_load.py:118`–`:126` 是 A2 自己 18:0x 写的、这次没去读**。⇒ **D 升为纪律 `self_artifact_reuse_discipline`：复用自己在更早时段写下的读法/键名/路径/口径时，必须重读一次原文并留 `(file:line, mtime)`；"我记得我写过"不算证据。** **本日已有两起同型：A2 的 `tied_weight` 键名、D 自己的前缀目录名（裁定 70）—— 两者都是"引用自己先前的结论而没重读"。**

**裁定 73（并发治理：静默窗口制度 + 优先权当场执行）**
- **D 实测到的冲突（`ps`，22:17:48）**：**E 的权威标定臂起于 22:14，A2 的 π₀.₅ 闭环 GPU 作业起于 22:16 ⇒ A2 正在污染 E 的"无 cotenant 权威臂"**；而**单卡优先权 A2 > C2 > E > B2 ⇒ A2 不让，让的是 E**。
- **处置令（已发 E）**：① **不得 kill A2 的作业**（它有优先权，且它测的 `--n-action-steps 50,25` 正是裁定 65-1 的验证输入）；② **E 当前这一轮的无 cotenant 权威臂标 `contaminated_by_cotenant=true`，不得作主线口径权威值**；③ **A2 作业结束后（`nvidia-smi` 回 0 MiB/无进程）E 重跑权威臂，并在 `daily_report.md` 事前申报静默窗口**；④ **E 的 `--cotenant proxy_a2` 臂照常跑，并把它与静默窗口臂的差值单独报出 —— 这个差值就是 D 要的"A2 训练并发时的吞吐损失"，是并行度建议值的直接依据**。
- **判据（必须有牙、能红）**：**每个臂的产物都要落 `cotenant_evidence`** = 臂开始与结束时刻的 `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` **原文** + `ps` 里**非本线进程**清单；**若臂的时间窗内存在任何非本线 GPU 进程，或 `loadavg_1m` 比臂开始前高 ≥5 ⇒ 该臂自动标 `contaminated`，不得被任何文书当权威口径引用。**
- **静默窗口制度（新治理项）**：**凡"要成为权威口径"的标定测量必须在申报过的静默窗口内做** —— 申报（`daily_report.md`：线/起止/需要的排他资源/预计时长/可否被打断）→ **D 按单卡优先权与关键路径排窗，冲突时先让关键路径** → 窗口内其它线不起 GPU 或 `--workers>1` 的 CPU 作业（必须做的先报 D）→ 产物落 `quiet_window=true` + 窗口申报行号 + 臂内 `loadavg` 三点与 `nr_throttled` 增量。**窗口外测的一律标 `contaminated_by_cotenant`，可作趋势参考、不得作权威口径。**
- **更正 D 自己（并行度上限的适用范围写窄了）**：D 在 `d_handoff_to_e` §9.2-④ 写「E3-④ 实测前各线并行度不得超过 2」——**准确表述是：该上限约束 A2/B2/C2 的生产性作业（采数据、训练、评测），不约束 E 的并行度标定测量本身（其任务书 E3-④ 明确要求扫 1/2/4/8，照扫）**；**但 E 的扫描本身会制造负载 ⇒ 必须在静默窗口内做，否则测的是"别人干扰下的扩缩效率"。**
- **A2 的 GPU 申报（22:0x：做什么/激活方式/预算 15–25 min/显存 <15 GB/单进程、不开多进程渲染/不采成功率/可随时 kill/跑完销账/起点 `nvidia-smi` 0 MiB 与 `nr_throttled 3726→3819`、`loadavg 53.71/50.64/49.66 → 37.58/37.68/40.63`）格式完全合规 ⇒ D 采纳为全仓申报模板。**

**裁定 74（`n_replan=25` 的依据从"算术外推"升级为"实测"；裁定 65-1 维持不变）**
- **A2 run1 的 π₀.₅ 闭环实测（D 实读 `gpu_run1_two_a2_defects/latency_mainline_egl_gpu_pi05.json`）**：

| 档 | `mean_loop_fps` | 每控制步墙钟 | 每 chunk 墙钟 | 对 `34.0 ms × n` 的预算占比 | 判定 |
|---|---|---|---|---|---|
| **`n=50`** | **59.176** | 16.90 ms | 845 ms | 845/1700 = **49.7%** | 实时可行，**但违反 v4 `H≥2n`，不能用** |
| **`n=25`** | **38.055** | 26.28 ms | 657 ms | 657/850 = **77.3%** | **实时可行，余量 22.7%** |

- **⇒ A2 §2.4 外推的 `61.6% / 余量 38.5%` 是乐观的，实测是 `77.3% / 余量 22.7%`（差 15.7 个百分点）。A2 把它标成 `proposed_from_g3_measurement` 并要求 S4 重测，这一步救了它 —— 否则 D 会拿一个错 15.7 个百分点的余量去排 P4 实机。**
- **⇒ 裁定 65-1（`n=25`）维持不变，且依据更稳**：**D 裁 n=25 的依据从来不是延迟，而是 v4 附录一（`aae20ffe604f`）`:103` 的 `H≥2n` 合规**（n=50 时 E=`[50,100)`、D=`[50,50)` 双空 ⇒ 三槽退化）；**延迟实测只确认可行 ⇒ 这条裁定对延迟数字不敏感，run2 即使把余量再压低也不动 n=25。**
- **证据等级**：run1 的两道闸是假红（A2 已逐条说明），**延迟数据本身有效**，run2 用同一口径重测 ⇒ **当前标 `provisional_from_archived_run1`，run2 落地后由 D 改标 `measured_run2` 并把两个数字并列**。**并且 77.3% 是在 `loadavg 67–72`（本日最忙）下测的 ⇒ 是保守端；必须等 run2 的较低负载值并列报，不许只报好看的。**

---

# 增补二十四（2026-09-29 23:0x）｜裁定 75–81：**全文在 `work/decisions/decisions_20260929.md`（1266→1419 ln，sha256-12 `5ab60141fa06`）；本节只做编号锚点与要点，避免两处正文分叉**

**为什么本节从简**：裁定 75–81 的完整正文（含全部实测数值、负载对、文件身份三元组、可推翻条件）已一次性写入 `work/decisions/decisions_20260929.md`，各线可执行动作项已分别写入四份执行单（`d_handoff_to_a2` §17 / `_b2` §15 / `_c2` §12 / `_e` §11），重启续跑入口已写入 `d_context_checkpoint_20260929_2130.md` **§14**（取代 §13.2/§13.4/§13.5/§13.6/§13.7）。**在备忘录里再抄一遍全文会造成三处正文，违反「同一事实只有一处权威」的口径纪律** ⇒ 本节只留编号锚点。

## 编号锚点（裁定号 → 一句话 → 权威正文位置）

| 裁定 | 一句话 | 权威正文 |
|---|---|---|
| **75** | A2 的「n=25 超预算 1.218×」= **同步串行环口径**（D 独立核算：各分量严格相加 = `episode_wall_s` ⇒ 零重叠），而 v4 `:103` 的 `H≥2n` 本是**异步**条件 ⇒ **`n_replan=25` 维持**；预算改**软约束 + `overload_flag`**（P4 真机不适用）；**异步实测前禁写「实时闭环」**；**E 的「2.1× 余量」属 n=50 摊薄、搬到 n=25 的真实值是余量 2.6%** | `decisions_20260929.md` 裁定 75；参数表 `timing.slot_n` / `timing.per_control_step_budget_note` / `timing.inference_latency_measurements_mainline_dt0034` |
| **76** | A2 run2 与 E 的 4 个 `proxy_a2` 批次 **互相污染** ⇒ 两者均非权威（A2 权威端 = run1；E 权威轮 = `summary_20260929_221443.json`）；**责任在 E**（应让路），E 已改批级闸 ⇒ **`per_batch_gpu_yield_gate`**；A2 的 `collected_at_run_time=false` ⇒ **`cotenant_evidence_must_be_runtime`**；**强制 quiet-window 权威重测** | 裁定 76；参数表 `rendering.mainline_render_caliber_E3` |
| **77** | E 回流单 9 项逐条裁（**E 欠账已清**）：CPU 权威基线 **12.88**、`workers_cap` **分场景 4/8**、后端 **egl+prefix-only**、平台申请降级、**不需补单臂数字**、**改文书不改目录**（prefix = `.codex-persist/egl-libs/590.48.01/`）、五项产物全留、授权加一行指针、**`check_gpu_render.py` 保持冻结** | 裁定 77；参数表 `rendering.backend` / `rendering.parallelism_cap` / `rendering.cpu_baseline_authoritative` |
| **78** | C2 的 T-C2-4 审计**接受**；**C2-4「假绿（变异体 import 到未变异旧副本）」是本轮全仓最有价值发现** ⇒ **`mutant_construction_isolation`**；三条上报裁完（最小公共 schema + `UNJUDGED` 计入非绿 / 委托闸补 45 条 `id` + 去前导空格 / **恒真闸降级为清单核对**）；**C2 的 D1 读码证实裁定 69**（装 `>=4.57.1` 会让 π₀.₅ 加载失败）；D3 两个图像体积口径分开登记；**D 亲自复跑 C2 的 env 闸门 offline = PASS/15/red=[]**；**78.11 文件身份时序问题** ⇒ **`citation_sha_as_of_discipline`** | 裁定 78；参数表 `operations.minimal_common_check_schema` / `always_true_gate_downgrade_rule` / `false_red_archival_format` / `rendering.env_contract_module_C2` |
| **79** | C2 的 **event2（第二次未申报覆写）**接受登记 ⇒ **裁定 68 的账本已交付**；根因 = **未加引号 heredoc ⇒ 任意代码执行** ⇒ **`heredoc_quoting_discipline`（红线）**；**整改判定闭合**（守卫版驱动 `3ba62c9567e9` + 自检 4/4，**D 22:45:24 实时核验无第三次事件**）；`regression_driver_output_enumeration` **升格红线** | 裁定 79；参数表 `operations.heredoc_quoting_discipline` / `regression_driver_output_enumeration` |
| **80** | B2 双向专家 **80/80**（**D 逐行复核、不采信 `summary`**）⇒ **D-H1 证实**（`vx300s_right.xml:3` `euler="0 0 3.1416"`）；**B2 的 plan-then-replay 雅可比 IK 路线优于裁定 66 ⇒ D 更正自己的原判、EE oracle 步骤作废**；新纪律 **`actuator_dynamics_before_control_law`**；**这是自验不是正式采集**（5 项缺口）；**唯一真阻塞已转移到「S1 正式采集」** | 裁定 80；参数表 `task.s1_demo_route` / `task.s1_expert_selfverify_status` |
| **81** | **命令 B2 在开始 S1 pilot 之前先代提交 git**（脏项 ~23 → **39**）；⚠ **`runs/` 被 `.gitignore:12` 排除 ⇒ NFS 是服务器重启后唯一证据载体** | 裁定 81 |

## 本轮 D 的自我更正（**必须显式记账，不得因为 D-H1 被证实而省略**）

1. **更正裁定 66 的「EE 模型只作 IK oracle」步骤 ⇒ 作废。** B2 的做法（在部署 env 自己的 `MjData` 上做 plan-then-replay 雅可比 IK）**更好地满足了裁定 66 的意图且少一层机器**。裁定 66 的其余各条继续有效。**这是「下位纠正 D」通道本轮的第二个成功实例**（第一个是 E 的 4-6 指出 D 的 prefix 路径错误）。
2. **D 的第 6 次同型错误仍记账**（裁定 66 段「weld 能解决」被 B2 的 probe2 证伪），**与同一轮里 D-H1 被 probe4 证实并存** ⇒ **结论：D 的推断必须先标 `d_inference_not_measured` 再交下游测，这一程序是有效的（本轮它同时产生了 1 次证伪与 1 次证实），不得因为证实了就省略标记。**
3. **D 的第 7 次同型错误继续记账**（裁定 71 段：在自己写下 `caliber_transplant_ban` 的同一轮里违反它）⇒ **本轮 75.6 正是该禁令的正确适用**（拦住 E 把 n=50 摊薄数搬到 n=25 主线）。
4. **D 的文书错误两处由 D 更正**：prefix 路径（裁定 70 更正、77.6 固化为 `.codex-persist/egl-libs/590.48.01/`）；`/dev/dri` 那条（77.4，本机 `drm_device_file=null` 已证伪「必须挂 /dev/dri」）。

## 需用户裁的 4 个分叉（D 已按「建议值 + 可推翻条件」暂行，全文见断点 §14.8）

① `parallel_eval_workers_cap` 若必须是单一常数取 4 还是 8；② 是否向平台申请 `NVIDIA_DRIVER_CAPABILITIES=graphics`（D 已降级为非阻塞改善项，**申请动作本身要用户点头**）；③ bf16 是否投入测试（改数值口径 ⇒ 影响所有已留档数字的可比性）；④ 是否要为 E 排 5 分钟稳态并发窗口（**D 目前不排**，主线阻塞不在这里）。
