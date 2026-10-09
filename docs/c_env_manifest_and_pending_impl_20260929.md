# C 线：增补六 §8-C 三条 P1 落地（解释器探测 / env manifest 与断点 / `PENDING_IMPL` 分级）

登记方：智能体 C（实体运行时·事实账本·训练视图线）。
依据：`rl_harness_supervision/supervisor_memo_20260929.md`（增补六）§0.2 第 2、3 条、
§8-C 第 1/2/3 条、裁定 17.7（过渡期专用标签）、裁定 18（stdfloor 的门禁免罪是**对的**）、
裁定 26（v1.5 复签通过）、以及 ADR-C-004（SKIP ≠ PASS）。
本文件是**推导记录**，判据原文在 D 的备忘，C 不复制也不改写 D 的裁定。

写入边界：`registry/verdict_identity.py`、`scripts/c_selfcheck_verdict_identity.py`、
`scripts/c_run_all_selfchecks.sh`、`scripts/c_env_manifest.py`（新增）、
`runs/infra/c_*`、`docs/c_*`、`work/decisions/decisions_20260929_C.md`。
**未改** A/B/D 任何文件，未改 `requirements.lock.txt` 与 `scripts/setup_env.sh`，
未执行任何 git 写命令（DR-003 决定 8 单写者纪律），全程未用 `rm`。

---

## 0. 接手时的现场（必须先说清，否则后面的数字无从对照）

本轮 C 的上下文是从盘上产物重建的（9/28 四线 rollout 已被检修清掉，见 ADR-C-006）。
接手时三件事的现场状态：

| 项 | 接手时实测 | 说明 |
| --- | --- | --- |
| `registry/verdict_identity.py` | 已改（新增 `USABLE_PENDING_IMPL` / `is_pending_impl_exoneration()` / `classify()` 两个新参 / `pending_impl_label` / `exoneration_disagreement`），语法通过 | 上一轮 C 写到一半 |
| `scripts/c_selfcheck_verdict_identity.py` | **未跟上**：`82/84 PASS，2 FAIL` | 两条 FAIL 不是回归红点，是自检里那套「独立重写的分级规则」还停在五档 |
| 门禁构建 | `v1.5 / f19f61341cbe`（现场 import 自报） | D 裁定 26 锚定的那个构建；今早还是 `v1.4 / b9379fdb1089` |
| `runs/infra/b_official_arms/reclassification.json` | `v1.5 / f19f61341cbe`、`ic_status 45/2/1`、`citable 25/22/1`（11:22） | 裁定 26 三前提之第 2 条**已满足**（B 已重出权威裁定表） |
| `runs/infra/lerobot_act_env_20260928/arms_summary.json` | `v1.2.1 / e4f5ec887788`（9/28 21:45） | A 的 48 臂汇总表**未重出**（等迁移闸 OPEN） |

> **本节的数字已被 §7.1 超越**（B 的 v1.5 逐臂重判在 12:0x 落盘 ⇒ `physical_fact` 0 → 48）。
> 原文保留不改，最终实测以 §7.6 为准。

⇒ 一个必须报的连带效应：门禁升到 v1.5 后，**被扫目录里没有任何一份逐臂裁定出自当前构建**
（15 个 build 里没有 `f19f61341cbe`），所以 C 的清单 `physical_fact` 从今早的 **15 → 0**
（那 15 条全部出自 `ckptseq/v14_crosscheck`，随构建移动降级为 `stale_build_evidence`）。
这不是回归红点，是内容寻址身份层**该有的行为**：判据一升级，旧构建的裁定就不当物理事实。

---

## 1. 三条 P1 的处置总览

| §8-C | 要求（原文摘要） | 处置 | 验收 |
| --- | --- | --- | --- |
| C1 | `c_run_all_selfchecks.sh` 的 `PY` 默认值改成「探测优先、失败即明确报错」，不钉死绝对路径 | 候选探测 + 依赖探测；退出码分成 0/1/2 三种含义 | 4 条路径实测（§3） |
| C2 | 环境重建后重跑全量回归 + 重出 env manifest，并登记「0929 检修 venv 重建」断点 | 新增 `scripts/c_env_manifest.py`；全量回归重跑 | manifest 落盘 + 13/13 全绿（§4、§6） |
| C3 | `registry/verdict_identity.py` 把 `PENDING_IMPL_probe_exonerated` 纳入 `usable_for` 分级，单独一档 | 新增第六档 `pending_impl_ruling_approved`，自检加真值表 + 3 个变异 | `125/126 PASS（1 SKIP）`（§2） |

---

## 2. C3：第六档 `pending_impl_ruling_approved`

### 2.1 为什么必须自成一档（不是给 `invalid_measurement` 加个注脚）

D 的 §8-C3 原文：「它既不是 `physical_fact`（门禁产不出），也不是 `stale_build_evidence`
（事实基础已核可）。建议单独一档『裁定已核可、实现待落地』，这一档在 v1.5 之前是
**唯一诚实的分级**。」裁定 17.7 又规定了表述纪律：**不得**写「已免罪」（超出事实），
也**不得**写「INVALID 维持不变所以能力未知」（丢掉已核可的事实基础）。

把两种错误表述翻译成 C 的分级语言，就是两个具体的事故：

- 落 `invalid_measurement` ⇒ 等于让**未被实现承载**的门禁结论单方面压倒已会签的裁定
  （= 裁定 17.7 禁止的第二种表述）；
- 落 `physical_fact` / `stale_build_evidence` ⇒ 等于把「门禁产不出的数值」当事实或当旧事实
  （= 裁定 17.7 禁止的第一种表述）。

所以这一档必须存在，且标签沿用 D 的原字 `PENDING_IMPL_probe_exonerated`（C 不另造词）。

### 2.2 优先级：为什么排在「终局语义怀疑」之后、「测量无效」之前

`classify()` 的顺序是：不是裁定 > 身份/有效性声明缺失 > **终局语义怀疑** >
**裁定已核可实现待落地** > 测量不可信 > 构建过期 > 可当事实。两处排序都有理由：

- **排在终局语义怀疑之后**：裁定 10 的探针免罪针对的是**输入契约 / blown** 那一维，
  覆盖不到「把截断标成失败」这种终局语义问题。若让免罪盖过 suspect，这一档就变成
  「免罪万能牌」——任何被权威表记过免罪的臂，连终局语义造假的裁定都能被抬出
  `invalid_measurement`。变异 7 专门测这一点（§2.4）。
- **排在测量不可信之前**：这一档要处理的正是「门禁判 `measurement_valid=False`、
  而监管层已会签免罪」的冲突本身；放到后面就永远轮不到它。

### 2.3 只认**正向**：裁定 18 的直接后果

`is_pending_impl_exoneration(validity_class, input_contract_status)` 只在
「权威表 = `VALID_probe_exonerated`」且「门禁 `input_contract.status != probe_exonerated`」
时为真。反方向（门禁免罪、权威表不是免罪）**只计数、不改分级**：裁定 18 已判
stdfloor 那条门禁是**对的**、属权威表滞后，那不是实现缺口。C 不替 A/B 裁定谁对，
所以反方向进 `exoneration_disagreement.gate_exonerated_authority_not` 计数，分级不动。

本轮实测两个方向都非空（这说明双向分列不是摆设）：

- 正向：`official_act_truth20_trimdone0_minmax_k2_lr1e-5_s20k_seed0`（= 裁定 17 的目标臂）；
- 反向：`official_act_truth20_trimdone0_stdfloor_minmax_k2_lr1e-5_s20k_seed0`（= 裁定 18 的目标臂）。

### 2.4 自检形态：真值表 8 格 + 纯函数 7 格 + 变异 6/7/8

新增两个 case（`case_pending_impl_grade`、`case_pending_impl_real_inventory`）。

**文件级真值表**（合成裁定 + 合成权威表索引；数字无物理意义，只测分级）：

| 格子 | 权威表 | 门禁 | 其它 | 期望档 | 出处 |
| --- | --- | --- | --- | --- | --- |
| `authority_exo_gate_violated` | `VALID_probe_exonerated` | `violated` | `mv=False` | **pending_impl** | §8-C3 / 裁定 17.7 |
| `authority_exo_gate_exonerated` | `VALID_probe_exonerated` | `probe_exonerated` | `mv=True` | physical_fact | 裁定 26：实现承载后本档自动清空 |
| `authority_valid_gate_violated` | `valid` | `violated` | `mv=False` | invalid_measurement | §8-C3 只认「权威表已会签」 |
| `authority_exo_suspect` | `VALID_probe_exonerated` | `violated` | `suspect=True` | invalid_measurement | 裁定 10 免罪范围 |
| `authority_exo_no_build` | `VALID_probe_exonerated` | `violated` | `gate_build` 缺失 | unidentified_build | 身份先于有效性 |
| `authority_exo_undeclared` | `VALID_probe_exonerated` | `violated` | `measurement_valid` 字段被删 | unidentified_build | 不替上游下结论 |
| `authority_exo_stale_build` | `VALID_probe_exonerated` | `violated` | 旧构建 | **pending_impl** | §8-C3：与构建新旧无关 |
| `authority_exo_aggregate` | `VALID_probe_exonerated` | `violated` | 聚合报告 | not_a_verdict | 不凭空造臂 |

8 格落在 5 个不同档 ⇒ 这一档既不是常量，也没有吞掉别的档。
另有 7 格直接问 `classify()` 纯函数（不经文件），与文件级同答 ⇒ 两条路径互校；
并断言两个新参**有缺省值**（旧调用点不传也能跑，向后兼容）。

**变异（每个都实测转红，不是写着好看）**：

- 变异 6：把这一档整个拿掉（退回 9/28 的五档实现，`_classify_without_pending_branch`）
  ⇒ 真清单里已会签的 **5 条全部被埋进 `invalid_measurement`**、过渡期标签全部消失。
  这正是 §8-C3 要防的事故，也是「本节断言非恒真」的证据。
- 变异 7：判据放宽成「一律免罪」（免罪万能牌）⇒ 当前构建的 `physical_fact` 被吞成待落地、
  权威表未记免罪的裁定也被抬进这一档；**同时**验证 suspect / 身份缺失 / 聚合报告三格
  **仍然不被免罪盖过**（说明那三条优先级是 `classify` 的顺序在管，不依赖判据宽窄）。
- 变异 8：只认**反方向** ⇒ stdfloor 那类「门禁判对了」的臂会被记成实现缺口，违反裁定 18。

### 2.5 真清单实测（`runs/infra/c_verdict_identity_inventory.json`）

188 文件 / **192 条裁定**、15 个 build 并存、当前构建 `v1.5 / f19f61341cbe`：

```
stale_build_evidence 145 / unidentified_build 24 / invalid_measurement 17
pending_impl_ruling_approved 5 / not_a_verdict 1 / physical_fact 0
```

命中本档的 5 条（全部是目标臂 `trimdone0_minmax_k2_lr1e-5_s20k_seed0`）：
4 条出自 `migration_gate/exoneration_path_probe/`（`b9379fdb1089`，A 的免罪通道探针），
1 条出自 `regate_current/`（`e4f5ec887788`，48 臂重判的那一份）。
另有 1 条同臂的顶层留档裁定 `gate_build` 缺失 ⇒ 如实停在 `unidentified_build`
（身份先于免罪，不给它抬档）。

分级可复算：自检里用**独立手写**的判据（不调 `is_pending_impl_exoneration`）复算 192 条，
命中集合与 `classify()` 逐条相同。

### 2.6 一处口径澄清（本轮新增的诊断项）

v1.5 已由 D 复签通过（裁定 26），所以旧产物上的 `PENDING_IMPL` 标签**不能**被读成
「实现还没落地」。这一档是**逐份裁定**的口径：说的是「这份产物的门禁输出没有承载免罪」。
清单因此新增两项，避免误读：

- `exoneration_disagreement.scope_note`：明写逐份裁定口径与「实现落地后本档自动清空」；
- `exoneration_disagreement.per_arm_current_build`：正向脱节的臂在**当前构建**下的产物观测。
  本轮为空列表 ⇒ 如实空着，并据此把「已承载免罪的记录自动让位」这条断言记为 **SKIP**
  （ADR-C-004：SKIP ≠ PASS）。C **不重跑门禁**去造这个观测 —— 那就是第二套判据。

等 B 把 v1.5 的逐臂重判产物落进 `lerobot_act_env_20260928/`（如 `regate_current/`），
这条 SKIP 会自动转成可验证，且本档计数应自动归零、目标臂转 `physical_fact` ——
**无需改 C 的任何代码**（真值表第 2 格就是这个性质）。

---

## 3. C1：`PY` 探测优先、失败即明确报错

改动只在 `scripts/c_run_all_selfchecks.sh` 头部与汇总段。要点：

- 候选顺序：显式 `PY`（若给了）→ `/root/venvs/rlrobot/bin/python` → `python3`；
- 每个候选跑一次**依赖探测**（`numpy torch pandas pyarrow robosuite gymnasium py_trees
  mujoco stable_baselines3` = 本轮 12 个自检脚本的并集），第一个全齐的才用；
- 退出码分三种含义：`0` 全绿 / `1` 有回归红点 / **`2` 没有可用解释器**（环境问题，
  不是回归失败）。检修那种「解释器不存在」再也不会长得像「回归全红」；
- 显式 `PY` 探测不过时**仍放行**（保留 D §0.2 第 3 条给过的临时做法），但绝不静默：
  当场打印缺哪些模块，并在汇总里声明「本次不构成一次可信的全量回归」。

四条路径实测（`tmp/agentC_probe_test_20260929/head_only.sh` = 只截到解释器选定为止的副本，
不触发长跑；另造 `no_venv.sh` 把 venv 候选换成不存在的路径）：

| # | 场景 | 实测 |
| --- | --- | --- |
| T1 | 默认，venv 已重建 | `探测 /root/venvs/rlrobot/bin/python -> OK`，选它，`rc=0` |
| T2 | `PY=/opt/conda/bin/python3`（缺 5 个包） | 打印 `MISSING:robosuite,gymnasium,py_trees,mujoco,stable_baselines3` → **回退**到 venv，`rc=0` |
| T3 | 无 venv、PATH 里没有可用 python3、未显式指定 | 打印候选与缺失清单 + 处置指引，**`rc=2`** |
| T4 | 无 venv 但显式 `PY=/opt/conda/bin/python3` | 放行 + `!! 由此产生的红点可能是环境缺失`，汇总里再声明一次 |

---

## 4. C2：env manifest 与「0929 检修 venv 重建」断点

新增 `scripts/c_env_manifest.py`，产物 `runs/infra/c_env_manifest_20260929.json`。
口径沿用 `docs/lerobot_official_env_manifest_20260924.md`：**环境路径 / 记录版本 /
版本冲突 / 入口验证**四块齐备。

### 4.1 断点是一个**窗口**，不是一个时刻

D 的要求是「登记断点，否则将来无法判断某条复现主张跨没跨过这个断点」。要能判，就得有
可比的时刻；本轮实测发现单点不够：

- `occurred_at = 2026-09-29T10:45:56+08:00`（`bin/python` 链接自身 ctime = `python -m venv` 建它的时刻）；
- `ready_at = 2026-09-29T10:57:19+08:00`（`rebuild2.log` 落盘，末行 `rc=0` = 环境可用）。

于是分类规则是三值：`mtime < occurred_at` ⇒ `before`（旧环境产物，跨了断点）；
落在窗口内 ⇒ `during_rebuild`（半装好的环境，同样不能当复现证据）；
`mtime >= ready_at` ⇒ `after`。

### 4.2 分类规则必须自测（真数据上它是空过的）

本轮 9 份 C 自检产物**全部**在断点之后（都是重建后重跑的）⇒ `before` / `during_rebuild`
两支在真数据上一条都没走到。空过的规则等于没有规则，所以把它抽成纯函数
`_position_vs_breakpoint()`，并用 6 个合成时刻逐支验证（含两端边界）：
`before 1s / occurred 当刻 / 窗口正中 / ready 前 1s / ready 当刻 / after 1h` ⇒ **6/6 符合期望**。
`--check` 模式把这 6 格也纳入闸（不符就 exit 3）。

### 4.3 lock 一致性与「继承包」

- `requirements.lock.txt` 的 **28 个 pin 全部精确命中**（`match 28 / mismatch 0 / missing 0`）；
- 13 个模块 import 探测全 OK（numpy 2.4.6 / mujoco 3.9.0 / robosuite **1.5.2** /
  gymnasium 1.2.3 / py_trees / stable_baselines3 2.7.1 / torch 2.4.1+cu124 / pandas 3.0.3 /
  pyarrow 24.0.0 / scipy 1.17.1 / numba 0.67.0 / mink / pytest 9.1.1）；
- **但 lock 是 `pip freeze --local`**：venv 用 `--system-site-packages` 建，
  `torch / torchvision / scipy / pandas / pyarrow / matplotlib` 从 base 继承、**不在 lock 里**。
  manifest 单列 `inherited_packages` 一栏，否则「lock 全中」会给出一个假的安心
  （真正跑训练的 torch 恰恰不在 lock 里）。
- 版本冲突按 0924 口径登记在 `known_conflicts`：`setup_env.sh` 的范围 pin（`numpy>=2`）与
  `robosuite 1.5.2 → mink==0.0.5 → numpy<2.0.0` 冲突，pip 26.2.1 判 `ResolutionImpossible`；
  复现口径 = 按 lock 精确装 + `--no-deps`。附四份证据产物的 sha256(12)/size/mtime。

### 4.4 `--check` 闸的反证（判据非恒真）

`--check` 的判据：lock 每个 pin 都必须在当前解释器下装成完全相同的版本，且 13 项 import
全 OK，否则 `exit 3`。反证实测：把 lock 复制一份、改 `numpy==1.99.99` 并追加
`notinstalledpkg==0.0.1`（`tmp/agentC_probe_test_20260929/bad.lock.txt`）⇒ 该脚本
`exit 3` 并逐条列出 `mismatch numpy pinned=1.99.99 installed=2.4.6` 与
`missing notinstalledpkg`。⇒ 这条闸**现在就是会红的**，不是恒真。

### 4.5 两处测量 bug（本轮自查自纠，登记以免重犯）

1. **符号链接跟穿**：第一版用 `bin/python.stat().st_ctime_ns` 取 venv 创建时刻，
   实测得到 `2025-09-22T11:55:17`（比检修早了一年）—— 因为 `bin/python` 是指向
   `/opt/conda/bin/python3.11` 的符号链接，`stat()` 跟到了 base 解释器。改用 `os.lstat()`
   后得到正确的 `2026-09-29T10:45:56`。**这个 bug 会让所有产物都被判成「断点后」**，
   即断点登记形同虚设。
2. **`realpath` 判不出「在不在这个 venv 里」**：同样是符号链接 + `--system-site-packages`，
   `os.path.realpath(sys.executable)` 指回 base，第一版据此算出的
   `runs_inside_requested_venv = False`（错）。改成看 `sys.prefix`（并附
   `is_venv = sys.prefix != sys.base_prefix`、`site_packages` 列表）后为 `True`。

### 4.6 不碰 GPU

manifest 只读 `nvidia-smi --query-gpu=... --format=csv,noheader`，**不创建 CUDA/EGL 上下文**
（A 在用卡训练），`gpu.context_probe.attempted = false` 并写明原因；同时记下调用时的
`CUDA_VISIBLE_DEVICES` / `MUJOCO_GL` / `OMP_NUM_THREADS`，因为
`torch.cuda.is_available()` 这类值**依赖这三个环境变量**，脱离它们记录就是误导。

---

## 5. 给 B / D 的观测（C 不代做，只报事实）

> **本节第 2/4 条已被 §7.1 超越**（产物已落盘、SKIP 已转实测），第 1/3 条仍成立但需按
> 裁定 28（§7.2）与 §19 A①（A 迁表后 meta 须刷成 `v1.5 / f19f61341cbe`）更新读法。

1. **裁定 26 三前提之第 2 条已满足**：`runs/infra/b_official_arms/reclassification.json`
   已是 `v1.5 / f19f61341cbe`、`ic_status 45/2/1`、`citable 25/22/1`（11:22 实测）。
2. **但被扫目录里还没有 v1.5 的逐臂裁定产物**：`runs/infra/lerobot_act_env_20260928/`
   下 188 份 `gate_*.json` 的 build 分布里没有 `f19f61341cbe` ⇒ C 的清单
   `physical_fact = 0`（今早 v1.4 时是 15）。**在 B 的 v1.5 逐臂重判产物落盘之前，
   任何「当前构建下的物理事实」在 C 这一层都是空的**；C 待办 1（P0-3 第二层：
   `ingest_runtime_result` 只吃 `physical_fact`）也因此仍然接不了线 —— 接了就是零输入。
3. **A 的权威表未重出**：`arms_summary.json` 仍是 `v1.2.1 / e4f5ec887788`（9/28 21:45），
   `validity_class` 分布 `valid 51 / invalid 1 / VALID_probe_exonerated 1`（索引 53 行含重测）。
   ⇒ C 的三键绑定仍指向这份表；表一刷新，C 的清单会自动跟随（内容寻址，无需改代码）。
4. **`PENDING_IMPL` 撤下的第三条前提在 C 侧的表现**：一旦 2 里的产物落盘，
   目标臂的 `input_contract.status` 会变成 `probe_exonerated` ⇒ C 的第六档自动清零、
   该臂转 `physical_fact`，`exoneration_disagreement.authority_exonerated_gate_not` 变空。
   C 会在那时把 §2.6 那条 SKIP 转成实测（不需要 D 再下一道裁定）。

---

## 6. 验收对照与复跑命令

```bash
# 全量回归（默认走探测；CPU-only 由脚本自己 export）
setsid bash scripts/c_run_all_selfchecks.sh > runs/infra/c_full_regression_20260929_pm2.log 2>&1 < /dev/null &

# 单独跑身份层自检（本轮 125/126 PASS，1 SKIP）
CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2 \
  /root/venvs/rlrobot/bin/python scripts/c_selfcheck_verdict_identity.py

# env manifest（--check 顺带做 lock 一致性闸；闸有反证，见 §4.4）
CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2 \
  /root/venvs/rlrobot/bin/python scripts/c_env_manifest.py --check
```

产物索引：

| 产物 | 内容 |
| --- | --- |
| `runs/infra/c_verdict_selfcheck.json` | 身份层自检结果（12 个 case、126 条断言、1 SKIP） |
| `runs/infra/c_verdict_identity_inventory.json` | 192 条裁定的全量清单（含新档与 `exoneration_disagreement` 诊断） |
| `runs/infra/c_env_manifest_20260929.json` | 环境快照 + 断点窗口 + lock 一致性 + 分类自测 |
| `runs/infra/c_gate_build_observed.jsonl` | 门禁构建观测流水（append-only，本轮追加 `v1.5/f19f61341cbe`） |
| `runs/infra/c_full_regression_20260929_pm2.log` | 全量回归日志（13 项） |
| `runs/infra/c_verdict_selfcheck/<时间戳>/pending_impl/` | 本节真值表用的合成裁定（8 份，数字无物理意义） |
| `tmp/agentC_probe_test_20260929/` | 探测四路径的测试副本与坏 lock 反证 |

**SKIP 清单（1 条，明写未被验证）**：`当前构建下已承载免罪的记录不再落这一档` ——
被扫目录里当前构建 `f19f61341cbe` 下还没有目标臂的裁定产物（§5 第 2 条），
所以「实现落地 ⇒ 过渡档自动让位」这条性质本轮只在合成真值表第 2 格上验过，
真产物侧**未被验证**。

---

## 7. 增补七（11:5x–12:0x）落地：裁定 28 的标注作废、裁定 29.4 的两条 P0、上游两次移动

> 本节是 §0–§6 的**追加**（append-only）：§0–§6 记的是 11:25–12:00 之间的实测，
> 其中若干结论已被上游移动与 D 的增补七超越。凡被超越处，本节明写，**不回改**前文。

### 7.1 上游在本轮实施期间移动了两次（不记就对不上前后数字）

| 时刻 | 事件 | C 清单实测 |
| --- | --- | --- |
| 11:29 | 门禁已是 `v1.5 / f19f61341cbe`，但被扫目录里**没有**当前构建的逐臂产物 | 192 条；`physical_fact` **0**；`pending_impl` 5；`invalid_measurement` 17 |
| 12:0x | B 的 v1.5 逐臂重判落进 `regate_current/`（含 `blindfix/`、`reblown/`） | **246 条**（+54）；`physical_fact` **48**；`pending_impl` 仍 5（全部历史构建）；`invalid_measurement` 17→23 |

⇒ §0 第 4 行与 §5 第 2/4 条里「`physical_fact` 15 → 0」「等 B 的 v1.5 逐臂重判产物落盘」
**已被事实超越：产物已落盘**。目标臂在当前构建下的那份现在是
`input_contract.status=probe_exonerated`、`measurement_valid=true` ⇒ `physical_fact`；
§2.6 那条 SKIP 也随之转成**实测 PASS**（「实现落地 ⇒ 过渡档自动让位」这条性质
已在真产物上验证，不再是合成真值表里的第 2 格）。C 侧**一行代码都没改**就跟随了上游
——这正是内容寻址 + 只读上游该有的行为。

### 7.2 裁定 28：`PENDING_IMPL_probe_exonerated` 标注**作废、全部撤下** —— C 的处置

裁定 28.1 撤下的是**标注**（对臂**现状态**的表述），不是「某一份产物有没有承载裁定」这个事实；
旧产物也不会因裁定更新而改写（内容寻址 + 只读上游）。所以 C 按裁定 28.4 对护栏① 的
**同型处理**：*本轮成 moot，机制仍保留*。落地方式三条，全部可核：

1. `LABEL_RETIRED = True` + `LABEL_RETIRED_BY`（引裁定 28.1 / 28.5）；
2. 命中记录的 `reasons` **逐条**追加作废声明 —— 不是只在文档里说一句：任何一条记录被单独
   摘出去引用时，都自带「这不是该臂现状态」的警告；
3. 清单摘要单列 `exoneration_disagreement.pending_impl_ruling`：`label_retired` /
   `retired_by` / `grade_mechanism_retired=false` / `arm_current_status_per_ruling`
   （**转引** 裁定 28.1，明写「C 未独立复核」）/ `citation_rule`（裁定 28.5：引 25/22/1
   必带 `v1.5 / f19f61341cbe`；引 v1.2.1 / v1.4 旧表必须标「历史口径」）/
   `evidence_for_open_question`（**实测字段**，不是叙述）。

**提请 D 裁定（C 不自行改分级）**：本档命中的 5 条现在全部出自历史构建，且性质与
「实现待落地」不符 —— 4 条是 A 在 `migration_gate/exoneration_path_probe/` 里
**故意造出来被拒**的写法探针（`gate_P0_baseline` / `P1_scope_arm` / `P2_scope_artifact` /
`P3_band_widened`，`violated` 是探针的**预期结果**），1 条是 `regate_v121_pinned/main/`
的**冻结锚点**（预登记 §6 钉死 v1.2.1）。三选一：

- (a) 留 `pending_impl_ruling_approved`（逐份产物的历史事实，靠 retired 标注防误读）；
- (b) 随裁定 28.2 转 `stale_build_evidence` —— **C 倾向此项**（这 5 条都是旧构建留档，
  而「未承载免罪」的事实可由 `exoneration_disagreement` 计数与 `reasons` 保留）；
- (c) 给「故意被拒的探针 / 冻结锚点」另立一档。

若判 (b)，C 的实施已经想好：把本档的激活条件收窄为「该臂在**当前构建**下没有任何承载免罪的
产物」（跨记录条件放 `inventory()`，`parse_verdict` 仍是记录级纯函数），被改判的记录留
`regraded_from` 以便审计；机制照常保留，将来再出现「条目已登记、会签块尚未换到新 build」的
窗口时它继续生效。实测证据已写进清单（`all_at_historical_builds=true`、
`pending_impl_builds=[b9379fdb1089, e4f5ec887788]`、
`arm_has_current_build_artifact_carrying_exoneration=true`），自检逐条独立复算过。

### 7.3 裁定 29.4 的两条 P0（C 已做）

**① `probe_modules` 加 `lerobot` + 回显来源与 commit pin。附一条 D 未覆盖的实测：**
lerobot 从来就**不在** `rlrobot` 这个 venv 里 —— 项目口径是**另建两个** venv
（`docs/lerobot_act_env_setup_20260928.md`：`/root/venvs/lerobot_act` 训练/离线审计、
`/root/venvs/lerobot_eval` 闭环真值评测；后者必须在同一解释器里既能 import lerobot
又能 import robosuite）。实测 `/root/venvs/` 下**只有 `rlrobot`** ⇒ 这两个环境也被同批
检修清掉了、**至今未重建**。所以「lerobot MISSING」的补救不是往 rlrobot 里 `pip install`，
而是跑 `scripts/install_lerobot_act_env.sh`。pin 从该脚本**解析**回显（不抄写）：
`LEROBOT=0.4.4`、`TORCH=2.6.0`、`TORCHVISION=0.21.0`、`INDEX=https://mirrors.aliyun.com/pypi/simple`、
`BASE_PY=/opt/conda/bin/python3.11`；两份 lock 各有一行 `lerobot==0.4.4`
⇒ **本项目的 pin 是 PyPI 版本号，不是 git commit**。

- 盘上三份候选源实测 commit：`zptang/lerobot_0cf8648` → `0cf86487…`（与目录名一致）、
  `gaoyuxuan/lerobot` → `4606785…`、`clzhang25/LIBERO/lerobot` → 无可用 HEAD
  （`fatal: ambiguous argument 'HEAD'`）。按裁定 29.4 **都不得当本项目的 pin**；
  C 只回显实测值，**不推断**它们与 PyPI `0.4.4` 是否同源。
- **一个重装陷阱（C 已预防）**：`install_lerobot_act_env.sh` 的 [5/7]、[7/7] 步会
  `pip freeze >` **就地覆盖** `runs/infra/lerobot_act_env_20260928/requirements{,.eval}.lock.txt`
  —— 那是 0928 环境的唯一证据。C 已先把两份 lock 逐字节复制到
  `runs/infra/c_lerobot_env_locks_backup_20260928/`（sha256 `68a38731c5b5…` /
  `b6db07e2e31c…`，与原件一致，已写进 manifest）；重装时也可用 `LOCK_OUT=` 指到别处。
- manifest 顶层新增 `env_fully_restored=false` 与 `reproduction_claims_blocked`
  （`missing = [lerobot, /root/venvs/lerobot_act, /root/venvs/lerobot_eval]`），
  探针分成 `required_for_c_regression`（13 个，进 `--check` 闸）与
  `blocking_for_reproduction`（lerobot，不进闸、但 `--check` 每次都把它喊出来）。
  ⇒ 「manifest 全绿」不可能再被读成「环境已完全恢复」（这正是裁定 29.4 点名的风险）。

**② GPU reason 改成可核事实**：原句「A 线正在用 GPU 训练」与同一份 manifest 里
`nvidia-smi` 实测的 `memory_used=0 MiB / utilization_gpu=0 %` 自相矛盾 ⇒ 改为
「本次不探测（不创建 CUDA/EGL 上下文）；GPU 此刻的占用以同一份 manifest 里
`gpu.nvidia_smi` 的实测值为准」，并附裁定 29.4 附带更正 2 的引用。
（同理，`c_run_all_selfchecks.sh` 头部那句「A 在用 GPU 训练」也改成不指认他线状态的写法。）

### 7.4 本轮自查自纠的两处新 bug（接 §4.5）

③ 解析 installer pin 的正则里 `$` **未转义**（正则里裸 `$` 是行尾锚）⇒ `pin.values`
是**空 dict**。空值比错值更难发现：manifest 看起来结构完整，只是那一栏没内容。
④ 取 git 失败原因时取了 stderr **最后一行** ⇒ 报出来的是 git 的用法提示
（`'git <command> [<revision>...] -- [<file>...]'`）而不是真正的原因（`fatal:` 那行）。

### 7.5 裁定 29.5 / §19 给 C 的两项新工作（本轮**未开工**，已登记待办）

- **待办 2 提 P0**（`work/decisions/` 正式登记处）：并号规则已给（`DR-D<n>` = D 线裁定序号，
  本轮到 DR-D28；`DR-00<n>` = B 线门禁/流程；`ADR-A-<n>` / `ADR-C-<n>` = A/C 线架构决定），
  原子单位 = 「一条决定一文件、内容寻址、只追加、撤销靠新条目指向旧条目」（与 `supersedes` 同型）。
- **待办 1 阻塞解除**（`physical_fact` 接线）：裁定 28 闭环 + 权威表已在 `f19f61341cbe` 上重出
  ⇒ 可以接；但 §19 C④ 明写「接之前先读 **11:45 版**表，不要用 11:22 版
  （后者缺 `terminal_kind_coverage` 等三处字段）」。
- 两项都是**新开工程**（前者要建登记处机制，后者要动 `harness/ledger.py` 的
  `ingest_runtime_result` 与 `DirectionScore` 身份字段），本轮**不半途开工**，
  按裁定 16 的顺序纪律排到下一轮；前置条件与验收判据写在 ADR-C-008 的待办表里。

### 7.6 增补七之后的最终实测（本文所有数字以此为准）

```
身份层自检     129/129 PASS（0 FAIL，0 SKIP；12 个 case，8 个变异体）
全量回归       13/13 全绿（含 golden 171 PASS / 0 FAIL / 1 NOT_ASSERTABLE）
env manifest   lock 28/28 match；required 13/13 import OK；blocking 缺失 [lerobot]
               env_fully_restored=false；断点分类自测 6/6
清单           246 条裁定 / 16 个 build；physical_fact 48、stale 145、unidentified 24、
               invalid_measurement 23、pending_impl 5（全部历史构建）、not_a_verdict 1
```

---

## 8. 15:4x–16:2x 落地：裁定 37.1 验收通过之后的三件事

> 本节依据 = 产物 mtime 与 D 的裁定原文（`rl_harness_supervision/supervisor_memo_20260929.md`
> §50–§54、`d_handoff_to_c_20260929.md` 附记 2/3），不是自述。
> §7.6 的数字是 12:0x 的，**以 §8.5 为准**。

### 8.1 验收结果与它的边界

**裁定 37.1：P0-3 + C-F1 + C-F2 全部验收通过**（D 只读复核）。D 点名认可的三处「比要求更严」：

1. **C-F1 没有把观测改成想要的值**：`rlrobot.modules.lerobot` 仍如实记
   `importable=false` + `ModuleNotFoundError`，改的是**判据的作用域**（`not_applicable` 三值 +
   `design_note`）。改观测或删行都是造假 —— 三值化的正确做法是让判据知道自己**不适用于**这个对象，
   而不是让它在这里恒过或恒红。
2. **C-F2 把「规则有牙」与「数据自洽」分开证**：规则自测用 synthetic 窗口
   （真窗口可能不可得、或恰好倒过来 ⇒ 规则就永远没被反向验证过），真窗口另列 `real_window`；
   两者不互相冒充。
3. **三条断点齐备且并列不合并**（`invalidates` 范围不同）。

**裁定 37.2：A 线解封**（`a_env_readiness_gate.py` E1..E7 全 PASS、`ALLOWED`、`blocking_fail=0`；
E6 五个 term 全部从本 manifest 取值）。**但解封有边界**，两条必须一起引用：

- A 现在可以声称新的训练/评测复现，但每条主张必须自带 ① 构建指纹（`v1.5 / f19f61341cbe`）
  ② 口径名 ③ **新 lock 的 sha256**（`env_provenance.json` 从「P1 接线」升为「第一次真跑就必须有」）。
- **解封 ≠ 48 臂旧产物自动跨断点有效**：`BP-20260929-lerobot-envs-wiped.invalidates` 明写
  「含 48 臂权威表所依据的那批评测，mtime 早于本断点 ⇒ 必须在重建后的环境上重跑才继续有效」。
  旧表仍可作**历史口径**引用（裁定 16.3 / 改判 7），但不得当作「已在当前环境复现」。

**裁定 37.3**：C 的 import 面实测**未触发**裁定 34.1 的可红条件（8 个 ACT 链路脚本全部 `hit=[]`，
与 A 的静态 grep 同向、且是更强证据），但**豁免边界收窄一句**：上游
`lerobot.scripts.lerobot_train` 的 import 闭包里确有 imageio（18 个子模块）⇒ C 把它**分开报**
（`why_upstream_separate`），A 须在断言产物里回显 imageio 的生效版本。
**一般化要求（此后适用于三线）**：「某包不在某链路的 import 面上」这类主张**必须给运行时证据**
（`sys.modules` 或等价动态追踪），**静态 grep 不足以独立支撑**（它扫不到传递依赖）。

### 8.2 裁定 37.4 第 2 条：覆写自己的 manifest 前必须留档（已实现）

D 的要求 15:29 落盘、C 15:30 覆写 ⇒ 是**竞态**，D 判不算 C 的错；且证据没丢
（D 在 14:31 只读跑 C 的脚本时把产物复制进了 `runs/infra/d_persistent_env_20260929/c_env_manifest.json`，
那一份记着 `env_fully_restored=false` / `importable=false` / `missing=["lerobot"]`
⇒ **「C-F1/C-F2 曾经是真红」仍可核**）。C 的 12:14 归档
`runs/infra/c_env_manifest_20260929_pre_lerobot_rebuild.json` 也做对了，只是漏了 14:54 那一版。

**已实现**：`c_env_manifest.py` 在写出前 `copy2` 归档上一版，新产物带
`previous_manifest={existed, path, sha256, generated_at, archived_to}` 与
`changed_fields={comparable, n_watched, n_changed, changed:{字段:{before,after}}}`。
15:47 那一版实测 `n_watched=31 / n_changed=3`。

**理由（与裁定 35.1 同源）**：**「修完就绿」和「判据本来就不会红」在覆写之后长得一模一样**，
只有留档能区分。这也是本仓第三次同型问题（裁定 23 的 `note` 恒空、裁定 35.3 的旁挂
`README_BASELINE.md`、裁定 37.4 第 1 条 A 的 E6 `note`）的一般规则：
**判据产物里的每一句散文，要么由观测生成，要么显式标注为历史说明并挂指针。**

### 8.3 P0-4：`work/decisions/` 正式登记处（待办 2 结案）

实现 `scripts/c_decisions_registry.py`、判据 `scripts/c_selfcheck_decisions_registry.py`（53 条，全部双向）、
口径 `work/decisions/registry/README.md`、叙事 `work/decisions/decisions_20260929_C.md#ADR-C-010`。
**本节只记「本轮撞出来的四个坑」，设计本身见上面三处**（裁定 21：判据单一来源，不在文档里抄第二份）。

| # | 坑 | 形状 | 为什么危险 |
| --- | --- | --- | --- |
| ① | 版本顺序按**文件名**排 | 文件名尾是内容哈希 ⇒ 字典序与写入时间**无关** ⇒「最新版」随机落错 | 旧 ack 永远显示 `matches_current_content=true` ⇒ **验收 3 的牙被拔掉还看不出来** |
| ② | 撤销的牙把两类引用**合并**判 | `supersedes` 指向已 `superseded` 的条目 = **传导成功**，却被判 `dangling_authority` | 判据恒红 ⇒ **永不报警等于没有报警**（与裁定 31.3 对 `exoneration_disagreement` 的要求同型） |
| ③ | 编号自检的期望值**硬编码** | 钉死 `B: DR-014`；B 当天在 `decisions_20260928_B.md:822` 补发 `DR-014` ⇒ 期望值腐烂 | 腐烂的样子是「测试红」，看起来像实现错 ⇒ **会诱导人去改对的实现** |
| ④ | 登记簿记被算进**判重分母** | `registered_at` 在哈希内容里 ⇒ 去重只在两次调用落在**同一秒**时成立；加 `version_seq` 后更是被 +1 完全打穿 | 「同内容重复登记 ⇒ 拒绝」这条验收悄悄失效，且失效方式是**多出一版**而不是报错 |

①④ 的共同根因是**一个哈希承担了两件事**。修法是分两层：
`payload_sha256`（「决定了什么」，判重按它）与文件名 `sha256`（全量含簿记，tamper 证据按它），
两层各配一条红（`payload_sha256_mismatch` / `tampered`）。
③ 的修法是**用第二份独立最小实现现场重算期望值**：测试若直接调实现来算期望，那就是自己证明自己（恒真）。
② 的修法是分开判并各配反面用例（`supersede_not_propagated` 也要能红、补上事件后要能转绿）。

**并号扫描面**同时从「写死 7 份文档」改成「`work/decisions/` 全量 markdown ∪ 登记处」
（登记处自己除外）：摄取范围要**稳定可复现**，并号扫描面要**宁宽勿漏**，两者不是一件事。

### 8.4 回归接线

`scripts/c_run_all_selfchecks.sh` 从 12 个自检增到 **13** 个（加 `c_selfcheck_decisions_registry`），
并新增一步 `c_env_manifest.py --check`（lock 一致性闸，mismatch/missing ⇒ exit 3）。

**`--check` 写独立产物 `runs/infra/c_env_manifest_regression.json`，不覆写默认那份
`c_env_manifest_20260929.json`**：后者是 A 线 `a_env_readiness_gate.py` E6 五个 term 的取值来源
（裁定 37.2 据它解封 A 线）。让一次回归跑就地换掉**跨线消费的权威快照**，
是把「测试」和「发布」混成一件事。要刷新权威快照请单独跑 `c_env_manifest.py`
（它会自动归档上一版，见 §8.2）。

### 8.5 P1-5 / P1-6 落地与**最终实测**（本节数字覆盖 §7.6）

**P1-5（`physical_fact` 接线）已落地**，判据在 `registry/verdict_identity.py::admit_as_physical_fact`
（规则原文 = 同模块 `ADMISSION_RULE`），三处接线与自检见 ADR-C-011。四条验收逐条对上：

| D 的验收 | 落地 | 有牙的证据 |
| --- | --- | --- |
| `ingest_runtime_result` **只吃 `physical_fact`**，非它一律拒收并回显理由 | fail-closed：必须显式给 `verdict=` 或 `observation_only=True`，都不给 ⇒ 抛 `VerdictAdmissionError` 且**一行不写** | 「不声明依据 ⇒ 拒收」+「拒收时帧 0 / 事件 0 / 标签 0」两条断言 |
| `DirectionScore` 自带 `gate_build` + `usable_for`（**身份字段，不是注释**） | 10 个字段进了 dataclass，并出现在 `to_dict()` / bundle manifest 里 | 「身份字段真的进了发布包 manifest」断言按字段名核 |
| `gate_build` 与门禁现值不符 ⇒ **拒收，不是 warn** | 账本与 `build_bundle` 两处都拒；比的是**调用时**的现值 | 「拒收结论里没有 warn 这种软处置字段」+ 错误文本必须含「不是 warn」并点名两个构建号 |
| 重判走 **append-only / 撤销** | 重判 = 追加事件；旧事件序列必须是新序列的**前缀**，payload 逐键不变 | 前缀判定（数「多了几条」抓不到改写中间一条）+ 旧 seq 一个不少 |

**与 B §5 的交点已预先写进验收**：B 的 v1.6 会升 `GATE_BUILD` ⇒ 现存 48 条 `physical_fact`
整批变成「与门禁现值不符」⇒ 准入闸全部拒收、`physical_fact` **48 → 0**。
**那是正确行为，不是回归红点。** 自检里有一条断言专门模拟这一刀（同一条裁定，
`GATE_NOW` 下准入、`GATE_NEXT` 下拒收），另有一条断言核「这句话还写在规则原文里」——
防止日后有人把它当注释删掉，删了之后 48→0 就会被下一个人读成回归。

**P1-6（逐臂 run manifest）已落地**（ADR-C-012）。三字段 `gate_build` / `sha256` /
`is_current_build` 一律取自 `vi.artifact_identity()`，**与 P0-2 同源同义**，靠三件事保证：
`build_manifest` 里**当场核对**（不同源就抛错）、来源映射**写进产物**（`three_field_source`，
读者可核不必读代码）、自检**逐字段**造反例。
一条自检设计的教训值得单记：最初的反面牙改的是 `artifact_identity` 本身 —— **无效**，
因为三字段与嵌入的身份同出一次调用，一起变就永远相等，判据**恒过**。
变异点必须放在 `arm_entry`（模拟「取值路径被换掉」）才造得出真分歧。
**变异体若不能造出分歧，那条判据就是装饰。**

绑定项按 owner 分两类且**绝不代填**：C 能自己算的（lock / 门禁模块 / 四个 C 侧模块）就地取 sha256；
只有 A 能给的（权重 / 数据集 / object seed / 评测 seed 列表 / probe_build）没给就记
`not_bound` + 点名缺哪几项；git 归属由 B 提供，没给记 `not_available`。
**manifest 必须现算**，不能读旧清单：三字段要反映调用时的门禁现值，否则门禁升版后
manifest 会**假装**还是当前构建。为此给 `inventory()` / `scan_dir()` 加了 `collect=` **出参**
（活对象不能塞进返回值——那个返回值要 `json.dumps`，塞进去清单就写不出来了）。

**最终实测（2026-09-29 17:0x，`runs/infra/c_full_regression_20260929_170x.log`，全绿）**：

```
全量回归       17/17 项 exit=0（解释器 /root/venvs/rlrobot/bin/python）
身份层         156/157 PASS + 1 SKIP（诚实 SKIP，不计入通过）
接线（新）      48/48 PASS   runs/infra/c_verdict_wiring_selfcheck.json
run manifest   真产物 246 臂 + 自检 15/15 PASS
               manifest_sha256 = 9d41d6917b15f73edd26b9eeb5afc16ecd9e5a917e1b7e3168fc62f9162a3eb1
               is_current_build 54 true / 192 false；distinct_gate_builds 16
               A 侧绑定 246 臂全部 not_bound（A 未提供，C 未代填）
登记处（新）    77 条决定 / 0 事件；verify 0 red 0 warn；自检 53/53 PASS
               4 条待 ack（ADR-C-009…012，missing=A,B,D，`list --missing-acks` 可查）
golden         conformant=true；171 PASS / 0 FAIL / 1 NOT_ASSERTABLE
账本视图        84/84；发布包 27/27；obs 30/30；契约 6/6；runtime adapter 6/6
T17 goal       44/50 PASS + 6 SKIP（SKIP 全在等 A 的两项，待办 5，不补数）
env manifest   --check PASS：lock 28/28 pin 全中、required 13 项 import 全 OK
               （写 runs/infra/c_env_manifest_regression.json，**未**覆写权威快照）
清单           246 条裁定 / 16 个 build；physical_fact 48、stale_build_evidence 150、
               unidentified_build 24、invalid_measurement 23、not_a_verdict 1
               provenance_kind：frozen_prereg_anchor 48 / ordinary_stale 61 /
               superseded_rerun 37 / deliberate_rejection_probe 4（第六档已清零）
门禁现值        v1.5 / f19f61341cbe / c7fadabe8e3c
```

**C 线待办现状**：1（P1-5）、2（P0-4）、3（P1-6）、9、10 全部**结案**；
4、7、8 此前已结案。**剩两项，都按 D 的明令不动**：
待办 5（T17 真帧）等 A 侧 2 项；待办 6（ξ 锚 / 导出列变更 = 冻结面）D 不批准
（裁定 29.5 第 3 条，等 P1-5 落定后一并看 —— 现在 P1-5 已落定，**请 D 裁**）。

---

## 9. 17:1x–17:2x 冻结收尾（裁定 38.4 / §59 / 增补十六 裁定 39）

本节是 C 线在**冻结时点**的状态登记，依据 `rl_harness_supervision/d_freeze_abc_20260929.md`
（16:58）与 `supervisor_memo_20260929.md` §58–§62（17:11）。**只登记，不新开任务**（冻结规则 1）。

### 9.0 时序诚实登记：冻结单到达时，P1-5 / P1-6 **已经做完了**

| 时刻 | 事件 | 依据 |
| --- | --- | --- |
| 15:37 | D 下发执行单（P0-1…P1-6 六项） | `d_handoff_to_c_20260929.md` mtime |
| 16:40–16:56 | C 落地 P1-5（`harness/ledger.py` 16:40、`registry/release_bundle.py` 16:42、`c_selfcheck_verdict_wiring.py` 16:49）与 P1-6（`scripts/c_run_manifest.py` 16:56、`registry/verdict_identity.py` 16:56） | 文件 mtime |
| **16:58** | **D 下发冻结单**，§3-C3 写「P1-5 / P1-6：登记为冻结时状态，**不追做**」 | `d_freeze_abc_20260929.md` mtime |
| 17:06–17:08 | C 跑完全量回归（17/17）并写回流单请 D 追认边界 | `c_selfcheck_decisions_registry.py` 17:06、`docs/c_handoff_to_d_p1_landed_20260929.md` 17:08 |
| 17:1x | **C 读到冻结单**（本轮上下文重建后第一件事就是重读 D 侧目录） | 本节 |

⇒ C **在读到冻结单之前**已完成 P1-5/P1-6。这正是裁定 39.2 描述的形态（「今天已发生两次
『C 仍是活进程』的交叉提交（`0032ff5`、`e6c661e`）—— 并发追加是**已发生过**的风险，不是假想」）。
**C 的处置**：① **不自行回滚**（回滚会改动三个模块、产生新的红点风险，且"回滚"本身不是 C 的权限）；
② **不声称合规**（冻结单说的是"不追做"，事实是"已做完"，两者不能混为一谈）；
③ 把改动性质如实登记，请 D 二选一：**追认**（改动是加法式、字段带默认值、红线有**显式**逃生口、
17/17 回归绿）或**令回滚**（C 按 D 指定的范围执行）。
**在 D 处置之前，C 不再对这三个模块做任何进一步改动。**

### 9.1 冻结单 §3-C1（P0-4 自查确认）：**已登记**，对应小节号如下

D 的要求是「确认 `work/decisions/decisions_20260929_C.md` 已把 C-F1/C-F2 修法、三条断点、
import 面实测登记进去 …… C 自查后点名『已登记』并给出对应小节号」。自查结果：

| D 点名要的内容 | 登记在 | 小节号 |
| --- | --- | --- |
| **C-F1 修法**（模块探针从「能不能 import」改成**语义探针**：版本号 + 安装来源） | `work/decisions/decisions_20260929_C.md:287` | **ADR-C-009 决定 1**；作用域处置（`rlrobot` 里没有 lerobot 是设计如此 ⇒ `not_applicable`，不是改观测）= **决定 2** |
| **C-F2 修法**（断点是**窗口**不是时刻；窗口必须同源） | 同上 | **ADR-C-009 决定 3**；自测形态（规则有牙 vs 数据自洽各证各的）= **决定 4** |
| **三条断点**（并列不合并，`invalidates` 范围不同） | 同上 | **ADR-C-009 决定 5** |
| **import 面实测**（裁定 37.3 的一般化要求：主张必须给运行时证据） | 同上 | **ADR-C-009 决定 8**（实测产物 `runs/infra/c_ruling_34_1_import_surface_20260929.json`；现成工具 `scripts/c_env_manifest.py --measure-import-surface`）；配套 = **决定 6**（发行版探针走子进程）、**决定 7**（覆写自己 manifest 前留档） |
| 本文的叙事版 | `docs/c_env_manifest_and_pending_impl_20260929.md` | **§8.1**（验收结果与边界）、**§8.2**（覆写留档）、**§8.3**（P0-4 登记处） |
| 登记处条目本身 | `work/decisions/registry/entries/ADR-C-009__*.json` | `verify` **PASS（red=0 warn=0）**；`requires_ack_from=A,B,D`，现 `missing=A,B,D` |

⇒ **确认：已登记**，不是"只活在 manifest 与日报里"。

**登记处计数变更（17:38）**：本节与 §8.5 引用的「77 条」是 **17:0x 的实测值**；
C 随后按冻结单 §3-C4/C5 登记了 **`ADR-C-013`**（冻结收尾 + 两份移交交付物）⇒ 现为
**78 条决定 / 0 事件 / `verify` PASS（red=0 warn=0）/ 自检 53/53**，
`counts_by_line = A:17 / B:14 / C:13 / D:34`，`n_missing_acks = 5`
（`ADR-C-009…012` 缺 A,B,D；`ADR-C-013` **只设 D**，理由见
`docs/c_handoff_to_b2_registry_20260929.md` §6.4：A/B 已冻结、B2 无法用自己的名字 ack，
设了就是永久假红点）。**旧数字不就地改写**（append-only），在此追记以免两份文档不同源。

### 9.2 冻结单 §3-C2（两个探针目录补申报）：**已由作者自行闭合**，C 只读复核

裁定 38.7④ 要求「**作者**须在 README §0 补作者/写入面/边界三行」。C 只读复核结果：

| 目录 | README §0 三行 | 冻结状态 | mtime |
| --- | --- | --- | --- |
| `runs/infra/maniskill_state_probe_20260929/` | **已补**（原申报降为 §0.1；目录名未改，符合 38.7③） | 已写明 38.7⑤ 冻结 + 两个下载工具移交 A2 | 17:03 |
| `runs/infra/robosuite_throughput_probe_20260929/` | **已补**（同上） | 已写明冻结 + 引用纪律（吞吐数字须成对引用 `loadavg` 与 `nr_throttled`） | 17:03 |

两处都写明了 38.7② 的边界（**没跑过任何 policy**，产物全是基础设施事实，任何数字不得被读成能力结论）。
**C 未写入这两个目录**（不在 C 的写入边界内；且 D 指明由作者补）。C 的归属申报在
`docs/c_handoff_to_d_p1_landed_20260929.md` §3（结论：**不是 C 的**，四条只读依据）。
⇒ 该项**闭合**，C 侧无待办。C 继续遵守：未改名、未改内容、**未引用其能力结论**。

### 9.3 冻结单 §3-C3（P1-5 / P1-6 登记为冻结时状态）

| 项 | 实现 | 自检 | 产物（冻结时点） | 冻结时状态 |
| --- | --- | --- | --- | --- |
| **P1-5** `physical_fact` 接线 | `registry/verdict_identity.py`（`admit_as_physical_fact` `:629`、`direction_identity` `:607`、`ADMISSION_RULE` `:590`）、`harness/ledger.py`（`ingest_runtime_result` fail-closed `:377`）、`registry/release_bundle.py`（`DirectionScore` 10 个身份字段 `:128`起、`_require_verdict_identity` `:191`、`VerdictIdentityViolation` `:58`） | `scripts/c_selfcheck_verdict_wiring.py` **48/48** | `runs/infra/c_verdict_wiring_selfcheck.json`（17:01） | **已落地、绿、不再演进**（§9.0 的时序申报适用于此项） |
| **P1-6** 逐臂 run manifest | `scripts/c_run_manifest.py`（三字段只从 `vi.artifact_identity()` 取，与 P0-2 **同源同义**） | `--selftest` **15/15** | `runs/infra/c_run_manifest_20260929.json`（16:56，530,984 B，**246 臂**，`manifest_sha256=9d41d6917b15f73e…`，`is_current_build` 54/192） | **已落地、绿、不再演进** |

**冻结后这两个数字会怎么变（预登记，防止被读成回归红点）**：门禁 build 一变（B 的 v1.6，**或** π₀.₅
建了自己的准入闸），`physical_fact` **48 → 0**、`is_current_build` **54 → 0**、准入闸**全部拒收**。
**那是正确行为**，正确动作是在新 build 上重新出裁定，**不是把闸放宽**。这句话写在三处代码规则原文里，
并有一条断言专门核它还在（`docs/c_handoff_to_d_p1_landed_20260929.md` §5）。

### 9.4 待办 5 / 待办 6 的**终局**处置（冻结后不再推进）

| 待办 | 冻结时状态 | 依据 |
| --- | --- | --- |
| **5** T17 真帧版本 | **不动，且冻结期内不可能推进**。它需要 `lift_B_to_A` 的真帧 teacher 数据（现 **0 行**）；A 的 (乙) 48 臂跨断点重跑已被**取消**（冻结单 §1.1：它只服务被 `01_开发技术方案.md:5` 排除的 ACT 线），A 侧 T17 两项虽已完成，但真帧数据这一前置在冻结期内不会产生 | 冻结单 §1.1；`docs/c_t17_goal_conditioning_20260929.md`；ADR-C-005 |
| **6** ξ 锚 / 导出列变更（= 冻结面） | **结案为不批准**（C 从未动它）。这同时回答了 C 在 17:08 回流单 §2.2 提的那个问题 —— D 已在 §59 明写「**C 待办 6（冻结面变更）不批准**」，列入「仍未裁的项（冻结后不再推进，登记为冻结时状态）」 | `supervisor_memo_20260929.md` §59 末段；裁定 29.5 第 3 条 |

⇒ **C 线待办表清空**：1/2/3/4/7/8/9/10 已结案，5/6 登记为冻结时状态（不追做）。
**冻结后 C 线无待办、无在跑的进程、无未销账的自检红点。**

**一处必须说清的区分（17:5x，按裁定 41.3 补）**：D 在裁定 41.3 里给「反向示范 0 行」这个缺口
找到了现成解 —— ABC-130k（YAM 双臂站）天然带正反任务对（5 对，最多的一对 2574 ↔ 2732 条）。
它**补上的是 A 线量化的那个一般缺口**，但**不是** C 待办 5 的解：待办 5 要的是 **Lift 任务**的真帧
（`lift_B_to_A` teacher），而 ABC-130k 是**另一种形态、另一批任务**。
⇒ 待办 5 的状态**不变**（冻结时状态 = 不动）；ABC-130k 那条路归 **B2 的任务 2**，
它进 C 的账本/视图时的落点已写在 `docs/c_reuse_manifest_for_a2_b2_20260929.md` §5 第 5 条
（`source="teleop"` + `bc_sources` + `supervision_mask`，且引用必须同时给 `morphology_proxy="yam"` 与任务对条数）。

### 9.5 冻结时点全量回归（**17/17 项 exit=0**）

```
runs/infra/c_full_regression_20260929_freeze_171x.log
  mtime   17:16      size 63,628 B
  sha256  cd997d7afaaa1190218e804e79b5aede0966e9a63c67bd0a59a1175d00c79459
  解释器  /root/venvs/rlrobot/bin/python（CPU-only：CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2）
  末行    全绿
```

17 项逐项 exit=0：`selfcheck_ledger_views` / `selfcheck_obs_store` / `selfcheck_release_bundle` /
`selfcheck_harness_contracts` / `selfcheck_runtime_adapter` / `selfcheck_stage3` /
`c_selfcheck_golden_conformance` / `c_selfcheck_verdict_identity` / `c_selfcheck_verdict_wiring` /
`c_run_manifest` / `c_selfcheck_goal_conditioning_t17` / `c_selfcheck_decisions_registry` /
`c_contract_lift_smoke` / `c_contract_lift_takeover_smoke` / `c_learner_shard_smoke` /
`c_env_manifest_check` / `verify_package`。
（16:2x 那一版是 15 项，17:0x 起是 17 项：新增 `c_selfcheck_verdict_wiring` 与 `c_run_manifest --selftest`。）

### 9.6 冻结后保留为**回归基线**的 C 线资产（冻结单 §0 第 2 条：产物转为回归基线）

| 资产 | 路径 | 对 A2/B2 的用法 |
| --- | --- | --- |
| 事实账本 | `harness/ledger.py` | 直接接（入账口径已 fail-closed，见复用清单 §3.4） |
| 观测快照 | `harness/obs_store.py` | 直接接**状态**；图像须先做 §2.3/§2.4 两项实测 |
| 视图派生 | `harness/data_bridge.py` | 不变量照抄；`n`/`H` 必须按 π₀.₅ chunk 重定标 |
| 契约与回放 | `harness/contracts.py`、`harness/runtime_adapter.py` | 契约**一个字不用改**；`driver` 必须换 |
| 参考 learner | `harness/queue_td_learner.py` | **只搬纪律不搬实现**（不在冻结面，可整体换） |
| 发布面 | `registry/release_bundle.py` | B2 的发布面就是它（**不要新造格式**） |
| 裁定身份层 | `registry/verdict_identity.py` | 模式复用；`GATE_MODULE_PATH` 需参数化 |
| 决定登记处 | `work/decisions/registry/` + `scripts/c_decisions_registry.py` | **维护权移交 B2**（`docs/c_handoff_to_b2_registry_20260929.md`） |
| env manifest / import 面工具 | `scripts/c_env_manifest.py`（`--measure-import-surface`） | A2/B2 可**只读调用**，产物写自己目录 |
| **A2/B2 复用清单** | `docs/c_reuse_manifest_for_a2_b2_20260929.md` | 冻结单 §3-C4 的主交付物（8 模块 × 三档，每条带行号） |

### 9.7 复活条件（C **不自行复活**）

冻结单 §0 第 3 条：ACT/Lift 线可被重新启用为**对照或退路**，但**必须 D 登记 + 用户确认**，
**不许三线自行复活**。⇒ C 线在冻结后：不新开任务、不改这 8 个模块、不重跑探针
（`--measure-import-surface` 也不主动重跑），只在 D 或 B2 明确要求时提供只读复核。
**唯一仍开着的两处，都在 D 手上**：① `registry/release_bundle.py` 的写入边界追认
（`docs/c_handoff_to_d_p1_landed_20260929.md` §2.1）；② §9.0 的 P1-5/P1-6 时序处置（追认或令回滚）。

### 9.8 移交前 C 自己撞出的一个**真红**（ADR-C-014）：登记处 CLI 的 `ack` / `annotate` 曾经会崩

执行冻结单 §3-C5（把 `registry/` 移交 B2）时，C 用**命令行**去给 ADR-C-013 追加一条自查批注，
当场崩了：

```
AttributeError: 'Namespace' object has no attribute 'kind'   # scripts/c_decisions_registry.py:783（修前）
```

`ack` **同型崩溃**；`revoke` 正常。根因是字典字面量的**三个值先全部求值**
（`{"ack": …, "revoke": args.kind, …}[args.cmd]`），而 `--kind` 只挂在 `revoke` 子命令上（`:725`）。
**后果**：移交给 B2 的登记处，**验收 3（ack 可核）在 CLI 上是死的** —— `list --missing-acks` 能看，
但**没有任何一条线能通过命令行 ack**。

**为什么 53/53 全绿的自检一条都没抓到**：前 8 案**全在进程内调 API**，没有一条经过 argparse/CLI。
⇒ 缺陷类是「**被测对象与用户使用的对象不是同一个**」；它与"恒真判据"同族但**方向相反**
（不是判据不看东西，而是判据看的是**另一个东西**）。

**修法与牙**（详见 ADR-C-014）：① 惰性取值 `kind = getattr(args, "kind", None) or args.cmd`（修后 `:786`），
并把 `by=... or args.line` 改成 `getattr(args, "line", None)`（`:789`；此前没崩只是因为 `--by` 必填让 `or` 短路，
**那是运气不是设计**）；② 新增第 9 案 `case_cli_surface`（**15 条检查**，自检 **53/53 → 68/68**）：
子进程真跑 `add/ack/annotate/revoke/supersede` 并逐条核后果，再配「把 eager 字典塞回源码副本」的**变异体**，
断言变异体上 `ack`/`annotate` **必须**崩、`revoke` 仍通（**牙不是恒红**），变异生效本身也有一条断言。
**一般规则**：带 CLI 的工具，自检至少要有一条走子进程的用例；**「库的自检全绿」不得被写成「工具可用」**。

**边界**：只改 `scripts/c_decisions_registry.py` 与 `scripts/c_selfcheck_decisions_registry.py`
（都在 C 的 `scripts/c_*` 边界内）；**未改** `harness/`、`registry/*.py`
⇒ §9.0 里"处置前不再改那三个模块"的承诺**仍然有效**。这**不是新开任务**（冻结规则 1）：
交一个 `ack` 命令会崩的登记处给 B2，等于没交。

### 9.9 回归日志的**版本关系**（防止两份日志被并列引用）

§9.5 引用的 `c_full_regression_20260929_freeze_171x.log`（17:16，`sha256=cd997d7afaaa1190…`）是
**修 ADR-C-014 之前**的那一轮。修完之后 C 重跑了一轮：

| 日志 | 时点 | 覆盖范围 |
| --- | --- | --- |
| `runs/infra/c_full_regression_20260929_freeze_171x.log` | 17:16 | P0-4 / P1-5 / P1-6 落地后的状态（**修 CLI 缺陷之前**） |
| `runs/infra/c_full_regression_20260929_freeze2_174x.log` | **17:51** | **冻结时点的最终状态**（含 ADR-C-014 的修复与第 9 案、登记处 79 条 / 1 事件）。**17/17 项 exit=0**、末行「全绿」、64,637 B、`sha256=52d85aba206b8dcbed6f2b11608183f5a4de7e6402161c8596aaefd3eb022c2e`；其中 `c_selfcheck_decisions_registry` 报 **68/68**（日志 `:644`） |

⇒ **引用冻结时点状态请用后者**；前者保留为"修复前"的对照（不删、不改写）。
两轮都是 17 项、都是 CPU-only、都由 `scripts/c_run_all_selfchecks.sh` 一次跑完。

**17:51 之后的变化范围（说明为什么不必再跑一轮全量）**：17:51 之后 C **只改了文档与登记处数据**
（`docs/c_*`、`work/decisions/decisions_20260929_C.md`、`work/decisions/registry/` 的 `add`/`annotate`），
**没有再动任何 `.py`**。登记处是全量回归里唯一对这些数据敏感的一项，已**单独补跑终态核验**（18:0x）：
`verify` **PASS（red=0 warn=0）**、`c_selfcheck_decisions_registry` **68/68**（含「真登记处自检全程只读」那条：
**83 个文件，新增 [] / 删除 [] / 改动 []**）、`list --missing-acks` **6 条**（共 **79** 条决定 / **2** 个事件）。
⇒ **17:51 那份日志 + 18:0x 这次补跑 = C 线冻结时点的完整证据链**，两份不得拆开单独引用。

### 9.10 第二次漏读（裁定 41）：同一处纪律又救了一次

§9 写完后，C 按裁定 39.2 的动作（追加共享文件前先 `git status` + `tail`）准备在 `daily_report.md`
追加 C 线小节，**在日报尾部读到 D 的 17:3x 节**，才发现 **增补十八（裁定 41）**：
它**改判**了裁定 40.3 的形态口径（实机 = 松灵 **Cobot Magic 双臂** ⇒ 动作空间 **14 维**，不是 6+1；
`gym-aloha/AlohaTransferCube-v0` 升为形态一致首选、`SO100GraspCube-v1`/`PickCube-v1` 降为 state 档对照、
`morphology_proxy` 取值变为 `so100_single_arm` / `yam`；ABC-130k 身份确证 = **YAM**、不得当 Piper 契约来源；
**iflytek 关闭**）。

**影响面**：`docs/c_reuse_manifest_for_a2_b2_20260929.md` 的 §2.3（容量推算的几何）、§3.7 第 2 条
（`gpt_rubric`：iflytek 关闭）、§6 第 3 条（动作契约 14 维 / 三列 / `morphology_proxy` 取值）——
**四处全部按裁定 41 更新完毕**，并新增 §5 第 5 条（ABC-130k 正反对进 C 的 BC 视图的落点）。
`harness/` 与 `registry/` **一行未改**（这些裁定不要求 C 改代码，只影响**给 A2/B2 的口径**）。

**这是 C 本轮第二次漏读 D 的文书**（第一次是增补十七，见复用清单头部自查登记）。
两次都被**同一个动作**捞回 ⇒ 那条纪律**不是形式主义**。
**一般规则（与 ADR-C-014 的那条同源，只是对象不同）**：
**"读完了"是一个时刻，不是状态**；在并发仓里，**每次交付前**都要重读一次监管目录的 mtime，
而不是相信自己在开工时读过的那一版。C 把这条登记下来，是因为它**在本轮里两次都是唯一防线**。
