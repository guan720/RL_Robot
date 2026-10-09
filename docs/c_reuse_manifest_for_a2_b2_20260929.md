# C → A2 / B2 复用清单（2026-09-29 17:1x）：8 个模块「可直接接 π₀.₅ / 必须改 / 已知缺口」

> **任务来源**：`rl_harness_supervision/d_freeze_abc_20260929.md` §3-C4（D 原话：「**这是 C 收尾里最有价值的一件**」）、
> `supervisor_memo_20260929.md` §59 与**增补十六 §62 复核点⑥**（「C 的『A2/B2 复用清单』是否点明**视觉表征缺失已从 P2 升为 P0**」）。
> **性质**：**只读分析**。C 本轮**没有**为 π₀.₅ 改这 8 个模块中的任何一个（冻结单 §3-C3：P1-5/P1-6 登记为冻结时状态、不追做）。
> **口径纪律**：每条判断都给**行号或可复跑命令**；没有行号的不进表。凡属**推算**（非本机实测）一律标注「推算」。
> **C 不代做**：本清单只回答「接进去要改哪几处」，与 A2 执行单 §6 末句一致（「本轮只要求你标出…不要求你改」）。
> 冻结面（0928 两份 lock、`arms_summary_v3.json`、门禁 `requirements.lock.txt`、`clip*.json`）**一处未碰**。
>
> **一处自查登记（17:4x）**：本清单**首稿漏读了增补十七（裁定 40）**，只读到增补十六（§62）。
> 漏读是被**裁定 39.2 要求的动作**捞回来的（「追加共享文件前先 `git status` + `tail`」⇒ 在 `daily_report.md`
> 尾部读到 D 的 17:1x 节）。已按裁定 40.1 / 40.2 / 40.3 补齐三处（§3.7 第 2 条、§5 第 4 条、§6 第 3 条），
> **旧文本就地更新并注明「17:4x 按裁定 40.1 更新」**，不假装一开始就写对了。
> **一般规则**：并发仓里"读完了"是个**时刻**，不是状态 —— 引用监管文书必须带 mtime，
> 且在**每次写完之前**重读一次 D 侧目录（C 本轮的教训是：17:11 的 memo 与 17:1x 的日报都在首稿之后才读到）。
>
> **第二处自查登记（17:5x）**：按上一条规则**再读一次** D 侧目录，又撞上 **增补十八（裁定 41，17:3x）**——
> 它**改判**了裁定 40.3 的形态口径（实机 = 松灵 **Cobot Magic 双臂 ALOHA 类** ⇒ 动作空间 **14 维**，不是 6+1；
> `gym-aloha/AlohaTransferCube-v0` 从"备选"升为**形态一致的首选**；`SO100GraspCube-v1`/`PickCube-v1`
> 降为 state 档对照、`morphology_proxy` 取值变为 `so100_single_arm` / `yam`；
> ABC-130k 身份确证 = **YAM 双臂站**、**不得**当 Piper 契约来源；**iflytek 关闭**）。
> 已按裁定 41.1 / 41.2 / 41.3 / 41.4 更新 **§2.3、§3.7 第 2 条、§5 第 5 条、§6 第 3 条**。
> **两次漏读都被同一个动作捞回**（裁定 39.2：追加共享文件前先 `git status` + `tail`）⇒
> 这条纪律**不是形式主义**：C 在一轮里被它救了两次，第二次差一点就把已被改判的形态口径发出去。

---

## 0. 三档判据的定义（先定义，避免读者按自己的意思读）

| 档 | 定义 | 反例（**不算**这一档） |
| --- | --- | --- |
| **可直接接** | 模块内**不含** ACT/Lift 路线假设；接 π₀.₅ 只需按它的接口喂数据，**不改它的代码** | 「看起来通用」但里面钉了 `lift_*` 常量 ⇒ 属**必须改** |
| **必须改** | 接 π₀.₅ **一定要**动代码或显式换参数，且本清单指出**改哪一行** | 只是"可以做得更好" ⇒ 属**已知缺口**或建议 |
| **已知缺口** | 现在**根本没有实现**，不是改几行能补上的 | 有实现但有 bug ⇒ 属必须改，并报 D |

**另有一档必须单列**：`§9.2 冻结面`。冻结面内的东西即使"必须改"也**不许 A2/B2 自行改**，须 D 批准。

---

## 1. 总表（8 模块）

| 模块 | 可直接接 π₀.₅ 的部分 | 必须改（附行号） | 已知缺口 | 冻结面 |
| --- | --- | --- | --- | --- |
| `harness/contracts.py` | **整体**：事件契约与确定性回放，观测是不透明 `dict[str,Any]`（`:14`/`:33`），对模态零假设 | 无（接 π₀.₅ 不需改） | ①无张量/图像类型约束；②`QueueState` 三队列语义是 v4 的 C/E/D 槽，π₀.₅ 若无抢占队列需显式声明"退化"而不是留空 | 否 |
| `harness/runtime_adapter.py` | 契约事件的产生与推进骨架（`:30`/`:40`/`:64`） | **`driver` 必须换**：默认是 mock 回执 `{"activated": True, "reward": 0.0}`（`:21`）；π₀.₅ 要接真推理 + 真 sim step | 单 request / 单 slot（`:18` docstring 自述），**无多 worker、无真机** | 否 |
| `harness/obs_store.py` | 内容寻址 + 表征版本冻结 + 新鲜度/同步容差判定（`:112`/`:203`/`:222`），**能存任意数值数组含 uint8 图像**（`:85`） | ①`np.savez` **不压缩**（`:95`）⇒ 图像体量需先做容量实测（§2.3）；②同内容不同采样时刻**硬拒**（`:157`）⇒ 真相机重复帧会撞墙（§2.4） | **无视频容器**（LeRobot 数据集是 mp4 + `torchcodec`）；无按模态分通道；无容量/配额闸 | 否 |
| `harness/ledger.py` | **整体**：append-only + SQLite 触发器把改写变硬错误（`:45`）、四种动作量分列、`obs_ref` 列已就位（`:158`）、`goal_id` 逐帧（`:152`） | `ingest_runtime_result` 现在是 **fail-closed**（`:377`）：必须给 `verdict=<裁定身份>` 或 `observation_only=True`，且 π₀.₅ 的 `verdict` 必须出自**π₀.₅ 时代的门禁**（§7） | **`lease_generation` 只是账本字段**（`:153`/`:50`），**无真互斥语义**；无多 worker 签名 | 否 |
| `harness/data_bridge.py` | 四视图派生 + 四种 mask 分离 + 分片导出带 sha256 校验（`:440`/`:740`/`:826`）；**维度零假设**（分片只带 `x_ref`，`:657`） | ①`n` / `chunk_len`（`:440`，缺省 `H=2n`）必须按 π₀.₅ 真实动作 chunk 重定标，`E_k` 取 `[n,2n)` 段是**设计假设**（`:56`）；②`bc_sources` 缺省 `("harness","teleop")`（`:443`）需按 B2 的示范来源核对 | **视觉表征完全缺失**：`resolve_x` 只回原始数组字典、无任何表征重算（`:557`）⇒ §2 | 否 |
| `harness/queue_td_learner.py` | 只值得复用**纪律**：`n`/γ 与 manifest 不符即拒（`:63`）、分片被改过即抛 `ViewExportTampered`、维度不符即 `LearnerRefused`（`:139`） | **整体替换**（π₀.₅ 主干不是 3 层 MLP）。注意它**不在** §9.2 冻结面内（`docs/ledger_data_bridge_20260928.md:213`：「随时可换」） | actor tanh 动作域写死 `[-1,1]`（`:329`）、`XI_DIM=1`（`:51`）、`device="cpu"`（`:82`）、goal 只是 one-hot（`:73`/`:144`） | 否 |
| `registry/release_bundle.py` | **整体**：内容寻址 bundle、双向同 checkpoint 强制（`:235` 内 `BidirectionalViolation`）、原子换版 + 回滚（`:406`/`:443`）、污染留档（`:362`）。B2 执行单 §4.4 明令「**不要新造一套发布格式**」⇒ 就是这一层 | ①`REQUIRED_ROLES` 含 `q`/`q_target`/`optimizer`（`:29`）⇒ zero-shot / 纯 BC 发布**必须显式** `waive_roles`（`:238`，会记进 manifest），**不许塞假组件**；②`gpt_rubric` 角色现在**无法**用真端点填（§3.7）；③`DirectionScore` 的身份字段（`:128`起）必须由 **π₀.₅ 门禁**填，不能沿用 ACT 门禁的 build | `registry/` 里已发布的旧版本（`reach_sac@v1` 等）**没有**被迁成 bundle；14 个 role 至今只有自检里的假组件 | 否（但 `registry/` 维护权本轮**移交 B2**，见 `docs/c_handoff_to_b2_registry_20260929.md`） |
| `registry/verdict_identity.py` | **模式可整体复用**：把上游门禁 import 成身份（不复制判据、不硬编码版本，`:173`）、六档 `usable_for`（`:53`–`:61`）、跨构建对账（`:764`）、append-only 重判（`:908`）、三字段同源（`:565`/`:607`） | ①`GATE_MODULE_PATH` **钉死**在 `scripts/b_gate_controlled_success.py`（`:47`）⇒ π₀.₅ 需要**参数化门禁来源**（或第二个 gate 模块）；②`ARM_SUMMARY_NAME`/`load_arm_index`（`:136`/`:202`）钉的是 A 的 ACT 权威表；③`DELIBERATE_REJECTION_PROBE_DIRS`/`FROZEN_PREREG_ANCHOR_DIRS`（`:98`/`:99`）是 Lift 时代路径常量 | 只认「一个当前门禁」；**多门禁并存**（ACT 线冻结基线 + π₀.₅ 新线）时的口径未实现 ⇒ 需 D 裁 | 否 |

---

## 2. 头号缺口：**视觉表征缺失**（D 已在 π₀.₅ 路线下把它从 P2 **升为 P0**）

D 的升级理由（冻结单 §3-C4）：「π₀.₅ 的输入主体就是图像」。以下四小节是 C 的**只读实测**，用来告诉 A2/B2
这个 P0 具体卡在哪几行，以及**哪一处是静默失败**（静默失败比报错危险，因为它不会让人停下）。

### 2.1 实测：C 的交付面里，视觉通道是 **0 处代码**

```bash
grep -rniE '\b(image|img|pixel|camera|rgb|video|jpeg|png)\b' \
  harness/*.py registry/release_bundle.py registry/verdict_identity.py | wc -l
# 实测输出：0
```

注意一个**读法陷阱**：不加词边界（`\b`）直接 grep `vision` 会命中一堆 `supervision_mask`
（`harness/data_bridge.py:145` 等），看起来像"有视觉代码"。**那是子串，不是视觉通道。**
本清单的所有 grep 结论都用词边界取，命令原样贴在下面各节，A2/B2 可只读复核。

### 2.2 最危险的形状：图像键会被**静默丢弃**，不报错

`harness/queue_td_learner.py:134`–`:140`（`_obs_vector`）：

```python
parts = [np.asarray(obs[key], dtype=np.float32).reshape(-1)
         for key in ("state", "environment_state") if key in obs]   # :134-135 ← 只挑这两个键
if not parts:
    raise LearnerRefused(...)                                       # :137 一个键都没有 ⇒ 拒（好）
vec = np.concatenate(parts)
if vec.shape[0] != cfg.state_dim:
    raise LearnerRefused(...)                                       # :139-140 宽度不符 ⇒ 拒（好）
```

三种情形，**只有第二种是静默的**：

| 快照里有什么 | 行为 | 危险度 |
| --- | --- | --- |
| 只有图像键、没有 `state`/`environment_state` | `LearnerRefused`（`:137`） | 低：**会停下** |
| **同时有 `state` 与图像键**（= π₀.₅ 的真实形态） | **图像键被无声跳过**，训练只用 flat 状态，宽度检查还会**通过** | **高：不报错、不告警，指标照出** |
| 只有 `state` | 正常 | — |

⇒ **给 A2/B2 的第一条硬要求**：接 π₀.₅ 时，obs 键的消费必须是**白名单 + 断言全覆盖**
（「存进 `ObsStore` 的键集合」与「被 collate 消费的键集合」逐键比对，有剩余键就**拒**）。
这与 C 本轮自查出的「恒真判据」是同一家族：**判据没有在看它声称在看的东西**。
C **未改** `_obs_vector`（冻结单 §3-C3；且它在 C 边界内但属"不追做"），只登记这个形状。

### 2.3 存得下 ≠ 存得起：容量是**推算**，接之前必须实测

`harness/obs_store.py:85` 的 `canonical_bytes` 用 `np.savez`（**不压缩**）落 `blobs/<aa>/<sha>.npz`，
存根在 `runs/infra/c_obs_store`（`:31`，NFS）。它能存 uint8 图像（只拒 `object` dtype，`:91`）。

**推算**（算术，**非本机实测**；几何取自 D 裁定 41.2 的**实测值**：ABC-130k/YAM = top + 2 wrist **三相机**、
**640×480**、**30 Hz**（D 实测 29.76 fps）、uint8 ⇒ 单相机单帧 640×480×3 = 921,600 B ≈ **900 KiB**）：

| 配置 | 每帧 | 100 局 × 500 帧 |
| --- | --- | --- |
| 1 相机（640×480） | ≈900 KiB | ≈43 GiB |
| **3 相机（YAM / ABC-130k 的实测布局）** | ≈**2.7 MiB** | ≈**129 GiB** |
| 对照：224×224×3 单相机 | ≈147 KiB | ≈7 GiB |

**（18:0x 补：必须分两条路算，不能拿一个数字盖两件事）** A2 的 G0.5 视觉通道预检**判甲案**
（「能出图且 fps 够闭环评测」，产物 `runs/vla/a2_g05_vision_precheck_20260929/`；**这是 A2 的实测，不是 C 的**），
其中 **π₀.₅ 的真实需求档 = 3 相机 224²**。⇒ 两条路差 **≈6.1 倍**（像素数 640×480=307,200 vs 224²=50,176 ⇒ 6.12×；每帧字节 2.64 MiB vs 441 KiB ⇒ 6.12×，两者同比值，**这条算术 C 现场核过**）：

| 路径 | 几何 | 每帧（3 相机，npz 不压缩） | 100 局 × 500 帧 | C 的结论 |
| --- | --- | --- | --- | --- |
| **离线数据集**（ABC-130k / YAM，裁定 41.2 实测） | 640×480 | ≈**2.7 MiB** | ≈**129 GiB** | **不可行**：不许拷进 `ObsStore`，只能**指针**（团队数据已有 mp4/mcap） |
| **仿真采集**（A2/B2 自己跑，π₀.₅ 需求档） | 224² | ≈**441 KiB** | ≈**21 GiB** | **勉强可行但不划算**：仍建议指针/压缩，且必须先做容量实测 |

⇒ 首稿那句"npz 承载不了"**只对第一条路成立**；第二条路是"承载得起但不该这么存"。
**日报 17:5x C 线小节 §4 第 ② 条引的是第一条路的数字（ABC-130k/YAM 几何），口径与本表一致**；
更细的两路对照以**本表为准**（同一件事只留一处权威数字，避免两份文档各说一半）。

⇒ **结论比首稿硬**：`np.savez` 不压缩的 npz **承载不了 ABC-130k 尺度的图像**。三条独立理由：
① 上表的量级（**推算**）；② D 的体积纪律 —— 该集 README 标 `n>1T`，
「**只许按任务对取子集，不许整集拷贝/转换**（NFS 已用 **94%**）」（裁定 41.2）；
③ 内容寻址只对**逐字节相同**的帧去重，真实相机帧几乎不重复 ⇒ **不能指望去重省容量**。
⇒ **必须改，且 C 的建议是明确的**（不是"二选一再看看"）：**图像不进 `ObsStore`**。
让 `x_ref` 指向**团队数据里的 (episode_id, frame_index) + 既有 mp4/mcap 路径**，
`ObsStore` 只存**状态向量 + 指针 + 采样时刻 + 表征版本** —— 它的 `representation_version` /
`normalizer_hash` / 新鲜度闸（`:203`）全部保留，正好承载 π₀.₅ 的 image processor 配置。
这会动 `obs_store` 的存储布局，属**接口变更 ⇒ 须报 D**（它不在 §9.2 冻结面内，但是 A/B 的对接面）。
**另一条同源的坑（裁定 41.2 实测）**：转换后的 `workplace/ABC130k` episode **缺 `top-camera.mp4`**（D 抽查 4/4），
而原始 mcap **含**固定 top 相机 ⇒ **是转换缺口不是源缺口，可重转补回**。
走"指针"方案前**必须先核这个缺口**，否则三相机里有一路会在训练中途才被发现是空的。

### 2.4 内容寻址去重的**副作用**：同内容不同采样时刻 = 硬拒

`harness/obs_store.py:152`–`:161`：同一个 `obs_ref` 若已存在且 `sampled_at_ns` 不同 ⇒ 抛 `StaleObservation`（`:157`）。
设计意图是对的（**不许把旧内容重打时间戳当新观察**），但在真相机下有一个未实测的触发面：
**逐字节相同的两帧**（静止场景 + uint8 量化、或采集侧重复投递同一帧）会被判成"重打时间戳"而**拒收**。
flat 状态向量下这几乎不触发（连续量），图像下**可能**触发。
⇒ C **不主张它一定会触发**（那是推理，不是实测）；给 A2 的要求是：**接真帧前先做一次重复帧实测**
（同场景连采 N 帧，看有多少对逐字节相同），把结果写进 `runs/vla/a2_*`，不要等它在训练中途中断采集。

### 2.5 表征版本这一层**已经就位**，π₀.₅ 直接用

`ObsStore.put` 强制 `representation_version` 非空（`:125`，空则 `ValueError`）、绑定 `normalizer_hash`（`:104`）与
`features_version`；`assert_single_representation`（`:222`）在一个视图混了多版本时**冻结该视图**而不是静默混用；
`data_bridge.export_views` 传了 `obs_store` 就把每行的 `representation_version` 落进分片（`:740` docstring），
learner 可据此拒混版本批次。
另一条**已有的诚实登记**（不是 C 本轮新发现，但正是这条 P0 的原文）：
`docs/ledger_data_bridge_20260928.md:425` 的模块状态表把 `harness/obs_store.py` 标为
「**已实现未验证** … 参考 learner 只按 `x_ref` 重算过 flat 状态向量，**没有任何视觉表征被重算过**」。

⇒ π₀.₅ 的 image processor / resize / 归一化配置应当**编进 `representation_version` 字符串**并用
`normalizer_hash` 承载，**不要**新造一套版本字段。现成的命名先例：
`scripts/c_contract_lift_smoke.py:58`（`lift-state-proprio50+obj10-v1`，由宽度拼出而非手写，宽度变了自动升版）。

---

## 3. 逐模块细节（总表之外的接线要点）

### 3.1 `harness/contracts.py` —— 唯一**一个字都不用改**的模块

`DecisionRequest.observation` 与 `OutcomeEvent.observation` 都是不透明 `dict[str, Any]`（`:14`/`:33`）；
`EVENT_KINDS` 是调度语义（`:10`），与机器人/模态无关；`ReplayDriver`（`:53`）提供
`request → commit → activate → finish → replay`（`:61`/`:65`/`:74`/`:81`/`:91`）的确定性回放。
**A2 的契约六问**（执行单 §5 G2）应当直接**按这些字段回答**，不要另立词表：
动作维度/单位/频率对应 `ActionEvent.actions` + `frame`（`:24`），终局语义对应 `OutcomeEvent.terminal_kind`（`:33`）。
**缺口**：`OutcomeEvent` 有 `grasp_verified` / `max_rise` / `failure_phase`（`:33`）—— 这三个是 **Lift 任务语义**，
π₀.₅ 换任务后它们**应当留空**而不是复用（复用 = 把新任务的成功判据塞进旧字段名，读者会误读）。
**建议**：新任务的成功判据走 `payload`/新字段并报 D，**不要**借 `max_rise` 装别的东西。

### 3.2 `harness/runtime_adapter.py` —— 骨架可用，`driver` 必须换

默认 `driver` 是 mock（`:20`）；`step(action)`（`:40`）与 `finalize(...)`（`:64`）产出 `RuntimeResult`（`:13`），
后者正是 `ledger.ingest_runtime_result` 的输入（`harness/ledger.py:377`）。
⇒ **π₀.₅ 的最小接线**：写一个真 `driver`（π₀.₅ 推理 → sim step → 回执），其余不动。
**缺口**：单 request / 单 slot（`:18` docstring 自述），**没有多 worker 并发**；A2 若要并行采集，
这一层需要重写或按 worker 分进程（分进程可绕开，但**账本写入的互斥仍是缺口**，见 §4.1）。

### 3.3 `harness/obs_store.py` —— 见 §2（本模块的三条都在那里）

补一条接口事实：`reuse_as`（`:203`）是**新鲜度闸**，超预算或超同步容差即抛 `StaleObservation`（`:217`）；
`bind_decision`（`:166`）把"该快照被哪个决策时刻用过"追加成使用记录、**不改原快照事实**。
π₀.₅ 的推理延迟（A2 的 G3 要测）应当走 `decided_at_ns - sampled_at_ns` 这条既有路径记账，
**不要**新造延迟字段。

### 3.4 `harness/ledger.py` —— 结构可直接接；**入账口径变了**（P1-5 的后果）

三条硬约束（`:1`–`:18` docstring）与 π₀.₅ 无冲突：迟到标签不改写物理事实（触发器，`:45`）、
四种动作量分列（`proposed_action`/`a_rl`/`driver_command`/`measured_state`）、不用 `executed_length`
（逐帧 `chunk_id` + `chunk_index`，`:152`）。
**必须知道的一处变化**（C 本轮 P1-5 落地，`:377`）：`ingest_runtime_result` 现在是 **fail-closed**，
调用方必须二选一：

- `verdict=<裁定身份>` ⇒ 只有 `usable_for == physical_fact` **且** `gate_build` 等于**调用时刻**的门禁现值才准入，
  其余各档**拒收并回显理由**（不是 warn），同时写 `verdict_refused` 事件留档、**不写任何帧/标签行**；
- `observation_only=True` ⇒ 声明这是 env 直出的原始观测/事件，写 `verdict_identity_absent` 事件，
  且下游 `build_bundle` **拒绝**把它翻成 `DirectionScore` 进发布包。

⇒ **B2 的三口径评测器**（执行单 §4.1）产出的成功率数字，要么带 π₀.₅ 门禁的裁定身份走第一条，
要么明确标 `observation_only` 走第二条。**第三条路（不带声明直接入账）现在会抛错**，这是设计如此。

### 3.5 `harness/data_bridge.py` —— 视图与 mask 是路线无关资产；`n`/`H` 必须重定标

不变量清单在 `:1`–`:20` docstring（一个决策槽 = 一个真实接纳的 request；`R_k` 由**旧 C** 产生；
`γ_slot=γ^n` 只算一次；`C_next=U_k` 必须由当时的 next queue 快照证实；终局 `bootstrap_valid=False`；
外部截断**不**当 `done=1`；影子建议永不伪 TD；`unknown` 不是零奖励）。**这些与用哪个 policy 无关**，
π₀.₅ 路线**照抄即可**，它们是 C 线最值钱的部分。
**必须改的两处**：① `n` / `chunk_len`（`:440`，缺省 `H=2n`）与 `E_k` 取 `[n,2n)` 段（`:56`）
是**为 v4 的异步槽语义**定的；π₀.₅ 的动作 chunk（例如 50 步 @50 Hz）必须重新推导 `n`，
否则「一决策槽」与「一次 chunk 推理」对不上，**TD 目标与 BC 监督会同时错**，而分片格式检查不会报。
② `export_views` 的 `unit_convention`（`:740`）会把 γ/n 的**定标状态**（assumed/measured/spec）写进 manifest，
γ/n 或 γ_slot 对不上直接抛（`:761`–`:768`）⇒ **换定标时必须显式换 `unit_convention`**，
不许把 B 的黄金值约定（γ=0.9, n=6）贴到新导出的分片上（`:752`–`:753` 原话）。
**当前状态诚实登记**：`n` 与 γ 的单位仍缺 P0 实测依据（`docs/ledger_data_bridge_20260928.md:214`：
「当前只能标『假设值』」）⇒ π₀.₅ 路线**不要继承这个假设值**，要自己测。

### 3.6 `harness/queue_td_learner.py` —— 整体替换；**只搬纪律，不搬实现**

值得搬的四条纪律（都有对应的拒绝路径，不是散文）：
① `n`/γ 与分片 manifest 不符即拒（`:63` docstring + 实装）；② 分片被改过即抛 `ViewExportTampered`（`:673`/`:826`）；
③ 观测维度不符即 `LearnerRefused`（`:139`）；④ **单 goal 词表被显式拒绝**（`:144`–`:156`）——
理由是 one-hot 恒为 `[1.0]` 时 goal 对输出的影响恒为 0，而**维度/concat/forward 检查全都会过**
⇒ T17「同状态换 goal」连测试都构造不出来（`:69`–`:72` 原话）。
**第 ④ 条正是 B2 任务 3（π₀.₅ 版 T17）需要的护栏形状**：goal 在 π₀.₅ 里是 **prompt 字符串**，
同型风险是「两个方向的 prompt 模板其实一样」⇒ 必须断言**prompt 逐字不同**，且
「同状态、同 θ、只换 goal ⇒ 前向输出必须不同；逐字节相同就是没接进去，判红」（B2 执行单 §3.2 原话）。
**必须改/缺口**：actor 是 3 层 MLP、tanh 动作域写死 `[-1,1]`（`:329`）、`XI_DIM=1`（`:51`）、
`device="cpu"`（`:82`，首版刻意不抢卡）、goal 走 one-hot（`:73`）。**它不在 §9.2 冻结面内**，可整体换。

### 3.7 `registry/release_bundle.py` —— B2 的发布面就是它；三处必须显式处理

**可直接接**：内容寻址 `bundle_id`（`:168`）、双向必须同一 `checkpoint_sha256`（`:235` 内
`BidirectionalViolation`：「分方向各挑最优」在结构上做不到，正好满足 B2 执行单 §4.2 的要求）、
`eval_protocol_sha256` 必须一致、原子换版需 `slot_boundary_confirmed=True`（`:406`）、
chunk 中途热换权重被拒（`MidChunkSwapRefused`，`:50`）、污染留档（`:362`）、回滚（`:443`）、
`deployment_manifest`（`:461`）。
**必须改的三处**：

1. **`q`/`q_target`/`optimizer` 三个 role**（`:29`）：π₀.₅ 的 zero-shot 评测发布**没有** Q 网络。
   正确做法是 `waive_roles=("q","q_target","optimizer")`（`:238`）—— 豁免会**记进 manifest**，可见、可审。
   **不许**造三个假组件把闸喂绿：`MissingComponent`（`:42`）存在的意义就是拦住这件事。
2. **`gpt_rubric` role**（**17:4x 按裁定 40.1、17:5x 按裁定 41.4 更新**）：观察模型**固定** = **dashscope / `qwen3.8-max`**，
   D **亲自跑探针实测**：文本 HTTP 200 / 1.2 s，**视觉通过**（64×64 纯红 PNG 以 data URL 传入，正确回答红色）
   ⇒ 「能吃图像」这条 v4 §6.1 的必要条件**已实测满足**，该 role 现在**可以**用真端点填。
   但三条纪律照抄（`supervisor_memo_20260929.md` §63）：① `intended_primary_observer` **仍写 GPT-6**、
   `actual_provider_model_id` 写实测值，**两者不许混写**；② **iflytek 已关闭**（裁定 41.4，用户裁定：被公司拦截；D 实测 7 个 URL 变体全部 HTTP 403
   = iflytek 自家 WAF，**不是改前后缀能解决的**）⇒ **A2/B2 均不得再打该端点**（WAF 明写"相关行为已记录"），
   B2 任务 5 的 iflytek 补测项**已删除**；**复活条件写死在参数表里**：用户给出未被拦截的端点 ⇒
   用 D 的同一探针补测、**追加为新产物不覆写**；
   ③ **换 provider 不降低校准要求**（v4 `01_开发技术方案.md:7`「Harness 的输出也需验证」）。
   ⇒ 该 role 用 `inline_component`（`:104`）登记**实测端点 + 探针产物 sha256**
   （`runs/vla/d_observer_endpoint_20260929/`），**不许**塞假 sha 冒充；rubric/prompt 正文未定前如实标「未定」。
3. **`DirectionScore` 的 10 个身份字段**（`:128` 起：`gate_version`/`gate_build`/`gate_spec_sha256`/
   `verdict_sha256`/`measurement_valid`/`usable_for`/`provenance_kind`/`is_current_build`/`superseded_by`/
   `regraded_from`）：值必须由 `registry.verdict_identity.direction_identity()`（`:607`）填，
   与 `artifact_identity()`（`:565`）**同源同义**（三字段不另写一套）。π₀.₅ 路线要用
   **π₀.₅ 门禁**的 build 填，**不能**沿用 ACT 门禁的 `v1.5/f19f61341cbe`（§7 说明后果）。
   `build_bundle(require_verdict_identity=True)`（`:242`，默认开）会逐方向核 `usable_for == physical_fact`
   且 `gate_build` 与传入的 `gate_current` 一致，不符即抛 `VerdictIdentityViolation`（`:58`），**不是 warn**。
   逃生口是**显式**的（`require_verdict_identity=False` 且不给 `gate_current`），留给"发布与门禁无关"的场景；
   π₀.₅ 的能力发布**不该**用它。

### 3.8 `registry/verdict_identity.py` —— 模式复用；门禁来源必须参数化

**可直接接的是一套模式**（π₀.₅ 一定也需要它，因为 B2 要建新准入闸）：
`current_gate_identity()` 用 **import** 上游门禁模块取 `GATE_VERSION`/`GATE_BUILD`/`GATE_SPEC_SHA`（`:173`），
**不复制判据、不硬编码版本号** ⇒ 上游一改判据，下游自动跟随，不会出现「C 以为还是 v1.2.1」。
六档 `usable_for`（`:53`–`:61`：`physical_fact` / `pending_impl_ruling_approved` / `stale_build_evidence` /
`invalid_measurement` / `unidentified_build` / `not_a_verdict`）、四类 `provenance_kind`（`:91`–`:95`）、
跨构建对账只在 `is_current_build==true` 子集上做、不同构建改报 `stale_side_not_comparable`（`:112`/`:130`/`:764`）、
append-only 重判（`:908`）、`admit_as_physical_fact` **拒收而非 warn**（`:629`）、
准入规则原文写在代码里并有断言核它还在（`ADMISSION_RULE`，`:590`）。
**必须改的三处**：① `GATE_MODULE_PATH` 钉死（`:47`）⇒ π₀.₅ 需要**可注入的门禁来源**
（`parse_verdict`/`inventory` 已有 `current=` 参数（`:420`/`:972`），缺的是**身份从哪来**这一层）；
② `ARM_SUMMARY_NAME = "arms_summary.json"` 与 `load_arm_index`（`:136`/`:202`）钉的是 A 的 ACT 权威表
（且 D 已指明现行为 **11:45 版**，不是 11:22 版）；③ 两个路径常量（`:98`/`:99`）是 Lift 时代产物。
**已知缺口（需 D 裁）**：本层假设**只有一个当前门禁**。ACT 线冻结后其基线产物仍要被引用（冻结单 §0：
「产物转为回归基线」），而 π₀.₅ 会有自己的门禁 ⇒ **两个 build 轴并存**时的口径未实现。
C **不自行扩展**（冻结单 §3-C3；且这属裁定 29.5 第 3 条那类"冻结面/口径"变更，须 D 批）。

---

## 4. 另外四条已知缺口（原文在 `docs/ledger_data_bridge_20260928.md:201`–`:214`）+ π₀.₅ 下的重估

### 4.1 真 Gateway 独占租约**未实现**（`lease_generation` 只是账本字段）
原文 `:201`。实测：`harness/ledger.py:153`（入参）、`:50`（列定义），全仓 `grep -n 'lease_generation' harness/ledger.py`
只有 4 处，**没有任何互斥/抢占实现**。⇒ 在**裁定 39.2 的四会话并发**下（B 收尾 + C 活进程 + A2 + B2），
这条从 P2 **升为 P1**：并行采集时账本层面**没有**任何东西阻止两个 worker 写同一 `episode_id`。
**给 A2/B2 的最低要求**：并行前先用 `episode_id` 命名空间分家（带线前缀 + worker 号），
并在采集脚本里自己核"没有第二个进程在写同一账本文件"；**不要**依赖 `lease_generation` 提供互斥。

### 4.2 多 worker 签名**未实现**
原文 `:211`。实测：`grep -rniE 'hmac|signature|worker_id|producer' harness/*.py registry/release_bundle.py` ⇒ **0 命中**。
`export_views` 写分片时 `root.mkdir(parents=True, exist_ok=True)`（`harness/data_bridge.py:770`）
⇒ **目录已存在不报错**；`load_views(verify=True)`（`:826`）核的是**同目录内** manifest 与分片的 sha256。
⇒ 组合起来的形状是：**另一个 worker 整目录覆写后，校验仍然自洽通过**。篡改检测拦不住"换了一个生产者"。
**给 A2/B2 的最低要求**：导出目录名带 `run_id` + 线前缀 + worker 号，**一次运行一个新目录**，不复用。

### 4.3 真实 ACT/VLA 主干未接
原文（`:211` 同句、`:209`）：视图分片已被一个**参考 learner** 真实消费过（装配张量、算 target、走反向、参数确实更新），
但「这只是**回放级接线验证**，不等于学习路线打通」。⇒ π₀.₅ 路线**不得**引用 C 的任何 smoke 结果
作为"学习路线可用"的证据。C 的 smoke 只证明**管道通**，不证明**学得动**。

### 4.4 `ReleaseBundle` 的 14 个 role 至今只有自检里的假组件
原文（`:205`）：真实 ACT/SAC checkpoint、normalizer、动作契约、调度配置**还没有被打包过**；
`registry/` 里已发布的 `reach_sac@v1` 等旧版本**没有**被迁成 bundle。
⇒ **π₀.₅ 会是第一个真发布**。B2 做第一次 `build_bundle` 时预期会撞上 §3.7 的三处（waive / gpt_rubric / 身份字段），
那不是 bug，是**第一次真用**必然暴露的接口面；撞到就报 D，不要就地放宽闸。

---

## 5. 给 B2 的四个接线点（B2 执行单 §3/§4 + 裁定 40.1/41.3 的对应面）

1. **goal → prompt 的映射必须内容寻址**：账本与视图逐行带 `goal_id`（`harness/ledger.py:152`、
   `harness/data_bridge.py:657`），但**从 `goal_id` 到 π₀.₅ prompt 文本的映射现在无处登记**。
   建议：把映射表做成 `inline_component(role="task_contract", ...)`（`registry/release_bundle.py:104`）进发布包
   ⇒ 换 prompt 模板 = 换 bundle 身份，做不到"悄悄改 prompt 还说是同一次发布"。
2. **三口径评测器 → `DirectionScore` 字段映射**：`policy 自主成功率` ⇒ `success_rate`；
   `系统最终完成率` / `干预率` ⇒ 现在**没有对应字段**（`DirectionScore` 只有 `flick_frac` /
   `controlled_success_rate` 两个附加位，`:119`–`:120`）。⇒ **需要 D 批**是否加字段（加字段是**加法式**、
   带默认值，与 P1-5 同型；C 不自行加）。在批之前，B2 可以把三口径写进 `notes` + `source`，
   **但发布判定只用 `success_rate` 那一列**，避免"三个数字混在一列里"。
3. **同一 checkpoint 双向合并发布**：结构上已强制（`:235` 的 `checkpoint_sha256` 比对 + `BidirectionalViolation`）
   ⇒ B2 执行单 §4.2 要求的「在结构上做不到冒充」**已经成立**，可直接引用，不必新造机制。
4. **（新增，裁定 40.1 执行项）观察模型校准 = B2 的任务 5**，两条指标**必须分开**：
   **判定一致率**（与环境真值同不同）与**纠正可用率**（纠正动作是否落在允许编辑范围内、是否可执行）。
   D 的原话：「**"模型说得对"不等于"纠正能用"**，**不许合并成一个分数**」。
   ⇒ 在 C 的账本口径里，这两条**天然分列**，不要新造字段：
   判定一致率走 `append_label(label_kind="quality"|"success", ...)`（`harness/ledger.py:191`），
   纠正可用率走 `append_proposal(source="harness_shadow", admitted=...)`（`:223`）——
   **纠正建议是"影子建议"，未进 request 就永远不得伪 TD**（`harness/data_bridge.py:1`–`:20` 不变量清单原话）。
   校准结果进发布包时，**判定与纠正是两个组件**（例如 `gpt_rubric` 与 `reward_view`，`:29`），
   合并成一个 role = 把两条指标混成一列，正是 D 禁止的形状。
5. **（新增，裁定 41.3）B2 任务 2 的第一优先「ABC-130k 离线正反对」⇒ 落点就是 C 的 BC 视图，不要新造**：
   D 实测该集在**同一 station、同一 14 维动作空间**下天然带正反任务对
   （`put_the_credit_cards_into_the_card_holder` 2574 ↔ `take_the_credit_cards_out_of_the_card_holder` 2732 等 **5 对**）。
   ⇒ 进 C 的账本/视图时：`append_frame(source="teleop", ...)`（`harness/ledger.py:152`、`FRAME_SOURCES` `:39`），
   BC 资格由 `bc_sources`（`harness/data_bridge.py:443`，缺省已含 `teleop`）与 `supervision_mask` /
   `bc_action_field`（`:657`）承载；**一条 BC 行只允许一位监督**（参考 learner 里就有这条断言：
   `harness/queue_td_learner.py:266`–`:269`）。
   **两条口径照抄（裁定 41.3）**：① (a) 只支撑「同一 θ 对目标有条件依赖」与 **BC 冷启动**，
   **不得**声称"Piper 上的双向能力"；② 引用必须**同时**给 `morphology_proxy="yam"` 与所用**任务对条数**。
   **一处必须说清的区分**：这批数据补上的是 **A 线量化的那个一般缺口**（`lift_B_to_A` teacher **0 行**），
   但它**不是** C 待办 5（T17 **Lift** 真帧版本）的解 —— 待办 5 要的是 **Lift 任务**的真帧，
   而 ABC-130k 是 **YAM 形态的另一批任务**。C 待办 5 仍按冻结时状态**不动**（§9.4）。

## 6. 给 A2 的四个接线点（A2 执行单 §5 G2/§6 + 裁定 40.2/41.1/41.2 的对应面）

1. **契约六问按 `harness/contracts.py` 的字段回答**（§3.1），不另立词表；Lift 语义字段
   （`grasp_verified`/`max_rise`/`failure_phase`，`:33`）在新任务下**留空**，不借位。
2. **env manifest 口径照抄 A 线**：`probe_kind=semantic`（版本号 + 安装来源），因为
   「`import X` 成功」是**恒真判据**（装上任何版本都过）。现成实现：`scripts/a_env_manifest.py`
   （A 线）与 `scripts/c_env_manifest.py --measure-import-surface`（C 线，可只读调用，产物写自己目录）。
   **裁定 39.1 的三条红线**（torch 必须逐字 `2.6.0+cu124`、不复用 `maniskill_probe` venv、
   不动已验收的 `lerobot_act`/`lerobot_eval`）与 C 的探针口径**不冲突**：C 的探针**只读**回显版本与安装来源，
   正好是 B2 那四条 π₀.₅ 牙（含 V-pi05-4「解析器不得动 torch 栈」）需要的证据源。
3. **契约六问里仍为 `null` 的四项（单位 / 参考系 / 夹爪语义 / 控制频率，裁定 40.2）⇒ 用 C 的既有机制承载，不要新造**：
   - **单位与定标状态**：`data_bridge.export_views(unit_convention=...)`（`:740`）已经把 γ/n 的
     **定标状态**（`assumed` / `measured` / `spec`）写进分片 manifest，对不上直接抛（`:761`–`:768`）。
     π₀.₅ 的动作单位/频率应当走**同一个字段**，让「假设值」与「实测值」在分片层面就分得清
     （C 线现在的 γ/n 仍是**假设值**，`docs/ledger_data_bridge_20260928.md:214` ⇒ **π₀.₅ 不要继承它**）。
   - **动作契约（17:5x 按裁定 41.1 / 41.2 改判）**：绑成 `action_contract` role
     （`registry/release_bundle.py:29`）⇒ 换动作维度/单位 = 换 bundle 身份。
     **动作空间是 14 维（2×(6 关节 + 1 夹爪)），不是 6+1** —— 因为实机是**双臂** Cobot Magic
     （leader–follower 遥操，2 条 follower Piper 臂），裁定 40.3 的"单臂 6+1"前提**已被 D 自己改判**。
     **可直接用的实测值（YAM / ABC-130k，裁定 41.2）**：动作总维度 **14**、**30 Hz**（29.76 fps 实测）、
     **640×480**、夹爪 **[0, 0.998] 归一化**、`intrinsics` 是**单个 3×3 矩阵**（fx 431.88 / fy 431.38 /
     cx 324.26 / cy 240.97 ⇒ RealSense 站），**不是"三组相机内参"**（D 17:0x 误读、已自行更正）。
     **但仍为 `null` 的四项不许猜**（单位 / 参考系 / 夹爪语义 / 控制频率，`02_开发实施指南.md:7`）：
     取不到就留 `null` 并在映射表标 `unknown` / `pending_user`。
     **一条硬纪律（裁定 41.2 第 2 条）**：ABC-130k **不得当作 Piper 的动作契约来源**
     （关节零位/限位/连杆长度/夹爪行程都不同）⇒ A2 契约表**三列**
     （`π₀.₅ 原生` ↔ `ABC-130k(YAM) 实测` ↔ `Piper/Cobot Magic 待实测`）里，
     **第二列的数值不得搬进第三列**。
   - **`morphology_proxy`（裁定 40.3 立、裁定 41.1 改取值，必带）**：本机**没有** Piper/Cobot Magic 数字孪生
     （`mani_skill` 包内 `*piper*`/`*agilex*` **0 命中**）⇒ 仿真产物必须带这个字段，
     **不得**把任何成功率/延迟/契约结论写成「Piper 上成立」。**取值两种**：
     `so100_single_arm`（`SO100GraspCube-v1` / `PickCube-v1`，**降为 state 档的判据与流程贯通对照**，形态 5+1 单臂）、
     `yam`（ABC-130k 离线数据）。**形态一致的首选是 `gym-aloha/AlohaTransferCube-v0`**
     （14 维双臂 + top/2 wrist 三相机，任务本身就是"方块在两区之间转移"，与 v4 `:5` 首场景同型），
     **条件 = A2 的 G0.5 视觉通道可用**；丙案（完全出不了图）**只能由用户裁**，A2 不许自选。
     **C 的建议落点**：把 `morphology_proxy` 写进 `task_contract` role 的 inline payload（`:104`）⇒ **内容寻址**，
     于是一个用代理形态跑出来的 bundle **在结构上无法**被读成实机结论（改字段 = 改 bundle 身份）。
     这比"在报告里写一句声明"强，因为声明会被人忘掉，身份不会。
4. **延迟/显存数字要带负载上下文**：冻结单 §4 要求吞吐/延迟/成本数字**成对引用 `loadavg` 与
   `cpu.stat:nr_throttled`**（本批 746→1612；同一任务两轮差 1.94×）。C 的 `ObsStore` 记
   `sampled_at_ns`/`decided_at_ns`/`sync_error_ns`（`:125`）可以承载**推理延迟**，
   但**承载不了负载上下文** ⇒ 那部分请 A2 自己落在 `runs/vla/a2_*` 里，不要指望账本。

---

## 7. 门禁换代的后果（**预登记**，防止被下一个人读成回归红点）

C 已在三处代码规则原文 + 一条断言里写明（`registry/verdict_identity.py:590` `ADMISSION_RULE`、
`harness/ledger.py:377` docstring、`registry/release_bundle.py:191` docstring）：

> 门禁 build 一变（B 的 v1.6，**或** π₀.₅ 建了自己的准入闸），现存 **48** 条 `physical_fact`
> 整批变成「与门禁现值不符」⇒ 准入闸**全部拒收**、`physical_fact` **48 → 0**、
> run manifest 的 `is_current_build` **54 → 0**。
> **那是正确行为，不是回归红点**；正确动作是在新 build 上重新出裁定，**不是把闸放宽**。

对 A2/B2 的直接含义：π₀.₅ 线**第一天**就会看到 ACT 时代的数字全部落到 `stale_build_evidence`。
这**正是冻结单 §0 第 2 条**（「产物转为回归基线」）在数据层的实现方式：留档、可比、**不当事实用**。
引用旧产物必须带**断点 + sha256**（冻结单 §4），跨断点的主张必须重跑
（`BP-20260929-lerobot-envs-wiped.invalidates` 口径不变）。

---

## 8. 一般规则移交（C 本轮自查出的 6 个判据缺陷，抽成 5 条可复用规则）

出处：`docs/c_handoff_to_d_p1_landed_20260929.md` §4（六条缺陷逐条留档）。这 5 条**与路线无关**，
A2/B2 建自己的闸时同样适用：

1. **一个哈希不要承担两件事** ⇒ 分「决定了什么」（payload）与「含簿记的整文件」两层哈希；
   否则去重/寻址会在加了 `registered_at`、`version_seq` 这类字段后**悄悄失效**，
   失效的样子是"多出一版"而不是报错。
2. **语义相反的引用不要合并判** ⇒ 「指向已撤销」与「指向已被取代」是两件事，
   合并判会让判据**恒红**，而**永不报警等于没有报警**（裁定 31.3 同型）。
3. **期望值不要钉常数，要第二份独立实现现场重算** ⇒ 钉死「B: DR-014」这种期望值会腐烂，
   而腐烂的样子是"测试红"，**会诱导人去改对的实现**。
4. **变异体必须造出真分歧** ⇒ 若变异点与被判据同源（同一次调用），一起变就永远相等，
   判据**恒过**；变异点要放在"取值路径被换掉"的位置。**变异体若不能造出分歧，那条判据就是装饰。**
5. **判据必须真的在看它声称在看的东西** ⇒ 恒真判据（`import X` 成功、`x == x`）与
   标签/断言不同源（标签说"撤销前是绿的"、断言在验撤销后）是同一族缺陷；
   读者只会记住那句散文，所以**散文与断言必须同源**。

---

## 9. 只读复核命令（A2/B2/D 都可以跑，C 不代跑）

```bash
PY=/root/venvs/rlrobot/bin/python
cd /workspace/mnt/sppro/yhzhang91/scripts/xhzhang52/RL_Robot

# §2.1 视觉通道 0 处代码
grep -rniE '\b(image|img|pixel|camera|rgb|video|jpeg|png)\b' \
  harness/*.py registry/release_bundle.py registry/verdict_identity.py | wc -l      # ⇒ 0
# §4.2 无生产者签名
grep -rniE 'hmac|signature|worker_id|producer' harness/*.py registry/release_bundle.py | wc -l  # ⇒ 0
# §2.2 静默丢键的那三行
sed -n '125,141p' harness/queue_td_learner.py
# §3.7 14 个必需 role 与 waive 通道
sed -n '29,34p;235,245p' registry/release_bundle.py
# §3.8 门禁来源钉死在哪
sed -n '46,48p;173,200p' registry/verdict_identity.py

# C 线冻结时点全量回归（17/17 项 exit=0）—— **引用这一份（17:51，含 ADR-C-014 的修复与第 9 案）**
tail -22 runs/infra/c_full_regression_20260929_freeze2_174x.log
sha256sum runs/infra/c_full_regression_20260929_freeze2_174x.log
# ⇒ 52d85aba206b8dcbed6f2b11608183f5a4de7e6402161c8596aaefd3eb022c2e（17:51，64,637 B，内含登记处自检 68/68）
# 修复**之前**那一轮留作对照，不与上面那份并列引用：
#   runs/infra/c_full_regression_20260929_freeze_171x.log（17:16，sha256 cd997d7afaaa1190…）
# 17:51 之后只改了文档与登记处数据（未动任何 .py），终态另核：
CUDA_VISIBLE_DEVICES="" /root/venvs/rlrobot/bin/python scripts/c_decisions_registry.py verify   # ⇒ PASS (red=0 warn=0)
CUDA_VISIBLE_DEVICES="" /root/venvs/rlrobot/bin/python scripts/c_selfcheck_decisions_registry.py # ⇒ 68/68（79 条 / 2 事件）
```

---

## 10. 边界与卫生声明

- 本文件是**只读分析**产物：C 本轮**未改** `harness/contracts.py`、`harness/runtime_adapter.py`、
  `harness/obs_store.py`、`harness/data_bridge.py`、`harness/queue_td_learner.py`
  （上述 5 个模块的最后修改时间都早于本轮：09-24 / 09-28 / 09-29 10:48）。
  本轮 C 改过的只有 `harness/ledger.py`（P1-5）、`registry/verdict_identity.py`（P0-1/P0-2/P1-5）、
  `registry/release_bundle.py`（P1-5，**边界已申报待 D 追认**，见
  `docs/c_handoff_to_d_p1_landed_20260929.md` §2.1）。
- §2.3 的容量数字是**算术推算**，已逐处标注「推算」，**不是**本机实测；§2.4 的重复帧触发面
  C **明确不主张它一定发生**，只要求 A2 接真帧前实测。
- 未用 `rm`；未执行任何 git 写命令（B/B2 是单写者，DR-003 决定 8）；未装任何环境、未下载任何权重
  （裁定 39.1 的三条红线一条未碰）；全程 CPU-only（`CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl OMP_NUM_THREADS=2`）；
  未对 `rlrobot` site-packages 做页缓存逐出（裁定 36.4）；未引用两个无前缀探针目录的**能力结论**
  （裁定 38.7②：只准引用其基础设施事实）。
- 合成数字一律标注**无物理意义**（ADR-C-007）。本文件不含合成数字。
