# C2 线任务自述与准入落盘（2026-09-29 20:5x）

作者：**C2**（新线，接 C 线的能力面：账本 / 数据桥 / 登记簿 / 判定身份）。
依据：`rl_harness_supervision/d_handoff_to_c2_20260929.md` **§2（准入格式五项）** 与 **§7（D 的回执与裁定）**。
写入面：本文件 + `docs/c2_*.md` + `runs/vla/c2_*` / `runs/infra/c2_*` + `scripts/c2_*.py` + `daily_report.md` 的 **C2 小节（只追加）**。

> **性质声明（先读这条）**：本文书是**任务自述 + 回执对账**，**不是判据、不是门禁、不构成任何晋级门**。
> 文中所有阈值一律标 `proposed`，须 D 裁定后方可作 blocking。这正是 D §2 要防的事：
> 口述任务不可核，且**一条自设门被反复引用后会获得既成地位**（`daily_report.md`「D 第十二次自我纠错」）。
> 本文书的存在是为了**可核**，不是为了设门。

---

## §0 建线边界（照 D §1 / §3 抄，作为自缚）

- **C 已冻结，C 的产物是冻结面**：决定登记簿 **79 entries**（`verify` red=0 warn=0）、自检 **68/68**、`physical_fact` 接线 **48/48**、逐臂 manifest **246 臂**、全量回归 **17/17 exit=0**（`docs/c_handoff_to_d_p1_landed_20260929.md:9`）。⇒ **接着用 / 接着补，不重做**（重做会让两套自检互相矛盾）。
- **登记簿维护权在 B2，不在我**（`docs/c_handoff_to_b2_registry_20260929.md:1` + 冻结单 §3-C5）。我不改 `work/decisions/registry/` 的机制、工具（`scripts/c_decisions_registry.py`）或自检；**要登记决定走 B2**。
- **主线已改判**（裁定 38 / 46.6）：`robosuite Lift` / 小网络 SAC / `queue_td_learner` 是**辅助实验不是主线**（C 自己写明「任何『learner 已就绪』的说法都不成立」，`docs/ledger_data_bridge_20260928.md:212`）。⇒ **我的工作必须挂到 VLA 主线**，否则就是给降级线加工。
- **不碰**：`RL_Harness_v4_20260924/`（只读）、A/B/C 的产物目录与已验收产物、0928 两份 lock、`arms_summary_v3.json`、`harness/contracts.py`、`harness/runtime_adapter.py`、`configs/`、任何 lock、`/workspace/mnt/sppro/yhzhang91/datasets`、iflytek 端点（裁定 41.4）、原始权重目录 `.codex-persist/hf-cache/modelscope/lerobot/pi05_base`（裁定 44.2）。
- **git：不提交**（裁定 49.6：B 冻结后单写者 = **B2**；D 不提交、A2/C2 不提交）。跨线提醒**保持**：每份报告点名 HEAD 与脏项数，但**不代做**。
- **卫生**：不用 `rm`（走 `recycle_bin`）；覆写自己的产物前留 before 影像 + sha256 前 12 位（裁定 35.1）；目录与脚本一律 `c2_` 前缀，不写无前缀目录。
- **证据**：每个数值主张带 `loadavg` + `nr_throttled`；并行度分母用 cgroup 的 **12 核**不用 `nproc`(=112)；外部事实标 `external_unverified` 且不与本机实测同表（裁定 36.4）；**只有声明值支撑的一律标 `declared_only`，不作 blocking**（D 新立 `operations.redline_provenance_discipline`）。

---

## §1 对 D §7.0 核对表的回应（三档：接受 / 接受但更正口径 / 补充证据）

### 1.1 接受 —— 裁定 48（撤销 `transformers >= 4.57.1` 红线）。D 正确，且我自己读了原文复核

| 事实 | 出处（file:line，我实读） |
|---|---|
| 卫语句不是版本区间，而是 siglip 的 `check` 调用 | `…/lerobot/policies/pi05/modeling_pi05.py:576`–`:584` |
| `check` 全文只接受两个版本 | `…/transformers/models/siglip/check.py`：`return transformers.__version__ == "4.53.2" or transformers.__version__ == "4.53.3"` |
| 该 transformers 是 **git 构建**，非 PyPI | `…/transformers-4.53.3.dist-info/direct_url.json`：`commit_id=dcddb970176382c0fcf4521b0c0e6fc15894dfe0`、`requested_revision=fix/lerobot_openpi` |
| A2 的 lock **记对了**（记的就是 commit） | `runs/vla/a2_env_pi05_sim_20260929/requirements.lock.txt:111` |

⇒ **装 `>=4.57.1` 会让 `check` 返回 False、π₀.₅ 直接加载失败**；D 那条红线若被字面执行会搞坏环境。**改判成立，我接受新红线（锚定 git commit + `siglip.check` 返回 True；`torch==2.6.0+cu124` 不动）。**

**我的错，写清楚**：我上一轮建议「改判 `V-pi05-1`，因为那个下界是 lerobot 的**声明值**不是实测必要值」——**方向碰巧对，理由错**。真实理由不是"声明值不足信"，而是**声明区间与卫语句互斥**。我把"声明值"当成唯一嫌疑、没去读卫语句，**与 D 今天三次纠错同型（读了声明没读实现）**。
⇒ **自缚**：本文书所有阈值 / 下界类主张一律带 `file:line`；只有声明值支撑的标 `declared_only`，且**不得作为 blocking**。

### 1.2 接受结论、更正口径 —— `normalizer_stats` 的 grep 命中数

D 判我「数字错、结论对」。**实质结论双方一致**（事实已被记录、**修复无人认领** ⇒ T-C2-1 成立），但**成因不是数字错，是时刻差**：

| 项 | 我 grep 时（**19:1x**，本轮对话内我自己的 `wc -l` 输出） | 现在（实测） |
|---|---|---|
| `rl_harness_supervision/supervisor_memo_20260929.md` | **1942 行** | **2222 行**，mtime **20:14** |
| `rl_harness_supervision/d_handoff_to_a2_20260929.md` | **314 行** | **488 行**，mtime **19:52** |

D 引的三处实质命中是 `d_handoff_to_a2_20260929.md:431`、`supervisor_memo_20260929.md:2093`（裁定 44.3）、`work/decisions/decisions_20260929.md:1104` —— **全部位于 19:1x 之后追加的行区间**。⇒ **「命中 0」在我跑的那一刻为真；「命中 3」在 20:14 后为真。两者都对，差的是时刻。**
口径我按 D 的要求改：**记录方是 D（裁定 44.3），不是只有 A2**；T-C2-1 与 D 给 A2 的 §12.9 按 §7.2 分工。

**顺带提议一条纪律（`proposed`，请 D 裁）**：本仓有 5 条会话并发追加共享文书 ⇒ **任何 grep / 计数类主张必须同批落 `(mtime, 行数, 命令原文)` 三元组**，否则"命中 0"与"命中 3"会在事后变成互相指控。这与既有的「追加共享文件前先 `git status` + `tail`」同族，补的是**读侧**。

### 1.3 补充证据 —— D 驳回的那条，**证据存在**；但我的引用方式不合格，接受批评

D 读的是 `load_verification.json` 的 **`remap`** 段（确实只有 `n_keys_in_file` / `n_keys_after_fix` / `s`）。**同一份 JSON 另有 `compare` 与 `verdict` 两段**：

- `compare`：`n_compared=812`、**`n_bitwise_exact=812`**、`n_differ=0`、`n_shape_mismatch=0`、`n_ckpt_keys_not_in_model=0`、**`n_model_keys_not_covered_by_ckpt=0`**；其 `model_keys_not_covered_note` 原文：「这些键在 ckpt 里找不到对应张量（也不是 tied 别名）⇒ **它们保持随机初始化**。**若为空，说明权重是完整落进模型的**」。
- `verdict = "all_bitwise_equal"`。
- **生成器实现原文（不是看结论数字）**：`scripts/a2_verify_pi05_load.py:163` 是逐张量 `torch.equal(a, fv.detach().cpu())`；`:183`–`:192` 统计 exact / differ / shape_mismatch / model_only；`:196`–`:198` 的 `ok` = `differ==0 且 shape_mismatch==0 且 model_only==0 且所有 tied 检查 bitwise 相等`。⇒ **`all_bitwise_equal` 这个 verdict 在实现上蕴含「逐位相同 + 无未覆盖（= 无随机初始化）键」。**
- **A2 自己的日报原文（D 可直接复核的共享文书）**：`daily_report.md:3849` ——「**812/812 张量 bitwise 相等**（`torch.equal`）、**0 个 shape 不匹配**、**模型侧 0 个键未被 ckpt 覆盖**（= 没有任何参数留在随机初始化）」；判定 `all_bitwise_equal`。
- **A2 已建议把它抄成断言**：`daily_report.md:3852` ——「B2 建 π₀.₅ 准入闸时，建议把「**812/812 bitwise + 0 未覆盖键**」直接抄成一条断言（本脚本可只读复用）」。⇒ **这条证据不但存在，产出方还要求它进闸**；若记录写成"逐位相同没有证据"，会与 A2 的日报直接矛盾。

**为什么这条必须留在记录里（不是争对错）**：`modeling_pi05.py:995`–`:998` 有一条**静默返回随机权重模型**的路径（`except Exception → print("Returning model without loading pretrained weights") → return model`），`:1046`–`:1047` 又把 `:1021` 的 `load_state_dict(strict=strict)` 异常**吞成一行 print**。⇒ **「加载成功」这句话本身没有证据力**；A2 那份逐位比对是**唯一**能把"加载成功"与"静默随机权重"区分开的东西。若记录写成"逐位相同没有证据"，后人会以为这道防线不存在。
**注**：A2 在 `daily_report.md:3845`–`:3848` 已**独立**指出同一条吞异常路径（「被 `:1046` 的**裸 `except`** 吞成一行 warning 就 `return model`」）⇒ 我与 A2 是**独立复现**，不是转述。

**我接受的元教训（照 D §7.8）**：我只报了数字、没给 JSON 段名与行号 ⇒ **本文书所有主张一律带可复核路径 + 行号**。

**版本影像（裁定 35.1）**：本文件首版 sha256-12 = `dde30c331917`（179 行）；本次为**加法式补充**（只增 §1.3 的三条引用，未改任何既有结论与阈值），改后 sha256-12 见 `runs/infra/c2_selfintake_versions/`。

### 1.4 D 判「成立」的其余六条
不复述，只在 §2 各任务里作为依据引用（`_obs_vector` 静默跳键、`queue_td_learner.py` 不在冻结面、`GATE_MODULE_PATH` 钉死、C 的三个推算/推理数字、B2 的 WARN 极性、A2 的 torch local tag 假红）。

---

## §2 任务自述（每条按 D §2 的五项格式）

### T-C2-1 · 归一化契约层（P0，裁定 49.2 **批准**）
1. **目标**：为 π₀.₅ 造出可复现的 normalizer stats，并把它变成一把**有牙的闸**，使「无 stats → 静默 pass-through → state 通道饱和」这条链在 P1 BC 之前断掉。
2. **挂主线**：v4 `01_开发技术方案.md:355`（首个迭代＝抓空→纠正→数据＋BC→一次 RL 更新→双向评估）的**数据层前置**；裁定 **46.6**（stats 只能来自示范数据集 ⇒ B2 的数据集是 A2 任何有意义 zero-shot/SFT 的 **P0 硬前置**）；裁定 **44.3**（无 stats ⇒ zero-shot 结论必须挂警示）；裁定 **46.2 / 48 / 49.2**。
3. **重叠自查**：按 D §7.2 分工——**A2 管标注口径，C2 管造 stats + 做闸**。B2 产数据集（我**不采数据**，D §4.4 明归 B2）。D 已在 `d_handoff_to_a2_20260929.md:431` 要求 A2 在 G3 报告挂警示 ⇒ **我不重复该要求**，只提供让它可判定的 stats 与闸。**不覆写** A2 的 `pi05_base_compat_lerobot044/`（裁定 44.2 原始权重只读；compat 目录也只读），另存 `c2_*` + diff patch。
4. **产物与判据**：`runs/vla/c2_normalizer_contract_20260929/`、`scripts/c2_build_normalizer_stats.py`、`scripts/c2_gate_normalizer_contract.py`。
   - **复用不重做**：上游 `lerobot/datasets/v30/augment_dataset_quantile_stats.py`（`normalize_processor.py:367` 点名的工具）算 q01/q99；A 线 `scripts/a_patch_dataset_std_floor.py` 的**相对下限公式**（逐维按该维自身量级缩放，非绝对常数）作为 scale 下限起点（**只读复用，不改 A 的文件**）。
   - **闸（每条都要能被具体篡改打红，双向牙，参照 B2 `mutation_verdict.json` 做法）**：
     - `G1 stats_present`：pre/post 两侧 `features` 非空、每维 `q01 < q99`。变异：清空 `features` **必须红**。
     - `G2 silent_passthrough_absent`：断言 `normalize_processor.py:305`–`:307` 那条 `norm_mode` 缺省 `IDENTITY` / `key not in self._tensor_stats → return tensor` 在**本配置下不可达**。变异：删掉任一维 stats **必须红**。（把静默 pass-through 变成响亮失败）
     - `G3 saturation_free`：归一化后 state 14 维**全部落在 [-1,1]**，且逐维对 `ctrlrange` 的可表示行程比例 ≥ `proposed 0.95`。变异：把 `waist` 的 q01/q99 换成手指维的值 **必须红**。（现状实测 waist/forearm_roll/wrist_rotate 仅 **0.3183**、wrist_angle **0.4876** ⇒ 现状**必然红**，这正是牙）
     - `G4 scale_floor`：每维 `q99 - q01` ≥ 该维相对下限。变异：把一个近常量维的分母缩小 10² **必须红**（复现 ACT 线 `|x|` 冲到 **20402** 那个机制）。
     - `G5 cross_morphology_reject`：用 **YAM/ABC130k 的 stats 喂 ViperX300 必须红**（D §7.2 加的牙）。
     - `G6 representation_version`：由宽度与 stats 哈希拼出、不手写（沿用 `harness/obs_store.py:104/:125` 已有的 `normalizer_hash` / `representation_version` 机制，**不新造版本字段**）。变异：改 stats 不改版本号 **必须红**。
   - **阈值提议（`proposed`，D 裁）**：G3 行程比例下限 **0.95**；G4 沿用 A/B 的 `absmax_j` **相对式**而非绝对常数，系数待我用仿真数据实测后在**回流单**提议。
   - **新发现，需写进闸的依据（我读实现原文拿到，带行号）**：`normalize_processor.py:362`–`:377` 的 **QUANTILES 分支同样无下限**——`denom = q99 - q01`（`:370`），保护是 `torch.where(denom == 0, eps, denom)`（`:372`–`:374`），**只在恰好等于 0 时兜底**；与 MIN_MAX（`:349`–`:354`）、MEAN_STD（`:335` `denom = std + eps`）**同型**。⇒ D 裁的「保留 QUANTILES + 补每维 scale 下限」在实现上**是必需的，不是加固**；且「QUANTILES 免疫近常量维炸穿」这类表述若进任何文书即属**恒真式安全错觉**（A 线已把 MIN_MAX 的同型口头表述作废过）。
5. **冻结面**：不需要。原始权重目录与 A2 compat 目录**只读**，我只写 `c2_*`。

### T-C2-2 · obs 键白名单 + 全覆盖断言（P0，裁定 49.2 **批准**，含改 `harness/queue_td_learner.py`）
1. **目标**：让「图像键被静默丢弃」从**形状**变成**不可能**——存入键集合与消费键集合逐键比对，有剩余键即拒，且错误信息点名被丢弃的键。
2. **挂主线**：D **§4.1**（P0，视觉表征缺口）；`docs/ledger_data_bridge_20260928.md:210`（`x_ref` 只重算 flat 状态向量）；v4 `01_开发技术方案.md:355` 那条链路**在数据层就断了**。
3. **重叠自查**：与 D §4.1 的最小切片**互补不重复**——本条管**消费侧不被静默截断**；§4.1 的**存储侧**切片（承载 / 内容寻址 / 往返逐位一致 / 体积纪律）并进 **T-C2-3**。A2 不碰 `harness/`；B2 任务 1 是环境准入闸、不碰 learner ⇒ **无重叠**。
4. **产物与判据**：先**只读复现探针** `scripts/c2_probe_obs_key_drop.py` → `runs/vla/c2_obs_key_whitelist_20260929/`（用真 π₀.₅ 形态 obs：`state` + 三路 224² 图像，**先证伪再修**，证明图像键被静默跳过且宽度检查通过）；再补丁 `harness/queue_td_learner.py`；闸 `scripts/c2_gate_obs_key_coverage.py`。
   - 满足 D §7.3 四条：① **不硬编码键名清单**（从快照/manifest 读）；② **差集为空才放行**；③ **不改变 `state_dim` 语义**、宽度检查仍有效（不废掉 ACT 线既有判据）；④ 错误信息**点名被丢弃的键** + 差集写进产物（「静默失败的反面不是报错，是**报得能定位**」）。
   - **双向牙**：只有 state 的旧快照**仍须绿**（不破坏 ACT 回归基线）；带图像键的**必须红**；变异体：把图像键**改名**后仍须红（证明不是靠键名硬编码）。
   - **交叉引用（D §7.3 末要求）**：与 T-C2-1 在报告里写成**同一根因的两面**（观测通道不被完整消费 / 不被正确缩放），**不拆成两个独立小修**。
5. **冻结面**：`harness/queue_td_learner.py` **不在**冻结面（`docs/ledger_data_bridge_20260928.md:213`「随时可换」）⇒ 裁定 49.2 已批准。`harness/contracts.py`、`harness/runtime_adapter.py`、`configs/`、任何 lock **不碰**。

### T-C2-3 · 重复帧 + `obs_store` 图像容量 + 往返一致实测（P1，裁定 49.3 **批准**）
1. **目标**：把 C 留下的三个**推算 / 推理**数字换成实测，并回答「图像能不能安全进 `ObsStore`」。
2. **挂主线**：D **§4.1** 最小切片；`docs/c_reuse_manifest_for_a2_b2_20260929.md:145`（C 明确要求接真帧前先做重复帧实测）、`:129`（容量是**算术推算**）、`:141`（`harness/obs_store.py:152`–`:161`，`:157` 抛 `StaleObservation`；C 明写「**不主张一定会触发**」）。
3. **重叠自查**：C 点名要 A2 做但 **A2 未做**（`runs/vla/a2_*` 无此产物）。我落 `c2_*`（线前缀纪律优先于 C 的原话）并**在报告里点名移交 A2**（裁定 49.3）。B2 不采数据 ⇒ 不冲突。
4. **产物与判据**：`runs/vla/c2_obs_store_image_probe_20260929/`、`scripts/c2_probe_obs_store_images.py`。
   - **三个数字逐个处置**（裁定 49.3）：147 KB/帧 → 实测；2.6 GB（3 相机 × 20 局 × 300 帧）→ 实测；去重率 → 实测。**不能实测的明确标注「仍为推算」**。
   - **重复帧**：静止场景连采 N 帧，统计逐字节相同对数 + `sampled_at_ns` 分布，实测 `StaleObservation` 是否**真触发**。
   - **往返一致**：存进去的图与取出来的图**逐位相等**（D §4.1 判据）。牙：必须能被「存 uint8 取出 float 未还原」这类篡改打红。
   - **体积**：`np.savez`（`harness/obs_store.py:85/:95`，不压缩）vs `np.savez_compressed` 实测比；NFS `/workspace/mnt/sppro` 已用 **94%** ⇒ 给出「选①压缩 / 选②video-backed」的**实测依据**。牙：容量判据必须能被「少算一路相机」打红。
5. **冻结面**：不需要（只读 `harness/obs_store.py`）。**若结论指向 ②video-backed ⇒ 属接口变更，只报 D 不改。**

### T-C2-4 · 跨线闸极性与变异审计（**P0**，裁定 49.3 批准并提级）
1. **目标**：把「恒真的闸等于没有闸」（裁定 27.1）从口号变成一张**逐闸实测表**。纯只读，**不改任何人的闸**。
2. **挂主线**：裁定 **27.1 / 39.1**（双向牙）、D 新立 `redline_provenance_discipline`；v4 `01_开发技术方案.md:7`「**Harness 的输出也需验证**」的同源要求（验证器自身也要被验证）。
3. **重叠自查**：B2 的 `mutation_verdict.json` 是**它自己那把闸**的自检，A2 的 9 断言是**它自己**的 manifest 自检 ⇒ 都是**自证**。**跨线他证没有人做**，无重叠。
4. **产物与判据**：`docs/c2_gate_polarity_audit_20260929.md` + `runs/infra/c2_gate_polarity_audit_20260929/`。
   - **列**（D §7.4 指定五列 + 追加一列）：`id` / `required` 文案 / **判定极性**（`required` 是否被写成了红条件）/ 有无双向变异体 / 是否恒真或恒假 / **该闸最近一次真实变红的时间与原因**（**从未红过的单独标出**）。
   - **已入表两起（D 独立复核成立）**：① B2 的 `G2_rebuild_lockout_not_default[a2env]`——`expected` 已满足（`actual.same_as_0928=false`、`lock_diff` 已逐包枚举）却报 **WARN** ⇒ 极性/文案反；② A2 的 `manifest_run2_dist_drift_false_red`——`lock_diff.changed` 是 `torch: 2.6.0 → 2.6.0+cu124`、`torchvision: 0.21.0 → 0.21.0+cu124`，而**红线值本来就是 `+cu124`**（裁定 39）⇒ 把 local tag 差当漂移。
   - **新增三起（我今天读实现原文拿到，均带 file:line）**：
     - ③ `modeling_pi05.py:995`–`:998` **静默返回随机权重模型**；`:1046`–`:1047` 把 `:1021` 的 `load_state_dict(strict=strict)` 异常**吞成一行 print** ⇒ 任何以「加载未报错」为绿的判据**恒真**。
     - ④ `normalize_processor.py:305`–`:307`：`norm_mode` 缺省 `IDENTITY`，且 `key not in self._tensor_stats` 时**直接 return 原张量** ⇒ 「归一化已生效」这类判据在缺 stats 时**恒真**（A2 的 `features={}` 正是走了这条）。
     - ⑤ `normalize_processor.py:362`–`:377` **QUANTILES 无下限**（保护只在 `denom == 0` 时兜底），与 MIN_MAX（`:349`–`:354`）、MEAN_STD（`:335`）**同型** ⇒ 见 T-C2-1 第 4 项。
   - **牙（审计表自身也要有牙）**：每条「恒真」判定必须附一个**具体篡改**使其变红；**附不出篡改的不许写「恒真」**。
5. **冻结面**：不需要（纯只读）。

### T-C2-5 · A 线「冻结时产物清单」补齐（P1，裁定 49.3 **批准**）
1. **目标**：让 A 线**可关闭**——五列齐的冻结时清单 + 未销账项登记 + 把**只活在冻结单里的纪律**搬进可检索文档。
2. **挂主线**：冻结单 §1.2 / §1.3 / §1.5（`d_freeze_abc_20260929.md`）。C 线绕路的成因正是「一条纪律只活在一份文书里」。
3. **重叠自查**：A 自 **16:43** 起无写入（冻结单 16:5x 下达 ⇒ §1.2/§1.3/§1.5 未落盘）；D 未派他人做 ⇒ 无重叠。**边界照裁定 49.3：不代 A 表态、不改 A 的文件。**
4. **产物与判据**：`docs/c2_a_line_freeze_inventory_20260929.md` + `runs/infra/c2_a_freeze_inventory_20260929/`（机器承载、可复跑）。
   - **五列**：路径 / **sha256** / **mtime** / 结论边界 / **是否跨断点有效**。（A 现有两张表 `docs/a_env_rebuild_acceptance_20260929.md:331`、`:552` 缺后三列）
   - **必写进去的纪律（裁定 49.3 点名）**：**「`S13` 未补前，任何人（含 A2/B2/C2）不得引用『D8 立即变红』」**。
   - **未销账项按「冻结时状态」登记、不追做**：P0（D8 补 `historical_meta_is_v121` + 变异 `S13`）、P1（迁移断言产物带 `baseline_meta`、sidecar 加 `imageio` 生效版本）、P2（E6 `note`/`:404` 静态散文）。
   - **牙**：清单必须能被「漏一个 A 名下现存产物」打红 ⇒ 用目录扫描做**闭包核对**（A 名下路径全集 vs 清单行数），**差集非空即红**。
5. **冻结面**：不需要（只读 A 的产物，不改任何 A 文件）。

### T-C2-6 · `registry/` 多门禁并存（裁定 49.4 **暂缓不批**）——「待触发」记录
- **事实**：`registry/verdict_identity.py:47` `GATE_MODULE_PATH = ROOT/"scripts"/"b_gate_controlled_success.py"`，**钉死单一 ACT 门禁**；C 已登记「多门禁并存（ACT 冻结基线 + π₀.₅ 新线）口径未实现」。
- **状态**：**待触发，不是沉默缺口**（裁定 49.4 明令「不许让它变成没人记得的沉默缺口」）。
- **触发条件（写死）**：当 **π₀.₅ 线的判定结果需要进 `verdict_identity` / `ReleaseBundle`** 时，由提出方（C2 / A2 / B2）**先写清「主线为什么需要它」并报 D**，届时再裁（与裁定 49.4 对 §5.2 的复活条件同型）。
- **风险不对称**（裁定 47.5(二) 同理）：改了会动到 C 已验收的 **48/48** 接线；**不改没有任何损失**。
- **归属**：`registry/` 维护权在 **B2**（`docs/c_handoff_to_b2_registry_20260929.md:1`）。

---

## §3 与 D §4 推荐任务的对账（D 不指派，我表态）

| D 的推荐 | C2 的表态 |
|---|---|
| **§4.1**（P0 视觉表征缺口） | **接下**，拆成 **T-C2-2**（消费侧白名单）+ **T-C2-3**（存储侧承载 / 往返逐位一致 / 体积纪律）。D 提示的「数据桥必须能把 stats 一起承载」由 **T-C2-1** 的 `representation_version` + `normalizer_hash` 承接（复用 `harness/obs_store.py:104/:125`，**不新造版本字段**） |
| **§4.2**（P1 `ReleaseBundle` 14 role 只有假组件） | **列为后备，本轮不开工**。理由：它依赖 T-C2-1 的 stats 产物与 A2 的**动作前 14 维语义**定案才打得成**真** bundle；先做只会打出第二个假组件。**触发条件（`proposed`）**：T-C2-1 的闸转绿 + A2 的 G2 动作语义定案 ⇒ 由我报 D 开工 |
| **§4.3**（P2 撤销的牙从未真触发） | **先问 B2 是否已在做**（D §2 第 3 项要求），确认无人做再接；**不碰真登记簿**（§1.2） |
| **§4.4** 不建议做的三条 | **我不做**，照抄为自缚：Lift / 小网络 SAC 的成功率优化（已降级）、zero-shot 能力评测（归 A2；裁定 46.6 明确拿到 stats 前不许用它做路线判断）、示范数据采集/转换（归 B2） |

---

## §4 开工顺序与资源申报

- **立即（不需 D）**：**T-C2-4（P0，纯只读）→ T-C2-3（CPU-only）→ T-C2-5（只读汇总）**。
- **已解锁**：**T-C2-1（P0）**、**T-C2-2（P0）**。
- **暂缓**：**T-C2-6**（只写「待触发」记录，见 §2 末）。
- **GPU**：只有 T-C2-1 的验证前向需**秒级** GPU；**>10 分钟一律事前在 `daily_report.md` 申报**（预计时长 / 显存 / 可否中断），单卡优先权在 A2，我按申报制排队。
- **git**：**不提交**（裁定 49.6）。
- **交付顺序**（D §6）：本文书 → 三条产物 → 一份回流单 `docs/c2_handoff_to_d_20260929.md`（做了什么 / 判据是否有牙**附变异自检结果** / 没做什么与为什么 / 需 D 裁的项）→ `daily_report.md` 追加 **C2 小节**（唯一被允许写的共享文书，**追加不覆写**，不动别人的小节）。

## §5 需 D 裁的项（**只列清单**，正文写在回流单，按 D §6.5）

1. **T-C2-1 的阈值**：G3 行程比例下限（`proposed 0.95`）与 G4 相对下限系数。
2. **§1.2 提议的新纪律**：grep / 计数类主张必须同批落 `(mtime, 行数, 命令原文)`。
3. **§1.3 的记录更正**：`load_verification.json` 的 `compare` / `verdict` 段是否恢复为「逐位相同 + 无未覆盖键」的**有效证据**（我主张恢复，并附 `modeling_pi05.py:995`–`:998` 作为它 **load-bearing** 的理由）。
4. **T-C2-3 若结论指向 video-backed obs 存储**（接口变更）。
5. **§4.2 / §4.3 的触发条件**是否照我写的口径登记。

## §6 引用纪律（自缚）

- 本文书**不是判据、不是门禁、不构成任何晋级门**；所有阈值标 `proposed`，须 D 裁定后方可作 blocking。
- 本机主张一律带**路径 + 行号**；只有声明值支撑的标 `declared_only` 且不作 blocking；外部事实标 `external_unverified`，不与本机实测并列同表（裁定 36.4）。
- 跨口径不得并列（裁定 31.3 / 33.4 / 36.4）；吞吐/延迟数字成对引用 `loadavg` 与 `nr_throttled`。
