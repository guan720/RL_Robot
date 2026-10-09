# C2 · T-C2-4 跨线闸极性与变异审计（限时版，2026-09-29 21:4x–22:0x）

**性质**：**纯只读**审计。C2 **没有改任何人的闸**（裁定 49.3 边界）；发现问题报 D 与所属线。
**范围（裁定 54 / §6 限时）**：只审「当前在长的 4 把新闸 + S1–S6 新闸」，**不做全仓历史普查**。
**作者**：C2。**写入面**：本文件（`docs/c2_*`）+ 共享文书追加。
**纪律**：每条计数/存在性主张同批带 `(mtime, 计数, 命令原文)`（裁定 50.1 / 51.2）；
外部事实一律 `external_unverified`；只有声明值支撑的标 `declared_only`，不作 blocking。

---

## §0 审计方法与可复核命令

判定「极性」的操作性定义（不是读文案，是读**产物字段**）：

| 概念 | 本审计的判据 |
|---|---|
| **恒真闸** | 在全部可得历史里从未出现过非绿状态，**且**没有变异体记录能把它打红 |
| **假红（false RED）** | 真环境/真数据被判红，事后证明是**判据写错**（有留档说明或自纠记录） |
| **假绿（false GREEN）** | 变异体本该被打红却没被打红，或判据在缺失输入时静默放行 |
| **极性错** | 判据方向与业务意图相反（把正常数据判红 / 把异常判绿） |

可复核命令（本轮实跑，输出已引在下面各条）：

```bash
# 1) B2 准入闸的全部历史 + 当前，按 status 直方图枚举（不靠"我记得"）
python - <<'PY'
import json,glob,os,collections
for p in sorted(glob.glob("runs/vla/b2_env_admission_20260929/**/delegated_*.json",recursive=True)):
    ...
PY
# 2) A2 环境 manifest 的 assertions 结构与取值
python -c "import json;a=json.load(open('runs/vla/a2_env_pi05_sim_20260929/env_manifest.json'))['assertions'];print(len(a),all(a.values()))"
```

**本轮机器口径**（每个数值主张同批落）：`loadavg 34.62 / 37.74 / 43.05`、
`nr_throttled` 见各产物 JSON 的 `machine_before/machine_after`、
并行度分母 = **12 核 cgroup 配额**（`cpu.cfs_quota_us=1200000`），**不是** `nproc=112`。

---

## §1 当前在长的 4 把闸（逐闸六列）

### 1.1 B2 · π₀.₅ 环境可复现性准入闸 `scripts/b2_env_admission_pi05.py`

| 列 | 实测 |
|---|---|
| **闸 id / 产物** | `admission_verdict.json`（当前 81205 B，mtime **09-29 21:13:01**，`gate_build=912b5b027e5d`） |
| **required 文案** | **有**：每条 check 带 `required` + `red_when` + `ruling_ref`（8 字段：`id/ok/observed/required/note/status/ruling_ref/red_when`）⇒ 本仓**最完整**的一把 |
| **判定极性** | 主判据极性**正确**（缺依赖/身份不符 ⇒ RED）。**但存在一处 WARN 极性错**（见 §3-F3，D 已独立复核成立） |
| **双向变异体** | **有，且是本仓最强的**：`mutation_verdict.json`（76871 B，mtime **21:07:55**）`n_mutations=60 / n_ok=60 / all_ok=true / n_reverse=18 / baseline_all_green=true` |
| **恒真/恒假** | 主体**非恒真**（run2/run3/current 都有真 RED）。**但它委托的两把子闸恒真**（见 §1.3 / §1.4） |
| **最近一次真实变红** | **21:13:01（current）**：`V-pi05-1_version_anchor` RED（裁定 48.4 的 transformers 重锚未完成）+ `V-pi05-3_channel_provenance` RED（渠道字段 `mixed` 未填）。历史：**run3 18:44:46** 同两条；**run2 18:28:42** `V-pi05-2_weights_identity` + `V-pi05-3`；**run1 17:44:29** `ok=false` 但 **0 条 status=RED**（见 §3-F1） |
| **状态词表** | `PASS / WARN / RED / UNJUDGED` 四档（run1 直方图 `{'PASS': 18, 'UNJUDGED': 5}`；current `{'PASS': 28, 'WARN': 2, 'RED': 2}` = 32 条） |

### 1.2 A2 · 环境 manifest 闸 `scripts/a2_env_manifest.py`

| 列 | 实测 |
|---|---|
| **闸 id / 产物** | `runs/vla/a2_env_pi05_sim_20260929/env_manifest.json`（30506 B，mtime **09-29 20:51:16**） |
| **required 文案** | **半有**：`assertions` 是 **`dict[str,bool]`，10 条**（V1…V10），**键名自带口径**（如 `V3_torch_version_redline_2_6_0_cu124`），但**没有** `required`/`red_when` 字段；`verdict.blocked_if` 有一句汇总（「V5/V10 红 ⇒ π₀.₅ 无法 from_pretrained」） |
| **判定极性** | **发生过一次真假红**（V10 的 c6 判据把 PEP 610 的裸 VCS URL 当不符 ⇒ 真环境被判红），A2 已自纠并加 6 变异体自检 6/6（见 §3-F4） |
| **双向变异体** | **有**：`--selftest` 6 变异体，`WHY_ARCHIVED.md` 记「6/6 全抓，M1 = 本轮真实 blocker 状态」。`kind=declared_only`（C2 **未复跑**该 selftest，只读留档；复跑需 A2 的 venv 与网络口径） |
| **恒真/恒假** | 当前 `all(assertions.values()) == true`（10/10）⇒ **此刻是恒真状态**。是否**结构性恒真**取决于变异体，C2 未复跑 ⇒ 标 `declared_only`，**不下"恒真闸"结论** |
| **最近一次真实变红** | **20:50:14**（`manifest_run3_v10_pep610_false_red/`，`V10=false`、`env_usable=false`）—— 但它是**假红**（判据错），不是环境红。真环境红：**未见留档**（run1/run2 两个 `*_false_red` 目录**没有** `WHY_ARCHIVED.md`，见 §3-F5） |

### 1.3 委托闸 G1–G5（`delegated_g1_g5_freeze.json` / `delegated_g1_g5_a2env.json`）

| 列 | 实测 |
|---|---|
| **产物** | `delegated_g1_g5_freeze.json`（6322 B，21:13:00）、`delegated_g1_g5_a2env.json`（7237 B，21:13:00） |
| **required 文案** | **无**：check 只有 `{id, status, ok, note}`，且 `note` 全为空串 |
| **判定极性** | 无法从产物判定（没有 required/red_when）⇒ **标 `undeclared`** |
| **双向变异体** | **未见**（产物内无变异记录） |
| **恒真/恒假** | **`freeze` 那把是恒真闸**：跨 **5 份**产物、**25/25 条**全 `PASS`，`ever_red=False`、`ever_warn=False`。`a2env` 那把 **16 PASS + 4 WARN**、`ever_red=False` |
| **最近一次真实变红** | **从未变红**（在全部可得历史里）⇒ 按 D 的要求**单独标出**（见 §4） |
| **额外缺陷** | **20/20 条 check 的 `id` 是 `null`、`ok` 也是 `null`**（`freeze` 25/25 同样）⇒ 无法按 id 引用某一条；任何按 `ok is True` 过滤的下游会把 PASS 读成"不合格"（见 §3-F2） |

### 1.4 委托闸 V0–V9（`delegated_v0_v9.json`）

| 列 | 实测 |
|---|---|
| **产物** | 4358 B，mtime **21:13:01**；顶层还有 `red_conditions` / `conclusion` / `baseline_constants` / `gate_build_expected` |
| **required 文案** | **有**：每条 `{id, ok, observed, required, note}`，例：`V2.required="门禁回归 157/157 断言、39 用例全过"`、`observed="ok=True n_asserts=157 n_asserts_ok=157 n_cases=39"` ⇒ **observed/required 成对**，可核 |
| **判定极性** | 正确（`ok` 布尔 + 顶层 `red_conditions` 显式写明何时红） |
| **双向变异体** | **间接有**：`V3.required="门禁变异 15/15 被抓住（基线全绿 + 无漏判）"`、`observed="all_ok=True baseline_all_green=True n_mutations=15 n_caught=15"` ⇒ V0–V9 是**对另一把闸（B 的门禁）变异结果的转述**，本身不带变异体 |
| **恒真/恒假** | 跨 **5 份**产物、**50/50 条** `ok=true` ⇒ **在可得历史里从未变红**（§4）。注意：它的 `checks` **没有 `status` 字段**（50/50 为 `None`）⇒ 按 `status` 汇总的下游会把这 10 条整体读成"无状态"（见 §3-F6） |
| **最近一次真实变红** | **从未变红** |

---

## §2 S1–S6 的新闸（含 **C2 自审**）

| 段 | owner | 闸 | 状态 | 极性/变异实测 |
|---|---|---|---|---|
| S1 示范数据 | B2 | 尚未见产物（`runs/vla/b2_sim_demo_bidir_20260930/` 不存在） | **未实施** | 无可审对象。C2 提醒：S1 出口判据第 5 条已写明三个变异体（DT 改回 0.02 / 反向判据方向写反 / 随机动作当示范），**落地时必须三个都跑**，否则专家自证闸有恒真风险 |
| S2 stats | C2 | 尚未落地（**入口卡在 S1 的 ≥5 集**） | **未实施** | 见回流单的待裁项（scale 下限两候选、clip 比例上限） |
| S3 BC/SFT | A2 | 尚未见产物 | **未实施** | 出口判据第 2 条要求"检查全部缺失/多余参数键、不许以『加载未报错』为绿"⇒ 与 §3-F7 的 `modeling_pi05.py:995`–`:998` 直接相关，**落地时必须显式覆盖** |
| S4 接线 · **B3 键覆盖闸** | **C2** | `scripts/c2_gate_obs_key_coverage.py`（sha256-12 `e078adbe4f38`）+ `runs/vla/c2_obs_key_whitelist_20260929/gate_20260929/` | **回放通过** | baseline **14/14 PASS**；**4 个文件级变异体 4/4 被抓住、0 假红**（M1 `check_coverage→evaluate_coverage`、M2 吞异常、M3 键名写死、M4 `covered=True` 恒真）；1 个输入级反向变异 R1（required 降 optional ⇒ G5 的牙失效，**符合预期**） |
| S4 接线 · **B4 env 闸** | **C2** | `scripts/c2_gate_env_gym_aloha.py`（sha256-12 `f5131349c60e`）+ `runs/vla/c2_env_gym_aloha_20260929/` | **离线：回放通过；在线：仿真通过（不含能力主张）** | offline **14/14 PASS**（CPU-only，不占 GPU）；online **9/9 PASS**（`MUJOCO_GL=egl`，实测 3.5 s，`nr_throttled_delta=2`）；3 个反向变异：J11（`hold_min_steps=0` ⇒ 反 flick 的牙失效）、J12（`target_side` 写死 ⇒ 方向判定翻转）、E6（`dt=0.02` ⇒ 构造被拒） |
| S5 评测 / S6 RL | A2/B2 | 尚未见产物 | **未实施** | 无可审对象 |

### 2.1 C2 自审：本轮**我自己的闸/探针出过 4 次缺陷**（3 假红 + 1 假绿）

这条是本次审计里**最该被看见的**——审计别人之前先审自己，否则极性审计本身就是一把恒真闸。

| # | 缺陷 | 方向 | 证据（全部留档，未删除） |
|---|---|---|---|
| C2-1 | 探针的**正向对照钉死在 π₀.₅ 变体**上；补丁生效后那些变体先被拒绝、跑不到逐键敏感度 ⇒ 对照取不到证据 ⇒ 判 `PROBE_INVALID`（**假红**），且 `--selftest` 直接 `KeyError` 崩 | 假红 | `runs/vla/c2_obs_key_whitelist_20260929/probe_20260929_postfix_run1_probe_invalid/WHY_ARCHIVED.md` |
| C2-2 | 闸的 **G12** 把 `message` 混进 `measured` 字段 ⇒ 与 `expected` 的 dict 相等判定必然失败（**假红**） | 假红 | 修法：只比较 `{raised, type}`，`message` 移进 `evidence`（`scripts/c2_gate_obs_key_coverage.py`） |
| C2-3 | env 闸的夹具把离桌高度放在**阈值边界**（`0.30-0.25 = 0.04999999999999999 < 0.05`）⇒ J1/J2/J5/J11/J12 **五条一起假红** | 假红 | 修法：夹具改用二进制可精确表示的值（0.25/0.375/0.125），并**新增 J14 显式测 `>=` 边界语义** |
| C2-4 | **变异体构造器**：重跑时若旧 `harness` 副本已存在，改名后子进程仍会 `import` 到**未变异的旧副本** ⇒ 变异体静默失效 = **假绿（牙不咬）** | **假绿** | 修法：每次跑用全新 `run_<时间戳>` 目录；旧副本存在时**响亮拒绝**而不是改名（`build_mutant` 返回 `ok=false` + 理由） |

**定性**：C2-4 比前三条严重——假红会被人发现，**假绿不会**。这与 §3-F7 同族（"未报错"型判据恒真）。

---

## §3 发现清单（每条带出处，**不改任何人的文件**）

### F1 · B2 闸：`ok=false` 可以在**零条 RED** 的情况下发生（词表风险）
`history/run1_20260929T1736_a2_not_delivered/admission_verdict.json`（32473 B，mtime **17:44:29**）：
顶层 `ok=false`，但 `status` 直方图 = `{'PASS': 18, 'UNJUDGED': 5}`，**RED = 0 条**。
⇒ **任何按 "RED" 字样判读的下游（人肉 grep 或汇总脚本）会把这次失败读成干净。**
`UNJUDGED` 是第 4 档状态，语义是"A2 未交付 ⇒ 无从判"，它**必须**参与失败判定。
**建议（报 B2 + D）**：在产物顶层显式写 `n_red / n_warn / n_unjudged / ok` 四元组，
并要求下游只读 `ok`；或在文书里把 `UNJUDGED` 与 `RED` 并列为"非绿"。

### F2 · B2 委托闸：**20/20 与 25/25 条 check 的 `id`、`ok` 都是 `null`**
`delegated_g1_g5_a2env.json`（21:13:00）与 `delegated_g1_g5_freeze.json`（21:13:00）：
5 条 check 的字段是 `{id: null, status: "PASS|WARN", ok: null, note: ""}`。
跨 4 份 a2env 产物共 **20 条**、5 份 freeze 产物共 **25 条**，`id` 全为 `null`
（命令：`glob runs/vla/b2_env_admission_20260929/**/delegated_*.json` ⇒ 14 份文件，逐条枚举）。
⇒ 后果：① **无法按 id 引用**某一条委托判据（D 的执行单里"G1–G5"只能整组引用）；
② 任何 `if c["ok"] is True` 的汇总会把 PASS 读成不合格（**假红**）；
③ 任何 `if c["status"] == "RED"` 的汇总对这两把闸**永远为假**（**恒真**）。
**建议**：补 `id`（如 `G1_freeze` / `G3_a2env`）并让 `ok` 与 `status` 同源。

### F3 · B2 闸的 WARN 极性错（**D 已独立复核成立**，此处只补产物坐标）
`admission_verdict.json`（21:13:01）与 run2（18:28:42）/run3（18:44:46）里，
`"  G2_rebuild_lockout_not_default[a2env]"` 报 **WARN**，而它的期望**已被满足**
（`same_as_0928=false`、`lock_diff` 已逐包枚举）⇒ 应为 PASS。
**附带发现（数据卫生）**：这条 check 的 **id 带两个前导空格**（`"  G2_..."`），
在三份产物里一致出现 ⇒ 精确匹配/去重/按 id 建索引都会漏掉它。

### F4 · A2 闸：一次**真假红**，已自纠 + 6/6 变异体（正面样本）
`runs/vla/a2_env_pi05_sim_20260929/manifest_run3_v10_pep610_false_red/WHY_ARCHIVED.md`：
V10 的 c6 原判据 `direct_url["url"].startswith("git+")`，而 **PEP 610 的 `url` 是裸 VCS URL**
（实测 `https://github.com/huggingface/transformers.git`，不带 `git+`）⇒ 真环境被判红。
修法：改判 `vcs_info.vcs == "git" and "archive_info" not in direct_url`，
并把判据拆成纯函数 `eval_v10()` + **6 变异体自检 6/6 全抓**（M1 = 本轮真实 blocker 状态）。
**C2 的评价**：这是本仓**处理假红的标准动作**（留档 + 拆纯函数 + 变异体自证），建议写进纪律。

### F5 · A2 闸：另两个 `*_false_red` 目录**没有留档说明**
`manifest_run1_probe_false_red/`（mtime **19:11:47**）与 `manifest_run2_dist_drift_false_red/`（**19:15:19**）
各只有 `env_manifest.json` + `env_manifest.log`，**无 `WHY_ARCHIVED.md`**
（命令：`ls` 逐目录枚举，3 个 false_red 目录里只有 run3 有留档说明）。
⇒ 目录**名**断言了"假红"，但产物内**没有**根因说明。按裁定 50.1，C2 **不断言**它们是不是假红，
只报"留档缺口"。**建议**：A2 补两份 `WHY_ARCHIVED.md`（与 run3 同格式）。

### F6 · 三套互不兼容的 check schema 共存于同一闸族
| 产物 | check 字段 |
|---|---|
| `admission_verdict.json` | `id, ok, observed, required, note, status, ruling_ref, red_when`（8 字段，**最完整**） |
| `delegated_g1_g5_*.json` | `id(null), status, ok(null), note("")` |
| `delegated_v0_v9.json` | `id, ok, observed, required, note`（**无 status**） |

⇒ 任何跨闸汇总器必须同时处理三套；只按 `status` 读会把 V0–V9 的 **50/50 条**读成"无状态"，
只按 `ok` 读会把 G1–G5 的 **45/45 条**读成不合格。
**建议（报 B2 + D）**：定一个最小公共 schema（`id / ok / status / required / observed / red_when`），
新闸一律照它；存量闸不强制回填，但**汇总器必须显式声明它读的是哪套**。

### F7 · 实现层的三处"恒真/吞异常"（**不是我们的闸，但会让我们的判据变空**）
| 位置 | 行为 | 后果 |
|---|---|---|
| `normalize_processor.py:305`–`:307` | stats 缺失时**静默走 IDENTITY** | "有归一化"型判据恒真 |
| `normalize_processor.py:362`–`:377` | QUANTILES 的 `denom=q99-q01` **只防 `denom==0`，无下限** | 近常量维被放大（ACT 线 `(x-mean)/(std+1e-6)` 冲到 20402 是同族）；`:335` MEAN_STD、`:349`–`:354` MIN_MAX **同缺陷** |
| `modeling_pi05.py:995`–`:998` + `:1046`–`:1047` | 缺键时**静默返回随机权重**；异常被吞成 `print` | **"加载未报错"型判据恒真** ⇒ S3 出口判据第 2 条必须显式查缺失/多余键 |

**注**：以上三处属 `site-packages`（第三方），**C2 不改**；只作为"判据设计约束"上报。
`kind=code_read_semantics`（读实现原文），非能力主张。

### F8 · torch local tag 假红（**D 已确认**，此处只登记坐标）
红线值本来就是 `2.6.0+cu124`，把 **local tag 差异**当漂移是判据错 ⇒ 假红。
出处：D 的执行单与备忘录（裁定 49.3 段）；C2 **未独立复跑**该闸 ⇒ 标 `declared_only`（不作 blocking）。

---

## §4 「从未真实变红」的闸（D 要求单独标出）

| 闸 | 可得历史 | 非绿次数 | 结论 |
|---|---|---|---|
| `delegated_g1_g5_freeze` | 5 份产物 / 25 条 | **0**（全 PASS） | **恒真（在可得历史内）**，且无变异体记录 ⇒ 风险最高 |
| `delegated_g1_g5_a2env` | 4 份产物 / 20 条 | 0 RED，4 WARN | 从未红过；WARN 语义未在产物内声明 |
| `delegated_v0_v9` | 5 份产物 / 50 条 | **0**（全 `ok=true`） | 从未红过，但**它是转述 B 门禁的变异结果**（`V3: n_mutations=15 n_caught=15`）⇒ 牙在**被转述的那把闸**上，不在它自己身上 |
| A2 `env_manifest.assertions` | 当前 10/10 true | 1 次假红（20:50:14） | 非恒真（红过，但是假红）；变异体 6/6 为 `declared_only` |

**处置建议**：`delegated_g1_g5_freeze` 要么补变异体、要么**显式降级为"清单核对"而非"闸"**
（叫"闸"却从不红，会让下游以为有一层保护 —— 这与裁定 27.1「恒真的闸等于没有闸」同义）。

---

## §5 上报给 D 的三条（**C2 不自行改任何人的闸**）

1. **词表统一**（F1 + F6）：定最小公共 check schema，并要求顶层 `ok` 是**唯一**失败判据；
   `UNJUDGED` 必须计入非绿。
2. **委托闸补 id**（F2）：`G1–G5` 的 45 条 check 现在 `id=null`，D 的执行单无法精确引用到条。
3. **恒真闸处置**（§4）：`delegated_g1_g5_freeze` 25/25 全绿且无变异体 ⇒ 请 D 裁
   「补牙」还是「降级为清单核对」。

**C2 自己已经做的**（不需 D 裁，属本线职责）：把上面 §2.1 的 4 次自审缺陷**全部留档**，
并且**没有**用"我的闸全绿"当结论——两把闸的绿是**带变异体实测**的绿
（4/4 文件级 + 3 个反向 + 1 个输入级），不是"跑了一遍没报错"。

---

## §6 本审计的边界与未完成项（诚实记账）

* **未审**：全仓历史闸（A/B/C 三线的 `selfcheck_*`、`b_selfcheck_gate_*`、`registry/` 自检）——
  裁定 54 / §6 明确限时，**不做全仓普查**。
* **未复跑**：A2 的 `--selftest`（6 变异体）、B2 的 60 变异体、B 的 157 断言 ——
  本审计**只读产物**，不复跑别人的闸（复跑会写别人的产物目录）。⇒ 涉及它们的结论一律标 `declared_only`。
* **未审 S1/S2/S3/S5/S6 的闸**：产物尚不存在（`未实施`），无对象可审；已在 §2 给出落地时的必测变异体提醒。
* 本文件是 C2 单写；追加到共享文书（`daily_report.md`）前已按纪律做 `git status` + `tail`。

---

## §7 追加（21:5x，应 D 执行单 §9-4 要求）：**文档级恒假断言**（不是闸，但同族）

同族定义：**被当成结论反复引用的未验证断言**。闸的恒真是"判据永远绿"，文档的恒假是
"理由永远被当成事实"。两者都靠"读实现 / 真跑"才能拆穿。

| # | 断言原文（file:line） | 实测/读实现后的结论 | 证据坐标 |
|---|---|---|---|
| **D1** | `docs/infra-gpu-render.md:115`（19614 B，mtime **09-29 17:04:46**）：「**二是没有 `/dev/dri` 时 EGL 设备枚举拿不到任何设备**」 | **被证伪**：`/dev/dri` 确实不存在，但 NVIDIA EGL 设备枚举**成功**，且 `drm_device_file=null` 不妨碍 `initialize_ok=true` ⇒ 该理由对 **NVIDIA `EGL_EXT_platform_device`** 不成立（对 Mesa 成立） | `runs/infra/e_gpu_egl_verify_20260929/staged_ldpath.json`（12273 B，mtime **20:59:32**）→ `egl_device_probe.devices[0]` = `{drm_device_file: null, vendor: "NVIDIA", initialize_ok: true}`；同文件 `egl_vendor_icds.icds` 只有 `/usr/share/glvnd/egl_vendor.d/50_mesa.json → libEGL_mesa.so.0`（即**默认 vendor 只有 Mesa**，这才是真障碍，不是 `/dev/dri`） |
| **D2** | 「`transformers >= 4.57.1`」作为 π₀.₅ 的依赖红线（**C2 自己上一轮提的**，来源是 lerobot 的**声明依赖**） | **错的，而且照它做会把环境搞坏**：真正的卫语句是 `modeling_pi05.py:576`–`:584` 的 `from transformers.models.siglip import check` → `check_whether_transformers_replace_is_installed_correctly()`，**不是版本区间**；A2 venv 里的 `transformers 4.53.3` 是 **git 构建**（commit `dcddb970176382c0fcf4521b0c0e6fc15894dfe0`、branch `fix/lerobot_openpi`），其自带 `check.py` **只接受 4.53.2 / 4.53.3** ⇒ 装 `>=4.57.1` 会让卫语句返回 **False**、π₀.₅ 直接加载失败 | D 的裁定 48 正文（`d_handoff_to_c2_20260929.md:132`–`:162`）；`requirements.lock.txt:111` = 该 commit；A2 的 `V10_transformers_identity_is_git_commit_per_ruling_48`（`env_manifest.json` assertions 10/10 true，mtime **20:51:16**） |
| **D3** | C 线的「**147 KB/帧**」图像体积推算 | **口径不同，不可与本线实测并列**：C2 实测 `harness/obs_store.py` 的 `np.savez`（**未压缩**）载荷 = **1765.19 KB/帧**（π₀.₅ 策略层 3×[3,224,224] float32 + state）与 **2701.04 KB/帧**（env 相机 3×480×640×3 uint8 + state）。**两者不是同一个量**（PNG 压缩 vs npz 未压缩），C2 **不做换算、不宣布谁对谁错**，只把两个口径分开登记 | `runs/vla/c2_obs_key_whitelist_20260929/probe_20260929/probe_main.json` → `variants.*.payload_KB_uncompressed_npz`；`runs/vla/c2_env_gym_aloha_20260929/gate_verdict_online.json` → E3/E7 的 `flat_payload_nbytes=1807552` |

**D2 的教训已被 D 立为纪律**（`operations.redline_provenance_discipline`）：任何版本/阈值/下界类红线，
第一次入文书前必须读实现原文并留 `文件:行号`；只有声明值支撑的一律标 `declared_only`，不得作 blocking。
**C2 补一条同族建议**：文档里的**理由句**（"因为 X 所以不可能"）应与结论分开标注 —— D1 的结论
（"容器内装不了 GL"）当时可能确实成立，但它的**理由之二**不成立；理由一旦被证伪，结论就必须重测，
而不是继续沿用。⇒ 建议文书里的"因为…"句也带 `kind`（`measured` / `code_read_semantics` / `declared_only`）。

---

## §8 追加（应 D 执行单 §9-2② 要求）：**monkeypatch「只改一半」审点**

裁定 57.4 的纪律：任何 monkeypatch 必须先读**使用方的 import 形式**；`from m import X` ⇒
必须同时改使用方绑定，并配「只改一半 ⇒ 静默错值」的变异体。逐闸核查结果：

| 涉及 monkeypatch 的实现 | 有没有这条牙 | 证据 |
|---|---|---|
| A2 `envs/gym_aloha_shim.py`（sha256-12 `dc14466fcdcf`） | **有** | `apply_dt()` 同时改 `gym_aloha.constants.DT` **与** `gym_aloha.env.DT`，并在 `verify=True` 时检查 `both_names_patched`，不同时生效即判失败；配套实验 `scripts/a2_hz_shim_verify.py:144` 的 `patch_mechanism_proof()`（**三种模式各在独立子进程**里构造真 env、读回**活对象**的 `control_timestep`），产物 `runs/vla/a2_hz_shim_29p4118_20260929/hz_shim_verification.json`（15406 B，mtime **21:23:34**）含 `patch_mechanism_proof.all_teeth_green` 与 `untouched.constants_DT=0.02 / env_module_DT=0.02 / live_control_timestep_s=0.02`。`kind=declared_only`（C2 **未复跑**，只读产物结构） |
| **C2 `harness/env_gym_aloha.py`**（sha256-12 `387f78e2c49f`） | **有（本轮新增，实测）** | 闸 `scripts/c2_gate_env_gym_aloha.py` 的 **E11**：进程内**只改** `gym_aloha.constants.DT=0.034`、**不改** `gym_aloha.env.DT`，再直接 `gym.make` 构造 ⇒ 实测 `constants_dt=0.034 / env_module_dt=0.02 / measured_hz=**50.0**`（**静默留在 50 Hz，与 A2 的结论一致**），而本模块 `EnvContractError` 拒绝构造，消息 = 「控制周期不是主线口径：实测 control_timestep_s=0.02 ≠ 0.034（shim 未生效？裁定 53）」。`finally` 复原两个名字，**不改 site-packages 文件**。产物：`runs/vla/c2_env_gym_aloha_20260929/gate_verdict_online.json` → `E11`（`nr_throttled_delta=10`、`elapsed_s=4.833`、`MUJOCO_GL=egl`） |
| B2 准入闸 / 委托闸 | **不涉及** | 它们判的是依赖版本、文件身份、lock 一致性，**没有 monkeypatch** ⇒ 该审点 N/A |
| 实现层的第三方 monkeypatch（`modeling_pi05.py` 的 siglip 替换） | **有牙，但牙在 A2 的 V10 上** | `V5_transformers_has_siglip_check_for_pi05` + `V10_transformers_identity_is_git_commit_per_ruling_48`（`env_manifest.json`，10/10 true）⇒ 替换是否正确安装由**卫语句真跑**判定，不是由版本号判定。**这正是 D2 被拆穿后应有的形态** |

**结论**：这条审点在**本仓现有两把涉及 monkeypatch 的实现上都已闭合**（A2 声明级、C2 实测级）。
**风险提示（不是判定）**：A2 的那条是 `declared_only` —— C2 未复跑其子进程实验；若 D 要求实测级确认，
应由 A2 或 C2 复跑一次 `scripts/a2_hz_shim_verify.py --selftest` 并落新产物（**C2 未自行复跑**，
因为那会写 A2 的产物目录，违反线前缀纪律）。

---

## §9 勘误（append-only，2026-09-29 23:3x；应 D 执行单 §12-4 / 裁定 78.11 要求补）

**本节只追加，上文 1–260 行一字未改**（追加前本文书 = 260 ln / sha256-12 `8ea4fb4ad518`；追加后行数见文末）。
D 的判定 C2 接受：**不是造假、不是结论错，是引用时序错**。

| # | 审计原文位置 | 原文写的 | 23:3x 重读现值 | 性质 |
|---|---|---|---|---|
| E1 | `:253`（§8 表内 C2 行） | `harness/env_gym_aloha.py` sha256-12 = `387f78e2c49f` | **`387f78e2c49f` → `6c4d71eb732e`，as_of mtime 2026-09-29 22:09:11**（579 ln / 32569 B） | 落笔 22:07:14，**写完 2 min 后文件被改** ⇒ 所引 sha 已不存在于磁盘 |
| E2 | `:99`（§1 汇总表 B4 行）、§8 | offline **`14/14 PASS`** | **`n_checks: offline 15`** / `verdict=PASS` / `red=[]` | J14（边界语义）、J15（秒口径）是 C2 自审 C2-3 之后新增的 check ⇒ 计数过期 |
| E3 | `:99`（§1 汇总表 B4 行） | online **`9/9 PASS`**（实测 3.5 s，`nr_throttled_delta=2`） | **`n_checks: online 13`** / `verdict=PASS` / `red=[]`（mtime 22:09:42） | 同 E2；E11（monkeypatch 只改一半）为后增 |
| E4 | 全文（当时尚未发生） | 未记载 D 的独立复跑 | **D 复跑时刻 22:52:32 / `verdict=PASS` / `red=[]`**，用的是当前 sha `6c4d71eb732e` | D 已据此**接受** `harness/env_gym_aloha.py`（§12-2） |

**本勘误引用的文件身份三元组（sha 于落笔时刻重读，命令原文 `sha256sum <path> | cut -c1-12`）**
- `harness/env_gym_aloha.py` · `6c4d71eb732e` · as_of mtime 22:09:11（579 ln / 32569 B）
- `runs/vla/c2_env_gym_aloha_20260929/gate_verdict_offline.json` · `4043c6d56900` · 字段 `verdict` / `n_checks`（11389 B）
- `runs/vla/c2_env_gym_aloha_20260929/gate_verdict_online.json` · `0c07951ce3da` · 字段 `verdict` / `n_checks`（16006 B）
- `runs/vla/d_verify_c2_env_gate_offline_20260929/gate_verdict_offline.json/gate_verdict_offline.json` · `3d2de924b547` · 字段 `generated_at` / `verdict` / `n_checks`（路径**嵌套一层**，即 D §12-2 记的 `--out` 口径缺陷实例，C2 不代改他人产物）

**纪律接受与 C2 的实现口径（`citation_sha_as_of_discipline`，红线级）**
1. 引用**自己写入面内、且仍可能在编辑**的文件时，sha **必须在落笔时刻重读**（不得沿用早先 run 的值），并带 `as_of` mtime；无法保证的标 `superseded_risk=true`。
2. C2 已把该口径写进回流单（`docs/c2_handoff_to_d_20260929.md`）的"纪律接受"节，并在本会话后续所有文书里执行。
3. **同族自查（不改判、只重申）**：§8 表内 A2 的 `envs/gym_aloha_shim.py` sha256-12 `dc14466fcdcf` 属**他人写入面**、C2 **未复跑** ⇒ 原文标 `kind=declared_only` 正确，维持。B2 的 `scripts/b2_s1_scripted_expert.py` 正踩同坑（D §12-4 已同条要求 B2）⇒ C2 侧的对策：**凡引用 B2 的 S1 产物做 stats 源，一律在读取时刻重算 sha 并写进 `provenance`，不在文书里抄旧值**。
