# C 线：T17 goal 贯通在真实参考 learner 上落地（2026-09-29）

登记方：智能体 C（实体运行时·事实账本·训练视图线）。
依据：`docs/b_handoff_to_c_20260928.md`（B→C 交接单，C-1/C-2/C-3 + §4 + §6 验收）、
监管备忘 增补三 §9-C 与 增补五 §9-C、v4 附录 02 §12「全包 goal 与时间条件」、
交付包 `RL_Harness_v4_20260924/AGENTS.md`「同一目标条件 VLA 学习 A→B 与 B→A」。
本文件是**推导记录**，判据原文在 B 的交接单，C 不复制也不改写 B 的规格。

写入边界：`harness/queue_td_learner.py`、`scripts/c_selfcheck_goal_conditioning_t17.py`、
`scripts/c_contract_lift_smoke.py`、`scripts/c_learner_shard_smoke.py`、
`scripts/c_run_all_selfchecks.sh`。**未改** A/B 任何文件，未改 `docs/b_golden/`，
未执行任何 git 写命令（DR-003 决定 8 单写者纪律）。

---

## 1. 为什么这条是 C 线当时的第一顺位

`decisions_20260928_C.md` 的待办表第 4 项写着「等 B 的参考实现落定再动，避免两边各写一套」。
本轮开工前实测：B 的参考实现已经落定并且自证有牙 ——
`scripts/b_selfcheck_goal_conditioning_t17.py`（1 参考 + 6 坏实现）、
`runs/infra/b_t17/t17_precheck.json`（`teeth_check.non_vacuous = true`，
`n_broken_variants = 6`、`n_runnable_broken_variants = 5`、`n_blocked_variants = 1`）、
`runs/infra/b_t17/t17_mutation.json`。**前置已解除**，所以这条从「等」变成「做」。

同时它是 C 线待办里唯一一条**完全落在 C 写入边界内、CPU-only、不依赖 A/B 在途产物**的项：
待办 1（P0-3 第二层）仍对着移动靶（见 §9），待办 2 要 D 的并号规则，待办 3 要 B 的 commit 归属。

## 2. 三处改动（交接单 §1 表，逐条）

### C-1 `LearnerConfig.goals`：单 goal → 双向词表

`harness/queue_td_learner.py:65` 的 `goals: tuple[str, ...] = ("lift",)` 改为
`("lift_A_to_B", "lift_B_to_A")`。

- **为什么必须改**：单 goal 词表下 `_goal_onehot` 恒返回 `[1.0]`。网络确实
  `torch.cat([state, goal, c, xi])`，**维度检查、concat 检查、forward 检查全都会过**，
  但 goal 那一列是常量 ⇒ 等价于给第一层加一个固定偏置，goal 对输出的影响恒为 0。
  这不是 C 的 bug（对词表外 goal 会 `LearnerRefused`，是诚实的），但它让 T17
  **连测试都构造不出来**（B 的 B1 变异体就是这一类，被判 `blocked` 而非 `pass`）。
- **不是 C 自创词表**：v4 附录 02 §12 与交付包 AGENTS.md 要的就是「同一目标条件学
  A→B 与 B→A」，所以缺省词表天生双向。
- **连带**：真帧通道的 `goal_id` 必须落在词表内，否则 learner 会（正确地）拒绝装配。
  `scripts/c_contract_lift_smoke.py` 新增 `GOAL_VOCAB` / `GOAL_ID` 两个常量作为**单一事实源**，
  `replay_into_contract(goal_id=...)` 的缺省从 `"lift"` 改为 `GOAL_ID`；
  `scripts/c_learner_shard_smoke.py` 从该模块 import，不再自己写一份字面量。
  合成终局通道的 `EpisodeBuilder(..., goal=GOAL_ID)` 同步显式传参。
- **不影响 B 的黄金值对账**：`scripts/c_selfcheck_golden_conformance.py` 的三处
  `LearnerConfig(goals=("A_to_B",))` 走的是 `build_nets` + 直接构造 goal 张量的路径，
  **不经** `_goal_onehot`（该脚本从不调用 `load_shard_batch`），所以 C-2 的守卫不会打到它。
  本轮全量回归实测 `golden_conformance` 仍 **PASS 171 / FAIL 0 / UNRESOLVED 0 / NOT_ASSERTABLE 1**。

### C-2 `_goal_onehot`：`goal_dim < 2` 时显式拒绝

按交接单 §1 给的「最小可接受形态」落地：**不改 embedding**，改为显式拒绝。

- **为什么选拒绝而不是 embedding**：改 embedding 会改变 `cfg.x_dim()`，而
  `c_selfcheck_golden_conformance` 的 E1–E6 是按 one-hot 的 `x_dim` 与 B 规格逐条对账的
  （γ=0.9 / n=6 / H=20 / C[0,6) E[6,12) D[12,20)）。为了一个表征选择去扰动已冻结的
  规格一致性面，收益不抵风险。one-hot 在 `goal_dim ≥ 2` 时是**合法**的 goal 表征，
  T17-a/c/d 全过（§3）。故取 B 明写的「或至少在 `goal_dim == 1` 时显式拒绝」那一支。
- **拒绝理由必须可诊断**：报错串里点名「one-hot 恒为常量」「不能声称
  goal-conditioned」「T17 构造不出来」，并回显实际词表；同时给出出路
  （要跑单 goal 的规格算例请直接构造 goal 张量，不要经 `_goal_onehot`）。
- **价值**：把「无法验证」变成「拒绝启动」，而不是让一个恒真的维度检查冒充验收。
  这条与 `docs/b_reproducibility_incident_20260928.md` §2 缺陷 3 的恒真检查是同一类风险。

### C-3 T17-a/c/d/e 落成单元测试

新增 `scripts/c_selfcheck_goal_conditioning_t17.py`（**只依赖 torch + numpy**，
不 import robosuite / mujoco）。

- **为什么刻意不依赖渲染栈**：T17 验的是**计算图**，不是真机能力。把它绑到 MuJoCo/EGL/GPU
  上，等于让一个纯结构性断言被无关的可用性阻塞 —— 本轮就实测到这种阻塞真实发生过（§10）。
- **不另立事实源**：观测走真实 `ObsStore`，时间轴复用 `selfcheck_ledger_views.EpisodeBuilder`，
  链路是 `FactLedger → ObsStore → db.build_views → db.export_views → ql.load_shard_batch`。
  所以本脚本验的不只是网络，还包括 **goal_id 能否从账本一路活到张量**
  （中间任何一处丢掉 goal，T17-a 就转红）。
- **合成表征版本号刻意不复用 Lift 的**：用 `t17-synthetic-state60-v1`。
  若在这里写 `lift-state-proprio50+obj10-v1`，就等于凭空多出第二个「Lift 表征版本」事实源，
  而那份版本号归 `c_contract_lift_smoke.REPR_VERSION` 独家生产（由宽度拼出，ADR 见 §2.4 日报）。
- **词表也不抄**：`DEFAULT_VOCAB` 由 `ql.LearnerConfig.__dataclass_fields__["goals"].default`
  读出。抄一份字面量到这里，等 C-1 的缺省变了而脚本没跟着变，测试就会对着一个不存在的
  词表绿着 —— 那是恒真断言的另一种形态。

## 3. T17 断言的落地形态与阈值来源

阈值**原样取自交接单 §2 表**，C 未调整任何一个：

| 断言 | 落地形态 | 阈值 | 实测 |
|---|---|---|---|
| T17-a | 同一批真实 state/c/ξ，只换 goal one-hot，逐组件比输出 | `not allclose(o0, o1, atol=1e-9)` | 4 个已实现组件全改变 |
| T17-c | one-hot 分支：第一层权重在 `[state_dim, state_dim+goal_dim)` 切片上的梯度 | `abs().sum() > 0` | actor `2.868e+01`、critic `6.464e+00` |
| T17-d | `d_goal / d_state`，`d_state` 用 `h + 0.1·randn`（种子固定） | `> 0.05` | `8.084e-03 / 5.993e-03 = 1.3490` |
| T17-e | 词表外 goal `lift_C_to_D` 必须被拒 | 抛 `LearnerRefused` 即通过 | 通过（且**不是** `KeyError`） |

- T17-c 走 one-hot 分支（交接单 §2 明写：embedding 才走 `goal_table.weight.grad`）。
- T17-d 的扰动用 `torch.Generator().manual_seed(SEED)`，不用全局 RNG ⇒ 跨进程逐位可复现，
  且不扰动其它断言的随机状态（与 `perturbation_invariance_probe` 用 `linspace` 同一动机）。
- critic 的动作位用**固定** E（`linspace`）而不是 actor 的实时输出：否则 actor 瞎了也会
  通过 critic 表现出来，B6（只验标量会漏掉）那类缺陷就抓不住。

## 4. 五组件覆盖：4 个 PASS，3 个 **SKIP**（SKIP ≠ PASS）

附录 02 §12 要求 base / editor / Q / 候选筛选 / 预测器**分别**验。C 的参考 learner
首版只实现了其中两个，另加两个 target 网络（B 的参考实现没有 target 网络，故未覆盖）：

| 组件 | 状态 | 说明 |
|---|---|---|
| `base(actor)` | **PASS** | `DeterministicActor`，只输出 E 段 |
| `Q(critic)` | **PASS** | `QueueCritic`，动作位是 H 长块 |
| `actor_target` | **PASS** | 不在五组件内，但 `td_targets` 的 bootstrap 全由它产生 |
| `critic_target` | **PASS** | 同上；goal 不进 target ⇒ TD 目标 y 就不是 goal 条件的 |
| `editor` | **SKIP** | 首版未实现 |
| `candidate_filter`（候选筛选） | **SKIP** | 首版未实现 |
| `predictor`（预测器） | **SKIP** | 首版未实现 |

按 ADR-C-004：SKIP 记 `ok=None`，**不计入通过也不计入失败**，汇总行写成
`44/50 PASS（6 SKIP）`（T17-a 与 T17-c 各 3 条 SKIP）。
**必须明写的结论：这三个组件本轮未被验证。** 实现后必须补测，不得因为「其余全绿」
就当五组件全覆盖。

## 5. 变异自检 M1–M6：每个变异抓什么

C 的纪律是「只测正向等于没测」（ADR-C-001 的 M10/M11 = 把修复前行为重新注入）。
本轮 6 个变异体，其中 **M3 / M5 是 B 参考实现覆盖不到的**：

| 变异 | 注入方式 | 被抓于 | 为什么需要它 |
|---|---|---|---|
| M1 actor 丢 goal | `DeterministicActor.forward` 里 goal 置零 | T17-a(actor) | B6 同构：只验标量/只验 critic 会漏 |
| M2 critic 丢 goal | `QueueCritic.forward` 里 goal 置零 | T17-a(Q) | 同一变异下 actor 仍敏感 ⇒ 证明**逐组件**必要 |
| M3 `actor_target` 丢 goal | 只覆盖**实例** `forward`（不动类） | T17-a(actor_target) | 在线网络全对但 bootstrap 不是 goal 条件的；B 的参考实现无 target 网络，覆盖不到 |
| M4 one-hot 无视 goal_id | 猴补丁 `_goal_onehot` 恒返回第一个方向 | T17-a | 装配层就被污染，两个方向输入相同 |
| M5 第一层被冻结 | `net[0].weight.requires_grad_(False)` | **T17-c**（T17-a 仍过） | 证明 T17-c 有**独立于 T17-a** 的牙齿：goal 影响存在但参数收不到梯度 |
| M6 单 goal 词表 | `goals=("lift",)` | C-2 守卫显式挡下 | 「构造不出来」必须被**挡住**，不能静默通过 |

M5 是本轮方法学上最值得留的一条：它证明 T17-a 与 T17-c **不是冗余的两条**，
只测「换 goal 输出会变」抓不到「goal 影响存在但学不到东西」。

另有 C-2 自己的可证伪反证：把守卫拿掉（重注入修复前的 `_goal_onehot`），
单 goal 词表下同一调用**静默返回 `[1.0]`** ⇒ 缺陷确实存在过，不是断言在打空气。

## 6. ξ 覆盖面普查（交接单 §4）：实测比例 **100%** ⇒ 判定为**实质缺口**

B 的请求只有一条：把「BC 行恒在 ξ=0」这个已声明的近似，从「写在 notes 里」升级为
「每 batch 可量化」，并给出**显式结论**（B §6.5：两种都接受，要的是显式而非沉默）。

落地：`harness/queue_td_learner.py::load_shard_batch` 逐 batch 计数，挂到
`ShardBatch.xi_census`，并把量化后的结论追加进 `notes`：

- `td_rows_total` / `td_rows_at_xi1` / `td_rows_at_xi1_ratio`
- `bc_rows_total` / `bc_rows_at_xi0` / `bc_rows_at_xi0_ratio`
- `bc_anchor_covers_xi1`（bool，显式结论位）
- 无 BC 行时比例记 `None`，**不伪造 0/0**

**C 的显式结论（回答 B §4 的提问）**：BC 行按构造 100% 落在 ξ=0（C 无法从分片重建，
BC 行没有前后槽链），而 TD 侧存在 ξ=1 的行、`next_xi` 恒为 1。
按 B 给的判据（「比例是 100% 还是 12% 决定这句话是已知近似还是实质缺口」），
**这是实质缺口**：`L_actor = −E[Q] + λ_BC·L_BC + λ_cont·L_continuity` 里的 λ_BC 锚
只在 ξ=0 的输入半空间施力，所以「有 BC 锚保护」这个主张**在部署区间（多数决策态 ξ=1）
没有证据**。

**真帧实测（`runs/infra/c_learner_shard_smoke.json`，本轮全量回归产物，46 项断言全过）**：

| 通道 | `bc_rows_at_xi0 / bc_rows_total` | 比例 | `td_rows_at_xi1 / td_rows_total` | 判定 |
|---|---|---|---|---|
| `clean`（无接管） | 0 / 0 | `None`（无 BC 行，**不伪造 0/0**） | 9 / 10 | 无缺口可言 |
| `takeover`（帧 F 起接管） | **28 / 28** | **1.0 = 100%** | 3 / 4 | **`substantive_gap`** |
| `terminal`（合成终局槽） | 0 / 0 | `None` | 1 / 2 | 无缺口可言 |

⇒ 唯一有 BC 行的通道上比例是 **100%**，`bc_anchor_xi0_gap.verdict = "substantive_gap"`，
`channels_with_gap = ["takeover"]`。B 问的「100% 还是 12%」有了确定答案：**100%**。

- **性质**：这是**现状登记**，不是失败项。首版无法从分片重建 BC 行的 C，
  修它要动导出列 = 冻结面变更（`docs/ledger_data_bridge_20260928.md` §9.2），
  属 v4 既定项，不在 learner 侧偷偷补 ⇒ 只如实标注，不让 `pass` 变红。
- **修法（登记，不在本轮做）**：harness 纠正也走 request/commit 之后，BC 行就有前后槽链，
  C 可精确重建、ξ 可为 1；届时 `bc_anchor_covers_xi1` 应转 `true`，本条缺口自动闭合。
- **验收方式**：`c_learner_shard_smoke` 的三条普查断言（行数自洽 / 与张量独立复算逐值相同 /
  无 BC 行时比例为 None）+ T17 脚本的 5 条；报告里新增 `bc_anchor_xi0_gap` 段
  给出逐通道比例与 `verdict`。

## 7. 两处精度更正的落地（交接单 §3）

- **§3.1 T17-e 的异常类型**：C 抛 `LearnerRefused`（继承 `RuntimeError`），
  **不是** `KeyError`。断言按 B 的更正写成 `LearnerRefused`，并**额外钉一条**
  「`LearnerRefused` 不是 `KeyError` 的子类」—— 防止日后有人把它改成 `KeyError`
  让 B 的旧写法蒙对（那会让两侧各测一个东西，共因失效看不出来）。
  另加一条「拒绝时不返回任何向量」，堵住「先降级成零向量、再补一条警告」的假拒绝。
- **§3.2 ξ 不是恒零**：B 的更正与 C 的实现一致，本轮复核确认无需改动
  （`xi = [1.0 if contiguous else 0.0]`，`next_xi` 恒 `[1.0]`）。§6 的普查正是建立在这个语义上。
- **交接单 §5 #6（E6 两个独立拒绝理由）**：复核确认**已满足**，无需改动 ——
  `harness/data_bridge.py` 的 `goal_epoch_incompatible`（U 到达时 in-force 的 goal/epoch
  已不是请求时那一个）与 `deadline_miss`（晚到）是**两条独立理由**，代码里并排 append，
  注释明写「晚到 + 换向必须同时留下两条理由」；两者都在 ADR-C-001 F3 的 `CENSORING_REASONS` 里。
  T17 只管计算图，没有把这两个理由合并。

## 8. 真贯通仍缺的两项（**不在 C 边界内**，交接单 §5 已交给 A）

C 扩了词表 ≠ 贯通完成。仍需 A 侧到位，否则真机数据依然发的是 `'lift'`：

1. `scripts/run_act_lift_runtime_failure_audit.py:36,39` 的 `goal_id` 硬编码；
2. policy 不接收 goal（`scripts/train_act_lift.py` 及 LeRobot 训练侧），且 BC 采集时就要按 goal 分组。

**C 侧的现状是诚实的**：真机数据若仍发 `goal_id='lift'`，learner 会
`LearnerRefused`（词表外），**不会**静默当成某个已知 goal 训下去。
这条拒绝行为本身就是 T17-e 断言的内容。

## 9. C 线待办 1（P0-3 第二层）为什么本轮**仍不接线**

`decisions_20260928_C.md` 待办 1 的阻塞理由是「当前构建下 `physical_fact = 0` 条，
此刻接线等于对着移动靶写死结构」。本轮开工前实测 `runs/infra/c_verdict_identity_inventory.json`
（2026-09-29 09:39，当前构建 **v1.4 / `b9379fdb1089`**）：

- `usable_for` 分布 = `stale_build_evidence 129 / unidentified_build 24 / invalid_measurement 18
  / **physical_fact 15** / not_a_verdict 1`；183 文件 / 187 条裁定，同目录并存 **15 个** `gate_build`。
- 但那 15 条 `physical_fact` **全部**出自 `ckptseq/v14_crosscheck`；
  48 臂权威表所在的 `regate_current` 仍是 `stale_build_evidence 41 / invalid_measurement 7`，
  即 **48 臂表在当前构建下 `physical_fact` 仍为 0**。
- 且 A/B 之间还开着免罪册条目的分歧（`docs/a_handoff_to_b_probe_exoneration_gap_20260928.md`：
  三分类 25/22/1 vs 24/22/2），D 本轮上午的 48 臂重判还只在 `tmp/agentD_review_20260929/`
  （**scratch，不是权威产物**）。

⇒ 阻塞**部分**解除（身份层已有 15 条真 `physical_fact` 可对齐），但权威 48 臂表未定。
按裁定 16 的顺序纪律，此刻把 `DirectionScore` / `ingest_runtime_result` 接到某一批数字上，
仍会在权威表刷新时重做一次。**本轮不动**，等 A 的迁移闸（`docs/a_handoff_to_b_probe_exoneration_gap_20260928.md`
§4 / `scripts/a_migration_gate_preflight.py`）与 D 的会签落定。
待办 2 仍需 D 的并号规则，待办 3 仍需 B 的 commit 归属。

## 10. 环境事件（必须报，影响四线）：venv 被服务器检修清掉

- **现象**：`/root/venvs/rlrobot` 整个目录消失（`ls /root/venvs/` 不存在），
  `~/.codex/sessions/2026/09/28/` 也一并没了（9/28 四线的 rollout 无法直接检索，
  本轮上下文是从盘上产物重建的）。`scripts/_venv.py` 的 docstring 早已预警：
  「venv 在容器 overlay 上，重启会丢」。
- **影响面**：`c_run_all_selfchecks.sh` 硬编码 `PY=/root/venvs/rlrobot/bin/python`，
  C 的全量回归、A 的 GPU 训练、B 的可复现性门禁**同时**失去运行环境。
  conda base 只有 torch 2.4.1 + numpy 1.26.4，缺 mujoco / robosuite / gymnasium / py_trees / pytest。
- **处置**：`runs/infra/c_env_rebuild_20260929/rebuild.sh`（C 侧脚本，日志 `rebuild.log` / `rebuild2.log`）。
  与 `scripts/setup_env.sh` 同一套包，但**刻意不做**两件越界的事：
  ① 不覆写仓库根的 `requirements.lock.txt`（候选清单写到
  `runs/infra/c_env_rebuild_20260929/requirements.lock.candidate.txt`，由 B/D 决定是否采纳）；
  ② 不跑 `scripts/b_selfcheck_reproducibility.py`（那会写 `runs/infra/b_*`，属 B 的产物目录）。
- **第一次失败与根因（值得留档）**：按 `setup_env.sh` 的**范围 pin** 装会被解析器判死 ——
  `robosuite 1.5.2 → mink==0.0.5 → numpy<2.0.0`，与 `numpy>=2` 冲突（`ResolutionImpossible`）。
  venv 原装 pip 24.0，升到 26.2.1 后解析器更严、会回溯到 `mink 0.0.5`。
  但 `requirements.lock.txt` 是 9/28 那次**实际装成并跑通全量回归**的 freeze
  （`mink==1.2.0` + `numpy==2.4.6` + `robosuite==1.5.2` 三者共存）。
  ⇒ 改按 lock 精确复现 + `--no-deps` 跳过解析。**解析器到不了这个组合，不代表这个组合不可用。**
- **重建后实测**：numpy 2.4.6 / mujoco 3.9.0 / robosuite **1.5.2** / gymnasium 1.2.3 /
  py_trees / stable_baselines3 2.7.1 / torch 2.4.1+cu124 / pandas 3.0.3 / pyarrow 24.0.0 /
  scipy 1.17.1 / pytest 9.1.1 / numba 0.67.0 全部 OK。
  robosuite 版本是 1.5.2 ⇒ 改判 3 的可复现性前提（robosuite 1.5.2 + `env_factory` 物体 pin）未被破坏。
- **给 D/B 的一条建议（不代做）**：`setup_env.sh` 的范围 pin 与 lock 已经不一致，
  下次在任何一台新机器上按 `setup_env.sh` 装都会撞同一个 `ResolutionImpossible`。
  建议把安装步骤改成「优先 `-r requirements.lock.txt --no-deps`，lock 缺失才回退范围 pin」，
  并把 pip 版本一并记进 lock。该文件不属 C 的写入边界，C 不改。

## 11. 验收对照（交接单 §6，B 会按这个判）

| # | B 的要求 | C 的落地 | 状态 |
|---|---|---|---|
| 1 | `cfg.goals` ≥2 项，且 `_goal_onehot` 在 `goal_dim<2` 时显式拒绝 | §2 C-1 / C-2 | **完成** |
| 2 | T17-a/c/d/e 落成单元测试并全过（异常类型按 §3.1） | §3 / §7，`scripts/c_selfcheck_goal_conditioning_t17.py` | **完成**（3 组件 SKIP，见 §4） |
| 3 | B 的 `teeth_check.non_vacuous` 仍为 `true` | 本脚本 `case_b_teeth_still_non_vacuous` 用 `--json-out` 复跑 B 的脚本（输出写 C 的目录，不碰 `runs/infra/b_t17/`） | **完成**：`non_vacuous=true`、6/6 坏实现仍被抓 |
| 4 | B 的 `b_selfcheck_golden_values.py` 仍 47/47、`b_selfcheck_t17_mutation.py` 仍 6/6 | 归 B 只读复核（B §6 明写「B 侧不需要 C 通知即可复核 3/4」）。C 侧对应证据：`c_selfcheck_golden_conformance` 仍 **171/0** | **未受影响** |
| 5 | `bc_rows_at_xi0 / bc_rows_total` 计数落地，或明确判定 notes 已足够 | §6：计数**已落地**，并给出显式结论 = 实质缺口 | **完成（取前者）** |

## 12. 产物索引与复跑命令

- 代码：`harness/queue_td_learner.py`（C-1/C-2/ξ 普查）、
  `scripts/c_selfcheck_goal_conditioning_t17.py`（新增）、
  `scripts/c_contract_lift_smoke.py`（`GOAL_VOCAB`/`GOAL_ID`）、
  `scripts/c_learner_shard_smoke.py`（词表 + 普查断言 + `bc_anchor_xi0_gap` 段）、
  `scripts/c_run_all_selfchecks.sh`（接入新脚本）
- 产物：`runs/infra/c_t17_goal_conditioning.json`（含 `impl_sha256`、阈值、逐组件 delta、
  ξ 普查、B 牙齿复跑结果）、`runs/infra/c_t17_goal_conditioning/<时间戳>/`（合成分片）、
  `runs/infra/c_learner_shard_smoke.json`、`runs/infra/c_env_rebuild_20260929/`
- 复跑（CPU-only，不抢 A 的卡）：
  `CUDA_VISIBLE_DEVICES="" MUJOCO_GL=egl /root/venvs/rlrobot/bin/python scripts/c_selfcheck_goal_conditioning_t17.py`
  全量：`setsid bash scripts/c_run_all_selfchecks.sh > /tmp/c_reg.log 2>&1 < /dev/null &`
